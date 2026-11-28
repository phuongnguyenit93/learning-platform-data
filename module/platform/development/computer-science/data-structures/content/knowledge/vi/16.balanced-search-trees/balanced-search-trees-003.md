# Cây AVL: chiều cao và hệ số cân bằng

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **cây AVL** là cây tìm kiếm nhị phân tự cân bằng và phân biệt **bất biến thứ tự BST** với **bất biến chiều cao AVL**.
- Tính **chiều cao** và **hệ số cân bằng (balance factor)** tại từng nút theo một quy ước rõ ràng.
- Nhận biết nút mất cân bằng khi thêm/xóa, xác định các hình dạng **LL, RR, LR, RL** và cách chọn quay trái, quay phải hoặc quay kép.
- Lý giải tại sao ràng buộc cục bộ `|balance| ≤ 1` ở **mọi nút** bảo đảm chiều cao `O(log n)`.
- Cài đặt **chèn và tìm kiếm** trong AVL, cập nhật metadata chiều cao và viết hàm kiểm tra bất biến bằng Python.
- Phân tích **thời gian, bộ nhớ, trường hợp biên và chi phí bảo trì** khi sử dụng AVL trong một hệ thống dữ liệu.

## 1. Vì sao cần AVL nếu đã có cây tìm kiếm nhị phân?

Giả sử hệ thống học tập quản lý bài học bằng khóa số nguyên `lesson_id` và cần thường xuyên **tìm theo khóa**, **thêm bài** hoặc **duyệt bài theo thứ tự khóa**. Trong cây tìm kiếm nhị phân (*Binary Search Tree — BST*) với các khóa duy nhất, mỗi nút thỏa:

1. Mọi khóa ở **cây con trái** nhỏ hơn khóa của nút.
2. Mọi khóa ở **cây con phải** lớn hơn khóa của nút.
3. Hai điều kiện áp dụng cho **mọi hậu duệ**, không chỉ hai con trực tiếp.

Một BST thường **không bảo đảm** cây thấp. Nếu chèn `10, 20, 30, 40, 50` theo thứ tự tăng dần mà không tái cân bằng:

```text
BST thường sau các lần chèn:

10
  \
   20
     \
      30
        \
         40
           \
            50
```

Đường tìm tới khóa `50` phải đi qua cả năm nút. Với `n` khóa tăng dần, chiều cao có thể bằng `n`; tìm/chèn/xóa trong trường hợp xấu nhất có thể tốn **O(n)**.

**AVL** (đặt theo tên Adelson-Velsky và Landis) bổ sung một bất biến về **chênh lệch chiều cao cây con ở mỗi nút**. Nhờ đó, cây không thể kéo dài thành một nhánh tùy ý. Các thao tác tìm, thêm, xóa trên AVL cài đặt đúng có thời gian **O(log n) trong trường hợp xấu nhất**.

> Cây AVL vẫn là **BST**: thứ tự khóa là điều kiện để tìm đúng; cân bằng chiều cao là điều kiện bổ sung để tìm nhanh trên cả đầu vào bất lợi.

## 2. Thống nhất định nghĩa chiều cao

**Chiều cao của một nút** là độ dài đường dài nhất đi xuống một nút lá trong cây con gốc tại nút ấy. Có hai quy ước thường gặp:

| Quy ước | Cây rỗng | Nút lá | Ví dụ đường 3 nút |
| --- | ---: | ---: | ---: |
| Đếm **số nút** trên đường dài nhất | 0 | 1 | 3 |
| Đếm **số cạnh** trên đường dài nhất | −1 | 0 | 2 |

Bài này dùng quy ước **đếm số nút**:

\[
h(\varnothing)=0,\qquad
h(v)=1+\max(h(v.left),h(v.right)).
\]

Theo đó, một nút lá không có con có `h=1`. Một nút có cây con trái cao 3 và phải cao 2 có `h=4`.

```text
                 40 (h=4)
                 /       \
          20 (h=3)     60 (h=2)
           /     \      /     \
     10 (h=2) 30(1) 50(1)   70(1)
         /
        5 (h=1)
```

Đọc từ **dưới lên**:

- Các lá `5`, `30`, `50`, `70` có chiều cao 1.
- Nút `10` có chiều cao `1 + max(1, 0) = 2`.
- Nút `20` có chiều cao `1 + max(2, 1) = 3`.
- Nút `60` có chiều cao `1 + max(1, 1) = 2`.
- Gốc `40` có chiều cao `1 + max(3, 2) = 4`.

**Chiều cao không phải độ sâu.** **Độ sâu (depth)** thường là số cạnh từ gốc tới nút; gốc có độ sâu 0. Chiều cao lại đo **từ nút đi xuống**. Hai đại lượng có hướng đo khác nhau và được dùng vào các câu hỏi khác nhau.

### 2.1. Chiều cao thực và metadata được lưu

Khi cài AVL, mỗi nút thường lưu trường `height` để không phải đi duyệt cả cây con mỗi lần cần so sánh hai chiều cao.

```python
class Node:
    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.left = None
        self.right = None
        self.height = 1


def height(node):
    return 0 if node is None else node.height


def update_height(node):
    node.height = 1 + max(height(node.left), height(node.right))
```

