# Phân biệt trạng thái đầy và rỗng trong bộ đệm vòng

Một **bộ đệm vòng** (*circular buffer*, *ring buffer*) dùng mảng có sức chứa cố định và các chỉ số quay vòng để tái sử dụng ô đã được giải phóng. Nó rất thích hợp để cài đặt **hàng đợi FIFO**: phần tử được thêm trước sẽ được lấy ra trước. Tuy nhiên, có một điểm dễ gây lỗi: **chỉ số đọc và chỉ số ghi trùng nhau có thể biểu thị cả “rỗng” lẫn “đầy”**.

Bài học thuộc chương **Hàng đợi và deque** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mô-đun xây dựng nền tảng cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị; đồng thời rèn cách thiết lập bất biến, hiểu thao tác và đánh giá độ phức tạp thời gian, bộ nhớ. Mục tiêu cụ thể của bài này là phân biệt đúng **rỗng/đầy** trong bộ đệm vòng, lựa chọn một quy ước lưu trạng thái và triển khai nhất quán từng phép `enqueue`, `dequeue`.

## 1. Bối cảnh: chỉ số quay vòng và hai loại vị trí

Giả sử ta có mảng `data` gồm `C` ô, với `C > 0`. Hai chỉ số thường được đặt tên:

- **`head` / `read_index`:** ô chứa phần tử **sẽ được lấy tiếp theo** khi bộ đệm không rỗng.
- **`tail` / `write_index`:** ô **sẽ ghi phần tử mới tiếp theo** khi bộ đệm chưa đầy.

Trong bài này, `tail` **luôn là vị trí ghi tiếp**, không phải vị trí chứa phần tử cuối đang chờ. Sự phân biệt này rất quan trọng: các tài liệu và thư viện khác có thể dùng tên `rear` hoặc `tail` để chỉ **ô chứa phần tử cuối**, dẫn đến công thức khác.

Hai phép tiến chỉ số qua một ô dùng:

```text
next(i) = (i + 1) % C
```

Sau chỉ số `C - 1` là chỉ số `0`. Chẳng hạn, `C = 4`:

```text
      [0] → [1] → [2] → [3]
       ↑                 |
       └─────────────────┘

next(0) = 1
next(2) = 3
next(3) = 0
```

Khi thêm phần tử, ta ghi ở `tail` rồi cập nhật `tail = next(tail)`. Khi lấy phần tử, ta đọc ở `head` rồi cập nhật `head = next(head)`. Không cần dịch toàn bộ dữ liệu.

Nhưng khi cả hai chỉ số quay đủ vòng, một vấn đề xuất hiện.

## 2. Vì sao `head == tail` không đủ để kết luận rỗng?

Hãy quan sát bộ đệm vật lý có `C = 4`. Ban đầu:

```text
Chỉ số         0      1      2      3
             +------+------+------+------+
data         |  ·   |  ·   |  ·   |  ·   |
             +------+------+------+------+
               ↑
           head = tail = 0
           Số phần tử: 0 — RỖNG
```

Thêm lần lượt `A`, `B`, `C`, `D`. Theo quy ước `tail` là ô sắp ghi:

```text
enqueue(A): ghi ô 0, tail = 1
enqueue(B): ghi ô 1, tail = 2
enqueue(C): ghi ô 2, tail = 3
enqueue(D): ghi ô 3, tail = 0  (quay vòng)

Chỉ số         0      1      2      3
             +------+------+------+------+
data         |  A   |  B   |  C   |  D   |
             +------+------+------+------+
               ↑
           head = tail = 0
           Số phần tử: 4 — ĐẦY
```

Ở **hai trạng thái hoàn toàn khác nhau**, ta đều có `head == tail == 0`. Trạng thái chỉ gồm cặp chỉ số **không đủ thông tin** nếu muốn dùng được cả `C` ô.

Điều này không phải lỗi của phép modulo. Nó là kết quả tự nhiên khi các chỉ số quay vòng: sau `C` lần tiến, một chỉ số trở lại vị trí ban đầu. Ta cần thêm **một quy ước** để biết đã thực hiện bao nhiêu thao tác hợp lệ, hoặc chủ động không sử dụng toàn bộ số ô.

