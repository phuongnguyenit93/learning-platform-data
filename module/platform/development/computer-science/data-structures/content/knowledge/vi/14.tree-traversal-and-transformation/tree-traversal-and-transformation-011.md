# Duyệt Morris bằng liên kết tạm và điều kiện sử dụng an toàn

Thông thường, để **duyệt sâu (DFS)** một cây nhị phân, ta dùng **đệ quy** hoặc **stack tường minh** để nhớ đường quay lại nút cha. Hai cách này dễ hiểu nhưng cần bộ nhớ điều khiển **O(h)**, trong đó `h` là chiều cao của cây. Có cách nào vẫn duyệt toàn bộ cây với **O(1) bộ nhớ phụ điều khiển** mà không cần con trỏ `parent` không?

**Duyệt Morris (Morris traversal)** là một kỹ thuật như vậy. Nó tận dụng những liên kết `right` đang rỗng để tạo **liên kết tạm (temporary thread)** từ một nút trong cây con trái **quay về nút cha cần tiếp tục xử lý**. Khi trở về, thuật toán **xóa liên kết tạm**, trả cây về cấu trúc ban đầu.

Đổi lại lợi ích bộ nhớ là một ràng buộc nghiêm ngặt: **Morris tạm thời sửa con trỏ của cây**. Một chương trình dừng giữa chừng, gặp ngoại lệ hoặc cho tác vụ khác duyệt cây cùng lúc có thể để lại hoặc quan sát cấu trúc sai. Vì vậy, hiểu **điều kiện sử dụng an toàn** quan trọng không kém việc thuộc mã thuật toán.

Bài thuộc chương **Duyệt và biến đổi cây** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Trong nền tảng học mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, ta tiếp tục luyện cách nhận diện **bất biến, thao tác, thời gian và bộ nhớ**, đồng thời đánh giá **tính đúng đắn và an toàn** khi tối ưu cấu trúc dữ liệu.

## 1. Bài toán: duyệt cây nhưng không dùng stack O(h)

Giả sử cây nhị phân có gốc và mỗi nút chứa:

- `value`: dữ liệu cần xử lý.
- `left`: tham chiếu đến con trái hoặc `None`.
- `right`: tham chiếu đến con phải hoặc `None`.

Ví dụ:

```text
                    4
                  /   \
                 2     6
                / \   / \
               1   3 5   7
```

Ba thứ tự DFS quen thuộc trên cây này là:

| Phép duyệt | Quy tắc | Dãy kết quả |
|---|---|---|
| **Inorder** (duyệt giữa) | Trái – Gốc – Phải | `1, 2, 3, 4, 5, 6, 7` |
| **Preorder** (duyệt trước) | Gốc – Trái – Phải | `4, 2, 1, 3, 6, 5, 7` |
| **Postorder** (duyệt sau) | Trái – Phải – Gốc | `1, 3, 2, 5, 7, 6, 4` |

Cách đệ quy giữ những nút cha đang chờ xử lý trong **call stack**. Một cách lặp thông thường dùng `stack.append` và `stack.pop` để làm điều tương tự.

**Morris không lưu danh sách những nút cha đang chờ.** Thay vào đó, nó tìm một chỗ liên kết `right` đang rỗng trong cây con trái, tạo đường tạm để quay về cha, rồi xóa đường này sau khi sử dụng.

Đối với **inorder và preorder**, ý tưởng giống nhau; chỉ khác **thời điểm thực hiện `visit`**. Đối với **postorder**, cần thêm thao tác đảo tạm rồi khôi phục một đường `right` để xử lý các nút theo thứ tự ngược.

## 2. Tiền nhiệm inorder và liên kết tạm là gì?

Với một nút `current` có cây con trái, **tiền nhiệm theo inorder** (*inorder predecessor*) của nó là **nút nằm ngoài cùng bên phải của cây con trái**.

Ví dụ:

```text
                 current = 8
                 /
                4
               / \
              2   6
                   \
                    7

Tiền nhiệm inorder của 8 là nút 7.
```

Nếu cây không bị sửa, nút `7` là nút phải nhất của cây con trái `8`, nên `7.right` bằng `None`. Thuật toán Morris tạm thiết lập:

```text
7.right = 8
```

Liên kết này được gọi là **thread**: sau khi duyệt xong phần cây bên trái, nó giúp thuật toán quay về `8` mà không phải giữ `8` trên stack.

### Phải biết khi nào thread là cũ hay mới

Ta tìm tiền nhiệm bằng quy tắc:

```text
pred = current.left

while pred.right != NULL and pred.right != current:
    pred = pred.right
```

Sau vòng lặp có **hai trường hợp hợp lệ**:

1. `pred.right is None`: **chưa tạo thread** từ `pred` về `current`. Ta có thể tạo thread rồi đi vào cây trái.
2. `pred.right is current`: **đã quay về từ cây trái** theo thread trước đó. Ta phải xóa thread và tiếp tục đúng thứ tự duyệt.

Ta không được tiếp tục đi theo `pred.right` khi nó **trỏ về current**, vì đó chính là liên kết tạm tạo chu trình.

### Sơ đồ tạo và tháo thread

```text
Trước khi đi vào cây trái:

       current
        /
       L
        \
         ...
           \
            pred ──right──> None

Tạo:
    pred.right = current

Sau khi duyệt hết cây trái:
    ... -> pred -> current    (quay lại qua thread)

Phát hiện pred.right is current:
    pred.right = None         (KHÔI PHỤC)
```

Trong cây ban đầu, `pred.right` là `None`. Vì vậy, **xóa đúng thread** đồng nghĩa khôi phục chính giá trị trước khi sửa. Nếu chương trình không trở lại điểm tháo thread, cây có thể còn một cạnh tạm tạo chu trình.

## 3. Morris inorder: thuật toán cốt lõi

Inorder có thứ tự **Trái – Gốc – Phải**. Ta giữ con trỏ `current`, bắt đầu từ gốc.

**Trường hợp A — current không có con trái:**

- Không có cây trái cần chờ.
- Xử lý `current` ngay.
- Chuyển `current = current.right`. Trường `right` này có thể là con phải thật hoặc **thread tạm quay về tổ tiên**.

**Trường hợp B — current có con trái:**

- Tìm `pred` là nút phải nhất của cây trái, dừng ở `None` hoặc thread trỏ về `current`.
- Nếu `pred.right is None`: đặt `pred.right = current` rồi đi trái; **chưa xử lý current**.
- Nếu `pred.right is current`: cây trái đã xong; đặt `pred.right = None`, **xử lý current**, rồi đi phải.

### Giả mã

