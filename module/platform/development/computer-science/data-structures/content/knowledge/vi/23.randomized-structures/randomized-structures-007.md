# Chèn, xóa và quay trong treap

Một **treap** (*tree + heap*) là cây nhị phân được quản lý bằng hai thứ tự đồng thời: **khóa** tuân theo quy tắc cây tìm kiếm nhị phân (*BST*), còn **độ ưu tiên** tuân theo quy tắc heap. Nếu tìm kiếm chỉ cần so sánh khóa như BST, thì **chèn và xóa mới là lúc ta thấy giá trị của phép quay**: ta vừa phải đưa khóa vào đúng thứ tự, vừa phải sắp lại các quan hệ cha–con cho đúng độ ưu tiên.

Bài **“Chèn, xóa và quay trong treap”** thuộc chương **Cấu trúc ngẫu nhiên** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Theo định hướng xây dựng nền tảng cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, bài nhấn mạnh ba câu hỏi khi thiết kế: **bất biến nào phải giữ, thao tác sửa đúng liên kết nào, và chi phí thời gian/bộ nhớ của từng lựa chọn là gì?**

Bài tập trung vào **treap dạng set theo khóa**, một node cho mỗi khóa khác nhau. Priority được dùng để điều chỉnh hình dạng; không phải khóa người dùng tìm kiếm. Ta chọn **min-heap trên priority**: số priority càng nhỏ càng được đưa lên gần gốc. Tài liệu dùng cùng quy ước từ đầu đến cuối; nếu dùng max-heap, cần đảo các phép so sánh priority, không chỉ đổi lời giải thích.

**Sau bài học, bạn có thể:**

- Chỉ ra hai bất biến BST/heap và phân biệt vị trí đúng theo khóa với vị trí đúng theo priority.
- Thực hiện **quay trái, quay phải** bằng sơ đồ con trỏ và chứng minh chúng giữ thứ tự inorder.
- Mô phỏng **chèn bằng BST rồi quay nút mới lên**, kể cả trường hợp phải quay liên tiếp.
- Mô phỏng **xóa bằng quay nút cần xóa xuống**, giải thích vì sao được phép có vi phạm heap tạm thời trên đúng đường nút sắp bị loại.
- So sánh hai cách xóa **quay xuống** và **`merge(left,right)`**; hiểu tiền điều kiện của `merge`.
- Viết Python tự chứa có `insert`, `discard`, tìm kiếm, đếm rotations, `subtree_size` và validator; xem một ví dụ C cập nhật con trỏ đúng.
- Kiểm thử với priority ấn định, seed tái lập, mô hình `set`, khóa trùng, xóa gốc và các trường hợp biên.
- Phân biệt **O(log n) kỳ vọng** với **worst-case O(n)** và chi phí ngăn xếp đệ quy.

## 1. Hợp đồng dữ liệu và bất biến trước khi sửa cây

Mỗi node có thể được mô hình hóa như sau:

```text
Node:
    key:       khóa, dùng so sánh BST
    priority:  độ ưu tiên, dùng so sánh min-heap
    left:      con trái hoặc NULL
    right:     con phải hoặc NULL
    size:      số node trong cây con (tùy chọn)
```

Với node `u`, các bất biến là:

**BST trên khóa:**

\[
\forall x\in subtree(u.left): x.key<u.key;
\quad
\forall y\in subtree(u.right): u.key<y.key.
\]

**Min-heap trên priority:**

\[
u.priority<child.priority
\]

cho mọi con tồn tại, nếu priority được đặt theo một **thứ tự toàn phần nghiêm ngặt, không trùng**. Một chương trình dùng PRNG hữu hạn có thể thêm tie-breaker để làm các priority duy nhất.

**Metadata kích thước:**

\[
size(u)=1+size(u.left)+size(u.right),\quad size(NULL)=0.
\]

**Sở hữu node:** mỗi khóa trong set có đúng một node reachable từ gốc; không có chu trình. Sau chèn thành công, số node tăng 1; sau xóa thành công, giảm 1.

### 1.1. Key không phải priority

Ví dụ các cặp `(key,priority)`:

```text
                 (40,10)
                /       \
            (20,30)   (60,40)
            /    \         \
        (10,80) (30,60)   (70,90)
```

Cây đúng BST vì `10<20<30<40<60<70` theo inorder. Heap đúng vì tại mỗi cạnh priority cha nhỏ hơn con.

Nếu tìm khóa 30, ta rẽ **theo key**: 40→20→30, **không rẽ theo priority**. Nếu muốn đưa một node mới có priority 5 vào, ta vẫn định vị theo key trước, sau đó dùng quay để đưa node về vị trí heap thích hợp.

### 1.2. Định nghĩa chính xác “cây đúng” sau mỗi thao tác

Sau một thao tác hoàn tất, cần kiểm tra độc lập:

1. Inorder tăng nghiêm ngặt; key không thiếu, không lặp.
2. Priority cha luôn tốt hơn priority con theo min-heap.
3. `size` của mọi node bằng số node thật trong cây con.
4. Root được cập nhật nếu quay thay đổi gốc.
5. Node bị xóa không còn reachable; không hủy các node còn dùng.
6. Nếu chèn khóa đã có hoặc xóa khóa vắng, tập logic không thay đổi.

**Lưu ý quan trọng khi xóa bằng quay:** một trạng thái **trung gian** có thể tạm thời vi phạm heap ở cạnh chứa chính node sắp xóa. Bất biến hoàn chỉnh chỉ được đòi hỏi **sau khi thao tác kết thúc**, khi node ấy đã bị gỡ khỏi cây.

## 2. Quay phải: đưa con trái lên mà không đổi inorder

Giả sử `x=y.left`. Các cây con A, B, C chứa các nhóm khóa:

\[
keys(A)<x.key<keys(B)<y.key<keys(C).
\]

Phép quay phải tại y:

```text
TRƯỚC rotate_right(y)           SAU rotate_right(y)

             y                             x
            / \                           / \
           x   C                         A   y
          / \                               / \
         A   B                             B   C
```

Các cạnh sửa đúng thứ tự:

```text
x = y.left             # Lấy con trái hiện tại.
y.left = x.right       # Cây B chuyển thành con trái của y.
x.right = y            # y chuyển thành con phải của x.
return x               # x là gốc MỚI của cây con này.
```

Đếm các gán con trỏ chính: `y.left` và `x.right`. Nếu đang có con trỏ từ cha tới cây con, hoặc y chính là gốc treap, **bên gọi phải lưu gốc x mới**.

### 2.1. Tại sao quay phải giữ BST?

Trước quay, inorder của cây con là:

\[
inorder(A),x,inorder(B),y,inorder(C).
\]

Sau quay, inorder vẫn chính xác dãy đó. Cây B có khóa lớn hơn x nhưng nhỏ hơn y, nên chuyển từ bên phải x sang bên trái y là hợp lệ. Không có key nào được tạo, mất hoặc thay đổi.

### 2.2. Điều kiện để quay phải sửa heap

Trong **chèn**, quay phải tại y khi:

- `x=y.left` đã có cây con hợp lệ,
- `x.priority<y.priority` (x có ưu tiên tốt hơn cha),
- những bất biến heap liên quan khác của cây con vẫn được bảo toàn theo lập luận chèn đệ quy.

Sau quay, x ở trên y, sửa cạnh min-heap sai cũ. Nhưng **không phải mọi phép quay phải tùy ý đều giữ heap**; ví dụ khi x có priority lớn hơn y, quay không lý do sẽ đưa node ưu tiên kém lên trên.

### 2.3. Cập nhật `subtree_size` sau quay phải

Nếu có metadata size:

```text
y.left = x.right
x.right = y

pull(y)    # Tính lại size node nằm DƯỚI.
pull(x)    # Tính lại size node nằm TRÊN.
return x
```

Gọi `pull(x)` trước `pull(y)` có thể dùng size cũ của y và làm sai `rank/select` dù inorder vẫn đúng.

## 3. Quay trái: đưa con phải lên

Nếu `x=y.right`, ta có cấu trúc đối xứng:

```text
TRƯỚC rotate_left(y)            SAU rotate_left(y)

           y                             x
          / \                           / \
         A   x                         y   C
            / \                       / \
           B   C                     A   B
```

Mã liên kết:

```text
x = y.right
y.right = x.left
x.left = y

pull(y)
pull(x)
return x
```

Thứ tự inorder vẫn là:

\[
inorder(A),y,inorder(B),x,inorder(C).
\]

Trong **chèn**, quay trái tại y khi `x=y.right` có priority **nhỏ hơn** priority y.

### 3.1. Vì sao cả hai phép quay đều O(1)?

Mỗi phép quay sửa số lượng **hằng số** con trỏ và cập nhật metadata một số node cố định. Nếu hàm `pull` là O(1), thời gian quay là O(1), bộ nhớ phụ O(1), **không phụ thuộc n**.

Điều cần phân biệt: một lần chèn/xóa có thể gọi **nhiều phép quay** trên một đường trong cây. “Một phép quay O(1)” **không** tự suy ra “một lần chèn O(1)”.

### 3.2. Bảng đối chiếu hai phép quay

| Tình huống | Phép quay | Node lên làm gốc | Cây con được chuyển |
| --- | --- | --- | --- |
| Con trái tốt hơn cha theo priority | `rotate_right(y)` | `y.left` | `x.right` → `y.left` |
| Con phải tốt hơn cha theo priority | `rotate_left(y)` | `y.right` | `x.left` → `y.right` |

**Câu kiểm tra bắt buộc:** “Con trỏ của **cha bên ngoài** sau quay có trỏ tới **gốc mới** không?” Nếu quên, một số node có thể mất liên kết với gốc toàn cây hoặc tạo đường trỏ sai.

## 4. Chèn bằng BST trước, rồi quay để khôi phục heap

Để chèn khóa k với priority p vào một treap set:

1. Tìm vị trí theo **key** như BST.
2. Nếu key đã tồn tại, **không** thêm node và **không** bốc priority mới theo chính sách bài.
3. Tạo node mới, đặt `left=right=NULL`, `size=1`.
4. Gắn node tại lá BST phù hợp.
5. Trên đường quay trở về gốc: nếu con mới có priority nhỏ hơn cha, quay để **đưa con lên**.
6. Cập nhật `size` và gốc cây con sau mỗi lần sửa.

### 4.1. Pseudocode chèn đệ quy

```text
INSERT(root, fresh):
    if root == NULL:
        return fresh

    if fresh.key < root.key:
        root.left = INSERT(root.left, fresh)

        if root.left.priority < root.priority:
            root = ROTATE_RIGHT(root)

    else if fresh.key > root.key:
        root.right = INSERT(root.right, fresh)

        if root.right.priority < root.priority:
            root = ROTATE_LEFT(root)

    else:
        return root                 # Set: khóa trùng.

    pull(root)
    return root
```

Nếu dùng kiểu hàm nhận `fresh` đã được cấp phát trước, API cấp cao phải kiểm tra trùng **trước khi bốc random/cấp node** hoặc có cơ chế hủy node chưa dùng khi trùng. Để tránh side effect khó giải thích, code Python ở phần sau kiểm tra trùng trước.

### 4.2. Vết chèn nhiều phép quay: thêm `(30,10)`

Ban đầu:

```text
              (40,40)
             /       \
         (20,60)    (60,70)
```

Chèn key 30 theo BST: `30<40`, `30>20`, nên đặt làm con phải node 20:

```text
              (40,40)
             /       \
         (20,60)    (60,70)
               \
              (30,10)
```

Cạnh `20(p60)→30(p10)` vi phạm min-heap, nên **quay trái tại 20**:

```text
              (40,40)
             /       \
         (30,10)    (60,70)
          /
      (20,60)
```

Cạnh `40(p40)→30(p10)` cũng vi phạm heap. **Quay phải tại 40**:

```text
                (30,10)
               /       \
           (20,60)    (40,40)
                           \
                          (60,70)
```

Cây kết thúc đúng: inorder `20,30,40,60`; heap có `10<60`, `10<40` và `40<70`.

