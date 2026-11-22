# Tìm nhiều mẫu bằng Aho–Corasick

**Aho–Corasick** là thuật toán tìm kiếm **đồng thời nhiều mẫu chuỗi** trong một văn bản. Thay vì chạy phép tìm một mẫu (như KMP) riêng cho từng từ khóa, Aho–Corasick xây dựng một bộ máy trạng thái (*automaton*) từ toàn bộ tập mẫu, sau đó quét văn bản theo một chiều. Bộ máy dùng ba thành phần quan trọng:

1. **Trie:** Lưu các tiền tố chung của các mẫu.
2. **Failure link** (*liên kết thất bại*): Khi ký tự tiếp theo không tiếp tục được đường trie hiện tại, chuyển về tiền tố dài nhất còn có thể khớp với hậu tố của phần đã đọc.
3. **Output link** (*liên kết xuất kết quả*): Tìm nhanh các mẫu khác cũng kết thúc tại vị trí hiện tại vì chúng là **hậu tố** của mẫu dài hơn.

Ứng dụng phổ biến gồm tìm nhiều từ khóa trong văn bản, quét nội dung theo từ điển, phát hiện mẫu chữ ký, phân tích chuỗi và tìm các mẫu được quan tâm trong log. Trong nhóm **Tìm kiếm chuỗi**, đây là công cụ nền tảng khi **số mẫu nhiều**, các mẫu chia sẻ tiền tố/hậu tố, và cần phát hiện **tất cả lần xuất hiện**, kể cả chồng lấp.

Bài học này triển khai Aho–Corasick cho **mẫu không rỗng**, hỗ trợ mẫu trùng nhau dưới những ID riêng, mẫu là hậu tố của mẫu khác, các lần xuất hiện chồng lấp, Unicode theo **code point** và trả vị trí cả theo code point lẫn UTF-16. Chương trình Java 17+ có kiểm thử so với bộ tìm kiếm vét cạn trên **500 trường hợp ngẫu nhiên**.

**Mục tiêu:** Sau bài học, bạn có thể tự dựng trie, tính fail/output links bằng BFS, quét văn bản với các chuyển trạng thái đúng, xuất đầy đủ kết quả mà không đếm trùng, chứng minh tính đúng, phân tích độ phức tạp của cách cài đặt sparse và lựa chọn cách tối ưu phù hợp.

## 1. Phát biểu bài toán

Cho tập hoặc danh sách `P=[p0,p1,...,p(k−1)]` gồm k **mẫu chuỗi**, và văn bản `text` dài T ký tự theo đơn vị đã chọn. Tìm tất cả cặp:

```text
(patternId, startPosition)
```

sao cho đoạn văn bản bắt đầu ở vị trí đó **bằng toàn bộ mẫu** ứng với patternId.

Một kết quả đầy đủ nên xác định:

- **ID mẫu:** ID theo vị trí trong danh sách đầu vào; khi hai mẫu có nội dung giống nhau nhưng ID khác, có thể báo cả hai.
- **Vị trí bắt đầu:** Start của lần xuất hiện.
- **Vị trí kết thúc:** End loại trừ (*half-open interval*).
- **Quy ước đơn vị:** Chỉ số theo code point, UTF-16 code unit, byte hay ký tự theo tiêu chuẩn khác; không trộn các đơn vị.

Nếu kết quả là `[start,end)`, độ dài bằng `end−start` trong **cùng đơn vị đo**.

### 1.1. Ví dụ kinh điển

Danh sách mẫu:

```text
p0 = "he"
p1 = "she"
p2 = "his"
p3 = "hers"

text = "ahishers"
```

Đánh chỉ số bắt đầu từ 0:

```text
Position: 0 1 2 3 4 5 6 7
Text:     a h i s h e r s
```

Các lần xuất hiện đúng:

| Thứ tự phát hiện | Pattern ID | Mẫu | Đoạn [start,end) |
| ---: | ---: | --- | --- |
| 1 | p2 | his | [1,4) |
| 2 | p1 | she | [3,6) |
| 3 | p0 | he | [4,6) |
| 4 | p3 | hers | [4,8) |

Ở vị trí kết thúc `end=6`, **cả "she" và "he"** đều khớp. Nếu chỉ kiểm tra nút hiện tại có kết thúc mẫu "she" hay không mà quên các mẫu ở hậu tố, kết quả sẽ **thiếu "he"**.

**Các lần xuất hiện có thể chồng lấp.** Không được mặc định sau khi tìm thấy một mẫu thì nhảy qua toàn bộ độ dài mẫu ấy, vì làm vậy sẽ bỏ lỡ nhiều kết quả hợp lệ.

### 1.2. Vì sao tìm từng mẫu riêng có thể tốn kém?

Cách trực tiếp: Với từng mẫu p, chạy một phép tìm đơn mẫu trên toàn văn bản. Nếu dùng KMP, tổng thời gian đại khái:

```text
O( SUM length(pattern) + k * T + Z )
```

với Z là tổng số lần xuất hiện cần báo cáo.

Khi k rất lớn, hạng `k*T` trở nên đáng kể. Aho–Corasick **dùng chung phần xử lý văn bản giữa các mẫu**: sau tiền xử lý bộ mẫu, chỉ cần quét text một lần với bộ máy trạng thái.

**Không thể bỏ qua Z:** Nếu số match thực sự là Z, chỉ riêng việc liệt kê đủ Z kết quả đã cần ít nhất Ω(Z) thời gian/bộ nhớ đầu ra. Ví dụ văn bản gồm nhiều ký tự "a" và tập mẫu chứa "a", "aa", "aaa"... có rất nhiều lần xuất hiện chồng lấp.

## 2. Trie: nén các tiền tố chung

**Trie** là cây có gốc; mỗi cạnh mang một đơn vị ký tự (ở mã này là **Unicode code point**). Một đường từ gốc đến một nút biểu diễn một tiền tố của ít nhất một mẫu.

Thêm từng mẫu bằng cách duyệt từng ký tự:

```text
state = root
for each character c in pattern:
    if trie[state] has no edge c:
        create a child node
    state = child(state, c)
mark state as terminal for this pattern ID
```

Với bốn mẫu "he", "she", "his", "hers", hình dung trie:

```text
root
 ├─ h
 │   ├─ e    [p0: "he"]
 │   │   └─ r
 │   │       └─ s    [p3: "hers"]
 │   └─ i
 │       └─ s        [p2: "his"]
 └─ s
     └─ h
         └─ e        [p1: "she"]
```

Mỗi nút lưu:

- `next`: Map từ ký tự/code point đến ID nút con.
- `fail`: ID nút biểu diễn hậu tố thích hợp dài nhất cũng tồn tại trong trie.
- `outputLink`: ID nút **kết thúc mẫu gần nhất** trên chuỗi fail; nếu không có, bằng −1.
- `terminalIds`: các ID mẫu **kết thúc đúng tại nút** này.

**Một nút terminal có thể chứa nhiều ID.** Ví dụ input `["aa","aa"]` có hai mẫu trùng nội dung nhưng ID p0,p1. Trie chỉ cần một đường "a"→"a", nhưng nút cuối lưu `terminalIds=[0,1]`.

### 2.1. Tại sao trie đơn thuần chưa đủ?

Trie hỗ trợ nhận diện mẫu theo một vị trí bắt đầu, nhưng nếu quét text và gặp sai khác, cần biết sẽ quay về đâu để **giữ thông tin hậu tố** đã khớp. Nếu chỉ quay về root và đọc tiếp ký tự mà không xét các hậu tố, có thể bỏ qua mẫu bắt đầu nằm **bên trong đoạn đã quét**.

Aho–Corasick bổ sung fail links để chuyển giữa các tiền tố mà không phải bắt đầu lại việc kiểm tra từ mọi vị trí của text.

## 3. Failure link: giữ hậu tố dài nhất còn hữu ích

Gọi `label(v)` là chuỗi ký tự trên đường từ root đến nút v trong trie. Với nút không phải root, `fail[v]` trỏ đến nút có label bằng **hậu tố thích hợp dài nhất** của `label(v)` mà cũng là **một tiền tố của ít nhất một mẫu**.

“Hậu tố thích hợp” (*proper suffix*) nghĩa là hậu tố **ngắn hơn toàn chuỗi**. Nếu không có hậu tố không rỗng nào là tiền tố của mẫu, fail về root (chuỗi rỗng).

Ví dụ nếu đang ở nút "she", các hậu tố thích hợp của "she" gồm:

```text
"he", "e", ""
```

Vì "he" cũng là một đường trong trie (và là mẫu p0), ta có:

```text
fail[state("she")] = state("he")
```

Nhờ đó khi quét tới ký tự 'e' cuối "she", ta có thể báo luôn **"he"** thông qua chuỗi fail/output.

### 3.1. Ví dụ về khớp một phần sau thất bại

Tưởng tượng đã đọc văn bản đến đoạn làm automaton ở state biểu diễn "ab". Ký tự mới là 'a' nhưng nút "ab" **không có cạnh 'a'**. Nếu trong trie có tiền tố "a", ta có thể theo fail từ "ab" về "a" (nếu "a" là hậu tố thích hợp dài nhất phù hợp của "ab"), rồi kiểm tra ký tự mới. Nếu cần tiếp tục từ root, fail sẽ dẫn dần về root.

