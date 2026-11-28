# Phát hiện cấu trúc không còn là cây do chu trình hoặc nhiều cha

Một cấu trúc dữ liệu có `root`, các nút và hai trường `left`/`right` **chưa chắc là cây**. Chỉ cần một nút con trỏ ngược lên tổ tiên, ta đã tạo **chu trình**; chỉ cần hai đường liên kết cùng dẫn đến một nút, ta đã tạo **nút có nhiều đường đến từ gốc** hoặc **nhiều cạnh đi vào**. Khi các giả định “đúng là cây” bị phá vỡ, duyệt đệ quy có thể chạy vô hạn, hàm đếm nút có thể đếm sai, phép sao chép có thể làm mất thông tin chia sẻ, và hàm giải phóng kiểu cây có thể gây double free hoặc use-after-free.

Bài **“Phát hiện cấu trúc không còn là cây do chu trình hoặc nhiều cha”** nằm trong chương **Duyệt và biến đổi cây** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Module học các cấu trúc từ mảng, danh sách liên kết, stack, queue, bảng băm tới cây, heap, đồ thị, chú trọng **bất biến**, các thao tác an toàn, **độ phức tạp thời gian và bộ nhớ**. Trong bài này, ta xem những liên kết con trỏ như **các cạnh có hướng** rồi dùng **DFS ba màu, bảng bậc vào, tập đã thăm và các phép kiểm định cấu trúc** để xác định có còn một cây có gốc hợp lệ hay không.

Sau bài học, bạn có thể:

- Phát biểu điều kiện để một cấu trúc nút có gốc là **cây có gốc** thay vì **DAG** hoặc đồ thị có chu trình.
- Phân biệt **giá trị nút trùng nhau**, **một đối tượng nút bị tham chiếu hai lần**, **hai cha khác nhau**, **cạnh ngược lên tổ tiên** và **con trỏ cha hợp lệ**.
- Viết bộ kiểm tra **không đệ quy**, phân biệt cạnh tới nút **đang ở đường DFS** với cạnh tới nút **đã xử lý xong**.
- Dùng số cạnh, số nút, bậc vào và bảng cha như các bất biến để phát hiện lỗi, biết giới hạn của từng cách.
- Chỉ ra phạm vi kiểm tra **phần reachable từ gốc** khác kiểm tra **toàn bộ tập nút**.
- Thiết kế kiểm thử và xử lý lỗi trước khi duyệt, clone, biến đổi, serialize hoặc giải phóng cấu trúc có thể không còn là cây.

## 1. Thế nào mới là một cây có gốc hợp lệ?

Trong bài này, ta giả sử một cấu trúc nhị phân dạng:

```text
root -> Node
Node.left  -> Node hoặc NULL
Node.right -> Node hoặc NULL
```

Mỗi liên kết `left`/`right` khác rỗng được xem là **một cạnh có hướng từ cha tới con**. Định nghĩa này không tự tính các trường khác như `parent`, `next` hay `prev` là cạnh đi xuống.

Với **cây có gốc, hữu hạn, không chia sẻ nút**:

1. Có một gốc duy nhất `root`, hoặc là cây rỗng (`root = NULL`).
2. Mọi nút thuộc cây đều **đi tới được từ gốc** theo các cạnh con.
3. Gốc **không có cạnh con nào đi vào nó** trong phạm vi cấu trúc được xét.
4. Mỗi nút khác gốc có **đúng một cạnh con đi vào**; không nút nào được dùng ở hai vị trí con.
5. Không tồn tại **chu trình có hướng** khi đi qua các cạnh con.
6. Từ gốc đến mỗi nút có **một đường đi duy nhất**.

Với một tập nút hữu hạn và mọi nút đều reachable từ gốc, điều kiện **mỗi nút khác gốc có đúng một cạnh đi vào, gốc có bậc vào 0** tương đương với hình dạng cây có gốc. Khi gắn thêm yêu cầu “mỗi nút tối đa hai vị trí con”, ta có cây nhị phân.

### 1.1. Cây đúng

```text
                 A
               /   \
              B     C
             / \     \
            D   E     F

Cạnh: A->B, A->C, B->D, B->E, C->F

A: bậc vào 0.
B,C,D,E,F: mỗi nút có bậc vào 1.
Không có chu trình, không có nút chia sẻ.
```

Một cây có `n` nút thực sự có đúng **`n-1` cạnh cha–con** nếu `n >= 1`. Cây rỗng có 0 nút và 0 cạnh.

### 1.2. Không phải mọi thứ “trông như cây” đều là cây

```text
(a) Chu trình:            (b) Dùng chung nút:       (c) Nút tự trỏ:

     A                         A                         A
      \                       / \                        |
       B                     B   C                       +--left--> A
        \                     \ /
         C                     D
         |
         +---left--> A

A->B->C->A           D được tham chiếu từ B và C.
```

- (a) chứa một **chu trình có hướng** nên không còn là cây.
- (b) là ví dụ **DAG** (*Directed Acyclic Graph*, đồ thị có hướng không chu trình) với một nút được tham chiếu từ hai nhánh; DAG **không phải** cây có gốc duy nhất theo quy ước ở đây.
- (c) là **self-loop** (chu trình độ dài một).

Một cấu trúc có thể đồng thời có cả **nhiều cạnh đi vào** và **chu trình**. Hai loại lỗi là những lý do khác nhau khiến cấu trúc không còn là cây; một bộ kiểm tra đầy đủ nên có cách giải thích hoặc báo cả hai khi cần.

## 2. Cùng giá trị không đồng nghĩa cùng nút

Đây là điểm dễ gây sai lệch trong mọi bộ kiểm tra.

```text
Cây hợp lệ:                  Cấu trúc không phải cây:

        A                          A
       / \                        / \
     (5) (5)                      B   B
      X   Y                        \ /
                                  cùng một object B
```

Ở hình trái, `X` và `Y` là **hai đối tượng nút khác nhau** dù `X.value == Y.value == 5`. Đó hoàn toàn có thể là một cây hợp lệ nếu bài toán không yêu cầu khóa duy nhất.

Ở hình phải, hai trường con dẫn tới **chính một đối tượng B**. Đây là hai cạnh con đi vào một nút, dù chỉ có **một nút cha khác nhau** là A. Ta vẫn xem là vi phạm cây nhị phân **không chia sẻ nút**, vì mỗi vị trí `left`/`right` phải sở hữu **một nút con độc lập** nếu có.

### 2.1. Phải đếm cạnh con, không chỉ đếm cha phân biệt

Hai tình huống cần nhận biết:

- **Hai cha khác nhau**: `B.right is D` và `C.left is D`.
- **Hai vị trí con từ cùng cha**: `A.left is D` và `A.right is D`.

Cả hai đều tạo **hai cạnh đi vào D** theo mô hình “mỗi trường con khác `NULL` là một cạnh”. Trường hợp thứ hai không có hai *đối tượng cha khác nhau*, nên dùng các thuật ngữ **“nhiều liên kết đi vào”**, **“nút được dùng chung”** hoặc **“nhiều đường”** chính xác hơn từ “nhiều cha” theo nghĩa đen.

Nếu API dùng **khóa duy nhất**, đó là bất biến **nghiệp vụ bổ sung**. Việc có trùng khóa có thể làm cây tìm kiếm nhị phân (BST) vi phạm chính sách khóa, nhưng **không tự chứng minh có chu trình hay nhiều cha**.

### 2.2. Identity trong Python, C và C++

- Python: so sánh nút theo **`is`** hoặc dùng bảng theo identity. Với `@dataclass(eq=False)`, object dùng `__eq__` và `__hash__` dựa theo danh tính mặc định.
- C: các con trỏ `Node*` bằng nhau khi chúng cùng trỏ tới **một đối tượng nút còn sống**; không dùng `node->value` làm định danh.
- C++: có thể dùng `const Node*` làm khóa identity trong `std::unordered_map`/`std::unordered_set` khi object còn sống.

Mọi kiểm tra theo con trỏ giả định các đường truy cập hợp lệ; một **con trỏ treo** hoặc trỏ vùng bộ nhớ sai không thể được “sửa” chỉ bằng cách đếm cạnh. Trong hệ thống phải chịu đầu vào không tin cậy ở cấp vùng nhớ, cần định dạng dữ liệu có **ID được quản lý, chỉ mục có kiểm tra** hoặc API xác thực vùng nhớ trước khi truy cập.

## 3. Ba lỗi cấu trúc thường gặp và hệ quả

### 3.1. Chu trình trực tiếp hoặc gián tiếp

```text
A.left = B
B.right = C
C.left = A

A -> B -> C -> A -> B -> ...
```

Hậu quả điển hình:

- DFS/BFS **không có visited** có thể không bao giờ kết thúc.
- Clone đệ quy có thể liên tục tạo nút và cạn bộ nhớ/stack.
- Hàm tính chiều cao `height(node) = 1 + max(height(children))` không có điểm dừng hợp lệ.
- Hàm giải phóng kiểu cây có thể đi vào nút đã giải phóng, gây truy cập sai hoặc double free.

Chu trình có thể dài hàng nghìn cạnh hoặc chỉ là `node.left = node`.

### 3.2. Nút được tham chiếu từ nhiều vị trí, không có chu trình

```text
    Root
    /  \
   L    R
    \  /
     Shared
```

Đồ thị này có thể hoàn toàn **không có chu trình** và BFS từ gốc vẫn kết thúc ngay cả khi không có visited. Nhưng những thuật toán giả định “mỗi nút có đúng một cha” vẫn có thể sai:

