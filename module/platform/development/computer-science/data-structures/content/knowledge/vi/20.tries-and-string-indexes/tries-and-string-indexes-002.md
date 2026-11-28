# Nút kết thúc khóa và sự khác biệt giữa tiền tố với khóa hoàn chỉnh

> **Chương:** Trie và chỉ mục chuỗi · **Bài học:** Nút kết thúc khóa và sự khác biệt giữa tiền tố với khóa hoàn chỉnh

Một Trie có thể chứa đường đi tương ứng với chuỗi `"an"` ngay cả khi ứng dụng **chưa lưu `"an"` như một khóa**. Chẳng hạn, nếu chỉ thêm `"anh"` thì các nút `a`, `an` và `anh` đều tồn tại trên cây; nhưng chỉ `anh` là từ đã được thêm. Ngược lại, nếu thêm cả `"an"` lẫn `"anh"`, nút `an` vừa kết thúc một khóa, vừa có con để biểu diễn khóa dài hơn.

Điểm phân biệt này nằm ở **nút kết thúc khóa** (*terminal node*, còn gọi là *end-of-word marker*). Nếu bỏ qua nó, thao tác kiểm tra tiền tố và thao tác tìm khóa đầy đủ dễ bị viết giống nhau, dẫn đến kết quả sai, xóa nhầm các từ có chung tiền tố hoặc đếm khóa trùng.

Bài này thuộc chương **Trie và chỉ mục chuỗi** trong mô-đun **Cấu trúc dữ liệu** (`COMPUTER_SCIENCE_DATA_STRUCTURES`). Chúng ta sẽ học cách đặc tả hành vi, giữ bất biến và phân tích thời gian–bộ nhớ khi sử dụng cây tiền tố. Những nguyên tắc này cũng liên quan đến cách thiết kế Map, Set, cây, bảng băm và các cấu trúc lưu trữ khác: **hình dạng nội bộ không thay thế hợp đồng thao tác**.

## 1. Mục tiêu học tập

Sau khi học xong, bạn có thể:

1. Nêu chính xác ý nghĩa của **đường đi tiền tố** và **dấu kết thúc khóa** trong Trie.
2. Phân biệt `contains(word)`, `starts_with(prefix)`, `count_prefix(prefix)` và truy vấn “khóa đã lưu nào là tiền tố của chuỗi đầu vào?”.
3. Giải thích vì sao một nút có thể **vừa là terminal vừa có nút con**, và vì sao một nút lá không nhất thiết là cách biểu diễn duy nhất cho một khóa.
4. Đặc tả rõ trường hợp **chuỗi rỗng**, Trie rỗng, thêm trùng và xóa một khóa vốn là tiền tố của khóa khác.
5. Cài đặt và kiểm thử Python Trie dạng Set với dấu `terminal`, bộ đếm cây con và dọn nhánh đúng.
6. Chứng minh thao tác chèn/xóa giữ bất biến, không làm mất những khóa còn được lưu.
7. Phân tích độ phức tạp theo **độ dài khóa hoặc tiền tố**, số lượng khóa trong cây con và kích thước kết quả.
8. Nhận biết tác động của Unicode, chuẩn hóa khóa và khác biệt giữa lưu Set với lưu Map.

## 2. Hai sự kiện logic phải được tách riêng

Gọi `S` là **tập các khóa hoàn chỉnh** đã được chèn vào Trie. Với chuỗi `x`, ta định nghĩa:

- `x ∈ S`: **`x` là khóa đầy đủ đã lưu**.
- `x` là tiền tố của một khóa `s ∈ S`: tồn tại `y` sao cho `s = x + y`.

Ký hiệu `x \preceq s` nghĩa là `x` là **tiền tố** của `s`; phần nối thêm `y` được phép rỗng. Vì vậy một chuỗi luôn là tiền tố của **chính nó**.

Hai tính chất cần phân biệt:

\[
\operatorname{isKey}(x)\iff x\in S
\]

\[
\operatorname{hasCompletion}(x)\iff
\exists s\in S:\ x\preceq s.
\]

Nếu `x` là khóa đã lưu thì `hasCompletion(x)` chắc chắn đúng, vì `x\preceq x`. Chiều ngược lại **không đúng**: `"a"` có thể là tiền tố của `"an"` dù `"a"` không nằm trong tập khóa.

### 2.1. Ví dụ tối giản

Giả sử:

```text
S = {"anh"}
```

Khi đó:

| Chuỗi `x` | Có đường đi từ gốc? | `isKey(x)` | `hasCompletion(x)` |
| --- | --- | --- | --- |
| `""` | Có — chính gốc | Sai | Đúng |
| `"a"` | Có | Sai | Đúng |
| `"an"` | Có | Sai | Đúng |
| `"anh"` | Có | Đúng | Đúng |
| `"ang"` | Không | Sai | Sai |
| `"anhx"` | Không | Sai | Sai |

Khi thêm `"an"` vào tập khóa, ta **không cần tạo lại** các cạnh `a→n`. Ta chỉ đổi trạng thái của nút `an` từ “chỉ là tiền tố” sang “cũng là khóa hoàn chỉnh”.

### 2.2. Vì sao cây không thể tự suy ra khóa chỉ từ cạnh?

Các cạnh chỉ cho biết **một dãy ký hiệu có thể xuất hiện ở đầu khóa**. Chúng không trả lời được câu hỏi: “Ứng dụng đã chấp nhận chính dãy ký hiệu này là một khóa hay chưa?”.

Ví dụ, cùng một đường:

```text
root --a--> A --n--> AN --h--> ANH
```

có thể biểu diễn các tập khóa khác nhau:

- `{"anh"}`: chỉ nút `ANH` là terminal.
- `{"an", "anh"}`: cả `AN` và `ANH` là terminal.
- `{"a", "an", "anh"}`: cả ba nút `A`, `AN` và `ANH` là terminal.

**Hình dạng cạnh giống nhau nhưng tập khóa khác nhau**. Dấu terminal là thông tin cần thiết để phân biệt các trạng thái đó.

## 3. Sơ đồ: nút nội bộ vẫn có thể kết thúc từ

Cho tập khóa:

```text
S = {"an", "anh", "ao", "ba", "ban"}
```

Ta có Trie không nén với một ký hiệu trên mỗi cạnh:

```text
                        root ("")
                         /      \
                        a        b
                      /   \       \
                     n*    o*      a*
                     |              |
                     h*             n*

 * = terminal = True
```

Diễn giải từng đường:

| Đường đi từ gốc | Chuỗi tương ứng | `terminal` | Có con? | Ý nghĩa |
| --- | --- | --- | --- | --- |
| Gốc | `""` | False | Có | Chỉ là tiền tố rỗng |
| `a` | `"a"` | False | Có | Tiền tố, chưa phải khóa |
| `a→n` | `"an"` | True | Có | Khóa hoàn chỉnh **và** tiền tố của `anh` |
| `a→n→h` | `"anh"` | True | Không | Khóa hoàn chỉnh |
| `a→o` | `"ao"` | True | Không | Khóa hoàn chỉnh |
| `b` | `"b"` | False | Có | Tiền tố, chưa phải khóa |
| `b→a` | `"ba"` | True | Có | Khóa hoàn chỉnh **và** tiền tố của `ban` |
| `b→a→n` | `"ban"` | True | Không | Khóa hoàn chỉnh |

