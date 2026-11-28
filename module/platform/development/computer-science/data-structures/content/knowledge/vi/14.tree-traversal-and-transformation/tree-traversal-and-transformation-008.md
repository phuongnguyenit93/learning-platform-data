# Dựng lại cây nhị phân từ các thứ tự duyệt và điều kiện duy nhất

Ta có thể duyệt một cây nhị phân theo **trước (preorder)**, **giữa (inorder)** hoặc **sau (postorder)** để thu được những dãy giá trị. Nhưng nếu làm ngược lại — chỉ biết một hay vài dãy duyệt — liệu có thể **dựng lại chính xác cấu trúc cây ban đầu**?

Câu trả lời phụ thuộc vào **những dãy đã biết** và **các giả định về cây**. Đặc biệt:

- **Preorder + inorder**, với **nhãn của các nút phân biệt**, xác định **duy nhất** một cây nhị phân nếu hai dãy thật sự tương thích.
- **Postorder + inorder**, cũng với nhãn phân biệt, xác định **duy nhất** cây nếu dữ liệu tương thích.
- **Preorder + postorder** thông thường **không đủ** để dựng duy nhất một cây nhị phân bất kỳ, ngay cả khi mọi nhãn đều khác nhau.
- Nếu cây là **cây nhị phân đầy đủ theo nghĩa mỗi nút trong có đúng hai con** (*full binary tree*) và các nhãn phân biệt, **preorder + postorder** có thể xác định duy nhất cây.
- Một **preorder có ký hiệu tường minh cho mọi nhánh rỗng** cũng mô tả đủ hình dạng và giá trị cây, kể cả khi giá trị ở các nút trùng nhau.

Bài nằm trong chương **Duyệt và biến đổi cây** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Lộ trình mô-đun xây dựng nền tảng qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, nhấn mạnh **bất biến**, **thao tác**, **độ phức tạp thời gian/bộ nhớ** và cách lựa chọn cấu trúc cho từng bài toán. Ở đây, ta sẽ kết hợp suy luận về thứ tự duyệt với thuật toán chia cây con, mã Python, kiểm tra dữ liệu không hợp lệ và chứng minh điều kiện **duy nhất**.

## 1. Ôn lại ba thứ tự duyệt

Với cây nhị phân có gốc `N`, cây con trái `L` và cây con phải `R`:

| Thứ tự duyệt | Quy tắc | Phần tử cho biết ngay |
|---|---|---|
| **Preorder** | **Gốc – Trái – Phải** | Giá trị **đầu tiên** là gốc cây |
| **Inorder** | **Trái – Gốc – Phải** | Vị trí gốc **chia dãy** thành phần trái và phải |
| **Postorder** | **Trái – Phải – Gốc** | Giá trị **cuối cùng** là gốc cây |

Xét cây:

```text
                  M
                /   \
               B     T
              / \     \
             A   D     Z
```

Ba thứ tự duyệt là:

```text
Preorder : M, B, A, D, T, Z
Inorder  : A, B, D, M, T, Z
Postorder: A, D, B, Z, T, M
```

Tất cả đều chứa sáu nút, nhưng khác nhau về cách mã hóa quan hệ cha–con:

- Preorder cho biết **gốc trước**.
- Postorder cho biết **gốc sau**.
- Inorder cho biết chính xác **ranh giới hai cây con**, nếu ta tìm được vị trí của gốc một cách **không nhập nhằng**.

Nhận ra sự phối hợp này là chìa khóa của các thuật toán dựng cây.

### Cây nhị phân khác cây tìm kiếm nhị phân

Trong bài này, trừ khi có nói rõ, cây chỉ là **cây nhị phân**, không nhất thiết là **cây tìm kiếm nhị phân (BST)**. Các giá trị như `M`, `B`, `T` chỉ là nhãn; thuật toán **không dựa trên quan hệ lớn hơn/nhỏ hơn** để chọn con trái hoặc phải.

Nếu đề bài bổ sung bất biến BST cùng khóa phân biệt, đó là **thông tin thêm về cấu trúc** và có thể làm thay đổi khả năng dựng lại cây. Không nên áp dụng quy tắc của BST cho một cây nhị phân bất kỳ.

## 2. “Dựng được một cây” khác “dựng được duy nhất”

Một cặp dãy đầu vào có thể rơi vào ba trường hợp:

1. **Không tồn tại** cây nhị phân nào có đúng các dãy duyệt đã cho.
2. **Tồn tại nhiều cây** phù hợp: có thể chọn một cây, nhưng không biết đó có phải cây gốc hay không.
3. **Tồn tại đúng một cây** phù hợp: cấu trúc được xác định duy nhất trong phạm vi các giả định.

Ví dụ chỉ có:

```text
Preorder  = [A, B]
Postorder = [B, A]
```

Hai cây dưới đây đều phù hợp:

```text
Cây 1:                   Cây 2:

    A                        A
   /                          \
  B                            B

Preorder  : A, B           Preorder  : A, B
Postorder : B, A           Postorder : B, A
```

Dữ liệu cho biết `A` là gốc và `B` là con, nhưng không cho biết `B` là **con trái hay con phải**.

Nếu biết thêm inorder:

```text
Cây 1: inorder = [B, A]
Cây 2: inorder = [A, B]
```

Ta phân biệt được hai cây. Chính vị trí gốc trong inorder cung cấp ranh giới mà preorder + postorder đang thiếu.

**Lưu ý thuật ngữ:** “Duy nhất” ở đây xét **cấu trúc nhị phân có phân biệt nhánh trái/phải và nhãn nút**, không phải chỉ xét hình dạng khi cho phép hoán đổi hai phía. Hai cây có một con ở trái và một con ở phải là **hai cây khác nhau**.

## 3. Preorder + inorder với nhãn phân biệt

Giả sử:

```text
preorder = [M, B, A, D, T, Z]
inorder  = [A, B, D, M, T, Z]
```

### Bước 1 — Chọn gốc từ preorder

Phần tử đầu preorder là `M`, do preorder luôn ghi gốc trước mọi nút khác.

### Bước 2 — Tách inorder tại gốc

Tìm `M` trong inorder:

```text
Inorder: [A, B, D | M | T, Z]
          cây trái  gốc  cây phải
```

Ta suy ra:

- Cây trái có **3 nút**: `A, B, D`.
- Cây phải có **2 nút**: `T, Z`.

