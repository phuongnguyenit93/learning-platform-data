# Hàng đợi bằng danh sách đơn có đầu và cuối

Trong chương **Hàng đợi và deque**, một lựa chọn cài đặt hàng đợi FIFO là **danh sách liên kết đơn có hai con trỏ `head` và `tail`**. Cách này cho phép thêm phần tử vào cuối và lấy phần tử khỏi đầu trong thời gian **O(1)**, kể cả khi số lượng phần tử thay đổi liên tục.

Bài học thuộc mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, nơi người học xây dựng nền tảng về mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị; đồng thời phân tích bất biến, thao tác và độ phức tạp thời gian, bộ nhớ để chọn cấu trúc dữ liệu phù hợp. Trọng tâm ở đây là **cài đặt queue bằng danh sách liên kết đơn**, đặc biệt là vai trò của hai đầu, các trường hợp biên và cách chứng minh tính đúng đắn.

## 1. Yêu cầu của hàng đợi FIFO

Hàng đợi (*queue*) là kiểu dữ liệu trừu tượng tuân thủ **First In, First Out**: phần tử được đưa vào trước sẽ được lấy ra trước, nếu chưa bị xóa bởi thao tác nào khác. Các phép toán tối thiểu cần cài đặt gồm:

| Phép toán | Ý nghĩa | Trạng thái sau phép toán |
|---|---|---|
| `enqueue(x)` | Thêm phần tử `x` vào **cuối** hàng | Hàng dài thêm một phần tử |
| `dequeue()` | Trả về và xóa phần tử ở **đầu** hàng | Hàng ngắn đi một phần tử |
| `peek()` / `front()` | Xem phần tử đầu nhưng không xóa | Không đổi |
| `is_empty()` | Cho biết hàng đợi có rỗng không | Không đổi |
| `size()` | Cho biết số phần tử hiện tại | Không đổi |

Với hàng đợi logic `[A, B, C]`, phép `enqueue(D)` tạo thành `[A, B, C, D]`; phép `dequeue()` tiếp theo trả về `A` và để lại `[B, C, D]`.

Một cách cài đặt chưa tốt có thể giữ đúng thứ tự FIFO nhưng phải **duyệt O(n)** phần tử mỗi lần thêm hoặc lấy. Mục tiêu của thiết kế hai con trỏ là giữ cả hai phép quan trọng ở **O(1)**.

## 2. Biểu diễn bằng danh sách liên kết đơn

Mỗi **nút** (*node*) chứa hai thành phần:

- `value`: dữ liệu do người dùng đưa vào.
- `next`: tham chiếu đến nút ngay sau, hoặc `None` nếu nút là nút cuối.

Bản thân hàng đợi lưu ba trường:

- **`head`:** tham chiếu đến nút đầu, tức phần tử sẽ được lấy ra tiếp theo.
- **`tail`:** tham chiếu đến nút cuối, nơi nối thêm phần tử mới.
- **`size`:** số nút hiện có; giúp truy vấn kích thước trong O(1).

Ví dụ, hàng đợi có ba phần tử:

```text
         head                                  tail
          |                                     |
          v                                     v
       +-------+       +-------+       +-------+
       | A | o-------> | B | o-------> | C | / |
       +-------+       +-------+       +-------+
            front                              rear

       size = 3             tail.next = None
```

Mỗi mũi tên là một tham chiếu `next`. Các nút có thể nằm rải rác trong bộ nhớ, nhưng thứ tự logic được xác định bằng đường đi từ `head` theo `next`. Dấu `/` ở nút cuối biểu thị tham chiếu rỗng.

**Tại sao cần cả hai con trỏ?**

- Chỉ có `head`: lấy đầu nhanh, nhưng để thêm vào cuối thường phải đi từ đầu đến cuối, tốn O(n).
- Chỉ có `tail` trong một danh sách đơn thông thường: không có tham chiếu trực tiếp đến đầu để lấy đầu trong O(1).
- Có **`head` và `tail`**: truy cập được cả hai vị trí cần thiết, không cần duyệt danh sách cho `enqueue` hay `dequeue`.

Ở đây sử dụng **danh sách đơn không có nút giả (*sentinel*)**. Có thể dùng nút giả trong một thiết kế khác, nhưng khi đó bất biến về `head` và `tail` cần được định nghĩa lại cho nhất quán.

## 3. Bất biến phải luôn đúng

**Bất biến cấu trúc** là các điều kiện phải được giữ trước và sau mỗi phép toán hoàn chỉnh:

1. `size == 0` khi và chỉ khi **cả `head` và `tail` đều là `None`**.
2. Nếu `size > 0`, cả `head` và `tail` đều trỏ tới các nút hợp lệ.
3. Bắt đầu từ `head`, đi theo `next` sẽ gặp đúng `size` nút rồi kết thúc; nút cuối chính là `tail`.
4. Khi không rỗng, **`tail.next is None`**; không có vòng liên kết.
5. Khi `size == 1`, **`head is tail`**: hai con trỏ trỏ tới **cùng một nút**.
6. Thứ tự các nút từ `head` đến `tail` là thứ tự enqueue của các phần tử chưa được dequeue.

Bất biến 1 và 5 đặc biệt quan trọng: nhiều lỗi xuất hiện khi lấy phần tử cuối nhưng chỉ đưa `head` về `None` và để `tail` trỏ vào một nút đã ra khỏi hàng.

## 4. Thêm phần tử ở cuối: `enqueue(x)`

Tạo nút mới với `value = x` và `next = None`. Sau đó xử lý hai trường hợp.

### Hàng đợi rỗng

Chưa có nút nào, nên nút mới vừa là đầu vừa là cuối:

```text
Trước:  head = None; tail = None; size = 0
                     enqueue(A)
Sau:    head ─┐
              v
              [ A | None ]
              ^
        tail ─┘            size = 1
```

Phải cập nhật **cả `head` và `tail`**. Nếu chỉ đặt `tail`, ta không thể dequeue phần tử vừa thêm vì `head` vẫn rỗng.

### Hàng đợi đã có phần tử

Nối nút mới vào sau nút cuối hiện tại, rồi chuyển `tail` sang nút mới:

```text
Trước:  head ──> [ A | • ] ──> [ B | None ] <── tail

                                 enqueue(C)

Sau:    head ──> [ A | • ] ──> [ B | • ] ──> [ C | None ]
                                                      ^
                                                     tail
```

Thứ tự các thao tác ở nhánh không rỗng:

1. `old_tail.next = new_node` để móc nút mới vào danh sách.
2. `tail = new_node` để ghi nhận nút cuối mới.
3. Tăng `size` lên 1.

**Giả mã:**

```text
ENQUEUE(x):
    new_node = Node(value=x, next=None)

    if tail == None:
        head = new_node
        tail = new_node
    else:
        tail.next = new_node
        tail = new_node

    size = size + 1
```

Không cần duyệt các nút đang có; dù hàng đợi chứa 2 hay 2 triệu phần tử, thao tác liên kết vẫn chỉ dùng một số phép gán cố định.

## 5. Lấy phần tử ở đầu: `dequeue()`

`dequeue()` cần **trả giá trị của nút đầu**, loại bỏ nút đó khỏi hàng và duy trì các bất biến.

- **Hàng rỗng:** không có giá trị để trả; cài đặt phải báo lỗi theo hợp đồng đã chọn.
- **Có từ hai nút:** lưu giá trị của `head`, chuyển `head` sang `head.next` và giảm `size`.
- **Chỉ có một nút:** sau khi chuyển `head`, kết quả là `None`; phải đặt **`tail = None`** để hàng thực sự trở lại trạng thái rỗng.

```text
Trước:
head ──> [ A | • ] ──> [ B | • ] ──> [ C | None ] <── tail
             |
           trả A

Sau dequeue():
head ──> [ B | • ] ──> [ C | None ] <── tail

Nếu trước đó chỉ có A:
head ──> [ A | None ] <── tail

Sau dequeue():
head = None
tail = None
size = 0
```

**Giả mã:**

```text
DEQUEUE():
    if head == None:
        raise EmptyQueueError

    old_head = head
    result = old_head.value
    head = old_head.next

    if head == None:
        tail = None

    size = size - 1
    return result
```

Giữ lại `result` trước khi loại nút đầu để bảo đảm giá trị được trả về đúng. Không cần tìm nút đứng trước `head`: ta chỉ chuyển thẳng sang `head.next`.

### Điều gì xảy ra nếu quên cập nhật `tail`?

Giả sử chỉ có `A`. Sau `dequeue()`, `head = None` nhưng `tail` vẫn trỏ tới nút `A` đã bị lấy ra. Nếu tiếp tục `enqueue(B)` bằng nhánh "hàng không rỗng", chương trình có thể nối `B` vào nút `A` cũ, trong khi `head` vẫn `None`: phần tử mới trở nên **không thể lấy từ đầu hàng**.

Vì vậy, luôn phải xử lý lúc **hàng chuyển từ một phần tử về rỗng**; đây là một kiểm tra cơ bản khi viết queue bằng danh sách liên kết.