**Chốt quan trọng:** `terminal=True` không bắt buộc nút phải là lá. Trong ví dụ, cả `an` và `ba` là terminal dù còn có nút con.

### 3.1. Nút lá có phải lúc nào cũng terminal?

Trong một Trie dạng Set được xây từ khóa và **luôn dọn hết nhánh không còn khóa** sau xóa, mỗi nút lá khác gốc đều phải là terminal: nếu không, nút lá ấy không phục vụ khóa nào và có thể bỏ đi.

Nhưng đây là **hệ quả của một bất biến cài đặt**, không phải định nghĩa terminal. Một cài đặt có thể giữ “nút chết” để tái sử dụng; khi đó tồn tại nút lá không terminal. Không được viết logic `contains` dựa trên việc “nút này là lá”.

### 3.2. Hai phép kiểm tra không tương đương

```python
# Sai: chỉ cần đường đi tồn tại đã coi là có khóa.
def contains_wrong(root, word):
    node = root
    for ch in word:
        node = node.children.get(ch)
        if node is None:
            return False
    return True

# Đúng: đường đi tồn tại VÀ nút cuối phải là terminal.
def contains_correct(root, word):
    node = root
    for ch in word:
        node = node.children.get(ch)
        if node is None:
            return False
    return node.terminal
```

Nếu Trie chỉ lưu `"anh"`, hàm sai trả True cho `"a"` và `"an"`; hàm đúng trả False.

## 4. Bốn câu hỏi khác nhau thường bị trộn lẫn

Có ít nhất bốn thao tác gần tên nhưng không có cùng ngữ nghĩa.

| Tên trong bài | Câu hỏi | Điều kiện trả lời |
| --- | --- | --- |
| `contains(word)` | Có lưu **chính khóa** này không? | Nút cuối tồn tại và terminal |
| `has_path(prefix)` | Có đường đi mang chuỗi này không? | Theo hết các cạnh được yêu cầu |
| `has_key_with_prefix(prefix)` | Có **ít nhất một khóa đã lưu** bắt đầu bằng chuỗi này không? | Đường đi tới nút và cây con còn ≥1 khóa |
| `is_prefix_of_query(query)` | Có khóa đã lưu nào là tiền tố của chuỗi truy vấn không? | Có nút terminal trên đường đi của `query` |

Trong nhiều thư viện, tên `starts_with(prefix)` có thể dùng cho ý nghĩa thứ hai hoặc thứ ba. Hai ý nghĩa thường trùng nhau khi **tiền tố không rỗng và các nhánh chết đã được dọn**, nhưng khác nhau ở một số trường hợp biên.

### 4.1. Cách đặt tên API rõ ràng

Để tránh mơ hồ, bài này dùng:

- `starts_with(prefix)`: **kiểm tra sự tồn tại của đường tiền tố**.
- `has_key_with_prefix(prefix)`: **kiểm tra có khóa hoàn chỉnh trong cây con**.
- `count_prefix(prefix)`: **đếm chính xác số khóa hoàn chỉnh trong cây con**.
- `contains(word)`: **kiểm tra khóa hoàn chỉnh**.
- `longest_stored_prefix(text)`: trả về **khóa dài nhất đã lưu** là tiền tố của `text`, hoặc `None` nếu không có.

Ví dụ, với `S={"an","anh","ba"}`:

| Truy vấn | Kết quả |
| --- | --- |
| `contains("a")` | False |
| `starts_with("a")` | True |
| `has_key_with_prefix("a")` | True |
| `count_prefix("a")` | 2 |
| `longest_stored_prefix("anhdao")` | `"anh"` |
| `longest_stored_prefix("anxa")` | `"an"` |
| `longest_stored_prefix("bala")` | `"ba"` |
| `longest_stored_prefix("a")` | `None` |

**Một tiền tố của khóa đã lưu** và **một khóa đã lưu là tiền tố của truy vấn** là hai quan hệ có hướng khác nhau; hãy đọc kỹ câu hỏi trước khi chọn thuật toán.

## 5. Trường hợp chuỗi rỗng và Trie rỗng

Chuỗi rỗng `""` là tiền tố của **mọi** chuỗi, kể cả chính nó:

\[
""\preceq s\quad\text{với mọi chuỗi }s.
\]

Gốc Trie luôn đại diện cho `""`, kể cả khi chưa lưu khóa nào. Vì thế cần tách **sự tồn tại của gốc** khỏi **sự tồn tại của khóa hoàn chỉnh**.

### 5.1. Một hợp đồng nhất quán

Trong bài này, ta chọn những quy tắc sau:

1. Gốc luôn tồn tại, nên `starts_with("")` luôn True, kể cả khi tập khóa rỗng.
2. `contains("")` chỉ True khi người dùng **đã chèn khóa rỗng**; khi đó `root.terminal=True`.
3. `has_key_with_prefix("")` là True khi **tập khóa không rỗng**.
4. `count_prefix("")` bằng **tổng số khóa phân biệt** đã lưu.
5. Cho phép chèn/xóa `""` như một khóa hợp lệ, không đi qua cạnh nào.

| Trạng thái | `starts_with("")` | `has_key_with_prefix("")` | `contains("")` | `count_prefix("")` |
| --- | --- | --- | --- | --- |
| Trie chưa có khóa | True | False | False | 0 |
| Chỉ có `"anh"` | True | True | False | 1 |
| Chỉ có `""` | True | True | True | 1 |
| Có `""` và `"anh"` | True | True | True | 2 |

Đây là **lựa chọn API**, không phải định luật bắt buộc mọi thư viện theo. Một API có tên `starts_with` nhưng được đặc tả là “có ít nhất một khóa hoàn chỉnh mang tiền tố đó” có thể trả False cho `""` khi Trie rỗng. Điều quan trọng là **viết hợp đồng rõ và kiểm thử đúng theo hợp đồng**.

### 5.2. Tại sao nên hỗ trợ bộ đếm cây con?

Nếu chỉ giữ `terminal` và `children`, ta vẫn có thể xác định có khóa nào bắt đầu bằng một tiền tố bằng cách tìm một nút terminal trong cây con. Nhưng có thể phải duyệt nhiều nút.

Nếu mỗi nút lưu `subtree_count` là số khóa hoàn chỉnh nằm trong cây con, ta trả:

```text
has_key_with_prefix(prefix) = count_prefix(prefix) > 0
```

Chi phí tìm nút tiền tố chỉ phụ thuộc độ dài tiền tố, sau đó đọc bộ đếm hằng số. Đổi lại, mỗi lần chèn/xóa thành công phải cập nhật bộ đếm trên đường đi.

## 6. Nút kết thúc khóa là bất biến của Set, không phải thuộc tính hình học

Cho `S` là tập khóa logic đã lưu. Mỗi nút `v` mang chuỗi `label(v)` là nhãn các cạnh từ gốc tới `v`. Bất biến quan trọng là:

\[
terminal(v)=\text{True}
\quad\Longleftrightarrow\quad
label(v)\in S.
\]

Đó là **mệnh đề hai chiều**:

- Nếu nút terminal, chuỗi trên đường đi **phải** là khóa đã lưu.
- Nếu một khóa đang được lưu, đường đi của nó **phải** kết thúc ở nút terminal.

Ngoài ra, với Trie không nén một ký hiệu mỗi cạnh:

1. Gốc mang chuỗi rỗng.
2. Mỗi nút có nhiều nhất một cạnh ra cho cùng một ký hiệu.
3. Mọi nút con nối thêm đúng một ký hiệu vào tiền tố nút cha.
4. Nếu lưu bộ đếm, với mọi nút:

\[
count(v)=\mathbf{1}_{terminal(v)}
+\sum_{u\in children(v)}count(u).
\]

5. Tại gốc, `count(root)=|S|`.
6. Trong cài đặt **dọn nhánh rỗng**, mọi nút khác gốc tồn tại đều có `count(v)>0`.

### 6.1. Tập khóa và số nút không đồng nhất

Với `S={"an","anh"}` có thể có bốn nút: gốc, `a`, `an`, `anh`. Nhưng chỉ có **hai** nút terminal. Do đó:

- `len(trie)` phải là 2.
- `count_prefix("a")` phải là 2.
- `count_prefix("an")` phải là 2.
- `count_prefix("anh")` phải là 1.

Việc đếm **nút** hoặc **đường đi** thay cho đếm **nút terminal** sẽ cho kết quả sai.

### 6.2. Nếu cho phép khóa trùng thì sao?

Một Trie dạng **Set** không đếm khóa trùng:

```text
insert("an") -> True   # Thêm lần đầu
insert("an") -> False  # Khóa đã tồn tại
len(trie)    -> 1
```

Nếu bài toán cần một **multiset**, ta có thể thay `terminal: bool` bằng `terminal_count: int` hoặc lưu thêm số lần xuất hiện. Khi đó bất biến của bộ đếm phải quyết định có đếm **số khóa phân biệt** hay **tổng số lượt xuất hiện**.

Không được trộn hai cách đếm. Bài này tiếp tục dùng **Set khóa phân biệt** để mọi thao tác có hợp đồng đơn giản và nhất quán.

## 7. Chèn khóa: đánh dấu ở đâu là đúng?

Để chèn `word`:

1. Bắt đầu tại gốc.
2. Theo các ký hiệu của `word`, tạo nút con nếu thiếu.
3. Khi đã xử lý **toàn bộ** ký hiệu, kiểm tra nút cuối.
4. Nếu nút cuối đã terminal, đây là chèn trùng: không thay đổi tập khóa và bộ đếm.
5. Nếu chưa terminal, đặt `terminal=True` và tăng số khóa trong các cây con trên đường đi đúng một lần.

### 7.1. Chèn từ ngắn vào Trie đang có từ dài

Ban đầu `S={"anh"}`:

```text
root -> a -> n -> h*
```

Thêm `"an"`:

```text
root -> a -> n* -> h*
```

Không có cạnh mới; chỉ có dấu terminal tại `n` và các bộ đếm tăng 1.

### 7.2. Chèn từ dài vào Trie đang có từ ngắn

Ban đầu `S={"an"}`:

```text
root -> a -> n*
```

Thêm `"anh"`:

```text
root -> a -> n* -> h*
```

Nút `n` **vẫn terminal**. Đừng viết mã kiểu “nếu có nút con thì bỏ dấu kết thúc ở nút cha”; logic đó làm mất khóa `an`.

### 7.3. Chèn khóa hoàn chỉnh không dựa vào độ dài cố định

Một số từ dài 1 ký hiệu, số khác dài hàng trăm ký hiệu, nhưng quy tắc giống nhau: **dấu terminal đặt tại nút sau khi xử lý hết dãy ký hiệu của khóa đó**. Nếu `word=""`, nút cuối chính là gốc.

## 8. Xóa khóa: bảo toàn những tiền tố còn được sử dụng

Cho `S={"an","anh","ao"}`. Nếu xóa `"an"`, tập hợp mới là `{"anh","ao"}`.

Đường `a→n` vẫn phải tồn tại để dẫn tới `anh`:

```text
Trước: root -> a -> n* -> h*
Sau:   root -> a -> n  -> h*
```

Chỉ cần bỏ `terminal` của nút `n`; không thể xóa cả nút đó.

### 8.1. Ba trường hợp khi xóa

| Trường hợp | Ví dụ | Hành động đúng |
| --- | --- | --- |
| Khóa bị xóa là tiền tố của khóa khác | Xóa `an` trong `{an,anh}` | Bỏ terminal, giữ nhánh phục vụ `anh` |
| Khóa bị xóa có hậu tố riêng không được dùng chung | Xóa `anh` trong `{an,anh}` | Bỏ terminal ở `anh`, dọn nút `h`; giữ `an` |
| Khóa không tồn tại | Xóa `a` trong `{an,anh}` | Trả False, không đổi terminal, bộ đếm hoặc nhánh |

### 8.2. Dọn nhánh từ dưới lên

Với bộ đếm `subtree_count`, sau khi xóa một khóa:

1. Xác nhận **đường đi tồn tại và nút cuối terminal**.
2. Bỏ dấu terminal.
3. Giảm bộ đếm ở các nút thuộc đường đi, kể cả gốc.
4. Bắt đầu từ nút cuối, xóa cạnh từ cha nếu cây con của nút không còn khóa.
5. Tiếp tục đi lên cho tới khi gặp nút vẫn chứa ít nhất một khóa trong cây con.
6. Giữ gốc ngay cả khi cây rỗng.

Cách làm này bảo đảm các nhánh còn phục vụ khóa khác được giữ lại, đồng thời tránh tạo đường tiền tố “ảo” không dẫn tới khóa hoàn chỉnh.

### 8.3. Không được giảm bộ đếm khi xóa thất bại

Nếu gọi `delete("a")` trong Trie chỉ có `anh`, nút `a` có tồn tại nhưng không terminal. Thao tác phải **không làm thay đổi**:

- Số khóa tại gốc.
- Số khóa tại nút `a`.
- Các dấu terminal.
- Cấu trúc các cạnh.

Đây là một **hậu điều kiện** quan trọng của API xóa. Tự giảm bộ đếm chỉ vì đường đi tồn tại sẽ làm toàn bộ thống kê tiền tố trở nên sai.

## 9. Cài đặt Python: TrieSet với terminal và bộ đếm

Cài đặt sau là một Trie **không nén**, mỗi cạnh mang một code point của chuỗi Python. Nút con được lưu bằng dictionary; ta giả định chi phí tra một cạnh là O(1) kỳ vọng trong điều kiện hash thông dụng.

Để tập trung vào hợp đồng, lớp `TrieSet`:

- Chỉ nhận khóa là `str`.
- Cho phép khóa rỗng.
- Bỏ qua chèn trùng.
- Trả False khi xóa khóa chưa có.
- Phân biệt `starts_with` với `has_key_with_prefix`.
- Duy trì `subtree_count` để đếm chính xác những khóa đã lưu.

### 9.1. Mã hoàn chỉnh

