# Dựng BST cân đối từ dãy khóa đã sắp xếp

Giả sử nền tảng học tập có hàng nghìn mã học viên đã được sắp tăng dần để xuất báo cáo. Ta muốn biến dãy ấy thành **cây tìm kiếm nhị phân** (*Binary Search Tree – BST*) nhằm phục vụ tra cứu theo khóa, tìm tiền nhiệm/kế nhiệm và truy vấn khoảng. Nếu cứ chèn lần lượt từ mã nhỏ nhất tới lớn nhất vào **BST thông thường không tự cân bằng**, cây có thể thành một chuỗi dài với chiều cao `n`, khiến tìm kiếm suy giảm tới `O(n)`.

Cách hiệu quả hơn là **dựng cây trực tiếp bằng cách chọn phần tử ở giữa làm gốc**, rồi lặp lại quy tắc đó trên nửa trái và nửa phải. Khi dãy đầu vào **đã sắp và có các khóa phân biệt**, thuật toán này cho một BST có chiều cao nhỏ nhất theo số nút, dùng **`O(n)` thời gian** để dựng các nút và **`O(log n)` bộ nhớ phụ** cho lời gọi đệ quy (không tính bộ nhớ chứa chính cây và dữ liệu đầu vào).

Bài học thuộc chương **Cây tìm kiếm nhị phân** của module cấu trúc dữ liệu. Trọng tâm không chỉ là mã nguồn tạo cây: chúng ta sẽ chứng minh vì sao thứ tự đúng, vì sao chiều cao cân đối, phân tích chi phí, xử lý dãy rỗng/dãy chẵn, cặp khóa–giá trị, khóa trùng, metadata và lựa chọn giải pháp phù hợp khi dữ liệu tiếp tục thay đổi.

## 1. Phân biệt BST hợp lệ với BST cân đối

Với BST có **khóa duy nhất** và một quan hệ thứ tự nhất quán, tại mỗi nút có khóa `k`:

- Mọi khóa trong **toàn bộ cây con trái** phải **nhỏ hơn** `k`.
- Mọi khóa trong **toàn bộ cây con phải** phải **lớn hơn** `k`.
- Hai cây con cũng thỏa các điều kiện ấy.

```text
                k
              /   \
    mọi khóa < k   mọi khóa > k
```

Chính bất biến này làm cho **duyệt giữa** (*in-order*: trái → nút → phải) xuất khóa theo thứ tự tăng.

Nhưng BST có thể thỏa hoàn toàn bất biến mà vẫn rất cao:

```text
Dãy chèn: 10, 20, 30, 40, 50, 60, 70

10
  \
   20
     \
      30
        \
         40
           \
            50
              \
               60
                 \
                  70
```

Cây lệch phải này vẫn là BST. Tuy nhiên, tìm khóa `70` phải xét bảy nút.

Một BST **cân đối theo cách chia tập khóa** có thể lưu cùng các khóa như sau:

```text
                 40
               /    \
             20      60
            /  \    /  \
          10   30  50   70
```

Lúc này, tìm `70` chỉ xét `40 → 60 → 70`, tức ba nút.

**Kết luận đầu tiên:** tính đúng thứ tự và tính cân đối là **hai tính chất khác nhau**. Việc chọn gốc từ trung vị chính là cách kiểm soát **hình dạng** của cây trong giai đoạn dựng ban đầu.

## 2. Hợp đồng đầu vào và đầu ra

Ta giả định ban đầu có một dãy:

```text
keys = [k0, k1, ..., k(n-1)]
```

với các điều kiện:

1. Khóa đã được sắp **tăng nghiêm ngặt** theo cùng quy tắc so sánh mà BST sẽ sử dụng.
2. Không có hai khóa được comparator coi là **tương đương**.
3. `n` là số khóa phân biệt, có thể bằng 0.
4. Dãy hỗ trợ truy cập phần tử bằng chỉ số với chi phí cơ bản `O(1)`, ví dụ `list` Python.
5. Kết quả là một **tham chiếu gốc** của BST, hoặc `None` nếu dãy rỗng.

Hậu điều kiện cần thỏa:

- Mọi khóa đầu vào xuất hiện **đúng một lần** trong BST.
- Không xuất hiện khóa ngoài đầu vào.
- Bất biến BST đúng tại **mọi nút**, không chỉ hai con trực tiếp.
- Duyệt in-order của cây bằng **chính dãy đầu vào**.
- Chiều cao cây được giữ **`O(log(n+1))`**.
- Nếu nút có `parent`, `subtree_size` hay `height` thì các trường này cũng phải đúng.

Với **BST-map**, dữ liệu đầu vào có thể là các cặp `(key, value)` đã sắp theo **key**. Giá trị đi kèm không được tách khỏi khóa khi dựng cây.

**Không tự động dùng thuật toán trên một dãy chưa sắp.** Nếu khóa chưa sắp, việc chọn phần tử ở vị trí giữa **không bảo đảm** nó nằm giữa các khóa theo giá trị, nên cây có thể sai bất biến.

## 3. Ý tưởng chia để trị: chọn trung vị làm gốc

Với một đoạn dãy đã sắp, quy trình là:

1. Nếu đoạn rỗng → trả cây rỗng.
2. Chọn **phần tử giữa** làm gốc đoạn.
3. Dựng đệ quy **nửa trái** thành cây con trái.
4. Dựng đệ quy **nửa phải** thành cây con phải.
5. Trả nút gốc vừa dựng.

```text
Dãy tăng:

[10, 20, 30, 40, 50, 60, 70]
             ↑
           giữa = 40

              40
             /  \
[10,20,30]        [50,60,70]
     ↓                 ↓
  dựng trái         dựng phải
```

Vì dãy tăng nghiêm ngặt:

- Các phần tử **trước vị trí giữa** nhỏ hơn khóa ở giữa.
- Các phần tử **sau vị trí giữa** lớn hơn khóa ở giữa.

Vì thế việc nối hai cây con vào nút giữa bảo toàn ngay phần quan trọng nhất của bất biến BST.

Đồng thời, số phần tử của hai nửa chênh nhau **không quá một**, nên chiều cao của hai cây con cũng gần nhau nếu tiếp tục chọn trung vị ở mọi mức.

### Tại sao gọi là chia để trị?

Mỗi lượt xử lý một đoạn có `m` phần tử và chia thành hai bài toán con cỡ khoảng `m/2`. Công việc tại nút gốc chỉ gồm:

- Chọn chỉ số giữa.
- Tạo một nút.
- Gắn tham chiếu con trái/con phải.
- Tùy chọn cập nhật metadata.

Việc dựng cả cây không yêu cầu so từng khóa đầu vào với mọi nút có sẵn, khác với cách **chèn từng khóa vào BST đã dựng dở**.

## 4. Minh họa trọn vẹn với 15 khóa

Lấy dãy:

```text
1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15
```

Phần tử giữa là `8`. Hai nửa:

```text
Trái:  1,2,3,4,5,6,7
Gốc:   8
Phải:  9,10,11,12,13,14,15
```

Trong nửa trái, chọn `4` làm gốc; trong nửa phải, chọn `12`. Tiếp tục chia:

```text
                        8
                    /       \
                   4         12
                 /   \      /   \
                2     6    10    14
               / \   / \   / \   /  \
              1   3 5   7 9  11 13  15
```

Các tầng:

| Tầng | Số nút | Khóa |
| ---: | ---: | --- |
| 1 | 1 | `8` |
| 2 | 2 | `4,12` |
| 3 | 4 | `2,6,10,14` |
| 4 | 8 | `1,3,5,7,9,11,13,15` |

