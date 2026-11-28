# Treap theo vị trí và tách–ghép một dãy

## 1. Bài toán: một dãy có thể bị chèn, xóa, cắt và dán liên tục

Trong học phần **Cấu trúc dữ liệu**, mảng và danh sách liên kết đều biểu diễn được một dãy có thứ tự. Tuy nhiên, những phép toán trên **vị trí của phần tử** có đánh đổi khác nhau:

- Mảng hỗ trợ đọc phần tử thứ `i` trong `O(1)`, nhưng chèn/xóa ở giữa thường phải dời `O(n)` phần tử.
- Danh sách liên kết có thể tháo/gắn tại vị trí **đã có con trỏ** trong `O(1)`, nhưng đi tới phần tử thứ `i` từ đầu danh sách thường mất `O(n)`.
- Cây tìm kiếm theo **giá trị khóa** hỗ trợ tra cứu khóa, nhưng khi dãy cho phép giá trị trùng nhau hoặc khi đảo thứ tự một đoạn, giá trị phần tử không còn là khóa định vị thích hợp.

Xét một trình soạn thảo có dãy:

```text
Chỉ số:       0   1   2   3   4   5
Dãy:          A   B   C   D   E   F
```

Các thao tác mong muốn:

1. Lấy phần tử tại chỉ số `i`.
2. Chèn một phần tử vào vị trí `i`.
3. Xóa phần tử tại vị trí `i`.
4. Tách dãy thành hai phần ở vị trí `k`.
5. Ghép hai dãy `A` và `B` thành `A+B`.
6. Cắt đoạn `[l,r)` rồi dán vào vị trí khác.
7. Đảo thứ tự một đoạn `[l,r)`.
8. Tính một giá trị tổng hợp trên đoạn, chẳng hạn tổng các số.

Một cấu trúc phù hợp là **treap theo vị trí** (*implicit treap*, hay *implicit-key treap*): cây nhị phân vừa giữ thứ tự phần tử theo **duyệt inorder**, vừa duy trì một thứ tự ưu tiên ngẫu nhiên để có hình dạng tương đối cân bằng.

> Ý tưởng quan trọng nhất: **không lưu chỉ số tuyệt đối của phần tử làm khóa**. Vị trí của một phần tử được suy ra từ **kích thước các cây con**. Nhờ vậy, sau chèn, xóa hoặc di chuyển đoạn, ta không phải cập nhật chỉ số tại hàng loạt nút.

Bài học trình bày bất biến của implicit treap, hai phép lõi `split`–`merge`, cách tạo các thao tác dãy từ chúng, lazy propagation để đảo đoạn, phân tích độ phức tạp và một cài đặt Python tự chứa.

## 2. Treap là sự kết hợp của hai bất biến

Tên **treap** ghép từ *tree* và *heap*. Một treap thông thường kết hợp:

- Bất biến **BST theo khóa**: bên trái nhỏ hơn khóa nút, bên phải lớn hơn.
- Bất biến **heap theo priority**: priority của cha lớn hơn priority của con nếu chọn max-heap.

Ở **treap theo vị trí**, thành phần BST được hiểu theo **thứ tự vị trí của các nút** thay vì so sánh giá trị phần tử. Ta cần phân biệt rất rõ hai thứ:

| Thuộc tính | Treap tìm kiếm theo khóa | Treap theo vị trí |
|---|---|---|
| Điều quyết định thứ tự inorder | Khóa dữ liệu, chẳng hạn `key` | Thứ tự phần tử trong **dãy** |
| Có bắt buộc `value(left)<value(root)`? | Có, nếu `value` là khóa BST phân biệt | **Không** |
| Giá trị trùng nhau | Cần chính sách khóa trùng | **Được phép**, là các vị trí riêng |
| Metadata hỗ trợ điều hướng | Có thể có `size` | **Cần `size`** để xác định vị trí |
| Bất biến heap | Priority cha ≥ priority con | Priority cha ≥ priority con |
| Phép thao tác lõi thường dùng | Split/merge theo khóa | **Split/merge theo số phần tử** |

Một implicit treap vẫn có cấu trúc nhị phân và thuộc họ treap; chỉ có cách biểu diễn **khóa thứ tự** là khác.

### 2.1. Thứ tự inorder là thứ tự của dãy

Giả sử có sáu phần tử `A,B,C,D,E,F`, và các priority minh họa:

```text
                       C (90)
                      /      \
                   A (70)    E (80)
                      \      /    \
                     B (50) D (60) F (40)
```

Cây thỏa max-heap về priority:

- `90>70` và `90>80`.
- `70>50`.
- `80>60` và `80>40`.

Duyệt inorder (**trái → nút → phải**) cho:

```text
A, B, C, D, E, F
```

Đây chính là **dãy đang lưu**. Không cần điều kiện `A<B<C<...` trên các giá trị; `A` và `B` chỉ là nhãn để nhận biết phần tử.

### 2.2. Priority không phải dữ liệu ứng dụng

Priority trong treap là **khóa phụ phục vụ hình dạng cây**. Nó khác với:

- Chỉ số hiện tại của phần tử.
- Giá trị đang lưu ở phần tử.
- “Mức ưu tiên công việc” trong một hàng đợi ưu tiên nghiệp vụ.

Ví dụ một dãy `[9,9,2,9]` hoàn toàn hợp lệ: bốn vị trí là bốn nút khác nhau; priority ngẫu nhiên chỉ quyết định cấu trúc nội bộ, **không làm thay đổi thứ tự dãy**.

Khi chèn nút, ta thường sinh priority ngẫu nhiên độc lập. **Priority đã gán cho một nút không đổi khi nó di chuyển vị trí trong dãy**.

### 2.3. Vì sao ngẫu nhiên giúp cân bằng?

Với `n` nút và **priority độc lập, phân biệt, có thứ tự ngẫu nhiên đều**, nút có priority cao nhất làm gốc. Gốc chia dãy thành phần trước nó và phần sau nó, rồi quy tắc lặp lại trên mỗi phần.

Dưới giả thiết chuẩn về priority, treap có:

- **Độ sâu kỳ vọng** của một nút là `O(\log n)`.
- **Chiều cao kỳ vọng** là `O(\log n)`.
- Các đường `split`/`merge` có độ dài kỳ vọng logarit.

Tuy nhiên đây là **bảo đảm kỳ vọng dựa trên ngẫu nhiên**, **không phải bảo đảm cho mọi cấu hình priority**. Có những cấu hình treap suy biến thành một đường dài `n` nút, khiến một thao tác tốn `O(n)`.

Không được nhầm treap ngẫu nhiên với AVL/Red–Black Tree, nơi chiều cao logarit được bảo đảm theo bất biến cân bằng của cấu trúc.

## 3. Bất biến thông tin cây con: `size`

### 3.1. Định nghĩa

Với một nút `u`:

\[
size(\varnothing)=0,
\]

\[
\boxed{
size(u)=1+size(u.left)+size(u.right).
}
\]

`size(u)` đếm **toàn bộ nút thuộc cây con gốc `u`**, kể cả `u`, không chỉ hai con trực tiếp.

Trong implicit treap minh họa, **mỗi vị trí ứng với một nút vật lý**, dù hai phần tử có giá trị trùng nhau. Vì vậy:

\[
size(root)=\text{độ dài dãy}.
\]

Bất biến này phải đúng sau **mọi lần sửa liên kết**.

### 3.2. Vị trí của nút được suy từ kích thước bên trái

Tại gốc một cây con, đặt:

\[
L=size(root.left).
\]

Theo inorder:

- Có đúng `L` phần tử đứng trước gốc trong cây con.
- Gốc có **chỉ số cục bộ `L`**, tính từ `0`.
- Các phần tử bên phải có chỉ số cục bộ lớn hơn `L`.

Để truy cập phần tử tại chỉ số `i` của cây con:

1. Nếu `i<L`, đi trái với chỉ số giữ nguyên `i`.
2. Nếu `i=L`, trả giá trị tại gốc.
3. Nếu `i>L`, đi phải với chỉ số mới `i-L-1`.

Không có bước nào cần **lưu một trường `index` cố định** cho nút.

### 3.3. Tính kích thước ở cây ví dụ

```text
                     C (priority 90, size 6)
                    /                       \
          A (70, size 2)                  E (80, size 3)
                  \                       /            \
              B (50, size 1)       D (60, size 1)  F (40, size 1)
```

Tại `C`:

\[
size(C)=1+size(A)+size(E)=1+2+3=6.
\]

Tại `A`:

\[
size(A)=1+size(\varnothing)+size(B)=1+0+1=2.
\]

Ví dụ tìm chỉ số `4` (phần tử thứ năm):

- Ở `C` có `size(left)=2`, nên `4>2`: đi phải với `i'=4-2-1=1`.
- Ở `E` có `size(left)=1`, nên `i'=1`: trả **`E`**.

**Điều kiện tiên quyết:** các giá trị `size` phải nhất quán với cây hiện tại. Sai metadata có thể khiến thuật toán đi sai nhánh ngay cả khi cây vẫn thỏa max-heap priority.

## 4. Không được nhầm khóa ngầm với chỉ số lưu tại nút

Có hai cách thiết kế rất khác nhau:

**Cách sai cho dãy chỉnh sửa động:** lưu `node.index` là `0,1,2,\ldots,n-1` rồi dùng nó làm khóa BST.

- Sau khi chèn một phần tử vào giữa, mọi phần tử phía sau có thể phải đổi chỉ số.
- Sau cắt–dán hoặc đảo đoạn, rất nhiều khóa vị trí phải thay đổi.
- Mỗi lần đổi khóa có thể còn phá thứ tự BST.

**Cách của implicit treap:** một nút chỉ lưu `value`, `priority`, `left/right` và metadata như `size`.

- Chỉ số là **kết quả** của cấu trúc hiện tại, không phải dữ liệu bất biến.
- Tách–ghép cây tự tạo ra thứ tự phần tử mới.
- Sau mỗi thay đổi, chỉ cần cập nhật metadata dọc những đường cây bị sửa.

Đây là một ví dụ của thiết kế **cấu trúc dữ liệu dựa trên bất biến**, thay vì cố cập nhật thủ công hàng loạt vị trí.