Với cách cài này, truy cập `node.height` là O(1), **nhưng chỉ đáng tin nếu metadata được cập nhật đúng sau mọi thay đổi liên kết**. Trường `height` sai khiến thuật toán quyết định quay sai ngay cả khi các khóa vẫn thỏa BST.

## 3. Hệ số cân bằng: đo độ lệch giữa hai nhánh

**Hệ số cân bằng** của nút `v` được định nghĩa trong bài này:

\[
\operatorname{BF}(v)=h(v.left)-h(v.right).
\]

Với quy ước đó:

- `BF(v) > 0`: cây con **trái** cao hơn.
- `BF(v) < 0`: cây con **phải** cao hơn.
- `BF(v) = 0`: hai cây con cao bằng nhau.

Một AVL hợp lệ phải thỏa **tại mọi nút**:

\[
\boxed{|\operatorname{BF}(v)|\le 1}
\qquad\Longleftrightarrow\qquad
\operatorname{BF}(v)\in\{-1,0,1\}.
\]

| `h(left)` | `h(right)` | `BF` | Đánh giá tại nút |
| ---: | ---: | ---: | --- |
| 0 | 0 | 0 | Lá, hợp lệ |
| 2 | 2 | 0 | Cân bằng tại nút |
| 3 | 2 | +1 | Hợp lệ, nặng trái nhẹ |
| 2 | 3 | −1 | Hợp lệ, nặng phải nhẹ |
| 4 | 2 | +2 | **Vi phạm AVL** |
| 1 | 3 | −2 | **Vi phạm AVL** |

Một số tài liệu định nghĩa `BF` theo chiều ngược `h(right)-h(left)`. Khi đó **dấu sẽ đổi**, nhưng điều kiện tuyệt đối `|BF|≤1` vẫn tương đương. Hãy **không trộn hai quy ước** khi đọc mã hoặc áp dụng bảng chọn phép quay.

### 3.1. Phải kiểm tra mọi nút, không chỉ gốc

```text
                 50
                /  \
              20    80
             /        \
            10         90
           /             \
          5              100
         /
        2
```

Chiều cao hai cây con của gốc `50` ở ví dụ này có thể khác nhau 1 hoặc gần nhau tùy các nhánh, nhưng một **nút bên trong như `20`** có thể bị lệch quá mức. Vì thế không thể chỉ kiểm tra `BF(root)` để tuyên bố toàn cây là AVL.

Quy tắc AVL yêu cầu:

\[
\forall v\text{ là nút thật trong cây},\quad |\operatorname{BF}(v)|\le 1.
\]

Một cây có `BF(root)=0` vẫn có thể **không phải AVL** nếu bất kỳ nút con nào có `|BF|>1`.

### 3.2. Chiều cao và số nút không cần bằng nhau giữa hai nhánh

AVL chỉ ràng buộc **chiều cao**. Hai cây con có cùng chiều cao nhưng số nút rất khác nhau vẫn có thể hợp lệ. Ví dụ, một cây con cao 3 có thể có 4 nút theo cấu trúc AVL tối thiểu; một cây cao 3 hoàn hảo có 7 nút. Chênh lệch **số lượng** không phải tiêu chí `BF`.

Đừng nhầm AVL với cây cân bằng theo **kích thước cây con** (*weight-balanced tree*), vốn có quy tắc khác.

## 4. Vì sao bất biến cục bộ bảo đảm chiều cao O(log n)?

Đây là ý tưởng quan trọng nhất: một cây có thể bị lệch **một mức** ở mỗi nút nhưng vẫn không thể cao tuyến tính theo số nút.

Gọi `N(h)` là **số nút tối thiểu** của một cây AVL có chiều cao `h` theo quy ước đếm nút.

- `N(0)=0`: cây rỗng.
- `N(1)=1`: một nút lá.
- Để một AVL cao `h≥2` có **ít nút nhất**, một con có chiều cao `h−1`, con còn lại cao `h−2`. Nếu con thấp hơn nữa sẽ vi phạm `|BF|≤1`.

Do đó:

\[
N(h)=1+N(h-1)+N(h-2),\qquad h\ge2.
\]

| `h` | `N(h)` nhỏ nhất | Một cách tính |
| ---: | ---: | --- |
| 0 | 0 | Cây rỗng |
| 1 | 1 | Một nút |
| 2 | 2 | `1+N(1)+N(0)` |
| 3 | 4 | `1+2+1` |
| 4 | 7 | `1+4+2` |
| 5 | 12 | `1+7+4` |
| 6 | 20 | `1+12+7` |
| 7 | 33 | `1+20+12` |

Dãy tăng theo dạng Fibonacci, nghĩa là **số nút tối thiểu tăng theo hàm mũ của chiều cao**. Cụ thể, đặt `F_0=0`, `F_1=1` thì:

\[
N(h)=F_{h+2}-1.
\]

Vì `F_m` tăng theo cấp số mũ với cơ số lớn hơn 1, để có một cây AVL cao `h` ta phải có số nút tăng theo mũ của `h`. Đảo chiều lập luận:

\[
n\ge N(h)\quad\Longrightarrow\quad h=O(\log n)
\quad\text{(với }n\ge2\text{)}.
\]