Điểm quan trọng không phải chỉ “quay lại vài ký tự”, mà là **biết chính xác hậu tố nào của phần đã xử lý có thể còn là tiền tố của một mẫu**.

### 3.2. Fail của root và con trực tiếp

Theo quy ước:

```text
fail[root] = root

for each direct child v of root:
    fail[v] = root
```

Với các nút sâu hơn, phải tìm hậu tố thích hợp dài nhất tồn tại trong trie. Đây là lý do dùng **BFS theo độ sâu của trie**: khi xử lý một nút, fail của cha và các nút có độ sâu ngắn hơn đã được tính.

### 3.3. Công thức xây fail cho cạnh u --c--> v

Giả sử `f=fail[u]`. Tìm đường nối ký tự c:

```text
f = fail[u]

while f != root AND no trie edge (f, c):
    f = fail[f]

if trie edge (f, c) exists:
    fail[v] = trieChild(f, c)
else:
    fail[v] = root
```

Phần “while” chính là thử các tiền tố có thể biểu diễn **hậu tố ngắn dần** của label(u), xem tiền tố nào có thể nối thêm c. Khi tìm được, label của nút mới là hậu tố thích hợp dài nhất phù hợp của label(v).

**Không được lấy fail[v]=fail[u] một cách máy móc.** Kết quả phải xét **ký tự c** vừa mở rộng, nếu không sẽ mất thông tin hậu tố.

### 3.4. BFS cần thiết như thế nào?

Khi dựng fail[v] cho con v của u, ta cần fail[u] đã biết. BFS xử lý các nút theo độ sâu tăng dần, nên fail[u] của cha chắc chắn đã sẵn sàng.

Nếu duyệt trie bằng DFS tùy tiện rồi tính fail của một nút dựa trên fail của nút khác chưa được thiết lập, có thể tạo liên kết sai. Một cách cài đúng vẫn có thể dùng đệ quy có memoization theo phụ thuộc, nhưng BFS là cách đơn giản và được dùng rộng rãi.

## 4. Output link: không bỏ sót mẫu hậu tố

Tại một vị trí trong text, state hiện tại có thể là nút kết thúc mẫu dài, và **một số nút trên chuỗi fail** cũng kết thúc mẫu ngắn hơn.

Ta cần báo:

1. Các mẫu kết thúc **đúng tại state hiện tại**.
2. Các mẫu kết thúc ở **những hậu tố terminal** của state ấy.

Nếu mỗi lần đều đi toàn bộ fail chain dù không có kết quả, có thể lặp nhiều bước vô ích. Ta lưu `outputLink[v]` trỏ tới nút terminal đầu tiên trên chuỗi fail của v, hoặc −1 nếu không có.

Khi đã tính `fail[v]`:

```text
f = fail[v]

if terminalIds[f] is not empty:
    outputLink[v] = f
else:
    outputLink[v] = outputLink[f]
```

Với các con trực tiếp của root, outputLink=−1 vì **mẫu rỗng bị cấm**, root không phải terminal.

### 4.1. Vì sao output link không phải fail link?

Fail link trỏ tới **tiền tố/hậu tố dài nhất hợp lệ của trie**, nhưng nút ấy **chưa chắc kết thúc mẫu**.

Output link bỏ qua các nút fail **không terminal**, đi thẳng tới **mẫu hậu tố gần nhất** cần xuất. Một automaton có thể cần fail để quyết định chuyển trạng thái nhưng dùng output link để phát kết quả.

Ví dụ:

```text
p0 = "a"
p1 = "ba"
p2 = "aba"

text = "aba"
```

Khi quét tới vị trí end=3:

- State "aba" kết thúc p2.
- Hậu tố "ba" kết thúc p1.
- Hậu tố "a" kết thúc p0.

Phải báo cả ba:

```text
p2 ("aba")@[0,3)
p1 ("ba") @[1,3)
p0 ("a")  @[2,3)
```

Trước đó, ở end=1, đã báo p0 @[0,1). Tổng cộng có **4 lần xuất hiện**.

### 4.2. Mã giữ danh sách terminal riêng, không merge kết quả vào mọi nút

Một cách khác là khi xây fail, gộp toàn bộ output của fail vào output của v. Nó giúp đọc output dễ hơn khi quét, nhưng có thể **sao chép nhiều ID mẫu qua nhiều nút**, tốn thêm bộ nhớ và thời gian tiền xử lý, đặc biệt khi các mẫu là những chuỗi "a", "aa", "aaa"... và chia sẻ rất nhiều hậu tố.

Trong bài này:

- `terminalIds[v]` chỉ chứa ID kết thúc **trực tiếp** tại v.
- `outputLink[v]` dẫn đến **terminal fail** tiếp theo.
- Khi quét, đi từ state đến các outputLink và báo mẫu theo thứ tự.

Cách này không sao chép ID mẫu vào từng trạng thái. Mỗi lần thăm một nút terminal theo outputLink tạo ra ít nhất một match, nên việc báo kết quả có thể tính theo Z, số lần xuất hiện được trả.

## 5. Quét văn bản bằng automaton

Giả sử đã xây trie, fail và output links.

Ban đầu:

```text
state = root
```

Với mỗi code point c trong văn bản, từ trái sang phải:

1. Nếu state hiện tại không có cạnh c, đi theo fail cho đến khi tìm được cạnh c hoặc tới root.
2. Nếu có cạnh c, chuyển qua nút con; nếu root cũng không có cạnh c, ở lại root.
3. Sau khi tiêu thụ **đúng một code point** của text, phát mọi ID mẫu terminal tại state hiện tại.
4. Tiếp tục đi qua outputLink để báo các mẫu là hậu tố.

Giả mã:

```text
state = root
for pos from 0 to T-1:
    c = text[pos]

    while state != root AND no trieEdge(state,c):
        state = fail[state]

    if trieEdge(state,c) exists:
        state = trieChild(state,c)
    else:
        state = root

    // end = pos+1, exclusive
    u = state
    while u != NONE:
        for patternId in terminalIds[u]:
            end = pos+1
            start = end - patternLength[patternId]
            emit(patternId, start, end)

        u = outputLink[u]
```

**Chú ý:** Không tiêu thụ c **mỗi lần theo fail**. Fail là thay đổi **trạng thái máy** trong khi đang xử lý **cùng một ký tự c**. Chỉ khi tìm được một chuyển trie phù hợp hoặc ở root không có cạnh mới đi sang ký tự tiếp theo của text.

### 5.1. Vì sao chỉ một lượt quét vẫn tìm được mọi vị trí bắt đầu?

State automaton ở vị trí i tóm tắt **hậu tố dài nhất của text[0..i] cũng là một tiền tố của mẫu**. Mọi mẫu kết thúc tại i là một hậu tố của text[0..i], nên mẫu ấy tương ứng với **state hiện tại** hoặc **một nút terminal trên chuỗi fail của state**. Output link liệt kê chính xác những nút terminal liên quan.

Vì vậy không cần khởi động một phép so khớp mới tại từng vị trí text; thông tin hậu tố đã được mang theo trong trạng thái.

### 5.2. Độ dài mẫu và vị trí match

Nếu một mẫu dài L code points kết thúc ngay sau ký tự vị trí pos, thì:

```text
endCp   = pos + 1
startCp = endCp - L
```

Đây là khoảng nửa mở `[startCp,endCp)`. Nếu lập trình theo chỉ số ký tự UTF-16 trên String Java, không được nhầm độ dài tính bằng code point với độ dài UTF-16 khi mẫu chứa ký tự ngoài BMP.

## 6. Kết quả chồng lấp và mẫu trùng nhau

### 6.1. Mẫu chồng lấp

Cho:

```text
patterns = ["a", "aa", "aaa"]
text     = "aaaa"
```

Các lần xuất hiện:

| Mẫu | Các đoạn khớp | Số lần |
| --- | --- | ---: |
| "a" | [0,1),[1,2),[2,3),[3,4) | 4 |
| "aa" | [0,2),[1,3),[2,4) | 3 |
| "aaa" | [0,3),[1,4) | 2 |

Tổng **9 match**, dù văn bản chỉ có bốn ký tự. Không được nhảy qua phần vừa khớp như một số kiểu tìm không chồng lấp của hàm tìm kiếm thông thường.

### 6.2. Mẫu trùng nhau là hai ID khác nhau

Nếu input:

```text
p0 = "a"
p1 = "aa"
p2 = "aaa"
p3 = "aa"

text = "aaaa"
```

p1 và p3 **cùng nội dung** nhưng là **hai mẫu đầu vào khác ID**. Nếu yêu cầu báo theo ID mẫu, mỗi lần "aa" xuất hiện tạo một match cho p1 **và** một match cho p3.

Khi ấy số lần theo ID là:

```text
p0 "a"   : 4
p1 "aa"  : 3
p2 "aaa" : 2
p3 "aa"  : 3

Tổng Z = 4+3+2+3 = 12
```

Trong trie, hai mẫu trùng nhau dùng chung nút terminal, nhưng nút đó lưu **hai ID**. Nếu bài yêu cầu tìm các **từ khóa phân biệt theo nội dung**, có thể loại trùng trước khi xây máy và lưu bảng ánh xạ nếu cần báo lại ID gốc; không được âm thầm thay đổi ý nghĩa của kết quả.

### 6.3. Thứ tự kết quả trong mã mẫu

