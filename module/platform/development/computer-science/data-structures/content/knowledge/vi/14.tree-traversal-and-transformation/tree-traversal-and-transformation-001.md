# Duyệt trước, giữa, sau và ý nghĩa thứ tự xử lý nút

Khi làm việc với **cây (tree)**, một câu hỏi cơ bản là: **ta xử lý nút cha trước, ở giữa hay sau các cây con của nó?** Cùng một cây có thể được thăm theo nhiều thứ tự, và mỗi thứ tự phục vụ một mục đích riêng. Ba cách duyệt sâu điển hình trên **cây nhị phân** là:

- **Duyệt trước (preorder):** xử lý **nút hiện tại**, sau đó duyệt **cây con trái**, rồi **cây con phải**.
- **Duyệt giữa (inorder):** duyệt **cây con trái**, xử lý **nút hiện tại**, rồi duyệt **cây con phải**.
- **Duyệt sau (postorder):** duyệt **cây con trái**, rồi **cây con phải**, cuối cùng xử lý **nút hiện tại**.

Bài học thuộc chương **Duyệt và biến đổi cây** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mô-đun xây dựng nền tảng về mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị; trong đó việc hiểu **bất biến**, **thao tác** và **độ phức tạp thời gian/bộ nhớ** giúp chọn đúng cấu trúc cho bài toán. Với cây, thứ tự duyệt còn quyết định liệu thông tin của cha hay của con đã sẵn sàng khi ta cần tính toán hoặc biến đổi nút.

## 1. Phạm vi: cây có gốc và hai nhánh trái/phải

Trong bài này, **cây nhị phân** gồm các nút; mỗi nút có tối đa **một con trái** và **một con phải**. Ta chọn một nút làm **gốc (root)**. Nút không có con nào là **lá (leaf)**; phần cây bắt đầu từ một nút là **cây con** của nút đó.

Ví dụ cây gồm bảy nút:

```text
               A
             /   \
            B     C
           / \   / \
          D   E F   G

Gốc: A
Con của A: trái B, phải C
Con của B: trái D, phải E
Con của C: trái F, phải G
Lá: D, E, F, G
```

Một **phép duyệt (traversal)** phải thăm mỗi nút cần xét đúng một lần theo thứ tự đã quy định. Trong các ví dụ, “xử lý” một nút đơn giản là **ghi giá trị nút vào danh sách kết quả**, nhưng trong ứng dụng thật có thể là kiểm tra, in thông tin, sao chép nút, tính biểu thức hoặc cập nhật dữ liệu tổng hợp.

Ba cách trên là ba kiểu **duyệt theo chiều sâu (Depth-First Search, DFS)**: từ một nút, ta tiếp tục đi xuống cây con trước khi quay lại xử lý nhánh kế tiếp. Chúng **khác** duyệt theo mức (*level-order* hay BFS) sử dụng queue để đi lần lượt theo tầng.

### Quy ước cần ghi nhớ

- **Trái trước phải:** cả ba cách trong bài đều duyệt **cây con trái trước cây con phải**. Nếu đảo hai nhánh, dãy kết quả sẽ khác.
- **Vị trí xử lý nút:** từ “trước”, “giữa”, “sau” nói về **thời điểm thực hiện công việc tại nút** so với hai cây con, không nói về vị trí nút trong hình vẽ.
- **Cây rỗng:** khi `root is None`, không có nút để xử lý; kết quả duyệt là dãy rỗng.
- **Nút lá:** không có cây con trái/phải; cả ba phép đều xử lý nút lá một lần, nhưng nút lá xuất hiện ở vị trí khác trong dãy tổng thể.

## 2. Ba quy tắc trên cùng một cây

Với mỗi nút có giá trị `N` và hai cây con `L` và `R`, ký hiệu `visit(N)` là thao tác xử lý nút. Ba công thức đệ quy:

| Kiểu duyệt | Thứ tự | Ghi nhớ |
|---|---|---|
| **Preorder** | `N → L → R` | **Gốc – Trái – Phải** |
| **Inorder** | `L → N → R` | **Trái – Gốc – Phải** |
| **Postorder** | `L → R → N` | **Trái – Phải – Gốc** |

Áp dụng lên cây ở phần 1:

```text
               A
             /   \
            B     C
           / \   / \
          D   E F   G
```

| Kiểu duyệt | Kết quả |
|---|---|
| **Preorder** | `A, B, D, E, C, F, G` |
| **Inorder** | `D, B, E, A, F, C, G` |
| **Postorder** | `D, E, B, F, G, C, A` |

Mỗi dãy có **bảy** giá trị, vì cây có bảy nút và mỗi nút được thăm đúng một lần. Chỉ **thứ tự** thay đổi.

