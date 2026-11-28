# Sao chép, giải phóng và duyệt cây có độ sâu lớn

Một cây có hàng trăm nghìn nút không nhất thiết rộng: nó có thể lệch hoàn toàn về một phía và gần giống một danh sách liên kết. Khi đó, các hàm đệ quy rất tự nhiên như `clone(root)`, `free_tree(root)` hay `inorder(root)` có thể tạo **hàng trăm nghìn khung lời gọi**. Chương trình có thể bị `RecursionError` trong Python hoặc cạn ngăn xếp thực thi trong C/C++, dù độ phức tạp thời gian của thuật toán vẫn là O(n).

Bài **“Sao chép, giải phóng và duyệt cây có độ sâu lớn”** thuộc chương **Duyệt và biến đổi cây** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Nền tảng của module bao gồm mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, với trọng tâm là **bất biến cấu trúc**, **vòng đời đối tượng** và **độ phức tạp thời gian/bộ nhớ**. Ở đây, ta dùng stack tường minh, queue và kỹ thuật chỉnh liên kết có kiểm soát để xử lý cây sâu **không phụ thuộc độ sâu đệ quy**.

Mục tiêu sau bài học:

- Phân biệt **sao chép con trỏ**, **sao chép nông**, **sao chép sâu cấu trúc** và **chia sẻ cấu trúc có chủ đích**.
- Viết thuật toán **clone cây nhị phân không đệ quy**, bảo toàn giá trị và hình dạng trong khi không dùng chung nút.
- Hiểu tại sao việc giải phóng **từng nút đúng một lần** phải tuân theo chính sách sở hữu; cài đặt cách giải phóng cây sâu không dùng đệ quy, kể cả khi bộ nhớ cấp phát thêm khan hiếm.
- Duyệt preorder, inorder, postorder và level-order bằng **stack/queue tường minh**; phân tích chi phí theo số nút `n`, chiều cao `h` và độ rộng `w`.
- Phát hiện các trường hợp đặc biệt: cây rỗng, chỉ một nút, cây lệch, shared subtree, chu trình, lỗi cấp phát, giải phóng trùng, iterator mất hiệu lực và dữ liệu payload có tài nguyên riêng.
- Chọn giải pháp thực tế trong Python, C và C++ với hợp đồng về **quyền sở hữu**, **lỗi** và **an toàn khi dừng giữa chừng**.

## 1. Cây sâu là gì và vì sao không thể chỉ nhìn vào số nút?

Xét hai cây nhị phân có cùng `n` nút.

```text
Cây cân đối, ít tầng:                  Cây lệch trái, rất sâu:

           A                                   A
         /   \                                /
        B     C                              B
       / \   / \                            /
      D   E F   G                          C
                                          /
                                         D
                                        /
                                       E
                                       ...
```

Gọi:

- `n` là số nút dữ liệu thật.
- `h` là **chiều cao tính bằng số cạnh** từ gốc tới lá sâu nhất. Cây một nút có `h=0`. Với cây rỗng, có thể chọn `h=-1` theo quy ước.
- `w` là số nút lớn nhất trên một tầng (maximum width).
- `d` là độ sâu của một nút, tính từ gốc với `depth(root)=0`.

| Hình dạng | Chiều cao `h` | Độ rộng `w` | Hệ quả |
| --- | --- | --- | --- |
| Cây một đường, `n` nút | `n-1` | 1 | Đệ quy và DFS stack có thể sâu Θ(n), BFS queue O(1) |
| Cây nhị phân cân đối | Θ(log n) | Có thể Θ(n) | DFS stack nhỏ, BFS queue có thể rất lớn |
| Cây tùy ý | Từ Θ(log n) tới Θ(n) đối với cây nhị phân có đủ nút | Từ 1 tới Θ(n) | Phải xét cả chiều cao và độ rộng |
| Cây rỗng | Theo quy ước | 0 | Mọi thao tác phải xử lý gốc `NULL`/`None` |

**Chi phí thời gian O(n) không có nghĩa an toàn ngăn xếp.** Hai hiện thực đều duyệt mỗi nút một lần nhưng một hiện thực gọi đệ quy sâu O(h), còn hiện thực kia giữ trạng thái trên một container tường minh mà ta có thể quản lý giới hạn bộ nhớ và đường lỗi.

### 1.1. Đệ quy dùng stack của chương trình

Một lời gọi đệ quy thường giữ **địa chỉ trả về, tham số, biến cục bộ** và trạng thái xử lý trên call stack. Nếu có `h+1` khung liên tiếp, độ sâu stack cũng là O(h+1). Đây là bộ nhớ **phụ trợ**, tách khỏi O(n) dung lượng đã có để lưu các nút.

Trong Python, cây rất sâu có thể gây `RecursionError`. Trong C/C++, cạn stack có thể dẫn đến lỗi nghiêm trọng, và không có bảo đảm portable rằng hệ thống sẽ báo một lỗi có thể phục hồi. **Không nâng giới hạn đệ quy hoặc tăng stack một cách mù quáng như giải pháp duy nhất**; hãy xem việc chuyển thành thuật toán lặp.

### 1.2. Stack/queue tường minh không tự làm biến mất mọi giới hạn

Dùng `list`/`vector`/mảng động làm stack chuyển phần trạng thái từ call stack sang vùng lưu do chương trình quản lý. Container ấy vẫn có thể **hết bộ nhớ** hoặc vượt giới hạn kích thước; do đó cần thiết kế xử lý thất bại. Đặc biệt, giải phóng một cây khi đang thiếu bộ nhớ nên ưu tiên kỹ thuật **không đòi cấp phát thêm**, nếu phù hợp với hợp đồng của dữ liệu.

## 2. Bất biến của một cây sở hữu riêng

Các thuật toán cơ bản trong bài trước hết giả định **cây nhị phân hữu hạn, không có chu trình và không chia sẻ cùng một nút con ở hai vị trí**.

Với mô hình C:

```c
typedef struct Node {
    int value;
    struct Node *left;
    struct Node *right;
} Node;
```

Ta có thể quy định **một chủ sở hữu (unique owner)** của toàn bộ cây. Chủ sở hữu này quản lý các nút reachable từ `root` và giải phóng đúng một lần khi kết thúc.

Bất biến:

1. `root == NULL` biểu diễn cây rỗng.
2. Mỗi nút thật có tối đa hai con; một liên kết `NULL` nghĩa là **không có nút con**.
3. Một nút khác gốc chỉ có **một cha**; không có cạnh tạo chu trình.
4. Hai con trỏ `left` và `right` chỉ đến nút thuộc cây đang sống hoặc `NULL`.
5. Mỗi nút được cấp phát động được **hủy đúng một lần**, không dùng sau khi hủy.
6. Một thao tác copy phải nêu rõ **nút có được chia sẻ** hay không và **ai sở hữu** từng nhánh.

```text
Cây hợp lệ:                         Không còn là cây sở hữu riêng:

       A                                  A
      / \                                / \
     B   C                              B   C
                                        \ /
                                         D

                                 D có hai cha / được chia sẻ.

Chu trình sai:
       A ---> B
       ^      |
       +------+
```

Với **DAG** (có shared subtree) hoặc đồ thị (có chu trình), thuật toán sao chép/giải phóng kiểu cây ngây thơ có thể copy lặp, giải phóng trùng hoặc lặp vô hạn. Bài sẽ phân tích riêng ở Mục 13.

### 2.1. Payload đơn giản và payload có tài nguyên khác nhau

`int value` được sao chép bằng phép gán. Nhưng nếu `Node` chứa `char *name`, `FILE *stream`, con trỏ tới mảng hoặc tài nguyên ngoài, **copy một `Node` không tự tạo ra bản sao độc lập của tài nguyên ấy**.

Ví dụ:

```c
typedef struct NamedNode {
    char *name;                  /* Giả sử nút sở hữu chuỗi cấp phát động. */
    struct NamedNode *left;
    struct NamedNode *right;
} NamedNode;
```

Nếu một node mới chỉ gán `new_node->name = old_node->name`, hai node cùng giữ địa chỉ. Nếu cả hai đều gọi `free(name)` khi dọn, có thể double free. Phải chọn **copy chuỗi** hoặc thay chính sách thành **chia sẻ không sở hữu / sở hữu chia sẻ** có hợp đồng phù hợp. Với ví dụ chính trong bài, payload là `int` để làm rõ các liên kết và chi phí của **cấu trúc cây**.

## 3. Sao chép nông, sao chép sâu và chia sẻ cấu trúc

### 3.1. Gán con trỏ: không tạo bản sao cây

```c
Node *alias = root;   /* Không có Node nào được tạo mới. */
```

`alias` và `root` cùng chỉ một cây. Nếu một nơi giải phóng cây, con trỏ còn lại có thể trở thành **con trỏ treo**. Không được coi hai tên con trỏ là hai chủ sở hữu độc lập.

### 3.2. Sao chép nông một nút: dễ tạo hai chủ sở hữu cho cùng cây con

```c
/* Không phải một deep clone an toàn:
Node *copy = malloc(sizeof *copy);
if (copy != NULL) {
    *copy = *root;  // left/right vẫn giữ địa chỉ cây con cũ.
}
*/
```

Phép gán struct sao chép **giá trị trường con trỏ**, không nhân bản các nút phía dưới. Hai gốc khác nhau có thể cùng trỏ tới những cây con; nếu destructor đệ quy của cả hai gốc đều coi chúng là sở hữu riêng, sẽ giải phóng trùng.

### 3.3. Sao chép sâu cấu trúc: mỗi nút được tạo lại

```text
Cây gốc:                          Cây clone sâu:

     A@0x10                            A'@0x90
     /   \                             /    \
   B@20 C@30                         B'@A0 C'@B0

Giá trị/hình dạng tương đương; mỗi nút A', B', C' có danh tính mới.
Không có liên kết con nào của clone trỏ tới nút cây gốc.
```

