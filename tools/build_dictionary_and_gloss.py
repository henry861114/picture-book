#!/usr/bin/env python3
"""Build the offline word dictionary and per-sentence Chinese glosses.

The word meanings come from the English-Chinese dictionary bundled with macOS
(via tools/dict_lookup), with a hand-written override table for function words,
irregular verbs, names and the small set of words the system dictionary misses.
The sentence gloss is intentionally a word-by-word Chinese reading aid, not a
literary translation; it is fully offline.
"""
import json
import glob
import os
import re

ROOT = 'app/src/main/assets/oxford/text'
DICT_OUT = 'app/src/main/assets/oxford/dictionary.json'

MANUAL = {
    # articles / determiners / pronouns
    'a': '一个', 'an': '一个', 'the': '这', 'this': '这个', 'that': '那个',
    'these': '这些', 'those': '那些', 'some': '一些', 'any': '任何', 'all': '全部',
    'each': '每个', 'every': '每个', 'both': '两个都', 'another': '另一个',
    'other': '其他', 'such': '这样的', 'same': '同样的', 'own': '自己的',
    'i': '我', 'me': '我', 'my': '我的', 'mine': '我的',
    'you': '你', 'your': '你的', 'yours': '你的',
    'he': '他', 'him': '他', 'his': '他的',
    'she': '她', 'her': '她', 'hers': '她的',
    'it': '它', 'its': '它的',
    'we': '我们', 'us': '我们', 'our': '我们的', 'ours': '我们的',
    'they': '他们', 'them': '他们', 'their': '他们的', 'theirs': '他们的',
    'who': '谁', 'whom': '谁', 'whose': '谁的', 'what': '什么', 'which': '哪个',
    'myself': '我自己', 'yourself': '你自己', 'himself': '他自己',
    'herself': '她自己', 'itself': '它自己', 'ourselves': '我们自己',
    'themselves': '他们自己', 'everyone': '每个人', 'everybody': '每个人',
    'someone': '某人', 'somebody': '某人', 'anyone': '任何人', 'anybody': '任何人',
    'nobody': '没有人', 'no-one': '没有人', 'nothing': '没有什么',
    'something': '某物', 'anything': '任何东西', 'everything': '一切',

    # prepositions / conjunctions / adverbs
    'and': '和', 'or': '或者', 'but': '但是', 'so': '所以', 'because': '因为',
    'if': '如果', 'when': '当……时', 'while': '当……的时候', 'before': '在……之前',
    'after': '在……之后', 'then': '然后', 'than': '比', 'as': '像',
    'of': '的', 'to': '到', 'in': '在……里', 'on': '在……上', 'at': '在',
    'by': '由', 'for': '为了', 'with': '和……一起', 'without': '没有',
    'from': '从', 'into': '进入', 'out': '出', 'up': '向上', 'down': '向下',
    'over': '在……上方', 'under': '在……下方', 'near': '在……附近',
    'around': '在……周围', 'through': '穿过', 'across': '穿过', 'along': '沿着',
    'behind': '在……后面', 'between': '在……之间', 'next': '下一个',
    'here': '这里', 'there': '那里', 'where': '哪里', 'everywhere': '到处',
    'inside': '里面', 'outside': '外面', 'home': '家', 'away': '离开',
    'again': '再一次', 'too': '也', 'very': '非常', 'just': '刚刚', 'only': '只有',
    'also': '也', 'still': '仍然', 'already': '已经', 'soon': '很快',
    'now': '现在', 'later': '后来', 'always': '总是', 'never': '从不',
    'sometimes': '有时', 'often': '经常', 'once': '一次', 'twice': '两次',
    'not': '不', 'no': '不', 'yes': '是', 'oh': '哦', 'ah': '啊',
    'well': '好', 'please': '请', 'thank': '谢谢', 'thanks': '谢谢',
    'hello': '你好', 'hi': '嗨', 'goodbye': '再见', 'sorry': '对不起',
    'maybe': '也许', 'perhaps': '也许', 'really': '真的', 'quite': '相当',
    'rather': '相当', 'almost': '几乎', 'together': '一起', 'alone': '独自',
    'again': '再一次', 'back': '回来', 'forward': '向前', 'later': '后来',

    # auxiliaries / common verbs
    'be': '是', 'am': '是', 'is': '是', 'are': '是', 'was': '是', 'were': '是',
    'been': '是', 'being': '正在', 'have': '有', 'has': '有', 'had': '有',
    'do': '做', 'does': '做', 'did': '做', 'done': '做完',
    'can': '能', 'could': '能', 'will': '将', 'would': '会', 'shall': '将',
    'should': '应该', 'may': '可以', 'might': '可能', 'must': '必须',
    "don't": '不', "can't": '不能', "won't": '不会', "didn't": '没有',
    "doesn't": '不', "isn't": '不是', "aren't": '不是', "wasn't": '不是',
    "weren't": '不是', "couldn't": '不能', "wouldn't": '不会', "shouldn't": '不应该',
    "let's": '让我们', "it's": '它是', "that's": '那是', "there's": '有',
    "what's": '是什么', "who's": '是谁', "i'm": '我是', "you're": '你是',
    "we're": '我们是', "they're": '他们是', "he's": '他是', "she's": '她是',
    "i've": '我已经', "we've": '我们已经', "they've": '他们已经',
    "i'll": '我会', "you'll": '你会', "we'll": '我们会', "they'll": '他们会',
    "he'll": '他会', "she'll": '她会', "it'll": '它会', "that'll": '那会',
    "there'll": '会有', "who'll": '谁会', "what'll": '什么会',
    "hasn't": '没有', "haven't": '没有', "hadn't": '没有',
    "mustn't": '不可以', "needn't": '不必', "shan't": '不会',
    "mightn't": '可能不',
    'go': '去', 'goes': '去', 'went': '去', 'gone': '去了',
    'come': '来', 'comes': '来', 'came': '来',
    'run': '跑', 'runs': '跑', 'ran': '跑', 'running': '跑',
    'look': '看', 'looks': '看', 'looked': '看', 'looking': '看',
    'see': '看见', 'sees': '看见', 'saw': '看见', 'seen': '看见',
    'say': '说', 'says': '说', 'said': '说', 'saying': '说',
    'tell': '告诉', 'told': '告诉', 'telling': '告诉',
    'get': '得到', 'gets': '得到', 'got': '得到', 'gotten': '得到',
    'make': '做', 'makes': '做', 'made': '做', 'making': '做',
    'take': '拿', 'takes': '拿', 'took': '拿', 'taken': '拿',
    'give': '给', 'gives': '给', 'gave': '给', 'given': '给',
    'find': '找到', 'finds': '找到', 'found': '找到',
    'think': '想', 'thinks': '想', 'thought': '想',
    'know': '知道', 'knows': '知道', 'knew': '知道', 'known': '知道',
    'want': '想要', 'wants': '想要', 'wanted': '想要',
    'like': '喜欢', 'likes': '喜欢', 'liked': '喜欢',
    'love': '爱', 'loves': '爱', 'loved': '爱',
    'help': '帮助', 'helps': '帮助', 'helped': '帮助',
    'play': '玩', 'plays': '玩', 'played': '玩', 'playing': '玩',
    'eat': '吃', 'eats': '吃', 'ate': '吃', 'eaten': '吃',
    'drink': '喝', 'drinks': '喝', 'drank': '喝', 'drunk': '喝',
    'sleep': '睡觉', 'sleeps': '睡觉', 'slept': '睡觉',
    'wake': '醒来', 'wakes': '醒来', 'woke': '醒来', 'woken': '醒来',
    'put': '放', 'puts': '放', 'putting': '放',
    'open': '打开', 'opens': '打开', 'opened': '打开',
    'close': '关上', 'closes': '关上', 'closed': '关上',
    'stop': '停', 'stops': '停', 'stopped': '停',
    'start': '开始', 'starts': '开始', 'started': '开始',
    'jump': '跳', 'jumps': '跳', 'jumped': '跳',
    'walk': '走', 'walks': '走', 'walked': '走',
    'ride': '骑', 'rides': '骑', 'rode': '骑', 'ridden': '骑',
    'swim': '游泳', 'swims': '游泳', 'swam': '游泳', 'swum': '游泳',
    'fly': '飞', 'flies': '飞', 'flew': '飞', 'flown': '飞',
    'fall': '落下', 'falls': '落下', 'fell': '落下', 'fallen': '落下',
    'climb': '爬', 'climbs': '爬', 'climbed': '爬',
    'carry': '搬运', 'carries': '搬运', 'carried': '搬运',
    'pull': '拉', 'pulls': '拉', 'pulled': '拉',
    'push': '推', 'pushes': '推', 'pushed': '推',
    'wash': '洗', 'washes': '洗', 'washed': '洗',
    'clean': '打扫', 'cleans': '打扫', 'cleaned': '打扫',
    'cook': '做饭', 'cooks': '做饭', 'cooked': '做饭',
    'sing': '唱歌', 'sings': '唱歌', 'sang': '唱歌', 'sung': '唱歌',
    'dance': '跳舞', 'dances': '跳舞', 'danced': '跳舞',
    'laugh': '笑', 'laughs': '笑', 'laughed': '笑',
    'cry': '哭', 'cries': '哭', 'cried': '哭',
    'shout': '喊', 'shouts': '喊', 'shouted': '喊',
    'ask': '问', 'asks': '问', 'asked': '问',
    'answer': '回答', 'answers': '回答', 'answered': '回答',
    'call': '叫', 'calls': '叫', 'called': '叫',
    'wait': '等', 'waits': '等', 'waited': '等',
    'live': '住', 'lives': '住', 'lived': '住',
    'sit': '坐', 'sits': '坐', 'sat': '坐',
    'stand': '站', 'stands': '站', 'stood': '站',
    'speak': '说', 'speaks': '说', 'spoke': '说', 'spoken': '说',
    'win': '赢', 'wins': '赢', 'won': '赢',
    'lose': '丢失', 'loses': '丢失', 'lost': '丢失',
    'leave': '离开', 'leaves': '离开', 'left': '离开',
    'feel': '感觉', 'feels': '感觉', 'felt': '感觉',
    'keep': '保持', 'keeps': '保持', 'kept': '保持',
    'meet': '遇见', 'meets': '遇见', 'met': '遇见',
    'pay': '付钱', 'pays': '付钱', 'paid': '付钱',
    'sell': '卖', 'sells': '卖', 'sold': '卖',
    'send': '发送', 'sends': '发送', 'sent': '发送',
    'spend': '花费', 'spends': '花费', 'spent': '花费',
    'build': '建造', 'builds': '建造', 'built': '建造',
    'burn': '烧', 'burns': '烧', 'burnt': '烧', 'burned': '烧',
    'learn': '学习', 'learns': '学习', 'learnt': '学习', 'learned': '学习',
    'mean': '意思是', 'means': '意思是', 'meant': '意思是',
    'hear': '听见', 'hears': '听见', 'heard': '听见',
    'hold': '拿着', 'holds': '拿着', 'held': '拿着',
    'fight': '打架', 'fights': '打架', 'fought': '打架',
    'break': '打破', 'breaks': '打破', 'broke': '打破', 'broken': '打破',
    'choose': '选择', 'chooses': '选择', 'chose': '选择', 'chosen': '选择',
    'drive': '驾驶', 'drives': '驾驶', 'drove': '驾驶', 'driven': '驾驶',
    'write': '写', 'writes': '写', 'wrote': '写', 'written': '写',
    'read': '读', 'reads': '读', 'reading': '读',
    'cut': '切', 'cuts': '切', 'cutting': '切',
    'let': '让', 'lets': '让', 'letting': '让',
    'set': '设置', 'sets': '设置', 'setting': '设置',
    'shut': '关上', 'shuts': '关上', 'shutting': '关上',
    'cost': '花费', 'costs': '花费',
    'hurt': '受伤', 'hurts': '受伤',
    'bring': '带来', 'brings': '带来', 'brought': '带来',
    'buy': '买', 'buys': '买', 'bought': '买',
    'catch': '抓住', 'catches': '抓住', 'caught': '抓住',
    'become': '成为', 'becomes': '成为', 'became': '成为',
    'begin': '开始', 'begins': '开始', 'began': '开始', 'begun': '开始',
    'forget': '忘记', 'forgets': '忘记', 'forgot': '忘记',
    'understand': '理解', 'understands': '理解', 'understood': '理解',
    'wear': '穿', 'wears': '穿', 'wore': '穿', 'worn': '穿',
    'throw': '扔', 'throws': '扔', 'threw': '扔', 'thrown': '扔',
    'show': '展示', 'shows': '展示', 'showed': '展示', 'shown': '展示',

    # nouns
    'mum': '妈妈', 'dad': '爸爸', 'mother': '妈妈', 'father': '爸爸',
    'parents': '父母', 'family': '家庭', 'home': '家', 'house': '房子',
    'school': '学校', 'class': '班级', 'teacher': '老师', 'friend': '朋友',
    'friends': '朋友们', 'boy': '男孩', 'girl': '女孩', 'children': '孩子们',
    'child': '孩子', 'man': '男人', 'woman': '女人', 'men': '男人们',
    'women': '女人们', 'people': '人们', 'dog': '狗', 'cat': '猫',
    'bird': '鸟', 'fish': '鱼', 'animal': '动物', 'tree': '树',
    'case': '箱子', 'cases': '箱子', 'unload': '卸下', 'unloaded': '卸下',
    'load': '装载', 'loaded': '装载', 'dear': '亲爱的', 'upside': '上下颠倒',
    'heads': '正面', 'tails': '反面', 'coin': '硬币', 'bunk': '床铺',
    'flower': '花', 'flowers': '花', 'leaf': '叶子', 'leaves': '叶子',
    'sun': '太阳', 'moon': '月亮', 'star': '星星', 'sky': '天空',
    'sea': '海', 'beach': '海滩', 'island': '岛屿', 'river': '河',
    'hill': '小山', 'park': '公园', 'garden': '花园', 'farm': '农场',
    'road': '路', 'street': '街道', 'car': '汽车', 'bus': '公共汽车',
    'train': '火车', 'boat': '船', 'plane': '飞机', 'bike': '自行车',
    'shop': '商店', 'market': '市场', 'book': '书', 'story': '故事',
    'page': '页', 'picture': '图画', 'name': '名字', 'ball': '球',
    'toy': '玩具', 'toys': '玩具', 'game': '游戏', 'games': '游戏',
    'party': '聚会', 'birthday': '生日', 'cake': '蛋糕', 'food': '食物',
    'milk': '牛奶', 'water': '水', 'table': '桌子', 'chair': '椅子',
    'door': '门', 'window': '窗户', 'room': '房间', 'bed': '床',
    'kitchen': '厨房', 'floor': '地板', 'wall': '墙', 'box': '盒子',
    'bag': '包', 'hat': '帽子', 'coat': '外套', 'shoe': '鞋',
    'shoes': '鞋', 'clothes': '衣服', 'day': '一天', 'night': '夜晚',
    'morning': '早晨', 'afternoon': '下午', 'evening': '晚上',
    'week': '星期', 'time': '时间', 'way': '方式', 'thing': '东西',
    'things': '东西', 'place': '地方', 'world': '世界', 'color': '颜色',
    'colour': '颜色', 'sound': '声音', 'noise': '噪音', 'word': '单词',
    'words': '单词', 'letter': '信', 'card': '卡片', 'present': '礼物',
    'presents': '礼物', 'money': '钱', 'shop': '商店', 'supermarket': '超市',
    'basket': '篮子', 'bottle': '瓶子', 'cup': '杯子', 'plate': '盘子',
    'spoon': '勺子', 'knife': '刀', 'fork': '叉子', 'bowl': '碗',
    'sugar': '糖', 'salt': '盐', 'bread': '面包', 'sandwich': '三明治',
    'biscuit': '饼干', 'biscuits': '饼干', 'egg': '鸡蛋', 'eggs': '鸡蛋',
    'apple': '苹果', 'apples': '苹果', 'banana': '香蕉', 'orange': '橙子',
    'crisps': '薯片', 'comic': '漫画', 'magazine': '杂志', 'newspaper': '报纸',
    'television': '电视', 'radio': '收音机', 'phone': '电话', 'computer': '电脑',
    'camera': '相机', 'clock': '钟', 'watch': '手表', 'key': '钥匙',
    'map': '地图', 'ticket': '票', 'umbrella': '雨伞', 'basket': '篮子',
    'bubble': '泡泡', 'bubbles': '泡泡', 'balloon': '气球', 'balloons': '气球',
    'kite': '风筝', 'robot': '机器人', 'dragon': '龙', 'monster': '怪物',
    'princess': '公主', 'king': '国王', 'queen': '女王', 'witch': '女巫',
    'pirate': '海盗', 'pirates': '海盗', 'castle': '城堡', 'treasure': '宝藏',
    'adventure': '冒险', 'holiday': '假期', 'birthday': '生日', 'party': '聚会',

    # adjectives / adverbs
    'big': '大的', 'little': '小的', 'small': '小的', 'good': '好的',
    'bad': '坏的', 'new': '新的', 'old': '旧的', 'happy': '快乐的',
    'sad': '伤心的', 'hot': '热的', 'cold': '冷的', 'wet': '湿的',
    'dry': '干的', 'muddy': '泥泞的', 'dirty': '脏的', 'hungry': '饿的',
    'thirsty': '渴的', 'tired': '累的', 'excited': '兴奋的', 'afraid': '害怕的',
    'angry': '生气的', 'funny': '有趣的', 'beautiful': '美丽的', 'long': '长的',
    'short': '短的', 'tall': '高的', 'fast': '快的', 'slow': '慢的',
    'red': '红色的', 'blue': '蓝色的', 'green': '绿色的', 'yellow': '黄色的',
    'black': '黑色的', 'white': '白色的', 'brown': '棕色的', 'pink': '粉色的',
    'purple': '紫色的', 'orange': '橙色的', 'one': '一', 'two': '二',
    'three': '三', 'four': '四', 'five': '五', 'six': '六', 'seven': '七',
    'eight': '八', 'nine': '九', 'ten': '十', 'first': '第一', 'second': '第二',
    'third': '第三', 'many': '许多', 'much': '许多', 'more': '更多',
    'most': '最多', 'few': '很少', 'lots': '许多', 'lot': '许多',
    'enough': '足够', 'full': '满的', 'empty': '空的', 'heavy': '重的',
    'light': '轻的', 'strong': '强壮的', 'weak': '虚弱的', 'young': '年轻的',
    'nice': '好的', 'kind': '友善的', 'clever': '聪明的', 'silly': '傻的',
    'loud': '大声的', 'quiet': '安静的', 'safe': '安全的', 'dangerous': '危险的',
    'famous': '著名的', 'different': '不同的', 'same': '同样的', 'ready': '准备好的',
    'busy': '忙碌的', 'free': '自由的', 'important': '重要的', 'interesting': '有趣的',
    'wonderful': '精彩的', 'great': '很棒的', 'super': '超级的', 'real': '真的',
    'wrong': '错误的', 'right': '正确的', 'true': '真实的', 'false': '假的',
    'better': '更好的', 'best': '最好的', 'worse': '更坏的', 'worst': '最坏的',
    'damaged': '被损坏的', 'dumping': '倾倒', 'hooray': '好耶', 'stuff': '东西',
    "o'clock": '……点钟', "you've": '你已经', 'grrr': '吼（拟声）',
}