```text
MORRIS_INORDER(root):
    current = root

    while current != NULL:
        if current.left == NULL:
            VISIT(current)
            current = current.right

        else:
            pred = current.left

            while pred.right != NULL and pred.right != current:
                pred = pred.right

            if pred.right == NULL:
                pred.right = current       # Tạo liên kết tạm.
                current = current.left

            else:
                pred.right = NULL          # Xóa liên kết tạm.
                VISIT(current)
                current = current.right
```

**Vị trí xử lý nút là trọng tâm:** nếu có cây trái, `current` chỉ được xử lý khi **quay lại lần hai**, sau khi cây trái đã được duyệt.

## 4. Truy vết Morris inorder từng bước

Xét lại cây:

```text
                    4
                  /   \
                 2     6
                / \   / \
               1   3 5   7
```

Ký hiệu `x → y` là thread tạm qua trường `x.right`, không phải cạnh của cây gốc.

| Lượt | `current` | Hành động | Thread còn tồn tại sau lượt | Kết quả đã xử lý |
|---:|---:|---|---|---|
| 1 | 4 | Tìm pred=3; tạo `3 → 4`; đi trái đến 2 | `3 → 4` | `[]` |
| 2 | 2 | Tìm pred=1; tạo `1 → 2`; đi trái đến 1 | `3 → 4`, `1 → 2` | `[]` |
| 3 | 1 | Không có trái; xử lý 1; theo `1.right` về 2 | `3 → 4`, `1 → 2` | `[1]` |
| 4 | 2 | Thấy `1.right is 2`; xóa `1 → 2`; xử lý 2; đi phải đến 3 | `3 → 4` | `[1, 2]` |
| 5 | 3 | Không có trái; xử lý 3; theo `3.right` về 4 | `3 → 4` | `[1, 2, 3]` |
| 6 | 4 | Thấy `3.right is 4`; xóa `3 → 4`; xử lý 4; đi phải đến 6 | Không có | `[1, 2, 3, 4]` |
| 7 | 6 | Tạo `5 → 6`; đi trái đến 5 | `5 → 6` | `[1, 2, 3, 4]` |
| 8 | 5 | Không có trái; xử lý 5; quay về 6 | `5 → 6` | `[1, 2, 3, 4, 5]` |
| 9 | 6 | Xóa `5 → 6`; xử lý 6; đi phải đến 7 | Không có | `[1, 2, 3, 4, 5, 6]` |
| 10 | 7 | Không có trái; xử lý 7; kết thúc | Không có | `[1, 2, 3, 4, 5, 6, 7]` |

Kết quả là `1, 2, 3, 4, 5, 6, 7` — đúng inorder.

Đặc biệt, ở cuối lượt 10, **không còn bất kỳ thread nào**. Đó là điều kiện cần của một lượt Morris hoàn chỉnh trên cây hợp lệ, không có ngoại lệ và không bị ngắt ngang.

### Bất biến khi đi vào cây trái

Khi tạo `pred.right = current`, ta biết trường ấy **đang rỗng** trong cây gốc. Ta chưa làm mất con phải thật. Sau khi cây trái xong, đường đi đúng sẽ quay đến `current`; khi phát hiện chính liên kết ấy, ta khôi phục `None`.

Bất biến này phân biệt Morris với việc tùy ý “nối các nút thành danh sách”. Morris dùng **liên kết chỉ tồn tại tạm** để điều khiển traversal và phải xóa chúng đúng lúc.

## 5. Python: Morris inorder hoàn chỉnh

Dưới đây là cài đặt **thuần Morris**, không gọi đệ quy và không tạo stack tường minh.

```python
class Node:
    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right


def morris_inorder(root):
    result = []
    current = root

    while current is not None:
        if current.left is None:
            result.append(current.value)
            current = current.right
            continue

        pred = current.left
        while pred.right is not None and pred.right is not current:
            pred = pred.right

        if pred.right is None:
            # Lần đầu gặp current: hẹn quay lại sau cây trái.
            pred.right = current
            current = current.left
        else:
            # Lần thứ hai: khôi phục thread trước khi visit.
            pred.right = None
            result.append(current.value)
            current = current.right

    return result


root = Node(
    4,
    left=Node(2, Node(1), Node(3)),
    right=Node(6, Node(5), Node(7)),
)

assert morris_inorder(root) == [1, 2, 3, 4, 5, 6, 7]
assert morris_inorder(None) == []
assert morris_inorder(Node("X")) == ["X"]
```

Ở bài toán **chỉ cần xuất dãy**, `result` có `n` giá trị, do đó toàn bộ hàm vẫn dùng **O(n) bộ nhớ kết quả**. Cụm từ “Morris dùng O(1) bộ nhớ” thường **chỉ bộ nhớ điều khiển thêm**, **không tính đầu ra**.

Nếu thay `result.append` bằng một thao tác tiêu thụ tức thời không cần giữ dãy kết quả, thuật toán không cần stack hoặc bộ nhớ theo chiều cao. Nhưng khi thao tác tiêu thụ có thể ném ngoại lệ, cần áp dụng các biện pháp an toàn ở phần sau.

### Không dùng `yield` một cách tùy tiện

Việc chuyển ngay dòng `result.append(...)` thành `yield current.value` để tạo generator **không tự động an toàn**. Nếu generator tạm dừng sau khi yield, có thể vẫn còn những thread tạm trong cây. Một tác vụ khác đọc cây trong khoảng thời gian đó có thể nhìn thấy liên kết sai. Nếu người gọi không duyệt generator đến hết, thread có thể không được khôi phục.

Vì vậy, không phát hành một Morris generator trên **cây dùng chung** nếu chưa thiết kế đầy đủ cơ chế sở hữu độc quyền, giải phóng tài nguyên và xử lý hủy duyệt.

## 6. Morris preorder: khác nhau ở thời điểm visit

Preorder có thứ tự **Gốc – Trái – Phải**. Nó vẫn dùng tiền nhiệm `pred` và các thread giống inorder, nhưng xử lý nút cha **ngay lần gặp đầu**.

Quy tắc:

- Nếu `current.left is None`: xử lý `current` và đi theo `current.right`.
- Nếu có cây trái và `pred.right is None`: **xử lý current trước**, tạo thread rồi đi trái.
- Nếu `pred.right is current`: **chỉ xóa thread**, không xử lý lại current, sau đó đi phải.

### Giả mã

```text
MORRIS_PREORDER(root):
    current = root

    while current != NULL:
        if current.left == NULL:
            VISIT(current)
            current = current.right

        else:
            pred = current.left

            while pred.right != NULL and pred.right != current:
                pred = pred.right

            if pred.right == NULL:
                VISIT(current)             # Gốc trước cây trái.
                pred.right = current
                current = current.left

            else:
                pred.right = NULL          # Chỉ khôi phục.
                current = current.right
```