**Có hai phép quay, không phải một.** Sau phép quay đầu, chỉ cạnh mới giữa 40 và 30 cần tiếp tục xét.

### 4.3. Chèn node có priority kém

Nếu chèn `(50,90)` vào cây ban đầu:

```text
             (40,40)
            /       \
       (20,60)     (60,70)
                   /
               (50,90)
```

Priority 90 lớn hơn 70, nên node mới đã thỏa min-heap với cha. **Không cần quay**, chỉ cập nhật metadata `size` trên đường tìm.

### 4.4. Chèn khóa nhỏ hơn tất cả hoặc lớn hơn tất cả

Vị trí lá BST là cực trái/cực phải, nhưng priority có thể khiến node quay lên trở thành gốc. Điều này phân biệt treap với BST thường:

- Key nhỏ nhất **không nhất thiết** làm gốc.
- Priority nhỏ nhất toàn bộ các node **bắt buộc** làm gốc sau khi chèn hoàn tất (với priority duy nhất).
- Nếu node mới có priority tốt nhất, nó có thể đi qua nhiều phép quay dọc đường tìm.

### 4.5. Bất biến trong lúc chèn

**Trước khi gắn node mới:** treap hiện tại đúng BST và heap.

**Ngay sau khi gắn lá:** BST vẫn đúng vì vị trí chọn theo key. Chỉ cạnh giữa node mới và cha có thể vi phạm heap.

**Khi quay node mới lên:** quay không đổi inorder, đồng thời sửa cạnh heap giữa node mới và cha. Các phần còn lại của hai cây con đã đúng theo giả định đệ quy.

**Khi trả về root mới:** cả BST và heap đúng, mọi node cũ còn nguyên, thêm đúng một khóa. Có thể chứng minh bằng quy nạp theo chiều dài đường tìm.

## 5. Ba trường hợp biên khi chèn

### 5.1. Treap rỗng

`root=NULL`, node mới làm gốc, `size=1`; không có phép quay. Một node luôn thỏa BST và heap.

### 5.2. Khóa đã tồn tại

Với set, `insert(k)` trả `False` và không sửa cây. Đặc biệt:

- Không tạo một node mới có cùng key.
- Không gọi `pull` vô lý trên node mới bị bỏ rơi.
- Trong chính sách code bài, không tiêu thụ PRNG khi insert trùng.
- Không tăng version của iterator nếu tập logic không thay đổi.

Nếu cần **multiset**, nên tăng trường `count` tại node có key bằng nhau (và duy trì `size` theo **tổng số phần tử hay số node** được định nghĩa), hoặc dùng ID phân biệt để tạo thứ tự. Không lén dùng `<=` cho một nhánh rồi mong treap set tự đúng.

### 5.3. Priority bằng nhau

Với nguồn random hữu hạn, priority có thể trùng. Cần một quy tắc thống nhất:

- Dùng tuple `(priority_random,serial_unique)` để có thứ tự toàn phần, hoặc
- Tạo lại priority cho tới khi khác tất cả priority đang dùng, kèm chi phí/bộ nhớ thích hợp.

Khi dùng tuple, **so tuple tại mọi nơi** (chèn, xóa, validator, merge). Không so raw priority ở một chỗ rồi so tuple ở chỗ khác.

Sử dụng PRNG không tự mang lại bảo đảm worst-case: một chuỗi priority hiếm nhưng bất lợi vẫn có thể tạo cây cao Θ(n).


## 6. Xóa bằng quay: đẩy node mục tiêu xuống rồi gỡ khỏi cây

Khác với chèn, xóa không có một node mới có thể quay **lên**. Ta muốn gỡ một node `target` mà không mất các cây con của nó.

Với BST thông thường, xóa node có hai con có thể sao chép khóa successor/predecessor rồi xóa node ở vị trí sâu hơn. Trong treap, nếu chỉ sao chép **key** mà giữ priority không tương ứng, vẫn phải rất cẩn thận vì BST/heap gắn với từng node. Một cách đẹp và thống nhất hơn là **quay chính node mục tiêu xuống** cho tới khi nó có tối đa một con, rồi bỏ node đó khỏi cấu trúc.

### 6.1. Trường hợp node chỉ có 0 hoặc 1 con

Nếu target là lá:

```text
        parent                  parent
          /                       /
       target       ->          NULL
```

Nối cha trực tiếp với `NULL`, giải phóng node target theo hợp đồng sở hữu.

Nếu target có đúng **một con**:

```text
        parent                  parent
          /                       /
       target       ->         child
          \
         child
```

Thay con trỏ từ cha tới target bằng con trỏ tới child. Vì target vốn nằm giữa cha và child trong một BST/heap hợp lệ, việc bỏ target **không phá các thứ tự** trong cây mới.

Nếu target là gốc toàn treap, “con trỏ cha” chính là biến `root` bên ngoài; phải cập nhật `root` bằng con còn lại.

### 6.2. Trường hợp node có hai con: chọn con có priority tốt hơn

Khi target có **cả con trái và con phải**, ta không thể nối một con bất kỳ vào vị trí target rồi vứt con còn lại, vì sẽ mất khóa. Quy tắc xóa quay xuống:

- Nếu `target.left.priority < target.right.priority`, **quay phải tại target**: đưa con trái lên, đẩy target xuống nhánh phải.
- Ngược lại, **quay trái tại target**: đưa con phải lên, đẩy target xuống nhánh trái.
- Tiếp tục tìm **chính node target** vừa đi xuống; lặp cho tới khi target có tối đa một con.
- Gỡ target; giữ các node khác và khôi phục `size` từ dưới lên.

Tại sao chọn **priority tốt hơn giữa hai con**? Khi target bị gỡ, gốc của cây con thay thế phải là node có priority nhỏ nhất trong phần hợp của hai cây con. So priority hai gốc giúp quyết định gốc đó đúng theo min-heap.

### 6.3. Điểm tinh tế: min-heap tạm thời bị phá tại target

Giả sử target đang là gốc treap hợp lệ nên nó có priority **nhỏ hơn** cả hai con. Khi quay một con lên trên target, ta **cố ý** đặt con có priority lớn hơn thành **cha tạm thời** của target. Đây không phải một treap hoàn chỉnh tại thời điểm giữa thao tác.

Sự vi phạm heap này được **cô lập trên đường chứa target sắp xóa**. Mọi node còn lại phải được giữ đúng thứ tự theo key/priority. Sau khi target cuối cùng bị gỡ, cây còn lại khôi phục min-heap.

**Vì thế không thể dùng điều kiện chèn “con ưu tiên tốt hơn cha thì mới quay” trong bước xóa này**: lúc bắt đầu xóa một target hợp lệ, con luôn có priority kém hơn cha. Phép quay khi xóa nhằm đẩy target xuống để loại bỏ, không phải khôi phục heap ngay sau từng phép quay.

### 6.4. Pseudocode xóa bằng quay

```text
ERASE_ROTATE(root, key) -> (new_root, removed):
    if root == NULL:
        return (NULL, false)

    if key < root.key:
        (root.left, removed) = ERASE_ROTATE(root.left, key)
        pull(root)
        return (root, removed)

    if key > root.key:
        (root.right, removed) = ERASE_ROTATE(root.right, key)
        pull(root)
        return (root, removed)

    # Đã tìm ra node target có key.
    if root.left == NULL:
        return (root.right, true)

    if root.right == NULL:
        return (root.left, true)

    # Target có cả hai con.
    if root.left.priority < root.right.priority:
        root = ROTATE_RIGHT(root)
        (root.right, removed) = ERASE_ROTATE(root.right, key)
    else:
        root = ROTATE_LEFT(root)
        (root.left, removed) = ERASE_ROTATE(root.left, key)

    pull(root)
    return (root, removed)
```

Mỗi vòng quay đưa target xuống sâu hơn trong một trong hai cây con, cho tới trường hợp 0/1 con. Tùy ngôn ngữ, khi giải phóng target phải bảo đảm node được hủy đúng **một lần** và hai cây con còn sống không bị hủy theo.

### 6.5. Vết xóa có ba phép quay: bỏ root `(40,10)`

Cây ban đầu:

```text
                  (40,10)  <- XÓA
                 /       \
            (20,30)    (60,20)
            /     \    /     \
        (10,80) (30,60) (50,70) (70,90)
```

Con trái target priority 30, con phải priority 20; **20 tốt hơn 30**, vì vậy quay **trái tại 40**:

```text
                  (60,20)
                 /       \
          (40,10)          (70,90)
          /     \
      (20,30)  (50,70)
      /    \
 (10,80) (30,60)
```

Target vẫn là node `40,10`, bây giờ nằm bên trái 60. Cạnh `60(p20)→40(p10)` **tạm vi phạm heap**; target sẽ tiếp tục được đẩy xuống rồi bị xóa.

Target có con trái 20(priority30), con phải 50(priority70); chọn con trái và quay **phải tại 40**:

```text
                  (60,20)
                 /       \
            (20,30)     (70,90)
            /     \
        (10,80) (40,10) <- XÓA TIẾP
                 /   \
            (30,60) (50,70)
```

Target vẫn có hai con: 30(priority60) và 50(priority70). Chọn con trái, quay **phải tại 40**:

```text
                  (60,20)
                 /       \
            (20,30)     (70,90)
            /     \
        (10,80)  (30,60)
                      \
                     (40,10) <- CÒN MỘT CON
                          \
                         (50,70)
```

Giờ target 40 chỉ có con phải 50. **Thay con trỏ `30.right` từ 40 thành 50**, bỏ node 40:

```text
                  (60,20)
                 /       \
            (20,30)     (70,90)
            /     \
        (10,80)  (30,60)
                      \
                     (50,70)
```

Kiểm tra cuối: inorder `10,20,30,50,60,70`; heap cha tốt hơn con trên mọi cạnh. Đã xóa **đúng một** node key 40, và tổng có **ba phép quay**.

### 6.6. Tại sao có thể tốn nhiều phép quay?

Số phép quay xóa phụ thuộc đường mà target đi xuống qua các gốc cây con cho đến khi chỉ còn một con. Trong trường hợp xấu, đường đó dài Θ(n). Với priority ngẫu nhiên độc lập và đầu vào thích hợp, tổng chi phí tìm và sửa liên kết là O(log n) **kỳ vọng**; không phải O(1) worst-case.

**Không đồng nhất số rotations với số bước tìm**: một phép xóa thường gồm đường tìm target **cộng** nhiều bước quay xuống và cập nhật metadata.

## 7. Xóa bằng `merge(left,right)`: một cách diễn đạt tương đương

Cũng có thể xóa mà **không gọi các hàm quay tường minh**. Khi đã tìm thấy target, hai cây con của nó thỏa:

\[
\forall a\in target.left,\quad \forall b\in target.right:\ a.key<b.key.
\]

Do đó ta có thể gọi:

\[
replacement=MERGE(target.left,target.right).
\]

Đặt replacement vào vị trí target rồi bỏ target. Phép `merge` chọn gốc theo priority, nên thực hiện **cùng ý tưởng lựa chọn node ưu tiên tốt nhất** như việc quay target xuống.

### 7.1. Mã giả `merge` cho min-heap

```text
MERGE(A, B):
    # Tiền điều kiện: mọi khóa trong A < mọi khóa trong B.
    if A == NULL: return B
    if B == NULL: return A

    if A.priority < B.priority:
        A.right = MERGE(A.right, B)
        pull(A)
        return A
    else:
        B.left = MERGE(A, B.left)
        pull(B)
        return B
```

**Tiền đề về key là bắt buộc**. Không được dùng `MERGE` này như phép hợp hai tập bất kỳ có khoảng khóa chồng lấn.

### 7.2. Mã giả xóa bằng merge

```text
ERASE_MERGE(root, k):
    if root == NULL: return (NULL, false)

    if k < root.key:
        (root.left, found) = ERASE_MERGE(root.left, k)
        pull(root)
        return (root, found)

    if k > root.key:
        (root.right, found) = ERASE_MERGE(root.right, k)
        pull(root)
        return (root, found)

    replacement = MERGE(root.left, root.right)
    release_only_target(root)
    return (replacement, true)
```

