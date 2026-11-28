# Tách và hợp treap theo miền khóa

Khi lưu dữ liệu có **thứ tự khóa**, không phải lúc nào ta cũng muốn chèn hoặc xóa từng phần tử riêng lẻ. Một hệ thống chỉ mục có thể cần **tách toàn bộ khóa nhỏ hơn một ngưỡng**, **loại một đoạn khóa**, **chuyển một khoảng từ cây này sang cây khác** hoặc **nối hai tập có miền khóa không giao nhau**. Trên treap, hai phép biến đổi cơ bản **`split`** (tách) và **`merge`** (hợp có thứ tự) cho phép thực hiện những công việc đó bằng cách thay liên kết trên một số đường của cây, thay vì duyệt và xây lại toàn bộ dữ liệu.

Bài **“Tách và hợp treap theo miền khóa”** thuộc chương **Cấu trúc ngẫu nhiên** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Trong lộ trình nghiên cứu cấu trúc dữ liệu từ mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap tới đồ thị, ta tiếp tục dùng **bất biến, thao tác và chi phí thời gian/bộ nhớ** để lựa chọn cấu trúc phù hợp. Treap là ví dụ quan trọng vì kết hợp thứ tự của **BST theo khóa** với thứ tự của **heap theo độ ưu tiên**, cho phép tách/hợp rất gọn mà vẫn giữ truy cập logarit **theo kỳ vọng**.

**Mục tiêu sau bài học:**

- Diễn giải chính xác hợp đồng của `split_lt(root,k)`, `split_le(root,k)`, `split3(root,k)` và `merge_ordered(A,B)`.
- Trình bày **tiền điều kiện miền khóa** của merge, giải thích tại sao merge không phải là phép hợp hai tập bất kỳ.
- Mô phỏng từng bước con trỏ được thay ở cả hai nhánh đệ quy của split/merge; chứng minh giữ BST, min-heap và metadata.
- Dùng **hai lần split** để cô lập miền `[lo,hi)` và **một lần merge** để xóa cả miền.
- Phân biệt **cắt rời node** với **sao chép node**, cùng hệ quả về ownership, iterator, persistence và lỗi giữa chừng.
- Biết khi nào một truy vấn đếm/tổng trong khoảng chỉ cần `rank` hoặc prefix aggregate mà **không** nên split cây.
- Cài đặt mã Python 3.10+ tự chứa, kiểm thử theo `set` chuẩn, test các biên và kiểm tra heap/BST/size sau thao tác.
- Phân tích rõ expected O(log n), worst-case O(n), O(k) thu hồi k node và các giới hạn đối với đối thủ thích nghi.
- Vận dụng split/merge để kết hợp các dải khóa vào một treap, đồng thời phát hiện những trường hợp **không được ghép trực tiếp**.

## 1. Mô hình treap trong bài và các ký hiệu

Mỗi node lưu:

```text
Node:
    key:        khóa có thứ tự toàn phần
    priority:   ưu tiên nội bộ, chọn ngẫu nhiên
    left:       cây con trái hoặc NULL
    right:      cây con phải hoặc NULL
    size:       số node trong cây con (nếu bảo trì thống kê thứ tự)
```

Ta dùng **treap set**: một khóa xuất hiện **tối đa một lần**. Priority có thứ tự **min-heap**: priority nhỏ hơn phải ở phía trên. Một số tài liệu dùng max-heap, khi đó phải đảo mọi phép so priority trong thuật toán chứ không chỉ thay ký hiệu.

### 1.1. Hai bất biến độc lập

**BST theo khóa** tại node u:

\[
\forall x\in subtree(u.left):x.key<u.key,\qquad
\forall y\in subtree(u.right):u.key<y.key.
\]

**Min-heap theo priority** trên từng cạnh:

\[
u.priority<child.priority
\]

khi priority được làm **duy nhất** bằng cách dùng phân phối liên tục lý tưởng hoặc tie-breaker nhất quán.

**Size** của cây con:

\[
size(NULL)=0,\quad size(u)=1+size(u.left)+size(u.right).
\]

Mỗi node reachable phải xuất hiện đúng một lần, không có chu trình. Bất biến BST cho phép dùng **ngưỡng khóa** để biết phải giữ/cắt nhánh nào; bất biến heap quyết định **gốc** khi nối hai cây.

### 1.2. Ví dụ làm việc xuyên suốt

Các cặp `(key, priority)`:

```text
(10,80), (20,30), (25,60), (30,10), (40,70), (50,20)
```

Treap min-heap tương ứng:

```text
                       (30,10)
                       /     \
                  (20,30)   (50,20)
                  /    \      /
             (10,80) (25,60) (40,70)
```

Inorder của cây là:

```text
10, 20, 25, 30, 40, 50
```

Gốc có `priority=10` là nhỏ nhất, nhưng **không** mang khóa nhỏ nhất. Khi tìm khóa, ta chỉ dùng `key`; khi merge, ta dùng `priority` để quyết định node nào trở thành gốc của kết quả.

### 1.3. Tách theo miền khóa nghĩa là gì?

Một thao tác tách không thay đổi giá trị của key hay priority. Nó **phân phối lại toàn bộ node** của một cây thành hai hay ba cây **độc lập về đường liên kết**:

- Không tạo ra một node dữ liệu mới nếu dùng bản **mutating/in-place**.
- Không nhân bản key.
- Không bỏ mất node.
- Các cây trả về vẫn riêng rẽ đúng BST và min-heap.
- Gốc treap nguồn phải được coi là **đã tiêu thụ**, không còn dùng một alias cũ như gốc của toàn tập.

Đối với một treap sở hữu duy nhất, split/merge giống như **cắt và nối các đường liên kết**, không phải `list.filter` hay `copy` của toàn bộ node.

## 2. Đặc tả `split_lt(T,k)`: hai nửa `<k` và `≥k`

Ký hiệu:

\[
(L,R)=split\_lt(T,k).
\]

**Hậu điều kiện về tập khóa:**

\[
keys(L)=\{x\in keys(T):x<k\},
\]
\[
keys(R)=\{x\in keys(T):x\ge k\}.
\]

Mỗi node dữ liệu trong T phải nằm **đúng một** trong L hoặc R. Cả L và R là treap hợp lệ, không chia sẻ node trong **bản mutating** đã hoàn tất.

### 2.1. Ví dụ tách trước khóa 30

```text
T ban đầu:

                       (30,10)
                       /     \
                  (20,30)   (50,20)
                  /    \      /
             (10,80) (25,60) (40,70)

split_lt(T,30):

L (<30):                        R (>=30):

         (20,30)                           (30,10)
         /    \                                 \
    (10,80) (25,60)                           (50,20)
                                                /
                                            (40,70)
```

Các khóa:

```text
L: 10, 20, 25
R: 30, 40, 50
```

**Khóa bằng ngưỡng k luôn vào R** trong đặc tả `split_lt`. Đây là quyết định thiết kế cần thể hiện trong tên hàm hoặc tài liệu; nhầm `<` với `≤` sẽ làm sai cả chèn trùng và các khoảng nửa mở.

### 2.2. Khi k ở ngoài miền dữ liệu

Với T chứa `{10,20,25,30,40,50}`:

| k | L: key < k | R: key ≥ k |
| ---: | --- | --- |
| 0 | ∅ | 10,20,25,30,40,50 |
| 10 | ∅ | 10,20,25,30,40,50 |
| 26 | 10,20,25 | 30,40,50 |
| 30 | 10,20,25 | 30,40,50 |
| 51 | 10,20,25,30,40,50 | ∅ |

Với cây rỗng, kết quả là `(NULL,NULL)`. Trong implementation đúng, split không yêu cầu k tồn tại.

## 3. Thuật toán `split_lt` chỉ đi theo một đường BST

Pseudocode cho bản **sửa con trỏ tại chỗ**:

```text
SPLIT_LT(root, k) -> (L, R):
    if root == NULL:
        return (NULL, NULL)

    if root.key < k:
        (a, b) = SPLIT_LT(root.right, k)
        root.right = a
        pull(root)
        return (root, b)

    else:
        (a, b) = SPLIT_LT(root.left, k)
        root.left = b
        pull(root)
        return (a, root)
```

Trong đó `pull(root)` tính lại `size(root)` sau khi thay một liên kết con. Trường hợp cơ sở là cây rỗng, không cần tạo sentinel phụ.

### 3.1. Nhánh `root.key<k`: gốc thuộc nửa trái

Nếu `root.key<k`, **toàn bộ cây trái của root** cũng chứa key <k do BST. Chúng ta giữ nguyên cây trái. **Chỉ cây phải** có thể chứa cả key nhỏ hơn k lẫn key lớn hơn hoặc bằng k.

```text
Trước, root.key < k:

          root
          /  \
         A    B

SPLIT_LT(B,k) -> (Bsmall, Bbig)

Sau:
          root            Bbig
          /  \
         A   Bsmall

Kết quả: (root, Bbig)
```

Gắn `root.right=Bsmall` vẫn đúng BST vì mọi key trong Bsmall vốn lớn hơn root.key và nhỏ hơn k. Heap vẫn đúng vì root đã có priority tốt hơn tất cả node trong cây B ban đầu, mà Bsmall chỉ là tập con của B.

### 3.2. Nhánh `root.key≥k`: gốc thuộc nửa phải

Nếu `root.key≥k`, **toàn bộ cây phải** có key >root.key≥k nên thuộc R. Chỉ cây trái có thể bị tách:

```text
Trước, root.key >= k:

          root
          /  \
         A    B

SPLIT_LT(A,k) -> (Asmall, Abig)

Sau:
     Asmall     root
                /  \
              Abig   B

Kết quả: (Asmall, root)
```

Gắn `root.left=Abig` vẫn đúng BST, và root vẫn có priority nhỏ hơn mọi node còn nằm dưới nó.

### 3.3. Điều gì không xảy ra khi split?

- Không đi qua **cả hai nhánh con** ở mỗi mức.
- Không lặp qua toàn bộ node trong khoảng bị tách.
- Không tạo một `Node` mới cho mỗi khóa.
- Không thay key hoặc priority.
- Không được tiếp tục dùng root cũ như một cây chứa **tất cả** key sau khi đã tách.

Bản in-place chỉ sửa liên kết dọc **một đường**, nhưng những object node cũ vẫn giữ identity. Một iterator đã tạo trước split có thể đi theo liên kết không còn đại diện tập gốc.

## 4. Chứng minh tính đúng của split bằng quy nạp

### 4.1. Trường hợp cơ sở

Nếu T rỗng thì cả L và R rỗng; hai tập khóa đều đúng định nghĩa, BST và heap đúng hiển nhiên, tổng kích thước bằng 0.

### 4.2. Giả sử cây con nhỏ hơn đã đúng

Giả sử `SPLIT_LT` đúng với mọi cây có ít node hơn T. Xét root.

**Nếu `root.key<k`:** root và toàn bộ cây trái chắc chắn thuộc L. Theo giả thiết quy nạp, split cây phải trả `(a,b)` với a chứa key <k và b chứa key ≥k. Nối a dưới root tạo L; b trả làm R.

**Nếu `root.key≥k`:** root và toàn bộ cây phải chắc chắn thuộc R. Split cây trái thành `(a,b)`; a thuộc L, b nối dưới root để tạo R.

Trong cả hai nhánh, mọi node xuất hiện đúng một lần và BST được giữ. Bất biến min-heap được giữ vì các node còn lại dưới root đều nằm trong **cây con cũ của root**, vốn có priority lớn hơn priority root. `pull` khôi phục metadata size.

### 4.3. Hệ quả về số phần tử

Nếu `n=size(T)` trước split, thì:

\[
size(L)+size(R)=n.
\]

Nếu treap có metadata `size`, đây là một test cấu trúc quan trọng; nó **chưa đủ** để phát hiện mất/mượn nhầm node vì hai lỗi có thể bù nhau, nên còn cần so identity và tập khóa.

### 4.4. Độ phức tạp của split

Gọi h là chiều cao treap nguồn, tính theo **số node** trên đường dài nhất. Thuật toán đi xuống nhiều nhất một con mỗi bước:

- Thời gian: `O(h)`.
- Số ô liên kết được thay: `O(h)`.
- Stack đệ quy: `O(h)`.
- Cấp phát node mới: **0** với bản mutating.

Dưới mô hình treap random có priority độc lập, thứ tự khóa cố định và một cách chọn query không phụ thuộc vào random đã lộ, chiều cao kỳ vọng O(log n), nên split có chi phí **O(log n) kỳ vọng**. Nhưng một treap lệch có `h=n`, nên worst-case là `O(n)`.

