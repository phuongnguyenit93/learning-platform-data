# Trie như cây các tiền tố của khóa

> **Chương:** Trie và chỉ mục chuỗi · **Bài học:** Trie như cây các tiền tố của khóa

Một ứng dụng từ điển cần trả lời nhanh các câu hỏi như “Có từ `anh` không?”, “Có từ nào bắt đầu bằng `an` không?” và “Hãy gợi ý những từ bắt đầu bằng `an`”. Nếu lưu toàn bộ từ trong một danh sách, ứng dụng có thể phải quét nhiều mục mỗi lần kiểm tra. Nếu dùng bảng băm, kiểm tra **một khóa đầy đủ** thường nhanh, nhưng việc liệt kê tất cả khóa cùng tiền tố lại không phải thao tác được bảng băm tối ưu trực tiếp.

**Trie** (đọc gần như “try”), hay *cây tiền tố* (*prefix tree*), tổ chức khóa thành các đường đi từ gốc. Mỗi cạnh mang một ký hiệu; các khóa bắt đầu bằng cùng một dãy ký hiệu sẽ **chia sẻ cùng đoạn đường đầu**. Nhờ vậy, truy vấn tiền tố có thể đi theo ký tự của tiền tố, thay vì thử riêng từng khóa lưu trong cấu trúc.

Bài học nằm trong chương **Trie và chỉ mục chuỗi** của mô-đun Cấu trúc dữ liệu (`COMPUTER_SCIENCE_DATA_STRUCTURES`). Chúng ta sẽ xem Trie dưới góc độ **bất biến biểu diễn, thao tác và chi phí thời gian–bộ nhớ**, đồng thời liên hệ với mảng, danh sách liên kết, Stack, Queue, bảng băm, cây, heap và đồ thị để biết khi nào Trie là lựa chọn phù hợp.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích Trie là **cây các tiền tố của khóa**, khác với cây tìm kiếm nhị phân và bảng băm.
2. Vẽ Trie từ một tập từ, chỉ ra đường đi của từng khóa, nút đánh dấu kết thúc từ và các tiền tố được chia sẻ.
3. Phân biệt **tìm khóa đầy đủ**, **kiểm tra tiền tố**, **đếm số khóa theo tiền tố** và **liệt kê các khóa cùng tiền tố**.
4. Cài đặt chèn, tìm, xóa, đếm tiền tố và gợi ý hoàn thành bằng Python.
5. Phát biểu đúng bất biến để xóa một khóa mà không làm mất khóa khác có cùng tiền tố.
6. Phân tích thời gian theo **độ dài khóa/tiền tố** và bộ nhớ theo **tổng số ký hiệu của các khóa**.
7. Hiểu ảnh hưởng của bảng con dạng dictionary, mảng con cố định, Unicode, chuẩn hóa chuỗi và thứ tự gợi ý.
8. So sánh Trie với Hash Map, BST cân bằng và danh sách từ theo nhu cầu của ứng dụng.

## 2. Trie là gì?

Trie là một **cây có gốc** dùng để lưu những khóa được xem là các **dãy ký hiệu**. Trong bài này, mỗi ký hiệu thường là một ký tự Unicode, nhưng cùng ý tưởng có thể dùng với chữ số, byte hoặc bit.

Một Trie thông thường có các thành phần:

- **Gốc (root):** biểu diễn tiền tố rỗng `""`.
- **Cạnh có nhãn:** từ một nút tới nút con qua ký hiệu tiếp theo.
- **Nút:** biểu diễn chuỗi nhận được bằng cách ghép nhãn các cạnh từ gốc tới nút.
- **Dấu kết thúc khóa:** cho biết chính chuỗi tại nút đó là **khóa đã được lưu**, không chỉ là tiền tố.
- **Tập nút con:** ánh xạ ký hiệu tiếp theo tới nút tương ứng.

Cấu trúc không nhất thiết lưu nguyên văn mỗi từ tại một nút lá: **một từ có thể kết thúc ở nút còn có con**.

### 2.1. Ví dụ với năm từ

Xây Trie cho tập:

```text
an, anh, ao, ba, ban
```

Có thể minh họa như sau; dấu `●` nghĩa là **kết thúc một khóa hợp lệ**:

```text
                      (gốc: "")
                       /       \
                      a         b
                    /   \        \
                   n ●   o ●      a ●
                   |              |
                   h ●            n ●

Các khóa:
- a -> n             = "an"
- a -> n -> h        = "anh"
- a -> o             = "ao"
- b -> a             = "ba"
- b -> a -> n        = "ban"
```

Từ ví dụ:

- `an` là khóa hợp lệ, đồng thời là tiền tố của `anh`.
- `a` là tiền tố của ba khóa nhưng **chưa được lưu như một khóa độc lập**.
- `b` là tiền tố của hai khóa nhưng không phải khóa hoàn chỉnh.
- `ba` là khóa hợp lệ, đồng thời là tiền tố của `ban`.
- `ax` không phải tiền tố của khóa nào vì nút `a` không có nhánh `x`.
- `""` là tiền tố rỗng của mọi khóa; việc `""` có được lưu như **một khóa** hay không là một vấn đề khác.

Đặc điểm cốt lõi là **chia sẻ tiền tố**: `an` và `anh` dùng chung đường `a → n`; `ba` và `ban` dùng chung `b → a`.

### 2.2. Nút không nhất thiết chứa cả từ

Một nút `n` trong nhánh `a → n` thường chỉ cần biết:

```text
children = {"h": ...}
terminal = True
```

Từ `an` được xác định bằng **đường đi từ gốc tới nút**, không cần lưu thêm bản sao chuỗi `"an"` trong mỗi nút. Có thể bổ sung dữ liệu ứng dụng ở nút kết thúc, chẳng hạn nghĩa từ, số lượt tìm hoặc ID bản ghi, nhưng đó là phần mở rộng của hợp đồng.

## 3. Trie khác cây tìm kiếm nhị phân như thế nào?

Cả hai đều có dạng cây, nhưng **quy tắc tổ chức khóa hoàn toàn khác**.

| Tiêu chí | Trie ký tự | Cây tìm kiếm nhị phân (BST) |
| --- | --- | --- |
| Ý nghĩa một cạnh | Đi theo **ký hiệu tiếp theo** của khóa | Chọn nhánh trái/phải theo **so sánh toàn bộ khóa** |
| Ý nghĩa một nút | Một tiền tố của ít nhất một khóa; có thể là khóa đầy đủ | Thường lưu một khóa đầy đủ hoặc mục dữ liệu |
| Số nhánh | Có thể nhiều, tùy bảng chữ cái và cài đặt | Tối đa hai con |
| Tìm khóa dài `L` | Theo tối đa `L` ký hiệu trong Trie cơ bản | Đi qua số nút theo chiều cao cây, mỗi nút so sánh khóa |
| Tìm theo tiền tố | Đi theo tiền tố, sau đó duyệt cây con | Có thể dùng tìm cận và duyệt khoảng nếu hỗ trợ thứ tự |
| Bất biến chính | Đường gốc→nút là duy nhất cho mỗi tiền tố | Khóa bên trái nhỏ hơn, bên phải lớn hơn theo quan hệ so sánh |

**Không nên gọi Trie là “BST nhiều nhánh”.** Trong Trie, cạnh không thể được chọn chỉ bằng một phép so sánh `word < key` với khóa của nút; cạnh được chọn theo vị trí ký tự đang đọc.

### 3.1. Trie cũng khác Hash Map

Hash Map thường tối ưu thao tác **tra một khóa đầy đủ**. Nếu cần hỏi “tất cả khóa có tiền tố `an`”, một Hash Map thuần túy không có chỉ mục tiền tố thường phải duyệt các khóa hoặc duy trì thêm cấu trúc riêng.

