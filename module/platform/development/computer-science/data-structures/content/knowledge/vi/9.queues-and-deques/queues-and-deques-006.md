# Bộ đệm có giới hạn: từ chối, chờ hoặc ghi đè dữ liệu

Một hàng đợi (*queue*) thường tuân thủ **FIFO** (*First In, First Out*): phần tử thêm trước được lấy ra trước. Nhưng khi hàng đợi nằm trong một **bộ đệm có giới hạn** (*bounded buffer*) với chỉ `C` vị trí lưu trữ, một câu hỏi quan trọng xuất hiện: **điều gì xảy ra khi phần tử mới đến trong lúc cả `C` vị trí đều đã có dữ liệu?**

Có ba nhóm chính sách phổ biến: **từ chối** yêu cầu thêm, **chờ** đến khi có chỗ trống, hoặc **ghi đè** một phần tử cũ. Cả ba có thể sử dụng cùng một mảng vòng; điểm khác biệt là **hợp đồng khi đầy**, ảnh hưởng trực tiếp đến việc có mất dữ liệu, liệu người gửi có phải chờ và loại ứng dụng nào phù hợp.

Đây là bài thuộc chương **Hàng đợi và deque**, mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Trong lộ trình tìm hiểu mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, chủ đề này giúp rèn cách xác định **bất biến**, mô tả **thao tác** và đánh giá **độ phức tạp thời gian, bộ nhớ** cùng với các yêu cầu thực tế như độ trễ và khả năng chịu tải.

## 1. Hợp đồng cơ bản của bộ đệm có giới hạn

Giả sử hàng đợi đang lưu các phần tử theo thứ tự logic từ đầu đến cuối:

```text
front                                     rear
  |                                        |
  v                                        v
[ A ] → [ B ] → [ C ]              sức chứa C = 3
  ↑
phần tử được lấy tiếp theo
```

Trạng thái lúc này là **đầy**, vì số phần tử `size` bằng sức chứa `C = 3`. Nếu phần tử mới `D` được gửi tới, bộ đệm không thể giữ đồng thời cả bốn phần tử mà vẫn tuân thủ giới hạn ba vị trí.

Các phép toán thường thấy:

| Phép toán | Ý nghĩa | Điều kiện cần xử lý |
|---|---|---|
| `enqueue(x)` / `put(x)` | Đưa `x` vào cuối hàng | Nếu đầy, phải áp dụng chính sách đã chọn |
| `dequeue()` / `get()` | Lấy và loại bỏ phần tử đầu | Nếu rỗng, phải báo rỗng hoặc chờ |
| `peek()` | Xem phần tử đầu mà không lấy ra | Không có phần tử khi rỗng |
| `is_full()` | Kiểm tra đã dùng hết sức chứa hữu dụng | Phụ thuộc cách biểu diễn |
| `is_empty()` | Kiểm tra không còn phần tử | Phụ thuộc cách biểu diễn |
| `size()` | Số phần tử đang chờ | Luôn trong giới hạn cho phép |

Cần phân biệt hai khái niệm:

- **Bộ đệm đầy (*overflow condition*):** không còn chỗ cho phần tử đến; chính sách xử lý có thể từ chối, chờ hoặc loại dữ liệu cũ.
- **Bộ đệm rỗng (*underflow condition*):** không có phần tử để lấy; API có thể báo lỗi, trả trạng thái không có dữ liệu hoặc chờ phần tử mới.

“Đầy” là một trạng thái bình thường của hàng đợi có giới hạn. Đó không tự động là lỗi lập trình; lỗi xảy ra khi cài đặt không tuân thủ chính sách đã công bố hoặc âm thầm làm mất dữ liệu ngoài dự kiến.

## 2. Mô hình mảng vòng và các bất biến

Một cách cài đặt hiệu quả dùng **mảng vòng** (*circular array/ring buffer*), với:

- `data`: mảng vật lý gồm `C` ô, với `C > 0`.
- `head`: chỉ số vật lý của phần tử sẽ được lấy tiếp theo, nếu không rỗng.
- `size`: số phần tử hợp lệ trong hàng, với `0 ≤ size ≤ C`.

Phần tử logic thứ `j` (đếm từ đầu, `0 ≤ j < size`) nằm tại:

```text
physical_index(j) = (head + j) % C
```

Vị trí sẽ ghi **khi còn chỗ** được tính bằng:

```text
write_index = (head + size) % C
```

Khi dequeue thành công, chuyển `head = (head + 1) % C`. Dấu `%` là phép lấy phần dư, giúp chỉ số quay về đầu mảng sau khi vượt qua ô cuối. Không cần dịch các phần tử còn lại.

Các bất biến của cách biểu diễn này là:

