# Duyệt cây bằng đệ quy và chi phí ngăn xếp theo chiều cao

Khi viết hàm duyệt cây, cách tự nhiên nhất thường là **đệ quy (recursion)**: xử lý một nút, rồi gọi lại cùng thuật toán trên từng cây con. Mã ngắn và sát cấu trúc định nghĩa của cây. Nhưng mỗi lời gọi đệ quy cần một **khung ngăn xếp (stack frame)** để nhớ trạng thái xử lý. Vì vậy, ngoài thời gian duyệt, ta phải trả lời câu hỏi quan trọng: **tại một thời điểm có bao nhiêu lời gọi đang chờ trên ngăn xếp?**

Với một cây có `n` nút và chiều cao `h`, phép duyệt theo chiều sâu (DFS) bằng đệ quy thường có:

- **Thời gian O(n)** nếu xử lý mỗi nút một lần, công việc tại nút tốn O(1).
- **Bộ nhớ phụ O(h)** cho ngăn xếp lời gọi, không phải mặc định O(n) và cũng không phải O(1).
- Nếu **lưu dãy kết quả** gồm các giá trị của mọi nút, cần thêm **O(n)** bộ nhớ kết quả, độc lập với bộ nhớ điều khiển đệ quy.

Bài học thuộc chương **Duyệt và biến đổi cây** trong mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mô-đun phát triển kiến thức cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị; đồng thời rèn luyện tư duy về **bất biến, thao tác, độ phức tạp thời gian và bộ nhớ**. Trọng tâm ở đây là hiểu cơ chế của lời gọi đệ quy, tính đúng đắn và lý do **chiều cao cây** quyết định bộ nhớ của DFS.

## 1. Cây có gốc, nút và chiều cao

Xét cây nhị phân có gốc (*root*), mỗi nút có tối đa hai tham chiếu `left` và `right`. Ví dụ:

```text
               A
             /   \
            B     C
           / \   / \
          D   E F   G
```

Các khái niệm cần phân biệt:

- **Số nút `n`:** tổng số nút thực sự tồn tại trong cây. Ví dụ có `n = 7`.
- **Độ sâu `depth(v)`:** số **cạnh** từ gốc đến nút `v`. Gốc có độ sâu 0; `D` có độ sâu 2.
- **Chiều cao theo số mức `h`:** số **nút** trên đường đi dài nhất từ gốc xuống một lá. Cây trên có `h = 3`.
- **Chiều cao theo số cạnh:** số cạnh trên đường dài nhất ấy, bằng `h - 1` với cây không rỗng. Ví dụ là 2.

Trong toàn bài, ta dùng **`h` là số mức (số nút trên đường dài nhất)**: cây rỗng có `h = 0`, cây một nút có `h = 1`. Nếu tài liệu khác dùng chiều cao theo số cạnh, kết luận tiệm cận vẫn tương đương sau khi tính trường hợp cây rỗng.

### Hai hình dạng có cùng số nút nhưng chiều cao khác

```text
CÂY CÂN ĐỐI                      CÂY LỆCH PHẢI

       A                          A
     /   \                         \
    B     C                         B
   / \   / \                         \
  D   E F   G                         C
                                       \
                                        D
                                         \
                                          E
                                           \
                                            F
                                             \
                                              G

n = 7, h = 3                     n = 7, h = 7
```

Cả hai cây có bảy nút, nên duyệt hết vẫn cần O(n) thời gian. Tuy nhiên, ngăn xếp đệ quy có thể cần nhớ **ba nút tổ tiên theo một đường** trong cây cân đối, hoặc **bảy nút theo một đường** trong cây lệch. Chính sự khác nhau về `h` khiến chi phí bộ nhớ khác nhau.

## 2. Khuôn mẫu đệ quy của phép duyệt DFS

Cây có tính chất tự tương tự: cây con trái/phải của một nút lại là những cây nhỏ hơn. Vì thế, mỗi hàm duyệt chỉ cần xử lý hai trường hợp:

1. **Trường hợp cơ sở (*base case*):** nút hiện tại không tồn tại (`None`) thì dừng.
2. **Bước đệ quy (*recursive step*):** xử lý nút hoặc gọi lại hàm trên các cây con theo thứ tự mong muốn.

Ba cách duyệt cây nhị phân quen thuộc:

| Phép duyệt | Thứ tự | Khi nào xử lý nút cha? |
|---|---|---|
| **Preorder** (duyệt trước) | Gốc → Trái → Phải | **Trước** hai cây con |
| **Inorder** (duyệt giữa) | Trái → Gốc → Phải | **Giữa** hai cây con |
| **Postorder** (duyệt sau) | Trái → Phải → Gốc | **Sau** hai cây con |

