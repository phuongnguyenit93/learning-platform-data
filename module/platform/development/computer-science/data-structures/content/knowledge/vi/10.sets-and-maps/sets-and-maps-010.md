# Cài đặt tập hợp hoặc ánh xạ bằng mảng, danh sách, bảng băm và cây

Giả sử nền tảng học tập cần lưu **mã học viên → điểm số** và trả lời bốn câu hỏi: mã này đã có chưa, điểm hiện tại là bao nhiêu, làm thế nào để cập nhật điểm, và cách xóa một hồ sơ. Ta có thể cài chức năng ấy bằng **mảng**, **danh sách liên kết**, **bảng băm** hoặc **cây tìm kiếm**. Các cách cài đặt mang lại **cùng một hành vi logic**, nhưng đánh đổi khác nhau về thời gian, bộ nhớ và thứ tự duyệt.

Trong chương **Tập hợp và ánh xạ** của module cấu trúc dữ liệu, mục tiêu của bài này là nối **kiểu dữ liệu trừu tượng (ADT)** với **cấu trúc lưu trữ thực tế**. Người học sẽ hiểu bất biến cần bảo toàn, tự cài các thao tác cơ bản và đánh giá khi nào cấu trúc nào thích hợp. Kiến thức này cũng là cầu nối giữa mảng, danh sách liên kết, bảng băm, cây và ứng dụng như danh sách kề đồ thị.

## 1. Phân biệt ADT với cấu trúc cài đặt

**Set ADT** biểu diễn một tập các phần tử phân biệt. Các thao tác tiêu biểu: `contains(x)`, `add(x)`, `remove(x)`, `size()`.

**Map ADT** biểu diễn các cặp `khóa → giá trị`, trong đó mỗi khóa phân biệt có **tối đa một giá trị tại một thời điểm**. Các thao tác tiêu biểu: `containsKey(k)`, `get(k)`, `put(k, v)`, `remove(k)`, `size()`.

Đây là các **hợp đồng hành vi**; chúng chưa quyết định dữ liệu phải nằm ở đâu trong bộ nhớ:

| Câu hỏi | Set | Map |
| --- | --- | --- |
| Phải giữ bất biến gì? | Mỗi phần tử phân biệt chỉ có một lần | Mỗi khóa phân biệt gắn tối đa một giá trị |
| Thêm một phần tử/khóa đã có? | Không làm tăng kích thước | `put` thường cập nhật giá trị; `insert` nghiêm ngặt có thể từ chối |
| Tra cứu để làm gì? | Hỏi có mặt hay không | Hỏi có khóa và giá trị tương ứng |
| Có bắt buộc phải có thứ tự? | Không, xét ở mức ADT cơ bản | Không, xét ở mức ADT cơ bản |
| Cài bằng gì? | Mảng, danh sách, hash set, cây… | Mảng cặp, danh sách nút, hash map, tree map… |

Một cách suy nghĩ hữu ích: **Set có thể cài trên Map**, dùng phần tử làm khóa và một giá trị đánh dấu không mang ý nghĩa nghiệp vụ. Bằng cách ấy, những cấu trúc cài `Map<K, V>` cũng có thể hỗ trợ cài set.

```text
Set: {"HV01", "HV02"}

Cài bằng map đánh dấu:
  "HV01" → true
  "HV02" → true
```

Giá trị đánh dấu không cần khác nhau; điều quan trọng là **sự hiện diện của khóa**.

### Một hợp đồng thao tác thống nhất

Trong các ví dụ bên dưới, ta chọn cách hiểu:

- `put(k, v)`: nếu khóa chưa có thì **thêm**, nếu đã có thì **thay giá trị cũ**.
- `find(k)`: trả `(True, v)` khi tìm thấy, `(False, None)` khi không có khóa.
- `remove(k)`: trả `True` nếu đã xóa một khóa, ngược lại trả `False`.
- `size()`: trả số khóa phân biệt.

Kết quả có cờ `found` giúp phân biệt **khóa vắng mặt** với **khóa tồn tại có giá trị `None`**. Những kiểu thư viện thực tế có thể dùng tên hoặc kiểu kết quả khác.

## 2. Bất biến chung khi chọn cách lưu trữ

Bất kể hiện thực nào, một map đúng phải giữ được:

1. **Tính duy nhất của khóa:** không có hai cặp độc lập có khóa được xem là bằng nhau.
2. **Tính nhất quán:** nếu `find(k)` thành công, nó trả giá trị đang gắn với `k`.
3. **Tính đúng đắn của cập nhật:** `put(k, newValue)` trên khóa có sẵn không tăng `size()`.
4. **Tính đúng đắn của xóa:** sau `remove(k)` thành công, `find(k)` phải báo thiếu; các khóa khác còn nguyên.
5. **Quy tắc trùng khóa ổn định:** phép bằng nhau, hàm băm hoặc bộ so sánh phải nhất quán với cấu trúc được chọn.

Ví dụ với mã học viên:

| Thao tác | Trạng thái logic | Số khóa |
| --- | --- | ---: |
| Ban đầu | `{}` | 0 |
| `put("HV01", 7)` | `{"HV01": 7}` | 1 |
| `put("HV02", 8)` | `{"HV01": 7, "HV02": 8}` | 2 |
| `put("HV01", 9)` | `{"HV01": 9, "HV02": 8}` | 2 |
| `remove("HV02")` | `{"HV01": 9}` | 1 |

Nếu chương trình lưu bản ghi mới mà không kiểm tra khóa cũ, nó có thể phá vỡ bất biến dù các thao tác thêm vào cấu trúc nền đều chạy thành công.

## 3. Cài Map bằng mảng chưa sắp xếp

