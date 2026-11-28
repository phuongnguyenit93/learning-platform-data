# Đếm phép so sánh, lần cấp phát và lượng bộ nhớ bên cạnh đo thời gian

Khi đánh giá một cấu trúc dữ liệu, chỉ biết “chạy mất 20 ms” thường chưa đủ để giải thích **vì sao** nó nhanh hoặc chậm. Hai cách cài đặt có thể có thời gian gần nhau trên dữ liệu nhỏ nhưng thực hiện số phép so sánh khác nhau rất nhiều. Một thuật toán có ít phép so sánh lại có thể tạo hàng nghìn đối tượng, kích hoạt thu gom rác hoặc sử dụng lượng bộ nhớ lớn hơn phương án còn lại.

Trong phần **Kiểm chứng và thực hành** của học phần cấu trúc dữ liệu, ta sẽ đo đồng thời những góc nhìn bổ sung cho nhau:

1. **Thời gian:** thao tác hoặc toàn bộ workload mất bao lâu?
2. **Số phép toán cốt lõi:** có bao nhiêu lần so sánh khóa, băm khóa, chép dữ liệu hoặc duyệt liên kết?
3. **Cấp phát:** khi nào cấu trúc xin thêm vùng nhớ, cấp phát bao nhiêu bộ đệm/nút, có cấp phát lại không?
4. **Bộ nhớ:** bao nhiêu dung lượng đang được giữ, bao nhiêu được dành sẵn và mức đỉnh trong quá trình chạy là bao nhiêu?

Mục đích không phải gom bốn đại lượng thành một điểm số duy nhất, mà dùng chúng để **kiểm tra dự đoán độ phức tạp**, tìm nguyên nhân chênh lệch hiệu năng và chọn cấu trúc dữ liệu theo tải thực tế.

## 1. Vì sao thời gian chạy chưa nói hết câu chuyện?

Giả sử phải hỗ trợ `push(x)` và `pop_min()` của hàng đợi ưu tiên. Ba biểu diễn thường gặp:

| Biểu diễn | `push(x)` | `pop_min()` | Đặc điểm đáng đo |
|---|---|---|---|
| Danh sách không sắp xếp | `O(1)` khấu hao khi thêm cuối mảng động | `O(n)` để tìm nhỏ nhất; xóa có thể kéo theo dịch chuyển | Nhiều so sánh lúc lấy nhỏ nhất |
| Danh sách sắp xếp giảm dần | `O(n)` vì cần chèn vào vị trí và dịch phần tử | `O(1)` khi lấy ở cuối | Chi phí chuyển sang pha thêm |
| Binary min-heap dạng mảng | `O(log n)` | `O(log n)` | So sánh dọc đường cây, cấp phát khi bộ đệm đầy |

Cả ba có thể trả cùng kết quả, nhưng chi phí xuất hiện ở những thao tác khác nhau. Nếu workload 95% `push` và hiếm khi `pop_min`, kết quả khác workload có số lần thêm/lấy cân bằng.

Thêm vào đó, **số phép so sánh không đồng nghĩa thời gian**. So hai số nguyên khác so hai chuỗi rất dài; một phép so sánh có thể kích hoạt mã người dùng. Trong bảng băm, chi phí hàm băm và kiểm tra bằng nhau cũng quan trọng. Vì vậy, phải đặt số đếm cạnh thời gian thực đo, không dùng nó thay thế hoàn toàn thời gian.

### Bốn loại câu hỏi cần tách bạch

- **Độ phức tạp thuật toán:** số thao tác cốt lõi tăng theo `n` như thế nào?
- **Chi phí triển khai:** mỗi thao tác cốt lõi cần bao nhiêu công việc thực tế của runtime?
- **Chi phí bộ nhớ:** phải giữ bao nhiêu ô, nút và đối tượng trong trạng thái ổn định hoặc lúc tăng dung lượng?
- **Hiệu năng hệ thống:** tổng thời gian còn chịu ảnh hưởng từ cache, GC, bộ cấp phát, CPU và hệ điều hành ra sao?

Ví dụ, phép chèn vào danh sách liên kết đôi có thể là `O(1)` **khi đã có con trỏ đến nút thích hợp**, nhưng tìm vị trí chèn bằng cách duyệt từ đầu có thể là `O(n)`. Chỉ đếm lần thay liên kết mà bỏ qua phần tìm kiếm sẽ gây hiểu nhầm.

## 2. Quy định chính xác thứ được đếm

Một bộ đếm chỉ có giá trị khi **định nghĩa đo lường** rõ ràng.

| Đại lượng | Một định nghĩa có thể dùng | Không nên hiểu nhầm là |
|---|---|---|
| `key_comparisons` | Mỗi lần thuật toán so thứ tự hai khóa (`<`, `<=`, `>`, ...) được thiết kế để chọn nhánh | Tổng mọi phép so sánh của CPU hoặc mọi điều kiện `if` |
| `hash_calls` | Mỗi lần cài đặt chủ động gọi hàm băm khóa | Số probe hay số lần so khóa trong toàn bộ bảng băm |
| `slot_writes` | Mỗi lần ghi vào một ô lưu trữ của cấu trúc do ta kiểm soát | Số byte thực ghi bởi phần cứng |
| `resize_copies` | Mỗi phần tử logic được sao chép sang bộ đệm mới khi tăng dung lượng | Tổng mọi dịch chuyển và sao chép do runtime thực hiện |
| `buffer_allocations` | Mỗi lần mã của ta tạo một bộ đệm lưu trữ mới | Số lệnh cấp phát mà trình thông dịch hoặc bộ cấp phát thực hiện |
| `node_allocations` | Mỗi nút mới được tạo theo mô hình cấu trúc | Số lần xin bộ nhớ từ hệ điều hành |
| `reserved_slots` | Số ô tham chiếu đã dành sẵn trong các bộ đệm đang sống theo mô hình | Tổng số byte RAM đã sử dụng |
| `peak_traced_bytes` | Đỉnh cấp phát được công cụ đo bộ nhớ theo dõi trong pha đo | RSS hoặc bộ nhớ toàn tiến trình |

