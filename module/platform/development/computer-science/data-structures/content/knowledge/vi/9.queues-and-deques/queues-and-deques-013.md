# Phân biệt hàng đợi thường với hàng đợi ưu tiên

**Hàng đợi thường** (*queue*) và **hàng đợi ưu tiên** (*priority queue*) đều là những kiểu dữ liệu trừu tượng quản lý tập phần tử đang chờ. Điểm khác biệt quyết định nằm ở câu hỏi: **phần tử nào được lấy ra tiếp theo?**

- **Queue thường** phục vụ theo **thứ tự đến**, tuân thủ FIFO (*First In, First Out*): ai vào trước, ra trước.
- **Priority queue** phục vụ theo **mức ưu tiên**: phần tử có khóa ưu tiên tốt nhất được lấy trước, dù nó mới đến sau. Khi nhiều phần tử có cùng mức ưu tiên, thứ tự giữa chúng **phụ thuộc quy tắc hòa** của hệ thống.

Ví dụ bốn công việc được gửi theo thứ tự `A → B → C → D`, với độ ưu tiên số nhỏ hơn nghĩa là cấp bách hơn:

| Công việc | Thứ tự đến | Độ ưu tiên |
|---|---:|---:|
| `A` | 1 | 3 |
| `B` | 2 | 1 |
| `C` | 3 | 1 |
| `D` | 4 | 2 |

Nếu **cả bốn đã được đưa vào trước khi bắt đầu lấy**:

```text
Queue FIFO:
 A → B → C → D

Priority queue, mức số nhỏ được lấy trước,
và giữ FIFO khi bằng mức:
 B → C → D → A
```

Sự khác biệt không nằm ở việc phần tử được lưu trong mảng hay danh sách liên kết. Đó là **hợp đồng thứ tự lấy phần tử**.

Bài thuộc chương **Hàng đợi và deque** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Trong lộ trình học cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, mục tiêu là hiểu **bất biến**, **thao tác**, **chi phí thời gian và bộ nhớ**, rồi chọn cấu trúc phù hợp. Bài tập trung vào việc phân biệt hai ADT, cách hiện thực chúng, tác động của thứ tự ưu tiên và các ứng dụng thuật toán tiêu biểu.

## 1. Queue thường: hợp đồng FIFO

Queue thông thường có hai thao tác cốt lõi:

- `enqueue(x)`: thêm `x` vào **cuối** hàng.
- `dequeue()`: lấy và loại bỏ phần tử ở **đầu** hàng.

Có thể thêm `peek()` để đọc phần tử đầu mà không xóa, cùng `is_empty()` và `size()` để kiểm tra trạng thái.

```text
                     FIFO
dequeue()                              enqueue(D)
    |                                       |
    v                                       v
  front                                    rear
   [ A ] ───→ [ B ] ───→ [ C ]  (A được lấy trước)
   Thứ tự hiện tại: A, rồi B, rồi C; D sẽ được thêm sau C.
```

Để tránh nhầm hướng mũi tên, ta luôn viết **dãy logic từ front đến rear**: `[A, B, C]`. Khi `enqueue(D)`, dãy trở thành `[A, B, C, D]`; khi `dequeue()`, kết quả là `A` và hàng còn `[B, C, D]`.

Nếu trước khi lấy có `Q = [q₀, q₁, …, qₙ₋₁]`:

```text
enqueue(x): Q_new = [q0, q1, ..., q(n-1), x]
dequeue():  trả q0, Q_new = [q1, ..., q(n-1)]
peek():     trả q0, Q giữ nguyên
```

**Bất biến FIFO:** trong số các phần tử chưa bị lấy ra, thứ tự tương đối luôn khớp với **thứ tự enqueue thành công**. Một phần tử đến sau không thể vượt qua phần tử đến trước chỉ vì giá trị hay ý nghĩa nghiệp vụ của nó khác.

Khi queue được cài bằng **mảng vòng** hoặc **danh sách liên kết có đầu/cuối**, `enqueue`, `dequeue`, `peek` đều có thể chạy **O(1)**. Dùng Python `list.pop(0)` để xóa đầu lại có thể mất O(n) do dịch các phần tử; đó là vấn đề cách **cài đặt**, không phải thuộc tính bắt buộc của queue FIFO.

## 2. Priority queue: hợp đồng chọn phần tử tốt nhất

Priority queue thường cung cấp:

- `insert(x, priority)` hay `push(x)`: đưa một phần tử có **khóa ưu tiên** vào tập đang chờ.
- `extract_min()` hoặc `extract_max()`: lấy và xóa phần tử có **khóa tốt nhất**.
- `peek_min()` hoặc `peek_max()`: xem phần tử tốt nhất mà không xóa.
- `is_empty()`, `size()`: truy vấn trạng thái.

Có **hai quy ước phổ biến**:

| Biến thể | Phần tử được lấy tiếp theo | Ví dụ |
|---|---|---|
| **Min-priority queue** | Khóa **nhỏ nhất** | `priority = 1` được lấy trước `priority = 5` |
| **Max-priority queue** | Khóa **lớn nhất** | `priority = 9` được lấy trước `priority = 4` |

Không có quy tắc chung rằng “số càng lớn thì ưu tiên càng cao”. Một hệ thống có thể định nghĩa **1 là cấp bách nhất**, hệ thống khác có thể định nghĩa **10 là cấp bách nhất**. Cần xác định rõ **chiều so sánh** trước khi cài đặt hoặc đọc kết quả.

Min-priority queue với các công việc từ đầu bài:

```text
Các mục đang chờ:
  A (3), B (1), C (1), D (2)

Các mức ưu tiên:
  mức 1: B, C
  mức 2: D
  mức 3: A

Nếu giữ FIFO trong cùng mức:
  extract_min lần lượt → B → C → D → A
```

**Bất biến ngữ nghĩa:** mỗi lần lấy thành công phải trả một phần tử có khóa ưu tiên tốt nhất **trong tập phần tử đang chờ tại thời điểm đó**. Một công việc đã được lấy ra không tự động bị “lấy lại” khi xuất hiện công việc có mức ưu tiên cao hơn về sau.

### Priority queue không đồng nghĩa với một danh sách đã sắp xếp hoàn toàn

ADT chỉ yêu cầu **truy cập/lấy được phần tử ưu tiên nhất**. Nó không yêu cầu mọi phần tử còn lại được đặt theo thứ tự tăng hay giảm trong bộ nhớ. Chẳng hạn, **binary heap** chỉ bảo đảm quan hệ giữa nút cha và con, chứ không bảo đảm tất cả ô của mảng đều đã được sắp tăng dần.

Priority queue cũng **khác deque** (*double-ended queue*). Deque hỗ trợ thao tác nhanh ở **hai đầu theo thứ tự hiện tại**, không tự tìm phần tử có mức ưu tiên tốt nhất ở vị trí bất kỳ.

## 3. Truy vết: cùng dữ liệu, khác thứ tự phục vụ

Để so sánh công bằng, dùng **cùng thứ tự thêm** và chỉ bắt đầu lấy sau khi đã thêm đủ bốn phần tử:

```text
enqueue/insert A(3), B(1), C(1), D(2)
```

Bảng giả sử min-priority queue **ổn định khi hòa** (giữ thứ tự đến giữa các mục cùng ưu tiên):

| Lượt lấy | Queue thường (FIFO) | Priority queue (min, hòa theo FIFO) | Lý do |
|---:|---|---|---|
| 1 | `A (3)` | `B (1)` | FIFO chọn đến trước; min chọn khóa nhỏ nhất |
| 2 | `B (1)` | `C (1)` | Sau `B`, `C` vẫn có khóa nhỏ nhất |
| 3 | `C (1)` | `D (2)` | Khóa 2 tốt hơn khóa 3 |
| 4 | `D (2)` | `A (3)` | Phần tử cuối cùng còn chờ |

Nếu đổi sang **max-priority queue**, dãy lấy là `A (3), D (2), B (1), C (1)` theo quy tắc hòa FIFO.

### Thứ tự thao tác quan trọng

Giả sử chỉ vừa thêm `A(3)`, rồi lập tức gọi `extract_min()`. Khi đó priority queue **phải trả `A`**, vì chưa có `B` hay `C`. Nếu `B(1)` đến sau lúc `A` đã được lấy, nó không thể thay đổi kết quả trong quá khứ.

Do đó, đừng phát biểu rằng “priority queue luôn trả `B` trước `A`” nếu chưa nói **các phần tử nào đã có mặt tại thời điểm lấy**. Priority queue sắp thứ tự lựa chọn trong **tập đang chờ**, không biết trước các phần tử chưa đến.

## 4. Đối chiếu hai ADT theo hợp đồng

| Tiêu chí | Hàng đợi thường | Hàng đợi ưu tiên |
|---|---|---|
| Quy tắc phục vụ | **Đến trước, ra trước (FIFO)** | **Khóa ưu tiên tốt nhất ra trước** |
| Phần tử được lấy | Đầu dãy theo thứ tự đến | Cực tiểu hoặc cực đại trong tập đang chờ |
| Cần thuộc tính priority? | Không | Có khóa hoặc bộ so sánh độ ưu tiên |
| Hai mục bằng ưu tiên | Không liên quan; thứ tự đến là quy tắc chung | **Chưa chắc FIFO** nếu không quy định chính sách hòa |
| Phần tử mới có thể vượt phần tử cũ? | Không | Có, nếu được ưu tiên hơn và cả hai còn chờ |
| Cấu trúc hiện thực thông dụng | Mảng vòng, danh sách liên kết, deque | Binary heap, cây cân bằng, mảng có/không sắp xếp |
| Chi phí thông dụng | `enqueue/dequeue` O(1) | Heap: `insert/extract` O(log n), `peek` O(1) |
| Công bằng theo thời điểm đến | Tự nhiên có FIFO | Có thể cần cơ chế chống chờ quá lâu |
| Bài toán tiêu biểu | BFS, hàng chờ sự kiện có thứ tự | Dijkstra, A*, chọn tác vụ theo mức ưu tiên |

