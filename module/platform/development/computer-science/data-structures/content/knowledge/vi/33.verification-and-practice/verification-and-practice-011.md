# Thực hành kiểm tra phép quay cây, xóa bảng băm và mở rộng mảng động

## 1. Mục tiêu của bài thực hành

Trong các chương về cây, bảng băm và mảng động, chúng ta học cách tối ưu thao tác tìm kiếm, thêm, xóa và truy cập. Nhưng một thuật toán có vẻ đúng trên ví dụ đơn giản vẫn có thể làm hỏng cấu trúc dữ liệu sau nhiều thao tác liên tiếp. Chẳng hạn:

- **Quay cây** có thể làm mất cây con ở giữa hoặc cập nhật sai chiều cao của nút.
- **Xóa trong bảng băm dò tuyến tính** có thể vô tình chặn đường tìm một khóa vẫn còn tồn tại.
- **Mở rộng mảng động** có thể sao chép thiếu phần tử, ghi sai thứ tự hoặc tăng dung lượng bằng một chiến lược có chi phí quá lớn.

Bài thuộc chương **Kiểm chứng và thực hành** của học phần cấu trúc dữ liệu. Ta sẽ luyện cách xác định **bất biến**, viết **oracle** (mô hình tham chiếu đơn giản), kiểm thử các **trường hợp biên**, dùng **kiểm thử ngẫu nhiên có hạt giống cố định** và phân biệt độ phức tạp của một thao tác với chi phí **khấu hao** của cả chuỗi thao tác. Mục tiêu là biết giải thích *vì sao phép biến đổi đúng* và *cách phát hiện lỗi nếu cài đặt sai*.

Ba bài thực hành dùng Python 3.10+ với thư viện chuẩn. Các đoạn mã được trình bày để có thể ghép thành một tệp và chạy độc lập theo thứ tự; không cần thư viện kiểm thử ngoài. Khi tích hợp vào dự án, có thể chuyển các khẳng định `assert` thành bài kiểm thử `pytest` hoặc framework tương ứng.

## 2. Quy trình kiểm chứng một cấu trúc dữ liệu

Một cách làm ổn định gồm năm bước:

1. **Viết hợp đồng thao tác:** xác định đầu vào hợp lệ, kết quả trả về và hành vi khi lỗi (chẳng hạn xóa khóa không tồn tại phải báo `KeyError`).
2. **Xác định bất biến cấu trúc:** điều luôn phải đúng sau mọi thao tác hoàn tất. Ví dụ: thứ tự khóa trong BST, đường dò không bị ngắt trong bảng băm, `0 ≤ size ≤ capacity` của mảng.
3. **Chọn oracle độc lập:** một phiên bản đơn giản dễ tin cậy, như danh sách đã sắp xếp, `dict` hoặc `list` Python, dùng để so kết quả ở quy mô nhỏ.
4. **Kiểm tra cả hậu điều kiện và tính toàn vẹn:** kiểm tra giá trị trả về, số phần tử, thứ tự và khả năng truy cập các phần tử không liên quan. Một lệnh có thể trả đúng nhưng âm thầm làm hỏng cấu trúc.
5. **Kiểm tra nhiều chuỗi thao tác:** tạo các tình huống có chủ đích, sau đó sinh thao tác giả ngẫu nhiên với seed cố định để tái hiện lỗi.

| Khía cạnh | Câu hỏi cần trả lời | Ví dụ lỗi |
| --- | --- | --- |
| Hậu điều kiện | Kết quả thao tác có đúng không? | `pop()` trả phần tử khác phần tử cuối. |
| Bất biến cấu trúc | Các liên kết/nội dung bên trong còn hợp lệ không? | Quay cây làm mất nhánh ở giữa. |
| Tính bảo toàn | Phần tử không bị tác động có còn không? | Xóa một khóa khiến khóa va chạm khác không tìm được. |
| Biên | Với rỗng, một phần tử, đầy dung lượng, va chạm thì sao? | Thêm vào mảng đầy ghi vượt bộ nhớ. |
| Chuỗi thao tác | Nhiều cập nhật liên tiếp có làm lộ lỗi không? | Đặt tombstone rồi chèn khóa cũ tạo bản sao. |
| Độ phức tạp | Chi phí thay đổi theo kích thước thế nào? | Mỗi lần append lại sao chép cả mảng. |

**Giới hạn của kiểm thử:** vượt qua nhiều kiểm thử làm tăng mức tin cậy, nhưng không thay thế chứng minh bất biến. Cũng không thể chỉ đo thời gian của một ví dụ nhỏ để kết luận thuật toán có độ phức tạp mong muốn.

---

## 3. Bài thực hành A — Kiểm tra phép quay cây nhị phân tìm kiếm

### 3.1. Phép quay phải giữ điều gì?

Với cây nhị phân tìm kiếm (BST) có khóa **không trùng nhau**, mỗi nút có khóa lớn hơn mọi khóa ở nhánh trái và nhỏ hơn mọi khóa ở nhánh phải. Hai phép quay cơ bản:

**Quay trái tại `x`:**

~~~text
         x                       y
        / \                     / \
       A   y      ---->        x   C
          / \                 / \
         B   C               A   B
~~~

**Quay phải tại `y`:**

~~~text
           y                   x
          / \                 / \
         x   C    ---->      A   y
        / \                     / \
       A   B                   B   C
