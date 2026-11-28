# Cây tìm kiếm có tổng, cực trị hoặc dữ liệu tổng hợp của cây con

## 1. Từ tìm kiếm theo khóa đến truy vấn thông tin tổng hợp

Một **cây tìm kiếm nhị phân** (*binary search tree*, BST) hỗ trợ tìm một khóa, chèn và xóa theo quan hệ thứ tự. Nhưng các ứng dụng không chỉ muốn biết một khóa có tồn tại:

- Trong cơ sở dữ liệu giao dịch, **tổng số tiền** của các giao dịch có ID thuộc đoạn `[100,200]` là bao nhiêu?
- Trong hệ thống cảm biến, **giá trị nhỏ nhất/lớn nhất** của các bản ghi có mốc thời gian thuộc một khoảng là gì?
- Trong bảng xếp hạng, một nhánh của cây chứa **bao nhiêu bản ghi** và tổng điểm của chúng?
- Trong bộ lập lịch, một phân vùng cây có thể được **bỏ qua hoàn toàn** nếu ta đã biết kết quả tổng hợp của nó không?

Nếu mỗi câu hỏi đều phải duyệt từng bản ghi, chi phí có thể là `O(n)`. Giải pháp của **cây tăng cường** (*augmented tree*) là lưu sẵn, tại mỗi nút, những **thông tin tổng hợp của toàn bộ cây con** dưới nút đó.

Ví dụ, thay vì chỉ lưu:

```text
node.key
node.value
node.left
node.right
```

ta còn lưu:

```text
node.count     # Số bản ghi trong cây con.
node.total     # Tổng các giá trị trong cây con.
node.minimum   # Giá trị nhỏ nhất trong cây con.
node.maximum   # Giá trị lớn nhất trong cây con.
```

Nhờ vậy, nếu một cây con nằm hoàn toàn trong đoạn truy vấn, ta dùng **metadata của nút gốc cây con** thay vì duyệt các hậu duệ.

> Tăng cường không thay đổi quy tắc BST-order. Nó bổ sung bất biến mới: metadata tại mỗi nút phải mô tả **đúng** tập phần tử trong cây con hiện tại, ngay cả sau chèn, xóa, cập nhật giá trị hoặc xoay cân bằng.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **khóa để sắp xếp BST** với **giá trị được tổng hợp**.
2. Phát biểu bất biến `sum`, `min`, `max` và `count` của một cây con.
3. Hiểu **phép kết hợp có tính kết hợp** (*associative combine*) và **phần tử đơn vị**, kể cả khi dữ liệu tổng hợp không giao hoán.
4. Tính **tổng tiền tố** và tổng trong khoảng khóa với `O(h)` thời gian.
5. Tính min/max theo khoảng bằng cách ghép những **cây con được bao trọn**, không được trừ hai giá trị cực trị tiền tố.
6. Cập nhật metadata đúng khi **insert, delete, thay value** và khi thực hiện các **rotation**.
7. Cài một **AVL tree tăng cường** có các thao tác tổng hợp và kiểm tra bất biến bằng Python.
8. Phân tích độ phức tạp theo chiều cao `h`, phân biệt cây cân bằng với BST lệch.
9. Lựa chọn giữa BST tăng cường, mảng tiền tố, Fenwick tree và segment tree.

Nội dung thuộc chương **Cây tăng cường** trong học phần **Cấu trúc dữ liệu**, hướng đến việc hiểu bất biến, thao tác và chi phí thời gian/bộ nhớ khi chọn cấu trúc từ mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị.

## 2. Khóa tìm kiếm và giá trị tổng hợp là hai vai trò khác nhau

Xét một bản ghi:

```text
(key=30, value=7)
```

Trong bài này:

- `key` là **số nguyên duy nhất**, dùng để xác định thứ tự của BST.
- `value` là **số nguyên có dấu**, được dùng để tính tổng, min, max.
- Mọi nút ở cây con trái có `key` **nhỏ hơn** khóa của cha.
- Mọi nút ở cây con phải có `key` **lớn hơn** khóa của cha.
- Không có điều kiện BST-order nào bắt buộc `value` tăng theo `key`.

Ví dụ, các cặp:

```text
(10, +4), (20, -3), (30, +7), (40, 0),
(50, +8), (60, -6), (70, +2)
```

được sắp trong cây theo **`key`**, còn những con số `+4,-3,+7,0,+8,-6,+2` là **payload** cần tổng hợp.

Nếu chọn tổng của **chính các khóa**, ta chỉ cần đặt `value=key`. Nhưng ví dụ dùng hai trường riêng để tránh hiểu nhầm rằng min/max payload có thể tìm bằng cách đi tới nút trái nhất/phải nhất. **Cực trị của value** không nhất thiết nằm tại các khóa cực tiểu/cực đại.

### Vì sao giả định khóa duy nhất?

Đây là một chính sách để giữ mã minh họa ngắn gọn: `put(key,value)` thêm khóa chưa có hoặc **ghi đè value của khóa đã có**. Không sinh hai nút cùng khóa.

Nếu ứng dụng cần nhiều bản ghi có cùng khóa, phải chọn rõ một trong các phương án:

- Khóa ghép `(key,unique_id)` để mỗi bản ghi có vị trí riêng.
- Một nút chứa **nhóm payload** cùng khóa, có tổng/min/max và số mục riêng của nhóm.
- Cây dạng multiset với `frequency` nếu mọi bản sao có cùng value.

Các bất biến cần được điều chỉnh tương ứng. **Không được mặc nhiên dùng `count=1` cho một nút chứa nhiều bản ghi logic.**

## 3. Bất biến tổng, min, max và số lượng trong cây con

Gọi `L` và `R` là cây con trái/phải của một nút `v`. Giả sử mỗi nút chứa đúng một bản ghi.

Đặt `count(None)=0`, `sum(None)=0`. Khi đó:

\[
\boxed{\begin{aligned}
count(v)&=count(L)+1+count(R),\\
sum(v)&=sum(L)+v.value+sum(R).
\end{aligned}}
\]

Đối với cực trị:

\[
\boxed{
min(v)=\min\bigl(v.value,\ min(L),\ min(R)\bigr)
}
\]

\[
\boxed{
max(v)=\max\bigl(v.value,\ max(L),\ max(R)\bigr)
}
\]

Tuy nhiên, với cây con rỗng, `min(None)` và `max(None)` cần **quy ước đúng**:

- Trong công thức toán học trên số thực mở rộng có thể dùng `min(None)=+\infty` và `max(None)=-\infty`.
- Trong mã có kiểu khóa/giá trị tổng quát, có thể dùng **`None`** biểu diễn “không có cực trị” rồi bỏ qua khi kết hợp.

**Không dùng `0` làm min/max của cây rỗng.** Nếu mọi value đều dương, `min=0` sẽ sai; nếu mọi value đều âm, `max=0` cũng sai.

### Phải đếm trên đúng miền dữ liệu

Metadata tổng hợp ở một nút bao gồm **chính nút đó và tất cả hậu duệ**, không chỉ con trực tiếp. `count` là số bản ghi, còn `height` (nếu dùng AVL) là chiều cao cây: hai khái niệm không thể thay cho nhau.

### Bất biến độc lập với hình dạng cây

BST có thể thay đổi hình dạng qua rotation. Miễn là mỗi nút tính lại metadata từ các con đang gắn **sau khi đổi liên kết**, các công thức vẫn đúng. Đó là điểm mấu chốt khiến tổng hợp cây con tương thích với cây tìm kiếm cân bằng.

## 4. Ví dụ cụ thể: cây có giá trị âm, dương và bằng 0

Từ bảy cặp `(key,value)` ở phần 2, dựng một BST cân bằng:

```text
                              (40, value=0)
                             /             \
                    (20, value=-3)      (60, value=-6)
                    /          \        /           \
              (10, +4)      (30, +7) (50, +8)     (70, +2)
```

Đọc `(key,value)`, không phải `(value,key)`.

| Nút khóa | Value | Count cây con | Sum cây con | Min value cây con | Max value cây con |
|---:|---:|---:|---:|---:|---:|
| `10` | `4` | 1 | 4 | 4 | 4 |
| `30` | `7` | 1 | 7 | 7 | 7 |
| `20` | `-3` | 3 | `4-3+7=8` | -3 | 7 |
| `50` | `8` | 1 | 8 | 8 | 8 |
| `70` | `2` | 1 | 2 | 2 | 2 |
| `60` | `-6` | 3 | `8-6+2=4` | -6 | 8 |
| `40` | `0` | 7 | `8+0+4=12` | -6 | 8 |

Ta có:

```text
count(root)   = 7
sum(root)     = 12
minimum(root) = -6    # Ở khóa 60, KHÔNG phải khóa nhỏ nhất.
maximum(root) = 8     # Ở khóa 50.
```

Đây là kết quả tổng hợp của **toàn bộ cây**. Chỉ cần đọc metadata ở `root`, không phải cộng từng node khi truy vấn.

### Truy vấn theo đoạn khóa

Với đoạn đóng `[25,65]`, các khóa hợp lệ là `30,40,50,60`, có value `7,0,8,-6`:

```text
count = 4
sum   = 7 + 0 + 8 - 6 = 9
min   = -6
max   = 8
```

Các phần sau sẽ tính kết quả ấy mà **không cần duyệt mọi phần tử trong khoảng**, nhờ metadata của các cây con bao trọn.

## 5. Cấu trúc tổng hợp từ phép kết hợp

Thay vì viết bốn thuật toán riêng cho count, tổng, min và max, ta có thể gói kết quả của một tập phần tử thành:

\[
\boxed{A=(count,\ sum,\ minimum,\ maximum).}
\]

Ví dụ:

```text
A1 = tổng hợp của [4, -3]  = (2, 1, -3, 4)
A2 = tổng hợp của [7, 0]   = (2, 7, 0, 7)

A1 ⊕ A2                  = (4, 8, -3, 7)
```

