# Hàng đợi hai đầu (deque) và bốn phép thêm–lấy ở hai phía

**Deque** (đọc gần như “deck”, viết tắt của *double-ended queue*) là **kiểu dữ liệu trừu tượng cho phép thêm và lấy phần tử ở cả đầu lẫn cuối**. Khác với hàng đợi FIFO thuần túy chỉ thêm ở cuối, lấy ở đầu, deque hỗ trợ bốn thao tác cơ bản: **`push_front`, `push_back`, `pop_front` và `pop_back`**. Nhờ đó, cùng một cấu trúc có thể đóng vai trò hàng đợi, ngăn xếp, hoặc hỗ trợ những thuật toán cần thao tác đồng thời tại hai phía.

Bài thuộc chương **Hàng đợi và deque** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Trong lộ trình xây dựng nền tảng cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, ta cần hiểu **hợp đồng thao tác**, **bất biến thứ tự**, độ phức tạp **thời gian/bộ nhớ** và cách chọn biểu diễn phù hợp. Bài này tập trung vào bốn phép thêm–lấy, cài đặt deque bằng **mảng vòng** hoặc **danh sách liên kết đôi**, cùng ví dụ thực tế sử dụng deque trong Python.

## 1. Hợp đồng trừu tượng của deque

Giả sử deque chứa dãy phần tử từ trái sang phải:

```text
                  Thứ tự logic của deque

       FRONT                                      BACK
         |                                          |
         v                                          v
        [ A ] <──> [ B ] <──> [ C ] <──> [ D ]
         ↑                                          ↑
  thêm/lấy phía đầu                         thêm/lấy phía cuối
```

Trong tài liệu này, **front/left** là **đầu**, **back/right** là **cuối**. Đây là quy ước cố định cho toàn bài.

| Phép toán | Tên thường gặp | Hành vi với deque ban đầu `[A, B, C]` |
|---|---|---|
| **`push_front(X)`** | `add_first`, `appendleft` | Thêm `X` trước `A` → `[X, A, B, C]` |
| **`push_back(X)`** | `add_last`, `append` | Thêm `X` sau `C` → `[A, B, C, X]` |
| **`pop_front()`** | `remove_first`, `popleft` | Trả `A`, còn `[B, C]` |
| **`pop_back()`** | `remove_last`, `pop` | Trả `C`, còn `[A, B]` |

Hai phép `peek_front()` và `peek_back()` chỉ xem giá trị ở đầu/cuối mà **không xóa phần tử**. Các phép `is_empty()` và `size()` cho biết trạng thái và số phần tử. Nếu có giới hạn sức chứa, cần thêm `is_full()`.

### Mô hình hóa bằng dãy

Gọi trạng thái logic là `D = [d₀, d₁, …, dₙ₋₁]`. Khi đó:

- `push_front(x)`: `D ← [x, d₀, d₁, …, dₙ₋₁]`.
- `push_back(x)`: `D ← [d₀, d₁, …, dₙ₋₁, x]`.
- `pop_front()` khi `n > 0`: trả `d₀`, còn lại `[d₁, …, dₙ₋₁]`.
- `pop_back()` khi `n > 0`: trả `dₙ₋₁`, còn lại `[d₀, …, dₙ₋₂]`.

**Bất biến ngữ nghĩa:** các phần tử không bị xóa giữ **nguyên thứ tự tương đối** của chúng, bất kể thêm hoặc lấy tại phía nào. Ví dụ, từ `[A, B, C]`, `push_front(X)` tạo `[X, A, B, C]`: thứ tự `A → B → C` không bị đảo.

Deque **không buộc luôn FIFO** khi sử dụng cả bốn phép. Nếu chỉ `push_back` và `pop_front`, deque hoạt động như một queue FIFO; nếu chỉ `push_back` và `pop_back`, nó hoạt động như stack LIFO.

## 2. Truy vết bốn thao tác và ý nghĩa từng phía

Bắt đầu từ deque rỗng. Mỗi trạng thái trong bảng được viết từ **front → back**:

| Bước | Thao tác | Giá trị trả về | Trạng thái sau thao tác |
|---:|---|---|---|
| 0 | Khởi tạo | — | `[]` |
| 1 | `push_back("A")` | — | `[A]` |
| 2 | `push_back("B")` | — | `[A, B]` |
| 3 | `push_front("X")` | — | `[X, A, B]` |
| 4 | `push_back("C")` | — | `[X, A, B, C]` |
| 5 | `pop_front()` | `X` | `[A, B, C]` |
| 6 | `pop_back()` | `C` | `[A, B]` |
| 7 | `push_front("Y")` | — | `[Y, A, B]` |
| 8 | `pop_back()` | `B` | `[Y, A]` |
| 9 | `peek_front()` | `Y` | `[Y, A]` |
| 10 | `peek_back()` | `A` | `[Y, A]` |

