# Treap kết hợp thứ tự khóa của BST với thứ tự ưu tiên của heap

Một cây tìm kiếm nhị phân (BST) có thể tìm nhanh khi cân đối nhưng suy biến thành danh sách liên kết nếu chèn khóa theo thứ tự bất lợi. Một heap tổ chức dữ liệu để biết phần tử có độ ưu tiên cao nhất nhưng không cung cấp tìm theo khóa theo thứ tự BST. **Treap** (*tree + heap*) kết hợp **hai bất biến trên cùng một cây nhị phân**: các khóa giữ thứ tự BST, còn các mức ưu tiên giữ thứ tự heap. Khi mức ưu tiên được rút ngẫu nhiên độc lập, treap thường có hình dạng cân đối **theo kỳ vọng** mà không cần luật cân bằng màu hoặc chênh lệch chiều cao như AVL.

Bài **“Treap kết hợp thứ tự khóa của BST với thứ tự ưu tiên của heap”** thuộc chương **Cấu trúc ngẫu nhiên**, module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Từ nền tảng mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, ta tập trung vào **bất biến, thao tác và độ phức tạp thời gian/bộ nhớ** để biết khi nào treap phù hợp.

Sau bài, bạn sẽ có thể:

- Phân biệt **khóa `key`** với **độ ưu tiên `priority`**, giải thích vì sao treap đồng thời là BST và heap.
- Dựng treap từ danh sách cặp (khóa, ưu tiên), xác định gốc bằng quy tắc Cartesian tree.
- Thực hiện quay trái/phải, chèn và xóa không phá hai bất biến.
- Hiểu hai phép nền tảng **`split`** và **`merge`**, cùng điều kiện tiền đề rất dễ bị bỏ qua.
- Cài đặt treap set bằng Python: tìm, chèn, xóa, duyệt thứ tự, `rank`, `select`, `lower_bound` và kiểm tra mọi bất biến.
- Phân tích vì sao độ sâu tra cứu **O(log n) kỳ vọng** dưới mô hình random thích hợp nhưng **worst-case Θ(n)**.
- Nhận diện tác động của khóa trùng, ưu tiên trùng, nguồn PRNG, vòng đời node, ngăn xếp đệ quy và thao tác đồng thời.
- So sánh treap với BST thường, AVL, red-black tree, heap, skip list và hash table; giải các bài tập có lời giải.

## 1. Hai quan hệ thứ tự cùng tồn tại trên một cây

Một node treap chuẩn chứa:

```text
Node {
    key       : khóa cần lưu
    priority  : độ ưu tiên dùng điều khiển hình dạng cây
    left      : con trái hoặc NULL
    right     : con phải hoặc NULL
    size      : số node trong cây con (nếu cần rank/select)
}
```

Ta sử dụng quy ước **min-heap theo priority**: số priority **nhỏ hơn** được đặt ở gần gốc. Một số tài liệu dùng **max-heap**, số lớn gần gốc; cả hai đúng nếu chọn một quy ước nhất quán. Tất cả ví dụ của bài dùng **min-heap**.

### 1.1. Bất biến BST theo khóa

Với node `u` mang khóa `k`:

\[
\forall x\in subtree(u.left): x.key < k,\qquad
\forall y\in subtree(u.right): y.key > k.
\]

Bài dùng **set**: khóa phân biệt. Vì vậy quan hệ tăng là **nghiêm ngặt**. Nếu cần map, có thể gắn payload với key; nếu cần multiset, phải bổ sung chính sách tần suất hoặc cách phân biệt bản sao, không tự ý cho khóa trùng trong code set.

### 1.2. Bất biến heap theo priority

Với min-priority treap, mỗi cạnh từ cha xuống con thỏa:

\[
u.priority < child.priority
\]

nếu các priority là **duy nhất**. Với giá trị priority có thể trùng, phải có quy tắc hòa rõ ràng, ví dụ so cặp `(priority, serial)` hoặc bốc lại khi trùng, và giữ đúng quan hệ ưu tiên toàn phần khi quay/split/merge.

**Lưu ý:** heap theo priority **không** có nghĩa khóa nhỏ nhất luôn ở gốc. Gốc có **priority nhỏ nhất**, còn khóa nhỏ nhất nằm ở node ngoài cùng bên trái như một BST thông thường.

### 1.3. Ví dụ một treap hợp lệ

Giả sử các cặp `(key, priority)`:

```text
(10, 80), (20, 30), (25, 60), (30, 10), (40, 70), (50, 20)
```

Một treap hợp lệ là:

```text
                        (30,10)
                       /       \
                 (20,30)       (50,20)
                 /    \         /
            (10,80) (25,60) (40,70)
```

Kiểm tra bằng mắt:

- BST: các khóa cây trái của 30 là 10,20,25 (đều <30); cây phải là 40,50 (đều >30).
- Heap: `10<30`, `10<20`, `30<80`, `30<60` và `20<70`.
- Duyệt **inorder** theo khóa thu được `10,20,25,30,40,50`, không phụ thuộc thứ tự priority.

### 1.4. Một hình dạng không hợp lệ

```text
         (30,50)
         /
     (20,10)
```

Cây này **đúng BST** nhưng **sai min-heap** vì con 20 có priority 10 nhỏ hơn priority 50 của cha. Một phép quay phải tại node 30 có thể đưa 20 lên trên mà vẫn giữ thứ tự BST.

**Không được đánh đồng** “BST đúng” với “treap đúng”: mọi thao tác phải bảo toàn **cả hai** bất biến.

## 2. Treap là Cartesian tree của các cặp khóa–ưu tiên

Khi **mọi key phân biệt** và **mọi priority phân biệt**, hai bất biến quyết định **duy nhất** hình dạng cây.

Quy tắc dựng:

1. Node có **priority nhỏ nhất** trong toàn tập làm **gốc**.
2. Những node có key nhỏ hơn key gốc tạo cây con trái.
3. Những node có key lớn hơn key gốc tạo cây con phải.
4. Lặp lại cùng quy tắc trên từng cây con.

Với bộ cặp ở Mục 1, priority nhỏ nhất là 10 tại key 30 nên root phải là 30. Bên trái `{10,20,25}`, priority nhỏ nhất là 30 tại key 20; bên phải `{40,50}`, priority nhỏ nhất là 20 tại key 50. Các cây con tiếp tục được quyết định duy nhất.

### 2.1. Vì sao hình dạng là duy nhất?

Gốc phải là node có priority nhỏ nhất để thỏa min-heap. Nếu chọn node khác làm gốc, node có priority nhỏ nhất phải nằm dưới nó, mâu thuẫn với bất biến heap.

Sau khi biết gốc, bất biến BST **bắt buộc** chia toàn bộ khóa sang trái/phải. Áp dụng quy tắc lập luận tương tự đệ quy cho mỗi nhóm cho thấy hình dạng duy nhất.

Khi hai node có priority bằng nhau, muốn tính duy nhất phải thêm một **tie-breaker** tạo thứ tự ưu tiên nghiêm ngặt.

### 2.2. Quan hệ với Cartesian tree

Hãy đặt các khóa theo thứ tự tăng:

```text
key:       10    20    25    30    40    50
priority:  80    30    60    10    70    20
```

Treap chính là một **min Cartesian tree** của dãy priority xét theo thứ tự khóa. Trong Cartesian tree, **inorder traversal** khôi phục thứ tự dãy gốc, còn mỗi cây con chọn phần tử có priority nhỏ nhất làm gốc.

Từ góc nhìn này, treap không phải là “ghép hai cây riêng biệt”; nó là **một cây duy nhất** thỏa hai quan hệ trên hai trường dữ liệu khác nhau.

### 2.3. Ưu tiên quyết định hình dạng, không quyết định ý nghĩa khóa

Nếu đổi priority của các node trong khi giữ nguyên key, cây có thể phải quay hoặc dựng lại. Nhưng **tập khóa logic** không đổi. Nếu cho phép sửa key trực tiếp sau khi đã nối node mà không xóa/chèn lại, bất biến BST có thể bị phá.

Trong một implementation set, nên xem key và priority của node **bất biến sau khi node được đưa vào cây**, trừ khi API cố tình hỗ trợ cập nhật có kiểm soát.

## 3. Quay phải và quay trái: đổi hình dạng, giữ thứ tự BST

Hai phép quay là công cụ xây treap theo hướng giống BST động. Khi node mới có priority cao hơn về mặt heap (số nhỏ hơn), ta đưa nó lên bằng phép quay mà không làm mất thứ tự khóa.

### 3.1. Quay phải

Giả sử `x` là con trái của `y`, còn `B` là cây con phải của x:

```text
Trước quay phải tại y:

            y
           / \
          x   C
         / \
        A   B

Sau:

          x
         / \
        A   y
           / \
          B   C
```

Vì `keys(A)<x.key<keys(B)<y.key<keys(C)`, sau quay vẫn là BST. Nếu x có priority tốt hơn (nhỏ hơn) y, đưa x lên còn giúp khôi phục bất biến min-heap tại vị trí đó.

Pseudocode:

```text
ROTATE_RIGHT(y):
    x = y.left
    assert x != NULL

    y.left = x.right
    x.right = y

    recompute_metadata(y)
    recompute_metadata(x)
    return x
```

Nếu có `subtree_size`, phải cập nhật **y trước x** vì sau quay y nằm dưới x.

### 3.2. Quay trái

Trường hợp đối xứng: `x` là con phải của `y`.

```text
Trước quay trái:

          y
         / \
        A   x
           / \
          B   C

Sau:

            x
           / \
          y   C
         / \
        A   B
```

Pseudocode:

```text
ROTATE_LEFT(y):
    x = y.right
    assert x != NULL

    y.right = x.left
    x.left = y

    recompute_metadata(y)
    recompute_metadata(x)
    return x
```

### 3.3. Ví dụ quay có cả key và priority

```text
Trước:

        (30,70)
        /
     (20,10)
          \
         (25,80)

Sau quay phải tại 30:

      (20,10)
            \
           (30,70)
           /
        (25,80)
```

Thứ tự inorder trước và sau đều là `20,25,30`. Priority gốc sau quay là 10, nhỏ hơn các priority 40 và 70 trong cây, nên bất biến heap thỏa.

**Cẩn thận:** phép quay không tự luôn làm treap hợp lệ. Nó chỉ giải quyết đúng quan hệ cha–con đang vi phạm **nếu những bất biến liên quan của các cây con đã đúng**. Không được quay tùy ý mà bỏ qua invariant về priority của các node khác.

## 4. Tìm kiếm: treap dùng đường BST, không tìm theo priority

Treap tra cứu khóa **y hệt BST**:

```text
CONTAINS(root, key):
    current = root
    while current != NULL:
        if key == current.key:
            return true
        if key < current.key:
            current = current.left
        else:
            current = current.right
    return false
```

Đường tìm **không dùng priority** để quyết định sang trái hay phải. Priority chỉ giải thích tại sao hình dạng có khả năng thấp theo kỳ vọng.

Với treap Mục 1:

- Tìm key 25: `30→20→25`.
- Tìm key 40: `30→50→40`.
- Tìm key 35: `30→50→40→NULL` (vắng mặt).
- Tìm key 10: `30→20→10`.

### 4.1. Độ phức tạp theo chiều cao thực tế

Gọi `h` là chiều cao tính bằng **số node** trên đường gốc–lá dài nhất. Mọi tìm kiếm đi nhiều nhất h node:

\[
T_{\rm find}=O(h).
\]

Nếu h=Θ(log n), tìm logarit; nếu cây lệch h=n, tìm tuyến tính. Chính **hình dạng treap** (do các priority đã rút) quyết định chi phí của một lần chạy cụ thể.

### 4.2. Tìm `lower_bound` và tiền nhiệm

Ta có thể tận dụng BST để tìm:

- `lower_bound(k)`: khóa nhỏ nhất ≥k, hoặc không có.
- `predecessor(k)`: khóa lớn nhất <k, hoặc không có.

Pseudocode lower bound:

```text
LOWER_BOUND(root, k):
    candidate = NULL
    current = root
    while current != NULL:
        if current.key >= k:
            candidate = current
            current = current.left
        else:
            current = current.right
    return candidate
```

Không cần duyệt toàn bộ inorder: với mỗi node, ta loại được một cây con nhờ BST.

## 5. Chèn treap bằng quay: BST trước, heap sau

Một cách chèn phổ biến:

1. Tìm chỗ đặt node bằng **so sánh khóa** như BST.
2. Nếu key trùng, trả kết quả **không chèn** theo chính sách set.
3. Gán **priority ngẫu nhiên** cho node mới.
4. Gắn node như lá BST.
5. Khi priority của node mới nhỏ hơn priority cha, **quay** để đưa nó lên cho đến khi không còn vi phạm heap.

### 5.1. Pseudocode chèn đệ quy với quay

```text
INSERT(root, new_node):
    if root == NULL:
        return new_node

    if new_node.key < root.key:
        root.left = INSERT(root.left, new_node)
        if root.left.priority < root.priority:
            root = ROTATE_RIGHT(root)

    else if new_node.key > root.key:
        root.right = INSERT(root.right, new_node)
        if root.right.priority < root.priority:
            root = ROTATE_LEFT(root)

    else:
        return root  # Set: key đã tồn tại.

    recompute_metadata(root)
    return root
```

**Điểm tinh tế:** nếu một phép chèn trùng không được phép tạo node, API thường kiểm tra trùng **trước khi bốc priority**, để không tiêu thụ nguồn RNG không cần thiết. Pseudocode nhận `new_node` đã tạo nhằm tập trung vào cơ chế quay; implementation hoàn chỉnh có thể đặt bước kiểm tra trùng ở ngoài.

### 5.2. Ví dụ thêm khóa có priority rất tốt

Bắt đầu:

```text
        (30,30)
       /       \
  (20,40)    (50,50)
```

Chèn node `(25,10)`: theo BST, 25 là con phải của 20:

```text
        (30,30)
       /       \
   (20,40)   (50,50)
         \
        (25,10)
```

Vì 10<40, quay trái tại 20:

```text
         (30,30)
        /       \
    (25,10)    (50,50)
     /
 (20,40)
```

Vì 10<30, quay phải tại 30:

```text
         (25,10)
        /       \
   (20,40)    (30,30)
                    \
                   (50,50)
```

Kiểm tra lại: inorder `20,25,30,50`; priority cha tại mọi cạnh nhỏ hơn priority con. Node mới được đưa lên đúng vị trí phù hợp cả BST và min-heap.

### 5.3. Vì sao chèn bằng quay đúng?

Phép chèn ở lá **không phá BST** vì tìm vị trí bằng key. Mỗi phép quay trái/phải **giữ BST**. Khi đẩy node có priority nhỏ hơn cha lên, ta sửa một cạnh heap bị vi phạm, đồng thời không làm hỏng thứ tự heap trong các cây con vốn đã hợp lệ.

Quy nạp theo đường quay chứng minh khi node mới dừng ở vị trí có priority lớn hơn priority cha (hoặc làm gốc), cả hai bất biến được khôi phục.

**Vấn đề thực thi:** mã đệ quy sử dụng O(h) stack trong một lần chèn; worst-case h=n dù kỳ vọng logarit. Nếu môi trường có stack depth thấp hoặc dữ liệu đối kháng, phải cân nhắc bản lặp, fallback hoặc cây có worst-case cứng.


## 6. `split`: chia treap theo một ngưỡng khóa

`SPLIT(T,k)` tách một treap T thành hai treap:

\[
A=\{x\in T:x.key<k\},\qquad
B=\{x\in T:x.key\ge k\}.
\]

Các node **không bị nhân bản**: ta chỉ thay một số liên kết, rồi trả hai gốc mới. Sau phép chia, bản T cũ không còn được dùng như một cây nguyên vẹn nếu implementation **sửa tại chỗ**.

### 6.1. Ví dụ tách theo khóa 30

Từ treap ở Mục 1:

```text
Trước SPLIT(T,30):

                  (30,10)
                 /       \
           (20,30)       (50,20)
           /    \         /
      (10,80) (25,60) (40,70)

Sau:
A (key < 30)            B (key >= 30)

      (20,30)                  (30,10)
       /   \                        \
  (10,80) (25,60)                (50,20)
                                 /
                             (40,70)
```

A có 10,20,25; B có 30,40,50. Mỗi cây con giữ được BST theo key và heap theo priority.

### 6.2. Thuật toán đệ quy

```text
SPLIT(root, k) -> (A, B):
    if root == NULL:
        return (NULL, NULL)

    if root.key < k:
        (left_part, right_part) = SPLIT(root.right, k)
        root.right = left_part
        recompute_metadata(root)
        return (root, right_part)

    else:
        (left_part, right_part) = SPLIT(root.left, k)
        root.left = right_part
        recompute_metadata(root)
        return (left_part, root)
```

Chỉ cần đi dọc **một đường BST**: với root nhỏ hơn k, root thuộc A; với root ≥k, root thuộc B. Đường còn lại bên không bị chia vẫn được giữ nguyên.

### 6.3. Chứng minh ngắn

Xét `root.key<k`. Tất cả key trong `root.left` nhỏ hơn root nên cũng nhỏ hơn k, chắc chắn thuộc A. Chỉ `root.right` có thể chứa cả key <k và ≥k; ta chia nó thành hai phần.

Gắn phần nhỏ hơn k trở lại `root.right` giữ đúng BST; phần lớn hơn hoặc bằng k trả riêng làm B. Heap cũng được giữ: root có priority tốt hơn mọi node trong cây con ban đầu, nên vẫn tốt hơn các node còn được giữ dưới nó.

Trường hợp `root.key≥k` đối xứng. Quy nạp theo số node cho thấy hai kết quả chứa đúng **mỗi node gốc một lần**, không thiếu và không trùng.

### 6.4. Độ phức tạp của split

Gọi h là chiều cao treap trước khi chia. Mỗi lời gọi chỉ đi xuống **một nhánh**, nên:

- Thời gian: **O(h)**.
- Stack đệ quy: **O(h)**.
- Không cần cấp thêm n node dữ liệu.
- Với treap random đúng mô hình, expected O(log n); worst-case O(n).

Đừng nhầm hai cây trả về với **hai bản sao độc lập**: bản triển khai dùng con trỏ thay đổi cấu trúc sở hữu. Nếu muốn persistent treap, phải **path-copy** hoặc dùng cơ chế bất biến thích hợp.

## 7. `merge`: hợp nhất hai treap có khoảng khóa tách biệt

`MERGE(A,B)` ghép hai treap thành một, **chỉ khi**:

\[
\boxed{\forall a\in A,\forall b\in B:\ a.key<b.key}.
\]

Nói cách khác, mọi khóa bên trái phải **nhỏ hơn** mọi khóa bên phải. Đây là tiền đề của merge dùng BST; không kiểm tra nó có thể làm hỏng cấu trúc ngay cả khi các priority được xếp đúng.

### 7.1. Vì sao chọn gốc theo priority?

Giả sử root A có priority `p_A` và root B có priority `p_B`:

- Nếu `p_A<p_B`, gốc kết quả bắt buộc là root A. Cây phải mới của nó là `MERGE(A.right,B)`.
- Nếu `p_B<p_A`, gốc kết quả là root B. Cây trái mới của nó là `MERGE(A,B.left)`.
- Nếu một cây rỗng, trả cây còn lại.

Đây là việc chọn gốc có priority nhỏ nhất trong hai tập theo bất biến min-heap.

### 7.2. Pseudocode hợp nhất

```text
MERGE(A, B):
    # Tiền điều kiện: mọi key(A) < mọi key(B).
    # Mọi priority được so theo một thứ tự toàn phần duy nhất.
    if A == NULL: return B
    if B == NULL: return A

    if A.priority < B.priority:
        A.right = MERGE(A.right, B)
        recompute_metadata(A)
        return A

    else:
        B.left = MERGE(A, B.left)
        recompute_metadata(B)
        return B
```

Khi chọn gốc A, `A.left` không thay đổi. Các node `A.right` và B đều lớn hơn A.key nên có thể là con phải của A. Heap được duy trì vì A.priority nhỏ hơn root B và nhỏ hơn các node dưới A theo bất biến đã có; phép merge đệ quy tự xử lý phần còn lại.

### 7.3. Ví dụ merge quay lại trạng thái ban đầu

Từ split theo 30 ở Mục 6:

```text
A root (20,30): 10,20,25
B root (30,10): 30,40,50
```

Vì root B có priority 10 nhỏ hơn 30 của root A, merge chọn root B. Phần trái mới của B được tạo bằng `MERGE(A, B.left)`, mà B.left ban đầu rỗng. Vậy toàn bộ A trở thành con trái của 30, thu lại treap như trước split.

### 7.4. Điều kiện khóa và xử lý priority trùng

Một ví dụ sai:

```text
A có khóa {10, 50}
B có khóa {20, 30}
```

`MERGE(A,B)` **không hợp lệ** vì 50>20. Muốn gộp hai tập khóa bất kỳ, cần một thuật toán union phù hợp, hoặc chèn từng khóa vào treap, **không** gọi merge mù.

Nếu hai root có priority bằng nhau và code dùng nhánh `else` để chọn B, nó có thể vẫn giữ heap không nghiêm ngặt, nhưng tính duy nhất và chứng minh phân phối theo priority liên tục không còn nguyên xi. Code thực hành dùng cặp ưu tiên có tie-breaker để tạo **thứ tự nghiêm ngặt**.

### 7.5. Chi phí của merge

Đường đệ quy chỉ đi qua **nhánh phải của A** và/hoặc **nhánh trái của B** tại mỗi bước, không duyệt toàn bộ hai cây. Chặn trên theo chiều cao:

\[
T_{\rm merge}=O(h_A+h_B),
\]

và stack phụ trợ cùng bậc. Trên các treap random với điều kiện phân phối phù hợp, expected O(log(n_A+n_B)); trong trường hợp cây lệch, worst O(n_A+n_B).

Không được hứa O(log n) kỳ vọng cho **mọi cặp treap được đối thủ chọn sau khi quan sát priority**, vì cách chọn đầu vào ghép có thể làm thay giả định random.

## 8. Chèn bằng `split` và `merge`

Một cách cài đặt treap khác không gọi quay tường minh:

1. Kiểm tra khóa `k` chưa tồn tại trong set.
2. Bốc priority cho node mới `v`.
3. `(A,B)=SPLIT(root,k)`.
4. `root=MERGE(MERGE(A,v),B)`.

Minh họa:

```text
Ban đầu:
      root T có khóa [10,20,40,50]

Sau SPLIT(T,30):
      A=[10,20], B=[40,50]

Node mới:
      v=(30, priority_random)

MERGE(A,v)  -> treap khóa [10,20,30]
MERGE(...,B)-> treap khóa [10,20,30,40,50]
```

Phép merge hợp lệ vì:

\[
\max key(A)<k<\min key(B)
\]

khi k chưa tồn tại. Nếu có khóa bằng k, cách chèn set chuẩn trả `False` trước khi split; không tạo hai node cùng khóa.

### 8.1. Pseudocode hoàn chỉnh

```text
INSERT_SET(root, k):
    if CONTAINS(root,k):
        return (root, false)

    fresh = NODE(k, RANDOM_PRIORITY())
    (A,B) = SPLIT(root,k)

    root = MERGE(MERGE(A,fresh),B)
    return (root, true)
```

**Chú ý về ngoại lệ/cấp phát:** chương trình nên chuẩn bị `fresh` và những bộ nhớ cần thiết trước khi bắt đầu thay con trỏ bằng split. Nếu split thành công nhưng một bước sau báo lỗi và ta không phục hồi được hai gốc, bộ chứa có thể còn ở trạng thái chia đôi. Một implementation có yêu cầu exception safety cao cần hợp đồng cấp phát/so sánh khóa cụ thể hoặc kế hoạch rollback; đoạn pseudocode chỉ minh họa thao tác tuần tự với các phép gán nội bộ không thất bại.

### 8.2. Phân tích chi phí

- `contains`: O(h).
- `split`: O(h).
- Hai phép `merge`: mỗi phép theo chiều cao các cây được ghép.
- Metadata `size` được cập nhật trên các đường thay đổi.

Trong phân phối treap random chuẩn và với một khóa chèn cố định độc lập với random, tổng expected **O(log n)**. Worst-case theo hình dạng có thể O(n), còn stack đệ quy worst O(n).

So với chèn bằng quay, cách split/merge đặc biệt thuận tiện khi ta còn muốn **tách tập theo ngưỡng**, **hợp hai dải khóa**, hoặc **xóa cả một dải**. Dù thuận tiện, nó không tự tăng bảo đảm worst-case so với các phép quay.

## 9. Xóa khóa bằng cách ghép hai cây con

Giả sử tìm thấy node `target` mang key k. Vì target thuộc BST:

\[
\forall x\in target.left: x.key<k,\qquad
\forall y\in target.right: y.key>k.
\]