1. `C > 0` và `0 ≤ head < C`.
2. `0 ≤ size ≤ C`.
3. **Rỗng** khi và chỉ khi `size == 0`; **đầy** khi và chỉ khi `size == C`.
4. Các phần tử đang chờ được đọc theo thứ tự `data[(head + j) % C]` với `j = 0, 1, …, size - 1`.
5. Không ghi đè lên ô chứa phần tử chưa được lấy ra, **trừ khi chính sách ghi đè đã cho phép chủ động loại phần tử đó**.

Nếu `size = C`, công thức `write_index` sẽ cho ra `head`. Điều này giải thích vì sao **thêm vào hàng đầy mà không kiểm tra** có thể ghi đè ngay phần tử cũ nhất. Đối với chính sách từ chối hoặc chờ, làm vậy là sai hợp đồng.

## 3. Ba chính sách khi bộ đệm đầy

Cùng một trạng thái đầu `[A, B, C]` với `C = 3`, giả sử một yêu cầu `enqueue(D)` xuất hiện:

| Chính sách | Điều xảy ra khi `D` đến | Trạng thái ngay sau quyết định | Số phận của `A` |
|---|---|---|---|
| **Từ chối (reject)** | Không nhận `D`; báo đầy | `[A, B, C]` | Vẫn chờ xử lý |
| **Chờ (block/wait)** | Tạm dừng yêu cầu thêm cho tới khi có chỗ | `[A, B, C]` trong lúc chờ | Vẫn chờ; có thể được consumer lấy ra |
| **Ghi đè cũ nhất (overwrite oldest)** | Loại `A`, nhận `D` | `[B, C, D]` | **Bị loại mà chưa được consumer lấy** |

Nếu producer đang chờ và consumer lấy `A` ra, producer có thể thêm `D`, để lại `[B, C, D]`. Đây cũng là trạng thái cuối của lựa chọn ghi đè, nhưng hai lịch sử rất khác nhau:

- **Chờ:** `A` đã được chuyển tới consumer.
- **Ghi đè:** `A` bị bỏ mà consumer chưa nhận được.

Do đó, **không thể đánh giá chính sách chỉ từ trạng thái cuối**. Ta phải kiểm tra kết quả trả về, khả năng thất thoát dữ liệu và độ trễ của từng thao tác.

## 4. Chính sách từ chối: giữ nguyên dữ liệu đang chờ

**Từ chối** nghĩa là khi đầy, yêu cầu `enqueue(x)` **thất bại ngay** và không làm thay đổi trạng thái hàng đợi. API có thể ném ngoại lệ, trả về `False` hoặc trả một kết quả mang mã `FULL`.

Hợp đồng logic:

```text
TRY_ENQUEUE(x):
    if size == C:
        return FULL               # Không sửa data, head, size

    index = (head + size) % C
    data[index] = x
    size += 1
    return ACCEPTED
```

Ví dụ với `[A, B, C]` và `C = 3`:

```text
try_enqueue(D)  -> FULL
Hàng vẫn là     [A, B, C]
```

Một chính sách từ chối có những tính chất:

- **Không tự mất dữ liệu đã nhận vào hàng:** `A`, `B` và `C` giữ nguyên.
- **Không bảo đảm dữ liệu mới `D` sẽ được xử lý:** bên gửi phải quyết định thử lại, lưu ở nơi khác, báo lỗi hoặc chủ động bỏ.
- **Không chặn producer:** hữu ích khi producer không được phép chờ lâu.
- **Cần tránh vòng lặp thử lại liên tục:** nếu hệ thống đầy, việc retry ngay trong vòng lặp không có khoảng nghỉ có thể làm lãng phí CPU và tạo thêm tải. Nên cân nhắc giới hạn số lần retry, chờ theo tín hiệu hoặc áp dụng backoff.

Một khác biệt quan trọng: **“hệ thống từ chối” không đồng nghĩa “dữ liệu tuyệt đối không mất”**. Nó chỉ giữ nguyên các phần tử **đã được nhận vào bộ đệm**. Nếu ứng dụng bỏ qua kết quả `FULL` và bỏ luôn `D`, dữ liệu mới vẫn mất ở cấp ứng dụng. Đối với tác vụ cần độ tin cậy cao, cần quy tắc xác nhận đã nhận, lưu bền vững hoặc thử lại phù hợp.

### Khi nào chọn từ chối?

- API cần trả lời nhanh và người gọi có thể xử lý lỗi “quá tải”.
- Producer có cơ chế retry, điều tiết lưu lượng hoặc hàng lưu tạm khác.
- Bộ đệm lưu các công việc phải giữ nguyên khi đã được chấp nhận.