## 5. Hai phép lõi: `split` và `merge`

Hầu hết các phép sửa dãy có thể được viết ngắn gọn từ hai thao tác:

- **`split(T,k)`:** tách treap `T` thành `A` chứa **`k` phần tử đầu**, và `B` chứa các phần tử còn lại.
- **`merge(A,B)`:** ghép tất cả phần tử của `A` **đứng trước** tất cả phần tử của `B`.

Khi ghép, `A` và `B` phải là **hai tập nút rời nhau** và mỗi cây đã thỏa các bất biến của treap. Phép `merge` là phép **nối dãy theo thứ tự**, không sắp xếp lại giá trị.

### 5.1. Quy ước chỉ số

Bài dùng chỉ số bắt đầu từ **`0`** và khoảng nửa mở theo **chỉ số**:

- `split(T,0)` → `([],T)`.
- `split(T,n)` → `(T,[])`.
- `split(T,k)` hợp lệ khi `0≤k≤n`.
- Đoạn `[l,r)` gồm các vị trí `l,l+1,\ldots,r-1`, có độ dài `r-l`.
- Phép `insert(i,x)` chèn `x` **trước** phần tử hiện ở vị trí `i`; `i=n` là thêm cuối.

**Khoảng nửa mở `[l,r)` ở đây là quy ước chỉ số dãy**, không liên quan tới việc một đối tượng “khoảng thời gian” có chứa đầu mút hay không.

### 5.2. `split(T,k)` trên ví dụ

Dãy:

```text
T = [A, B, C, D, E, F]
```

Gọi:

```text
(A_tree, B_tree) = split(T, 3)
```

Kết quả:

```text
A_tree: [A, B, C]
B_tree: [D, E, F]
```

Với cây priority ở mục 2, `split(T,3)` có thể sinh:

```text
       C(90)                  E(80)
       /                      /   \
    A(70)                   D(60) F(40)
       \
       B(50)

inorder: A,B,C          inorder: D,E,F
```

Hai nửa vẫn đúng thứ tự inorder và bất biến max-heap. Các trường `size` thay đổi tại những nút có liên kết con bị sửa.

### 5.3. `merge(A,B)` phải khôi phục một cây hợp lệ

Với hai treap riêng biệt:

```text
A = [A,B,C]
B = [D,E,F]
```

Kết quả `merge(A,B)` phải có inorder:

```text
[A,B,C,D,E,F]
```

Để giữ bất biến max-heap:

1. So sánh priority tại hai gốc.
2. Gốc có priority lớn hơn làm **gốc của cây kết quả**.
3. Ghép đệ quy vào đúng nhánh giáp ranh.
4. Tính lại metadata tại gốc vừa thay đổi con.

**Không** tìm nút lớn nhất theo giá trị hay sắp lại phần tử. Việc ưu tiên chỉ quyết định **hình dạng cây**, không đổi thứ tự dãy.

## 6. Chi tiết thuật toán `split` theo số phần tử

### 6.1. Phân tích tại gốc

Giả sử `u` là gốc, `L=size(u.left)`, cần lấy `k` phần tử đầu.

**Trường hợp 1 — `k≤L`**

Tất cả `k` phần tử đầu nằm trong **cây trái của `u`**. Ta tách cây trái:

```text
(A, B) = split(u.left, k)
u.left = B
pull(u)
return (A, u)
```

Vì `u` và toàn bộ cây phải đứng sau cây trái theo inorder, chúng phải ở **nửa sau**. Phần `A` tách ra là nửa đầu.

**Trường hợp 2 — `k>L`**

Nửa đầu chứa **toàn bộ cây trái** và **chính `u`**, tức `L+1` phần tử. Cần lấy thêm:

\[
k'=k-L-1
\]

phần tử ở đầu cây phải.

```text
(A, B) = split(u.right, k - L - 1)
u.right = A
pull(u)
return (u, B)
```

Phần `u` cùng cây trái và `A` thuộc nửa đầu; `B` thuộc nửa sau.

### 6.2. Mã giả hoàn chỉnh

```text
SPLIT(u, k):
    # 0 <= k <= SIZE(u)

    if u == None:
        return (None, None)

    PUSH(u)                    # Nếu dùng lazy reversal.
    L = SIZE(u.left)

    if k <= L:
        (a, new_left) = SPLIT(u.left, k)
        u.left = new_left
        PULL(u)
        return (a, u)

    else:
        (new_right, b) = SPLIT(u.right, k - L - 1)
        u.right = new_right
        PULL(u)
        return (u, b)
```

Khi `u=None`, chỉ có lời gọi hợp lệ với `k=0`. Bài cài đặt kiểm tra biên ở **API công khai**, còn `split` là hàm nội bộ chỉ được gọi với giá trị `k` hợp lệ.

### 6.3. Tại sao phải `PUSH` trước khi nhìn vào `left/right`?

Nếu cây có **thẻ đảo đoạn chờ xử lý** (*lazy reversal*), hai nhánh trái/phải vật lý có thể chưa phản ánh thứ tự dãy hiện tại. Trước khi dùng `size(u.left)` để quyết định “`k` phần tử đầu nằm phía nào”, phải **đẩy thẻ lazy xuống** bằng `PUSH(u)`.

Nếu không, `split` có thể tách sai vị trí dù các giá trị `size` là đúng về số lượng.

### 6.4. Độ phức tạp

Tại mỗi bước chỉ đi xuống một nhánh, rồi gọi `pull` đúng một lần khi quay về:

\[
T_{\text{split}}=O(h+1).
\]

Với treap có priority ngẫu nhiên theo giả thiết chuẩn, **kỳ vọng** `O(\log(n+1))`; trường hợp xấu nhất nếu treap suy biến là **`O(n)`**.

Bản đệ quy dùng **`O(h+1)` bộ nhớ stack**, không phải `O(1)`. Đây là một đánh đổi triển khai quan trọng trong Python.

## 7. Chi tiết thuật toán `merge`

### 7.1. Hai gốc và bất biến max-heap

Giả sử hai treap `A`, `B` có tập nút rời nhau, và mọi phần tử của `A` phải **đứng trước** mọi phần tử của `B`.

- Nếu một cây rỗng, trả cây còn lại.
- Nếu `priority(A.root)>priority(B.root)`, gốc `A` thắng; vì toàn bộ `B` đứng sau `A`, ta ghép `B` vào **phía phải** của `A`.
- Nếu gốc `B` thắng, ta ghép `A` vào **phía trái** của `B`.

Mã giả:

```text
MERGE(a, b):
    if a == None: return b
    if b == None: return a

    if PRIORITY(a) > PRIORITY(b):
        PUSH(a)
        a.right = MERGE(a.right, b)
        PULL(a)
        return a

    else:
        PUSH(b)
        b.left = MERGE(a, b.left)
        PULL(b)
        return b
```

Nếu có cơ chế priority đảm bảo **duy nhất**, không có trường hợp bằng nhau. Nếu cho phép bằng, phải chọn một chính sách nhất quán (chẳng hạn `≥` nghiêng về cây trái); việc bảo đảm hiệu năng kỳ vọng còn phụ thuộc cách xử lý priority ngẫu nhiên.

### 7.2. Vì sao không làm sai thứ tự dãy?

**Nếu `a` thắng:** cây trái của `a` giữ nguyên, giá trị gốc `a` giữ nguyên, còn phần phía phải trở thành `merge(a.right,b)`. Vì cả `a.right` cũ lẫn toàn bộ `b` đều đứng sau giá trị gốc `a`, thứ tự được nối đúng.

**Nếu `b` thắng:** đối xứng; toàn bộ `a` đứng trước giá trị gốc `b` và cây phải của `b`.

Do đó:

\[
inorder(merge(a,b))=inorder(a)\mathbin{+\!\!+}inorder(b),
\]

với `+\!\!+` là phép nối dãy.

### 7.3. Vì sao không làm sai bất biến heap?

Nếu `a.root` có priority cao hơn `b.root`, nó cũng cao hơn mọi nút trong `a` và `b` theo bất biến max-heap ở hai cây đầu vào. Khi chọn `a.root` làm gốc, phần ghép đệ quy ở cây phải vẫn là treap có heap hợp lệ. Cây trái `a.left` không đổi. Tính lại metadata là đủ để giữ bất biến tại gốc.

Lập luận đối xứng nếu `b.root` thắng.

### 7.4. Chi phí

Một lần `merge` chỉ sửa đường biên giữa hai treap, không duyệt toàn bộ phần tử. Chi phí tỉ lệ với độ dài đường đệ quy, có chặn trên `O(h_a+h_b+1)` nếu hai cây có chiều cao `h_a,h_b`.

Với priority ngẫu nhiên độc lập và giả thiết cân bằng kỳ vọng của treap, có thể xem một lần ghép hai dãy tổng cộng `n` phần tử là **`O(\log(n+1))` thời gian kỳ vọng**. Trường hợp xấu nhất vẫn có thể là `O(n)`.

Lưu ý trong ứng dụng: `merge` **không sao chép các nút**. Sau khi ghép, hai gốc đầu vào không còn nên được dùng như hai cây sở hữu độc lập; nếu giữ và sửa chúng song song sẽ dễ tạo **chia sẻ nút**, phá cấu trúc cây.

## 8. Những phép sửa dãy được ghép từ `split` và `merge`

Khi đã có hai thao tác lõi, nhiều phép toán trở thành các biểu thức ngắn.

### 8.1. Chèn một phần tử vào vị trí `i`

Với `0≤i≤n`:

```text
(A, B) = split(T, i)
X = new_node(value, random_priority)
T = merge(merge(A, X), B)
```

Ví dụ:

```text
T = [A, B, C, D]
insert(2, X)

A = [A, B]
B = [C, D]

Kết quả: [A, B, X, C, D]
```

Không cần đổi `index` của các nút `C,D` vì **vị trí được suy ra từ cây**, không được lưu cố định.

### 8.2. Xóa phần tử tại vị trí `i`

Với `0≤i<n`:

