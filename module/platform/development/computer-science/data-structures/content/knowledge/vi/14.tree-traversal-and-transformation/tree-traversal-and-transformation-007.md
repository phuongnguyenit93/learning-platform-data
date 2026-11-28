# Tìm đường từ gốc và xác định tổ tiên chung

Trong cây tổ chức nhân sự, muốn biết một nhân viên nằm dưới những cấp quản lý nào, ta cần **đường đi từ gốc đến nút**. Muốn biết hai nhân viên có người quản lý chung gần nhất ở cấp nào, ta cần tìm **tổ tiên chung gần nhất** (*Lowest Common Ancestor*, viết tắt **LCA**). Cùng nguyên lý này xuất hiện khi tìm đường dẫn tệp, so sánh hai nút trong cây phân loại, xác định quan hệ giữa hai thành phần giao diện và tính khoảng cách trên cây.

Bài **“Tìm đường từ gốc và xác định tổ tiên chung”** thuộc chương **Duyệt và biến đổi cây** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Module xây dựng nền tảng cấu trúc dữ liệu bằng mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị; trọng tâm của bài là chọn đúng cách lưu đường đi, duy trì bất biến, đánh giá **độ phức tạp thời gian/bộ nhớ** và xác định khi nào nên tiền xử lý để trả lời nhiều truy vấn.

Sau bài học, bạn có thể:

- Phân biệt **đường đi duy nhất trong cây**, **tổ tiên**, **tổ tiên chung** và **LCA**.
- Tìm đường từ gốc bằng DFS có quay lui hoặc BFS có bản đồ cha.
- Tìm LCA bằng hai đường đi, bằng độ sâu/con trỏ cha, hoặc bằng một lần DFS có xác minh **cả hai nút đều tồn tại**.
- Tận dụng thứ tự khóa trong **cây tìm kiếm nhị phân (BST)** và tiền xử lý **binary lifting** khi phải trả lời nhiều truy vấn.
- Dùng LCA để xây đường giữa hai nút và tính khoảng cách; tránh nhầm **giá trị nút** với **danh tính nút**.
- Phân tích chi phí của cây cân bằng/cây lệch, xử lý gốc rỗng, nút vắng mặt, nút là tổ tiên của nút kia và đầu vào không thực sự là cây.

## 1. Định nghĩa: đường đi, tổ tiên và LCA

Xét một **cây có gốc** (*rooted tree*): mỗi nút khác gốc có đúng một cha, không có chu trình, và từ gốc đi tới mỗi nút có **một đường đi duy nhất**.

### 1.1. Cây mẫu

```text
                    8                  độ sâu 0
                 /     \
                3       10             độ sâu 1
              /   \        \
             1     6        14          độ sâu 2
                  / \       /
                 4   7     13           độ sâu 3
```

Ta dùng quy ước **độ sâu `depth(root) = 0`** và độ sâu của nút con bằng độ sâu cha cộng 1. Độ sâu là **số cạnh**, không phải số nút trên đường đi.

| Nút đích | Đường từ gốc (danh sách nút) | Độ sâu |
| --- | --- | --- |
| 8 | `8` | 0 |
| 1 | `8 → 3 → 1` | 2 |
| 4 | `8 → 3 → 6 → 4` | 3 |
| 7 | `8 → 3 → 6 → 7` | 3 |
| 13 | `8 → 10 → 14 → 13` | 3 |

**Đường từ gốc tới nút `u`** là dãy bắt đầu tại gốc, đi theo liên kết cha–con và kết thúc ở `u`. Nếu `u` nằm ở độ sâu `d`, dãy có `d+1` nút và `d` cạnh.

### 1.2. Tổ tiên và tổ tiên chung

Nút `a` là **tổ tiên** của `u` nếu `a` nằm trên đường từ gốc tới `u`. Trong định nghĩa LCA thường dùng, **mỗi nút được coi là tổ tiên của chính nó** (*inclusive ancestor*).

Ví dụ:

- Tổ tiên của 7: `8, 3, 6, 7`.
- Tổ tiên chung của 4 và 7: `8, 3, 6`.
- **LCA(4, 7) = 6** vì 6 là tổ tiên chung có độ sâu lớn nhất.
- **LCA(1, 13) = 8** vì chỉ gốc 8 là tổ tiên chung.
- **LCA(3, 7) = 3** vì 3 là tổ tiên của chính nó và của 7.
- **LCA(7, 7) = 7** nếu nút 7 tồn tại trong cây.

Nói cách khác, **LCA là nút cuối cùng của tiền tố chung** giữa hai đường đi từ cùng gốc.

### 1.3. Điều kiện tồn tại của LCA

Trong bài này, hàm LCA có hợp đồng:

- Trả **nút LCA** khi cả hai nút đích **đều thuộc cây**.
- Trả `None`/`NULL` nếu cây rỗng, một hoặc cả hai nút không thuộc cây.
- Nếu hai đối số chỉ **cùng một nút** và nút đó có mặt trong cây, LCA chính là nút ấy.

Điều kiện “cả hai có mặt” rất quan trọng: có những mã đệ quy phổ biến trả về một nút tìm được ngay cả khi nút đích kia không tồn tại. Chúng chỉ đúng khi **đầu vào bảo đảm cả hai nút hiện diện**, hoặc phải có bước kiểm chứng bổ sung.

### 1.4. Cây tổng quát, cây nhị phân và BST

LCA không đòi hỏi cây nhị phân hay khóa có thứ tự. Nó có nghĩa với **cây có gốc bất kỳ**, kể cả nút có nhiều con.

BST là trường hợp đặc biệt: nếu khóa duy nhất và bất biến **mọi khóa ở cây con trái nhỏ hơn khóa cha, mọi khóa bên phải lớn hơn**, có thể dùng so sánh khóa để tìm LCA nhanh hơn trên cây cân bằng.

Với **đồ thị có hướng có nút nhiều cha**, khái niệm tổ tiên chung có thể không còn cho ra một nút duy nhất theo thứ tự cây; không áp dụng trực tiếp chứng minh của cây mà không xác định định nghĩa thích hợp.

## 2. Danh tính nút khác với giá trị nút

Một cây có thể chứa hai nút **khác nhau** cùng nhãn `5`. Nếu đích là một **đối tượng nút cụ thể**, kiểm tra `node.value == 5` chưa đủ xác định đúng nút đó.

```text
           9
          / \
        (5A) (5B)

Hai nút 5A và 5B có cùng payload 5, nhưng là hai nút riêng.
LCA(5A, 5B) = 9.
```

Với một cây tùy ý, nên tìm theo **danh tính nút** (identity hoặc ID duy nhất), không chỉ theo payload. Nếu đề bài nói “tìm LCA của hai giá trị khóa” thì phải nêu điều kiện **khóa duy nhất** hoặc quy tắc chọn nút khi giá trị lặp.

### 2.1. Kiểu nút Python cho các ví dụ

Các đoạn Python trong bài dùng lớp `Node` và cây mẫu dưới đây. Có thể đặt đoạn này ở đầu tệp rồi lần lượt chạy các hàm của những mục sau.

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(eq=False)
class Node:
    value: int
    left: Node | None = None
    right: Node | None = None


def sample_tree() -> tuple[Node, dict[str, Node]]:
    # Giữ từng đối tượng nút, không tái tạo Node chỉ bằng giá trị.
    nodes = {
        str(v): Node(v)
        for v in (8, 3, 10, 1, 6, 14, 4, 7, 13)
    }

    nodes["8"].left = nodes["3"]
    nodes["8"].right = nodes["10"]
    nodes["3"].left = nodes["1"]
    nodes["3"].right = nodes["6"]
    nodes["6"].left = nodes["4"]
    nodes["6"].right = nodes["7"]
    nodes["10"].right = nodes["14"]
    nodes["14"].left = nodes["13"]

    return nodes["8"], nodes


root, nodes = sample_tree()
```

`eq=False` giúp hai `Node` khác nhau không mặc nhiên được coi là bằng nhau theo nội dung; với cấu hình này đối tượng có thể làm khóa của `dict` theo identity. Trong mã bên dưới, điều kiện `node is target` diễn tả rõ rằng phải khớp **chính đối tượng được hỏi**.

**Giả định xuyên suốt:** đầu vào là cây nhị phân hữu hạn, không có chu trình, không dùng chung một nút con qua nhiều cha, và không bị sửa trong lúc một lượt tìm kiếm đang chạy.

## 3. Tìm đường từ gốc bằng DFS có quay lui

Để tìm đường từ gốc đến một nút đích bất kỳ, có thể đi **DFS (Depth-First Search)** từ gốc:

1. Đưa nút đang xét vào danh sách `path`.
2. Nếu nút chính là đích, giữ đường này và báo thành công.
3. Nếu chưa thấy, tìm trong cây con trái, rồi cây con phải.
4. Nếu cả hai nhánh đều không thấy, **bỏ nút hiện tại khỏi `path`** khi quay lui.

Quy tắc bước 4 là bất biến mấu chốt: không được giữ lại các nút của nhánh tìm kiếm thất bại.

### 3.1. Mã Python đầy đủ

```python
def find_path(root: Node | None, target: Node) -> list[Node] | None:
    """Đường từ root đến đúng đối tượng target, hoặc None nếu vắng."""
    path: list[Node] = []

    def visit(node: Node | None) -> bool:
        if node is None:
            return False

        path.append(node)

        if node is target:
            return True

        if visit(node.left) or visit(node.right):
            return True

        path.pop()  # Nhánh này không chứa target: quay lui.
        return False

    if visit(root):
        return path.copy()  # Đường đã hoàn tất, trả kết quả độc lập.
    return None


