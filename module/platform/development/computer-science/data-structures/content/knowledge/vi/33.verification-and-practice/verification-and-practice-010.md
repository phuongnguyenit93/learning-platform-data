# Thực hành cài đặt cùng một kiểu dữ liệu trừu tượng bằng nhiều cấu trúc

Một **kiểu dữ liệu trừu tượng** (*Abstract Data Type – ADT*) mô tả **những phép toán người dùng có thể thực hiện** và **kết quả phải nhận được**, nhưng không buộc ta phải lưu dữ liệu theo một cách duy nhất. Chẳng hạn, Queue có thể lưu bằng mảng vòng, danh sách liên kết hoặc hai Stack. Các cách biểu diễn này có những bất biến và chi phí vận hành khác nhau, nhưng cùng phải bảo đảm **vào trước, ra trước** (*FIFO*).

Trong chương **Kiểm chứng và thực hành** của học phần cấu trúc dữ liệu, ta sẽ tự cài đặt **một Queue ADT bằng ba cấu trúc** rồi dùng cùng một bộ kiểm thử để xác minh hành vi. Đây là cách thực hành quan trọng trước khi lựa chọn mảng, danh sách liên kết, Stack, Queue, bảng băm, cây, heap hay đồ thị cho một bài toán thực tế: **tách điều cấu trúc phải làm khỏi cách cấu trúc được xây dựng**.

Mục tiêu sau bài học:

- Viết một hợp đồng ADT độc lập với kiểu lưu trữ.
- Cài đặt Queue bằng mảng vòng tự mở rộng, danh sách liên kết đơn và hai Stack.
- Phát biểu bất biến biểu diễn và phép ánh xạ sang trạng thái logic.
- Viết một bộ kiểm thử duy nhất áp dụng cho cả ba bản, đối chiếu với mô hình `deque`.
- So sánh thời gian trường hợp xấu nhất, thời gian khấu hao, cấp phát và bộ nhớ để chọn bản phù hợp.

## 1. Đầu tiên, chốt hợp đồng Queue

Queue được mô hình hóa bằng dãy logic:

\[
Q=[q_0,q_1,\ldots,q_{n-1}],
\]

trong đó \(q_0\) là phần tử **được thêm sớm nhất** còn ở trong Queue.

