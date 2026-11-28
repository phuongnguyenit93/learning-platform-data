# Xóa nút lá và nút chỉ có một con

Một ứng dụng lưu danh sách mã học viên bằng **cây tìm kiếm nhị phân** (*Binary Search Tree – BST*). Khi học viên thôi tham gia, hệ thống phải xóa mã của họ khỏi cây. Nghe có vẻ chỉ cần “bỏ nút tương ứng”, nhưng các nút còn liên kết với nhau: **xóa sai một liên kết có thể làm mất cả một cây con vẫn cần giữ**.

Tin tốt là có hai trường hợp xóa BST tương đối đơn giản: **nút lá** (không có con) và **nút chỉ có một con**. Với nút lá, ta gỡ liên kết từ cha tới nút đó. Với nút chỉ có một con, ta nối cha trực tiếp tới đứa con duy nhất, giữ nguyên cả cây con nằm phía dưới.

Bài thuộc chương **Cây tìm kiếm nhị phân** trong module cấu trúc dữ liệu. Mục tiêu là hiểu thật chắc **bất biến thứ tự BST**, cách xác định nút và nút cha, cách xử lý trường hợp **nút gốc**, và cách phân tích thời gian – bộ nhớ khi xóa. Trường hợp **nút có hai con** được nhắc tới để xác định ranh giới, nhưng không tự ý xử lý nó bằng quy tắc dành cho nút lá/một con.

## 1. Điều kiện tiên quyết: bất biến BST cần được giữ sau khi xóa

Với một BST chứa **các khóa phân biệt** và được so sánh bằng một thứ tự nhất quán, tại mỗi nút có khóa `k`:

- **Toàn bộ cây con trái** chỉ chứa các khóa nhỏ hơn `k`.
- **Toàn bộ cây con phải** chỉ chứa các khóa lớn hơn `k`.
- Hai cây con cũng thỏa cùng quy tắc tại mọi nút.

```text
                    50
                   /  \
                 30    70
                / \   /  \
               20 40 60   80
```

Ở gốc `50`, mọi khóa phía trái (`20,30,40`) đều nhỏ hơn `50`; mọi khóa phía phải (`60,70,80`) đều lớn hơn `50`.

**Xóa đúng** phải bảo đảm hai điều:

1. Khóa được yêu cầu xóa **không còn xuất hiện** trong BST; mọi khóa khác vẫn tồn tại chính xác như chính sách tập hợp/ánh xạ đã quy định.
2. **Bất biến thứ tự trên toàn bộ cây con** tiếp tục đúng, để các thao tác tìm kiếm, chèn và duyệt in-order vẫn hoạt động chính xác.

Nếu BST là một **map**, mỗi nút còn có `value`. Xóa theo `key` sẽ loại luôn ánh xạ `key → value`. Chúng ta không quyết định hướng rẽ bằng giá trị `value`.

### Tại sao không thể chỉ “gán nút bằng None”?

Giả sử biến cục bộ `current` trỏ tới nút `20`:

```python
current = None
```

Việc này chỉ đổi **biến cục bộ `current`**; liên kết `parent.left` trong cây vẫn giữ nguyên. Muốn gỡ nút khỏi cây, phải thực sự thay đổi **liên kết trỏ tới nó**, hoặc thay đổi **con trỏ gốc** khi đó chính là gốc.

Đó là lý do thuật toán xóa cần quản lý **vị trí liên kết của nút trong cây**, không chỉ tìm ra giá trị khóa.

## 2. Phân loại nút cần xóa theo số con

Nút BST có thể thuộc ba nhóm:

| Loại nút | Điều kiện | Hướng xử lý |
| --- | --- | --- |
| **Nút lá** | `left == None` và `right == None` | Gỡ nút khỏi liên kết của cha; hoặc đặt gốc rỗng |
| **Nút một con** | Chính xác một trong hai liên kết con khác `None` | Nối cha hoặc gốc trực tiếp tới đứa con ấy |
| **Nút hai con** | Cả `left` và `right` đều khác `None` | Cần thuật toán riêng, thường dùng successor/predecessor và xử lý liên kết |

Trong bài này, ta chỉ **thực thi xóa đối với hai nhóm đầu**. Nếu cần xóa nút có hai con, chương trình ví dụ sẽ chủ động **báo chưa hỗ trợ**, thay vì thực hiện thao tác có nguy cơ mất dữ liệu.

### Đếm số con, không đếm số hậu duệ

Ví dụ:

```text
     30
       \
        40
          \
           45
             \
              48
```

Nút `30` có **một con trực tiếp** (`40`), dù bên dưới nó còn ba nút hậu duệ. Vì thế `30` được xếp vào trường hợp **nút chỉ có một con**. Khi xóa `30`, phải giữ **toàn bộ cây con bắt đầu từ `40`**, không phải chỉ giữ riêng giá trị `40`.

## 3. Trường hợp thứ nhất: xóa nút lá

**Nút lá** không có con trái và cũng không có con phải.

Xét cây:

```text
Trước khi xóa 20:

        50
       /  \
     30    70
    /  \
   20  40

Sau khi xóa 20:

        50
       /  \
     30    70
       \
        40
```

Ta tìm `20` theo quy tắc BST:

```text
20 < 50 → rẽ trái tới 30
20 < 30 → rẽ trái tới 20
20 = 20 → tìm thấy
```

`20` là con **trái** của `30`, đồng thời `20.left == None` và `20.right == None`. Ta chỉ cần:

```text
parent.left = None
```

Nếu nút lá là **con phải** của cha, phải dùng `parent.right = None`. Không được đoán phía liên kết dựa trên việc vẽ cây hoặc luôn mặc định là bên trái.

### Vì sao xóa lá bảo toàn BST?

Nút lá không có hậu duệ. Gỡ nó chỉ làm **giảm một khóa** trong tập khóa của cây con nơi nó thuộc về; các nút còn lại không thay đổi thứ tự hay vị trí.

Không có nút nào được chuyển sang một nhánh không phù hợp, vì thế mọi bất biến “trái nhỏ hơn, phải lớn hơn” vốn đúng trước khi xóa vẫn đúng sau khi xóa.

**Bước đổi liên kết** là `O(1)`, nhưng **xóa theo khóa** vẫn phải tìm `20` trước. Với BST chiều cao `h`, tổng thời gian thường là `O(h)`.

## 4. Trường hợp thứ hai: nút chỉ có con trái

Xét nút `70` chỉ có một con trái `60`:

```text
Trước khi xóa 70:

        50
          \
           70
          /
         60
        /  \
       55  65

Sau khi xóa 70:

        50
          \
           60
          /  \
         55  65
```

Đứa con duy nhất của `70` là **gốc cả cây con `60`**, không chỉ là một giá trị đơn lẻ.

Khi `70` là con phải của `50`, phép nối lại cần làm là:

```text
parent.right = node.left
```

Ta đang thay liên kết từ `50` tới `70` bằng liên kết tới `60`. Hai nút `55` và `65` vẫn được giữ vì chúng là hậu duệ của `60`.

### Tại sao có thể nối trực tiếp lên trên?

Vì cây ban đầu là BST hợp lệ:

- Mọi khóa trong cây con của `70` đều **nhỏ hơn `70`**.
- Đồng thời toàn bộ cây con ấy đang ở nhánh phải của `50`, nên mọi khóa trong đó đều **lớn hơn `50`**.
- Chuyển liên kết từ `50.right` tới `60` **không thay đổi bất kỳ quan hệ tổ tiên–hậu duệ có ý nghĩa nào đối với các giới hạn khóa còn lại**.

Cụ thể, `55, 60, 65` đều nằm trong khoảng `(50, 70)` trước khi xóa. Sau khi bỏ giới hạn của nút `70`, chúng vẫn thỏa các giới hạn từ tổ tiên `50` và giữ nguyên thứ tự nội bộ.

**Không cần sao chép từng nút `55, 60, 65`.** Chỉ cần đổi một tham chiếu tới gốc cây con `60`.

## 5. Trường hợp thứ ba: nút chỉ có con phải

Quy tắc hoàn toàn đối xứng.

```text
Trước khi xóa 30:

            50
           /
          30
            \
             40
            /  \
           35  45

Sau khi xóa 30:

            50
           /
          40
         /  \
        35  45
```

Vì `30` là **con trái** của `50`, còn `40` là **con phải duy nhất** của `30`, thao tác nối lại là:

```text
parent.left = node.right
```

Tất cả khóa `35, 40, 45` đều nhỏ hơn `50`, nên thay liên kết không làm vi phạm bất biến. Cây con dưới `40` được giữ nguyên.

### Một nguyên tắc hợp nhất hai trường hợp

Với nút có **tối đa một con**, ta có thể lấy con còn tồn tại bằng:

```python
child = node.left if node.left is not None else node.right
```

Công thức này cho kết quả:

- Nút chỉ có con trái → `child = node.left`.
- Nút chỉ có con phải → `child = node.right`.
- Nút lá → `child = None`.

Nhờ vậy, **xóa nút lá và xóa nút một con có thể dùng chung một đoạn nối liên kết**. Điều kiện bắt buộc là phải **kiểm tra trước rằng nút không có hai con**; nếu cả hai con đều tồn tại mà tùy ý chọn một phía, cây con còn lại sẽ bị mất.

## 6. Trường hợp đặc biệt: chính nút gốc bị xóa

Nút cần xóa có thể không có **nút cha**. Khi ấy, thay vì cập nhật `parent.left` hoặc `parent.right`, ta phải cập nhật **gốc của cây**.

### Gốc cũng là nút lá

```text
Trước:     50

Xóa 50

Sau:      (cây rỗng)
```

Nếu chỉ có một nút gốc duy nhất, xóa nó làm:

```text
root = None
```

### Gốc chỉ có con phải

```text
Trước:

     50
       \
        70
       /  \
      60   80

Xóa 50:

     70
    /  \
   60   80
```

Gốc mới là `old_root.right`.

### Gốc chỉ có con trái