PHONETIC = {
    'a': 'ə', 'an': 'ən', 'the': 'ðə', 'and': 'ænd', 'to': 'tuː', 'of': 'ɒv',
    'in': 'ɪn', 'on': 'ɒn', 'at': 'æt', 'is': 'ɪz', 'are': 'ɑː', 'was': 'wɒz',
    'were': 'wɜː', 'be': 'biː', 'he': 'hiː', 'she': 'ʃiː', 'it': 'ɪt',
    'we': 'wiː', 'they': 'ðeɪ', 'you': 'juː', 'i': 'aɪ', 'me': 'miː',
    'my': 'maɪ', 'your': 'jɔː', 'his': 'hɪz', 'her': 'hɜː', 'our': 'aʊə',
    'their': 'ðeə', 'who': 'huː', 'what': 'wɒt', 'where': 'weə', 'when': 'wen',
    'why': 'waɪ', 'how': 'haʊ', 'no': 'nəʊ', 'yes': 'jes', 'not': 'nɒt',
    'can': 'kæn', 'could': 'kʊd', 'will': 'wɪl', 'would': 'wʊd',
    'should': 'ʃʊd', 'may': 'meɪ', 'might': 'maɪt', 'must': 'mʌst',
    'do': 'duː', 'does': 'dʌz', 'did': 'dɪd', 'have': 'hæv', 'has': 'hæz',
    'had': 'hæd', 'go': 'ɡəʊ', 'come': 'kʌm', 'look': 'lʊk', 'see': 'siː',
    'run': 'rʌn', 'said': 'sed', 'want': 'wɒnt', 'like': 'laɪk', 'get': 'ɡet',
    'make': 'meɪk', 'take': 'teɪk', 'give': 'ɡɪv', 'play': 'pleɪ',
    'eat': 'iːt', 'drink': 'drɪŋk', 'sleep': 'sliːp', 'wake': 'weɪk',
    'mum': 'mʌm', 'dad': 'dæd', 'house': 'haʊs', 'school': 'skuːl',
    'dog': 'dɒɡ', 'cat': 'kæt', 'big': 'bɪɡ', 'little': 'ˈlɪtl',
    'good': 'ɡʊd', 'bad': 'bæd', 'new': 'njuː', 'old': 'əʊld',
    'red': 'red', 'blue': 'bluː', 'green': 'ɡriːn', 'yellow': 'ˈjeləʊ',
    'black': 'blæk', 'white': 'waɪt',
}

