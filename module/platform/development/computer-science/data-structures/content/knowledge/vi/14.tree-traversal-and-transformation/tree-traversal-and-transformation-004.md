# Duyệt không đệ quy bằng ngăn xếp tường minh

Duyệt cây theo chiều sâu (*depth-first traversal*, DFS) thường được trình bày bằng **đệ quy**: một hàm xử lý nút hiện tại rồi gọi lại chính nó cho các cây con. Mã đệ quy ngắn, nhưng các lời gọi đang chờ quay lại thực chất được quản lý bởi **ngăn xếp lời gọi** (*call stack*) của chương trình. Ta có thể thay cơ chế ấy bằng **ngăn xếp tường minh** (*explicit stack*) do chính mình tạo và điều khiển.

Cách làm không đệ quy đặc biệt hữu ích khi cây **rất sâu**, khi ngôn ngữ có giới hạn độ sâu lời gọi (chẳng hạn `RecursionError` trong Python), hoặc khi thuật toán cần **tạm dừng, quan sát, lưu lại trạng thái duyệt**. Tuy nhiên, bỏ đệ quy **không có nghĩa bỏ nhu cầu ghi nhớ đường đi**: ta chỉ chuyển trạng thái từ call stack sang cấu trúc stack do chương trình quản lý.

Bài thuộc chương **Duyệt và biến đổi cây** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Trong lộ trình xây dựng kiến thức cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, nội dung tập trung vào **bất biến**, **thứ tự thao tác** và **độ phức tạp thời gian, bộ nhớ**. Bài sẽ triển khai đầy đủ ba phép duyệt **preorder, inorder và postorder** bằng stack, truy vết, chứng minh tính đúng đắn và phân tích sự khác nhau giữa những biến thể cài đặt.

## 1. Bài toán và ba thứ tự duyệt cây nhị phân

Trong bài này, mỗi nút có giá trị `value` và tối đa hai tham chiếu `left`, `right`. Duyệt đúng nghĩa là **xử lý mỗi nút một lần theo thứ tự được quy định**. Dùng cây minh họa:

```text
                  A
                /   \
               B     C
              / \   / \
             D   E F   G

Nút gốc: A
Cây trái của A: B, D, E
Cây phải của A: C, F, G
```

Nếu quy ước **luôn duyệt cây trái trước cây phải**, ta có ba kiểu DFS:

| Kiểu duyệt | Quy tắc tại nút N | Kết quả trên cây minh họa |
|---|---|---|
| **Preorder** — duyệt trước | **Nút → Trái → Phải** | `A, B, D, E, C, F, G` |
| **Inorder** — duyệt giữa | **Trái → Nút → Phải** | `D, B, E, A, F, C, G` |
| **Postorder** — duyệt sau | **Trái → Phải → Nút** | `D, E, B, F, G, C, A` |

Cả ba đều xử lý đủ bảy nút. Sự khác nhau nằm ở **thời điểm xử lý cha so với con**, không phải số nút được thăm.

Ở đây **xử lý nút** thường là `result.append(node.value)` để dễ kiểm tra. Nhưng đó cũng có thể là tạo bản sao, tính tổng hợp cây con, xuất biểu thức hay cập nhật dữ liệu. Trong ứng dụng như vậy, thứ tự xử lý có thể quyết định tính đúng đắn.

### Những điều kiện tiên quyết

- **Cây rỗng:** `root is None`; kết quả là `[]`.
- **Nút lá:** hai con đều `None`; phải được xử lý đúng một lần.
- **Nhãn nút trùng nhau:** hai nút khác nhau dù cùng `value` vẫn phải được thăm riêng; thuật toán làm việc với **tham chiếu nút**, không dùng giá trị để xác định đã thăm.
- **Cấu trúc thật sự là cây:** không có chu trình và không có cùng một nút con bị chia sẻ giữa nhiều cha. Với đồ thị hoặc DAG, cần hợp đồng về thăm trùng và có thể cần tập `visited`.
- **Ngăn xếp tường minh:** là một cấu trúc LIFO hỗ trợ `push` và `pop` ở đỉnh. Trong Python, `list.append` và `list.pop()` đáp ứng thao tác này.

## 2. Call stack và explicit stack giống, khác nhau thế nào?

Mã preorder đệ quy có dạng:

```python
def preorder_recursive(node):
    if node is None:
        return
    visit(node)
    preorder_recursive(node.left)
    preorder_recursive(node.right)
```

Khi hàm ở gốc gọi vào cây con trái, nó **chưa hoàn tất**: còn phải quay về để đi sang cây con phải. Thông tin “đang ở nút nào, sẽ tiếp tục ở đâu” được lưu trong **khung ngăn xếp lời gọi** (*stack frame*).

Ngăn xếp tường minh đưa thông tin ấy ra một danh sách do ta tự quản lý:

```text
ĐỆ QUY                                KHÔNG ĐỆ QUY

preorder(A)                           stack = [A]
 └── preorder(B)                      lấy A, đẩy C rồi B
      └── preorder(D)                 stack = [C, B]
           └── ...                    lấy B, đẩy E rồi D
                                      stack = [C, E, D]

Call stack giữ các lời gọi chờ.        Stack giữ các nút/khung chờ.
```

Khác biệt cốt lõi:

| Vấn đề | Đệ quy | Stack tường minh |
|---|---|---|
| Ai lưu trạng thái chờ? | Runtime và call stack | Chương trình qua cấu trúc dữ liệu |
| Cơ chế LIFO | Tự động khi gọi/trả về | Tự viết `append`/`pop` |
| Cách giữ vị trí “quay lại” | Địa chỉ tiếp tục trong frame | Có thể lưu **nút** hoặc **(nút, trạng thái)** |
| Thứ tự duyệt | Từ vị trí lời gọi/`visit` | Từ thứ tự đưa vào stack và xử lý frame |
| Cây rất sâu | Có thể vượt giới hạn đệ quy | Tránh giới hạn gọi hàm DFS, nhưng vẫn tốn bộ nhớ |
| Lỗi thường gặp | Sai base case, sai thứ tự gọi | Sai thứ tự push, thiếu trạng thái hoàn tất |

Điều quan trọng là **stack tường minh không tự tạo ra đúng preorder/inorder/postorder**. Ta phải thiết kế *ý nghĩa của mỗi mục trên stack* để khôi phục chính xác thứ tự mong muốn.

## 3. Preorder không đệ quy: xử lý ngay khi lấy nút

Preorder là **Gốc – Trái – Phải**, nên thuật toán đơn giản:

1. Nếu cây rỗng, trả kết quả rỗng.
2. Đẩy gốc vào stack.
3. Khi stack chưa rỗng, lấy nút đỉnh và **xử lý ngay**.
4. Đẩy **con phải trước**, sau đó **con trái** nếu các con tồn tại.
5. Lặp lại.

### Vì sao phải đẩy phải trước trái?

Ngăn xếp là **LIFO**: phần tử vừa đẩy sau cùng được lấy ra trước. Muốn duyệt **trái trước phải**, ta cần để **con trái ở đỉnh**.

```text
Cây con:
      A
     / \
    B   C

Sai:  push(B), rồi push(C)  -> stack [B, C] -> pop C trước.
Đúng: push(C), rồi push(B)  -> stack [C, B] -> pop B trước.

Quy ước: phía bên phải của dãy stack là ĐỈNH.
```

### Giả mã

```text
PREORDER_ITERATIVE(root):
    if root == NULL: return []

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

### Truy vết preorder

Với cây bảy nút ở đầu bài, stack được viết từ **đáy đến đỉnh**:

| Lượt | Nút vừa lấy | Thao tác đẩy tiếp | Stack sau lượt | Kết quả |
|---:|---|---|---|---|
| 0 | — | Đẩy `A` | `[A]` | `[]` |
| 1 | `A` | Đẩy `C`, rồi `B` | `[C, B]` | `[A]` |
| 2 | `B` | Đẩy `E`, rồi `D` | `[C, E, D]` | `[A, B]` |
| 3 | `D` | Không có con | `[C, E]` | `[A, B, D]` |
| 4 | `E` | Không có con | `[C]` | `[A, B, D, E]` |
| 5 | `C` | Đẩy `G`, rồi `F` | `[G, F]` | `[A, B, D, E, C]` |
| 6 | `F` | Không có con | `[G]` | `[A, B, D, E, C, F]` |
| 7 | `G` | Không có con | `[]` | `[A, B, D, E, C, F, G]` |

Bảng cho thấy sau khi xử lý `A`, nút `C` **chờ trong stack** cho đến khi toàn bộ cây trái của `A` đã được duyệt. Đây là hành vi DFS.

### Python

```python
def preorder_iterative(root):
    if root is None:
        return []

    result = []
    stack = [root]

    while stack:
        node = stack.pop()
        result.append(node.value)

        # LIFO: đẩy phải trước để trái được lấy ra trước.
        if node.right is not None:
            stack.append(node.right)
        if node.left is not None:
            stack.append(node.left)

    return result
```

Mã chỉ xử lý nút khi **lấy khỏi stack**, nên mỗi nút được đưa vào và lấy ra đúng một lần nếu đầu vào là cây.

## 4. Inorder không đệ quy: ghi nhớ đường đi về trái

Inorder có thứ tự **Trái – Gốc – Phải**. Khác preorder, ta không được xử lý nút ngay khi gặp; phải **duyệt hết cây trái trước**.

Ta dùng hai biến:

- `current`: nút đang đi xuống để tìm phần tử trái nhất chưa xử lý.
- `stack`: các nút tổ tiên **đang chờ** sau khi duyệt cây trái.

Quy trình:

1. Bắt đầu `current = root`.
2. Khi `current` khác `None`, **đẩy nó vào stack** và tiếp tục `current = current.left`.
3. Khi không thể đi trái nữa, **lấy một nút khỏi stack và xử lý**.
4. Chuyển `current` sang `node.right` rồi lặp lại.
5. Kết thúc khi **`current is None` và stack rỗng**.

### Vì sao cần cả hai điều kiện dừng?

Nếu `current is None` nhưng stack còn nút, ta **chưa thăm xong**: các tổ tiên đang chờ xử lý. Ngược lại, sau khi xử lý một nút, stack có thể tạm rỗng nhưng `current` được đặt sang một **cây phải chưa duyệt**. Điều kiện vòng lặp đúng là:

```text
while current != NULL OR stack không rỗng
```

### Giả mã

```text
INORDER_ITERATIVE(root):
    current = root
    stack = []
    output = []

    while current != NULL or stack không rỗng:
        while current != NULL:
            stack.push(current)
            current = current.left

        node = stack.pop()
        output.append(node.value)
        current = node.right

    return output
```

### Truy vết inorder

Xét cây nhỏ:

```text
         A
        / \
       B   C
      / \
     D   E
