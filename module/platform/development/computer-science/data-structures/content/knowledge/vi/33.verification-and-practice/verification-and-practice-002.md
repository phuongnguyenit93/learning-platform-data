# Kiểm tra bất biến sau từng thao tác cập nhật

Một phép toán trên cấu trúc dữ liệu không chỉ phải trả về kết quả đúng mà còn phải để cấu trúc ở trạng thái **hợp lệ cho phép toán tiếp theo**. Một lỗi nhỏ trong `insert`, `delete` hoặc `resize` có thể chưa lộ ra ngay; nhiều lần gọi sau đó mới khiến dữ liệu sai, duyệt vô hạn hoặc truy cập ngoài phạm vi. Đó là lý do cần phát biểu **bất biến** (*invariant*) và kiểm tra chúng sau mỗi thao tác cập nhật, đặc biệt trong giai đoạn phát triển và kiểm thử.

Trong bài học về kiểm chứng và thực hành cấu trúc dữ liệu, ta sẽ học cách chuyển bất biến thành điều kiện có thể chạy kiểm tra, chọn thời điểm kiểm tra hợp lý và kết hợp với kiểm thử hành vi. Cách làm áp dụng được cho mảng, danh sách liên kết, Stack, Queue, bảng băm, cây, heap và đồ thị.

## 1. Bất biến là gì, và kiểm tra được điều gì?

**Bất biến cấu trúc dữ liệu** là mệnh đề phải đúng ở mọi trạng thái *ổn định* mà cấu trúc công khai cho người gọi. Ví dụ:

- Mảng động có `0 <= size <= capacity`.
- Queue vòng có chỉ số đầu nằm trong phạm vi bộ đệm và các phần tử theo đúng thứ tự logic.
- Danh sách liên kết đôi có các liên kết `prev` và `next` nhất quán.
- Min-heap có khóa của cha không lớn hơn khóa của từng con.
- Cây tìm kiếm nhị phân có thứ tự khóa phù hợp với quy ước về khóa trùng.

Cần phân biệt ba loại mệnh đề liên quan:

| Loại | Nội dung | Ví dụ Queue |
|---|---|---|
| **Bất biến biểu diễn** | Điều kiện nội bộ để bộ nhớ/trạng thái lưu trữ nhất quán | `0 <= count <= len(buffer)`; `head` là chỉ số hợp lệ |
| **Đặc tả hành vi** | Kết quả quan sát được qua API | `dequeue` trả phần tử vào Queue sớm nhất |
| **Điều kiện trước/sau** | Yêu cầu và kết quả của một lần gọi cụ thể | Khi Queue không rỗng, `dequeue` giảm `count` đúng 1 |

Bất biến biểu diễn là *điều kiện cần* để cài đặt đúng, nhưng không luôn đủ để kết luận hành vi đúng. Một Queue có `count = 3` và chỉ số hợp lệ vẫn có thể trả sai thứ tự FIFO. Vì vậy, cần kiểm tra **cả bất biến lẫn kết quả so với đặc tả**.

### Bất biến phải đúng khi nào?

Giả sử `insert` của cây cân bằng tạm thời thay đổi con trỏ, rồi cập nhật chiều cao và quay cây. Giữa hai lệnh, một phần bất biến có thể tạm thời sai. Điều quan trọng là:

1. Trước khi thao tác cập nhật bắt đầu, trạng thái phải hợp lệ.
2. Khi thao tác kết thúc thành công, tất cả bất biến phải được khôi phục.
3. Nếu thao tác báo lỗi theo hợp đồng, trạng thái sau lỗi phải thỏa bất biến và chính sách thay đổi/không thay đổi đã định.

Đặt kiểm tra tại **ranh giới công khai sau thao tác**, khi cấu trúc đã hoàn tất mọi bước cập nhật. Không mặc nhiên đặt kiểm tra toàn bộ ở giữa một thuật toán đang cố ý sử dụng trạng thái trung gian. Với cấu trúc cho phép truy cập đồng thời, ranh giới này còn phải được bảo vệ bằng cơ chế đồng bộ phù hợp; kiểm tra trong một luồng không tự tạo ra tính an toàn luồng.

## 2. Cơ sở lập luận: quy nạp trên chuỗi thao tác