Trie dành cấu trúc đường đi cho các tiền tố, nên định vị nút tiền tố có thể mất thời gian theo độ dài tiền tố, sau đó duyệt **chỉ cây con liên quan**. Tuy vậy, Trie thường có nhiều đối tượng nút và bảng con, có thể tốn RAM hơn một Hash Map trong một số workload.

## 4. Bất biến biểu diễn của Trie

Bất biến là những quy tắc phải đúng trước và sau mọi thao tác. Với một Trie lưu **tập khóa không trùng**, ta chọn các bất biến sau:

1. Có đúng một gốc biểu diễn tiền tố rỗng.
2. Từ mỗi nút, mỗi ký hiệu có **tối đa một** cạnh tới nút con. Hai cạnh ra khỏi cùng nút không có cùng nhãn.
3. Mỗi nút có đúng một đường từ gốc; ghép nhãn các cạnh trên đường đó được **một tiền tố duy nhất**.
4. Một khóa `s` thuộc tập nếu và chỉ nếu đường mang toàn bộ ký hiệu của `s` tồn tại **và nút cuối có `terminal=True`**.
5. Nút có con vẫn có thể có `terminal=True` nếu một khóa là tiền tố của khóa khác.
6. Sau xóa, các nhánh không còn dẫn tới khóa nào có thể được loại bỏ; không được xóa nhánh còn được khóa khác dùng chung.
7. Nếu lưu bộ đếm `subtree_words`, giá trị này phải bằng số **khóa hoàn chỉnh** nằm trong cây con của nút, tính cả khóa kết thúc ngay tại nút.

Bất biến số 7 có thể viết:

\[
count(v)=\mathbf{1}_{terminal(v)}
+\sum_{u\in children(v)}count(u).
\]

Trong đó `\mathbf{1}_{terminal(v)}` bằng 1 nếu nút `v` đánh dấu kết thúc khóa, bằng 0 nếu không. Do đó:

\[
count(root)=\text{số khóa phân biệt đang lưu}.
\]

### 4.1. Vì sao chỉ kiểm tra đường đi là chưa đủ?

Với Trie lưu `an` và `anh`:

```text
a -> n ● -> h ●
```

Nếu hỏi `contains("a")`, đường `a` có tồn tại, nhưng nút `a` không được đánh dấu kết thúc. Kết quả phải là **False**.

Ngược lại, `starts_with("a")` phải là **True** vì có ít nhất một khóa bắt đầu bằng `a`.

Hai thao tác khác nhau ở đúng điều kiện kiểm tra sau khi đi hết chuỗi đầu vào.

### 4.2. Khóa rỗng không đồng nghĩa Trie rỗng

Gốc luôn tồn tại. Vì thế `starts_with("")` có thể được định nghĩa là **True** cho cả Trie rỗng: tiền tố rỗng có đường đi hợp lệ ngay tại gốc.

Nhưng `contains("")` chỉ True nếu hợp đồng cho phép khóa rỗng và gốc có `terminal=True`. Trong cài đặt ở bài này, ta **cho phép lưu khóa rỗng** và dùng gốc làm nút kết thúc của nó.

## 5. Hợp đồng giao diện: những thao tác cần phân biệt

Ta xây một Trie dạng **Set of strings**: mỗi khóa phân biệt xuất hiện tối đa một lần.

| Thao tác | Ý nghĩa | Đầu vào | Kết quả |
| --- | --- | --- | --- |
| `insert(word)` | Thêm khóa chưa tồn tại | Một chuỗi | `True` nếu mới thêm; `False` nếu đã có |
| `contains(word)` | Kiểm tra khóa đầy đủ có trong tập | Một chuỗi | Boolean |
| `starts_with(prefix)` | Kiểm tra đường tiền tố có tồn tại | Một chuỗi | Boolean |
| `count_prefix(prefix)` | Đếm số khóa có tiền tố đó | Một chuỗi | Số nguyên không âm |
| `delete(word)` | Xóa một khóa đã có | Một chuỗi | `True` nếu xóa; `False` nếu không có |
| `words_with_prefix(prefix, limit)` | Liệt kê tối đa `limit` khóa bắt đầu bằng tiền tố | Tiền tố, giới hạn tùy chọn | Danh sách chuỗi tăng theo thứ tự ký tự |
| `len(trie)` | Đếm số khóa phân biệt | Không | Số nguyên |

Quy tắc ở đây là **thêm lại cùng khóa không làm tăng số lượng**. Nếu cần đếm số lần xuất hiện hoặc số lần người dùng nhập từ, ta phải xây một **multiset** hoặc thêm trường tần suất, và cập nhật bất biến tương ứng.

### 5.1. Bảng phản hồi trên dữ liệu mẫu

Với `an, anh, ao, ba, ban`:

| Lời gọi | Kết quả | Vì sao |
| --- | --- | --- |
| `contains("an")` | `True` | Nút `a→n` có dấu kết thúc |
| `contains("a")` | `False` | Có đường đi nhưng chưa có dấu kết thúc |
| `starts_with("a")` | `True` | Có đường tiền tố `a` |
| `starts_with("ax")` | `False` | Không có nhánh `x` sau `a` |
| `count_prefix("an")` | `2` | Có `an` và `anh` |
| `count_prefix("b")` | `2` | Có `ba` và `ban` |
| `words_with_prefix("an")` | `["an", "anh"]` | Khóa tại nút tiền tố rồi đến hậu duệ |
| `words_with_prefix("x")` | `[]` | Không có khóa bắt đầu bằng `x` |

## 6. Thêm khóa: dùng lại đường đi tiền tố đã có

Để chèn từ `word`:

1. Bắt đầu từ gốc.
2. Với từng ký hiệu `c` của `word`, kiểm tra nút hiện tại có cạnh `c` không.
3. Nếu có, đi tiếp theo cạnh có sẵn; nếu chưa, tạo nút mới và cạnh tương ứng.
4. Sau khi xử lý hết ký hiệu, đánh dấu nút cuối là **kết thúc khóa**.
5. Nếu cài bộ đếm số khóa trong cây con, tăng bộ đếm cho đúng những nút trên đường đi **chỉ khi khóa thực sự mới**.

### 6.1. Chèn từng từ vào Trie

| Bước | Từ thêm | Đường mới hoặc dùng lại | Đánh dấu kết thúc |
| --- | --- | --- | --- |
| 1 | `an` | Tạo `a→n` | `n` của `an` |
| 2 | `anh` | Dùng `a→n`, tạo `h` | `h` của `anh` |
| 3 | `ao` | Dùng `a`, tạo `o` | `o` của `ao` |
| 4 | `ba` | Tạo `b→a` | `a` của `ba` |
| 5 | `ban` | Dùng `b→a`, tạo `n` | `n` của `ban` |

Sau khi chèn `anh`, dấu kết thúc của `an` **phải giữ nguyên**. Chèn từ dài hơn không được làm mất từ ngắn hơn là tiền tố của nó.

### 6.2. Trường hợp thêm trùng

Nếu `insert("an")` được gọi lần nữa, không tạo khóa thứ hai và không được tăng các bộ đếm `subtree_words`.

Nếu cài đặt có nhiệm vụ cập nhật **giá trị gắn với khóa**, nó có thể thay giá trị tại nút kết thúc, nhưng số khóa phân biệt không thay đổi. Bài này chọn hợp đồng Set để lập luận rõ ràng.

## 7. Tìm chính xác và tìm tiền tố

Cả hai thao tác đều bắt đầu giống nhau: lần theo ký hiệu từ gốc.

### 7.1. Tìm khóa đầy đủ

Giả sử tìm `anh`:

