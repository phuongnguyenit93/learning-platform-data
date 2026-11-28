# Sao chép toàn bộ và chia sẻ cấu trúc giữa các phiên bản

Giả sử nền tảng học tập có một cây tìm kiếm nhị phân (*Binary Search Tree – BST*) lưu **15.000 mã học viên và điểm tổng kết**. Sau khi điểm của đúng **một** học viên được điều chỉnh, hệ thống phải giữ trạng thái trước đó để đối chiếu và đồng thời tạo một phiên bản mới cho báo cáo hiện hành.

Có hai cách thực hiện dễ hình dung:

1. **Sao chép toàn bộ** (*full copy*): tạo lại mọi nút của cây, rồi đưa thay đổi vào bản mới.
2. **Chia sẻ cấu trúc** (*structural sharing*): chỉ tạo các nút nằm trên đường bị ảnh hưởng bởi cập nhật, còn những nhánh không thay đổi được các phiên bản cùng dùng.

Cả hai đều có thể giữ nguyên phiên bản cũ. Nhưng chúng khác rất lớn về **số nút được cấp phát, thời gian cập nhật, mức sử dụng bộ nhớ và yêu cầu bất biến của dữ liệu được chia sẻ**.

Bài thuộc chương **Bất biến và phiên bản** của module **Cấu trúc dữ liệu**. Ta sẽ so sánh hai chiến lược, minh họa bằng mảng, stack và BST, viết Python tự chứa để kiểm tra bằng **danh tính đối tượng**, chứng minh vì sao path copying đúng, phân tích trường hợp cây cân đối/cây lệch, đồng thời thảo luận alias, bộ nhớ của lịch sử phiên bản và giới hạn của chia sẻ dữ liệu trong môi trường đồng thời.

## 1. Hợp đồng chung: cập nhật không phá phiên bản cũ

Một cấu trúc dữ liệu có khả năng lưu phiên bản (*persistent data structure*) cho phép một thao tác tạo trạng thái mới mà **không sửa nội dung phiên bản trước đó**.

Giao diện khái quát:

```text
v0 = create(initial_data)
v1 = update(v0, key, new_value)
v2 = update(v1, other_key, other_value)

read(v0) → dữ liệu ban đầu
read(v1) → chỉ thay đổi thứ nhất
read(v2) → cả hai thay đổi
```

Nếu hai phiên bản cùng tồn tại, một truy vấn trên `v0` phải tiếp tục trả nội dung thuộc `v0`, ngay cả sau khi `v1` hoặc `v2` được tạo.

**Không cần tạo một bản sao đầy đủ để đạt hợp đồng này.** Đó là điểm khác biệt quan trọng giữa **mục tiêu giữ phiên bản** và **chiến lược hiện thực**.

### Ba điều kiện để gọi kết quả là một phiên bản đúng nghĩa

- **Giữ nội dung cũ:** cập nhật không sửa nút, liên kết hoặc phần tử thuộc phiên bản cũ theo phạm vi hợp đồng.
- **Tạo nội dung mới:** truy vấn từ gốc mới phản ánh đúng thao tác cập nhật.
- **Các phiên bản độc lập về mặt quan sát:** mọi phần tử dùng chung có trạng thái ổn định, hoặc được kiểm soát bằng quy tắc ownership/snapshot rõ ràng.

Điều kiện thứ ba thường bị bỏ sót khi cấu trúc ngoài bất biến nhưng **payload bên trong mutable**.

## 2. Bắt đầu từ mảng: mutable, sao chép đầy đủ và phiên bản cũ

Một list Python bình thường là mutable:

```python
scores = [8, 9, 7]
old_reference = scores

scores[1] = 10

assert old_reference is scores
assert old_reference == [8, 10, 7]
```

`old_reference` chỉ là alias; nó không lưu được điểm `9` trước khi cập nhật.

Để giữ giá trị cũ, ta có thể sao chép list rồi thay một vị trí trên bản mới:

```python
v0 = [8, 9, 7]
v1 = v0.copy()
v1[1] = 10

assert v0 == [8, 9, 7]
assert v1 == [8, 10, 7]
assert v0 is not v1
```

Đối với **dãy các số nguyên bất biến**, cách này tạo hai phiên bản nội dung độc lập ở cấp list.

### Độ phức tạp

Nếu list dài `n`:

- `v0.copy()` sao chép `n` tham chiếu: **`O(n)` thời gian**.
- Bản list mới có `n` ô tham chiếu: **`O(n)` bộ nhớ thêm**.
- `v1[i] = x` sửa một vị trí trên bản mới: **`O(1)`**.
- Tổng cập nhật bằng copy-then-write: **`O(n)` thời gian, `O(n)` bộ nhớ mới**.

Dù chỉ sửa **một phần tử**, cách sao chép toàn bộ list vẫn phải sao chép đủ **`n` vị trí**.

### Cẩn thận với phần tử mutable

```python
v0 = [[8, 9], [7]]
v1 = v0.copy()

assert v1 is not v0
assert v1[0] is v0[0]

v1[0].append(10)

assert v0[0] == [8, 9, 10]
```

Lệnh `copy()` chỉ là **sao chép nông**. Hai list ngoài tách biệt nhưng cùng trỏ tới **list trong**. Khi muốn lưu lịch sử, **sao chép cấp ngoài chưa đủ** nếu phần tử được sửa tại chỗ.

## 3. Chiến lược 1: sao chép toàn bộ cấu trúc

**Full copy** nghĩa là khi tạo phiên bản mới, ta cấp phát một cấu trúc mới, với những **nút hoặc ô chứa của cấu trúc** được sao chép từ phiên bản cũ.

Với một cây nhị phân:

```text
Phiên bản v0:                     Phiên bản v1:

         40 (A)                           40 (A')
        /      ╲                         /       ╲
     20 (B)   60 (C)                   20 (B')    60 (C')
               /    ╲                            /    ╲
            50 (D)  70 (E)                    50 (D')  70 (E')

Tất cả A', B', C', D', E' là đối tượng nút mới.
Có thể sửa dữ liệu ở D' mà không sửa D.
```

Ở đây, **sao chép toàn bộ nút** là một chính sách có chủ đích để bảo vệ liên kết cây. Nó chưa tự khẳng định rằng mọi giá trị con phức tạp của từng nút cũng đã được sao chép sâu.

### Ưu điểm

- Dễ hình dung: mỗi phiên bản có **các nút riêng**.
- Một bản sao độc lập về liên kết thuận tiện nếu sau đó cần các cập nhật mutable riêng biệt.
- Dễ truyền các phiên bản độc lập cho những thành phần vốn dùng API mutable, nếu đã xử lý đúng ownership của phần tử.
- Ít phụ thuộc vào kỹ thuật thay đổi đường đi trong cây.

### Nhược điểm

- Sao chép toàn cây `n` nút tốn **`Θ(n)` thời gian và `Θ(n)` nút mới** mỗi lần.
- Nếu mỗi cập nhật chỉ đổi một khóa, phần lớn các bản sao là **dữ liệu giống phiên bản cũ**.
- Giữ nhiều phiên bản có thể làm tổng bộ nhớ tăng nhanh.
- Sao chép toàn bộ liên kết **không giải quyết alias của value mutable** nếu chỉ mang lại tham chiếu value cũ.

Một bản sao đầy đủ có thể vẫn là lựa chọn hợp lý khi dữ liệu nhỏ, số lần cập nhật ít, hoặc nghiệp vụ yêu cầu những bản độc lập hoàn toàn về sở hữu.

## 4. Chiến lược 2: chia sẻ phần không thay đổi

**Structural sharing** sử dụng lại **chính những đối tượng nút cũ** ở vị trí không bị tác động. Chỉ phần bắt buộc thay đổi mới được cấp phát lại.

Dùng cùng cây trên, giả sử chèn khóa `55` thành **con phải của `50`**:

```text
v0:

              40 (A)
             /      ╲
          20 (B)   60 (C)
                   /    ╲
                50 (D)  70 (E)

v1:

              40 (A')                 ← mới
             /      ╲
          20 (B)   60 (C')            ← B chia sẻ, C' mới
                   /    ╲
                50 (D')  70 (E)       ← D' mới, E chia sẻ
                    ╲
                    55 (F)            ← mới
```

Những nút `A', C', D', F` được tạo mới. **Nút `B` và `E` không được sao chép**.

Phiên bản `v0` vẫn trỏ tới `A, C, D` cũ. Phiên bản `v1` trỏ tới `A', C', D', F` và chia sẻ `B, E`.

### Ý nghĩa thật sự của “dùng chung”