## 5. `split_le` và `split3`: ranh giới bằng khóa nằm ở đâu?

Chỉ một ký tự so sánh có thể làm khác toàn bộ hợp đồng.

### 5.1. `split_le(T,k)`: `≤k` và `>k`

\[
(A,B)=split\_le(T,k)
\]

với:

\[
keys(A)=\{x:x\le k\},\qquad
keys(B)=\{x:x>k\}.
\]

Pseudocode:

```text
SPLIT_LE(root,k):
    if root == NULL:
        return (NULL,NULL)

    if root.key <= k:
        (a,b) = SPLIT_LE(root.right,k)
        root.right = a
        pull(root)
        return (root,b)

    else:
        (a,b) = SPLIT_LE(root.left,k)
        root.left = b
        pull(root)
        return (a,root)
```

Cấu trúc giống `split_lt`; chỉ khác quyết định **node bằng k thuộc bên nào**. Với T chứa `{10,20,30}` và k=20:

```text
split_lt(T,20): ( {10},    {20,30} )
split_le(T,20): ( {10,20}, {30}    )
```

### 5.2. Không tự dùng `k+1` để đổi `≤k` thành `<k+1`

Với khóa kiểu số nguyên **hữu hạn** trong C/C++, `k+1` có thể overflow ở giá trị lớn nhất; với khóa chuỗi hay tuple, phép cộng 1 thậm chí không tồn tại. Hãy viết `split_le` trực tiếp bằng comparator `<=` hoặc xây một comparator ranh giới phù hợp kiểu key.

### 5.3. `split3(T,k)`: tách riêng khóa đúng bằng k

Với set có key phân biệt, `split3` trả:

\[
(A,E,B),\qquad A=\{x:x<k\},\ E=\{x:x=k\},\ B=\{x:x>k\}.
\]

E rỗng hoặc chứa **một node**. Có thể thực hiện bằng hai phép:

```text
(A, GE) = SPLIT_LT(T,k)
(E, B)  = SPLIT_LE(GE,k)
```

Hoặc tối ưu bằng một lượt đi theo BST, khi gặp key k thì tách ngay hai cây con rồi cô lập node k. `split3` rất hữu ích cho chèn/xóa chính xác và phép `union` có loại khóa trùng.

### 5.4. Bảng chọn quy tắc ranh giới

| Mục tiêu | Ranh giới 1 | Ranh giới 2 |
| --- | --- | --- |
| Lấy khóa `<k` | `split_lt(k)` | Không cần |
| Lấy khóa `≤k` | `split_le(k)` | Không cần |
| Cô lập khóa `=k` | `split_lt(k)` | `split_le(k)` trên nửa ≥k |
| Cô lập `[lo,hi)` | `split_lt(lo)` | `split_lt(hi)` trên nửa ≥lo |
| Cô lập `(lo,hi]` | `split_le(lo)` | `split_le(hi)` trên nửa >lo |
| Cô lập `[lo,hi]` | `split_lt(lo)` | `split_le(hi)` trên nửa ≥lo |

**Tránh viết “tách khoảng từ lo tới hi” mà không chỉ rõ đóng/mở ở hai đầu.** Tranh chấp đúng bằng lo hoặc hi là nguồn lỗi off-by-one phổ biến.


## 6. Đặc tả `merge_ordered(A,B)`: ghép hai miền khóa đã có thứ tự

`merge_ordered` nhận **hai treap riêng rẽ** A và B, trả về một treap U chứa toàn bộ node, với tiền điều kiện:

\[
\boxed{
A=\varnothing\ \lor\ B=\varnothing\
\lor\max(keys(A))<\min(keys(B)).
}
\]

Nếu cả hai không rỗng, **mọi khóa trong A phải nhỏ hơn mọi khóa trong B**. Điều kiện này nghiêm ngặt vì bài dùng **set**, không cho khóa trùng.

**Hậu điều kiện:**

\[
keys(U)=keys(A)\cup keys(B),\quad
size(U)=size(A)+size(B).
\]

U giữ BST, min-heap và metadata size. Các gốc A/B cũ được coi là **đã tiêu thụ**; không tiếp tục dùng chúng như những tập độc lập nếu bản merge sửa tại chỗ.

### 6.1. Ví dụ merge hai nửa theo k=30

Sau `split_lt(T,30)` ở Mục 2:

```text
A:                         B:

       (20,30)                   (30,10)
       /    \                         \
   (10,80) (25,60)                   (50,20)
                                       /
                                   (40,70)
```

Gốc A có priority30, gốc B có priority10; min-heap yêu cầu **30(key), priority10** làm gốc của kết quả.

```text
merge_ordered(A,B):

                       (30,10)
                       /     \
                  (20,30)   (50,20)
                  /    \      /
             (10,80) (25,60) (40,70)
```

Không có node mới. Nối lại hai nửa có thể tái tạo cây ban đầu vì bộ cặp `(key,priority)` được giữ nguyên.

### 6.2. Phép merge KHÔNG phải union của hai tập tùy ý

Ví dụ:

```text
A có key {10, 50}
B có key {20, 40}
```

Hai tập khóa **đan xen**: `50>20`. Mặc dù từng cây có thể tự thỏa BST và heap, gọi `merge_ordered(A,B)` **sai tiền điều kiện**, có thể tạo một cây không còn đúng BST.

Muốn hợp hai tập bất kỳ, cần một thuật toán `union` chuyên biệt (trình bày sau), hoặc dùng thao tác chèn từng khóa kèm chính sách duplicate. Không được “merge thử rồi xem inorder có đúng không” trong production.

## 7. Thuật toán merge: chọn gốc theo priority tốt hơn

Pseudocode dùng min-heap:

```text
MERGE_ORDERED(A,B):
    # Precondition: all keys(A) < all keys(B).
    if A == NULL: return B
    if B == NULL: return A

    if A.priority < B.priority:
        A.right = MERGE_ORDERED(A.right,B)
        pull(A)
        return A

    else:
        B.left = MERGE_ORDERED(A,B.left)
        pull(B)
        return B
```

Không cần so từng key để quyết định nhánh trong lõi merge **vì tiền điều kiện đã bảo đảm thứ tự miền khóa**. Priority quyết định gốc nào được giữ ở trên.

### 7.1. Nhánh `A.priority<B.priority`

Gốc A có priority tốt hơn gốc B; nó bắt buộc là gốc của U khi priority các node phân biệt. A.left giữ nguyên, vì mọi key ở đó vẫn nhỏ hơn A.key.

Cây mới bên phải A phải chứa:

- A.right: khóa lớn hơn A.key nhưng vẫn thuộc miền A.
- Toàn bộ B: khóa lớn hơn mọi key thuộc A.

Vì thế ta nối:

\[
A.right=MERGE\_ORDERED(A.right,B).
\]

Tiền điều kiện merge đệ quy vẫn đúng: mọi key của A.right đều nhỏ hơn mọi key của B.

### 7.2. Nhánh `B.priority<A.priority`

Đối xứng, gốc B có priority tốt hơn và làm gốc kết quả. B.right giữ nguyên. Cây trái mới:

\[
B.left=MERGE\_ORDERED(A,B.left).
\]

Mọi key A đều nhỏ hơn mọi key B.left theo tiền điều kiện toàn cục, nên BST vẫn đúng.

### 7.3. Chứng minh tính đúng bằng quy nạp

Nếu một cây rỗng, trả cây kia đã hợp lệ. Với hai cây không rỗng, node có priority tốt nhất giữa **hai gốc** cũng là node có priority tốt nhất trong **toàn bộ hai cây** (vì mỗi cây con là min-heap).

Nó phải thành gốc của cây kết quả. Phần con còn lại được ghép đệ quy trên hai treap nhỏ hơn thỏa điều kiện thứ tự khóa. Kết quả đệ quy đúng BST và heap theo giả thiết quy nạp; các liên kết không bị động đến vẫn đúng. Cuối cùng `pull` khôi phục size.

Với priority duy nhất, treap kết quả là **Cartesian tree duy nhất** của toàn bộ các cặp dữ liệu. Vì vậy:

\[
merge\_ordered(split\_lt(T,k))=T
\]

theo **hình dạng cây**, nếu không thay các key/priority và không có lỗi giữa chừng. Phát biểu này nói về kết quả cấu trúc; một implementation mutating vẫn có thể đã làm mất hiệu lực iterator hoặc alias bên ngoài trong khi thực hiện.

### 7.4. Chi phí merge

Gọi `h_A,h_B` là chiều cao của hai treap nguồn. Mỗi mức đệ quy chỉ đi xuống **nhánh phải A** hoặc **nhánh trái B**:

\[
\boxed{T_{\rm merge}=O(h_A+h_B)}.
\]

- Stack đệ quy: `O(h_A+h_B)`.
- Số node cần cấp thêm: **0** với bản mutating.
- Worst-case hai cây lệch: `O(|A|+|B|)`.
- Expected O(log(|A|+|B|)) nếu hình dạng hai treap bắt nguồn từ priority ngẫu nhiên phù hợp trên các tập khóa cố định, không bị chọn thích nghi theo priority đã quan sát.

Không được bảo đảm O(log n) expected cho **mọi cặp cây tùy ý** do một đối thủ chủ ý chọn sau khi đã quan sát hình dạng.

## 8. Split rồi merge có làm thay thứ tự hay hình dạng không?

Một câu hỏi thực tế: dùng split để tạm lấy một miền rồi merge lại, treap có còn như trước không?

Nếu mọi key và priority đều phân biệt và node không bị sửa giá trị:

- Split bảo toàn **bộ cặp key–priority**.
- Merge hai miền theo đúng thứ tự bảo toàn cùng **bộ cặp**.
- Treap min-heap của một bộ cặp phân biệt là duy nhất.

Do đó sau khi merge lại theo cùng ranh giới, ta thu được **cùng Cartesian tree**, không chỉ cùng tập khóa.

### 8.1. Phân biệt “cùng hình dạng” và “không có side effect”

Dù root cuối cùng trỏ tới cùng node và các cạnh trở lại như cũ:

- Giữa hai thao tác, các con trỏ đã từng bị đổi.
- Iterator có thể đã bị đánh dấu invalid bởi version.
- Một luồng khác không được nhìn trạng thái giữa chừng.
- Nếu ném ngoại lệ khi đang split/merge, không chắc trạng thái đã trở lại.
- Một API cho phép **cấp nhiều owner tới cùng node** có thể tạo alias nguy hiểm.

Vì vậy “split rồi merge là identity về cấu trúc khi hoàn tất” **không đồng nghĩa** “an toàn để làm tùy ý giữa một lượt duyệt concurrent”.

### 8.2. Thử các trường hợp biên

```text
T = {10,20,30}

split_lt(T,10) -> ({}, {10,20,30})
merge          -> {10,20,30}

split_lt(T,25) -> ({10,20}, {30})
merge          -> {10,20,30}

split_lt(T,100)-> ({10,20,30}, {})
merge          -> {10,20,30}
```

Trong cả ba trường hợp, nếu các priority không đổi, hình dạng cuối xác định duy nhất, kể cả khi một bên rỗng.

## 9. Cô lập miền `[lo,hi)` bằng hai lần split

Đây là ứng dụng cơ bản nhất của split theo khóa.

Muốn tách toàn bộ node có:

\[
lo\le key<hi,
\]

ta làm:

```text
(L, GE)    = SPLIT_LT(root, lo)
(MID, R)   = SPLIT_LT(GE, hi)
```

Hậu điều kiện:

\[
\begin{array}{ll}
L: & key<lo,\\
MID: & lo\le key<hi,\\
R: & key\ge hi.
\end{array}
\]

### 9.1. Ví dụ cụ thể

Cho T có `{10,20,25,30,40,50}`, cô lập `[20,45)`:

```text
split_lt(T,20):
    L  = {10}
    GE = {20,25,30,40,50}

split_lt(GE,45):
    MID = {20,25,30,40}
    R   = {50}
```

Ba miền **không giao nhau**, phủ hết tập khóa. Ta có thể:

- Giữ MID như một treap riêng, rồi nối `merge_ordered(L,R)` để xóa khoảng khỏi T.
- Gắn MID trở lại: `merge_ordered(merge_ordered(L,MID),R)`.
- Thực hiện một biến đổi có quy tắc hợp lệ trên payload của MID, rồi ghép lại nếu các **key không đổi** và các metadata được cập nhật đúng.

### 9.2. Trường hợp `lo≥hi`

Miền nửa mở `[lo,hi)` là rỗng nếu `lo≥hi`. Một API nên **trả treap rỗng hoặc số phần tử 0**, không cần split hay sửa liên kết.