Giả mã:

```text
PREORDER(node):
    if node == NULL: return
    visit(node)
    PREORDER(node.left)
    PREORDER(node.right)

INORDER(node):
    if node == NULL: return
    INORDER(node.left)
    visit(node)
    INORDER(node.right)

POSTORDER(node):
    if node == NULL: return
    POSTORDER(node.left)
    POSTORDER(node.right)
    visit(node)
```

Cả ba đều có hai lời gọi trên các cây con, nhưng **chúng chạy lần lượt**, không phải chạy song song. Khi gọi duyệt cây con trái, lời gọi ở nút cha **tạm dừng**. Sau khi cây trái xong và trả về, lời gọi cha tiếp tục với cây phải. Đây là chìa khóa giải thích vì sao số khung **đồng thời đang hoạt động** phụ thuộc vào **chiều cao**, không phải tổng số nút.

**Bất biến xử lý:** nếu cây thực sự không có nút dùng chung hay chu trình, mỗi nút không rỗng được `visit` chính xác một lần và thứ tự `visit` do vị trí câu lệnh quyết định.

## 3. Ngăn xếp lời gọi thực sự chứa gì?

Khi một hàm gọi hàm khác, hệ thống thường lưu một **khung ngăn xếp** cho lời gọi đang hoạt động. Mô hình khái niệm của một khung có thể gồm:

- Tham số và biến cục bộ, chẳng hạn `node`.
- Vị trí tiếp tục thực thi sau khi lời gọi con trả về.
- Thông tin quản lý lời gọi hoặc giá trị trung gian tùy ngôn ngữ và runtime.

Bố trí chính xác của stack frame là **chi tiết triển khai**. Ta không cần biết từng byte để phân tích tiệm cận; chỉ cần thấy rằng một lời gọi duyệt nút với số biến cục bộ cố định dùng **O(1) thông tin điều khiển**.

### Truy vết preorder trên cây con

Cho:

```text
        A
       / \
      B   C
     / \
    D   E
```

Khi duyệt preorder:

| Sự kiện | Ngăn xếp lời gọi đang hoạt động (đáy → đỉnh) | Giá trị đã `visit` |
|---|---|---|
| Bắt đầu `preorder(A)` | `[A]` | `A` |
| `A` gọi `preorder(B)` | `[A, B]` | `A, B` |
| `B` gọi `preorder(D)` | `[A, B, D]` | `A, B, D` |
| `D` gọi con `None` | `[A, B, D, None]` trong khoảnh khắc | Không thêm giá trị |
| Trả về từ nhánh rỗng và `D` | `[A, B]` | `A, B, D` |
| `B` gọi `preorder(E)` | `[A, B, E]` | `A, B, D, E` |
| `E` hoàn tất, quay lại `A` | `[A]` | `A, B, D, E` |
| `A` gọi `preorder(C)` | `[A, C]` | `A, B, D, E, C` |
| `C` hoàn tất | `[]` | `A, B, D, E, C` |

Độ dài stack có thể đạt **`h + 1`** nếu tính cả lời gọi tạm đến `None`; trong bảng, khi đi đến `D` có ba nút thực, cộng một lời gọi cơ sở. Vẫn là **O(h)**.

Một nhầm lẫn thường gặp: vì hàm có **hai lời gọi đệ quy**, không có nghĩa số frame đồng thời tăng như `2^h`. Lời gọi trái **kết thúc** trước khi lời gọi phải bắt đầu. Ngăn xếp tại mỗi thời điểm chỉ biểu diễn **một đường đi đang khám phá** cùng một số trạng thái chờ quay lại, không chứa toàn bộ cây trong các frame đệ quy.

### Thứ tự giải phóng khung

Tại nút lá `D`, hai lời gọi với con rỗng trả về ngay. Sau đó khung `D` kết thúc, cho phép `B` tiếp tục sang `E`. Khi cả `D` và `E` xong, khung `B` mới kết thúc và `A` có thể duyệt `C`.

Do cơ chế **vào sâu rồi quay lui** này, DFS đệ quy có tính chất của một **stack LIFO** ngay cả khi ta không tự viết lớp Stack nào.

## 4. Chứng minh thời gian O(n)

Giả sử `visit(node)`, kiểm tra `None` và đọc tham chiếu con đều tốn O(1). Gọi `T(n)` là thời gian duyệt một cây có `n` nút.

Với gốc có cây con trái `n_L` nút, cây con phải `n_R` nút, ta có:

```text
n = 1 + n_L + n_R

T(n) = T(n_L) + T(n_R) + O(1)
T(0) = O(1)
```

