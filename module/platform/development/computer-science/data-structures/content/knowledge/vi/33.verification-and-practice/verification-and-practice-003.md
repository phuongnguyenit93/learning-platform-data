# Ca rỗng, một phần tử, khóa trùng, biên chỉ số và đầy dung lượng

Một cấu trúc dữ liệu có thể chạy đúng với một trăm phần tử nhưng sai ngay khi không có phần tử nào, khi xóa phần tử cuối cùng hoặc khi thêm đúng phần tử làm đầy bộ đệm. Những trường hợp đó là **ca biên** (*boundary cases*). Chúng kiểm tra các điểm mà điều kiện trong thuật toán đổi nhánh: `size == 0`, `size == 1`, `index == size - 1`, `size == capacity`, hoặc khóa được thêm đã tồn tại.

Trong học phần **Kiểm chứng và thực hành** của cấu trúc dữ liệu, ta cần biến các ca biên thành kiểm thử có **kết quả mong đợi rõ ràng**. Một bài kiểm thử tốt kiểm tra cả giá trị trả về, lỗi phát sinh, trạng thái sau thao tác và những bất biến phải giữ. Cách làm áp dụng cho mảng, danh sách liên kết, Stack, Queue, Set, Map, bảng băm, cây, heap và đồ thị.

## 1. Bắt đầu bằng hợp đồng, rồi mới chọn dữ liệu kiểm thử

Đừng viết kiểm thử chỉ từ cách cài đặt hiện tại. Trước tiên, xác định hợp đồng công khai của phép toán:

| Câu hỏi | Ví dụ cần quyết định |
|---|---|
| Trạng thái nào là hợp lệ? | Queue có thể rỗng hay bắt buộc có ít nhất một phần tử? |
| Phép toán nào được gọi khi rỗng? | `peek()` ném lỗi, trả kiểu `Option`, hay trả mã lỗi? |
| Chỉ số hợp lệ là gì? | `get(i)` nhận `0 <= i < size`; `insert(i, x)` có nhận `i == size` không? |
| Phần tử/khóa trùng được xử lý ra sao? | `Set.add(x)` bỏ qua phần tử có sẵn; `Map.put(k, v)` ghi đè giá trị cũ? |
| Đầy dung lượng nghĩa là gì? | Bộ đệm cố định từ chối thêm; mảng động tự mở rộng? |
| Khi thất bại, trạng thái có thay đổi không? | `enqueue` khi đầy ném lỗi và phải giữ nguyên Queue? |
| Chi phí được cam kết ở trường hợp nào? | `append` của mảng động là `O(1)` khấu hao, không phải `O(1)` mỗi lần |

Với một phép toán, có thể mô tả một ca kiểm thử dưới dạng:

```text
Given: trạng thái trước và tham số
When:  phép toán được gọi
Then:  giá trị / ngoại lệ mong đợi
And:   trạng thái sau và bất biến mong đợi
```

Chẳng hạn, `Stack.pop()` với `S = ["A"]` phải trả `"A"` và để lại `S' = []`; với `S = []` phải xử lý rỗng theo đúng hợp đồng. Bài kiểm thử chỉ xác nhận giá trị trả về `"A"` mà không xác nhận Stack đã rỗng vẫn chưa đầy đủ.

## 2. Ca rỗng: trạng thái hợp lệ nhưng nhiều phép toán không khả dụng

Trạng thái rỗng thường là điểm khởi đầu của cấu trúc, đồng thời là trạng thái sau khi xóa phần tử cuối. Nó đặc biệt dễ gây lỗi vì không có phần tử đầu/đuôi, không có khóa nhỏ nhất và không có chỉ số dữ liệu hợp lệ.