Nếu code cứ gọi hai split khi `lo>hi` mà không kiểm tra, các điều kiện ghép sau đó có thể không còn khớp ý nghĩa L/MID/R, dẫn tới lỗi miền khóa.

### 9.3. Điều kiện để ghép lại

Sau hai lần split đúng:

\[
\max(keys(L))<lo\le \min(keys(MID))
\]

nếu hai tập tương ứng không rỗng, và:

\[
\max(keys(MID))<hi\le\min(keys(R)).
\]

Vì vậy:

```text
MERGE_ORDERED(L, MID)
MERGE_ORDERED(result, R)
```

đều hợp lệ. Điều này chỉ đúng nếu các node trong MID **không bị sửa key thành giá trị ngoài miền** trước khi ghép.

## 10. Xóa hoặc trích xuất cả dải khóa

`extract_range(lo,hi)` có thể tách MID như phần trước, rồi:

\[
root_{\rm remaining}=merge\_ordered(L,R).
\]

Trả MID về bên gọi hoặc sở hữu hủy nó. Trên một treap đúng:

\[
keys(T_{\rm after})
=keys(T_{\rm before})\setminus [lo,hi),
\]

và MID chứa đúng các khóa bị loại.

### 10.1. Pseudocode trích xuất, không hủy node

```text
EXTRACT_RANGE(root,lo,hi):
    if lo >= hi:
        return (root, NULL)

    (L, GE) = SPLIT_LT(root, lo)
    (MID,R) = SPLIT_LT(GE, hi)

    remaining = MERGE_ORDERED(L,R)
    return (remaining,MID)
```

Vì kết quả MID là **một treap được sở hữu riêng**, không cần đi qua từng node của miền để xây treap mới.

### 10.2. Chi phí thời gian tách so với giải phóng

Gọi k là số node trong MID:

- **Số bước sửa liên kết cấu trúc**: hai split và một merge → O(h) theo các đường cây, **O(log n) kỳ vọng** dưới mô hình random phù hợp.
- **Số node thực sự được xử lý/hủy** nếu yêu cầu giải phóng toàn bộ MID: ít nhất **Ω(k)** việc thu hồi trong mô hình phải giải phóng từng node, thường O(k).
- Nếu trả MID cho bên gọi làm một treap riêng, không cần hủy hay đi qua k node lúc ấy.

**Không được nói “xóa k phần tử chỉ tốn O(log n) tổng thời gian”** nếu hàm còn gọi destructor từng payload, xóa dữ liệu ngoài hệ thống, hoặc thu hồi bộ nhớ k node ngay trong một lời gọi. Phải nêu rõ đơn vị đo: **pointer restructuring** khác **reclamation/payload cleanup**.

### 10.3. `erase_range` và bộ đếm số phần tử

Nếu `size` đúng, số node bị trích xuất bằng:

\[
k=size(MID).
\]

API có thể trả k, rồi giải phóng treap MID theo cơ chế ownership. Không cần duyệt MID để chỉ **đếm** node, dù cuối cùng có thể cần duyệt để **hủy**.

### 10.4. Khi MID có payload đặc biệt

Một node treap có thể chứa bản ghi có destructor, handle tới file hoặc tài nguyên mạng. Khi xóa dải:

- Trước khi hủy, tách ownership của các node ra khỏi treap chính.
- Không để tham chiếu từ root chính tới node đã giải phóng.
- Hủy tài nguyên theo thứ tự và hợp đồng đã xác định.
- Nếu xóa k bản ghi trong database có side effect, không được lấy phép ghép con trỏ O(log n) làm độ phức tạp cho toàn giao dịch nghiệp vụ.

## 11. Chuyển một miền khóa giữa hai treap

Giả sử muốn chuyển những khóa thuộc `[lo,hi)` từ treap SOURCE sang treap DEST, **không** tạo bản sao node.

Ta cần bảo đảm DEST **không chứa khóa trong khoảng đó** trước khi ghép. Nếu DEST có bất kỳ khóa nào thuộc `[lo,hi)`, quy tắc set sẽ bị vi phạm hoặc thứ tự miền không còn đúng.

### 11.1. Ví dụ chuyển khoảng

```text
SOURCE = {10, 20, 25, 30, 40, 50}
DEST   = {1, 5, 60, 80}

Chuyển [20,45):

SOURCE sau   = {10,50}
DEST sau     = {1,5,20,25,30,40,60,80}
```

DEST được chia thành:

```text
Dleft   = {1,5}          (<20)
Dmiddle = {}             ([20,45))
Dright  = {60,80}        (>=45)
```

Trích xuất MID từ SOURCE, rồi ghép theo thứ tự:

```text
DEST = merge_ordered(
           merge_ordered(Dleft, MID),
           Dright
       )
```

### 11.2. Quy trình có tiền kiểm

```text
TRANSFER_RANGE(SOURCE,DEST,lo,hi):
    if SOURCE == DEST:
        handle_by_contract
    if lo >= hi:
        return 0
    if DEST contains any key in [lo,hi):
        return ERROR_OVERLAPPING_KEYS

    (SOURCE, MID) = EXTRACT_RANGE(SOURCE,lo,hi)
    (DL, GE)      = SPLIT_LT(DEST,lo)
    (DM, DR)      = SPLIT_LT(GE,hi)
    assert DM is empty

    DEST = MERGE_ORDERED(MERGE_ORDERED(DL,MID),DR)
    return size(MID)
```

**Chú ý:** nếu code cần trả số node đã chuyển, lưu `size(MID)` trước khi merge; sau khi merge, cùng node MID có thể không còn là gốc của một cây độc lập, và `size(MID)` có thể đã thay đổi.

### 11.3. Vì sao tiền kiểm là cần thiết?

Với:

```text
SOURCE trích [20,45): {20,25,30,40}
DEST hiện có:          {1,25,60}
```

DEST đã có key25 trong khoảng. Không được ghép MID trực tiếp, vì sẽ tạo **hai node key25** trong set hoặc khiến một node nằm sai miền. Các phương án chính sách khác nhau:

- **Từ chối trước khi sửa** (đơn giản, rõ).
- **Gộp trùng theo một quy tắc payload** bằng thuật toán union phù hợp.
- **Ghi đè** bên DEST, với quy tắc xóa/hủy node cũ và sở hữu.
- **Sao chép** thay vì chuyển, nếu API thực sự yêu cầu hai tập độc lập.

Lựa chọn nào cũng cần nêu trong hợp đồng; không có “merge” mặc định tự giải quyết các tình huống này.

### 11.4. Atomicity khi thao tác nhiều cây

Ngay cả nếu hai split và merge đều đúng khi hoàn tất, một thao tác TRANSFER có thể xảy ra lỗi **giữa chừng**, khi SOURCE đã bị cắt mà DEST chưa được nối.

Nếu API đòi **all-or-nothing**, cần cơ chế transaction/rollback, hoặc xây phiên bản mới theo cơ chế persistent treap rồi công bố hai root cùng lúc dưới đồng bộ thích hợp. Mã học thuật ở bài này chỉ chứng minh tính đúng của các phép biến đổi **khi hoàn tất**, không tuyên bố strong exception guarantee mặc định.


## 12. Khi miền khóa xen kẽ: `union` khác `merge_ordered`

Với hai tập khóa A và B không bảo đảm thứ tự toàn bộ miền, phép **hợp tập** là:

\[
keys(U)=keys(A)\cup keys(B).
\]

Nếu `A={10,50}` và `B={20,40}`, **không** được gọi `merge_ordered(A,B)`; điều kiện mọi key A nhỏ hơn mọi key B là sai. `merge_ordered` là primitive chuyên biệt **nối hai dải đã sắp theo miền khóa**, không phải union bất kỳ.

### 12.1. Union đơn giản bằng chèn từng khóa

```text
for each key of B:
    A.insert(key)
```

Nếu A là set, insert xử lý duplicate. Nếu B phải giữ nguyên, tạo node mới bên A khi cần; nếu chuyển ownership của B, cần thuật toán khác.

Với `a=|A|`, `b=|B|`, có b lần chèn/tìm; theo mô hình treap random phù hợp, expected O(b log(a+b+1)) cho thao tác cộng thêm duyệt B. Không tự hứa chặn này trước adversary lựa chọn hình dạng theo priority đã nhìn thấy.

### 12.2. Union theo split3

Một cách chia-để-trị giữ node identity:

```text
UNION(A,B):
    if A == NULL: return B
    if B == NULL: return A

    if A.priority > B.priority:
        swap(A,B)  # Đưa root có priority tốt hơn lên A.

    (BL, BEQ, BR) = SPLIT3(B, A.key)

    A.left  = UNION(A.left, BL)
    A.right = UNION(A.right, BR)

    discard_duplicate_node_only(BEQ)
    pull(A)
    return A
```

Gốc A có priority nhỏ nhất trong cả hai cây, vì nó đã tốt hơn gốc B và mỗi cây con đều thỏa heap. Chia B theo A.key làm BL nhỏ hơn, BR lớn hơn, BEQ là node trùng nếu tồn tại. Ghép kết quả đệ quy vào trái/phải A giữ BST. Phần tử trùng bị loại theo chính sách **giữ node gốc A**.

**Quan trọng:** `discard_duplicate_node_only(BEQ)` chỉ hủy node trùng đã được tách khỏi các cây con. Không được hủy cả cây con đã được đưa vào BL/BR. Hai cây nguồn phải có **ownership rời nhau**; không chạy union mutating trên node đang chia sẻ giữa các phiên bản persistent. Phân tích độ phức tạp của union chuyên biệt cần chứng minh riêng về số lời gọi đệ quy và phân phối priority, không chỉ mượn kết luận của merge hai dải.

## 13. Truy vấn khoảng: khi nào không cần split?

Split hữu ích khi **biến đổi cấu trúc hoặc chuyển ownership**. Nếu chỉ muốn **đọc** kích thước hoặc tổng trong một khoảng, ta thường có lựa chọn rẻ hơn và không sửa liên kết.

### 13.1. `count_range(lo,hi)` bằng `rank`

Với `size` đúng, định nghĩa `rank(k)` là số khóa nhỏ hơn k. Với `lo<hi`:

\[
\boxed{count[lo,hi)=rank(hi)-rank(lo)}.
\]

T={10,20,25,30,40,50} cho `[20,45)`:

\[
rank(45)=5,\quad rank(20)=1,\quad count=4.
\]

Hai lượt `rank` đều O(h), expected O(log n). Không tách cây, không invalid iterator. Nếu lo≥hi thì số lượng bằng 0 theo hợp đồng.

### 13.2. `sum_range` với metadata tổng giá trị

Nếu node chứa `value` **khác key**, giữ:

\[
sum(u)=value(u)+sum(u.left)+sum(u.right).
\]

Duyệt để lấy tổng prefix `prefix_sum(k)` trên mọi node key<k:

```text
PREFIX_SUM(root,k):
    answer = 0
    current = root

    while current != NULL:
        if k <= current.key:
            current = current.left
        else:
            answer += sum(current.left) + current.value
            current = current.right

    return answer
```

Do đó:

\[
\boxed{sum[lo,hi)=prefix\_sum(hi)-prefix\_sum(lo)}.
\]

Chi phí O(h) mỗi lần prefix, **không sửa cây**. Đổi con trỏ trong chèn/xóa/split/merge phải cập nhật cả `size` và `sum` qua hàm pull.

### 13.3. Cập nhật payload bằng lazy tag sau hai split

Với key cố định, có thể cô lập MID và áp dụng một cập nhật đồng loạt cho **payload value**:

```text
(L,GE) = split_lt(root,lo)
(M,R)  = split_lt(GE,hi)

apply_lazy_add(M,delta)   # Chỉ sửa value và aggregate.
root = merge_ordered(merge_ordered(L,M),R)
```

Cách này chỉ đúng nếu implementation có:

- `apply(node,delta)`: cập nhật value, aggregate và lazy tag nhất quán.
- `push(node)`: đẩy tag xuống con trước khi tiếp cận/sửa liên kết.
- `pull(node)`: tính lại metadata khi con thay đổi.
- Quy tắc ghép tag tương thích với phép toán.

Không được gắn `lazy_add` nhưng không sửa `sum` rồi nghĩ kết quả vẫn đúng. Bài này tập trung vào primitive split/merge; lazy propagation là mở rộng đòi thiết kế và chứng minh riêng.

### 13.4. Đừng đổi key trong miền mà không chứng minh thứ tự

Nếu MID chứa {20,25}, L={10}, R={30,40}, rồi sửa key MID thành {35,40}:

- MID không còn đứng giữa L và R.
- Có key40 trùng R.
- `merge_ordered(MID,R)` sai tiền điều kiện.