Cần quyết định thêm: tính phép so sánh thất bại hay chỉ thành công? Có tính so với sentinel không? Đếm lời gọi API hay chỉ so sánh **khóa** bên trong thuật toán? Nếu đo `push` và `pop_min` riêng, bộ đếm được reset ở đâu?

**Nguyên tắc:** chọn một quy ước, giữ nguyên giữa các phương án và ghi quy ước trong báo cáo. Nếu phương án A đếm cả so sánh chỉ số còn B chỉ đếm so sánh khóa, hai con số không thể so trực tiếp.

## 3. Xây min-heap có bộ đếm minh bạch

Ta dùng một min-heap dạng mảng dành cho **số nguyên**, cho phép giá trị âm và trùng nhau. Để đếm lần cấp phát theo nghĩa thuật toán, ta **tự quản lý một bộ đệm có dung lượng cố định tại từng thời điểm** rồi nhân đôi khi đầy, thay vì dựa vào chiến lược tăng dung lượng nội bộ của `list.append`.

Các bộ đếm:

- `comparisons`: số lần so sánh thứ tự **hai giá trị của heap** qua `_less`.
- `slot_writes`: số lần ghi một ô trong bộ đệm, bao gồm ghi khi tăng dung lượng.
- `resize_copies`: số giá trị được sao chép từ bộ đệm cũ sang bộ đệm lớn hơn.
- `buffer_allocations`: số lần tạo bộ đệm mảng ở cấp thuật toán, tính cả lần khởi tạo.
- `allocated_slots_total`: tổng số ô của **mọi bộ đệm từng được tạo** trong một vòng đời.
- `peak_reserved_slots`: đỉnh số ô đã dành sẵn ở các bộ đệm đồng thời tồn tại khi resize.

Đây là các đại lượng **mô hình hóa**, không phải số byte hay số lời gọi `malloc` thực tế của Python.

### 3.1. Mã Python đầy đủ

```python
from dataclasses import dataclass


_EMPTY = object()


@dataclass
class HeapMetrics:
    comparisons: int = 0
    slot_writes: int = 0
    resize_copies: int = 0
    buffer_allocations: int = 0
    allocated_slots_total: int = 0
    peak_reserved_slots: int = 0


class InstrumentedMinHeap:
    def __init__(self, initial_capacity: int = 1):
        if initial_capacity < 1:
            raise ValueError("initial_capacity phai >= 1")

        self._data = [_EMPTY] * initial_capacity
        self._size = 0
        self.metrics = HeapMetrics(
            buffer_allocations=1,
            allocated_slots_total=initial_capacity,
            peak_reserved_slots=initial_capacity,
        )

    def __len__(self) -> int:
        return self._size

    def _less(self, a: int, b: int) -> bool:
        # Chi dem so sanh thu tu cua hai phan tu heap.
        self.metrics.comparisons += 1
        return a < b

    def _write(self, index: int, value) -> None:
        self._data[index] = value
        self.metrics.slot_writes += 1

    def _grow(self) -> None:
        old = self._data
        old_capacity = len(old)
        new_capacity = old_capacity * 2
        new = [_EMPTY] * new_capacity

        self.metrics.buffer_allocations += 1
        self.metrics.allocated_slots_total += new_capacity

        # Trong khi sao chep, ca hai bo dem cung ton tai.
        self.metrics.peak_reserved_slots = max(
            self.metrics.peak_reserved_slots,
            old_capacity + new_capacity,
        )

        for i in range(self._size):
            new[i] = old[i]
            self.metrics.slot_writes += 1
            self.metrics.resize_copies += 1

        self._data = new

    def push(self, value: int) -> None:
        if self._size == len(self._data):
            self._grow()

        i = self._size
        self._size += 1
        self._write(i, value)

        # Sift up.
        while i > 0:
            parent = (i - 1) // 2
            if not self._less(self._data[i], self._data[parent]):
                break

            child_value = self._data[i]
            parent_value = self._data[parent]
            self._write(i, parent_value)
            self._write(parent, child_value)
            i = parent

    def peek_min(self) -> int:
        if self._size == 0:
            raise IndexError("heap rong")
        return self._data[0]

    def pop_min(self) -> int:
        if self._size == 0:
            raise IndexError("heap rong")

        result = self._data[0]
        last = self._data[self._size - 1]
        self._write(self._size - 1, _EMPTY)
        self._size -= 1

        if self._size > 0:
            self._write(0, last)
            i = 0

            # Sift down.
            while True:
                left = 2 * i + 1
                if left >= self._size:
                    break

                right = left + 1
                child = left

                if (
                    right < self._size
                    and self._less(self._data[right], self._data[left])
                ):
                    child = right

                if not self._less(self._data[child], self._data[i]):
                    break

                a = self._data[i]
                b = self._data[child]
                self._write(i, b)
                self._write(child, a)
                i = child

        return result

    def snapshot_for_test(self) -> list[int]:
        # Ngoai vung do; sorted co the tu goi phep so sanh.
        return sorted(self._data[:self._size])

    def assert_invariants(self) -> None:
        assert 0 <= self._size <= len(self._data)
        for i in range(self._size):
            assert self._data[i] is not _EMPTY
        for i in range(self._size, len(self._data)):
            assert self._data[i] is _EMPTY
        for i in range(1, self._size):
            assert self._data[(i - 1) // 2] <= self._data[i]
```