Với hai tổng hợp `A` và `B`, định nghĩa `combine(A,B)` bằng:

\[
\begin{aligned}
count(A\oplus B)&=count(A)+count(B),\\
sum(A\oplus B)&=sum(A)+sum(B),\\
min(A\oplus B)&=\min(min(A),min(B)),\\
max(A\oplus B)&=\max(max(A),max(B)),
\end{aligned}
\]

trong đó cực trị của tập rỗng được **bỏ qua**.

### Tính kết hợp

Phép kết hợp phải thỏa:

\[
\boxed{(A\oplus B)\oplus C=A\oplus(B\oplus C).}
\]

Vì cộng, min và max đều **có tính kết hợp**, ta có thể tổng hợp các nhóm theo thứ tự cây mà không cần đi xuống mọi phần tử. Việc một rotation thay cách đặt ngoặc trong phép kết hợp không đổi kết quả tổng hợp.

### Phần tử đơn vị

Cần một tổng hợp rỗng `E` sao cho:

\[
\boxed{E\oplus A=A\oplus E=A.}
\]

Với count, sum, min/max, ta chọn:

```text
E = (count=0, sum=0, minimum=None, maximum=None)
```

`None` nghĩa là **không có giá trị**, không phải một payload hợp lệ để so lớn/nhỏ. Phép `combine` chỉ xét cực trị thật sự có mặt.

Một tập có **phép kết hợp kết hợp được và phần tử đơn vị** được gọi là một **monoid**. Đây là mô hình đại số quen thuộc cho metadata của segment tree, cây tìm kiếm tăng cường và nhiều cấu trúc khác.

### Không phải hàm thống kê nào cũng có tóm tắt kích thước cố định

Sum, min, max và count gộp được trong `O(1)`. Nhưng **trung vị chính xác** của hợp hai tập không thể suy ra chỉ từ bộ `(count,sum,min,max)` của từng tập.

Nếu cần median/quantile chính xác trên dữ liệu động, có thể phải giữ **thông tin thứ tự** như subtree size của cây tìm kiếm, các tần suất, hoặc cấu trúc chuyên biệt — chứ không thể thêm một trường `median` rồi hy vọng gộp hai cây con trong `O(1)` bằng bốn thống kê trên.

## 6. Một tổng hợp có thể không giao hoán

Trong ví dụ sum/min/max, `A\oplus B=B\oplus A` cũng đúng. Nhưng điều kiện bắt buộc để tổng hợp theo cây là **kết hợp được**, **không nhất thiết giao hoán**.

Ví dụ, mỗi nút chứa một đoạn văn bản và `combine` là phép **nối chuỗi**:

```text
"ab" + "cd" = "abcd"
"cd" + "ab" = "cdab"
```

Phép nối chuỗi có tính kết hợp:

\[
(a+b)+c=a+(b+c),
\]

nhưng không giao hoán:

\[
a+b\ne b+a\quad\text{nói chung}.
\]

Với cây tìm kiếm theo khóa tăng, thứ tự tổng hợp đúng phải là:

\[
\boxed{aggregate(v)=aggregate(v.left)\ \oplus\
payload(v)\ \oplus\ aggregate(v.right).}
\]

Nếu tráo cây trái và cây phải, kết quả nối chuỗi có thể sai dù các trường `sum/min/max` vẫn không đổi.

Các ví dụ tổng/min/max trong bài dùng tổ hợp giao hoán, nhưng khi thiết kế tổng hợp **ma trận, chuỗi, hàm biến đổi hoặc phép nhân không giao hoán**, phải bảo toàn **thứ tự in-order** khi cập nhật và truy vấn.

## 7. Tổng hợp toàn bộ cây và một cây con: O(1) khi đã có gốc

Nếu `root` là gốc cây đã được cập nhật metadata đúng:

```text
aggregate_all() = root.aggregate
```

Đọc tổng/min/max/count toàn cây có **`O(1)` thời gian** (chưa tính cách sao chép payload lớn).

Tương tự, nếu đã có **handle tới một nút `v`**, việc đọc aggregate của **toàn bộ cây con gốc `v`** là `O(1)`.

Nhưng phải phân biệt:

- **Đã có handle tới `v`:** đọc metadata `O(1)`.
- **Chỉ biết khóa `k`:** cần tìm nút có khóa đó, mất `O(h)`, rồi mới đọc metadata `O(1)`.

Và một cây con theo hình dạng cây **không đồng nghĩa** với một đoạn khóa tùy ý `[lo,hi]`. Muốn tổng hợp một đoạn khóa, phải chọn/cắt thành các phần phù hợp với BST-order.

## 8. Tổng tiền tố theo khóa: không duyệt những phần đã biết

Định nghĩa:

\[
prefix_{<}(x)=\sum_{\text{nút }v:\,v.key<x}v.value.
\]

Ta tìm từ gốc xuống. Tại nút `v`:

- Nếu `x\le v.key`, cả nút `v` và cây phải đều có khóa `\ge x`. Ta đi **trái**, không cộng.
- Nếu `x>v.key`, **toàn bộ cây trái** và chính nút `v` có khóa `<x`. Ta cộng ngay `sum(v.left)+v.value`, rồi đi **phải**.

### Mã giả

```text
PREFIX_LT(root, x):
    result = 0
    v = root

    while v is not null:
        if x <= v.key:
            v = v.left
        else:
            result += sum(v.left) + v.value
            v = v.right

    return result
```

### Tổng nhỏ hơn hoặc bằng

Định nghĩa:

\[
prefix_{\le}(x)=\sum_{v.key\le x}v.value.
\]

Thuật toán chỉ đổi nhánh so sánh: nếu `x<v.key` thì đi trái, còn nếu `x\ge v.key` thì cộng `sum(left)+value` rồi đi phải.

**Độ phức tạp:** mỗi vòng đi xuống một cạnh, làm `O(1)` phép tính; tổng **`O(h)` thời gian** và **`O(1)` bộ nhớ phụ** với bản lặp. Với AVL/red-black tree cân bằng, `h=O(\log n)`.

### Value âm vẫn hợp lệ

Tiền tố **không nhất thiết tăng** nếu payload có số âm; điều này không ảnh hưởng tính đúng của phép cộng. Thuật toán đi theo **khóa**, không giả định sum là một hàm đơn điệu.

## 9. Tổng theo khoảng bằng hiệu hai tiền tố

Với khoảng đóng `[lo,hi]`, giả sử `lo\le hi`:

\[
\boxed{
sum_{[lo,hi]}=prefix_{\le}(hi)-prefix_{<}(lo).
}
\]

Đối với khoảng nửa kín `[lo,hi)`:

\[
\boxed{
sum_{[lo,hi)}=prefix_{<}(hi)-prefix_{<}(lo).
}
\]

### Ví dụ với cây phần 4

```text
key:    10   20   30   40   50   60   70
value:   4   -3    7    0    8   -6    2
```

Tính tổng đoạn đóng `[25,65]`:

```text
prefix_le(65) = 4-3+7+0+8-6 = 10
prefix_lt(25) = 4-3         = 1

sum_[25,65]   = 10-1 = 9
```

Không phải duyệt từng phần tử: mỗi phép prefix chỉ đi theo một đường gốc–lá, cộng aggregate của các cây con được bỏ qua.

### Không dùng `hi+1` nếu không cần

Với khóa số nguyên, đôi khi thấy công thức `prefix_lt(hi+1)-prefix_lt(lo)`. Nhưng:

- Nó không áp dụng trực tiếp cho kiểu khóa không có khái niệm `+1` như chuỗi, timestamp hoặc khóa ghép.
- Trên kiểu số nguyên cố định, `hi+1` có thể tràn khi `hi` là giá trị lớn nhất.

Dùng riêng hai phép `prefix_lt` và `prefix_le` rõ nghĩa hơn.

### Vì sao lấy hiệu được với sum nhưng không được với min/max?

Phép cộng có phần tử nghịch đảo: nếu `prefix_le(hi)` là tổng phần trước và trong đoạn, có thể trừ tổng phần trước đoạn.

Nhưng `min` và `max` **không có phép trừ tương ứng**:

```text
min([1, 5, 7]) = 1
min([1])       = 1

Không có phép "1 - 1" nào khôi phục min([5, 7]) = 5.
```

Muốn hỏi min/max theo khoảng, cần một phương pháp **tập hợp các cây con được bao trọn**, không thể áp nguyên công thức hiệu tiền tố của sum.

## 10. Min/max theo khoảng: phân rã thành các cây con phù hợp

Giả sử truy vấn theo đoạn khóa đóng `[lo,hi]`. Ta muốn lấy **value nhỏ nhất/lớn nhất** của những nút có khóa trong đoạn.

Một cách cài hiệu quả là lưu thêm tại mỗi nút:

```text
subtree_min_key    # Khóa bé nhất trong toàn cây con.
subtree_max_key    # Khóa lớn nhất trong toàn cây con.
```

Hai trường này được dùng để nhận biết xem **toàn bộ cây con** có nằm trong khoảng truy vấn không. Chúng khác hoàn toàn với `min_value/max_value` của payload.

### Ba trường hợp khi xét một cây con T

**1. Không giao với đoạn:**

```text
T.max_key < lo hoặc T.min_key > hi
```

Khi đó bỏ qua `T` và trả **aggregate rỗng**.

**2. Nằm hoàn toàn trong đoạn:**

```text
lo <= T.min_key và T.max_key <= hi
```

Lấy thẳng `T.aggregate` trong **`O(1)`**, không đi xuống con.

**3. Giao một phần:**

Phải xét những nhánh cần thiết, cộng thông tin nút hiện tại nếu `lo\le key\le hi`, rồi kết hợp bằng `combine`.

### Mã giả