Cập nhật **payload** mà giữ nguyên key thường an toàn về miền. Cập nhật **key** phải xử lý lại thứ tự BST và quy tắc duplicate; không thể ghép mù hai treap.

## 14. Rủi ro sở hữu, ngoại lệ và concurrency

### 14.1. Split/merge mutating là phép chuyển quyền sở hữu

Trong C/C++, sau:

```text
(L,R)=split_lt(T,k)
```

L/R sở hữu các node mới tách; T cũ **không** còn là tập đầy đủ. Nếu dùng alias root T để giải phóng mọi node, có thể gây double free hoặc mất dữ liệu. Trong Python, các object có thể còn sống do reference ngoài nhưng không còn thuộc set cũ.

Một mô hình ownership rõ là: **mỗi node có đúng một owner tree** sau mỗi thao tác hoàn tất. Không dùng hai root chia sẻ node mà lại gọi split/merge tại chỗ độc lập.

### 14.2. Lỗi giữa nhiều phép đổi con trỏ

Nếu làm:

```text
(L,GE) = split_lt(root,lo)
(M,R)  = split_lt(GE,hi)
root   = merge_ordered(L,R)
```

một exception trong lúc đi sâu hoặc sau split đầu có thể để lại các gốc đã sửa dở. Mã mutable đơn giản **không tự có strong exception guarantee**.

Để có all-or-nothing, cần transaction/rollback, hoặc **path-copying** tạo gốc mới trước rồi mới công bố root dưới đồng bộ phù hợp. Chú ý ngay cả cách persistent cần hợp đồng quản lý tài nguyên và lỗi cấp phát.

### 14.3. Đệ quy có thể vượt stack

Treap ngẫu nhiên có expected height O(log n), nhưng trạng thái hợp lệ dạng đường thẳng cao n vẫn tồn tại. Split/merge recursive tốn O(h) stack; Python có thể phát sinh `RecursionError`, C/C++ có thể tràn stack.

Nếu ứng dụng yêu cầu an toàn khi trạng thái xấu xảy ra, cân nhắc bản lặp với stack tường minh, chặn độ sâu và fallback được chứng minh, hoặc dùng cây cân bằng tất định. Không đơn giản nâng `recursionlimit` rồi coi đã có worst-case logarit.

### 14.4. Iterator invalidation và đọc đồng thời

Split/merge đổi các cạnh và gốc cây con. Iterator đang giữ stack có thể bỏ sót, lặp node hoặc thấy node chuyển sang cây khác. Một thread đọc có thể quan sát giai đoạn trung gian khi thread khác đang thay nhiều con trỏ.

Các lựa chọn:

- Lock quanh chuỗi biến đổi và các thao tác cần nhất quán.
- Snapshot hoặc persistent nodes cho reader.
- Fail-fast version cho generator tuần tự, **không** coi version là lock.
- Thiết kế concurrent chuyên biệt với atomic operations, linearization point và memory reclamation.

Đặc biệt, **chuyển dải giữa hai treap** cần bảo vệ **cả hai** root theo cùng hợp đồng atomicity.

## 15. Độ phức tạp, expected và worst-case

Đặt `n=|T|`, `a=|A|`, `b=|B|`, `k` là số node trong miền trích xuất; `h` là chiều cao cây.

| Thao tác | Số bước cấu trúc | Expected trong mô hình random phù hợp | Worst-case |
| --- | --- | --- | --- |
| `split_lt(T,key)` / `split_le` / `split3` | O(h) | O(log(n+1)) | O(n) |
| `merge_ordered(A,B)` | O(h_A+h_B) | O(log(a+b+1)) | O(a+b) |
| `extract_range(lo,hi)` | Hai split + một merge | O(log(n+1)) | O(n) |
| `erase_range`, có hủy k node | Cấu trúc + cleanup | O(log(n+1)+k) nếu cleanup tuyến tính | O(n+k) |
| `count_range` bằng rank | Hai đường tìm | O(log(n+1)) | O(n) |
| `sum_range` bằng prefix aggregate | Hai đường tìm | O(log(n+1)) | O(n) |
| Đọc/xuất k khóa trong khoảng | Tìm biên + đi qua k node | O(log(n+1)+k) | O(n+k) |
| Chuyển miền giữa hai cây | Một số split/merge + tiền kiểm | O(log(n_1+1)+log(n_2+1)) cấu trúc | O(n_1+n_2) |

Về bộ nhớ:

- n node dữ liệu, mỗi node có key/priority, hai con trỏ và metadata O(1): tổng **O(n)**.
- Bản split/merge mutating **không cần cấp node mới**, stack O(h), worst O(n).
- Tách MID k node thành một treap khác **không tạo k bản sao**; chỉ chuyển ownership.
- Nếu thu hồi từng node/payload, tính thêm công việc O(k).
- Bản persistent path-copy có thể cấp thêm O(h) node trên một đường cập nhật, expected O(log n), nhưng phải tính cả các phiên bản còn được giữ.

### 15.1. Giả định của bảo đảm kỳ vọng

Expected O(log n) thường dựa trên n khóa **đã cố định độc lập với priority**, priority IID liên tục (hoặc mô hình tương đương có chứng minh) và không có sự lựa chọn trạng thái **thích nghi theo random đã quan sát**. Một đối thủ có thể cố ý chỉ giữ các cây treap lệch, nên không được tự áp dụng kết quả expected của cây ngẫu nhiên ban đầu vào mọi tập sống đã bị chọn lọc.

### 15.2. Treap hợp lệ vẫn có worst-case tuyến tính

Với `key=priority` tăng từ 1 tới n:

```text
(1,1)
    \
    (2,2)
        \
        (3,3)
            \
              ...
               (n,n)
```

Cây này đúng BST và min-heap nhưng chiều cao h=n. Tách tại k sát cực phải có thể đi qua Θ(n) node. **Một trạng thái xấu hợp lệ** đã đủ bác bỏ phát biểu “split luôn O(log n) worst-case”.

### 15.3. Lợi ích thực dụng của primitive theo miền

Xóa từng khóa trong một khoảng k phần tử có thể cần k đường tìm; hai split và một merge chỉ cần **hằng số lần thao tác theo đường cây** để cắt ra toàn bộ MID. Hiệu quả đặc biệt rõ nếu muốn **chuyển hoặc giữ MID** mà không hủy từng node ngay.

Nếu phải hủy k payload vật lý, phần cleanup thường còn Θ(k). Vì vậy hãy phân biệt **chi phí tái nối treap** với **toàn bộ chi phí nghiệp vụ**.


## 16. Python 3.10+: cài đặt treap có `split`, `merge` và các thao tác miền

Chương trình bên dưới **tự chứa**, chỉ dùng thư viện chuẩn. Các key là `int`, unique như set. Hai primitive `split_lt`/`split_le` sửa liên kết tại chỗ; `merge_ordered` **chỉ được gọi khi thứ tự miền khóa đã được chứng minh**. Lớp `TreapSet` bọc primitive và giữ trách nhiệm ownership của các root.

API gồm:

- `insert/contains/discard`: quản lý từng khóa.
- `split_off(k)`: giữ mọi key <k trong object hiện tại, trả **một treap mới** chứa các key ≥k.
- `join_right(other)`: nối toàn bộ `other` vào bên phải treap hiện tại, **tiêu thụ other** sau khi kiểm tra miền khóa.
- `extract_range(lo,hi)`: lấy treap mới chứa `[lo,hi)`, bỏ miền này khỏi cây nguồn.
- `erase_range(lo,hi)`: loại cả miền, trả số khóa bị loại.
- `range_count(lo,hi)`: chỉ đọc bằng hai lần `rank`.
- `select`/`rank`/`keys`/`assert_valid`: truy vấn và kiểm thử.

### 16.1. Mã có thể đặt vào một tệp Python duy nhất