Các phương thức kiểm tra và tạo ảnh chụp **cố ý không đi qua `_less` và `_write`**, nhờ đó không làm thay đổi bộ đếm của thuật toán đang được đánh giá. Chúng được gọi **ngoài vùng định thời** trong ví dụ đo dưới đây.

### 3.2. Đếm được những gì?

Khi thêm phần tử mới:

1. Nếu `size == capacity`, heap tạo bộ đệm gấp đôi, tăng `buffer_allocations` và chép toàn bộ phần tử đang hoạt động.
2. Giá trị mới được ghi một lần vào ô cuối.
3. Mỗi cấp của thao tác *sift up* thực hiện tối đa một phép so thứ tự để quyết định có đổi chỗ hay không.
4. Mỗi lần đổi chỗ trong mã này ghi hai ô.

Khi lấy nhỏ nhất:

1. Phần tử cuối được lấy để thay phần tử ở gốc, đồng thời ô cuối được đánh dấu rỗng.
2. Nếu heap còn phần tử, *sift down* chọn con nhỏ hơn (nếu có hai con), rồi so với cha.
3. Mỗi lần đổi chỗ ghi hai ô.

Với heap nhị phân, độ cao là `O(log n)`. Vì vậy số so sánh thứ tự cho **một** `push` hoặc `pop_min` có chặn trên `O(log n)`, dù số lượng cụ thể tùy phân phối giá trị. Việc đếm không thay thế chứng minh bất biến heap; cần kiểm tra thứ tự cha–con và kết quả lấy nhỏ nhất riêng.

### 3.3. Phân biệt “ô đã cấp phát” với “bộ nhớ đang giữ”

Giả sử bắt đầu với dung lượng `1`, rồi mở rộng lần lượt lên `2`, `4`, `8`:

- `buffer_allocations = 4`: một lần khởi tạo và ba lần tạo bộ đệm mới.
- `allocated_slots_total = 1 + 2 + 4 + 8 = 15`: tổng số ô **đã từng được tạo**.
- `reserved_slots = 8` sau khi hoàn tất: dung lượng bộ đệm hiện tại, không phải 15 ô.
- Lúc chuyển từ 4 lên 8, tồn tại đồng thời hai bộ đệm tổng cộng 12 ô; đây là một giá trị có thể dùng để phân tích **đỉnh bộ đệm trong thuật toán**.

Cả 15 và 12 đều là **số ô tham chiếu**, không phải byte RSS. Các đối tượng `int`, đối tượng `list`, metadata, phân bổ của runtime và bộ nhớ đệm của bộ cấp phát nằm ngoài cách đếm này. Ngoài ra, biến `old` chỉ là một tham chiếu tới bộ đệm cũ trong `_grow`; chính sách giải phóng bộ nhớ thực tế phụ thuộc runtime.

**Cảnh báo khi so sánh:** `allocated_slots_total` là đại lượng tích lũy và không giảm khi bộ đệm cũ không còn được dùng. Không dùng nó làm “lượng bộ nhớ đang tiêu thụ” ở thời điểm cuối. Với bộ nhớ đang giữ, phải xem dung lượng hiện tại hoặc công cụ đo thực tế.

## 4. Kết hợp bộ đếm với thời gian chạy trên cùng workload

Để đo có ý nghĩa, hãy chuẩn bị **chuỗi thao tác xác định** bên ngoài vùng định thời. Chuỗi đó phải giữ đúng hợp đồng, có đủ `push`, `pop_min`, giá trị trùng và cả các lần tăng kích thước.

Ví dụ sử dụng hạt giống cố định, tránh `pop_min` khi rỗng trong workload chính:

```python
from random import Random
from time import perf_counter_ns


def generate_operations(seed: int, steps: int):
    rng = Random(seed)
    operations = []
    current_size = 0

    for _ in range(steps):
        # Bias ve push de co luc heap tang dung luong.
        if current_size == 0 or rng.random() < 0.60:
            value = rng.randrange(-100, 101)
            operations.append(("push", value))
            current_size += 1
        else:
            operations.append(("pop_min", None))
            current_size -= 1

    return operations


operations = generate_operations(seed=2026, steps=3000)

heap = InstrumentedMinHeap(initial_capacity=1)
popped = []

start = perf_counter_ns()

for action, value in operations:
    if action == "push":
        heap.push(value)
    else:
        popped.append(heap.pop_min())

elapsed_ns = perf_counter_ns() - start

heap.assert_invariants()  # Ngoai dong ho
stats = heap.metrics

print("Elapsed ns:", elapsed_ns)
print("Key comparisons:", stats.comparisons)
print("Slot writes:", stats.slot_writes)
print("Resizes:", stats.buffer_allocations - 1)
print("Copied on resize:", stats.resize_copies)
print("Allocated slots over lifetime:", stats.allocated_slots_total)
print("Peak concurrent slots (model):", stats.peak_reserved_slots)
print("Current capacity:", len(heap._data))
print("Remaining elements:", len(heap))
```

