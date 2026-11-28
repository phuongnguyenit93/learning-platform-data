# Heap có chỉ mục và ánh xạ ngược từ phần tử sang vị trí

## 1. Vấn đề thực tế: biết tên công việc nhưng không biết nó đang nằm đâu

Hãy tưởng tượng một bộ lập lịch đang quản lý các công việc:

| Mã công việc | Độ ưu tiên | Ghi chú |
|---|---:|---|
| `A` | 6 | Tạo báo cáo |
| `B` | 2 | Xử lý cảnh báo |
| `C` | 4 | Đồng bộ dữ liệu |
| `D` | 9 | Gửi thông báo |

Nếu **số nhỏ hơn nghĩa là ưu tiên cao hơn**, một **min-heap** giúp lấy công việc quan trọng nhất tại gốc trong `O(1)` và thêm/lấy công việc trong `O(\log n)` thời gian.

Nhưng người dùng thường không yêu cầu “thay khóa ở chỉ số `3`”. Họ yêu cầu:

```text
change_priority("D", 1)    # D trở nên khẩn cấp.
cancel("C")                 # Hủy công việc C.
contains("A")               # A có còn đang đợi không?
```

**Heap thường không biết ngay công việc `D` ở chỉ số nào.** Các phần tử thay đổi vị trí sau những lần hoán đổi khi thêm, lấy và sửa độ ưu tiên. Nếu quét mảng tìm theo `id`, mỗi thao tác cập nhật theo ID có thể tốn `O(n)`, cho dù phần sửa heap sau đó chỉ mất `O(\log n)`.

Giải pháp là **heap có chỉ mục** (*indexed heap*, *indexed priority queue*): duy trì một bảng tra cứu **ngược từ định danh phần tử về vị trí hiện tại** trong mảng heap.

```text
                MẢNG HEAP                         ÁNH XẠ NGƯỢC

Chỉ số:         0       1       2       3         ID → chỉ số
Phần tử:      (2,B)   (6,A)   (4,C)   (9,D)       B  →  0
                                                   A  →  1
  heap[2] ────────────────► (4,C)                 C  →  2
                                                   D  →  3

                           position["C"] ─────────► 2
```

Hai hướng truy cập bổ sung cho nhau:

- **Vị trí → phần tử:** `heap[i]` trả về bản ghi ở chỉ số `i`.
- **Phần tử → vị trí:** `position[id]` trả về chỉ số **hiện tại** của bản ghi có ID đó.

### Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Giải thích vì sao heap thông thường không tra cứu ID trong `O(\log n)`.
2. Viết bất biến đồng bộ giữa mảng heap và bảng ánh xạ ngược.
3. Hiểu vì sao **mọi lần hoán đổi** phải cập nhật **cả hai** mục vị trí.
4. Cài đặt thêm, lấy gốc, đổi khóa và xóa theo ID bằng indexed min-heap.
5. Xây indexed heap từ một danh sách đầu vào bằng `heapify` từ dưới lên.
6. Phân tích thời gian kỳ vọng và chi phí bộ nhớ của bảng băm, hoặc thời gian bảo đảm khi dùng mảng chỉ số cho ID nguyên dày đặc.
7. Phân biệt khóa ưu tiên, định danh duy nhất, số thứ tự chèn và handle có phiên bản.
8. Xử lý các trường hợp biên: trùng ID, bằng ưu tiên, phần tử cuối, chỉ mục cũ, xóa rồi thêm lại.

Đây là bài của chương **Heap và hàng đợi ưu tiên** trong học phần **Cấu trúc dữ liệu**. Cách bổ sung bảng tra cứu để tăng tốc một thao tác là một ví dụ điển hình của việc kết hợp heap với mảng, bảng băm, cây và những cấu trúc khác để lựa chọn đánh đổi phù hợp theo thời gian, bộ nhớ và bất biến dữ liệu.

## 2. Heap chỉ sắp xếp một phần, không tạo chỉ mục theo định danh

Binary min-heap trên mảng thỏa hai bất biến cơ bản:

1. **Hình dạng:** cây nhị phân hoàn chỉnh, được lưu theo thứ tự tầng từ trái qua phải.
2. **Thứ tự heap:** mỗi cha có khóa không lớn hơn mọi con trực tiếp.

Với chỉ số từ `0`:

\[
parent(i)=\left\lfloor\frac{i-1}{2}\right\rfloor\quad(i>0);
\qquad left(i)=2i+1;\qquad right(i)=2i+2.
\]

Xét min-heap hợp lệ:

```text
                        (1, E)
                       /      \
                   (4, A)    (3, C)
                   /   \      /
                (7, D) (6, B) (5, F)

Mảng:  [(1,E), (4,A), (3,C), (7,D), (6,B), (5,F)]
Chỉ số:    0      1      2      3      4      5
```

Đọc `heap[0]` biết ngay công việc `E` có khóa nhỏ nhất. Nhưng để tìm `B`:

- Không thể suy ra vị trí từ ký tự `B`.
- Không thể dùng **binary search** vì mảng `[1,4,3,7,6,5]` không tăng dần.
- Quan hệ `parent\le child` theo **priority** không cho biết ID nằm bên trái hay bên phải.

Không có chỉ mục phụ, việc quét theo ID mất `O(n)` thời gian trong trường hợp xấu nhất. Nếu đã có **chỉ số đúng** của `B`, thay khóa rồi đẩy lên/xuống mới chỉ cần `O(\log n)`.

**Tách hai loại chi phí:**

\[
T_{\text{update theo ID}}
=T_{\text{tìm ID}}+T_{\text{sửa heap}}.
\]

Không có bảng vị trí:

\[
O(n)+O(\log n)=O(n).
\]

Có bảng ánh xạ ngược với tra cứu trung bình `O(1)`:

\[
O(1)_{\text{kỳ vọng}}+O(\log n)_{\text{kỳ vọng}}
=O(\log n)_{\text{kỳ vọng}}.
\]

Phát biểu trên giả định thao tác so sánh khóa và băm/so sánh ID có chi phí hằng số theo mô hình phân tích. Một ID chuỗi rất dài hoặc hàm băm đặc biệt có thể làm chi phí cơ bản lớn hơn.

## 3. Phân biệt rõ ba khái niệm: khóa, định danh và vị trí

Trong indexed heap, một phần tử thường có ba thuộc tính:

| Thuộc tính | Ví dụ | Vai trò | Có thể thay đổi? |
|---|---|---|---|
| **ID** (*identity*) | `"job-42"` | Xác định **đúng công việc** | Thường không đổi trong vòng đời công việc |
| **Priority** (*key*) | `3` | Quyết định thứ tự ưu tiên | Có thể cập nhật |
| **Vị trí heap** (*index*) | `7` | Địa chỉ logic trong mảng heap | Thay đổi sau nhiều phép swap |

Các công việc khác nhau **được phép có cùng priority**, nhưng trong thiết kế ánh xạ `id → index` thông dụng, **ID của các công việc đang hoạt động phải duy nhất**.

Ví dụ:

```text
id="A", priority=2
id="B", priority=2

Hợp lệ: A và B là hai công việc khác nhau, cùng khóa ưu tiên.
Không hợp lệ với bảng một-vị-trí-mỗi-ID:
  id="A", priority=2
  id="A", priority=5
```

Nếu một ứng dụng thật sự cho phép nhiều bản ghi trùng ID, phải chọn:

- Một **handle duy nhất cho từng bản ghi** làm định danh chỉ mục.
- Hoặc ánh xạ ID tới **tập vị trí**, với quy tắc cập nhật mỗi lần swap phức tạp hơn.
- Hoặc gộp những bản ghi cùng ID thành một mục logic, tùy hợp đồng nghiệp vụ.