Một nút được chia sẻ nếu hai gốc phiên bản dẫn tới **cùng đối tượng nút trong bộ nhớ**, không chỉ hai nút có khóa hoặc giá trị bằng nhau.

Trong Python:

```python
a is b   # Cùng một đối tượng
a == b   # Có thể chỉ bằng nhau về giá trị
```

Để kiểm tra chia sẻ cấu trúc, ta dùng **`is`**, không chỉ `==`.

## 5. Khác biệt giữa chia sẻ cấu trúc và sao chép nông

Cả hai chiến lược có thể tái sử dụng đối tượng nào đó, nhưng mục tiêu và cách tổ chức khác nhau.

**Sao chép nông (*shallow copy*):**

```text
list mới
  ├──► phần tử X cũ
  └──► phần tử Y cũ

Chỉ tách container ngoài.
Các phần tử X/Y có thể vẫn mutable.
```

**Structural sharing trong một cấu trúc persistent:**

```text
root_v0 ──► nút cũ ──► cây con bất biến
root_v1 ──► nút mới ──► cùng cây con bất biến
```

Ở đây, **nút được chia sẻ phải không bị sửa**, và những phần tử được chia sẻ phải có ngữ nghĩa ổn định trong phạm vi phiên bản.

Không phải mọi sao chép nông đều là một cài đặt persistent đúng. Ngược lại, structural sharing thường **cố ý giữ tham chiếu chung** để giảm lượng cấp phát, nhưng dựa vào quy tắc **không sửa nút cũ**.

## 6. Một sơ đồ bộ nhớ: tách biệt hoàn toàn và DAG chia sẻ

Nếu tạo hai bản sao độc lập của một cây, mỗi gốc dẫn tới các đối tượng riêng:

```text
Full copy:

root_v0 ──► A ──► B, C ──► D, E
root_v1 ──► A'──► B',C' ──► D',E'

Không nút cấu trúc nào có cùng danh tính qua hai bản.
```

Nếu dùng chia sẻ cấu trúc:

```text
Structural sharing:

root_v0 ──► A ──► B, C ──► D, E
root_v1 ──► A'──► B, C' ──► D', E, F

Nút B và E có nhiều đường tham chiếu từ các phiên bản.
```

Từng phiên bản riêng vẫn là **một cây hợp lệ**, nhưng tập hợp toàn bộ các nút có thể được nhìn từ nhiều gốc tạo thành **đồ thị có hướng không chu trình (DAG)** do có nhánh dùng chung.

### “Cùng nút” không đồng nghĩa “cùng vị trí trong mọi bản”

Một nút con bất biến có thể được tái sử dụng dưới **các bản cha khác nhau** ở các phiên bản. Vì vậy, một trường `parent` mutable nằm ngay trong nút con dùng chung thường không phù hợp: nó không thể biểu diễn đồng thời hai quan hệ cha theo hai gốc khác nhau.

Đối với cấu trúc persistent, khi cần lần ngược tổ tiên, ta có thể giữ **stack đường đi gắn với phiên bản**, hoặc dùng cấu trúc zipper thay vì sửa `node.parent`.

## 7. So sánh từng bước khi thay một khóa trong BST

Ta dùng một BST cân đối có khóa `1..15`:

```text
                       8
                    /     ╲
                   4       12
                 /  ╲     /   ╲
                2    6   10    14
               / ╲  / ╲  / ╲   / ╲
              1   3 5  7 9  11 13 15
```

Giả sử muốn cập nhật **value của khóa `14`**, không đổi `key` hoặc hình dạng logic của BST.

### Nếu full copy

- Bản mới có **15 nút mới**.
- Tại nút mới mang khóa `14`, thay value.
- Mọi nút khác có nội dung cũ nhưng **danh tính đối tượng mới**.
- Gốc cũ vẫn trỏ tới 15 nút ban đầu.

Nếu giữ `v0` và `v1`, có thể có **30 đối tượng nút** (không tính các đối tượng payload dùng chung) cho hai phiên bản này.

### Nếu structural sharing theo đường tìm

Đường tìm khóa `14` là:

```text
8 → 12 → 14
```

Ta tạo **3 nút mới**: bản của `14` mang value mới, bản của `12` trỏ tới nút `14'`, và bản của gốc `8` trỏ tới `12'`.

Các cây con dưới `4`, `10` và các nút `13,15` không bị sửa. Chúng được chia sẻ giữa hai phiên bản.

Nếu giữ `v0` và `v1`, số đối tượng nút phân biệt là **15 + 3 = 18**.

### Bảng so sánh tại cùng một trạng thái

| Đại lượng | Full copy | Structural sharing |
| --- | ---: | ---: |
| Số nút cây cũ | 15 | 15 |
| Số nút mới khi sửa `14` | 15 | 3 |
| Nút cũ có bị sửa? | Không | Không |
| Có dùng chung nút cấu trúc giữa 2 gốc? | Không | Có |
| Gốc phiên bản mới | Mới | Mới |
| Số nút phân biệt giữ bởi 2 bản | 30 | 18 |

Các con số này thuộc **ví dụ cụ thể**; không phải mọi cập nhật trên mọi cây đều tạo đúng ba nút. Yếu tố chi phối path copying là **độ dài đường cập nhật `h`**.

## 8. Python: kiểu nút BST không cho sửa trường

Ta dùng `dataclasses.dataclass(frozen=True)` để biểu diễn nút. Các khóa là `int` phân biệt, còn payload là `str` hoặc `None`. Chúng ta không dùng list mutable làm value trong phần kiểm thử chính.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Node:
    key: int
    value: str | None
    left: "Node | None" = None
    right: "Node | None" = None
```

Nút `Node` không cho gán lại `key`, `value`, `left` hay `right` qua API thông thường:

```python
sample = Node(10, "A")

try:
    sample.value = "B"
except AttributeError:
    pass
else:
    raise AssertionError("Nút frozen không cho sửa trường")
```

**Lưu ý:** `frozen=True` bảo vệ **thuộc tính nút**, không tự đóng băng những đối tượng con tùy ý. Vì thế, việc chọn kiểu payload ổn định là **một phần của thiết kế**.

## 9. Dựng BST cân đối từ dãy khóa đã sắp

Ta cần một cây ban đầu cân đối để thấy rõ lợi ích của path copying.

Hàm sau nhận danh sách cặp `(key,value)` đã sắp tăng nghiêm ngặt theo `key`, chọn trung vị của mỗi đoạn để dựng các nhánh.

```python
def build_balanced(sorted_items):
    """Tạo BST cân đối, không sửa input."""
    for i in range(1, len(sorted_items)):
        if not (
            sorted_items[i - 1][0] < sorted_items[i][0]
        ):
            raise ValueError("Các khóa phải tăng nghiêm ngặt")

    def build(lo, hi):
        if lo >= hi:
            return None

        mid = lo + (hi - lo) // 2
        key, value = sorted_items[mid]

        return Node(
            key=key,
            value=value,
            left=build(lo, mid),
            right=build(mid + 1, hi),
        )

    return build(0, len(sorted_items))


v0 = build_balanced([
    (key, f"v{key}") for key in range(1, 16)
])

assert v0.key == 8
assert v0.left.key == 4
assert v0.right.key == 12
assert v0.right.right.key == 14
```

Vì chỉ số giữa chia đôi số phần tử, cây có chiều cao **4**. Việc dựng một lần từ dãy đã sắp tốn **`O(n)` thời gian**, không cần chèn lần lượt vào BST không tự cân bằng.

## 10. Hàm tìm khóa dùng chung cho mọi phiên bản

Một điểm thuận lợi là **thuật toán đọc không cần biết cây được dựng bằng full copy hay structural sharing**. Nó chỉ nhận một gốc phiên bản và tuân theo thứ tự BST.

```python
def find(root, key):
    """Trả (found, value), phân biệt thiếu khóa với value=None."""
    node = root

    while node is not None:
        if key == node.key:
            return True, node.value

        node = (
            node.left if key < node.key
            else node.right
        )

    return False, None


def inorder_items(root):
    """Sinh (key,value) theo thứ tự khóa tăng."""
    stack = []
    node = root

    while node is not None or stack:
        while node is not None:
            stack.append(node)
            node = node.left

        node = stack.pop()
        yield node.key, node.value
        node = node.right