Do đó mọi khóa trong `target.left` đều nhỏ hơn mọi khóa trong `target.right`. Ta có thể:

1. Lấy gốc của hai cây con trái/phải của target.
2. `replacement=MERGE(target.left,target.right)`.
3. Gắn replacement vào vị trí cũ của target.
4. Hủy node target theo đúng hợp đồng ownership.
5. Cập nhật `subtree_size` trên đường từ tổ tiên tới gốc.

### 9.1. Ví dụ xóa một node có hai con

Treap:

```text
               (30,10)
              /       \
         (20,30)     (50,20)
         /   \          /
    (10,80) (25,60)  (40,70)
```

Xóa node 30. Hai cây con gồm:

```text
A: (20,30) với các khóa 10,20,25
B: (50,20) với các khóa 40,50
```

Vì priority gốc B là 20 nhỏ hơn priority gốc A là 30, `MERGE(A,B)` chọn 50 làm gốc rồi gắn A qua các bước ghép ở cây con trái của 50:

```text
             (50,20)
             /
         (20,30)
         /     \
    (10,80)   (25,60)
                     \
                    (40,70)
```

**Kiểm tra:** inorder `10,20,25,40,50`; mọi priority cha nhỏ hơn con. Ta đã loại đúng một node key 30, không cần sao chép key từ successor như cách xóa BST thông thường.

### 9.2. Pseudocode xóa khóa

```text
ERASE(root,k) -> (new_root,removed):
    if root == NULL:
        return (NULL,false)

    if k < root.key:
        (root.left,removed) = ERASE(root.left,k)
        recompute_metadata(root)
        return (root,removed)

    if k > root.key:
        (root.right,removed) = ERASE(root.right,k)
        recompute_metadata(root)
        return (root,removed)

    replacement = MERGE(root.left,root.right)
    destroy_exactly_this_node(root)
    return (replacement,true)
```

Khi không tìm thấy k, cấu trúc logic không đổi. Khi xóa thành công, `size` của toàn set giảm **một**, bất kể target có bao nhiêu con hoặc độ sâu bao nhiêu.

### 9.3. Xóa bằng quay cũng có thể làm được

Một biến thể khác không dùng merge trực tiếp:

- Khi node cần xóa có hai con, chọn con có **priority tốt hơn** (nhỏ hơn) để đưa lên bằng quay.
- Lặp cho đến khi node mục tiêu chỉ còn tối đa một con.
- Nối cha với con còn lại và hủy node.

Cách này duy trì thứ tự BST đồng thời dần đưa node bị xóa xuống. Bản split/merge thường diễn đạt ngắn gọn hơn, còn quay phù hợp nếu code đã có primitive rotate và cần tương thích một API BST động.

### 9.4. Chi phí và quản lý tài nguyên

Tìm target O(h), ghép hai cây con theo đường biên O(h_left+h_right), cập nhật metadata theo các đường sửa. Trong mô hình random với khóa được chọn không dựa vào priority, thao tác có expected O(log n); worst-case O(n).

Trong C/C++:

- Không được `free` target **trước** khi lấy các con trỏ `left/right` cần thiết.
- Sau khi merge hai cây con, không được để node target vẫn reachable từ gốc mới.
- Chỉ hủy **một node target**; các node trong hai cây con được giữ nguyên identity.
- Nếu một iterator ngoài đang giữ `Node*` tới target, xóa có thể làm con trỏ ấy treo. Đây là vấn đề vòng đời/iterator invalidation cần hợp đồng riêng.


## 10. Python: cài đặt `TreapSet` đầy đủ với `split` và `merge`

Mục này cung cấp **một chương trình Python 3.10+ tự chứa**, không dùng thư viện cấu trúc dữ liệu bên ngoài. Treap lưu **khóa nguyên phân biệt**, sử dụng min-heap trên cặp priority, duy trì `size` mỗi cây con và có các thao tác:

- `contains`, `lower_bound`, `predecessor`.
- `insert` và `discard`.
- `rank(key)`: số khóa nhỏ hơn key.
- `select(index)`: khóa thứ index theo thứ tự tăng, **đánh chỉ số từ 0**.
- `keys()` và `range_keys(low,high)` theo khoảng nửa mở `[low,high)`.
- `assert_valid()`: kiểm tra sâu cả hai bất biến, danh tính node, chu trình và kích thước cây con.

Để các priority phân biệt cả khi PRNG trả lại cùng số, ta dùng `priority=(random_128_bits, serial)`. Trường `serial` làm **tie-breaker duy nhất trong một instance**, còn random_128_bits quyết định hình dạng gần như toàn bộ trong quy mô thực tế. Khi nói kết quả xác suất **IID liên tục** ở phần lý thuyết, đó là **mô hình lý tưởng**; một PRNG 128-bit hữu hạn với tie-breaker không đúng tuyệt đối phân phối liên tục, dù xác suất trùng raw priority cực nhỏ nếu số node thực tế không quá lớn.

### 10.1. Mã Python chạy độc lập

```python
from __future__ import annotations

import random
from dataclasses import dataclass
from collections.abc import Iterator


@dataclass(eq=False, slots=True)
class Node:
    key: int
    priority: tuple[int, int]
    left: Node | None = None
    right: Node | None = None
    size: int = 1


def node_size(node: Node | None) -> int:
    return 0 if node is None else node.size


def pull(node: Node) -> None:
    """Đồng bộ size từ hai cây con sau khi sửa liên kết."""
    node.size = 1 + node_size(node.left) + node_size(node.right)


def split(
    root: Node | None, key: int
) -> tuple[Node | None, Node | None]:
    """Chia: left có key < key; right có key >= key.

    Sửa liên kết node tại chỗ, không path-copy.
    """
    if root is None:
        return None, None

    if root.key < key:
        less, greater_or_equal = split(root.right, key)
        root.right = less
        pull(root)
        return root, greater_or_equal

    less, greater_or_equal = split(root.left, key)
    root.left = greater_or_equal
    pull(root)
    return less, root


def merge(left: Node | None, right: Node | None) -> Node | None:
    """Tiền điều kiện: mọi key(left) < mọi key(right)."""
    if left is None:
        return right
    if right is None:
        return left

    if left.priority < right.priority:
        left.right = merge(left.right, right)
        pull(left)
        return left

    right.left = merge(left, right.left)
    pull(right)
    return right


def erase(
    root: Node | None, key: int
) -> tuple[Node | None, bool]:
    """Gỡ đúng một node mang key, trả (root_mới, có_xóa)."""
    if root is None:
        return None, False

    if key < root.key:
        root.left, removed = erase(root.left, key)
        pull(root)
        return root, removed

    if key > root.key:
        root.right, removed = erase(root.right, key)
        pull(root)
        return root, removed

    replacement = merge(root.left, root.right)

    # Tách tham chiếu từ node cũ; cây mới sở hữu các cây con.
    root.left = None
    root.right = None
    root.size = 1
    return replacement, True


class TreapSet:
    """Treap set đơn luồng, khóa int, min-priority heap."""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._root: Node | None = None
        self._serial = 0
        self._version = 0

    @staticmethod
    def _require_int(key: int) -> None:
        if type(key) is not int:
            raise TypeError("TreapSet chỉ nhận khóa int (không nhận bool)")

    def __len__(self) -> int:
        return node_size(self._root)

    def contains(self, key: int) -> bool:
        self._require_int(key)
        current = self._root

        while current is not None:
            if key == current.key:
                return True
            current = (
                current.left if key < current.key
                else current.right
            )

        return False

    def lower_bound(self, key: int) -> int | None:
        """Khóa nhỏ nhất >= key, nếu không có thì None."""
        self._require_int(key)
        current = self._root
        candidate: Node | None = None

        while current is not None:
            if current.key >= key:
                candidate = current
                current = current.left
            else:
                current = current.right

        return None if candidate is None else candidate.key

    def predecessor(self, key: int) -> int | None:
        """Khóa lớn nhất < key, nếu không có thì None."""
        self._require_int(key)
        current = self._root
        candidate: Node | None = None

        while current is not None:
            if current.key < key:
                candidate = current
                current = current.right
            else:
                current = current.left

        return None if candidate is None else candidate.key

    def insert(self, key: int) -> bool:
        """True khi có khóa mới; False nếu khóa đã tồn tại."""
        self._require_int(key)

        # Không tiêu thụ RNG khi có khóa trùng.
        if self.contains(key):
            return False

        priority = (self._rng.getrandbits(128), self._serial)
        fresh = Node(key=key, priority=priority)

        # Chỉ khi đã cấp được node mới bắt đầu đổi liên kết.
        self._serial += 1
        smaller, greater_or_equal = split(self._root, key)
        self._root = merge(merge(smaller, fresh), greater_or_equal)
        self._version += 1
        return True

    def discard(self, key: int) -> bool:
        self._require_int(key)
        self._root, removed = erase(self._root, key)

        if removed:
            self._version += 1

        return removed

    def rank(self, key: int) -> int:
        """Số khóa < key, kể cả khi key chưa tồn tại."""
        self._require_int(key)
        result = 0
        current = self._root

        while current is not None:
            if key <= current.key:
                current = current.left
            else:
                result += 1 + node_size(current.left)
                current = current.right

        return result

    def select(self, index: int) -> int:
        """Khóa thứ index (0-based) trong thứ tự tăng."""
        if type(index) is not int or not (0 <= index < len(self)):
            raise IndexError("select(index): index ngoài [0,size)")

        current = self._root

        while current is not None:
            left_size = node_size(current.left)

            if index < left_size:
                current = current.left
            elif index == left_size:
                return current.key
            else:
                index -= left_size + 1
                current = current.right

        raise AssertionError("Treap thiếu node hoặc metadata size sai")

    def keys(self) -> Iterator[int]:
        """Iterator inorder; không sửa cây qua API khi đang duyệt."""
        expected_version = self._version
        stack: list[Node] = []
        current = self._root

        while current is not None or stack:
            if self._version != expected_version:
                raise RuntimeError("Treap thay đổi khi đang duyệt")

            while current is not None:
                stack.append(current)
                current = current.left

            current = stack.pop()
            yield current.key
            current = current.right

        if self._version != expected_version:
            raise RuntimeError("Treap thay đổi khi đang duyệt")

    def range_keys(self, low: int, high: int) -> Iterator[int]:
        """Sinh các khóa thuộc [low, high), không tạo list."""
        self._require_int(low)
        self._require_int(high)

        if low >= high:
            return

        expected_version = self._version
        stack: list[Node] = []
        current = self._root

        while current is not None or stack:
            if self._version != expected_version:
                raise RuntimeError("Treap thay đổi khi đang duyệt")

            # Bỏ cả cây con trái của node có key < low.
            while current is not None:
                if current.key < low:
                    current = current.right
                else:
                    stack.append(current)
                    current = current.left

            if not stack:
                break

            current = stack.pop()
            if current.key >= high:
                break

            yield current.key
            current = current.right

        if self._version != expected_version:
            raise RuntimeError("Treap thay đổi khi đang duyệt")

    def assert_valid(self) -> None:
        """Validator O(n) thời gian, O(n) nhớ, chỉ dùng debug."""
        seen: set[Node] = set()

        def walk(
            node: Node | None,
            low: int | None,
            high: int | None,
            parent_prio: tuple[int, int] | None,
        ) -> int:
            if node is None:
                return 0

            assert node not in seen, "Lặp lại node hoặc chu trình"
            seen.add(node)
            assert type(node.key) is int
            assert low is None or low < node.key
            assert high is None or node.key < high
            assert parent_prio is None or parent_prio < node.priority

            left_count = walk(node.left, low, node.key, node.priority)
            right_count = walk(node.right, node.key, high, node.priority)

            expected_size = 1 + left_count + right_count
            assert node.size == expected_size, "Sai subtree_size"
            return expected_size

        total = walk(self._root, None, None, None)
        assert total == len(self)
        assert total == len(seen)


def demonstration() -> None:
    tree = TreapSet(seed=2026)

    assert len(tree) == 0
    assert tree.lower_bound(5) is None

    for key in (30, 10, 50, 20, 40, 25):
        assert tree.insert(key)

    tree.assert_valid()
    assert len(tree) == 6
    assert list(tree.keys()) == [10, 20, 25, 30, 40, 50]
    assert tree.contains(25)
    assert not tree.contains(999)
    assert tree.lower_bound(26) == 30
    assert tree.predecessor(25) == 20
    assert tree.rank(25) == 2
    assert tree.rank(26) == 3
    assert tree.select(0) == 10
    assert tree.select(2) == 25
    assert tree.select(5) == 50
    assert list(tree.range_keys(15, 45)) == [20, 25, 30, 40]

    assert not tree.insert(30)  # Trùng key: không nhân bản node.
    assert tree.discard(30)
    assert not tree.discard(30)
    tree.assert_valid()

    assert list(tree.keys()) == [10, 20, 25, 40, 50]
    assert len(tree) == 5

    for key in (10, 20, 25, 40, 50):
        assert tree.discard(key)

    assert len(tree) == 0
    assert list(tree.keys()) == []
    tree.assert_valid()
    print("TreapSet: OK")


if __name__ == "__main__":
    demonstration()
```