```text
Trước:

       50
      /
     30
    /  \
   20  40

Xóa 50:

       30
      /  \
     20  40
```

Gốc mới là `old_root.left`.

**Một lỗi rất phổ biến:** viết đúng trường hợp `parent.left = child` và `parent.right = child`, nhưng quên trường hợp `parent is None`. Kết quả là hàm có thể chạy đúng khi xóa nút sâu và **sai khi xóa gốc**.

## 7. Tìm nút và nút cha trước khi nối lại liên kết

Thuật toán xóa bắt đầu giống tìm kiếm BST:

1. Đặt `current = root`, `parent = None`.
2. Khi `current` tồn tại và chưa bằng khóa cần xóa:
   - Ghi `parent = current`.
   - Rẽ trái nếu khóa cần xóa nhỏ hơn `current.key`.
   - Rẽ phải nếu khóa cần xóa lớn hơn `current.key`.
3. Nếu gặp `None` thì khóa không tồn tại: **không sửa cây**.
4. Nếu tìm thấy, kiểm tra số con:
   - Hai con: thông báo **chưa hỗ trợ** trong bài.
   - Không quá một con: chọn `child`, sau đó cập nhật **đúng một liên kết** từ `parent` hoặc `root`.
5. Chỉ khi xóa thành công mới giảm biến đếm kích thước.

### Giả mã

```text
DELETE_ZERO_OR_ONE_CHILD(root, key):
    parent = null
    current = root

    while current != null and current.key != key:
        parent = current
        if key < current.key:
            current = current.left
        else:
            current = current.right

    if current == null:
        return (root, false)  // Khóa không tồn tại

    if current.left != null and current.right != null:
        error "nút có hai con chưa được hỗ trợ"

    child = current.left if current.left != null else current.right

    if parent == null:
        root = child
    else if parent.left is current:
        parent.left = child
    else:
        parent.right = child

    return (root, true)
```

Cụm `parent.left is current` kiểm tra **liên kết theo danh tính nút**, không phải phép bằng nhau về giá trị. Đây là cách quyết định phải cập nhật nhánh nào sau khi đã tìm đúng nút theo khóa.

## 8. Cài đặt Python lặp đầy đủ

Đoạn mã dưới đây tự chứa, dùng các khóa **số nguyên phân biệt**. Lớp `BST` có thêm, tra cứu, xóa nút lá/một con, duyệt in-order và đếm số nút.

### Định nghĩa nút và lớp BST

```python
class Node:
    def __init__(self, key, value=None):
        self.key = key
        self.value = value
        self.left = None
        self.right = None


class BST:
    def __init__(self):
        self.root = None
        self._size = 0

    def insert(self, key, value=None):
        """Trả True nếu thêm nút mới; False khi cập nhật khóa cũ."""
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
                    current.left = Node(key, value)
                    self._size += 1
                    return True
                current = current.left
            else:
                if current.right is None:
                    current.right = Node(key, value)
                    self._size += 1
                    return True
                current = current.right

    def find(self, key):
        """Trả (found, value), không nhầm value=None với khóa thiếu."""
        current = self.root

        while current is not None:
            if key == current.key:
                return True, current.value
            current = current.left if key < current.key else current.right

        return False, None

    def remove_zero_or_one(self, key):
        """Xóa khóa nếu nút có tối đa một con; trả True nếu đã xóa."""
        parent = None
        current = self.root

        # 1. Tìm nút và cha theo bất biến BST.
        while current is not None:
            if key == current.key:
                break

            parent = current
            current = current.left if key < current.key else current.right

        if current is None:
            return False

        # 2. Không xử lý nút hai con bằng công thức một con.
        if current.left is not None and current.right is not None:
            raise NotImplementedError(
                "Nút có hai con cần thuật toán xóa riêng"
            )

        # 3. Con duy nhất (hoặc None nếu là lá).
        child = current.left if current.left is not None else current.right

        # 4. Nối lại đúng liên kết từ cha hoặc thay gốc.
        if parent is None:
            self.root = child
        elif parent.left is current:
            parent.left = child
        else:
            parent.right = child

        self._size -= 1

        # 5. Tách nút cũ khỏi con mà nó từng trỏ tới.
        #    Cấu trúc cây còn sống vẫn nối đúng qua parent/root.
        current.left = None
        current.right = None
        return True

    def inorder(self):
        result = []
        pending = []
        current = self.root

        while pending or current is not None:
            while current is not None:
                pending.append(current)
                current = current.left

            current = pending.pop()
            result.append(current.key)
            current = current.right

        return result

    def size(self):
        return self._size
```

Hàm `remove_zero_or_one` có hợp đồng rõ ràng:

- Khóa không tồn tại → trả `False`, cây và `_size` không đổi.
- Nút có **0 hoặc 1 con** → xóa thành công, trả `True`, giảm `_size` đúng một lần.
- Nút có **2 con** → phát sinh `NotImplementedError` **trước khi thay đổi liên kết và biến đếm**.

