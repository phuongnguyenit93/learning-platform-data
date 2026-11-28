# Deque bằng mảng vòng hoặc các khối liên kết

**Deque** (*double-ended queue*, hàng đợi hai đầu) cho phép **thêm và lấy phần tử tại cả đầu lẫn cuối**. Để bốn phép chính `push_front`, `push_back`, `pop_front`, `pop_back` đều hiệu quả, ta cần một cách tổ chức bộ nhớ không buộc phải dịch toàn bộ phần tử mỗi khi đầu hàng thay đổi. Hai phương án đáng học là **mảng vòng** (*circular array*) và **chuỗi các khối liên kết** (*linked blocks / segmented deque*).

Bài thuộc chương **Hàng đợi và deque** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Trong nền tảng cấu trúc dữ liệu từ mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap đến đồ thị, mục tiêu không chỉ là viết được phép thêm–lấy, mà còn hiểu **bất biến cấu trúc**, **chi phí thời gian/bộ nhớ** và lý do chọn một biểu diễn phù hợp với tải thực tế. Trọng tâm bài này là đối chiếu cách **quay chỉ số trong một mảng** với cách **mở rộng dần bằng những khối lưu trữ nhỏ nối với nhau**.

## 1. Bốn phép toán và thứ tự logic của deque

Quy ước đầu (*front*, *left*) ở bên trái, cuối (*back*, *right*) ở bên phải:

```text
      front                                  back
        |                                     |
        v                                     v
      [ A ] <----> [ B ] <----> [ C ] <----> [ D ]
        ^                                     ^
   push_front(x)                         push_back(x)
   pop_front()                            pop_back()
```

Deque là một **kiểu dữ liệu trừu tượng** (*ADT*). Hợp đồng nêu thứ tự phần tử sau mỗi thao tác, chứ không yêu cầu phần tử phải nằm ở vị trí vật lý nào.

| Phép toán | Tác động lên deque `[A, B, C]` | Kết quả |
|---|---|---|
| `push_front(X)` | Chèn `X` vào đầu | `[X, A, B, C]` |
| `push_back(X)` | Chèn `X` vào cuối | `[A, B, C, X]` |
| `pop_front()` | Lấy và xóa phần tử đầu | Trả `A`, còn `[B, C]` |
| `pop_back()` | Lấy và xóa phần tử cuối | Trả `C`, còn `[A, B]` |
| `peek_front()` / `peek_back()` | Xem một đầu, không xóa | `A` / `C` |
| `size()` / `is_empty()` | Đọc thông tin trạng thái | Không đổi |

**Bất biến ngữ nghĩa:** mọi phần tử chưa bị xóa phải giữ nguyên thứ tự tương đối. Chẳng hạn, `push_front(X)` không thể khiến `B` vượt trước `A` trong dãy đang có. Cách lưu trữ phải bảo đảm bất biến này khi chỉ số quay vòng hoặc khi di chuyển sang khối mới.

Deque có thể mô phỏng **queue FIFO** bằng `push_back` + `pop_front`; hoặc **stack LIFO** bằng `push_back` + `pop_back`. Khi dùng cả bốn phép, deque linh hoạt hơn hai quy tắc riêng ấy.

## 2. Vì sao một mảng đặc hoặc danh sách đơn chưa đủ?

Giả sử biểu diễn dãy trực tiếp bằng các ô `data[0]` đến `data[n-1]` và luôn đặt phần tử đầu tại ô `0`. Với `push_front(X)`, để tạo chỗ, ta phải dời `n` phần tử sang phải; với `pop_front()`, thường phải dời `n - 1` phần tử sang trái. Mỗi lần như vậy tốn **O(n)** theo số phần tử.

Một **danh sách liên kết đơn** có `head` và `tail` có thể thêm ở hai đầu và lấy ở đầu trong O(1), nhưng lấy ở cuối thường phải tìm **nút trước `tail`**, tốn O(n). Danh sách liên kết đôi khắc phục bằng con trỏ `prev`; chuỗi các khối liên kết đưa ý tưởng liên kết hai chiều lên **cấp khối** thay vì mỗi phần tử.

Hai phương án trọng tâm:

1. **Mảng vòng:** có một mảng lớn và một chỉ số bắt đầu; tính vị trí mọi phần tử bằng phép modulo. Thao tác hai đầu chỉ sửa vài ô/chỉ số.
2. **Các khối liên kết:** dữ liệu nằm trong nhiều mảng con có kích thước giới hạn; mỗi khối liên kết với khối trước và sau. Chỉ các khối ở hai đầu nhận thao tác thêm/lấy thông thường.

Điểm chung của hai cách là **không dịch toàn bộ phần tử để lấy hoặc thêm ở đầu**.

## 3. Cách 1 — Deque bằng mảng vòng

### 3.1. Trạng thái và chỉ số

Một deque dạng mảng vòng có sức chứa `C > 0` lưu:

- `data`: mảng vật lý gồm `C` ô.
- `head`: chỉ số vật lý của phần tử đầu logic khi deque không rỗng.
- `size`: số phần tử hiện có, `0 ≤ size ≤ C`.

Phần tử logic thứ `j`, với `0 ≤ j < size`, nằm ở:

```text
physical(j) = (head + j) % C
```

Khi `size > 0`, phần tử cuối nằm ở `(head + size - 1) % C`. Vị trí chèn cuối khi còn chỗ là `(head + size) % C`.

**Rỗng** khi `size == 0`, **đầy** khi `size == C`. Theo quy ước này, ta không dùng giá trị chứa trong ô mảng hoặc một phép so sánh hai chỉ số để phân biệt rỗng/đầy.

### 3.2. Bốn thao tác bằng phép modulo

```text
PUSH_FRONT(x):
    if size == C: báo đầy
    head = (head - 1 + C) % C
    data[head] = x
    size += 1

PUSH_BACK(x):
    if size == C: báo đầy
    index = (head + size) % C
    data[index] = x
    size += 1

POP_FRONT():
    if size == 0: báo rỗng
    result = data[head]
    data[head] = EMPTY
    head = (head + 1) % C
    size -= 1
    return result

POP_BACK():
    if size == 0: báo rỗng
    index = (head + size - 1) % C
    result = data[index]
    data[index] = EMPTY
    size -= 1
    return result
```

Ở `push_front`, chỉ số `head` **lùi một ô** (từ `0` sẽ quay về `C - 1`), rồi đặt phần tử mới vào đó. Ở `pop_back`, `head` **không thay đổi** vì chỉ bỏ phần tử cuối. Khi deque trở lại rỗng, `head` vẫn có thể khác `0` và điều đó không gây lỗi: `size` mới là điều kiện rỗng.

Mỗi phép trên chỉ dùng một số lượng cố định phép toán trên ô và chỉ số, nên **O(1)** trong mô hình mảng vòng có sức chứa cố định, với điều kiện phép thêm không gặp trạng thái đầy.

### 3.3. Truy vết: chỉ số vật lý khác thứ tự logic

Dùng mảng `C = 4`. Dấu `·` chỉ ô không thuộc deque, còn dãy logic luôn viết từ đầu đến cuối:

| Bước | Thao tác | Giá trị trả về | Mảng vật lý `[0,1,2,3]` | `head` | `size` | Deque logic |
|---:|---|---|---|---:|---:|---|
| 0 | Khởi tạo | — | `[·, ·, ·, ·]` | 0 | 0 | `[]` |
| 1 | `push_back(A)` | — | `[A, ·, ·, ·]` | 0 | 1 | `[A]` |
| 2 | `push_back(B)` | — | `[A, B, ·, ·]` | 0 | 2 | `[A, B]` |
| 3 | `push_front(X)` | — | `[A, B, ·, X]` | 3 | 3 | `[X, A, B]` |
| 4 | `push_back(C)` | — | `[A, B, C, X]` | 3 | 4 | `[X, A, B, C]` |
| 5 | `pop_back()` | `C` | `[A, B, ·, X]` | 3 | 3 | `[X, A, B]` |
| 6 | `pop_front()` | `X` | `[A, B, ·, ·]` | 0 | 2 | `[A, B]` |
| 7 | `push_front(Y)` | — | `[A, B, ·, Y]` | 3 | 3 | `[Y, A, B]` |
| 8 | `push_back(D)` | — | `[A, B, D, Y]` | 3 | 4 | `[Y, A, B, D]` |

Tại bước 8, thứ tự đọc là `data[3]`, `data[0]`, `data[1]`, `data[2]`; nghĩa là `Y, A, B, D`. Nếu đọc thẳng mảng vật lý từ 0 tới 3, kết quả sẽ sai.

### 3.4. Khi mảng đầy: cố định hay tự mở rộng?

Một mảng vòng **sức chứa cố định** phải có chính sách khi đầy: từ chối, chờ hoặc ghi đè theo hợp đồng riêng. Nếu muốn deque tăng số phần tử không định trước, có thể **cấp phát mảng lớn hơn** rồi sao chép **theo thứ tự logic**:

```text
old_C = length(data)
new_data = new_array(2 * old_C)

for j from 0 to size - 1:
    new_data[j] = data[(head + j) % old_C]

data = new_data
head = 0
```

Sau khi sao chép, các phần tử đang có nằm trong đoạn `new_data[0:size]`. Lúc này có thể thêm phần tử ở **đầu** bằng cách lùi `head` từ 0 về ô cuối của mảng mới, hoặc thêm ở **cuối** vào ô `size`.

Một lần mở rộng có thể tốn **O(n)** thời gian và bộ nhớ cấp phát thêm tương ứng sức chứa mới, nhưng tăng dung lượng theo hệ số (ví dụ gấp đôi) cho phép hai phép thêm đạt **O(1) khấu hao** trên chuỗi thao tác dài. Hai phép lấy vẫn O(1) nếu không kết hợp chính sách thu nhỏ tốn sao chép.