### 2.1. Preorder: xử lý nút cha trước các con

Ở nút `A`, ta ghi `A` **ngay khi đến**, sau đó đi vào cây con `B` và cuối cùng cây con `C`:

```text
visit(A)
    visit(B)
        visit(D)
        visit(E)
    visit(C)
        visit(F)
        visit(G)

Kết quả: A B D E C F G
```

Tại mỗi nút, công việc tại nút xảy ra **trước khi** ta xử lý các con của nó. Vì vậy, preorder phù hợp khi muốn **thiết lập hoặc truyền thông tin từ cha xuống con**; chẳng hạn cấp phát một nút mới trước khi sao chép các nhánh của nó.

### 2.2. Inorder: xử lý nút giữa hai nhánh

Đối với gốc `A`, trước hết duyệt toàn bộ cây trái `B`, lúc đó ta đã có `D, B, E`; tiếp theo mới ghi `A`; cuối cùng duyệt cây phải `C` để có `F, C, G`:

```text
inorder(B)  = D B E
visit(A)    = A
inorder(C)  = F C G

Kết quả: D B E A F C G
```

Inorder có ý nghĩa đặc biệt với **cây tìm kiếm nhị phân (BST)**, vì các giá trị trong cây con trái thường nhỏ hơn nút hiện tại và các giá trị trong cây con phải thường lớn hơn. Khi bất biến BST đúng, duyệt giữa trái–gốc–phải cho dãy khóa đã sắp theo thứ tự tăng hoặc không giảm, tùy chính sách khóa trùng.

### 2.3. Postorder: xử lý nút cha sau các con

Để xử lý nút `B` theo postorder, ta xử lý `D`, `E` trước rồi mới `B`. Tương tự, xử lý `F`, `G` trước `C` và chỉ đến cuối cùng mới xử lý gốc `A`:

```text
postorder(B) = D E B
postorder(C) = F G C
visit(A)     = A

Kết quả: D E B F G C A
```

Postorder phù hợp cho các công việc cần **kết quả từ cả hai cây con trước khi tính nút cha**, ví dụ tính kích thước cây con, tính chiều cao, đánh giá biểu thức hoặc tháo bỏ toàn bộ cây từ dưới lên.

## 3. “Xử lý nút” khác với “đi qua nút”

Trong chương trình đệ quy, nút hiện tại có thể được **tham chiếu nhiều lần về mặt điều khiển**:

1. Vừa gọi hàm duyệt vào nút.
2. Quay lại nút sau khi đã duyệt xong nhánh trái.
3. Quay lại nút sau khi đã duyệt xong nhánh phải.

Ba kiểu duyệt chỉ khác ở việc đặt **hành động `visit` tại một trong ba thời điểm**. Không có nghĩa preorder chỉ “nhìn thấy” nút một lần và postorder chỉ “nhìn thấy” nút lúc cuối.

Xét nút `B` trong cây `A-B-C`:

| Thời điểm | Nếu dùng preorder | Nếu dùng inorder | Nếu dùng postorder |
|---|---|---|---|
| Vừa bước vào nút `B` | **Xử lý `B`** | Chưa xử lý | Chưa xử lý |
| Duyệt xong con trái `D` | `B` đã xử lý | **Xử lý `B`** | Chưa xử lý |
| Duyệt xong con phải `E` | `B` đã xử lý | `B` đã xử lý | **Xử lý `B`** |

Trong cả ba cách, ta vẫn phải khám phá các nhánh trái và phải. **Dời vị trí của câu lệnh xử lý** tạo ra thứ tự khác nhau, dù cấu trúc điều khiển đệ quy gần như giống hệt.

### Tại sao thứ tự xử lý lại quyết định tính đúng?

Giả sử nhiệm vụ là tính:

```text
size(node) = 1 + size(node.left) + size(node.right)
```

Ta **không thể hoàn tất phép gán `size(node)` từ kết quả cây con** trước khi tính xong `size(node.left)` và `size(node.right)`. Đó là lý do cách giải tự nhiên có bản chất **postorder**, dù các lệnh thăm nút có thể có thêm thao tác khác ở đầu hàm.

Ngược lại, nếu nhiệm vụ là **truyền một độ sâu đã biết từ nút cha xuống con**, ta có thể tính/ghi độ sâu của nút hiện tại trước, rồi truyền `depth + 1` khi duyệt xuống. Đó là cách nghĩ **preorder**.

## 4. Giả mã cho ba kiểu duyệt

Hãy để `VISIT(node)` biểu thị công việc thực tế tại nút:

### Preorder — gốc, trái, phải

```text
PREORDER(node):
    if node == NULL:
        return

    VISIT(node)
    PREORDER(node.left)
    PREORDER(node.right)
```