Lưu ý rằng `pop_front` và `pop_back` đều **lấy và xóa** phần tử, nhưng ở hai phía khác nhau. Hai phép `peek` đều **không đổi độ dài** và không tác động đến thứ tự. Trạng thái sau bước 8 có đầu là `Y`, cuối là `A`.

### Những tình huống biên của deque

1. **Rỗng:** `pop_front`, `pop_back`, `peek_front` và `peek_back` không có phần tử hợp lệ; API phải báo lỗi hoặc trả kiểu kết quả biểu thị rỗng đã được công bố.
2. **Một phần tử:** cả `pop_front` và `pop_back` đều lấy **cùng phần tử đó**, rồi đưa deque về trạng thái rỗng.
3. **Hai phần tử trở lên:** lấy ở một phía không làm thay đổi vị trí tương đối của các phần tử còn lại.
4. **Giá trị trùng nhau:** hai lần thêm `A` vẫn là hai phần tử riêng biệt; số phần tử không được suy ra từ giá trị.
5. **Giá trị `None` hợp lệ:** nếu cho phép lưu `None`, không được dùng việc nhận giá trị `None` làm dấu hiệu chắc chắn hàng rỗng.
6. **Sức chứa cố định:** khi đầy, cả `push_front` và `push_back` phải tuân thủ chính sách riêng về từ chối, chờ hoặc ghi đè nếu API định nghĩa; lấy ở hai đầu vẫn thực hiện được.

## 3. Vì sao lựa chọn cách lưu trữ quan trọng?

Ta muốn **cả bốn phép đều có thời gian O(1)**. Cách lưu trữ dữ liệu quyết định có đạt mục tiêu này hay không.

Một danh sách dựa trên mảng giữ các phần tử từ chỉ số `0` có thể xử lý `push_back` và `pop_back` nhanh, nhưng thêm/xóa ở đầu bằng cách dịch các phần tử có chi phí **O(n)**. Danh sách liên kết đơn có `head` và `tail` xử lý thêm ở cả hai đầu và lấy ở đầu trong O(1), nhưng **`pop_back` thường là O(n)** vì cần tìm nút đứng trước `tail`.

Hai cách cài đặt phù hợp để thao tác hiệu quả ở **cả hai đầu** là:

- **Mảng vòng:** dùng chỉ số đầu và số phần tử, cho phép tiến/lùi chỉ số qua ranh giới mảng bằng phép modulo.
- **Danh sách liên kết đôi:** mỗi nút có `prev` và `next`, cho phép truy cập và gỡ nút ở cả đầu lẫn cuối thông qua `head` và `tail`.

| Biểu diễn | `push_front` | `push_back` | `pop_front` | `pop_back` |
|---|---:|---:|---:|---:|
| Mảng đặc, luôn dồn về đầu | O(n) | O(1) khấu hao nếu mảng động | O(n) | O(1) |
| Danh sách đơn có `head` và `tail` | O(1) | O(1) | O(1) | O(n) |
| **Mảng vòng, sức chứa cố định** | **O(1)** | **O(1)** | **O(1)** | **O(1)** |
| **Danh sách liên kết đôi có hai đầu** | **O(1)** | **O(1)** | **O(1)** | **O(1)** |

Bảng giả định biết sẵn `head`/`tail` và các thao tác truy cập ô hoặc tham chiếu là hằng số. Với mảng vòng **tự mở rộng**, hai phép thêm có thể tốn O(n) khi cấp phát/sao chép, nhưng thường đạt **O(1) khấu hao** khi tăng sức chứa theo hệ số; hai phép lấy vẫn là O(1).

## 4. Cài đặt deque bằng mảng vòng

Dùng một mảng vật lý có **sức chứa `C > 0`**, một chỉ số `head` và bộ đếm `size`:

- `head` chỉ tới **phần tử đầu logic**, nếu deque không rỗng.
- `size` là số phần tử, với `0 ≤ size ≤ C`.
- Phần tử logic thứ `j`, tính từ đầu, nằm tại `(head + j) % C`.
- Nếu `size > 0`, phần tử cuối ở `(head + size - 1) % C`.

Biểu diễn này cho phép thay đổi vị trí đầu bằng **lùi** hoặc **tiến** chỉ số một bước, không cần dịch toàn bộ mảng.

### Bốn công thức thao tác

**Thêm ở đầu (`push_front(x)`):**

```text
Nếu size == C: báo đầy
head = (head - 1 + C) % C
data[head] = x
size = size + 1
```