| Phép toán | Hành vi theo hợp đồng của bài |
|---|---|
| `enqueue(x)` | Thêm `x` vào cuối dãy: \(Q'=Q+[x]\); trả `None` |
| `dequeue()` | Khi \(n>0\), trả \(q_0\) và chuyển thành \(Q'=[q_1,\ldots,q_{n-1}]\) |
| `front()` | Khi \(n>0\), trả \(q_0\) nhưng **không đổi dãy logic** |
| `len(q)` | Trả đúng số phần tử logic |
| `snapshot()` | Trả danh sách theo thứ tự FIFO; chỉ dùng để quan sát và kiểm thử |

Quy ước chung trong bài:

1. Queue mới tạo **rỗng** và có `len(q) == 0`.
2. `dequeue()` và `front()` trên Queue rỗng ném `IndexError` **mà không thay đổi trạng thái logic**.
3. Queue cho phép **phần tử trùng nhau và giá trị `None`**. Vì thế, `None` không được dùng làm dấu báo Queue rỗng.
4. Không có giới hạn dung lượng logic cố định; Queue có thể tăng kích thước cho tới khi gặp giới hạn tài nguyên của môi trường.
5. Không yêu cầu an toàn đồng thời; ba ví dụ dưới đây dành cho truy cập tuần tự, không có cơ chế khóa.

Nếu một Queue từ chối thêm khi đầy còn Queue khác tự mở rộng, chúng **không cùng hợp đồng**. Tương tự, Priority Queue lấy phần tử ưu tiên cao nhất không phải Queue FIFO, dù cả hai đều có thao tác “thêm” và “lấy”.

### Đặc tả trước/sau của hai cập nhật chính

Với trạng thái trước là \(Q\) và giá trị mới \(x\):

\[
\begin{aligned}
&\operatorname{enqueue}(Q,x): &&Q'=Q\mathbin{+\!\!+}[x],\\
&\operatorname{dequeue}([a]+R): &&\text{trả }a,\quad Q'=R.
\end{aligned}
\]

Ký hiệu \(+\!\!+\) là phép nối dãy. Phần tử đầu có thể bằng `None`, nên không thể phát hiện Queue rỗng chỉ bằng cách kiểm tra giá trị lấy ra.

## 2. Ba biểu diễn cho cùng một trạng thái logic

Ta cần một cách chuyển trạng thái lưu trữ nội bộ thành dãy Queue logic; gọi đó là **hàm trừu tượng hóa** (*abstraction function*) \(\alpha\).

| Cách lưu | Biểu diễn nội bộ | Dãy Queue logic |
|---|---|---|
| Mảng vòng | `buffer`, `head`, `size`, `capacity` | Lấy `size` ô liên tiếp theo modulo, bắt đầu ở `head` |
| Danh sách liên kết đơn | `head`, `tail`, `size`, liên kết `next` | Duyệt nút từ `head` đến `tail` |
| Hai Stack | `incoming`, `outgoing` | `reversed(outgoing) + incoming` |

Hình dung cùng Queue `["A", "B", "C"]`:

```text
Queue logic:                 A -> B -> C

Mang vong (cap = 5):
chi so:                    0    1    2    3    4
buffer:                   [C]  [ ]  [ ]  [A]  [B]
head = 3, size = 3      =>  A, B, C

Danh sach lien ket:
head -> [A] -> [B] -> [C] -> None
                       ^tail

Hai Stack (dinh o ben phai):
outgoing = [B, A]     incoming = [C]
Queue logic = reverse([B, A]) + [C] = [A, B, C]
```

Các cách lưu **không giống nhau ở bộ nhớ**, nhưng sau mỗi thao tác, ảnh chụp Queue logic và giá trị trả về phải giống nhau. Đó là tiêu chí tương đương quan sát được (*observational equivalence*).

## 3. Cài đặt 1: Queue bằng mảng vòng tự mở rộng

Mảng vòng phù hợp khi muốn truy cập phần tử liên tiếp trong bộ nhớ mà không phải dịch cả dãy mỗi lần lấy ở đầu. Ba trường quan trọng là:

- `_buffer`: bộ đệm có dung lượng \(C\ge1\).
- `_head`: vị trí vật lý của phần tử logic đầu tiên.
- `_size`: số phần tử đang lưu, \(0\le \_size\le C\).

Phần tử logic thứ \(i\) nằm tại:

\[
\operatorname{index}(i)=(head+i)\bmod C.
\]

Khi thêm cuối, ô mới có chỉ số `(head + size) % C`. Khi đầy, bản này **nhân đôi dung lượng** và chép lại các phần tử theo thứ tự logic.

```python
_EMPTY = object()  # Sentinel noi bo, khac None.


class RingQueue:
    def __init__(self, initial_capacity: int = 2):
        if initial_capacity < 1:
            raise ValueError("initial_capacity phai >= 1")
        self._buffer = [_EMPTY] * initial_capacity
        self._head = 0
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def _grow(self) -> None:
        old = self._buffer
        old_capacity = len(old)
        new = [_EMPTY] * (old_capacity * 2)

        # Sao chep dung thu tu Queue, khong phai thu tu vat ly.
        for i in range(self._size):
            new[i] = old[(self._head + i) % old_capacity]

        self._buffer = new
        self._head = 0

    def enqueue(self, value) -> None:
        if self._size == len(self._buffer):
            self._grow()

        tail = (self._head + self._size) % len(self._buffer)
        self._buffer[tail] = value
        self._size += 1

    def dequeue(self):
        if self._size == 0:
            raise IndexError("Queue rong")

        value = self._buffer[self._head]
        self._buffer[self._head] = _EMPTY  # Bo tham chieu cu.
        self._head = (self._head + 1) % len(self._buffer)
        self._size -= 1

        if self._size == 0:
            self._head = 0

        return value

    def front(self):
        if self._size == 0:
            raise IndexError("Queue rong")
        return self._buffer[self._head]

    def snapshot(self) -> list:
        capacity = len(self._buffer)
        return [
            self._buffer[(self._head + i) % capacity]
            for i in range(self._size)
        ]

    def check_invariants(self) -> None:
        capacity = len(self._buffer)
        assert capacity >= 1
        assert 0 <= self._size <= capacity
        assert 0 <= self._head < capacity
        if self._size == 0:
            assert self._head == 0

        for index, value in enumerate(self._buffer):
            active = (index - self._head) % capacity < self._size
            if active:
                assert value is not _EMPTY
            else:
                assert value is _EMPTY
```

### Vì sao đúng?

Trước thao tác, giả sử dãy trừu tượng là `Q`.

- `enqueue(x)`: vị trí `(head + size) % C` nằm ngay sau phần tử cuối cùng trong dãy logic nếu còn chỗ. Khi đầy, `_grow()` sao chép các phần tử theo thứ tự `Q` và đặt `head = 0` trước khi thêm `x`. Sau cùng, dãy logic là `Q + [x]`.
- `dequeue()`: đọc ô `head`, rồi tăng `head` theo modulo và giảm `size`. Dãy logic mất đúng phần tử đầu. Nếu xóa phần tử cuối, đặt `head = 0` theo quy ước trạng thái rỗng.
- `front()`: trả ô `head`, không cập nhật số phần tử hay vị trí.
- Ô vừa xóa được gán `_EMPTY` để không giữ tham chiếu tới đối tượng đã rời Queue.

`_EMPTY` chỉ dành cho nội bộ; với dữ liệu người dùng thông thường, `None` vẫn là giá trị hợp lệ. Kiểm tra `check_invariants()` có chi phí `O(C)`, nên chỉ gọi trong kiểm thử hoặc các điểm chẩn đoán, không cộng nó vào độ phức tạp thao tác sản xuất.

### Chi phí

- `enqueue`: `O(1)` **khấu hao**, nhưng một lần phải mở rộng có thể `O(n)` vì chép toàn bộ phần tử hiện có.
- `dequeue`, `front`, `len`: `O(1)` trong trường hợp xấu nhất theo mô hình thao tác cơ bản.
- Bộ nhớ: `O(C)` cho bộ đệm, với `C` là dung lượng đã cấp phát. Vì ví dụ **không thu nhỏ sau khi xóa**, dung lượng có thể lớn hơn nhiều số phần tử hiện tại; có thể xem là `O(h)` theo kích thước lớn nhất từng đạt tới trong vòng đời Queue.

Đánh đổi chính là tính cục bộ tốt và ít đối tượng nút riêng, đổi lại có các lần cấp phát lại và sao chép toàn bộ khi đầy.

## 4. Cài đặt 2: Queue bằng danh sách liên kết đơn

Danh sách liên kết đơn lưu mỗi giá trị trong một nút, các nút nối bằng `next`. Muốn thêm cuối với `O(1)`, ta cần giữ cả `head` và `tail`.

Bất biến:

1. Khi `_size == 0`, cả `_head` và `_tail` đều là `None`.
2. Khi `_size > 0`, duyệt từ `_head` bằng `next` phải gặp đúng `_size` nút, không có chu trình.
3. Nút cuối cùng phải là `_tail`, và `_tail.next is None`.

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

    def __len__(self) -> int:
        return self._size

    def enqueue(self, value) -> None:
        node = _Node(value)

        if self._tail is None:
            # Queue dang rong: node vua la dau vua la cuoi.
            self._head = node
        else:
            self._tail.next = node

        self._tail = node
        self._size += 1

    def dequeue(self):
        if self._head is None:
            raise IndexError("Queue rong")

        old_head = self._head
        value = old_head.value
        self._head = old_head.next
        self._size -= 1

        if self._head is None:
            # Vua xoa nut duy nhat.
            self._tail = None

        old_head.next = None  # Cat lien ket nut cu.
        return value

    def front(self):
        if self._head is None:
            raise IndexError("Queue rong")
        return self._head.value

    def snapshot(self) -> list:
        result = []
        node = self._head
        while node is not None:
            result.append(node.value)
            node = node.next
        return result

    def check_invariants(self) -> None:
        if self._size == 0:
            assert self._head is None
            assert self._tail is None
            return

        assert self._head is not None
        assert self._tail is not None

        seen = set()
        count = 0
        node = self._head
        last = None

        while node is not None:
            identity = id(node)
            assert identity not in seen  # Khong co chu trinh.
            seen.add(identity)
            last = node
            node = node.next
            count += 1

        assert count == self._size
        assert last is self._tail
        assert self._tail.next is None
```

### Vì sao đúng?

- `enqueue(x)`: nếu rỗng, nút mới là cả đầu và đuôi; nếu không, nối nút mới vào sau `tail` rồi cập nhật `tail`. Dãy logic mới bằng dãy cũ nối `x`.
- `dequeue()`: thay đầu bằng nút tiếp theo, trả giá trị nút cũ. Nếu chỉ có một nút, phải cập nhật **cả** `head = tail = None`; nếu quên `tail`, lần thêm tiếp theo có thể nối vào một nút đã bị loại khỏi Queue.
- `front()` chỉ xem giá trị đầu, không thay liên kết.

Danh sách liên kết cấp phát một nút cho mỗi lần thêm, và nút được loại bỏ khi lấy đầu; việc thu hồi bộ nhớ thực tế tùy runtime và các tham chiếu còn tồn tại. Bài dùng Python nên mỗi nút còn có overhead của đối tượng và tham chiếu; không thể kết luận số byte chỉ từ `size`.

### Chi phí

- `enqueue`, `dequeue`, `front`, `len`: `O(1)` theo mô hình cấp phát và cập nhật con trỏ cơ bản.
- Duyệt hoặc `snapshot()`: `O(n)` thời gian.
- Bộ nhớ nút đang thuộc Queue: `O(n)` theo số phần tử hiện tại, cộng overhead của bộ cấp phát và đối tượng trong ngôn ngữ cụ thể.

Lợi thế là không cần sao chép toàn bộ dữ liệu lúc Queue lớn lên. Đánh đổi là thêm đối tượng nút và liên kết, có thể làm giảm tính cục bộ bộ nhớ so với mảng.

## 5. Cài đặt 3: Queue bằng hai Stack

Đây là một ví dụ thú vị: dùng hai cấu trúc **LIFO** để tạo ra một ADT **FIFO**.

- `incoming`: các giá trị mới được `push` vào cuối.
- `outgoing`: các giá trị chuẩn bị lấy ra; **đỉnh** (`outgoing[-1]`) là phần tử cũ nhất chưa lấy.
- Khi `outgoing` rỗng, chuyển toàn bộ giá trị từ `incoming` sang `outgoing` bằng các phép `pop`/`append`. Việc chuyển **đảo thứ tự**, đặt phần tử cũ nhất lên đỉnh `outgoing`.

Dãy Queue logic là:

\[
\alpha(incoming,outgoing)=
\operatorname{reverse}(outgoing)\mathbin{+\!\!+}incoming.
\]

```python
class TwoStacksQueue:
    def __init__(self):
        self._incoming = []
        self._outgoing = []

    def __len__(self) -> int:
        return len(self._incoming) + len(self._outgoing)

    def _transfer_if_needed(self) -> None:
        if not self._outgoing:
            while self._incoming:
                self._outgoing.append(self._incoming.pop())

    def enqueue(self, value) -> None:
        self._incoming.append(value)

    def dequeue(self):
        if len(self) == 0:
            raise IndexError("Queue rong")

        self._transfer_if_needed()
        return self._outgoing.pop()

    def front(self):
        if len(self) == 0:
            raise IndexError("Queue rong")

        self._transfer_if_needed()
        return self._outgoing[-1]

    def snapshot(self) -> list:
        return list(reversed(self._outgoing)) + list(self._incoming)

    def check_invariants(self) -> None:
        # Hai list la hai Stack; moi phan tu thuoc dung mot Stack.
        logical = self.snapshot()
        assert len(logical) == len(self)
```

### Theo dõi trạng thái từng bước

```text
enqueue(A):  incoming = [A]      outgoing = []
enqueue(B):  incoming = [A, B]   outgoing = []

dequeue():   chuyen het incoming sang outgoing:
              incoming = []      outgoing = [B, A]
             lay A tu dinh outgoing:
              incoming = []      outgoing = [B]

enqueue(C):  incoming = [C]     outgoing = [B]
Queue logic = reverse([B]) + [C] = [B, C]
```

**Điểm dễ nhầm:** `front()` về mặt hợp đồng chỉ đọc Queue logic, nhưng có thể **thay đổi cách biểu diễn nội bộ** bằng việc chuyển giá trị giữa hai Stack. Đây không phải lỗi nếu `snapshot()` và mọi quan sát công khai khác vẫn thể hiện cùng dãy FIFO.

### Vì sao chuyển mỗi phần tử không quá một lần?

Một phần tử được thêm vào `incoming` đúng một lần. Nếu được lấy ra, nó sẽ chuyển từ `incoming` sang `outgoing` **tối đa một lần**, rồi được lấy khỏi `outgoing` đúng một lần. Một lần chuyển có thể mất `O(n)` khi `outgoing` vừa hết, nhưng trên một chuỗi `m` thao tác, tổng số phần tử được chuyển không vượt quá số phần tử đã thêm.

Do đó, tính theo phân tích khấu hao:

- `enqueue`: `O(1)` **khấu hao** vì `list.append` có thể cấp phát lại.
- `dequeue`, `front`: `O(1)` **khấu hao** trên chuỗi thao tác, nhưng **một lần** có thể mất `O(n)` để chuyển các phần tử.
- `len`: `O(1)`.
- `snapshot`: `O(n)` thời gian và cần danh sách mới dài `n`.
- Bộ nhớ lưu phần tử của hai Stack là `O(n)` theo số phần tử logic; các `list` động có thể còn giữ dung lượng dự phòng sau khi xóa và có cấp phát tạm thời khi chuyển phần tử.

Nếu hệ thống cần giới hạn nghiêm ngặt cho **độ trễ trường hợp xấu nhất** của từng `dequeue`, phân tích khấu hao chưa phải bảo đảm cần thiết. Đây là một lý do để cân nhắc mảng vòng hoặc danh sách liên kết.

## 6. Viết một bộ kiểm thử chung cho ba bản

Ba lớp có cùng giao diện, nên **không cần viết ba bộ kiểm thử riêng biệt**. Ta dùng `collections.deque` làm mô hình Queue FIFO độc lập, vì nó không cần biết mảng vòng, con trỏ nút hay hai Stack hoạt động như thế nào.

Ta kiểm tra:

1. Giá trị trả về hoặc loại lỗi cho mỗi thao tác.
2. Kích thước và dãy logic sau **từng thao tác**.
3. Bất biến biểu diễn của từng cài đặt.
4. Trạng thái không đổi theo hợp đồng khi `front()` đọc và khi `dequeue()`/`front()` báo rỗng.

### 6.1. Bộ chạy lại một chuỗi thao tác

```python
from collections import deque


def invoke_queue(queue, operation, value):
    try:
        if operation == "enqueue":
            return ("ok", queue.enqueue(value))
        if operation == "dequeue":
            return ("ok", queue.dequeue())
        if operation == "front":
            return ("ok", queue.front())
        raise ValueError("Thao tac khong ho tro")
    except IndexError:
        return ("empty", None)


def invoke_model(model, operation, value):
    try:
        if operation == "enqueue":
            return ("ok", model.append(value))
        if operation == "dequeue":
            return ("ok", model.popleft())
        if operation == "front":
            return ("ok", model[0])
        raise ValueError("Thao tac khong ho tro")
    except IndexError:
        return ("empty", None)


def run_trace(queue_class, operations):
    tested = queue_class()
    reference = deque()

    tested.check_invariants()
    assert tested.snapshot() == []

    for step, (operation, value) in enumerate(operations, start=1):
        before_tested = tested.snapshot()
        before_reference = list(reference)

        expected = invoke_model(reference, operation, value)
        actual = invoke_queue(tested, operation, value)

        assert actual == expected, (
            step, operation, value, expected, actual
        )

        tested.check_invariants()
        assert len(tested) == len(reference)
        assert tested.snapshot() == list(reference), (
            step, operation, value,
            tested.snapshot(), list(reference)
        )

        # front va cac duong loi khong doi day logic.
        if operation == "front" or expected[0] == "empty":
            assert tested.snapshot() == before_tested
            assert list(reference) == before_reference
```

Với `TwoStacksQueue`, phép `front()` có thể chuyển phần tử giữa hai mảng nội bộ, nhưng `snapshot()` trước và sau vẫn giống nhau. Bởi vậy, kiểm thử so **trạng thái logic**, không yêu cầu các trường riêng của từng cài đặt bất biến về mặt vật lý.

### 6.2. Bộ ca biên cố định

```python
fixed_trace = [
    ("front", None),       # Doc Queue rong
    ("dequeue", None),     # Lay Queue rong
    ("enqueue", None),     # None la du lieu hop le
    ("front", None),
    ("dequeue", None),     # Chuyen ve Queue rong
    ("enqueue", "A"),
    ("enqueue", "B"),
    ("enqueue", "B"),      # Gia tri trung
    ("dequeue", None),
    ("enqueue", "C"),      # Queue vong co the quan vong
    ("front", None),
    ("dequeue", None),
    ("dequeue", None),
    ("dequeue", None),
    ("dequeue", None),     # Rong lai
]

for implementation in (RingQueue, LinkedQueue, TwoStacksQueue):
    run_trace(implementation, fixed_trace)
```

Chuỗi này kiểm tra rỗng, một phần tử, `None`, phần tử trùng, lấy tới rỗng và thêm lại. Mảng vòng mặc định dung lượng `2` nên cũng trải qua việc tăng dung lượng; dữ liệu sau xóa được thêm trở lại tạo tình huống thay đổi vị trí đầu.

### 6.3. Sinh ngẫu nhiên chuỗi cập nhật

Để tìm các trạng thái khó dự đoán, sinh ngẫu nhiên `enqueue`, `dequeue`, `front` với seed cố định. Ta cố tình cho phép cả lời gọi trên Queue rỗng, vì chúng có **hành vi lỗi đã đặc tả**.

```python
from random import Random


def random_trace(seed=2026, steps=3000):
    rng = Random(seed)
    actions = []

    for _ in range(steps):
        p = rng.random()
        if p < 0.55:
            actions.append((
                "enqueue",
                rng.choice([None, -1, 0, 0, 1, "A", "A"])
            ))
        elif p < 0.85:
            actions.append(("dequeue", None))
        else:
            actions.append(("front", None))

    return actions


operations = random_trace()
for implementation in (RingQueue, LinkedQueue, TwoStacksQueue):
    run_trace(implementation, operations)
```

Cùng một `operations` được chạy lại **từ trạng thái mới** trên mỗi bản. Khi kiểm thử thất bại, nên lưu seed, chuỗi thao tác và bước sai đầu tiên; sau đó thử xóa bớt thao tác để rút gọn phản ví dụ.

`check_invariants` dùng `assert` phục vụ phát hiện lỗi trong môi trường kiểm thử. Python có thể bỏ qua `assert` khi chạy với tùy chọn `-O`; không sử dụng chúng thay cho xử lý lỗi trong ứng dụng sản xuất.

## 7. Lập luận đúng đắn bằng bất biến và phép ánh xạ

Các kiểm thử hữu ích nhưng không phải chứng minh rằng cấu trúc đúng với **mọi chuỗi**. Ta còn cần lý giải bất biến từ khởi tạo qua từng cập nhật.

| Cấu trúc | Trạng thái ban đầu | Khi `enqueue(x)` | Khi `dequeue()` |
|---|---|---|---|
| Mảng vòng | `size = 0`, `head = 0`, buffer trống | Ghi vào ô cuối logic; mở rộng trước nếu đầy | Đọc ô đầu, dọn ô, tăng `head` và giảm `size` |
| Liên kết đơn | `head = tail = None`, `size = 0` | Nối nút vào sau `tail`; xử lý riêng Queue rỗng | Bỏ nút đầu, cập nhật `head`; xóa `tail` nếu hết nút |
| Hai Stack | Cả hai Stack rỗng | `incoming.append(x)` | Nếu cần, đảo `incoming` sang `outgoing`; lấy đỉnh `outgoing` |

Với từng hàng, ta cần chứng minh:

1. **Khởi tạo đúng:** hàm trừu tượng hóa trả dãy `[]`.
2. **Bước thêm đúng:** từ dãy \(Q\) trở thành \(Q+[x]\).
3. **Bước lấy đúng:** từ dãy \([a]+R\) trả `a`, còn lại `R`.
4. **Bước đọc đúng:** `front()` trả `a` mà dãy logic không đổi.
5. **Nhánh lỗi đúng:** khi rỗng, phép lấy/đọc báo `IndexError` trước khi biến đổi trạng thái logic.

Nếu các điều kiện này được duy trì cho mọi lời gọi hợp lệ, có thể dùng quy nạp trên số thao tác để lập luận ba cài đặt cho cùng kết quả quan sát được. `snapshot()` là cách kiểm tra ánh xạ trong bài thực hành; trong hệ thống thật, không nhất thiết phải công khai API cho phép xem tất cả phần tử.

## 8. So sánh thời gian và bộ nhớ theo cùng workload

Một bảng tổng hợp, với \(n\) là số phần tử logic ngay trước thao tác:

| Thuộc tính | Mảng vòng tự mở rộng | Danh sách liên kết đơn | Hai Stack |
|---|---|---|---|
| `enqueue` | `O(1)` khấu hao; lần mở rộng `O(n)` | `O(1)` theo mô hình nút/con trỏ | `O(1)` khấu hao |
| `dequeue` | `O(1)` trường hợp xấu nhất | `O(1)` | `O(1)` khấu hao; một lần chuyển `O(n)` |
| `front` | `O(1)` | `O(1)` | `O(1)` khấu hao; có thể chuyển `O(n)` |
| Duyệt theo FIFO | `O(n)` | `O(n)` | `O(n)` |
| Cấp phát khi thêm | Đôi khi tạo bộ đệm lớn hơn | Mỗi lần tạo nút mới | Mảng động bên trong Stack có thể mở rộng |
| Tính cục bộ bộ nhớ | Các ô tham chiếu liên tiếp | Các nút có thể rải rác | Các ô của từng Stack liên tiếp |
| Bộ nhớ | `O(C)`, có thể giữ dung lượng lịch sử | `O(n)` nút đang sống | `O(n)` phần tử logic, thêm dung lượng dự phòng của các Stack |

Bảng mô tả chi phí cấu trúc trong mô hình thao tác cơ bản, không phải khẳng định về thời gian thực của mọi runtime. Đặc biệt, cấp phát nút của danh sách liên kết có thể kích hoạt bộ cấp phát/GC, còn các thao tác `append` của Python `list` có thể cấp phát lại. Cả ba bản đều có overhead của đối tượng Python và các trình kiểm tra trong mã mẫu.

### Chọn bản nào?

**Mảng vòng:** hợp với Queue lớn, nhiều thao tác hai đầu và cần tính cục bộ tốt; phải chấp nhận lần mở rộng đắt và dung lượng có thể dư sau khi xóa nhiều.

**Danh sách liên kết:** không cần sao chép toàn bộ khi mở rộng, cập nhật đầu/đuôi đơn giản; nhưng có overhead một nút và liên kết cho mỗi phần tử, thường kém tính cục bộ hơn.

**Hai Stack:** tận dụng được thư viện Stack có sẵn, giải thích tốt kỹ thuật khấu hao; nhưng `dequeue`/`front` có thể thỉnh thoảng tốn `O(n)` do chuyển cả dãy.

Không có lựa chọn “tốt nhất” cho mọi ứng dụng. Nếu cần giới hạn độ trễ mỗi `dequeue`, kết luận có thể khác ứng dụng chỉ cần thông lượng trung bình cao. Nếu phải hỗ trợ truy cập chỉ số hoặc xóa phần tử giữa, bản hợp đồng Queue hiện tại chưa có các phép toán đó và cần cân nhắc ADT khác.

## 9. Benchmark công bằng: đo cùng chuỗi thao tác hợp lệ

Đo hiệu năng chỉ có ý nghĩa **sau khi cả ba bản đều vượt qua bộ kiểm thử tính đúng**. Ta tạo một chuỗi thao tác không lấy Queue rỗng, giữ tỷ lệ thêm/lấy cố định và sinh dữ liệu **trước** vùng định thời.

```python
from statistics import median
from time import perf_counter_ns


def valid_workload(seed=42, steps=20_000):
    rng = Random(seed)
    actions = []
    pending = 0

    for _ in range(steps):
        if pending == 0 or rng.random() < 0.55:
            actions.append(("enqueue", rng.randrange(1000)))
            pending += 1
        else:
            actions.append(("dequeue", None))
            pending -= 1

    return actions


def benchmark(queue_class, actions, repetitions=5):
    samples = []

    for _ in range(repetitions):
        q = queue_class()  # Khong tinh khoi tao.
        checksum = 0

        start = perf_counter_ns()
        for operation, value in actions:
            if operation == "enqueue":
                q.enqueue(value)
            else:
                checksum += q.dequeue()
        elapsed_ns = perf_counter_ns() - start

        # Kiem tra sau khi dung dong ho.
        q.check_invariants()
        samples.append((elapsed_ns / len(actions), checksum, q.snapshot()))

    # Cung mot chuoi phai cho cung checksum va trang thai logic.
    first_checksum = samples[0][1]
    first_state = samples[0][2]
    assert all(
        checksum == first_checksum and state == first_state
        for _, checksum, state in samples
    )

    return median(sample[0] for sample in samples)


actions = valid_workload()
for implementation in (RingQueue, LinkedQueue, TwoStacksQueue):
    print(implementation.__name__, benchmark(implementation, actions))
```

Kết quả là **trung vị của thời gian trung bình trên một thao tác trong từng lượt**, không phải p50 độ trễ của từng lời gọi. Vùng định thời còn có chi phí vòng lặp, kiểm tra nhánh và cộng `checksum`, nên không nên gọi đây là “thời gian thuần của enqueue/dequeue”. Các bản thực hiện cùng workload nên phép đo vẫn hữu ích để tham khảo, nếu đọc đúng giới hạn.

Ví dụ này không đưa số đo dựng sẵn: kết quả phải chạy trên môi trường thực tế. Khi đo nghiêm túc, cần warmup thích hợp, nhiều lượt độc lập, đảo thứ tự chạy các phương án, đo bộ nhớ riêng và sử dụng nhiều kích thước dữ liệu. Benchmark trên chỉ là khuôn mẫu tối giản.

`check_invariants` và `snapshot` gọi ngoài đồng hồ. Hai hàm có thể duyệt toàn bộ Queue nên không được vô tình đưa vào vùng định thời nếu mục tiêu là đo chi phí phép toán công khai.

## 10. Những lỗi thường gặp khi cài cùng ADT bằng nhiều cấu trúc

### Lỗi A: khác nhau về hành vi rỗng

Một bản `dequeue` trả `None` khi rỗng, bản khác ném `IndexError`. Nếu `None` cũng là dữ liệu hợp lệ, hai bản không có cùng hợp đồng. Hãy thống nhất lỗi trước khi viết kiểm thử.

### Lỗi B: Queue vòng tính `tail` sai

Sai:

```python
tail = size % capacity
```

Đúng:

```python
tail = (head + size) % capacity
```

Dòng sai chỉ tình cờ đúng khi `head == 0`. Sau một chuỗi `enqueue`, `dequeue`, `enqueue`, `head` có thể dịch sang vị trí khác và gây ghi đè phần tử còn tồn tại.

### Lỗi C: danh sách liên kết quên cập nhật `tail`

Khi xóa nút duy nhất, nếu chỉ đặt `head = None` mà để `tail` trỏ vào nút cũ, lần `enqueue` sau có thể tạo một nút không còn nối được từ `head`. Bất biến `head`/`tail` phải được kiểm tra ngay sau phép xóa.

### Lỗi D: hai Stack chuyển dữ liệu quá thường xuyên

Nếu chuyển toàn bộ `incoming` sang `outgoing` mỗi lần `front` hoặc `dequeue`, thay vì chỉ chuyển **khi `outgoing` rỗng**, thuật toán có thể bị sai thứ tự FIFO và mất bảo đảm chi phí khấu hao như dự kiến.

### Lỗi E: so trạng thái vật lý thay vì logic

Mảng vòng và hai Stack có thể lưu phần tử khác thứ tự trong bộ nhớ mà vẫn đúng Queue FIFO. Kiểm thử phải so `snapshot()` hoặc kết quả lấy ra theo hợp đồng, không so trực tiếp `_buffer`, `_incoming` hay các nút của danh sách.

## 11. Thực hành nâng cao: đổi ADT nhưng giữ phương pháp

Phương pháp “một hợp đồng, nhiều cấu trúc, một bộ kiểm thử” có thể áp dụng rộng hơn:

| ADT | Một vài cách cài đặt | Lưu ý đặc tả |
|---|---|---|
| Stack | Mảng động, danh sách liên kết | LIFO, lỗi khi rỗng, số phần tử |
| Set | Bảng băm, BST cân bằng, mảng sắp xếp | Không trùng giá trị logic; thứ tự duyệt có được cam kết không? |
| Map | HashMap, cây tìm kiếm, danh sách cặp khóa–giá trị | Ghi đè khóa, giá trị `None`, cách kiểm tra bằng nhau |
| Priority Queue | Heap, mảng sắp xếp, danh sách thường | Quy tắc chọn ưu tiên và hòa khi ưu tiên bằng nhau |
| Disjoint Set | Mảng nhãn thành phần, rừng Union-Find | Hai phần tử có liên thông hay không sau `union` |
| Tập động có truy vấn hạng | Cây cân bằng có `subtree_size`, mảng sắp xếp | Chính sách khóa trùng, định nghĩa `rank/select` |
| Cấu trúc tổng đoạn | Mảng thường, Fenwick Tree, Segment Tree | Cập nhật điểm, quy ước đoạn `[l, r)`, chỉ số hợp lệ |

Ví dụ, một `Map` dùng HashMap và một `Map` dùng cây có thể cùng hỗ trợ `put/get/remove` nhưng khác khả năng duyệt theo khóa tăng dần. Nếu ADT cam kết truy vấn khoảng, HashMap đơn thuần không cung cấp ngay hiệu quả như cây có thứ tự; nếu ADT không cam kết thứ tự duyệt, không được coi thứ tự khác nhau là lỗi.

### Bài tập tự làm: Queue với ba cách cài đặt

1. Thêm phương thức `is_empty()` vào ba lớp, bảo đảm kết quả luôn bằng `len(q) == 0`.
2. Bổ sung ca kiểm thử hai Stack khi `outgoing` còn một phần tử, sau đó thêm các giá trị vào `incoming` rồi lấy liên tục tới rỗng.
3. Với `RingQueue(initial_capacity=1)`, theo dõi các dung lượng `1 → 2 → 4 → 8` và kiểm tra sau mỗi lần tăng dung lượng không làm thay đổi thứ tự FIFO.
4. Với `LinkedQueue`, kiểm tra chu trình `enqueue(None) → dequeue() → enqueue("X") → front()` và xác minh `head/tail` đúng ở trạng thái rỗng.
5. Đưa một lỗi cố ý vào `_grow`, `_tail` hoặc `_transfer_if_needed`; dùng bộ chạy lại với seed cố định để tìm chuỗi thao tác nhỏ nhất phát hiện sai lệch.
6. Bổ sung phép đo bộ nhớ: số nút đang sống trong LinkedQueue, dung lượng bộ đệm vòng và dung lượng dự phòng của hai Stack. Nêu rõ đây là các chỉ số khác nhau và không được tự suy ra RSS.

**Gợi ý lời giải bài 2:** nếu `outgoing` chưa rỗng thì phần tử mới của `incoming` phải chờ tới sau những phần tử cũ còn trong `outgoing`; chỉ chuyển `incoming` khi `outgoing` trở thành rỗng. Dãy logic luôn là `reversed(outgoing) + incoming`.

**Gợi ý lời giải bài 3:** trước và sau `_grow`, lấy ảnh chụp Queue logic phải cho cùng một dãy. Một bản sao chép theo **thứ tự vật lý** của bộ đệm vòng có thể làm sai Queue khi `head != 0`.

## 12. Checklist hoàn thành một bài cài đặt ADT đa biểu diễn

- Đã chốt giao diện công khai, giá trị trả về, lỗi và chính sách trùng lặp giống nhau?
- Mỗi bản có hàm ánh xạ từ biểu diễn nội bộ sang cùng trạng thái logic?
- Bất biến được kiểm tra sau khởi tạo, thêm, lấy và các nhánh biên?
- Có kiểm thử rỗng, một phần tử, `None`, giá trị trùng, mở rộng dung lượng và chuỗi thao tác dài?
- Có một **mô hình độc lập** và cùng bộ thao tác chạy lại từ trạng thái mới trên mọi bản?
- Có phân biệt thay đổi **biểu diễn vật lý** với thay đổi **hành vi quan sát được**?
- Đã phân tích đúng `O(1)` trường hợp xấu nhất và `O(1)` khấu hao, tránh đánh đồng hai loại?
- Đã so cả thời gian, cấp phát, bộ nhớ và chi phí bảo trì trong workload thực tế?
- Các phép đo hiệu năng có loại phần kiểm tra toàn bộ khỏi vùng định thời và xác minh kết quả sau lượt đo?
- Đã mô tả khi nào nên dùng từng cách cài đặt thay vì tuyên bố một bản tốt nhất cho mọi trường hợp?

Bản chất của ADT là **một hợp đồng có thể được hiện thực bằng nhiều cấu trúc dữ liệu**. Khi cài Queue bằng mảng vòng, danh sách liên kết và hai Stack, ta không chỉ rèn kỹ năng lập trình mà còn học cách chứng minh bất biến, dùng bộ kiểm thử chung và chọn biểu diễn dựa trên đánh đổi về thời gian, bộ nhớ và tải thao tác.