| Cấu trúc | Phép toán trên cấu trúc rỗng | Kết quả theo hợp đồng được chọn |
|---|---|---|
| Mảng / danh sách | `length`, `is_empty` | Trả `0` và `True` |
| Mảng / danh sách | `get(0)`, `remove(0)` | Báo chỉ số không hợp lệ, giữ nguyên trạng thái |
| Stack | `push(x)` | Thành Stack một phần tử |
| Stack | `pop()`, `peek()` | Báo rỗng, không làm biến đổi Stack |
| Queue | `enqueue(x)` | Thành Queue một phần tử |
| Queue | `dequeue()`, `front()` | Báo rỗng, không làm biến đổi Queue |
| Map | `get(k)` với khóa vắng mặt | Trả `Option.none` hoặc báo lỗi tùy API; không nhập nhằng với giá trị `None` hợp lệ |
| Min-heap | `extract_min()` | Báo rỗng, không có giá trị nhỏ nhất |
| Đồ thị | `neighbors(v)` khi `v` chưa tồn tại | Trả rỗng hay báo lỗi phải được đặc tả rõ; hai cách không tương đương |

**Điểm quan trọng:** bảng trên thể hiện những hợp đồng thường được lựa chọn, không phải quy tắc bất biến của mọi thư viện. API có thể cung cấp song song `pop()` ném lỗi và `try_pop()` trả `Option`. Kiểm thử phải dựa vào chính sách đã công bố.

### Vì sao không nên mặc nhiên dùng `None` để báo rỗng?

Giả sử Stack cho phép `push(None)`. Khi `pop()` trả `None`, người gọi không biết đó là phần tử thực vừa được lấy hay dấu hiệu Stack rỗng. Có thể giải quyết bằng ngoại lệ, một giá trị sentinel nội bộ không thể nhầm với dữ liệu, hoặc kiểu kết quả phân biệt `Some(None)` với `None-option`.

Ca rỗng nên kiểm tra tối thiểu:

1. Khởi tạo cho kích thước `0`, bất biến hợp lệ và không có phần tử đọc được.
2. Phép toán đọc/xóa không hợp lệ sinh đúng kết quả lỗi được đặc tả.
3. Nhánh lỗi không làm thay đổi kích thước, chỉ số hoặc các liên kết nội bộ.
4. Sau lỗi vẫn có thể thêm phần tử và sử dụng bình thường.

## 3. Ca một phần tử: bước chuyển trạng thái dễ làm sai đầu và đuôi

Khi cấu trúc chỉ có một phần tử, **đầu và đuôi có thể trỏ cùng một nút**, **đỉnh và đáy trùng nhau**, hoặc **nút gốc đồng thời là lá**. Xóa phần tử này phải cập nhật mọi trường liên quan.

| Cấu trúc | Trước thao tác | Thao tác | Sau thao tác cần xác nhận |
|---|---|---|---|
| Stack | `[A]` | `pop()` | Trả `A`; Stack rỗng |
| Queue | `[A]` | `dequeue()` | Trả `A`; không còn phần tử trước hoặc sau |
| Danh sách liên kết đơn | `head -> A -> null`, `tail = A` | Xóa `A` | `head = tail = null`, `size = 0` |
| Danh sách liên kết đôi | Một nút A | Xóa A | Không còn con trỏ `head`/`tail` trỏ tới A; mọi liên kết rỗng hợp lệ |
| Heap | `[A]` | `extract_min()` | Trả A; heap rỗng, không truy cập `heap[0]` sau khi xóa |
| Cây BST | `root = A` | Xóa khóa của A | `root = null`, không còn nút |
| Disjoint Set | Một phần tử thuộc một tập | `find(x)` | Trả đại diện x; không cần thay đổi số tập |

Đặc biệt với danh sách liên kết, mã kiểu `head = head.next` **chưa đủ** nếu có con trỏ `tail`. Khi xóa nút duy nhất, `tail` phải được xóa theo; nếu không, thao tác `append` tiếp theo có thể nối vào nút đã bị loại khỏi danh sách.

Kiểm tra cả hai chiều chuyển trạng thái:

```text
Rỗng -> thêm A -> Một phần tử -> lấy A -> Rỗng
Rỗng -> thêm A -> thêm B -> Hai phần tử -> lấy một -> Một phần tử
```

Nếu cài đặt có tối ưu riêng cho `size == 1`, hãy thêm ca kiểm thử lặp chu trình `thêm -> xóa` nhiều lần. Lỗi giữ tham chiếu cũ hoặc cập nhật chỉ số không đầy đủ thường chỉ xuất hiện ở lần lặp thứ hai.

