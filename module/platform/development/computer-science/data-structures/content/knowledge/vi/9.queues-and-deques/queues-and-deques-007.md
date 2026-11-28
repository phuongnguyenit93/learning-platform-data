# Mở rộng hàng đợi vòng và sắp xếp lại phần tử khi sao chép

**Hàng đợi vòng** (*circular queue*) dùng một mảng và các chỉ số quay vòng để thêm ở cuối, lấy ở đầu mà không phải dịch các phần tử sau mỗi lần `dequeue()`. Với sức chứa cố định, `enqueue()` không thể tiếp tục khi mảng đầy. Một cách mở rộng là **cấp phát mảng lớn hơn và sao chép những phần tử còn trong hàng theo đúng thứ tự FIFO**. Đây chính là bước cần chú ý: thứ tự logic có thể bắt đầu ở giữa mảng cũ và quay về đầu, nên việc chép nguyên mảng theo chỉ số vật lý dễ khiến hàng đợi bị đảo thứ tự.

Bài thuộc chương **Hàng đợi và deque** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Trong lộ trình học cấu trúc dữ liệu từ mảng, danh sách liên kết, stack, queue đến bảng băm, cây, heap và đồ thị, mục tiêu là nắm bất biến, thao tác và độ phức tạp về thời gian, bộ nhớ để chọn cấu trúc phù hợp. Trọng tâm bài này là **khi nào cần tăng sức chứa, sao chép thế nào để giữ FIFO, cập nhật lại chỉ số ra sao và tại sao `enqueue()` vẫn có độ phức tạp O(1) khấu hao** dù đôi lúc phải sao chép O(n) phần tử.

## 1. Vì sao hàng đợi vòng cần mở rộng?

Giả sử ta cài đặt queue bằng một mảng `data` có `C` ô:

- `head`: chỉ số vật lý của phần tử sẽ được lấy ra tiếp theo, nếu hàng không rỗng.
- `size`: số phần tử hiện có, thỏa mãn `0 ≤ size ≤ C`.
- `C = len(data)`: số ô đã cấp phát, tức **sức chứa vật lý**.

Phần tử thứ `j` trong thứ tự logic từ đầu hàng, với `0 ≤ j < size`, nằm tại:

```text
physical_index(j) = (head + j) % C
```

Vị trí thêm mới khi còn chỗ là:

```text
write_index = (head + size) % C
```

Nhờ phép lấy dư `%`, chỉ số được quay về `0` khi đi hết mảng. Các phép thêm/lấy thông thường có thể thực hiện bằng cách sửa một ô và một vài biến trạng thái, trong **O(1)**.

Tuy nhiên, khi `size == C`, tất cả các ô đã được sử dụng. Nếu bài toán không có giới hạn cứng về số phần tử chờ, ta có thể tăng sức chứa thay vì báo lỗi đầy. Ví dụ:

```text
Sức chứa 4:

             head
               |
               v
Mảng vật lý:  [A] [B] [C] [D]
size = 4
Hàng logic:    A → B → C → D

enqueue(E) → cần chỗ lưu thứ 5.
```

**Mở rộng mảng** là thao tác cấp phát một mảng vật lý mới có nhiều ô hơn, chuyển các phần tử hợp lệ sang đó, sau đó tiếp tục thêm phần tử `E`. Mỗi lần mở rộng có thể tốn O(n), nhưng nếu tăng dung lượng theo một chiến lược hợp lý, chi phí trung bình trên một chuỗi thao tác vẫn thấp.

## 2. Phân biệt thứ tự vật lý với thứ tự FIFO

Khi `head == 0` và các phần tử nằm liên tiếp, sao chép `data[0]`, `data[1]`, … có vẻ hợp lý. Nhưng sau các lần `dequeue()` và `enqueue()`, thứ tự logic thường **vắt qua ranh giới cuối mảng**.

Xét mảng `C = 5` với trạng thái:

```text
Chỉ số vật lý:     0     1     2     3     4
                 +-----+-----+-----+-----+-----+
data:            |  F  |  G  |  C  |  D  |  E  |
                 +-----+-----+-----+-----+-----+
                               ↑
                            head = 2

size = 5, C = 5 → đầy
```