Mỗi nút thực được xử lý một lần, mỗi tham chiếu con được kiểm tra một số lần hằng số. Với cây nhị phân `n` nút, số nhánh con rỗng là `n + 1`, nên cả những lời gọi cơ sở cũng chỉ thêm O(n) công việc.

Vì vậy:

```text
T(n) = Θ(n)       với n >= 1
```

Kết luận áp dụng cho preorder, inorder và postorder. **Vị trí `visit` thay đổi thứ tự kết quả nhưng không thay đổi số nút phải xử lý.**

Nếu xử lý nút tốn nhiều hơn O(1), tổng thời gian thay đổi. Ví dụ: nếu tại mỗi nút ta lại quét toàn bộ cây con của nó, việc “duyệt một lần” ở mức điều khiển không còn bảo đảm O(n) cho toàn bộ công việc.

### Điều không nên làm khi phân tích

Đừng suy luận từ hai lời gọi đệ quy rằng:

```text
T(n) = 2T(n - 1) + O(1)
```

Quan hệ ấy **không đúng với hai cây con của một cây n nút**, bởi `n_L + n_R = n - 1`; không thể có hai cây con khác nhau mỗi cây đều chứa `n-1` nút trong một cây thực sự. Đệ quy phân chia các nút, không nhân bản toàn bộ dữ liệu thành hai bản sao.

## 5. Chứng minh bộ nhớ ngăn xếp O(h)

Gọi `S(h)` là số lượng bộ nhớ điều khiển lớn nhất mà các lời gọi đệ quy cần cho một cây có `h` mức.

Khi gọi hàm ở gốc, ta giữ một frame kích thước O(1). Ta có thể duyệt cây trái (tiêu thụ tới `S(h_L)`), **trả về**, rồi duyệt cây phải (tiêu thụ tới `S(h_R)`). Do hai lời gọi không hoạt động đồng thời, mức bộ nhớ đỉnh thỏa:

```text
S(h) <= max(S(h_L), S(h_R)) + O(1)

h = 1 + max(h_L, h_R)
```

Vì chiều cao giảm ít nhất một mức khi đi xuống một nút con:

```text
S(h) = O(h)
```

Với các phiên bản đệ quy duyệt cả cây có frame kích thước hằng số, một đường gốc–lá dài nhất thường tạo ra **Θ(h) frame đang hoạt động**. Vì thế có thể nói chi phí stack **Θ(h)** trong mô hình này; ký hiệu **O(h)** thường được dùng để mô tả bộ nhớ phụ.

### Cây cân bằng và cây lệch

| Kiểu cây | Số nút `n` | Chiều cao `h` | Stack đệ quy lớn nhất |
|---|---:|---:|---:|
| Rỗng | 0 | 0 | O(1) cho lời gọi cơ sở |
| Một nút | 1 | 1 | O(1) |
| Cây cân đối có 7 nút | 7 | 3 | O(3) frame nút, cộng cơ sở |
| Cây nhị phân cân bằng nói chung | `n` | **Θ(log n)** | **O(log n)** |
| Cây lệch một phía | `n` | **Θ(n)** | **O(n)** |

Vì vậy, **hai cây cùng n nút có thể có chi phí stack khác nhau rất lớn**. Không nên xem số lượng nút và chiều cao là hai đại lượng luôn cùng bậc.

### Chi phí kết quả không phải chi phí stack

Một hàm như:

```python
result = []
# Mỗi lần thăm một nút:
result.append(node.value)
```

tạo danh sách kết quả chứa `n` giá trị. Khi đó:

- **Ngăn xếp lời gọi:** O(h).
- **Danh sách kết quả:** O(n).
- **Tổng bộ nhớ phụ:** O(h + n) = O(n) với cây không rỗng.

Nếu thay việc lưu bằng một hành động xử lý/tiêu thụ trực tiếp có O(1) trạng thái, ta có thể chỉ dùng O(h) bộ nhớ phụ. Khi bài toán hỏi “space complexity”, cần nêu rõ **có tính bộ nhớ đầu ra hay không**.

## 6. Cài đặt Python: ba phép duyệt bằng đệ quy

Ta sử dụng một kiểu nút đơn giản và viết ba hàm trả về danh sách giá trị:

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


root = Node(
    "A",
    Node("B", Node("D"), Node("E")),
    Node("C", Node("F"), Node("G")),
)