- Đếm bằng cách cộng `1 + size(left) + size(right)` sẽ **đếm Shared hai lần**.
- Clone như cây sẽ tạo **hai nút Shared clone** riêng, làm mất quan hệ aliasing.
- Giải phóng cây bằng hai nhánh có thể hủy `Shared` hai lần.
- Thuật toán lấy **đường gốc–đích duy nhất** không còn đúng: có hai đường tới `Shared`.

Đây là lý do **chỉ phát hiện chu trình chưa đủ** để khẳng định cấu trúc là cây.

### 3.3. Cấu trúc có phần không tới được từ gốc

```text
root --> A --> B

X --> Y --> X     (một phần độc lập không reachable từ root)
```

Nếu chỉ bắt đầu duyệt từ `root`, ta chỉ kiểm tra được **phần reachable** chứa `A, B`. Chu trình `X ↔ Y` bên ngoài không được phát hiện.

Muốn tuyên bố **toàn bộ kho nút** tạo thành **một cây duy nhất**, cần có danh sách/registry của mọi nút mà hệ thống đang quản lý và kiểm tra:

- Mọi nút mong đợi có reachable từ gốc không?
- Có cạnh ngoài vùng reachable đi vào một nút đã kiểm tra không?
- Có thành phần khác, nút cô lập hoặc chu trình riêng không?

Một hàm `validate(root)` không biết các nút ở ngoài vùng reachable **không thể chứng minh điều gì về những nút đó**.

## 4. Các bất biến nhanh: đếm nút, cạnh và bậc vào

Gọi `V` là số nút **khác nhau theo danh tính** reachable từ gốc, `E` là số cạnh con khác rỗng trong phần reachable, **đếm theo từng vị trí** `left`/`right`.

Khi cây không rỗng và hợp lệ:

\[
E = V - 1.
\]

Vì sao? Có `V-1` nút khác gốc; mỗi nút ấy có đúng một cạnh đi vào. Mọi cạnh trong cấu trúc đều là cạnh cha–con giữa những nút reachable, nên tổng có `V-1` cạnh.

### 4.1. Tại sao `E = V - 1` là tín hiệu hữu ích?

Trong một đồ thị hữu hạn có hướng, mọi nút được **reachable từ gốc**, bất kỳ cách khám phá nào cũng có thể chọn `V-1` **cạnh phát hiện** để đưa `V-1` nút mới vào tập đã thấy. Nếu `E=V-1` thì **không có cạnh dư** nào trỏ tới một nút đã phát hiện; cấu trúc reachable là một cây có gốc.

Do đó, trong **phạm vi reachable và theo định nghĩa cạnh con ở trên**, đẳng thức `E=V-1` là một phép kiểm chứng hợp lệ nếu đếm đúng mọi nút và **mọi cạnh kể cả cạnh lặp**.

Tuy nhiên, để **chẩn đoán nguyên nhân**, chỉ biết tổng không đủ: ta vẫn cần phân biệt cạnh gây **chu trình** với cạnh dẫn đến **nút được dùng chung**.

### 4.2. Đếm sai dẫn tới kết luận sai

```text
       A
      / \
     B   C
      \ /
       D
```

Đếm đúng: `V=4` (A, B, C, D), `E=4` (A→B, A→C, B→D, C→D), nên `E≠V-1=3`.

Nếu chỉ gọi đệ quy `count(left)+count(right)` mà không phân biệt identity, có thể “đếm nút” D **hai lần** và báo `V=5` giả. Khi đó `E=V-1` có thể tưởng đúng một cách sai lệch.

**Quy tắc:** bộ đếm `V` phải dựa trên **tập đối tượng đã thấy**, trong khi `E` phải dựa trên **số trường liên kết con khác rỗng đã quan sát** từ từng nút duy nhất.

### 4.3. Kiểm tra bậc vào

Một kiểm tra khác là:

- `indegree[root] == 0`.
- Với mọi `v != root` reachable: `indegree[v] == 1`.
- Không có thành phần mong đợi nằm ngoài reachable.

Khi dùng **bậc vào theo số cạnh**, hai trường `left/right` cùng chỉ `D` làm `indegree[D]=2`, kể cả khi chúng xuất phát từ cùng một cha.

| Mẫu sai | Bậc vào có thể phát hiện? | DFS ba màu có thể chẩn đoán? |
| --- | --- | --- |
| Nút con được dùng hai vị trí | Có: bậc vào ≥ 2 | Có: cạnh đến nút đã xử lý |
| Hai cha khác nhau cùng trỏ một nút | Có: bậc vào ≥ 2 | Có: cạnh đến nút đã xử lý |
| Con trỏ ngược lên tổ tiên | Có cạnh dư; gốc/tổ tiên có bậc vào bất thường | Có: cạnh đến nút **đang nằm trong đường DFS** |
| Nút tự trỏ | Có: một cạnh dư, có thể là bậc vào 2 hoặc gốc bậc vào 1 | Có: cạnh đến chính nó đang màu xám |
| Thành phần không reachable | Không thể biết chỉ từ vùng reachable | Không thể biết nếu không có registry toàn bộ nút |

Trong cấu trúc trực tiếp có chu trình, **ít nhất một cạnh phải trỏ vào nút đã được phát hiện**; trường hợp này bị nhận ra bởi quy trình DFS đúng. Không cần dựa duy nhất vào đẳng thức tổng số cạnh để phân loại.

## 5. DFS ba màu: phát hiện chu trình và nút dùng chung trong một lượt

**DFS ba màu** dùng trạng thái thăm:

- **WHITE (trắng)**: chưa phát hiện nút.
- **GRAY (xám)**: nút đã vào DFS nhưng **chưa rời đường duyệt đang hoạt động**.
- **BLACK (đen)**: nút đã xử lý xong mọi cạnh con.

Khi kiểm tra một cạnh `u → v`:

| Màu của `v` | Diễn giải |
| --- | --- |
| WHITE | Nút mới; ghi nhận nó và DFS xuống |
| GRAY | `v` là nút đang ở đường DFS; cạnh là **back edge**, tạo chu trình có hướng |
| BLACK | Nút đã kết thúc xử lý nhưng lại có một cạnh đi tới: **chia sẻ/nhiều đường tới cùng nút**, không phải back edge của lượt DFS ấy |

### 5.1. Vì sao cần phân biệt xám và đen?

Giả sử:

```text
A.left = B        A.right = C
B.right = D       C.left = D
```

Khi DFS đi theo nhánh B trước, D trở thành **BLACK** sau khi hoàn tất nhánh ấy. Lúc đi nhánh C và thấy cạnh `C→D`, đây là **nút dùng chung** trong một DAG, không phải chu trình.

Ngược lại, nếu D có liên kết `D.left = A` trong lúc A vẫn đang GRAY, cạnh `D→A` đi **ngược lên tổ tiên**, tạo chu trình.

Một bộ kiểm tra chỉ có `visited = {node}` sẽ phát hiện “đã thấy” nhưng không biết đó là chu trình hay chia sẻ. Muốn giải thích nguyên nhân, dùng **GRAY/BLACK** hoặc stack tổ tiên tương đương.

### 5.2. Bất biến của DFS ba màu

Trước mỗi bước:

1. Những nút GRAY chính là những nút trong **chuỗi khung DFS đang hoạt động**, theo đường từ gốc tới nút hiện tại.
2. Những nút BLACK đã kiểm tra xong cả hai vị trí con; không cần mở rộng lại.
3. Không có nút nào được **vào DFS lần thứ hai** chỉ vì một cạnh khác dẫn tới nó.
4. Một cạnh tới GRAY được báo chu trình; một cạnh tới BLACK được báo liên kết dùng chung.
5. Nếu stack kết thúc, tất cả nút reachable đã được xử lý; mỗi cạnh đi ra từ mỗi nút khác nhau được kiểm tra đúng một lần.

Với đồ thị con hữu hạn, các bất biến này giúp thuật toán kết thúc **ngay cả khi có chu trình**, thay vì đi mãi theo chu trình ấy.

## 6. Python: cài đặt bộ kiểm tra không đệ quy, có chẩn đoán

Ta dùng `@dataclass(eq=False)` để các nút được nhận biết bằng **danh tính đối tượng**, không phải so sánh nội dung. Thuật toán dùng **stack tường minh** chứa một khung `(node, next_child_index)`, nơi chỉ số 0/1/2 lần lượt nghĩa là “sắp xét trái”, “sắp xét phải” và “đã xét xong cả hai”.

### 6.1. Code tự chạy độc lập

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(eq=False)
class Node:
    value: str
    left: Node | None = None
    right: Node | None = None


@dataclass
class Issue:
    kind: str             # "CYCLE" hoặc "SHARED_NODE"
    source: Node
    target: Node


@dataclass
class Inspection:
    node_count: int
    edge_count: int
    issues: list[Issue]

    @property
    def is_tree(self) -> bool:
        return not self.issues


def inspect_reachable_tree(root: Node | None) -> Inspection:
    """
    Kiểm tra đồ thị các liên kết left/right reachable từ root.
    Nhận diện node theo identity, không theo value.
    Không dùng đệ quy và không đi mãi trong chu trình.
    """
    if root is None:
        return Inspection(0, 0, [])

    WHITE, GRAY, BLACK = 0, 1, 2

    color: dict[Node, int] = {root: GRAY}
    stack: list[tuple[Node, int]] = [(root, 0)]
    issues: list[Issue] = []
    edges = 0

    while stack:
        node, next_child = stack[-1]

        if next_child == 2:
            color[node] = BLACK
            stack.pop()
            continue

        # Cập nhật khung hiện tại trước khi đi xuống một con.
        stack[-1] = (node, next_child + 1)
        child = node.left if next_child == 0 else node.right

        if child is None:
            continue

        edges += 1
        state = color.get(child, WHITE)

        if state == WHITE:
            color[child] = GRAY
            stack.append((child, 0))
        elif state == GRAY:
            issues.append(Issue("CYCLE", node, child))
        else:
            issues.append(Issue("SHARED_NODE", node, child))

    return Inspection(len(color), edges, issues)