Trong bài này, một ID đại diện **đúng một mục đang hoạt động**. Không dùng `priority` làm khóa của ánh xạ ngược vì priority có thể trùng và có thể thay đổi.

## 4. Bất biến ánh xạ ngược: hai hướng phải luôn khớp

Gọi `H` là mảng heap dài `n` và `pos` là bảng ánh xạ `ID → chỉ số`.

**Bất biến đồng bộ:**

\[
\boxed{\forall i\in[0,n):\quad pos[H[i].id]=i.}
\]

Và với mọi ID hiện đang được quản lý:

\[
\boxed{\forall id\in pos:\quad H[pos[id]].id=id.}
\]

Hai chiều phải đúng cùng lúc. Ngoài ra:

- `len(pos)=len(H)=n` nếu mỗi mục có ID duy nhất.
- Mọi `pos[id]` thuộc `[0,n)`.
- Không có ID đã xóa vẫn nằm trong `pos`.
- Heap-order `H[parent].priority\le H[child].priority` vẫn đúng khi tính cả tiêu chí ưu tiên phụ nếu có.

Có thể xem mảng và ánh xạ ngược như **hai mặt của một quan hệ một-một** trên tập ID đang hoạt động:

```text
H[0].id = B     ⇔     pos[B] = 0
H[1].id = A     ⇔     pos[A] = 1
H[2].id = C     ⇔     pos[C] = 2
H[3].id = D     ⇔     pos[D] = 3
```

Quan hệ này chỉ đúng tại **trạng thái hoàn tất, hợp lệ của các thao tác**. Bên trong một hàm đang hoán đổi các ô, có thể xuất hiện các bước cập nhật trung gian; không được cho luồng khác đọc một trạng thái chưa đồng bộ.

### Vì sao bất biến mới quan trọng ngang với heap-order?

Một heap có thể vẫn trả công việc ưu tiên nhất chính xác, trong khi `pos` sai và việc `cancel("C")` vô tình xóa công việc khác.

```text
Heap sau một swap:       [(1,D), (2,B), (4,C)]
pos còn lưu cũ:          D → 2, B → 1, C → 0

Heap-order có thể hoàn toàn đúng.
Nhưng pos["C"] = 0 trỏ tới D thay vì C!
```

Do đó, kiểm thử indexed heap phải xác nhận **đồng thời** cả bất biến thứ tự và bất biến ánh xạ.

## 5. Hoán đổi hai vị trí phải cập nhật cả hai ID

Giả sử:

```text
Trước swap(0, 3):

H[0] = (2, "B")      pos["B"] = 0
H[3] = (9, "D")      pos["D"] = 3
```

Sau khi hoán đổi, hai mục đã đổi vị trí:

```text
Sau swap(0, 3):

H[0] = (9, "D")      pos["D"] PHẢI = 0
H[3] = (2, "B")      pos["B"] PHẢI = 3
```

Phép cập nhật chuẩn:

```python
def swap_with_reverse_map(
    heap: list[tuple[int, str]],
    position: dict[str, int],
    i: int,
    j: int,
) -> None:
    heap[i], heap[j] = heap[j], heap[i]
    position[heap[i][1]] = i
    position[heap[j][1]] = j
```

Tại sao không chỉ cập nhật `position` của phần tử “đang bị đẩy lên”? Vì **phần tử bị đổi chỗ với nó cũng chuyển sang một vị trí khác**. Một ánh xạ sai thường không khiến thao tác hiện tại thất bại ngay; nó gây lỗi ở lần sửa hoặc hủy tiếp theo.

Với bảng băm, cập nhật hai mục thường có chi phí `O(1)` kỳ vọng. Nếu `sift-up`/`sift-down` đi qua `O(\log n)` tầng, tổng số lần sửa ánh xạ cũng là `O(\log n)`.

**Quy tắc triển khai:** mọi hoán đổi trong heap có chỉ mục nên đi qua **một hàm swap tập trung**; không để những hàm khác tự hoán đổi mảng mà quên cập nhật bảng.

## 6. Ví dụ theo dõi toàn bộ heap và ánh xạ qua nhiều thao tác

Khởi đầu là một min-heap theo khóa:

```text
       0       1       2       3       4
     (1,B)   (4,A)   (3,C)   (7,D)   (6,E)

pos = {B:0, A:1, C:2, D:3, E:4}
```

### Bước A — thay khóa của E từ 6 xuống 0

Tra bảng: `pos["E"]=4`, không cần quét mảng.

```text
Đổi khóa E tại i=4:
[(1,B), (4,A), (3,C), (7,D), (0,E)]

Swap i=4 với cha i=1:
[(1,B), (0,E), (3,C), (7,D), (4,A)]
  pos[E]=1, pos[A]=4

Swap i=1 với cha i=0:
[(0,E), (1,B), (3,C), (7,D), (4,A)]
  pos[E]=0, pos[B]=1
```

Ánh xạ kết thúc bước A:

```text
{E:0, B:1, C:2, D:3, A:4}
```

### Bước B — hủy C

Tra `pos["C"]=2`. Phần tử cuối là `(4,A)` ở chỉ số `4`.

- Lưu mục `C` để trả về; xóa `C` khỏi ánh xạ.
- Bỏ mục cuối ra khỏi mảng; thay ô `2` bằng `A`.
- Cập nhật `pos["A"]=2`.
- Kiểm tra thứ tự: gốc `E` có khóa `0`; `A` có khóa `4` và hiện không có con, nên không cần swap.

```text
H   = [(0,E), (1,B), (4,A), (7,D)]
pos = {E:0, B:1, A:2, D:3}
```

### Bước C — lấy phần tử ưu tiên nhất

Lấy gốc `E`, chuyển phần tử cuối `D` có khóa `7` lên thay gốc:

```text
Sau bỏ gốc E và chuyển D lên:
[(7,D), (1,B), (4,A)]

Sift-down: đổi D với con nhỏ hơn là B:
[(1,B), (7,D), (4,A)]
```

Ánh xạ phải trở thành:

```text
pos = {B:0, D:1, A:2}
```

**Điểm cần nhớ:** chỉ số của `B` đã chuyển `0 → 1 → 0` trong chuỗi thao tác. Nếu một thành phần ngoài heap giữ chỉ số `0` của B từ trước, việc cập nhật bằng chỉ số cũ có thể sửa **nhầm E hoặc D**. Các thao tác nghiệp vụ nên dùng **ID ổn định**, không dùng vị trí mảng như định danh lâu dài.

## 7. Chọn cấu trúc cho bảng vị trí: mảng hay bảng băm?

Chỉ mục ngược không bắt buộc là `dict`. Có hai trường hợp phổ biến.

### 7.1. ID là số nguyên dày đặc trong [0, U)

Nếu các ID là `0,1,\ldots,U-1` hoặc thuộc một miền số nguyên nhỏ, ta có thể dùng **mảng vị trí**:

```text
ID:              0   1   2   3   4   5
position[id]:    2  -1   0  -1   1  -1

-1 là sentinel: ID chưa nằm trong heap.
```

Tra cứu `position[id]` là **`O(1)` trường hợp xấu nhất** với chỉ số hợp lệ, không cần hàm băm. Bộ nhớ của bảng vị trí là **`O(U)`**, không phải `O(n)` nếu `U` lớn hơn nhiều số phần tử đang hoạt động.

Nên chọn mảng vị trí nếu:

- ID là số nguyên có cận trên biết trước, tương đối nhỏ.
- Cần truy cập ổn định và muốn tránh overhead của bảng băm.
- Chấp nhận bộ nhớ dự phòng cho ID hiện chưa tham gia heap.