**Không phải** chỉ vì BST có thể chứa tối đa `2^h-1` nút mà suy ra h=O(log n). Giới hạn tối đa chỉ cung cấp **cận dưới** cho chiều cao cần để chứa `n` nút; giới hạn **số nút tối thiểu do AVL bắt buộc** mới cung cấp **cận trên**.

### 4.1. Ý nghĩa đối với các phép toán

Tìm khóa trong BST đi xuống theo một đường nên chi phí là **O(h)**. AVL bảo đảm `h=O(log n)`, vì thế:

- Tìm, tìm min/max, predecessor/successor: **O(log n)** trong trường hợp xấu nhất.
- Xác định vị trí thêm hoặc nút cần xóa: **O(log n)**.
- Duyệt toàn bộ theo thứ tự: vẫn **O(n)** vì cần xuất `n` phần tử.
- Truy vấn khoảng xuất `k` khóa: có thể đạt **O(log n + k)** với thuật toán duyệt khoảng phù hợp.

Đây là bảo đảm về **số bước tăng theo quy mô**, không phải cam kết mọi cấu hình AVL đều chạy nhanh hơn bảng băm, mảng đã sắp xếp hoặc cây Đỏ–Đen trong mọi trường hợp thực tế.

## 5. Thêm khóa có thể làm thay đổi BF như thế nào?

Chèn vào BST chỉ thêm một nút tại **vị trí lá** theo thứ tự khóa. Tác động lên chiều cao chỉ có thể lan tới các **tổ tiên trên đường từ lá mới tới gốc**.

```text
Trước khi chèn 10:               Sau khi chèn 10:

        30 (h=2)                         30 (h=3, BF=+2)
       /                                 /
     20 (h=1)                         20 (h=2, BF=+1)
                                      /
                                    10 (h=1, BF=0)
```

Sau chèn:

1. Nút mới `10` là lá, `height=1`, `BF=0`.
2. Nút `20` có trái cao 1, phải 0 → `height=2`, `BF=+1`.
3. Nút `30` có trái cao 2, phải 0 → `height=3`, `BF=+2`.
4. `30` là một nút **vi phạm AVL**, dù thứ tự `10 < 20 < 30` vẫn đúng.

Thuật toán AVL đi ngược lên đường tìm, **cập nhật chiều cao**, tính lại `BF` rồi quay ở vị trí phù hợp.

### 5.1. Các chiều cao chỉ thay đổi khi thật sự cần

Nếu một lần chèn không làm chiều cao cây con đổi, các tổ tiên cao hơn cũng có thể không cần đổi chiều cao. Tuy nhiên, cần thiết kế thuật toán cập nhật **đúng metadata theo đường bị ảnh hưởng**, không tự ý bỏ qua kiểm tra nếu chưa chứng minh được điều kiện dừng.

Trong triển khai đệ quy đơn giản, sau khi chèn vào cây con, ta luôn gọi `update_height` và `rebalance` trên đường trả về. Chiều dài đường này bị chặn bởi O(log n) đối với cây AVL hợp lệ ban đầu.

## 6. Khôi phục bất biến bằng phép quay

Một phép **quay trái** hoặc **quay phải** đổi một số liên kết nhưng **không thay thứ tự inorder** của các khóa. Ví dụ quay phải:

```text
Trước quay phải tại y:              Sau:

           y                              x
          / \                            / \
         x   C                          A   y
        / \                                / \
       A   B                              B   C
```

Giữ đúng khoảng khóa:

\[
A < x < B < y < C.
\]

Trước và sau quay, inorder đều là `in(A), x, in(B), y, in(C)`. Vì vậy phép quay hợp lệ **bảo toàn bất biến BST**; còn việc giảm chiều cao ở điểm thích hợp phụ thuộc loại mất cân bằng.

### 6.1. Bốn hình dạng sau khi chèn

| Trường hợp | Hình dạng tăng chiều cao | Các phép quay |
| --- | --- | --- |
| **LL** | Trái của con trái | Quay phải nút mất cân bằng |
| **RR** | Phải của con phải | Quay trái nút mất cân bằng |
| **LR** | Phải của con trái | Quay trái ở con trái, rồi quay phải tại nút |
| **RL** | Trái của con phải | Quay phải ở con phải, rồi quay trái tại nút |

**LL — Left–Left**, chèn `30, 20, 10`:

```text
        30                  20
       /                   /  \
     20       --R-->     10   30
    /
   10
```

**RR — Right–Right**, chèn `10, 20, 30`:

```text
10                         20
  \                        /  \
   20        --L-->       10   30
     \
      30
```

**LR — Left–Right**, chèn `30, 10, 20`:

```text
      30               30                20
     /                /                 /  \
   10        --L-->  20        --R-->   10   30
     \              /
      20           10
```

**RL — Right–Left**, chèn `10, 30, 20`:

```text
10                 10                       20
  \                  \                      /  \
   30       --R-->    20         --L-->    10   30
  /                    \
 20                     30
```

Trong ký hiệu trên, `L` là quay trái, `R` là quay phải. Phép quay **đơn** tốn O(1) thao tác đổi liên kết, quay **kép** gồm hai phép quay đơn nên vẫn O(1) thao tác cục bộ.

