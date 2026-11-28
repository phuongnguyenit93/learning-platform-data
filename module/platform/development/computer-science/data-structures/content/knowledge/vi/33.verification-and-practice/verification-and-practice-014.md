# Bài tập tổng hợp từ yêu cầu sử dụng đến cài đặt và chứng minh bất biến

Khi học một cấu trúc dữ liệu, việc biết thao tác `push`, `pop` hoặc `insert` có độ phức tạp `O(1)` hay `O(log n)` mới chỉ giải quyết một phần bài toán. Trong dự án thực tế, trước hết phải **diễn dịch yêu cầu thành hợp đồng thao tác**, tiếp theo **chọn cấu trúc thỏa các ràng buộc**, rồi **cài đặt và chứng minh rằng bất biến luôn đúng**. Cuối cùng, cần đối chiếu với một mô hình đơn giản và kiểm thử trường hợp biên.

Bài thực hành này đi xuyên suốt quy trình đó bằng một bài toán duy nhất: **quản lý hàng chờ yêu cầu dịch vụ có thể hủy theo mã yêu cầu**. Bài toán kết hợp hàng đợi FIFO, danh sách liên kết kép và bảng băm, đồng thời tạo điều kiện chứng minh tính đúng đắn bằng quy nạp trên các thao tác. Những kỹ năng này có thể áp dụng lại cho stack, heap, cây, bảng băm hay đồ thị.

> **Mục tiêu học tập:** Sau bài này, người học có thể viết đặc tả độc lập với cài đặt; đánh giá cấu trúc dữ liệu theo thao tác và tải sử dụng; xây dựng bất biến biểu diễn; chứng minh `enqueue`, `serve` và `cancel` bảo toàn bất biến; phân tích độ phức tạp; thiết kế phép thử mô hình và xác định giới hạn khi nhiều luồng truy cập.

## 1. Đề bài: hàng chờ có thể hủy yêu cầu

Một dịch vụ tiếp nhận các yêu cầu, mỗi yêu cầu có một mã định danh `id` duy nhất khi đang nằm trong hàng chờ. Hệ thống cần đáp ứng:

1. **Tiếp nhận** `enqueue(id)`: thêm yêu cầu mới vào **cuối hàng**. Nếu mã đã tồn tại trong hàng, từ chối và không thay đổi trạng thái.
2. **Phục vụ** `serve()`: lấy và xóa yêu cầu ở **đầu hàng**. Nếu hàng rỗng, trả về `None`.
3. **Hủy** `cancel(id)`: xóa yêu cầu có mã xác định, kể cả khi nó ở giữa hàng; nếu không tìm thấy thì không thay đổi trạng thái.
4. **Xem đầu hàng** `peek()`: trả mã đầu hàng mà không xóa.
5. **Tra cứu** `contains(id)`: cho biết yêu cầu có nằm trong hàng không.
6. **Liệt kê kiểm tra** `snapshot()`: trả danh sách mã theo thứ tự FIFO hiện tại.

Điều kiện bổ sung:

- Một mã đang chờ **không được xuất hiện hai lần**. Sau khi một mã được phục vụ hoặc hủy, mã đó có thể được đưa vào hàng lại như một yêu cầu mới.
- Mã là chuỗi không rỗng, không có khoảng trắng ở đầu/cuối; phân biệt chữ hoa và chữ thường. Mã sai định dạng gây `ValueError`.
- `enqueue` và `cancel` trả `True` khi thực sự thay đổi trạng thái, `False` khi yêu cầu hợp lệ nhưng bị trùng hoặc không tồn tại.
- Với quy mô lớn và hủy thường xuyên, mục tiêu là `enqueue`, `serve`, `cancel`, `peek` và `contains` có thời gian **`O(1)` trung bình**; `snapshot` được phép `O(n)`.
- Bài cài đặt cơ sở xử lý **tuần tự**. Phần mở rộng cuối bài xem xét nhiều luồng.

Giả sử thứ tự vào hàng, không có ưu tiên theo độ quan trọng, quyết định thứ tự phục vụ. Không cần lưu dữ liệu nghiệp vụ của yêu cầu ngoài mã `id`; khi mở rộng có thể thay bằng một đối tượng chứa thêm thông tin.

### Ví dụ hành vi mong muốn

| Lời gọi | Kết quả | Hàng chờ sau lời gọi |
| --- | --- | --- |
| Khởi tạo | — | `[]` |
| `enqueue("A")` | `True` | `[A]` |
| `enqueue("B")` | `True` | `[A, B]` |
| `enqueue("C")` | `True` | `[A, B, C]` |
| `enqueue("B")` | `False` | `[A, B, C]` |
| `cancel("B")` | `True` | `[A, C]` |
| `peek()` | `"A"` | `[A, C]` |
| `serve()` | `"A"` | `[C]` |
| `enqueue("B")` | `True` | `[C, B]` |
| `serve()` | `"C"` | `[B]` |
| `serve()` | `"B"` | `[]` |
| `serve()` | `None` | `[]` |

