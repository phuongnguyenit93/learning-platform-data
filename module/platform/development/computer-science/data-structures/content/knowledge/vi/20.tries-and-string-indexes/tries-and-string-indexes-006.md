# Liệt kê khóa theo tiền tố và hỗ trợ gợi ý tìm kiếm

> **Chương:** Trie và chỉ mục chuỗi · **Bài học:** Liệt kê khóa theo tiền tố và hỗ trợ gợi ý tìm kiếm

Khi người dùng gõ `an` vào một ô tìm kiếm, hệ thống có thể gợi ý `an`, `anh`, `an toàn` hoặc những từ khóa khác bắt đầu bằng hai ký hiệu ấy. Một câu hỏi đơn giản — “Những khóa nào bắt đầu bằng `an`?” — khác rõ rệt với câu hỏi “`an` có phải chính là một khóa đã lưu không?”. Truy vấn thứ nhất phải **liệt kê nhiều kết quả**, có thể phải xếp chúng theo thứ tự và cắt ở một giới hạn; truy vấn thứ hai chỉ cần một giá trị đúng/sai.

Trie (*cây tiền tố*) phù hợp với truy vấn này vì mọi khóa có chung một tiền tố đều nằm trong **cùng một cây con**. Ta chỉ cần lần theo tiền tố, rồi duyệt phần cây con ấy để lấy các nút đánh dấu kết thúc khóa. Nhưng lợi thế ấy không có nghĩa toàn bộ autocomplete luôn O(P), với `P` là độ dài tiền tố: bước **xuất và xếp hạng kết quả** có chi phí riêng, đôi khi lớn hơn rất nhiều so với bước tìm vị trí tiền tố.

Bài học thuộc chương **Trie và chỉ mục chuỗi** của mô-đun **Cấu trúc dữ liệu** (`COMPUTER_SCIENCE_DATA_STRUCTURES`). Ta sẽ đặc tả thao tác, xây thuật toán duyệt đúng, phân tích thời gian–bộ nhớ, cài đặt Python hoàn chỉnh, rồi xem xét thứ tự Unicode, gợi ý theo độ phổ biến, giới hạn kết quả và cập nhật chỉ mục. Cách phân tích này gắn với mục tiêu chung của mô-đun: hiểu bất biến và chi phí thao tác khi lựa chọn mảng, danh sách liên kết, Stack, Queue, bảng băm, cây, heap và đồ thị cho bài toán thực tế.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **kiểm tra tồn tại tiền tố** với **liệt kê khóa đầy đủ có tiền tố đó**.
2. Giải thích vì sao các khóa bắt đầu bằng một tiền tố tạo thành một **cây con liên thông** của trie.
3. Viết thuật toán hai giai đoạn: **định vị nút tiền tố** rồi **duyệt các nút terminal trong cây con**.
4. So sánh DFS, BFS, duyệt theo thứ tự ký tự và duyệt theo mức ưu tiên khi liệt kê kết quả.
5. Cài đặt gợi ý có `limit` bằng DFS lặp, không phụ thuộc giới hạn đệ quy của Python.
6. Phân tích chi phí theo `P`, số nút được duyệt `R`, số kết quả `C` và tổng số ký hiệu xuất ra `Z`.
7. Xây gợi ý **top-k theo điểm** bằng heap và hiểu vì sao top-k cơ bản vẫn phải xem toàn bộ ứng viên.
8. Nêu đúng bất biến terminal và bộ đếm cây con khi chèn, xóa hoặc cập nhật điểm gợi ý.
9. Xử lý nhất quán Unicode, chuẩn hóa, chữ hoa–thường và hợp đồng thứ tự kết quả.
10. Lựa chọn chỉ mục và chiến lược cache/xếp hạng theo tần suất truy vấn, cập nhật, thời gian phản hồi và giới hạn bộ nhớ.

## 2. Đặc tả: tìm chính xác, kiểm tra tiền tố và liệt kê là ba việc khác nhau

Gọi `K` là tập khóa chuỗi phân biệt đang được lưu. Quan hệ `p\preceq s` có nghĩa `p` là **tiền tố** của `s`, tức tồn tại một chuỗi `t` (có thể rỗng) sao cho `s=p+t`.

Ba thao tác cơ bản:

\[
\operatorname{contains}(s)
\iff s\in K;
\]

\[
\operatorname{hasKeyWithPrefix}(p)
\iff \exists s\in K:\ p\preceq s;
\]

\[
\operatorname{matches}(p)
=\{s\in K:\ p\preceq s\}.
\]

**`contains` trả Boolean; `matches` trả một tập/danh sách kết quả.** Muốn trả danh sách có thứ tự, ta còn phải định nghĩa **thứ tự nào**.

### 2.1. Ví dụ tập khóa

Cho:

```text
K = {"an", "anh", "ao", "ba", "ban"}
```

| Truy vấn | Kết quả | Giải thích |
| --- | --- | --- |
| `contains("a")` | False | `a` chỉ là tiền tố |
| `contains("an")` | True | `an` là khóa đầy đủ |
| `hasKeyWithPrefix("a")` | True | Có `an, anh, ao` |
| `matches("an")` | `{an, anh}` | Cả hai bắt đầu bằng `an` |
| `matches("ba")` | `{ba, ban}` | `ba` là khóa và là tiền tố của `ban` |
| `matches("ax")` | Tập rỗng | Không có nhánh `x` sau `a` |
| `matches("")` | Toàn bộ `K` | Chuỗi rỗng là tiền tố mọi chuỗi |

Trong bài này, kết quả `suggest_lex` sẽ là **danh sách chuỗi tăng theo thứ tự code point Unicode**. Kết quả `suggest_top_k` sẽ là **danh sách cặp (khóa, điểm)** theo điểm giảm dần, hòa điểm thì khóa tăng theo code point.

### 2.2. Dấu terminal quyết định phần tử nào được xuất

Một nút của trie biểu diễn một tiền tố. **Không phải mọi nút đều là khóa hoàn chỉnh.** Chỉ những nút có `terminal=True` mới được phát ra thành kết quả.

Nếu trie chỉ lưu `"anh"`:

```text
root -> a -> n -> h*
```

thì `matches("a")` phải trả `{"anh"}`, **không** được trả thêm `"a"` và `"an"`. Hai nút đó tồn tại để dẫn đường, không phải để biểu diễn khóa đã lưu.

### 2.3. Thứ tự kết quả cần ghi rõ

“Liệt kê các khóa” có thể nghĩa:

- Tập kết quả không thứ tự.
- Khóa tăng theo thứ tự ký tự.
- Khóa ngắn trước, dài sau.
- Khóa có tần suất hoặc điểm phổ biến cao trước.
- Khóa được cá nhân hóa theo một hàm xếp hạng.

Các thứ tự này **không tương đương**. Việc đi tới nút tiền tố là phần chung, còn cách duyệt hoặc chọn ứng viên phụ thuộc hợp đồng riêng.

## 3. Vì sao các khóa cùng tiền tố nằm trong một cây con?

Trie không nén có một gốc và mỗi cạnh mang đúng một ký hiệu. Từ mỗi nút, mỗi ký hiệu có tối đa một cạnh con.

Nếu khóa `s` bắt đầu bằng tiền tố `p`, đường đi của `s` phải đi qua **nút biểu diễn `p`**. Ngược lại, mọi nút terminal ở dưới nút `p` tạo thành một khóa bắt đầu bằng `p`.

Vì vậy, với nút `v_p` ứng với `p`:

\[
matches(p)
=\{\operatorname{label}(v):
v \text{ terminal và thuộc cây con của }v_p\}.
\]

Đây là cơ sở toán học của thuật toán liệt kê bằng trie.

### 3.1. Sơ đồ minh họa

Với các khóa:

```text
an, anh, ao, ba, ban, bao
```

ta có:

```text
                       root ("")
                      /         \
                     a           b
                   /   \          \
                  n*    o*         a*
                  |              /   \
                  h*            n*    o*

* = terminal: khóa đầy đủ đã lưu
```

Muốn tìm tất cả khóa bắt đầu bằng `"ba"`:

1. Từ gốc, đi theo cạnh `b`.
2. Từ nút `b`, đi theo cạnh `a`.
3. Đến nút `ba`, duyệt **chỉ cây con dưới nó**.
4. Phát ra `ba`, `ban` và `bao` tại các nút terminal.

Không cần thăm nhánh `a` của gốc chứa `an, anh, ao`.

### 3.2. Tính đúng dựa trên bất biến đường đi

Bất biến chính:

- Đường từ gốc tới nút là dãy ký hiệu của đúng một tiền tố.
- `terminal=True` khi và chỉ khi tiền tố ấy thuộc tập khóa.
- Các nhánh ra khỏi một nút có nhãn duy nhất.