Nếu thiết kế nhầm `head == tail` luôn là rỗng, ngay sau lần enqueue thứ `C`, hàng đợi đầy có thể bị nhận nhầm là rỗng. Khi đó dữ liệu vừa ghi sẽ trở nên không thể lấy ra theo đúng FIFO.

## 3. Ba cách phân biệt rỗng và đầy

Có ba phương án thông dụng. Mỗi phương án chọn **bất biến trạng thái** khác nhau, vì thế công thức kiểm tra cũng khác nhau.

| Cách biểu diễn | Điều kiện rỗng | Điều kiện đầy | Số phần tử lưu tối đa trong mảng `C` ô |
|---|---|---|---:|
| **1. Có bộ đếm `size`** | `size == 0` | `size == C` | **`C`** |
| **2. Chừa một ô trống** | `head == tail` | `next(tail) == head` | **`C - 1`** |
| **3. Có cờ `full`** | `head == tail and not full` | `full` | **`C`** |

Trong cách 1, `tail` có thể **được tính** từ `head` và `size`; không nhất thiết lưu thành biến. Trong cách 2 và 3, ta lưu hai chỉ số `head` và `tail`. Mỗi công thức trong bảng chỉ đúng khi các thao tác cập nhật trạng thái theo **cùng một quy ước**.

Không nên trộn lẫn: chẳng hạn, đã chừa một ô trống thì không được áp dụng logic “đầy khi `size == C`” nếu không có biến `size` và không thực sự dùng đủ `C` ô.

## 4. Cách 1: lưu thêm bộ đếm `size`

### Bất biến

Lưu ba thông tin: mảng `data` dài `C`, chỉ số đọc `head`, và số phần tử hợp lệ `size`:

```text
C > 0
0 <= head < C
0 <= size <= C

empty = (size == 0)
full  = (size == C)

write_index = (head + size) % C
```

Nếu `size > 0`, phần tử logic ở vị trí thứ `j` (tính từ đầu) nằm tại ô:

```text
physical_index(j) = (head + j) % C
                  với 0 <= j < size
```

Theo đó, `write_index` chính là vị trí **sau phần tử cuối logic**, chỉ dùng để ghi khi `size < C`.

Khi `size = 0`, `write_index = head`; khi `size = C`, do `C % C = 0` nên **`write_index = head`**. Sự trùng chỉ số vẫn tồn tại nhưng đã có `size` để phân biệt.

### Thao tác thêm và lấy

```text
ENQUEUE(x):
    if size == C:
        báo lỗi đầy
    write_index = (head + size) % C
    data[write_index] = x
    size = size + 1

DEQUEUE():
    if size == 0:
        báo lỗi rỗng
    result = data[head]
    data[head] = EMPTY
    head = (head + 1) % C
    size = size - 1
    return result
```

Dấu `EMPTY` trong giả mã là thao tác dọn vị trí vật lý; **không dùng nội dung ô để suy ra trạng thái rỗng**. Chẳng hạn, nếu `None` là một giá trị dữ liệu hợp lệ, `data[head] is None` không cho ta biết hàng có rỗng hay không.

### Truy vết khi chỉ số trùng nhau

Với `C = 3`:

| Bước | Thao tác | Mảng vật lý `[0,1,2]` | `head` | `size` | `write_index` | Trạng thái |
|---:|---|---|---:|---:|---:|---|
| 0 | Khởi tạo | `[·, ·, ·]` | 0 | 0 | 0 | Rỗng |
| 1 | `enqueue(A)` | `[A, ·, ·]` | 0 | 1 | 1 | Bình thường |
| 2 | `enqueue(B)` | `[A, B, ·]` | 0 | 2 | 2 | Bình thường |
| 3 | `enqueue(C)` | `[A, B, C]` | 0 | 3 | 0 | **Đầy** |
| 4 | `dequeue()` → `A` | `[·, B, C]` | 1 | 2 | 0 | Bình thường |
| 5 | `enqueue(D)` | `[D, B, C]` | 1 | 3 | 1 | **Đầy** |

Ở bước 5, `head = write_index = 1` nhưng hàng chứa đủ ba phần tử theo thứ tự **`B → C → D`**. Chỉ có `size` mới phân biệt được trạng thái này với một hàng rỗng có `head = 1`.

### Cài đặt Python bằng bộ đếm