Cách trực tiếp nhất là lưu một **mảng các cặp khóa–giá trị**. Trong Python, `list` là mảng động và rất phù hợp để minh họa:

```text
Vị trí:   0              1              2
        ┌─────────────┬─────────────┬─────────────┐
Mảng:   │ ("B", 20)   │ ("A", 10)   │ ("C", 30)   │
        └─────────────┴─────────────┴─────────────┘
```

Muốn tìm khóa `"A"`, ta duyệt từ đầu cho đến khi gặp cặp có khóa bằng `"A"`. Mảng **chưa sắp xếp** không cung cấp một cách tìm nhị phân theo khóa.

### Mã Python minh họa

```python
class UnsortedArrayMap:
    def __init__(self):
        self._items = []                 # [(key, value), ...]

    def _find_index(self, key):
        for index, (old_key, _) in enumerate(self._items):
            if old_key == key:
                return index
        return -1

    def find(self, key):
        index = self._find_index(key)
        if index == -1:
            return False, None
        return True, self._items[index][1]

    def put(self, key, value):
        index = self._find_index(key)
        if index == -1:
            self._items.append((key, value))
            return True                  # Vừa thêm khóa mới
        self._items[index] = (key, value)
        return False                     # Đã cập nhật

    def remove(self, key):
        index = self._find_index(key)
        if index == -1:
            return False
        self._items.pop(index)
        return True

    def size(self):
        return len(self._items)


grades = UnsortedArrayMap()
assert grades.put("B", 20) is True
assert grades.put("A", 10) is True
assert grades.put("A", 15) is False
assert grades.size() == 2
assert grades.find("A") == (True, 15)
assert grades.find("X") == (False, None)
assert grades.remove("B") is True
assert grades.size() == 1
```

### Phân tích

Gọi `n` là số khóa phân biệt.

- **Tra cứu:** có thể duyệt hết `n` cặp → `O(n)`.
- **Thêm mới:** nếu phải bảo đảm khóa không trùng, trước hết phải kiểm tra mảng → `O(n)`; sau đó `append` thường có chi phí **khấu hao `O(1)`**.
- **Cập nhật:** tìm khóa `O(n)`, thay giá trị tại vị trí tìm được `O(1)` → tổng `O(n)`.
- **Xóa:** tìm `O(n)`; `pop(index)` có thể dịch nhiều phần tử → `O(n)`.
- **Bộ nhớ:** `O(n)` cặp.

Nếu **không cần giữ thứ tự** trong mảng, thao tác xóa sau khi đã tìm được vị trí có thể thay mục cần xóa bằng **mục cuối**, rồi bỏ mục cuối. Khi đó phần xử lý sau bước tìm chỉ còn `O(1)`, nhưng **toàn bộ xóa theo khóa** vẫn là `O(n)` vì phải tìm khóa.

Mảng chưa sắp xếp phù hợp với **tập dữ liệu nhỏ**, việc cài đặt cần đơn giản hoặc các thao tác cần duyệt toàn bộ nhiều hơn tra cứu riêng lẻ.

## 4. Cài Map bằng mảng đã sắp xếp

Nếu các cặp luôn được giữ **theo thứ tự tăng dần của khóa**, ta có thể dùng **tìm kiếm nhị phân**:

```text
Vị trí:   0              1              2              3
        ┌─────────────┬─────────────┬─────────────┬─────────────┐
Mảng:   │ ("A", 10)   │ ("B", 20)   │ ("C", 30)   │ ("D", 40)   │
        └─────────────┴─────────────┴─────────────┴─────────────┘
                         ↑ tìm B bằng cách thu hẹp khoảng
```

**Bất biến bổ sung:** khóa tại mọi vị trí phải sắp tăng dần theo cùng một quy tắc so sánh. Muốn chèn một khóa ở giữa, phải **dịch các phần tử sang phải**; muốn xóa, thường phải **dịch sang trái**.

### Tìm vị trí chèn bằng lower bound

Với khóa là chuỗi hoặc số có phép so sánh nhất quán:

```python
class SortedArrayMap:
    def __init__(self):
        self._items = []

    def _lower_bound(self, key):
        """Vị trí đầu tiên có khóa >= key."""
        lo, hi = 0, len(self._items)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._items[mid][0] < key:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def find(self, key):
        i = self._lower_bound(key)
        if i < len(self._items) and self._items[i][0] == key:
            return True, self._items[i][1]
        return False, None

    def put(self, key, value):
        i = self._lower_bound(key)
        if i < len(self._items) and self._items[i][0] == key:
            self._items[i] = (key, value)
            return False
        self._items.insert(i, (key, value))
        return True

    def remove(self, key):
        i = self._lower_bound(key)
        if i == len(self._items) or self._items[i][0] != key:
            return False
        self._items.pop(i)
        return True

    def items(self):
        return list(self._items)


m = SortedArrayMap()
m.put("C", 30)
m.put("A", 10)
m.put("B", 20)
m.put("B", 25)

assert m.items() == [("A", 10), ("B", 25), ("C", 30)]
assert m.find("B") == (True, 25)
assert m.remove("A")
assert m.items() == [("B", 25), ("C", 30)]
```

**Tại sao không chỉ dùng `bisect` trên `list` các cặp?** Có thể dùng thư viện tìm nhị phân nếu cấu trúc và hàm lấy khóa phù hợp; ví dụ tự viết `_lower_bound` giúp làm rõ rằng tiêu chí so sánh là **khóa**, không phải giá trị của cặp.

### Đánh đổi chính