### Inorder — trái, gốc, phải

```text
INORDER(node):
    if node == NULL:
        return

    INORDER(node.left)
    VISIT(node)
    INORDER(node.right)
```

### Postorder — trái, phải, gốc

```text
POSTORDER(node):
    if node == NULL:
        return

    POSTORDER(node.left)
    POSTORDER(node.right)
    VISIT(node)
```

**Điểm khác biệt duy nhất ở ba đoạn giả mã là vị trí `VISIT(node)`.** Các trường hợp cơ sở và thứ tự đi vào con trái/con phải đều giống nhau.

Nếu `VISIT` có **tác dụng phụ** (ghi tệp, sửa dữ liệu, xóa nút, gửi sự kiện), đổi vị trí này có thể thay đổi hành vi đáng kể, không chỉ đổi dãy được in ra.

## 5. Python: một cấu trúc nút, ba cách duyệt

Ví dụ sau sử dụng nút nhị phân có `value`, `left`, `right`. Ba hàm nhận gốc cây và trả về **danh sách giá trị theo thứ tự đã thăm**.

```python
class Node:
    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right


def preorder(root):
    result = []

    def walk(node):
        if node is None:
            return
        result.append(node.value)
        walk(node.left)
        walk(node.right)

    walk(root)
    return result


def inorder(root):
    result = []

    def walk(node):
        if node is None:
            return
        walk(node.left)
        result.append(node.value)
        walk(node.right)

    walk(root)
    return result


def postorder(root):
    result = []

    def walk(node):
        if node is None:
            return
        walk(node.left)
        walk(node.right)
        result.append(node.value)

    walk(root)
    return result


#                 A
#               /   \
#              B     C
#             / \   / \
#            D   E F   G
root = Node(
    "A",
    left=Node("B", Node("D"), Node("E")),
    right=Node("C", Node("F"), Node("G")),
)

assert preorder(root) == ["A", "B", "D", "E", "C", "F", "G"]
assert inorder(root) == ["D", "B", "E", "A", "F", "C", "G"]
assert postorder(root) == ["D", "E", "B", "F", "G", "C", "A"]

# Cây rỗng không có giá trị để duyệt.
assert preorder(None) == []
assert inorder(None) == []
assert postorder(None) == []

# Một nút cho kết quả như nhau ở cả ba thứ tự.
leaf = Node("X")
assert preorder(leaf) == ["X"]
assert inorder(leaf) == ["X"]
assert postorder(leaf) == ["X"]
```

Đoạn mã tạo kết quả mới cho mỗi lời gọi, không sửa cây. Nếu muốn **xử lý trực tiếp** thay vì lưu các giá trị, có thể thay `result.append(node.value)` bằng hàm xử lý thích hợp. Khi đó cần cân nhắc tác dụng phụ và thời điểm đã hoàn tất xử lý các cây con.

### Kiểm tra cây lệch

Một cây không bắt buộc phải cân bằng. Ví dụ cây chỉ có con phải:

```text
A
 \
  B
   \
    C
```

Kết quả:

| Thứ tự | Dãy |
|---|---|
| Preorder | `A, B, C` |
| Inorder | `A, B, C` |
| Postorder | `C, B, A` |

Với cây chỉ có con trái:

```text
    A
   /
  B
 /
C
```

Preorder là `A, B, C`, còn inorder và postorder đều là `C, B, A`. Đây là ví dụ cho thấy **các dãy có thể trùng nhau trong một số cây đặc biệt**, nhưng quy tắc của ba kiểu duyệt vẫn khác nhau.

## 6. Cài đặt không đệ quy bằng stack

Đệ quy sử dụng **ngăn xếp lời gọi** của chương trình. Có thể thay nó bằng **stack tường minh**, hữu ích khi muốn kiểm soát quá trình duyệt hoặc tránh giới hạn độ sâu đệ quy của ngôn ngữ.

### 6.1. Preorder dùng stack

Với preorder, ta lấy một nút, xử lý ngay, rồi đưa **con phải trước, con trái sau** vào stack. Vì stack là LIFO, con trái được lấy ra trước.

```python
def preorder_iterative(root):
    if root is None:
        return []

    result = []
    stack = [root]

    while stack:
        node = stack.pop()
        result.append(node.value)

        if node.right is not None:
            stack.append(node.right)
        if node.left is not None:
            stack.append(node.left)

    return result


assert preorder_iterative(root) == preorder(root)
```

Nếu đẩy **trái trước, phải sau** lên stack thì nhánh phải sẽ được duyệt trước; đó là lỗi phổ biến khi chuyển từ đệ quy sang lặp.

### 6.2. Inorder dùng stack