```python
class CountedRingQueue:
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

    def enqueue(self, value):
        if self.is_full():
            raise OverflowError("Bộ đệm vòng đã đầy")
        capacity = len(self._data)
        write_index = (self._head + self._size) % capacity
        self._data[write_index] = value
        self._size += 1

    def peek(self):
        if self.is_empty():
            raise IndexError("Bộ đệm vòng rỗng")
        return self._data[self._head]

    def dequeue(self):
        if self.is_empty():
            raise IndexError("Bộ đệm vòng rỗng")
        value = self._data[self._head]
        self._data[self._head] = None
        self._head = (self._head + 1) % len(self._data)
        self._size -= 1
        return value


q = CountedRingQueue(3)
for x in ["A", "B", "C"]:
    q.enqueue(x)

assert q.is_full()
assert q.dequeue() == "A"
q.enqueue("D")  # Tái sử dụng ô 0.

assert q.peek() == "B"
assert q.is_full()
assert [q.dequeue(), q.dequeue(), q.dequeue()] == ["B", "C", "D"]
assert q.is_empty()

q.enqueue(None)  # None vẫn là một phần tử hợp lệ.
assert len(q) == 1
assert q.dequeue() is None
assert q.is_empty()
```

**Ưu điểm:** tận dụng đủ `C` ô; API `size()`/`len()` là O(1), dễ đọc và dễ kiểm tra bất biến. **Đánh đổi:** bộ đếm phải được cập nhật chính xác ở mọi nhánh thao tác thành công. Nếu thao tác chạy đồng thời, `size` cũng là trạng thái chia sẻ cần được đồng bộ đúng cách.

## 5. Cách 2: chủ động chừa một ô trống

Cách này **không lưu `size`**. Ta giữ hai chỉ số vật lý:

- `head`: vị trí sẽ đọc.
- `tail`: vị trí sẽ ghi.

Quy ước quan trọng là **không bao giờ được lấp đầy cả `C` ô**. Ta dừng khi chỉ còn đúng một ô chưa được dùng. Nhờ vậy:

```text
empty = (head == tail)
full  = ((tail + 1) % C == head)
```

Với `C = 4`, ta chỉ chứa tối đa **3 phần tử**:

```text
RỖNG: head = 0, tail = 0

       0     1     2     3
      [·]   [·]   [·]   [·]


ĐẦY: head = 0, tail = 3

       0     1     2     3
      [A]   [B]   [C]   [·]
       ↑                 ↑
      head              tail (ô chừa lại)

next(tail) = 0 = head
```

Ô `tail` vẫn trống lúc hàng đầy. Chữ “đầy” ở đây nghĩa là **đã đạt số phần tử tối đa được phép của quy ước**, không phải mọi ô trong mảng vật lý đều có dữ liệu.

Để lưu được **ít nhất một phần tử**, cần `C >= 2`. Mảng chỉ có một ô (`C = 1`) sẽ có sức chứa hữu dụng `C - 1 = 0`, nên không phù hợp với phương án này.

### Giả mã hai phép toán

```text
ENQUEUE(x):
    if (tail + 1) % C == head:
        báo lỗi đầy
    data[tail] = x
    tail = (tail + 1) % C

DEQUEUE():
    if head == tail:
        báo lỗi rỗng
    result = data[head]
    data[head] = EMPTY
    head = (head + 1) % C
    return result
```

Trong phương án này, **không cần biến `size`**. Khi cần tính độ dài, có thể dùng `(tail - head + C) % C`, cho kết quả trong khoảng `0` đến `C - 1`; công thức này đúng vì ta đã quy ước chừa một ô.

### Truy vết với `C = 4`

| Bước | Thao tác | `head` | `tail` | Số phần tử logic | Trạng thái |
|---:|---|---:|---:|---:|---|
| 0 | Khởi tạo | 0 | 0 | 0 | Rỗng |
| 1 | `enqueue(A)` | 0 | 1 | 1 | Bình thường |
| 2 | `enqueue(B)` | 0 | 2 | 2 | Bình thường |
| 3 | `enqueue(C)` | 0 | 3 | 3 | **Đầy**, dù ô 3 còn trống |
| 4 | `dequeue()` → `A` | 1 | 3 | 2 | Bình thường |
| 5 | `enqueue(D)` | 1 | 0 | 3 | **Đầy**, thứ tự `B,C,D` |