Cây chứa `15` nút nhưng chiều cao chỉ **4 nút** từ gốc đến lá. Duyệt giữa trả chính xác `1,2,...,15`.

Ngược lại, nếu chèn tuần tự `1,2,...,15` vào BST thường không tự cân bằng, chiều cao trở thành **15**. Cùng một bộ dữ liệu, cách **dựng hình dạng cây** đã tạo ra khác biệt lớn về đường tìm.

## 5. Số phần tử chẵn: chọn giữa bên trái hay bên phải?

Nếu số phần tử là **chẵn**, có **hai phần tử ở giữa**.

Ví dụ:

```text
keys = [10, 20, 30, 40, 50, 60, 70, 80]

Chỉ số:  0   1   2   3   4   5   6   7
                          ↑   ↑
                    hai vị trí giữa:
                        3 và 4
```

Có thể chọn:

- **Giữa lệch trái:** chỉ số `3` → khóa `40`.
- **Giữa lệch phải:** chỉ số `4` → khóa `50`.

Cả hai đều đúng và tạo hai cây cân đối. Trong bài này, thuật toán dùng đoạn **nửa mở `[lo, hi)`** và:

```text
mid = (lo + hi) // 2
```

Với `[0,8)` ta có `mid=4`, tức chọn **giữa lệch phải** khi số phần tử chẵn.

Cây ví dụ:

```text
                     50
                   /    \
                 30      70
                /  \    /  \
              20   40  60   80
             /
            10
```

Chiều cao là **4**; dãy in-order vẫn là `10,20,30,40,50,60,70,80`.

### Đừng nhầm cân đối với phải có hai nhánh bằng hệt nhau

Với `8` nút, không thể chia các `7` nút còn lại thành hai phần bằng nhau tuyệt đối. Một phía có `4` nút, phía kia `3` nút, nhưng điều đó vẫn giúp kiểm soát chiều cao.

Trong một hệ thống có yêu cầu **hình dạng cây tái lập được**, cần quy định dứt khoát chính sách chọn giữa. Không nên để hai nơi cùng dựng cây nhưng một nơi chọn giữa lệch trái, nơi kia chọn lệch phải, rồi kiểm thử đòi cây có hình dạng giống hệt nhau.

## 6. Giả mã dựng cây bằng khoảng chỉ số

Dùng đoạn **nửa mở `[lo, hi)`** trên dãy `keys`:

```text
BUILD(keys, lo, hi):
    if lo >= hi:
        return null

    mid = lo + (hi - lo) // 2

    node = new Node(keys[mid])

    node.left  = BUILD(keys, lo, mid)
    node.right = BUILD(keys, mid + 1, hi)

    return node


BUILD_SORTED_BST(keys):
    return BUILD(keys, 0, length(keys))
```

Biểu thức `lo + (hi - lo) // 2` tương đương về giá trị toán học với `(lo+hi)//2` khi `lo <= hi` và các chỉ số không âm. Trong những ngôn ngữ có số nguyên giới hạn cố định, dạng hiệu có thể giúp tránh **tràn số khi cộng hai chỉ số lớn**.

### Cơ sở dừng

Nếu `lo == hi`, đoạn rỗng và trả `None`. Nếu `hi == lo+1`, chọn phần tử duy nhất làm nút, hai lời gọi dựng con đều nhận đoạn rỗng nên trả `None`.

Không cần một trường hợp đặc biệt chỉ dành cho `n=1`. Cơ sở đoạn rỗng đã bao phủ mọi tình huống.

### Tại sao dùng [lo, hi)?

Khoảng nửa mở giúp tách không chồng lấn:

```text
[lo, mid)       -> cây con trái
mid             -> nút gốc
[mid + 1, hi)   -> cây con phải
```

Không có chỉ số nào bị lặp hoặc bỏ sót. Nếu dùng nhầm `[lo,mid]` cho nửa trái, phần tử giữa có thể được đưa vào cây con **lần thứ hai** hoặc gây đệ quy không kết thúc.

## 7. Chứng minh cây dựng được vẫn là BST hợp lệ

Ta chứng minh theo **số phần tử trong đoạn**.

**Cơ sở `n=0`:** trả cây rỗng, hợp lệ.

**Cơ sở `n=1`:** một nút không có con; không có quan hệ khóa nào vi phạm.

**Bước quy nạp:** giả sử hàm `BUILD` dựng đúng BST cho mọi đoạn có ít hơn `n` phần tử. Với đoạn `n` phần tử, thuật toán chọn khóa `k = keys[mid]`.

Do dãy đã **tăng nghiêm ngặt**:

- Mọi phần tử trong `keys[lo:mid]` đều **`< k`**.
- Mọi phần tử trong `keys[mid+1:hi]` đều **`> k`**.

Theo giả thiết quy nạp, hai lời gọi con đều dựng BST hợp lệ. Khi gắn chúng thành cây con trái và phải của nút mang khóa `k`, bất biến BST đúng ở gốc và trên toàn bộ hậu duệ.

Vì mọi phần tử chỉ thuộc **một** trong ba phần: trái, giữa, phải, tập khóa của cây đúng bằng tập khóa đầu vào, không mất và không lặp phần tử.

**Kết luận:** thuật toán dựng được BST hợp lệ với mọi dãy đầu vào tăng nghiêm ngặt.

### Kiểm tra bằng in-order

Quy tắc duyệt giữa lần lượt đọc:

```text
INORDER(left) + [root.key] + INORDER(right)
```

Theo cách chia đoạn, biểu thức trên chính là:

```text
keys[lo:mid] + [keys[mid]] + keys[mid+1:hi]
= keys[lo:hi]
```

Do đó, với đầu vào hợp lệ, **in-order của cây phải khôi phục nguyên vẹn dãy đã sắp**, một hậu điều kiện rất thuận tiện để kiểm thử.

## 8. Tại sao cách chia trung vị tạo chiều cao nhỏ?

Ta đo chiều cao `h` bằng **số nút trên đường dài nhất từ gốc đến một lá**:

```text
h(cây rỗng) = 0
h(nút lá)   = 1
h(node) = 1 + max(h(node.left), h(node.right))
```

Nếu có `n` nút, sau khi chọn một nút làm gốc, hai cây con chứa khoảng một nửa số nút còn lại. Đường đi dài nhất từ gốc theo thuật toán sẽ lần lượt đi qua những đoạn có cỡ:

```text
n, khoảng n/2, khoảng n/4, khoảng n/8, ...
```

Số lần chia đôi trước khi còn đoạn rỗng tỉ lệ với `log₂(n+1)`.

Một cây nhị phân cao `h` nút có tối đa:

```text
1 + 2 + 4 + ... + 2^(h-1) = 2^h - 1 nút
```

Vì thế bất kỳ cây nhị phân nào chứa `n` nút đều phải thỏa:

```text
n <= 2^h - 1

suy ra:

h >= ceil(log2(n + 1))
```

Thuật toán chia trung vị xây được một cây có chiều cao **đúng bằng `ceil(log₂(n+1))`** theo quy ước trên: các đoạn luôn được chia sao cho số nút của hai cây con chênh nhau không quá một, và không thể đạt chiều cao thấp hơn giới hạn đếm nút nói trên.

### Bảng độ cao lý thuyết

| `n` | `h` của cây dựng theo trung vị | `h` có thể có ở cây lệch |
| ---: | ---: | ---: |
| 0 | 0 | 0 |
| 1 | 1 | 1 |
| 2 | 2 | 2 |
| 3 | 2 | 3 |
| 7 | 3 | 7 |
| 8 | 4 | 8 |
| 15 | 4 | 15 |
| 31 | 5 | 31 |
| 1.023 | 10 | 1.023 |