def show_report(root: Node | None) -> None:
    result = inspect_reachable_tree(root)

    print("nodes:", result.node_count,
          "edges:", result.edge_count,
          "is_tree:", result.is_tree)

    for issue in result.issues:
        print(issue.kind, issue.source.value,
              "->", issue.target.value)


# 1. Cây hợp lệ với hai nút khác nhau cùng payload.
root = Node("A", Node("5"), Node("5"))
show_report(root)
# nodes: 3 edges: 2 is_tree: True

# 2. Hai nhánh dùng chung một object.
d = Node("D")
b = Node("B", right=d)
c = Node("C", left=d)
shared_root = Node("A", left=b, right=c)
show_report(shared_root)
# nodes: 4 edges: 4 is_tree: False
# SHARED_NODE C -> D

# 3. Chu trình gián tiếp.
a = Node("A")
b = Node("B")
c = Node("C")
a.left = b
b.right = c
c.left = a
show_report(a)
# nodes: 3 edges: 3 is_tree: False
# CYCLE C -> A

# 4. Một nút ở cả hai vị trí con của cùng một cha.
same_child = Node("X")
double_slot = Node("A", left=same_child, right=same_child)
show_report(double_slot)
# nodes: 2 edges: 2 is_tree: False
# SHARED_NODE A -> X

# 5. Cây rỗng (được chấp nhận như một empty tree).
show_report(None)
# nodes: 0 edges: 0 is_tree: True
```

Hàm trả **các cạnh có vấn đề**, không hủy/chỉnh bất kỳ liên kết nào. Nó kiểm tra phần **reachable từ gốc được truyền vào**, không chứng minh cả kho đối tượng bên ngoài gốc tạo thành một cây.

### 6.2. Vì sao không đệ quy?

Trên cây lệch sâu hàng trăm nghìn nút, DFS đệ quy có thể chạm giới hạn call stack. Ở đây, mỗi nút hoạt động tạo **một khung tường minh** trên list Python. Stack có thể chứa O(h+1) khung theo chiều cao nhánh hiện tại, nhưng được quản lý trong vùng nhớ thông thường thay vì ép hệ thống giữ O(h) lời gọi hàm lồng nhau.

**Điều này không làm bộ nhớ miễn phí**: stack và bảng `color` vẫn có thể gặp lỗi cấp phát khi đầu vào rất lớn. Điểm quan trọng là ta kiểm soát được cấu trúc trạng thái và không bị giới hạn riêng bởi độ sâu đệ quy Python.

### 6.3. Cách đọc kết quả khi có cả chu trình lẫn chia sẻ

Hàm có thể báo nhiều `Issue`:

- `CYCLE` cho cạnh đến một node GRAY, chứng minh tồn tại chu trình có hướng.
- `SHARED_NODE` cho cạnh đến một node BLACK, chứng minh có nhiều cạnh/đường tới cùng đối tượng.

Một cạnh đến GRAY đồng thời có thể làm bậc vào của nút đích vượt quy tắc cây, nhưng bộ kiểm tra **ưu tiên báo loại “chu trình” cho cạnh đó**. Do thứ tự duyệt, một graph phức tạp có thể có các cạnh đến nút đích được báo theo cách khác khi đổi thứ tự khám phá; **nhãn cạnh là chẩn đoán của lượt DFS**, còn kết luận `is_tree=False` không phụ thuộc thứ tự.

Để có báo cáo đầy đủ về **mọi nút có bậc vào ≥ 2**, hãy đếm bậc vào riêng như Mục 8, không xem danh sách Issue là bảng thống kê bậc vào hoàn chỉnh.

### 6.4. Độ phức tạp

Nếu phần reachable chứa `V` nút **khác nhau** và `E` cạnh con khác rỗng:

- Mỗi nút đổi màu trắng → xám → đen một lần.
- Mỗi nút kiểm tra tối đa hai liên kết con (nên `E ≤ 2V` với mô hình nhị phân).
- Thời gian **O(V+E)** kỳ vọng khi dict Python tra cứu theo identity với chi phí kỳ vọng O(1).
- Bảng `color` và danh sách lỗi có thể dùng **O(V+E)** bộ nhớ trong trường hợp xấu; riêng `color` dùng O(V), stack khung O(h_DFS) với `h_DFS ≤ V`.
- Với cây hợp lệ, không có lỗi và `E=V-1`; tổng vẫn O(V).

Với đồ thị con không nhị phân, cùng ý tưởng làm việc nếu có thể liệt kê mọi cạnh con và lưu vị trí cạnh tiếp theo trong mỗi khung; chi phí vẫn O(V+E).

## 7. Giải thích dấu vết bằng DFS trên ba mẫu

### 7.1. Cây hợp lệ

```text
A -> B -> D
 \-> C

Bắt đầu: A xám.
A->B: B trắng -> B xám.
B->D: D trắng -> D xám.
D không có con: D đen.
B hoàn tất: B đen.
A->C: C trắng -> C xám; C hoàn tất -> đen.
A hoàn tất -> đen.

Không cạnh nào tới nút đã có màu.
```

Mỗi cạnh tới một nút trắng là **cạnh khám phá**, thêm một nút mới vào cây DFS. Đến cuối, số cạnh khám phá là `V-1` và không có cạnh dư.

### 7.2. Chu trình

```text
A -> B -> C
^         |
+---------+

A: xám
B: xám
C: xám
Xét C->A: A đang xám
=> A là tổ tiên trên đường DFS hiện hành.
=> Có chu trình A->B->C->A.
```

Chỉ cần một **cạnh tới GRAY** đã đủ chứng minh tồn tại một chu trình. Không cần đệ quy tiếp qua A.

### 7.3. Nút dùng chung nhưng không có chu trình

```text
A->B, A->C, B->D, C->D

Xét nhánh A->B->D:
  D được xử lý xong -> BLACK.
Xét nhánh A->C->D:
  D đang BLACK.
  => Nút D xuất hiện ở hai vị trí con.
  => Cấu trúc không còn là cây.
```

Không có đường đi có hướng quay từ D về A/B/C. Nói “có chu trình vì đã gặp D hai lần” là **khẳng định sai**. Chính phân biệt GRAY/BLACK giúp tránh nhầm một DAG với graph cyclic.


## 8. BFS và bảng bậc vào: kiểm tra theo số cạnh thực

DFS ba màu cung cấp chẩn đoán **loại cạnh**. Nếu cần báo **nút nào có bao nhiêu liên kết đi vào**, có thể dùng BFS từ gốc, đếm bậc vào và chỉ enqueue mỗi nút **một lần**.

### 8.1. Thuật toán kiểm tra theo bậc vào

```python
from collections import deque


def inspect_indegree(root: Node | None):
    """Trả (số nút, số cạnh, bậc vào, trạng thái cây)."""
    if root is None:
        return 0, 0, {}, True

    seen = {root}
    queue = deque([root])
    indegree: dict[Node, int] = {root: 0}
    edge_count = 0

    while queue:
        node = queue.popleft()

        # Kiểm tra CẢ HAI slot. Không khử trùng child trước khi đếm.
        for child in (node.left, node.right):
            if child is None:
                continue

            edge_count += 1
            indegree[child] = indegree.get(child, 0) + 1

            if child not in seen:
                seen.add(child)
                queue.append(child)

    is_tree = (
        indegree[root] == 0
        and edge_count == len(seen) - 1
        and all(
            indegree[node] == 1
            for node in seen if node is not root
        )
    )

    return len(seen), edge_count, indegree, is_tree


# Sau khai báo Node ở Mục 6:
d = Node("D")
a = Node("A",
         left=Node("B", right=d),
         right=Node("C", left=d))