## 4. Mã Python: deque mảng vòng tự mở rộng

Ví dụ sau dùng `head` và `size`, tự tăng sức chứa khi một trong hai phía cần thêm mà mảng đã đầy. Đây là deque **dùng tuần tự**, không tích hợp cơ chế khóa cho nhiều luồng.

```python
class RingDeque:
    def __init__(self, initial_capacity=2):
        if type(initial_capacity) is not int or initial_capacity <= 0:
            raise ValueError("initial_capacity phải là số nguyên dương")
        self._data = [None] * initial_capacity
        self._head = 0
        self._size = 0

    def __len__(self):
        return self._size

    @property
    def capacity(self):
        return len(self._data)

    def is_empty(self):
        return self._size == 0

    def _grow(self):
        old = self._data
        old_capacity = len(old)
        new_data = [None] * (2 * old_capacity)

        for j in range(self._size):
            new_data[j] = old[(self._head + j) % old_capacity]

        # Chỉ công bố trạng thái mới sau khi sao chép xong.
        self._data = new_data
        self._head = 0

    def push_front(self, value):
        if self._size == len(self._data):
            self._grow()
        capacity = len(self._data)
        self._head = (self._head - 1 + capacity) % capacity
        self._data[self._head] = value
        self._size += 1

    def push_back(self, value):
        if self._size == len(self._data):
            self._grow()
        capacity = len(self._data)
        index = (self._head + self._size) % capacity
        self._data[index] = value
        self._size += 1

    def pop_front(self):
        if self._size == 0:
            raise IndexError("Deque rỗng")
        value = self._data[self._head]
        self._data[self._head] = None
        self._head = (self._head + 1) % len(self._data)
        self._size -= 1
        return value

    def pop_back(self):
        if self._size == 0:
            raise IndexError("Deque rỗng")
        index = (self._head + self._size - 1) % len(self._data)
        value = self._data[index]
        self._data[index] = None
        self._size -= 1
        return value

    def peek_front(self):
        if self._size == 0:
            raise IndexError("Deque rỗng")
        return self._data[self._head]

    def peek_back(self):
        if self._size == 0:
            raise IndexError("Deque rỗng")
        index = (self._head + self._size - 1) % len(self._data)
        return self._data[index]

    def to_list(self):
        capacity = len(self._data)
        return [
            self._data[(self._head + j) % capacity]
            for j in range(self._size)
        ]


d = RingDeque(2)
d.push_back("A")
d.push_back("B")
d.push_front("X")  # Đầy: mở rộng lên 4 ô trước khi thêm.
d.push_back("C")

assert d.to_list() == ["X", "A", "B", "C"]
assert d.pop_front() == "X"
assert d.pop_back() == "C"

d.push_front("Y")
d.push_back("D")
assert d.to_list() == ["Y", "A", "B", "D"]
assert d.peek_front() == "Y"
assert d.peek_back() == "D"
```

Điều đáng chú ý là `_grow()` luôn sao chép từ `head` cũ theo modulo **sức chứa cũ**, rồi đặt `head = 0`. Nếu chỉ chép nguyên mảng vật lý từ trái sang phải trong lúc dữ liệu đã quay vòng, deque có thể đổi thứ tự và trả sai kết quả.

## 5. Cách 2 — Deque bằng các khối liên kết

Mảng vòng giữ mọi vị trí trong **một mảng vật lý**. **Deque khối liên kết** (*block-linked deque*, *segmented deque*) chia phần tử thành những **khối có số ô giới hạn**, sau đó liên kết các khối với nhau. Mỗi khối chứa một mảng nhỏ, còn các khối lưu `prev`/`next` để di chuyển theo cả hai chiều.

Ví dụ với **mỗi khối có `B = 4` ô**:

```text
                  CÁC KHỐI NỐI THEO HAI CHIỀU

front_block                                    back_block
     |                                             |
     v                                             v
+---------------+        +---------------+        +---------------+
| · | · | A | B | <----> | C | D | E | F | <----> | G | H | · | · |
+---------------+        +---------------+        +---------------+
      [2:4)                  [0:4)                   [0:2)

Thứ tự logic: A → B → C → D → E → F → G → H
```

Dấu `[lo:hi)` chỉ **đoạn vị trí hợp lệ trong một khối**, từ `lo` (bao gồm) đến `hi` (không bao gồm). Các ô ngoài đoạn đó không thuộc deque, dù trước đây có thể đã lưu dữ liệu khác.

Khác với **danh sách liên kết đôi từng phần tử**, ở đây **mỗi khối** có hai liên kết đến khối láng giềng; phần tử trong khối được lưu trong **mảng con**. Nhờ giảm số nút/đối tượng liên kết theo số lượng phần tử, cách này thường tận dụng tính cục bộ của bộ nhớ tốt hơn liên kết từng phần tử, dù vẫn phải trả chi phí quản lý các khối và các ô chưa dùng.