Gọi `I(S)` là bất biến của trạng thái biểu diễn `S`, và `op(S, x)` là thao tác cập nhật với tham số `x`. Muốn biết bất biến giữ được sau *mọi* chuỗi cập nhật hợp lệ, ta cần:

- **Bước cơ sở:** trạng thái khởi tạo `S₀` thỏa `I(S₀)`.
- **Bước quy nạp:** nếu `I(S)` đúng trước khi gọi `op` và tiền điều kiện của phép toán được đáp ứng, thì trạng thái `S'` sau khi thao tác thành công cũng thỏa `I(S')`.
- **Nhánh lỗi:** nếu có lỗi thuộc hợp đồng (chẳng hạn lấy phần tử từ Queue rỗng), trạng thái sau lỗi vẫn thỏa `I`; nếu cam kết không thay đổi trạng thái thì còn phải có `S' = S` về mặt logic.

Viết ngắn gọn bằng ký hiệu Hoare:

\[
\{I \land P_{op}\}\;op\;\{I \land Q_{op}\}
\]

Trong đó `P_op` là tiền điều kiện, `Q_op` là hậu điều kiện. Công thức này mô tả **nhánh kết thúc bình thường**; nếu API có nhánh ngoại lệ, cần xác định riêng hậu điều kiện của nhánh đó. Quy nạp là khung lập luận; `assert` chạy sau mỗi bước chỉ cung cấp bằng chứng từ **những lần chạy đã thử**, không thay cho chứng minh tổng quát.

Ví dụ với mảng động: nếu `size == capacity` trước khi `append`, phải mở rộng dung lượng trước khi ghi. Sau khi thêm, `size' = size + 1` và `size' <= capacity'`. Nếu quên cập nhật `capacity` hoặc tăng `size` hai lần, kiểm tra sau cập nhật sẽ phát hiện ngay thay vì để lỗi lan sang thao tác sau.

## 3. Ví dụ xuyên suốt: Queue vòng sử dụng mảng

Một **Queue** hoạt động theo FIFO (*First In, First Out*): thêm ở cuối và lấy ở đầu. Mảng vòng lưu Queue bằng ba thành phần:

| Biến | Ý nghĩa |
|---|---|
| `buffer` | Mảng có độ dài `C >= 1` |
| `head` | Vị trí vật lý của phần tử logic đầu tiên khi Queue không rỗng |
| `count` | Số phần tử logic đang chứa, từ `0` tới `C` |

Phần tử logic thứ `i` (đếm từ `0`) nằm ở chỉ số vật lý:

\[
\operatorname{index}(i)=(head+i)\bmod C,\qquad 0\le i<count.
\]

Vị trí để thêm khi chưa đầy là `(head + count) mod C`. Khi lấy một phần tử, đầu mới là `(head + 1) mod C` nếu còn phần tử. Ví dụ khi `C = 4`, `head = 2`, `count = 3`:

```text
Vi tri vat ly:     0       1       2       3
buffer:           [C]   [trong]   [A]     [B]
                              ^ head = 2
Queue logic:       A  ->  B  ->  C
```

Các bất biến mà ta **chủ động chọn** cho cách biểu diễn này:

1. `C = len(buffer) >= 1`.
2. `0 <= count <= C` và `0 <= head < C`.
3. Nếu `count == 0` thì quy ước chuẩn hóa `head == 0`.
4. Đúng `count` ô đang hoạt động, tính từ `head` theo vòng tròn, chứa phần tử dữ liệu; mọi ô còn lại được gán dấu `EMPTY` nội bộ để dễ phát hiện dữ liệu sót.
5. Thứ tự logic của Queue bằng `buffer[(head+i) % C]` với `i = 0, ..., count-1`.

Điều kiện 3 và việc dọn ô ở điều kiện 4 **không bắt buộc đối với mọi Queue vòng**; đây là lựa chọn cụ thể giúp cách cài đặt đang xét dễ kiểm tra và không giữ tham chiếu tới giá trị đã xóa. Điều kiện 5 xác định cách trích ra Queue logic, nhưng vẫn cần một mô hình độc lập để khẳng định thứ tự đó đúng theo lịch sử `enqueue` và `dequeue`.

**Lưu ý giá trị `None`:** `None` có thể là phần tử hợp lệ, vì vậy không thể dùng `None` để biểu thị ô trống. Ta dùng một đối tượng đặc biệt làm dấu `EMPTY` và so sánh bằng `is`.