Trong bài, **deep clone cấu trúc** nghĩa là mỗi nút gốc có **đúng một nút mới** tương ứng, cùng giá trị `int`, cùng các quan hệ `left/right`, nhưng không trùng danh tính. Nếu payload chứa đối tượng mutable hay tài nguyên cấp phát riêng, muốn **độc lập cả payload** phải clone từng payload theo hợp đồng.

### 3.4. Structural sharing là lựa chọn khác, không phải lỗi mặc định

Một số **cây bất biến/persistent tree** chia sẻ các nhánh không thay đổi giữa các phiên bản nhằm giảm chi phí copy:

```text
Version 1 root ---+--> Subtree S
Version 2 root ---+--> Subtree S   (S bất biến và dùng chung)
```

Thiết kế này có thể hợp lệ nếu có cơ chế sở hữu và vòng đời bảo đảm `S` còn sống đến khi phiên bản cuối thôi dùng nó. Không được áp dụng hàm `free_tree` vốn giả định **mọi nhánh đều có một chủ sở hữu duy nhất** lên từng phiên bản rồi hy vọng không có double free.

## 4. Phiên bản đệ quy: đẹp về ý tưởng, có giới hạn độ sâu

### 4.1. Clone đệ quy

```python
def clone_recursive(node):
    if node is None:
        return None
    return Node(
        node.value,
        left=clone_recursive(node.left),
        right=clone_recursive(node.right),
    )
```

Theo quy nạp: cây rỗng được clone thành rỗng; nút hiện tại được tạo mới và hai cây con được clone rồi gắn vào hai trường tương ứng. Tổng thời gian O(n), số khung sâu nhất O(h+1), chưa kể O(n) bộ nhớ của cây kết quả.

Nhưng nếu cây lệch có độ sâu rất lớn, đệ quy Python có thể thất bại **trước khi clone xong**. Tương tự trong C với `malloc` và các lời gọi đệ quy, có thêm rủi ro **cấp phát thất bại** và cần thu hồi clone dở.

### 4.2. Giải phóng đệ quy kiểu C

```c
#include <stdlib.h>

/* Chỉ an toàn về cấu trúc khi đúng là cây sở hữu riêng,
   và độ sâu lời gọi phù hợp với ngăn xếp thực thi. */
void free_recursive(Node *node) {
    if (node == NULL) return;
    free_recursive(node->left);
    free_recursive(node->right);
    free(node);
}
```

Đây là **postorder: trái → phải → gốc**. Nếu gọi `free(node)` trước rồi truy cập `node->left` hoặc `node->right`, đó là use-after-free. Tuy nhiên, việc duyệt đúng thứ tự **không giải quyết được nguy cơ cạn call stack trên cây sâu**.

### 4.3. DFS đệ quy và các điểm không được quên

- Đặt **base case** cho cây rỗng trước khi giải tham chiếu.
- Với hàm có thể ném ngoại lệ hoặc thất bại cấp phát, phải thiết kế cleanup bản sao đang xây.
- Không đệ quy đi qua một nút **nhiều lần như thể mỗi lần là một chủ sở hữu riêng** khi đầu vào có shared subtree.
- Không dùng đệ quy để “xóa từng đỉnh có thể tới được” trong cấu trúc có chu trình mà không có cơ chế visited.
- Trên cây sâu, chuyển sang **stack/queue tường minh** hoặc một thuật toán hủy không cần stack.

## 5. Python: clone cây sâu bằng DFS stack tường minh

Ví dụ Python dùng node chứa `int`, nên copy giá trị đủ để payload độc lập. Ta tạo nút mới ngay khi phát hiện nút cũ, rồi đưa **cặp nút nguồn–đích** vào stack để mở rộng từng tầng nhánh theo DFS.

### 5.1. Định nghĩa nút và clone lặp

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(eq=False)
class Node:
    value: int
    left: Node | None = None
    right: Node | None = None


def clone_tree_iterative(root: Node | None) -> Node | None:
    """Clone các NÚT của một cây nhị phân sở hữu riêng."""
    if root is None:
        return None

    cloned_root = Node(root.value)
    stack: list[tuple[Node, Node]] = [(root, cloned_root)]

    while stack:
        source, target = stack.pop()

        if source.right is not None:
            target.right = Node(source.right.value)
            stack.append((source.right, target.right))

        if source.left is not None:
            target.left = Node(source.left.value)
            stack.append((source.left, target.left))

    return cloned_root


root = Node(8, Node(3, Node(1), Node(6)), Node(10))
copy = clone_tree_iterative(root)

assert copy is not None
assert copy is not root
assert copy.left is not root.left
assert copy.left.value == root.left.value

copy.left.value = 999
assert root.left.value == 3
```

**Tại sao push phải trước trái?** Vì stack LIFO, công việc mở rộng nút trái sẽ được xử lý trước nút phải. Tuy nhiên, cả hai trường con vẫn được gắn đúng `left/right`, nên **thứ tự xử lý công việc không ảnh hưởng hình dạng clone cuối cùng** trong cây không chia sẻ nút.

### 5.2. Bất biến của clone tường minh

Sau mỗi vòng lặp:

1. `cloned_root` đã là một nút mới độc lập với gốc.
2. Với mọi cặp `(source,target)` đang chờ trên stack, `target` là bản sao nút tương ứng vừa tạo; các con của cặp ấy chưa được mở rộng.
3. Với mọi nút đã xử lý, trường `target.left/right` trỏ tới nút clone đúng của `source.left/right` hoặc `None`.
4. Không có một nút clone nào lấy `left/right` của nút gốc làm đường liên kết đích.
5. Mỗi nút nguồn của cây thật được tạo một nút đích và được mở rộng một lần.

Do đó, khi stack rỗng, toàn bộ cây đã được clone với hình dạng và giá trị tương ứng.

### 5.3. Thời gian và bộ nhớ

Với cây có `n` nút, chiều cao `h`:

- **O(n)** thời gian tạo `n` nút mới.
- **O(n)** bộ nhớ cho các nút clone (đầu ra).
- **O(h+1)** bộ nhớ phụ trợ cho stack DFS ở cây nhị phân sở hữu riêng; tại một thời điểm stack chứa các nhánh chưa xử lý dọc theo đường hiện tại.
- Không dùng ngăn xếp đệ quy của Python nên tránh lỗi `RecursionError` do chính thuật toán clone.

**Quan trọng:** không được gọi tổng bộ nhớ là O(h) vì cây clone có `n` nút mới. Stack chỉ là **bộ nhớ phụ trợ ngoài đầu ra**.

### 5.4. Kiểm thử trên cây lệch rất sâu

Có thể dựng một đường con trái dài bằng vòng lặp, không dùng đệ quy:

```python
def make_left_chain(n: int) -> Node | None:
    root = None
    for value in range(n):
        root = Node(value, left=root)
    return root


root = make_left_chain(100_000)
cloned = clone_tree_iterative(root)

# Kiểm tra cấu trúc theo vòng lặp; không so sánh đệ quy cả cây.
a, b = root, cloned
count = 0

while a is not None and b is not None:
    assert a is not b
    assert a.value == b.value
    assert a.right is None and b.right is None
    a, b = a.left, b.left
    count += 1

assert a is None and b is None
assert count == 100_000
```

Đây là bài thử minh họa dùng khá nhiều bộ nhớ thực tế; kích thước phù hợp tùy môi trường. Không kiểm tra bằng `root == cloned` nếu kiểu dữ liệu tự định nghĩa so sánh sâu đệ quy trên các cây con: phép so sánh đó cũng có thể gặp giới hạn độ sâu.

## 6. Duyệt cây sâu mà không dùng đệ quy

Để duyệt không đệ quy, ta chuyển trạng thái “đang ở đâu và sẽ làm gì tiếp” từ call stack sang **stack hoặc queue tường minh**.

### 6.1. Preorder: gốc → trái → phải

```python
def preorder_iter(root: Node | None):
    if root is None:
        return

    stack = [root]
    while stack:
        node = stack.pop()
        yield node.value

        if node.right is not None:
            stack.append(node.right)
        if node.left is not None:
            stack.append(node.left)
```

Push **phải trước trái** vì stack LIFO sẽ pop trái trước. Mỗi nút được đẩy và lấy ra đúng một lần. Thời gian O(n), bộ nhớ stack O(h+1) đối với cây nhị phân; trên cây lệch thành một đường chỉ cần O(1) mục chờ trong phiên bản này.

### 6.2. Inorder: trái → gốc → phải

```python
def inorder_iter(root: Node | None):
    stack: list[Node] = []
    current = root

    while current is not None or stack:
        while current is not None:
            stack.append(current)
            current = current.left

        current = stack.pop()
        yield current.value
        current = current.right
```

Stack giữ các tổ tiên cần quay lại sau khi duyệt cây con trái. Mỗi nút được push/pop một lần, tổng O(n) thời gian và O(h+1) stack.

Trong cây BST có khóa đúng bất biến, inorder sinh các khóa theo thứ tự **không giảm**; với khóa duy nhất là thứ tự **tăng chặt**. Nhưng nếu payload không phải khóa BST, inorder vẫn là một thứ tự duyệt cấu trúc chứ không có nghĩa sắp xếp.

### 6.3. Postorder: trái → phải → gốc bằng khung trạng thái

```python
def postorder_iter(root: Node | None):
    if root is None:
        return

    # ready=True: hai cây con đã được xếp để xử lý trước cha.
    stack: list[tuple[Node, bool]] = [(root, False)]

    while stack:
        node, ready = stack.pop()

        if ready:
            yield node.value
        else:
            stack.append((node, True))
            if node.right is not None:
                stack.append((node.right, False))
            if node.left is not None:
                stack.append((node.left, False))
```

Nếu không có cờ `ready` hoặc thông tin tương đương, rất dễ xuất cha **trước** khi duyệt xong con. Khung `ready=True` nằm dưới hai cây con trong stack, nên cha chỉ xuất sau.

Với cây nhị phân thật, số khung hoạt động O(h+1), tổng thao tác O(n). Bất kể duyệt đủ hay dừng sớm, generator còn giữ các tham chiếu tới những nút trên stack cho đến khi được hoàn tất hoặc đóng.

### 6.4. Level-order: queue FIFO

```python
from collections import deque