### 10.2. Vì sao dùng `priority=(random_128_bits, serial)`?

Hai node có thể bốc trùng số trong một PRNG hữu hạn. Nếu dùng so sánh `<` để chọn gốc, một tie không được xử lý nhất quán có thể làm đứt chứng minh **thứ tự ưu tiên nghiêm ngặt** và làm kết quả phụ thuộc quy tắc chèn.

Cặp `(số_random, serial)` tạo thứ tự đầy đủ, không trùng trong một instance vì `serial` tăng cho mỗi node mới. Nó không cho một RNG bảo mật, không làm priority có phân phối liên tục lý tưởng và **không loại trừ worst-case**.

Một cách khác là rút lại priority nếu đã được sử dụng, nhưng phải xét lỗi/tài nguyên và cách quản lý các giá trị đã dùng nếu cần giới hạn bộ nhớ.

### 10.3. Vì sao `size` phải được cập nhật ở split/merge/erase?

`rank` và `select` dùng số node trong cây con trái để bỏ qua cả một nhánh. Nếu `size` lỗi, tìm chính xác theo key vẫn có thể hoạt động trong khi `rank/select` trả sai.

`pull(node)` tính:

\[
node.size=1+size(node.left)+size(node.right).
\]

Mỗi phép `split`, `merge` và `erase` gọi `pull` trên các node có liên kết con thay đổi. Trong bản `erase`, khi node bị gỡ, ta trả `merge(left,right)`; các tổ tiên trên đường quay về cũng được cập nhật `size`.

**Không được** dùng `len(node.left)` vì `left` là node hoặc None, không phải một list. Metadata `size` có ý nghĩa vì nó được **duy trì khi cập nhật**, không phải được tính lại toàn cây mỗi lần truy vấn.

### 10.4. Độ phức tạp thực tế của mã

Gọi n là số khóa và h là chiều cao cây tại thời điểm thao tác.

| Thao tác | Thời gian theo h | Kỳ vọng nếu priority gần mô hình IID chuẩn | Bộ nhớ phụ trợ |
| --- | --- | --- | --- |
| `contains`, `lower_bound`, `predecessor` | O(h) | O(log n) | O(1) |
| `rank`, `select` | O(h) | O(log n) | O(1) |
| `split` | O(h) | O(log n) | O(h) stack |
| `merge` | O(h_A+h_B) | O(log(n_A+n_B)) dưới giả định thích hợp | O(h_A+h_B) stack |
| `insert` (contains+split+merge) | O(h) theo các cây phát sinh, chặn O(n) tổng quát | O(log n) | O(h) stack |
| `discard` | O(h) theo đường xóa/merge, chặn O(n) | O(log n) | O(h) stack |
| `keys` xuất n khóa | O(n) | O(n) | O(h) stack tự quản |
| `range_keys` xuất k khóa | O(h+k) | O(log n+k) | O(h) stack |
| `assert_valid` | O(n) | O(n) | O(n) set và O(h) đệ quy |

**Cảnh báo về đệ quy:** `split`, `merge`, `erase` và `assert_valid` dùng đệ quy. Dù h kỳ vọng O(log n), trường hợp cây lệch có thể khiến Python ném `RecursionError` trước khi hoàn thành thao tác. Mã mang tính học thuật đơn luồng; ứng dụng cần bảo đảm mạnh hơn phải dùng phiên bản lặp, giới hạn độ sâu an toàn hoặc một cấu trúc cân bằng tất định.

### 10.5. Iterator được phép quan sát điều gì?

`keys` và `range_keys` là **generator**. Phần thân chỉ bắt đầu chạy khi gọi `next` lần đầu; phiên bản cấu trúc được ghi lúc ấy, không phải lúc tạo object generator. Khi có thay đổi `insert/discard` **thành công** qua API trong lúc đang duyệt, lần gọi tiếp theo sẽ phát hiện version khác và ném `RuntimeError`.

- Đây là **fail-fast best effort trong chương trình tuần tự**, không phải snapshot.
- Chèn trùng hoặc xóa khóa vắng không đổi version trong code.
- Sửa trực tiếp `_root`/`Node.left`/`Node.right` bỏ qua API có thể không bị phát hiện.
- Đọc/ghi đa luồng vẫn cần khóa hoặc concurrent treap được thiết kế riêng; `_version` không thay thế đồng bộ.

Nếu cần iterator ổn định qua cập nhật, hãy chọn snapshot, immutable/persistent tree hoặc hợp đồng cursor được thiết kế rõ, thay vì dùng generator của bản học thuật như thể nó an toàn trên mọi trạng thái.

### 10.6. Tính an toàn trước ngoại lệ còn giới hạn

Đoạn `insert` chuẩn bị `fresh` trước khi thay liên kết, giảm nguy cơ cấp phát node giữa chừng. Nhưng `split/merge` sửa cây **tại chỗ** và dùng đệ quy; nếu comparator bất thường, lỗi runtime hoặc `RecursionError` xảy ra **sau khi đã sửa vài cạnh**, không có bảo đảm transaction/rollback mạnh.

Code giới hạn key là **`int` chính xác** và dùng tuple ưu tiên có comparator nhất quán để đơn giản hóa; vẫn cần chiến lược lỗi/khả năng khôi phục cho hệ thống production.

Tương tự, bản `discard` tách tham chiếu node cũ trong Python nhưng không thể khiến mọi alias bên ngoài tự biến mất. Trong ngôn ngữ có `free/delete`, memory reclamation càng phải được xử lý riêng.

## 11. `rank` và `select`: biến treap thành cây có thống kê thứ tự

BST giữ được thứ tự khóa, nhưng muốn trả phần tử theo **vị trí** cần metadata kích thước cây con.

### 11.1. Đếm bao nhiêu khóa nhỏ hơn `k`

Tại node `u`:

- Nếu `k≤u.key`, tất cả khóa trong cây phải và u đều ≥k; đi trái.
- Nếu `k>u.key`, toàn bộ cây trái và u có khóa <k; cộng `1+size(u.left)` rồi đi phải.

Pseudocode:

```text
RANK(k):
    count = 0
    node = root
    while node != NULL:
        if k <= node.key:
            node = node.left
        else:
            count += 1 + size(node.left)
            node = node.right
    return count
```

Với dãy khóa `[10,20,25,30,40,50]`:

```text
rank(10) = 0
rank(25) = 2
rank(26) = 3
rank(60) = 6
```

Chỉ tiêu tốn O(h) vì không cần duyệt node trong cây con đã được đếm bằng metadata.

### 11.2. Chọn khóa thứ `index` với quy ước 0-based

Tại node u, đặt `left_size=size(u.left)`:

- Nếu `index<left_size`, đi trái.
- Nếu `index==left_size`, key của u chính là khóa cần tìm.
- Nếu `index>left_size`, đi phải với `index-=left_size+1`.

Với dãy trên:

```text
select(0) = 10
select(2) = 25
select(5) = 50
select(6) -> IndexError
```

Điều kiện tiên quyết: metadata `size` đúng tại **mọi node**. Chỉ sai một kích thước cây con cũng có thể khiến `select` đi sai nhánh.

### 11.3. Chi phí của metadata

Một trường integer `size` bổ sung **O(1) thông tin cho mỗi node**, tổng O(n) bộ nhớ. Mỗi phép quay/split/merge/chèn/xóa cập nhật `size` ở các node bị đổi liên kết, không cần quét lại toàn bộ.

Vì vậy `rank/select` vẫn O(log n) **kỳ vọng** dưới hình dạng random phù hợp, nhưng worst-case O(n) nếu treap lệch. Thêm `size` **không** biến treap thành cây cân bằng tất định.


## 12. Phân tích xác suất: vì sao tìm kiếm O(log n) kỳ vọng?

Muốn chứng minh treap có đường tìm ngắn, cần nêu rõ mô hình. Giả sử `n` khóa phân biệt đã được **cố định**:

\[
x_1<x_2<\cdots<x_n,
\]

và mỗi khóa nhận một priority **độc lập, cùng phân phối liên tục**. Các priority gần như chắc chắn khác nhau, và mọi hoán vị tương đối của n priority có xác suất `1/n!`. Đầu vào **không cần được xáo trộn**; random nằm ở priority nội bộ.

### 12.1. Xác suất một khóa là tổ tiên của khóa khác

Với `j<i`, node `x_j` là tổ tiên của node `x_i` **khi và chỉ khi** priority của `x_j` nhỏ nhất trên đoạn khóa liên tiếp:

\[
x_j,x_{j+1},\ldots,x_i.
\]

Đoạn này có `i-j+1` node với các priority IID, nên mỗi node có cơ hội bằng nhau trở thành phần tử ưu tiên nhất:

\[
\boxed{\Pr(x_j\text{ là tổ tiên của }x_i)=\frac1{i-j+1}}.
\]

Tương tự, với `j>i`:

\[
\Pr(x_j\text{ là tổ tiên của }x_i)=\frac1{j-i+1}.
\]

Công thức đến từ hai bất biến của Cartesian tree, **không** phải giả định rằng các đường đi được chọn ngẫu nhiên độc lập.

### 12.2. Độ sâu kỳ vọng của một khóa

Gọi `D_i` là số **cạnh** từ gốc tới `x_i`, bằng số tổ tiên thật của node. Đếm các tổ tiên bằng biến chỉ báo, sử dụng tính tuyến tính kỳ vọng:

\[
\begin{aligned}
E[D_i]
&=\sum_{j=1}^{i-1}\frac1{i-j+1}
 +\sum_{j=i+1}^{n}\frac1{j-i+1}\\
&=\mathcal H_i+\mathcal H_{n-i+1}-2,
\end{aligned}
\]

với `\mathcal H_m=\sum_{t=1}^{m}1/t` là **số điều hòa**. Đừng nhầm ký hiệu này với `height` của node.

Do `\mathcal H_m≤1+\ln m`:

\[
\boxed{E[D_i]=O(\log n)}.
\]

Ví dụ n=5, `i=3`:

\[
E[D_3]=2\mathcal H_3-2
=2(1+1/2+1/3)-2
=\frac53.
\]

Kỳ vọng không bắt buộc nguyên, dù một đường đi thực tế luôn có số cạnh nguyên.

### 12.3. Chiều cao cực đại phải được chứng minh riêng

Chiều cao h tính bằng **số node** trên đường gốc–lá dài nhất:

\[
h=1+\max_i D_i.
\]

Từ `E[D_i]=O(\log n)` cho mỗi i **không được** viết `E[\max_iD_i]=\max_iE[D_i]`. Đẳng thức ấy sai nói chung.

Trong mô hình priority IID liên tục, một kết quả chuẩn là:

\[
\boxed{E[h]=O(\log n)}.
\]

Ý tưởng chứng minh mạnh hơn: với một khóa cố định, các tổ tiên ở mỗi phía chính là những **kỷ lục priority thấp** khi quét từ khóa ấy sang trái hoặc phải. Với các biến IID liên tục, chỉ báo “phần tử mới thấp hơn tất cả phần tử đã thấy” của tiền tố dài t có xác suất `1/t`, và những chỉ báo kỷ lục **trong cùng một phía** độc lập. Do đó số tổ tiên mỗi phía là một tổng Bernoulli có kỳ vọng O(log n) và có chặn đuôi.

### 12.4. Phác thảo chặn đuôi để kiểm soát maximum

Gọi Y là số tổ tiên ở một phía của một node. Nếu phía ấy dài tối đa n phần tử:

\[
Y=\sum_{t=2}^{m}I_t,\qquad
\Pr(I_t=1)=\frac1t,\quad m\le n.
\]

Với `n≥2` và các chỉ báo kỷ lục độc lập:

\[
\begin{aligned}
E[e^Y]
&=\prod_{t=2}^{m}\left(1+\frac{e-1}{t}\right)\\
&\le \exp\left((e-1)\sum_{t=2}^{m}\frac1t\right)
\le n^{e-1}.
\end{aligned}
\]

Markov áp dụng cho `e^Y` cho:

\[
\Pr(Y\ge8\ln n)\le n^{e-1-8}.
\]