```python
class TrieNode:
    __slots__ = ("children", "terminal", "subtree_count")

    def __init__(self):
        self.children = {}
        self.terminal = False
        self.subtree_count = 0


class TrieSet:
    def __init__(self):
        self._root = TrieNode()
        self._size = 0

    @staticmethod
    def _check_string(text):
        if not isinstance(text, str):
            raise TypeError("khóa và tiền tố phải là str")

    def __len__(self):
        return self._size

    def _locate(self, text):
        node = self._root
        for char in text:
            node = node.children.get(char)
            if node is None:
                return None
        return node

    def contains(self, word):
        self._check_string(word)
        node = self._locate(word)
        return node is not None and node.terminal

    def starts_with(self, prefix):
        """Có đường tiền tố; luôn True với prefix rỗng."""
        self._check_string(prefix)
        return self._locate(prefix) is not None

    def count_prefix(self, prefix):
        """Số khóa hoàn chỉnh có tiền tố prefix."""
        self._check_string(prefix)
        node = self._locate(prefix)
        return 0 if node is None else node.subtree_count

    def has_key_with_prefix(self, prefix):
        self._check_string(prefix)
        return self.count_prefix(prefix) > 0

    def insert(self, word):
        """True nếu thêm khóa mới; False nếu đã tồn tại."""
        self._check_string(word)

        node = self._root
        path = [node]

        for char in word:
            child = node.children.get(char)
            if child is None:
                child = TrieNode()
                node.children[char] = child
            node = child
            path.append(node)

        if node.terminal:
            return False

        node.terminal = True
        for item in path:
            item.subtree_count += 1
        self._size += 1
        return True

    def delete(self, word):
        """True nếu xóa thành công; False nếu không có khóa."""
        self._check_string(word)

        node = self._root
        path = [node]

        for char in word:
            node = node.children.get(char)
            if node is None:
                return False
            path.append(node)

        if not node.terminal:
            return False

        node.terminal = False
        for item in path:
            item.subtree_count -= 1

        # Chỉ cắt nhánh có 0 khóa trong cây con.
        for i in range(len(word) - 1, -1, -1):
            parent = path[i]
            child = path[i + 1]
            if child.subtree_count > 0:
                break
            del parent.children[word[i]]

        self._size -= 1
        return True

    def longest_stored_prefix(self, text):
        """Khóa đã lưu dài nhất là tiền tố của text; None nếu thiếu."""
        self._check_string(text)

        node = self._root
        best = 0 if node.terminal else None

        for index, char in enumerate(text, start=1):
            node = node.children.get(char)
            if node is None:
                break
            if node.terminal:
                best = index

        return None if best is None else text[:best]

    def keys_with_prefix(self, prefix="", limit=None):
        """Liệt kê khóa theo thứ tự code point Unicode."""
        self._check_string(prefix)
        if limit is not None:
            if not isinstance(limit, int) or limit < 0:
                raise ValueError("limit phải là số nguyên không âm")
            if limit == 0:
                return []

        start = self._locate(prefix)
        if start is None:
            return []

        result = []
        stack = [(prefix, start)]

        while stack:
            text, node = stack.pop()

            if node.terminal:
                result.append(text)
                if limit is not None and len(result) >= limit:
                    break

            # Stack LIFO nên đẩy nhánh lớn trước.
            for char in sorted(node.children, reverse=True):
                stack.append((text + char, node.children[char]))

        return result
```

### 9.2. Vì sao mã không dùng `setdefault` một cách ngẫu nhiên?

Khi tạo nút mới, ta kiểm tra:

```python
child = node.children.get(char)
if child is None:
    child = TrieNode()
    node.children[char] = child
```

Cách này chỉ tạo `TrieNode` khi thật sự thiếu cạnh. Dạng `node.children.setdefault(char, TrieNode())` sẽ **tạo đối tượng `TrieNode()` trước khi gọi hàm**, kể cả khi cạnh đã tồn tại; đối tượng không dùng đến có thể tạo chi phí cấp phát thừa.

Độ phức tạp theo bậc có thể không đổi, nhưng với Trie có nhiều tiền tố chung, tránh cấp phát nút vô ích là một tối ưu thực tế.

### 9.3. Tại sao kiểm tra terminal sau khi đi hết từ?

Trong `insert`, sau khi đi tới nút cuối, nếu `node.terminal` đã True thì không tăng bộ đếm. Một đường tồn tại từ trước **không đồng nghĩa** khóa đã có; vì thế không được bỏ qua chèn chỉ vì đường đi tồn tại.

Ví dụ, khi Trie có `"anh"` và thêm `"an"`, mọi cạnh của `an` đã tồn tại, nhưng terminal tại `an` còn False. Thao tác phải thêm được khóa `an`.

## 10. Kiểm thử hành vi: tiền tố chưa chắc là khóa

Đặt phần kiểm thử dưới đây sau các lớp ở mục 9 trong cùng một tệp Python.

### 10.1. Đường tồn tại nhưng chưa terminal

```python
trie = TrieSet()

assert trie.starts_with("")
assert not trie.has_key_with_prefix("")
assert not trie.contains("")
assert trie.count_prefix("") == 0

assert trie.insert("anh")
assert trie.starts_with("a")
assert trie.starts_with("an")
assert trie.starts_with("anh")

assert not trie.contains("a")
assert not trie.contains("an")
assert trie.contains("anh")

assert trie.has_key_with_prefix("an")
assert trie.count_prefix("an") == 1
assert not trie.starts_with("ang")
assert not trie.has_key_with_prefix("ang")
```

### 10.2. Cùng đường đi, nay là hai khóa

```python
assert trie.insert("an")
assert trie.contains("an")
assert trie.contains("anh")
assert trie.count_prefix("an") == 2
assert len(trie) == 2

assert not trie.insert("an")
assert trie.count_prefix("an") == 2
assert len(trie) == 2

assert trie.keys_with_prefix("an") == ["an", "anh"]
assert trie.longest_stored_prefix("anhdao") == "anh"
assert trie.longest_stored_prefix("anxa") == "an"
assert trie.longest_stored_prefix("a") is None
```

### 10.3. Xóa khóa ngắn nhưng giữ khóa dài

```python
assert trie.delete("an")
assert not trie.contains("an")
assert trie.contains("anh")
assert trie.starts_with("an")
assert trie.has_key_with_prefix("an")
assert trie.count_prefix("an") == 1
assert len(trie) == 1

assert not trie.delete("an")
assert trie.count_prefix("an") == 1
assert len(trie) == 1
```

### 10.4. Xóa khóa dài và dọn nhánh

```python
assert trie.delete("anh")
assert not trie.contains("anh")
assert not trie.starts_with("an")
assert not trie.has_key_with_prefix("an")
assert trie.count_prefix("") == 0
assert len(trie) == 0

# Root vẫn tồn tại, dù không còn khóa nào.
assert trie.starts_with("")
assert not trie.has_key_with_prefix("")
```

### 10.5. Kiểm thử khóa rỗng và khóa khác cùng tồn tại

```python
assert trie.insert("")
assert trie.contains("")
assert trie.has_key_with_prefix("")
assert trie.count_prefix("") == 1
assert trie.longest_stored_prefix("anything") == ""

assert trie.insert("ba")
assert trie.insert("ban")
assert trie.contains("ba")
assert trie.contains("ban")
assert trie.count_prefix("ba") == 2
assert trie.keys_with_prefix("", limit=3) == ["", "ba", "ban"]

assert trie.delete("")
assert not trie.contains("")
assert trie.contains("ba")
assert trie.contains("ban")
assert trie.count_prefix("") == 2
```