Bước 5 tái sử dụng ô `3` rồi quay `tail` về `0`. Khi đó `next(tail) = 1 = head` nên bộ đệm đầy, mặc dù `head != tail`.

### Cài đặt Python chừa một ô

```python
class OneSlotRingQueue:
    def __init__(self, physical_capacity):
        if type(physical_capacity) is not int or physical_capacity < 2:
            raise ValueError("Cần ít nhất 2 ô vật lý")
        self._data = [None] * physical_capacity
        self._head = 0
        self._tail = 0

    def is_empty(self):
        return self._head == self._tail

    def is_full(self):
        capacity = len(self._data)
        return (self._tail + 1) % capacity == self._head

    def __len__(self):
        capacity = len(self._data)
        return (self._tail - self._head + capacity) % capacity

    def enqueue(self, value):
        if self.is_full():
            raise OverflowError("Bộ đệm vòng đã đầy")
        self._data[self._tail] = value
        self._tail = (self._tail + 1) % len(self._data)

    def peek(self):
        if self.is_empty():
            raise IndexError("Bộ đệm vòng rỗng")
        return self._data[self._head]

    def dequeue(self):
        if self.is_empty():
            raise IndexError("Bộ đệm vòng rỗng")
        value = self._data[self._head]
        self._data[self._head] = None
        self._head = (self._head + 1) % len(self._data)
        return value


q = OneSlotRingQueue(4)  # Chứa tối đa 3 phần tử.
for x in ["A", "B", "C"]:
    q.enqueue(x)

assert q.is_full()
assert len(q) == 3
assert q.dequeue() == "A"
q.enqueue("D")

assert q.is_full()
assert [q.dequeue(), q.dequeue(), q.dequeue()] == ["B", "C", "D"]
assert q.is_empty()
```

**Ưu điểm:** kiểm tra rỗng/đầy chỉ dựa trên hai chỉ số; không phải duy trì bộ đếm hoặc cờ. **Đánh đổi:** mất một ô lưu trữ hữu dụng, tương ứng tỉ lệ `1/C` của mảng vật lý. Với `C` lớn, mức tổn hao tương đối nhỏ; với `C = 2`, một nửa số ô dành cho quy ước.

## 6. Cách 3: dùng cờ `full`

Nếu muốn **dùng đủ `C` ô** nhưng không lưu bộ đếm, ta có thể giữ hai chỉ số `head`, `tail` và một cờ Boolean `full`:

```text
empty = (head == tail) and (not full)
full  = full
```

Cách hiểu:

- **`head == tail`, `full == False`:** rỗng.
- **`head == tail`, `full == True`:** đầy.
- **`head != tail`:** hàng có một số phần tử nhưng chưa đầy; theo bất biến, `full == False`.

Khi enqueue thành công, ghi vào `tail`, cho `tail` tiến một ô, rồi đặt `full = (tail == head)`. Khi dequeue thành công, đọc ô `head`, cho `head` tiến một ô và đặt `full = False`.

```text
ENQUEUE(x):
    if full:
        báo lỗi đầy

    data[tail] = x
    tail = (tail + 1) % C
    full = (tail == head)

DEQUEUE():
    if head == tail and not full:
        báo lỗi rỗng

    result = data[head]
    data[head] = EMPTY
    head = (head + 1) % C
    full = False
    return result
```

### Truy vết thay đổi cờ

Giả sử `C = 2`:

| Bước | Thao tác | `head` | `tail` | `full` | Kết luận |
|---:|---|---:|---:|---|---|
| 0 | Khởi tạo | 0 | 0 | `False` | Rỗng |
| 1 | `enqueue(A)` | 0 | 1 | `False` | Có 1 phần tử |
| 2 | `enqueue(B)` | 0 | 0 | `True` | **Đầy** |
| 3 | `dequeue()` → `A` | 1 | 0 | `False` | Có 1 phần tử |
| 4 | `dequeue()` → `B` | 0 | 0 | `False` | **Rỗng** |

Khi đầy, hai chỉ số trùng nhau nhưng cờ bật. Khi lấy ra, phải **xóa cờ đầy**, kể cả sau lần lấy đầu tiên. Quên cập nhật cờ sẽ khiến hàng không thể nhận phần tử mới dù đã có ô trống.