Đây là **cài đặt học tập có phạm vi giới hạn**, chưa phải API xóa BST tổng quát. Không nên dùng nó để thay thế một thư viện cây tìm kiếm hoàn chỉnh.

### Kiểm thử xóa nút lá

```python
tree = BST()
for key in (50, 30, 70, 20, 40, 60, 80, 65):
    tree.insert(key, "value-" + str(key))

assert tree.inorder() == [20, 30, 40, 50, 60, 65, 70, 80]
assert tree.size() == 8

assert tree.remove_zero_or_one(20) is True
assert tree.inorder() == [30, 40, 50, 60, 65, 70, 80]
assert tree.find(20) == (False, None)
assert tree.size() == 7

assert tree.remove_zero_or_one(20) is False
assert tree.size() == 7
```

Khóa `20` ban đầu là nút lá; sau xóa không có khóa khác bị mất.

### Kiểm thử xóa nút có một con phải

Trong cây vừa tạo, `60` có con phải duy nhất `65`:

```text
     70
    /
   60
     \
      65
```

```python
assert tree.remove_zero_or_one(60) is True
assert tree.inorder() == [30, 40, 50, 65, 70, 80]
assert tree.find(65) == (True, "value-65")
assert tree.find(60) == (False, None)
assert tree.size() == 6
```

Sau xóa, `70.left` phải trỏ trực tiếp tới `65`. Giá trị gắn với khóa `65` cũng phải được giữ nguyên.

### Kiểm thử xóa nút có một con trái

Ta tạo cây khác:

```python
other = BST()
for key in (50, 30, 20, 70):
    other.insert(key)

# 30 có con trái 20, không có con phải.
assert other.remove_zero_or_one(30) is True
assert other.inorder() == [20, 50, 70]
assert other.root.left.key == 20
assert other.size() == 3
```

Lúc này `50.left` được chuyển từ `30` sang `20`, không có thao tác sao chép các nút còn lại.

## 9. Kiểm thử riêng việc xóa gốc

Xóa gốc là trường hợp cần được kiểm thử **độc lập**, vì không có nút cha để thay liên kết.

### Cây chỉ có một nút

```python
single = BST()
single.insert(50, "gốc duy nhất")

assert single.remove_zero_or_one(50) is True
assert single.root is None
assert single.size() == 0
assert single.inorder() == []
assert single.remove_zero_or_one(50) is False
```

### Gốc chỉ có con phải

```python
right_only = BST()
for key in (50, 70, 60, 80):
    right_only.insert(key)

assert right_only.remove_zero_or_one(50) is True
assert right_only.root.key == 70
assert right_only.inorder() == [60, 70, 80]
assert right_only.size() == 3
```

### Gốc chỉ có con trái

```python
left_only = BST()
for key in (50, 30, 20, 40):
    left_only.insert(key)

assert left_only.remove_zero_or_one(50) is True
assert left_only.root.key == 30
assert left_only.inorder() == [20, 30, 40]
assert left_only.size() == 3
```

**Điểm mấu chốt:** gốc mới không nhất thiết là một nút lá hoặc một nút vừa được tạo. Nó là **gốc của cây con còn sống**, cùng tất cả hậu duệ của cây con đó.

## 10. Phát hiện đúng nút có hai con và không xóa nhầm

Xét:

```text
      50
     /  \
    30   70
```

Nút `50` có **hai con**. Nếu áp dụng tùy tiện công thức:

```python
child = current.left if current.left is not None else current.right
```

rồi thay gốc bằng `child`, cả cây con phải `70` sẽ bị **mất khả năng truy cập từ gốc**. Ngược lại, chọn `current.right` sẽ làm mất `30`.

Vì vậy, kiểm tra `current.left is not None and current.right is not None` phải nằm **trước mọi bước nối liên kết**.

```python
two_children = BST()
for key in (50, 30, 70):
    two_children.insert(key)

before = two_children.inorder()
before_size = two_children.size()

try:
    two_children.remove_zero_or_one(50)
except NotImplementedError:
    pass
else:
    raise AssertionError("Phải từ chối nút có hai con")

assert two_children.inorder() == before
assert two_children.size() == before_size
```

Trong một **BST đầy đủ**, xóa nút hai con thường sử dụng **phần tử kế nhiệm theo thứ tự** (*in-order successor*, nhỏ nhất trong cây con phải) hoặc **tiền nhiệm** (*predecessor*, lớn nhất trong cây con trái), rồi xóa nút thay thế ở vị trí cũ. Quá trình đó cần một lời giải thích riêng, đặc biệt khi nút thay thế có một con. **Không gộp nó vào hai trường hợp đơn giản khi chưa bảo toàn đầy đủ liên kết và bất biến.**

## 11. Cài đặt đệ quy: trả gốc cây con mới

Có một cách biểu diễn rất gọn của thao tác xóa nút 0–1 con: mỗi lời gọi đệ quy trả về **gốc mới của cây con sau khi xóa** và một cờ thành công.

Với lớp `Node` đã định nghĩa ở trên:

```python
def delete_zero_or_one_recursive(root, key):
    """Trả (new_root, removed); lỗi nếu nút tìm thấy có hai con."""
    if root is None:
        return None, False

    if key < root.key:
        root.left, removed = delete_zero_or_one_recursive(
            root.left, key
        )
        return root, removed

    if key > root.key:
        root.right, removed = delete_zero_or_one_recursive(
            root.right, key
        )
        return root, removed

    # Đã gặp khóa cần xóa.
    if root.left is not None and root.right is not None:
        raise NotImplementedError("Nút có hai con cần thuật toán riêng")

    child = root.left if root.left is not None else root.right
    return child, True
```

Nếu xóa một nút lá, `child` là `None`, nên lời gọi cha nhận `None` cho đúng liên kết con. Nếu xóa nút một con, lời gọi cha nhận **gốc cây con còn lại**. Nếu xóa gốc, người gọi phải **nhận kết quả trả về** và cập nhật biến gốc.

### Ví dụ chạy với nút lá và một con

```python
recursive_tree = Node(50)
recursive_tree.left = Node(30)
recursive_tree.right = Node(70)
recursive_tree.left.left = Node(20)
recursive_tree.right.left = Node(60)

# Xóa lá 20.
recursive_tree, removed = delete_zero_or_one_recursive(
    recursive_tree, 20
)
assert removed is True
assert recursive_tree.left.left is None

# Xóa 70: chỉ còn con trái 60.
recursive_tree, removed = delete_zero_or_one_recursive(
    recursive_tree, 70
)
assert removed is True
assert recursive_tree.right.key == 60

# Khóa thiếu.
recursive_tree, removed = delete_zero_or_one_recursive(
    recursive_tree, 999
)
assert removed is False
```

### Bảo đảm không sửa cây khi gặp hai con

Trong phiên bản đệ quy, ngoại lệ được phát sinh **trước khi trả kết quả xóa tại nút có hai con**. Các lệnh gán `root.left, removed = ...` hoặc `root.right, removed = ...` ở tổ tiên chỉ diễn ra **sau khi lời gọi con trả về thành công**. Do đó ngoại lệ không làm các tổ tiên gán lại liên kết cho thao tác đang thất bại.

Tuy nhiên, cách chứng minh này dựa trên **mã cụ thể trong bài**. Một phiên bản khác có thao tác sửa trạng thái trước khi kiểm tra hai con có thể để lại cây đã biến đổi một phần.

### Khi nào nên dùng đệ quy?

Đệ quy làm rõ “xóa ở cây con rồi trả gốc cây con mới”, nhưng sử dụng **`O(h)` ngăn xếp lời gọi** và có thể vượt giới hạn đệ quy trên cây rất sâu. Bản lặp ở phần trên chỉ dùng **`O(1)` bộ nhớ phụ** cho các tham chiếu `current`, `parent` và `child`.

## 12. Bất biến sau thao tác và cách tự kiểm tra

Có thể tách việc xác minh một phép xóa thành ba câu hỏi:

**1. Khóa cần xóa đã thực sự biến mất chưa?**

```text
contains(deleted_key) == False
```

**2. Những khóa khác còn nguyên không?**

Có thể so tập khóa trước/sau xóa:

```text
after_keys == before_keys - {deleted_key}
```

**3. Thứ tự BST còn đúng trên mọi cây con không?**

Với khóa duy nhất, phép duyệt in-order phải cho một dãy **tăng nghiêm ngặt**; kiểm tra bằng giới hạn `low < key < high` trên toàn cây cũng là một cách trực tiếp.

### Ví dụ kiểm tra toàn cây bằng biên tổ tiên

Hàm dưới đây dành cho BST có **khóa nguyên**, dùng `None` để biểu thị không có biên:

```python
def valid_bst(root):
    pending = [(root, None, None)]

    while pending:
        node, low, high = pending.pop()
        if node is None:
            continue

        if low is not None and node.key <= low:
            return False
        if high is not None and node.key >= high:
            return False

        pending.append((node.left, low, node.key))
        pending.append((node.right, node.key, high))

    return True


assert valid_bst(tree.root) is True
assert valid_bst(other.root) is True
assert valid_bst(left_only.root) is True
assert valid_bst(right_only.root) is True
assert valid_bst(single.root) is True
```

Đây là **công cụ kiểm thử**, không phải thao tác cần chạy trước và sau **mọi lần xóa trong sản xuất**. Việc kiểm tra toàn cây tốn `O(n)`; nếu luôn thực hiện nó quanh mỗi lần xóa, tổng chi phí thao tác sẽ không còn chỉ `O(h)`.

### Vì sao chỉ kiểm tra in-order chưa đủ cho mọi lỗi?

Với một **cây nhị phân hữu hạn đúng cấu trúc** và khóa phân biệt được so sánh nhất quán, dãy in-order tăng nghiêm ngặt giúp kiểm tra tính thứ tự BST. Tuy nhiên, một đồ thị liên kết có **chu trình**, hoặc một nút được chia sẻ sai giữa hai nhánh, không còn là **cây** đúng nghĩa. Các hàm duyệt BST thông thường có thể lặp vô hạn hoặc xử lý sai khi gặp đầu vào như vậy. Khi kiểm thử các con trỏ tự cài, cần bảo đảm thêm **tính cấu trúc cây** nếu dữ liệu có thể không đáng tin cậy.