Khi `head = 0`, phép `(head - 1 + C) % C` cho `C - 1`, tức quay về ô vật lý cuối. Phần tử mới được đặt trước mọi phần tử logic đang có.

**Thêm ở cuối (`push_back(x)`):**

```text
Nếu size == C: báo đầy
index = (head + size) % C
data[index] = x
size = size + 1
```

Ô `(head + size) % C` nằm ngay sau phần tử cuối hiện tại. Nếu deque đang rỗng, thêm ở cuối ghi tại `head`.

**Lấy ở đầu (`pop_front()`):**

```text
Nếu size == 0: báo rỗng
result = data[head]
data[head] = EMPTY
head = (head + 1) % C
size = size - 1
return result
```

Chỉ số đầu tiến tới phần tử thứ hai cũ, nếu còn. Sau khi lấy phần tử duy nhất, `size = 0`; `head` vẫn có thể là bất kỳ chỉ số hợp lệ nào.

**Lấy ở cuối (`pop_back()`):**

```text
Nếu size == 0: báo rỗng
index = (head + size - 1) % C
result = data[index]
data[index] = EMPTY
size = size - 1
return result
```

Lấy cuối **không cần thay `head`**. Chỉ vị trí cuối logic bị bỏ và `size` giảm; phần tử đầu còn lại không đổi.

Trong giả mã, `EMPTY` nghĩa là dọn ô vật lý vừa lấy ra; không được dùng nội dung ô để suy ra trạng thái rỗng, vì dữ liệu hợp lệ có thể là `None`.

### Sơ đồ chỉ số khi thêm ở đầu

Giả sử `C = 5`, `head = 0`, deque chứa `[A, B]`:

```text
Chỉ số vật lý:   0     1     2     3     4
               +-----+-----+-----+-----+-----+
data:          |  A  |  B  |  ·  |  ·  |  ·  |
               +-----+-----+-----+-----+-----+
                 ↑
               head = 0, size = 2

push_front(X):
head = (0 - 1 + 5) % 5 = 4

Chỉ số vật lý:   0     1     2     3     4
               +-----+-----+-----+-----+-----+
data:          |  A  |  B  |  ·  |  ·  |  X  |
               +-----+-----+-----+-----+-----+
                                         ↑
                                      head = 4

Thứ tự logic: X → A → B
```

Mảng vật lý `[A, B, ·, ·, X]` trông không theo thứ tự, nhưng quy tắc đọc từ `head` theo vòng tạo đúng thứ tự deque. **Tăng/lùi chỉ số là thay đổi điểm bắt đầu**, không phải đảo mảng.

## 5. Truy vết bốn phép trong cùng một mảng vòng

Chọn sức chứa `C = 5` và ban đầu `head = 0`, `size = 0`. Dấu `·` biểu thị ô trống.

| Bước | Thao tác | Giá trị trả về | Mảng vật lý `[0,1,2,3,4]` | `head` | `size` | Thứ tự logic |
|---:|---|---|---|---:|---:|---|
| 0 | Khởi tạo | — | `[·, ·, ·, ·, ·]` | 0 | 0 | `[]` |
| 1 | `push_back(A)` | — | `[A, ·, ·, ·, ·]` | 0 | 1 | `[A]` |
| 2 | `push_back(B)` | — | `[A, B, ·, ·, ·]` | 0 | 2 | `[A, B]` |
| 3 | `push_front(X)` | — | `[A, B, ·, ·, X]` | 4 | 3 | `[X, A, B]` |
| 4 | `push_back(C)` | — | `[A, B, C, ·, X]` | 4 | 4 | `[X, A, B, C]` |
| 5 | `pop_front()` | `X` | `[A, B, C, ·, ·]` | 0 | 3 | `[A, B, C]` |
| 6 | `push_front(Y)` | — | `[A, B, C, ·, Y]` | 4 | 4 | `[Y, A, B, C]` |
| 7 | `pop_back()` | `C` | `[A, B, ·, ·, Y]` | 4 | 3 | `[Y, A, B]` |
| 8 | `push_back(D)` | — | `[A, B, D, ·, Y]` | 4 | 4 | `[Y, A, B, D]` |
| 9 | `push_back(E)` | — | `[A, B, D, E, Y]` | 4 | 5 | `[Y, A, B, D, E]` |

Sau bước 9, hàng **đầy** vì `size == C`. Vị trí vật lý của đầu là `4` (giá trị `Y`) và của cuối là `(4 + 5 - 1) % 5 = 3` (giá trị `E`). Hai thao tác `peek_front` và `peek_back` tương ứng trả `Y` và `E`.

Đây là trường hợp có ích để kiểm tra: **phần tử đầu và cuối nằm ở hai phía khác nhau của ranh giới mảng vật lý**, nhưng bốn phép vẫn phải giữ đúng thứ tự logic.