Độ sâu một node là tổng tổ tiên từ hai phía; **không cần giả sử hai phía độc lập** để dùng union bound:

\[
\Pr(D_i\ge16\ln n)\le2n^{e-1-8}.
\]

Union bound tiếp qua n node:

\[
\Pr(h\ge16\ln n+1)\le2n^{e-8}.
\]

Vì `e-8<-5`, xác suất này đủ nhỏ để kết hợp với `h≤n` và suy ra `E[h]=O(\log n)`. Hằng số lỏng nhưng cho thấy **một lộ trình chứng minh height** thay vì suy từ expected depth một cách sai.

### 12.5. Chi phí kỳ vọng và worst-case

Các thao tác đi theo đường cây (tìm/lower bound), cập nhật trên một số đường (chèn/xóa, split/merge) hoặc đi dọc đường dựa trên `subtree_size` (rank/select).

Với priority IID phù hợp và khóa thao tác được cố định độc lập với random:

- Tìm kiếm, chèn và xóa: **O(log n) kỳ vọng**.
- `rank`, `select`: **O(log n) kỳ vọng**, nếu `size` được bảo trì đúng.
- Duyệt toàn bộ n khóa theo inorder: **O(n)** thời gian.
- Bộ nhớ node: **O(n)** vì mỗi khóa chỉ có một node, hai con trỏ và O(1) metadata.

Với một hình dạng treap cụ thể có chiều cao h, phần lớn thao tác có **O(h)** hoặc O(tổng chiều cao các đường cập nhật); worst-case khi h=n có thể **Θ(n)**.

**Randomized treap không phải cây cân bằng tất định.** Không tuyên bố worst-case O(log n) chỉ dựa vào kỳ vọng logarit.

## 13. Một treap cực lệch vẫn đúng cả BST lẫn heap

Giả sử key tăng từ 1 đến 5 và priority cũng tăng theo key:

```text
(key, priority):
(1,1), (2,2), (3,3), (4,4), (5,5)

(1,1)
    \
    (2,2)
        \
        (3,3)
            \
            (4,4)
                \
                (5,5)
```

Cây thỏa BST, đồng thời parent.priority < child.priority trên mọi cạnh. Tuy vậy:

- Chiều cao có n node, n−1 cạnh.
- Tìm khóa lớn nhất hoặc khóa vắng lớn hơn mọi khóa tốn Θ(n).
- `rank/select` có thể tốn Θ(n).
- Các hàm đệ quy có thể dùng Θ(n) stack.

### 13.1. Sự kiện cực xấu có xác suất dương

Với n priority IID liên tục, thứ tự tăng hoàn toàn theo key là **một trong n! thứ tự tương đối** có xác suất bằng nhau:

\[
\boxed{\Pr(\text{priority tăng hoàn toàn theo key})=\frac1{n!}}.
\]

Đây là xác suất của **một trạng thái đặc biệt**, không phải xác suất của **mọi cây cao Θ(n)**. Nhưng chỉ cần một hình dạng hợp lệ có chi phí tuyến tính đã đủ để bác bỏ worst-case logarit.

### 13.2. Ba cách đọc một tuyên bố về chiều cao

| Phát biểu | Đúng? | Giải thích |
| --- | --- | --- |
| “Treap luôn cao O(log n)” | Không | Hình dạng đường thẳng hợp lệ |
| “Treap random IID có chiều cao kỳ vọng O(log n)” | Có, dưới giả định đã nêu | Phân tích random Cartesian tree |
| “Với bất kỳ seed nào, chiều cao không quá c log n” | Không | Seed có thể tạo thứ tự bất lợi |

Không nên nhầm **max observed height** qua 20 seed kiểm thử với **worst-case toán học**.

### 13.3. Tránh buộc priority phụ thuộc một cách đơn giản vào key

Đặt `priority=key` trên tập khóa sorted biến treap min-priority thành **cây lệch phải một cách tất định**. Dùng `priority=hash(key)` có thể nhanh trong một số workload, nhưng muốn có định lý expected phải chứng minh những tính chất random cần thiết của hash đối với **tập khóa và đối thủ** đang xét.

Một đối thủ quan sát priority, hình dạng hoặc thời gian rồi chọn tiếp khóa/chỉnh sửa tập có thể khiến phân phối trạng thái sống bị **thiên lệch theo random đã lộ**. Vì vậy chứng minh cho tập khóa cố định độc lập với random không tự bảo đảm hiệu năng trước mọi **adaptive adversary**.

### 13.4. Seed, tie-breaker và chống tấn công độ phức tạp

`random.Random(seed)` phù hợp cho **mô phỏng và test tái lập**, nhưng không phải nguồn random mật mã. Cặp priority `(random_128_bits, serial)` giải quyết tie về mặt so sánh, không loại bỏ trạng thái xấu.

Nếu hệ thống cần worst-case O(log n) cho mỗi thao tác, hãy cân nhắc AVL/red-black tree hoặc cơ chế fallback có chứng minh cả chi phí chuyển đổi; chỉ “đổi seed rồi thử lại” không tự có chặn worst-case hữu hạn nếu không giới hạn số lần thử.

## 14. C: quay trái/phải và cập nhật size một cách an toàn

Ví dụ C11 này minh họa thao tác **đổi con trỏ** và cập nhật metadata `size`. Các node được khai báo **trên stack** trong `main`, không được `free`. Khi triển khai treap cấp phát động bằng `malloc`, cần quản lý ownership và hủy node riêng.

```c
#include <assert.h>
#include <stddef.h>
#include <stdint.h>

typedef struct Node {
    int key;
    uint64_t priority;
    size_t size;
    struct Node *left;
    struct Node *right;
} Node;

static size_t node_size(const Node *node) {
    return node == NULL ? 0u : node->size;
}

static void pull(Node *node) {
    assert(node != NULL);
    node->size = 1u + node_size(node->left) + node_size(node->right);
}

static Node *rotate_right(Node *y) {
    assert(y != NULL && y->left != NULL);

    Node *x = y->left;
    y->left = x->right;
    x->right = y;

    pull(y); /* Cập nhật con dưới trước. */
    pull(x);
    return x;
}

static Node *rotate_left(Node *y) {
    assert(y != NULL && y->right != NULL);

    Node *x = y->right;
    y->right = x->left;
    x->left = y;

    pull(y);
    pull(x);
    return x;
}

int main(void) {
    /* Ban đầu chỉ cạnh 30 -> 20 sai min-heap. */
    Node n25 = { .key=25, .priority=80, .size=1 };
    Node n20 = {
        .key=20, .priority=10, .size=2, .right=&n25
    };
    Node n30 = {
        .key=30, .priority=70, .size=3, .left=&n20
    };

    Node *root = rotate_right(&n30);

    assert(root == &n20);
    assert(root->right == &n30);
    assert(n30.left == &n25);
    assert(n30.size == 2 && n20.size == 3);

    /* Cả BST và min-heap đều đúng sau quay phải. */
    assert(root->priority < n30.priority);
    assert(n30.priority < n25.priority);

    /* Quay ngược để kiểm tra liên kết của primitive quay.
       Trạng thái sau quay ngược KHÔNG còn là treap hợp lệ. */
    Node *old_root = rotate_left(root);
    assert(old_root == &n30);
    assert(n30.left == &n20);
    assert(n20.right == &n25);
    assert(n30.size == 3 && n20.size == 2);

    return 0;
}
```

### 14.1. Vì sao quay ngược ở cuối không được dùng làm treap?

Sau `rotate_right`, gốc 20 có priority 10, còn node 30 priority 70 và node 25 priority 80; các cạnh đều thỏa heap. Khi quay trái tại 20 để **minh họa cấu trúc con trỏ**, gốc trở thành 30(priority 70) với con trái 20(priority 10). Bất biến heap **bị vi phạm lại**.

Phép quay **luôn giữ BST nếu đầu vào có BST đúng**, nhưng chỉ giữ hoặc khôi phục min-heap khi được gọi với **điều kiện priority đúng**. Đây là lý do treap không được quay tùy ý.

### 14.2. Quy tắc cập nhật metadata

Sau quay phải:

1. Gán `y.left=x.right`, `x.right=y`.
2. Gọi `pull(y)` vì y đã thành node ở dưới.
3. Gọi `pull(x)` vì size của x phụ thuộc vào size của y vừa đổi.

Nếu gọi `pull(x)` quá sớm, `size` có thể sai, khiến `rank/select` trả kết quả không đúng dù tìm theo key vẫn ổn.

### 14.3. Gỡ node cấp phát động trong C

Khi xóa node target:

1. Lưu `left=target->left` và `right=target->right` **trước khi free**.
2. `replacement=merge(left,right)`, giữ nguyên các node thuộc hai cây con.
3. Gắn replacement vào vị trí root/cha cũ.
4. Hủy payload riêng của target theo hợp đồng.
5. `free(target)` đúng **một lần**, không free các node đã được merge lại.

Nếu iterator hoặc thread khác giữ `Node*` tới target, cần iterator invalidation/memory reclamation phù hợp. Con trỏ trong **cây mới** đúng không có nghĩa những alias bên ngoài đều an toàn.


## 15. Kiểm thử: không chỉ kiểm tra inorder

Một treap có thể trả đúng `contains` nhưng vẫn sai heap, sai `size` hoặc giữ một node ở hai đường khác nhau. Vì vậy cần **validator độc lập với truy vấn**:

1. Khóa tăng nghiêm ngặt theo BST ở mọi cây con.
2. Mỗi cạnh có `priority(parent)<priority(child)` theo tuple.
3. Mỗi node xuất hiện **đúng một lần theo identity**, không có chu trình.
4. `size(node)=1+size(left)+size(right)`.
5. Inorder bằng đúng `sorted(set_keys)`.
6. `rank` và `select` khớp thứ tự thực.
7. Các thao tác chèn trùng/xóa vắng không làm đổi tập logic.

### 15.1. Đối chiếu nhiều chuỗi cập nhật với `set` Python

Đây là đoạn test **tiếp nối mã `TreapSet` ở Mục 10**:

```python
import random


def test_against_set(seed: int) -> None:
    # Tách RNG tạo workload khỏi RNG bốc priority của treap.
    workload = random.Random(100000 + seed)
    tree = TreapSet(seed=seed)
    expected: set[int] = set()

    for step in range(400):
        key = workload.randrange(-90, 91)
        action = workload.randrange(3)

        if action == 0:  # Insert
            was_new = key not in expected
            assert tree.insert(key) == was_new
            expected.add(key)

        elif action == 1:  # Discard
            existed = key in expected
            assert tree.discard(key) == existed
            expected.discard(key)

        else:  # Contains
            assert tree.contains(key) == (key in expected)

        tree.assert_valid()
        ordered = sorted(expected)

        assert len(tree) == len(expected)
        assert list(tree.keys()) == ordered

        if step % 17 == 0:
            for probe in (-100, -25, 0, 25, 100):
                smaller = [x for x in ordered if x < probe]
                ge = [x for x in ordered if x >= probe]

                assert tree.rank(probe) == len(smaller)
                assert tree.predecessor(probe) == (
                    smaller[-1] if smaller else None
                )
                assert tree.lower_bound(probe) == (
                    ge[0] if ge else None
                )

            for index, value in enumerate(ordered):
                assert tree.select(index) == value

            assert list(tree.range_keys(-25, 25)) == [
                x for x in ordered if -25 <= x < 25
            ]


for seed in range(12):
    test_against_set(seed)
```

Test này giúp tìm lỗi khi chèn/xóa nhiều lần làm `size` không khớp, quên cập nhật cây con sau merge hoặc làm sai biên của split. Nó **không chứng minh expected O(log n)**; tính đúng và chi phí là hai loại kiểm định khác nhau.

### 15.2. Thử đầu vào có thứ tự tăng, giảm, xen kẽ

```python
def test_orderings() -> None:
    sorted_keys = list(range(-50, 50))
    orderings = [
        sorted_keys,
        list(reversed(sorted_keys)),
        sorted_keys[::2] + sorted_keys[1::2],
    ]

    for index, order in enumerate(orderings):
        tree = TreapSet(seed=20 + index)

        for key in order:
            assert tree.insert(key)

        tree.assert_valid()
        assert list(tree.keys()) == sorted_keys

        for key in reversed(order):
            assert tree.discard(key)

        tree.assert_valid()
        assert len(tree) == 0
        assert list(tree.keys()) == []


test_orderings()
```

Một BST không cân bằng thường suy biến khi chèn khóa tăng dần. Treap random **vẫn đúng với mọi thứ tự**, và trong mô hình priority độc lập, các kết quả expected không yêu cầu thứ tự input được shuffle.