```text
(A, Rest) = split(T, i)
(Middle, B) = split(Rest, 1)

# Middle chứa đúng một phần tử.
removed_value = Middle.value
T = merge(A, B)
```

Chúng ta tách đúng một **vị trí** chứ không xóa mọi phần tử có cùng giá trị. Ví dụ dãy `[7,7,9]`, `erase(1)` chỉ xóa **một** giá trị `7` ở chỉ số `1`.

### 8.3. Đọc phần tử tại vị trí `i`

Có hai cách:

- Đi từ gốc xuống bằng `size(left)`, không cần sửa cây.
- Tách ba đoạn bằng `split`, đọc nút giữa, rồi `merge` trở lại.

Cách đi trực tiếp ngắn hơn về hằng số thời gian và **không làm thay đổi cấu trúc cây** (ngoài việc đẩy thẻ lazy nếu có). Bài sẽ cài đặt cách đi trực tiếp.

### 8.4. Tách và ghép hai dãy

```text
split([A,B,C,D,E], 2)
    → [A,B] và [C,D,E]

merge([A,B], [C,D,E])
    → [A,B,C,D,E]
```

Hàm `split` trả **hai gốc treap rời nhau**. Hàm `merge` nối chúng theo thứ tự đã chọn. Nếu ghép ngược:

```text
merge([C,D,E], [A,B]) → [C,D,E,A,B]
```

Kết quả là một dãy khác; bản thân `merge` **không biết “thứ tự ban đầu”**.

### 8.5. Cắt một đoạn `[l,r)`

Đầu tiên tách dãy thành:

\[
T=A + M + C
\]

trong đó:

- `A` gồm `l` phần tử đầu.
- `M` gồm `r-l` phần tử từ `l` đến `r-1`.
- `C` là phần còn lại.

Mã giả:

```text
(A, Rest) = split(T, l)
(M, C)    = split(Rest, r-l)

Without = merge(A, C)
```

Nếu muốn dán `M` vào vị trí `pos` trong **dãy sau khi cắt**:

```text
(P, Q) = split(Without, pos)
T = merge(merge(P, M), Q)
```

Đây là phép **cut–paste** bằng một số hằng lần split/merge.

## 9. Cắt–dán: phải nói rõ hệ tọa độ của `pos`

Một trong những lỗi phổ biến nhất không nằm ở thuật toán treap, mà nằm ở **ý nghĩa của vị trí đích**.

### 9.1. Quy ước dùng trong bài

Hàm:

```text
move(l, r, pos)
```

được định nghĩa như sau:

1. Cắt đoạn `[l,r)` của dãy **ban đầu**.
2. Có dãy còn lại độ dài `n-(r-l)`.
3. Chèn đoạn vừa cắt **trước vị trí `pos` của dãy còn lại**.

Điều kiện:

\[
0\le l\le r\le n,\qquad
0\le pos\le n-(r-l).
\]

Đây là chỉ số **sau khi cắt**, không phải chỉ số `pos` tính trên dãy ban đầu.

### 9.2. Ví dụ chi tiết

```text
Ban đầu:
index     0  1  2  3  4  5
value     A  B  C  D  E  F

Cắt [1,4):
M = [B,C,D]
Without = [A,E,F]

Dán tại pos = 3 trong Without:
Without trước vị trí 3 = [A,E,F]
Without sau vị trí 3  = []

Kết quả:
[A,E,F,B,C,D]
```

Một phép cắt–dán như vậy không cần di chuyển/copy từng phần tử `B,C,D`; nó chỉ **tái kết nối các cây con**.

### 9.3. Nếu API nhận vị trí đích theo chỉ số ban đầu?

Đó là **một hợp đồng khác**. Giả sử muốn chèn đoạn bị cắt trước phần tử đang ở chỉ số `t` của dãy **trước khi cắt**:

- Nếu `t≤l` thì `pos=t`.
- Nếu `t≥r` thì `pos=t-(r-l)`.
- Nếu `l<t<r` thì phần tử đích thuộc chính đoạn vừa cắt; cần định nghĩa rõ thao tác là **không đổi** hay có quy tắc khác.

Không nên dùng thẳng `t` làm `pos` mà quên điều chỉnh khi cắt một đoạn nằm trước vị trí đích.

### 9.4. Chi phí

Cắt–dán gồm một **số hằng phép split/merge**, nên:

- Thời gian kỳ vọng: **`O(\log(n+1))`**, với giả thiết priority ngẫu nhiên chuẩn.
- Trường hợp xấu nhất: **`O(n)`**.
- Bộ nhớ phụ đệ quy: kỳ vọng **`O(\log(n+1))`**, xấu nhất **`O(n)`**.
- Không cần cấp phát nút mới nếu chỉ di chuyển một đoạn; dữ liệu đoạn được **tái sử dụng**.

Không được gán chi phí theo độ dài đoạn `r-l` nếu thuật toán không thực sự duyệt từng phần tử. Đây là một lợi thế lớn so với dịch từng ô trong mảng.

## 10. Đảo đoạn bằng lazy propagation

### 10.1. Vấn đề với cách đảo trực tiếp

Một yêu cầu thường gặp trong trình soạn thảo hoặc bài toán biến đổi hoán vị:

```text
T = [A,B,C,D,E,F]
reverse([1,5)) → [A,E,D,C,B,F]
```

Nếu tách đoạn `[B,C,D,E]` rồi duyệt từng phần tử để đảo, chi phí sẽ phụ thuộc độ dài đoạn.

Trong **implicit treap**, có thể gắn một **thẻ đảo lười** (*lazy reverse flag*) vào gốc của cây con tương ứng đoạn, rồi hoãn việc thực sự đảo liên kết các nút sâu bên dưới.

### 10.2. Inorder đảo ngược hoạt động thế nào?

Một cây nhị phân với inorder:

```text
inorder(left) + [root] + inorder(right)
```

Khi đảo thứ tự toàn bộ cây con, kết quả phải là:

```text
reverse(inorder(right)) + [root] + reverse(inorder(left))
```

Vì vậy, ta có thể:

1. **Đổi chỗ hai con trái/phải**.
2. Đánh dấu hai con **cũng cần đảo** khi được truy cập sau này.

Điểm hay: **`size` và tổng các giá trị số không đổi khi chỉ đảo thứ tự**. Do đó có thể trì hoãn xử lý thẻ `rev` mà vẫn giữ hai loại tổng hợp này đúng.

### 10.3. Hàm `push`

Quy ước mã của bài: khi `node.rev=True`, dãy con của nút cần được xem là đã đảo, nhưng việc **hoán đổi các con và chuyển thẻ xuống** chưa được thực hiện vật lý.

```text
PUSH(node):
    if node.rev:
        swap(node.left, node.right)

        if node.left exists:
            node.left.rev = not node.left.rev
        if node.right exists:
            node.right.rev = not node.right.rev

        node.rev = False
```

Nếu đảo cùng một đoạn **hai lần**, hai thẻ đảo triệt tiêu nhau:

\[
reverse(reverse(S))=S.
\]

Dùng phép XOR boolean là hợp lý:

```text
node.rev ^= True
```

### 10.4. Các thao tác nào phải `push`?

Bất cứ thao tác nào **đi xuống hoặc thay đổi liên kết con theo thứ tự dãy** đều cần xử lý thẻ của nút hiện tại trước:

- `split`.
- `merge` ở nhánh được chọn làm gốc.
- Tìm phần tử theo chỉ số.
- Duyệt inorder để xuất dữ liệu.
- Các thuật toán duyệt cây con phụ thuộc thứ tự.

Ngược lại, **đọc `size(root)` hoặc `total(root)`** không cần đẩy thẻ nếu metadata là những đại lượng không phụ thuộc thứ tự.

Nếu sau này metadata phụ thuộc thứ tự, chẳng hạn **hash của chuỗi theo chiều trái–phải**, thao tác đảo có thể cần thêm **hash thuận/hash ngược** và quy tắc đổi tương ứng. Không thể mặc định mọi loại metadata đều bất biến dưới phép đảo.

### 10.5. Cách đảo `[l,r)`

```text
(A, Rest) = split(T, l)
(M, C)    = split(Rest, r-l)

if M != None:
    M.rev ^= True

T = merge(merge(A, M), C)
```

Đoạn `M` được đánh dấu đảo **chỉ ở gốc**, không cần duyệt `r-l` phần tử ngay lập tức.

Độ phức tạp kỳ vọng của thao tác: **`O(\log(n+1))`**, trường hợp xấu nhất `O(n)` vì split/merge; bước đánh dấu `rev` chỉ `O(1)`.

### 10.6. Ví dụ cộng dồn thẻ

```text
Ban đầu:            [1, 2, 3, 4, 5, 6]
Đảo [1,5):          [1, 5, 4, 3, 2, 6]
Đảo [2,4):          [1, 5, 3, 4, 2, 6]
Đảo [1,5) lần nữa:  [1, 2, 4, 3, 5, 6]
```

Các lần đảo đoạn **chồng lấn** không nhất thiết triệt tiêu toàn bộ tác động của nhau. Chỉ khi đảo đúng **cùng một đoạn liên tiếp hai lần, không có thao tác xen kẽ làm thay đổi dãy**, ta mới có thể khẳng định dãy trở về trạng thái trước đó.

## 11. Tăng cường thêm tổng cây con để tính tổng đoạn

Dù chủ đề chính là quản lý vị trí, ta có thể minh họa một metadata thứ hai để hiểu rõ nguyên tắc **cây tăng cường**.

Giả sử mỗi phần tử lưu một **số nguyên `value`**. Tại nút `u` lưu:

\[
total(\varnothing)=0,
\]

\[
\boxed{
total(u)=value(u)+total(u.left)+total(u.right).
}
\]

Tính lại hai trường:

```text
PULL(u):
    u.size = 1 + SIZE(u.left) + SIZE(u.right)
    u.total = u.value + TOTAL(u.left) + TOTAL(u.right)
```

### 11.1. Tổng đoạn `[l,r)`

Tách dãy:

```text
(A, Rest) = split(T, l)
(M, C) = split(Rest, r-l)

answer = TOTAL(M)

T = merge(merge(A, M), C)
return answer
```