Nếu những bất biến này được giữ, việc liệt kê tất cả terminal trong cây con `v_p` **không bỏ sót** khóa có tiền tố `p` và **không thêm nhầm** khóa nằm ngoài tập đó.

## 4. Thuật toán tổng quát gồm hai giai đoạn

Đặt `P=len(prefix)` là số ký hiệu đầu vào theo cách biểu diễn đang dùng.

**Giai đoạn A — định vị nút tiền tố:**

```text
LOCATE(root, prefix):
    node <- root

    for mỗi ký hiệu ch của prefix:
        if node không có cạnh ch:
            return NONE
        node <- node.children[ch]

    return node
```

Nếu `LOCATE` trả `NONE`, không có khóa nào mang tiền tố đó, và kết quả liệt kê là rỗng.

**Giai đoạn B — duyệt cây con và phát kết quả:**

```text
ENUMERATE(node, current_text):
    if node.terminal:
        EMIT(current_text)

    for mỗi cạnh (ch, child) của node:
        ENUMERATE(child, current_text + ch)
```

Bản giả mã đệ quy giúp nhìn rõ ý tưởng, nhưng có hai điểm cần cải thiện khi lập trình:

1. Với khóa rất dài, DFS đệ quy có thể vượt giới hạn ngăn xếp của ngôn ngữ/runtime.
2. `current_text + ch` có thể tạo và sao chép chuỗi tại **mỗi cạnh**, dù nhiều nút không terminal.

Ta sẽ viết **DFS lặp** và duy trì danh sách ký hiệu của đường đi trong phần cài đặt.

### 4.1. Nếu tiền tố tự là khóa hoàn chỉnh

Nếu nút `v_p` có `terminal=True`, **phải xuất chính `p`** trước khi duyệt những khóa dài hơn, nếu hợp đồng dùng thứ tự từ điển thông thường.

Ví dụ `matches("an")` với `{an,anh}` nên chứa cả `an` và `anh`. Nếu chỉ duyệt các **con** của nút `an` mà quên kiểm tra nút bắt đầu, ta sẽ bỏ sót `an`.

### 4.2. Nếu tiền tố không tồn tại

Ví dụ đang lưu `an, anh, ao` nhưng được hỏi `prefix="ax"`:

```text
root --a--> node_a --x--> không có
```

Có thể trả `[]` ngay, không cần duyệt phần khác của trie. Đây là lợi thế rõ ràng so với quét mọi khóa khi tập dữ liệu lớn và nhiều tiền tố truy vấn không có kết quả.

## 5. DFS và BFS trả các thứ tự khác nhau

Trie là một cây. Để đi hết cây con, ta có thể dùng **DFS** (duyệt sâu) hoặc **BFS** (duyệt rộng), nhưng lựa chọn ấy ảnh hưởng thứ tự phát khóa.

### 5.1. DFS theo thứ tự ký tự

Nếu tại mỗi nút:

1. Phát khóa ở nút hiện tại nếu terminal.
2. Xử lý các cạnh con **theo nhãn tăng dần**.

thì DFS tạo các khóa theo thứ tự từ điển của dãy ký hiệu, với quy tắc **một khóa là tiền tố của khóa khác sẽ đứng trước khóa dài hơn**.

Ví dụ:

```text
K = {"an", "anh", "ang", "ao"}
```

DFS tăng nhãn phát:

```text
an
ang
anh
ao
```

Tại nút `an`, phát `an` trước khi đi xuống; nhãn `g` nhỏ hơn `h` nên `ang` đứng trước `anh`.

### 5.2. BFS theo chiều sâu

BFS dùng **Queue** để thăm các nút theo chiều sâu tăng. Với cùng tập khóa, BFS có xu hướng phát các khóa ngắn trước. Nhưng BFS không tự bảo đảm “điểm phổ biến cao nhất trước”, và cũng không nhất thiết đúng thứ tự từ điển.

Ví dụ `{a, ab, ac, b}`:

- DFS theo nhãn tăng phát `a, ab, ac, b`.
- BFS theo tầng có thể phát `a, b, ab, ac`.

Hai dãy đều liệt kê đủ khóa, nhưng chỉ dãy đầu là thứ tự từ điển theo ký hiệu.

### 5.3. DFS, BFS và bộ nhớ tạm

| Phương pháp | Vùng lưu trạng thái | Thứ tự tự nhiên | Điểm cần chú ý |
| --- | --- | --- | --- |
| DFS đệ quy | Call stack theo chiều sâu | Tùy thứ tự các con | Có thể vượt giới hạn đệ quy |
| DFS lặp | Stack các nhánh/sự kiện | Có thể bảo đảm từ điển nếu xếp nhánh | Phải khôi phục đường ký hiệu đúng |
| BFS | Queue các nút chưa xử lý | Theo mức độ sâu | Hàng đợi có thể lớn ở tầng nhiều nhánh |
| Duyệt theo điểm | Heap / hàng đợi ưu tiên hoặc chỉ mục top-k | Theo quy tắc điểm nếu có thông tin phù hợp | Không phải cứ dùng heap là tránh được việc xét ứng viên |

DFS phù hợp với liệt kê theo thứ tự từ điển và dễ dừng khi đã đủ `limit`. BFS có ích khi muốn ưu tiên độ dài hoặc tầng, nhưng cần quy định rõ cách phá hòa giữa các nút cùng tầng.

## 6. Tạo kết quả từ các nút terminal và chi phí chuỗi

Với mỗi nút terminal, chương trình phải tạo một chuỗi khóa đầy đủ từ đường đi.

Có ba cách thường thấy:

1. **Giữ chuỗi hiện tại:** tại cạnh `ch`, tạo `current + ch`.
2. **Giữ danh sách ký hiệu:** thêm khi đi xuống, bỏ khi đi lên, và `"".join(path)` chỉ ở nút terminal.
3. **Lưu nguyên khóa ở nút terminal:** đọc giá trị đã lưu, đổi lại tốn bộ nhớ lưu bản sao hoặc tham chiếu.

### 6.1. Chi phí của `current + ch`

Trong Python, chuỗi `str` bất biến. `current + ch` thường tạo một chuỗi mới với nội dung của `current` và `ch`.

Nếu đường có chiều sâu `H`, tổng ký tự được sao chép vào **các chuỗi trung gian** trên một đường dài có thể đạt:

\[
1+2+\cdots+H=\Theta(H^2).
\]

Đây là lý do không nên kết luận một DFS “chỉ đi qua mỗi cạnh một lần” thì chắc chắn O(số nút) **thao tác ký tự**, nếu cài đặt sao chép tiền tố tại mỗi bước.

### 6.2. Danh sách đường đi và sự kiện vào/ra nút

Một DFS lặp có thể dùng danh sách `path` chứa những ký hiệu của nhánh hiện tại.

- Khi **vào nút con**, thêm nhãn cạnh vào `path`.
- Nếu nút terminal, tạo chuỗi `"".join(path)`.
- Sau khi duyệt xong cây con, **ra nút** và bỏ nhãn cuối khỏi `path`.

Ta có thể mô phỏng thao tác vào/ra bằng những phần tử đặc biệt trong Stack, không cần đệ quy. Phương án này giữ việc ghi kết quả đúng thời điểm và tránh nối chuỗi tại mọi nút không terminal.

### 6.3. Tổng độ dài đầu ra không thể bỏ qua

Nếu trả `C` khóa `s_1,\ldots,s_C`, đặt:

\[
Z=\sum_{j=1}^{C}|s_j|.
\]

Muốn xây các đối tượng chuỗi kết quả mới, phải tạo lượng nội dung tỷ lệ ít nhất `Z` ký hiệu trong mô hình ghi từng ký hiệu:

\[
T_{\mathrm{output}}=\Omega(Z).
\]

Ngay cả khi trie định vị tiền tố O(P), việc trả một triệu từ dài vẫn không thể là O(P) thời gian cho **toàn bộ** truy vấn.

## 7. Tính thời gian theo tiền tố, số nút duyệt và lượng kết quả

Đặt:

- `P`: độ dài tiền tố.
- `R`: số nút thật sự được duyệt trong cây con trong một lời gọi.
- `C`: số khóa terminal được phát ra.
- `Z`: tổng số ký hiệu trong `C` khóa được tạo.
- `d_v`: số con của nút `v`.
- `σ`: số ký hiệu trong bảng chữ cái.

Giả sử chọn một cạnh bằng Hash Map có chi phí O(1) kỳ vọng, mã giữ `path` và chỉ tạo chuỗi ở terminal, đồng thời **sắp nhãn con mỗi lần duyệt nút**.

Một chặn trên là:

\[
T_{\mathrm{lex}}=
O\left(P+R+Z+
\sum_{\text{nút }v\text{ đã mở rộng}}d_v\log(d_v+1)\right).
\]