- **Tìm khóa:** `O(log n)` qua tìm nhị phân.
- **Cập nhật khóa có sẵn:** tìm `O(log n)`, thay tại chỗ `O(1)`.
- **Chèn/xóa:** tìm `O(log n)` nhưng phải dịch phần tử tối đa `O(n)` → tổng `O(n)`.
- **Duyệt theo khóa tăng dần:** `O(n)` vì mảng đã sắp.
- **Truy vấn một khoảng khóa:** tìm điểm bắt đầu `O(log n)`, rồi duyệt `k` mục → `O(log n + k)`.
- **Bộ nhớ:** `O(n)`.

Mảng đã sắp thường hợp với dữ liệu **đọc nhiều, sửa ít** hoặc có số phần tử ổn định. Nó có lợi thế truy cập phần tử theo chỉ số và bộ nhớ liên tục, nhưng kém linh hoạt khi thường xuyên chèn giữa mảng.

## 5. Trường hợp đặc biệt: mảng địa chỉ trực tiếp

Nếu khóa là các số nguyên trong miền nhỏ, đã biết trước, chẳng hạn `0…1000`, ta có thể dùng **khóa chính là chỉ số mảng**. Khi đó không cần tìm tuần tự hoặc tính hash.

```text
Khóa:       0      1      2      3
Mảng:    [EMPTY, "An", EMPTY, "Bình", ...]
                 ↑           ↑
               key=1       key=3
```

### Phải phân biệt ô trống với giá trị hợp lệ

Nếu `None` có thể là giá trị được lưu, không thể dùng `None` để chỉ ô chưa có. Một **sentinel** độc nhất giải quyết sự nhập nhằng:

```python
EMPTY = object()
MAX_ID = 5
table = [EMPTY] * (MAX_ID + 1)

table[1] = None
table[3] = "Bình"

assert table[1] is not EMPTY       # Khóa 1 tồn tại, giá trị None
assert table[2] is EMPTY           # Khóa 2 chưa tồn tại
assert table[3] == "Bình"

def find_direct(key):
    if not (0 <= key <= MAX_ID):
        return False, None
    value = table[key]
    if value is EMPTY:
        return False, None
    return True, value

assert find_direct(1) == (True, None)
assert find_direct(2) == (False, None)
```

**Giới hạn lớn nhất là bộ nhớ:** nếu miền khóa có `U` giá trị khả dĩ, cần `O(U)` ô, dù chỉ có `n` khóa đang thực sự xuất hiện. Tra cứu, gán và xóa một khóa hợp lệ đều có thể `O(1)`, nhưng duyệt mọi khóa đang có bằng cách quét toàn mảng có thể tốn `O(U)`.

Mảng địa chỉ trực tiếp rất phù hợp với **miền khóa nguyên nhỏ và dày**, nhưng không hợp lý khi dùng mã định danh cực lớn, thưa hoặc là chuỗi tùy ý.

## 6. Cài Map bằng danh sách liên kết

Thay vì đặt các cặp liền nhau trong mảng, ta có thể dùng **danh sách liên kết đơn**: mỗi nút chứa khóa, giá trị và tham chiếu tới nút kế tiếp.

```text
head
 │
 ▼
("B", 20) → ("A", 10) → ("C", 30) → None
```

Khi tìm `"C"`, phải đi lần lượt qua các nút. Tuy nhiên, sau khi biết **nút đứng trước vị trí cần xóa**, việc nối lại các liên kết có thể chỉ cần `O(1)` thao tác con trỏ, không phải dịch cả đoạn mảng.

### Python minh họa

```python
class Node:
    def __init__(self, key, value, next_node=None):
        self.key = key
        self.value = value
        self.next = next_node


class LinkedMap:
    def __init__(self):
        self.head = None
        self._size = 0

    def find(self, key):
        node = self.head
        while node is not None:
            if node.key == key:
                return True, node.value
            node = node.next
        return False, None

    def put(self, key, value):
        node = self.head
        while node is not None:
            if node.key == key:
                node.value = value
                return False
            node = node.next

        self.head = Node(key, value, self.head)
        self._size += 1
        return True

    def remove(self, key):
        prev = None
        node = self.head
        while node is not None:
            if node.key == key:
                if prev is None:
                    self.head = node.next
                else:
                    prev.next = node.next
                self._size -= 1
                return True
            prev, node = node, node.next
        return False

    def size(self):
        return self._size


linked = LinkedMap()
assert linked.put("A", 10)
assert linked.put("B", 20)
assert linked.put("A", 15) is False
assert linked.find("A") == (True, 15)
assert linked.remove("B")
assert linked.find("B") == (False, None)
assert linked.size() == 1
```

Hàm `put` ở đây **chèn đầu danh sách** nếu khóa mới. Vì vậy thứ tự duyệt các nút là **ngược thứ tự chèn mới** (nếu không có xóa và chèn lại), không phải thứ tự sắp xếp khóa. Nếu cần bảo đảm thứ tự chèn, có thể duy trì thêm con trỏ `tail` và chèn cuối.

### Chi phí

Với danh sách liên kết chưa sắp và `n` khóa:

- Tra cứu, cập nhật theo khóa: `O(n)` vì phải đi tìm nút.
- Thêm khóa mới có kiểm tra trùng: `O(n)` do bước tìm, dù việc gắn nút mới vào đầu là `O(1)`.
- Xóa theo khóa: `O(n)` để tìm; thay đổi con trỏ sau khi tìm được nút là `O(1)`.
- Duyệt mọi mục: `O(n)`.
- Bộ nhớ: `O(n)` nút nhưng **mỗi nút có chi phí con trỏ và cấp phát riêng**.

Danh sách liên kết không mặc nhiên nhanh hơn mảng. Nó hữu ích khi thao tác cấu trúc cần nối/xóa nút ở vị trí đã biết, hoặc khi muốn hiện thực các cấu trúc như **bucket của hash table theo separate chaining**.

## 7. Cài Map bằng bảng băm (hash table)

