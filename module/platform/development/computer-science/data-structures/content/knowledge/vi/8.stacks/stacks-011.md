# So sánh chi phí và lựa chọn cách biểu diễn ngăn xếp

Một trình phân tích biểu thức cần lưu các dấu ngoặc đang mở; trình duyệt có thể cần theo dõi lịch sử thao tác để hỗ trợ **Undo**; thuật toán DFS cần một nơi lưu các đỉnh sẽ được xử lý tiếp theo. Cả ba đều có thể sử dụng **ngăn xếp (stack)**, nhưng cách **biểu diễn** stack trong bộ nhớ không nhất thiết giống nhau.

Nếu dữ liệu có số phần tử tối đa biết trước, **mảng cố định** có thể kiểm soát dung lượng và thời gian xử lý. Nếu kích thước thay đổi linh hoạt, **mảng động** thường đơn giản và khai thác bộ nhớ liên tục. Nếu cần tạo/xóa nút ở đỉnh mà không phải dời phần tử, **danh sách liên kết đơn** là một lựa chọn khác. Một số thư viện còn cung cấp **deque** hoặc kiểu stack bất biến.

Bài này thuộc chương **Ngăn xếp** trong module cấu trúc dữ liệu. Trọng tâm là **so sánh thời gian, bộ nhớ, hành vi lỗi, chi phí thực tế** và cách chọn hiện thực đáp ứng đúng bất biến của stack, thay vì chỉ học thuộc bảng Big-O.

## 1. Một Stack ADT, nhiều hiện thực

**Stack** là kiểu dữ liệu trừu tượng (*abstract data type – ADT*) tuân thủ nguyên tắc **LIFO** (*Last In, First Out*): phần tử được thêm **sau cùng** được lấy ra **đầu tiên**.

Những thao tác căn bản:

| Thao tác | Hành vi logic | Có thay đổi stack không? |
| --- | --- | --- |
| `push(x)` | Đưa `x` lên đỉnh | Có |
| `pop()` | Lấy và xóa phần tử ở đỉnh | Có |
| `peek()` hoặc `top()` | Xem phần tử đỉnh nhưng không xóa | Không |
| `is_empty()` | Hỏi stack có rỗng không | Không |
| `size()` | Số phần tử đang lưu | Không |

Ví dụ:

```text
Ban đầu: []

push("A")   → [A]          đỉnh: A
push("B")   → [A, B]       đỉnh: B
push("C")   → [A, B, C]    đỉnh: C
pop()       → trả C; [A, B]
peek()      → trả B; [A, B] không đổi
```

Ta ký hiệu danh sách từ **đáy đến đỉnh**, đỉnh nằm **bên phải**. Đối với cài đặt bằng danh sách liên kết, ta cũng có thể đặt đỉnh tại **đầu danh sách** để thao tác được thực hiện nhanh nhất.

**Bất biến lõi:** nếu chưa có thao tác nào lấy ra, chuỗi `pop()` phải trả các phần tử theo **thứ tự ngược** với chuỗi `push()`. Cấu trúc lưu trữ là mảng, các nút liên kết hay deque đều phải bảo toàn bất biến ấy.

### Phải thống nhất hợp đồng lỗi

Trong stack rỗng, `pop()` và `peek()` không có giá trị để trả. Một API có thể:

- Phát sinh ngoại lệ (ví dụ `IndexError` trong Python).
- Trả `(found, value)` hoặc kiểu `Option` để phân biệt không tìm thấy.
- Trả một giá trị đánh dấu riêng, **chỉ khi giá trị ấy không hợp lệ như dữ liệu stack**.

Không nên ngầm xem `None` là “stack rỗng” nếu `None` có thể được `push` như một phần tử hợp lệ. Tương tự, stack có **dung lượng cố định** phải quyết định trước cách báo **overflow** khi đầy.

## 2. Tiêu chí so sánh đúng

Đặt:

- `n`: số phần tử hiện đang lưu.
- `C`: dung lượng đã cấp cho mảng; với mảng cố định, đây là giới hạn tối đa.
- `m`: số thao tác trong một chuỗi `push/pop` khi phân tích **chi phí khấu hao**.

Các tiêu chí đáng xét:

| Tiêu chí | Câu hỏi cần trả lời |
| --- | --- |
| **Thời gian push/pop/peek** | Trung bình, khấu hao hay bảo đảm từng lần? |
| **Chi phí lúc mở rộng** | Có phải sao chép các phần tử khi đầy không? |
| **Dung lượng và bộ nhớ** | Cấp phát trước `C` ô hay chỉ cấp theo `n` phần tử? |
| **Tính cục bộ bộ nhớ** | Phần tử gần nhau trong bộ nhớ hay là các nút rời rạc? |
| **Cấp phát/giải phóng** | Mỗi `push` cần cấp phát nút mới hay dùng vùng dự phòng? |
| **Giới hạn cứng** | Stack phải chặn `push` khi đạt trần hay có thể lớn thêm? |
| **Tính ổn định của thời gian** | Có chấp nhận một lần `push` chậm do resize? |
| **Tính bất biến/chia sẻ phiên bản** | Có cần giữ lại trạng thái stack cũ để Undo không? |