root, nodes = sample_tree()

path = find_path(root, nodes["7"])
print([n.value for n in path] if path is not None else None)
# [8, 3, 6, 7]

outside = Node(7)  # Cùng giá trị nhưng là đối tượng khác.
print(find_path(root, outside))  # None
print(find_path(None, nodes["7"]))  # None
```

Hàm trả một danh sách **các nút thật trong cây**, không sao chép sâu các đối tượng nút. Nếu cần chỉ giá trị cho mục đích hiển thị, chuyển bằng `[n.value for n in path]` sau khi xác nhận `path is not None`.

### 3.2. Bất biến của quá trình quay lui

Tại thời điểm bắt đầu xử lý một nút `u`:

- `path` biểu diễn đường hợp lệ từ gốc tới cha của `u`.
- Sau `path.append(u)`, `path` là đường từ gốc tới `u`.
- Nếu tìm thành công ở bất kỳ nhánh con nào, `path` được giữ ở **đường thành công**, không bị pop.
- Nếu thất bại cả hai nhánh, `path.pop()` đưa nó về đúng trạng thái trước khi vào `u`.

Từ bất biến, khi `visit(root)` trả `True`, `path` là đường đúng từ gốc tới đích; nếu trả `False`, mọi nhánh đã thử đều quay lui đúng.

### 3.3. Độ phức tạp

Gọi `n` là số nút, `h` là chiều cao tính theo **số cạnh** từ gốc tới lá sâu nhất.

- **Thời gian:** O(n) trong trường hợp xấu nhất; có thể dừng sớm nếu gặp đích.
- **Bộ nhớ stack đệ quy:** O(h+1), vì đang hoạt động trên tối đa một đường gốc–lá.
- **Danh sách `path`:** O(h+1) nút ở một thời điểm; nếu thành công, bản sao kết quả chứa `depth(target)+1` mục.
- **Tổng bộ nhớ phụ trợ:** O(h+1), không tính cây đầu vào.

Trên cây lệch rất sâu, `h` có thể Θ(n) và đệ quy Python có thể chạm giới hạn độ sâu. Với dữ liệu như vậy, cân nhắc DFS dùng stack tường minh hoặc duyệt theo cha.

### 3.4. Lỗi quay lui phổ biến

```python
# SAI về ý tưởng: quên path.pop() khi nhánh thất bại.
# path.append(node)
# if found_left or found_right:
#     return True
# return False
```

Nếu tìm nhầm sang nhánh trái trước rồi cuối cùng mới thấy đích bên phải, `path` có thể chứa cả nút của những nhánh **không nằm trên đường thật**. Việc xóa đúng một phần tử ở nhánh thất bại là điều kiện bắt buộc, không chỉ là tối ưu bộ nhớ.

## 4. Tìm đường bằng BFS và bảng cha

Một lựa chọn khác là dùng **queue FIFO** để duyệt cây từ gốc, đồng thời ghi `parent[child] = node` cho từng nút phát hiện.

Khi đã tìm được đích, đi từ đích ngược về gốc bằng bảng cha, rồi đảo danh sách.

```text
           root 8
           /    \
          3      10
           \
            6
             \
              7 (target)

Ghi khi phát hiện:
parent[8] = None
parent[3] = 8
parent[10] = 8
parent[6] = 3
parent[7] = 6

Lần ngược: 7 -> 6 -> 3 -> 8
Đảo lại:   8 -> 3 -> 6 -> 7
```

Trong cây, **mọi đường từ gốc tới đích đều là cùng một đường duy nhất**, nên DFS và BFS trả cùng dãy nút, dù thứ tự **khám phá** các nhánh khác nhau.

### 4.1. Xây bảng cha và độ sâu cho cả cây

```python
from collections import deque


def build_parent_depth(
    root: Node | None,
) -> tuple[dict[Node, Node | None], dict[Node, int]]:
    """Chỉ mục cho một cây bất biến; khóa Node theo identity."""
    if root is None:
        return {}, {}

    parent: dict[Node, Node | None] = {root: None}
    depth: dict[Node, int] = {root: 0}
    queue = deque([root])

    while queue:
        node = queue.popleft()

        for child in (node.left, node.right):
            if child is None:
                continue

            # Giả định cây: mỗi nút con có đúng một cha.
            parent[child] = node
            depth[child] = depth[node] + 1
            queue.append(child)

    return parent, depth


def path_from_index(
    target: Node,
    parent: dict[Node, Node | None],
) -> list[Node] | None:
    """Trả đường gốc -> target từ một bảng cha đã xây."""
    if target not in parent:
        return None

    reversed_path: list[Node] = []
    current: Node | None = target

    while current is not None:
        reversed_path.append(current)
        current = parent[current]

    reversed_path.reverse()
    return reversed_path


root, nodes = sample_tree()
parent, depth = build_parent_depth(root)

print([n.value for n in path_from_index(nodes["13"], parent)])
# [8, 10, 14, 13]

print(depth[nodes["13"]])  # 3
print(path_from_index(Node(13), parent))  # None
```

Bảng `parent` dùng chính đối tượng `Node` làm khóa. Do đó, tạo thêm `Node(13)` không làm nó trở thành nút thuộc cây. Nếu hệ thống dùng ID số nguyên duy nhất, có thể thay khóa đối tượng bằng ID và bảo đảm quản lý vòng đời/ID tái sử dụng.

### 4.2. Bất biến của BFS ghi cha

- Gốc có `parent[root] = None` và `depth[root] = 0`.
- Khi enqueue một nút con `v` từ nút cha `u`, ghi `parent[v] = u` và `depth[v] = depth[u]+1`.
- Mọi nút đã ghi vào bảng đều có **một đường cha hợp lệ về gốc**.
- Vì đầu vào là cây, mỗi nút khác gốc chỉ được phát hiện từ đúng một cha; không cần `visited` riêng.

### 4.3. Chi phí và biến thể dừng sớm

Bảng cha và bảng độ sâu cho **toàn cây**:

- O(n) thời gian xây chỉ mục.
- O(n) bộ nhớ cho hai bảng và queue trong trường hợp xấu nhất.
- Sau khi xây, dựng đường tới một nút bất kỳ trong chỉ mục mất O(d+1) thời gian và O(d+1) bộ nhớ kết quả, với `d = depth(target)`.

Nếu chỉ hỏi **một** đích, có thể dừng BFS ngay khi thấy đích và chỉ giữ bảng cha cho các nút đã phát hiện tới thời điểm đó. Tuy nhiên, trong trường hợp xấu nhất vẫn có thể phải thăm O(n) nút và giữ O(n) tham chiếu.

**Đánh đổi:** DFS quay lui tiết kiệm hơn về bộ nhớ trong cây rộng (O(h+1)), trong khi xây bảng cha dùng O(n) bộ nhớ nhưng hữu ích nếu cần truy xuất **nhiều đường đi** hoặc **nhiều LCA** sau đó.

## 5. Cách thứ nhất tìm LCA: so sánh hai đường đi từ gốc

Ý tưởng trực tiếp nhất:

1. Tìm đường `P` từ gốc tới nút `a`.
2. Tìm đường `Q` từ gốc tới nút `b`.
3. Nếu một đường không tồn tại, trả `None`.
4. Duyệt hai đường từ đầu, chừng nào hai nút tương ứng **là cùng đối tượng**.
5. Nút cuối cùng khớp chính là LCA.

### 5.1. Minh họa

```text
P(root -> 4) = [8, 3, 6, 4]
Q(root -> 7) = [8, 3, 6, 7]

Tiền tố chung = [8, 3, 6]
LCA = 6
```

### 5.2. Mã Python

```python
def lca_by_paths(
    root: Node | None,
    a: Node,
    b: Node,
) -> Node | None:
    pa = find_path(root, a)
    pb = find_path(root, b)

    if pa is None or pb is None:
        return None

    common: Node | None = None

    for x, y in zip(pa, pb):
        if x is not y:
            break
        common = x

    return common


root, nodes = sample_tree()

