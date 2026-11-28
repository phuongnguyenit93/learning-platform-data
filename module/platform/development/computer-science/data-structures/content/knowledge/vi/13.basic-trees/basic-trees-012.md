# Phân biệt cây biểu diễn dữ liệu với cây tìm kiếm và heap

## 1. Cùng là cây, vì sao cách sử dụng khác nhau?

Trong môn **Cấu trúc dữ liệu**, cây (*tree*) là một mô hình các nút được liên kết theo quan hệ phân cấp. Ta gặp cây khi biểu diễn thư mục và tài liệu, tổ chức danh mục, lưu biểu thức, tra cứu dữ liệu có thứ tự hoặc quản lý công việc theo mức ưu tiên.

Tuy cùng có **gốc**, **nút cha**, **nút con**, **lá** và **cây con**, ba nhóm cấu trúc sau hướng tới các yêu cầu rất khác nhau:

1. **Cây biểu diễn dữ liệu (hierarchical/data tree):** giữ **ý nghĩa của quan hệ cha–con** trong dữ liệu.
2. **Cây tìm kiếm (search tree):** duy trì **bất biến sắp xếp hoặc phân vùng khóa** để tra cứu, chèn, xóa theo khóa hiệu quả.
3. **Heap (đống):** duy trì **bất biến ưu tiên cha–con** để lấy phần tử có mức ưu tiên cao nhất hoặc thấp nhất nhanh chóng.

Bài này lấy **cây tìm kiếm nhị phân (Binary Search Tree — BST)** và **heap nhị phân (binary heap)** làm hai đại diện cụ thể. “Cây tìm kiếm” còn có những dạng khác như B-tree hoặc B+ tree; “heap” cũng có nhiều biến thể. Những công thức và thuật toán riêng cho BST/heap nhị phân dưới đây **không được áp dụng máy móc cho mọi biến thể**.

Câu hỏi định hướng là:

- Nếu cần giữ một **sơ đồ chương–bài học**, liệu có phải sắp các chương theo khóa tăng dần như BST?
- Nếu cần tìm một **mã số cụ thể**, cây nhị phân bất kỳ có bảo đảm tìm nhanh không?
- Nếu cần liên tục chọn **công việc có ưu tiên nhỏ nhất**, BST và heap có lợi thế gì khác nhau?
- Vì sao **heap không phải BST**, dù cả hai có thể được vẽ thành một cây nhị phân?

Mục tiêu là biết **bất biến phải duy trì**, **phép toán được tối ưu** và **độ phức tạp thời gian–bộ nhớ** để chọn đúng cấu trúc cho từng bài toán.

## 2. Điểm chung: cấu trúc cây và các bất biến nền

Một **cây có gốc (rooted tree)** không rỗng có:

- Đúng **một gốc**, không có cha.
- Mỗi nút khác gốc có **đúng một cha trực tiếp**.
- Mọi nút có thể đi tới từ gốc theo các cạnh cha–con.
- Không có chu trình cha–con.
- Nếu có `n` nút thì có **`n-1` cạnh**.

**Cây tổng quát** cho phép một nút có nhiều con. **Cây nhị phân** giới hạn mỗi nút tối đa **hai vị trí con phân biệt: trái và phải**. Trường hợp một vị trí con rỗng vẫn hợp lệ.

Giả sử cây có gốc `r`, nút `u`:

- **Độ sâu** `depth(u)` là số cạnh từ `r` đến `u`.
- **Chiều cao của nút** `height(u)` là số cạnh trên đường dài nhất từ `u` xuống một lá trong cây con.
- **Chiều cao cây** `h=height(r)`.
- Theo quy ước bài này, gốc có depth `0` và lá có height `0`; cây rỗng được xử lý riêng.

Những quan hệ trên **chưa quyết định** liệu cây dùng để lưu phân cấp, tra cứu hay quản lý ưu tiên. Sự khác biệt nằm ở **bất biến bổ sung**.

### Ba loại bất biến cần tách bạch

| Loại bất biến | Câu hỏi được bảo đảm | Ví dụ |
|---|---|---|
| **Cấu trúc cây** | Có đúng một cha cho mỗi nút không phải gốc, không chu trình? | Cả ba nhóm |
| **Bất biến giá trị/khóa** | Khóa trong các cây con nằm về phía nào so với khóa nút cha? | BST |
| **Bất biến ưu tiên** | Cha có ưu tiên không lớn hơn/không nhỏ hơn con? | Min-heap/max-heap |
| **Bất biến hình dạng** | Những vị trí mức nào phải được lấp đầy? | Binary heap thông thường phải complete |

**Lưu ý:** cây biểu diễn dữ liệu có thể có thêm ràng buộc nghiệp vụ riêng, chẳng hạn một tài liệu chỉ thuộc một thư mục hoặc các mục con phải được hiển thị theo thứ tự. Nhưng ràng buộc đó **không tự động là bất biến BST hay heap**.

## 3. Cây biểu diễn dữ liệu: bảo toàn quan hệ phân cấp

### 3.1. Mục tiêu và ví dụ

Cây biểu diễn dữ liệu dùng quan hệ cha–con để thể hiện ý nghĩa như “chứa”, “thuộc về”, “được phân rã thành” hoặc “có các thành phần”.

```text
                     Học phần CTDL
                    /      |      \
                 Mảng     Cây     Đồ thị
                 / \      / \       |
             Tĩnh  Động  BST Heap  BFS/DFS
```

Ở đây:

- “Cây” là một **chương**, có các mục “BST” và “Heap”.
- “BST” và “Heap” trong sơ đồ là **tên bài học** chứ không phải phép tổ chức giá trị của các nút trong chính cây mục lục.
- Đặt “Đồ thị” sang trái hay phải “Mảng” **không cần tuân theo quan hệ nhỏ hơn/lớn hơn về khóa**.
- Một nút như “Học phần CTDL” có **ba con** nên đây là cây tổng quát, không phải cây nhị phân theo quan hệ hiển thị.

Mục tiêu chính là **trả lời các câu hỏi về cấu trúc phân cấp**:

- Một chương có những bài nào?
- Cha của một bài là chương nào?
- Từ gốc đến bài này đi qua những mục nào?
- Một chương có bao nhiêu hậu duệ?
- Duyệt các mục theo đúng thứ tự đã tổ chức ra sao?

### 3.2. Bất biến và thứ tự

Đối với một cây phân cấp có gốc:

1. Mỗi đối tượng không phải gốc thuộc về **đúng một cha trực tiếp**, nếu mô hình thật sự là cây.
2. Không có chu trình.
3. Nếu là **cây có thứ tự**, thứ tự các con là một phần của dữ liệu: `[Mảng, Cây, Đồ thị]` có thể khác `[Đồ thị, Mảng, Cây]`.
4. Nếu cần giữ liên kết hai chiều, mỗi quan hệ `u.children` chứa `v` phải tương ứng với `v.parent = u`.

Không có điều kiện bắt buộc kiểu “mọi nút bên trái có mã nhỏ hơn gốc”. Các nút có nhãn/giá trị trùng nhau vẫn có thể là các **đối tượng riêng**, miễn quan hệ của chúng hợp lệ.

**Cây dữ liệu không nhất thiết là cây tổng quát.** Một cây cú pháp gồm toán tử nhị phân và các toán hạng có thể là cây nhị phân; mục đích của nó vẫn là **biểu diễn cấu trúc biểu thức**, không phải để tra cứu như BST. Phân loại theo **mục đích/bất biến** khác với phân loại theo **số con tối đa**.

### 3.3. Biểu diễn trong bộ nhớ

Có hai phương án quen thuộc:

```text
Nút tổng quát:
    value
    parent       (tùy chọn)
    children[]   (danh sách con)

Nút nhị phân mang dữ liệu:
    value
    left
    right
```