### 5.1. Trạng thái và bất biến

Một thiết kế đơn giản lưu:

- `front_block`: khối chứa phần tử đầu.
- `back_block`: khối chứa phần tử cuối.
- `size`: tổng số phần tử.
- `B`: sức chứa của mỗi khối, **cố định và dương**.
- Trong từng khối: mảng `values` dài `B`, chỉ số `lo` và `hi`, cùng `prev` và `next`.

Các bất biến quan trọng:

1. Nếu `size == 0`, `front_block is None` và `back_block is None`.
2. Nếu không rỗng, hai con trỏ ngoài cùng đều trỏ tới khối hợp lệ; các khối đang liên kết đều chứa ít nhất **một phần tử**.
3. Trong mỗi khối đang dùng, `0 ≤ lo < hi ≤ B`. Dữ liệu hợp lệ chỉ nằm trong đoạn `values[lo:hi]`.
4. `front_block.prev is None` và `back_block.next is None`.
5. Hai khối kề nhau `a` và `b` phải thỏa `a.next is b` và `b.prev is a`.
6. Tổng `(hi - lo)` của các khối đang liên kết bằng `size`.
7. Ghép các đoạn hợp lệ của các khối từ `front_block` đến `back_block` cho đúng dãy deque logic từ đầu đến cuối.

Không cần mọi khối đều đầy. Có thể có **ô trống trong khối đầu hoặc cuối**, và trong một cách triển khai đơn giản cũng có thể còn ô chưa sử dụng ở một số khối bên trong sau nhiều lượt thêm/lấy ở hai phía. Điều quan trọng là không xuất hiện **khối rỗng vẫn được liên kết như một khối chứa dữ liệu**.

### 5.2. Thêm ở đầu và ở cuối

**`push_front(x)`:** nếu chưa có khối, tạo khối đầu với `lo = hi = B` rồi giảm `lo` và ghi `x`. Nếu đã có khối đầu và `lo > 0`, giảm `lo` rồi ghi trực tiếp. Nếu `lo == 0`, tạo **khối mới phía trước**, nối nó với khối đầu cũ, đặt dữ liệu vào ô cuối của khối mới.

**`push_back(x)`:** nếu chưa có khối, tạo khối đầu với `lo = hi = 0` rồi ghi `x` vào ô 0. Nếu khối cuối có `hi < B`, ghi tại `hi` rồi tăng `hi`. Nếu `hi == B`, tạo **khối mới phía sau**, nối với khối cuối cũ và ghi tại ô đầu của khối mới.

Chú ý: **khối có thể còn ô trống ở phía đối diện**. Ví dụ một khối có `lo = 0` và `hi = 2` trong tổng `B = 4` ô. Nó còn chỗ **ở bên phải** nhưng đã hết chỗ **ở bên trái**, nên `push_front` cần mở khối mới phía trước. Đây là hệ quả hợp lệ của thiết kế chỉ dùng các đoạn liên tiếp trong mỗi khối.

### 5.3. Lấy ở hai đầu và tháo khối rỗng

**`pop_front()`:** lấy `values[lo]` ở khối đầu, dọn ô đó, tăng `lo` và giảm `size`. Nếu sau thao tác `lo == hi`, khối vừa rỗng: **tháo nó khỏi đầu chuỗi**; nếu không còn khối nào, đặt cả `front_block` và `back_block` về `None`.

**`pop_back()`:** giảm `hi` của khối cuối, lấy `values[hi]`, dọn ô và giảm `size`. Nếu `lo == hi`, tháo khối cuối; khi đó phải sửa `back_block` và, nếu vừa lấy phần tử duy nhất, sửa cả `front_block`.

Vì mỗi thao tác chỉ làm việc với **khối ở một đầu** và tối đa một thay đổi liên kết giữa các khối, không cần duyệt qua mọi khối đang có. Nếu `B` là một hằng số nhỏ cố định, mỗi thao tác có **O(1)** thời gian trong mô hình cấp phát khối chi phí hằng số.

## 6. Truy vết khi tạo và gỡ các khối

Chọn `B = 3`. Trong sơ đồ, mỗi khối có ba ô; dấu `·` là ô ngoài đoạn hợp lệ:

| Bước | Thao tác | Các khối từ đầu đến cuối | Deque logic |
|---:|---|---|---|
| 0 | Khởi tạo | Không có khối | `[]` |
| 1 | `push_back(A)` | `[A, ·, ·]` | `[A]` |
| 2 | `push_back(B)` | `[A, B, ·]` | `[A, B]` |
| 3 | `push_front(X)` | `[·, ·, X] ⇄ [A, B, ·]` | `[X, A, B]` |
| 4 | `push_back(C)` | `[·, ·, X] ⇄ [A, B, C]` | `[X, A, B, C]` |
| 5 | `pop_front()` → `X` | `[A, B, C]` | `[A, B, C]` |
| 6 | `push_front(Y)` | `[·, ·, Y] ⇄ [A, B, C]` | `[Y, A, B, C]` |
| 7 | `push_back(D)` | `[·, ·, Y] ⇄ [A, B, C] ⇄ [D, ·, ·]` | `[Y, A, B, C, D]` |
| 8 | `pop_back()` → `D` | `[·, ·, Y] ⇄ [A, B, C]` | `[Y, A, B, C]` |