```text
RANGE_AGG(T, lo, hi):
    if T == null or lo > hi:
        return EMPTY

    if T.max_key < lo or hi < T.min_key:
        return EMPTY

    if lo <= T.min_key and T.max_key <= hi:
        return T.aggregate

    if T.key < lo:
        return RANGE_AGG(T.right, lo, hi)
    if T.key > hi:
        return RANGE_AGG(T.left, lo, hi)

    return COMBINE(
        RANGE_AGG(T.left, lo, hi),
        SINGLE(T.value),
        RANGE_AGG(T.right, lo, hi)
    )
```

Hàm `COMBINE` ba đối số là cách viết tắt của kết hợp **theo thứ tự** hai lần, ví dụ `combine(combine(A,B),C)`.

### Phức tạp của truy vấn theo khoảng

Với một **khoảng khóa liên tục**, những cây con bị cắt ở biên chỉ nằm dọc theo **tối đa hai đường tìm kiếm biên**. Các cây con ở giữa được nhận nguyên khối trong `O(1)`. Trên BST cân bằng chiều cao `h`, số nút/khối cần xử lý là **`O(h)`**, vì mỗi tầng chỉ phát sinh một số lượng hằng định các nhánh phải tiếp tục đào sâu.

Vì vậy:

\[
\boxed{T_{\mathrm{rangeAgg}}=O(h)=O(\log n)\text{ với cây cân bằng}}
\]

cho **một đoạn khóa liên tục** và một aggregate kết hợp trong `O(1)`. Nếu yêu cầu **liệt kê mọi bản ghi**, còn có chi phí xuất kết quả `O(k)` với `k` bản ghi trong đoạn.

Không nên suy rộng cận `O(\log n)` này cho một tập điều kiện lọc **tùy ý không tạo thành khoảng liên tục theo thứ tự BST**, ví dụ “lấy value lớn hơn 100” khi cây được sắp theo ID. Loại lọc ấy có thể phải duyệt nhiều nút, trừ khi lưu thêm chỉ mục phù hợp.

## 11. Theo dõi một truy vấn khoảng với ví dụ

Dùng cây phần 4 và hỏi `aggregate_range(25,65)`.

```text
                              40:0
                         /             \
                     20:-3           60:-6
                    /    \           /     \
                 10:+4  30:+7     50:+8   70:+2
```

Tại gốc `40`:

- `40` thuộc `[25,65]`, nên lấy `SINGLE(0)`.
- Cây trái gốc `20` có khóa từ `10` tới `30`, chỉ **giao một phần**.
- Cây phải gốc `60` có khóa từ `50` tới `70`, cũng **giao một phần**.

Tại nút `20`:

- `20<25` nên bản thân `20` và cây trái đều không đủ điều kiện.
- Chỉ xét cây phải gốc `30`. Cây con này nằm trọn trong đoạn, trả `aggregate(30)=(count=1,sum=7,min=7,max=7)`.

Tại nút `60`:

- `60` nằm trong khoảng, thêm payload `-6`.
- Cây trái gốc `50` nằm hoàn toàn trong đoạn, trả aggregate `(1,8,8,8)`.
- Cây phải gốc `70` nằm ngoài khoảng, trả rỗng.

Gộp lại theo thứ tự khóa:

```text
key=30: value +7
key=40: value  0
key=50: value +8
key=60: value -6

count=4; sum=9; min=-6; max=8
```

Nếu một cây con lớn chứa hàng nghìn khóa mà toàn bộ nằm giữa `25` và `65`, thuật toán có thể dùng metadata ngay tại gốc cây con ấy, không cần xuống từng nút. Đó là lợi thế thực sự của tăng cường thông tin tổng hợp.

## 12. Thay giá trị của một khóa đã có: không phải xoay

Giả sử khóa `50` đang có `value=8` và ta thay bằng `value=-10`.

BST vẫn có **cùng tập khóa và cùng hình dạng**, vì khóa tìm kiếm không đổi. Chỉ metadata tổng hợp phải cập nhật trên đường từ nút `50` lên gốc.

Trên cây phần 4:

```text
Trước: values [4,-3,7,0,8,-6,2]
Sau:   values [4,-3,7,0,-10,-6,2]

Tổng toàn cây: 12 -> -6
Min toàn cây:  -6 -> -10
Max toàn cây:   8 -> 7
Count:          7 -> 7
```

**Không cần xoay vì value thay đổi.** AVL/red-black chỉ cân bằng theo hình dạng cây và thứ tự **key**, còn value được dùng cho aggregate.

### Phải tính lại cả min/max

Đối với sum, có thể cập nhật theo chênh lệch:

\[
sum_{\mathrm{new}}=sum_{\mathrm{old}}+(newValue-oldValue)
\]

trên các tổ tiên.

Nhưng nếu `value` trước đó là **min/max duy nhất**, không thể chỉ “trừ” hoặc “cộng” để tìm min/max mới. Cần **recalculate từ metadata của hai con và value hiện tại**. Đây là lý do nên dùng một hàm `recalc(node)` duy nhất, không bảo trì riêng lẻ từng metadata bằng quy tắc tùy tiện.

## 13. Insert: cập nhật tăng cường theo đường đi tìm

Để thêm `(key,value)` vào AVL/BST:

1. Tìm đúng vị trí theo `key`.
2. Nếu chưa có khóa, tạo một nút lá với aggregate của một value.
3. Nếu khóa đã có, theo chính sách của bài, **ghi đè value** thay vì tạo nút thứ hai.
4. Khi quay ngược đường tìm, tính lại aggregate của mọi tổ tiên.
5. Nếu dùng AVL/red-black, cân bằng bằng rotation và **tính lại metadata sau mỗi rotation**.

### Ví dụ thêm khóa mới

Thêm `(35,5)` vào cây ví dụ:

```text
40 -> trái 20 -> phải 30 -> phải (rỗng)
```

Nút `35` được đặt đúng BST-order. Sau đó, các nút trên đường `35→30→20→40` phải cập nhật lại count/sum/min/max, và có thể thực hiện rotation để khôi phục cân bằng.

### Ví dụ ghi đè

`put(30,-2)` không làm tăng số nút vì `key=30` đã tồn tại:

```text
count(root) giữ nguyên.
sum(root) giảm 9 đơn vị (từ +7 xuống -2).
minimum(root) có thể đổi; phải tính lại, không đoán.
```

Trong cả hai trường hợp, **một đường gốc–lá** đủ để cập nhật metadata và cân bằng nếu cây có bất biến AVL/red-black.

## 14. Delete: cẩn thận khi dùng nút kế tiếp

Xóa một khóa có ba trường hợp BST chuẩn:

1. **Lá:** bỏ nút, trả `None` tại vị trí đó.
2. **Một con:** nối con duy nhất của nút vào chỗ cũ.
3. **Hai con:** tìm **inorder successor** — nút có khóa nhỏ nhất ở cây con phải — rồi dùng successor để thay vị trí nút cần xóa.

### Không chỉ chuyển key mà quên payload

Giả sử cần xóa nút khóa `40`, còn successor là khóa `50` với `value=8`.

Nếu chỉ chuyển `key=50` vào vị trí `40` nhưng giữ `value=0`, cây có thể vẫn đúng **BST-order**, nhưng đã **mất bản ghi `(50,8)`** và thay bằng bản ghi sai `(50,0)`. Tổng và cực trị sẽ sai so với dữ liệu nghiệp vụ.

Phải:

- Chuyển **cả bản ghi `(key,value)`** của successor; hoặc
- Di chuyển nguyên **nút successor** sang vị trí nút đã xóa.

Sau đó tính lại metadata trên các đường thay đổi liên kết.

### Vì sao việc xóa khó hơn chỉ cập nhật count?

Khi xóa một node mang giá trị nhỏ nhất hoặc lớn nhất của một cây con, không thể khôi phục cực trị mới bằng “nghịch đảo” của min/max. Phải tính lại từ các cây con còn lại.

Trong triển khai AVL bên dưới, ta **gỡ nguyên nút successor** rồi chuyển nút ấy sang vị trí cần thay, sau đó rebalance. Không để hai nút cùng khóa và không làm mất value đi kèm khóa.

## 15. Rotation: bảo trì metadata đúng thứ tự

Xét phép **xoay trái** tại `x`, với con phải `y`:

```text
Trước:                             Sau:

           x                                y
          / \                              / \
         A   y                            x   C
            / \                          / \
           B   C                        A   B
```

Tập khóa theo thứ tự **không đổi**: `A,x,B,y,C`. Nhưng nội dung **cây con của `x` và `y`** thay đổi, nên metadata của hai nút phải cập nhật.

Sau khi sửa liên kết:

\[
\begin{aligned}
agg(x)&=agg(A)\oplus single(value_x)\oplus agg(B),\\
agg(y)&=agg(x)\oplus single(value_y)\oplus agg(C).
\end{aligned}
\]

Do `agg(y)` phụ thuộc vào `agg(x)` **mới**, thứ tự đúng là:

```text
rotate_left(x):
    y = x.right
    B = y.left
    x.right = B
    y.left = x
    recalc(x)   # Nút đi xuống.
    recalc(y)   # Gốc mới.
    return y
```

Xoay phải tương tự: **tính lại nút đi xuống trước**, sau đó gốc mới.

### Metadata nào cần cập nhật?

Với AVL ví dụ của bài:

- `height`: để giữ cân bằng.
- `aggregate`: count/sum/min/max.
- `lo_key` và `hi_key`: để biết khoảng khóa thực sự của cây con khi truy vấn range.

**Đừng cập nhật mỗi `height` và quên aggregate.** Cây có thể tìm theo khóa đúng nhưng trả tổng/min/max sai — kiểu lỗi khó thấy nếu bài kiểm tra chỉ có `get(key)` mà thiếu truy vấn khoảng.