```text
root -> "a" -> "n" -> "h"
                         ●
```

Nếu bất kỳ nhánh nào không tồn tại, trả False. Nếu đi hết chuỗi nhưng nút cuối không có dấu kết thúc, trả False. Chỉ trả True khi **cả đường đi và dấu kết thúc** đều thỏa.

### 7.2. Kiểm tra tiền tố

Giả sử hỏi `starts_with("an")`. Đi tới nút `a→n`; không cần biết nút đó có `terminal=True` hay không, chỉ cần đường đi tồn tại.

Trong một Trie **đã được dọn nhánh rỗng sau mỗi lần xóa**, mọi đường còn tồn tại (trừ gốc đặc biệt) đều dẫn tới ít nhất một khóa hoàn chỉnh. Nhờ vậy, kiểm tra đường đi cũng đồng nghĩa có khóa tương ứng với tiền tố không rỗng.

Nếu cài đặt giữ những nút “chết” sau xóa để tái sử dụng, đường đi có thể còn tồn tại mà không dẫn tới khóa nào. Khi đó `starts_with(prefix)` nên kiểm tra thêm bộ đếm số khóa trong cây con hoặc duy trì bất biến dọn nhánh. **Ngữ nghĩa API phải khớp với cách quản lý nút.**

### 7.3. Đếm theo tiền tố

Nếu tại mỗi nút có `subtree_words`, ta chỉ cần:

1. Đi theo ký hiệu của `prefix`.
2. Nếu đường bị đứt, trả 0.
3. Nếu tới được nút, trả `subtree_words` của nút ấy.

Thao tác đếm có thể hoàn thành mà không cần duyệt toàn bộ những khóa bắt đầu bằng tiền tố.

## 8. Xóa khóa: chỉ cắt nhánh không còn được dùng

Xóa phức tạp hơn chèn ở chỗ **nhiều khóa dùng chung tiền tố**.

Với Trie chứa `an` và `anh`, nếu xóa `an` thì:

```text
Trước:    a -> n ● -> h ●
Sau:      a -> n   -> h ●
```

Ta chỉ bỏ dấu kết thúc ở `n`. Nút `n` phải giữ lại để tìm được `anh`.

Ngược lại, nếu chỉ còn khóa `anh` trong nhánh `a→n→h`, xóa `anh` có thể khiến nút `h`, rồi `n`, rồi `a` không còn dẫn tới khóa nào; các nút đó có thể bị loại bỏ từ dưới lên.

### 8.1. Các bước xóa an toàn

1. Đi theo toàn bộ `word`, đồng thời ghi nhận đường các nút từ gốc tới nút cuối.
2. Nếu một cạnh không có hoặc nút cuối không được đánh dấu kết thúc, trả False và **không thay đổi** Trie.
3. Bỏ `terminal` của nút cuối.
4. Giảm `subtree_words` đúng một đơn vị trên mọi nút của đường đi.
5. Đi ngược từ cuối lên, loại cạnh tới những nút có `subtree_words=0`.
6. Dừng khi gặp nút vẫn có khóa trong cây con; **không xóa gốc**.

Với hợp đồng Set, mỗi lần xóa thành công làm `len(trie)` giảm đúng một đơn vị.

### 8.2. Vì sao không được chỉ xóa nút cuối?

Nếu xóa từ `anh` mà không cắt các nhánh thừa, một cài đặt có thể để lại đường `a→n→h` không còn khóa nào. Tìm chính xác vẫn có thể trả False, nhưng `starts_with("anh")` sẽ có nguy cơ trả True nếu chỉ kiểm tra tồn tại đường.

Có hai cách thiết kế đúng:

- **Cắt nhánh rỗng:** không giữ đường dẫn không còn khóa; việc kiểm tra đường đi đủ cho `starts_with`.
- **Giữ nút nhưng kiểm tra bộ đếm:** `starts_with` phải yêu cầu `subtree_words>0` với tiền tố không rỗng.

Trong cài đặt dưới đây, ta chọn **cắt nhánh rỗng** và duy trì bộ đếm để hỗ trợ thêm `count_prefix`.

## 9. Cài đặt Trie bằng Python

Đoạn mã sau hoàn chỉnh, dùng `dict` để lưu các cạnh con theo ký tự. Đó là **Trie không nén**: mỗi cạnh mang đúng một ký tự. Cài đặt dùng `__slots__` cho nút để giảm một phần overhead của đối tượng Python, nhưng vẫn sử dụng dictionary và đối tượng chuỗi.

### 9.1. Lớp nút và các bất biến

```python
class TrieNode:
    __slots__ = ("children", "terminal", "subtree_words")

    def __init__(self):
        self.children = {}       # char -> TrieNode
        self.terminal = False    # Chính tiền tố tại nút là khóa đã lưu?
        self.subtree_words = 0   # Số khóa hoàn chỉnh trong cây con


class Trie:
    def __init__(self):
        self._root = TrieNode()
        self._size = 0

    def __len__(self):
        return self._size

    def _walk(self, text):
        node = self._root
        for char in text:
            node = node.children.get(char)
            if node is None:
                return None
        return node

    def contains(self, word):
        node = self._walk(word)
        return node is not None and node.terminal

    def starts_with(self, prefix):
        # Prefix rỗng luôn có đường đi tại root,
        # ngay cả khi Trie chưa lưu khóa nào.
        return self._walk(prefix) is not None

    def count_prefix(self, prefix):
        node = self._walk(prefix)
        return 0 if node is None else node.subtree_words

    def insert(self, word):
        if self.contains(word):
            return False

        node = self._root
        node.subtree_words += 1

        for char in word:
            child = node.children.get(char)
            if child is None:
                child = TrieNode()
                node.children[char] = child

            node = child
            node.subtree_words += 1

        node.terminal = True
        self._size += 1
        return True

    def delete(self, word):
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
            item.subtree_words -= 1

        # Xóa ngược các nhánh không còn khóa nào.
        for i in range(len(word) - 1, -1, -1):
            parent = path[i]
            child = path[i + 1]

            if child.subtree_words == 0:
                del parent.children[word[i]]
            else:
                break

        self._size -= 1
        return True

    def words_with_prefix(self, prefix="", limit=None):
        if limit is not None and limit < 0:
            raise ValueError("limit phải không âm")

        if limit == 0:
            return []

        start = self._walk(prefix)
        if start is None:
            return []

        result = []
        path = list(prefix)

        # DFS lặp, tránh giới hạn đệ quy với khóa dài.
        # Mỗi sự kiện là (is_exit, node, incoming_char).
        stack = [(False, start, None)]

        while stack:
            is_exit, node, char = stack.pop()

            if is_exit:
                path.pop()
                continue

            if char is not None:
                path.append(char)

            if node.terminal:
                result.append("".join(path))
                if limit is not None and len(result) >= limit:
                    break

            if char is not None:
                stack.append((True, None, None))

            # LIFO: đẩy ngược để xử lý nhánh nhỏ trước.
            for ch in sorted(node.children, reverse=True):
                stack.append((False, node.children[ch], ch))

        return result
```

Cách cài đặt `words_with_prefix` dùng các sự kiện **vào nút/ra nút** để quản lý danh sách ký tự `path`. Khi vào một nút con, thêm ký tự cạnh tới nút đó; khi xử lý xong cây con, sự kiện ra nút sẽ bỏ ký tự. Nhờ đó không phải tạo một chuỗi tiền tố mới ở mỗi cạnh duyệt.

Kết quả được liệt kê theo thứ tự tăng dần của các **ký tự Unicode** vì các nhánh con được sắp bằng `sorted`. Đây không nhất thiết là thứ tự từ điển theo quy tắc tiếng Việt hoặc một locale cụ thể.