Khi mọi nhãn phân biệt, vị trí của `M` là **duy nhất**, nên phép chia này không nhập nhằng.

### Bước 3 — Phân vùng preorder theo kích thước cây trái

Sau gốc `M`, preorder ghi **toàn bộ cây trái**, rồi mới đến cây phải:

```text
Preorder: [M | B, A, D | T, Z]
           gốc  cây trái cây phải
```

Đoạn preorder cây trái có 3 phần tử vì inorder đã cho biết kích thước cây trái bằng 3. Đoạn còn lại thuộc cây phải.

### Bước 4 — Tiếp tục đệ quy

Cây trái:

```text
Preorder trái = [B, A, D]
Inorder trái  = [A, B, D]

Gốc là B, tách inorder:
[A | B | D]

=> B có con trái A và con phải D.
```

Cây phải:

```text
Preorder phải = [T, Z]
Inorder phải  = [T, Z]

Gốc là T; inorder không có giá trị ở bên trái T,
còn Z ở bên phải T.

=> T không có con trái và có con phải Z.
```

Kết quả cuối:

```text
                  M
                /   \
               B     T
              / \     \
             A   D     Z
```

Không cần so sánh thứ tự chữ cái giữa các nhãn. Ta chỉ dùng **vị trí trong các dãy duyệt**.

## 4. Giả mã dựng cây từ preorder + inorder

Ta có thể viết hàm dựng cây từ hai lát cắt:

```text
BUILD_PRE_IN(pre_sub, in_sub):
    if hai dãy rỗng:
        return NULL

    root_value = phần tử đầu pre_sub
    mid = vị trí root_value trong in_sub

    left_size = mid
    left_in   = in_sub trước mid
    right_in  = in_sub sau mid

    left_pre  = left_size phần tử tiếp theo trong pre_sub
    right_pre = phần còn lại trong pre_sub

    root = Node(root_value)
    root.left  = BUILD_PRE_IN(left_pre, left_in)
    root.right = BUILD_PRE_IN(right_pre, right_in)
    return root
```

Cách viết bằng các lát cắt **dễ hiểu** nhưng có thể tốn công tạo danh sách con và tìm kiếm lặp. Để có hiệu năng tốt, ta dùng:

- Một **bảng băm** tra giá trị → vị trí trong inorder.
- Hai chỉ số `lo, hi` chỉ ra **khoảng nửa mở `[lo, hi)`** của cây con trong inorder.
- Một con trỏ `next_pre` chỉ vào phần tử preorder chưa dùng tiếp theo.

### Bất biến của con trỏ preorder

Khi bắt đầu `build(lo, hi)`, phần tử tại `preorder[next_pre]` là **gốc của cây con** ứng với đoạn `inorder[lo:hi]`. Sau khi dựng xong cây con ấy, con trỏ đã tiêu thụ **đúng `hi-lo` nhãn**.

Việc dựng cây con **trái trước, phải sau** là bắt buộc khi đọc preorder từ trái sang phải.

## 5. Python: dựng cây từ preorder + inorder trong O(n)

Mã dưới đây sử dụng nhãn **phân biệt và có thể băm (hashable)** như số nguyên, chuỗi hoặc tuple bất biến. Để hỗ trợ nhãn không băm được, cần ánh xạ sang một ID phân biệt và có thể băm.

```python
class Node:
    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right


def preorder_values(root):
    if root is None:
        return []
    return (
        [root.value]
        + preorder_values(root.left)
        + preorder_values(root.right)
    )


def inorder_values(root):
    if root is None:
        return []
    return (
        inorder_values(root.left)
        + [root.value]
        + inorder_values(root.right)
    )


def postorder_values(root):
    if root is None:
        return []
    return (
        postorder_values(root.left)
        + postorder_values(root.right)
        + [root.value]
    )


def build_from_pre_in(preorder, inorder):
    n = len(preorder)
    if n != len(inorder):
        raise ValueError("Hai dãy phải có cùng độ dài")

    # Điều kiện của thuật toán: mọi nhãn là duy nhất.
    if len(set(preorder)) != n or len(set(inorder)) != n:
        raise ValueError("Cần nhãn phân biệt giữa các nút")
    if set(preorder) != set(inorder):
        raise ValueError("Hai dãy không có cùng tập nhãn")

    position = {value: i for i, value in enumerate(inorder)}
    next_pre = 0

    def build(lo, hi):
        nonlocal next_pre

        if lo == hi:
            return None
        if next_pre >= n:
            raise ValueError("Preorder kết thúc quá sớm")

        value = preorder[next_pre]
        next_pre += 1

        mid = position.get(value)
        if mid is None or not lo <= mid < hi:
            raise ValueError("Hai thứ tự duyệt không tương thích")

        node = Node(value)
        node.left = build(lo, mid)
        node.right = build(mid + 1, hi)
        return node

    root = build(0, n)
    if next_pre != n:
        raise ValueError("Preorder còn phần tử không sử dụng")
    return root


pre = ["M", "B", "A", "D", "T", "Z"]
ino = ["A", "B", "D", "M", "T", "Z"]

root = build_from_pre_in(pre, ino)

assert preorder_values(root) == pre
assert inorder_values(root) == ino
assert postorder_values(root) == ["A", "D", "B", "Z", "T", "M"]
```

Ba hàm `preorder_values`, `inorder_values` và `postorder_values` dùng phép nối danh sách để **minh họa/đối chiếu kết quả**. Trên cây lệch, các phép nối ấy có thể sao chép danh sách nhiều lần và tốn Θ(n²). **Độ phức tạp O(n) được khẳng định cho hàm dựng `build_from_pre_in`**, không áp dụng mặc định cho mọi hàm duyệt minh họa.

### Vì sao phải kiểm tra đoạn `[lo, hi)`?

Một cặp dãy có nhãn phân biệt và **cùng tập nhãn** vẫn có thể không biểu diễn cùng một cây. Ví dụ:

```text
Preorder = [A, B, C]
Inorder  = [C, A, B]
```

Gốc `A` chia inorder thành cây trái `[C]` và cây phải `[B]`. Nhưng phần tử preorder kế tiếp là `B`, **không nằm trong đoạn inorder của cây trái**. Không có cây nhị phân nào thỏa đồng thời hai thứ tự này; hàm phải báo lỗi thay vì lắp ghép một cây sai.