So với xóa bằng quay:

| Khía cạnh | Xóa quay target xuống | Xóa bằng merge hai con |
| --- | --- | --- |
| Primitive chính | `rotate_left/rotate_right` | `merge` |
| Cách chọn con ưu tiên tốt | So priority hai con tại mỗi bước quay | So priority hai gốc trong recursion |
| Trạng thái heap tạm | Target ở dưới cha kém ưu tiên đến khi bị xóa | Merge dựng kết quả mới không còn target |
| Inorder sau xóa | Giữ tăng nghiêm ngặt | Giữ tăng nghiêm ngặt khi tiền đề key đúng |
| Metadata | `pull` sau quay và khi unwind | `pull` khi merge và khi unwind |
| Worst-case | O(n) | O(n) |
| Kỳ vọng theo mô hình random chuẩn | O(log n) cho thao tác | O(log n) cho thao tác |

Với cùng tập cặp `(key,priority)` có priority phân biệt, hình dạng treap cuối là **duy nhất** bởi hai bất biến. Vì vậy hai thuật toán đúng phải dẫn tới **cùng hình dạng cuối** khi xóa cùng key, mặc dù chuỗi bước trung gian khác nhau.

### 7.3. Chèn bằng `split+merge` là lựa chọn khác

Trong một hệ thống đã có `split(T,k) -> (A,B)` với các khóa A <k và B ≥k, có thể chèn node mới v sau khi xác minh k chưa tồn tại:

```text
(A, B) = SPLIT(root, k)
root = MERGE(MERGE(A, v), B)
```

Cách này thuận tiện khi triển khai xóa/chèn **theo dải** và implicit treap; nhưng bài này lấy **quay** làm primitive trung tâm để hiểu rõ hành vi con trỏ khi chèn/xóa một node.

**Chú ý:** split/merge sửa cây tại chỗ có thể làm invalid các iterator hoặc alias cũ; persistent treap cần path-copying thay vì sửa node được chia sẻ.

## 8. Chi phí chi tiết: đường tìm, số quay, stack, metadata

Đặt:

- `n` là số node.
- `h` là chiều cao theo **số node** của cây ở thời điểm thao tác.
- `r` là số phép quay đã thực hiện.
- `k` là số phần tử của một truy vấn dải nếu có.

Một lượt tìm target trong BST tốn **O(h)** thời gian, O(1) bộ nhớ phụ khi viết bằng vòng lặp.

Chèn bằng quay trên đường đệ quy có chi phí **O(h)** cho tìm vị trí/quay lại; `r≤h` (mỗi mức đường chèn cần nhiều nhất một phép quay ở code đệ quy). Một phép quay O(1), nên chi phí cập nhật liên kết không vượt O(h).

Xóa bằng quay tốn O(h) để tìm target và tối đa O(h_left+h_right) bước để đẩy target xuống (tương ứng đường ghép hai cây con); vì hai chiều cao đều ≤h, tổng **O(h)** theo bậc cho một thao tác. Metadata `size` được sửa O(1) tại mỗi mức/rotation.

| Thao tác | Theo chiều cao h | Kỳ vọng với priority IID hợp lệ | Trường hợp xấu |
| --- | --- | --- | --- |
| `contains(k)` | O(h) | O(log n) | O(n) |
| `insert(k)` bằng quay | O(h) | O(log n) | O(n) |
| `discard(k)` bằng quay | O(h) | O(log n) | O(n) |
| `discard(k)` bằng merge | O(h) | O(log n) | O(n) |
| `lower_bound(k)` | O(h) | O(log n) | O(n) |
| `rank/select` với size đúng | O(h) | O(log n) | O(n) |
| Inorder xuất đủ n khóa | O(n) | O(n) | O(n) |
| Range query xuất k khóa | O(h+k) | O(log n+k) | O(n+k) |

Nếu code `insert` kiểm tra khóa trùng bằng một lượt `contains` riêng, có thêm một đường tìm O(h), nhưng tổng vẫn O(h) theo bậc.

### 8.1. Bộ nhớ và stack

- Một node chứa key, priority, hai con trỏ, metadata size: **O(1) bộ nhớ/node**, tổng **O(n)**.
- `insert` và `erase` đệ quy dùng **O(h)** stack, O(log n) theo kỳ vọng trong mô hình chuẩn nhưng worst O(n).
- Một phép quay cục bộ chỉ cần **O(1)** bộ nhớ.
- Việc triển khai vòng lặp dùng stack/parent pointers có thể thay đổi chi phí bộ nhớ phụ và độ phức tạp code; không thay bất biến lý thuyết.

### 8.2. Kỳ vọng không phải chặn cứng

Với n khóa đã cố định độc lập với các priority IID liên tục, hình dạng treap tương đương một random BST; expected depth/height ở bậc O(log n).

Nhưng các priority có thể tăng theo key, tạo:

```text
(1,1)
   \
  (2,2)
     \
    (3,3)
       ...
         (n,n)
```

Treap vẫn đúng BST+heap và chiều cao là n. Một lần tìm/chèn/xóa có thể mất Θ(n). Không nên quảng bá “mọi thao tác O(log n)” nếu chỉ có expected bound.

### 8.3. Xóa “đụng nhiều node” không đồng nghĩa xóa nhiều khóa

Trong trace ở Mục 6, có ba phép quay và cập nhật size ở nhiều node. Dù nhiều liên kết đổi, **chỉ một node target bị loại**. Các con (10,20,30,50,60,70) vẫn phải tồn tại đúng một lần và giữ nguyên identity nếu API có con trỏ node.

Đây là tiêu chí quan trọng cho test có kiểm tra `size` và tập khóa sau mỗi lần xóa.


## 9. Python: treap set đầy đủ dùng quay cho cả chèn và xóa

Dưới đây là một implementation **Python 3.10+ tự chứa**, chỉ dùng thư viện chuẩn. Thay vì dùng split/merge trong phần lõi, chương trình **gọi trực tiếp các phép quay** để nhìn rõ hành vi sửa cây:

- `insert`: gắn lá theo BST, quay lên nếu con có priority tốt hơn cha.
- `discard`: tìm target, quay target xuống với con có priority tốt hơn, rồi gỡ khi target chỉ còn 0/1 con.
- `contains`, `lower_bound`, `predecessor`: tra cứu theo key.
- `rank/select`: dùng `subtree_size` được cập nhật sau mỗi thay đổi.
- `keys`, `range_keys`: duyệt theo thứ tự và phát hiện thay đổi qua API khi đang duyệt (best effort).
- `assert_valid`: kiểm tra BST, heap, size, identity và chu trình.

### 9.1. Node, cập nhật size, hai phép quay

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


def size_of(node: Node | None) -> int:
    return 0 if node is None else node.size


def pull(node: Node) -> None:
    """Cập nhật số node trong cây con từ hai con."""
    node.size = 1 + size_of(node.left) + size_of(node.right)


def rotate_right(y: Node) -> Node:
    """Trả gốc MỚI sau quay phải; y.left phải tồn tại."""
    assert y.left is not None

    x = y.left
    y.left = x.right
    x.right = y

    pull(y)  # y giờ nằm dưới x.
    pull(x)
    return x


def rotate_left(y: Node) -> Node:
    """Trả gốc MỚI sau quay trái; y.right phải tồn tại."""
    assert y.right is not None

    x = y.right
    y.right = x.left
    x.left = y

    pull(y)
    pull(x)
    return x
```

Node dùng `priority=(raw_random,serial)`, sắp xếp theo tuple để có **priority duy nhất** trong cùng một instance. `serial` không phải key; nó chỉ phân biệt những lần rút raw random trùng nhau.

### 9.2. `TreapSet` và thao tác chèn bằng quay

```python
class TreapSet:
    def __init__(self, seed: int | None = None) -> None:
        self._root: Node | None = None
        self._rng = random.Random(seed)
        self._serial = 0
        self._version = 0
        self.rotations = 0

    @staticmethod
    def _check_key(key: int) -> None:
        if type(key) is not int:
            raise TypeError("TreapSet chỉ nhận khóa int, không nhận bool")

    def _new_priority(self) -> tuple[int, int]:
        """Dùng PRNG để chọn thứ tự ưu tiên của node mới."""
        priority = (self._rng.getrandbits(128), self._serial)
        self._serial += 1
        return priority

    def __len__(self) -> int:
        return size_of(self._root)

    def contains(self, key: int) -> bool:
        self._check_key(key)
        current = self._root

        while current is not None:
            if key == current.key:
                return True
            current = current.left if key < current.key else current.right

        return False

    def lower_bound(self, key: int) -> int | None:
        """Key nhỏ nhất >= key; None nếu không có."""
        self._check_key(key)
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
        """Key lớn nhất < key; None nếu không có."""
        self._check_key(key)
        current = self._root
        candidate: Node | None = None

        while current is not None:
            if current.key < key:
                candidate = current
                current = current.right
            else:
                current = current.left

        return None if candidate is None else candidate.key

    def _insert_node(self, root: Node | None, fresh: Node) -> Node:
        """Vị trí BST trước, quay con có priority tốt lên."""
        if root is None:
            return fresh

        if fresh.key < root.key:
            root.left = self._insert_node(root.left, fresh)

            if root.left.priority < root.priority:
                root = rotate_right(root)
                self.rotations += 1

        elif fresh.key > root.key:
            root.right = self._insert_node(root.right, fresh)

            if root.right.priority < root.priority:
                root = rotate_left(root)
                self.rotations += 1

        else:
            # insert() đã kiểm tra trùng trước.
            raise AssertionError("Duplicate key lọt qua precheck")

        pull(root)
        return root

    def insert(self, key: int) -> bool:
        """True nếu thêm một khóa mới, False nếu bị trùng."""
        self._check_key(key)

        # Phép contains chỉ đọc, không đổi cây và không bốc random.
        if self.contains(key):
            return False

        fresh = Node(key, self._new_priority())
        self._root = self._insert_node(self._root, fresh)
        self._version += 1
        return True
```

Ở code này, `_insert_node` không gặp trường hợp duplicate vì `insert` đã kiểm tra; trong môi trường có cập nhật đồng thời, hai bước **contains rồi insert** không thể coi là atomic nếu thiếu khóa. Đoạn này chỉ hỗ trợ **tuần tự**.

Đếm `rotations` giúp kiểm tra các ví dụ quay. Nó là **tổng số quay từ khi tạo instance**, không phải số bước tìm kiếm và không reset sau mỗi thao tác. Muốn biết số quay của một thao tác, lấy **hiệu bộ đếm trước và sau**.

### 9.3. Xóa bằng quay và cập nhật gốc mới

```python
    def _erase_node(
        self, root: Node | None, key: int
    ) -> tuple[Node | None, bool]:
        if root is None:
            return None, False

        if key < root.key:
            root.left, removed = self._erase_node(root.left, key)
            pull(root)
            return root, removed

        if key > root.key:
            root.right, removed = self._erase_node(root.right, key)
            pull(root)
            return root, removed

        # Đã tìm thấy đúng node target mang key.
        if root.left is None:
            replacement = root.right
            root.right = None
            root.size = 1
            return replacement, True

        if root.right is None:
            replacement = root.left
            root.left = None
            root.size = 1
            return replacement, True

        # Target có hai con: đưa con ưu tiên tốt hơn lên,
        # đẩy chính target xuống, tiếp tục xóa target.
        if root.left.priority < root.right.priority:
            root = rotate_right(root)
            self.rotations += 1
            root.right, removed = self._erase_node(root.right, key)
        else:
            root = rotate_left(root)
            self.rotations += 1
            root.left, removed = self._erase_node(root.left, key)

        pull(root)
        return root, removed

    def discard(self, key: int) -> bool:
        """Xóa nếu có; False nếu khóa vắng."""
        self._check_key(key)
        self._root, removed = self._erase_node(self._root, key)

        if removed:
            self._version += 1
        return removed
