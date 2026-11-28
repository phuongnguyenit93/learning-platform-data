# Thứ tự giữa các phần tử có cùng ưu tiên và cách giữ tính ổn định

## 1. Bài toán: hai công việc cùng ưu tiên thì ai được xử lý trước?

Giả sử một hệ thống quản lý yêu cầu hỗ trợ. Mỗi yêu cầu có **mức độ ưu tiên**: số nhỏ hơn nghĩa là cần được xử lý sớm hơn.

| Thời điểm đưa vào hàng đợi | ID | Độ ưu tiên | Nội dung |
|---:|---|---:|---|
| 1 | `A` | `2` | Kiểm tra tài khoản |
| 2 | `B` | `1` | Khắc phục lỗi hệ thống |
| 3 | `C` | `2` | Cập nhật thông tin |
| 4 | `D` | `1` | Khôi phục dịch vụ |

Hàng đợi ưu tiên phải bảo đảm `B` và `D` được lấy trước `A`, `C` vì khóa `1` ưu tiên hơn `2`. Nhưng nếu cả `B` lẫn `D` cùng khóa `1`, ta phải quyết định **B trước D** hay **D trước B**.

Trong nhiều hệ thống, quy tắc mong muốn là:

> Khi **độ ưu tiên bằng nhau**, yêu cầu **được đưa vào hàng đợi sớm hơn** phải được xử lý trước.

Với quy tắc ấy, thứ tự lấy ra của ví dụ phải là:

```text
B (priority=1, đến thứ 2)
D (priority=1, đến thứ 4)
A (priority=2, đến thứ 1)
C (priority=2, đến thứ 3)
```

Đây là yêu cầu **ổn định** (*stability*) khi các khóa ưu tiên bằng nhau. Một **binary heap** hoặc **d-ary heap** thông thường chỉ có bất biến thứ tự giữa cha và con, nên **không tự bảo đảm** thứ tự này.

### Bạn sẽ học được gì?

Sau bài này, bạn có thể:

1. Định nghĩa chính xác tính ổn định của hàng đợi ưu tiên khi có khóa bằng nhau.
2. Phân biệt **ổn định của kết quả lấy ra** với **vị trí vật lý của phần tử trong heap**.
3. Giải thích bằng phản ví dụ vì sao heap chỉ so sánh priority có thể đảo thứ tự đến.
4. Dùng **khóa ghép `(priority, sequence)`** để tạo một thứ tự so sánh nhất quán.
5. Cài stable min-priority queue và max-priority queue bằng `heapq` trong Python.
6. Xử lý payload không so sánh được, timestamp trùng, khóa không hợp lệ và ID duy nhất.
7. Xác định chính sách **giữ hay cấp lại số thứ tự** khi thay đổi mức ưu tiên.
8. Kết hợp tính ổn định với **indexed heap**, **lazy deletion** và cập nhật khóa.
9. Phân tích chi phí thời gian, bộ nhớ, tính đồng thời và tính công bằng.

Chủ đề thuộc chương **Heap và hàng đợi ưu tiên** của học phần **Cấu trúc dữ liệu**. Việc bổ sung tiêu chí phụ vào khóa là một ví dụ thực tế của tư duy **bất biến, thao tác, độ phức tạp thời gian và bộ nhớ**, giúp lựa chọn giữa mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị.

## 2. Tính ổn định thực sự có nghĩa là gì?

Gọi `p(x)` là độ ưu tiên của phần tử `x`, và `a(x)` là **thứ tự x được đưa vào hàng đợi**.

Trong min-priority queue, ta thường muốn:

- Nếu `p(x)<p(y)` thì `x` được lấy **trước** `y` khi cả hai đang chờ.
- Nếu `p(x)=p(y)` và `a(x)<a(y)` thì `x` được lấy **trước** `y`, miễn là cả hai vẫn đang chờ và chưa bị hủy/cập nhật theo một chính sách thay đổi thứ tự.

Phần thứ hai chính là **ổn định theo thứ tự đến**. Trong một hệ thống có các sự kiện đến tuần tự, có thể xem nó là quy tắc **FIFO trong mỗi mức ưu tiên** (*first in, first out within each priority*).

### So với queue FIFO

Một **queue FIFO** lấy mọi phần tử theo thứ tự đưa vào, bất kể priority:

```text
Thứ tự đưa vào: A(2), B(1), C(2), D(1)

Queue FIFO lấy: A, B, C, D
Stable priority queue lấy: B, D, A, C
```

Stable priority queue **không phải** queue FIFO trên toàn bộ dữ liệu. Nó chỉ bảo toàn FIFO **bên trong các nhóm có cùng mức ưu tiên**.

### So với phép sắp xếp ổn định

Một thuật toán **sắp xếp ổn định** không đổi thứ tự tương đối của các phần tử có khóa bằng nhau. Stable priority queue yêu cầu tính chất tương tự ở **chuỗi kết quả pop** khi dữ liệu liên tục được thêm, lấy, đổi khóa hoặc hủy.

Đối với hàng đợi ưu tiên động, phải ghi rõ **thứ tự nào được xem là “đến trước”** sau mỗi lần cập nhật. Nếu không, khái niệm ổn định còn thiếu hợp đồng nghiệp vụ.

## 3. Vì sao binary heap thông thường không ổn định?

Min-heap chỉ yêu cầu:

\[
key(parent)\le key(child)
\]

với mọi cạnh cha–con. Khi hai khóa bằng nhau, chúng **đều thỏa** quan hệ `\le`, nên bất biến không bắt buộc phần tử đến trước phải nằm ở gốc hoặc ở nhánh bên trái.

### Phản ví dụ chỉ có ba phần tử

Đưa lần lượt ba yêu cầu có cùng priority `1` vào heap:

```text
A(1), B(1), C(1)

Mảng heap hợp lệ:
Chỉ số:   0      1      2
         [A(1), B(1), C(1)]

Cây:
           A(1)
          /    \
        B(1)   C(1)
```

Lần đầu `pop` lấy `A`. Thuật toán xóa gốc của binary heap chuyển phần tử **cuối mảng** `C` lên gốc:

```text
Trước pop: [A(1), B(1), C(1)]

Lấy A; đưa C lên gốc:
Sau pop:   [C(1), B(1)]
             ^
             C ở gốc
```

Nếu `sift-down` dừng khi `parent\le child`, quan hệ `1\le1` đúng, nên không cần đổi chỗ. Lần `pop` tiếp theo trả `C`, rồi mới tới `B`.

```text
Thứ tự đưa vào: A, B, C
Thứ tự pop:     A, C, B     <- KHÔNG ổn định
```

Không có vi phạm heap-order nào: **mảng vẫn là min-heap hợp lệ**. Vấn đề là bất biến heap không thể phân biệt các phần tử có cùng khóa.

### “Chọn con trái khi hai con bằng nhau” có đủ không?

**Không.** Phản ví dụ trên đảo thứ tự ngay khi chuyển **phần tử cuối lên gốc**, trước cả khi có quyết định giữa hai con. Quy tắc “hòa thì chọn con trái” chỉ ảnh hưởng một bước của `sift-down`, không tạo bảo đảm FIFO cho toàn bộ chuỗi thao tác.

Muốn giữ thứ tự, ta phải bổ sung **thông tin về thứ tự đến** vào phép so sánh, thay vì chỉ thay quy tắc hoán đổi khi hai khóa bằng nhau.

## 4. Khóa ghép: giải pháp phổ biến để giữ ổn định

Mỗi phần tử có hai thông tin so sánh:

\[
\boxed{K(x)=\bigl(p(x),\,s(x)\bigr)}
\]

trong đó:

- `p(x)`: **priority** của `x`.
- `s(x)`: **sequence number** — số thứ tự chèn tăng dần, duy nhất trong những mục cần so sánh.

Trong **min-heap**, ta so sánh hai khóa ghép theo **thứ tự từ điển** (*lexicographic order*):

\[
(p_1,s_1)<(p_2,s_2)
\]

khi và chỉ khi:

\[
p_1<p_2\quad\text{hoặc}\quad
(p_1=p_2\ \land\ s_1<s_2).
\]

Nói bằng lời:

1. **So priority trước.**
2. Nếu priority bằng nhau, **so sequence**.
3. Mục có `sequence` nhỏ hơn là mục đến sớm hơn, nên được lấy trước.

### Minh họa