assert find(v0, 14) == (True, "v14")
assert find(v0, 100) == (False, None)
assert [k for k, _ in inorder_items(v0)] == list(range(1, 16))
```

`find` trả cặp `(found,value)` thay vì chỉ value. Nhờ thế, một khóa tồn tại và có value `None` **không bị nhầm với khóa không tồn tại**.

## 11. Python: sao chép tất cả nút và cập nhật value

Trước tiên, tạo hàm chỉ **nhân bản toàn bộ nút**, giữ nguyên giá trị của mỗi nút. Hàm này **không phải sao chép sâu payload**; nó đúng với ví dụ vì payload là `str` và `None`.

```python
def clone_all_nodes(root):
    """Sao chép mọi nút. Payload được dùng lại theo tham chiếu."""
    if root is None:
        return None

    return Node(
        root.key,
        root.value,
        clone_all_nodes(root.left),
        clone_all_nodes(root.right),
    )
```

Để cập nhật một khóa và **tạo đúng một bản sao mới cho mỗi nút cũ**, ta kết hợp bước chép và thay đổi trong **một lần duyệt**, thay vì chép tất cả rồi lại path-copy thêm một lần nữa:

```python
def full_copy_put(root, key, value):
    """Tạo bản cây mới không chia sẻ nút cấu trúc với root.

    Nếu key chưa có thì chèn; nếu đã có thì thay value.
    """

    if root is None:
        return Node(key, value)

    if key < root.key:
        return Node(
            root.key,
            root.value,
            full_copy_put(root.left, key, value),
            clone_all_nodes(root.right),
        )

    if key > root.key:
        return Node(
            root.key,
            root.value,
            clone_all_nodes(root.left),
            full_copy_put(root.right, key, value),
        )

    # Cùng key: tạo nút mới và copy cả hai cây con.
    return Node(
        root.key,
        value,
        clone_all_nodes(root.left),
        clone_all_nodes(root.right),
    )
```

### Vì sao hàm này tốn Θ(n) khi cây có n nút?

Mỗi nút cũ đi vào đúng một trong hai dạng xử lý:

- Nút trên đường tìm: xử lý bởi `full_copy_put`.
- Nút ngoài đường tìm: xử lý bởi `clone_all_nodes`.

Vì vậy, mọi nút cũ được tạo lại **đúng một lần**. Nếu chèn một khóa chưa tồn tại, thêm một nút mới nữa. Với `n` nút đầu vào:

```text
Nút mới nếu cập nhật key đã có: n
Nút mới nếu chèn key mới:       n + 1

Thời gian xây bản mới:          Θ(n + 1)
Bộ nhớ nút mới:                Θ(n + 1)
Bộ nhớ call stack:              O(h)
```

Với `n >= 1`, thời gian và số nút mới thường viết gọn là **`Θ(n)`**. Kể cả khi nút cần sửa nằm ngay gốc, full copy vẫn nhân bản mọi cây con.

## 12. Kiểm thử full copy: cây cũ và cây mới độc lập về nút

```python
v_full = full_copy_put(v0, 14, "updated")

assert find(v0, 14) == (True, "v14")
assert find(v_full, 14) == (True, "updated")

assert [k for k, _ in inorder_items(v_full)] == list(range(1, 16))
assert v_full is not v0
assert v_full.left is not v0.left
assert v_full.right is not v0.right

# Toàn bộ nút là mới, kể cả nhánh không đổi.
assert v_full.left.left is not v0.left.left
```

Hai cây có thể chứa nhiều cặp khóa–giá trị bằng nhau nhưng **không dùng chung nút cấu trúc**.

### Ưu điểm phụ của hai cây độc lập về nút

Nếu muốn chuyển một bản sao sang dạng mutable và sửa riêng những liên kết trong đó, bản copy toàn bộ làm các nút không bị chia sẻ giữa hai phiên bản. Tuy nhiên, nếu payload là đối tượng mutable được sao chép nông, **độc lập về nút chưa có nghĩa độc lập về payload**.

Một thiết kế lưu lịch sử phải xác định rõ nó cần bảo vệ **chỉ liên kết cây** hay **toàn bộ trạng thái quan sát được**.

## 13. Python: path copying và chia sẻ các nhánh không đổi

Bây giờ thay `full_copy_put` bằng hàm chỉ tạo nút trên **đường tìm khóa**.

```python
def path_copy_put(root, key, value):
    """Cập nhật BST theo persistent path copying.

    Trả gốc mới; không sửa root hoặc các nút cũ.
    """

    if root is None:
        return Node(key, value)

    if key < root.key:
        new_left = path_copy_put(root.left, key, value)

        # Không có thay đổi logic ở cây con.
        if new_left is root.left:
            return root

        return Node(
            root.key, root.value,
            new_left, root.right
        )

    if key > root.key:
        new_right = path_copy_put(root.right, key, value)

        if new_right is root.right:
            return root

        return Node(
            root.key, root.value,
            root.left, new_right
        )

    # Key đã tồn tại: chỉ thay payload tại nút này.
    if root.value == value:
        return root

    return Node(
        root.key, value,
        root.left, root.right
    )
```

### Nhìn vào điểm quyết định

```text
return Node(
    root.key,
    root.value,
    new_left,   # cây con bị thay đổi
    root.right  # cây con không đổi, dùng lại chính đối tượng cũ
)
```

Đây là **structural sharing có chủ đích**. Không có lệnh nào như `root.right = ...` hay `root.left = ...`; mọi bản cha mới được tạo bằng hàm khởi tạo `Node`.

Nếu cập nhật `key` đã có nhưng `value` bằng cũ, hàm trả lại chính `root`. Những lời gọi tổ tiên cũng có thể nhìn thấy **tham chiếu không đổi** và trả tiếp nút cũ, **không cấp phát**.

## 14. Kiểm thử path copying: chính xác ba nút mới

```python
v_shared = path_copy_put(v0, 14, "updated")

assert find(v0, 14) == (True, "v14")
assert find(v_shared, 14) == (True, "updated")

assert [k for k, _ in inorder_items(v_shared)] == list(range(1, 16))

assert v_shared is not v0
assert v_shared.left is v0.left

# Đường 8 → 12 → 14 được tạo lại.
assert v_shared.right is not v0.right
assert v_shared.right.right is not v0.right.right

# Cây con của 10 không thuộc đường sửa, được giữ nguyên.
assert v_shared.right.left is v0.right.left

# Nút 13 và 15 nằm dưới 14, không đổi và được chia sẻ.
assert v_shared.right.right.left is v0.right.right.left
assert v_shared.right.right.right is v0.right.right.right
```

Một đoạn mã đọc `v0` cũ vẫn nhận value `"v14"`, còn truy vấn từ `v_shared` trả `"updated"`.

### Vì sao không được sửa nút chia sẻ?

Nếu sau khi tạo `v_shared` ta dùng một thao tác “tối ưu” để sửa `v0.right.left` tại chỗ, nhiều gốc phiên bản có thể cùng quan sát thay đổi ấy. Điều đó phá chính lời hứa về tính bền vững.

**Structural sharing an toàn dựa trên bất biến của các nút được chia sẻ**, không chỉ dựa trên việc số lần copy ít hơn.

## 15. Đếm số nút vật lý: khác số nút nhìn thấy qua từng gốc

Với cấu trúc persistent, cần phân biệt:

- **Số nút logic của một phiên bản:** số nút có thể tới được từ gốc phiên bản ấy.
- **Số đối tượng nút phân biệt của tất cả phiên bản đang giữ:** đếm mỗi **danh tính đối tượng** chỉ một lần, ngay cả khi nhiều gốc cùng tham chiếu tới nó.

Một hàm để đếm các đối tượng nút phân biệt:

```python
def unique_node_count(roots):
    """Đếm số đối tượng Node khác nhau qua nhiều gốc."""
    seen = set()
    pending = list(roots)

    while pending:
        node = pending.pop()

        if node is None:
            continue

        marker = id(node)
        if marker in seen:
            continue

        seen.add(marker)
        pending.append(node.left)
        pending.append(node.right)

    return len(seen)


def node_count(root):
    """Số nút logic của một BST không có chu trình."""
    return unique_node_count([root])
```

### Đối chiếu full copy và sharing

```python
assert node_count(v0) == 15
assert node_count(v_full) == 15
assert node_count(v_shared) == 15