### 7.2. ID là chuỗi hoặc số nguyên thưa

Với ID như `"job-2026-11-0087"`, `"task:alpha"` hoặc số nguyên rất lớn, mảng trực tiếp theo ID sẽ lãng phí. **Bảng băm `dict[id] = index`** chỉ chứa các ID đang hoạt động.

- Bộ nhớ phụ thường **`O(n)`** cho `n` mục trong heap.
- Tra cứu, chèn, sửa, xóa mục trong bảng có chi phí trung bình/kỳ vọng thường `O(1)`.
- Trong trường hợp va chạm bất lợi, phép tra bảng băm không phải lúc nào cũng `O(1)` xấu nhất.
- ID phải hỗ trợ băm và so sánh bằng nhau **nhất quán**, không thay đổi theo cách làm sai khóa bảng khi còn được dùng.

Nếu miền ID khổng lồ nhưng chỉ có vài chục công việc đang hoạt động, bảng băm thường tiết kiệm bộ nhớ hơn mảng vị trí cấp theo toàn miền.

### Bảng so sánh

| Cách lưu `position` | Tra cứu vị trí | Bộ nhớ riêng của bảng | Phù hợp |
|---|---|---|---|
| Mảng theo ID số nguyên | `O(1)` với chỉ số hợp lệ | `O(U)` | ID dày đặc trong miền nhỏ |
| Bảng băm theo ID | `O(1)` kỳ vọng | `O(n)` | ID thưa, chuỗi, khóa hashable |
| Không lưu ánh xạ | `O(n)` quét heap | `O(1)` | Rất ít thao tác theo ID |

Nếu phải đảm bảo **`O(\log n)` xấu nhất cho cả bước định vị theo ID**, một cấu trúc chỉ mục có bảo đảm xấu nhất thích hợp hơn bảng băm thông thường (ví dụ cây tìm kiếm cân bằng theo ID, với chi phí tra `O(\log n)`); chi phí tổng cập nhật heap và chỉ mục khi đó cần phân tích theo cả hai cấu trúc.

## 8. Thiết kế giao diện: không để lộ chỉ số như một định danh bền vững

Một indexed heap thường công bố các thao tác:

| Phương thức | Đầu vào | Ý nghĩa |
|---|---|---|
| `add(id, priority)` | ID mới và khóa | Thêm mục, báo lỗi nếu ID đang hoạt động |
| `peek()` | Không có | Xem mục có khóa nhỏ nhất |
| `pop()` | Không có | Lấy và xóa mục nhỏ nhất |
| `change_priority(id, priority)` | ID đang hoạt động | Sửa khóa và khôi phục heap-order |
| `remove(id)` | ID đang hoạt động | Xóa đúng mục theo ID |
| `contains(id)` | ID | Kiểm tra membership |
| `priority_of(id)` | ID đang hoạt động | Xem khóa hiện tại |
| `len(heap)` | Không có | Số mục đang hoạt động |

Thông thường **không nên** công bố một API kiểu:

```text
idx = heap.find_index("A")
... nhiều thao tác khác ...
heap.change_at(idx, new_priority)
```

Vì chỉ số có thể **đã cũ** sau bất kỳ lần `add`, `pop`, `remove` hoặc `change_priority` nào gây hoán đổi.

Thay vào đó:

```text
heap.change_priority("A", new_priority)
```

Phương thức tự lấy **vị trí mới nhất từ ánh xạ** ngay trước khi sửa. Đây vừa là thiết kế dễ dùng, vừa giúp bảo vệ bất biến khỏi mã bên ngoài.

## 9. Mã Python hoàn chỉnh: indexed min-heap có khóa hòa ổn định

Ta xây một cấu trúc tự chứa bằng Python với các giả định:

- Mỗi công việc có `id` là **chuỗi duy nhất** khi đang hoạt động.
- `priority` là **số nguyên**; khóa nhỏ hơn được xử lý trước.
- Khi hai công việc cùng priority, công việc được **thêm sớm hơn** xử lý trước.
- Khi đổi priority, công việc **giữ thứ tự đến ban đầu**.
- Không có hai luồng cùng lúc sửa cấu trúc.

Để xử lý hòa, mỗi mục heap được lưu dưới dạng:

\[
(\text{priority},\text{sequence},\text{id}),
\]

trong đó `sequence` là số thứ tự tăng dần, không lặp lại giữa các lần thêm. So sánh heap dùng **cặp** `(priority, sequence)`; ID chỉ phục vụ định danh và ánh xạ.

### 9.1. Toàn bộ định nghĩa

```python
from collections.abc import Iterable
from itertools import count


class IndexedMinHeap:
    """Min-heap theo (priority, thứ tự đến), có tra cứu ID -> index."""

    def __init__(self, items: Iterable[tuple[str, int]] = ()) -> None:
        self._heap: list[tuple[int, int, str]] = []
        self._pos: dict[str, int] = {}
        self._tickets = count()

        # Tạo mảng và ánh xạ một lần, rồi heapify từ dưới lên.
        for task_id, priority in items:
            if task_id in self._pos:
                raise ValueError(f"ID trùng: {task_id}")
            i = len(self._heap)
            self._heap.append((priority, next(self._tickets), task_id))
            self._pos[task_id] = i

        for i in range(len(self._heap) // 2 - 1, -1, -1):
            self._sift_down(i)

    def __len__(self) -> int:
        return len(self._heap)

    def contains(self, task_id: str) -> bool:
        return task_id in self._pos

    def priority_of(self, task_id: str) -> int:
        return self._heap[self._pos[task_id]][0]

    def _key(self, i: int) -> tuple[int, int]:
        priority, sequence, _ = self._heap[i]
        return priority, sequence

    def _swap(self, i: int, j: int) -> None:
        # Bắt buộc đồng bộ mảng và CẢ HAI mục của bảng vị trí.
        self._heap[i], self._heap[j] = self._heap[j], self._heap[i]
        self._pos[self._heap[i][2]] = i
        self._pos[self._heap[j][2]] = j

    def _sift_up(self, i: int) -> None:
        while i > 0:
            parent = (i - 1) // 2
            if self._key(parent) <= self._key(i):
                break
            self._swap(parent, i)
            i = parent

    def _sift_down(self, i: int) -> None:
        n = len(self._heap)
        while True:
            left = 2 * i + 1
            if left >= n:
                break

            right = left + 1
            smaller = left
            if right < n and self._key(right) < self._key(left):
                smaller = right

            if self._key(i) <= self._key(smaller):
                break
            self._swap(i, smaller)
            i = smaller

    def _repair(self, i: int) -> None:
        # Một nút được thay thế có thể cần đi lên HOẶC đi xuống.
        if i > 0 and self._key(i) < self._key((i - 1) // 2):
            self._sift_up(i)
        else:
            self._sift_down(i)

    def add(self, task_id: str, priority: int) -> None:
        if task_id in self._pos:
            raise ValueError("ID đang tồn tại")

        i = len(self._heap)
        self._heap.append((priority, next(self._tickets), task_id))
        self._pos[task_id] = i
        self._sift_up(i)

    def peek(self) -> tuple[str, int]:
        if not self._heap:
            raise IndexError("Heap rỗng")
        priority, _, task_id = self._heap[0]
        return task_id, priority

    def change_priority(self, task_id: str, new_priority: int) -> None:
        i = self._pos[task_id]  # KeyError nếu ID không tồn tại.
        _, sequence, _ = self._heap[i]
        self._heap[i] = (new_priority, sequence, task_id)
        self._repair(i)

    def _remove_at(self, i: int) -> tuple[str, int]:
        removed = self._heap[i]
        last = self._heap.pop()  # Xóa ô cuối, không dịch phần đuôi.
        del self._pos[removed[2]]

        if i < len(self._heap):
            # Chỉ có thể gán lại khi i vẫn nằm trong miền hợp lệ.
            self._heap[i] = last
            self._pos[last[2]] = i
            self._repair(i)

        return removed[2], removed[0]

    def remove(self, task_id: str) -> tuple[str, int]:
        return self._remove_at(self._pos[task_id])

    def pop(self) -> tuple[str, int]:
        if not self._heap:
            raise IndexError("Heap rỗng")
        return self._remove_at(0)

    def check_invariants(self) -> bool:
        """O(n), chỉ dùng để minh họa/debug."""
        n = len(self._heap)
        if len(self._pos) != n:
            return False

        for i, (priority, sequence, task_id) in enumerate(self._heap):
            if self._pos.get(task_id) != i:
                return False
            if i > 0:
                parent = (i - 1) // 2
                if self._key(parent) > (priority, sequence):
                    return False
        return True
```

