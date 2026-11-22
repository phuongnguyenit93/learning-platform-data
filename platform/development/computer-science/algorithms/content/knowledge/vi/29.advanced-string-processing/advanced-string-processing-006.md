# Máy tự động hậu tố (suffix automaton) và biểu diễn các chuỗi con

**Suffix Automaton** (thường viết **SAM**, còn gọi là *suffix automaton* hay *directed acyclic word graph* trong ngữ cảnh tìm chuỗi con) là cấu trúc dữ liệu gọn dùng để biểu diễn **toàn bộ các chuỗi con liên tiếp** (*substrings*) của **một chuỗi cố định**. Với chuỗi s dài n, có thể có tới `n(n+1)/2` chuỗi con **khác nhau theo vị trí bắt đầu/kết thúc**; nếu liệt kê trực tiếp từng chuỗi con thì chi phí rất lớn. SAM gom nhiều chuỗi con vào cùng **trạng thái tương đương**, vì chúng có cùng tập vị trí kết thúc trong s, và dùng các cạnh có nhãn ký tự để nhận diện một chuỗi con bằng đường đi từ gốc.

SAM đặc biệt hữu ích cho các bài toán **Xử lý chuỗi nâng cao** như: kiểm tra một chuỗi có phải substring của s, đếm số substring phân biệt, đếm số lần xuất hiện của một substring (kể cả chồng lấp), tìm substring xuất hiện lặp lại dài nhất, tìm **longest common substring** với chuỗi thứ hai, hoặc chọn substring thứ k theo thứ tự từ điển.

Bài học cung cấp **định nghĩa endpos**, ba trường hợp mở rộng SAM, lý do cần **clone state**, bảng ví dụ chính xác, công thức đếm chuỗi con, xử lý tần suất và thứ tự từ điển, chứng minh và độ phức tạp. Phần Java 17+ xây SAM theo **Unicode code point** và có bộ kiểm thử độc lập trên **500 trường hợp Unicode ngẫu nhiên**.

**Mục tiêu quan trọng nhất:** Một **trạng thái SAM không đồng nghĩa với một substring duy nhất**. Một trạng thái đại diện cho **nhiều substring có độ dài khác nhau nhưng chung tập vị trí kết thúc**. Một substring cụ thể được nhận diện bằng **đường đi có nhãn từ root**; đường đó có thể kết thúc tại trạng thái chia sẻ với các substring khác.

## 1. Thuật ngữ: substring, suffix, subsequence

Cho chuỗi `s="banana"`:

- **Substring (chuỗi con liên tiếp)** là một đoạn các ký tự liền nhau: "ana", "ban", "nan", "banana" là substring.
- **Suffix (hậu tố)** là substring kết thúc tại cuối chuỗi: "a", "na", "ana", "nana", "anana", "banana" và chuỗi rỗng.
- **Prefix (tiền tố)** là substring bắt đầu ở đầu chuỗi: "b", "ba", "ban", "bana", "banan", "banana" và chuỗi rỗng.
- **Subsequence (dãy con không nhất thiết liên tiếp)** được phép bỏ qua ký tự giữa. Ví dụ "bnn" có thể là subsequence của "banana", nhưng không phải substring.

SAM trong bài này nhận diện **substring liên tiếp**, không giải trực tiếp bài longest common subsequence.

Nếu đánh chỉ số từ 0 và dùng khoảng nửa mở `[l,r)`, substring s[l..r) gồm các ký tự ở vị trí l,l+1,...,r−1. Với 0≤l<r≤n, có `n(n+1)/2` cặp (l,r) không rỗng, nhưng **nhiều cặp có thể cho cùng một nội dung substring**. Ví dụ chuỗi "aaaa" có 10 đoạn không rỗng theo vị trí, nhưng chỉ 4 chuỗi con **phân biệt theo nội dung**: "a","aa","aaa","aaaa".

**Hai mục tiêu cần tách:** Đếm **số substring phân biệt** là đếm nội dung; đếm **số lần xuất hiện** là đếm vị trí của một nội dung. SAM hỗ trợ cả hai, với hai loại thông tin khác nhau.

## 2. endpos: quan hệ tương đương cốt lõi

Với substring không rỗng x của s, định nghĩa:

```text
endpos(x) =
  tập tất cả chỉ số i sao cho
  s[i-|x|+1 ... i] = x
```

Chỉ số ở đây là **vị trí kết thúc inclusive** (từ 0). Cùng một x có thể có nhiều vị trí kết thúc nếu x xuất hiện nhiều lần.

Ví dụ s="ababa", vị trí:

```text
0 1 2 3 4
a b a b a
```

Ta có:

```text
endpos("a")   = {0,2,4}
endpos("b")   = {1,3}
endpos("ab")  = {1,3}
endpos("ba")  = {2,4}
endpos("aba") = {2,4}
endpos("bab") = {3}
```

Hai substring không rỗng được coi là **tương đương endpos** khi có cùng tập vị trí kết thúc:

```text
x ~ y  <=>  endpos(x) = endpos(y)
```

Trong ví dụ:

- "b" và "ab" cùng endpos={1,3}; chúng nằm trong **một lớp**.
- "ba" và "aba" cùng endpos={2,4}; chúng nằm trong **một lớp khác**.
- "a" có endpos={0,2,4}; lớp của nó khác hai lớp trên.

**SAM có một trạng thái cho mỗi lớp tương đương endpos của các substring không rỗng, cộng với root cho chuỗi rỗng.** Nhờ vậy số trạng thái chỉ O(n), dù số substring phân biệt có thể Θ(n²).

### 2.1. Vì sao các substring cùng lớp endpos có độ dài tạo một khoảng liên tục?

Xét hai substring x,y cùng endpos và `|x|<|y|`. Vì chúng cùng kết thúc ở cùng các vị trí, x phải là một **hậu tố** của y. Mọi hậu tố z của y có độ dài nằm giữa |x| và |y| cũng có cùng endpos: mọi lần xuất hiện của y cho một lần xuất hiện của z, và mọi lần xuất hiện của z kết thúc ở vị trí thuộc endpos(x) sẽ có cùng ngữ cảnh dài hơn trong lớp.

Kết quả: Các substring do một trạng thái v đại diện có độ dài là **mọi số nguyên trong một khoảng liên tục**:

```text
minLen(v) = len(link(v)) + 1
maxLen(v) = len(v)

Lengths(v) =
  {minLen(v), minLen(v)+1, ..., len(v)}
```

Trong đó `len(v)` là độ dài substring **dài nhất** trong lớp, và `link(v)` là trạng thái của lớp chứa hậu tố thích hợp dài nhất **nằm ngoài** lớp v.

Đây là lý do công thức đếm substring phân biệt trở nên đơn giản: một trạng thái v≠root đóng góp đúng `len(v)-len(link(v))` nội dung substring.

### 2.2. Bất biến của suffix link

Với mọi v≠root:

```text
0 <= len(link(v)) < len(v)
```

Đi theo suffix links luôn **giảm độ dài**, nên cấu trúc suffix links tạo thành một cây có gốc tại root (nếu xem mỗi trạng thái có một cạnh nối tới link). Các cạnh suffix link **khác** cạnh transition theo ký tự: loại thứ nhất phục vụ hậu tố/lớp endpos, loại thứ hai phục vụ nhận diện substring bằng cách đọc ký tự.

## 3. Mỗi trạng thái và các cạnh lưu gì?

Một cài đặt SAM thông dụng dùng các trường:

| Trường | Ý nghĩa |
| --- | --- |
| `next[c]` | Trạng thái tiếp theo nếu nối thêm ký tự/code point c |
| `len` | Độ dài lớn nhất của substring trong lớp |
| `link` | Trạng thái chứa hậu tố thích hợp dài nhất ngoài lớp |
| `firstPos` | Một vị trí kết thúc của substring dài nhất thuộc trạng thái |
| `occ` | Số lần xuất hiện, sau khi lan truyền qua suffix links |
| `clone` | Đánh dấu trạng thái sao chép khi phải tách lớp |

Root có ID0, `len=0` và `link=-1`. Với mã mẫu, vị trí lưu theo Unicode code point, không phải byte hay UTF-16 char.

### 3.1. Transition có nghĩa gì?

Nếu từ root đi theo dãy ký tự x và tất cả transition tồn tại, x là một substring của s. Đường đi được xác định duy nhất bởi các ký tự vì mỗi trạng thái có **tối đa một transition cho một ký tự cụ thể**.

Ví dụ trên SAM("ababa"):

```text
root --a--> ... --b--> ... --a--> ...
```

đường đọc "aba" tồn tại vì "aba" là substring. Nhưng "aa" không xuất hiện trong "ababa", nên một trong các transition khi đọc "aa" không tồn tại.

**Không phải mọi đường đi từ root đều tương ứng một trạng thái khác nhau.** Hai chuỗi nhãn khác nhau có thể kết thúc ở **cùng state** và có cùng endpos, ví dụ "b" và "ab" trong "ababa". Vì vậy không được lấy **số trạng thái trừ 1** làm số substring phân biệt.

### 3.2. Transition graph không có chu trình

Khi đi một cạnh có nhãn ký tự từ trạng thái u sang v, ta nối thêm một ký tự vào substring đã đọc. Trong SAM chuẩn, `len(v)>len(u)` cho transition như vậy. Do đó transition graph là **đồ thị có hướng không chu trình (DAG)** theo thứ tự độ dài, dù nó không nhất thiết là một cây.

Hệ quả:

- Có thể đếm các đường đi bằng quy hoạch động trên DAG.
- Có thể tìm substring thứ k theo thứ tự từ điển bằng số lượng đường đi tiếp sau mỗi cạnh.
- Có thể xử lý trạng thái theo `len` tăng hoặc giảm bằng counting sort.

### 3.3. firstPos khác “vị trí xuất hiện đầu tiên theo thời gian”