n, e, indegree, valid = inspect_indegree(a)
print(n, e, valid)    # 4 4 False
print(indegree[d])    # 2
```

**Điểm cốt lõi:** đếm **mỗi cạnh** nhưng chỉ **mở rộng mỗi nút một lần**. Nếu đặt `if child not in seen` bao quanh cả câu lệnh `indegree[child] += 1`, một nút có hai cha có thể bị ghi bậc vào sai thành 1.

### 8.2. Vì sao đếm bậc vào có thể xác nhận cây?

Tất cả nút trong `seen` đều reachable từ gốc do cách BFS tạo tập. Nếu gốc có bậc vào 0 và mọi nút khác có bậc vào đúng 1, một nút không thể có đường cha thay thế. Một chu trình reachable cũng không thể tồn tại mà vẫn giữ các bậc vào ấy: vì ta đã có cạnh khám phá cho mỗi nút khác gốc, cạnh khép vòng sẽ là cạnh đi vào **bổ sung** tới một nút đã thấy (hoặc gốc).

Do đó, với cấu trúc hữu hạn và các cạnh con được liệt kê đầy đủ, quy tắc bậc vào **đủ để quyết định** phần reachable có là một cây hay không.

Tuy nhiên, bảng bậc vào **không tự chỉ rõ cạnh nào đóng chu trình**; DFS ba màu giúp chỉ ra một back edge làm nhân chứng cho chu trình.

### 8.3. Độ phức tạp

Với `V` nút reachable và `E` cạnh con:

- BFS và đếm bậc vào: **O(V+E)** thời gian kỳ vọng khi `set/dict` tra cứu identity O(1) trung bình.
- `seen`, `indegree` và queue: **O(V)** bộ nhớ; đây là bảng cho mỗi nút, không phải kết quả chỉ tính một chiều cao.
- Nếu một nút có nhiều vị trí con trùng nhau, mọi vị trí vẫn tăng `edge_count` và `indegree`.

BFS không cần ba màu khi mục tiêu chỉ là **quyết định tính hợp lệ cây và thống kê bậc vào**. Chọn theo chẩn đoán mà ứng dụng yêu cầu.

## 9. Phạm vi kiểm tra: một gốc, cả kho nút hay một rừng cây?

Có ba bài toán khác nhau:

| Bài toán | Câu hỏi thực sự | Dữ liệu cần có |
| --- | --- | --- |
| **Validate reachable subtree** | Các nút reachable từ `root` có tạo cây không? | Một gốc và các liên kết con |
| **Validate entire rooted tree** | Mọi nút mà hệ thống quản lý có nằm trong cùng một cây gốc hợp lệ không? | Gốc, registry/tập mọi nút, các liên kết |
| **Validate forest** | Có nhiều cây tách biệt, mỗi nút thuộc đúng một cây không? | Tập gốc hợp lệ, registry hoặc các tập nút toàn cục |

### 9.1. Toàn bộ kho nút cần so với kết quả reachable

Nếu có registry `all_nodes` liệt kê mọi đối tượng được quản lý, cần:

1. Kiểm tra `root` thuộc registry khi kho không rỗng.
2. Duyệt từ `root` và thu được tập `reachable` theo identity.
3. Xác minh mọi đối tượng có trong `reachable` đều thuộc registry (không có liên kết ra đối tượng ngoài kho).
4. Xác minh `reachable == all_nodes` về **danh tính nút**, không chỉ giá trị.
5. Kiểm tra không chu trình/nút dùng chung trong phần reachable.

Nếu registry có nút cô lập hoặc một chu trình riêng, kiểm tra reachable từ gốc có thể trả “cây hợp lệ” cho **phần con**, nhưng kiểm tra **toàn kho là một cây** phải thất bại vì còn thành phần không thuộc gốc.

Không thể tự đoán ra một nút ngoài vùng reachable nếu API không cung cấp registry hoặc phương pháp liệt kê tập nút ấy.

### 9.2. Kiểm tra rừng cây

Với một **rừng** (*forest*) hợp lệ, có thể có nhiều gốc và nhiều cây tách biệt; không nên báo lỗi chỉ vì có hơn một gốc nếu hợp đồng cho phép rừng.

Một chiến lược:

- Duyệt lần lượt từng gốc bằng DFS/BFS theo identity.
- Dùng một tập `owned_by` chung để đảm bảo **mỗi nút xuất hiện trong đúng một cây**.
- Nếu một nút được phát hiện từ hai gốc, đó là **chia sẻ giữa hai cây**, vi phạm sở hữu riêng của rừng.
- Với từng gốc, kiểm tra không chu trình và không có cạnh con bổ sung đi vào nút đã thăm.
- Cuối cùng so sánh hợp của mọi vùng reachable với toàn bộ registry nếu có.

**Chú ý:** nếu chỉ chạy `inspect_reachable_tree` trên từng gốc **và tạo tập màu mới mỗi lần**, hai cây chia sẻ nút D có thể mỗi cây riêng lẻ vẫn trông như cây hợp lệ. Muốn kiểm tra *không có chia sẻ giữa các gốc*, phải dùng **trạng thái toàn cục** giữa các lượt.

## 10. Trường `parent`: liên kết ngược hợp lệ không phải chu trình con

Một cấu trúc cây có thể lưu thêm `parent` để leo từ con lên cha:

```text
           A
          / \
         B   C

A.left   = B
B.parent = A

A -> B là cạnh con (đi xuống).
B.parent -> A là liên kết ngược metadata.
```

Nếu thuật toán xem **mọi con trỏ** trong object là “cạnh con” và chạy DFS, nó sẽ thấy chu trình `A -> B -> A` dù cây hợp lệ. Đây là **lỗi mô hình hóa**.

### 10.1. Phân biệt quan hệ cấu trúc và metadata

Chọn rõ tập liên kết định nghĩa cây:

- `left` và `right`: **cạnh con** được xét cho bậc vào, cycle detection và root reachability.
- `parent`: **metadata ngược**, không được duyệt như một con bổ sung trong bộ kiểm tra cấu trúc.
- `next_same_level`, `thread`, `sibling`: liên kết phụ theo hợp đồng riêng; cũng không tự là cạnh con.
- `NIL`/sentinel: điểm dừng kỹ thuật nếu kiểu cây dùng sentinel thay `NULL`.

Sau khi kiểm tra hình dạng theo `left/right`, nếu có `parent`, kiểm tra **tính nhất quán ngược**.

### 10.2. Bất biến cần kiểm tra khi có parent pointer

Với một cây đúng nghĩa:

- `root.parent is None` (hoặc sentinel theo hợp đồng).
- Nếu `u.left is v` thì `v.parent is u`.
- Nếu `u.right is v` thì `v.parent is u`.
- Một nút không được được nhận làm con của hai cha khác nhau.
- Sau thao tác **rotate**, **detach**, **attach**, **transplant** hoặc xóa, phải cập nhật metadata cha–con nhất quán.

Một parent pointer sai nhưng không được liệt kê trong `left/right` không nhất thiết tạo chu trình **cạnh con**; nó vẫn là **vi phạm bất biến metadata** cần được báo riêng.

### 10.3. Ví dụ Python kiểm tra metadata cha

```python
@dataclass(eq=False)
class ParentNode:
    value: str
    left: ParentNode | None = None
    right: ParentNode | None = None
    parent: ParentNode | None = None


def check_parent_fields(root: ParentNode | None) -> list[str]:
    if root is None:
        return []

    errors: list[str] = []
    if root.parent is not None:
        errors.append("root.parent phai rong")

    seen = {root}
    stack = [root]

    while stack:
        node = stack.pop()

        for child in (node.left, node.right):
            if child is None:
                continue

            if child.parent is not node:
                errors.append("child.parent khong khop voi lien ket cha")

            if child not in seen:
                seen.add(child)
                stack.append(child)

    return errors


a = ParentNode("A")
b = ParentNode("B", parent=a)
a.left = b
print(check_parent_fields(a))  # []

b.parent = None
print(check_parent_fields(a))
# ['child.parent khong khop voi lien ket cha']
```

Hàm trên chỉ kiểm tra **đối chiếu parent pointer**; nó **không thay thế** DFS ba màu hoặc đếm bậc vào. Nếu có shared child và parent trỏ tới một trong hai cha, kiểm tra parent có thể phát hiện một số sai khác nhưng vẫn cần kiểm định cấu trúc theo identity.

## 11. Đồ thị vô hướng: quy tắc phát hiện chu trình khác đi

Một số cây được biểu diễn thành **đồ thị vô hướng** bằng danh sách kề: mỗi cạnh `u—v` thường xuất hiện ở cả `adj[u]` lẫn `adj[v]`.

```text
A --- B --- C

adj[A] = [B]
adj[B] = [A, C]
adj[C] = [B]
```

Khi DFS đi từ A tới B, thấy cạnh B→A trong danh sách kề không phải bằng chứng có chu trình: đây là **cạnh ngược biểu diễn cùng một cạnh vô hướng đã đi qua**. Khác hẳn với việc một nút có `child.parent`, ở biểu diễn này có **hai mục adjacency cho mỗi cạnh vô hướng**.

### 11.1. DFS với parent cho đồ thị vô hướng đơn

```text
DFS_UNDIRECTED(u, parent):
    mark u visited

    for v in neighbors(u):
        if v is not visited:
            DFS_UNDIRECTED(v, u)
        else if v != parent:
            report cycle
```

Quy tắc trên phù hợp với **đồ thị vô hướng đơn** (không self-loop, không hai cạnh song song cùng cặp đỉnh) nếu xử lý các trường hợp riêng đúng.

Nếu đồ thị cho phép **cạnh song song** giữa cùng hai đỉnh, chỉ kiểm tra `v == parent` có thể bỏ sót chu trình độ dài hai cạnh. Khi đó cần nhận biết **ID cạnh** và bỏ qua **chính cạnh đã dẫn tới nút**, không bỏ qua mọi cạnh tới cùng đỉnh cha.

### 11.2. Hai điều kiện của cây vô hướng

Một đồ thị vô hướng hữu hạn với `V` đỉnh là cây khi:

- **Liên thông**.
- **Không có chu trình**.

Tương đương (với phép đếm cạnh đúng, kể cả trường hợp tự nối/đa cạnh theo mô hình tương ứng): đồ thị **liên thông** và có `E=V-1` cạnh.

Có thể dùng BFS/DFS với parent hoặc cấu trúc **Disjoint Set Union (DSU/Union-Find)** để phát hiện cạnh nối hai đỉnh đã cùng thành phần; DSU phù hợp khi xử lý danh sách các cạnh vô hướng và muốn xác định chu trình dần dần.

### 11.3. Không trộn lẫn hai mô hình

| Mô hình | Cạnh kiểm tra | Có bỏ qua edge ngược tới cha không? |
| --- | --- | --- |
| Cây có gốc bằng `left/right` | Chỉ hướng **cha → con** | Không có edge ngược trong mô hình; `parent` không được xem là con |
| Đồ thị vô hướng bằng adjacency list | Mỗi cạnh quan hệ vô hướng | Có, nhưng bỏ qua **cạnh đi vào tương ứng**, đặc biệt khi có cạnh song song |
| DAG hoặc đồ thị có hướng | Cạnh đi theo hướng thật | **Không** được tự bỏ qua cạnh tới parent nếu đó là một cạnh có hướng hợp lệ |

Chọn sai mô hình có thể khiến cây hợp lệ bị báo chu trình hoặc graph cyclic lại được báo hợp lệ.

## 12. C++: bộ kiểm tra cây nhị phân bằng địa chỉ nút

Đối với một cây C++ có `Node*`, ta có thể dùng `std::unordered_map<const Node*, Color>` để nhận biết **danh tính địa chỉ**. Stack khung tường minh giúp tránh lời gọi đệ quy sâu.

### 12.1. Ví dụ C++17 độc lập

```cpp
#include <cstddef>
#include <iostream>
#include <unordered_map>
#include <vector>