## 6. Cài đặt Python với sức chứa cố định

Ví dụ sau tạo deque bằng **mảng vòng** và đặt tên bốn phép giống hợp đồng đã nêu. Khi đầy, hai phép thêm ném `OverflowError`; khi rỗng, hai phép lấy và hai phép xem ném `IndexError`.

```python
class ArrayDeque:
    def __init__(self, capacity):
        if type(capacity) is not int or capacity <= 0:
            raise ValueError("capacity phải là số nguyên dương")
        self._data = [None] * capacity
        self._head = 0
        self._size = 0

    def __len__(self):
        return self._size

    def is_empty(self):
        return self._size == 0

    def is_full(self):
        return self._size == len(self._data)

    def push_front(self, value):
        if self.is_full():
            raise OverflowError("Deque đã đầy")
        cap = len(self._data)
        self._head = (self._head - 1 + cap) % cap
        self._data[self._head] = value
        self._size += 1

    def push_back(self, value):
        if self.is_full():
            raise OverflowError("Deque đã đầy")
        cap = len(self._data)
        index = (self._head + self._size) % cap
        self._data[index] = value
        self._size += 1

    def pop_front(self):
        if self.is_empty():
            raise IndexError("Không thể lấy đầu deque rỗng")
        value = self._data[self._head]
        self._data[self._head] = None
        self._head = (self._head + 1) % len(self._data)
        self._size -= 1
        return value

    def pop_back(self):
        if self.is_empty():
            raise IndexError("Không thể lấy cuối deque rỗng")
        index = (self._head + self._size - 1) % len(self._data)
        value = self._data[index]
        self._data[index] = None
        self._size -= 1
        return value

    def peek_front(self):
        if self.is_empty():
            raise IndexError("Deque rỗng")
        return self._data[self._head]

    def peek_back(self):
        if self.is_empty():
            raise IndexError("Deque rỗng")
        index = (self._head + self._size - 1) % len(self._data)
        return self._data[index]

    def to_list(self):
        cap = len(self._data)
        return [
            self._data[(self._head + j) % cap]
            for j in range(self._size)
        ]


d = ArrayDeque(5)
d.push_back("A")
d.push_back("B")
d.push_front("X")
d.push_back("C")

assert d.to_list() == ["X", "A", "B", "C"]
assert d.pop_front() == "X"
d.push_front("Y")
assert d.pop_back() == "C"

d.push_back("D")
d.push_back("E")
assert d.is_full()
assert d.peek_front() == "Y"
assert d.peek_back() == "E"
assert d.to_list() == ["Y", "A", "B", "D", "E"]

assert [d.pop_front() for _ in range(5)] == ["Y", "A", "B", "D", "E"]
assert d.is_empty()
```

Lớp trên dùng bộ đếm `_size` để **phân biệt đầy với rỗng**. Không thể chỉ dựa vào việc chỉ số đầu bằng chỉ số thêm tiếp, vì chúng có thể trùng nhau trong cả hai trạng thái.

### Kiểm tra tình huống một ô và giá trị đặc biệt

```python
single = ArrayDeque(1)
assert single.is_empty()

single.push_front(None)
assert single.is_full()
assert single.peek_front() is None
assert single.peek_back() is None
assert single.pop_back() is None
assert single.is_empty()

single.push_back("K")
assert single.pop_front() == "K"
assert single.is_empty()

try:
    single.pop_back()
except IndexError:
    pass
else:
    raise AssertionError("Phải báo lỗi khi pop_back trên deque rỗng")
```

Deque có sức chứa **1** là một kiểm tra đáng giá: đầu và cuối vật lý cùng là ô `0`. Sau khi lấy phần tử duy nhất bằng bất kỳ phép `pop` nào, `size` phải về `0`, và lần thêm tiếp theo phải vẫn hoạt động.

Dù `data` dùng `None` để dọn ô, phép `push_front(None)` hoàn toàn hợp lệ vì thông tin rỗng/đầy được xác định bằng `size`.

## 7. Cài đặt deque bằng danh sách liên kết đôi

Mảng vòng có lợi thế dùng vùng chứa liên tục. Một lựa chọn khác là **danh sách liên kết đôi** (*doubly linked list*): mỗi nút lưu `value`, tham chiếu `prev` về nút trước và `next` tới nút sau. Deque giữ cả `head` và `tail`:

```text
   head                                          tail
     |                                             |
     v                                             v
    [ A ] <────> [ B ] <────> [ C ] <────> [ D ]
  prev=None                                   next=None
```

Vì có liên kết theo **hai chiều**, ta có thể thêm và tháo nút ở cả hai đầu mà không cần duyệt tìm nút đứng trước `tail`.