Ở đây, `elapsed_ns` **bao gồm** chi phí tăng bộ đếm, kiểm tra nhánh và thao tác của Python. Nó đo **phiên bản đã gắn công cụ theo dõi** (*instrumented version*), không phải thời gian nguyên bản của một heap tối ưu không có bộ đếm.

Điều đó không làm bộ đếm vô dụng: số phép so sánh và số lần chép vẫn giúp xác minh xu hướng theo `n`. Nhưng nếu muốn đo tốc độ sản xuất, hãy chạy **một bản không gắn công cụ theo dõi** với cùng dữ liệu, sau khi đã đối chiếu hành vi.

### 4.1. Kiểm tra tính đúng đắn bằng mô hình đơn giản

Kết quả lấy ra phải đúng theo min-priority queue, và số lần xuất hiện của các phần tử còn lại phải được bảo toàn. Ta dùng một danh sách thường làm mô hình độc lập:

```python
reference = []
expected_popped = []

for action, value in operations:
    if action == "push":
        reference.append(value)
    else:
        smallest = min(reference)
        reference.remove(smallest)  # Xoa dung mot ban sao
        expected_popped.append(smallest)

assert popped == expected_popped
assert heap.snapshot_for_test() == sorted(reference)
heap.assert_invariants()
```

Việc đối chiếu mô hình diễn ra sau phép đo thời gian. Với workload lớn hơn, có thể dùng mô hình khác hoặc chạy bộ kiểm thử nhỏ riêng để tránh chi phí `min` và `remove` tuyến tính ảnh hưởng tổng thời gian của thí nghiệm.

Chỉ khi kết quả đúng mới nên so chi phí: một heap bị lỗi trả sai thứ tự và làm thiếu thao tác có thể trông “nhanh” hơn cấu trúc đúng.

### 4.2. Báo số đếm theo đơn vị có ý nghĩa

Không chỉ báo tổng số so sánh. Hãy ghi:

\[
\text{comparisons/op}
=\frac{\text{tổng số so sánh khóa}}{\text{số thao tác có thực hiện}},
\]

và tương tự cho `slot_writes/op`, `resize_copies/push` hoặc `bytes/element` khi có số đo bộ nhớ phù hợp.

Nếu các phép toán có chi phí khác nhau, nên **phân nhóm theo loại**: so sánh trên mỗi `push` khác so sánh trên mỗi `pop_min`. Một workload có 90% `push` sẽ không so trực tiếp được với workload có 90% `pop_min` chỉ bằng tổng `comparisons`.

Bảng báo cáo có thể dùng:

| Quy mô / workload | Thời gian giữa các lượt | So sánh / `push` | So sánh / `pop_min` | Bản sao do resize | Lần tạo bộ đệm | Bộ nhớ đỉnh |
|---|---|---|---|---|---|---|
| `n` nhỏ, 70% thêm | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| `n` vừa, 50/50 | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| `n` lớn, 30% thêm | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |

Không tự điền các con số đo khi chưa chạy thí nghiệm; môi trường, ngôn ngữ, phân phối dữ liệu và cách instrument ảnh hưởng kết quả.

## 5. Đo số lần cấp phát: cấp phát ở cấp thuật toán khác cấp phát thực tế

Một cấu trúc dữ liệu tạo một nút bằng `Node(value)` có thể làm phát sinh nhiều hoạt động bộ nhớ dưới runtime. Ngược lại, bộ cấp phát có thể lấy vùng nhớ từ pool đã dự trữ thay vì gọi hệ điều hành mỗi lần.

Vì vậy, cần phân biệt ba cấp độ:

| Cấp độ | Ví dụ | Cách đo |
|---|---|---|
| **Sự kiện cấp phát logic** | Tạo một nút danh sách, một block, một buffer mới | Bộ đếm do người viết thuật toán đặt tại điểm tạo |
| **Cấp phát của runtime/allocator** | Đối tượng hoặc khối nhớ được cấp phát trong heap của runtime | Profiler/allocator hook tương ứng với ngôn ngữ |
| **Trang nhớ thực / RSS** | Bộ nhớ tiến trình giữ trong RAM theo hệ điều hành | Công cụ hệ điều hành hoặc profiler cấp tiến trình |

Không có hệ số quy đổi cố định từ **số nút** ra **số byte RSS**. Một nút có thể chứa nhiều trường, con trỏ, phần căn chỉnh (*alignment*), header đối tượng và chi phí bộ cấp phát. Bộ nhớ RSS còn bao gồm mã chương trình, runtime, stack và nhiều đối tượng không thuộc cấu trúc.

### Quy tắc instrument một lần tạo nút

Ví dụ một danh sách liên kết đơn:

```python
class CountingLinkedList:
    def __init__(self):
        self.head = None
        self.size = 0
        self.nodes_created = 0

    def push_front(self, value):
        node = {"value": value, "next": self.head}
        self.nodes_created += 1  # Mot nut logic moi
        self.head = node
        self.size += 1
```

`nodes_created` là tổng số nút logic đã tạo trong vòng đời. Nếu sau đó xóa nút và bộ nhớ được giải phóng, biến đếm **không tự giảm**; muốn biết số nút đang sống thì xem `size` (khi bất biến danh sách đúng). Bản Python sử dụng `dict` làm nút nên cấp phát thực tế có thể khác một `struct Node` trong C++; không gọi `nodes_created` là số lần `malloc`.

### Điều kiện đặc biệt: cấu trúc dùng chia sẻ bộ nhớ