def levelorder_iter(root: Node | None):
    if root is None:
        return

    queue = deque([root])

    while queue:
        node = queue.popleft()
        yield node.value

        if node.left is not None:
            queue.append(node.left)
        if node.right is not None:
            queue.append(node.right)
```

BFS dùng queue vì phải xử lý nút gần gốc trước. Tổng O(n) thời gian, bộ nhớ queue O(w), trong đó `w` là độ rộng tầng lớn nhất. Với cây một đường, queue O(1); với cây cân đối rất rộng, queue có thể Θ(n).

**Chi tiết về `yield`:** mã trên enqueue con **sau khi** yield, tức các liên kết con được đọc khi bên gọi yêu cầu phần tử tiếp. Nếu cây bị sửa giữa hai lần lấy, hành vi có thể phản ánh liên kết mới; không mặc định generator là snapshot bất biến. Khi cần đọc con trước lúc nhường điều khiển, enqueue trước `yield`; nhưng điều đó vẫn không bảo vệ cây khỏi các thay đổi sâu hơn.

### 6.5. Kiểm tra các dãy duyệt

```python
root = Node(
    8,
    left=Node(3, Node(1), Node(6)),
    right=Node(10),
)

print(list(preorder_iter(root)))   # [8, 3, 1, 6, 10]
print(list(inorder_iter(root)))    # [1, 3, 6, 8, 10]
print(list(postorder_iter(root)))  # [1, 6, 3, 10, 8]
print(list(levelorder_iter(root))) # [8, 3, 10, 1, 6]
```

Các hàm ở trên sinh giá trị **lười** từng bước. `list(...)` trong ví dụ chỉ dùng để hiển thị/kiểm tra kết quả và sẽ tạo danh sách O(n); trong ứng dụng có thể duyệt trực tiếp hoặc dừng khi đã đủ dữ liệu.

## 7. Giải phóng cây sâu bằng cách chỉnh liên kết, không cấp phát thêm

Đây là tình huống dễ bị bỏ sót: ta đã clone bằng stack tường minh, nhưng khi cleanup lại gọi destructor đệ quy rồi gặp stack overflow trên cây rất sâu.

Trong C, có thể giải phóng một **cây nhị phân sở hữu riêng** bằng cách **xoay/phẳng dần liên kết** và giải phóng nút khi không còn con trái. Thuật toán sau dùng **O(1) bộ nhớ phụ trợ**, không cần stack hoặc `malloc` mới.

### 7.1. Trực giác

Nếu nút `root` còn con trái `left`, chuyển nút con trái lên trước nút gốc:

```text
Trước một bước:
           R
          / \
         L   T
        / \
       A   B

Sau một lần đổi liên kết:
           L
          / \
         A   R
            / \
           B   T
```

Không có nút nào bị tạo hoặc mất ở bước này. Khi nút đang xét **không còn con trái**, nó có thể được giải phóng; nút tiếp theo là con phải của nó. Việc xoay đưa những nút cần xử lý ra đầu đường tiến mà không cần lưu stack.

### 7.2. Mã C giải phóng O(1) bộ nhớ phụ trợ

```c
#include <stdlib.h>

typedef struct Node {
    int value;
    struct Node *left;
    struct Node *right;
} Node;

/*
 * Tiêu thụ toàn bộ cây sở hữu riêng.
 * Không dùng root hoặc bất kỳ Node* trong cây sau khi gọi.
 * Không cần cấp phát thêm và không dùng đệ quy.
 */
void tree_destroy_iterative(Node *root) {
    while (root != NULL) {
        if (root->left != NULL) {
            Node *left = root->left;

            root->left = left->right;
            left->right = root;
            root = left;
        } else {
            Node *next = root->right;
            free(root);
            root = next;
        }
    }
}
```

### 7.3. Vì sao không gây use-after-free?

Ở nhánh `root->left == NULL`:

1. **Đọc `root->right` trước** để lưu nơi tiếp tục.
2. `free(root)` đúng một lần.
3. Chỉ dùng biến `next` đã lưu, **không đọc `root` nữa**.

Ở nhánh có con trái, chỉ đổi các liên kết của **nút còn sống** và không giải phóng; nút mới được đưa lên trở thành `root` để tiếp tục vòng lặp.

### 7.4. Tính đúng đắn và độ phức tạp

Với một cây nhị phân hữu hạn, không có chu trình/chia sẻ nút và các liên kết do cùng một chủ sở hữu quản lý:

- Một bước **xoay** chỉ sắp lại các liên kết mà không làm mất nút hoặc sinh thêm nút.
- Khi không còn con trái, nút hiện tại được giải phóng rồi rời cấu trúc xử lý; nó không xuất hiện lại.
- Các phép xoay chuyển những nút chưa xử lý ra đầu đường đi; mỗi nút được giải phóng một lần.
- Toàn bộ phép xoay và giải phóng cộng lại có độ phức tạp **O(n)**, bộ nhớ phụ trợ **O(1)**. Đây là cách phẳng hóa phá hủy theo đường phải, không phải một lượt duyệt bảo toàn hình dạng.

**Hợp đồng cực kỳ quan trọng:** phương pháp **phá hủy liên kết cây trong quá trình chạy**. Chỉ dùng khi được quyền sửa/hủy toàn bộ cây, **không còn bộ duyệt hoặc người đọc khác** dựa vào liên kết, và mỗi nút chỉ thuộc quyền sở hữu của cây ấy.

Nếu các nhánh dùng chung nút hoặc có chu trình, thuật toán không còn đúng. Không thử “cứ free đến khi chạy xong” với một đồ thị: phải dùng quy tắc quản lý danh tính và sở hữu của đồ thị.

### 7.5. Tại sao không phải lúc nào cũng dùng DFS postorder có stack?

Một cách khác là postorder dùng stack tường minh lưu khung `(node, ready)`, rồi gọi `free(node)` khi khung sẵn sàng. Cách ấy trực quan hơn, có thể có bộ nhớ O(h+1) nhưng cần một vùng stack có thể phát sinh lỗi cấp phát.

Trong tình huống cần **cleanup sau một lần cấp phát thất bại**, việc cấp phát thêm cho chính quá trình cleanup có thể tiếp tục thất bại. Hàm `tree_destroy_iterative` ở trên tránh điểm yếu này bằng cách không xin thêm bộ nhớ, đổi lại chỉ phù hợp khi **được phép phá hủy cây**.

Nếu cần giữ nguyên cấu trúc khi duyệt, rõ ràng không được dùng hàm trên như một iterator.


## 8. Chương trình C hoàn chỉnh: deep clone không đệ quy, lỗi cấp phát và cleanup an toàn

Ta xây dựng phiên bản C đầy đủ với những yêu cầu sau:

1. `tree_clone(source, &result)` không dùng đệ quy, không chia sẻ nút với `source`.
2. Mỗi công việc trong stack lưu `(src, destination_link)`: nút nguồn cần clone và **địa chỉ ô con trỏ đích** để nối nút mới.
3. Nếu `malloc/realloc` thất bại, hàm giải phóng mọi nút clone đã tạo, trả `false` và bảo đảm `result == NULL`.
4. Nếu cây nguồn rỗng, clone thành công và kết quả rỗng.
5. Hàm giải phóng clone/root không cần cấp phát hoặc đệ quy, nên có thể chạy cả ở nhánh thất bại do thiếu bộ nhớ.

### 8.1. Tại sao stack lưu `Node **destination_link`?

Khi tạo nút clone, ta cần biết **nó phải được gắn vào trường nào**: biến `copy_root`, `parent_copy->left` hay `parent_copy->right`.

```text
Job hiện tại:
  source = địa chỉ Node nguồn S
  destination_link = &parent_copy->left

Xử lý:
  fresh = malloc(Node)
  fresh.left = NULL
  fresh.right = NULL
  *destination_link = fresh

Sau đó chuẩn bị:
  (S.right, &fresh.right)
  (S.left,  &fresh.left)
```

Các trường `left/right` nằm **trong những nút clone được cấp phát riêng**, nên con trỏ `&fresh->left` không bị đổi địa chỉ khi **mảng stack chứa Job được `realloc`**. Chỉ nội dung stack tạm bị dời, không phải các nút cây đích.

Điều kiện: một node clone chỉ được giải phóng khi ta đã bỏ/không còn sử dụng mọi Job trỏ vào các trường của nó. Ở nhánh lỗi, ta **giải phóng toàn bộ mảng Job trước**, rồi hủy cây clone dở.

### 8.2. Code C độc lập

```c
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct Node {
    int value;
    struct Node *left;
    struct Node *right;
} Node;

/* Giải phóng cây không đệ quy, O(1) bộ nhớ phụ trợ. */
static void tree_destroy(Node *root) {
    while (root != NULL) {
        if (root->left != NULL) {
            Node *left = root->left;
            root->left = left->right;
            left->right = root;
            root = left;
        } else {
            Node *next = root->right;
            free(root);
            root = next;
        }
    }
}

/* Một công việc tạo bản sao tại một ô liên kết cụ thể. */
typedef struct Job {
    const Node *source;
    Node **destination;
} Job;

/* Push vào dynamic array; thất bại không làm mất mảng cũ. */
static bool push_job(
    Job **jobs,
    size_t *size,
    size_t *capacity,
    Job item
) {
    if (*size == *capacity) {
        size_t new_capacity = 16;

        if (*capacity != 0) {
            if (*capacity > ((size_t)-1) / 2) {
                return false;  /* Tránh tràn khi nhân đôi. */
            }
            new_capacity = *capacity * 2;
        }

        if (new_capacity > ((size_t)-1) / sizeof(Job)) {
            return false;      /* Tránh tràn số byte cấp phát. */
        }

        Job *grown = realloc(*jobs, new_capacity * sizeof(Job));
        if (grown == NULL) {
            return false;
        }

        *jobs = grown;
        *capacity = new_capacity;
    }

    (*jobs)[(*size)++] = item;
    return true;
}