Với inorder, trước tiên ta đi **hết về bên trái**, lưu những nút cha đang chờ trong stack. Khi không còn con trái, lấy một nút ra để xử lý rồi chuyển sang cây con phải.

```python
def inorder_iterative(root):
    result = []
    stack = []
    current = root

    while current is not None or stack:
        while current is not None:
            stack.append(current)
            current = current.left

        current = stack.pop()
        result.append(current.value)
        current = current.right

    return result


assert inorder_iterative(root) == inorder(root)
```

Trong đoạn này, một nút cha được **đẩy vào stack trước khi đi sâu xuống trái**, nhưng chỉ **xử lý sau khi quay lên từ nhánh trái**. Đó chính là thời điểm “giữa”.

### 6.3. Postorder dùng stack và cờ đã xử lý các con

Postorder cần trì hoãn xử lý nút cho tới khi hai cây con xong. Ta có thể lưu cặp `(node, expanded)`. Khi gặp một nút chưa mở rộng, đẩy lại chính nó với cờ `True`, rồi đẩy con phải và con trái để được lấy ra theo thứ tự trái trước.

```python
def postorder_iterative(root):
    if root is None:
        return []

    result = []
    stack = [(root, False)]

    while stack:
        node, expanded = stack.pop()

        if expanded:
            result.append(node.value)
        else:
            # Nút sẽ được xử lý sau khi hai cây con đã xong.
            stack.append((node, True))
            if node.right is not None:
                stack.append((node.right, False))
            if node.left is not None:
                stack.append((node.left, False))

    return result


assert postorder_iterative(root) == postorder(root)
assert postorder_iterative(None) == []
```

Ở đây, `expanded=True` không có nghĩa đã xử lý nút, mà có nghĩa **lượt mở rộng các con đã được lên lịch**; khi lấy lại nút có cờ đó khỏi stack, hai cây con đã được xử lý. Cách này dễ kiểm tra hơn một số biến thể tối ưu bộ nhớ bằng “nút vừa thăm”.

### So sánh đệ quy và stack tường minh

| Tiêu chí | Đệ quy | Stack tường minh |
|---|---|---|
| Diễn đạt ba quy tắc | Rất ngắn, dễ sát định nghĩa | Nhiều bước kiểm soát trạng thái |
| Trạng thái chờ | Lưu trong call stack | Lưu trong `list`/stack do ta quản lý |
| Cây quá sâu | Có thể gặp giới hạn đệ quy | Không bị giới hạn bởi độ sâu đệ quy, nhưng vẫn cần bộ nhớ |
| Thứ tự con trái/phải | Thể hiện trực tiếp trong lời gọi | Phải chú ý tính LIFO của stack |
| Thời gian tổng | O(n) | O(n) |

Việc chọn biểu diễn lặp không làm thay đổi **thứ tự logic của nút** nếu thuật toán được viết đúng.

## 7. Ý nghĩa thực tiễn: chọn thứ tự xử lý theo phụ thuộc dữ liệu

Ba kiểu duyệt không chỉ là ba cách in nút. Ta chọn chúng theo **chiều phụ thuộc giữa cha và con**.

### 7.1. Preorder: xử lý từ trên xuống

Tình huống điển hình:

- Ghi tên thư mục trước rồi xử lý các thư mục con.
- Gán độ sâu, đường dẫn hoặc cấu hình cho nút con dựa trên thông tin đã có ở cha.
- Tạo bản sao nút cha trước khi gắn các bản sao cây con.
- Xuất biểu diễn **tiền tố (prefix)** của cây biểu thức.

Ví dụ truyền độ sâu xuống từng nút:

```python
def list_values_with_depth(root):
    result = []

    def walk(node, depth):
        if node is None:
            return
        result.append((node.value, depth))  # Xử lý cha trước.
        walk(node.left, depth + 1)
        walk(node.right, depth + 1)

    walk(root, 0)
    return result


assert list_values_with_depth(root) == [
    ("A", 0), ("B", 1), ("D", 2), ("E", 2),
    ("C", 1), ("F", 2), ("G", 2)
]
```

Tại đây độ sâu của con cần thông tin từ cha. Preorder hợp với luồng xử lý **top-down (từ trên xuống)**.

### 7.2. Inorder: đặt nút giữa hai cây con

Tình huống điển hình:

- Xuất các khóa của một **BST** theo thứ tự đã sắp.
- Biểu diễn toán tử nhị phân **giữa hai toán hạng** trong cây biểu thức.
- Duyệt cấu trúc nhị phân mà vị trí “trái trước, phải sau” mang ý nghĩa riêng.

Ví dụ một cây tìm kiếm nhị phân hợp lệ:

```text
                8
              /   \
             4     12
            / \   /  \
           2   6 10  14

BST: mọi khóa bên trái < nút < mọi khóa bên phải.
```