Việc `B` xuất hiện lần thứ hai là hợp lệ vì lần đầu đã bị hủy. Mục tiêu không phải bảo đảm mỗi mã chỉ được sử dụng một lần trong suốt đời hệ thống, mà là duy nhất **tại một thời điểm** trong hàng.

## 2. Chuyển yêu cầu thành đặc tả toán học

Trước khi nghĩ đến mảng, cây hay bảng băm, hãy định nghĩa trạng thái trừu tượng:

```text
Q = [q0, q1, ..., q(n-1)]

Q là dãy hữu hạn các mã phân biệt.
Q[0] là phần tử vào hàng sớm nhất trong số các phần tử còn chờ.
```

Gọi `x ∈ Q` khi mã `x` đang xuất hiện trong dãy. Với một yêu cầu hợp lệ `x`, hợp đồng thao tác như sau:

| Thao tác | Điều kiện | Trạng thái sau | Kết quả |
| --- | --- | --- | --- |
| `enqueue(x)` | `x ∉ Q` | `Q' = Q + [x]` | `True` |
| `enqueue(x)` | `x ∈ Q` | `Q' = Q` | `False` |
| `serve()` | `Q = []` | `Q' = Q` | `None` |
| `serve()` | `Q = [x] + R` | `Q' = R` | `x` |
| `cancel(x)` | `x ∈ Q` | `Q' = Q` bỏ đúng phần tử `x`, giữ thứ tự các phần tử khác | `True` |
| `cancel(x)` | `x ∉ Q` | `Q' = Q` | `False` |
| `peek()` | `Q` khác rỗng | `Q' = Q` | `Q[0]` |
| `peek()` | `Q` rỗng | `Q' = Q` | `None` |
| `contains(x)` | Mọi `Q` | `Q' = Q` | `x ∈ Q` |
| `snapshot()` | Mọi `Q` | `Q' = Q` | Bản sao của `Q` |

Đây là **đặc tả hành vi**, không phụ thuộc cách dữ liệu nằm trong bộ nhớ. Ta có thể dùng danh sách Python làm mô hình tham chiếu đơn giản dù thao tác hủy theo mã của mô hình có thể là `O(n)`.

### Những bất biến thuộc tầng đặc tả

Hai tính chất quan trọng của trạng thái trừu tượng là:

- **Duy nhất:** không có `i != j` sao cho `Q[i] == Q[j]`.
- **FIFO của những yêu cầu còn chờ:** nếu `a` được thêm trước `b` và cả hai vẫn nằm trong `Q`, thì `a` xuất hiện trước `b`. Hủy một yêu cầu không thay đổi thứ tự tương đối giữa các yêu cầu còn lại.

Cần chứng minh cài đặt duy trì hai tính chất này, ngoài việc trả đúng kết quả của từng hàm.

## 3. Chọn cấu trúc từ yêu cầu sử dụng

Thử xét một số phương án:

| Phương án | Thêm cuối | Phục vụ đầu | Hủy một mã bất kỳ | Tra cứu mã | Nhận xét |
| --- | --- | --- | --- | --- | --- |
| Mảng động/list | `O(1)` khấu hao | `O(n)` do dịch phần tử khi xóa đầu | `O(n)` tìm và dịch | `O(n)` | Dễ viết nhưng không đạt mục tiêu khi hàng lớn |
| Queue dựa trên deque | `O(1)` | `O(1)` | `O(n)` tìm và xóa mã ở giữa | `O(n)` | Phù hợp nếu rất ít hủy theo mã |
| Danh sách liên kết kép | `O(1)` khi giữ hai đầu | `O(1)` | `O(1)` sau khi có nút, nhưng tìm nút mất `O(n)` | `O(n)` | Thiếu chỉ mục tra cứu |
| Bảng băm đơn thuần | `O(1)` trung bình | Không trực tiếp biểu diễn đầu FIFO theo cách tổng quát | `O(1)` trung bình | `O(1)` trung bình | Cần duy trì thứ tự phục vụ ngoài tra cứu |
| **Danh sách liên kết kép + bảng băm** | **`O(1)` trung bình** | **`O(1)`** | **`O(1)` trung bình** | **`O(1)` trung bình** | Đáp ứng đủ hợp đồng và minh họa bất biến kết hợp |

Ta chọn **danh sách liên kết kép** để lưu thứ tự và **dictionary/bảng băm** ánh xạ `id -> node` để tìm ngay nút cần hủy. Hai cấu trúc phải luôn nhất quán: nút xuất hiện trong danh sách khi và chỉ khi chỉ mục có mục tương ứng.

### Cách biểu diễn

Dùng hai nút gác (*sentinel*) `head` và `tail`, không phải yêu cầu thực:

```text
head <──> Node("A") <──> Node("B") <──> Node("C") <──> tail
           ^               ^               ^
           |               |               |
index:  "A" ----------  "B" ----------  "C"     (id -> chính đối tượng node)
```

- `head.next` là yêu cầu đầu tiên, hoặc là `tail` nếu rỗng.
- `tail.prev` là yêu cầu cuối cùng, hoặc là `head` nếu rỗng.
- Mỗi nút thực có hai liên kết `prev`, `next` và một mã `id`.
- `index[id]` trỏ đến **chính nút** chứa `id` trong danh sách.
- `size` đếm số nút thực, không tính sentinel.