### 9.2. Ví dụ sử dụng và kiểm tra hành vi

Đặt tiếp sau lớp trên trong cùng tệp Python:

```python
trie = Trie()

for word in ["an", "anh", "ao", "ba", "ban"]:
    assert trie.insert(word)

assert len(trie) == 5
assert trie.contains("an")
assert trie.contains("anh")
assert not trie.contains("a")
assert not trie.contains("ax")

assert trie.starts_with("a")
assert trie.starts_with("an")
assert trie.starts_with("b")
assert not trie.starts_with("ax")

assert trie.count_prefix("a") == 3
assert trie.count_prefix("an") == 2
assert trie.count_prefix("b") == 2
assert trie.count_prefix("") == 5

assert trie.words_with_prefix("an") == ["an", "anh"]
assert trie.words_with_prefix("b") == ["ba", "ban"]
assert trie.words_with_prefix("a", limit=2) == ["an", "anh"]
assert trie.words_with_prefix("x") == []

assert not trie.insert("an")  # Khóa trùng: không tăng bộ đếm
assert len(trie) == 5

assert trie.delete("an")
assert not trie.contains("an")
assert trie.contains("anh")  # Không được xóa mất khóa dài hơn
assert trie.count_prefix("an") == 1
assert not trie.delete("an")  # Xóa lần hai không đổi trạng thái
assert len(trie) == 4

assert trie.delete("ba")
assert not trie.contains("ba")
assert trie.contains("ban")  # "ba" là tiền tố của "ban"
assert trie.count_prefix("b") == 1
assert len(trie) == 3

# Cho phép lưu cả chuỗi rỗng.
assert trie.starts_with("")
assert not trie.contains("")
assert trie.insert("")
assert trie.contains("")
assert trie.count_prefix("") == 4
assert trie.words_with_prefix("", limit=1) == [""]
assert trie.delete("")
assert not trie.contains("")
assert trie.count_prefix("") == 3
```

Các `assert` minh họa **hợp đồng**, không đo hiệu năng thực tế. Việc `contains("an")` trả False sau khi xóa trong khi `starts_with("an")` vẫn True là kết quả đúng vì `anh` còn tồn tại.

### 9.3. Bất biến bộ đếm trong ví dụ

Trước khi xóa, số khóa trong các cây con là:

```text
root: 5
  a: 3
    n: 2  ("an", "anh")
      h: 1 ("anh")
    o: 1  ("ao")
  b: 2
    a: 2  ("ba", "ban")
      n: 1 ("ban")
```

Khi xóa `an`:

- Bộ đếm của `root` từ 5 xuống 4.
- Bộ đếm của nút `a` từ 3 xuống 2.
- Bộ đếm của nút `a→n` từ 2 xuống 1.
- Nút `a→n` không còn đánh dấu kết thúc, nhưng **không bị xóa** vì cây con còn `anh`.

Nếu bộ đếm bị cập nhật sai, `count_prefix` có thể sai dù `contains` vẫn đúng. Vì vậy, kiểm thử nên bao gồm cả trạng thái sau chèn trùng, xóa khóa là tiền tố và xóa khóa dài.

## 10. Phân tích thời gian theo độ dài khóa

Đặt:

- `L` là số ký hiệu của một khóa đầy đủ.
- `P` là số ký hiệu của tiền tố được hỏi.
- `S` là tổng số ký hiệu của **các khóa phân biệt** đang lưu.
- `N` là số nút thực tế của Trie, tính cả gốc.
- `\sigma` là số ký hiệu có thể xuất hiện trong bảng chữ cái.
- `Z` là tổng số ký hiệu trong những chuỗi **được xuất ra** khi liệt kê kết quả.

Giả sử mỗi nút dùng dictionary ánh xạ một ký tự tới con; tra cứu/chèn/xóa một cạnh có chi phí **O(1) kỳ vọng** trong mô hình khóa ký tự kích thước hằng và hoạt động hash phù hợp.

### 10.1. Các thao tác cơ bản

| Thao tác | Chi phí thời gian thông dụng | Vì sao |
| --- | --- | --- |
| `contains(word)` | O(L) kỳ vọng theo số ký hiệu | Theo tối đa `L` cạnh, kiểm tra `terminal` |
| `starts_with(prefix)` | O(P) kỳ vọng | Theo tối đa `P` cạnh |
| `count_prefix(prefix)` | O(P) kỳ vọng | Tìm nút tiền tố rồi đọc bộ đếm O(1) |
| `insert(word)` | O(L) kỳ vọng | Kiểm tra trùng, duyệt/tạo tối đa `L` nút, cập nhật đường đi |
| `delete(word)` | O(L) kỳ vọng | Đi xuống, giảm bộ đếm và có thể dọn ngược tối đa `L` nút |
| `len(trie)` | O(1) | Đọc `_size` |
| Liệt kê tất cả khóa | Ít nhất Ω(Z) để tạo kết quả | Phải xuất đủ ký hiệu của kết quả |

Đối với chèn khóa rỗng (`L=0`) hoặc tiền tố rỗng (`P=0`), vẫn có chi phí thao tác hằng số. Có thể dùng O(L+1) và O(P+1) khi muốn biểu thức bao quát cả trường hợp rỗng.

**Giới hạn:** Đây là phân tích dưới giả định dictionary có thao tác theo ký tự O(1) kỳ vọng. Nếu dùng biểu diễn khác, chi phí chọn cạnh có thể đổi. Không nên gọi O(L) là chặn xấu nhất tuyệt đối cho mọi dictionary và mọi hàm băm.

### 10.2. Vì sao không phụ thuộc trực tiếp số khóa `n`?

Khi tìm `"anh"`, ta đi theo ba cạnh tương ứng ba ký tự, bất kể Trie đang có 100 hay một triệu khóa khác. Nếu cách lấy con ở mỗi nút không phụ thuộc số khóa toàn cục, số bước đi theo đường tìm bị chặn bởi chiều dài `L=3`.

Tuy nhiên, kết luận này **không có nghĩa mọi chi phí đều độc lập với `n`**:

- Khóa dài hơn cần nhiều bước hơn.
- Cây có thể chiếm nhiều bộ nhớ theo tổng ký hiệu của các khóa.
- Liệt kê tất cả khóa dưới một tiền tố vẫn phải trả công việc theo số nút đi qua và kích thước kết quả.
- Trên phần cứng thật, cache, cấp phát và hoạt động dictionary ảnh hưởng hằng số.

### 10.3. Liệt kê tiền tố và kích thước đầu ra

Với `words_with_prefix(prefix)`:

1. Tìm nút tiền tố: O(P) kỳ vọng.
2. Duyệt các nút cần thiết trong cây con.
3. Tạo chuỗi cho các khóa được trả về.
4. Trong mã trên, còn **sắp nhãn con ở từng nút** để lấy thứ tự ký tự.

Gọi `R` là số nút đã thăm của cây con (nếu không giới hạn kết quả, `R` gồm toàn bộ nút cây con), và `d_v` là số con của mỗi nút đã xử lý. Thời gian của ví dụ Python được chặn theo dạng:

\[
O\left(P+R+Z+\sum_{v\ \text{được xử lý}} d_v\log(d_v+1)\right)
\]

dưới giả định tra dictionary theo ký tự như trên. `Z` bao gồm tổng độ dài của các chuỗi được tạo. Phần tổng `d_v\log(d_v+1)` xuất phát từ `sorted(node.children)`; một cài đặt **không yêu cầu sắp kết quả** có thể bỏ phần sắp này và duyệt trực tiếp các cạnh.