Kiểm tra `lo <= mid < hi` phát hiện sự mâu thuẫn ngay khi dựng cây con.

### Tình huống biên

```python
assert build_from_pre_in([], []) is None

single = build_from_pre_in([42], [42])
assert single.value == 42
assert single.left is None and single.right is None

left_only = build_from_pre_in(["A", "B"], ["B", "A"])
assert left_only.left.value == "B"
assert left_only.right is None

right_only = build_from_pre_in(["A", "B"], ["A", "B"])
assert right_only.left is None
assert right_only.right.value == "B"

for pre_bad, in_bad in [
    (["A", "B"], ["A"]),              # Sai độ dài
    (["A", "A"], ["A", "A"]),         # Nhãn trùng
    (["A", "B"], ["A", "C"]),         # Khác tập nhãn
    (["A", "B", "C"], ["C", "A", "B"]), # Không tương thích
]:
    try:
        build_from_pre_in(pre_bad, in_bad)
    except ValueError:
        pass
    else:
        raise AssertionError("Phải phát hiện dữ liệu không hợp lệ")
```

Hàm dựng không yêu cầu giá trị của nút là số hoặc có quan hệ thứ tự lớn–nhỏ. Chỉ cần nhãn phân biệt và có thể băm; ví dụ nhãn `None` vẫn có thể là **giá trị của một nút thật** vì đối tượng `Node(None)` khác với tham chiếu cây rỗng `None`. Một dãy rỗng dựng thành cây rỗng; một dãy `[None]` dựng thành một đối tượng `Node` có giá trị `None`.

## 6. Postorder + inorder: dựng theo chiều ngược lại

Giả sử biết:

```text
Postorder = [A, D, B, Z, T, M]
Inorder   = [A, B, D, M, T, Z]
```

Phần tử **cuối** postorder là gốc `M`. Tách inorder tại `M`:

```text
Inorder: [A, B, D | M | T, Z]
```

Postorder ghi **toàn bộ cây trái trước cây phải, rồi mới đến gốc**:

```text
Postorder: [A, D, B | Z, T | M]
             trái    phải  gốc
```

Ta có thể xác định kích thước và hai đoạn con. Nhưng nếu đọc postorder bằng một con trỏ chạy **từ cuối về đầu**, sau khi lấy `M` thì phần tử tiếp theo là `T` — **gốc cây phải**.

Vì thế, khác với thuật toán preorder, khi đọc postorder theo chiều ngược, phải **dựng cây phải trước rồi mới dựng cây trái**.

### Giả mã chỉ số

```text
BUILD_POST_IN(lo, hi):
    if lo == hi:
        return NULL

    value = postorder[next_post]
    next_post -= 1

    mid = vị trí value trong inorder

    node = Node(value)
    node.right = BUILD_POST_IN(mid + 1, hi)  # Phải trước
    node.left  = BUILD_POST_IN(lo, mid)
    return node
```

Nếu dựng trái trước trong khi đang đọc postorder từ **cuối về đầu**, ta sẽ lấy nhầm nhãn ở cây phải sang cây trái và kết quả có thể sai.

## 7. Python: dựng cây từ postorder + inorder

```python
def build_from_post_in(postorder, inorder):
    n = len(postorder)
    if n != len(inorder):
        raise ValueError("Hai dãy phải có cùng độ dài")
    if len(set(postorder)) != n or len(set(inorder)) != n:
        raise ValueError("Cần nhãn phân biệt giữa các nút")
    if set(postorder) != set(inorder):
        raise ValueError("Hai dãy không có cùng tập nhãn")

    position = {value: i for i, value in enumerate(inorder)}
    next_post = n - 1

    def build(lo, hi):
        nonlocal next_post

        if lo == hi:
            return None
        if next_post < 0:
            raise ValueError("Postorder kết thúc quá sớm")

        value = postorder[next_post]
        next_post -= 1

        mid = position.get(value)
        if mid is None or not lo <= mid < hi:
            raise ValueError("Hai thứ tự duyệt không tương thích")

        node = Node(value)
        node.right = build(mid + 1, hi)
        node.left = build(lo, mid)
        return node

    root = build(0, n)
    if next_post != -1:
        raise ValueError("Postorder còn phần tử không sử dụng")
    return root


post = ["A", "D", "B", "Z", "T", "M"]
ino = ["A", "B", "D", "M", "T", "Z"]

root2 = build_from_post_in(post, ino)

assert postorder_values(root2) == post
assert inorder_values(root2) == ino
assert preorder_values(root2) == ["M", "B", "A", "D", "T", "Z"]

assert build_from_post_in([], []) is None

single = build_from_post_in([7], [7])
assert single.value == 7
```

Cả hai thuật toán `pre+in` và `post+in` dựa trên cùng một nguyên tắc **gốc chia inorder thành hai cây con**. Sự khác nhau là **phía nào phải dựng trước** theo chiều ta đang tiêu thụ dãy chứa gốc.

## 8. Vì sao hai cặp có inorder xác định duy nhất?

Ta chứng minh bằng quy nạp trên số nút `n`, với các nhãn **phân biệt**.

### Cơ sở

- `n = 0`: cây duy nhất là cây rỗng.
- `n = 1`: cây duy nhất là một nút mang nhãn duy nhất trong dãy.

### Bước quy nạp cho preorder + inorder

Giả sử mọi cây con có ít hơn `n` nút được xác định duy nhất nếu biết preorder và inorder hợp lệ, nhãn phân biệt.

Với cây `n` nút:

1. Phần tử đầu **preorder** xác định **duy nhất gốc**.
2. Vì mọi nhãn phân biệt, vị trí của gốc trong **inorder** là duy nhất.
3. Vị trí ấy chia inorder thành **đúng tập nút cây trái** và **đúng tập nút cây phải**, đồng thời cho biết kích thước của mỗi bên.
4. Từ kích thước hai bên, ta chia phần preorder còn lại thành hai đoạn preorder tương ứng.
5. Theo giả thiết quy nạp, mỗi cây con được dựng **duy nhất**.

Kết hợp gốc với hai cây con đã xác định duy nhất, toàn bộ cây cũng duy nhất.

### Bước quy nạp cho postorder + inorder