### 15.3. Trường hợp khóa trùng, khóa vắng, biên

```python
tree = TreapSet(seed=7)

assert tree.lower_bound(0) is None
assert tree.predecessor(0) is None
assert tree.rank(0) == 0

for key in (0, -10, 10):
    assert tree.insert(key)

assert not tree.insert(0)
assert len(tree) == 3
assert not tree.discard(999)
assert len(tree) == 3

assert tree.lower_bound(-100) == -10
assert tree.lower_bound(0) == 0
assert tree.lower_bound(1) == 10
assert tree.lower_bound(11) is None

assert tree.predecessor(-10) is None
assert tree.predecessor(0) == -10
assert tree.predecessor(10) == 0
assert tree.predecessor(11) == 10

assert tree.rank(-10) == 0
assert tree.rank(0) == 1
assert tree.rank(10) == 2
assert tree.rank(11) == 3

assert list(tree.range_keys(-10, 10)) == [-10, 0]
assert list(tree.range_keys(10, 10)) == []
tree.assert_valid()

try:
    tree.select(3)
    raise AssertionError("select phải báo lỗi ngoài phạm vi")
except IndexError:
    pass
```

Ở đây `select` có quy ước **0-based**; với 3 khóa, chỉ số hợp lệ là 0,1,2. Nếu kiểm thử lỗi IndexError bằng một framework, nên dùng `pytest.raises(IndexError)` hoặc cờ báo minh bạch, không bắt mọi exception một cách lẫn lộn.

### 15.4. Dựng một treap đường thẳng để thấy worst-case

Một **cây đường thẳng** với ưu tiên tăng cùng key là hợp lệ. Ta dựng trực tiếp các node cho một test có chủ đích:

```python
def build_right_chain(n: int) -> TreapSet:
    tree = TreapSet(seed=0)
    root: Node | None = None

    # Dựng từ khóa lớn về nhỏ để gắn con phải
    # và cập nhật size đúng trên mỗi bước.
    for key in range(n - 1, -1, -1):
        root = Node(key, (key, key), right=root)
        pull(root)

    tree._root = root  # Chỉ dành cho test cấu trúc nội bộ.
    return tree


chain = build_right_chain(80)
chain.assert_valid()

assert len(chain) == 80
assert list(chain.keys()) == list(range(80))
assert chain.contains(79)
assert chain.rank(80) == 80
assert chain.select(79) == 79

# Chiều cao theo số node đúng bằng 80.
depth = 0
current = chain._root
while current is not None:
    depth += 1
    current = current.right

assert depth == 80
```

Vì các priority tăng theo key, min-heap bắt buộc gốc nhỏ nhất và mỗi node chỉ có con phải. Test n=80 để validator đệ quy vẫn nằm trong mức an toàn thông thường; không cố ý dựng n quá lớn rồi nhầm `RecursionError` thành lỗi lập trình của invariant.

**Không** sửa `tree._root` trực tiếp trong ứng dụng. Đoạn này chỉ minh họa rằng worst-case Θ(n) tồn tại **trong tập trạng thái hợp lệ**.

### 15.5. Kiểm thử validator bắt được lỗi ở mức cấu trúc

Có thể thử trong môi trường cô lập: tạo một cây có đúng thứ tự khóa nhưng sai heap, ví dụ root priority 50 và con trái priority 10. Validator `assert_valid` phải từ chối.

```python
bad = TreapSet()
bad._root = Node(
    key=30,
    priority=(50, 0),
    left=Node(key=20, priority=(10, 1)),
)
pull(bad._root)

detected = False
try:
    bad.assert_valid()
except AssertionError:
    detected = True

assert detected, "Cây sai heap phải bị phát hiện"
```

Cách dùng cờ `detected` tránh lỗi test vô tình bắt chính `AssertionError` mà nó tự `raise` sau khi validator không phát hiện gì. Cũng cần nhớ `assert` có thể bị tắt bởi `python -O`; một validator cần dùng trong production phải kiểm tra và ném exception tường minh.

## 16. Quản lý vòng đời, ngoại lệ và đồng thời

Các thao tác treap nhìn đơn giản khi chạy **tuần tự**, nhưng có nhiều vấn đề riêng nếu cần thư viện sản phẩm.

### 16.1. `split/merge` tại chỗ không phải thao tác bất biến

Trong bản code:

```text
(A, B) = split(T, k)
```

các liên kết bên trong T **đã bị thay đổi** để trả hai gốc A và B. Không được tiếp tục dùng một alias cũ tới root như thể nó vẫn đại diện toàn bộ T.

Nếu hai owner cùng chia sẻ node và một owner gọi split, owner còn lại có thể thấy cấu trúc bị thay đổi. Muốn **persistent treap**, phải dùng path-copying hoặc node bất biến để các phiên bản lịch sử không bị ảnh hưởng.

### 16.2. Ngoại lệ giữa các phép đổi con trỏ

Trong chương trình tuần tự, `merge` và `split` thực hiện nhiều phép gán trên đường đệ quy. Nếu Python gặp `RecursionError`, bộ nhớ hết, comparator ném ngoại lệ hoặc thao tác bị ngắt giữa chừng, một phần liên kết có thể đã được sửa.

Bản học thuật không hứa **strong exception guarantee** cho mọi lỗi. Một API yêu cầu “hoặc hoàn tất hoặc cây ban đầu nguyên vẹn” cần chiến lược transaction/rollback, node bất biến/path-copy hoặc nguyên tắc thiết kế riêng.

### 16.3. Iterator invalidation

Nếu một iterator inorder đang giữ stack các node, phép quay hoặc xóa có thể đổi đường liên kết mà iterator đang dựa vào. Trong Python, object bị gỡ có thể còn sống vì iterator giữ tham chiếu mạnh, nhưng không còn thuộc set hiện tại.

Trong C/C++, iterator giữ `Node*` tới node đã `free` có thể gây **use-after-free**. Thư viện phải định nghĩa iterator còn hợp lệ hay bị vô hiệu sau insert/remove, split/merge.

### 16.4. Chạy đồng thời cần cơ chế nhất quán riêng

Một phép quay thay nhiều con trỏ: `y.left`, `x.right`, root của cây con, và metadata. Nếu luồng khác đọc khi không có đồng bộ, nó có thể quan sát một cây đang ở trạng thái trung gian.

- Cách đơn giản: một **mutex** bảo vệ find/insert/delete/rank/select và cả thời gian duyệt nếu iterator cần trạng thái nhất quán.
- Có thể dùng **snapshot bất biến** để trình đọc không thấy các sửa đổi trực tiếp.
- Concurrent lock-free treap là **một thuật toán khác**, cần atomic operations, linearization point và memory reclamation; không thể chỉ đổi vài phép gán thành CAS là đủ.
- Chờ lock, GC và quản lý đời node có thể chi phối thời gian thực, không được bỏ qua khi chuyển từ O(log n) số bước sang latency.

### 16.5. Treap không phải heap ưu tiên tác vụ

Mặc dù root của treap có **priority nhỏ nhất** trong các node, mục tiêu chính của treap là **tìm theo key có thứ tự**. Một heap thông thường không có BST invariant theo key và không cung cấp `lower_bound(key)` như treap.

Nếu ứng dụng chỉ cần lấy task có priority cao nhất, một binary heap array có thể phù hợp hơn. Không nên chọn treap chỉ vì trong tên có chữ “heap”.

## 17. So sánh với các cấu trúc có thứ tự khác

| Cấu trúc | Tìm khóa | Chèn/xóa | Thứ tự khóa, truy vấn dải | Đặc điểm |
| --- | --- | --- | --- | --- |
| BST không cân bằng | O(h), worst O(n) | O(h), worst O(n) | Có, nhưng h có thể n | Hình dạng nhạy thứ tự chèn |
| AVL tree | O(log n) worst-case | O(log n) worst-case | Có | Bất biến chiều cao tất định |
| Red-black tree | O(log n) worst-case | O(log n) worst-case | Có | Bất biến màu/chiều cao đen |
| **Treap priority ngẫu nhiên** | O(log n) kỳ vọng | O(log n) kỳ vọng | Có, dễ split/merge | BST+heap, worst O(n) |
| Skip list | O(log n) kỳ vọng | O(log n) kỳ vọng | Có, duyệt tầng đáy | Nhiều liên kết theo tầng |
| Mảng sorted | O(log n) binary search | O(n) do dịch phần tử | Có, locality tốt | Thích hợp đọc nhiều |
| Hash table | O(1) kỳ vọng exact key với giả định phù hợp | O(1) kỳ vọng cơ bản | Không tự sorted | Collision/resize/seed |
| Binary heap array | Không có tìm key bất kỳ O(log n) theo mặc định | Push/pop theo priority O(log n) | Không tự sorted theo key | Ưu tiên lấy min/max |

**Khi cân nhắc treap:** workload thường xuyên chèn/xóa một set có thứ tự và cần `lower_bound`, rank/select hoặc split/merge theo các dải khóa. Treap có mã primitive gọn và expected hiệu năng tốt nếu nguồn random/đối thủ phù hợp.

**Khi cần worst-case cứng:** AVL/red-black thường phù hợp hơn, vì heap property theo random priority **không chặn chiều cao**.

**Khi cần locality và đọc nhiều:** mảng sorted hoặc cấu trúc theo block có thể nhanh và gọn hơn dù cùng bậc Big-O trên truy vấn.

### 17.1. Một cái nhìn về biến thể `implicit treap`

Một **implicit treap** thay key tường minh bằng **vị trí suy ra từ `subtree_size`**, hỗ trợ tách/ghép một dãy theo index. Khi đó thứ tự inorder là thứ tự phần tử dãy, chứ không phải thứ tự tăng của trường key.

- Split theo index thay vì key.
- Metadata size quyết định một phần tử nằm ở vị trí nào.
- Có thể bổ sung lazy flags cho thao tác dải, như đảo đoạn hoặc cộng dồn, nếu các bất biến cập nhật được chứng minh.

Đây là **biến thể khác** so với `TreapSet` trong bài. Không được dùng nguyên `split(root,key)` theo key rồi coi là split theo vị trí; cả điều kiện phân chia và thuật toán metadata cần được thay đổi.

### 17.2. Persistence cũng cần một mô hình ownership khác

Trong **persistent treap**, mỗi lần update có thể tạo một gốc phiên bản mới mà phiên bản cũ vẫn truy vấn được. Để làm vậy, không được sửa trực tiếp những node được chia sẻ giữa phiên bản cũ và mới.

Có thể path-copy các node trên đường cập nhật, cho chi phí tạo thêm O(log n) node **kỳ vọng** dưới mô hình random phù hợp, và lưu nhiều phiên bản bằng các gốc khác nhau. Tuy nhiên cần xét GC/reference counting và tổng bộ nhớ theo số phiên bản; không tự áp dụng bản `split/merge` mutating ở Mục 10 cho persistent API.