NAMES = {
    'biff': '比夫', 'chip': '奇普', 'kipper': '基珀', 'wilf': '威尔夫',
    'wilma': '威尔玛', 'floppy': '弗洛皮', 'nadim': '纳迪姆', 'anneena': '安妮娜',
    'buster': '巴斯特', 'lee': '李', 'rosie': '罗西', 'ellie': '埃莉',
    'gran': '奶奶', 'grandma': '奶奶', 'grandpa': '爷爷',
    'mrs': '太太', 'mr': '先生', 'miss': '小姐', 'ms': '女士', 'dr': '医生',
    'johnson': '约翰逊', 'may': '梅', 'honey': '哈尼', 'seabay': '西湾',
    'omar': '奥马尔', 'adeel': '阿迪尔', 'zak': '扎克', 'martha': '玛莎',
    'cairo': '开罗', 'tiger': '泰格', 'annie': '安妮', 'joe': '乔',
    'jack': '杰克', 'tom': '汤姆', 'sam': '萨姆', 'ben': '本', 'max': '马克斯',
    'molly': '莫莉', 'lilly': '莉莉', 'billy': '比利', 'danny': '丹尼',
    'sunny': '桑尼', 'bunny': '邦尼', 'robin': '罗宾', 'hood': '胡德',
    'fiona': '菲奥娜',
}