Hai nút gác giúp xóa đầu, giữa, cuối bằng cùng một thao tác nối hai hàng xóm, giảm nhánh xử lý đặc biệt.

**Câu hỏi trước khi xem lời giải:** Nếu chỉ sử dụng danh sách liên kết đơn và bảng băm `id -> node`, tại sao xóa nút tùy ý khó đạt `O(1)`? Vì để bỏ một nút khỏi danh sách đơn, thông thường cần biết nút **đứng trước nó** để sửa `prev.next`; việc chỉ biết nút cần xóa chưa bảo đảm có thể sửa liên kết trong `O(1)` mà vẫn giữ các ràng buộc tổng quát.

## 4. Phát biểu bất biến biểu diễn

Để chứng minh chính xác, đặt `L` là dãy nút thực khi đi theo `next` từ `head` đến `tail`. Ta giữ các bất biến sau tại thời điểm kết thúc mỗi thao tác công khai.

**I1 — Hai sentinel hợp lệ.** `head` và `tail` là hai đối tượng phân biệt; `head.prev == None` và `tail.next == None`. Danh sách rỗng khi và chỉ khi `head.next is tail` và `tail.prev is head`.

**I2 — Liên kết hai chiều đối xứng.** Với mọi liên kết từ một nút `u` tới `v = u.next`, có `v.prev is u`. Tương tự, với mọi liên kết ngược `v.prev = u`, phải có `u.next is v`.

**I3 — Đường đi hữu hạn, không lặp.** Đi theo `next` bắt đầu tại `head` sẽ tới `tail` sau hữu hạn bước và không đi qua một nút thực hai lần. Không có nhánh/nút thực “mồ côi” thuộc cấu trúc nhưng không nằm trên đường đi này.

**I4 — Chỉ mục là song ánh với nút thực.** Với mỗi nút thực `v` trong `L`, `index[v.id] is v`. Ngược lại, mỗi mục `index[k]` trỏ đúng một nút thực trong `L` có mã `k`. Vì vậy không có mã trùng và không có khóa trỏ đến nút đã bị xóa.

**I5 — Số lượng khớp.** `size == len(L) == len(index)`.

Đây là các **bất biến biểu diễn (representation invariants)**. Chúng nói cấu trúc bộ nhớ phải trông như thế nào. Bất biến về thứ tự FIFO thuộc **ngữ nghĩa** của dãy trừu tượng và sẽ được chứng minh thông qua cách thêm/xóa nút.

Có thể mô tả quan hệ giữa tầng biểu diễn và tầng đặc tả:

```text
Cấu trúc cụ thể (head, tail, next, prev, index, size)
                         |
                         | abstraction function
                         v
Dãy trừu tượng Q = [node.id for node theo head.next ... tail.prev]
```

Nếu cài đặt giữ I1–I5 và mỗi thao tác chuyển `Q` đúng theo bảng đặc tả, ta đã có bằng chứng tính đúng đắn đối với hợp đồng tuần tự đã đặt ra.

## 5. Cài đặt hoàn chỉnh bằng Python

Đoạn mã sau dùng Python 3, mỗi `id` là chuỗi và `dict` làm chỉ mục băm. Hàm `check_invariants` chỉ dùng khi học và kiểm thử; không gọi nó trong đường xử lý hiệu năng cao.

