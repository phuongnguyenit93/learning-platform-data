# Cây thống kê thứ tự với kích thước cây con

## 1. Bài toán: tìm theo thứ hạng thay vì chỉ tìm theo khóa

Trong môn **Cấu trúc dữ liệu**, một cây tìm kiếm nhị phân (Binary Search Tree — **BST**) có thể trả lời câu hỏi “khóa `x` có tồn tại không?” bằng cách so sánh `x` với khóa tại nút hiện tại, rồi chỉ đi xuống cây con trái hoặc phải. Nhưng có những câu hỏi khác:

- Trong các giá trị được sắp tăng dần, **phần tử nhỏ thứ `k`** là gì?
- Có **bao nhiêu phần tử nhỏ hơn `x`**?
- Có bao nhiêu phần tử trong đoạn `[L,R]`?
- Nếu thêm hoặc xóa dữ liệu liên tục, làm sao tìm **trung vị** mà không phải sắp xếp lại toàn bộ sau mỗi lần sửa?
- Khi có nhiều phần tử cùng khóa, vị trí xếp hạng được hiểu và đếm như thế nào?

Giả sử ta đang quản lý điểm số:

```text
Dữ liệu:                 8, 4, 10, 2, 6, 12, 14, 4, 10, 10

Sắp tăng dần:            2, 4, 4, 6, 8, 10, 10, 10, 12, 14
Vị trí đánh số từ 1:      1  2  3  4  5   6   7   8   9  10
```

Ta có:

- Phần tử nhỏ thứ `7` là `10`.
- Số phần tử **nhỏ hơn `10`** là `5`.
- Số phần tử **không lớn hơn `10`** là `8`.
- Số phần tử trong đoạn đóng `[4,10]` là `7`.
- Có `10` phần tử, nên hai giá trị giữa là `8` và `10`; nếu lấy trung vị bằng trung bình của hai giá trị giữa, kết quả là `9`.

Nếu mỗi lần hỏi đều duyệt đủ `n` phần tử hoặc sắp xếp lại, chi phí có thể cao khi có nhiều truy vấn và cập nhật. **Cây thống kê thứ tự (Order-Statistic Tree, viết tắt OST)** giải quyết vấn đề bằng cách **tăng cường một cây tìm kiếm** với thông tin **kích thước cây con**.

> Ý tưởng then chốt: tại mỗi nút, biết có bao nhiêu phần tử nằm trong cây con trái, để có thể **bỏ qua cả một nhóm phần tử** khi truy vấn thứ hạng.

Bài này trình bày từ bất biến toán học đến thuật toán `select`, `rank`, `count_range`, sau đó xây một **AVL tree tăng cường** bằng Python để giữ truy vấn nhanh ngay cả khi chèn/xóa nhiều lần.

## 2. Cây nền, thứ tự khóa và hai cách hiểu kích thước

### 2.1. BST là điều kiện nền, không phải chỉ có hình cây

Một BST với khóa phân biệt tuân theo:

\[
\forall u:\quad
key(v)<key(u)\ \text{nếu }v\text{ thuộc toàn bộ cây con trái của }u;
\]

\[
key(v)>key(u)\ \text{nếu }v\text{ thuộc toàn bộ cây con phải của }u.
\]

**Toàn bộ cây con** là từ khóa quan trọng. Chỉ so khóa của hai con trực tiếp với khóa cha là chưa đủ để bảo đảm BST.

Vì vậy, nếu cần tìm một giá trị `x`, ta có thể bỏ hẳn một phía không thể chứa `x`. OST dùng chính bất biến ấy và **thêm số lượng phần tử của từng cây con** để bỏ qua một phía khi tính thứ hạng.

### 2.2. Chính sách khóa trùng của bài này

Một cây thống kê thứ tự có thể cấm khóa trùng, hoặc chấp nhận nhiều phần tử có cùng khóa. Có nhiều cách hợp lệ để xử lý trùng, nhưng phải chọn **một chính sách nhất quán**.

Trong bài này, để mô tả **đa tập (multiset)**, mỗi nút lưu:

- `key`: một khóa phân biệt tại vị trí nút đó;
- `count`: **số lần xuất hiện** của khóa này, luôn `≥1`;
- `left`, `right`: các liên kết cây tìm kiếm;
- `size`: **tổng số phần tử, tính cả các lần xuất hiện trùng**, trong cây con;
- `height`: chiều cao theo số cạnh, phục vụ cân bằng AVL.

**Mỗi khóa phân biệt chỉ có một nút.** Các phần tử trùng được gom trong `count`. Nhờ vậy, BST vẫn dùng bất đẳng thức nghiêm ngặt ở hai phía.

Ví dụ, `4` xuất hiện hai lần nghĩa là **một nút có `key=4, count=2`**, không phải hai nút khóa `4` được đặt tùy ý ở các nhánh.

### 2.3. Kích thước theo số phần tử hay số nút?

Đây là một điểm dễ nhầm:

- `size(u)` trong bài: **số phần tử**, có tính trùng.
- **Số nút vật lý** trong cây con: số khóa **phân biệt** ở cây con đó.

Với nút có `key=10, count=3` và không có con:

- `size=3`, nhưng số nút vật lý là `1`.
- Khi `select` tìm phần tử thứ `1`, `2` hoặc `3` **trong cây con đó**, đều trả `10`.
- Nếu muốn thống kê theo **khóa phân biệt**, phải định nghĩa thêm metadata khác, chẳng hạn `distinct_size=1+distinct_size(left)+distinct_size(right)`.

Không được dùng một trường `size` để vừa đếm số phần tử có lặp vừa đếm số khóa phân biệt.

### 2.4. Quy ước khi cây rỗng

Chọn:

\[
size(\varnothing)=0,\qquad height(\varnothing)=-1.
\]

Chiều cao theo **số cạnh**, nên lá có `height=0`. BST rỗng có `0` phần tử, `select` trên cây rỗng phải báo lỗi chỉ số, còn `rank_lt(x)` và đếm đoạn trên cây rỗng trả `0`.

## 3. Bất biến cốt lõi của Order-Statistic Tree

Với một nút `u` có số lần xuất hiện `count(u)`:

\[
\boxed{
size(u)=size(u.left)+count(u)+size(u.right)
}
\]

Trong trường hợp **không cho phép khóa trùng**, `count(u)=1` cho mọi nút, công thức trở thành:

\[
size(u)=1+size(u.left)+size(u.right).
\]

### 3.1. Cây ví dụ có khóa trùng

Từ đa tập ở đầu bài, một BST hợp lệ là:

```text
                       key=8
                       count=1
                       size=10
                     /          \
                    /            \
             key=4                 key=12
             count=2               count=1
             size=4                size=5
             /    \                /    \
         key=2    key=6        key=10   key=14
         count=1  count=1      count=3  count=1
         size=1   size=1       size=3   size=1
```

Mỗi nút giữ đúng khóa BST theo quan hệ nhỏ/lớn; `count` được gộp trong nút.

Tại nút `4`:

\[
size(4)=size(2)+count(4)+size(6)=1+2+1=4.
\]

Tại nút `12`:

\[
size(12)=size(10)+count(12)+size(14)=3+1+1=5.
\]

Tại gốc `8`:

\[
size(8)=4+1+5=10.
\]

Đếm trên cây **không cần duyệt lại các nút mỗi lần**, vì thông tin đã được tổng hợp và lưu trong `size`.

### 3.2. Bảng chi tiết

| Khóa nút | `count` | `size(left)` | `size(right)` | `size` |
|---:|---:|---:|---:|---:|
| 2 | 1 | 0 | 0 | 1 |
| 4 | 2 | 1 | 1 | 4 |
| 6 | 1 | 0 | 0 | 1 |
| 8 | 1 | 4 | 5 | 10 |
| 10 | 3 | 0 | 0 | 3 |
| 12 | 1 | 3 | 1 | 5 |
| 14 | 1 | 0 | 0 | 1 |

**Bất biến phải đúng tại mọi nút**, không chỉ gốc. Một giá trị `size(root)=10` đúng tình cờ **không đủ**: nếu `size(4)` sai, thuật toán `select` có thể đi nhầm đường khi tìm các vị trí thuộc cây con trái.

### 3.3. Một phép tính lại cục bộ

Sau khi thay đổi cây con, ta sử dụng phép tính lại (*pull/recompute*):

```text
PULL(u):
    u.size   = SIZE(u.left) + u.count + SIZE(u.right)
    u.height = 1 + max(HEIGHT(u.left), HEIGHT(u.right))
```

Trong đó `SIZE(None)=0`, `HEIGHT(None)=-1`.

Nếu metadata của hai con đã đúng, `PULL(u)` mất **`O(1)` thời gian** và làm metadata của `u` đúng. Đây là nền tảng cho chèn, xóa và quay/xoay cây.

## 4. OS-SELECT: tìm phần tử nhỏ thứ `k`

### 4.1. Thứ hạng trong một cây con

Xét nút hiện tại `u` và gọi:

\[
L=size(u.left),\qquad C=count(u).
\]

Do tính chất BST, dãy đã sắp xếp của cây con `u` gồm:

1. `L` phần tử của cây con trái.
2. `C` lần xuất hiện của khóa `key(u)`.
3. Các phần tử của cây con phải.