IRREGULAR = {
    'am': 'be', 'is': 'be', 'are': 'be', 'was': 'be', 'were': 'be', 'been': 'be',
    'has': 'have', 'had': 'have', 'having': 'have',
    'does': 'do', 'did': 'do', 'done': 'do',
    'says': 'say', 'said': 'say',
    'goes': 'go', 'went': 'go', 'gone': 'go',
    'comes': 'come', 'came': 'come',
    'gets': 'get', 'got': 'get', 'gotten': 'get',
    'makes': 'make', 'made': 'make',
    'takes': 'take', 'took': 'take', 'taken': 'take',
    'gives': 'give', 'gave': 'give', 'given': 'give',
    'finds': 'find', 'found': 'find',
    'thinks': 'think', 'thought': 'think',
    'knows': 'know', 'knew': 'know', 'known': 'know',
    'runs': 'run', 'ran': 'run',
    'sees': 'see', 'saw': 'see', 'seen': 'see',
    'eats': 'eat', 'ate': 'eat', 'eaten': 'eat',
    'drinks': 'drink', 'drank': 'drink', 'drunk': 'drink',
    'sleeps': 'sleep', 'slept': 'sleep',
    'wakes': 'wake', 'woke': 'wake', 'woken': 'wake',
    'wears': 'wear', 'wore': 'wear', 'worn': 'wear',
    'sits': 'sit', 'sat': 'sit',
    'stands': 'stand', 'stood': 'stand',
    'speaks': 'speak', 'spoke': 'speak', 'spoken': 'speak',
    'swims': 'swim', 'swam': 'swim', 'swum': 'swim',
    'wins': 'win', 'won': 'win',
    'loses': 'lose', 'lost': 'lose',
    'leaves': 'leave', 'left': 'leave',
    'feels': 'feel', 'felt': 'feel',
    'keeps': 'keep', 'kept': 'keep',
    'meets': 'meet', 'met': 'meet',
    'pays': 'pay', 'paid': 'pay',
    'sells': 'sell', 'sold': 'sell',
    'sends': 'send', 'sent': 'send',
    'spends': 'spend', 'spent': 'spend',
    'builds': 'build', 'built': 'build',
    'burns': 'burn', 'burnt': 'burn',
    'learns': 'learn', 'learnt': 'learn',
    'means': 'mean', 'meant': 'mean',
    'hears': 'hear', 'heard': 'hear',
    'holds': 'hold', 'held': 'hold',
    'fights': 'fight', 'fought': 'fight',
    'falls': 'fall', 'fell': 'fall', 'fallen': 'fall',
    'breaks': 'break', 'broke': 'break', 'broken': 'break',
    'chooses': 'choose', 'chose': 'choose', 'chosen': 'choose',
    'drives': 'drive', 'drove': 'drive', 'driven': 'drive',
    'rides': 'ride', 'rode': 'ride', 'ridden': 'ride',
    'writes': 'write', 'wrote': 'write', 'written': 'write',
    'brings': 'bring', 'brought': 'bring',
    'buys': 'buy', 'bought': 'buy',
    'catches': 'catch', 'caught': 'catch',
    'becomes': 'become', 'became': 'become',
    'begins': 'begin', 'began': 'begin', 'begun': 'begin',
    'forgets': 'forget', 'forgot': 'forget', 'forgotten': 'forget',
    'understands': 'understand', 'understood': 'understand',
    'throws': 'throw', 'threw': 'throw', 'thrown': 'throw',
    'shows': 'show', 'showed': 'show', 'shown': 'show',
    'children': 'child', 'men': 'man', 'women': 'woman', 'people': 'person',
    'feet': 'foot', 'teeth': 'tooth', 'mice': 'mouse',
    'better': 'good', 'best': 'good', 'worse': 'bad', 'worst': 'bad',
}