```python
class _Node:
    __slots__ = ("ticket_id", "prev", "next")

    def __init__(self, ticket_id):
        self.ticket_id = ticket_id
        self.prev = None
        self.next = None


class TicketQueue:
    def __init__(self):
        self._head = _Node(None)
        self._tail = _Node(None)
        self._head.next = self._tail
        self._tail.prev = self._head

        self._index = {}   # ticket_id -> chính đối tượng _Node
        self._size = 0

    @staticmethod
    def _validate_id(ticket_id):
        if (not isinstance(ticket_id, str)
                or not ticket_id
                or ticket_id.strip() != ticket_id):
            raise ValueError("id phải là chuỗi không rỗng, không có "
                             "khoảng trắng ở hai đầu")

    def __len__(self):
        return self._size

    def contains(self, ticket_id):
        self._validate_id(ticket_id)
        return ticket_id in self._index

    def enqueue(self, ticket_id):
        self._validate_id(ticket_id)
        if ticket_id in self._index:
            return False

        node = _Node(ticket_id)
        # Đưa vào chỉ mục trước; nếu chèn vào dict thất bại do
        # lỗi cấp phát, các liên kết của danh sách chưa bị sửa.
        self._index[ticket_id] = node

        prev = self._tail.prev
        prev.next = node
        node.prev = prev
        node.next = self._tail
        self._tail.prev = node
        self._size += 1
        return True

    def _remove_node(self, node):
        # Tiền điều kiện: node là nút thực còn nằm trong danh sách.
        prev, nxt = node.prev, node.next
        prev.next = nxt
        nxt.prev = prev

        ticket_id = node.ticket_id
        del self._index[ticket_id]
        self._size -= 1

        # Ngắt các liên kết cũ để tránh vô tình tái sử dụng nút.
        node.prev = None
        node.next = None
        return ticket_id

    def serve(self):
        first = self._head.next
        if first is self._tail:
            return None
        return self._remove_node(first)

    def cancel(self, ticket_id):
        self._validate_id(ticket_id)
        node = self._index.get(ticket_id)
        if node is None:
            return False
        self._remove_node(node)
        return True

    def peek(self):
        first = self._head.next
        return None if first is self._tail else first.ticket_id

    def snapshot(self):
        result = []
        cur = self._head.next
        while cur is not self._tail:
            result.append(cur.ticket_id)
            cur = cur.next
        return result

    def check_invariants(self):
        # Chỉ để kiểm thử, O(n); không gọi trong thao tác nóng.
        assert self._head is not self._tail
        assert self._head.prev is None
        assert self._tail.next is None

        seen_ids = set()
        cur = self._head
        count = 0

        while cur is not self._tail:
            nxt = cur.next
            assert nxt is not None
            assert nxt.prev is cur
            cur = nxt

            if cur is not self._tail:
                assert cur.ticket_id not in seen_ids
                assert self._index.get(cur.ticket_id) is cur
                seen_ids.add(cur.ticket_id)
                count += 1
                assert count <= self._size

        assert count == self._size
        assert len(self._index) == self._size
        assert set(self._index) == seen_ids

        # Đi ngược lại để kiểm tra các liên kết prev.
        cur = self._tail
        backward_count = 0
        while cur is not self._head:
            prev = cur.prev
            assert prev is not None
            assert prev.next is cur
            cur = prev
            if cur is not self._head:
                backward_count += 1
                assert backward_count <= self._size
        assert backward_count == self._size
```

Ví dụ sử dụng:

```python
q = TicketQueue()

assert q.enqueue("A") is True
assert q.enqueue("B") is True
assert q.enqueue("C") is True
assert q.enqueue("B") is False
assert q.cancel("B") is True
assert q.snapshot() == ["A", "C"]
assert q.peek() == "A"
assert q.serve() == "A"
assert q.enqueue("B") is True
assert q.snapshot() == ["C", "B"]
assert q.contains("C") is True
assert len(q) == 2
q.check_invariants()
```

Ở đây `_remove_node` là thao tác nội bộ duy nhất gỡ nút, được cả `serve` và `cancel` sử dụng. Gom cách thay đổi liên kết vào cùng một hàm giúp giảm nguy cơ hai đường code duy trì các bất biến khác nhau.

**Phạm vi của mã:** Đây là cài đặt *tuần tự*. Dù Python có GIL ở một số runtime, các cập nhật `dict`, `prev`, `next` và `size` là nhiều bước liên tiếp; không được mặc định toàn bộ thao tác là nguyên tử khi nhiều luồng gọi cùng lúc.

## 6. Chứng minh đúng đắn bằng quy nạp theo số thao tác

Ta cần chứng minh hai mệnh đề:

- **P1:** I1–I5 đúng sau mỗi thao tác công khai hoàn tất bình thường.
- **P2:** Dãy trừu tượng `Q` của cấu trúc thay đổi đúng bảng đặc tả ở mục 2.

Cách chứng minh là **quy nạp theo độ dài chuỗi thao tác** trên cấu trúc ban đầu rỗng.

### 6.1. Cơ sở quy nạp: hàng chờ mới tạo

Hàm khởi tạo tạo hai sentinel và nối:

```text
head.next = tail
tail.prev = head
head.prev = None
tail.next = None
index = {}
size = 0
```

Không có nút thực nên I1, I2 và I3 đúng. Chỉ mục rỗng, số lượng bằng 0 nên I4–I5 đúng. Hàm trừu tượng trả `Q = []`, phù hợp trạng thái ban đầu. Vậy P1 và P2 đúng trước thao tác đầu tiên.

### 6.2. Bước quy nạp: `enqueue(x)`

**Giả thiết quy nạp:** trước lời gọi, cấu trúc thỏa I1–I5 và biểu diễn đúng `Q`.

- Nếu `x` không hợp lệ, hàm ném `ValueError` trước khi sửa cấu trúc; trạng thái không đổi.
- Nếu `x` đã là khóa trong `index`, hàm trả `False`, không đổi trạng thái. Điều này đúng với đặc tả `x ∈ Q`.
- Nếu `x` chưa tồn tại, tạo đúng một nút mới và nối vào **giữa nút cuối hiện hành với sentinel `tail`**. Bốn liên kết quanh vị trí thêm được thiết lập tương hỗ: `prev.next = node`, `node.prev = prev`, `node.next = tail` và `tail.prev = node`.

Vì đường đi cũ hữu hạn và nút mới chưa xuất hiện trong đó, kết quả vẫn là một đường đi không lặp và kết thúc ở `tail` (I1–I3). Chỉ mục thêm đúng `x -> node`, không trùng khóa và không trỏ sai nút (I4); số nút, số khóa và `size` cùng tăng 1 (I5). Dãy trừu tượng chuyển từ `Q` thành `Q + [x]`, đúng FIFO và đặc tả. P1–P2 được bảo toàn.