~~~

Khi quay, toàn bộ cây con `B` được chuyển từ một nhánh sang nhánh khác. Vì BST có thứ tự `A < x < B < y < C`, phép chuyển vẫn bảo toàn thứ tự nếu các con trỏ được cập nhật chính xác.

Sau mỗi phép quay hợp lệ, cần giữ các bất biến:

- Dãy khóa khi duyệt **in-order** không đổi, nên tập khóa và số nút không đổi.
- Không nút nào biến mất, xuất hiện hai lần hoặc tạo chu trình.
- Các quan hệ khóa của BST vẫn đúng.
- Metadata của nút bị ảnh hưởng (ví dụ `height`, `size`, tổng cây con) được tính lại.

Trong **AVL**, sau phép quay dùng để sửa mất cân bằng, còn kiểm tra hệ số cân bằng `|height(left)-height(right)| ≤ 1` cho toàn cây. Nhưng **một phép quay đơn bất kỳ không bảo đảm biến một BST thành AVL**; điều kiện cân bằng chỉ là hậu điều kiện khi chọn đúng trường hợp và chuỗi quay.

### 3.2. Cài đặt phép quay trái và quay phải

Ở đây ta dùng nút có `key`, `left`, `right` và `height`; không lưu con trỏ cha. Hàm quay trả về **gốc mới của cây con**, vì người gọi phải gắn lại gốc mới vào cha hoặc cập nhật biến `root`.

~~~python
from __future__ import annotations
from dataclasses import dataclass
from random import Random


@dataclass
class Node:
    key: int
    left: Node | None = None
    right: Node | None = None
    height: int = 1


def h(node: Node | None) -> int:
    return 0 if node is None else node.height


def update_height(node: Node) -> None:
    node.height = 1 + max(h(node.left), h(node.right))


def rebuild_heights(node: Node | None) -> int:
    """Dùng khi tạo cây thủ công cho bài kiểm tra."""
    if node is None:
        return 0
    left_h = rebuild_heights(node.left)
    right_h = rebuild_heights(node.right)
    node.height = 1 + max(left_h, right_h)
    return node.height


def rotate_left(x: Node) -> Node:
    if x.right is None:
        raise ValueError("Quay trái cần có con phải")

    y = x.right
    middle = y.left

    y.left = x
    x.right = middle

    # Nút x xuống thấp hơn: cập nhật x trước y.
    update_height(x)
    update_height(y)
    return y


def rotate_right(y: Node) -> Node:
    if y.left is None:
        raise ValueError("Quay phải cần có con trái")

    x = y.left
    middle = x.right

    x.right = y
    y.left = middle

    update_height(y)
    update_height(x)
    return x
~~~

Nếu cấu trúc có thêm `parent`, `subtree_size` hoặc dữ liệu tăng cường khác, việc kiểm tra phải bao gồm những trường đó. Mã trên không cập nhật `parent` vì mô hình nút không có con trỏ cha.

### 3.3. Bộ kiểm tra độc lập cho BST, chiều cao và AVL

Hàm kiểm tra dùng giới hạn khóa trên mỗi cây con thay vì chỉ so cha với con trực tiếp. Điều này phát hiện lỗi sâu hơn, chẳng hạn một khóa nằm trong cây con phải của gốc nhưng vẫn nhỏ hơn gốc.

~~~python
def inspect_tree(
    root: Node | None, *, require_avl: bool = False
) -> tuple[list[int], set[int]]:
    seen: set[int] = set()

    def walk(
        node: Node | None,
        lower: int | None,
        upper: int | None,
    ) -> tuple[int, list[int]]:
        if node is None:
            return 0, []

        identity = id(node)
        assert identity not in seen, "Nút lặp lại hoặc có chu trình"
        seen.add(identity)

        if lower is not None:
            assert lower < node.key, "Vi phạm cận dưới BST"
        if upper is not None:
            assert node.key < upper, "Vi phạm cận trên BST"

        left_h, left_keys = walk(node.left, lower, node.key)
        right_h, right_keys = walk(node.right, node.key, upper)
        expected_h = 1 + max(left_h, right_h)
        assert node.height == expected_h, "Chiều cao lưu sai"

        if require_avl:
            assert abs(left_h - right_h) <= 1, "Chưa cân bằng AVL"

        return (
            expected_h,
            left_keys + [node.key] + right_keys,
        )

    _, keys = walk(root, None, None)
    assert keys == sorted(keys)
    return keys, seen
~~~

So sánh cả hai kết quả của `inspect_tree` trước và sau quay giúp phát hiện việc “mất” một nút dù kết quả tìm kiếm một vài khóa vẫn đúng. `id(node)` chỉ dùng để nhận diện **đúng các đối tượng nút** trong một lần kiểm thử; không phải khóa nghiệp vụ của cây.

### 3.4. Kiểm tra bốn trường hợp LL, RR, LR, RL

Trong các tình huống dưới đây, cây con có ba khóa và chọn đúng phép quay cần thiết để khôi phục cân bằng AVL:

| Trường hợp | Kiểu lệch | Chuỗi thao tác |
| --- | --- | --- |
| LL | Nặng trái của con trái | Quay phải tại gốc |
| RR | Nặng phải của con phải | Quay trái tại gốc |
| LR | Nặng phải của con trái | Quay trái tại con trái, rồi quay phải tại gốc |
| RL | Nặng trái của con phải | Quay phải tại con phải, rồi quay trái tại gốc |

