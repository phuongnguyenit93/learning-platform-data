# Phép quay trái, quay phải và bảo toàn thứ tự BST

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Vẽ chính xác **quay trái (left rotation)** và **quay phải (right rotation)** tại một nút, kể cả khi nút có cây con nằm giữa hai khóa.
- Chứng minh phép quay **bảo toàn bất biến thứ tự của cây tìm kiếm nhị phân (BST)**, không làm mất hay tạo thêm khóa.
- Phân biệt **thay đổi hình dạng cây** với **thay đổi nội dung hoặc thứ tự duyệt inorder**.
- Cập nhật đúng các tham chiếu `left`, `right`, `parent`, **gốc cây** và metadata chiều cao sau phép quay.
- Giải thích bốn hình dạng **LL, RR, LR, RL** và cách kết hợp quay đơn/quay kép để khôi phục cân bằng.
- Phân tích chi phí O(1) của phần thay liên kết, chi phí bảo trì metadata, và kiểm tra các bất biến bằng một ví dụ Python tự chứa.

## 1. Tại sao cây tìm kiếm cần phép quay?

Trong **cây tìm kiếm nhị phân (Binary Search Tree — BST)** với khóa phân biệt, mỗi nút có một khóa và tối đa hai nhánh:

1. Mọi khóa trong cây con trái **nhỏ hơn** khóa của nút.
2. Mọi khóa trong cây con phải **lớn hơn** khóa của nút.
3. Hai điều kiện trên phải đúng với **toàn bộ cây con**, không chỉ với hai nút con trực tiếp.

Ví dụ, sau khi chèn lần lượt `10, 20, 30` vào BST thông thường, cây có thể thành:

```text
10
  \
   20
     \
      30
```

Cây này hoàn toàn **đúng thứ tự BST**, nhưng đường từ gốc tới lá khá dài. Nếu tiếp tục chèn khóa tăng dần, cây trở thành một dãy một nhánh; tìm, thêm và xóa có thể tốn **O(n)** thay vì O(log n).

**Phép quay cây (tree rotation)** là một thao tác cục bộ thay quan hệ cha–con để đổi hình dạng mà vẫn giữ thứ tự khóa. Nó là công cụ nền tảng của nhiều cây tự cân bằng như **AVL** và **Red–Black**.

Quay trái tại gốc `10` của ví dụ trên:

```text
Trước quay:              Sau quay trái tại 10:

10                            20
  \                          /  \
   20                       10   30
     \
      30
```

Cây mới thấp hơn một mức và vẫn thỏa thứ tự BST. Tuy nhiên, **không phải phép quay bất kỳ lúc nào cũng giảm chiều cao hoặc tự động cân bằng toàn cây**. Thuật toán cân bằng phải chọn **đúng điểm và hướng quay** dựa trên bất biến đang bị vi phạm.

### 1.1. Phạm vi giả định

Trong bài học:

- Mỗi khóa là một giá trị thuộc miền có **thứ tự toàn phần nhất quán**; các ví dụ dùng số nguyên.
- Khóa **không trùng**; một Map có thể cập nhật giá trị nếu thêm khóa đã tồn tại. Hệ thống muốn lưu khóa trùng phải có chính sách riêng như bộ đếm hoặc danh sách giá trị.
- `left` và `right` là **tham chiếu** tới nút con, không phải sao chép nút con.
- `None` đại diện cho cây con rỗng.
- **Chiều cao** được tính bằng số nút trên đường dài nhất: `height(None)=0` và nút lá có `height=1`.

Nhờ nêu rõ giả định, ta có thể kiểm chứng tính đúng đắn bằng quy tắc BST và không nhầm với đồ thị có chu trình hoặc với quan hệ sắp xếp thiếu bắc cầu.

## 2. Quay trái: đưa con phải lên làm gốc cây con

Xét một nút `x` có **con phải `y`**. Cây con trái của `x` là `A`; cây con trái và phải của `y` lần lượt là `B` và `C`:

```text
TRƯỚC quay trái tại x:

         x
        / \
       A   y
          / \
         B   C
```

Sau khi **quay trái tại `x`**:

```text
SAU quay trái tại x:

         y
        / \
       x   C
      / \
     A   B
```

Ta chỉ thay đổi **vị trí của `x`, `y` và cây con `B`**:

1. Ghi nhớ `y = x.right`; đây phải là một nút thật.
2. Chuyển `B = y.left` thành **con phải** của `x`: `x.right = B`.
3. Đưa `x` thành **con trái** của `y`: `y.left = x`.
4. Đưa `y` vào vị trí mà `x` trước đó giữ trong cây lớn hơn (nếu có).
5. Cập nhật các tham chiếu cha và metadata chiều cao nếu cấu trúc có lưu chúng.

Thao tác này **không** tạo nút mới, xóa nút hoặc đổi khóa của nút nào. Gốc **cây con vừa quay** đổi từ `x` thành `y`.