Với cây này:

```text
Preorder : 8, 4, 2, 6, 12, 10, 14
Inorder  : 2, 4, 6, 8, 10, 12, 14
Postorder: 2, 6, 4, 10, 14, 12, 8
```

**Duyệt giữa cho thứ tự tăng là nhờ bất biến BST**, không phải đặc tính của **mọi** cây nhị phân. Nếu một nút trái có giá trị lớn hơn cha trong cây bất kỳ, inorder vẫn thăm trái–gốc–phải nhưng dãy giá trị không nhất thiết được sắp.

```python
bst = Node(
    8,
    Node(4, Node(2), Node(6)),
    Node(12, Node(10), Node(14)),
)

assert inorder(bst) == [2, 4, 6, 8, 10, 12, 14]
```

Nếu BST cho phép khóa trùng, quy tắc đặt khóa trùng vào cây trái/phải phải được xác định nhất quán; kết quả inorder thường là **không giảm** thay vì tăng nghiêm ngặt.

### 7.3. Postorder: tổng hợp từ dưới lên

Tình huống điển hình:

- Tính **kích thước cây con**, tổng giá trị hoặc chiều cao của một nút.
- Đánh giá cây biểu thức khi toán tử cần kết quả hai toán hạng.
- Giải phóng hoặc tháo cấu trúc khi phải xử lý con trước cha.
- Biến đổi cây theo công thức cần kết quả của các cây con.

Ví dụ tính **số nút trong mỗi cây con**:

```python
def annotate_subtree_sizes(node):
    if node is None:
        return 0

    left_size = annotate_subtree_sizes(node.left)
    right_size = annotate_subtree_sizes(node.right)

    # Đến đây đã có kết quả của cả hai cây con.
    node.subtree_size = 1 + left_size + right_size
    return node.subtree_size


assert annotate_subtree_sizes(root) == 7
assert root.subtree_size == 7
assert root.left.subtree_size == 3
assert root.right.subtree_size == 3
assert root.left.left.subtree_size == 1
```

Ở đây, hành động gán `node.subtree_size` chỉ chính xác **sau khi** các giá trị `left_size` và `right_size` đã sẵn sàng. Đó là luồng xử lý **bottom-up (từ dưới lên)**.

### 7.4. Cây biểu thức: tiền tố, trung tố, hậu tố

Xét biểu thức `(2 + 3) * 5` được biểu diễn thành cây:

```text
               (*)
              /   \
            (+)    5
           /   \
          2     3
```

| Kiểu duyệt | Dãy nút | Diễn giải |
|---|---|---|
| Preorder | `*, +, 2, 3, 5` | Biểu thức **tiền tố (prefix)**: toán tử trước toán hạng |
| Inorder | `2, +, 3, *, 5` | Biểu thức **trung tố (infix)**: toán tử giữa hai toán hạng |
| Postorder | `2, 3, +, 5, *` | Biểu thức **hậu tố (postfix)**: toán tử sau toán hạng |

Một điểm quan trọng: **chuỗi inorder đơn thuần không mang đủ dấu ngoặc**. Nếu chỉ in `2 + 3 * 5` mà không thêm ngoặc từ cấu trúc cây, cách hiểu theo độ ưu tiên toán tử thông thường sẽ là `2 + (3 * 5)`, **khác** với cây `(2 + 3) * 5`. Khi xuất trung tố từ cây biểu thức, cần giữ dấu ngoặc hoặc quy tắc ưu tiên/kết hợp tương ứng.

Mã kiểm tra ba thứ tự trên cây biểu thức:

```python
expr = Node(
    "*",
    Node("+", Node(2), Node(3)),
    Node(5),
)

assert preorder(expr) == ["*", "+", 2, 3, 5]
assert inorder(expr) == [2, "+", 3, "*", 5]
assert postorder(expr) == [2, 3, "+", 5, "*"]
```

Một trình đánh giá biểu thức đệ quy cũng có bản chất postorder: cần tính giá trị hai cây con trước rồi mới áp dụng toán tử ở nút cha.

```python
def evaluate_expression(node):
    if node is None:
        raise ValueError("Biểu thức không được rỗng")

    # Lá là toán hạng dạng số trong ví dụ.
    if node.left is None and node.right is None:
        return node.value

    if node.left is None or node.right is None:
        raise ValueError("Toán tử nhị phân phải có đủ hai con")

    left_value = evaluate_expression(node.left)
    right_value = evaluate_expression(node.right)

    if node.value == "+":
        return left_value + right_value
    if node.value == "*":
        return left_value * right_value
    raise ValueError("Toán tử không được hỗ trợ")


assert evaluate_expression(expr) == 25
```