## 5. Chính sách chờ: tạo áp lực ngược về producer

**Chờ** (*blocking enqueue*) nghĩa là khi hàng đầy, producer không hoàn tất thao tác thêm ngay. Nó **đợi đến khi consumer lấy ra một phần tử**, rồi mới thêm phần tử mới.

```text
Producer: enqueue(D)
             |
             v
        Hàng có chỗ? --- Có ---> ghi D và hoàn tất
             |
            Không
             |
             v
        Chờ tín hiệu có chỗ
             |
             +------> kiểm tra lại điều kiện
```

Cách làm này tạo **áp lực ngược** (*backpressure*): khi consumer xử lý chậm hơn tốc độ dữ liệu đến, producer phải giảm nhịp do không thể thêm vô hạn vào bộ đệm.

### Đồng bộ hóa đúng khi nhiều luồng

Để chờ có hiệu quả, chỉ viết vòng lặp `while is_full(): pass` là chưa đủ: nó gây **busy waiting**, tiêu tốn CPU và có thể gây tranh chấp tài nguyên. Một hàng đợi chặn đúng nghĩa thường dùng **khóa kết hợp biến điều kiện**, semaphore hoặc cơ chế chờ tương đương.

Giả mã minh họa cho luồng producer và consumer:

```text
PUT_WAIT(x):
    acquire(lock)

    while size == C:
        wait(not_full, lock)    # Nhả lock trong lúc chờ; lấy lại lock khi tỉnh

    write_at_tail(x)
    size += 1
    signal(not_empty)
    release(lock)

GET_WAIT():
    acquire(lock)

    while size == 0:
        wait(not_empty, lock)

    result = remove_at_head()
    size -= 1
    signal(not_full)
    release(lock)
    return result
```

Dùng **`while` để kiểm tra lại điều kiện**, vì một luồng có thể được đánh thức nhưng tình trạng đầy/rỗng đã thay đổi trước lúc nó lấy lại khóa; hệ thống cũng có thể có các lần đánh thức không gắn với việc điều kiện đã thỏa mãn (*spurious wakeups*).

Trong hệ thống thật, nên sử dụng thư viện đồng bộ đã được kiểm chứng. Đoạn giả mã diễn đạt quy tắc, không phải là mã Python chạy trực tiếp.

### Chờ không có nghĩa là chờ mãi mãi

Một API có thể cung cấp thêm:

- **Timeout:** chờ tối đa trong một khoảng rồi báo không thể thêm.
- **Hủy:** ngừng chờ khi yêu cầu, luồng hoặc dịch vụ bị đóng.
- **Chính sách dừng:** xử lý producer đang chờ khi consumer không còn hoạt động.
- **Hành vi không chặn:** có thể có lựa chọn `put_nowait` bên cạnh `put` mặc định chờ.

Nếu producer và consumer chạy **trong cùng một luồng tuần tự**, producer chặn ở `enqueue` trong khi chờ consumer ở phía sau cùng luồng thực hiện `dequeue`, chương trình có thể mắc kẹt. Cơ chế chờ chỉ có ích khi tồn tại **một tác nhân độc lập** có thể giải phóng chỗ hoặc có cơ chế timeout/hủy.

### Python: hàng đợi chặn bằng `queue.Queue`

`queue.Queue(maxsize=C)` của Python hỗ trợ phối hợp nhiều luồng và kiểm soát sức chứa. Chỉ dùng `maxsize` **dương** để biểu thị giới hạn: trong API này, `maxsize=0` nghĩa là **không giới hạn**, không phải bộ đệm chứa 0 phần tử.

```python
from queue import Queue, Full, Empty

q = Queue(maxsize=2)
q.put_nowait("A")
q.put_nowait("B")

try:
    q.put_nowait("C")          # Không còn chỗ: báo Full ngay.
except Full:
    print("Tạm thời quá tải")

assert q.get_nowait() == "A"   # Consumer lấy A, giải phóng một ô.
q.task_done()                  # Báo công việc A đã xử lý xong.

q.put("C", timeout=1)          # Có chỗ nên hoàn tất ngay.
assert q.get_nowait() == "B"
q.task_done()
assert q.get_nowait() == "C"
q.task_done()

q.join()                       # Chờ số công việc chưa hoàn tất về 0.
```

Lệnh `put(item, timeout=1)` **có thể chờ tối đa một giây** rồi ném `Full` nếu không có chỗ; trong ví dụ trên nó không cần chờ vì vừa có một lần `get` thành công. `get()` có thể chặn nếu hàng rỗng; `get_nowait()` ném `Empty` trong trường hợp đó.