### 2.1. Vì sao cây con `B` phải chuyển sang bên phải `x`?

Từ bất biến BST trước khi quay, ta biết:

\[
\forall a\in A:\ a < x,\qquad
\forall b\in B:\ x < b < y,\qquad
\forall c\in C:\ y < c.
\]

Các khóa trong `B` **lớn hơn `x` nhưng nhỏ hơn `y`**. Sau khi `x` trở thành con trái của `y`, cây con `B` chỉ có thể nằm ở **phía phải của `x`** để vẫn đúng thứ tự.

Đây là điểm quan trọng nhất khi tự viết phép quay: **không được làm mất hoặc gắn sai cây con nằm giữa hai nút được quay**.

### 2.2. Chứng minh bằng thứ tự duyệt giữa (inorder)

Ký hiệu `in(A)` là dãy khóa thu được khi duyệt inorder cây con `A`. Trước quay trái:

```text
in(A), x, in(B), y, in(C)
```

Sau quay trái:

```text
in(A), x, in(B), y, in(C)
```

Hai dãy **giống hệt nhau**. Phép quay chỉ thay đổi hình dạng các nhánh chứ không thay đổi **thứ tự tuyến tính của các khóa**.

Kết luận mạnh hơn việc “một ví dụ trông đúng”: nếu các cây con `A`, `B`, `C` đã thỏa thứ tự BST và trước quay có `A < x < B < y < C`, thì sau quay **toàn bộ cây con vẫn thỏa bất biến BST**.

## 3. Quay phải: phép đối xứng của quay trái

Quay phải tại `y` yêu cầu nút `y` có **con trái `x`**:

```text
TRƯỚC quay phải tại y:       SAU quay phải tại y:

          y                            x
         / \                          / \
        x   C                        A   y
       / \                              / \
      A   B                            B   C
```

Các bước:

1. Ghi nhớ `x = y.left`.
2. Chuyển `B = x.right` thành **con trái** của `y`: `y.left = B`.
3. Đưa `y` thành **con phải** của `x`: `x.right = y`.
4. Nối `x` với nút cha cũ của `y`, hoặc biến `x` thành gốc cây nếu `y` từng là gốc.
5. Cập nhật tham chiếu cha và metadata liên quan.

Thứ tự inorder trước/sau đều là:

```text
in(A), x, in(B), y, in(C)
```

Vì vậy quay phải cũng **bảo toàn quan hệ thứ tự BST**. Hai phép quay là **nghịch đảo về hình dạng** khi được thực hiện đúng tại các nút tương ứng:

- Quay trái tại `x` để `y` lên làm gốc cây con.
- Quay phải tại `y` vừa lên để đưa `x` về vị trí cũ.

Những phép quay này khôi phục lại **cấu trúc liên kết ban đầu** nếu không có cập nhật khác xen giữa và vẫn dùng chính các nút đó.

## 4. Phép quay bảo toàn gì và thay đổi gì?

| Thuộc tính | Sau phép quay hợp lệ | Vì sao? |
| --- | --- | --- |
| **Tập khóa / số nút** | **Không đổi** | Không cấp phát hay loại nút |
| **Giá trị gắn với từng khóa** | **Không đổi** | Không hoán đổi nội dung bản ghi |
| **Thứ tự inorder** | **Không đổi** | Các cây con giữ quan hệ `A < x < B < y < C` |
| **Bất biến BST** | **Được giữ** nếu trước quay đúng | Các nút được nối lại theo đúng khoảng khóa |
| **Gốc của cây con** | **Thay đổi** | Con lên thay nút được quay |
| **Nút cha và con của các nút tham gia** | **Thay đổi** | Đó là mục đích của quay |
| **Độ sâu từng nút** | **Có thể thay đổi** | Các nhánh chuyển sang vị trí khác |
| **Chiều cao cây con** | **Có thể tăng, giảm hoặc giữ nguyên** | Phụ thuộc hình dạng `A`, `B`, `C` |
| **Metadata `height`, `size`, `parent`** | **Có thể cần cập nhật** | Tham chiếu và hình dạng đã thay đổi |

Một lỗi suy luận phổ biến là “nếu inorder không đổi thì mọi thứ khác cũng không đổi”. **Sai**: đường tìm, mức sâu của từng nút, quan hệ cha–con và chiều cao có thể thay đổi, dù dãy khóa inorder giữ nguyên.

### 4.1. Khi nào không được quay?

- **Không thể quay trái** nếu `x.right is None`: không có con phải để đưa lên.
- **Không thể quay phải** nếu `y.left is None`: không có con trái để đưa lên.
- Không quay một **nút không thuộc cây đang quản lý** rồi tự cho rằng gốc và liên kết còn hợp lệ.
- Không sửa con trỏ theo thứ tự tùy ý đến mức làm mất tham chiếu tạm cần dùng.
- Không kết luận toàn cây đã cân bằng chỉ vì thực hiện thành công một phép quay.

