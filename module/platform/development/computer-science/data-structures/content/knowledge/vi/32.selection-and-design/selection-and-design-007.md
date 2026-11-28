# Kết hợp bảng băm với danh sách đôi để xây bộ đệm LRU

Một bộ đệm (*cache*) giữ lại dữ liệu đã tải hoặc tính toán để những lần truy cập sau không phải thực hiện công việc tốn kém. Khi bộ nhớ có giới hạn, hệ thống phải quyết định **giữ mục nào, loại mục nào** khi có dữ liệu mới. Chính sách **LRU – Least Recently Used** loại bỏ mục *ít được sử dụng gần đây nhất* trong số các mục hiện còn trong bộ đệm.

Tưởng như chỉ cần lưu danh sách các mục, nhưng cách cài đặt quyết định hiệu năng: tìm một khóa trong danh sách thường mất `O(n)`; còn bảng băm tra cứu khóa nhanh nhưng không tự duy trì thứ tự “vừa dùng gần nhất”. **Ghép bảng băm với danh sách liên kết đôi** cho phép thực hiện tra cứu, cập nhật mức độ gần đây và loại bỏ mục cũ nhất trong **`O(1)` kỳ vọng cho mỗi thao tác** dưới các giả định thích hợp về bảng băm.

Đây là một ví dụ quan trọng của chương **Lựa chọn và thiết kế**: chọn cấu trúc dữ liệu bằng cách xác định phép toán chủ đạo, bất biến phải giữ và chi phí thời gian/bộ nhớ. Ta sẽ thiết kế LRU từ yêu cầu, hiện thực một phiên bản có thể kiểm tra, rồi xem khi nào phương án này phù hợp và những bảo đảm nào nó *không* cung cấp.

## 1. Đặc tả chính xác một bộ đệm LRU

Giả sử bộ đệm có dung lượng tối đa `C` mục, mỗi mục là một cặp `(key, value)`. Một API tối thiểu gồm:

| Phép toán | Hành vi | Ảnh hưởng đến mức độ “gần đây” |
| --- | --- | --- |
| `get(key)` khi **hit** | Trả giá trị gắn với khóa | Đánh dấu mục đó là **vừa được sử dụng nhất** (*MRU*) |
| `get(key)` khi **miss** | Báo không tìm thấy | Không đổi thứ tự những mục đang có |
| `put(key, value)` khi khóa đã tồn tại | Thay giá trị | Đánh dấu mục đó là MRU |
| `put(key, value)` khi khóa mới, bộ đệm chưa đầy | Thêm mục | Mục mới trở thành MRU |
| `put(key, value)` khi khóa mới, bộ đệm đã đầy | Loại bỏ **LRU** rồi thêm mục mới | Mục mới trở thành MRU |
| `remove(key)` (nếu hỗ trợ) | Xóa chủ động một khóa | Không tự thay đổi thứ tự tương đối của các mục khác |

**Quy ước của bài học:** mọi lần `get` thành công và `put` đều tính là một lần sử dụng. Dung lượng `C` được đo bằng **số mục**, không phải số byte. Nếu `C = 0`, bộ đệm không giữ bất kỳ mục nào. Một giá trị như `None`/`null` có thể hợp lệ, vì thế cần phân biệt *miss* với *hit có giá trị null*.

LRU đo **thứ tự của các lần sử dụng**, không nhất thiết đo thời gian đồng hồ. Trong chương trình đơn luồng, mỗi lần truy cập có thể coi như một mốc logic tăng dần: mục nào được chạm sau thì mới hơn. Cách dùng thứ tự này tránh phụ thuộc vào độ phân giải của đồng hồ hoặc các trường hợp hai lần truy cập có timestamp giống nhau.

### Đừng nhầm LRU với FIFO hay LFU

- **FIFO – First In, First Out:** loại mục đã **được thêm vào lâu nhất**, cho dù mục đó vẫn được truy cập liên tục.
- **LRU – Least Recently Used:** loại mục có **lần truy cập hoặc cập nhật gần đây nhất xa nhất**.
- **LFU – Least Frequently Used:** ưu tiên loại mục có **số lần sử dụng thấp**, cần thêm quy tắc phá hòa và cơ chế quản lý tần suất.

Ví dụ, có A được chèn trước B nhưng A vừa được `get`. Khi thêm mục mới vào bộ đệm đầy, **LRU có thể loại B**, còn FIFO sẽ loại A nếu chưa có thay đổi khác. Đây là khác biệt ngữ nghĩa, không chỉ là chi tiết triển khai.

## 2. Vì sao cần kết hợp hai cấu trúc?

Một phương án ban đầu là lưu mọi mục trong một danh sách theo thứ tự sử dụng. Truy cập `get(key)` cần tìm đúng nút trước khi chuyển nó lên đầu: **`O(C)`** nếu phải quét. Nếu chỉ dùng hash map, tìm khóa thường kỳ vọng `O(1)`, nhưng xác định khóa nào ít được dùng gần đây nhất cần thông tin thứ tự; quét toàn bộ map mỗi lần loại bỏ có thể mất `O(C)`.

Giải pháp phối hợp hai cấu trúc, mỗi cấu trúc đảm nhiệm một công việc:

1. **Bảng băm** `index: key → node` tìm trực tiếp nút mang khóa, với thời gian kỳ vọng `O(1)` khi giả định về hàm băm, xử lý va chạm và hệ số tải phù hợp.
2. **Danh sách liên kết đôi** giữ các nút theo thứ tự sử dụng. Mỗi nút có con trỏ `prev` và `next`, nên có thể gỡ một nút **đã biết** và chèn lại ở đầu trong `O(1)`.

Quy ước trong bài: nút **gần đầu danh sách** là mục được sử dụng gần đây nhất (*MRU*); nút **gần cuối** là mục ít được sử dụng gần đây nhất (*LRU*).

```text
Bảng băm:
    index["B"] -> nodeB
    index["A"] -> nodeA
    index["C"] -> nodeC

Danh sách đôi dùng chính các đối tượng nodeB, nodeA, nodeC:
    HEAD <-> nodeB <-> nodeA <-> nodeC <-> TAIL
              MRU                     LRU
```

Trong biểu diễn thực tế, một nút chứa `key`, `value`, `prev` và `next`. Map giữ **tham chiếu đến chính nút đó**, thay vì sao chép dữ liệu hoặc lưu một chỉ số dễ thay đổi.

### Tại sao là danh sách *đôi*?

Khi đã biết nút B, để chuyển B lên đầu phải gỡ B khỏi vị trí cũ. Với danh sách đôi, nút B biết trực tiếp cả nút trước và nút sau, nên có thể nối hai nút ấy lại trong `O(1)`. Với danh sách liên kết đơn thông thường, B không có `prev`; muốn gỡ B, ta có thể phải tìm nút đứng trước nó bằng cách quét `O(C)` hoặc duy trì thêm thông tin phức tạp.

**Map tìm nút nhanh; danh sách đôi di chuyển nút nhanh.** Hai cấu trúc bổ sung cho nhau để cả hai nhu cầu đều được đáp ứng.

## 3. Dùng nút canh gác để đơn giản hóa thao tác

Một kỹ thuật quen thuộc là tạo hai nút giả (*sentinel/dummy nodes*):

- `head` là nút canh gác ở đầu, không mang khóa thật.
- `tail` là nút canh gác ở cuối, không mang khóa thật.

Khi rỗng:

```text
head <-> tail

head.next == tail
tail.prev == head
```

Khi có ba mục, theo thứ tự từ mới nhất đến cũ nhất:

```text
head <-> [K3] <-> [K1] <-> [K2] <-> tail
          MRU                    LRU
```

Ta **không bao giờ đưa sentinel vào bảng băm**. Nhờ luôn tồn tại hai nút biên, thao tác chèn/gỡ một nút thật không cần nhiều nhánh riêng cho trường hợp đầu hay cuối.

### 3.1. Gỡ một nút đã biết

Giả sử có các liên kết `left ↔ node ↔ right`. Gỡ `node` bằng cách nối `left` với `right`:

```text
detach(node):
    left = node.prev
    right = node.next

    left.next = right
    right.prev = left

    node.prev = null
    node.next = null
```

Các phép gán con trỏ có số lượng hằng số: `O(1)`. Nhưng **điều kiện tiên quyết** là `node` là một nút thật đang nằm trong đúng danh sách, các liên kết của nó còn hợp lệ. Không gỡ `head` hoặc `tail`.

### 3.2. Chèn nút ngay sau đầu

```text
insertAfterHead(node):
    first = head.next

    node.prev = head
    node.next = first

    head.next = node
    first.prev = node
```

Ngay cả khi danh sách rỗng, `first == tail` nên thao tác vẫn hợp lệ. Mục `node` trở thành MRU.

### 3.3. Chuyển nút đang có lên đầu

```text
moveToFront(node):
    detach(node)
    insertAfterHead(node)
```

Cả hai bước đều `O(1)` vì đã biết nút. Nút giữ nguyên `key`, `value` và danh tính logic; chỉ thay các liên kết. Bảng băm **không cần đổi** ánh xạ `key → node` khi di chuyển nút đó.

Có thể bỏ qua việc gỡ/chèn khi `node == head.next` để tiết kiệm vài phép gán, nhưng đây chỉ là tối ưu nhỏ, không thay đổi độ phức tạp.

### 3.4. Loại bỏ mục cũ nhất

Vì đầu là MRU và cuối là LRU, nút ít được sử dụng gần đây nhất luôn nằm ở `tail.prev`.

```text
evictLRU():
    if tail.prev == head:
        return EMPTY

    victim = tail.prev
    detach(victim)
    index.remove(victim.key)
    return victim
```

Việc xác định nút cần loại mất `O(1)`; gỡ nút khỏi danh sách mất `O(1)`; xóa khóa khỏi hash map thường có thời gian **kỳ vọng `O(1)`**, không phải bảo đảm chặn xấu nhất cho mọi triển khai.

**Điểm rất dễ sai:** chỉ gỡ nút khỏi danh sách mà quên xóa khỏi map sẽ để lại tham chiếu tới nút không còn thuộc bộ đệm, có thể khiến lần `get` sau trả dữ liệu đã bị loại.

## 4. Bất biến: điều gì phải luôn đúng?

Một bộ đệm đúng cần nhiều hơn việc “ví dụ chạy được”. Sau mỗi thao tác hoàn tất, phải bảo toàn các bất biến sau:

1. **Số lượng:** `0 ≤ |index| ≤ C`. Với `C = 0`, `index` rỗng và danh sách chỉ có hai sentinel.
2. **Tương ứng một–một:** mỗi khóa trong `index` trỏ tới **đúng một nút thật** đang có trong danh sách; mỗi nút thật trong danh sách có **đúng một khóa** trong map trỏ ngược về nút đó.
3. **Khóa duy nhất:** không có hai nút thật cùng một khóa; `index[node.key]` là chính `node`.
4. **Liên kết hai chiều:** với mọi nút `x` đang liên kết, `x.next.prev == x` và `x.prev.next == x` khi các nút kề tồn tại theo thiết kế sentinel.
5. **Biên hợp lệ:** `head.prev == null`, `tail.next == null`, `head.next` và `tail.prev` luôn trỏ đến nút hợp lệ.
6. **Thứ tự LRU:** đi từ `head.next` đến `tail.prev` ta gặp các mục theo thứ tự *từ truy cập gần đây nhất đến truy cập xa nhất*, theo quy ước “sử dụng” ở phần 1.

Bất biến (2) rất quan trọng vì hai cấu trúc lưu **cùng một tập mục** theo hai cách khác nhau. Nếu map có `n` khóa nhưng danh sách có `n-1` nút thật, lỗi không chỉ làm sai độ phức tạp mà còn làm sai kết quả.

Bất biến (6) là điều trực tiếp chứng minh **loại bỏ đúng LRU**: phần tử cuối là phần tử chưa được chạm lâu nhất theo thứ tự sử dụng.

## 5. Thiết kế các phép toán chính

### 5.1. `get(key)`

- Tìm nút tương ứng trong map.
- Nếu không có: trả miss, không đổi thứ tự.
- Nếu có: chuyển nút lên ngay sau `head`, rồi trả giá trị.

```text
get(key):
    node = index.get(key)
    if node không tồn tại:
        return MISS

    moveToFront(node)
    return HIT(node.value)
```

**Độ phức tạp:** tra map kỳ vọng `O(1)`, thay liên kết `O(1)`, tổng kỳ vọng `O(1)` dưới giả định khóa có chi phí băm/so sánh hằng số phù hợp.

Một hàm `peek(key)` đôi khi được bổ sung để đọc mà **không đổi mức độ gần đây**. Không nên tự thêm `peek` vào API mà không ghi rõ khác biệt với `get`, vì hành vi cập nhật thứ tự quyết định đúng/sai của chính sách LRU.

### 5.2. `put(key, value)` khi khóa đã có

- Tìm nút trong map.
- Ghi giá trị mới vào chính nút đó.
- Chuyển nút lên đầu như một lần sử dụng mới.
- Không tăng số mục; không loại bỏ phần tử nào.

```text
if index.contains(key):
    node = index.get(key)
    node.value = value
    moveToFront(node)
    return
```

Nếu thay vì cập nhật nút cũ ta tạo thêm nút mới cùng khóa, bất biến khóa duy nhất sẽ bị phá. Khi đó có thể có một nút cũ nằm ở cuối danh sách nhưng map lại trỏ tới nút mới, làm chính sách loại bỏ sai.

### 5.3. `put(key, value)` khi khóa mới

- Nếu `C = 0`: không lưu mục.
- Tạo một nút mới, thêm nó vào map và đầu danh sách.
- Nếu số lượng vượt `C`, lấy nút ngay trước `tail` và xóa nó khỏi **cả danh sách lẫn map**.

```text
put(key, value):
    if capacity == 0:
        return

    node = index.get(key)
    if node tồn tại:
        node.value = value
        moveToFront(node)
        return

    fresh = new Node(key, value)
    index[key] = fresh
    insertAfterHead(fresh)

    if index.size > capacity:
        victim = tail.prev
        detach(victim)
        index.remove(victim.key)
```

Việc chèn mới rồi kiểm tra vượt sức chứa làm cho ở trạng thái trung gian có tối đa `C+1` mục, nhưng **trạng thái sau khi lời gọi hoàn tất** thỏa `|index| ≤ C`. Nếu môi trường yêu cầu không bao giờ vượt ngân sách vật lý dù chỉ tạm thời, có thể loại mục cũ trước khi cấp chỗ cho mục mới, hoặc thiết kế quản lý bộ nhớ phù hợp hơn.

Các bước trong mã giả giả định thao tác thành công, không bị luồng khác chen vào. Một triển khai có cấp phát thất bại, callback lúc evict hoặc ghi dữ liệu song song phải bảo đảm không để lại trạng thái nửa cập nhật.

### 5.4. `remove(key)` nếu người dùng xóa chủ động

```text
remove(key):
    node = index.get(key)
    if node không tồn tại:
        return false

    detach(node)
    index.remove(key)
    return true
```

Xóa chủ động không đồng nghĩa một mục bị loại vì LRU. Cả hai đều cần xóa nhất quán map/danh sách, nhưng thống kê hit/miss và lý do loại bỏ có thể được ứng dụng ghi riêng.

## 6. Mô phỏng từng bước với dung lượng 3

Ký hiệu danh sách theo chiều **MRU → LRU**. Bộ đệm ban đầu rỗng với `C = 3`:

| Bước | Thao tác | Kết quả / diễn giải | Danh sách sau thao tác (MRU → LRU) |
| ---: | --- | --- | --- |
| 0 | Khởi tạo | Chưa có mục | `[]` |
| 1 | `put(A, 1)` | Thêm A | `[A]` |
| 2 | `put(B, 2)` | Thêm B | `[B, A]` |
| 3 | `put(C, 3)` | Thêm C, vừa đầy | `[C, B, A]` |
| 4 | `get(A)` | Hit, trả 1; A mới nhất | `[A, C, B]` |
| 5 | `put(D, 4)` | Thêm D, loại **B** | `[D, A, C]` |
| 6 | `put(C, 30)` | Sửa C thành 30, C mới nhất | `[C, D, A]` |
| 7 | `get(B)` | Miss, thứ tự giữ nguyên | `[C, D, A]` |
| 8 | `put(E, 5)` | Thêm E, loại **A** | `[E, C, D]` |

Ở bước 5, **B** bị loại dù B được chèn sau A, vì A vừa được truy cập ở bước 4. Đó chính là khác biệt giữa LRU và FIFO.

Sau bước 6, C vẫn có một nút trong danh sách, giá trị là 30. Nếu cập nhật C mà tạo thêm nút C mới, danh sách có thể chứa C hai lần và làm hỏng thứ tự loại bỏ.

### Tự thử xác định LRU

Nếu lúc này `get(D)` thành công, thứ tự sẽ là `[D, E, C]`. Một lần `put(F, 6)` tiếp theo loại C và để lại `[F, D, E]`.

Điều quan trọng là **truy cập thành công vào mục đang có làm đổi vị trí**, kể cả khi không thay đổi giá trị.

## 7. Hiện thực Python 3 dùng sentinel

Đoạn mã sau là một hiện thực học tập đầy đủ của LRU theo **số mục**. Nó dùng `dict` làm bảng băm và danh sách đôi tự cài đặt. `get` trả `(found, value)` để phân biệt miss với hit có giá trị `None`.

```python
class _Node:
    __slots__ = ("key", "value", "prev", "next")

    def __init__(self, key=None, value=None):
        self.key = key
        self.value = value
        self.prev = None
        self.next = None


class LRUCache:
    def __init__(self, capacity):
        if capacity < 0:
            raise ValueError("capacity must be nonnegative")

        self.capacity = capacity
        self.index = {}              # key -> _Node

        self.head = _Node()          # nút giả MRU
        self.tail = _Node()          # nút giả LRU
        self.head.next = self.tail
        self.tail.prev = self.head

    def _detach(self, node):
        # node là một nút thật đang nằm trong danh sách.
        before = node.prev
        after = node.next
        before.next = after
        after.prev = before
        node.prev = None
        node.next = None

    def _insert_front(self, node):
        first = self.head.next
        node.prev = self.head
        node.next = first
        self.head.next = node
        first.prev = node

    def _touch(self, node):
        if node.prev is self.head:
            return
        self._detach(node)
        self._insert_front(node)

    def get(self, key):
        node = self.index.get(key)
        if node is None:
            return False, None       # miss; None có thể là value hợp lệ

        self._touch(node)
        return True, node.value

    def put(self, key, value):
        if self.capacity == 0:
            return

        node = self.index.get(key)
        if node is not None:
            node.value = value
            self._touch(node)
            return

        node = _Node(key, value)
        self.index[key] = node
        self._insert_front(node)

        if len(self.index) > self.capacity:
            victim = self.tail.prev
            self._detach(victim)
            del self.index[victim.key]

    def remove(self, key):
        node = self.index.get(key)
        if node is None:
            return False

        self._detach(node)
        del self.index[key]
        return True

    def keys_mru_to_lru(self):
        node = self.head.next
        while node is not self.tail:
            yield node.key
            node = node.next

    def __len__(self):
        return len(self.index)
```

**Giới hạn của ví dụ:** mã giả định khóa có thể dùng làm khóa `dict`, không có thao tác đồng thời và không hỗ trợ TTL, trọng số, chuyển đổi dung lượng lúc chạy hay callback khi loại bỏ. Một key hợp lệ trỏ tới một nút thật; sentinel không nằm trong `dict`. Với đối tượng khóa có thể thay đổi nội dung được dùng tính hash, chương trình có thể không tìm lại được mục, nên khóa phải giữ ổn định theo quy tắc của bảng băm.

### Kiểm chứng kết quả bằng các thao tác đơn giản

```python
cache = LRUCache(3)
cache.put("A", 1)
cache.put("B", 2)
cache.put("C", 3)
assert list(cache.keys_mru_to_lru()) == ["C", "B", "A"]

assert cache.get("A") == (True, 1)
assert list(cache.keys_mru_to_lru()) == ["A", "C", "B"]

cache.put("D", 4)                    # đẩy B ra khỏi cache
assert cache.get("B") == (False, None)
assert list(cache.keys_mru_to_lru()) == ["D", "A", "C"]

cache.put("C", 30)                  # cập nhật mục có sẵn
assert cache.get("C") == (True, 30)
assert len(cache) == 3

cache.put("E", 5)                   # sau get(C), A là LRU
assert cache.get("A") == (False, None)
assert list(cache.keys_mru_to_lru()) == ["E", "C", "D"]

zero = LRUCache(0)
zero.put("X", 100)
assert len(zero) == 0
assert zero.get("X") == (False, None)

one = LRUCache(1)
one.put("X", None)
assert one.get("X") == (True, None)  # hit với giá trị None
one.put("Y", 9)
assert one.get("X") == (False, None)
assert one.get("Y") == (True, 9)
```

Đoạn kiểm chứng là các tình huống có thể chạy trong môi trường Python 3; nó minh họa hành vi đúng, **không thay thế** kiểm thử bất biến và kiểm thử đồng thời của một bộ đệm sản phẩm thực tế.

