# Kiểu dữ liệu trừu tượng FIFO và các phép thêm–lấy

Trong nhóm cấu trúc dữ liệu tuyến tính, **hàng đợi (queue)** mô tả cách quản lý các phần tử theo quy tắc **FIFO** (*First In, First Out*): phần tử được thêm vào trước sẽ được lấy ra trước. Đây là mô hình nền tảng của hàng chờ xử lý yêu cầu, bộ đệm dữ liệu, duyệt đồ thị theo chiều rộng và nhiều hệ thống điều phối công việc.

Bài học thuộc chương **Hàng đợi và deque** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mục tiêu là hiểu hàng đợi dưới góc nhìn **kiểu dữ liệu trừu tượng (ADT)**, nắm rõ hợp đồng của các phép thêm–lấy, các bất biến FIFO và sự đánh đổi về thời gian, bộ nhớ giữa những cách cài đặt.

## 1. Hàng đợi là một kiểu dữ liệu trừu tượng

**Kiểu dữ liệu trừu tượng** xác định *dữ liệu được phép thao tác như thế nào* và *mỗi thao tác phải cho kết quả gì*, nhưng không buộc người sử dụng biết dữ liệu nằm trong mảng, danh sách liên kết hay một cấu trúc bên trong khác.

Ví dụ, một hàng chờ tiếp nhận hồ sơ có thể được hiểu bằng hai quy tắc:

1. Hồ sơ mới được đưa vào **cuối hàng**.
2. Khi có nhân viên rảnh, hồ sơ ở **đầu hàng** được lấy ra xử lý.

Với hàng đợi FIFO, ta gọi:

- **Front (đầu hàng):** vị trí của phần tử sẽ được lấy ra tiếp theo.
- **Rear/Back (cuối hàng):** phía nhận các phần tử mới.
- **Enqueue:** thêm phần tử vào cuối hàng.
- **Dequeue:** lấy ra **và loại bỏ** phần tử ở đầu hàng.

```text
                  Hàng đợi theo thứ tự logic

        dequeue ← [ A ] [ B ] [ C ] ← enqueue(D)
                   ↑             ↑
                 front          rear

        Sau enqueue(D):  [ A ] [ B ] [ C ] [ D ]
        Sau dequeue():   [ B ] [ C ] [ D ]       trả về A
```

Trong sơ đồ, ký hiệu A, B, C là **giá trị phần tử**; các ô không nhất thiết nằm liên tiếp trong bộ nhớ vật lý. Điều quan trọng là **thứ tự logic** được bảo toàn.

### Mô hình hóa chính xác bằng dãy

Xem trạng thái hàng đợi là dãy hữu hạn `Q = [q₀, q₁, …, qₙ₋₁]`, đọc từ đầu đến cuối hàng:

- `enqueue(x)`: biến `Q` thành `[q₀, q₁, …, qₙ₋₁, x]`.
- `dequeue()`, nếu `n > 0`: trả về `q₀`, đồng thời biến `Q` thành `[q₁, …, qₙ₋₁]`.
- `peek()`, nếu `n > 0`: trả về `q₀`, **giữ nguyên** `Q`.

Từ hợp đồng này suy ra: nếu lần lượt `enqueue(A)`, `enqueue(B)`, `enqueue(C)` và không có thao tác khác làm thay đổi thứ tự, ba lần `dequeue()` thành công tiếp theo sẽ trả về `A`, `B`, `C`.

FIFO không có nghĩa phần tử phải được xử lý **xong** trước phần tử sau: hàng đợi chỉ quy định **thứ tự lấy phần tử ra**. Trong hệ thống xử lý song song, các công việc có thể hoàn thành khác thứ tự bắt đầu.

## 2. Hợp đồng các phép toán cơ bản