Điểm dễ nhầm: **`get()` giải phóng vị trí lưu trữ**; `task_done()` là tín hiệu công việc lấy ra đã xử lý xong, phục vụ cơ chế `join()`. `task_done()` không phải thao tác giải phóng ô lưu trữ trong queue.

### Ví dụ hai luồng chứng minh put có thể phải đợi

```python
from queue import Queue
from threading import Event, Thread

q = Queue(maxsize=1)
q.put_nowait("A")               # Hàng đã đầy.

started = Event()
finished = Event()

def producer():
    started.set()
    q.put("B")                  # Chặn khi A còn trong hàng.
    finished.set()

t = Thread(target=producer)
t.start()
started.wait()

assert not finished.is_set()    # B chưa thể được đưa vào vì A vẫn chiếm ô.
assert q.get_nowait() == "A"    # Lúc này mới có chỗ.
q.task_done()

t.join()
assert finished.is_set()
assert q.get_nowait() == "B"
q.task_done()
q.join()
```

Ví dụ chỉ có một producer và thao tác lấy ở luồng chính; vì `A` chưa được lấy trước kiểm tra, producer không thể hoàn tất việc thêm `B` sớm. Trong ứng dụng, việc quản lý thời gian chờ và dừng luồng vẫn cần một cơ chế rõ ràng để tránh chờ vô hạn.

## 6. Chính sách ghi đè: ưu tiên dữ liệu mới nhất

**Ghi đè phần tử cũ nhất** (*overwrite oldest*) là chính sách khác hẳn hàng đợi bảo toàn toàn bộ phần tử đã nhận. Khi `size == C`, bộ đệm:

1. Xác định phần tử đầu hiện tại, tức **cũ nhất**.
2. Cho phép bỏ phần tử ấy ngay cả khi chưa được consumer lấy.
3. Ghi phần tử mới vào vị trí được giải phóng.
4. Cập nhật `head` để phần tử lâu nhất còn lại trở thành đầu hàng.

Với mảng vòng dùng `head` và `size`, khi đầy thì `write_index = head`, nên có thể làm trực tiếp:

```text
ENQUEUE_OVERWRITE(x):
    if size < C:
        data[(head + size) % C] = x
        size += 1
        return (overwritten=False, removed=None)

    removed = data[head]       # Phần tử cũ nhất bị loại.
    data[head] = x            # Ghi mới ngay lên ô cũ.
    head = (head + 1) % C     # Đầu mới là phần tử cũ thứ hai.
    return (overwritten=True, removed=removed)
```

Giá trị trả về gồm **cờ có ghi đè hay không** và **giá trị bị loại**, giúp người gọi đo lường thất thoát. Tại sao phải trả cả cờ? Vì `None` có thể chính là giá trị bị loại hợp lệ; chỉ trả `None` sẽ không đủ để biết có ghi đè hay không.

### Truy vết mảng vòng khi ghi đè

Giả sử `C = 3`, ban đầu `head = 0` và đã thêm `A, B, C`:

```text
Vật lý       chỉ số: 0    1    2
                    +----+----+----+
                    | A  | B  | C  |
                    +----+----+----+
                      ↑
                    head = 0, size = 3

Thứ tự logic: A → B → C
```

Thêm `D` khi đầy theo chính sách ghi đè:

```text
- Bỏ A tại ô head = 0.
- Ghi D vào ô 0.
- Chuyển head = (0 + 1) % 3 = 1.
- Giữ size = 3.

Vật lý:        [D] [B] [C]
                  ↑
                head = 1

Thứ tự logic: B → C → D
```

Thêm tiếp `E` cũng khi đầy:

```text
- Bỏ B tại ô 1.
- Ghi E vào ô 1.
- Chuyển head = 2.
- Giữ size = 3.

Vật lý:        [D] [E] [C]
                      ↑
                    head = 2

Thứ tự logic: C → D → E
```

Phần tử đang chờ **vẫn được lấy theo FIFO trong nhóm còn giữ lại**, nhưng những phần tử `A` và `B` đã biến mất. Vì vậy, bộ đệm này phù hợp với yêu cầu **“giữ C giá trị mới nhất”** hơn là hàng chờ tác vụ phải xử lý đầy đủ.

### Khi nào ghi đè phù hợp?

- Dữ liệu cảm biến cập nhật liên tục, chỉ cần một khoảng giá trị gần nhất.
- Bộ đệm phục vụ biểu đồ trực tiếp; khi quá tải, các mẫu gần hiện tại có giá trị hơn mẫu rất cũ.
- Lưu bộ lịch sử ngắn (*rolling history*) trong bộ nhớ.