**Không được xử lý current ở cả hai lần gặp** khi current có cây trái: làm vậy sẽ khiến một nút xuất hiện hai lần trong kết quả.

### Python: Morris preorder

```python
def morris_preorder(root):
    result = []
    current = root

    while current is not None:
        if current.left is None:
            result.append(current.value)
            current = current.right
            continue

        pred = current.left
        while pred.right is not None and pred.right is not current:
            pred = pred.right

        if pred.right is None:
            result.append(current.value)
            pred.right = current
            current = current.left
        else:
            pred.right = None
            current = current.right

    return result


assert morris_preorder(root) == [4, 2, 1, 3, 6, 5, 7]
```

Trên cây mẫu, khi gặp nút `4` lần đầu, preorder ghi `4` rồi mới đi vào `2`. Inorder phải chờ đến khi `1, 2, 3` đã xong mới ghi `4`. **Liên kết tạm và cách đi cây giống nhau; chỉ vị trí `visit` thay đổi.**

## 7. So sánh inorder và preorder qua cùng một nút

Xét một nút `N` có cây trái không rỗng:

| Sự kiện | Morris inorder | Morris preorder |
|---|---|---|
| Lần đầu gặp `N`, chưa có thread | Tạo thread; đi trái | **Visit N**; tạo thread; đi trái |
| Trong lúc đi hết cây trái | Chưa visit `N` | `N` đã được visit |
| Quay về `N` theo thread | Xóa thread; **visit N** | Xóa thread; không visit lại |
| Sau khi đã xóa thread | Đi sang cây phải | Đi sang cây phải |
| `N` không có con trái | Visit N rồi đi phải | Visit N rồi đi phải |

Tổng số nút được xử lý vẫn đúng **một lần** cho mỗi phép duyệt. Với cây không có con trái, hai phép đều xử lý ngay vì chẳng có cây trái cần xét trước.

### Cây tìm kiếm nhị phân và thứ tự tăng

Nếu cây là **BST** với bất biến khóa cây trái nhỏ hơn khóa nút, khóa cây phải lớn hơn khóa nút, **Morris inorder** trả các khóa theo thứ tự tăng dần.

Tính chất được sắp của kết quả là nhờ **bất biến BST**, không phải vì Morris tự sắp xếp dữ liệu. Trên cây nhị phân bất kỳ, Morris inorder vẫn đúng thứ tự **Trái – Gốc – Phải** nhưng giá trị có thể không tăng.

```python
bst = Node(
    8,
    left=Node(4, Node(2), Node(6)),
    right=Node(12, Node(10), Node(14)),
)

assert morris_inorder(bst) == [2, 4, 6, 8, 10, 12, 14]
assert morris_preorder(bst) == [8, 4, 2, 6, 12, 10, 14]
```

**Quan trọng:** thao tác Morris tạm sửa các liên kết `right` kể cả khi về mặt nghiệp vụ ta chỉ muốn “đọc” BST. Nó không phù hợp với một cấu trúc BST chỉ đọc, bất biến, hoặc đang được thao tác đồng thời nếu không có cơ chế bảo vệ phù hợp.

## 8. Morris postorder: khó hơn do phải xử lý con trước cha

Postorder có thứ tự **Trái – Phải – Gốc**. Morris inorder/preorder chỉ cần visit nút khi gặp lần đầu hoặc khi quay lại từ cây trái. Với postorder, ta phải trì hoãn việc xử lý nút đến khi **cả cây trái và cây phải** đã xong.

Một kỹ thuật Morris postorder là:

1. Tạo **nút giả (dummy root)** có `dummy.left = root`.
2. Duyệt theo cơ chế tạo thread và quay về tương tự inorder.
3. Khi phát hiện một thread từ `pred` quay về `current`, **xóa thread**, rồi xử lý các nút trên **đường biên phải của cây con trái theo chiều ngược lại**.
4. Đảo tạm các con trỏ `right` trên đường ấy để có thể đi ngược **không dùng stack**, sau đó **đảo lại ngay** để khôi phục cấu trúc.

### Vì sao cần nút giả?

Nút giả đặt cây gốc ban đầu ở vị trí **con trái** của một nút mới. Như vậy, khi xử lý xong cây ban đầu, thuật toán vẫn có một lần **quay về nút giả** để xuất những nút cuối cùng, bao gồm **gốc thật**, theo postorder.

```text
         dummy
          /
         4
       /   \
      2     6
     / \   / \
    1   3 5   7

Postorder thật:
1, 3, 2, 5, 7, 6, 4

dummy không được đưa vào kết quả.
```

### Đường biên phải và việc đảo tạm

Xét cây con:

```text
             4
              \
               6
                \
                 7
```

Đường `right` đi từ `4` đến `7` là:

```text
4 -> 6 -> 7 -> None
```

Để xuất postorder của một phần đã hoàn tất, ta có thể cần thứ tự **7, 6, 4**. Nếu tạm đảo các liên kết trên đường:

```text
7 -> 6 -> 4 -> None
```

thì có thể đi xuôi từ `7` để xử lý **7, 6, 4**, rồi **đảo lại lần thứ hai** nhằm phục hồi đường gốc `4 -> 6 -> 7`.

**Không được bỏ bước đảo lại.** Đây là một loại thay đổi tạm **khác** với thread: ngoài việc tạo/xóa liên kết từ tiền nhiệm lên tổ tiên, Morris postorder còn đảo chiều một số liên kết `right` trong quá trình xuất nút.

## 9. Python: Morris postorder với đảo và khôi phục đường phải

Đoạn mã dưới đây dùng một hàm đảo đường `right` **kết thúc bằng `None`**. Trước khi gọi, thuật toán đã xóa thread ở cuối đường, nên đường bên phải đang xét kết thúc bằng `None`.