assert preorder(root) == ["A", "B", "D", "E", "C", "F", "G"]
assert inorder(root) == ["D", "B", "E", "A", "F", "C", "G"]
assert postorder(root) == ["D", "E", "B", "F", "G", "C", "A"]
```

Ở mỗi hàm, trạng thái đệ quy gồm `node` và vị trí quay lại; O(1) trên mỗi frame. `result` được tạo **một lần bên ngoài hàm `walk`**, rồi mọi lần gọi con cùng ghi vào danh sách ấy.

Với **cây rỗng**:

```python
assert preorder(None) == []
assert inorder(None) == []
assert postorder(None) == []
```

Với **một nút**:

```python
leaf = Node(42)
assert preorder(leaf) == [42]
assert inorder(leaf) == [42]
assert postorder(leaf) == [42]
```

Điều kiện `if node is None: return` là bắt buộc để không truy cập `left`/`right` trên giá trị rỗng và để mọi nhánh đệ quy kết thúc.

## 7. Đo chiều sâu hoạt động bằng biến tham số

Một cách giúp hình dung bộ nhớ đệ quy là đếm **số nút thực trong chuỗi lời gọi đang đi từ gốc xuống**, thay vì đo RAM của runtime.

```python
def preorder_with_depth_stats(root):
    order = []
    max_active_nodes = 0

    def walk(node, active_nodes):
        nonlocal max_active_nodes

        if node is None:
            return

        # Tăng khi bước vào một nút thực.
        active_nodes += 1
        max_active_nodes = max(max_active_nodes, active_nodes)

        order.append(node.value)
        walk(node.left, active_nodes)
        walk(node.right, active_nodes)

    walk(root, 0)
    return order, max_active_nodes


order, max_depth = preorder_with_depth_stats(root)
assert order == ["A", "B", "D", "E", "C", "F", "G"]
assert max_depth == 3


skew = Node("A", right=Node("B", right=Node("C", right=Node("D"))))
order, max_depth = preorder_with_depth_stats(skew)

assert order == ["A", "B", "C", "D"]
assert max_depth == 4
```

Ví dụ này đo **độ dài đường đi tối đa qua các nút không rỗng**. Số frame thực tế có thể nhỉnh hơn vì có lời gọi cơ sở đến `None` và có frame của hàm bao ngoài; các thành phần ấy chỉ thêm một lượng hằng số so với `h` trong kiểu cài đặt này.

**Điểm cần hiểu:** biến `active_nodes` được truyền theo giá trị số nguyên. Khi một nhánh trả về, lời gọi cha vẫn giữ giá trị cũ của mình để tiếp tục nhánh còn lại. Nếu dùng một bộ đếm toàn cục rồi chỉ tăng mà quên giảm khi thoát hàm, số đo sẽ biến thành **tổng nút đã đi qua**, không còn là chiều sâu đang hoạt động.

## 8. Khi kết quả cây con quyết định cách xử lý cha

Không phải tất cả thuật toán trên cây đều chỉ **in giá trị nút**. Nhiều bài toán cần **trả kết quả từ cây con lên cha**, và khung đệ quy có thể lưu những kết quả trung gian.

### 8.1. Tính chiều cao cây theo số nút

```text
height(None) = 0

height(node) = 1 + max(height(node.left), height(node.right))
```

Mã Python:

```python
def tree_height(node):
    if node is None:
        return 0

    left_height = tree_height(node.left)
    right_height = tree_height(node.right)

    return 1 + max(left_height, right_height)


assert tree_height(root) == 3
assert tree_height(skew) == 4
assert tree_height(None) == 0
assert tree_height(Node("X")) == 1
```

Một lời gọi `tree_height(node)` phải **giữ frame của cha** trong lúc tính `left_height`, rồi giữ tiếp trong lúc tính `right_height`. Hai kết quả là các số nguyên và chỉ chiếm O(1) thông tin tại frame. Do đó tổng chi phí vẫn **O(n) thời gian, O(h) stack**.

Cách tính này mang bản chất **postorder**: chỉ xác định chiều cao của cha **sau** khi có chiều cao của hai cây con.

### 8.2. Tính số nút trong cây con

```python
def subtree_size(node):
    if node is None:
        return 0

    left_size = subtree_size(node.left)
    right_size = subtree_size(node.right)
    return 1 + left_size + right_size


assert subtree_size(root) == 7
assert subtree_size(root.left) == 3
assert subtree_size(root.left.left) == 1
```

Ta chỉ nhận được kích thước ở nút cha khi hai lời gọi con xong. Mỗi nút kết hợp kết quả con trong O(1), nên thời gian duyệt toàn cây O(n).

**Cảnh báo về cách dùng:** gọi `subtree_size(root)` một lần là O(n); nhưng nếu từ một vòng lặp khác ta **gọi lại `subtree_size` cho mọi nút** mà không lưu kết quả, nhiều cây con bị tính lặp. Ví dụ trên cây lệch, tổng công việc có thể là Θ(n²). Khi cần kích thước của *mọi* cây con, nên gán kết quả vào mỗi nút trong **một lần duyệt postorder**.

### 8.3. Biến đổi cây và phụ thuộc dữ liệu

Ví dụ gán thuộc tính tổng số nút bên dưới từng nút:

```python
def annotate_sizes(node):
    if node is None:
        return 0

    left_count = annotate_sizes(node.left)
    right_count = annotate_sizes(node.right)
    node.size = 1 + left_count + right_count
    return node.size