assert unique_node_count([v0, v_full]) == 30
assert unique_node_count([v0, v_shared]) == 18
```

**Bài học:** số nút logic của một phiên bản có thể **không đổi**, trong khi chi phí bộ nhớ vật lý của **hai phiên bản được giữ cùng lúc** khác nhau rõ rệt.

### Khi nào nên dùng đếm theo danh tính?

Trong bài tập hoặc công cụ chẩn đoán, `unique_node_count` hữu ích để kiểm chứng structural sharing. Tuy nhiên, chính phép đếm này tốn **`O(U)` thời gian và `O(U)` bộ nhớ** với `U` đối tượng nút phân biệt qua các gốc, nên không nên chạy sau mọi thao tác cập nhật ở hệ thống lớn.

## 16. Chứng minh bản sao đầy đủ không làm đổi phiên bản cũ

Xét `full_copy_put` với đầu vào là cây BST hợp lệ, khóa duy nhất.

**Trường hợp cây rỗng:** tạo một nút mới, cây cũ vẫn rỗng.

**Trường hợp nút có khóa khác khóa cần cập nhật:** tạo nút mới mang khóa và giá trị của nút cũ. Một phía được cập nhật đệ quy, phía còn lại được nhân bản bằng `clone_all_nodes`.

**Trường hợp khóa bằng nhau:** tạo nút mới mang value mới, sao chép cả hai cây con.

Không trường hợp nào gán vào các trường của nút cũ. Vì mỗi cây con cũ được duyệt và tạo lại bằng các nút mới, mọi nút cấu trúc của phiên bản mới **độc lập danh tính** với nút thuộc phiên bản cũ.

Bất biến BST được duy trì vì thao tác chỉ **cập nhật value tại khóa đã có** hoặc **chèn khóa mới đúng đường so sánh**; thuật toán không đổi vị trí của các khóa cũ.

**Lưu ý phạm vi chứng minh:** nó chứng minh **liên kết và khóa nút** không bị sửa. Nếu value là đối tượng mutable được dùng lại theo tham chiếu, cần thêm điều kiện để bảo đảm phiên bản cũ không bị thay đổi nội dung quan sát.

## 17. Chứng minh path copying giữ tính đúng và chia sẻ an toàn

Ta chứng minh theo cấu trúc cây đầu vào.

### Cơ sở

Nếu `root is None`, `path_copy_put` tạo nút mới chứa khóa. Cây rỗng cũ không bị sửa.

### Bước đệ quy sang trái

Khi `key < root.key`, thay đổi chỉ xảy ra trong cây con trái. Theo giả thiết quy nạp, `path_copy_put(root.left,...)` trả một cây con mới hợp lệ mà không sửa cây trái cũ.

Ta tạo nút mới mang khóa và value của gốc cũ, nối:

- `left = new_left`, cây con vừa thay đổi;
- `right = root.right`, **chính cây con phải cũ**.

Vì mọi khóa trong `new_left` vẫn nhỏ hơn khóa gốc và các khóa bên phải vẫn lớn hơn, bất biến BST không bị phá.

Bản thân `root` không bị sửa, vì ta tạo một đối tượng `Node` mới.

### Bước đệ quy sang phải

Hoàn toàn đối xứng: cây trái dùng chung, cây phải là bản mới, rồi tạo nút gốc mới.

### Trường hợp khóa đã có

Chỉ value thay đổi; hai cây con và khóa được giữ nguyên. Tạo nút mới mang payload mới, nên thứ tự BST vẫn đúng.

Nếu value không đổi, trả lại gốc cũ: không có gì cần sửa hoặc sao chép.

### Kết luận

Với payload có ngữ nghĩa ổn định và so sánh khóa nhất quán, `path_copy_put` bảo đảm:

1. **Tính đúng của phiên bản mới** về tập khóa và giá trị cập nhật.
2. **Không sửa trạng thái cũ**.
3. **Tái sử dụng đúng nhánh không thay đổi**, nên chỉ cần số nút mới tỷ lệ với độ dài đường cập nhật.

Đó là cơ sở logic để dùng structural sharing cho các phiên bản.

## 18. Độ phức tạp chính: Θ(n) so với O(h)

Gọi:

- `n`: số nút trong một phiên bản BST.
- `h`: chiều cao BST, tính bằng số nút trên đường gốc–lá dài nhất.
- `k`: số phần tử được trả về khi duyệt khoảng.

Giả định một lần so sánh khóa, đọc tham chiếu và tạo nút đều tốn `O(1)`.

| Thao tác | Full copy | Structural sharing/path copying |
| --- | --- | --- |
| Cập nhật một key đã có | **`Θ(n)`** thời gian | **`O(h)`** thời gian |
| Số nút mới cho một key đã có | **`n`** | Tối đa `h`, có thể 0 nếu no-op |
| Chèn một key mới | **`Θ(n+1)`** thời gian | **`O(h+1)`** thời gian |
| Số nút mới khi chèn key mới | **`n+1`** | Tối đa `h+1` |
| Bộ nhớ call stack ở mã đệ quy | `O(h)` | `O(h)` |
| Đọc key từ một phiên bản | `O(h)` | `O(h)` |
| Duyệt hết một phiên bản | `Θ(n)` | `Θ(n)` |

**`O(h)` là độ phức tạp tổng quát của BST**, không tự động là `O(log n)`.

- Nếu BST **cân đối**, `h=O(log n)`, nên cập nhật path copying có thể tốn **`O(log n)`**.
- Nếu BST **suy biến** thành một chuỗi, `h=Θ(n)`, nên path copying có thể tốn **`Θ(n)`**.
- Full copy vẫn phải chép toàn bộ nút bất kể cây cân đối hay không.

Nếu ứng dụng cần bảo đảm trường hợp xấu nhất là logarit sau nhiều lần thêm/xóa, nên dùng **cấu trúc persistent tự cân bằng** với phép quay/cập nhật triển khai đúng, không chỉ gắn `frozen=True` cho BST thường.

## 19. Tại sao cùng tập dữ liệu, hiệu quả có thể rất khác?

Một cây cân đối và cây lệch có cùng `n` nút nhưng chiều cao khác nhau:

```text
15 khóa cân đối: h = 4
15 khóa chuỗi:   h = 15
```

Khi cập nhật một khóa rất sâu:

- Full copy vẫn tạo **15 nút mới**.
- Path copying trên cây cân đối có thể tạo khoảng **4–5 nút** tùy vị trí chèn hoặc cập nhật.
- Path copying trên cây lệch có thể tạo **15–16 nút**, gần như không còn lợi thế về số nút.

Structural sharing đặc biệt hiệu quả khi phần thay đổi **nhỏ so với toàn cấu trúc** và đường từ gốc tới vị trí thay đổi **ngắn**.

Nó không phải phép màu biến mọi cấu trúc yếu về chiều cao thành cấu trúc hiệu quả.

## 20. Giữ m phiên bản: tổng bộ nhớ khác nhau thế nào?

Giả sử có một BST ban đầu với `n` nút, sau đó thực hiện `m` cập nhật **không thay đổi số khóa**. Ta giữ **tất cả** các phiên bản.

### Full copy

Mỗi lần cập nhật tạo một cây mới với `n` nút. Nếu mọi phiên bản được giữ:

```text
Số nút vật lý:

n + n + n + ... + n
    m lần bản mới

= (m + 1) · n
= Θ(mn + n)
```

Bộ nhớ chỉ dành cho nút cấu trúc tăng **tuyến tính theo số phiên bản nhân số nút**.

### Structural sharing

Nếu mỗi lần cập nhật làm thay đổi một khóa và sao chép tối đa `h_i` nút mới:

```text
Số nút cấp phát qua lịch sử:

n + h_1 + h_2 + ... + h_m

= O(n + tổng h_i)
```

Nếu mọi phiên bản đều có `h_i <= H`:

```text
O(n + m · H)
```

Với cây cân đối có `n` khóa cố định và `H=O(log n)`:

```text
O(n + m log n)
```

Đây là **giới hạn trên số nút được cấp phát**; số nút thực sự còn sống có thể thấp hơn nếu một số gốc/nút không còn được tham chiếu.

### Nếu có cả thao tác chèn khóa mới

Một lần chèn vào cây rỗng vẫn tạo một nút dù `h=0`. Vì vậy công thức an toàn hơn khi có cây rỗng và số khóa thay đổi là **`O(n_0 + tổng (h_i+1))`**, với `n_0` là số nút ban đầu.

Nếu số khóa tăng tới `n_0+m` và mọi cây luôn cân đối, có thể dùng cận tổng **`O(n_0 + m log(n_0+m+1))`** cho số nút được cấp phát.

### Đừng tính payload hai lần mà không nói rõ

Những công thức trên đếm **đối tượng nút cấu trúc**. Nếu mỗi value là ảnh, danh sách lớn hoặc blob dữ liệu, chi phí payload có thể chi phối toàn bộ bộ nhớ. Full copy có thể **dùng chung payload mutable** một cách nguy hiểm, còn deep copy payload có thể tốn đáng kể hơn chi phí sao chép nút.

## 21. Hai phiên bản bằng nhau về nội dung có thể có chi phí rất khác

Nếu gọi:

```python
same_full = full_copy_put(v0, 14, "v14")
same_shared = path_copy_put(v0, 14, "v14")