## 4. Biến bất biến thành kiểm tra thực thi

Ví dụ Python dưới đây cho phép bật `check_invariants=True` khi phát triển. Hàm `_assert_invariants` kiểm tra cả phạm vi chỉ số lẫn việc các ô hoạt động và ô trống không lẫn nhau. Mỗi thao tác cập nhật công khai gọi `_verify` sau khi hoàn tất.

```python
from typing import Any

_EMPTY = object()  # Khac moi gia tri thong thuong, ke ca None


class RingQueue:
    def __init__(self, capacity: int = 2,
                 check_invariants: bool = True) -> None:
        if capacity < 1:
            raise ValueError("capacity phai >= 1")
        self._buffer: list[Any] = [_EMPTY] * capacity
        self._head = 0
        self._count = 0
        self._check = check_invariants
        self._verify()  # Buoc co so: sau khoi tao

    def _assert_invariants(self) -> None:
        cap = len(self._buffer)
        assert cap >= 1
        assert 0 <= self._count <= cap
        assert 0 <= self._head < cap
        if self._count == 0:
            assert self._head == 0

        # Moi o phai phu hop voi trang thai dang dung / dang trong.
        for position, value in enumerate(self._buffer):
            offset = (position - self._head) % cap
            is_active = offset < self._count
            if is_active:
                assert value is not _EMPTY
            else:
                assert value is _EMPTY

    def _verify(self) -> None:
        if self._check:
            self._assert_invariants()

    def __len__(self) -> int:
        return self._count

    def is_empty(self) -> bool:
        return self._count == 0

    def as_list(self) -> list[Any]:
        """Anh chup Queue theo thu tu FIFO, dung cho kiem thu."""
        cap = len(self._buffer)
        return [self._buffer[(self._head + i) % cap]
                for i in range(self._count)]

    def _grow(self) -> None:
        old_capacity = len(self._buffer)
        larger = [_EMPTY] * (2 * old_capacity)
        for i in range(self._count):
            larger[i] = self._buffer[(self._head + i) % old_capacity]
        self._buffer = larger
        self._head = 0
        # Chua kiem tra: _grow la mot buoc noi bo cua enqueue.

    def enqueue(self, value: Any) -> None:
        if self._count == len(self._buffer):
            self._grow()
        tail = (self._head + self._count) % len(self._buffer)
        self._buffer[tail] = value
        self._count += 1
        self._verify()  # Hau dieu kien cua thao tac cap nhat

    def dequeue(self) -> Any:
        if self._count == 0:
            raise IndexError("dequeue tu Queue rong")
        value = self._buffer[self._head]
        self._buffer[self._head] = _EMPTY
        self._head = (self._head + 1) % len(self._buffer)
        self._count -= 1
        if self._count == 0:
            self._head = 0
        self._verify()  # Hau dieu kien cua thao tac cap nhat
        return value

    def peek(self) -> Any:
        if self._count == 0:
            raise IndexError("peek tu Queue rong")
        return self._buffer[self._head]
```

`_assert_invariants` cần duyệt `C` ô nên mất `O(C)` thời gian mỗi lần; phần kiểm tra dùng `O(1)` bộ nhớ bổ sung. Trong lúc kiểm thử, chi phí đó giúp phát hiện lỗi đúng tại thao tác gây ra. Khi tắt `check_invariants`, các thao tác đọc và `dequeue` có thời gian `O(1)`, còn `enqueue` có thời gian `O(1)` **khấu hao** do có thể phải sao chép `O(C)` phần tử lúc mở rộng. Vì ví dụ không thu nhỏ mảng, thời gian kiểm tra khi bật vẫn phụ thuộc vào **dung lượng đã cấp phát**, kể cả sau khi xóa gần hết phần tử.

Mã sử dụng `assert` để phát hiện lỗi lập trình. Trong Python, chạy bằng tùy chọn `-O` có thể loại bỏ các lệnh `assert`; vì vậy **không dựa vào chúng để kiểm tra đầu vào người dùng hoặc bảo vệ tính đúng đắn ở môi trường sản xuất**. Kiểm tra đầu vào như `capacity < 1` và lỗi Queue rỗng dùng ngoại lệ thực sự. Trong môi trường nhiều luồng, mã này chưa có đồng bộ và không cam kết an toàn truy cập đồng thời.

### Đối chiếu từng thao tác với bất biến

