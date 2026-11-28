# Giữ đúng liên kết cha, gốc và thông tin phụ khi xóa

Một **cây tìm kiếm nhị phân** (*Binary Search Tree – BST*) không chỉ là tập khóa được nối bằng các con trỏ. Một hiện thực thực tế có thể còn lưu **con trỏ cha** (`parent`), **gốc cây** (`root`), **tổng số nút** (`size`), **kích thước từng cây con** (`subtree_size`), chiều cao, hoặc dữ liệu tổng hợp để hỗ trợ truy vấn nhanh.

Khi xóa một khóa, việc làm cho khóa ấy biến mất khỏi phép duyệt in-order **chưa đủ**. Nếu `parent` vẫn trỏ về nút đã bị tháo, hoặc `subtree_size` chưa giảm, các thao tác đi ngược lên cha, tìm hạng (*rank*), chọn phần tử thứ `k`, hoặc cân bằng cây có thể cho kết quả sai. Đặc biệt, trường hợp xóa **gốc** và xóa nút có **hai con** dễ làm lộ những lỗi đó.

Bài học thuộc chương **Cây tìm kiếm nhị phân** trong module cấu trúc dữ liệu. Ta sẽ lập ra những bất biến cần duy trì, xây một hàm thay liên kết thống nhất, phân biệt nút bị xóa về mặt logic với nút bị tháo vật lý, cài Python cho cả **tiền nhiệm** và **kế nhiệm**, rồi kiểm tra cả thứ tự khóa **lẫn thông tin phụ**.

## 1. Một phép xóa BST đúng phải bảo toàn những gì?

Ta xét BST có **khóa phân biệt**, so sánh bằng một thứ tự nhất quán. Với mỗi nút có khóa `k`:

- Tất cả khóa trong **toàn bộ cây con trái** nhỏ hơn `k`.
- Tất cả khóa trong **toàn bộ cây con phải** lớn hơn `k`.
- Hai cây con cũng tuân theo cùng bất biến.

Khi hiện thực có thêm trường `parent` và `subtree_size`, những bất biến quan trọng khác là:

| Bất biến | Nội dung |
| --- | --- |
| **Thứ tự BST** | Mọi khóa trái `< key <` mọi khóa phải tại từng nút |
| **Gốc** | `root is None` khi cây rỗng; nếu không rỗng, `root.parent is None` |
| **Liên kết hai chiều** | Nếu `p.left is c` hoặc `p.right is c` thì `c.parent is p` |
| **Không có nút mồ côi còn là thành viên cây** | Mọi nút logic phải đi tới được từ `root` bằng liên kết con |
| **Cấu trúc cây** | Không có chu trình, không có hai đường từ gốc tới cùng một nút |
| **Kích thước cây con** | `node.subtree_size = 1 + size(node.left) + size(node.right)` |
| **Kích thước toàn cây** | `tree.size == 0` nếu rỗng; nếu không, `tree.size == root.subtree_size` |
| **Ánh xạ khóa–giá trị** | Với tree map, mỗi khóa còn lại gắn với đúng `value` của nó |

Ta sẽ dùng hàm `size(None) = 0` trong các công thức. Trường `subtree_size` đếm **số nút trong cây con bắt đầu tại nút hiện tại**, gồm cả chính nó, không phải số con trực tiếp.

Ví dụ:

```text
                  50 [size=5]
                /             \
          30 [size=3]       80 [size=1]
          /       \
     20 [size=1]  40 [size=1]
```

Ở đây `50.subtree_size = 1 + 3 + 1 = 5`, còn `30.subtree_size = 1 + 1 + 1 = 3`. Nếu xóa `20` mà chỉ bỏ liên kết nhưng giữ `30.subtree_size = 3` và `50.subtree_size = 5`, cấu trúc khóa có thể vẫn là BST, **nhưng metadata đã sai**.

## 2. Phân biệt “xóa khóa logic” với “tháo nút vật lý”

Trong BST thông thường, có ba tình huống:

1. **Nút lá:** tháo nút, thay liên kết tới nó bằng `None`.
2. **Nút một con:** tháo nút, thay liên kết tới nó bằng gốc **cây con duy nhất**.
3. **Nút hai con:** thường sao chép cặp `(key, value)` từ **kế nhiệm** hoặc **tiền nhiệm** vào nút đang xét, rồi tháo **nút thay thế** ở chỗ cũ.

Với trường hợp thứ ba, cần phân biệt:

- **Khóa cần xóa** là `target.key`, biến mất về mặt logic.
- **Đối tượng nút bị tháo khỏi các liên kết** lại là `successor` hoặc `predecessor`.
- **Đối tượng nút ở vị trí ban đầu** thường còn nằm trong cây, nhưng mang **khóa và giá trị của nút thay thế**.

Ví dụ trước khi xóa khóa `50`:

```text
           50 [object A]
          /              \
        30              80
                       /
                     60 [object B]
```

Sau khi **sao chép kế nhiệm**:

```text
           60 [object A, key đổi từ 50 thành 60]
          /              \
        30               80

object B đã được tháo khỏi cây.
```

Điều này quan trọng khi bên ngoài giữ tham chiếu đến các đối tượng nút: một tham chiếu tới **A** vẫn hợp lệ nhưng có thể thấy khóa mới; một tham chiếu tới **B** có thể trỏ đến một đối tượng **không còn là thành viên BST**. Bài này xem nút là **chi tiết triển khai nội bộ**, không cam kết giữ danh tính nút theo khóa qua phép xóa.

## 3. Liên kết cha–con phải khớp theo cả hai chiều

Nếu `parent.left` trỏ tới một nút `child`, thì `child.parent` phải trỏ ngược về `parent`. Tương tự với `parent.right`.

```text
          parent
          /    \
       child    ...
          ↑
   child.parent phải là parent
```

Khi thay con `old` của `parent` bằng `replacement`:

1. Xác định `old` nằm bên **trái** hay **phải** theo **danh tính đối tượng**.
2. Gán đúng liên kết `parent.left` hoặc `parent.right` thành `replacement`.
3. Nếu `replacement` khác `None`, gán `replacement.parent = parent`.
4. Sau khi thay liên kết thành công, tách `old` khỏi cây nếu nó thực sự đã bị tháo.
5. Cập nhật metadata trên những đường tổ tiên bị ảnh hưởng.

**Không được chỉ sửa một chiều:**

```python
# Sai nếu dùng parent pointer:
parent.left = child
# ... nhưng quên child.parent = parent
```