```python
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass
from collections.abc import Iterator


# Tie-break ID duy nhất giữa các node được tạo trong process.
# Random 128 bit quyết định gần như toàn bộ thứ tự ưu tiên.
_TIE_IDS = itertools.count()


@dataclass(eq=False, slots=True)
class Node:
    key: int
    priority: tuple[int, int]
    left: Node | None = None
    right: Node | None = None
    size: int = 1


def size_of(root: Node | None) -> int:
    return 0 if root is None else root.size


def pull(root: Node) -> None:
    root.size = 1 + size_of(root.left) + size_of(root.right)


def split_lt(
    root: Node | None, key: int
) -> tuple[Node | None, Node | None]:
    """(left: key<k, right: key>=k); sửa node tại chỗ."""
    if root is None:
        return None, None

    if root.key < key:
        a, b = split_lt(root.right, key)
        root.right = a
        pull(root)
        return root, b

    a, b = split_lt(root.left, key)
    root.left = b
    pull(root)
    return a, root


def split_le(
    root: Node | None, key: int
) -> tuple[Node | None, Node | None]:
    """(left: key<=k, right: key>k)."""
    if root is None:
        return None, None

    if root.key <= key:
        a, b = split_le(root.right, key)
        root.right = a
        pull(root)
        return root, b

    a, b = split_le(root.left, key)
    root.left = b
    pull(root)
    return a, root


def split3(
    root: Node | None, key: int
) -> tuple[Node | None, Node | None, Node | None]:
    """(<k, ==k, >k); giữa là None hoặc đúng một node."""
    if root is None:
        return None, None, None

    if root.key < key:
        a, equal, b = split3(root.right, key)
        root.right = a
        pull(root)
        return root, equal, b

    if root.key > key:
        a, equal, b = split3(root.left, key)
        root.left = b
        pull(root)
        return a, equal, root

    left, right = root.left, root.right
    root.left = None
    root.right = None
    root.size = 1
    return left, root, right


def merge_ordered(
    left: Node | None, right: Node | None
) -> Node | None:
    """PRECONDITION: mọi key(left) < mọi key(right).

    Đây là primitive nội bộ, KHÔNG tự kiểm tra tiền điều kiện.
    """
    if left is None:
        return right
    if right is None:
        return left

    if left.priority < right.priority:
        left.right = merge_ordered(left.right, right)
        pull(left)
        return left

    right.left = merge_ordered(left, right.left)
    pull(right)
    return right


def min_key(root: Node) -> int:
    while root.left is not None:
        root = root.left
    return root.key


def max_key(root: Node) -> int:
    while root.right is not None:
        root = root.right
    return root.key


class TreapSet:
    """Ordered set treap đơn luồng, có giao diện chuyển ownership."""

    def __init__(self, seed: int | None = None) -> None:
        self._root: Node | None = None
        self._rng = random.Random(seed)
        self._version = 0

    @staticmethod
    def _check_key(key: int) -> None:
        if type(key) is not int:
            raise TypeError("Key phải là int, không nhận bool")

    def _new_priority(self) -> tuple[int, int]:
        return (self._rng.getrandbits(128), next(_TIE_IDS))

    def __len__(self) -> int:
        return size_of(self._root)

    def contains(self, key: int) -> bool:
        self._check_key(key)
        node = self._root

        while node is not None:
            if key == node.key:
                return True
            node = node.left if key < node.key else node.right
        return False

    def rank(self, key: int) -> int:
        """Số key nhỏ hơn key (key có thể không tồn tại)."""
        self._check_key(key)
        node = self._root
        result = 0

        while node is not None:
            if key <= node.key:
                node = node.left
            else:
                result += 1 + size_of(node.left)
                node = node.right

        return result

    def select(self, index: int) -> int:
        """Index 0-based trong thứ tự tăng."""
        if type(index) is not int or not (0 <= index < len(self)):
            raise IndexError("select index ngoài phạm vi")

        node = self._root
        while node is not None:
            left_size = size_of(node.left)

            if index < left_size:
                node = node.left
            elif index == left_size:
                return node.key
            else:
                index -= left_size + 1
                node = node.right

        raise AssertionError("Metadata size hoặc BST sai")

    def insert(self, key: int) -> bool:
        """Chèn một key; duplicate không tiêu thụ RNG."""
        self._check_key(key)
        if self.contains(key):
            return False

        fresh = Node(key, self._new_priority())
        left, right = split_lt(self._root, key)

        # Cả hai merge đều hợp lệ về miền khóa.
        self._root = merge_ordered(
            merge_ordered(left, fresh), right
        )
        self._version += 1
        return True

    def discard(self, key: int) -> bool:
        """Xóa một key bằng split3 + merge hai miền."""
        self._check_key(key)
        left, equal, right = split3(self._root, key)

        self._root = merge_ordered(left, right)
        if equal is None:
            return False

        # equal đã rời cây và không giữ con trỏ tới node khác.
        self._version += 1
        return True

    def split_off(self, key: int) -> TreapSet:
        """Self giữ key<k; trả treap mới chứa key>=k."""
        self._check_key(key)
        left, right = split_lt(self._root, key)

        self._root = left
        out = TreapSet()
        out._root = right

        if right is not None:
            self._version += 1

        return out

    def join_right(self, other: TreapSet) -> int:
        """Chuyển mọi node từ other sang bên phải self.

        Điều kiện: mọi key(self)<mọi key(other).
        Khi thành công, other trở nên rỗng.
        """
        if self is other:
            raise ValueError("Không thể join một cây với chính nó")
        if other._root is None:
            return 0

        if self._root is not None:
            if max_key(self._root) >= min_key(other._root):
                raise ValueError("Miền khóa giao nhau hoặc sai thứ tự")

        count = len(other)
        self._root = merge_ordered(self._root, other._root)
        other._root = None

        self._version += 1
        other._version += 1
        return count

    def extract_range(self, lo: int, hi: int) -> TreapSet:
        """Tách [lo,hi) thành một treap có ownership riêng."""
        self._check_key(lo)
        self._check_key(hi)
        extracted = TreapSet()

        if lo >= hi:
            return extracted

        left, ge_lo = split_lt(self._root, lo)
        middle, right = split_lt(ge_lo, hi)
        self._root = merge_ordered(left, right)
        extracted._root = middle

        if middle is not None:
            self._version += 1

        return extracted

    def erase_range(self, lo: int, hi: int) -> int:
        """Bỏ [lo,hi), trả số key; cleanup do Python GC xử lý."""
        removed = self.extract_range(lo, hi)
        count = len(removed)
        # Khi removed ra khỏi scope, có thể có công việc thu hồi
        # O(count); không tính nó vào số bước split/merge.
        return count

    def range_count(self, lo: int, hi: int) -> int:
        """Chỉ đọc, không sửa các liên kết."""
        self._check_key(lo)
        self._check_key(hi)
        if lo >= hi:
            return 0
        return self.rank(hi) - self.rank(lo)

    def keys(self) -> Iterator[int]:
        """Generator inorder; best-effort fail-fast trong tuần tự."""
        expected_version = self._version
        stack: list[Node] = []
        node = self._root

        while node is not None or stack:
            if self._version != expected_version:
                raise RuntimeError("Treap bị thay đổi khi duyệt")

            while node is not None:
                stack.append(node)
                node = node.left

            node = stack.pop()
            yield node.key
            node = node.right

        if self._version != expected_version:
            raise RuntimeError("Treap bị thay đổi khi duyệt")

    def height(self) -> int:
        """Chiều cao theo số node, đo lặp không đệ quy."""
        if self._root is None:
            return 0

        answer = 0
        stack: list[tuple[Node, int]] = [(self._root, 1)]

        while stack:
            node, depth = stack.pop()
            answer = max(answer, depth)

            if node.left is not None:
                stack.append((node.left, depth + 1))
            if node.right is not None:
                stack.append((node.right, depth + 1))

        return answer

    def assert_valid(self) -> None:
        """Validator test: BST, heap, size, node identity và cycle."""
        seen: set[Node] = set()
        priorities: set[tuple[int, int]] = set()

        def walk(
            node: Node | None,
            lower: int | None,
            upper: int | None,
            parent_prio: tuple[int, int] | None,
        ) -> int:
            if node is None:
                return 0

            assert node not in seen, "Cycle hoặc node xuất hiện hai lần"
            seen.add(node)
            assert type(node.key) is int
            assert lower is None or lower < node.key
            assert upper is None or node.key < upper
            assert parent_prio is None or parent_prio < node.priority

            assert node.priority not in priorities
            priorities.add(node.priority)

            lc = walk(node.left, lower, node.key, node.priority)
            rc = walk(node.right, node.key, upper, node.priority)

            expected_size = 1 + lc + rc
            assert node.size == expected_size, "Sai subtree_size"
            return expected_size

        count = walk(self._root, None, None, None)
        assert count == len(self)
        assert len(seen) == count


def demonstration() -> None:
    tree = TreapSet(seed=2026)
    for key in (30, 10, 50, 20, 25, 40):
        assert tree.insert(key)

    tree.assert_valid()
    assert list(tree.keys()) == [10, 20, 25, 30, 40, 50]
    assert tree.rank(30) == 3
    assert tree.select(2) == 25
    assert not tree.insert(20)

    right = tree.split_off(30)
    assert list(tree.keys()) == [10, 20, 25]
    assert list(right.keys()) == [30, 40, 50]
    tree.assert_valid()
    right.assert_valid()

    assert tree.join_right(right) == 3
    assert len(right) == 0
    assert list(tree.keys()) == [10, 20, 25, 30, 40, 50]

    middle = tree.extract_range(20, 45)
    assert list(middle.keys()) == [20, 25, 30, 40]
    assert list(tree.keys()) == [10, 50]
    assert tree.range_count(10, 51) == 2

    tail = tree.split_off(20)
    assert tree.join_right(middle) == 4
    assert tree.join_right(tail) == 1

    assert list(tree.keys()) == [10, 20, 25, 30, 40, 50]
    assert tree.discard(25)
    assert not tree.discard(25)
    assert tree.erase_range(20, 50) == 3

    assert list(tree.keys()) == [10, 50]
    tree.assert_valid()
    print("Split/merge TreapSet: OK")


if __name__ == "__main__":
    demonstration()
```

### 16.2. Một số hợp đồng không hiển nhiên của code

**Hai cây độc lập sau split:** `split_off` trả một object `TreapSet` mới sở hữu các node key≥k; object gốc chỉ giữ key<k. `join_right` chuyển toàn bộ node từ object `other` và đặt `other._root=None`, nhằm tránh hai owner cùng quản lý một cây.

**Nguồn priority:** mỗi `TreapSet` có PRNG riêng; tuple `(random_128_bit, global_tie_id)` tránh priority **trùng hoàn toàn** ngay cả khi join hai cây được tạo từ các instance khác nhau. Mô hình toán lý tưởng dùng priority IID liên tục; nguồn PRNG hữu hạn và tie-breaker của code là một **mô hình triển khai gần đúng**, không bảo mật.

**Kiểm tra tiền đề merge:** primitive `merge_ordered` là nội bộ, **không** tự kiểm tra biên khóa để tiết kiệm đường duyệt. `join_right` kiểm tra `max_key(self)<min_key(other)` trước khi gọi merge. Các hàm insert/split/extract có bằng chứng miền khóa từ chính cách split.

**Dùng generator trong lúc cập nhật:** `keys` chỉ kiểm tra phiên bản khi chạy; nó **không** cung cấp snapshot. `TreapSet` là ví dụ **đơn luồng**, không có khóa đồng bộ.

**Strong exception safety:** code thay liên kết trực tiếp qua recursion. Nếu `RecursionError` hay lỗi runtime xảy ra ở giữa, không có rollback tổng quát. Không dùng mã học thuật này như thư viện giao dịch quan trọng mà chưa thiết kế thêm cơ chế lỗi.

### 16.3. Vì sao `erase_range` có hai loại chi phí?

Hàm `erase_range` chỉ dùng `extract_range` để tách MID ra khỏi root rồi trả `len(MID)`. Việc **cắt liên kết** dựa trên một số đường BST, expected logarit. Khi MID hết được tham chiếu, Python có thể phải thu hồi từng node, và trong môi trường có destructor/payload thật, cleanup không tự biến thành O(log n).

Thay vì hứa “toàn bộ xóa k khóa là O(log n)”, hãy nói:

> **Tách và tái nối con trỏ:** O(log n) kỳ vọng. **Giải phóng k node và tài nguyên bên trong:** thường thêm O(k).

### 16.4. Khi n lớn và cây rất lệch

`height()` ở ví dụ dùng stack lặp để đo ngay cả khi cây cao; nhưng `split_lt`, `split_le`, `split3`, `merge_ordered` và validator `walk` dùng đệ quy. Treap lệch có thể ném `RecursionError`. Điều này không bác bỏ tính đúng của thuật toán toán học; nó cho thấy implementation cần một chính sách stack và xử lý exception khi đưa vào sản phẩm.


## 17. Kiểm thử tách/hợp, ranh giới và quyền sở hữu node

Một bài kiểm tra split/merge phải xác nhận **cả nội dung lẫn bất biến**. So kết quả với `sorted(set_keys)` chưa đủ nếu heap hoặc `subtree_size` đã bị sai. Trước và sau mỗi chuỗi thao tác, nên kiểm tra:

- Mọi key của mỗi treap tăng nghiêm ngặt theo inorder.
- Không có node lặp identity hoặc chu trình.
- Mọi cạnh cha–con thỏa min-heap theo priority.
- `size(u)=1+size(u.left)+size(u.right)`.
- Tập key của các nửa split đúng quy tắc ranh giới.
- Join sai tiền đề bị từ chối **trước khi thay đổi** hai root.
- Sau khi chuyển ownership, cây nguồn không còn giữ những node đã chuyển.

Các đoạn Python dưới đây **tiếp nối mã Mục 16**, chỉ dùng thư viện chuẩn. Chúng là ví dụ kiểm tra chức năng, **không phải bài đo benchmark throughput**.

### 17.1. Helper dựng một treap mới

```python
def make_tree(keys: list[int], seed: int = 2026) -> TreapSet:
    tree = TreapSet(seed=seed)
    for key in keys:
        assert tree.insert(key)

    tree.assert_valid()
    return tree
```

Vì primitive `split_lt`/`split_le` nhận gốc và **tiêu thụ cấu trúc**, không gọi chúng nhiều lần trên cùng gốc cũ nếu chưa rejoin hoặc dựng lại cây.

### 17.2. Phân biệt `split_lt` và `split_le` tại key tồn tại

```python
keys = [10, 20, 25, 30, 40, 50]

original = make_tree(keys)
left, right = split_lt(original._root, 30)
original._root = None  # Chuyển ownership cho hai kết quả.

a, b = TreapSet(), TreapSet()
a._root, b._root = left, right

assert list(a.keys()) == [10, 20, 25]
assert list(b.keys()) == [30, 40, 50]
a.assert_valid()
b.assert_valid()

# Chỉ primitive nội bộ; ghép lại và xóa gốc trung gian.
joined = TreapSet()
joined._root = merge_ordered(a._root, b._root)
a._root = None
b._root = None
joined.assert_valid()
assert list(joined.keys()) == keys

original2 = make_tree(keys)
le, gt = split_le(original2._root, 30)
original2._root = None

x, y = TreapSet(), TreapSet()
x._root, y._root = le, gt
assert list(x.keys()) == [10, 20, 25, 30]
assert list(y.keys()) == [40, 50]
x.assert_valid()
y.assert_valid()
```

Kết quả khác nhau **chính xác tại key=30**; một phép dùng `<30` và phép kia `≤30`. Các trường `_root` private chỉ được sửa trong **test primitive** nhằm mô phỏng chuyển ownership, không phải cách dùng API công khai.

### 17.3. Test `split3` với key có hoặc không tồn tại

```python
for target in (0, 20, 27, 50, 99):
    tree = make_tree([10, 20, 25, 30, 40, 50])
    left, equal, right = split3(tree._root, target)
    tree._root = None

    a, e, b = TreapSet(), TreapSet(), TreapSet()
    a._root, e._root, b._root = left, equal, right

    keys = [10, 20, 25, 30, 40, 50]
    assert list(a.keys()) == [x for x in keys if x < target]
    assert list(e.keys()) == [x for x in keys if x == target]
    assert list(b.keys()) == [x for x in keys if x > target]

    a.assert_valid()
    e.assert_valid()
    b.assert_valid()
```

E rỗng nếu key vắng; nếu key có thì E đúng một node, `size=1` và không còn liên kết con sang L/R.

### 17.4. Join sai tiền đề không làm thay đổi hai cây

```python
a = make_tree([10, 50])
b = make_tree([20, 40])

before_a = list(a.keys())
before_b = list(b.keys())

failed = False
try:
    a.join_right(b)
except ValueError:
    failed = True

assert failed
assert list(a.keys()) == before_a
assert list(b.keys()) == before_b
a.assert_valid()
b.assert_valid()
```

`join_right` thực hiện tiền kiểm bằng min/max key **trước** khi vào primitive merge. Vì vậy riêng lỗi tiền đề miền khóa bị phát hiện an toàn; điều này **không** đồng nghĩa strong exception guarantee cho mọi lỗi runtime trong recursion.

### 17.5. Đối chiếu hàng loạt split/join với `set`