### 9.2. Cách sử dụng

```python
queue = IndexedMinHeap([
    ("A", 4), ("B", 1), ("C", 3), ("D", 8)
])

print(queue.peek())       # ('B', 1)
print(queue.contains("C"))  # True

queue.change_priority("D", 0)
print(queue.peek())       # ('D', 0)

print(queue.remove("C"))  # ('C', 3)
print(queue.contains("C"))  # False

print(queue.pop())        # ('D', 0)
print(queue.pop())        # ('B', 1)
print(queue.pop())        # ('A', 4)
print(len(queue))         # 0
print(queue.check_invariants())  # True
```

Hàm được viết theo giao diện ID, không bắt người gọi lưu chỉ số. Sau mỗi thao tác, cả `_heap` và `_pos` được cập nhật bên trong lớp.

### 9.3. Điểm then chốt của mã

**Khi thêm mới:**

1. Kiểm tra ID chưa có trong `_pos`.
2. Ghi mục vào cuối `_heap`.
3. Ghi vị trí mới vào `_pos`.
4. `_sift_up`; mọi swap đi qua `_swap` nên bản đồ vị trí luôn được sửa.

**Khi đổi priority:**

1. Tra `i = _pos[task_id]`.
2. Đổi priority nhưng **giữ nguyên sequence**.
3. Gọi `_repair(i)` để chọn đẩy lên nếu nhỏ hơn cha, ngược lại đẩy xuống.

**Khi xóa:**

1. Xác định vị trí `i` qua ID.
2. Lấy mục ở cuối mảng và xóa vị trí cuối.
3. Xóa ánh xạ của **ID bị loại bỏ**.
4. Nếu `i` chưa phải cuối, đặt mục cuối vào `i`, cập nhật ánh xạ của nó rồi khôi phục heap.

**Khi tạo từ đầu vào:** xây đủ các mục và ánh xạ trước, sau đó gọi `_sift_down` từ nút cha cuối về gốc. Như vậy không cần thêm từng mục bằng `add`.

### 9.4. Phạm vi bảo đảm

Đây là phiên bản giảng dạy, giả định có đủ bộ nhớ và không có lỗi phát sinh giữa các phép gán trạng thái nội bộ. Trong một triển khai cần **exception safety** mạnh, nếu cấp phát cho bảng băm ném ngoại lệ ngay giữa thao tác swap hoặc chèn, phải có biện pháp để khôi phục giao dịch, dự trữ bộ nhớ hoặc bảo đảm cấu trúc không lộ trạng thái dở dang. Mã ví dụ cũng không tự an toàn khi nhiều luồng cập nhật cùng lúc.

Không nên cung cấp `_heap` và `_pos` cho mã ngoài sửa trực tiếp, bởi một lần sửa không đi qua API có thể phá bất biến mà `_repair` không phát hiện được.

## 10. Vì sao hàm _repair chọn hướng đúng?

Sau khi thay khóa của một phần tử hoặc đưa phần tử cuối vào một ô bị xóa, **chỉ các cạnh tiếp giáp vị trí vừa thay** có thể sai trong cấu trúc ban đầu đang hợp lệ.

Với min-heap:

- Nếu nút mới **nhỏ hơn cha**, cần **đẩy lên**.
- Nếu nút mới **không nhỏ hơn cha**, các quan hệ với cha đã đúng; nếu có lỗi, nó ở phía **con**, nên **đẩy xuống**.
- Nếu nút là gốc, nó không có cha: chỉ có thể cần đẩy xuống.

### Bất biến đẩy lên

Khi một khóa mới quá nhỏ, các cây con bên dưới vẫn có quan hệ đúng; chỉ cạnh lên cha có thể sai. Mỗi lần swap với cha lớn hơn:

1. Khóa nhỏ hơn chuyển lên một tầng.
2. Khóa cha cũ đi xuống nơi khóa mới vừa đứng; vì heap trước thay đổi hợp lệ, các quan hệ với cây con dưới vị trí ấy vẫn được giữ.
3. Vi phạm có thể chuyển tiếp lên một cạnh ở tầng trên.

Khi đến gốc hoặc gặp cha không lớn hơn nút, heap hợp lệ.

### Bất biến đẩy xuống

Khi khóa mới quá lớn, hai cây con của vị trí ấy vẫn là heap. Chọn **con nhỏ hơn**, hoán đổi nếu cần và tiếp tục xuống. Khóa mới ở vị trí cha không lớn hơn con còn lại, nên những cạnh đã đi qua được sửa đúng.

Một phần tử chỉ đi qua nhiều nhất chiều cao cây:

\[
h=\lfloor\log_2 n\rfloor,\quad n\ge1.
\]

Do đó, phần sửa heap theo một đường có `O(\log n)` bước.

**Riêng bảng vị trí:** mỗi swap thay đổi đúng hai vị trí; `_swap` cập nhật hai ánh xạ tương ứng. Vì vậy bất biến `pos[heap[i].id]=i` vẫn đúng sau mỗi lần swap hoàn chỉnh.

## 11. Chi phí xây indexed heap từ một danh sách đầu vào

Có hai cách thường gặp để xây heap cho `n` mục đã có sẵn.

### Cách A — thêm từng mục

Mỗi `add` có thể đẩy lên `O(\log n)` tầng. Xây từ đầu bằng `n` lần thêm có cận trên:

\[
T_A(n)=O(n\log n).
\]

### Cách B — xây mảng + ánh xạ, rồi heapify từ dưới lên

1. Ghi `n` mục vào mảng, lập `pos[id]=i`: `O(n)` kỳ vọng với bảng băm.
2. Duyệt các nút cha từ `\lfloor n/2\rfloor-1` về `0`, gọi `sift-down`.
3. Mỗi lần đổi chỗ, cập nhật ánh xạ nhờ `_swap`.

Phân tích heapify:

- Khoảng một nửa nút là lá, không cần đi xuống.
- Một số lượng ít hơn nút có thể đi xuống hai tầng.
- Chỉ rất ít nút gần gốc đi xuống `O(\log n)` tầng.

Tổng công việc bị chặn bởi:

\[
O\!\left(n\sum_{h\ge0}\frac{h}{2^{h+1}}\right)=O(n).
\]

Do mỗi swap cập nhật một số lượng cố định mục trong bảng băm, công việc xây heap và ánh xạ là **`O(n)` kỳ vọng** trên mô hình bảng băm thông dụng, cộng với thời gian đọc `n` đầu vào. Số ô lưu trữ cho cả heap và ánh xạ là `O(n)`.