struct Node {
    int id;
    const Node* left = nullptr;
    const Node* right = nullptr;
};

enum class Color { Gray, Black };

struct Frame {
    const Node* node;
    int next_child; // 0: left, 1: right, 2: done
};

struct Report {
    std::size_t nodes = 0;
    std::size_t edges = 0;
    std::size_t cycles = 0;
    std::size_t shared = 0;

    bool is_tree() const {
        return cycles == 0 && shared == 0;
    }
};

Report inspect(const Node* root) {
    Report report;
    if (root == nullptr) return report;

    std::unordered_map<const Node*, Color> color;
    std::vector<Frame> stack;

    color.emplace(root, Color::Gray);
    stack.push_back({root, 0});

    while (!stack.empty()) {
        Frame& frame = stack.back();

        if (frame.next_child == 2) {
            color[frame.node] = Color::Black;
            stack.pop_back();
            continue;
        }

        // Đọc child trước khi có khả năng push làm vector realloc.
        const Node* child =
            frame.next_child == 0
                ? frame.node->left
                : frame.node->right;

        ++frame.next_child;
        if (child == nullptr) continue;

        ++report.edges;

        auto found = color.find(child);

        if (found == color.end()) {
            color.emplace(child, Color::Gray);
            stack.push_back({child, 0});
        } else if (found->second == Color::Gray) {
            ++report.cycles;
        } else {
            ++report.shared;
        }
    }

    report.nodes = color.size();
    return report;
}

int main() {
    Node a{1}, b{2}, c{3}, d{4};

    a.left = &b;
    a.right = &c;
    b.right = &d;
    c.left = &d;

    Report shared = inspect(&a);
    std::cout << std::boolalpha
              << shared.is_tree() << " "
              << shared.nodes << " "
              << shared.edges << " "
              << shared.shared << "\n";
    // false 4 4 1

    // Tạo thêm chu trình D -> A.
    d.left = &a;
    Report cyclic = inspect(&a);
    std::cout << cyclic.cycles << "\n"; // Ít nhất 1

    // Ví dụ chỉ hợp lệ về mặt lifetime khi a,b,c,d còn sống.
}
```

Khi `stack.push_back` gây `realloc`, tham chiếu `frame` tới phần tử của vector có thể bị vô hiệu. Mã đã **đọc child và tăng `next_child` trước khi push**, rồi không dùng `frame` nữa trong lượt ấy. Đây là điểm quan trọng để không vô tình tạo một lỗi iterator mới trong chính hàm xác minh.

### 12.2. Hợp đồng bộ nhớ của phiên bản C++

- Các `Node` do `main` sở hữu; `inspect` **chỉ đọc**, không `delete` nút.
- Mọi node reachable phải còn sống và các con trỏ phải hợp lệ trong suốt quá trình.
- `std::unordered_map` và `std::vector` có thể cấp phát/ném ngoại lệ khi hết bộ nhớ; không nên tuyên bố hàm luôn hoàn thành với input khổng lồ.
- Phép so sánh địa chỉ ở đây dùng để nhận biết **object identity** trong cấu trúc nút sống; không phải cơ chế xác thực con trỏ tùy ý.
- Nếu một luồng khác sửa `left/right` đồng thời không đồng bộ, có thể có data race; bộ màu không biến hàm thành thread-safe.

### 12.3. Độ phức tạp

Với `V` node và `E` child-edge reachable:

- O(V+E) thời gian kỳ vọng theo bảng băm.
- O(V) metadata cho `unordered_map` và O(h_DFS) stack khung, với `h_DFS ≤ V`.
- Không sửa dữ liệu nguồn và không cần đệ quy, nên thích hợp cho cây rất sâu ở góc độ call stack.

Điều kiện còn thiếu nếu muốn sử dụng trong sản phẩm: xử lý input không tin cậy ở mức pointer, giới hạn tài nguyên, lỗi cấp phát và chính sách chẩn đoán nếu muốn **đường dẫn cụ thể tới chu trình** thay vì chỉ số lượng lỗi.


## 13. Đưa ra nhân chứng: đường chu trình và hai đường tới cùng nút

Đôi khi chỉ báo `False` là chưa đủ. Để sửa dữ liệu, người dùng cần biết **liên kết nào** gây lỗi và **vì sao**.

### 13.1. Tìm một chu trình cụ thể

Khi DFS xét cạnh `u → v` và `v` đang GRAY, `v` là tổ tiên của `u` trên đường DFS hiện hành. Nếu lưu thêm `dfs_parent[x]` của mỗi nút được phát hiện lần đầu, có thể dựng chu trình:

1. Bắt đầu từ `u`, lần lượt đi qua `dfs_parent` đến khi gặp `v`.
2. Đảo dãy vừa thu được để có đường `v → ... → u`.
3. Gắn `v` ở cuối để đóng vòng bằng cạnh `u → v`.

```text
A -> B -> C -> D
     ^         |
     +---------+

DFS đang ở D, xét cạnh D->B.
Theo dfs_parent: D, C, B.
Đảo lại: B, C, D.
Thêm B:  B -> C -> D -> B.  (nhân chứng chu trình)
```

Hàm minh họa sau giả định đã xác nhận `target_gray` là tổ tiên của `source` trong đúng lượt DFS và có bảng `dfs_parent` tương ứng:

```python
def cycle_witness(source, target_gray, dfs_parent):
    """Trả đường target -> ... -> source -> target."""
    backward = [source]
    node = source

    while node is not target_gray:
        node = dfs_parent[node]
        backward.append(node)

    backward.reverse()
    backward.append(target_gray)
    return backward
```

Muốn sử dụng trong `inspect_reachable_tree`, ghi `dfs_parent[root] = None`, và khi phát hiện một nút WHITE `child`, ghi `dfs_parent[child] = node` trước khi đẩy frame. Khi gặp cạnh tới GRAY, gọi hàm với `(node, child, dfs_parent)`.

Với một cạnh lỗi, việc dựng nhân chứng mất O(chiều dài chu trình), tối đa O(V). Nếu dựng một nhân chứng **cho mọi back edge** độc lập, tổng chi phí báo cáo có thể lớn hơn O(V+E) do lặp lại các đường; nên giới hạn số nhân chứng hoặc dùng cấu trúc chẩn đoán phù hợp.

### 13.2. Hai đường đi chứng minh nút được dùng chung

Với một cạnh `u → v` và `v` đã BLACK, bảng `dfs_parent` cho biết đường khám phá đầu tiên từ gốc tới `v`.

Cạnh mới cho một đường thứ hai:

```text
Đường thứ nhất: root -> ... -> v
Đường thứ hai:  root -> ... -> u -> v
```

Nếu các đường **khác nhau ở ít nhất một vị trí cạnh**, cùng một nút `v` đã được đưa vào hai vị trí cấu trúc. Đây là một **nhân chứng chia sẻ**.

Ví dụ:

```text
A -> B -> D
 \-> C -> D

