# Liên kết thất bại và cách báo nhiều mẫu cùng kết thúc

> **Chủ đề:** Computer Science Algorithms → **Tìm kiếm chuỗi**.  
> **Mục tiêu:** Hiểu cơ chế failure link của thuật toán **Aho–Corasick**, cách quét một văn bản theo trie và liên kết thất bại, và đặc biệt cách **báo mọi mẫu có cùng vị trí kết thúc** bằng output link. Trình bày cả cách đếm số lần xuất hiện không cần phát từng kết quả, xử lý các mẫu trùng ID, Unicode, kiểm thử Java 17 và độ phức tạp.

## 1. Định nghĩa bài toán

Cho văn bản `T` và một danh sách các mẫu **không rỗng**:

`P[0], P[1], ..., P[k−1]`.

Mỗi mẫu mang **ID bằng vị trí trong danh sách**. Có thể tồn tại hai ID có nội dung giống nhau, chẳng hạn P[0]=`he` và P[5]=`he`.

Cần tìm **mọi lần xuất hiện** dưới dạng:

`(patternId, start, endExclusive)`.

Khoảng `[start,endExclusive)` là đoạn text chứa mẫu, đánh số từ 0, **không bao gồm vị trí endExclusive**. Bởi vậy `endExclusive−start` bằng độ dài mẫu trong cùng đơn vị ký tự.

Một vị trí kết thúc có thể tương ứng **nhiều mẫu khác nhau**. Một mẫu cũng có thể xuất hiện nhiều lần **chồng lấn**. Trong bài này, khi các mẫu có nội dung trùng nhau nhưng ID khác nhau, mỗi ID tạo **một sự kiện khớp riêng**.

### 1.1. Bộ ví dụ xuyên suốt

Các mẫu theo thứ tự:

| ID | Mẫu |
|---:|---|
| 0 | `he` |
| 1 | `she` |
| 2 | `his` |
| 3 | `hers` |
| 4 | `e` |
| 5 | `he` |
| 6 | `ers` |
| 7 | `rs` |
| 8 | `s` |
| 9 | `hers` |

Văn bản `T = "ushers"`:

```text
Index:  0 1 2 3 4 5
Text:   u s h e r s
```

Các kết quả:

```text
[1,2)  ID 8: s
[1,4)  ID 1: she
[2,4)  ID 0: he
[2,4)  ID 5: he
[3,4)  ID 4: e
[2,6)  ID 3: hers
[2,6)  ID 9: hers
[3,6)  ID 6: ers
[4,6)  ID 7: rs
[5,6)  ID 8: s
```

Tổng **10 sự kiện khớp**. Đặc biệt tại `endExclusive=4` có **4 sự kiện**, tại `endExclusive=6` có **5 sự kiện**.

Nếu thuật toán chỉ in **mẫu dài nhất**, chỉ in **node terminal hiện tại** hoặc chỉ in **một ID** của mỗi node, nó sẽ bỏ sót kết quả. Đây là vấn đề trung tâm của bài học.

## 2. Trie và ý nghĩa trạng thái

Aho–Corasick bắt đầu từ một **trie**, tức cây lưu tất cả **tiền tố** của các mẫu.

- `root` biểu diễn chuỗi rỗng.
- `next[v][c]` trỏ tới node biểu diễn `label(v)` nối ký tự c, nếu cạnh trie đó tồn tại.
- `label(v)` là chuỗi ký tự đọc từ root tới node v.
- `depth(v)=|label(v)|`.
- `terminalIds[v]` là **danh sách ID mẫu kết thúc đúng tại v**. Một node terminal có thể chứa nhiều ID của các mẫu trùng nội dung.

Ví dụ:

```text
(root)
  ├─ h ─ e* ─ r ─ s*
  │     └ ...
  ├─ s ─ h ─ e*
  ├─ e*
  └─ r ─ s*

* biểu thị node terminal của một hay nhiều ID
```

Với 10 mẫu trên, node `he` lưu IDs `[0,5]`; node `hers` lưu IDs `[3,9]`.

Trie giải quyết việc chia sẻ tiền tố, nhưng nếu chỉ có trie và thử lại từ từng vị trí đầu text, có thể tốn thời gian lớn. **Failure links** giúp dùng lại phần hậu tố đã quét thay vì bắt đầu lại từ đầu.

### 2.1. Bất biến trạng thái khi scan

Sau khi đọc xong một tiền tố text, node `state` của Aho–Corasick biểu diễn:

**Hậu tố dài nhất của text đã đọc mà đồng thời là một tiền tố của ít nhất một mẫu.**

Nếu ký tự tiếp theo c có cạnh trie từ state, đi theo cạnh đó. Nếu không, thử các hậu tố ngắn hơn qua failure links.

Ví dụ sau khi đã đọc `she`, state là node `she`. Khi đọc tiếp ký tự `r`, không có cạnh trie `she→r`; nhưng suffix `he` có cạnh tới node `her`, nên state tiếp theo là `her`.

## 3. Failure link: hậu tố dài nhất còn hữu ích

Với mỗi node v khác root, định nghĩa:

`fail[v] = node biểu diễn hậu tố thực sự dài nhất của label(v) cũng là một tiền tố tồn tại trong trie`.

**Hậu tố thực sự** không được bằng chính chuỗi đang xét; nghĩa là `depth(fail[v]) < depth(v)`. Nếu không có hậu tố như vậy, trỏ root.

### 3.1. Ví dụ các liên kết

Với bộ mẫu xuyên suốt:

- `fail["she"] = "he"`.
- `fail["he"] = "e"`.
- `fail["e"] = root`.
- `fail["hers"] = "ers"`.
- `fail["ers"] = "rs"`.
- `fail["rs"] = "s"`.
- `fail["s"] = root`.

Chuỗi thất bại từ `hers`:

```text
hers → ers → rs → s → root
```

Những node này biểu diễn **các suffix đang khớp**, không phải các vị trí tùy ý.

### 3.2. Failure link khác output link

`fail[v]` có thể trỏ tới một node **không terminal**. Nó chủ yếu giúp chuyển trạng thái khi **thiếu cạnh**.

Trong khi đó, nếu đang cần báo mọi mẫu vừa kết thúc, ta muốn nhảy nhanh giữa các node **terminal** trên chuỗi fail. Vì thế ta xây thêm `outputLink[v]`, được giải thích ở phần 5.

Không được nhầm: failure link chỉ đảm bảo **có thể tiếp tục tìm kiếm**, còn output link là cơ chế **không bỏ sót mẫu khớp**.

### 3.3. Tại sao không có vòng fail vô hạn?

Failure link của mọi node khác root đều đến node có độ sâu nhỏ hơn. Vì depth là số nguyên không âm, đi theo fail cuối cùng sẽ tới root. Chỉ root có `fail[root]=root` theo quy ước.

## 4. Xây failure links bằng BFS

Tạo xong toàn bộ trie rồi mới xây failure links.

Khởi tạo:

- `fail[root]=root`.
- Với các con trực tiếp của root: `fail[child]=root`.
- Đưa các con root vào queue BFS.