Nếu có `limit`, thuật toán có thể dừng sau khi xuất đủ kết quả; thời gian phụ thuộc số nút/nhánh thực tế đã xử lý và chi phí sắp nhánh, **không chỉ** giá trị `limit`. Một tiền tố có hàng nghìn hậu duệ không thể trả hết bằng O(P) thời gian.

## 11. Bộ nhớ: chia sẻ tiền tố nhưng phải trả phí cho nút

Với Trie không nén và `S` là tổng độ dài ký hiệu của các khóa phân biệt, mỗi lần chèn một khóa dài `L` tạo **tối đa `L` nút mới**.

Do đó:

\[
1\le N\le 1+S.
\]

Cận trên đạt gần nhất khi rất ít tiền tố được dùng chung. Nếu nhiều từ chia sẻ tiền tố dài, số nút có thể nhỏ hơn đáng kể so với tổng số ký hiệu `S`.

### 11.1. Đếm nút trong ví dụ

Với `an, anh, ao, ba, ban`:

- Gốc: 1 nút.
- Nhánh `a`: các tiền tố `a, an, anh, ao` → 4 nút.
- Nhánh `b`: các tiền tố `b, ba, ban` → 3 nút.

Tổng `N=1+4+3=8` nút.

Trong khi tổng số ký hiệu của năm khóa là:

\[
S=2+3+2+2+3=12.
\]

Trie chỉ có 7 nút không phải gốc thay vì 12 vị trí ký tự độc lập, vì các khóa cùng chia sẻ đường đi. Tuy nhiên, **ít nút hơn không mặc nhiên ít byte hơn** một mảng chuỗi hoặc Hash Set: mỗi nút có dictionary con, dấu `terminal`, bộ đếm và overhead đối tượng.

### 11.2. Bộ nhớ thực tế khác O(S) ở đâu?

Với dictionary con, tổng số cạnh trong một cây có `N` nút là `N-1`. Ta thường nói bộ nhớ cấu trúc O(N), và do `N≤S+1` nên O(S+1), **nếu** chi phí cho một nút và một mục cạnh có chặn hằng số trong mô hình đang dùng.

Trên Python, mỗi nút là một đối tượng, có bảng `children` và các đối tượng khóa/giá trị đi kèm. Hệ số byte có thể lớn; cần đo trên runtime và dữ liệu cụ thể. Một cấu trúc nén đường đi như Radix Trie có thể giảm số nút, nhưng đi kèm cách so khớp **đoạn chuỗi** trên cạnh phức tạp hơn. Bài này tập trung vào Trie **một ký hiệu mỗi cạnh**.

### 11.3. So sánh với lưu từ nguyên vẹn

Lưu `n` từ trong một mảng chuỗi thường cần bộ nhớ tỷ lệ tổng số ký hiệu `S` cộng overhead cho `n` đối tượng chuỗi. Hash Set còn có bảng hash và metadata. Trie chia sẻ các tiền tố nhưng phải lưu nút và cấu trúc nhánh.

Vì vậy, khẳng định “Trie luôn tiết kiệm bộ nhớ hơn Hash Map” hoặc “Trie luôn tốn nhiều bộ nhớ hơn” đều thiếu cơ sở nếu chưa xác định loại khóa, phân bố tiền tố, cách đóng gói và yêu cầu truy vấn.

## 12. Chọn cách biểu diễn tập con: mảng hay dictionary?

Một nút Trie cần ánh xạ **ký hiệu tiếp theo → nút con**. Có hai hướng phổ biến.

### 12.1. Mảng con cố định

Giả sử bảng chữ cái là `a-z`, có `\sigma=26` ký hiệu. Mỗi nút có thể giữ mảng 26 ô con:

```text
children[0]  = cạnh 'a'
children[1]  = cạnh 'b'
...
children[25] = cạnh 'z'
```

Ưu điểm:

- Lấy con theo chỉ số ký hiệu thường O(1) trong RAM.
- Không phải băm ký hiệu cho mỗi bước.
- Có thể duyệt nhãn theo thứ tự cố định dễ dàng.

Nhược điểm:

- Mỗi nút có thể cấp phát 26 ô ngay cả khi chỉ có một nhánh con.
- Bộ nhớ vùng ô theo mô hình là Θ(σN), với `σ` bằng 26 nếu cố định.
- Nếu khóa chứa dấu tiếng Việt, chữ số, ký hiệu Unicode hoặc emoji, bảng chữ cái không còn đơn giản chỉ 26 chữ.

### 12.2. Dictionary con thưa

Mỗi nút chỉ giữ những cạnh **thực sự tồn tại**:

```python
children = {
    "a": node_a,
    "b": node_b,
}
```

Ưu điểm:

- Không cấp phát một ô riêng cho mọi ký hiệu không xuất hiện.
- Linh hoạt với bảng chữ cái lớn hoặc không cố định.
- Code học tập dễ viết và mở rộng.

Nhược điểm:

- Dictionary và các mục hash có overhead bộ nhớ.
- Lấy con là O(1) **kỳ vọng** theo mô hình hash, không phải chứng minh O(1) xấu nhất trong mọi trường hợp.
- Muốn liệt kê theo thứ tự ký tự có thể phải sắp nhãn ở từng nút.

### 12.3. Bảng so sánh

| Tiêu chí | Mảng con kích thước `σ` | Dictionary con |
| --- | --- | --- |
| Tra nhánh theo ký hiệu | O(1) RAM nếu ánh xạ chỉ số hằng số | O(1) kỳ vọng khi hash phù hợp |
| Bộ nhớ mỗi nút | Có tới `σ` ô dù ít con | Phụ thuộc số cạnh thực có và overhead |
| Bảng ký hiệu lớn/Unicode | Khó nếu cấp mảng quá lớn | Linh hoạt hơn |
| Duyệt nhánh theo thứ tự | Quét các chỉ số đã định nghĩa | Có thể cần `sorted` |
| Phù hợp | Alphabet nhỏ và cố định, mật độ nhánh cao | Alphabet lớn hoặc nhánh thưa |

Giữa hai lựa chọn còn có các biểu diễn lai, vector con nhỏ đã sắp, bảng chuyển trạng thái nén và Radix Trie. Chọn biểu diễn cần dựa vào **bảng chữ cái, số nút, phân bố nhánh và bộ nhớ**, không chỉ số khóa.

## 13. Unicode: một “ký tự nhìn thấy” không luôn là một đơn vị xử lý

Với bài toán từ điển tiếng Việt, khái niệm “ký tự” cần được làm rõ.

Trong Python, vòng lặp `for char in text` duyệt **điểm mã Unicode** (*code point*). Một chữ có dấu mà người dùng nhìn thấy có thể được biểu diễn bởi:

- Một điểm mã đã tổ hợp sẵn, ví dụ `"à"`.
- Ký tự cơ sở `"a"` và dấu kết hợp `"\u0300"`.

Hai chuỗi có thể hiển thị giống nhau nhưng có **dãy điểm mã khác nhau** nếu chưa chuẩn hóa. Trie ở phần trước xem đó là hai đường khác nhau.

### 13.1. Ví dụ chuẩn hóa NFC

```python
import unicodedata

composed = "bàn"       # Dạng có ký tự 'à' tổ hợp sẵn
decomposed = "ba\u0300n"  # a + dấu huyền kết hợp

assert composed != decomposed
assert unicodedata.normalize("NFC", composed) == \
       unicodedata.normalize("NFC", decomposed)
```

Nếu một nguồn dữ liệu dùng NFC còn nguồn khác dùng ký tự cơ sở + dấu kết hợp, chèn cả hai vào Trie **không chuẩn hóa** sẽ tạo hai khóa khác nhau về mặt chuỗi.

Khi ứng dụng muốn coi chúng là một từ, hãy chuẩn hóa **cả khi chèn lẫn khi truy vấn** theo cùng quy tắc.