Bảng băm (*hash table*) xử lý vấn đề tra cứu `O(n)` của mảng/danh sách chưa sắp bằng cách **tính chỉ số từ khóa**:

```text
                   hash(key) % capacity
   khóa "A"  ────────────────────────┐
                                     ▼
Buckets:       0         1         2         3
             [ ... ]   [ ... ]   [ ... ]   [ ... ]
```

Bảng có `capacity` vị trí hoặc **bucket**. Hàm `hash(key)` giúp chọn bucket cần kiểm tra. Khi các khóa phân bố hợp lý và bảng không quá đầy, chỉ cần kiểm tra số ít mục trong một bucket.

### Va chạm băm và quy tắc bằng nhau

Hai khóa khác nhau vẫn có thể được ánh xạ vào cùng bucket. Đây là **va chạm băm**, không phải khóa trùng.

- Hai khóa `k1`, `k2` **bằng nhau** phải có hash tương thích: `k1 == k2 ⇒ hash(k1) == hash(k2)`.
- Hai khóa có hash bằng nhau **chưa chắc bằng nhau**.
- Khi phát hiện khóa thực sự bằng nhau, `put` phải **thay giá trị**, không thêm mục trùng.

Một cách xử lý va chạm là **separate chaining**: mỗi bucket lưu một danh sách các cặp khóa–giá trị:

```text
bucket 0:  ("A", 10) → ("D", 40)
bucket 1:  ("B", 20)
bucket 2:  (rỗng)
bucket 3:  ("C", 30) → ("E", 50)
```

Nếu nhiều khóa dồn vào một bucket, việc duyệt bucket đó trở nên chậm. Vì vậy **chất lượng phân bố hash** và **hệ số tải** đều quan trọng.

### Ví dụ bảng băm có bucket dạng list và tự mở rộng

Ví dụ sau nhằm minh họa ý tưởng, **không phải một phiên bản tối ưu để thay thế Python `dict`**:

```python
class ChainedHashMap:
    def __init__(self, capacity=8):
        if capacity < 1:
            raise ValueError("capacity phải dương")
        self._buckets = [[] for _ in range(capacity)]
        self._size = 0

    def _index(self, key):
        return hash(key) % len(self._buckets)

    def find(self, key):
        for existing_key, value in self._buckets[self._index(key)]:
            if existing_key == key:
                return True, value
        return False, None

    def put(self, key, value):
        bucket = self._buckets[self._index(key)]
        for i, (existing_key, _) in enumerate(bucket):
            if existing_key == key:
                bucket[i] = (existing_key, value)
                return False

        bucket.append((key, value))
        self._size += 1

        # Mở rộng bảng khi số khóa / số bucket vượt 0.75.
        if self._size > len(self._buckets) * 0.75:
            self._resize()
        return True

    def _resize(self):
        old_buckets = self._buckets
        self._buckets = [[] for _ in range(2 * len(old_buckets))]
        for bucket in old_buckets:
            for key, value in bucket:
                self._buckets[self._index(key)].append((key, value))

    def remove(self, key):
        bucket = self._buckets[self._index(key)]
        for i, (existing_key, _) in enumerate(bucket):
            if existing_key == key:
                bucket.pop(i)
                self._size -= 1
                return True
        return False

    def size(self):
        return self._size


grades = ChainedHashMap(capacity=2)
assert grades.put("HV01", None) is True
assert grades.put("HV02", 8.0) is True
assert grades.put("HV01", 9.0) is False
assert grades.find("HV01") == (True, 9.0)
assert grades.find("HV99") == (False, None)
assert grades.size() == 2
assert grades.remove("HV02") is True
assert grades.size() == 1
```

Bất biến quan trọng sau mỗi thao tác:

1. Mỗi cặp nằm trong bucket phù hợp với `hash(key) % capacity` hiện tại.
2. Mỗi khóa phân biệt xuất hiện tối đa một lần trong toàn bảng.
3. `_size` bằng tổng số mục trong các bucket.
4. Sau khi **resize**, mọi mục phải được **phân bố lại**, vì modulo theo `capacity` mới có thể khác trước.

Trong `_resize` trên, các cặp được chèn trực tiếp vào bucket mới và `_size` **không bị tăng lần nữa**. Nếu sơ ý gọi một thao tác thêm mới mà không quản lý đúng biến đếm, việc tái băm có thể làm sai kích thước.

### Hệ số tải và chi phí

Đặt `n` là số khóa và `b` là số bucket. **Hệ số tải** là:

```text
α = n / b
```

Với separate chaining, một phân tích kỳ vọng điển hình cho chi phí tra cứu là `O(1 + α)` khi hàm băm phân bố đều. Nếu chiến lược mở rộng giữ `α` bị chặn trên bởi một hằng số hợp lý, các thao tác tra cứu, chèn và xóa có thời gian **trung bình/kỳ vọng `O(1)`** (giả định chi phí hash/equality cơ bản là hằng số).

Một lần **tái băm** có thể tốn `O(n)` vì phải di chuyển các mục. Tuy vậy, nếu dung lượng được tăng theo cấp số nhân và các mục được phân bố lại hợp lý, chi phí **chèn trung bình khấu hao** trên một chuỗi dài thao tác vẫn thường là `O(1)`.

Tình huống xấu nhất có thể `O(n)` khi nhiều khóa cùng va chạm hoặc khi một thao tác kích hoạt resize; không nên khẳng định hash map luôn `O(1)` trong mọi trường hợp.

### Open addressing: lựa chọn khác với separate chaining

Bảng băm còn có thể xử lý va chạm bằng **open addressing**: các cặp nằm ngay trong một mảng ô, và khi ô mong muốn đã bận, thuật toán sẽ thăm dò những ô khác theo một quy tắc, chẳng hạn linear probing.