```

| Bước | Hành động | Stack đang chờ (đáy → đỉnh) | `current` | Kết quả |
|---:|---|---|---|---|
| 0 | Bắt đầu | `[]` | `A` | `[]` |
| 1 | Đi trái, đẩy `A` | `[A]` | `B` | `[]` |
| 2 | Đi trái, đẩy `B` | `[A, B]` | `D` | `[]` |
| 3 | Đẩy `D`, đi trái rỗng | `[A, B, D]` | `None` | `[]` |
| 4 | Pop/visit `D`, chuyển phải | `[A, B]` | `None` | `[D]` |
| 5 | Pop/visit `B`, chuyển phải | `[A]` | `E` | `[D, B]` |
| 6 | Đẩy `E`, đi trái rỗng | `[A, E]` | `None` | `[D, B]` |
| 7 | Pop/visit `E`, chuyển phải | `[A]` | `None` | `[D, B, E]` |
| 8 | Pop/visit `A`, chuyển phải | `[]` | `C` | `[D, B, E, A]` |
| 9 | Đẩy `C`, đi trái rỗng | `[C]` | `None` | `[D, B, E, A]` |
| 10 | Pop/visit `C` | `[]` | `None` | `[D, B, E, A, C]` |

Ta thấy `A` nằm trong stack cho đến khi toàn bộ cây con trái `B` hoàn thành. Cách lưu **nút cha chờ quay lại** này mô phỏng đúng bản chất của inorder đệ quy.

### Python

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
```

Với **cây tìm kiếm nhị phân (BST)** có bất biến mọi khóa cây trái nhỏ hơn nút và mọi khóa cây phải lớn hơn nút, inorder cho dãy khóa tăng. Cần nhớ kết luận này **phụ thuộc vào bất biến BST**, không đúng cho cây nhị phân bất kỳ.

## 5. Postorder không đệ quy: phải nhớ đã xử lý các con chưa

Postorder có thứ tự **Trái – Phải – Gốc**. Đây là trường hợp dễ sai nhất khi dùng stack vì nút cha chỉ được xử lý **sau khi cả hai cây con đã hoàn tất**.

Nếu chỉ lấy nút ra khỏi stack rồi xử lý ngay, ta sẽ nhận preorder, không phải postorder. Ta cần phân biệt:

- **Lần đầu gặp một nút:** phải lên lịch duyệt hai cây con.
- **Lần quay lại sau hai cây con:** mới được xử lý nút cha.

Một kỹ thuật rõ ràng là đặt trên stack cặp `(node, expanded)`, với `expanded` là một cờ Boolean.

### 5.1. Một stack với cờ `expanded`

Thuật toán:

1. Nếu root rỗng, trả `[]`.
2. Đẩy `(root, False)`.
3. Lấy một cặp ra:
   - Nếu `expanded == True`, xử lý nút ngay.
   - Nếu `expanded == False`, đẩy `(node, True)` để **hẹn xử lý cha sau**, rồi đẩy con phải và con trái với cờ `False`.
4. Lặp tới khi stack rỗng.

Vì stack LIFO, thứ tự lấy tiếp theo là **cây trái**, **cây phải**, rồi **(node, True)**.

```text
POSTORDER_ITERATIVE(root):
    if root == NULL: return []

    stack = [(root, false)]
    output = []

    while stack không rỗng:
        node, expanded = stack.pop()

        if expanded:
            output.append(node.value)
        else:
            stack.push((node, true))
            if node.right != NULL:
                stack.push((node.right, false))
            if node.left != NULL:
                stack.push((node.left, false))

    return output
```

### Vì sao cờ `expanded` có nghĩa chính xác?

Mục `(node, True)` được đặt **bên dưới** các mục của hai cây con. Nó chỉ nổi lên đầu stack khi cả hai cây con đã được duyệt. Vì thế, một nút chỉ được `visit` đúng lúc đã có kết quả từ con.

### Truy vết postorder trên cây nhỏ

Xét:

```text
       A
      / \
     B   C
```

Stack ghi từ đáy đến đỉnh:

| Lượt | Mục vừa lấy | Stack sau lượt | Kết quả |
|---:|---|---|---|
| 0 | — | `[(A,F)]` | `[]` |
| 1 | `(A,F)` | `[(A,T), (C,F), (B,F)]` | `[]` |
| 2 | `(B,F)` | `[(A,T), (C,F), (B,T)]` | `[]` |
| 3 | `(B,T)` | `[(A,T), (C,F)]` | `[B]` |
| 4 | `(C,F)` | `[(A,T), (C,T)]` | `[B]` |
| 5 | `(C,T)` | `[(A,T)]` | `[B,C]` |
| 6 | `(A,T)` | `[]` | `[B,C,A]` |

Ở đây `F` là `False` (chưa mở rộng con), `T` là `True` (đã lên lịch xử lý sau con). **`(A,T)` không bị lấy ra trước `B` hoặc `C`**, nên kết quả bảo đảm Trái – Phải – Gốc.

### Python

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
            continue

        # Xử lý cha sau: đưa "lịch hẹn" của cha xuống dưới hai con.
        stack.append((node, True))
        if node.right is not None:
            stack.append((node.right, False))
        if node.left is not None:
            stack.append((node.left, False))

    return result