### Khi heapify một mảng đã có sẵn

Nếu chương trình trực tiếp gọi `heapq.heapify` trên một mảng và còn giữ bảng ánh xạ cũ `pos`, bảng có thể bị **sai**, vì `heapify` hoán đổi các phần tử mà không cập nhật bảng.

Hai hướng hợp lệ:

- Viết `heapify` của indexed heap dùng `_swap` có cập nhật ánh xạ.
- Hoặc để thư viện thay đổi mảng, rồi **xây lại toàn bộ `pos`** từ các vị trí cuối cùng sau khi heapify. Bước xây lại này `O(n)` kỳ vọng.

Không được giả định rằng `heapify` “chỉ sửa thứ tự” nên ánh xạ ngược không cần cập nhật: **thứ tự trong mảng chính là vị trí mà ánh xạ lưu**.

## 12. Chi phí thao tác và bộ nhớ tổng thể

Giả sử `n` là số mục trong indexed heap, `U` là kích thước miền ID nếu dùng mảng vị trí và phép so sánh khóa là `O(1)`.

| Thao tác | Với bảng băm `id→index` | Với mảng vị trí ID nguyên |
|---|---|---|
| `contains(id)` | `O(1)` kỳ vọng | `O(1)` khi ID hợp lệ |
| `priority_of(id)` | `O(1)` kỳ vọng | `O(1)` |
| `peek()` | `O(1)` | `O(1)` |
| `add(id,priority)` | `O(\log(n+1))` kỳ vọng | `O(\log(n+1))`, tính riêng chi phí mở rộng vùng mảng heap |
| `change_priority(id,p)` | `O(\log(n+1))` kỳ vọng | `O(\log(n+1))` |
| `remove(id)` | `O(\log(n+1))` kỳ vọng | `O(\log(n+1))` |
| `pop()` | `O(\log(n+1))` kỳ vọng | `O(\log(n+1))` |
| Xây ban đầu từ `n` mục | `O(n)` kỳ vọng | `O(n)` nếu miền ID và vùng pos đã được khởi tạo |
| Bộ nhớ mảng heap | `O(n)` | `O(n)` |
| Bộ nhớ ánh xạ ngược | `O(n)` | `O(U)` |

**Lưu ý về `add`:** mảng động có thể cần cấp phát lại và chuyển toàn bộ dữ liệu khi hết sức chứa; một lần thêm riêng lẻ có thể chịu chi phí `O(n)` dù phần sift-up chỉ `O(\log n)`. Khi phân tích hàng đợi ưu tiên trên mảng động thông thường, chi phí `append` được xem là `O(1)` **khấu hao**, nên hàng `add` biểu thị cận thường dùng cho chuỗi thao tác, không phải một bảo đảm tuyệt đối về cấp phát bộ nhớ cho từng lần.

**Lưu ý về bảng băm:** thời gian kỳ vọng dựa vào hành vi tra cứu trung bình thích hợp của bảng băm. Nếu cần bảo đảm chặt chẽ trường hợp xấu nhất, phải lựa chọn cách ánh xạ và mô hình thực thi tương ứng; đừng gắn nhãn `O(1)` xấu nhất cho một `dict` tổng quát.

Mảng heap và bảng ngược đều có số phần tử tỷ lệ `n`, nên indexed heap giữ tổng dung lượng **`O(n)`** với bảng băm. Tuy nhiên, so với heap chỉ lưu khóa, nó tiêu tốn thêm chỗ cho ID, ánh xạ và có thể số thứ tự hòa. Trong hệ thống có nhiều triệu mục, hằng số bộ nhớ của các cấu trúc này cần được đo.

## 13. Khóa ưu tiên trùng nhau và quy tắc ổn định

Heap không tự bảo đảm **FIFO giữa các phần tử có cùng priority**. Ví dụ:

```text
Đến theo thứ tự:
A (priority 2)
B (priority 2)
C (priority 1)
```

Ta muốn lấy `C` trước, sau đó `A` rồi `B`. Khi đó, khóa so sánh có thể là:

\[
(\text{priority},\text{arrival\_sequence}).
\]

Trong mã Python:

```text
(priority=2, sequence=0, id=A)
(priority=2, sequence=1, id=B)
(priority=1, sequence=2, id=C)
```

Min-heap lấy `C` (khóa `(1,2)`) trước, rồi `A` (`(2,0)`) và `B` (`(2,1)`).

**Khi thay priority của A:**

- Nếu nghiệp vụ muốn A giữ “tuổi” ban đầu, **giữ nguyên sequence**.
- Nếu việc đổi priority được hiểu như xếp lại ở cuối những công việc cùng mức mới, phải có chính sách cấp **sequence mới**.
- Nếu thay đổi cả priority lẫn sequence, hướng sửa phải dựa trên **khóa ghép thực tế** chứ không chỉ so `priority`.

Không dùng ID để phân xử hòa một cách tình cờ nếu nghiệp vụ muốn thứ tự đến trước; sắp theo chuỗi `"A" < "B"` không có nghĩa A thực sự đến trước B.

## 14. Handle, ID tái sử dụng và vấn đề chỉ số bị cũ

ID là danh tính nghiệp vụ, còn chỉ số trong heap chỉ là trạng thái nội bộ. Nhưng ngay cả ID cũng có thể gặp vấn đề nếu được **tái sử dụng**.

Ví dụ:

1. Công việc `A` (phiên bản cũ) được thêm vào heap.
2. `A` bị hủy và xóa khỏi heap.
3. Một công việc khác được tạo **lại với cùng ID `A`**.
4. Một sự kiện hủy **trễ** của công việc A cũ đến hệ thống.

Nếu sự kiện chỉ mang `id="A"`, nó có thể vô tình hủy **công việc A mới**. Đây không phải lỗi heap-order hay bảng `pos`, mà là lỗi **định danh tái sử dụng** (*ABA-like identity reuse*).

Một giải pháp là dùng **handle có phiên bản**:

```text
handle = (slot, generation)

A cũ: (slot=12, generation=4)
A mới: (slot=12, generation=5)
```

Khi nhận một handle, hệ thống đối chiếu cả slot lẫn generation. Nếu không khớp phiên bản đang hoạt động, từ chối sự kiện cũ.

Với công việc có **UUID hoặc ID đơn điệu không tái sử dụng**, vấn đề này có thể được giải quyết ngay ở chính sách tạo ID. Dù chọn cách nào, **không được dùng chỉ số heap làm handle bền vững** trừ khi có cơ chế ánh xạ và kiểm tra phiên bản riêng.

## 15. Indexed heap khác với lazy deletion như thế nào?

Trong **indexed heap**, mỗi ID đang hoạt động có đúng **một mục vật lý** trong heap. Khi đổi khóa hoặc hủy, chương trình sửa/xóa **ngay mục đó**.

Trong kỹ thuật **xóa lười** (*lazy deletion*), thay vì xác định vị trí cũ, ta có thể:

1. Thêm bản ghi mới `(priority,version,id)` vào heap.
2. Đánh dấu bản ghi cũ không còn hợp lệ trong bảng trạng thái theo ID.
3. Khi lấy gốc, bỏ qua những bản ghi không còn khớp phiên bản hiện hành.

Ví dụ:

```text
Heap vật lý:
    (1, version=2, A)   <- hợp lệ
    (5, version=1, A)   <- lỗi thời
    (3, version=1, B)   <- hợp lệ

Trạng thái:
    active[A] = version 2
    active[B] = version 1
```