**Chú ý:** chiều cao nhỏ nhất không có nghĩa cây có hình dạng duy nhất. Chọn trung vị lệch trái hoặc lệch phải khi số phần tử chẵn có thể cho hai cây khác nhau nhưng **cùng độ cao tối ưu**.

## 9. Python hoàn chỉnh: Node, parent và metadata

Để vừa minh họa thuật toán dựng vừa hỗ trợ các ứng dụng như **rank/select** và kiểm tra thông tin phụ, mỗi nút sẽ lưu:

- `key`: khóa phân biệt.
- `value`: dữ liệu gắn với khóa (có thể là `None`).
- `left`, `right`: hai con.
- `parent`: nút cha, hoặc `None` tại gốc.
- `subtree_size`: số nút trong cây con gốc tại nút ấy.
- `height`: chiều cao cây con, đo bằng số nút.

Các trường phụ không bắt buộc đối với một BST tối giản, nhưng là ví dụ tốt về **cách dựng metadata từ dưới lên** khi biết trước cấu trúc cây.

### Khai báo nút

```python
class Node:
    def __init__(self, key, value=None, parent=None):
        self.key = key
        self.value = value
        self.parent = parent
        self.left = None
        self.right = None
        self.subtree_size = 1
        self.height = 1


def node_size(node):
    return 0 if node is None else node.subtree_size


def node_height(node):
    return 0 if node is None else node.height
```

### Dựng BST cân đối từ dãy khóa tăng nghiêm ngặt

```python
def build_balanced_bst(sorted_keys):
    """Dựng BST cân đối từ list khóa tăng nghiêm ngặt.

    Trả về root; không sửa list đầu vào.
    """
    # Kiểm tra precondition trong O(n), với so sánh O(1).
    for i in range(1, len(sorted_keys)):
        if not sorted_keys[i - 1] < sorted_keys[i]:
            raise ValueError(
                "Cần các khóa phân biệt được sắp tăng nghiêm ngặt"
            )

    def build(lo, hi, parent):
        if lo >= hi:
            return None

        mid = lo + (hi - lo) // 2
        node = Node(sorted_keys[mid], parent=parent)

        node.left = build(lo, mid, node)
        node.right = build(mid + 1, hi, node)

        # Cả hai cây con đã dựng xong: tính metadata từ dưới lên.
        node.subtree_size = (
            1 + node_size(node.left) + node_size(node.right)
        )
        node.height = (
            1 + max(node_height(node.left), node_height(node.right))
        )
        return node

    return build(0, len(sorted_keys), None)
```

Mỗi nút được tạo đúng một lần. Lời gọi con trái và con phải nhận `parent=node`, nên các liên kết hai chiều được thiết lập ngay khi dựng. Hai trường `subtree_size` và `height` chỉ được tính khi **hai cây con đã hoàn tất**, vì khi ấy metadata của các con đã chính xác.

### Kiểm thử với dãy 1..15

```python
keys = list(range(1, 16))
root = build_balanced_bst(keys)

assert root.key == 8
assert root.parent is None
assert root.subtree_size == 15
assert root.height == 4

assert root.left.key == 4
assert root.right.key == 12
assert root.left.parent is root
assert root.right.parent is root

assert root.left.subtree_size == 7
assert root.right.subtree_size == 7
```

Đoạn mã này có thể được chạy độc lập trong Python nếu đặt phần định nghĩa `Node`, các helper và hàm dựng phía trên trong cùng một tệp hoặc cùng phiên làm việc.

## 10. Duyệt giữa để xác minh dãy đầu ra

Ta không cần sắp xếp kết quả: chỉ cần duyệt **trái → nút → phải**.

```python
def inorder_keys(root):
    result = []
    stack = []
    current = root

    while current is not None or stack:
        while current is not None:
            stack.append(current)
            current = current.left

        current = stack.pop()
        result.append(current.key)
        current = current.right

    return result


assert inorder_keys(root) == list(range(1, 16))
assert inorder_keys(build_balanced_bst([])) == []
assert inorder_keys(build_balanced_bst([42])) == [42]
assert inorder_keys(build_balanced_bst([10, 20])) == [10, 20]
```

Trong ví dụ, cây được dựng cân đối nên chiều cao chỉ `O(log n)`; stack của phép duyệt dùng `O(log n)` bộ nhớ phụ, không tính list kết quả `O(n)`.

### Tìm kiếm trên cây vừa dựng

```python
def search(root, key):
    current = root

    while current is not None:
        if key == current.key:
            return current
        current = (
            current.left if key < current.key
            else current.right
        )

    return None


assert search(root, 8) is root
assert search(root, 1).key == 1
assert search(root, 15).key == 15
assert search(root, 16) is None
```

Một đường tìm trên cây cân đối có độ dài tối đa `O(log n)`. Thuật toán tìm kiếm bản thân nó **không khác** BST thường; khác biệt nằm ở hình dạng cây đầu vào.

## 11. Kiểm tra tính hợp lệ của toàn bộ cấu trúc

Kiểm tra mỗi `inorder_keys(root) == keys` rất hữu ích, nhưng chưa xác nhận:

- `parent` của mỗi nút có trỏ đúng cha không.
- `root.parent` có bằng `None` không.
- Một đối tượng nút có xuất hiện qua hai đường đi hoặc chu trình không.
- `subtree_size` và `height` có đúng không.

Hàm kiểm tra dưới đây dùng **đường biên tổ tiên**, danh tính nút và phép tính metadata độc lập. Nó dành cho đầu vào có thể so sánh bằng `<`, `<=` và giả định các đối tượng `Node` như trên.

```python
def validate_bst(root):
    if root is None:
        return True

    if root.parent is not None:
        return False

    stack = [(root, None, None, None)]
    seen = set()
    order = []

    while stack:
        node, lower, upper, expected_parent = stack.pop()

        if id(node) in seen:
            return False
        seen.add(id(node))
        order.append(node)

        if node.parent is not expected_parent:
            return False

        if lower is not None and node.key <= lower:
            return False
        if upper is not None and node.key >= upper:
            return False

        if node.left is not None:
            stack.append((node.left, lower, node.key, node))
        if node.right is not None:
            stack.append((node.right, node.key, upper, node))

    # Cha được thêm vào order trước con; đảo lại để tính bottom-up.
    sizes = {}
    heights = {}

    for node in reversed(order):
        expected_size = (
            1 + sizes.get(node.left, 0) + sizes.get(node.right, 0)
        )
        expected_height = (
            1 + max(
                heights.get(node.left, 0),
                heights.get(node.right, 0)
            )
        )

        if node.subtree_size != expected_size:
            return False
        if node.height != expected_height:
            return False

        sizes[node] = expected_size
        heights[node] = expected_height

    return sizes[root] == len(seen)
```

### Kiểm thử một số kích thước

```python
for n in (0, 1, 2, 3, 4, 5, 7, 8, 15, 31, 100):
    ordered = list(range(n))
    tree = build_balanced_bst(ordered)

    assert validate_bst(tree)
    assert inorder_keys(tree) == ordered

    if tree is not None:
        assert tree.subtree_size == n
        assert tree.parent is None
```

Bộ kiểm tra dành cho **môi trường học/kiểm thử**, tốn `O(n)` thời gian và `O(n)` bộ nhớ phụ; không nên chạy sau mỗi truy vấn trong hệ thống sản xuất.

## 12. Phân tích độ phức tạp của dựng trực tiếp

Giả sử dãy đã sắp có `n` khóa. Ngoài kiểm tra hợp lệ `O(n)`, mỗi lời gọi không rỗng:

1. Chọn một vị trí giữa: `O(1)`.
2. Tạo nút: `O(1)`.
3. Gọi dựng hai đoạn con.
4. Nối con và tính metadata: `O(1)`.

Ta có truy hồi gần đúng:

```text
T(n) = T(floor((n-1)/2)) + T(ceil((n-1)/2)) + O(1)

T(0) = O(1)
```

Một cách đếm còn trực tiếp hơn: **mỗi trong số `n` phần tử tạo đúng một nút**, không có nút nào bị tạo hai lần, và công việc quanh mỗi nút là hằng số. Vì thế:

```text
Thời gian dựng = Θ(n)
```

Do cây được chia gần đôi ở mỗi tầng, độ sâu đệ quy tối đa:

```text
O(log(n+1))
```

### Phân biệt ba loại bộ nhớ

| Thành phần | Chi phí |
| --- | --- |
| Dãy khóa đầu vào `keys` nếu đã lưu thành list | `O(n)` |
| `n` đối tượng nút trong BST đầu ra | `O(n)` |
| **Bộ nhớ phụ** do đệ quy, không tính đầu vào/đầu ra | **`O(log(n+1))`** |

Đừng viết “toàn bộ thuật toán chỉ dùng `O(log n)` bộ nhớ” nếu thực tế còn tạo `n` nút. Cách nói đúng là **`O(log n)` bộ nhớ phụ**, cộng **`O(n)` bộ nhớ lưu BST**.

### Tiền điều kiện đã sắp quan trọng về chi phí

Nếu dữ liệu **chưa sắp**, phải sắp trước bằng một thuật toán phù hợp:

```text
Dữ liệu chưa sắp -> sort O(n log n) -> build O(n)

Tổng: O(n log n)
```

Với một comparator có chi phí không hằng số, còn phải tính giá của phép so sánh. Việc “dựng cây `O(n)`” ở đây giả định **đầu vào đã được sắp** và truy cập chỉ số nhanh.

## 13. Tránh copy mảng ở mỗi lời gọi đệ quy

Một phiên bản trông ngắn gọn trong Python là:

```python
def build_with_slices(keys):
    if not keys:
        return None

    mid = len(keys) // 2
    node = Node(keys[mid])

    node.left = build_with_slices(keys[:mid])
    node.right = build_with_slices(keys[mid + 1:])
    return node
```

Về **thứ tự BST** và **hình dạng cây**, ý tưởng này vẫn đúng khi đầu vào đã sắp tăng. Tuy nhiên, đoạn mã rút gọn **chưa gán `parent` và chưa cập nhật `subtree_size`/`height`**; nếu cần những trường ấy, phải bổ sung chúng như phiên bản đầy đủ ở phần 9. Ngoài ra, mỗi biểu thức `keys[:mid]` hay `keys[mid+1:]` tạo **list mới** và sao chép các tham chiếu.

Tổng lượng phần tử được sao chép qua các mức đệ quy có thể tới:

```text
Mức 1: gần n phần tử
Mức 2: gần n phần tử
Mức 3: gần n phần tử
...
Khoảng log2(n) mức

Tổng: O(n log n) phần tử được sao chép
```

Vì thế bản dùng slicing có thể tốn **`O(n log n)` thời gian** thay vì `O(n)`, dù chi phí tạo nút vẫn là `O(n)`. Độ sâu đệ quy vẫn `O(log n)`, nhưng các bản sao list làm phát sinh bộ nhớ trung gian đáng kể (đỉnh sử dụng của các bản sao có thể `O(n)` ngoài nút đầu ra).

**Khuyến nghị:** để đạt đúng mục tiêu dựng trực tiếp `O(n)`, truyền **chỉ số `lo` và `hi` trên cùng dãy đầu vào**, không cắt ra list mới trong mỗi lời gọi.

### Tối ưu không đồng nghĩa làm code khó đọc

Dạng `build(lo,hi)` với khoảng nửa mở rất dễ kiểm thử:

- `lo == hi` → rỗng.
- `mid` luôn nằm trong đoạn khi `lo < hi`.
- Hai đoạn con không giao nhau.
- Không copy dữ liệu đầu vào.

Đây vừa là cách viết hiệu quả, vừa là cách làm rõ **bất biến chia đoạn**.

## 14. Nếu dữ liệu là các cặp khóa–giá trị

Một BST-map lưu thông tin theo **khóa**, chẳng hạn:

```text
(student_id, record)
```

Nếu các cặp đã được sắp tăng theo `student_id`, ta có thể dựng cây theo đúng thuật toán trung vị, nhưng **mỗi nút phải nhận cả cặp** của cùng một vị trí đầu vào.

### Hàm dựng tree map từ sorted pairs

Đoạn mã dùng lại `Node`, `node_size` và `node_height` ở phần 9:

```python
def build_balanced_map(sorted_items):
    """sorted_items: [(key, value), ...] sắp tăng theo key."""
    for i in range(1, len(sorted_items)):
        if not sorted_items[i - 1][0] < sorted_items[i][0]:
            raise ValueError("Keys phải tăng nghiêm ngặt")

    def build(lo, hi, parent):
        if lo >= hi:
            return None

        mid = lo + (hi - lo) // 2
        key, value = sorted_items[mid]
        node = Node(key, value, parent)

        node.left = build(lo, mid, node)
        node.right = build(mid + 1, hi, node)

        node.subtree_size = (
            1 + node_size(node.left) + node_size(node.right)
        )
        node.height = (
            1 + max(node_height(node.left), node_height(node.right))
        )
        return node

    return build(0, len(sorted_items), None)
```

Ví dụ:

```python
items = [
    (10, "An"),
    (20, None),
    (30, "Bình"),
    (40, "Chi"),
    (50, "Dung"),
]

map_root = build_balanced_map(items)

assert validate_bst(map_root)
assert inorder_keys(map_root) == [10, 20, 30, 40, 50]
assert search(map_root, 20).value is None
assert search(map_root, 30).value == "Bình"
assert search(map_root, 50).value == "Dung"
```

**Giá trị `None` hợp lệ không có nghĩa khóa vắng mặt.** Phải xét nút hoặc một cờ `found` riêng. Việc dựng theo sorted pairs không được tách mảng khóa và mảng giá trị rồi làm xáo trộn quan hệ giữa chúng.

### Duyệt cặp theo thứ tự khóa

```python
def inorder_items(root):
    result = []
    stack = []
    current = root

    while current is not None or stack:
        while current is not None:
            stack.append(current)
            current = current.left

        current = stack.pop()
        result.append((current.key, current.value))
        current = current.right

    return result


assert inorder_items(map_root) == items
```

Điều này kiểm thử cả **thứ tự khóa** lẫn **giá trị đi kèm**.

## 15. Khóa trùng: phải chọn chính sách trước khi dựng

Thuật toán `build_balanced_bst` ở trên yêu cầu:

```text
keys[i - 1] < keys[i]
```

Nếu đầu vào là:

```text
10, 20, 20, 20, 30
```

thì dãy chỉ **không giảm** (non-decreasing), không **tăng nghiêm ngặt** (strictly increasing). Không nên cứ lấy phần tử giữa rồi mặc định các khóa trong nửa trái nhỏ hơn và trong nửa phải lớn hơn gốc.

Với các khóa trùng, hãy xác định kiểu dữ liệu trừu tượng:

| Nhu cầu | Chính sách phù hợp |
| --- | --- |
| **BST-set** | Mỗi khóa xuất hiện một lần, loại các bản sao |
| **BST-map** | Mỗi khóa chỉ có một giá trị; xác định quy tắc gộp/cập nhật khi trùng |
| **BST-multiset** | Một nút cho mỗi khóa phân biệt và trường `count` |
| **BST-multimap** | Một nút cho mỗi khóa phân biệt và danh sách các giá trị của khóa ấy |