Trong cấu trúc **bất biến có chia sẻ** (*persistent data structure*), hai phiên bản có thể cùng tham chiếu nhiều nút. Tổng số nút mà từng phiên bản duyệt được **không bằng** tổng số nút vật lý độc nhất.

Nếu cần đo bộ nhớ của các phiên bản, phải xác định:

- Đếm nút độc nhất theo **định danh đối tượng**, tránh đếm trùng nút được chia sẻ.
- Phân biệt bộ nhớ của một phiên bản riêng với bộ nhớ của **tất cả phiên bản đang sống**.
- Nêu rõ các tham chiếu bên ngoài có còn giữ lại phiên bản cũ hay không.

Các cấu trúc dựa trên arena hoặc object pool cũng cần đo riêng số đối tượng **đang hoạt động**, số ô **đã dự trữ** và số lần thực sự phải tăng arena.

## 6. Đo lượng bộ nhớ bằng công cụ runtime

Trong CPython, `tracemalloc` có thể theo dõi những vùng cấp phát bộ nhớ Python nằm trong phạm vi theo dõi của nó. Hãy đo trong **một lượt riêng** với lượt định thời, vì bật công cụ theo dõi có thể tạo overhead thời gian.

```python
import tracemalloc


def measure_heap_allocations(values):
    # values duoc tao TRUOC thoi diem do.
    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        baseline, _ = tracemalloc.get_traced_memory()

        target = InstrumentedMinHeap(initial_capacity=1)
        for x in values:
            target.push(x)

        current, peak = tracemalloc.get_traced_memory()

        # Giu target song cho den khi da lay du so do.
        return {
            "tracked_retained_delta_bytes": current - baseline,
            "tracked_peak_delta_bytes": peak - baseline,
            "logical_buffer_allocations": target.metrics.buffer_allocations,
            "logical_resize_copies": target.metrics.resize_copies,
            "count": len(target),
        }
    finally:
        tracemalloc.stop()


values = list(range(5000, 0, -1))
result = measure_heap_allocations(values)
assert result["count"] == len(values)
print(result)
```

Đây là **mức chênh lệch cấp phát được theo dõi** từ một mốc trong cùng tiến trình, không phải tổng RAM của tiến trình. Số liệu có thể bao gồm cấp phát phụ của Python trong giai đoạn đo. `tracemalloc` không cung cấp mặc định bộ nhớ của mọi thư viện native hay bộ nhớ GPU; nếu cần RSS hoặc đỉnh vật lý ở hệ điều hành, dùng công cụ bổ sung phù hợp.

Với mảng động, số slot đã cấp phát theo mô hình thường tăng theo dung lượng. Nhưng trong Python, các số nguyên trong `values` đã tồn tại trước phép đo; `target` có thể chỉ giữ **tham chiếu** tới chúng. Không được lấy `len(values) * kích thước_một_int` rồi cho rằng đó là lượng bộ nhớ tăng thêm nếu các đối tượng số nguyên được chia sẻ.

### Ba đại lượng bộ nhớ dễ nhầm lẫn

**Bộ nhớ hữu ích của dữ liệu:** dung lượng để biểu diễn nội dung logic, chẳng hạn `n` khóa và `n` giá trị.

**Bộ nhớ overhead:** mảng chỉ mục, con trỏ, bucket, metadata của nút, dung lượng trống dự phòng và header đối tượng.

**Bộ nhớ đỉnh:** có thể cao hơn đáng kể bộ nhớ cuối cùng khi cấu trúc nhân đôi buffer hoặc tái băm và cần giữ hai vùng nhớ trong thời gian chuyển đổi.

Ví dụ, bảng băm có thể dành nhiều bucket trống để giữ hệ số tải thấp, giúp tra cứu nhanh hơn nhưng tiêu tốn RAM. Nếu tối ưu chỉ thời gian mà không đo số byte giữ lại trên mỗi bản ghi, ta dễ bỏ qua đánh đổi này.

## 7. Đếm phép so sánh cho nhiều cấu trúc khác nhau

Không phải mọi cấu trúc đều có “so sánh khóa” làm phép toán cốt lõi. Cần chọn biến đếm phù hợp với thuật toán:

| Cấu trúc | Sự kiện đáng đếm | Câu hỏi được giải thích |
|---|---|---|
| Mảng / tìm tuyến tính | So sánh giá trị với khóa cần tìm | Có bao nhiêu phần tử được kiểm tra trước khi tìm thấy? |
| Binary search | Số lần so sánh phần tử giữa với khóa | Số bước có tăng theo `log n` khi dữ liệu đã sắp xếp? |
| BST / AVL / Red–Black Tree | So sánh khóa, lần quay, lần sửa chiều cao/màu | Chi phí duy trì cân bằng khi chèn/xóa? |
| Min/Max Heap | So sánh thứ tự, lần hoán đổi/ghi ô | Đường sift có dài theo độ cao heap không? |
| HashMap / Set | Lần gọi hàm băm, probe, so bằng nhau, resize/rehash | Va chạm và hệ số tải ảnh hưởng thao tác thế nào? |
| Danh sách liên kết | Số nút duyệt, thay đổi con trỏ, nút tạo mới | Chi phí tìm vị trí và thao tác liên kết là bao nhiêu? |
| Fenwick Tree | Lần thăm ô, số cập nhật nút, số bước duyệt chỉ số | Mỗi truy vấn/cập nhật có đi qua `O(log n)` nút không? |
| Segment Tree | Số nút cây được thăm, số lần gộp kết quả | Chi phí truy vấn phụ thuộc dạng đoạn và cập nhật ra sao? |
| Đồ thị BFS/DFS | Đỉnh được lấy khỏi cấu trúc chờ, cạnh được xét | Khối lượng thực thi có tương quan với `V + E`? |
| Dijkstra với heap | Số lần relax cạnh, `push`/`pop`, mục nhập lỗi thời | Chi phí tổ hợp của đồ thị và priority queue là gì? |