Không nên âm thầm ghi đè các thông điệp mà hệ thống đã hứa sẽ xử lý đầy đủ, chẳng hạn lệnh thanh toán, nhiệm vụ quan trọng hoặc nhật ký cần bảo toàn. Nếu thực sự cho phép mất dữ liệu, **phải công bố rõ chính sách** và cách đo lường dữ liệu bị loại.

## 7. Cài đặt Python: từ chối và ghi đè trên cùng một mảng vòng

Ví dụ sau minh họa hai chính sách **không chặn**. Lớp sử dụng một mảng có sức chứa cố định, `head` và `size`; không phụ thuộc vào nội dung một ô để xác định trạng thái rỗng. Đây là mô hình **dùng tuần tự**, chưa được đồng bộ cho nhiều luồng.

```python
class BoundedRing:
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

    def to_list(self):
        capacity = len(self._data)
        return [
            self._data[(self._head + i) % capacity]
            for i in range(self._size)
        ]

    def enqueue_reject(self, value):
        """Thêm nếu còn chỗ; khi đầy thì không đổi trạng thái."""
        if self.is_full():
            raise OverflowError("Hàng đợi đã đầy")
        capacity = len(self._data)
        write_index = (self._head + self._size) % capacity
        self._data[write_index] = value
        self._size += 1

    def enqueue_overwrite(self, value):
        """Trả (đã_ghi_đè, giá_trị_bị_loại)."""
        if not self.is_full():
            self.enqueue_reject(value)
            return False, None

        removed = self._data[self._head]
        self._data[self._head] = value
        self._head = (self._head + 1) % len(self._data)
        return True, removed

    def peek(self):
        if self.is_empty():
            raise IndexError("Hàng đợi rỗng")
        return self._data[self._head]

    def dequeue(self):
        if self.is_empty():
            raise IndexError("Hàng đợi rỗng")
        value = self._data[self._head]
        self._data[self._head] = None
        self._head = (self._head + 1) % len(self._data)
        self._size -= 1
        return value


# Chính sách từ chối: phần tử đã được nhận luôn giữ nguyên khi đầy.
rejecting = BoundedRing(3)
for item in ["A", "B", "C"]:
    rejecting.enqueue_reject(item)

before = rejecting.to_list()
try:
    rejecting.enqueue_reject("D")
except OverflowError:
    pass

assert before == rejecting.to_list() == ["A", "B", "C"]
assert rejecting.dequeue() == "A"
rejecting.enqueue_reject("D")
assert rejecting.to_list() == ["B", "C", "D"]


# Chính sách ghi đè: giữ ba phần tử mới nhất.
overwriting = BoundedRing(3)
for item in ["A", "B", "C"]:
    overwriting.enqueue_reject(item)

changed, removed = overwriting.enqueue_overwrite("D")
assert (changed, removed) == (True, "A")
assert overwriting.to_list() == ["B", "C", "D"]

changed, removed = overwriting.enqueue_overwrite("E")
assert (changed, removed) == (True, "B")
assert overwriting.to_list() == ["C", "D", "E"]

# Sức chứa 1 và giá trị None đều hoạt động.
single = BoundedRing(1)
single.enqueue_reject(None)
changed, removed = single.enqueue_overwrite("X")
assert changed is True
assert removed is None           # None là dữ liệu bị loại, không phải "không có ghi đè".
assert single.dequeue() == "X"
assert single.is_empty()
```

Ở đây `enqueue_reject` và `enqueue_overwrite` đều thêm trong **O(1)** theo số phần tử đang lưu. Khi đầy, `enqueue_overwrite` chỉ ghi vào một ô và cập nhật một chỉ số; **không dịch mảng**. Việc tạo `to_list()` để quan sát trạng thái mất O(n), nhưng không thuộc chi phí thực thi các phép thêm/lấy.

Nếu ứng dụng cho phép chọn chính sách động, cần giữ hợp đồng API rõ ràng: cùng một lời gọi `enqueue` nhưng thay đổi chế độ có thể biến “được nhận chắc chắn” thành “một phần tử cũ bị loại”. Do đó, nên công bố và kiểm thử chế độ đã chọn, thay vì cho phép hành vi này xảy ra ngầm.

## 8. Bất biến và cách chứng minh các chính sách là nhất quán

Xét mảng vòng có `C > 0`, với trạng thái `(data, head, size)`.

### Từ chối

Nếu `size < C`, enqueue ghi vào ô `(head + size) % C` rồi tăng `size`. Dãy logic mới là dãy cũ nối thêm `x`, nên giữ FIFO.

Nếu `size == C`, thao tác báo đầy và **không cập nhật** `data`, `head`, `size`. Bất biến giữ nguyên. Các phần tử cũ không bị mất do thao tác bị từ chối.

### Chờ