```

**Vị trí các phương thức:** khối `_erase_node` và `discard` ở trên là phần **tiếp nối bên trong lớp `TreapSet`** của Mục 9.2, không phải hai hàm cấp module. Người học khi chép mã cần đặt chúng ở cùng cấp thụt 4 khoảng trắng với `insert`.

Giải thích các trường hợp xóa:

- Target có con trái rỗng: thay target bằng con phải (có thể là None).
- Target có con phải rỗng: thay target bằng con trái.
- Target có cả hai con: dùng comparator priority của **hai con**, không so target với con; quay theo hướng đã chọn và tiếp tục tìm đúng key target trong nhánh vừa chuyển.
- Sau recursion, gọi `pull(root)` để cập nhật metadata cây con còn lại.

Trong Python, việc tách `root.right=None` hoặc `root.left=None` trên node đã bị gỡ giúp không giữ alias không cần thiết qua node target. Nó **không** đồng nghĩa hủy cưỡng chế object nếu người dùng còn giữ reference; trong C/C++ phải quản lý vòng đời rõ hơn.

### 9.4. Rank, select và iterator inorder

```python
    def rank(self, key: int) -> int:
        """Số khóa nhỏ hơn key, kể cả khi key không tồn tại."""
        self._check_key(key)
        current = self._root
        result = 0

        while current is not None:
            if key <= current.key:
                current = current.left
            else:
                result += 1 + size_of(current.left)
                current = current.right

        return result

    def select(self, index: int) -> int:
        """Phần tử ở vị trí index tăng dần, đánh từ 0."""
        if type(index) is not int or not (0 <= index < len(self)):
            raise IndexError("select index ngoài phạm vi")

        current = self._root

        while current is not None:
            left_size = size_of(current.left)

            if index < left_size:
                current = current.left
            elif index == left_size:
                return current.key
            else:
                index -= left_size + 1
                current = current.right

        raise AssertionError("Metadata size sai hoặc thiếu node")

    def keys(self) -> Iterator[int]:
        """Sinh inorder; fail-fast nếu cập nhật qua API khi duyệt."""
        expected_version = self._version
        stack: list[Node] = []
        current = self._root

        while current is not None or stack:
            if self._version != expected_version:
                raise RuntimeError("Treap đã thay đổi trong lúc duyệt")

            while current is not None:
                stack.append(current)
                current = current.left

            current = stack.pop()
            yield current.key
            current = current.right

        if self._version != expected_version:
            raise RuntimeError("Treap đã thay đổi trong lúc duyệt")

    def range_keys(self, low: int, high: int) -> Iterator[int]:
        """Sinh [low,high) theo thứ tự tăng; không cấp list kết quả."""
        self._check_key(low)
        self._check_key(high)

        if low >= high:
            return

        expected_version = self._version
        stack: list[Node] = []
        current = self._root

        while current is not None or stack:
            if self._version != expected_version:
                raise RuntimeError("Treap đã thay đổi trong lúc duyệt")

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
            raise RuntimeError("Treap đã thay đổi trong lúc duyệt")
```

`rank` và `select` phụ thuộc **size của từng cây con**, không phải size toàn cây. Nếu quay mà quên `pull(y)`/`pull(x)`, cả hai có thể sai dù `contains` vẫn đúng.

`keys` và `range_keys` là generator. `expected_version` được ghi **khi generator bắt đầu được chạy bằng `next` lần đầu**, không phải lúc gọi hàm tạo generator. Đây chỉ là cơ chế fail-fast trong trường hợp tuần tự, không phải iterator snapshot hoặc bảo vệ đa luồng.

### 9.5. Validator: kiểm tra cả BST, heap, size, identity

```python
    def assert_valid(self) -> None:
        """Chỉ dùng debug/test: O(n) thời gian và bộ nhớ."""
        seen: set[Node] = set()

        def visit(
            node: Node | None,
            lower: int | None,
            upper: int | None,
            parent_priority: tuple[int, int] | None,
        ) -> int:
            if node is None:
                return 0

            assert node not in seen, "Cycle hoặc dùng lặp node"
            seen.add(node)

            assert type(node.key) is int
            assert lower is None or lower < node.key
            assert upper is None or node.key < upper
            assert (
                parent_priority is None
                or parent_priority < node.priority
            ), "Vi phạm min-heap"

            left_count = visit(
                node.left, lower, node.key, node.priority
            )
            right_count = visit(
                node.right, node.key, upper, node.priority
            )

            actual = 1 + left_count + right_count
            assert node.size == actual, "Sai subtree_size"
            return actual

        total = visit(self._root, None, None, None)
        assert total == len(self)
        assert total == len(seen)

    def height(self) -> int:
        """Đếm chiều cao bằng stack lặp, không theo đệ quy."""
        if self._root is None:
            return 0

        answer = 0
        stack = [(self._root, 1)]

        while stack:
            node, depth = stack.pop()
            answer = max(answer, depth)

            if node.left is not None:
                stack.append((node.left, depth + 1))
            if node.right is not None:
                stack.append((node.right, depth + 1))

        return answer
```

`assert_valid` chỉ nên chạy trong test/debug. Nó duyệt cả cây và dùng `seen` để bắt node trùng identity/chu trình; gọi validator sau mọi thao tác production sẽ khiến throughput không còn phản ánh độ phức tạp O(log n) kỳ vọng của chèn/xóa.

**Lưu ý `assert`:** Python có thể vô hiệu `assert` khi chạy với `-O`. Nếu validator được dùng làm rào chắn an toàn trong sản phẩm, cần dùng kiểm tra và exception tường minh, không dựa vào `assert`.

### 9.6. Chạy một ví dụ sử dụng

```python
def demo_treap() -> None:
    tree = TreapSet(seed=2026)

    for key in (40, 20, 60, 10, 30, 50, 70):
        assert tree.insert(key)

    tree.assert_valid()
    assert len(tree) == 7
    assert list(tree.keys()) == [10, 20, 30, 40, 50, 60, 70]

    assert tree.contains(30)
    assert not tree.contains(999)
    assert tree.lower_bound(35) == 40
    assert tree.predecessor(40) == 30

    assert tree.rank(30) == 2
    assert tree.rank(35) == 3
    assert tree.select(0) == 10
    assert tree.select(6) == 70
    assert list(tree.range_keys(15, 65)) == [20, 30, 40, 50, 60]

    assert not tree.insert(40)       # Không tạo khóa trùng.
    assert tree.discard(40)          # Xóa node có thể có hai con.
    assert not tree.discard(40)      # Xóa vắng: False.
    tree.assert_valid()

    assert list(tree.keys()) == [10, 20, 30, 50, 60, 70]
    assert len(tree) == 6

    for key in (10, 20, 30, 50, 60, 70):
        assert tree.discard(key)

    assert tree.height() == 0
    assert len(tree) == 0
    tree.assert_valid()
    print("Rotation-based TreapSet: OK")


if __name__ == "__main__":
    demo_treap()
```

**Cách ghép mã:** nối các khối 9.1–9.5 theo thứ tự vào **một file Python**. Các phương thức `_erase_node`, `discard`, `rank`, `select`, `keys`, `range_keys`, `assert_valid`, `height` đều cần thụt vào **bên trong lớp `TreapSet`**. Hàm `demo_treap` ở cấp module, không nằm trong lớp.

**Phạm vi:** ví dụ chỉ xử lý khóa `int` trong môi trường tuần tự. Không nên xem nó là thư viện concurrent, persistent, hay một cấu trúc có worst-case logarit cứng.


## 10. Test với priority cố định: kiểm chứng đúng từng phép quay

Một seed làm được tính tái lập, nhưng để **đảm bảo một đường quay cụ thể** xuất hiện, nên cho test cung cấp dãy priority cố định. Đây là cơ chế riêng của bài kiểm thử, **không** phải cơ chế để người dùng cuối tự chọn priority khi chương trình vận hành.

### 10.1. Lớp kế thừa thay nguồn priority, giữ nguyên logic treap

Đoạn dưới đây nối tiếp lớp `TreapSet` ở Mục 9:

```python
class ScriptedTreapSet(TreapSet):
    def __init__(self, raw_priorities: list[int]) -> None:
        super().__init__(seed=0)
        self._planned = iter(raw_priorities)

    def _new_priority(self) -> tuple[int, int]:
        raw = next(self._planned)
        answer = (raw, self._serial)
        self._serial += 1
        return answer


tree = ScriptedTreapSet([40, 60, 70, 10])

for key in (40, 20, 60):
    assert tree.insert(key)

assert tree.rotations == 0
assert tree._root is not None and tree._root.key == 40

assert tree.insert(30)
tree.assert_valid()

# Insert 30(P10) cần: quay trái tại 20,
# rồi quay phải tại 40.
assert tree.rotations == 2
assert tree._root is not None and tree._root.key == 30
assert list(tree.keys()) == [20, 30, 40, 60]
assert len(tree) == 4

before = tree.rotations
assert tree.discard(30)

# Target có hai con, chỉ cần một phép quay để
# chuyển target xuống rồi nối con còn lại.
assert tree.rotations == before + 1
tree.assert_valid()
assert list(tree.keys()) == [20, 40, 60]
```

Lý do chèn trùng không tiêu thụ một priority có sẵn: `TreapSet.insert` gọi `contains` và trả False trước khi gọi `_new_priority`. Một test có dãy priority ngắn có thể phát hiện việc thay đổi chính sách này.

### 10.2. Test chính xác ba phép quay khi xóa gốc

Trace ở Mục 6 có các cặp:

```text
key:       40   20   60   10   30   50   70
priority:  10   30   20   80   60   70   90
```

Test:

```python
tree = ScriptedTreapSet([10, 30, 20, 80, 60, 70, 90])

for key in (40, 20, 60, 10, 30, 50, 70):
    assert tree.insert(key)

tree.assert_valid()
assert tree.rotations == 0
assert tree._root is not None and tree._root.key == 40

before = tree.rotations
assert tree.discard(40)

assert tree.rotations - before == 3
assert tree._root is not None and tree._root.key == 60
assert list(tree.keys()) == [10, 20, 30, 50, 60, 70]
assert len(tree) == 6
tree.assert_valid()
```

Bài test không chỉ so kết quả cuối cùng mà còn so **số phép quay của tình huống đã được mô phỏng bằng tay**. Nếu code lỡ chọn con có priority kém hơn khi xóa, validator hoặc bộ đếm có khả năng phát hiện sai sót.

### 10.3. Test khóa trùng không bốc priority tiếp

```python
tree = ScriptedTreapSet([30, 50])

assert tree.insert(20)       # Dùng priority raw 30.
assert not tree.insert(20)   # Trùng: không dùng priority raw 50.
assert tree.insert(10)       # Dùng priority raw 50.

assert len(tree) == 2
assert tree._root is not None and tree._root.key == 20
tree.assert_valid()
```

Nếu đổi `insert` thành “bốc priority rồi mới kiểm tra khóa trùng”, bài test có thể hết nguồn dữ liệu hoặc tạo hình dạng khác. Chính sách không tiêu thụ random ở thao tác thất bại giúp việc debug tái lập dễ hiểu hơn, dù không phải mọi thư viện treap đều buộc phải chọn chính sách ấy.

## 11. Test đối chiếu với `set`: tính đúng không phụ thuộc random

Một randomized structure cần có **tính đúng với mọi priority hợp lệ**, chứ không chỉ với seed may mắn. Ta có thể dùng `set` Python làm mô hình nội dung, `sorted` làm mô hình thứ tự, và kiểm tra **sau mỗi update**.

### 11.1. Chuỗi thao tác có seed tái lập

```python
import random