| Thao tác | Chỗ dễ gây lỗi | Điều kiện cần đúng sau thao tác |
|---|---|---|
| Khởi tạo | Cấp phát mảng rỗng hoặc `head` sai | `C >= 1`, `head = count = 0`, mọi ô trống |
| `enqueue` khi còn chỗ | Tính sai vị trí cuối; quên tăng `count` | Thêm đúng một ô hoạt động; `count' = count + 1` |
| `enqueue` khi đầy | Sao chép sai thứ tự sau khi vòng quay quấn qua cuối mảng | Mảng mới đủ lớn; `head = 0`; thứ tự cũ được giữ nguyên rồi thêm giá trị mới |
| `dequeue` | Quên xóa dấu sử dụng, quên cập nhật `head` hoặc `count` | `count' = count - 1`; đầu mới là phần tử kế tiếp; ô cũ trống |
| `dequeue` phần tử cuối | Để `head` trôi sang vị trí khác dù quy ước cần `0` | `count = 0`, `head = 0`, không còn ô hoạt động |
| `dequeue` trên Queue rỗng | Sửa chỉ số trước khi báo lỗi | Ném `IndexError`, trạng thái không thay đổi |

Việc `_grow` không tự kiểm tra ở giữa cho thấy cách đặt điểm kiểm chứng: ta xem `enqueue` là **một thao tác công khai hoàn chỉnh**, kiểm tra ngay khi nó đã thêm phần tử và khôi phục bất biến. Nếu cần gọi `_grow` trực tiếp hoặc mở rộng cấu trúc cho phép thao tác con được quan sát, phải xác định lại ranh giới kiểm tra.

## 5. Kiểm tra liên tục bằng chuỗi thao tác

Một số lỗi chỉ xuất hiện sau nhiều bước, chẳng hạn `enqueue`, `dequeue` rồi `enqueue` lại để `tail` quay về đầu mảng. Hãy thử một chuỗi cố định:

```python
q = RingQueue(capacity=3, check_invariants=True)
q.enqueue(None)
q.enqueue("B")
q.enqueue("C")
assert q.as_list() == [None, "B", "C"]

assert q.dequeue() is None
q.enqueue("D")  # Ghi vao o dau mang do tail quang vong.
assert q.as_list() == ["B", "C", "D"]

q.enqueue("E")  # Day mang: phai mo rong, giu nguyen thu tu.
assert q.as_list() == ["B", "C", "D", "E"]
assert [q.dequeue() for _ in range(4)] == ["B", "C", "D", "E"]
assert q.is_empty()

try:
    q.dequeue()
except IndexError:
    pass
else:
    raise AssertionError("Queue rong phai bao loi")
assert q.as_list() == []
```

Trong ví dụ này, `_verify` chạy sau từng lần cập nhật. Các lệnh `assert q.as_list()` bổ sung điều bất biến biểu diễn **chưa chứng minh**: Queue vẫn giữ thứ tự FIFO. Nếu người lập trình vô tình đảo chỗ hai phần tử đang hoạt động, bất biến “đúng số ô, đúng chỉ số” có thể vẫn thỏa, nhưng so sánh với thứ tự mong đợi sẽ bắt lỗi.

### Kiểm thử đối chiếu với mô hình độc lập

Đối với kiểm thử rộng hơn, dùng `collections.deque` làm mô hình Queue và so kết quả **sau mỗi thao tác**. Dùng hạt giống cố định để tái hiện lỗi:

```python
from collections import deque
from random import Random

rng = Random(2026)
queue = RingQueue(capacity=2, check_invariants=True)
reference = deque()

for _ in range(2000):
    if rng.random() < 0.6:
        value = rng.choice([None, 0, 1, 2])
        queue.enqueue(value)
        reference.append(value)
    elif reference:
        assert queue.dequeue() == reference.popleft()
    else:
        try:
            queue.dequeue()
        except IndexError:
            pass
        else:
            raise AssertionError("Thieu loi khi Queue rong")

    assert len(queue) == len(reference)
    assert queue.as_list() == list(reference)
```

Đây là **kiểm thử dựa trên mô hình**: `deque` xác định kết quả đúng theo API FIFO; `_assert_invariants` bảo đảm bố cục nội bộ đáp ứng các điều kiện đã chọn. Hai cách bổ sung cho nhau. Có thể áp dụng cách tương tự với `list` cho Stack, `dict` cho Map hoặc một thuật toán đơn giản nhưng chậm hơn làm mô hình cho cấu trúc truy vấn đoạn.