| Tiêu chí | Indexed heap | Lazy deletion |
|---|---|---|
| Tìm vị trí theo ID | Bảng `id→index` | Không cần nếu không sửa/xóa tại chỗ |
| Đổi khóa | Sửa mục cũ + sift | Thêm mục mới, đánh dấu mục cũ lỗi thời |
| Hủy theo ID | Xóa vật lý ngay | Đánh dấu không hợp lệ |
| Số mục vật lý | Thường bằng số ID hoạt động | Có thể lớn hơn rất nhiều |
| Khi pop | Một lần xóa + sửa heap | Có thể bỏ qua nhiều mục lỗi thời |
| Chi phí bảo trì | Phải sửa mapping sau mọi swap | Phải quản lý version và dọn mục lỗi thời |
| Bộ nhớ | `O(n)` theo số mục hoạt động | Theo tổng bản ghi chưa được dọn, có thể `m\gg n` |

Nếu dùng Python `heapq` và yêu cầu cập nhật theo ID không quá nghiêm ngặt về bộ nhớ, lazy deletion thường là phương án thuận tiện. Nếu cần **xóa vật lý ngay**, kiểm soát số mục trong heap hoặc đổi khóa rất nhiều lần, indexed heap có ưu thế.

Đừng khẳng định mỗi `pop` của lazy heap chỉ `O(\log n)` với `n` là số ID đang hoạt động: một lần gọi có thể phải loại bỏ **nhiều** bản ghi lỗi thời trước khi trả được một mục hợp lệ. Cần dùng `m` (số mục vật lý) và chi phí cộng dồn để phân tích.

## 16. Ví dụ ứng dụng: Dijkstra với hàng đợi ưu tiên có chỉ mục

Trong thuật toán Dijkstra cho đồ thị có trọng số cạnh **không âm**, mỗi đỉnh `v` có nhãn khoảng cách tạm thời `dist[v]`. Khi phát hiện đường đi ngắn hơn:

\[
dist[v]\leftarrow\min(dist[v],dist[u]+w(u,v)).
\]

Nếu `v` còn ở trong hàng đợi ưu tiên, cần **giảm khóa** `decrease\_key(v,new\_distance)` để nó được xét sớm hơn theo khoảng cách mới.

Nếu đỉnh có ID nguyên dày đặc `0,\ldots,V-1`, dùng mảng `position[v]` có thể tra vị trí trong **`O(1)`**, và một lần giảm khóa trong heap tốn **`O(\log V)`**.

Mã giả:

```text
DIJKSTRA(start, graph):
    for each vertex v:
        dist[v] = INF
    dist[start] = 0

    PQ = indexed min-heap of vertices keyed by dist[v]

    while PQ not empty:
        u, du = PQ.pop_min()
        if du == INF:
            break

        for each edge (u, v, weight):
            if v remains in PQ and du + weight < dist[v]:
                dist[v] = du + weight
                PQ.decrease_key(v, dist[v])
```

Ví dụ mô tả biến thể đưa mọi đỉnh vào heap ban đầu; phải có chiến lược xử lý `INF` và các đỉnh đã lấy ra. Có thể dùng cách khác chỉ thêm đỉnh khi được khám phá, nhưng cần quản lý trạng thái “chưa có trong heap”, “đang ở heap” và “đã xử lý”.

Với adjacency list và indexed binary heap có một mục cho mỗi đỉnh, phân tích thông dụng là:

\[
O((V+E)\log(V+1))
\]

thời gian, do các lần lấy đỉnh và giảm khóa. Mỗi cập nhật vị trí khi swap là một phần của các thao tác heap này. Bộ nhớ cho mảng heap, vị trí và khoảng cách là `O(V)`, chưa kể `O(V+E)` của đồ thị.

**Quan trọng:** indexed heap giúp thao tác hàng đợi nhanh, nhưng **không làm Dijkstra đúng với cạnh âm**. Điều kiện trọng số không âm là yêu cầu riêng của thuật toán đường đi.

### Ứng dụng khác

- **Bộ lập lịch:** cập nhật deadline hoặc hủy công việc theo ID.
- **Mô phỏng sự kiện rời rạc:** thay thời điểm diễn ra của một sự kiện đã lên lịch.
- **Prim:** giảm khóa của đỉnh khi có cạnh nối vào cây với chi phí thấp hơn.
- **Hệ thống điều phối tác vụ:** kết hợp một bảng tra cứu ID và heap theo thứ tự ưu tiên.

Trong những ứng dụng này, nếu cần tìm theo ID **và** lấy ưu tiên nhất, việc kết hợp bảng tra cứu với heap thường hợp lý hơn ép một cấu trúc tự đảm nhiệm cả hai yêu cầu.

## 17. Đồng thời và tính nguyên tử của hai cấu trúc

Indexed heap chứa **hai trạng thái liên quan**:

```text
Mảng heap:    H
Ánh xạ ngược: pos
```

Một lần swap không chỉ thay hai ô mảng mà còn thay hai ánh xạ. Nếu hai luồng cùng lúc gọi `remove` và `change_priority` mà không đồng bộ, có thể xảy ra:

1. Luồng A đọc `pos["C"]=4`.
2. Luồng B hoán đổi C sang vị trí `1` và cập nhật bảng.
3. Luồng A vẫn sửa `H[4]` vì giữ chỉ số cũ, gây tác động lên mục khác.

Ngay cả việc đọc `pos` và sau đó đọc `H[pos[id]]` cũng có thể không nhất quán khi có luồng đang sửa.

Trong ứng dụng nhiều luồng, cần:

- Bảo vệ **cả mảng heap lẫn bảng ánh xạ** bằng cùng một giao thức đồng bộ.
- Không để một thao tác cập nhật lộ ra trạng thái đã swap mảng nhưng chưa cập nhật mapping.
- Xác định khi nào có thể công bố kết quả `peek`, `remove`, `change_priority` một cách nguyên tử ở mức nghiệp vụ.
- Quản lý vòng đời của các công việc bên ngoài heap, tránh dùng ID/handle đã hủy hoặc tái sử dụng không kiểm soát.

Chỉ dùng một `dict` thread-safe ở mức thao tác đơn lẻ (nếu một nền tảng có bảo đảm đó) **không** làm tổ hợp các thao tác heap + dict tự động thread-safe.

## 18. Kiểm tra bất biến và thiết kế kiểm thử

Trong giai đoạn phát triển, có thể kiểm tra cả hai điều kiện sau sau một chuỗi thao tác:

\[
\forall i>0:\quad key(H[parent(i)])\le key(H[i]).
\]

\[
\forall i\in[0,n):\quad pos[H[i].id]=i,\qquad |pos|=n.
\]

Phương thức `check_invariants()` của lớp Python minh họa kiểm tra cả hai điều kiện trong `O(n)` thời gian kỳ vọng. Không nên gọi nó sau **mọi** thao tác trên đường chạy hiệu năng cao, vì như vậy mỗi lần `add`/`remove` sẽ có thêm `O(n)` kiểm tra và mất lợi thế của heap.

### Các tình huống nên có trong bộ kiểm thử

| Tình huống | Điều cần xác minh |
|---|---|
| Heap rỗng | `peek`/`pop` báo lỗi; `contains` trả `False` |
| Thêm ID đầu tiên | `pos[id]=0`, phần tử là gốc |
| Thêm một ID trùng | Phải báo lỗi hoặc xử lý theo hợp đồng đã chọn |
| Nhiều mục trùng priority | Thứ tự hòa theo `sequence` ổn định |
| Giảm priority của nút lá | Có thể cần nhiều lần sift-up và sửa mapping |
| Tăng priority của gốc | Có thể cần sift-down và sửa mapping |
| Xóa phần tử cuối | Không ghi vào chỉ số đã nằm ngoài mảng mới |
| Xóa gốc | Đưa mục cuối lên, sửa đúng mapping và heap-order |
| Xóa giữa làm sift-up | Không được luôn mặc định sift-down |
| Xóa giữa làm sift-down | Không được luôn mặc định sift-up |
| Xóa ID chưa có | API báo lỗi theo hợp đồng |
| Xóa rồi thêm lại cùng ID | Không còn mapping cũ; ticket mới đúng chính sách |
| Xây heap từ nhiều mục | `heapify` và mapping cuối cùng cùng khớp |
| Cập nhật nhiều lần rồi pop hết | Thứ tự trả về hợp lệ, ánh xạ rỗng cuối cùng |