print(lca_by_paths(root, nodes["4"], nodes["7"]).value)  # 6
print(lca_by_paths(root, nodes["1"], nodes["13"]).value) # 8
print(lca_by_paths(root, nodes["3"], nodes["7"]).value)  # 3
print(lca_by_paths(root, nodes["7"], nodes["7"]).value)  # 7
print(lca_by_paths(root, nodes["7"], Node(7)))           # None
```

**Lưu ý:** `lca_by_paths` gọi `find_path` hai lần, nhưng O(n)+O(n)+O(h) vẫn là **O(n)** về bậc thời gian. Bộ nhớ phụ trợ O(h+1) cho ngăn xếp và hai đường, không tính cây đầu vào.

### 5.3. Chứng minh tính đúng đắn

Trong một cây có gốc, đường từ gốc tới nút là **duy nhất**. Mọi tổ tiên của `a` chính là các nút trên đường `P`, và tương tự cho `b`. Một nút là tổ tiên chung khi và chỉ khi nó nằm trên **cả hai đường**.

Hai đường có cùng gốc nên phần giao theo thứ tự gốc–lá là **một tiền tố chung**; sau điểm tách nhánh, chúng không thể hợp lại trong cây thật vì như vậy một nút có hai đường về gốc. Nút cuối của tiền tố chung có độ sâu lớn nhất trong các tổ tiên chung. Theo định nghĩa, đó là LCA.

### 5.4. Khi nào nên chọn cách này?

- Bài học/ứng dụng cần **hiển thị luôn hai đường từ gốc**.
- Mỗi lần chỉ có ít truy vấn, cây không quá lớn.
- Cần xử lý rõ trường hợp nút **không tồn tại** và nút **là tổ tiên của nút kia**.
- Dễ kiểm thử vì có thể so sánh tiền tố hai danh sách.

Nếu cần hàng trăm nghìn truy vấn, việc DFS lại toàn cây cho mỗi cặp có thể quá tốn kém. Khi đó nên xây chỉ mục cha/độ sâu hoặc tiền xử lý tổ tiên nhiều cấp.

## 6. Cách thứ hai: bảng cha và cân bằng độ sâu

Khi đã có `parent` và `depth` từ Mục 4, có thể tìm LCA mà **không cần tạo hai đường đầy đủ**:

1. Kiểm tra cả `a` và `b` có trong chỉ mục.
2. Đưa nút sâu hơn **lên cha** cho đến khi hai nút có cùng độ sâu.
3. Nếu hai nút trùng nhau, đó là LCA.
4. Nếu chưa trùng, cho cả hai đi lên **mỗi bước một cha** đến khi gặp nhau.

### 6.1. Ví dụ

```text
LCA(4, 1)

4: depth=3          1: depth=2
4 -> cha 6 (d=2)    1 (d=2)
6 -> cha 3          1 -> cha 3
                  => LCA = 3
```

### 6.2. Mã Python dùng chỉ mục đã xây

```python
def lca_from_parent(
    a: Node,
    b: Node,
    parent: dict[Node, Node | None],
    depth: dict[Node, int],
) -> Node | None:
    if a not in parent or b not in parent:
        return None

    x, y = a, b

    while depth[x] > depth[y]:
        x = parent[x]  # x chưa thể là root trong nhánh này.

    while depth[y] > depth[x]:
        y = parent[y]

    while x is not y:
        x = parent[x]
        y = parent[y]

    return x


root, nodes = sample_tree()
parent, depth = build_parent_depth(root)

print(lca_from_parent(nodes["4"], nodes["1"], parent, depth).value)
# 3

print(lca_from_parent(nodes["3"], nodes["7"], parent, depth).value)
# 3

print(lca_from_parent(nodes["13"], Node(13), parent, depth))
# None
```

Để code Python có kiểu tĩnh chặt chẽ, các biến leo cha có thể được khai báo `Node | None` và có kiểm tra khi lấy từ bảng. Trong hợp đồng **chỉ mục của một cây hợp lệ**, các bước leo ở vòng thứ nhất và thứ hai không tới `None` khi còn chênh độ sâu; hai nút cùng độ sâu chắc chắn gặp nhau chậm nhất tại gốc.

### 6.3. Bất biến và chi phí

Sau bước cân bằng, hai con trỏ ở **cùng độ sâu**. Mỗi lần dịch đồng thời một cạnh về gốc, tính chất này được giữ. Khi chúng gặp nhau lần đầu, đó là tổ tiên chung sâu nhất: nếu có tổ tiên chung thấp hơn, chúng đã phải trùng sớm hơn.

- Xây bảng cha/độ sâu một lần: **O(n)** thời gian/bộ nhớ.
- Mỗi LCA sau khi có bảng: **O(h+1)** thời gian xấu nhất, **O(1)** bộ nhớ phụ.
- Nếu chỉ cần LCA duy nhất và không có chỉ mục sẵn, xây bảng O(n) có thể tốn bộ nhớ hơn so với tìm bằng DFS.
- Nếu có nhiều truy vấn, tái dùng bảng giúp tránh quét toàn cây cho từng cặp.

Nếu mỗi nút đã chứa **con trỏ cha `parent` và trường `depth`**, có thể dùng cùng thuật toán mà không phải xây thêm hai bảng độc lập, miễn là các trường được duy trì đúng sau mỗi thao tác thay đổi cây.

## 7. Cách thứ ba: DFS một lượt để tìm LCA và kiểm tra cả hai đích

Trong cây nhị phân không có khóa sắp xếp, một thuật toán đệ quy thường gặp là:

```text
LCA(node, a, b):
    nếu node null: trả null
    nếu node == a hoặc node == b: trả node
    left = LCA(node.left, a, b)
    right = LCA(node.right, a, b)
    nếu left và right đều có: trả node
    nếu không: trả left hoặc right
```

Mẫu trên **chỉ an toàn về ngữ nghĩa LCA nếu đã biết cả hai nút tồn tại**, vì một nhánh chỉ tìm thấy `a` cũng có thể trả `a` dù `b` hoàn toàn vắng mặt. Với bài học có yêu cầu phân biệt nút vắng, ta nên **đếm số đích đã tìm thấy**.

### 7.1. Hàm một lượt trả cả số đích tìm thấy và nút LCA

```python
def lca_verified(
    root: Node | None,
    a: Node,
    b: Node,
) -> Node | None:
    """Trả LCA khi CẢ HAI đối tượng nằm trong cây, nếu không None."""

    if a is b:
        # Hai đích cùng đối tượng: chỉ cần kiểm tra nó có thuộc cây.
        return a if find_path(root, a) is not None else None

    def scan(node: Node | None) -> tuple[int, Node | None]:
        if node is None:
            return 0, None

        left_count, left_lca = scan(node.left)
        right_count, right_lca = scan(node.right)

        # Một cây con đã chứa cả hai đích thì LCA nằm trong cây con ấy.
        if left_lca is not None:
            return 2, left_lca
        if right_lca is not None:
            return 2, right_lca

        count = (
            left_count
            + right_count
            + int(node is a)
            + int(node is b)
        )

        if count == 2:
            return 2, node

        return count, None

    found, ancestor = scan(root)
    return ancestor if found == 2 else None


root, nodes = sample_tree()

print(lca_verified(root, nodes["4"], nodes["7"]).value)   # 6
print(lca_verified(root, nodes["1"], nodes["13"]).value)  # 8
print(lca_verified(root, nodes["3"], nodes["7"]).value)   # 3
print(lca_verified(root, nodes["7"], nodes["7"]).value)   # 7

print(lca_verified(root, nodes["7"], Node(7)))  # None
print(lca_verified(None, nodes["4"], nodes["7"]))  # None
```

Mỗi lần `scan` trả cặp:

- `count` là số đích **khác nhau** trong cây con, tối đa 2.
- `ancestor` là LCA của hai đích khi `count == 2`; nếu chưa tìm đủ, là `None`.

Trường hợp `a is b` được xử lý riêng để không nhầm một nút duy nhất thành **hai đích khác nhau** khi cộng các điều kiện.

### 7.2. Vì sao thuật toán đúng?

Giả sử đang ở nút `u`:

- Nếu cả hai đích nằm trong **cùng cây con trái**, LCA nằm trong trái và kết quả được truyền lên; tương tự với phải.
- Nếu một đích ở cây con trái và một ở cây con phải, **`u` là điểm hợp nhánh đầu tiên** khi đi từ dưới lên, nên là LCA.
- Nếu `u` chính là một đích và đích còn lại nằm trong một cây con của `u`, **`u` là tổ tiên của cả hai**, nên là LCA.
- Nếu chỉ thấy một đích trong toàn cây, kết quả cuối cùng trả `None` thay vì báo sai một nút đơn lẻ.

Do cây có gốc hữu hạn và hai đích khác nhau xuất hiện mỗi nút nhiều nhất một lần, `count` không vượt 2 dưới giả định đầu vào đúng nghĩa cây.

### 7.3. Chi phí và giới hạn

- Một lượt hậu tự thăm từng nút: **O(n)** thời gian, cả khi không thấy đích.
- Bộ nhớ stack đệ quy: **O(h+1)**.
- Không cần xây danh sách đường đi hoặc bảng cha O(n).
- Trong ví dụ, phép tìm cho `a is b` dùng DFS tìm đường O(n) xấu nhất và O(h+1) bộ nhớ, vẫn cùng bậc.
- Trên cây quá sâu, cần cân nhắc phiên bản lặp để tránh giới hạn đệ quy.

**Khác biệt về mục tiêu:** cách hai đường đi cung cấp luôn đường gốc–đích; cách DFS một lượt tập trung trả **một tổ tiên chung**, không tự cho ra hai đường đầy đủ.


## 8. LCA trong cây tìm kiếm nhị phân: tận dụng quan hệ thứ tự

Với **BST có khóa duy nhất**, bất biến tại mỗi nút `u` là:

- Mọi khóa trong cây con trái **nhỏ hơn** `u.key`.
- Mọi khóa trong cây con phải **lớn hơn** `u.key`.
- Hai cây con tiếp tục tuân thủ cùng quy tắc.

Nếu hai khóa mục tiêu `a` và `b` đều thuộc BST:

1. Nếu **cả hai nhỏ hơn** khóa nút đang xét, LCA nằm trong cây con trái.
2. Nếu **cả hai lớn hơn**, LCA nằm trong cây con phải.
3. Nếu hai khóa nằm **khác phía**, hoặc một khóa **bằng khóa nút hiện tại**, nút hiện tại là LCA.

```text
                   8
                  / \
                 3   10
                / \    \
               1   6    14
                  / \   /
                 4   7 13