Trong công thức:

- `P`: tìm nút tiền tố.
- `R`: thăm nút và xử lý sự kiện Stack.
- `Z`: tạo các chuỗi kết quả.
- Phần tổng: các lệnh `sorted(children)` tại những nút mở rộng.

Phát biểu này phụ thuộc cách cài đặt. Nếu dùng **mảng nhánh đã sắp**, chi phí sắp lại mỗi lần có thể bỏ. Nếu dùng **mảng `σ` con cố định** và phải quét hết các ô để lấy con tăng nhãn, phần duyệt có thể O(Rσ).

### 7.1. Chi phí khi chỉ kiểm tra có gợi ý hay không

Nếu mỗi nút lưu `subtree_count` = số khóa terminal trong cây con, câu hỏi “có khóa nào bắt đầu bằng `prefix` không?” chỉ cần:

1. Theo đường `prefix`.
2. Đọc `subtree_count` của nút vừa tới.

Thời gian O(P+1) kỳ vọng theo mô hình Hash Map con, **không cần liệt kê kết quả**.

Nhưng chỉ số `subtree_count` phải được cập nhật khi chèn/xóa khóa. Nếu cập nhật sai, kết quả đếm và quyết định “có gợi ý” cũng sai.

### 7.2. Nếu `limit=k` nhỏ

Một lời gọi trả **tối đa `k` khóa** có thể dừng ngay khi đã tìm đủ. Khi đó `R` là số nút đã thăm trước thời điểm dừng; không nhất thiết bằng tổng nút của cả cây con.

Tuy nhiên, **không thể thay công thức trên bằng O(P+k)** trong mọi trie. Có thể phải đi qua một đường rất dài để tìm được một khóa terminal, và từng nút đã mở rộng còn có chi phí lấy/sắp nhánh.

### 7.3. Bộ nhớ phụ của DFS

Với DFS lặp:

- `path` chứa số ký hiệu theo chiều sâu đang đi: O(H), với `H` là độ sâu của đường đang xét.
- Stack chứa những nhánh chưa duyệt: phụ thuộc số nhánh rẽ đang chờ, trường hợp xấu có thể O(R).
- Nếu trả một danh sách `C` chuỗi, bộ nhớ cho **kết quả** có thể Θ(Z) ký hiệu, chưa kể overhead danh sách/đối tượng.
- Nếu chỉ phát qua generator, có thể tránh giữ toàn bộ danh sách kết quả cùng lúc, nhưng người tiêu thụ vẫn phải xử lý nội dung được phát.

Trong trie có `σ` giới hạn, phần Stack chờ theo DFS thường liên hệ với số nhánh rẽ dọc đường; giới hạn tổng quát O(R) vẫn an toàn.

## 8. Cài đặt Python: chỉ mục Trie hỗ trợ liệt kê và xếp hạng

Ta xây một `TrieSearchIndex` có hợp đồng rõ:

- Lưu một **tập các khóa phân biệt**.
- Mỗi khóa được gắn một `score` nguyên không âm.
- `upsert(word, score)` thêm khóa mới hoặc thay điểm của khóa đã có.
- `delete(word)` xóa khóa, không làm mất khóa khác chung tiền tố.
- `count_prefix(prefix)` đếm số khóa phân biệt có tiền tố.
- `iter_matches(prefix)` **phát tuần tự** các cặp `(word,score)` theo thứ tự ký tự.
- `suggest_lex(prefix, limit)` lấy tối đa `limit` khóa theo thứ tự từ điển.
- `suggest_top_k(prefix, k)` lấy tối đa `k` cặp khóa–điểm có điểm cao nhất; hòa điểm thì khóa tăng.

Điểm số trong bài là thuộc tính ứng dụng **được cung cấp sẵn**, không giả định hệ thống tự biết số lượt tìm hay tần suất thật. Nếu muốn đếm lượt chọn kết quả, ứng dụng phải cập nhật điểm bằng một chính sách rõ ràng.

### 8.1. Lớp nút

```python
from heapq import nsmallest
from itertools import islice


class TrieNode:
    __slots__ = ("children", "terminal", "score", "subtree_count")

    def __init__(self):
        self.children = {}      # Một ký hiệu -> đúng một TrieNode
        self.terminal = False   # Có lưu chính khóa ở tiền tố này?
        self.score = 0          # Điểm của khóa, chỉ có ý nghĩa khi terminal
        self.subtree_count = 0  # Số khóa phân biệt trong cây con
```

Hai bất biến trung tâm:

\[
terminal(v)=\text{True}\iff label(v)\in K
\]

và

\[
count(v)=\mathbf{1}_{terminal(v)}
+\sum_{u\in children(v)}count(u).
\]

Giá trị `score` của nút không terminal không đóng góp vào số khóa hay kết quả gợi ý.

### 8.2. Phần quản lý khóa: tìm, chèn, xóa và đếm

Đặt mã tiếp sau `TrieNode` trong cùng tệp:

```python
class TrieSearchIndex:
    def __init__(self):
        self._root = TrieNode()
        self._size = 0

    @staticmethod
    def _validate_text(text):
        if not isinstance(text, str):
            raise TypeError("khóa và tiền tố phải là str")

    @staticmethod
    def _validate_score(score):
        if type(score) is not int or score < 0:
            raise ValueError("score phải là số nguyên không âm")

    @staticmethod
    def _validate_limit(limit):
        if limit is not None and (
            type(limit) is not int or limit < 0
        ):
            raise ValueError("limit phải là None hoặc số nguyên không âm")

    def __len__(self):
        return self._size

    def _locate(self, text):
        node = self._root
        for ch in text:
            node = node.children.get(ch)
            if node is None:
                return None
        return node

    def contains(self, word):
        self._validate_text(word)
        node = self._locate(word)
        return node is not None and node.terminal

    def count_prefix(self, prefix):
        self._validate_text(prefix)
        node = self._locate(prefix)
        return 0 if node is None else node.subtree_count

    def has_key_with_prefix(self, prefix):
        return self.count_prefix(prefix) > 0

    def upsert(self, word, score=0):
        """True nếu thêm khóa mới; False nếu chỉ thay điểm."""
        self._validate_text(word)
        self._validate_score(score)

        node = self._root
        path = [node]

        for ch in word:
            child = node.children.get(ch)
            if child is None:
                child = TrieNode()
                node.children[ch] = child
            node = child
            path.append(node)

        is_new = not node.terminal

        if is_new:
            node.terminal = True
            self._size += 1
            for item in path:
                item.subtree_count += 1

        node.score = score
        return is_new

    def delete(self, word):
        """Xóa một khóa, giữ các khóa dùng chung tiền tố."""
        self._validate_text(word)

        node = self._root
        path = [node]

        for ch in word:
            node = node.children.get(ch)
            if node is None:
                return False
            path.append(node)

        if not node.terminal:
            return False

        node.terminal = False
        node.score = 0

        for item in path:
            item.subtree_count -= 1

        # Cắt các cây con không còn khóa terminal.
        for i in range(len(word) - 1, -1, -1):
            parent = path[i]
            child = path[i + 1]
            if child.subtree_count > 0:
                break
            del parent.children[word[i]]

        self._size -= 1
        return True
```

**Chú ý `upsert`:** khi một khóa đã tồn tại, thay `score` **không** làm tăng `subtree_count` hoặc `len`. Trong chỉ mục tìm kiếm thật, cùng một từ có thể đổi mức phổ biến nhiều lần; phân biệt **khóa mới** và **điểm mới** giúp tránh đếm sai.

## 9. DFS lặp với sự kiện vào/ra nút

Ta bổ sung phương thức `iter_matches` **vào trong lớp `TrieSearchIndex`** ở mục 8.

Mã dùng Stack các sự kiện:

- Sự kiện **vào** mang nút và nhãn của cạnh dẫn tới nút.
- Sự kiện **ra** xóa nhãn vừa thêm khỏi `path`.
- Mỗi lần gặp nút terminal, phát một cặp `(chuỗi_đầy_đủ,score)`.
- Các cạnh được xếp theo thứ tự nhãn tăng, nhưng vì Stack LIFO nên **đẩy ngược** để nhánh nhỏ được xử lý trước.

### 9.1. Mã liệt kê tăng theo ký tự

```python
    def iter_matches(self, prefix=""):
        """Generator (word, score) theo thứ tự code point Unicode."""
        self._validate_text(prefix)

        start = self._locate(prefix)
        if start is None:
            return

        path = list(prefix)
        stack = [(False, start, None)]  # (is_exit, node, edge_char)

        while stack:
            is_exit, node, ch = stack.pop()

            if is_exit:
                path.pop()
                continue

            if ch is not None:
                path.append(ch)

            if node.terminal:
                yield ("".join(path), node.score)

            if ch is not None:
                stack.append((True, None, None))

            # Đẩy nhãn lớn trước; nhãn nhỏ được pop trước.
            for edge, child in sorted(
                node.children.items(), reverse=True
            ):
                stack.append((False, child, edge))
```