Với cây lưu `parent`, muốn quay ở **giữa cây**, ngoài các nút cục bộ còn phải cập nhật cạnh từ **cha cũ** tới gốc cây con mới. Với quay ở **gốc toàn cây**, chương trình phải cập nhật chính biến `root`.

## 5. Quay ở gốc và quay giữa cây

### 5.1. Quay trái ở gốc

```text
Trước:

root ──> x
          \
           y

Sau:

root ──> y
         /
        x
```

Nếu một hàm chỉ đổi `x.right` và `y.left` nhưng không trả về/đổi `root`, các lời gọi tìm kiếm sau đó vẫn bắt đầu từ `x` và có thể **không truy cập được `y`**.

Hàm quay vì thế thường nhận và trả lại gốc, hoặc hoạt động thông qua một đối tượng cây có trường `root`.

### 5.2. Quay tại cây con

```text
Trước quay trái tại x:        Sau:

          p                         p
         /                         /
        x                         y
         \                       /
          y                     x
```

Giả sử `x` là **con trái** của `p`. Sau quay, `p.left` phải đổi sang `y`, đồng thời `y.parent` trở thành `p` và `x.parent` trở thành `y`. Nếu `x` là con phải của `p` thì phải thay `p.right` thay vì `p.left`.

Nếu `B` là cây con chuyển từ `y.left` sang `x.right` thì `B.parent` cũng phải thành `x`. **Quên một hướng cập nhật** làm các thuật toán đi từ con lên cha như tìm tổ tiên, cập nhật chiều cao hoặc tái cân bằng có thể hoạt động sai.

### 5.3. Nên cập nhật tham chiếu theo thứ tự nào?

Một trình tự an toàn khi quay trái:

```text
y = x.right
B = y.left
p = x.parent

x.right = B
if B != None: B.parent = x

y.parent = p
if p == None: root = y
else: thay liên kết của p từ x sang y

y.left = x
x.parent = y

cập nhật metadata của x, rồi y, rồi tổ tiên nếu cần
```

Lưu `y`, `B` và `p` **trước** khi ghi đè các tham chiếu. Quay phải dùng các phép gán đối xứng.

## 6. Ví dụ Python: quay trái/phải có tham chiếu cha và chiều cao

Ví dụ sau thiết kế **một BST thông thường** rồi cho phép quay tại gốc hoặc tại nút bên trong. Nó cố ý **không tự cân bằng khi chèn**, để người học thấy rõ quay là **thao tác cục bộ** và bất biến BST có thể kiểm tra độc lập với cân bằng AVL.

Các quy ước:

- Khóa là số nguyên phân biệt; khóa trùng giữ nguyên nút.
- Mỗi nút lưu `key`, `left`, `right`, `parent`, `height`.
- `height(None) = 0`, lá có chiều cao 1.
- Hàm quay nhận `root` hiện tại và `pivot` đã thuộc cây, rồi **trả lại gốc hiện tại** sau quay.
- `validate` kiểm tra thứ tự toàn cây, tham chiếu cha–con, chiều cao lưu và không có nút bị duyệt lặp.