Những kiểm thử này nhắm vào **hợp đồng và trạng thái**, không phải việc Trie có đúng một hình dạng nút duy nhất. Một biểu diễn nén cạnh hoặc một cấu trúc con khác vẫn có thể đáp ứng cùng các kết quả.

## 11. Kiểm tra bất biến nội bộ có hệ thống

Một số lỗi không lộ ra ngay ở `contains`; ví dụ `count_prefix` có thể trả số sai sau một chuỗi chèn/xóa. Vì vậy, ngoài kiểm thử API, ta có thể viết một hàm kiểm tra bất biến nội bộ trong môi trường phát triển.

### 11.1. Kiểm tra bộ đếm và nhánh chết

```python
def validate_trie(trie):
    """Dùng cho kiểm thử: xác minh các bộ đếm và không có nhánh chết."""
    root = trie._root

    def walk(node, is_root=False):
        total = 1 if node.terminal else 0

        for char, child in node.children.items():
            assert isinstance(char, str) and len(char) == 1
            child_total = walk(child)
            assert child_total > 0   # Nhánh còn sống phải dẫn tới khóa
            total += child_total

        assert node.subtree_count == total
        return total

    assert walk(root, is_root=True) == len(trie)


sample = TrieSet()
for key in ["", "an", "anh", "ao", "ba"]:
    assert sample.insert(key)
    validate_trie(sample)

for key in ["an", "anh", "", "ba", "ao"]:
    assert sample.delete(key)
    validate_trie(sample)

assert len(sample) == 0
```

Bài kiểm tra có chi phí duyệt toàn bộ Trie, nên thích hợp cho **unit test** hoặc chế độ debug, không cần chạy sau mỗi thao tác trong môi trường sản xuất.

### 11.2. Kiểm thử dựa trên mô hình Set tham chiếu

Để kiểm tra rằng terminal đại diện đúng cho tập khóa, có thể dùng `set[str]` của Python làm mô hình tham chiếu:

```python
def check_against_set(trie, reference, probes):
    assert len(trie) == len(reference)

    for text in probes:
        assert trie.contains(text) == (text in reference)
        assert trie.count_prefix(text) == sum(
            key.startswith(text) for key in reference
        )
        assert trie.has_key_with_prefix(text) == any(
            key.startswith(text) for key in reference
        )


trie = TrieSet()
reference = set()

for word in ["anh", "an", "ao", "anh", ""]:
    trie.insert(word)
    reference.add(word)
    check_against_set(trie, reference, ["", "a", "an", "anh", "x"])

for word in ["an", "x", "", "anh"]:
    trie.delete(word)
    reference.discard(word)
    check_against_set(trie, reference, ["", "a", "an", "anh", "x"])
```

`set` ở đây không được dùng để **triển khai** Trie; nó giúp kiểm thử tính đúng bằng một biểu diễn độc lập. Những phép `sum/any` theo toàn bộ tập có thể O(n) hoặc tốn nhiều phép so sánh chuỗi, nhưng điều đó chấp nhận được với tập kiểm thử nhỏ.

## 12. Chứng minh tính đúng của thao tác chèn và xóa

Trong cấu trúc dữ liệu, việc nêu một đoạn mã hoạt động trên ví dụ là chưa đủ. Cần biết vì sao nó **giữ đúng bất biến cho mọi khóa hợp lệ**.

### 12.1. Chứng minh cho `insert(word)`

Giả sử Trie trước thao tác biểu diễn đúng tập `S`.

**Trường hợp 1: `word ∈ S`.** Đường đi có sẵn và nút cuối terminal. Hàm trả False, không đổi `terminal`, bộ đếm hay kích thước. Tập khóa sau thao tác vẫn là `S`.

**Trường hợp 2: `word ∉ S`.** Hàm tạo đúng những cạnh còn thiếu trên đường của `word` và đánh dấu terminal ở nút cuối. Không thay đổi dấu terminal của nút cũ khác. Tập khóa sau thao tác là:

\[
S' = S\cup\{word\}.
\]

Mỗi nút nằm trên đường từ gốc tới `word` có đúng **một** khóa hoàn chỉnh mới trong cây con nên bộ đếm tăng 1 là đúng. Các nút không nằm trên đường đi giữ nguyên số khóa trong cây con. Vì thế mọi bộ đếm vẫn đúng, và `len` tăng 1.

### 12.2. Chứng minh cho `delete(word)`

Giả sử Trie biểu diễn đúng tập `S`.

**Trường hợp 1: `word ∉ S`.** Hoặc thiếu một cạnh, hoặc nút cuối không terminal. Hàm trả False trước khi sửa trạng thái; tập và mọi bộ đếm không đổi.

**Trường hợp 2: `word ∈ S`.** Hàm bỏ terminal tại đúng nút của `word`, làm tập khóa trở thành:

\[
S' = S\setminus\{word\}.
\]

Chỉ các nút trên đường đi của `word` mất đúng một khóa hoàn chỉnh trong cây con, nên chỉ các bộ đếm ấy giảm 1.

Nếu nút con có `subtree_count>0`, ít nhất một khóa còn sử dụng đường tới nó; hàm **không xóa** cạnh đó. Nếu bộ đếm bằng 0, không còn khóa nào dùng đường đó, nên loại cạnh sẽ không làm mất khóa thuộc `S'`. Dọn từ dưới lên bảo đảm không giữ nhánh chết ngoài gốc.

Vì vậy, mọi khóa còn trong `S'` vẫn có đường đi với terminal đúng; và không có khóa đã xóa nào bị nhận nhầm là còn.

### 12.3. Bất biến bảo toàn qua chuỗi thao tác

Bắt đầu với Trie rỗng hợp lệ, mỗi lần chèn/xóa theo hai chứng minh trên đều giữ đúng bất biến. Theo **quy nạp trên số thao tác**, bất biến đúng sau mọi chuỗi chèn/xóa hợp lệ.

Khi thêm thao tác mới như cập nhật giá trị, lưu tần suất hay xóa theo tiền tố, cần lập luận thêm rằng thao tác ấy không phá các quy tắc terminal và bộ đếm.

## 13. Thời gian: độ dài chuỗi quan trọng hơn số khóa

Gọi:

- `n` là số khóa phân biệt đang lưu.
- `L` là số **code point** của khóa đầy đủ.
- `P` là số code point của tiền tố.
- `S` là tổng độ dài của các khóa phân biệt.
- `N` là số nút thực tế, gồm gốc.
- `R` là số nút được thăm trong quá trình liệt kê cây con.
- `Z` là tổng độ dài các chuỗi được tạo trong kết quả.

Giả định bảng `children` hỗ trợ tìm/chèn/xóa một cạnh ký tự trong **O(1) kỳ vọng** với cách băm phù hợp, và kiểm tra/đổi `terminal` hay cộng bộ đếm là O(1).