“Queue thường luôn nhanh hơn priority queue” là một cách nói quá đơn giản. Đúng là **queue FIFO hiệu quả** có thao tác cơ bản O(1), còn **priority queue dùng binary heap** thường O(log n) khi thêm/lấy; nhưng nếu dùng những cách biểu diễn khác, chi phí có thể thay đổi. Phải so sánh **ADT và cấu trúc lưu trữ cụ thể**, đồng thời xét yêu cầu thứ tự phục vụ.

## 5. Biểu diễn queue thường bằng `collections.deque`

Trong Python, `collections.deque` có `append` để thêm cuối và `popleft` để lấy đầu, phù hợp với queue FIFO:

```python
from collections import deque


class FIFOQueue:
    def __init__(self):
        self._items = deque()

    def __len__(self):
        return len(self._items)

    def is_empty(self):
        return not self._items

    def enqueue(self, value):
        self._items.append(value)

    def peek(self):
        if self.is_empty():
            raise IndexError("Queue rỗng")
        return self._items[0]

    def dequeue(self):
        if self.is_empty():
            raise IndexError("Queue rỗng")
        return self._items.popleft()


q = FIFOQueue()
for name, priority in [("A", 3), ("B", 1), ("C", 1), ("D", 2)]:
    q.enqueue((name, priority))

assert q.peek() == ("A", 3)
assert [q.dequeue()[0] for _ in range(4)] == ["A", "B", "C", "D"]
assert q.is_empty()
```

Queue thường **không xem xét** trường `priority` khi lấy: bộ `("A", 3)` được phục vụ trước `("B", 1)` đơn giản vì nó đến trước.

**Độ phức tạp:** giả định `deque.append` và `deque.popleft` O(1) ở hai đầu, mỗi enqueue/dequeue/peek là O(1); bộ nhớ cho `n` mục là O(n). Hàng rỗng được nhận biết qua số phần tử, không qua một giá trị dữ liệu cụ thể như `None`.

## 6. Priority queue với heap nhị phân

Một cách hiện thực phổ biến là **binary heap** (*đống nhị phân*) lưu trong mảng. Với **min-heap**:

> Mỗi nút cha có khóa ưu tiên **không lớn hơn** khóa của các nút con.

Min-heap có tính chất `priority(parent) ≤ priority(child)`, nên **phần tử ở gốc là một khóa nhỏ nhất** trong cả heap.

### 6.1. Tính chất hình dạng và ánh xạ chỉ số

Binary heap là **cây nhị phân hoàn chỉnh**: các mức được lấp từ trên xuống, và mức cuối được lấp từ trái sang phải. Nhờ đó ta có thể lưu bằng mảng, không cần con trỏ liên kết giữa các nút:

```text
             h[0]
            /    \
         h[1]    h[2]
         / \      / \
       h[3] h[4] h[5] h[6]

Với nút ở chỉ số i:
  parent(i)     = (i - 1) // 2       nếu i > 0
  left_child(i) = 2*i + 1
  right_child(i)= 2*i + 2
```

Ví dụ một min-heap hợp lệ với các khóa ưu tiên:

```text
                 1
               /   \
              2     1
             / \
            5   3

Mảng vật lý: [1, 2, 1, 5, 3]
```

Mảng này **không tăng dần** (`2` đứng trước `1`), nhưng vẫn đúng min-heap vì mỗi cha không lớn hơn các con. Cấu trúc chỉ bảo đảm **gốc luôn nhỏ nhất**, không bảo đảm thứ tự giữa những phần tử ngang hàng hoặc ở hai nhánh khác nhau.

### 6.2. Insert: thêm rồi “nổi” lên

Để thêm `x`:

1. Ghi `x` ở cuối mảng để giữ hình dạng cây hoàn chỉnh.
2. Trong khi khóa `x` tốt hơn (nhỏ hơn với min-heap) khóa cha, đổi `x` với cha.
3. Dừng khi quan hệ heap đúng hoặc `x` đã lên gốc.

Chiều cao của cây có `n` nút là O(log n), nên `insert` tốn **O(log n)** trong trường hợp xấu nhất.

### 6.3. Extract-min: thay gốc rồi “chìm” xuống

Để lấy phần tử nhỏ nhất:

1. Lưu giá trị ở gốc `h[0]` để trả về.
2. Lấy phần tử cuối mảng đặt vào vị trí gốc (nếu heap còn phần tử).
3. Cho phần tử mới ở gốc hoán đổi dần với **con có khóa nhỏ hơn** nếu quan hệ heap bị vi phạm.
4. Trả về phần tử nhỏ nhất đã lưu.