P1 = [A, B, D]
P2 = [A, C, D]
```

Nếu cả hai liên kết `A.left` và `A.right` trỏ tới D thì hai dãy node đều có dạng `[A, D]`. Khi đó cần **ghi thêm tên slot cạnh (`left/right`)** để phân biệt hai vị trí cấu trúc; chỉ lưu dãy danh tính nút chưa đủ làm chứng cứ cho “hai cạnh” trong trường hợp này.

### 13.3. Thông tin nên đưa vào báo cáo

Một hệ thống chẩn đoán có thể ghi:

| Trường | Ý nghĩa |
| --- | --- |
| `kind` | `CYCLE`, `SHARED_NODE` hoặc `UNREACHABLE` |
| `source_id`, `target_id` | ID/danh tính hai đầu của cạnh lỗi |
| `slot` | `left`, `right` hoặc tên vị trí con |
| `root_id` | Gốc của phạm vi đang kiểm tra |
| `path1`, `path2` | Nhân chứng đường đi, nếu cần |
| `node_count`, `edge_count` | Tóm tắt số nút/cạnh reachable |
| `version` | Phiên bản cây/registry được kiểm tra nếu có |

**Không nên log địa chỉ con trỏ tùy tiện như một ID công khai** khi điều đó làm lộ chi tiết bộ nhớ hoặc không ổn định giữa các phiên chạy. Trong ứng dụng, có thể gán ID nội bộ duy nhất cho lần kiểm tra.

## 14. Xử lý sau khi phát hiện lỗi: không sửa hoặc free tùy tiện

Khi cấu trúc không còn là cây, quyết định tiếp theo phụ thuộc **ý nghĩa nghiệp vụ** và **chính sách sở hữu**. Hai liên kết vào cùng nút đôi khi là lỗi, nhưng đôi khi là **chia sẻ có chủ đích** của một DAG/persistent structure.

### 14.1. Nếu có chu trình không mong muốn

Cách khắc phục có thể là:

1. Chọn cạnh sai dựa trên dữ liệu nguồn, quy tắc nghiệp vụ hoặc dấu vết tạo liên kết.
2. Ngắt **đúng cạnh** ấy, đưa vị trí con về `NULL` hay con phù hợp.
3. Kiểm tra lại **toàn bộ bất biến**: khả năng reachable, bậc vào, không còn chu trình, parent pointer và các chỉ mục phụ.
4. Cập nhật phiên bản cấu trúc, vô hiệu hoặc xây lại iterator/cache phụ thuộc đường liên kết cũ.

**Không có thuật toán tổng quát** nào chỉ dựa trên hình dạng graph mà luôn biết “cạnh nào là lỗi nghiệp vụ”. Ví dụ, từ vòng `A→B→C→A`, cắt một trong ba cạnh đều có thể phá vòng nhưng tạo ba cấu trúc khác nhau.

### 14.2. Nếu có nút được dùng chung

Có ít nhất ba lựa chọn:

- **Chỉ một cha sở hữu nút**: ngắt liên kết còn lại, và bảo đảm nhánh bị mất vẫn thỏa yêu cầu nghiệp vụ.
- **Clone cây con được chia sẻ**: tạo một bản sao sâu độc lập cho một vị trí cha, rồi nối lại; cần xử lý lỗi cấp phát và metadata cha.
- **Công nhận cấu trúc là DAG**: đổi API traversal/clone/serialization/destroy sang thuật toán đồ thị có visited và ownership phù hợp.

Chọn phương án nào cũng có thể thay đổi dữ liệu quan sát được, nên phải dựa vào đặc tả và ý định, không tự “sửa” khi gặp nút lặp.

### 14.3. Giải phóng graph phải dựa trên danh tính và ownership

Một destructor kiểu cây thường giả định mọi nút chỉ reachable theo **một đường**. Với graph có sharing hoặc chu trình, hàm đệ quy ngây thơ:

```c
/* SAI với graph có chu trình hoặc shared node. */
void destroy_as_tree(Node *node) {
    if (node == NULL) return;
    destroy_as_tree(node->left);
    destroy_as_tree(node->right);
    free(node);
}
```

có thể lặp vô hạn, giải phóng trùng hoặc đọc con trỏ của nút đã hủy.

Đối với một graph sở hữu các nút cấp phát động riêng và được phép hủy **toàn bộ**, cách khái quát an toàn hơn là:

1. **Thu thập trước** danh sách các nút **khác nhau** reachable bằng visited theo identity; giữ lại các con trỏ trong worklist trước khi giải phóng bất kỳ nút nào.
2. Nếu cấp phát cho bảng visited/worklist thất bại, **không bắt đầu hủy dở** nếu không có phương án cleanup khác.
3. Khi đã thu thập đầy đủ, giải phóng mỗi nút **đúng một lần** theo danh sách unique; không dereference nút sau `free`.
4. Dọn payload theo ownership trước hoặc trong khi hủy từng đối tượng; các liên kết mượn không được hủy như object sở hữu.
5. Không cho thread/iterator khác tiếp tục đọc các nút đã hủy.

Phương án thu thập hai pha dùng **O(V)** bộ nhớ phụ trợ và O(V+E) thời gian kỳ vọng cho traversal, thêm O(V) thao tác hủy nút, nhưng rõ ràng hơn việc cố “đi tiếp sau free”.

Nếu graph dùng reference counting, garbage collection hoặc một kho quản lý ID và vòng đời riêng, destructor phải tuân thủ hệ thống ấy. Một chu trình giữa các `shared_ptr` mạnh có thể giữ đối tượng sống không mong muốn; đó là vấn đề quản lý ownership, không giải được chỉ bằng DFS tìm chu trình.

### 14.4. Không tiếp tục dùng bộ duyệt cây cũ

Một bộ duyệt inorder hoặc BFS đang giữ stack/queue các con trỏ tới nút. Sau khi sửa hoặc hủy liên kết:

- Vị trí “tiếp theo” có thể đã đổi.
- Con trỏ có thể trỏ vào object đã được thu hồi.
- Thứ tự BST hoặc độ sâu cũng có thể không còn hợp lệ.

Trong trường hợp có thể thay đổi cấu trúc, nên xác định chính sách **cấm sửa khi duyệt**, **fail-fast theo version**, **snapshot**, **persistent structure**, hoặc một API graph/live iterator có hợp đồng cụ thể.

## 15. Kiểm tra đầu vào trước các thao tác biến đổi tốn kém

Không phải mọi hàm xử lý cây đều cần chạy kiểm định O(V+E) trước mỗi lần gọi. Nhưng với **dữ liệu nhập từ ngoài, cây khôi phục từ file, liên kết được nối thủ công hoặc một kho có nhiều tác nhân sửa**, kiểm định ở đúng ranh giới có thể tránh hậu quả nghiêm trọng.

### 15.1. Một pipeline tiếp nhận dữ liệu

```text
Đọc / tạo cấu trúc
        |
        v
Xác định tập cạnh thực sự định nghĩa cây
        |
        v
Xác thực ID / chỉ số / vùng lưu trữ hợp lệ
        |
        v
Kiểm tra reachable + chu trình + nhiều liên kết vào
        |
        +---- FAIL ---> Báo lỗi / cách ly cấu trúc / sửa có kiểm soát
        |
        v
Kiểm tra bất biến riêng (BST, heap, đỏ–đen, metadata parent...)
        |
        v
Cho phép thuật toán cây: clone, traversal, height, LCA, destroy
```

Một dạng “cây” có thể qua được kiểm tra **không chu trình/không nhiều cha** nhưng vẫn không phải BST nếu thứ tự khóa sai, hoặc không phải heap nếu quan hệ cha–con về ưu tiên sai. **Kiểm tra hình dạng cây chỉ là lớp bất biến nền tảng.**

### 15.2. Dữ liệu nhập bằng ID an toàn hơn con trỏ chưa xác minh

Nếu đầu vào từ JSON, tệp nhị phân hoặc database, nên biểu diễn liên kết bằng **ID/offset/chỉ số** đã được kiểm tra giới hạn, rồi dựng graph trong bộ nhớ. Không nên ép các số từ đầu vào thành `Node*` và giải tham chiếu chúng: thuật toán visited/DFS không thể chứng minh một địa chỉ tùy ý là hợp lệ.

Một pipeline cơ bản:

- Kiểm tra ID xuất hiện trong bảng nút.
- Kiểm tra mỗi slot con chứa ID hợp lệ hoặc marker “không có con”.
- Kiểm tra các ID trùng theo quy tắc nghiệp vụ.
- Tạo adjacency và chạy validator theo identity/ID.
- Chỉ sau đó mới cấp quyền dùng các thuật toán giả định cây.

### 15.3. Kiểm tra đồng thời trên một ảnh chụp nhất quán

Trong chương trình nhiều luồng, nếu một thread sửa `left/right` trong lúc validator đang đọc, kết quả có thể không tương ứng với **bất kỳ trạng thái cây hoàn chỉnh** nào. Trong C/C++, đọc và ghi không đồng bộ còn có thể gây **data race**.

Một vài chiến lược:

- Khóa các thay đổi cấu trúc trong lúc kiểm tra.
- Chụp một snapshot nhất quán rồi xác minh snapshot.
- Gắn validator với một phiên bản bất biến của cây.
- Dùng cơ chế version và xác minh lại theo hợp đồng đồng bộ đầy đủ; **chỉ kiểm tra version đầu/cuối không tự thay thế khóa hoặc memory ordering**.

Nếu đầu vào có kích thước không kiểm soát, cần giới hạn số nút, số cạnh, thời gian kiểm tra và dung lượng bảng visited để tránh cạn tài nguyên.

## 16. Bảng so sánh các kỹ thuật

| Phương pháp | Phát hiện chu trình | Phát hiện nút dùng chung | Truy ra loại lỗi | Bộ nhớ thêm | Ghi chú |
| --- | --- | --- | --- | --- | --- |
| DFS ba màu | Có | Có | Phân biệt cạnh tới GRAY/BLACK | O(V) bảng màu + O(h_DFS) stack | Phù hợp chẩn đoán trực tiếp theo cạnh |
| BFS + visited + bậc vào | Có thể quyết định cây hợp lệ/không theo bậc vào, không chỉ đích danh chu trình | Có | Biết nút nào có indegree ≥ 2 | O(V) + queue O(V) | Đếm mọi cạnh, kể cả slot lặp |
| Chỉ visited boolean | Nhận ra cạnh đến nút đã thấy | Có thể phát hiện lặp | **Không phân biệt** cycle với sharing | O(V) | Dùng cho traversal graph, không đủ chẩn đoán |
| Đếm `V`/`E` đúng | Phát hiện có cạnh dư trong phần reachable | Phát hiện có cạnh dư | Không cho biết cạnh lỗi | O(V) để xác định nút unique | `E=V-1` đủ khi mọi nút đã reachable |
| DFS với parent trên graph vô hướng đơn | Có | Không diễn giải theo “nhiều cha” | Chu trình vô hướng | O(V) | Phải bỏ qua đúng edge đi vào |
| DSU/Union-Find trên danh sách cạnh vô hướng | Có | Không áp dụng trực tiếp quy tắc cha có hướng | Cạnh tạo vòng thành phần | O(V) | Kiểm tra liên thông riêng |
| Chỉ kiểm tra `left != right` | Không | Chỉ một kiểu trùng slot tại cùng nút | Rất hạn chế | O(1) mỗi nút | Không chứng minh toàn cây |
| Duyệt đệ quy không visited | Không an toàn trên graph cyclic | Dễ thăm trùng | Không có chẩn đoán đáng tin | O(h) call stack, có thể không kết thúc | Không dùng để xác minh đầu vào có thể sai |

**`h_DFS`** là độ sâu đường khám phá DFS trên graph, tối đa O(V), không phải “chiều cao cây” khi cấu trúc đã có chu trình. Các bậc thời gian cho hash-based set/map là kỳ vọng O(V+E) với phép hash/so sánh thích hợp; trường hợp xấu nhất của bảng băm phụ thuộc chính sách collision và dữ liệu.

## 17. Kiểm thử hệ thống cho bộ kiểm tra cây

Một bộ kiểm tra mạnh phải bao phủ cả **cây đúng** lẫn **đồ thị không đúng**. Chỉ thử với BST cân bằng hoặc cây một nút sẽ không phát hiện nhiều lỗi quan trọng.

### 17.1. Các ca kiểm thử cốt lõi

1. **Gốc rỗng:** chấp nhận theo quy ước “cây rỗng” nếu API cho phép.
2. **Một nút:** `V=1, E=0`, là cây.
3. **Cây một đường rất sâu:** chạy không đệ quy, đúng `E=V-1`.
4. **Cây cân đối nhiều tầng:** không báo shared/cycle giả.
5. **Hai nút khác nhau cùng value:** vẫn là cây.
6. **`root.left is root`:** báo `CYCLE`.
7. **Chu trình dài:** ví dụ `A→B→C→A`, kết thúc và báo chu trình.
8. **`root.left is root.right`:** báo `SHARED_NODE`, hai slot cùng trỏ một object.
9. **Hai cha khác nhau dùng chung một con:** báo `SHARED_NODE`, không nhầm thành chu trình nếu không có edge ngược.
10. **DAG nhiều tầng:** shared child có thể được trỏ tới nhiều lần; không lặp vô hạn và đếm node unique.
11. **Graph vừa chia sẻ vừa có chu trình:** có thể báo nhiều lỗi; kết luận không phải cây.
12. **Self-loop ở nút sâu:** không chỉ kiểm tra gốc.
13. **Registry có nút cô lập:** kiểm tra reachable có thể pass, kiểm tra toàn registry phải fail.
14. **Rừng hai cây không giao nhau:** hợp lệ nếu hợp đồng là forest, không hợp lệ nếu đòi một root duy nhất.
15. **Hai gốc cùng chia sẻ nút:** phát hiện khi dùng bộ visited/ownership toàn cục.
16. **Parent pointer đúng:** không được xem parent là child-cycle.
17. **Parent pointer sai:** báo lỗi metadata dù child graph vẫn là cây.
18. **Nút sentinel/NIL:** phải loại khỏi tập node dữ liệu theo đúng API.
19. **Nhiều ID cùng payload hoặc payload rỗng:** kiểm tra theo identity/ID.
20. **Chuyển cây con/gắn lại liên kết:** xác minh trạng thái trước và sau cập nhật, bao gồm khả năng sinh chu trình.
21. **Cây rất lớn:** đánh giá giới hạn stack tường minh, bảng hash, dung lượng lỗi và hành vi khi hết bộ nhớ.
22. **Sửa cây đồng thời:** chỉ kiểm tra trong chính sách khóa/snapshot hợp lệ, không dựa vào xác suất “không crash”.

### 17.2. Test Python nhỏ bằng khẳng định

Các đoạn dưới dùng `Node` và `inspect_reachable_tree` từ Mục 6.

```python
# Cây một đường hợp lệ.
head = Node("0")
cursor = head