Khi đó, tìm kiếm **đi xuống** bằng `left/right` có thể vẫn đúng, nhưng đi **lên** từ `child` bằng `parent` lại quay về nút đã bị xóa.

### Xác định phía bằng tham chiếu, không chỉ bằng so sánh khóa

Với BST khóa duy nhất và thứ tự nhất quán, ta có thể suy luận phía con từ khóa. Tuy nhiên, khi đã có tham chiếu `old` và `parent`, kiểm tra:

```python
if parent.left is old:
    parent.left = replacement
else:
    assert parent.right is old
    parent.right = replacement
```

thường trực tiếp và vững hơn. Nó biểu diễn chính xác **liên kết nào đang chứa đối tượng phải tháo**.

Với kiểu `Node` tự viết trong Python, toán tử `is` kiểm tra **cùng đối tượng**, khác `==` có thể bị định nghĩa lại để so khóa hoặc dữ liệu.

## 4. Gốc là trường hợp không có cha

Bất biến của gốc:

```text
tree.root is None
hoặc
tree.root.parent is None
```

Khi nút cần tháo chính là `root` và có tối đa một con, không tồn tại `parent.left` hoặc `parent.right` để thay. Phải cập nhật **chính `tree.root`**.

### Xóa nút gốc duy nhất

```text
Trước:             Sau:

      50          (cây rỗng)
```

Kết quả: `root = None`, `size = 0`.

### Xóa gốc chỉ có một con

```text
Trước:                 Sau:

        50                    70
          \                  /  \
           70               60   80
          /  \
         60  80
```

Cập nhật:

```python
tree.root = old_root.right
tree.root.parent = None
```

Không phải tạo một bản sao của `70` và các hậu duệ. Chỉ chuyển tham chiếu gốc từ `50` sang `70`.

Khi xóa gốc có **hai con** theo chiến lược **sao chép cặp kế nhiệm**, đối tượng gốc vẫn còn trong cây; **chỉ khóa/value của nó thay đổi** và một nút khác được tháo ở phía dưới. Khi ấy `root.parent` vẫn phải là `None` và kích thước cây con ở gốc phải được cập nhật.

## 5. Một helper thay liên kết thống nhất

Thay vì viết lặp lại mọi trường hợp gốc, con trái và con phải ở nhiều đoạn xóa, ta có thể gom vào một hàm **thay một nút bằng cây con khác**.

Giả mã:

```text
REPLACE_LINK(tree, old, replacement):
    p = old.parent

    if p == null:
        tree.root = replacement
    else if p.left == old:
        p.left = replacement
    else:
        assert p.right == old
        p.right = replacement

    if replacement != null:
        replacement.parent = p

    return p
```

Giá trị trả về `p` chính là **tổ tiên gần nhất có thể cần cập nhật metadata** sau khi tháo một nút. Nếu `old` là gốc và `replacement` là đứa con duy nhất, subtree_size của `replacement` **đã đúng** theo số nút của cây con còn sống, nên không nhất thiết phải tính lại.

### Điều kiện bắt buộc trước khi gọi helper

Hàm này **chỉ thay liên kết**, không tự bảo đảm toàn bộ điều kiện BST. Người gọi phải chắc chắn:

- `old` đang là một nút thành viên cây.
- `replacement` phù hợp với các giới hạn thứ tự ở vị trí `old`.
- Các cây con cần giữ không bị bỏ quên.
- Việc thay liên kết không tạo chu trình.
- Nếu `old` có hai con, phải dùng thuật toán xử lý hai con trước; không thể chuyển tùy tiện một trong hai con vào vị trí cũ.

Đối với nút **không quá một con**, `replacement` chính là con còn lại, hoặc `None` nếu nút lá. Đối với **nút kế nhiệm**, `replacement` là `successor.right`. Đối với **nút tiền nhiệm**, `replacement` là `predecessor.left`.

## 6. Xóa nút lá: gỡ liên kết và giảm size dọc tổ tiên

Ví dụ ban đầu:

```text
                   50 [5]
                  /       \
              30 [3]     80 [1]
              /   \
           20 [1] 40 [1]
```

Muốn xóa `20`:

1. Tìm `20`; cha là `30`.
2. Nút `20` có hai con đều rỗng, nên `replacement = None`.
3. Thay `30.left = None`.
4. Giảm số nút toàn cây từ `5` xuống `4`.
5. Cập nhật `30.subtree_size = 2` và `50.subtree_size = 4`.

```text
Sau:
                   50 [4]
                  /       \
              30 [2]     80 [1]
                 \
                 40 [1]
```

Các nút `40` và `80` giữ nguyên kích thước cây con; chỉ những **tổ tiên của vị trí bị tháo** cần tính lại.

Nếu nút lá là gốc duy nhất, `root = None`, tổng số nút là 0; không có đường tổ tiên cần cập nhật.

## 7. Xóa nút một con: nối cả cây con và sửa parent

Ví dụ:

```text
                 50
                   \
                    70
                   /
                  60
                 /  \
                55  65
```

Nút `70` có **một con trực tiếp** là `60`, dù bên dưới `60` còn `55` và `65`.

Sau khi xóa `70`, gốc cây con `60` phải thay vị trí nó:

```text
                 50
                   \
                    60
                   /  \
                  55   65
```

Những thay đổi bắt buộc:

```text
50.right = 60
60.parent = 50
70.parent = None  (nếu tách sạch nút cũ)
70.left = None
```

Ta **không di chuyển từng hậu duệ** của `60`. Nút `55` và `65` vẫn trỏ về `60`, nên liên kết hai chiều bên trong cây con còn đúng.

Nếu đổi liên kết `50.right` nhưng bỏ qua `60.parent`, từ `60` đi ngược theo parent sẽ tới `70` đã bị xóa, làm sai thuật toán tìm tổ tiên hoặc kế nhiệm.

### Một cây con được bảo toàn nguyên vẹn

Không cần đặt lại `subtree_size` của `60`: trước và sau khi `70` bị tháo, tập nút bên trong cây con `60` vẫn là `{55,60,65}`, nên kích thước tại `60` không đổi. Chỉ các tổ tiên **phía trên** cần được tính lại.

Nếu nút bị xóa là gốc, `60.parent` phải thành `None`. Kích thước của gốc mới `60` đã bằng số nút còn sống.

## 8. Hai con: sao chép cặp rồi tháo nút kế nhiệm

Khi `target` có hai con, chọn:

```text
successor = minimum(target.right)
```

Nút kế nhiệm **không có con trái** nhưng có thể có **con phải**.

Quy trình đúng khi cài bằng phương án **sao chép cặp**:

1. Tìm `target` theo khóa.
2. Tìm `successor` và giữ được liên kết `successor.parent`.
3. Sao chép **cả `key` và `value`** từ `successor` vào `target`.
4. Thay liên kết tới `successor` bằng `successor.right`, và cập nhật `parent` của cây con thay thế.
5. Tính lại metadata từ **cha của nút kế nhiệm vừa tháo** lên tới gốc.
6. Giảm `tree._size` **đúng một lần**.

### Kế nhiệm ở sâu

```text
Trước xóa 50:

                50
               /  \
             30    80
                  /
                 60
                   \
                    70
                   /
                  65
```

Kế nhiệm là `60`. Nút này đang là con trái của `80`, và có con phải `70`.

Sau khi sao chép cặp `60` vào nút `50` và nối lại:

```text
Sau xóa 50:

                60
               /  \
             30    80
                  /
                 70
                /
               65
```

Thao tác nối then chốt là:

```text
80.left = 70
70.parent = 80
```

Nếu quên `70.parent = 80`, liên kết đi lên bị sai. Nếu gán `80.left = None`, cả `70` và `65` bị mất.

### Kế nhiệm là con phải trực tiếp

```text
Trước:                   Sau:

      50                      70
     /  \                    /  \
   30    70                30    80
           \
            80
```

Kế nhiệm `70` **chính là `target.right`**. Sau khi sao chép:

```text
target.right = 80
80.parent = target
```

Không sửa `target.left` hay `replacement_parent.left`. Một hàm `replace_link(successor, successor.right)` dùng liên kết `parent.left/right` theo **danh tính nút** sẽ xử lý đúng cả trường hợp trực tiếp lẫn trường hợp kế nhiệm sâu.

## 9. Hai con: chiến lược tiền nhiệm đối xứng

Chọn:

```text
predecessor = maximum(target.left)
```

Nút tiền nhiệm **không có con phải**, nhưng có thể có **con trái**.

```text
Trước xóa 50:

                50
               /  \
             30    80
               \
                40
               /
              35
```

Tiền nhiệm là `40`. Nó có con trái `35`. Để xóa `50` bằng tiền nhiệm:

1. Sao chép `(40, value_of_40)` vào nút đang chứa `50`.
2. Nối `30.right = 35`.
3. Cập nhật `35.parent = 30`.
4. Tính lại metadata từ `30` lên tới gốc.
5. Giảm số nút đúng một.

```text
Sau:

                40
               /  \
             30    80
               \
                35
```

Nếu tiền nhiệm là **con trái trực tiếp** của nút cần xóa, phép thay liên kết sẽ sửa `target.left` và cập nhật con trái còn lại theo cách đối xứng với kế nhiệm trực tiếp.

| Vấn đề | Kế nhiệm | Tiền nhiệm |
| --- | --- | --- |
| Bắt đầu tìm thay thế | `target.right` | `target.left` |
| Di chuyển để lấy cực trị | Đi trái liên tục | Đi phải liên tục |
| Con mà nút thay thế có thể giữ | `successor.right` | `predecessor.left` |
| Nút thay thế có thể là con trực tiếp | Con phải | Con trái |
| Điểm bắt đầu cập nhật metadata | `successor.parent` | `predecessor.parent` |

**Điểm chung:** sau khi sao chép payload, nút **bị tháo vật lý** là nút thay thế, không phải nút `target`. Vì vậy, phải lần theo **tổ tiên của nút bị tháo vật lý** để sửa thông tin phụ.

## 10. Cập nhật kích thước cây con mà không quét lại toàn cây

Xét metadata:

```text
subtree_size(node) =
    1 + subtree_size(node.left) + subtree_size(node.right)

subtree_size(None) = 0
```

Một cách sai nhưng dễ nghĩ tới là **duyệt lại toàn bộ cây `O(n)` sau mỗi lần xóa** để tính mọi kích thước.

Có cách tốt hơn: khi một nút bị tháo, các **cây con nằm trên đường từ vị trí đó lên gốc** mới giảm một nút. Những nhánh khác không đổi.

### Hàm tính lại dọc tổ tiên

Giả mã:

```text
REFRESH_UPWARDS(node):
    while node != null:
        node.subtree_size =
            1 + SIZE(node.left) + SIZE(node.right)
        node = node.parent
```

Nếu cả hai con đều có `subtree_size` đúng, tính kích thước nút cha chỉ tốn **`O(1)`**. Lặp qua tối đa `h` tổ tiên mất **`O(h)` thời gian** và dùng `O(1)` biến phụ.

### Điểm bắt đầu phải là cha của nút bị tháo thật

Ví dụ xóa `50` bằng kế nhiệm ở nhánh sâu:

```text
target = 50
successor = 60
successor.parent = 80
```

Sau khi sao chép cặp `60` vào `target` và tháo đối tượng nút `60`, cần cập nhật từ **`80`**, rồi tới **`target`** (giờ mang khóa `60`), rồi tiếp tục các tổ tiên của target nếu có.

Nếu chỉ tính lại từ **`target.parent`**, ta có thể bỏ qua những nút **giữa successor và target** đang mất một hậu duệ. Chẳng hạn `80.subtree_size` sẽ giữ số cũ và kết quả `rank/select` sai.

Nếu nút thay thế là con trực tiếp, `successor.parent is target` nên bắt đầu ngay từ target.

### Không giảm từng nút hai lần

Với trường hợp hai con dùng sao chép cặp, vẫn chỉ có **một nút thực bị tháo**, nên:

- `tree._size -= 1` một lần;
- các `subtree_size` trên đường cần thiết giảm **một**, bằng cách **tính lại từ hai con**;
- không vừa giảm tay kích thước của target vừa gọi `REFRESH_UPWARDS` theo kiểu khiến cùng một thông tin bị trừ hai lần.

**Ưu điểm của tính lại thay vì trừ tay:** dễ mở rộng sang metadata khác như `subtree_sum` hoặc `height` vì công thức luôn dựa trên các con hiện còn.

## 11. Cài Python: nút có parent và subtree_size

Dưới đây là cài đặt học tập **tự chứa** cho một BST-map khóa nguyên, gồm:

- `key`, `value`, `left`, `right`, `parent`;
- `subtree_size` trên mỗi nút;
- biến `_size` toàn cây;
- thêm mới hoặc cập nhật khóa cũ;
- xóa bằng `successor` hoặc `predecessor`;
- kiểm tra tồn tại, in-order và truy vấn kích thước cây.

Cài đặt này dùng **cách sao chép cặp** để xử lý hai con. Vì không tự cân bằng, độ phức tạp phụ thuộc `h`.