## 8. Phân tích độ phức tạp và bộ nhớ

Gọi `n` là số mục hiện có, `n ≤ C`. Giả định thao tác con trỏ và xử lý khóa có chi phí `O(1)`, bảng băm có chi phí kỳ vọng `O(1)` với hệ số tải được duy trì phù hợp.

| Thao tác | Truy cập bảng băm | Thao tác danh sách đôi | Tổng thời gian thông dụng |
| --- | --- | --- | --- |
| `get(key)` hit | Kỳ vọng `O(1)` | Gỡ + chèn trước, `O(1)` | **Kỳ vọng `O(1)`** |
| `get(key)` miss | Kỳ vọng `O(1)` | Không làm gì | **Kỳ vọng `O(1)`** |
| `put(key,value)` khóa cũ | Kỳ vọng `O(1)` | Cập nhật/touch `O(1)` | **Kỳ vọng `O(1)`** |
| `put(key,value)` khóa mới | Chèn và có thể xóa, thường kỳ vọng khấu hao `O(1)` | Thêm trước và có thể gỡ cuối `O(1)` | **Kỳ vọng khấu hao `O(1)`** |
| `remove(key)` | Kỳ vọng `O(1)` | Gỡ nút `O(1)` | **Kỳ vọng `O(1)`** |
| Đọc mục MRU/LRU nếu không rỗng | Không cần | `head.next`/`tail.prev` | `O(1)` |
| Liệt kê tất cả `n` mục | Không cần | Duyệt `n` nút | `O(n)` |

**Vì sao không ghi “`O(1)` trường hợp xấu cho mọi thao tác”?** Bởi hash map thông dụng có thể gặp va chạm hoặc phải rehash. Một lần `put` kích hoạt tái băm có thể tốn `O(n)`, còn `get` với va chạm bất lợi cũng có thể chậm hơn hằng số. Việc thay đổi con trỏ trong danh sách đôi có chặn `O(1)`, nhưng tổng thời gian còn chịu chi phí của map.

Nếu khóa là chuỗi dài `L` ký tự và phải tính lại hash hoặc so sánh toàn bộ chuỗi, thời gian xử lý khóa có thể phụ thuộc `L`. Khi báo độ phức tạp `O(1)` theo `n`, hãy nêu giả định về chi phí băm/so sánh.

### 8.1. Bộ nhớ

Mỗi mục được lưu dưới dạng:

- Một nút danh sách: `key`, `value`, `prev`, `next`.
- Một mục bảng băm: ánh xạ `key → node`.
- Hai nút sentinel và một số biến quản lý.

Số mục tối đa `C` nên **bộ nhớ phụ `O(C)`** cho phần quản lý chỉ mục/nút, ngoài kích thước thực của các giá trị và khóa. Nếu bộ đệm tự sở hữu các bản sao giá trị, tổng bộ nhớ dữ liệu còn phụ thuộc kích thước từng giá trị; không thể kết luận “chỉ tốn `C` byte”.

Tại một số thời điểm, bảng băm có dung lượng dự phòng và có thể tạo bảng mới khi resize, làm **bộ nhớ đỉnh** cao hơn trạng thái thông thường. Bản thân danh sách đôi cũng tiêu tốn thêm hai liên kết cho mỗi nút và chi phí cấp phát nút. Nếu `C` nhỏ hoặc dữ liệu rất ngắn, overhead này có thể đáng kể so với giá trị được cache.

### 8.2. Chứng minh ngắn tính đúng đắn

Giả sử bất biến ở mục 4 đúng trước thao tác:

- **`get` miss:** không thay đổi cấu trúc, bất biến vẫn đúng.
- **`get` hit:** chỉ gỡ một nút đang có và đưa lên đầu. Map vẫn trỏ tới nút ấy, các liên kết vẫn nhất quán. Vì nút vừa được sử dụng, đặt nó ở MRU là đúng.
- **`put` khóa cũ:** vẫn một nút cho khóa, giá trị được cập nhật, thứ tự được làm mới; số lượng không đổi.
- **`put` khóa mới khi chưa đầy:** tạo một khóa và một nút tương ứng, đưa lên MRU. Không có mục cũ bị mất.
- **`put` khóa mới khi đã đầy:** tạo mục MRU mới; mục có lần sử dụng cũ nhất trong những mục cũ vẫn nằm ở `tail.prev`, nên gỡ nó khỏi danh sách và map trả lại đúng tập `C` mục gần đây nhất.
- **`remove`:** xóa cùng một nút khỏi cả map và danh sách, giữ thứ tự tương đối của những nút còn lại.

Suy ra bằng quy nạp theo chuỗi thao tác, dưới giả định các bước được thực hiện trọn vẹn và đúng thứ tự, phần tử bị loại mỗi lần đầy chính là **LRU** theo quy ước đã nêu.

## 9. Những lỗi hiện thực thường gặp

### 9.1. Quên xóa mục khỏi bảng băm khi evict

Đây là lỗi phổ biến nhất. Danh sách đã loại B nhưng map còn `B → nodeB`; lần `get(B)` tiếp theo có thể trả giá trị không còn thuộc bộ đệm hoặc cố gỡ một nút đã bị gỡ.

**Kiểm tra:** sau khi loại một khóa, xác nhận `key` không còn trong map và không còn nút mang khóa đó trong danh sách.

### 9.2. Chỉ xóa liên kết một chiều