## 18. Những lỗi dễ mắc và cách chẩn đoán

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Lẫn `priority` với `key` khi tìm | Đi sai nhánh, bỏ sót khóa | Tìm chỉ dựa trên key; priority quyết định hình dạng |
| Dùng min-heap ở chèn nhưng max-heap ở merge | Phá invariant sau cập nhật | Chọn một quy ước heap nhất quán |
| Dùng `<=` thay `<` ở BST set | Cho phép khóa trùng không có chính sách | So sánh tăng nghiêm ngặt, xử lý duplicate trước |
| Không xử lý priority bằng nhau | Hình dạng phụ thuộc tie tùy ý; validator strict fail | Tie-breaker duy nhất hoặc rút lại mức |
| Chèn node mới mà không quay khi priority nhỏ hơn cha | BST đúng, heap sai | Quay trái/phải hoặc dùng split/merge |
| Quay mà không cập nhật root của cây con | Mất node hoặc giữ con trỏ gốc cũ | Hàm quay trả gốc mới, cha phải nhận kết quả |
| Chỉ kiểm tra hai node sau quay, quên cây con B | Heap có thể sai ở cạnh khác | Chỉ quay khi tiền điều kiện thích hợp, validator toàn cây |
| `split` dùng điều kiện khóa không nhất quán | Bị lẫn khóa bằng k giữa hai kết quả | Quy ước A: <k, B: ≥k và giữ thống nhất |
| Gọi `merge(A,B)` khi khoảng khóa giao nhau | BST sai dù priority có thể đúng | Chỉ merge nếu mọi key(A)<mọi key(B) |
| Chèn trùng sau khi đã split mà không phục hồi | Cấu trúc bị chia đôi hoặc có duplicate | Kiểm tra trước khi sửa liên kết |
| Xóa target nhưng không merge hai cây con | Mất một nhánh dữ liệu | Thay target bằng merge(left,right) |
| Cấp phát rồi sửa nửa cây, exception xảy ra | Cấu trúc có thể ở trạng thái dở | Thiết kế exception safety và rollback/path-copy |
| Không cập nhật `size` sau merge/rotate | `rank/select` sai, dù `contains` còn đúng | Gọi `pull` từ dưới lên |
| Dùng `max priority` làm gốc trong code min-heap | Sai heap invariant | So sánh `<` với min-heap |
| Tính `E[height]` bằng `max E[depth]` | Đổi kỳ vọng và cực đại sai | Phân tích tail/maximum riêng |
| Xem expected O(log n) là worst-case | Sai bảo đảm độ trễ | Nêu worst-case Θ(n), xét AVL/red-black nếu cần |
| Dùng PRNG seed công khai như nguồn bảo mật | Có thể dự đoán thứ tự ưu tiên | Đánh giá threat model, không nhầm RNG với worst-case |
| Recursive split/merge trên cây đường rất dài | `RecursionError` hoặc tràn stack | Bản lặp, giới hạn và fallback phù hợp |
| Dùng `split/merge` mutating trên shared nodes | Các phiên bản/owner ảnh hưởng lẫn nhau | Ownership riêng hoặc persistent path-copy |
| Duyệt cây trong khi update không có hợp đồng | Duyệt thiếu/lặp hoặc use-after-free | Iterator invalidation, snapshot hay lock |
| Đo max chiều cao qua vài seed rồi gọi worst-case | Sai kết luận thống kê | Phân biệt max quan sát và worst-case toán học |

### 18.1. Debug bằng cách in khóa và priority cùng nhau

Khi thấy truy vấn sai, in mỗi node dưới dạng `(key,priority,size)` và liên kết left/right. Chỉ in key dễ bỏ lỡ lỗi heap; chỉ in priority dễ bỏ lỡ lỗi BST.

Quy trình:

1. Kiểm tra inorder có tăng nghiêm ngặt không; so với `sorted(reference_set)`.
2. Kiểm tra mọi cạnh cha–con theo tuple priority.
3. So `size` với số node thực sự của mỗi cây con.
4. Nếu lỗi sau insert, in đường cập nhật và từng phép quay/split/merge.
5. Nếu lỗi sau erase, xác định target, hai cây con và gốc replacement.
6. Kiểm tra node identity không xuất hiện ở hai nhánh hoặc tạo chu trình.
7. Chỉ sau khi cấu trúc đúng mới đo đường tìm/độ cao, vì benchmark trên một cây hỏng không có ý nghĩa.

### 18.2. Các test bắt buộc trước khi dùng thật

- Treap rỗng và chỉ một node, rồi xóa về rỗng.
- Key âm, key 0, key rất lớn, target ngoài biên.
- Insert duplicate, discard khóa vắng, insert lại khóa đã xóa.
- Input đã tăng, đã giảm, xen kẽ và random.
- Priority rất tốt khiến node mới phải trở thành root.
- Priority rất kém khiến node mới thành lá.
- Split tại key nhỏ hơn min, bằng min, giữa hai khóa, lớn hơn max.
- Merge với một cây rỗng và với hai cây có khoảng khóa hợp lệ.
- Test phát hiện merge sai tiền đề: không gọi merge bừa hoặc có tiền kiểm ở wrapper.
- Xóa lá, xóa node một con, hai con và xóa root.
- Kiểm tra `rank`/`select` sau mọi kiểu rotate/merge.
- Kiểm tra exact-k và range query so với mô hình chuẩn.
- Test node identity và không có chu trình.
- Test phá bất biến cố ý để biết validator thật sự phát hiện.
- Kiểm thử nhiều seed, không chỉ một seed đã “đẹp”.
- Test cực đoan cây dài để lộ giới hạn đệ quy.
- Nếu có concurrency hoặc persistence, test riêng lịch sử truy cập và vòng đời node.

## 19. Bài tập có lời giải

### Bài 1. Hai trường trong node

Một node treap chứa `(key=30, priority=7)`. Trường nào dùng để quyết định đi trái khi tìm key=20 và trường nào dùng khi chọn gốc giữa hai node?

**Lời giải:** Đi trái vì `20<30` theo **key**; chọn gốc theo **priority** (với min-heap, priority nhỏ hơn gần root). Trộn hai quan hệ sẽ làm tìm sai hoặc phá heap.

### Bài 2. Chọn quy ước min-heap

Một treap dùng min-priority. Cha có priority 10, hai con có priority 20 và 40. Heap invariant đúng không? Nếu cha priority 50 thì sao?

**Lời giải:** Với cha 10, cả `10<20` và `10<40` nên đúng. Với cha 50, cả hai con có priority nhỏ hơn cha nên sai min-heap, dù thứ tự khóa có thể vẫn đúng.

### Bài 3. Inorder của treap

Một treap có khóa `10,25,20,40,30`. Nếu đúng BST theo key, inorder traversal là gì, bất kể priority?

**Lời giải:** `10,20,25,30,40`. Inorder do bất biến BST quyết định, không do heap priority.

### Bài 4. Phần tử nhỏ nhất theo key ở đâu?

Gốc treap mang key=30 nhưng priority=1 nhỏ nhất. Có được kết luận key=30 là khóa nhỏ nhất của tập không?

**Lời giải:** Không. Root có **priority nhỏ nhất**, không phải **key nhỏ nhất**. Key nhỏ nhất nằm ở node **ngoài cùng bên trái** theo đường BST, có thể là key=10.

### Bài 5. Root của Cartesian tree

Các cặp là `(10,50), (20,10), (30,30), (40,20)`, min-heap priority. Key nào bắt buộc là root?

**Lời giải:** Key=20 vì priority 10 nhỏ nhất toàn tập. Cây trái chỉ chứa key10; cây phải chứa key30,40 và sẽ lấy key40(priority20) làm root cây phải.

### Bài 6. Dựng đủ một treap nhỏ

Với cặp của Bài 5, vẽ cây treap hoàn chỉnh.

**Lời giải:**

```text
        (20,10)
       /       \
   (10,50)    (40,20)
              /
          (30,30)
```

BST đúng vì `10<20<30<40` theo inorder. Heap đúng vì `10<50`, `10<20` và `20<30` theo priority.

### Bài 7. Vì sao Cartesian tree duy nhất?

Với key và priority đều phân biệt, giải thích tại sao không có hai cây treap khác nhau trên cùng tập cặp.

**Lời giải:** Root bắt buộc là node có priority nhỏ nhất. Key của root buộc tất cả key nhỏ hơn ở cây trái, tất cả key lớn hơn ở cây phải. Lặp đệ quy trên hai tập con quyết định mỗi cây con duy nhất.

### Bài 8. Ưu tiên trùng nhau

Nếu hai node có cùng priority=5, câu “treap có hình dạng duy nhất” còn tự đúng không?

**Lời giải:** Không nếu không có quy tắc hòa. Cần một comparator tổng quát nhất quán như `(priority,serial)` hoặc rút lại priority trùng, rồi dùng cùng comparator khi quay/split/merge và validator.

### Bài 9. Quay phải và thứ tự key

Cây `y(key=30)` có con trái `x(key=20)`, và x có cây con phải gồm key25. Sau quay phải tại y, key25 nằm ở đâu?

**Lời giải:** Key25 trở thành cây con **trái của y(key30)**, còn x(key20) thành gốc cây con. Inorder vẫn `20,25,30`. Phép quay giữ thứ tự BST.

### Bài 10. Khi nào quay phải để sửa heap?

Trong treap min-priority, `root=(30,70)` có con trái `(20,10)`, các phần khác hợp lệ theo điều kiện quay. Nên quay hướng nào?

**Lời giải:** Quay **phải** tại 30 để đưa node 20(priority10) lên trên. Cần tiếp tục kiểm tra heap của những liên kết khác; không quay tùy ý khi tiền đề không thỏa.

### Bài 11. Khi nào quay trái để sửa heap?

Root `(20,40)` có con phải mới `(25,10)`. Nên dùng quay trái hay phải?

**Lời giải:** **Quay trái** tại 20 để đưa node25(priority10) lên. Key20 sẽ thành con trái của key25 và BST vẫn đúng.

### Bài 12. Hai lần quay trong một lần chèn

Treap có root `(30,30)`, con trái `(20,40)`, con phải `(50,50)`. Chèn `(25,10)` cần các phép quay nào?

**Lời giải:** Chèn 25 làm con phải của 20 theo BST. Vì priority10 tốt hơn 40, quay **trái tại 20**; node25 trở thành con trái của 30. Vì priority10 tốt hơn 30, quay **phải tại 30**; node25 thành root. Inorder vẫn `20,25,30,50`.

### Bài 13. Tiền đề của `split`

`SPLIT(T,30)` trong bài trả A và B theo quan hệ nào?

**Lời giải:** A chứa **mọi key <30**, B chứa **mọi key ≥30**. Key đúng bằng 30 thuộc **B**, không bị loại hoặc nhân bản. Hai kết quả giữ invariant của treap và dùng chung các node gốc được phân chia theo ownership tại chỗ.

### Bài 14. Split ở hai biên

Treap chứa khóa `10,20,30`. Kết quả `SPLIT(T,5)` và `SPLIT(T,100)` về tập khóa là gì?

**Lời giải:** Với k=5: A rỗng, B có `10,20,30`. Với k=100 (trên một treap nguyên vẹn riêng, không phải gọi liên tiếp trên T đã bị sửa): A có `10,20,30`, B rỗng.

### Bài 15. Trường hợp nhánh `root.key<k` của split

Nếu root.key=20 và k=30, root thuộc kết quả A hay B? Cần đệ quy vào con nào?

**Lời giải:** Root thuộc **A** vì 20<30. Cây trái của root chắc chắn thuộc A; chỉ **cây phải** có thể chứa cả key <30 và ≥30, nên split đệ quy vào root.right.

### Bài 16. Tiền đề của merge

`MERGE(A,B)` có hợp lệ khi A chứa `{10,50}` và B chứa `{20,30}` không?

**Lời giải:** Không. Điều kiện bắt buộc là **mọi key(A)<mọi key(B)**, nhưng 50>20. Merge kiểu treap không phải union hai tập tùy ý; gọi như vậy có thể phá BST.

### Bài 17. Chọn gốc khi merge

A là treap có root priority 15, B root priority 5, và mọi key của A đều nhỏ hơn mọi key của B. Gốc kết quả là root nào?

**Lời giải:** Gốc B(priority5), vì heap dùng ưu tiên nhỏ nhất. Cây trái mới của B được tính bằng `MERGE(A,B.left)`; cây phải B giữ nguyên.


### Bài 18. Merge với cây rỗng

Nếu `A` rỗng, `MERGE(A,B)` phải trả gì? Có cần cấp thêm node?

**Lời giải:** Trả ngay root B, không cấp thêm node dữ liệu. Tương tự `MERGE(A,NULL)` trả A. Đây là hai điều kiện dừng của merge.

### Bài 19. Chèn bằng split/merge

Treap có `{10,20,40,50}`, muốn thêm key30. Liệt kê đúng các tập khóa trung gian.

**Lời giải:** `SPLIT(root,30)` thành A=`{10,20}` và B=`{40,50}`. Tạo node mới chứa key30 với priority đã rút. `MERGE(A,node30)` cho tập `{10,20,30}`; merge tiếp với B cho `{10,20,30,40,50}`. Mỗi merge hợp lệ vì khoảng khóa không giao nhau.

### Bài 20. Chèn trùng khóa

Treap set đã chứa 30. Vì sao không nên tạo thêm node30 rồi gọi split/merge như bình thường?

**Lời giải:** Bất biến BST set yêu cầu key phân biệt và thứ tự nghiêm ngặt. Thêm node trùng có thể làm split/merge không còn đúng tiền đề. `insert(30)` nên trả False, không đổi tập và trong chính sách code bài **không tiêu thụ RNG**.

### Bài 21. Xóa node có hai con

Trong treap Mục 1, xóa root key30. Cây con nào được đem merge và key nào thành root mới?

**Lời giải:** Merge cây trái `{10,20,25}` với cây phải `{40,50}`. Root trái có priority30 tại key20, root phải có priority20 tại key50. Vì 20<30, root kết quả là **key50**, với con trái mới do `MERGE(A,B.left)`. Tập còn `10,20,25,40,50`.