Quá trình chìm xuống đi qua tối đa O(log n) mức, nên `extract_min` tốn **O(log n)**. `peek_min` chỉ cần đọc gốc, **O(1)** nếu heap không rỗng.

Ở **max-heap**, đảo chiều so sánh: cha không nhỏ hơn con, gốc có khóa lớn nhất.

## 7. Python `heapq`: min-priority queue ổn định khi hòa

Thư viện chuẩn `heapq` cung cấp thao tác với **min-heap** trên một `list` Python. Nhưng heap không mặc định bảo đảm **FIFO giữa các phần tử có cùng khóa ưu tiên**. Nếu cần quy tắc hòa rõ ràng, ta có thể lưu mỗi mục theo bộ:

```text
(priority, arrival_sequence, item)
```

Python so sánh tuple từ trái sang phải: trước tiên so `priority`, sau đó so `arrival_sequence`. Dãy số thứ tự đến tăng dần khiến phần tử có cùng priority được lấy theo FIFO.

### Cài đặt lớp `StableMinPriorityQueue`

```python
import heapq
from itertools import count


class StableMinPriorityQueue:
    def __init__(self):
        self._heap = []
        self._sequence = count()

    def __len__(self):
        return len(self._heap)

    def is_empty(self):
        return not self._heap

    def insert(self, item, priority):
        entry = (priority, next(self._sequence), item)
        heapq.heappush(self._heap, entry)

    def peek(self):
        if self.is_empty():
            raise IndexError("Priority queue rỗng")
        priority, sequence, item = self._heap[0]
        return item, priority

    def extract_min(self):
        if self.is_empty():
            raise IndexError("Priority queue rỗng")
        priority, sequence, item = heapq.heappop(self._heap)
        return item, priority


pq = StableMinPriorityQueue()
pq.insert("A", 3)
pq.insert("B", 1)
pq.insert("C", 1)
pq.insert("D", 2)

assert pq.peek() == ("B", 1)
assert [
    pq.extract_min()[0] for _ in range(4)
] == ["B", "C", "D", "A"]
assert pq.is_empty()
```

Các chi tiết quan trọng:

- **`priority` ở vị trí đầu tuple** quyết định độ ưu tiên chính. Số nhỏ hơn được lấy trước.
- **`sequence` tăng đơn điệu** và duy nhất giữa các lần chèn của queue này, nên giải quyết hòa theo thứ tự đến.
- **`item` ở vị trí cuối** không cần hỗ trợ toán tử so sánh nếu `sequence` là duy nhất, vì khi hai mục có cùng priority thì thứ tự sequence đã phân định.
- `peek()` không xóa mục; `extract_min()` xóa và trả đúng một mục.
- Hai lời gọi trên ném `IndexError` nếu queue rỗng. Không được dùng giá trị `None` làm dấu hiệu chắc chắn không có dữ liệu, vì `None` có thể chính là một `item` hợp lệ.

Ví dụ thử phần tử không so sánh được trực tiếp:

```python
pq = StableMinPriorityQueue()

first = {"task": "Ghi log"}
second = {"task": "Gửi thông báo"}

pq.insert(first, priority=2)
pq.insert(second, priority=2)

assert pq.extract_min()[0] is first
assert pq.extract_min()[0] is second
```

Nếu heap chỉ lưu `(priority, item)`, hai mục có priority bằng nhau có thể khiến Python cố so sánh hai dictionary và báo lỗi. Thêm bộ đếm ở giữa tránh sự phụ thuộc đó.

### Max-priority queue trong trường hợp priority là số

Với khóa ưu tiên là **số thực hữu hạn** và ý nghĩa “số lớn hơn là ưu tiên cao hơn”, có thể biến đổi khóa thành số đối `-priority` để dùng cùng một min-heap:

```python
import heapq
from itertools import count

heap = []
seq = count()

for item, priority in [
    ("A", 3), ("B", 1), ("C", 1), ("D", 2)
]:
    heapq.heappush(heap, (-priority, next(seq), item))

order = [heapq.heappop(heap)[2] for _ in range(len(heap))]
assert order == ["A", "D", "B", "C"]
```

Đây là kỹ thuật dành cho khóa số thích hợp; với chuỗi, tuple nhiều trường hoặc thứ tự so sánh tùy biến, không thể đơn giản đặt dấu trừ. Nếu có giá trị `NaN`, các phép so sánh số cũng không còn tính chất thứ tự toàn phần cần thiết cho heap; nên chuẩn hóa hoặc từ chối các khóa không hợp lệ.

## 8. Cùng một tên “priority queue”, nhiều cấu trúc lưu trữ

Priority queue là **hợp đồng lựa chọn ưu tiên**, không đồng nghĩa bắt buộc phải dùng binary heap. Nếu có `n` mục đang chờ:

| Cách hiện thực min-priority queue | Insert | Extract-min | Peek-min | Bộ nhớ |
|---|---:|---:|---:|---:|
| Mảng **không sắp xếp** | O(1) khấu hao khi thêm cuối mảng động | O(n) để tìm mục nhỏ nhất | O(n) nếu không lưu riêng min | O(n) |
| Mảng **sắp xếp** phù hợp để lấy ở cuối | O(n) vì phải dời phần tử khi chèn | O(1) ở đầu thích hợp | O(1) | O(n) |
| **Binary min-heap** | **O(log n)** | **O(log n)** | **O(1)** | **O(n)** |
| Cây tìm kiếm cân bằng có xử lý khóa trùng | O(log n) | O(log n) | O(log n), hoặc O(1) nếu giữ con trỏ min | O(n) |

Đối với mảng sắp xếp, ta có thể đặt khóa **nhỏ nhất ở cuối** để lấy trong O(1); lúc chèn cần tìm vị trí và dịch phần tử, thường O(n). Nếu chọn khóa nhỏ nhất ở đầu và dùng mảng đặc phải dịch khi xóa, `extract_min` sẽ O(n), cho thấy bảng độ phức tạp phụ thuộc **quy ước cài đặt cụ thể**.

Binary heap tạo ra sự cân bằng hợp lý khi hệ thống có **cả nhiều lần thêm và nhiều lần lấy**. Mảng không sắp xếp có thể tốt nếu thêm rất nhiều nhưng lấy cực tiểu rất ít; mảng sắp xếp có thể phù hợp khi phần lớn thao tác là xem/lấy và rất hiếm khi chèn.

### Tạo heap từ mảng có sẵn

Nếu đã có `n` phần tử lưu trong mảng, có thể gọi `heapq.heapify` để chuyển **cả mảng** thành heap trong **O(n)** thời gian theo thuật toán xây heap từ dưới lên. Điều này tốt hơn việc nhất thiết gọi `heappush` lần lượt `n` lần (cận trên O(n log n)) nếu toàn bộ dữ liệu đã sẵn.

```python
import heapq

priorities = [7, 2, 9, 1, 5, 3]
heapq.heapify(priorities)

assert priorities[0] == 1
assert [heapq.heappop(priorities) for _ in range(6)] == [
    1, 2, 3, 5, 7, 9
]
```

`heapify` không trả danh sách được sắp xếp. Nó chỉ tổ chức lại mảng để duy trì **bất biến heap**. Chỉ khi lần lượt `heappop`, ta mới thu được thứ tự tăng dần.

## 9. Thứ tự hòa, tính công bằng và hiện tượng đói tài nguyên

### 9.1. Cùng ưu tiên thì lấy ai trước?

Bất biến heap min chỉ yêu cầu một phần tử có khóa nhỏ nhất nằm ở gốc. Nếu có nhiều mục bằng nhau, heap có thể chọn **bất kỳ** mục nào trong số đó, tùy thứ tự hoán đổi và cách so sánh.

Ví dụ:

```text
B(1) đến trước C(1).

Một min-priority queue không định nghĩa chính sách hòa:
    B hay C đều có thể được chọn trước.

Min-priority queue ổn định theo thời điểm đến:
    B phải được chọn trước C.
```

Nếu cần **FIFO trong cùng mức ưu tiên**, hãy đưa thời điểm đến hoặc bộ đếm thứ tự vào khóa so sánh, chẳng hạn `(priority, sequence)`. Nếu muốn thứ tự khác, ví dụ công việc có hạn chót sớm hơn thắng khi cùng priority, định nghĩa khóa phù hợp với chính sách đó.

Trong queue FIFO thông thường, thứ tự đến **là bản chất hợp đồng**; trong priority queue, quy tắc hòa cần được nêu **riêng**.

### 9.2. Priority queue có thể khiến mục ưu tiên thấp chờ rất lâu

Giả sử luôn có những mục ưu tiên 1 mới đến trước khi bộ xử lý lấy hết chúng. Một mục ưu tiên 9 có thể bị trì hoãn **không giới hạn**, dù nó đã đến sớm. Hiện tượng này thường gọi là **starvation** (đói tài nguyên).

Một số chiến lược giảm nguy cơ:

- **Aging:** tăng dần độ ưu tiên hiệu dụng của mục đã chờ lâu.
- **Định mức hoặc phân lượt:** sau một số mục ưu tiên cao, dành lượt cho mức thấp hơn.
- **Nhiều queue theo mức ưu tiên:** quản lý FIFO trong mỗi mức, kết hợp chính sách phân bổ lượt giữa các mức.
- **Giới hạn chờ hoặc hạn chót:** đưa điều kiện thời gian chờ vào cách chọn công việc.

Những chiến lược này **thay đổi hoặc mở rộng chính sách phục vụ**, không phải tính chất tự có của binary heap. Nếu độ ưu tiên thay đổi theo thời gian, chương trình cần cập nhật cấu trúc cho đúng với khóa mới; không thể chỉ thay một trường trong đối tượng đang nằm trong heap rồi mặc nhiên bất biến heap được duy trì.