Hỏi LCA(4, 7):
  Tại 8: cả hai khóa < 8 -> xuống trái (3).
  Tại 3: cả hai khóa > 3 -> xuống phải (6).
  Tại 6: 4 < 6 < 7 -> LCA = 6.
```

### 8.1. Kiểm tra sự tồn tại trước khi trả LCA

Một lỗi là dừng tại “nơi tách nhánh” **nhưng không kiểm tra hai khóa thực sự có trong cây**. Ví dụ `LCA(4, 100)` có thể trả một nút dù khóa 100 không tồn tại.

Hàm dưới đây chủ động kiểm tra hai khóa bằng tìm kiếm BST, sau đó mới tìm vị trí tách nhánh:

```python
def bst_find(root: Node | None, key: int) -> Node | None:
    node = root

    while node is not None:
        if key == node.value:
            return node
        if key < node.value:
            node = node.left
        else:
            node = node.right

    return None


def bst_lca(
    root: Node | None,
    key_a: int,
    key_b: int,
) -> Node | None:
    """Chỉ dùng cho BST có khóa duy nhất và bất biến đúng."""
    if bst_find(root, key_a) is None:
        return None
    if bst_find(root, key_b) is None:
        return None

    low, high = sorted((key_a, key_b))
    node = root

    while node is not None:
        if high < node.value:
            node = node.left
        elif low > node.value:
            node = node.right
        else:
            return node

    return None


root, nodes = sample_tree()  # Cây mẫu cũng là BST.

print(bst_lca(root, 4, 7).value)  # 6
print(bst_lca(root, 3, 7).value)  # 3
print(bst_lca(root, 1, 13).value) # 8
print(bst_lca(root, 4, 100))      # None
```

### 8.2. Độ phức tạp và điều kiện sử dụng

Mỗi phép tìm kiếm hoặc di chuyển từ gốc xuống một nhánh đi qua tối đa `h+1` nút:

- **Thời gian:** O(h+1), gồm hai lần xác minh khóa và một lần tìm LCA; hệ số hằng không đổi bậc.
- **Bộ nhớ phụ trợ:** O(1) cho phiên bản lặp, không tính đầu vào.
- **BST cân bằng:** `h = O(log n)` nên O(log n) thời gian.
- **BST lệch:** `h = O(n)`, có thể mất O(n).

Nếu cây **không phải BST**, hoặc khóa trùng mà không có quy tắc riêng, không được dùng cách rẽ trái/phải bằng so sánh khóa. Trong cây tổng quát hãy dùng **identity của nút** và thuật toán LCA bất kỳ ở các mục trước.

## 9. Truy vấn LCA nhiều lần: binary lifting

Nếu có một cây gần như không thay đổi và `q` truy vấn LCA, duyệt lại O(n) cho từng cặp có thể tốn O(qn). **Binary lifting** tiền xử lý các tổ tiên ở khoảng cách lũy thừa của 2, giúp nhảy nhiều tầng trong một bước.

### 9.1. Ý tưởng bảng `up[k][v]`

Đánh số mỗi nút từ 0 đến `n-1` và lưu:

```text
up[0][v] = cha trực tiếp của v           (2^0 = 1 cạnh)
up[1][v] = tổ tiên cách v 2 cạnh         (2^1 = 2 cạnh)
up[2][v] = tổ tiên cách v 4 cạnh         (2^2 = 4 cạnh)
up[3][v] = tổ tiên cách v 8 cạnh         (2^3 = 8 cạnh)
...
```

Nếu không tồn tại tổ tiên ở khoảng cách đó, lưu một sentinel `-1` (và bảo đảm ID nút hợp lệ là số không âm).

Công thức:

\[
up[k][v] = up[k-1][up[k-1][v]]
\]

chỉ khi `up[k-1][v]` tồn tại; nếu không, kết quả là `-1`. Công thức đúng vì đi lên `2^{k-1}` cạnh **hai lần** tương đương đi lên `2^k` cạnh.

### 9.2. Dùng nhảy bit để nâng độ sâu

Giả sử cần nâng nút `u` lên 13 cạnh. Vì `13 = 8 + 4 + 1`, ta chỉ cần tối đa ba lần nhảy:

```text
u --2^3=8--> ... --2^2=4--> ... --2^0=1--> tổ tiên cần đến
```

Sau khi hai nút về cùng độ sâu:

- Nếu trùng nhau, đó là LCA.
- Nếu khác nhau, xét `k` từ lớn về nhỏ.
- Khi `up[k][u]` và `up[k][v]` **khác nhau**, nâng cả hai lên khoảng cách `2^k` mà không vượt quá LCA.
- Cuối cùng, cha trực tiếp của hai vị trí là LCA.

### 9.3. Python: chỉ mục binary lifting dùng danh tính nút

```python
from collections import deque


class BinaryLifting:
    """LCA cho một cây nhị phân có gốc và không thay đổi."""

    def __init__(self, root: Node | None):
        self.nodes: list[Node] = []
        self.index: dict[Node, int] = {}
        self.depth: list[int] = []
        self.up: list[list[int]] = []

        if root is None:
            return

        parent_idx: list[int] = []
        queue = deque([(root, -1, 0)])

        # BFS để gán ID, cha và độ sâu.
        while queue:
            node, p, d = queue.popleft()
            i = len(self.nodes)

            self.nodes.append(node)
            self.index[node] = i
            self.depth.append(d)
            parent_idx.append(p)

            if node.left is not None:
                queue.append((node.left, i, d + 1))
            if node.right is not None:
                queue.append((node.right, i, d + 1))

        n = len(self.nodes)
        levels = n.bit_length()
        self.up.append(parent_idx)  # up[0][v] = cha trực tiếp.

        for _ in range(1, levels):
            previous = self.up[-1]
            layer = [
                -1 if previous[v] == -1
                else previous[previous[v]]
                for v in range(n)
            ]
            self.up.append(layer)

    def lca(self, a: Node, b: Node) -> Node | None:
        if a not in self.index or b not in self.index:
            return None

        u = self.index[a]
        v = self.index[b]

        if self.depth[u] < self.depth[v]:
            u, v = v, u

        # Nâng u đến cùng độ sâu với v.
        difference = self.depth[u] - self.depth[v]
        k = 0

        while difference:
            if difference & 1:
                u = self.up[k][u]
            difference >>= 1
            k += 1

        if u == v:
            return self.nodes[u]

        # Đi từ các bước nhảy lớn tới nhỏ.
        for k in range(len(self.up) - 1, -1, -1):
            ancestor_u = self.up[k][u]
            ancestor_v = self.up[k][v]

            if ancestor_u != ancestor_v:
                u = ancestor_u
                v = ancestor_v

        # Sau vòng, u và v là hai nhánh dưới LCA.
        return self.nodes[self.up[0][u]]


root, nodes = sample_tree()
index = BinaryLifting(root)