### Bài 22. Vì sao xóa chỉ giảm size một?

Node bị xóa có hai con và nhiều node cháu. Metadata size của toàn cây giảm bao nhiêu?

**Lời giải:** Giảm **đúng 1** vì chỉ node target bị loại; các node trong hai cây con được **merge giữ lại**, không bị xóa. Một lỗi gỡ cả cây con sẽ làm size giảm sai và mất khóa.

### Bài 23. Xóa khóa không tồn tại

Treap set có `{10,20,30}`. Gọi `discard(99)`, hợp đồng code bài trả gì và kích thước thay đổi không?

**Lời giải:** Trả **False**; số node vẫn 3. Không tạo node, không thay đổi logic tập khóa và không tăng version trong code.

### Bài 24. Vì sao phải cập nhật `subtree_size`?

Treap có thứ tự đúng nhưng metadata size cây trái bị khai báo ít hơn thực tế 2 node. Những phép nào có thể sai?

**Lời giải:** `rank` và `select` dùng `size(left)` để đếm/bỏ qua cây con, nên có thể trả thứ hạng hoặc khóa sai. `contains` theo BST có thể vẫn đúng, vì không dùng metadata size. Cần `pull` đúng sau mọi phép đổi liên kết.

### Bài 25. Rank của khóa không có

Treap chứa khóa `[10,20,25,30,40,50]`. Tính `rank(26)` theo quy ước “số khóa nhỏ hơn k”.

**Lời giải:** Có ba khóa `10,20,25` nhỏ hơn 26, nên `rank(26)=3`. Không yêu cầu k phải tồn tại.

### Bài 26. Select đánh số từ 0

Với cùng dãy khóa, `select(0)`, `select(2)`, `select(5)` là gì? `select(6)` thì sao?

**Lời giải:** Lần lượt **10,25,50**. `select(6)` báo `IndexError` vì chỉ có sáu khóa và chỉ số hợp lệ là 0..5. Đổi sang quy ước 1-based sẽ thay toàn bộ công thức và test.

### Bài 27. Kỳ vọng độ sâu khóa giữa

Treap có n=5 khóa phân biệt, priority IID liên tục. Độ sâu kỳ vọng tính bằng cạnh của `x_3` là bao nhiêu?

**Lời giải:**

\[
E[D_3]=\mathcal H_3+\mathcal H_3-2
=2(1+1/2+1/3)-2
=\frac53.
\]

Kết quả là kỳ vọng trên các hoán vị priority, không phải độ sâu thực tế của một cây.

### Bài 28. Xác suất một khóa là tổ tiên

Trong bộ khóa tăng `x_1,\ldots,x_8`, xác suất `x_2` là tổ tiên của `x_6` bằng bao nhiêu dưới mô hình IID liên tục?

**Lời giải:** Đoạn từ x2 đến x6 có `6-2+1=5` node. `x_2` phải có priority nhỏ nhất trong đoạn ấy, nên xác suất bằng **1/5**.

### Bài 29. Tuyến tính kỳ vọng không cần độc lập giữa các tổ tiên

Khi cộng xác suất `x_j` là tổ tiên của `x_i` để tính expected depth, có phải các sự kiện “là tổ tiên” đều độc lập không?

**Lời giải:** Không cần. Công thức `E[\sum I_j]=\sum E[I_j]` **luôn đúng** cho biến chỉ báo hữu hạn, kể cả các sự kiện phụ thuộc. Giả định IID được dùng để tính từng xác suất `1/(|i-j|+1)`, không phải để cho phép cộng kỳ vọng.

### Bài 30. Độ sâu kỳ vọng có tự chặn expected height không?

Nếu `E[D_i]≤C\log n` cho mọi i, có thể viết `E[\max_iD_i]=\max_iE[D_i]` không?

**Lời giải:** Không. Cực đại và kỳ vọng không giao hoán nói chung. Expected height O(log n) của treap được chứng minh bằng **phân tích đuôi của số tổ tiên/kỷ lục**, rồi áp dụng union bound qua mọi node, không chỉ thay “max” vào kết quả cho từng khóa.

### Bài 31. Trường hợp xấu có xác suất dương

Cho n=5 key tăng và priority IID liên tục. Xác suất priority tăng hoàn toàn theo key là bao nhiêu, và hình dạng treap là gì?

**Lời giải:** Một thứ tự trong `5!=120` thứ tự tương đối, nên xác suất `1/120`. Treap trở thành **cây lệch phải** dài 5 node, vẫn đúng BST và min-heap; tìm khóa cuối mất Θ(n).

### Bài 32. Kỳ vọng không phải worst-case

Treap có expected search O(log n). Một thử nghiệm tạo cây đường dài cho thấy tìm mất n bước. Điều đó có phủ định tính đúng của thuật toán không?

**Lời giải:** Không. Một cây lệch thỏa cả hai bất biến vẫn trả đúng khóa; nó chỉ là một **kết quả ngẫu nhiên xấu về chi phí**. Định lý expected không hứa mọi seed nhanh; worst-case vẫn Θ(n).

### Bài 33. Priority bằng key

Một lập trình viên tối ưu bằng cách đặt `priority=key` với mọi key dương, thay vì bốc random. Kết quả hình dạng thế nào đối với min-treap?

**Lời giải:** Với các key tăng, priority cũng tăng; node key nhỏ nhất làm root, các node còn lại tạo đường lệch phải. Chiều cao Θ(n) **một cách tất định**. Chứng minh expected dựa trên priority IID không áp dụng.

### Bài 34. Chi phí bộ nhớ của treap

Nếu treap lưu n khóa, mỗi node có hai con trỏ, key, priority và subtree_size, bậc bộ nhớ theo n là gì? Nó có cần O(n log n) node vì chiều cao logarit không?

**Lời giải:** **O(n) node và O(n) bộ nhớ metadata**, vì mỗi khóa tương ứng một node với O(1) trường. Chiều cao logarit kỳ vọng không làm số node tăng; stack của thuật toán đệ quy có thể O(h), worst O(n).

### Bài 35. Chọn cấu trúc với giới hạn thời gian cứng

Một dịch vụ đòi mọi lần chèn và tìm theo khóa có **worst-case O(log n) phép so sánh**. Treap random thông thường có đáp ứng không?

**Lời giải:** Không. Treap có **O(log n) kỳ vọng**, nhưng worst Θ(n). Với yêu cầu worst-case, nên ưu tiên AVL/red-black tree chuẩn hoặc một cấu trúc/fallback có chặn đã chứng minh.

### Bài 36. Iterator sau khi xóa

Một iterator giữ đường đi qua node20 trong treap. Thread khác xóa node20. Có an toàn tiếp tục iterator không?

**Lời giải:** Không thể giả định. Trong Python, iterator có thể giữ tham chiếu tới node đã rời set; trong C/C++, nếu node bị free có thể gây use-after-free. Phải có khóa, snapshot, iterator invalidation và chính sách memory reclamation phù hợp.

### Bài 37. Vì sao không tự dùng `split` cho persistent treap?

Hai phiên bản treap chia sẻ node. Một phiên bản gọi `split` tại chỗ trên node chung. Phiên bản còn lại có đảm bảo không đổi không?

**Lời giải:** Không. Split/merge mutating sửa con trỏ của những node chung. Persistent treap cần node bất biến/path-copying để phiên bản cũ giữ nguyên cấu trúc, và có hợp đồng ownership/ref-count/GC.

### Bài 38. Implicit treap khác treap set ở đâu?

Một `implicit treap` dùng vị trí của phần tử trong inorder làm khóa ngầm. Có được dùng nguyên `split(root,key)` của treap set để tách sau phần tử thứ r không?

**Lời giải:** Không. Split theo **index** phải tính số node cây con trái để quyết định mỗi nhánh; split theo key chỉ so `node.key < k`. Cả hai đều tận dụng heap priority và subtree_size nhưng có **ngữ nghĩa và thuật toán chia khác nhau**.

### Bài 39. Phân biệt heap mảng với treap

Một ứng dụng chỉ cần lấy công việc có priority nhỏ nhất và thêm công việc mới, không cần truy vấn `lower_bound(key)`. Treap có bắt buộc là lựa chọn tốt nhất vì root chứa priority nhỏ nhất không?

**Lời giải:** Không. **Binary heap array** thường đơn giản và phù hợp hơn khi chỉ cần push/pop theo priority, đồng thời có locality tốt. Treap được chọn khi cần **duy trì thứ tự key**, tìm kiếm theo key, range hoặc split/merge.

### Bài 40. Kiểm tra hợp đồng một phép merge

Cho A={10,20,30}, B={40,50}. Hai cây đều là treap đúng, priority mỗi node phân biệt. Sau `MERGE(A,B)`, cần kiểm tra ít nhất bốn bất biến nào?

**Lời giải:** (1) Inorder có đầy đủ `10,20,30,40,50` đúng một lần. (2) BST tăng nghiêm ngặt ở mọi cây con. (3) Priority cha tốt hơn con theo min-heap. (4) `subtree_size` đúng tại mỗi node nếu có. Ngoài ra phải kiểm tra không có chu trình/node trùng identity và bản A/B cũ đã được coi là tiêu thụ bởi phép merge tại chỗ.

## 20. Tổng kết và checklist triển khai

**Treap = BST theo key + heap theo priority trên cùng một cây.** Với min-heap, gốc là node có priority nhỏ nhất; theo BST, mọi key của cây trái nhỏ hơn key gốc, mọi key của cây phải lớn hơn. Hai quan hệ này cùng với priority phân biệt quyết định hình dạng **Cartesian tree duy nhất**.

Những điều cần nhớ:

1. **Hai bất biến phải giữ đồng thời.** Tìm theo key như BST; priority điều khiển hình dạng.
2. **Quay trái/phải giữ inorder** và dùng để đưa node có priority tốt hơn lên, nhưng quay tùy ý không bảo đảm heap đúng.
3. **`split(root,k)`** trả hai treap chứa các khóa `<k` và `≥k`; chỉ thay đường liên kết, không tự sao chép toàn bộ node.
4. **`merge(A,B)`** chỉ hợp lệ khi **mọi key A nhỏ hơn mọi key B**; root kết quả được chọn theo priority tốt hơn.
5. **Chèn:** kiểm tra trùng khóa, bốc priority rồi chèn bằng quay hoặc `split+merge`.
6. **Xóa:** tìm target, thay nó bằng `merge(target.left,target.right)`, giữ nguyên node hai cây con và giảm size đúng 1.
7. **Thống kê thứ tự:** `size(node)=1+size(left)+size(right)` giúp `rank/select` đi theo một đường cây, O(h).
8. **Kỳ vọng:** với n khóa cố định và priority IID liên tục, độ sâu/chiều cao cùng các thao tác cốt lõi có **O(log n) kỳ vọng**, nhưng worst-case **Θ(n)**.
9. **Bộ nhớ:** n node, mỗi node O(1) metadata → **O(n)** bộ nhớ; đệ quy tốn O(h) stack, worst O(n).
10. **Triển khai thực tế:** xác định chính sách duplicate, tie-break priority, seed/RNG, exception safety, ownership, iterator và concurrency. Nếu cần worst-case cứng, dùng cấu trúc có bất biến cân bằng tất định.

### Checklist ngắn trước khi chốt một thao tác

| Câu hỏi | Cách xác minh |
| --- | --- |
| Các key vẫn sorted? | Inorder + kiểm tra khoảng key từng cây con |
| Parent priority có tốt hơn child? | Validator min-heap trên mọi cạnh |
| Có nhân bản/mất node? | So số lượng và tập node identity |
| `size` sau update đúng? | `pull` từ dưới lên, kiểm tra `rank/select` |
| `merge` có đúng tiền đề? | `max_key(A)<min_key(B)` hoặc chứng minh bằng nguồn chia |
| Random có đúng mô hình? | Priority được rút độc lập với key; tie-break rõ |
| API có an toàn khi thất bại? | Kiểm tra allocation, recursion, rollback/ownership |
| Bảo đảm được công bố là gì? | O(log n) **kỳ vọng**, worst O(n), không nói quá về deadline |

**Bài học quan trọng nhất:** treap sử dụng **ngẫu nhiên hóa ưu tiên** để tạo hình dạng BST thuận lợi **theo kỳ vọng**, không thay thế bất biến cân bằng cứng. Hiểu rõ **hai thứ tự**, **cách sửa liên kết** và **giả định xác suất** sẽ giúp bạn chọn treap đúng bài toán và tự kiểm tra một implementation thay vì chỉ tin vào ký hiệu O(log n).