| Phép toán | Ý nghĩa | Ảnh hưởng đến hàng đợi | Trường hợp cần chú ý |
|---|---|---|---|
| `enqueue(x)` | Thêm `x` vào cuối | Tăng số phần tử lên 1 | Hàng đợi có sức chứa cố định có thể đã đầy |
| `dequeue()` | Lấy và xóa phần tử đầu | Giảm số phần tử đi 1 | Không thể lấy khi hàng đợi rỗng |
| `peek()` / `front()` | Xem phần tử đầu | Không đổi | Không có phần tử đầu khi rỗng |
| `is_empty()` | Kiểm tra hàng đợi rỗng | Không đổi | Đúng khi kích thước bằng 0 |
| `size()` / `len()` | Đếm số phần tử hiện có | Không đổi | Có thể bằng 0 |
| `is_full()` | Kiểm tra hết chỗ chứa | Không đổi | Chỉ có ý nghĩa khi giới hạn sức chứa |

Tên hàm và cách báo lỗi là lựa chọn của API cụ thể. Chẳng hạn, `dequeue()` trên hàng đợi rỗng có thể **ném ngoại lệ**, trả về một mã lỗi hoặc dùng kết quả tùy chọn (*optional*). Khi thiết kế, cần công bố rõ quy tắc; không nên tự ý trả `None` để biểu thị rỗng nếu `None` cũng là một giá trị hợp lệ được đưa vào hàng đợi.

### Truy vết một chuỗi thao tác

Quy ước viết trạng thái từ **front → rear**:

| Bước | Thao tác | Giá trị trả về | Trạng thái sau thao tác |
|---:|---|---|---|
| 0 | Khởi tạo | — | `[]` |
| 1 | `enqueue("An")` | — | `[An]` |
| 2 | `enqueue("Bình")` | — | `[An, Bình]` |
| 3 | `enqueue("Chi")` | — | `[An, Bình, Chi]` |
| 4 | `peek()` | `An` | `[An, Bình, Chi]` |
| 5 | `dequeue()` | `An` | `[Bình, Chi]` |
| 6 | `enqueue("Dũng")` | — | `[Bình, Chi, Dũng]` |
| 7 | `dequeue()` | `Bình` | `[Chi, Dũng]` |

Ở bước 4, `peek()` không loại bỏ `An`, vì vậy bước 5 vẫn lấy ra `An`. Hai phần tử có giá trị bằng nhau vẫn được xem là **hai lần thêm riêng biệt** và phải được lấy ra theo thứ tự thêm.

## 3. Bất biến FIFO và các tình huống biên

Một cách phát biểu bất biến quan trọng: **trong số các phần tử chưa bị lấy ra, phần tử được enqueue sớm nhất luôn nằm ở front**.

Ta có thể kiểm tra tính đúng đắn của một cài đặt qua lập luận quy nạp:

1. **Ban đầu:** hàng đợi rỗng nên bất biến đúng.
2. **Khi enqueue:** phần tử mới chỉ được nối vào rear, vì thế không thể vượt lên trước phần tử đang chờ.
3. **Khi dequeue:** phần tử front được lấy ra; phần tử chờ lâu nhất còn lại trở thành front mới.

Như vậy, sau mọi chuỗi thao tác hợp lệ, thứ tự FIFO vẫn được giữ.

Các tình huống biên cần được đặc biệt quan tâm:

- **Hàng đợi rỗng:** không có front hợp lệ; `dequeue` và `peek` phải tuân thủ cơ chế báo lỗi đã chọn.
- **Chỉ có một phần tử:** `dequeue` khiến hàng đợi trở thành rỗng; cài đặt danh sách liên kết cần cập nhật **cả head và tail**.
- **Hàng đợi đầy:** chỉ xảy ra với biến thể có sức chứa giới hạn; `enqueue` phải báo đầy hoặc chờ chỗ trống theo hợp đồng API.
- **Thao tác lặp lại:** enqueue rồi dequeue nhiều lần không được làm mất chỗ chứa một cách vô lý; đây là lý do mảng vòng thường phù hợp hơn mảng chỉ tăng chỉ số cuối.
- **Giá trị đặc biệt, trùng nhau:** có thể enqueue các giá trị giống nhau hoặc `None` nếu kiểu dữ liệu cho phép; trạng thái rỗng phải được xác định riêng.