## 6. Cài đặt Python hoàn chỉnh

Ví dụ sau dùng nút riêng và duy trì `_head`, `_tail`, `_size`. Hàng đợi không có giới hạn dung lượng cố định; nếu không cấp phát thêm bộ nhớ được, việc tạo nút có thể thất bại tùy môi trường.

```python
class _Node:
    def __init__(self, value):
        self.value = value
        self.next = None


class LinkedQueue:
    def __init__(self):
        self._head = None
        self._tail = None
        self._size = 0

    def __len__(self):
        return self._size

    def is_empty(self):
        return self._head is None

    def enqueue(self, value):
        new_node = _Node(value)

        if self._tail is None:
            # Hàng đang rỗng: nút mới là cả đầu và cuối.
            self._head = new_node
            self._tail = new_node
        else:
            # Hàng đã có nút: nối vào cuối.
            self._tail.next = new_node
            self._tail = new_node

        self._size += 1

    def peek(self):
        if self._head is None:
            raise IndexError("Không thể xem đầu hàng đợi rỗng")
        return self._head.value

    def dequeue(self):
        if self._head is None:
            raise IndexError("Không thể lấy từ hàng đợi rỗng")

        old_head = self._head
        result = old_head.value
        self._head = old_head.next

        if self._head is None:
            # Vừa lấy nút duy nhất: xóa con trỏ cuối.
            self._tail = None

        self._size -= 1
        old_head.next = None  # Ngắt liên kết từ nút đã loại.
        return result


q = LinkedQueue()
assert q.is_empty()

q.enqueue("A")
q.enqueue("B")
q.enqueue("C")

assert len(q) == 3
assert q.peek() == "A"
assert len(q) == 3             # peek không xóa phần tử.
assert q.dequeue() == "A"

q.enqueue("D")
assert [q.dequeue(), q.dequeue(), q.dequeue()] == ["B", "C", "D"]
assert q.is_empty()
assert len(q) == 0

q.enqueue("E")                # Kiểm tra tái sử dụng sau khi rỗng.
assert q.peek() == "E"
assert q.dequeue() == "E"
assert q.is_empty()
```

Một số quyết định thiết kế trong ví dụ:

- **`IndexError` khi rỗng:** giúp phân biệt lỗi lấy/xem phần tử với việc một phần tử hợp lệ có giá trị `None`. Một API khác có thể chọn ngoại lệ tùy chỉnh hoặc kiểu kết quả tùy chọn, miễn là nhất quán.
- **`_size` cập nhật ở cả hai chiều:** bảo đảm `len(q)` là O(1), tránh đếm nút mỗi lần truy vấn.
- **`old_head.next = None`:** ngắt liên kết từ nút đã lấy ra, giúp tránh việc giữ tham chiếu tới phần còn lại nếu một nơi khác còn nắm giữ nút cũ. Tính đúng đắn FIFO vẫn dựa vào cập nhật `_head` và `_tail`.
- **Không dùng giá trị `None` để nhận biết nút rỗng:** việc kiểm tra dựa trên **con trỏ nút**. Vì vậy, có thể gọi `q.enqueue(None)` và lấy ra giá trị `None` hợp lệ.
- **Không tự đồng bộ giữa các luồng:** mã minh họa một hàng đợi dùng tuần tự. Khi nhiều luồng truy cập đồng thời, cần cơ chế đồng bộ thích hợp, chẳng hạn `queue.Queue` trong Python.

## 7. Truy vết hoạt động và kiểm tra bất biến

Trạng thái bên dưới biểu diễn thứ tự logic từ `head` tới `tail`:

| Bước | Thao tác | Giá trị trả về | Danh sách liên kết sau thao tác | `head` | `tail` | `size` |
|---:|---|---|---|---|---|---:|
| 0 | Khởi tạo | — | `∅` | `None` | `None` | 0 |
| 1 | `enqueue(A)` | — | `A` | `A` | `A` | 1 |
| 2 | `enqueue(B)` | — | `A → B` | `A` | `B` | 2 |
| 3 | `enqueue(C)` | — | `A → B → C` | `A` | `C` | 3 |
| 4 | `dequeue()` | `A` | `B → C` | `B` | `C` | 2 |
| 5 | `enqueue(D)` | — | `B → C → D` | `B` | `D` | 3 |
| 6 | `dequeue()` | `B` | `C → D` | `C` | `D` | 2 |
| 7 | `dequeue()` | `C` | `D` | `D` | `D` | 1 |
| 8 | `dequeue()` | `D` | `∅` | `None` | `None` | 0 |
| 9 | `enqueue(E)` | — | `E` | `E` | `E` | 1 |