```python
import random


def test_random_splits(seed: int) -> None:
    rng = random.Random(10000 + seed)
    keys = sorted(rng.sample(range(-250, 251), 120))
    expected = set(keys)
    tree = make_tree(keys, seed)

    for _ in range(100):
        cut = rng.randrange(-280, 281)
        right = tree.split_off(cut)

        assert list(tree.keys()) == sorted(x for x in expected if x < cut)
        assert list(right.keys()) == sorted(x for x in expected if x >= cut)
        tree.assert_valid()
        right.assert_valid()

        count_before = len(right)
        assert tree.join_right(right) == count_before
        assert len(right) == 0
        assert list(tree.keys()) == sorted(expected)
        tree.assert_valid()


for seed in range(8):
    test_random_splits(seed)
```

Ngưỡng có thể nằm ngoài min/max nên test bao phủ trường hợp một nửa rỗng. Cần lưu `count_before` **trước join**, vì sau join cây nguồn đã bị tiêu thụ và `len(right)=0`.

### 17.6. Test trích xuất, khôi phục và đếm khoảng

```python
def test_ranges(seed: int) -> None:
    rng = random.Random(20000 + seed)
    original = rng.sample(range(-80, 81), 75)
    tree = make_tree(original, seed)
    expected = set(original)

    for _ in range(60):
        lo = rng.randrange(-100, 101)
        hi = rng.randrange(-100, 101)

        wanted = {x for x in expected if lo <= x < hi}
        assert tree.range_count(lo, hi) == len(wanted)

        middle = tree.extract_range(lo, hi)
        middle_count = len(middle)
        assert middle_count == len(wanted)

        expected -= wanted
        assert set(tree.keys()) == expected
        assert set(middle.keys()) == wanted

        tree.assert_valid()
        middle.assert_valid()

        # Phục hồi cả MID qua các dải đã có thứ tự.
        if lo < hi:
            tail = tree.split_off(lo)
            tail_count = len(tail)

            assert tree.join_right(middle) == middle_count
            assert tree.join_right(tail) == tail_count

            expected |= wanted
            assert set(tree.keys()) == expected
            tree.assert_valid()


for seed in range(8):
    test_ranges(seed)
```

Khi `lo≥hi`, MID rỗng và cây gốc không thay đổi; không cần tách/ghép. Khi `lo<hi`, vì các khóa còn lại thuộc hai miền `key<lo` hoặc `key≥hi`, ghép lại `left + MID + right` hợp lệ ngay cả khi MID rỗng.

### 17.7. Xác minh split in-place không copy node

Có thể thu `id(node)` của mọi node, kiểm tra trước/sau split. `id` chỉ được dùng trong phạm vi test khi các object vẫn được tham chiếu; không lưu nó như ID vĩnh viễn.

```python
def collect_node_ids(root: Node | None) -> set[int]:
    result: set[int] = set()
    stack = [root]

    while stack:
        node = stack.pop()
        if node is None:
            continue

        assert id(node) not in result, "Cycle hoặc lặp node"
        result.add(id(node))
        stack.append(node.left)
        stack.append(node.right)

    return result


tree = make_tree([10, 20, 25, 30, 40, 50])
original_ids = collect_node_ids(tree._root)
right = tree.split_off(30)

left_ids = collect_node_ids(tree._root)
right_ids = collect_node_ids(right._root)

assert left_ids.isdisjoint(right_ids)
assert left_ids | right_ids == original_ids

tree.join_right(right)
assert collect_node_ids(tree._root) == original_ids
tree.assert_valid()
```

Nếu test chỉ so số lượng và tập key, một implementation có thể âm thầm tạo bản sao node mà vẫn cho kết quả logic đúng. Kiểm tra identity làm rõ đúng ý nghĩa **chuyển node không sao chép** của bản in-place.

### 17.8. Test chuyển cả miền sang một cây đích

Một hàm thao tác qua API công khai có thể từ chối miền trùng **trước khi sửa**. Để không mất số lượng đã chuyển, lưu `moved=len(middle)` **trước** khi gọi `join_right`, bởi sau đó object `middle` trở nên rỗng:

```python
def transfer_range_safe(
    src: TreapSet,
    dst: TreapSet,
    lo: int,
    hi: int,
) -> int:
    if src is dst:
        raise ValueError("Không chuyển giữa cùng một treap")
    if type(lo) is not int or type(hi) is not int:
        raise TypeError("Ranh giới phải là int")
    if lo >= hi:
        return 0
    if dst.range_count(lo, hi) != 0:
        raise ValueError("Destination đã có key trong miền")

    middle = src.extract_range(lo, hi)
    moved = len(middle)

    right = dst.split_off(lo)
    right_count = len(right)

    moved_actual = dst.join_right(middle)
    right_actual = dst.join_right(right)
    if moved_actual != moved or right_actual != right_count:
        raise AssertionError("Sai số lượng node chuyển ownership")
    return moved


src = make_tree([10, 20, 25, 30, 40, 50])
dst = make_tree([1, 5, 60, 80])
assert transfer_range_safe(src, dst, 20, 45) == 4

assert list(src.keys()) == [10, 50]
assert list(dst.keys()) == [1, 5, 20, 25, 30, 40, 60, 80]
src.assert_valid()
dst.assert_valid()
```

Hàm `transfer_range_safe` lưu `moved` và `right_count` trước khi hai cây nguồn của join bị tiêu thụ. Các lệnh `join_right` được thực thi **ngoài `assert`**, nên không biến mất khi chạy Python với tối ưu hóa `-O`.

**Giới hạn của bản hoàn chỉnh:** tiền kiểm ngăn lỗi overlap, nhưng một exception trong quá trình sửa nhiều cây vẫn có thể để lại trạng thái dở. Strong exception guarantee cần transaction hoặc persistent/path-copying.


## 18. C++17: mô hình chuyển ownership bằng `std::unique_ptr`

Trong C++, một lỗi đặc trưng của split/merge mutating là **hai root cùng tưởng mình sở hữu một node**. Có thể dùng `std::unique_ptr<Node>` để khiến quyền sở hữu được truyền tường minh qua `std::move`; điều này giúp tránh giải phóng trùng ở đường chạy thông thường.

Ví dụ sau là chương trình C++17 **độc lập**, minh họa split và merge theo miền với key/priority đã chọn, không chứa PRNG. Nó tập trung vào việc truyền root, nên `insert_new` có **tiền điều kiện khóa chưa tồn tại và priority phân biệt**.

```cpp
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <memory>
#include <utility>
#include <vector>

struct Node {
    int key;
    std::uint64_t priority;
    std::size_t size = 1;
    std::unique_ptr<Node> left;
    std::unique_ptr<Node> right;

    Node(int k, std::uint64_t p) : key(k), priority(p) {}
};

using Ptr = std::unique_ptr<Node>;

std::size_t size_of(const Ptr& root) {
    return root ? root->size : 0;
}

void pull(Node& root) {
    root.size = 1 + size_of(root.left) + size_of(root.right);
}

// Consumes root. Returns (< key, >= key).
std::pair<Ptr, Ptr> split_lt(Ptr root, int key) {
    if (!root)
        return {nullptr, nullptr};

    if (root->key < key) {
        auto parts = split_lt(std::move(root->right), key);
        root->right = std::move(parts.first);
        pull(*root);
        return {std::move(root), std::move(parts.second)};
    }

    auto parts = split_lt(std::move(root->left), key);
    root->left = std::move(parts.second);
    pull(*root);
    return {std::move(parts.first), std::move(root)};
}

// PRECONDITION: all keys(A)<all keys(B) if both nonempty.
Ptr merge_ordered(Ptr a, Ptr b) {
    if (!a)
        return b;
    if (!b)
        return a;

    if (a->priority < b->priority) {
        a->right = merge_ordered(std::move(a->right), std::move(b));
        pull(*a);
        return a;
    }

    b->left = merge_ordered(std::move(a), std::move(b->left));
    pull(*b);
    return b;
}

void inorder(const Ptr& root, std::vector<int>& keys) {
    if (!root)
        return;

    inorder(root->left, keys);
    keys.push_back(root->key);
    inorder(root->right, keys);
}

Ptr insert_new(Ptr root, int key, std::uint64_t priority) {
    // Cấp node TRƯỚC khi split để tránh cấp phát tại bước sau.
    auto fresh = std::make_unique<Node>(key, priority);
    auto halves = split_lt(std::move(root), key);

    return merge_ordered(
        merge_ordered(std::move(halves.first), std::move(fresh)),
        std::move(halves.second)
    );
}

int main() {
    Ptr root;
    root = insert_new(std::move(root), 30, 10);
    root = insert_new(std::move(root), 10, 80);
    root = insert_new(std::move(root), 50, 20);
    root = insert_new(std::move(root), 20, 30);
    root = insert_new(std::move(root), 25, 60);
    root = insert_new(std::move(root), 40, 70);

    auto halves = split_lt(std::move(root), 30);
    assert(!root);  // Ownership đã được chuyển vào split.

    std::vector<int> keys_left;
    std::vector<int> keys_right;

    inorder(halves.first, keys_left);
    inorder(halves.second, keys_right);

    assert((keys_left == std::vector<int>{10, 20, 25}));
    assert((keys_right == std::vector<int>{30, 40, 50}));

    root = merge_ordered(
        std::move(halves.first), std::move(halves.second)
    );

    std::vector<int> whole;
    inorder(root, whole);
    assert((whole == std::vector<int>{10, 20, 25, 30, 40, 50}));
    assert(size_of(root) == 6);

    std::cout << "Treap split/merge with unique_ptr: OK\n";
    return 0;
}
```

### 18.1. `std::move` không phải sao chép node

- `split_lt(std::move(root),30)` chuyển quyền sở hữu gốc vào hàm split; biến `root` ở `main` không còn giữ cây.
- Hai `unique_ptr` được trả về sở hữu hai cây con rời nhau.
- `merge_ordered(std::move(halves.first),std::move(halves.second))` chuyển quyền sở hữu cả hai cây nguồn vào hàm merge.
- Sau khi merge hoàn tất, biến `root` mới là owner của toàn bộ treap.

Việc dịch chuyển `unique_ptr` thường chỉ di chuyển quyền sở hữu con trỏ, **không** sao chép các bản ghi khóa. Điều này phù hợp ý nghĩa split/merge theo miền.

### 18.2. Những gì `unique_ptr` chưa giải quyết

- Nó không kiểm tra `max_key(A)<min_key(B)`. Merge sai miền vẫn có thể phá BST.
- Nó không kiểm tra key trùng hoặc priority trùng khi gọi `insert_new`; đó là tiền điều kiện phải bảo đảm ở wrapper.
- Nó không tạo transaction tự động. Nếu recursion ném exception sau một số thao tác `std::move`, code cần thiết kế phục hồi hoặc strong guarantee riêng.
- Hủy một cây rất sâu vẫn có thể tạo một chuỗi destructor lồng nhau; **thu hồi k node là công việc O(k)**, không thể tính gộp vào một merge logarit.
- Không có iterator an toàn concurrent hay persistent version.

Việc cấp node mới **trước split** trong ví dụ tránh một nguồn lỗi cấp phát cụ thể, nhưng **không phải chứng minh strong exception guarantee cho toàn hàm**. Đây là điểm quan trọng khi chuyển từ mã thuật toán sang API production.

## 19. Bẫy kỹ thuật thường gặp