## 13. Độ phức tạp thời gian và bộ nhớ

Đặt `n` là số nút phân biệt trong cây và `h` là chiều cao BST, đo bằng số nút trên đường dài nhất từ gốc đến lá.

| Công việc | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| Tìm nút cần xóa theo khóa | `O(h)` | Bản lặp `O(1)` |
| Nhận diện nút lá/một con khi đã tìm thấy | `O(1)` | `O(1)` |
| Chọn `child` và đổi một liên kết cha/gốc | `O(1)` | `O(1)` |
| Toàn bộ xóa thành công theo khóa bằng bản lặp | `O(h)` | `O(1)` |
| Xóa bằng bản đệ quy | `O(h)` | `O(h)` cho call stack |
| Kiểm tra lại toàn bộ BST | `O(n)` | `O(h)` với DFS |
| Duyệt hết cây để xuất danh sách khóa | `O(n)` | `O(n)` nếu lưu danh sách |

**Ghi chú:** các mốc trên coi so sánh khóa và cập nhật tham chiếu có chi phí cơ bản hằng số. Với khóa chuỗi dài hoặc comparator phức tạp, chi phí một lần so sánh có thể tăng theo độ dài khóa.

### Khi BST cân bằng và khi BST lệch

- BST cân bằng có `h = O(log n)`, nên xóa bằng cách tìm nút rồi nối lại liên kết có thể đạt `O(log n)`.
- BST không tự cân bằng có thể có `h = O(n)` khi lệch, nên xóa theo khóa có thể mất `O(n)`.
- Một cây **tự cân bằng** như AVL hoặc cây đỏ–đen còn có các bước cập nhật thông tin cân bằng và có thể quay cây **sau khi xóa**. Hai đoạn mã trong bài chỉ bảo toàn **thứ tự BST**, không tự duy trì các điều kiện cân bằng bổ sung của AVL/đỏ–đen.

### Bỏ nút không nhất thiết giải phóng bộ nhớ ngay lập tức

Trong Python, sau khi xóa khỏi cây, đối tượng nút cũ có thể còn được biến khác tham chiếu tới, nên không thể khẳng định bộ nhớ được trả lại ngay lập tức. Việc tách `current.left` / `current.right` trong mã lặp giúp bỏ các tham chiếu cũ từ nút đã xóa tới cây con; nó **không thay thế cơ chế quản lý bộ nhớ** của ngôn ngữ.

Trong C/C++, nếu cài bằng con trỏ sở hữu bộ nhớ, cần quy định rõ thao tác giải phóng nút để không **rò rỉ bộ nhớ** và không làm mất những nút con vẫn được giữ. Nếu hệ thống có thêm `parent pointer`, phải cập nhật nó khi nối con lên vị trí cha cũ.

## 14. So sánh trường hợp lá và một con

| Tiêu chí | Xóa nút lá | Xóa nút một con |
| --- | --- | --- |
| Số con trực tiếp của nút | `0` | `1` |
| `child` dùng thay thế | `None` | Gốc của cây con duy nhất |
| Cập nhật tại cha | Đặt liên kết tới nút bị xóa bằng `None` | Trỏ liên kết tới `child` |
| Nếu xóa gốc | `root = None` | `root = child` |
| Có phải chuyển từng hậu duệ? | Không có hậu duệ | **Không**, giữ nguyên toàn bộ cây con |
| Chi phí nối liên kết | `O(1)` | `O(1)` |
| Tổng chi phí xóa theo khóa | `O(h)` | `O(h)` |

Hai trường hợp có thể hợp nhất bằng phép nối `parent_link = child`, nhưng vẫn cần xác định **liên kết thật** được thay và kiểm tra **không có hai con**.

## 15. Các lỗi thường gặp

1. **Chỉ gán `current = None`:** đổi biến cục bộ, không gỡ liên kết trong cây.
2. **Gán `parent.left = None` cho mọi nút lá:** nếu nút là con phải, sẽ xóa nhầm hoặc không xóa gì.
3. **Quên xử lý `parent is None`:** không cập nhật gốc khi xóa chính nút gốc.
4. **Xóa nút một con nhưng đặt liên kết cha bằng `None`:** làm mất toàn bộ cây con vẫn cần giữ.
5. **Chỉ sao chép giá trị của con lên cha mà không xử lý liên kết:** có thể tạo trùng khóa hoặc cấu trúc sai.
6. **Dùng công thức một con để xóa nút hai con:** đánh rơi một nhánh và mất dữ liệu.
7. **Giảm `size` trước khi kiểm tra khóa có tồn tại không:** kích thước sai sau một thao tác xóa thất bại.
8. **Giảm `size` cả khi phát sinh lỗi “hai con chưa hỗ trợ”:** vi phạm hợp đồng lỗi không làm thay đổi cây.
9. **Nhầm khóa với giá trị dữ liệu:** phải tìm bằng `key`, không phải `value`.
10. **Nhầm `value=None` với khóa không tồn tại:** một tree map có thể lưu giá trị `None` hợp lệ.
11. **Dùng phép bằng nhau không nhất quán với phép thứ tự:** đường tìm có thể bỏ qua nút cần xóa.
12. **Sửa `key` của nút trước khi nối cây:** có thể phá bất biến thứ tự.
13. **Quên cập nhật trường `parent` nếu cấu trúc có liên kết cha:** các thao tác kế nhiệm và đi ngược tổ tiên có thể sai.
14. **Giả định BST tự cân bằng sau xóa:** một BST thường không duy trì chiều cao logarit.
15. **Tin một phép xóa đã thành công mà không kiểm thử nút lá/gốc/một con riêng:** lỗi liên kết thường chỉ lộ ra ở một hình dạng cây nhất định.
16. **Không xét đồng thời:** nếu nhiều luồng thay liên kết của cây không có đồng bộ, các thao tác tìm/chèn/xóa có thể quan sát trạng thái không nhất quán.