### Minh họa một chuỗi kiểm thử

```python
h = IndexedMinHeap()
assert h.check_invariants()
assert not h.contains("X")

h.add("A", 5)
h.add("B", 2)
h.add("C", 9)
h.add("D", 4)
assert h.check_invariants()

h.change_priority("C", 1)  # Có thể đi lên nhiều tầng.
assert h.peek() == ("C", 1)
assert h.check_invariants()

h.change_priority("C", 8)  # Có thể đi xuống.
assert h.check_invariants()

h.remove("B")             # Xóa theo ID.
assert not h.contains("B")
assert h.check_invariants()

while len(h):
    h.pop()
    assert h.check_invariants()

assert len(h) == 0
```

Đây là **ví dụ mã kiểm thử trong nội dung bài học**, không phải yêu cầu thực thi bất kỳ bộ kiểm thử dự án nào. Trong kiểm thử tự động mở rộng, có thể so kết quả lấy gốc với một mô hình tham chiếu đơn giản chứa các công việc còn hoạt động và sắp theo `(priority,sequence)`.

## 19. Lỗi dễ mắc khi triển khai bảng ánh xạ ngược

| Lỗi | Hậu quả | Biện pháp |
|---|---|---|
| Chỉ sửa mảng khi swap | Bảng vị trí trỏ sai | Dùng một hàm `_swap` sửa cả hai ID |
| Chỉ cập nhật mapping của mục đang sift | Mục bị đổi chỗ cũng có vị trí mới | Ghi lại mapping của **cả hai** |
| Xóa phần tử nhưng không xóa `pos[id]` | Mapping trỏ tới vị trí đã mất | Xóa mục ánh xạ của ID bị loại |
| Thay phần tử cuối vào ô bị xóa nhưng không cập nhật mapping | ID chuyển vào ô mới vẫn trỏ tới cuối cũ | Ghi vị trí mới trước khi sift |
| Gọi `heapq.heapify` lên mảng nhưng dùng map cũ | Heap đổi nhiều vị trí mà map không biết | Rebuild map hoặc tự heapify qua `_swap` |
| Dùng priority làm định danh | Nhiều ID có cùng priority; priority còn thay đổi | Dùng ID duy nhất và ổn định |
| Giữ chỉ số heap trong một đối tượng bên ngoài rồi dùng lại | Chỉ số thay đổi sau swap | Gọi API theo ID/handle ổn định |
| Dùng bảng mảng `position[id]` cho ID thưa rất lớn | Cấp phát bộ nhớ lãng phí | Dùng bảng băm |
| Tưởng bảng băm `O(1)` xấu nhất | Va chạm băm và rehash có thể làm thao tác chậm | Ghi rõ kỳ vọng; chọn chỉ mục có bảo đảm phù hợp |
| Cho phép ID thay đổi sau khi đưa vào heap | Khóa của map không khớp với mục | Không cho đổi ID hoặc đổi có kiểm soát |
| Xóa tại cuối rồi ghi lại `H[i]` | `i` không còn là chỉ số hợp lệ | Kiểm tra `i<len(H)` sau khi pop cuối |
| Luôn đẩy xuống khi xóa tùy ý | Phần tử cuối có thể nhỏ hơn cha | Kiểm tra quan hệ với cha để chọn hướng |
| Chỉ kiểm tra heap-order mà không kiểm tra pos | Heap trông đúng nhưng update theo ID sai | Kiểm tra cả hai bất biến |
| Khóa có giá trị không so sánh nhất quán | Sift-up/down không có lập luận thứ tự | Chuẩn hóa khóa, xử lý `NaN` nếu có |
| Đổi ID cũ sang một nhiệm vụ mới không kiểm tra thế hệ | Sự kiện cũ có thể tác động mục mới | Dùng ID không tái sử dụng hoặc handle có version |
| Không đồng bộ mảng và map khi đa luồng | Race, sai vị trí, xóa nhầm | Khóa/giao thức concurrent cho cả cấu trúc |

### Cách chẩn đoán khi kết quả sai

Kiểm tra theo thứ tự:

1. ID của mỗi mục có duy nhất trong heap không?
2. `pos` có cùng số phần tử với `heap` không?
3. Mỗi `pos[id]` có trỏ ngược tới đúng mục ID ấy không?
4. Mọi cạnh cha–con có thỏa min/max-heap theo **đúng khóa so sánh** không?
5. Mọi thao tác hoán đổi, xóa, thay gốc hoặc heapify có cập nhật bảng không?
6. Có ai bên ngoài giữ chỉ số cũ hoặc sửa thẳng mảng và bảng hay không?

Các câu hỏi này thường giúp xác định lỗi là **hỏng cấu trúc heap**, **hỏng chỉ mục**, hay **hỏng hợp đồng định danh**.

## 20. Bài tập tự kiểm tra

**Bài 1.** Heap có mảng `[(1,B),(4,A),(3,C),(7,D),(6,E)]`. Hãy viết đầy đủ ánh xạ ngược `pos`. Từ `pos["E"]`, tìm vị trí của E mất thời gian gì nếu `pos` là bảng băm?

**Bài 2.** Cũng với heap ở Bài 1, giảm priority của E từ `6` xuống `0`. Ghi mảng heap và bảng `pos` sau **mỗi** lần swap.

**Bài 3.** Một lần `swap(1,4)` đổi `A` và `E`. Vì sao cập nhật duy nhất `pos["E"]` là chưa đủ?

**Bài 4.** Hãy phát biểu bất biến `pos[heap[i].id]=i` bằng lời. Điều gì sẽ xảy ra nếu heap-order đúng nhưng ánh xạ ngược sai?

**Bài 5.** Cho heap `[(0,E),(1,B),(3,C),(7,D),(4,A)]` và `pos` tương ứng. Xóa `C` theo ID. Kết quả mảng và ánh xạ là gì?

**Bài 6.** Sau thao tác ở Bài 5, tiếp tục `pop()` gốc. Mục trả về, mảng và vị trí cuối cùng của B, A, D là gì?

**Bài 7.** Nếu chỉ có mảng heap `n` phần tử và biết mỗi ID, việc tìm vị trí trong trường hợp xấu nhất mất bao nhiêu? Còn khi dùng bảng băm ánh xạ ngược thì sao?

**Bài 8.** Nếu các ID là số nguyên `0` đến `999` và chỉ có `30` ID hoạt động, bộ nhớ của **mảng vị trí** so với **bảng băm** phụ thuộc vào những đại lượng nào? Kỹ thuật nào có tra cứu `O(1)` trường hợp xấu nhất cho ID hợp lệ?

**Bài 9.** Vì sao xây indexed heap từ `n` mục bằng cách tạo mảng, ánh xạ rồi heapify có thể mất `O(n)` thời gian kỳ vọng, thay vì `O(n\log n)`?

**Bài 10.** Sau khi gọi `heapq.heapify` trên mảng mục, tại sao không thể tái sử dụng bảng `pos` lập trước khi heapify mà không kiểm tra hoặc sửa?