### 6.2. Quy tắc tổng quát theo BF của nút và nút con

Với quy ước `BF = h(left) − h(right)`:

| Tại nút `v` | BF của con nặng | Cách xử lý |
| --- | --- | --- |
| `BF(v) > 1`, nặng trái | `BF(v.left) ≥ 0` | Quay **phải** tại `v` |
| `BF(v) > 1`, nặng trái | `BF(v.left) < 0` | Quay **trái** tại `v.left`, rồi **phải** tại `v` |
| `BF(v) < −1`, nặng phải | `BF(v.right) ≤ 0` | Quay **trái** tại `v` |
| `BF(v) < −1`, nặng phải | `BF(v.right) > 0` | Quay **phải** tại `v.right`, rồi **trái** tại `v` |

Trong **chèn AVL**, nút con nặng khi xuất hiện vi phạm do một lần chèn thường có BF cùng hướng hoặc ngược hướng khác 0. **Trong xóa AVL**, BF của con nặng **có thể bằng 0**, nên dấu `≥` và `≤` trong bảng rất quan trọng. Không nên dùng điều kiện dựa hoàn toàn vào **khóa mới chèn** để tái cân bằng sau xóa.

### 6.3. Thứ tự tính lại chiều cao sau quay

Quay trái tại `x` đưa `y=x.right` lên:

```text
       x                        y
      / \                      / \
     A   y       -->          x   C
        / \                  / \
       B   C                A   B
```

Sau đổi liên kết, **`x` đi xuống**, `y` đi lên. Hãy:

1. Tính lại `height(x)` từ các con `A`, `B`.
2. Sau đó tính `height(y)` từ con mới `x` và `C`.

Quay phải thực hiện đối xứng: tính lại chiều cao **nút đi xuống** trước rồi tới **nút đi lên**. Nếu tính ngược thứ tự, nút cha có thể đọc metadata cũ của nút con và khiến BF sau quay bị sai.

## 7. Ví dụ Python tự chứa: AVL Map hỗ trợ chèn và tìm

Ví dụ sau dùng khóa số nguyên phân biệt và lưu giá trị bất kỳ. Khi gặp khóa đã có, phương thức chèn **thay giá trị** thay vì thêm một nút trùng. Mỗi lời gọi `insert` trả về **gốc mới của cây con** vì phép quay có thể đổi gốc.

```python
class AVLNode:
    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.left = None
        self.right = None
        self.height = 1


def height(node):
    return 0 if node is None else node.height


def balance_factor(node):
    if node is None:
        return 0
    return height(node.left) - height(node.right)


def update_height(node):
    node.height = 1 + max(height(node.left), height(node.right))


def rotate_left(x):
    """Điều kiện: x.right không rỗng."""
    y = x.right
    middle = y.left

    y.left = x
    x.right = middle

    update_height(x)  # x đi xuống, phải tính trước.
    update_height(y)
    return y


def rotate_right(y):
    """Điều kiện: y.left không rỗng."""
    x = y.left
    middle = x.right

    x.right = y
    y.left = middle

    update_height(y)  # y đi xuống, phải tính trước.
    update_height(x)
    return x


def rebalance(node):
    """Giữ BST và sửa BF sau khi một cây con thay đổi."""
    update_height(node)
    bf = balance_factor(node)

    if bf > 1:
        if balance_factor(node.left) < 0:  # LR
            node.left = rotate_left(node.left)
        return rotate_right(node)           # LL hoặc sau LR

    if bf < -1:
        if balance_factor(node.right) > 0:  # RL
            node.right = rotate_right(node.right)
        return rotate_left(node)            # RR hoặc sau RL

    return node


def insert(node, key, value):
    if node is None:
        return AVLNode(key, value)

    if key < node.key:
        node.left = insert(node.left, key, value)
    elif key > node.key:
        node.right = insert(node.right, key, value)
    else:
        node.value = value  # Một khóa, một bản ghi.
        return node

    return rebalance(node)


def search(node, key):
    current = node
    while current is not None:
        if key == current.key:
            return current.value
        current = current.left if key < current.key else current.right
    return None


def inorder(node):
    if node is not None:
        yield from inorder(node.left)
        yield node.key
        yield from inorder(node.right)


def validate(node, lower=None, upper=None):
    """Tính lại chiều cao và kiểm tra BST, AVL, metadata.

    Trả (chiều cao thật, số nút).
    """
    if node is None:
        return 0, 0

    if lower is not None:
        assert lower < node.key, "Vi phạm thứ tự BST (cận dưới)"
    if upper is not None:
        assert node.key < upper, "Vi phạm thứ tự BST (cận trên)"

    left_h, left_n = validate(node.left, lower, node.key)
    right_h, right_n = validate(node.right, node.key, upper)

    real_height = 1 + max(left_h, right_h)
    assert node.height == real_height, "Metadata height bị sai"
    assert abs(left_h - right_h) <= 1, "Vi phạm cân bằng AVL"
    return real_height, 1 + left_n + right_n


# 1. Kiểm tra bốn tình huống quay.
cases = [
    [30, 20, 10],  # LL
    [10, 20, 30],  # RR
    [30, 10, 20],  # LR
    [10, 30, 20],  # RL
]

for keys in cases:
    root = None
    for key in keys:
        root = insert(root, key, f"lesson-{key}")
        validate(root)

    assert root.key == 20
    assert root.height == 2
    assert balance_factor(root) == 0
    assert list(inorder(root)) == [10, 20, 30]
    assert search(root, 10) == "lesson-10"

# 2. Kiểm tra dãy dài hơn, cập nhật khóa cũ và tìm khóa thiếu.
root = None
keys = [50, 20, 80, 10, 30, 70, 90, 5, 15, 25, 35, 60, 75]
for key in keys:
    root = insert(root, key, f"lesson-{key}")
    validate(root)

assert list(inorder(root)) == sorted(keys)
assert validate(root)[1] == len(keys)
assert search(root, 25) == "lesson-25"
assert search(root, 999) is None

root = insert(root, 25, "updated-25")
assert search(root, 25) == "updated-25"
assert validate(root)[1] == len(keys)  # Không có nút trùng.
```