## 16. Tổng hợp có tính kết hợp giúp tăng cường dễ bảo trì

Một augmentation thích hợp cần trả lời:

1. **Dữ liệu cục bộ của nút là gì?** Ví dụ payload `value`.
2. **Metadata của cây rỗng là gì?** Ví dụ `E=(0,0,None,None)`.
3. **Kết hợp hai kết quả mất bao lâu?** Ví dụ `O(1)` cho sum/min/max/count.
4. **Có tính kết hợp không?** Nếu không, đổi hình dạng cây có thể đổi kết quả sai.
5. **Thứ tự kết hợp có quan trọng không?** Với phép không giao hoán phải giữ `left→node→right`.
6. **Cập nhật cục bộ được không?** Sau insert/delete/rotation chỉ cần tính lại một số nút trên đường bị tác động.

Với aggregate có kích thước cố định và kết hợp `O(1)`, việc bảo trì aggregate sau một rotation tốn **`O(1)`**. Mỗi phép insert/delete trên cây cân bằng AVL vẫn đi qua `O(\log n)` nút, nên thêm augmentation **không làm đổi bậc Big-O của thao tác cập nhật**.

**Không phải mọi metadata đều hợp:** nếu `aggregate` tại mỗi nút là **danh sách mọi giá trị của cây con**, một lần gộp có thể tốn `O(\text{size subtree})` và chiếm bộ nhớ vượt `O(n)`. Cần chọn thông tin tóm tắt có kích thước và phép kết hợp phù hợp với nhu cầu.

## 17. Thiết kế mã Python: một Aggregate dùng chung cho toàn cây

Ta sẽ cài một **AVL tree** có những tính chất sau:

- Khóa `key` là **số nguyên duy nhất**, dùng cho BST-order.
- Giá trị `value` là **số nguyên có dấu**, cần tổng/min/max.
- `put(key,value)`: thêm hoặc **ghi đè** giá trị của khóa hiện có.
- `delete(key)`: xóa hẳn nút chứa khóa, báo `KeyError` nếu không tồn tại.
- `get(key)`: lấy payload của một khóa.
- `stats()`: aggregate toàn bộ cây.
- `prefix_sum_lt(key)`, `prefix_sum_le(key)`: tổng tiền tố.
- `range_stats(lo,hi)`: count, sum, min, max cho đoạn **đóng** `[lo,hi]`.
- `check_invariants()`: kiểm tra BST-order, cân bằng AVL và toàn bộ metadata.

Đây là mã học thuật tự chứa; ghép các khối theo thứ tự trong phần 17–20 thành **một tệp Python**. Đoạn mã trong bài **không được chạy trong quá trình biên soạn STEP 4**.

### 17.1. Phần tử đơn vị và phép combine

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Aggregate:
    count: int = 0
    total: int = 0
    minimum: int | None = None
    maximum: int | None = None


EMPTY = Aggregate()


def single(value: int) -> Aggregate:
    return Aggregate(1, value, value, value)


def optional_min(a: int | None, b: int | None) -> int | None:
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def optional_max(a: int | None, b: int | None) -> int | None:
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def combine(a: Aggregate, b: Aggregate) -> Aggregate:
    return Aggregate(
        count=a.count + b.count,
        total=a.total + b.total,
        minimum=optional_min(a.minimum, b.minimum),
        maximum=optional_max(a.maximum, b.maximum),
    )
```

Điểm cần quan sát:

- `EMPTY` thật sự là đơn vị: `combine(EMPTY,A)==A`.
- `minimum=None` nghĩa là **không có phần tử**, không phải khóa hay value `0`.
- Value âm vẫn được cộng và lấy cực trị chính xác.
- `Aggregate` là bất biến (*immutable*) nhờ `frozen=True`, tránh sửa trực tiếp một kết quả được chia sẻ làm metadata.

### 17.2. Nút AVL chứa khoảng khóa và aggregate

```python
@dataclass
class Node:
    key: int
    value: int
    left: Node | None = None
    right: Node | None = None
    height: int = 1
    lo_key: int = field(init=False)
    hi_key: int = field(init=False)
    aggregate: Aggregate = field(init=False)

    def __post_init__(self) -> None:
        self.lo_key = self.key
        self.hi_key = self.key
        self.aggregate = single(self.value)


def node_height(node: Node | None) -> int:
    return 0 if node is None else node.height


def node_aggregate(node: Node | None) -> Aggregate:
    return EMPTY if node is None else node.aggregate


def recalc(node: Node) -> None:
    """Tính lại metadata từ hai con đang gắn vào node."""
    node.height = 1 + max(
        node_height(node.left), node_height(node.right)
    )
    node.lo_key = node.left.lo_key if node.left else node.key
    node.hi_key = node.right.hi_key if node.right else node.key
    node.aggregate = combine(
        combine(node_aggregate(node.left), single(node.value)),
        node_aggregate(node.right),
    )


def balance_factor(node: Node) -> int:
    return node_height(node.left) - node_height(node.right)
```

`lo_key` và `hi_key` **không phải cực trị của value**. Chúng là hai **khóa biên** của cây con theo thứ tự BST. Bản cài đặt có cả hai để nhận biết nhanh cây con nằm ngoài/trong đoạn khóa.

Trong một BST với khóa duy nhất, khóa nhỏ nhất của cây con nằm ở phía trái nhất, nên sau `recalc`:

```text
node.lo_key = left.lo_key  nếu có left; ngược lại node.key
node.hi_key = right.hi_key nếu có right; ngược lại node.key
```

Nếu so sánh các khóa là `O(1)` và metadata có kích thước cố định, `recalc` tốn **`O(1)`**.

## 18. AVL rotation và cân bằng đi kèm cập nhật aggregate

Mã sau sử dụng các định nghĩa ở phần 17.

```python
def rotate_left(x: Node) -> Node:
    y = x.right
    assert y is not None
    middle = y.left

    y.left = x
    x.right = middle

    recalc(x)  # Nút x đã đi xuống.
    recalc(y)  # Gốc y mới phụ thuộc vào aggregate(x) mới.
    return y


def rotate_right(y: Node) -> Node:
    x = y.left
    assert x is not None
    middle = x.right

    x.right = y
    y.left = middle

    recalc(y)  # Nút y đã đi xuống.
    recalc(x)  # Gốc x mới.
    return x


def rebalance(node: Node) -> Node:
    recalc(node)
    factor = balance_factor(node)

    if factor > 1:
        assert node.left is not None
        if balance_factor(node.left) < 0:
            node.left = rotate_left(node.left)
        return rotate_right(node)

    if factor < -1:
        assert node.right is not None
        if balance_factor(node.right) > 0:
            node.right = rotate_right(node.right)
        return rotate_left(node)

    return node
```

`rebalance` giải quyết các trường hợp AVL **LL, LR, RR và RL**. Mỗi lần xoay chỉ đổi một số liên kết và chạy `recalc` trên các nút vừa đổi quan hệ cha–con.

**Quan sát quan trọng:** nếu `put` chỉ đổi value tại một khóa đã tồn tại, `rebalance` vẫn đúng và tính lại aggregate, nhưng không cần xoay vì hình dạng không đổi. Cân bằng phụ thuộc **chiều cao các nhánh**, không phụ thuộc số âm/dương trong payload.

## 19. Chèn, thay payload và xóa nút không làm mất bản ghi

### 19.1. Thêm khóa hoặc ghi đè value

```python
def put_node(node: Node | None, key: int, value: int) -> Node:
    if node is None:
        return Node(key, value)

    if key < node.key:
        node.left = put_node(node.left, key, value)
    elif key > node.key:
        node.right = put_node(node.right, key, value)
    else:
        node.value = value  # Một khóa chỉ có một bản ghi.

    return rebalance(node)
```

### 19.2. Gỡ nguyên nút nhỏ nhất

```python
def detach_min(node: Node) -> tuple[Node | None, Node]:
    """Trả (gốc còn lại, nguyên nút có key nhỏ nhất)."""
    if node.left is None:
        remaining = node.right
        node.right = None
        return remaining, node

    node.left, smallest = detach_min(node.left)
    return rebalance(node), smallest
```

### 19.3. Xóa theo khóa

```python
def delete_node(node: Node | None, key: int) -> Node | None:
    if node is None:
        raise KeyError(key)

    if key < node.key:
        node.left = delete_node(node.left, key)
    elif key > node.key:
        node.right = delete_node(node.right, key)
    else:
        if node.left is None:
            return node.right
        if node.right is None:
            return node.left

        # Xóa nút hai con: chuyển NGUYÊN successor.
        new_right, successor = detach_min(node.right)
        successor.left = node.left
        successor.right = new_right
        node = successor

    return rebalance(node)