~~~python
cases = [
    ("LL", Node(30, left=Node(20, left=Node(10)))),
    ("RR", Node(10, right=Node(20, right=Node(30)))),
    ("LR", Node(30, left=Node(10, right=Node(20)))),
    ("RL", Node(10, right=Node(30, left=Node(20)))),
]

for label, root in cases:
    rebuild_heights(root)
    keys_before, nodes_before = inspect_tree(root)

    if label == "LL":
        root = rotate_right(root)
    elif label == "RR":
        root = rotate_left(root)
    elif label == "LR":
        root.left = rotate_left(root.left)
        root = rotate_right(root)
    else:  # RL
        root.right = rotate_right(root.right)
        root = rotate_left(root)

    keys_after, nodes_after = inspect_tree(root, require_avl=True)
    assert keys_after == keys_before == [10, 20, 30]
    assert nodes_after == nodes_before
    assert root.key == 20
~~~

**Trường hợp phải thử thêm: cây con ở giữa không rỗng.** Nếu chỉ thử ba nút thẳng hàng, một cách cài đặt bỏ quên `middle` vẫn có thể qua kiểm thử.

~~~python
root = Node(10, right=Node(30, left=Node(20)))
rebuild_heights(root)
keys_before, nodes_before = inspect_tree(root)

root = rotate_left(root)
keys_after, nodes_after = inspect_tree(root)

assert root.key == 30
assert root.left.key == 10
assert root.left.right.key == 20   # Cây con ở giữa vẫn tồn tại
assert keys_before == keys_after == [10, 20, 30]
assert nodes_before == nodes_after
~~~

Ở ví dụ cuối, sau **một** phép quay trái, cây vẫn có thể chưa cân bằng AVL. Điều cần chứng minh tại đây là phép quay đơn đúng về **BST, liên kết và chiều cao**; nếu đang sửa trường hợp RL của AVL, phải quay phải tại con phải trước.

### 3.5. Kiểm tra ngẫu nhiên bảo toàn in-order

Để thử phép quay trên cây có hình dạng phong phú hơn, có thể tạo BST bằng cách chèn các khóa phân biệt, rồi quay tại gốc khi có con phù hợp. Khi quay tùy ý, chỉ bắt buộc bảo toàn BST và metadata; không bắt buộc toàn cây cân bằng AVL.

~~~python
def insert_bst(root: Node | None, key: int) -> Node:
    if root is None:
        return Node(key)
    if key < root.key:
        root.left = insert_bst(root.left, key)
    elif key > root.key:
        root.right = insert_bst(root.right, key)
    else:
        raise ValueError("Bài này yêu cầu các khóa phân biệt")
    update_height(root)
    return root


rng = Random(20261128)
for _ in range(200):
    root = None
    keys = rng.sample(range(-1000, 1000), rng.randint(2, 25))
    for key in keys:
        root = insert_bst(root, key)

    before_keys, before_ids = inspect_tree(root)
    if root.right is not None:
        root = rotate_left(root)
    else:
        root = rotate_right(root)
    after_keys, after_ids = inspect_tree(root)

    assert before_keys == after_keys == sorted(keys)
    assert before_ids == after_ids
~~~

Một bài mở rộng hữu ích là chọn **một nút bên trong cây** thay vì luôn quay ở gốc, sau đó gắn gốc cây con mới vào đúng con trỏ của nút cha và kiểm tra toàn bộ cây. Đây là tình huống dễ lộ lỗi quên cập nhật liên kết với cha.

---

## 4. Bài thực hành B — Kiểm tra xóa trong bảng băm dò tuyến tính

### 4.1. Vì sao không thể xóa bằng cách đặt ô thành EMPTY?

Trong bảng băm dùng **open addressing** và **linear probing**, tìm khóa `k` bắt đầu từ `h(k)\bmod m` và xét lần lượt các ô:

\[
i_t=(h(k)+t)\bmod m,\qquad t=0,1,\ldots,m-1.
\]

Nếu gặp ô **chưa từng sử dụng** (`EMPTY`), có thể dừng tìm: theo quy tắc chèn, khóa không thể nằm sau ô đó trên cùng đường dò. Nhưng nếu ô đã chứa một khóa rồi bị xóa, việc đổi thẳng thành `EMPTY` sẽ làm hỏng giả thiết này.

~~~text
Dung lượng m = 7, tất cả khóa minh họa có h(k) % 7 = 2.

Chèn A, B, C:
chỉ số:    0 1 2 3 4 5 6
ô:         . . A B C . .

Xóa A bằng EMPTY (sai):
ô:         . . . B C . .
find(C): bắt đầu ở ô 2, gặp EMPTY và dừng -> báo thiếu C!

Xóa A bằng TOMBSTONE (đúng):
ô:         . . X B C . .
find(C): bỏ qua X, đi tiếp qua B đến C.
~~~

Giải pháp đơn giản là phân biệt ba trạng thái ô:

| Trạng thái | Ý nghĩa | Khi tìm kiếm | Khi chèn |
| --- | --- | --- | --- |
| `EMPTY` | Ô chưa từng có phần tử từ lần tái băm gần nhất | Dừng, kết luận không có khóa | Có thể dùng |
| `DELETED` (*tombstone*) | Ô từng được dùng nhưng khóa đã bị xóa | **Tiếp tục dò** | Có thể tái sử dụng sau khi chắc chắn khóa chưa ở sau |
| `OCCUPIED(key,value)` | Ô có cặp khóa và giá trị | So khóa; nếu khác thì tiếp tục | Cập nhật nếu cùng khóa, tiếp tục dò nếu khác |

**Bất biến đường dò:** với mỗi khóa còn tồn tại tại ô `j`, đi từ vị trí băm ban đầu theo chuỗi dò tới `j` không được gặp `EMPTY` trước đó. `DELETED` không cắt đứt đường dò.

### 4.2. Bản cài đặt tối giản có tombstone và tái băm

Mã dưới đây dùng hai đối tượng sentinel riêng biệt để phân biệt EMPTY và DELETED. Các giá trị hợp lệ của bảng có thể là `None` vì ô có phần tử được biểu diễn bằng một tuple `(key, value)`; không dùng `None` làm dấu ô trống.

Để việc tìm kiếm có độ dài đường dò hợp lý khi khóa phân bố đều, bản thực hành giữ tỷ lệ **ô đang dùng + tombstone** không vượt quá khoảng một nửa trước khi thêm khóa mới. Khi cần, ta tái băm tại dung lượng hiện tại để loại tombstone, hoặc tăng gấp đôi dung lượng khi số khóa thực đã quá lớn.

~~~python
_EMPTY = object()
_DELETED = object()


class LinearProbingMap:
    def __init__(self) -> None:
        self.slots = [_EMPTY] * 8
        self.size = 0
        self.tombstones = 0

    def __len__(self) -> int:
        return self.size

    def _locate(self, key, for_insert: bool) -> int:
        """Trả vị trí có key, hoặc ô hợp lệ để chèn, hoặc -1."""
        m = len(self.slots)
        first_deleted = -1

        for step in range(m):
            index = (hash(key) + step) % m
            entry = self.slots[index]

            if entry is _EMPTY:
                if for_insert and first_deleted >= 0:
                    return first_deleted
                return index if for_insert else -1

            if entry is _DELETED:
                if for_insert and first_deleted < 0:
                    first_deleted = index
                # Không được dừng tìm tại tombstone.
                continue

            if entry[0] == key:
                return index

        return first_deleted if for_insert else -1

    def _rehash(self, new_capacity: int) -> None:
        old_slots = self.slots
        self.slots = [_EMPTY] * new_capacity
        self.size = 0
        self.tombstones = 0

        for entry in old_slots:
            if entry is _EMPTY or entry is _DELETED:
                continue
            index = self._locate(entry[0], for_insert=True)
            assert index >= 0
            self.slots[index] = entry
            self.size += 1

    def put(self, key, value) -> None:
        # Kiểm tra khóa đã có trước: cập nhật không tăng size.
        existing = self._locate(key, for_insert=False)
        if existing >= 0:
            self.slots[existing] = (key, value)
            return

        # Không để đường dò dài lên vì quá nhiều tombstone.
        if 2 * (self.size + self.tombstones + 1) > len(self.slots):
            if 2 * (self.size + 1) > len(self.slots):
                self._rehash(2 * len(self.slots))
            else:
                self._rehash(len(self.slots))

        index = self._locate(key, for_insert=True)
        assert index >= 0
        if self.slots[index] is _DELETED:
            self.tombstones -= 1
        self.slots[index] = (key, value)
        self.size += 1

    def get(self, key):
        index = self._locate(key, for_insert=False)
        if index < 0:
            raise KeyError(key)
        return self.slots[index][1]

    def delete(self, key):
        index = self._locate(key, for_insert=False)
        if index < 0:
            raise KeyError(key)
        old_value = self.slots[index][1]
        self.slots[index] = _DELETED
        self.size -= 1
        self.tombstones += 1
        return old_value
~~~

Code giả định khóa là **hashable**, quan hệ bằng nhau nhất quán với hàm băm và giá trị hash không đổi trong thời gian khóa được lưu. Nếu khóa bị thay đổi khiến giá trị băm thay đổi sau khi chèn, việc tìm kiếm sẽ không còn đáng tin cậy, ngay cả khi thuật toán dò đúng.

### 4.3. Kiểm tra va chạm có chủ đích

Ta tạo các khóa khác nhau nhưng đều trả về cùng giá trị băm. Kiểm thử này buộc các khóa phải chia sẻ một chuỗi dò, qua đó phát hiện lỗi xóa bằng EMPTY.

~~~python
@dataclass(frozen=True)
class CollidingKey:
    number: int

    def __hash__(self) -> int:
        return 3  # Cố ý buộc mọi khóa va chạm


table = LinearProbingMap()
a, b, c, d = [CollidingKey(i) for i in range(4)]
table.put(a, "A")
table.put(b, "B")
table.put(c, "C")

assert table.delete(a) == "A"
assert table.get(b) == "B"  # Không bị ngắt đường dò
assert table.get(c) == "C"
assert len(table) == 2
assert table.tombstones == 1

# Một phần tử mới có thể dùng lại tombstone của a.
table.put(d, "D")
assert table.get(d) == "D"
assert table.get(b) == "B"
assert table.get(c) == "C"
assert len(table) == 3