Nếu lưu danh sách con và một liên kết cha tùy chọn, bộ nhớ của các nút/cạnh là **`O(n)`** cho cây `n` nút.

**Ưu điểm:** đi xuống các cây con, đi lên tổ tiên và hiển thị phân cấp tự nhiên. **Giới hạn:** không có thứ tự khóa để loại bỏ nửa cây khi tìm một nhãn tùy ý; tìm kiếm có thể phải duyệt toàn bộ `n` nút.

### 3.4. Python: tạo cây danh mục và tìm một nhãn

```python
class DataNode:
    def __init__(self, label):
        self.label = label
        self.parent = None
        self.children = []

    def add_child(self, child):
        if not isinstance(child, DataNode):
            raise TypeError("child phải là DataNode")

        if child.parent is not None:
            raise ValueError("child đã có cha")

        # Kiểm tra không gắn một tổ tiên xuống dưới hậu duệ.
        cursor = self
        while cursor is not None:
            if cursor is child:
                raise ValueError("thao tác tạo chu trình")
            cursor = cursor.parent

        self.children.append(child)
        child.parent = self


def find_label_dfs(root, target):
    """Trả về nút đầu tiên có nhãn target theo DFS preorder."""
    if root is None:
        return None

    stack = [root]

    while stack:
        node = stack.pop()
        if node.label == target:
            return node

        # Push ngược để xử lý con theo thứ tự danh sách.
        for child in reversed(node.children):
            stack.append(child)

    return None


course = DataNode("Học phần CTDL")
arrays = DataNode("Mảng")
trees = DataNode("Cây")
graphs = DataNode("Đồ thị")

course.add_child(arrays)
course.add_child(trees)
course.add_child(graphs)

trees.add_child(DataNode("BST"))
trees.add_child(DataNode("Heap"))

found = find_label_dfs(course, "Heap")
print(found.label)         # Heap
print(found.parent.label)  # Cây

missing = find_label_dfs(course, "Hash table")
print(missing)             # None
```

**Giải thích độ phức tạp:**

- Truy cập cha từ nút đã biết: **`O(1)`** nếu có trường `parent`.
- Liệt kê `k` con: **`O(k)`** thời gian.
- Tìm một nhãn bằng DFS: **`O(n)` thời gian trường hợp xấu nhất**, vì nhãn có thể nằm ở nút cuối hoặc không tồn tại.
- Stack DFS: có thể cần **`O(n)` bộ nhớ phụ** trên cây tổng quát rất rộng; phụ thuộc hình dạng. Không tính bộ nhớ đã dùng để lưu các nút.

Nếu tra cứu nhãn/mã thường xuyên, có thể thêm **chỉ mục ánh xạ mã → nút**; khi đó truy vấn mã có thể nhanh hơn, nhưng chỉ mục là **cấu trúc phụ bổ sung**, phải được duy trì khi thêm, xóa hoặc đổi mã. Nó không làm cây phân cấp tự trở thành BST.

## 4. Cây tìm kiếm: bất biến khóa giúp quyết định đường đi

### 4.1. “Cây tìm kiếm” là một họ cấu trúc

Một **cây tìm kiếm (search tree)** được thiết kế để hỗ trợ truy vấn khóa: tìm đúng khóa, chèn, xóa, tìm tiền nhiệm/kế nhiệm hoặc duyệt theo thứ tự khóa.

Ở đây dùng **BST — cây tìm kiếm nhị phân** làm ví dụ cơ bản:

> Với mỗi nút có khóa `k`, **mọi khóa trong toàn bộ cây con trái** đều nhỏ hơn `k`; **mọi khóa trong toàn bộ cây con phải** đều lớn hơn `k`.

Bài này chọn chính sách **không cho khóa trùng**, để sử dụng bất đẳng thức **nghiêm ngặt**. BST thực tế có thể lưu số lần xuất hiện hoặc có quy tắc xử lý khóa trùng khác; khi đó bất biến và mã kiểm tra phải được điều chỉnh tương ứng.

### 4.2. Ví dụ BST

Dùng các khóa số phân biệt `2,4,6,8,10,12,14`:

```text
                  8
                /   \
               4     12
              / \   /  \
             2   6 10  14

Bên trái 8:   2, 4, 6  < 8
Bên phải 8:  10,12,14  > 8
Bên trái 12: 10        < 12
Bên phải 12: 14        > 12
```

Với BST này, để tìm khóa `10`:

1. So `10` với `8`. Vì `10 > 8`, **chỉ đi sang phải**.
2. So `10` với `12`. Vì `10 < 12`, **chỉ đi sang trái**.
3. Tới nút `10`, trả kết quả.

Không cần thăm cây con trái của `8`, bởi bất biến bảo đảm tất cả khóa ở đó **nhỏ hơn `8`**, không thể chứa `10`.

### 4.3. Bất biến xét **toàn bộ cây con**, không chỉ con trực tiếp

Một lỗi phổ biến là chỉ kiểm tra `left.key < node.key < right.key` ở từng nút.

Xét:

```text
          8
         /
        4
         \
         10   ← Vi phạm BST: 10 nằm trong toàn bộ cây con TRÁI của 8
```

Quan hệ giữa nút `4` và con phải `10` thỏa `4<10`; quan hệ giữa `8` và con trái `4` thỏa `4<8`. Nhưng **nút `10` phải nhỏ hơn `8`** vì nó thuộc cây con trái của `8`. Vậy đây **không phải BST**.

Cách xác thực đúng phải mang theo **giới hạn khóa hợp lệ do tất cả tổ tiên áp đặt**.

### 4.4. Thứ tự duyệt inorder của BST

Duyệt **trung thứ tự (inorder)** theo trình tự:

```text
Cây con trái → Nút hiện tại → Cây con phải
```

Với BST có khóa phân biệt và bất biến nghiêm ngặt, kết quả là một dãy **tăng dần**:

```text
2, 4, 6, 8, 10, 12, 14
```

Đây là khác biệt quan trọng so với cây phân cấp thông thường và heap: **inorder của một cây nhị phân bất kỳ không được bảo đảm sắp xếp**.

### 4.5. Chiều cao quyết định hiệu năng

Gọi `h` là chiều cao BST theo số cạnh.

- Mỗi bước tìm kiếm chỉ chọn **một cây con**, nên tìm kiếm **`O(h+1)` thời gian**.
- Chèn theo khóa và xóa theo quy tắc BST cũng thường mất **`O(h+1)`** cho quá trình tìm vị trí (chưa tính các chi tiết tái cân bằng).
- Nếu BST **cân bằng** như AVL hoặc Red–Black Tree, chiều cao được kiểm soát `O(\log n)`, nên các thao tác tìm/chèn/xóa được bảo đảm hoặc duy trì trong **`O(\log n)`** với thuật toán tương ứng.
- Nếu BST **không cân bằng**, chiều cao có thể đạt `n-1`, khiến tìm kiếm/chèn/xóa suy giảm tới **`O(n)`**.

Ví dụ, chèn tuần tự `2,4,6,8,10` vào BST cơ bản ban đầu rỗng:

```text
2
 \
  4
   \
    6
     \
      8
       \
        10
```

Đây **vẫn là BST hợp lệ**, nhưng là cây suy biến và cao `4` cạnh. Vì vậy không được khẳng định “BST luôn tìm `O(\log n)`” nếu không nói rõ cân bằng hoặc giả thiết về hình dạng.

## 5. Python: BST không cân bằng, tìm kiếm và duyệt có thứ tự

Ví dụ sau dùng các khóa số nguyên, **không nhận khóa trùng**, để bất biến và kết quả dễ kiểm tra.