Khi `size == C`, producer **không được phép cập nhật hàng**. Sau khi consumer dequeue thành công, `size` giảm một, tạo chỗ. Producer tỉnh dậy, **kiểm tra lại điều kiện trong vùng đồng bộ** và chỉ sau đó mới thực hiện enqueue theo nhánh còn chỗ. Vì vậy, một thao tác `put` hoàn tất thành công có hành vi như enqueue bình thường.

Nếu hết thời hạn hoặc bị hủy trước khi thêm, API phải thông báo kết quả theo hợp đồng và không giả vờ đã nhận phần tử.

### Ghi đè

Nếu `size < C`, thực hiện enqueue thường. Nếu `size == C`, ghi `x` vào ô `head` chứa phần tử cũ nhất và tăng `head` một bước vòng; `size` vẫn bằng `C`.

Giả sử dãy trước thao tác là `[q₀, q₁, …, q₍C₋₁₎]`. Sau khi ghi đè, dãy logic là:

```text
[q₁, q₂, …, q₍C₋₁₎, x]
```

Thứ tự giữa các phần tử **còn được giữ lại** không thay đổi. Bất biến về giới hạn `0 ≤ size ≤ C` và vị trí logic vẫn đúng. Nhưng hợp đồng phải chấp nhận việc loại `q₀` chưa được consumer lấy; đó là sự khác biệt có chủ ý so với FIFO không mất dữ liệu.

## 9. Thời gian O(1) không có nghĩa độ trễ giống nhau

Với mảng vòng sức chứa cố định, thao tác thành công cần một lượng xử lý hằng số:

| Chính sách | Công việc tính toán khi thêm thành công | Thời gian chờ của người gửi | Nguy cơ mất dữ liệu |
|---|---|---|---|
| Từ chối | O(1) | Không chặn; trả lỗi đầy ngay | Phần tử **mới** không được nhận nếu caller không thử lại |
| Chờ | O(1) khi đã có chỗ, cộng chi phí đồng bộ | Có thể dài hoặc vô hạn nếu không có timeout/hủy | Không tự bỏ phần tử đã nhận, nhưng producer có thể timeout |
| Ghi đè cũ nhất | O(1) | Không chặn do đầy trong mô hình tuần tự | **Phần tử cũ nhất chưa được tiêu thụ có thể mất** |

**Độ phức tạp tính toán** và **độ trễ thực tế** là hai đại lượng khác nhau. Với chính sách chờ, phần cập nhật mảng chỉ tốn O(1), nhưng lời gọi `put` có thể chờ lâu vì consumer chưa tạo chỗ. Do đó không thể mô tả thời gian phản hồi toàn bộ thao tác chờ là “O(1) và luôn nhanh”.

Mọi chính sách vẫn cần mảng `C` ô, nên **bộ nhớ lưu trữ O(C)** và các trường trạng thái bổ sung chỉ tốn O(1). Nếu ứng dụng cần lưu dữ liệu từ chối ở nơi khác hoặc triển khai hàng chờ nhiều tầng, chi phí của **toàn hệ thống** có thể lớn hơn kích thước bộ đệm này.

### Tải đến và tốc độ xử lý

Gọi `λ` là tốc độ dữ liệu đến trung bình và `μ` là tốc độ consumer lấy dữ liệu ra, cùng đơn vị phần tử/giây.

- Khi `λ < μ` trong điều kiện thích hợp, consumer thường có khả năng theo kịp đầu vào.
- Nếu trong một giai đoạn dài `λ > μ`, bộ đệm hữu hạn sẽ có xu hướng đầy, bất kể mỗi lần enqueue/dequeue chỉ O(1).
- Khi đầy, **từ chối** chuyển tải quá mức thành lỗi; **chờ** lan áp lực ngược tới producer; **ghi đè** giữ tốc độ nhận dữ liệu mới bằng cách bỏ dữ liệu cũ.

Ví dụ, bộ đệm ban đầu rỗng có `C = 100`, luồng đến ổn định khoảng **120 phần tử/giây** và consumer xử lý khoảng **100 phần tử/giây**. Nếu hai tốc độ giữ ổn định, mức tích lũy xấp xỉ **20 phần tử/giây**, nên có thể đầy sau khoảng **100 / 20 = 5 giây**. Đây chỉ là mô hình gần đúng với tốc độ cố định; lưu lượng đột biến, lịch luồng và việc consumer tạm dừng có thể làm thời điểm đầy khác đi.

Tăng `C` có thể **hấp thụ một đợt tăng tải ngắn**, nhưng không giải quyết tình trạng tốc độ đến vượt quá tốc độ xử lý lâu dài. Để xử lý bền vững còn cần kiểm soát tải hoặc tăng năng lực xử lý.