Lập luận tương tự: phần tử cuối postorder cho gốc; vị trí gốc trong inorder xác định hai đoạn cây con; từ kích thước hai đoạn, phân tách postorder trước gốc. Dựng đệ quy mỗi cây con là duy nhất.

**Điều kiện “các dãy hợp lệ” không thể bỏ qua.** Chứng minh tính duy nhất chỉ nói rằng **nếu tồn tại cây thỏa dữ liệu**, thì không thể có hai cây khác nhau dưới các giả định trên. Nó **không khẳng định** mọi hai dãy có cùng số lượng nhãn đều dựng được cây.

## 9. Nhãn trùng nhau làm điều kiện duy nhất thay đổi

Bản đồ `value → vị trí inorder` chỉ có một vị trí chính xác cho mỗi nút **khi các nhãn phân biệt**. Nếu hai nút cùng mang nhãn `A`, một nhãn `A` trong preorder có thể tương ứng với **nhiều vị trí** trong inorder.

Ví dụ:

```text
Preorder = [A, A]
Inorder  = [A, A]
```

Hai cây khác nhau đều hợp lệ:

```text
Cây 1:                   Cây 2:

    A                        A
   /                          \
  A                            A

Preorder  = [A, A]         Preorder  = [A, A]
Inorder   = [A, A]         Inorder   = [A, A]
```

Vì vậy, **preorder + inorder không bảo đảm duy nhất nếu nhãn trùng nhau**. Tương tự, postorder + inorder có thể nhập nhằng khi giá trị bị lặp.

Điều này **không có nghĩa mọi trường hợp trùng nhãn đều bất khả thi**, hoặc nhất thiết có nhiều cây. Nó chỉ có nghĩa **điều kiện đủ tổng quát về tính duy nhất không còn**. Nếu có thông tin bổ sung (ID duy nhất cho từng nút, hình dạng biết trước hoặc ràng buộc khác), vẫn có thể dựng cây duy nhất.

### Cách giải quyết hợp lý

- Dùng **ID nút phân biệt** thay vì chỉ dùng giá trị hiển thị. Ví dụ hai nút có cùng nhãn `A` có thể mang ID `A#1` và `A#2` trong cả hai dãy.
- Truyền thêm dữ liệu về **cấu trúc**, chẳng hạn ký hiệu nhánh rỗng.
- Nếu bài toán chỉ yêu cầu dựng **một cây hợp lệ**, có thể xem xét các khả năng vị trí gốc trùng nhau bằng tìm kiếm/quay lui; nhưng muốn trả **duy nhất**, phải kiểm tra chỉ tồn tại một cấu trúc thỏa ràng buộc.

**Không nên tự ý lấy vị trí đầu tiên của nhãn trùng trong inorder rồi khẳng định đã khôi phục đúng cây gốc.** Đây có thể chỉ là một lựa chọn tùy tiện trong nhiều khả năng.

## 10. Preorder + postorder thường không xác định duy nhất

Có thể nghĩ rằng biết **gốc ở đầu preorder** và **gốc ở cuối postorder** là đủ. Nhưng cả hai thứ tự đều đặt nút cha **ngoài hai cây con**, không cho biết chắc chắn một cây con là **trái hay phải** khi nút cha chỉ có **một con**.

Một lần nữa, ví dụ:

```text
    A             A
   /               \
  B                 B

Preorder  cả hai: [A, B]
Postorder cả hai: [B, A]
```

Dữ liệu còn thiếu chính là **hướng của liên kết đơn**. Trên một đường gồm nhiều nút, mỗi nút chỉ có một con có thể là nhánh trái hoặc phải mà không làm đổi preorder/postorder của chuỗi ấy.

Ngay cả khi **mọi nhãn đều phân biệt**, chỉ có hai thứ tự preorder + postorder **không bảo đảm duy nhất trên lớp tất cả cây nhị phân**.

### Nhưng có thể dựng một cây tùy chọn không?

Có. Với một cặp dãy preorder/postorder tương thích, đôi khi thuật toán chọn quy ước **“nếu nút có một con thì đặt bên trái”** để tạo ra *một* cây. Tuy nhiên, đây chỉ là cây đại diện theo quy ước, **không có căn cứ khẳng định nó là cây ban đầu**.

Nếu yêu cầu đề là “khôi phục chính xác”, ta phải xác minh điều kiện duy nhất trước khi chấp nhận loại kết quả này.

## 11. Điều kiện bổ sung: cây nhị phân đầy đủ (full binary tree)

**Cây nhị phân đầy đủ** trong ngữ cảnh này nghĩa là **mỗi nút có đúng 0 hoặc đúng 2 con**. Nút có đúng một con **không được phép xuất hiện**.

Đừng nhầm với:

- **Cây nhị phân hoàn chỉnh (complete):** các mức được lấp theo quy luật từ trái sang phải.
- **Cây nhị phân hoàn hảo (perfect):** mọi nút trong có hai con và mọi lá nằm ở cùng độ sâu.

Cây **full** không bắt buộc mọi lá cùng một độ sâu; điều cần thiết ở đây là **không có nút một con**.

### Vì sao full giải quyết sự nhập nhằng?

Với một cây full có nhiều hơn một nút, gốc **bắt buộc có hai cây con không rỗng**. Do preorder là Gốc – Trái – Phải, phần tử **ngay sau gốc** là **gốc cây trái**.

Ví dụ:

```text
                 A
               /   \
              B     C
             / \   / \
            D   E F   G

Preorder : A, B, D, E, C, F, G
Postorder: D, E, B, F, G, C, A
```

Sau khi biết gốc là `A`:

1. Preorder chỉ ra **`B`** là gốc cây trái.
2. Tìm `B` trong postorder. Vì postorder kết thúc cây con bằng gốc của nó, đoạn `[D, E, B]` là **toàn bộ postorder cây trái**.
3. Ta suy ra cây trái có **3 nút**; cây phải cũng có **3 nút**.
4. Chia hai dãy và dựng đệ quy các cây con, vì mọi nút trong chúng cũng tuân thủ điều kiện full.

Với nhãn phân biệt và dữ liệu hợp lệ, quá trình trên **xác định duy nhất cây**.

### Giả mã phân đoạn