# Cập nhật khóa có sẵn: không tạo bản sao và không tăng size.
table.put(b, "B2")
assert table.get(b) == "B2"
assert len(table) == 3

# Xóa khóa vắng mặt phải báo lỗi, không làm giảm size.
try:
    table.delete(a)
except KeyError:
    pass
else:
    raise AssertionError("Xóa khóa vắng mặt phải phát sinh KeyError")
assert len(table) == 3
~~~

### 4.4. Oracle bằng `dict` và kiểm tra sau từng thao tác

Một lỗi xóa có thể chỉ xuất hiện sau một chuỗi dài gồm chèn, chèn đè, xóa, chèn lại và tái băm. Ta dùng `dict` của Python làm oracle về **hành vi ánh xạ khóa → giá trị**, đồng thời kiểm tra số ô occupied và số tombstone của bảng tự cài.

~~~python
def check_hash_invariants(
    table: LinearProbingMap, model: dict
) -> None:
    occupied = [
        slot for slot in table.slots
        if slot is not _EMPTY and slot is not _DELETED
    ]
    deleted = sum(slot is _DELETED for slot in table.slots)
    assert len(occupied) == table.size == len(model)
    assert deleted == table.tombstones
    assert table.size + table.tombstones <= len(table.slots)

    # Không trùng khóa và mọi khóa vẫn tìm được bằng thuật toán dò.
    stored_keys = [entry[0] for entry in occupied]
    assert len(set(stored_keys)) == len(stored_keys)
    assert set(stored_keys) == set(model)
    for key, expected in model.items():
        assert table.get(key) == expected


rng = Random(3311)
table = LinearProbingMap()
model = {}
keys = [CollidingKey(i) for i in range(30)]

for _ in range(1500):
    key = rng.choice(keys)
    operation = rng.randrange(3)

    if operation == 0:  # put
        value = rng.randint(-1000, 1000)
        table.put(key, value)
        model[key] = value

    elif operation == 1:  # delete
        if key in model:
            assert table.delete(key) == model.pop(key)
        else:
            try:
                table.delete(key)
            except KeyError:
                pass
            else:
                raise AssertionError("Thiếu KeyError khi xóa")

    else:  # get
        if key in model:
            assert table.get(key) == model[key]
        else:
            try:
                table.get(key)
            except KeyError:
                pass
            else:
                raise AssertionError("Thiếu KeyError khi tìm")

    check_hash_invariants(table, model)
~~~

Kiểm thử này cố ý dùng các khóa có cùng hash để tăng khả năng lộ lỗi logic. Trong tình huống va chạm cực đoan, độ dài đường dò có thể là `O(m)` dù bảng giữ tỷ lệ lấp đầy nhỏ. Độ phức tạp **kỳ vọng** `O(1)` của tìm/chèn/xóa open addressing chỉ áp dụng với giả định phù hợp về phân bố hash và kiểm soát tỷ lệ lấp đầy; trường hợp xấu nhất vẫn có thể là `O(m)`.

Ngoài tombstone, một cách xóa khác là **dịch lùi cụm khóa** (*backward-shift deletion*), nhưng phải giữ tính hợp lệ của đường dò trong quá trình dịch. Không nên thay thế tombstone bằng cách dồn các ô một cách tùy ý, đặc biệt khi cụm khóa đi vòng qua cuối bảng.

---

## 5. Bài thực hành C — Kiểm tra mở rộng mảng động

### 5.1. Phân biệt `size` và `capacity`

Mảng động chứa một bộ nhớ có dung lượng `capacity`, nhưng mới có `size` phần tử hợp lệ. Khi gọi `append(x)`:

- Nếu `size < capacity`, ghi `x` vào ô `size` rồi tăng `size`.
- Nếu `size = capacity`, cấp phát bộ đệm lớn hơn, sao chép **đúng `size` phần tử đang có theo đúng thứ tự**, sau đó thêm `x`.

Ví dụ khi tăng gấp đôi dung lượng:

~~~text
Trước append(40):
size = 3, capacity = 4
[10, 20, 30, _]

Sau append(40):
size = 4, capacity = 4
[10, 20, 30, 40]

Sau append(50):
size = 5, capacity = 8
[10, 20, 30, 40, 50, _, _, _]
~~~

Các dấu `_` là ô dự trữ, **không thuộc phần tử hợp lệ**. Bất biến quan trọng:

\[
0 \le size \le capacity,\qquad
buffer[0:size] = \text{dãy giá trị đã thêm và chưa xóa}.
\]

Khác với mảng cố định, việc mở rộng mảng động thay đổi bộ đệm bên trong, nhưng không được làm thay đổi thứ tự, giá trị hay chỉ số logic của các phần tử hiện có.

### 5.2. Cài đặt có bộ đếm số phần tử sao chép

Mã sau bắt đầu với dung lượng 1, nhân đôi khi đầy, **không tự thu nhỏ khi pop** để tập trung kiểm chứng chi phí mở rộng. Có thể lưu `None` như một giá trị hợp lệ vì số phần tử được quản lý bằng `size`, không suy từ các ô chứa `None`.