Nếu dùng một nút và trường `count`, có thể **gom bản sao trước** rồi dựng BST trên **các khóa phân biệt**; số lượng bản sao không quyết định chiều cao theo số nút.

### Ví dụ gộp số lần xuất hiện

```python
def count_groups(sorted_keys):
    """Trả [(key, count), ...] từ dãy không giảm."""
    groups = []

    for key in sorted_keys:
        if not groups or groups[-1][0] != key:
            groups.append((key, 1))
        else:
            old_key, old_count = groups[-1]
            groups[-1] = (old_key, old_count + 1)

    return groups


groups = count_groups([10, 20, 20, 20, 30, 30])

assert groups == [(10, 1), (20, 3), (30, 2)]
```

Hàm `count_groups` có thời gian `O(m)` cho `m` bản sao và tạo nhiều nhất `u` nhóm (với `u` là số khóa phân biệt). Sau đó có thể dựng cây trên `u` khóa, lưu `count` của mỗi nhóm như payload.

**Cần lưu ý:** ví dụ gộp giả định dãy **đã không giảm** và phép `==` đồng ý với cách xác định khóa trùng. Với comparator tùy biến, phải nhóm theo **tính tương đương của comparator**, không nhất thiết theo `==` của Python.

## 16. Comparator tùy biến và thứ tự sắp xếp

Trong ví dụ Python, các khóa số dùng toán tử `<`. Thực tế khóa có thể là:

- Chuỗi mã học viên.
- Thời điểm bắt đầu buổi học.
- Tuple `(priority, task_id)`.
- Đối tượng với quy tắc so sánh riêng.

Thuật toán dựng trung vị **không quan tâm giá trị số** của khóa, mà quan tâm **thứ tự do comparator định nghĩa**. Nếu cây sẽ tìm kiếm theo `compare(a,b)`, dãy đầu vào phải được sắp bằng **chính comparator ấy**.

Ví dụ mã học viên:

```text
"HV2", "HV10", "HV100"
```

Theo thứ tự từ điển mặc định, `"HV10"` có thể đứng trước `"HV2"`; nếu nghiệp vụ yêu cầu so phần số, thứ tự mong muốn sẽ khác.

### Quan hệ thứ tự phải nhất quán

Ta cần một thứ tự đủ chặt để quyết định:

- `a < b`: đưa `a` về phía trái của `b`.
- `a > b`: đưa `a` về phía phải.
- `a` và `b` tương đương: áp dụng chính sách khóa trùng.

Nếu comparator không bắc cầu hoặc không nhất quán, không thể bảo đảm các đường tìm kiếm phù hợp với cách phân nhánh của BST.

Đặc biệt, giá trị số thực `NaN` không thỏa các quy tắc so sánh thứ tự thông thường theo cách mong đợi; nên đặt chính sách rõ ràng trước khi dùng làm khóa. **Dãy chỉ trông “có vẻ đã sắp” chưa đủ** nếu phép so sánh của cây khác phép so sánh dùng để sắp.

## 17. Dựng từ sorted iterator khi biết trước số phần tử

Dãy đã sắp đôi khi đến từ một **iterator/generator**, không phải list cho phép truy cập chỉ số. Ta vẫn có thể dựng BST cân đối trong **`O(n)` thời gian** nếu **biết trước `n`** và iterator cung cấp khóa theo thứ tự tăng.

Ý tưởng tinh tế là dùng **thứ tự duyệt giữa ngay trong lúc dựng**:

1. Với `n` nút cần dựng, dựng trước **cây con trái** từ khoảng `n//2` phần tử đầu của iterator.
2. Lấy **khóa tiếp theo** làm khóa nút gốc.
3. Dựng cây con phải từ `n - 1 - n//2` phần tử tiếp theo.
4. Gắn `parent` và tính lại metadata.

### Mã Python dựng từ iterator

```python
def build_from_sorted_iterable(ordered_keys, count):
    """Dựng BST cân đối từ đúng count khóa tăng nghiêm ngặt."""
    if count < 0:
        raise ValueError("count không được âm")

    source = iter(ordered_keys)
    has_previous = False
    previous = None

    def read_next():
        nonlocal has_previous, previous
        key = next(source)  # StopIteration nếu dữ liệu thiếu

        if has_previous and not (previous < key):
            raise ValueError("Iterator không tăng nghiêm ngặt")

        previous = key
        has_previous = True
        return key

    def build(n):
        if n == 0:
            return None

        left_count = n // 2
        left = build(left_count)

        # Chỉ sau khi dựng cây trái mới lấy khóa giữa.
        node = Node(read_next())
        node.left = left
        if left is not None:
            left.parent = node

        node.right = build(n - left_count - 1)
        if node.right is not None:
            node.right.parent = node

        node.subtree_size = (
            1 + node_size(node.left) + node_size(node.right)
        )
        node.height = (
            1 + max(node_height(node.left), node_height(node.right))
        )
        return node

    root = build(count)

    # Bảo đảm không có phần tử thừa sau count khóa.
    sentinel = object()
    if next(source, sentinel) is not sentinel:
        raise ValueError("Iterator chứa nhiều hơn count khóa")

    return root
```

Kiểm thử:

```python
stream_root = build_from_sorted_iterable(
    (k for k in range(1, 16)), count=15
)

assert validate_bst(stream_root)
assert inorder_keys(stream_root) == list(range(1, 16))
assert stream_root.height == 4
```

### Điểm khác với phiên bản dùng chỉ số

Ở phiên bản này, nút gốc của một cây con **được tạo sau khi dựng cây con trái**, vì iterator phải tiêu thụ các khóa nhỏ hơn trước mới tới khóa giữa. Do đó, ta gắn `left.parent = node` **sau khi tạo node**, không thể truyền sẵn parent khi dựng cây trái theo cách thông thường.

Bằng cách dựng `n//2` nút bên trái, một nút ở giữa và phần còn lại bên phải, ta vẫn tạo được cây cân đối với in-order đúng thứ tự iterator.

**Giới hạn bắt buộc:** phải biết trước số phần tử `count`. Nếu không biết độ dài và không thể đếm trước, một lượt duyệt duy nhất không đủ thông tin để chọn vị trí trung vị ngay từ đầu theo công thức này; ta cần thêm một lượt đếm nếu nguồn cho phép duyệt lại, hoặc lưu dữ liệu/áp dụng một chiến lược khác.

**Độ phức tạp:** `O(n)` thời gian, `O(log n)` call stack, cộng `O(n)` bộ nhớ cho các nút đầu ra. Nếu iterator phát sinh ít hơn `count` mục, thao tác `next` sẽ báo thiếu; nếu thừa, ví dụ chủ động phát hiện và báo lỗi. Dữ liệu vi phạm thứ tự tăng cũng bị từ chối trong lúc tiêu thụ.

## 18. Metadata phải được tính sau khi dựng hai cây con

Nếu nút lưu `subtree_size`, `height` hay tổng dữ liệu của cây con, thuật toán dựng trực tiếp có lợi thế: **khi rời một lời gọi đệ quy, cả hai cây con đã hoàn thành**.

Với kích thước:

```text
size(node) = 1 + size(node.left) + size(node.right)
size(None) = 0
```

Với chiều cao:

```text
height(node) = 1 + max(height(node.left), height(node.right))
height(None) = 0
```

Mỗi công thức được tính trong **`O(1)`** khi metadata của các con đã đúng. Tổng chi phí cập nhật cho `n` nút là `O(n)`, không cần duyệt thêm một lượt riêng.

### Ví dụ rank/select dùng subtree_size