## 4. Khóa trùng và phần tử trùng: phải tách ngữ nghĩa từng ADT

“Trùng” có thể mang ý nghĩa rất khác nhau:

- **List, Stack, Queue:** thông thường cho phép nhiều phần tử bằng nhau; thêm `A` hai lần tạo hai vị trí logic.
- **Set:** hai giá trị được coi là bằng nhau theo quy tắc so sánh của Set chỉ có **một** đại diện logic; `add(A)` lần hai không tăng kích thước.
- **Map:** mỗi khóa logic ánh xạ tới một giá trị tại một thời điểm; `put(k, v2)` với `k` đã tồn tại thường thay giá trị `v1` bằng `v2` và không tăng số khóa.
- **Multiset / Multimap:** giá trị hay khóa có thể xuất hiện nhiều lần; phải đặc tả đếm số lần hoặc cách trả tập kết quả.
- **BST / heap:** heap có thể chứa nhiều giá trị bằng nhau; BST cần quy ước cấm trùng, đếm số lần hoặc đặt các khóa bằng nhau ở nhánh được chọn. Quy ước phải được giữ cả lúc chèn, tìm và xóa.
- **Đồ thị:** một đồ thị đơn thường không có cạnh trùng; đa đồ thị cho phép nhiều cạnh nối cùng cặp đỉnh. `add_edge(u, v)` phải làm đúng loại đồ thị được đặc tả.

### Khóa trùng không giống va chạm băm

Với bảng băm, hai khóa **khác nhau** có thể cho cùng giá trị băm hoặc cùng bucket. Đó là **va chạm băm**, không có nghĩa chúng là khóa trùng. Hai khóa chỉ được coi là trùng khi quan hệ bằng nhau theo hợp đồng của Map kết luận như vậy. Nếu `a == b`, các giá trị băm phải tương thích theo yêu cầu của bộ so sánh/băm; nhưng `hash(a) == hash(b)` **không** suy ra `a == b`.

Một ma trận kiểm thử Map hữu ích:

| Trước thao tác | Thao tác | Kết quả quan sát cần kiểm tra |
|---|---|---|
| Map rỗng | `put(k, 10)` | Có đúng một khóa `k`, giá trị 10 |
| Đã có `k -> 10` | `put(k, 20)` | Vẫn chỉ một khóa `k`, giá trị thành 20 |
| Đã có `k -> None` | `put(k, 20)` | Phát hiện `k` đã tồn tại dù giá trị cũ là `None` |
| Đã có `k1 -> A` | `put(k2, B)` với `k1 != k2` nhưng cùng hash/bucket | Cả hai khóa vẫn tìm được, không ghi đè nhau |
| Có nhiều khóa | `remove(k)` | Chỉ xóa `k`; mọi khóa khác giữ nguyên |

Ví dụ một hợp đồng `put` trả về cặp `(đã_tồn_tại, giá_trị_cũ)` để phân biệt khóa vắng mặt với giá trị `None`:

```python
def put(mapping: dict, key, value):
    if key in mapping:
        old_value = mapping[key]
        mapping[key] = value
        return True, old_value
    mapping[key] = value
    return False, None


m = {}
assert put(m, "id", None) == (False, None)
assert put(m, "id", 7) == (True, None)
assert len(m) == 1
assert m["id"] == 7
```

Trong ví dụ Python, `key` phải băm được và thỏa quy tắc bình đẳng của `dict`. Nếu tự xây dựng HashMap, kiểm thử khóa khác nhau nhưng chủ động có cùng hàm băm còn giúp phát hiện lỗi xử lý chuỗi liên kết hoặc probing.

## 5. Biên chỉ số: chỉ một ký tự `<=` cũng đổi hành vi

Với cấu trúc dạng dãy dài `n`, cần phân biệt **truy cập**, **xóa** và **chèn**:

| Phép toán | Miền chỉ số hợp lệ, dùng chỉ số không âm | Ca cần thử |
|---|---|---|
| `get(i)` / `set(i, x)` | `0 <= i < n` | `-1`, `0`, `n - 1`, `n` |
| `remove_at(i)` | `0 <= i < n` | `0` khi rỗng; `0` và `n - 1` khi có dữ liệu; `n` |
| `insert_at(i, x)` | `0 <= i <= n` | Chèn đầu `0`, chèn cuối `n`, ngoài biên `n + 1` |
| `slice(start, end)` nửa mở | Thường `0 <= start <= end <= n` khi API tự định nghĩa chặt | Đoạn rỗng `start == end`, đoạn toàn bộ `[0:n]` |

Một số ngôn ngữ như Python hỗ trợ chỉ số âm hoặc tự điều chỉnh chỉ số lớn khi gọi `list.insert`. Nếu đang thiết kế ADT yêu cầu chỉ số **không âm, không tự điều chỉnh**, phải kiểm tra điều kiện *trước khi* gọi cơ chế của ngôn ngữ:

```python
def get_at(items, index):
    if not (0 <= index < len(items)):
        raise IndexError("index ngoai pham vi")
    return items[index]


def insert_at(items, index, value):
    if not (0 <= index <= len(items)):
        raise IndexError("vi tri chen ngoai pham vi")
    items.insert(index, value)


a = []
insert_at(a, 0, "A")  # Chen vao mang rong la hop le.
insert_at(a, 1, "B")  # Chen tai vi tri n la hop le.
assert a == ["A", "B"]
assert get_at(a, 0) == "A"
assert get_at(a, 1) == "B"

for invalid_index in (-1, 2):
    try:
        get_at(a, invalid_index)
    except IndexError:
        pass
    else:
        raise AssertionError("get_at phai tu choi chi so sai")
```

Kiểm thử còn nên xác nhận **không thay đổi dữ liệu khi chỉ số sai**, đặc biệt với `insert_at` và `remove_at`. Để kiểm tra lỗi ngoài biên, luôn thử các giá trị **ngay sát ranh giới**: `n - 1`, `n`, `n + 1`; chỉ dùng giá trị rất lớn có thể bỏ sót lỗi so sánh `>` thay vì `>=`.

### Biên của mảng vòng và cây

Trong Queue vòng, vị trí vật lý thường được tính `index = (head + offset) % capacity`. Các ca quan trọng là `head == capacity - 1`, `head + offset == capacity` và các trạng thái đã quấn qua đầu mảng. **Không** được tính modulo khi `capacity == 0`, trừ khi đã đặc tả và xử lý riêng trường hợp đó.

Trong cây, “biên chỉ số” còn xuất hiện khi dùng mảng biểu diễn heap: phần tử `i` có con trái `2*i + 1`, con phải `2*i + 2` **chỉ khi** chỉ số đó nhỏ hơn `n`. Với heap rỗng hoặc một phần tử, không được đọc con vốn không tồn tại. Đối với truy vấn đoạn `[l, r)` hoặc `[l, r]`, nhất thiết ghi rõ **đầu cuối có bao gồm hay không**, vì `r == n` hợp lệ cho đoạn nửa mở nhưng không hợp lệ nếu `r` là chỉ số của phần tử cuối.

## 6. Đầy dung lượng: phân biệt sức chứa với số phần tử

**Dung lượng** (`capacity`) là lượng lưu trữ có thể dùng trước khi phải làm gì đó; **kích thước** (`size`) là số phần tử logic đang có. Với bộ đệm cố định `capacity = C`, bất biến cơ bản là:

\[
0 \le size \le C.
\]

Khi `size == C`, ta đã ở trạng thái đầy. Phép `enqueue(x)` hoặc `push(x)` phải có một chính sách rõ ràng:

| Chính sách | Hành vi khi đầy | Ca kiểm thử đặc trưng |
|---|---|---|
| **Từ chối** | Báo `FullError`/trả thất bại, không thay đổi dữ liệu | Đầy -> thêm -> lỗi; dữ liệu và kích thước giữ nguyên |
| **Tự mở rộng** | Cấp phát thêm và giữ nguyên thứ tự phần tử | Thêm khi đầy làm tăng dung lượng, mọi phần tử cũ vẫn đúng |
| **Ghi đè phần tử cũ nhất** | Thay phần tử theo chính sách bộ đệm vòng | Khi đầy, xác nhận phần tử nào bị loại và thứ tự mới |
| **Chặn chờ** | Đợi đến khi có chỗ nếu API hỗ trợ đồng bộ | Phải kiểm thử cơ chế đánh thức/hủy/chờ hết hạn trong môi trường đồng thời |

Không được đổi từ “từ chối” sang “ghi đè” chỉ để tránh ngoại lệ: đó là thay đổi hành vi quan sát được, dễ làm mất dữ liệu. Một **mảng động** có thể tăng dung lượng khi đầy về mặt nội bộ, nhưng **Queue có giới hạn tối đa** có thể phải từ chối thêm dù máy vẫn còn bộ nhớ. Nếu `capacity = 0` được phép trong đặc tả, đó là bộ đệm luôn đầy và phải có xử lý riêng; ví dụ bên dưới quy định `capacity >= 1` để phép modulo luôn hợp lệ.

Những kích thước nên thử là `0`, `1`, `C - 1`, `C`, và thao tác làm phát sinh nhu cầu lưu `C + 1` phần tử. Khi tự mở rộng, kiểm tra lần thêm **đúng lúc** `size == C`, vì lần thêm ngay trước đó thường chạy theo nhánh khác. Khi từ chối, xác nhận có thể `dequeue` rồi `enqueue` trở lại bình thường.

## 7. Ví dụ hoàn chỉnh: Queue vòng hữu hạn và các ca biên

Ta chọn hợp đồng đơn giản:

- `capacity` là số nguyên dương cố định, Queue có thể chứa cả giá trị `None` và phần tử trùng nhau.
- `enqueue(x)` thêm vào cuối nếu còn chỗ; khi đầy ném `QueueFull` **trước khi sửa trạng thái**.
- `dequeue()` trả phần tử ở đầu; khi rỗng ném `QueueEmpty` và giữ nguyên Queue.
- `front()` trả đầu Queue nhưng không xóa; `to_list()` tạo ảnh chụp logic theo thứ tự FIFO.

```python
_EMPTY = object()


class QueueEmpty(IndexError):
    pass


class QueueFull(OverflowError):
    pass


class BoundedRingQueue:
    def __init__(self, capacity: int):
        if capacity < 1:
            raise ValueError("capacity phai >= 1")
        self._buffer = [_EMPTY] * capacity
        self._head = 0
        self._size = 0
        self._check()

    def __len__(self):
        return self._size

    def _check(self):
        c = len(self._buffer)
        assert c >= 1
        assert 0 <= self._size <= c
        assert 0 <= self._head < c
        if self._size == 0:
            assert self._head == 0
        for index, value in enumerate(self._buffer):
            active = (index - self._head) % c < self._size
            assert (value is not _EMPTY) == active

    def to_list(self):
        c = len(self._buffer)
        return [self._buffer[(self._head + i) % c]
                for i in range(self._size)]

    def enqueue(self, value):
        c = len(self._buffer)
        if self._size == c:
            raise QueueFull("Queue day")
        tail = (self._head + self._size) % c
        self._buffer[tail] = value
        self._size += 1
        self._check()

    def front(self):
        if self._size == 0:
            raise QueueEmpty("Queue rong")
        return self._buffer[self._head]

    def dequeue(self):
        if self._size == 0:
            raise QueueEmpty("Queue rong")
        value = self._buffer[self._head]
        self._buffer[self._head] = _EMPTY
        self._head = (self._head + 1) % len(self._buffer)
        self._size -= 1
        if self._size == 0:
            self._head = 0
        self._check()
        return value
```

Ở phiên bản phục vụ kiểm thử này, `_check` duyệt toàn bộ bộ đệm sau mỗi lần cập nhật, tốn `O(C)` thời gian, giúp phát hiện ô không được dọn hoặc kích thước sai. Nếu bỏ kiểm tra toàn phần trong bản chạy tối ưu, `enqueue`, `dequeue` và `front` của Queue cố định đều tốn `O(1)` thời gian và `O(C)` bộ nhớ tổng thể. Những lệnh `assert` nội bộ có thể bị Python loại bỏ khi chạy với `-O`; không dùng chúng để thay thế kiểm tra đầu vào và xử lý lỗi công khai.