```python
def _reverse_right_chain(start):
    """Đảo liên kết right của một chuỗi kết thúc bằng None."""
    previous = None
    current = start

    while current is not None:
        next_node = current.right
        current.right = previous
        previous = current
        current = next_node

    return previous


def _append_right_boundary_reversed(start, output):
    """Xuất từ nút phải nhất trở về start, rồi hoàn nguyên."""
    reversed_head = _reverse_right_chain(start)

    try:
        current = reversed_head
        while current is not None:
            output.append(current.value)
            current = current.right
    finally:
        # Khôi phục ngay cả nếu append giá trị trên đường này lỗi.
        # Các thread ở tổ tiên (nếu có) vẫn cần được xét riêng.
        _reverse_right_chain(reversed_head)


def morris_postorder(root):
    dummy = Node(None, left=root)
    result = []
    current = dummy

    while current is not None:
        if current.left is None:
            current = current.right
            continue

        pred = current.left
        while pred.right is not None and pred.right is not current:
            pred = pred.right

        if pred.right is None:
            pred.right = current
            current = current.left
        else:
            # Hoàn tất cây con trái, gỡ thread trước khi đảo biên.
            pred.right = None
            _append_right_boundary_reversed(current.left, result)
            current = current.right

    return result


assert morris_postorder(root) == [1, 3, 2, 5, 7, 6, 4]
assert morris_postorder(None) == []
assert morris_postorder(Node("X")) == ["X"]
```

Trong `_append_right_boundary_reversed`, `finally` cố gắng khôi phục **đường đang bị đảo** nếu `output.append` gây lỗi. Tuy nhiên, **đây chưa phải bảo đảm hoàn nguyên toàn bộ cây khi có ngoại lệ**: những thread ở các tổ tiên khác có thể vẫn tồn tại. Không nên hiểu `finally` cục bộ này là một lớp bảo vệ đầy đủ cho Morris postorder.

### Truy vết khái niệm postorder trên cây nhỏ

```text
       A
      / \
     B   C
```

- `dummy` tạo thread từ phần phải nhất của toàn cây quay về `dummy`.
- Khi hoàn tất cây con trái của `A`, thuật toán xử lý nút `B`.
- Khi quay về `dummy` sau khi đi qua cả `B` và `C`, biên phải của cây thật là `A → C`.
- Đảo biên phải, xử lý `C` rồi `A`, sau đó đảo lại.

Kết quả: **`B, C, A`**. Nút `dummy` không xuất hiện.

## 10. Kiểm tra cây không bị đổi sau mỗi phép duyệt

Vì Morris có tác dụng phụ tạm thời, chỉ so sánh dãy kết quả **chưa đủ**. Cần kiểm tra cấu trúc **sau khi hàm kết thúc bình thường**.

Ta viết một hàm kiểm tra phục vụ **test trên cây nhỏ**, dùng đệ quy độc lập để tạo chữ ký cấu trúc:

```python
def tree_signature(node):
    if node is None:
        return ("N",)

    return (
        "V",
        node.value,
        tree_signature(node.left),
        tree_signature(node.right),
    )


test_tree = Node(
    4,
    left=Node(2, Node(1), Node(3)),
    right=Node(6, Node(5), Node(7)),
)

before = tree_signature(test_tree)

assert morris_inorder(test_tree) == [1, 2, 3, 4, 5, 6, 7]
assert tree_signature(test_tree) == before

assert morris_preorder(test_tree) == [4, 2, 1, 3, 6, 5, 7]
assert tree_signature(test_tree) == before

assert morris_postorder(test_tree) == [1, 3, 2, 5, 7, 6, 4]
assert tree_signature(test_tree) == before

# Cùng một cây có thể dùng lại sau các lượt Morris đã hoàn tất.
assert morris_inorder(test_tree) == [1, 2, 3, 4, 5, 6, 7]
assert tree_signature(test_tree) == before
```

Hàm `tree_signature` chỉ dành cho kiểm thử: nó **dùng đệ quy** và tạo dữ liệu O(n), không thuộc phân tích bộ nhớ O(1) của Morris. Nó cũng có thể không kết thúc nếu chạy trên cây **đang có thread chưa gỡ**, vì khi ấy có thể xuất hiện chu trình.

Trong chương trình thực, tốt hơn là so sánh danh tính liên kết hoặc có kiểm tra chống chu trình khi kiểm tra dữ liệu đáng ngờ, thay vì đệ quy mù trên một cấu trúc có thể đã hỏng.

## 11. Chứng minh đúng thứ tự và tính hoàn nguyên

### 11.1. Bất biến quan trọng của Morris inorder

Trong lúc duyệt, với mỗi `current` có cây trái:

- Nếu `pred.right is None`, cây trái của `current` **chưa được đi hết trong lượt này**. Ta tạo thread từ `pred` về `current` để có đường trở lại.
- Nếu `pred.right is current`, ta đã đi hết phần cần thăm trong cây trái của `current`. Khi gặp lại `current`, xóa thread trước khi đi sang cây phải.
- Một nút có con trái được visit **đúng ở lần quay về**; một nút không có con trái được visit ngay khi tới.

Với cây hữu hạn và đúng giả định cấu trúc, mỗi nút được xử lý đúng một lần theo thứ tự **Trái – Gốc – Phải**.

### 11.2. Bất biến cho Morris preorder

Các thread được tạo/xóa ở cùng những thời điểm, nhưng `visit(current)` diễn ra:

- Khi tới nút không có con trái; hoặc
- Khi gặp **lần đầu** nút có con trái, trước khi đi sâu.

Khi quay về qua thread, chỉ xóa thread và đi phải. Vì vậy kết quả đúng **Gốc – Trái – Phải**, không xử lý trùng.

### 11.3. Bất biến hoàn nguyên

Mỗi thread `pred.right = current` được tạo **chỉ khi `pred.right` là `None`**. Khi gặp lại `current` lần hai, thuật toán nhận ra thread bằng kiểm tra **đồng nhất đối tượng** `pred.right is current` và khôi phục `pred.right = None`.

Với một lượt duyệt **đến hết bình thường**, không có thao tác ngoài sửa cấu trúc và không có ngoại lệ, mỗi thread đã tạo đều được gỡ. Mỗi đường biên phải bị đảo trong postorder cũng được đảo lại trước khi tiếp tục. Do đó **cấu trúc cây sau cùng** bằng cấu trúc cây ban đầu.

**Hạn chế quan trọng:** đây là bảo đảm về **lúc kết thúc đúng thuật toán**, không phải bảo đảm cây luôn giống ban đầu ở **mọi thời điểm** giữa các bước. Trong khi Morris chạy, cây có thể tạm mang thread tạo chu trình.

## 12. Vì sao thời gian vẫn O(n) dù có vòng tìm predecessor?

Mã Morris có vòng lặp ngoài và vòng lặp trong tìm nút phải nhất:

```text
while pred.right != NULL and pred.right != current:
    pred = pred.right
```

Thoạt nhìn, với mỗi `current` ta có thể phải đi qua nhiều nút trên nhánh phải, nên dễ kết luận sai rằng thời gian là O(n²). Nhưng các lượt tìm tiền nhiệm có cấu trúc đặc biệt.

### Đếm tổng công việc trên các liên kết