Một trạng thái v có thể lưu `firstPos` của một lần kết thúc mà ta đã có khi xây automaton. Đó là **một đại diện hợp lệ**, không bắt buộc là **vị trí sớm nhất trong text**.

Muốn khôi phục substring dài nhất của v từ s:

```text
start = firstPos[v] - len[v] + 1
endExclusive = firstPos[v] + 1
```

với các chỉ số tính cùng đơn vị code point. Khi clone q, sao chép `firstPos` của q vẫn cho một đoạn đại diện của độ dài mới, vì clone đại diện hậu tố ngắn hơn của chuỗi dài thuộc q.

## 4. Xây SAM trực tuyến bằng cách thêm từng ký tự

SAM có thể được xây bằng cách đọc s từ trái sang phải, mỗi lần thêm một ký tự mới ở cuối prefix đã xử lý. Gọi `last` là trạng thái tương ứng **toàn bộ tiền tố hiện tại**.

Khi thêm ký tự c ở vị trí i:

1. Tạo state `cur` mới với `len[cur]=len[last]+1`, `firstPos=i` và `occ[cur]=1` (tiền tố mới kết thúc ở i).
2. Từ p=last, đi ngược suffix links. Với các state p chưa có cạnh c, thêm transition `p --c--> cur`.
3. Nếu đi đến p=−1 (vượt root) thì đặt `link[cur]=root`.
4. Nếu gặp một transition sẵn có `p --c--> q`, xét độ dài.
5. Nếu `len[p]+1=len[q]`, gắn `link[cur]=q`.
6. Nếu `len[p]+1<len[q]`, phải tạo **clone** để tách một lớp tương đương.
7. Cuối cùng `last=cur`.

### 4.1. Trường hợp A: đi hết suffix links mà không thấy cạnh c

Nếu mọi state trên chuỗi suffix links của last đều thiếu cạnh c, những hậu tố kết thúc bằng c thích hợp trước đây chưa tồn tại. Các transition được thêm tới cur; hậu tố proper dài nhất ngoài lớp mới là chuỗi rỗng. Ta đặt:

```text
link[cur] = root
```

Đây là tình huống đơn giản, ví dụ ký tự c chưa từng xuất hiện phù hợp trong một tiền tố nào trước đó.

### 4.2. Trường hợp B: đã có cạnh p --c--> q và độ dài liền kề

Nếu:

```text
len[p] + 1 == len[q]
```

thì q đã có độ dài dài nhất đúng bằng độ dài substring vừa tạo khi nối ký tự c từ lớp p. Không cần tách lớp endpos. Chỉ đặt:

```text
link[cur] = q
```

Các transition mới thêm ở các trạng thái thiếu c vẫn trỏ tới cur; link[cur] trỏ đến q để thể hiện hậu tố phù hợp.

### 4.3. Trường hợp C: phải tạo clone

Nếu đã có cạnh `p --c--> q` nhưng:

```text
len[p] + 1 < len[q]
```

q đang gộp những substring mà sau khi thêm ký tự mới **không còn cùng quan hệ endpos** như trước. Không thể gắn link[cur]=q trực tiếp, vì q có len lớn hơn độ dài hậu tố thích hợp cần tìm.

Tạo state `clone`:

```text
len[clone]      = len[p] + 1
next[clone]     = copy(next[q])
link[clone]     = old link[q]
firstPos[clone] = firstPos[q]
occ[clone]      = 0
```

**Clone không biểu diễn một tiền tố mới kết thúc tại thời điểm chèn**, nên ban đầu occ=0. Đây là điểm rất hay bị sai khi triển khai đếm số lần xuất hiện.

Tiếp theo:

- Đi ngược suffix links từ p.
- Trong khi transition c đang trỏ tới q, đổi nó sang clone.
- Đặt `link[q]=clone` và `link[cur]=clone`.

Lúc này clone đại diện cho phần lớp ngắn hơn, còn q đại diện cho phần dài hơn. Việc giữ nguyên những transition khác của q và sao chép sang clone bảo toàn các substring đã có.

**Không phải lúc nào cũng clone.** Clone chỉ cần khi một transition sẵn có có `len[q]>len[p]+1`. Nếu tự clone vô điều kiện, số trạng thái/links có thể bị sai hoặc phình không cần thiết.

### 4.4. Một hình dung trực quan

Trước khi clone, state q có thể đại diện cho nhiều substring cùng endpos trong tiền tố đã xây. Khi thêm một ký tự, những substring ngắn hơn trong lớp q bắt đầu có thể xuất hiện thêm ở vị trí mới, trong khi substring dài hơn không xuất hiện thêm. **Tập endpos tách làm hai nhóm**.

Clone tạo một lớp riêng cho nhóm ngắn hơn; q giữ nhóm dài hơn. Các suffix links trỏ đến clone để thể hiện chính xác quan hệ hậu tố mới. Bất biến endpos được duy trì sau mỗi ký tự.

## 5. Ví dụ bắt buộc: vì sao "abb" cần clone?

Xây SAM lần lượt cho s="a", rồi "ab", rồi "abb".

Sau "ab", đã có một state q biểu diễn chuỗi "ab" và đường root→"b" cũng có thể đi tới q: ở thời điểm đó "ab" và "b" cùng có endpos={1}, nên cùng một lớp.

Khi thêm ký tự 'b' cuối:

```text
text = "abb"

endpos("ab") = {1}
endpos("b")  = {1,2}
```

Hai substring không còn tương đương! Cần **clone q** để đưa "b" ra lớp riêng.

Trong cài đặt chuẩn, các trạng thái cuối cùng:

| ID | len | link | Khoảng độ dài [min,max] | occ | Clone? |
| ---: | ---: | ---: | --- | ---: | --- |
| 0 | 0 | −1 | root (chuỗi rỗng) | 3* | Không |
| 1 | 1 | 0 | [1,1] | 1 | Không |
| 2 | 2 | 4 | [2,2] | 1 | Không |
| 3 | 3 | 4 | [2,3] | 1 | Không |
| 4 | 1 | 0 | [1,1] | 2 | **Có** |

(*occ của root trong cách lan truyền mã là số vị trí kết thúc tiền tố không rỗng, bằng n; không dùng nó làm số lần xuất hiện của substring rỗng.*)

Những substring được chia theo state:

```text
State 1: "a"
State 2: "ab"
State 3: "bb", "abb"
State 4: "b"

Tổng 1+1+2+1 = 5 substring phân biệt.
```

Đúng bằng tập:

```text
{"a", "b", "ab", "bb", "abb"}
```

Một điểm quan trọng: **state 3** mang hai substring "bb" và "abb", vì chúng cùng kết thúc tại vị trí2 nên có endpos={2}. Không phải mọi state đều là một chuỗi nhãn duy nhất.

### 5.1. Các transition sau khi clone

Với quy trình thêm ký tự như trong mã Java:

```text
root --a--> state 1
root --b--> state 4  (clone)

state 1 --b--> state 2
state 2 --b--> state 3
state 4 --b--> state 3

link[state 2] = state 4
link[state 3] = state 4
link[state 4] = root
```

Cạnh root --b--> clone giúp nhận diện substring "b" tại cả hai vị trí. "ab" vẫn đi root --a-->1 --b-->2, không bị mất. Các đường "bb" và "abb" đều tới state3, minh họa trực tiếp việc **nhiều substring tới một state**.

### 5.2. Chứng minh clone không được occ=1

Khi thêm 'b' ở vị trí2, ta chỉ tạo **một tiền tố mới**: "abb" kết thúc ở2. State `cur=3` nhận occ=1. Clone state4 chỉ là nút được tạo để chia lại lớp tương đương, không phải một tiền tố mới thêm theo thời điểm; nếu đặt occ[clone]=1 ngay, sau khi cộng dồn qua suffix link nó sẽ **đếm thêm một lần không tồn tại**.

Cách đúng: **cur=1, clone=0**, sau đó lan truyền các đóng góp từ các prefix states qua suffix link. Kết quả "b" có occ=2 đúng như thực tế.

## 6. Đếm số chuỗi con phân biệt

Với mỗi trạng thái v≠root, các độ dài substring trong lớp v là:

```text
len(link[v])+1, len(link[v])+2, ..., len[v]
```

Số độ dài là:

```text
contribution(v) = len[v] - len[link[v]]
```

Vì mỗi độ dài thuộc một lớp cho đúng một substring, và mọi substring không rỗng thuộc một lớp, ta được:

```text
DISTINCT(s) =
    SUM_{v != root} (len[v] - len[link[v]])
```

Chỉ cần duyệt các state một lần sau khi xây xong SAM, O(numberOfStates)=O(n).

### 6.1. Ví dụ "ababa"

Trạng thái của SAM("ababa") không cần clone; theo một thứ tự xây chuẩn:

| State | len | link | Dải độ dài | Số substring đóng góp | Các substring thuộc lớp |
| ---: | ---: | ---: | --- | ---: | --- |
| 0 | 0 | −1 | root | 0 | Chuỗi rỗng |
| 1 | 1 | 0 | [1,1] | 1 | a |
| 2 | 2 | 0 | [1,2] | 2 | b, ab |
| 3 | 3 | 1 | [2,3] | 2 | ba, aba |
| 4 | 4 | 2 | [3,4] | 2 | bab, abab |
| 5 | 5 | 3 | [4,5] | 2 | baba, ababa |

Tổng:

```text
1 + 2 + 2 + 2 + 2 = 9
```

Tập substring phân biệt, theo thứ tự từ điển dựa trên code point:

```text
a
ab
aba
abab
ababa
b
ba
bab
baba
```

Có **9 substring phân biệt**, dù số đoạn vị trí là `5×6/2=15`.

### 6.2. Ví dụ "banana"

Với s="banana" (6 code points):

```text
number of SAM states = 10
number of distinct nonempty substrings = 15
occ("ana") = 2
```

15 substring phân biệt có thể phân nhóm theo ký tự bắt đầu:

```text
Bắt đầu bằng b:
    b, ba, ban, bana, banan, banana         (6)

Bắt đầu bằng a:
    a, an, ana, anan, anana                  (5)

Bắt đầu bằng n:
    n, na, nan, nana                         (4)

Tổng = 6+5+4 = 15
```

Lưu ý các substring đếm **theo nội dung**, không nhân theo số vị trí lặp. "ana" xuất hiện ở khoảng [1,4) và [3,6) nhưng chỉ góp **một** substring phân biệt.

### 6.3. Dùng long, không dùng int cho số lượng

Tối đa có `n(n+1)/2` substring phân biệt. Với chuỗi đủ dài, giá trị có thể vượt miền int; trong Java nên dùng long. Nếu chuỗi thực tế quá lớn để tổng còn vừa long, cần BigInteger, nhưng vì độ dài String/array còn bị chặn bởi int và bộ nhớ, long thường đủ cho bài lập trình thông thường.

Với s rỗng, SAM chỉ có root và số substring **không rỗng** bằng 0.

## 7. Kiểm tra substring có tồn tại hay không

Một phép kiểm tra membership đơn giản:

```text
contains(pattern):
    state = root
    for each character c of pattern:
        if next[state][c] does not exist:
            return false
        state = next[state][c]
    return true
```

Lý do: Mọi đường từ root biểu diễn một substring của s, và mọi substring có đường tương ứng. Không cần đi suffix links khi tra một pattern **đã có sẵn**: chỉ cần lần lượt đi transition từ root.

Thời gian:

```text
O(|pattern|)
```

tính theo số ký tự/code points và giả thiết lookup Map O(1) trung bình.

**Ví dụ s="ababa":**

```text
contains("aba")   = true
contains("bab")   = true
contains("aa")    = false
contains("abc")   = false
contains("")      = true   (quy ước empty substring)
```

Bản Java cố ý chọn `contains("")=true` theo quy ước toán học: chuỗi rỗng là substring của mọi chuỗi, kể cả chuỗi rỗng.

**Không được hiểu end state là vị trí kết thúc duy nhất trong text.** SAM gom nhiều lần xuất hiện; membership chỉ trả yes/no, chưa trả mọi vị trí.

## 8. Đếm số lần xuất hiện của substring

Cần phân biệt hai thứ:

- Trong lúc xây SAM, một state mới `cur` được tạo cho **mỗi tiền tố** của s, có thể đặt `occ[cur]=1`.
- Clone state `clone` không gắn với một tiền tố mới, đặt `occ[clone]=0`.

Sau khi xây xong, để biết `|endpos(v)|`, truyền số đếm từ các state có độ dài lớn xuống suffix link:

```text
order states by len increasing
for each v in order REVERSED (except root):
    occ[link[v]] += occ[v]
```

Phải duyệt theo **len giảm dần**, vì `len[link[v]]<len[v]`. Nếu cộng theo thứ tự ngẫu nhiên, một state có thể chưa nhận đủ đóng góp từ các con suffix-link trước khi truyền tiếp lên cha.

### 8.1. Vì sao công thức đúng?

Mỗi vị trí kết thúc i trong s tạo một tiền tố s[0..i] với state `cur_i`. Đặt một dấu đếm ở state ấy. Mọi hậu tố của tiền tố này tương ứng các lớp có thể tìm bằng cách đi suffix links từ cur_i. Vì vậy khi cộng dồn tất cả dấu đếm theo cây suffix links, state v nhận đúng một dấu cho mỗi vị trí i sao cho một substring thuộc lớp v kết thúc ở i.

Do đó sau propagation:

```text
occ[v] = |endpos(v)|
```

Với một truy vấn không rỗng q, đi transition từ root theo q; nếu tới state v, số lần xuất hiện của q bằng `occ[v]`. Mọi substring thuộc cùng lớp v có **cùng endpos**, nên dùng chung số đếm là chính xác.

### 8.2. Các ví dụ

```text
s = "ababa"
occ("a")   = 3      // kết thúc ở 0,2,4
occ("aba") = 2      // [0,3), [2,5)
occ("bab") = 1      // [1,4)
occ("aa")  = 0      // không có transition
```

```text
s = "aaaa"
occ("a")   = 4
occ("aa")  = 3
occ("aaa") = 2
occ("aaaa")= 1
```

**Đếm chồng lấp là bắt buộc** trong định nghĩa này: "aa" xuất hiện 3 lần trong "aaaa" ở start0,1,2.

### 8.3. Chuỗi rỗng cần chính sách riêng

Về mặt quy ước substring, chuỗi rỗng có **n+1 ranh giới** trong chuỗi dài n. Nhưng `occ[root]` trong quy trình cộng dồn prefix-state của mã là n, vì chỉ có n tiền tố **không rỗng** được chèn.

Vì vậy không được trả `occ[root]` như “số lần xuất hiện của chuỗi rỗng”. Trong chương trình:

- `contains("")` trả true.
- `occurrences("")` **ném IllegalArgumentException** để tránh quy ước mơ hồ.
- Nếu ứng dụng cần `n+1` cho empty pattern, hãy xử lý riêng ở API, không dựa trên occ[root].

### 8.4. Khi cần vị trí của từng lần xuất hiện

occ[v] chỉ là **số lượng**, không lưu trực tiếp mọi vị trí. Để liệt kê các vị trí kết thúc của một substring, có thể lưu các vị trí của prefix states rồi thu thập theo **cây suffix links**, hoặc dùng cấu trúc phụ để hỗ trợ truy vấn vị trí hiệu quả. Việc lưu/đưa ra K vị trí vẫn cần Ω(K) thời gian đầu ra.

Không nên suy ra “vì firstPos có một vị trí nên occ lần xuất hiện đều ở vị trí ấy”. firstPos chỉ là một đại diện, không phải tập endpos.

## 9. Cách thứ hai đếm substring: đếm đường đi trên transition DAG

Do transition graph là DAG và mỗi đường từ root có nhãn duy nhất, số substring phân biệt bằng **số đường không rỗng bắt đầu từ root**, mỗi đường dừng ở một vị trí bất kỳ.

Đặt:

```text
ways[v] =
    số đường đi KHÔNG RỖNG bắt đầu từ state v
```

Với mỗi cạnh từ v sang u mang ký tự c, ta có:

1. Đường chỉ gồm riêng c: **1** cách.
2. Đường bắt đầu bằng c rồi đi tiếp một đường không rỗng từ u: **ways[u]** cách.

Nên:

```text
ways[v] = SUM_{(v --c--> u)} (1 + ways[u])

distinctSubstrings = ways[root]
```

Công thức này tính **đường đi**, không tính số state. Cạnh khác nhãn đại diện substring bắt đầu bằng ký tự khác, nên không đếm trùng; với cùng nhãn, transition của một state là đơn trị, nên không có hai đường khác nhau cùng chuỗi nhãn.

### 9.1. Thứ tự tính DP

Mỗi transition v→u đi tới state có len lớn hơn. Vì vậy có thể tính `ways` theo **len giảm dần** (đầu tiên các state dài, sau đó các state ngắn), hoặc DFS memoization trên transition DAG. Mã Java dùng counting sort theo len để có thứ tự O(n), rồi duyệt ngược.

**Độc lập với công thức suffix link:** Có thể dùng `sum(len−len(link))` và `ways[root]` để cross-check hai cách đếm. Với "ababa", cả hai trả 9; với "banana", cả hai trả 15.

### 9.2. Không nhầm “đường từ root” và “đường bất kỳ”

Một đường bắt đầu từ một state không phải root có thể mang một chuỗi nhãn, nhưng để biểu diễn **substrings của s với nhãn đầy đủ**, ta đếm đường từ **root**. Công thức ways[v] chỉ là bộ đếm số **phần nối thêm** phục vụ tổng từ root và chọn thứ k; nó không tự động là số substring của mọi chuỗi phụ có ngữ cảnh bất kỳ.

## 10. Chuỗi con phân biệt thứ k theo thứ tự từ điển

Nếu cần substring **không rỗng** thứ k, đánh số từ 1, theo thứ tự từ điển trên **Unicode code point**, có thể dùng ways[] để bỏ qua nguyên nhánh.

Tại một state v:

1. Lấy các ký tự c của outgoing transitions theo thứ tự tăng dần.
2. Với cạnh c→u, số substring bắt đầu với ký tự c tại vị trí này là `1+ways[u]`.
3. Nếu k lớn hơn số đó, trừ k và bỏ toàn bộ nhánh.
4. Nếu k nằm trong nhánh, thêm c vào kết quả.
5. Substring chỉ gồm phần hiện tại là mục đầu tiên của nhánh; nếu k=1, trả ngay.
6. Nếu k>1, trừ 1 rồi chuyển v=u và xét phần mở rộng tiếp.

Giả mã:

```text
kthDistinct(k):
    ways = countNonemptyPathsPerState()
    require 1 <= k <= ways[root]

    answer = ""
    v = root

    loop:
        for c in sortedOutgoingLabels(v):
            u = next[v][c]
            branch = 1 + ways[u]

            if k > branch:
                k -= branch
                continue

            append c to answer
            if k == 1:
                return answer

            k -= 1
            v = u
            break
```

Với s="ababa", danh sách đã sắp:

```text
1  a
2  ab
3  aba
4  abab
5  ababa
6  b
7  ba
8  bab
9  baba
```

Nên:

```text
kthDistinct(1) = "a"
kthDistinct(5) = "ababa"
kthDistinct(6) = "b"
kthDistinct(9) = "baba"
```

Nếu k=0 hoặc k>9, chương trình **ném lỗi rõ ràng**, không truy cập transition sai hoặc trả chuỗi ngẫu nhiên.

### 10.1. Thứ tự Unicode code point khác thứ tự ngôn ngữ tự nhiên