assert list(inorder_items(same_full)) == list(inorder_items(v0))
assert list(inorder_items(same_shared)) == list(inorder_items(v0))
```

Hai thao tác đều không làm thay đổi **trạng thái logic** so với `v0`.

Nhưng:

```python
assert same_full is not v0
assert same_full.left is not v0.left

assert same_shared is v0
```

Full copy được thiết kế để **luôn nhân bản mọi nút**, dù dữ liệu không thay đổi. Bản path copying kiểm tra trường hợp không đổi và **dùng lại toàn bộ gốc cũ**.

**Tối ưu no-op** giúp giảm cấp phát trong các ứng dụng có nhiều lượt ghi lại cùng giá trị, nhưng cần cân nhắc cách so sánh value: với payload mutable hoặc đối tượng có phép `==` phức tạp, việc “bằng nhau” chưa tự bảo đảm cùng ngữ nghĩa lịch sử.

## 22. Structural sharing ở stack/danh sách liên kết

BST có thể cần sao chép đường từ gốc, còn **danh sách liên kết bất biến** đặc biệt phù hợp cho thao tác thêm đầu.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Link:
    value: int
    next: "Link | None" = None


def push(head, value):
    return Link(value, head)


def pop(head):
    if head is None:
        raise IndexError("Danh sách rỗng")
    return head.value, head.next


def list_values(head):
    result = []
    while head is not None:
        result.append(head.value)
        head = head.next
    return result


v0_list = Link(20, Link(30))
v1_list = push(v0_list, 10)

assert list_values(v0_list) == [20, 30]
assert list_values(v1_list) == [10, 20, 30]

assert v1_list.next is v0_list
```

### Phân tích cập nhật ở đầu

- **Structural sharing:** thêm một nút mới có `next = v0_list` → **`O(1)` thời gian**, **1 nút mới**.
- **Sao chép đầy đủ danh sách:** tạo lại tất cả `n` nút cũ cùng một nút mới → **`Θ(n)` thời gian**, **`n+1` nút mới**.

Khi `pop`, bản persistent chỉ trả con trỏ `next` làm gốc của trạng thái mới, **không cần xóa hoặc sửa nút cũ**.

### Nhưng sửa phần tử thứ i thì sao?

Với danh sách liên kết đơn không có chỉ mục phụ, muốn thay phần tử tại chỉ số `i` (tính từ 0) mà không sửa nút cũ, thường cần sao chép **`i+1` nút tiền tố** và chia sẻ phần đuôi sau đó: **`O(i+1)`** thời gian/nút mới.

Do đó, hiệu quả phụ thuộc vào **thao tác và cấu trúc**, không chỉ vào việc có dùng structural sharing hay không.

## 23. Persistent vector: dùng cây thay cho copy cả mảng

Một mảng/tuple liên tiếp trong bộ nhớ thường phải sao chép nhiều tham chiếu khi cần tạo một phiên bản mới với một phần tử khác.

Một **persistent vector** thường sử dụng cây phân nhánh (ví dụ bậc `B`) để giữ vị trí các phần tử. Khi sửa một chỉ số:

1. Đi từ gốc tới lá/vị trí chứa phần tử đó.
2. Tạo bản sao các nút trên đường đi.
3. Những cây con khác được chia sẻ.
4. Trả gốc phiên bản mới.

```text
                 root
            /      |      ╲
         subtree subtree subtree
                    |
                 vị trí i

Chỉ các nút trên đường tới i phải được thay.
```

Với cây phân nhánh đều bậc `B`:

- Chiều cao xấp xỉ `O(log_B n)`.
- Số **nút cây** mới dọc một đường có thể `O(log_B n)`.
- Nếu mỗi nút phải sao chép một mảng con kích thước `O(B)`, chi phí **theo ô tham chiếu** có thể tới `O(B log_B n)`.

Đây là mô hình khái quát; cấu trúc vector persistent thực tế còn có phần đuôi (*tail*), các tối ưu khác và giới hạn độ phức tạp riêng.

**Không nên mặc định tuple Python có chi phí cập nhật như persistent vector chuyên dụng**. Chúng có biểu diễn và thuật toán cập nhật khác nhau.

## 24. Chia sẻ cấu trúc trong trie, cây đoạn và map

Ngoài BST, kỹ thuật dùng lại cây con không đổi còn áp dụng cho nhiều cấu trúc.

### Trie persistent

Khi thêm một từ vào trie, chỉ các nút thuộc **đường tiền tố** và nhánh mới phải tạo lại; những tiền tố/nhánh không liên quan có thể được chia sẻ. Chi phí phụ thuộc **độ dài khóa** và cách tổ chức bảng cạnh tại mỗi nút.

### Persistent segment tree

Khi cập nhật một vị trí trong dãy, chỉ đường từ gốc tới lá đại diện vị trí ấy thay đổi; các đoạn không bị ảnh hưởng được giữ nguyên. Với một cây đoạn nhị phân cân đối, thao tác cập nhật điểm tạo `O(log n)` nút mới.

### Persistent ordered map hoặc hash trie

Các cấu trúc map persistent có thể dùng cây tự cân bằng hoặc **HAMT** (*hash array mapped trie*). Mỗi phép cập nhật tạo một phiên bản mới và chia sẻ phần lớn cấu trúc, nhưng độ phức tạp phụ thuộc **bậc phân nhánh, độ dài mã băm, va chạm và giao diện cập nhật**.

### Không đánh đồng mọi “sharing” với tính bền vững

Một hệ thống có thể chia sẻ cache mutable giữa nhiều đối tượng để tiết kiệm bộ nhớ. Đó **không** tự là persistent data structure. Chỉ khi cập nhật **không thay đổi trạng thái quan sát của phiên bản cũ** ta mới đạt hợp đồng bền vững.

## 25. Khi một cập nhật chạm tới nhiều nơi

Path copying thường được giới thiệu với **một thay đổi theo một đường**. Nếu một thao tác tác động lên **nhiều nhánh**:

- Có thể phải tạo lại **hợp của các đường** dẫn tới các vị trí thay đổi.
- Những nút chung của nhiều đường có thể chỉ cần tạo lại **một lần** nếu thuật toán xử lý gộp.
- Cập nhật tuần tự từng khóa có thể sao chép một số tổ tiên **nhiều lần qua các phiên bản trung gian**.

Ví dụ khi cập nhật cả `3` và `14` trong cùng BST cân đối:

```text
              8
            /   ╲
           4     12
          /        ╲
         2         14
          ╲
           3

Hai đường cập nhật có nút 8 chung.
```

Một thuật toán **batch update** có thể tạo nút gốc `8` mới đúng một lần và xử lý hai cây con, còn việc gọi path copying hai lượt tạo hai phiên bản liên tiếp với hai bản gốc khác nhau.

### Khi sharing mang lại ít lợi ích

- Thay đổi **hầu hết các nút** của cây trong một thao tác.
- Cây quá lệch khiến đường chèn/xóa rất dài.
- Nút quá nhỏ và overhead cấp phát/thu gom rác đáng kể.
- Dữ liệu luôn được xuất/sắp tuần tự, còn tính locality của mảng liên tiếp quan trọng hơn.
- Mỗi phiên bản chỉ được dùng một lần và không cần giữ lịch sử.

Trong những tình huống này, full copy, cấu trúc mutable hoặc một batch rebuild có thể là lựa chọn tốt hơn tùy hợp đồng.

## 26. Chia sẻ an toàn đòi hỏi payload cũng ổn định

Nút `Node` của chúng ta có `frozen=True` và payload `str/None`. Nếu cho phép value là **list mutable**, việc chỉ tạo nút mới trên đường đi không bảo vệ nội dung list dùng chung.

```python
@dataclass(frozen=True)
class UnsafeNode:
    key: int
    value: list[int]
    left: "UnsafeNode | None" = None
    right: "UnsafeNode | None" = None


raw_scores = [8, 9]
old_root = UnsafeNode(10, raw_scores)

# Tạo một root mới trỏ tới chính nút cũ.
new_root = UnsafeNode(
    20, [10],
    left=old_root
)

raw_scores.append(7)

assert old_root.value == [8, 9, 7]
assert new_root.left.value == [8, 9, 7]
```

Hai gốc không sửa liên kết nút cũ, nhưng **giá trị quan sát của khóa `10` đã đổi**.

### Khắc phục bằng hợp đồng giá trị

Với dữ liệu điểm là `list[int]`, có thể chuẩn hóa khi đưa vào cấu trúc:

```python
@dataclass(frozen=True)
class SafeNode:
    key: int
    value: tuple[int, ...]
    left: "SafeNode | None" = None
    right: "SafeNode | None" = None


source = [8, 9]
stable_root = SafeNode(10, tuple(source))

source.append(7)

assert stable_root.value == (8, 9)
```

Với payload phức tạp hơn, có thể cần **giá trị bất biến sâu**, cơ chế sao chép phù hợp hoặc quyền sở hữu độc quyền. Đừng cho rằng `copy.deepcopy` tự biến đối tượng được sao chép thành bất biến: bản sao thường **vẫn có thể sửa** nếu API của nó cho phép.

### Full copy cũng có cùng rủi ro nếu chỉ chép nút

`clone_all_nodes` trong phần 11 tạo các nút mới, nhưng vẫn dùng `root.value` cũ. Nếu value là list mutable, hai cây full copy có thể **không chia sẻ nút** mà vẫn **chia sẻ list**.

Vì vậy, cần phân biệt:

- **Full copy của cấu trúc nút**.
- **Deep copy của đồ thị payload**.
- **Tính bất biến quan sát của các phiên bản**.

Ba ý này không tự kéo theo nhau.

## 27. Thứ tự khóa và metadata khi chia sẻ cây

Nếu một nút tham gia nhiều phiên bản, cần suy nghĩ về những trường phụ thuộc vào cấu trúc.

### Khóa và comparator

Một BST được tổ chức theo thứ tự `key`. Nếu đối tượng khóa mutable bị thay đổi sau khi một nút đã được đặt vào cây, các đường tìm kiếm có thể rẽ sai, dù không có liên kết con nào bị sửa.

**Không sửa thuộc tính dùng để so sánh khóa của một nút đang được chia sẻ.**

### Metadata subtree size / height

Nếu nút lưu kích thước cây con hoặc chiều cao:

```text
size(node) = 1 + size(left) + size(right)
height(node) = 1 + max(height(left), height(right))
```

Khi một liên kết trong phiên bản mới thay đổi, bản nút mới phải có **metadata được tính lại** theo hai cây con của **chính phiên bản mới**. Nút cũ vẫn giữ metadata của phiên bản cũ.

Không được cập nhật `old_node.subtree_size` tại chỗ nếu nó được một gốc lịch sử sử dụng.

### Parent pointer

Như đã đề cập, `parent` trong nút dùng chung không thể luôn biểu diễn đúng quan hệ cha ở mọi phiên bản. Một iterator có stack đường đi tính theo **gốc phiên bản cụ thể** thường phù hợp hơn.

### Cấu trúc tự cân bằng

Nếu dùng AVL hoặc đỏ–đen persistent, các phép quay phải được triển khai theo hướng **tạo nút mới và chia sẻ nhánh không đổi**, đồng thời cập nhật mọi metadata/màu ở các nút phiên bản mới.

**Path copying không tự làm BST thường cân bằng**; nó chỉ giữ phiên bản cũ khi thay đổi cây.

## 28. Vòng đời bộ nhớ và thu gom rác

Structural sharing giảm số nút **phải tạo mới**, nhưng cũng làm việc quản lý vòng đời phụ thuộc vào **các gốc còn được giữ**.

```text
history = [root_v0, root_v1, root_v2]

Nút X có thể được cả ba gốc sử dụng.
Nút Y chỉ có ở root_v0.
Nút Z chỉ có ở root_v2.
```

Nếu xóa `root_v0` khỏi lịch sử:

- `Y` **có thể** trở thành nút không còn được tham chiếu và được thu hồi.
- `X` vẫn cần giữ vì `root_v1` và `root_v2` còn sử dụng nó.
- Không thể suy ra một số byte chính xác sẽ được giải phóng ngay; còn phải tính các tham chiếu khác, iterator và cơ chế quản lý bộ nhớ.

### Retention policy

Một ứng dụng có thể:

- Giữ **10 phiên bản gần nhất** để hỗ trợ undo.
- Giữ phiên bản gắn nhãn checkpoint hoặc kỳ kiểm toán.
- Giữ bản snapshot trong thời gian một truy vấn dài đang dùng.
- Bỏ các gốc không còn cần đến để giải phóng các nút chỉ thuộc những phiên bản đó.

**Persistence không có nghĩa buộc phải lưu mọi phiên bản mãi mãi.** Nó chỉ cho phép phiên bản cũ **còn được giữ** tiếp tục sử dụng an toàn.

### Chi phí đỉnh

Khi tạo một bản mới, trong một thời gian **cây cũ và các nút mới có thể cùng tồn tại**. Full copy có thể cần không gian đỉnh gần gấp đôi số nút. Path copying thường tạo ít nút hơn nếu đường cập nhật ngắn, nhưng số phiên bản tích lũy vẫn phải được quản lý.

## 29. Phân nhánh phiên bản: cùng một gốc có thể tạo nhiều bản mới

Chia sẻ cấu trúc không chỉ có ích cho chuỗi `v0 → v1 → v2`, mà còn cho **nhiều nhánh** phát sinh từ cùng một trạng thái.

```python
v_A = path_copy_put(v0, 14, "A")
v_B = path_copy_put(v0, 3, "B")

assert find(v0, 14) == (True, "v14")
assert find(v0, 3) == (True, "v3")

assert find(v_A, 14) == (True, "A")
assert find(v_A, 3) == (True, "v3")

assert find(v_B, 14) == (True, "v14")
assert find(v_B, 3) == (True, "B")
```

Cả hai nhánh bắt đầu từ **cùng `v0`**. Không nhánh nào phải ghi đè trạng thái của nhánh kia.

### Đếm nút giữa ba phiên bản

- `v0` có 15 nút.
- `v_A` sao chép đường `8 → 12 → 14`: **3 nút mới**.
- `v_B` sao chép đường `8 → 4 → 2 → 3`: **4 nút mới**.

Vì hai nhánh được tạo **độc lập từ `v0`**, các bản nút mới của chúng khác nhau. Số đối tượng nút phân biệt:

```python
assert unique_node_count([v0, v_A, v_B]) == 15 + 3 + 4
```

Mặc dù mỗi phiên bản có đủ 15 nút logic, tổng số nút vật lý giữ bởi ba phiên bản chỉ là **22**, không phải **45**.

### Tạo nhánh không đồng nghĩa tự gộp nhánh

Nếu sau này muốn kết hợp `v_A` và `v_B` thành một bản chung, phải có thuật toán **merge** và quy tắc giải quyết xung đột giữa các khóa/giá trị. Chỉ có structural sharing **không tự cung cấp** điều đó.

## 30. So sánh với copy-on-write và snapshot đầy đủ

**Copy-on-write (COW)** là nguyên tắc chia sẻ một vùng dữ liệu cho tới khi xuất hiện thao tác ghi. Khi cần ghi, hệ thống sao chép phần dữ liệu phải tách ra.

Structural sharing trong persistent tree là một kiểu tổ chức phù hợp với ý tưởng **không sao chép phần không đổi**. Nhưng không phải mọi cơ chế COW đều có **full persistence** hoặc cho phép cập nhật một phiên bản cũ thành nhiều nhánh.

### Phân biệt theo hợp đồng

| Khái niệm | Câu hỏi chính |
| --- | --- |
| Full-copy snapshot | Có chép toàn bộ trạng thái để lấy một bản riêng không? |
| Structural sharing | Các phiên bản có dùng chung những phần không đổi không? |
| Copy-on-write | Khi có ghi lên phần đang chia sẻ, hệ thống tách bản sao như thế nào? |
| Persistent data structure | Phiên bản cũ có giữ nguyên sau cập nhật không? |
| Immutable data | Trạng thái của đối tượng/phiên bản có thể bị sửa tại chỗ không? |

Một đối tượng bất biến có thể được sao chép toàn bộ. Một hệ thống COW có thể chỉ cho sử dụng bản mới nhất. Một cấu trúc persistent có thể chia sẻ phần lớn nút. Đây là **những khía cạnh độc lập**, không nên dùng thay tên cho nhau.

## 31. Chia sẻ phiên bản và cập nhật đồng thời

Một cấu trúc persistent an toàn về các nút đã công bố thường thuận lợi khi nhiều người **đọc những phiên bản khác nhau**:

```text
reader A ──► root_v10
reader B ──► root_v11

writer xây root_v12 bằng cách tạo nút mới
và chia sẻ các nút bất biến từ root_v11.
```

Tuy nhiên, **không sửa nút cũ** chưa đủ để bảo đảm an toàn cho toàn bộ hệ thống.

### Vẫn cần quy tắc công bố phiên bản