**Cách lắp mã:** đoạn trên là phương thức của `TrieSearchIndex`, có cùng mức thụt lề với `contains` hay `delete`. Không đặt nó độc lập ngoài lớp nếu muốn gọi `index.iter_matches(...)`.

### 9.2. Vết sự kiện để thấy `path` không bị sai

Xét cây con của `"an"` chứa:

```text
an*
 |
 +-- g*  ("ang")
 |
 +-- h*  ("anh")
```

Khi bắt đầu tại nút `an`, `path=['a','n']`.

1. Vào nút `an`, thấy terminal nên phát `"an"`.
2. Đẩy sự kiện vào nhánh `h` rồi nhánh `g`, vì Stack LIFO.
3. Vào nhánh `g`: thêm `g`, phát `"ang"`; sau đó ra nút, bỏ `g`.
4. Vào nhánh `h`: thêm `h`, phát `"anh"`; sau đó ra nút, bỏ `h`.

Kết quả theo thứ tự ký tự: `an, ang, anh`. Sau khi duyệt xong, `path` trở lại đúng tiền tố ban đầu.

### 9.3. Vì sao kiểm tra terminal trước khi đi xuống?

Trong thứ tự từ điển của các dãy ký hiệu, một khóa là tiền tố của khóa dài hơn đứng **trước** khóa dài hơn.

Ví dụ `"an" < "anh"`, bởi vì `"an"` kết thúc trước khi phải xét ký hiệu tiếp theo. Phát khóa ở nút trước khi thăm con bảo đảm quy tắc này.

### 9.4. Generator không giữ toàn bộ danh sách

`iter_matches` dùng `yield`: nó tạo từng kết quả khi người tiêu thụ yêu cầu, không xây một danh sách chứa mọi khóa ngay lập tức.

Điều này hữu ích nếu số kết quả lớn hoặc nếu `limit` nhỏ. Nhưng nó **không xóa chi phí của những nút đã thăm**, và mỗi kết quả vẫn cần tạo chuỗi hoàn chỉnh.

**Giới hạn hành vi:** mã minh họa giả định không có thao tác thêm/xóa/cập nhật đồng thời khi một generator đang được duyệt. Nếu chỉ mục có thể thay đổi trong lúc liệt kê, cần quy định snapshot, khóa đồng bộ hoặc cơ chế phát hiện phiên bản thay đổi.

## 10. Giới hạn số gợi ý theo thứ tự từ điển

Để trả tối đa `limit` khóa đầu tiên từ generator, có thể dùng `itertools.islice`.

Bổ sung vào lớp `TrieSearchIndex`:

```python
    def suggest_lex(self, prefix="", limit=None):
        """Danh sách khóa tăng theo code point Unicode."""
        self._validate_text(prefix)
        self._validate_limit(limit)

        matches = self.iter_matches(prefix)

        if limit is None:
            return [word for word, _ in matches]

        return [word for word, _ in islice(matches, limit)]
```

Kết quả:

- `limit=None`: trả toàn bộ khóa khớp.
- `limit=0`: trả danh sách rỗng.
- `limit=k>0`: trả tối đa `k` khóa đầu tiên theo thứ tự đã chọn.
- `prefix=""`: bắt đầu duyệt từ gốc, tức có thể liệt kê mọi khóa.
- `prefix` không tồn tại: trả `[]`.

### 10.1. Điều kiện dừng sớm đúng

Khi đã phát đủ `k` khóa, `islice` không yêu cầu thêm kết quả từ generator. Do đó nó không cần duyệt hết cây con nếu kết quả đã đủ.

Tuy nhiên, tại những nút **đã mở rộng**, mã `iter_matches` vẫn sắp danh sách con trước khi chuyển sang nút tiếp theo. Vì thế `limit=3` không có nghĩa chỉ thực hiện ba phép toán hoặc ba bước đi trong cây.

### 10.2. Khi tiền tố có ít hơn `k` khóa

Nếu chỉ có hai khóa bắt đầu bằng `"an"` mà `limit=10`, kết quả chứa **hai** khóa. Để biết không còn kết quả, generator phải duyệt hết cây con liên quan.

### 10.3. Bộ nhớ kết quả

`suggest_lex` trả một danh sách, nên giữ tất cả chuỗi đã tạo trong kết quả. Nếu muốn truyền từng kết quả ra giao diện hoặc một bộ xử lý phía sau, có thể dùng trực tiếp:

```python
for word, score in index.iter_matches("an"):
    print(word, score)
```

Khi đó không cần tạo sẵn danh sách toàn bộ, nhưng mọi kết quả được sử dụng vẫn có chi phí xuất tương ứng.

## 11. Gợi ý theo độ phổ biến: từ trie tới top-k

Autocomplete thực tế thường không xếp theo thứ tự ký tự. Người dùng có thể muốn kết quả **phổ biến hoặc phù hợp nhất** đứng trước.

Giả sử các khóa có điểm:

| Khóa | Điểm |
| --- | ---: |
| `an` | 10 |
| `anh` | 20 |
| `ao` | 15 |
| `an toàn` | 35 |

Với `prefix="a"` và `k=2`, nếu chỉ xếp từ điển thì có thể nhận `an, an toàn` (tùy bộ ký tự). Nhưng theo điểm giảm dần thì `an toàn` (35) và `anh` (20) phải đứng trước.

**Thứ tự từ điển và thứ tự theo điểm là hai hợp đồng khác nhau.** Trie giúp tìm cây con ứng viên; nó không tự quyết định ứng viên nào nổi bật nhất.

### 11.1. Cách đơn giản: lấy tất cả rồi sắp theo điểm

Quy trình:

1. Định vị tiền tố.
2. Liệt kê toàn bộ `C` khóa khớp, kèm điểm.
3. Sắp giảm dần theo điểm; hòa điểm thì theo tên khóa tăng.
4. Chọn `k` kết quả đầu.

Nếu `C` lớn và chỉ cần `k=5`, việc sắp cả `C` phần tử có thể lãng phí.

### 11.2. Dùng heap chọn top-k

Python có `heapq.nsmallest(k, iterable, key=...)`, cho phép giữ `k` ứng viên tốt nhất theo một khóa sắp xếp.

Để ưu tiên:

1. Điểm cao hơn trước.
2. Nếu hòa điểm, khóa tăng theo thứ tự ký tự.

ta dùng khóa:

```python
(-score, word)
```

Giá trị `-score` nhỏ nhất ứng với điểm cao nhất.

Bổ sung phương thức sau vào `TrieSearchIndex`:

```python
    def suggest_top_k(self, prefix="", k=5):
        """Top-k (word, score): score giảm, hòa điểm word tăng."""
        self._validate_text(prefix)
        self._validate_limit(k)

        if k is None:
            raise ValueError("k phải là số nguyên không âm")
        if k == 0:
            return []

        return nsmallest(
            k,
            self.iter_matches(prefix),
            key=lambda item: (-item[1], item[0]),
        )
```

Phương thức trên dùng `nsmallest` với heap trong thư viện chuẩn, không đòi tự cài Heap nhị phân. Nó vẫn **duyệt toàn bộ khóa ứng viên** vì chưa có thông tin điểm cao nhất được lưu sẵn trong các cây con.

### 11.3. Top-k cơ bản không phải O(P+k)

Gọi `C` là số khóa khớp tiền tố, `R` là số nút cây con được duyệt, `Z_{\mathrm{all}}` là tổng độ dài tất cả khóa ứng viên được tạo.

Một phân tích gần đúng cho cách `nsmallest` trên là:

\[
O\left(
P+R+Z_{\mathrm{all}}
+\sum_v d_v\log(d_v+1)
+C\log(\min(C,k)+1)
\right),
\]

dưới giả định so sánh điểm và tên khóa có giá phù hợp. Phần `C\log(\min(C,k)+1)` phản ánh lựa chọn bằng heap khi `k>0`; nếu `k\ge C`, thư viện có thể sắp toàn bộ ứng viên.

**Cẩn thận:** So sánh hai khóa chuỗi khi hòa điểm có thể phải đọc nhiều ký hiệu. Nếu đo chính xác thao tác ký tự, cần cộng chi phí so sánh tên khóa; các công thức đếm phép so sánh chỉ cho chặn theo **số phép so sánh** khi bỏ qua độ dài toán hạng.

Dù `k=1`, không có metadata bổ sung thì ta vẫn phải tìm hoặc xem xét đủ ứng viên để biết khóa nào có điểm cao nhất.