Khi một ca ngẫu nhiên thất bại, cần lưu hạt giống cùng **chuỗi thao tác gây lỗi**, sau đó rút gọn chuỗi tới trường hợp nhỏ nhất vẫn tái hiện được lỗi. Chuỗi `enqueue(A), enqueue(B), dequeue(), enqueue(C)` thường dễ chẩn đoán hơn một lịch sử dài hàng nghìn thao tác.

## 6. Tìm đúng lỗi: vi phạm bất biến hay vi phạm hành vi?

Xét các lỗi giả định sau đây:

**Lỗi A — Quên giảm `count` sau `dequeue`:** chương trình đã đánh dấu ô đầu là `_EMPTY` nhưng không giảm `count`. Kiểm tra phát hiện ngay một ô được coi là đang hoạt động lại mang dấu `_EMPTY`.

**Lỗi B — Sai công thức vị trí cuối:** dùng `(head + count + 1) % C`. Trong nhiều trạng thái, giá trị bị ghi vào ô ngoài vùng hoạt động; kiểm tra đối chiếu “ô hoạt động/ô trống” phát hiện sự không nhất quán.

**Lỗi C — Hoán đổi hai phần tử đang hoạt động:** các chỉ số và số ô vẫn hợp lệ, nên kiểm tra biểu diễn có thể không phát hiện. Kiểm tra `as_list()` so với mô hình sẽ phát hiện sai thứ tự FIFO.

**Lỗi D — Quên kiểm tra Queue rỗng:** phép toán có thể đọc một ô `_EMPTY`, trả một giá trị sai hoặc sửa `head`; cần kiểm thử đường lỗi và yêu cầu trạng thái sau ngoại lệ không đổi.

Từ các tình huống trên rút ra một nguyên tắc quan trọng: **không có một tập `assert` nội bộ nhỏ nào tự chứng minh mọi hành vi đúng**. Hãy đặc tả từng phép toán, kiểm tra bất biến và đối chiếu kết quả qua API công khai.

## 7. Mẫu bất biến cho các cấu trúc dữ liệu khác

Khi xây dựng bộ kiểm tra, hãy bắt đầu bằng bất biến cốt lõi rồi bổ sung bất biến đặc thù của biến thể được cài đặt:

| Cấu trúc | Bất biến nên kiểm tra sau cập nhật | Chi phí kiểm tra đầy đủ thường gặp |
|---|---|---|
| Mảng động | `0 <= size <= capacity`, đoạn hoạt động chứa đúng `size` phần tử | `O(1)` cho kích thước; `O(n)` nếu so toàn bộ nội dung với mô hình |
| Danh sách liên kết đơn | Duyệt từ `head` tới hết đúng `size` nút, không có chu trình ngoài ý muốn | `O(n)` |
| Danh sách liên kết đôi | `node.next.prev == node` và `node.prev.next == node` tại liên kết hợp lệ; đầu/cuối và kích thước nhất quán | `O(n)` |
| Stack / Queue | Số phần tử, đầu/đỉnh, vị trí hoạt động hợp lệ; thứ tự LIFO/FIFO qua mô hình | `O(n)` để so thứ tự toàn bộ |
| Bảng băm | Số mục đang dùng đúng, khóa có thể tìm lại theo quy tắc băm/probing; tombstone được xử lý nhất quán | Thường `O(n)` hoặc hơn, tùy kiểm tra |
| Cây tìm kiếm nhị phân | Mọi khóa bên trái/phải thỏa quy tắc thứ tự **trên toàn cây**; không có chu trình; kích thước nút nhất quán | `O(n)` nếu duyệt hợp lý |
| AVL / cây cân bằng | Ngoài thứ tự BST: chiều cao lưu trong nút đúng, chênh lệch chiều cao hai nhánh không quá 1 | `O(n)` |
| Min-heap dạng mảng | Với mỗi nút `i > 0`, `key[parent(i)] <= key[i]` | `O(n)` |
| Disjoint Set Union | Con trỏ cha tạo thành rừng, gốc trỏ về chính nó; số tập nếu lưu phải chính xác | `O(n)` hoặc hơn để duyệt/kiểm tra |
| Đồ thị vô hướng | Mỗi cạnh `(u, v)` có biểu diễn hai chiều nhất quán nếu dùng danh sách kề đối xứng; không có cạnh/đỉnh ngoài quy ước | `O(V + E)` khi duyệt toàn bộ |