### 9.3. Priority không phải bảo đảm hoàn thành sớm

Priority queue quyết định **thứ tự lấy phần tử đang chờ**. Khi công việc đã được giao cho worker, tiến độ hoàn thành còn phụ thuộc thời gian xử lý, số worker, khả năng tạm dừng và các ràng buộc khác.

Một hệ thống không có *preemption* (ngắt công việc đang chạy) không thể lập tức dừng công việc `A` chỉ vì công việc `B` ưu tiên cao hơn vừa xuất hiện. Vì vậy, đừng đánh đồng “được lấy ra trước” với “chắc chắn hoàn tất trước”.

## 10. Ứng dụng: BFS dùng FIFO, Dijkstra dùng priority queue

Cấu trúc dữ liệu ảnh hưởng trực tiếp đến **thuật toán được thực hiện**.

### 10.1. BFS trên đồ thị không trọng số

**Duyệt theo chiều rộng** (*Breadth-First Search*, BFS) trên đồ thị không trọng số (hoặc các cạnh có chi phí bằng nhau) cần duyệt các đỉnh theo **số cạnh từ đỉnh xuất phát tăng dần**. Queue FIFO duy trì thứ tự phát hiện:

```python
from collections import deque


def bfs_distances(graph, start):
    distance = {start: 0}
    q = deque([start])

    while q:
        u = q.popleft()
        for v in graph[u]:
            if v not in distance:
                distance[v] = distance[u] + 1
                q.append(v)

    return distance


graph = {
    "S": ["A", "B"],
    "A": ["C"],
    "B": ["D"],
    "C": [],
    "D": []
}
assert bfs_distances(graph, "S") == {
    "S": 0, "A": 1, "B": 1, "C": 2, "D": 2
}
```

Dùng FIFO bảo đảm đỉnh cách `S` một cạnh được xử lý trước lớp đỉnh cách hai cạnh trong BFS tiêu chuẩn. Nếu thay bằng một priority queue có khóa tùy tiện, ta có thể **không còn** thứ tự BFS mong muốn.

### 10.2. Dijkstra trên đồ thị có trọng số không âm

Với bài toán đường đi ngắn nhất khi **trọng số cạnh không âm**, thuật toán Dijkstra thường dùng **min-priority queue**. Khóa ưu tiên là **khoảng cách tạm thời** đến đỉnh, không phải thứ tự đỉnh được phát hiện.

```text
S có các lối đi:
  S → A: chi phí 8
  S → B: chi phí 2
  B → A: chi phí 1

Phát hiện A trước, khoảng cách tạm thời 8.
Sau đó phát hiện B, khoảng cách tạm thời 2.

Min-priority queue chọn B(2) trước A(8),
rồi có thể cải thiện khoảng cách A thành 3.
```

Ví dụ Python sử dụng `heapq`, chấp nhận tạo mục mới khi khoảng cách giảm và **bỏ mục cũ** lúc lấy ra:

```python
import heapq


def dijkstra(graph, start):
    dist = {start: 0}
    heap = [(0, start)]

    while heap:
        current_dist, u = heapq.heappop(heap)

        # Mục cũ còn lại trong heap sau khi đã tìm ra đường tốt hơn.
        if current_dist != dist.get(u):
            continue

        for v, weight in graph.get(u, []):
            if weight < 0:
                raise ValueError("Dijkstra yêu cầu cạnh không âm")

            candidate = current_dist + weight
            if candidate < dist.get(v, float("inf")):
                dist[v] = candidate
                heapq.heappush(heap, (candidate, v))

    return dist


graph = {
    "S": [("A", 8), ("B", 2)],
    "A": [("C", 4)],
    "B": [("A", 1), ("C", 7)],
    "C": []
}
assert dijkstra(graph, "S") == {
    "S": 0, "A": 3, "B": 2, "C": 7
}
```

Ở ví dụ, `A` có thể xuất hiện **nhiều lần trong heap** với các khoảng cách 8 và 3. Khi lấy mục khoảng cách 8, kiểm tra `current_dist != dist[u]` cho phép bỏ nó vì đã cũ. Đây là một cách xử lý **giảm khóa bằng cách chèn mục mới** (*lazy decrease-key*), không phải khả năng tự cập nhật khóa của `heapq`.

**Lưu ý:** đoạn mã minh họa dùng các đỉnh là chuỗi so sánh được khi hai khoảng cách bằng nhau. Nếu đỉnh là đối tượng không so sánh được, nên bổ sung bộ đếm `sequence` như trong lớp `StableMinPriorityQueue` để tránh lỗi so sánh tuple.

**So sánh ý tưởng:**

| Thuật toán | Phần tử chọn tiếp theo | Cấu trúc phù hợp |
|---|---|---|
| BFS (mỗi cạnh chi phí 1) | Đỉnh **được phát hiện trước** trong hàng | **Queue FIFO** |
| Dijkstra (trọng số cạnh không âm) | Đỉnh có **khoảng cách tạm thời nhỏ nhất** | **Min-priority queue** |