### Bất biến danh sách đôi

- Rỗng khi và chỉ khi `head is None` **và** `tail is None`.
- Nếu không rỗng, `head.prev is None` và `tail.next is None`.
- Nếu chỉ có một nút, `head is tail`.
- Với mọi cặp nút kề nhau `a → b`, phải có `a.next is b` và `b.prev is a`.
- Dãy đi theo `next` từ `head` đến `tail` phải trùng thứ tự logic của deque.
- Nếu lưu `size`, số nút đếm được phải bằng `size`.

Đặc biệt, khi deque có **một nút**, lấy bằng `pop_front` hoặc `pop_back` đều phải đưa **cả hai con trỏ** về `None`.

### Cách sửa liên kết trong bốn thao tác

| Thao tác | Các liên kết chính cần cập nhật |
|---|---|
| `push_front(x)` | Đặt `new.next = head`, cho `head.prev = new` nếu có; chuyển `head = new`; nếu trước đó rỗng, đặt cả `tail = new` |
| `push_back(x)` | Đặt `new.prev = tail`, cho `tail.next = new` nếu có; chuyển `tail = new`; nếu trước đó rỗng, đặt cả `head = new` |
| `pop_front()` | Chuyển `head = head.next`; nếu còn nút, đặt `head.prev = None`, nếu hết nút, đặt `tail = None` |
| `pop_back()` | Chuyển `tail = tail.prev`; nếu còn nút, đặt `tail.next = None`, nếu hết nút, đặt `head = None` |

Mỗi thao tác liên kết chỉ cập nhật một số lượng cố định tham chiếu: **O(1)**, giả định cấp phát hoặc giải phóng nút có chi phí hằng số theo mô hình thuật toán.

### Cài đặt Python minh họa

```python
class _Node:
    def __init__(self, value):
        self.value = value
        self.prev = None
        self.next = None


class LinkedDeque:
    def __init__(self):
        self._head = None
        self._tail = None
        self._size = 0

    def __len__(self):
        return self._size

    def is_empty(self):
        return self._size == 0

    def push_front(self, value):
        node = _Node(value)
        node.next = self._head
        if self._head is None:
            self._tail = node
        else:
            self._head.prev = node
        self._head = node
        self._size += 1

    def push_back(self, value):
        node = _Node(value)
        node.prev = self._tail
        if self._tail is None:
            self._head = node
        else:
            self._tail.next = node
        self._tail = node
        self._size += 1

    def pop_front(self):
        if self._head is None:
            raise IndexError("Deque rỗng")
        node = self._head
        self._head = node.next
        if self._head is None:
            self._tail = None
        else:
            self._head.prev = None
        node.next = None
        self._size -= 1
        return node.value

    def pop_back(self):
        if self._tail is None:
            raise IndexError("Deque rỗng")
        node = self._tail
        self._tail = node.prev
        if self._tail is None:
            self._head = None
        else:
            self._tail.next = None
        node.prev = None
        self._size -= 1
        return node.value


d = LinkedDeque()
d.push_front("B")
d.push_front("A")
d.push_back("C")

assert d.pop_back() == "C"
assert d.pop_front() == "A"
assert d.pop_back() == "B"
assert d.is_empty()
assert d._head is None and d._tail is None

d.push_back("D")  # Thử thêm lại sau khi rỗng.
assert d.pop_front() == "D"
assert d.is_empty()
```

Danh sách liên kết đôi có thể tăng số nút theo nhu cầu mà không cần **sao chép cả mảng** khi thêm. Đổi lại, mỗi nút cần **hai tham chiếu liên kết** và cấp phát riêng. Việc truy cập phần tử nằm giữa cũng phải duyệt liên kết, thường **O(n)**, vì không có ánh xạ chỉ số vật lý như mảng.

## 8. So sánh chi phí thời gian và bộ nhớ

Gọi `n` là số phần tử đang có và `C` là sức chứa mảng đã cấp phát.

| Phép toán | Mảng vòng cố định | Mảng vòng tự mở rộng | Danh sách liên kết đôi |
|---|---:|---:|---:|
| `push_front` | O(1) | O(1) **khấu hao** | O(1) |
| `push_back` | O(1) | O(1) **khấu hao** | O(1) |
| `pop_front` | O(1) | O(1) | O(1) |
| `pop_back` | O(1) | O(1) | O(1) |
| `peek_front`, `peek_back` | O(1) | O(1) | O(1) |
| `size`, `is_empty` | O(1) | O(1) | O(1) nếu lưu bộ đếm |
| Duyệt hết `n` phần tử | O(n) | O(n) | O(n) |
| Bộ nhớ của cấu trúc | O(C) | O(C) | O(n) |