```text
ID   priority   sequence   khóa so sánh
A       2           0      (2, 0)
B       1           1      (1, 1)
C       2           2      (2, 2)
D       1           3      (1, 3)
```

Thứ tự khóa tăng dần:

```text
(1, 1) B
(1, 3) D
(2, 0) A
(2, 2) C
```

Đúng với mong muốn: **priority trước, FIFO khi priority bằng nhau**.

### Vì sao sequence phải duy nhất?

Nếu `s(x)=s(y)` trong khi `p(x)=p(y)`, hai khóa ghép vẫn hòa nhau. Khi ấy việc chọn mục nào trước có thể phụ thuộc vào một tiêu chí thứ ba hoặc chi tiết bên trong heap, và không còn chứng minh được thứ tự đến từ chỉ hai trường.

Một bộ đếm đơn điệu tăng dần, cấp một số **khác nhau cho mỗi lần enqueue**, là cách đơn giản để tạo sequence duy nhất trong một phạm vi quản lý.

## 5. Chứng minh tính ổn định bằng khóa ghép

Giả sử ta đưa vào một min-heap các mục có khóa `K(x)=(p(x),s(x))`, với `s(x)` duy nhất và tăng theo thời điểm enqueue.

Một heap hợp lệ có tính chất **gốc mang khóa nhỏ nhất** theo phép so sánh đã chọn. Đối với hai mục `x` và `y` vẫn còn trong heap:

**Trường hợp 1 — khác priority.** Nếu `p(x)<p(y)` thì `K(x)<K(y)`, bất kể sequence. Khi cả hai vẫn có mặt, `y` không thể được pop trước `x` chỉ vì `y` đến sớm hơn.

**Trường hợp 2 — cùng priority.** Nếu `p(x)=p(y)` nhưng `s(x)<s(y)`, theo định nghĩa từ điển:

\[
K(x)<K(y).
\]

Do đó, khi cả hai còn chờ, `y` không thể được lấy trước `x`. Tính chất này vẫn đúng sau mọi lần `sift-up` hoặc `sift-down` vì các thao tác ấy duy trì **heap-order theo toàn bộ khóa ghép**.

**Kết luận:** khi các mục không bị hủy và sequence được giữ theo hợp đồng, **thứ tự pop bảo toàn FIFO đối với các mục có priority bằng nhau**.

Điểm tinh tế: heap **không cần giữ** thứ tự vật lý của các mục theo ID trong mảng. Hai mục có thể đổi chỗ nhiều lần bên trong heap, nhưng thứ tự **lấy ra** vẫn đúng vì khóa so sánh đã mã hóa tiêu chí phụ.

## 6. Mô phỏng một min-heap ổn định từ lúc thêm tới lúc lấy

Xét các mục `A(2,0)`, `B(1,1)`, `C(2,2)`, `D(1,3)`. Để sơ đồ gọn, mỗi mục được viết `ID(priority,sequence)`.

### Bước 1 — thêm A

```text
[A(2,0)]
```

### Bước 2 — thêm B

```text
Thêm cuối: [A(2,0), B(1,1)]
So khóa:   (1,1) < (2,0)
Đẩy lên:   [B(1,1), A(2,0)]
```

### Bước 3 — thêm C

```text
[B(1,1), A(2,0), C(2,2)]
```

Gốc `B` có priority `1`, nên không đổi với `C` có priority `2`.

### Bước 4 — thêm D

Thêm `D(1,3)` ở cuối, so với cha `A(2,0)`:

```text
[B(1,1), A(2,0), C(2,2), D(1,3)]

(1,3) < (2,0) -> đổi D với A:
[B(1,1), D(1,3), C(2,2), A(2,0)]

So D với B:
(1,1) < (1,3) -> không đổi
```

Hai phần tử priority `1` nằm theo khóa ghép: `B(1,1)` có thứ tự đến sớm hơn `D(1,3)`.

### Bước 5 — lấy liên tiếp

| Lần pop | Mục được lấy | Khóa ghép | Lý do |
|---:|---|---|---|
| 1 | `B` | `(1,1)` | Priority nhỏ nhất; đến trước D |
| 2 | `D` | `(1,3)` | Priority 1 còn lại |
| 3 | `A` | `(2,0)` | Priority 2; đến trước C |
| 4 | `C` | `(2,2)` | Priority 2 còn lại |

Thứ tự pop là **B, D, A, C**. Vị trí nội bộ của các mục có thể thay đổi khi pop, nhưng việc chọn gốc vẫn dựa trên cặp `(priority,sequence)` nên kết quả ổn định.

## 7. Python heapq: stable min-priority queue đơn giản

Python cung cấp `heapq` để thao tác **min-heap** trên một `list`. Thư viện so sánh tuple theo **thứ tự từ điển** nên ta có thể lưu:

```text
(priority, sequence, payload)
```

Khi `sequence` được cấp duy nhất, hai mục có cùng priority sẽ phân biệt được ngay ở trường sequence, nên **không phải so sánh payload**.

### Mã hoàn chỉnh

```python
import heapq
from itertools import count


sequence = count()  # 0, 1, 2, 3, ...; duy nhất trong hàng đợi này.
queue: list[tuple[int, int, str]] = []


def enqueue(priority: int, job_id: str) -> None:
    order = next(sequence)
    heapq.heappush(queue, (priority, order, job_id))


def dequeue() -> tuple[str, int]:
    priority, _, job_id = heapq.heappop(queue)
    return job_id, priority


enqueue(2, "A")
enqueue(1, "B")
enqueue(2, "C")
enqueue(1, "D")

print(dequeue())  # ('B', 1)
print(dequeue())  # ('D', 1)
print(dequeue())  # ('A', 2)
print(dequeue())  # ('C', 2)
```

### Những bất biến được duy trì

1. Mảng `queue` là một min-heap theo **toàn bộ tuple**, không chỉ theo priority.
2. Bộ đếm `sequence` cấp mỗi lần chèn một số khác nhau.
3. `heapq.heappush` và `heapq.heappop` giữ heap-order theo thứ tự tuple.
4. Nếu hai mục còn chờ có priority bằng nhau, mục có sequence nhỏ hơn có khóa ghép nhỏ hơn.

Nhờ đó, **`heappop` không cần có tính ổn định nội tại**; việc ổn định đến từ khóa so sánh do ứng dụng chủ động tạo.

### Khi heap rỗng

`heapq.heappop([])` phát sinh `IndexError`. API nghiệp vụ nên quyết định sẽ ném lỗi, trả `None` hay trả trạng thái “không có công việc” và xử lý trường hợp rỗng một cách nhất quán.

## 8. Trường hợp payload không hỗ trợ so sánh

Một lỗi Python phổ biến là đưa thẳng tuple `(priority,payload)` vào `heapq`:

```python
import heapq

queue = []
heapq.heappush(queue, (2, {"id": "A"}))

# Lần thêm tiếp có cùng priority sẽ cần so sánh hai dict.
try:
    heapq.heappush(queue, (2, {"id": "B"}))
except TypeError:
    print("Không thể so sánh hai payload dict")
```

Khi hai phần tử cùng priority, Python so sánh tiếp phần tử thứ hai trong tuple. Hai `dict` không hỗ trợ phép `<`, nên có thể gặp `TypeError`.

**Giải pháp:** đặt một sequence duy nhất giữa priority và payload:

```python
import heapq
from itertools import count

ticket = count()
queue = []

heapq.heappush(queue, (2, next(ticket), {"id": "A"}))
heapq.heappush(queue, (2, next(ticket), {"id": "B"}))

print(heapq.heappop(queue)[2])  # {'id': 'A'}
print(heapq.heappop(queue)[2])  # {'id': 'B'}
```

Hai bản ghi cùng priority đã được phân định bằng `sequence` khác nhau. Python không cần đi tới trường payload.

**Cảnh báo:** nếu sequence có thể trùng, chương trình lại có nguy cơ so sánh payload ở trường tiếp theo. Hãy đảm bảo thứ tự khóa có **tiêu chí phân biệt cuối cùng đáng tin cậy**, hoặc thiết kế đối tượng so sánh chỉ dựa vào các trường hợp lệ.

## 9. Dùng dataclass để tách khóa so sánh khỏi dữ liệu

Thay vì đưa tuple trực tiếp vào heap, Python cho phép định nghĩa một kiểu bản ghi có thứ tự:

```python
from dataclasses import dataclass, field
from itertools import count
import heapq


@dataclass(order=True)
class QueueItem:
    priority: int
    sequence: int
    payload: object = field(compare=False)


next_sequence = count()
queue: list[QueueItem] = []

heapq.heappush(
    queue, QueueItem(2, next(next_sequence), {"id": "A"})
)
heapq.heappush(
    queue, QueueItem(2, next(next_sequence), {"id": "B"})
)
heapq.heappush(
    queue, QueueItem(1, next(next_sequence), {"id": "C"})
)

while queue:
    item = heapq.heappop(queue)
    print(item.payload["id"])
# C
# A
# B
```

`@dataclass(order=True)` tạo các phương thức so sánh theo thứ tự những trường có `compare=True`. Trường `payload` có `compare=False`, nên không tham gia so sánh.

Ưu điểm:

- Nói rõ cấu trúc dữ liệu thay vì phụ thuộc thứ tự tuple khó nhớ.
- Không vô tình so sánh payload khi có các phần tử cùng priority.
- Có thể thêm trường dữ liệu nghiệp vụ không tham gia chọn ưu tiên.

Điều kiện ổn định vẫn là **sequence tăng dần và duy nhất** giữa những mục cần phân xử hòa. `dataclass` không tự cấp sequence hoặc tự giữ tính ổn định.

## 10. Max-heap: ưu tiên số lớn hơn nhưng vẫn FIFO khi hòa

Nếu số **lớn hơn** nghĩa là khẩn cấp hơn, ta cần một **max-priority queue**.

Với khóa số hỗ trợ phép lấy dấu đối `-priority`, có thể dùng min-heap của Python và lưu:

\[
\boxed{K(x)=(-p(x),s(x)).}
\]

Khi priority lớn hơn, giá trị `-priority` nhỏ hơn nên được lấy trước. Nếu priority bằng nhau, ta vẫn so `sequence` **tăng dần**, nên mục đến trước được lấy trước.

### Ví dụ

```python
import heapq
from itertools import count

sequence = count()
queue: list[tuple[int, int, str]] = []


def enqueue_max(priority: int, job_id: str) -> None:
    heapq.heappush(
        queue, (-priority, next(sequence), job_id)
    )


def dequeue_max() -> tuple[str, int]:
    negative_priority, _, job_id = heapq.heappop(queue)
    return job_id, -negative_priority


enqueue_max(10, "A")
enqueue_max(20, "B")
enqueue_max(10, "C")
enqueue_max(20, "D")

print(dequeue_max())  # ('B', 20)
print(dequeue_max())  # ('D', 20)
print(dequeue_max())  # ('A', 10)
print(dequeue_max())  # ('C', 10)
```

**Sai lầm thường gặp:** lưu `(-priority,-sequence)`. Cách ấy khiến các mục cùng priority có sequence **lớn hơn** được lấy trước — tức **LIFO khi hòa**, không phải FIFO.

### Lưu ý về đảo dấu

- Mẹo `-priority` chỉ phù hợp khi kiểu khóa có phép đổi dấu hợp lệ.
- Với số nguyên độ rộng cố định ở một số ngôn ngữ, đảo dấu giá trị âm nhỏ nhất có thể gây **tràn số**.
- Với object phức tạp hoặc nhiều tiêu chí, nên cung cấp **comparator** rõ ràng hoặc dùng API max-heap thích hợp của môi trường.
- Nếu dùng một bộ so sánh đảo chiều toàn bộ tuple, có thể vô tình đảo **cả sequence**, dẫn tới mất FIFO. Cần đảo chiều **priority**, không đảo tiêu chí thứ tự đến.

## 11. FIFO, LIFO và những chính sách hòa khác

**Ổn định FIFO** là một lựa chọn phổ biến, nhưng không phải lựa chọn duy nhất. Ứng dụng có thể chủ động chọn chính sách khác.

| Chính sách khi priority bằng nhau | Khóa phụ / cách chọn | Ví dụ dùng |
|---|---|---|
| **FIFO** — đến trước xử lý trước | `sequence` tăng dần | Hàng đợi hỗ trợ khách hàng |
| **LIFO** — đến sau xử lý trước | `-sequence` trong min-heap | Một số mô hình ưu tiên công việc mới |
| **Theo hạn chót** | `deadline` rồi mới `sequence` | Lập lịch cần ưu tiên hạn sớm |
| **Theo ID** | `id` | Muốn thứ tự xác định theo ID, không nhất thiết FIFO |
| **Không quy định** | Chỉ `priority` | Chấp nhận bất kỳ thứ tự nào khi hòa |

Ví dụ với **min-heap, LIFO khi cùng priority**:

```python
import heapq
from itertools import count

sequence = count()
h = []
for name in ["A", "B", "C"]:
    order = next(sequence)
    heapq.heappush(h, (1, -order, name))

print([heapq.heappop(h)[2] for _ in range(3)])
# ['C', 'B', 'A']
```

LIFO là một chính sách có chủ ý, **không** phải “tính ổn định” theo thứ tự enqueue ban đầu.

Điều quan trọng là **quy định chính sách trước**, định nghĩa khóa so sánh phản ánh chính sách ấy, rồi duy trì nhất quán trong mọi thao tác thêm, thay khóa, lấy gốc và xóa.

## 12. Timestamp có thay thế sequence được không?

Ta có thể nghĩ đến khóa:

```text
(priority, created_at)
```

Trong môi trường đơn giản, timestamp ngày giờ có thể **gần giống** thứ tự đến. Tuy nhiên, timestamp không luôn là một khóa phân xử hòa đáng tin cậy:

1. Hai yêu cầu có thể nhận **cùng timestamp** nếu độ phân giải đồng hồ không đủ cao.
2. Đồng hồ hệ thống có thể được điều chỉnh, làm thời gian quan sát đi ngược.
3. Trong hệ thống phân tán, đồng hồ các máy có thể **lệch nhau**.
4. Timestamp của **lúc tạo công việc** có thể khác thứ tự thực sự **enqueue** vào hàng đợi.
5. Một yêu cầu có thể đến lại sau khi bị hủy hoặc retry, khiến “đến trước” cần được định nghĩa theo **lượt nào**.

Nếu hai công việc cùng priority và cùng timestamp, heap lại không có tiêu chí nào chứng minh FIFO.

### Dùng sequence do hàng đợi cấp

Một bộ đếm đơn điệu cấp ticket ở thời điểm enqueue:

```text
enqueue(A) -> sequence=100
enqueue(B) -> sequence=101
enqueue(C) -> sequence=102
```

Ưu điểm: thứ tự rõ ràng và không phụ thuộc độ phân giải đồng hồ.

### Có cần kết hợp cả timestamp lẫn sequence?

Có thể dùng:

\[
(priority, timestamp, sequence).
\]

Trong đó `sequence` là tiêu chí **cuối cùng**, phân xử khi timestamp trùng. Nhưng nếu mục tiêu thực sự là **FIFO theo thứ tự enqueue**, chỉ dùng `sequence` thường đơn giản và ít rủi ro hơn.

Nếu muốn sắp theo **thời điểm sự kiện gốc** (*event time*) thay vì thời điểm enqueue, đó là một chính sách khác; hãy đặt tên trường và giải thích rõ.

## 13. Độ phức tạp: khóa phụ có làm heap chậm hơn về Big-O không?

Với binary heap có `n` phần tử, những thao tác cơ bản có độ phức tạp:

| Thao tác | Heap chỉ có priority | Heap dùng khóa `(priority,sequence)` |
|---|---|---|
| `peek` | `O(1)` | `O(1)` |
| `push` | `O(\log n)` | `O(\log n)` |
| `pop` | `O(\log n)` | `O(\log n)` |
| `heapify` từ mảng | `O(n)` | `O(n)` |
| Tìm ID bất kỳ | `O(n)` | `O(n)` nếu không có chỉ mục phụ |
| Đổi khóa tại chỉ số đã biết | `O(\log n)` | `O(\log n)` |
| Bộ nhớ lưu `n` mục | `O(n)` | `O(n)`, thêm một trường sequence mỗi mục |

**Vì sao cùng Big-O?** Cấu trúc cây hoàn chỉnh không đổi. Các vòng `sift-up` và `sift-down` vẫn đi qua nhiều nhất `O(\log n)` tầng. So sánh hai cặp khóa cố định `(priority,sequence)` chỉ tăng một số lượng hằng số phép so sánh nguyên cơ bản.