## 12. Kiểm thử đầy đủ với dữ liệu mẫu

Các đoạn sau được đặt **sau khi đã ghép đủ lớp `TrieSearchIndex` với ba phương thức `iter_matches`, `suggest_lex` và `suggest_top_k`**.

### 12.1. Liệt kê theo tiền tố

```python
index = TrieSearchIndex()

assert index.upsert("an", score=10)
assert index.upsert("anh", score=20)
assert index.upsert("ao", score=15)
assert index.upsert("ba", score=30)
assert index.upsert("ban", score=25)

assert len(index) == 5
assert index.contains("an")
assert not index.contains("a")
assert index.count_prefix("") == 5
assert index.count_prefix("a") == 3
assert index.count_prefix("an") == 2
assert index.count_prefix("ba") == 2
assert not index.has_key_with_prefix("ax")

assert index.suggest_lex("a") == ["an", "anh", "ao"]
assert index.suggest_lex("an") == ["an", "anh"]
assert index.suggest_lex("ba") == ["ba", "ban"]
assert index.suggest_lex("a", limit=2) == ["an", "anh"]
assert index.suggest_lex("a", limit=0) == []
assert index.suggest_lex("xyz") == []
```

### 12.2. Top-k theo điểm

```python
assert index.suggest_top_k("a", k=2) == [
    ("anh", 20),
    ("ao", 15),
]

# Thay điểm của khóa cũ không làm tăng số khóa.
assert not index.upsert("an", score=25)
assert len(index) == 5
assert index.count_prefix("an") == 2

assert index.suggest_top_k("a", k=2) == [
    ("an", 25),
    ("anh", 20),
]

# Điểm hòa nhau: tên khóa tăng trước.
assert not index.upsert("anh", score=25)
assert index.suggest_top_k("a", k=2) == [
    ("an", 25),
    ("anh", 25),
]
```

### 12.3. Xóa khóa là tiền tố của khóa khác

```python
assert index.delete("an")
assert not index.contains("an")
assert index.contains("anh")
assert index.count_prefix("an") == 1
assert index.suggest_lex("an") == ["anh"]
assert not index.delete("an")

assert index.delete("anh")
assert index.count_prefix("an") == 0
assert index.suggest_lex("an") == []
assert index.contains("ao")
```

### 12.4. Chuỗi rỗng là một khóa hợp lệ

```python
empty = TrieSearchIndex()

assert empty.suggest_lex("") == []
assert empty.count_prefix("") == 0

assert empty.upsert("", score=100)
assert empty.contains("")
assert empty.count_prefix("") == 1
assert empty.suggest_lex("") == [""]
assert empty.suggest_top_k("", k=1) == [("", 100)]

assert empty.upsert("a", score=1)
assert empty.suggest_lex("", limit=2) == ["", "a"]

assert empty.delete("")
assert not empty.contains("")
assert empty.suggest_lex("") == ["a"]
```

### 12.5. Không có kết quả và giới hạn quá lớn

```python
assert index.suggest_top_k("ax", k=5) == []
assert index.suggest_lex("ba", limit=100) == ["ba", "ban"]
assert index.suggest_top_k("ba", k=100) == [
    ("ba", 30),
    ("ban", 25),
]
```

**Lưu ý:** Những `assert` kiểm tra hành vi theo hợp đồng, không phải phép đo hiệu năng. Với ứng dụng thực tế còn phải kiểm tra chuẩn hóa Unicode, việc điểm thay đổi theo thời gian và truy vấn đồng thời.

## 13. Bất biến của số khóa và cập nhật điểm

Trong `TrieSearchIndex`, `subtree_count` đếm **số khóa phân biệt**, không phải tổng điểm.

Ví dụ cây con `"a"` có ba khóa:

```text
an:  10 điểm
anh: 20 điểm
ao:  15 điểm
```

Bộ đếm tại nút `a` là **3**, không phải 45.

### 13.1. Khi thêm khóa mới

Nếu `upsert("ang",score=50)` thêm một khóa mới:

- Tạo các nút/cạnh thiếu.
- Đặt `terminal=True` ở nút cuối.
- Tăng `subtree_count` đúng 1 tại các nút từ gốc tới khóa mới.
- Gắn `score=50` tại nút cuối.

### 13.2. Khi thay điểm khóa cũ

Nếu `upsert("anh",score=99)` khi `anh` đã có:

- **Không** tăng `len` hoặc `subtree_count`.
- Chỉ thay `score` của nút terminal.
- Nếu ứng dụng có cache top-k ở tổ tiên, phải cập nhật hoặc vô hiệu hóa cache ấy.

### 13.3. Khi xóa

Nếu xóa `an` nhưng còn `anh`:

- Bỏ terminal và điểm tại nút `an`.
- Giảm số khóa trong các cây con trên đường đi.
- Giữ nút `an` và nhánh `h` vì vẫn còn `anh`.
- Khi cây con của một nút có `subtree_count=0`, có thể cắt nhánh ấy từ dưới lên.

Cách xóa này giữ đúng cả `contains`, `count_prefix` và autocomplete.

### 13.4. Một lỗi logic khó phát hiện

Nếu chèn một từ trùng và vẫn tăng bộ đếm, `contains` và `suggest_lex` có thể **vẫn trông đúng** vì terminal không bị thay đổi, nhưng `count_prefix` sẽ quá lớn. Khi đó hệ thống có thể báo “có 10 kết quả” trong khi chỉ xuất được 9 khóa.

Nên kiểm thử cả danh sách gợi ý **và** số lượng tiền tố sau chuỗi cập nhật.

## 14. Kiểm tra bất biến và đối chiếu với tập tham chiếu

Bên cạnh các `assert` theo ví dụ, ta nên kiểm tra cấu trúc của toàn trie sau nhiều lần chèn/xóa.

### 14.1. Kiểm tra số khóa trong cây con

Đoạn kiểm tra dưới dùng DFS lặp để tránh giới hạn đệ quy:

```python
def validate_index(index):
    totals = {}
    seen = set()
    stack = [(index._root, False)]

    while stack:
        node, expanded = stack.pop()

        if not expanded:
            assert id(node) not in seen
            seen.add(id(node))

            stack.append((node, True))
            for ch, child in node.children.items():
                assert isinstance(ch, str) and len(ch) == 1
                stack.append((child, False))
        else:
            expected = int(node.terminal)

            for child in node.children.values():
                assert child.subtree_count > 0
                expected += totals[id(child)]

            assert node.subtree_count == expected
            totals[id(node)] = expected

    assert totals[id(index._root)] == len(index)


check = TrieSearchIndex()
for word, score in [("an", 2), ("anh", 8), ("ao", 1)]:
    check.upsert(word, score)
    validate_index(check)

check.upsert("anh", score=12)  # Chỉ đổi điểm.
validate_index(check)
check.delete("an")
validate_index(check)
check.delete("anh")
validate_index(check)
check.delete("ao")
validate_index(check)
assert len(check) == 0
```

Hàm này duyệt toàn bộ nút để kiểm tra nên dùng trong unit test hoặc debug, **không cần chạy sau mỗi cập nhật** trong hệ thống có lưu lượng lớn.

### 14.2. Dùng `set` làm mô hình độc lập

Có thể so danh sách gợi ý với các khóa lấy từ `set`:

```python
def check_suggestions_against_set(index, reference, prefixes):
    assert len(index) == len(reference)

    for prefix in prefixes:
        expected = sorted(
            word for word in reference
            if word.startswith(prefix)
        )
        assert index.suggest_lex(prefix) == expected
        assert index.count_prefix(prefix) == len(expected)


index = TrieSearchIndex()
reference = set()

for word in ["an", "anh", "ao", "an", "ba", "ban"]:
    index.upsert(word, score=0)
    reference.add(word)
    check_suggestions_against_set(
        index, reference, ["", "a", "an", "b", "x"]
    )

for word in ["an", "missing", "ba", "anh", "ban", "ao"]:
    index.delete(word)
    reference.discard(word)
    check_suggestions_against_set(
        index, reference, ["", "a", "an", "b", "x"]
    )
```

Bộ kiểm tra có thể quét toàn bộ `reference` và sắp nhiều khóa, nhưng đó là **chi phí chấp nhận được của bài kiểm thử**, không phải chi phí cần chạy khi phục vụ truy vấn.

## 15. Cải thiện top-k bằng metadata ở cây con

Phương án `suggest_top_k` ở mục 11 xem mọi khóa khớp rồi dùng heap chọn `k` tốt nhất. Nếu mỗi tiền tố có hàng triệu khóa nhưng người dùng chỉ muốn 5 gợi ý, đây có thể là nút thắt.

Một hướng tối ưu là **lưu thêm dữ liệu tổng hợp ở các nút**.