Nếu thực hiện `left.next = right` nhưng quên `right.prev = left`, lần thao tác tiếp theo dựa trên `prev` có thể cắt nhầm nút hoặc tạo vòng lặp. Một danh sách đôi phải duy trì **cả hai chiều**.

### 9.3. Cập nhật khóa cũ bằng cách thêm nút mới

Bất biến “một khóa tương ứng đúng một nút” bị phá. Cập nhật `value` trực tiếp vào nút cũ và chuyển nó lên đầu. Số lượng phần tử không thay đổi.

### 9.4. Không tính `get` là lần sử dụng

Nếu `get(A)` hit nhưng không chuyển A về đầu, cấu trúc đã thực hiện FIFO hoặc biến thể khác, không còn là LRU theo quy ước bài này.

### 9.5. Chọn sai đầu loại bỏ

Nếu đầu danh sách là MRU, nút cần evict nằm **trước tail**, không phải **sau head**. Chỉ cần đảo chiều quy ước trong một hàm có thể khiến bộ đệm loại mục mới dùng nhất.

### 9.6. Xử lý sai `capacity = 0` hoặc `capacity = 1`

Với `C=0`, mọi `put` phải để bộ đệm rỗng. Với `C=1`, thêm khóa khác sẽ loại khóa cũ, nhưng cập nhật **chính khóa hiện có** không được làm số lượng thành 2.

### 9.7. Nhầm miss với giá trị `None`/`null`

Nếu `None` là giá trị hợp lệ, `get` chỉ trả `None` khi miss sẽ không phân biệt được hai trường hợp. Có thể trả cặp `(found,value)`, kiểu `Option/Maybe` hoặc dùng sentinel không trùng dữ liệu.

### 9.8. Dùng con trỏ/nút sau khi xóa

Sau evict hoặc remove, không được dùng lại nút bị loại qua tham chiếu cũ mà không có hợp đồng vòng đời rõ ràng. Cấu trúc phải quản lý giải phóng bộ nhớ thích hợp; trong ngôn ngữ có cấp phát thủ công còn phải tránh dùng con trỏ đã giải phóng.

### 9.9. Giữ con trỏ trong map nhưng thay nút khi move

Mấu chốt của thiết kế là **di chuyển nút bằng thay liên kết**, giữ nguyên đối tượng/nút mà map trỏ tới. Nếu tạo nút mới khi chạm, phải đồng bộ mọi tham chiếu; cách đó phức tạp và dễ lỗi hơn.

## 10. Từ bộ đệm học tập đến sản phẩm thực tế

Cấu trúc map + danh sách đôi là lõi của LRU, nhưng một cache thực tế thường có yêu cầu bổ sung.

### 10.1. Đồng thời: mọi truy cập hit đều là một thao tác ghi

Vì `get` hit thay đổi thứ tự danh sách, đó **không phải thao tác chỉ đọc**. Nếu hai luồng đồng thời chạy `get(A)` và `put(B)` mà không đồng bộ, các phép gán `prev`/`next` có thể chen nhau làm hỏng liên kết, ngay cả khi hash map của thư viện cho phép đọc đồng thời.

Có thể dùng khóa bảo vệ **cả map và danh sách** trong mỗi thao tác, hoặc thiết kế sharding/thuật toán đồng thời chuyên dụng có hợp đồng rõ ràng. Cần phân tích tính nguyên tử quan sát được: không luồng nào nhìn thấy mục nằm ở map nhưng bị gỡ khỏi danh sách trong trạng thái dở dang.

Việc dùng lock làm phát sinh chi phí và tranh chấp; khi số luồng rất cao, một khóa toàn cục có thể trở thành điểm nghẽn. Lúc đó có thể phải chấp nhận LRU gần đúng, phân vùng cache hoặc chính sách thay thế khác.

### 10.2. Dung lượng theo byte: một mục không bằng một mục

Nếu có một ảnh 10 MB và một kết quả JSON 1 KB, giới hạn “100 mục” không bảo đảm mức dùng RAM.

Với cache có trọng số `weight(value)`:

```text
currentWeight = tổng trọng số của mọi mục đang lưu
budget = giới hạn số byte / trọng số

sau khi thêm hoặc sửa:
    while currentWeight > budget:
        evictLRU()
```

Bất biến mới: `currentWeight` phải bằng đúng tổng trọng số các mục còn lưu và không vượt `budget` sau mỗi thao tác hoàn tất. Một lần thêm mục lớn có thể buộc loại **nhiều** mục nên chi phí của lời gọi không còn luôn `O(1)` theo số mục, dù mỗi lần evict một mục vẫn có thể kỳ vọng `O(1)`.

Phải có chính sách cho mục lớn hơn cả ngân sách: từ chối cache, chỉ giữ ngoài cache, hoặc cách xử lý khác được định nghĩa rõ.

### 10.3. TTL và hết hạn khác với LRU

**Time To Live (TTL)** loại một mục khi đã quá thời hạn. **LRU** loại khi thiếu dung lượng, dựa trên mức độ gần đây. Một mục có thể vừa được truy cập nhưng đã hết TTL; hoặc là mục ít dùng nhất nhưng chưa hết TTL.

Khi ghép TTL với LRU, cần xác định liệu `get` có kiểm tra hết hạn trước khi coi là hit, cách thu gom mục hết hạn và có thêm chỉ mục theo thời gian hay không. Không thể nói “đã có LRU thì tự động có TTL”.