```text
hash(k) → ô 2 đã bận → thử ô 3 → thử ô 4 → ...
```

Khi xóa ở một số cách open addressing, cần dùng dấu **đã xóa** (*tombstone*) hoặc dịch các mục thích hợp để không làm hỏng đường thăm dò. Việc tùy tiện xóa một mục rồi biến ô đó thành “chưa từng có dữ liệu” có thể khiến những mục nằm phía sau không còn tìm được.

Chaining và open addressing đều có thể cài Map/Set, nhưng khác nhau về bố trí bộ nhớ, hệ số tải tối ưu, tính cục bộ cache và cách xử lý xóa. Python `dict` là một hiện thực bảng băm được tối ưu, **không phải** đoạn mã chaining minh họa ở trên.

## 8. Cài Map bằng cây tìm kiếm nhị phân

Một **cây tìm kiếm nhị phân** (*binary search tree*, BST) lưu một khóa–giá trị ở mỗi nút và duy trì bất biến:

- Mọi khóa trong cây con **trái** của nút nhỏ hơn khóa tại nút.
- Mọi khóa trong cây con **phải** lớn hơn khóa tại nút.
- Nếu gặp khóa được xem là **tương đương** với khóa nút, `put` cập nhật giá trị thay vì tạo nút mới.

```text
              ("M", 13)
              /       \
         ("F", 6)    ("T", 20)
         /     \           \
      ("C",3) ("J",10)    ("Z",26)
```

Khác với bảng băm, cây có thứ tự cho phép **duyệt khóa theo thứ tự tăng dần** bằng phép duyệt trung thứ tự (*in-order traversal*).

### BST đơn giản bằng Python

```python
class BSTNode:
    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.left = None
        self.right = None


class BSTMap:
    def __init__(self):
        self.root = None
        self._size = 0

    def put(self, key, value):
        if self.root is None:
            self.root = BSTNode(key, value)
            self._size = 1
            return True

        node = self.root
        while True:
            if key == node.key:
                node.value = value
                return False
            if key < node.key:
                if node.left is None:
                    node.left = BSTNode(key, value)
                    break
                node = node.left
            else:
                if node.right is None:
                    node.right = BSTNode(key, value)
                    break
                node = node.right

        self._size += 1
        return True

    def find(self, key):
        node = self.root
        while node is not None:
            if key == node.key:
                return True, node.value
            if key < node.key:
                node = node.left
            else:
                node = node.right
        return False, None

    def items_in_order(self):
        def traverse(node):
            if node is not None:
                yield from traverse(node.left)
                yield (node.key, node.value)
                yield from traverse(node.right)

        return list(traverse(self.root))

    def size(self):
        return self._size


tree = BSTMap()
for key, value in [("M", 13), ("F", 6), ("T", 20),
                   ("C", 3), ("J", 10), ("Z", 26)]:
    tree.put(key, value)

assert tree.find("J") == (True, 10)
assert tree.put("J", 99) is False
assert tree.size() == 6
assert [key for key, _ in tree.items_in_order()] == [
    "C", "F", "J", "M", "T", "Z"
]
```

Đây là **BST chưa tự cân bằng**. Nó minh họa việc chèn, tìm và duyệt, không cung cấp phương thức xóa. Muốn triển khai `remove` cần xử lý ba tình huống:

1. **Nút lá:** bỏ nút.
2. **Nút chỉ có một con:** nối cha trực tiếp tới con đó.
3. **Nút có hai con:** dùng nút kế tiếp theo thứ tự (*in-order successor*) hoặc nút trước theo thứ tự để thay thế, sau đó xóa nút được chuyển.

Sau xóa, mọi thao tác vẫn phải duy trì bất biến thứ tự và số lượng khóa. Với cây cân bằng, còn phải cập nhật thông tin cân bằng và có thể thực hiện phép quay (*rotation*).

### Chiều cao cây quyết định thời gian

Đặt `h` là chiều cao cây. Tìm/chèn/xóa BST đi theo một đường từ gốc xuống nên tốn `O(h)`.

- Với cây **cân đối**, `h = O(log n)`.
- Với BST **không tự cân bằng**, chèn dãy khóa đã sắp như `1, 2, 3, 4, 5` có thể tạo chuỗi dài, `h = O(n)`.

```text
Chèn 1, 2, 3, 4 vào BST thường:

1
 \
  2
   \
    3
     \
      4

Chiều cao tăng theo n ⇒ tìm có thể O(n)
```

Để có giới hạn `O(log n)` cho tìm/chèn/xóa, thường dùng **cây tìm kiếm tự cân bằng** như AVL hoặc cây đỏ–đen. Các hiện thực `TreeMap` của Java và `std::map` của C++ cung cấp thao tác theo thứ tự với chi phí logarit theo hợp đồng thư viện thích hợp.

### Quy tắc so sánh cũng quyết định khóa trùng

Trong cây có thứ tự, hai khóa thường được coi tương đương khi **bộ so sánh không phân biệt chúng**. Nếu so sánh sinh viên chỉ theo điểm số, hai sinh viên có cùng điểm có thể bị gộp trong một tree set, dù mã học viên khác nhau.

Muốn cây lưu đúng định danh nghiệp vụ, hãy chọn bộ so sánh **nhất quán và đủ phân biệt**, ví dụ dùng mã học viên làm khóa, hoặc dùng cặp `(điểm, mã)` nếu cần sắp hạng với tiêu chí phá hòa. Mã ví dụ ở trên dùng `==` và `<` của kiểu khóa Python; với loại khóa tùy chỉnh phải bảo đảm hai phép này nhất quán.

## 9. Dùng cùng các cấu trúc để cài Set