### Cấu trúc dữ liệu

```python
class Node:
    def __init__(self, key, value, parent=None):
        self.key = key
        self.value = value
        self.parent = parent
        self.left = None
        self.right = None
        self.subtree_size = 1


class BSTMap:
    def __init__(self):
        self.root = None
        self._size = 0

    @staticmethod
    def _node_size(node):
        return 0 if node is None else node.subtree_size

    def _refresh_upwards(self, node):
        """Tính lại metadata từ node tới gốc."""
        while node is not None:
            node.subtree_size = (
                1
                + self._node_size(node.left)
                + self._node_size(node.right)
            )
            node = node.parent

    def _replace_link(self, old, child):
        """Thay nút old bởi child; trả cha cũ của old."""
        parent = old.parent

        if parent is None:
            assert self.root is old
            self.root = child
        elif parent.left is old:
            parent.left = child
        else:
            assert parent.right is old
            parent.right = child

        if child is not None:
            child.parent = parent

        return parent

    def _find_node(self, key):
        current = self.root

        while current is not None:
            if key == current.key:
                return current
            current = (
                current.left if key < current.key
                else current.right
            )

        return None
```

**Lưu ý về `_replace_link`:** hàm chỉ đổi liên kết cha/gốc và cập nhật `child.parent`; nó **không tự xóa** `old` và **không tự giảm** `_size`. Phần xóa bên ngoài chịu trách nhiệm làm đúng từng bước.

### Thêm mới và cập nhật giá trị

```python
    def put(self, key, value):
        """Trả True khi thêm nút; False khi cập nhật khóa cũ."""
        if self.root is None:
            self.root = Node(key, value)
            self._size = 1
            return True

        current = self.root

        while True:
            if key == current.key:
                current.value = value
                return False

            if key < current.key:
                if current.left is None:
                    current.left = Node(key, value, parent=current)
                    self._size += 1
                    self._refresh_upwards(current)
                    return True
                current = current.left
            else:
                if current.right is None:
                    current.right = Node(key, value, parent=current)
                    self._size += 1
                    self._refresh_upwards(current)
                    return True
                current = current.right

    def find(self, key):
        node = self._find_node(key)
        if node is None:
            return False, None
        return True, node.value

    def size(self):
        return self._size
```

Hai khối mã phía trên và các khối tiếp theo mô tả **các phần liên tiếp của cùng lớp `BSTMap`**. Khi chạy một tệp Python, hãy đặt tất cả phương thức cùng mức thụt lề trong thân lớp. Các khối tách riêng để giải thích từng nhóm thao tác.

**Bất biến khi chèn:**

- Nút mới có `parent` là nút đang dẫn tới ô trống.
- Cờ `inserted` quyết định có tăng `_size` hay không.
- `subtree_size` được cập nhật từ cha của nút mới tới gốc.
- Cập nhật `value` của khóa có sẵn không đổi số nút hoặc kích thước cây con.

## 12. Cài Python: xóa đầy đủ và làm mới metadata

Phương thức sau nằm trong **cùng lớp `BSTMap`**:

```python
    def delete(self, key, strategy="successor"):
        """Trả True nếu xóa được key; hỗ trợ cả hai chiến lược."""
        if strategy not in ("successor", "predecessor"):
            raise ValueError("strategy phải là successor hoặc predecessor")

        target = self._find_node(key)

        if target is None:
            return False

        # Trường hợp hai con: sao chép cặp từ nút thay thế,
        # sau đó tháo nút thay thế có tối đa một con.
        if target.left is not None and target.right is not None:
            if strategy == "successor":
                removed = target.right
                while removed.left is not None:
                    removed = removed.left
                child = removed.right
            else:
                removed = target.left
                while removed.right is not None:
                    removed = removed.right
                child = removed.left

            target.key = removed.key
            target.value = removed.value

        else:
            # Nút mục tiêu cũng là nút bị tháo vật lý.
            removed = target
            child = (
                target.left if target.left is not None
                else target.right
            )

        # Thay đúng liên kết từ cha/gốc, kể cả vị trí trực tiếp.
        dirty_parent = self._replace_link(removed, child)

        # Tách con trỏ của nút vật lý đã ra khỏi cây.
        removed.parent = None
        removed.left = None
        removed.right = None

        # Chỉ một nút bị tháo; kích thước logic giảm đúng một.
        self._size -= 1

        # Các ancestor của vị trí tháo bị đổi subtree_size.
        # Nếu xóa gốc có tối đa một con, gốc mới tự có size đúng.
        self._refresh_upwards(dirty_parent)
        return True

    def inorder_items(self):
        """Trả [(key, value), ...] theo thứ tự khóa tăng."""
        result = []
        stack = []
        current = self.root

        while stack or current is not None:
            while current is not None:
                stack.append(current)
                current = current.left

            current = stack.pop()
            result.append((current.key, current.value))
            current = current.right

        return result
```

### Vì sao đường cập nhật luôn đi qua những nút cần sửa?

- Xóa **lá/một con không phải gốc**: `dirty_parent` là cha cũ của target; mọi cây con giảm số nút nằm trên đường `dirty_parent → root`.
- Xóa **gốc lá**: không có nút còn sống cần làm mới.
- Xóa **gốc một con**: `child` trở thành gốc, cây con của nó không thay đổi thành viên; `child.subtree_size` đã bằng số nút còn lại.
- Xóa **hai con bằng kế nhiệm**: `removed` nằm trong cây con phải của target, nên đường từ `removed.parent` lên gốc **đi qua target**, bảo đảm cập nhật cả cây con đang mất một nút và gốc.
- Xóa **hai con bằng tiền nhiệm**: lập luận đối xứng với cây con trái của target.

Vì chỉ có một vị trí bị tháo vật lý, cập nhật từ vị trí ấy lên gốc là đủ cho metadata xác định **bằng các con**.

### Một chi tiết cần nhớ về đối tượng được tháo

Sau khi `_replace_link` chạy, ta đặt `removed.parent/left/right` thành `None` để tách nút cũ khỏi các liên kết còn sống. **Không được thực hiện thao tác tách này trước khi xác định và nối `child`**, vì có thể đánh mất gốc cây con cần giữ.

Điều này không bảo đảm đối tượng `removed` được giải phóng tức thì: bên ngoài có thể vẫn giữ tham chiếu, và vòng đời đối tượng còn phụ thuộc runtime.

## 13. Một bộ kiểm tra độc lập cho BST có metadata