Ở bước 3, khối chứa `A, B` không có chỗ **phía trước** (`lo = 0`), nên ta tạo khối trái mới. Ở bước 5, sau khi lấy `X`, khối trái rỗng và được tháo khỏi chuỗi. Ở bước 7, khối phải `[A, B, C]` đã kín phía cuối, nên tạo một khối phải mới cho `D`.

**Không có bước nào chuyển `A`, `B` hoặc `C` sang khối khác.** Đó là khác biệt quan trọng với một lần mở rộng mảng vòng phải sao chép toàn bộ các phần tử hiện có.

## 7. Mã Python: deque bằng chuỗi khối liên kết

Ví dụ sau cài đặt cấu trúc khối liên kết hai chiều, mỗi khối gồm `B` ô. Các khối chỉ được tạo khi cần và được tháo ngay khi đã rỗng. Để mã dễ hiểu, mỗi phần tử vẫn có thể là `None`; trạng thái rỗng được xác định bằng `_size` và con trỏ khối.

```python
class _Block:
    def __init__(self, capacity, start):
        self.values = [None] * capacity
        self.lo = start
        self.hi = start
        self.prev = None
        self.next = None


class LinkedBlockDeque:
    def __init__(self, block_size=4):
        if type(block_size) is not int or block_size <= 0:
            raise ValueError("block_size phải là số nguyên dương")
        self._block_size = block_size
        self._front = None
        self._back = None
        self._size = 0

    def __len__(self):
        return self._size

    def is_empty(self):
        return self._size == 0

    def push_front(self, value):
        if self._front is None:
            block = _Block(self._block_size, self._block_size)
            self._front = self._back = block
        elif self._front.lo == 0:
            block = _Block(self._block_size, self._block_size)
            block.next = self._front
            self._front.prev = block
            self._front = block

        block = self._front
        block.lo -= 1
        block.values[block.lo] = value
        self._size += 1

    def push_back(self, value):
        if self._back is None:
            block = _Block(self._block_size, 0)
            self._front = self._back = block
        elif self._back.hi == self._block_size:
            block = _Block(self._block_size, 0)
            block.prev = self._back
            self._back.next = block
            self._back = block

        block = self._back
        block.values[block.hi] = value
        block.hi += 1
        self._size += 1

    def pop_front(self):
        if self._front is None:
            raise IndexError("Deque rỗng")

        block = self._front
        value = block.values[block.lo]
        block.values[block.lo] = None
        block.lo += 1
        self._size -= 1

        if block.lo == block.hi:
            following = block.next
            self._front = following
            if following is None:
                self._back = None
            else:
                following.prev = None
            block.next = None
        return value

    def pop_back(self):
        if self._back is None:
            raise IndexError("Deque rỗng")

        block = self._back
        block.hi -= 1
        value = block.values[block.hi]
        block.values[block.hi] = None
        self._size -= 1

        if block.lo == block.hi:
            previous = block.prev
            self._back = previous
            if previous is None:
                self._front = None
            else:
                previous.next = None
            block.prev = None
        return value

    def peek_front(self):
        if self._front is None:
            raise IndexError("Deque rỗng")
        return self._front.values[self._front.lo]

    def peek_back(self):
        if self._back is None:
            raise IndexError("Deque rỗng")
        return self._back.values[self._back.hi - 1]

    def to_list(self):
        result = []
        block = self._front
        while block is not None:
            result.extend(block.values[block.lo:block.hi])
            block = block.next
        return result


d = LinkedBlockDeque(block_size=3)
d.push_back("A")
d.push_back("B")
d.push_front("X")
d.push_back("C")

assert d.to_list() == ["X", "A", "B", "C"]
assert d.pop_front() == "X"
d.push_front("Y")
d.push_back("D")
assert d.to_list() == ["Y", "A", "B", "C", "D"]
assert (d.peek_front(), d.peek_back()) == ("Y", "D")
assert d.pop_back() == "D"

assert [d.pop_front() for _ in range(4)] == ["Y", "A", "B", "C"]
assert d.is_empty()
assert d._front is None and d._back is None
```

Mỗi lần tạo khối trong mã dùng `[None] * B`, tốn **O(B)** để khởi tạo mảng con. Khi **`B` là kích thước khối cố định**, chi phí này được coi là O(1) theo số phần tử `n` trong deque. Nếu coi `B` cũng là biến đầu vào tăng theo bài toán, cần ghi rõ thao tác cấp phát khối có O(B) thời gian và bộ nhớ cho lần đó.

### Thử tình huống biên