Mã sắp các mã số **code point** bằng Integer ascending. Đây là một thứ tự xác định và phù hợp cho bài thuật toán, nhưng không tương đương mọi quy tắc sắp từ điển theo ngôn ngữ hay java.text.Collator. Nếu đề yêu cầu thứ tự có dấu/không dấu, không phân biệt hoa/thường hoặc chuẩn locale, cần định nghĩa lại comparator và đảm bảo cấu trúc hoạt động theo tiêu chí ấy.

### 10.2. Chi phí của kth trong bản Java

Mã tính ways[] một lần cho mỗi lần gọi kth: O(states+transitions). Sau đó khi đi theo đường kết quả, mỗi state được ghé có nhãn outgoing được sắp xếp. Cận trên thô cho một truy vấn là O(E log σ_max + độ dài kết quả) trên các state có thể ghé, với E là số transition và σ_max là bậc ra tối đa; với alphabet nhỏ, thường nhanh.

Nếu có rất nhiều truy vấn kth, có thể **cache ways[] và danh sách cạnh đã sort** sau khi xây automaton để tránh tính lại. Mã mẫu ưu tiên minh bạch và ít trạng thái mutable hơn.

## 11. Substring xuất hiện lặp lại dài nhất

Muốn tìm một substring xuất hiện **ít nhất hai lần**, kể cả hai lần chồng lấp, có thể:

1. Xây SAM và propagate occ[].
2. Duyệt các state v≠root có `occ[v]≥2`.
3. Chọn v có `len[v]` lớn nhất.
4. Dùng `firstPos[v]` để khôi phục đại diện dài `len[v]` từ s.

Vì mọi substring trong lớp v có cùng occ, chọn substring dài nhất của lớp là tối ưu trong số các substring do lớp ấy đại diện.

```text
bestState = argmax len[v]
            subject to v != root and occ[v] >= 2

result = s[firstPos[v]-len[v]+1 .. firstPos[v]+1)
```

Nếu không có state nào có `occ≥2` và len>0, kết quả là chuỗi rỗng.

Ví dụ:

```text
s = "ababa"
longestRepeated = "aba"  (length=3, occurs=2)

s = "aaaa"
longestRepeated = "aaa"  (length=3, occurs=2)

s = "abc"
longestRepeated = ""     (không có substring không rỗng lặp lại)
```

**Chú ý về “không chồng lấp”:** Điều kiện occ≥2 ở đây **cho phép chồng lấp**. Nếu đề yêu cầu hai lần xuất hiện **không chồng lấp**, chỉ biết số lần occ không đủ; cần thông tin vị trí bắt đầu/kết thúc cực trị hoặc phương án khác để kiểm tra khoảng cách tối thiểu giữa hai lần.

## 12. Longest Common Substring (LCS) của hai chuỗi

**Longest Common Substring** là chuỗi con **liên tiếp dài nhất** xuất hiện trong cả A và B. Nó **khác Longest Common Subsequence**, vốn cho phép bỏ ký tự.

Cho:

```text
A = "banana"
B = "ananas"

Longest common substring = "anana"
Length = 5 code points
```

Giải bằng SAM:

1. Xây SAM của A.
2. Quét B từ trái sang phải.
3. Giữ state u và biến `matched` là độ dài **hậu tố của B đã quét vẫn nhận diện được trong SAM(A)**.
4. Nếu u có transition bằng ký tự c mới, chuyển state và tăng matched.
5. Nếu không có cạnh c, đi theo suffix links để rút hậu tố đang khớp; mỗi lần đặt matched=len[state mới].
6. Nếu đến root vẫn không có cạnh c, matched=0, state=root.
7. Theo dõi giá trị matched lớn nhất và vị trí kết thúc tương ứng trong B.

Giả mã:

```text
u = root
matched = 0
best = 0
bestEnd = 0

for i = 0..|B|-1:
    c = B[i]

    while u != root and next[u][c] absent:
        u = link[u]
        matched = len[u]

    if next[u][c] exists:
        u = next[u][c]
        matched += 1
    else:
        u = root
        matched = 0

    if matched > best:
        best = matched
        bestEnd = i + 1

answer = B[bestEnd-best .. bestEnd)
```

### 12.1. Tại sao matched không đơn giản bằng len[u] ở mọi bước?

Một state đại diện nhiều substring có độ dài khác nhau. Khi quét B, phần đang khớp có thể chỉ là **một substring ngắn hơn len[u]** dù kết thúc tại u. Ta cần lưu biến `matched` riêng. Khi đi suffix link vì thiếu transition, mới đặt matched về `len[u]` của lớp hậu tố vừa chọn.

Nếu luôn đặt matched=len[u] sau mọi transition, có thể **phóng đại độ dài khớp** khi đường từ B chưa có đủ số ký tự tương ứng.

### 12.2. Phân tích thời gian

Mỗi ký tự B được xử lý một lần; các bước đi suffix links giảm độ dài matched, các bước chuyển thành công tăng nó một đơn vị. Do matched≥0, tổng số bước đi suffix link được khống chế amortized O(|B|). Với tra Map trung bình O(1), quét B tốn **O(|B|)** sau khi đã xây SAM của A.

Nếu hai chuỗi rỗng hoặc không có substring chung không rỗng, trả chuỗi rỗng và độ dài0.

## 13. Unicode code point và chỉ số trong Java

Một `char` Java là UTF-16 **code unit**, không nhất thiết là một Unicode code point hoàn chỉnh. Ký tự 🙂 nằm ngoài BMP nên chiếm **hai char** nhưng chỉ **một code point**.

Mã dùng:

```java
int[] cps = input.codePoints().toArray();
```

Mỗi cạnh next của SAM mang một int code point. Các biến `len, firstPos, matched` đều đo theo **code point index**, không phải offset UTF-16.

Khi khôi phục substring từ mảng codepoints:

```java
new String(codePoints, startCp, lengthCp)
```

Java xây chuỗi đúng từ các code points, không cắt giữa hai nửa surrogate pair.

### 13.1. Ví dụ Unicode

Cho:

```text
s = "a🙂a🙂"

Code points:  [a, 🙂, a, 🙂]
N = 4
UTF-16 code units = 6
```

Những substring phân biệt:

```text
a
🙂
a🙂
🙂a
a🙂a
🙂a🙂
a🙂a🙂
```

Tổng = **7**. "🙂" xuất hiện hai lần; "a🙂" cũng xuất hiện hai lần. SAM xây trên code point có 5 state với chuỗi mẫu này.

Nếu chỉ báo vị trí code point, cần chuyển đổi sang UTF-16 offset trước khi cắt String bằng substring(int,int). Không được dùng chỉ số code point như chỉ số char một cách mù quáng. Mã này trả chuỗi kết quả bằng new String(int[],...), tránh lỗi.

### 13.2. Chuẩn hóa Unicode và so sánh chữ

SAM thực hiện **so khớp chính xác** các codepoints đã được đưa vào. Nếu một chữ có thể được biểu diễn dưới dạng ký tự dựng sẵn hoặc base+combining mark, hai chuỗi nhìn giống nhau có thể có codepoint sequence khác nhau. Nếu ứng dụng muốn coi chúng tương đương, hãy chuẩn hóa **cả chuỗi gốc và truy vấn** theo cùng quy tắc như NFC.

Nếu muốn case-insensitive, phải định nghĩa chính sách lowercase/case folding nhất quán. Các biến đổi này có thể thay đổi số codepoints và offset, nên nếu cần vị trí trong text gốc phải giữ bảng ánh xạ ngược.

Mã giả định input là chuỗi Unicode hợp lệ; với surrogate code unit đơn lẻ không ghép cặp, cần chính sách kiểm tra/làm sạch đầu vào ở tầng ứng dụng.

## 14. Cài đặt Java 17+ hoàn chỉnh

Tên tệp: **`SuffixAutomatonDemo.java`**. Mã chạy độc lập, không dùng thư viện ngoài JDK.

Chức năng:

- Xây SAM trực tuyến từ một String theo code point, gồm trường hợp clone.
- Counting sort các state theo len, rồi propagate occ[] theo suffix links.
- `contains(query)`: có substring không; query rỗng được chấp nhận.
- `occurrences(query)`: số lần xuất hiện chồng lấp của query **không rỗng**; query rỗng bị từ chối theo hợp đồng API.
- `distinctByLinks()`: công thức tổng len−len(link).
- `distinctByPaths()`: đếm số đường đi không rỗng từ root trên transition DAG; dùng làm kiểm tra độc lập.
- `kthDistinct(k)`: substring phân biệt thứ k, k bắt đầu từ 1, theo thứ tự codepoint.
- `longestRepeatedSubstring()`: substring lặp lại dài nhất với ít nhất hai lần xuất hiện, chấp nhận chồng lấp.
- `longestCommonSubstring(other)`: quét chuỗi thứ hai bằng suffix links và trả substring, độ dài codepoint, vị trí bắt đầu codepoint trong other.
- `randomCrossCheck()`: 500 phép thử nhỏ với alphabet gồm ASCII và emoji, đối chiếu với brute force cho **tập substring, tần suất, kth, LCS và longest repeated length**.

### 14.1. Toàn bộ mã