Khi xử lý cạnh trie `u --c--> v`:

1. Bắt đầu `f=fail[u]`.
2. Trong khi `f!=root` và node f không có cạnh c, đi `f=fail[f]`.
3. Nếu từ f có cạnh c, lấy `fail[v]=next[f][c]`.
4. Nếu không có cạnh c kể cả ở root, lấy `fail[v]=root`.

```text
buildFailures():
    queue = tất cả con trực tiếp của root
    fail[root] = root
    fail[child của root] = root

    while queue không rỗng:
        u = popFront(queue)

        for mỗi cạnh trie u --c--> v:
            f = fail[u]
            while f != root and next[f][c] không tồn tại:
                f = fail[f]

            if next[f][c] tồn tại:
                fail[v] = next[f][c]
            else:
                fail[v] = root

            pushBack(queue, v)
```

Dùng **BFS theo độ sâu** là quan trọng: khi xử lý v, các liên kết của những node nông hơn mà ta dùng để tính `fail[v]` đã được xây xong.

### 4.1. Tính fail của `she`

`she` là con của `sh` theo ký tự `e`.

Giả sử `fail["sh"]="h"`. Từ `h` có cạnh `e` tới `he`, nên:

`fail["she"]="he"`.

Node `he` terminal, và `fail["he"]="e"` cũng terminal. Tại cùng điểm kết thúc của `she`, các mẫu `she`, `he` và `e` đều khớp.

### 4.2. Tính fail của `hers`

Theo các tiền tố có trong trie:

```text
fail[hers] = ers
fail[ers]  = rs
fail[rs]   = s
fail[s]    = root
```

Tại end cuối văn bản `ushers`, state là `hers`, nên cần báo tất cả ID của node `hers`, `ers`, `rs`, `s`.

### 4.3. Không thêm mẫu sau khi build rồi giữ nguyên fail

Nếu thêm một mẫu mới tạo ra tiền tố/hậu tố mà trước đó chưa có, failure links của các node cũ có thể thay đổi. Cách đơn giản và đúng là **xây lại** automaton khi bộ mẫu được cập nhật; bài toán từ điển động cần cấu trúc chuyên biệt nếu muốn tránh rebuild.

## 5. Báo nhiều mẫu cùng kết thúc bằng outputLink

Mỗi node v có:

`terminalIds[v]`: ID mẫu có chuỗi **đúng bằng** `label(v)`.

Định nghĩa:

`outputLink[v] = node terminal gần nhất nằm trên chuỗi fail bắt đầu từ fail[v]`.

Nếu không có node terminal như vậy, `outputLink[v]=root` (sentinel). Không chấp nhận mẫu rỗng trong các chương trình này, nên root không terminal.

Khi BFS xây fail của v, có thể tính ngay:

```text
f = fail[v]
if terminalIds[f] không rỗng:
    outputLink[v] = f
else:
    outputLink[v] = outputLink[f]
```

Vì node f nông hơn v, `outputLink[f]` đã được tính.

### 5.1. Thao tác emit đúng

Sau khi quét mỗi ký tự và cập nhật state:

```text
emit terminalIds[state]

v = outputLink[state]
while v != root:
    emit terminalIds[v]
    v = outputLink[v]
```

Mỗi bước qua outputLink tới **một node terminal có ít nhất một ID**, nên thời gian báo output tỷ lệ với số match được báo, không phải chiều dài của chuỗi fail có nhiều node không terminal.

### 5.2. Output của `she`

Ở end4, state là `she`:

```text
node she : terminalIds = [1]
   ↓ outputLink
node he  : terminalIds = [0,5]
   ↓ outputLink
node e   : terminalIds = [4]
   ↓ outputLink
root     : stop
```

Kết quả theo thứ tự này: IDs **1,0,5,4**. Cùng end4, các start tương ứng là 1,2,2,3.

### 5.3. Output của `hers`

Ở end6:

```text
hers : [3,9]
  ↓
ers  : [6]
  ↓
rs   : [7]
  ↓
s    : [8]
  ↓
root
```

Kết quả: IDs **3,9,6,7,8** — năm sự kiện ở cùng một điểm kết thúc.

### 5.4. Hai biến thể khác

**Đi cả chuỗi fail khi báo:** từ state liên tục `v=fail[v]`, tại mỗi node kiểm terminalIds. Cách này đúng nhưng có thể phải kiểm rất nhiều node **không terminal**.

**Sao chép toàn bộ outputs của fail node:** khi build, dùng:

`outputs[v] = terminalIds[v] nối tiếp outputs[fail[v]]`.

Lúc scan chỉ cần phát `outputs[state]`. Đây là biến thể dễ viết, nhưng những danh sách output dài có thể bị **nhân bản qua nhiều node**, làm chi phí xây và bộ nhớ cao, trong trường hợp xấu có thể bậc hai theo độ lớn trie.

Với từ điển lớn, giữ `terminalIds` và `outputLink` thường tiết kiệm bộ nhớ hơn.

## 6. Duyệt văn bản và lập chỉ số kết quả

Đặt state=root. Với mỗi ký tự c của T ở index i:

```text
while state != root AND next[state][c] không tồn tại:
    state = fail[state]

if next[state][c] tồn tại:
    state = next[state][c]
else:
    state = root

endExclusive = i + 1

báo terminalIds[state]
đi hết outputLink chain và báo mỗi terminalIds
```

Nếu mẫu p có độ dài `len[p]`, ta in:

`start=endExclusive−len[p]`.

### 6.1. Bảng chạy cho `ushers`

| Index | Ký tự | State sau chuyển | Mẫu được báo |
|---:|---|---|---|
| 0 | u | root | Không |
| 1 | s | s | s: ID 8 |
| 2 | h | sh | Không |
| 3 | e | she | she:1, he:0, he:5, e:4 |
| 4 | r | her | Không |
| 5 | s | hers | hers:3, hers:9, ers:6, rs:7, s:8 |

Tổng 10 match. Mẫu ID2 `his` **không xuất hiện**.

Vị trí `endExclusive` là 2,4,6, không phải 1,3,5. Nếu đề đòi end **inclusive**, đổi riêng khi xuất: `endInclusive=endExclusive−1`.

### 6.2. Không reset state sau một match

Ví dụ `ana` xuất hiện hai lần trong `banana`: `[1,4)` và `[3,6)`, chúng **chồng lấn**. Nếu sau khi báo match thứ nhất mà nhảy thẳng về root, có thể làm mất match thứ hai. Thuật toán Aho–Corasick tiếp tục với state và failure links bình thường.

### 6.3. Không dùng số ID để suy độ dài

Một terminal node có thể có nhiều ID, và hai ID giống mẫu cùng độ dài. Luôn lưu `lengths[id]` từ mẫu gốc để tính chính xác start theo cùng đơn vị index.

## 7. Java 17 — Aho–Corasick với failure và output links

Mã sau là một chương trình chạy **độc lập**:

- Trie và next map dùng Unicode **code points**.
- Các mẫu trùng nội dung giữ **mọi ID**.
- Xây failure links và outputLink bằng BFS.
- Quét text và báo node hiện tại cùng mọi terminal suffix.
- Chỉ số kết quả dùng `[startCp,endCp)` theo **code point**.
- Mẫu rỗng bị từ chối; không có mẫu thì automaton chỉ có root.

Lưu thành **AhoCorasickOutputLinksDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class AhoCorasickOutputLinksDemo {
    static final class Node {
        final Map<Integer, Integer> next = new HashMap<>();
        final List<Integer> terminalIds = new ArrayList<>();
        int fail = 0;
        int outputLink = 0;
    }

    record Hit(int id, String pattern, int startCp, int endCp) {}

    static final class Automaton {
        final List<Node> nodes = new ArrayList<>();
        final String[] patterns;
        final int[] lengths;

        Automaton(String[] input) {
            patterns = input.clone();
            lengths = new int[patterns.length];
            nodes.add(new Node()); // Root ID 0.

            for (int id = 0; id < patterns.length; id++) {
                if (patterns[id] == null || patterns[id].isEmpty()) {
                    throw new IllegalArgumentException(
                            "Each pattern must be nonempty");
                }

                int[] codes = patterns[id].codePoints().toArray();
                lengths[id] = codes.length;
                int state = 0;
                for (int cp : codes) {
                    Integer child = nodes.get(state).next.get(cp);
                    if (child == null) {
                        child = nodes.size();
                        nodes.get(state).next.put(cp, child);
                        nodes.add(new Node());
                    }
                    state = child;
                }
                nodes.get(state).terminalIds.add(id);
            }
            buildLinks();
        }

        void buildLinks() {
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            for (int child : nodes.get(0).next.values()) {
                nodes.get(child).fail = 0;
                nodes.get(child).outputLink = 0;
                queue.addLast(child);
            }

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                for (Map.Entry<Integer, Integer> step
                        : nodes.get(u).next.entrySet()) {
                    int cp = step.getKey();
                    int child = step.getValue();

                    int f = nodes.get(u).fail;
                    while (f != 0
                            && !nodes.get(f).next.containsKey(cp)) {
                        f = nodes.get(f).fail;
                    }
                    int target = nodes.get(f).next.getOrDefault(cp, 0);
                    nodes.get(child).fail = target;

                    nodes.get(child).outputLink =
                            !nodes.get(target).terminalIds.isEmpty()
                            ? target : nodes.get(target).outputLink;
                    queue.addLast(child);
                }
            }
        }

        void emit(List<Hit> result, int node, int endCp) {
            for (int id : nodes.get(node).terminalIds) {
                result.add(new Hit(id, patterns[id],
                        endCp - lengths[id], endCp));
            }
        }

        List<Hit> scan(String text) {
            int[] chars = text.codePoints().toArray();
            List<Hit> result = new ArrayList<>();
            int state = 0;

            for (int i = 0; i < chars.length; i++) {
                int cp = chars[i];

                while (state != 0
                        && !nodes.get(state).next.containsKey(cp)) {
                    state = nodes.get(state).fail;
                }
                state = nodes.get(state).next.getOrDefault(cp, 0);

                int endCp = i + 1;
                emit(result, state, endCp);

                for (int suffix = nodes.get(state).outputLink;
                     suffix != 0;
                     suffix = nodes.get(suffix).outputLink) {
                    emit(result, suffix, endCp);
                }
            }
            return result;
        }
    }

    static void printHit(Hit h) {
        System.out.println("[" + h.startCp() + ","
                + h.endCp() + ") #" + h.id() + " " + h.pattern());
    }

    public static void main(String[] args) {
        String[] patterns = {
            "he", "she", "his", "hers", "e",
            "he", "ers", "rs", "s", "hers"
        };
        Automaton ac = new Automaton(patterns);
        String text = "ushers";
        List<Hit> hits = ac.scan(text);

        System.out.println("Text: " + text);
        System.out.println("Code-point length: "
                + text.codePointCount(0, text.length()));
        System.out.println("Matches: " + hits.size());
        for (Hit h : hits) printHit(h);

        String unicode = "a😀a";
        Automaton emoji = new Automaton(
                new String[]{"😀", "a😀", "😀a", "a"});
        System.out.println("Unicode code points: "
                + unicode.codePointCount(0, unicode.length()));
        System.out.println("Unicode UTF-16 units: " + unicode.length());
        for (Hit h : emoji.scan(unicode)) printHit(h);

        System.out.println("Empty text matches: "
                + ac.scan("").size());
        System.out.println("Zero patterns matches: "
                + new Automaton(new String[0]).scan("ushers").size());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 AhoCorasickOutputLinksDemo.java
java AhoCorasickOutputLinksDemo
```

Stdout:

```text
Text: ushers
Code-point length: 6
Matches: 10
[1,2) #8 s
[1,4) #1 she
[2,4) #0 he
[2,4) #5 he
[3,4) #4 e
[2,6) #3 hers
[2,6) #9 hers
[3,6) #6 ers
[4,6) #7 rs
[5,6) #8 s
Unicode code points: 3
Unicode UTF-16 units: 4
[0,1) #3 a
[0,2) #1 a😀
[1,2) #0 😀
[1,3) #2 😀a
[2,3) #3 a
Empty text matches: 0
Zero patterns matches: 0
```

### 7.1. Thứ tự output có bắt buộc như trên?

Không. Mã này báo **node hiện tại trước**, rồi các terminal suffix theo độ dài giảm dần. Tại một node terminal có nhiều ID trùng chuỗi, ID xuất theo **thứ tự mẫu được thêm**.

Nếu đề yêu cầu sort theo `start` hoặc `patternId`, hãy sort output sau khi tìm. Để **kiểm chứng tập sự kiện**, nên sort các tuple `(start,end,id)` để tránh nhầm khác biệt thứ tự trình bày với lỗi tính đúng.

### 7.2. Cách hiểu chỉ số Unicode

Trong Java, `"😀".length()==2` vì emoji dùng hai UTF-16 code units, nhưng `"😀".codePointCount(0,2)==1`.

Chương trình dùng `codePoints().toArray()`, nên:

`"a😀a"` có **3 code points** và **4 UTF-16 units**.

Vị trí `[startCp,endCp)` trong output là **code-point offsets**. Nếu dùng API `String.substring`, cần chuyển sang UTF-16 offsets bằng:

`text.offsetByCodePoints(0, codePointOffset)`.

Không truyền trực tiếp chỉ số code point vào substring vì có thể cắt đôi surrogate pair.

### 7.3. Vì sao từ chối mẫu rỗng?

Mẫu rỗng có thể được định nghĩa là khớp tại **mọi ranh giới** giữa ký tự, tức n+1 vị trí cho text n ký tự. Khi đó root phải được xử lý đặc biệt và cả mốc trước ký tự đầu phải được báo.

Các chương trình demo chọn hợp đồng **mẫu không rỗng** để root là sentinel, không phát match rỗng ngoài ý muốn.

### 7.4. Có cần chuẩn hóa Unicode?

Aho–Corasick so **chuỗi code point chính xác**. Hai chuỗi hiển thị giống nhau có thể khác cách biểu diễn Unicode (ký tự dấu dựng sẵn và tổ hợp base+combining mark). Nếu muốn so không phân biệt hoa/thường hoặc chuẩn hóa, cần biến đổi **cả patterns lẫn text** theo cùng quy tắc; nếu độ dài thay đổi, phải lưu ánh xạ vị trí để trả offset về text gốc.

## 8. Chứng minh outputLink báo đủ và không báo sai

### 8.1. Mọi match có terminal trên failure chain

Giả sử mẫu p kết thúc tại end của text. Khi đó p là hậu tố của đoạn text đã đọc và là đường từ root tới một terminal node trong trie.

State sau ký tự vừa đọc là **hậu tố dài nhất** của text đã đọc mà là tiền tố trie. Mọi mẫu p khớp ở end là một hậu tố của state đó. Những trie-prefix suffix như vậy xuất hiện trên chuỗi failure links từ state.

Vì vậy terminal node của p là **state hoặc một failure ancestor** của state.

### 8.2. OutputLink bỏ qua đúng những node không terminal

BFS đặt outputLink[v] tới **terminal gần nhất trên failure chain**, hoặc dùng outputLink[fail[v]] nếu fail[v] không terminal. Bằng quy nạp theo độ sâu, nó không bỏ sót terminal ancestor nào.

Duyệt state rồi các outputLink vì thế báo **mọi terminal node trên failure chain**, không cần duyệt các node không terminal.

### 8.3. Không có match giả

Mỗi ID được lưu đúng ở node biểu diễn nội dung mẫu ấy. Nếu node xuất hiện trên failure chain của state khi text kết thúc ở end, nội dung node là **hậu tố của text**, nên việc báo ID là hợp lệ.

### 8.4. Không báo lặp ID tại cùng end

Failure links luôn giảm độ sâu nên không có chu trình. Một terminal node được đi qua tối đa một lần trong chuỗi outputLink; mỗi ID được thêm **một lần vào node terminal của chính mẫu đó**.

Do vậy một ID không được báo hai lần ở cùng end. Hai ID có cùng nội dung vẫn xuất hiện thành **hai kết quả hợp lệ**.

## 9. Chi phí của trie, fail và output

Đặt:

- `n`: số code points của text.
- `L`: tổng độ dài code points của tất cả patterns, tính cả mẫu trùng.
- `S`: số node trie, luôn `S≤L+1`.
- `D`: độ dài mẫu lớn nhất.
- `z`: tổng số sự kiện match, kể cả nhiều ID tại cùng vị trí.

**Xây trie:** O(L) thời gian kỳ vọng và O(L) bộ nhớ với map transitions.

**Xây fail thưa theo mã demo:** mỗi cạnh trie có thể phải đi qua nhiều failure links, độ sâu tối đa D. Chặn an toàn đơn giản là **O(L·D) thời gian kỳ vọng**. Không mặc nhiên gọi cách cài `while` fallback thưa là O(L) worst-case.

Với bảng chữ cái cố định có σ ký tự, có thể xây automaton bằng **bảng transition đầy đủ** trong O(Sσ) thời gian và bộ nhớ; cách này bỏ việc đi fallback khi scan nhưng tốn O(Sσ) ô.

**Quét text:** khi đi cạnh trie, depth tăng tối đa1; khi đi fail, depth giảm ít nhất1. Tổng số bước fail trong cả quá trình quét là **O(n) amortized**. Mỗi outputLink dẫn đến node có ít nhất một ID báo. Với lookup HashMap kỳ vọng O(1):

**Thời gian scan có báo mọi match: O(n+z) kỳ vọng.**

Bộ nhớ cho automaton thưa: `O(L+k)` kể ID, nodes, failure links và output links; danh sách kết quả lưu toàn bộ cần thêm **O(z)**. Nếu output dùng callback/streaming, có thể tránh giữ z kết quả.

### 9.1. Vì sao không thể hứa O(n) nếu phải in mọi kết quả?

Với bộ mẫu `a, aa, aaa, ..., a` lặp k lần và text có n ký tự `a`, có thể phát sinh tới Θ(nk) sự kiện. Chỉ riêng việc in z sự kiện đòi Ω(z) thời gian.

Nếu chỉ cần **số lần xuất hiện** của mỗi mẫu, thay vì tất cả vị trí, có thể tránh phụ thuộc z bằng kỹ thuật ở phần kế tiếp.

### 9.2. Map hay bảng chữ cái nhỏ?

Với chữ thường Latin 26 ký tự, mảng `int[26]` cho chuyển trạng thái có thể rất nhanh và có độ phức tạp lookup worst-case O(1), nhưng dùng nhiều ô nếu trie lớn.

Với Unicode rộng, `Map<Integer,Integer>` thưa phù hợp và tránh giả định chỉ có `a..z`; tuy nhiên lookup HashMap là **O(1) trung bình/kỳ vọng**, không phải cam kết worst-case cố định.

## 10. Chỉ đếm số match: truyền ngược trên failure tree

Nếu đề chỉ cần `count[id]` — số lần xuất hiện của từng mẫu — không cần báo từng đoạn `[start,end)`.

Ý tưởng:

1. Mỗi mẫu id lưu `terminalNode[id]` là node cuối trong trie.
2. Khi scan mỗi ký tự text xong, tăng `visits[state]++`.
3. Sau scan, xét mọi node v khác root **theo thứ tự ngược BFS** và cộng:

   `visits[fail[v]] += visits[v]`.

4. Trả `count[id] = visits[terminalNode[id]]`.

### 10.1. Chứng minh công thức

Tại một điểm kết thúc end, mọi mẫu khớp có terminal node nằm trên chuỗi fail của state hiện tại. Nếu tăng `visits[state]++`, ta đã ghi nhận **một lần trạng thái hiện tại xuất hiện**.

Truyền visits từ state sang fail[state], rồi sang fail tiếp theo, tương đương cộng một đơn vị vào **mọi suffix state** trên failure chain. Sau khi truyền hết, giá trị visits tại terminal node của mẫu chính là số vị trí kết thúc mẫu đó khớp.

Phải duyệt **ngược BFS** vì failure links từ node sâu sang node nông: node nông chỉ nên truyền tổng visits của nó sau khi đã nhận đủ mọi đóng góp từ các node sâu.

### 10.2. Duplicate ID và suffix match

ID0=`he`, ID5=`he` cùng terminal node, nên count của chúng bằng nhau. Nhưng vẫn có **hai phần tử kết quả**.

Với `ushers`, counts theo ID là:

`[1, 1, 0, 1, 1, 1, 1, 1, 2, 1]`.

Mẫu `his` không xuất hiện ⇒ count0. Mẫu `s` xuất hiện ở `[1,2)` và `[5,6)` ⇒ count2.

### 10.3. Độ phức tạp đếm

Sau tiền xử lý failure links, scan tốn O(n) kỳ vọng. Reverse BFS tốn O(S); đọc k terminal nodes tốn O(k). Tổng:

**O(n+S+k) kỳ vọng**, **không phụ thuộc z**.

Kỹ thuật này phù hợp khi output quá lớn nhưng ta chỉ cần thống kê theo pattern ID.

## 11. Java 17 — đếm occurrences bằng reverse failure propagation

Chương trình sau là **độc lập**, không cần outputLink. Nó lưu `terminalNode[]` và BFS order của trie.

Lưu thành **AhoCorasickFailureCountDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class AhoCorasickFailureCountDemo {
    static final class Node {
        final Map<Integer, Integer> next = new HashMap<>();
        int fail = 0;
    }

    static final class Counter {
        final List<Node> nodes = new ArrayList<>();
        final List<Integer> bfsOrder = new ArrayList<>();
        final int[] terminalNode;

        Counter(String[] patterns) {
            nodes.add(new Node());
            terminalNode = new int[patterns.length];

            for (int id = 0; id < patterns.length; id++) {
                String pattern = patterns[id];
                if (pattern == null || pattern.isEmpty()) {
                    throw new IllegalArgumentException("Empty pattern");
                }

                int state = 0;
                for (int cp : pattern.codePoints().toArray()) {
                    Integer child = nodes.get(state).next.get(cp);
                    if (child == null) {
                        child = nodes.size();
                        nodes.get(state).next.put(cp, child);
                        nodes.add(new Node());
                    }
                    state = child;
                }
                terminalNode[id] = state;
            }
            buildFailureTree();
        }

        void buildFailureTree() {
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            bfsOrder.add(0);

            for (int child : nodes.get(0).next.values()) {
                nodes.get(child).fail = 0;
                queue.addLast(child);
            }

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                bfsOrder.add(u);

                for (Map.Entry<Integer, Integer> step
                        : nodes.get(u).next.entrySet()) {
                    int cp = step.getKey();
                    int child = step.getValue();

                    int f = nodes.get(u).fail;
                    while (f != 0
                            && !nodes.get(f).next.containsKey(cp)) {
                        f = nodes.get(f).fail;
                    }
                    nodes.get(child).fail =
                            nodes.get(f).next.getOrDefault(cp, 0);
                    queue.addLast(child);
                }
            }
        }

        long[] count(String text) {
            long[] visits = new long[nodes.size()];
            int state = 0;

            for (int cp : text.codePoints().toArray()) {
                while (state != 0
                        && !nodes.get(state).next.containsKey(cp)) {
                    state = nodes.get(state).fail;
                }
                state = nodes.get(state).next.getOrDefault(cp, 0);
                visits[state]++;
            }

            for (int i = bfsOrder.size() - 1; i >= 1; i--) {
                int u = bfsOrder.get(i);
                visits[nodes.get(u).fail] += visits[u];
            }

            long[] counts = new long[terminalNode.length];
            for (int id = 0; id < counts.length; id++) {
                counts[id] = visits[terminalNode[id]];
            }
            return counts;
        }
    }

    public static void main(String[] args) {
        String[] patterns = {
            "he", "she", "his", "hers", "e",
            "he", "ers", "rs", "s", "hers"
        };
        Counter ac = new Counter(patterns);

        long[] counts = ac.count("ushers");
        System.out.println("Counts in ushers: "
                + Arrays.toString(counts));
        System.out.println("Total matches in ushers: "
                + Arrays.stream(counts).sum());
        System.out.println("Empty text counts: "
                + Arrays.toString(ac.count("")));

        Counter overlap = new Counter(
                new String[]{"a", "aa", "aaa", "aaaa", "aaaaa"});
        System.out.println("Overlapping counts in aaaaa: "
                + Arrays.toString(overlap.count("aaaaa")));

        Counter emoji = new Counter(
                new String[]{"😀", "a😀", "😀a", "a"});
        System.out.println("Unicode counts in a😀a: "
                + Arrays.toString(emoji.count("a😀a")));

        System.out.println("No patterns counts: "
                + Arrays.toString(new Counter(new String[0])
                        .count("anything")));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 AhoCorasickFailureCountDemo.java
java AhoCorasickFailureCountDemo
```

Stdout:

```text
Counts in ushers: [1, 1, 0, 1, 1, 1, 1, 1, 2, 1]
Total matches in ushers: 10
Empty text counts: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
Overlapping counts in aaaaa: [5, 4, 3, 2, 1]
Unicode counts in a😀a: [1, 1, 1, 2]
No patterns counts: []
```

### 11.1. Vì sao có reverse BFS?

Nếu truyền từ root xuống, node `"s"` có thể được xử lý **trước** node `"hers"` gửi phần đóng góp theo chain `hers→ers→rs→s`, khiến count của `"s"` bị thiếu. Reverse BFS bảo đảm trạng thái sâu truyền trước khi trạng thái nông được chốt.

### 11.2. Nếu chỉ cần số lượng, không cần lưu danh sách Hit

Trong scanner liệt kê, `List<Hit>` có thể lớn tới z. Với Counter, ngoài automaton và input text, chỉ cần `visits[S]` và `counts[k]`, nên không cần tạo mọi kết quả. Với dữ liệu nhiều match lồng nhau, khác biệt bộ nhớ và tốc độ rất đáng kể.

## 12. Java 17 — oracle vét cạn để kiểm mọi match

Để kiểm lỗi bỏ sót output, một oracle đơn giản **không dùng trie hay fail** là so từng mẫu trực tiếp với mọi đoạn text có thể kết thúc ở end.

Ta so kết quả Aho–Corasick với brute force theo tuple `(start,end,id)` sau khi sort; không chuyển sang `Set` vì có thể che giấu một sự kiện bị báo lặp.

Chương trình dưới còn có một biến thể Aho–Corasick **sao chép outputs của fail node** thay vì dùng outputLink. Cách này dễ kiểm bằng brute nhưng có thể tốn thêm bộ nhớ với dictionary lớn.

Lưu thành **AhoCorasickBruteCrossCheckDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;

public class AhoCorasickBruteCrossCheckDemo {
    record Hit(int start, int end, int id) {}

    static final class Node {
        final Map<Integer, Integer> next = new HashMap<>();
        final List<Integer> outputs = new ArrayList<>();
        int fail = 0;
    }

    static final class Aho {
        final List<Node> nodes = new ArrayList<>();
        final int[] lengths;

        Aho(String[] patterns) {
            nodes.add(new Node());
            lengths = new int[patterns.length];

            for (int id = 0; id < patterns.length; id++) {
                if (patterns[id] == null || patterns[id].isEmpty()) {
                    throw new IllegalArgumentException("Empty pattern");
                }

                int[] codes = patterns[id].codePoints().toArray();
                lengths[id] = codes.length;
                int state = 0;
                for (int cp : codes) {
                    Integer child = nodes.get(state).next.get(cp);
                    if (child == null) {
                        child = nodes.size();
                        nodes.get(state).next.put(cp, child);
                        nodes.add(new Node());
                    }
                    state = child;
                }
                nodes.get(state).outputs.add(id);
            }

            ArrayDeque<Integer> queue = new ArrayDeque<>();
            for (int child : nodes.get(0).next.values()) {
                nodes.get(child).fail = 0;
                queue.addLast(child);
            }

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                for (Map.Entry<Integer, Integer> step
                        : nodes.get(u).next.entrySet()) {
                    int cp = step.getKey();
                    int child = step.getValue();
                    int f = nodes.get(u).fail;

                    while (f != 0
                            && !nodes.get(f).next.containsKey(cp)) {
                        f = nodes.get(f).fail;
                    }
                    int fallback =
                            nodes.get(f).next.getOrDefault(cp, 0);
                    nodes.get(child).fail = fallback;
                    nodes.get(child).outputs.addAll(
                            nodes.get(fallback).outputs);
                    queue.addLast(child);
                }
            }
        }

        List<Hit> scan(String text) {
            List<Hit> found = new ArrayList<>();
            int state = 0;
            int[] codes = text.codePoints().toArray();

            for (int i = 0; i < codes.length; i++) {
                int cp = codes[i];
                while (state != 0
                        && !nodes.get(state).next.containsKey(cp)) {
                    state = nodes.get(state).fail;
                }
                state = nodes.get(state).next.getOrDefault(cp, 0);

                int end = i + 1;
                for (int id : nodes.get(state).outputs) {
                    found.add(new Hit(end - lengths[id], end, id));
                }
            }
            return found;
        }
    }

    static List<Hit> brute(String[] patterns, String text) {
        int[] codes = text.codePoints().toArray();
        int[][] pats = new int[patterns.length][];
        for (int id = 0; id < patterns.length; id++) {
            pats[id] = patterns[id].codePoints().toArray();
        }

        List<Hit> matches = new ArrayList<>();
        for (int end = 1; end <= codes.length; end++) {
            for (int id = 0; id < pats.length; id++) {
                int[] p = pats[id];
                if (p.length > end) continue;

                boolean equal = true;
                for (int j = 0; j < p.length; j++) {
                    if (codes[end - p.length + j] != p[j]) {
                        equal = false;
                        break;
                    }
                }
                if (equal) {
                    matches.add(new Hit(end - p.length, end, id));
                }
            }
        }
        return matches;
    }

    static List<Hit> normalized(List<Hit> matches) {
        List<Hit> result = new ArrayList<>(matches);
        result.sort(Comparator.comparingInt(Hit::end)
                .thenComparingInt(Hit::start)
                .thenComparingInt(Hit::id));
        return result;
    }

    static void check(String[] patterns, String text) {
        List<Hit> expected = normalized(brute(patterns, text));
        List<Hit> actual = normalized(new Aho(patterns).scan(text));
        if (!expected.equals(actual)) {
            throw new IllegalStateException(
                    "Mismatch for text=" + text
                    + " expected=" + expected
                    + " actual=" + actual);
        }
    }

    static String randomWord(Random rng, int length) {
        StringBuilder s = new StringBuilder();
        for (int i = 0; i < length; i++) {
            s.append((char) ('a' + rng.nextInt(3)));
        }
        return s.toString();
    }

    public static void main(String[] args) {
        String[] patterns = {
            "he", "she", "his", "hers", "e",
            "he", "ers", "rs", "s", "hers"
        };
        check(patterns, "ushers");
        System.out.println("Sample matches: "
                + new Aho(patterns).scan("ushers").size());

        String[] emoji = {"😀", "a😀", "😀a", "a"};
        check(emoji, "a😀a");
        System.out.println("Unicode matches: "
                + new Aho(emoji).scan("a😀a").size());

        Random rng = new Random(3742026L);
        int cases = 2000;

        for (int tc = 0; tc < cases; tc++) {
            int k = rng.nextInt(7);
            String[] pats = new String[k];

            for (int id = 0; id < k; id++) {
                if (id > 0 && rng.nextInt(4) == 0) {
                    pats[id] = pats[rng.nextInt(id)];
                } else {
                    pats[id] = randomWord(rng, 1 + rng.nextInt(4));
                }
            }

            String text = randomWord(rng, rng.nextInt(16));
            check(pats, text);
        }

        System.out.println("Random cases checked: " + cases);
        System.out.println("All matches equal brute force: true");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 AhoCorasickBruteCrossCheckDemo.java
java AhoCorasickBruteCrossCheckDemo
```

Stdout:

```text
Sample matches: 10
Unicode matches: 5
Random cases checked: 2000
All matches equal brute force: true
```

### 12.1. Vì sao cần so cả vị trí và ID?

So duy nhất số match có thể che giấu lỗi “thiếu một kết quả, thừa một kết quả”. Oracle phải so **từng tuple `(start,end,id)`**. Sort để không ép thứ tự phát của trie giống thứ tự duyệt ID trong brute force.

### 12.2. Vì sao random có seed cố định?

`Random(3742026L)` khiến cùng bộ test được sinh lại mỗi lần chạy, giúp tái hiện lỗi. Alphabet `a,b,c` tạo nhiều prefix, suffix chung và các match chồng lấn. Cách sinh cố tình có thể tạo **hai ID có cùng pattern**.

## 13. Streaming và Unicode

Aho–Corasick có thể quét theo stream mà không giữ toàn bộ văn bản, miễn automaton đã được xây.

Giữ `state` và `processedCodePoints` giữa các chunk:

1. Nhận một code point c.
2. Chuyển state bằng trie/fail.
3. Tăng `processedCodePoints`.
4. Emit mọi terminal ở state/outputLink.
5. Match của ID p có `end=processedCodePoints`, `start=end−lengths[p]`.

**Không reset state khi sang chunk mới.** Mẫu có thể bắt đầu ở cuối chunk trước và kết thúc ở đầu chunk sau.

### 13.1. Chunk có thể cắt đôi surrogate pair

Trong Java, emoji như 😀 là **hai UTF-16 code units**. Nếu stream được chia thành `String` chunks tùy ý, high surrogate có thể nằm cuối chunk1 và low surrogate ở đầu chunk2. Gọi `codePoints()` trên mỗi chunk riêng sẽ không tự ghép lại cặp ở hai phía ranh giới.

Phải giữ **một high surrogate đang chờ** hoặc dùng bộ giải mã có trạng thái, đảm bảo cung cấp các code points hợp lệ cho automaton. Cùng nguyên tắc áp dụng khi đọc UTF-8 byte stream có code point bị chia giữa các block.

### 13.2. Chuẩn hóa text và pattern nhất quán

Nếu dùng NFC hoặc lowercase/casefold, phải áp cùng quy tắc cho cả text và patterns. Nếu biến đổi làm thay đổi độ dài, vị trí trên chuỗi đã chuẩn hóa không còn trùng với offset trong text gốc; muốn in offset gốc, cần lưu **ánh xạ chỉ số**. Các chương trình ở đây dùng so khớp chính xác code points đã có.

## 14. Lỗi thường gặp và cách khắc phục

### Lỗi 1 — Chỉ lưu cờ terminal

`terminal=true` không biểu diễn được hai ID `he` riêng biệt. Dùng `List<Integer> terminalIds`.

### Lỗi 2 — Chỉ báo node state hiện tại

Bỏ mẫu là hậu tố của mẫu dài hơn: sau `she`, phải báo cả `he` và `e`. Dùng outputLink hoặc merged outputs.

### Lỗi 3 — Chỉ báo fail trực tiếp một lần

Sau `hers` còn `ers`, `rs`, `s`, không thể chỉ kiểm `fail[hers]` rồi dừng.

### Lỗi 4 — Nhầm failure link là một node terminal

Fail có thể trỏ node không terminal; outputLink được thiết kế để bỏ qua các node ấy khi phát kết quả.

### Lỗi 5 — Xây fail bằng DFS tùy ý

Node sâu có thể cần fail của node nông chưa tính. Xây bằng BFS theo độ sâu hoặc một thứ tự bảo đảm phụ thuộc.

### Lỗi 6 — Sai khái niệm suffix

Fail là **proper suffix** đồng thời là trie prefix, không phải suffix bất kỳ của chuỗi.

### Lỗi 7 — Root fail gây vòng lặp

Đặt `fail[root]=root` nhưng vòng fallback phải dừng ở root; không chạy `while` vô hạn nếu root không có transition.

### Lỗi 8 — OutputLink trỏ về chính nó

OutputLink phải tới terminal failure ancestor **nông hơn**, hoặc root sentinel; nếu trỏ chính nó, vòng emit vô hạn.

### Lỗi 9 — Reset state sau match

Có thể bỏ các match chồng lấn như `ana` trong `banana`. Không tự reset state sau emit.

### Lỗi 10 — Mismatch thì quay root ngay

Đường dự phòng có thể tiếp tục: từ `she` đọc `r` phải đi qua `he` tới `her`.

### Lỗi 11 — Quên báo sau mỗi ký tự

Nếu chỉ kiểm terminal cuối toàn bộ text, mất những match kết thúc trước đó.

### Lỗi 12 — Deduplicate mẫu khi đề cần output theo ID

Hai mẫu `he` ở ID0,ID5 là **hai kết quả** khi cùng xuất hiện. Không tự gộp.

### Lỗi 13 — Dùng `.length()` khi output index theo code point

Một emoji dài2 Java char nhưng1 code point. Tính mẫu length bằng `codePoints()` để offset nhất quán.

### Lỗi 14 — Nhầm endInclusive với endExclusive

Ở text `ushers`, `she` là `[1,4)`, endExclusive4; không in `[1,3)`.

### Lỗi 15 — Chấp nhận empty pattern mà không có định nghĩa

Một mẫu rỗng có thể match tại n+1 ranh giới. Các ví dụ này **reject empty pattern** cho nhất quán.

### Lỗi 16 — Không xử lý k=0

Không có pattern thì scanner chỉ còn root và kết quả phải rỗng.

### Lỗi 17 — Không xử lý text rỗng

Với mẫu không rỗng, text rỗng có 0 match và mảng counts toàn0.

### Lỗi 18 — Đếm chỉ các lần state trực tiếp terminal

Nếu state dài hơn và mẫu là suffix, cần truyền visits qua fail chain để đếm đủ.

### Lỗi 19 — Truyền counts theo BFS xuôi

Node nông truyền trước khi nhận hết đóng góp từ node sâu, nên mất số liệu. Dùng **reverse BFS**.

### Lỗi 20 — Hứa O(n) khi phải in z kết quả

Chi phí đúng là O(n+z) kỳ vọng trong scan với outputLink.

### Lỗi 21 — Hứa sparse build fail luôn O(L) worst-case

Cách dùng `while` fallback có thể thử nhiều failure ancestors cho mỗi trie edge; chặn đơn giản O(L·D) kỳ vọng.

### Lỗi 22 — Copy outputs ở mọi node mà không tính bộ nhớ

Có thể nhân bản nhiều ID trong nhiều suffix states. OutputLink tiết kiệm hơn cho dictionary lớn.

### Lỗi 23 — Trộn các chỉ số byte, char, code point

Đầu vào UTF-8, Java UTF-16 và logical Unicode code point có đơn vị khác nhau. Chọn một hợp đồng offset và chuyển đúng.

### Lỗi 24 — Không giữ state giữa stream chunks

Mất mẫu vượt qua ranh giới chunk. Giữ state và số code points tổng cộng.

### Lỗi 25 — Không xử lý surrogate bị cắt đôi

Decode Unicode theo stream, không coi từng nửa surrogate như hai code points độc lập.

### Lỗi 26 — Thêm mẫu sau build mà không cập nhật fail

New prefix/suffix làm failure links cũ không còn đủ. Rebuild automaton hoặc dùng giải pháp dynamic.

### Lỗi 27 — Oracle so kết quả qua Set

Set có thể che giấu lỗi báo trùng. Sort List sự kiện, so cả ID, start,end và số lần.

### Lỗi 28 — Bỏ qua thứ tự input mẫu

Nếu output yêu cầu ID, cách lưu `terminalIds` phải giữ ID gốc ngay cả khi có chuỗi trùng.

## 15. Kiểm thử các trường hợp biên

| Case | Kỳ vọng |
|---|---|
| Không có mẫu | 0 sự kiện; counts là mảng rỗng |
| Text rỗng | 0 sự kiện với mẫu không rỗng |
| Mẫu dài hơn text | 0 sự kiện |
| Mẫu trùng nội dung khác ID | Mỗi ID tạo sự kiện riêng |
| Mẫu là suffix của mẫu khác | Báo tất cả tại cùng end |
| Chuỗi fail dài `hers→ers→rs→s` | Không bỏ sót terminal suffix |
| Text có ký tự ngoài trie | Fallback root an toàn |
| Mismatch nhưng suffix còn transition | Đi fail rồi transition, không reset vô điều kiện |
| Match chồng lấn | Giữ mọi sự kiện |
| Text `"aaaa"` với mẫu a,aa,aaa | Counts `[4,3,2]` |
| Emoji `"a😀a"` | Index theo 3 code points, không 4 |
| Duplicate `"hers"` | Hai ID cùng `[2,6)` |
| Cần counts chứ không cần vị trí | Dùng reverse failure propagation |
| Kết quả rất lớn | Stream/callback thay vì giữ `List<Hit>` |
| Text chunk cắt giữa match | Giữ state qua chunk |
| Text chunk cắt giữa surrogate | Giải mã code points trước scan |

### 15.1. Mẫu chồng lấn

Với `T="banana"`, mẫu `ana` xuất hiện `[1,4)` và `[3,6)`. Hai lần chia sẻ ký tự ở index3; không được dùng logic “phát hiện một match rồi nhảy tới sau match”.

### 15.2. Các mẫu lồng nhau

Với mẫu `a`, `aa`, `aaa` và text `aaaa`, một ranh giới end có thể kết thúc **ba mẫu**. Đây là ví dụ ngắn để bắt lỗi chỉ báo terminal hiện tại.

## 16. Bài tập có đáp án

### Bài 1 — Định nghĩa fail

Với node `"she"` và trie có `"he"`, fail của `"she"`?

**Đáp án:** `"he"`.

### Bài 2 — Failure chain

Bộ mẫu chứa `hers`, `ers`, `rs`, `s`. Chuỗi fail?

**Đáp án:** `hers→ers→rs→s→root`.

### Bài 3 — Cùng end4

`ushers` có bao nhiêu match tại endExclusive4 với mẫu đã cho?

**Đáp án:** 4 sự kiện theo IDs 1,0,5,4.

### Bài 4 — Cùng end6

Có bao nhiêu match tại endExclusive6?

**Đáp án:** 5 sự kiện theo IDs 3,9,6,7,8.

### Bài 5 — Tổng match

Cả văn bản `ushers` có bao nhiêu sự kiện theo ID?

**Đáp án:** 10.

### Bài 6 — Có cần báo suffix?

Tại state `she`, nếu chỉ in ID1 có đầy đủ không?

**Đáp án:** không; còn IDs0,5 của `he` và ID4 của `e`.

### Bài 7 — Một boolean terminal?

Hai mẫu giống nhau nhưng khác ID, boolean terminal có đủ để báo từng ID?

**Đáp án:** không. Cần danh sách terminal IDs.

### Bài 8 — OutputLink là gì?

**Đáp án:** node terminal gần nhất trên chuỗi fail sau node hiện tại, hoặc root sentinel.

### Bài 9 — Tại sao fail giảm depth?

**Đáp án:** fail biểu diễn **proper suffix**, ngắn hơn label(node).

### Bài 10 — `she` rồi `r`

Khi state `she` thiếu cạnh r nhưng fail `he` có cạnh r, đi tới đâu?

**Đáp án:** state `her`.

### Bài 11 — Tính start

Mẫu `she` dài3 tại end4 có start bằng?

**Đáp án:** 1.

### Bài 12 — Mẫu `e` ở end4

Start?

**Đáp án:** 3.

### Bài 13 — Count của s

`"s"` xuất hiện bao nhiêu lần trong `ushers`?

**Đáp án:** 2.

### Bài 14 — Mẫu không xuất hiện

Count của `his`?

**Đáp án:** 0.

### Bài 15 — Duplicate he

ID0 và ID5 có counts ra sao?

**Đáp án:** cùng bằng1 nhưng ở hai vị trí mảng khác nhau.

### Bài 16 — Reverse BFS

Tại sao không truyền counts từ root xuống?

**Đáp án:** vì node nông có thể chưa nhận đóng góp từ các node sâu, làm đếm thiếu.

### Bài 17 — Độ phức tạp emit

Scan n ký tự, báo z sự kiện, có thể chỉ cần O(n) luôn không?

**Đáp án:** không. Cần ít nhất Ω(z) để phát z sự kiện; với outputLink là O(n+z) kỳ vọng.

### Bài 18 — Độ phức tạp counts

Sau khi có failure links, đếm tất cả mẫu bằng reverse propagation mất bao nhiêu?

**Đáp án:** O(n+S+k) kỳ vọng.

### Bài 19 — a,aa,aaa

Counts trong `aaaa`?

**Đáp án:** `[4,3,2]`.

### Bài 20 — Empty pattern

Code demo xử lý mẫu rỗng thế nào?

**Đáp án:** từ chối để tránh mơ hồ về n+1 ranh giới.

### Bài 21 — Emoji

`"a😀a"` có số UTF-16 units và Unicode code points?

**Đáp án:** 4 UTF-16 units và 3 code points.

### Bài 22 — String.substring

Có thể dùng code point start trực tiếp trong `substring`?

**Đáp án:** không; cần đổi sang UTF-16 offset bằng `offsetByCodePoints`.

### Bài 23 — Sao chép output

Nhược điểm sao chép outputs của failure parent?

**Đáp án:** có thể nhân bản nhiều ID trên nhiều node, tăng thời gian và bộ nhớ.

### Bài 24 — Stream chunk

Mẫu bắt đầu ở chunk1, kết thúc ở chunk2. Có reset state?

**Đáp án:** không; giữ state và processed code-point offset xuyên chunk.

### Bài 25 — Cập nhật dictionary

Thêm mẫu mới sau build fail có cần build lại?

**Đáp án:** thông thường có, vì cấu trúc suffix/prefix mới thay đổi failure links và output links.

## 17. Checklist cuối bài

1. Đã thống nhất mỗi mẫu có ID riêng, kể cả duplicate strings?
2. Đã chọn đơn vị chỉ số byte, char hay code point?
3. Các mẫu rỗng có bị từ chối hoặc có quy ước riêng?
4. Trie chứa mọi mẫu trước khi xây failure links?
5. Root và các con root có fail đúng?
6. Các liên kết fail được tính BFS theo độ sâu?
7. Fail là proper suffix dài nhất còn thuộc trie prefix?
8. Khi mismatch, có lần theo fail thay vì reset vội về root?
9. Sau mỗi ký tự, có báo terminal IDs tại state?
10. Có báo mọi terminal suffix theo outputLink?
11. OutputLink có bảo đảm tiến về node nông hơn?
12. Có lưu nhiều ID ở cùng terminal node?
13. Có giữ các match chồng lấn?
14. Có tính `[start,end)` theo cùng đơn vị index với độ dài mẫu?
15. Có kiểm ví dụ `she→he→e` và `hers→ers→rs→s`?
16. Có kiểm ID của hai mẫu trùng `he` và hai mẫu trùng `hers`?
17. Có kiểm trường hợp text rỗng và dictionary rỗng?
18. Nếu chỉ cần counts, có reverse failure propagation?
19. Có phân biệt O(n+z) với O(n+S+k)?
20. Có tính được chi phí xây fail theo cấu trúc transition đã dùng?
21. Có thử Unicode emoji và offset code point?
22. Có xử lý decoder khi stream chia đôi surrogate pair?
23. Có dùng seed cố định cho randomized oracle?
24. Oracle có so **mọi tuple** start, end, ID?
25. Không gộp kết quả bằng Set khiến mất số lần?
26. Nếu dictionary thay đổi, có cập nhật toàn bộ failure/output links?
27. Nếu z lớn, có chiến lược stream output hoặc chỉ đếm?
28. Nếu cần sort theo yêu cầu cụ thể, có xử lý thứ tự output?

**Ghi nhớ:** `fail[v]` dẫn tới **hậu tố thực sự dài nhất của node v cũng là tiền tố trong trie**. `outputLink[v]` dẫn tới **node terminal gần nhất trên failure chain**. Sau mỗi ký tự text, phát terminal của state hiện tại và **tất cả terminal suffix nodes** qua outputLink; vì thế nhiều mẫu có thể cùng kết thúc và mẫu trùng nội dung nhưng khác ID vẫn được báo đủ. Nếu chỉ cần số lần xuất hiện, ghi `visits[state]` trong lúc quét rồi **truyền ngược theo failure tree** để đếm hiệu quả.