Mã Java bên dưới phát:

1. Các kết quả theo **vị trí kết thúc tăng dần**, vì quét text trái→phải.
2. Ở cùng vị trí kết thúc, mẫu **dài hơn trước**, vì đi từ state terminal sâu nhất qua outputLink tới hậu tố ngắn dần.
3. Nếu nhiều ID trỏ cùng nút terminal (mẫu trùng), phát **theo thứ tự ID đầu vào**.

Đây là một quy ước hữu ích để kiểm thử, **không phải thứ tự bắt buộc** của mọi thư viện Aho–Corasick. Muốn sắp kết quả theo start hoặc theo ID, cần bước sắp riêng hoặc cấu trúc báo cáo phù hợp.

## 7. Unicode và vị trí trong Java

Một `char` của Java là một **UTF-16 code unit**, không luôn là một ký tự Unicode hoàn chỉnh. Một ký tự như emoji 🙂 có code point ngoài BMP nên chiếm **hai char** UTF-16.

Trong bài:

- Trie và automaton chuyển theo **Unicode code point** (int), lấy bằng `String.codePoints()`.
- Độ dài mẫu `lengthCp` là số code points, không phải `String.length()`.
- Kết quả trả cả **startCp/endCp** (chỉ số code point) và **startUtf16/endUtf16** (offset để cắt String Java).
- Ví dụ code dùng `Character.charCount(cp)` để tạo bảng prefix offset UTF-16 cho text.

### 7.1. Ví dụ emoji

Đặt:

```text
smile = "🙂"
text = "a🙂a🙂"

p0 = "🙂"
p1 = "a🙂"
p2 = "🙂a"
p3 = "🙂"    // trùng p0 nhưng ID khác
```

Theo code point, text có 4 phần tử:

```text
Code-point positions:    0    1    2    3
Text:                    a    🙂    a    🙂

UTF-16 offsets:       0    1    3    4    6
```

Bảng offset nghĩa là:

- Code point index0 bắt đầu ở UTF-16 offset0.
- Emoji đầu tiên bắt đầu ở UTF-16 offset1, kết thúc offset3.
- Ký tự "a" thứ hai bắt đầu UTF-16 offset3.
- Emoji cuối bắt đầu offset4 và kết thúc offset6.

Một kết quả p1="a🙂" ở đầu văn bản có:

```text
cp range    = [0,2)
utf16 range = [0,3)
```

Nếu lấy nhầm `endUtf16=startUtf16+lengthCp=2` thì sẽ **cắt dở surrogate pair** của emoji. Cách đúng là ánh xạ cả start/end code-point offset sang UTF-16 offset.

### 7.2. Chuẩn hóa và phân biệt chữ hoa–chữ thường

Aho–Corasick chính xác theo **đơn vị ký tự mà bạn đưa vào automaton**. Nếu yêu cầu tìm không phân biệt hoa/thường hoặc thống nhất Unicode normalization:

1. Chuẩn hóa **cả mẫu lẫn văn bản** theo cùng quy tắc.
2. Xây automaton trên những chuỗi đã chuẩn hóa.
3. Tính match trên chuỗi đã chuẩn hóa.
4. Nếu muốn trả **offset trên văn bản gốc**, cần bảng ánh xạ vị trí sau chuẩn hóa về vị trí gốc, vì Unicode normalization/case folding có thể thay đổi độ dài hoặc số code point.

Không được chỉ lower-case pattern mà giữ text nguyên. Ngoài ra, `String.toLowerCase(Locale.ROOT)` là xử lý chữ thường Unicode theo Java, không phải một quy tắc case folding hoàn hảo cho mọi ngôn ngữ và mọi yêu cầu tìm kiếm.

**Ranh giới từ** cũng không được tự suy ra từ substring. Nếu chỉ muốn match từ độc lập (không match "he" trong "the"), cần định nghĩa/kiểm tra word boundaries riêng, có xét đặc tính Unicode và ngôn ngữ.

### 7.3. Chuỗi chứa surrogate lẻ

Java String có thể chứa surrogate không ghép cặp; `codePoints()` có cách xử lý những code unit ấy theo quy tắc API nhưng chúng không phải Unicode scalar value hợp lệ. Nếu bài toán cần chỉ nhận văn bản Unicode hợp lệ, hãy kiểm tra/chuẩn hóa đầu vào ở tầng tiền xử lý. Mã minh họa giả định chuỗi ứng dụng dùng Unicode hợp lệ.

## 8. Xây liên kết fail bằng BFS: từng bước

Xét trie có các mẫu "he", "she", "his", "hers".

### 8.1. Gốc và con trực tiếp

Root có cạnh 'h' và 's'. Các nút con "h" và "s" đều có fail=root. Chúng chưa thể có một hậu tố không rỗng, ngắn hơn chính chuỗi một ký tự, mà vẫn là tiền tố mẫu.

### 8.2. Nút "sh"

Nút "sh" có cha "s" và ký tự cuối 'h'. Từ fail("s")=root, có cạnh root --'h'--> "h", nên:

```text
fail("sh") = "h"
```

Nghĩa là nếu đã đọc đoạn cuối "sh", hậu tố "h" vẫn hữu ích để nối các ký tự tiếp theo.

### 8.3. Nút "she"

Từ fail("sh")="h", nối ký tự 'e' tồn tại cạnh "h" --'e'--> "he". Vậy:

```text
fail("she") = "he"
```

Vì "he" là terminal của p0, ta có:

```text
outputLink("she") = "he"
```

Khi đọc đoạn "she" trong text, có thể phát p1="she" và sau đó p0="he".

### 8.4. Không phải mọi fail node đều là terminal

Nếu một nút v có fail[v] trỏ đến một tiền tố hợp lệ nhưng **không** kết thúc mẫu, outputLink[v] sẽ tiếp tục đi qua outputLink của fail[v] để tới một terminal sâu hơn trên chuỗi suffix. Việc tách hai loại link cho phép:

- Dùng `fail` để điều hướng khi thiếu cạnh.
- Dùng `outputLink` chỉ để tìm những mẫu thực sự kết thúc.

Nếu không có terminal trên chuỗi fail, outputLink=-1; bước phát kết quả kết thúc.

### 8.5. Tại sao không gộp tất cả output vào terminal node?

Có thể làm, nhưng với các mẫu liên tiếp "a","aa","aaa",... thì số lượng ID mẫu được sao chép dọc theo fail links có thể lớn hơn rất nhiều số mẫu gốc. Dùng output links tiết kiệm **bộ nhớ automaton** và vẫn phát đầy đủ match khi cần.

## 9. Chứng minh tính đúng

### 9.1. Bất biến trạng thái sau mỗi ký tự

Sau khi xử lý ký tự ở vị trí i của text, state biểu diễn:

> **Hậu tố dài nhất của text[0..i] cũng là tiền tố của ít nhất một mẫu trong trie.**

**Cơ sở:** Trước khi đọc văn bản, state=root biểu diễn chuỗi rỗng. Hậu tố rỗng là tiền tố của mọi mẫu.

**Bước quy nạp:** Giả sử state trước khi đọc ký tự c là hậu tố tiền tố dài nhất của đoạn đã đọc. Nếu state có cạnh c, theo trie ta nối được c và thu được hậu tố tiền tố dài hơn đúng cách.

Nếu thiếu cạnh c, một hậu tố mới có thể trở thành tiền tố mẫu chỉ khi hậu tố **trước c** của đoạn đã đọc cũng là tiền tố mẫu. Fail chain liệt kê các hậu tố tiền tố ứng viên theo độ dài giảm dần. Tìm nút đầu tiên có cạnh c cho ta hậu tố tiền tố dài nhất có thể sau khi nối c. Nếu không có, chuyển root.

Vì vậy bất biến đúng sau mỗi ký tự.

### 9.2. Không phát match giả

Mỗi ID trong terminalIds[u] là một mẫu đã được chèn chính xác theo đường trie đến u. Nếu u là state hiện tại hoặc terminal node trên outputLink chain của state, label(u) là hậu tố của đoạn text đã đọc và bằng mẫu. Vị trí start=end−lengthCp xác định đúng đoạn kết thúc tại end. Do đó mọi hit phát ra là một lần xuất hiện thực sự.

### 9.3. Không bỏ sót match

Xét một mẫu p bất kỳ kết thúc tại vị trí end. Vì p là hậu tố của đoạn text[0..end), đồng thời p là đường trong trie, nút terminal của p phải nằm trong danh sách hậu tố tiền tố của state hiện tại. Nếu đó chính là state, ta phát từ terminalIds[state]. Nếu đó là hậu tố ngắn hơn, nó nằm trên chuỗi fail; outputLink nối qua các terminal trên chuỗi ấy và sẽ tới nút của p. Vì vậy mọi match đều được phát.

### 9.4. Không lặp lại một match do cùng một ID

Mỗi nút trie có một độ sâu duy nhất; fail link luôn đi về một trạng thái có độ sâu nhỏ hơn, nên outputLink chain không có chu trình. Một ID mẫu được chèn vào terminal node đúng một lần theo danh sách input. Do đó với một vị trí kết thúc, ID ấy được phát tối đa một lần. Mẫu trùng **có ID khác** vẫn được phát thành các hit khác nhau — đó là chủ đích, không phải đếm trùng sai.