print(index.lca(nodes["4"], nodes["7"]).value)    # 6
print(index.lca(nodes["1"], nodes["13"]).value)   # 8
print(index.lca(nodes["3"], nodes["7"]).value)    # 3
print(index.lca(nodes["7"], nodes["7"]).value)    # 7
print(index.lca(nodes["7"], Node(7)))             # None
```

Bộ chỉ mục gán **ID nội bộ cho mỗi đối tượng Node** rồi dùng `-1` cho vị trí tổ tiên không tồn tại. Nó không dựa vào sự duy nhất của `value`.

**Giả định then chốt:** đây là cây có gốc **không thay đổi cấu trúc** sau khi xây chỉ mục. Nếu thay cha, thêm/xóa nút hoặc thay gốc, các bảng `up`/`depth`/`index` có thể không còn phản ánh cây hiện tại.

### 9.4. Phân tích chi phí

Đặt `L = ⌈log₂(n+1)⌉` ở bậc tiệm cận:

- BFS gán ID, cha và độ sâu: **O(n)** thời gian và bộ nhớ.
- Xây `L` tầng tổ tiên: **O(n log n)** thời gian và **O(n log n)** ô bảng.
- Một truy vấn `lca(a,b)`: **O(log n)** lần xét bit và nâng, O(1) bộ nhớ phụ cho các biến cục bộ.
- Với `q` truy vấn trên cây tĩnh: **O(n log n + q log n)** tổng thời gian, không tính xuất kết quả.

Độ phức tạp truy vấn **không phụ thuộc cây có cân bằng hay không** như tìm trên BST. Đổi lại, chi phí tiền xử lý và bộ nhớ bảng có thể cao hơn đáng kể so với chỉ lưu cha/độ sâu O(n).

### 9.5. Kiểm tra tính đúng đắn của thuật toán nhảy

Sau khi cân bằng độ sâu, `u` và `v` ở cùng tầng. Nếu chúng khác nhau, LCA là một tổ tiên **chung** phía trên cả hai.

Khi nhảy ở mức `k`, chỉ nhảy nếu hai tổ tiên mức đó **khác nhau**: như vậy ta không vượt qua tổ tiên chung gần nhất. Duyệt các mức từ lớn tới nhỏ khiến hai vị trí tiến sát tới hai nhánh trực tiếp dưới LCA. Cuối cùng `up[0][u]` là LCA.

Trong một cây hợp lệ, hai nhánh sau khi cân bằng không thể đi lên mãi mà không gặp cùng gốc; ở điểm kết thúc, cha trả về là một ID hợp lệ, không phải `-1`.

### 9.6. Nếu cây thường xuyên thay đổi thì sao?

Binary lifting trong ví dụ là **chỉ mục cho cây tĩnh**. Sau khi chèn/xóa/chuyển cây con, chỉ sửa vài ô `parent` có thể chưa đủ: `depth` và nhiều tổ tiên `2^k` của cả cây con liên quan cũng thay đổi.

Một lựa chọn đơn giản là **xây lại chỉ mục** khi cây đổi, thích hợp khi cập nhật hiếm. Với cập nhật thường xuyên và nhiều truy vấn, cần cấu trúc dữ liệu động chuyên biệt hoặc chiến lược phiên bản hóa; không nên giả định binary lifting tĩnh vẫn đúng.

## 10. Euler tour và truy vấn khoảng tối thiểu: hướng nâng cao

Một kỹ thuật LCA khác biến bài toán cây thành một **truy vấn trên mảng** (*Range Minimum Query*, RMQ).

### 10.1. Duyệt Euler giữ độ sâu mỗi lần ghé thăm

Trong DFS Euler tour từ gốc, ghi nút mỗi lần vào hoặc quay lại từ một cây con; với cây `n >= 1` nút có thể thu được dãy dài `2n-1`, trong đó một nút có thể xuất hiện nhiều lần.

Ghi kèm:

- `euler[i]`: nút ở vị trí i trong tour.
- `tour_depth[i]`: độ sâu của nút ấy.
- `first[u]`: vị trí **xuất hiện đầu tiên** của nút `u`.

Với hai nút `a` và `b`, đặt `i = first[a]`, `j = first[b]`, giả sử `i <= j`. **Nút có độ sâu nhỏ nhất trên đoạn Euler từ i tới j** là LCA của a và b.

Ví dụ cây đơn giản:

```text
       A (0)
      / \
     B(1) C(1)

Euler nodes:  A, B, A, C, A
Depth:        0, 1, 0, 1, 0
first[B] = 1, first[C] = 3

Min depth trên đoạn [1..3] là A (depth 0)
=> LCA(B,C) = A
```

### 10.2. Vì sao RMQ giúp được?

Euler tour biểu diễn một đường đi DFS bao gồm cả lúc quay từ nhánh này lên tổ tiên để chuyển sang nhánh khác. Giữa lần xuất hiện đầu của `a` và `b`, độ sâu nhỏ nhất tương ứng với tổ tiên chung gần nhất mà traversal phải quay tới để nối hai vị trí.

Nếu dùng **sparse table** trên mảng Euler để trả chỉ số có độ sâu nhỏ nhất:

- Tạo Euler tour: O(n) thời gian/bộ nhớ.
- Tiền xử lý RMQ sparse table: thường **O(n log n)** thời gian/bộ nhớ.
- Một truy vấn RMQ trên đoạn: **O(1)** theo mô hình sparse table cho phép lấy min của hai đoạn chồng lấn; suy ra LCA O(1) sau tiền xử lý.

Nếu dùng **segment tree** RMQ, xây O(n), trả RMQ O(log n) và bộ nhớ O(n). Mỗi lựa chọn có độ phức tạp, hằng số thời gian và độ khó cài đặt khác nhau.

**Lưu ý:** Euler tour trong phần này là **dãy phục vụ truy vấn LCA**, không phải kết quả duyệt inorder hay preorder chỉ liệt kê mỗi nút một lần.

## 11. Tìm đường giữa hai nút thông qua LCA

Trong cây vô hướng xét theo các cạnh cha–con, giữa hai nút `a` và `b` có **một đường đi đơn duy nhất**:

```text
a -> ... -> LCA(a,b) -> ... -> b
```

Ví dụ trong cây mẫu:

```text
Đường từ 4 tới 13:
4 -> 6 -> 3 -> 8 -> 10 -> 14 -> 13

LCA(4,13) = 8
```

### 11.1. Dựng đường giữa hai nút bằng hai đường gốc

Giả sử:

```text
Pa = [root, ..., LCA, ..., a]
Pb = [root, ..., LCA, ..., b]

Pa[:k] = Pb[:k] là tiền tố chung dài k
Pa[k-1] = Pb[k-1] = LCA
```

Đường từ `a` tới `b` là:

```text
reverse(Pa[k-1:]) + Pb[k:]
```

Trong đó lát cắt đầu chứa LCA đúng một lần, còn lát cắt sau **bỏ LCA** để không lặp.

### 11.2. Mã Python

```python
def path_between(
    a: Node,
    b: Node,
    parent: dict[Node, Node | None],
) -> list[Node] | None:
    pa = path_from_index(a, parent)
    pb = path_from_index(b, parent)

    if pa is None or pb is None:
        return None

    k = 0

    while k < min(len(pa), len(pb)) and pa[k] is pb[k]:
        k += 1

    # Cả hai nút thuộc cùng một cây trong index nên k >= 1.
    return list(reversed(pa[k - 1:])) + pb[k:]


root, nodes = sample_tree()
parent, depth = build_parent_depth(root)

path = path_between(nodes["4"], nodes["13"], parent)
print([n.value for n in path] if path is not None else None)
# [4, 6, 3, 8, 10, 14, 13]

same = path_between(nodes["7"], nodes["7"], parent)
print([n.value for n in same])  # [7]
```

Nếu `a` là tổ tiên của `b`, đoạn từ `a` lên LCA có độ dài một nút, nên kết quả đúng `a → ... → b`. Cách tạo đường dùng O(da+db) thời gian/bộ nhớ theo độ sâu, kể cả chi phí dựng hai đường từ bảng cha.

### 11.3. Khoảng cách bằng số cạnh

Nếu hai nút có độ sâu `d_a` và `d_b`, với LCA có độ sâu `d_l`, số cạnh trên đường duy nhất là:

\[
dist(a,b)=d_a+d_b-2d_l
\]

Lý do: từ `a` đi lên LCA mất `d_a-d_l` cạnh; từ LCA xuống `b` mất `d_b-d_l` cạnh. Tổng hai đoạn tạo công thức trên.

```python
def distance_edges(
    a: Node,
    b: Node,
    depth: dict[Node, int],
    ancestor: Node | None,
) -> int | None:
    if ancestor is None or a not in depth or b not in depth:
        return None

    return depth[a] + depth[b] - 2 * depth[ancestor]


root, nodes = sample_tree()
parent, depth = build_parent_depth(root)
ancestor = lca_from_parent(nodes["4"], nodes["13"], parent, depth)