Một set có thể được cài bằng cách lược bỏ phần giá trị của map và giữ **khóa/phần tử phân biệt**:

| Cấu trúc nền | Cách cài Set | Quy tắc tránh trùng |
| --- | --- | --- |
| Mảng chưa sắp | Mảng các phần tử | Tìm tuyến tính trước khi thêm |
| Mảng đã sắp | Mảng phần tử tăng dần | Tìm nhị phân vị trí; chèn nếu chưa có |
| Danh sách liên kết | Mỗi nút giữ một phần tử | Duyệt kiểm tra trước khi nối nút |
| Bảng băm | Mỗi phần tử đóng vai trò khóa | So sánh bằng nhau tại bucket/vị trí thăm dò |
| Cây tìm kiếm | Mỗi nút giữ một phần tử | So sánh theo comparator khi tìm vị trí |

Ví dụ cài set đơn giản dựa trên map:

```python
class SetFromMap:
    def __init__(self):
        self._map = ChainedHashMap()

    def add(self, item):
        return self._map.put(item, True)

    def contains(self, item):
        found, _ = self._map.find(item)
        return found

    def remove(self, item):
        return self._map.remove(item)

    def size(self):
        return self._map.size()


seen = SetFromMap()
assert seen.add("HV01") is True
assert seen.add("HV01") is False
assert seen.add("HV02") is True
assert seen.size() == 2
assert seen.contains("HV02")
assert seen.remove("HV01")
assert not seen.contains("HV01")
```

Trong ví dụ này, `SetFromMap` tái sử dụng `ChainedHashMap` đã định nghĩa ở phần bảng băm. Khi học trong một notebook hoặc file Python, cần đặt định nghĩa `ChainedHashMap` **trước** `SetFromMap`.

**Không phải mọi kiểu Set/Map trong mọi ngôn ngữ đều được cài đúng như nhau.** Mục đích của ví dụ là chỉ ra mối liên hệ giữa hai ADT: set có thể xem là tập khóa của một map mà phần giá trị không được quan tâm.

## 10. Bảng độ phức tạp tổng hợp

Gọi `n` là số khóa hoặc phần tử phân biệt đang lưu, `U` là kích thước miền khóa nguyên khả dĩ, `h` là chiều cao BST. Các bảng sau mô tả **cách triển khai đã nêu** và giả định phép so sánh/băm khóa cơ bản tốn `O(1)`.

| Hiện thực | Tìm khóa | Thêm khóa mới có chống trùng | Cập nhật khóa cũ | Xóa theo khóa | Bộ nhớ |
| --- | --- | --- | --- | --- | --- |
| Mảng **chưa sắp** | `O(n)` | `O(n)` | `O(n)` | `O(n)` | `O(n)` |
| Mảng **đã sắp** | `O(log n)` | `O(n)` | `O(log n)` | `O(n)` | `O(n)` |
| **Danh sách liên kết** chưa sắp | `O(n)` | `O(n)` | `O(n)` | `O(n)` | `O(n)` |
| **Bảng băm** có tải được kiểm soát | Trung bình `O(1)` | Trung bình khấu hao `O(1)` | Trung bình `O(1)` | Trung bình `O(1)` | `O(n)` |
| **BST chưa cân bằng** | `O(h)` | `O(h)` | `O(h)` | `O(h)` | `O(n)` |
| **Cây tìm kiếm cân bằng** | `O(log n)` | `O(log n)` | `O(log n)` | `O(log n)` | `O(n)` |
| **Mảng địa chỉ trực tiếp** | `O(1)` | `O(1)` | `O(1)` | `O(1)` | `O(U)` |

**Ghi chú:** bảng tách “cập nhật khóa cũ” và “thêm khóa mới”. Với BST thường, `h` có thể là `n`; với cây cân bằng, `h = O(log n)`. Các mốc bảng băm là **trung bình/kỳ vọng**, không phải bảo đảm tệ nhất cho mọi khóa hay mọi lần resize.

### Độ phức tạp duyệt và thứ tự

| Hiện thực | Thứ tự duyệt điển hình | Chi phí liệt kê tất cả phần tử |
| --- | --- | --- |
| Mảng chưa sắp | Thứ tự lưu trong mảng; có thể phản ánh thứ tự chèn nếu luôn append | `O(n)` |
| Mảng đã sắp | Theo thứ tự khóa | `O(n)` |
| Danh sách liên kết | Theo thứ tự các nút, có thể ngược thứ tự chèn nếu prepend | `O(n)` |
| Hash map/set nói chung | **Không nhất thiết có thứ tự được bảo đảm** | `O(n + b)` nếu quét tất cả `b` bucket |
| Cây tìm kiếm | Duyệt in-order theo thứ tự khóa | `O(n)` để xuất mọi khóa |
| Mảng địa chỉ trực tiếp | Theo thứ tự chỉ số nếu duyệt cả mảng | `O(U)` khi phải kiểm tra từng ô |

Không suy diễn thứ tự duyệt chỉ từ chữ “hash”: chẳng hạn Python `dict` từ 3.7 có bảo đảm thứ tự chèn, dù được hiện thực dựa trên bảng băm. Thứ tự cần dựa vào **hợp đồng của kiểu cụ thể**.

### Chi phí thật không chỉ có Big-O

Hai cấu trúc có cùng `O(n)` bộ nhớ vẫn có thể dùng số byte rất khác nhau:

- **Mảng động:** dữ liệu/ô tham chiếu thường được bố trí tương đối liên tục, thuận lợi cho cache và ít chi phí con trỏ hơn.
- **Danh sách liên kết:** mỗi nút cần con trỏ và thường là một lần cấp phát riêng; việc duyệt có thể kém cục bộ bộ nhớ.
- **Bảng băm:** cần bucket/ô trống dự phòng để giảm va chạm; resize có thể cấp lại vùng nhớ lớn.
- **Cây cân bằng:** cần liên kết trái/phải, đôi khi liên kết cha và metadata như chiều cao hoặc màu; bù lại hỗ trợ thứ tự và truy vấn khoảng.