Ta không phải cộng `r-l` phần tử: `total(M)` đã tổng hợp toàn bộ đoạn.

Ví dụ:

```text
T = [10,20,30,40,50]
range_sum(1,4) = 20+30+40 = 90
```

**Chi phí kỳ vọng `O(\log(n+1))`** cho split/merge, mặc dù đoạn dài có thể chứa rất nhiều phần tử.

### 11.2. Một truy vấn đọc có thể thay đổi hình dạng cây

Hàm tổng đoạn theo split–merge là **logic đọc**, nhưng có thể làm thay đổi **liên kết/shape nội bộ** trong quá trình tách rồi ghép trở lại. **Thứ tự dãy và các giá trị không đổi** khi hoàn thành, song không nên mặc định lời gọi là “read-only” về mặt con trỏ.

Trong hệ thống đồng thời hoặc cấu trúc bất biến (*persistent*), cần thiết kế cách truy vấn không sửa cấu trúc hoặc có cơ chế đồng bộ/phiên bản thích hợp.

### 11.3. Khi các phần tử là ký tự thay vì số

Nếu các giá trị là `"A"`, `"B"`,... thì trường tổng số nguyên `total` của mã minh họa không còn phù hợp. Khi đó:

- Có thể **chỉ lưu `size` và `rev`** nếu không cần tổng.
- Có thể thay bằng metadata khác, chẳng hạn hash chuỗi, số ký tự của một loại, hoặc thống kê có phép gộp phù hợp.
- Phải phân tích lại chi phí của phép gộp. Nối chuỗi Python trực tiếp sau mỗi thao tác có thể sao chép dữ liệu dài, không còn `O(1)` tại một nút.

Phần mã hoàn chỉnh ở dưới **chủ động giới hạn dữ liệu ở số nguyên** để công thức `total` luôn có nghĩa.

## 12. Python đầy đủ: implicit treap với split, merge và đảo đoạn

Đoạn mã sau dùng:

- **max-heap priority**, priority lớn hơn nằm cao hơn.
- Thứ tự dãy lấy bằng **inorder**.
- `size` để tách theo vị trí.
- `total` để tính tổng đoạn số nguyên.
- `rev` để đảo đoạn lười.
- Khóa priority là cặp `(random_bits, serial)` nhằm bảo đảm các nút được tạo bởi **cùng một đối tượng treap** có priority phân biệt ngay cả khi số ngẫu nhiên trùng.

**Giả thiết hiệu năng:** trong lý thuyết, lấy priority độc lập và phân biệt ngẫu nhiên. Cài đặt dùng 64 bit ngẫu nhiên kèm số thứ tự duy nhất; khi trùng 64 bit, thành phần thứ hai phá hòa nên phân phối không còn đúng mô hình liên tục lý tưởng ở trường hợp hiếm ấy. Không dùng bộ sinh ngẫu nhiên này như một công cụ bảo mật; nó chỉ phục vụ lựa chọn hình dạng cây.

### 12.1. Nút và các hàm tổng hợp

```python
import random


class Node:
    __slots__ = (
        "value", "priority", "left", "right",
        "size", "total", "rev"
    )

    def __init__(self, value, priority):
        self.value = value
        self.priority = priority
        self.left = None
        self.right = None

        self.size = 1
        self.total = value
        self.rev = False


def size_of(node):
    return 0 if node is None else node.size


def total_of(node):
    return 0 if node is None else node.total


def pull(node):
    """Tính lại metadata; hai cây con đã đúng."""
    if node is None:
        return

    node.size = 1 + size_of(node.left) + size_of(node.right)
    node.total = (
        node.value + total_of(node.left) + total_of(node.right)
    )


def push(node):
    """Đẩy thẻ đảo xuống trước khi dùng liên kết theo thứ tự."""
    if node is None or not node.rev:
        return

    node.left, node.right = node.right, node.left

    if node.left is not None:
        node.left.rev ^= True
    if node.right is not None:
        node.right.rev ^= True

    node.rev = False
```

**Ba tầng bất biến của nút:**

1. `size` là số nút trong cây con.
2. `total` là tổng giá trị số nguyên trong cây con.
3. Priority cha không nhỏ hơn priority con; thứ tự dãy là inorder **sau khi áp dụng ý nghĩa của các thẻ `rev`**.

Vì **đảo thứ tự không đổi số lượng hoặc tổng**, `pull` không cần quan tâm `rev`. Nhưng mọi thao tác sửa/đọc thứ tự con phải gọi `push` đúng lúc.

### 12.2. Hai phép lõi: `split` và `merge`

```python
def split(root, k):
    """Tách k phần tử đầu: trả (first_k, rest).

    Hàm nội bộ: tiền điều kiện 0 <= k <= size_of(root).
    """
    if root is None:
        return None, None

    push(root)
    left_size = size_of(root.left)

    if k <= left_size:
        first, remaining_left = split(root.left, k)
        root.left = remaining_left
        pull(root)
        return first, root

    else:
        first_right, rest = split(
            root.right, k - left_size - 1
        )
        root.right = first_right
        pull(root)
        return root, rest


def merge(a, b):
    """Nối inorder(a) trước inorder(b), dùng chung các nút."""
    if a is None:
        return b
    if b is None:
        return a

    if a.priority > b.priority:
        push(a)
        a.right = merge(a.right, b)
        pull(a)
        return a

    else:
        push(b)
        b.left = merge(a, b.left)
        pull(b)
        return b
```

**Điều kiện gọi `merge`:** `a` và `b` là hai cây hợp lệ, **không chia sẻ nút**, và người gọi muốn tất cả phần tử của `a` đứng trước tất cả phần tử của `b`. Không được ghép một cây với chính nó.

**Điều kiện gọi `split`:** `k` hợp lệ. Hàm **thay đổi liên kết tại các nút đầu vào** và trả hai gốc sở hữu các phần nút tách rời; biến gốc cũ không còn đại diện cho toàn bộ dãy.

### 12.3. Lớp bọc và kiểm tra chỉ số

```python
class ImplicitTreap:
    def __init__(self, values=(), seed=None):
        self.root = None
        self._rng = random.Random(seed)
        self._serial = 0

        # Xây bằng chèn cuối: O(n log n) kỳ vọng.
        for value in values:
            self.insert(len(self), value)

    def __len__(self):
        return size_of(self.root)

    def _new_node(self, value):
        if type(value) is not int:
            raise TypeError("Ví dụ này chỉ nhận giá trị nguyên")

        self._serial += 1
        priority = (self._rng.getrandbits(64), self._serial)
        return Node(value, priority)

    def _check_position(self, pos, allow_end=False):
        if type(pos) is not int:
            raise TypeError("Chỉ số phải là int")

        upper = len(self) if allow_end else len(self) - 1
        if not 0 <= pos <= upper:
            raise IndexError("Vị trí nằm ngoài dãy")

    def _check_range(self, left, right):
        if type(left) is not int or type(right) is not int:
            raise TypeError("Chỉ số phải là int")
        if not 0 <= left <= right <= len(self):
            raise IndexError("Đoạn [left, right) không hợp lệ")

    def insert(self, pos, value):
        """Chèn trước chỉ số pos; pos == len hợp lệ."""
        self._check_position(pos, allow_end=True)

        fresh = self._new_node(value)
        left, right = split(self.root, pos)
        self.root = merge(merge(left, fresh), right)

    def erase(self, pos):
        """Xóa đúng một phần tử tại pos; trả giá trị đã xóa."""
        self._check_position(pos)

        left, rest = split(self.root, pos)
        middle, right = split(rest, 1)

        # middle có đúng một nút theo hợp đồng split.
        removed = middle.value
        self.root = merge(left, right)
        return removed

    def at(self, pos):
        """Truy cập bằng kích thước cây trái, không split."""
        self._check_position(pos)

        node = self.root
        index = pos

        while node is not None:
            push(node)
            left_size = size_of(node.left)

            if index < left_size:
                node = node.left
            elif index == left_size:
                return node.value
            else:
                index -= left_size + 1
                node = node.right

        raise RuntimeError("Metadata size không nhất quán")

    def reverse(self, left, right):
        """Đảo đoạn chỉ số nửa mở [left, right)."""
        self._check_range(left, right)

        a, rest = split(self.root, left)
        middle, c = split(rest, right - left)

        if middle is not None:
            middle.rev ^= True

        self.root = merge(merge(a, middle), c)

    def move(self, left, right, pos):
        """Cắt [left, right), dán tại pos SAU KHI cắt."""
        self._check_range(left, right)

        remaining_length = len(self) - (right - left)
        if type(pos) is not int:
            raise TypeError("Chỉ số pos phải là int")
        if not 0 <= pos <= remaining_length:
            raise IndexError("pos nằm ngoài dãy sau khi cắt")

        a, rest = split(self.root, left)
        middle, c = split(rest, right - left)
        without = merge(a, c)

        before, after = split(without, pos)
        self.root = merge(merge(before, middle), after)

    def range_sum(self, left, right):
        """Tổng số nguyên của đoạn [left, right)."""
        self._check_range(left, right)

        a, rest = split(self.root, left)
        middle, c = split(rest, right - left)
        answer = total_of(middle)

        # Ghép lại cả khi chỉ đọc giá trị tổng hợp.
        self.root = merge(merge(a, middle), c)
        return answer

    def to_list(self):
        """Duyệt inorder, đẩy lazy trước khi chọn con."""
        result = []
        stack = []
        node = self.root

        while node is not None or stack:
            while node is not None:
                push(node)
                stack.append(node)
                node = node.left

            node = stack.pop()
            result.append(node.value)
            node = node.right

        return result
```

Cách tạo treap bằng vòng lặp `insert(len(self), value)` rất dễ hiểu và minh họa đúng các thao tác. Nó có **`O(n\log(n+1))` thời gian kỳ vọng** để xây `n` phần tử; có thể xây treap từ một dãy và các priority đã biết trong `O(n)` bằng thuật toán Cartesian stack, nhưng đó là một kỹ thuật tối ưu riêng.

### 12.4. Minh họa chèn và xóa