```

Khi successor thay một nút hai con:

- `successor.key` đi cùng `successor.value`; không có lỗi giữ nhầm value của khóa vừa xóa.
- Các con được gắn lại theo đúng thứ tự BST.
- `rebalance(successor)` cập nhật cả chiều cao, biên khóa và aggregate.
- Mỗi đường đệ quy trong `detach_min` cũng gọi `rebalance` khi đi ngược lên.

**Nếu chương trình công khai handle trỏ trực tiếp tới từng nút**, việc di chuyển nguyên nút có thể có ý nghĩa với quyền sở hữu và vòng đời handle; ví dụ này chỉ công khai **API theo khóa**, nên người gọi không dựa vào địa chỉ nút nội bộ.

## 20. Lớp AugmentedAVL: get, stats, prefix và range

Mã lớp sau dùng toàn bộ các hàm ở phần 17–19.

```python
class AugmentedAVL:
    def __init__(self) -> None:
        self.root: Node | None = None

    def __len__(self) -> int:
        return self.stats().count

    def put(self, key: int, value: int) -> None:
        self.root = put_node(self.root, key, value)

    def delete(self, key: int) -> None:
        self.root = delete_node(self.root, key)

    def get(self, key: int) -> int:
        node = self.root
        while node is not None:
            if key < node.key:
                node = node.left
            elif key > node.key:
                node = node.right
            else:
                return node.value
        raise KeyError(key)

    def stats(self) -> Aggregate:
        return node_aggregate(self.root)

    def prefix_sum_lt(self, key: int) -> int:
        """Tổng value của các nút có khóa < key."""
        answer = 0
        node = self.root
        while node is not None:
            if key <= node.key:
                node = node.left
            else:
                answer += node_aggregate(node.left).total + node.value
                node = node.right
        return answer

    def prefix_sum_le(self, key: int) -> int:
        """Tổng value của các nút có khóa <= key."""
        answer = 0
        node = self.root
        while node is not None:
            if key < node.key:
                node = node.left
            else:
                answer += node_aggregate(node.left).total + node.value
                node = node.right
        return answer

    def range_sum(self, lo: int, hi: int) -> int:
        if lo > hi:
            return 0
        return self.prefix_sum_le(hi) - self.prefix_sum_lt(lo)

    def _range_stats(
        self, node: Node | None, lo: int, hi: int
    ) -> Aggregate:
        if node is None or node.hi_key < lo or hi < node.lo_key:
            return EMPTY

        if lo <= node.lo_key and node.hi_key <= hi:
            return node.aggregate

        if node.key < lo:
            return self._range_stats(node.right, lo, hi)

        if node.key > hi:
            return self._range_stats(node.left, lo, hi)

        return combine(
            combine(
                self._range_stats(node.left, lo, hi),
                single(node.value),
            ),
            self._range_stats(node.right, lo, hi),
        )

    def range_stats(self, lo: int, hi: int) -> Aggregate:
        """Count, tổng, min, max của khóa trong đoạn đóng [lo,hi]."""
        if lo > hi:
            return EMPTY
        return self._range_stats(self.root, lo, hi)

    def check_invariants(self) -> bool:
        """Duyệt toàn cây O(n): chỉ nên dùng cho kiểm thử/debug."""
        def walk(
            node: Node | None,
            low: int | None,
            high: int | None,
        ) -> tuple[Aggregate, int, int | None, int | None]:
            if node is None:
                return EMPTY, 0, None, None

            assert low is None or low < node.key
            assert high is None or node.key < high

            la, lh, lmin, _ = walk(node.left, low, node.key)
            ra, rh, _, rmax = walk(node.right, node.key, high)

            expected = combine(
                combine(la, single(node.value)), ra
            )
            expected_lo = lmin if lmin is not None else node.key
            expected_hi = rmax if rmax is not None else node.key

            assert node.aggregate == expected
            assert node.lo_key == expected_lo
            assert node.hi_key == expected_hi
            assert node.height == 1 + max(lh, rh)
            assert abs(lh - rh) <= 1
            return expected, node.height, expected_lo, expected_hi

        try:
            aggregate, _, _, _ = walk(self.root, None, None)
            return aggregate == self.stats()
        except AssertionError:
            return False
```

### Những chi tiết dễ bỏ qua

1. `range_stats` trả `EMPTY` nếu không có khóa trong đoạn; vì thế `minimum` và `maximum` là `None`.
2. `range_sum` sử dụng hiệu hai tiền tố, nhưng `range_stats` không làm vậy cho min/max.
3. Hai biên `lo_key/hi_key` cho phép chấp nhận **nguyên cây con** mà không đi sâu.
4. `check_invariants` tự tính lại metadata từ các nút con để phát hiện lỗi cập nhật, thay vì chỉ tin `node.aggregate` đã lưu.
5. Bất biến AVL được kiểm qua `height` và chênh lệch chiều cao hai con.
6. `put` dùng chính sách ghi đè; muốn cộng dồn phải gọi `put(key, get(key)+delta)` hoặc thêm API `add_value` phù hợp.

## 21. Ví dụ sử dụng: tổng, cực trị và cập nhật động

Sau khi ghép mã ở phần 17–20:

```python
tree = AugmentedAVL()

for key, value in [
    (40, 0), (20, -3), (60, -6),
    (10, 4), (30, 7), (50, 8), (70, 2),
]:
    tree.put(key, value)

assert tree.check_invariants()
assert len(tree) == 7

print(tree.stats())
# Aggregate(count=7, total=12, minimum=-6, maximum=8)

print(tree.range_stats(25, 65))
# Aggregate(count=4, total=9, minimum=-6, maximum=8)

print(tree.prefix_sum_le(65))    # 10
print(tree.prefix_sum_lt(25))    # 1
print(tree.range_sum(25, 65))    # 9

tree.put(50, -10)               # Cập nhật value, không đổi key.
print(tree.stats())
# Aggregate(count=7, total=-6, minimum=-10, maximum=7)
assert tree.check_invariants()

tree.delete(20)                 # Nút có thể có hai con.
assert len(tree) == 6
print(tree.stats())
# Aggregate(count=6, total=-3, minimum=-10, maximum=7)
assert tree.check_invariants()
```

### Vì sao tổng sau cập nhật là -6?

Ban đầu `sum=12`. Đổi value khóa `50` từ `8` thành `-10` làm chênh lệch `-18`:

\[
12+(-10-8)=-6.
\]

Sau đó xóa nút khóa `20` có value `-3`:

\[
-6-(-3)=-3.
\]

Count giảm từ `7` xuống `6`. Min vẫn `-10` (khóa `50`), max là `7` (khóa `30`).

Các kết quả phải đúng dù AVL thay đổi hình dạng qua rotation; truy vấn được định nghĩa theo **tập cặp key/value**, không theo vị trí vật lý của nút.

## 22. Trường hợp rỗng, khoảng không giao và value âm

### Cây rỗng

```python
empty = AugmentedAVL()
assert empty.stats() == Aggregate()
assert empty.range_stats(0, 100) == Aggregate()
assert empty.range_sum(0, 100) == 0
assert empty.prefix_sum_lt(100) == 0
assert empty.check_invariants()
```

Không được trả min hoặc max là `0` cho cây rỗng. Kết quả `minimum=None, maximum=None` biểu diễn **không có phần tử**.

### Đoạn không chứa khóa nào

```python
tree = AugmentedAVL()
tree.put(10, -9)
tree.put(20, -4)

result = tree.range_stats(11, 19)
assert result == Aggregate()

result = tree.range_stats(0, 100)
assert result.count == 2
assert result.total == -13
assert result.minimum == -9
assert result.maximum == -4
```

Nếu dùng `minimum=0` làm giá trị mặc định, ví dụ này trả min sai vì `0` không có trong dữ liệu.

### Khoảng đảo ngược

Theo hợp đồng trong mã, `range_stats(lo,hi)` trả `EMPTY` nếu `lo>hi`. Một API khác có thể chọn **ném lỗi**; điều quan trọng là phải xác định trước và kiểm thử nhất quán.

### Khóa không tồn tại

`prefix_sum_lt(15)` vẫn có nghĩa vì nó cộng mọi nút có `key<15`; không cần tìm thấy đúng khóa `15`. Trong khi đó, `get(15)` và `delete(15)` báo `KeyError`, vì hai thao tác ấy đòi **một nút thực sự tồn tại**.

## 23. Phân tích thời gian và bộ nhớ

Gọi `n` là số **khóa phân biệt** (một nút cho một khóa), và `h` là chiều cao cây.

| Thao tác | BST tăng cường chưa cân bằng | AVL tăng cường |
|---|---|---|
| `get(key)` | `O(h)`, xấu nhất `O(n)` | `O(\log(n+1))` |
| `put(key,value)` | `O(h)` | `O(\log(n+1))` |
| `delete(key)` | `O(h)` | `O(\log(n+1))` |
| `stats()` toàn cây | `O(1)` | `O(1)` |
| Tổng/min/max **cây con đã có handle** | `O(1)` | `O(1)` |
| `prefix_sum_lt/le` | `O(h)` | `O(\log(n+1))` |
| `range_sum(lo,hi)` | `O(h)` | `O(\log(n+1))` |
| `range_stats(lo,hi)` cho một đoạn khóa liên tục | `O(h)` | `O(\log(n+1))` |
| `check_invariants()` toàn cây | `O(n)` | `O(n)` |
| Bộ nhớ nút và metadata | `O(n)` | `O(n)` |

### Bộ nhớ phụ của triển khai

- `get` và prefix trong ví dụ dùng vòng lặp: **`O(1)`** biến phụ.
- `_range_stats` dùng đệ quy theo chiều cao: **`O(h)`** không gian ngăn xếp. Với AVL là `O(\log(n+1))`.
- `put_node`, `delete_node`, `detach_min` dùng đệ quy: **`O(h)`** không gian ngăn xếp.
- `recalc` và mỗi rotation: **`O(1)`** phép kết hợp metadata, bộ nhớ tạm hằng số.

Một cây AVL có `height=O(\log n)` do bất biến cân bằng; **chỉ lưu metadata không làm một BST lệch thành AVL**. Nếu chèn khóa tăng dần vào BST thường mà không xoay, độ cao vẫn có thể `\Theta(n)` và mọi truy vấn theo đường tìm có thể chậm tuyến tính.

### Chi phí thực tế

Thêm aggregate và hai khóa biên làm **tăng số trường trên mỗi nút**. Khi mỗi phép cập nhật kéo theo nhiều `recalc`, hằng số thời gian cũng tăng. Nếu ứng dụng chỉ cần tìm khóa mà không hỏi tổng/min/max/range, augmentation có thể không đáng chi phí.

## 24. Kiểm thử chéo với mô hình tham chiếu

Một cách kiểm tra cấu trúc động là giữ **`dict` tham chiếu** của các cặp key/value và sau mỗi thao tác so kết quả truy vấn với phép tính trực tiếp trên dict.

Đoạn sau là **mã ví dụ để người học tự chạy**, không phải kiểm thử được thực thi trong giai đoạn biên soạn bài:

```python
tree = AugmentedAVL()
reference: dict[int, int] = {}