### 6.3. Bước quy nạp: `serve()`

Nếu `head.next is tail`, I1–I5 cho thấy cấu trúc không có nút thực. Hàm trả `None` và giữ nguyên `Q = []`.

Ngược lại, `first = head.next` là nút thực đầu tiên trong `L`. Hàm `_remove_node(first)` nối trực tiếp hai hàng xóm `head` và `first.next`, xóa khóa của `first` trong chỉ mục, giảm `size` đúng 1. Các nút còn lại giữ nguyên liên kết tương đối, đường đi từ `head` tới `tail` vẫn hữu hạn và không lặp. I1–I5 tiếp tục đúng, còn `Q = [x] + R` chuyển thành `R` và trả `x`. Đây chính là hợp đồng `serve`.

### 6.4. Bước quy nạp: `cancel(x)`

Với mã hợp lệ nhưng không tồn tại, `index.get(x)` trả `None`; hàm không sửa gì và trả `False`.

Nếu mã tồn tại, từ I4 suy ra `index[x]` là **đúng một nút thực** trên đường đi. `_remove_node` bỏ nút đó bằng cách nối `prev` với `next`; các nút khác giữ nguyên thứ tự. Xóa đúng một mục chỉ mục và giảm `size` 1 giữ I4–I5; đường đi và liên kết hai chiều vẫn hợp lệ nên giữ I1–I3. Hàm trả `True`; dãy `Q` bị xóa đúng một lần xuất hiện của `x` và giữ nguyên thứ tự các phần tử khác.

Lập luận này áp dụng cho cả hủy đầu hàng, giữa hàng, cuối hàng và hàng chỉ có một phần tử vì sentinel khiến thao tác nối có cùng dạng.

### 6.5. Các thao tác chỉ đọc

`contains`, `peek`, `snapshot` và `__len__` không thay đổi liên kết, chỉ mục hoặc số lượng. Do I4–I5, kết quả tra cứu và kích thước đúng với `Q`. Do I1–I3 và việc duyệt theo `next`, `snapshot` trả các mã theo đúng thứ tự trong `Q`, còn `peek` đọc phần tử đầu hoặc `None` nếu rỗng. Bất biến không thay đổi.

**Kết luận quy nạp:** Sau mọi chuỗi thao tác hợp lệ chạy tuần tự và hoàn tất bình thường, I1–I5 vẫn đúng và trạng thái trừu tượng luôn đáp ứng đặc tả. Do đó, thao tác duy trì tính duy nhất mã và FIFO của những yêu cầu chưa bị hủy hoặc phục vụ.

**Lưu ý về phạm vi chứng minh:** Lập luận giả sử một thao tác không bị xen kẽ bởi thao tác khác và các thao tác bộ nhớ bình thường hoàn tất. Muốn bảo đảm tính nhất quán giữa chừng nếu có lỗi cấp phát, tín hiệu bất thường hoặc nhiều luồng đồng thời, cần thêm cơ chế xử lý ngoại lệ/đồng bộ và chứng minh riêng cho các tình huống đó.

## 7. Chứng minh kết thúc và phân tích độ phức tạp

### 7.1. Vì sao các thao tác kết thúc?

`enqueue`, `serve`, `cancel`, `peek` và `contains` không có vòng lặp phụ thuộc độ dài cấu trúc; khi phép toán trên `dict` hoàn tất, chúng kết thúc sau hữu hạn bước.

`snapshot` xuất phát từ `head.next` và di chuyển theo `next`. Theo I3, đường đi có đúng `n` nút thực trước khi tới `tail`; mỗi vòng lặp đi sang một nút kế tiếp, nên vòng lặp kết thúc sau `n` bước.

`check_invariants` là công cụ kiểm tra trạng thái khi giả định cấu trúc đang đúng. Trong trường hợp cấu trúc bị phá, các điều kiện `assert` và giới hạn đếm phát hiện một số dạng sai; nó không thay thế việc xác minh đầy đủ trên mọi kiểu đồ thị con trỏ hỏng.

### 7.2. Thời gian và bộ nhớ

Gọi `n` là số yêu cầu đang chờ, với hàm băm phân bố phù hợp:

| Thao tác | Thời gian trung bình | Trường hợp xấu đáng chú ý | Bộ nhớ phụ của một lời gọi |
| --- | --- | --- | --- |
| `enqueue(x)` | `O(1)` | Truy cập/chèn `dict` có thể `O(n)` | `O(1)` ngoài nút và mục bảng băm được thêm |
| `serve()` | `O(1)` trung bình | Xóa khỏi `dict` có thể chịu trường hợp xấu của bảng băm | `O(1)` |
| `cancel(x)` | `O(1)` trung bình | Tra cứu `dict` có thể `O(n)` | `O(1)` |
| `contains(x)` | `O(1)` trung bình | Tra cứu `dict` có thể `O(n)` | `O(1)` |
| `peek()`, `len(q)` | `O(1)` | `O(1)` theo mô hình truy cập trường | `O(1)` |
| `snapshot()` | `O(n)` | `O(n)` nếu bất biến đúng | `O(n)` |
| `check_invariants()` | `O(n)` trung bình | Kiểm tra bộ băm chịu đặc tính bảng băm | `O(n)` do tập mã đã thấy |