```python
t = ImplicitTreap([10, 20, 30, 40], seed=42)

print(t.to_list())       # [10, 20, 30, 40]

t.insert(2, 99)
print(t.to_list())       # [10, 20, 99, 30, 40]

print(t.at(2))           # 99

removed = t.erase(1)
print(removed)           # 20
print(t.to_list())       # [10, 99, 30, 40]
```

Mã lưu **mỗi vị trí là một nút**, nên hai giá trị giống nhau không bị gộp. Ví dụ:

```python
t = ImplicitTreap([7, 7, 9], seed=7)

assert t.erase(1) == 7
assert t.to_list() == [7, 9]
```

### 12.5. Cắt–dán, đảo đoạn và tổng đoạn

```python
t = ImplicitTreap([10, 20, 30, 40, 50, 60], seed=9)

# Cắt [20,30,40], còn [10,50,60]; dán ở cuối.
t.move(1, 4, 3)
print(t.to_list())       # [10, 50, 60, 20, 30, 40]

# Đảo các vị trí 1,2,3,4.
t.reverse(1, 5)
print(t.to_list())       # [10, 30, 20, 60, 50, 40]

print(t.range_sum(1, 4)) # 30 + 20 + 60 = 110
print(t.at(4))           # 50

t.insert(2, 99)
print(t.to_list())       # [10, 30, 99, 20, 60, 50, 40]

assert t.erase(3) == 20
print(t.to_list())       # [10, 30, 99, 60, 50, 40]
```

**Không có hình dạng cây cố định** trong ví dụ này. Seed chỉ cố định chuỗi ưu tiên ngẫu nhiên để tiện tái hiện khi thực hành; không có yêu cầu gốc phải mang một giá trị cụ thể. Điều được kiểm chứng là **thứ tự dãy và các tổng hợp đúng**, không phải việc cây có hình vẽ giống nhau.

### 12.6. Các trường hợp biên

```python
t = ImplicitTreap([], seed=1)

assert len(t) == 0
assert t.to_list() == []
assert t.range_sum(0, 0) == 0

t.insert(0, -5)
assert t.to_list() == [-5]
assert t.at(0) == -5
assert t.range_sum(0, 1) == -5

t.reverse(0, 1)
assert t.to_list() == [-5]

t.move(0, 1, 0)
assert t.to_list() == [-5]

assert t.erase(0) == -5
assert t.to_list() == []

# Các thao tác ngoài phạm vi phải báo lỗi.
try:
    t.at(0)
except IndexError:
    pass
else:
    raise AssertionError("at(0) trên cây rỗng phải lỗi")

try:
    t.insert(2, 7)
except IndexError:
    pass
else:
    raise AssertionError("Chèn tại pos=2 trên dãy rỗng phải lỗi")
```

Các `assert` là minh họa để người học tự thực hành, **không phải kết quả của một lần chạy kiểm thử tự động trong quy trình biên soạn học liệu**.

## 13. Xác thực các bất biến mà không tin metadata đang lưu

Khi viết cấu trúc dữ liệu tăng cường, một lỗi trong `pull` hoặc `push` có thể không làm lộ sai sót ngay tại thao tác vừa chạy. Vì vậy nên có một hàm kiểm tra độc lập để so sánh:

1. Mỗi đối tượng nút xuất hiện đúng một lần; không có chu trình hoặc dùng chung một nút ở hai vị trí.
2. Priority của cha **không nhỏ hơn** priority của từng con.
3. Trường `size` bằng số nút **tính lại từ cấu trúc thực**.
4. Trường `total` bằng tổng các giá trị số **tính lại từ cấu trúc thực**.
5. Thẻ `rev` là boolean; sự đảo chưa đẩy không ảnh hưởng bất biến `size` và `total`.

### 13.1. Validator hậu thứ tự không làm thay đổi cây

```python
def validate_treap(root):
    """Kiểm tra size, total, heap và tính chất cây.

    Không cần push: đảo thứ tự không đổi số nút hoặc tổng.
    """
    if root is None:
        return True

    seen = set()
    actual = {}
    frames = [(root, False)]

    while frames:
        node, ready = frames.pop()
        if node is None:
            continue
        if not isinstance(node, Node):
            return False

        if not ready:
            marker = id(node)
            if marker in seen:
                return False
            seen.add(marker)

            if type(node.rev) is not bool:
                return False

            for child in (node.left, node.right):
                if child is not None:
                    if not isinstance(child, Node):
                        return False
                    if child.priority > node.priority:
                        return False

            frames.append((node, True))
            frames.append((node.right, False))
            frames.append((node.left, False))

        else:
            left_size, left_total = actual.get(
                node.left, (0, 0)
            )
            right_size, right_total = actual.get(
                node.right, (0, 0)
            )

            expected_size = 1 + left_size + right_size
            expected_total = (
                node.value + left_total + right_total
            )

            if node.size != expected_size:
                return False
            if node.total != expected_total:
                return False

            actual[node] = (expected_size, expected_total)

    return True
```

**Tại sao validator không cần gọi `push`?** Vì `size` và `total` là những thống kê **không phụ thuộc thứ tự**. Đảo đoạn có thể đổi vị trí trái/phải khi đẩy lazy, nhưng số nút/tổng của toàn bộ cây con vẫn như cũ. Hàm xác thực này **không kiểm tra một thứ tự inorder kỳ vọng từ bên ngoài**; điều đó cần đối chiếu riêng với dãy tham chiếu.

Chi phí với `n` nút hợp lệ: **`O(n)` thời gian, `O(n)` bộ nhớ phụ** cho bảng tổng hợp độc lập, tập định danh và stack. Không nên gọi validator `O(n)` sau **mọi** thao tác trong đường vận hành mà vẫn tuyên bố tổng chi phí mỗi thao tác là `O(\log n)`.

### 13.2. Kiểm tra đối chiếu với danh sách thường

Một cách tự kiểm tra dễ hiểu là duy trì một **danh sách Python tham chiếu**:

```python
values = [10, 20, 30, 40, 50, 60]
reference = values.copy()

t = ImplicitTreap(values, seed=123)
assert validate_treap(t.root)

# Chèn.
t.insert(2, 99)
reference.insert(2, 99)
assert t.to_list() == reference
assert validate_treap(t.root)

# Đảo đoạn.
t.reverse(1, 6)
reference[1:6] = list(reversed(reference[1:6]))
assert t.to_list() == reference
assert validate_treap(t.root)

# Tổng đoạn.
assert t.range_sum(1, 5) == sum(reference[1:5])
assert t.to_list() == reference
assert validate_treap(t.root)

# Cắt–dán, pos tính trên dãy sau cắt.
l, r, pos = 1, 4, 2
segment = reference[l:r]
del reference[l:r]
reference[pos:pos] = segment

t.move(l, r, pos)
assert t.to_list() == reference
assert validate_treap(t.root)
```

Danh sách tham chiếu có thể tốn `O(n)` cho chèn/xóa/đảo đoạn, nhưng điều này chấp nhận được khi nó dùng làm **mốc kiểm thử**, không phải cấu trúc sản xuất tối ưu.

### 13.3. Kiểm tra đúng thứ tự, không chỉ tổng

Hai dãy:

```text
[1, 2, 3, 4] và [4, 3, 2, 1]
```

đều có:

```text
size = 4
total = 10
```

Vì vậy `size` và `total` đúng **không đủ chứng minh thứ tự dãy đúng**, đặc biệt khi có thẻ `rev`. Phải đối chiếu inorder sau khi đẩy lazy với một thứ tự tham chiếu độc lập.

**Bài học tổng quát:** metadata chỉ chứng minh những bất biến mà chúng thật sự mô tả. Không thể suy ra một thuộc tính khác nếu chưa có lập luận tương ứng.

## 14. Chứng minh tính đúng của `split`

### 14.1. Định nghĩa cần giữ

Cho `T` biểu diễn dãy `S` có `n` phần tử. Với `0≤k≤n`:

\[
split(T,k)=(A,B)
\]

phải thỏa:

\[
inorder(A)=S[0:k],
\]

\[
inorder(B)=S[k:n].
\]

Ngoài ra, `A`, `B` phải là hai treap hợp lệ và **không dùng chung nút**.

### 14.2. Cơ sở đệ quy

Nếu `T=None`, dãy rỗng nên chỉ có `k=0` hợp lệ. Trả `(None,None)` là đúng.

### 14.3. Bước quy nạp

Giả sử `T` có gốc `u`, cây trái chứa `L` phần tử, và kết quả split trên cây con được gọi đệ quy là đúng.

Sau `push(u)`, thứ tự trái–phải vật lý phản ánh đúng thứ tự cần xét.

**Nếu `k≤L`:**

- `k` phần tử đầu đều nằm trong cây trái.
- Split cây trái thành `A` chứa `k` phần tử đầu và `B_L` là phần còn lại.
- Gắn `u.left=B_L`.
- Vì gốc `u` và toàn bộ cây phải thuộc phần sau, trả `(A,u)` đúng thứ tự.

**Nếu `k>L`:**

- Nửa đầu gồm toàn bộ `L` phần tử trái, gốc `u` và `k-L-1` phần tử đầu của cây phải.
- Split cây phải thành `A_R` và `B`.
- Gắn `u.right=A_R`.
- Trả `(u,B)` đúng thứ tự.

Trong cả hai trường hợp, `pull(u)` khôi phục `size/total` từ hai cây con đã đúng. Vì chỉ loại/gắn các nhánh theo thứ tự cũ và không thay priority, bất biến max-heap còn đúng.

Do đó thuật toán split đúng bằng **quy nạp trên kích thước cây**.

## 15. Chứng minh tính đúng của `merge`

### 15.1. Tiền điều kiện

Giả sử `A` và `B` là hai treap hợp lệ **rời nhau**, và kết quả mong muốn là:

\[
S=inorder(A)+inorder(B).
\]

### 15.2. Cơ sở

Nếu một cây rỗng, trả cây còn lại. Thứ tự nối là hiển nhiên và các bất biến của cây còn lại không đổi.

### 15.3. Bước quy nạp

Nếu `A.root` có priority lớn hơn:

- Chọn `A.root` làm gốc mới để giữ bất biến heap.
- Chỉ cần nối phần tử sau `A.root`: đó là `merge(A.right,B)`.
- Theo giả thiết quy nạp, phần ghép này có inorder là `inorder(A.right)+inorder(B)`.
- Kết hợp với `A.left` và giá trị gốc, inorder toàn cây là `inorder(A)+inorder(B)`.
- `pull(A.root)` làm metadata đúng.

Nếu `B.root` thắng, lập luận đối xứng qua `merge(A,B.left)`.

Vì priority gốc được chọn lớn hơn mọi priority của hai cây đầu vào, và cây con kết quả cũng giữ bất biến heap, phép ghép trả một treap hợp lệ với **đúng thứ tự nối**.

### 15.4. Hệ quả cho chèn, xóa, cắt–dán và đảo

- **Chèn:** split đúng vị trí, ghép `A+[x]+B` nên thêm đúng một phần tử tại chỉ số `i`.
- **Xóa:** tách `A+[x]+B`, bỏ cây chứa đúng một nút `x`, ghép `A+B`.
- **Cắt–dán:** phân hoạch `A+M+C`, bỏ `M` rồi ghép lại ở vị trí `pos` của `A+C`.
- **Đảo:** split đúng đoạn `M`, thẻ `rev` tạo inorder `reverse(M)`, rồi ghép đúng thứ tự.

Các thao tác cấp cao đúng khi `split`, `merge`, `push`, `pull` và hợp đồng chỉ số đều đúng.

## 16. Tại sao thời gian kỳ vọng là logarit?

### 16.1. Treap theo vị trí là một Cartesian tree

Với thứ tự phần tử cố định `1,2,\ldots,n` và priority phân biệt, treap có cấu trúc duy nhất nếu yêu cầu:

1. Duyệt inorder trả về đúng thứ tự phần tử.
2. Priority của cha lớn hơn mọi con.

Gốc là phần tử có priority lớn nhất trong dãy. Hai phía của nó được xây đệ quy theo cùng quy tắc. Cấu trúc này còn gọi là một **Cartesian tree** theo thứ tự vị trí và priority.

### 16.2. Trực giác ngẫu nhiên

Nếu các priority là độc lập và có thứ tự ngẫu nhiên đều, phần tử làm gốc phân bố đều trên các vị trí. Trong các cây con, quy tắc tiếp tục tương tự.

Điều đó ngăn một thứ tự giá trị như:

```text
[1, 2, 3, 4, 5, 6, 7, ...]
```

tự động làm cây suy biến như khi chèn tăng dần vào BST không tự cân bằng theo **giá trị**. Implicit treap **không dùng giá trị để quyết định gốc**.

### 16.3. Một phép tính kỳ vọng về độ sâu

Với nút tại chỉ số `i` (0-based) trong `n` nút, một nút `j\ne i` là tổ tiên của `i` khi priority của `j` là lớn nhất trong đoạn vị trí từ `i` tới `j`.

Dưới giả thiết thứ tự priority ngẫu nhiên đều:

\[
P(j\text{ là tổ tiên của }i)=\frac{1}{|i-j|+1}.
\]

Vì vậy, độ sâu kỳ vọng của nút `i` thỏa:

\[
E[depth(i)]
=\sum_{d=1}^{i}\frac1{d+1}
+\sum_{d=1}^{n-1-i}\frac1{d+1}
=O(\log(n+1)).
\]

Đây là một lập luận trực quan cho việc những đường đi có độ dài kỳ vọng logarit. Chặn trên chiều cao kỳ vọng cũng là một tính chất đã biết của treap ngẫu nhiên; chứng minh đầy đủ đòi thêm phân tích xác suất, không chỉ cộng độ sâu của một nút.

### 16.4. Phạm vi của bảo đảm

**Kỳ vọng không đồng nghĩa bảo đảm tuyệt đối.**

- Priority ngẫu nhiên cho hiệu năng tốt trong kỳ vọng khi lựa chọn thứ tự thao tác **không cố tình khai thác các priority đã thấy**.
- Một cấu hình priority bất lợi vẫn có thể tạo chiều cao `\Theta(n)`.
- Nếu dùng priority có mẫu kém, có tương quan mạnh hoặc được chọn có chủ đích, giả thiết hiệu năng kỳ vọng có thể không còn phù hợp.
- Nếu thao tác được lựa chọn **thích nghi theo cấu trúc/priority nội bộ**, cần xem lại giả thiết xác suất của mô hình phân tích.

Bài dùng `random.Random` để minh họa thuật toán, không tuyên bố nó chống được đối thủ cố tình điều khiển đầu vào.

## 17. Phân tích thời gian–bộ nhớ theo thao tác

Ký hiệu `n` là độ dài dãy, `h` là chiều cao treap, `m=r-l` là độ dài đoạn thao tác.

| Thao tác | Số split/merge | Thời gian theo chiều cao | Kỳ vọng khi priority ngẫu nhiên | Trường hợp xấu nhất |
|---|---:|---:|---:|---:|
| `at(i)` | 0 | `O(h+1)` | `O(\log(n+1))` | `O(n)` |
| `insert(i,x)` | 1 split + 2 merge | `O(h+1)` theo tổng số đường | `O(\log(n+1))` | `O(n)` |
| `erase(i)` | 2 split + 1 merge | `O(h+1)` | `O(\log(n+1))` | `O(n)` |
| `reverse(l,r)` với lazy | 2 split + 2 merge | `O(h+1)` | `O(\log(n+1))` | `O(n)` |
| `move(l,r,pos)` | 3 split + 3 merge | `O(h+1)` | `O(\log(n+1))` | `O(n)` |
| `range_sum(l,r)` | 2 split + 2 merge | `O(h+1)` | `O(\log(n+1))` | `O(n)` |
| `to_list()` | 0 | `O(n)` | `O(n)` | `O(n)` |
| Dựng bằng `n` lần insert cuối | `O(n)` lần thao tác | — | `O(n\log(n+1))` | `O(n^2)` |

**Lưu ý:** trong các thao tác gồm một số hằng lần split/merge, mỗi đường nằm trong một treap có tối đa khoảng `n+1` nút. Do đó tổng thời gian kỳ vọng vẫn logarit. Các chặn trên theo `h` trong bảng hiểu là chặn theo chiều cao lớn nhất của các treap trung gian liên quan.

### 17.1. Bộ nhớ

- Mỗi phần tử là một nút lưu `value,priority,left,right,size,total,rev`, nên **`O(n)` bộ nhớ** toàn cấu trúc.
- `split/merge` đệ quy cần `O(h+1)` khung gọi: **kỳ vọng `O(\log(n+1))`**, xấu nhất `O(n)`.
- `at(i)` dùng vòng lặp nên **`O(1)` bộ nhớ phụ**.
- `to_list()` tạo danh sách đầu ra **`O(n)`** và stack duyệt **`O(h+1)`**.
- `move/reverse` không cấp phát nút mới; `insert` cấp phát một nút, `erase` loại một nút.
- Kích thước số nguyên trong Python có thể tăng theo giá trị; các bảng Big-O giả định giá trị và thao tác số học kích thước giới hạn.

### 17.2. Khi nào dãy ngắn nên dùng mảng?

Nếu `n` nhỏ, thao tác chủ yếu là truy cập trực tiếp, hoặc hầu như không sửa ở giữa, **mảng/list** thường đơn giản và nhanh hơn trong thực tế do dữ liệu liên tiếp trong bộ nhớ và chi phí con trỏ thấp.

Treap hợp lý hơn khi:

- Cần **nhiều** thao tác cắt–ghép các đoạn dài.
- Chèn/xóa ở vị trí bất kỳ xảy ra thường xuyên.
- Cần đảo đoạn hoặc tổng đoạn động.
- Có thể chấp nhận chi phí nút/cấp phát và phân tích kỳ vọng.

Không nên coi treap là cấu trúc “mặc định tốt hơn mảng” cho mọi bài toán.

## 18. Mở rộng: các metadata và phép lazy khác

### 18.1. Tổng, min, max, hash

Một implicit treap có thể lưu thêm:

- `sum`: tổng số của dãy con.
- `min`, `max`: giá trị cực tiểu/cực đại của cây con.
- `count_condition`: số phần tử thỏa một điều kiện.
- `hash_forward/hash_reverse`: hash theo thứ tự thuận/ngược, nếu cần so sánh chuỗi con.

Để tích hợp đúng, phải viết:

1. **Bất biến** của metadata.
2. Công thức `pull` từ hai con.
3. Ảnh hưởng của mỗi thao tác lazy lên metadata.
4. Thứ tự `push` trước khi sử dụng liên kết cây.
5. Độ phức tạp thật của phép gộp.

Ví dụ, với `min`, đảo đoạn **không làm thay đổi giá trị nhỏ nhất**; với một hash theo thứ tự, đảo đoạn **thường làm thay đổi hash**, phải lưu hoặc tính hash ngược phù hợp.

### 18.2. Lazy cộng một hằng trên đoạn

Nếu muốn cộng `delta` vào mọi phần tử trong đoạn, có thể lưu thẻ `lazy_add`. Với nút `u` và số phần tử cây con `size(u)`:

```text
APPLY_ADD(u, delta):
    u.value += delta
    u.total += delta * u.size
    u.lazy_add += delta
```

Khi đẩy xuống:

```text
PUSH_ADD(u):
    nếu lazy_add != 0:
        APPLY_ADD(u.left, lazy_add)  nếu con trái tồn tại
        APPLY_ADD(u.right, lazy_add) nếu con phải tồn tại
        lazy_add = 0
```

Bài chỉ minh họa **quy tắc toán học**; mã hoàn chỉnh ở mục 12 **chưa tích hợp `lazy_add`**.

Khi có đồng thời `rev` và `lazy_add`, cần thiết kế thứ tự đẩy thẻ và kiểm tra chúng có giao hoán theo ngữ nghĩa hay không. Cộng cùng một hằng vào mọi phần tử và đảo thứ tự **giao hoán về giá trị cuối**, nhưng những loại cập nhật khác (gán, nhân, hàm biến đổi phụ thuộc vị trí) có thể cần quy tắc hợp thành phức tạp hơn.