## 16. Thực hành: kiểm thử đối chiếu với tập khóa tham chiếu

Một cách kiểm thử dễ hiểu là dùng **Python `set`** làm mô hình tập khóa và đối chiếu kết quả in-order của BST.

Mục đích ở đây là kiểm tra **tính đúng**, không phải đo hiệu năng:

```python
case = BST()
reference = set()

for key in (50, 30, 70, 20, 40, 60, 80, 65):
    case.insert(key)
    reference.add(key)

assert case.inorder() == sorted(reference)

# Nút lá.
assert case.remove_zero_or_one(20) is True
reference.remove(20)
assert case.inorder() == sorted(reference)

# Nút một con (60 chỉ có con phải 65).
assert case.remove_zero_or_one(60) is True
reference.remove(60)
assert case.inorder() == sorted(reference)

# Một nút lá khác.
assert case.remove_zero_or_one(40) is True
reference.remove(40)
assert case.inorder() == sorted(reference)

# Khóa không tồn tại.
assert case.remove_zero_or_one(12345) is False
assert case.inorder() == sorted(reference)

assert case.size() == len(reference)
assert valid_bst(case.root)
```

Với dữ liệu nhỏ, `sorted(reference)` là một **đáp án độc lập** để phát hiện việc mất nhầm cây con, thêm trùng hoặc đổi sai thứ tự.

### Bộ tình huống nên tự bổ sung

- Xóa lá bên **trái** và lá bên **phải**.
- Xóa nút có **một con trái** và có **một con phải**.
- Xóa **gốc rỗng sau thao tác**, gốc một con trái và gốc một con phải.
- Xóa **khóa vắng mặt**, lặp lại xóa cùng khóa.
- Gặp **nút hai con**: xác nhận lỗi và cây không bị biến đổi.
- Xóa nút một con mà đứa con ấy có **cây con nhiều tầng**: kiểm tra mọi hậu duệ còn tồn tại.
- Sau một chuỗi xóa, kiểm tra `size`, `find`, `inorder` và bất biến BST.

## 17. Ứng dụng: xóa hồ sơ theo mã mà không mất hồ sơ khác

Giả sử nền tảng lưu các khóa học theo `course_id` trong một tree map:

```text
       CS200
      /     \
   CS100   CS300
              \
              CS350
```

Nếu phải xóa `CS300`, nút ấy có **một con phải** `CS350`. Kết quả mong muốn là:

```text
       CS200
      /     \
   CS100   CS350
```

Bản ghi `CS350` phải còn được tìm thấy với **đúng giá trị đi kèm**, không chỉ còn mã. Việc này quan trọng khi BST lưu cặp `(key,value)`, chẳng hạn `course_id → lesson_details`.

Nếu xóa `CS100` (một nút lá), chỉ liên kết `CS200.left` bị gỡ. Nếu xóa `CS200` ngay khi nó có **hai con**, ta cần thuật toán khác, không thể áp dụng công thức “nối cha với con duy nhất”.

**Lựa chọn cấu trúc:** BST tự cài phù hợp để học bất biến và chi phí. Trong phần mềm sản xuất, nếu cần một map có thứ tự cùng thao tác xóa đầy đủ, nên cân nhắc cấu trúc cây cân bằng/thư viện đã kiểm thử thay vì chỉ dùng bài minh họa này.

## 18. Tự luyện tập

**Bài 1.** Với BST:

```text
      50
     /  \
    30   70
   /
  20
```

Khi xóa `20`, đó là trường hợp nào? Cần thay liên kết nào?

**Bài 2.** Xét nút `30` trong cây của bài 1. Nếu xóa `30` sau khi `20` vẫn còn, cần nối lại liên kết nào? Gốc cây có đổi không?

**Bài 3.** BST có gốc `50` và cây con phải bắt đầu từ `70` với các con `60`, `80`. Xóa `50` tạo gốc mới là gì? Có phải sao chép từng nút `60`, `80` không?