**Big-O chưa đủ để quyết định.** Hai hiện thực đều có `O(1)` cho `push` trong một mô hình phù hợp, nhưng một hiện thực có thể phải cấp phát nút trên mỗi lần chèn, còn hiện thực khác chỉ ghi vào một ô còn trống.

## 3. Biểu diễn bằng mảng cố định

Giả sử đã cấp trước mảng `buffer` gồm `C` ô. Một số nguyên `size` ghi số phần tử thực có; phần tử đỉnh nằm tại chỉ số `size - 1` khi `size > 0`.

```text
C = 6, size = 3

chỉ số:    0      1      2      3      4      5
          ┌──────┬──────┬──────┬──────┬──────┬──────┐
buffer:   │  A   │  B   │  C   │  —   │  —   │  —   │
          └──────┴──────┴──────┴──────┴──────┴──────┘
                            ↑
                          top = 2
```

**Bất biến:** `0 <= size <= C`. Chỉ các ô từ `0` đến `size - 1` là nội dung logic của stack. Các ô còn lại là dung lượng dự phòng.

### Cài đặt Python minh họa

Dù Python `list` là một mảng động ở cấp thư viện, ta có thể **cấp trước đủ ô và tự chặn dung lượng** để minh họa ADT stack trên mảng cố định.

```python
class FixedArrayStack:
    def __init__(self, capacity: int):
        if capacity < 0:
            raise ValueError("capacity phải không âm")
        self._capacity = capacity
        self._buffer = [None] * capacity
        self._size = 0

    def push(self, item):
        if self._size == self._capacity:
            raise OverflowError("stack đã đầy")
        self._buffer[self._size] = item
        self._size += 1

    def pop(self):
        if self._size == 0:
            raise IndexError("pop từ stack rỗng")
        self._size -= 1
        item = self._buffer[self._size]
        self._buffer[self._size] = None  # Bỏ tham chiếu không cần thiết
        return item

    def peek(self):
        if self._size == 0:
            raise IndexError("peek từ stack rỗng")
        return self._buffer[self._size - 1]

    def is_empty(self):
        return self._size == 0

    def size(self):
        return self._size


stack = FixedArrayStack(3)
stack.push("A")
stack.push(None)                  # None là dữ liệu hợp lệ
stack.push("C")

assert stack.size() == 3
assert stack.pop() == "C"
assert stack.pop() is None
assert stack.peek() == "A"
```

Ở đây việc ghi `None` vào ô đã `pop` **không có nghĩa `None` là dấu ô trống được phép dùng để suy luận trạng thái**. Biến `_size` mới là nguồn xác định các ô hợp lệ, nên vẫn lưu được `None` như dữ liệu.

### Độ phức tạp

- `push`, `pop`, `peek`, `size`, `is_empty`: **`O(1)`** khi thao tác trên ô mảng có chi phí hằng số.
- Khởi tạo và cấp trước `C` ô: **`O(C)` thời gian và `O(C)` bộ nhớ**.
- Không có resize, nên khi đạt trần phải **báo overflow, từ chối chèn hoặc áp dụng chính sách khác đã định nghĩa**.

**Ưu điểm:** đơn giản, truy cập đỉnh trực tiếp, dung lượng dự báo được, ít thao tác cấp phát lại sau khởi tạo.

**Nhược điểm:** phải chọn `C` trước; cấp thừa gây lãng phí ô, cấp thiếu làm từ chối `push`; không hợp với dữ liệu tăng không đoán trước.

Lưu ý: nếu dùng ngôn ngữ cấp phát động, quá trình tạo các đối tượng được `push` và quản lý bộ nhớ của chính chúng còn có chi phí riêng, không nằm trong bảng chi phí truy cập ô mảng.

## 4. Biểu diễn bằng mảng động

Với **mảng động** (*dynamic array*), có thể tăng dung lượng khi mảng đầy. Trong Python, `list` cung cấp ngay các thao tác ở cuối thích hợp cho stack.

```python
stack = []

stack.append("A")   # push
stack.append("B")
stack.append("C")

assert stack[-1] == "C"  # peek
assert stack.pop() == "C"
assert stack.pop() == "B"
assert stack == ["A"]
```

**Quy tắc quan trọng:** đỉnh phải được đặt ở **cuối list** nếu muốn `append` và `pop()` nhanh. Dùng `insert(0, x)` hoặc `pop(0)` để thao tác ở đầu list sẽ phải dịch nhiều phần tử và có chi phí `O(n)` theo cách cài mảng động thông dụng.

### Vì sao `append` là `O(1)` khấu hao, không phải luôn `O(1)`?

Giả sử mảng đang có `n` phần tử và `capacity = n`. Để chèn thêm:

1. Cấp một vùng nhớ lớn hơn.
2. Sao chép hoặc chuyển các tham chiếu/phần tử đang có sang vùng mới.
3. Thêm phần tử mới, cập nhật kích thước và dung lượng.