**Nhưng hằng số không hoàn toàn miễn phí:**

- Mỗi mục cần lưu thêm một sequence.
- Có thể phải so sánh hai trường thay vì một khi priority bằng nhau.
- Nếu sequence là số nguyên độ dài tùy ý rất lớn, chi phí so sánh/cấp phát của bản thân số không còn hằng số theo độ dài bit.
- Nếu dữ liệu được gói trong nhiều object Python, overhead có thể khác giữa tuple và dataclass.
- Trong ngôn ngữ có kiểu số nguyên độ rộng cố định, phải xử lý vấn đề tràn bộ đếm.

Theo mô hình thuật toán thông dụng với các khóa kích thước cố định, tính ổn định có **bộ nhớ `O(n)`** và không làm thay đổi bậc độ phức tạp của thao tác heap.

## 14. Xây heap ban đầu từ một danh sách mà vẫn ổn định

Nếu có sẵn `n` công việc trong một danh sách theo đúng thứ tự enqueue mong muốn, ta có thể cấp sequence theo **vị trí xuất hiện trong danh sách**, rồi `heapify` một lần:

```python
import heapq

items = [
    ("A", 2),
    ("B", 1),
    ("C", 2),
    ("D", 1),
]

heap = [
    (priority, sequence, job_id)
    for sequence, (job_id, priority) in enumerate(items)
]
heapq.heapify(heap)  # O(n), không cần push n lần.

result = []
while heap:
    priority, sequence, job_id = heapq.heappop(heap)
    result.append(job_id)

print(result)  # ['B', 'D', 'A', 'C']
```

### Vì sao heapify không làm mất ổn định?

`heapq.heapify` có thể hoán đổi các ô của mảng, nhưng nó sử dụng **khóa đã gắn sequence**. Vì hai mục có priority bằng nhau vẫn được phân biệt bằng sequence, thứ tự pop tiếp theo vẫn phản ánh thứ tự enqueue ban đầu.

**Điều kiện:** danh sách đầu vào phải phản ánh đúng thứ tự mà ứng dụng muốn giữ. Nếu ta tạo sequence sau khi dữ liệu đã bị xáo trộn, hệ thống sẽ giữ FIFO theo thứ tự **đã xáo trộn ấy**, không thể suy ra lịch sử thực sự.

Xây heap bằng `n` lần `heappush` có thể mất `O(n\log n)` trong trường hợp xấu nhất; `heapify` từ dưới lên chỉ cần **`O(n)`** thời gian.

## 15. Khi công việc đổi priority: “đến trước” được tính từ lúc nào?

Đây là quyết định nghiệp vụ quan trọng nhất khi hàng đợi ưu tiên có thao tác **`change_priority`**.

Giả sử:

```text
Thời điểm 1: A được enqueue với priority=5
Thời điểm 2: B được enqueue với priority=2
Thời điểm 3: C được enqueue với priority=2
Thời điểm 4: A được đổi priority từ 5 sang 2
```

Sau khi đổi, cả A, B, C đều có priority `2`. **A có được xếp trước B và C không?**

Không thể trả lời chỉ bằng bất biến heap. Có ít nhất hai chính sách hợp lệ.

### Chính sách A — giữ thứ tự đến ban đầu

Khi đổi priority của A, **giữ nguyên sequence** đã cấp ở thời điểm 1.

```text
A: (priority=2, sequence=1)
B: (priority=2, sequence=2)
C: (priority=2, sequence=3)

Thứ tự pop: A, B, C
```

Cách này phù hợp khi “tuổi” của công việc tính từ **lần enqueue đầu tiên** và không thay đổi dù priority đổi.

### Chính sách B — đưa vào cuối nhóm ưu tiên mới

Khi đổi priority của A, **cấp một sequence mới** ở thời điểm 4.

```text
B: (priority=2, sequence=2)
C: (priority=2, sequence=3)
A: (priority=2, sequence=4)

Thứ tự pop: B, C, A
```

Cách này phù hợp khi **thay đổi priority** được xem là “xếp lại vào hàng đợi” ở nhóm ưu tiên mới.

### Không có chính sách nào tự động đúng cho mọi hệ thống

Nếu yêu cầu là “công việc đã chờ lâu thì được ưu tiên trước khi bằng cấp”, chính sách A có thể hợp lý. Nếu mục tiêu là công bằng giữa những việc **đã ở mức priority mới từ trước**, chính sách B có thể phù hợp hơn.

**Phải công bố quy tắc trong API**, ví dụ:

```text
change_priority(id, value, preserve_arrival=True)
```

Hoặc tách thành hai thao tác khác nhau như `reprioritize_preserving_age` và `requeue_with_new_age`. Điều tối kỵ là để người dùng **suy đoán** thứ tự khi priority thay đổi.

## 16. Khi thay khóa trong indexed heap, phải so toàn bộ khóa ghép

Một **indexed heap** kết hợp:

1. Mảng heap chứa các bản ghi `(priority,sequence,id)`.
2. Ánh xạ `position[id]=index` cho biết vị trí hiện tại của ID.

Chỉ mục này cần thiết vì heap-order theo priority không giúp tìm ID bất kỳ nhanh. Khi thay priority theo ID:

- Tra vị trí từ bảng `position`.
- Cập nhật priority, đồng thời giữ hoặc thay sequence theo chính sách.
- **So sánh khóa ghép cũ và mới** để chọn `sift-up` hoặc `sift-down`.
- Sau **mọi lần swap**, cập nhật bảng vị trí của **cả hai ID**.

### Bất biến cần có

Với `H` là mảng và `pos` là bảng ánh xạ:

\[
\forall i>0:\quad
K(H[parent(i)])\le K(H[i]),
\]

\[
\forall i\in[0,n):\quad pos[H[i].id]=i.
\]

Trong đó:

\[
K(x)=(x.priority,x.sequence).
\]

Nếu chỉ kiểm tra `priority` khi quyết định hướng sửa, chương trình có thể bỏ qua sự thay đổi sequence và phá thứ tự ổn định.

### Ví dụ đổi sequence mà priority không đổi

```text
Trước:
  A=(2,1) ở gốc
  B=(2,2) ở con

Requeue A với sequence=3:
  A=(2,3) ở gốc
  B=(2,2) ở con

Priority không đổi, nhưng A=(2,3) > B=(2,2).
Phải sift-down để B trở thành gốc.
```

Đây là lý do **không đủ** nếu chỉ viết:

```text
if new_priority == old_priority:
    return
```

khi hệ thống cho phép thay đổi cả thứ tự đến.

## 17. Cài đặt stable indexed min-priority queue bằng Python

Ví dụ sau hỗ trợ **thêm, xem, lấy, đổi priority và hủy theo ID**, đồng thời giữ thứ tự đến ban đầu khi đổi priority. Mỗi ID đang hoạt động là duy nhất.

Để code độc lập và dễ kiểm chứng, thứ tự so sánh của heap chỉ gồm `(priority,sequence)`, còn `job_id` dùng cho ánh xạ.