SKIP_RUNS = {
    '名', '动', '形', '副', '代', '介', '连', '助', '量', '数', '叹', '拟',
    '前缀', '后缀', '可数', '不可数', '英', '美', '口', '俚', '书', '方',
    '古', '诗', '喻', '转', '贬', '褒', '敬', '谦', '婉', '俗', '罕', '废',
    '旧', '新', '专', '缩', '略', '音译用字', '用于', '同', '姓', '地名',
    '人名', '另见', '参见', '复数', '过去式', '过去分词', '比较级', '最高级',
}


def parse_def(desc):
    desc = desc.strip()
    phonetic = ''
    m = re.search(r'BrE\s+([^,|]+)', desc)
    if not m:
        m = re.search(r'AmE\s+([^,|]+)', desc)
    if m:
        phonetic = m.group(1).strip()
    d = re.sub(r'\[[^\]]*\]', ' ', desc)
    d = re.sub(r'\([^)]*\)', ' ', d)
    d = re.sub(r'（[^）]*）', ' ', d)
    runs = re.findall(r'[\u4e00-\u9fff]+', d)
    for r in runs:
        if r in SKIP_RUNS:
            continue
        if len(r) >= 1:
            return phonetic, r
    return phonetic, ''


def base_candidates(word):
    w = word.lower().replace('’', "'")
    out = []
    if w in IRREGULAR:
        out.append(IRREGULAR[w])
    if w.endswith("'s"):
        out.append(w[:-2])
    if w.endswith('ies') and len(w) > 4:
        out.append(w[:-3] + 'y')
    if w.endswith('es') and len(w) > 3:
        out.append(w[:-2])
    if w.endswith('s') and len(w) > 2:
        out.append(w[:-1])
    if w.endswith('ed') and len(w) > 3:
        stem = w[:-2]
        out.append(stem)
        out.append(w[:-1])
        if len(stem) > 2 and stem[-1] == stem[-2]:
            out.append(stem[:-1])
    if w.endswith('ing') and len(w) > 4:
        stem = w[:-3]
        out.append(stem)
        out.append(stem + 'e')
        if len(stem) > 2 and stem[-1] == stem[-2]:
            out.append(stem[:-1])
    if w.endswith('er') and len(w) > 3:
        out.append(w[:-2])
        out.append(w[:-1])
    if w.endswith('est') and len(w) > 4:
        out.append(w[:-3])
        out.append(w[:-2])
    return out