### 7.1. Vì sao cài đặt này không cần trường `parent`?

Trong `insert(node, ...)`, lời gọi đệ quy chèn vào cây con rồi **gán lại con trỏ của cha**:

```python
node.left = insert(node.left, key, value)
# hoặc:
node.right = insert(node.right, key, value)
```

Khi phép quay đổi gốc của cây con, giá trị trả về từ `rebalance` được gán đúng vào `node.left`, `node.right` hoặc biến `root` của bên ngoài:

```python
root = insert(root, new_key, new_value)
```

Nhờ vậy không cần lưu `parent` tại mỗi nút trong phiên bản này. Một cài đặt **lặp** có trường `parent` cũng hợp lệ nhưng phải duy trì thêm những tham chiếu ngược sau mỗi phép quay.

### 7.2. Bộ kiểm chứng đang đo điều gì?

Hàm `validate` được thiết kế có chủ ý để **không tin** trường `height` khi kiểm chứng:

1. Nó tính lại chiều cao thật của hai cây con từ dưới lên.
2. Nó so sánh kết quả đó với `node.height` đã lưu.
3. Nó xác minh `|left_h-right_h|≤1` tại **mọi nút**.
4. Nó mang `lower` và `upper` từ tổ tiên để kiểm tra **toàn bộ quy tắc BST**.
5. Nó trả số nút, giúp kiểm tra thêm khóa trùng có làm tăng kích thước cây hay không.

**Không gọi `validate` sau mỗi lần chèn trong ứng dụng hiệu năng cao.** Hàm này duyệt toàn cây **O(n)** để thử nghiệm; phần chèn AVL thường chỉ làm việc trên đường đi và vài nút quay. Các lệnh `validate(root)` sau mỗi lần chèn trong ví dụ nhằm thể hiện **đúng bất biến theo từng bước**, không phải một phần của thuật toán chèn chuẩn.

### 7.3. Chi phí của từng thao tác trong mã

| Thao tác | Thời gian | Bộ nhớ phụ | Ghi chú |
| --- | --- | --- | --- |
| `height(node)`, `balance_factor(node)` | **O(1)** | **O(1)** | Tin metadata `height` được duy trì đúng |
| `update_height(node)` | **O(1)** | **O(1)** | Dùng chiều cao hai cây con |
| Một phép quay đơn | **O(1)** | **O(1)** | Chỉ sửa số lượng liên kết cố định |
| `rebalance(node)` tại một nút | **O(1)** | **O(1)** | Có thể quay đơn/kép |
| `search(root, key)` | **O(log n)** xấu nhất | **O(1)** | Duyệt lặp một đường từ gốc |
| `insert(root, key, value)` | **O(log n)** xấu nhất | **O(log n)** | Ngăn xếp đệ quy theo chiều cao AVL |
| `inorder(root)` đầy đủ | **O(n)** | **O(h)** ngoài dữ liệu kết quả | Generator duyệt từng nút |
| `validate(root)` | **O(n)** | **O(h)** ngăn xếp đệ quy | Chỉ phục vụ kiểm thử / chẩn đoán |

AVL có **O(n)** bộ nhớ cho `n` nút, mỗi nút giữ O(1) thông tin khóa, giá trị, hai tham chiếu con và một trường chiều cao. Chi phí thực tế còn phụ thuộc kích thước đối tượng Python, bộ cấp phát và cách lưu khóa/giá trị.

## 8. Xóa khỏi AVL: vì sao việc cập nhật chiều cao khó hơn chèn?

**Xóa BST** thường cần tìm nút rồi xử lý một trong ba tình huống:

1. Nút lá: bỏ nút.
2. Nút có đúng một con: nối con đó lên vị trí nút bị xóa.
3. Nút có hai con: thay bằng khóa **kế tiếp theo inorder (successor)** hoặc **trước đó (predecessor)** theo cách giữ bất biến BST, rồi xóa nút thay thế ở vị trí cũ.

Các thao tác ấy có thể giữ **thứ tự BST**, nhưng **giảm chiều cao** của một nhánh và làm tổ tiên mất cân bằng AVL.

### 8.1. Vì sao có thể phải sửa nhiều tổ tiên?