| Phát biểu hoặc thao tác sai | Vấn đề | Cách xử lý |
| --- | --- | --- |
| “Split sửa key ở mỗi node” | Không cần và có thể phá BST | Chỉ đổi liên kết, giữ key/priority |
| “Split cần duyệt cả hai con của mọi node” | Làm mất ưu thế đường tìm | Chỉ đệ quy vào một nhánh theo so sánh key |
| “`split_lt` đưa key bằng k sang trái” | Sai dấu so sánh | L: <k, R: ≥k |
| “`split_le` giống hoàn toàn `split_lt`” | Key bằng k vào khác phía | L: ≤k, R: >k |
| “`split_le(k)` cứ viết `split_lt(k+1)`” | Có thể overflow/không có successor | Dùng comparator ≤ trực tiếp |
| “`split3` luôn có node ở giữa” | Key có thể vắng | E = NULL hoặc đúng một node |
| “Sau split, root cũ vẫn đại diện toàn tập” | Hai cây đã đổi liên kết | Chuyển owner sang hai root kết quả |
| “Merge so key ở mỗi mức để chọn gốc” | Lẫn BST với heap | Sau khi có tiền đề key, chọn gốc theo priority |
| “Có thể merge {10,50} với {20,40}” | Hai miền khóa xen kẽ | Dùng union hoặc chèn từng khóa |
| “Đổi key MID rồi ghép lại luôn đúng” | Có thể vượt miền/trùng | Kiểm tra lại BST và ranh giới |
| “Xóa khoảng k node luôn O(log n) tổng thể” | Thu hồi k node/payload chưa tính | Tách structural và cleanup O(k) |
| “Chỉ cần `size(L)+size(R)=n` là split đúng” | Có thể mất/lặp node bù trừ | So tập key, identity và heap |
| “Một merge thành công thì tree B vẫn dùng độc lập” | B đã bị chuyển ownership | Đặt root B rỗng, không giữ alias |
| “Union hai set chính là merge” | Khác tiền điều kiện, khác duplicate policy | Dùng union chuyên biệt |
| “Range count nên split rồi merge” | Chỉ đọc mà vẫn sửa liên kết | Dùng rank(hi)-rank(lo) |
| “Lazy add vào key không ảnh hưởng BST” | Key có thể vượt ranh giới | Chỉ lazy update payload được thiết kế đúng |
| “Split trả hai cây nên cần O(n) bản sao node” | Nhầm ownership với copy | Mutating split sửa O(h) cạnh |
| “Persistent treap dùng nguyên split mutating” | Phiên bản cũ có thể bị sửa | Path-copy, node bất biến |
| “Treap có expected O(log n) nên worst O(log n)” | Cây lệch hợp lệ vẫn tồn tại | Ghi worst O(n), xét cây cân bằng nếu cần |
| “Tăng recursionlimit xử lý mọi trường hợp xấu” | Stack và lỗi giữa chừng vẫn tồn tại | Bản lặp/transaction/fallback |
| “Version của iterator là lock” | Không đảm bảo atomic nhiều con trỏ | Khóa/snapshot/concurrent algorithm |
| “Đo `len(other)` sau join để biết số đã chuyển” | Other đã rỗng | Lưu count trước join |

### 19.1. Quy trình debug khi split ra sai miền

Giả sử T có `{10,20,30,40}` và `split_lt(T,30)` trả L={10,20,30}. Kiểm tra:

1. Nhánh `root.key<k` có dùng so sánh **nghiêm ngặt** không?
2. Key bằng k được đưa vào **R** hay bị gắn sai?
3. Bên gọi có nhận đúng cả hai gốc mới không?
4. `root.left`/`root.right` sau đệ quy đã gắn đúng nửa nhỏ hơn/lớn hơn?
5. Inorder và `size` có khớp? Có node bị chia sẻ giữa L và R không?

Không sửa “bằng cách lọc bỏ 30 khỏi L” sau cùng: đó là che lỗi và có thể làm mất identity/node. Phải sửa **đúng phép so sánh và con trỏ**.

### 19.2. Quy trình debug khi merge phá heap

Nếu merge cho inorder đúng nhưng parent priority lớn hơn child:

1. Hai cây nguồn trước merge đã đúng heap chưa?
2. Khi cả hai không rỗng, code có chọn **root có priority nhỏ hơn** không?
3. Sau khi chọn A, có nối `A.right=merge(A.right,B)` thay vì sửa `A.left` không?
4. Sau khi chọn B, có nối `B.left=merge(A,B.left)` không?
5. Có xử lý tie-break priority đồng nhất mọi nơi không?
6. `pull` có cập nhật size sau khi thay liên kết không?

Nếu hai cây nguồn dùng priority trùng hoàn toàn và code giả định nghiêm ngặt, cần sửa **mô hình priority**, không chỉ đảo một phép so ở một nhánh.

### 19.3. Các loại kiểm thử cần có trước khi dùng thật

- Tách cây rỗng, cây một node, ngưỡng ngoài min/max.
- Ngưỡng đúng bằng key tồn tại và nằm giữa hai key.
- Tách rồi merge hồi nguyên, so identity và tập key.
- Merge với một bên rỗng, với hai dải đúng thứ tự.
- Từ chối merge khi hai miền giao hoặc đảo thứ tự.
- `split3` với key tồn tại/không tồn tại.
- Tách `[lo,hi)` với lo<hi, lo=hi, lo>hi.
- Xóa cả tập, xóa khoảng không có key.
- Chuyển dải tới cây đích rỗng hoặc có khoảng trống hợp lệ.
- Từ chối chuyển dải khi đích có key trùng trong khoảng.
- Kiểm tra `rank` và metadata sau mọi lần sửa con trỏ.
- Tái lập test với seed và nhiều thứ tự chèn.
- Dựng treap lệch để xác nhận giới hạn đệ quy.
- Nếu có concurrent/persistent, test riêng atomicity/ownership, không dựa chỉ vào unit test set.


## 20. Bài tập thực hành có lời giải

### Bài 1. Xác định miền khóa của `split_lt`

Treap T chứa các khóa `{5,10,20,25,30,50}`. Gọi `split_lt(T,25)`. Hai tập L và R gồm những gì?

**Lời giải:** L nhận các key **nhỏ hơn 25**: `{5,10,20}`. R nhận các key **lớn hơn hoặc bằng 25**: `{25,30,50}`. Key đúng 25 nằm ở R, không nằm trong L.

### Bài 2. `split_le` khác ở đâu?

Cùng tập T, gọi `split_le(T,25)`. Kết quả?

**Lời giải:** L chứa khóa ≤25: `{5,10,20,25}`; R chứa khóa >25: `{30,50}`. So với `split_lt`, **chỉ việc phân bổ key bằng ngưỡng thay đổi**.

### Bài 3. Split với ngưỡng nhỏ hơn min

Treap có `{10,20,30}`. `split_lt(T,0)` trả gì?

**Lời giải:** L rỗng; R có `{10,20,30}`. Không mất node, không cần tạo node mới. `size(L)+size(R)=3`.

### Bài 4. Split với ngưỡng lớn hơn max

Treap có `{10,20,30}`. `split_lt(T,100)` trả gì?

**Lời giải:** L có `{10,20,30}`, R rỗng. Việc một bên rỗng là kết quả hợp lệ và là trường hợp quan trọng của primitive.

### Bài 5. Ngưỡng không tồn tại

Treap `{10,20,30,40}` được split theo k=25. Điều gì xảy ra với khóa 25?

**Lời giải:** Không tạo thêm key25. Kết quả `L={10,20}`, `R={30,40}`. Split chỉ **phân phối lại node đã tồn tại**, không chèn ngưỡng vào cây.

### Bài 6. Vì sao nhánh trái không cần duyệt hết?

Trong `split_lt(root,k)`, nếu `root.key<k`, tại sao có thể giữ nguyên toàn bộ `root.left`?

**Lời giải:** Bất biến BST cho `x.key<root.key<k` với mọi node thuộc cây trái. Vì vậy toàn bộ cây trái chắc chắn thuộc L, chỉ cây phải có thể chứa hai loại khóa và cần split.

### Bài 7. Tại sao nhánh phải không cần duyệt hết?

Nếu `root.key≥k`, cây con nào chắc chắn thuộc R và vì sao?

**Lời giải:** Toàn bộ `root.right` thuộc R vì các khóa ở đó >root.key≥k. Chỉ `root.left` có thể cần tách theo ngưỡng.

### Bài 8. Sửa đúng con trỏ ở nhánh `root.key<k`

Giả sử `(a,b)=split_lt(root.right,k)`. Phải đặt `root.right` bằng a hay b?

**Lời giải:** Đặt **`root.right=a`**, vì a chứa các key <k và vẫn lớn hơn root.key theo cây con gốc. b chứa key≥k, phải trả thành nửa R, không nối vào root L.

### Bài 9. Sửa đúng con trỏ ở nhánh `root.key≥k`

Giả sử `(a,b)=split_lt(root.left,k)`. Phải đặt `root.left` bằng gì?

**Lời giải:** Đặt **`root.left=b`**; b là phần ≥k nhưng nhỏ hơn root.key vì vốn thuộc cây trái. a (<k) trở thành kết quả L độc lập.

### Bài 10. Tổng số node sau split

Treap có 100 node. Sau split, L có 37 node. R phải có bao nhiêu node nếu primitive đúng và không tạo/xóa node?

**Lời giải:** `100-37=63` node. Tổng size không thay đổi. Tuy vậy chỉ so số đếm chưa đủ kiểm tra **tính duy nhất của node identity**, cần thêm validator.

### Bài 11. `split3` với key có mặt

T={10,20,30,40}, `split3(T,30)` trả ba miền khóa nào?

**Lời giải:** `A={10,20}`, `E={30}`, `B={40}`. Với treap set, E đúng một node, không phải một cây lớn có key trùng.

### Bài 12. `split3` với key vắng

T={10,20,30,40}, `split3(T,25)` trả ba miền khóa nào?

**Lời giải:** `A={10,20}`, `E=∅`, `B={30,40}`. Không được tạo node key25 để “điền” phần bằng.

### Bài 13. Vì sao không dùng `k+1` trong mọi ngôn ngữ?

Muốn tách các key≤k, một người viết `split_lt(T,k+1)`. Điều gì có thể sai?

**Lời giải:** Với integer C/C++ ở giá trị lớn nhất, `k+1` có thể overflow; với chuỗi hoặc khóa tổng quát không có toán tử successor đơn giản. Viết **`split_le` bằng comparator ≤** trực tiếp sẽ đúng về hợp đồng tổng quát hơn.

### Bài 14. Tiền điều kiện của `merge_ordered`

A có `{10,20}`, B có `{30,40}`. Có được merge không? Nếu A={10,50}, B={20,40} thì sao?

**Lời giải:** Trường hợp thứ nhất hợp lệ vì `20<30`. Trường hợp thứ hai **không** hợp lệ vì `50>20`; các miền xen kẽ, phải dùng union hoặc chèn từng khóa, không dùng merge theo miền.

### Bài 15. Hai cây có key bằng nhau ở biên

A={10,20}, B={20,30}. Có được `merge_ordered(A,B)` trong treap set không?

**Lời giải:** Không. Điều kiện nghiêm ngặt `max(A)<min(B)` thất bại vì `20=20`. Nếu muốn union set, phải chọn chính sách loại một node duplicate.

### Bài 16. Root nào được chọn khi merge?

Hai treap có miền khóa hợp lệ; root A priority15, root B priority7. Min-heap yêu cầu root kết quả là node nào?

**Lời giải:** **Root B priority7**, vì nó có priority nhỏ hơn root A, và hai gốc đã là node ưu tiên tốt nhất của hai cây nguồn. Cây trái mới của B được tạo bằng `merge_ordered(A,B.left)`.

### Bài 17. Nhánh merge khi root A tốt hơn

Nếu `A.priority<B.priority`, nhánh nào của A thay đổi?

**Lời giải:** `A.right` được gán `merge_ordered(A.right,B)`. `A.left` giữ nguyên. Mọi key B đều lớn hơn mọi key A, nên chỉ có thể nằm bên phải root A.

### Bài 18. Nhánh merge khi root B tốt hơn

Nếu `B.priority<A.priority`, nhánh nào của B thay đổi?

**Lời giải:** `B.left` nhận `merge_ordered(A,B.left)`. `B.right` giữ nguyên. Mọi key A đều nhỏ hơn mọi key B, đúng vị trí cây trái.

### Bài 19. Merge với một cây rỗng

`merge_ordered(NULL,B)` và `merge_ordered(A,NULL)` trả gì, có cấp node mới không?

**Lời giải:** Trả lần lượt B và A; không cần cấp node dữ liệu. Đây là điều kiện dừng quan trọng của recursion.

### Bài 20. Vì sao merge không phải phép nối hai linked list?

Nếu A có 1.000 node, B có 1.000 node, merge bắt buộc sao chép 2.000 node sang một vùng mới không?

**Lời giải:** Không. Bản mutating chỉ thay **một số liên kết trên đường biên**, không copy từng node. Chi phí cấu trúc O(h_A+h_B); số node mới bằng 0, nhưng metadata/stack vẫn cần được tính.

### Bài 21. Split rồi merge có phục hồi cùng hình dạng?

Có cùng tập node và các priority phân biệt. Split theo k rồi merge hai nửa đúng thứ tự. Cây cuối có chỉ cùng tập khóa hay cùng hình dạng?

**Lời giải:** **Cùng hình dạng Cartesian tree** khi mọi cặp key–priority được giữ nguyên, vì hai bất biến BST/min-heap và priority phân biệt xác định cây duy nhất. Điều này không có nghĩa quá trình không đổi các con trỏ tạm thời.

### Bài 22. Cô lập miền nửa mở

T={10,20,25,30,40,50}, cần MID chứa `[20,45)`. Liệt kê hai split và ba miền.

**Lời giải:** `(L,GE)=split_lt(T,20)` cho L={10}, GE={20,25,30,40,50}. Tiếp `(MID,R)=split_lt(GE,45)` cho MID={20,25,30,40}, R={50}. Hai biên đã được áp dụng đúng.