Chọn cấu trúc sai có thể khiến **thuật toán không còn thỏa bất biến mong muốn**, chứ không chỉ làm chậm chương trình.

## 11. Một số câu hỏi thiết kế thực tế

### Nếu muốn priority queue có nhiều mức nhưng vẫn FIFO trong từng mức?

Có thể dùng **một queue FIFO cho mỗi mức ưu tiên**. Ví dụ ba mức `1, 2, 3`:

```text
Mức 1: B → C
Mức 2: D
Mức 3: A

Chọn mức ưu tiên tốt nhất có queue không rỗng,
sau đó dequeue theo FIFO trong mức đó.
```

Nếu số mức ưu tiên là **hằng số nhỏ**, tìm mức không rỗng có thể coi là O(1) theo kích thước hàng. Nếu số mức lớn hoặc thay đổi, cần cấu trúc bổ sung để tìm mức tốt nhất hiệu quả, chẳng hạn heap quản lý các mức đang có.

### Nếu cần sửa độ ưu tiên của một mục đang chờ?

Với heap thông thường, **không nên sửa trực tiếp khóa trong một mục** mà không điều chỉnh heap: bất biến cha–con có thể bị phá. Có những cách như:

- Cài phép `decrease_key` / `increase_key` kèm bảng ánh xạ mục đến chỉ số heap rồi phục hồi vị trí.
- Đánh dấu mục cũ không còn hợp lệ, **chèn mục mới** với độ ưu tiên cập nhật và bỏ mục cũ khi gặp nó trong quá trình lấy.
- Xây lại heap trong các tình huống dữ liệu thay đổi theo lô.

Mỗi phương án có đánh đổi về bộ nhớ, độ phức tạp và mã quản lý trạng thái; không nên mặc nhiên coi cập nhật priority là O(1).

### Nếu hàng đầy thì sao?

FIFO queue và priority queue đều có thể được **giới hạn sức chứa**. Khi đầy, hệ thống vẫn cần quy định chính sách từ chối, chờ hoặc bỏ một mục theo tiêu chí cụ thể. “Hàng đợi ưu tiên” **không có nghĩa tự động bỏ mục ưu tiên thấp nhất** khi đầy. Hành vi ấy chỉ xảy ra nếu API chủ động định nghĩa như vậy.

Nếu xử lý đa luồng, cũng cần chọn cấu trúc **đồng bộ** phù hợp. `heapq` là các phép toán heap trên `list`, không tự tạo một hàng đợi có khóa/điều kiện chờ hoàn chỉnh. Python có `queue.PriorityQueue` cho ngữ cảnh phối hợp giữa các luồng và hỗ trợ `put`/`get` với giới hạn tùy chọn.

## 12. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Xem queue thường và priority queue có cùng thứ tự lấy | Trả phần tử sai yêu cầu | FIFO lấy theo lúc đến; priority queue lấy theo khóa tốt nhất |
| Không xác định chiều ưu tiên | Nhầm mức 1 với mức 10 | Quy định min hay max ngay từ đầu |
| Cho rằng priority queue ổn định khi hòa | Các mục đồng ưu tiên có thể đổi thứ tự | Thêm `sequence` để hòa theo thời gian đến |
| Tưởng heap là mảng đã sắp xếp | Duyệt mảng heap không cho thứ tự ưu tiên | Dùng `heappop` hoặc thuật toán duyệt phù hợp |
| Dùng `list.pop(0)` cho queue thông thường | Xóa đầu có thể tốn O(n) | Dùng `deque.popleft` hoặc mảng vòng |
| Dùng `deque.pop()` để lấy cực tiểu | Lấy phần tử cuối, không phải ưu tiên tốt nhất | Dùng heap/cấu trúc tìm cực trị |
| Chỉ lưu `(priority, item)` với item không so sánh được | Gặp lỗi khi priority hòa trong tuple | Dùng `(priority, sequence, item)` |
| Bỏ qua thời điểm phần tử đến | Kết luận sai thứ tự nếu extract xảy ra xen giữa insert | Truy vết theo **thứ tự thao tác thực tế** |
| Thay priority của phần tử trong heap mà không tái lập bất biến | Heap trả sai phần tử ưu tiên | Cập nhật heap đúng thuật toán |
| Khẳng định mọi thao tác priority queue O(log n) | Peek gốc heap thực tế O(1) | Phân biệt insert, extract và peek |
| Dùng Dijkstra với cạnh âm | Không còn bảo đảm đúng của thuật toán | Dùng bài toán/phương pháp thích hợp cho trọng số âm |
| Tin priority queue tự chống starvation | Mục ít ưu tiên có thể chờ vô hạn | Thiết kế aging/hạn chót/định mức |
| Đánh đồng ưu tiên được lấy với hoàn thành sớm | Công việc song song có thể kết thúc khác thứ tự | Phân biệt thứ tự chọn và thứ tự hoàn tất |