### Bộ kiểm thử thực hành bằng `unittest`

Các ca sau tập trung vào rỗng, một phần tử, giá trị trùng, `None`, đầy dung lượng và quấn vòng. Chúng kiểm tra cả **giá trị trả về và trạng thái sau thao tác**.

```python
import unittest


class TestBoundedRingQueue(unittest.TestCase):
    def test_empty_and_recovery(self):
        q = BoundedRingQueue(2)
        self.assertEqual(q.to_list(), [])
        with self.assertRaises(QueueEmpty):
            q.dequeue()
        with self.assertRaises(QueueEmpty):
            q.front()
        self.assertEqual(len(q), 0)
        q.enqueue("A")
        self.assertEqual(q.dequeue(), "A")
        self.assertEqual(q.to_list(), [])

    def test_one_element_and_none(self):
        q = BoundedRingQueue(1)
        q.enqueue(None)
        self.assertIsNone(q.front())
        self.assertIsNone(q.dequeue())
        self.assertEqual(len(q), 0)
        q.enqueue("again")
        self.assertEqual(q.dequeue(), "again")

    def test_duplicates(self):
        q = BoundedRingQueue(3)
        q.enqueue("A")
        q.enqueue("A")
        self.assertEqual(q.to_list(), ["A", "A"])
        self.assertEqual(q.dequeue(), "A")
        self.assertEqual(q.to_list(), ["A"])

    def test_full_does_not_mutate(self):
        q = BoundedRingQueue(2)
        q.enqueue("A")
        q.enqueue("B")
        before = q.to_list()
        with self.assertRaises(QueueFull):
            q.enqueue("C")
        self.assertEqual(q.to_list(), before)
        self.assertEqual(len(q), 2)

    def test_wraparound_after_full(self):
        q = BoundedRingQueue(2)
        q.enqueue("A")
        q.enqueue("B")
        self.assertEqual(q.dequeue(), "A")
        q.enqueue("C")  # Tail quay ve vi tri vat ly 0
        self.assertEqual(q.to_list(), ["B", "C"])
        self.assertEqual(q.dequeue(), "B")
        self.assertEqual(q.dequeue(), "C")
        self.assertEqual(q.to_list(), [])

    def test_invalid_capacity(self):
        with self.assertRaises(ValueError):
            BoundedRingQueue(0)


if __name__ == "__main__":
    unittest.main()
```

Để chạy trực tiếp, đặt phần định nghĩa `BoundedRingQueue` và phần kiểm thử vào cùng tệp `.py`. Mỗi phép cập nhật thành công tự kiểm tra bất biến; kiểm thử bổ sung các yêu cầu nghiệp vụ mà bất biến nội bộ không xác nhận được, chẳng hạn đúng thứ tự FIFO và không làm biến đổi dữ liệu khi Queue đầy.

Lưu ý: `to_list()` của ví dụ là hàm hỗ trợ quan sát trong bài học, không nhất thiết là một phương thức phải có trong Queue thực tế. Nếu API chỉ cung cấp `front`, `enqueue`, `dequeue`, ta có thể kiểm thử trình tự trả về qua các phép `dequeue` thay vì đọc bộ đệm nội bộ.

## 8. Thiết kế ma trận ca biên có hệ thống

Thay vì chỉ chọn dữ liệu ngẫu nhiên, hãy phân hoạch trạng thái và đối chiếu các thao tác tại **đúng điểm đổi nhánh**.