```

Cách này dùng **một stack tường minh**, không cần biến toàn cục và không nhầm giữa nhãn nút với trạng thái xử lý. Nó đặc biệt thích hợp khi công việc ở nút chỉ cần biết rằng hai cây con đã được xử lý xong.

## 6. Một bộ máy thống nhất với ba pha

Ta có thể mô phỏng luồng điều khiển của đệ quy bằng **khung trạng thái** `(node, phase)`, thay vì viết ba thuật toán riêng. Mỗi nút có ba pha xử lý:

| Pha | Ý nghĩa | Kiểu duyệt xử lý nút ở pha này |
|---:|---|---|
| `0` | Vừa đến nút, **chưa** duyệt trái | **Preorder** |
| `1` | Đã duyệt xong trái, **chưa** duyệt phải | **Inorder** |
| `2` | Đã duyệt xong cả trái và phải | **Postorder** |

Tại pha 0, đặt lịch quay về pha 1 rồi đi vào cây trái. Tại pha 1, đặt lịch quay về pha 2 rồi đi vào cây phải. Tại pha 2, hoàn tất nút.

```text
Nút N, pha 0
   |
   +-- visit N nếu preorder
   +-- chờ pha 1, duyệt cây trái
              |
              +-- visit N nếu inorder
              +-- chờ pha 2, duyệt cây phải
                         |
                         +-- visit N nếu postorder
                         +-- kết thúc nút N
```

### Python: một hàm cho cả ba thứ tự

```python
def traverse_with_frames(root, order):
    if order not in ("pre", "in", "post"):
        raise ValueError("order phải là pre, in hoặc post")
    if root is None:
        return []

    result = []
    stack = [(root, 0)]

    while stack:
        node, phase = stack.pop()

        if phase == 0:
            if order == "pre":
                result.append(node.value)
            stack.append((node, 1))
            if node.left is not None:
                stack.append((node.left, 0))

        elif phase == 1:
            if order == "in":
                result.append(node.value)
            stack.append((node, 2))
            if node.right is not None:
                stack.append((node.right, 0))

        else:  # phase == 2
            if order == "post":
                result.append(node.value)

    return result
```

**Bất biến điều khiển:** với một khung `(node, 1)` đang chờ trong stack, cây trái của `node` sẽ được hoàn tất trước khi khung ấy được lấy ra; với `(node, 2)`, cả hai cây con sẽ hoàn tất trước khi khung được lấy ra. Vì vậy, ghi `visit` ở pha tương ứng giữ đúng ba thứ tự DFS.

Một ưu điểm của cách làm này là có thể thêm thông tin vào frame, chẳng hạn trạng thái **đang tính**, kết quả từng cây con, hay đường dẫn hiện tại. Đó là nền tảng cho nhiều thuật toán biến đổi cây cần công việc ở cả trước và sau khi duyệt con.

## 7. Phương án postorder hai stack và đánh đổi bộ nhớ

Có một kỹ thuật postorder khác: **dùng hai stack**, thường dễ nhớ nhưng có thể dùng nhiều bộ nhớ hơn.

Giả mã:

```text
POSTORDER_TWO_STACKS(root):
    if root == NULL: return []

    s1 = [root]
    s2 = []

    while s1 không rỗng:
        node = s1.pop()
        s2.push(node)

        if node.left != NULL:
            s1.push(node.left)
        if node.right != NULL:
            s1.push(node.right)

    while s2 không rỗng:
        output.append(s2.pop().value)

    return output
```

Trong giai đoạn đầu, `s1` lấy **phải trước trái** vì ta đẩy trái trước, phải sau. Kết quả ghi vào `s2` có thứ tự gần như **Gốc – Phải – Trái**; khi lấy ngược từ `s2`, ta có **Trái – Phải – Gốc**.

### Python

```python
def postorder_two_stacks(root):
    if root is None:
        return []

    s1 = [root]
    s2 = []
    result = []

    while s1:
        node = s1.pop()
        s2.append(node)

        if node.left is not None:
            s1.append(node.left)
        if node.right is not None:
            s1.append(node.right)

    while s2:
        result.append(s2.pop().value)

    return result
```

### Khác biệt quan trọng về độ phức tạp

Hai stack có **O(n) thời gian**, vì mỗi nút được đưa vào/lấy ra một số lần hằng số. Tuy nhiên, `s2` giữ **tất cả n nút** trước khi giai đoạn xuất kết quả bắt đầu, nên cần **O(n) bộ nhớ phụ điều khiển/lưu nút**, ngay cả khi cây khá cân bằng.

Ngược lại, phiên bản **một stack với cờ** chỉ giữ các khung đang chờ trên một đường DFS cùng các nhánh anh em chưa duyệt, nên với cây nhị phân cần **O(h)** bộ nhớ stack trong trường hợp xấu nhất theo chiều cao `h`.

**Không được khẳng định mọi thuật toán không đệ quy đều dùng O(h).** Độ phức tạp bộ nhớ phụ thuộc **những gì thực sự được giữ** trên các stack, nhất là biến thể hai stack giữ toàn bộ nút.

## 8. Ví dụ Python hoàn chỉnh và kiểm tra đối chiếu

Ghép định nghĩa nút và dựng cây để kiểm tra các thuật toán vừa trình bày:

```python
class Node:
    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right


#                A
#              /   \
#             B     C
#            / \   / \
#           D   E F   G
root = Node(
    "A",
    left=Node("B", Node("D"), Node("E")),
    right=Node("C", Node("F"), Node("G")),
)

expected_pre = ["A", "B", "D", "E", "C", "F", "G"]
expected_in = ["D", "B", "E", "A", "F", "C", "G"]
expected_post = ["D", "E", "B", "F", "G", "C", "A"]

assert preorder_iterative(root) == expected_pre
assert inorder_iterative(root) == expected_in
assert postorder_iterative(root) == expected_post
assert postorder_two_stacks(root) == expected_post