def test_reference(seed: int) -> None:
    workload = random.Random(10000 + seed)
    tree = TreapSet(seed=seed)
    expected: set[int] = set()

    for step in range(300):
        key = workload.randrange(-50, 51)
        action = workload.randrange(3)

        if action == 0:
            should_insert = key not in expected
            assert tree.insert(key) == should_insert
            expected.add(key)

        elif action == 1:
            should_remove = key in expected
            assert tree.discard(key) == should_remove
            expected.discard(key)

        else:
            assert tree.contains(key) == (key in expected)

        tree.assert_valid()
        ordered = sorted(expected)

        assert len(tree) == len(expected)
        assert list(tree.keys()) == ordered

        if step % 25 == 0:
            for probe in (-60, -25, 0, 25, 60):
                smaller = [x for x in ordered if x < probe]
                greater_equal = [x for x in ordered if x >= probe]

                assert tree.rank(probe) == len(smaller)
                assert tree.predecessor(probe) == (
                    smaller[-1] if smaller else None
                )
                assert tree.lower_bound(probe) == (
                    greater_equal[0] if greater_equal else None
                )

            for index, value in enumerate(ordered):
                assert tree.select(index) == value

            assert list(tree.range_keys(-20, 20)) == [
                x for x in ordered if -20 <= x < 20
            ]


for seed in range(10):
    test_reference(seed)
```

Hai bộ RNG riêng giúp việc chọn **thao tác kiểm thử** không phụ thuộc vào các lần rút priority bên trong treap. Một thay đổi trong số lượt bốc priority có thể đổi hình dạng, nhưng vẫn không được làm sai tập khóa logic.

### 11.2. Test thứ tự chèn đặc biệt

```python
def test_orderings() -> None:
    base = list(range(-40, 40))
    orderings = [
        base,
        list(reversed(base)),
        base[::2] + base[1::2],
    ]

    for seed, order in enumerate(orderings):
        tree = TreapSet(seed=100 + seed)

        for key in order:
            assert tree.insert(key)

        tree.assert_valid()
        assert list(tree.keys()) == base

        # Xóa theo thứ tự đối lập với thứ tự chèn.
        for key in reversed(order):
            assert tree.discard(key)

        tree.assert_valid()
        assert len(tree) == 0
        assert list(tree.keys()) == []


test_orderings()
```

Nếu một bản chèn chỉ hoạt động khi đầu vào random, nó không phải treap set đúng. Random priority giúp **hiệu năng kỳ vọng**, không phải điều kiện cho tính đúng.

### 11.3. Kiểm thử mọi hoán vị priority nhỏ

Với một tập **5 khóa cố định** và priority `1,2,3,4,5` phân biệt, có đúng `5!=120` thứ tự ưu tiên tương đối. Có thể thử hết chúng:

```python
from itertools import permutations


def exhaustive_small_test() -> None:
    keys = [10, 20, 30, 40, 50]

    for prios in permutations(range(1, 6)):
        tree = ScriptedTreapSet(list(prios))

        # Cố định thứ tự chèn tăng dần.
        for key in keys:
            assert tree.insert(key)

        tree.assert_valid()
        assert list(tree.keys()) == keys

        # Xóa cả gốc / node giữa / node biên theo nhiều bước.
        for key in (30, 10, 50, 20, 40):
            assert tree.discard(key)
            tree.assert_valid()

        assert len(tree) == 0


exhaustive_small_test()
```

Thử 120 hoán vị không thay thế chứng minh cho mọi n, nhưng bao phủ nhiều hình dạng và nhiều đường quay **với n nhỏ**. Nó mạnh hơn chỉ chạy một seed rồi thấy chương trình “có vẻ ổn”.

### 11.4. Test thất bại và dữ liệu biên

```python
tree = TreapSet(seed=3)

assert not tree.discard(0)
assert tree.lower_bound(0) is None
assert tree.predecessor(0) is None
assert tree.rank(0) == 0

for key in (-10, 0, 10):
    assert tree.insert(key)

assert not tree.insert(0)
assert not tree.discard(999)
assert list(tree.keys()) == [-10, 0, 10]

assert tree.lower_bound(-11) == -10
assert tree.lower_bound(0) == 0
assert tree.lower_bound(11) is None
assert tree.predecessor(-10) is None
assert tree.predecessor(0) == -10
assert tree.predecessor(11) == 10

assert tree.select(0) == -10
assert tree.select(2) == 10
tree.assert_valid()

for bad in (-1, 3):
    detected = False

    try:
        tree.select(bad)
    except IndexError:
        detected = True

    assert detected, "select ngoài biên phải báo IndexError"
```

Không bắt `AssertionError` do **chính test cố tình `raise`** rồi nhầm là validator đã phát hiện lỗi. Cách dùng cờ `detected` khiến test chỉ chấp nhận đúng exception của phương thức đang kiểm tra.

## 12. C: quay trái/phải khi caller phải cập nhật con trỏ gốc

Trong C, một lỗi thường gặp là sửa xong con trỏ nội bộ nhưng quên đổi root ở **bên gọi**. Ví dụ dưới đây dùng **con trỏ tới con trỏ** `Node **link` để thể hiện rõ nơi phải ghi root mới, đồng thời cập nhật subtree_size.

Mã C11 này là **ví dụ độc lập**: các node được khai báo trên stack, không dùng `malloc/free`. Chúng chỉ sống đến cuối hàm `main`.

```c
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

typedef struct Node {
    int key;
    uint64_t priority;
    size_t size;
    struct Node *left;
    struct Node *right;
} Node;

static size_t node_size(const Node *p) {
    return p == NULL ? 0u : p->size;
}

static void pull(Node *p) {
    assert(p != NULL);
    p->size = 1u + node_size(p->left) + node_size(p->right);
}

/* link là địa chỉ của root, hoặc địa chỉ ô child của cha. */
static void rotate_right(Node **link) {
    Node *y = *link;
    assert(y != NULL && y->left != NULL);

    Node *x = y->left;
    y->left = x->right;
    x->right = y;
    *link = x;          /* Ghi root MỚI vào bên gọi. */

    pull(y);
    pull(x);
}

static void rotate_left(Node **link) {
    Node *y = *link;
    assert(y != NULL && y->right != NULL);

    Node *x = y->right;
    y->right = x->left;
    x->left = y;
    *link = x;

    pull(y);
    pull(x);
}

int main(void) {
    /* Node 30(p10) phải được chèn dưới 20 rồi đưa lên.
       Dựng trạng thái ĐÃ nối lá tại vị trí BST. */
    Node n30 = {
        .key=30, .priority=10, .size=1,
        .left=NULL, .right=NULL
    };
    Node n20 = {
        .key=20, .priority=60, .size=2,
        .left=NULL, .right=&n30
    };
    Node n60 = {
        .key=60, .priority=70, .size=1,
        .left=NULL, .right=NULL
    };
    Node n40 = {
        .key=40, .priority=40, .size=4,
        .left=&n20, .right=&n60
    };

    Node *root = &n40;

    /* Sửa heap tại cạnh 20 -> 30 bằng quay trái
       tại con trái của root; root chính vẫn là 40. */
    rotate_left(&root->left);
    assert(root == &n40);
    assert(root->left == &n30);
    assert(n20.size == 1);
    assert(n30.size == 2);

    /* Sửa tiếp heap tại cạnh 40 -> 30 bằng quay phải
       tại chính root toàn treap. */
    rotate_right(&root);
    assert(root == &n30);
    assert(root->left == &n20);
    assert(root->right == &n40);
    assert(n40.right == &n60);
    assert(n40.size == 2);
    assert(n30.size == 4);

    /* Các cạnh của min-heap và BST đều đúng. */
    assert(n30.priority < n20.priority);
    assert(n30.priority < n40.priority);
    assert(n40.priority < n60.priority);
    assert(n20.key < n30.key && n30.key < n40.key);
    assert(n40.key < n60.key);

    puts("Pointer-to-pointer treap rotations: OK");
    return 0;
}
```

**Tại sao dùng `Node **link`?** Khi quay cây con là `parent.left`, gọi `rotate_left(&parent.left)` sẽ ghi gốc mới trực tiếp vào ô đó. Khi quay root toàn cây, gọi `rotate_right(&root)` để biến gốc ngoài theo đúng kết quả. Nếu quên `*link=x`, những node đã đổi con trỏ có thể không còn được truy cập đúng qua root cũ.

### 12.1. Rủi ro của `assert` trong C

Các lời gọi quay **không** được đặt làm biểu thức có side effect bên trong `assert(...)`, vì khi biên dịch với `NDEBUG`, macro `assert` có thể bị loại và phép quay **không chạy**.

Trong ví dụ, quay được gọi **trực tiếp**, còn `assert` chỉ dùng xác minh sau thao tác. Trong production, nếu không thể tin tiền điều kiện `y!=NULL` và con cần quay tồn tại, nên kiểm tra trả mã lỗi hoặc dùng hợp đồng API rõ, không chỉ dựa vào assert debug.

### 12.2. Quy tắc vòng đời khi code C có cấp phát động

Nếu treap thật dùng `malloc` để tạo node:

1. Chèn: cấp và khởi tạo node trước khi gắn vào cây. Nếu cấp phát thất bại, trả lỗi, giữ cây ban đầu.
2. Xóa: giữ con trỏ con còn lại (hoặc merge hai cây con) **trước** khi `free(target)`.
3. Đổi con trỏ từ cha hoặc root tới replacement.
4. Chỉ `free(target)` **một lần**; không `free` các con được nối lại vào cây.
5. Không đọc `target->left/right` hoặc metadata sau khi đã `free`.
6. Iterator hoặc một luồng khác còn giữ `Node *target` có thể bị dangling; cần hợp đồng invalidation và memory reclamation.

Các node trong `main` của ví dụ đang ở stack và **không được `free`**; cố ý tách minh họa phép quay khỏi việc cấp phát để người học tập trung vào lỗi con trỏ.


## 13. Chứng minh hậu điều kiện cho chèn và xóa

Một thao tác đúng không chỉ trả `True` hay `False`, mà còn phải bảo toàn **các bất biến cấu trúc**. Ta xét các tiền điều kiện và hậu điều kiện đủ để kiểm tra code độc lập với seed.

### 13.1. Hợp đồng chèn một khóa `k`

**Tiền điều kiện:**

- Treap đầu vào hợp lệ theo BST/heap.
- Comparator khóa tạo thứ tự toàn phần nhất quán.
- Priority của node mới khác các priority hiện có theo comparator đang dùng.
- Không có cập nhật đồng thời không đồng bộ.

**Nếu k đã có:**

\[
S_{\rm after}=S_{\rm before},
\]

API set trả False, không tạo node hay tiêu thụ priority theo chính sách bài.

**Nếu k chưa có:**

\[
S_{\rm after}=S_{\rm before}\cup\{k\}.
\]

Inorder vẫn tăng nghiêm ngặt; priority cha tốt hơn con, metadata size đúng, và `len(after)=len(before)+1`.

**Lập luận:** chèn như BST bảo toàn thứ tự khóa. Những phép quay bảo toàn inorder. Mỗi vi phạm heap bắt đầu từ node mới được gắn lá; quay trên đường từ node ấy lên sửa vi phạm ở một cạnh, rồi xử lý tiếp cạnh với cha mới. Sau khi không còn vi phạm, treap hoàn tất.

### 13.2. Hợp đồng xóa một khóa `k`

**Tiền điều kiện** tương tự: treap đầu vào hợp lệ, comparator đúng, các thao tác chỉ chạy tuần tự hoặc được đồng bộ.

**Nếu k vắng:**

\[
S_{\rm after}=S_{\rm before}.
\]

API trả False; không có node nào phải bị loại.

**Nếu k có:**

\[
S_{\rm after}=S_{\rm before}\setminus\{k\}.
\]

Các node khác giữ lại; inorder tăng, heap đúng, size giảm 1.

**Lập luận:** phép quay luôn bảo toàn inorder và tập node. Khi target có hai con, chọn con có priority tốt hơn để đưa lên tương ứng cách dựng `merge` trên hai cây con. Mỗi bước đưa target xuống và vẫn giữ mọi node không phải target. Khi target có tối đa một con, nối thẳng con còn lại là phép gỡ BST hợp lệ; target được hủy. Heap sau cùng đúng do mỗi lần chọn gốc theo priority tốt nhất giữa các cây con còn sống.

### 13.3. Tại sao không được kiểm tra heap giữa chừng khi xóa quay?

Sau lần quay đầu khi xóa root có priority nhỏ nhất, node vừa được đưa lên **có priority lớn hơn target**. Kết quả tạm thời không thỏa heap tại cạnh vào target, dù thuật toán vẫn đang đúng hướng.

Một validator gọi **giữa các bước quay** sẽ báo sai — điều đó không tự chứng minh thuật toán xóa sai. Validator phải chạy **sau khi target đã bị gỡ hoàn toàn và các size đã được cập nhật**.

Ngược lại, nếu thao tác kết thúc mà vẫn có một cạnh priority ngược, thì code thực sự sai. Các bước quay là thao tác trung gian nằm trong một **giao dịch logic** của phép xóa.

### 13.4. Metadata `size` phải đúng sau quay và sau đường đệ quy

Ví dụ một cây con trước quay phải:

```text
           y (size = 1 + |A| + |B| + 1 + |C|)
          / \
         x   C
        / \
       A   B