/*
 * Thành công: trả true, *out nhận gốc bản sao độc lập;
 *             nếu source == NULL thì *out == NULL.
 * Thất bại: trả false, *out == NULL; không rò rỉ clone dở.
 *
 * Caller sở hữu cây bản sao thành công và phải tree_destroy(*out).
 * source phải trỏ đến cây còn sống, không chu trình và không chia sẻ nút.
 * out không được alias vùng con trỏ trong cây nguồn.
 */
static bool tree_clone(const Node *source, Node **out) {
    if (out == NULL) return false;
    *out = NULL;

    if (source == NULL) {
        return true;  /* Clone cây rỗng thành cây rỗng. */
    }

    Node *result = NULL;
    Job *jobs = NULL;
    size_t job_size = 0;
    size_t job_capacity = 0;

    if (!push_job(
            &jobs, &job_size, &job_capacity,
            (Job){source, &result})) {
        free(jobs);
        return false;
    }

    while (job_size != 0) {
        Job job = jobs[--job_size];

        Node *fresh = malloc(sizeof *fresh);
        if (fresh == NULL) {
            goto fail;
        }

        fresh->value = job.source->value;
        fresh->left = NULL;
        fresh->right = NULL;

        /* Công bố một nút clone đã khởi tạo đầy đủ. */
        *job.destination = fresh;

        if (job.source->right != NULL &&
            !push_job(
                &jobs, &job_size, &job_capacity,
                (Job){job.source->right, &fresh->right})) {
            goto fail;
        }

        if (job.source->left != NULL &&
            !push_job(
                &jobs, &job_size, &job_capacity,
                (Job){job.source->left, &fresh->left})) {
            goto fail;
        }
    }

    free(jobs);
    *out = result;
    return true;

fail:
    /* Bỏ mọi Job trỏ vào các nút clone, rồi thu hồi clone dở. */
    free(jobs);
    tree_destroy(result);  /* Không xin cấp phát thêm, không đệ quy. */
    return false;
}

/* Dựng cây lệch trái với n nút, không dùng đệ quy. */
static bool make_left_chain(size_t n, Node **out) {
    if (out == NULL) return false;
    *out = NULL;

    Node *root = NULL;

    for (size_t i = 0; i < n; ++i) {
        Node *fresh = malloc(sizeof *fresh);
        if (fresh == NULL) {
            tree_destroy(root);
            return false;
        }

        fresh->value = (int)i; /* Ví dụ n vừa phạm vi int. */
        fresh->left = root;
        fresh->right = NULL;
        root = fresh;
    }

    *out = root;
    return true;
}

int main(void) {
    Node *original = NULL;
    Node *copy = NULL;

    if (!make_left_chain(100000, &original)) {
        fputs("Khong the tao cay nguon\n", stderr);
        return EXIT_FAILURE;
    }

    if (!tree_clone(original, &copy)) {
        fputs("Khong the clone cay\n", stderr);
        tree_destroy(original);
        return EXIT_FAILURE;
    }

    /* Kiểm tra dọc đường trái không cần đệ quy. */
    const Node *a = original;
    const Node *b = copy;
    size_t count = 0;
    bool independent = true;

    while (a != NULL && b != NULL) {
        if (a == b || a->value != b->value ||
            a->right != NULL || b->right != NULL) {
            independent = false;
            break;
        }

        ++count;
        a = a->left;
        b = b->left;
    }

    if (a != NULL || b != NULL) independent = false;

    printf("nodes=%zu independent=%s\n",
           count, independent ? "yes" : "no");

    tree_destroy(copy);
    tree_destroy(original);
    copy = NULL;
    original = NULL;

    return independent && count == 100000
           ? EXIT_SUCCESS
           : EXIT_FAILURE;
}
```

### 8.3. Quy trình khi `malloc/realloc` thất bại

Giả sử stack đang có một số Job và quá trình đã clone được vài nút:

```text
source root ---> [A] ---> ...
result      ---> [A'] ---> [B'] ---> ...
jobs        ---> [(C, &B'.right), (D, &A'.right), ...]

Nếu malloc(Node) hoặc realloc(jobs) thất bại:
    1. Bỏ jobs.
    2. Hủy các Node clone còn reachable từ result.
    3. Trả false với *out vẫn NULL.
    4. Cây source giữ nguyên.
```

Mỗi node mới được **khởi tạo `left=right=NULL` trước khi nối vào clone**. Vì vậy cây clone xây dở vẫn là một cây hợp lệ với các nhánh chưa tạo được biểu diễn bằng `NULL`; `tree_destroy(result)` không phải chạm đến địa chỉ rác.

Đây là dạng **strong failure behavior** cho đầu ra clone: caller không nhận bản sao dở. Bộ nhớ từ các Job không bị rò rỉ vì `free(jobs)` được gọi ở mọi đường thoát sau khi đã có mảng; `realloc` thất bại không tự giải phóng mảng cũ, và `push_job` chỉ đổi con trỏ mảng khi thành công.

### 8.4. Độ phức tạp của chương trình C

- Dựng cây `n` nút: O(n) lần cấp phát, O(n) dung lượng cho cây nguồn.
- Clone: O(n) thời gian tổng trong mô hình cấp phát O(1) và mảng Job tăng dung lượng theo hệ số; O(n) vùng cho clone và O(h+1) vùng phụ cho stack Job đối với cây nhị phân không chia sẻ.
- Hủy: O(n) thời gian, O(1) vùng phụ.
- Kiểm tra hai đường lệch: O(n) thời gian, O(1) vùng phụ.

Với cây lệch một phía, số Job chờ thường rất ít. Đối với cây rộng/cân đối, stack DFS có thể chứa O(h+1) Job trong khi cây clone vẫn cần O(n) nút đích.

**Phạm vi:** đây là code C mô tả vòng đời và xử lý thất bại ở mức cấu trúc. Nó không hỗ trợ payload có tài nguyên lồng nhau hoặc cây nhiều chủ sở hữu; khi mở rộng kiểu nút, cần bổ sung clone/destroy cho từng tài nguyên theo hợp đồng.

## 9. C++: `unique_ptr` và destructor sâu vẫn có thể là vấn đề

C++ cung cấp **RAII** và `std::unique_ptr` để gắn quyền sở hữu nút với vòng đời đối tượng. Ví dụ:

```cpp
#include <memory>

struct Node {
    int value = 0;
    std::unique_ptr<Node> left;
    std::unique_ptr<Node> right;
};
```

`unique_ptr` tránh nhiều lỗi double delete từ sở hữu trùng. Tuy nhiên, khi hủy một `Node`, destructor của hai `unique_ptr` con sẽ lần lượt hủy hai cây con. Trên một chuỗi nút cực sâu, quá trình này có thể tạo **chuỗi destructor sâu**, dù mã người viết không có hàm `free_recursive`.

**RAII đảm bảo có destructor được gọi theo vòng đời; nó không bảo đảm destructor mặc định luôn chịu được cây sâu tùy ý.**

### 9.1. Dọn cây `unique_ptr` bằng chỉnh liên kết không cấp phát

Ta có thể đưa nguyên lý từ C sang C++ bằng các thao tác chuyển sở hữu `std::move`.

```cpp
#include <iostream>
#include <memory>
#include <utility>

/* Cây nhị phân với mỗi nhánh được sở hữu duy nhất. */
struct Node {
    int value = 0;
    std::unique_ptr<Node> left;
    std::unique_ptr<Node> right;
};

/* Hủy toàn cây theo vòng lặp, O(1) vùng phụ. */
void destroy_iterative(std::unique_ptr<Node>& root) noexcept {
    while (root) {
        if (root->left) {
            auto promoted = std::move(root->left);

            root->left = std::move(promoted->right);
            promoted->right = std::move(root);
            root = std::move(promoted);
        } else {
            auto next = std::move(root->right);

            // Hai con của nút hiện tại đều rỗng ở thời điểm reset.
            root.reset();
            root = std::move(next);
        }
    }
}

/* Chủ sở hữu toàn cây: luôn dùng destructor lặp. */
class Tree {
public:
    std::unique_ptr<Node> root;

    Tree() = default;
    Tree(const Tree&) = delete;
    Tree& operator=(const Tree&) = delete;

    ~Tree() noexcept {
        destroy_iterative(root);
    }
};