### 9.5. Tính đúng của BFS xây fail

BFS bảo đảm khi xử lý cạnh u --c--> v, fail[u] đã tính đúng. Mọi hậu tố thích hợp của label(v)=label(u)+c mà cũng là tiền tố mẫu đều có dạng suffix(label(u))+c, trong đó suffix(label(u)) là một nút trên chuỗi fail của u (hoặc root). Thử từ fail[u] rồi lui dần bảo đảm nút đầu tiên nối được c có độ sâu lớn nhất, vì fail chain sắp theo độ dài hậu tố giảm. Đó chính là fail[v].

OutputLink[v] được tính từ fail[v], nên theo quy nạp nó trỏ đến terminal gần nhất trên chuỗi fail, hoặc −1. Hai nhóm liên kết được xây đúng.

## 10. Độ phức tạp — phân biệt bản sparse và bản đầy đủ

Đặt:

- `L`: tổng độ dài **tất cả mẫu** tính theo code point.
- `H`: độ dài code point của mẫu dài nhất.
- `K`: số mẫu đầu vào, gồm cả mẫu trùng ID.
- `N`: số nút trie, `N≤L+1`.
- `T`: độ dài văn bản theo code point.
- `Z`: số match thực sự được phát, tính theo **pattern ID**.

### 10.1. Xây trie

Mỗi code point của một mẫu được đưa qua một cạnh trie, nên với Map tra cứu trung bình O(1):

```text
Xây trie: O(L) thời gian kỳ vọng
Bộ nhớ nút/cạnh: O(L)
Lưu terminal IDs: O(K)
```

Nếu K=0, trie chỉ có root và tìm trên text cho kết quả rỗng.

### 10.2. Xây failure/output links kiểu sparse của mã Java

Mã dùng `HashMap<Integer,Integer>` cho cạnh đi ra và khi tìm fail[v] có vòng while chạy dọc fail chain. Chi phí cho **một cạnh trie** có thể đến O(H) trong trường hợp xấu nếu phải thử nhiều hậu tố. Do đó một cận trên **bảo thủ và đúng cho cài đặt sparse này**:

```text
BFS fail/output construction:
    O(L * H) thao tác Map trong trường hợp xấu
    O(L) bộ nhớ links
```

Nhiều trình bày nêu tiền xử lý Aho–Corasick O(L×|Σ|), hoặc O(L) khi alphabet cố định và chuyển trạng thái/automaton được biểu diễn thích hợp. Cần phân biệt: nếu lưu **bảng chuyển đầy đủ** ở mọi nút (hoặc có kỹ thuật memoized goto đúng), ta có thể đạt tiền xử lý tuyến tính theo kích thước bảng/bộ máy, đổi lại tốn bộ nhớ khoảng O(N×|Σ|) cho bảng dense.

**Không nên tuyên bố cài đặt HashMap sparse trong bài luôn xây fail O(L) bất kể mọi chuỗi mẫu**, vì vòng fallback ở mỗi cạnh trie không được memo hóa thành bảng chuyển đầy đủ.

### 10.3. Quét text

Mỗi bước trie thành công tăng độ sâu state tối đa 1; mỗi lần theo fail giảm độ sâu ít nhất1. Trên toàn văn bản, số lần đi fail do thiếu cạnh được **khống chế amortized O(T)**, vì độ sâu không âm. Với Map tra cứu kỳ vọng O(1), phần điều hướng tốn:

```text
O(T) thời gian kỳ vọng
```

Mỗi lần đi outputLink đến nút terminal tạo ít nhất một kết quả, nên tổng chi phí phát match là O(Z). Vì vậy:

```text
Quét + phát kết quả: O(T + Z) kỳ vọng
```

Đây là lợi ích quan trọng nhất: thay vì quét text K lần, ta xử lý text một lần bằng automaton, cộng thời gian tương xứng số kết quả thực sự.

### 10.4. Bộ nhớ trong chương trình hoàn chỉnh

Automaton: O(L+K) cho trie, links, terminal IDs, lengths và patterns. Để trả tất cả Hit, mã còn lưu:

- Mảng code point của text: O(T).
- Bảng offset UTF-16 prefix: O(T).
- Danh sách Z kết quả: O(Z).

Vậy bộ nhớ tổng của **bản chương trình trả List<Hit>** là:

```text
O(L + K + T + Z)
```

Nếu thay vì giữ tất cả Hit, ta dùng một callback/consumer phát từng match và xử lý ngay, có thể tránh O(Z) bộ nhớ lưu kết quả. Muốn quét streaming không giữ toàn bộ text hoặc offset prefix, cần thiết kế thêm cơ chế duy trì offset toàn cục và trạng thái máy giữa các chunk, như phần 12.

### 10.5. Trường hợp Z lớn

Nếu text="aaaa...a" dài T và patterns=["a","aa",...,"a"*H], tổng số match có thể là:

```text
Z = SUM_{len=1..H} max(0,T-len+1)
```

khi H≤T:

```text
Z = H*(T+1) - H*(H+1)/2
```

Z có thể đạt Θ(T*H), dù quét text chỉ cần T code points. Không thể tối ưu thời gian xuất tất cả match xuống O(T) nếu **đề yêu cầu liệt kê toàn bộ Z kết quả**. Nếu chỉ hỏi “có ít nhất một mẫu xuất hiện không?”, “bao nhiêu ID mẫu khác nhau được gặp?” hoặc tổng số lần, có thể tối ưu cách thu thập/đếm tùy bài toán.

## 11. Chương trình Java 17+ hoàn chỉnh

Tệp: **`AhoCorasickDemo.java`**.

Lựa chọn cài đặt:

- Dùng các code points Unicode kiểu int thay vì char của Java.
- Root có ID0, các nút còn lại đánh số tăng khi chèn trie.
- Mỗi nút có Map ký tự→nút con, List pattern ID terminal, fail, outputLink.
- Xây fail/output links bằng BFS; duyệt Map sparse thay vì bảng ký tự cố định.
- Tìm tất cả match; trả cả vị trí code point và offset UTF-16.
- Mẫu trùng nội dung giữ **ID riêng**, không loại trùng ngầm.
- **Mẫu rỗng bị từ chối** để tránh việc phải định nghĩa match ở mọi ranh giới; danh sách không có mẫu thì hợp lệ, trả danh sách kết quả rỗng.
- Văn bản rỗng trả kết quả rỗng với mọi mẫu không rỗng.
- Thứ tự phát: vị trí kết thúc tăng dần, mẫu dài hơn trước ở cùng end, mẫu trùng theo ID đầu vào.
- Bản kiểm thử độc lập dùng brute force để so sánh **toàn bộ danh sách Hit**, không chỉ số lượng.

### 11.1. Mã chạy độc lập