### Bài 23. Biên đóng/mở khác

Với T={10,20,25,30,40,50}, muốn MID chứa `(20,40]`, dùng split nào?

**Lời giải:** Đầu tiên `split_le(T,20)` để tách key≤20 khỏi phần >20. Sau đó `split_le(part_gt_20,40)` để lấy MID có key≤40. Kết quả MID={25,30,40}.

### Bài 24. Miền rỗng

Một API gọi `extract_range(50,20)` trên T có 100 node. Kết quả đúng và hành vi nên có là gì?

**Lời giải:** Khoảng `[50,20)` rỗng do lo>hi. Trả treap rỗng, giữ nguyên T, không cần split hay thay con trỏ. `erase_range` tương ứng trả 0.

### Bài 25. Xóa cả dải bằng cách nào?

T={10,20,25,30,40,50}. Muốn xóa `[20,45)`, root còn lại chứa gì?

**Lời giải:** Split thành L={10}, MID={20,25,30,40}, R={50}. Dùng `merge_ordered(L,R)`, root còn {10,50}. MID có 4 node, được trả riêng hoặc thu hồi theo ownership.


### Bài 26. Chi phí dải k node: cấu trúc so với thu hồi

Một treap có n=1 triệu node, MID có k=100.000 node. Có thể nói giải phóng cả MID chỉ tốn O(log n) vì dùng hai split và một merge không?

**Lời giải:** **Không** nếu yêu cầu hủy từng node/payload. Phần **thay liên kết** chỉ O(log n) kỳ vọng trong mô hình random phù hợp, nhưng dọn 100.000 node thường cần Θ(k) công việc. Nếu chỉ **trả MID cho bên gọi** làm treap riêng, lúc trích xuất không phải duyệt toàn bộ k node.

### Bài 27. Đếm khoảng bằng rank

T={10,20,25,30,40,50}, tính số khóa thuộc `[20,45)` chỉ bằng rank.

**Lời giải:** `rank(45)=5` vì 10,20,25,30,40 nhỏ hơn 45; `rank(20)=1`. Hiệu `5−1=4`. Hai lần rank không cần split và không sửa cây.

### Bài 28. Rank khi key không tồn tại

Với cùng T, `rank(26)` bằng bao nhiêu? Có cần key 26 tồn tại không?

**Lời giải:** `rank(26)=3` vì các key nhỏ hơn 26 là 10,20,25. Rank chỉ đếm quan hệ thứ tự, **không** yêu cầu key truy vấn tồn tại.

### Bài 29. Sum trong khoảng

Treap lưu payload value: key 10→2, key20→3, key30→5, key40→7. Tính tổng value `[20,40)`.

**Lời giải:** Miền gồm key20 và key30, tổng `3+5=8`. Có thể tính `prefix_sum(40)-prefix_sum(20)=(2+3+5)-2=8`. Nếu metadata subtree_sum đúng, hai prefix đi theo một đường, không cần split.

### Bài 30. Vì sao cập nhật key trong MID nguy hiểm?

L={10}, MID={20,25}, R={30,40}. Sửa key của MID thành {35,40} rồi merge. Sai ở đâu?

**Lời giải:** MID không còn nằm trước R vì 40≥30, đồng thời key40 trùng R. `merge_ordered(MID,R)` vi phạm tiền đề và có thể phá BST set. Muốn cập nhật **key**, cần tái định vị/thực hiện union và xử lý duplicate; cập nhật payload mới là bài toán lazy range đơn giản hơn.

### Bài 31. Chuyển dải giữa hai treap không trùng

SOURCE={10,20,25,30,40,50}, DEST={1,5,60,80}. Chuyển `[20,45)`. Hai set cuối là gì?

**Lời giải:** SOURCE còn {10,50}; DEST trở thành {1,5,20,25,30,40,60,80}. MID={20,25,30,40} đã được chuyển ownership chứ không copy node, và DEST được nối theo thứ tự `Dleft + MID + Dright`.

### Bài 32. Chuyển dải bị trùng key

Nếu DEST={1,25,60}, SOURCE có MID={20,25,30,40}, có được dùng join_right để chèn MID vào DEST không?

**Lời giải:** Không. Key25 đã ở DEST và cùng thuộc MID, vi phạm set và điều kiện các miền không giao. Phải **từ chối trước khi sửa** hoặc dùng chính sách union/ghi đè có thiết kế riêng.

### Bài 33. Sai lầm đếm sau khi cây nguồn bị consume

Một đoạn code gọi `moved=dst.join_right(other)` rồi thử `len(other)` để biết số node đã chuyển. `len(other)` bằng gì?

**Lời giải:** Bằng **0** sau join thành công trong API của bài, vì `other._root=None`. Phải lưu `len(other)` trước merge, hoặc dùng chính số `moved` được trả. Đếm sau khi đã chuyển ownership là đọc trạng thái mới, không phải số phần tử cũ.

### Bài 34. Kiểm tra identity

Một split trả hai treap có đúng các key dự kiến, nhưng thực hiện bằng cách copy tất cả node. Điều này có đáp ứng hợp đồng **split in-place** của bài không?

**Lời giải:** Không. Kết quả tập khóa có thể đúng, nhưng hợp đồng in-place yêu cầu giữ **identity** các node dữ liệu và chỉ chuyển liên kết/ownership, không tạo bản sao dữ liệu. Test `id(node)` trước/sau giúp phát hiện vi phạm này.

### Bài 35. Vì sao union không phải merge?

A={10,50}, B={20,40}. Nêu hai cách hợp tập đúng và cách nào tận dụng được cả hai cấu trúc treap.

**Lời giải:** Cách dễ là **chèn từng key B vào A** với chính sách duplicate set. Cách chuyên biệt dùng **union theo priority kết hợp `split3`** để chia một treap theo key gốc treap kia rồi đệ quy. Cả hai khác `merge_ordered` vì hai miền khóa xen kẽ.

### Bài 36. Chứng minh chọn gốc union

Trong union hai treap min-heap, vì sao có thể so priority của hai gốc rồi chọn gốc tốt hơn làm root kết quả?

**Lời giải:** Mỗi root đã là node ưu tiên tốt nhất trong treap của chính nó. Do đó node có priority nhỏ hơn giữa hai root cũng tốt hơn mọi node ở cả hai cây. Nó phải làm root của treap kết quả (với comparator priority nghiêm ngặt). Các node còn lại được phân vào trái/phải theo key qua split3.

### Bài 37. Kỳ vọng không phải worst-case

Treap có O(log n) kỳ vọng cho split. Dựng trạng thái hợp lệ khiến split mất Θ(n).

**Lời giải:** Dùng key `1,2,\ldots,n` và priority tăng theo key, tạo cây lệch phải dài n. `split_lt(T,n)` đi qua gần mọi node dọc đường phải, nên Θ(n). Cây vẫn đúng BST và min-heap; không mâu thuẫn với expected O(log n).

### Bài 38. Stack đệ quy trên cây lệch

Một treap có h=n=50.000 node theo đường phải. Hàm split đệ quy có thể gặp vấn đề gì ngay cả khi thuật toán đúng?

**Lời giải:** Nó dùng O(h) stack, có thể vượt giới hạn đệ quy Python hoặc stack C/C++ trước khi xong. Nếu đã sửa vài con trỏ thì exception còn có thể để lại trạng thái dở. Cần bản lặp, giới hạn/fallback và exception safety rõ.

### Bài 39. Persistent treap có dùng split mutating được không?

Hai phiên bản lịch sử chia sẻ vài node. Phiên bản mới gọi `split_lt` mutating trên root chung. Điều gì có thể xảy ra với phiên bản cũ?

**Lời giải:** Các node chung bị đổi con trỏ, nên phiên bản cũ có thể bị thay đổi mà không chủ ý. Persistent treap cần **node bất biến hoặc path-copy** ở các đường sửa; sự chia sẻ node chỉ an toàn khi không sửa trực tiếp node đã chia sẻ.

### Bài 40. Trình bày hợp đồng của một thao tác trích xuất

Bạn thiết kế API `extract_range(lo,hi)` cho treap set. Hãy nêu bốn yếu tố phải ghi rõ trong tài liệu.

**Lời giải:** Tối thiểu cần: (1) khoảng là **nửa mở [lo,hi)**, với lo≥hi trả rỗng; (2) source **mất** các node trong khoảng và hàm trả một treap **sở hữu** đúng các node ấy; (3) bất biến BST, min-heap và size vẫn đúng, không copy node trong bản mutating; (4) chi phí cấu trúc O(log n) **kỳ vọng**, worst O(n), còn hủy k node/payload tính riêng. Với production cần thêm hợp đồng iterator, ngoại lệ và đồng thời.

## 21. Tổng kết và checklist triển khai

Hai phép nền tảng của treap theo miền khóa là:

\[
\boxed{
split\_lt(T,k)=(\{x<k\},\{x\ge k\})
}
\]

và:

\[
\boxed{
merge\_ordered(A,B)\quad\text{khi } \max(A)<\min(B).
}
\]

Chúng tạo ra và tái nối các treap bằng cách thay **đường liên kết**, bảo toàn key, priority, BST, heap và metadata size khi hoàn tất. Điều đó cho phép biến đổi dải khóa nhanh về **số bước cấu trúc** mà không duyệt qua từng node trong dải.

### 21.1. Công thức cô lập và xóa `[lo,hi)`

```text
(L, GE)    = SPLIT_LT(root, lo)
(MID, R)   = SPLIT_LT(GE, hi)

# L   : key < lo
# MID : lo <= key < hi
# R   : key >= hi

root_after = MERGE_ORDERED(L, R)
return MID
```

Nếu không muốn loại MID, có thể ghép lại:

```text
root = MERGE_ORDERED(MERGE_ORDERED(L, MID), R)
```

vì các miền khóa đã được tách đúng thứ tự. Phép `merge_ordered` **không thể** được dùng thay thế `union` cho hai tập khóa xen kẽ.

### 21.2. Bảng quyết định nhanh

| Nhiệm vụ | Primitive hoặc công thức | Lưu ý |
| --- | --- | --- |
| Giữ key <k, trả key ≥k | `split_lt` | Key bằng k vào R |
| Giữ key ≤k, trả key >k | `split_le` | Key bằng k vào L |
| Xóa đúng một key | `split3` rồi merge hai miền ngoài | E rỗng hoặc một node |
| Trích xuất `[lo,hi)` | Hai lần `split_lt` | lo≥hi trả rỗng |
| Ghép hai dải đúng thứ tự | `merge_ordered` | max(A)<min(B) |
| Đếm key trong một khoảng | `rank(hi)-rank(lo)` | Không cần sửa cây |
| Tổng payload trong khoảng | Hiệu prefix aggregate | Cần metadata sum đúng |
| Hợp hai tập xen kẽ | Union chuyên biệt / chèn từng key | Có chính sách duplicate |
| Chuyển dải từ SOURCE tới DEST | Extract + split DEST + ordered merges | Kiểm tra overlap trước |
| Giữ nhiều phiên bản cũ | Persistent/path-copy | Không sửa node chia sẻ |

### 21.3. Kiểm tra trước khi kết luận “đã đúng”

1. **BST:** mọi key bên trái nhỏ hơn gốc, bên phải lớn hơn gốc.
2. **Heap:** parent.priority nhỏ hơn child.priority theo comparator thống nhất.
3. **Size/aggregate:** metadata được tính lại từ dưới lên sau đổi con trỏ.
4. **Miền khóa:** mọi lần merge đều có bằng chứng `max(A)<min(B)`.
5. **Ownership:** split không tạo bản sao ngoài dự kiến; không còn hai owner cùng quản lý node mutating.
6. **Trường hợp biên:** cây rỗng, một phía rỗng, ngưỡng tồn tại/không tồn tại, lo≥hi.
7. **Hiệu năng:** O(log n) là **kỳ vọng dưới mô hình random thích hợp**; worst-case vẫn O(n).
8. **Tài nguyên:** tách node và thu hồi node là hai chi phí khác nhau; stack đệ quy, alias, exception và đồng thời cần hợp đồng riêng.

**Kết luận:** sức mạnh của `split` và `merge` không phải là “phép màu” cho phép gộp bất kỳ hai cây, mà là khai thác chính xác **hai bất biến của treap**. BST cho ta các **ranh giới miền khóa**, heap chỉ ra cách **chọn gốc khi nối**. Hiểu rõ tiền điều kiện và ownership sẽ giúp bạn biến đổi cả một khoảng dữ liệu bằng vài thao tác theo chiều cao cây, đồng thời không đánh đổi tính đúng lấy một lời hứa hiệu năng kỳ vọng bị diễn giải quá mức.