int main() {
    Tree tree;

    for (int i = 0; i < 100000; ++i) {
        auto fresh = std::make_unique<Node>();
        fresh->value = i;
        fresh->left = std::move(tree.root);
        tree.root = std::move(fresh);
    }

    size_t count = 0;
    for (const Node *p = tree.root.get();
         p != nullptr; p = p->left.get()) {
        ++count;
    }

    std::cout << count << "\n";  // 100000

    // Khi Tree rời scope, ~Tree gọi destroy_iterative.
    // Không phụ thuộc lời gọi destructor lồng theo độ sâu cây.
}
```

### 9.2. Vì sao cần `next` trước khi `root.reset()`?

Ở nhánh không còn con trái:

```cpp
auto next = std::move(root->right);
root.reset();
root = std::move(next);
```

`next` nhận quyền sở hữu cây con phải **trước** khi nút gốc bị hủy. Tại thời điểm `reset`, cả `left` lẫn `right` của nút cũ đều rỗng, nên hủy nó **không kéo theo destructor sâu của cây con**. Sau đó vòng lặp tiếp tục trên `next`.

Không nên viết ngay `root = std::move(root->right)` rồi giả định mọi thứ an toàn: biểu thức nguồn tham chiếu tới một trường bên trong đối tượng mà đích có thể hủy trong quá trình gán, làm lý luận lifetime/aliasing phức tạp hoặc sai.

### 9.3. Những giới hạn của ví dụ

- `destroy_iterative` chỉ đúng với cây có **sở hữu duy nhất, không chu trình**, và giả định destructor của payload không ném ngoại lệ.
- Liên kết có thể bị xoay trong khi giải phóng; không được còn người đọc hoặc iterator dựa vào chúng.
- Mỗi phép `std::move` của `unique_ptr` là thao tác chuyển quyền sở hữu, không sao chép node.
- Nếu để `std::unique_ptr<Node> root` trần ngoài lớp `Tree` rồi nó tự bị hủy theo cơ chế mặc định, vẫn có thể gặp chuỗi destructor sâu. Dùng một wrapper có destructor lặp giúp bao phủ cả lúc đối tượng rời scope sau ngoại lệ.
- Nếu kiểu `Node` có thêm tài nguyên hoặc callback destructor phức tạp, cần rà soát hợp đồng hủy và khả năng ngoại lệ của chúng; mã minh họa dùng payload `int`.

### 9.4. Sao chép một cây `unique_ptr`

`unique_ptr` **không copy được**. Đây là lợi ích của mô hình sở hữu duy nhất: trình biên dịch không cho phép vô tình tạo hai owner từ một con trỏ.

Muốn clone, phải tạo các `Node` mới và clone từng nhánh, dùng stack/queue tường minh hoặc một hàm clone đệ quy khi chiều cao được kiểm soát. Nếu clone một cây rất sâu có thể ném ngoại lệ cấp phát, **hủy clone dở cũng cần được thiết kế theo kiểu lặp**, chứ không chỉ sửa mỗi thuật toán clone.

Một hướng chắc chắn là tạo clone trong một đối tượng `Tree` có destructor lặp, rồi **chuyển quyền sở hữu** tới kết quả chỉ sau khi xây xong. Nếu phát sinh ngoại lệ, wrapper tạm tự dọn các nút đã tạo bằng destructor lặp.

## 10. Python có GC vẫn cần quản lý độ sâu và retention

Python không cho người dùng tự gọi `free(node)` đối với những đối tượng Python thông thường. Bộ nhớ của chúng do runtime quản lý, nhưng điều đó **không đồng nghĩa** mọi thao tác trên cây sâu đều an toàn hoặc mọi nút được thu hồi ngay khi ta bỏ tên `root`.

### 10.1. Bỏ tham chiếu không phải lệnh dọn cây lập tức

```python
root = make_left_chain(100_000)
alias = root
root = None

# alias vẫn giữ đường tham chiếu tới gốc,
# nên cây chưa hết khả năng truy cập.
```

Các generator tạm dừng, stack, cache hoặc biến khác cũng có thể giữ một phần cây sống lâu hơn nhu cầu nghiệp vụ. Việc GC/allocator trả RAM cho hệ điều hành xảy ra theo cơ chế riêng của runtime, không phải ngay lập tức chỉ vì gán `None`.

### 10.2. Tách các liên kết bằng vòng lặp khi cần chủ động thu dọn

Nếu ứng dụng muốn **tháo cây thành các nút rời** mà không dùng đệ quy, ví dụ trước khi bỏ các tham chiếu lớn, có thể làm:

```python
def detach_tree_iterative(root: Node | None) -> None:
    """Phá các liên kết trái/phải; chỉ dùng với cây mà ta được quyền sửa."""
    if root is None:
        return

    stack = [root]

    while stack:
        node = stack.pop()

        left = node.left
        right = node.right

        # Đọc các con trước khi tháo liên kết.
        node.left = None
        node.right = None

        if right is not None:
            stack.append(right)
        if left is not None:
            stack.append(left)


root = make_left_chain(100_000)
detach_tree_iterative(root)
assert root is not None
assert root.left is None and root.right is None
```

Hàm này **không gọi free trên đối tượng Python**; nó chỉ bỏ các liên kết để những nút không còn được giữ bởi nơi khác có thể đủ điều kiện thu hồi. Nếu có alias tới một nút cũ, nút ấy có thể vẫn sống. Nếu nhiều luồng/tác vụ còn cần cây, việc tháo liên kết như vậy là phá hỏng dữ liệu của họ.

Với cây nhị phân sở hữu riêng, stack dùng O(h+1) vùng phụ, thời gian O(n). Trong ứng dụng chỉ cần bỏ cây và runtime có cơ chế thu hồi phù hợp, có thể không cần thao tác này; đây là lựa chọn **có chủ đích để quản lý liên kết**, không phải quy trình bắt buộc của mọi chương trình Python.

## 11. Clone bằng BFS queue: khi nào nên dùng?

Thay vì DFS stack, có thể clone cây bằng **BFS queue**, lưu cặp `(source_node, clone_node)`. Các nút ở tầng nông được clone trước.

```python
from collections import deque


def clone_tree_bfs(root: Node | None) -> Node | None:
    if root is None:
        return None

    copy_root = Node(root.value)
    queue = deque([(root, copy_root)])

    while queue:
        source, target = queue.popleft()

        if source.left is not None:
            target.left = Node(source.left.value)
            queue.append((source.left, target.left))

        if source.right is not None:
            target.right = Node(source.right.value)
            queue.append((source.right, target.right))

    return copy_root
```

Độ phức tạp:

- O(n) thời gian vì mỗi nút được clone và mở rộng một lần.
- O(n) bộ nhớ cho cây clone.
- O(w) bộ nhớ phụ trợ cho queue BFS trên cây nhị phân, với `w` là độ rộng tầng lớn nhất.

Với **cây lệch rất sâu** (w=1, h≈n), clone BFS dùng queue O(1), trong khi một biến thể DFS dùng stack cũng có thể nhỏ tùy dạng nhánh. Với **cây cân đối rất rộng**, DFS stack O(log n) thường ít bộ nhớ phụ trợ hơn BFS queue O(n).

**Chọn BFS khi cần xử lý theo tầng**, chẳng hạn gắn metadata độ sâu cho nút clone. Chọn DFS khi ưu tiên lưu ít mục chờ trên cây rộng, hoặc khi muốn dùng cùng kiểu stack cho các phép duyệt/lọc khác.


## 12. Lỗi giữa chừng, bất biến mạnh và thứ tự dọn tài nguyên

Các thao tác clone thường có nhiều điểm có thể thất bại: cấp phát nút, cấp phát payload, mở rộng stack công việc, tạo liên kết phụ hoặc sao chép dữ liệu có thể ném ngoại lệ.

### 12.1. Bất biến của một clone đang xây

Một thiết kế thuận tiện để cleanup có các bất biến:

1. Gốc bản sao `result` hoặc bằng `NULL`, hoặc dẫn tới **một cây clone dở nhưng hợp lệ**.
2. Mọi nút clone được gắn vào cây đích đều đã khởi tạo đầy đủ các trường con trỏ, mặc định con vắng bằng `NULL`.
3. Không nút clone nào có `left/right` trỏ về cây nguồn nếu yêu cầu là bản sao sâu độc lập.
4. Những nút clone mới tạo được nối vào **đúng một nơi**, để hủy cây đích có thể tới và dọn tất cả chúng.
5. Khi lỗi, bỏ mọi Job/cursor tạm rồi hủy cây clone dở, không công bố nó cho caller như kết quả thành công.

Những quy tắc này cho phép rollback toàn bộ thao tác clone mà không cần ghi một danh sách riêng tất cả con trỏ cần `free`.

### 12.2. Mất quyền sở hữu một nút mới tạo

```c
/* Ví dụ sai về sở hữu (đoạn trong một hàm, chưa đầy đủ): */
Node *fresh = malloc(sizeof *fresh);
if (fresh == NULL) return false;
fresh->left = NULL;
fresh->right = NULL;

/* Nếu thất bại trước khi fresh được gắn vào cây
   mà không gọi free(fresh), nút này sẽ rò rỉ. */
```

Trong mã thực tế, mỗi bước cần có **một đường thu hồi rõ ràng**:

- Khi nút còn là biến tạm **chưa gắn**: biến tạm sở hữu và phải `free` nếu có lỗi.
- Sau khi gắn thành công: chủ sở hữu cây đích chịu trách nhiệm cleanup.
- Không để cả hai bên cùng `free` một nút.

Với C++, `std::unique_ptr<Node> fresh` có thể giúp quản lý vùng tạm trước khi chuyển quyền sở hữu vào cây đích.

### 12.3. Clone payload cần hàm sao chép/hủy phù hợp

Nếu nút chứa một con trỏ tới chuỗi mà mỗi node sở hữu riêng, `clone_node` phải cấp phát và copy chuỗi; destructor phải `free` chuỗi trước khi `free` node.

```c
/* Ý tưởng khi node sở hữu payload chuỗi động:
   - clone payload: allocate một buffer riêng, copy nội dung;
   - nếu allocate thất bại: trả lỗi, cleanup nút mới;
   - destroy payload: free(node->name) đúng một lần;
   - sau đó mới free(node).
*/
```

Với đồ thị đối tượng có quan hệ chia sẻ, không thể giải quyết ownership bằng mỗi câu “gọi free cho mọi trường con trỏ”. Cần phân biệt **con trỏ sở hữu** và **con trỏ mượn**, kể cả khi cùng kiểu C.

### 12.4. Phân biệt các mức bảo đảm khi thao tác thất bại

| Bảo đảm | Ý nghĩa |
| --- | --- |
| **Không rò rỉ tài nguyên** | Những tài nguyên do thao tác tạo ra được thu hồi hoặc chuyển giao rõ ràng |
| **Basic guarantee** | Đối tượng còn ở trạng thái hợp lệ, không rò rỉ, nhưng có thể đã bị thay đổi |
| **Strong guarantee** | Nếu thất bại, trạng thái quan sát được của đối tượng/bộ phận đầu ra giống trước thao tác |
| **No-throw cleanup** | Đường dọn không gây thêm lỗi cần xử lý theo hợp đồng |

Trong ví dụ `tree_clone` C, nguồn không bị sửa; nếu clone thất bại, `*out` vẫn `NULL` và mọi nút clone dở bị giải phóng. Đây là hành vi đầu ra dạng “thành công hoặc không nhận clone”; nó không tự phát biểu cho các tác dụng phụ khác như logging hoặc cấp phát nội bộ của allocator.

Với code C++ sử dụng `std::unique_ptr`, chú ý destructor/move phải phù hợp với bảo đảm mong muốn. Một destructor có thể ném ngoại lệ hoặc phải đệ quy sâu sẽ khiến cleanup khó dự đoán hơn, dù mã cấp phát dùng RAII.

## 13. Cây có chia sẻ nút, chu trình và con trỏ cha: đổi bài toán

Một cây sở hữu riêng được nhận diện bởi **mỗi nút khác gốc chỉ có một cha và chỉ một đường từ gốc tới nút**. Nếu điều kiện này không đúng, thuật toán cần mô hình mới.

### 13.1. Một nút được chia sẻ bởi hai nhánh

```text
          A
         / \
        B   C
         \ /
          D