Đoạn mã chỉ hỗ trợ hai toán tử `+` và `*` trên các lá số, nhằm làm rõ **thời điểm tính nút cha**. Nó chưa phải trình phân tích/đánh giá mọi biểu thức số học.

## 8. So sánh với duyệt theo mức (BFS)

Duyệt trước, giữa, sau đều là **DFS theo thứ tự đệ quy**. Để đối chiếu, **duyệt theo mức (level-order)** dùng queue FIFO và xử lý các nút ở cùng độ sâu trước khi chuyển xuống mức tiếp theo.

Với cây bảy nút:

```text
               A
             /   \
            B     C
           / \   / \
          D   E F   G

Preorder   : A B D E C F G
Inorder    : D B E A F C G
Postorder  : D E B F G C A
Level-order: A B C D E F G
```

Ví dụ BFS trên cây:

```python
from collections import deque


def level_order(root):
    if root is None:
        return []

    result = []
    queue = deque([root])

    while queue:
        node = queue.popleft()
        result.append(node.value)

        if node.left is not None:
            queue.append(node.left)
        if node.right is not None:
            queue.append(node.right)

    return result


assert level_order(root) == ["A", "B", "C", "D", "E", "F", "G"]
```

Nếu bài toán cần xử lý **từng tầng**, ví dụ tìm khoảng cách nhỏ nhất tính bằng số cạnh trên cây, level-order thường tự nhiên hơn. Nếu cần **thăm toàn bộ nhánh và kiểm soát thời điểm xử lý cha/con**, ba phép DFS của bài là công cụ thích hợp.

## 9. Phân tích độ phức tạp thời gian và bộ nhớ

Gọi:

- `n` là số nút trong cây.
- `h` là số **mức** trên đường dài nhất từ gốc đến lá; cây rỗng có `h = 0`, cây một nút có `h = 1`. Nếu định nghĩa chiều cao theo **số cạnh**, độ lớn ngăn xếp chỉ khác một hằng số.
- `w` là số nút lớn nhất trên một mức cây.

| Phép duyệt | Thời gian | Bộ nhớ phụ để điều khiển duyệt | Nếu trả về danh sách n giá trị |
|---|---:|---:|---:|
| Preorder DFS đệ quy | **O(n)** | **O(h)** call stack | Thêm O(n) bộ nhớ kết quả |
| Inorder DFS đệ quy | **O(n)** | **O(h)** call stack | Thêm O(n) |
| Postorder DFS đệ quy | **O(n)** | **O(h)** call stack | Thêm O(n) |
| Preorder/Inorder/Postorder lặp bằng stack | **O(n)** | **O(h)** với cách cài đặt nêu trên | Thêm O(n) |
| Level-order dùng queue | **O(n)** | **O(w)** cho số nút chờ theo mức, tối đa O(n) | Thêm O(n) |

**Vì sao O(n) thời gian?** Mỗi nút được xử lý đúng một lần và mỗi liên kết con được xét một số lần hằng số. Với `VISIT` có chi phí O(1), tổng là O(n). Nếu công việc `VISIT` tự nó mất nhiều hơn O(1), phải cộng thêm chi phí đó; ví dụ in một chuỗi có độ dài biến đổi theo nút không còn là thao tác hằng số theo kích thước đầu ra.

**Vì sao O(h) bộ nhớ DFS?** Khi đi sâu xuống một nhánh, thuật toán cần nhớ các nút tổ tiên đang chờ quay lại. Số tổ tiên trên một đường không vượt quá chiều cao cây. Trong cài đặt postorder lặp dùng cờ, có thể có một vài mục stack cho mỗi mức, nhưng vẫn O(h) trên cây nhị phân.

- **Cây cân bằng:** `h = O(log n)`; DFS chỉ cần O(log n) bộ nhớ điều khiển.
- **Cây lệch như danh sách liên kết:** `h = O(n)`; đệ quy hoặc stack tường minh có thể cần O(n) bộ nhớ.
- **Cây rộng:** BFS có thể phải giữ O(n) nút trong queue khi một mức chứa rất nhiều nút.

Trong Python, cây lệch quá sâu có thể gây `RecursionError` vì vượt giới hạn đệ quy. **Duyệt lặp dùng stack tường minh** có thể tránh giới hạn call stack, dù không làm giảm số nút phải xử lý hoặc lượng bộ nhớ cần thiết theo trường hợp xấu nhất.

### Độ phức tạp khi dùng kết quả của cây con

Nếu tính các đại lượng tổng hợp như kích thước cây con bằng postorder, mỗi nút kết hợp kết quả hai con trong O(1), nên toàn bộ cũng O(n) thời gian và O(h) ngăn xếp lời gọi. Nếu gán một thuộc tính tại **mỗi nút** như `subtree_size`, phần lưu thuộc tính nằm trong cây và cần O(n) vị trí tổng cộng, khác với bộ nhớ điều khiển duyệt.