def main():
    defs = {}
    for line in open('/tmp/oxford_defs.tsv', encoding='utf-8'):
        parts = line.rstrip('\n').split('\t', 1)
        if len(parts) == 2:
            defs[parts[0].lower()] = parts[1]

    words = set()
    for path in glob.glob(os.path.join(ROOT, '*.json')):
        d = json.load(open(path))
        for page in d['pages']:
            for s in page['sentences']:
                for m in re.finditer(r"[A-Za-z]+(?:['’\-][A-Za-z]+)*", s['en']):
                    words.add(m.group(0).lower().replace('’', "'"))
    # Green Island shares the same word popup dictionary.
    story_path = 'app/src/main/assets/story.json'
    if os.path.exists(story_path):
        story = json.load(open(story_path))
        for page in story.get('pages', []):
            for segment in page.get('segments', []):
                for m in re.finditer(r"[A-Za-z]+(?:['’\-][A-Za-z]+)*", segment.get('en', '')):
                    words.add(m.group(0).lower().replace('’', "'"))

    dictionary = {}
    for w in sorted(words):
        entry = {'p': '', 'z': ''}
        if w in MANUAL:
            entry['z'] = MANUAL[w]
        if w in NAMES:
            entry['z'] = NAMES[w]
        # phonetic from the surface form if available
        if w in defs:
            p, z = parse_def(defs[w])
            if p and not entry['p']:
                entry['p'] = p
            if not entry['z'] and z:
                entry['z'] = z
        # Fall back to a base form, but never override an exact manual/name entry.
        if w not in MANUAL and w not in NAMES:
            for base in base_candidates(w):
                if base in MANUAL and MANUAL[base]:
                    entry['z'] = MANUAL[base]
                    break
                if base in NAMES and NAMES[base]:
                    entry['z'] = NAMES[base]
                    break
                if base in defs and not entry['z']:
                    p, z = parse_def(defs[base])
                    if z:
                        entry['z'] = z
                    if p and not entry['p']:
                        entry['p'] = p
                    break
        # last resort: surface definition
        if not entry['z'] and w in defs:
            p, z = parse_def(defs[w])
            entry['z'] = z
            if p and not entry['p']:
                entry['p'] = p
        if w in PHONETIC:
            entry['p'] = PHONETIC[w]
        dictionary[w] = entry

    os.makedirs(os.path.dirname(DICT_OUT), exist_ok=True)
    with open(DICT_OUT, 'w', encoding='utf-8') as f:
        json.dump(dictionary, f, ensure_ascii=False, indent=1, sort_keys=True)

    def lookup(word):
        w = word.lower().replace('’', "'")
        e = dictionary.get(w)
        if e and e.get('z'):
            return e['z']
        for base in base_candidates(w):
            e = dictionary.get(base)
            if e and e.get('z'):
                return e['z']
            if base in MANUAL:
                return MANUAL[base]
        return ''

    def gloss(text):
        ms = list(re.finditer(r"[A-Za-z]+(?:['’\-][A-Za-z]+)*", text))
        if not ms:
            return ''
        out = []
        last = 0
        for m in ms:
            out.append(convert_punct(text[last:m.start()]))
            z = lookup(m.group(0))
            out.append(z if z else m.group(0))
            last = m.end()
        out.append(convert_punct(text[last:]))
        s = ''.join(out)
        s = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', s)
        s = re.sub(r'\s+([。，！？；：、])', r'\1', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    def convert_punct(s):
        return (s.replace('“', '').replace('”', '').replace('"', '')
                  .replace('?', '？').replace('!', '！').replace(',', '，')
                  .replace(';', '；').replace(':', '：').replace('.', '。'))

    total = 0
    missing = 0
    for path in sorted(glob.glob(os.path.join(ROOT, '*.json'))):
        d = json.load(open(path))
        for page in d['pages']:
            for s in page['sentences']:
                s['zh'] = gloss(s['en'])
                total += 1
                if not s['zh']:
                    missing += 1
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    print(f'dictionary entries: {len(dictionary)}; sentences: {total}; missing gloss: {missing}')


if __name__ == '__main__':
    main()