Với thuật toán đồ thị, chỉ đếm phép so sánh trọng số có thể bỏ qua phần lớn công việc duyệt cạnh. Với HashMap, chỉ đếm `==` mà bỏ qua hàm băm và số lần probe có thể đánh giá sai hiệu quả. **Chọn phép đếm dựa trên nguồn chi phí thực**, không máy móc dùng cùng một counter cho mọi cấu trúc.

### Ví dụ đếm so sánh cho tìm kiếm nhị phân

Mã sau đếm số lần so sánh thứ tự bằng cách dùng **một lần so sánh ba ngả ở mức thuật toán** (dùng hai toán tử khi cần), do đó định nghĩa bộ đếm là **số vị trí giữa đã kiểm tra**, không phải số lần thực thi toán tử Python:

```python
def binary_search_with_steps(items, target):
    left, right = 0, len(items) - 1
    positions_checked = 0

    while left <= right:
        mid = (left + right) // 2
        positions_checked += 1

        if items[mid] == target:
            return mid, positions_checked
        if items[mid] < target:
            left = mid + 1
        else:
            right = mid - 1

    return -1, positions_checked


data = list(range(1024))
found, steps = binary_search_with_steps(data, 777)
assert found == 777
assert steps <= 11
```

Mỗi vòng duyệt có thể gọi **hai** toán tử so sánh (`==` rồi `<`), nhưng `positions_checked` chỉ tăng **một**. Đây là ví dụ cho thấy tên `comparisons` dễ gây hiểu nhầm nếu không viết định nghĩa. Nếu muốn đếm **số lời gọi toán tử so khóa thật**, phải tăng counter trước từng biểu thức so sánh.

## 8. Đọc xu hướng bộ đếm cùng với độ phức tạp

Số đếm cho phép kiểm tra một vài dự đoán mà thời gian đo thường khó nhìn rõ trên dữ liệu nhỏ.

### 8.1. Đếm theo `n`, không chỉ theo thời gian

Với binary search trên mảng sắp xếp dài `n`, số lần kiểm tra vị trí giữa trong trường hợp xấu nhất tăng theo `O(log n)`. Với tìm tuyến tính, số lần xem phần tử trong trường hợp xấu nhất là `O(n)`. Khi tăng `n` gấp đôi, bộ đếm của binary search thường tăng rất ít, còn tìm tuyến tính có thể tăng gần gấp đôi.

Tuy nhiên, một đường cong đếm trên vài bộ dữ liệu **không phải chứng minh đầy đủ về độ phức tạp**. Chứng minh cần lập luận từ cấu trúc vòng lặp, điều kiện dừng, bất biến và giả thiết đầu vào. Số đếm giúp kiểm tra xem **cài đặt có hành xử phù hợp với lập luận** hay không.

### 8.2. Cấp phát và chi phí khấu hao

Nếu buffer của heap nhân đôi từ 1 lên 2, 4, 8, ..., đến lúc đủ chứa `n` phần tử thì:

- Số lần tăng dung lượng sau khởi tạo là `O(log n)`.
- Tổng số lần sao chép phần tử **chỉ do resize** trong quá trình thêm `n` phần tử là `O(n)`: các lần sao chép xảy ra ở kích thước 1, 2, 4, ..., nhỏ hơn `n`.
- Dung lượng bộ đệm cuối cùng nhỏ hơn `2n` đối với `n >= 1` theo chính sách nhân đôi từ 1.
- Trong quá trình mở rộng, bộ đệm cũ và mới cùng tồn tại tạm thời, nên **đỉnh dung lượng dành chỗ** có thể lớn hơn dung lượng cuối.

Những nhận xét trên thuộc **chính sách bộ đệm trong ví dụ**, không phải bảo đảm cho mọi `list` hoặc mọi thư viện heap. Cấp phát đối tượng khóa, bộ nhớ riêng của runtime và GC cần được đo bằng công cụ khác.

### 8.3. Chuẩn hóa kết quả trước khi so

Nếu thử `n = 1.000` và `n = 100.000` nhưng số thao tác cũng tăng 100 lần, tổng phép so sánh tăng nhiều là điều tất yếu. Hãy phân biệt:

- `n`: số phần tử có trong cấu trúc ở một thời điểm.
- `m`: tổng số thao tác được chạy.
- Tỷ lệ thao tác: `push`, `pop`, `get`, `put`, `remove`.
- Số lần xảy ra sự kiện hiếm: resize, rehash, tạo nút mới, dọn nút.

Để đánh giá chi phí theo kích thước, thử **giữ `m` và phân phối thao tác cố định** khi thay `n` (hoặc tạo trạng thái ban đầu khác nhau), rồi theo dõi so sánh/op và thời gian/op. Để đánh giá chi phí tích lũy, giữ quy mô làm việc tương tự và tăng `m`.

### 8.4. Báo trung bình có thể che đỉnh