- Mỗi nút được chọn làm `current` một số lần hằng số (đối với nút có cây trái, thường **hai lần**: tạo và gỡ thread).
- Mỗi thread được **tạo đúng một lần** và **gỡ đúng một lần**.
- Khi tìm `pred` cho một `current`, ta đi theo **đường phải nhất của cây con trái**. Đường này được khảo sát khi tạo thread và lặp lại khi gỡ thread.
- Các lần đi qua những đường phải nhất ấy có **tổng độ dài O(n)** trên cây nhị phân: một cạnh phải thật không cần bị quét lặp vô hạn qua các lượt trở lại, mà tham gia một số lần hằng số trong cách phân rã các đường tiền nhiệm.

Vì vậy, **tổng thời gian Morris inorder và preorder là Θ(n)** với thao tác visit O(1), dù một lần tìm predecessor riêng lẻ có thể mất O(h).

### Morris postorder cũng O(n)

Postorder bổ sung việc đảo tạm và đảo lại các đường biên phải. Mỗi đường biên được xử lý theo những mốc hoàn thành cây con; tổng số bước trên các đường biên phải qua toàn bộ cây vẫn **O(n)** theo cùng kiểu lập luận về cạnh và các lượt đi hạn chế.

Do đó, postorder cũng **O(n) thời gian** theo số nút khi thao tác xử lý nút là O(1).

### Bộ nhớ điều khiển

| Phương pháp | Thời gian | Bộ nhớ điều khiển thêm | Có sửa cây trong lúc chạy? |
|---|---:|---:|---|
| DFS đệ quy | O(n) | O(h) call stack | Không bắt buộc |
| DFS lặp bằng stack | O(n) | O(h) stack | Không bắt buộc |
| **Morris inorder** | **O(n)** | **O(1)** | **Có: thread tạm** |
| **Morris preorder** | **O(n)** | **O(1)** | **Có: thread tạm** |
| **Morris postorder** | **O(n)** | **O(1)** | **Có: thread và đảo đường tạm** |

Giả định các hàm Morris có một vài con trỏ/biến điều khiển và **không lưu stack khôi phục**. Nếu hàm trả về danh sách `n` giá trị như các ví dụ Python, **bộ nhớ đầu ra là O(n)**.

**O(1) chỉ là một dạng đánh đổi**: ta tiết kiệm stack vì tận dụng chính các con trỏ trong cây làm nơi lưu đường quay về.

## 13. Điều kiện sử dụng an toàn: không chỉ cần đúng thuật toán

Một phép duyệt Morris phù hợp khi tất cả các điều kiện sau được bảo đảm:

1. **Cấu trúc đầu vào là cây nhị phân hợp lệ**, không có chu trình hay nút dùng chung giữa nhiều cha theo định nghĩa cây.
2. **Các liên kết `left` và `right` được phép thay đổi tạm**, không phải cấu trúc bất biến/chỉ đọc.
3. Trong suốt lượt duyệt, ta có **quyền truy cập độc quyền** với các thao tác dựa trên cấu trúc, hoặc có cơ chế khóa ngăn tất cả các tác vụ khác đọc/ghi cây đang mang thread.
4. Lượt duyệt chạy **đến hết**, không có `break`, `return` sớm, exception hoặc hủy ngang làm bỏ qua các bước gỡ thread.
5. Người viết thuật toán hiểu chính xác những vị trí có thể còn thread, và **phục hồi mọi thay đổi** trước khi phát hành quyền truy cập lại cho tác vụ khác.
6. Nếu cần xử lý ngoại lệ, phải có **cơ chế dọn dẹp được thiết kế và kiểm chứng** hoặc chọn giải pháp không sửa cây.

### 13.1. Cây dùng chung và vấn đề đồng thời

Trong lúc tồn tại thread:

```text
pred.right -> ancestor
```

một hàm duyệt cây thông thường có thể lần theo `right` rồi quay về tổ tiên, tạo chu trình. Điều này có thể gây lặp vô hạn, đếm trùng hoặc đọc sai cấu trúc. Một tác vụ khác có thể nhầm thread là liên kết con phải thật rồi sửa/xóa nhầm.

**Không nên chạy Morris đồng thời với DFS/BFS thông thường, thao tác thêm/xóa, kiểm tra cây, tuần tự hóa hoặc một lượt Morris khác trên cùng cây**, trừ khi có cơ chế đồng bộ và thiết kế riêng chứng minh được an toàn.

Một khóa truy cập phải bảo vệ **toàn bộ thời gian tạo/khôi phục thread**, không chỉ riêng thời điểm `visit`. Nếu việc duyệt không cần thay đổi cây, đệ quy hoặc stack tường minh thường dễ duy trì an toàn hơn.

### 13.2. Ngoại lệ hoặc dừng sớm

Đoạn mã sau là **nguy hiểm** nếu được chèn vào giữa vòng Morris khi thread còn tồn tại:

```python
# Ví dụ ý tưởng không an toàn, KHÔNG phải hàm hoàn chỉnh:
#
# if current.value == target:
#     return current        # Có thể bỏ lại thread tạm.
```

Tương tự:

- `break` khỏi vòng lặp trước khi gỡ hết thread.
- Callback `visit` ném exception.
- Bộ cấp phát bộ nhớ gặp lỗi khi thêm vào `result`.
- Generator được đóng khi chưa duyệt đến hết.
- Hủy tác vụ hoặc dừng tiến trình giữa chừng.

Không phải sự cố nào cũng cho phép `finally` chạy; ví dụ tiến trình bị chấm dứt cưỡng bức không bảo đảm cơ hội dọn dẹp. Khi ứng dụng cần cây **luôn nhất quán cho bên đọc**, bản thân cơ chế thread tạm có thể không đáp ứng yêu cầu.

### 13.3. Mã hóa cây hoặc truy vấn đệ quy khi Morris đang chạy

Không nên gọi từ callback của Morris một hàm `same_tree`, `height`, `serialize` hoặc duyệt đệ quy qua liên kết `right` khi thread còn tồn tại. Những hàm ấy thường giả định mọi `right` đang là liên kết con thật, nên có thể gặp chu trình hoặc thu được kết quả sai.

Trong các phiên bản trả danh sách, `result.append(node.value)` đơn thuần **không tự duyệt cấu trúc**, nên phù hợp hơn cho ví dụ. Tuy nhiên nó không giải quyết hoàn toàn vấn đề ngoại lệ cấp phát.

## 14. Phiên bản ưu tiên khôi phục khi callback ném ngoại lệ

Nếu ứng dụng **bắt buộc dùng callback** có thể ném ngoại lệ nhưng vẫn muốn thử Morris inorder, có thể giữ một danh sách những thread đã tạo mà chưa gỡ.