### 15.1. Lưu `max_score` ở mỗi nút

Cho mỗi nút `v`:

\[
maxScore(v)=
\max\{\operatorname{score}(s):s \text{ là khóa terminal trong cây con }v\}.
\]

Nếu không có khóa trong cây con, có thể dùng một giá trị canh gác (sentinel) hoặc `None`.

Khi tìm top-k:

1. Định vị nút tiền tố.
2. Dùng hàng đợi ưu tiên (*priority queue*) chứa các cây con theo **điểm trần** `maxScore`.
3. Ưu tiên mở cây con có khả năng chứa khóa điểm cao.
4. Khi đã có `k` kết quả và mọi nhánh chưa thăm đều có điểm tối đa không vượt ngưỡng cạnh tranh, có thể dừng nếu quy tắc phá hòa cũng được xử lý chính xác.

Như vậy có thể tránh **một phần** công việc trên cây con điểm thấp. Tuy nhiên, trong trường hợp xấu nhất vẫn có thể phải xét rất nhiều ứng viên, đặc biệt khi nhiều điểm bằng nhau.

### 15.2. Phá hòa điểm phải được thiết kế cẩn thận

Nếu sắp theo `(-score,word)`, chỉ lưu `max_score` là chưa đủ để quyết định chắc chắn khóa nào thắng khi **nhiều khóa có cùng điểm**. Cần thêm thông tin để phá hòa hoặc tiếp tục khám phá những nhánh có điểm ngang nhau.

Không được dừng ngay khi thấy một nhánh chưa xét có `max_score` bằng điểm thấp nhất trong top-k hiện tại rồi mặc định nó không thể tạo kết quả tốt hơn.

### 15.3. Cache danh sách top-k ở từng nút

Một lựa chọn khác là lưu sẵn **`k` khóa tốt nhất** cho mỗi nút tiền tố.

Ưu điểm:

- Sau khi đi tới nút tiền tố, đọc danh sách cache có thể nhanh.
- Hữu ích khi cùng một tiền tố được hỏi rất nhiều lần.

Nhược điểm:

- Mỗi khóa có thể xuất hiện trong cache của **nhiều tổ tiên**, làm tăng bộ nhớ.
- Thêm/xóa hoặc đổi điểm một khóa có thể yêu cầu cập nhật các cache trên đường dài `L`.
- Nếu một khóa đang ở top-k bị xóa, cần tìm khóa thay thế từ cây con; không thể chỉ xóa mục cache và coi danh sách còn đúng.
- Cache phải được vô hiệu hóa hoặc cập nhật nếu dữ liệu thay đổi.

Đây là đánh đổi điển hình: **trả thêm chi phí cập nhật và bộ nhớ để giảm chi phí đọc**.

### 15.4. Phân biệt điểm gắn với từ và thứ hạng phụ thuộc truy vấn

Một điểm cố định cho khóa phù hợp khi xếp theo độ phổ biến chung. Nhưng trong hệ tìm kiếm thật, thứ hạng có thể phụ thuộc vị trí, ngữ cảnh, lịch sử người dùng hoặc từ khóa khác. Khi đó `score(word)` không còn là giá trị bất biến duy nhất.

Cache top-k theo tiền tố có thể không dùng lại được cho mọi ngữ cảnh. Phải xác định **những tham số nào ảnh hưởng điểm** trước khi quyết định lưu metadata ở nút.

## 16. Unicode, chuẩn hóa và định nghĩa thứ tự từ điển

Trie trong mã Python trên duyệt `for ch in word`, tức một cạnh cho **một Unicode code point**. Dữ liệu tiếng Việt có thể có nhiều cách biểu diễn cùng một chữ hiển thị.

### 16.1. Hai chuỗi hiển thị giống nhau có thể khác đường đi

```python
import unicodedata

composed = "bàn"
decomposed = "ba\u0300n"

assert composed != decomposed
assert (
    unicodedata.normalize("NFC", composed)
    == unicodedata.normalize("NFC", decomposed)
)
```

Nếu ứng dụng muốn coi chúng là **một từ khóa**, cần chuẩn hóa trước khi `upsert`, `contains`, `delete` và `suggest_lex`. Không thể chỉ chuẩn hóa lúc thêm mà bỏ qua lúc tìm tiền tố.

### 16.2. Ví dụ lớp bao chuẩn hóa

```python
import unicodedata


def normalize_key(text):
    if not isinstance(text, str):
        raise TypeError("khóa phải là str")
    return unicodedata.normalize("NFC", text.casefold())


index = TrieSearchIndex()
index.upsert(normalize_key("Bàn"), score=10)

assert index.contains(normalize_key("ba\u0300n"))
assert index.suggest_lex(normalize_key("BÀ")) == ["bàn"]
```

`casefold()` hỗ trợ tìm không phân biệt hoa/thường theo quy tắc Unicode, nhưng nó có thể thay đổi dãy code point. `NFC` đưa nhiều dạng tổ hợp tương đương về một biểu diễn chuẩn. **Đây không phải phép bỏ dấu:** `ban` và `bàn` vẫn là hai khóa khác nhau.

### 16.3. Tại sao thứ tự code point chưa chắc là thứ tự từ điển tiếng Việt?

Hàm `sorted` của Python so sánh chuỗi theo thứ tự code point Unicode. Thứ tự ấy không nhất thiết đúng **quy tắc sắp xếp ngôn ngữ tự nhiên** hoặc tiêu chuẩn tìm kiếm sản phẩm.

Nếu hợp đồng yêu cầu thứ tự từ điển tiếng Việt, có thể cần:

- Một quy tắc collation phù hợp và nhất quán.
- Sắp **toàn bộ các khóa khớp** theo khóa collation thay vì chỉ sắp các cạnh theo code point.
- Hoặc một cấu trúc chỉ mục được thiết kế phù hợp với thứ tự collation được chọn.

Không được hứa “đúng thứ tự tiếng Việt” chỉ vì các nhánh con đã được `sorted` theo code point.

### 16.4. Chuẩn hóa có thể đổi độ dài tiền tố

Một chuỗi với dấu kết hợp có thể có số code point khác chuỗi đã chuẩn hóa. Vì vậy:

- `P` trong phân tích chi phí là độ dài tiền tố **sau khi chọn biểu diễn và quy tắc chuẩn hóa**.
- Phải tính thêm chi phí chuẩn hóa nếu đánh giá **toàn bộ truy vấn**, không chỉ phần đi theo cạnh.
- Khi người dùng đang gõ dở một ký tự có dấu, ứng dụng có thể cần xử lý sự kiện nhập liệu theo quy tắc riêng.

## 17. Phân trang, cập nhật và tính ổn định của kết quả

Một chỉ mục có thể trả hàng triệu kết quả cho tiền tố rỗng hoặc tiền tố phổ biến. Khi ấy nên cân nhắc phân trang hoặc streaming thay vì gửi toàn bộ kết quả.

### 17.1. Phân trang bằng `offset` có thể tốn nhiều công việc

Giả sử muốn trang 100, mỗi trang 20 kết quả, trong danh sách từ điển. Nếu thuật toán mỗi lần bắt đầu từ nút tiền tố rồi bỏ qua `99×20=1980` khóa trước trang cần lấy, thời gian vẫn phụ thuộc những khóa phải bỏ qua.

Không được suy rằng lấy trang thứ 100 là O(20) chỉ vì chỉ **trả** 20 khóa.

### 17.2. Cursor lưu trạng thái duyệt

Một cursor có thể ghi trạng thái DFS (các nút và vị trí nhánh tiếp theo), giúp tiếp tục từ nơi đang dừng. Tuy nhiên, khi dữ liệu được cập nhật:

- Các nút bị xóa có thể làm con trỏ tới nhánh cũ không còn hợp lệ.
- Khóa mới có thể được thêm trước hoặc sau vị trí hiện tại theo thứ tự.
- Điểm xếp hạng có thể đổi làm thứ tự top-k thay đổi.

Hệ thống cần quy định cursor theo **snapshot cố định**, **phiên bản chỉ mục**, hoặc chấp nhận kết quả có thể đổi giữa các trang.

### 17.3. `last_key` làm mốc tiếp tục

Một phương án khác là lưu **khóa cuối cùng đã xuất** và yêu cầu trang tiếp theo bắt đầu sau khóa ấy. Muốn làm hiệu quả phải có thuật toán tìm **khóa kế tiếp trong thứ tự** dưới một tiền tố, không đơn giản lặp toàn bộ DFS và bỏ qua kết quả cũ.

Nếu có thêm cập nhật, cơ chế này vẫn cần chính sách về khóa mới, khóa đã xóa và tính ổn định thứ tự.