```java
import java.util.*;

public class SuffixAutomatonDemo {
    static final class State {
        final Map<Integer, Integer> next = new HashMap<>();
        int len = 0;
        int link = -1;
        int firstPos = -1;
        long occ = 0;
        boolean clone = false;
    }

    record Lcs(String substring, int lengthCp, int startInOtherCp) {}

    static final class SAM {
        private final List<State> states = new ArrayList<>();
        private final int[] source;
        private int last = 0;

        SAM(String input) {
            Objects.requireNonNull(input, "input");
            source = input.codePoints().toArray();
            states.add(new State()); // root: len=0, link=-1
            for (int i = 0; i < source.length; i++) {
                extend(source[i], i);
            }
            propagateOccurrences();
        }

        private void extend(int cp, int position) {
            int cur = states.size();
            State fresh = new State();
            fresh.len = states.get(last).len + 1;
            fresh.firstPos = position;
            fresh.occ = 1; // every prefix end contributes once
            states.add(fresh);

            int p = last;
            while (p != -1
                    && !states.get(p).next.containsKey(cp)) {
                states.get(p).next.put(cp, cur);
                p = states.get(p).link;
            }

            if (p == -1) {
                fresh.link = 0;
            } else {
                int q = states.get(p).next.get(cp);
                if (states.get(p).len + 1 == states.get(q).len) {
                    fresh.link = q;
                } else {
                    int clone = states.size();
                    State copied = new State();
                    State original = states.get(q);
                    copied.len = states.get(p).len + 1;
                    copied.link = original.link;
                    copied.firstPos = original.firstPos;
                    copied.clone = true;
                    copied.next.putAll(original.next);
                    // Clones do not terminate an inserted prefix.
                    copied.occ = 0;
                    states.add(copied);

                    while (p != -1
                            && Objects.equals(
                                    states.get(p).next.get(cp), q)) {
                        states.get(p).next.put(cp, clone);
                        p = states.get(p).link;
                    }

                    original.link = clone;
                    fresh.link = clone;
                }
            }
            last = cur;
        }

        // Counting sort by len: O(n + states).
        private int[] statesByLength() {
            int n = source.length;
            int[] frequency = new int[n + 1];
            for (State s : states) {
                frequency[s.len]++;
            }
            for (int i = 1; i <= n; i++) {
                frequency[i] += frequency[i - 1];
            }
            int[] order = new int[states.size()];
            for (int id = states.size() - 1; id >= 0; id--) {
                int length = states.get(id).len;
                order[--frequency[length]] = id;
            }
            return order;
        }

        private void propagateOccurrences() {
            int[] order = statesByLength();
            for (int i = order.length - 1; i >= 1; i--) {
                int u = order[i];
                int suffix = states.get(u).link;
                states.get(suffix).occ += states.get(u).occ;
            }
        }

        int stateCount() {
            return states.size();
        }

        int transitionCount() {
            int total = 0;
            for (State s : states) {
                total += s.next.size();
            }
            return total;
        }

        boolean contains(String query) {
            Objects.requireNonNull(query, "query");
            int u = 0;
            for (int cp : query.codePoints().toArray()) {
                Integer next = states.get(u).next.get(cp);
                if (next == null) {
                    return false;
                }
                u = next;
            }
            return true; // empty string is a substring by convention
        }

        long occurrences(String query) {
            Objects.requireNonNull(query, "query");
            if (query.isEmpty()) {
                throw new IllegalArgumentException(
                        "occurrences of empty query not supported");
            }
            int u = 0;
            for (int cp : query.codePoints().toArray()) {
                Integer next = states.get(u).next.get(cp);
                if (next == null) {
                    return 0L;
                }
                u = next;
            }
            return states.get(u).occ; // overlapping occurrences counted
        }

        long distinctByLinks() {
            long result = 0L;
            for (int u = 1; u < states.size(); u++) {
                State current = states.get(u);
                result += (long) current.len
                        - states.get(current.link).len;
            }
            return result;
        }

        // Number of nonempty paths starting at each state.
        private long[] pathCounts() {
            long[] ways = new long[states.size()];
            int[] order = statesByLength();
            for (int i = order.length - 1; i >= 0; i--) {
                int u = order[i];
                for (int v : states.get(u).next.values()) {
                    ways[u] += 1L + ways[v];
                }
            }
            return ways;
        }

        long distinctByPaths() {
            return pathCounts()[0];
        }

        // 1-based order under Unicode code-point lexicographic order.
        String kthDistinct(long k) {
            long[] ways = pathCounts();
            if (k <= 0 || k > ways[0]) {
                throw new IllegalArgumentException(
                        "k outside distinct substring count");
            }
            int u = 0;
            StringBuilder answer = new StringBuilder();

            while (true) {
                int[] letters = states.get(u).next.keySet()
                        .stream().mapToInt(Integer::intValue)
                        .sorted().toArray();
                boolean found = false;

                for (int cp : letters) {
                    int v = states.get(u).next.get(cp);
                    long count = 1L + ways[v];
                    if (k > count) {
                        k -= count;
                        continue;
                    }
                    answer.appendCodePoint(cp);
                    if (k == 1L) {
                        return answer.toString();
                    }
                    k--; // consume substring ending at this edge
                    u = v;
                    found = true;
                    break;
                }
                if (!found) {
                    throw new AssertionError("invalid path count");
                }
            }
        }

        String longestRepeatedSubstring() {
            int best = 0;
            for (int i = 1; i < states.size(); i++) {
                State s = states.get(i);
                if (s.occ >= 2 && s.len > states.get(best).len) {
                    best = i;
                }
            }
            State s = states.get(best);
            if (s.len == 0) {
                return "";
            }
            int begin = s.firstPos - s.len + 1;
            return new String(source, begin, s.len);
        }

        Lcs longestCommonSubstring(String other) {
            Objects.requireNonNull(other, "other");
            int[] chars = other.codePoints().toArray();
            int u = 0;
            int matched = 0;
            int best = 0;
            int bestEnd = 0;

            for (int i = 0; i < chars.length; i++) {
                int cp = chars[i];
                while (u != 0 && !states.get(u).next.containsKey(cp)) {
                    u = states.get(u).link;
                    matched = states.get(u).len;
                }

                Integer next = states.get(u).next.get(cp);
                if (next == null) {
                    u = 0;
                    matched = 0;
                } else {
                    u = next;
                    matched++;
                }
                if (matched > best) {
                    best = matched;
                    bestEnd = i + 1;
                }
            }
            return new Lcs(
                    new String(chars, bestEnd - best, best),
                    best, bestEnd - best);
        }
    }

    static Map<String, Long> bruteCounts(String text) {
        int[] cps = text.codePoints().toArray();
        Map<String, Long> result = new HashMap<>();
        for (int start = 0; start < cps.length; start++) {
            for (int end = start + 1; end <= cps.length; end++) {
                String sub = new String(cps, start, end - start);
                result.merge(sub, 1L, Long::sum);
            }
        }
        return result;
    }

    static int compareCodePoints(String a, String b) {
        int[] x = a.codePoints().toArray();
        int[] y = b.codePoints().toArray();
        for (int i = 0; i < Math.min(x.length, y.length); i++) {
            int c = Integer.compare(x[i], y[i]);
            if (c != 0) {
                return c;
            }
        }
        return Integer.compare(x.length, y.length);
    }

    static int bruteLcsLength(String left, String right) {
        int[] cps = right.codePoints().toArray();
        int result = 0;
        for (int start = 0; start < cps.length; start++) {
            for (int end = start + 1; end <= cps.length; end++) {
                String candidate =
                        new String(cps, start, end - start);
                if (left.contains(candidate)) {
                    result = Math.max(result, end - start);
                }
            }
        }
        return result;
    }

    static void randomCrossCheck() {
        Random rng = new Random(20261110L);
        int[] alphabet = {'a', 'b', 'c', 0x1F642};

        for (int trial = 0; trial < 500; trial++) {
            StringBuilder a = new StringBuilder();
            StringBuilder b = new StringBuilder();
            int n = rng.nextInt(10);
            int m = rng.nextInt(10);

            for (int i = 0; i < n; i++) {
                a.appendCodePoint(alphabet[rng.nextInt(alphabet.length)]);
            }
            for (int i = 0; i < m; i++) {
                b.appendCodePoint(alphabet[rng.nextInt(alphabet.length)]);
            }

            String left = a.toString();
            String right = b.toString();
            SAM sam = new SAM(left);
            Map<String, Long> count = bruteCounts(left);

            if (sam.distinctByLinks() != count.size()
                    || sam.distinctByPaths() != count.size()) {
                throw new AssertionError(
                        "distinct mismatch in trial " + trial);
            }

            int maxStates = n == 0 ? 1 : (n == 1 ? 2 : 2 * n - 1);
            if (sam.stateCount() > maxStates) {
                throw new AssertionError("too many states");
            }

            for (Map.Entry<String, Long> e : count.entrySet()) {
                if (!sam.contains(e.getKey())
                        || sam.occurrences(e.getKey()) != e.getValue()) {
                    throw new AssertionError(
                            "occurrences mismatch trial " + trial);
                }
            }
            if (!sam.contains("")) {
                throw new AssertionError(
                        "empty substring membership mismatch");
            }

            List<String> sorted = new ArrayList<>(count.keySet());
            sorted.sort(SuffixAutomatonDemo::compareCodePoints);
            for (int k = 1; k <= sorted.size(); k++) {
                if (!sam.kthDistinct(k).equals(sorted.get(k - 1))) {
                    throw new AssertionError(
                            "kth mismatch trial " + trial);
                }
            }

            int expectedRepeated = 0;
            for (Map.Entry<String, Long> e : count.entrySet()) {
                if (e.getValue() >= 2) {
                    expectedRepeated = Math.max(
                            expectedRepeated,
                            e.getKey().codePointCount(
                                    0, e.getKey().length()));
                }
            }
            String repeated = sam.longestRepeatedSubstring();
            int repeatLength =
                    repeated.codePointCount(0, repeated.length());
            if (repeatLength != expectedRepeated
                    || (!repeated.isEmpty()
                        && sam.occurrences(repeated) < 2)) {
                throw new AssertionError(
                        "longest repeated mismatch");
            }

            Lcs lcs = sam.longestCommonSubstring(right);
            if (lcs.lengthCp() != bruteLcsLength(left, right)
                    || !left.contains(lcs.substring())
                    || !right.contains(lcs.substring())
                    || lcs.substring().codePointCount(
                            0, lcs.substring().length())
                        != lcs.lengthCp()) {
                throw new AssertionError(
                        "LCS mismatch trial " + trial);
            }
        }
        System.out.println(
                "Random exhaustive: PASS (500 Unicode cases)");
    }

    public static void main(String[] args) {
        SAM alternating = new SAM("ababa");
        System.out.println(
                "ababa: states=" + alternating.stateCount()
                + ", transitions=" + alternating.transitionCount()
                + ", distinct=" + alternating.distinctByLinks()
                + ", dp=" + alternating.distinctByPaths());
        System.out.println(
                "ababa membership: aba=" + alternating.contains("aba")
                + ", aa=" + alternating.contains("aa"));
        System.out.println(
                "ababa occurrences: a=" + alternating.occurrences("a")
                + ", aba=" + alternating.occurrences("aba")
                + ", bab=" + alternating.occurrences("bab"));
        System.out.println(
                "ababa kth: 1=" + alternating.kthDistinct(1)
                + ", 5=" + alternating.kthDistinct(5)
                + ", 6=" + alternating.kthDistinct(6)
                + ", 9=" + alternating.kthDistinct(9));
        String repeated = alternating.longestRepeatedSubstring();
        System.out.println(
                "ababa repeated: " + repeated
                + " occurs=" + alternating.occurrences(repeated));

        SAM banana = new SAM("banana");
        System.out.println(
                "banana: states=" + banana.stateCount()
                + ", distinct=" + banana.distinctByLinks()
                + ", ana=" + banana.occurrences("ana"));
        Lcs common = banana.longestCommonSubstring("ananas");
        System.out.println(
                "LCS banana/ananas: " + common.substring()
                + " length=" + common.lengthCp()
                + " startInOther=" + common.startInOtherCp());

        SAM repeats = new SAM("aaaa");
        System.out.println(
                "aaaa: states=" + repeats.stateCount()
                + ", distinct=" + repeats.distinctByLinks()
                + ", aa=" + repeats.occurrences("aa")
                + ", repeat=" + repeats.longestRepeatedSubstring()
                + ", kth4=" + repeats.kthDistinct(4));

        SAM empty = new SAM("");
        System.out.println(
                "empty: states=" + empty.stateCount()
                + ", distinct=" + empty.distinctByLinks()
                + ", hasEmpty=" + empty.contains("")
                + ", hasA=" + empty.contains("a"));

        String smile = new String(Character.toChars(0x1F642));
        SAM unicode = new SAM("a" + smile + "a" + smile);
        System.out.println(
                "unicode: states=" + unicode.stateCount()
                + ", distinct=" + unicode.distinctByLinks()
                + ", smile=" + unicode.occurrences(smile)
                + ", aSmile=" + unicode.occurrences("a" + smile));

        try {
            alternating.kthDistinct(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid k: " + ex.getMessage());
        }
        try {
            alternating.occurrences("");
        } catch (IllegalArgumentException ex) {
            System.out.println("Empty count: " + ex.getMessage());
        }

        randomCrossCheck();
    }
}
```