```

Đây là một **DAG** (nếu không có chu trình), không còn là cây nhị phân theo giả định sở hữu riêng. Nếu dùng clone DFS không có bảng ánh xạ, nút D có thể được clone **hai lần** thành D1/D2. Điều đó biến một đồ thị chia sẻ thành một cây không còn chia sẻ: giá trị nhìn có thể giống, nhưng **danh tính và quan hệ aliasing đã đổi**.

Nếu dùng destructor của cây sở hữu riêng, một nút D được duyệt từ cả B lẫn C có thể bị giải phóng **hai lần** hoặc bị đọc sau khi đã free.

### 13.2. Clone đồ thị bảo toàn chia sẻ

Nếu yêu cầu là **bảo toàn danh tính/chia sẻ** của DAG hay đồ thị, cần một bảng ánh xạ:

```text
mapping[old_node] = corresponding_new_node

CLONE_GRAPH(root):
    nếu root rỗng: trả rỗng
    tạo clone_root
    mapping[root] = clone_root
    worklist = [root]

    while còn nút nguồn trong worklist:
        old = pop(worklist)
        new = mapping[old]

        với mỗi cạnh old -> child:
            nếu child chưa có trong mapping:
                tạo cloned_child
                mapping[child] = cloned_child
                push(worklist, child)
            nối new -> mapping[child]
```

Điểm quan trọng là **đưa nút mới vào mapping trước khi đi theo các cạnh con của nó**. Nhờ thế, nếu có chu trình trỏ lại một nút đã phát hiện, thuật toán dùng bản sao đang có thay vì tạo thêm vô hạn.

Với `V` đối tượng và `E` liên kết, clone đồ thị bằng worklist và bảng băm thường O(V+E) **thời gian kỳ vọng** và O(V+E) bộ nhớ cho đối tượng/cạnh đầu ra, thêm O(V) bộ nhớ bảng ánh xạ/worklist (bỏ qua metadata nội bộ), nếu thao tác hash chi phí kỳ vọng O(1).

**Cleanup đồ thị phải theo hệ thống sở hữu riêng** (ví dụ kho quản lý mỗi đối tượng một lần, reference counting phù hợp hoặc GC), không gọi `tree_destroy` kiểu cây trên từng cạnh để cố đi hết đồ thị.

### 13.3. Nếu nút có con trỏ cha

Một nút có thể lưu:

```c
typedef struct ParentNode {
    int value;
    struct ParentNode *parent; /* Mượn cha. */
    struct ParentNode *left;   /* Chủ sở hữu nhánh theo hợp đồng. */
    struct ParentNode *right;
} ParentNode;
```

Khi clone, `new_node->parent` phải trỏ tới **nút cha của bản sao**, không phải `old_node->parent` của cây nguồn. Copy struct nguyên xi sẽ tạo liên kết ngược sang cây gốc và phá tính độc lập.

Khi hủy cây, chỉ đi theo các liên kết **sở hữu** `left/right`. Nếu đi luôn theo `parent`, traversal có thể tạo chu trình cha–con và không dừng. Với C++ và `unique_ptr`, con trỏ cha thường là **con trỏ mượn** hoặc weak reference theo thiết kế, tránh tạo hai chủ sở hữu mạnh cho cùng đường.

### 13.4. Cây có nút sentinel/NIL

Một số cây cân bằng có một nút `NIL` dùng chung cho nhiều liên kết con vắng mặt. Đó không phải `NULL` thông thường. Không được lấy hàm `tree_destroy` giả định “mọi `left/right` khác NULL đều là nút dữ liệu do cây sở hữu” rồi áp dụng nguyên xi.

Phải xây một hàm hủy đúng theo **bất biến của cây sentinel**: dừng tại `NIL`, không nhân bản nó như nút dữ liệu cho mọi nhánh nếu không mong muốn, và giải phóng sentinel theo **một** chủ sở hữu thích hợp.

## 14. Sao chép khác chuyển quyền sở hữu và khác biến đổi tại chỗ

Cần tách ba thao tác có cùng vẻ ngoài nhưng chi phí/ý nghĩa khác nhau.

### 14.1. Deep clone

Tạo O(n) nút mới và giữ nguyên cây nguồn. Có hai cây độc lập về **liên kết và node identity**. Thời gian O(n), bộ nhớ đầu ra O(n); nếu payload có tài nguyên riêng, thêm chi phí clone payload.

### 14.2. Move/transfer

Chuyển **quyền sở hữu** cây gốc từ chủ A sang chủ B mà không tạo lại mỗi nút. Ví dụ C++:

```cpp
std::unique_ptr<Node> from = /* ... */;
std::unique_ptr<Node> to = std::move(from);

// to nhận ownership; from trở thành rỗng.
// Không tạo n Node mới và không biến đây thành deep clone.
```

Lưu ý đoạn trên chỉ minh họa cú pháp khi đã có kiểu `Node` thích hợp. Nếu `Node` là cấu trúc có cây con `unique_ptr`, chủ mới vẫn phải quản lý **destructor sâu** nếu cây rất lệch.

### 14.3. Biến đổi tại chỗ

Ví dụ đảo hai cây con của mỗi nút:

```python
def mirror_in_place(root: Node | None) -> None:
    if root is None:
        return

    stack = [root]
    while stack:
        node = stack.pop()
        node.left, node.right = node.right, node.left

        if node.left is not None:
            stack.append(node.left)
        if node.right is not None:
            stack.append(node.right)