Sau **chèn AVL**, ở điểm mất cân bằng đầu tiên và sau khi quay đúng, chiều cao cây con thường trở về mức trước khi chèn. Vì vậy có thể kết thúc quá trình tái cân bằng chèn ở điểm thích hợp (dù một cài đặt đệ quy đơn giản vẫn duyệt đường trả về để cập nhật metadata).

Sau **xóa**, một cây con có thể **giảm chiều cao** ngay cả sau khi quay; thay đổi ấy còn có thể lan lên nhiều tổ tiên. Do vậy xóa AVL có thể cần **nhiều lần quay/tái cân bằng ở các mức khác nhau** trên đường về gốc.

```text
Xóa một lá
    |
    v
Cây con giảm chiều cao
    |
    v
Cập nhật height ở cha và tính BF
    |
    +--> |BF| <= 1: đi tiếp nếu chiều cao còn ảnh hưởng tổ tiên
    |
    +--> |BF| > 1: chọn quay đơn/kép, rồi xét tổ tiên kế tiếp
```

### 8.2. Khi BF của con nặng bằng 0

Ví dụ một nút `v` bị lệch trái `BF(v)=+2` sau xóa. Nếu con trái `u` có `BF(u)=0` thì **quay phải đơn** là lựa chọn phù hợp. Tình huống `BF(con)=0` có thể xuất hiện sau xóa và thường không xuất hiện như trường hợp gây lệch đầu tiên do **một lần chèn**.

Vì vậy điều kiện tổng quát nên dùng:

```text
if BF(v) > 1:
    if BF(v.left) < 0: quay trái ở v.left
    quay phải tại v

if BF(v) < -1:
    if BF(v.right) > 0: quay phải ở v.right
    quay trái tại v
```

Đây là phần **quyết định phép quay**, chưa phải thuật toán xóa đầy đủ. Muốn cài xóa cần xử lý chính xác việc **nối lại cây con, khóa thay thế, cập nhật chiều cao và gốc mới** trong toàn bộ đường đệ quy.

**Lưu ý:** Ví dụ Python ở mục 7 chỉ cài **chèn, tìm kiếm và kiểm chứng**, không cung cấp hàm xóa. Không nên áp dụng phép xóa BST thông thường rồi tuyên bố cây vẫn là AVL khi chưa triển khai bước tái cân bằng sau xóa.

## 9. Những bất biến phải được kiểm tra độc lập

| Nhóm bất biến | Phát biểu | Khi nào dễ bị phá? |
| --- | --- | --- |
| **Thứ tự BST** | Mọi khóa cây trái < nút < mọi khóa cây phải | Gắn nhầm cây con giữa khi quay; sửa khóa tại chỗ |
| **Cân bằng AVL** | `|h(left)-h(right)| ≤ 1` ở mọi nút | Chèn/xóa làm thay đổi chiều cao một nhánh |
| **Metadata chiều cao** | `height(v)=1+max(height(left),height(right))` | Quên cập nhật sau quay hoặc sau nối lại cây con |
| **Tính duy nhất của khóa** | Mỗi khóa chỉ xuất hiện một lần trong AVL Map | Thêm khóa trùng mà không có chính sách |
| **Tính liên thông cấu trúc cây** | Mọi nút thuộc đúng một cây con, không tạo chu trình | Thao tác tham chiếu sai, bỏ mất cây con giữa |
| **Gốc hiện tại** | Biến `root` trỏ gốc mới sau quay | Không nhận giá trị trả về từ `insert`/`rotate` |
| **Quy tắc so sánh khóa** | Khóa có thứ tự nhất quán, bắc cầu, ổn định khi lưu | So sánh hỗn hợp kiểu, `NaN`, thay đổi thuộc tính khóa |

Các bất biến không thay thế nhau. Một cây có thể **đúng BST, height đúng nhưng BF=+3**; cây đó không phải AVL. Một cây có thể **đẹp và cân đối** nhưng gắn nhầm khóa lớn bên trái, khiến tìm kiếm sai.

## 10. AVL so với các cấu trúc dữ liệu khác

AVL là một lựa chọn khi cần **thứ tự khóa và thời gian tìm được chặn trong trường hợp xấu nhất**. Không phải mọi bài toán cần AVL.

| Cấu trúc | Tra chính xác | Duyệt theo khóa tăng | Thêm/xóa | Đánh đổi chính |
| --- | --- | --- | --- | --- |
| **BST không cân bằng** | O(n) xấu nhất | O(n) duyệt hết | O(n) xấu nhất | Dễ cài hơn nhưng có thể lệch |
| **AVL** | O(log n) xấu nhất | O(n) duyệt hết | O(log n) xấu nhất | Phải duy trì chiều cao và quay |
| **Red–Black** | O(log n) xấu nhất | O(n) duyệt hết | O(log n) xấu nhất | Duy trì màu/black-height thay vì BF chặt |
| **Bảng băm** | O(1) kỳ vọng | Cần sắp xếp thêm | O(1) kỳ vọng cho thao tác theo khóa | Không tự duy trì thứ tự khóa |
| **Mảng đã sắp** | O(log n) tìm nhị phân | O(n) duyệt hết | O(n) để chèn/xóa giữa dãy | Truy cập theo vị trí tốt, sửa giữa dãy tốn kém |
| **Min-heap** | Không thuận lợi để tìm khóa bất kỳ | Không có inorder sắp | O(log n) thêm/lấy cực trị | Tối ưu lấy phần tử ưu tiên nhất |