### 17.4. Không thay đổi trie giữa chừng khi duyệt generator đơn giản

Mã ở mục 9 không có khóa đồng bộ hay snapshot. Nếu vừa duyệt vừa xóa nút, các frame Stack có thể còn tham chiếu tới nút không còn thuộc chỉ mục; nếu thêm khóa, một số nhánh mới có thể được thấy, một số không.

Vì vậy nên nêu ràng buộc **không cập nhật trong thời gian duyệt**, hoặc xây cơ chế snapshot/phiên bản rõ ràng nếu hệ thống cần đọc và ghi đồng thời.

## 18. Những truy vấn nào không phải truy vấn tiền tố?

Autocomplete bằng trie rất hữu ích, nhưng không nên dùng nó như câu trả lời mặc định cho mọi dạng tìm kiếm chuỗi.

| Nhu cầu | Ví dụ | Trie tiền tố cơ bản có hỗ trợ trực tiếp? |
| --- | --- | --- |
| Khóa bắt đầu bằng chuỗi | `an...` | Có |
| Tìm đúng khóa | `contains("anh")` | Có |
| Đếm khóa theo tiền tố | `count_prefix("an")` | Có nếu duy trì count, hoặc duyệt cây con |
| Tìm một đoạn ở giữa khóa | Từ có chứa `"nh"` | Không trực tiếp, có thể cần quét hoặc chỉ mục con |
| Tìm hậu tố | Từ kết thúc bằng `"anh"` | Không trực tiếp; có thể cân nhắc trie trên chuỗi đảo |
| Sửa lỗi gõ một ký tự | `"ahn"` gần `"anh"` | Cần thuật toán tìm gần đúng, ví dụ theo khoảng cách chỉnh sửa |
| Đa từ và xếp hạng ngữ nghĩa | “cấu trúc dữ liệu” | Cần quy tắc tách từ, lập chỉ mục và xếp hạng bổ sung |

Một trie có thể là **thành phần** của hệ thống tìm kiếm lớn, nhưng việc đổi từ tìm tiền tố sang tìm gần đúng hoặc tìm đoạn con thường làm thay đổi cả thuật toán và độ phức tạp.

### 18.1. Trie đảo cho truy vấn hậu tố

Nếu đảo mỗi khóa trước khi lưu, tiền tố của chuỗi đảo tương ứng **hậu tố của chuỗi gốc**. Ví dụ:

```text
"anh" đảo thành "hna"
"lanh" đảo thành "hnal"
```

Muốn tìm các từ kết thúc bằng `"anh"`, có thể truy vấn tiền tố `"hna"` trên trie đảo, rồi đảo ngược các kết quả. Tuy nhiên, việc đảo chuỗi, chuẩn hóa và xây thêm chỉ mục có chi phí bộ nhớ–thời gian riêng.

### 18.2. Tìm gần đúng không đơn giản là DFS mọi nhánh

Khi cho phép sai chính tả, thuật toán có thể phối hợp trie với trạng thái quy hoạch động của khoảng cách chỉnh sửa để cắt nhánh không thể tạo kết quả tốt. Chi phí tùy độ dài chuỗi, ngưỡng lỗi và số nút được duyệt; không còn chặn O(P) như tìm tiền tố chính xác.

## 19. Các lỗi triển khai thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Trả mọi nút đi qua khi duyệt | Trả cả các tiền tố không phải khóa | Chỉ phát nút `terminal=True` |
| Quên phát chính nút tiền tố nếu terminal | Bỏ sót `an` trong `{an,anh}` | Kiểm tra nút bắt đầu trước khi thăm con |
| Chỉ tìm nút tiền tố rồi kết luận autocomplete O(P) | Bỏ qua việc duyệt, sắp và xuất | Phân tích thêm `R,Z` và chi phí sắp nhánh |
| Dùng Stack nhưng đẩy nhãn tăng rồi pop LIFO | Thứ tự kết quả bị đảo | Đẩy nhãn **giảm** để thăm tăng |
| Tạo `prefix+ch` trên mọi cạnh mà không tính chi phí | Có thể sao chép chuỗi nhiều lần | Dùng `path` và sự kiện vào/ra, hoặc cộng chi phí sao chép |
| Dùng BFS rồi tuyên bố kết quả luôn tăng từ điển | BFS ưu tiên chiều sâu, không phải thứ tự từ điển | Định nghĩa và chọn chiến lược duyệt đúng |
| Cho `limit=k` nên tuyên bố O(k) | Có thể đi qua nhiều nút trước khi tìm đủ kết quả | Đếm số nút thăm và độ dài đường |
| Gọi `sorted(dict)` ở mỗi nút nhưng bỏ chi phí | Có thể sắp nhiều nhánh lặp lại | Cộng `d\log(d+1)` hoặc giữ nhánh có thứ tự |
| Dùng heap top-k rồi coi như chỉ đọc `k` khóa | Heap cơ bản vẫn phải nhận toàn bộ ứng viên | Phân biệt chọn top-k với pruning theo metadata |
| Khi cập nhật điểm, tăng `subtree_count` | Số khóa theo tiền tố bị sai | Chỉ tăng khi khóa mới chuyển thành terminal |
| Xóa một tiền tố và cắt mất các từ dài hơn | Mất kết quả autocomplete hợp lệ | Chỉ dọn cây con còn 0 khóa |
| Lưu top-k cache mà không invalidation | Gợi ý cũ, sai thứ hạng | Cập nhật hoặc đánh dấu dirty trên đường tiền tố |
| Dùng thứ tự Unicode mặc định để khẳng định thứ tự từ điển tiếng Việt | Gợi ý có thể không theo mong muốn sản phẩm | Định nghĩa collation và kiểm thử |
| Chuẩn hóa chỉ khi chèn, không khi truy vấn | Không tìm thấy từ có biểu diễn khác | Chuẩn hóa nhất quán |
| Duyệt generator đồng thời với cập nhật | Kết quả có thể không ổn định | Snapshot/khóa/version hoặc cấm sửa khi duyệt |
| Dùng offset phân trang rồi báo O(page_size) | Phải đi qua nhiều kết quả bị bỏ | Dùng cursor/successor có đặc tả rõ |

## 20. Bài tập vận dụng có gợi ý giải

### Bài 1 — Xác định cây con cần duyệt

Trie lưu `{an,anh,ao,ba,ban,bao}`. Khi liệt kê với `prefix="ba"`, nút bắt đầu là nút nào và các khóa nào phải được xuất?

**Gợi ý:** Đi từ gốc theo `b→a`. Nút `ba` là terminal, sau đó các nhánh `n` và `o` tạo `ban` và `bao`. Kết quả `ba,ban,bao`; không duyệt nhánh `a` ở gốc.

### Bài 2 — Đường có nhưng không phải khóa

Trie chỉ chứa `{"anh"}`. Với `prefix="a"`, kết quả autocomplete theo thứ tự từ điển phải là gì?

**Gợi ý:** Chỉ có `["anh"]`. Nút `a` và `an` tồn tại nhưng không terminal, nên không được xuất.

### Bài 3 — Thứ tự DFS

Trie chứa `{"an","anh","ang","ao"}`. Nếu duyệt DFS và tại mỗi nút thăm các con theo nhãn tăng, hãy ghi thứ tự khóa.

**Gợi ý:** `["an","ang","anh","ao"]`. Phát `an` trước các hậu duệ; nhánh `g` được đi trước `h`.

### Bài 4 — DFS khác BFS

Trie chứa `{"a","ab","ac","b"}`. So sánh thứ tự theo DFS nhãn tăng và BFS theo chiều sâu, giả sử ở mỗi tầng xử lý nhãn tăng.

**Gợi ý:** DFS: `a,ab,ac,b`. BFS: `a,b,ab,ac`. Muốn kết quả từ điển, dùng DFS theo thứ tự con phù hợp.

### Bài 5 — Tác động của `limit`

Trie có nhiều khóa rất dài nhưng chỉ cần `limit=1`. Có thể khẳng định thời gian O(1) không?

**Gợi ý:** Không. Phải tìm nút tiền tố và đi tới một nút terminal, có thể qua một đường dài; thêm chi phí lấy/sắp nhánh.

### Bài 6 — Chi phí đầu ra

Một truy vấn trả 1.000 khóa, mỗi khóa dài 30 code point. Tổng `Z` là bao nhiêu? Cần ít nhất bao nhiêu công việc tạo ký hiệu nếu xây chuỗi kết quả mới?

**Gợi ý:** `Z=30.000` code point. Cận dưới cho việc tạo nội dung đầu ra là Ω(30.000) thao tác ghi ký hiệu theo mô hình đó.

### Bài 7 — Sao chép chuỗi trung gian

