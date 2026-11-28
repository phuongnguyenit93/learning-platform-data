# Biểu diễn cây bằng liên kết cha–con

## 1. Bài toán: biến quan hệ phân cấp thành dữ liệu trong bộ nhớ

Trong học phần **Cấu trúc dữ liệu**, cây (*tree*) mô tả một tập hợp nút có quan hệ phân cấp. Ví dụ, một thư mục có thể chứa nhiều thư mục con; một mục của danh mục học tập có nhiều mục cấp dưới; một biểu thức có các thành phần con. Để chương trình duyệt, sửa, tìm đường đi hoặc tính độ phức tạp của những cấu trúc ấy, ta cần chọn **cách biểu diễn cây trong bộ nhớ**.

Một lựa chọn phổ biến là lưu các **liên kết cha–con**:

- Mỗi nút biết **cha trực tiếp** của nó, trừ nút gốc.
- Mỗi nút biết những **con trực tiếp** của nó, nếu có.
- Từ gốc, có thể đi qua các liên kết con để tới toàn bộ nút.

Trong bài này, ta nghiên cứu **cây tổng quát có gốc (general rooted tree)**: một nút có thể có **0, 1, 2 hoặc nhiều con**, không bị giới hạn bởi số hai như cây nhị phân. Nội dung tập trung vào **bất biến của liên kết**, các cấu trúc lưu trữ, cách cập nhật an toàn và chi phí thời gian–bộ nhớ khi thao tác.

**Điểm quan trọng:** cây là một quan hệ toán học; `parent`, `children`, mảng, danh sách liên kết hay con trỏ chỉ là các **phương án biểu diễn quan hệ đó**. Chọn phương án nào phụ thuộc vào thao tác mà bài toán cần thực hiện thường xuyên.

## 2. Mô hình cây có gốc và các quan hệ trực tiếp

Xét cây sau, trong đó mỗi cạnh đi từ cha ở phía trên tới con ở phía dưới:

```text
                      R
                   /  |  \
                  A   B   C
                 / \   \
                D   E   F
                    |
                    G

Gốc: R
Danh sách cạnh cha → con:
R→A, R→B, R→C, A→D, A→E, B→F, E→G
```

Từ hình vẽ:

- `R` là **gốc (root)**, không có cha.
- `parent(A)=R`, `parent(E)=A`, `parent(G)=E`.
- `children(R)=[A,B,C]`, `children(A)=[D,E]`, `children(E)=[G]`.
- `C,D,F,G` là **lá (leaves)** vì không có con.
- `R,A,B,E` là **nút trong (internal nodes)** vì có ít nhất một con.
- `D` và `E` là **anh em (siblings)** vì có cùng cha `A`.
- `R,A,E` là **tổ tiên (ancestors)** của `G`; chỉ `E` là **cha trực tiếp** của `G`.

Ở đây có `n=8` nút và `7=n-1` cạnh.

Cây có gốc hợp lệ thỏa các điều kiện:

1. Có đúng **một gốc** (nếu cây không rỗng).
2. Gốc có **0 cha**; mỗi nút khác có **đúng 1 cha**.
3. Mỗi nút có đường đi từ gốc, không có thành phần bị tách rời.
4. Không có **chu trình cha–con**.
5. Mỗi cạnh cha–con nối **hai nút khác nhau** và mỗi nút con chỉ xuất hiện một lần dưới một cha.

Khi biểu diễn cây bằng **hai chiều liên kết** — từ cha tới con và từ con về cha — chúng ta còn phải bảo đảm hai chiều này **đồng bộ**.

### Cây có thứ tự hay không có thứ tự?

Ví dụ viết `children(R)=[A,B,C]` sử dụng **danh sách có thứ tự**. Đây là lựa chọn phù hợp với menu, mục lục hoặc tài liệu mà thứ tự con có ý nghĩa. Trong một **cây không có thứ tự (unordered tree)**, ta chỉ cần biết tập con của `R` là `{A,B,C}`; thứ tự trình bày không phải một phần của cấu trúc toán học.

Do đó, trước khi chọn `list`, `set` hoặc một danh sách liên kết, hãy quyết định **thứ tự con có bắt buộc được duy trì không**.

## 3. Biểu diễn trực tiếp: mỗi nút có `parent` và `children`

Một cách cài đặt tự nhiên là mỗi nút có ba phần thông tin:

```text
TreeNode
┌─────────────────────────┐
│ value: dữ liệu của nút   │
│ parent: cha hoặc None   │
│ children: danh sách con │
└─────────────────────────┘
```

Trong Python, ta có thể hình dung:

```python
class TreeNode:
    def __init__(self, value):
        self.value = value
        self.parent = None
        self.children = []
```

Ở mô hình này:

- `node.parent` trả về cha trực tiếp hoặc `None` nếu là gốc.
- `node.children` liệt kê các con trực tiếp.
- `len(node.children)` là số con của nút.
- `not node.children` cho biết nút có phải là lá không.
- Chỉ cần giữ một tham chiếu tới **gốc** là có thể truy cập toàn bộ nút bằng cách lần theo danh sách con, **nếu bất biến cây được duy trì**.

Biểu diễn này có hai dạng tham chiếu:

```text
        parent
          ▲
          │
          B ─────────► F
          │ children   (cạnh B→F)
          ▼
        children

Quan hệ B là cha của F được lưu ở cả:
    F.parent = B
    B.children chứa F
```

Với cây `n≥1` nút:

- Có `n-1` liên kết cha khác `None`.
- Có tổng cộng `n-1` mục con trên tất cả danh sách `children`.
- Dữ liệu liên kết vì thế tốn **`O(n)` bộ nhớ**, chưa kể kích thước `value`.

Biểu diễn hai chiều tạo một **đánh đổi**: tốn thêm tham chiếu cha so với chỉ lưu con, nhưng tra cứu cha trực tiếp rất nhanh. Đồng thời, mỗi lần thay đổi cây phải cập nhật **cả hai hướng** thật nhất quán.

## 4. Bất biến hai chiều quan trọng nhất

Đối với hai nút khác nhau `u`, `v`, ta muốn:

\[
v\in\operatorname{children}(u)
\quad\Longleftrightarrow\quad
\operatorname{parent}(v)=u.
\]

Điều này có nghĩa:

- Nếu `u.children` chứa `v` thì `v.parent` **phải là chính đối tượng `u`**.
- Nếu `v.parent` là `u` thì danh sách con của `u` **phải chứa `v` đúng một lần**.
- Không có một đối tượng `v` nằm trong danh sách con của hai cha khác nhau.
- Nút gốc có `parent=None`, và không xuất hiện trong danh sách con của nút nào.
- Không có đường từ một nút đi xuống các con rồi quay lại chính nút đó.

### Ví dụ biểu diễn sai