```text
BUILD_FULL(pre, post):
    if dãy rỗng: return NULL

    root_value = pre[0]
    if dãy có một phần tử:
        return Node(root_value)

    # Cây full có hơn một nút => cả hai con tồn tại.
    left_root = pre[1]

    # Trong post, left_root kết thúc đoạn cây con trái.
    split = vị trí left_root trong post
    left_size = split + 1

    chia pre và post theo left_size
    dựng cây trái và cây phải
    return root
```

**Nếu có một nút chỉ có đúng một con**, phép xác định cây trái từ `pre[1]` không còn chắc chắn: phần tử ấy có thể là gốc của con trái **hoặc** con phải. Vì vậy, điều kiện full là một **ràng buộc có ý nghĩa học thuật**, không phải chi tiết có thể bỏ qua.

## 12. Python: dựng từ preorder + postorder khi cây full

Đây là phiên bản dùng các khoảng nửa mở của hai dãy và bản đồ vị trí trong postorder. Mã cũng **từ chối cấu trúc không full** thay vì âm thầm gán nhánh con một phía.

```python
def build_full_from_pre_post(preorder, postorder):
    n = len(preorder)
    if n != len(postorder):
        raise ValueError("Hai dãy phải có cùng độ dài")
    if len(set(preorder)) != n or len(set(postorder)) != n:
        raise ValueError("Cần nhãn phân biệt")
    if set(preorder) != set(postorder):
        raise ValueError("Hai dãy không cùng tập nhãn")

    # Cây full không rỗng có số nút lẻ.
    if n % 2 == 0 and n != 0:
        raise ValueError("Cây full không rỗng phải có số nút lẻ")

    pos = {value: i for i, value in enumerate(postorder)}

    def build(pre_lo, pre_hi, post_lo, post_hi):
        count = pre_hi - pre_lo

        if count != post_hi - post_lo:
            raise ValueError("Hai đoạn có số nút không khớp")
        if count == 0:
            return None

        value = preorder[pre_lo]
        if value != postorder[post_hi - 1]:
            raise ValueError("Gốc trong preorder/postorder khác nhau")

        node = Node(value)
        if count == 1:
            return node

        # Với cây full, cả hai cây con đều không rỗng.
        left_root = preorder[pre_lo + 1]
        split = pos[left_root]

        if not post_lo <= split < post_hi - 1:
            raise ValueError("Không xác định được cây con trái")

        left_size = split - post_lo + 1
        right_size = count - 1 - left_size

        if left_size <= 0 or right_size <= 0:
            raise ValueError("Dữ liệu không biểu diễn cây full")

        node.left = build(
            pre_lo + 1,
            pre_lo + 1 + left_size,
            post_lo,
            post_lo + left_size,
        )
        node.right = build(
            pre_lo + 1 + left_size,
            pre_hi,
            post_lo + left_size,
            post_hi - 1,
        )
        return node

    return build(0, n, 0, n)


pre_full = ["A", "B", "D", "E", "C", "F", "G"]
post_full = ["D", "E", "B", "F", "G", "C", "A"]

full_root = build_full_from_pre_post(pre_full, post_full)

assert preorder_values(full_root) == pre_full
assert postorder_values(full_root) == post_full
assert inorder_values(full_root) == ["D", "B", "E", "A", "F", "C", "G"]

assert build_full_from_pre_post([], []) is None
assert build_full_from_pre_post(["X"], ["X"]).value == "X"
```

Mỗi lần cắt cây con chỉ điều chỉnh **chỉ số**, không sao chép các lát cắt danh sách. Với nhãn phân biệt, ánh xạ `postorder` cho phép tìm ranh giới cây trái trong thời gian trung bình O(1). Các đoạn con được xác minh bằng giá trị gốc và kích thước; nếu dữ liệu không tương thích, thuật toán sẽ báo lỗi.

**Ví dụ không đủ điều kiện full:** `preorder = [A, B]`, `postorder = [B, A]` có hai nút, nên không thể là cây full có hai nút. Ta không được dùng thuật toán trên để tuyên bố đã dựng duy nhất một cây từ cặp dãy ấy.

## 13. Một dãy duyệt có ký hiệu nhánh rỗng cũng đủ

Khi chỉ có **preorder không đánh dấu nhánh rỗng**, ta không biết một nút có con trái, con phải hay cả hai. Tuy nhiên, nếu biểu diễn **mỗi tham chiếu con rỗng** bằng một token đặc biệt `#`, hình dạng cây được mã hóa đầy đủ.

Ví dụ hai cây:

```text
Cây 1: A có con trái B       Cây 2: A có con phải B

     A                             A
    /                               \
   B                                 B

Preorder thường:
[A, B]                         [A, B]

Preorder kèm dấu nhánh rỗng:
[A, B, #, #, #]                [A, #, B, #, #]
```

Hai dãy có ký hiệu `#` **khác nhau**, nên cây được xác định.

Với kiểu mã hóa này:

- Một **nút thực** ghi một token nhãn rồi mã hóa cây trái và cây phải.
- Một **cây con rỗng** ghi đúng một token `#`.
- Vì quy tắc mã hóa được xác định đệ quy, bộ giải mã đọc token nào cũng biết lúc nào phải dựng nút và lúc nào phải trả về `None`.

Đặc biệt, **các nhãn nút thật có thể trùng nhau**; vị trí của các dấu rỗng đã mô tả hình dạng. Điều kiện cần là token `#` phải **được dành riêng**, không nhập nhằng với nhãn dữ liệu thật (hoặc được escape).

### Python: mã hóa và dựng lại với token rỗng

```python
NULL_TOKEN = "#"


def encode_preorder_with_nulls(root):
    tokens = []

    def walk(node):
        if node is None:
            tokens.append(NULL_TOKEN)
            return

        if node.value == NULL_TOKEN:
            raise ValueError("Nhãn nút không được trùng token rỗng")

        tokens.append(node.value)
        walk(node.left)
        walk(node.right)

    walk(root)
    return tokens


def decode_preorder_with_nulls(tokens):
    it = iter(tokens)
    end = object()

    def build():
        token = next(it, end)
        if token is end:
            raise ValueError("Thiếu token khi dựng cây")

        if token == NULL_TOKEN:
            return None

        node = Node(token)
        node.left = build()
        node.right = build()
        return node

    root = build()
    if next(it, end) is not end:
        raise ValueError("Có token thừa sau khi dựng cây")
    return root


example = Node("A", left=Node("B"))
tokens = encode_preorder_with_nulls(example)

assert tokens == ["A", "B", "#", "#", "#"]
rebuilt = decode_preorder_with_nulls(tokens)
assert encode_preorder_with_nulls(rebuilt) == tokens

duplicates = Node("X", Node("X"), Node("X"))
same_labels_tokens = encode_preorder_with_nulls(duplicates)
assert encode_preorder_with_nulls(
    decode_preorder_with_nulls(same_labels_tokens)
) == same_labels_tokens

assert decode_preorder_with_nulls(["#"]) is None
```