Một workload có 10.000 thao tác nhanh và một lần resize đắt có thể cho thời gian trung bình thấp, nhưng hệ thống yêu cầu giới hạn độ trễ có thể quan tâm tới **p95/p99 hoặc thao tác chậm nhất**.

Số đếm tổng cũng che đỉnh nếu không đo riêng từng thao tác. Có thể lấy chênh lệch `metrics` trước và sau từng lệnh để ghi `comparisons_per_call` hay `resize_copies_per_call`, **ở lượt chẩn đoán riêng**. Đừng bật ghi log từng thao tác trong benchmark định thời chính vì overhead có thể rất lớn.

## 9. Phân biệt thời gian có instrument với thời gian sản xuất

Gắn bộ đếm vào mỗi lần so sánh khiến mỗi phép toán phát sinh thêm một lần cập nhật số nguyên, truy cập đối tượng `metrics` và có thể thêm cấp phát/thu hồi đối tượng của runtime. Khi số thao tác rất nhỏ, chi phí này có thể lớn hơn công việc thực.

Nên chia quy trình thành **ba loại lượt chạy**:

| Lượt chạy | Bật gì? | Kết quả sử dụng |
|---|---|---|
| **Đúng đắn** | Kiểm tra bất biến, mô hình tham chiếu, ca biên | Xác nhận các phiên bản thực hiện cùng hợp đồng |
| **Chẩn đoán thuật toán** | Bộ đếm so sánh, ghi ô, cấp phát logic | Giải thích tại sao chi phí tăng theo dữ liệu/workload |
| **Benchmark thời gian và RAM** | Công cụ đo phù hợp, tối thiểu can thiệp | Đánh giá thời gian và bộ nhớ trong điều kiện gần thực tế |

Để so hai cài đặt, phải đảm bảo phiên bản instrumented và bản không instrumented có **thuật toán và hợp đồng tương ứng**, đồng thời chạy cùng workload. Không nên lấy số đếm từ bản A và thời gian từ bản B khác logic rồi gộp chúng thành “hiệu năng của một thuật toán”.

### Warmup và lặp lại

- Sinh toàn bộ dữ liệu cùng chuỗi thao tác **trước** vùng định thời.
- Chạy warmup thích hợp với runtime và mục tiêu đo.
- Khởi tạo lại trạng thái tương đương cho từng lượt; tránh phép xóa ở lượt trước làm đổi kích thước lượt sau.
- Chạy nhiều lượt, đảo thứ tự các phương án, ghi môi trường và báo trung vị cùng độ phân tán.
- Nếu đo p95/p99 theo lời gọi, thu mẫu độ trễ từng lời gọi bằng phương pháp cân nhắc overhead; **trung vị các lượt của trung bình thời gian/op không phải p50 của từng thao tác**.
- Đo bộ nhớ và GC bằng công cụ riêng khi cần, vì profiler có thể làm thay đổi thời gian.

Đối với Java, các môi trường có JIT nên dùng công cụ benchmark như JMH thay vì đo một vòng lặp thủ công đơn lẻ. Với C/C++, phép đo trình biên dịch tối ưu có thể loại bỏ công việc không quan sát được nếu không giữ kết quả; cần thiết kế benchmark chống lỗi này. Ở Python, lưu checksum hoặc kiểm tra kết quả ngoài đồng hồ giúp bảo đảm workload thực sự được thực thi.

## 10. Bài tập: số đếm giải thích điều gì?

### Bài 1 — Một mảng động tăng dung lượng

Một mảng động bắt đầu với dung lượng 1, nhân đôi khi đầy và lần lượt thêm 8 phần tử. Hãy đếm số lần tạo bộ đệm, số phần tử được sao chép chỉ do resize và dung lượng cuối cùng.

**Đáp án:** tạo bộ đệm ban đầu dung lượng 1 rồi thêm các bộ đệm dung lượng 2, 4, 8: **4 lần tạo bộ đệm** (3 lần resize). Sao chép lần lượt 1, 2, 4 phần tử nên **7 lần sao chép do resize**; dung lượng cuối là **8 ô**. Đây chưa phải số byte hoặc số cấp phát nội bộ của runtime.

### Bài 2 — Hai heap có cùng thời gian

Hai bản min-heap có cùng độ trễ trung bình nhưng một bản dùng ít phép so sánh hơn, lại có nhiều `slot_writes` hơn. Có thể kết luận bản ít so sánh chắc chắn tốt hơn không?

**Đáp án:** không. Chi phí một phép so sánh, ghi bộ nhớ, tính cục bộ và cấp phát đều có thể khác nhau; tỷ lệ workload và kích thước cũng quan trọng. Cần so đúng đắn, thời gian, số đếm và bộ nhớ trên cùng đầu vào, rồi mới đánh giá sự đánh đổi.

### Bài 3 — Đếm phép toán nào cho HashMap?

Một HashMap xử lý 10.000 lần `get`, nhưng nhóm khóa được chọn có nhiều va chạm băm. Chỉ đếm số lần gọi `get` có đủ giải thích vì sao chậm không?

**Đáp án:** không. Nên đếm thêm lần tính hash, số bucket/probe hoặc nút trong chuỗi được xét, số lần so bằng nhau, tỷ lệ hit/miss; nếu có cập nhật, theo dõi cả rehash và cấp phát. Giải thích cần phụ thuộc thiết kế chaining hay open addressing.

### Bài 4 — Bộ nhớ “tổng từng cấp phát” và bộ nhớ hiện tại