```text
R.children = [A, B]
A.parent = R
B.parent = C          ← SAI: B được liệt kê dưới R nhưng trỏ cha C
```

Hoặc:

```text
R.children = [A, A]   ← SAI: cùng một nút A xuất hiện hai lần
A.parent = R
```

Hoặc:

```text
A.children = [B]
B.children = [C]
C.children = [A]      ← SAI: tạo chu trình A→B→C→A
```

Các trường hợp này không chỉ gây sai số lượng nút. Chúng có thể làm cho thuật toán tính tổ tiên không kết thúc, duyệt cây thăm lặp hoặc một thao tác “xóa cây con” xóa nhầm vùng dữ liệu.

### Tại sao `n-1` liên kết chưa đủ?

Một cấu trúc có `n` nút và `n-1` cạnh chưa chắc là cây nếu có **chu trình và nút bị cô lập**. Ví dụ, ba nút `A,B,C` tạo chu trình và nút `D` đứng riêng: có `4` nút, `3` cạnh nhưng không liên thông.

Vì vậy, khi **kiểm tra toàn bộ dữ liệu**, chỉ đối chiếu số liên kết là điều kiện cần; phải kiểm tra thêm tính thống nhất hai chiều, **mọi nút thuộc cùng gốc** và **không chu trình**.

## 5. Cài đặt Python: tạo cây và chỉ cho chỉnh qua API

Để tránh thay đổi nửa chừng, ta tạo lớp `TreeNode` có các phương thức:

- `add_child(child)`: gắn một **gốc cây con đang tách rời** thành con mới.
- `detach()`: tách cây con gốc tại nút đang xét khỏi cha cũ.
- `move_to(new_parent)`: chuyển một cây con đang có cha sang cha mới, sau khi kiểm tra không tạo chu trình.
- `is_root()`, `is_leaf()`, `child_count()`: các truy vấn cơ bản.

Các phương thức sau giả định đầu vào trước thao tác là **các cây hợp lệ**, thao tác không chạy đồng thời với việc sửa liên kết khác, và không có lỗi cấp phát bộ nhớ bất thường trong quá trình cập nhật.

```python
class TreeNode:
    def __init__(self, value):
        self.value = value
        self.parent = None
        self.children = []

    def is_root(self):
        return self.parent is None

    def is_leaf(self):
        return len(self.children) == 0

    def child_count(self):
        return len(self.children)

    def add_child(self, child):
        if not isinstance(child, TreeNode):
            raise TypeError("child phải là một TreeNode")

        if child.parent is not None:
            raise ValueError("child đã có cha; cần tháo hoặc chuyển cây con")

        # Không thể gắn một tổ tiên thành con của hậu duệ.
        ancestor = self
        while ancestor is not None:
            if ancestor is child:
                raise ValueError("phép gắn này sẽ tạo chu trình")
            ancestor = ancestor.parent

        self.children.append(child)
        child.parent = self

    def detach(self):
        """Tháo toàn bộ cây con này khỏi cha cũ."""
        if self.parent is None:
            return False

        old_parent = self.parent
        old_parent.children.remove(self)
        self.parent = None
        return True

    def move_to(self, new_parent):
        """Chuyển cây con này sang nút cha mới."""
        if not isinstance(new_parent, TreeNode):
            raise TypeError("new_parent phải là một TreeNode")

        if self.parent is None:
            raise ValueError("nút gốc chưa có cha; dùng add_child để ghép cây")

        if self.parent is new_parent:
            return False  # Không thay đổi vị trí

        # Kiểm tra TRƯỚC khi sửa các liên kết.
        ancestor = new_parent
        while ancestor is not None:
            if ancestor is self:
                raise ValueError("không thể chuyển vào chính cây con của mình")
            ancestor = ancestor.parent

        old_parent = self.parent

        # Phụ thuộc giả định không có sửa đồng thời/lỗi cấp phát:
        new_parent.children.append(self)
        old_parent.children.remove(self)
        self.parent = new_parent
        return True
```

### 5.1. Dựng cây ví dụ

```python
nodes = {name: TreeNode(name) for name in "RABCDEFG"}

nodes["R"].add_child(nodes["A"])
nodes["R"].add_child(nodes["B"])
nodes["R"].add_child(nodes["C"])
nodes["A"].add_child(nodes["D"])
nodes["A"].add_child(nodes["E"])
nodes["B"].add_child(nodes["F"])
nodes["E"].add_child(nodes["G"])

root = nodes["R"]

print(root.is_root())             # True
print(root.child_count())         # 3
print(nodes["G"].parent.value)    # E
print(nodes["C"].is_leaf())       # True
print(nodes["B"].child_count())   # 1
```

Từ một tham chiếu `root`, ta có thể lần theo `children` để tới mọi nút; nếu cần đi ngược từ `G` về gốc, ta theo `G.parent → E.parent → A.parent → R`.

### 5.2. Vì sao dùng **định danh đối tượng** thay vì giá trị?

Hai nút khác nhau có thể cùng chứa một giá trị `"A"` nhưng là **hai đối tượng riêng biệt**. Không nên xác định cha, tổ tiên hoặc chu trình bằng cách so sánh `node.value`.

Trong lớp trên, phép so sánh `is` phân biệt **đúng đối tượng**. Nó cũng tránh việc hai nút có cùng nhãn bị hiểu nhầm là một nút duy nhất. Nếu ứng dụng cần tra cứu theo mã nghiệp vụ, hãy sử dụng một **định danh duy nhất** cho từng nút hoặc một bảng tra mã → nút.

Trong mã minh họa, `children` và `parent` là thuộc tính có thể bị sửa trực tiếp. Một thư viện thực tế nên đóng gói các liên kết này và chỉ cho thay đổi qua API duy trì bất biến; nếu mã bên ngoài viết `node.parent = other` mà không cập nhật danh sách con, cấu trúc sẽ mất đồng bộ.

## 6. Gắn, tháo và chuyển cây con: thay đổi cả hai chiều

### 6.1. Gắn một nút lá mới

Nếu `C` ban đầu là lá, ta có thể thêm một nút `H` làm con:

```python
h = TreeNode("H")
nodes["C"].add_child(h)

print(h.parent.value)        # C
print(nodes["C"].is_leaf())  # False
print(h.is_leaf())           # True
```

Sau khi thêm:

- `C.children` có thêm `H`.
- `H.parent` trỏ tới `C`.
- Số nút và số cạnh cùng tăng `1`, vẫn thỏa `|E|=|V|-1`.
- `C` chuyển từ lá thành nút trong; `H` là lá.

### 6.2. Tháo cây con

Trong cây mẫu, `E` có một con `G`. Khi gọi `nodes["E"].detach()`, ta **chỉ xóa cạnh `A→E`**, không xóa `E` hay `G`:

```python
print(nodes["E"].detach())   # True
print(nodes["E"].parent)     # None
print(nodes["G"].parent.value)  # E
```

Sau đó tồn tại **hai cây riêng biệt**:

- Cây thứ nhất có gốc `R` và không còn `E,G`.
- Cây thứ hai có gốc `E`, vẫn chứa con `G`.

Nếu coi toàn bộ các nút ban đầu là một tập, cấu trúc hiện tại là **rừng (forest)**, không phải một cây duy nhất. **Tháo liên kết** và **xóa dữ liệu nút** là hai thao tác khác nhau.

### 6.3. Chuyển cây con sang cha mới

Giả sử ta đang có cây nguyên vẹn, và muốn chuyển `E` từ dưới `A` sang dưới `C`. Ta cần:

1. Kiểm tra `C` **không nằm trong cây con của `E`**.
2. Loại `E` khỏi `A.children`.
3. Thêm `E` vào `C.children`.
4. Đổi `E.parent` từ `A` sang `C`.
5. Giữ nguyên quan hệ bên trong cây con `E→G`.

Với lớp ở trên, có thể thao tác từ cây mẫu đã khởi tạo:

```python
# Dùng một bản cây mới nếu đã thực hiện detach ở mục 6.2.
fresh = {name: TreeNode(name) for name in "RABCDEFG"}
for parent, child in [
    ("R", "A"), ("R", "B"), ("R", "C"),
    ("A", "D"), ("A", "E"), ("B", "F"), ("E", "G")
]:
    fresh[parent].add_child(fresh[child])

print(fresh["E"].move_to(fresh["C"]))  # True
print(fresh["E"].parent.value)        # C
print([x.value for x in fresh["A"].children])  # ['D']
print([x.value for x in fresh["C"].children])  # ['E']
print(fresh["G"].parent.value)        # E (không thay đổi)

try:
    fresh["E"].move_to(fresh["G"])
except ValueError as error:
    print(error)  # Không thể chuyển E xuống hậu duệ G.
```

**Vì sao không được chuyển `E` xuống `G`?** `G` đang là hậu duệ của `E`; nếu thêm cạnh `G→E` trong khi vẫn còn `E→G`, ta tạo chu trình. Hàm `move_to` kiểm tra bằng cách đi ngược từ cha đích qua các tổ tiên: nếu gặp nút đang chuyển thì từ chối **trước khi sửa dữ liệu**.

### 6.4. Tính nhất quán khi cập nhật

Trong lớp minh họa, mọi kiểm tra hợp lệ được thực hiện trước khi đổi liên kết, và thao tác gắn mới vào danh sách con được thực hiện trước khi tháo liên kết cũ. Điều này giúp giữ trạng thái cũ nếu `list.append` thất bại **trước khi sửa gì khác**.

Tuy nhiên, các cập nhật nhiều trường vẫn **không tự động là thao tác nguyên tử** trước nhiều luồng hoặc sự kiện bất thường. Trong hệ thống cần bảo đảm giao dịch, hãy dùng **khóa**, cấu trúc phiên bản bất biến, hoặc một cơ chế **rollback** được thiết kế rõ ràng. Không nên cho thuật toán khác duyệt các liên kết đang được chỉnh sửa dở dang.

### 6.5. Thay đổi gốc không chỉ là đổi một con trỏ

Nếu muốn chọn một nút hiện có làm **gốc mới** cho cùng cây vô hướng, phải **đảo hướng các liên kết cha–con dọc theo đường tương ứng**, và có thể phải cập nhật lại depth/height. Chỉ gán biến `root = another_node` sẽ không tạo một quan hệ phân cấp hợp lệ từ nút mới vì các cạnh vẫn hướng theo gốc cũ.

Đổi gốc là một thao tác có ngữ nghĩa riêng, khác với **gắn** hoặc **chuyển cây con**. Các phép biến đổi cũng phải bảo đảm mọi nút vẫn có đúng một cha, trừ gốc mới.

## 7. Truy vấn quan hệ cha, con, anh em và tổ tiên

Nhờ hai chiều liên kết, nhiều truy vấn được mô tả rất tự nhiên.

Vì các mục 6.1–6.3 minh họa việc **thay đổi cây**, ta **khởi tạo lại cây mẫu ban đầu** trước khi thực hiện các truy vấn và phép duyệt bên dưới. Nhờ vậy, các kết quả in ra không phụ thuộc vào việc người học đã thử thao tác gắn, tháo hay chuyển cây con ở mục trước:

```python
nodes = {name: TreeNode(name) for name in "RABCDEFG"}
for p, c in [
    ("R", "A"), ("R", "B"), ("R", "C"),
    ("A", "D"), ("A", "E"), ("B", "F"), ("E", "G")
]:
    nodes[p].add_child(nodes[c])

root = nodes["R"]
```

### 7.1. Cha và con trực tiếp

```python
def direct_parent(node):
    return node.parent


def direct_children(node):
    # Trả bản sao để mã gọi không sửa danh sách gốc.
    return list(node.children)


def siblings(node):
    if node.parent is None:
        return []
    return [
        candidate
        for candidate in node.parent.children
        if candidate is not node
    ]
```

- Xem `parent` đã có tham chiếu nút: **`O(1)` thời gian**.
- Xem **số con** với `len(children)` của Python: **`O(1)`**.
- Sao chép danh sách `k` con: **`O(k)` thời gian và bộ nhớ**.
- Liệt kê anh em: phải duyệt danh sách con của cha, **`O(k)` thời gian**, với `k` là số con của cha.

Nếu dùng `direct_children` trả chính danh sách lưu nội bộ thay vì bản sao, việc đọc sẽ rẻ hơn, nhưng mã bên ngoài có thể vô tình `append` hoặc `remove` rồi phá bất biến `parent/children`.

### 7.2. Truy vấn tổ tiên và đường về gốc

```python
def ancestors(node):
    result = []
    cursor = node.parent

    while cursor is not None:
        result.append(cursor)
        cursor = cursor.parent

    return result


def path_root_to_node(node):
    path = [node]
    cursor = node.parent

    while cursor is not None:
        path.append(cursor)
        cursor = cursor.parent

    path.reverse()
    return path


print([x.value for x in ancestors(nodes["G"])])
# ['E', 'A', 'R'] nếu sử dụng cây mẫu chưa chỉnh sửa.

print([x.value for x in path_root_to_node(nodes["G"])])
# ['R', 'A', 'E', 'G'] nếu sử dụng cây mẫu chưa chỉnh sửa.
```

**Bất biến của vòng lặp:** sau mỗi lần chuyển `cursor = cursor.parent`, ta tiến lên **đúng một cạnh** về phía gốc. Với cây hợp lệ, quá trình kết thúc ở nút có `parent=None`.