Các giới hạn `O(n)` trong bảng là mức tham khảo cho cách kiểm tra hợp lý và không nhất thiết áp dụng cho mọi biểu diễn. Ví dụ, tìm chu trình trong danh sách liên kết có thể dùng thuật toán rùa–thỏ với `O(1)` bộ nhớ phụ; duyệt tất cả cạnh của đồ thị thường dùng `O(V + E)` thời gian. Với bảng băm có probing, kiểm tra mọi khóa bằng cách tự tìm kiếm lại có thể tốn hơn một lần quét các ô.

### Ví dụ nhanh: kiểm tra heap sau `push`/`pop`

Với min-heap mảng `heap[0:n]`, cha của nút `i` (`i > 0`) ở `(i-1)//2`. Điều kiện heap là:

\[
\forall i\in\{1,\ldots,n-1\},\quad
heap[\lfloor(i-1)/2\rfloor]\le heap[i].
\]

Có thể viết:

```python
def assert_min_heap(heap):
    for i in range(1, len(heap)):
        assert heap[(i - 1) // 2] <= heap[i]
```

Chạy sau `push`, `pop_min`, `decrease_key` giúp bắt lỗi trong thao tác đẩy lên (*sift up*) hoặc đẩy xuống (*sift down*). Nhưng cần kiểm thử riêng rằng `pop_min` trả đúng phần tử nhỏ nhất trước cập nhật, vì một heap hợp lệ sau thao tác chưa đủ chứng minh giá trị trả về đúng.

### Ví dụ nhanh: kiểm tra BST

Không chỉ so khóa với **cha trực tiếp**. Một nút nằm sâu trong nhánh trái của gốc vẫn phải nhỏ hơn gốc theo quy tắc BST. Nếu quy ước **khóa không trùng**, hàm kiểm tra cần truyền khoảng giới hạn từ tổ tiên:

```python
def assert_bst(node, lower=None, upper=None):
    if node is None:
        return
    if lower is not None:
        assert node.key > lower
    if upper is not None:
        assert node.key < upper
    assert_bst(node.left, lower, node.key)
    assert_bst(node.right, node.key, upper)
```

Đoạn mã minh họa chỉ kiểm tra thứ tự khóa trên một cây hữu hạn, không có chu trình, với khóa so sánh được và không dùng `None` làm khóa. Khi cài đặt thực tế, còn cần kiểm tra không chia sẻ nút ngoài dự kiến, con trỏ cha, độ cao hoặc số lượng nút nếu các thông tin đó được lưu; nếu cho phép khóa trùng phải điều chỉnh bất đẳng thức đúng với hợp đồng.

## 8. Khi nào kiểm tra đầy đủ, khi nào kiểm tra cục bộ?

**Trong phát triển và kiểm thử:** bật kiểm tra toàn bộ sau mỗi thao tác. Chi phí lớn hơn, nhưng vị trí phát hiện lỗi gần nơi gây lỗi nhất. Nếu một bộ kiểm tra toàn phần tốn `O(n)` sau từng lần thêm, `n` thao tác có thể tốn tổng cộng `O(n²)` chỉ cho việc kiểm tra; cần chấp nhận và giới hạn quy mô ca thử.

**Trong môi trường chạy thực tế:** chỉ để lại những kiểm tra cần thiết cho hợp đồng hoặc an toàn đầu vào, hoặc dùng kiểm tra rẻ tại các vị trí liên quan. Ví dụ, sau khi thêm vào heap chỉ kiểm tra các liên kết trên đường từ lá mới tới gốc; sau quay AVL kiểm tra lại các nút bị ảnh hưởng. Những kiểm tra cục bộ giúp tìm lỗi sớm nhưng **không đảm bảo** cấu trúc đã đúng ở mọi vùng còn lại.

**Trong thử nghiệm dài hoặc trước phát hành:** chạy kiểm tra toàn bộ định kỳ, kết hợp kiểm thử ngẫu nhiên, kiểm thử thuộc tính (*property-based testing*), so với mô hình tham chiếu và bộ ca biên. Với lỗi hiếm, có thể lưu và tái chạy chuỗi thao tác cụ thể.