Một BST được bổ sung `subtree_size` có thể hỗ trợ:

- `rank(x)`: số khóa nhỏ hơn `x`.
- `select(i)`: khóa đứng ở chỉ số `i` trong thứ tự tăng (đếm từ 0).

```python
def select_key(root, index):
    """Trả khóa thứ index (0-based), hoặc None nếu ngoài phạm vi."""
    if root is None or index < 0:
        return None
    if index >= root.subtree_size:
        return None

    current = root
    k = index

    while current is not None:
        left_size = node_size(current.left)

        if k < left_size:
            current = current.left
        elif k == left_size:
            return current.key
        else:
            k -= left_size + 1
            current = current.right

    raise AssertionError("subtree_size không nhất quán")


assert select_key(root, 0) == 1
assert select_key(root, 7) == 8
assert select_key(root, 14) == 15
assert select_key(root, 15) is None
```

Trên cây cân đối vừa dựng, `select` mất `O(log n)` thời gian trong trường hợp xấu nhất, với metadata chính xác.

### Sau này nếu cây bị chèn/xóa thì sao?

Sau khi xây, mọi thao tác làm thay đổi liên kết hoặc số nút phải **duy trì lại metadata trên những nút bị ảnh hưởng**. Không được giả định `subtree_size` và `height` sẽ tự cập nhật chỉ vì chúng từng đúng lúc dựng.

Nếu sau đó dùng một cây AVL hoặc đỏ–đen, các phép quay còn phải sửa `parent`, `height` và các trường liên quan theo đúng thuật toán của cấu trúc ấy.

## 19. Dựng cân đối ban đầu không có nghĩa tự cân bằng về sau

Một cây dựng từ sorted keys có thể rất cân đối **tại thời điểm khởi tạo**, nhưng bản thân thuật toán dựng không cung cấp cơ chế duy trì chiều cao trong các lần cập nhật sau.

Ví dụ:

```text
Dựng trực tiếp từ 1..7:

          4
         /  \
        2    6
       / \  / \
      1  3 5   7

Tiếp tục chèn tuần tự 8,9,10,11 vào BST thường:

          4
         /  \
        2    6
       / \  / \
      1  3 5   7
                \
                 8
                  \
                   9
                    \
                     10
                       \
                        11
```

Cây vẫn thỏa BST nhưng nhánh ngoài cùng bên phải kéo dài.

**Dựng cân đối và duy trì cân đối là hai công việc khác nhau.**

Nếu ứng dụng liên tục chèn/xóa và cần bảo đảm tìm kiếm `O(log n)` cho **mọi trạng thái**, hãy sử dụng **BST tự cân bằng** như AVL hoặc cây đỏ–đen, hoặc một thư viện ordered map/set có hợp đồng độ phức tạp tương ứng.

### Khi nào dựng lại toàn cây?

Nếu ứng dụng chủ yếu đọc và chỉ cập nhật theo từng đợt, có thể:

1. Tập hợp một ảnh chụp khóa/giá trị đã sắp.
2. Dựng lại BST cân đối `O(n)` từ ảnh chụp ấy.
3. Thay con trỏ gốc theo cơ chế nhất quán của hệ thống.

Tuy nhiên, **dựng lại thường xuyên** có chi phí `O(n)` mỗi lượt, cần xét bộ nhớ đỉnh (cây cũ và cây mới có thể cùng tồn tại) cũng như các tham chiếu hoặc iterator đang trỏ vào cây cũ. Đây không phải lựa chọn mặc định cho mọi lần chèn.

## 20. So sánh với chèn tuần tự, chèn trung vị trước và mảng đã sắp

Với **cùng một dãy `n` khóa phân biệt đã sắp**, có nhiều cách lưu trữ:

| Phương án | Chi phí xây dựng | Hình dạng/chiều cao cuối | Tìm khóa sau khi dựng |
| --- | --- | --- | --- |
| **Chèn tuần tự tăng vào BST thường** | `Θ(n²)` | Cây lệch, `h=n` | `O(n)` trường hợp xấu nhất |
| **Chèn theo thứ tự trung vị trước vào BST thường** | `O(n log n)` | Cân đối, `h=O(log n)` | `O(log n)` |
| **Dựng trực tiếp bằng khoảng chỉ số** | **`Θ(n)`** | Cân đối, `h=O(log n)` | `O(log n)` |
| **Giữ nguyên mảng đã sắp** | Không cần dựng thêm cây | Không có cây | `O(log n)` qua tìm nhị phân |
| **Nạp vào cây tự cân bằng bằng insert** | `O(n log n)` theo các phép chèn | Bảo đảm `O(log n)` | `O(log n)` |

Dựng cây trực tiếp `O(n)` không có nghĩa nó luôn ưu việt hơn **mảng đã sắp**. Mảng có thể truy cập ngẫu nhiên theo chỉ số `O(1)`, có locality bộ nhớ tốt và hỗ trợ tìm nhị phân; trong khi BST tiêu tốn thêm bộ nhớ con trỏ/nút.

Ngược lại, cây có cấu trúc liên kết linh hoạt và khả năng hỗ trợ cập nhật, iterator theo thứ tự hoặc augmentation thích hợp, nhưng cần **duy trì cân bằng** nếu mong muốn bảo đảm thời gian cập nhật logarit.

### Chọn theo đặc tính công việc

- **Dữ liệu gần như tĩnh, chỉ tìm kiếm/range:** mảng đã sắp thường đủ tốt.
- **Cần BST để học hoặc truy vấn theo nút:** dựng trực tiếp từ dãy đã sắp là cách tốt.
- **Cập nhật động và cần thứ tự:** cân nhắc AVL/đỏ–đen hay ordered map thư viện.
- **Chỉ tra cứu chính xác, không cần thứ tự:** bảng băm có thể phù hợp hơn.
- **Dữ liệu lớn nằm trên đĩa:** chỉ mục B-tree/B+ tree thường gần nhu cầu lưu trữ thực tế hơn BST con trỏ trong RAM.

## 21. Trường hợp biên cần kiểm thử

### Dãy rỗng

```python
assert build_balanced_bst([]) is None
assert build_balanced_map([]) is None
```

Không nên tạo một “nút rỗng” giả nếu hợp đồng của cây rỗng là `root=None`.

### Một khóa

```python
single = build_balanced_bst([42])

assert single.key == 42
assert single.left is None
assert single.right is None
assert single.parent is None
assert single.height == 1
assert single.subtree_size == 1
```

### Hai khóa

```python
two = build_balanced_bst([10, 20])

assert inorder_keys(two) == [10, 20]
assert two.height == 2
assert two.key == 20  # Giữa lệch phải theo công thức mid
assert two.left.key == 10
assert two.right is None
```

### Khóa trùng hoặc chưa sắp

```python
def expect_bad_input(keys):
    try:
        build_balanced_bst(keys)
    except ValueError:
        return
    raise AssertionError("Phải từ chối dãy chưa tăng nghiêm ngặt")


expect_bad_input([10, 20, 20, 30])
expect_bad_input([10, 30, 20, 40])
expect_bad_input([30, 20, 10])
```

### Dãy tăng nhưng không cách đều

```python
sparse = [-100, -5, 0, 7, 80, 1000]
sparse_root = build_balanced_bst(sparse)

assert inorder_keys(sparse_root) == sparse
assert sparse_root.height == 3
assert validate_bst(sparse_root)
```

**Chọn trung vị theo vị trí**, không phải theo khoảng cách số học giữa hai khóa. Cây đúng bất biến ngay cả khi khoảng cách giữa các khóa rất lớn hoặc không đều.

### Đầu vào không được thay đổi