| Thao tác | Độ phức tạp thời gian thông dụng | Điều kiện |
| --- | --- | --- |
| `contains(word)` | O(L+1) kỳ vọng | Duyệt tối đa `L` cạnh, đọc terminal |
| `starts_with(prefix)` | O(P+1) kỳ vọng | Chỉ cần đường đi |
| `has_key_with_prefix(prefix)` | O(P+1) kỳ vọng | Duyệt rồi xem bộ đếm |
| `count_prefix(prefix)` | O(P+1) kỳ vọng | Duyệt rồi đọc `subtree_count` |
| `insert(word)` | O(L+1) kỳ vọng | Tạo tối đa `L` nút và cập nhật đường đi |
| `delete(word)` | O(L+1) kỳ vọng | Kiểm tra, giảm bộ đếm, có thể dọn ngược |
| `longest_stored_prefix(text)` | O(L+1) kỳ vọng | Theo đường của truy vấn và nhớ terminal mới nhất |
| `len(trie)` | O(1) | Đọc `_size` |
| Liệt kê tất cả khóa tiền tố | Ít nhất Ω(Z) | Phải tạo đủ đầu ra |

### 13.1. Vì sao không chỉ viết O(1) cho `contains`?

Nếu `L` là tham số thay đổi, ta phải đọc đến `L` ký hiệu để xác định đường đi và terminal. Câu “kiểm tra một khóa trong Trie O(L)” là cách nói chính xác hơn “O(1)” theo số khóa `n`.

Nếu khóa dài cố định và từng cạnh tra O(1), có thể coi độ dài là một hằng số trong một ứng dụng cụ thể. Nhưng **đó là giả định**, không phải tính chất của mọi chuỗi.

### 13.2. Phân tích liệt kê kết quả

Với `keys_with_prefix(prefix)`:

1. Đi tới nút tiền tố: O(P) kỳ vọng.
2. Duyệt các nút cần thiết trong cây con.
3. Tạo chuỗi kết quả và sắp thứ tự các nhánh tại từng nút.

Nếu `d_v` là số con của nút `v` đã xử lý, thời gian có dạng chặn trên:

\[
O\left(P+R+Z+\sum_{v}d_v\log(d_v+1)\right),
\]

với phép cộng trên những nút được duyệt, và giả định ký hiệu/so sánh ký tự có chi phí hằng số. Thành phần cuối đến từ `sorted(node.children)`. Cài đặt chỉ cần **liệt kê không sắp** có thể bỏ phần sắp nhánh.

Trong mã minh họa, phép `text + char` còn tạo chuỗi trung gian khi đi xuống; chi phí sao chép các chuỗi trung gian ấy phải được tính nếu yêu cầu phân tích chặt theo số ký tự. Cách lưu danh sách ký tự đường đi và dùng sự kiện vào/ra nút có thể giảm việc sao chép tiền tố ở mỗi cạnh. Dù tối ưu thế nào, **không thể trả `Z` ký tự kết quả mà không tốn ít nhất Ω(Z) công việc đầu ra**.

### 13.3. Trường hợp xấu nhất và bộ nhớ

Nếu mỗi nút dùng dictionary, O(1) trên một cạnh là **kỳ vọng** trong mô hình hash phù hợp; không phải chặn xấu nhất tuyệt đối cho mọi dictionary và mọi khóa.

Trie không nén tạo nhiều nhất một nút mới cho mỗi ký hiệu được thêm, nên:

\[
1\le N\le 1+S.
\]

Số cạnh của cây là `N-1`. Với overhead trên nút và cạnh được xem hằng số trong mô hình, bộ nhớ cấu trúc O(S+1). Trên Python, đối tượng nút và dictionary con có overhead đáng kể; Trie **không mặc nhiên tiết kiệm byte hơn Hash Set**.

## 14. Nút terminal khi Trie lưu Map thay vì Set

Bài này dùng tập khóa, nhưng ứng dụng thực tế có thể muốn lưu:

```text
"an"  -> "điều kiện yên ổn"
"anh" -> "từ xưng hô"
"ao"  -> "vùng nước nhỏ"
```

Khi đó Trie đóng vai trò **Map từ chuỗi tới giá trị**. Nút cuối của khóa cần giữ cả dấu đã lưu và giá trị:

```python
class MapTrieNode:
    def __init__(self):
        self.children = {}
        self.terminal = False
        self.value = None
```

### 14.1. Vì sao không dùng `value is not None` thay terminal?

Vì `None` có thể là **giá trị hợp lệ** của một mục Map:

```text
put("an", None)   # Đã lưu khóa "an" với giá trị None
get("an")         # Trả None
get("a")          # Cũng có thể trả None nếu quy ước thiếu khóa là None
```

Nếu chỉ dùng `value is not None` để quyết định khóa có tồn tại, ta sẽ nhầm `"an"` **đã lưu giá trị None** thành khóa vắng mặt.

Giải pháp:

- Giữ `terminal` hoặc `has_value` riêng với nội dung giá trị.
- Hoặc dùng một **sentinel** đặc biệt để biểu thị “chưa lưu mục”, khác với mọi giá trị hợp lệ.
- Nếu API phân biệt khóa thiếu và giá trị `None`, có thể dùng `contains` hoặc ném `KeyError` theo hợp đồng.

### 14.2. Cập nhật giá trị không tạo khóa mới

Nếu `put("an", value)` được gọi khi nút `an` đã terminal, thao tác chỉ thay `value`, không tăng `len` và không tăng `subtree_count`.

Nếu chưa terminal, đó là thêm khóa mới và phải tăng bộ đếm đúng một lần. Phân biệt **lưu một mục mới** với **cập nhật giá trị của mục cũ** là ứng dụng trực tiếp của dấu terminal.

### 14.3. Xóa khóa có giá trị không phá các khóa khác

Khi xóa `"an"` trong Map còn `"anh"`, ta bỏ dấu terminal/giá trị ở nút `an` nhưng giữ nhánh `h`. Nút `an` tiếp tục đóng vai trò **tiền tố**, mặc dù không còn đại diện một mục Map.

## 15. Unicode và quy tắc “khóa bằng nhau”

Trie ở mục 9 duyệt một chuỗi Python theo các **code point Unicode**. Hai chuỗi có vẻ ngoài giống nhau có thể có biểu diễn khác nhau, chẳng hạn:

- `"á"`: một code point tổ hợp sẵn.
- `"a\u0301"`: `a` cộng dấu sắc kết hợp.

### 15.1. Chuẩn hóa phải nhất quán

```python
import unicodedata

composed = "á"
decomposed = "a\u0301"

assert composed != decomposed
assert unicodedata.normalize("NFC", composed) == \
       unicodedata.normalize("NFC", decomposed)
```

Nếu ứng dụng xem hai biểu diễn là **một khóa**, phải chuẩn hóa đầu vào theo cùng một quy tắc **khi chèn, tìm và xóa**.

Ví dụ tạo một lớp bao:

```python
import unicodedata


def normalize_key(text):
    if not isinstance(text, str):
        raise TypeError("khóa phải là str")
    return unicodedata.normalize("NFC", text)


trie = TrieSet()
assert trie.insert(normalize_key("bàn"))
assert trie.contains(normalize_key("ba\u0300n"))
```

### 15.2. Không nhầm tiền tố của chuỗi gốc với tiền tố sau chuẩn hóa