### 14.2. Biên dịch và chạy

Lưu mã vào tệp **SuffixAutomatonDemo.java**. Dùng JDK 17 trở lên:

```bash
javac SuffixAutomatonDemo.java
java SuffixAutomatonDemo
```

**Stdout chính xác:**

```text
ababa: states=6, transitions=6, distinct=9, dp=9
ababa membership: aba=true, aa=false
ababa occurrences: a=3, aba=2, bab=1
ababa kth: 1=a, 5=ababa, 6=b, 9=baba
ababa repeated: aba occurs=2
banana: states=10, distinct=15, ana=2
LCS banana/ananas: anana length=5 startInOther=0
aaaa: states=5, distinct=4, aa=3, repeat=aaa, kth4=aaaa
empty: states=1, distinct=0, hasEmpty=true, hasA=false
unicode: states=5, distinct=7, smile=2, aSmile=2
Invalid k: k outside distinct substring count
Empty count: occurrences of empty query not supported
Random exhaustive: PASS (500 Unicode cases)
```

### 14.3. Giải thích từng nhóm output

**ababa states/transitions:** Có 6 trạng thái (root + năm prefix states) và 6 transition. Số substring phân biệt bằng công thức suffix link là 9, đồng thời DP trên transition DAG trả 9. Hai cách đếm độc lập khớp.

**ababa membership:** "aba" xuất hiện, còn "aa" không có trong s. Kiểm tra bằng transition từ root, không cần so từng vị trí.

**ababa occurrences:** "a" xuất hiện 3 lần, "aba" 2 lần và "bab" một lần; các lần xuất hiện chồng lấp vẫn được tính.

**ababa kth:** Bốn truy vấn theo thứ tự từ điển code point trả "a","ababa","b","baba", đúng danh sách ở phần 10.

**ababa repeated:** Substring lặp dài nhất là "aba" độ dài3 và xuất hiện hai lần ở [0,3),[2,5).

**banana:** Có 10 states, 15 substring phân biệt, và "ana" xuất hiện hai lần. Clone states cần thiết để tách các lớp endpos khác nhau.

**LCS banana/ananas:** Chuỗi chung liên tiếp dài nhất là "anana" dài5 code points, bắt đầu ở index0 trong "ananas".

**aaaa:** Có bốn substring phân biệt, "aa" xuất hiện 3 lần, "aaa" lặp lại dài nhất và substring thứ4 là "aaaa".

**empty:** Với chuỗi gốc rỗng, chỉ có root, không có substring không rỗng; theo quy ước `contains("")=true`, `contains("a")=false`.

**unicode:** "a🙂a🙂" có 4 codepoints, 5 states, 7 substring phân biệt. Emoji "🙂" và "a🙂" đều xuất hiện hai lần. Mã khôi phục substring theo codepoint nên không cắt surrogate pair.

**Invalid k / Empty count:** API cố ý từ chối k ngoài [1,distinct] và truy vấn tần suất của chuỗi rỗng, giúp tránh kết quả mơ hồ.

**Random exhaustive:** 500 cặp chuỗi nhỏ ngẫu nhiên gồm 'a','b','c' và emoji 🙂, mỗi chuỗi có độ dài codepoint dưới10. Bộ kiểm thử tự liệt kê substring bằng brute force, rồi đối chiếu: countDistinct bằng cả hai công thức, occurrences cho mọi substring, mọi kth theo Unicode codepoint, độ dài repeated tối ưu và độ dài longest common substring. Chỉ in PASS nếu **mọi kiểm tra đều khớp**, nếu sai ném AssertionError.

## 15. Phân tích độ phức tạp và giới hạn bộ nhớ

Gọi n là số Unicode codepoints của chuỗi nguồn; m là độ dài truy vấn/chuỗi thứ hai.

### 15.1. Số trạng thái và transition

Với SAM của **một chuỗi**:

- n=0: chỉ root, 1 state.
- n=1: root và một state cho ký tự, 2 states.
- n≥2: số state tối đa **2n−1**.
- Số transition cũng O(n); một cận thường dùng cho n≥3 là **3n−4**.

Do đó dù có Θ(n²) substring phân biệt, cấu trúc SAM giữ **O(n)** state và transition.

Mã Java dùng HashMap cho transition và một state mới cho mỗi ký tự nguồn; có thể tạo thêm một clone cho một số lần mở rộng. Vì chỉ có O(n) clone, tổng số state vẫn O(n).

### 15.2. Xây và propagate

Trong triển khai chuẩn, với tra cứu Map trung bình O(1), việc dựng SAM có độ phức tạp **O(n) kỳ vọng** theo lập luận amortized cho các vòng đi suffix links và đổi hướng transition. Với alphabet cố định và mảng transition, thường trình bày O(n) thời gian.

Counting sort theo len mất O(n + numberOfStates)=O(n). Propagate occ theo suffix links mất O(numberOfStates)=O(n).

Bộ nhớ của source codepoints, state, suffix link và transitions là O(n) kỳ vọng theo số phần tử, với chi phí hằng số HashMap tương đối lớn.

**Cảnh báo triển khai:** Bản Java dùng HashMap linh hoạt cho Unicode nhưng có nhiều object và Map; với n cực lớn, chi phí bộ nhớ thực có thể cao dù ký hiệu Big-O là O(n). Có thể tối ưu bằng cấu trúc lưu transition gọn, nén alphabet hoặc dùng mảng cho alphabet nhỏ, cân nhắc thời gian/bộ nhớ thực tế.

### 15.3. Các thao tác truy vấn

| Truy vấn | Thời gian thường gặp | Bộ nhớ phụ |
| --- | --- | --- |
| contains(query) | O(m) trung bình | O(m) do tạo codepoint array |
| occurrences(query) | O(m) trung bình | O(m) do tạo codepoint array |
| distinctByLinks() | O(n) | O(1) ngoài state đã có |
| distinctByPaths() | O(n) | O(n) mảng order/ways |
| kthDistinct(k) | O(n) DP + chi phí sort outgoing trên đường truy vết | O(n) |
| longestRepeatedSubstring() | O(n) + độ dài kết quả | O(độ dài kết quả) |
| longestCommonSubstring(other) | O(m) trung bình sau build | O(m) do codepoint array |

Đối với kthDistinct, vì mã sắp outgoing labels **mỗi lần truy vấn**, cận thô cho phần sort trên đường là O(E log σ_max) với E là tổng số transition và σ_max là bậc ra lớn nhất. Muốn nhiều truy vấn kth, nên cache order và ways. Không được gọi kth liên tục hàng triệu lần rồi xem chi phí tiền xử lý như O(1) cho mỗi truy vấn.

### 15.4. Khi chỉ cần kiểm tra một substring, SAM có phải luôn tốt nhất?

Không. Nếu chỉ có một query m trên một text n, KMP hoặc phép tìm đơn mẫu phù hợp có thể đơn giản hơn. SAM hữu ích khi **một chuỗi nguồn cố định**, có rất nhiều truy vấn substring, hoặc khi cần **các thống kê toàn cục** như distinct count, repeated substring, LCS với nhiều chuỗi khác.