Chỉ kiểm tra dãy in-order tăng **chưa đủ** để xác nhận `parent` và `subtree_size` đều đúng. Ta cần kiểm tra cả:

- Gốc có `parent is None`.
- Từng liên kết từ cha tới con và từ con tới cha khớp nhau.
- Không có chu trình hoặc nút được chia sẻ sai.
- Thứ tự khóa được bảo đảm bằng **biên tổ tiên**.
- Kích thước cây con của mỗi nút đúng công thức.
- `_size` bằng số nút thực đi tới được từ gốc.

Mã kiểm thử dưới đây dành cho **khóa nguyên phân biệt**; nó dùng một bộ `seen` để phát hiện nếu một đối tượng nút xuất hiện lại qua đường đi khác.

```python
def validate_tree(tree):
    root = tree.root

    if root is None:
        return tree.size() == 0

    if root.parent is not None:
        return False

    # 1. Kiểm tra thứ tự, parent, hình học cây.
    pending = [(root, None, None, None)]
    seen = set()
    visited = []

    while pending:
        node, low, high, expected_parent = pending.pop()

        if id(node) in seen:
            return False
        seen.add(id(node))
        visited.append(node)

        if node.parent is not expected_parent:
            return False
        if low is not None and node.key <= low:
            return False
        if high is not None and node.key >= high:
            return False

        if node.right is not None:
            pending.append(
                (node.right, node.key, high, node)
            )
        if node.left is not None:
            pending.append(
                (node.left, low, node.key, node)
            )

    # 2. Tính subtree_size từ dưới lên, độc lập với metadata.
    computed = {}

    # visited có thứ tự cha trước con, nên duyệt đảo lại.
    for node in reversed(visited):
        expected = (
            1
            + computed.get(node.left, 0)
            + computed.get(node.right, 0)
        )
        if node.subtree_size != expected:
            return False
        computed[node] = expected

    return (
        len(seen) == tree.size()
        and computed[root] == tree.size()
    )
```

Giả định đầu vào là các nút có các trường đã định nghĩa; hàm trên phát hiện một số dạng cấu trúc sai mà thuật toán duyệt BST thuần có thể bỏ qua. Đây là **công cụ kiểm thử `O(n)` thời gian, `O(n)` bộ nhớ phụ**, không phải việc cần chạy trong mỗi lần `delete` của hệ thống sản xuất.

### Tại sao kiểm tra từ dưới lên?

Nếu muốn xác minh `node.subtree_size`, ta phải biết số nút **thực sự có mặt trong hai cây con**. Do đó, tính các nút con trước rồi tới cha.

Danh sách `visited` thu được theo thứ tự duyệt mà **cha luôn xuất hiện trước các hậu duệ**; duyệt ngược danh sách ấy khiến hậu duệ được tính trước cha. Mỗi đối tượng nút được dùng làm khóa của `computed`; các lớp nút trong bài có identity hash mặc định.

## 14. Thử xóa gốc và kiểm tra các liên kết

Dùng các phương thức đã trình bày trong lớp `BSTMap`:

```python
tree = BSTMap()

for key in (50, 30, 80, 20, 40, 60, 90, 65, 70):
    assert tree.put(key, "v" + str(key))

assert tree.size() == 9
assert tree.root.subtree_size == 9
assert tree.root.parent is None
assert validate_tree(tree)

assert tree.delete(50, strategy="successor")
assert tree.size() == 8
assert tree.root.key == 60
assert tree.root.parent is None
assert tree.root.subtree_size == 8

assert [k for k, _ in tree.inorder_items()] == [
    20, 30, 40, 60, 65, 70, 80, 90
]
assert tree.find(60) == (True, "v60")
assert tree.find(65) == (True, "v65")
assert tree.find(70) == (True, "v70")
assert tree.find(50) == (False, None)
assert validate_tree(tree)
```

Ví dụ này bao gồm **kế nhiệm sâu** là `60`, có **con phải `65`**, và phía dưới `65` còn `70`. Sau khi tháo nút `60` ở vị trí cũ, `80.left` phải trỏ tới `65` và `65.parent` phải trỏ về `80`.

### Đối chiếu liên kết trực tiếp sau xóa

```python
assert tree.root.right.key == 80
assert tree.root.right.left.key == 65
assert tree.root.right.left.parent is tree.root.right

# Cây con phải có 80, 65, 70, 90.
assert tree.root.right.subtree_size == 4
# Cây con trái có 30, 20, 40.
assert tree.root.left.subtree_size == 3
assert tree.root.subtree_size == 8
```

Nếu một hàm xóa chỉ thay khóa và tháo nút mà quên cập nhật `subtree_size`, các kiểm thử bên trên sẽ phát hiện vấn đề dù dãy in-order có thể vẫn đúng.

## 15. Kiểm thử tiền nhiệm, trường hợp trực tiếp và xóa gốc một con

### Xóa bằng tiền nhiệm ở sâu

```python
by_predecessor = BSTMap()

for key in (50, 30, 80, 20, 40, 60, 90, 35):
    by_predecessor.put(key, "v" + str(key))

assert validate_tree(by_predecessor)
assert by_predecessor.delete(50, "predecessor")
assert by_predecessor.root.key == 40
assert [k for k, _ in by_predecessor.inorder_items()] == [
    20, 30, 35, 40, 60, 80, 90
]
assert by_predecessor.root.left.right.key == 35
assert by_predecessor.root.left.right.parent is (
    by_predecessor.root.left
)
assert validate_tree(by_predecessor)
```

Nút tiền nhiệm `40` có con trái `35`; sau khi tháo `40` ở chỗ cũ, phải cập nhật `35.parent` thành `30`.

### Nút kế nhiệm là con phải trực tiếp

```python
direct = BSTMap()

for key in (50, 30, 70, 80):
    direct.put(key, key)

assert direct.delete(50, "successor")
assert direct.root.key == 70
assert direct.root.right.key == 80
assert direct.root.right.parent is direct.root
assert direct.root.subtree_size == 3
assert validate_tree(direct)
```

### Xóa gốc có đúng một con

```python
one_child = BSTMap()

for key in (50, 30, 20, 40):
    one_child.put(key, key)

assert one_child.delete(50)
assert one_child.root.key == 30
assert one_child.root.parent is None
assert one_child.root.subtree_size == 3
assert [k for k, _ in one_child.inorder_items()] == [
    20, 30, 40
]
assert validate_tree(one_child)
```

### Xóa gốc cuối cùng

```python
single = BSTMap()
single.put(7, None)

assert single.delete(7)
assert single.root is None
assert single.size() == 0
assert validate_tree(single)

assert single.delete(7) is False
assert single.size() == 0
```