```python
class BSTNode:
    def __init__(self, key):
        self.key = key
        self.left = None
        self.right = None


class BST:
    def __init__(self):
        self.root = None

    def insert(self, key):
        """Chèn khóa; trả False nếu khóa đã tồn tại."""
        if self.root is None:
            self.root = BSTNode(key)
            return True

        cursor = self.root

        while True:
            if key == cursor.key:
                return False

            if key < cursor.key:
                if cursor.left is None:
                    cursor.left = BSTNode(key)
                    return True
                cursor = cursor.left
            else:
                if cursor.right is None:
                    cursor.right = BSTNode(key)
                    return True
                cursor = cursor.right

    def find(self, key):
        """Trả nút có khóa key, hoặc None."""
        cursor = self.root

        while cursor is not None:
            if key == cursor.key:
                return cursor

            if key < cursor.key:
                cursor = cursor.left
            else:
                cursor = cursor.right

        return None

    def inorder(self):
        """Trả danh sách khóa tăng dần, không dùng đệ quy."""
        result = []
        stack = []
        cursor = self.root

        while cursor is not None or stack:
            while cursor is not None:
                stack.append(cursor)
                cursor = cursor.left

            cursor = stack.pop()
            result.append(cursor.key)
            cursor = cursor.right

        return result


bst = BST()

for key in [8, 4, 12, 2, 6, 10, 14]:
    assert bst.insert(key)

print(bst.find(10).key)         # 10
print(bst.find(99))             # None
print(bst.inorder())            # [2, 4, 6, 8, 10, 12, 14]
print(bst.insert(4))            # False: khóa trùng
```

### Chi phí thực tế của ví dụ

- `find` đi xuống một đường: **`O(h+1)` thời gian**, **`O(1)` bộ nhớ phụ** vì dùng vòng lặp.
- `insert` đi xuống một đường rồi thêm một nút: **`O(h+1)` thời gian**, **`O(1)` bộ nhớ phụ** ngoài nút mới.
- `inorder` thăm mỗi nút đúng một lần: **`O(n)` thời gian**, stack tạm **`O(h+1)`**, danh sách kết quả **`O(n)`**.
- Lưu toàn bộ BST cần **`O(n)` bộ nhớ** cho các nút và liên kết.

**Cảnh báo:** đoạn mã là **BST cơ bản, không tự cân bằng**. Sự kiện chèn theo thứ tự thuận lợi trong ví dụ không được coi là bằng chứng hiệu năng `O(\log n)` cho mọi đầu vào.

### 5.1. Kiểm tra BST bằng khoảng khóa

Hàm sau kiểm tra bất biến trên **toàn bộ cây con**, thay vì chỉ so sánh với con trực tiếp. Nó cũng dùng tập định danh để từ chối nút bị dùng chung hoặc chu trình trong đồ thị tham chiếu.

```python
def is_valid_bst(root):
    # Giả định khóa là các số có thể so sánh với <, <=, >=.
    pending = [(root, None, None)]
    seen = set()

    while pending:
        node, low, high = pending.pop()

        if node is None:
            continue

        marker = id(node)
        if marker in seen:
            return False  # Dùng chung nút hoặc có chu trình.
        seen.add(marker)

        if low is not None and node.key <= low:
            return False
        if high is not None and node.key >= high:
            return False

        pending.append((node.left, low, node.key))
        pending.append((node.right, node.key, high))

    return True


print(is_valid_bst(bst.root))  # True

bad = BSTNode(8)
bad.left = BSTNode(4)
bad.left.right = BSTNode(10)

print(is_valid_bst(bad))       # False
```

Trong trường hợp một cây nhị phân hợp lệ có `n` nút, việc xác thực toàn bộ bất biến cần **`O(n)` thời gian và tối đa `O(n)` bộ nhớ phụ** do tập đã thăm. Kiểm tra cấu trúc không có chu trình khác với tìm một khóa: không thể bỏ qua toàn bộ các nhánh nếu mục tiêu là **chứng minh mọi nút đều hợp lệ**.

## 6. Heap: tối ưu việc lấy phần tử ưu tiên nhất

### 6.1. Heap ở đây là *binary heap*

Một **binary heap** là cây nhị phân đáp ứng hai loại bất biến:

1. **Hình dạng complete:** mọi mức trước mức cuối đều đầy, mức cuối lấp từ **trái sang phải**.
2. **Thứ tự ưu tiên cha–con:** cha không lớn hơn con (min-heap) hoặc không nhỏ hơn con (max-heap).

Hai biến thể thông dụng:

- **Min-heap:** `priority(parent) ≤ priority(child)`. Gốc chứa một phần tử có **ưu tiên nhỏ nhất**.
- **Max-heap:** `priority(parent) ≥ priority(child)`. Gốc chứa một phần tử có **ưu tiên lớn nhất**.

Điều kiện áp dụng cho **mỗi cạnh cha–con**. Khi bắc cầu theo một đường đi, ở min-heap, mọi hậu duệ đều có ưu tiên **không nhỏ hơn tổ tiên**; ở max-heap, ngược lại.

### 6.2. Ví dụ min-heap và max-heap

Dùng cùng tập khóa `2,4,6,8,10,12,14`:

```text
Min-heap:                        Max-heap:

         2                              14
       /   \                           /  \
      6     4                         10   12
     / \   / \                       / \   / \
   14   8 12  10                     2   8 4   6

Mỗi cha <= từng con.           Mỗi cha >= từng con.
Cả hai đều complete.           Cả hai đều complete.
```

Với min-heap bên trái:

- `2≤6` và `2≤4`.
- `6≤14` và `6≤8`.
- `4≤12` và `4≤10`.

Đây là min-heap hợp lệ nhưng **không phải BST**: nút `6` là con trái của `2` dù `6 > 2`. Ngoài ra, các giá trị ở những nhánh trái/phải không được sắp xếp theo bất biến phân vùng khóa của BST.

### 6.3. “Phần tử nhỏ nhất ở gốc” không có nghĩa cả cây được sắp xếp

Trong min-heap, chỉ có bảo đảm rằng **gốc là phần tử nhỏ nhất** trong các phần tử đang lưu. Không có ràng buộc:

- Cây con trái phải chứa toàn giá trị nhỏ hơn cây con phải.
- Duyệt inorder phải cho dãy tăng dần.
- Các phần tử theo thứ tự mức phải tăng dần.
- Phần tử nhỏ thứ hai phải nằm ở một vị trí cố định nào đó ngoài việc nó là một trong các con của gốc nếu cây có ít nhất hai nút.

Ví dụ mảng mức của min-heap ở trên là:

```text
[2, 6, 4, 14, 8, 12, 10]
```

Dãy này **không tăng dần**, nhưng heap vẫn đúng. Nếu cần lần lượt lấy ra các giá trị từ nhỏ tới lớn, phải thực hiện **nhiều lần pop**, mỗi lần đưa heap về trạng thái hợp lệ.

### 6.4. Heap dùng mảng hiệu quả vì complete

Heap nhị phân thường lưu trong **mảng liên tiếp** theo thứ tự mức, thay vì cấp phát nút có hai con trỏ.

Với chỉ số bắt đầu từ `0`:

\[
\operatorname{left}(i)=2i+1,\qquad
\operatorname{right}(i)=2i+2,
\]

và với `i>0`:

\[
\operatorname{parent}(i)=\left\lfloor\frac{i-1}{2}\right\rfloor.
\]

Nếu chỉ số con vượt quá độ dài mảng, con đó không tồn tại. Vì cây **complete**, các nút chiếm liên tục các chỉ số `0..n-1`, không có lỗ cần chèn `None`.

**Giới hạn hình dạng:** heap nhị phân không thể có một nút con phải nhưng thiếu con trái tại vị trí tương ứng; cấu trúc như vậy không complete.

### 6.5. Các thao tác ưu tiên

Với binary heap `n` phần tử:

- **Peek:** xem gốc có ưu tiên cao nhất (min hoặc max) trong **`O(1)`**.
- **Push:** thêm phần tử vào cuối mảng để giữ complete, sau đó **sift-up** (đẩy lên) khi vi phạm ưu tiên cha–con; **`O(\log n)`** trường hợp xấu nhất.
- **Pop gốc:** lấy gốc, đưa phần tử cuối lên gốc rồi **sift-down** (đẩy xuống) để sửa bất biến; **`O(\log n)`**.
- **Heapify:** xây heap từ `n` phần tử bất kỳ bằng cách sift-down từ các nút trong cuối mảng về đầu; **`O(n)`** thời gian.
- **Tìm một giá trị tùy ý** không phải gốc: trong trường hợp xấu nhất vẫn cần **`O(n)`**, vì bất biến heap không cho phép chọn duy nhất nhánh trái/phải như BST.

Đây là lý do heap thích hợp để triển khai **priority queue (hàng đợi ưu tiên)**, nhưng không phải cấu trúc tìm kiếm khóa tùy ý tốt nhất.

## 7. Python: cài đặt min-heap bằng mảng

Để thấy rõ bất biến, ta triển khai một min-heap nhỏ thay vì chỉ gọi thư viện. Code giả định các khóa có thể so sánh bằng `<` và `<=`.

```python
class MinHeap:
    def __init__(self, values=()):
        self.data = list(values)

        # Heapify từ dưới lên: các lá đã là heap hợp lệ.
        for i in range(len(self.data) // 2 - 1, -1, -1):
            self._sift_down(i)

    def __len__(self):
        return len(self.data)

    def peek(self):
        if not self.data:
            raise IndexError("heap rỗng")
        return self.data[0]

    def push(self, value):
        data = self.data
        data.append(value)

        # Phần tử mới ở cuối, hình dạng complete vẫn đúng.
        i = len(data) - 1

        while i > 0:
            parent = (i - 1) // 2
            if data[parent] <= data[i]:
                break

            data[parent], data[i] = data[i], data[parent]
            i = parent

    def pop(self):
        if not self.data:
            raise IndexError("heap rỗng")

        data = self.data
        minimum = data[0]
        last = data.pop()

        if data:
            data[0] = last
            self._sift_down(0)

        return minimum

    def _sift_down(self, i):
        data = self.data
        n = len(data)

        while True:
            left = 2 * i + 1
            right = 2 * i + 2
            smallest = i

            if left < n and data[left] < data[smallest]:
                smallest = left

            if right < n and data[right] < data[smallest]:
                smallest = right

            if smallest == i:
                break

            data[i], data[smallest] = data[smallest], data[i]
            i = smallest


def is_min_heap(values):
    return all(
        values[(i - 1) // 2] <= values[i]
        for i in range(1, len(values))
    )


heap = MinHeap([8, 4, 12, 2, 6, 10, 14])

assert is_min_heap(heap.data)
print(heap.peek())   # 2

heap.push(1)
assert is_min_heap(heap.data)
print(heap.peek())   # 1

ordered = [heap.pop() for _ in range(len(heap))]
print(ordered)       # [1, 2, 4, 6, 8, 10, 12, 14]
```

### Vì sao `push` và `pop` đúng?

**Push:** thêm ở cuối mảng, nên bất biến **complete** còn nguyên. Chỉ có thể vi phạm ở đường từ nút mới lên gốc. Mỗi lần đổi chỗ với cha nhỏ hơn mức ưu tiên của nó làm phần tử mới đi lên một mức; kết thúc khi cha không lớn hơn nó hoặc tới gốc.

**Pop:** sau khi bỏ gốc, lấy phần tử cuối về gốc giúp hình dạng **vẫn complete**. Chỉ có thể vi phạm trên đường từ gốc xuống dưới. Mỗi lần đổi với **con nhỏ nhất** giúp khôi phục bất biến tại nút hiện tại, rồi tiếp tục xuống dưới.

Vì heap complete có chiều cao **`\lfloor\log_2 n\rfloor`**, mỗi lần sift-up/sift-down có tối đa `O(\log n)` bước.

**Bộ nhớ phụ:** thao tác push/pop trên mảng dùng **`O(1)` bộ nhớ phụ**, chưa tính dung lượng mở rộng của mảng động và bản thân `n` phần tử đang lưu. `heapify` từ dưới lên làm việc tại chỗ trên bản sao danh sách trong `self.data`, nên vòng heapify không cần thêm bộ nhớ phụ tỷ lệ `n`; danh sách đầu vào được sao chép một lần.

### Tại sao `heapify` có thể là `O(n)`?

Nếu chèn lần lượt `n` phần tử bằng `push`, chặn trên tổng là **`O(n\log n)`**. Nhưng khi heapify từ dưới lên:

- Nhiều nút ở gần lá chỉ cần sift xuống rất ít mức.
- Chỉ một số ít nút ở gần gốc có thể sift xuống sâu.
- Tổng số công việc qua mọi nút là **`O(n)`**, không phải `O(n\log n)`.

Đây là một ví dụ quan trọng về sự khác nhau giữa **xây heap hàng loạt** và **cập nhật heap từng phần tử**.

### Dùng thư viện Python khi lập trình ứng dụng

Python có mô-đun chuẩn `heapq` cho min-heap lưu trên một danh sách:

```python
import heapq

priorities = [8, 4, 12, 2, 6, 10, 14]

heapq.heapify(priorities)       # O(n)
heapq.heappush(priorities, 1)   # O(log n)

print(priorities[0])            # 1
print(heapq.heappop(priorities))  # 1
```

Trong ứng dụng hàng đợi ưu tiên, một mục thường là cặp `(priority, payload)`. Nếu cần **thứ tự ổn định khi priority bằng nhau**, có thể thêm **số thứ tự tăng dần** vào khóa so sánh, ví dụ `(priority, sequence_number, task)`. Heap **không tự bảo đảm FIFO giữa các phần tử cùng ưu tiên**.

## 8. Cùng một tập số nhưng ba cách tổ chức khác nhau

Giả sử các giá trị là:

```text
{2, 4, 6, 8, 10, 12, 14}
```

Chúng ta có thể xây ba cây cùng chứa các số này nhưng ngữ nghĩa khác nhau.

### 8.1. Cây dữ liệu: các cạnh do ứng dụng quy định

```text
         8
       / | \
      2  12  6
        /  \
       4    14
            /
           10
```

Đây là **cây tổng quát** nếu các cạnh mang nghĩa phân cấp do ứng dụng quyết định. Không có yêu cầu khóa phải tăng hay giảm theo hướng nào; nút `8` có ba con nên bản thân cấu trúc này không phải cây nhị phân.

Nếu muốn biểu diễn **một cây dữ liệu nhị phân**, ta có thể giới hạn mỗi nút hai con mà vẫn **không phải BST**. Số con tối đa và mục tiêu tìm kiếm là hai loại ràng buộc độc lập.

### 8.2. BST: vị trí dựa trên quan hệ nhỏ hơn/lớn hơn

```text
          8
        /   \
       4     12
      / \   /  \
     2   6 10  14
```

Nhờ bất biến phân vùng khóa ở **mọi nút**, một so sánh giúp chọn một nhánh để tiếp tục tìm.

### 8.3. Min-heap: vị trí ưu tiên và hình dạng complete

```text
          2
        /   \
       6     4
      / \   /  \
     14  8 12  10
```

Ở đây phần tử nhỏ nhất `2` nằm ở gốc. Nhưng không thể dùng so sánh với nút `6` để kết luận khóa `10` sẽ chỉ ở cây con trái hay phải của `6`. Heap **không phân vùng các khóa như BST**.

### 8.4. Bảng đối chiếu điều quan sát được