### 10.4. Cache miss có thể kéo theo tải dữ liệu đắt

Một API cache thực tế thường triển khai thêm `load(key)` từ cơ sở dữ liệu/đĩa/mạng khi miss. **Độ phức tạp `O(1)` của quản lý LRU không tính chi phí tải dữ liệu**.

Nếu nhiều luồng cùng miss một khóa, có thể phát sinh *cache stampede*: tất cả cùng tải dữ liệu đắt. Single-flight, khóa theo khóa hoặc chính sách hợp nhất yêu cầu có thể cần thiết. Đây là bài toán điều phối nạp dữ liệu, khác với duy trì thứ tự LRU.

### 10.5. LRU có thể không phải chính sách hit rate tốt nhất

Nếu luồng truy cập quét qua một tập dữ liệu lớn hơn `C` nhiều lần, mỗi mục mới sẽ đẩy mục cũ, khiến LRU gặp **scan pollution** và tỷ lệ hit thấp. Với tải phân bố lệch hoặc có tính chu kỳ, LFU, segmented LRU, 2Q, ARC hoặc những chính sách thay thế khác có thể phù hợp hơn tùy yêu cầu và cách cài đặt.

Việc chọn chính sách nên dựa vào **hit rate**, chi phí miss, dung lượng cache, độ phức tạp cập nhật và hành vi của tải công việc thực tế. LRU đơn giản, dễ hiểu và hỗ trợ một tập thao tác đẹp về độ phức tạp, nhưng không đảm bảo tỷ lệ hit tối ưu cho mọi chuỗi truy cập.

## 11. Lập bảng so sánh với các cách thiết kế khác

| Thiết kế | Tìm theo khóa | Đưa mục vừa dùng lên MRU | Loại mục LRU | Bộ nhớ phụ và giới hạn |
| --- | --- | --- | --- | --- |
| Mảng không có chỉ mục, sắp theo lần dùng | `O(C)` nếu quét | Có thể `O(C)` vì dời phần tử | `O(1)` nếu LRU ở cuối | Liền kề, đơn giản, nhưng truy cập chậm |
| Danh sách liên kết đôi đơn lẻ | `O(C)` để tìm khóa | `O(1)` sau khi tìm thấy nút | `O(1)` | Mỗi nút có liên kết; chưa giải quyết tra cứu |
| Hash map đơn lẻ | Kỳ vọng `O(1)` | Không có cấu trúc thứ tự LRU trực tiếp | Thường phải quét `O(C)` hoặc bổ sung metadata | Tra cứu nhanh nhưng thiếu thông tin thứ tự |
| **Hash map + danh sách đôi** | **Kỳ vọng `O(1)`** | **`O(1)`** | **Kỳ vọng `O(1)`** kể cả xóa map | **`O(C)`** cho nút và chỉ mục, cần duy trì bất biến |
| Cây tìm kiếm theo thời điểm sử dụng + map | Kỳ vọng `O(1)` để tìm qua map | Thay khóa trong cây `O(log C)` | Lấy/xóa cực trị `O(log C)` | Hữu ích nếu cần truy vấn có thứ tự thời điểm khác, nhưng nặng hơn LRU đơn thuần |

Với **hai phép toán chủ đạo là tìm theo khóa và cập nhật thứ tự sử dụng**, giải pháp map + danh sách đôi có tính cân bằng tốt: không cần sắp toàn bộ các khóa theo timestamp và không cần quét để tìm nút cần di chuyển.

Cấu trúc phối hợp này còn xuất hiện trong bài toán **LRU cache theo dung lượng mục**, danh sách lịch sử có giới hạn và một số cơ chế giữ thứ tự truy cập. Mỗi khi dùng lại, cần xác định đúng quy tắc “sử dụng” của ứng dụng.

## 12. Bài tập tự kiểm tra

### Bài 1 — Theo dõi thứ tự và mục bị loại

Cache có `C=2`, bắt đầu rỗng:

```text
put(X,1)
put(Y,2)
get(X)
put(Z,3)
get(Y)
```

**Hỏi:** mỗi thao tác tạo thứ tự MRU → LRU nào? Lần `get(Y)` cuối hit hay miss?

*Đáp án:* `[X]` → `[Y,X]` → `[X,Y]` → `[Z,X]` (loại Y) → `[Z,X]`. Lần `get(Y)` cuối là **miss**.

### Bài 2 — Tìm lỗi bất biến

Hàm evict chỉ làm:

```text
victim = tail.prev
detach(victim)
```

**Hỏi:** còn thiếu bước nào? Sau đó `get(victim.key)` có nguy cơ gì?

*Đáp án:* thiếu xóa `index[victim.key]`. Map có thể trỏ tới nút đã bị gỡ, tạo kết quả hit giả và thao tác trên liên kết không hợp lệ.

### Bài 3 — Tại sao danh sách đơn không tiện?

Giả sử `index[key]` trỏ tới nút của một danh sách liên kết đơn, nhưng nút không biết nút trước. Khi `get(key)` hit, cần chuyển nút đó lên đầu. Vì sao không thể khẳng định gỡ nút tùy ý luôn `O(1)` nếu không có thông tin bổ sung?

*Đáp án:* phải sửa `next` của nút ngay trước nút được gỡ. Nếu không biết predecessor, có thể phải quét từ đầu mất `O(C)`. Danh sách đôi lưu sẵn `prev` để thao tác `O(1)` sau khi đã tìm nút.