Với yêu cầu **lấy các bài có thời lượng trong khoảng [20,40]** mà vẫn hỗ trợ thêm/xóa bài thường xuyên, một AVL theo khóa `(duration, lesson_id)` có thể phục vụ truy vấn khoảng **O(log n + k)** với `k` kết quả nếu dùng thuật toán duyệt khoảng thích hợp.

Nhưng nếu nghiệp vụ chủ yếu tra **ID chính xác** và hiếm khi cần thứ tự, `dict` theo ID thường đơn giản và có tra cứu kỳ vọng O(1). Nếu dữ liệu hiếm thay đổi và truy vấn thứ tự rất nhiều, **mảng đã sắp** cũng đáng cân nhắc.

### 10.1. Cần bảo toàn khóa định danh và khóa sắp xếp

Giả sử mỗi bản ghi bài có `lesson_id` và `duration_minutes`:

- `lesson_id` là khóa định danh nghiệp vụ; nó nên giữ ổn định khi bài được sửa tiêu đề.
- `(duration_minutes, lesson_id)` là khóa **thứ tự** để các bài cùng thời lượng có thứ tự xác định.
- Nếu sửa `duration_minutes`, phải **loại khóa thứ tự cũ rồi chèn khóa mới** vào AVL, hoặc dùng thao tác tương đương bảo toàn BST; không đổi trường khóa của một nút tại chỗ.

Một hệ thống có thể dùng song song `dict` theo ID và AVL theo thời lượng, nhưng mỗi lần sửa/xóa cần giữ **hai chỉ mục nhất quán**, trả thêm chi phí bộ nhớ và bảo trì.

## 11. Kiểm thử: đừng chỉ nhìn hình dạng cây

Với mỗi thao tác chèn/xóa đã triển khai, nên kiểm tra:

1. **Tập khóa không đổi ngoài phần cần thêm/xóa.** Quay không được tạo mất hay nhân đôi khóa.
2. **Duyệt inorder cho khóa tăng chặt.** Nếu có khóa trùng, cần chính sách rõ và kiểm tra theo chính sách đó.
3. **BST trên mọi nút:** sử dụng cận dưới và cận trên, không chỉ so với cha trực tiếp.
4. **BF trên mọi nút:** tính lại chiều cao thật để kiểm tra `|BF|≤1`.
5. **Metadata:** chiều cao lưu phải đúng bằng chiều cao tính lại từ các con.
6. **Chiều cao tổng thể:** không tăng tuyến tính khi chèn khóa tăng hoặc giảm liên tiếp.
7. **Gốc mới:** sau quay ở gốc, các thao tác tìm kiếm phải dùng đúng tham chiếu trả về.
8. **Trường hợp biên:** cây rỗng, một nút, khóa trùng, chèn tăng/giảm, bốn hình dạng quay, xóa lá/1 con/2 con nếu đã hỗ trợ xóa.

### 11.1. Những lỗi phổ biến

- **“BST thì tự nhiên đã cân bằng.”** Không đúng: chèn khóa tăng dần có thể cho `h=Θ(n)`.
- **“BF chỉ cần kiểm tra ở gốc.”** Sai: mọi nút phải có `BF∈{-1,0,1}`.
- **“BF=+1 là mất cân bằng.”** Sai với quy ước bài này: +1 vẫn hợp lệ; +2 hoặc −2 mới là dấu hiệu vi phạm thường gặp sau một cập nhật từ cây hợp lệ.
- **“Height của nút chỉ cần là độ sâu từ gốc.”** Sai: height và depth đo theo hai hướng khác nhau.
- **“AVL bắt buộc hai cây con có cùng số nút.”** Sai: bất biến dựa vào chiều cao, không phải kích thước.
- **“Quay là hoán đổi khóa giữa hai nút.”** Sai: quay đổi liên kết, giữ nguyên thứ tự inorder và nội dung mỗi nút.
- **“Quay xong chỉ cần cập nhật height của nút đi lên.”** Sai: phải cập nhật nút đi xuống trước.
- **“Cài LL/RR là đủ.”** Sai: LR/RL cần quay kép.
- **“Sau xóa có thể dùng nguyên điều kiện so khóa vừa chèn.”** Sai: xóa không có khóa mới; BF của con nặng có thể bằng 0.
- **“Chèn AVL O(1) vì mỗi quay O(1).”** Sai: còn đường tìm kiếm và cập nhật các tổ tiên O(log n).
- **“Chạy validate O(n) trong ví dụ chứng tỏ thuật toán chèn O(n).”** Sai: validate là kiểm tra bổ sung, không phải bản chất `insert`.

## 12. Bài tập vận dụng

**Bài 1 — Tính chiều cao.** Với cây rỗng, nút lá và một nút có con trái cao 3, con phải cao 2, hãy tính `height` theo cả quy ước đếm nút và đếm cạnh. Nêu vì sao hai quy ước không làm đổi Big O.