Cách dùng cờ làm việc được cả với **`C = 1`**: thêm một phần tử làm `head == tail` và `full = True`; lấy phần tử duy nhất xóa cờ, đưa hàng trở lại rỗng.

**Ưu điểm:** dùng đủ số ô vật lý, không cần lưu số lượng phần tử. **Đánh đổi:** cập nhật sai cờ trong một nhánh sẽ làm logic đầy/rỗng sai. Muốn biết `size` chính xác, cần thêm bộ đếm hoặc tính dựa trên các chỉ số và cờ (khi trùng: `C` nếu đầy, `0` nếu rỗng; khi không trùng: `(tail - head + C) % C`).

## 7. Phương án mở rộng: bộ đếm tăng liên tục

Một biến thể dùng hai bộ đếm logic **`read_count`** và **`write_count`** tăng mỗi khi lấy/thêm thành công, còn chỉ số vật lý lấy bằng phép modulo:

```text
size = write_count - read_count
empty = (size == 0)
full  = (size == C)

read_index  = read_count % C
write_index = write_count % C
```

Phương án này không có nhập nhằng khi **hai chỉ số vật lý** trùng nhau, vì bộ đếm logic vẫn phân biệt được “đã đi bao nhiêu vòng”. Ví dụ `C = 3`: khi vừa thêm đủ ba phần tử, `read_count = 0` và `write_count = 3`, hai chỉ số vật lý đều bằng `0` nhưng hiệu bộ đếm là `3`, nên trạng thái đầy.

Đổi lại, với **số nguyên hữu hạn bit** trong hệ thống thật, bộ đếm có thể tràn; việc tính hiệu và so sánh phải được thiết kế nhất quán với cách số nguyên quay vòng. Trong môi trường có nhiều luồng, việc công bố dữ liệu, điều kiện nhìn thấy bộ nhớ và tính nguyên tử của các phép cập nhật vẫn cần cơ chế đồng bộ phù hợp.

## 8. Cần xử lý thế nào khi bộ đệm đầy?

“Đầy” là trạng thái hợp lệ của một bộ đệm có giới hạn sức chứa, không phải một phép thuật tự tăng dung lượng. Khi `enqueue(x)` gặp hàng đầy, API phải có **chính sách rõ ràng**:

| Chính sách | Hành vi | Hệ quả |
|---|---|---|
| **Báo lỗi hoặc từ chối** | Không ghi `x`, trạng thái giữ nguyên | Không mất phần tử đang chờ; bên gửi phải xử lý lỗi |
| **Chờ có chỗ** | Đợi một dequeue thành công rồi mới ghi | Có thể gây chặn; cần phối hợp đồng bộ và điều kiện dừng |
| **Mở rộng dung lượng** | Cấp phát mảng mới, sao chép các phần tử theo thứ tự FIFO | Có bước O(n), đòi hỏi cấp phát động |
| **Ghi đè phần tử cũ nhất** | Bỏ phần tử đầu rồi ghi `x` theo chính sách đã định | Có thể mất dữ liệu chưa được xử lý; đây là *buffer ghi đè*, khác hợp đồng hàng đợi từ chối khi đầy |

Trong ba cài đặt minh họa ở trên, chính sách là **báo lỗi khi đầy**. Đối với bộ đệm cảm biến chỉ cần dữ liệu mới nhất, chính sách ghi đè có thể có ích. Với hàng chờ giao dịch hoặc công việc cần xử lý đầy đủ, ghi đè có thể là lỗi nghiệp vụ nghiêm trọng.

Tương tự, **dequeue khi rỗng** phải trả kết quả lỗi hoặc chờ dữ liệu theo hợp đồng; tuyệt đối không tự coi giá trị `None` trong ô là dấu hiệu rỗng nếu người dùng được phép enqueue `None`.

## 9. Độ phức tạp và lựa chọn cách biểu diễn

Giả sử `C` là sức chứa vật lý và các phép truy cập một ô mảng, cộng/trừ và modulo được tính là chi phí hằng số:

| Đại lượng | Lưu `size` | Chừa một ô | Cờ `full` |
|---|---:|---:|---:|
| `enqueue` thành công | O(1) | O(1) | O(1) |
| `dequeue` thành công | O(1) | O(1) | O(1) |
| `peek` | O(1) | O(1) | O(1) |
| Kiểm tra rỗng/đầy | O(1) | O(1) | O(1) |
| Truy vấn số phần tử | O(1) | O(1) | O(1) với công thức có xét cờ |
| Bộ nhớ của toàn bộ mảng | O(C) | O(C) | O(C) |
| Số phần tử tối đa | `C` | `C - 1` | `C` |