Kiểm tra bước 7: chỉ còn một nút, nên `head is tail`. Bước 8 lấy nút cuối và đưa cả hai con trỏ về `None`. Bước 9 kiểm tra hàng hoạt động chính xác sau khi đã rỗng một lần.

### Lập luận chứng minh FIFO

Xét dãy các nút từ `head` tới `tail` là thứ tự phần tử còn trong hàng:

1. **Cơ sở:** danh sách rỗng biểu diễn đúng hàng đợi rỗng.
2. **Enqueue:** nút mới chỉ được nối **sau `tail`**, nên thứ tự các nút cũ giữ nguyên và phần tử mới nằm cuối.
3. **Dequeue:** chỉ loại **nút `head`**, nên phần tử vào sớm nhất trong số các phần tử còn lại trở thành đầu mới.
4. **Peek:** chỉ đọc dữ liệu tại `head`, không làm thay đổi danh sách.

Theo quy nạp, mỗi chuỗi thao tác hợp lệ duy trì đúng thứ tự FIFO.

## 8. Phân tích thời gian và bộ nhớ

Với `n` là số nút đang ở trong hàng:

| Thao tác | Độ phức tạp thời gian | Lý do |
|---|---|---|
| `enqueue(x)` | **O(1)** | Tạo nút và sửa số lượng cố định tham chiếu; không duyệt danh sách |
| `dequeue()` | **O(1)** | Đọc nút đầu, chuyển `head` và có thể đặt lại `tail` |
| `peek()` | **O(1)** | Đọc giá trị tại `head` |
| `is_empty()` | **O(1)** | Kiểm tra `head is None` |
| `len(q)` | **O(1)** | Đọc bộ đếm `_size` |
| Duyệt toàn bộ nội dung | **O(n)** | Phải lần theo `next` qua mọi nút |

Các đánh giá O(1) cho phép thêm/lấy tính theo số thao tác thuật toán, giả định cấp phát một nút và cập nhật tham chiếu có chi phí hằng số; ở thực tế, trình cấp phát bộ nhớ và cơ chế thu gom rác có thể thêm chi phí hệ thống.

**Bộ nhớ để lưu `n` phần tử là O(n)**: mỗi nút chứa một giá trị và một tham chiếu `next`. Bản thân đối tượng `LinkedQueue` chỉ cần ba trường `head`, `tail`, `size`, tức **O(1)** bộ nhớ phụ ngoài các nút. So với mảng, danh sách liên kết có thêm chi phí con trỏ và cấp phát nút, nhưng không phải cấp phát trước một vùng nhớ liên tục hoặc định nghĩa sức chứa tối đa ngay từ đầu.

### So sánh với các cách cài đặt khác

| Biểu diễn queue | `enqueue` | `dequeue` | Đặc điểm |
|---|---|---|---|
| Danh sách đơn có `head` và `tail` | O(1) | O(1) | Số nút linh hoạt; tốn tham chiếu và cấp phát từng nút |
| Danh sách đơn chỉ lưu `head` | O(n) nếu phải tìm cuối | O(1) | Cần duyệt để nối cuối trong cách cài đặt thông thường |
| Mảng vòng sức chứa cố định | O(1) | O(1) | Bộ nhớ liên tục; cần xử lý trường hợp đầy |
| Mảng vòng tự mở rộng | O(1) khấu hao | O(1) | Có lần mở rộng phải sao chép O(n) phần tử |
| Python `list.append` + `list.pop(0)` | O(1) khấu hao | O(n) | Lấy ở đầu phải dịch các phần tử còn lại |

Một **deque** hỗ trợ thêm/lấy tại **cả hai đầu**. Danh sách đơn có `head` và `tail` phù hợp để làm queue FIFO; nếu muốn **lấy từ cuối** trong O(1), danh sách đơn vẫn phải tìm nút đứng trước `tail`, thường mất O(n). Để hiện thực đầy đủ deque với thao tác O(1) ở hai đầu, có thể dùng **danh sách liên kết đôi** hoặc **mảng vòng**.

## 9. Lỗi thường gặp và cách phát hiện