operations = [
    ("put", 40, 0),
    ("put", 20, -3),
    ("put", 60, -6),
    ("put", 10, 4),
    ("put", 30, 7),
    ("put", 50, 8),
    ("put", 70, 2),
    ("put", 50, -10),
    ("delete", 20, None),
    ("put", 15, 9),
    ("delete", 60, None),
]

for operation, key, value in operations:
    if operation == "put":
        assert value is not None
        tree.put(key, value)
        reference[key] = value
    else:
        tree.delete(key)
        del reference[key]

    assert tree.check_invariants()
    assert len(tree) == len(reference)

    values = list(reference.values())
    expected = Aggregate(
        count=len(values),
        total=sum(values),
        minimum=min(values, default=None),
        maximum=max(values, default=None),
    )
    assert tree.stats() == expected

    for lo, hi in [
        (-100, 100), (25, 65), (11, 19), (50, 50), (90, 10),
    ]:
        chosen = [
            v for k, v in reference.items() if lo <= k <= hi
        ]
        direct = Aggregate(
            count=len(chosen),
            total=sum(chosen),
            minimum=min(chosen, default=None),
            maximum=max(chosen, default=None),
        )
        assert tree.range_stats(lo, hi) == direct
        assert tree.range_sum(lo, hi) == direct.total
```

### Vì sao kiểm thử này mạnh hơn chỉ nhìn cây?

Một lỗi `recalc` có thể không ảnh hưởng `get(key)` vì BST-order vẫn đúng. Nhưng phép so:

```text
tree.range_stats(lo,hi) == kết quả đếm trực tiếp trên dict
```

có thể phát hiện metadata sai sau một chuỗi rotation hoặc delete. Nên kết hợp **truy vấn độc lập trên nhiều đoạn khóa** với **kiểm tra bất biến tại từng nút**.

### Property testing nâng cao

Với mỗi tập key/value hợp lệ, những tính chất sau cần đúng:

\[
stats().count=n,
\qquad stats().total=\sum_{v}v.value.
\]

\[
rangeSum(-\infty,+\infty)=stats().total.
\]

\[
rangeSum(a,c)=rangeSum(a,b)+rangeSum(b,c)
\]

chỉ khi **chia khoảng không chồng lặp và không bỏ sót** theo quy ước phù hợp, chẳng hạn `[a,b)` và `[b,c)`. Với hai **khoảng đóng** `[a,b]` và `[b,c]`, nút khóa `b` sẽ bị **đếm hai lần** nếu tồn tại.

Các phép kiểm tra cần đặc biệt tập trung vào value âm, đoạn không chứa khóa, xóa gốc hai con và cập nhật một payload đang là min/max duy nhất.

## 25. Khi nhiều bản ghi cùng khóa

Trong phần cài đặt, một khóa `key` chỉ có một bản ghi, nên `put` ghi đè. Nếu bài toán dùng **multiset**, cần thay thiết kế.

### 25.1. Các bản sao có cùng value

Nếu một nút có khóa `k`, value `v` và `frequency=c`, đóng góp của nút là:

\[
count_{\mathrm{self}}=c,\qquad
sum_{\mathrm{self}}=cv,\qquad
min_{\mathrm{self}}=max_{\mathrm{self}}=v
\]

khi `c\ge1`.

Ví dụ: `(key=50,value=-2,count=3)` đóng góp count `3` và sum `-6`. Khi xóa một bản sao, giảm count và cập nhật metadata trên đường tới gốc; không phải xóa nút nếu `count>1`.

### 25.2. Các bản ghi cùng khóa có value khác nhau

Nếu một khóa `k` có payload `3,-5,7`, một trường `value` đơn lẻ không mô tả đủ dữ liệu. Có thể:

- Dùng khóa ghép `(key,unique_id)`, mỗi bản ghi là một nút.
- Lưu một **bucket** nhiều value trong nút và duy trì aggregate nội bộ bucket.

Với bucket có thể thêm/xóa tùy ý, cập nhật `min/max` của bucket không luôn `O(1)`: xóa phần tử đang là min có thể buộc quét bucket, trừ khi bucket có cấu trúc phụ như multiset cân bằng hoặc heap có chỉ mục.

**Luôn định nghĩa rõ “một phần tử” trong aggregate là một nút hay một bản ghi logic.**

## 26. Ví dụ nâng cao: tổng hợp max-subarray trên thứ tự khóa

Không chỉ sum/min/max, ta còn có thể lưu metadata **đủ để trả lời câu hỏi phức tạp hơn**.

Giả sử mỗi nút có một value và các nút được xem như **một dãy theo thứ tự khóa tăng**. Ta muốn tổng lớn nhất của **một đoạn con liên tiếp theo thứ tự ấy** (*maximum subarray sum*).

Với **đoạn không rỗng**, một tổng hợp có thể chứa:

```text
total        # Tổng toàn đoạn.
best_prefix  # Tổng lớn nhất của một tiền tố không rỗng.
best_suffix  # Tổng lớn nhất của một hậu tố không rỗng.
best        # Tổng lớn nhất của một đoạn con liên tiếp không rỗng.
```

Cho hai đoạn liên tiếp `A` rồi `B`, gộp trong `O(1)`:

\[
\begin{aligned}
total(AB)&=total(A)+total(B),\\
prefix(AB)&=\max(prefix(A),total(A)+prefix(B)),\\
suffix(AB)&=\max(suffix(B),total(B)+suffix(A)),\\
best(AB)&=\max(best(A),best(B),suffix(A)+prefix(B)).
\end{aligned}
\]

Ví dụ dãy giá trị theo thứ tự khóa:

```text
[-2, 3, -1, 4, -5]
        └───────┘
         3-1+4 = 6