assert annotate_sizes(root) == 7
assert root.size == 7
assert root.left.size == 3
assert root.right.size == 3
```

Khi phép biến đổi yêu cầu **kết quả từ con**, hãy xử lý **sau khi** các cây con trả về. Ngược lại, khi công việc yêu cầu **truyền thông tin từ cha xuống con**, có thể dùng kiểu preorder: xử lý cha và đưa tham số như `depth + 1` xuống các lời gọi con.

Cả hai cách vẫn dùng **stack theo đường đi từ gốc xuống nút hiện tại**, chứ không giữ đồng thời khung của mọi nút trong cây.

## 9. Vì sao cây sâu có thể gây lỗi đệ quy?

Các ngôn ngữ/runtime thường giới hạn độ sâu lời gọi vì ngăn xếp thực tế không vô hạn. Với **Python**, đệ quy trên cây quá sâu có thể phát sinh `RecursionError` trước khi duyệt hết nút.

Ví dụ tạo một cây **lệch phải** có nhiều nút:

```python
def build_right_chain(n):
    root = None

    # Chỉ dùng vòng lặp để xây cây, không dùng đệ quy.
    for value in range(n - 1, -1, -1):
        root = Node(value, right=root)
    return root


chain = build_right_chain(6)
assert preorder(chain) == [0, 1, 2, 3, 4, 5]
assert tree_height(chain) == 6
```

Khi `n` rất lớn, đường gốc–lá có `h = n` mức, nên một phép duyệt đệ quy có thể cần gần `n` frame. **Không nên coi cách tăng `sys.setrecursionlimit` là giải pháp tổng quát**: đặt giới hạn quá cao không làm giảm O(h) bộ nhớ và có thể khiến chương trình cạn tài nguyên hoặc gặp vấn đề ngăn xếp ở tầng hệ thống.

Giải pháp thường phù hợp hơn với cây sâu là **thay ngăn xếp lời gọi bằng stack tường minh**. Ta vẫn phải nhớ các nút chưa xử lý, nhưng có thể tự quản lý cấu trúc dữ liệu thay vì bị giới hạn bởi cơ chế gọi hàm đệ quy của Python.

### Đệ quy đuôi có giải quyết vấn đề không?

Không nên mặc định **tối ưu đệ quy đuôi (*tail-call optimization*)** sẽ làm giảm bộ nhớ. Python không bảo đảm tối ưu lời gọi đệ quy đuôi như vậy, và một hàm DFS thường còn phải quay lại nút cha để xử lý nhánh khác hoặc kết hợp kết quả.

Ngay cả trong ngôn ngữ có hỗ trợ tối ưu một số lời gọi đuôi, cần kiểm tra điều kiện cụ thể của thuật toán thay vì suy ra “mọi phép duyệt cây đệ quy dùng O(1) stack”.

## 10. Chuyển preorder từ đệ quy sang stack tường minh

Đối với preorder **Gốc – Trái – Phải**, có thể lưu những nút sẽ thăm trong một stack.

Khi lấy nút `u`, xử lý `u` rồi **đẩy con phải trước con trái**. Vì stack là LIFO, con trái sẽ được lấy trước con phải.

```text
STACK_PREORDER(root):
    if root == NULL:
        return []

    stack = [root]
    output = []

    while stack không rỗng:
        node = stack.pop()
        output.append(node.value)

        if node.right != NULL:
            stack.push(node.right)
        if node.left != NULL:
            stack.push(node.left)

    return output
```

Mã Python:

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
assert preorder_iterative(chain) == [0, 1, 2, 3, 4, 5]
assert preorder_iterative(None) == []
```

Cài đặt này không dùng các lời gọi DFS lồng nhau nên **không bị giới hạn bởi độ sâu đệ quy của hàm `walk`**. Tuy nhiên, nó vẫn dùng stack để lưu các nút chưa xử lý.

### Stack tường minh lớn đến đâu?

Trên cây nhị phân, trong thuật toán preorder lặp này, khi đi dọc một đường sâu, stack có thể giữ **một số nhánh anh em chưa duyệt**, tối đa một nhánh phải đang chờ cho mỗi mức. Vì vậy lượng phần tử trong stack là **O(h)**.