Ngoài chi phí, phải cân nhắc khả năng kiểm tra phá vỡ chương trình: một hàm xác minh không nên thay đổi trạng thái đang được xác minh, gọi lại API cập nhật hay vô tình làm thay đổi con trỏ duyệt. Nếu bản thân bộ kiểm tra có lỗi, nó có thể báo sai; hãy viết một vài ca thử cố tình làm hỏng cấu trúc để xác nhận các `assert` bắt được vi phạm mong đợi.

## 9. Bài tập thực hành: tìm lỗi sau từng cập nhật

Một Stack dùng mảng lưu `items`, số phần tử đang dùng `size`, và có `capacity = len(items)`. Lập trình viên viết:

```python
def pop(self):
    if self.size == 0:
        raise IndexError("Stack rong")
    value = self.items[self.size - 1]
    self.items[self.size - 1] = None
    return value
```

Hãy thực hiện ba việc: (1) viết ít nhất hai bất biến; (2) chỉ ra lỗi; (3) mô tả một ca kiểm thử khiến lỗi lộ ra ngay sau một `pop`.

**Gợi ý lời giải:**

- Hai bất biến tối thiểu là `0 <= size <= capacity` và `items[0:size]` biểu diễn đúng các phần tử đang tồn tại trong Stack. Nếu quy ước ô hoạt động không dùng `None` làm dấu trống, có thể kiểm tra thêm tính nhất quán vùng hoạt động; tuy nhiên nếu người dùng được phép `push(None)`, phải sử dụng một sentinel riêng.
- Lỗi nằm ở chỗ quên `self.size -= 1`. Sau khi lấy phần tử đỉnh, `size` vẫn báo số cũ và `peek` có thể trả `None` thay vì phần tử đỉnh mới. Đoạn mã còn phải tuân theo quy ước về dọn ô và sentinel của cài đặt cụ thể.
- Với Stack chứa `['A', 'B']`, sau `pop` phải nhận `'B'`, `size` phải là `1`, và đỉnh mới phải là `'A'`. Đặt kiểm tra ngay sau lần `pop` giúp khoanh vùng lỗi; chỉ kiểm tra `0 <= size <= capacity` sẽ **không** bắt được việc quên giảm `size`, nên cần cả hậu điều kiện và kiểm thử hành vi.

## 10. Checklist khi thêm một thao tác cập nhật mới

Trước khi chấp nhận `insert`, `delete`, `update`, `merge`, `rotate` hoặc `resize`, hãy tự kiểm:

1. **Bất biến đã được viết rõ chưa?** Gồm điều kiện kích thước, con trỏ/chỉ số, tính thứ tự, cấu trúc liên kết và dữ liệu phụ trợ nếu có.
2. **Trạng thái ban đầu có hợp lệ không?** Kiểm tra ngay sau khởi tạo, kể cả trường hợp rỗng.
3. **Kiểm tra nằm tại ranh giới thao tác chưa?** Mọi đường thành công đều khôi phục bất biến; đường lỗi có hậu điều kiện riêng.
4. **Có quên phần không thay đổi không?** Một thao tác cục bộ không được làm hỏng nút, khóa hay phần tử ở vùng không liên quan.
5. **Đã thử các điểm biên chưa?** Rỗng, một phần tử, đầy, tràn dung lượng, khóa trùng, `None` hợp lệ, quấn vòng, quay/cân bằng lại cây.
6. **Đã so kết quả với mô hình chưa?** Bất biến nội bộ không thay thế kiểm tra LIFO, FIFO, tính đúng của tìm kiếm hoặc thứ tự truy vấn.
7. **Chi phí kiểm tra có phù hợp môi trường không?** Kiểm tra toàn bộ sau từng cập nhật trong test; chọn chính sách phù hợp ở nơi có yêu cầu hiệu năng.

Kiểm tra bất biến sau mỗi cập nhật tạo ra một vòng phản hồi ngắn: **thao tác vừa làm gì → cấu trúc hiện còn hợp lệ không → kết quả có đúng hợp đồng không**. Nhờ đó, lỗi được phát hiện gần nguồn gốc, việc sửa chữa ít rủi ro hơn, và những lựa chọn cài đặt khác nhau vẫn có thể được kiểm chứng theo cùng một đặc tả.