### 13.2. Phân biệt hoa/thường và dấu

Ví dụ một bước chuẩn hóa cho mục đích tìm kiếm **không phân biệt hoa/thường**:

```python
import unicodedata


def normalize_key(text):
    return unicodedata.normalize(
        "NFC", unicodedata.normalize("NFC", text).casefold()
    )


trie = Trie()
assert trie.insert(normalize_key("Bàn"))
assert not trie.insert(normalize_key("ba\u0300n"))
assert trie.contains(normalize_key("BÀN"))
```

`casefold()` là phép biến đổi Unicode mạnh hơn `lower()` cho một số chữ cái; nó có thể làm thay đổi số ký hiệu của khóa. `NFC` giúp thống nhất những dạng biểu diễn tương đương theo chuẩn này.

**Không được tự suy ra** `normalize_key("ban")==normalize_key("bàn")`: hàm trên **không xóa dấu**. Tìm kiếm không phân biệt dấu là một **quy tắc khác** cần được định nghĩa và kiểm tra riêng vì nó có thể làm nhiều khóa khác nhau hợp nhất.

### 13.3. Độ dài ký hiệu phụ thuộc quy tắc phân đoạn

Một người dùng nhìn thấy một cụm ký tự có thể tương ứng nhiều code point hoặc nhiều byte UTF-8. Trong mã ở bài này:

- `L=len(word)` là **số code point của chuỗi Python**.
- Chi phí duyệt là theo số code point sau khi áp dụng bước chuẩn hóa.
- Nếu ứng dụng muốn một cạnh cho **cụm tự vị** (*grapheme cluster*) thay vì code point, cần một bước phân đoạn khác và mô hình thời gian/bộ nhớ tương ứng.
- Nếu Trie lưu byte UTF-8, `L` nên được định nghĩa bằng **số byte**, không phải số chữ người dùng nhìn thấy.

Những cách phân đoạn này đều có thể hợp lệ, nhưng việc trộn lẫn chúng khiến thao tác tiền tố và số bước phân tích dễ sai.

## 14. Tự động hoàn thành (*autocomplete*) là hai việc nối tiếp

Một hệ gợi ý từ theo tiền tố thường gồm:

1. **Định vị nút tiền tố** `prefix`.
2. **Duyệt và chọn kết quả** từ cây con của nút đó.

Điểm mạnh của Trie là bước 1 có thể thực hiện theo độ dài tiền tố, không phải dò từng khóa trong cả tập.

### 14.1. Ví dụ gợi ý

Nếu Trie lưu:

```text
an, anh, ao, ba, ban
```

thì:

```text
words_with_prefix("a")       -> ["an", "anh", "ao"]
words_with_prefix("an")      -> ["an", "anh"]
words_with_prefix("ban")     -> ["ban"]
words_with_prefix("b", 1)    -> ["ba"]
words_with_prefix("xyz")     -> []
```

Danh sách trên tuân thứ tự ký tự Unicode của mã Python. Nó **không phải bảng xếp hạng theo tần suất tìm kiếm**, độ phổ biến hay ngữ cảnh người dùng.

### 14.2. Gợi ý theo độ phổ biến cần dữ liệu bổ sung

Nếu ứng dụng muốn trả “3 từ được tìm nhiều nhất có tiền tố `a`”, các nút kết thúc có thể cần lưu:

- `frequency`: số lượt dùng từ hoặc điểm ưu tiên.
- Metadata như ID từ, thời điểm sử dụng, loại từ.
- Một cơ chế chọn top-k trong cây con hoặc chỉ mục kết quả được cập nhật.

Duyệt tất cả khóa dưới một tiền tố rồi sắp theo tần suất có chi phí phụ thuộc số khóa ứng viên và số ký hiệu đầu ra. Chỉ việc đi tới nút tiền tố **không giải quyết miễn phí** phần chọn top-k.

Nếu lưu sẵn danh sách top-k tại từng nút để trả lời nhanh, việc thêm/xóa hoặc đổi tần suất một từ phải cập nhật thông tin trên đường tiền tố, làm tăng thời gian cập nhật và bộ nhớ. Đây là đánh đổi quen thuộc giữa **chi phí xây dựng, cập nhật, truy vấn và dung lượng lưu**.

### 14.3. Giới hạn `limit` không đồng nghĩa O(limit)

Nếu người dùng yêu cầu hai gợi ý, thuật toán có thể dừng sau khi tìm đủ hai khóa. Nhưng để tìm ra chúng, đôi khi phải đi qua nhiều nút trung gian hoặc sắp nhánh, đặc biệt khi từ rất dài hoặc một vài nhánh có cấu trúc phức tạp.

Vì vậy, cần báo chi phí theo **độ dài tiền tố, số nút đã xét, quy tắc thứ tự và tổng độ dài kết quả**, chứ không chỉ số gợi ý được trả về.

## 15. Các ứng dụng điển hình của Trie

### 15.1. Từ điển và kiểm tra tiền tố

Ứng dụng chính là:

- Kiểm tra từ có tồn tại.
- Kiểm tra tiền tố có từ nào khớp.
- Liệt kê các từ bắt đầu bằng tiền tố.
- Đếm các từ dưới một tiền tố.

Các thao tác này khớp trực tiếp với cấu trúc cây tiền tố.

### 15.2. Gợi ý nhập liệu

Khi người dùng lần lượt gõ `a`, `an`, `anh`, giao diện có thể giữ đường đi trong Trie để cập nhật gợi ý. Nếu truy vấn được gửi lại từ đầu ở mỗi lần gõ, mỗi lần vẫn chỉ cần đi theo chuỗi hiện tại; việc giữ trạng thái con trỏ tiền tố có thể là một tối ưu cài đặt **nếu** ứng dụng xử lý được xóa ký tự, sửa giữa và thay đổi dữ liệu.

### 15.3. Đếm từ theo tiền tố trong bộ từ khóa

Nếu cần hỏi thường xuyên “có bao nhiêu khóa bắt đầu bằng `th`”, một bộ đếm `subtree_words` như ở trên cho phép trả lời nhanh sau khi định vị nút tiền tố.

Đổi lại, **mọi lần thêm/xóa thành công** phải cập nhật bộ đếm trên đường đi, nếu không chỉ mục thống kê sẽ sai. Đây là một ví dụ về bất biến biểu diễn dùng để đánh đổi chi phí cập nhật lấy tốc độ truy vấn.

### 15.4. Định tuyến theo dãy bit

Ý tưởng Trie có thể áp dụng cho **chuỗi bit**: mỗi nút có nhánh 0 và 1. Một ứng dụng điển hình là tìm tiền tố khớp dài nhất của địa chỉ mạng trong cấu trúc thích hợp.

Nhưng Trie bit đơn giản và Trie định tuyến được tối ưu có thể có cách nén, xử lý độ dài tiền tố và chính sách ưu tiên khác nhau. Bài này chỉ dùng ví dụ để thấy rằng **ký hiệu trên cạnh không bắt buộc là chữ cái**.

### 15.5. Lưu và tra chuỗi khóa có tiền tố chung

Trường hợp nhiều khóa có phần đầu giống nhau, Trie giúp tránh lưu lặp lại toàn bộ đường ký hiệu ở cấp nút. Tuy nhiên, phải đo cả overhead nút và bảng con; bài toán cần tra cứu chính xác mà không có truy vấn tiền tố vẫn có thể phù hợp với Hash Map đơn giản hơn.

## 16. Trie, Hash Map, BST và mảng từ: chọn thế nào?