Lần chèn kích hoạt mở rộng có thể tốn **`O(n)`**. Tuy nhiên, nếu dung lượng được tăng theo **hệ số lớn hơn 1**, chẳng hạn gấp đôi để minh họa, nhiều lần chèn tiếp theo dùng các ô dự phòng và không phải sao chép.

```text
capacity: 1 → 2 → 4 → 8 → 16 → ...
sao chép: 1 + 2 + 4 + 8 + ... < 2n
```

Trên một chuỗi `n` lần chèn, tổng số phần tử cần sao chép do các lần tăng theo lũy thừa hai là `O(n)`; chia cho `n` lần chèn được **`O(1)` khấu hao mỗi `push`**. Đây là phân tích cho chính sách tăng dung lượng theo cấp số nhân, không phải khẳng định Python luôn nhân đôi dung lượng.

### Pop và thu nhỏ mảng

`pop` ở cuối mảng động thường chỉ làm giảm số phần tử và giải phóng tham chiếu ở ô cuối, nên **`O(1)`** khi không cần co vùng nhớ. Một số hiện thực có thể **thu nhỏ bộ đệm** ở các ngưỡng nhất định; một lần co có thể mất `O(n)` và phải được xét trong phân tích khấu hao.

Nếu một hiện thực tự viết cứ giảm dung lượng ngay khi vừa bớt một phần tử, chuỗi `push/pop` gần ngưỡng có thể gây **co–giãn liên tục**. Một chiến lược phổ biến là chỉ co khi số phần tử xuống thấp hơn đáng kể so với dung lượng, ví dụ nhỏ hơn một phần tư, thay vì co ngay dưới mức đầy. Không nên nhầm ngưỡng minh họa này với chính sách bắt buộc của thư viện Python.

### Lớp bọc stack dùng mảng động

```python
class DynamicArrayStack:
    def __init__(self):
        self._items = []

    def push(self, item):
        self._items.append(item)

    def pop(self):
        if not self._items:
            raise IndexError("pop từ stack rỗng")
        return self._items.pop()

    def peek(self):
        if not self._items:
            raise IndexError("peek từ stack rỗng")
        return self._items[-1]

    def is_empty(self):
        return not self._items

    def size(self):
        return len(self._items)


s = DynamicArrayStack()
s.push("A")
s.push("B")
assert s.pop() == "B"
assert s.peek() == "A"
```

**Ưu điểm:** không phải ấn định dung lượng, truy cập đỉnh nhanh, bố trí các ô tham chiếu tương đối liên tục, mã đơn giản.

**Nhược điểm:** có dung lượng dự phòng, chi phí mở rộng không đồng đều giữa các lần chèn; một số lần thao tác có thể bị ảnh hưởng bởi phân bổ bộ nhớ và sao chép.

## 5. Biểu diễn bằng danh sách liên kết đơn

Với **danh sách liên kết đơn** (*singly linked list*), mỗi nút chứa một giá trị và một liên kết tới nút kế tiếp. Ta đặt **đỉnh stack tại đầu danh sách**:

```text
       top/head
          │
          ▼
        [ C ] → [ B ] → [ A ] → None
          ↑
      pop lấy C trước
```

- `push(x)`: tạo nút mới, cho nút mới trỏ tới đỉnh cũ, rồi đổi đỉnh thành nút mới.
- `pop()`: lấy giá trị tại đỉnh, chuyển đỉnh tới nút kế tiếp.
- `peek()`: đọc giá trị tại nút đỉnh, không thay đổi liên kết.

**Đặt đỉnh ở cuối danh sách liên kết đơn không có con trỏ tới nút trước sẽ làm `pop` khó:** muốn tìm nút đứng trước đuôi, có thể phải duyệt `O(n)`. Đặt đỉnh ở **head** cho phép cả hai thao tác chèn/xóa thực hiện tại một vị trí đã biết.

### Cài đặt Python

```python
class Node:
    def __init__(self, value, next_node=None):
        self.value = value
        self.next = next_node


class LinkedStack:
    def __init__(self):
        self._head = None
        self._size = 0

    def push(self, item):
        self._head = Node(item, self._head)
        self._size += 1

    def pop(self):
        if self._head is None:
            raise IndexError("pop từ stack rỗng")
        old_head = self._head
        self._head = old_head.next
        self._size -= 1
        value = old_head.value
        old_head.next = None
        return value

    def peek(self):
        if self._head is None:
            raise IndexError("peek từ stack rỗng")
        return self._head.value

    def is_empty(self):
        return self._head is None

    def size(self):
        return self._size


s = LinkedStack()
s.push("A")
s.push("B")
s.push(None)

assert s.size() == 3
assert s.pop() is None
assert s.pop() == "B"
assert s.pop() == "A"
assert s.is_empty()
```

**Bất biến:**

1. Nếu `_size == 0` thì `_head is None`, và ngược lại.
2. Số nút có thể đi tới từ `_head` bằng đúng `_size`.
3. Các nút tạo thành một chuỗi không có chu trình theo thiết kế này.
4. `_head.value` là giá trị được thêm gần nhất nhưng chưa bị `pop`.