print(distance_edges(nodes["4"], nodes["13"], depth, ancestor))  # 6
```

Một trường hợp đặc biệt:

- `dist(a,a) = 0`.
- Nếu `a` là tổ tiên của `b`, `dist(a,b) = depth[b]-depth[a]`.
- Nếu hai nút không cùng cây/cùng chỉ mục hợp lệ, không được tính công thức mà không xác minh LCA.

### 11.4. Nếu cạnh có trọng số

Trên một **cây**, đường giữa hai nút vẫn duy nhất dù cạnh có trọng số. Nếu `prefix[u]` là tổng trọng số từ gốc tới `u`, thì:

\[
weight(a,b)=prefix[a]+prefix[b]-2prefix[LCA(a,b)]
\]

Công thức là cộng/trừ trên các đoạn đường gốc; nó không tự yêu cầu dùng Dijkstra vì cây chỉ có một đường đơn giữa hai nút. Nhưng phải xử lý kiểu số và khả năng tràn số cho tổng trọng số, đồng thời xác định trọng số mỗi cạnh theo hợp đồng.

## 12. So sánh các phương án và cách chọn

| Phương pháp | Điều kiện | Chuẩn bị | Một truy vấn LCA | Bộ nhớ thêm | Phù hợp khi |
| --- | --- | --- | --- | --- | --- |
| Hai đường DFS | Cây bất kỳ | Không | O(n) | O(h+1) | Ít truy vấn, cần đường đi |
| DFS một lượt có đếm đích | Cây bất kỳ | Không | O(n) | O(h+1) | Ít truy vấn, cần đúng LCA |
| Bảng cha + độ sâu | Cây bất kỳ, tĩnh | O(n) | O(h+1) | O(n) | Nhiều truy vấn vừa phải; cần đường |
| Con trỏ cha + depth có sẵn | Cây có metadata chính xác | Không (nếu có sẵn) | O(h+1) | O(1) mỗi truy vấn | Node tự lưu cha và độ sâu |
| Dùng thứ tự BST | BST khóa duy nhất | Không | O(h+1) | O(1) | Cây tìm kiếm; nút xác định bằng khóa |
| Binary lifting | Cây có gốc tĩnh | O(n log n) | O(log n) | O(n log n) | Rất nhiều truy vấn |
| Euler tour + sparse table | Cây tĩnh | O(n log n) | O(1) | O(n log n) | Nhiều truy vấn và muốn truy vấn nhanh |

`n` là số nút, `h` là chiều cao, các độ phức tạp không tính chi phí đọc/hiển thị một đường kết quả có O(h+1) nút. **Ngay cả khi LCA truy vấn O(1), xuất một đường dài d cạnh vẫn cần Ω(d+1) công việc** để ghi đủ các nút.

### 12.1. Tổng chi phí khi có nhiều truy vấn

Với `q` cặp nút trên cùng cây tĩnh:

- Tìm bằng DFS độc lập mỗi lần: **O(qn)**.
- Bảng cha/độ sâu: **O(n + qh)**.
- Binary lifting: **O(n log n + q log n)**.
- Euler tour + RMQ sparse table: **O(n log n + q)**.

Đừng mặc định kỹ thuật tiền xử lý phức tạp luôn tốt hơn: với `q` rất nhỏ, chi phí xây bảng và bộ nhớ có thể lớn hơn thời gian giải một vài DFS trực tiếp.

### 12.2. Cây lệch và cây cân bằng

- Cây cân bằng có `h = O(log n)`: bước leo cha hoặc BST LCA có thể đạt O(log n).
- Cây lệch có `h = Θ(n)`: leo cha và đường DFS có thể dài tuyến tính; Python đệ quy dễ đụng giới hạn stack.
- Binary lifting vẫn trả LCA trong O(log n) trên cây tĩnh lệch, đổi lại chi phí bảng O(n log n).
- Nếu dữ liệu thay đổi sau tiền xử lý, mọi kết luận dựa trên bảng chỉ đúng khi metadata được cập nhật hoặc xây lại nhất quán.

`w` (độ rộng tầng lớn nhất) quan trọng với queue BFS; DFS theo đường gốc dùng stack theo chiều cao. Việc chọn BFS hay DFS để tìm **một đường đơn** nên cân nhắc hình dạng cây và bộ nhớ đang có.


## 13. C: tìm đường và LCA bằng mảng con trỏ nút

Python thuận tiện cho danh sách động và bảng băm. Trong C, ta cần quyết định rõ **bộ nhớ lưu đường**, **dung lượng**, **danh tính nút** và **trạng thái lỗi**.

Ví dụ dưới dùng một mảng con trỏ có dung lượng cố định làm vùng lưu đường. Các nút cây nằm ở biến cục bộ của `main`, không được `free`. Hàm tìm đường chỉ lưu **con trỏ mượn** tới nút, không sở hữu và không hủy cây.

### 13.1. Phân biệt không thấy đích và không đủ chỗ lưu đường

Nếu chỉ trả `false` khi không tìm thấy, một hàm có buffer quá nhỏ dễ đánh đồng hai trạng thái:

- **NOT_FOUND:** đã duyệt đủ cây theo hợp đồng và đích không thuộc cây.
- **TOO_DEEP:** trong quá trình tìm gặp đường cần lưu dài hơn dung lượng mảng, nên chưa thể kết luận đích không có.

Cần phân biệt hai trạng thái bằng một `enum`. Nếu gặp đường quá sâu trước khi tới nhánh chứa đích, ví dụ này trả `TOO_DEEP` ngay; đó là lựa chọn **an toàn về dung lượng**, không tuyên bố mọi nút khác đã được tìm hết.

### 13.2. Chương trình C độc lập

```c
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct Node {
    int value;
    const struct Node *left;
    const struct Node *right;
} Node;

typedef enum PathStatus {
    PATH_NOT_FOUND,
    PATH_FOUND,
    PATH_TOO_DEEP
} PathStatus;

typedef struct Path {
    const Node **nodes;   /* Vùng do caller cung cấp, không sở hữu Node. */
    size_t length;
    size_t capacity;
} Path;

/* Tìm root -> target bằng identity (địa chỉ nút). */
static PathStatus dfs_path(
    const Node *node,
    const Node *target,
    Path *out
) {
    if (node == NULL) {
        return PATH_NOT_FOUND;
    }

    if (out->length == out->capacity) {
        return PATH_TOO_DEEP; /* Không ghi ngoài mảng. */
    }

    out->nodes[out->length++] = node;

    if (node == target) {
        return PATH_FOUND;
    }

    PathStatus left = dfs_path(node->left, target, out);
    if (left != PATH_NOT_FOUND) {
        return left; /* Tìm thấy hoặc chưa đủ capacity. */
    }

    PathStatus right = dfs_path(node->right, target, out);
    if (right != PATH_NOT_FOUND) {
        return right;
    }

    --out->length; /* Quay lui nếu không tìm thấy ở cây con này. */
    return PATH_NOT_FOUND;
}

static PathStatus find_path(
    const Node *root,
    const Node *target,
    Path *out
) {
    out->length = 0;
    return dfs_path(root, target, out);
}

/* Trả NULL nếu hai đường không có tiền tố chung. */
static const Node *lca_from_paths(const Path *a, const Path *b) {
    size_t common = 0;
    size_t limit = (a->length < b->length) ? a->length : b->length;

    while (common < limit &&
           a->nodes[common] == b->nodes[common]) {
        ++common;
    }

    return (common == 0) ? NULL : a->nodes[common - 1];
}

static void print_path(const Path *path) {
    for (size_t i = 0; i < path->length; ++i) {
        if (i > 0) printf(" -> ");
        printf("%d", path->nodes[i]->value);
    }
    puts("");
}