Để có trạng thái này, ta có thể thực hiện:

1. `enqueue(A)`, `enqueue(B)`, `enqueue(C)`, `enqueue(D)`, `enqueue(E)`.
2. `dequeue()` hai lần, trả lần lượt `A` và `B`. Lúc này `head = 2`, `size = 3`.
3. `enqueue(F)` vào ô `0`, rồi `enqueue(G)` vào ô `1`.

Mảng vật lý là `[F, G, C, D, E]`, **nhưng thứ tự FIFO phải là**:

```text
Đường đọc theo chỉ số logic:

j = 0       1       2       3       4
     ↓       ↓       ↓       ↓       ↓
   ô 2     ô 3     ô 4     ô 0     ô 1
     ↓       ↓       ↓       ↓       ↓
     C   →   D   →   E   →   F   →   G
   front                              rear
```

Nếu sao chép nguyên mảng vật lý sang mảng lớn hơn thành `[F, G, C, D, E, …]` rồi đặt `head = 0`, thao tác `dequeue()` tiếp theo sẽ trả `F`, **sai** vì phần tử đúng phải là `C`.

Đây là lỗi đặc trưng khi mở rộng circular queue: **sao chép theo chỉ số vật lý rồi quên khôi phục thứ tự logic**.

## 3. Nguyên tắc sao chép đúng: bắt đầu từ `head`

Giả sử mảng cũ có sức chứa `C_old`, chỉ số đầu `head_old` và `n = size` phần tử hợp lệ. Cấp phát mảng mới có sức chứa `C_new > C_old`. Ta sao chép:

```text
for j = 0 to n - 1:
    new_data[j] = old_data[(head_old + j) % C_old]
```

Sau khi chép đủ `n` phần tử, đặt:

```text
data = new_data
head = 0
size = n           # Không đổi số phần tử đang chờ
```

Đến đây, các phần tử hợp lệ đã được sắp **liên tiếp từ ô `0` đến ô `n - 1`** trên mảng mới, đúng thứ tự FIFO. Ô thêm mới tiếp theo, nếu sử dụng biến `head + size`, sẽ là:

```text
write_index = (head + size) % C_new
            = n                 vì head = 0 và n < C_new
```

Nếu cách cài đặt giữ biến `tail` mang ý nghĩa **ô sẽ ghi tiếp**, cần đặt `tail = n` sau khi mở rộng (với `n < C_new`). Nếu `tail` được định nghĩa là **ô đang chứa phần tử cuối**, thì đặt `tail = n - 1` với hàng không rỗng. Không nên lấy một công thức áp dụng cho hai quy ước đặt tên khác nhau.

### Minh họa đầy đủ khi mảng đã quay vòng

Quay lại mảng cũ chứa `[F, G, C, D, E]`, `head = 2`, `size = 5`. Giả sử chọn **tăng gấp đôi**, từ `C_old = 5` lên `C_new = 10`.

| Chỉ số logic `j` | Chỉ số cũ `(2 + j) % 5` | Giá trị | Chỉ số mới |
|---:|---:|---|---:|
| 0 | 2 | `C` | 0 |
| 1 | 3 | `D` | 1 |
| 2 | 4 | `E` | 2 |
| 3 | 0 | `F` | 3 |
| 4 | 1 | `G` | 4 |

Mảng mới:

```text
Chỉ số mới:       0     1     2     3     4     5     6     7     8     9
                 +-----+-----+-----+-----+-----+-----+-----+-----+-----+-----+
new_data:        |  C  |  D  |  E  |  F  |  G  |  ·  |  ·  |  ·  |  ·  |  ·  |
                 +-----+-----+-----+-----+-----+-----+-----+-----+-----+-----+
                   ↑                             ↑
                  head = 0                  vị trí thêm tiếp

size = 5, capacity = 10
Thứ tự logic: C → D → E → F → G
```

Sau đó `enqueue(H)` ghi `H` vào ô `5`, tăng `size = 6` và giữ `head = 0`. Kết quả:

```text
[C, D, E, F, G, H, ·, ·, ·, ·]
Thứ tự lấy tiếp theo: C, D, E, F, G, H
```