for i in range(1, 50000):
    child = Node(str(i))
    cursor.left = child
    cursor = child

report = inspect_reachable_tree(head)
assert report.is_tree
assert report.node_count == 50000
assert report.edge_count == 49999

# Cạnh ngược từ lá về gốc tạo chu trình.
cursor.right = head
report = inspect_reachable_tree(head)
assert not report.is_tree
assert any(issue.kind == "CYCLE" for issue in report.issues)

# Khôi phục, rồi tạo một shared node từ hai slot.
cursor.right = None
shared = Node("shared")
head.right = shared
head.left.right = shared

report = inspect_reachable_tree(head)
assert not report.is_tree
assert any(issue.kind == "SHARED_NODE" for issue in report.issues)
```

**Chi tiết quan trọng:** trong đoạn cuối, `head.left` không rỗng vì chuỗi được dựng dài 50.000 nút. Khi thêm `head.right = shared` và `head.left.right = shared`, hai cạnh từ hai nút khác nhau dẫn đến chính object `shared`. Việc này không tạo chu trình vì `shared` không trỏ ngược về tổ tiên.

Bài kiểm thử chọn 50.000 nút để phơi bày giới hạn đệ quy, nhưng kích thước thực tế phải phù hợp bộ nhớ máy chạy test. Để test hiệu quả, kết hợp ca nhỏ dễ debug và ca sâu phục vụ đánh giá tài nguyên.

### 17.3. Đối chiếu các bất biến tự động

Với một report có `is_tree=True` và gốc không rỗng, cần có:

\[
edge\_count = node\_count - 1.
\]

Với mọi nút non-root, bảng bậc vào phải bằng 1; với gốc bằng 0. Nếu hai phương pháp **DFS màu** và **BFS bậc vào** cho kết luận khác nhau khi cây đứng yên, có lỗi ở hiện thực hoặc giả định về cách liệt kê cạnh.

Một dạng property-based testing hữu ích:

- Sinh các cây nhị phân hợp lệ ngẫu nhiên bằng cách gắn **một nút mới** vào một slot con rỗng của nút đang có.
- Kiểm tra validator chấp nhận mọi cây sinh ra.
- Chọn một liên kết và đổi nó sang một nút tổ tiên để sinh chu trình, hoặc tới một nút đã reachable để tạo sharing.
- Kiểm tra validator bác bỏ cấu trúc mới và không bị mắc kẹt.
- So sánh chẩn đoán với thao tác phá hỏng đã áp dụng, lưu ý một đồ thị phức tạp có thể chứa **nhiều lỗi đồng thời**.

Cần tránh sinh một “ca lỗi” mà thực ra chỉ **di chuyển** một nhánh hợp lệ, ví dụ xóa hẳn liên kết cũ rồi nối sang cha mới: thao tác đó có thể tạo một cây mới hoàn toàn hợp lệ. Muốn chắc chắn sinh shared node, phải **giữ nguyên liên kết cũ** và tạo thêm một liên kết mới tới **cùng node**.

## 18. Bài tập thực hành có lời giải

### Bài 1. Xác định tính hợp lệ của cây

```text
    A
   / \
  B   C
     /
    D
```

**Hỏi:** Đây có phải cây có gốc theo mô hình left/right không?

**Lời giải:** Có. Mọi nút reachable từ A, gốc không có cạnh đi vào, các nút B/C/D mỗi nút có một cạnh đi vào và không có chu trình. `V=4, E=3`.

### Bài 2. Hai nút cùng payload

Hai nút khác nhau B và C đều có `value=5`, là hai con của A. Có phải vi phạm “nhiều cha” không?

**Lời giải:** Không. Hai object khác nhau có thể mang cùng giá trị; mỗi object có đúng một cạnh đi vào. Chỉ nếu một bất biến khóa nghiệp vụ cấm trùng giá trị thì mới có lỗi riêng.

### Bài 3. Cùng node ở hai slot

```python
child = Node("X")
root = Node("A", left=child, right=child)
```

**Lời giải:** Không phải cây sở hữu riêng. Có hai cạnh `A.left→X` và `A.right→X`, `indegree[X]=2`. Đây là chia sẻ một node qua hai slot, dù có một object cha A.

### Bài 4. Chu trình tự trỏ

```python
a = Node("A")
a.left = a
```

**Lời giải:** Cạnh `A→A` là self-loop, tạo chu trình độ dài một. DFS gặp A đang GRAY khi xét `a.left` và báo `CYCLE`.

### Bài 5. Đồ thị hình thoi

```text
    A
   / \
  B   C
   \ /
    D