## 4. Cài đặt bằng mảng vòng (circular array)

Một mảng thường có độ dài cố định `capacity`. Nếu liên tục tăng chỉ số vị trí thêm, các ô ở đầu mảng đã được giải phóng sẽ bị bỏ phí. **Mảng vòng** giải quyết vấn đề bằng cách quay về đầu mảng sau khi đi qua ô cuối.

Ta lưu ba thông tin:

- `data`: mảng vật lý gồm `capacity` ô.
- `head`: chỉ số ô vật lý ứng với front, nếu hàng đợi không rỗng.
- `count`: số phần tử hợp lệ, với `0 ≤ count ≤ capacity`.

Vị trí đặt phần tử mới là `(head + count) % capacity`. Khi lấy đầu hàng, sau khi xóa phần tử, vị trí head mới là `(head + 1) % capacity`. Phép chia lấy dư (`%`) giúp chỉ số quay vòng.

### Ví dụ khi chỉ số quay vòng

Với sức chứa 3, ban đầu enqueue `A`, `B`, `C`:

```text
Chỉ số mảng:       0     1     2
Mảng vật lý:      [A]   [B]   [C]
head = 0, count = 3
Thứ tự logic:     A → B → C
```

Sau `dequeue()` lấy `A`, `head = 1` và `count = 2`. Tiếp theo, `enqueue(D)` đặt `D` vào ô số `(1 + 2) % 3 = 0`:

```text
Chỉ số mảng:       0     1     2
Mảng vật lý:      [D]   [B]   [C]
head = 1, count = 3
Thứ tự logic:     B → C → D
```

**Mảng vật lý `[D, B, C]` không có nghĩa D được lấy trước**; phần tử đầu hàng là ô `head = 1`. Đây là điểm cần phân biệt giữa **vị trí lưu trữ** và **thứ tự FIFO**.

### Cài đặt Python minh họa

```python
class CircularQueue:
    def __init__(self, capacity):
        if capacity <= 0:
            raise ValueError("capacity phải lớn hơn 0")
        self._data = [None] * capacity
        self._head = 0
        self._count = 0

    def __len__(self):
        return self._count

    def is_empty(self):
        return self._count == 0

    def is_full(self):
        return self._count == len(self._data)

    def enqueue(self, value):
        if self.is_full():
            raise OverflowError("Hàng đợi đã đầy")
        tail = (self._head + self._count) % len(self._data)
        self._data[tail] = value
        self._count += 1

    def peek(self):
        if self.is_empty():
            raise IndexError("Hàng đợi rỗng")
        return self._data[self._head]

    def dequeue(self):
        if self.is_empty():
            raise IndexError("Hàng đợi rỗng")
        value = self._data[self._head]
        self._data[self._head] = None  # Bỏ tham chiếu tới phần tử cũ
        self._head = (self._head + 1) % len(self._data)
        self._count -= 1
        return value


q = CircularQueue(3)
q.enqueue("A")
q.enqueue("B")
q.enqueue("C")
assert q.dequeue() == "A"
q.enqueue("D")
assert q.peek() == "B"
assert [q.dequeue(), q.dequeue(), q.dequeue()] == ["B", "C", "D"]
assert q.is_empty()
```

Cài đặt trên dành cho **hàng đợi giới hạn sức chứa**; nếu đầy thì báo `OverflowError`, không tự mở rộng. Việc theo dõi `_count` giúp phân biệt *rỗng* và *đầy* ngay cả khi chỉ số đầu và vị trí thêm mới trùng nhau sau một vòng quay. Phần tử `None` vẫn có thể được enqueue vì trạng thái rỗng không phụ thuộc vào giá trị của ô.

Các bước tính chỉ số, ghi/đọc ô và cập nhật biến đều cần thời gian hằng số. Vì vậy, `enqueue`, `dequeue` và `peek` đều chạy trong **O(1)** ở trường hợp xấu nhất, với bộ nhớ **O(C)** cho sức chứa `C`.

## 5. Các cách cài đặt khác và độ phức tạp