Giải pháp này dùng `try/finally` để xóa thread còn tồn tại khi thoát bất thường. **Đánh đổi:** danh sách theo dõi tốn **O(h)** bộ nhớ ở trường hợp xấu nhất, nên **không còn là Morris O(1) bộ nhớ phụ thuần túy**.

### Mã minh họa

```python
def morris_inorder_guarded(root, visit):
    """Inorder với danh sách khôi phục thread khi visit ném lỗi."""
    current = root
    active_threads = []  # Các cặp (pred, owner) còn đang nối tạm.

    try:
        while current is not None:
            if current.left is None:
                visit(current.value)
                current = current.right
                continue

            pred = current.left
            while pred.right is not None and pred.right is not current:
                pred = pred.right

            if pred.right is None:
                # Ghi nhận trước khi sửa, tránh lỗi append bỏ thread lạc.
                active_threads.append((pred, current))
                pred.right = current
                current = current.left
            else:
                pred.right = None

                # Các thread đang mở được gỡ theo thứ tự LIFO.
                if not active_threads or active_threads[-1][0] is not pred:
                    raise ValueError("Trạng thái thread không nhất quán")
                active_threads.pop()

                visit(current.value)
                current = current.right

    finally:
        # Dọn những thread chưa hoàn nguyên nếu callback ném lỗi.
        for pred, owner in reversed(active_threads):
            if pred.right is owner:
                pred.right = None


def small_tree():
    return Node(
        4,
        left=Node(2, Node(1), Node(3)),
        right=Node(6, Node(5), Node(7)),
    )


safe_root = small_tree()
before = tree_signature(safe_root)
visited = []


def visit_or_fail(value):
    if value == 3:
        raise RuntimeError("Dừng xử lý giả lập")
    visited.append(value)


try:
    morris_inorder_guarded(safe_root, visit_or_fail)
except RuntimeError:
    pass

# Dù callback lỗi, những thread còn được theo dõi đã được gỡ.
assert tree_signature(safe_root) == before
assert morris_inorder(safe_root) == [1, 2, 3, 4, 5, 6, 7]
```

**Giới hạn của ví dụ guarded:**

- Nó chỉ xử lý các lỗi **thông thường có thể unwind đến `finally`** và giả định cây không bị sửa từ một nơi khác.
- Nó không làm thao tác callback được hoàn tác; ví dụ nếu callback đã ghi tệp thì `finally` không tự xóa những gì đã ghi.
- Nó không làm Morris an toàn khi nhiều luồng cùng truy cập, hoặc khi tiến trình chết mà không chạy cleanup.
- Nếu ứng dụng cần mức bảo đảm mạnh, thuật toán không sửa cây dùng **stack tường minh** vẫn là lựa chọn đơn giản và dễ kiểm chứng hơn.
- `active_threads` có thể dài tỉ lệ với chiều cao cây, nên chi phí bộ nhớ điều khiển là **O(h)**, thay vì O(1).

Cơ chế guarded được trình bày để thấy **đánh đổi giữa tiết kiệm bộ nhớ và khả năng khôi phục khi gặp lỗi**, không phải khuyến nghị mặc định dùng Morris trong mọi hệ thống.

## 15. Không thể thay mọi truy vấn đệ quy bằng Morris

Morris đặc biệt phù hợp với **thăm mỗi nút theo một thứ tự DFS xác định**. Nhưng không phải bài toán nào trên cây cũng được giải đơn giản bằng cách chỉ thay traversal:

- **Tính kích thước cây**: có thể đếm một lần mỗi nút trong một lượt Morris.
- **Đọc các khóa BST theo thứ tự**: Morris inorder cho đúng thứ tự khóa; tuy vậy vẫn cần bảo đảm độc quyền trên cây trong khi chạy.
- **Tính thống kê cần hai kết quả con**, như `height(node) = 1 + max(height(left),height(right))`: duyệt xong nút theo postorder chưa tự động cung cấp nơi lưu tất cả kết quả trung gian. Nếu không được gắn cache vào nút hoặc dùng bộ nhớ phụ, vẫn cần thiết kế thêm cách tổng hợp.
- **Cây bất biến/chỉ đọc**: không được đổi liên kết, nên Morris cổ điển không đáp ứng ràng buộc.
- **Cây có parent pointer**: có thể có cách duyệt O(1) bộ nhớ điều khiển **không cần tạo thread** nếu tận dụng quan hệ cha–con, nhưng đó là thuật toán với giả định khác.
- **DAG hoặc đồ thị**: cùng một nút có thể có nhiều cha hoặc tồn tại chu trình, nên cơ chế thread của cây nhị phân không được áp dụng trực tiếp.

Chọn cấu trúc dữ liệu không chỉ theo cận O(1) hay O(h), mà còn theo **quyền sửa đổi cấu trúc**, tính đồng thời, yêu cầu dừng sớm và độ khó kiểm chứng bất biến.

## 16. Những trường hợp biên cần thử

| Đầu vào | Inorder | Preorder | Postorder | Chú ý |
|---|---|---|---|---|
| Cây rỗng | `[]` | `[]` | `[]` | Không có thread nào |
| Một nút `X` | `[X]` | `[X]` | `[X]` | Nút giả của postorder không vào kết quả |
| Chỉ có nhánh phải `A → B → C` | `A,B,C` | `A,B,C` | `C,B,A` | Inorder/preorder đi qua các `right` thật |
| Chỉ có nhánh trái `A ← B ← C` | `C,B,A` | `A,B,C` | `C,B,A` | Có nhiều thread lồng nhau |
| Cây BST cân bằng | Khóa tăng | Gốc trước | Lá trước | Kiểm tra với thuật toán stack |
| Hai nút có nhãn bằng nhau | Vẫn thăm từng nút | Vẫn thăm từng nút | Vẫn thăm từng nút | Dùng **đồng nhất nút** khi phát hiện thread |

### Kiểm thử cây lệch và giá trị trùng

```python
right_chain = Node("A", right=Node("B", right=Node("C")))
left_chain = Node("A", left=Node("B", left=Node("C")))
duplicates = Node("X", Node("X"), Node("X"))

assert morris_inorder(right_chain) == ["A", "B", "C"]
assert morris_preorder(right_chain) == ["A", "B", "C"]
assert morris_postorder(right_chain) == ["C", "B", "A"]

assert morris_inorder(left_chain) == ["C", "B", "A"]
assert morris_preorder(left_chain) == ["A", "B", "C"]
assert morris_postorder(left_chain) == ["C", "B", "A"]

assert morris_inorder(duplicates) == ["X", "X", "X"]
assert morris_preorder(duplicates) == ["X", "X", "X"]
assert morris_postorder(duplicates) == ["X", "X", "X"]
```