**Thao tác mở rộng không tự thêm hoặc xóa phần tử nào.** Nó chỉ đổi cách bố trí vật lý. Vì thế sau khi chỉ mở rộng, `size` phải giữ nguyên; chỉ khi `enqueue(H)` thực sự thành công mới tăng `size`.

## 4. Thuật toán mở rộng mảng vòng

Phiên bản dưới đây bắt đầu từ mảng có sức chứa dương, chỉ mở rộng **khi đầy**, và chọn dung lượng mới **gấp đôi** dung lượng cũ:

```text
GROW():
    old_data = data
    old_capacity = length(old_data)
    new_capacity = 2 * old_capacity
    new_data = array(new_capacity)

    for j from 0 to size - 1:
        old_index = (head + j) % old_capacity
        new_data[j] = old_data[old_index]

    data = new_data
    head = 0

ENQUEUE(x):
    if size == length(data):
        GROW()

    write_index = (head + size) % length(data)
    data[write_index] = x
    size += 1
```

Thứ tự xử lý rất quan trọng:

1. **Kiểm tra đầy** theo đúng bất biến `size == capacity`.
2. **Cấp phát mảng lớn hơn** trước khi thay đổi con trỏ hoặc bộ đếm của hàng đợi hiện tại.
3. **Sao chép theo thứ tự logic**, với phép modulo tính theo **sức chứa cũ**, chứ không phải mới.
4. **Chỉ sau khi sao chép hoàn tất**, thay mảng đang dùng và đặt lại `head = 0`.
5. **Thêm phần tử mới** vào cuối hàng vừa mở rộng.

Việc sao chép theo mảng mới và chỉ thay `data`, `head` ở cuối cũng giúp hạn chế nguy cơ để cấu trúc ở trạng thái dang dở nếu **cấp phát hoặc sao chép thất bại**. Trong ví dụ Python với một mảng tham chiếu thông thường, ta chỉ gán tham chiếu giữa các `list`; mã không tự nhân bản đối tượng dữ liệu.

### Vì sao không thể dùng modulo theo dung lượng mới khi đọc mảng cũ?

Nếu `C_old = 5`, `head = 2` và `j = 3`, ô đúng trong mảng cũ là:

```text
(2 + 3) % 5 = 0
```

Nếu nhầm dùng `% 10` vì mảng mới có 10 ô, kết quả là chỉ số `5`, **không tồn tại trong mảng cũ**. Khi lấy từ `old_data`, luôn dùng `old_capacity`; khi tính chỗ ghi ở `new_data`, dùng `new_capacity` hoặc chính `j`.

## 5. Cài đặt Python có thể mở rộng

Lớp sau sử dụng mảng vòng tự mở rộng. Mảng có ít nhất một ô ngay từ đầu; `_head` giữ chỉ số đầu và `_size` giữ số phần tử. Mỗi lần đầy, phương thức `_grow()` cấp phát mảng có sức chứa gấp đôi, sao chép thứ tự logic rồi đặt `_head = 0`.

```python
class DynamicCircularQueue:
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
        old_data = self._data
        old_capacity = len(old_data)
        new_data = [None] * (old_capacity * 2)

        for j in range(self._size):
            old_index = (self._head + j) % old_capacity
            new_data[j] = old_data[old_index]

        # Chỉ công bố trạng thái mới sau khi sao chép hoàn tất.
        self._data = new_data
        self._head = 0

    def enqueue(self, value):
        if self._size == len(self._data):
            self._grow()

        index = (self._head + self._size) % len(self._data)
        self._data[index] = value
        self._size += 1

    def peek(self):
        if self.is_empty():
            raise IndexError("Không thể xem hàng đợi rỗng")
        return self._data[self._head]

    def dequeue(self):
        if self.is_empty():
            raise IndexError("Không thể lấy từ hàng đợi rỗng")

        result = self._data[self._head]
        self._data[self._head] = None  # Bỏ tham chiếu phần tử đã lấy.
        self._head = (self._head + 1) % len(self._data)
        self._size -= 1
        return result

    def to_list(self):
        """Quan sát thứ tự FIFO; duyệt O(n) phần tử."""
        capacity = len(self._data)
        return [
            self._data[(self._head + j) % capacity]
            for j in range(self._size)
        ]


q = DynamicCircularQueue(initial_capacity=5)
for value in ["A", "B", "C", "D", "E"]:
    q.enqueue(value)

assert [q.dequeue(), q.dequeue()] == ["A", "B"]
q.enqueue("F")
q.enqueue("G")

# Mảng vật lý đã quay vòng: [F, G, C, D, E].
assert q._head == 2
assert q._data == ["F", "G", "C", "D", "E"]
assert q.to_list() == ["C", "D", "E", "F", "G"]

q.enqueue("H")  # Đang đầy nên phải mở rộng từ 5 lên 10 ô.
assert q.capacity == 10
assert q._head == 0
assert q.to_list() == ["C", "D", "E", "F", "G", "H"]
assert [q.dequeue() for _ in range(6)] == [
    "C", "D", "E", "F", "G", "H"
]
assert q.is_empty()
```