### 18.3. Treap persistent (bất biến theo phiên bản)

Hàm `split/merge` trong bài **sửa con trỏ trực tiếp**. Nếu cần giữ nhiều phiên bản dãy cho undo/redo, có thể dùng *persistent treap* với **path copying**:

- Mỗi thao tác chỉ sao chép các nút trên đường bị sửa.
- Những cây con không đổi có thể được chia sẻ an toàn nếu **bất biến/không bị sửa về sau**.
- Bộ nhớ thêm kỳ vọng thường `O(\log n)` nút cho một thao tác đường đi, nhưng phải tính đúng số nhánh bị sao chép và cách xử lý lazy.
- `push` cũng không được trực tiếp sửa một nút được chia sẻ giữa các phiên bản.

**Không thể** lấy nguyên mã treap mutating trong bài rồi chỉ giữ lại `old_root` để mong có các bản snapshot bất biến: các thao tác sau có thể sửa chính các nút mà gốc cũ đang trỏ tới.

### 18.4. Xây treap hàng loạt bằng Cartesian stack

Nếu đã có dãy theo thứ tự inorder và sinh trước priority cho mọi phần tử, có thể xây Cartesian tree trong **`O(n)`** bằng một **stack đơn điệu theo priority**:

- Đi qua các nút từ trái sang phải theo thứ tự dãy.
- Dùng stack để giữ chuỗi priority giảm dần.
- Nút mới lấy những nút nhỏ hơn priority của nó làm cây trái thích hợp, đồng thời được gắn làm con phải của nút còn lại trên stack.
- Sau khi xây liên kết, tính metadata bằng hậu thứ tự.

Cách này tránh lặp `n` lần split/merge, nhưng có thêm logic dựng cây và không làm thay đổi bất biến sử dụng về sau. Khi học các thao tác dãy động, **xây bằng chèn cuối** thường dễ theo dõi hơn.

## 19. Những lỗi cài đặt thường gặp

1. **Sử dụng giá trị phần tử như khóa BST.** Implicit treap phải giữ **thứ tự vị trí**, không sắp giá trị.
2. **Lưu chỉ số tuyệt đối bất biến ở mỗi nút.** Chèn/xóa/cắt–dán làm hàng loạt vị trí đổi; hãy suy chỉ số từ `size(left)`.
3. **Nhầm `size` với số con trực tiếp.** `size` gồm toàn bộ nút trong cây con.
4. **Quên cập nhật `size` sau đổi liên kết.** `split/merge/at` có thể định hướng sai.
5. **Quên cập nhật `total` sau split/merge.** Truy vấn tổng đoạn có thể sai dù thứ tự dãy đúng.
6. **Gọi `pull` trước khi sửa xong các con.** Metadata được tính từ cấu trúc cũ.
7. **Quên `push` trước khi rẽ nhánh theo chỉ số khi có `rev`.** Trái/phải vật lý có thể chưa phản ánh dãy đã đảo.
8. **Đảo trực tiếp hai con mà không chuyển thẻ xuống con khi đẩy lazy.** Chỉ đảo ở một mức không đủ đảo cả cây con.
9. **Đẩy `rev` nhiều lần mà không tắt thẻ ở cha.** Có thể đảo lặp không mong muốn.
10. **Không dùng XOR cho nhiều lần đảo cùng một đoạn.** Hai lần đảo phải triệt tiêu nhau.
11. **Giả định metadata nào cũng không đổi khi đảo.** `size/sum/min/max` không phụ thuộc thứ tự; hash thuận thường phụ thuộc thứ tự.
12. **Dùng `split(root,k)` với `k<0` hoặc `k>n`.** API phải kiểm tra biên.
13. **Nhầm `[l,r)` với đoạn gồm cả `r`.** Độ dài cần tách là `r-l`.
14. **Khi `k>L` trong split, quên trừ `L+1`.** Bị lệch một vị trí vì không tính nút gốc.
15. **Trong merge, ghép cây `B` vào con trái của `A` khi `A` thắng priority.** Phải ghép vào **con phải** để `A` đứng trước `B`.
16. **Ghép hai cây có chung nút.** Có thể tạo chu trình/DAG, làm hỏng cấu trúc treap.
17. **Tái dùng gốc đầu vào như thể split không phá hủy cây ban đầu.** Split theo con trỏ là thao tác mutating.
18. **Không gán lại `root` từ kết quả merge.** Có thể mất các nút khỏi cây đang truy cập.
19. **Dùng chỉ số đích trước khi cắt làm `pos` sau khi cắt.** Dẫn tới dán sai vị trí.
20. **Không xác định nghĩa của đích nằm ngay trong đoạn bị cắt.** Hợp đồng API phải rõ.
21. **Kết luận di chuyển đoạn dài mất `O(m)` vì có `m` phần tử.** Split–merge chỉ sửa đường cây, không duyệt từng phần tử.
22. **Cho rằng treap bảo đảm logarit ở mọi cấu hình.** Priority bất lợi có thể tạo đường dài `O(n)`.
23. **Dùng bộ sinh priority cố định/tương quan với chỉ số rồi vẫn áp chặn kỳ vọng chuẩn.** Bảo đảm xác suất cần giả thiết ngẫu nhiên phù hợp.
24. **Nhầm priority thuật toán với “ưu tiên nghiệp vụ”.** Giá trị dữ liệu và priority cấu trúc có vai trò khác nhau.
25. **Quên bộ nhớ stack đệ quy trong Python.** Treap suy biến có thể chạm giới hạn đệ quy.
26. **Đọc tổng đoạn bằng split mà quên merge lại.** Gây mất một phần dãy khỏi gốc hiện tại.
27. **Cho rằng một truy vấn tổng đoạn dùng split là hoàn toàn không sửa cấu trúc.** Nó có thể thay liên kết bên trong rồi ghép lại.
28. **Tin rằng `size` và `total` đúng đủ chứng minh thứ tự dãy đúng.** Các dãy đảo có thể cùng số nút/tổng.
29. **Dùng `to_list` trong mọi thao tác sản xuất để xác minh rồi tuyên bố cập nhật `O(\log n)`.** Duyệt toàn dãy là `O(n)`.
30. **Dùng mã cộng tổng số nguyên cho chuỗi mà không đổi metadata.** Công thức `total=value+...` không đúng với mọi kiểu dữ liệu.
31. **Giữ `old_root` để làm undo trong khi thao tác vẫn sửa nút tại chỗ.** Cần persistent path copying hoặc snapshot thật.
32. **Không đồng bộ khi nhiều luồng đọc/ghi.** Một truy vấn có thể thấy cây vừa tách nhưng chưa ghép, hoặc thẻ lazy đang đẩy dở.
33. **Quên dọn liên kết của nút bị xóa nếu có tham chiếu ngoài.** API nội bộ cần quy tắc quyền sở hữu, tránh tiếp tục sửa nút đã không thuộc dãy.
34. **Nhầm kỳ vọng chiều cao với bảo đảm độc lập của mọi chuỗi thao tác thích nghi.** Phải nêu giả thiết phân phối priority và quyền quan sát của tác nhân chọn thao tác.

## 20. Bài tập thực hành có đáp án

### Bài 1. Xác định thứ tự inorder

Cho cây:

```text
        C
       / \
      A   E
       \ / \
       B D F
```

Duyệt inorder cho dãy nào?

**Đáp án:** **`A,B,C,D,E,F`**. Treap theo vị trí dùng chính thứ tự inorder để biểu diễn dãy.

### Bài 2. Kiểm tra bất biến priority

Trong cây trên, các priority lần lượt `A=70, B=50, C=90, D=60, E=80, F=40`. Cây có phải max-heap theo priority không?

**Đáp án:** **Có.** `C=90` lớn hơn `A=70` và `E=80`; `A=70>B=50`; `E=80>D=60,F=40`.

### Bài 3. Tính kích thước cây con

Trong cây trên, `size(A)`, `size(E)` và `size(C)` lần lượt bằng bao nhiêu?

**Đáp án:** **`2,3,6`**. Công thức `size(u)=1+size(left)+size(right)`.

### Bài 4. Truy cập phần tử theo chỉ số

Trong dãy `[A,B,C,D,E,F]`, tìm phần tử ở chỉ số `4` bằng treap trong Bài 1. Cần rẽ nhánh nào?

**Đáp án:** Tại `C`, `size(left)=2` nên đi phải với chỉ số mới `4-2-1=1`. Tại `E`, `size(left)=1` nên trả **`E`**.

### Bài 5. Split theo số phần tử

Cho dãy `[A,B,C,D,E,F]`. Kết quả `split(T,3)` là gì?

**Đáp án:** Hai dãy **`[A,B,C]`** và **`[D,E,F]`**.

### Bài 6. Split ở biên

Với một treap `T` có `n` phần tử, `split(T,0)` và `split(T,n)` trả gì?

**Đáp án:** `split(T,0)=([],T)` và `split(T,n)=(T,[])`, theo nghĩa dãy; ở mức con trỏ là hai cây rời nhau với một cây rỗng.

### Bài 7. Vì sao split trừ `L+1`?

Tại gốc có cây trái chứa `L=4` phần tử. Muốn tách `k=7` phần tử đầu, cần lấy bao nhiêu phần tử từ cây phải?

**Đáp án:** `k'=7-4-1=2`. Số `1` là chính nút gốc.

### Bài 8. Kết quả merge

Nếu `A=[2,7,7]` và `B=[1,9]`, `merge(A,B)` tạo dãy nào? Có tự sắp giá trị không?

**Đáp án:** **`[2,7,7,1,9]`**. Merge của implicit treap là **nối thứ tự**, không phải merge sắp xếp như merge sort.

### Bài 9. Chèn trước chỉ số

Dãy `[10,20,30,40]`, chèn `99` tại `pos=2`. Kết quả?

**Đáp án:** **`[10,20,99,30,40]`**.

### Bài 10. Xóa khi giá trị trùng

Dãy `[7,7,9]`, xóa phần tử ở chỉ số `1`. Kết quả là gì?

**Đáp án:** **`[7,9]`**. Chỉ xóa **một vị trí**, không xóa mọi phần tử bằng `7`.