## 10. Chọn chính sách theo yêu cầu nghiệp vụ

| Tình huống | Lựa chọn thường hợp lý | Lý do |
|---|---|---|
| Yêu cầu API có thể trả mã “quá tải” | **Từ chối** kèm retry/backoff hợp lý | Phản hồi nhanh; caller biết yêu cầu chưa được nhận |
| Công việc cần xử lý đầy đủ, producer có thể đợi | **Chờ** với timeout/hủy | Tạo backpressure; không chủ động bỏ việc đã nhận |
| Dữ liệu cảm biến, biểu đồ thời gian thực chỉ cần mẫu mới nhất | **Ghi đè cũ nhất** | Ưu tiên dữ liệu gần hiện tại; chấp nhận mất mẫu cũ |
| Tác vụ thanh toán hoặc thông điệp đã cam kết xử lý | Từ chối an toàn hoặc chờ, kết hợp cơ chế lưu bền vững khi cần | Cần nhận biết thất bại và tránh âm thầm mất dữ liệu |
| Hệ thống giám sát trạng thái mới nhất | Có thể ghi đè với bộ đếm số mẫu bị loại | Giá trị gần hiện tại có ích hơn lịch sử quá cũ |

Chọn **một chính sách cho mỗi loại dữ liệu**, dựa trên điều gì quan trọng hơn: tính đầy đủ của dữ liệu, thời gian phản hồi producer, hay độ mới của dữ liệu tiêu thụ. Có thể kết hợp chính sách ở các tầng khác nhau, nhưng lúc đó cần nói rõ nơi nào xác nhận tiếp nhận và nơi nào có thể bỏ dữ liệu.

### Các chỉ số nên quan sát khi chạy thực tế

- **Độ sâu hàng đợi (`size`)** và mức sử dụng `size / C`: đánh giá áp lực lên bộ đệm.
- **Số lần từ chối:** cho biết producer gặp tình trạng đầy với chính sách reject.
- **Số phần tử bị ghi đè:** giúp thấy mức mất dữ liệu thực sự.
- **Thời gian chờ enqueue:** nhất là các giá trị lớn, timeout và số producer đang chờ.
- **Tốc độ thêm và lấy:** giúp phân biệt lỗi giới hạn sức chứa với tình trạng consumer xử lý không theo kịp.
- **Tuổi dữ liệu khi được lấy ra:** cho biết độ trễ tích lũy dù hàng chưa đầy.

Không chỉ nhìn phần trăm bộ nhớ đã sử dụng. Một bộ đệm luôn đầy có thể là hành vi có chủ đích ở chế độ “giữ C mẫu mới nhất”, trong khi với hàng đợi yêu cầu nghiệp vụ, trạng thái đầy liên tục có thể báo hiệu nghẽn xử lý.

## 11. Các lỗi dễ mắc khi triển khai

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Không kiểm tra đầy trước enqueue thường | Ghi đè phần tử cũ dù API hứa không mất dữ liệu | Kiểm tra `size == C` trước khi ghi |
| Trả về thành công khi từ chối | Caller tưởng dữ liệu đã được nhận | Trả ngoại lệ/mã FULL rõ ràng |
| Với ghi đè, tăng `size` khi đã đầy | Vi phạm `size ≤ C`, tính vị trí sai | Giữ `size = C`, tiến `head` |
| Với ghi đè, quên tiến `head` | Đảo thứ tự logic, có thể đọc phần tử mới trước | Sau ghi tại đầu cũ, tiến đầu một vị trí |
| Coi `None` trong ô là dấu hiệu rỗng | Nhầm dữ liệu hợp lệ với trạng thái | Kiểm tra bộ đếm hoặc metadata |
| Chờ bằng vòng lặp liên tục không đồng bộ | Tốn CPU, nguy cơ tranh chấp | Dùng điều kiện/semaphore/queue thư viện |
| Chỉ dùng `if` sau đánh thức luồng | Tiếp tục dù hàng vẫn đầy do luồng khác đã chiếm chỗ | Kiểm tra điều kiện trong vòng `while` |
| Giữ khóa trong lúc chờ mà không nhả khóa | Consumer không thể lấy dữ liệu để giải phóng ô | Dùng cơ chế wait nhả/tái chiếm khóa đúng cách |
| Chờ không timeout, không có consumer hoạt động | Producer treo vô hạn | Quy định timeout, hủy và xử lý shutdown |
| Dựa vào `q.full()` rồi mới `q.put()` trong nhiều luồng | Trạng thái có thể thay đổi giữa kiểm tra và ghi | Dùng thao tác put đồng bộ/không chặn có báo lỗi |
| Ghi đè mà không đo số phần tử mất | Hệ thống trông như hoạt động bình thường nhưng mất mẫu | Đếm, báo cáo hoặc lưu dấu lần ghi đè |
| Tưởng FIFO bảo đảm hoàn tất đúng thứ tự | Xử lý song song có thể hoàn tất khác thứ tự lấy | Phân biệt thứ tự dequeue và thứ tự hoàn thành |