```python
class Node:
    def __init__(self, key):
        self.key = key
        self.left = None
        self.right = None
        self.parent = None
        self.height = 1


def height(node):
    return 0 if node is None else node.height


def update_height(node):
    node.height = 1 + max(height(node.left), height(node.right))


def update_ancestors(node):
    """Tính lại chiều cao từ node đến gốc theo các liên kết parent."""
    while node is not None:
        update_height(node)
        node = node.parent


def insert_bst(root, key):
    """Chèn BST thường, không tự cân bằng; khóa trùng không thêm nút."""
    if root is None:
        return Node(key)

    current = root
    while True:
        if key == current.key:
            return root
        if key < current.key:
            if current.left is None:
                new_node = Node(key)
                current.left = new_node
                new_node.parent = current
                break
            current = current.left
        else:
            if current.right is None:
                new_node = Node(key)
                current.right = new_node
                new_node.parent = current
                break
            current = current.right

    update_ancestors(current)
    return root


def rotate_left(root, x):
    """Quay trái tại x và trả về gốc cây cập nhật."""
    y = x.right
    if y is None:
        raise ValueError("Quay trái cần nút con phải")

    old_parent = x.parent
    middle = y.left

    # Cây con giữa x và y chuyển sang phải của x.
    x.right = middle
    if middle is not None:
        middle.parent = x

    # Đưa y vào vị trí x từng giữ.
    y.parent = old_parent
    if old_parent is None:
        root = y
    elif old_parent.left is x:
        old_parent.left = y
    else:
        assert old_parent.right is x
        old_parent.right = y

    # Đặt x thành con trái của y.
    y.left = x
    x.parent = y

    # Nút đi xuống phải cập nhật trước nút đi lên.
    update_height(x)
    update_height(y)
    update_ancestors(y.parent)
    return root


def rotate_right(root, y):
    """Quay phải tại y và trả về gốc cây cập nhật."""
    x = y.left
    if x is None:
        raise ValueError("Quay phải cần nút con trái")

    old_parent = y.parent
    middle = x.right

    # Cây con giữa x và y chuyển sang trái của y.
    y.left = middle
    if middle is not None:
        middle.parent = y

    # Đưa x vào vị trí y từng giữ.
    x.parent = old_parent
    if old_parent is None:
        root = x
    elif old_parent.left is y:
        old_parent.left = x
    else:
        assert old_parent.right is y
        old_parent.right = x

    # Đặt y thành con phải của x.
    x.right = y
    y.parent = x

    update_height(y)
    update_height(x)
    update_ancestors(x.parent)
    return root


def inorder(root):
    """Duyệt inorder không đệ quy, O(n) thời gian."""
    result = []
    stack = []
    current = root
    while stack or current is not None:
        while current is not None:
            stack.append(current)
            current = current.left
        current = stack.pop()
        result.append(current.key)
        current = current.right
    return result


def validate(root):
    """Kiểm tra thứ tự BST, parent, height và nút không trùng."""
    seen = set()

    def walk(node, parent, lower, upper):
        if node is None:
            return 0, 0  # (height, số nút)

        assert node not in seen, "Có chu trình hoặc nhiều đường đến một nút"
        seen.add(node)
        assert node.parent is parent, "Tham chiếu parent sai"
        if lower is not None:
            assert lower < node.key, "Sai cận dưới BST"
        if upper is not None:
            assert node.key < upper, "Sai cận trên BST"

        lh, ln = walk(node.left, node, lower, node.key)
        rh, rn = walk(node.right, node, node.key, upper)
        assert node.height == 1 + max(lh, rh), "Sai height"
        return node.height, 1 + ln + rn

    return walk(root, None, None, None)


# A. Quay trái tại gốc rồi quay phải để khôi phục hình dạng.
root = None
for key in [10, 5, 20, 15, 30, 12, 17]:
    root = insert_bst(root, key)

expected = [5, 10, 12, 15, 17, 20, 30]
assert inorder(root) == expected
assert validate(root)[1] == len(expected)

root = rotate_left(root, root)
assert root.key == 20
assert root.parent is None
assert root.left.key == 10
assert inorder(root) == expected
assert validate(root)[1] == len(expected)

root = rotate_right(root, root)
assert root.key == 10
assert inorder(root) == expected
assert validate(root)[1] == len(expected)

# B. Quay phải ở cây con phải, không đổi gốc toàn cây.
root = rotate_right(root, root.right)
assert root.key == 10
assert root.right.key == 15
assert root.right.parent is root
assert inorder(root) == expected
assert validate(root)[1] == len(expected)

# C. Quay kép LR.
lr = None
for key in [30, 10, 20]:
    lr = insert_bst(lr, key)
lr = rotate_left(lr, lr.left)
lr = rotate_right(lr, lr)
assert lr.key == 20
assert inorder(lr) == [10, 20, 30]
assert validate(lr) == (2, 3)

# D. Quay kép RL.
rl = None
for key in [10, 30, 20]:
    rl = insert_bst(rl, key)
rl = rotate_right(rl, rl.right)
rl = rotate_left(rl, rl)
assert rl.key == 20
assert inorder(rl) == [10, 20, 30]
assert validate(rl) == (2, 3)

# E. Quay theo hướng thiếu con phải thông báo lỗi.
try:
    rotate_left(lr, lr.right)
except ValueError:
    pass
else:
    raise AssertionError("Phải từ chối quay khi thiếu con phải")
```

### 6.1. Những chỗ dễ sai trong mã

**Quên gốc mới:** sau `rotate_left(root, root)`, phải dùng giá trị `root` được trả về. Gốc có thể thay đổi nhưng số nút không đổi.

**Quên cây con giữa:** `middle` phải được nối sang con còn trống của nút đi xuống; nếu không, có thể mất cả một cây con và vi phạm thứ tự BST.

**Quên `parent`:** nếu chỉ gán `left`/`right`, đi từ nút lên cha có thể dẫn tới nút cũ không còn là cha hoặc tạo vòng tham chiếu.

**Cập nhật metadata sai thứ tự:** sau quay trái, `x` đi xuống, `y` lên trên; tính lại `height(x)` rồi `height(y)`. Với quay phải, tính lại `height(y)` trước `height(x)`.

**Chỉ kiểm tra hai nút quay:** `validate` dùng cả cận dưới và cận trên do tổ tiên truyền xuống, nên phát hiện được khóa nằm sai sâu trong cây con.

**Dùng bộ kiểm chứng thay thuật toán:** `validate` duyệt toàn cây nên O(n), phục vụ thử nghiệm và học tập; không phải bước bắt buộc của mỗi phép quay/chèn trong cây cân bằng vận hành.

### 6.2. Chi phí của mã so với phép quay nguyên thủy

Phần **thay tham chiếu cục bộ** của `rotate_left`/`rotate_right` chỉ gồm số lượng phép gán không phụ thuộc `n`:

- **O(1)** thời gian cho con trỏ và cập nhật chiều cao **hai nút trực tiếp**.
- **O(1)** bộ nhớ phụ cho vài tham chiếu tạm.

Nhưng **hàm minh họa ở trên** còn gọi `update_ancestors` để luôn giữ metadata chiều cao đúng **từ cây con được quay đến gốc toàn cây**. Nếu có `h` mức tổ tiên, chi phí toàn bộ lời gọi **O(h)** thời gian (trường hợp xấu O(n) trong BST lệch), dù phép quay cục bộ vẫn là O(1).

Trong **AVL/RB tree**, thuật toán thêm/xóa thường đã theo dõi đường tổ tiên để cập nhật và tái cân bằng, nên thao tác quay nguyên thủy không cần chủ động quét đường này lần thứ hai. Với cây cân bằng có `h=O(log n)`, việc tìm chỗ chèn, sửa metadata và quay theo đường đi vẫn cho **O(log n)** thời gian cho thao tác chèn/xóa tương ứng nếu được cài đúng.

## 7. Bốn tình huống LL, RR, LR, RL

Phép quay không được chọn chỉ dựa trên việc cây **trông lệch**. Với AVL, sau khi chèn một khóa, ta tìm tổ tiên mất cân bằng và xét **hướng tăng chiều cao** của các nhánh.

Định nghĩa:

\[
\operatorname{balance}(v)=h(v.left)-h(v.right).
\]

Bất biến AVL yêu cầu `balance(v) ∈ {-1,0,1}` ở mọi nút. Sau chèn, nếu một nút có `balance > 1` thì nặng trái; nếu `balance < -1` thì nặng phải.

### 7.1. LL — một phép quay phải

Chèn `30, 20, 10`:

```text
Trước:                 Sau quay phải tại 30:

      30                       20
     /                        /  \
   20                        10   30
  /
10
```

Đường tăng chiều cao nằm **trái của con trái**. Nút `30` mất cân bằng trái, nên quay phải để `20` lên gốc.

### 7.2. RR — một phép quay trái

Chèn `10, 20, 30`:

```text
Trước:                 Sau quay trái tại 10:

10                            20
  \                          /  \
   20                       10   30
     \
      30
```

Đường tăng chiều cao nằm **phải của con phải**. Nút `10` mất cân bằng phải, nên quay trái.

### 7.3. LR — quay trái ở con, rồi quay phải ở nút

Chèn `30, 10, 20`:

```text
Bước 0:                Bước 1:                Bước 2:

      30                     30                     20
     /                      /                      /  \
   10                     20                     10   30
     \                   /
      20                10

             quay trái tại 10       quay phải tại 30
```

Nếu chỉ quay phải ngay tại `30`, nút `10` lên trên nhưng phần cây vẫn còn lệch. Phải **biến hình dạng gấp khúc (LR) thành LL**, rồi quay phải tại nút mất cân bằng.

### 7.4. RL — quay phải ở con, rồi quay trái ở nút

Chèn `10, 30, 20`:

```text
Bước 0:                Bước 1:                Bước 2:

10                     10                     20
  \                      \                   /  \
   30                     20                10   30
  /                         \
 20                          30

           quay phải tại 30        quay trái tại 10
```

Đây là tình huống đối xứng của LR.

| Hình dạng | Dấu hiệu AVL tại nút `z` mất cân bằng do chèn | Thao tác |
| --- | --- | --- |
| **LL** | Nặng trái, khóa mới ở nhánh trái của `z.left` | Quay phải `z` |
| **RR** | Nặng phải, khóa mới ở nhánh phải của `z.right` | Quay trái `z` |
| **LR** | Nặng trái, khóa mới ở nhánh phải của `z.left` | Quay trái `z.left`, sau đó quay phải `z` |
| **RL** | Nặng phải, khóa mới ở nhánh trái của `z.right` | Quay phải `z.right`, sau đó quay trái `z` |

Trong thao tác **xóa AVL**, xác định hướng quay cần dựa vào hệ số cân bằng của nút và **nút con tương ứng**, kể cả trường hợp hệ số bằng 0. Không nên bê nguyên điều kiện dựa trên “khóa vừa chèn” sang phép xóa.

## 8. Vì sao bảo toàn inorder chưa đủ để bảo đảm AVL?

Giả sử quay trái tại `x` bảo toàn toàn bộ dãy inorder. Điều đó chỉ chứng minh **bất biến tìm kiếm** vẫn đúng. Muốn nói cây là AVL, ta còn cần:

\[
\forall v:\quad |h(v.left)-h(v.right)|\le 1.
\]

Một phép quay có thể:

- Làm chiều cao cây con giảm.
- Chuyển chỗ mất cân bằng sang một nút khác nếu chọn sai hướng.
- Giữ hoặc tăng chiều cao trong một hình dạng không phù hợp.