Mảng vòng cố định cho thời gian **O(1) trong trường hợp xấu nhất của các thao tác thành công**, theo mô hình truy cập ô và tính chỉ số hằng số. Nếu mảng tự mở rộng, một lần thêm khiến mảng đầy phải cấp phát và chép lại `n` phần tử, tốn O(n); khi tăng sức chứa theo hệ số, nhiều lần thêm có thể được phân tích **O(1) khấu hao**.

Danh sách liên kết đôi tiêu thụ nhiều bộ nhớ phụ cho các con trỏ liên kết; mảng vòng có thể cấp phát một số ô chưa dùng. Chọn phương án nào phụ thuộc vào sức chứa dự kiến, giới hạn RAM, độ trễ chấp nhận được và việc cần truy cập ngẫu nhiên hay không.

Nếu mục tiêu chỉ là một **queue FIFO**, danh sách liên kết đơn với `head` và `tail` đã đủ cho `enqueue`/`dequeue` O(1). Ta cần liên kết đôi hoặc mảng vòng khi muốn **lấy nhanh cả phía cuối**.

## 9. Sử dụng `collections.deque` trong Python

Python cung cấp `collections.deque` để thao tác hiệu quả ở cả hai phía. Tên API tương ứng với bốn phép của bài:

| Khái niệm trong bài | `collections.deque` |
|---|---|
| `push_front(x)` | `appendleft(x)` |
| `push_back(x)` | `append(x)` |
| `pop_front()` | `popleft()` |
| `pop_back()` | `pop()` |
| `peek_front()` | `d[0]` khi không rỗng |
| `peek_back()` | `d[-1]` khi không rỗng |

Ví dụ:

```python
from collections import deque

d = deque(["A", "B"])
d.appendleft("X")          # push_front
d.append("C")              # push_back

assert list(d) == ["X", "A", "B", "C"]
assert d.popleft() == "X"   # pop_front
assert d.pop() == "C"       # pop_back
assert list(d) == ["A", "B"]

assert d[0] == "A"          # peek_front
assert d[-1] == "B"         # peek_back

d.clear()
assert len(d) == 0
```

Với deque rỗng, `popleft()` và `pop()` ném `IndexError`. Truy cập phần tử đầu/cuối bằng `d[0]` hoặc `d[-1]` cũng chỉ hợp lệ khi có phần tử.

Theo tài liệu Python, các thao tác **append/pop ở hai đầu** có độ phức tạp xấp xỉ O(1). Tuy nhiên, đừng suy ra việc truy cập một **chỉ số ở giữa** deque cũng nhanh như mảng: truy cập giữa deque có thể tốn O(n). Nếu bài toán thường xuyên cần `d[i]` ở các vị trí bất kỳ, một danh sách dạng mảng có thể thích hợp hơn.

### Deque có `maxlen`: giới hạn và tự loại phần tử phía đối diện

Khác với `ArrayDeque` ở trên (báo lỗi khi đầy), `collections.deque(maxlen=C)` mặc định **tự loại phần tử ở phía đối diện** khi thêm vào deque đã đầy:

```python
from collections import deque

recent = deque(["A", "B", "C"], maxlen=3)

recent.append("D")          # Thêm phải, bỏ A ở trái.
assert list(recent) == ["B", "C", "D"]

recent.appendleft("X")      # Thêm trái, bỏ D ở phải.
assert list(recent) == ["X", "B", "C"]
```

Chính sách này phù hợp với bộ nhớ lịch sử giới hạn, nhưng có thể làm mất phần tử chưa được xử lý. Nếu cần **từ chối khi đầy** hoặc **chờ có chỗ**, phải chọn API hoặc lớp bọc có hợp đồng thích hợp. Ví dụ, `queue.Queue(maxsize=C)` cung cấp cơ chế phối hợp producer–consumer giữa các luồng; đó là một hợp đồng khác với `deque(maxlen=C)`.

## 10. Deque có thể dùng như queue hoặc stack

Deque mở rộng tập thao tác của queue:

```text
QUEUE FIFO:
    Thêm:  push_back(x)
    Lấy:   pop_front()
    Ví dụ: A đến, B đến → lấy A rồi B

STACK LIFO:
    Thêm:  push_back(x)
    Lấy:   pop_back()
    Ví dụ: A đến, B đến → lấy B rồi A

DEQUE HAI ĐẦU:
    Có thể thêm/lấy ở cả front và back tùy thuật toán
```

Cũng có thể thực hiện queue FIFO bằng `push_front` và `pop_back`, miễn toàn bộ chương trình dùng nhất quán hai phía đối diện. Tuy nhiên, trong đa số API, quy ước **thêm phải, lấy trái** dễ đọc hơn.