Một bộ đệm vòng là cấu trúc dữ liệu đơn giản, nhưng việc **chờ** và **ghi đè** thay đổi cách ứng dụng tương tác với nó. Hãy kiểm thử cả hành vi **khi đầy**, **khi rỗng** và **sau nhiều lần chỉ số quay vòng**.

## 12. Tự kiểm tra hiểu biết

**Câu 1.** Bộ đệm có `C = 3` đang chứa `[A, B, C]`. Producer gửi `D` khi áp dụng chính sách từ chối. Kết quả nào đúng?

*Lời giải:* `D` bị từ chối và hàng vẫn là `[A, B, C]`. Các phần tử đã được nhận giữ nguyên. Nếu ứng dụng cần xử lý `D`, phía producer phải tự quyết định retry, lưu lại hoặc báo lỗi.

**Câu 2.** Vẫn với `[A, B, C]`, nếu dùng chính sách ghi đè phần tử cũ nhất thì điều gì xảy ra khi thêm `D` và tiếp tục thêm `E`?

*Lời giải:* Thêm `D` loại `A`, tạo `[B, C, D]`. Thêm `E` loại `B`, tạo `[C, D, E]`. Phần tử tiếp theo consumer lấy là `C`.

**Câu 3.** Producer đang chờ enqueue `D` vào hàng đầy `[A, B, C]`. Consumer lấy `A` thành công. Trạng thái có thể trở thành gì nếu producer thức dậy và thêm `D` thành công?

*Lời giải:* Sau khi consumer lấy `A`, hàng là `[B, C]`; thêm `D` trở thành `[B, C, D]`. Không có phần tử cũ nào bị loại do chính sách overwrite; `A` đã được consumer nhận.

**Câu 4.** Một tác vụ cần giữ mọi lệnh đã tiếp nhận và không được bỏ lệnh cũ âm thầm. Trong ba chính sách, chính sách nào không phù hợp nếu thiếu cơ chế bảo đảm bổ sung?

*Lời giải:* **Ghi đè cũ nhất**, vì nó loại dữ liệu đã vào hàng nhưng chưa được consumer lấy. Từ chối có báo lỗi hoặc chờ có timeout có thể phù hợp hơn; nếu cần bảo đảm vượt qua sự cố hệ thống, phải xét cả lưu trữ bền vững và xác nhận xử lý.

**Câu 5.** Một hàng đợi có `C = 1` chứa giá trị `None` hợp lệ. Sau `enqueue_overwrite("X")`, tại sao việc trả `None` đơn lẻ không đủ báo trạng thái?

*Lời giải:* `None` là **giá trị bị loại** trong lần ghi đè, nhưng cũng có thể được dùng để báo “không có phần tử nào bị loại”. Cần trả thêm cờ, ví dụ `(True, None)`.

**Câu 6.** Vì sao mảng vòng với enqueue/dequeue O(1) vẫn có thể khiến producer chờ lâu?

*Lời giải:* O(1) chỉ mô tả số bước **cập nhật cấu trúc**. Chính sách chờ yêu cầu producer đợi consumer giải phóng vị trí; thời gian này phụ thuộc vào tải, tiến độ consumer và đồng bộ, không bị chặn trên bởi O(1) theo độ dài hàng đợi.

**Câu 7.** Tốc độ dữ liệu đến luôn cao hơn tốc độ xử lý. Tăng sức chứa có giải quyết được tình trạng quá tải vĩnh viễn không?

*Lời giải:* **Không.** Tăng sức chứa chỉ kéo dài thời gian trước khi đầy. Cần giảm tốc độ đưa vào, tăng năng lực tiêu thụ, hoặc chấp nhận loại dữ liệu theo chính sách được thiết kế.

**Ghi nhớ:** Bộ đệm có giới hạn luôn cần quyết định **phải làm gì khi hết chỗ**. **Từ chối** giữ nguyên dữ liệu đã nhận và trả thất bại cho producer; **chờ** tạo backpressure để producer đợi consumer; **ghi đè** giữ dữ liệu mới bằng cách chủ động bỏ dữ liệu cũ nhất. Việc lựa chọn phụ thuộc vào yêu cầu không mất dữ liệu, độ trễ và tính mới của thông tin, bên cạnh độ phức tạp O(1) của các phép toán trên mảng vòng.