```

Tổng đoạn con lớn nhất là `6`. Một `max_value` riêng lẻ chỉ cho biết giá trị phần tử lớn nhất `4`, **không trả lời được** bài toán max-subarray.

### Cây rỗng và tính kết hợp

Đối với định nghĩa “đoạn con không rỗng”, cần biểu diễn riêng trạng thái **đoạn rỗng** thay vì gán mọi trường bằng `0`; nếu làm thế, dãy toàn số âm sẽ trả sai `best=0`. Có thể dùng một cờ `is_empty` làm đơn vị và quy tắc combine xử lý cờ ấy trước.

Nếu metadata như trên được bảo trì đúng ở mỗi nút, các rotation không làm đổi **dãy in-order**, và phép combine kết hợp được, thì ta có thể truy vấn max-subarray trên một đoạn khóa bằng cùng ý tưởng phân rã cây con.

Đây là ví dụ quan trọng: **không chỉ lưu kết quả cuối, mà lưu đủ thông tin để kết hợp hai kết quả cục bộ chính xác**.

## 27. Ví dụ nâng cao: rolling hash và tổng hợp không giao hoán

Giả sử cây giữ một chuỗi ký tự theo thứ tự key, và cần tóm tắt chuỗi bằng **rolling hash**.

Một metadata có thể là `(length,hash)`. Với cơ số `B` và mô-đun `M`, phép nối đoạn `A` trước `C`:

\[
\begin{aligned}
length(AC)&=length(A)+length(C),\\
hash(AC)&=(hash(A)\cdot B^{length(C)}+hash(C))\bmod M.
\end{aligned}
\]

Nếu các lũy thừa `B^k\bmod M` đã sẵn sàng theo độ dài thích hợp, phép combine có thể tốn **`O(1)`** trong mô hình số nguyên từ máy.

**Thứ tự quan trọng:** `hash(A\Vert C)` thường khác `hash(C\Vert A)`. Vì vậy, aggregate tại nút phải tuân theo **cây trái → value nút → cây phải**.

**Đừng nhầm:** hash bằng nhau không chứng minh hai chuỗi bằng nhau vì có thể có **va chạm hash**. Với ứng dụng đòi chính xác tuyệt đối, cần kiểm tra bổ sung hoặc mô hình khác.

### Tại sao không lưu chuỗi đã nối ở mọi nút?

Phép nối chuỗi thông thường có thể phải sao chép toàn bộ số ký tự ở hai vế, nên combine **không `O(1)`** theo độ dài chuỗi. Nếu mọi nút đều lưu bản sao đầy đủ nội dung cây con, bộ nhớ có thể tăng tới `\Theta(n^2)` trên một BST lệch, hoặc `\Theta(n\log n)` trên nhiều cây cân bằng, tùy cách chia sẻ vùng nhớ.

Nếu mục tiêu là `O(\log n)` thời gian cho cập nhật/truy vấn một tóm tắt cố định, cần một representation như hash, ma trận cố định, hoặc cấu trúc chia sẻ chuỗi thích hợp — không chỉ dựa vào tính kết hợp trừu tượng.

## 28. So sánh với mảng tiền tố, Fenwick và segment tree

Không phải lúc nào BST tăng cường cũng là lựa chọn tốt nhất.

| Nhu cầu | Cấu trúc đáng cân nhắc | Đánh đổi |
|---|---|---|
| Dữ liệu tĩnh, hỏi **tổng đoạn theo chỉ số** | Mảng prefix sum | Xây `O(n)`; mỗi tổng đoạn `O(1)` |
| Dữ liệu tĩnh, hỏi min/max đoạn | Sparse table hoặc segment tree | Sparse table có thể trả RMQ `O(1)` sau tiền xử lý phù hợp; cập nhật khó |
| Khóa số nguyên trong miền cố định, cập nhật tổng tần suất/giá trị | Fenwick tree | `O(\log U)` cho point update/prefix sum; `O(U)` bộ nhớ |
| Miền chỉ số cố định, nhiều loại aggregate và cập nhật điểm | Segment tree | `O(\log U)` cho point update/range aggregate |
| Khóa động, rất thưa, cần tìm/thêm/xóa theo khóa | AVL/red-black tree tăng cường | `O(\log n)` với metadata tổng hợp |
| Truy vấn theo khóa hiếm, chủ yếu tìm ID chính xác | Bảng băm + thống kê riêng | Tìm ID nhanh, nhưng range query cần cấu trúc bổ sung |

### 28.1. Mảng tiền tố

Cho dãy value cố định `a[0..n-1]`:

\[
P[0]=0,\qquad
P[i+1]=P[i]+a[i].
\]

Tổng đoạn nửa kín `[l,r)` là:

\[
\boxed{sum_{[l,r)}=P[r]-P[l]}.
\]

Ưu điểm: trả tổng trong `O(1)`. Nhược điểm: nếu sửa một `a[i]`, nhiều giá trị tiền tố sau đó phải thay, thường tốn `O(n)` nếu cập nhật trực tiếp mảng prefix.

### 28.2. Fenwick tree

Fenwick hỗ trợ **tổng tiền tố** và **cập nhật điểm** trong `O(\log U)` trên các vị trí chỉ số. Phù hợp khi tập khóa đã được ánh xạ thành chỉ số nguyên ổn định.

Không được suy ra Fenwick chuẩn tự hỗ trợ min/max đoạn tùy ý bằng **trừ hai cực trị tiền tố**; min/max không có phép nghịch đảo giống cộng.

### 28.3. Segment tree

Segment tree lưu aggregate của những đoạn chỉ số cố định. Nếu phép combine có tính kết hợp và đơn vị, một đoạn `[l,r)` được phân thành các nút đoạn thích hợp để kết hợp trong `O(\log U)`; cập nhật một vị trí cũng `O(\log U)`.

BST tăng cường dùng **thứ tự khóa động** thay vì một miền chỉ số cố định. Nếu khóa mới xuất hiện ở giữa những khóa cũ, BST có thể chèn và cân bằng mà không buộc phải **đánh số lại toàn bộ**.

### 28.4. Nén tọa độ

Nếu biết trước mọi khóa, có thể **sort và nén tọa độ** rồi dùng Fenwick/segment tree. Nhưng nếu trong lúc chạy xuất hiện một khóa mới cần đặt **giữa** hai khóa cũ, ánh xạ index có thể phải được cập nhật hoặc xây lại; một cấu trúc động theo khóa có thể thuận tiện hơn.

## 29. Vấn đề thực tế: tải cập nhật, đồng thời và vòng đời dữ liệu

### 29.1. Có nhiều cập nhật value hay nhiều truy vấn?

Nếu chỉ có một vài thay đổi value nhưng hàng triệu truy vấn tổng/min/max đoạn, metadata rất có ích. Nếu mỗi thay đổi lại khiến phải cập nhật nhiều trường trên đường tới gốc, hãy đo chi phí hằng số thay vì chỉ nhìn `O(\log n)`.

### 29.2. Khóa có thật sự bất biến?

Không nên sửa `node.key` trực tiếp sau khi đã chèn, vì vị trí của nút trong BST đang phản ánh **khóa cũ**. Muốn đổi khóa, thường phải **xóa bản ghi theo khóa cũ, rồi chèn lại với khóa mới** và bảo trì metadata.

Đổi `value` không ảnh hưởng BST-order; đổi `key` có thể phá toàn bộ thứ tự tìm kiếm.

### 29.3. Đọc/ghi đồng thời

Trong lúc một luồng xoay cây, các con trỏ và metadata có thể ở trạng thái **chuyển tiếp**. Một luồng truy vấn không đồng bộ có thể đọc tổ hợp **con trỏ mới + aggregate cũ**, dẫn tới kết quả sai.

Hệ thống đa luồng cần chính sách như khóa đọc–ghi, snapshot bất biến, phiên bản hoặc cơ chế giao dịch tương thích. **Không có lớp Python giảng dạy nào ở đây tự cung cấp thread-safety**.

### 29.4. Cấp phát và cache

Cây nút liên kết thường dùng nhiều con trỏ và metadata hơn mảng liên tiếp; các lần đi theo liên kết có thể gây cache miss. Với tập khóa nhỏ và ít cập nhật, mảng đã sắp hoặc segment tree có thể đơn giản, dễ dự đoán và nhanh hơn.

### 29.5. Số nguyên tràn hoặc NaN

Python dùng số nguyên độ dài linh hoạt; nhiều ngôn ngữ khác có kiểu số nguyên hữu hạn. Nếu `sum` được lưu trong `int32`, tổng có thể tràn dù mỗi value riêng lẻ hợp lệ. Cần chọn kiểu tích lũy đủ rộng hoặc quy tắc tràn rõ ràng.

`NaN` phá tính chất thứ tự so sánh thông thường. Không nên cho phép `NaN` làm khóa BST trừ khi đã định nghĩa một **total order** nhất quán.

## 30. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nhầm `min_key` với `min_value` | Tìm khóa nhỏ nhất thay vì payload nhỏ nhất | Lưu hai khái niệm riêng |
| Dùng `min(None)=0` hoặc `max(None)=0` | Sai với tập toàn dương/toàn âm | Dùng `None` hoặc đơn vị `\pm\infty` phù hợp |
| Quên chính payload của nút khi recalc | Tổng/count thiếu một bản ghi | `left ⊕ single(value) ⊕ right` |
| Cho rằng sum tiền tố luôn tăng | Value âm làm tiền tố giảm | Rẽ cây theo **key**, không theo sum |
| Trừ hai min/max tiền tố | Không tồn tại nghịch đảo cho cực trị | Phân rã cây con hoặc segment tree |
| Duyệt từng nút trong đoạn dù đã có metadata | Mất lợi thế tăng cường | Nhận nguyên cây con khi được bao trọn |
| Bỏ qua điều kiện subtree nằm ngoài đoạn | Duyệt thừa | Dùng `lo_key/hi_key` |
| Giữ min/max cũ sau update/xóa | Cực trị có thể đã biến mất | `recalc` từ con còn lại |
| Sau rotation chỉ cập nhật height | `get(key)` vẫn đúng nhưng range query sai | `recalc` cả height, bounds, aggregate |
| Tính gốc mới trước nút đi xuống khi xoay | Dùng metadata cũ của con | Recalc nút thấp trước |
| Xóa nút hai con nhưng chỉ copy key | Payload gắn nhầm khóa, mất dữ liệu | Chuyển cả record hoặc nguyên successor |
| Chèn khóa trùng thành nhiều node ngoài hợp đồng | BST-order và interval bounds có thể sai | Định nghĩa policy multiset/bucket/khóa ghép |
| Gọi `put` và tưởng rằng cộng dồn | Value bị ghi đè | Dùng `add_value` hoặc API rõ nghĩa |
| Nói mọi range query có `O(\log n)` | Chỉ đúng với đoạn khóa liên tục và aggregate gộp nhanh | Phân biệt lọc tùy ý/liệt kê kết quả |
| Chỉ có metadata mà không cân bằng BST | Cây lệch vẫn `O(n)` chiều cao | AVL/red-black/treap với bảo đảm phù hợp |
| Kết hợp dữ liệu không giao hoán sai thứ tự | Ví dụ hash/nối chuỗi sai | Giữ `left→node→right` |
| Lưu danh sách đầy đủ trong mỗi node | Tốn lớn bộ nhớ, combine không `O(1)` | Chọn summary có kích thước cố định |
| Dùng tổng/min/max để suy median chính xác | Bộ thông tin không đủ | Lưu order-statistics hoặc tần suất |
| Dùng `hi+1` với khóa bất kỳ | Có thể vô nghĩa hoặc tràn | Dùng `prefix_le(hi)` |
| Gọi kiểm tra toàn cây sau mỗi thao tác production | Thêm `O(n)` chi phí | Dùng khi test/debug |
| Đọc cây đang bị thay đổi đồng thời không khóa | Có thể thấy con trỏ và metadata lệch phiên bản | Đồng bộ hoặc snapshot |

## 31. Bài tập tự kiểm tra

**Bài 1.** Với `(key,value)` lần lượt là `(10,4),(20,-3),(30,7),(40,0),(50,8),(60,-6),(70,2)`, tính count, sum, min và max value của toàn bộ cây.

**Bài 2.** Vì sao min/max value của cây con không nhất thiết trùng với value của nút có key nhỏ nhất/lớn nhất?

**Bài 3.** Viết bất biến `sum(v)` và `count(v)` với mỗi nút chứa đúng một bản ghi.

**Bài 4.** Nếu cây con rỗng, tổng và min/max nên được biểu diễn thế nào để không sai với dữ liệu âm/dương?

**Bài 5.** Với value `[4,-3,7,0,8,-6,2]`, tính `prefix_sum_lt(25)` và `prefix_sum_le(65)`. Suy ra tổng đoạn khóa đóng `[25,65]`.

**Bài 6.** Tại nút có khóa `40`, `prefix_sum_lt(65)` phải cộng dữ liệu nào khi `65>40`? Vì sao có thể bỏ qua việc duyệt từng nút của cây trái?

**Bài 7.** Đối với khoảng nửa kín `[lo,hi)`, viết công thức tổng đoạn từ hai phép tiền tố.

**Bài 8.** Vì sao không thể tính min của đoạn `[lo,hi]` bằng cách trừ hai giá trị min tiền tố?

**Bài 9.** Một cây con có `lo_key=30` và `hi_key=60`. Với truy vấn `[25,65]` có thể dùng nguyên aggregate không? Với `[35,55]` thì sao?

**Bài 10.** Trong ví dụ phần 4, các khóa thuộc `[25,65]` là gì? Giá trị count, sum, min, max?

**Bài 11.** Nếu thay value ở khóa `50` từ `8` thành `-10`, tổng/min/max toàn cây đổi thế nào? Count có đổi không?

**Bài 12.** Tại sao khi cập nhật value hiện đang là minimum duy nhất, không thể chỉ áp một hiệu số vào trường min?

**Bài 13.** Khi insert một khóa mới, những nút nào cần recalc? Tại sao một cây cân bằng chỉ tốn `O(\log n)` công việc?

**Bài 14.** Cho sơ đồ xoay trái `x(A,y(B,C))\to y(x(A,B),C)`. Viết công thức aggregate của `x` và `y` sau xoay.

**Bài 15.** Sau xoay trái, tại sao tính `recalc(y)` trước `recalc(x)` có thể sai?

**Bài 16.** Xóa nút `(40,0)` bằng inorder successor `(50,8)`. Vì sao copy `key=50` nhưng giữ `value=0` là sai?

**Bài 17.** Định nghĩa phép combine và phần tử đơn vị cho `(count,sum,min,max)`. Phép combine có tính kết hợp không?

**Bài 18.** Phép nối chuỗi có tính kết hợp nhưng không giao hoán. Tại sao cần tổng hợp theo thứ tự `left→node→right`, và lưu toàn bộ chuỗi trong mỗi node có nhất thiết hiệu quả không?

**Bài 19.** Độ phức tạp của `get`, `put`, `delete`, `prefix_sum`, `range_stats` trên BST lệch so với AVL cân bằng là gì?

**Bài 20.** Nếu cây chỉ chứa các value âm `[-9,-4]`, aggregate rỗng phải có minimum/maximum như thế nào để không làm sai kết quả?

**Bài 21.** Một cây có ba phần tử cùng key và cùng value `-2`. Nếu gom thành một nút `count=3`, đóng góp của nút cho count/sum/min/max là gì?

**Bài 22.** Tại sao `count,sum,min,max` chưa đủ để suy ra **median chính xác** của hợp hai tập?

**Bài 23.** Đối với tổng lớn nhất của đoạn con liên tiếp theo key, vì sao cần lưu `best_prefix` và `best_suffix` bên cạnh `best` và `total`?

**Bài 24.** Dữ liệu có khóa nguyên trong miền nhỏ cố định, cập nhật nhiều và chủ yếu hỏi tổng tiền tố. Vì sao Fenwick có thể phù hợp hơn một AVL nút liên kết?

**Bài 25.** Nếu biết trước mọi khóa rồi nén tọa độ để dùng segment tree, chuyện gì xảy ra nếu có khóa mới chen vào giữa hai khóa đã nén?

**Bài 26.** Giải thích vì sao `range_stats(lo,hi)` có thể `O(\log n)` trên AVL nhưng **liệt kê** mọi bản ghi trong khoảng có thể cần `\Omega(k)` công việc với `k` kết quả.

**Bài 27.** Nếu hàm `check_invariants` phát hiện height và BST-order đúng nhưng tổng subtree sai sau một phép xoay, cần kiểm tra điểm nào trước tiên?

**Bài 28.** Đề xuất các ca biên để kiểm tra một AVL tăng cường lưu sum/min/max/count.

### Đáp án và giải thích

1. `count=7, sum=12, min=-6, max=8`.
2. BST sắp **theo key**, không theo value. Ví dụ key `60` có value `-6` là min dù key nhỏ nhất `10` có value `4`.
3. `sum(v)=sum(left)+v.value+sum(right)`, `count(v)=count(left)+1+count(right)`; với cây rỗng cả hai bằng `0`.
4. Sum rỗng `0`; min/max rỗng dùng `None` hay đơn vị mở rộng `+\infty`/`-\infty` phù hợp, không dùng số `0` cho cực trị.
5. `prefix_lt(25)=4-3=1`; `prefix_le(65)=4-3+7+0+8-6=10`; tổng đoạn `[25,65]=10-1=9`.
6. Cộng `sum(left_subtree)+value(40)` vì mọi key cây trái đều nhỏ hơn `40<65`, rồi đi phải để xét những khóa lớn hơn `40`. Metadata cho phép cộng cả cây trái `O(1)`.
7. `sum_[lo,hi)=prefix_lt(hi)-prefix_lt(lo)`.
8. Min/max không có phép trừ/nghịch đảo của phép gộp: min tiền tố không cho biết min của phần còn lại nếu loại các phần tử đầu.
9. `[25,65]` chứa toàn bộ miền khóa `[30,60]`, nên dùng nguyên metadata. `[35,55]` chỉ giao một phần, phải đi sâu hoặc cắt thành các khối phù hợp.
10. Các key `30,40,50,60` mang value `7,0,8,-6`; `count=4,sum=9,min=-6,max=8`.
11. `sum=12-18=-6`, `min=-10`, `max=7`; `count` vẫn `7` vì chỉ đổi value.
12. Nếu minimum duy nhất bị thay bằng value lớn hơn, min mới có thể đến từ một nút khác. Không có phép nghịch đảo của min; cần tính lại từ value hiện tại và extrema các con.
13. Nút mới và các tổ tiên trên đường tìm từ chỗ chèn về gốc; nếu có rotation, các nút đổi liên kết cũng recalc. AVL có chiều cao `O(\log n)` nên số nút liên quan `O(\log n)`.
14. `agg(x)=agg(A)⊕single(x.value)⊕agg(B)`; `agg(y)=agg(x)⊕single(y.value)⊕agg(C)` sau xoay.
15. Vì `agg(y)` phụ thuộc vào `agg(x)` mới; nếu dùng `agg(x)` cũ, dữ liệu `C` hoặc `B` có thể bị tính sai/lặp trong kết quả.
16. Khóa `50` phải gắn với payload `8`. Giữ value `0` sẽ thay nội dung bản ghi, làm tổng/min/max sai dù BST-order còn đúng.
17. `combine` cộng count/sum và lấy min/min, max/max trên những cực trị có mặt. Đơn vị `E=(0,0,None,None)`. Có tính kết hợp vì các phép thành phần đều kết hợp được.
18. Vì `"ab"+"cd"` khác `"cd"+"ab"`, phải giữ thứ tự in-order của khóa. Nếu mỗi node lưu chuỗi đã nối đầy đủ, combine có thể `O(length)` và tốn bộ nhớ; nên dùng summary cố định hoặc cấu trúc chuỗi chia sẻ thích hợp.
19. Với BST không cân bằng, các truy vấn theo đường tìm có `O(h)`, xấu nhất `O(n)`. Với AVL, `h=O(\log n)` nên những thao tác này `O(\log n)`; `stats()` toàn cây là `O(1)` khi metadata đã đúng.
20. Minimum/maximum của aggregate rỗng phải **không tham gia quyết định cực trị**, ví dụ `None`. Tập `[-9,-4]` phải có min `-9` và max `-4`, không phải max `0`.
21. `count=3`; `sum=3\times(-2)=-6`; `min=-2` và `max=-2`.
22. Hai tập có cùng count/sum/min/max có thể có phân bố giá trị giữa khác nhau, nên median của hợp có thể khác; thông tin thứ tự/tần suất bổ sung là cần thiết.
23. Đoạn con tốt nhất có thể **băng qua ranh giới** của hai cây con; cần `suffix(A)+prefix(B)` để xét trường hợp ấy, ngoài `best(A)` và `best(B)`.
24. Fenwick lưu mảng có locality tốt, hỗ trợ update điểm và sum tiền tố `O(\log U)` với một số thao tác số học đơn giản; không cần cấp phát một nút/con trỏ cho mỗi khóa nếu miền nhỏ.
25. Khóa mới có thể cần một index **nằm giữa** hai chỉ số nén cũ, làm thứ tự mapping không còn phù hợp. Cần cập nhật/nén lại hoặc dùng cấu trúc động.
26. Aggregate dùng nguyên **cây con được bao trọn** nên chỉ xử lý `O(\log n)` khối biên trên AVL; nhưng muốn xuất `k` bản ghi phải tạo ít nhất `k` kết quả, tốn `\Omega(k)`.
27. Kiểm tra thứ tự `recalc` sau rotation (nút đi xuống trước, gốc mới sau), công thức `combine(left,single,right)`, và việc cập nhật đúng con trỏ khi xoay.
28. Các ca: cây rỗng; một khóa; value âm/dương/0; đoạn không giao; `lo>hi`; update value đang là min/max duy nhất; insert tạo LL/LR/RR/RL; delete lá, một con, hai con; xóa/put khóa không tồn tại; tổng lớn/tràn kiểu; so với dict tham chiếu sau nhiều thao tác.

## 32. Ghi nhớ

**Cây tìm kiếm tăng cường** lưu **metadata của toàn bộ cây con** để trả lời nhanh những truy vấn như tổng, min/max, số lượng hoặc một dữ liệu tổng hợp phức tạp. Với mỗi nút, công thức then chốt là **`aggregate(node)=combine(aggregate(left),single(value),aggregate(right))`** theo đúng thứ tự duyệt giữa; phép combine cần **có tính kết hợp**, có **phần tử đơn vị** và đủ rẻ để cập nhật. Sum cho phép tính **tổng đoạn bằng hiệu hai tiền tố**, còn min/max **không thể trừ tiền tố** mà phải kết hợp những cây con nằm trong đoạn khóa. Trên cây cân bằng như **AVL**, `put/delete/prefix/range aggregate` thường mất **`O(\log n)`**, còn đọc aggregate toàn cây chỉ **`O(1)`**, miễn là metadata được cập nhật chính xác khi thay value, thêm/xóa nút và sau **mọi rotation**. Cần phân biệt **key tìm kiếm** với **value được tổng hợp**, định nghĩa đúng hành vi khóa trùng và khoảng rỗng, đồng thời chọn cây tăng cường hay Fenwick/segment tree/mảng tiền tố theo miền khóa và tần suất thao tác thực tế.