```

Thuật toán không tạo clone O(n); nó thay **chính cây đang có**, làm các đường duyệt theo trái/phải khác trước. Một iterator/đường gốc–đích được tính trước phép mirror có thể không còn phản ánh thứ tự/cấu trúc theo yêu cầu. Nếu cần cả **cây gốc lẫn cây mirror**, nên clone trước rồi mirror trên bản sao.

### 14.4. Persistent trees và copy-on-write

Đối với cây bất biến, một bản cập nhật đôi khi chỉ cần **copy những nút trên đường từ gốc tới vị trí đổi** và chia sẻ các cây con không bị ảnh hưởng. Trên cây cân bằng, số nút copy theo đường có thể O(log n); trên cây lệch có thể O(n). Nhưng cần:

- Không sửa các nhánh dùng chung bằng alias có quyền ghi.
- Quản lý lifetime của mọi phiên bản.
- Xác định dữ liệu payload có bất biến hay được copy an toàn không.
- Đánh giá chi phí metadata sở hữu và hệ quả cho bộ nhớ đệm CPU.

Không nên gọi cách này là “deep clone toàn bộ độc lập” nếu mục tiêu vẫn là **structural sharing**.

## 15. Tóm tắt độ phức tạp và lựa chọn phù hợp

| Công việc | Thời gian điển hình | Bộ nhớ phụ trợ ngoài nút đầu ra | Điều kiện/ghi chú |
| --- | --- | --- | --- |
| Clone đệ quy | O(n) | O(h+1) call stack | Dễ đọc, nhưng cây cực sâu có thể tràn stack |
| Clone DFS stack | O(n) | O(h+1) stack | Clone tạo thêm O(n) nút kết quả |
| Clone BFS queue | O(n) | O(w) queue | Clone tạo thêm O(n) nút kết quả |
| Preorder lặp | O(n) | O(h+1) stack tối đa | Với cây một đường, stack có thể O(1) thực tế |
| Inorder lặp | O(n) | O(h+1) stack | Không cần kết quả O(n) nếu xử lý streaming |
| Postorder lặp có phase | O(n) | O(h+1) stack | Trì hoãn nút cha đến sau hai con |
| Level-order BFS | O(n) | O(w) queue | Cây rộng có thể cần Θ(n) queue |
| Hủy đệ quy hậu tự | O(n) | O(h+1) call stack | Không phù hợp độ sâu rất lớn |
| Hủy theo stack postorder | O(n) | O(h+1) stack | Cần stack đủ dung lượng, có thể gặp lỗi cấp phát |
| Hủy bằng chỉnh liên kết | O(n) | **O(1)** | Phá liên kết, chỉ áp dụng cho cây sở hữu riêng |
| Clone đồ thị có chia sẻ | O(V+E) kỳ vọng | O(V) mapping/worklist ngoài kết quả | Phải giữ đúng danh tính và chu trình |
| Mirror tại chỗ | O(n) | O(h+1) stack | Không clone; làm thay đổi cây nguồn |
| Move `unique_ptr` gốc | O(1) | O(1) | Chỉ chuyển quyền sở hữu, không copy nút |

Các bậc thời gian dùng mô hình **truy cập liên kết và cấp phát/giải phóng mỗi nút là thao tác hằng số điển hình**; allocator thực tế, destructor payload và I/O có thể có chi phí khác. Nếu kết quả duyệt được lưu lại thành danh sách `n` mục, cần cộng **O(n) bộ nhớ kết quả**, độc lập với stack/queue.

### 15.1. Cây rộng và cây sâu đưa ra lựa chọn trái ngược

- **Rất sâu nhưng hẹp:** DFS đệ quy nguy hiểm; BFS queue chỉ có thể O(1) trên đường đơn, còn DFS stack tường minh tránh cạn call stack. Hủy không cấp phát bằng chỉnh liên kết đặc biệt phù hợp.
- **Rộng nhưng cân đối:** DFS stack O(log n) có lợi về bộ nhớ phụ trợ; BFS queue có thể chiếm O(n).
- **Nhiều truy vấn duyệt/sao chép:** nên cân nhắc immutable snapshot/persistent structure hoặc cache có giới hạn thay vì clone lại cả cây cho mỗi thao tác không cần thiết.
- **Dữ liệu không bảo đảm là cây thật:** cần kiểm tra cấu trúc và chọn thuật toán đồ thị có visited/ownership phù hợp trước khi clone/hủy.

## 16. Quy trình thiết kế khi gặp cây có thể sâu bất thường

1. **Xác định đầu vào:** có thật là cây hữu hạn, không chu trình và không shared child không?
2. **Xác định ownership:** ai sở hữu root, nút con, payload, sentinel, parent pointer?
3. **Đo/giới hạn độ sâu:** chiều cao có thể tăng theo đầu vào do người dùng tạo hoặc do cây lệch không?
4. **Chọn mô hình truy cập:** DFS stack O(h), BFS queue O(w), hoặc thuật toán chuyên biệt không cấp phát thêm cho cleanup.
5. **Chọn copy hay sharing:** cần bản sao độc lập hay chỉ cần phiên bản bất biến chia sẻ nhánh?
6. **Lập hợp đồng lỗi:** nếu cấp phát ở nút thứ `k` thất bại, những nút clone trước đó sẽ được thu hồi bằng cách nào?
7. **Bảo đảm không đọc sau hủy:** mọi con trỏ tiếp tục duyệt phải được lưu hoặc xử lý **trước** khi hủy nút hiện tại.
8. **Xử lý dừng sớm:** generator hoặc iterator còn giữ nút, task đang pending, bộ nhớ kết quả có thể tồn tại tới khi nào?
9. **Xác định tính đồng thời:** có thread/tác vụ khác sửa cây hoặc giữ view không? Có cần snapshot hoặc khóa?
10. **Kiểm tra độ phức tạp toàn vòng đời:** không chỉ O(n) cho clone mà cả O(n) cho cleanup, bộ nhớ clone O(n) và peak memory khi giữ cả nguồn lẫn đích.

Trong hệ thống có đầu vào không đáng tin cậy, việc giới hạn chiều cao và kích thước cây là một biện pháp **chống cạn tài nguyên**. Dùng thuật toán lặp giúp tránh call-stack overflow, nhưng không tự ngăn một đầu vào tạo hàng tỉ nút làm hết heap.

## 17. Kiểm thử cây sâu và thuộc tính của bản sao

### 17.1. Những trường hợp cần có

1. **Cây rỗng:** clone thành công với gốc rỗng; hủy rỗng không gây lỗi.
2. **Một nút:** bản sao có cùng giá trị nhưng khác identity.
3. **Cây đầy/cân đối:** tất cả nhánh và thứ tự trái/phải được bảo toàn.
4. **Cây lệch trái rất sâu:** clone, duyệt, giải phóng đều không phụ thuộc đệ quy.
5. **Cây lệch phải rất sâu:** kiểm tra tương tự, đặc biệt bộ duyệt inorder/postorder.
6. **Nhiều mức dữ liệu trùng nhau:** clone không gộp nút chỉ vì payload giống.
7. **Payload = 0 hoặc âm:** không nhầm với con rỗng.
8. **Clone rồi sửa một nút clone:** nguồn không đổi, và ngược lại.
9. **Clone thất bại ở lần malloc/realloc thứ k:** không rò rỉ nút đích đã cấp, nguồn nguyên vẹn và caller nhận trạng thái lỗi.
10. **Hủy bản sao rồi nguồn:** không double free hoặc use-after-free.
11. **Cây có payload cấp phát riêng:** clone và destructor xử lý đúng quyền sở hữu payload.
12. **Tree sử dụng `unique_ptr`:** destructor của wrapper xử lý cây cực sâu và cả đường ngoại lệ.
13. **Có parent pointer:** sau clone, parent của nút clone trỏ về nút clone cha, không phải cha nguồn.
14. **DAG/shared subtree:** nhận diện đầu vào không phù hợp với clone/destroy kiểu cây.
15. **Chu trình:** không chạy trực tiếp thuật toán cây gây lặp vô hạn; xử lý dưới hợp đồng đồ thị.
16. **Cây có sentinel `NIL`:** hủy/duyệt theo đúng điều kiện dừng sentinel.
17. **Generator duyệt dừng sớm:** còn tham chiếu tới nút chờ hay không, có cleanup cần thiết không?
18. **Biến đổi khi đang duyệt:** xác minh chính sách invalidation/khóa/snapshot, không dựa vào “không crash”.

### 17.2. Kiểm tra hình dạng và độc lập mà không dùng đệ quy

Thay vì so sánh đối tượng node bằng hàm `__eq__` đệ quy, ta có thể đi qua hai cây **song song** với stack các cặp:

```python
def assert_independent_clone(a: Node | None, b: Node | None) -> None:
    stack = [(a, b)]

    while stack:
        original, copied = stack.pop()

        if original is None or copied is None:
            assert original is None and copied is None
            continue

        assert original is not copied
        assert original.value == copied.value

        stack.append((original.left, copied.left))
        stack.append((original.right, copied.right))


root = Node(5, Node(3), Node(8))
cloned = clone_tree_iterative(root)
assert_independent_clone(root, cloned)
```

Hàm kiểm thử trên giả định **hai đầu vào thật sự là cây**. Với shared subtree hoặc chu trình, cần thêm bảng đối chiếu danh tính/visited để không lặp hoặc kiểm tra aliasing sai; chỉ xác minh một cặp giá trị mỗi lần chưa đủ chứng minh một clone đồ thị bảo toàn quan hệ chia sẻ.

### 17.3. Kiểm thử đối chiếu các thứ tự duyệt

```python
root = Node(8, Node(3, Node(1), Node(6)), Node(10))

assert list(preorder_iter(root)) == [8, 3, 1, 6, 10]
assert list(inorder_iter(root)) == [1, 3, 6, 8, 10]
assert list(postorder_iter(root)) == [1, 6, 3, 10, 8]
assert list(levelorder_iter(root)) == [8, 3, 10, 1, 6]