Một nhánh duy nhất dài `H` ký hiệu. Nếu tại mỗi cạnh dùng `current+ch`, tổng số ký hiệu sao chép có thể là bao nhiêu theo bậc tăng trưởng?

**Gợi ý:** `1+2+\cdots+H=\Theta(H^2)`. Dùng danh sách `path` và chỉ `join` ở terminal có thể tránh nhiều chuỗi trung gian.

### Bài 8 — Chọn top-k theo điểm

Các khóa có điểm `an:10`, `anh:20`, `ao:15` và `ang:20`. Với `prefix="a"` và `k=2`, hãy trả theo điểm giảm, hòa điểm thì khóa tăng.

**Gợi ý:** `[("ang",20),("anh",20)]`, vì `ang` đứng trước `anh` theo thứ tự code point.

### Bài 9 — Vì sao heap vẫn quét ứng viên?

Một tiền tố có 100.000 khóa. Thuật toán duyệt mọi kết quả rồi gọi `heapq.nsmallest(5,...)` có phải chỉ xem 5 khóa không?

**Gợi ý:** Không. Nó phải nhận toàn bộ ứng viên để xác định 5 khóa tốt nhất, dù chỉ giữ một số lượng ứng viên nhỏ trong bộ nhớ lựa chọn.

### Bài 10 — Bộ đếm khi thay điểm

Trie lưu `an` và `anh` với điểm 5 và 10. Cập nhật `an` thành điểm 50. `count_prefix("an")` thay đổi không?

**Gợi ý:** Không; vẫn có hai khóa phân biệt. Chỉ điểm `an` đổi, còn bộ đếm đếm terminal trong cây con.

### Bài 11 — Xóa từ là tiền tố

Trie chứa `{an,anh,ang}`. Sau `delete("an")`, `suggest_lex("an")` trả gì và vì sao?

**Gợi ý:** `["ang","anh"]`. Nút `an` không còn terminal nhưng vẫn giữ các nhánh `g,h` vì hai khóa dài còn sống.

### Bài 12 — Prefix rỗng

Theo hợp đồng của bài, chỉ mục chưa có khóa trả gì cho `count_prefix("")` và `suggest_lex("")`? Sau khi thêm khóa `""` thì sao?

**Gợi ý:** Ban đầu 0 và `[]`. Sau khi thêm chuỗi rỗng, bộ đếm là 1 và danh sách chứa `[""]`. Gốc có thể terminal.

### Bài 13 — Unicode và dấu kết hợp

Vì sao chèn `"bàn"` rồi truy vấn `"ba\u0300"` có thể không đi đúng đường nếu chưa chuẩn hóa, dù giao diện hiển thị giống nhau?

**Gợi ý:** Hai chuỗi có thể dùng dãy code point khác nhau. Chuẩn hóa cùng quy tắc, ví dụ NFC, khi thêm và truy vấn.

### Bài 14 — Cache top-k bị lỗi sau cập nhật

Nút `a` cache hai khóa `an` và `anh` có điểm cao nhất. Ứng dụng xóa `anh` nhưng không cập nhật cache. Lỗi nào xuất hiện?

**Gợi ý:** Autocomplete có thể vẫn trả một khóa đã xóa. Cần invalidation/cập nhật cache và tìm ứng viên thay thế nếu cần đủ hai kết quả.

### Bài 15 — Phân trang offset

Trang 50 có 20 kết quả. Nếu mỗi lần từ gốc duyệt và bỏ qua 49 trang trước, ít nhất bao nhiêu khóa có thể phải được duyệt/bỏ trước khi tới trang cần?

**Gợi ý:** `49\cdot20=980` kết quả trước trang 50, chưa kể nút trung gian. Do đó không phải chỉ O(20).

### Bài 16 — Trie có đúng loại truy vấn không?

Ứng dụng cần tìm mọi từ **chứa** đoạn `"nh"` ở bất kỳ vị trí nào, không bắt buộc đầu từ. Trie tiền tố cơ bản có truy vấn trực tiếp O(P) cho yêu cầu đó không?

**Gợi ý:** Không. Trie tiền tố tổ chức theo phần đầu; cần chỉ mục đoạn con, duyệt các khóa, hoặc cấu trúc bổ sung thích hợp.

### Bài 17 — Bộ nhớ DFS và BFS

Một cây con có một tầng chứa 20.000 nút. DFS và BFS giữ trạng thái có thể khác nhau thế nào?

**Gợi ý:** BFS có thể cần giữ nhiều nút của cả tầng trong Queue. DFS giữ đường hiện tại và những nhánh đang chờ; trong trường hợp rộng cũng có thể giữ nhiều frame, nhưng cơ chế và đỉnh sử dụng có thể khác. Không có bảo đảm rằng DFS luôn O(H) bộ nhớ nếu nó đẩy toàn bộ anh em vào Stack.

### Bài 18 — Chọn thiết kế theo workload

Hệ thống có rất nhiều truy vấn tiền tố giống nhau, mỗi truy vấn muốn 5 gợi ý điểm cao, trong khi dữ liệu ít thay đổi. So sánh top-k quét toàn bộ cây con với cache top-5 tại từng nút.

**Gợi ý:** Quét toàn bộ dễ cài, cập nhật đơn giản và ít metadata hơn nhưng trả giá mỗi lần truy vấn. Cache top-5 giúp đọc nhanh với truy vấn lặp lại, đổi lại bộ nhớ và chi phí cập nhật/invalidation lớn; phải xét tần suất và độ dài khóa.

## 21. Checklist thiết kế một dịch vụ autocomplete

Dùng mẫu sau để chuẩn bị trước khi triển khai:

```text
1. Hợp đồng:
   - contains(word) hay liệt kê khóa theo prefix?
   - Kết quả là chuỗi, ID, bản ghi hay (chuỗi, điểm)?
   - Có giới hạn limit và yêu cầu phân trang?
   - Prefix rỗng có được dùng để xem mọi khóa?

2. Chuỗi và thứ tự:
   - Ký hiệu là byte, Unicode code point hay grapheme?
   - Có chuẩn hóa NFC, casefold, bỏ dấu không?
   - Thứ tự từ điển theo code point hay collation?
   - Top-k theo điểm, tần suất hay ngữ cảnh nào?

3. Bất biến:
   - terminal xác định đúng khóa hoàn chỉnh?
   - subtree_count bằng số terminal ở cây con?
   - Chèn trùng/chỉnh điểm không tăng số khóa?
   - Xóa không làm mất hậu duệ có cùng tiền tố?

4. Thuật toán:
   - LOCATE tiền tố trước khi duyệt?
   - DFS hay BFS phù hợp thứ tự?
   - Có cần sorted(children) mỗi lần không?
   - Sử dụng generator, limit và dừng sớm?
   - Có sao chép prefix ở mọi cạnh không?

5. Độ phức tạp:
   - P: chiều dài tiền tố?
   - R: số nút thật sự được thăm?
   - C: số khóa được xét hoặc phát?
   - Z: tổng ký hiệu đầu ra?
   - d_v, sigma: chi phí liệt kê nhánh?
   - Với top-k: có quét hết C ứng viên?

6. Dịch vụ thực tế:
   - Có nhiều truy vấn lặp lại cần cache không?
   - Thêm/xóa/đổi điểm phải invalidation những gì?
   - Phân trang dùng offset, last_key hay cursor?
   - Có snapshot hoặc phiên bản khi cập nhật đồng thời?
   - Đã đo bộ nhớ, p95/p99 độ trễ và chất lượng kết quả?

7. Kiểm thử:
   - Nút tiền tố terminal và không terminal.
   - Prefix không tồn tại, prefix rỗng.
   - Limit=0, limit lớn hơn số kết quả.
   - Điểm hòa, thay điểm, xóa khóa đang top-k.
   - Unicode và chuẩn hóa nhất quán.
   - So kết quả với tập tham chiếu sau nhiều cập nhật.
```

**Kết luận:** Trie biến truy vấn “tất cả khóa bắt đầu bằng một tiền tố” thành bài toán **tìm một nút rồi duyệt cây con**, tránh phải xét mọi khóa không liên quan. Nhưng truy vấn gợi ý hoàn chỉnh còn có chi phí **đi qua nút, sắp nhánh, tạo chuỗi, chọn top-k và cập nhật thông tin xếp hạng**. DFS theo nhãn tăng thích hợp cho liệt kê từ điển; heap giúp chọn top-k theo điểm nhưng không tự tránh việc đọc ứng viên; metadata và cache có thể giảm thời gian đọc để đổi lấy RAM và chi phí cập nhật. Khi đặc tả rõ terminal, thứ tự, Unicode, giới hạn kết quả và các tham số `P,R,C,Z`, ta có thể xây hệ thống gợi ý đúng về hành vi và lựa chọn phương án có chi phí phù hợp với workload thực tế.