| Trạng thái đầu | Thao tác | Điểm cần quan sát |
|---|---|---|
| Rỗng `n = 0` | Đọc, xóa, tìm, thêm | Lỗi rỗng/không tồn tại hoặc thêm phần tử đầu tiên |
| Một phần tử `n = 1` | Đọc, xóa, cập nhật | Phần tử duy nhất; chuyển về rỗng |
| Ít nhất hai phần tử | Xóa đầu, xóa giữa, xóa cuối | Liên kết, chỉ số và thứ tự phần còn lại |
| Có giá trị/khóa trùng | Thêm, tìm, xóa | Chính sách trùng, số lượng và giá trị còn lại |
| Biên dưới `i = -1, 0` | Truy cập/chèn/xóa | Chỉ số âm, đầu dãy, khả năng chèn vào dãy rỗng |
| Biên trên `i = n-1, n, n+1` | Truy cập/chèn/xóa | Bao gồm hay loại trừ biên trên |
| Sắp đầy `n = C-1` | Thêm | Đi vào trạng thái đầy với đủ `C` phần tử |
| Đầy `n = C` | Thêm | Từ chối/giãn bộ nhớ/ghi đè đúng hợp đồng |
| Vừa rời trạng thái đầy | Xóa rồi thêm | Chỉ số quấn vòng, tái sử dụng chỗ trống |

Mỗi hàng nên có kiểm thử **trước, trong và sau** nhánh đặc biệt, vì lỗi có thể nằm ở cả thao tác chuẩn bị lẫn thao tác xử lý biên. Với một mảng động, hãy thử các dung lượng nhỏ như `1`, `2`, `4` để kích hoạt cấp phát lại nhiều lần. Với cây cân bằng, thử các chuỗi gây quay trái, quay phải và hai kiểu quay kép; với bảng băm, thử các chuỗi dẫn đến va chạm, xóa rồi chèn lại, hoặc kích hoạt rehash.

### Không phải mọi tổ hợp đều cần một ca riêng

Nếu có năm trạng thái biên và sáu phép toán, việc nhân tất cả tổ hợp có thể tạo nhiều ca không có ý nghĩa. Chọn các kết hợp thể hiện một **quy tắc cụ thể**: Stack không cần kiểm thử “khóa trùng” như Map, nhưng cần kiểm thử “giá trị trùng” và thứ tự LIFO; đồ thị không có “đầy bộ đệm” nếu thiết kế không giới hạn số đỉnh/cạnh. Hãy ưu tiên ca biên dựa trên ADT và nhánh thuật toán thực sự tồn tại.

## 9. Từ ca đơn lẻ sang kiểm thử chuỗi và thuộc tính

Nhiều lỗi không xuất hiện trong một lời gọi độc lập. Ví dụ Queue vòng thường chỉ hỏng sau chuỗi:

```text
enqueue(A), enqueue(B), dequeue(), enqueue(C), dequeue(), dequeue()
```

Với dung lượng `2`, chuỗi này buộc chỉ số cuối quấn vòng. Có thể kiểm tra theo **mô hình tham chiếu**: một `list` hoặc `collections.deque` đóng vai trò dãy Queue logic, còn cài đặt thật được thử trên cùng các lệnh. Sau từng bước, so kích thước, thứ tự và lỗi mong đợi; khi Queue rỗng/đầy, xác minh đường lỗi không làm thay đổi mô hình lẫn cấu trúc thật.

Các thuộc tính tổng quát hữu ích:

- **Stack:** nếu `push(x)` thành công thì `pop()` ngay sau đó phải trả `x` và khôi phục trạng thái logic cũ.
- **Queue:** `enqueue(x)` vào Queue rỗng rồi `dequeue()` phải trả `x`; hai lần thêm `x`, `y` rồi lấy phải trả theo thứ tự `x`, `y`.
- **Set:** `add(x)` hai lần phải cho cùng tập logic như thêm một lần, nếu phép thêm dùng ngữ nghĩa Set thông thường.
- **Map:** ghi đè một khóa không làm thay đổi giá trị của các khóa khác.
- **Mảng:** chèn `x` tại chỉ số hợp lệ `i`, rồi xóa đúng `i` trước khi có cập nhật khác, phải khôi phục dãy ban đầu.
- **Heap:** nếu `extract_min()` thành công, kết quả không lớn hơn mọi phần tử còn lại theo quan hệ thứ tự của heap.