### Độ phức tạp và chi phí cấp phát

Với tham chiếu trực tiếp tới `head`, các thao tác `push`, `pop`, `peek` đều có **`O(1)` bước liên kết**, và `size` cũng `O(1)` nếu duy trì biến đếm. Không có thao tác **sao chép toàn bộ các phần tử do resize**.

Tuy nhiên:

- Mỗi `push` thường cần **cấp phát một nút** mới.
- Mỗi nút chứa cả giá trị và **ít nhất một tham chiếu** tới nút kế tiếp, cộng metadata/cấp phát tùy ngôn ngữ.
- Các nút có thể nằm rải rác trong bộ nhớ; duyệt thường kém tính cục bộ cache hơn mảng.
- **Không có giới hạn dung lượng cố định** chỉ có nghĩa là không đặt trần trước; `push` vẫn có thể thất bại khi hết bộ nhớ.
- Giải phóng nút/thu gom rác có thể tạo chi phí thời gian thực tế, đặc biệt nếu yêu cầu độ trễ nghiêm ngặt.

Vì vậy, `O(1)` theo số bước thuật toán **không** đồng nghĩa mọi `push` liên kết có thời gian thực tế cố định, bất kể cấp phát và hệ thống bộ nhớ.

## 6. Biến thể: deque hoặc stack bất biến

### Deque dùng làm stack

**Deque** (*double-ended queue*) hỗ trợ thêm và xóa ở **hai đầu**. Nếu ta chỉ dùng một đầu cho `push` và `pop`, nó đáp ứng giao diện stack.

```python
from collections import deque

stack = deque()
stack.append("A")
stack.append("B")

assert stack[-1] == "B"
assert stack.pop() == "B"
assert stack.pop() == "A"
```

Trong Python, `collections.deque` được tối ưu cho `append`/`pop` ở **hai đầu** với chi phí `O(1)` theo giao diện tài liệu, trong khi `list` thuận tiện khi chỉ thao tác cuối. Deque không nhất thiết là một mảng liên tục duy nhất và có cấu trúc khối nội bộ, nên mức sử dụng bộ nhớ, hiệu ứng cache và tốc độ thực tế khác `list`.

Trong Java, `ArrayDeque` thường là lựa chọn phổ biến để cài một stack mutable hơn kiểu `Stack` cũ; ví dụ `push`, `pop`, `peek` hỗ trợ trực tiếp. `ArrayDeque` **không cho phép phần tử `null`** và **không tự đồng bộ cho nhiều luồng**; những yêu cầu đó cần lựa chọn API khác.

### Stack bất biến để chia sẻ trạng thái

Với một **stack bất biến (persistent stack)** dựa trên nút liên kết, ta có thể tạo phiên bản mới mà **không sửa phiên bản cũ**:

```text
old_top ──→ [B] → [A] → None
new_top ──→ [C] ─┘

Phiên bản mới lưu C → B → A.
Phiên bản cũ vẫn lưu B → A.
```

Bằng cách tạo nút mới cho đỉnh và cho nó trỏ tới chuỗi nút cũ, thao tác `push` tạo một phiên bản mới chỉ cần **`O(1)` nút bổ sung**, không cần sao chép mọi phần tử cũ. `pop` trên phiên bản mới có thể trả về phần đuôi cũ mà không sửa nút nào. Những phiên bản còn được giữ tham chiếu sẽ chia sẻ các đuôi chung; tổng bộ nhớ phụ thuộc số nút còn sống và cách quản lý phiên bản, **không chỉ độ sâu của phiên bản hiện tại**.

Cấu trúc bất biến hợp với **Undo, backtracking và xử lý theo phiên bản**. Đổi lại, không nên nhầm nó với stack mutable sử dụng ít cấp phát: mỗi lần tạo phiên bản đỉnh mới vẫn có thể cấp phát một nút.

## 7. Bảng so sánh độ phức tạp

Gọi `n` là số phần tử đang lưu và `C` là dung lượng mảng cố định. Bảng xét các cách cài đặt phổ biến, với thao tác trên một ô mảng/tham chiếu/nút và phép xử lý dữ liệu phần tử có chi phí cơ bản hằng số.

| Biểu diễn | `push` | `pop` | `peek` | `size` | Bộ nhớ lưu trữ |
| --- | --- | --- | --- | --- | --- |
| **Mảng cố định** | `O(1)` nếu chưa đầy | `O(1)` | `O(1)` | `O(1)` | `O(C)` ô, cấp trước |
| **Mảng động** | `O(1)` khấu hao; lần resize `O(n)` | `O(1)` thường/khấu hao; lần co có thể `O(n)` | `O(1)` | `O(1)` | `O(n)` với chiến lược quản lý dung lượng theo hệ số |
| **Danh sách liên kết, top = head** | `O(1)` bước liên kết | `O(1)` bước liên kết | `O(1)` | `O(1)` nếu lưu biến đếm | `O(n)` nút |
| **Deque** | `O(1)` ở đầu được hỗ trợ, theo hợp đồng hiện thực | `O(1)` tương ứng | `O(1)` ở đầu | `O(1)` thường gặp | `O(n)` trong hiện thực phù hợp |
| **Stack bất biến liên kết** | `O(1)` tạo đỉnh phiên bản mới | `O(1)` lấy phần đuôi | `O(1)` | `O(1)` nếu lưu kích thước | `O(1)` nút mới mỗi `push`; tổng phụ thuộc phiên bản còn giữ |