```python
from itertools import count


class StableIndexedMinQueue:
    def __init__(self) -> None:
        self.heap: list[tuple[int, int, str]] = []
        self.pos: dict[str, int] = {}
        self.tickets = count()

    def __len__(self) -> int:
        return len(self.heap)

    def _key(self, i: int) -> tuple[int, int]:
        priority, sequence, _ = self.heap[i]
        return priority, sequence

    def _swap(self, i: int, j: int) -> None:
        self.heap[i], self.heap[j] = self.heap[j], self.heap[i]
        self.pos[self.heap[i][2]] = i
        self.pos[self.heap[j][2]] = j

    def _sift_up(self, i: int) -> None:
        while i > 0:
            parent = (i - 1) // 2
            if self._key(parent) <= self._key(i):
                return
            self._swap(parent, i)
            i = parent

    def _sift_down(self, i: int) -> None:
        n = len(self.heap)
        while True:
            left = 2 * i + 1
            if left >= n:
                return

            right = left + 1
            best = left
            if right < n and self._key(right) < self._key(left):
                best = right

            if self._key(i) <= self._key(best):
                return
            self._swap(i, best)
            i = best

    def _repair(self, i: int) -> None:
        if i > 0 and self._key(i) < self._key((i - 1) // 2):
            self._sift_up(i)
        else:
            self._sift_down(i)

    def add(self, job_id: str, priority: int) -> None:
        if job_id in self.pos:
            raise ValueError("ID đang hoạt động")
        ticket = next(self.tickets)
        i = len(self.heap)
        self.heap.append((priority, ticket, job_id))
        self.pos[job_id] = i
        self._sift_up(i)

    def peek(self) -> tuple[str, int]:
        if not self.heap:
            raise IndexError("Hàng đợi rỗng")
        priority, _, job_id = self.heap[0]
        return job_id, priority

    def change_priority(self, job_id: str, new_priority: int) -> None:
        i = self.pos[job_id]  # KeyError nếu không tồn tại.
        _, old_ticket, _ = self.heap[i]
        # Giữ thứ tự đến ban đầu khi chỉ đổi priority.
        self.heap[i] = (new_priority, old_ticket, job_id)
        self._repair(i)

    def requeue(self, job_id: str, new_priority: int) -> None:
        """Coi việc đổi priority là lượt xếp hàng mới."""
        i = self.pos[job_id]
        self.heap[i] = (new_priority, next(self.tickets), job_id)
        # So cả cặp khóa: priority có thể bằng cũ nhưng ticket đã khác.
        self._repair(i)

    def _remove_at(self, i: int) -> tuple[str, int]:
        removed = self.heap[i]
        last = self.heap.pop()
        del self.pos[removed[2]]

        if i < len(self.heap):
            self.heap[i] = last
            self.pos[last[2]] = i
            self._repair(i)

        return removed[2], removed[0]

    def cancel(self, job_id: str) -> tuple[str, int]:
        return self._remove_at(self.pos[job_id])

    def pop(self) -> tuple[str, int]:
        if not self.heap:
            raise IndexError("Hàng đợi rỗng")
        return self._remove_at(0)


q = StableIndexedMinQueue()
q.add("A", 5)
q.add("B", 2)
q.add("C", 2)

q.change_priority("A", 2)  # A giữ ticket cũ nhất.
print(q.pop())             # ('A', 2)
print(q.pop())             # ('B', 2)
print(q.pop())             # ('C', 2)

r = StableIndexedMinQueue()
r.add("A", 5)
r.add("B", 2)
r.add("C", 2)
r.requeue("A", 2)          # A được đưa vào cuối nhóm priority 2.
print(r.pop())             # ('B', 2)
print(r.pop())             # ('C', 2)
print(r.pop())             # ('A', 2)
```

### Vì sao cấu trúc này ổn định?

- `add` cấp một ticket mới, duy nhất.
- `change_priority` giữ ticket cũ; `requeue` cấp ticket mới theo hợp đồng.
- Cả `_sift_up` và `_sift_down` so **cặp `(priority,sequence)`**.
- `_swap` cập nhật vị trí hiện tại của cả hai ID.
- `pop` và `cancel` đưa phần tử cuối vào chỗ cần xóa rồi khôi phục heap, không dựa vào thứ tự vật lý trước đó.

Với bảng băm hoạt động theo giả định thông thường, `add`, `change_priority`, `requeue`, `pop` và `cancel` có chi phí **`O(\log n)` kỳ vọng** theo mô hình so sánh khóa hằng số; `peek` là `O(1)`. Bảng `pos` dùng `O(n)` bộ nhớ bổ sung.

**Giới hạn ví dụ:** lớp không hỗ trợ sửa cùng lúc từ nhiều luồng, không tự bảo vệ khỏi người ngoài sửa thẳng `heap`/`pos` và không xác nhận một ID thuộc “thế hệ” nào khi bị xóa rồi tái sử dụng. Trong hệ thống thực tế, cần thêm kiểm soát quyền sở hữu và vòng đời công việc.

## 18. Xóa lười: phải tách thứ tự đến và phiên bản cập nhật

Python `heapq` không có API xóa theo ID hoặc `decrease-key` trực tiếp. Một phương án khác là **lazy deletion**:

- Khi đổi priority, đẩy một bản ghi mới vào heap.
- Bản ghi cũ vẫn nằm trong heap nhưng được xem là **hết hiệu lực** (*stale*).
- Khi pop, bỏ qua những bản ghi stale.

Muốn giữ ổn định, ta phải phân biệt:

1. **`arrival_sequence`:** thứ tự đến của **công việc logic**.
2. **`version`:** phiên bản **của bản ghi vật lý** sau mỗi lần cập nhật.

Nếu dùng **một** counter mới cho cả thứ tự đến và phiên bản, việc cập nhật priority có thể vô tình thay đổi “tuổi” công việc, kể cả khi chính sách yêu cầu giữ tuổi ban đầu.

### Ví dụ

```text
A được enqueue trước B:

A: arrival=0, priority=5, version=0
B: arrival=1, priority=2, version=1

Giảm priority của A xuống 2, giữ arrival=0:

Heap vật lý có thể chứa:
  (5, arrival=0, version=0, A)  <- stale
  (2, arrival=1, version=1, B)  <- active
  (2, arrival=0, version=2, A)  <- active

A cần được lấy trước B vì cùng priority=2 và arrival(A)=0.
```

Để phân biệt hai bản ghi của cùng A, cần `version` khác nhau. Nếu không, một lần pop trên bản ghi cũ có thể bị nhận nhầm là bản ghi đang hoạt động.

## 19. Cài đặt lazy stable priority queue bằng heapq

Mã dưới dùng khóa vật lý:

```text
(priority, arrival, version, job_id)
```

Trong đó:

- `priority` quyết định mức ưu tiên.
- `arrival` bảo toàn thứ tự đến cho các công việc còn hoạt động.
- `version` phân biệt các bản ghi cũ/mới của cùng ID.
- `job_id` dùng tra cứu và trả kết quả.

Vì `arrival` và `version` được cấp đơn điệu, phép so sánh tuple không cần phụ thuộc vào việc hai `job_id` có so sánh được hay không.

```python
import heapq
from itertools import count


class LazyStableMinQueue:
    def __init__(self) -> None:
        self.heap: list[tuple[int, int, int, str]] = []
        self.active: dict[str, tuple[int, int, int]] = {}
        self.arrivals = count()
        self.versions = count()

    def add(self, job_id: str, priority: int) -> None:
        if job_id in self.active:
            raise ValueError("ID đang hoạt động")
        arrival = next(self.arrivals)
        version = next(self.versions)
        self.active[job_id] = (priority, arrival, version)
        heapq.heappush(
            self.heap, (priority, arrival, version, job_id)
        )

    def change_priority(self, job_id: str, priority: int) -> None:
        _, arrival, _ = self.active[job_id]  # KeyError nếu chưa có.
        version = next(self.versions)
        self.active[job_id] = (priority, arrival, version)
        heapq.heappush(
            self.heap, (priority, arrival, version, job_id)
        )

    def requeue(self, job_id: str, priority: int) -> None:
        # Chính sách: cập nhật được xem là một lượt đến mới.
        _ = self.active[job_id]
        arrival = next(self.arrivals)
        version = next(self.versions)
        self.active[job_id] = (priority, arrival, version)
        heapq.heappush(
            self.heap, (priority, arrival, version, job_id)
        )

    def cancel(self, job_id: str) -> None:
        # Xóa logic; các bản ghi cũ còn lại sẽ bị bỏ qua lúc pop.
        del self.active[job_id]

    def pop(self) -> tuple[str, int]:
        while self.heap:
            priority, arrival, version, job_id = heapq.heappop(
                self.heap
            )
            if self.active.get(job_id) == (
                priority, arrival, version
            ):
                del self.active[job_id]
                return job_id, priority
            # Stale: bản ghi đã bị thay thế, hủy hoặc pop trước đó.

        raise IndexError("Không còn công việc hợp lệ")

    def __len__(self) -> int:
        return len(self.active)


q = LazyStableMinQueue()
q.add("A", 5)              # arrival A = 0
q.add("B", 2)              # arrival B = 1
q.change_priority("A", 2)  # A vẫn có arrival = 0

print(q.pop())             # ('A', 2)
print(q.pop())             # ('B', 2)
print(len(q))              # 0

r = LazyStableMinQueue()
r.add("A", 5)
r.add("B", 2)
r.requeue("A", 2)          # arrival mới lớn hơn B
print(r.pop())             # ('B', 2)
print(r.pop())             # ('A', 2)
```

### Phân biệt số công việc hoạt động và số bản ghi vật lý