Cả ba cách dùng **O(1) bộ nhớ trạng thái** ngoài mảng chứa dữ liệu. Việc kiểm tra đầy/rỗng **không làm tăng độ phức tạp từ O(1) lên O(n)**; điều quyết định là có phải **dịch chuyển hoặc sao chép các phần tử** trong mỗi thao tác hay không.

Một gợi ý lựa chọn:

- Chọn **`size`** nếu cần lấy kích thước thường xuyên, muốn dùng đủ mọi ô và ưu tiên dễ hiểu, dễ duy trì bất biến.
- Chọn **chừa một ô** nếu muốn trạng thái rỗng/đầy được quyết định chỉ bằng hai chỉ số và chấp nhận mất một vị trí lưu.
- Chọn **cờ `full`** nếu cần dùng đủ mọi ô mà không muốn cập nhật bộ đếm; phải kiểm soát chặt việc bật/tắt cờ.
- Cân nhắc **bộ đếm tăng liên tục** khi thuật toán cần số lần đọc/ghi logic, với thiết kế tràn số và đồng bộ phù hợp.

Các cách trên đều mô tả **trạng thái tuần tự**. Nếu có một luồng sản xuất và một luồng tiêu thụ, hoặc nhiều luồng cùng thao tác, việc chọn biến trạng thái ít hơn **không tự động bảo đảm an toàn luồng**. Cần xét cơ chế khóa, tính nguyên tử, thứ tự bộ nhớ và cách thông báo đầy/rỗng theo ngữ cảnh sử dụng.

## 10. Chứng minh các điều kiện không mâu thuẫn

### Với bộ đếm `size`

Bất biến ban đầu là `size = 0`, `0 ≤ head < C`. `enqueue` chỉ chạy khi `size < C` và tăng `size` một đơn vị; `dequeue` chỉ chạy khi `size > 0` và giảm `size` một đơn vị. Do đó luôn có:

```text
0 <= size <= C

size == 0 ⇔ rỗng
size == C ⇔ đầy
```

Hai điều kiện rỗng và đầy không thể cùng đúng vì `C > 0`.

### Với cách chừa một ô

Số phần tử logic nằm trong khoảng `0` đến `C - 1`; `tail` luôn ở ô chưa sử dụng. Nếu `tail == head` thì không có phần tử nào. Nếu `next(tail) == head` thì thêm một phần tử nữa sẽ khiến `tail` đuổi kịp `head`, làm mất khả năng phân biệt rỗng, nên thao tác thêm phải bị từ chối.

Với `C >= 2`, trạng thái `head == tail` và `next(tail) == head` không thể xảy ra đồng thời. Điều này tạo ra hai điều kiện kiểm tra tách biệt.

### Với cờ `full`

Ban đầu `head == tail` và `full == False`. Sau mỗi enqueue thành công, ta cập nhật cờ bằng việc kiểm tra chỉ số ghi mới có bằng chỉ số đọc hay không; nếu bằng, hàng vừa đầy. Sau mỗi dequeue thành công, hàng không còn đầy, nên cờ trở thành `False`. Vì vậy, khi hai chỉ số trùng nhau, **cờ đầy** xác định chính xác trường hợp nào đang xảy ra.

Cả ba lập luận đều dựa trên việc **không thực hiện enqueue vào hàng đầy** và **không thực hiện dequeue từ hàng rỗng** trong các phiên bản có chính sách báo lỗi.

## 11. Lỗi triển khai thường gặp