Với `n` nút thực của cây nhị phân, có đúng **`n+1` liên kết con rỗng**. Vì thế chuỗi mã hóa chứa **`2n+1` token**: n nhãn nút và n+1 token rỗng.

Mã hóa/giải mã trên tốn O(n) thời gian theo số nút với công việc hằng số trên một token, O(h) stack đệ quy và O(n) bộ nhớ cho chuỗi token/cây kết quả. Cần phân biệt bộ nhớ điều khiển với bộ nhớ lưu cây hoặc dãy mã hóa. Với cây quá sâu, bản đệ quy vẫn có thể gặp giới hạn gọi hàm của Python; có thể viết bộ giải mã lặp bằng stack trạng thái.

### Kiểm tra dữ liệu bị thiếu hoặc thừa

```python
for bad in [
    [],                 # Thiếu cả token gốc
    ["A", "#"],         # Thiếu token cây phải
    ["#", "A"],         # Có token thừa sau cây rỗng
]:
    try:
        decode_preorder_with_nulls(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("Phải báo lỗi dãy token không hợp lệ")
```

Dữ liệu có dấu rỗng chính là một **định dạng tuần tự hóa cây**, khác với dãy preorder của các nút thật dùng trong bài toán dựng cây thông thường.

## 14. Tổng hợp các tổ hợp thông tin và điều kiện duy nhất

Bảng dưới giả định ta muốn khôi phục **cây nhị phân có nhánh trái/phải phân biệt**, và các dãy đầu vào phải **hợp lệ, tương thích**.

| Thông tin được cung cấp | Có bảo đảm duy nhất không? | Điều kiện và lý do |
|---|---|---|
| Chỉ **preorder** | **Không** | Không cho biết ranh giới các nhánh |
| Chỉ **inorder** | **Không** | Không xác định được gốc hoặc hình dạng |
| Chỉ **postorder** | **Không** | Không cho biết chia hai cây con |
| **Preorder + inorder** | **Có**, nếu nhãn phân biệt | Gốc từ preorder, chia trái/phải bằng inorder |
| **Postorder + inorder** | **Có**, nếu nhãn phân biệt | Gốc từ postorder, chia trái/phải bằng inorder |
| **Preorder + postorder** | **Không nói chung** | Nút một con có thể đặt trái hoặc phải |
| Preorder + postorder, biết cây **full** | **Có**, nếu nhãn phân biệt | Mọi nút trong có hai con; xác định kích thước cây trái |
| Preorder với **token rỗng cho cả hai nhánh** | **Có**, kể cả nhãn trùng | Dấu rỗng mã hóa đầy đủ hình dạng |
| Chỉ preorder, biết cây là **BST khóa phân biệt** | **Có**, nếu dãy hợp lệ với BST | Bất biến BST xác định đoạn khóa nhỏ/lớn; dữ liệu ràng buộc thêm |

Không nên suy luận “càng nhiều dãy duyệt càng chắc chắn có cây”. Ví dụ nếu ba dãy mâu thuẫn, **không có cây nào** thỏa cả ba. Việc chứng minh duy nhất luôn cần đi kèm **kiểm tra tồn tại và tính hợp lệ**.

### Nhãn trùng và BST

Một BST với **khóa phân biệt** có inorder là dãy các khóa tăng dần. Do đó, biết preorder hợp lệ của BST cùng bất biến BST cho phép dựng lại cây mà không cần cung cấp inorder riêng. Nhưng kết luận này **phụ thuộc ràng buộc BST**, hoàn toàn không áp dụng cho preorder của một cây nhị phân bất kỳ. Với khóa trùng, chính sách đặt khóa trùng và cách nhận diện từng nút lại trở thành thông tin quan trọng.

## 15. Phân tích thời gian và bộ nhớ

Gọi `n` là số nút, `h` là số nút trên đường từ gốc đến lá sâu nhất. Giả sử nhãn có thể băm, thao tác hash/so sánh khóa thường O(1) trung bình.

| Cách dựng | Thời gian | Bộ nhớ phụ điều khiển/tra cứu, chưa tính cây mới |
|---|---|---|
| Preorder + inorder, dùng bản đồ vị trí | **O(n)** trung bình | **O(n)** cho bản đồ + **O(h)** stack |
| Postorder + inorder, dùng bản đồ vị trí | **O(n)** trung bình | **O(n)** cho bản đồ + **O(h)** stack |
| Preorder + postorder khi cây full, dùng bản đồ | **O(n)** trung bình | **O(n)** bản đồ + **O(h)** stack |
| Preorder có dấu rỗng | **O(n)** | **O(h)** stack; O(n) cho chuỗi token nếu tạo chuỗi |
| Dùng `index()` tìm gốc lặp lại trong từng đoạn | Có thể **O(n²)** | Tùy cách chia và có sao chép đoạn hay không |

Trong ba thuật toán dùng bản đồ, mỗi nhãn tham gia đúng một lần vào việc tạo nút; tìm vị trí gốc có chi phí trung bình O(1). Vì vậy tổng là O(n). Việc dùng hash có thể có chi phí khác trong trường hợp va chạm bất thường; giả định hash hiệu quả là chuẩn trong bài toán cấu trúc dữ liệu.

### Tại sao tìm tuyến tính có thể thành O(n²)?

Nếu mỗi lần dựng cây con lại dùng `inorder.index(root)` hoặc tự quét đoạn inorder để tìm gốc, thao tác tìm vị trí có thể mất thời gian tỷ lệ kích thước cây con. Trên cây lệch:

```text
Lần 1 tìm trong n phần tử
Lần 2 tìm trong n-1 phần tử
Lần 3 tìm trong n-2 phần tử
...
Tổng: n + (n-1) + ... + 1 = Θ(n²)
```

Tạo nhiều lát cắt `preorder[a:b]`/`inorder[a:b]` cũng có thể sao chép dữ liệu và làm tăng chi phí. **Bản đồ vị trí + khoảng chỉ số** là lựa chọn hiệu quả hơn.