Gọi `n` là số ID đang hoạt động trong `active` và `m` là tổng số bản ghi vật lý trong `heap`, gồm cả stale:

- `len(queue)` trong ví dụ trả **`n`**.
- Sau rất nhiều lần cập nhật, `m` có thể **lớn hơn `n` đáng kể**.
- Mỗi `heappush` có chi phí `O(\log(m+1))` thông dụng.
- Một lần `pop` có thể phải loại **nhiều** bản ghi stale trước khi trả một mục hợp lệ; không thể kết luận nó luôn `O(\log n)` khi xét từng lần gọi.
- Có thể định kỳ lọc các bản ghi đang hiệu lực rồi `heapify` lại để giới hạn dung lượng giữ stale.

**So với indexed heap**, lazy deletion tránh duy trì bảng `id\to index` sau mỗi lần swap, nhưng phải đánh đổi bộ nhớ lưu nhiều phiên bản và chi phí dọn stale.

## 20. Một lỗi tinh vi: xóa rồi tái sử dụng ID

Giả sử một công việc `A` bị hủy, nhưng các bản ghi vật lý cũ vẫn còn trong heap lazy. Sau đó hệ thống thêm một công việc **mới** cũng dùng ID `A`.

Nếu bảng trạng thái chỉ ghi:

```text
active[A] = True
```

thì bản ghi cũ có thể bị nhận nhầm là công việc mới.

### Cách bảo vệ

- Dùng **ID không tái sử dụng**, nếu điều kiện nghiệp vụ cho phép.
- Hoặc gắn mỗi lần thêm mới một **generation/version duy nhất**.
- Khi pop, chỉ chấp nhận bản ghi khớp **toàn bộ thông tin nhận diện phiên bản hiện hành**, không chỉ khớp ID hay priority.

Trong lớp `LazyStableMinQueue` ở phần 19, `version` mới được cấp cho **mỗi lần add/change/requeue**, nên một bản ghi cũ của A sẽ không có version trùng với lần thêm lại mới.

Tương tự, trong indexed heap, việc giữ một **chỉ số mảng cũ** để truy cập mục mới có cùng ID cũng có thể gây lỗi. Tính ổn định của thứ tự ưu tiên và tính an toàn của định danh là **hai vấn đề khác nhau**, đều cần hợp đồng rõ ràng.

## 21. Tính ổn định trong môi trường đồng thời và phân tán

Với một hàng đợi trong **một luồng**, gọi `next(sequence)` khi enqueue thường đủ để xác định một thứ tự rõ ràng.

Với **nhiều luồng** hoặc **nhiều máy**, phải trả lời hai câu hỏi:

1. **Ai cấp số thứ tự duy nhất?**
2. **Thứ tự enqueue thực sự được xác lập tại điểm nào?**

### Nhiều luồng cùng thao tác một heap

Nếu hai luồng cùng đọc/ghi bộ đếm và heap mà không có cơ chế đồng bộ, có thể:

- Cấp **cùng một sequence** cho hai phần tử.
- Chèn phần tử theo thứ tự vật lý khác với thứ tự mà API công bố.
- Làm hỏng chính mảng heap khi nhiều thao tác sửa cùng lúc.

Do đó, cần một **giao thức nguyên tử/khóa** bao gồm việc cấp sequence và cập nhật heap, hoặc một kiến trúc có một đầu mối tuần tự hóa thao tác. Chỉ dùng bộ đếm cấp ticket nguyên tử mà không đồng bộ heap vẫn chưa đủ để biến các thao tác priority queue thành thread-safe.

### Nhiều máy cùng ghi

Một timestamp của máy A không nhất thiết so sánh tin cậy được với máy B. Nếu cần một thứ tự toàn cục thật sự, có thể cần:

- Bộ cấp sequence tập trung hoặc dịch vụ **sequencer**.
- Log sự kiện có chỉ số vị trí xác định.
- Một cơ chế đồng thuận/xác định thứ tự mà toàn bộ bên tham gia tuân theo.

**Không thể bảo đảm FIFO theo thứ tự đến “ngoài đời” giữa những sự kiện hoàn toàn đồng thời nếu chưa quy định cách xác lập thứ tự.** Hệ thống phải chọn một quan hệ thứ tự có thể quan sát và kiểm chứng được.

### Tràn số thứ tự

Trong Python, số nguyên có độ dài linh hoạt nên bộ đếm ít có nguy cơ tràn theo kiểu `int32`/`int64`. Với ngôn ngữ dùng số nguyên cố định, khi sequence quay vòng, giá trị mới có thể **nhỏ hơn giá trị cũ** và làm sai FIFO.

Một giải pháp là dùng kiểu đủ rộng với chính sách an toàn, phiên bản/epoch hoặc tái đánh số có kiểm soát; không được âm thầm để bộ đếm quay vòng khi còn các mục cũ cần so sánh.

## 22. Tính ổn định không đồng nghĩa với tính công bằng tổng thể

Stable priority queue bảo đảm FIFO khi **hai công việc có cùng priority**, nhưng **không bảo đảm** một công việc có priority thấp sẽ sớm được chạy.

Ví dụ min-priority queue:

```text
Job L: priority = 9
Liên tục có job H1, H2, H3, ... priority = 1
```

Nếu lúc nào cũng có một job priority `1` đang chờ, job L priority `9` có thể bị trì hoãn rất lâu, dù nó vào hàng đợi trước.

Đó là **starvation** (thiếu cơ hội phục vụ), và tính ổn định **không tự giải quyết**.

### Một số chính sách công bằng cần thiết nếu ứng dụng yêu cầu

- **Aging:** tăng dần mức ưu tiên thực tế của công việc đã chờ lâu.
- **Quota theo mức ưu tiên:** phân bổ một tỷ lệ thời gian cho mỗi nhóm.
- **Weighted fair scheduling:** phục vụ nhiều nhóm theo trọng số.
- **Round-robin giữa các nhóm:** tránh để một nhóm luôn chiếm hết tài nguyên.

Nếu dùng aging làm thay đổi **priority theo thời gian**, phải thiết kế cách **cập nhật khóa**. Không thể chỉ đổi thuộc tính `priority` của đối tượng bên trong heap và giả định heap-order vẫn hợp lệ.

### Tại sao cần tách hai khái niệm?

| Tính chất | Câu hỏi được giải quyết |
|---|---|
| **Ổn định** | Khi hai việc **cùng priority**, việc đến trước có được lấy trước không? |
| **Công bằng** | Các mức ưu tiên/nhóm khác nhau có được chia cơ hội phục vụ hợp lý không? |
| **Không bỏ đói** | Một công việc có thể phải chờ mãi dù hệ thống tiếp tục chạy không? |
| **Đúng hạn** | Công việc có hoàn thành trước deadline được không? |

Một hệ thống có thể ổn định nhưng không công bằng; cũng có thể công bằng giữa các nhóm mà không FIFO trong từng nhóm. Cần quy định riêng từng mục tiêu.

## 23. Phương án thay thế: một queue FIFO cho mỗi mức ưu tiên

Nếu số mức ưu tiên **nhỏ và cố định**, không nhất thiết phải gán sequence cho từng phần tử trong một heap.

Ví dụ có đúng ba cấp `0,1,2`, với `0` ưu tiên cao nhất. Ta có thể duy trì **một queue FIFO cho mỗi cấp**:

```text
priority 0: [D]       <- FIFO
priority 1: [B, E]    <- FIFO
priority 2: [A, C]    <- FIFO

Mỗi lần lấy: chọn queue ưu tiên cao nhất không rỗng,
sau đó pop đầu của queue đó.
```

### Mã Python

```python
from collections import deque

queues = {0: deque(), 1: deque(), 2: deque()}


def put(priority: int, name: str) -> None:
    queues[priority].append(name)


def take() -> str:
    for priority in (0, 1, 2):
        if queues[priority]:
            return queues[priority].popleft()
    raise IndexError("Tất cả hàng đợi đều rỗng")


put(2, "A")
put(1, "B")
put(2, "C")
put(0, "D")

print([take() for _ in range(4)])  # ['D', 'B', 'A', 'C']
```

Mỗi `deque.append` và `deque.popleft` thường `O(1)`. Việc tìm nhóm không rỗng tốn `O(K)` nếu quét `K` cấp ưu tiên; với `K=3` là hằng số nhỏ.