Vì vậy quy trình tái cân bằng chuẩn không phải “thấy lệch thì quay bừa” mà là:

1. Cập nhật chiều cao thực của các cây con sau khi thay đổi.
2. Tìm nút có hệ số cân bằng vượt ngoài khoảng cho phép.
3. Xác định một trong các hình dạng LL/RR/LR/RL.
4. Thực hiện đúng phép quay đơn hoặc kép.
5. Cập nhật metadata, nối lại gốc cây con và tiếp tục xử lý tổ tiên nếu thuật toán yêu cầu.

### 8.1. Quay và bất biến của cây Red–Black

Red–Black tree cũng sử dụng quay trái/phải để thay hình dạng, nhưng quyết định sửa cây còn phụ thuộc **màu nút**, quy tắc **không có hai nút đỏ liên tiếp** và **black-height** trên các đường đến lá giả.

**Một phép quay không tự sửa màu.** Thao tác thêm/xóa Red–Black phối hợp **đổi màu** và **quay** theo trường hợp cụ thể. Nếu chỉ dùng mã quay BST thông thường mà không cập nhật quy tắc màu, cây có thể vẫn tìm kiếm đúng nhưng **không còn bảo đảm cân bằng Red–Black**.

### 8.2. Quay không thay đổi số nút, nhưng metadata tổng hợp phải sửa

Nếu mỗi nút còn lưu:

\[
\operatorname{size}(v)=1+\operatorname{size}(v.left)+\operatorname{size}(v.right),
\]

thì sau quay, dù **tổng số nút trong cả cây con** không đổi, `size` của hai nút quay **có thể thay đổi**. Ví dụ `x` trước quay là gốc của toàn bộ cây con; sau quay, `x` chỉ quản lý `A` và `B`, nên `size(x)` thường nhỏ hơn trước.

Ứng dụng dùng `size` để tìm **phần tử thứ k** hoặc tính **thứ hạng** phải cập nhật metadata tương ứng. Với các giá trị gộp trên cây con như tổng, min, max hoặc giá trị tùy chỉnh, phải có **quy tắc tính lại** nhất quán với cấu trúc và phép quay.

## 9. Đánh đổi thời gian, bộ nhớ và độ phức tạp cài đặt

| Công việc | Chi phí điển hình | Ghi chú |
| --- | --- | --- |
| Quay đơn chỉ thay liên kết | **O(1)** thời gian, **O(1)** bộ nhớ phụ | Đã có tham chiếu tới nút pivot và con cần thiết |
| Quay kép | **O(1)** thời gian, **O(1)** bộ nhớ phụ | Hai phép quay đơn liên tiếp |
| Sửa chiều cao của hai nút quay | **O(1)** | Giả sử chiều cao các cây con khác đã đúng |
| Lan truyền sửa metadata đến gốc | **O(h)** | `h` là chiều cao hiện tại; có thể nằm trong thuật toán tái cân bằng |
| Tìm nút theo khóa trong BST | **O(h)** | Cây lệch có `h=O(n)` |
| Chèn/tìm trong AVL cân bằng đúng | **O(log n)** xấu nhất | Có bước tìm và tái cân bằng thích hợp |
| Chèn/tìm trong Red–Black đúng | **O(log n)** xấu nhất | Có thêm quy tắc màu và xử lý fix-up |
| Bộ nhớ mỗi nút để lưu `parent`, `height` | **O(1)** bổ sung mỗi nút | Tổng O(n), tăng số tham chiếu và công việc cập nhật |

**Không nên trộn ba loại chi phí**: chi phí **phép quay nguyên thủy**, chi phí **một lời gọi tiện ích có sửa toàn bộ tổ tiên**, và chi phí **toàn bộ thao tác chèn/xóa**. Một phép quay O(1) không có nghĩa toàn bộ `insert` là O(1); ngược lại, một hàm kiểm chứng toàn cây O(n) không có nghĩa bản chất thao tác quay là O(n).

### 9.1. Khi nào có thể bỏ tham chiếu cha?

Cây BST/AVL có thể dùng **thuật toán đệ quy trả về gốc mới của cây con**, rồi gán:

```python
# Phác thảo cách gắn gốc cây con mới khi cài bằng đệ quy:
#
# node.left = insert(node.left, new_key)
# ...
# return rotate_right(node)  # Trả gốc mới của cây con, không cần parent.
#
# caller:
# root = insert(root, new_key)
```

Cách này không cần trường `parent`, tiết kiệm một tham chiếu mỗi nút và giảm một loại bất biến. Đổi lại, lời gọi cần quản lý đúng gốc cây con và ngăn xếp đệ quy. Không nên dùng lại nguyên hàm `rotate_right(root, pivot)` có `parent` ở ví dụ trên cho lớp nút không có trường `parent`; hai API minh họa **hai cách thiết kế khác nhau**.

### 9.2. Có nên tự cài phép quay trong ứng dụng?