| Lỗi | Hậu quả | Cách tránh |
|---|---|---|
| Enqueue vào hàng rỗng nhưng chỉ gán `tail` | `head` vẫn rỗng; không thể lấy phần tử mới | Khi rỗng, gán **cả `head` và `tail`** |
| Dequeue nút cuối nhưng giữ lại `tail` cũ | `tail` trỏ vào nút không còn trong hàng | Nếu `head is None` sau lấy, đặt `tail = None` |
| Gán `tail = new_node` trước khi nối `old_tail.next` | Mất vị trí nút cuối cũ nếu không lưu tạm | Nối `tail.next` trước, rồi cập nhật `tail` |
| Dùng `value is None` để kiểm tra rỗng | Nhầm giá trị dữ liệu hợp lệ với trạng thái rỗng | Kiểm tra **tham chiếu nút** hoặc `size == 0` |
| Quên tăng/giảm `size` | `len(q)` sai, gây lệch bất biến | Cập nhật ở cuối mỗi nhánh thành công |
| Chỉ kiểm tra các thao tác khi hàng có nhiều nút | Không phát hiện lỗi khi chuyển từ 0 ↔ 1 nút | Thử cả hàng rỗng, một nút và chuỗi thao tác xen kẽ |

Các trường hợp nên tự kiểm tra khi viết một cài đặt mới:

- `dequeue()` và `peek()` trên hàng rỗng phải báo lỗi đúng hợp đồng.
- Enqueue đúng một phần tử rồi dequeue: cả `head`, `tail` đều rỗng; `size == 0`.
- Enqueue nhiều phần tử có **giá trị trùng nhau**: không mất hay đảo thứ tự các lần thêm.
- Enqueue `None` (nếu được phép): `dequeue()` vẫn lấy đúng một phần tử và cập nhật kích thước.
- Lặp nhiều lượt enqueue → dequeue tới rỗng → enqueue lại: không để sót liên kết hoặc con trỏ cũ.

## 10. Khi nào nên chọn cách cài đặt này?

Danh sách đơn có đầu và cuối phù hợp khi **số phần tử biến động**, cần thêm ở cuối và lấy ở đầu liên tục, muốn độ phức tạp O(1) cho các thao tác chính và chấp nhận chi phí tạo nút riêng.

Ví dụ, với hàng chờ xử lý phiếu yêu cầu:

1. Phiếu mới đến được đóng gói thành nút và nối vào `tail`.
2. Bộ xử lý lấy phiếu tại `head` và giải phóng nút đầu.
3. Khi tạm hết phiếu, `head = tail = None`; phiếu mới kế tiếp tạo lại hàng từ một nút.

Nếu hệ thống có giới hạn bộ nhớ rõ ràng và chú trọng tính cục bộ của dữ liệu trong bộ nhớ, mảng vòng thường là lựa chọn đáng cân nhắc. Nếu cần đồng bộ giữa các luồng hoặc tiến trình, phải chọn thêm cơ chế phối hợp thích hợp; cấu trúc `head`/`tail` một mình không giải quyết đồng thời.

## 11. Câu hỏi tự luyện

**Bài 1.** Một hàng đợi rỗng lần lượt thực hiện `enqueue(10)`, `enqueue(20)`, `dequeue()`, `enqueue(30)`. Vẽ `head`, `tail` và các con trỏ `next` ở trạng thái cuối.

*Đáp án:* `head → [20] → [30] → None`, `tail` trỏ nút `30` và `size = 2`. Phép dequeue trả về `10`.

**Bài 2.** Sau `enqueue("X")` rồi `dequeue()`, vì sao phải đưa `tail` về `None`?

*Đáp án:* Hàng đã rỗng; nếu `tail` còn trỏ tới nút `X` đã bị loại, lần enqueue tiếp theo có thể nối phần tử mới vào nút cũ trong khi `head` vẫn rỗng, vi phạm bất biến.

**Bài 3.** Một queue có một triệu phần tử. `enqueue(x)` cần duyệt bao nhiêu nút nếu đã lưu `tail` chính xác?

*Đáp án:* **Không cần duyệt nút nào**; chỉ tạo nút mới, nối vào `tail.next` rồi chuyển `tail`. Số bước thuật toán là O(1).

**Bài 4.** Vì sao danh sách liên kết đơn có `head` và `tail` chưa đủ để hỗ trợ `pop_back()` trong O(1)?

*Đáp án:* Để xóa nút cuối, phải tìm **nút liền trước `tail`** nhằm cập nhật `tail` và ngắt liên kết; danh sách đơn không có con trỏ quay ngược, nên thường phải duyệt O(n).

Điều cốt lõi của cài đặt này là **`head` giữ đường vào phần tử cần lấy, `tail` giữ điểm nối phần tử mới**. Khi bảo toàn các bất biến rỗng, một nút và liên kết cuối, queue thực hiện đúng FIFO với `enqueue` và `dequeue` O(1), cùng bộ nhớ O(n).