```

Sau quay:

```text
             x
            / \
           A   y
              / \
             B   C
```

Kích thước:

\[
size(y)_{\rm after}=1+|B|+|C|,
\]
\[
size(x)_{\rm after}=1+|A|+size(y)_{\rm after}.
\]

Vì vậy phải `pull(y)` **trước** `pull(x)`. Các metadata tổng hợp khác như `subtree_sum`, `subtree_min/max` cũng có thể được bảo trì tương tự nếu toán tử tổng hợp và các quy tắc biến đổi được định nghĩa đầy đủ.

## 14. Lỗi phổ biến khi sửa treap

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Tìm vị trí chèn dựa theo priority thay vì key | Không còn BST | Chỉ định vị theo key |
| Dùng phép so heap trái chiều giữa insert/delete | Phá heap sau thao tác | Chọn min-heap hoặc max-heap nhất quán |
| Dùng `rotate_left` khi con trái cần được đưa lên | Sai hình dạng, có thể thiếu child | Con trái lên bằng rotate_right |
| Quên thay `root=rotate...` | Gốc bên ngoài trỏ tới cây cũ | Trả gốc mới hoặc dùng `Node **link` |
| Quay nhưng đặt `y.left=x.left` thay vì `x.right` | Mất hoặc lặp cây B | Theo sơ đồ ba cây A,B,C |
| Cập nhật `pull(parent)` trước `pull(child)` | Metadata size sai | Tính node nằm dưới trước |
| Chèn trùng nhưng vẫn tạo node | Tập có key trùng | Precheck hoặc chính sách multiset |
| Khi xóa hai con, chỉ nối một con rồi bỏ con kia | Mất nhiều khóa | Quay target xuống hoặc merge hai con |
| Khi xóa hai con, chọn child priority kém hơn | Kết quả có thể phá heap | Đưa child có priority tốt nhất lên |
| Khi xóa, yêu cầu heap phải đúng ngay sau từng quay | Phản đối nhầm một bước trung gian hợp lệ | Cho phép vi phạm chỉ trên target sắp gỡ |
| Khi xóa, tiếp tục đệ quy vào gốc mới thay vì node target cũ | Xóa nhầm hoặc không xóa target | Theo nhánh chứa target sau quay |
| Xóa một node nhưng giảm size theo số lần quay | `len` sai | Mỗi target là một khóa, giảm 1 |
| Lấy priority mới khi xóa target | Thay hình dạng và hợp đồng ngẫu nhiên | Xóa theo priority đã có |
| Trộn tuple priority với raw priority khi so | Tie-break không nhất quán | Dùng một comparator cho mọi thao tác |
| `merge` hai cây có khóa xen kẽ | Phá BST | Chỉ merge khi max(left)<min(right) |
| Xóa target rồi `free` cả cây con còn sống | Mất dữ liệu, double free | Chỉ hủy chính target |
| Dùng con trỏ target sau `free` | Use-after-free | Lưu successor/children trước free |
| Dùng iterator đang duyệt sau phép quay mà không có hợp đồng | Trùng/bỏ sót key | Version, snapshot, lock |
| Chạy validator O(n) trên mọi update production | Phá hiệu năng kỳ vọng | Chỉ test/debug theo chính sách |
| Thấy expected O(log n) rồi hứa worst O(log n) | Rủi ro latency và stack | Nêu worst O(n), xem AVL/RB |
| Đặt priority bằng key | Cây lệch tất định trên input sorted | Priority ngẫu nhiên độc lập với key |
| Benchmark một seed rồi kết luận tất cả seed | Bỏ qua đuôi phân phối | Nhiều seed và phân tích xác suất |
| Bỏ qua `RecursionError` giữa một phép sửa tại chỗ | Cấu trúc có thể đang sửa dở | Giới hạn sâu, iteration, transaction |
| Chèn/xóa đa luồng chỉ bằng khóa GIL hoặc version | Có thể thấy trạng thái trung gian | Đồng bộ/read snapshot, contract rõ |

### 14.1. Debug bằng một log thay đổi liên kết

Đối với khóa k đang làm lỗi, ở mỗi bước ghi:

```text
action = INSERT / ERASE
key = k
root_before = (key,priority,size)
direction = LEFT / RIGHT
rotate = LEFT / RIGHT / NONE
root_after = (key,priority,size)
inorder_after = [...]
```

Với `insert`, xem node mới có đi theo đúng nhánh BST trước quay hay không. Với `erase`, log **identity của target** để chắc mỗi bước quay tiếp tục đẩy đúng target xuống.

**Không chỉ so hai kết quả `contains(k)`**: một treap có thể tìm đúng nhiều key trong khi bị sai heap hoặc `size`, và chỉ hỏng ở các update sau. Inorder, heap validator và size validator đều cần có mặt trong test.

### 14.2. Nếu code sai ngay sau quay

Kiểm tra theo thứ tự:

1. `x` có thật là con đúng phía của `y` không?
2. Cây **B** ở giữa hai khóa x và y có được giữ nguyên và chuyển sang đúng ô child không?
3. Bên gọi đã cập nhật root cây con chưa?
4. Cây con dưới được `pull` trước cây con trên chưa?
5. Phép quay có đúng mục đích **chèn đưa node lên** hoặc **xóa đẩy target xuống** không?
6. Nếu lỗi chỉ xuất hiện sau xóa hoàn tất, đã theo đúng node target qua từng lần quay chưa?

### 14.3. Các ca cần test cho xóa

- Xóa một node duy nhất để treap rỗng.
- Xóa lá, node một con, node hai con.
- Xóa root đang có cả hai con.
- Xóa liên tục từ khóa nhỏ nhất đến lớn nhất, và ngược lại.
- Xóa lại cùng key sau khi đã xóa (trả False).
- Xóa key vắng ở giữa hai khóa có thật.
- Xóa khiến cây con bị thay gốc nhiều lần.
- Xóa ngay sau khi một node vừa được quay lên thành root.
- Dùng priority đã định để buộc chọn **trái** rồi **phải** trong một quá trình xóa.
- Kiểm tra kích thước, inorder, heap và `rank/select` sau từng bước.

## 15. Quản lý vòng đời, lỗi runtime và cập nhật đồng thời

### 15.1. Đệ quy có thể vượt stack trong trạng thái xấu

Treap có expected height O(log n) khi priority phù hợp, nhưng một kết quả ngẫu nhiên xấu có thể tạo cây đường dài `h=n`. Với implementation `_insert_node`/`_erase_node` đệ quy:

- Stack cần O(h) lời gọi.
- Python có giới hạn độ sâu đệ quy hữu hạn.
- Một `RecursionError` có thể xảy ra **sau khi vài liên kết đã bị đổi**.
- Nếu không có rollback, không thể mặc nhiên coi treap vẫn nguyên vẹn.

Do đó mã trong Mục 9 là **mã học thuật** nhằm giải thích phép quay. Hệ thống cần độ tin cậy cao phải lựa chọn một trong các phương án: cài đặt lặp với stack tường minh/parent pointers, một cấu trúc có chặn chiều cao cứng, hoặc hợp đồng phục hồi lỗi/transaction rõ ràng.

### 15.2. `insert` có hai bước đọc rồi ghi

Cài đặt `insert` gọi `contains` để phát hiện duplicate, rồi mới bốc priority và gọi `_insert_node`. Trong một chương trình **đa luồng**, nếu thread khác chèn key giữa hai bước này, điều kiện “key chưa tồn tại” có thể không còn đúng.

- Với mô hình tuần tự, điều này an toàn.
- Với concurrent treap, phải có **mutex/transaction** hoặc thuật toán đồng bộ riêng.
- `_version` chỉ là công cụ phát hiện một số thay đổi khi duyệt, **không phải lock**.
- GIL của một runtime không tự cung cấp một hợp đồng atomic cho toàn bộ nhiều bước thao tác trên mọi implementation Python.

### 15.3. Iterator không phải snapshot

Iterator inorder thường giữ stack các node trên đường duyệt. Khi một node bị quay hoặc xóa, đường liên kết thay đổi. Nếu iterator vẫn dùng đường cũ, nó có thể:

- Bỏ sót node.
- Xuất một node nhiều lần.
- Theo một node đã rời set.
- Với C/C++, đọc một địa chỉ đã free.

Ví dụ Python `keys` trong bài kiểm tra version ở mỗi lần lấy phần tử; nếu có update thành công thông qua API, nó báo lỗi khi tiếp tục. Đây là **best-effort fail-fast** trong môi trường tuần tự; nó không bảo đảm một snapshot nguyên tử hay an toàn đa luồng.

Muốn duyệt ổn định qua update, có thể dùng **snapshot** (tạo list keys trước, dùng thêm O(n) bộ nhớ), **persistent treap** có path-copying, hoặc giữ lock đủ lâu để duyệt.

### 15.4. Concurrent rotations phức tạp hơn chỉ gán pointer atomic

Một phép quay đổi ít nhất hai cạnh và gốc cây con; còn có metadata `size`. Một luồng đọc có thể nhìn thấy các thay đổi giữa chừng nếu không đồng bộ.

Concurrent treap thực sự cần các quy tắc về:

- Điểm **linearization** của insert/delete/read.
- Memory ordering và các atomic operations thích hợp.
- Ownership node trong quá trình quay/gỡ.
- Hazard pointers, epoch reclamation hoặc cơ chế tương đương nếu dùng node cấp phát động.
- Iterator consistency và phiên bản cây.

**Không được** coi việc thay con trỏ thường thành CAS ở một chỗ là đủ để tạo treap lock-free đúng.

### 15.5. Strong exception safety không tự có

Nếu phép so sánh khóa, cấp phát, lời gọi đệ quy hoặc xử lý con trỏ phát sinh lỗi sau một số gán liên kết, trạng thái treap có thể đã bị sửa. Mã học thuật không cung cấp rollback tự động.

Một API production cần chọn rõ:

- **Basic guarantee:** object còn hợp lệ theo một hợp đồng được xác định sau lỗi.
- **Strong guarantee:** thao tác hoặc hoàn tất, hoặc trạng thái logic ban đầu được giữ.
- **No-throw:** chỉ khi mọi phép cần thiết đã được chứng minh không ném.

Để có strong guarantee, có thể dùng persistent/path-copying rồi chỉ công bố root mới sau khi hoàn thành, hoặc cơ chế rollback có kiểm thử. Đừng tuyên bố strong guarantee chỉ vì đã cấp node mới trước thao tác.

### 15.6. Seed tái lập không phải chứng minh performance

`random.Random(seed)` giúp lặp lại lỗi trên một hình dạng cụ thể, không bảo mật random và không tạo worst-case O(log n). Nếu đối thủ có thể đoán priority hoặc chọn khóa theo trạng thái đã lộ, chứng minh expected cho khóa đã cố định độc lập với priority có thể không áp dụng nguyên xi.

**Tư duy thiết kế:** hiệu năng expected đến từ một mô hình xác suất; tính đúng của BST/heap phải giữ với **mọi** priority hợp lệ; an toàn đồng thời và hồi phục lỗi lại cần hợp đồng bổ sung.

## 16. Chọn quay hay split/merge cho ứng dụng?

| Nhu cầu | Chèn/xóa bằng quay | Chèn/xóa bằng split/merge |
| --- | --- | --- |
| Dạy sửa con trỏ cục bộ và các phép cân chỉnh | Trực quan | Gọn nhưng ít lộ chuyển động từng cạnh |
| Dùng API BST có `rotate_left/right` sẵn | Thuận tiện | Cần primitive mới |
| Xóa một key | Đẩy target xuống rồi gỡ | Merge hai cây con, gỡ target |
| Tách cây theo ngưỡng key | Cần viết thêm split | Split là primitive chính |
| Ghép hai dải key đã phân tách | Cần viết merge | Merge là primitive chính |
| Range update, implicit treap | Cần bổ sung nhiều logic | Thường thuận tiện hơn |
| Bảo đảm expected | O(log n) với mô hình random đúng | O(log n) với mô hình random đúng |
| Worst-case | O(n) | O(n) |
| Exception/ownership | Cần xử lý | Cũng cần xử lý, nhất là split mutating |

**Không có cách nào “luôn nhanh hơn” chỉ dựa vào tên primitive.** Thực tế phụ thuộc cache, allocator, chi phí so sánh khóa, recursion, cách bảo trì metadata và workload.

### 16.1. Khi cần deadline worst-case cứng

Nếu hợp đồng yêu cầu tìm/chèn/xóa theo key có **O(log n) worst-case** cho mọi trạng thái hợp lệ, hãy ưu tiên cây AVL, red-black hoặc cấu trúc khác đã chứng minh giới hạn chiều cao. Treap với priority ngẫu nhiên thông thường **chỉ có O(log n) kỳ vọng**, không biến thành cây cân bằng cứng vì ta chọn một thuật toán xóa khác.

### 16.2. Khi muốn cập nhật dải hoặc duy trì phiên bản

Treap có ưu thế thuật toán là các phép split/merge diễn đạt tự nhiên các thao tác dải. Một **implicit treap** dùng subtree size để định vị theo chỉ số, còn treap set bài này định vị theo key. Với **persistent treap**, không được áp dụng các primitive mutating trực tiếp lên node chia sẻ; cần path-copy/immutable nodes.

Những biến thể này vẫn dựa trên cùng hai bất biến BST/heap (hoặc thứ tự dãy theo rank ở implicit treap) và yêu cầu duy trì metadata chính xác sau mọi phép biến đổi.


## 17. Bài tập thực hành có lời giải

### Bài 1. Phân biệt key và priority

Treap có root `(key=40,priority=10)`, muốn tìm key=20. Bạn dùng key hay priority để quyết định nhánh? Priority của root có cho biết đó là key nhỏ nhất không?

**Lời giải:** Dùng **key**: vì 20<40 nên đi trái. Priority 10 chỉ cho biết root có ưu tiên tốt nhất theo heap, **không** có nghĩa key40 là khóa nhỏ nhất. Key nhỏ nhất được tìm bằng đường cực trái BST.

### Bài 2. Kiểm tra hai bất biến

Cây:

```text
        (30,10)
        /     \
   (20,40)  (50,20)