Mọi hàm dùng `pred.right is current` để nhận ra **cùng đối tượng nút**, không dùng `pred.value == current.value`. Nhãn trùng không làm hỏng việc nhận diện thread.

### So sánh kết quả bằng thuật toán stack

Để kiểm thử một triển khai Morris, nên chuẩn bị một bộ duyệt **không sửa cây** làm “oracle” trên nhiều dạng cây. Ví dụ inorder dùng stack:

```python
def inorder_with_stack(root):
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


sample = small_tree()
before = tree_signature(sample)

expected = inorder_with_stack(sample)
assert morris_inorder(sample) == expected
assert tree_signature(sample) == before
```

Phép so sánh kết quả giúp phát hiện sai thứ tự. Phép so sánh cấu trúc sau lượt hoàn thành giúp phát hiện một số lỗi **bỏ quên thread**. Hai kiểm tra bổ sung cho nhau.

## 17. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Quên kiểm tra `pred.right is current` | Có thể theo thread thành vòng lặp | Dừng tìm predecessor khi gặp `None` **hoặc current** |
| Tạo thread khi `pred.right` là con phải thật | Ghi đè liên kết gốc, mất cây con | Chỉ tạo khi `pred.right is None` |
| Không xóa thread khi quay về | Cây bị để lại chu trình, duyệt sau sai | Khôi phục `pred.right = None` trước khi tiếp tục |
| Inorder visit ngay lần đầu ở nút có con trái | Trở thành thứ tự khác, thường preorder | Visit sau khi gỡ thread |
| Preorder visit cả lúc tạo và gỡ thread | Nút cha xuất hiện hai lần | Chỉ visit **lần đầu** |
| Postorder không có dummy | Có thể bỏ qua gốc thật ở lượt kết thúc | Dùng nút giả với `dummy.left = root` |
| Postorder đảo đường phải nhưng không đảo lại | Thay đổi vĩnh viễn liên kết của cây | Luôn hoàn nguyên đường vừa đảo |
| Dừng sớm khi đã tìm thấy mục tiêu | Thread ở tổ tiên có thể chưa được gỡ | Duyệt tới hết hoặc có cleanup được thiết kế rõ |
| Callback phát sinh exception | Phá vỡ đường xử lý tới điểm gỡ thread | Dùng giải pháp không sửa cây hoặc quản lý cleanup |
| Cho một luồng khác duyệt trong lúc Morris chạy | Luồng khác có thể nhìn thấy chu trình | Truy cập độc quyền trong **toàn lượt** |
| Biến Morris thành generator không quản lý vòng đời | Có thể giữ thread qua các lần yield | Không yield khi còn thread nếu cây có thể bị bên khác quan sát |
| Gọi hàm đệ quy khác từ callback | Có thể duyệt theo thread tạm sai cấu trúc | Không duyệt lại cây trong lúc Morris đang chạy |
| Ghi O(1) cho hàm trả list n giá trị | Bỏ qua O(n) bộ nhớ kết quả | Tách **bộ nhớ điều khiển** và **đầu ra** |
| Nhầm “O(1) bộ nhớ” với “không thay đổi cây” | Đánh giá sai ràng buộc đọc an toàn | Nêu rõ Morris sửa cây tạm |
| Dùng Morris trên cây DAG/có chu trình | Thread không còn hợp đồng khôi phục đúng | Xác minh dữ liệu thật sự là cây |
| Dùng so sánh giá trị để tìm thread | Nhầm khi nhiều nút cùng nhãn | Dùng so sánh **đồng nhất đối tượng** `is` |

## 18. Chọn Morris hay stack tường minh trong thực tế?

Một số tình huống gợi ý cách chọn:

| Hoàn cảnh | Lựa chọn thường phù hợp hơn | Vì sao |
|---|---|---|
| Cây chỉ đọc hoặc cấu trúc bất biến | **Stack tường minh/đệ quy** | Không sửa `left/right` |
| Cây dùng chung nhiều luồng | **Stack tường minh**, hoặc quản lý khóa/đồng bộ rõ ràng | Không xuất hiện thread mà bên đọc khác có thể thấy |
| Cần dừng ngay khi tìm thấy nút | **Stack tường minh** | `break/return` dễ kiểm soát, không bỏ thread |
| Có callback có thể ném ngoại lệ | **Stack tường minh** | Không cần khôi phục liên kết đã bị thay đổi |
| Cây có thể rất sâu, muốn tránh RecursionError | **Stack tường minh** hoặc Morris phù hợp điều kiện | Cả hai không dùng call stack DFS sâu |
| Bộ nhớ điều khiển rất hạn chế, có quyền sửa cây độc quyền và duyệt hết | **Morris** | O(1) trạng thái điều khiển |
| Muốn duyệt BST tăng dần nhưng chỉ cần kết quả trong lúc xử lý | **Morris inorder** nếu có độc quyền | Không cần stack O(h), nhưng nhớ hoàn nguyên |
| Cần trả về cả dãy n nút | Không mặc nhiên Morris tiết kiệm toàn bộ RAM | Riêng đầu ra đã O(n) |
| Cần tổng hợp thống kê của hai cây con | Thường là **postorder + dữ liệu con** | Phải lưu hoặc gắn kết quả trung gian theo bài toán |

Một cách ra quyết định thực tế: **đầu tiên** kiểm tra có được phép tạm sửa cây và bảo đảm không ai truy cập khi đang sửa hay không; **sau đó** mới cân nhắc lợi ích O(1) bộ nhớ điều khiển. Nếu điều kiện an toàn không đạt, lợi ích bộ nhớ không đủ để biện minh cho Morris cổ điển.

## 19. Câu hỏi tự luyện có lời giải

**Bài 1 — Tiền nhiệm inorder.** Với cây có gốc `8` và cây trái gốc `4`, trong đó `4.right = 6` và `6.right = 7`, tiền nhiệm inorder của `8` là nút nào?

*Lời giải:* Nút **7**, vì nó là nút nằm ngoài cùng bên phải của cây con trái `8`.

**Bài 2 — Tạo thread.** Morris đang ở `current=8`, tìm được `pred=7` với `pred.right is None`. Thuật toán làm gì tiếp theo?

*Lời giải:* Tạm đặt **`7.right = 8`** và đi sang **`8.left`**. Chưa visit `8` nếu đang duyệt **inorder**; visit `8` trước khi đi trái nếu đang duyệt **preorder**.