Nếu `K` lớn hoặc mức ưu tiên biến động, có thể dùng thêm **heap cho các cấp ưu tiên đang có việc**, còn mỗi cấp giữ một `deque` FIFO. Cách này phức tạp hơn về đồng bộ hai cấu trúc nhưng giảm chi phí tìm nhóm trong nhiều trường hợp.

### Khi nào chọn cách nào?

| Bài toán | Thiết kế đáng cân nhắc |
|---|---|
| Priority là số nguyên trong vài mức cố định | Mảng/dict các `deque`, quét mức |
| Priority gần như liên tục, có nhiều mức | Heap với khóa `(priority,sequence)` |
| Cần update/cancel theo ID liên tục | Stable indexed heap hoặc cấu trúc hỗ trợ handle |
| Muốn tận dụng `heapq` và chấp nhận stale | Lazy stable heap với version |
| Nhiều công việc trong từng nhóm, cần FIFO rõ ràng | `deque` riêng mỗi nhóm |

Khả năng giữ ổn định là **một yêu cầu hành vi**, không buộc mọi ứng dụng phải sử dụng heap. Hãy chọn cấu trúc phù hợp với số nhóm ưu tiên, tần suất sửa/xóa và giới hạn bộ nhớ.

## 24. Những lỗi dễ mắc

| Lỗi/hiểu nhầm | Vì sao sai? | Cách khắc phục |
|---|---|---|
| “Heap có khóa bằng nhau sẽ tự FIFO.” | Heap-order không phân biệt các khóa bằng nhau | Thêm sequence vào khóa |
| “Chọn con trái khi hòa là đủ ổn định.” | Pop gốc vẫn có thể đưa mục đến sau lên trước | So toàn bộ khóa ghép |
| “Mảng heap phải giữ thứ tự chèn.” | Ổn định yêu cầu **thứ tự pop**, không phải vị trí nội bộ | Kiểm thử đầu ra |
| “Max-heap dùng `(-priority,-sequence)` để FIFO.” | `-sequence` ưu tiên mục đến **sau** | Dùng `(-priority,sequence)` với min-heap |
| “Timestamp luôn duy nhất.” | Có thể trùng hoặc lệch đồng hồ | Dùng ticket đơn điệu |
| “Có thể dùng `(priority,payload)` với dict.” | Khi priority hòa, Python so sánh payload và có thể `TypeError` | Thêm sequence duy nhất |
| “Chỉ cần dataclass có `order=True`.” | Nó không tự sinh thứ tự đến | Cấp sequence khi enqueue |
| “Sequence có thể trùng mà không ảnh hưởng.” | Khi cùng priority, phép so có thể hòa | Bảo đảm sequence duy nhất |
| “Đổi priority không ảnh hưởng vị trí khi số không đổi.” | Sequence có thể được cấp mới dù priority giữ nguyên | So toàn bộ `(priority,sequence)` |
| “Giảm khóa trong min-heap luôn cần sift-down.” | Giảm khóa có thể vi phạm với cha | Sift-up dựa trên khóa ghép |
| “Tìm theo ID trong heap có `O(\log n)`.” | Heap chỉ có thứ tự bộ phận theo priority | Indexed heap hoặc bảng handle |
| “Lazy deletion chỉ cần kiểm tra ID.” | ID có thể có nhiều phiên bản vật lý | Kiểm tra version và trạng thái active |
| “Dùng chung arrival và version là luôn đúng.” | Update tạo bản ghi mới có thể thay tuổi công việc | Tách hai trường theo hợp đồng |
| “Heapify phá tính ổn định dù đã có sequence.” | Heapify so toàn bộ khóa ghép nên vẫn có thứ tự pop đúng | Gắn sequence **trước** heapify |
| “Hệ thống đồng thời chỉ cần bộ đếm nguyên tử.” | Còn phải đồng bộ thao tác heap và định nghĩa thứ tự enqueue | Một giao thức nguyên tử nhất quán |
| “Stable priority queue không bao giờ bỏ đói việc thấp.” | Priority cao liên tục có thể chiếm hết lượt | Cần chính sách fairness/aging |
| “Khóa số thực luôn có thứ tự tin cậy.” | `NaN` có thể phá tính nhất quán của `<` và `<=` | Chuẩn hóa hoặc loại khóa không hợp lệ |
| “Đảo dấu mọi trường để làm max-heap.” | Đảo sequence làm sai chính sách FIFO | Chỉ đảo chiều priority |

### Lưu ý riêng về khóa có giá trị NaN

Với số thực IEEE 754, `NaN` không tuân theo quan hệ thứ tự thông thường: các so sánh `NaN < x`, `NaN > x` và `NaN == x` không có tính chất như số hữu hạn. Kể cả khi có sequence, nếu priority không có một quan hệ so sánh **nhất quán**, không nên giả định heap sẽ duy trì được quy tắc chọn ưu tiên như mong muốn.

Có thể từ chối `NaN` khi enqueue, hoặc chuẩn hóa thành một giá trị sentinel có thứ tự được định nghĩa rõ. Quyết định này cần nằm trong hợp đồng API.

## 25. Kiểm thử tính ổn định

Kiểm thử ổn định không chỉ hỏi “gốc có priority nhỏ nhất không?”. Nó cần kiểm tra **toàn bộ thứ tự pop** trong các tình huống hòa priority.

### Các trường hợp nên có

1. Nhiều phần tử cùng priority, không có phần tử khác.
2. Nhiều nhóm priority đan xen theo thứ tự enqueue.
3. Có `heapify` từ danh sách đầu vào.
4. Có phần tử bị hủy khi đang chờ.
5. Có thay priority theo chính sách **giữ arrival**.
6. Có thay priority theo chính sách **requeue arrival mới**.
7. Có ID bị xóa rồi thêm lại, tránh nhận nhầm phiên bản cũ.
8. Có payload không so sánh được.
9. Có nhiều thao tác đồng thời theo hợp đồng thứ tự được chọn.
10. Có số lượng mục lớn, sequence rất lớn hoặc gần giới hạn kiểu số.

### Kiểm thử với một mô hình tham chiếu

Đối với hàng đợi **không thay khóa, không hủy**, có thể so kết quả pop của `heapq` với một phép sắp xếp theo `(priority,sequence)`:

```python
import heapq

arrivals = [
    ("A", 2),
    ("B", 1),
    ("C", 2),
    ("D", 1),
    ("E", 2),
]

entries = [
    (priority, index, name)
    for index, (name, priority) in enumerate(arrivals)
]

expected = [name for _, _, name in sorted(entries)]

heap = entries.copy()
heapq.heapify(heap)
actual = [heapq.heappop(heap)[2] for _ in range(len(heap))]

assert actual == expected
assert actual == ["B", "D", "A", "C", "E"]
```

Ở đây, `sorted` được dùng để tạo **mô hình tham chiếu**, không phải để thay thế thao tác heap trong một hàng đợi có dữ liệu đến liên tục. Bài kiểm thử trên xác minh thứ tự đầu ra, không chứng minh khả năng đúng với mọi chuỗi update/cancel.

### Kiểm thử theo bất biến

Đối với indexed heap, ngoài so sánh đầu ra, cần kiểm tra:

\[
K(H[parent(i)])\le K(H[i])
\]

cho mọi `i>0` và:

\[
position[H[i].id]=i
\]

cho mọi chỉ số hợp lệ. Phép kiểm tra toàn bộ này thường mất `O(n)`, phù hợp cho kiểm thử/debug hơn là chạy sau **mỗi** thao tác trong đường xử lý cần hiệu năng cao.

## 26. Bài tập tự kiểm tra

**Bài 1.** Một min-heap nhận lần lượt `A(1)`, `B(1)`, `C(1)`. Nếu chỉ so priority, vì sao chuỗi pop có thể là `A,C,B` thay vì `A,B,C`?

**Bài 2.** Định nghĩa ngắn gọn “ổn định” trong hàng đợi ưu tiên. Nó có đồng nghĩa với FIFO toàn cục không?

**Bài 3.** Các phần tử `A(2)`, `B(1)`, `C(2)`, `D(1)` đến theo thứ tự đã ghi. Hãy gán sequence bắt đầu từ `0` và cho biết thứ tự pop của stable min-heap.

**Bài 4.** Viết điều kiện so sánh hai cặp khóa `(priority,sequence)` theo thứ tự từ điển.