```python
# Một ô mỗi khối: mọi khối chứa tối đa một phần tử.
single_slot = LinkedBlockDeque(block_size=1)
single_slot.push_front(None)
single_slot.push_back("A")
single_slot.push_front("B")

assert single_slot.to_list() == ["B", None, "A"]
assert single_slot.pop_back() == "A"
assert single_slot.pop_front() == "B"
assert single_slot.pop_front() is None
assert single_slot.is_empty()

# Tái sử dụng sau khi đã tháo hết các khối.
single_slot.push_back("C")
assert single_slot.pop_back() == "C"
assert len(single_slot) == 0
```

Nếu còn **một phần tử duy nhất**, `pop_front` và `pop_back` đều phải đưa cả `_front` và `_back` về `None`. Nếu quên một trong hai, lần thêm tiếp theo có thể nối vào một khối đã bị loại khỏi deque.

## 8. So sánh độ phức tạp hai cách biểu diễn

Gọi `n` là số phần tử đang có, `C` là sức chứa của một mảng vòng, `B` là sức chứa cố định của mỗi khối và `k` là số khối đang được liên kết.

| Đặc tính | Mảng vòng cố định | Mảng vòng tự mở rộng | Các khối liên kết (B cố định) |
|---|---|---|---|
| `push_front` | O(1) nếu còn chỗ | **O(1) khấu hao** | **O(1)** |
| `push_back` | O(1) nếu còn chỗ | **O(1) khấu hao** | **O(1)** |
| `pop_front` | O(1) | O(1) | O(1) |
| `pop_back` | O(1) | O(1) | O(1) |
| `peek_front` / `peek_back` | O(1) | O(1) | O(1) |
| Truy cập phần tử thứ `j` khi biết `j` | O(1) | O(1) | Thường phải đi qua khối: O(k) trường hợp xấu nhất |
| Duyệt toàn bộ `n` phần tử | O(n) | O(n) | O(n + k), với `k ≤ n` khi không giữ khối rỗng |
| Bộ nhớ lưu trữ | O(C) | O(C) | O(Bk), tức **O(n)** khi B là hằng số |
| Khi cần thêm chỗ | Áp dụng chính sách khi đầy | Cấp phát mảng mới, **chép O(n)** phần tử | Cấp phát thêm **một khối**, không phải sao chép toàn deque |

**Vì sao O(Bk) cho cấu trúc khối?** Có `k` khối, mỗi khối cấp phát `B` vị trí cùng hai tham chiếu liên kết và metadata. Thiết kế của bài tháo khối ngay khi rỗng, nên với `n > 0`, mỗi khối hoạt động chứa ít nhất một phần tử và `k ≤ n`. Khi `B` là hằng số, tổng bộ nhớ là **O(n)**. Số ô chưa dùng trong các khối có thể làm hệ số bộ nhớ cao hơn mảng đặc.

**Vì sao truy cập giữa có thể chậm?** Mảng vòng ánh xạ chỉ số logic sang ô vật lý bằng một phép tính. Ở deque khối liên kết, ví dụ cần lấy phần tử logic thứ `j`, ta thường phải đi từ khối đầu hoặc cuối qua các liên kết cho tới khối chứa phần tử ấy. Truy cập vị trí giữa trong biểu diễn liên kết khối đơn giản không được bảo đảm O(1).

**Chi phí đỉnh của mở rộng:** khi mảng vòng động đầy, có thể phải giữ **đồng thời mảng cũ và mảng mới** lúc chép dữ liệu. Deque khối có thể tăng từng khối nhỏ nên tránh bước sao chép toàn bộ phần tử đang chờ, nhưng đổi lại có chi phí quản lý nhiều khối và việc cấp phát từng khối.

## 9. Mối quan hệ với `collections.deque` của Python

Python cung cấp `collections.deque`, hỗ trợ thao tác hiệu quả ở hai đầu:

```python
from collections import deque

d = deque(["A", "B", "C"])
d.appendleft("X")          # push_front
d.append("Y")              # push_back

assert list(d) == ["X", "A", "B", "C", "Y"]
assert d.popleft() == "X"   # pop_front
assert d.pop() == "Y"       # pop_back
assert list(d) == ["A", "B", "C"]
```

Trong **CPython**, deque được tổ chức dựa trên **các khối chứa nhiều tham chiếu phần tử được liên kết với nhau**; kích thước khối và chính sách tái sử dụng khối là **chi tiết triển khai**, có thể thay đổi theo phiên bản. Để lập trình đúng, cần dựa vào **hợp đồng công khai** của `collections.deque`: thêm/lấy ở hai đầu nhanh, còn việc truy cập các phần tử ở giữa bằng chỉ số có thể tốn O(n). Không nên viết mã ứng dụng giả định một kích thước khối nội bộ cụ thể.

Một deque có `maxlen` còn có chính sách giới hạn dung lượng riêng: khi đầy, thêm vào một đầu sẽ **tự bỏ phần tử ở đầu đối diện**.