Một **priority queue** không thể được thay thế đơn giản bằng deque nếu cần lấy phần tử theo độ ưu tiên bất kỳ, vì deque chỉ cung cấp truy cập nhanh ở **hai đầu theo thứ tự hiện tại**. Priority queue thường dùng cấu trúc heap hoặc cơ chế sắp xếp khác.

## 11. Ứng dụng: tìm giá trị lớn nhất trong cửa sổ trượt

Deque có một ứng dụng thuật toán điển hình: tìm **giá trị lớn nhất trong mọi cửa sổ độ dài `k`** của dãy số, hiệu quả hơn cách quét lại từng cửa sổ.

Ví dụ, với dãy `[4, 2, 12, 3, 8, 7]` và `k = 3`, các cửa sổ và giá trị lớn nhất là:

| Cửa sổ | Phần tử | Lớn nhất |
|---:|---|---:|
| 0–2 | `[4, 2, 12]` | 12 |
| 1–3 | `[2, 12, 3]` | 12 |
| 2–4 | `[12, 3, 8]` | 12 |
| 3–5 | `[3, 8, 7]` | 8 |

Kỹ thuật **monotonic deque** lưu **chỉ số** phần tử theo thứ tự tăng dần của vị trí và **giá trị giảm dần** từ front đến back:

1. **`pop_front`** để bỏ những chỉ số đã ra khỏi cửa sổ.
2. **`pop_back`** để bỏ những chỉ số có giá trị không lớn hơn giá trị mới, vì chúng không còn cần thiết làm ứng viên cực đại.
3. **`push_back`** chỉ số mới.
4. Xem chỉ số ở `front` để lấy giá trị cực đại của cửa sổ hiện tại.

```python
from collections import deque

def sliding_max(nums, k):
    if k < 1 or k > len(nums):
        raise ValueError("k phải nằm trong khoảng 1..len(nums)")

    candidates = deque()  # Lưu chỉ số; giá trị giảm dần từ trái sang phải.
    result = []

    for i, value in enumerate(nums):
        # Bỏ chỉ số đã nằm ngoài cửa sổ [i-k+1, i].
        while candidates and candidates[0] <= i - k:
            candidates.popleft()

        # Giá trị cũ không lớn hơn value mới không còn là ứng viên tốt.
        while candidates and nums[candidates[-1]] <= value:
            candidates.pop()

        candidates.append(i)

        if i >= k - 1:
            result.append(nums[candidates[0]])

    return result


assert sliding_max([4, 2, 12, 3, 8, 7], 3) == [12, 12, 12, 8]
assert sliding_max([5, 5, 4], 1) == [5, 5, 4]
```

Điểm đặc biệt: một chỉ số được thêm **đúng một lần** và bị lấy ra **nhiều nhất một lần** (từ đầu khi hết hạn hoặc từ cuối khi bị ứng viên mới thay thế). Tổng số lần thao tác deque qua `n` phần tử là **O(n)**, nên toàn bộ thuật toán là **O(n) thời gian** và **O(k) bộ nhớ phụ** cho các chỉ số đang nằm trong cửa sổ.

Một deque làm được điều này vì thuật toán cần loại phần tử **quá cũ ở đầu** và loại phần tử **không còn hữu ích ở cuối**, đúng với hai nhóm thao tác mà deque hỗ trợ nhanh.

## 12. Một số lỗi cài đặt dễ gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Nhầm `push_front` với `push_back` | Phần tử mới nằm sai phía | Chốt quy ước front = trái, back = phải |
| Nhầm `pop_front` với `pop_back` | Trả giá trị không mong muốn | Truy vết dãy logic sau mỗi phép |
| Mảng vòng: `head - 1` không lấy modulo | Chỉ số âm hoặc ra ngoài mảng ở ngôn ngữ khác | Dùng `(head - 1 + C) % C` |
| Mảng vòng: pop_back từ `(head + size) % C` | Đọc ô sắp ghi, không phải phần tử cuối | Dùng `(head + size - 1) % C` |
| Mảng vòng: pop_back lại tăng `head` | Bỏ nhầm đầu logic | Giữ nguyên `head` khi chỉ lấy ở cuối |
| Lấy hết phần tử nhưng không giảm `size` | Trạng thái đầy/rỗng sai | Mỗi pop thành công giảm đúng 1 |
| Danh sách đôi: quên sửa `prev` hoặc `next` | Liên kết ngược/xuôi không nhất quán | Kiểm tra cả hai chiều sau thêm/lấy |
| Danh sách đôi: lấy nút duy nhất nhưng không xóa cả hai con trỏ | Head/tail trỏ tới nút không còn trong deque | Khi rỗng, đặt `head = tail = None` |
| Coi `None` là dấu hiệu không có phần tử | Không lưu được `None` hợp lệ | Dựa vào `size` hoặc con trỏ nút |
| Dùng `deque(maxlen=C)` mà tưởng sẽ báo đầy | Dữ liệu ở phía đối diện bị bỏ im lặng | Kiểm tra chính sách giới hạn theo API |
| Dùng `list.pop(0)` liên tục để giả lập deque | Xóa đầu mất O(n) | Dùng deque hoặc mảng vòng |
| Thao tác nhiều bước trên deque chia sẻ giữa các luồng mà thiếu đồng bộ | Có thể phát sinh kết quả không nhất quán | Chọn cấu trúc hoặc khóa đồng bộ thích hợp |