**Bài 5.** Tại sao quy tắc “khi hai con có cùng priority thì chọn con trái” không đủ bảo đảm FIFO?

**Bài 6.** Với max-priority queue dùng min-heap trên số nguyên, chọn khóa `(-priority,sequence)` hay `(-priority,-sequence)` để giữ FIFO khi bằng priority?

**Bài 7.** Một ứng dụng lưu `(priority,payload)`, trong đó payload là `dict`. Vì sao có thể gặp `TypeError`? Thiết kế lại khóa để tránh lỗi.

**Bài 8.** Nếu hai mục cùng priority và cùng sequence, điều gì có thể xảy ra? Cách tạo sequence nào đơn giản và đáng tin cậy trong một hàng đợi tuần tự?

**Bài 9.** Hai yêu cầu có cùng timestamp. Vì sao timestamp không đủ phân định thứ tự? Có thể bổ sung trường nào?

**Bài 10.** Công việc A enqueue ở thời điểm 1 với priority 5; B, C enqueue ở thời điểm 2 và 3 với priority 2. A được đổi sang priority 2 tại thời điểm 4. Nếu giữ arrival ban đầu, thứ tự giữa A, B, C là gì? Nếu requeue A, thứ tự là gì?

**Bài 11.** Trong min-heap ổn định, priority của một mục không đổi nhưng sequence được cấp lại thành số lớn hơn. Có thể cần `sift-up` hay `sift-down` không?

**Bài 12.** Một lazy priority queue giữ bản ghi cũ khi đổi priority. Vì sao cần **version riêng**, không chỉ `arrival_sequence`?

**Bài 13.** Với bảng băm `active[id]=(priority,arrival,version)`, khi pop một bản ghi từ heap, điều kiện nào cho biết bản ghi đó còn hợp lệ?

**Bài 14.** Cho `n` phần tử và các khóa kích thước cố định. Việc thêm sequence vào tuple có làm `push`/`pop` đổi từ `O(\log n)` thành `O(n)` không? Vì sao?

**Bài 15.** Một stable heap xây bằng `heapify` từ danh sách `A(2),B(1),C(2),D(1)`. Tính ổn định có được giữ nếu sequence được gán theo thứ tự đầu vào trước heapify không?

**Bài 16.** Hệ thống có `K=3` mức ưu tiên cố định, mỗi mức cần FIFO. Hãy đề xuất cấu trúc khác ngoài heap và phân tích chi phí thêm/lấy.

**Bài 17.** Vì sao một stable priority queue vẫn có thể **starvation** cho công việc ưu tiên thấp? Hãy nêu một giải pháp fairness.

**Bài 18.** Nếu hai luồng cùng enqueue, vì sao cấp sequence duy nhất thôi chưa chắc đủ an toàn?

**Bài 19.** Hai máy dùng thời gian đồng hồ riêng để sắp cùng một hàng đợi toàn cục. Rủi ro nào phát sinh? Nêu một cơ chế xác lập thứ tự thay thế.

**Bài 20.** Nếu một ID bị hủy rồi được tái sử dụng, tại sao bản ghi stale có thể nguy hiểm? Gợi ý cách phòng tránh.

### Đáp án và giải thích

1. Sau khi lấy A, binary heap đưa phần tử cuối C lên gốc; cả C và B có cùng priority nên `sift-down` có thể dừng. Khi đó C được lấy trước B mà heap-order vẫn đúng.
2. Ổn định nghĩa là **với các mục cùng priority đang chờ**, mục được enqueue sớm hơn được pop trước theo chính sách đã định. FIFO toàn cục không xét priority, nên khác.
3. A=(2,0), B=(1,1), C=(2,2), D=(1,3). Thứ tự pop: **B, D, A, C**.
4. `(p1,s1)<(p2,s2)` nếu `p1<p2`, hoặc `p1=p2` và `s1<s2`.
5. Việc thay gốc bằng phần tử cuối khi pop có thể đưa phần tử đến sau lên trước mà không cần chọn giữa hai con. Chọn con trái không mã hóa thứ tự enqueue.
6. Dùng **`(-priority,sequence)`**; priority lớn được lấy trước, nhưng sequence nhỏ vẫn được lấy trước khi priority bằng nhau.
7. Khi priority hòa, Python so sánh tiếp `dict` và có thể `TypeError`. Dùng `(priority,unique_sequence,payload)` hoặc dataclass với payload `compare=False`.
8. Khóa ghép có thể vẫn hòa, kéo theo tiêu chí so sánh khác hoặc phụ thuộc chi tiết heap. Dùng counter đơn điệu cấp một ticket khác nhau cho mỗi lượt enqueue.
9. Timestamp có thể trùng vì độ phân giải hoặc do các sự kiện đồng thời. Bổ sung sequence duy nhất hoặc một cơ chế phân thứ tự được xác lập.
10. Giữ arrival: **A, B, C**. Requeue A sau khi đổi mức: **B, C, A**.
11. Có thể cần **sift-down** vì khóa `(priority,new_sequence)` tăng dù priority giữ nguyên. Phải so toàn bộ khóa ghép.
12. Bản ghi mới và cũ có thể cùng arrival vì muốn giữ tuổi công việc. Version tách biệt giúp phát hiện bản ghi nào đang hiệu lực.
13. Chỉ chấp nhận nếu `active.get(id)==(priority,arrival,version)` của bản ghi vừa lấy. Nếu khác hoặc ID không còn active, đó là stale.
14. Không. Với hai số có so sánh `O(1)`, khóa ghép chỉ tăng hằng số thao tác; heap vẫn có chiều cao `O(\log n)`, nên `push`/`pop` vẫn `O(\log n)`.
15. Có. `heapify` duy trì heap-order theo khóa đã có `(priority,sequence)`; thứ tự pop là **B, D, A, C**, dù các ô nội bộ có thể đổi chỗ.
16. Dùng **ba `deque`**, mỗi mức một FIFO. Enqueue và dequeue trong nhóm là `O(1)`; quét ba mức để tìm nhóm cao nhất không rỗng cũng `O(1)` vì `K=3` cố định.
17. Nếu luôn có công việc priority cao, việc thấp có thể bị trì hoãn vô hạn dù FIFO trong nhóm. Có thể dùng aging, quota, round-robin theo nhóm hoặc weighted fair scheduling.
18. Hai luồng có thể cùng sửa mảng heap và bảng ánh xạ, gây race dù ticket không trùng. Cần đồng bộ thao tác cấp sequence **và** cập nhật cấu trúc theo hợp đồng.
19. Clock skew, timestamp trùng và chỉnh giờ có thể đảo thứ tự. Dùng sequencer tập trung, thứ tự trong một log được thống nhất hoặc giao thức sắp thứ tự phân tán phù hợp.
20. Một bản ghi stale mang ID cũ có thể bị nhận nhầm là công việc mới. Dùng ID không tái sử dụng hoặc kết hợp ID với generation/version được kiểm tra khi pop.

## 27. Ghi nhớ

**Heap thông thường không ổn định khi nhiều phần tử cùng priority**, vì bất biến chỉ so khóa cha–con, và `pop` có thể đưa phần tử đến sau lên gốc. Muốn bảo đảm **FIFO trong mỗi mức ưu tiên**, hãy so **khóa ghép `(priority,sequence)`** với sequence duy nhất tăng theo thứ tự enqueue; trong max-heap dùng min-heap đảo dấu khóa số, giữ **`(-priority,sequence)`**, không đảo chiều sequence. Tính ổn định là thuộc tính của **thứ tự pop**, không phải yêu cầu mảng heap giữ nguyên thứ tự vật lý. Nếu có thao tác đổi mức ưu tiên, phải quy định rõ **giữ arrival ban đầu** hay **requeue bằng sequence mới**; nếu dùng lazy deletion, tách **arrival** khỏi **version** để phân biệt bản ghi cũ. Indexed heap cần so toàn bộ khóa ghép và cập nhật ánh xạ sau mọi swap. Với khóa kích thước cố định, việc bổ sung sequence không đổi các cận `O(\log n)` cho push/pop hay `O(n)` cho heapify, nhưng tốn thêm bộ nhớ và công quản lý ticket. Cuối cùng, **ổn định không đồng nghĩa với công bằng**: nếu hệ thống cần tránh bỏ đói công việc hoặc làm việc đồng thời/phân tán, phải thiết kế thêm chính sách fairness và cơ chế xác lập thứ tự nhất quán.