Vì vậy, trong cây con `u`, khóa ở nút `u` chiếm **các thứ hạng từ `L+1` đến `L+C`**.

Nếu đang tìm phần tử nhỏ thứ `k` (đánh số từ `1`):

- **`k≤L`:** tìm tiếp trong cây con trái với cùng `k`.
- **`L<k≤L+C`:** đáp án chính là `key(u)`.
- **`k>L+C`:** tìm trong cây con phải với thứ hạng mới `k'=k-L-C`.

Các trường hợp này **không chồng lấn** và bao phủ mọi vị trí từ `1` tới `size(u)`.

### 4.2. Mã giả

```text
OS-SELECT(root, k):
    if k < 1 or k > SIZE(root):
        báo lỗi chỉ số

    u = root

    while u không rỗng:
        L = SIZE(u.left)
        C = u.count

        if k <= L:
            u = u.left
        else if k <= L + C:
            return u.key
        else:
            k = k - L - C
            u = u.right
```

Tại mọi bước, ta chỉ đi xuống **một** cây con. Không có lần duyệt riêng nào để đếm lại `L` vì nó đã được lưu tại nút con trái.

### 4.3. Truy vết `select(7)`

Trên cây mẫu gồm `10` phần tử:

```text
Dãy tăng: 2, 4, 4, 6, 8, 10, 10, 10, 12, 14
Vị trí:   1  2  3  4  5   6   7   8   9  10
```

| Bước | Nút `u` | `L=size(left)` | `C=count` | `k` hiện tại | Quyết định |
|---|---:|---:|---:|---:|---|
| 1 | 8 | 4 | 1 | 7 | `7>5`: đi phải tới 12, `k'=2` |
| 2 | 12 | 3 | 1 | 2 | `2≤3`: đi trái tới 10 |
| 3 | 10 | 0 | 3 | 2 | `0<2≤3`: trả **10** |

Một lần đọc `size(left)=4` ở gốc đã giúp bỏ qua **bốn phần tử** cùng lúc. Đó chính là lợi ích của metadata cây con.

### 4.4. Các trường hợp biên

- `select(1)` trả khóa nhỏ nhất.
- `select(size(root))` trả khóa lớn nhất.
- `select(0)`, `select(n+1)` hoặc `select` trên cây rỗng: **phải báo lỗi**, không trả một khóa tùy tiện.
- Nếu `count(u)>1`, nhiều vị trí khác nhau có thể trả **cùng một khóa**.
- Nếu `size` bị lưu sai, kiểm tra biên và quyết định đi trái/phải đều có thể sai.

## 5. OS-RANK: tìm số phần tử đứng trước một khóa

### 5.1. Phải định nghĩa rank trước khi viết code

Trong các tài liệu, “rank” có thể nghĩa là:

- Vị trí **đánh số từ `0`** hay từ `1`.
- Số phần tử **nhỏ hơn** `x`.
- Số phần tử **nhỏ hơn hoặc bằng** `x`.
- Vị trí của **một lần xuất hiện cụ thể** trong nhóm khóa trùng.

Để tránh nhập nhằng, bài dùng hai hàm:

\[
\boxed{rank\_lt(x)=\#\{a:a<x\}}
\]

\[
\boxed{rank\_le(x)=\#\{a:a\le x\}}
\]

Cả hai trả **số lượng phần tử**, có tính các lần xuất hiện trùng; `x` **không cần tồn tại** trong cây.

Trên dữ liệu mẫu:

| `x` | `rank_lt(x)` | `rank_le(x)` | Số lần `x` xuất hiện |
|---:|---:|---:|---:|
| 2 | 0 | 1 | 1 |
| 4 | 1 | 3 | 2 |
| 5 | 3 | 3 | 0 |
| 8 | 4 | 5 | 1 |
| 10 | 5 | 8 | 3 |
| 11 | 8 | 8 | 0 |
| 14 | 9 | 10 | 1 |
| 99 | 10 | 10 | 0 |

### 5.2. Thuật toán `rank_lt(x)`

Khi tới nút `u`:

- Nếu `x≤key(u)`, bản thân `u` và toàn bộ cây con phải **không thể** đóng góp phần tử nhỏ hơn `x`. Ta đi trái.
- Nếu `x>key(u)`, **mọi phần tử ở cây con trái** và **toàn bộ `count(u)` phần tử ở nút này** đều nhỏ hơn `x`. Cộng `size(left)+count(u)`, rồi đi phải.

Mã giả:

```text
RANK-LT(root, x):
    result = 0
    u = root

    while u != None:
        if x <= u.key:
            u = u.left
        else:
            result += SIZE(u.left) + u.count
            u = u.right

    return result
```

Với `rank_le(x)`, thay điều kiện đi trái thành `x<key(u)`; khi `x≥key(u)` thì cộng cả cây con trái và số lần `key(u)` xuất hiện.

### 5.3. Truy vết `rank_lt(10)`

Tại gốc `8`, vì `10>8`, mọi phần tử ở cây trái `[2,4,4,6]` cùng bản thân `8` đều nhỏ hơn `10`.

Cộng ngay:

\[
size(left)+count(8)=4+1=5.
\]

Đi sang nút `12`: `10≤12`, chỉ đi trái. Đến nút `10`: `10≤10`, chỉ đi trái. Cây trái rỗng, dừng. **Kết quả `5`**.

Lưu ý: Nếu hỏi `rank_le(10)`, ta còn phải cộng `3` phần tử bằng `10`, được **`8`**.

### 5.4. Mối liên hệ giữa rank và select

Với **khóa phân biệt**, nếu `select(k)=x` thì:

\[
rank\_lt(x)=k-1.
\]

Với khóa trùng, nếu `select(k)=x` thì:

\[
rank\_lt(x)<k\le rank\_le(x).
\]

Ví dụ, cả `select(6)`, `select(7)` và `select(8)` đều là `10`; khi đó:

\[
rank\_lt(10)=5,\qquad rank\_le(10)=8.
\]

Vì vậy, một khóa trùng không có một **vị trí duy nhất** nếu không bổ sung quy tắc xác định lần xuất hiện.

## 6. Các truy vấn phát sinh trực tiếp từ rank và select

### 6.1. Đếm số lần một khóa xuất hiện

\[
\boxed{count(x)=rank\_le(x)-rank\_lt(x)}.
\]

Ví dụ: `count(10)=8-5=3`. Truy vấn này mất thời gian theo chiều cao cây, dù một ứng dụng BST khác có thể tìm trực tiếp nút `x` rồi trả `node.count` bằng cùng bậc thời gian.

### 6.2. Đếm trong đoạn đóng `[L,R]`

Với `L≤R`:

\[
\boxed{count\_range(L,R)=rank\_le(R)-rank\_lt(L)}.
\]

Nếu `L>R`, có thể quy định kết quả `0` vì đoạn rỗng.

Trên dữ liệu mẫu:

```text
[4,10] chứa: 4, 4, 6, 8, 10, 10, 10
rank_le(10) = 8
rank_lt(4)  = 1
count_range(4, 10) = 8 - 1 = 7
```

Không được dùng `rank_lt(R)-rank_lt(L)` cho đoạn **đóng** nếu muốn tính cả khóa bằng `R`.

### 6.3. Trung vị (median)

Với `n` phần tử đã sắp và thứ tự `k` bắt đầu từ `1`:

- Nếu `n` lẻ: phần tử ở vị trí `(n+1)/2` là trung vị.
- Nếu `n` chẵn: một quy ước phổ biến đối với dữ liệu số là **trung bình cộng** của hai phần tử ở vị trí `n/2` và `n/2+1`.

Trên mẫu `n=10`:

\[
median=\frac{select(5)+select(6)}{2}
=\frac{8+10}{2}=9.
\]

Một số ứng dụng dùng **trung vị dưới** hoặc **trung vị trên** thay vì trung bình. Hãy ghi rõ hợp đồng API, đặc biệt với giá trị không phải số.

### 6.4. Phân vị và quy ước chỉ số

Nếu muốn “phần tử ở phân vị thứ `p`”, phải chọn cách định nghĩa phân vị. Một quy ước đơn giản là **nearest-rank**:

\[
k=\lceil p n\rceil,\qquad 0<p\le 1,
\]

rồi trả `select(k)`.

Quy tắc này **khác** các định nghĩa phân vị có nội suy thường dùng trong thống kê. Cây OST hỗ trợ nhanh việc lấy giá trị theo thứ hạng, nhưng **định nghĩa thống kê của phân vị** vẫn do ứng dụng quyết định.

### 6.5. Xác định vị trí chèn trong dãy đã sắp

- `rank_lt(x)` bằng số phần tử đứng trước vị trí **chèn `x` trước nhóm bằng `x`**.
- `rank_le(x)` bằng số phần tử đứng trước vị trí **chèn `x` sau nhóm bằng `x`**.

Tương ứng với tư tưởng `lower_bound`/`upper_bound` trong các cấu trúc dữ liệu có thứ tự. Các hàm rank rất hữu ích khi cần mô phỏng vị trí trong một dãy có thứ tự **đang thay đổi**.

## 7. Vì sao cần cây tìm kiếm tự cân bằng?

Lưu `size` giúp tránh duyệt cả cây con, nhưng **không làm giảm chiều cao**.

Giả sử ta chèn lần lượt `1,2,3,4,5,6,7` vào BST thông thường, không tái cân bằng:

```text
1
 \
  2
   \
    3
     \
      4
       \
        5
         \
          6
           \
            7
```

Dù mỗi nút đều lưu `size` đúng, truy vấn `select(7)` vẫn có thể phải đi qua **bảy nút**, và trong trường hợp tổng quát có thể mất `O(n)`.

**Order-Statistic Tree không bắt buộc là một loại cây cân bằng cụ thể.** Có thể tăng cường:

- Red–Black Tree.
- AVL tree.
- Treap với giả thiết xác suất phù hợp.
- Một số cây tìm kiếm khác với chiến lược metadata tương ứng.

Trong bài này ta dùng **AVL tăng cường** vì có thể minh họa rõ bằng các thao tác xoay trái/phải. Độ cao AVL được bảo đảm `O(\log u)`, với `u` là **số khóa phân biệt/nút vật lý**. Nếu tổng số phần tử kể cả trùng là `n≥u`, ta cũng có chặn trên `O(\log(n+1))`, nhưng viết theo `u` giúp phản ánh đúng việc các khóa trùng được gom trong một nút.

### Cây AVL lưu thêm gì?

Mỗi nút lưu:

```text
key
count
size
height
left
right
```

Các bất biến:

\[
size(u)=size(L)+count(u)+size(R),
\]

\[
height(u)=1+\max(height(L),height(R)),
\]

\[
|height(L)-height(R)|\le 1.
\]

Tất cả đều phải đúng sau khi chèn, xóa hoặc xoay.

## 8. Cài đặt Python: AVL hỗ trợ thống kê thứ tự và khóa trùng

Chúng ta xây một **multiset có thứ tự** bằng AVL, với các phép:

- `add(key)`: thêm **một lần xuất hiện**.
- `discard(key)`: xóa **một lần xuất hiện**, trả về có xóa được hay không.
- `count(key)`: số lần xuất hiện.
- `select(k)`: khóa nhỏ thứ `k`, với `k` từ `1`.
- `rank_lt(key)`, `rank_le(key)`.
- `count_range(low,high)`, `median()`.
- `len(tree)`: **tổng số phần tử**, kể cả trùng.

Code minh họa sử dụng **các khóa số nguyên có thể so sánh**, không lưu payload phụ. Nếu một ứng dụng cần giữ nhiều bản ghi cùng khóa với payload riêng, phải thiết kế thêm danh sách bản ghi hoặc một thứ tự phụ, không thể chỉ giữ `count`.

### 8.1. Nút và phép tính lại cục bộ

```python
class Node:
    def __init__(self, key):
        self.key = key
        self.count = 1
        self.size = 1
        self.height = 0
        self.left = None
        self.right = None


def size_of(node):
    return 0 if node is None else node.size


def height_of(node):
    return -1 if node is None else node.height


def pull(node):
    """Hai cây con của node đã có metadata đúng."""
    if node is None:
        return

    node.size = (
        size_of(node.left)
        + node.count
        + size_of(node.right)
    )
    node.height = (
        1 + max(height_of(node.left), height_of(node.right))
    )


def balance_factor(node):
    return height_of(node.left) - height_of(node.right)
```

Những dòng quan trọng nhất của một OST chính là công thức `size` và **lời hứa rằng hai cây con đúng trước khi gọi `pull`**.

### 8.2. Phép xoay trái/phải có bảo trì `size`

Xoay trái tại nút `x` với `y=x.right`:

```text
     x                      y
    / \                    / \
   A   y        →         x   C
      / \                / \
     B   C              A   B
```

Mỗi phép xoay giữ nguyên thứ tự inorder nhưng làm thay đổi **cây con gốc tại `x` và `y`**. Vì thế metadata phải được tính lại:

```python
def rotate_left(x):
    y = x.right
    if y is None:
        raise ValueError("Không thể xoay trái khi thiếu con phải")

    x.right = y.left
    y.left = x

    # Nút đi xuống trước, gốc mới sau.
    pull(x)
    pull(y)

    return y


def rotate_right(y):
    x = y.left
    if x is None:
        raise ValueError("Không thể xoay phải khi thiếu con trái")

    y.left = x.right
    x.right = y

    pull(y)
    pull(x)

    return x
```

**Không đảo thứ tự:** xoay trái gọi `pull(x)` rồi `pull(y)`; xoay phải gọi `pull(y)` rồi `pull(x)`. Nút được nâng lên cần dùng metadata **mới** của nút vừa bị đẩy xuống.

Mỗi phép xoay có **`O(1)` thời gian và bộ nhớ phụ**, vì chỉ sửa một số hằng con trỏ và tính lại hai nút.

### 8.3. Hàm tái cân bằng AVL

```python
def rebalance(node):
    """Hai cây con đã cân bằng và có metadata đúng."""
    pull(node)
    bf = balance_factor(node)

    if bf > 1:
        # Lệch trái: LL hoặc LR.
        if balance_factor(node.left) < 0:
            node.left = rotate_left(node.left)
        return rotate_right(node)

    if bf < -1:
        # Lệch phải: RR hoặc RL.
        if balance_factor(node.right) > 0:
            node.right = rotate_right(node.right)
        return rotate_left(node)

    return node
```

Hàm này xử lý đủ **LL, RR, LR, RL**. Điều kiện với dấu bằng ở hệ số cân bằng của con quan trọng trong trường hợp **xóa**: con có `bf=0` vẫn có thể dùng **xoay đơn**.

### 8.4. Thêm một lần xuất hiện

```python
def insert(node, key):
    if node is None:
        return Node(key)

    if key < node.key:
        node.left = insert(node.left, key)
    elif key > node.key:
        node.right = insert(node.right, key)
    else:
        # Khóa đã tồn tại: tăng số lần xuất hiện,
        # không tạo nút BST mới.
        node.count += 1
        pull(node)
        return node

    return rebalance(node)
```

Khi thêm một khóa mới, các khung gọi đi **từ dưới lên**, gắn cây con mới rồi `rebalance`. Khi thêm một lần xuất hiện của khóa cũ, **chỉ `count` và các `size` trên đường tổ tiên đổi**, không đổi hình dạng; vẫn phải cập nhật `size` của mọi tổ tiên.

### 8.5. Xóa nút nhỏ nhất của cây con: xử lý đúng `count`

Khi xóa một nút BST có **hai con**, một lựa chọn quen thuộc là dùng **kế nhiệm inorder**, tức nút nhỏ nhất trong cây con phải.

Nhưng ở mô hình khóa trùng, nút kế nhiệm có thể có `count>1`. Nếu ta sao chép `successor.key` và `successor.count` vào vị trí cần xóa, rồi **chỉ giảm `successor.count` đi `1`**, ta sẽ tạo **hai nút khác nhau cùng khóa** và đếm sai.

Vì vậy, khi dùng chiến lược sao chép **cả `key` và `count`**, phải **tách toàn bộ nút kế nhiệm ra khỏi vị trí cũ**, không chỉ xóa một lần xuất hiện.

Hàm `pop_min_node` dưới đây thực hiện chính xác thao tác đó:

```python
def pop_min_node(node):
    """Tách toàn bộ nút nhỏ nhất.

    Trả (gốc_cây_con_còn_lại, nút_đã_tách).
    node phải khác None.
    """
    if node.left is None:
        remaining = node.right
        node.right = None  # Ngắt liên kết ở nút vừa tách.
        return remaining, node

    node.left, minimum = pop_min_node(node.left)
    return rebalance(node), minimum
```

**Vì sao đúng?**

- Nút nhỏ nhất trong BST không có con trái.
- Nó **có thể có con phải**: phải nối cây con phải đó vào chỗ nút cũ.
- Khi tháo nút nhỏ nhất, ta di chuyển **toàn bộ `count`** của khóa đó; số phần tử ở cây con còn lại giảm đúng bằng `count(minimum)`.
- Các tổ tiên trên đường tháo được tính lại và tái cân bằng từ dưới lên.

### 8.6. Xóa đúng một lần xuất hiện

```python
def delete_one(node, key):
    """Trả (gốc_mới, removed)."""
    if node is None:
        return None, False

    if key < node.key:
        node.left, removed = delete_one(node.left, key)

    elif key > node.key:
        node.right, removed = delete_one(node.right, key)

    else:
        # Đã tìm đúng khóa.
        if node.count > 1:
            node.count -= 1
            pull(node)
            return node, True

        # count == 1: xóa toàn bộ nút vật lý.
        if node.left is None:
            return node.right, True

        if node.right is None:
            return node.left, True

        # Hai con: chuyển toàn bộ khóa và số lần xuất hiện
        # của nút kế nhiệm về vị trí hiện tại.
        node.right, successor = pop_min_node(node.right)
        node.key = successor.key
        node.count = successor.count

        return rebalance(node), True

    if not removed:
        return node, False

    return rebalance(node), True
```

Tại nhánh `node.count>1`, giảm một lần xuất hiện không thay đổi hình dạng nên gọi `pull(node)` là đủ. Tại nhánh xóa nút vật lý, thuật toán nối lại các cây con và `rebalance`. Nếu khóa không tồn tại, **không cập nhật bừa** metadata.

### 8.7. Lớp bọc và các truy vấn có thứ hạng

```python
class OrderStatisticTree:
    def __init__(self):
        self.root = None

    def __len__(self):
        return size_of(self.root)

    def add(self, key):
        self.root = insert(self.root, key)

    def discard(self, key):
        self.root, removed = delete_one(self.root, key)
        return removed

    def count(self, key):
        node = self.root
        while node is not None:
            if key < node.key:
                node = node.left
            elif key > node.key:
                node = node.right
            else:
                return node.count
        return 0

    def select(self, k):
        """Phần tử nhỏ thứ k; k bắt đầu từ 1."""
        if not 1 <= k <= len(self):
            raise IndexError("k nằm ngoài số phần tử")

        node = self.root

        while node is not None:
            left_size = size_of(node.left)

            if k <= left_size:
                node = node.left
            elif k <= left_size + node.count:
                return node.key
            else:
                k -= left_size + node.count
                node = node.right

        raise RuntimeError("Metadata size không nhất quán")

    def rank_lt(self, key):
        result = 0
        node = self.root

        while node is not None:
            if key <= node.key:
                node = node.left
            else:
                result += size_of(node.left) + node.count
                node = node.right

        return result

    def rank_le(self, key):
        result = 0
        node = self.root

        while node is not None:
            if key < node.key:
                node = node.left
            else:
                result += size_of(node.left) + node.count
                node = node.right

        return result

    def count_range(self, low, high):
        if low > high:
            return 0
        return self.rank_le(high) - self.rank_lt(low)

    def median(self):
        """Trung vị số học; yêu cầu khóa hỗ trợ phép + và /."""
        n = len(self)
        if n == 0:
            raise ValueError("Không có trung vị của cây rỗng")

        if n % 2 == 1:
            return self.select((n + 1) // 2)

        lower = self.select(n // 2)
        upper = self.select(n // 2 + 1)
        return (lower + upper) / 2

    def to_sorted_list(self):
        """Phục vụ hiển thị; O(n) thời gian và bộ nhớ."""
        result = []
        stack = []
        node = self.root

        while node is not None or stack:
            while node is not None:
                stack.append(node)
                node = node.left

            node = stack.pop()
            result.extend([node.key] * node.count)
            node = node.right

        return result
```

**Hợp đồng API:**

- `add(x)` luôn thêm **một** phần tử.
- `discard(x)` xóa **một** phần tử bằng `x` và trả `False` nếu không có.
- `len(tree)` là tổng số phần tử **bao gồm trùng**, không phải số nút vật lý.
- `select(k)` dùng **thứ hạng từ `1`**, không phải chỉ số mảng từ `0`.
- `median()` trả trung bình của hai khóa giữa khi `n` chẵn; với khóa không phải số, cần quy ước trung vị khác.
- `to_sorted_list()` chủ yếu để quan sát/đối chiếu kết quả, không nên gọi sau mọi cập nhật nếu muốn giữ hiệu năng truy vấn theo chiều cao.

### 8.8. Ví dụ sử dụng lớp hoàn chỉnh

```python
values = [8, 4, 10, 2, 6, 12, 14, 4, 10, 10]

tree = OrderStatisticTree()
for value in values:
    tree.add(value)

print(tree.to_sorted_list())
# [2, 4, 4, 6, 8, 10, 10, 10, 12, 14]

print(len(tree))              # 10
print(tree.count(4))          # 2
print(tree.count(10))         # 3
print(tree.select(7))         # 10
print(tree.rank_lt(10))       # 5
print(tree.rank_le(10))       # 8
print(tree.count_range(4, 10))  # 7
print(tree.median())          # 9.0

assert tree.discard(10)
print(tree.count(10))         # 2
print(len(tree))              # 9

assert not tree.discard(99)   # Không có khóa 99.
print(len(tree))              # 9: giữ nguyên

tree.add(4)
print(tree.count(4))          # 3
print(len(tree))              # 10
```

Lưu ý: các ví dụ mã trong bài là tài liệu để thực hành; chúng **không phải kết quả đã chạy kiểm thử tự động** trong quy trình biên soạn.

## 9. Truy vết cập nhật `size` khi khóa trùng thay đổi

Với cây ví dụ ban đầu:

```text
                   8 (c=1, s=10)
                  /             \
           4 (c=2,s=4)      12 (c=1,s=5)
            /     \           /       \
        2(c=1) 6(c=1)    10(c=3,s=3) 14(c=1)
```

Trong sơ đồ, `c=count` và `s=size`.

### 9.1. Chèn thêm một lần `4`

- Tìm thấy nút `4`, **không tạo nút mới**.
- `count(4)` tăng từ `2` lên `3`.
- `size(4)` tăng từ `4` lên `5`.
- `size(8)` tăng từ `10` lên `11`.
- Cây con phải tại `12` không thay đổi.
- Chiều cao và hình dạng không đổi, nên không cần xoay.

Dãy mới có thêm một số `4` tại vùng các khóa bằng `4`, nhưng không tồn tại thêm nút vật lý.

### 9.2. Xóa một lần `10`

Bắt đầu lại từ cây **ban đầu** để không lẫn với ví dụ vừa chèn:

- `count(10)` giảm từ `3` xuống `2`, nút `10` vẫn tồn tại.
- `size(10)` giảm từ `3` xuống `2`.
- `size(12)` giảm từ `5` xuống `4`.
- `size(8)` giảm từ `10` xuống `9`.
- Không cần xóa nút vật lý hay thay liên kết.

Dãy còn lại:

```text
[2, 4, 4, 6, 8, 10, 10, 12, 14]
```

### 9.3. Xóa gốc `8` có hai con và kế nhiệm trùng

Tiếp tục xét **cây ban đầu** có `10` phần tử. Gốc `8` có hai con. Kế nhiệm inorder là nút khóa `10` với **`count=3`**.

Ta phải:

1. Tách **toàn bộ nút `10`** (cả ba lần xuất hiện) khỏi cây con phải.
2. Đặt tại vị trí gốc cũ: `key=10, count=3`.
3. Gắn lại cây con phải còn lại, rồi cập nhật/cân bằng.

```text
Trước:                             Sau xóa một lần khóa 8:

          8 (c=1)                           10 (c=3)
         /       \                         /        \
      4(c=2)    12(c=1)                4(c=2)      12(c=1)
      /   \      /  \                  /   \             \
     2     6  10(c=3) 14               2     6             14

Tổng số phần tử trước: 10
Tổng số phần tử sau:    9
```

Kết quả có:

```text
[2, 4, 4, 6, 10, 10, 10, 12, 14]
```

**Chỉ `8` bị xóa.** Ba lần xuất hiện của `10` vẫn nguyên vẹn. Nếu mã chỉ giảm `count` của nút kế nhiệm cũ rồi sao chép cả ba lần `10` lên gốc, cây sẽ có thêm `10` không mong muốn. Đây là lỗi đặc trưng khi kết hợp BST xóa nút hai con với metadata tính **bội số khóa**.

## 10. Xoay cây: vì sao phải tính lại kích thước đúng thứ tự?

### 10.1. Xoay không làm thay đổi thứ tự inorder

Giả sử một vùng BST:

```text
Trước xoay trái:              Sau xoay trái:

       x                            y
      / \                          / \
     A   y                        x   C
        / \                      / \
       B   C                    A   B
```

Thứ tự inorder theo khóa vẫn là:

```text
toàn bộ A, x, toàn bộ B, y, toàn bộ C
```

Nhưng tập phần tử trong cây con **gốc tại `x`** đã đổi. Trước xoay, `x` bao gồm cả `y,C`; sau xoay thì không. Vì vậy:

- Sau xoay trái, tính `size(x)` **trước** `size(y)`.
- Sau xoay phải, tính nút bị đẩy xuống trước nút được đưa lên.

### 10.2. Công thức ở vùng xoay với khóa trùng

Gọi `s_A,s_B,s_C` là kích thước ba cây con, `c_x,c_y` là số lần xuất hiện ở hai nút quay.

Trước xoay trái:

\[
size(x)=s_A+c_x+s_B+c_y+s_C,
\]

\[
size(y)=s_B+c_y+s_C.
\]

Sau xoay trái:

\[
size(x)=s_A+c_x+s_B,
\]

\[
size(y)=size(x)+c_y+s_C.
\]

Kết quả `size(y)` sau xoay bằng `size(x)` trước xoay, vì **tập phần tử toàn vùng không đổi**. Nhưng `size(x)` sau xoay thường nhỏ hơn trước, và cả `height` cũng có thể đổi.

### 10.3. Xoay kép

AVL có bốn loại mất cân bằng:

| Mẫu | Cách xử lý |
|---|---|
| **LL** | Xoay phải một lần |
| **RR** | Xoay trái một lần |
| **LR** | Xoay trái ở con trái, rồi xoay phải ở nút cha |
| **RL** | Xoay phải ở con phải, rồi xoay trái ở nút cha |

Mỗi phép xoay đơn trong mục 8.2 đã gọi `pull` đúng thứ tự. Xoay kép chỉ là **hai xoay đơn liên tiếp**, không cần công thức metadata riêng; mỗi lần xoay có chi phí cục bộ `O(1)`.

**Nhớ gán gốc cây con mới.** Các hàm xoay trả về nút làm gốc sau khi quay. Nếu không gán lại cho `parent.left`, `parent.right` hoặc biến `root` toàn cây, cấu trúc có thể bị mất liên kết, dù công thức `size` trong vùng xoay là đúng.

## 11. Chứng minh tính đúng của OS-SELECT

Để biết một thuật toán tăng cường đúng không chỉ trên ví dụ, ta cần nêu **bất biến vòng lặp**.

### 11.1. Bất biến

Trong quá trình `select(k)`, trước mỗi vòng lặp:

> Phần tử cần tìm là phần tử nhỏ thứ `k` **trong cây con gốc tại nút hiện tại**.

Ban đầu nút hiện tại là gốc toàn cây và `k` là vị trí người dùng yêu cầu, nên bất biến đúng.

### 11.2. Bảo toàn khi đi trái

Gọi `L=size(left)`, `C=count(node)`. Nếu `k≤L`, phần tử thứ `k` nằm trong **`L` phần tử nhỏ nhất** của cây con hiện tại, tức cây con trái. Đi trái và giữ nguyên `k` bảo toàn bất biến.

### 11.3. Bảo toàn khi đi phải

Nếu `k>L+C`, phần tử cần tìm không nằm trong cây con trái hay nhóm khóa tại nút. Có đúng `L+C` phần tử đứng trước nó, nên trong cây con phải thứ hạng mới là:

\[
k'=k-L-C.
\]

Đi phải với `k'` bảo toàn bất biến.

### 11.4. Điều kiện dừng

Nếu `L<k≤L+C`, vị trí mong muốn thuộc nhóm `C` phần tử có cùng khóa tại nút. Trả `node.key` là đúng.

Mỗi vòng lặp đi xuống **một mức**, nên cây hợp lệ hữu hạn sẽ kết thúc trong tối đa `h+1` mức. Nếu đầu vào `1≤k≤size(root)` và metadata đúng, thuật toán không đi tới `None` trước khi trả kết quả.

## 12. Chứng minh tính đúng của OS-RANK

### 12.1. Bất biến của `rank_lt`

Trong quá trình `rank_lt(x)`:

> Biến `result` bằng số phần tử đã xác định chắc chắn **nhỏ hơn `x`** trong những phần cây đã bỏ qua.

Ban đầu chưa bỏ qua phần tử nào, nên `result=0`.

Nếu `x≤key(node)`, nút hiện tại và cây con phải không đóng góp phần tử nào nhỏ hơn `x`. Ta đi trái, `result` giữ nguyên.

Nếu `x>key(node)`, toàn bộ cây con trái và `count(node)` phần tử ở nút hiện tại đều nhỏ hơn `x`. Cộng đúng `size(left)+count(node)` rồi đi phải.

Khi tới `None`, không còn phần tử nào chưa xét có thể nhỏ hơn `x`. `result` là đáp án.

### 12.2. Tại sao `rank_le` chỉ khác một điều kiện?

Với `rank_le(x)`, khi `x==key(node)`, các lần xuất hiện tại nút **cũng phải được cộng**, nên ta xử lý trường hợp `x≥key(node)` như nhánh cộng. Đó là lý do điều kiện “đi trái” trở thành `x<key(node)`.

Nhìn đơn giản, nhưng dấu **`<`/`≤`** quyết định chính xác việc có tính các đầu mút và nhóm khóa trùng hay không.

## 13. Chứng minh bảo trì `size` sau chèn, xóa và xoay

### 13.1. Nút mới và cây rỗng

- Cây rỗng có `size=0`.
- Nút mới có `count=1` và hai con rỗng, nên `size=0+1+0=1`.

Đó là các cơ sở đúng.

### 13.2. Tính lại từ hai cây con

Giả sử `size(left)` và `size(right)` đều đúng. Cây con gốc tại nút hiện tại gồm ba nhóm **không chồng lấn**:

- Toàn bộ phần tử cây trái.
- `count` lần xuất hiện của khóa nút.
- Toàn bộ phần tử cây phải.

Vì thế:

\[
size=size(left)+count+size(right)
\]

đếm chính xác số phần tử. Lập luận này là một bước **quy nạp cấu trúc**.

### 13.3. Sau chèn

- Nếu khóa mới, tạo một nút lá `size=1`.
- Nếu khóa đã có, tăng `count` ở nút đó và gọi `pull`.
- Ở các khung quay về, sau khi gắn cây con mới, gọi `rebalance`/`pull` từ dưới lên.
- Những cây con không nằm trên đường chèn không thay đổi.

Vì con được xử lý trước cha, mọi `pull` đều đọc metadata con đúng.

### 13.4. Sau xóa một lần xuất hiện

- Nếu `count>1`, giảm `count` đúng một đơn vị và `pull`.
- Nếu `count=1` và có 0 hoặc 1 con, thay nút bằng cây con còn lại.
- Nếu có hai con, di chuyển **toàn bộ nút kế nhiệm** ra khỏi nhánh phải; đặt `key,count` của kế nhiệm vào vị trí cần xóa. Bảo trì nhánh phải từ dưới lên và tính lại nút thay thế.
- Mọi khung tổ tiên bị ảnh hưởng tiếp tục `rebalance`.

Trong trường hợp hai con, cần chú ý tổng số phần tử giảm đúng **một** — lần xuất hiện khóa bị xóa — dù nút kế nhiệm có thể mang `count>1`.

### 13.5. Sau xoay

Các cây con `A,B,C` giữ nguyên metadata. Khi xoay trái, nút `x` nhận con mới `A,B`, nên `pull(x)` làm đúng `size(x)`. Sau đó `y` nhận con trái `x` đã đúng và con phải `C` đã đúng; `pull(y)` làm đúng `size(y)`. Xoay phải đối xứng.

Các phép xoay còn bảo toàn thứ tự inorder, nên không làm mất bất biến BST. Một hàm tái cân bằng AVL đúng duy trì tiếp chiều cao `O(\log u)`.

**Kết luận:** độ đúng của `select/rank` phụ thuộc **hai lời chứng minh đồng thời**: thứ tự BST và kích thước cây con được bảo trì chính xác sau mọi phép cập nhật.

## 14. Độ phức tạp thời gian và bộ nhớ

Ký hiệu:

- `u`: số **khóa phân biệt**, cũng là số nút vật lý.
- `n`: tổng số **phần tử kể cả trùng**; `1≤u≤n` khi cây không rỗng.
- `h`: chiều cao cây theo số cạnh.
- Bài giả định phép so sánh khóa, cộng số đếm và đọc trường mất thời gian `O(1)`.

| Thao tác | BST tăng cường không cân bằng | AVL Order-Statistic Tree |
|---|---|---|
| `select(k)` | `O(h+1)` | `O(\log(u+1))` |
| `rank_lt(x)` / `rank_le(x)` | `O(h+1)` | `O(\log(u+1))` |
| `count(x)` | `O(h+1)` | `O(\log(u+1))` |
| `count_range(L,R)` | `O(h+1)` | `O(\log(u+1))` |
| `median()` | `O(h+1)` | `O(\log(u+1))` |
| Thêm một phần tử `add(x)` | `O(h+1)` | `O(\log(u+1))` |
| Xóa một phần tử `discard(x)` | `O(h+1)` | `O(\log(u+1))` |
| Một lần `pull` hoặc xoay đơn | `O(1)` | `O(1)` |
| Xuất toàn bộ phần tử tăng dần | `O(n+u)`, rút gọn `O(n)` | `O(n)` |
| Bộ nhớ lưu nút và metadata | `O(u)` | `O(u)` |

### 14.1. Vì sao dùng `u` chứ không chỉ `n`?

Vì các khóa trùng được gom lại tại một nút, cây AVL cân bằng theo **số nút vật lý** `u` chứ không theo `n` phần tử. Nếu một triệu phần tử đều có cùng khóa, cây chỉ có **một nút** với `count=1000000`. Các truy vấn trên cây này có thể trả kết quả trong thời gian hằng số, không cần đi qua một triệu nút.

Viết `O(\log(n+1))` vẫn là một chặn trên đúng vì `u≤n`, nhưng kém chính xác hơn. `O(\log(u+1))` cũng xử lý hợp lý trường hợp `u=1`, khi một truy vấn vẫn cần hằng số bước.

### 14.2. Bộ nhớ phụ của Python

- `select`, `rank` và `count` dùng vòng lặp: **`O(1)` bộ nhớ phụ**.
- `insert`, `delete_one`, `pop_min_node` sử dụng đệ quy: **`O(h+1)` khung gọi**, tức `O(\log(u+1))` trên AVL hợp lệ.
- Mỗi nút bổ sung `count,size,height`: chi phí metadata **`O(u)`**.
- `to_sorted_list` trả ra `n` giá trị: **`O(n)` bộ nhớ kết quả**, dù cây chỉ có `u` nút vật lý.

**Quan trọng:** `O(1)` của một phép xoay **không có nghĩa** `O(1)` cho toàn bộ chèn/xóa. Tìm vị trí và sửa metadata trên đường từ lá tới gốc vẫn tốn thời gian theo chiều cao.

## 15. So sánh OST với các cấu trúc dữ liệu khác

| Cấu trúc | Lấy phần tử thứ `k` | Đếm khóa nhỏ hơn `x` | Thêm/xóa một phần tử | Đặc điểm |
|---|---|---|---|---|
| **Mảng đã sắp** | `O(1)` khi truy cập chỉ số | `O(\log n)` bằng tìm nhị phân | `O(n)` do dời phần tử | Tốt khi ít sửa |
| **BST không có `size`** | Có thể `O(n)` nếu không đếm lại cây con | Có thể `O(n)` | Theo chiều cao | Chưa có chỉ mục thứ hạng |
| **AVL OST** | `O(\log(u+1))` | `O(\log(u+1))` | `O(\log(u+1))` | Động, có thứ tự và thống kê |
| **Binary heap** | Không hỗ trợ trực tiếp `k` tổng quát trong `O(\log n)` | Không hỗ trợ trực tiếp | Push/pop ưu tiên `O(\log n)` | Tối ưu phần tử cực trị |
| **Bảng băm** | Không hỗ trợ thứ tự tự nhiên | Không hỗ trợ trực tiếp | Trung bình nhanh theo khóa | Tối ưu tra cứu chính xác |
| **Fenwick tree (BIT)** | Có thể tìm theo tổng tần suất với điều kiện phù hợp | `O(\log M)` trên chỉ số nén | `O(\log M)` cập nhật tần suất | Tốt khi miền giá trị đã biết hoặc nén tọa độ |

Trong bảng, `M` là số vị trí của miền chỉ số đối với Fenwick tree, có thể khác `u` và `n`.

### 15.1. Khi nào chọn OST?

OST phù hợp nếu cần **cập nhật động** và thường xuyên truy vấn thứ hạng trên một tập khóa có thứ tự, ví dụ:

- Bảng điểm được thêm/xóa liên tục, cần tìm người ở vị trí `k`.
- Hệ thống thống kê thời gian thực, cần trung vị và phân vị theo thứ hạng.
- Sổ lệnh hoặc một tập giá thay đổi, cần biết có bao nhiêu giá thấp hơn ngưỡng.
- Bộ quản lý dữ liệu cần trả lời các câu hỏi `order_of_key(x)` và `find_by_order(k)`.
- Mô phỏng thứ tự các phần tử khi cần chèn/xóa và truy vấn vị trí.

Không nhất thiết phải dùng OST nếu chỉ cần `min/max`: một heap có thể đơn giản hơn. Nếu miền khóa nhỏ, cố định và đã nén tọa độ, Fenwick/segment tree lưu tần suất cũng là lựa chọn đáng cân nhắc.

### 15.2. OST không tự hỗ trợ truy vấn tổng trọng số

`size` là số lượng, không phải tổng giá trị. Nếu cần tính **tổng điểm số**, **tổng doanh thu theo khoảng khóa** hoặc các phép tổng khác, phải lưu metadata bổ sung như `subtree_total` và bảo trì nó theo quy tắc riêng.

Một cây có thể lưu cả `size` và `total`, nhưng khi đó mỗi thao tác thay đổi phải giữ **cả hai** bất biến, không chỉ cập nhật một trường.

## 16. Hai biến thể thiết kế đáng biết

### 16.1. Khóa phân biệt hoàn toàn

Nếu ứng dụng **cấm khóa trùng**, có thể bỏ `count` và coi mỗi nút đóng góp đúng một phần tử:

```text
size(u) = 1 + size(left) + size(right)
```

Khi đó `select(k)` so sánh `k` với `size(left)+1`, và `rank_lt(x)` cộng `size(left)+1` khi đi phải.

Đây là dạng thường gặp khi giới thiệu **Order-Statistic Red–Black Tree** với các khóa phân biệt.

### 16.2. Mỗi phần tử trùng là một nút riêng

Một cách khác là gắn **khóa phụ duy nhất** cho từng lần xuất hiện, chẳng hạn cặp `(value, unique_id)`:

```text
(10, 1001), (10, 1002), (10, 1003)
```

BST sắp theo cặp khóa, nên mỗi nút vật lý có đúng một phần tử. Lúc này:

\[
size(u)=1+size(left)+size(right).
\]

Ưu điểm là mỗi bản ghi có định danh riêng, dễ xóa chính xác một bản ghi theo ID nếu có chỉ mục. Nhược điểm là số nút bằng tổng số phần tử `n`, và quy tắc rank theo **giá trị chính** cần xử lý cận dưới/cận trên của các cặp khóa.

**Không có cách nào đúng cho mọi bài toán.** Mô hình `count` rất phù hợp nếu chỉ cần thống kê số lần xuất hiện của một giá trị; mô hình cặp khóa phù hợp nếu từng bản ghi trùng giá trị vẫn có danh tính/payload riêng.

## 17. OS-RANK khi đã có tham chiếu tới một nút

Trong một số cài đặt OST, mỗi nút còn có liên kết `parent`. Khi đã có **tham chiếu tới nút `u`**, ta có thể tính thứ hạng bằng cách đi từ nút lên gốc, không cần tìm lại khóa từ gốc.

Với khóa phân biệt:

1. Khởi tạo `r=size(u.left)+1`.
2. Trong khi `u` chưa phải gốc:
   - Nếu `u` là **con phải** của cha `p`, cộng `size(p.left)+1` vào `r`, vì mọi nút cây trái và chính `p` đều đứng trước `u`.
   - Nếu `u` là con trái, không cộng.
   - Đi lên `u=p`.
3. Trả `r`.

Với mô hình khóa trùng của bài, nếu muốn thứ hạng của **lần xuất hiện thứ `j` trong nút `u`**, khởi tạo:

\[
r=size(u.left)+j,\qquad 1\le j\le count(u).
\]

Khi đi lên từ **con phải**, cộng:

\[
size(p.left)+count(p)
\]

thay vì `size(p.left)+1`.

### Mã giả có `parent`

```text
RANK-NODE(u, occurrence_index):
    require 1 <= occurrence_index <= u.count
    r = SIZE(u.left) + occurrence_index

    while u.parent != None:
        p = u.parent
        if u is p.right:
            r += SIZE(p.left) + p.count
        u = p

    return r
```

**Điểm khác biệt:** `rank_lt(x)` dùng **khóa truy vấn**, còn `RANK-NODE` dùng **tham chiếu đối tượng nút** và chỉ số lần xuất hiện. Hai cách đều có thời gian `O(h+1)`, nhưng cách thứ hai cần thêm liên kết `parent` được bảo trì đúng qua **mọi phép xoay, chèn, xóa**.

Ví dụ, nút `10` ở cây mẫu có ba lần xuất hiện, chiếm thứ hạng toàn cục `6,7,8`. Chỉ có tham chiếu tới nút `10` mà không cung cấp `occurrence_index` thì không thể xác định **một vị trí duy nhất**.

## 18. Tự xác minh bất biến của AVL-OST

Khi viết một cây tăng cường, một lỗi nhỏ trong xóa hoặc xoay có thể không lộ ra ngay ở `find`, nhưng lại làm `size` sai. Do đó nên có **hàm kiểm tra độc lập** phục vụ thực hành.

Một validator cần kiểm tra:

1. Không có chu trình hoặc một đối tượng nút bị truy cập từ hai đường khác nhau.
2. Khóa trong toàn cây con trái **nhỏ hơn** khóa nút; cây con phải **lớn hơn**, theo cận từ tất cả tổ tiên.
3. `count` là số nguyên dương.
4. `size` lưu tại nút bằng **số phần tử tính lại độc lập** từ hai cây con và `count`.
5. `height` lưu tại nút bằng **chiều cao thực** từ hai cây con.
6. Độ chênh chiều cao ở mọi nút tối đa `1` nếu đây là AVL.

### 18.1. Validator dùng hậu thứ tự lặp

```python
def validate_ost(root):
    """Kiểm tra BST, AVL, count, size, height và định danh nút."""
    if root is None:
        return True

    seen = set()
    actual = {}
    # (node, lower_bound, upper_bound, ready)
    stack = [(root, None, None, False)]

    while stack:
        node, low, high, ready = stack.pop()
        if node is None:
            continue

        if not isinstance(node, Node):
            return False

        if not ready:
            identity = id(node)
            if identity in seen:
                return False
            seen.add(identity)

            if low is not None and node.key <= low:
                return False
            if high is not None and node.key >= high:
                return False

            if type(node.count) is not int or node.count < 1:
                return False

            stack.append((node, low, high, True))
            stack.append((node.right, node.key, high, False))
            stack.append((node.left, low, node.key, False))

        else:
            left_size, left_h = actual.get(node.left, (0, -1))
            right_size, right_h = actual.get(node.right, (0, -1))

            expected_size = (
                left_size + node.count + right_size
            )
            expected_h = 1 + max(left_h, right_h)

            if node.size != expected_size:
                return False
            if node.height != expected_h:
                return False
            if abs(left_h - right_h) > 1:
                return False

            actual[node] = (expected_size, expected_h)

    return True
```

Hàm chỉ tin vào **khóa và liên kết cấu trúc**, không lấy giá trị `size` của con để tự kiểm tra chính `size` của con. Thay vào đó, nó dùng một bảng `actual` đã tính lại từ dưới lên.

**Chi phí:** với `u` nút vật lý hợp lệ, thời gian `O(u)` và bộ nhớ phụ `O(u)`. Hàm này dành cho kiểm thử hoặc kiểm tra nhất quán, **không phải bước bắt buộc sau mỗi cập nhật trong đường vận hành tối ưu**.

### 18.2. Ví dụ kiểm tra ở các tình huống quan trọng

```python
tree = OrderStatisticTree()
assert validate_ost(tree.root)

for x in [8, 4, 10, 2, 6, 12, 14, 4, 10, 10]:
    tree.add(x)
    assert validate_ost(tree.root)

assert tree.to_sorted_list() == [
    2, 4, 4, 6, 8, 10, 10, 10, 12, 14
]

# Giảm count mà không xóa nút vật lý.
assert tree.discard(10)
assert tree.count(10) == 2
assert validate_ost(tree.root)

# Xóa gốc có hai con khi kế nhiệm còn count=2.
assert tree.discard(8)
assert validate_ost(tree.root)
assert tree.to_sorted_list() == [
    2, 4, 4, 6, 10, 10, 12, 14
]

# Xóa tiếp tới lúc không còn khóa 4.
assert tree.discard(4)
assert tree.discard(4)
assert tree.count(4) == 0
assert validate_ost(tree.root)

# Không được làm cây thay đổi nếu khóa không có.
before = tree.to_sorted_list()
assert not tree.discard(999)
assert tree.to_sorted_list() == before
assert validate_ost(tree.root)
```

### 18.3. Đối chiếu với một nguồn độc lập

Để kiểm thử bằng tư duy, có thể giữ thêm một danh sách tham chiếu trong bộ thử nghiệm và kiểm tra:

```text
Sau mỗi add(x):
    thêm x vào reference

Sau mỗi discard(x):
    chỉ xóa một lần x khỏi reference nếu có

expected = sorted(reference)

Kiểm tra:
    len(tree) == len(expected)
    tree.to_sorted_list() == expected
    với mỗi k hợp lệ: tree.select(k) == expected[k-1]
    rank_lt(x) == số phần tử expected nhỏ hơn x
    rank_le(x) == số phần tử expected không lớn hơn x
```

Đây là một hình thức **kiểm tra chéo với cách tính đơn giản**, rất hữu ích để phát hiện lỗi cập nhật metadata. Tuy nhiên, trong tác vụ biên soạn học liệu này, các đoạn code được cung cấp để học và tự thực hành; **không chạy vòng test hay QA chuyên môn**.

## 19. Những lỗi thường gặp và cách phòng tránh

1. **Nhầm `size` với số con trực tiếp.** `size` tính toàn bộ phần tử ở cây con, không chỉ con ngay dưới nút.
2. **Đếm số nút vật lý thay vì số phần tử có trùng.** Với `count=3`, nút đóng góp **ba** phần tử vào `size`.
3. **Quên xác định rank đánh số từ `0` hay `1`.** Bài dùng `select(k)` từ `1` và `rank_lt` là số phần tử trước `x`.
4. **Chỉ viết `L+1` trong `select` khi có khóa trùng.** Phải dùng cả khoảng vị trí `L+1..L+count`.
5. **Đi sang phải nhưng chỉ trừ `size(left)+1`.** Với đa tập, phải trừ `size(left)+count`.
6. **Dùng sai dấu khi tính rank.** `rank_lt` và `rank_le` khác nhau tại khóa bằng `x`.
7. **Dùng `rank_lt(R)-rank_lt(L)` cho đoạn đóng.** Phải dùng `rank_le(R)-rank_lt(L)`.
8. **Cho rằng `select(k)` luôn trả khóa phân biệt.** Nhiều vị trí có thể thuộc cùng một nút `count>1`.
9. **Không kiểm tra `k` ngoài phạm vi.** `k=0` hoặc `k>n` phải bị từ chối.
10. **Thêm khóa trùng bằng cách tạo thêm một nút có khóa bằng khóa hiện tại nhưng vẫn dùng BST nghiêm ngặt.** Phải chọn chính sách trùng nhất quán.
11. **Tăng `count` mà không cập nhật `size` trên đường tổ tiên.** Dữ liệu và metadata sẽ lệch.
12. **Xóa một phần tử trong nút `count>1` rồi xóa luôn nút vật lý.** Làm mất những lần xuất hiện còn lại.
13. **Xóa nút hai con: chuyển cả `count` của kế nhiệm nhưng chỉ giảm một lần xuất hiện tại vị trí cũ.** Tạo hai nút cùng khóa và đếm sai.
14. **Giả định kế nhiệm inorder luôn là lá.** Nó có thể có con phải; phải nối con ấy khi tháo.
15. **Xóa khóa không tồn tại nhưng vẫn giảm `size`.** Cần cờ thành công hoặc trả cây không đổi.
16. **Quay cây mà quên tính lại `size`.** Nút bị đẩy xuống có cây con mới, nên metadata cũ sai.
17. **Quay trái rồi tính nút được nâng lên trước.** Nút nâng lên cần giá trị mới của nút bị đẩy xuống.
18. **Không nối lại gốc cây con mới sau phép xoay.** Có thể làm mất một phần cây trong cấu trúc truy cập được.
19. **Cho rằng có `size` là đủ để bảo đảm `O(\log n)`.** Phải có cây nền cân bằng thích hợp.
20. **Chỉ kiểm tra `size(root)`.** Kích thước tại nút giữa có thể sai dù tổng tại gốc đúng.
21. **Chỉ kiểm tra inorder mà bỏ qua metadata.** Dãy khóa tăng dần không chứng minh `select/rank` đúng.
22. **Cho rằng heap phù hợp cho rank tổng quát vì chiều cao thấp.** Heap không có bất biến phân vùng khóa của BST.
23. **Không phân biệt trung vị dưới/trên/trung bình.** Với `n` chẵn, phải nêu rõ kết quả mong muốn.
24. **Tính phân vị mà không nói phương pháp.** Nearest-rank khác các quy tắc nội suy.
25. **Quên rằng `to_sorted_list` có thể tạo danh sách rất lớn.** Chi phí kết quả phụ thuộc `n` phần tử, không chỉ `u` nút vật lý.
26. **Dùng khóa không có quan hệ thứ tự toàn phần đáng tin cậy.** `NaN` hoặc phép so sánh bất nhất có thể phá bất biến BST.
27. **Sửa khóa tại chỗ mà không tái tổ chức cây.** Có thể vi phạm giới hạn khóa do tổ tiên áp đặt.
28. **Cho phép nhiều luồng sửa/đọc cây đang cập nhật mà không đồng bộ.** Có thể quan sát `size` và liên kết không cùng một phiên bản.
29. **Thêm trường `parent` nhưng không cập nhật khi xoay.** Thuật toán `RANK-NODE` từ dưới lên sẽ sai.
30. **Dùng validator `O(u)` sau mọi cập nhật mà vẫn khẳng định thao tác chỉ `O(\log u)`.** Phải phân biệt đường vận hành và kiểm thử.

## 20. Bài tập thực hành có đáp án

### Bài 1. Kích thước cây con khi không có khóa trùng

BST có gốc `8`, cây con trái `3` nút và cây con phải `5` nút. Nếu mỗi nút chỉ đóng góp một khóa, `size(8)` là bao nhiêu?

**Đáp án:** `size(8)=3+1+5=9`.

### Bài 2. Kích thước khi có bội số

Một nút `u` có `count=4`, cây con trái chứa `3` phần tử và cây con phải chứa `6` phần tử. `size(u)` bằng bao nhiêu?

**Đáp án:** `3+4+6=13`, dù bản thân `u` chỉ là **một nút vật lý**.

### Bài 3. Đọc cây ví dụ

Ở cây mẫu có gốc `8`, nút `4` có `count=2`, nút `10` có `count=3`. Tổng số khóa phân biệt và tổng số phần tử là bao nhiêu?

**Đáp án:** Có **7 khóa phân biệt/nút vật lý**: `2,4,6,8,10,12,14`. Có **10 phần tử** sau khi cộng các lần xuất hiện trùng.

### Bài 4. OS-SELECT thứ bảy

Trên dãy tăng `[2,4,4,6,8,10,10,10,12,14]`, `select(7)` trả giá trị gì?

**Đáp án:** **`10`**, vì các vị trí `6,7,8` đều nằm trong nhóm khóa `10`.

### Bài 5. Truy vết khi đi sang phải

Ở nút `u` có `size(left)=5`, `count(u)=2` và đang tìm thứ hạng `k=9`. Có đi phải không? Nếu có, `k'` bằng bao nhiêu?

**Đáp án:** Có. Vì `9>5+2=7` nên đi phải với `k'=9-7=2`.

### Bài 6. Truy vết khi khóa trùng

Ở nút `u` có `size(left)=5` và `count(u)=3`. Những thứ hạng nào trong cây con trả khóa của `u`?

**Đáp án:** **`6,7,8`**, vì `L<k≤L+C`, tương đương `5<k≤8`.

### Bài 7. Rank nhỏ hơn

Trên dãy mẫu, `rank_lt(10)` bằng bao nhiêu? Vì sao không đếm ba phần tử `10`?

**Đáp án:** **`5`**. Các phần tử nhỏ hơn `10` là `2,4,4,6,8`; phép đếm nghiêm ngặt không tính những phần tử bằng `10`.

### Bài 8. Rank nhỏ hơn hoặc bằng

Trên dãy mẫu, `rank_le(10)` bằng bao nhiêu?

**Đáp án:** **`8`**: gồm năm phần tử nhỏ hơn `10` và ba phần tử bằng `10`.

### Bài 9. Đếm xuất hiện

Nếu `rank_lt(4)=1` và `rank_le(4)=3`, có bao nhiêu phần tử bằng `4`?

**Đáp án:** `3-1=2` lần xuất hiện.

### Bài 10. Đếm đoạn đóng

Dùng `rank` tính số phần tử thuộc đoạn `[4,10]` trên dữ liệu mẫu.

**Đáp án:** `rank_le(10)-rank_lt(4)=8-1=7`.

### Bài 11. Đếm đoạn không có khóa nào

Trên dãy mẫu, số phần tử thuộc `[15,20]` bằng bao nhiêu?

**Đáp án:** **`0`**, vì tất cả phần tử đều nhỏ hơn `15`.

### Bài 12. Trung vị

Dãy mẫu có `10` phần tử. Nếu trung vị của số phần tử chẵn là trung bình hai giá trị giữa, trung vị bằng bao nhiêu?

**Đáp án:** Giá trị ở vị trí `5` là `8` và ở vị trí `6` là `10`; trung vị bằng **`9`**.

### Bài 13. Thêm khóa trùng

Ở cây mẫu ban đầu, thêm một phần tử `4`. `count(4)`, `size(4)` và `size(root)` lần lượt thay đổi thế nào?

**Đáp án:** `count(4):2→3`, `size(4):4→5`, `size(root):10→11`. Không cần tạo nút vật lý mới.

### Bài 14. Xóa bớt khóa trùng

Ở cây mẫu ban đầu, xóa một lần xuất hiện `10`. Nút `10` có bị xóa khỏi cây không? Tổng `size(root)` mới là bao nhiêu?

**Đáp án:** **Không** xóa nút vì `count(10)` giảm từ `3` xuống `2`. Tổng `size(root)` giảm từ `10` xuống **`9`**.

### Bài 15. Xóa nút hai con có kế nhiệm trùng

Cây mẫu có gốc `8`, kế nhiệm là nút `10` với `count=3`. Khi xóa `8` bằng cách sao chép kế nhiệm, phải làm gì với nút `10` cũ?

**Đáp án:** Sao chép **cả `key=10` và `count=3`** vào vị trí thay thế, đồng thời **tách toàn bộ nút `10` cũ** khỏi cây con phải. Không được chỉ giảm `count` của nút cũ đi một, vì sẽ tạo hai nút cùng khóa và đếm sai.

### Bài 16. Xóa khóa không tồn tại

Thực hiện `discard(999)` khi cây không chứa khóa `999`. Kết quả trả về và metadata phải thế nào?

**Đáp án:** Trả **`False`** và không thay đổi `count`, `size`, `height` hoặc liên kết.

### Bài 17. Phép xoay với `size`

Xoay trái tại `x` có con phải `y`. Tại sao phải tính lại `size(x)` trước `size(y)`?

**Đáp án:** Sau xoay, `x` có hai cây con mới, rồi `x` trở thành con trái của `y`. `size(y)` cần **giá trị mới của `size(x)`**, nên phải tính `x` trước.

### Bài 18. AVL so với BST suy biến

Nếu BST tăng cường `size` nhưng không cân bằng bị kéo thành một đường gồm `n` nút, `select(k)` có được bảo đảm `O(\log n)` không?

**Đáp án:** **Không.** Truy vấn đi xuống một đường có thể mất **`O(n)`**. Metadata không tự giảm chiều cao; cần cây nền cân bằng nếu muốn chặn trên logarit.

### Bài 19. Chi phí với khóa trùng

Một OST lưu `1000000` phần tử đều bằng `7` theo mô hình `count`. Có bao nhiêu nút vật lý và `root.size` bằng bao nhiêu?

**Đáp án:** Có **một nút** với `key=7, count=1000000` và `root.size=1000000`. Các truy vấn tìm theo khóa, select/rank tại cây này đi qua một nút.

### Bài 20. OS-RANK theo tham chiếu nút

Giả sử có liên kết `parent`, đang ở nút `u` là **con phải** của `p`. Khi đi lên `p` trong quá trình tính rank, cần cộng những nhóm phần tử nào?

**Đáp án:** Cộng toàn bộ `size(p.left)` phần tử trong cây con trái của `p` cùng `count(p)` lần xuất hiện ở chính `p`, vì chúng đều đứng trước các phần tử thuộc cây con phải.

### Bài 21. Đếm khóa phân biệt

Nếu một ứng dụng cần chọn **khóa phân biệt thứ `k`** chứ không phải phần tử thứ `k`, dùng trường `size` hiện tại có đủ không?

**Đáp án:** **Không.** `size` đếm cả lần xuất hiện trùng. Có thể lưu thêm `distinct_size=1+distinct_size(left)+distinct_size(right)` và dùng thuật toán tương tự nhưng với số **nút vật lý** thay vì bội số.

### Bài 22. Chọn cấu trúc

Một hệ thống có miền điểm số nguyên hữu hạn từ `0` tới `100`, chèn/xóa và truy vấn thứ hạng thường xuyên. Có bắt buộc dùng OST không?

**Đáp án:** **Không.** Vì miền khóa nhỏ và cố định, có thể dùng **mảng tần suất**, Fenwick tree hoặc segment tree trên miền điểm. OST đặc biệt hữu ích khi miền khóa rộng, thay đổi động hoặc không muốn xây một mảng lớn cho miền chỉ số.

### Bài 23. So sánh mảng đã sắp và OST

Nếu dữ liệu cố định và chỉ có truy vấn `select(k)`, cấu trúc nào có lợi thế rõ ràng?

**Đáp án:** **Mảng đã sắp** thường đơn giản và đọc phần tử thứ `k` trong **`O(1)`**. OST hữu ích hơn khi cần **chèn/xóa thường xuyên** mà vẫn duy trì truy vấn thứ hạng hiệu quả.

### Bài 24. Phân vị nearest-rank

Với `n=10` phần tử và quy ước `k=⌈pn⌉`, phân vị `p=0.7` lấy phần tử ở vị trí nào trên dãy mẫu?

**Đáp án:** `k=⌈0.7×10⌉=7`, nên giá trị là **`10`**. Phải nêu rõ quy ước nearest-rank; cách nội suy khác có thể cho kết quả khác.

### Bài 25. Phân tích bộ nhớ

Một OST có `u` khóa phân biệt và `n≥u` lần xuất hiện. Bộ nhớ nút và metadata có bậc tăng trưởng nào? Nếu xuất mọi phần tử ra danh sách, bộ nhớ kết quả bằng bao nhiêu?

**Đáp án:** Cây có **`O(u)` bộ nhớ** vì mỗi khóa phân biệt có một nút. Danh sách kết quả chứa `n` lần xuất hiện cần **`O(n)` bộ nhớ**.

### Bài 26. Khi nào có thể kết luận thuật toán đúng?

Một cây có inorder tăng dần và `root.size` đúng. Đã đủ chứng minh `select/rank` đúng chưa?

**Đáp án:** **Chưa.** Cần đảm bảo BST hợp lệ **trên mọi cây con** và `size` đúng **tại mọi nút**. Một kích thước sai ở nút trung gian vẫn có thể làm `select/rank` đi nhánh sai.

## 21. Tổng kết

**Cây thống kê thứ tự (Order-Statistic Tree)** là một cây tìm kiếm có thứ tự được **tăng cường thông tin kích thước cây con**. Trường quan trọng nhất là:

\[
\boxed{
size(u)=size(u.left)+count(u)+size(u.right)
}
\]

với `count(u)=1` khi khóa phân biệt hoàn toàn. Nhờ `size(left)`, thuật toán:

- **`select(k)`** biết phần tử nhỏ thứ `k` thuộc cây trái, chính nút hiện tại hay cây phải.
- **`rank_lt(x)`** và **`rank_le(x)`** bỏ qua cả cây con khi đếm.
- **`count_range(L,R)`** dùng hiệu hai rank.
- **Trung vị và phân vị theo thứ hạng** dùng một hoặc hai truy vấn select.

Các truy vấn trên chỉ đi theo **một đường trong BST**, tốn `O(h+1)`. Nếu dùng cây nền **tự cân bằng** như AVL hoặc Red–Black Tree, thời gian được bảo đảm **`O(\log(u+1))`**, với `u` là số khóa phân biệt.

Điểm quyết định tính đúng không chỉ là **thêm trường `size`**. Mọi thao tác **chèn, xóa, sửa số lần xuất hiện và xoay cây** phải duy trì bất biến từ dưới lên. Đặc biệt, khi xóa một nút có hai con trong mô hình `count`, cần xử lý **toàn bộ nút kế nhiệm** chứ không sao chép bội số một cách thiếu nhất quán.

Khi lựa chọn cấu trúc dữ liệu, hãy phân biệt rõ **thứ hạng của phần tử có trùng** với **thứ hạng của khóa phân biệt**, chi phí truy vấn với chi phí cập nhật, và lợi ích của metadata với yêu cầu **cân bằng cây nền**. Đó là nền tảng để triển khai các hệ thống thống kê thứ tự động vừa đúng vừa hiệu quả.