| Lỗi | Biểu hiện | Cách tránh |
|---|---|---|
| Xem `head == tail` luôn là rỗng nhưng vẫn sử dụng cả `C` ô | Sau khi thêm đủ `C` phần tử, hàng “biến mất” | Chọn bộ đếm, cờ, hoặc chừa một ô thật sự |
| Nhầm `tail` là ô chứa phần tử cuối | Ghi trùng ô hoặc bỏ trống sai chỗ | Tài liệu hóa `tail` là **ô ghi tiếp** |
| Với cách chừa một ô, cho phép thêm đến `C` phần tử | `head == tail` dù còn dữ liệu | Giới hạn mức sử dụng **`C - 1`** |
| Quên tăng/giảm `size` | Báo đầy/rỗng sai, ghi đè dữ liệu | Kiểm tra `0 ≤ size ≤ C` sau mỗi thao tác |
| Quên bỏ cờ `full` sau dequeue | Từ chối thêm mặc dù đã có chỗ | Đặt `full = False` sau mỗi lần lấy thành công |
| Thử `data[head] is None` để kiểm tra rỗng | Nhầm giá trị `None` hợp lệ | Xác định trạng thái bằng metadata |
| Quên phép `% C` khi tiến chỉ số | Đọc hoặc ghi ra ngoài mảng | Dùng `(index + 1) % C` với `C > 0` |
| Không kiểm tra `C = 1` | Cách chừa một ô có sức chứa bằng 0 | Yêu cầu `C >= 2` khi dùng phương án đó |
| Không quy định chính sách khi đầy | Vô tình ghi đè dữ liệu chưa đọc | Chọn từ chối, chờ, mở rộng hoặc ghi đè có chủ đích |

Để phát hiện lỗi, nên truy vết **bốn thời điểm**: vừa khởi tạo, vừa thêm phần tử đầu tiên, vừa đạt sức chứa hữu dụng, và vừa lấy phần tử cuối cùng. Lặp lại chuỗi ấy nhiều vòng để chắc rằng các chỉ số quay về đầu mà bất biến vẫn đúng.

## 12. Bài tập tự kiểm tra

**Bài 1.** Với mảng `C = 5`, `head = 2` và `tail = 2`, hãy cho biết trạng thái hàng theo ba phương án.

*Lời giải:* Với **bộ đếm**, cần xem `size`: `0` là rỗng, `5` là đầy. Với **chừa một ô**, `head == tail` là rỗng. Với **cờ**, cần xem `full`: `False` là rỗng, `True` là đầy.

**Bài 2.** Bộ đệm chừa một ô có `C = 8`. Hàng chứa tối đa bao nhiêu phần tử? Điều kiện nào báo đầy?

*Lời giải:* Tối đa **7 phần tử**. Đầy khi `(tail + 1) % 8 == head`.

**Bài 3.** Trong cách lưu `size`, có `C = 4`, `head = 3`, `size = 3`. Phần tử mới được ghi tại chỉ số nào? Sau khi thêm, `head` có đổi không?

*Lời giải:* `(3 + 3) % 4 = 2`. Sau khi thêm, `size = 4` và `head` vẫn là `3`; hàng đầy.

**Bài 4.** Với cờ `full`, sau khi thêm vừa đủ `C` phần tử thì hai chỉ số bằng nhau và cờ bật. Nếu dequeue thành công đúng một lần, cờ phải là gì?

*Lời giải:* **`False`**, vì đã giải phóng một ô. Nếu `C = 1` thì sau dequeue, hai chỉ số vẫn bằng nhau nhưng cờ tắt và hàng rỗng.

**Bài 5.** Tại sao không nên dùng điều kiện `data[head] == None` để quyết định một queue rỗng?

*Lời giải:* `None` có thể là **giá trị phần tử hợp lệ**; hơn nữa, một ô không thuộc dãy logic có thể vẫn chứa giá trị cũ nếu không được dọn. Chỉ metadata về số lượng hoặc các chỉ số/cờ theo quy ước mới xác định chính xác trạng thái.

**Bài 6.** Một ứng dụng cần giữ tối đa 100 mẫu dữ liệu chưa đọc và dùng phương án chừa một ô. Cần cấp phát bao nhiêu ô vật lý?

*Lời giải:* **101 ô**, vì sức chứa hữu dụng bằng `C - 1`. Nếu dùng phương án bộ đếm hoặc cờ đầy, 100 ô vật lý đủ để giữ 100 mẫu.

Điều quan trọng là **“rỗng” và “đầy” được quyết định bởi bất biến của cách biểu diễn, không phải hình dạng hai chỉ số riêng lẻ**. Với mảng vòng, hãy chọn trước một quy ước rõ ràng — lưu `size`, chừa một ô hoặc lưu cờ `full` — rồi để mọi phép thêm, lấy và kiểm tra tuân thủ đúng quy ước ấy.