Trong ví dụ, các trường `_data`, `_head` được đọc trực tiếp ở phần minh họa để kiểm tra **bố trí bên trong**, không phải giao diện khuyến nghị cho mã ứng dụng. Người sử dụng queue thông thường chỉ nên thao tác qua `enqueue`, `dequeue`, `peek` và truy vấn kích thước.

Ở cài đặt này, **`None` có thể là dữ liệu hợp lệ**. Chúng ta kiểm tra hàng rỗng bằng `_size == 0`, không dùng giá trị của ô `_data[_head]` để suy đoán trạng thái. Khi dequeue, việc xóa tham chiếu ở ô cũ giúp đối tượng đã rời hàng không bị queue giữ lại không cần thiết.

### Thử các trường hợp biên

```python
# Sức chứa ban đầu 1: từ lần thêm thứ hai phải tăng thành 2.
small = DynamicCircularQueue(1)
small.enqueue(None)
assert small.capacity == 1
small.enqueue("X")
assert small.capacity == 2
assert small.dequeue() is None
assert small.dequeue() == "X"
assert small.is_empty()

# Hàng rỗng rồi thêm lại, không cần reset head về 0.
small.enqueue("Y")
assert small.dequeue() == "Y"
small.enqueue("Z")
assert small.peek() == "Z"
assert small.dequeue() == "Z"

# Mở rộng nhiều lần vẫn giữ nguyên thứ tự FIFO.
many = DynamicCircularQueue(1)
for value in range(30):
    many.enqueue(value)
assert many.capacity >= 30
assert [many.dequeue() for _ in range(30)] == list(range(30))
assert many.is_empty()
```

Ở `small`, chỉ số `head` có thể nằm khác `0` sau khi hàng đã rỗng. Điều đó vẫn hợp lệ: lần enqueue sau ghi tại `(head + size) % capacity` và FIFO được giữ. Khi một lần mở rộng thực sự xảy ra, thuật toán đặt lại `head = 0` sau khi sắp các phần tử vào đầu mảng mới.

## 6. Chứng minh thao tác mở rộng giữ bất biến FIFO

Định nghĩa dãy logic trước khi mở rộng là:

```text
Q = [q0, q1, ..., q(n-1)]

qj = old_data[(head_old + j) % C_old]
       với 0 <= j < n
```

Trong `_grow()`, với từng `j` trong khoảng `0, 1, …, n - 1`, ta gán:

```text
new_data[j] = qj
```

Sau đó đặt `head_new = 0`, giữ `size_new = n`. Vì `C_new > n`, chỉ số vật lý của phần tử logic thứ `j` trên mảng mới là:

```text
(head_new + j) % C_new
= (0 + j) % C_new
= j
```

Do đó, phần tử đọc theo thứ tự logic mới vẫn là `new_data[j] = qj`. **Mọi phần tử còn chờ giữ nguyên giá trị, số lượng và thứ tự; chỉ vị trí vật lý thay đổi.**

Khi tiếp tục `enqueue(x)`, phần tử mới được ghi tại `new_data[n]` và `size` tăng thành `n + 1`. Dãy queue trở thành:

```text
[q0, q1, ..., q(n-1), x]
```

Đây chính xác là hợp đồng enqueue của hàng đợi FIFO.

### Bất biến cốt lõi cần giữ sau mỗi thao tác

Với sức chứa `C > 0`:

1. `0 ≤ head < C` và `0 ≤ size ≤ C`.
2. Các phần tử đang chờ xuất hiện theo thứ tự `data[(head + j) % C]`, `j` từ `0` đến `size - 1`.
3. Khi enqueue thông thường, chỉ ghi vào ô nằm sau phần tử cuối logic, không ghi đè phần tử chưa được dequeue.
4. Khi dequeue, chỉ lấy phần tử đầu; sau đó `head` tiến một ô theo modulo.
5. Khi mở rộng, `size` **không đổi** và `head` được đưa về `0` **sau khi** đã sao chép từ đầu đến cuối logic.

Nếu chỉ số chèn ở phiên bản dùng `head`/`size` được tính bằng `(head + size) % C`, mọi quy tắc trên có thể kiểm tra trực tiếp.

## 7. Chi phí của lần mở rộng: O(n)

Khi hàng đang chứa `n` phần tử và `size == C`:

- Cấp phát/khởi tạo mảng mới có `C_new` ô tốn **O(C_new)** trong mô hình mảng khởi tạo các ô.
- Sao chép `n` phần tử từ mảng cũ sang mảng mới tốn **O(n)**.
- Đổi tham chiếu mảng và đặt `head = 0` tốn **O(1)**.
- Thêm phần tử sau khi mở rộng tốn thêm **O(1)**.

Nếu `C_new = 2C` và khi đầy `n = C`, cả hai bước cấp phát và sao chép đều tốn **O(n)**. Vì thế **một lần enqueue gây mở rộng có thời gian O(n)** theo kích thước hàng đợi.

Về bộ nhớ, sau khi mở rộng, mảng mới có sức chứa `2C`, nên queue sử dụng **O(C)** không gian lưu trữ theo sức chứa cũ tính theo hệ số hằng. Trong lúc sao chép, **cả mảng cũ và mảng mới cùng tồn tại**:

```text
Trong lúc mở rộng:
- Mảng cũ: C ô
- Mảng mới: 2C ô
- Tổng ô vật lý tạm thời: 3C
```

Đó vẫn là O(C) theo ký hiệu tiệm cận, nhưng mức bộ nhớ đỉnh quan trọng trong hệ thống có giới hạn RAM. Một lần mở rộng có thể thất bại do không đủ bộ nhớ ngay cả khi mảng mới, xét riêng, chỉ lớn hơn mảng cũ một hệ số.

Cần phân biệt **sao chép tham chiếu** với **sao chép sâu đối tượng**: đoạn mã Python chỉ di chuyển các tham chiếu tới phần tử, không nhân bản nội dung đối tượng. Nếu dùng một cấu trúc lưu giá trị trực tiếp có kích thước lớn, lượng dữ liệu thực tế phải sao chép và thời gian cấp phát có thể khác.

## 8. Vì sao `enqueue` vẫn O(1) khấu hao?

Nếu mảng tăng dung lượng bằng cách **nhân đôi mỗi khi đầy**, các lần mở rộng xảy ra ngày càng thưa. Để thấy điều đó, giả sử sức chứa ban đầu là `1`, chỉ thực hiện enqueue và không dequeue:

| Số phần tử trước lần thêm | Sức chứa trước | Thao tác đặc biệt |
|---:|---:|---|
| 0 | 1 | Thêm ngay |
| 1 | 1 | Mở rộng 1 → 2, sao chép 1 phần tử |
| 2 | 2 | Mở rộng 2 → 4, sao chép 2 phần tử |
| 3 | 4 | Thêm ngay |
| 4 | 4 | Mở rộng 4 → 8, sao chép 4 phần tử |
| 5, 6, 7 | 8 | Thêm ngay |
| 8 | 8 | Mở rộng 8 → 16, sao chép 8 phần tử |

Số phần tử được sao chép trong các lần tăng sức chứa là dãy:

```text
1 + 2 + 4 + 8 + ... + 2^k
= 2^(k+1) - 1
< 2^(k+1)
```

Đây là **cấp số nhân**. Nếu sau `m` lần enqueue, sức chứa cuối cùng là `C_final`, thì với chiến lược nhân đôi từ sức chứa dương cố định:

```text
Tổng số phần tử phải sao chép
  < C_final
  = O(m)         khi sức chứa ban đầu cố định và không thu nhỏ
```

Mỗi enqueue còn có O(1) công việc thông thường. Do đó tổng thời gian của **`m` lần enqueue** là **O(m)** và chi phí **khấu hao cho một enqueue là O(1)**.

Điều này vẫn đúng khi có xen kẽ dequeues, miễn ta **chỉ mở rộng, không thu nhỏ**: để mở rộng đến một mức sức chứa mới, hệ thống phải từng nhận đủ lượng phần tử tương ứng, nên tổng số lần sao chép qua các lần tăng dung lượng vẫn bị chặn bởi một cấp số nhân liên quan đến tổng số lần enqueue. Dequeue thường tốn O(1) mỗi lần.

**O(1) khấu hao không có nghĩa mọi lời gọi enqueue đều chạy O(1).** Một lời gọi đơn lẻ lúc mảng đầy vẫn có thể tốn O(n) vì cần cấp phát và chép dữ liệu.

### Tại sao tăng mỗi lần đúng một ô lại không tốt?

Nếu mở rộng từ `C` thành `C + 1` mỗi khi đầy, các lần thêm liên tiếp sẽ sao chép:

```text
1 + 2 + 3 + ... + (m - 1)
= m(m - 1) / 2
= Θ(m²)
```

Vì thế chi phí khấu hao cho mỗi enqueue có thể lên tới Θ(m) trên chuỗi `m` lần thêm, thay vì O(1). Tăng theo một **hệ số lớn hơn 1**, chẳng hạn gấp đôi, giúp tổng công việc sao chép được kiểm soát.

Một thư viện có thể dùng hệ số tăng khác 2 để cân bằng số lần sao chép và lượng bộ nhớ dư; kết luận O(1) khấu hao dựa vào việc sức chứa tăng theo tỷ lệ đủ lớn khi cần.

## 9. Có nên thu nhỏ mảng khi dequeue?

Sau khi queue từng lớn rồi được lấy gần hết, `size` có thể rất nhỏ trong khi `capacity` vẫn lớn. Ví dụ từng có `1.024` phần tử, sau đó chỉ còn `5`, nhưng mảng vẫn gồm `1.024` ô. Nếu không thu nhỏ, queue vẫn hoạt động đúng và có thể tái sử dụng các ô đã cấp phát.

**Thu nhỏ** (*shrink*) có thể tiết kiệm bộ nhớ nhưng cũng cần cấp phát mảng nhỏ hơn và **sao chép theo thứ tự logic** như khi mở rộng. Khi đó phải bảo đảm sức chứa mới không nhỏ hơn `size`.

Một sai lầm là:

- Vừa rơi xuống dưới 50% dung lượng thì giảm một nửa.
- Vừa tăng vượt 50% dung lượng thì nhân đôi.

Nếu số phần tử dao động quanh ngưỡng, queue có thể liên tục cấp phát/sao chép qua lại, gây **dao động dung lượng** (*thrashing*).

Một chiến lược minh họa là **chỉ thu nhỏ khi `size ≤ capacity / 4`**, giảm dung lượng xuống một nửa nhưng không nhỏ hơn dung lượng tối thiểu; còn mở rộng khi đầy. Hai ngưỡng cách nhau tạo khoảng đệm, giúp giảm các lần thay đổi dung lượng liên tiếp.

```text
Ví dụ về chính sách tùy chọn:

GROW khi size == capacity:
    new_capacity = 2 * capacity

SHRINK khi size <= capacity / 4:
    new_capacity = max(min_capacity, capacity // 2)
    chỉ thực hiện nếu new_capacity >= size
```

Đây là **một lựa chọn thiết kế**, không phải yêu cầu bắt buộc của queue ADT. Muốn chứng minh O(1) khấu hao cho hệ thống vừa mở rộng vừa thu nhỏ, cần phân tích cả hai loại chuyển đổi và cách tách ngưỡng; không thể tự động lấy lập luận chỉ tăng gấp đôi rồi áp dụng nguyên vẹn cho mọi quy tắc thu nhỏ.

Trong ví dụ Python của bài, ta **không thu nhỏ** để giữ logic đơn giản và cho thấy rõ chi phí của thao tác mở rộng.