*Gợi ý:* Bài dùng cây rỗng cao 0, lá cao 1, nút có hai con cao 4. Nếu đếm cạnh thì các chiều cao lần lượt là −1, 0 và 3; chỉ chênh một đơn vị.

**Bài 2 — Dấu của BF.** Một nút có trái cao 4, phải cao 3. Nút đó có hợp lệ trong AVL không? Một nút khác trái cao 2, phải cao 4 có BF bao nhiêu?

*Gợi ý:* BF đầu = +1, hợp lệ; BF thứ hai = −2, vi phạm và nặng phải.

**Bài 3 — Kiểm tra ở mọi nút.** Hãy vẽ một BST có gốc BF=0 nhưng có một nút con BF=+2. Giải thích vì sao không được kết luận toàn bộ cây là AVL chỉ bằng BF gốc.

*Gợi ý:* Có thể tạo hai nhánh tổng cao bằng nhau nhưng trong mỗi nhánh có các đoạn lệch ở cấp thấp hơn; bất biến AVL mang lượng từ “mọi nút”.

**Bài 4 — Các hình dạng quay.** Hãy chèn lần lượt `[30,20,10]`, `[10,20,30]`, `[30,10,20]` và `[10,30,20]` vào AVL rỗng. Xác định BF của nút mất cân bằng và vẽ kết quả sau quay.

*Gợi ý:* LL, RR, LR, RL; cả bốn kết thúc với gốc `20`, hai lá `10` và `30`.

**Bài 5 — Chiều cao tối thiểu.** Dùng `N(0)=0`, `N(1)=1` và `N(h)=1+N(h−1)+N(h−2)` để tính `N(6)` và `N(7)`. Vì sao dãy này cho thấy chiều cao AVL tăng logarit theo số nút?

*Gợi ý:* `N(6)=20`, `N(7)=33`; số nút tối thiểu tăng theo dạng Fibonacci nên tăng theo hàm mũ của `h`.

**Bài 6 — Metadata sau quay.** Trước quay trái, nút `x` có con phải `y`, và `y` có cây con trái `B`. Sau quay, cây con `B` phải nằm ở đâu? Nút nào phải tính lại `height` trước?

*Gợi ý:* `B` trở thành `x.right`; tính lại `height(x)` trước `height(y)`.

**Bài 7 — Khóa trùng.** Tại sao mã `insert` của ví dụ cập nhật giá trị khi `key == node.key` thay vì chèn thêm một nút? Nếu bài toán muốn lưu nhiều giá trị cho một khóa, bạn sẽ thay đổi cấu trúc giá trị như thế nào?

*Gợi ý:* Dùng ngữ nghĩa Map một khóa/một mục; nếu cần nhiều giá trị, nút có thể giữ danh sách hoặc tập giá trị cho khóa.

**Bài 8 — Xóa trong AVL.** Sau khi xóa ở nhánh phải, một nút có `BF=+2` và con trái có `BF=0`. Nên quay đơn hay quay kép? Vì sao trạng thái này phải được xét trong thuật toán xóa?

*Gợi ý:* Quay phải đơn; BF con bằng 0 là trường hợp có thể xuất hiện sau xóa và không nên xử lý như tình huống LR.

**Bài 9 — Phân biệt chi phí.** Giải thích tại sao `balance_factor` có thể là O(1) khi lưu `height`, trong khi một hàm kiểm chứng tính lại chiều cao của cả cây là O(n).

*Gợi ý:* Metadata cho phép đọc hai con trong O(1); kiểm chứng không được tin metadata nên phải đi qua tất cả nút.

**Bài 10 — Chọn cấu trúc.** Một hệ thống cần tìm bài theo ID, một hệ thống khác thường xuyên hỏi các bài theo khoảng thời lượng và liên tục thêm/xóa. Hãy so sánh bảng băm, mảng đã sắp và AVL theo thời gian, bộ nhớ và chi phí bảo trì.

*Gợi ý:* Bảng băm thuận tra chính xác O(1) kỳ vọng; mảng đã sắp tìm nhị phân nhưng chèn giữa O(n); AVL giữ O(log n) tìm/chèn/xóa theo thứ tự, đổi lại phải duy trì chiều cao và quay.

## Tổng kết

**Cây AVL** là BST bổ sung ràng buộc **`|height(left)-height(right)|≤1` tại mọi nút**. Quy ước chiều cao cần thống nhất; với `height(None)=0` và lá cao 1, hệ số cân bằng là `BF=h(left)-h(right)` và các giá trị hợp lệ là `−1, 0, +1`. Ràng buộc này buộc số nút tối thiểu tăng theo dạng Fibonacci khi chiều cao tăng, nhờ đó **h=O(log n)** và các phép toán tìm, chèn, xóa có chi phí **O(log n) xấu nhất** nếu cài đúng. Khi cập nhật làm một nhánh lệch quá mức, thuật toán phải **tính lại metadata và chọn quay LL/RR/LR/RL** mà vẫn bảo toàn thứ tự BST. AVL là một công cụ hữu ích cho dữ liệu cần **thứ tự khóa ổn định và giới hạn chiều cao**, nhưng việc chọn dùng nó phải tính cả bộ nhớ và độ phức tạp duy trì bất biến.