- Cây cân bằng: thường O(log n) chiều sâu stack.
- Cây lệch: có thể chỉ có một vài nút nằm trong stack tường minh tại mỗi thời điểm, dù thời gian duyệt vẫn O(n). **Cận trên O(h)** không đòi hỏi mọi cây đều đạt đúng h phần tử.
- Một thuật toán DFS tường minh khác có thể lưu thêm nhiều thông tin trong từng frame; phải xét cách cài đặt cụ thể để xác định bộ nhớ.

**Chuyển sang lặp giải quyết vấn đề giới hạn call stack**, chứ không tạo phép màu biến việc duyệt cây thành O(1) bộ nhớ trong mọi trường hợp.

## 11. Mô phỏng chính xác ba pha đệ quy bằng stack

Khi muốn duyệt trước, giữa, sau với cùng một bộ máy, ta có thể mô phỏng **các mốc xử lý** tại mỗi nút bằng cặp `(node, phase)`.

Đặt ba pha:

- `0`: vừa vào nút.
- `1`: đã duyệt xong cây trái, sắp xử lý hoặc đi sang phải.
- `2`: đã duyệt xong cây phải, chuẩn bị kết thúc nút.

Vì stack tường minh hoạt động LIFO, ta đẩy **theo thứ tự ngược lại** với các bước muốn thực hiện:

```python
def traverse_with_frames(root, order):
    if order not in ("pre", "in", "post"):
        raise ValueError("order phải là pre, in hoặc post")
    if root is None:
        return []

    result = []
    # (node, phase); cây trái và phải được lên lịch tuần tự.
    stack = [(root, 0)]

    while stack:
        node, phase = stack.pop()

        if phase == 0:
            if order == "pre":
                result.append(node.value)

            # Khi trở về từ cây trái, tiếp tục pha 1.
            stack.append((node, 1))
            if node.left is not None:
                stack.append((node.left, 0))

        elif phase == 1:
            if order == "in":
                result.append(node.value)

            # Khi trở về từ cây phải, tiếp tục pha 2.
            stack.append((node, 2))
            if node.right is not None:
                stack.append((node.right, 0))

        else:  # phase == 2
            if order == "post":
                result.append(node.value)

    return result


assert traverse_with_frames(root, "pre") == preorder(root)
assert traverse_with_frames(root, "in") == inorder(root)
assert traverse_with_frames(root, "post") == postorder(root)
assert traverse_with_frames(None, "post") == []
assert traverse_with_frames(chain, "post") == [5, 4, 3, 2, 1, 0]
```

Bản này giúp làm rõ bản chất của call stack: mỗi frame phải nhớ **đang ở giai đoạn nào**, để khi quay lại từ nhánh trái có thể tiếp tục sang nhánh phải rồi mới hoàn tất nút.

### Bất biến của bộ máy ba pha

Với mỗi mục `(node, phase)` đang chờ:

- Nếu `phase = 0`, chưa xử lý cây con nào.
- Nếu `phase = 1`, việc duyệt cây trái đã hoàn tất; phần việc tại nút (nếu là inorder) sắp được thực hiện.
- Nếu `phase = 2`, cả hai cây con đã hoàn tất; phần việc tại nút (nếu là postorder) sắp được thực hiện.

Stack chứa các **mốc quay lại** cho những nút tổ tiên đang mở. Vì ở mỗi nút ta chỉ lưu một mốc tiếp tục rồi đi xuống một cây con, độ dài stack lớn nhất tỉ lệ với chiều cao `h` (cộng một lượng hằng số), tức **O(h)**.

Ở đoạn mã, `phase = 2` chỉ có thể xuất hiện sau khi lời gọi xử lý cây phải đã hoàn tất. Nhờ đó, việc ghi `result.append` đúng ở pha 2 cho kết quả postorder.

## 12. Những khác biệt cần chú ý khi so với BFS

**DFS đệ quy** giữ các nút **dọc một đường đi**, trong khi **BFS theo mức** dùng queue để giữ những nút đã gặp nhưng chưa xử lý ở các mức gần nhau.

| Đặc tính | DFS đệ quy | BFS bằng queue |
|---|---|---|
| Cấu trúc điều khiển | Ngăn xếp lời gọi (LIFO) | Hàng đợi (FIFO) |
| Thứ tự thường dùng | Preorder, inorder, postorder | Theo mức từ nông đến sâu |
| Thời gian trên cây n nút | O(n) | O(n) |
| Bộ nhớ điều khiển | O(h) | O(w), với `w` là độ rộng lớn nhất, và cận trên O(n) |
| Rủi ro trên cây lệch sâu | Chiều sâu call stack O(n) | Queue thường chỉ chứa ít nút |
| Rủi ro trên cây rất rộng | Stack theo chiều cao tương đối nhỏ | Queue có thể giữ nhiều nút một mức |