```python
original = [5, 15, 25, 35, 45]
snapshot = original.copy()

result_root = build_balanced_bst(original)

assert original == snapshot
assert inorder_keys(result_root) == original
```

Thuật toán tham chiếu các phần tử của list, không sắp xếp lại hoặc xóa phần tử của list đầu vào.

## 22. Những sai lầm thường gặp

1. **Chèn tuần tự dãy đã sắp vào BST thường rồi gọi đó là “dựng cân đối”.** Cây có thể lệch hoàn toàn.
2. **Chọn phần tử giữa theo giá trị số học thay vì vị trí.** Với khóa không cách đều, cách này không bảo đảm hai phía có số nút gần nhau.
3. **Không kiểm tra đầu vào đã sắp.** Một cây được dựng từ các nửa theo chỉ số có thể vi phạm thứ tự nếu dãy đầu vào lộn xộn.
4. **Không có chính sách khóa trùng.** Khóa bằng gốc có thể xuất hiện trong cây con và phá bất biến nghiêm ngặt.
5. **Dùng `mid` trong cả đoạn con trái và làm gốc.** Gây trùng khóa hoặc đệ quy không kết thúc.
6. **Nhầm đoạn nửa mở `[lo,hi)` với đoạn đóng.** Dễ sai cơ sở dừng và bỏ sót/phát lặp phần tử.
7. **Quên trường hợp dãy rỗng.** Có thể truy cập chỉ số không hợp lệ.
8. **Đòi gốc phải có một khóa duy nhất khi `n` chẵn.** Có hai lựa chọn giữa hợp lệ.
9. **Chỉ kiểm tra hai con trực tiếp thay vì toàn bộ cây con.** Không đủ để xác minh bất biến BST.
10. **Cho rằng mọi BST có chiều cao `O(log n)`.** Chỉ đúng khi có bảo đảm về hình dạng hoặc cơ chế cân bằng.
11. **Dùng slicing trên mọi lời gọi nhưng vẫn báo thời gian dựng `O(n)`.** Copy list có thể gây `O(n log n)` thời gian.
12. **Lẫn lộn bộ nhớ chứa cây `O(n)` với bộ nhớ phụ đệ quy `O(log n)`.**
13. **Tính `subtree_size` trước khi dựng hai con.** Metadata sẽ chỉ thấy một phần cây con.
14. **Gắn `child.parent` về sai nút.** Tìm xuống có thể đúng nhưng đi ngược tổ tiên sai.
15. **Sao chép key mà quên value khi dựng BST-map.** Cây tăng khóa nhưng ánh xạ dữ liệu bị hỏng.
16. **Dùng comparator khác lúc dựng và lúc tìm.** Có thể dẫn tìm kiếm sang nhánh sai.
17. **Coi phần tử trùng theo `==` dù comparator xem là tương đương theo quy tắc khác.** Chính sách key duy nhất bị phá.
18. **Dựng cân đối xong nhưng tiếp tục chèn tăng dần mà không duy trì cân bằng.** Chiều cao có thể lại tăng tuyến tính.
19. **Tái dựng cây trong hệ thống đang có iterator mà không có hợp đồng nhất quán.** Tham chiếu tới nút cũ có thể không còn đại diện cây hiện tại.
20. **Xem các đoạn mã có assert là đã thực hiện Content QA đầy đủ.** Ví dụ học tập vẫn cần vòng kiểm tra chuyên môn riêng nếu đưa vào sản phẩm giáo dục.

## 23. Kiểm thử theo tính chất (property-based thinking)

Ngoài các ví dụ với `n=15`, ta nên thử **nhiều kích thước** và đối chiếu các tính chất không phụ thuộc vào hình dạng chính xác.

### Tính chất cần kiểm tra

Với một dãy khóa `keys` tăng nghiêm ngặt:

- `inorder_keys(build(keys)) == keys`.
- Số nút đạt tới được từ gốc là `len(keys)`.
- `root.subtree_size == len(keys)` nếu cây không rỗng.
- `root.height == len(keys).bit_length()` với `n >= 1`, tương đương `floor(log₂ n)+1` và bằng `ceil(log₂(n+1))`.
- Mọi `parent` và giới hạn thứ tự từ tổ tiên đều đúng.
- Khóa trong dãy đều tìm thấy; khóa ngoài dãy không được tạo thêm.
- Giá trị map đi kèm giữ nguyên.

### Vòng kiểm tra nhiều kích thước

```python
for n in range(0, 129):
    ordered = [3 * i + 1 for i in range(n)]
    r = build_balanced_bst(ordered)

    assert validate_bst(r)
    assert inorder_keys(r) == ordered

    if n == 0:
        assert r is None
    else:
        assert r.subtree_size == n
        assert r.height == n.bit_length()
        assert r.parent is None

        assert search(r, ordered[0]) is not None
        assert search(r, ordered[-1]) is not None
```

**Vì sao `n.bit_length()` đúng?** Với `n >= 1`, số bit cần biểu diễn `n` ở hệ nhị phân bằng `floor(log₂n)+1`, đúng bằng chiều cao nhỏ nhất của một cây nhị phân chứa `n` nút.

Để kiểm thử mạnh hơn, có thể lấy những tập khóa **không cách đều**, giữ thứ tự tăng, rồi dựng lại. Điều đó xác nhận thuật toán phụ thuộc vào **thứ tự** chứ không dựa vào khoảng cách số học.

Các kiểm thử này phục vụ người học tự xác minh. Chúng **không thay thế** vòng Content QA chuyên môn ở bước sau của quy trình tạo học liệu.

## 24. Bài tập tự luyện

**Bài 1.** Vì sao BST từ dãy `[10,20,30,40,50,60,70]` có thể có hai hình dạng rất khác nhau? Nêu điều kiện của bất biến BST và chiều cao hai cây mẫu.

**Bài 2.** Dùng thuật toán chọn trung vị để dựng cây từ `[1,2,3,4,5,6,7]`. Viết gốc, hai con của gốc và kết quả in-order.

**Bài 3.** Với `[10,20,30,40,50,60,70,80]` và `mid=(lo+hi)//2`, khóa nào làm gốc? Hai cây con ban đầu có bao nhiêu nút?

**Bài 4.** Với `n=15` và `n=16`, chiều cao tối thiểu của cây nhị phân tính theo số nút trên đường dài nhất là bao nhiêu?

**Bài 5.** Chứng minh bằng quy nạp rằng chọn phần tử giữa từ một dãy tăng nghiêm ngặt sẽ tạo BST hợp lệ với toàn bộ khóa xuất hiện đúng một lần.

**Bài 6.** Viết giả mã dựng trực tiếp từ đoạn chỉ số nửa mở `[lo,hi)`. Tại sao nhánh phải phải bắt đầu tại `mid+1` thay vì `mid`?

**Bài 7.** Phân tích thời gian và bộ nhớ phụ của thuật toán dựng trực tiếp bằng chỉ số khi đầu vào đã sắp. Vì sao tổng thời gian không phải `O(n log n)`?

**Bài 8.** Một lập trình viên dùng `keys[:mid]` và `keys[mid+1:]` ở mọi lời gọi. Cây có còn cân đối không? Chi phí có thể thay đổi ra sao?

**Bài 9.** Nếu dữ liệu đầu vào chưa sắp, có thể chỉ chọn phần tử ở giữa theo chỉ số rồi gắn hai nửa để được BST hợp lệ không? Nêu một phản ví dụ.

**Bài 10.** Dãy `[10,20,20,30,40]` vi phạm điều kiện gì? Hãy đề xuất hai chính sách hợp lý cho BST-set và BST-multiset.