int main(void) {
    Node n4  = {4, NULL, NULL};
    Node n7  = {7, NULL, NULL};
    Node n1  = {1, NULL, NULL};
    Node n13 = {13, NULL, NULL};
    Node n6  = {6, &n4, &n7};
    Node n3  = {3, &n1, &n6};
    Node n14 = {14, &n13, NULL};
    Node n10 = {10, NULL, &n14};
    Node n8  = {8, &n3, &n10};

    enum { CAPACITY = 16 };
    const Node *buffer_a[CAPACITY];
    const Node *buffer_b[CAPACITY];

    Path path_a = {buffer_a, 0, CAPACITY};
    Path path_b = {buffer_b, 0, CAPACITY};

    PathStatus sa = find_path(&n8, &n4, &path_a);
    PathStatus sb = find_path(&n8, &n7, &path_b);

    if (sa == PATH_TOO_DEEP || sb == PATH_TOO_DEEP) {
        fputs("Duong tim kiem qua sau cho buffer\n", stderr);
        return EXIT_FAILURE;
    }

    if (sa != PATH_FOUND || sb != PATH_FOUND) {
        puts("Mot trong hai nut khong thuoc cay");
        return EXIT_SUCCESS;
    }

    printf("Duong toi 4: ");
    print_path(&path_a);       /* 8 -> 3 -> 6 -> 4 */

    printf("Duong toi 7: ");
    print_path(&path_b);       /* 8 -> 3 -> 6 -> 7 */

    const Node *ancestor = lca_from_paths(&path_a, &path_b);
    if (ancestor != NULL) {
        printf("LCA = %d\n", ancestor->value); /* 6 */
    }

    return EXIT_SUCCESS;
}
```

### 13.3. Bất biến và chi phí của ví dụ C

Ở mỗi lần vào `dfs_path(node)`, `out->nodes[0..length-1]` là đường hợp lệ từ gốc tới cha của `node`. Sau khi đẩy nút, vùng đó biểu diễn đường tới chính nút đang xét. Khi thất bại, hàm bỏ nút cuối để nhánh khác bắt đầu từ đúng tiền tố chung.

- **Không vượt mảng:** kiểm tra `length == capacity` trước khi ghi.
- **Không `free` cây:** hàm chỉ mượn địa chỉ của các biến `Node` còn sống trong `main`.
- **Không nhầm nút cùng giá trị:** so sánh `node == target`, không so sánh `node->value`.
- **Không trả LCA nếu thiếu đích:** `main` kiểm tra cả hai `PathStatus == PATH_FOUND` rồi mới so sánh đường.
- **Không trả nhầm khi quá sâu:** báo `PATH_TOO_DEEP` riêng thay vì quy thành `PATH_NOT_FOUND`.

Với cây có `n` nút và chiều cao `h`, tìm một đường tốn O(n) thời gian xấu nhất, O(h+1) stack đệ quy, vùng lưu đường O(h+1) nếu cấp đủ. Khi đường dài hơn `CAPACITY`, ví dụ dừng với trạng thái lỗi; sản phẩm có thể dùng **mảng động tăng dung lượng** hoặc DFS không đệ quy để hỗ trợ cây sâu.

## 14. Biến đổi cây và sự hợp lệ của đường/LCA đã lưu

Một đường hoặc bảng tổ tiên được tính cho **một trạng thái cây**. Nếu cấu trúc đổi, kết quả cũ có thể trở nên sai.

### 14.1. Chèn hoặc xóa nút

Ví dụ `path = [8,3,6,7]` hợp lệ ở thời điểm t1. Đến t2, ta chuyển nút 7 sang làm con của 10. Đường cũ vẫn là một danh sách đối tượng có thể còn sống, nhưng **không còn là đường từ gốc tới 7 trong cây hiện tại**.

Nếu một nút trong đường bị giải phóng, C/C++ có thể gặp **con trỏ treo** khi sử dụng danh sách con trỏ đã lưu. Trong Python có GC, list có thể giữ nút bị tách khỏi cây sống lâu hơn nhu cầu nghiệp vụ; khi đó lỗi là **ngữ nghĩa cây hoặc giữ tham chiếu**, không nhất thiết là use-after-free.

### 14.2. Quay cây cân bằng (rotation)

Một phép quay trên BST/AVL/red-black tree có thể giữ **thứ tự inorder các khóa** và không thay đối tượng nút, nhưng nó có thể thay:

- Quan hệ cha–con.
- Độ sâu của một số nút.
- Đường từ gốc tới một nút.
- LCA của một số cặp nút khi xét cấu trúc cây vừa đổi.

Do đó `parent`, `depth`, `up` và Euler tour được xây **trước khi quay** có thể không hợp lệ cho truy vấn sau quay. Đừng nhầm **thứ tự khóa BST không đổi** với **đường đi/LCA không đổi**.

### 14.3. Chính sách cập nhật chỉ mục

Một số lựa chọn:

1. **Cây bất biến trong thời gian truy vấn:** đơn giản nhất để dùng binary lifting hay Euler tour.
2. **Đánh phiên bản:** lưu `tree_version` khi xây chỉ mục; nếu cây đổi thì từ chối truy vấn hoặc xây lại.
3. **Cập nhật metadata cục bộ/toàn bộ:** tự duy trì `parent` và `depth` theo phép sửa; phải chứng minh các bảng tổ tiên cao hơn cũng đúng.
4. **Persistent tree:** mỗi phiên bản có đường liên kết riêng; chỉ mục gắn với đúng phiên bản và những nút cần thiết được giữ sống.
5. **Cấu trúc cây động:** dùng thuật toán/cấu trúc chuyên biệt nếu cần nhiều thay đổi và nhiều truy vấn xen kẽ.

**Version không tự giải quyết đồng bộ:** nếu luồng khác sửa cây sau khi ta kiểm tra version nhưng trước khi đọc liên kết, kết quả có thể sai hoặc gặp data race. Cần khóa, snapshot nhất quán hoặc API concurrent được thiết kế riêng.

### 14.4. Quyền sở hữu và con trỏ cha

Khi mỗi nút giữ `parent`:

- Liên kết cha thường là **tham chiếu không sở hữu** nếu nút cha/đối tượng tree quản lý vòng đời.
- Nếu dùng `shared_ptr` mạnh theo cả hai chiều cha–con, có thể tạo **chu trình sở hữu** làm các nút không được giải phóng như mong đợi.
- Khi tách/gắn một cây con, phải cập nhật con trỏ cha đúng trước khi thuật toán path/LCA tiếp tục.
- Nếu node ID có thể bị tái sử dụng trong một pool, nên có cơ chế nhận biết handle cũ (ví dụ index + generation) để không tra nhầm đối tượng.

## 15. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Tìm nút bằng `value` khi có nhãn trùng | Tìm nhầm đối tượng | Dùng ID/danh tính nút hoặc hợp đồng khóa duy nhất |
| DFS quên `path.pop()` khi thất bại | Đường chứa nút ngoài nhánh đúng | Giữ bất biến đường từ gốc tới nút hiện tại |
| Cho rằng hai nút đích chắc chắn tồn tại | LCA trả nhầm một đích khi đích kia vắng | Xác minh tồn tại hoặc dùng DFS trả `count` |
| Quên trường hợp `a is b` | Đếm nhầm hai đích khác nhau | Xử lý cùng nút rõ ràng |
| Dùng LCA BST cho cây không có thứ tự | Rẽ sai nhánh | Dùng LCA cây tổng quát |
| Mặc định BST luôn cân bằng | Báo nhầm O(log n) | Viết O(h), chỉ đổi thành O(log n) khi có bảo đảm |
| Coi LCA luôn phải là nút phía trên hai đích | Trả sai khi một đích là tổ tiên đích kia | Dùng định nghĩa tổ tiên bao gồm chính nút |
| Dùng `==` thay `is` trên object có equality theo nội dung | Nhầm hai nút cùng payload | Quy định identity/ID |
| BFS quên ghi cha ngay khi phát hiện con | Không dựng được đường chính xác | Ghi `parent[child]` lúc enqueue |
| Dùng bảng cha của cây cũ sau khi quay/chuyển nhánh | LCA và khoảng cách sai | Rebuild hoặc duy trì metadata có chứng minh |
| Dùng DFS đệ quy trên cây lệch cực sâu | Có thể tràn stack/`RecursionError` | Dùng stack/queue lặp hoặc mô hình khác |
| Dùng con trỏ nút đã hủy trong path C | Use-after-free | Bảo đảm lifetime hoặc copy dữ liệu cần thiết |
| Xem DAG có nút nhiều cha như cây | Đường không còn duy nhất | Chuyển sang bài toán đồ thị với định nghĩa rõ |
| Tính khoảng cách mà không kiểm tra LCA | Dùng độ sâu không chung gốc | Xác minh cùng cây và tổ tiên hợp lệ |

## 16. Quy trình kiểm thử và đánh giá thuật toán

### 16.1. Các trường hợp tối thiểu

1. **Cây rỗng:** tìm đường trả `None`; LCA trả `None`.
2. **Cây một nút:** đường tới gốc có một nút; `LCA(root,root)=root`.
3. **Hai nút cùng cây con:** LCA nằm dưới gốc.
4. **Hai nút khác cây con của gốc:** LCA chính là gốc.
5. **Một đích là tổ tiên đích kia:** LCA bằng đích tổ tiên.
6. **Hai đích là chính một đối tượng:** LCA bằng đối tượng đó nếu tồn tại.
7. **Một đích không có trong cây:** trả `None`, không trả đích còn lại.
8. **Hai đối tượng khác nhau cùng giá trị:** không đồng nhất chúng.
9. **Cây lệch sâu:** xác minh đường, độ sâu và không dựa vào stack khi có nguy cơ quá giới hạn.
10. **Cây cân đối nhiều nhánh:** kiểm tra các mức độ sâu khác nhau.
11. **BST với khóa vắng:** phương pháp rẽ nhánh phải trả `None`.
12. **Nhiều truy vấn:** so sánh kết quả binary lifting với phương pháp hai đường trên cùng cây tĩnh.
13. **Đường giữa hai nút:** bắt đầu bằng `a`, kết thúc bằng `b`, không lặp LCA.
14. **Khoảng cách:** bằng `len(path_between(a,b))-1`.
15. **Quay/chuyển cây con:** chỉ mục cũ phải được xem là stale hoặc rebuild.
16. **Cây có nút được chia sẻ hay chu trình:** kiểm tra đầu vào không đáp ứng giả định của thuật toán cây.

### 16.2. Bất biến dùng trong kiểm thử

Với `parent` và `depth` của một cây hợp lệ:

- `parent[root] is None`.
- `depth[root] == 0`.
- Với mỗi nút khác gốc: `parent[node]` tồn tại và `depth[node] == depth[parent[node]] + 1`.
- `path_from_index(node)[0] is root` và phần tử cuối `is node`.
- Nếu `lca(a,b) = l`, `l` nằm trên cả hai đường gốc–đích.
- Không có tổ tiên chung khác có độ sâu lớn hơn `depth[l]`.
- `distance(a,b) == distance(b,a)` và `distance(a,a) == 0`.
- Với mỗi cặp nút tồn tại, các phương pháp LCA độc lập phải trả **cùng đối tượng**.

Ví dụ Python sau có thể dùng để đối chiếu các phương pháp trên cây mẫu:

```python
root, nodes = sample_tree()
parent, depth = build_parent_depth(root)
lifting = BinaryLifting(root)

for a in nodes.values():
    for b in nodes.values():
        expected = lca_by_paths(root, a, b)

        assert lca_verified(root, a, b) is expected
        assert lca_from_parent(a, b, parent, depth) is expected
        assert lifting.lca(a, b) is expected

        path = path_between(a, b, parent)
        assert path is not None
        assert path[0] is a
        assert path[-1] is b

        distance = distance_edges(a, b, depth, expected)
        assert distance == len(path) - 1