assert traverse_with_frames(root, "pre") == expected_pre
assert traverse_with_frames(root, "in") == expected_in
assert traverse_with_frames(root, "post") == expected_post
```

Những khẳng định `assert` này là **ví dụ kiểm tra** để người học có thể chạy sau khi ghép các định nghĩa hàm vào cùng tệp Python. Chúng minh họa kỳ vọng về đầu ra, không thay thế việc kiểm thử chuyên sâu cho các ứng dụng có cây phức tạp.

### Kiểm tra cây rỗng

```python
assert preorder_iterative(None) == []
assert inorder_iterative(None) == []
assert postorder_iterative(None) == []
assert postorder_two_stacks(None) == []

assert traverse_with_frames(None, "pre") == []
assert traverse_with_frames(None, "in") == []
assert traverse_with_frames(None, "post") == []
```

Các hàm không được `pop` trên stack rỗng hoặc truy cập `left`/`right` của `None`. Đây là trường hợp cơ sở tương đương `if node is None: return` trong đệ quy.

### Kiểm tra cây một nút và giá trị trùng nhau

```python
single = Node(None)
assert preorder_iterative(single) == [None]
assert inorder_iterative(single) == [None]
assert postorder_iterative(single) == [None]

duplicates = Node("X", Node("X"), Node("X"))
assert preorder_iterative(duplicates) == ["X", "X", "X"]
assert inorder_iterative(duplicates) == ["X", "X", "X"]
assert postorder_iterative(duplicates) == ["X", "X", "X"]
```

`None` là **giá trị hợp lệ của một nút** trong ví dụ, khác với việc **tham chiếu nút bằng `None`**. Vì vậy ta kiểm tra `node is None`, không kiểm tra `node.value is None`. Hai nút có cùng giá trị vẫn là hai nút khác nhau và phải được xử lý riêng.

## 9. Cây lệch sâu: lý do thực tế để dùng stack tường minh

Xét cây chỉ có con phải:

```text
A
 \
  B
   \
    C
     \
      D
       \
        E
```

Đó là cây nhị phân hợp lệ nhưng chiều cao bằng số nút. Với nhiều nghìn nút, đệ quy Python có thể phát sinh `RecursionError` do vượt giới hạn độ sâu lời gọi.

Ta có thể **xây cây bằng vòng lặp**, không cần đệ quy:

```python
def make_right_chain(n):
    root = None

    for value in range(n - 1, -1, -1):
        root = Node(value, right=root)

    return root


deep_root = make_right_chain(5000)

pre = preorder_iterative(deep_root)
post = postorder_iterative(deep_root)

assert len(pre) == 5000
assert pre[:3] == [0, 1, 2]
assert pre[-1] == 4999
assert post[:3] == [4999, 4998, 4997]
assert post[-1] == 0

assert inorder_iterative(deep_root) == list(range(5000))
```

Với cây lệch **chỉ có nhánh phải**:

- Preorder đi **Gốc – Phải**, nên thứ tự `0, 1, …, 4999`.
- Inorder cũng đi **Gốc – Phải** vì các nhánh trái đều rỗng.
- Postorder đi **Phải – Gốc**, nên trả `4999, 4998, …, 0`.

Đừng suy luận rằng **mọi** cây lệch sẽ cho preorder và inorder giống nhau: cây lệch **chỉ có nhánh trái** sẽ có inorder và postorder cùng dãy từ lá về gốc, còn preorder đi từ gốc xuống lá.

Đoạn mã minh họa thuật toán lặp có thể xử lý cây sâu mà không cần **lời gọi duyệt đệ quy**. Nó vẫn cần RAM cho **các nút của cây**, **stack tường minh** và **danh sách kết quả**.

## 10. Phân tích thời gian O(n) và bộ nhớ theo chiều cao h

Gọi `n` là số nút, `h` là **số nút trên đường dài nhất từ gốc tới lá**; cây rỗng có `h = 0`, cây một nút có `h = 1`.

### 10.1. Thời gian

Với cây thật sự (không chia sẻ nút) và mỗi lần `visit` tốn O(1):

- **Preorder:** mỗi nút được đẩy vào stack một lần, lấy ra một lần và xử lý một lần.
- **Inorder:** mỗi nút được đưa vào stack khi đi trái, rồi lấy ra để xử lý, mỗi lần một.
- **Postorder cờ:** mỗi nút được đưa vào ở trạng thái `False`, sau đó thêm trạng thái `True` và lấy ra lần nữa: số thao tác hằng số trên một nút.
- **Bộ máy ba pha:** mỗi nút đi qua ba pha, mỗi pha làm O(1) việc.
- **Postorder hai stack:** mỗi nút đi qua `s1` và `s2` một lần.

Tổng thời gian đều là **O(n)** cho n nút (và thường là Θ(n) vì phải xử lý n nút). Nếu công việc tại nút tốn O(f(node)), cần cộng chi phí ấy; ví dụ xử lý n nút không tự bảo đảm O(n) nếu mỗi lần `visit` lại quét một cây con.

### 10.2. Bộ nhớ stack

| Cách duyệt | Bộ nhớ stack phụ | Giải thích |
|---|---|---|
| Preorder một stack | **O(h)** | Giữ các nhánh phải chưa thăm dọc đường đang đi |
| Inorder một stack | **O(h)** | Giữ các tổ tiên chờ duyệt xong cây trái |
| Postorder một stack có cờ | **O(h)** | Giữ khung hẹn xử lý cha và nhánh chưa duyệt |
| Ba pha `(node, phase)` | **O(h)** | Mỗi đường DFS chứa hữu hạn khung đang mở |
| Postorder hai stack | **O(n)** | Stack thứ hai có thể tích lũy toàn bộ n nút |
| DFS đệ quy thông thường | **O(h)** | Dùng call stack của runtime |

**Vì sao O(h) với các biến thể một stack?** Trên đường đi sâu nhất, mỗi mức cây nhị phân chỉ có tối đa một nhánh còn lại cần lưu, cộng khung tiếp tục của nút trên đường ấy. Vì thế, số mục chờ đồng thời bị chặn bởi **một hệ số hằng nhân chiều cao h**.

Cận **O(h)** không có nghĩa stack luôn giữ đúng h mục. Ví dụ preorder trên cây chỉ có nhánh phải có thể có stack chỉ một mục ở mỗi bước; nhưng trên một cây với nhiều nhánh anh em chờ, stack lớn hơn. Phân tích tiệm cận sử dụng **cận trên của trường hợp xấu nhất**.

### 10.3. Cân bằng, lệch và bộ nhớ đầu ra

| Dạng cây | Quan hệ giữa h và n | Một stack DFS |
|---|---|---|
| Cây cân bằng | `h = Θ(log n)` | **O(log n)** bộ nhớ phụ |
| Cây lệch một phía | `h = Θ(n)` | **O(n)** cận trên (có thể dùng ít hơn tùy thuật toán cụ thể) |
| Cây rỗng | `n = 0, h = 0` | **O(1)** trạng thái cơ sở |

Các hàm trên trả về **danh sách n giá trị**, vì vậy còn cần **O(n)** bộ nhớ đầu ra. Tổng bộ nhớ ngoài cây đầu vào là:

```text
Một stack:    O(h + n) = O(n) nếu lưu toàn bộ kết quả
Hai stack:    O(n)     nếu lưu toàn bộ kết quả
```

Nếu thay `result.append` bằng việc **xử lý/tiêu thụ giá trị ngay tại thời điểm thăm** và không giữ dãy đầu ra, các thuật toán một stack có thể chỉ cần **O(h)** bộ nhớ phụ.

### 10.4. DFS không đệ quy và BFS dùng queue

**DFS** dùng stack LIFO, đi sâu và quay lại. **BFS/level-order** dùng queue FIFO, đi theo từng tầng. BFS thường cần **O(w)** bộ nhớ điều khiển với `w` là số nút nhiều nhất của một tầng cây (và O(n) trong trường hợp xấu nhất).

Chọn BFS không thay thế được preorder/inorder/postorder khi bài toán cần **đúng thứ tự DFS**. Tuy nhiên, khi cần xử lý các nút theo **khoảng cách từ gốc**, BFS mới là lựa chọn tự nhiên.

## 11. Ứng dụng với BST và biến đổi cây từ dưới lên

### 11.1. Inorder lặp để đọc BST tăng dần

Với BST có tính chất **khóa cây trái nhỏ hơn khóa nút, khóa cây phải lớn hơn khóa nút**, dãy inorder trái–gốc–phải được sắp tăng dần.

```python
bst = Node(
    8,
    left=Node(4, Node(2), Node(6)),
    right=Node(12, Node(10), Node(14)),
)