Nếu có nhiều mẫu cần tìm đồng thời **trên một text mới mỗi lần**, Aho–Corasick xây theo **tập mẫu** là hướng khác. Cả hai dùng automaton nhưng đối tượng tiền xử lý và câu hỏi truy vấn khác nhau.

## 16. SAM so với suffix tree, suffix array và các cấu trúc khác

| Cấu trúc | Tiền xử lý gì? | Mạnh ở đâu? |
| --- | --- | --- |
| **Suffix Automaton** | Một chuỗi s | Membership substring, số substring phân biệt, occurrences, LCS, repeated, kth |
| **Suffix Array** | Một chuỗi s, sắp các hậu tố | Tìm mẫu bằng binary search/LCP, sắp thứ tự hậu tố, truy vấn theo thứ tự |
| **Suffix Tree** | Một chuỗi s, trie hậu tố nén cạnh | Biểu diễn suffix và substring trong cây nén |
| **Suffix Trie** | Tất cả hậu tố không nén | Trực quan nhưng có thể Θ(n²) nút |
| **KMP / Z-function** | Mẫu hoặc một chuỗi | Khớp một mẫu, biên/chu kỳ/tiền tố |
| **Aho–Corasick** | Tập nhiều mẫu | Quét văn bản để tìm đồng thời nhiều mẫu |
| **Suffix automaton generalized** | Nhiều chuỗi với cách xử lý ranh giới | Một số bài nhiều chuỗi, cần thiết kế bổ sung |

SAM **không phải** suffix trie: chuyển trạng thái của nó là DAG có các đường khác nhãn có thể hội tụ vào cùng state do endpos tương đương. SAM cũng không phải suffix tree: suffix tree nén các cạnh chứa nhiều ký tự, còn SAM dùng transition theo một code point và suffix links; hai cấu trúc có những quan hệ toán học sâu sắc nhưng triển khai khác nhau.

### 16.1. Nếu chuỗi gốc thay đổi?

SAM online chuẩn hỗ trợ **thêm ký tự vào cuối** bằng extend và cập nhật links/transitions. Nhưng bản Java này **chốt occurrence propagation trong constructor** sau khi xây xong và không cung cấp API chỉnh sửa về sau. Nếu muốn thêm ký tự sau khi đã propagate, phải tổ chức lại base occ/propagation hoặc xây lại, không tăng occ trực tiếp rồi mặc định mọi thống kê cũ còn đúng.

Xóa ký tự, chèn ở giữa, sửa ký tự tùy vị trí là bài toán khác; không được xem SAM tĩnh như một cấu trúc edit hỗ trợ tùy ý.

### 16.2. Kết hợp nhiều chuỗi và ký tự phân cách

Nếu ghép nhiều chuỗi bằng một ký tự phân cách không xuất hiện trong input, SAM của chuỗi ghép có thể nhận diện những substring **băng qua ranh giới**, không tồn tại trong bất kỳ chuỗi gốc nào. Để giải bài nhiều chuỗi, phải đánh dấu ranh giới và thiết kế cách loại những substring băng qua, hoặc dùng phương pháp generalized SAM thích hợp.

Ví dụ ghép "ab#cd": chuỗi "b#c" là substring của chuỗi ghép, nhưng không phải substring của "ab" hay "cd". Không được trực tiếp dùng distinctCount của chuỗi ghép như tổng số substring phân biệt của các chuỗi nguồn.

## 17. Những lỗi thường gặp

1. **Coi mỗi state là một substring duy nhất.** Một state có thể đại diện cho nhiều độ dài trong khoảng len(link)+1..len.
2. **Đếm substring phân biệt bằng số state−1.** Công thức đúng là tổng len[v]−len[link[v]].
3. **Nhầm substring với subsequence.** SAM biểu diễn các đoạn **liên tiếp**.
4. **Nhầm suffix link với transition theo ký tự.** Link thể hiện quan hệ hậu tố lớp endpos, transition dùng để đọc substring.
5. **Gán link của root bằng 0 rồi không có điều kiện dừng.** Có thể lặp vô tận trên suffix links; mã dùng −1 cho root.
6. **Quên cập nhật last=cur khi thêm ký tự.** Prefix sau đó xây sai.
7. **Không tạo transition ở tất cả state p thiếu ký tự trên suffix-link chain.** Bỏ đường đọc một số substring mới.
8. **Gắn link[cur]=q khi len[p]+1<len[q].** Không tách lớp cần clone; len/link không còn đúng.
9. **Clone cả khi len[p]+1==len[q].** Thêm state không cần thiết, dễ sai cấu trúc.
10. **Quên copy next của q sang clone.** Đường substring trước đó có thể mất.
11. **Quên copy old link[q] sang clone.** Suffix-link tree có thể mất tính đúng.
12. **Quên đổi link[q] và link[cur] sang clone.** Hai lớp mới không được nối đúng.
13. **Không redirect các transition c trỏ tới q trên chuỗi suffix links.** Các đường ngắn vẫn đi q dài.
14. **Redirect mọi transition c không kiểm tra đích là q.** Phá các đường vốn cần giữ nguyên.
15. **Đặt occ[clone]=1.** Đếm thừa một tiền tố không tồn tại.
16. **Chỉ cộng occ của các state không clone rồi bỏ lan truyền qua clone.** Bỏ số lần xuất hiện của các substring ngắn.
17. **Propagate occ theo len tăng.** State cha có thể chưa nhận đủ số đếm từ con.
18. **Dùng occ[root] để đếm chuỗi rỗng n+1.** Trong code, root occ=n, không phải n+1.
19. **Đếm số lần substring bằng số transition tới state.** Không liên quan trực tiếp đến endpos.
20. **Không tính trường hợp match chồng lấp.** "aa" trong "aaaa" xuất hiện 3 lần, không phải2.
21. **Dùng int để chứa distinct count khi n đủ lớn.** Giá trị có thể vượt 2³¹−1.
22. **Tính dải độ dài của state là [len(link),len].** Biên trái đúng là **len(link)+1**.
23. **Quên loại root khỏi tổng distinct.** Root biểu diễn chuỗi rỗng, không đóng góp substring không rỗng.
24. **Duyệt transition DAG để DP theo thứ tự len tăng.** ways[u] cần ways[v] của các state có len lớn hơn; phải xử lý ngược.
25. **Đếm số đường bất kỳ trong DAG thay vì đường từ root.** Có thể đếm những nhãn không có ngữ cảnh khởi đầu đúng.
26. **Sai thứ tự từ điển khi kthDistinct.** Cần sort labels ở mỗi state theo comparator đúng.
27. **Dùng k bắt đầu từ0 trong công thức dành cho k từ1.** Dễ sai đúng một vị trí.
28. **Không trừ một đơn vị cho đường kết thúc ngay tại ký tự cạnh trong kth.** Bỏ qua substring tiền tố ngắn hơn.
29. **Đặt matched=len[u] sau mọi chuyển khi tìm LCS.** State có thể đại diện nhiều độ dài; matched riêng mới đúng.
30. **Đi suffix link khi tìm LCS mà không giảm matched.** Phóng đại chiều dài đường đang khớp.
31. **Nhầm LCS substring với longest common subsequence.** Subsequence cho phép bỏ ký tự.
32. **Chỉ dùng occ≥2 để kết luận hai lần xuất hiện không chồng lấp.** Cần kiểm tra vị trí nếu cấm chồng lấp.
33. **Dùng firstPos như vị trí xuất hiện sớm nhất.** Nó chỉ là một đại diện, không nhất thiết min endpos.
34. **Dùng String.length() như số codepoints của emoji.** Ngoài BMP gồm hai UTF-16 units.
35. **Cắt String bằng substring với codepoint offsets.** Có thể cắt giữa surrogate pair; dùng new String(int[],...).
36. **Chuẩn hóa query nhưng không chuẩn hóa source.** So khớp Unicode có thể bỏ kết quả đáng lẽ tương đương.
37. **Coi thứ tự Unicode codepoint là thứ tự từ điển của mọi ngôn ngữ.** Collation theo locale là tiêu chí khác.
38. **Cho rằng clone làm số state lên O(n²).** Có O(n) clones theo xây SAM chuẩn.
39. **Coi số đường từ root bị chặn bởi số state.** DAG có thể có Θ(n²) đường nhãn riêng dù chỉ O(n) nodes.
40. **Sử dụng một transition map chung cho q và clone thay vì copy.** Khi sửa map này, cả hai state bị thay đổi sai.
41. **Giữ occ đã propagate rồi tiếp tục extend mà không tái tổ chức.** Số đếm trạng thái có thể bị cộng nhiều lần.
42. **Kết hợp các chuỗi bằng separator rồi quên loại substring băng qua separator.** Báo những chuỗi con không thuộc chuỗi gốc nào.
43. **Không thử chuỗi rỗng và chuỗi dài1.** Biên n=0,1 có công thức số state riêng.
44. **Không thử các chuỗi lặp kiểu aaaa và chuỗi có clone kiểu abb/banana.** Nhiều lỗi chỉ lộ ở clone/occ.
45. **Không kiểm thử với oracle độc lập.** Distinct/formula và LCS dễ sai âm thầm nếu thiếu brute-force test nhỏ.

## 18. Bài tập tự luyện có đáp án

**Bài 1.** SAM được dùng để biểu diễn loại chuỗi con nào?

**Đáp án:** Các **substring liên tiếp** của một chuỗi nguồn, không phải subsequence rời rạc.

**Bài 2.** endpos(x) là gì?

**Đáp án:** Tập các chỉ số kết thúc (inclusive) của mọi lần xuất hiện substring x trong chuỗi nguồn.

**Bài 3.** Khi nào hai substring nằm trong cùng state SAM?

**Đáp án:** Khi chúng có **cùng tập endpos**; chúng là một lớp tương đương endpos.

**Bài 4.** Trong "ababa", endpos("b") và endpos("ab") là gì?