## 10. Bất biến và cách chứng minh kết quả

Có thể chứng minh bằng quy nạp theo số nút của một cây con.

### Cơ sở: cây rỗng và cây một nút

- **Cây rỗng:** cả ba hàm trả dãy rỗng, nên không bỏ sót nút nào.
- **Cây một nút `X`:** các lời gọi cây con trái/phải đều trả rỗng; mỗi cách xử lý `X` đúng một lần. Dãy là `[X]`.

### Bước quy nạp: cây có gốc N và hai cây con L, R

Giả sử thuật toán xử lý đúng mỗi nút đúng một lần, theo thứ tự được định nghĩa, trong hai cây con `L` và `R`.

- **Preorder** ghép `[N] + preorder(L) + preorder(R)`, nên `N` đứng trước tất cả nút con, còn thứ tự bên trong hai cây con vẫn đúng.
- **Inorder** ghép `inorder(L) + [N] + inorder(R)`, nên toàn bộ cây trái đứng trước `N` và toàn bộ cây phải đứng sau `N`.
- **Postorder** ghép `postorder(L) + postorder(R) + [N]`, nên `N` chỉ được xử lý sau khi mọi nút trong hai cây con đã xử lý.

Vì các cây con của một **cây thực sự** không chia sẻ nút, ba dãy ghép không đếm trùng nút. Vậy cả ba cách đều thăm đúng `n` nút và bảo đảm đúng thứ tự quy ước.

Điều kiện “cây thực sự” rất quan trọng: nếu một nút được **hai cha cùng tham chiếu**, cấu trúc đã thành một đồ thị có hướng dùng chung nút (*DAG*) chứ không còn là cây đúng nghĩa theo giả định. Khi đó thuật toán trên có thể **thăm một nút nhiều lần**; nếu có chu trình, đệ quy thậm chí không kết thúc. Muốn duyệt đồ thị tổng quát, cần quy tắc đánh dấu nút đã thăm.

## 11. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Quên trường hợp `node is None` | Truy cập thuộc tính của `None`, lỗi lúc chạm lá | Kiểm tra trường hợp cơ sở trước |
| Preorder đặt `visit` sau hai nhánh | Biến thành postorder | Đặt `visit` **trước** hai lời gọi |
| Inorder xử lý nút trước khi duyệt trái | Kết quả không còn trái–gốc–phải | Đặt `visit` **giữa** hai lời gọi |
| Postorder xử lý cha khi con chưa xong | Tính tổng hợp thiếu dữ liệu | Chỉ xử lý cha **sau** cả hai cây con |
| Đẩy con trái rồi con phải lên stack cho preorder | LIFO khiến duyệt **phải trước trái** | Đẩy **phải trước, trái sau** |
| Khi lặp inorder, bỏ qua trạng thái trở lại từ cây trái | Thăm nút không đúng vị trí giữa | Dùng stack lưu các nút tổ tiên |
| Nhầm inorder với sắp xếp mọi cây nhị phân | Kết luận sai khi cây không phải BST | Chỉ có thứ tự khóa khi **bất biến BST** đúng |
| Quên ngoặc của cây biểu thức ở biểu diễn trung tố | Diễn giải sai cây theo ưu tiên toán tử | Thêm dấu ngoặc hoặc quy tắc xuất biểu thức tương ứng |
| Coi preorder riêng lẻ đủ tái tạo mọi cây | Nhiều cấu trúc cây có thể có cùng dãy preorder | Cần thông tin cấu trúc bổ sung, chẳng hạn dấu nút rỗng |
| Đệ quy trên cây cực sâu | Có thể vượt giới hạn stack | Chọn cài đặt lặp khi cần |
| Duyệt nhầm cấu trúc có chu trình như cây | Lặp vô hạn hoặc đếm trùng | Kiểm tra giả định cây hoặc dùng tập đã thăm cho đồ thị |
| Sửa liên kết con trong lúc duyệt mà không xét thứ tự | Bỏ qua nhánh hoặc duyệt nhánh sai | Giữ tham chiếu cần dùng trước khi biến đổi |

### Một lưu ý về khôi phục cây từ dãy duyệt

**Chỉ một dãy preorder, inorder hoặc postorder nói chung không đủ để xác định duy nhất cấu trúc cây nhị phân.** Ví dụ các cây có một gốc và chỉ một nút con ở bên trái hoặc bên phải có thể cho cùng một preorder nếu nhãn nút tương ứng như nhau.