## 10. Những lỗi thường gặp khi sao chép

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Sao chép `new_data[j] = old_data[j]` rồi đặt `head = 0` | Đảo thứ tự FIFO nếu mảng cũ đã quay vòng | Đọc từ `(old_head + j) % old_capacity` |
| Dùng `% new_capacity` để đọc mảng cũ | Có thể truy cập ngoài mảng cũ hoặc lấy sai ô | Dùng modulo theo **sức chứa cũ** khi đọc |
| Không đặt lại `head` sau khi dồn về ô 0 | Lần dequeue tiếp theo đọc sai phần tử | Đặt `head = 0` sau khi chép xong |
| Lấy `tail` cũ làm ô ghi tiếp sau khi mở rộng | Chèn vào giữa dãy logic hoặc tạo khoảng hở | Nếu `tail` là ô ghi tiếp, đặt `tail = size` |
| Tăng `size` trong vòng sao chép | Đếm trùng các phần tử đã tồn tại | Giữ nguyên `size` trong bước chuyển mảng |
| Sao chép cả những ô đã dequeue | Mang dữ liệu cũ trở lại hàng logic | Chỉ chép đúng `size` phần tử từ `head` |
| Thay `data` bằng mảng mới trước khi sao chép đủ | Có thể mất trạng thái hợp lệ nếu thao tác thất bại | Hoàn tất sao chép rồi mới thay `data` và `head` |
| Quên kiểm tra đầy trước enqueue | Ghi đè phần tử chưa được lấy | Kiểm tra `size == capacity` rồi mở rộng |
| Mở rộng `capacity + 1` mỗi lần | Sao chép liên tục, tổng Θ(m²) cho m lần thêm | Dùng tăng theo hệ số, ví dụ gấp đôi |
| Nghĩ O(1) khấu hao là O(1) trường hợp xấu nhất | Đánh giá thấp độ trễ của một lần mở rộng | Phân biệt thời gian từng lần và cả chuỗi thao tác |
| Không tính bộ nhớ tạm của hai mảng | Không đủ RAM trong đỉnh mở rộng | Dự trù cùng lúc mảng cũ và mảng mới |
| Thu nhỏ và mở rộng với ngưỡng quá sát | Liên tục cấp phát/sao chép khi kích thước dao động | Tách ngưỡng bằng khoảng đệm |

Nếu phát hiện dequeues trả sai thứ tự ngay sau khi tăng dung lượng, hãy in **hai dãy khác nhau**: mảng vật lý và danh sách phần tử logic từ `head`. Chúng có thể không giống nhau trước khi mở rộng, nhưng **dãy logic phải giống hệt nhau trước và sau bước sao chép**.

## 11. Chọn mảng vòng tự mở rộng hay cấu trúc khác?

| Tiêu chí | Mảng vòng cố định | Mảng vòng tự mở rộng | Danh sách liên kết có `head`/`tail` |
|---|---|---|---|
| `enqueue` khi còn chỗ | O(1) | O(1) | O(1) |
| `enqueue` khi đầy | Báo đầy hoặc chờ theo chính sách | Mở rộng, có thể O(n) ở lần đó | Thêm nút O(1) theo mô hình cấp phát |
| `dequeue` | O(1) | O(1) | O(1) |
| Sức chứa | Cố định | Thay đổi theo nhu cầu | Phụ thuộc bộ nhớ có thể cấp phát |
| Bộ nhớ | O(C) | O(C) cho sức chứa hiện tại; có đỉnh sao chép | O(n) nút và tham chiếu |
| Ưu điểm | Dự đoán được giới hạn và chi phí mỗi phép | Không cần đoán trước số phần tử tối đa | Không cần sao chép toàn bộ khi tăng số nút |
| Đánh đổi | Có thể đầy | Một lần tăng có độ trễ O(n) và cần thêm RAM tạm | Cấp phát từng nút, thêm overhead con trỏ |

**Mảng vòng tự mở rộng** hợp lý khi số phần tử chờ biến động, muốn tận dụng cách lưu trữ theo mảng và chấp nhận đôi lúc phải cấp phát/sao chép. Với hệ thống cần giới hạn độ trễ nghiêm ngặt cho từng thao tác, queue sức chứa cố định hoặc một kiến trúc cấp phát khác có thể phù hợp hơn. Nếu cần thao tác thêm/lấy **cả hai đầu**, có thể xây dựng deque trên mảng vòng bằng cách quản lý cả hai phía.