```java
import java.util.*;
import java.util.stream.*;

public class AhoCorasickDemo {
    record Hit(
            int patternId, String pattern,
            int startCp, int endCp,
            int startUtf16, int endUtf16) {}

    static final class Node {
        final Map<Integer, Integer> next = new HashMap<>();
        final List<Integer> terminalIds = new ArrayList<>();
        int fail = 0;
        int outputLink = -1;
    }

    static final class Automaton {
        private final List<Node> nodes = new ArrayList<>();
        private final List<String> patterns;
        private final int[] lengths;

        Automaton(List<String> input) {
            Objects.requireNonNull(input, "patterns");
            for (String p : input) {
                Objects.requireNonNull(p, "pattern must not be null");
                if (p.isEmpty()) {
                    throw new IllegalArgumentException(
                            "empty pattern is not supported");
                }
            }
            patterns = List.copyOf(input);
            lengths = new int[patterns.size()];
            nodes.add(new Node()); // root = state 0

            for (int id = 0; id < patterns.size(); id++) {
                int[] units = patterns.get(id).codePoints().toArray();
                lengths[id] = units.length;
                int state = 0;
                for (int cp : units) {
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
            buildFailureLinks();
        }

        private void buildFailureLinks() {
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            // Root's immediate children have fail=root.
            for (int child : nodes.get(0).next.values()) {
                nodes.get(child).fail = 0;
                nodes.get(child).outputLink = -1;
                queue.addLast(child);
            }

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                for (Map.Entry<Integer, Integer> edge
                        : nodes.get(u).next.entrySet()) {
                    int cp = edge.getKey();
                    int v = edge.getValue();
                    int fallback = nodes.get(u).fail;

                    while (fallback != 0
                            && !nodes.get(fallback)
                                    .next.containsKey(cp)) {
                        fallback = nodes.get(fallback).fail;
                    }

                    Integer candidate =
                            nodes.get(fallback).next.get(cp);
                    int f = candidate == null ? 0 : candidate;

                    nodes.get(v).fail = f;
                    Node suffix = nodes.get(f);
                    nodes.get(v).outputLink =
                            !suffix.terminalIds.isEmpty()
                                    ? f : suffix.outputLink;
                    queue.addLast(v);
                }
            }
        }

        int stateCount() {
            return nodes.size();
        }

        List<Hit> search(String text) {
            Objects.requireNonNull(text, "text");
            int[] cps = text.codePoints().toArray();
            int[] offset = new int[cps.length + 1];

            for (int i = 0; i < cps.length; i++) {
                offset[i + 1] = offset[i]
                        + Character.charCount(cps[i]);
            }

            List<Hit> hits = new ArrayList<>();
            int state = 0;
            for (int pos = 0; pos < cps.length; pos++) {
                int cp = cps[pos];

                while (state != 0
                        && !nodes.get(state)
                                .next.containsKey(cp)) {
                    state = nodes.get(state).fail;
                }
                Integer next = nodes.get(state).next.get(cp);
                state = next == null ? 0 : next;

                // Longest suffix first, then shorter terminal
                // suffixes through outputLink. Duplicates preserved.
                for (int u = state; u != -1;
                        u = nodes.get(u).outputLink) {
                    for (int id : nodes.get(u).terminalIds) {
                        int endCp = pos + 1;
                        int startCp = endCp - lengths[id];
                        hits.add(new Hit(
                                id, patterns.get(id),
                                startCp, endCp,
                                offset[startCp], offset[endCp]));
                    }
                }
            }
            return hits;
        }
    }

    static String shortHits(List<Hit> hits) {
        return hits.stream()
                .map(h -> "p" + h.patternId()
                        + "(" + h.pattern() + ")@["
                        + h.startCp() + "," + h.endCp() + ")")
                .toList().toString();
    }

    static String unicodeHits(List<Hit> hits) {
        return hits.stream()
                .map(h -> "p" + h.patternId()
                        + "@cp[" + h.startCp()
                        + "," + h.endCp()
                        + ")/utf16[" + h.startUtf16()
                        + "," + h.endUtf16() + ")")
                .toList().toString();
    }

    static int[] counts(List<Hit> hits, int patternCount) {
        int[] result = new int[patternCount];
        for (Hit hit : hits) {
            result[hit.patternId()]++;
        }
        return result;
    }

    // Independent brute-force oracle, including duplicate IDs.
    static List<Hit> brute(List<String> patterns, String text) {
        int[] cps = text.codePoints().toArray();
        int[] offset = new int[cps.length + 1];
        for (int i = 0; i < cps.length; i++) {
            offset[i + 1] = offset[i]
                    + Character.charCount(cps[i]);
        }

        List<Hit> result = new ArrayList<>();
        for (int end = 1; end <= cps.length; end++) {
            List<Hit> atEnd = new ArrayList<>();
            for (int id = 0; id < patterns.size(); id++) {
                int[] p = patterns.get(id).codePoints().toArray();
                int start = end - p.length;
                if (start < 0) {
                    continue;
                }

                boolean equal = true;
                for (int j = 0; j < p.length; j++) {
                    if (cps[start + j] != p[j]) {
                        equal = false;
                        break;
                    }
                }
                if (equal) {
                    atEnd.add(new Hit(
                            id, patterns.get(id),
                            start, end, offset[start], offset[end]));
                }
            }
            atEnd.sort(
                    Comparator.<Hit>comparingInt(
                            h -> h.endCp() - h.startCp())
                            .reversed()
                            .thenComparingInt(Hit::patternId));
            result.addAll(atEnd);
        }
        return result;
    }

    static void randomizedCrossCheck() {
        Random rng = new Random(20261110L);
        String alphabet = "abc";

        for (int trial = 0; trial < 500; trial++) {
            int textLength = rng.nextInt(15);
            StringBuilder text = new StringBuilder();
            for (int i = 0; i < textLength; i++) {
                text.append(alphabet.charAt(
                        rng.nextInt(alphabet.length())));
            }

            int count = rng.nextInt(7);
            List<String> patterns = new ArrayList<>();
            for (int id = 0; id < count; id++) {
                int length = 1 + rng.nextInt(5);
                StringBuilder p = new StringBuilder();
                for (int k = 0; k < length; k++) {
                    p.append(alphabet.charAt(
                            rng.nextInt(alphabet.length())));
                }
                patterns.add(p.toString());
            }

            List<Hit> actual =
                    new Automaton(patterns).search(text.toString());
            List<Hit> expected =
                    brute(patterns, text.toString());
            if (!actual.equals(expected)) {
                throw new AssertionError(
                        "trial " + trial
                        + " text=" + text
                        + " patterns=" + patterns
                        + " actual=" + actual
                        + " expected=" + expected);
            }
        }
        System.out.println(
                "Random cross-check: PASS (500 cases)");
    }

    public static void main(String[] args) {
        List<String> classicPatterns =
                List.of("he", "she", "his", "hers");
        Automaton classic = new Automaton(classicPatterns);
        System.out.println(
                "Classic states: " + classic.stateCount());
        System.out.println(
                "Classic hits: "
                        + shortHits(classic.search("ahishers")));

        List<String> overlapPatterns =
                List.of("a", "aa", "aaa", "aa");
        Automaton overlap = new Automaton(overlapPatterns);
        List<Hit> overlaps = overlap.search("aaaa");
        System.out.println(
                "Overlap hits: " + overlaps.size()
                + " counts=" + Arrays.toString(
                        counts(overlaps, overlapPatterns.size())));
        System.out.println(
                "Overlap text aaa: "
                        + shortHits(overlap.search("aaa")));

        List<String> suffixPatterns =
                List.of("a", "ba", "aba");
        System.out.println(
                "Suffix hits: "
                        + shortHits(new Automaton(suffixPatterns)
                                .search("aba")));

        String smile =
                new String(Character.toChars(0x1F642));
        List<String> unicodePatterns =
                List.of(smile, "a" + smile, smile + "a", smile);
        Automaton unicode = new Automaton(unicodePatterns);
        System.out.println(
                "Unicode hits: "
                        + unicodeHits(unicode.search(
                                "a" + smile + "a" + smile)));

        System.out.println(
                "No patterns: "
                        + new Automaton(List.of())
                                .search("abc").size());
        System.out.println(
                "Empty text: "
                        + classic.search("").size());

        try {
            new Automaton(List.of("a", ""));
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Empty pattern rejected: " + ex.getMessage());
        }

        randomizedCrossCheck();
    }
}
```

### 11.2. Biên dịch và chạy

Dùng **JDK 17 trở lên**. Lưu nội dung mã vào đúng tệp:

```bash
javac AhoCorasickDemo.java
java AhoCorasickDemo
```

**Stdout chính xác:**

```text
Classic states: 10
Classic hits: [p2(his)@[1,4), p1(she)@[3,6), p0(he)@[4,6), p3(hers)@[4,8)]
Overlap hits: 12 counts=[4, 3, 2, 3]
Overlap text aaa: [p0(a)@[0,1), p1(aa)@[0,2), p3(aa)@[0,2), p0(a)@[1,2), p2(aaa)@[0,3), p1(aa)@[1,3), p3(aa)@[1,3), p0(a)@[2,3)]
Suffix hits: [p0(a)@[0,1), p2(aba)@[0,3), p1(ba)@[1,3), p0(a)@[2,3)]
Unicode hits: [p1@cp[0,2)/utf16[0,3), p0@cp[1,2)/utf16[1,3), p3@cp[1,2)/utf16[1,3), p2@cp[1,3)/utf16[1,4), p1@cp[2,4)/utf16[3,6), p0@cp[3,4)/utf16[4,6), p3@cp[3,4)/utf16[4,6)]
No patterns: 0
Empty text: 0
Empty pattern rejected: empty pattern is not supported
Random cross-check: PASS (500 cases)
```

### 11.3. Giải thích output

**Classic states: 10:** Có 10 nút trie, gồm root và các nút tương ứng tiền tố duy nhất của "he","she","his","hers". Bộ máy có thể có nhiều nút hơn số mẫu vì một mẫu dài đi qua nhiều nút.

**Classic hits:** Tìm "his" [1,4), "she" [3,6), "he" [4,6) và "hers" [4,8). Ở end=6, "she" được báo trước "he" vì dài hơn. Nếu bỏ outputLink, "he" có thể bị thiếu tại vị trí này.

**Overlap hits:** Với patterns=["a","aa","aaa","aa"], text="aaaa", có **12 match**, số lần mỗi ID là [4,3,2,3]. Mẫu p1 và p3 đều "aa" nên mỗi lần của chuỗi "aa" phải báo hai ID.

**Overlap text aaa:** In đầy đủ các đoạn để thấy thứ tự phát: end=1 có "a"; end=2 có hai "aa" rồi "a"; end=3 có "aaa", hai "aa" rồi "a". Không bỏ match chồng lấp.

**Suffix hits:** Với "a","ba","aba" trên "aba", ở end=3 báo cả ba mẫu đang là hậu tố: "aba","ba","a"; tính cả "a" ở end=1 tổng 4 hit.

**Unicode hits:** Mỗi ID báo đoạn code point và đoạn UTF-16 chính xác. Emoji 🙂 chiếm một code point nhưng hai UTF-16 code units. Các mẫu trùng emoji p0 và p3 được báo riêng.

**No patterns:** Danh sách mẫu rỗng là hợp lệ; trie chỉ có root, search trả 0 hit. Điều này **khác** trường hợp input chứa **một mẫu chuỗi rỗng**.

**Empty text:** Không có vị trí nào để một mẫu không rỗng kết thúc, nên trả 0 hit.

**Empty pattern rejected:** Mẫu rỗng bị từ chối có chủ đích. Nếu muốn hỗ trợ mẫu rỗng, phải tự định nghĩa nó xuất hiện tại **T+1 ranh giới** của text hay theo quy tắc khác và bổ sung logic riêng; không để mặc định terminal root rồi quét như các mẫu khác.