### Không giảm metadata khi khóa thiếu

```python
missing = BSTMap()

for key in (50, 30, 70):
    missing.put(key, key)

before = missing.inorder_items()
before_size = missing.size()

assert missing.delete(9999) is False
assert missing.inorder_items() == before
assert missing.size() == before_size
assert validate_tree(missing)
```

## 16. Metadata giúp ích gì? Rank và select

Nếu chỉ cần tìm một khóa chính xác, `subtree_size` là metadata dư thừa. Nhưng nó trở nên hữu ích khi muốn trả lời:

- **rank(k):** có bao nhiêu khóa nhỏ hơn `k`?
- **select(i):** khóa đứng thứ `i` trong thứ tự tăng dần (chỉ số bắt đầu từ 0) là khóa nào?

Giả sử:

```text
Khóa đã sắp: 20, 30, 40, 60, 65, 70, 80, 90
             0   1   2   3   4   5   6   7
```

Khi biết kích thước cây con trái của mỗi nút, ta có thể quyết định rẽ trái, dừng tại nút hoặc rẽ phải mà không duyệt toàn cây.

### Rank: đếm số khóa nhỏ hơn x

```python
def rank_less_than(tree, x):
    """Số khóa < x trong BST có subtree_size đúng."""
    current = tree.root
    rank = 0

    while current is not None:
        left_size = (
            0 if current.left is None
            else current.left.subtree_size
        )

        if x <= current.key:
            current = current.left
        else:
            rank += left_size + 1
            current = current.right

    return rank


assert rank_less_than(tree, 60) == 3
assert rank_less_than(tree, 66) == 5
assert rank_less_than(tree, 1000) == 8
```

Khi `x > current.key`, tất cả khóa trong cây con trái và chính nút hiện tại đều nhỏ hơn `x`; ta cộng `left_size + 1` rồi sang phải. Nếu `x <= current.key`, chưa thể tính nút hiện tại, nên sang trái.

### Select: tìm khóa ở vị trí i

```python
def select_key(tree, index):
    """Trả (found, key) tại thứ hạng 0-based."""
    if index < 0 or index >= tree.size():
        return False, None

    current = tree.root
    k = index

    while current is not None:
        left_size = (
            0 if current.left is None
            else current.left.subtree_size
        )

        if k < left_size:
            current = current.left
        elif k == left_size:
            return True, current.key
        else:
            k -= left_size + 1
            current = current.right

    raise AssertionError("Metadata subtree_size không nhất quán")


assert select_key(tree, 0) == (True, 20)
assert select_key(tree, 3) == (True, 60)
assert select_key(tree, 7) == (True, 90)
assert select_key(tree, 8) == (False, None)
```

Với metadata đúng, cả `rank` và `select` chỉ đi một đường, tốn `O(h)` thời gian và `O(1)` bộ nhớ phụ. **Nếu `subtree_size` sai sau xóa**, thuật toán có thể chọn nhánh sai và trả kết quả sai dù tất cả khóa vẫn nằm trong cây.

## 17. Còn height, sum, min/max cache, màu và thông tin cân bằng?

Mỗi loại metadata có **bất biến riêng**, không thể chỉ giảm `subtree_size` rồi xem như mọi thông tin khác đều đúng.

| Metadata | Bất biến tiêu biểu | Khi xóa cần làm gì? |
| --- | --- | --- |
| `subtree_size` | `1 + size(left) + size(right)` | Tính lại dọc đường tổ tiên của nút tháo |
| `height` | `1 + max(height(left), height(right))` | Tính lại chiều cao từ dưới lên |
| `subtree_sum` | `value + sum(left) + sum(right)` với dữ liệu cộng được | Cập nhật đúng payload và tính lại trên các đường bị ảnh hưởng |
| `subtree_min/max` | Cực trị khóa của cây con | Tính lại nếu cực trị cũ bị xóa/đổi |
| `parent` | Liên kết hai chiều, gốc có cha `None` | Cập nhật ngay khi nối lại con/gốc |
| `balance_factor` AVL | Quan hệ chiều cao hai con | Cập nhật và có thể **quay cây** |
| `color` đỏ–đen | Quy tắc màu và số nút đen trên đường | Cần thuật toán **xóa + sửa cân bằng** riêng |

Ví dụ nếu BST là cây hỗ trợ **tổng điểm của mỗi cây con**, các nút có `subtree_sum`, thì sau khi sao chép `(key, value)` từ kế nhiệm, **nút target đã đổi payload**. Với cách cài đặt trong bài, đường tính lại từ cha của nút bị tháo kế nhiệm **đi qua target**, nên có thể tính đúng `subtree_sum` theo công thức từ các con. Nhưng phải **thực sự tính lại** `subtree_sum`, không chỉ `subtree_size`.

### Cập nhật metadata là một phần của thao tác, không phải việc phụ

Xóa có thể đúng với `search(key)` và `inorder()` nhưng sai với `rank` hoặc `select`. Vì vậy, API của một **augmented BST** phải xem cập nhật metadata là **hậu điều kiện bắt buộc**.

Khi dùng cấu trúc tự cân bằng, xóa thường kéo theo cập nhật từ vị trí tháo, rồi các phép quay thay đổi quan hệ cha–con; metadata phải được tính lại ở **đúng những nút bị ảnh hưởng bởi quay**, không thể coi mã BST thường ở đây là thuật toán AVL/đỏ–đen hoàn chỉnh.

## 18. So sánh sao chép payload với transplant nút

Trong cài đặt ở trên, xóa hai con dùng cách **sao chép `(key,value)`** vào nút target, rồi tháo successor/predecessor.

Một hiện thực khác dùng **transplant**: di chuyển **chính đối tượng nút kế nhiệm** đến vị trí target, nối lại cả cây con trái, phải và con trỏ cha.

| Khía cạnh | Sao chép payload | Transplant nút |
| --- | --- | --- |
| Nút ở vị trí target sau xóa | Đối tượng cũ, khóa/value mới | Đối tượng successor/predecessor |
| Nút bị tháo vật lý | Nút thay thế | Nút target và thay đổi liên kết nhiều vị trí |
| Liên kết cần sửa | Chủ yếu liên kết ở vị trí nút thay thế | Liên kết ở cả vị trí target và vị trí nút thay thế |
| Parent pointer | Sửa parent của con thay thế ở chỗ cũ | Sửa nhiều parent pointer hơn |
| `subtree_size` | Cập nhật từ cha của nút thay thế lên gốc | Cần phân tích các đường bị ảnh hưởng bởi transplant |
| Tham chiếu tới nút target | Còn đối tượng, nhưng khóa/value đổi | Không còn là thành viên cây |
| Độ phức tạp của BST thường | `O(h)` | `O(h)` với hiện thực đúng |