### Bài 11. Độ dài đoạn

Đoạn chỉ số nửa mở `[2,7)` có bao nhiêu phần tử?

**Đáp án:** **`7-2=5`** phần tử, tại các chỉ số `2,3,4,5,6`.

### Bài 12. Cắt đoạn

Dãy `[A,B,C,D,E,F]`, cắt `[1,4)`. Đoạn bị cắt và dãy còn lại?

**Đáp án:** Đoạn **`[B,C,D]`**, còn lại **`[A,E,F]`**.

### Bài 13. Dán theo vị trí sau khi cắt

Từ Bài 12, dán đoạn bị cắt tại `pos=3` của dãy còn lại. Kết quả?

**Đáp án:** **`[A,E,F,B,C,D]`**.

### Bài 14. Đích tính theo dãy ban đầu

Dãy dài `8`, cắt `[2,5)` rồi muốn dán trước phần tử ban đầu có chỉ số `t=7`. `pos` trong dãy sau khi cắt là bao nhiêu?

**Đáp án:** Vì `t≥r`, `pos=t-(r-l)=7-3=4`.

### Bài 15. Đảo đoạn nửa mở

Dãy `[A,B,C,D,E,F]`, đảo `[1,5)`. Kết quả?

**Đáp án:** **`[A,E,D,C,B,F]`**. Các vị trí `1` đến `4` được đảo, vị trí `5` giữ nguyên.

### Bài 16. Đảo hai lần

Nếu không có thao tác xen kẽ, đảo đúng cùng đoạn `[l,r)` hai lần thì dãy cuối thế nào?

**Đáp án:** **Trở về dãy ban đầu**, vì `reverse(reverse(S))=S`. Đó là lý do thẻ boolean có thể hợp thành bằng XOR.

### Bài 17. Vì sao cần `push`?

Một nút đang có `rev=True`. Nếu `split` dùng ngay `size(left)` và liên kết trái/phải mà không đẩy thẻ, lỗi có thể là gì?

**Đáp án:** Liên kết vật lý có thể chưa phản ánh **thứ tự dãy đã đảo**, khiến thuật toán tách sai những phần tử đứng trước/sau vị trí `k`.

### Bài 18. Lazy đảo có đổi tổng không?

Một đoạn số nguyên `[3,9,-2,7]` được đảo thành `[7,-2,9,3]`. `size` và `total` có đổi không?

**Đáp án:** **Không.** `size=4` và `total=17` trước và sau đảo. Đảo thay **thứ tự**, không thay tập phần tử.

### Bài 19. Tổng đoạn

Dãy `[10,20,30,40,50]`, tính `range_sum(1,4)`.

**Đáp án:** **`20+30+40=90`**.

### Bài 20. Tổng đoạn rỗng

Với mọi dãy số và `l=r` hợp lệ, `range_sum(l,r)` trả bao nhiêu trong hợp đồng bài này?

**Đáp án:** **`0`**, vì đoạn `[l,l)` không chứa phần tử nào và `0` là phần tử trung hòa của phép cộng.

### Bài 21. Kỳ vọng và trường hợp xấu nhất

Nếu priority ngẫu nhiên độc lập, thời gian kỳ vọng của `split/merge` là bao nhiêu? Có bảo đảm đúng bậc này cho mọi cấu hình không?

**Đáp án:** **`O(\log(n+1))` kỳ vọng** dưới giả thiết phân phối priority phù hợp. Không bảo đảm cho mọi cấu hình; treap suy biến có thể cần **`O(n)`**.

### Bài 22. Bộ nhớ stack đệ quy

`split` và `merge` đệ quy cần bao nhiêu bộ nhớ stack theo chiều cao `h`?

**Đáp án:** **`O(h+1)`**, kỳ vọng `O(\log(n+1))` với treap ngẫu nhiên chuẩn; xấu nhất `O(n)`.

### Bài 23. Vì sao giá trị tăng dần không làm treap suy biến một cách tất yếu?

Thêm lần lượt giá trị `1,2,3,4,\ldots` vào implicit treap. Vì sao thứ tự tăng dần của các giá trị không đủ kết luận cây suy biến?

**Đáp án:** Cấu trúc cây được quyết định bởi **priority ngẫu nhiên và vị trí inorder**, không dùng phép so sánh giá trị để tạo BST. Vẫn có cấu hình priority bất lợi, nhưng dữ liệu tăng dần không tự gây suy biến như BST đơn giản theo khóa.

### Bài 24. Quyền sở hữu sau split

Sau khi gọi `(A,B)=split(T,k)`, có nên tiếp tục dùng biến `T` cũ như thể nó trỏ tới nguyên dãy ban đầu không?

**Đáp án:** **Không.** Split thay con trỏ tại một số nút. Phải coi `A` và `B` là hai kết quả mới và ghép lại nếu muốn khôi phục dãy; không dùng gốc `T` cũ như một snapshot bất biến.

### Bài 25. Thêm metadata phụ thuộc thứ tự

Một treap lưu hash của chuỗi theo thứ tự trái–phải. Có thể áp dụng `reverse` mà không sửa hash không?

**Đáp án:** **Không thể mặc định.** Hash thuận thường thay đổi khi thứ tự đảo. Có thể cần lưu **hash thuận/hash ngược** cùng công thức cập nhật lazy phù hợp.

### Bài 26. So sánh với mảng

Một dãy hàng triệu phần tử thường xuyên phải cắt rồi dán những đoạn dài vào vị trí khác. Vì sao treap có thể đáng cân nhắc hơn mảng?

**Đáp án:** Cắt–dán bằng **một số hằng split/merge** nên tốn `O(\log n)` kỳ vọng, không cần dời/sao chép hàng loạt phần tử của đoạn và phần còn lại như khi sửa mảng thông thường. Đổi lại treap có chi phí nút, con trỏ, ngẫu nhiên và trường hợp xấu nhất `O(n)`.

### Bài 27. Persistent treap

Nếu cần giữ gốc của mọi phiên bản dãy để hỗ trợ undo, có thể dùng nguyên mã `split/merge` mutating rồi chỉ lưu `old_root` không?

**Đáp án:** **Không.** Những nút của phiên bản cũ có thể bị sửa tại chỗ khi thao tác mới. Cần snapshot thật hoặc **persistent treap với path copying và lazy an toàn cho cấu trúc chia sẻ**.

### Bài 28. Validator phát hiện điều gì?

Một validator không tin các trường `size/total` nên tính lại chúng như thế nào?

**Đáp án:** Duyệt **hậu thứ tự** từ liên kết thực, tính kích thước và tổng của hai cây con rồi so với metadata tại cha. Nên kiểm tra thêm tính chất cây không chu trình/nút dùng chung và bất biến priority.

### Bài 29. Một điều mà validator metadata không chứng minh

Hai dãy `[1,2,3]` và `[3,2,1]` đều có `size=3`, `total=6`. Vì sao validator chỉ kiểm size/sum không thể kết luận dãy đúng thứ tự?

**Đáp án:** `size` và `total` **không phụ thuộc thứ tự**. Cần đối chiếu inorder sau khi áp dụng ý nghĩa các thẻ lazy với một dãy tham chiếu độc lập.

### Bài 30. Phân biệt treap vị trí với heap ưu tiên nghiệp vụ

Một ứng dụng lập lịch có công việc ưu tiên cao nhất cần xử lý trước. Có nên dùng `priority` ngẫu nhiên của implicit treap để xác định công việc nào chạy trước không?

**Đáp án:** **Không.** Priority của implicit treap chỉ phục vụ **hình dạng cân bằng ngẫu nhiên** và không mang ý nghĩa ưu tiên công việc. Nếu cần lấy công việc có mức ưu tiên nghiệp vụ cao nhất, nên dùng **priority queue/heap** hoặc cấu trúc đáp ứng đúng yêu cầu đó.

## 21. Tổng kết

**Treap theo vị trí (implicit treap)** biểu diễn một dãy thông qua **thứ tự inorder**, chứ không lưu chỉ số tuyệt đối tại các nút. Cấu trúc kết hợp:

1. **Bất biến thứ tự dãy:** inorder đúng bằng thứ tự các phần tử.
2. **Bất biến max-heap priority:** priority cha lớn hơn hoặc bằng priority con.
3. **Bất biến kích thước cây con:** `size(u)=1+size(left)+size(right)`.

Nhờ `size`, ta có thể **tách `k` phần tử đầu**, **ghép hai dãy có thứ tự nối rõ ràng**, truy cập theo chỉ số và xây dựng **chèn, xóa, cắt–dán** từ một số hằng phép `split/merge`. Nếu bổ sung **lazy reversal**, đảo một đoạn dài chỉ cần đánh dấu ở gốc đoạn rồi đẩy thẻ khi thật sự cần truy cập. Với **`total`**, tổng đoạn cũng được tính bằng cách cô lập đoạn rồi đọc metadata.

Dưới giả thiết **priority ngẫu nhiên phù hợp**, các thao tác theo đường cây có thời gian **`O(\log(n+1))` kỳ vọng**, nhưng trường hợp xấu nhất có thể là `O(n)`. Trường hợp dãy dài và nhiều phép chỉnh sửa đoạn, treap có thể hiệu quả hơn việc dời hàng loạt phần tử trong mảng; ngược lại, mảng vẫn đơn giản và tốt hơn cho truy cập trực tiếp, dữ liệu nhỏ hoặc ít cập nhật.

Điểm quyết định tính đúng là **hợp đồng về vị trí**: `split` dùng **số phần tử đầu**, đoạn thao tác là **`[l,r)`**, và vị trí dán `pos` của bài được tính **sau khi cắt**. Đồng thời, khi có lazy reversal, mọi thao tác phụ thuộc thứ tự phải `push` trước khi đi xuống, và mọi thao tác sửa liên kết phải `pull` từ những cây con đã đúng.

Khi nắm vững các bất biến và hai phép `split–merge`, ta có một công cụ linh hoạt để thiết kế các cấu trúc dãy động, từ cắt–dán văn bản tới đảo đoạn, tổng đoạn và những biến thể cây tăng cường phức tạp hơn.