Nếu độ sâu nút là `d`, thời gian duyệt là **`O(d)`**; danh sách kết quả gồm `d` tổ tiên hoặc `d+1` nút trên đường đi, nên bộ nhớ trả về là **`O(d+1)`**.

### 7.3. Tổ tiên chung gần nhất từ liên kết cha

**Tổ tiên chung gần nhất (Lowest Common Ancestor, LCA)** của hai nút trong **cùng cây có gốc** là nút sâu nhất là tổ tiên của cả hai, cho phép chính một nút được xem là tổ tiên của nó trong truy vấn LCA.

Khi có liên kết cha và độ sâu, ta có thể:

1. Đưa nút sâu hơn lên tới độ sâu của nút kia.
2. Đưa hai nút lên đồng thời cho tới khi gặp cùng một đối tượng.

```python
def depth(node):
    d = 0
    while node.parent is not None:
        node = node.parent
        d += 1
    return d


def tree_root(node):
    while node.parent is not None:
        node = node.parent
    return node


def lowest_common_ancestor(a, b):
    if tree_root(a) is not tree_root(b):
        raise ValueError("Hai nút không thuộc cùng cây")

    da, db = depth(a), depth(b)

    while da > db:
        a = a.parent
        da -= 1
    while db > da:
        b = b.parent
        db -= 1

    while a is not b:
        a = a.parent
        b = b.parent

    return a


print(lowest_common_ancestor(nodes["D"], nodes["G"]).value)
# A, trên cây mẫu chưa chỉnh sửa.

print(lowest_common_ancestor(nodes["D"], nodes["F"]).value)
# R, trên cây mẫu chưa chỉnh sửa.
```

Chi phí mỗi truy vấn là **`O(h)` thời gian**, **`O(1)` bộ nhớ phụ**, với `h` là chiều cao cây theo số cạnh. Với rất nhiều truy vấn LCA trên cây cố định, có thể dùng thuật toán tiền xử lý chuyên biệt để tăng tốc, nhưng bài này tập trung vào lợi ích của việc lưu liên kết cha.

## 8. Duyệt cây: dùng `children` để tìm mọi hậu duệ

Nếu một nút có `k` con, danh sách `children` cho phép duyệt trực tiếp chúng. Hai chiến lược phổ biến là **DFS** và **BFS**.

### 8.1. DFS tiền thứ tự bằng stack

**DFS preorder** xử lý nút cha trước, rồi đến các cây con. Nếu muốn giữ thứ tự `children`, với stack LIFO phải đưa con vào theo **thứ tự ngược**.

```python
def dfs_preorder(root):
    if root is None:
        return []

    result = []
    pending = [root]

    while pending:
        node = pending.pop()
        result.append(node.value)

        for child in reversed(node.children):
            pending.append(child)

    return result


# Trên cây mẫu chưa chỉnh sửa:
print(dfs_preorder(root))
# ['R', 'A', 'D', 'E', 'G', 'B', 'F', 'C']
```

**Bất biến:** stack chứa những nút đã được phát hiện nhưng chưa xử lý. Khi pop một nút, các con của nó được đưa vào stack. Với một cây hợp lệ, mỗi nút không phải gốc được thêm vào đúng một lần từ cha của nó.

**Chi phí:** `O(n)` thời gian vì mỗi nút và mỗi liên kết con được duyệt một lần; stack công việc có thể chứa `O(n)` phần tử trong trường hợp cây có gốc rất rộng. Danh sách kết quả thêm `O(n)` bộ nhớ.

### 8.2. BFS theo từng mức bằng queue

**BFS** dùng queue FIFO để xử lý các nút theo độ sâu tăng dần:

```python
from collections import deque


def bfs_values(root):
    if root is None:
        return []

    result = []
    pending = deque([root])

    while pending:
        node = pending.popleft()
        result.append(node.value)

        for child in node.children:
            pending.append(child)

    return result


# Trên cây mẫu chưa chỉnh sửa:
print(bfs_values(root))
# ['R', 'A', 'B', 'C', 'D', 'E', 'F', 'G']
```

BFS tốn **`O(n)` thời gian** và tối đa **`O(n)` bộ nhớ phụ** cho queue; với một cây rất rộng, queue có thể chứa nhiều con đang chờ. Nếu chỉ cần xử lý từng nút thay vì trả cả danh sách, có thể loại bỏ bộ nhớ dành cho `result`.

### 8.3. Tính kích thước cây con từ dưới lên

**Kích thước cây con (subtree size)** của `u` là số nút nằm trong cây con gốc `u`:

\[
\operatorname{size}(u)
=1+\sum_{v\in\operatorname{children}(u)}
\operatorname{size}(v).
\]

Muốn tính cho **tất cả nút trong `O(n)` thời gian**, ta xử lý các con trước khi hoàn tất cha bằng hậu thứ tự (*postorder*):

```python
def all_subtree_sizes(root):
    if root is None:
        return {}

    sizes = {}
    frames = [(root, False)]  # (node, ready)

    while frames:
        node, ready = frames.pop()

        if ready:
            sizes[node] = 1 + sum(
                sizes[child] for child in node.children
            )
        else:
            frames.append((node, True))
            for child in reversed(node.children):
                frames.append((child, False))

    return sizes


# Trên cây mẫu chưa chỉnh sửa:
sizes = all_subtree_sizes(root)
print(sizes[nodes["E"]])  # 2 (E và G)
print(sizes[nodes["A"]])  # 4 (A, D, E, G)
print(sizes[root])        # 8
```

Khi lấy frame `(node, True)` ra khỏi stack, các con của nó đã được xử lý và có kích thước trong `sizes`. Tổng số lượt đọc qua danh sách con là `n-1`, nên thời gian **`O(n)`**; bảng kết quả và frames chiếm tối đa **`O(n)` bộ nhớ phụ**.

Lưu sẵn kích thước cây con giúp trả truy vấn `size(u)` trong `O(1)` sau tiền xử lý, nhưng **mọi thao tác gắn, tháo hoặc chuyển cây con** có thể làm thay đổi kích thước của các tổ tiên. Nếu không cập nhật đúng, cache sẽ lỗi.

## 9. Biểu diễn khác: chỉ dùng mảng `parent`

Nếu các nút được đánh số `0..n-1`, có thể lưu cha của từng nút trong một **mảng cha**:

```text
Nút theo chỉ số:
0=R, 1=A, 2=B, 3=C, 4=D, 5=E, 6=F, 7=G

parent = [None, 0, 0, 0, 1, 1, 2, 5]

Chỉ số:  0  1  2  3  4  5  6  7
Cha:     –  0  0  0  1  1  2  5
```

Ở dạng này:

- Xem cha trực tiếp của nút `i`: `parent[i]`, **`O(1)` thời gian**.
- Đi từ nút về gốc: lần theo `parent[i]`, **`O(depth(i))`**.
- Muốn liệt kê **tất cả con trực tiếp** của `u` nếu chỉ có mảng cha: phải tìm mọi chỉ số `i` sao cho `parent[i] == u`, mất **`O(n)` thời gian** mỗi lần quét.
- Lưu mảng cha cần **`O(n)` bộ nhớ**.

Nếu thường xuyên cần duyệt xuống con, ta có thể xây thêm danh sách con cho mỗi nút trong **một lượt**:

```python
def children_from_parent_array(parent):
    n = len(parent)
    children = [[] for _ in range(n)]

    for node, p in enumerate(parent):
        if p is None:
            continue
        children[p].append(node)

    return children


parent = [None, 0, 0, 0, 1, 1, 2, 5]
children = children_from_parent_array(parent)

print(children)
# [[1, 2, 3], [4, 5], [6], [], [], [7], [], []]
```

**Điều kiện tiên quyết:** đoạn mã ngắn này giả định `parent` là một mảng hợp lệ, mọi chỉ số cha nằm trong phạm vi, có đúng một gốc và không có chu trình. Nếu `parent` đến từ dữ liệu ngoài, phải **xác thực trước**; một phần tử `parent[i]=i` có thể tạo chu trình, còn chỉ số âm trong Python có thể âm thầm trỏ tới phần tử cuối.

### Khi nào chỉ mảng cha là đủ?

Nếu ứng dụng chủ yếu thực hiện **đi từ nút lên cha/gốc** (ví dụ xây đường dẫn đầy đủ từ một mục về cấp cao nhất), mảng cha đơn giản và tiết kiệm liên kết con. Nếu ứng dụng liên tục hiển thị danh sách con hoặc duyệt cả cây, nên lưu thêm `children` hoặc một cấu trúc chỉ mục con phù hợp.

**Mảng cha và nút liên kết không loại trừ nhau**: phần khác biệt chủ yếu là dùng **chỉ số nguyên** hay **tham chiếu đối tượng** để mô tả các cạnh. Cả hai đều biểu diễn cùng quan hệ cây.

## 10. Danh sách kề và biểu diễn “con đầu, anh em kế tiếp”

### 10.1. Danh sách kề của đồ thị vô hướng

Nếu nhìn cây như một đồ thị vô hướng, mỗi cạnh `{u,v}` được lưu trong danh sách kề của **cả hai đầu**:

```text
R: [A, B, C]
A: [R, D, E]
B: [R, F]
C: [R]
D: [A]
E: [A, G]
F: [B]
G: [E]
```

Biểu diễn này phù hợp khi dữ liệu đầu vào chỉ gồm **các cạnh vô hướng**, và ta muốn chọn gốc sau. Khi đã chọn gốc `R`, một lần DFS/BFS có thể xác định:

- `parent[R] = None`.
- Với mỗi cạnh nối từ nút đang thăm `u` sang nút chưa thăm `v`: `parent[v]=u`, thêm `v` vào `children[u]`.

Nếu đầu vào là cây vô hướng hợp lệ, mỗi nút có **đúng một đường đi đơn** từ gốc, nên mỗi cha được gán không mâu thuẫn.

Không được nhầm danh sách kề vô hướng với `children`: một mục kề có thể là **cha hoặc con**, trong khi danh sách `children[u]` chỉ chứa **con** của `u` theo gốc đã chọn.

### 10.2. First-child / next-sibling (con đầu, anh em kế tiếp)

Thay vì một danh sách con `children` ở mỗi nút, có thể dùng hai liên kết:

- `first_child`: trỏ tới **con đầu tiên** của nút.
- `next_sibling`: trỏ tới **anh em ngay sau** nút trong danh sách con của cùng cha.

Ví dụ với `R` có các con `A, B, C`:

```text
R.first_child ──► A ──next_sibling──► B ──next_sibling──► C
                                                        │
                                                 next_sibling=None

A.first_child ──► D ──next_sibling──► E
E.first_child ──► G
```

Từ `R.first_child`, ta đi qua chuỗi `next_sibling` để liệt kê tất cả con của `R`. Nhờ vậy, **mỗi nút dùng số lượng trường liên kết cố định** thay vì một đối tượng danh sách con riêng.

```python
class LCRSNode:
    def __init__(self, value):
        self.value = value
        self.first_child = None
        self.next_sibling = None
        self.parent = None  # Tùy chọn, hỗ trợ đi ngược lên cha


def iter_children(node):
    child = node.first_child
    while child is not None:
        yield child
        child = child.next_sibling
```

Cấu trúc này thường được gọi là **left-child/right-sibling** (*LCRS*). Về mặt số trường tham chiếu, nó giống một cây nhị phân với liên kết trái/phải, nhưng **ý nghĩa của hai liên kết không phải con trái và con phải của cây nhị phân gốc**: liên kết “phải” tại đây có nghĩa là **anh em kế tiếp**. Không nên dùng trực tiếp các bất biến của cây tìm kiếm nhị phân hoặc heap cho biểu diễn LCRS.

**Chi phí đặc trưng:**

- Tìm con đầu tiên: `O(1)`.
- Liệt kê `k` con: `O(k)`.
- Tìm con cuối khi không có tham chiếu cuối: `O(k)`.
- Xem cha: `O(1)` nếu lưu trường `parent`, nếu không phải dùng cách tìm khác.
- Bộ nhớ liên kết tổng thể: `O(n)`.

Cách chọn `children=list` hay `first_child/next_sibling` phụ thuộc tần suất truy cập theo chỉ số, thao tác thêm/xóa tại vị trí, nhu cầu giữ thứ tự và chi phí vùng nhớ trong môi trường cài đặt.

## 11. Kiểm tra cấu trúc: phát hiện chu trình, trùng nút và rời gốc

Khi dữ liệu đến từ một API bên ngoài hoặc được khôi phục từ tệp, không nên giả định những tham chiếu `parent/children` luôn đúng. Ta cần phân biệt:

- **Tính hợp lệ của cây mà ta thăm được từ gốc**.
- **Tính đầy đủ so với tập nút mà ứng dụng cho là thuộc cây**.

Nếu chỉ nhận một tham chiếu `root`, hàm duyệt **không thể tự biết** còn nút bị cô lập ở đâu trong bộ nhớ. Muốn phát hiện nút rời gốc, phải cung cấp một **tập nút kỳ vọng**.

### 11.1. Hàm kiểm tra bằng định danh đối tượng