```

Có đúng BST và min-heap không?

**Lời giải:** Đúng BST vì `20<30<50`, và đúng min-heap vì `10<40` và `10<20`. Priority không cần tăng theo inorder, chỉ cần tăng theo **cạnh cha–con**.

### Bài 3. Một cây đúng BST nhưng sai heap

Root `(30,50)` có con trái `(20,10)`. Bất biến nào sai và quay hướng nào có thể sửa?

**Lời giải:** BST đúng vì 20<30, min-heap sai vì 50>10 ở cạnh cha–con. **Quay phải tại 30** đưa node20(priority10) lên trên. Với cây chỉ hai node, kết quả đúng cả BST và heap.

### Bài 4. Một cây đúng heap nhưng sai BST

Root `(30,10)` có con trái `(40,20)`. Có thể xem đây là treap hợp lệ không?

**Lời giải:** Không. Heap đúng vì 10<20, nhưng BST sai vì key40 lớn hơn key30 lại nằm bên trái. Chỉ đúng heap là **không đủ**. Không thể sửa lỗi này chỉ bằng cách đổi comparator priority; cần đặt lại liên kết theo key.

### Bài 5. Quay phải: cây B chuyển đi đâu?

Trước quay phải tại y, x=y.left và B=x.right. Sau quay phải, B là cây con nào của node nào?

**Lời giải:** **B trở thành `y.left`**, trong khi `x.right=y`. X là gốc mới của cây con. Lý do: mọi key trong B nằm giữa x.key và y.key, nên B phải ở bên trái y nhưng bên phải x theo inorder.

### Bài 6. Quay trái: cây B chuyển đi đâu?

Trước quay trái tại y, x=y.right và B=x.left. Sau quay trái, B là cây con nào?

**Lời giải:** **B trở thành `y.right`**, còn `x.left=y`. B có key lớn hơn y nhưng nhỏ hơn x, đúng vị trí mới dưới y.

### Bài 7. Vì sao một phép quay là O(1)?

Một lần quay có thể làm đổi gốc cây con. Có phải chi phí quay tăng theo tổng số node trong các cây A,B,C không?

**Lời giải:** Không. Các cây con A,B,C được giữ qua **con trỏ gốc**, không cần duyệt phần tử. Quay chỉ sửa một số con trỏ và cập nhật metadata ở vài node, nên thời gian O(1), bộ nhớ phụ O(1) theo mô hình pointer.

### Bài 8. Không cập nhật root sau quay

Một hàm quay phải trả con trỏ x mới, nhưng caller vẫn giữ root=y cũ. Vấn đề nào có thể xảy ra?

**Lời giải:** Caller không còn tham chiếu đúng **gốc cây con**; có thể bỏ sót node x hoặc quản lý sai đường liên kết khi tiếp tục thao tác. Phải gán `root=rotate_right(root)` hoặc dùng `Node **link` để ghi trực tiếp vào ô root/child của cha.

### Bài 9. Thứ tự cập nhật size sau quay

Quay phải tại y đưa x lên trên. Nên tính `pull(y)` hay `pull(x)` trước?

**Lời giải:** **`pull(y)` trước**, rồi `pull(x)`. Vì y trở thành con dưới của x, size mới của x phụ thuộc vào size mới của y.

### Bài 10. Chèn khóa theo BST

Cây có root key40, con trái key20, con phải key60. Chèn key30 lần đầu, vị trí lá BST ban đầu ở đâu?

**Lời giải:** Đi `40→20`, vì 30<40 và 30>20. Node mới được nối làm **con phải của key20**. Sau đó mới xét priority để quyết định quay.

### Bài 11. Chèn node có priority tốt nhất

Với cây ở Bài 10: root `(40,40)`, con trái `(20,60)`, con phải `(60,70)`. Chèn `(30,10)` cần các phép quay nào?

**Lời giải:** Ban đầu nối `30` bên phải `20`. Vì `10<60`, quay **trái tại 20**. Vì `10<40`, quay **phải tại 40**. Kết quả root là `(30,10)`, inorder `20,30,40,60`. Tổng **2 phép quay**.

### Bài 12. Chèn node có priority kém hơn cha

Cây có root `(40,10)`, con phải `(60,30)`. Chèn `(50,90)` vào đâu và cần quay không?

**Lời giải:** Đặt `(50,90)` làm con **trái của 60** vì 40<50<60. Do `30<90`, min-heap với cha 60 đã đúng; **không cần quay**. Vẫn phải cập nhật size theo đường 60→40.

### Bài 13. Chèn vào cây rỗng

Treap rỗng, thêm `(20,100)`. Root mới và số phép quay là gì?

**Lời giải:** Root là node20, không có phép quay. BST và heap đúng một cách hiển nhiên với một node; `size=1`.

### Bài 14. Chèn khóa trùng

Treap set đã có key30. `insert(30)` nên trả gì và có tạo node không?

**Lời giải:** Trả **False**, không tạo node và không sửa cây. Trong chính sách code bài, thao tác trùng cũng **không tiêu thụ priority ngẫu nhiên** và không tăng version.

### Bài 15. Priority trùng có tự nhiên tạo Cartesian tree duy nhất không?

Hai node có priority raw bằng 10. Nếu code dùng `<` khi quay, còn validator dùng `<=`, điều gì sai?

**Lời giải:** So sánh không nhất quán làm kết quả phụ thuộc đường cập nhật và có thể khiến validator chấp nhận trạng thái mà thuật toán không xử lý đúng. Dùng một **thứ tự priority toàn phần duy nhất**, ví dụ tuple `(raw_priority,serial_unique)`, ở mọi thao tác.

### Bài 16. Xóa một lá

Cây `(30,10)` có con trái `(20,40)` là lá. Xóa key20 cần quay không?

**Lời giải:** Không. Thay liên kết con trái của 30 bằng `NULL`, giải phóng node20 nếu sở hữu cấp phát động, cập nhật size root từ 2 xuống 1. Không cần quay vì target có 0 con.

### Bài 17. Xóa node chỉ có một con

Root key30 có con phải key50, và key50 có con trái key40. Xóa key50 cần làm gì?

**Lời giải:** Khi tìm target50, nó có **một con là 40**. Thay con trỏ `root.right` bằng node40, bỏ target50, cập nhật size. BST hợp lệ vì 30<40. Nếu cây treap ban đầu đúng heap, heap cũng được giữ khi bỏ target ở giữa.

### Bài 18. Chọn hướng quay khi xóa hai con

Target có con trái priority30 và con phải priority20, dùng min-heap. Nên quay hướng nào đầu tiên?

**Lời giải:** **Quay trái tại target** để đưa **con phải priority20** lên. Priority20 tốt hơn priority30 nên đó là gốc phù hợp hơn cho phần cây còn lại sau khi target được loại.

### Bài 19. Đối xứng trường hợp trước

Target có con trái priority5 và con phải priority60. Hướng quay đầu tiên?

**Lời giải:** **Quay phải tại target** để đưa **con trái priority5** lên, đẩy target xuống nhánh phải của node vừa được đưa lên.

### Bài 20. Vì sao tạm thời thấy min-heap sai sau quay xóa?

Treap hợp lệ có root target(priority10), con được chọn priority20. Sau quay, node priority20 làm cha target priority10. Có phải thuật toán xóa sai ngay lập tức không?

**Lời giải:** Không. Đây là một **trạng thái trung gian được phép** trong thuật toán quay target xuống; cạnh vào chính target tạm thời trái heap. Thuật toán phải tiếp tục đẩy và gỡ target. Chỉ khi hoàn tất mới đòi heap đúng trên mọi cạnh còn lại.


### Bài 21. Xóa root có ba phép quay

Treap ban đầu có root `(40,10)`, con trái `(20,30)`, con phải `(60,20)`; node20 có hai con `(10,80),(30,60)`, node60 có hai con `(50,70),(70,90)`. Khi xóa key40 theo thuật toán quay xuống, các phép quay là gì?

**Lời giải:** Target40 ban đầu có con 20(priority30) và 60(priority20), nên quay **trái tại 40**. Target vẫn có con 20(priority30) và 50(priority70), nên quay **phải tại 40**. Tiếp theo target có con 30(priority60) và 50(priority70), nên quay **phải tại 40** lần nữa. Giờ target chỉ còn con phải50, nối node30.right tới 50, bỏ node40. Tổng cộng **3 phép quay**.

### Bài 22. Tập khóa sau khi xóa ở Bài 21

Kết quả inorder sau xóa key40 gồm những khóa nào và root mới có key gì?

**Lời giải:** Inorder là `10,20,30,50,60,70`, root mới là **key60** (priority20). Tất cả node khác được giữ lại, size toàn cây từ 7 xuống 6.

### Bài 23. Vì sao không chọn con bất kỳ khi xóa?

Target có hai con, root trái priority50 và root phải priority10. Nếu luôn quay phải mà không xét priority, có bảo đảm heap cuối đúng không?

**Lời giải:** Không. Khi xóa target, gốc của phép hợp hai cây con phải ưu tiên **priority nhỏ hơn**, tức node bên phải priority10. Quay phải tùy ý có thể đưa node ưu tiên kém lên trước và khiến kết quả cuối phá heap.

### Bài 24. Tại sao theo identity của target khi quay?

Sau khi quay, root của cây con không còn là target. Nếu hàm xóa tiếp tục xử lý root mới như thể nó vẫn là node mang key cần xóa, điều gì có thể xảy ra?

**Lời giải:** Có thể xóa nhầm node vừa đưa lên, hoặc không bao giờ gỡ target thật. Sau quay phải, target trở thành **con phải của root mới**; sau quay trái, target trở thành **con trái của root mới**. Phải đi theo nhánh ấy hoặc tìm tiếp đúng key target.

### Bài 25. Tại sao xóa làm size giảm 1 dù có nhiều quay?

Một phép xóa cần 10 rotations. Metadata `size` tổng phải giảm bao nhiêu?

**Lời giải:** Giảm **đúng 1** vì chỉ một node có key được gỡ khỏi set. Rotations thay **liên kết và hình dạng**, không thêm hoặc loại phần tử. Giảm size theo số rotations là lỗi nghiêm trọng.

### Bài 26. `merge` khi xóa có tiền đề gì?

Target có cây con trái A và cây con phải B. Vì sao `MERGE(A,B)` hợp lệ mà `MERGE` của hai set tùy ý chưa chắc hợp lệ?

**Lời giải:** Do BST, mọi khóa A đều **nhỏ hơn target.key**, mọi khóa B **lớn hơn target.key**, nên `max_key(A)<min_key(B)`. Hai tập bất kỳ có thể xen kẽ khóa, vi phạm tiền đề merge theo thứ tự.

### Bài 27. Xóa bằng quay và merge có thể cho cây cuối khác nhau không?

Giả sử priority của mọi node phân biệt và cả hai implementation đều đúng BST+min-heap sau khi xóa cùng key. Hình dạng treap cuối có bắt buộc giống nhau không?

**Lời giải:** Có. Với key/priority phân biệt, **Cartesian tree được xác định duy nhất**: root là node priority tốt nhất, các cây con được chia bởi key. Vì vậy hai implementation đúng trên cùng tập cặp phải cho cùng hình dạng cuối, dù đường biến đổi trung gian khác nhau.

### Bài 28. Chèn và xóa ảnh hưởng worst-case thế nào?

Một treap được rút priority theo mô hình IID, expected chiều cao O(log n). Có thể khẳng định mọi lần `insert` hoặc `discard` đều O(log n) worst-case không?

**Lời giải:** Không. Một treap đường dài n node vẫn thỏa BST/heap; tìm vị trí chèn/xóa có thể mất Θ(n). Bảo đảm **O(log n) kỳ vọng** không phải chặn cho mọi cấu hình priority.

### Bài 29. Bộ nhớ phụ của đệ quy

Nếu một thao tác đi qua đường dài h node và dùng hàm đệ quy một cấp cho mỗi node, stack phụ là bao nhiêu? Với một cây lệch có h=n thì sao?

**Lời giải:** Dùng O(h) stack. Nếu cây lệch h=n, worst O(n) stack và có thể gây `RecursionError` trong Python. Kỳ vọng chiều cao logarit không loại trừ giới hạn stack của một lần chạy cụ thể.

### Bài 30. Thay root sau hai phép quay

Trong ví dụ chèn `(30,10)`, sau quay trái ở node20, có được giữ con trỏ `root.left=20` không?

**Lời giải:** Không. Quay trái làm node30 thành **gốc mới của cây con trái của root40**; phải cập nhật `root.left=30`. Sau đó quay phải tại root40, lại phải cập nhật **root toàn cây** thành 30.

### Bài 31. `rank` sau một phép quay

Treap có inorder `10,20,30,40`. Sau một phép quay hợp lệ giữ inorder, `rank(30)` có thay đổi không? Metadata nào bắt buộc sửa?

**Lời giải:** `rank(30)=2` **không đổi** vì tập khóa và thứ tự không đổi. Nhưng `subtree_size` của những node bị đổi quan hệ con có thể đổi; phải `pull` đúng từ dưới lên để rank trả 2 trong code.

### Bài 32. `select` sau khi xóa

Treap chứa `[10,20,30,40,50]`. Xóa 30, kết quả `select(2)` theo 0-based là gì?

**Lời giải:** Dãy còn `[10,20,40,50]`; `select(2)=40`. Nếu code trả 30 hoặc 50, cần kiểm tra cả linked structure và metadata size sau quay/xóa.

### Bài 33. Test scripted priority có ưu thế gì so với chỉ seed?

Bạn muốn chắc chắn một lần xóa bắt buộc quay trái rồi quay phải. Vì sao seed cố định không phải phương án đơn giản nhất để kiểm tra đúng chuỗi ấy?

**Lời giải:** Seed cố định chỉ tái lập **chuỗi random của PRNG**, không diễn đạt trực tiếp hình dạng mong muốn và có thể phụ thuộc thứ tự tiêu thụ RNG. Scripted priority đặt đúng các ưu tiên của từng key, nên có thể dựng cây dự kiến và kiểm tra **hướng/số rotations** một cách độc lập với RNG.

### Bài 34. Kiểm thử đối chiếu với `set`

Vì sao cần so `list(tree.keys())==sorted(expected_set)` sau nhiều chuỗi insert/discard, dù `tree.contains(k)` cho vài khóa vẫn đúng?

**Lời giải:** Một cấu trúc có thể mất khóa, lặp khóa hoặc sắp sai ở một nhánh chưa được truy vấn. So toàn bộ inorder với sorted set phát hiện lỗi nội dung/thứ tự; còn `assert_valid` phát hiện heap, size, identity/chu trình. Hai loại test bổ sung cho nhau.

### Bài 35. `Node **link` trong C dùng để làm gì?

Một phép quay thực hiện tại `parent->left`. Vì sao gọi `rotate_right(&parent->left)` có ích hơn chỉ sửa một biến con trỏ cục bộ?

**Lời giải:** `&parent->left` là **địa chỉ ô liên kết thực** từ parent tới gốc cây con. Hàm quay ghi `*link=new_root` nên parent lập tức trỏ tới gốc mới. Nếu root toàn cây đổi, truyền `&root` tương tự.

### Bài 36. Hủy node sau xóa

Trong C, sau khi thay target bằng con còn lại hoặc merge hai cây con, có nên `free(target->left)` và `free(target->right)` cùng `free(target)` không?

**Lời giải:** Không. Các cây con đã được nối vào treap mới và vẫn **thuộc sở hữu cấu trúc**. Chỉ hủy payload riêng của target (nếu có), rồi `free(target)` **một lần**. Không đọc target sau khi free.

### Bài 37. Cập nhật đồng thời khi dùng `contains` trước `insert`

Thread A thấy `contains(k)==False`. Trước khi A thực hiện insert, thread B thêm k. Nếu không có đồng bộ, lời hứa “không có duplicate” còn được bảo đảm không?

**Lời giải:** Không. Đây là **race giữa check và update**. Treap tuần tự cần mutex/transaction hoặc một thuật toán concurrent có linearization point rõ. `_version` fail-fast không phải khóa đồng bộ.

### Bài 38. Fail-fast iterator có phải snapshot không?

Một generator inorder đã yield một key, rồi chương trình chèn một khóa mới. Generator của Mục 9 báo `RuntimeError` ở lần lấy tiếp theo. Có thể gọi đó là snapshot ổn định không?

**Lời giải:** Không. Nó **phát hiện cập nhật** (best effort) rồi từ chối tiếp tục; snapshot phải giữ một ảnh logic cố định cho cả lượt duyệt. Muốn snapshot, có thể sao chép `list(keys())` trước update hoặc dùng persistent tree.

### Bài 39. Nếu xóa ném `RecursionError` giữa chừng?

Một treap lệch khiến hàm xóa đệ quy ném `RecursionError` sau một vài rotations. Có thể mặc định cây vẫn đúng BST/heap và root cũ còn dùng an toàn không?

**Lời giải:** Không. Các phép quay có thể đã **sửa tại chỗ một số liên kết** trước khi exception thoát ra; assignment root của caller có thể chưa hoàn tất. Muốn bảo đảm phục hồi cần chiến lược exception safety/rollback, path-copy, hoặc bản không đệ quy có hợp đồng lỗi phù hợp.

### Bài 40. Quyết định chọn cấu trúc

Một hệ thống cần tập có thứ tự, nhiều lần tìm/chèn/xóa, chấp nhận độ trễ kỳ vọng nhưng không có deadline cứng. Treap bằng quay có phù hợp không? Nếu yêu cầu worst-case O(log n) cho mỗi thao tác thì sao?

**Lời giải:** Treap là lựa chọn hợp lý cho trường hợp đầu nếu random, chi phí comparator, quyền sở hữu và bộ nhớ được quản lý phù hợp; expected tìm/chèn/xóa **O(log n)**. Nếu cần **worst-case O(log n)**, cân nhắc AVL hoặc red-black tree chuẩn; thay xóa quay bằng merge không biến expected thành worst-case.

## 18. Tổng kết: một thao tác treap là một cam kết về bất biến

### 18.1. Công thức chèn

```text
1. Dùng key để tìm vị trí lá BST.
2. Nếu key đã có: không thêm node.
3. Tạo node mới với priority duy nhất.
4. Gắn node vào cây.
5. Nếu con có priority nhỏ hơn cha:
      - con trái: rotate_right(cha)
      - con phải: rotate_left(cha)