**Random cross-check:** Với seed cố định, sinh 500 test nhỏ trên alphabet "abc", gồm văn bản rỗng, danh sách mẫu rỗng, mẫu trùng, mẫu lồng nhau và mẫu chồng lấp. Mỗi test so **toàn bộ danh sách Hit** với brute force, gồm ID, start/end code point, start/end UTF-16 và thứ tự. Nếu sai một trường hợp, chương trình ném AssertionError, không in PASS.

### 11.4. Vì sao code giữ raw Node map thay vì bảng 26 chữ cái?

Mã dùng `Map<Integer,Integer>` để hỗ trợ Unicode code points, không ép input vào alphabet cố định 'a'..'z'. Nếu bài chỉ có 26 chữ cái ASCII thường, có thể dùng `int[26]` trong mỗi Node để tra cứu nhanh và giảm hằng số, đánh đổi bộ nhớ theo số nút×26. Với byte alphabet 256 hoặc bảng codepoint lớn, một trie sparse thường tiết kiệm bộ nhớ ở những nút ít con.

**Đừng dùng `int[65536]` cho mỗi Node** một cách thiếu cân nhắc: số nút có thể rất lớn, bộ nhớ sẽ phình mạnh. Unicode đầy đủ còn có những code points vượt 65535.

## 12. Quét nhiều chunk và phát kết quả streaming

Aho–Corasick phù hợp xử lý một luồng văn bản lớn vì automaton chỉ cần **state hiện tại** để tiếp tục. Có thể giữ:

- Trạng thái automaton sau chunk trước.
- Vị trí code point toàn cục đã tiêu thụ.
- Nếu cần UTF-16 offsets, vị trí UTF-16 toàn cục và đủ dữ liệu để tính start offset của match.
- Các kết quả đã phát hoặc một callback nhận kết quả ngay.

**Không reset state về root ở đầu mỗi chunk.** Nếu mẫu bắt đầu ở cuối chunk A và kết thúc ở đầu chunk B, reset sẽ làm mất kết quả xuyên ranh giới.

Ví dụ:

```text
pattern = "abcd"
chunk1 = "xxab"
chunk2 = "cdyy"
```

Sau chunk1, automaton đang ở trạng thái biểu diễn "ab". Giữ trạng thái này khi quét chunk2 cho phép báo "abcd" qua ranh giới chunk.

### 12.1. Những điều cần giữ thêm khi muốn trả start offset

Nếu chỉ cần patternId và end position, state + bộ đếm end toàn cục thường đủ. Nếu cần start/end codepoint, tính start=end−patternLength. Nếu cần **start UTF-16 offset** trong một luồng mà không giữ toàn bộ văn bản, cần giữ thông tin chiều dài UTF-16 của **H codepoints gần nhất** (hoặc một bộ đệm vị trí vòng đủ dài H+1). Chỉ có tổng UTF-16 offset hiện tại và độ dài **code point** của mẫu không đủ nếu mẫu chứa surrogate pairs.

Ngoài ra, khi chia input thành chunk Java String, một cặp surrogate có thể bị **cắt giữa hai chunk**. Bộ giải streaming đúng phải ghép/xử lý trạng thái codepoint decoder qua ranh giới ấy, không đơn giản gọi codePoints() độc lập cho từng chunk nếu có nguy cơ surrogate bị tách đôi.

### 12.2. Bản mã Java này không phải scanner streaming

Phương thức `search(String text)` trong chương trình tạo mảng code point và prefix UTF-16 offsets của **cả text**, rồi trả List<Hit>. Nó **chưa cung cấp API feed(chunk)**, vì vậy không được tuyên bố nó đang dùng O(H) bộ nhớ scanner. Phần streaming là hướng mở rộng khi xử lý file rất lớn, log dài hoặc dữ liệu đến theo mạng.

## 13. Các biến thể bài toán thường gặp

### 13.1. Chỉ cần biết mẫu nào từng xuất hiện

Nếu chỉ cần trả danh sách ID mẫu có ít nhất một match, không nhất thiết giữ mọi Hit. Có thể đánh dấu seen[id] khi phát terminal, rồi trả các ID đã thấy. Chi phí quét vẫn chịu ảnh hưởng của cách duyệt outputLink; có thể tối ưu thêm bằng cấu trúc báo từng mẫu một lần, nhưng phải bảo toàn semantics của các mẫu trùng ID.

### 13.2. Đếm số lần của từng mẫu

Với `counts[id]++` mỗi khi phát ID, ta có số lần xuất hiện (kể cả chồng lấp). Trên text="aaaa", mẫu "aa" xuất hiện **ba** lần, không phải hai. Dùng long nếu T lớn và tổng nhiều lần xuất hiện có thể vượt int.

Nếu số mẫu rất lớn và có nhiều terminal hậu tố, đôi khi có thể tối ưu **đếm** bằng số lần truy cập state rồi truyền tổng theo cây fail thay vì phát từng match; nhưng phải triển khai đúng thứ tự chuyển góp và ánh xạ terminal ID. Không được dùng kỹ thuật đếm đó thay cho bài **liệt kê chính xác mọi vị trí** nếu yêu cầu có start/end.

### 13.3. Chỉ cần match sớm nhất

Nếu đề chỉ cần sự tồn tại của một match, có thể dừng quét ngay khi gặp một terminal hoặc outputLink tới terminal. Nhưng nếu yêu cầu **match có vị trí bắt đầu nhỏ nhất**, “match đầu tiên theo end tăng dần” chưa chắc có start nhỏ nhất: một mẫu dài có thể bắt đầu sớm nhưng kết thúc sau một mẫu ngắn bắt đầu muộn. Phải định nghĩa thứ tự ưu tiên và tổ chức logic phù hợp.

### 13.4. Match từ độc lập

Aho–Corasick tìm **substring**, không tự yêu cầu word boundary. "he" có thể được báo trong "the". Muốn chỉ lấy từ hoàn chỉnh, thêm bộ lọc trước/sau vị trí match theo quy tắc tách từ của ứng dụng; nếu cần xét ký tự **sau end**, có thể phải trì hoãn quyết định báo match cho tới khi đọc thêm ký tự hoặc tới cuối văn bản.

### 13.5. Trọng số mẫu, ưu tiên và điểm số

Nếu mỗi mẫu có trọng số, có thể cộng điểm khi mẫu xuất hiện, hoặc chọn mẫu theo mức độ ưu tiên. Lúc này phải xác định **có cộng mọi match chồng lấp không**, có tính một pattern nhiều lần không, và cách xử lý duplicates. Automaton chỉ cung cấp các lần xuất hiện; **logic tổng hợp điểm** là lớp bài toán riêng.

### 13.6. Từ điển thay đổi liên tục

Aho–Corasick tiêu chuẩn xây automaton sau khi biết tập mẫu. Khi thêm/xóa mẫu, fail/output links có thể thay đổi; không thể chỉ thêm một cạnh trie rồi giữ nguyên tất cả liên kết như thể bộ máy vẫn đúng. Với từ điển thay đổi nhiều, cân nhắc xây lại theo lô, các nhóm automaton hoặc một cấu trúc động chuyên biệt.

## 14. Phân biệt Aho–Corasick với các kỹ thuật khác

| Kỹ thuật | Tác vụ chính | Cách hoạt động |
| --- | --- | --- |
| **Naive matching** | Một hoặc vài mẫu rất nhỏ | So trực tiếp mọi điểm bắt đầu |
| **KMP** | Một mẫu trong một văn bản | Dùng prefix function/failure để tránh so lại |
| **Rabin–Karp** | Tìm mẫu bằng hashing | So hash đoạn, xác minh khi cần để tránh collision |
| **Trie** | Lưu nhiều chuỗi và tiền tố | Theo cạnh từ root, chưa đủ để quét text tối ưu |
| **Aho–Corasick** | Nhiều mẫu trên một văn bản | Trie + fail + output, quét theo automaton |
| **Suffix array / suffix automaton** | Nhiều truy vấn trên một văn bản cố định | Tiền xử lý **văn bản** thay vì bộ mẫu |
| **Regex engine** | Ngôn ngữ mẫu linh hoạt hơn | Hỗ trợ ký hiệu lặp/lựa chọn/ràng buộc; thuật toán tùy engine |

### 14.1. Liên hệ với KMP

KMP cho **một mẫu** dùng thông tin tiền tố/hậu tố để biết có thể tiếp tục ở đâu khi sai khác. Aho–Corasick mở rộng ý tưởng ấy lên **một trie chứa nhiều mẫu**, với fail link đưa trạng thái về tiền tố chung phù hợp.

Không nên đồng nhất mọi link fail của Aho–Corasick với việc “lùi một ký tự” trong KMP. Chúng biểu diễn **trạng thái tiền tố khác nhau trên một trie**, và cần BFS để thiết lập đầy đủ.

### 14.2. Khi nên dùng suffix array thay vì Aho–Corasick?

Nếu văn bản rất lớn nhưng **cố định**, còn nhiều truy vấn mẫu đến **sau**, có thể tiền xử lý text thành suffix array, suffix automaton hoặc cấu trúc chỉ mục khác. Nếu tập **mẫu cố định** và cần quét nhiều văn bản/luồng khác nhau, xây một automaton Aho–Corasick rồi dùng lại thường thuận tiện.