Những thuộc tính này vừa giúp sinh kiểm thử ngẫu nhiên, vừa hỗ trợ thu nhỏ chuỗi lỗi. Nếu một kiểm thử ngẫu nhiên thất bại, hãy ghi hạt giống, chuỗi phép toán và trạng thái trước lần đầu sai để tái hiện chính xác.

## 10. Bài tập tự kiểm tra

**Bài 1 — Tìm lỗi điều kiện đầy:** Cho Queue có `size`, `capacity` và mã:

```python
def enqueue(self, x):
    if self.size > self.capacity:
        raise QueueFull()
    # ghi x vao buffer va tang size
```

Hãy xác định lỗi và ca nhỏ nhất bắt được lỗi. **Đáp án:** cần kiểm tra `size == capacity` hoặc `size >= capacity` trước khi ghi. Với `capacity = 1`, thêm `A` để đạt `size = 1`, sau đó thử thêm `B`: mã dùng `>` vẫn cho phép ghi, dẫn đến truy cập sai ô hoặc tăng `size` quá dung lượng. Kiểm tra cả trạng thái sau lỗi phải vẫn chứa đúng `[A]`.

**Bài 2 — Viết ca Map ghi đè:** Map ban đầu có `k -> None`. Gọi `put(k, 5)`. **Đáp án mong đợi:** `k` được nhận diện là khóa đã tồn tại, kích thước Map không đổi, giá trị tại `k` trở thành `5`, mọi khóa khác không đổi. Nếu API trả giá trị cũ, cần phân biệt “khóa có giá trị cũ là `None`” với “khóa vắng mặt”.

**Bài 3 — Kiểm thử biên chèn và đọc:** Với dãy `[10, 20]`, hãy kiểm tra `get(1)`, `get(2)`, `insert(2, 30)`, `insert(4, 40)` theo hợp đồng chỉ số không âm, chèn cho phép `i == n`. **Đáp án:** `get(1)` trả `20`, `get(2)` lỗi; `insert(2, 30)` thành `[10, 20, 30]`; lúc đó `insert(4, 40)` lỗi và dãy giữ nguyên. Chú ý đánh giá biên dựa trên **kích thước tại thời điểm gọi**, không phải kích thước lúc đầu bài.

**Bài 4 — Phân biệt va chạm và trùng:** Hai khóa `k1 != k2` có cùng giá trị hash. Hãy phát biểu điều Map phải bảo đảm. **Đáp án:** cả hai khóa được lưu và tìm độc lập, trừ khi hợp đồng về quan hệ bằng nhau coi chúng là cùng một khóa; một hash trùng không đủ để hợp nhất hai khóa.

## 11. Checklist trước khi kết luận phép toán đã đúng

1. Đã kiểm tra **rỗng → một phần tử → rỗng** và không còn tham chiếu/đầu-đuôi sai sau khi xóa phần tử cuối?
2. Đã kiểm tra giá trị trùng và **khóa trùng theo đúng ADT**, kể cả trường hợp giá trị hợp lệ là `None`?
3. Đã kiểm tra chỉ số ngay sát biên dưới và trên, riêng cho đọc, chèn và xóa?
4. Đã kiểm tra đúng lúc `size == capacity`, lúc vừa hết đầy và khi chỉ số vòng quấn qua mảng?
5. Mỗi nhánh lỗi có đúng ngoại lệ/giá trị trả về và **không sửa trạng thái ngoài hợp đồng**?
6. Sau thao tác có kiểm tra bất biến và so kết quả với mô hình hoặc trạng thái logic mong đợi?
7. Các yêu cầu thời gian, bộ nhớ đã được phát biểu đúng mức bảo đảm, kể cả lúc mở rộng hay rehash?

Ca biên là nơi các quy tắc trừu tượng gặp điều kiện thực tế của biểu diễn. Kiểm thử có hệ thống các trạng thái rỗng, một phần tử, trùng, sát biên chỉ số và đầy dung lượng giúp xác định **phép toán nào phá vỡ hợp đồng**, thay vì phát hiện sai lệch nhiều bước sau khi dữ liệu đã bị biến đổi.