**Bài 4.** Một nút có một con trái; nút con ấy lại có hai con. Nút ban đầu được xem là “một con” hay “nhiều con”? Giải thích thao tác xóa đúng.

**Bài 5.** Trong mã Python, vì sao `current = None` không đủ để xóa một nút? Nêu các trường hợp cần cập nhật `parent.left`, `parent.right` hoặc `root`.

**Bài 6.** Nếu khóa cần xóa **không tồn tại**, giá trị trả về và biến `size` phải như thế nào trong hợp đồng của bài?

**Bài 7.** Vì sao cần kiểm tra `current.left` và `current.right` trước khi chọn `child`? Nêu hậu quả nếu xóa nút hai con bằng quy tắc một con.

**Bài 8.** Với cây được chèn theo `[50, 30, 70, 20, 40, 60, 80, 65]`, hãy lần lượt xóa `20` rồi `60`. Viết dãy in-order sau mỗi thao tác.

**Bài 9.** So sánh độ phức tạp **tìm theo khóa** và **nối lại liên kết** khi xóa nút lá hoặc một con trên BST chiều cao `h`. Điều gì thay đổi khi cây lệch?

**Bài 10.** Với hàm đệ quy `delete_zero_or_one_recursive`, vì sao bắt buộc phải gán lại `root` từ giá trị trả về khi xóa gốc?

**Bài 11.** Nếu cấu trúc nút có thêm trường `parent`, sau khi thay liên kết của cha bằng `child`, cần đồng bộ thông tin gì?

**Bài 12.** Viết kiểm thử cho ba trường hợp: (a) xóa nút lá là con phải, (b) xóa gốc chỉ có con trái, (c) cố xóa nút hai con phải báo lỗi mà cây không thay đổi.

<details>
<summary>Đáp án và gợi ý</summary>

1. `20` là nút lá, con trái của `30`; thực hiện `30.left = None`.
2. `30` chỉ có con trái `20`, nên nối `50.left = 20`. Gốc vẫn là `50`.
3. Gốc mới là `70`; các cây con dưới `70` còn nguyên, không cần sao chép từng nút.
4. Nút ban đầu vẫn **chỉ có một con trực tiếp**. Nối cha/gốc tới gốc cây con ấy, giữ nguyên mọi hậu duệ.
5. `current = None` chỉ thay đổi biến cục bộ. Nếu nút là con trái thì `parent.left = child`; con phải thì `parent.right = child`; nếu là gốc thì `root = child`.
6. Trả `False`; `size` không đổi, mọi liên kết và dữ liệu không đổi.
7. Nếu có hai con, việc chọn một con sẽ đánh mất nhánh kia. Phải chuyển sang thuật toán xóa hai con.
8. Sau xóa `20`: `[30,40,50,60,65,70,80]`; sau xóa `60`: `[30,40,50,65,70,80]`.
9. Tìm theo khóa `O(h)`, nối liên kết sau khi tìm được nút `O(1)`, tổng `O(h)`. BST cân bằng có `h=O(log n)`, cây lệch có thể `h=O(n)`.
10. Hàm trả **gốc cây con mới**; khi xóa gốc, chính `root` có thể phải đổi thành con duy nhất hoặc `None`.
11. Nếu có `child`, cần gán `child.parent = parent`; nếu `child` thành gốc mới, `child.parent = None`; phải bảo đảm liên kết hai chiều nhất quán.
12. Ví dụ:

```python
# a) Xóa lá là con phải.
a = BST()
for k in (50, 30, 70):
    a.insert(k)
assert a.remove_zero_or_one(70)
assert a.inorder() == [30, 50]

# b) Xóa gốc có đúng một con trái.
b = BST()
for k in (50, 30, 20):
    b.insert(k)
assert b.remove_zero_or_one(50)
assert b.root.key == 30
assert b.inorder() == [20, 30]

# c) Hai con không hỗ trợ và không sửa cây.
c = BST()
for k in (50, 30, 70):
    c.insert(k)
old = c.inorder()
try:
    c.remove_zero_or_one(50)
except NotImplementedError:
    pass
else:
    raise AssertionError("Phải báo lỗi với nút hai con")
assert c.inorder() == old
assert c.size() == len(old)
```

</details>

## Ghi nhớ

**Xóa BST theo khóa gồm hai phần:** tìm đúng nút/cha trong **`O(h)`**, rồi sửa một liên kết trong **`O(1)`** nếu nút có **0 hoặc 1 con**. Với **nút lá**, liên kết cha (hoặc gốc) được thay bằng `None`. Với **nút một con**, liên kết ấy được thay bằng **gốc cây con duy nhất**, giữ nguyên mọi hậu duệ. Luôn xử lý riêng **nút gốc**, không giảm kích thước khi khóa thiếu hoặc thao tác thất bại, và **không dùng công thức một con cho nút hai con**. Cây còn lại phải giữ đầy đủ các khóa khác và bất biến **mọi khóa trái nhỏ hơn – mọi khóa phải lớn hơn**; tổng chi phí có thể `O(log n)` khi cây cân bằng hoặc `O(n)` khi BST lệch.