**Quan trọng:** từ “`O(1)`” trong từng dòng có **ý nghĩa khác nhau**. Với mảng cố định, thao tác hợp lệ không cần resize. Với mảng động, `push` thường chỉ `O(1)` **khấu hao**. Với danh sách liên kết, số lần thay liên kết là hằng số nhưng có thể phát sinh cấp phát nút. Để thiết kế hệ thống nhạy với độ trễ, phải phân biệt **trung bình, khấu hao, tệ nhất và chi phí cấp phát thực tế**.

### Chi phí khởi tạo và bộ nhớ dự phòng

| Câu hỏi | Mảng cố định | Mảng động | Danh sách liên kết |
| --- | --- | --- | --- |
| Chi phí khởi tạo | `O(C)` nếu điền/khởi tạo `C` ô | Thường `O(1)` khi rỗng | `O(1)` |
| Phần bộ nhớ chưa dùng | Có thể có `C - n` ô | Có thể có `capacity - n` ô | Thường không giữ các ô dự phòng dạng mảng |
| Chi phí mỗi mục | Ô dữ liệu/tham chiếu | Ô dữ liệu/tham chiếu | Dữ liệu/tham chiếu và liên kết nút |
| Khi tăng bất ngờ | Overflow nếu đầy | Có thể resize và sao chép | Có thể cấp phát nút mới |
| Tính cục bộ cache | Tốt khi ô nằm liên tục | Thường tốt với mảng các tham chiếu | Thường kém hơn do nút rời rạc |

Cấp trước `C` ô có thể là chi phí đáng kể ngay khi stack còn rỗng. Ngược lại, bộ nhớ `O(n)` của danh sách liên kết có thể có **hệ số lớn** do mỗi nút là một đối tượng riêng. Không nên chọn chỉ dựa trên ký hiệu `O(n)` và `O(C)` mà bỏ qua dung lượng thực tế, overhead và cách cấp phát.

## 8. Nhìn sâu hơn vào chi phí bộ nhớ

Một stack lưu `n` **tham chiếu** đến đối tượng có thể khác stack lưu `n` giá trị nguyên thủy trực tiếp trong mảng typed, dù cả hai đều là “mảng”.

### Mảng cố định

Nếu mỗi ô có kích thước `w` byte và cần `C` ô, phần vùng dữ liệu chính vào khoảng `C × w` byte, ngoài metadata. Tại một thời điểm chỉ có `n` ô đang chứa mục logic, nên `C - n` ô dự phòng có thể gây lãng phí.

### Mảng động

Nếu có `capacity` ô, tổng vùng ô phụ thuộc **dung lượng đã cấp**, không chỉ số phần tử hiện tại. Chính sách tăng theo hệ số giúp `capacity` ở cùng bậc `O(n)` khi `n > 0` và mảng được quản lý phù hợp, đổi lấy những lần resize hiếm nhưng tốn kém. Với Python `list`, từng ô là **tham chiếu**; bộ nhớ các đối tượng mà chúng trỏ tới còn phải tính riêng.

### Danh sách liên kết

Mỗi nút cần vùng lưu giá trị hoặc tham chiếu, trường `next` và metadata cấp phát. Với `n` nút, tổng chi phí vẫn `O(n)`, nhưng có thể lớn hơn mảng tương đương. Khi stack rỗng, bản thân đối tượng quản lý stack thường chỉ cần một con trỏ `head` và có thể thêm biến `size`.

**Kết luận:** nói “linked list tiết kiệm bộ nhớ hơn mảng vì không dự phòng” chỉ có thể đúng trong những điều kiện rất cụ thể. Nhiều trường hợp bộ nhớ con trỏ/cấp phát của danh sách liên kết còn **đắt hơn phần dự phòng** của mảng động.

## 9. Chọn biểu diễn theo yêu cầu bài toán

Một cách chọn thực tế:

| Tình huống | Lựa chọn thường phù hợp | Vì sao |
| --- | --- | --- |
| Cần stack thông dụng trong Python, chỉ đẩy/lấy cuối | **`list`** | Đơn giản, `append`/`pop` cuối hiệu quả, ít mã |
| Cần thao tác cả hai đầu trong Python | **`deque`** | `O(1)` ở hai đầu theo hợp đồng |
| Có **giới hạn tối đa** đã biết và cần từ chối khi đầy | **Mảng cố định** hoặc vùng nhớ cấp trước có giới hạn | Giới hạn rõ, tránh resize ngoài ý muốn |
| Kích thước tăng giảm rất linh hoạt, ít quan tâm thứ tự vật lý | **Mảng động** | Tự quản lý dung lượng, phù hợp thao tác cuối |
| Cần tạo/xóa đỉnh bằng liên kết, cấu trúc dựa trên nút sẵn có | **Danh sách liên kết, top = head** | Không cần dời phần tử hay resize |
| Muốn giữ nhiều trạng thái stack cũ để Undo | **Stack bất biến/persistent** | Chia sẻ đuôi giữa các phiên bản |
| Đường xử lý yêu cầu độ trễ rất chặt | **Cân nhắc dung lượng cố định/vùng nhớ cấp trước** | Tránh lần resize và giảm cấp phát động; vẫn phải phân tích môi trường |
| Cần chia sẻ stack giữa nhiều luồng | **Chọn cấu trúc/giao thức đồng bộ phù hợp** | Một `list` hoặc `deque` thông thường không tự tạo hợp đồng thread-safe toàn bộ chuỗi thao tác |