```python
recent = deque(["A", "B", "C"], maxlen=3)
recent.append("D")
assert list(recent) == ["B", "C", "D"]  # Bỏ A bên trái.

recent.appendleft("X")
assert list(recent) == ["X", "B", "C"]  # Bỏ D bên phải.
```

Chính sách đó hữu ích cho lịch sử dữ liệu gần nhất, nhưng có thể gây mất phần tử chưa được xử lý nếu ứng dụng mong đợi kiểu queue từ chối khi đầy. **Kiểu lưu trữ** và **chính sách khi đầy** là hai quyết định khác nhau.

### Lưu ý về đồng thời

Các lớp `RingDeque` và `LinkedBlockDeque` minh họa ở bài này **không tự đồng bộ** cho nhiều luồng. Các thao tác ghép gồm nhiều bước như “kiểm tra rồi thêm”, hoặc duyệt trong lúc luồng khác thay đổi dữ liệu, cần cơ chế phối hợp phù hợp. Với producer–consumer cần chờ và giới hạn sức chứa trong Python, có thể cân nhắc `queue.Queue` theo đúng hợp đồng chặn của nó.

## 10. Khi nào nên chọn mảng vòng, khi nào chọn khối liên kết?

**Mảng vòng** thường hợp lý khi:

- Biết trước số phần tử tối đa hoặc chấp nhận tăng dung lượng theo chu kỳ.
- Cần **truy cập ngẫu nhiên theo vị trí logic** nhanh ngoài bốn phép ở hai đầu.
- Muốn giữ phần tử trong một vùng chứa mảng liên tục, thường thuận lợi cho tính cục bộ bộ nhớ.
- Có thể chấp nhận một lần chép O(n) khi tăng sức chứa, hoặc chọn sức chứa cố định để tránh bước đó.

**Các khối liên kết** thường hợp lý khi:

- Số phần tử thay đổi nhiều và muốn tăng/giảm lưu trữ theo **khối nhỏ**.
- Quan trọng nhất là các thao tác **hai đầu**, rất ít truy cập vị trí giữa.
- Muốn tránh việc mỗi lần mở rộng phải sao chép toàn bộ các phần tử đang chờ.
- Chấp nhận các liên kết giữa khối, các ô chưa dùng ở đầu/cuối và cấp phát nhiều mảng con.

Hai ví dụ ứng dụng:

- **Hàng công việc biến động:** nếu chỉ thêm/lấy ở hai phía, một deque lưu theo khối có thể phục vụ tốt mà không cần chép nguyên hàng khi tải tăng; vẫn phải cân nhắc đồng bộ và chiến lược quá tải.
- **Bộ đệm cửa sổ trượt:** nếu chủ yếu duy trì phần tử theo hai đầu, cả hai cách đều phù hợp. Nếu thuật toán còn cần truy cập nhanh phần tử logic thứ `j` bất kỳ, mảng vòng có lợi thế rõ ràng.

Không có một cách lưu trữ tốt nhất cho mọi trường hợp. Cần xét **mẫu thao tác**, **độ trễ cao nhất chấp nhận được**, **độ lớn dữ liệu**, **số lần thay đổi kích thước** và **chi phí bộ nhớ phụ**.

## 11. Lỗi dễ mắc và cách kiểm tra

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Mảng vòng: `push_front` quên lấy modulo khi `head = 0` | Chỉ số ra ngoài phạm vi trong nhiều ngôn ngữ | Dùng `(head - 1 + C) % C` với `C > 0` |
| Mảng vòng: `pop_back` tính `(head + size) % C` | Đọc **ô ghi tiếp**, không phải ô cuối | Dùng `(head + size - 1) % C` |
| Mảng vòng: dùng `None` làm dấu hiệu chắc chắn rỗng | Không thể lưu `None` hợp lệ | Dựa vào `size == 0` |
| Mảng vòng: mở rộng nhưng sao chép mảng vật lý theo thứ tự 0..C-1 | Dãy FIFO đổi thứ tự khi đã quay vòng | Sao chép theo `(old_head + j) % old_C` |
| Khối liên kết: dùng `hi` như chỉ số phần tử cuối | Đọc sang **ô ngay sau phần tử cuối** | Cuối hợp lệ là `hi - 1` |
| Khối liên kết: tạo khối mới nhưng quên liên kết `prev/next` hai chiều | Đi theo một chiều được, chiều ngược bị đứt | Cập nhật đối xứng hai đầu liên kết |
| Khối liên kết: để khối rỗng nằm giữa chuỗi hoạt động | Duyệt có thể gặp khối không chứa phần tử; lãng phí bộ nhớ | Tháo khối khi `lo == hi` |
| Khối liên kết: bỏ khối duy nhất nhưng chỉ xóa một con trỏ ngoài | `front` hoặc `back` còn trỏ tới khối cũ | Khi lấy hết, đưa **cả hai** về `None` |
| Khối liên kết: cho rằng mọi khối đều kín mới hợp lệ | Bỏ qua các khoảng trống hợp lệ trong khối | Theo dõi đoạn `[lo, hi)` của từng khối |
| Nhầm “O(1) khấu hao” với mọi thao tác O(1) | Không tính được độ trễ tăng mảng | Ghi rõ lần resize có thể O(n) |
| Thao tác đồng thời mà không có đồng bộ | Có thể làm sai bộ đếm hoặc chuỗi liên kết | Sử dụng khóa/queue đồng bộ phù hợp |