| Câu hỏi | Cây dữ liệu | BST | Min-heap |
|---|---|---|---|
| Cha–con dựa trên điều gì? | Ngữ nghĩa phân cấp | Quy tắc khóa + thao tác chèn | Vị trí complete + ưu tiên |
| Nút có bao nhiêu con? | Có thể hơn hai | Tối đa hai | Tối đa hai |
| Khóa nhỏ nhất có nhất thiết ở gốc? | Không | Không | **Có** |
| Inorder được sắp xếp? | Không có quy ước tổng quát cho nhiều con | **Có**, với BST hợp lệ | Không |
| Có thể chọn nhánh khi tìm khóa? | Không, nếu không có chỉ mục thêm | **Có**, nhờ thứ tự khóa | Không theo quy tắc BST |
| Hình dạng complete bắt buộc? | Không | Không | **Có** |
| Phải cân bằng? | Không | Chỉ nếu biến thể yêu cầu | Complete đã cho chiều cao thấp |
| Một nhãn lặp lại có được không? | Có thể, nếu là các nút riêng | Theo chính sách khóa trùng | Có thể |

Kết luận: **hình vẽ giống một cái cây không đủ để xác định thuật toán đúng**. Phải hỏi **điều kiện nào được giữ sau mọi lần cập nhật**.

## 9. So sánh thời gian và bộ nhớ theo thao tác

Gọi `n` là số nút/phần tử, `h` là chiều cao cây theo cạnh, `k` là số con trực tiếp của một nút.

### 9.1. Bảng độ phức tạp

| Thao tác | Cây dữ liệu tổng quát (danh sách con) | BST cơ bản | Binary heap |
|---|---|---|---|
| Tìm **một giá trị/nhãn tùy ý** không có chỉ mục phụ | `O(n)` xấu nhất | `O(h+1)` | `O(n)` xấu nhất |
| Xem phần tử nhỏ nhất | Không có cấu trúc khóa bảo đảm vị trí | `O(h+1)` theo nhánh cực trái | `O(1)` với min-heap |
| Xem phần tử lớn nhất | Không có cấu trúc khóa bảo đảm vị trí | `O(h+1)` theo nhánh cực phải | `O(1)` với max-heap |
| Chèn phần tử mới | Theo cha/vị trí mong muốn; gán liên kết có thể `O(1)`, kiểm tra/cập nhật phát sinh thêm | `O(h+1)`, chưa tính tái cân bằng | `O(\log n)` |
| Xóa phần tử | Phụ thuộc chính sách xử lý cây con; không có phép xóa chung | `O(h+1)` với thuật toán BST phù hợp | Pop gốc `O(\log n)`; xóa phần tử bất kỳ có thể cần tìm `O(n)` |
| Duyệt toàn bộ `n` phần tử | `O(n)` | `O(n)` (inorder tăng dần) | `O(n)` để xem hết mảng, **không sắp xếp** |
| Lấy **tất cả phần tử theo khóa tăng dần** | Nếu chưa có chỉ mục/sắp xếp, cần công việc bổ sung | Inorder `O(n)` | Lấy liên tiếp bằng pop `O(n\log n)`; làm thay đổi heap |
| Xây từ `n` đầu vào | Tùy quan hệ cha–con được cung cấp; dựng liên kết thường `O(n)` | Chèn lần lượt `O(n(h+1))` chặn thô; xấu nhất `O(n²)` | Heapify từ dưới lên **`O(n)`** |
| Bộ nhớ lưu cấu trúc | `O(n)` | `O(n)` | `O(n)` |

**Ghi chú cho BST:**

- Với BST không cân bằng, `h` có thể bằng `n-1`.
- Với AVL/Red–Black Tree, chiều cao `O(\log n)` được duy trì bằng các phép điều chỉnh.
- Khi nói xây BST bằng cách chèn lần lượt, không thể thay `h` bằng `\log n` nếu không có giả thiết cân bằng hoặc thứ tự đầu vào thích hợp.

**Ghi chú cho cây dữ liệu:** việc “chèn” có thể chỉ là gắn con dưới cha đã biết, nhưng **tìm cha**, **tránh chu trình**, **giữ thứ tự**, **cập nhật depth/size cache** hoặc **sửa liên kết hai chiều** đều có thể phát sinh chi phí. Không có một giới hạn `O(1)` chung cho mọi API chỉnh sửa cây phân cấp.

**Ghi chú cho heap:** bảng so sánh áp dụng cho **binary heap**. Phần tử ưu tiên nhất ở gốc, nhưng **không có chỉ mục khóa tùy ý**. Nếu cần thay đổi/xóa công việc không nằm ở gốc, có thể phải thêm bảng ánh xạ ID → vị trí để đạt thao tác cập nhật nhanh và phải giữ bảng nhất quán mỗi lần đổi chỗ.

### 9.2. Đừng nhầm “chiều cao nhỏ” với “tìm mọi giá trị nhanh”

Một heap complete có chiều cao **`O(\log n)`**. Tuy vậy việc tìm **một khóa bất kỳ** có thể vẫn cần xem **`O(n)`** phần tử, vì bất biến min-heap chỉ biết **cha không lớn hơn con**, không biết khóa cần tìm thuộc nhánh nào.

Một BST cân bằng cũng có chiều cao `O(\log n)`, **đồng thời** có bất biến phân vùng khóa. Chính **sự kết hợp** này mới giúp chọn một nhánh trong mỗi bước và bảo đảm tìm theo khóa nhanh.

### 9.3. Về bộ nhớ phụ

- Cây dữ liệu và BST dạng nút liên kết cần **`O(n)`** bộ nhớ lưu các nút/cạnh.
- Heap nhị phân dạng mảng lưu **`O(n)`** giá trị, thường không cần trường `left`/`right` riêng.
- DFS trên cây dữ liệu tổng quát có thể cần stack **`O(n)`** trong trường hợp cây rộng; DFS đệ quy có thể cần **`O(h+1)`** khung lời gọi.
- Duyệt inorder BST bằng stack cần **`O(h+1)`** bộ nhớ phụ, chưa tính danh sách kết quả.
- Heap push/pop chỉ cần **`O(1)` bộ nhớ phụ** trong mã sift lặp, ngoài mảng heap; bản thân mảng vẫn có `O(n)` bộ nhớ.

Các độ phức tạp nói trên giả định một phép so sánh khóa hoặc xử lý nút cơ bản mất `O(1)`. Nếu khóa lớn hoặc phép so sánh tốn kém, phải tính thêm chi phí thực tế đó.

## 10. Cập nhật dữ liệu: loại bất biến nào dễ bị phá?

Không phải mọi thao tác thay đổi nút đều có cùng tác động.

### 10.1. Cây dữ liệu: di chuyển một mục

Giả sử có cây mục lục:

```text
Khóa học
├── Chương A
│   └── Bài X
└── Chương B
```

Muốn chuyển “Bài X” sang “Chương B”, ta phải:

1. Xác định cha mới không nằm trong cây con đang chuyển.
2. Tháo “Bài X” khỏi danh sách con của “Chương A”.
3. Gắn “Bài X” vào danh sách con của “Chương B”.
4. Cập nhật `parent`, thứ tự, độ sâu và thông tin phụ thuộc cấu trúc nếu có.

Không cần so sánh tên “Bài X” với “Chương B” theo một quan hệ nhỏ hơn/lớn hơn để quyết định vị trí. Thứ tự hiển thị do **ngữ nghĩa nghiệp vụ** quyết định.

### 10.2. BST: đổi khóa có thể phá bất biến tìm kiếm

Trong BST:

```text
       8
      / \
     4   12
```

Nếu tự ý thay khóa của nút `4` thành `20` nhưng giữ nguyên liên kết, cây **không còn BST**: `20` nằm trong cây con trái của `8`.

Thông thường cần **xóa khóa cũ và chèn khóa mới**, hoặc dùng một thao tác cập nhật chuyên dụng bảo toàn bất biến, thay vì sửa khóa tại chỗ một cách tùy tiện. Với các cây tự cân bằng, còn cần duy trì bất biến chiều cao/màu hoặc quy tắc tương ứng.

### 10.3. Heap: đổi ưu tiên có thể đòi sift-up hoặc sift-down

Trong min-heap:

```text
        2
       / \
      6   4
```

Nếu giảm ưu tiên của một nút con từ `6` xuống `1`, nút con nay nhỏ hơn cha; phải **sift-up** để min-heap hợp lệ.

Nếu tăng ưu tiên của gốc từ `2` lên `20`, gốc có thể lớn hơn con; phải **sift-down** để khôi phục thứ tự ưu tiên.

Với binary heap lưu mảng, thay đổi ưu tiên tại một vị trí **đã biết** và khôi phục bất biến thường mất **`O(\log n)`**. Nhưng nếu chỉ biết ID một phần tử mà không biết vị trí mảng, chi phí tìm vị trí có thể là **`O(n)`** trước khi sift.

### 10.4. Cùng là xóa một nút nhưng ý nghĩa khác

| Cấu trúc | “Xóa” thường cần quyết định |
|---|---|
| Cây dữ liệu | Xóa riêng lá, xóa cả cây con, hay chuyển con sang cha khác? |
| BST | Xóa khóa và nối lại các cây con sao cho bất biến phân vùng khóa vẫn đúng; cây cân bằng có thể phải xoay/chỉnh |
| Heap | Nếu xóa gốc, thay bằng phần tử cuối rồi sift; nếu xóa vị trí bất kỳ, còn cần tìm và cập nhật vị trí |

Từ “xóa một nút” không tự mô tả một thuật toán duy nhất cho mọi loại cây.

## 11. Phân biệt hình dạng: binary, full, complete, balanced

Các thuật ngữ về **hình dạng** không tương đương với thuật ngữ về **mục tiêu**.

### 11.1. Cây nhị phân không đồng nghĩa BST

**Binary tree** chỉ bảo đảm mỗi nút tối đa hai con và phân biệt trái/phải. BST là **binary tree cộng thêm bất biến khóa**. Một cây biểu thức toán học có hai toán hạng cũng có thể là binary tree nhưng không phải BST.

### 11.2. Complete không đồng nghĩa heap

**Complete binary tree** lấp đầy các mức trước mức cuối, mức cuối từ trái sang phải. Nhưng muốn thành min-heap/max-heap, cần **thêm bất biến ưu tiên**. Một cây complete mà gốc không phải giá trị min (đối với min-heap) vẫn không hợp lệ dưới vai trò min-heap.

### 11.3. Heap không đồng nghĩa cây cân bằng tìm kiếm

Binary heap complete nên chiều cao thấp, nhưng thiếu bất biến tra cứu khóa như BST. Cây được coi là **đủ cân đối về hình dạng** không tự có khả năng tìm bất kỳ khóa nào theo một nhánh.

### 11.4. BST không bắt buộc complete

BST ví dụ:

```text
       8
      /
     4
    /
   2
```

Vẫn đúng bất biến BST, nhưng không complete khi `2` ở mức `2` trong lúc mức `1` chưa đầy. BST không cân bằng còn có thể suy biến thành chuỗi.

**Tóm lại:** binary/complete/full/perfect/balanced là những mô tả **hình dạng** với định nghĩa cụ thể; data tree/BST/heap là phân biệt **mục đích và bất biến nghiệp vụ/khóa/ưu tiên**. Hai nhóm mô tả có thể kết hợp.

## 12. Chọn cấu trúc theo mục tiêu thao tác

### 12.1. Bảng chọn nhanh

| Nhu cầu trọng tâm | Cấu trúc phù hợp | Lý do |
|---|---|---|
| Danh mục bài học, thư mục, tổ chức theo cha–con | **Cây dữ liệu có gốc**, danh sách con hoặc LCRS | Quan hệ phân cấp là dữ liệu cần giữ |
| Tìm một khóa và duyệt khóa đã sắp thứ tự | **BST cân bằng** hoặc cây tìm kiếm tương ứng | Bất biến phân vùng giúp tìm và inorder |
| Liên tục lấy phần tử có **ưu tiên nhỏ nhất** | **Min-heap / priority queue** | Gốc là min, push/pop `O(\log n)` |
| Liên tục lấy phần tử có **ưu tiên lớn nhất** | **Max-heap / priority queue** | Gốc là max |
| Tìm nhanh bằng khóa, **không cần thứ tự** | Có thể dùng **bảng băm (hash table)** | Tra cứu trung bình `O(1)` khi điều kiện băm phù hợp |
| Truy vấn nhiều tiền nhiệm/kế nhiệm hoặc đoạn khóa | Thường cân nhắc **cây tìm kiếm có thứ tự**, ví dụ BST cân bằng/B-tree | Hỗ trợ điều hướng theo thứ tự khóa |
| Dữ liệu có một đối tượng thuộc nhiều cha | **Đồ thị/DAG**, không ép thành cây đơn cha | Tránh phá ý nghĩa liên kết |

Các gợi ý này phải được điều chỉnh theo yêu cầu cụ thể: dữ liệu có cần lưu bền không, có cập nhật thường xuyên không, khóa có trùng không, ưu tiên có đổi không, có nhiều luồng không và giới hạn bộ nhớ như thế nào.

### 12.2. Ba tình huống có cùng nhãn “Task”

**Tình huống A — Danh sách nhiệm vụ theo dự án:** dự án gồm nhóm công việc, mỗi nhóm có các công việc con. Người dùng thường mở rộng/thu gọn nhóm. Cấu trúc phù hợp là **cây phân cấp**.

**Tình huống B — Tra nhiệm vụ theo ID có thứ tự:** hệ thống cần tìm ID, in các ID trong khoảng và duyệt tăng dần. Một **cây tìm kiếm cân bằng** có thể phù hợp, đặc biệt nếu cần thứ tự; bảng băm có thể phù hợp hơn nếu chỉ cần tìm đúng ID.

**Tình huống C — Bộ lập lịch ưu tiên:** hệ thống liên tục cần công việc có deadline sớm nhất. **Min-heap** lưu deadline làm khóa ưu tiên hỗ trợ xem công việc sớm nhất nhanh và cập nhật hàng đợi hiệu quả.

Một ứng dụng thực tế có thể đồng thời sử dụng **cả ba cấu trúc** trên cùng tập công việc: cây để hiển thị phân cấp, bảng băm/BST để tra theo ID, heap để chọn tác vụ sắp chạy. Chúng đóng các **vai trò bổ sung**, không phải buộc chọn đúng một cấu trúc cho mọi nhu cầu.

## 13. Những hiểu nhầm thường gặp