Đây không phải quy tắc tuyệt đối; lựa chọn tùy yêu cầu vị trí, số truy vấn, độ dài dữ liệu, alphabet và tài nguyên.

## 15. Những lỗi thường gặp

1. **Chỉ xây trie rồi quét một lần mà không có fail links.** Có thể bỏ mẫu bắt đầu giữa vùng đã đọc khi gặp mismatch.
2. **Tính fail[v]=fail[parent[v]] mà quên ký tự cạnh cuối.** Fail phải tìm hậu tố có thể nối chính ký tự ấy.
3. **Dùng DFS tùy ý khi các fail phụ thuộc chưa có.** BFS theo độ sâu là cách trực tiếp để bảo đảm phụ thuộc được tính trước.
4. **Đặt fail của con root trỏ chính nó.** Có thể tạo vòng lặp khi thiếu cạnh; con root phải fail về root.
5. **Đi fail nhưng đồng thời tăng vị trí text.** Phải thử lại **cùng ký tự** khi thay state.
6. **Ở root thiếu cạnh mà vẫn truy cập child null.** Khi root không có cạnh, state giữ root rồi chuyển sang ký tự tiếp theo.
7. **Chỉ báo mẫu terminal tại state hiện tại.** Bỏ các mẫu hậu tố như "he" sau "she".
8. **Đi tất cả fail states để phát mẫu mà không kiểm tra terminal, gây thao tác thừa.** Dùng outputLink đến các terminal nếu muốn tối ưu báo kết quả.
9. **Gộp tất cả output vào mọi node mà không tính bộ nhớ.** Nhiều mẫu là hậu tố của nhau có thể tạo rất nhiều ID được sao chép.
10. **Nhầm fail link và output link.** Fail phục vụ điều hướng; outputLink phục vụ phát mẫu hậu tố.
11. **Quên báo những mẫu trùng nội dung nhưng khác ID.** Nếu input là danh sách ID, phải phát cả các ID.
12. **Báo cùng một ID hai lần ở cùng end do tự merge output rồi vẫn đi outputLink.** Chọn một chiến lược phát hoặc khử trùng đúng cách.
13. **Chỉ cho một terminal ID trên mỗi nút.** Không hỗ trợ mẫu trùng theo ID.
14. **Dùng vị trí kết thúc inclusive trong khi công thức lại dùng exclusive.** Start/end sai một đơn vị.
15. **Tính start=end−String.length() khi đang quét code point.** Chuỗi ngoài BMP có UTF-16 length khác code point length.
16. **Trộn vị trí byte với vị trí char/UTF-16/codepoint.** Không thể tự chuyển đổi bằng cộng một hằng số.
17. **Dùng `charAt` rồi coi mỗi char là một ký tự Unicode.** Ký tự ngoài BMP có surrogate pair.
18. **Không chuẩn hóa cả pattern và text theo cùng quy tắc.** Có thể bỏ match hoặc so nhầm.
19. **Chuẩn hóa Unicode rồi trả offset như thể độ dài không đổi.** Cần bảng ánh xạ về text gốc.
20. **Ngầm coi tìm substring là tìm nguyên từ.** Aho–Corasick không tự kiểm tra word boundaries.
21. **Bỏ match chồng lấp bằng cách nhảy pos qua độ dài mẫu vừa tìm.** Sai nếu đề yêu cầu mọi lần xuất hiện.
22. **Không hỗ trợ text rỗng.** Với mẫu không rỗng, kết quả rỗng, không có lỗi.
23. **Mặc định mẫu rỗng là một match duy nhất mà không định nghĩa vị trí.** Cần chính sách rõ; code này từ chối.
24. **Bỏ trường hợp danh sách mẫu rỗng.** Kết quả hợp lệ là danh sách Hit rỗng.
25. **Dùng alphabet 26 chữ cái cho input Unicode bất kỳ.** Phần lớn codepoint ngoài 'a'..'z' sẽ không biểu diễn được.
26. **Cấp phát bảng 65536 cạnh cho mọi Node mà không xét bộ nhớ.** Có thể gây OOM và vẫn không hỗ trợ đầy đủ Unicode ngoài BMP.
27. **Cho rằng HashMap iteration order cố định là quy tắc output.** Nó không được bảo đảm; output trong code dựa trên tiến trình text và outputLink, không dựa vào thứ tự HashMap BFS.
28. **Không tính thời gian theo số kết quả Z.** Chỉ liệt kê Z match đã cần Ω(Z).
29. **Tuyên bố bản sparse build fail luôn O(L) mà bỏ qua vòng duyệt fail tại mỗi cạnh trie.** Có thể cần O(LH) trong cận xấu nếu chưa memoize goto.
30. **Nhầm trie nodes và số mẫu.** Một mẫu dài tạo nhiều state; số node có thể lên tới L+1.
31. **Đếm tổng Z rồi cho rằng đó là số mẫu phân biệt xuất hiện.** Một pattern có thể match nhiều lần; hai mẫu trùng ID khác cũng khác nhau.
32. **Reset automaton về root mỗi chunk trong streaming.** Bỏ match bắt đầu ở chunk trước và kết thúc ở chunk sau.
33. **Chia String chunk giữa surrogate pair rồi gọi codePoints độc lập.** Có thể làm sai các codepoints và offset.
34. **Dùng outputLink của một node trước khi fail/output của suffix node được tính.** Cần xây theo BFS.
35. **Không phân biệt end position của text đã tiêu thụ và vị trí state trong trie.** State lưu tiền tố/hậu tố, không phải chỉ số text.
36. **Sửa các pattern sau khi dựng máy nhưng không xây lại links.** Automaton không còn tương ứng từ điển.
37. **Dùng một object mutable để làm key Map codepoints mà không giữ ổn định.** Có thể khiến chuyển trạng thái tìm sai.
38. **Chỉ thử mẫu không có chung tiền tố.** Không kiểm tra khả năng nén trie và fail.
39. **Chỉ thử mẫu không có quan hệ hậu tố.** Không kiểm tra outputLink.
40. **Chỉ thử chuỗi không có ký tự lặp.** Không kiểm tra chồng lấp, self-similar patterns và các fail chain dài.
41. **Giả sử mọi match phải được sắp theo start.** Bản quét online tự nhiên theo end tăng; muốn start tăng cần thêm bước.
42. **Cho rằng match đầu tiên theo end cũng có start nhỏ nhất.** Với nhiều độ dài mẫu, hai thứ tự có thể khác.
43. **Không giữ ánh xạ pattern ID khi loại trùng/chuẩn hóa.** Khó trả kết quả đúng theo đề.
44. **Dùng int cho tổng số match cực lớn khi chỉ cần đếm.** Nên cân nhắc long hoặc BigInteger theo miền dữ liệu.
45. **Không kiểm thử với oracle độc lập.** Lỗi fail/output thường lộ ở vài tổ hợp tiền tố/hậu tố khó đoán.

## 16. Bài tập tự luyện có đáp án

**Bài 1.** Aho–Corasick giải bài toán gì?

**Đáp án:** Tìm đồng thời nhiều mẫu trên một văn bản, có thể phát tất cả lần xuất hiện theo mẫu ID và vị trí, kể cả chồng lấp.

**Bài 2.** Ba thành phần cốt lõi của bộ máy là gì?

**Đáp án:** Trie, failure links và output/terminal reporting (thường có output links để đi nhanh tới hậu tố terminal).

**Bài 3.** Trong trie, mỗi nút biểu diễn điều gì?

**Đáp án:** Chuỗi label trên đường từ root tới nút, tức một tiền tố của ít nhất một mẫu.

**Bài 4.** Vì sao cần fail links?

**Đáp án:** Khi thiếu cạnh nối ký tự c tại state hiện tại, fail tìm hậu tố dài nhất còn có thể là tiền tố mẫu để tiếp tục **cùng ký tự c**, tránh bỏ các mẫu bắt đầu ở giữa đoạn đã đọc.

**Bài 5.** fail[root] và fail của con trực tiếp root là gì?

**Đáp án:** fail[root]=root theo quy ước; con trực tiếp có fail=root.

**Bài 6.** Vì sao xây fail bằng BFS?

**Đáp án:** Fail của nút con cần fail của cha, và outputLink cần fail/outputLink của nút hậu tố ngắn hơn; BFS theo độ sâu đảm bảo các phụ thuộc đã tính.

**Bài 7.** Cho các mẫu "he","she","his","hers", vì sao khi thấy "she" phải báo "he"?

**Đáp án:** "he" là hậu tố của "she" và là một mẫu, fail("she") trỏ tới nút "he"; outputLink dẫn tới terminal tương ứng.

**Bài 8.** Trên text "ahishers", những match nào xuất hiện?

**Đáp án:** "his" [1,4), "she" [3,6), "he" [4,6), "hers" [4,8).

**Bài 9.** Cho patterns=["a","ba","aba"], text="aba". Tổng match bao nhiêu?

**Đáp án:** 4: "a" [0,1), "aba" [0,3), "ba" [1,3), "a" [2,3).

**Bài 10.** Vì sao chỉ kiểm tra terminal ở state hiện tại chưa đủ?

**Đáp án:** Mẫu ngắn hơn có thể là hậu tố của state dài nhưng không phải terminal trực tiếp tại state; cần đi outputLink.

**Bài 11.** Nếu patterns=["a","aa","aaa"], text="aaaa", có tổng bao nhiêu match?