Thao tác chuẩn hóa có thể biến đổi cách biểu diễn và số code point. Trong một hệ thống định nghĩa khóa bằng **chuỗi đã chuẩn hóa**, mọi truy vấn tiền tố phải dùng cùng quy tắc và phải nêu rõ tiền tố được xét **trên chuỗi chuẩn hóa**.

Nếu người dùng đang nhập một tổ hợp ký tự chưa hoàn chỉnh, trải nghiệm gợi ý có thể cần quy tắc đặc biệt cho dấu kết hợp. Không nên tự động suy rằng việc chuẩn hóa luôn bảo toàn mọi quan hệ tiền tố ở cấp chuỗi thô.

### 15.3. Phân biệt hoa/thường là chính sách riêng

Một số ứng dụng muốn `"An"` và `"an"` là cùng khóa; số khác muốn phân biệt. Nếu chọn `casefold()` hoặc `lower()`, phải dùng thống nhất ở các thao tác và chấp nhận việc hai khóa khác nhau ở dữ liệu gốc có thể hợp nhất.

**Nút terminal là dấu kết thúc của khóa theo quy tắc chuẩn hóa đã chọn**, không tự trả lời được câu hỏi hai biểu diễn Unicode có cùng ý nghĩa hay không.

## 16. Ứng dụng thực tế của việc phân biệt terminal và tiền tố

### 16.1. Từ điển và kiểm tra chính tả

Khi người dùng gõ `"an"`:

- `contains("an")` cho biết đó có phải từ đã được chấp nhận.
- `has_key_with_prefix("an")` cho biết còn có từ hoàn chỉnh nào bắt đầu bằng `an`.
- `keys_with_prefix("an")` có thể trả gợi ý như `["an","anh"]`.

Nếu nhầm tiền tố thành khóa, bộ kiểm tra chính tả có thể chấp nhận các đoạn nhập dở như `"a"` chỉ vì từ `"anh"` tồn tại.

### 16.2. Gợi ý tìm kiếm

Một hộp tìm kiếm thường muốn trả những **khóa hoàn chỉnh** có tiền tố đã nhập. Nút tiền tố là điểm bắt đầu duyệt; các kết quả chỉ được thêm vào danh sách khi gặp nút terminal.

Nếu hệ thống chỉ in nhãn mọi nút con, nó sẽ trả cả những chuỗi không được đăng ký làm từ khóa, ví dụ `"a"` trong Trie chỉ lưu `"an"`.

### 16.3. Bộ lọc và định tuyến theo tiền tố

Với các mẫu đường dẫn hoặc dãy bit, một khóa ngắn có thể được lưu như mẫu hợp lệ đồng thời là tiền tố của một mẫu dài hơn. Truy vấn “tìm khóa hợp lệ dài nhất là tiền tố của chuỗi đầu vào” phải nhớ **nút terminal sâu nhất** đã đi qua.

Ví dụ lưu `{"a","an","anh"}`, truy vấn `"anhdao"` trả `"anh"` thay vì chỉ trả True khi thấy có đường đi. Thuật toán `longest_stored_prefix` thực hiện điều này bằng cách cập nhật `best` tại từng nút terminal.

Cách so khớp này là mô hình ý tưởng; trong định tuyến mạng thực tế còn có quy tắc độ dài tiền tố, ưu tiên và biểu diễn nhị phân riêng.

### 16.4. Đếm theo tiền tố và biểu đồ thống kê

Nếu lưu bộ đếm `subtree_count`, ứng dụng có thể hiển thị:

```text
"an" -> 12 khóa hoàn chỉnh bắt đầu bằng "an"
"th" -> 87 khóa hoàn chỉnh bắt đầu bằng "th"
```

Không được lấy **số nút trong cây con** làm số khóa. Một nhánh dài từ một khóa đơn có thể tạo nhiều nút nhưng chỉ một terminal.

## 17. Những lỗi triển khai và cách phát hiện

| Lỗi | Biểu hiện | Kiểm thử nên có |
| --- | --- | --- |
| `contains` chỉ kiểm tra đường đi | Từ `a` được nhận dù chỉ lưu `anh` | Chèn từ dài, tìm mọi tiền tố ngắn |
| Dùng `is_leaf` thay terminal | `an` bị coi là không có khi còn `anh` | Lưu đồng thời `an` và `anh` |
| Bỏ terminal của nút khi thêm con | Chèn `anh` làm mất `an` | Chèn ngắn trước, dài sau |
| Xóa nút terminal có con | Xóa `an` làm mất `anh` | Xóa tiền tố nhưng giữ từ dài |
| Xóa nhánh chỉ dựa vào đường được hỏi | Làm mất từ khác chung đoạn đầu | Chèn nhiều từ có tiền tố chung, xóa một |
| Chèn trùng vẫn tăng bộ đếm | `count_prefix` lớn hơn số khóa thực | Chèn một khóa hai lần |
| Xóa thất bại vẫn giảm bộ đếm | Có thể xuất hiện số âm hoặc nhánh chết | Xóa tiền tố chưa phải khóa |
| Không dọn nhánh nhưng `starts_with` chỉ xem đường | Báo có gợi ý cho tiền tố không còn khóa | Xóa khóa cuối của một nhánh |
| Dùng `value is not None` cho Map | Khóa lưu giá trị `None` bị coi là vắng | Lưu khóa với payload `None` |
| Không thống nhất Unicode | Một từ hiển thị giống nhau đi vào hai nhánh | NFC từ tổ hợp và dạng kết hợp |
| Dùng `len(children)==0` để đếm khóa | Chỉ đếm lá, bỏ khóa terminal nội bộ | Trie chứa `an` và `anh` |
| Autocomplete trả mọi nút từng thăm | Trả cả các tiền tố chưa lưu | Kiểm tra mọi kết quả đều `contains=True` |

### 17.1. Quan hệ kiểm thử mạnh

Sau mọi thao tác chèn/xóa, các quan hệ sau nên đúng:

\[
count\_prefix("")=len(trie)
\]

\[
contains(x)\ \Longrightarrow\ has\_key\_with\_prefix(x)
\]

\[
count\_prefix(x)>0
\ \Longleftrightarrow\
has\_key\_with\_prefix(x).
\]

Nếu `prefix` khác rỗng và cài đặt dọn hết nhánh chết, ta còn có:

\[
starts\_with(prefix)
\ \Longleftrightarrow\
has\_key\_with\_prefix(prefix).
\]

Tại `prefix=""` và Trie rỗng, tương đương cuối **không đúng** theo hợp đồng của bài này: `starts_with("")` True nhưng `has_key_with_prefix("")` False.

## 18. Bài tập vận dụng và gợi ý giải

### Bài 1 — Đường đi có nhưng khóa chưa có

Trie chỉ lưu `{"anh"}`. Điền True/False cho:

```text
contains("a")
contains("an")
contains("anh")
starts_with("a")
starts_with("an")
has_key_with_prefix("an")
```

**Gợi ý:** Lần lượt `False, False, True, True, True, True`. Hai tiền tố ngắn có đường đi nhưng chưa terminal.

### Bài 2 — Một nút terminal có con