1. **Cho rằng cứ có gốc và hai con là BST.** Cây nhị phân chỉ áp đặt giới hạn hai con; BST cần bất biến khóa trên **toàn bộ cây con**.
2. **Cho rằng mọi cây tìm kiếm đều là BST.** Còn có các cây tìm kiếm đa nhánh, B-tree, B+ tree với bất biến riêng.
3. **Cho rằng BST tìm `O(\log n)` trên mọi dữ liệu.** BST không cân bằng có thể cao `n-1` và tìm `O(n)`.
4. **Cho rằng cây phân cấp dữ liệu phải được sắp theo khóa.** Tên/chỉ số các con có thể theo thứ tự nghiệp vụ, không phải thứ tự BST.
5. **Cho rằng min-heap là BST có phần tử nhỏ nhất ở gốc.** Trong BST, khóa nhỏ nhất nằm ở nhánh cực trái; trong min-heap, gốc chứa min và không có phân vùng trái/phải kiểu BST.
6. **Cho rằng heap được sắp xếp toàn bộ.** Mảng heap không cần tăng dần hay giảm dần; chỉ các quan hệ cha–con được bảo đảm.
7. **Cho rằng complete là đủ để tạo heap.** Complete là bất biến hình dạng, chưa nói gì về giá trị.
8. **Cho rằng heap có chiều cao `O(\log n)` thì tìm mọi khóa `O(\log n)`.** Thiếu quy tắc loại bỏ một nhánh theo khóa.
9. **Cho rằng BST phải complete hoặc perfect.** Các hình dạng này không phải điều kiện của BST thông thường.
10. **Chỉ so khóa với con trực tiếp khi kiểm tra BST.** Phải kiểm tra các giới hạn do **tất cả tổ tiên** áp đặt.
11. **Dùng `>=` hoặc `<=` tùy ý trong BST có khóa trùng.** Chính sách khóa trùng phải nhất quán; mã minh họa dùng khóa phân biệt.
12. **Dùng nhãn bằng nhau để gộp hai nút dữ liệu.** Hai nút có thể cùng nhãn nhưng là các đối tượng riêng trong cây phân cấp.
13. **Thay đổi giá trị BST hoặc ưu tiên heap mà không sửa cấu trúc.** Có thể phá bất biến khóa hoặc heap.
14. **Gắn lại cây con dữ liệu mà không kiểm tra chu trình.** Có thể tạo một nút vừa là tổ tiên vừa là hậu duệ của nó.
15. **Nhầm priority queue với queue FIFO.** Heap ưu tiên theo khóa, không bảo đảm phục vụ theo thứ tự vào trước khi ưu tiên bằng nhau.
16. **Cho rằng xóa phần tử bất kỳ trong heap luôn `O(\log n)`.** Nếu chưa biết vị trí phần tử trong mảng, tìm nó có thể mất `O(n)`.
17. **Cho rằng các phép duyệt toàn bộ cây đều có thời gian `O(h)`.** Nếu phải thăm `n` nút, thời gian thường là `O(n)` dù cây thấp.
18. **Không tính bộ nhớ danh sách kết quả.** Một lần inorder `O(n)` thời gian cũng có thể lưu `O(n)` giá trị kết quả.
19. **Quên quy ước chiều cao.** Trong bài, chiều cao tính bằng số cạnh, nên lá cao `0`; tài liệu đếm theo số nút sẽ lệch một.
20. **Chọn duy nhất một cấu trúc cho mọi thao tác của ứng dụng.** Có thể kết hợp cây dữ liệu, chỉ mục tìm kiếm và heap để tối ưu từng loại công việc.

## 14. Tự kiểm tra bằng ví dụ Python

Các đoạn dưới dùng các lớp/hàm đã định nghĩa trong bài. Chúng minh họa sự khác biệt giữa **duyệt toàn bộ**, **tìm theo khóa** và **kiểm tra ưu tiên**.

```python
# Cây phân cấp: tìm nhãn cần duyệt nếu không có chỉ mục.
assert find_label_dfs(course, "BST").label == "BST"
assert find_label_dfs(course, "Không tồn tại") is None

# BST: tìm một khóa theo bất biến trái < gốc < phải.
assert bst.find(6).key == 6
assert bst.find(100) is None
assert bst.inorder() == [2, 4, 6, 8, 10, 12, 14]
assert is_valid_bst(bst.root)
assert not is_valid_bst(bad)

# Heap: bản thân mảng có thể không được sắp xếp.
sample_heap = [2, 6, 4, 14, 8, 12, 10]
assert is_min_heap(sample_heap)
assert sample_heap != sorted(sample_heap)

# Không phải mảng complete có thứ tự tùy ý đều là min-heap.
assert not is_min_heap([9, 3, 7])

# Một khóa trùng bị từ chối ở BST minh họa,
# còn min-heap vẫn cho phép ưu tiên bằng nhau.
assert bst.insert(8) is False
duplicates = MinHeap([2, 2, 1])
assert [duplicates.pop() for _ in range(3)] == [1, 2, 2]
```

Ở những đoạn kiểm tra này:

- `is_valid_bst` kiểm tra **toàn bộ cấu trúc khóa** của BST.
- `is_min_heap` kiểm tra **mọi quan hệ ưu tiên cha–con** trong một mảng.
- Việc một mảng qua được `is_min_heap` **không chứng minh** nó có các quan hệ phân cấp nghiệp vụ hay bất biến BST.

Các khẳng định là tài liệu thực hành, không thay thế việc xác thực dữ liệu sản xuất, nhất là khi phần tử có khóa không so sánh được hoặc có mã trùng, ưu tiên thay đổi, và cấu trúc bị sửa đồng thời.

## 15. Bài tập thực hành có đáp án

### Bài 1. Chọn cây cho danh mục

Một khóa học có nhiều chương, mỗi chương có nhiều bài và người học cần mở rộng/thu gọn từng chương. Nên dùng cây phân cấp, BST hay heap để **biểu diễn quan hệ chứa bài học**?

**Đáp án:** Dùng **cây biểu diễn dữ liệu có gốc**, thường là danh sách con hoặc mô hình tương đương, vì quan hệ chương–bài là thông tin chính. Có thể bổ sung chỉ mục tìm theo ID; không cần áp bất biến BST/heap cho các cạnh cha–con.

### Bài 2. Cây nhị phân không nhất thiết là BST

Cho cây:

```text
       8
      / \
     12  4
```

Cây có phải cây nhị phân hợp lệ không? Có phải BST theo bất đẳng thức nghiêm ngặt không?

**Đáp án:** **Có** là cây nhị phân vì mỗi nút tối đa hai con, không chu trình. **Không** là BST vì `12` nằm bên trái `8` và `4` nằm bên phải `8`, vi phạm quy tắc khóa.

### Bài 3. Kiểm tra giới hạn của tổ tiên

Cho cây:

```text
       8
      /
     4
      \
      10
```

Vì sao việc so sánh nút với con trực tiếp chưa đủ để kết luận BST?

**Đáp án:** `10 > 4` nên hợp lệ với cha trực tiếp `4`, nhưng `10` nằm trong **cây con trái của `8`** và phải nhỏ hơn `8`. Vì `10>8`, toàn cây không phải BST.

### Bài 4. Tìm khóa trong BST

Cho BST gồm `8` ở gốc; `4,12` là con; `2,6` là con của `4`; `10,14` là con của `12`. Tìm khóa `6` đi qua những nút nào?

**Đáp án:** So `6` với `8` (nhỏ hơn, đi trái), tới `4` (lớn hơn, đi phải), tới `6`. Đường tìm là **`8→4→6`**.

### Bài 5. Inorder của BST

Duyệt inorder BST trong Bài 4 cho dãy gì?

**Đáp án:** **`2,4,6,8,10,12,14`**, tăng dần theo khóa nhờ bất biến BST.

### Bài 6. Cây tìm kiếm suy biến

Chèn lần lượt `1,2,3,4,5` vào BST không tự cân bằng ban đầu rỗng. Cây có hình dạng gì và tìm khóa cuối có chi phí thế nào?

**Đáp án:** Cây trở thành **một chuỗi lệch phải**, chiều cao `4` cạnh. Tìm khóa `5` phải đi qua năm nút, tổng quát có thể tốn **`O(n)`**. Cân bằng cấu trúc mới bảo đảm chiều cao nhỏ.

### Bài 7. Nhận diện min-heap

Mảng `[2, 6, 4, 14, 8, 12, 10]` có phải min-heap không? Có được sắp tăng dần không?

**Đáp án:** **Có** là min-heap: mọi cha không lớn hơn từng con theo chỉ số `2i+1` và `2i+2`; hình dạng mảng đặc là complete. **Không** tăng dần vì `6>4` và `14>8` ở các vị trí kế tiếp.

### Bài 8. Phát hiện vi phạm heap

Mảng `[3, 1, 5]` là một cây complete. Nó có phải min-heap không?

**Đáp án:** **Không** vì gốc `3` lớn hơn con trái `1`. Complete chỉ bảo đảm hình dạng, không bảo đảm ưu tiên cha–con.

### Bài 9. Xem ưu tiên nhỏ nhất

Với một min-heap chứa `n` công việc, thời gian xem công việc có ưu tiên nhỏ nhất mà không xóa là bao nhiêu? Vì sao?