Toàn bộ trạng thái của queue dùng `O(n)` bộ nhớ: `n` nút liên kết và `n` mục bảng băm, cộng hai sentinel. Bảng băm có thể cấp phát dư dung lượng so với số mục thực, nhưng vẫn `O(n)` theo mô hình thông thường.

**Không khẳng định `O(1)` tuyệt đối cho mọi thao tác chỉ vì có hash map.** Bảng băm phụ thuộc vào độ phân bố băm, va chạm, tái băm và triển khai cụ thể. Nếu hợp đồng thật sự đòi **cận xấu nhất** nghiêm ngặt, cần chọn thiết kế và giả định khác, hoặc chấp nhận một mức `O(log n)` với cây tìm kiếm cân bằng.

Chi phí xây chỉ mục bằng bảng băm là cái giá để hủy theo mã nhanh. Nếu yêu cầu chỉ có thêm cuối và phục vụ đầu, một deque thông thường đơn giản hơn và dùng ít cấu trúc phụ hơn.

## 8. Kiểm thử có hệ thống: ví dụ, bất biến và mô hình tham chiếu

Chứng minh giải thích vì sao thuật toán đúng **nếu được triển khai như mô tả**. Kiểm thử giúp phát hiện lỗi mã hóa, sai giả định, thiếu trường hợp biên hoặc thay đổi ngoài ý muốn. Hai cách bổ trợ nhau.

### 8.1. Bảng trường hợp kiểm thử trọng tâm

| Trường hợp | Chuỗi thao tác | Điều cần xác nhận |
| --- | --- | --- |
| Rỗng | `serve()`, `peek()`, `cancel("X")` | Trả `None`, `None`, `False`; `size = 0` |
| Một phần tử | `enqueue("A")` rồi `serve()` | Trả A, trở lại danh sách rỗng có liên kết sentinel đúng |
| Trùng mã | `enqueue("A")` hai lần | Lần sau `False`, một nút và một mục chỉ mục |
| Hủy đầu | `[A,B,C]` rồi `cancel("A")` | `[B,C]`, đầu mới là B |
| Hủy giữa | `[A,B,C]` rồi `cancel("B")` | `[A,C]`, thứ tự giữ nguyên |
| Hủy cuối | `[A,B,C]` rồi `cancel("C")` | `[A,B]`, có thể thêm cuối tiếp |
| Hủy rồi thêm lại | `enqueue("A")`, `cancel("A")`, `enqueue("A")` | Lần thêm lại thành công |
| Không tồn tại | `cancel("Z")`, `contains("Z")` | `False`; trạng thái không đổi |
| ID không hợp lệ | `enqueue("")`, `cancel(" A ")` | `ValueError`; trạng thái không đổi |
| Chuỗi dài | Hàng nghìn lượt thêm, phục vụ, hủy | `snapshot()` và I1–I5 luôn khớp mô hình |

Sau mỗi thao tác thay đổi cấu trúc, trong môi trường kiểm thử hãy gọi `check_invariants()`. Điều này phát hiện sớm lỗi nối liên kết thay vì chỉ thấy thứ tự sai ở cuối bài thử.

### 8.2. Kiểm thử mô hình (*model-based testing*)

Dùng một `list` chậm nhưng dễ hiểu làm **oracle**. Với mỗi thao tác ngẫu nhiên, cập nhật cả `TicketQueue` và danh sách mô hình, so sánh kết quả. Mục tiêu của oracle là **đúng và đơn giản**, không cần nhanh.

```python
import random
import unittest


class TicketQueueTest(unittest.TestCase):
    def test_example_and_edges(self):
        q = TicketQueue()
        self.assertIsNone(q.serve())
        self.assertIsNone(q.peek())
        self.assertFalse(q.cancel("missing"))
        self.assertTrue(q.enqueue("A"))
        self.assertTrue(q.enqueue("B"))
        self.assertFalse(q.enqueue("A"))
        self.assertTrue(q.cancel("A"))
        self.assertEqual(q.serve(), "B")
        self.assertEqual(q.snapshot(), [])
        q.check_invariants()

        with self.assertRaises(ValueError):
            q.enqueue("")
        with self.assertRaises(ValueError):
            q.cancel(" A ")
        q.check_invariants()

    def test_random_operations_against_list(self):
        rng = random.Random(2026)  # Có thể lặp lại cùng chuỗi thao tác.
        q = TicketQueue()
        model = []

        for _ in range(3000):
            ticket_id = f"T{rng.randrange(50)}"
            op = rng.randrange(4)

            if op == 0:                # enqueue
                expected = ticket_id not in model
                self.assertEqual(q.enqueue(ticket_id), expected)
                if expected:
                    model.append(ticket_id)

            elif op == 1:              # cancel
                expected = ticket_id in model
                self.assertEqual(q.cancel(ticket_id), expected)
                if expected:
                    model.remove(ticket_id)

            elif op == 2:              # serve
                expected = model.pop(0) if model else None
                self.assertEqual(q.serve(), expected)

            else:                       # peek
                expected = model[0] if model else None
                self.assertEqual(q.peek(), expected)

            self.assertEqual(q.snapshot(), model)
            self.assertEqual(len(q), len(model))
            self.assertEqual(q.contains(ticket_id),
                             ticket_id in model)
            q.check_invariants()


if __name__ == "__main__":
    unittest.main()
```