Không phải mọi cấu trúc lưu trữ đều cho cùng chi phí khi thực hiện hợp đồng queue ADT.

| Cách cài đặt | `enqueue` | `dequeue` | Bộ nhớ | Ghi chú |
|---|---:|---:|---:|---|
| Mảng vòng, sức chứa cố định | O(1) | O(1) | O(C) | Không cấp phát thêm khi hoạt động; cần xử lý khi đầy |
| Mảng vòng, tự mở rộng | O(1) khấu hao | O(1) | O(C) | Một lần tăng dung lượng có thể tốn O(n) để sao chép |
| Danh sách liên kết đơn với `head`, `tail` | O(1) | O(1) | O(n) | Cần thêm bộ nhớ liên kết cho từng nút |
| Python `list.append` + `list.pop(0)` | O(1) khấu hao | O(n) | O(n) | `pop(0)` phải dời các phần tử còn lại |
| Python `collections.deque` (thêm/lấy ở hai đầu) | O(1) | O(1) | O(n) | Thích hợp để hiện thực hàng đợi FIFO |

Trong bảng, `n` là số phần tử đang lưu và `C` là sức chứa đã cấp phát. **O(1) khấu hao** (*amortized*) là chi phí trung bình trên một chuỗi thao tác, không có nghĩa mọi lần gọi riêng lẻ đều chạy trong thời gian hằng số.

Với **danh sách liên kết đơn**, ta nối nút mới vào `tail` khi enqueue và bỏ nút `head` khi dequeue. Cần giữ đồng thời con trỏ đầu và cuối để tránh duyệt toàn bộ danh sách; khi lấy hết phần tử cuối, đặt `head = tail = null`. Cách này không đòi hỏi vùng nhớ liên tục, nhưng mỗi nút thường tốn thêm bộ nhớ lưu con trỏ.

### Sử dụng queue FIFO có sẵn trong Python

Python cung cấp `collections.deque` (*double-ended queue*), hỗ trợ thao tác hiệu quả tại cả hai đầu. Chỉ cần **thêm bằng `append` và lấy bằng `popleft`**, nó thực hiện đúng hành vi của queue FIFO:

```python
from collections import deque

requests = deque()
requests.append("Yêu cầu 101")     # enqueue
requests.append("Yêu cầu 102")

first = requests[0]                # peek, không xóa
served = requests.popleft()       # dequeue

assert first == served == "Yêu cầu 101"
assert list(requests) == ["Yêu cầu 102"]
```

Chú ý: `deque.pop()` **lấy ở cuối**, còn `deque.appendleft(x)` **thêm ở đầu**. Nếu tự ý dùng các phép đó trong hàng chờ FIFO, thứ tự phục vụ sẽ thay đổi.

Khi cần hàng đợi phối hợp giữa các **luồng (threads)** trong Python, có thể chọn `queue.Queue` với các thao tác `put` và `get`, hỗ trợ đồng bộ và chờ khi cần. Ví dụ `collections.deque` trên tập trung minh họa thứ tự FIFO; nó không thay thế đầy đủ cơ chế phối hợp luồng và quy tắc báo lỗi của `queue.Queue`.

## 6. Ứng dụng: vì sao FIFO hữu ích?

**Duyệt đồ thị theo chiều rộng (BFS)** là ví dụ tiêu biểu. Khi thăm một đỉnh, ta đưa các đỉnh kề chưa được phát hiện vào cuối hàng đợi; đỉnh được phát hiện sớm hơn sẽ được xét trước. Với đồ thị không trọng số, cơ chế này cho phép khám phá các đỉnh theo số cạnh tăng dần tính từ đỉnh bắt đầu.

```python
from collections import deque

def bfs(graph, start):
    discovered = {start}
    q = deque([start])
    visit_order = []

    while q:
        vertex = q.popleft()
        visit_order.append(vertex)

        for neighbor in graph.get(vertex, []):
            if neighbor not in discovered:
                discovered.add(neighbor)  # Đánh dấu ngay khi enqueue
                q.append(neighbor)

    return visit_order


graph = {
    "A": ["B", "C"],
    "B": ["D"],
    "C": ["E"],
    "D": [],
    "E": [],
}
assert bfs(graph, "A") == ["A", "B", "C", "D", "E"]
```