**Không có nghĩa transplant đơn giản hơn.** Trong trường hợp successor nằm sâu, cần tháo successor khỏi cha cũ, nối con phải của nó vào chỗ cũ, đưa successor vào vị trí target, gắn lại hai cây con của target, sửa các `parent pointer`, rồi cập nhật metadata theo vị trí mới. Nếu thiếu bất kỳ bước nào, cây có thể hỏng.

### Cần nhất quán hợp đồng về danh tính nút

Nếu người gọi được phép giữ tham chiếu `Node` và kỳ vọng “node này mãi đại diện cùng một key”, chiến lược sao chép payload có thể không phù hợp. Khi đó, thiết kế thư viện cần xác định rõ vòng đời và chính sách iterator/handle trước khi chọn thuật toán xóa.

Trong bài học, `Node` là chi tiết nội bộ; giao diện công khai nên làm việc bằng **khóa**, **giá trị** và **kết quả tìm/xóa**, không cho người dùng tự chỉnh liên kết hay metadata.

## 19. Độ phức tạp thời gian và bộ nhớ

Gọi `n` là số nút và `h` là số nút trên đường dài nhất từ gốc tới một lá. Giả định phép so sánh khóa và cập nhật một trường có chi phí hằng số.

| Công việc | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| Tìm nút theo khóa | `O(h)` | `O(1)` bản lặp |
| Tìm successor/predecessor khi nút có hai con | `O(h)` | `O(1)` |
| Thay liên kết cha/gốc và sửa `child.parent` | `O(1)` | `O(1)` |
| Tính lại `subtree_size` dọc tổ tiên | `O(h)` | `O(1)` |
| **Xóa hoàn chỉnh + metadata trong bài** | **`O(h)`** | **`O(1)`** |
| Duyệt in-order, tạo list cặp | `O(n)` | `O(n)` cho list kết quả |
| Kiểm tra độc lập toàn bộ metadata | `O(n)` | `O(n)` cho tập đã gặp và số đếm |
| Rank/select khi metadata đúng | `O(h)` | `O(1)` |

Tổng `O(h) + O(h) + O(h) = O(h)` vì chỉ có một số hằng số đường từ gốc xuống rồi đi từ vị trí tháo lên.

### Điều kiện cân bằng quan trọng

- **BST cân đối:** `h = O(log n)`; các thao tác đạt `O(log n)`.
- **BST lệch thành chuỗi:** `h = Θ(n)`; thao tác có thể mất `Θ(n)`.
- **AVL/đỏ–đen:** duy trì `h = O(log n)` nhưng cần quy tắc xóa và tái cân bằng riêng.

`parent pointer` và `subtree_size` **không tự làm cây cân bằng**. Chúng chỉ giúp thực hiện những chức năng cụ thể nhanh và kiểm soát tính nhất quán của cấu trúc.

## 20. Những lỗi thường gặp

1. **Chỉ sửa `parent.left/right` nhưng không sửa `child.parent`.** Tìm xuống đúng, đi lên sai.
2. **Quên trường hợp `parent is None`.** Xóa gốc làm `root` trỏ tới nút cũ hoặc lỗi truy cập.
3. **Sau khi thay gốc quên đặt `root.parent = None`.** Có thể xuất hiện đường đi ngược về nút đã tháo.
4. **Nhầm cha của target với cha của successor.** Cập nhật `subtree_size` từ sai vị trí và bỏ qua một nhánh.
5. **Với successor trực tiếp, luôn sửa liên kết trái của cha.** Liên kết đúng là `target.right`.
6. **Với predecessor trực tiếp, luôn sửa liên kết phải của cha.** Liên kết đúng là `target.left`.
7. **Gỡ successor bằng `None` khi nó có con phải.** Làm mất cả cây con vẫn hợp lệ.
8. **Gỡ predecessor bằng `None` khi nó có con trái.** Làm mất dữ liệu.
9. **Đổi khóa ở target nhưng quên đổi value.** Cặp ánh xạ bị ghép sai.
10. **Sao chép cả `left/right/parent` từ nút thay thế vào target mà không phân tích lại.** Dễ tạo chu trình, mất nhánh hoặc sai liên kết.
11. **Giảm `size` hai lần.** Xóa logic chỉ bỏ đúng một khóa, kể cả dùng kế nhiệm.
12. **Không giảm `size` hoặc `subtree_size` khi xóa lá.** Rank/select và báo cáo tổng số sai.
13. **Quên làm mới metadata tại những tổ tiên nằm giữa successor và target.** Các truy vấn theo thứ hạng sai dù in-order đúng.
14. **Làm mới metadata từ trên xuống khi con chưa đúng.** Nút cha cần được tính sau các con.
15. **Cho rằng cập nhật `subtree_size` là đủ cho AVL hoặc đỏ–đen.** Chưa bảo đảm cân bằng/màu sắc.
16. **Dùng bộ so sánh khác lúc tìm và lúc xóa.** Có thể tháo nhầm nút hoặc phá thứ tự.
17. **Xóa khóa không tồn tại mà vẫn đổi metadata.** Trạng thái cây thay đổi dù thao tác thất bại.
18. **Giữ tham chiếu Node bên ngoài rồi giả định key không đổi sau delete.** Chiến lược sao chép payload có thể thay key/value của nút còn sống.
19. **Kiểm thử chỉ so dãy khóa in-order.** Không phát hiện parent sai hoặc `subtree_size` sai.
20. **Sửa cấu trúc từ nhiều luồng không đồng bộ.** Trạng thái trung gian có thể bị đọc; cần một cơ chế đồng bộ hoặc cấu trúc concurrent với hợp đồng rõ ràng.

## 21. Luyện tập

**Bài 1.** Với BST có gốc `50`, con trái `30` và con phải `80`, nếu xóa `30` là nút lá, phải cập nhật các trường nào để giữ `parent` và `subtree_size` đúng?

**Bài 2.** Một nút `70` có một con trái `60`; `70` là con phải của `50`. Sau xóa `70`, hãy chỉ ra các gán liên kết cần thiết. Nếu `60` có hai con riêng, các nút ấy có bị mất không?

**Bài 3.** Xóa gốc `50` có đúng một con phải `80`. Hãy cho biết `root` và `root.parent` sau xóa, và vì sao `80.subtree_size` không nhất thiết phải tính lại.