Bài thử này không chứng minh đầy đủ mọi đầu vào, nhưng có giá trị ở chỗ **thao tác của oracle không dùng cùng thuật toán liên kết kép**. Nếu sao chép nguyên xi logic đang kiểm thử để làm oracle, hai phía có thể mắc cùng một lỗi.

### 8.3. Kiểm thử các tính chất độc lập

Ngoài so sánh với mô hình, có thể kiểm tra các tính chất (*properties*):

- **Tính không đổi:** `peek` và `contains` không sửa `snapshot`.
- **Thêm rồi hủy:** nếu `x` chưa tồn tại, `enqueue(x)` rồi `cancel(x)` khôi phục dãy ban đầu.
- **Trùng mã không có tác dụng:** nếu `x` đã tồn tại, `enqueue(x)` trả `False` và `snapshot` không đổi.
- **Hủy không đổi thứ tự còn lại:** sau `cancel(x)`, dãy mới bằng dãy cũ đã xóa `x`.
- **Phục vụ đúng đầu hàng:** nếu dãy trước là `[a] + R`, `serve()` trả `a` và để lại `R`.
- **Bảo toàn kích thước:** khi thêm/hủy/phục vụ thành công, kích thước đổi đúng `+1` hoặc `-1`; khi thất bại, không đổi.

Các tính chất này tiếp tục hữu ích nếu thay cài đặt bằng cây, hash map có duy trì thứ tự hoặc một queue khác.

## 9. Phát hiện các lỗi thiết kế và chứng minh thường gặp

**Lỗi 1 — Xóa khỏi danh sách nhưng quên xóa chỉ mục.** `serve()` đã nối lại `head` và nút kế tiếp, nhưng `index` vẫn giữ mã cũ. Khi thêm mã đó lần nữa, chương trình từ chối sai; I4 và I5 bị phá vỡ.

**Lỗi 2 — Xóa chỉ mục nhưng quên nối `prev` và `next`.** `cancel(x)` trả `True` nhưng `snapshot()` vẫn liệt kê mã đã hủy. Một thao tác có thể trả kết quả “đúng kiểu” nhưng trạng thái không đúng.

**Lỗi 3 — Chỉ sửa một chiều.** Sau hủy B khỏi `A <-> B <-> C`, mã đã đặt `A.next = C` nhưng quên `C.prev = A`. Duyệt xuôi có thể trông đúng, còn thao tác hủy C tiếp theo sẽ dùng con trỏ ngược lỗi thời. Đây là lý do cần I2 và kiểm tra duyệt ngược.

**Lỗi 4 — Coi phép thử vài đầu vào là chứng minh.** Một test hủy phần tử đầu không bao phủ hủy cuối hoặc hàng một phần tử. Chứng minh quy nạp phải phân tích các lớp trường hợp ảnh hưởng bất biến, còn kiểm thử nên cố gắng làm sai giả định bằng trường hợp biên.

**Lỗi 5 — Phân tích độ phức tạp theo tên cấu trúc.** “Có hash map nên mọi thao tác `O(1)`” là thiếu điều kiện; phải nêu trung bình hay xấu nhất, có resize hay không, và có thao tác ẩn phải duyệt toàn bộ danh sách không.

**Lỗi 6 — Tuyên bố thread-safe từ thao tác riêng lẻ.** Hai luồng cùng chạy `enqueue` có thể cùng đọc `tail.prev` trước khi gắn nút và làm mất liên kết, dù từng phép gán con trỏ rất nhỏ. Tính đúng đắn tuần tự **không tự nâng thành** đúng đắn đồng thời.

## 10. Mở rộng bài tập

### Mức 1: thay đổi yêu cầu, phân tích lại cấu trúc

Giả sử dịch vụ muốn **chèn yêu cầu ưu tiên** để xử lý yêu cầu có độ ưu tiên cao trước, còn những yêu cầu cùng mức vẫn FIFO. Hãy viết lại đặc tả và cân nhắc:

- Một **heap** cho lấy yêu cầu có ưu tiên cao `O(log n)` khi thêm và `O(log n)` khi lấy; tra cứu/hủy theo mã cần chỉ mục `id -> vị_trí` và cập nhật vị trí mỗi lần đổi chỗ.
- Một cấu trúc **nhiều deque theo mức ưu tiên** có thể đơn giản hơn nếu số mức ưu tiên nhỏ và cố định; cần nêu cách tìm mức không rỗng cao nhất.
- Nếu vẫn cần hủy theo mã trong `O(1)` trung bình nhưng có nhiều mức ưu tiên, có thể dùng `id -> node` trên các danh sách liên kết của từng mức và thêm chỉ mục mức cao nhất đang có yêu cầu.