```python
def validate_rooted_tree(root, expected_nodes=None):
    if root is None:
        return expected_nodes is None or len(expected_nodes) == 0

    if not isinstance(root, TreeNode):
        return False
    if root.parent is not None:
        return False

    visited_ids = set()
    pending = [root]

    while pending:
        node = pending.pop()
        marker = id(node)

        # Nút xuất hiện lần hai: có chu trình hoặc dùng chung nút.
        if marker in visited_ids:
            return False
        visited_ids.add(marker)

        for child in node.children:
            if not isinstance(child, TreeNode):
                return False
            if child.parent is not node:
                return False
            pending.append(child)

    if expected_nodes is not None:
        expected_ids = [id(node) for node in expected_nodes]
        # Danh sách kỳ vọng phải không trùng và khớp đúng tập đã thăm.
        return (
            len(expected_ids) == len(set(expected_ids))
            and visited_ids == set(expected_ids)
        )

    return True


original = {name: TreeNode(name) for name in "RABCDEFG"}
for p, c in [
    ("R", "A"), ("R", "B"), ("R", "C"),
    ("A", "D"), ("A", "E"), ("B", "F"), ("E", "G")
]:
    original[p].add_child(original[c])

assert validate_rooted_tree(
    original["R"], list(original.values())
)

orphan = TreeNode("X")
assert not validate_rooted_tree(
    original["R"], list(original.values()) + [orphan]
)
```

### Những điều hàm đã kiểm tra

- Gốc thực sự không có cha.
- Mọi nút duyệt được xuất hiện **đúng một lần**.
- Không có chu trình hoặc một đối tượng nút được dùng từ nhiều đường đi xuống.
- Với mỗi liên kết cha → con, liên kết ngược con → cha đúng đối tượng.
- Khi cung cấp `expected_nodes`, không còn nút kỳ vọng nào ở ngoài cây.

**Bất biến hai chiều:** nếu đầu vào ban đầu được xác định là một tập nút hữu hạn và mỗi nút không phải gốc đúng một lần là con của một nút đã duyệt, việc kiểm tra các liên kết ngược và tập nút thăm được đủ để bảo đảm quan hệ cha–con tương ứng.

Trong mã thực tế, nên kiểm tra thêm kiểu/giới hạn đầu vào, tính nhất quán của các chỉ mục, và dùng quyền truy cập hạn chế với các trường liên kết. Nếu nhiều luồng cùng sửa cây, kiểm tra cần thực hiện trên một **ảnh chụp nhất quán** hoặc dưới khóa phù hợp.

**Độ phức tạp:** với `n` nút có thể tới được và `m` mục con được duyệt, chi phí thông thường là `O(n+m)` thời gian và `O(n)` bộ nhớ cho tập định danh cùng stack. Với cây hợp lệ, `m=n-1` nên rút gọn thành **`O(n)`**; nếu đưa thêm `expected_nodes` gồm `q` nút, cộng `O(q)` để đối chiếu.

## 12. Phân tích độ phức tạp của các thao tác

Ký hiệu:

- `n`: tổng số nút của cây đang xét.
- `h`: chiều cao tính theo số cạnh.
- `k`: số con trực tiếp của một nút, hoặc số con của cha khi thao tác trên nút con.
- `s`: số nút của một cây con.
- Các chi phí bên dưới giả định đã có **tham chiếu tới nút**. Nếu phải tìm nút theo giá trị trong cây, đó là thao tác bổ sung.

| Thao tác với `TreeNode` | Thời gian | Bộ nhớ phụ | Vì sao? |
|---|---|---|---|
| Xem `node.parent` | `O(1)` | `O(1)` | Một tham chiếu |
| Kiểm tra `is_root`, `is_leaf` | `O(1)` | `O(1)` | Kiểm tra trường/độ dài |
| Đếm con bằng `len(children)` | `O(1)` | `O(1)` | Danh sách Python biết độ dài |
| Liệt kê `k` con | `O(k)` | `O(1)` nếu duyệt trực tiếp | Mỗi con được đọc một lần |
| Sao chép danh sách `k` con | `O(k)` | `O(k)` | Tạo một danh sách mới |
| Liệt kê anh em | `O(k)` | `O(k)` nếu trả danh sách | Duyệt con của cha |
| Đi từ nút về gốc | `O(depth(u)) \subseteq O(h)` | `O(1)` nếu chỉ đếm | Mỗi bước lên một cha |
| `add_child` có kiểm tra chu trình | `O(h)` kiểm tra, `O(1)` amortized để `append` | `O(1)` | Đi lên từ cha dự kiến |
| `detach` từ danh sách con Python | `O(k)` | `O(1)` | `list.remove` phải tìm vị trí |
| `move_to` với nút đang có cha | `O(h+k)` thường gặp | `O(1)` | Kiểm tra tổ tiên + xóa khỏi cha cũ |
| DFS/BFS cả cây | `O(n)` | Tới `O(n)` cho công việc chờ | Thăm mỗi nút một lần |
| Tính kích thước mọi cây con một lượt | `O(n)` | `O(n)` | Postorder + bảng kết quả |
| Tìm giá trị nếu không có chỉ mục phụ | `O(n)` trường hợp xấu nhất | Tùy cách duyệt | Có thể phải xem toàn bộ nút |

Lưu ý: `O(h)` trong kiểm tra tổ tiên nghĩa là tối đa `h+1` nút trên đường về gốc, vẫn là `O(h+1)` đối với trường hợp cây một nút. Khi viết bảng độ phức tạp, nhiều tài liệu viết `O(h)` cho ngắn gọn vì `h` thường được hiểu là chiều cao theo **số nút**; quy ước bài này dùng cạnh, nên với trường hợp `h=0` cần hiểu chặn trên là **`O(h+1)`**.

### Chi phí bộ nhớ của các cách lưu

| Cách biểu diễn | Liên kết lưu thêm | Tổng bộ nhớ theo số nút/cạnh |
|---|---|---|
| Chỉ danh sách `children` | Mỗi cạnh xuất hiện một lần dưới cha | `O(n)` |
| `parent` + `children` | Mỗi cạnh có tham chiếu xuôi và ngược | `O(n)`, hằng số lớn hơn |
| Chỉ mảng `parent` | Một ô cha cho mỗi nút | `O(n)` |
| Danh sách kề vô hướng | Mỗi cạnh xuất hiện ở cả hai đầu | `O(n+m) = O(n)` với cây |
| First-child/next-sibling | Hai tham chiếu cấu trúc mỗi nút, có thể thêm parent | `O(n)` |

Việc hai biểu diễn đều có `O(n)` bộ nhớ **không có nghĩa chi phí thực tế giống nhau**. Số đối tượng danh sách, kích thước tham chiếu, công suất dư của mảng động và cấu trúc cấp phát có thể khác nhau. Lựa chọn còn phụ thuộc yêu cầu hiệu năng, bộ nhớ và khả năng sửa cấu trúc.

## 13. Sai lầm thường gặp khi biểu diễn bằng cha–con