Tự cài quay là bài luyện quan trọng để hiểu **tham chiếu, bất biến và phân tích O(h)**. Trong mã sản phẩm, nếu ngôn ngữ/thư viện đã có một ordered map hoặc cây cân bằng đáp ứng yêu cầu, thường nên ưu tiên cấu trúc đã được kiểm chứng. Các lỗi con trỏ cha, cập nhật gốc, cân bằng khi xóa, khóa trùng và tính nhất quán của chỉ mục rất khó phát hiện nếu chỉ thử vài trường hợp đơn giản.

## 10. Quy trình kiểm chứng một phép quay

Không chỉ kiểm tra rằng hàm không báo lỗi. Hãy kiểm tra **những tính chất đúng trước/sau**:

1. **Bất biến BST trước quay:** tất cả khóa trái nhỏ hơn và tất cả khóa phải lớn hơn trong mọi cây con.
2. **Tiền điều kiện:** quay trái cần con phải; quay phải cần con trái.
3. **Danh sách khóa inorder trước quay:** lưu để so sánh sau quay.
4. **Số nút và tập nút:** không mất, lặp hoặc tạo thêm nút.
5. **Quan hệ cha–con:** `child.parent is parent` nếu có lưu trường `parent`; gốc mới có `parent is None`.
6. **Chiều cao và metadata:** số lưu ở nút phải bằng giá trị tính lại từ cây con.
7. **Hình dạng và gốc mới:** nút con được đưa lên đúng vị trí, cây con giữa được chuyển đúng phía.
8. **Inorder sau quay:** dãy khóa **phải giống hoàn toàn** dãy trước.
9. **Cân bằng theo thuật toán áp dụng:** nếu mục tiêu là AVL/RB, kiểm tra thêm bất biến của **họ cây ấy**, không chỉ BST.
10. **Trường hợp biên:** cây rỗng, nút lá, quay gốc, quay cây con ở bên trái/phải của một cha, cây con giữa rỗng hoặc có nhiều nút.

Trong mã ví dụ, `validate` dùng `seen` để phát hiện một nút bị duyệt lặp, `parent` để kiểm tra cạnh ngược, cận khóa để kiểm tra bất biến BST và chiều cao tính lại để kiểm tra metadata. Những kiểm tra này có thể được dùng trong **bộ kiểm thử**; không nên chạy O(n) sau mọi thao tác trong ứng dụng có yêu cầu hiệu năng cao.

## 11. Những sai lầm thường gặp

- **“Quay trái là đổi chỗ hai khóa.”** Sai. Quay đổi **liên kết giữa nút**; khóa và giá trị gắn với từng nút giữ nguyên.
- **“Cây con giữa hai nút quay có thể bỏ đi.”** Sai. Cây con `B` phải chuyển sang phía phù hợp để không mất dữ liệu và vẫn đúng thứ tự.
- **“Quay trái được tại mọi nút.”** Sai. Cần có con phải; quay phải cần có con trái.
- **“Cứ quay xong là cây AVL.”** Sai. Phải chọn hướng quay dựa trên trạng thái cân bằng và kiểm tra tại các nút liên quan.
- **“Inorder không đổi nên chiều cao không đổi.”** Sai. Chính vì chiều cao có thể đổi nên phép quay mới được dùng để tái cân bằng.
- **“Nếu quay ở gốc cây không cần cập nhật `root`.”** Sai. Gốc cây con mới khác gốc cũ; ở gốc toàn cây phải thay biến `root`.
- **“Chỉ cần sửa `left`/`right`, `parent` tự đúng.”** Sai. Nếu có trường `parent`, phải cập nhật cả liên kết ngược và cha cũ.
- **“Chiều cao chỉ cần cập nhật ở nút đi lên.”** Sai. Cần tính lại nút đi xuống trước để chiều cao nút đi lên dùng dữ liệu đúng.
- **“Quay đơn O(1) nên chèn/xóa cây cân bằng O(1).”** Sai. Tìm vị trí và cập nhật dọc đường tới gốc tốn O(log n) với cây đã cân bằng.
- **“Quay phải tại nút cha luôn sửa được trường hợp LR.”** Sai. LR thường cần quay **trái ở con trái**, rồi **phải tại cha**.
- **“Quay có thể sửa việc so sánh khóa không bắc cầu.”** Sai. Cân bằng hình dạng không sửa được quy tắc thứ tự không hợp lệ.

## 12. Bài tập vận dụng

**Bài 1 — Vẽ quay trái.** Cho `x=20`, con phải `y=40`, cây con trái của `x` có khóa `10`, cây con giữa `B` có khóa `30` và cây con phải của `y` có khóa `50`. Vẽ trước/sau quay trái tại `20`. `30` phải nằm ở đâu sau quay?

*Gợi ý:* Sau quay, `40` là gốc cây con, `20` là con trái, và `30` trở thành **con phải của `20`**. Inorder vẫn `10, 20, 30, 40, 50`.