**Đáp án:** **`O(1)`**, vì bất biến min-heap bảo đảm phần tử nhỏ nhất đang ở gốc, tương ứng chỉ số `0` của mảng.

### Bài 10. Xóa gốc heap

Sau khi bỏ phần tử gốc của binary heap, vì sao thường đưa phần tử cuối mảng lên gốc rồi sift-down?

**Đáp án:** Dùng phần tử cuối để lấp gốc rồi rút ngắn mảng sẽ **giữ hình dạng complete**. Sift-down khôi phục bất biến ưu tiên trên đường đi xuống, mất **`O(\log n)`** trường hợp xấu nhất.

### Bài 11. Chiều cao heap

Một binary heap có `n=31` phần tử. Chiều cao theo cạnh là bao nhiêu?

**Đáp án:** Vì binary heap complete, **`h=\lfloor\log_2 31\rfloor=4`**.

### Bài 12. Heapify so với chèn từng phần tử

Cần biến một mảng chưa được tổ chức gồm `n` khóa thành min-heap. So sánh heapify từ dưới lên và việc chèn lần lượt bằng push.

**Đáp án:** **Heapify bottom-up `O(n)`**; chèn từng phần tử có chặn trên tổng **`O(n\log n)`**. Heapify tận dụng việc đa số nút nằm gần lá, có quãng sift ngắn.

### Bài 13. Tìm một khóa tùy ý trong heap

Có thể dựa vào min-heap để tìm một khóa `x` bất kỳ chỉ trong `O(\log n)` không?

**Đáp án:** Không có bảo đảm đó. Min-heap chỉ quy định mỗi cha không lớn hơn con; các nhánh không được phân vùng như BST. Trong trường hợp xấu nhất phải xem **`O(n)`** phần tử.

### Bài 14. Hai mục cùng tên

Một cây thư mục có hai mục “Tài liệu” ở hai chương khác nhau. Có nhất thiết vi phạm bất biến cây dữ liệu không? BST dùng khóa là tên có chấp nhận hay không?

**Đáp án:** Hai nút **khác nhau** có cùng nhãn không vi phạm bất biến cây phân cấp nếu mỗi nút có một cha và không chu trình. BST có cho phép trùng khóa hay không phụ thuộc **chính sách khóa trùng**; mã BST trong bài **từ chối** khóa trùng, nhưng biến thể khác có thể lưu số lần xuất hiện hoặc có quy tắc khác.

### Bài 15. Cập nhật khóa BST

Trong BST gốc `8`, con trái `4`, nếu đổi khóa `4` thành `20` mà không thay liên kết, điều gì xảy ra?

**Đáp án:** **Phá bất biến BST**, vì khóa `20` nằm trong cây con trái của `8` nhưng lớn hơn `8`. Cần thao tác cập nhật bảo toàn thứ tự, ví dụ xóa khóa cũ rồi chèn khóa mới.

### Bài 16. Cập nhật ưu tiên heap

Trong min-heap, giảm giá trị của một nút con từ `6` xuống `1`, trong khi cha của nó là `2`. Cần sửa theo hướng nào?

**Đáp án:** Ưu tiên của con nhỏ hơn cha nên cần **sift-up**, đổi chỗ với cha đến khi cha không lớn hơn con hoặc tới gốc. Trong binary heap, thao tác tại vị trí đã biết mất tối đa **`O(\log n)`**.

### Bài 17. Sắp thứ tự toàn bộ

Cần xuất toàn bộ `n` khóa theo thứ tự tăng dần. Cấu trúc nào hỗ trợ tự nhiên hơn: BST hợp lệ hay min-heap?

**Đáp án:** BST hỗ trợ **inorder `O(n)` thời gian** khi đã có cây và mỗi nút được duyệt một lần. Min-heap chỉ bảo đảm min ở gốc; muốn lần lượt lấy ra toàn bộ theo thứ tự tăng dần có thể thực hiện `n` lần pop, tốn **`O(n\log n)`**, và làm thay đổi heap. Nếu chưa có cấu trúc, còn cần tính chi phí xây dựng thích hợp.

### Bài 18. Chọn cấu trúc cho bộ lập lịch

Một hệ thống cần chạy công việc có deadline sớm nhất, thêm công việc mới thường xuyên và đôi khi đổi deadline của công việc đã tồn tại. Nên dùng cấu trúc nào? Có lưu ý gì với thao tác đổi deadline?

**Đáp án:** **Min-heap / priority queue** phù hợp để lấy deadline nhỏ nhất, push và pop hiệu quả. Nếu thường đổi deadline theo ID, nên cân nhắc **chỉ mục ID → vị trí heap** hoặc chiến lược bản ghi phiên bản/lazy deletion để tìm đúng phần tử cần cập nhật; sau thay đổi phải sift lên hoặc xuống. Cần giữ chỉ mục nhất quán với mỗi lần hoán đổi.

### Bài 19. Có thể dùng nhiều cấu trúc đồng thời không?

Một ứng dụng lưu nhiệm vụ theo dự án và cần cả tìm nhanh theo ID lẫn chọn nhiệm vụ ưu tiên cao nhất. Có phải chọn đúng một trong ba loại cây?

**Đáp án:** **Không.** Có thể dùng cây dữ liệu để hiển thị quan hệ dự án–nhiệm vụ, bảng băm/BST cho tra cứu ID và heap cho hàng đợi ưu tiên. Các cấu trúc giữ các mục đích khác nhau; khi thêm/xóa/sửa nhiệm vụ cần cập nhật nhất quán các chỉ mục liên quan.

### Bài 20. Phân biệt hình dạng và bất biến

Một cây nhị phân complete có `7` nút nhưng các khóa được đặt tùy ý. Có thể kết luận nó là BST hoặc heap không?

**Đáp án:** **Không.** Complete chỉ là điều kiện **hình dạng**. BST cần bất biến phân vùng khóa trên mọi cây con; min-/max-heap cần bất biến ưu tiên cha–con. Không có những điều kiện này, cây chỉ là một cây nhị phân complete mang dữ liệu.

## 16. Tổng kết

Ba nhóm cây có chung nền tảng nút–cạnh nhưng khác **mục đích, bất biến và thao tác được tối ưu**:

- **Cây biểu diễn dữ liệu:** lưu quan hệ phân cấp có ý nghĩa. Không cần bất biến thứ tự khóa; tìm nhãn bất kỳ có thể cần duyệt **`O(n)`**, còn tra cha/con từ liên kết đã lưu có thể nhanh.
- **BST (đại diện cây tìm kiếm):** mọi khóa trong cây con trái nhỏ hơn gốc và trong cây con phải lớn hơn gốc, theo chính sách khóa của bài. Tìm, chèn, xóa phụ thuộc chiều cao **`O(h+1)`**; chỉ các biến thể có cân bằng mới bảo đảm **`O(\log n)`** trong trường hợp xấu nhất. Inorder cho dãy khóa tăng dần.
- **Binary heap:** cây nhị phân **complete**, thêm bất biến ưu tiên cha–con. Min-/max-heap cho phép xem ưu tiên nhỏ nhất/lớn nhất **`O(1)`**, push/pop gốc **`O(\log n)`**, heapify **`O(n)`**; nhưng tìm khóa tùy ý vẫn có thể **`O(n)`**.

Không được suy luận “cùng là cây nhị phân nên dùng chung thuật toán tìm kiếm” hoặc “chiều cao thấp nên mọi truy vấn đều nhanh”. **Hình dạng, thứ tự khóa và ưu tiên** là ba nhóm ràng buộc độc lập. Khi lựa chọn cấu trúc dữ liệu, hãy bắt đầu từ **câu hỏi phải trả lời nhanh**, rồi đánh giá bất biến, các thao tác cập nhật và độ phức tạp thời gian–bộ nhớ của đúng biến thể được sử dụng.