**Yêu cầu nộp:** bảng thao tác, độ phức tạp, bất biến mới và một trường hợp mà cấu trúc ban đầu không còn thỏa yêu cầu.

### Mức 2: bổ sung đa luồng

Giả sử nhiều worker có thể gọi `enqueue`, `serve` và `cancel` đồng thời. Cài đặt hiện tại không thread-safe.

Một phương án cơ sở là dùng **một mutex duy nhất** bảo vệ toàn bộ các thao tác trên `_head`, `_tail`, `_index` và `_size`. Khi gọi `snapshot`, cũng phải giữ cùng khóa trong suốt quá trình duyệt hoặc tạo ra một bản sao nhất quán dưới khóa.

**Câu hỏi cần chứng minh:** Với một mutex bao quanh mỗi thao tác, các lời gọi đồng thời có thể tuyến tính hóa tại đâu? Có thể lập luận rằng các thao tác thay đổi trạng thái được tuần tự hóa theo thứ tự nắm khóa; từng trạng thái quan sát được sau khi nhả khóa thỏa I1–I5. Nhưng đổi lại, throughput có thể bị giới hạn bởi thời gian giữ khóa, đặc biệt khi `snapshot` duyệt `O(n)` phần tử.

Không thể đơn giản thay mutex bằng vài lệnh CAS mà vẫn giữ nguyên chứng minh tuần tự: cần phân tích trạng thái trung gian, tiến triển, nguy cơ ABA và vòng đời nút.

### Mức 3: giảm bộ nhớ hoặc thay đổi mô hình tải

Nếu hủy rất hiếm, cân nhắc deque đơn thuần để giảm bộ nhớ chỉ mục. Nếu nhiều yêu cầu dùng lại một mã sau khi đã hoàn tất, kiểm tra kỹ xem **duy nhất lúc đang chờ** có đúng hợp đồng nghiệp vụ không. Nếu cần tra cứu lịch sử đã phục vụ, phải thêm trạng thái khác; đừng để `index` của hàng chờ vừa đóng vai trò lịch sử vừa đóng vai trò các nút hiện tại.

Nếu tỷ lệ thêm và hủy cao, có thể so sánh với deque có “tombstone” (đánh dấu đã hủy) cùng bảng băm. Lúc ấy cần làm rõ thời gian loại bỏ tombstone, nguy cơ `O(n)` khi phải dọn một chuỗi dài ở đầu, và mức bộ nhớ phình ra khi chưa dọn. Cách đo cũng cần thể hiện tỷ lệ hủy và chu kỳ dọn dẹp.

## 11. Tiêu chí đánh giá một lời giải tổng hợp

Một bài giải được xem là hoàn chỉnh về mặt thiết kế khi có đủ các thành phần dưới đây:

| Thành phần | Câu hỏi tự đánh giá |
| --- | --- |
| **Yêu cầu và hợp đồng** | Có nêu rõ kết quả, trạng thái sau thao tác, trường hợp rỗng/trùng/không tồn tại không? |
| **Lựa chọn cấu trúc** | Có gắn mỗi yêu cầu hiệu năng với một cấu trúc và thừa nhận đánh đổi không? |
| **Bất biến biểu diễn** | Có mô tả quan hệ giữa danh sách, chỉ mục và kích thước, bao gồm các nút biên không? |
| **Chứng minh** | Có trường hợp cơ sở, bước bảo toàn cho từng thao tác thay đổi dữ liệu và lập luận cho thao tác chỉ đọc không? |
| **Kết thúc và độ phức tạp** | Có nêu đúng cận trung bình/xấu nhất, tính cả bộ nhớ và thao tác duyệt không? |
| **Kiểm thử** | Có kiểm tra trường hợp biên, chuỗi thao tác hỗn hợp, bất biến và đối chiếu với oracle độc lập không? |
| **Giới hạn** | Có phân biệt cài đặt tuần tự, đồng thời và các điều kiện của mô hình bộ nhớ không? |

**Bài tập suy ngẫm cuối:** Nếu bỏ hoàn toàn `index` khỏi cài đặt mà vẫn yêu cầu `cancel(id)` trung bình `O(1)` cho hàng rất lớn, bạn có còn giữ được hợp đồng hiện tại không? Hãy nêu giả định bổ sung (nếu có), cấu trúc thay thế và bằng chứng về độ phức tạp. Nếu không có giả định mới hoặc cách truy cập trực tiếp tới nút, việc tìm mã trong danh sách liên kết sẽ thường cần duyệt `O(n)`.

Điểm cốt lõi của một bài tập cấu trúc dữ liệu tổng hợp là **nối được yêu cầu sử dụng với biểu diễn, từ biểu diễn với bất biến, từ thao tác với chứng minh, rồi từ chứng minh với phép kiểm tra thực tế**. Khi các mắt xích đó rõ ràng, quyết định chọn cấu trúc mới có cơ sở cả về tính đúng đắn lẫn hiệu năng.