**Bài 11.** Có hai công việc cùng priority `2`: A đến trước B. Cấu trúc cần lưu khóa so sánh nào để lấy A trước B? Khi chỉ đổi priority, nên giữ hay đổi sequence nếu muốn giữ tuổi công việc?

**Bài 12.** Với một heap có một phần tử `(4,A)`, hãy mô tả điều xảy ra khi `pop()`. Vì sao không được gán lại phần tử cuối vào `heap[0]` sau đó?

**Bài 13.** Nếu một heap đã xóa `A`, rồi thêm một công việc **mới** cũng tên `A`, một yêu cầu hủy trễ của A cũ gây rủi ro gì? Đề xuất một cách định danh an toàn.

**Bài 14.** So sánh bộ nhớ và tốc độ xóa theo ID của indexed heap với phương án lazy deletion khi một công việc bị thay priority hàng nghìn lần.

**Bài 15.** Vì sao chỉ khóa một thao tác ghi vào `dict` là chưa đủ để đảm bảo indexed heap an toàn khi nhiều luồng cùng sửa?

**Bài 16.** Trong thuật toán Dijkstra với `V` đỉnh và ID nguyên dày đặc, vì sao có thể dùng mảng vị trí thay bảng băm? Khi cải thiện khoảng cách tới đỉnh `v`, heap cần thực hiện thao tác nào?

**Bài 17.** Cho một ứng dụng nhận yêu cầu “cập nhật job X theo ID” rất hiếm, nhưng `peek/pop` liên tục. Có nhất thiết cần thêm bảng chỉ mục `O(n)` không? Nêu sự đánh đổi.

**Bài 18.** Hãy mô tả một phép kiểm tra để phát hiện **map bị lỗi** mà một phép kiểm tra heap-order đơn thuần không phát hiện.

### Đáp án và giải thích

1. `pos={B:0,A:1,C:2,D:3,E:4}`. Với bảng băm, tra `pos["E"]` tốn `O(1)` kỳ vọng.
2. Đổi E thành `0`: `[(1,B),(4,A),(3,C),(7,D),(0,E)]`, map chưa đổi vị trí. Swap `4↔1`: `[(1,B),(0,E),(3,C),(7,D),(4,A)]`, `pos[E]=1,pos[A]=4`. Swap `1↔0`: `[(0,E),(1,B),(3,C),(7,D),(4,A)]`, `pos[E]=0,pos[B]=1`; các mục khác giữ đúng vị trí.
3. Vì `A` cũng chuyển sang vị trí `4` khi E chuyển tới `1`. Nếu không sửa `pos[A]`, lần sửa/xóa A về sau có thể đụng vào mục sai.
4. Với mọi ô `i` trong heap, bảng ngược lấy ID của ô ấy phải trả chính `i`. Nếu sai, `remove(id)` hoặc `change_priority(id)` có thể sửa nhầm phần tử dù lấy gốc vẫn cho kết quả đúng.
5. Xóa C ở `i=2`, lấy A cuối thay vào: `[(0,E),(1,B),(4,A),(7,D)]`, `pos={E:0,B:1,A:2,D:3}`.
6. `pop()` trả `(E,0)`. Đưa D lên gốc rồi swap với B: `[(1,B),(7,D),(4,A)]`, do đó `pos[B]=0,pos[D]=1,pos[A]=2`.
7. Không chỉ mục: `O(n)` xấu nhất. Bảng băm ngược: `O(1)` kỳ vọng để định vị, rồi `O(\log n)` để sửa heap nếu có thay đổi.
8. Mảng vị trí tốn `O(U)` với `U=1000`, bảng băm tốn `O(n)` với `n=30`. Mảng theo ID có truy cập `O(1)` trường hợp xấu nhất khi chỉ số hợp lệ.
9. Khoảng một nửa nút là lá, các nút gần lá chỉ đẩy ít tầng. Tổng công `\sum_h O(nh/2^{h+1})=O(n)`. Nếu mỗi swap cập nhật map `O(1)` kỳ vọng, tổng vẫn `O(n)` kỳ vọng.
10. `heapify` đổi vị trí nhiều phần tử. Nếu không cập nhật lại `pos`, giá trị `pos[id]` có thể không còn bằng chỉ số thật. Cần heapify qua hàm swap có cập nhật hoặc xây lại map từ mảng sau heapify.
11. Dùng `(priority,arrival_sequence)` với sequence khác nhau. Nếu muốn giữ thứ tự đến ban đầu khi chỉ sửa priority, **giữ nguyên** sequence.
12. Lưu `(A,4)`, xóa ô cuối đồng thời làm mảng rỗng, xóa `pos[A]` rồi trả kết quả. Không còn `heap[0]` hợp lệ để ghi.
13. Yêu cầu hủy A cũ có thể xóa A mới. Sử dụng ID duy nhất không tái sử dụng hoặc handle gồm `(slot,generation)`.
14. Indexed heap thay khóa **tại chỗ**, giữ số mục vật lý gần số ID hoạt động và dùng map `O(n)`; xóa theo ID trong `O(\log n)` kỳ vọng. Lazy deletion để lại bản ghi cũ, có thể tăng kích thước `m` và phải bỏ các mục stale khi pop hoặc rebuild.
15. Swap phải sửa cả mảng và hai mục bảng vị trí; một luồng có thể nhìn thấy trạng thái trung gian của luồng khác. Cần đồng bộ **toàn bộ thao tác** của heap + map.
16. ID đỉnh thường thuộc `[0,V)` nên mảng `position[v]` dùng `O(V)` bộ nhớ, tra cứu `O(1)`. Khi giảm khoảng cách tạm thời `dist[v]`, dùng **decrease-key** và sift-up trong min-heap.
17. Không nhất thiết. Một phép quét ID hiếm khi xảy ra có thể chấp nhận `O(n)` mà không tốn bộ nhớ `O(n)` và công bảo trì mapping. Quyết định dựa trên tần suất thực tế.
18. Với mỗi `i`, kiểm tra `pos[heap[i].id]==i` và `len(pos)==len(heap)`. Điều này phát hiện ánh xạ lỗi dù tất cả các cạnh cha–con vẫn hợp lệ.

## 21. Ghi nhớ

**Indexed heap** kết hợp **mảng heap** và **ánh xạ ngược từ ID sang vị trí**. Bất biến quan trọng nhất là **`pos[heap[i].id]=i`** với mọi chỉ số hiện có, đi cùng bất biến cha–con của heap. Mỗi lần hoán đổi hai phần tử phải cập nhật **cả hai vị trí trong bảng ngược**; khi thêm, xóa, thay gốc hoặc heapify cũng phải giữ hai cấu trúc đồng bộ. Với bảng băm, tra ID thường **`O(1)` kỳ vọng**, nên sửa khóa và xóa theo ID đạt **`O(\log n)` kỳ vọng**, đổi lại dùng thêm **`O(n)` bộ nhớ**. Nếu ID là số nguyên trong miền nhỏ, có thể thay bảng băm bằng mảng vị trí `O(U)` để tra cứu `O(1)` trường hợp xấu nhất. Đừng dùng **chỉ số heap** như định danh bền vững: chỉ số đổi sau swap; hãy dùng **ID duy nhất hoặc handle có phiên bản**, đồng thời kiểm soát khóa trùng, thứ tự hòa, vòng đời mục và đồng bộ truy cập. Cấu trúc phù hợp nhất là cấu trúc đáp ứng **cả thao tác lấy ưu tiên nhất lẫn tra cứu/cập nhật theo ID** với chi phí thời gian và bộ nhớ chấp nhận được.