Việc đánh dấu khi enqueue ngăn cùng một đỉnh bị đưa vào hàng đợi nhiều lần. Với biểu diễn **danh sách kề**, BFS duyệt tối đa mỗi đỉnh và mỗi cạnh một số lần hằng số: thời gian **O(V + E)** và bộ nhớ phụ **O(V)** (bao gồm tập đỉnh đã phát hiện, thứ tự kết quả và hàng đợi). `V` và `E` lần lượt là số đỉnh và số cạnh.

Những ứng dụng khác gồm bộ đệm thông điệp được nhận theo thứ tự, hàng chờ yêu cầu ở quầy dịch vụ và tác vụ chờ được phân phối cho nhân viên xử lý. FIFO giúp giữ thứ tự **nhận và lấy việc** có thể dự đoán được, nhưng không tự bảo đảm thời gian chờ nhỏ, ưu tiên công việc khẩn cấp hay thứ tự hoàn tất khi có nhiều bộ xử lý.

## 7. Phân biệt queue, stack, deque và priority queue

| Cấu trúc | Quy tắc lấy phần tử | Khi nào phù hợp |
|---|---|---|
| **Queue** | FIFO: phần tử vào trước ra trước | Hàng chờ tiếp nhận, BFS, xử lý theo thứ tự đến |
| **Stack** | LIFO: phần tử vào sau ra trước | Ngăn xếp lời gọi, hoàn tác, duyệt DFS kiểu stack |
| **Deque** | Có thể thêm/lấy ở **cả đầu và cuối** | Cần thao tác hai đầu, cửa sổ trượt, hiện thực cả queue lẫn stack |
| **Priority queue** | Lấy theo **độ ưu tiên** đã định | Lập lịch ưu tiên, thuật toán Dijkstra |

**Queue là một ADT có quy tắc FIFO**. **Deque** là ADT tổng quát hơn về các đầu có thể thao tác: dùng một tập con phép toán của deque sẽ tạo ra hành vi queue, nhưng dùng tất cả thao tác của deque không còn ràng buộc FIFO như queue thuần túy.

Khi chọn cấu trúc cho bài toán, hãy xác định thứ tự được yêu cầu trước: nếu cần giữ thứ tự đến, chọn queue; nếu cần lấy phần tử mới nhất, chọn stack; nếu cần ưu tiên công việc có độ khẩn cấp cao, chọn priority queue.

## 8. Tự kiểm tra hiểu biết

**Tình huống 1.** Hàng đợi ban đầu rỗng. Thực hiện `enqueue(7)`, `enqueue(9)`, `dequeue()`, `enqueue(5)`, `peek()`. Giá trị hai lần lấy/xem là gì?

*Giải thích:* `dequeue()` trả `7`; sau đó hàng đợi là `[9, 5]`, nên `peek()` trả `9`.

**Tình huống 2.** Mảng vòng sức chứa 4 có `head = 3`, `count = 2`. Vị trí vật lý để enqueue phần tử tiếp theo là ô nào?

*Giải thích:* `(3 + 2) % 4 = 1`. Chỉ số vật lý không phản ánh trực tiếp thứ tự FIFO.

**Tình huống 3.** Vì sao thay `deque.popleft()` bằng `list.pop(0)` có thể khiến hệ thống chậm khi hàng đợi dài?

*Giải thích:* `list.pop(0)` phải dịch chuyển nhiều phần tử còn lại, mất O(n) cho một lần lấy; lấy ở đầu `collections.deque` mất O(1).

Điểm cần nhớ là **hợp đồng thao tác quyết định tính đúng đắn; cách lưu trữ quyết định chi phí**. Một cài đặt hàng đợi tốt vừa giữ bất biến FIFO, vừa đảm bảo phép thêm ở cuối và lấy ở đầu đáp ứng yêu cầu hiệu năng và sức chứa của bài toán.