Không phải mọi **DFS** đều cần dùng một lớp stack tự viết: trong Python có thể dùng trực tiếp `list`; ngăn xếp **lời gọi hàm** cũng có tính LIFO, nhưng chịu giới hạn độ sâu đệ quy và chi phí frame riêng. Nếu duyệt đồ thị rất sâu, DFS lặp với stack tường minh có thể giúp tránh giới hạn đệ quy của môi trường.

### Ví dụ 1: kiểm tra dấu ngoặc

Một biểu thức có tối đa vài nghìn dấu ngoặc lồng nhau, số lượng thay đổi theo đầu vào. Stack bằng `list` thường là lựa chọn đơn giản:

```python
def balanced_brackets(text: str) -> bool:
    opening = "([{"
    closing_to_opening = {")": "(", "]": "[", "}": "{"}
    stack = []

    for ch in text:
        if ch in opening:
            stack.append(ch)
        elif ch in closing_to_opening:
            if not stack or stack.pop() != closing_to_opening[ch]:
                return False

    return not stack


assert balanced_brackets("{[()]}") is True
assert balanced_brackets("([)]") is False
assert balanced_brackets("(((") is False
```

Với `m` ký tự đầu vào và `d` độ sâu lồng nhau cực đại, thuật toán tốn `O(m)` thời gian trung bình/khấu hao theo mô hình list stack và `O(d)` bộ nhớ phụ. Độ phức tạp không tự thay đổi chỉ vì chuyển từ mảng động sang danh sách liên kết, nhưng hệ số thời gian/bộ nhớ có thể khác.

### Ví dụ 2: Undo

Nếu chỉ cần hoàn tác thao tác mới nhất và không cần giữ nhiều nhánh lịch sử, một stack mutable có thể phù hợp:

```python
undo_stack = []

undo_stack.append(("set_title", "Tiêu đề cũ"))
undo_stack.append(("set_color", "blue"))

last_action = undo_stack.pop()
assert last_action == ("set_color", "blue")
```

Nếu phải giữ **nhiều nhánh lịch sử** trong cùng lúc (chẳng hạn sau Undo lại thực hiện thao tác mới nhưng vẫn giữ nhánh cũ), một stack bất biến với các phiên bản chia sẻ nút có thể là lựa chọn đáng cân nhắc. Cần thiết kế thêm cách quản lý các phiên bản và nội dung thao tác, không chỉ chọn cấu trúc stack.

### Ví dụ 3: công việc có giới hạn dung lượng

Một hệ thống xử lý tín hiệu nhúng có thể biết chắc số khung xử lý lồng nhau không vượt quá `C`. Khi đó, mảng cấp trước với hành vi overflow xác định có thể thuận lợi hơn việc cấp phát lại trong luồng xử lý. Tuy nhiên, nếu đỉnh thực tế vượt trần, chương trình phải **xử lý lỗi rõ ràng**; không được ghi vượt ranh giới mảng.

## 10. Các trường hợp biên và lỗi thường gặp

1. **`pop()` khi rỗng.** Phải báo underflow theo hợp đồng; không trả một ô dữ liệu không hợp lệ.
2. **`push()` khi đầy trên mảng cố định.** Phải báo overflow hoặc dùng chính sách rõ; không ghi vượt `C`.
3. **Đặt đỉnh ở đầu `list` rồi gọi `pop(0)`.** Dịch phần tử gây `O(n)`, làm mất ưu điểm thao tác cuối.
4. **Đặt đỉnh ở đuôi danh sách liên kết đơn** nhưng không có cách tới nút trước. `pop` có thể thành `O(n)`.
5. **Đánh đồng `O(1)` khấu hao với `O(1)` tệ nhất.** Một lần mở rộng mảng động có thể mất `O(n)`.
6. **Giả định linked stack không phát sinh chi phí cấp phát.** Mỗi `push` thường tạo nút mới, và `pop` liên quan đến giải phóng/thu gom rác.
7. **Không xóa tham chiếu khỏi ô mảng sau `pop`.** Có thể giữ đối tượng trong bộ nhớ lâu hơn cần thiết.
8. **Cho rằng `None` đồng nghĩa stack rỗng.** Nếu `None` là phần tử hợp lệ, phải dùng biến kích thước hoặc tín hiệu riêng để xác định rỗng.
9. **Nhầm stack với queue.** Stack lấy phần tử vào sau ra trước; queue lấy theo FIFO.
10. **Đánh giá bộ nhớ chỉ bằng số phần tử.** Mảng có ô dự phòng; danh sách liên kết có con trỏ/metadata; stack persistent còn giữ các nút thuộc phiên bản cũ.
11. **Bỏ qua chính sách đồng thời.** Hai luồng kiểm tra `not empty` rồi cùng `pop` có thể gặp tình huống đua; cần cơ chế đồng bộ đúng với môi trường.
12. **Sử dụng stack của đệ quy mà không xét độ sâu lời gọi.** Một số môi trường có giới hạn stack lời gọi, nên độ sâu lớn có thể dẫn tới lỗi hoặc tràn ngăn xếp lời gọi.
13. **Đo thời gian bằng một lần chạy quá ngắn rồi suy ra kết luận chung.** Khác biệt có thể do interpreter, allocator, GC, cache và phân phối kích thước stack.