**Bài 3 — Gỡ thread.** Morris gặp lại `current=8` và thấy `pred.right is current`. Hành động bắt buộc là gì?

*Lời giải:* **`pred.right = None`** để khôi phục cây trước khi đi sang cây phải. Với inorder, sau đó visit `8`; với preorder, không visit lại.

**Bài 4 — Đánh giá thứ tự.** Trên cây cân bằng có gốc `4`, cây trái `2` với hai lá `1,3` và cây phải `6` với lá `5,7`, hãy viết inorder, preorder và postorder.

*Lời giải:* Inorder **`1,2,3,4,5,6,7`**; preorder **`4,2,1,3,6,5,7`**; postorder **`1,3,2,5,7,6,4`**.

**Bài 5 — Thời điểm visit.** Nếu chuyển `visit(current)` của Morris inorder từ nhánh gỡ thread sang nhánh tạo thread, thuật toán đang gần với kiểu duyệt nào?

*Lời giải:* **Preorder** (Gốc – Trái – Phải), vì cha được xử lý trước khi đi vào cây trái.

**Bài 6 — O(1) bộ nhớ.** Vì sao có thể nói Morris inorder dùng O(1) bộ nhớ phụ nhưng một hàm trả về danh sách tất cả n giá trị lại dùng O(n)?

*Lời giải:* **O(1)** chỉ tính các biến/con trỏ điều khiển của phép duyệt. Danh sách kết quả có **n** giá trị, cần **O(n)** bộ nhớ riêng.

**Bài 7 — Vòng tìm predecessor.** Vòng `while` tìm nút phải nhất đôi khi đi qua nhiều nút. Tại sao tổng thời gian Morris không mặc nhiên là O(n²)?

*Lời giải:* Các đường phải nhất chỉ được khảo sát một số lần hằng số liên quan tới việc **tạo/gỡ thread**; tổng số lần đi qua các cạnh trên cả lượt duyệt là O(n). Mỗi nút cũng chỉ được xử lý một lần.

**Bài 8 — Cây không có con trái.** Nếu cây là đường chỉ gồm các con phải, Morris inorder có cần tạo thread không?

*Lời giải:* **Không.** Tại mọi nút `left is None`, thuật toán xử lý nút và đi theo con phải; kết quả đi từ gốc đến lá.

**Bài 9 — Postorder.** Tại sao Morris postorder thường dùng một `dummy` và đảo tạm các đường `right`?

*Lời giải:* Nút giả cho phép có **mốc quay lại sau khi toàn bộ cây gốc hoàn tất**, còn việc đảo đường phải giúp xuất các nút biên theo thứ tự **từ dưới lên** mà không dùng stack.

**Bài 10 — Dừng sớm.** Có nên gọi `return` ngay khi tìm được một khóa trong Morris inorder đang có thread mở không?

*Lời giải:* **Không**, trừ khi có cơ chế dọn dẹp được thiết kế để khôi phục mọi thread còn mở. Thường nên dùng cách duyệt bằng stack nếu yêu cầu dừng sớm.

**Bài 11 — Đồng thời.** Vì sao không được để một luồng DFS đệ quy đọc cùng cây trong khi Morris đang chạy mà không có đồng bộ?

*Lời giải:* DFS có thể theo một liên kết `right` tạm quay về tổ tiên, tạo chu trình hoặc gặp cấu trúc không đúng với cây gốc.

**Bài 12 — Ngoại lệ.** Thêm `finally` trong hàm phụ đảo biên của postorder có bảo đảm mọi thread ở các tổ tiên đều được xóa khi gặp lỗi không?

*Lời giải:* **Không.** Nó chỉ khôi phục đường `right` vừa đảo. Thread mở ở những nơi khác cần cơ chế dọn dẹp riêng hoặc phải tránh dùng Morris trong hoàn cảnh không bảo đảm chạy hết.

**Bài 13 — Đánh đổi an toàn.** Vì sao một biến thể Morris lưu danh sách `(pred, current)` để khôi phục trong `finally` có thể không còn O(1) bộ nhớ điều khiển?

*Lời giải:* Có thể có nhiều thread lồng nhau trên một đường sâu. Danh sách thread đang mở có cận trên **O(h)**, trong trường hợp cây lệch có thể là O(n).

**Bài 14 — Chọn thuật toán.** Một cây BST đang được nhiều bộ đọc truy vấn đồng thời và không có khóa độc quyền. Nên dùng Morris inorder hay một inorder với stack riêng?

*Lời giải:* **Inorder với stack riêng** là lựa chọn phù hợp hơn vì không đổi liên kết của cây. Morris cổ điển đòi hỏi quyền sửa tạm và kiểm soát truy cập.

**Bài 15 — Nút trùng giá trị.** Hai nút đều mang giá trị `5`. Tại sao phải dùng `pred.right is current` thay cho `pred.right.value == current.value`?

*Lời giải:* Thread phải được nhận ra bằng **cùng đối tượng nút**, không phải cùng nhãn. Hai nút khác nhau có thể có cùng giá trị, nên so giá trị có thể nhầm liên kết.

**Bài 16 — Khôi phục sau traversal.** Ngoài việc so sánh dãy kết quả, nên kiểm tra gì khi viết test cho Morris?

*Lời giải:* Kiểm tra **các liên kết trái/phải** hoặc chữ ký cấu trúc trước và sau, đồng thời bảo đảm không còn thread. Dãy kết quả đúng chưa đủ để chứng minh cây đã được hoàn nguyên.

## 20. Tổng kết

**Duyệt Morris** dùng những liên kết `right` đang rỗng để tạo **đường quay về tổ tiên tạm thời**, nhờ đó duyệt inorder và preorder trong **O(n) thời gian, O(1) bộ nhớ phụ điều khiển** mà không cần đệ quy hoặc stack. Điểm khác giữa hai kiểu là **khi nào xử lý nút**: inorder visit sau khi duyệt cây trái và gỡ thread, preorder visit ngay trước khi đi trái. Biến thể postorder cần thêm **nút giả** và **đảo/khôi phục tạm những đường biên phải**.

**Điều kiện an toàn là bắt buộc:** đầu vào phải là cây hợp lệ; con trỏ được phép sửa; toàn bộ lượt duyệt phải được bảo vệ khỏi truy cập/mutation đồng thời; mỗi thread và đường bị đảo phải được khôi phục. Dừng sớm, callback phát sinh ngoại lệ hay hủy một generator trước khi kết thúc có thể để lại cấu trúc sai. Trong những hoàn cảnh không bảo đảm hoàn nguyên, **duyệt bằng stack tường minh O(h) thường là lựa chọn an toàn và dễ duy trì hơn**.