Để khôi phục cây, thường cần thêm thông tin: chẳng hạn **preorder + inorder** hoặc **postorder + inorder** với giá trị nút **phân biệt**; hoặc một chuỗi preorder có **ký hiệu cho nhánh rỗng** được mã hóa nhất quán. Nếu có khóa trùng, việc khôi phục còn phải giải quyết nhập nhằng.

## 12. Bài tập tự luyện có lời giải

**Bài 1 — Ba dãy duyệt.** Cho cây:

```text
      M
     / \
    J   R
       /
      P
```

Hãy viết preorder, inorder và postorder.

*Lời giải:* Preorder **`M, J, R, P`** (gốc trước); inorder **`J, M, P, R`** (trái–gốc–phải); postorder **`J, P, R, M`** (con trước cha).

**Bài 2 — Chọn kiểu duyệt.** Bạn cần tính số nút của mọi cây con, trong đó số nút tại cha bằng 1 cộng số nút của con trái và con phải. Nên xử lý nút cha trước hay sau các con?

*Lời giải:* **Sau các con (postorder)**, vì phải biết kích thước hai cây con trước khi tính và gán kích thước của cha.

**Bài 3 — Cây tìm kiếm nhị phân.** Một BST có khóa `[2, 4, 6, 8, 10, 12, 14]`, được bố trí cân bằng như ví dụ trong bài. Kiểu duyệt nào cho khóa tăng dần?

*Lời giải:* **Inorder** trái–gốc–phải, nhờ bất biến BST. Không thể kết luận như vậy cho cây nhị phân bất kỳ.

**Bài 4 — Cây biểu thức.** Với cây gốc `-`, con trái là số `9`, con phải là cây `*` có hai lá `2` và `3`. Hãy viết biểu diễn tiền tố và hậu tố.

*Lời giải:* Tiền tố: **`- 9 * 2 3`**. Hậu tố: **`9 2 3 * -`**. Kết quả biểu thức là `9 - (2 * 3) = 3`.

**Bài 5 — Duyệt lặp.** Muốn preorder trái trước phải bằng stack, tại sao phải đẩy con phải lên stack trước con trái?

*Lời giải:* Vì stack **LIFO**. Đẩy phải trước làm con trái nằm ở đỉnh và được lấy ra xử lý trước.

**Bài 6 — Chiều cao cây.** So sánh bộ nhớ điều khiển preorder đệ quy trên cây cân bằng có `n` nút và cây lệch có `n` nút.

*Lời giải:* Cây cân bằng có độ sâu O(log n), nên call stack O(log n). Cây lệch có độ sâu O(n), nên call stack O(n).

**Bài 7 — Thứ tự khác nhau.** Có đúng là mọi cây nhị phân có ít nhất hai nút đều cho ba dãy preorder/inorder/postorder khác nhau không?

*Lời giải:* **Không.** Với cây chỉ có các nhánh phải, preorder và inorder có thể cùng thứ tự; với cây chỉ có các nhánh trái, inorder và postorder có thể trùng nhau. Quy tắc duyệt vẫn khác.

**Bài 8 — DFS hay BFS?** Cần in các nút theo từng mức độ sâu, hoàn tất mức `d` trước khi xử lý mức `d+1`. Nên chọn kiểu nào?

*Lời giải:* **Level-order/BFS** dùng queue, không phải một trong ba kiểu DFS. Với cây `A, B, C, D, E, F, G` trong bài, level-order là `A, B, C, D, E, F, G`.

**Bài 9 — Tính đúng đắn.** Nếu code postorder xử lý nút cha ngay sau khi duyệt xong **cây trái**, trước khi duyệt cây phải, thì đó còn là postorder không?

*Lời giải:* **Không.** Đó là **inorder** trái–gốc–phải. Postorder chỉ xử lý cha sau **cả cây trái và cây phải**.

**Bài 10 — Tái dựng cây.** Có thể khôi phục chính xác mọi cây nhị phân chỉ từ dãy preorder `[A, B]` không?

*Lời giải:* **Không.** `B` có thể là con trái hoặc con phải của `A`, và hai cây này có cùng preorder. Cần thông tin bổ sung về cấu trúc.

**Ghi nhớ:** Với cây nhị phân, **preorder = gốc–trái–phải** phù hợp xử lý từ **cha xuống con**; **inorder = trái–gốc–phải** đặc biệt hữu ích để đọc khóa **BST** theo thứ tự; **postorder = trái–phải–gốc** phù hợp tính toán hoặc biến đổi từ **con lên cha**. Cả ba đều thăm mỗi nút đúng một lần, thường **O(n) thời gian** và **O(h) bộ nhớ điều khiển** khi `h` là chiều cao cây. Thứ tự xử lý được chọn theo **phụ thuộc dữ liệu**, không chỉ theo hình vẽ của cây.