**Bài 11.** Một BST-map chứa `(10,"An"),(20,None),(30,"Bình")`. Dựng theo trung vị cần làm gì để không gắn sai giá trị? Cây có bao nhiêu nút?

**Bài 12.** Tại sao `subtree_size` và `height` nên được tính **sau** khi dựng hai cây con? Nêu công thức cho hai trường này.

**Bài 13.** Nếu chỉ có iterator tăng dần và biết `count=7`, hãy mô tả cách dựng cây từ `count//2` phần tử đầu, phần tử tiếp theo và các phần tử còn lại.

**Bài 14.** Nếu iterator không cho biết số phần tử và không thể duyệt lại, giải pháp dựng từ iterator của bài còn áp dụng trực tiếp không? Cần thêm giả thiết hoặc tài nguyên nào?

**Bài 15.** So sánh dựng trực tiếp từ dãy đã sắp `O(n)` với chèn trung vị trước `O(nlog n)` và chèn tăng tuần tự `Θ(n²)`. Chiều cao cuối của mỗi phương án?

**Bài 16.** Nếu cây được dựng cân đối một lần, sau đó chèn liên tục các khóa tăng lớn hơn mọi khóa cũ vào BST không tự cân bằng, chiều cao có được bảo đảm logarit không?

**Bài 17.** Với dữ liệu gần như tĩnh đã sắp, vì sao một mảng có thể phù hợp hơn BST? Nêu một nhu cầu khiến cây có thứ tự hữu ích hơn.

**Bài 18.** Vì sao một dãy có thể “đã sắp” theo comparator A nhưng không phù hợp để dựng BST dùng comparator B?

**Bài 19.** Cho `keys=[-100,-7,2,3,100000]`, chọn phần tử giữa làm gốc. Có cần dùng khoảng cách tuyệt đối giữa các khóa để cân bằng không?

**Bài 20.** Đề xuất bộ kiểm thử bao gồm dãy rỗng, một nút, số lượng chẵn/lẻ, khóa trùng, đầu vào chưa sắp, giá trị `None` và metadata `parent/subtree_size/height`.

<details>
<summary>Đáp án và gợi ý</summary>

1. BST hợp lệ chỉ yêu cầu mọi khóa trái nhỏ hơn và mọi khóa phải lớn hơn ở toàn bộ cây con. Chèn tăng dần có thể tạo chuỗi `h=7`; chọn trung vị tạo cây gốc `40` có `h=3`.
2. Gốc `4`, con trái `2`, con phải `6`; tiếp tục dựng các nút `1,3,5,7`. In-order là `1,2,3,4,5,6,7`.
3. `mid=4` → khóa gốc `50`, cây trái có `4` nút (`10..40`), cây phải có `3` nút (`60..80`).
4. `n=15` có `h=4`; `n=16` có `h=5` theo `ceil(log₂(n+1))`.
5. Dãy tăng bảo đảm mọi khóa ở đoạn trái `< key[mid]` và mọi khóa đoạn phải `> key[mid]`; theo giả thiết quy nạp, hai cây con đúng BST. Chia đoạn không chồng lấn nên mọi khóa xuất hiện đúng một lần.
6. `build(lo,hi)`: rỗng nếu `lo>=hi`; chọn `mid=lo+(hi-lo)//2`; dựng trái `[lo,mid)`, dựng phải `[mid+1,hi)`. Bắt đầu phải từ `mid+1` để không dựng lại gốc.
7. Mỗi trong `n` phần tử tạo đúng một nút, công việc quanh nút `O(1)`, tổng `Θ(n)`. Độ sâu chia đôi `O(log n)` nên call stack `O(log n)`; ngoài ra `O(n)` để lưu các nút.
8. Cây vẫn đúng BST/cân đối nếu đầu vào hợp lệ, nhưng slicing sao chép nhiều phần tử qua các tầng, gây `O(n log n)` thời gian và bộ nhớ trung gian.
9. Không. Ví dụ `[10,30,20]` chọn gốc `30` (chỉ số 1) thì cây phải chứa `20 < 30`, vi phạm bất biến.
10. Hai khóa `20` bằng nhau phá điều kiện tăng nghiêm ngặt. BST-set có thể khử trùng, dùng `[10,20,30,40]`; BST-multiset có thể gom `count(20)=2` tại một nút.
11. Phải dựng theo **khóa** và mang theo **giá trị của đúng cặp** vào cùng nút. Cây có ba nút; `value=None` của khóa `20` vẫn là giá trị hợp lệ.
12. `subtree_size=1+size(left)+size(right)`; `height=1+max(height(left),height(right))`. Cần metadata hai con đã đúng mới tính được cha.
13. Dựng cây trái từ `3` mục đầu; lấy khóa thứ tư làm gốc; dựng cây phải từ `3` mục còn lại. Kết quả in-order trùng thứ tự iterator.
14. Không trực tiếp theo công thức cần `count`. Có thể đếm trước nếu nguồn tái duyệt được, lưu một lượt vào mảng để biết `n`, hoặc dùng một cơ chế xây khác.
15. Dựng trực tiếp `Θ(n)` với `h=O(log n)`; chèn trung vị trước `O(nlog n)` với `h=O(log n)`; chèn tăng tuần tự `Θ(n²)` với `h=n`.
16. Không. Những lần chèn mới có thể tạo chuỗi kéo dài phía phải; dựng cân đối ban đầu không thay thế thuật toán tự cân bằng.
17. Mảng đã sắp hỗ trợ truy cập chỉ số `O(1)`, tìm nhị phân `O(log n)`, thuận lợi về bộ nhớ và không cần con trỏ. BST/cây cân bằng hữu ích khi muốn các cập nhật liên kết hoặc augmentation theo thứ tự với yêu cầu phù hợp.
18. BST phân nhánh theo comparator lúc tìm/chèn. Nếu đầu vào được sắp bằng comparator khác, các khóa nằm trước/sau trung vị theo chỉ số có thể không nhỏ hơn/lớn hơn theo comparator của BST.
19. Phần tử giữa là `2`. Không cần xét khoảng cách số học; thuật toán cân đối **số nút** ở hai nửa và giữ thứ tự khóa.
20. Kiểm tra `inorder == keys`, tổng số nút, `root.parent=None`, liên kết hai chiều, biên BST toàn cây, metadata được tính độc lập, chiều cao `ceil(log₂(n+1))`, xử lý đúng `n=0,1`, chẵn/lẻ, từ chối dãy trùng/chưa sắp và bảo toàn `value=None`.

</details>

## Ghi nhớ

**Với một dãy khóa phân biệt đã sắp tăng**, cách dựng BST cân đối trực tiếp là **chọn phần tử giữa làm gốc, dựng nửa trái thành cây con trái, dựng nửa phải thành cây con phải**. Khi dùng **khoảng chỉ số trên cùng dãy**, mỗi khóa tạo đúng một nút, nên thời gian dựng là **`Θ(n)`**, bộ nhớ phụ đệ quy **`O(log n)`** và bộ nhớ chứa BST **`O(n)`**. Cây có chiều cao tối thiểu **`ceil(log₂(n+1))`** theo quy ước số nút trên đường dài nhất, nhờ đó tìm kiếm theo khóa có giới hạn `O(log n)` ngay sau khi dựng. Hãy xử lý đúng **đoạn rỗng, số phần tử chẵn, khóa trùng, comparator và cặp `(key,value)`**; tránh **slicing list** nếu cần bảo đảm thời gian dựng tuyến tính. Cuối cùng, **dựng cây cân đối một lần không tự duy trì cân bằng sau các thao tác chèn/xóa**: với dữ liệu động cần bảo đảm chi phí, hãy dùng BST tự cân bằng thích hợp.