## 11. Kiểm thử bất biến và hành vi tương đương

Một hiện thực khác nhau vẫn phải cho **cùng chuỗi kết quả** khi nhận cùng chuỗi thao tác hợp lệ. Có thể dùng một bộ kiểm thử mang tính mô hình để đối chiếu các stack:

```python
def check_stack_contract(make_stack):
    s = make_stack()
    assert s.is_empty()
    assert s.size() == 0

    s.push("A")
    s.push(None)
    s.push("C")

    assert s.size() == 3
    assert s.peek() == "C"
    assert s.size() == 3     # peek không xóa

    assert s.pop() == "C"
    assert s.pop() is None
    assert s.pop() == "A"
    assert s.is_empty()

    try:
        s.pop()
    except IndexError:
        pass
    else:
        raise AssertionError("pop rỗng phải phát sinh IndexError")


# Sau khi định nghĩa các lớp ở phần trên:
check_stack_contract(lambda: FixedArrayStack(3))
check_stack_contract(DynamicArrayStack)
check_stack_contract(LinkedStack)
```

Các lỗi thường lộ ra trong kiểm thử:

- Duy trì biến `size` không khớp số phần tử.
- `peek` vô tình lấy mất phần tử.
- Sai vị trí đỉnh dẫn đến FIFO thay vì LIFO.
- `pop` chưa giải phóng tham chiếu hoặc chưa nối lại `head`.
- Mảng cố định không chặn overflow ở biên.

### Kiểm thử giới hạn dung lượng

```python
fixed = FixedArrayStack(1)
fixed.push("A")

try:
    fixed.push("B")
except OverflowError:
    pass
else:
    raise AssertionError("push vượt dung lượng phải lỗi")

assert fixed.size() == 1
assert fixed.peek() == "A"
```

Đây là các kiểm thử được **trình bày để người học chạy thử**, không đồng nghĩa với việc mọi chi phí thực tế đã được benchmark hoặc mọi biến thể đã qua kiểm chứng. Đối với hệ thống sản xuất, cần bổ sung kiểm thử chịu tải, đầu vào lớn và chính sách lỗi, đồng thời đo độ trễ từng thao tác.

## 12. Nếu cần benchmark, nên đo điều gì?

Một phép đo hữu ích phải trả lời câu hỏi về **công việc thực tế**, không chỉ chạy vài lệnh rồi so một số thời gian.

- Đo riêng **chuỗi push**, **chuỗi pop**, và **mẫu xen kẽ push/pop**. Chuỗi chỉ push có thể kích hoạt nhiều lần mở rộng mảng; mẫu xen kẽ kiểm tra cấp phát/thu hồi.
- Chọn kích thước nhỏ, vừa, lớn; có cả độ sâu ổn định và trường hợp gần đỉnh cao nhất.
- Quan sát **độ trễ từng thao tác**, nhất là các ngưỡng resize, bên cạnh thời gian tổng; một giá trị trung bình có thể che một lần chậm.
- Đo **bộ nhớ đỉnh**, không chỉ kích thước logic `n`; cần phân biệt ô dự phòng, đối tượng nút và bộ nhớ các phần tử được tham chiếu.
- Lặp lại trên cùng môi trường, kiểm soát thao tác khởi tạo và chi phí cấp phát dữ liệu ngoài stack; không giả định rằng kết quả ở một ngôn ngữ/phiên bản chuyển sang ngôn ngữ khác.

Những kết quả đo thực nghiệm là **bằng chứng phụ thuộc môi trường**. Phân tích Big-O vẫn cần để hiểu hành vi theo quy mô, còn benchmark giúp kiểm chứng hệ số thực tế và các ngưỡng đáng quan tâm.

## 13. Tự luyện tập

**Bài 1.** Một stack mảng cố định có `C = 8`, `size = 5`. Có thể thêm tối đa bao nhiêu phần tử mà không gây overflow? Chỉ số đỉnh hiện tại là bao nhiêu nếu đánh chỉ số từ 0?

**Bài 2.** Giải thích tại sao `list.append(x)` thường có chi phí `O(1)` khấu hao nhưng đôi khi có thể tốn `O(n)`.