~~~python
class DynamicArray:
    def __init__(self) -> None:
        self._capacity = 1
        self._buffer = [None] * self._capacity
        self._size = 0
        self.copies = 0  # Tổng phần tử sao chép khi cấp phát lại

    def __len__(self) -> int:
        return self._size

    @property
    def capacity(self) -> int:
        return self._capacity

    def _grow(self) -> None:
        new_capacity = self._capacity * 2
        new_buffer = [None] * new_capacity

        for i in range(self._size):
            new_buffer[i] = self._buffer[i]
            self.copies += 1

        self._buffer = new_buffer
        self._capacity = new_capacity

    def append(self, value) -> None:
        if self._size == self._capacity:
            self._grow()
        self._buffer[self._size] = value
        self._size += 1

    def pop(self):
        if self._size == 0:
            raise IndexError("pop từ mảng rỗng")
        self._size -= 1
        value = self._buffer[self._size]
        self._buffer[self._size] = None
        return value

    def get(self, index: int):
        if not (0 <= index < self._size):
            raise IndexError("Chỉ số không hợp lệ")
        return self._buffer[index]

    def to_list(self) -> list:
        return self._buffer[:self._size]
~~~

### 5.3. Trường hợp biên và kiểm tra oracle bằng `list`

**Tối thiểu** nên thử: mảng rỗng, thêm phần tử đầu, thêm đúng lúc đầy, `None` là phần tử hợp lệ, pop lần lượt về rỗng, rồi thêm lại. Sau đó tạo chuỗi thao tác ngẫu nhiên và đối chiếu với `list` Python.

~~~python
a = DynamicArray()
assert len(a) == 0
assert a.capacity == 1

a.append(None)
a.append(20)
assert a.to_list() == [None, 20]
assert a.pop() == 20
assert a.pop() is None

try:
    a.pop()
except IndexError:
    pass
else:
    raise AssertionError("pop từ mảng rỗng phải báo IndexError")

rng = Random(2026)
a = DynamicArray()
model = []

for _ in range(2000):
    if not model or rng.randrange(3) != 0:
        value = rng.choice([None, -1, 0, 1, 1000])
        a.append(value)
        model.append(value)
    else:
        assert a.pop() == model.pop()

    assert a.to_list() == model
    assert len(a) == len(model)
    assert 0 <= len(a) <= a.capacity
    assert a.capacity >= 1
    assert a.capacity & (a.capacity - 1) == 0  # Lũy thừa của 2

    for index, expected in enumerate(model):
        assert a.get(index) == expected
~~~

Đoạn `for index, expected in enumerate(model)` khiến **chương trình kiểm thử** có thể tốn nhiều thời gian hơn thao tác `append` đơn lẻ. Đó là chủ ý: bài kiểm tra đối chiếu toàn bộ trạng thái, trong khi cấu trúc dữ liệu chỉ cần thực hiện mỗi thao tác với chi phí theo đặc tả của nó.

### 5.4. Thử tăng dung lượng và đo chi phí sao chép

Với mảng tăng gấp đôi, các lần sao chép xảy ra lúc dung lượng cũ lần lượt là `1,2,4,8,\ldots`. Giả sử có `N` lần gọi `append` kể từ khi mảng rỗng, tổng số phần tử sao chép trong **mọi lần tăng dung lượng** bị chặn bởi:

\[
1+2+4+\cdots+2^t < 2N.
\]

Vì có thêm `N` lần ghi phần tử mới, tổng công việc của `N` lần append là `O(N)`. Do đó chi phí **khấu hao (amortized)** của một lần append là `O(1)`, dù một lần append đúng lúc mảng đầy phải sao chép `O(N)` phần tử.

Để quan sát, dùng một mảng mới và chỉ append:

~~~python
for n in [1, 2, 3, 5, 9, 17, 1000]:
    a = DynamicArray()
    for i in range(n):
        a.append(i)

    assert len(a) == n
    assert a.to_list() == list(range(n))
    assert a.copies < 2 * n
    assert n <= a.capacity < 2 * n
~~~

Với cách cấp phát bắt đầu từ 1 và nhân đôi, dung lượng sau `n≥1` lần append là lũy thừa của 2 nhỏ nhất không nhỏ hơn `n`, nên không vượt quá gần hai lần kích thước logic. Tuy nhiên, **sau nhiều lần pop**, dung lượng có thể vẫn lớn hơn `2\times size` vì bản này không thu nhỏ bộ đệm.

### 5.5. Vì sao mở rộng thêm một ô mỗi lần là nguy hiểm?

Nếu mỗi lần đầy chỉ tăng `capacity` thêm 1, chuỗi `N` lần append có thể cần sao chép:

\[
1+2+\cdots+(N-1)=\frac{N(N-1)}{2}=\Theta(N^2).
\]

Vì vậy append sẽ tốn `\Theta(N)` trung bình trên một chuỗi dài, khác với `O(1)` khấu hao của tăng theo hệ số nhân (như nhân đôi).

Ngược lại, tăng theo hệ số nhân không bảo đảm **thời gian tệ nhất** của từng append là hằng số; thao tác gây mở rộng vẫn có thể mất `\Theta(N)`. Nếu hệ thống yêu cầu giới hạn độ trễ nghiêm ngặt cho mọi thao tác, cần cân nhắc cấu trúc hoặc chiến lược phân bổ khác.