Trong Python, `collections.deque` cung cấp thao tác hiệu quả ở hai đầu và thường là lựa chọn thuận tiện cho hàng đợi FIFO thông thường. Cài đặt thủ công ở bài này nhằm làm rõ **bất biến, ánh xạ chỉ số và phân tích chi phí**, chứ không phải để thay thế mọi triển khai thư viện đã tối ưu.

## 12. Tự luyện theo từng tình huống

**Câu 1.** Mảng cũ có `C = 4`, `head = 3`, `size = 4` và dữ liệu vật lý `[B, C, D, A]`. Hãy xác định thứ tự logic và mảng mới sau khi mở rộng lên 8 ô.

*Đáp án:* Các chỉ số logic lần lượt là `3, 0, 1, 2`, nên thứ tự là `A → B → C → D`. Mảng mới cần là `[A, B, C, D, ·, ·, ·, ·]` và `head_new = 0`.

**Câu 2.** Nếu trước khi mở rộng `head_old = 4`, `C_old = 6` và `size = 6`, phần tử logic thứ `j = 3` nằm ở ô vật lý nào?

*Đáp án:* `(4 + 3) % 6 = 1`. Khi chép, giá trị tại ô `1` của mảng cũ được đặt vào ô `3` của mảng mới.

**Câu 3.** Vì sao không thể giữ `head = 4` sau khi đã chép các phần tử logic vào `new_data[0]`, `new_data[1]`, …?

*Đáp án:* Vì đầu hàng thực tế đã được chuyển về ô `0`. Giữ chỉ số cũ khiến `peek`/`dequeue` truy cập sai vị trí. Cần cập nhật `head = 0` sau sao chép.

**Câu 4.** Lúc mở rộng mảng từ `8` lên `16` ô khi đầy, số phần tử cần sao chép là bao nhiêu và độ phức tạp của lần enqueue gây mở rộng?

*Đáp án:* Cần sao chép **8 phần tử**, cộng việc khởi tạo vùng chứa mới. Chi phí một lần enqueue đó là **O(n)** với `n = 8` phần tử cũ.

**Câu 5.** Vì sao mảng nhân đôi có enqueue O(1) khấu hao nhưng mảng tăng mỗi lần một ô có thể gây Θ(m²) công việc trong m lần thêm?

*Đáp án:* Nhân đôi chỉ sao chép ở các mức dung lượng `1, 2, 4, 8, …`, tổng cấp số nhân O(m). Tăng từng ô sao chép `1 + 2 + … + (m - 1) = Θ(m²)`.

**Câu 6.** Sau khi tăng dung lượng, có nên tăng `size` thêm một lần cho mỗi phần tử đã chép không?

*Đáp án:* **Không.** Sao chép chỉ đổi vị trí lưu trữ, không tạo thêm phần tử logic. `size` chỉ tăng khi enqueue một phần tử mới thành công.

**Câu 7.** Một queue từng có 10.000 phần tử rồi giảm còn 3 phần tử. Cài đặt chỉ mở rộng có nhất thiết phải thu nhỏ ngay không?

*Đáp án:* Không. Giữ dung lượng lớn vẫn đúng và có lợi nếu tải sắp tăng lại. Có thể thiết kế thu nhỏ để tiết kiệm bộ nhớ, nhưng cần một ngưỡng phù hợp và chấp nhận chi phí sao chép.

**Ghi nhớ:** Mở rộng hàng đợi vòng là **chuyển dãy phần tử logic sang một mảng lớn hơn**. Sao chép từ `old_data[(head + j) % old_capacity]` sang `new_data[j]`, đặt lại `head = 0`, giữ nguyên `size` rồi mới thêm phần tử mới. Một lần mở rộng tốn O(n), nhưng khi tăng sức chứa theo hệ số, tổng chi phí qua nhiều lần thêm được kiểm soát, giúp `enqueue` có **O(1) khấu hao** trong khi `dequeue` vẫn **O(1)**.