- Biến nào lưu **`current_root`**?
- Người đọc có lấy gốc một lần rồi giữ trong suốt truy vấn không?
- Hai writer cùng đọc `root_v11` rồi tạo hai bản mới, ai được chọn làm bản hiện hành?
- Có yêu cầu transaction để công bố đồng thời nhiều thay đổi liên quan không?
- Một iterator đang dùng gốc cũ có được giữ gốc đó sống đủ lâu không?

Nếu hai writer cùng xây hai phiên bản hợp lệ nhưng **ghi đè tham chiếu bản hiện hành**, có thể xảy ra *lost update*. Persistence giữ các gốc lịch sử được tham chiếu, **không tự chọn cách merge hoặc đồng bộ việc công bố**.

### Tránh chia sẻ payload mutable giữa các luồng

Ngay cả khi nút cấu trúc không đổi, một value là list mutable vẫn có thể bị sửa bởi một luồng khác và làm các reader của nhiều phiên bản thấy nội dung mới. **Bảo đảm về concurrency cần xét cả phần tử lồng nhau.**

## 32. Chọn sao chép toàn bộ hay chia sẻ cấu trúc?

Không có một lựa chọn đúng cho mọi hệ thống. Hãy xét tần suất cập nhật, kích thước dữ liệu, thời gian lưu phiên bản và kiểu truy vấn.

| Tình huống | Hướng cân nhắc | Lý do |
| --- | --- | --- |
| Cấu trúc nhỏ, ít cập nhật | Full copy | Đơn giản, chi phí đủ nhỏ |
| Cấu trúc lớn, cập nhật chỉ vài khóa | Structural sharing | Tránh copy phần lớn nhánh không đổi |
| Cần nhiều trạng thái để undo/snapshot | Persistent sharing | Giảm cấp phát trên mỗi phiên bản |
| Cần những bản hoàn toàn độc lập để sửa mutable | Full copy kèm chính sách deep ownership | Không để nút/payload ngoài ý muốn dùng chung |
| Chỉ cần một trạng thái hiện hành, ghi cực thường xuyên | Mutable structure có thể phù hợp | Tránh overhead tạo phiên bản không dùng |
| Dữ liệu gần như tĩnh và chủ yếu đọc theo chỉ số | Mảng đã sắp / snapshot đơn giản | Tận dụng truy cập và locality |
| Cây thấp được bảo đảm sau cập nhật | Persistent balanced tree | Path copying theo đường logarit |
| Cây rất lệch, cập nhật sâu | Xem lại cấu trúc/cân bằng | Sharing không loại bỏ chiều cao `Θ(n)` |
| Dữ liệu phân nhánh, cần merge | Persistent + thuật toán merge | Versioning và merge là hai nhiệm vụ khác nhau |

### Checklist trước khi quyết định

1. Một cập nhật trung bình chạm bao nhiêu nút/ô?
2. Có cần giữ **bao nhiêu phiên bản** và trong bao lâu?
3. Dữ liệu con là bất biến sâu hay còn alias mutable?
4. Cấu trúc nền có giới hạn chiều cao/độ sâu không?
5. Bộ nhớ đỉnh và chi phí garbage collection có quan trọng không?
6. Có cần chụp snapshot nhất quán trong lúc dữ liệu nguồn đang cập nhật không?
7. Người đọc có thực sự cần snapshot lịch sử, hay chỉ cần một live view mới nhất?
8. Có cần hỗ trợ nhiều writer, merge, transaction hoặc audit bền vững không?

**Lợi ích của sharing phải được đo theo nhu cầu thực tế**, không chỉ nhìn vào số nút mới ở một ví dụ đẹp.

## 33. Các lỗi tư duy và lỗi cài đặt thường gặp

1. **Cho rằng persistent nhất thiết phải sao chép toàn bộ.** Structural sharing có thể giữ phiên bản cũ với ít nút mới.
2. **Cho rằng structural sharing tự bảo đảm dữ liệu bất biến sâu.** Payload mutable vẫn có thể đổi.
3. **Sao chép list ngoài rồi coi các list bên trong là độc lập.** Shallow copy giữ alias tới phần tử.
4. **Đếm số nút của từng phiên bản rồi cộng tất cả** mà không loại các đối tượng dùng chung.
5. **Dùng `==` để kiểm tra hai nhánh có chia sẻ nút.** Phải dùng danh tính `is`.
6. **Sửa `old_root.left` trong phiên bản mới.** Làm thay đổi mọi gốc còn tham chiếu nút cũ.
7. **Chỉ sao chép nút đích nhưng không tạo lại các tổ tiên.** Gốc mới không nối tới thay đổi.
8. **Sao chép toàn cây rồi vẫn báo chi phí `O(h)`.** Đó là `Θ(n)` trong hiện thực full copy.
9. **Cho rằng copy nút là deep copy payload.** Các value có thể vẫn là cùng object.
10. **Cho rằng frozen dataclass tự đóng băng list trong trường value.** Nó chỉ chặn gán lại thuộc tính theo API thường dùng.
11. **Cho rằng BST persistent luôn có `h=O(log n)`.** BST thường vẫn có thể lệch.
12. **Bỏ qua chi phí bộ nhớ phụ của đệ quy.** Cả bản full copy và path copy Python đều dùng call stack.
13. **Lưu parent pointer mutable trong nút chia sẻ** mà không xét nó thuộc phiên bản nào.
14. **Quên cập nhật subtree_size/height tại nút mới.** Các truy vấn phụ có thể sai dù thứ tự BST còn đúng.
15. **Giữ mọi phiên bản vô hạn và không có retention policy.** Bộ nhớ vẫn tăng theo lịch sử.
16. **Bỏ một gốc rồi tin rằng toàn bộ cây cũ được giải phóng ngay.** Nhiều nút còn dùng chung bởi gốc khác.
17. **Cho rằng COW luôn tương đương fully persistent.** Cần xét API và khả năng cập nhật nhánh lịch sử.
18. **Cho rằng immutable nodes tự giải quyết xung đột hai writer.** Cần đồng bộ công bố gốc.
19. **Phát sinh nhiều bản giữa chừng khi có batch update** mà không xét cập nhật gộp.
20. **Cho rằng sharing luôn nhanh hơn thực tế.** Overhead cấp phát, pointer chasing, locality và garbage collection có thể ảnh hưởng.
21. **Đổi key của nút BST đang được chia sẻ.** Có thể phá thứ tự của tất cả phiên bản tham chiếu nút ấy.
22. **Sử dụng mutable payload làm dữ liệu lịch sử** nhưng không ghi rõ mức snapshot/ownership.
23. **Dùng thuật ngữ “persistent” để chỉ dữ liệu đã lưu trên đĩa** mà bỏ qua nghĩa giữ phiên bản trong thuật toán.
24. **Không kiểm thử phiên bản cũ sau mỗi cập nhật.** Kết quả mới có thể đúng dù lịch sử đã bị sửa lén.

## 34. Tự luyện tập

**Bài 1.** Phân biệt **mục tiêu giữ phiên bản cũ** với **chiến lược full copy** và **structural sharing**. Vì sao cả hai có thể đáp ứng cùng mục tiêu?

**Bài 2.** Với `v0=[1,2,3]` và `v1=v0.copy(); v1[1]=9`, hai phiên bản độc lập ở tầng nào? Chi phí cập nhật theo độ dài `n`?

**Bài 3.** Nếu `v0=[[1],[2]]` và `v1=v0.copy()`, sửa `v1[0].append(7)` có ảnh hưởng `v0` không? Vì sao?

**Bài 4.** Vẽ hai phiên bản BST có khóa `20,40,50,60,70` khi thay value của khóa `50`. Bản full copy tạo bao nhiêu nút mới?

**Bài 5.** Với BST có gốc `40`, trái `20`, phải `60`, dưới `60` có trái `50` và phải `70`, chèn `55` bằng path copying: nút nào mới, nút nào dùng chung?

**Bài 6.** Vì sao `root_v1.left is root_v0.left` là một phép kiểm tra mạnh hơn `root_v1.left == root_v0.left` khi muốn xác nhận chia sẻ nút?

**Bài 7.** Với cây `1..15` cân đối như phần 7, đường cập nhật value của `14` gồm mấy nút? Nếu giữ hai gốc, số nút phân biệt với full copy và path copying lần lượt là bao nhiêu?

**Bài 8.** Viết hàm `clone_all_nodes(root)` tạo các nút mới với cùng khóa, value và hình dạng. Hàm đó có tự deep-copy value list không?

**Bài 9.** Chứng minh `full_copy_put` cần `Θ(n)` nút mới khi cập nhật một key đã có trên cây `n` nút, bất kể khóa ở độ sâu bao nhiêu.