**Bài 3.** Một linked stack dùng danh sách liên kết đơn và đặt đỉnh ở **đuôi**. Vì sao `pop()` có thể tốn `O(n)`? Cách sửa đơn giản nhất là gì?

**Bài 4.** So sánh chi phí bộ nhớ khi lưu `n = 1000` phần tử trên mảng cố định dung lượng `C = 100000` với linked stack. Có thể khẳng định linked stack luôn dùng ít byte hơn không?

**Bài 5.** Trong một stack cho phép `None`, tại sao trả `None` khi `pop` từ stack rỗng có thể gây nhập nhằng? Nêu một hợp đồng API thay thế.

**Bài 6.** Nếu ứng dụng yêu cầu **mọi push hợp lệ** không thực hiện sao chép `n` phần tử do mở rộng dung lượng, nên tránh loại hiện thực nào? Nêu đánh đổi của những lựa chọn thay thế.

**Bài 7.** Dùng `list` trong Python, hãy mô tả thao tác `push`, `peek`, `pop`. Tại sao `pop(0)` không nên dùng trong biểu diễn đỉnh ở cuối?

**Bài 8.** Một công cụ hỗ trợ Undo và giữ lại hai nhánh lịch sử sau khi người dùng hoàn tác rồi thực hiện thao tác mới. Tại sao stack bất biến có thể phù hợp hơn một stack mutable duy nhất?

**Bài 9.** Viết hàm lấy tất cả phần tử khỏi stack thành list kết quả. Nếu đã `push(1), push(2), push(3)`, list kết quả phải như thế nào? Độ phức tạp theo `n` là bao nhiêu nếu mỗi `pop` `O(1)`?

**Bài 10.** Với mảng động kích thước `n`, so sánh thao tác `pop()` ở cuối và `pop(0)` ở đầu về thời gian. Vì sao kết quả có sự khác biệt?

<details>
<summary>Đáp án và gợi ý</summary>

1. Còn `8 - 5 = 3` ô; chỉ số đỉnh hiện tại là `5 - 1 = 4`.
2. Khi còn ô dự phòng, chỉ cần ghi ô cuối; khi đầy, có thể phải cấp vùng lớn hơn và chuyển `n` phần tử. Nếu dung lượng tăng theo hệ số, tổng chi phí resize trên nhiều lần chèn là tuyến tính, nên trung bình khấu hao `O(1)`.
3. Không có liên kết ngược tới nút trước đuôi, phải duyệt để tìm. Đặt đỉnh ở `head` để thêm/xóa chỉ đổi một số tham chiếu `O(1)`.
4. Mảng cố định giữ `100000` ô ngay cả khi chỉ dùng `1000`; linked stack giữ khoảng `1000` nút. Tuy nhiên, mỗi nút có overhead tham chiếu/metadata; không thể so byte chính xác nếu chưa biết biểu diễn và môi trường.
5. Vì `None` có thể là dữ liệu đỉnh hợp lệ. Có thể phát sinh `IndexError` khi rỗng hoặc trả `(found, value)` với `found = False`.
6. Tránh mảng động mở rộng bằng sao chép trong đường xử lý nhạy độ trễ. Mảng cố định tránh resize nhưng giới hạn dung lượng; linked stack không sao chép cả vùng nhưng vẫn cấp phát nút và có độ trễ allocator.
7. `append(x)`, `s[-1]`, `s.pop()` với kiểm tra rỗng khi cần. `pop(0)` dịch các phần tử còn lại, `O(n)`.
8. Stack bất biến có thể giữ đồng thời nhiều đỉnh phiên bản cùng chia sẻ phần đuôi; phiên bản cũ không bị `pop/push` trên nhánh mới làm mất.
9. Lần lượt `pop` và `append` giá trị vào list kết quả: `[3, 2, 1]`. Với `n` lần `pop` và `append` khấu hao hằng số, tổng `O(n)`; bộ nhớ list kết quả `O(n)`.
10. `pop()` cuối thường `O(1)` (ngoại trừ chi phí co bộ đệm); `pop(0)` cần dịch khoảng `n - 1` phần tử, `O(n)`.

</details>

## Ghi nhớ

**Stack ADT chỉ quy định LIFO, không bắt buộc một cách biểu diễn.** Mảng cố định cho thao tác đỉnh `O(1)` trong giới hạn `C` nhưng phải cấp trước `O(C)` ô. Mảng động có thao tác cuối **`O(1)` khấu hao** và linh hoạt, đổi lấy những lần resize `O(n)`. Danh sách liên kết đặt đỉnh ở đầu cho `O(1)` bước liên kết nhưng có chi phí cấp phát nút và bộ nhớ tham chiếu. Deque và stack bất biến đáp ứng các yêu cầu chuyên biệt. Chọn cấu trúc dựa trên **độ sâu dự kiến, giới hạn dung lượng, yêu cầu độ trễ, bộ nhớ, tính cục bộ cache và nhu cầu giữ phiên bản**, không chỉ dựa trên một cột Big-O.