### Bài 4 — Cập nhật khác thêm mới

Bộ đệm có `C=3` và thứ tự `[C,B,A]`. Gọi `put(B,99)`.

*Đáp án:* danh sách trở thành `[B,C,A]` và chỉ có ba nút; giá trị của B thành 99. Không evict A vì không thêm khóa mới.

### Bài 5 — Giới hạn theo byte

Một cache có tổng trọng số hiện tại 90 trên ngân sách 100. Thêm mục mới trọng số 50; các mục cũ có trọng số 10, 20, 60 từ LRU → MRU. Giả sử không có khóa trùng.

*Đáp án:* tổng ban đầu sau thêm là 140; cần loại mục trọng số 10 rồi 20 rồi 60 theo thứ tự LRU đến khi còn 50 ≤ 100. Việc thêm mục lớn có thể loại nhiều mục, nên thời gian của lời gọi theo số mục bị loại có thể tăng.

### Bài 6 — Chọn cấu trúc phù hợp

Ứng dụng có `C=10.000` mục và thực hiện hàng triệu `get(key)`; mỗi hit phải chuyển mục lên MRU. Vì sao chỉ lưu một mảng với thứ tự sử dụng chưa phù hợp? Phương án nào cần thêm bất biến?

*Gợi ý:* mảng phải tìm khóa/quản lý dịch phần tử, có thể tốn `O(C)` mỗi hit. Hash map + danh sách đôi giúp tìm nút kỳ vọng `O(1)` và di chuyển `O(1)`, nhưng cần kiểm tra map và danh sách chứa đúng cùng một tập nút với liên kết hai chiều hợp lệ.

### Bài 7 — Kiểm chứng độ phức tạp

Một người nói: “`get` và `put` trong LRU này đều `O(1)` trường hợp xấu vì chỉ đổi vài con trỏ.” Nhận định có đầy đủ không?

*Đáp án:* không. Phần đổi con trỏ `O(1)`, nhưng tra cứu/chèn/xóa bảng băm có thể gặp va chạm, và thao tác thêm có thể kích hoạt rehash. Bảo đảm thông dụng là **kỳ vọng `O(1)`** cho `get` và **kỳ vọng khấu hao `O(1)`** cho `put` mới, theo các giả định phù hợp.

## 13. Checklist trước khi sử dụng

Trước khi dùng một hiện thực LRU trong chương trình, hãy kiểm tra:

- **Hợp đồng:** `get` hit có tính là lần dùng mới? `put` khóa cũ có cập nhật recency? Có `peek` hoặc `remove` không? Cách biểu diễn miss là gì?
- **Dung lượng:** xử lý `C=0`, `C=1`, mục lớn hơn ngân sách và thời điểm kiểm tra vượt sức chứa.
- **Bất biến:** mỗi khóa có một nút; map và danh sách chứa cùng tập mục; liên kết `prev/next` hợp lệ; đầu là MRU, cuối là LRU.
- **Vòng đời:** sau evict/remove không còn tham chiếu stale trong map; khóa dùng để hash không đổi khi đang được lưu.
- **Thời gian và bộ nhớ:** tra map kỳ vọng `O(1)`, thao tác danh sách `O(1)`; bộ nhớ `O(C)` cộng dung lượng giá trị; cân nhắc resize và cấp phát.
- **Đồng thời:** mọi chỉnh sửa map và liên kết của cùng một lần truy cập phải được đồng bộ theo hợp đồng; không chia sẻ nút bị xóa một cách không an toàn.
- **Đúng tải công việc:** đo hit rate, miss cost, p95/p99 latency và bộ nhớ đỉnh nếu hệ thống yêu cầu; kiểm tra tính phù hợp của LRU với chuỗi truy cập thực tế.

Một chiến lược kiểm thử hữu ích là dùng một **mô hình tham chiếu đơn giản nhưng chậm**, chẳng hạn mảng khóa giữ thứ tự MRU → LRU. Sinh các chuỗi `get`/`put`/`remove` hợp lệ rồi so nội dung và thứ tự của mô hình với hiện thực map + danh sách đôi sau từng bước. Mô hình tham chiếu có thể mất `O(C)` cho mỗi thao tác, nhưng thuận tiện để phát hiện lỗi liên kết hoặc quên cập nhật map trong kiểm thử trên bộ đệm nhỏ.

## Kết luận

Bộ đệm LRU là ví dụ điển hình cho việc **kết hợp cấu trúc dữ liệu theo phép toán chủ đạo**. Bảng băm tìm nhanh nút theo khóa; danh sách liên kết đôi gỡ/chèn nhanh nút đã biết; hai sentinel đơn giản hóa xử lý biên. Khi cùng giữ bất biến ánh xạ một–một và thứ tự MRU → LRU, các thao tác `get`, `put` và loại bỏ có chi phí **kỳ vọng hằng số** trong mô hình phù hợp, với bộ nhớ phụ tuyến tính theo dung lượng.

Điều phải giữ không chỉ là ký hiệu `O(1)`, mà còn là **ngữ nghĩa lần sử dụng, tính nhất quán giữa map và danh sách, vòng đời nút và chính sách khi đầy**. Với hệ thống thực tế, bổ sung yêu cầu đồng thời, TTL, trọng số bộ nhớ và đo hit rate sẽ quyết định liệu LRU đơn giản có đủ hay cần một chiến lược thay thế khác.