6. Cập nhật size từ dưới lên.
7. Cập nhật root/cây con ở bên gọi.
```

**Bất biến sau chèn:** inorder tăng nghiêm ngặt, min-heap đúng, size tăng một khi chèn thành công.

### 18.2. Công thức xóa bằng quay

```text
1. Tìm target theo key.
2. Nếu không thấy: giữ nguyên set.
3. Nếu target có 0 hoặc 1 con: nối thẳng con còn lại.
4. Nếu target có hai con:
      - left.priority < right.priority:
            rotate_right(target)
            tiếp tục xóa target ở nhánh phải mới
      - ngược lại:
            rotate_left(target)
            tiếp tục xóa target ở nhánh trái mới
5. Lặp tới khi target có tối đa một con rồi gỡ.
6. pull() từ dưới lên, cập nhật root ở mỗi cấp.
```

**Bất biến sau xóa:** inorder tăng, heap đúng trên mọi cạnh còn sống, size giảm đúng một nếu xóa thành công.

**Khác biệt quan trọng:** trong khi xóa, heap **được phép sai tạm trên đường chứa target**; không được dùng điều kiện quay của chèn để quyết định một phép quay của xóa.

### 18.3. Công thức xóa bằng merge

```text
1. Tìm target theo key.
2. Gán replacement = merge(target.left, target.right).
3. Nối parent/root tới replacement.
4. Loại đúng target và cập nhật size.
```

`merge` hợp lệ vì mọi khóa cây trái target nhỏ hơn mọi khóa cây phải target. Khi root có priority phân biệt, hai cách xóa đúng tạo **cùng Cartesian tree cuối**.

### 18.4. Chi phí và phạm vi áp dụng

| Đối tượng | Chi phí |
| --- | --- |
| Một phép quay | **O(1)** thời gian/bộ nhớ phụ |
| Một lần tìm/chèn/xóa bằng quay | **O(h)** theo chiều cao cây h |
| Kỳ vọng với priority độc lập, tập khóa cố định phù hợp | **O(log n)** |
| Worst-case với cây lệch | **O(n)** |
| Bộ nhớ node treap set | **O(n)** |
| Stack của bản đệ quy | **O(h)**, worst O(n) |

**Checklist cuối cùng:** sau mọi thao tác, kiểm tra **BST, min-heap, subtree_size, root mới, node identity và tập khóa**. Mỗi phép quay chỉ sửa một số con trỏ; phần khó của treap không phải bản thân phép quay mà là **biết khi nào quay, theo đúng node nào và giữ tất cả bất biến sau khi kết thúc**.

Nếu nắm rõ những cam kết này, bạn có thể đọc một implementation treap hiện có, tự mô phỏng các phép chèn/xóa và đánh giá đúng sự khác nhau giữa một cấu trúc có hiệu năng **kỳ vọng** với cấu trúc có bảo đảm **worst-case**.