### Phân biệt ba loại bộ nhớ

1. **Cây kết quả:** O(n) nút mới được tạo.
2. **Bản đồ vị trí:** O(n) mục đối với các thuật toán dùng inorder/postorder làm chỉ mục.
3. **Ngăn xếp đệ quy:** O(h), vì mỗi lần chỉ đi sâu trên một đường của cây.

Nếu cây cân bằng thì `h = O(log n)`; nếu cây lệch, `h = O(n)`. Kết luận “độ phức tạp bộ nhớ của hàm dựng là O(n)” bao gồm bản đồ (và thường cả cây kết quả). Khi đề chỉ hỏi **stack đệ quy**, cần nêu riêng **O(h)**.

## 16. Bất biến và kiểm tra tính hợp lệ

### Bất biến khi dùng khoảng nửa mở

Với `build(lo, hi)` của preorder + inorder:

- Các nút cần dựng nằm **chính xác** trong `inorder[lo:hi]`.
- `preorder[next_pre]` là gốc cây con này khi `lo < hi`.
- Tìm gốc phải cho `mid` nằm **trong** đoạn `[lo,hi)`.
- Cây con trái có `mid-lo` nút, cây con phải có `hi-mid-1` nút.
- Sau khi dựng xong, con trỏ preorder đã tiến **đúng `hi-lo` vị trí**.

Với postorder + inorder, bất biến tương ứng dùng con trỏ đọc **ngược**. Phải dựng **phải rồi trái** vì sau gốc ở cuối, phần tử vừa đọc lùi tới thuộc cây phải.

### Các kiểm tra đầu vào cần thiết

- Hai dãy có **cùng độ dài**.
- Hai dãy có **cùng tập nhãn với số lần xuất hiện phù hợp**; trong thuật toán đơn giản ở đây, mọi nhãn phải phân biệt.
- Gốc của mỗi cây con **phải thuộc đoạn inorder/postorder đang xét**.
- Sau khi dựng xong, **mọi phần tử được dùng đúng một lần**, không thừa hoặc thiếu.
- Nếu giả định cây **full**, mỗi nút trong phải có đúng hai cây con, trừ trường hợp nút lá.
- Nếu dùng dấu nhánh rỗng, chuỗi token phải có cấu trúc hợp lệ và không còn token thừa.

**Điểm cần nhớ:** xác minh chỉ bằng việc mọi nhãn xuất hiện trong cả hai dãy là **chưa đủ**. Hai thứ tự có thể dùng cùng nhãn nhưng không tương thích về cấu trúc cây.

### Không so sánh nút theo thứ tự từ vựng

Trong thuật toán dựng cây nhị phân tổng quát, một nhãn `"B"` không mặc nhiên thuộc cây trái của `"M"` vì `"B" < "M"`. Nhãn chỉ dùng để **nhận diện đúng nút**; quan hệ con trái/con phải đến từ **vị trí trong các dãy duyệt**. Chỉ với giả định BST ta mới được dùng quy tắc so sánh khóa để chia cây.

## 17. Lỗi thường gặp và cách phòng tránh

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Cho rằng hai dãy duyệt bất kỳ luôn xác định cây | Dựng sai hoặc nhận kết quả không duy nhất | Kiểm tra **loại dãy và ràng buộc** |
| Preorder + postorder, bỏ qua nút một con | Không biết con trái hay con phải | Yêu cầu full hoặc thông tin cấu trúc khác |
| Nhãn trùng nhưng dùng `value → index` như ánh xạ một-một | Mất vị trí gốc hợp lệ, kết luận sai | Dùng ID phân biệt hoặc giải quyết nhập nhằng |
| Dựng preorder + inorder nhưng dựng phải trước | Đọc sai thứ tự preorder | Tiêu thụ preorder **trái trước, phải sau** |
| Dựng postorder + inorder từ cuối nhưng dựng trái trước | Đọc sai đoạn postorder | Tiêu thụ postorder **phải trước, trái sau** |
| Không kiểm tra `mid` có thuộc đoạn hiện tại | Dựng cây sai từ hai dãy mâu thuẫn | Kiểm tra `lo <= mid < hi` |
| Tìm gốc bằng quét tuyến tính ở từng bước | Có thể mất Θ(n²) | Dùng bảng băm vị trí |
| Cắt danh sách con liên tục | Tốn bộ nhớ/copy dữ liệu | Dùng khoảng chỉ số |
| Không kiểm tra phần tử thừa sau khi dựng | Dữ liệu không hợp lệ bị bỏ qua | Kiểm tra con trỏ đã dùng toàn bộ dãy |
| Dùng preorder đơn lẻ, không mã hóa cây rỗng | Không biết hình dạng cây | Bổ sung null markers hoặc dãy khác |
| Dùng ký hiệu `#` vừa làm dữ liệu nút vừa làm dấu rỗng | Bộ giải mã nhập nhằng | Dành riêng token hoặc escape |
| Nhầm “full” với “complete” hoặc “perfect” | Áp sai chứng minh duy nhất | Xác nhận **mỗi nút trong có đúng hai con** |
| Quên kiểm tra trường hợp cây rỗng/một nút | Lỗi biên, chỉ số vượt dãy | Cơ sở `n=0` hoặc `n=1` |
| Cây quá sâu khi dựng bằng đệ quy Python | Có thể `RecursionError` | Chuyển sang thuật toán dùng stack khi cần |
| Đánh giá O(h) là tổng bộ nhớ bao gồm cây mới | Báo thiếu O(n) nút và bản đồ | Tách **cây kết quả, bản đồ, call stack** |

## 18. Tự luyện với lời giải

**Bài 1 — Xác định gốc.** Cho preorder `[P, L, K, N, R]` và inorder `[K, L, N, P, R]`. Gốc là nút nào? Cây trái có mấy nút?

*Lời giải:* Gốc `P` là phần tử đầu preorder. Vị trí `P` trong inorder tách dãy trái `[K,L,N]` gồm **3 nút**, bên phải `[R]` gồm 1 nút.

**Bài 2 — Dựng cây.** Với hai dãy ở bài 1, hãy viết cấu trúc cây.

*Lời giải:* Gốc `P`; cây trái có gốc `L`, con trái `K`, con phải `N`; cây phải là lá `R`:

```text
       P
      / \
     L   R
    / \
   K   N
```

**Bài 3 — Postorder.** Dãy postorder của cây ở bài 2 là gì?

*Lời giải:* Cây trái `K,N,L`; cây phải `R`; cuối cùng gốc `P`. Kết quả **`[K, N, L, R, P]`**.

**Bài 4 — Cặp inorder + postorder.** Cho inorder `[2, 4, 6, 8, 10]` và postorder `[2, 6, 4, 10, 8]`. Hãy xác định gốc và cây con bên trái.

*Lời giải:* Gốc là `8` ở cuối postorder. Inorder bên trái `[2,4,6]` cho cây con có gốc `4`, con trái `2`, con phải `6`. Bên phải gốc `8` là lá `10`.

**Bài 5 — Sai dữ liệu.** Preorder `[A,B,C]` và inorder `[C,A,B]` có cùng tập nhãn phân biệt. Có dựng được cây không?

*Lời giải:* **Không.** Gốc `A` yêu cầu cây trái chỉ chứa `C`, nhưng phần tử preorder tiếp theo là `B`; cặp dãy không tương thích về cấu trúc.

**Bài 6 — Không duy nhất.** Preorder `[A,B]` và postorder `[B,A]` có bao nhiêu cách gắn `B` làm con của `A` nếu không có ràng buộc khác?

*Lời giải:* **Hai**: `B` là con trái hoặc con phải. Cả hai đều có cùng hai dãy đã cho.

**Bài 7 — Nhãn trùng.** Preorder `[A,A]` và inorder `[A,A]` có bảo đảm dựng duy nhất một cây không?

*Lời giải:* **Không.** Nút `A` thứ hai có thể ở bên trái hoặc bên phải của gốc `A`; dãy giá trị không phân biệt hai cấu trúc.

**Bài 8 — Full binary tree.** Một cây full có 6 nút có tồn tại không? Vì sao?

*Lời giải:* **Không.** Với cây full không rỗng, số nút luôn **lẻ** vì mỗi nút trong có hai con; số nút toàn cây bằng `2i+1` nếu có `i` nút trong.

**Bài 9 — Preorder + postorder của cây full.** Cho preorder `[A,B,D,E,C,F,G]` và postorder `[D,E,B,F,G,C,A]`. Có thể xác định cây trái của gốc có bao nhiêu nút?

*Lời giải:* Gốc `A`, phần tử tiếp theo của preorder là `B`, tức gốc cây trái. Trong postorder, `B` kết thúc đoạn `[D,E,B]`, nên cây trái có **3 nút**.

**Bài 10 — Dấu rỗng.** Hai cây `A`–`B` có `B` là con trái hoặc con phải. Vì sao preorder với ký hiệu null phân biệt được hai cây?

*Lời giải:* Cây trái cho `[A,B,#,#,#]`, cây phải cho `[A,#,B,#,#]`. Vị trí ký hiệu `#` mô tả chính xác nhánh không tồn tại.

**Bài 11 — Dữ liệu trùng nhưng có dấu rỗng.** Preorder có ký hiệu rỗng có thể dựng duy nhất cây gồm ba nút đều nhãn `X` không?

*Lời giải:* **Có**, nếu mỗi nhánh rỗng đều được đánh dấu bằng token riêng không trùng nhãn nút. Dãy token mô tả đầy đủ hình dạng bất kể các nhãn `X` giống nhau.

**Bài 12 — Chi phí.** Vì sao dựng từ preorder + inorder bằng bảng vị trí và khoảng chỉ số có thể đạt O(n), còn tìm tuyến tính vị trí gốc ở từng cây con có thể Θ(n²)?

*Lời giải:* Bảng băm cho phép tìm vị trí gốc trung bình O(1) cho mỗi nút; mỗi nút được dựng một lần. Quét lại đoạn inorder ở từng bước có thể xét tổng `n+(n-1)+...+1` phần tử trên cây lệch.

**Bài 13 — Dựng cây postorder.** Khi đọc postorder từ cuối về đầu và đã lấy gốc, tại sao phải dựng **cây phải** trước cây trái?

*Lời giải:* Postorder theo chiều thuận là Trái–Phải–Gốc. Khi đọc ngược, sau Gốc đến **Phải** rồi mới Trái; con trỏ postorder phải được tiêu thụ theo đúng thứ tự ấy.

**Bài 14 — Điều kiện duy nhất.** Nếu biết preorder và inorder với nhãn phân biệt, nhưng hai dãy không tương thích, phát biểu “dựng cây duy nhất” có đúng không?

*Lời giải:* **Không.** Khi không tồn tại cây, không thể nói có một cây duy nhất. Điều kiện đúng là **hai dãy hợp lệ và tương thích**, khi đó cây được dựng **duy nhất**.

**Bài 15 — Bộ nhớ.** Với cây cân bằng có n nút, dựng bằng preorder + inorder dùng bảng vị trí và đệ quy có chi phí bộ nhớ nào?

*Lời giải:* Bảng vị trí O(n), các nút mới O(n), stack đệ quy O(log n) vì chiều cao O(log n). Nếu tính tổng bộ nhớ gồm cây và bảng: **O(n)**; nếu chỉ tính call stack: **O(log n)**.

## 19. Tổng kết

Để **dựng lại cây nhị phân**, biết một thứ tự duyệt thường chưa đủ. **Preorder + inorder** hoặc **postorder + inorder**, khi nhãn phân biệt và dữ liệu tương thích, cho phép xác định **duy nhất** cả gốc lẫn ranh giới cây trái/phải. Thuật toán dùng **bản đồ vị trí và các khoảng chỉ số** đạt **O(n) thời gian trung bình**, cần O(n) bộ nhớ tra cứu và O(h) stack đệ quy.

**Preorder + postorder** thường không xác định được phía trái/phải của nút một con. Tính duy nhất được khôi phục khi có ràng buộc đủ mạnh, chẳng hạn **cây full với nhãn phân biệt**, hoặc khi dữ liệu duyệt có thêm **ký hiệu nhánh rỗng**. Muốn phát biểu đúng về tính duy nhất, luôn nói rõ **các dãy nào được cung cấp, nhãn có phân biệt không, cấu trúc cây bị ràng buộc ra sao và dữ liệu đầu vào có tương thích không**.