1. **Chỉ cập nhật `parent` mà không sửa `children`.** Hai chiều liên kết sẽ mô tả hai cấu trúc khác nhau.
2. **Chỉ thêm vào `children` mà quên gán `parent`.** Truy vấn tổ tiên và kiểm tra gốc sai.
3. **Cho phép một nút có hai cha.** Một cây có gốc không cho phép một đối tượng xuất hiện dưới hai đường cha–con khác nhau.
4. **Gắn tổ tiên làm con của hậu duệ.** Tạo chu trình khiến DFS và vòng đi theo cha có thể không kết thúc.
5. **So sánh giá trị nút thay vì định danh nút.** Hai nút có cùng `value` không có nghĩa cùng là một nút.
6. **Sao chép tham chiếu tới danh sách con rồi nghĩ đó là danh sách độc lập.** Nếu trả chính `node.children`, bên ngoài có thể sửa trực tiếp và phá bất biến.
7. **Nhầm con trực tiếp với mọi hậu duệ.** `children(u)` không tự bao gồm cháu, chắt; muốn lấy cây con phải duyệt xuống.
8. **Nhầm anh em với các nút cùng độ sâu.** Anh em phải có **cùng cha**, không chỉ cùng mức.
9. **Xóa `node.parent` rồi nghĩ đã xóa nút khỏi cây.** Cần xóa cả tham chiếu trong danh sách con của cha.
10. **Tháo cây con nhưng quên rằng nó vẫn tồn tại.** `detach` tách cây thành hai cây, không hủy dữ liệu các nút.
11. **Dùng mảng cha có chỉ số không hợp lệ.** Một chỉ số `-1` có thể được Python hiểu là phần tử cuối; phải dùng và kiểm tra giá trị sentinel rõ ràng.
12. **Nhầm danh sách kề vô hướng với danh sách con.** Trong danh sách kề, nút cha cũng là một nút kề của nút con.
13. **Cho rằng mọi cây chỉ có hai con.** Cây tổng quát có thể có rất nhiều con; cần chọn biểu diễn phù hợp.
14. **Cho rằng chỉ cần `n-1` liên kết là dữ liệu hợp lệ.** Cần kiểm tra liên thông, một gốc và không chu trình.
15. **Gắn/sửa trong khi thuật toán khác đang duyệt mà không đồng bộ.** Một phần tử có thể bị bỏ sót hoặc thăm hai lần nếu thấy trạng thái trung gian.
16. **Gắn cache depth/subtree size nhưng không cập nhật sau move.** Quan hệ thay đổi có thể làm mọi độ sâu trong cây con và kích thước ở các tổ tiên thay đổi.
17. **Đánh giá truy vấn con là `O(1)` chỉ vì có trường `children`.** Lấy tham chiếu danh sách có thể `O(1)`, nhưng **liệt kê `k` con** cần `O(k)`.
18. **Đánh đồng `move_to` với `add_child`.** Một nút đã có cha phải được chuyển có kiểm tra và cập nhật quan hệ cũ; không thể đơn giản thêm lần nữa.

## 14. Các tình huống biên và kiểm thử thủ công

Bên dưới là những phép kiểm tra có thể thực hành với các hàm đã định nghĩa. Các đoạn kiểm thử được trình bày để người học hiểu kỳ vọng, không phải một vòng QA tự động của hệ thống xây học liệu.

```python
# Cây chỉ có một nút: nút vừa là gốc, vừa là lá.
single = TreeNode("only")
assert single.is_root()
assert single.is_leaf()
assert single.child_count() == 0
assert validate_rooted_tree(single, [single])

# Thêm một lá mới.
child = TreeNode("child")
single.add_child(child)
assert child.parent is single
assert not single.is_leaf()
assert validate_rooted_tree(single, [single, child])

# Không thể dùng cùng một đối tượng con ở hai vị trí.
other_parent = TreeNode("another")
try:
    other_parent.add_child(child)
except ValueError:
    pass
else:
    raise AssertionError("Phải từ chối khi child đã có cha")

# Không thể gắn cha cũ xuống dưới con, vì tạo chu trình.
try:
    child.add_child(single)
except ValueError:
    pass
else:
    raise AssertionError("Phải từ chối thao tác tạo chu trình")

# Tháo tạo ra hai cây riêng biệt.
assert child.detach()
assert child.parent is None
assert single.is_leaf()
assert validate_rooted_tree(single, [single])
assert validate_rooted_tree(child, [child])

# Tháo nút vốn đã là gốc không làm gì.
assert child.detach() is False
```

Những kiểm thử này minh họa tính đúng đắn của các liên kết. Khi phát triển một thư viện thực tế, còn cần thử các đối tượng chứa giá trị trùng nhau, cây rất rộng/rất sâu, nút bị sửa ngoài API, và các thao tác có lỗi giữa chừng hoặc bị thực hiện đồng thời.

## 15. Bài tập thực hành có đáp án

### Bài 1. Nhận diện liên kết

Với cây mẫu gồm `R,A,B,C,D,E,F,G`, hãy xác định `parent(G)`, `children(R)` và `children(E)`.

**Đáp án:** `parent(G)=E`, `children(R)=[A,B,C]`, `children(E)=[G]`.

### Bài 2. Gốc và lá

Một cây chỉ có một nút `X`. Giá trị `parent(X)` và `children(X)` là gì? `X` có phải vừa là gốc vừa là lá không?

**Đáp án:** `parent(X)=None` và `children(X)=[]`. `X` là gốc vì không có cha và là lá vì không có con.

### Bài 3. Liên kết hai chiều

Giả sử `A.children=[B]` nhưng `B.parent=C`. Dữ liệu có hợp lệ không? Cần sửa gì nếu ý định là `A` làm cha của `B`?

**Đáp án:** **Không hợp lệ**, vì hai chiều mâu thuẫn. Nếu cây dự kiến cho `B` thuộc `A`, cần bảo đảm `B.parent=A` và `B` không còn được liệt kê dưới một cha khác. Mọi sửa đổi phải qua thao tác duy trì bất biến, không chỉnh lẻ một trường.

### Bài 4. Thêm cây con

Trong cây mẫu, `C` là lá. Gắn nút mới `H` làm con của `C`. Tổng số nút và tổng số cạnh thay đổi như thế nào?

**Đáp án:** Từ `8` nút và `7` cạnh thành `9` nút và `8` cạnh. `C` thành nút trong, `H` là lá; vẫn có `|E|=|V|-1`.

### Bài 5. Tháo cây con

Tháo cây con gốc `E` khỏi cha `A` trong cây mẫu. Những nút nào thuộc cây riêng gốc `E`? Có còn một cây duy nhất trên toàn bộ tập nút không?

**Đáp án:** Cây riêng gốc `E` chứa `E,G`, vì liên kết `E→G` được giữ nguyên. Toàn bộ tập nút trở thành **rừng gồm hai cây**, không còn một cây liên thông duy nhất.