Nếu triển khai **thu nhỏ dung lượng khi xóa**, không nên thu nhỏ ngay khi `size=capacity/2` rồi lại tăng khi đầy: chuỗi pop/append luân phiên gần ngưỡng có thể liên tục sao chép mảng lớn. Một quy tắc thông dụng là **tăng khi đầy, giảm một nửa khi mức sử dụng xuống ≤ 1/4**, tạo khoảng đệm giữa hai ngưỡng để giữ chi phí khấu hao thấp. Với `capacity` tối thiểu bằng 1, cần bảo đảm không thu nhỏ về 0.

---

## 6. Kết nối ba bài: thiết kế kiểm thử theo bất biến

Ba ví dụ khác nhau về biểu diễn nhưng cùng tuân theo quy tắc “một thao tác đúng phải giữ những tính chất nền tảng của cấu trúc”.

| Thao tác | Bất biến chính | Oracle đơn giản | Lỗi đặc biệt nên chủ động tạo |
| --- | --- | --- | --- |
| Quay BST/AVL | In-order không đổi; nút không mất; height và BST đúng | Dãy khóa sắp xếp và tập định danh nút | Cây con ở giữa khác rỗng; quay tại nút không phải gốc; bốn kiểu LL/RR/LR/RL |
| Xóa linear probing | Không cắt đường dò đến khóa còn sống; size chính xác | Python `dict` | Nhiều khóa cùng hash; xóa đầu cụm; tái chèn vào tombstone; tái băm |
| Mở rộng mảng động | Thứ tự dữ liệu giữ nguyên; `size≤capacity`; sao chép đúng các phần tử hợp lệ | Python `list` | Vượt ngưỡng `1,2,4,8`; lưu `None`; pop về rỗng; append lại |

### Kiểm thử ví dụ, kiểm thử tính chất và kiểm thử ngẫu nhiên

Một **kiểm thử ví dụ** đặt dữ liệu cụ thể và đáp án biết trước; nó giúp bắt lỗi thường gặp và tạo ví dụ có thể giải thích bằng tay. Một **kiểm thử tính chất** xác nhận quan hệ luôn đúng, chẳng hạn quay cây không đổi danh sách in-order hoặc thêm rồi pop trả về chính giá trị vừa thêm. **Kiểm thử ngẫu nhiên có seed** tạo nhiều chuỗi thao tác để phát hiện các tương tác mà ta chưa nghĩ đến.

Nên kết hợp cả ba: nếu chỉ dùng dữ liệu ngẫu nhiên, có thể không bao giờ gặp trường hợp ngưỡng chính xác; nếu chỉ dùng ví dụ nhỏ, có thể bỏ sót trạng thái sau nhiều thao tác.

### Cách thu nhỏ một phản ví dụ

Nếu một chuỗi 1.500 thao tác bị lỗi:

1. Ghi seed, số bước, thao tác và trạng thái mô hình tại thời điểm lỗi.
2. Loại bớt các thao tác trước đó rồi chạy lại để tìm chuỗi ngắn nhất vẫn tái hiện lỗi.
3. Rút gọn khóa, giá trị hoặc hình dạng cây về trường hợp nhỏ hơn.
4. Đối chiếu trạng thái ngay **trước và sau thao tác đầu tiên làm bất biến sai**.

Ví dụ, lỗi xóa bảng băm có thể rút thành ba lần chèn khóa cùng hash, một lần xóa khóa đầu và một lần tìm khóa cuối. Lỗi quay cây có thể rút thành nút `x`, nút `y` và một cây con `B` không rỗng. Những phản ví dụ nhỏ thường chỉ ra nguyên nhân trực tiếp rõ hơn nhiều so với log dài.

## 7. So sánh độ phức tạp khi kiểm chứng

| Cấu trúc và thao tác | Thời gian điển hình | Thời gian xấu nhất | Bộ nhớ phụ trợ |
| --- | --- | --- | --- |
| Một phép quay cây (cập nhật số trường cố định) | `O(1)` | `O(1)` | `O(1)` |
| Duyệt xác minh toàn cây có `n` nút | `O(n)` | `O(n)` | `O(h)` đệ quy và `O(n)` cho tập nút/dãy khóa |
| Tìm/chèn/xóa linear probing với hash phân bố tốt và bảng được kiểm soát mức lấp đầy | Kỳ vọng `O(1)` | `O(m)` | `O(1)` cho thao tác không tái băm |
| Tái băm bảng có `m` ô | Kỳ vọng `O(m)` nếu hash phân bố tốt | Có thể `O(m²)` với nhiều khóa va chạm | `O(m)` để cấp phát bảng mới |
| Append mảng động, chưa đầy | `O(1)` | `O(1)` | `O(1)` |
| Append mảng động, phải mở rộng từ `n` phần tử | `O(n)` | `O(n)` | `O(n)` trong lúc có bộ đệm mới |
| Chuỗi `N` append với chiến lược nhân đôi | `O(N)` tổng, `O(1)` khấu hao mỗi lần | Một append riêng lẻ `O(N)` | `O(N)` dung lượng lưu trữ |