Một cấu trúc đã cấp phát các buffer 8, 16, 32 và đang chỉ giữ buffer 32. Có thể nói nó đang dùng 56 ô bộ đệm không?

**Đáp án:** không. **56 ô** là tổng số ô từng được tạo; số ô dự trữ ở buffer hiện tại là **32** theo giả thiết. Đỉnh đồng thời tại lần chuyển từ 16 sang 32 có thể là **48 ô** của hai buffer, chưa tính overhead. Dùng công cụ đo thực tế để biết số byte đang giữ.

### Bài 5 — Chọn bằng chứng phù hợp

Bạn cần so một Queue vòng và một danh sách liên kết trong workload `enqueue`/`dequeue` một triệu lần. Hãy đề xuất các chỉ số và tách lượt đo.

**Gợi ý:** xác minh thứ tự FIFO trước. Ở lượt chẩn đoán, đếm cấp phát nút của danh sách liên kết, lần tăng dung lượng và số phần tử chép của Queue vòng, số cập nhật con trỏ hoặc ô. Ở lượt benchmark, đo thời gian/throughput và độ trễ đuôi nếu cần; đo bộ nhớ giữ lại và đỉnh riêng. Thử cả Queue nhỏ ổn định, Queue lớn và chuỗi tạo/giải phóng nhiều phần tử để phản ánh GC hoặc bộ cấp phát.

## 11. Mẫu báo cáo thực hành

Một báo cáo đủ rõ để người khác diễn giải nên có các nhóm sau:

**Bài toán và môi trường:** tên và phiên bản cấu trúc, hệ điều hành, CPU, runtime, phiên bản mã, dung lượng bộ nhớ, số luồng, trạng thái warmup.

**Dữ liệu và workload:** `n` ban đầu, số thao tác `m`, tỷ lệ thao tác, phân phối khóa và giá trị, tỷ lệ trùng, trạng thái rỗng/đầy, seed sinh thao tác, chính sách lỗi.

**Quy ước đếm:** định nghĩa mỗi counter, thời điểm reset, liệu có bao gồm so sánh kiểm tra bất biến, sao chép lúc resize, cấp phát ban đầu hay không.

**Kết quả:** tổng thời gian và phân phối theo lượt, thời gian/op, so sánh/op hoặc từng loại thao tác, số lần tạo nút/buffer, số ô hiện giữ, tổng ô từng cấp phát, bộ nhớ giữ lại và đỉnh theo công cụ đo.

**Giới hạn:** instrument có overhead bao nhiêu, công cụ bộ nhớ theo dõi phạm vi nào, workload đã/không mô phỏng điều kiện đồng thời, GC, cache và dữ liệu rất lớn.

Ví dụ một mẫu bảng để **điền sau khi đo thực tế**:

| Cấu trúc | `n` | `m` | Thời gian trung vị/op | So sánh khóa/op | Cấp phát logic | Traced peak bytes | Đúng đắn |
|---|---:|---:|---:|---:|---:|---:|---|
| Min-heap dạng mảng | ... | ... | ... | ... | ... | ... | PASS/FAIL |
| Danh sách không sắp xếp | ... | ... | ... | ... | ... | ... | PASS/FAIL |

Không ghép số **so sánh/op** từ một kiểu workload với số **thời gian/op** đo từ workload khác mà không chú thích. Hai con số chỉ bổ trợ việc giải thích khi cùng phản ánh một lượng công việc tương đương.

## 12. Checklist trước khi rút ra kết luận

1. **Đã kiểm tra tính đúng đắn chưa?** Giá trị trả về, bất biến, bảo toàn phần tử và trạng thái sau chuỗi thao tác.
2. **Counter đã định nghĩa rõ chưa?** Đếm so sánh khóa, bước duyệt hay số toán tử? Có đếm thao tác thất bại không?
3. **Có phân biệt cấp phát logic với cấp phát runtime không?** Một nút hoặc một buffer không tương đương một lần gọi hệ điều hành.
4. **Có phân biệt dung lượng hiện giữ, tổng cấp phát và đỉnh không?** Tránh dùng tổng cộng dồn làm số RAM cuối cùng.
5. **Đã dùng đúng workload chưa?** Cùng `n`, `m`, phân phối dữ liệu và tỷ lệ `push/pop/get` giữa các phiên bản.
6. **Đã tách lượt chẩn đoán khỏi lượt định thời chưa?** Instrument và profiler có thể làm thay đổi thời gian.
7. **Đã ghi warmup, cấp phát lại và GC chưa?** Các sự kiện hiếm có thể ảnh hưởng độ trễ đuôi.
8. **Đã đọc độ phức tạp đúng kiểu bảo đảm chưa?** Trường hợp xấu nhất, kỳ vọng và khấu hao không đồng nghĩa.
9. **Đã đo những chỉ số thực sự cần cho ứng dụng chưa?** Có lúc giảm RAM quan trọng hơn giảm vài phép so sánh.
10. **Đã lưu dữ liệu và cách đo để chạy lại chưa?** Có seed, phiên bản mã, môi trường và phương pháp thống kê.

Đếm phép so sánh, số lần cấp phát và lượng bộ nhớ **không thay thế đo thời gian**, mà giúp hiểu thời gian đó đến từ đâu. Khi các số đếm được định nghĩa rõ, cấu trúc vẫn đúng theo hợp đồng và workload đại diện cho bài toán, ta có cơ sở vững chắc hơn để chọn giữa các thiết kế dữ liệu có đánh đổi khác nhau về tốc độ, bộ nhớ và độ ổn định.