**Bài 2 — Vẽ quay phải.** Dùng hình của Bài 1 sau quay trái, hãy quay phải tại `40`. So sánh hình dạng cuối với hình ban đầu và giải thích quan hệ nghịch đảo.

*Gợi ý:* Quay phải đưa `20` lên lại, còn `30` chuyển về con trái của `40`. Nút và thứ tự inorder không đổi.

**Bài 3 — Tiền điều kiện.** Một nút `17` chỉ có con trái và không có con phải. Gọi `rotate_left` tại nút đó có hợp lệ không? Ứng dụng nên xử lý thế nào?

*Gợi ý:* Không hợp lệ. Nên thông báo lỗi/kiểm tra trước vì không có con phải để đưa lên.

**Bài 4 — Quay tại cây con.** Một gốc `60` có con trái `20`, và `20` có con phải `40`. Quay trái tại `20`. Gốc toàn cây có đổi không? Những tham chiếu `parent` nào cần sửa?

*Gợi ý:* Gốc toàn cây vẫn `60`, nhưng `60.left` đổi sang `40`; `40.parent=60`, `20.parent=40`, và cây con giữa chuyển về `20.right` nếu tồn tại.

**Bài 5 — Nhận diện LL/RR/LR/RL.** Lần lượt chèn `[30,20,10]`, `[10,20,30]`, `[30,10,20]` và `[10,30,20]` vào AVL rỗng. Cho biết dạng mất cân bằng và chuỗi phép quay tương ứng.

*Gợi ý:* LL → quay phải; RR → quay trái; LR → trái ở con rồi phải ở cha; RL → phải ở con rồi trái ở cha.

**Bài 6 — Chứng minh bằng inorder.** Với `A < x < B < y < C`, viết dãy inorder trước và sau quay trái tại `x`. Vì sao chứng minh này mạnh hơn việc chỉ thử năm khóa cụ thể?

*Gợi ý:* Cả hai cùng `in(A), x, in(B), y, in(C)`; lập luận áp dụng cho mọi cây con hợp lệ, không phụ thuộc kích thước ví dụ.

**Bài 7 — Phân tích Big O.** Một phép quay chỉ sửa số liên kết cố định, nhưng hàm minh họa lại gọi `update_ancestors`. Hãy phân biệt chi phí phần quay, cả lời gọi và một lần chèn AVL chuẩn.

*Gợi ý:* Phần thay liên kết O(1); lời gọi có cập nhật tổ tiên O(h); chèn AVL có đường tìm và cập nhật chiều cao O(log n) khi cây hợp lệ.

**Bài 8 — Bất biến bổ sung.** Nếu mỗi nút giữ `size` để tìm phần tử thứ k, sau quay trái tại `x` cần tính lại `size` của những nút nào? Những cây con nào có thể dùng lại số lượng cũ?

*Gợi ý:* Tính lại `size(x)` và `size(y)` theo các con sau quay; `A`, `B`, `C` không đổi cấu trúc nên metadata nội bộ của chúng vẫn dùng được.

**Bài 9 — Phân biệt cân bằng và thứ tự.** Một phép quay tạo cây có chiều cao nhỏ nhưng vô tình gắn `B` sang phía trái của `x` dù khóa trong `B` lớn hơn `x`. Cây có hợp lệ không?

*Gợi ý:* Không. Cân bằng hình dạng không có giá trị nếu phá bất biến BST; tìm kiếm có thể rẽ sai nhánh.

**Bài 10 — Kiểm thử biên.** Thiết kế ít nhất năm trường hợp kiểm thử cho hai hàm quay: quay gốc, quay giữa cây, cây con giữa có nút, thiếu con cần thiết, cập nhật chiều cao, kiểm tra `parent` và so sánh inorder.

*Gợi ý:* Đừng chỉ so sánh khóa gốc. Kiểm tra cả tập nút, cạnh ngược, metadata, thứ tự và tình trạng không có chu trình.

## Tổng kết

**Quay trái và quay phải** là những phép biến đổi **cục bộ, O(1) cho phần thay liên kết**, được dùng để điều chỉnh hình dạng cây tìm kiếm. Quay trái đưa **con phải** lên và chuyển cây con giữa sang phải của nút đi xuống; quay phải thực hiện đối xứng. Phép quay hợp lệ **không đổi khóa, không làm mất nút và giữ nguyên thứ tự duyệt inorder**, nên bảo toàn bất biến BST. Tuy nhiên, nó có thể thay đổi gốc cây con, độ sâu, chiều cao và các tham chiếu `parent`, vì thế mã cài đặt phải nối lại đúng cây cha và cập nhật metadata. Trong AVL, những trường hợp **LL/RR** dùng quay đơn, còn **LR/RL** dùng quay kép; trong Red–Black, phép quay được phối hợp với đổi màu. Hiểu đúng phép quay là nền tảng để xây các cây tìm kiếm **vừa đúng thứ tự, vừa kiểm soát được chiều cao và độ phức tạp thời gian/bộ nhớ**.