## 13. Tự luyện với lời giải

**Bài 1 — Xác định thứ tự.** Thêm lần lượt `X(4)`, `Y(2)`, `Z(5)`, `T(2)` rồi mới lấy hết. Viết kết quả cho queue FIFO và min-priority queue có hòa theo FIFO.

*Lời giải:* FIFO: **`X, Y, Z, T`**. Min-priority: ưu tiên 2 trước, sau đó 4 rồi 5; giữa `Y` và `T` giữ thứ tự đến. Kết quả **`Y, T, X, Z`**.

**Bài 2 — Max-priority.** Với cùng dữ liệu ở bài 1, max-priority queue có hòa theo FIFO lấy theo thứ tự nào?

*Lời giải:* Khóa lớn được ưu tiên: `Z(5)`, `X(4)`, rồi `Y(2)` và `T(2)`. Kết quả **`Z, X, Y, T`**.

**Bài 3 — Thời điểm lấy.** Ban đầu queue rỗng; thực hiện `insert(A, 7)`, `extract_min()`, `insert(B, 1)`, `insert(C, 0)`, `extract_min()`. Hai kết quả extract là gì?

*Lời giải:* Lần đầu chỉ có `A` nên trả **`A`**. Lần hai có `B(1)`, `C(0)` nên trả **`C`**. Không thể lấy `C` ở lần đầu vì nó chưa đến.

**Bài 4 — Heap hay danh sách?** Cần hàng đợi ưu tiên với rất nhiều lần `insert` và `extract_min` xen kẽ. Vì sao binary heap thường hợp lý hơn danh sách mảng không sắp xếp?

*Lời giải:* Heap có insert và extract O(log n), còn mảng không sắp xếp thường phải quét O(n) để tìm cực tiểu khi lấy. Với rất nhiều lần lấy, phần quét đó có thể tốn kém.

**Bài 5 — Bất biến heap.** Mảng `[1, 3, 2, 7, 5, 4]` có thể là min-heap hợp lệ không? Nó có phải dãy sắp xếp tăng dần không?

*Lời giải:* **Có thể là min-heap hợp lệ**, vì mỗi nút cha `1, 3, 2` không lớn hơn các con tương ứng. Nhưng **không phải dãy tăng dần**, vì `3` đứng trước `2`.

**Bài 6 — Thứ tự bằng nhau.** Hai tác vụ `A` và `B` có cùng priority, `A` đến trước. Dùng `heapq` thuần với khóa chỉ gồm priority có đảm bảo trả `A` trước không?

*Lời giải:* **Không có bảo đảm ổn định theo thời điểm đến**. Hãy lưu khóa `(priority, sequence, item)` để định nghĩa quy tắc hòa rõ ràng.

**Bài 7 — BFS và Dijkstra.** Vì sao BFS trên đồ thị không trọng số thường dùng queue FIFO, trong khi Dijkstra trên đồ thị có trọng số không âm lại dùng min-priority queue?

*Lời giải:* BFS cần xử lý đỉnh theo lớp khoảng cách số cạnh/ thứ tự phát hiện, phù hợp FIFO. Dijkstra cần chọn đỉnh có **khoảng cách tạm thời nhỏ nhất**, phù hợp min-priority queue.

**Bài 8 — Công bằng.** Một mục ưu tiên thấp đã chờ lâu, nhưng liên tục xuất hiện mục mới có mức ưu tiên cao hơn. Priority queue thông thường tự bảo đảm mục cũ cuối cùng được lấy không?

*Lời giải:* **Không.** Nó có thể tiếp tục bị trì hoãn. Nếu yêu cầu giới hạn thời gian chờ, cần thêm chính sách aging, phân lượt hoặc hạn chót.

**Bài 9 — Độ phức tạp.** Một min-heap đang có `n` phần tử. Nêu thời gian của `insert`, `peek_min` và `extract_min`.

*Lời giải:* `insert` O(log n), `peek_min` O(1), `extract_min` O(log n), với các thao tác cơ bản và khóa so sánh chi phí hằng số. Khi n nhỏ hay bằng 0 cần xử lý rỗng theo hợp đồng.

**Ghi nhớ:** **Queue thường** duy trì FIFO bất kể giá trị phần tử. **Priority queue** chọn phần tử có **khóa ưu tiên tốt nhất trong tập đang chờ**, còn thứ tự giữa các mục cùng khóa cần chính sách riêng. Một queue cài bằng mảng vòng hoặc deque cho enqueue/dequeue O(1), trong khi priority queue cài bằng binary heap thường có insert/extract O(log n), peek O(1). Lựa chọn đúng giúp bảo toàn bất biến của bài toán: **BFS cần thứ tự lớp theo FIFO, còn Dijkstra cần cực tiểu của khoảng cách tạm thời**.