assert inorder_iterative(bst) == [2, 4, 6, 8, 10, 12, 14]
```

Nếu cây không thỏa bất biến BST, inorder vẫn duyệt đúng **thứ tự cấu trúc**, nhưng dãy giá trị có thể không được sắp. Nếu BST cho phép khóa trùng, quy tắc đặt khóa trùng cần được xác định, và kết quả thường là dãy **không giảm**.

### 11.2. Biến đổi bottom-up bằng postorder

Nhiều phép biến đổi cần kết quả cây con **trước** khi xử lý cha, ví dụ tính số nút của mỗi cây con:

```text
size(None) = 0
size(node) = 1 + size(node.left) + size(node.right)
```

Ta có thể dùng **postorder với cờ** rồi gán thuộc tính `subtree_size` sau khi hai con được xử lý:

```python
def annotate_subtree_sizes_iterative(root):
    if root is None:
        return 0

    stack = [(root, False)]

    while stack:
        node, expanded = stack.pop()

        if expanded:
            left_size = (
                node.left.subtree_size if node.left is not None else 0
            )
            right_size = (
                node.right.subtree_size if node.right is not None else 0
            )
            node.subtree_size = 1 + left_size + right_size
        else:
            stack.append((node, True))
            if node.right is not None:
                stack.append((node.right, False))
            if node.left is not None:
                stack.append((node.left, False))

    return root.subtree_size