### Bài 6. Chuyển cây con

Chuyển `E` từ cha `A` sang cha `C` trong cây mẫu. Hỏi `parent(E)`, `parent(G)` và các danh sách con của `A,C` sau khi chuyển.

**Đáp án:** `parent(E)=C`, `parent(G)=E`. `children(A)=[D]`; `children(C)=[E]`. Quan hệ bên trong cây con gốc `E` không thay đổi.

### Bài 7. Phát hiện chu trình

Trong cây mẫu, có được gọi `G.add_child(A)` nếu `A` vẫn là tổ tiên của `G` không?

**Đáp án:** **Không.** `A` là tổ tiên của `G` trên đường `A→E→G`; gắn `A` dưới `G` tạo chu trình `A→E→G→A`. Hàm `add_child` cần từ chối trước khi sửa bất kỳ liên kết nào.

### Bài 8. Mảng cha

Với `parent=[None,0,0,1,1]`, hãy xác định gốc và danh sách con của mỗi nút.

**Đáp án:** Gốc là `0`. `children[0]=[1,2]`, `children[1]=[3,4]`, còn `children[2]=children[3]=children[4]=[]`.

### Bài 9. Chi phí tra cứu con

Nếu chỉ lưu mảng `parent` của `n` nút, mất bao lâu để tìm **tất cả con trực tiếp** của nút `u` trong trường hợp xấu nhất? Nếu còn có danh sách `children[u]` dài `k` thì sao?

**Đáp án:** Với chỉ mảng cha, cần quét tới `n` mục nên **`O(n)`**. Với danh sách con, lấy danh sách đã lưu có thể `O(1)`, nhưng **liệt kê đủ `k` con** cần **`O(k)`** thời gian.

### Bài 10. Anh em và cùng mức

Trong cây mẫu, `D` và `F` đều có độ sâu `2`. Chúng có phải anh em không?

**Đáp án:** **Không.** `parent(D)=A` và `parent(F)=B`. Anh em phải có cha trực tiếp giống nhau.

### Bài 11. Tổng số tham chiếu

Một cây có gốc gồm `20` nút được lưu bằng `parent` và `children`. Có bao nhiêu tham chiếu `parent` khác `None` và bao nhiêu mục trong tất cả danh sách con cộng lại?

**Đáp án:** Có `20-1=19` tham chiếu cha khác rỗng và `19` mục con, vì mỗi nút không phải gốc tạo đúng một cạnh cha–con.

### Bài 12. Tìm đường về gốc

Trong cây mẫu, hàm `path_root_to_node(G)` trả về những nút nào? Thời gian phụ thuộc đại lượng gì?

**Đáp án:** `[R,A,E,G]`. Thời gian tỷ lệ với **độ sâu của `G` cộng một**, tức `O(depth(G)+1)`.

### Bài 13. Kiểm tra nút rời gốc

Một hàm duyệt từ `R` thăm được `8` nút, nhưng danh sách nút mà ứng dụng quản lý có `9` nút. Có thể kết luận mọi nút đều thuộc cây gốc `R` không?

**Đáp án:** **Không.** Nút thứ chín có thể đang bị cô lập hoặc thuộc một cây khác. Phải đối chiếu tập định danh của các nút kỳ vọng với tập đã thăm từ `R`.

### Bài 14. LCRS khác cây nhị phân thông thường

Trong biểu diễn `first_child/next_sibling`, trường `next_sibling` của nút `A` trỏ tới `B`. Có nên kết luận `B` là “con phải của `A`” trong cây phân cấp gốc không?

**Đáp án:** **Không.** Nó là **anh em kế tiếp** của `A`, cùng cha với `A`. Cấu trúc LCRS sử dụng hai liên kết hình thức giống trái/phải, nhưng ý nghĩa quan hệ khác cây nhị phân nguyên gốc.

### Bài 15. Bộ nhớ và cách lưu

Một cây có rất nhiều con dưới một nút. Nếu chỉ lưu liên kết `parent`, việc hiển thị các con sẽ tốn nhiều lần quét. Nên thêm cấu trúc gì nếu thao tác liệt kê con diễn ra thường xuyên?

**Đáp án:** Lưu thêm danh sách `children` hoặc `first_child/next_sibling`. Điều này giúp truy cập đúng nhóm con mà không quét toàn bộ `n` nút; đổi lại cần thêm liên kết và duy trì nhất quán khi cập nhật.

### Bài 16. Truy vấn kích thước cây con

Cây mẫu ban đầu có `E→G`. Kích thước cây con gốc `E` và gốc `A` là bao nhiêu? Nếu chuyển `E` sang dưới `C`, kích thước cây con gốc `A` và `C` thay đổi như thế nào?

**Đáp án:** Trước khi chuyển, `size(E)=2` và `size(A)=4`. Sau chuyển, `size(A)=2` (chỉ còn `A,D`), còn `size(C)=3` (`C,E,G`). Nếu lưu cache kích thước, phải cập nhật các tổ tiên chịu ảnh hưởng.

## 16. Tổng kết

**Biểu diễn cây bằng liên kết cha–con** giúp chuyển quan hệ phân cấp thành dữ liệu có thể duyệt và cập nhật. Với **mỗi nút lưu `parent` và `children`**, chương trình tra cha trực tiếp trong **`O(1)`**, liệt kê `k` con trong **`O(k)`** và đi theo chuỗi tổ tiên trong thời gian tỷ lệ độ sâu. Tổng số liên kết trong cây có `n` nút là **`O(n)`**.

Đổi lại, ta phải bảo vệ **bất biến hai chiều**: một nút được liệt kê là con của cha nào thì tham chiếu `parent` phải quay về đúng cha đó; không có nút nhiều cha, không chu trình và mọi nút thuộc đúng gốc của cây đang xét. Khi gắn, tháo hoặc chuyển cây con, cần cập nhật **cả hai hướng**, kiểm tra chu trình trước và giữ đúng các thông tin phụ trợ nếu có.

Ngoài mô hình nút liên kết, ta còn có **mảng cha**, **danh sách kề vô hướng** và **first-child/next-sibling**. Không có cách lưu trữ tốt nhất cho mọi bài toán: nếu truy vấn cha thường xuyên, liên kết `parent` hữu ích; nếu duyệt xuống con thường xuyên, danh sách `children` đáng giá; nếu dữ liệu được đánh số và ít thay đổi, mảng cha có thể gọn và đơn giản.

Khi chọn cấu trúc phù hợp, hãy xuất phát từ **thao tác cần nhanh**, **bất biến cần giữ**, **quy mô cây**, **thứ tự các con** và **chi phí bộ nhớ** — không chỉ từ hình vẽ của cây.