**Đáp án:** 4+3+2=9.

**Bài 12.** Nếu bổ sung một mẫu "aa" trùng với mẫu "aa" đã có, yêu cầu báo theo ID, tổng match ở text "aaaa" thành bao nhiêu?

**Đáp án:** 12, vì mỗi trong ba lần "aa" phải được báo cho hai ID khác nhau.

**Bài 13.** Tại sao không được nhảy qua toàn bộ mẫu sau một match?

**Đáp án:** Vì những lần xuất hiện tiếp theo có thể chồng lấp; ví dụ "aa" trong "aaaa" có ba lần tại start0,1,2.

**Bài 14.** outputLink[v] là gì?

**Đáp án:** Nút terminal gần nhất trên chuỗi fail của v, hoặc −1 nếu không có; giúp bỏ qua các fail nodes không terminal khi báo kết quả.

**Bài 15.** Nếu fail[v] không terminal, tính outputLink[v] thế nào?

**Đáp án:** outputLink[v]=outputLink[fail[v]].

**Bài 16.** Độ dài mẫu dùng để tính start trong code mẫu là loại nào?

**Đáp án:** Số Unicode code points, vì automaton chuyển theo code point; startCp=endCp−lengthCp.

**Bài 17.** Trong Java, emoji ngoài BMP chiếm bao nhiêu UTF-16 char?

**Đáp án:** Thường 2 char, nhưng là 1 Unicode code point. Vì vậy không dùng String.length() như độ dài code point.

**Bài 18.** Với text="a🙂a🙂", các offset UTF-16 ở ranh giới code points là gì?

**Đáp án:** [0,1,3,4,6].

**Bài 19.** Mẫu "a🙂" ở đầu text có đoạn code point/UTF-16 nào?

**Đáp án:** cp[0,2), utf16[0,3).

**Bài 20.** Nếu cần tìm không phân biệt hoa thường, chỉ lowercase patterns có đủ không?

**Đáp án:** Không; phải áp quy tắc chuẩn hóa tương ứng cho cả patterns và text, và ánh xạ offset về text gốc nếu chuẩn hóa làm đổi chiều dài.

**Bài 21.** Một node terminal có thể lưu nhiều pattern IDs không?

**Đáp án:** Có, khi input có mẫu trùng nội dung và yêu cầu giữ ID riêng.

**Bài 22.** Tại sao không cần báo tất cả các fail nodes không terminal?

**Đáp án:** Chúng chỉ dùng để định hướng chuyển trạng thái, không đại diện mẫu kết thúc; outputLink bỏ qua chúng.

**Bài 23.** Bản mã Java sử dụng cấu trúc nào cho cạnh trie?

**Đáp án:** HashMap<Integer,Integer> từ code point sang ID nút con, hỗ trợ alphabet Unicode sparse.

**Bài 24.** Với L là tổng độ dài mẫu, tối đa bao nhiêu nút trie được tạo?

**Đáp án:** L+1 gồm root, vì mỗi code point được chèn tạo nhiều nhất một node mới.

**Bài 25.** Vì sao không được khẳng định bước xây fail sparse trong code luôn O(L)?

**Đáp án:** Mỗi cạnh trie có thể phải đi qua nhiều fail links khi tìm transition tương ứng; cận bảo thủ là O(LH) nếu H là độ dài mẫu lớn nhất.

**Bài 26.** Độ phức tạp quét text và liệt kê mọi match theo T và Z?

**Đáp án:** O(T+Z) kỳ vọng với HashMap tra cứu trung bình O(1) và fail amortized; không thể bỏ Z nếu phải xuất đủ từng match.

**Bài 27.** Tại sao có thể xuất nhiều hơn T kết quả?

**Đáp án:** Nhiều mẫu/hậu tố có thể kết thúc cùng vị trí và các match chồng lấp; ví dụ các mẫu a,aa,aaa... trên dãy nhiều a.

**Bài 28.** Nếu danh sách mẫu rỗng nhưng text không rỗng, kết quả?

**Đáp án:** Danh sách Hit rỗng; trie chỉ có root.

**Bài 29.** Mẫu rỗng được xử lý thế nào trong chương trình?

**Đáp án:** Từ chối bằng IllegalArgumentException. Muốn hỗ trợ phải tự định nghĩa số/vị trí match ở các ranh giới chuỗi.

**Bài 30.** Nếu text rỗng và mọi mẫu không rỗng, tổng match?

**Đáp án:** 0.

**Bài 31.** Khi quét nhiều chunk, vì sao không reset automaton mỗi chunk?

**Đáp án:** Vì một mẫu có thể bắt đầu ở chunk trước và kết thúc ở chunk sau; cần giữ state giữa các chunk.

**Bài 32.** Khi muốn trả offset UTF-16 toàn cục trong streaming, cần chú ý gì?

**Đáp án:** Cần theo dõi offset UTF-16, giữ đủ thông tin ranh giới code points gần đây (ít nhất tương ứng mẫu dài nhất), và xử lý surrogate pair bị chia giữa chunk.

**Bài 33.** Aho–Corasick có tự tìm “từ độc lập” không?

**Đáp án:** Không; nó tìm substring. Cần lọc word boundary riêng nếu yêu cầu match nguyên từ.

**Bài 34.** Từ điển thay đổi (thêm một mẫu) có thể giữ nguyên fail/output links không?

**Đáp án:** Không được mặc định; thêm mẫu có thể thay đổi nhiều hậu tố/prefix liên quan. Cần xây lại hoặc dùng cấu trúc động chuyên biệt có chứng minh.

**Bài 35.** Khi nào cân nhắc suffix array thay vì Aho–Corasick?

**Đáp án:** Khi văn bản cố định và có nhiều truy vấn mẫu đến sau, tiền xử lý text thành chỉ mục có thể phù hợp; nếu mẫu cố định và quét nhiều văn bản, Aho–Corasick thường thuận lợi.

## 17. Bảng ghi nhớ và checklist triển khai

| Nội dung | Quy tắc |
| --- | --- |
| Bài toán | Nhiều mẫu trên một văn bản |
| Nền tảng | Trie các tiền tố chung |
| Ký tự đang quét | Dùng Unicode code point trong bản Java |
| fail[v] | Hậu tố thích hợp dài nhất của label(v) cũng là tiền tố trie |
| fail[root] | Root theo quy ước |
| fail của con root | Root |
| Dựng fail | BFS theo độ sâu trie |
| outputLink[v] | Terminal fail gần nhất hoặc −1 |
| Thiếu cạnh c | Theo fail và thử lại **cùng c** |
| Có cạnh c | Chuyển trie rồi tiêu thụ c đúng một lần |
| Phát match | Terminal hiện tại + các terminal theo outputLink |
| Vị trí match | `[endCp−lengthCp,endCp)` |
| Mẫu trùng | Giữ nhiều ID ở cùng terminal nếu bài cần |
| Chồng lấp | Phải báo mọi đoạn hợp lệ |
| Empty pattern | Từ chối theo hợp đồng chương trình |
| Empty pattern list | Hợp lệ, không match |
| Empty text | Không match mẫu không rỗng |
| Unicode UTF-16 | Dùng prefix offset để ánh xạ cp→char |
| Chuẩn hóa chữ | Áp cho cả patterns/text và ánh xạ offset gốc |
| Build trie | O(L) kỳ vọng với Map |
| Build sparse fail | Cận bảo thủ O(LH) trong code mẫu |
| Scan và emit | O(T+Z) kỳ vọng |
| Automaton memory | O(L+K) |
| Memory của List<Hit> | Thêm O(T+Z) trong bản minh họa |
| Streaming | Giữ state và offset, không reset giữa chunks |
| Test oracle | Vét cạn tất cả start/end trên test nhỏ |

## Kết luận

**Aho–Corasick** kết hợp **trie** để chia sẻ tiền tố, **failure links** để trở về hậu tố tiền tố phù hợp khi thất bại, và **output links** để phát đầy đủ các mẫu ngắn là hậu tố của state hiện tại. Nhờ bộ máy trạng thái này, văn bản được quét theo một chiều, đồng thời tìm nhiều mẫu, kể cả match chồng lấp và các mẫu có nội dung trùng nhau nhưng ID khác.

Điểm quan trọng nhất khi tự cài đặt là:

1. **Xây fail đúng bằng BFS** và thử lại cùng ký tự khi đi fail.
2. **Không bỏ các mẫu hậu tố**: báo terminal của state và toàn bộ terminal theo outputLink.
3. **Định nghĩa rõ đơn vị vị trí** (code point, UTF-16 hay byte), xử lý chính xác mẫu trùng, mẫu rỗng và chồng lấp.
4. **Phân tích đúng cấu trúc dùng**: bản sparse trong Java quét text O(T+Z) kỳ vọng, nhưng việc xây fail bằng fallback lặp có cận trường hợp xấu phụ thuộc H; một automaton dense/memoized có đánh đổi khác.

Khi đã hiểu bất biến “state là hậu tố dài nhất của văn bản đã đọc cũng là tiền tố của mẫu”, bạn có thể mở rộng bộ tìm kiếm này thành công cụ đếm từ khóa, dò chữ ký, xử lý streaming hoặc chỉ mục mẫu cho nhiều văn bản một cách có hệ thống và kiểm chứng được.