| Yêu cầu | Trie không nén | Hash Map / Hash Set | BST cân bằng | Mảng từ |
| --- | --- | --- | --- | --- |
| Tìm chính xác khóa dài `L` | O(L) kỳ vọng theo cạnh ký tự | Thường O(L) để hash khóa, cộng tra bucket kỳ vọng; có thể khác nếu hash đã được lưu | O(log n) phép so sánh toàn khóa; mỗi so sánh có thể tốn O(L) | O(n) phép so sánh nếu chưa sắp |
| Kiểm tra có khóa theo tiền tố | O(P) kỳ vọng khi đường tồn tại/được dọn đúng | Thường cần chỉ mục bổ sung hoặc duyệt nhiều khóa | Có thể tìm cận và kiểm tra ứng viên theo thứ tự | Có thể dùng tìm nhị phân nếu mảng sắp và có phép so sánh phù hợp |
| Liệt kê tất cả khóa cùng tiền tố | Duyệt cây con của nút tiền tố | Có thể phải quét nhiều khóa nếu không có chỉ mục khác | Có thể duyệt khoảng khóa | Duyệt dải liên tiếp nếu đã sắp đúng |
| Thêm/xóa khóa | O(L) kỳ vọng theo cạnh | O(1) kỳ vọng theo số khóa khi hash/so sánh O(1), cộng chi phí xử lý ký tự nếu có | O(log n) so sánh khóa và cân bằng | Thêm cuối khấu hao O(1), chèn giữ thứ tự có thể O(n) |
| Bộ nhớ | Theo số tiền tố/nút và cạnh, nhiều metadata | Theo số mục, bucket và khóa | Theo số nút, liên kết và metadata cân bằng | Theo số phần tử và chuỗi/đối tượng |
| Lợi thế chính | Truy vấn theo tiền tố | Tra chính xác một khóa | Thứ tự và truy vấn khoảng | Duyệt liên tiếp, truy cập chỉ số |

**Chú ý đơn vị:** Hàng về Hash Map có thể được trình bày là “O(1) kỳ vọng” nếu mô hình giả định **hash và so sánh khóa là thao tác O(1)**. Với chuỗi dài, việc tính hash hoặc so sánh vẫn có thể phụ thuộc `L`. Hàng về BST đếm phép so sánh khóa; nếu mỗi so sánh phải duyệt nhiều ký tự, cần nhân thêm chi phí đó.

### 16.1. Quyết định theo toàn bộ luồng công việc

Giả sử có `n` từ ban đầu, `q` truy vấn tiền tố và `u` cập nhật:

- Xây Trie từ các từ: thường O(S) kỳ vọng theo số ký hiệu của đầu vào, chưa kể cấp phát và chuẩn hóa.
- Mỗi truy vấn định vị tiền tố dài `P`: O(P) kỳ vọng, **chưa kể kết quả phải xuất**.
- Mỗi cập nhật khóa dài `L`: O(L) kỳ vọng.
- Bộ nhớ: phụ thuộc số nút tiền tố thực và overhead của cách lưu con.

Nếu chỉ có một lần kiểm tra khóa nguyên vẹn, chi phí tạo Trie có thể không đáng. Nếu có rất nhiều truy vấn tiền tố, phần đầu tư xây cấu trúc có thể đem lại lợi ích. Tần suất thao tác và phân bố dữ liệu mới là cơ sở lựa chọn.

## 17. Các trường hợp biên và lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Coi có đường đi là có khóa hoàn chỉnh | `contains("a")` trả True dù chỉ lưu `an` | Kiểm tra `terminal` tại nút cuối |
| Chèn từ dài rồi xóa dấu kết thúc của từ ngắn | Mất khóa là tiền tố của từ khác | Giữ dấu kết thúc độc lập với tập con |
| Xóa một từ rồi xóa luôn mọi nút trên đường | Làm mất các khóa dùng chung tiền tố | Chỉ cắt nút có `subtree_words=0` |
| Chèn trùng nhưng vẫn tăng bộ đếm | `count_prefix` và `len` sai | Kiểm tra khóa đã có trước khi tăng |
| Xóa khóa không tồn tại nhưng vẫn giảm bộ đếm | Có thể tạo số âm và phá bất biến | Kiểm tra đường đi và dấu kết thúc trước |
| Chỉ dùng `children` mà không đánh dấu kết thúc | Không phân biệt `an` với tiền tố của `anh` | Dùng `terminal` hoặc cơ chế tương đương |
| Tự giả định thứ tự dictionary là từ điển | Kết quả autocomplete không như cam kết | Định nghĩa thứ tự và sắp nhãn khi cần |
| Gọi O(L) là chặn tuyệt đối cho mọi bảng con | Hash, mảng và cấu trúc con có giả định khác | Nêu mô hình truy cập cạnh |
| Bỏ qua Unicode và chuẩn hóa | Từ hiển thị giống nhau nhưng khác đường đi | Chuẩn hóa nhất quán khi thêm và tìm |
| Khẳng định Trie luôn tiết kiệm RAM | Một nút có thể có overhead lớn | Đo số nút, số cạnh, bucket và byte thực tế |
| Dùng DFS đệ quy trên từ rất dài | Có thể vượt giới hạn đệ quy của runtime | Dùng duyệt lặp hoặc bảo đảm giới hạn chiều sâu |
| Chỉ tính O(P) cho toàn bộ autocomplete | Quên duyệt cây con và tạo kết quả | Tính thêm số nút đã xem và độ dài đầu ra |

### 17.1. Kiểm thử khi có xóa và chèn xen kẽ

Một bộ kiểm thử nên bao gồm:

- Chèn `an`, rồi chèn `anh`, xóa `an`, bảo đảm `anh` còn.
- Chèn `an` hai lần, kiểm tra số khóa không tăng lần hai.
- Xóa khóa chưa tồn tại, bảo đảm không thay đổi kích thước.
- Xóa từ dài duy nhất ở một nhánh, bảo đảm nhánh rỗng được dọn.
- Xóa tới khi Trie rỗng, kiểm tra `len=0`, `count_prefix("")=0`.
- Chèn/xóa chuỗi rỗng nếu hợp đồng cho phép.
- Gọi autocomplete với `limit=0`, tiền tố không có và tiền tố đã tồn tại.
- Thử các chuỗi Unicode có dấu ở dạng tổ hợp sẵn và phân tách.

Những kiểm tra này tập trung vào **bất biến và hành vi**, không phụ thuộc hình dạng biểu diễn nội bộ cụ thể.

## 18. Bài tập thực hành có hướng dẫn giải

### Bài 1 — Vẽ cây tiền tố

Chèn lần lượt các khóa `to, top, tone, tea`. Hãy vẽ Trie và đánh dấu nút kết thúc khóa.

**Gợi ý:** Gốc có nhánh `t`. Từ `t` tách `o` và `e`. Nút `t→o` là kết thúc `to` và còn có các nhánh `p` (cho `top`) và `n→e` (cho `tone`). Nhánh `t→e→a` kết thúc `tea`. Đường có con vẫn có thể kết thúc từ.

### Bài 2 — Phân biệt từ và tiền tố

Trie lưu `an, anh, ao, ba, ban`. Xác định kết quả:

```text
contains("a")
contains("an")
starts_with("a")
starts_with("ax")
count_prefix("an")
count_prefix("")
```

**Gợi ý:** Lần lượt `False, True, True, False, 2, 5`. `count_prefix("")` bằng tổng số khóa phân biệt khi gốc lưu đúng `subtree_words`.

### Bài 3 — Xóa khóa là tiền tố

Trie chỉ chứa `cat, cats, car`. Xóa `cat`. Nút nào được loại bỏ và khóa nào còn tồn tại?