**Bài 4.** Một nút cần xóa có hai con, successor nằm sâu trong cây con phải. Sau khi sao chép cặp và tháo successor, nên cập nhật metadata từ **target.parent** hay **successor.parent**? Giải thích.

**Bài 5.** Vì sao successor có thể có con phải nhưng không có con trái? Khi tháo nó, cần nối nút nào lên vị trí cũ?

**Bài 6.** Trong một tree map, target là `(50, "An")` và successor là `(60, "Bình")`. Nếu chỉ chép khóa `60` mà giữ `"An"`, bất biến nào bị phá?

**Bài 7.** Cho cây:

```text
          50
         /  \
       30    80
             /
            60
              \
               65
```

Xóa `50` bằng kế nhiệm. Những liên kết `left/right/parent` nào đổi, và các `subtree_size` nào cần tính lại?

**Bài 8.** Vì sao một phép xóa đúng về dãy in-order có thể vẫn làm `rank_less_than` hoặc `select_key` trả sai?

**Bài 9.** Thiết kế kiểm tra độc lập để xác nhận `root.parent is None`, mọi con trỏ parent đều trỏ về đúng cha, không có chu trình và số nút bằng `_size`.

**Bài 10.** Một BST giữ metadata `height` và `subtree_sum` ngoài `subtree_size`. Sau khi xóa, những thông tin nào cần tính lại? Mã BST thường có đủ để giữ bất biến AVL không?

**Bài 11.** Phân biệt chiến lược **sao chép payload** và **transplant nút** đối với tham chiếu bên ngoài đến `Node`.

**Bài 12.** Phân tích thời gian và bộ nhớ phụ để tìm target, tìm successor, nối lại liên kết và cập nhật metadata trên BST chiều cao `h`.

**Bài 13.** Với cây đã chèn `[50,30,80,20,40,60,90,65,70]`, hãy xóa `50` bằng successor và dự đoán `root.subtree_size`, `root.right.subtree_size` và `root.left.subtree_size`.

**Bài 14.** Viết kiểm thử cho việc xóa khóa không tồn tại, xóa gốc một con, xóa target hai con bằng predecessor và successor; sau mỗi lần, xác nhận cả khóa, ánh xạ value, parent pointer và `subtree_size`.

<details>
<summary>Đáp án và gợi ý</summary>

1. Gán `50.left = None`, giảm `_size` một và tính lại `50.subtree_size` (trong cây ba nút, từ 3 còn 2). Nếu tách đối tượng `30`, có thể đặt `30.parent = None`; gốc `50.parent` vẫn là `None`.
2. `50.right = 60` và `60.parent = 50`. Cây con của `60` được giữ nguyên; chỉ thay một liên kết dẫn tới gốc cây con, không xóa các hậu duệ.
3. `root = 80` và `root.parent = None`. Cây con `80` vẫn chứa chính xác những nút nó đã chứa trước khi xóa `50`, nên `80.subtree_size` đã đúng.
4. Bắt đầu từ **successor.parent** vì nút bị tháo vật lý ở vị trí successor; đường lên gốc sẽ đi qua target và các tổ tiên của target. Nếu chỉ bắt đầu ở `target.parent`, metadata ở các nút giữa successor và target có thể sai.
5. Nếu có con trái, successor chưa phải nhỏ nhất trong cây con phải. Nó có thể có con phải; khi tháo successor phải nối `successor.parent` tới `successor.right` và cập nhật parent của con đó.
6. Ánh xạ **khóa → giá trị** sai: `60` bị gắn với giá trị `"An"` thay vì `"Bình"`. Phải chép cả `key` và `value`.
7. Successor là `60`, có con phải `65`. Sao chép cặp từ `60` sang vị trí `50`, nối `80.left = 65`, `65.parent = 80`; cập nhật `subtree_size` từ `80` lên gốc (nay mang khóa `60`).
8. `rank/select` dựa trên số nút trong từng cây con để rẽ nhánh. Nếu liên kết được sửa mà `subtree_size` vẫn là số cũ, thuật toán có thể đi nhánh sai dù in-order tăng.
9. Duyệt từ gốc với `expected_parent`, dùng `seen` để phát hiện đối tượng lặp; kiểm tra thứ tự bằng biên, đếm nút, sau đó tính `subtree_size` từ dưới lên độc lập. Mã `validate_tree` trong bài là một cách.
10. `height` cần tính lại bằng `1 + max(height(left),height(right))`; `subtree_sum` cần tính lại theo payload và các con hiện tại. Với AVL còn phải kiểm soát cân bằng và quay, nên mã BST thường **chưa đủ**.
11. Sao chép payload giữ đối tượng target nhưng đổi key/value; transplant đưa đối tượng successor/predecessor về vị trí target và thay nhiều liên kết. Cần xác định rõ hợp đồng handle/iterator khi cho người gọi giữ tham chiếu Node.
12. Tổng `O(h)` thời gian do một số đường đi dài tối đa `h`, `O(1)` bộ nhớ phụ khi dùng vòng lặp và chỉ giữ vài tham chiếu; BST lệch có thể có `h=O(n)`.
13. Sau xóa, cây có 8 nút, gốc (mang khóa `60`) có `subtree_size=8`, cây con trái `30` có `subtree_size=3`, cây con phải `80` có `subtree_size=4`.
14. Có thể xây cây bằng `put`, dùng `delete` cho hai chiến lược rồi gọi `validate_tree`; đối chiếu `inorder_items` với `sorted(reference.items())` từ một `dict` tham chiếu, đồng thời kiểm tra `size()` và các giá trị trả về của `find`.

</details>

## Ghi nhớ

**Xóa BST đúng không chỉ là loại một khóa.** Phải giữ đồng thời **bất biến thứ tự, liên kết cha–con hai chiều, con trỏ gốc, số nút toàn cây và mọi metadata của cây con**. Với nút 0–1 con, nối cha/gốc tới con còn sống và sửa `child.parent`; với nút hai con dùng **sao chép cặp từ kế nhiệm/tiền nhiệm**, nút bị tháo vật lý là nút thay thế, nên bắt đầu tính lại metadata từ **cha của nút bị tháo** lên gốc. Chỉ giảm số nút **một lần**, kiểm thử **cả cấu trúc lẫn thông tin phụ**, và đừng nhầm BST giữ thứ tự với AVL/đỏ–đen có yêu cầu cân bằng riêng. Khi được hiện thực đúng, thao tác xóa và cập nhật `subtree_size` cùng tốn **`O(h)` thời gian, `O(1)` bộ nhớ phụ** ở bản lặp.