Big-O là công cụ dự đoán **xu hướng theo quy mô**, không thay thế việc đo đạc với kích thước dữ liệu, phân bố khóa và môi trường thật.

## 11. Chọn cách cài phù hợp với bài toán

Không có hiện thực tốt nhất cho mọi trường hợp. Có thể đặt các câu hỏi theo thứ tự:

1. **Khóa thuộc miền nào?** Số nguyên nhỏ và liên tiếp, hay chuỗi/đối tượng đa dạng?
2. **Thao tác chính là gì?** Tra cứu chính xác, thêm/xóa thường xuyên, hay duyệt toàn bộ?
3. **Có cần thứ tự không?** Chỉ cần hiện diện, giữ thứ tự chèn, hay truy vấn theo khoảng?
4. **Có bao nhiêu dữ liệu?** Vài chục phần tử hay hàng triệu khóa?
5. **Bộ nhớ bị giới hạn thế nào?** Miền khóa có thưa không, có chấp nhận bucket trống/con trỏ không?
6. **Quy tắc khóa trùng là gì?** Cần chuẩn hóa, bằng nhau theo nội dung hay theo comparator?

| Tình huống | Lựa chọn thường hợp lý | Vì sao |
| --- | --- | --- |
| Vài cặp cấu hình cố định, hiếm khi tra cứu | Mảng cặp đơn giản | Ít mã, dễ kiểm tra và duy trì |
| Dữ liệu đã sắp, ít cập nhật, cần truy vấn khoảng | Mảng đã sắp | Tìm nhị phân và duyệt theo thứ tự hiệu quả |
| Mã nguyên từ `0` đến vài nghìn, miền khá dày | Mảng địa chỉ trực tiếp | Truy cập `O(1)`, chi phí `O(U)` chấp nhận được |
| Tra cứu mã học viên, SKU nhiều lần, không cần sắp khóa | Hash map / hash set | Trung bình tra cứu/thêm/xóa nhanh |
| Cần khóa tăng dần và truy vấn đoạn khóa thường xuyên | Tree map / tree set cân bằng | Tìm/cập nhật `O(log n)`, duyệt có thứ tự |
| Thuật toán liên quan nhiều thao tác nối/xóa nút đã biết vị trí | Danh sách liên kết | Thao tác con trỏ cục bộ `O(1)` khi đã có nút/vị trí |
| Danh sách kề đồ thị, muốn tra đỉnh và lưu nhiều hàng xóm | Map từ đỉnh tới list/set | Kết hợp map với collection theo yêu cầu trùng/thứ tự |

Với **đồ thị**, ví dụ map `vertex → set of neighbors` cung cấp tra đỉnh bằng map và kiểm tra láng giềng bằng set; đây là sự kết hợp các cấu trúc, không phải một ADT hoàn toàn mới.

### Ví dụ: kho hàng thay đổi thường xuyên

Giả sử cần 100.000 mã SKU, mỗi giây có nhiều tra cứu và cập nhật, nhưng báo cáo tăng dần theo mã chỉ xuất một lần mỗi ngày.

Một lựa chọn hợp lý là **hash map để vận hành thường ngày** và **sắp xếp các khóa khi xuất báo cáo**. Cấu trúc không cần duy trì thứ tự mọi lúc vì yêu cầu thứ tự hiếm gặp. Ngược lại, nếu ứng dụng phải trả truy vấn “mọi SKU từ A đến B” liên tục, một **tree map** hoặc một chỉ mục sắp xếp bổ sung có thể phù hợp hơn.

Đây là quyết định dựa trên **tỷ lệ thao tác**, không chỉ việc cấu trúc nào có thao tác đơn lẻ nhanh nhất.

## 12. Những lỗi cài đặt dễ phá bất biến

1. **Thêm cặp mới mà không kiểm tra khóa trùng.** Mảng hoặc danh sách có thể chứa hai cặp cùng khóa; map không còn là ánh xạ đúng.
2. **Nhầm địa chỉ ô hash với tính duy nhất.** Hai khóa khác nhau có thể cùng hash/bucket; vẫn cần kiểm tra bằng nhau.
3. **Quên tái phân bố khi mở rộng bảng băm.** Công thức xác định bucket thay đổi theo dung lượng mới.
4. **Quên cập nhật biến `size` khi ghi đè hoặc xóa khóa thiếu.** Kích thước map đếm số khóa phân biệt, không đếm số lần gọi `put`.
5. **Nhầm tìm nhị phân với chèn `O(log n)` trên mảng đã sắp.** Dịch phần tử vẫn có thể tốn `O(n)`.
6. **Cho rằng xóa nút danh sách liên kết theo khóa luôn `O(1)`.** Chỉ bước nối lại con trỏ là hằng số; tìm nút có thể `O(n)`.
7. **Gọi BST thường là cây cân bằng.** Chèn khóa theo thứ tự có thể làm cây lệch, chi phí suy biến `O(n)`.
8. **Thay đổi trường tham gia hash/so sánh của khóa đã lưu.** Có thể khiến find/remove đi sai vị trí.
9. **Dùng `None` làm dấu ô trống khi `None` là giá trị hợp lệ.** Cần sentinel hoặc thông tin tồn tại riêng.
10. **Giả định hash map luôn duyệt theo thứ tự chèn hoặc sắp xếp.** Hợp đồng thứ tự phải được chọn rõ.
11. **Dùng mỗi cấu trúc chỉ vì `O(1)` trên lý thuyết.** Hệ số tải, kích thước khóa, chi phí cache và bộ nhớ có thể làm quyết định kém phù hợp.
12. **Thay collection nội bộ khi đang duyệt mà không có chính sách.** Với nhiều hiện thực, thêm/xóa trong khi duyệt có thể làm iterator lỗi hoặc tạo hành vi không mong muốn.