assert annotate_subtree_sizes_iterative(root) == 7
assert root.subtree_size == 7
assert root.left.subtree_size == 3
assert root.right.subtree_size == 3
assert root.left.left.subtree_size == 1
```

Ở bước `expanded=True`, các cây con đã được xử lý, nên thuộc tính `subtree_size` của con đã tồn tại. Đó là **bất biến quan trọng** của cách biến đổi hậu tự.

Độ phức tạp của một lần gán kích thước cho mọi nút là **O(n) thời gian**, **O(h) stack**; ngoài ra kết quả `subtree_size` được lưu trong từng nút, tổng cộng **O(n)** dữ liệu bổ sung nếu tính các thuộc tính mới. Thuật toán không phải là “O(h) tổng bộ nhớ” nếu tính cả các thuộc tính ghi lên cây.

Nếu cần truyền dữ liệu từ cha xuống con, chẳng hạn tính độ sâu hoặc đường dẫn, ta thường chọn **preorder** vì cha được xử lý trước.

## 12. Bất biến và chứng minh tính đúng đắn

### 12.1. Preorder

**Bất biến:** stack chứa các gốc của những cây con chưa duyệt, sắp xếp sao cho gốc cây con cần thăm tiếp nằm trên đỉnh. Sau khi xử lý nút `N`, ta đẩy phải trước trái. Vì LIFO, cây trái của `N` sẽ được duyệt hết trước khi bắt đầu cây phải.

Quy nạp theo kích thước cây con cho thấy thứ tự nhận được là `[N] + preorder(left) + preorder(right)`. Không có nút bị mất: mỗi nút không phải gốc được đưa vào stack từ đúng một liên kết cha.

### 12.2. Inorder

**Bất biến:** stack lưu các tổ tiên chưa được xử lý, đang chờ phần bên trái của chúng hoàn tất. Vòng lặp đi hết về trái bảo đảm khi lấy một nút khỏi stack, **không còn nút chưa xử lý trong cây con trái** của nút ấy.

Sau khi xử lý nút, thuật toán chuyển sang cây phải. Vì thế thứ tự là `inorder(left) + [N] + inorder(right)`.

### 12.3. Postorder

**Bất biến:** một mục `(N, True)` chỉ được lấy ra sau khi tất cả phần việc của hai cây con `N.left` và `N.right` đã được lấy ra và hoàn thành. Khi chưa mở rộng, ta đưa lịch hẹn xử lý `N` **bên dưới** hai cây con. LIFO bảo đảm công việc con đi trước công việc cha.

Vì vậy thứ tự là `postorder(left) + postorder(right) + [N]`. Biến thể ba pha sử dụng cùng nguyên tắc: `phase=2` chỉ xuất hiện khi các pha xử lý cây trái/phải đã hoàn tất.

### 12.4. Phân tích kết thúc

Một cây hữu hạn không có chu trình có số nút `n` hữu hạn. Mỗi nút được đẩy vào các trạng thái hữu hạn lần (preorder/inorder một lần; postorder cờ hai lượt; ba pha ba lượt). Các vòng lặp không tạo thêm nút hay quay lại trạng thái đã hoàn tất, nên sau một số hữu hạn thao tác stack sẽ rỗng và thuật toán dừng.

Điều kiện **không có chu trình** là quan trọng: nếu một con trỏ dẫn ngược về tổ tiên, các thuật toán cây trên có thể duyệt lặp vô hạn. Muốn áp dụng cho đồ thị tổng quát, cần thêm cơ chế **đánh dấu nút đã thăm** và xác định lại hợp đồng traversal.

## 13. Những lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Preorder đẩy trái trước phải | Nhánh phải được thăm trước do LIFO | **Đẩy phải trước, trái sau** |
| Inorder xử lý nút ngay lúc đẩy | Biến thành preorder hoặc mất quy tắc trái–gốc–phải | Chỉ xử lý nút **khi pop sau khi đi hết trái** |
| Inorder dừng chỉ vì `current is None` | Bỏ các nút tổ tiên còn trong stack | Dùng `while current is not None or stack` |
| Postorder xử lý cha ngay lần đầu lấy | Thành thứ tự xử lý cha trước con | Lưu trạng thái `expanded` hoặc pha |
| Postorder chỉ thêm `(node, True)` nhưng quên thêm con | Không thăm cây con | Đặt lịch cha rồi thêm phải, trái |
| Nhầm `expanded=True` là đã xử lý cha | Bỏ xử lý cha hoặc xử lý trùng | Hiểu đây là **lịch hẹn xử lý sau con** |
| Duyệt hai stack mà coi bộ nhớ O(h) | Stack thứ hai có thể lưu n nút | Tính O(n) cho biến thể hai stack |
| Không xử lý `root=None` | Có thể pop nút rỗng rồi đọc thuộc tính | Kiểm tra cây rỗng hoặc bảo vệ vòng lặp |
| Dùng `node.value is None` để nhận biết rỗng | Bỏ qua nút có giá trị `None` hợp lệ | Kiểm tra **tham chiếu nút** bằng `is None` |
| Dùng giá trị nút làm khóa duy nhất | Bỏ sót các nút khác nhau có nhãn trùng | Xử lý theo đối tượng nút |
| Chỉ báo O(h) bộ nhớ dù trả cả danh sách | Không tính O(n) đầu ra | Tách bộ nhớ stack và bộ nhớ kết quả |
| Cho rằng không đệ quy tức O(1) bộ nhớ | Quên stack tường minh | Phân tích số trạng thái chờ |
| Thay DFS bằng BFS mà không xét hợp đồng | Thứ tự kết quả thay đổi | Chọn theo yêu cầu preorder/inorder/postorder/level-order |
| Sửa liên kết con trước khi lên lịch duyệt | Có thể mất tham chiếu nhánh chưa xử lý | Lưu tham chiếu cần thiết hoặc xác lập pha rõ ràng |
| Duyệt một DAG như cây | Nút được chia sẻ có thể bị xử lý nhiều lần | Nếu cần mỗi nút một lần, bổ sung `visited` |

## 14. Câu hỏi tự luyện và lời giải

**Bài 1 — Preorder.** Cây có gốc `M`, con trái `J`, con phải `R`; `R` có con trái `P`. Preorder dùng stack phải cho dãy gì? Khi pop `M`, đẩy con nào trước?

*Lời giải:* Dãy **`M, J, R, P`**. Khi pop `M`, **đẩy `R` trước `J`** để `J` được lấy tiếp theo.

**Bài 2 — Inorder.** Với cùng cây, inorder cho dãy nào?

*Lời giải:* **`J, M, P, R`**. Duyệt `J` trước, đến `M`, rồi cây con phải có `P` trước `R`.

**Bài 3 — Postorder.** Với cùng cây, postorder cho dãy nào?

*Lời giải:* **`J, P, R, M`**; mọi con được xử lý trước cha.

**Bài 4 — Điều kiện vòng lặp inorder.** Vì sao chỉ dùng `while current is not None` là sai?

*Lời giải:* Khi đi hết về trái, `current` thành `None` nhưng **stack vẫn còn nút cha cần xử lý**. Cần tiếp tục chừng nào `current` hoặc stack còn công việc.

**Bài 5 — Cờ postorder.** Khi lần đầu lấy `(A, False)` với hai con `B`, `C`, thứ tự push vào stack cần thế nào để cho kết quả `B, C, A`?

*Lời giải:* Đẩy **`(A, True)`, `(C, False)`, `(B, False)`** theo đúng thứ tự ấy. Do LIFO, `B` được xử lý trước `C`, cuối cùng mới `A`.

**Bài 6 — Bộ nhớ.** Một cây cân bằng có `n` nút, chiều cao `h = Θ(log n)`. Duyệt inorder lặp bằng stack cần bộ nhớ điều khiển bao nhiêu?

*Lời giải:* **O(h) = O(log n)**, chưa tính danh sách n giá trị nếu hàm trả kết quả đầy đủ.

**Bài 7 — Hai stack postorder.** Vì sao phiên bản hai stack dùng O(n) bộ nhớ phụ dù cây cân bằng?

*Lời giải:* Stack `s2` **tích lũy toàn bộ n nút** trước khi bắt đầu lấy ngược để xuất kết quả, nên riêng `s2` đã dùng O(n).

**Bài 8 — Cây lệch.** Với cây chỉ có nhánh phải `A → B → C → D`, hãy viết ba dãy duyệt.

*Lời giải:* Preorder **`A, B, C, D`**; inorder **`A, B, C, D`**; postorder **`D, C, B, A`**.

**Bài 9 — Giá trị trùng nhau.** Cây có gốc `7` và hai con đều có `value=7`. Thuật toán có thể chỉ giữ một lần giá trị 7 vì trùng nhau không?

*Lời giải:* **Không.** Ba nút khác nhau phải được xử lý, nên cả ba dãy kết quả đều chứa **ba số 7**.

**Bài 10 — Đệ quy hay lặp.** Một cây có 100.000 nút nối thành một đường duy nhất. Vì sao có thể ưu tiên DFS lặp trong Python?

*Lời giải:* Đệ quy có thể vượt giới hạn call stack của Python khi chiều sâu quá lớn. DFS lặp chuyển trạng thái sang stack tường minh, không cần 100.000 lời gọi hàm lồng nhau, nhưng vẫn cần đủ bộ nhớ.

**Bài 11 — Biến đổi cây.** Cần tính kích thước cây con ở mỗi nút bằng `1 + size(left) + size(right)`. Nên dùng thứ tự nào?

*Lời giải:* **Postorder**, vì phải biết giá trị cây con trái và phải trước khi tính nút cha. Dùng `expanded=True` để xác định khi nào được gán kết quả.

**Bài 12 — Cấu trúc dữ liệu.** Có thể thay stack bằng queue FIFO trong thuật toán preorder và vẫn bảo đảm duyệt sâu trái–phải như cũ không?

*Lời giải:* **Không nói chung.** Queue lấy phần tử vào trước, nên thường tạo thứ tự theo mức (BFS), còn stack lấy phần tử vừa đưa vào để tiếp tục khám phá sâu. Cần thuật toán khác nếu yêu cầu DFS.

**Bài 13 — Bộ nhớ kết quả.** Một hàm preorder lặp dùng stack O(h) nhưng trả danh sách n giá trị. Bộ nhớ phụ tổng cộng là gì?

*Lời giải:* **O(n + h)**, tương đương O(n) khi `h ≤ n` và cây không rỗng. Phải nêu riêng O(h) cho stack nếu đề hỏi chỉ bộ nhớ điều khiển.

**Bài 14 — Chứng minh thời gian.** Postorder một stack với cờ đôi khi xử lý cùng nút ở hai lần pop. Vì sao tổng thời gian vẫn O(n)?

*Lời giải:* Mỗi nút chỉ có **hai trạng thái**: chưa mở rộng và đã sẵn sàng xử lý. Mỗi trạng thái tốn O(1), nên có tối đa một số hằng lần thao tác trên mỗi nút và tổng O(n).

## 15. Tổng kết và nguyên tắc chọn cách duyệt

Duyệt không đệ quy bằng ngăn xếp tường minh là cách **mô phỏng DFS mà không dựa vào lời gọi hàm lồng nhau**. Với **preorder**, xử lý ngay khi pop và **đẩy phải trước trái**. Với **inorder**, đẩy các nút khi đi xuống trái, chỉ xử lý nút sau khi quay lên, rồi chuyển sang phải. Với **postorder**, cần lưu trạng thái để chỉ xử lý cha sau khi cả hai cây con đã hoàn tất.

Cả ba phép duyệt có thể đạt **O(n) thời gian**. Các cách **một stack** phù hợp dùng **O(h) bộ nhớ điều khiển** trên cây nhị phân có chiều cao `h`; riêng postorder **hai stack** có thể cần **O(n)** bộ nhớ. Nếu lưu toàn bộ n giá trị đầu ra, còn phải tính thêm **O(n)** cho kết quả. Hãy chọn cấu trúc stack và quy ước khung rõ ràng theo **thứ tự xử lý cần thiết** và **giới hạn độ sâu cây**, không chỉ vì mã lặp hay mã đệ quy trông ngắn hơn.