Khi tự viết một deque, nên kiểm tra cả **chỉ thêm/lấy một phía**, **xen kẽ hai phía**, **chỉ còn một phần tử**, **sức chứa 1** và **đầu quay vòng qua ranh giới mảng**. Đây là những tình huống dễ làm lộ lỗi tính chỉ số hoặc cập nhật hai con trỏ.

## 13. Bài tập tự luyện

**Bài 1 — Truy vết cơ bản.** Bắt đầu từ deque rỗng, thực hiện `push_back(1)`, `push_front(2)`, `push_back(3)`, `pop_back()`, `push_front(4)`. Giá trị được pop và dãy cuối là gì?

*Đáp án:* Trước khi pop là `[2, 1, 3]`, nên `pop_back()` trả **3**. Sau `push_front(4)`, deque là **`[4, 2, 1]`**.

**Bài 2 — Chỉ số quay vòng.** Mảng vòng có `C = 6`, `head = 0` và `size = 2`. Nếu `push_front(X)`, chỉ số `head` mới bằng bao nhiêu?

*Đáp án:* `(0 - 1 + 6) % 6 = 5`. Phần tử mới nằm ở ô vật lý 5 nhưng trở thành đầu logic.

**Bài 3 — Lấy ở cuối.** Mảng vòng có `C = 7`, `head = 5`, `size = 4`. `pop_back()` phải đọc tại chỉ số nào? `head` thay đổi không?

*Đáp án:* `(5 + 4 - 1) % 7 = 1`. Sau thao tác, `size = 3` và `head` **vẫn bằng 5**.

**Bài 4 — Danh sách liên kết đơn.** Vì sao một danh sách đơn có `head` và `tail` vẫn không hỗ trợ `pop_back()` O(1) trong thiết kế thông thường?

*Đáp án:* Muốn xóa nút cuối cần biết **nút ngay trước `tail`**. Danh sách đơn không có `prev` nên thường phải duyệt từ `head` đến nút áp chót, tốn O(n).

**Bài 5 — Python có giới hạn.** Với `d = deque(["A", "B"], maxlen=2)`, sau `d.appendleft("X")` deque chứa gì?

*Đáp án:* **`["X", "A"]`**. Phần tử cuối cũ `B` bị loại để nhường chỗ cho `X` ở đầu.

**Bài 6 — Chọn cấu trúc.** Cần lấy phần tử đến sớm nhất và đồng thời có thể hủy nhanh phần tử mới nhất ở cuối. Queue FIFO chỉ có `enqueue/dequeue` đã đủ chưa?

*Đáp án:* Queue FIFO thuần túy không cung cấp thao tác lấy cuối. **Deque** hỗ trợ `pop_front` lấy phần tử cũ nhất và `pop_back` lấy/hủy phần tử cuối trong O(1) với cài đặt phù hợp.

**Bài 7 — Tính đúng đắn.** Sau `push_back(A)`, `push_back(B)`, `push_front(C)`, nếu lấy hết bằng `pop_front` thì thứ tự trả về là gì? Nếu thay bằng `pop_back` thì sao?

*Đáp án:* Deque là `[C, A, B]`. Lấy hết bằng `pop_front` trả **C, A, B**; lấy hết bằng `pop_back` trả **B, A, C**.

**Ghi nhớ:** Deque định nghĩa **bốn phép thêm–lấy độc lập ở hai phía**. Với **mảng vòng**, việc lùi/tiến chỉ số `head` và tính vị trí cuối theo modulo giúp cả bốn phép chạy O(1) khi còn sức chứa. Với **danh sách liên kết đôi**, các tham chiếu `prev`/`next` giúp thêm và gỡ nút ở hai đầu trong O(1). Chọn deque khi bài toán thực sự cần điều khiển phần tử từ cả hai đầu, và luôn kiểm tra đúng hợp đồng rỗng/đầy, thứ tự logic cùng chi phí của kiểu cài đặt cụ thể.