```

**Lời giải:** `V=4, E=4`; D có hai cạnh đi vào. Nếu D không có liên kết ngược, đây là DAG dùng chung node, **không có chu trình** nhưng cũng **không là cây**.

### Bài 6. Chu trình dài

`A.left=B`, `B.right=C`, `C.left=A`. Khi DFS đang xét cạnh `C→A`, A có màu gì?

**Lời giải:** A đang **GRAY** vì lượt DFS đã vào A nhưng chưa kết thúc nó. Cạnh đi ngược tới tổ tiên A chứng minh chu trình `A→B→C→A`.

### Bài 7. Vì sao BLACK khác GRAY?

Một cạnh mới dẫn tới node đã BLACK. Có thể tuyên bố ngay “có chu trình” không?

**Lời giải:** Không. Node BLACK đã xử lý xong, có thể được dùng từ một nhánh khác trong DAG. Cạnh đó chứng minh chia sẻ/nhiều đường trong mô hình cây, nhưng không nhất thiết tạo directed cycle.

### Bài 8. Tại sao chỉ dùng visited chưa đủ chẩn đoán?

**Lời giải:** Set visited cho biết node đã từng gặp, không biết node đang ở **đường DFS hoạt động** hay đã hoàn tất. Cả chu trình và shared subtree đều có thể dẫn đến “đã thăm”; cần GRAY/BLACK hoặc trạng thái tương đương để phân biệt.

### Bài 9. Đếm `V` và `E`

Một vùng reachable có 10 node khác nhau và 11 cạnh con. Có phải cây hợp lệ không?

**Lời giải:** Không. Cây có 10 nút phải có 9 cạnh. `E=11` cho thấy có 2 cạnh dư so với cây phát hiện; có thể do chia sẻ, chu trình hoặc kết hợp. Cần xem cạnh để xác định loại lỗi.

### Bài 10. Cạnh vào gốc

Gốc A có `A.left=B` và `B.left=A`. Bậc vào của gốc là bao nhiêu, và điều gì sai?

**Lời giải:** Trong phần reachable, A có một cạnh vào từ B nên `indegree[A]=1` thay vì 0. Có chu trình A→B→A.

### Bài 11. Bỏ đếm cạnh nếu đã visited

Một BFS chỉ tăng `indegree[child]` khi `child not in seen`. Có thể phát hiện D có hai cha trong graph hình thoi không?

**Lời giải:** Không chắc. Khi D gặp lần thứ hai, điều kiện `child not in seen` sai và lần tăng bậc vào bị bỏ. Phải **tăng bậc vào cho mọi cạnh**, còn kiểm tra visited chỉ quyết định có enqueue lại hay không.

### Bài 12. Cây rỗng

`inspect_reachable_tree(None)` nên trả gì?

**Lời giải:** Theo quy ước bài học, cây rỗng hợp lệ: `node_count=0`, `edge_count=0`, `issues=[]`, `is_tree=True`. API khác có thể bắt buộc phải có gốc; cần ghi rõ hợp đồng.

### Bài 13. Nút ngoài vùng reachable

Từ gốc A chỉ có thể tới B. Ngoài ra registry còn có X và Y nối thành chu trình `X→Y→X`. `inspect_reachable_tree(A)` có phát hiện được chu trình ấy không?

**Lời giải:** Không. Nó chỉ kiểm tra phần reachable từ A. Muốn xác minh **toàn registry là một cây**, phải có registry và đảm bảo mọi node đều reachable; sau đó kiểm tra cấu trúc.

### Bài 14. Rừng hai gốc

Hai cây hợp lệ `R1` và `R2` không chia sẻ nút. Hệ thống cho phép forest. Có lỗi vì có hai gốc không?

**Lời giải:** Không, theo hợp đồng **rừng cây**. Mỗi cây riêng là hợp lệ. Nhưng nếu nghiệp vụ yêu cầu **một cây duy nhất**, phải bác bỏ vì có hai thành phần.

### Bài 15. Hai gốc dùng chung một nút

Hai lần `inspect_reachable_tree(R1)` và `inspect_reachable_tree(R2)` đều trả `True`, nhưng một nút D xuất hiện trong cả hai cây. Rừng có sở hữu riêng hợp lệ không?

**Lời giải:** Không. Hai cây dùng chung một object; cần **bảng visited/owner chung giữa các gốc** để phát hiện. Một lượt validate tách biệt không đủ chứng minh không có chia sẻ trên toàn rừng.

### Bài 16. Parent pointer hợp lệ

`A.left=B` và `B.parent=A`. Khi chỉ kiểm tra cạnh con, có chu trình không?

**Lời giải:** Không. `parent` là liên kết metadata ngược và **không nằm trong tập cạnh con** `left/right`. Phải kiểm tra độ khớp của nó riêng, không đưa nó vào DFS như một nhánh con.

### Bài 17. Parent pointer sai

`A.left=B` nhưng `B.parent=C`. Cấu trúc cạnh con có thể vẫn là cây không?

**Lời giải:** Có thể có, nếu các cạnh `left/right` tạo một cây hợp lệ. Tuy nhiên, metadata `B.parent` **không nhất quán**, phải báo một lỗi riêng về bất biến cha–con.

### Bài 18. Đồ thị vô hướng

Với cạnh vô hướng `A—B`, trong adjacency list có cả A→B và B→A. Tại sao DFS vô hướng không thể coi mọi cạnh đến một node đã visited là chu trình?

**Lời giải:** Cạnh B→A chỉ là biểu diễn ngược của **cùng cạnh vô hướng** vừa đi qua. Phải bỏ qua cạnh đi vào từ parent theo edge ID phù hợp. Với graph đa cạnh, bỏ qua mọi cạnh về parent theo ID đỉnh có thể làm mất chu trình do cạnh song song.

### Bài 19. Cấu trúc bị lỗi trước khi free

Một node D thuộc cả nhánh trái và phải của cây. Vì sao `free_tree(left); free_tree(right)` kiểu cây sở hữu riêng có thể nguy hiểm?

**Lời giải:** Hai nhánh cùng reachable tới D, nên D có thể bị `free` hai lần hoặc bị truy cập sau lần hủy đầu. Phải xác định ownership và xử lý theo danh tính nếu là graph.

### Bài 20. Sửa một chu trình

Graph có vòng `A→B→C→A`. Chỉ dựa trên hình dạng, có biết chắc nên cắt cạnh nào để đúng nghiệp vụ không?

**Lời giải:** Không. Cắt một trong các cạnh có thể phá vòng nhưng tạo các cấu trúc khác nhau. Cần hợp đồng dữ liệu và nguồn gốc liên kết để chọn cạnh; sau sửa phải kiểm định lại.

### Bài 21. Sửa nút dùng chung

D là con của B và C. Có những cách nào để biến nó thành một cây sở hữu riêng?

**Lời giải:** Có thể ngắt một liên kết nếu không cần nhánh đó, hoặc clone sâu D và các nút con cho một cha. Nếu sharing là chủ đích, nên giữ DAG và đổi thuật toán, không ép dữ liệu thành cây một cách tùy tiện.

### Bài 22. Độ phức tạp DFS ba màu

Vùng reachable có `V` node, `E` liên kết con. Với dict hash identity, độ phức tạp kỳ vọng là gì?

**Lời giải:** O(V+E) thời gian, O(V) bảng trạng thái và O(h_DFS) stack khung, cộng dung lượng danh sách lỗi nếu ghi lại từng cạnh dư. Với mô hình nhị phân, `E≤2V` nên bậc thời gian vẫn tuyến tính theo V.

### Bài 23. Cây rất sâu

Có một đường từ gốc tới lá dài 100.000 cạnh. Vì sao nên dùng DFS ba màu không đệ quy?

**Lời giải:** Đệ quy có thể vượt giới hạn call stack; stack tường minh giúp quản lý trạng thái trong container động. Vẫn cần O(V) bộ nhớ bảng màu và có thể O(h_DFS) stack, nên không có nghĩa là bộ nhớ hằng số.

### Bài 24. BST đúng thứ tự cục bộ nhưng có vòng

`A.value=10`, `B.value=5`, `A.left=B` và `B.right=A`. Hai phép so sánh cạnh trái/phải có vẻ phù hợp BST. Cấu trúc có là BST hợp lệ không?

**Lời giải:** Không. Có chu trình A→B→A và một nút có đường về gốc, vi phạm cấu trúc cây. Kiểm tra vài phép so sánh khóa cục bộ không thay thế kiểm tra hình dạng và bất biến thứ tự trên **cả cây**.

### Bài 25. Version của validator

Một thread kiểm tra version trước khi duyệt, thread khác sửa `left/right` giữa lượt, validator kiểm tra lại version cuối. Điều này có tự bảo đảm kết quả đúng và không data race trong C++ không?

**Lời giải:** Không. Chỉ đọc phiên bản đầu/cuối không tự đồng bộ truy cập các liên kết; dữ liệu có thể bị thay đổi không an toàn giữa lượt. Cần khóa, snapshot, phiên bản bất biến hoặc thiết kế concurrent đúng mô hình bộ nhớ.

## 19. Tổng kết và checklist áp dụng

- **Cây có gốc** không chỉ là object có `left/right`. Trong phạm vi reachable, mỗi nút khác gốc cần đúng một cạnh đi vào, gốc không có cạnh đi vào và không có chu trình.
- **Chu trình** là cạnh quay trở lại một nút đang ở đường DFS (**GRAY**). **Nút dùng chung** là đối tượng được tham chiếu từ nhiều slot/đường; khi DFS gặp một nút đã **BLACK**, đó không nhất thiết là chu trình.
- **Dữ liệu bằng nhau không phải identity bằng nhau.** Hai object cùng payload có thể là hai nút hợp lệ; một object xuất hiện ở hai slot là vi phạm sở hữu riêng.
- **DFS ba màu không đệ quy** phát hiện chu trình và chia sẻ, thời gian O(V+E) kỳ vọng, không cạn call stack vì độ sâu đệ quy.
- **BFS bậc vào** đếm mọi cạnh con và chỉ enqueue mỗi nút một lần. Với vùng reachable, bậc vào của gốc 0, của mỗi nút khác 1; đồng thời `E=V-1` trong cây không rỗng.
- **Scope kiểm định quan trọng:** `validate(root)` chỉ thấy vùng reachable. Muốn xác minh toàn registry hoặc forest, cần xét mọi nút/gốc và kiểm tra không có sharing giữa các cây.
- **Chỉ tính cạnh con thật sự:** `parent`, `next`, thread pointer và sentinel cần mô hình riêng; đồ thị vô hướng có quy tắc chu trình khác cạnh cha→con có hướng.
- **Không dùng thuật toán cây khi giả định đã bị phá.** Clone, chiều cao, LCA, serialize, iterator hoặc free kiểu cây có thể sai, lặp mãi hoặc hủy trùng nếu cấu trúc là DAG/graph.
- **Sửa lỗi có chủ đích:** cắt cạnh, clone nhánh hay chuyển sang API DAG/graph phải dựa vào nghiệp vụ và ownership; sau sửa kiểm tra lại toàn bộ bất biến.
- **Bảo vệ vòng đời và đồng bộ:** visited không xác thực con trỏ treo; hash map không làm truy cập đồng thời an toàn. Cần giới hạn đầu vào, xác thực ID, giữ object sống và kiểm định trên một trạng thái nhất quán.

Trước khi cho phép một dữ liệu “giống cây” đi vào thuật toán duyệt hoặc biến đổi, hãy trả lời được ba câu hỏi: **Những liên kết nào là cạnh con thật? Mỗi đối tượng có thể đến được theo bao nhiêu đường từ gốc? Có cạnh nào quay lại một tổ tiên hay không?** Câu trả lời nhất quán ở ba điểm đó là nền tảng để chọn đúng thuật toán cây hoặc đồ thị.