**Bài 10.** Viết hoặc giải thích `path_copy_put`. Vì sao chỉ có một cây con tại mỗi tổ tiên cần nhận con trỏ mới?

**Bài 11.** Giải thích vì sao khi `key` có sẵn và `value` không đổi, phiên bản mới có thể tái sử dụng chính `root` cũ.

**Bài 12.** Xây hàm đếm số đối tượng nút **phân biệt** qua nhiều gốc BST. Vì sao cần `seen` theo danh tính object?

**Bài 13.** Nếu có `m` cập nhật trên BST `n` khóa cố định, phân tích số nút của full copy và path copying khi mọi phiên bản được giữ, với chiều cao tối đa `H`.

**Bài 14.** Khi BST lệch thành chuỗi dài `n`, phép cập nhật key ở cuối bằng path copying có còn giảm được nhiều nút không? Vì sao?

**Bài 15.** Với stack linked list bất biến, `push` và `pop` tạo bao nhiêu nút mới? Vì sao hiệu quả hơn copy toàn bộ danh sách cho thao tác thêm đầu?

**Bài 16.** Một persistent linked list cần sửa phần tử tại chỉ số `i`. Vì sao phải sao chép tiền tố tới vị trí ấy nếu các nút đều bất biến?

**Bài 17.** Mô tả path copying trên persistent segment tree khi cập nhật một vị trí. Số nút mới ở cây cân đối theo `n` là bao nhiêu?

**Bài 18.** Nêu một tình huống cần cập nhật nhiều nhánh và giải thích vì sao batch update có thể giảm việc sao chép lặp tại những tổ tiên chung.

**Bài 19.** Tại sao nút `frozen=True` chứa value là `list[int]` vẫn có thể làm nhiều phiên bản quan sát thấy thay đổi chung?

**Bài 20.** Nếu một nút cây persistent có trường `parent` mutable, vì sao dùng chung nút giữa hai phiên bản có thể khiến giá trị `parent` không đúng cho ít nhất một phiên bản?

**Bài 21.** Nêu sự khác nhau giữa **structural sharing**, **copy-on-write**, **persistent**, **immutable** và **lưu bền trên ổ đĩa**.

**Bài 22.** Một hệ thống giữ mọi phiên bản cũ để undo. Bỏ một gốc lịch sử có chắc giải phóng ngay mọi nút thuộc phiên bản ấy không? Vì sao?

**Bài 23.** Nếu hai writer tạo hai phiên bản mới từ cùng một gốc, structural sharing có tự quyết định bản nào là bản chính hay merge hai bản không?

**Bài 24.** Đề xuất một bộ kiểm thử cho full copy và structural sharing: kiểm tra giá trị cũ, giá trị mới, số nút vật lý, `is` trên nhánh không đổi, BST in-order và trường hợp no-op.

<details>
<summary>Đáp án và gợi ý</summary>

1. Mục tiêu là giữ phiên bản cũ khi cập nhật. Full copy tách tất cả nút, structural sharing giữ các nhánh không đổi; cả hai đều đạt mục tiêu nếu không sửa trạng thái dùng chung.
2. Hai list ngoài độc lập, phần tử là số nguyên bất biến. `v0=[1,2,3]`, `v1=[1,9,3]`. Copy `O(n)` thời gian và bộ nhớ, gán một ô `O(1)`.
3. Có. Hai list ngoài khác nhau nhưng cùng tham chiếu list trong; `v0[0]` cũng thành `[1,7]`.
4. Với 5 nút cũ, full copy tạo **5 nút mới** khi thay value của khóa đã có, đồng thời giữ nguyên 5 nút cũ.
5. Mới: `55, 50', 60', 40'`. Chia sẻ: `20` và `70` cùng mọi nhánh không đổi khác.
6. `is` xác nhận cùng danh tính object; `==` có thể chỉ xác nhận nội dung bằng nhau giữa hai bản clone.
7. Đường `8 → 12 → 14` có 3 nút. Full copy giữ hai bản: 30 nút; path copying: 18 nút.
8. Duyệt đệ quy và tạo `Node(root.key,root.value,clone(left),clone(right))`. Nó chỉ copy các **nút**, không tự sao chép sâu value mutable.
9. Hàm xử lý mọi nút cũ đúng một lần, dù ở đường tìm hay nhánh clone; vì vậy tạo `n` nút mới và cần `Θ(n)` công việc.
10. Mỗi khóa xác định một nhánh duy nhất theo BST. Chỉ nhánh đó có nội dung thay đổi; nhánh kia giữ chính tham chiếu cũ, còn các tổ tiên được tạo lại để nối con mới.
11. Nếu không thay đổi về nội dung logic, giữ nguyên `root` không phá bất biến và tiết kiệm cấp phát.
12. Dùng DFS với `seen` chứa `id(node)`; bỏ qua node nếu đã thấy. Chia sẻ có thể khiến một object xuất hiện qua nhiều gốc, chỉ đếm một lần.
13. Full copy cần `Θ((m+1)n)` nút nếu giữ hết phiên bản. Path copying cần `O(n+mH)` nút; nếu cân đối có `H=O(log n)`.
14. Đường tìm có thể dài `Θ(n)`, nên path copying phải tạo tới `Θ(n)` nút mới; lợi thế có thể biến mất.
15. `push` tạo một nút mới; `pop` không tạo nút mới, chỉ trả `next`. Cả hai `O(1)`; copy toàn bộ danh sách phải tạo nhiều nút.
16. Muốn thay một liên kết ở vị trí sâu mà không sửa nút cũ, mọi nút ở tiền tố dẫn tới đó phải được tạo lại để gốc phiên bản mới trỏ được tới phần đổi.
17. Cập nhật một lá và tạo lại đường từ gốc tới lá; cây cân đối có `O(log n)` mức, tạo `O(log n)` nút mới.
18. Cập nhật cả hai lá ở hai nhánh có cùng gốc; batch có thể tạo bản gốc mới một lần, còn hai lượt riêng tạo hai bản gốc trung gian.
19. `frozen=True` chặn gán lại thuộc tính nút, không chặn `list.append` qua alias; mọi phiên bản dùng chung list quan sát nội dung thay đổi.
20. Cùng một nút con được dùng dưới hai bản cha khác nhau. Một giá trị `parent` đơn nhất trong nút không thể trỏ đúng đồng thời tới cả hai cha theo hai phiên bản.
21. Structural sharing là chia sẻ nhánh không đổi; COW là sao chép khi phải ghi; persistent là giữ phiên bản cũ sau cập nhật; immutable là không sửa trạng thái đối tượng tại chỗ; durability là lưu dữ liệu qua vòng đời tiến trình/thiết bị theo bảo đảm lưu trữ.
22. Không. Nút có thể còn được gốc khác, iterator hoặc tham chiếu khác giữ; bộ quản lý bộ nhớ quyết định khi nào thu hồi đối tượng không còn ai sử dụng.
23. Không. Hai bản đều có thể hợp lệ nhưng việc chọn gốc hiện hành và merge cần quy tắc đồng bộ/xung đột riêng.
24. Kiểm thử `find(v0,k)` giữ giá trị cũ, `find(v1,k)` thấy mới, in-order giữ khóa tăng, `unique_node_count` bằng con số kỳ vọng, `is` của nhánh chia sẻ, `is not` của đường cập nhật; no-op trả gốc cũ ở path copying nhưng full copy vẫn có thể nhân bản.

</details>

## Ghi nhớ

**Sao chép toàn bộ** và **chia sẻ cấu trúc** đều có thể giữ phiên bản cũ, nhưng trả giá khác nhau. Với cây `n` nút, full copy tạo **`Θ(n)` nút mới mỗi cập nhật**, trong khi **path copying chỉ tạo các nút trên đường thay đổi**, thường **`O(h)` theo chiều cao `h`**, tương ứng `O(log n)` nếu cây được duy trì cân đối. Với `m` bản cập nhật trên cây `n` khóa cố định và giữ tất cả gốc, chi phí nút có thể là **`Θ(mn+n)`** cho full copy so với **`O(n+m log n)`** cho structural sharing trên cây cân đối. Nhưng chia sẻ chỉ an toàn nếu **nút và payload được dùng chung có ngữ nghĩa ổn định**; copy nút không tự deep-copy value. Khi thiết kế phiên bản, hãy kiểm tra **danh tính nút, đường copy, vòng đời các gốc, chiều cao cây, metadata, quyền sở hữu payload và cơ chế công bố dữ liệu** thay vì chỉ nhìn tổng số nút của một phiên bản.