Cần xác định **đề bài yêu cầu thứ tự nào** rồi mới chọn DFS hay BFS. Đổi từ DFS sang BFS có thể giảm bộ nhớ trên cây lệch nhưng lại làm thay đổi thứ tự xử lý nút, nên **không phải phép thay thế tương đương** khi hợp đồng yêu cầu preorder/inorder/postorder.

## 13. Những lỗi dễ gặp khi viết DFS đệ quy

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Quên trường hợp `node is None` | Truy cập thuộc tính của `None` hoặc không có điểm dừng | Đặt base case đầu hàm |
| Đặt câu lệnh `visit` sai vị trí | Preorder/inorder/postorder trở thành kiểu khác | Kiểm tra thứ tự Gốc/Trái/Phải |
| Nhầm hai nhánh đệ quy là hai lời gọi chạy song song | Đánh giá bộ nhớ quá lớn theo số nút | Nhớ nhánh trái kết thúc trước nhánh phải |
| Cho rằng mỗi lời gọi có O(1) frame nên tổng bộ nhớ O(1) | Bỏ qua số frame hoạt động đồng thời | Bộ nhớ là O(h), không phải O(1) |
| Dùng số nút `n` thay cho chiều cao `h` ở mọi cây | Bỏ qua lợi thế cây cân bằng | Tách phân tích O(h), rồi xét h theo hình dạng |
| Tính cả danh sách kết quả vào O(h) mà không ghi chú | Thiếu bộ nhớ đầu ra O(n) | Báo riêng stack và kết quả |
| Tạo bản sao dãy kết quả ở mỗi lời gọi | Tốn nhiều thời gian và bộ nhớ cấp phát | Dùng accumulator hoặc xử lý trực tiếp |
| Quét lại toàn bộ cây con tại mỗi nút | Có thể làm thời gian vượt O(n) | Tính từ dưới lên trong một lần postorder |
| Bỏ qua cây cực sâu trong Python | `RecursionError` | Dùng stack tường minh khi cần |
| Dựa vào tail-call optimization mặc định | Sai trong Python | Không giả định Python tự tối ưu đệ quy |
| Dùng cấu trúc có chu trình như cây | Không kết thúc hoặc lặp nút | Xác minh cấu trúc cây; nếu là đồ thị, cần đánh dấu đã thăm |
| Khi biến đổi cây, sửa liên kết trước khi giữ tham chiếu con | Bỏ mất nhánh chưa duyệt | Xác định rõ thời điểm xử lý và lưu tham chiếu cần thiết |

### Một ví dụ về việc sao chép danh sách gây chi phí khác

Mã sau **đúng thứ tự preorder**, nhưng có thể tốn thời gian cao hơn vì **nối các danh sách kết quả đệ quy**:

```python
def preorder_with_concatenation(node):
    if node is None:
        return []
    return (
        [node.value]
        + preorder_with_concatenation(node.left)
        + preorder_with_concatenation(node.right)
    )
```

Với cây lệch, ở nhiều mức, phép `+` phải sao chép một danh sách có chiều dài tỷ lệ với số nút còn lại. Tổng lượng phần tử được sao chép có thể là **Θ(n²)** thay vì O(n).

Cách dùng một `result` chung và `append` khi thăm nút, như ở mục 6, tránh việc ghép/copy nhiều danh sách lớn. **Phân tích O(n) dựa vào công việc O(1) tại mỗi nút; không thể áp dụng máy móc cho mọi mã đệ quy.**

## 14. Câu hỏi tự kiểm tra và lời giải

**Câu 1 — Call stack.** Một cây nhị phân cân bằng có `n` nút và chiều cao Θ(log n). DFS đệ quy cần bao nhiêu bộ nhớ ngăn xếp?

*Lời giải:* **O(log n)** bộ nhớ phụ cho call stack, vì tại một thời điểm chỉ có một đường lời gọi sâu tối đa h mức.

**Câu 2 — Cây lệch.** Một cây có 1.000 nút nối liên tiếp bằng con phải, tức h = 1.000. Độ phức tạp thời gian và bộ nhớ stack của preorder là gì?

*Lời giải:* **O(n)** thời gian để thăm 1.000 nút; **O(h) = O(n)** stack vì phải đi sâu qua toàn bộ đường nút. Trong Python, có thể gặp giới hạn đệ quy tùy môi trường.

**Câu 3 — Hai lời gọi.** Vì sao hai dòng `walk(node.left)` và `walk(node.right)` không làm số frame đồng thời tăng gấp đôi qua mỗi mức?

*Lời giải:* Hai lời gọi chạy **nối tiếp**: nhánh trái phải trả về trước khi nhánh phải bắt đầu. Một frame của cha chờ trong lúc đi xuống, không giữ đồng thời cả hai cây con đang chạy.