**Gợi ý:** Chỉ bỏ dấu kết thúc của nút `c→a→t`; nút `t` vẫn cần để đi tới `cats`. Không được xóa nhánh `c→a→r` của `car`. Nếu dùng bộ đếm, giảm trên đường gốc→c→a→t.

### Bài 4 — Xóa nhánh không còn khóa

Trie chứa `car` và `cat`. Xóa `car`, rồi xóa `cat`. Điều gì xảy ra với các nhánh?

**Gợi ý:** Sau xóa `car`, nhánh `c→a→r` mất nút `r` nhưng `c→a→t` vẫn còn. Sau xóa `cat`, nhánh `t`, rồi `a`, rồi `c` có thể được dọn nếu không còn khóa nào; gốc vẫn tồn tại.

### Bài 5 — Đếm nút và tổng độ dài

Với các khóa `an, anh, ao, ba, ban`, hãy tính tổng độ dài `S` và số nút `N` của Trie không nén.

**Gợi ý:** `S=2+3+2+2+3=12`. Các tiền tố không rỗng phân biệt là `a, an, anh, ao, b, ba, ban`, có 7 nút; cộng gốc thành `N=8`. Đây là ví dụ chia sẻ tiền tố, không phải số byte thực của các đối tượng.

### Bài 6 — Phân tích thời gian

Giả sử mỗi nút dùng dictionary con, tra một cạnh O(1) kỳ vọng. Một khóa dài `L=20` ký hiệu và tiền tố dài `P=5`. Hãy nêu bậc thời gian của `contains`, `starts_with` và `count_prefix`.

**Gợi ý:** `contains` O(L)=O(20); `starts_with` và `count_prefix` O(P)=O(5) theo mô hình. Các con số thể hiện số bước theo ký hiệu, không phải thời gian micro giây và không bao gồm việc tạo một danh sách kết quả lớn.

### Bài 7 — Autocomplete với giới hạn

Trie lưu `an, anh, ao, ba, ban` và liệt kê theo thứ tự ký tự Unicode. Kết quả của `words_with_prefix("a", limit=2)` là gì? Vì sao không thể nói mọi autocomplete luôn O(P)?

**Gợi ý:** Kết quả `["an", "anh"]`. Ngoài tìm nút tiền tố, thuật toán phải đi qua nhánh và tạo chuỗi đầu ra, đôi khi còn sắp nhãn con.

### Bài 8 — Unicode và chuẩn hóa

Người dùng nhập hai chuỗi `"bàn"` và `"ba\u0300n"`. Vì sao Trie theo code point có thể xem là hai khóa khác nhau? Nêu cách xử lý nếu muốn gộp chúng.

**Gợi ý:** Một chuỗi dùng ký tự `à` tổ hợp sẵn, chuỗi kia dùng `a` cùng dấu huyền kết hợp. Chuẩn hóa NFC nhất quán trước khi chèn, tra và xóa để đưa những dạng tương đương về cùng biểu diễn.

### Bài 9 — Mảng con và dictionary

Một Trie có 1.000 nút, bảng chữ cái 26 ký hiệu. Nếu mỗi nút giữ mảng 26 tham chiếu, có bao nhiêu ô tham chiếu được cấp phát? Tại sao dictionary con có thể dùng ít ô liên kết hơn?

**Gợi ý:** Có `1.000×26=26.000` ô tham chiếu, dù nhiều ô rỗng. Dictionary con chỉ giữ các cạnh thật, nhưng có overhead hash và metadata riêng; phải đo byte thực tế trước khi kết luận phương án nào tiết kiệm RAM hơn.

### Bài 10 — Chọn cấu trúc phù hợp

Hệ thống A chỉ kiểm tra một mã đầy đủ có tồn tại; hệ thống B cần kiểm tra, đếm và liệt kê từ theo tiền tố nhiều lần. Cả hai lưu cùng số khóa.

**Gợi ý:** A có thể dùng Hash Set đơn giản. B nên cân nhắc Trie vì hỗ trợ các thao tác tiền tố trực tiếp; tuy nhiên cần tính chi phí xây, byte/nút, Unicode và chi phí xuất kết quả. Không có cấu trúc nào tối ưu tuyệt đối cho mọi workload.

### Bài 11 — Bài nâng cao: tần suất từ

Muốn gợi ý từ phổ biến nhất theo tiền tố, bạn định lưu `frequency` ở mỗi nút kết thúc. Như vậy đã đủ để trả top-5 mọi tiền tố trong O(P) chưa?

**Gợi ý:** Chưa. Đi tới nút tiền tố mất O(P), nhưng muốn biết năm khóa có tần suất cao nhất trong cây con phải duyệt ứng viên hoặc duy trì chỉ mục top-5 tại các nút. Nếu duy trì chỉ mục, mọi lần thay đổi tần suất hoặc thêm/xóa cần cập nhật dữ liệu liên quan.

## 19. Mẫu phân tích và tự kiểm tra trước khi chọn Trie

Khi giải bài toán chỉ mục chuỗi, hãy ghi rõ:

```text
1. Hợp đồng:
   - Lưu tập khóa, đa tập hay Map từ khóa sang giá trị?
   - Khóa trùng được bỏ qua, cộng tần suất hay ghi đè?
   - Có cho phép khóa rỗng không?

2. Đơn vị ký hiệu:
   - Byte UTF-8, code point hay grapheme cluster?
   - Có chuẩn hóa Unicode, casefold, bỏ dấu không?
   - Một truy vấn được chuẩn hóa cùng cách với khi lưu chứ?

3. Các phép toán cần:
   - contains(word)?
   - starts_with(prefix)?
   - count_prefix(prefix)?
   - insert/delete?
   - autocomplete theo thứ tự ký tự hay độ phổ biến?

4. Biểu diễn:
   - Mỗi cạnh một ký hiệu hay đường đi được nén?
   - children là dictionary, mảng cố định hay cấu trúc lai?
   - Có terminal, subtree_words và metadata khác?

5. Bất biến:
   - Đường từ gốc mô tả một tiền tố duy nhất?
   - terminal quyết định khóa đầy đủ?
   - Bộ đếm của nút bằng số khóa trong cây con?
   - Xóa không làm mất nhánh còn được dùng?

6. Chi phí:
   - L = chiều dài khóa; P = chiều dài tiền tố.
   - S = tổng số ký hiệu; N = số nút; Z = độ dài đầu ra.
   - Chi phí chọn một cạnh thuộc mô hình nào?
   - Chi phí duyệt/sắp kết quả đã tính chưa?
   - Bộ nhớ nút, bảng con và sức chứa dư ra sao?

7. Kiểm thử:
   - Khóa là tiền tố của khóa khác.
   - Thêm trùng, xóa thiếu, xóa đến rỗng.
   - Prefix rỗng, khóa rỗng, Unicode nhiều biểu diễn.
   - Các giới hạn kết quả và thứ tự xuất.
```

**Kết luận:** Trie tổ chức tập khóa thành **cây các tiền tố**. Đường đi từ gốc cho biết tiền tố, còn dấu `terminal` mới xác định một khóa hoàn chỉnh. Nhờ chia sẻ tiền tố, Trie hỗ trợ tìm chính xác, kiểm tra tiền tố và đếm theo tiền tố bằng thời gian phụ thuộc **độ dài chuỗi được hỏi**, dưới giả định chi phí chọn cạnh phù hợp. Đổi lại, việc xóa phải bảo toàn các nhánh dùng chung, autocomplete phải trả chi phí theo kết quả, và bộ nhớ nút có thể lớn. Khi kết hợp đúng bất biến, quy tắc Unicode, độ phức tạp và workload thực tế, Trie trở thành công cụ hữu ích cho các bài toán chỉ mục chuỗi mà mảng, Hash Map hoặc BST không giải quyết trực tiếp với cùng cách tổ chức.