Ở hàng tái băm, `m` là dung lượng bảng băm cũ. Khi tái băm sang dung lượng mới cùng bậc, duyệt bảng cũ cần `O(m)`; chèn lại `n` khóa có thể tốn thêm `O(n²)` nếu tất cả va chạm vào cùng một cụm, nên giới hạn xấu nhất là `O(m+n²)`, hay `O(m²)` khi `n=O(m)`. Với hash phân bố tốt, thời gian tái băm **kỳ vọng** là `O(m)`. Trong thực tế, cần phân biệt **độ phức tạp thao tác của cấu trúc** và **độ phức tạp của mã kiểm thử**: xác minh mọi nút/mọi khóa sau mỗi bước có thể tốn `O(n)` hoặc hơn, và điều đó không làm thay đổi chi phí lý thuyết của thao tác thông thường.

## 8. Bài tập tự làm

**Bài 1 — Tìm lỗi phép quay.** Một bạn viết phép quay trái như sau:

~~~python
def broken_rotate_left(x):
    y = x.right
    y.left = x
    x.right = None
    return y
~~~

Hãy cho một BST nhỏ nhất có cây con giữa `B` khác rỗng để chỉ ra khóa nào bị mất. Hãy sửa hàm và giải thích vì sao phải lưu `middle = y.left` **trước khi** thay đổi các con trỏ. Để đạt đủ hậu điều kiện AVL, cần tính lại metadata nào?

*Đáp án định hướng:* với `x=10`, `y=30` và cây con giữa có khóa `20`, khóa 20 bị mất. Sửa bằng cách chuyển `y.left` cũ thành `x.right`, rồi tính lại height cho `x` và `y` theo đúng thứ tự.

**Bài 2 — Khóa có va chạm.** Xét bảng băm dài 7 với ba khóa `A,B,C` đều có hash bằng 2. Sau khi chèn theo thứ tự, hãy mô tả trạng thái khi xóa `B` bằng EMPTY và khi xóa bằng DELETED. Với mỗi phương án, hãy truy vết tìm `C` và chèn một khóa mới `D` cùng hash.

**Bài 3 — Bắt lỗi tombstone.** Trong hàm tìm khóa, một bạn dùng điều kiện `if entry is _EMPTY or entry is _DELETED: return -1`. Hãy viết ca kiểm thử ngắn nhất cho thấy lỗi, rồi đề xuất cách duyệt đúng khi gặp tombstone.

**Bài 4 — Phân biệt dữ liệu trống và giá trị None.** Vì sao `None` không nên được dùng đồng thời làm “ô chưa có phần tử” và “giá trị có thể lưu” trong cùng một bảng băm? Có nhất thiết phải cấm `None` trong `DynamicArray` của bài này không?

**Bài 5 — Tổng số bản sao của mảng động.** Với mảng có dung lượng ban đầu 1, mỗi khi đầy tăng gấp đôi, hãy tính số phần tử được sao chép trong `N=9` lần append đầu. So sánh với việc tăng dung lượng thêm 1 mỗi lần đầy.

*Đáp án định hướng:* nhân đôi sao chép `1+2+4+8=15` phần tử cho 9 lần append; tăng thêm 1 mỗi lần sao chép `1+2+\cdots+8=36` phần tử.

**Bài 6 — Thiết kế chiến lược thu nhỏ.** Hãy bổ sung `shrink` cho `DynamicArray` khi `size≤capacity/4`, với `capacity≥1`. Viết test append/pop xen kẽ tại các ngưỡng và chứng minh vì sao giảm ở 1/4 tránh được việc liên tục sao chép chỉ sau một cặp pop/append gần mức nửa dung lượng.

**Bài 7 — Mở rộng kiểm chứng AVL.** Bổ sung trường `subtree_size` vào `Node` và cài đặt kiểm tra `size(node)=1+size(left)+size(right)`. Chỉnh phép quay để cập nhật cả `height` và `subtree_size`. Sau đó sinh các cây con và xác minh in-order, tập định danh nút, height, subtree_size đều giữ đúng.

**Bài 8 — Làm bài kiểm thử có thể tái lập.** Khi một kiểm thử ngẫu nhiên thất bại, hãy in seed, số thứ tự thao tác và danh sách thao tác đã thực hiện. Thử giảm từ 1.500 thao tác xuống một ví dụ tối thiểu vẫn thất bại. Giải thích bất biến đầu tiên bị phá vỡ.

## 9. Tổng kết

Ba bài thực hành cung cấp ba cách tư duy kiểm chứng bổ trợ nhau:

- **Phép quay cây** là một biến đổi liên kết cục bộ, phải giữ nguyên thứ tự BST, đủ nút và metadata; khi quay trong AVL còn phải khôi phục cân bằng theo đúng tình huống.
- **Xóa bảng băm dò tuyến tính** phải bảo toàn khả năng đi dọc chuỗi dò đến các khóa còn sống; tombstone và tái băm là những công cụ để giữ bất biến ấy.
- **Mở rộng mảng động** phải bảo toàn dãy phần tử logic qua lần cấp phát lại; chiến lược tăng dung lượng theo hệ số nhân đem lại `O(1)` **khấu hao** cho append, dù một lần mở rộng riêng lẻ có thể tốn tuyến tính.

Khi chọn hoặc tự cài đặt cấu trúc dữ liệu, hãy luôn ghi rõ hợp đồng thao tác, bất biến, trường hợp biên và mô hình tham chiếu. Một bộ kiểm thử có ví dụ đối kháng, kiểm tra trạng thái sau mỗi bước và phép đo chi phí đúng bản chất sẽ giúp phát hiện lỗi nhanh hơn và tạo nền tảng vững cho phần chứng minh tính đúng đắn.