copy = clone_tree_iterative(root)
assert list(preorder_iter(copy)) == list(preorder_iter(root))
assert list(inorder_iter(copy)) == list(inorder_iter(root))
assert list(postorder_iter(copy)) == list(postorder_iter(root))
assert list(levelorder_iter(copy)) == list(levelorder_iter(root))
```

Những kiểm tra này xác minh giá trị và thứ tự, nhưng **chưa thay thế** kiểm tra identity tách biệt hay test failure injection. Hai cây khác hình dạng có thể trùng một số dãy duyệt; khi cần bảo toàn chính xác hình dạng, phải so sánh từng cặp liên kết như hàm `assert_independent_clone`.

## 18. Bài tập có lời giải

### Bài 1. Vì sao cây sâu gây vấn đề?

Một cây nhị phân lệch trái có 100.000 nút. Hàm duyệt đệ quy O(n) thời gian có chắc chạy an toàn không?

**Lời giải:** Không. Độ sâu lời gọi có thể 100.000, gây `RecursionError` ở Python hoặc cạn call stack trong C/C++. O(n) thời gian chỉ mô tả số công việc; cần chuyển sang vòng lặp và quản lý stack/queue tường minh hoặc giới hạn độ sâu đầu vào.

### Bài 2. So sánh gán con trỏ và clone

```c
Node *other = root;
```

Lệnh trên tạo mấy nút cây mới?

**Lời giải:** Không tạo nút nào. `other` và `root` cùng trỏ tới cây gốc. Giải phóng cây qua một alias có thể khiến alias còn lại bị treo.

### Bài 3. Sao chép struct C nông

```c
Node *copy = malloc(sizeof *copy);
/* Giả sử cấp phát thành công. */
*copy = *root;
```

Nếu cây gốc có con trái, `copy->left` trỏ đến đâu?

**Lời giải:** Trỏ tới **cùng đối tượng nút con trái** với `root->left`, vì phép gán chỉ copy giá trị con trỏ. Không phải deep clone; nếu mỗi gốc được hủy như cây riêng, có thể double free.

### Bài 4. Deep clone phải bảo toàn gì?

Một hàm clone đã giữ nguyên mọi giá trị nhưng đảo vị trí `left` và `right` của một nút. Đây có phải bản sao cấu trúc đúng không?

**Lời giải:** Không. Deep clone cấu trúc yêu cầu mỗi liên kết trái/phải trong clone tương ứng đúng với liên kết ở nguồn, đồng thời node identity là mới. Chỉ cùng tập giá trị không đủ.

### Bài 5. Cây một đường

Cây lệch trái có `n` nút. Chiều cao `h` và độ rộng `w` là bao nhiêu?

**Lời giải:** `h=n-1` theo số cạnh; `w=1` với `n>0`. Stack đệ quy có thể O(n), BFS queue O(1).

### Bài 6. DFS stack và BFS queue khi clone

Với cây nhị phân cân đối có `n` nút, chi phí bộ nhớ phụ trợ của clone DFS/BFS khác nhau thế nào?

**Lời giải:** DFS stack thường O(h+1)=O(log n), BFS queue O(w) có thể Θ(n). Cả hai clone toàn bộ cây đều cần thêm O(n) bộ nhớ nút **đầu ra**.

### Bài 7. Preorder không đệ quy

Muốn preorder từ trái sang phải bằng stack LIFO, cần push con nào trước?

**Lời giải:** Push **con phải trước, con trái sau**, để stack pop con trái trước. Mỗi nút được xử lý một lần.

### Bài 8. Inorder trên cây sâu

Vì sao inorder dùng stack tường minh cần giữ các nút tổ tiên?

**Lời giải:** Sau khi đi sâu xuống nhánh trái và thăm một nút, thuật toán còn phải quay lại tổ tiên chưa xuất rồi mới qua cây con phải. Stack ghi nhớ đường tổ tiên ấy mà không dùng call stack đệ quy.

### Bài 9. Postorder cần đánh dấu giai đoạn

Tại sao trong postorder không thể pop nút rồi luôn xuất ngay?

**Lời giải:** Vì postorder yêu cầu **hai cây con được xử lý trước cha**. Dùng khung `(node, ready)` hoặc thông tin tương đương để trì hoãn việc xuất cha cho tới khi các khung con đã hoàn tất.

### Bài 10. BFS có luôn ít bộ nhớ hơn DFS không?

**Lời giải:** Không. Trên cây lệch một đường, BFS queue O(1) có thể rất ít bộ nhớ; trên cây cân đối rộng, queue có thể Θ(n) trong khi DFS stack O(log n). Cần xét `h` và `w`.

### Bài 11. Dọn cây sau malloc thất bại

Một hàm clone đã tạo 20 nút rồi `malloc` thất bại. Vì sao gọi hàm hủy đệ quy có thể vẫn nguy hiểm nếu cây nguồn cực sâu?

**Lời giải:** Clone dở có thể chứa một đường rất sâu, nên hủy đệ quy vẫn có thể cạn call stack. Dùng cleanup lặp được thiết kế trước, tốt nhất không cần cấp phát thêm trong nhánh thiếu bộ nhớ.

### Bài 12. Nối nút clone đúng thời điểm

Vì sao nên khởi tạo `fresh->left = fresh->right = NULL` trước khi nối `fresh` vào cây clone?

**Lời giải:** Để cây clone dở vẫn có liên kết hợp lệ nếu thao tác sau thất bại. Cleanup chỉ đi qua các nút đã tạo và gặp `NULL` ở những nhánh chưa tạo, không đọc địa chỉ rác.

### Bài 13. Dọn bằng phép xoay có giữ hình dạng không?

Hàm `tree_destroy_iterative` dùng đổi liên kết khi nút có con trái. Có được dùng nó để duyệt rồi tiếp tục sử dụng cây không?

**Lời giải:** Không. Hàm thay đổi cấu trúc và giải phóng các nút; nó chỉ phù hợp khi được phép tiêu thụ/hủy cây. Không dùng như bộ duyệt bảo toàn cây.

### Bài 14. Use-after-free

```c
Node *next = root->right;
free(root);
printf("%d", root->value);
```

Dòng nào sai?

**Lời giải:** Đọc `root->value` sau `free(root)` là use-after-free. Có thể dùng `next` đã lưu để tiếp tục nhưng không đọc/ghi vùng của `root` đã hủy.

### Bài 15. `unique_ptr` có loại bỏ mọi lỗi độ sâu không?

Một cây C++ gồm 200.000 `Node` nối bằng `unique_ptr<Node> left`. Khi `root` rời scope và dùng destructor mặc định, có chắc không gặp stack overflow?

**Lời giải:** Không. Destructor của nút có thể kích hoạt destructor con sâu theo chuỗi. Cần một quy trình hủy lặp hoặc wrapper với destructor hủy lặp nếu chiều cao không giới hạn.

### Bài 16. Move khác clone

```cpp
auto to = std::move(from);
```

Với `from` là `unique_ptr<Node>`, thao tác này tạo bao nhiêu nút cây mới?

**Lời giải:** Không tạo nút mới. `to` nhận ownership của gốc cũ, `from` trở thành rỗng. Muốn hai cây độc lập phải clone.

### Bài 17. Python có GC thì cần detach không?

Một ứng dụng đã xong với cây Python; cây chỉ có các nút `Node` bình thường và không có alias khác. Có bắt buộc duyệt toàn cây gọi `detach_tree_iterative` trước khi bỏ `root` không?

**Lời giải:** Không bắt buộc. Python quản lý vòng đời đối tượng theo runtime. Detach chủ động có thể cần trong thiết kế nhất định nhưng làm thay đổi cây và không cam kết RSS giảm tức thì. Phải xem liệu còn generator, cache hoặc alias giữ nút không.

### Bài 18. Cây con được chia sẻ

A có hai nhánh dẫn tới cùng nút D. Clone không dùng mapping sẽ xử lý D thế nào?

**Lời giải:** Có thể tạo hai bản sao D1/D2 và **làm mất quan hệ chia sẻ**. Đây là DAG chứ không phải cây sở hữu riêng. Muốn giữ aliasing cần mapping `old_node -> cloned_node` và xử lý visited; destructor cũng phải quản lý mỗi nút đúng một lần.

### Bài 19. Nút có trường parent

Trong deep clone của cây có `parent`, có được giữ `copy->parent = original->parent` không?

**Lời giải:** Không nếu mục tiêu là clone độc lập. Trường `parent` của clone phải trỏ đến **nút cha clone**, không phải nút nguồn. Parent thường là liên kết mượn, không phải owner của cha.

### Bài 20. Cây có `NIL` sentinel

Một cây đỏ–đen dùng một node `NIL` cho mọi lá vắng. Có được `free(NIL)` mỗi khi gặp một liên kết con tới NIL không?

**Lời giải:** Không. Sentinel là nút kỹ thuật thường được chia sẻ, không phải nút dữ liệu mới ở mỗi nhánh. Phải dừng traversal tại NIL và hủy sentinel đúng một lần theo chính sách sở hữu.

### Bài 21. Sao chép payload mutable

Mỗi node giữ một con trỏ `name` tới chuỗi động do node sở hữu. Clone chỉ tạo node mới và copy địa chỉ `name`. Vì sao chưa đạt deep clone độc lập?

**Lời giải:** Hai node cùng trỏ tới chuỗi cũ, nên sửa chuỗi ở một bản có thể ảnh hưởng bản kia và cùng `free` sẽ có nguy cơ double free. Phải cấp chuỗi mới và copy nội dung, hoặc đổi chính sách ownership/immutability có chủ đích.

### Bài 22. Ngân sách bộ nhớ khi clone

Cây gốc có `n` nút, mỗi node dùng `s` byte (bỏ qua padding/allocator). Trong giai đoạn clone sâu thành công, số byte riêng cho các nút gốc và clone xấp xỉ bao nhiêu?

**Lời giải:** Khoảng `2ns` byte chỉ cho hai bộ nút, chưa tính allocator overhead, stack Job O(h), payload và các dữ liệu khác. Peak memory có thể cao hơn khi mảng stack tự `realloc` hoặc khi clone payload tạm.

### Bài 23. Không được sửa cây đang được duyệt

Một generator inorder đã `yield` được một nút và còn giữ stack. Luồng khác xóa các nút trên stack. Hậu quả ở C++ và Python có thể khác nhau thế nào?

**Lời giải:** Trong C++, con trỏ mượn tới node đã hủy có thể dangling/use-after-free. Trong Python, generator có thể giữ node còn sống qua tham chiếu mạnh nhưng kết quả không còn đúng với cấu trúc hiện tại. Cả hai cần hợp đồng snapshot, bất biến trong lượt duyệt hoặc đồng bộ phù hợp.

### Bài 24. Chọn chiến lược

Có cây nhị phân cân đối 1.000.000 nút, cần tạo một bản sao độc lập rồi hủy cả hai. Nên dự toán những gì ngoài thời gian O(n)?

**Lời giải:** Dự toán **O(n) bộ nhớ node clone**, thời điểm peak giữ cả nguồn và đích, chi phí stack DFS O(log n) hoặc queue BFS O(n) trên cây rộng, khả năng `malloc/realloc` thất bại và đường cleanup không đệ quy. Khi payload phức tạp, phải cộng chi phí copy/hủy tài nguyên riêng.

## 19. Tổng kết và nguyên tắc vận dụng

- **Cây rất sâu làm lộ giới hạn ngăn xếp:** độ phức tạp O(n) không loại bỏ `RecursionError` hoặc nguy cơ cạn stack khi clone, duyệt hoặc destructor.
- **Sao chép cấu trúc độc lập phải tạo lại mọi node** và nối đúng `left/right`; gán con trỏ hoặc copy struct nông không phải deep clone. Payload mutable cần chính sách copy riêng.
- **Clone không đệ quy** dùng DFS stack cặp `(source, target)` hoặc cặp `(source, destination_link)`; BFS dùng queue. Thời gian O(n), node kết quả O(n), bộ nhớ phụ DFS O(h+1) hoặc BFS O(w).
- **Duyệt sâu** bằng preorder/inorder/postorder stack và level-order queue giúp tránh call stack sâu; mỗi cách có bất biến và thứ tự trả nút riêng.
- **Giải phóng sâu** không nên phụ thuộc đệ quy. Với cây sở hữu riêng và được quyền phá liên kết, thuật toán chỉnh liên kết hủy O(n) thời gian, O(1) bộ nhớ phụ trợ, không cần cấp phát thêm trong nhánh lỗi.
- **RAII và `unique_ptr` không tự bảo đảm destructor mặc định không đệ quy sâu.** Thiết kế wrapper quản lý toàn cây với destructor lặp khi cần.
- **Cây thật khác DAG/graph:** chia sẻ nút, chu trình, con trỏ cha hay NIL sentinel làm thay đổi quy tắc clone, visited và ownership. Không dùng destructor cây sở hữu riêng để free cùng node qua nhiều đường.
- **Tính đúng đắn đi cùng vòng đời và lỗi:** mọi nút clone phải được khởi tạo trước khi nối; khi lỗi, dọn clone dở mà không dùng thêm bộ nhớ nếu có thể; giữ nguyên nguồn và không công bố kết quả chưa hoàn chỉnh.
- **Chọn theo chiều cao, độ rộng, số nút và yêu cầu dữ liệu:** xét `h`, `w`, peak memory, tần suất clone, nhu cầu duyệt/lưu kết quả và mức độ thay đổi cây, thay vì chỉ nhìn Big-O một thao tác.

Một hiện thực phù hợp không chỉ cho kết quả đúng trên cây nhỏ: nó còn giữ bất biến, không rò rỉ, không truy cập nút đã hủy và xử lý được **cây sâu đúng theo giới hạn mà ứng dụng đã công bố**.