```

**Lưu ý:** đoạn `assert` thực hiện nhiều truy vấn trong mã **kiểm thử** để kiểm chứng tính nhất quán. Chúng không phải lời khuyên dùng nhiều thuật toán song song trên mỗi truy vấn trong môi trường sản phẩm.

## 17. Bài tập thực hành có lời giải

### Bài 1. Đường từ gốc tới một nút

Với cây mẫu `8/3/10/...` ở đầu bài, tìm đường từ gốc tới nút 13.

**Lời giải:** `8 → 10 → 14 → 13`. Có 4 nút, 3 cạnh, nên `depth(13)=3`.

### Bài 2. LCA hai nút cùng cây con

Tìm `LCA(4,7)`.

**Lời giải:** `6`. Hai đường `[8,3,6,4]` và `[8,3,6,7]` có tiền tố chung dài nhất `[8,3,6]`.

### Bài 3. LCA hai nhánh khác nhau

Tìm `LCA(1,13)`.

**Lời giải:** `8`, vì 1 thuộc nhánh trái của 8 còn 13 thuộc nhánh phải; không có tổ tiên chung nào dưới 8.

### Bài 4. Một nút là tổ tiên của nút còn lại

Tìm `LCA(3,4)`.

**Lời giải:** `3`. Theo định nghĩa inclusive ancestor, 3 là tổ tiên của chính nó và của 4.

### Bài 5. Hai đối số cùng một nút

Nếu `a is b` và `a` thuộc cây, `LCA(a,b)` là gì?

**Lời giải:** Chính `a`. Nếu `a` không thuộc cây, hàm tuân thủ hợp đồng bài phải trả `None`.

### Bài 6. Giá trị trùng nhưng danh tính khác

Hai nút khác nhau A và B đều mang `value = 5` và là hai con của gốc R. Có thể tìm LCA chỉ bằng câu hỏi “khóa 5” không?

**Lời giải:** Không đủ thông tin nếu khóa trùng. Với hai đối tượng A/B được xác định riêng, `LCA(A,B)=R`. Cần ID/danh tính hoặc một quy tắc chọn nút rõ ràng.

### Bài 7. Quay lui DFS

Đang tìm đường tới nút trong cây con phải, nhưng DFS đã duyệt cây con trái không có đích. Vì sao phải gọi `path.pop()` khi nhánh trái thất bại?

**Lời giải:** Để bỏ các nút của nhánh không nằm trên đường tới đích, khôi phục `path` thành đường tới cha trước khi thử nhánh phải. Nếu không, kết quả có thể chứa cả đường sai.

### Bài 8. Nút không tồn tại

`a` thuộc cây, còn `b` là một đối tượng mới có cùng giá trị với một nút trong cây. Theo hợp đồng identity, `LCA(a,b)` là gì?

**Lời giải:** `None`, vì `b` không phải đối tượng nút thuộc cây. Không được báo LCA chỉ bằng việc khớp giá trị.

### Bài 9. Lỗi phổ biến của LCA đệ quy ngắn

Một hàm đệ quy gặp `a` thì trả `a`, cuối cùng trả `a` dù không tìm thấy `b`. Nó đã vi phạm điều kiện nào?

**Lời giải:** Nó chưa xác minh **cả hai đích hiện diện**. Cần hai phép kiểm tra tồn tại hoặc một DFS có đếm số đích và chỉ xuất LCA khi đủ hai.

### Bài 10. Thời gian tìm hai đường

Trên cây có `n` nút và chiều cao `h`, tìm hai đường bằng DFS quay lui rồi lấy tiền tố chung tốn thời gian/bộ nhớ gì?

**Lời giải:** O(n) thời gian xấu nhất cho hai lần DFS, O(h+1) bộ nhớ phụ gồm stack và các đường; so sánh tiền tố mất thêm O(h+1), không đổi bậc O(n).

### Bài 11. Bảng cha để nhiều truy vấn

Cần tìm đường gốc–đích của 1.000 nút khác nhau trong cùng cây tĩnh. Vì sao nên cân nhắc xây bảng cha một lần?

**Lời giải:** Bảng cha xây O(n) cho toàn cây, sau đó mỗi đường có thể dựng bằng cách leo từ đích về gốc O(d+1). Tránh duyệt lại nhiều nhánh không liên quan cho từng câu hỏi. Đổi lại bộ nhớ bảng O(n).

### Bài 12. Cân bằng độ sâu

Hai nút `a` và `b` lần lượt có độ sâu 7 và 3. Trước khi cho cả hai leo cha đồng thời, cần làm gì?

**Lời giải:** Nâng `a` lên 4 cạnh để cùng độ sâu 3 với `b`. Sau đó nếu hai nút trùng thì đó là LCA; nếu chưa thì cho cả hai leo mỗi lần một cạnh.

### Bài 13. Chi phí BST LCA

Một BST có `n` nút cân bằng, chứa hai khóa `x,y`. Tìm LCA theo so sánh khóa tốn bao nhiêu? Nếu BST lệch?

**Lời giải:** O(h+1) nói chung; cây cân bằng có O(log n), cây lệch có O(n). Cần xác minh cả hai khóa tồn tại nếu API yêu cầu trả `None` khi thiếu.

### Bài 14. Nâng 13 cạnh bằng binary lifting

Giả sử bảng `up[k][v]` chứa tổ tiên cách `2^k` cạnh. Nâng một nút lên 13 cạnh bằng những mức nào?

**Lời giải:** `13 = 8+4+1`, dùng mức `k=3`, `k=2` và `k=0`. Thứ tự có thể thay đổi khi các tổ tiên tồn tại và tổng số cạnh bằng 13.

### Bài 15. Chi phí nhiều truy vấn

Với `n` nút và `q` truy vấn LCA trên cây tĩnh, binary lifting mất bao nhiêu thời gian/bộ nhớ?

**Lời giải:** O(n log n) tiền xử lý và bộ nhớ; mỗi truy vấn O(log n), tổng O(n log n + q log n). Không tự áp dụng bảng cũ sau khi thay đổi quan hệ cha–con.

### Bài 16. Euler tour và RMQ

Vì sao giữa lần xuất hiện đầu của hai nút trong Euler tour, vị trí có độ sâu nhỏ nhất cho ta LCA?

**Lời giải:** Để đi từ nhánh chứa nút đầu sang nhánh chứa nút sau, DFS phải quay lên tổ tiên chung gần nhất. Trong đoạn tour nối hai vị trí, đó là độ sâu nhỏ nhất. RMQ dùng để tìm vị trí này.

### Bài 17. Khoảng cách giữa hai nút

Trong cây mẫu, tính khoảng cách số cạnh giữa 4 và 13.

**Lời giải:** `depth(4)=3`, `depth(13)=3`, `depth(LCA=8)=0` nên `3+3-2·0=6` cạnh. Đường: `4 → 6 → 3 → 8 → 10 → 14 → 13`.

### Bài 18. Khoảng cách của nút với chính nó

Với `a` tồn tại, tính `dist(a,a)` và `LCA(a,a)`.

**Lời giải:** `dist(a,a)=0` và `LCA(a,a)=a`. Đường giữa hai nút là `[a]`, chỉ một nút và không có cạnh.

### Bài 19. Quay cây có làm đổi LCA?

Một cây BST được quay để cân bằng nhưng giữ nguyên tập khóa và thứ tự inorder. Có thể tái sử dụng vô điều kiện bảng binary lifting trước quay không?

**Lời giải:** Không. Quay làm đổi liên kết cha–con và có thể đổi độ sâu/LCA. Phải cập nhật đúng mọi bảng phụ thuộc cấu trúc hoặc xây lại chỉ mục.

### Bài 20. Cây hay DAG?

Hai nhánh của một cấu trúc cùng trỏ tới nút D. Có còn một đường duy nhất từ gốc tới D không?

**Lời giải:** Không nhất thiết. D có thể được đi tới từ hai đường; đây là DAG nếu không có chu trình, không còn là cây theo giả định mỗi nút một cha. Bài toán LCA cần được định nghĩa lại phù hợp đồ thị, không sao chép máy móc thuật toán cây.

## 18. Tổng kết và nguyên tắc lựa chọn

- **Đường từ gốc** đến mỗi nút của một cây có gốc là duy nhất. Có thể lấy bằng **DFS quay lui** hoặc **BFS ghi cha**; DFS cần O(h+1) stack, bảng cha cần O(n) bộ nhớ để tái sử dụng.
- **LCA là tổ tiên chung sâu nhất**, bao gồm trường hợp một đích là tổ tiên của đích kia. Định nghĩa trong bài yêu cầu **cả hai đích tồn tại**.
- **Phân biệt danh tính nút và payload:** hai nút có cùng nhãn vẫn là hai đối tượng; nếu khóa trùng, thuật toán dựa trên giá trị có thể mơ hồ.
- **Ít truy vấn trên cây bất kỳ:** tìm hai đường và so tiền tố, hoặc DFS một lượt có xác minh hiện diện, đều O(n) thời gian xấu nhất.
- **BST có khóa duy nhất:** so sánh khóa để rẽ nhánh tìm LCA O(h+1), O(log n) khi cây cân bằng.
- **Nhiều truy vấn trên cây tĩnh:** parent/depth O(n) chuẩn bị và O(h+1) mỗi truy vấn; **binary lifting** O(n log n) tiền xử lý, O(log n) mỗi truy vấn; Euler tour + sparse-table RMQ có thể O(1) mỗi truy vấn sau tiền xử lý O(n log n).
- **Đường giữa hai nút** đi qua LCA; khoảng cách cạnh là `depth(a)+depth(b)-2depth(LCA)`.
- **Bất biến và vòng đời quan trọng hơn mẹo tính toán:** cây bị chuyển nhánh/xóa/quay có thể làm đường và chỉ mục cũ sai; con trỏ tới nút đã giải phóng có thể treo, còn cây có chu trình/nhiều cha không đáp ứng chứng minh của thuật toán cây.
- **Chọn theo tình huống:** số truy vấn, chiều cao cây, mức thay đổi cấu trúc, bộ nhớ sẵn có và nhu cầu xuất đường thực tế. Một truy vấn nhanh không giúp tránh được thời gian cần thiết để xuất hàng nghìn nút trên đường dài.