**Câu 4 — Trường hợp cơ sở.** Tại sao phải có `if node is None: return` ở đầu DFS?

*Lời giải:* Mọi lá đều có tham chiếu con rỗng. Base case ngăn việc đọc thuộc tính của `None` và bảo đảm đệ quy có điểm dừng.

**Câu 5 — Thứ tự duyệt.** Cho cây:

```text
       P
      / \
     Q   R
        /
       S
```

Hãy ghi preorder, inorder và postorder.

*Lời giải:* Preorder **`P, Q, R, S`**; inorder **`Q, P, S, R`**; postorder **`Q, S, R, P`**.

**Câu 6 — Tính chiều cao.** Một hàm `height` phải lấy kết quả hai cây con để tính `1 + max(left, right)`. Đó là tư duy preorder hay postorder?

*Lời giải:* **Postorder** (tổng hợp từ con lên cha). Kết quả của nút cha chỉ được tính sau khi cả hai cây con đã được giải quyết.

**Câu 7 — Bộ nhớ đầu ra.** Hàm preorder trả về danh sách gồm tất cả `n` giá trị nhưng call stack có độ sâu tối đa `h`. Hãy phân biệt hai chi phí bộ nhớ.

*Lời giải:* **O(h)** cho ngăn xếp lời gọi, **O(n)** cho danh sách đầu ra; tổng **O(n + h) = O(n)** khi cây có `n` nút.

**Câu 8 — Lặp thay đệ quy.** Chuyển preorder từ đệ quy sang `stack = [root]` có bảo đảm dùng O(1) bộ nhớ mọi lúc không?

*Lời giải:* **Không.** Stack tường minh vẫn giữ các nút chưa xử lý, với cận trên **O(h)** trong phiên bản đẩy con phải rồi trái. Nó tránh giới hạn call stack của runtime, chứ không loại bỏ nhu cầu ghi nhớ trạng thái.

**Câu 9 — Đệ quy hai nhánh.** Đánh giá `T(n) = 2T(n-1) + O(1)` có đúng cho DFS trên cây nhị phân n nút không?

*Lời giải:* **Không.** Hai cây con có tổng `n-1` nút, nên hệ thức đúng là `T(n) = T(n_L) + T(n_R) + O(1)` với `n_L + n_R = n-1`. Tổng thời gian O(n).

**Câu 10 — Cây một nút.** Theo quy ước chiều cao là số nút trên đường dài nhất, cây rỗng và cây một nút có chiều cao bao nhiêu?

*Lời giải:* Cây rỗng có **h = 0**, cây một nút có **h = 1**. Nếu quy ước chiều cao tính bằng số cạnh, cần nêu lại giá trị cơ sở tương ứng.

**Câu 11 — Tối ưu tránh tính lặp.** Muốn gán kích thước cây con lên mọi nút của một cây lệch, có nên gọi lại hàm đếm toàn bộ cây con từ đầu tại từng nút?

*Lời giải:* Không. Cách đó có thể tốn **Θ(n²)**. Dùng **một lần postorder**, mỗi nút cộng kích thước hai con O(1), để đạt **O(n)** thời gian.

**Câu 12 — Cây hay đồ thị?** Nếu hai nút cha cùng trỏ tới một nút con chung, hàm đệ quy cây ở bài này có bảo đảm chỉ xử lý nút con một lần không?

*Lời giải:* **Không.** Giả định “mỗi nút thuộc đúng một đường cha từ gốc” không còn đúng. Đây là cấu trúc DAG dùng chung nút; muốn tránh xử lý trùng phải thiết kế đánh dấu đã thăm tùy hợp đồng bài toán.

## 15. Tổng kết

Duyệt cây bằng đệ quy phù hợp với cấu trúc tự tương tự của cây: mỗi hàm xử lý một nút và **gọi tiếp trên cây con**. Preorder xử lý cha trước, inorder đặt cha giữa hai nhánh, postorder xử lý cha sau các con. Nếu công việc trên mỗi nút có chi phí O(1), cả ba thường duyệt hết cây trong **O(n) thời gian**.

Chi phí bộ nhớ điều khiển phụ thuộc vào **đường gọi đệ quy sâu nhất**, tức **chiều cao `h` của cây**, nên là **O(h)**: thường O(log n) với cây cân bằng và O(n) với cây lệch. Nếu kết quả được giữ trong danh sách, phải tính thêm O(n) bộ nhớ đầu ra. Với cây quá sâu, có thể thay đệ quy bằng **stack tường minh** để tránh giới hạn đệ quy, trong khi vẫn giữ đúng thứ tự xử lý và đánh giá rõ chi phí bộ nhớ.