## 13. Tự luyện tập

**Bài 1.** Một map lưu 20 cặp khóa–giá trị trong mảng chưa sắp xếp. Khi tìm một khóa ở cuối mảng, cần kiểm tra tối đa bao nhiêu cặp? Nếu mảng đã sắp và dùng tìm nhị phân, độ phức tạp thay đổi thế nào?

**Bài 2.** Tại sao thao tác `append` cuối mảng động có chi phí khấu hao `O(1)`, nhưng `put(k, v)` vào map dùng mảng chưa sắp vẫn có thể tốn `O(n)`?

**Bài 3.** Mô tả ba bước chính khi xóa một khóa trong danh sách liên kết đơn, và giải thích vì sao tìm theo khóa vẫn có thể chiếm `O(n)`.

**Bài 4.** Một bảng băm có `n = 6` khóa và `b = 8` bucket. Tính hệ số tải `α`. Khi tăng dung lượng lên `16` bucket, tại sao phải phân bố lại các cặp?

**Bài 5.** Hai khóa khác nhau có cùng hash. Hash map có được phép giữ cả hai không? Bước nào bảo đảm không coi nhầm hai khóa là một?

**Bài 6.** BST thường nhận lần lượt các khóa `1, 2, 3, 4, 5, 6`. Cây có thể có hình dạng gì? Tìm khóa `6` cần đi qua bao nhiêu nút trong tình huống lệch hoàn toàn?

**Bài 7.** Vì sao mảng địa chỉ trực tiếp không phù hợp khi miền khóa có từ `0` đến `10^12` nhưng chỉ có một nghìn khóa thực tế?

**Bài 8.** Viết một set đơn giản dựa trên map: nêu cách thực hiện `add`, `contains`, `remove` và cách duy trì tính duy nhất.

**Bài 9.** Chọn giữa hash map và tree map cho hai tình huống: (a) liên tục tra mã sản phẩm cụ thể; (b) thường xuyên liệt kê mã từ `SP100` đến `SP500` theo thứ tự.

**Bài 10.** Một hệ thống muốn vừa trả lời nhanh “đã có học viên X chưa” vừa in danh sách theo **thứ tự học viên xuất hiện lần đầu**. Chọn cách phối hợp cấu trúc nào và phân tích thời gian, bộ nhớ với `m` lượt sự kiện và `d` học viên phân biệt.

<details>
<summary>Đáp án và gợi ý</summary>

1. Mảng chưa sắp có thể kiểm tra 20 cặp, tổng quát `O(n)`; mảng đã sắp tìm nhị phân `O(log n)`.
2. Phải **tìm xem khóa đã tồn tại chưa** để giữ bất biến; bước tìm tuyến tính tốn `O(n)`, dù nối cuối chỉ khấu hao `O(1)`.
3. Đi từ `head` để tìm nút và theo dõi nút trước; nối `prev.next` tới `node.next` hoặc đổi `head`; giảm kích thước. Bước đi tìm cần tối đa `n` lần so sánh.
4. `α = 6/8 = 0.75`. Sau tăng `b`, vị trí `hash(k) % b` thay đổi, nên cần phân bố lại mục; không thể chỉ kéo dài mảng mà bỏ qua rehash trong các cấu trúc dùng modulo này.
5. Có. Kiểm tra `==` (hoặc quy tắc bằng nhau tương ứng) trong vùng xử lý va chạm giúp phân biệt, không chỉ dựa vào hash.
6. Cây có thể lệch hoàn toàn sang phải. Để tìm `6` phải đi qua 6 nút, tương ứng `O(n)`.
7. Cấp khoảng `10^12` ô là cực kỳ lãng phí, bộ nhớ `O(U)` so với `O(n)` của cấu trúc chỉ lưu khóa xuất hiện.
8. Lưu `element → marker` trong map; `add` ghi khóa nếu thiếu, `contains` kiểm tra khóa, `remove` xóa khóa; số phần tử bằng số khóa phân biệt.
9. (a) Hash map thường phù hợp vì tra cứu trung bình `O(1)`; (b) tree map cân bằng phù hợp hơn cho truy vấn khoảng có thứ tự.
10. Dùng `set` để kiểm tra đã gặp, `list` để ghi nhận mã xuất hiện lần đầu; mỗi sự kiện kiểm tra trung bình `O(1)` và thêm cuối khấu hao `O(1)`, tổng thời gian trung bình `O(m)`, bộ nhớ `O(d)`.

</details>

## Ghi nhớ

**Set/Map ADT quy định hành vi và bất biến, không quy định cách lưu trữ.** Cài bằng mảng hoặc danh sách liên kết đơn giản nhưng thường phải tìm tuyến tính; mảng đã sắp tìm nhanh bằng nhị phân song chèn/xóa tốn chi phí dịch phần tử. Bảng băm cho tra cứu/chèn/xóa **trung bình `O(1)`** khi băm và hệ số tải hợp lý; cây tìm kiếm cân bằng cho **`O(log n)`** và duyệt khóa có thứ tự. Mảng địa chỉ trực tiếp là lựa chọn chuyên biệt khi miền khóa nguyên nhỏ. Muốn chọn đúng cấu trúc, hãy bắt đầu từ **bất biến khóa duy nhất**, nhu cầu cập nhật/tra cứu/thứ tự, sau đó cân nhắc cả **thời gian, bộ nhớ và đặc tính dữ liệu**.