Một cách kiểm tra hữu ích là giữ **một dãy logic kỳ vọng** rồi so sánh sau từng phép: trước/sau quay vòng, trước/sau tạo khối mới, trước/sau tháo khối cuối cùng. Đừng chỉ nhìn mảng vật lý hoặc số khối, vì cùng một dãy logic có thể có nhiều bố trí vật lý hợp lệ.

## 12. Tự luyện với lời giải

**Bài 1 — Chỉ số trong mảng vòng.** Deque có `C = 6`, `head = 0` và `size = 2`. Sau `push_front(X)`, `head` mới bằng bao nhiêu? Phần tử cuối đang ở ô nào?

*Lời giải:* `head = (0 - 1 + 6) % 6 = 5`, `size = 3`. Ô cuối là `(5 + 3 - 1) % 6 = 1`. Dãy mới bắt đầu tại ô 5 rồi đi qua 0 và 1.

**Bài 2 — Mở rộng mảng đã quay vòng.** Mảng vật lý có `C = 4`, `head = 2`, `size = 4` và dữ liệu `[C, D, A, B]`. Hãy nêu bốn giá trị đầu tiên trong mảng mới sau khi tăng lên 8 ô.

*Lời giải:* Thứ tự logic bắt đầu ở ô 2, rồi 3, 0, 1: `A, B, C, D`. Mảng mới bắt đầu bằng `[A, B, C, D, …]` và `head` mới bằng 0.

**Bài 3 — Khối mới bên trái.** Khối đầu có `B = 4`, `lo = 0`, `hi = 2`, chứa `[A, B, ·, ·]`. Có thể `push_front(X)` vào chính khối này mà vẫn giữ đoạn hợp lệ liên tiếp không?

*Lời giải:* **Không**, vì `lo = 0` nên không còn vị trí ở **bên trái** đoạn hợp lệ. Có thể tạo khối mới trước khối cũ và đặt `X` ở ô cuối khối mới.

**Bài 4 — Tháo khối.** Một deque chỉ có một khối với `lo = 2`, `hi = 3` và chứa một phần tử ở ô 2. Sau `pop_back()`, phải cập nhật gì?

*Lời giải:* Lấy phần tử ô 2, giảm `hi` thành 2, khiến `lo == hi`. Khối trở thành rỗng và phải được tháo; đặt `front_block = back_block = None`, `size = 0`.

**Bài 5 — Chi phí cấp phát.** Với kích thước khối `B` được cố định từ trước, thêm một khối mất O(1) theo số phần tử `n` trong deque. Nếu `B` cũng tăng cùng đầu vào, có thể khẳng định thao tác tạo khối O(1) độc lập với `B` không?

*Lời giải:* **Không.** Việc khởi tạo `B` ô thường có chi phí O(B). Kết luận O(1) theo `n` chỉ dùng khi `B` là hằng số.

**Bài 6 — Chọn cách lưu.** Ứng dụng thường thêm/lấy ở hai đầu và đôi khi đọc phần tử logic thứ `j` bất kỳ. Mảng vòng và chuỗi khối liên kết khác nhau ở điểm nào?

*Lời giải:* Mảng vòng ánh xạ `j` sang `(head + j) % C` trong O(1). Chuỗi khối liên kết đơn giản thường phải duyệt qua nhiều khối để tìm phần tử, có thể O(k) với `k` là số khối.

**Bài 7 — Độ phức tạp.** Vì sao nói `push_front` trên mảng vòng tự mở rộng thường O(1) khấu hao, còn thêm vào đầu một chuỗi khối liên kết với `B` cố định có O(1) theo số phần tử?

*Lời giải:* Mảng vòng đôi khi phải cấp phát và sao chép **toàn bộ `n` phần tử** khi đầy, nhưng các lần nhân đôi tạo chi phí khấu hao O(1). Chuỗi khối chỉ phải thêm **một khối kích thước B cố định** khi đầu hiện tại hết chỗ; không cần sao chép `n` phần tử đã có.

**Ghi nhớ:** Với deque, ta cần bảo toàn **thứ tự logic từ front tới back** trong mọi phép thêm và lấy. **Mảng vòng** làm điều đó bằng `head`, `size` và phép modulo; **khối liên kết** làm điều đó bằng các đoạn dữ liệu trong khối và liên kết giữa các khối. Cả hai đều hỗ trợ thao tác hai đầu hiệu quả, nhưng khác nhau ở cách mở rộng, độ trễ khi cấp phát, mức dùng bộ nhớ và khả năng truy cập phần tử ở giữa.