**Đáp án:** Cả hai bằng {1,3}, nên cùng lớp endpos.

**Bài 5.** Trong "ababa", endpos("ba") và endpos("aba") là gì?

**Đáp án:** Cả hai bằng {2,4}, nên có thể cùng một state.

**Bài 6.** Một state v≠root đại diện những độ dài nào?

**Đáp án:** Tất cả độ dài nguyên từ `len(link[v])+1` đến `len[v]`.

**Bài 7.** Vì sao cần clone khi `len[p]+1<len[q]`?

**Đáp án:** Một lớp endpos đang cần tách thành phần ngắn hơn và dài hơn để giữ bất biến suffix-link/transition sau khi thêm ký tự.

**Bài 8.** Clone sao chép trường nào từ q và thay đổi trường nào?

**Đáp án:** Sao chép transitions, old link và firstPos; đặt `len[clone]=len[p]+1`, `occ[clone]=0`; redirect các transition c trỏ q và sửa link[q],link[cur] sang clone.

**Bài 9.** Vì sao occ[clone]=0?

**Đáp án:** Clone chỉ tách một lớp endpos, không tương ứng một tiền tố mới được thêm; đặt1 sẽ đếm thừa.

**Bài 10.** Trong chuỗi "abb", có bao nhiêu substring phân biệt?

**Đáp án:** 5: "a","b","ab","bb","abb".

**Bài 11.** Với state có len=7 và len(link)=3, đóng góp bao nhiêu substring phân biệt?

**Đáp án:** `7−3=4`, tương ứng bốn độ dài 4,5,6,7.

**Bài 12.** Công thức đếm tổng substring phân biệt bằng suffix links?

**Đáp án:** `Σ_{v≠root}(len[v]−len[link[v]])`.

**Bài 13.** "ababa" có bao nhiêu substring phân biệt?

**Đáp án:** 9.

**Bài 14.** "banana" có bao nhiêu substring phân biệt?

**Đáp án:** 15.

**Bài 15.** Kiểm tra "aba" có phải substring của "ababa" bằng SAM thế nào?

**Đáp án:** Bắt đầu tại root, lần lượt đi transition 'a','b','a'; nếu đủ ba transition tồn tại, trả true.

**Bài 16.** Mất bao lâu để kiểm tra một query dài m trên SAM đã xây?

**Đáp án:** O(m) trung bình với Map lookup O(1) trung bình.

**Bài 17.** Vì sao phải lan truyền occ theo len giảm dần?

**Đáp án:** Suffix link đi tới state có len nhỏ hơn; cần cộng đủ số đếm của state dài vào state ngắn trước khi state ngắn truyền lên tiếp.

**Bài 18.** Trong "aaaa", "aa" xuất hiện mấy lần?

**Đáp án:** 3 lần, ở [0,2),[1,3),[2,4), có chồng lấp.

**Bài 19.** Trong "ababa", "aba" và "bab" xuất hiện mấy lần?

**Đáp án:** "aba" xuất hiện2, "bab" xuất hiện1.

**Bài 20.** Bài toán contains("") và occurrences("") trong mã được định nghĩa thế nào?

**Đáp án:** contains("")=true theo quy ước empty substring; occurrences("") ném lỗi để không nhầm với occ[root].

**Bài 21.** Công thức ways[v] đếm các đường không rỗng?

**Đáp án:** `ways[v]=Σ_{v--c→u}(1+ways[u])`; distinct count=ways[root].

**Bài 22.** Vì sao có thể tính ways theo len giảm dần?

**Đáp án:** Mọi transition đi tới state có len lớn hơn, nên các giá trị phía sau đã được tính trước.

**Bài 23.** Trong "ababa", substring phân biệt thứ 5 và thứ 9 theo codepoint lexicographic là gì?

**Đáp án:** Thứ5 là "ababa", thứ9 là "baba".

**Bài 24.** Trong kth, vì sao mỗi nhánh c→u có `1+ways[u]` lựa chọn?

**Đáp án:** Có một substring dừng ngay sau c, cộng mọi chuỗi nối thêm một đường không rỗng từ u.

**Bài 25.** Substring xuất hiện lặp lại dài nhất trong "ababa" là gì?

**Đáp án:** "aba" dài3, xuất hiện hai lần (chồng lấp).

**Bài 26.** Substring lặp lại dài nhất của "aaaa" là gì?

**Đáp án:** "aaa" dài3, xuất hiện hai lần ở start0 và1.

**Bài 27.** Chuỗi con chung liên tiếp dài nhất của "banana" và "ananas" là gì?

**Đáp án:** "anana" dài5.

**Bài 28.** Khi LCS scan B mất transition, phải làm gì?

**Đáp án:** Theo suffix links cho đến khi có transition hoặc về root; mỗi bước fallback đặt matched=len[state mới], rồi thử lại ký tự đang đọc.

**Bài 29.** Vì sao không luôn đặt matched=len[state] trong LCS?

**Đáp án:** Một state có thể chứa nhiều substring khác độ dài; hậu tố thực sự đang khớp với B có thể ngắn hơn len[state].

**Bài 30.** Với "a🙂a🙂", có bao nhiêu codepoints, UTF-16 code units và substring phân biệt?

**Đáp án:** 4 codepoints, 6 UTF-16 code units, 7 substring phân biệt.

**Bài 31.** Số state SAM tối đa của một chuỗi dài n≥2?

**Đáp án:** Không quá `2n−1`.

**Bài 32.** Vì sao SAM có O(n) state mà có thể biểu diễn Θ(n²) substring phân biệt?

**Đáp án:** Một state đại diện cho nhiều substring của các độ dài khác nhau, và transition DAG có thể có nhiều đường nhãn khác nhau hội tụ vào một state.

**Bài 33.** Nếu chỉ cần tìm một mẫu trong một văn bản, SAM có luôn là lựa chọn tốt nhất không?

**Đáp án:** Không. KMP hoặc tìm đơn mẫu có thể đơn giản hơn; SAM phù hợp khi một chuỗi nguồn có nhiều truy vấn hoặc cần các thống kê substring toàn cục.

**Bài 34.** Khi ghép "ab#cd", substring "b#c" có thuộc một trong hai chuỗi nguồn không?

**Đáp án:** Không. Nó chỉ tồn tại trong chuỗi ghép; giải nhiều chuỗi phải xử lý ranh giới đúng.

**Bài 35.** Hãy nêu bộ kiểm thử nhỏ để phát hiện lỗi clone/occ.

**Đáp án:** Dùng "abb", "banana", "aaaa", "ababa", chuỗi rỗng và Unicode; liệt kê brute force tất cả substring, so distinct count, frequency của từng nội dung, kth và LCS với chuỗi thứ hai.

## 19. Checklist ghi nhớ

- [ ] Xác định rõ bài hỏi substring liên tiếp, không phải subsequence.
- [ ] Hiểu state là lớp **endpos-equivalence**, không là một substring.
- [ ] Root len=0, link=−1; last là state của toàn bộ prefix hiện tại.
- [ ] Khi extend, tạo cur với len=oldLen+1 và occ ban đầu 1.
- [ ] Đi suffix links để thêm transition thiếu ký tự.
- [ ] Nếu gặp q có len[p]+1==len[q], nối link[cur]=q.
- [ ] Nếu len[p]+1<len[q], tạo clone, sao chép next/link/firstPos và occ=0.
- [ ] Redirect transition c trỏ q đúng chuỗi suffix links, sửa link của q và cur sang clone.
- [ ] Đếm distinct bằng tổng len[v]−len[link[v]], không bằng số state.
- [ ] Đếm occurrences sau khi propagate state counts theo len giảm.
- [ ] Dùng transition từ root để kiểm tra substring và lấy end-state.
- [ ] Đếm đường đi trên DAG: ways[v]=Σ(1+ways[to]).
- [ ] Muốn kth, sắp cạnh theo codepoint, bỏ qua cả nhánh bằng ways.
- [ ] Muốn repeated substring, chọn state có occ≥2 và len lớn nhất.
- [ ] Muốn LCS, quét chuỗi B và giữ matched riêng, fallback suffix links.
- [ ] Với Unicode, thống nhất mọi len/firstPos theo codepoint hoặc đơn vị khác đã chọn.
- [ ] Phân biệt chuỗi rỗng trong membership và occurrence count.
- [ ] Test chuỗi rỗng, dài1, lặp, có clone, emoji và kiểm thử brute force.
- [ ] Chỉ công bố kết quả tối ưu hay độ phức tạp tương ứng với API/cài đặt thực sự dùng.

## Kết luận

**Máy tự động hậu tố** biểu diễn toàn bộ substring của một chuỗi cố định bằng số state và transition chỉ **O(n)**. Ý tưởng cốt lõi không phải lưu mỗi substring thành một node, mà **gom các substring có cùng tập vị trí kết thúc (endpos)** thành một state, với dải độ dài `len(link)+1..len`, dùng **suffix link** để nối các lớp và **clone** khi một lớp phải bị tách sau khi thêm ký tự.

Từ các bất biến đó phát sinh các công thức và thao tác mạnh:

- **Số substring phân biệt:** `Σ(len[v]−len[link[v]])`.
- **Số lần xuất hiện:** propagate occ theo suffix links, rồi tra state kết thúc của query.
- **Thứ k theo thứ tự từ điển:** DP số đường đi trên transition DAG.
- **Substring lặp dài nhất:** chọn state có occ≥2 và len lớn nhất.
- **Longest common substring:** quét chuỗi thứ hai, fallback theo suffix links khi thiếu transition.

Khi học và cài đặt SAM, hãy tập trung hiểu **clone** qua ví dụ "abb" và phân biệt **state / lớp endpos / đường đi từ root**. Đây là chìa khóa để không nhầm số trạng thái với số chuỗi con, và để xử lý đúng frequency, lexicographic ranking và LCS trong các bài **Xử lý chuỗi nâng cao**.