Trie lưu `{"an","anh","ang"}`. Nút mang tiền tố `an` có phải terminal không? Nó có thể có bao nhiêu nút con trong ví dụ?

**Gợi ý:** `an` là khóa hoàn chỉnh nên terminal=True. Nó có hai nhánh tiếp theo `h` và `g`; nút terminal không cần là lá.

### Bài 3 — Đếm đúng số khóa

Trie lưu `{"a","an","anh","ao"}`. Tính:

```text
count_prefix("")
count_prefix("a")
count_prefix("an")
count_prefix("anh")
count_prefix("ax")
```

**Gợi ý:** `4,4,2,1,0`. Đếm các nút terminal trong cây con, không đếm toàn bộ nút.

### Bài 4 — Xóa khóa là tiền tố

Trie lưu `{"an","anh"}`. Sau `delete("an")`, điều gì xảy ra với `contains("an")`, `starts_with("an")` và `contains("anh")`?

**Gợi ý:** `False, True, True`. Nút `an` không còn terminal nhưng vẫn phải giữ để đi đến khóa `anh`.

### Bài 5 — Xóa khóa dài trước

Trie lưu `{"an","anh"}`. Sau `delete("anh")`, nhánh nào có thể bị dọn? `contains("an")` còn đúng không?

**Gợi ý:** Nút `h` không còn dẫn tới khóa nào và có thể bị loại. Nút `an` vẫn terminal; `contains("an")` còn True.

### Bài 6 — Hai cách hiểu về tiền tố rỗng

Theo hợp đồng của bài, một Trie rỗng trả kết quả thế nào cho `starts_with("")`, `has_key_with_prefix("")` và `contains("")`?

**Gợi ý:** `True, False, False`. Gốc có đường rỗng, nhưng không có khóa hoàn chỉnh. Sau khi chèn `""`, cả ba trở thành True.

### Bài 7 — Kiểm tra chèn trùng

Sau khi chèn `{"an","anh"}`, gọi `insert("an")` lần nữa. `len` và `count_prefix("an")` thay đổi không?

**Gợi ý:** Không. Trie dạng Set giữ hai khóa phân biệt nên `len=2` và `count_prefix("an")=2`; lần chèn trùng trả False.

### Bài 8 — Chọn câu trả lời đúng của longest prefix

Trie lưu `{"a","an","anh","ban"}`. Hãy tìm kết quả của:

```text
longest_stored_prefix("anhdao")
longest_stored_prefix("anxa")
longest_stored_prefix("banana")
longest_stored_prefix("xoai")
```

**Gợi ý:** `"anh"`, `"an"`, `"ban"`, `None`. Thuật toán nhớ **terminal sâu nhất trên đường của truy vấn**, không chỉ kiểm tra đường đến cuối.

### Bài 9 — Giá trị `None` trong Trie Map

Một Trie Map lưu `put("an", None)`. Tại sao dùng `value is not None` để kiểm tra tồn tại là sai?

**Gợi ý:** `None` là payload hợp lệ, không phải bằng chứng khóa vắng. Cần dấu `terminal/has_value` riêng hoặc sentinel không trùng giá trị hợp lệ.

### Bài 10 — Độ phức tạp theo độ dài

Trie có một triệu khóa, nhưng mỗi khóa cần tìm dài `L=12` code point. Với dictionary con có tra cứu O(1) kỳ vọng, `contains` mất bao nhiêu bước chọn cạnh theo bậc tăng trưởng? Có nên khẳng định tổng autocomplete cũng O(12) không?

**Gợi ý:** Đi qua tối đa 12 cạnh, nên O(L+1) kỳ vọng. Autocomplete còn duyệt cây con và tạo kết quả, không thể chỉ tính độ dài tiền tố.

### Bài 11 — Unicode và dấu kết hợp

Nếu lưu `"bàn"` nhưng truy vấn bằng `"ba\u0300n"`, vì sao một Trie theo code point có thể trả False dù hai chuỗi nhìn giống nhau?

**Gợi ý:** Dãy code point khác nhau. Muốn xem là một khóa, phải chuẩn hóa theo cùng quy tắc (ví dụ NFC) trước khi lưu và truy vấn.

### Bài 12 — Tự xây phản ví dụ

Hãy tạo một tập khóa nhỏ nhất có thể để bác bỏ phát biểu: “Một nút là khóa hoàn chỉnh khi và chỉ khi nó không có con”.

**Gợi ý:** Tập `{"a","ab"}` là đủ. Nút `a` terminal=True nhưng có con `b`; vì vậy điều kiện “không có con” không phải tiêu chuẩn nhận biết khóa.

## 19. Checklist thiết kế nút terminal

Khi xây một Trie cho ứng dụng thực tế, hãy trả lời:

```text
1. Ngữ nghĩa khóa:
   - Trie lưu Set, Multiset hay Map?
   - Khóa trùng làm gì? Payload có thể là None không?
   - Có cho phép khóa rỗng không?

2. Ngữ nghĩa tiền tố:
   - contains(word): nút cuối phải terminal?
   - starts_with(prefix): chỉ kiểm tra đường hay phải có khóa sống?
   - has_key_with_prefix(prefix): có kiểm tra số khóa cây con?
   - Có cần longest_stored_prefix(query) không?

3. Bất biến:
   - Một cạnh cho mỗi ký hiệu ở mỗi nút?
   - terminal(v) iff label(v) là khóa đã lưu?
   - subtree_count(v) tính cả terminal của chính v?
   - Gốc được giữ khi Trie rỗng?
   - Có dọn nhánh không còn khóa?

4. Cập nhật:
   - Chèn trùng có giữ nguyên bộ đếm?
   - Chèn từ dài có giữ terminal của từ ngắn?
   - Xóa từ ngắn có giữ từ dài chung tiền tố?
   - Xóa thất bại có giữ nguyên mọi trạng thái?

5. Chuỗi và thứ tự:
   - Đơn vị là byte, Unicode code point hay grapheme?
   - Có chuẩn hóa NFC, casefold hoặc biến đổi khác?
   - Autocomplete sắp theo thứ tự Unicode hay mức độ phổ biến?

6. Chi phí và kiểm thử:
   - Độ dài khóa L, tiền tố P, tổng ký hiệu S?
   - Lookup children có giả định kỳ vọng hay xấu nhất?
   - Đã tính thời gian và byte của đầu ra autocomplete?
   - Có unit test và kiểm tra bất biến sau chuỗi chèn/xóa?
```

**Kết luận:** Nút của Trie nói lên **một tiền tố**, còn dấu `terminal` nói lên **một khóa hoàn chỉnh đã được lưu**. Hai thông tin ấy không thể thay thế cho nhau: `a` có thể là tiền tố của `anh` mà chưa phải khóa, còn `an` có thể vừa là khóa vừa là tiền tố của `anh`. Phân biệt chính xác đường đi, terminal, khóa sống trong cây con và quan hệ tiền tố theo hướng truy vấn giúp cài đặt đúng thao tác tìm kiếm, chèn, xóa, đếm và autocomplete. Khi những bất biến đó được duy trì cùng quy tắc Unicode và mô hình chi phí rõ ràng, Trie trở thành một chỉ mục chuỗi có hành vi đáng tin cậy, không chỉ là một cây được vẽ đúng hình.
