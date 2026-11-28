# Chọn thông tin phụ dựa trên phép truy vấn cần hỗ trợ

## 1. Vấn đề thiết kế: không phải cây nào cũng nên lưu cùng một metadata

Trong môn **Cấu trúc dữ liệu**, một cây tìm kiếm thường lưu khóa, các liên kết tới cây con và đôi khi thêm chiều cao hoặc màu để tự cân bằng. Nhưng khi ứng dụng hỏi những câu phức tạp hơn “khóa `x` có tồn tại không?”, cấu trúc này có thể phải duyệt nhiều nút.

Ví dụ, một tập bản ghi có thứ tự cần trả lời:

- Có **bao nhiêu** bản ghi có khóa nhỏ hơn `x`?
- Bản ghi có khóa **nhỏ thứ `k`** là gì?
- **Tổng trọng số** của các bản ghi có khóa thuộc `[L,R]` là bao nhiêu?
- Trong danh sách các khoảng thời gian, **có khoảng nào giao** với `[L,R]`?
- Trong một dãy số, **tổng đoạn con liên tiếp lớn nhất** bằng bao nhiêu?
- Với một dãy dấu ngoặc, **mọi tiền tố có cân bằng** hay không?

Một cách đơn giản là sau mỗi truy vấn, duyệt các nút liên quan và tính kết quả. Nếu cây có `n` nút, nhiều truy vấn có thể phải đọc tới `n` nút, dù cây đã cân bằng.

**Cây tăng cường (augmented tree)** lưu thêm các thông tin **tóm tắt cây con** tại từng nút. Thông tin này được chọn **từ loại truy vấn và phép cập nhật cần hỗ trợ**, không phải thêm các trường tùy ý cho đầy đủ.

> Nguyên tắc thiết kế: từ câu hỏi cần trả lời, xác định *thông tin đủ* để bỏ qua một cây con hoặc gộp đáp án của nhiều cây con; sau đó chứng minh thông tin ấy có thể **duy trì sau mỗi lần thay đổi cây** với chi phí chấp nhận được.

Bài này tập trung vào **phương pháp lựa chọn metadata**. Ta sẽ thiết kế các bộ trường khác nhau cho thống kê thứ tự, tổng, truy vấn khoảng, dãy ngoặc và tổng đoạn con lớn nhất; xây một ví dụ Python AVL vừa lưu `size` vừa lưu `subtree_sum`; rồi phân tích những tình huống mà một tóm tắt hằng kích thước **không đủ**.

## 2. Ba lớp câu hỏi phải tách biệt

Trước khi chọn một trường phụ, cần trả lời ba câu hỏi độc lập.

### 2.1. Tập dữ liệu có tổ chức theo thứ tự nào?

Một BST sắp **theo khóa**:

```text
mọi khóa ở trái < khóa tại nút < mọi khóa ở phải
```

Một implicit treap sắp **theo vị trí của phần tử trong dãy**:

```text
inorder(tree) = dãy đang quản lý
```

Một interval tree có thể sắp theo **đầu trái của khoảng**, còn `maxHigh` là tóm tắt **đầu phải**.

Những thứ tự ấy khác nhau. Chẳng hạn, lưu `subtree_sum` trong BST theo khóa **không có nghĩa** nút nào đứng gần nhau trên màn hình; nó chỉ cho phép tổng hợp theo thứ tự khóa.

### 2.2. Truy vấn cần câu trả lời kiểu nào?

Ví dụ:

| Truy vấn | Kết quả mong muốn | Thông tin có thể cần |
|---|---|---|
| Độ dài dãy | Một số lượng | `size` |
| Phần tử nhỏ thứ `k` | Một khóa/giá trị | `size(left)` để định hướng |
| Số khóa dưới `x` | Một số lượng | `size` cộng thứ tự BST |
| Tổng trọng số trong một cây con | Một con số | `subtree_sum` |
| Khoảng bất kỳ giao `Q` | Một bản ghi hoặc không có | `maxHigh` cộng thứ tự theo `low` |
| Giá trị nhỏ nhất trong đoạn | Một giá trị | `subtree_min` hoặc cấu trúc truy vấn đoạn |
| Tổng đoạn con liên tiếp lớn nhất | Một con số | `sum, best_prefix, best_suffix, best_subarray` |
| Kiểm tra dãy ngoặc đúng | Boolean | `sum` và `min_prefix` |
| Trung vị động của tập khóa | Một khóa | `size` và cây tìm kiếm cân bằng |
| Giá trị phân biệt trong một khoảng | Số lượng khác nhau | Cần xử lý trùng và phạm vi; `size` đơn thuần không đủ |

### 2.3. Cập nhật sẽ xảy ra theo cách nào?

Cùng một truy vấn có thể cần thiết kế khác nhau tùy cập nhật:

- Chèn và xóa **một khóa**.
- Thay đổi **trọng số** của khóa đã tồn tại.
- Nối hai dãy, cắt một đoạn, đảo một đoạn.
- Cộng một hằng số vào **mọi phần tử của một đoạn**.
- Xóa một khoảng và thêm khoảng khác.
- Thay đổi khóa làm **mất thứ tự BST**.
- Truy cập nhiều phiên bản bất biến hoặc đồng thời.

Một metadata **trả lời nhanh** nhưng mỗi lần sửa phải **tính lại toàn bộ cây** có thể không phù hợp. Muốn một thiết kế hiệu quả, phải đánh giá **cả truy vấn lẫn cập nhật**.

## 3. Quy trình chọn metadata dựa trên truy vấn

Có thể dùng quy trình bảy bước sau:

1. **Định nghĩa câu hỏi chính xác.** Chỉ số từ `0` hay `1`? Đoạn đóng hay nửa mở? Đếm khóa phân biệt hay cả bản sao? Kết quả khi tập rỗng?
2. **Chọn cây nền và thứ tự.** BST theo khóa, cây theo vị trí, interval tree hay cấu trúc khác? Có cần chiều cao logarit?
3. **Phân rã một cây con.** Kết quả của vùng `left + node + right` có thể biểu diễn bằng gì?
4. **Chọn trạng thái tóm tắt.** Lưu những trường **đủ để gộp lại** và để truy vấn cắt nhánh; tránh lưu quá ít hoặc quá nhiều.
5. **Viết công thức `pull`.** Tính metadata của cha từ giá trị nút và metadata của hai con trong `O(1)` nếu mục tiêu là cập nhật đường đi logarit.
6. **Kiểm tra mọi thao tác sửa.** Chèn, xóa, thay giá trị, xoay đơn/kép, split/merge, lazy propagation: trường nào thay đổi và khi nào phải tính lại?
7. **Chứng minh và kiểm thử.** Kiểm tra bất biến quy nạp, chặn thời gian/bộ nhớ, đối chiếu với thuật toán quét đơn giản.

Đây không phải một danh sách “metadata chuẩn” cho mọi bài. Với hai bài toán khác nhau, đáp án có thể là **hai cấu trúc hoặc hai bộ trường hoàn toàn khác nhau**.

### Ví dụ nhỏ: từ câu hỏi tới trường phụ

**Yêu cầu:** tìm phần tử thứ `k` trong cây có khóa phân biệt.

- Cây nền: BST có thứ tự.
- Dữ liệu cần bỏ qua: **số phần tử** bên trái.
- Trường phụ: `size`.
- Công thức gộp: `size=1+size(left)+size(right)`.
- Quy tắc tìm: so `k` với `size(left)+1`.
- Sau xoay: tính lại `size` ở các nút bị đổi con.

**Yêu cầu:** tính tổng trọng số của một cây con.

- Cây nền: có thể là BST hoặc cây nhị phân theo vị trí.
- Dữ liệu cần gộp: **tổng** của hai cây con cộng trọng số tại nút.
- Trường phụ: `subtree_sum`.
- Công thức gộp: `sum=sum(left)+weight+sum(right)`.

**Yêu cầu:** tìm một khoảng giao truy vấn.

- Cây nền: BST theo đầu trái của khoảng.
- Dữ liệu cần để loại nhánh: đầu phải **lớn nhất** của toàn bộ cây con.
- Trường phụ: `maxHigh`.
- Công thức gộp: `maxHigh=max(high(node),maxHigh(left),maxHigh(right))`.

Ba bài toán đều là “cây tăng cường”, nhưng **không thể thay thế tùy ý `size`, `sum` và `maxHigh` cho nhau**.

## 4. Bất biến tổng quát: metadata của một cây con

Giả sử một cây nhị phân có nút `u`, hai cây con `L,R`, dữ liệu riêng tại nút là `v(u)`. Ta muốn một đại lượng tổng hợp:

\[
M(u)=F(M(L),v(u),M(R)).
\]

Với cây rỗng có trạng thái trung hòa:

\[
M(\varnothing)=e.
\]

Nếu phép `F` tính được trong `O(1)`, có thể xây một hàm **`pull(u)`** tính lại `M(u)` từ hai con.

```text
PULL(u):
    require metadata(u.left) đúng
    require metadata(u.right) đúng
    u.metadata = combine(
        metadata(u.left),
        local_summary(u),
        metadata(u.right)
    )
```

### 4.1. Không có metadata nào đúng nếu chỉ cập nhật ở gốc

Ví dụ một BST:

```text
                 20
                /  \
              10    30
             /  \   / \
            5   15 25 35
```

Nếu sửa dữ liệu ở nút `5`, những nút có cây con chứa `5` là:

```text
5 → 10 → 20
```

Chỉ cập nhật trường của gốc `20` **không đủ**. Trường ở `10` vẫn sai, mà truy vấn về sau có thể đọc trực tiếp metadata của cây con gốc tại `10`.

Do đó chèn, xóa, sửa giá trị thường phải tính lại **từ dưới lên dọc đường tổ tiên**.

### 4.2. Không phải mọi hàm gộp đều có chi phí hằng

Ví dụ:

- `size`: một phép cộng hữu hạn → `O(1)`.
- `sum`: hai phép cộng → `O(1)` trong mô hình số học kích thước giới hạn.
- `maxHigh`: một số phép so sánh → `O(1)`.
- “Danh sách mọi giá trị phân biệt trong cây con”: nếu lưu danh sách/tập thực, mỗi lần gộp có thể phải xét **nhiều phần tử** và tốn thêm bộ nhớ.

Câu “metadata tính được từ hai con” **chưa đủ** để suy ra cập nhật `O(\log n)`. Còn cần **chi phí gộp** và **chi phí sửa cây**.

## 5. Phép gộp kết hợp (associative): nền tảng của nhiều metadata

### 5.1. Một tóm tắt của dãy có thể được gộp ra sao?

Với một dãy `S` và hai phần liên tiếp `A,B`:

\[
S=A\mathbin{+\!\!+}B.
\]

Giả sử `summary(A)` có kích thước cố định. Nếu tồn tại phép gộp `\oplus` sao cho:

\[
summary(A+B)=summary(A)\oplus summary(B),
\]

và có trạng thái rỗng `e`, ta có thể xây tóm tắt cho cả cây bằng cách gộp:

\[
\boxed{
M(u)=M(u.left)\oplus local(u)\oplus M(u.right).
}
\]

Nếu `\oplus` **kết hợp**:

\[
(a\oplus b)\oplus c=a\oplus(b\oplus c),
\]

thì việc đổi cách đặt ngoặc khi hình dạng cây thay đổi không làm kết quả tổng hợp sai.

Một bộ gồm **tập giá trị tóm tắt**, **phép gộp kết hợp** và **phần tử trung hòa** được gọi là một **monoid**. Nhiều cây tổng hợp đoạn thực chất lưu một monoid tại mỗi nút.

### 5.2. Ví dụ các monoid đơn giản

| Truy vấn | `summary` | Gộp `a⊕b` | Trạng thái rỗng `e` |
|---|---|---|---|
| Đếm số phần tử | `size` | `a+b` | `0` |
| Tổng giá trị | `sum` | `a+b` | `0` |
| Tích giá trị | `product` | `a×b` | `1` |
| Giá trị nhỏ nhất | `minimum` | `min(a,b)` | `+\infty` |
| Giá trị lớn nhất | `maximum` | `max(a,b)` | `-\infty` |
| Logic “có phần tử thỏa `P`?” | Boolean | `a OR b` | `False` |
| Logic “mọi phần tử thỏa `P`?” | Boolean | `a AND b` | `True` |
| XOR các giá trị bit | `xor` | `a XOR b` | `0` |

**Lưu ý giá trị rỗng:** `+\infty` và `-\infty` trong bảng là ký hiệu toán học. Cài đặt với số nguyên có miền hữu hạn hoặc kiểu tùy chỉnh cần một biểu diễn sentinel phù hợp, không tự giả định luôn có vô cực đúng kiểu.

### 5.3. Gộp hai thống kê cùng lúc

Nếu ứng dụng cần cả số lượng và tổng trọng số, lưu:

\[
M(S)=(count(S),sum(S)).
\]

Định nghĩa:

\[
(c_1,s_1)\oplus(c_2,s_2)
=
(c_1+c_2,\ s_1+s_2),
\]

với:

\[
e=(0,0).
\]

Trạng thái tại một nút có trọng số `w` là:

\[
local(u)=(1,w(u)).
\]

Bộ `(size,sum)` này là **tích trực tiếp** của hai tóm tắt; vẫn có phép gộp `O(1)` và trạng thái rỗng rõ ràng.

### 5.4. Kết hợp không đồng nghĩa giao hoán

**Kết hợp** có nghĩa là cách đặt ngoặc không quan trọng. **Giao hoán** có nghĩa là có thể đổi thứ tự các toán hạng:

\[
a\oplus b=b\oplus a.
\]

Một số thống kê dãy **phụ thuộc thứ tự**. Ví dụ, nối chuỗi:

```text
"ab" + "cd" = "abcd"
"cd" + "ab" = "cdab"
```

Phép nối **kết hợp** nhưng **không giao hoán**. Khi gộp metadata của cây theo thứ tự inorder, phải dùng:

```text
summary(left) ⊕ summary(node) ⊕ summary(right)
```

Không được tự đảo thành `right ⊕ node ⊕ left` chỉ vì hai phép cộng số trong ví dụ `sum` vẫn cho kết quả giống nhau.

### 5.5. Đổi cấu trúc và đảo thứ tự là hai việc khác nhau

Một **phép xoay BST** giữ nguyên thứ tự inorder, nên một phép gộp kết hợp theo inorder vẫn trả kết quả cho cùng dãy. Tuy nhiên, metadata ở **những nút cụ thể** có thể thay đổi do tập con mà chúng đại diện thay đổi.

Một thao tác **đảo đoạn** thực sự làm đổi thứ tự inorder. Với các tóm tắt phụ thuộc thứ tự (hash, dãy ngoặc, tổng tiền tố), phải cập nhật metadata thích hợp; không thể chỉ giữ nguyên vì tổng phần tử hoặc min/max không đổi.

## 6. Ví dụ xuyên suốt: cùng một BST, hai truy vấn khác nhau

Ta có một BST với **khóa nguyên phân biệt** và **trọng số số nguyên** tại mỗi khóa:

```text
                         key=20, weight=7
                        /                 \
                key=10,w=5             key=30,w=-2
                 /      \               /       \
             key=5,w=4  key=15,w=3   key=25,w=6  key=35,w=1
```

Dữ liệu theo thứ tự khóa:

| Khóa | 5 | 10 | 15 | 20 | 25 | 30 | 35 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| Trọng số | 4 | 5 | 3 | 7 | 6 | -2 | 1 |

Cần hỗ trợ:

1. Tìm **khóa nhỏ thứ `k`**.
2. Đếm số khóa **nhỏ hơn `x`**.
3. Tính **tổng trọng số** của khóa thuộc `[L,R]`.
4. Sửa trọng số, thêm/xóa khóa mà vẫn duy trì những truy vấn trên.

### 6.1. Chọn metadata

Lưu ở mỗi nút:

- `size`: **số khóa/nút** trong cây con.
- `subtree_sum`: **tổng trọng số** của các nút trong cây con.

Hai bất biến:

\[
\boxed{size(u)=1+size(u.left)+size(u.right)}
\]

\[
\boxed{
subtreeSum(u)=
subtreeSum(u.left)+weight(u)+subtreeSum(u.right).
}
\]

Với cây rỗng:

\[
size(\varnothing)=0,\qquad subtreeSum(\varnothing)=0.
\]

Ta cũng lưu `height` để dùng **AVL tree** làm cây nền tự cân bằng. `height` phục vụ cân bằng, không phải truy vấn nghiệp vụ.

### 6.2. Tính từ lá lên gốc

Ở các nút lá:

```text
5:  size=1, sum=4
15: size=1, sum=3
25: size=1, sum=6
35: size=1, sum=1
```

Tại nút `10`:

\[
size(10)=1+1+1=3,
\]

\[
sum(10)=4+5+3=12.
\]

Tại nút `30`:

\[
size(30)=1+1+1=3,
\]

\[
sum(30)=6+(-2)+1=5.
\]

Tại gốc `20`:

\[
size(20)=3+1+3=7,
\]

\[
sum(20)=12+7+5=24.
\]

Bảng tóm tắt:

| Khóa nút | `weight` | `size(left)` | `size(right)` | `size` | `subtree_sum` |
|---:|---:|---:|---:|---:|---:|
| 5 | 4 | 0 | 0 | 1 | 4 |
| 10 | 5 | 1 | 1 | 3 | 12 |
| 15 | 3 | 0 | 0 | 1 | 3 |
| 20 | 7 | 3 | 3 | 7 | 24 |
| 25 | 6 | 0 | 0 | 1 | 6 |
| 30 | -2 | 1 | 1 | 3 | 5 |
| 35 | 1 | 0 | 0 | 1 | 1 |

### 6.3. Một lần cập nhật ảnh hưởng những nút nào?

Nếu đổi trọng số khóa `15` từ `3` thành `10`:

- `sum(15)` thay từ `3` thành `10`.
- `sum(10)` thay từ `12` thành `19`.
- `sum(20)` thay từ `24` thành `31`.
- Tất cả `size` **không đổi** vì số nút không đổi.
- Cây bên phải nút `20` không thay đổi.

Không cần duyệt toàn bộ bảy nút, chỉ cập nhật **đường từ nút vừa sửa lên gốc**.

## 7. Query 1 — chọn khóa nhỏ thứ `k` bằng `size`

### 7.1. Quy ước

Hàm `select(k)` dùng thứ hạng từ **`1`**:

```text
Sorted keys: 5, 10, 15, 20, 25, 30, 35
Rank:        1   2   3   4   5   6   7
```

Với nút `u`, gọi:

\[
L=size(u.left).
\]

- Nếu `k≤L`: đi trái, giữ `k`.
- Nếu `k=L+1`: trả `key(u)`.
- Nếu `k>L+1`: đi phải với `k'=k-L-1`.

Mã giả:

```text
SELECT(root, k):
    require 1 <= k <= SIZE(root)

    u = root
    while u != None:
        left_count = SIZE(u.left)

        if k <= left_count:
            u = u.left
        else if k == left_count + 1:
            return u.key
        else:
            k -= left_count + 1
            u = u.right
```

### 7.2. Truy vết

Tìm khóa nhỏ thứ `5`:

- Tại `20`, `size(left)=3`, nên `5>4`: đi phải với `k'=5-4=1`.
- Tại `30`, `size(left)=1`, nên `k'=1≤1`: đi trái tới `25`.
- Tại `25`, `size(left)=0`, `k'=1`: trả **`25`**.

Truy vấn chỉ đi một **đường** trong cây, thời gian `O(h+1)` với `h` là chiều cao cây.

### 7.3. Một lỗi lựa chọn metadata phổ biến

Nếu chỉ lưu `sum` mà **không lưu `size`**, không thể suy ra bên trái có bao nhiêu khóa:

```text
Tổng trọng số bên trái = 12
```

có thể đến từ ba khóa `4,5,3` hoặc nhiều cách phân bố số lượng khác. **Tổng không thay thế số lượng**. Do đó truy vấn theo thứ hạng cần `size`, ngay cả khi ứng dụng đã lưu `subtree_sum`.

## 8. Query 2 — rank của khóa bằng `size` cộng thứ tự BST

### 8.1. Tránh mơ hồ về “rank”

Ta định nghĩa:

\[
\boxed{rankLT(x)=\#\{k\in keys:k<x\}.}
\]

Đây là **số khóa nhỏ hơn `x`**, không phải vị trí 1-based của bản ghi có khóa `x`.

Với các khóa ví dụ:

```text
rankLT(20) = 3        # 5,10,15
rankLT(22) = 4        # 5,10,15,20
rankLT(5)  = 0
rankLT(99) = 7
```

`x` không cần hiện diện trong cây.

### 8.2. Quy tắc đi xuống

Tại nút `u`:

- Nếu `x≤key(u)`, nút hiện tại và cây phải đều **không nhỏ hơn `x`**; chỉ đi trái.
- Nếu `x>key(u)`, toàn bộ cây trái và nút hiện tại đều **nhỏ hơn `x`**; cộng `size(left)+1`, đi phải.

```text
RANK-LT(root, x):
    result = 0
    u = root

    while u != None:
        if x <= u.key:
            u = u.left
        else:
            result += SIZE(u.left) + 1
            u = u.right

    return result
```

Dùng `size` để cộng cả một cây con thay vì đếm lại từng nút.

### 8.3. Thứ hạng khi có khóa trùng

Cài đặt mẫu của bài chọn **khóa phân biệt**. Nếu muốn hỗ trợ đa tập, cần quy ước:

- Mỗi nút mang `count(u)≥1` lần xuất hiện; hoặc
- Mỗi bản ghi có khóa ghép `(value,id)` duy nhất.

Với phương án `count`, cập nhật công thức:

\[
size(u)=size(left)+count(u)+size(right).
\]

Và ở nhánh `x>key(u)`, cộng:

\[
size(left)+count(u).
\]

Nếu hệ thống cần **rank theo số lần xuất hiện**, lưu `size` theo bội số; nếu cần **rank theo khóa phân biệt**, lưu thống kê khác hoặc dùng một nút cho mỗi khóa phân biệt. **Một tên trường không thể mang hai định nghĩa trái ngược.**

## 9. Query 3 — tổng trọng số theo khoảng khóa

### 9.1. Một tổng cây con chưa đủ để định hướng

Trường `subtree_sum` trả ngay tổng của **toàn cây con**, nhưng truy vấn:

```text
Tổng weight của những khóa trong [10,30]
```

chỉ lấy một phần của cây. Để không duyệt mọi nút, ta cần kết hợp:

1. Thứ tự BST theo `key`.
2. Tổng cây con có sẵn.
3. **Hàm tổng tiền tố theo khóa**.

### 9.2. Tổng của mọi khóa nhỏ hơn `x`

Định nghĩa:

\[
\boxed{
prefixSumLT(x)=\sum_{\text{key}<x}weight(key).
}
\]

Tại nút `u`:

- Nếu `x≤key(u)`, chỉ có cây trái còn khả năng chứa khóa nhỏ hơn `x`; đi trái, chưa cộng.
- Nếu `x>key(u)`, **toàn bộ** cây trái và nút hiện tại đều thỏa; cộng `sum(left)+weight(u)`, rồi đi phải.

Mã giả:

```text
PREFIX-SUM-LT(root, x):
    result = 0
    u = root

    while u != None:
        if x <= u.key:
            u = u.left
        else:
            result += SUM(u.left) + u.weight
            u = u.right

    return result
```

Với ví dụ:

\[
prefixSumLT(25)=4+5+3+7=19.
\]

Lưu ý tổng có thể **âm** nếu trọng số âm; thuật toán vẫn đúng vì nó **gộp theo thứ tự khóa**, không dùng tính đơn điệu của tổng.

### 9.3. Tổng của mọi khóa nhỏ hơn hoặc bằng `x`

Định nghĩa:

\[
\boxed{
prefixSumLE(x)=\sum_{\text{key}\le x}weight(key).
}
\]

Chỉ đổi điều kiện rẽ nhánh:

- Nếu `x<key(u)`: đi trái.
- Ngược lại: cộng `sum(left)+weight(u)`, rồi đi phải.

### 9.4. Tổng đoạn đóng `[L,R]`

Với `L≤R`:

\[
\boxed{
rangeSum(L,R)=prefixSumLE(R)-prefixSumLT(L).
}
\]

Trên cây mẫu, các khóa trong `[10,30]` là `10,15,20,25,30`, tổng:

\[
5+3+7+6-2=19.
\]

Kiểm tra bằng tiền tố:

\[
prefixSumLE(30)=23,
\]

\[
prefixSumLT(10)=4,
\]

\[
rangeSum(10,30)=23-4=19.
\]

**Trường hợp đoạn rỗng:** nếu `L>R`, API có thể trả `0`. Cần công bố quy tắc này để không vô tình lấy hiệu hai tiền tố theo đầu mút ngược.

### 9.5. Vì sao `sum` không thay `size` và ngược lại?

- `sum` gộp **trọng số**, có thể âm và không phản ánh số lượng.
- `size` đếm **số nút hoặc số lần xuất hiện**, không phản ánh trọng số.
- Nếu cần cả thứ hạng và tổng trọng số, lưu **cả hai** là quyết định tự nhiên.

Chi phí metadata thêm mỗi nút là **hằng số trường**, nhưng mỗi đường cập nhật phải làm thêm một số phép cộng.

## 10. Query 4 — tìm khoảng giao cần `maxHigh`, không phải `size`

### 10.1. Cây lưu các khoảng đóng

Một bản ghi khoảng:

\[
I=[low(I),high(I)],\qquad low(I)\le high(I).
\]

Với truy vấn khoảng đóng `Q=[L,R]`, hai khoảng giao khi:

\[
\boxed{low(I)\le R\quad\text{và}\quad L\le high(I).}
\]

Giả sử BST sắp theo **đầu trái `low`**, có thể thêm ID phụ để phân biệt các khoảng trùng đầu trái. Ta muốn tìm **một** khoảng giao với `Q`.

Nếu một khoảng bắt đầu rất sớm nhưng kết thúc muộn, so sánh `low` đơn thuần không đủ để loại cây con.

### 10.2. Thông tin cần để bỏ cả cây con

Lưu:

\[
\boxed{
maxHigh(u)=\max\left(
high(u),maxHigh(u.left),maxHigh(u.right)
\right),
}
\]

với:

\[
maxHigh(\varnothing)=-\infty.
\]

Nếu:

\[
maxHigh(T)<L,
\]

thì mọi khoảng trong cây con `T` đều kết thúc trước đầu trái truy vấn, nên **không giao với `Q`**. Ta có thể bỏ toàn bộ cây con.

### 10.3. Ví dụ

```text
                     [16,21], maxHigh=40
                    /                  \
          [8,9], maxHigh=23          [25,30], maxHigh=40
           /       \                   /       \
        [5,8]    [15,23]            [17,19]  [26,40]
```

Truy vấn `[22,24]`:

- Nút `[16,21]` không giao.
- Cây trái có `maxHigh=23≥22` nên **chưa thể loại**, thử đi trái.
- Tại `[8,9]`, cây trái có `maxHigh=8<22` nên bỏ cây trái.
- Đi phải tới `[15,23]`, giao truy vấn.

**Kết quả:** `[15,23]`.

### 10.4. Vì sao không chỉ dựa vào `maxHigh≥L`?

`maxHigh≥L` có nghĩa là ít nhất một khoảng trong cây con có đầu phải đủ lớn; khoảng ấy vẫn có thể **bắt đầu sau `R`**, nên chưa chắc giao. Để xây thuật toán tìm **một** khoảng giao chỉ đi một nhánh, còn phải dùng **BST theo `low`** và chứng minh lựa chọn nhánh không bỏ mất ứng viên.

Đây là nguyên tắc quan trọng khi chọn metadata:

> Một trường phụ chỉ có ý nghĩa **khi kết hợp với bất biến cấu trúc nền và điều kiện truy vấn**. Có metadata phù hợp không thay thế được chứng minh tính đúng của thuật toán.

### 10.5. Tìm một kết quả khác với liệt kê tất cả

Một interval tree cân bằng có thể tìm **một** khoảng giao theo một đường `O(\log n)`. Nhưng nếu cần **liệt kê tất cả `k` khoảng giao**, bản thân việc xuất `k` kết quả đã tốn `\Omega(k)`.

Các thuật toán duyệt có cắt nhánh bằng `maxHigh` có thể thăm nhiều nút không thuộc kết quả. **Không được mặc định mọi thuật toán liệt kê đều có `O(\log n+k)`** nếu chưa chứng minh thêm.

## 11. Query 5 — tổng đoạn con liên tiếp lớn nhất cần nhiều hơn `sum`

### 11.1. Vì sao tổng toàn đoạn chưa đủ?

Xét hai dãy:

```text
A = [4, -5, 6]
B = [4,  0, 1]
```

Cả hai có tổng bằng `5`. Nhưng tổng đoạn con liên tiếp lớn nhất:

- Với `A` là `6`, lấy đoạn `[6]`.
- Với `B` là `5`, lấy cả đoạn `[4,0,1]`.

Vì thế, chỉ lưu `sum` **không đủ** để trả lời truy vấn “tổng đoạn con liên tiếp lớn nhất”.

### 11.2. Chọn bốn trường

Với một dãy **không rỗng** `S`, lưu:

1. `sum(S)`: tổng **toàn bộ** phần tử.
2. `pref(S)`: tổng lớn nhất của một **tiền tố không rỗng**.
3. `suff(S)`: tổng lớn nhất của một **hậu tố không rỗng**.
4. `best(S)`: tổng lớn nhất của một **đoạn con liên tiếp không rỗng**.

Tại một phần tử `x`:

\[
M([x])=(x,x,x,x).
\]

### 11.3. Công thức gộp hai đoạn liên tiếp

Nếu `S=A+B`, tổng của S là:

\[
sum(S)=sum(A)+sum(B).
\]

Tiền tố lớn nhất của S hoặc:

- Nằm hoàn toàn trong A; hoặc
- Bao gồm toàn bộ A cộng một tiền tố của B.

Vì vậy:

\[
\boxed{
pref(S)=\max(pref(A),sum(A)+pref(B)).
}
\]

Tương tự:

\[
\boxed{
suff(S)=\max(suff(B),sum(B)+suff(A)).
}
\]

Đoạn con tốt nhất thuộc một trong ba trường hợp:

1. Nằm hoàn toàn trong A.
2. Nằm hoàn toàn trong B.
3. Cắt qua ranh giới, gồm một hậu tố A và một tiền tố B.

Do đó:

\[
\boxed{
best(S)=\max(best(A),best(B),suff(A)+pref(B)).
}
\]

Bộ bốn trường này gộp được trong **`O(1)`**.

### 11.4. Thực hiện gộp với dữ liệu âm

Ví dụ:

```text
A = [4, -5]
B = [6]
```

Ở A:

```text
sum = -1
pref = 4
suff = -1         # hậu tố [-5] hoặc [4,-5], tốt nhất -1
best = 4
```

Ở B:

```text
sum = 6
pref = 6
suff = 6
best = 6
```

Gộp:

\[
sum(A+B)=-1+6=5,
\]

\[
pref(A+B)=\max(4,-1+6)=5,
\]

\[
suff(A+B)=\max(6,6-1)=6,
\]

\[
best(A+B)=\max(4,6,-1+6)=6.
\]

Đúng với `[4,-5,6]`: tổng đoạn con lớn nhất là `6`.

### 11.5. Trạng thái rỗng và quy ước không rỗng

Nếu cho phép đoạn con **rỗng**, tổng tối ưu có thể luôn ít nhất `0`. Nhưng bài này chọn đoạn con **không rỗng**: với `[-7,-2,-5]` kết quả phải là `-2`, **không phải `0`**.

Để gộp với cây con rỗng, có thể dùng trạng thái trung hòa:

\[
e=(sum=0,\ pref=-\infty,\ suff=-\infty,\ best=-\infty).
\]

Khi gộp, cần xử lý số học với `-\infty` phù hợp; trong code thực tế có thể dùng đối tượng `None` và nhánh xử lý tách biệt.

**Bài học lựa chọn metadata:** một câu hỏi có thể cần **một bộ trường phối hợp**, chứ không phải một con số duy nhất.

## 12. Query 6 — kiểm tra dãy ngoặc bằng tổng và tiền tố nhỏ nhất

### 12.1. Mô hình hóa dấu ngoặc

Với dãy chỉ gồm `(` và `)`, gán:

\[
value('(')=+1,\qquad value(')')=-1.
\]

Ví dụ:

```text
Dãy:       ( ( ) ( ) )
Giá trị:   1 1 -1 1 -1 -1
Tiền tố:   0 1  2 1 2  1  0
```

Một dãy ngoặc tròn hợp lệ nếu:

1. Tổng toàn dãy bằng `0`.
2. **Mọi tổng tiền tố không âm**, tức không có dấu đóng xuất hiện trước khi có dấu mở tương ứng.

### 12.2. Chọn metadata

Với đoạn S, lưu:

- `sum(S)`: tổng giá trị.
- `minPref(S)`: **tổng tiền tố nhỏ nhất**, có tính cả tiền tố rỗng `0`.

Với một phần tử có giá trị `x`:

\[
M([x])=(x,\min(0,x)).
\]

Trạng thái rỗng:

\[
e=(0,0).
\]

### 12.3. Công thức gộp

Với `S=A+B`:

\[
sum(S)=sum(A)+sum(B).
\]

Một tiền tố của S hoặc chỉ nằm trong A, hoặc chứa toàn bộ A và một tiền tố của B. Vì thế:

\[
\boxed{
minPref(S)=\min(minPref(A),sum(A)+minPref(B)).
}
\]

Dãy ngoặc đúng khi:

\[
\boxed{sum(root)=0\quad\text{và}\quad minPref(root)\ge 0}.
\]

Trên một cây dãy cân bằng có metadata này, ta có thể kiểm tra **toàn bộ dãy** bằng hai trường ở gốc trong `O(1)` sau khi cập nhật đã hoàn thành. Thao tác sửa tại một vị trí vẫn cần bảo trì metadata dọc đường cây.

### 12.4. Vì sao một trường `sum` không đủ?

Hai dãy:

```text
"()"   → +1,-1 → tổng 0, hợp lệ
")("   → -1,+1 → tổng 0, KHÔNG hợp lệ
```

Cả hai có tổng bằng `0`, nhưng `")("` có tiền tố đầu bằng `-1`. Trường `minPref` phát hiện ngay sự khác biệt này.

### 12.5. Thứ tự gộp không được đảo

Trường `minPref` **phụ thuộc thứ tự**. Khi gộp A rồi B:

\[
minPref(A+B)=\min(minPref(A),sum(A)+minPref(B)).
\]

Không được đổi A và B chỉ vì phép `min` bản thân giao hoán; **biểu thức gộp** còn mang phần chuyển `sum(A)`.

## 13. Metadata dùng để tìm một đáp án và metadata để tổng hợp khác nhau

Có hai mẫu thiết kế lớn.

### 13.1. Mẫu tổng hợp (*aggregation*)

Ví dụ `sum`, `min`, `max`, `size`, bốn trường max-subarray hoặc cặp `sum/minPref`.

- Mỗi cây con có một tóm tắt.
- Gộp nhiều cây con theo thứ tự để lấy tóm tắt vùng lớn.
- Truy vấn toàn cây trả lời ngay từ metadata gốc.
- Truy vấn đoạn thường phân hoạch đoạn thành những cây con để gộp.

Ở các mẫu này, phép gộp kết hợp là một công cụ thiết kế rất hữu ích.

### 13.2. Mẫu định hướng hoặc cắt nhánh (*navigation/pruning*)

Ví dụ:

- `size(left)` quyết định phần tử thứ `k` nằm bên trái, ở gốc hay bên phải.
- `maxHigh(left)` chứng minh cây con trái có thể được **bỏ qua** nếu đầu phải lớn nhất nhỏ hơn đầu trái truy vấn.
- `subtree_min` có thể loại nhánh nếu mọi giá trị lớn hơn ngưỡng quan tâm.

Ở đây, metadata không nhất thiết **là kết quả trực tiếp**, mà là **chứng cứ để không cần đọc các nút khác**.

Một bài toán có thể kết hợp cả hai mẫu: BST tổng trọng số theo khoảng cần `subtree_sum` để cộng cả nhánh, đồng thời dùng thứ tự khóa để chọn đường đi.

## 14. Chọn metadata cho truy vấn tổng/trị cực trị trên đoạn vị trí

Xét một dãy số:

```text
D = [4, 1, 7, -2, 6, 3, 8]
```

Ứng dụng cần:

1. Tổng đoạn `[l,r)`.
2. Giá trị nhỏ nhất trên đoạn `[l,r)`.
3. Chèn/xóa/đảo một đoạn.

Nếu dùng một **implicit treap** hoặc một cây dãy lưu độ dài cây con, có thể lưu:

```text
size
sum
minimum
```

Bất biến:

\[
size(u)=1+size(L)+size(R),
\]

\[
sum(u)=sum(L)+value(u)+sum(R),
\]

\[
min(u)=\min(min(L),value(u),min(R)).
\]

Để lấy một đoạn:

```text
(A, Rest) = split(T, l)
(M, B) = split(Rest, r-l)

answer_sum = SUM(M)
answer_min = MIN(M)

T = merge(merge(A, M), B)
```

Nếu cây có chiều cao kỳ vọng logarit và `split/merge` hiệu quả theo độ cao, các truy vấn dùng một số hằng split/merge có thời gian **kỳ vọng `O(\log n)`**, không phụ thuộc độ dài đoạn.

### 14.1. Tại sao cần `size` dù truy vấn chỉ là min/sum?

Vì `split(T,l)` cần biết **`l` phần tử đầu** nằm ở đâu. Trường `size` là metadata **phục vụ định vị đoạn**, còn `sum/min` là metadata **phục vụ đáp án**.

Đây là ví dụ rõ ràng cho việc chọn thông tin phụ từ **toàn bộ thuật toán truy vấn**, không chỉ từ kiểu kết quả cuối cùng.

### 14.2. Đảo đoạn không đổi mọi metadata

Đảo đoạn giữ nguyên:

- `size`.
- `sum`.
- `min` và `max`.

Nhưng đảo đoạn có thể thay đổi:

- `best_prefix` và `best_suffix` (hai giá trị có thể đổi vai trò).
- Hash chuỗi theo chiều thuận.
- `minPref` của dãy dấu ngoặc, trừ khi lưu thêm tóm tắt chiều ngược.

Vì thế một trường phụ phù hợp cho truy vấn thường **chưa đủ** để kết luận nó cũng phù hợp với mọi loại **lazy update**.

## 15. Lazy propagation: metadata phải tương thích với phép cập nhật

### 15.1. Cộng một hằng số lên mọi phần tử của đoạn

Giả sử một cây con có `size=m` và `sum=s`. Muốn cộng `delta` vào tất cả `m` phần tử:

\[
\boxed{sum'=s+delta\cdot m}.
\]

Đây là lý do thao tác **range add + range sum** cần lưu **cả `size` và `sum`** nếu áp dụng lazy trên cây dãy:

```text
APPLY_ADD(node, delta):
    node.value += delta
    node.sum += delta * node.size
    node.lazy_add += delta
```

Hàm này sửa giá trị tại nút, tóm tắt cả cây con và thẻ cập nhật chờ truyền xuống. Nếu đi xuống nhánh con sau đó, phải đẩy thẻ trước (*push*).

### 15.2. Min/max khi cộng hằng số

Nếu mỗi giá trị của đoạn tăng `delta`:

\[
min'=min+delta,\qquad max'=max+delta.
\]

Vì vậy, `size,sum,min,max` đều có thể cập nhật trong `O(1)` tại gốc của một cây con khi áp dụng **cùng một phép cộng**.

### 15.3. Tổng đoạn con lớn nhất không có cùng quy tắc đơn giản

Nếu cộng `delta` vào mọi phần tử, một đoạn con dài `\ell` tăng tổng thêm:

\[
delta\cdot\ell.
\]

Nhưng **độ dài của đoạn tối ưu có thể thay đổi** sau cập nhật. Vì vậy, từ riêng `sum,pref,suff,best` không thể dùng một quy tắc đơn giản như:

```text
best += delta * size
```

cho mọi dãy và mọi `delta`.

Ví dụ:

```text
S = [-2, 5, -2]
best(S) = 5

Cộng 3 vào mọi phần tử:
S' = [1, 8, 1]
best(S') = 10
```

Nếu làm `best += 3*size`, ta được `5+9=14`, **sai**.

Đây là bài học quan trọng: **chọn metadata cho truy vấn phải tính cả phép cập nhật cần hỗ trợ**. Có những tổ hợp truy vấn/cập nhật cần metadata phức tạp hơn hoặc thuật toán khác.

### 15.4. Đảo đoạn và tóm tắt hai chiều

Nếu metadata phụ thuộc vào hướng, một cách thiết kế là lưu:

- Tóm tắt theo thứ tự thuận.
- Tóm tắt theo thứ tự ngược.

Khi đảo nguyên cây con, hoán đổi hai tóm tắt. Với max-subarray:

- `sum` giữ nguyên.
- `best` giữ nguyên vì đảo một đoạn con giữ nguyên tổng tốt nhất.
- `pref` và `suff` **đổi vai trò**.

Đối với một số phép gộp khác, quy tắc đảo có thể phức tạp hơn. Cần viết **phép biến đổi metadata do lazy tag** trước khi triển khai.

### 15.5. Thẻ lazy cần luật hợp thành

Nếu có hai cập nhật cùng loại:

```text
add(a) rồi add(b) = add(a+b)
```

Nếu có phép gán:

```text
assign(x) rồi assign(y) = assign(y)
```

Nếu có cả gán và cộng, thứ tự ảnh hưởng kết quả:

```text
assign(5), add(3) → 8
add(3), assign(5) → 5
```

Do đó lazy propagation cần nêu:

1. Cách **áp dụng** một tag vào metadata.
2. Cách **hợp thành** tag mới với tag cũ.
3. Thứ tự **push** trước khi xuống con.
4. Quy tắc **pull** sau khi thay đổi cấu trúc hoặc con.

Chỉ lưu thêm trường `lazy` mà chưa định nghĩa bốn điều này có thể tạo ra cấu trúc sai.

## 16. Xoay cây: khi nào một metadata có thể bảo trì trong `O(1)`?

### 16.1. Xoay trái

Một phép xoay trái tại `x` có con phải `y`:

```text
Trước:                          Sau:

       x                               y
      / \                             / \
     A   y                           x   C
        / \                         / \
       B   C                       A   B
```

Dù cây con toàn vùng vẫn chứa cùng các phần tử theo inorder, **tập phần tử trong cây con gốc `x`** đã đổi.

Với metadata dạng:

\[
M(u)=M(L)\oplus local(u)\oplus M(R),
\]

thứ tự tính lại phải là:

```text
x.right = B
y.left  = x

PULL(x)      # Nút đi xuống được tính trước.
PULL(y)      # Gốc mới dùng metadata của x đã đúng.
```

Với xoay phải, quy tắc đối xứng: tính nút bị đẩy xuống trước gốc mới.

### 16.2. Điều kiện cập nhật cục bộ

Một metadata phù hợp để dùng trong cây tự cân bằng thường cần:

- Có công thức tính lại từ **chính nút và hai con**.
- Công thức không duyệt toàn cây con.
- Các phép xoay chỉ sửa một số **hằng nút** tại mỗi bước.
- Các nút còn lại giữ metadata đã đúng.

Khi đó, mỗi phép xoay thêm chi phí bảo trì metadata **`O(1)`**.

### 16.3. Chứng minh quy nạp cho `pull`

Giả sử:

- Hai cây con `L,R` đã có metadata đúng.
- `local(u)` đúng cho dữ liệu đang lưu tại nút.
- `\oplus` diễn tả chính xác cách ghép các dãy/cây con theo thứ tự.

Khi gọi:

\[
M(u)=M(L)\oplus local(u)\oplus M(R),
\]

ta được tóm tắt đúng của toàn bộ cây con gốc `u`.

Một thuật toán chèn/xóa đệ quy sửa cây con trước, rồi **pull từ dưới lên**, sẽ duy trì bất biến metadata theo quy nạp. Các phép xoay phải gọi `pull` theo thứ tự phụ thuộc vừa nêu.

Điều này trả lời câu hỏi **vì sao cập nhật dọc đường đi là đủ**, thay vì tính lại toàn bộ cây sau mọi lần sửa.

## 17. Cài đặt Python: AVL tăng cường `size` và `subtree_sum`

Phần này minh họa một thiết kế xuất phát từ các truy vấn ở mục 6–9.

### 17.1. Hợp đồng API

Cây lưu:

- **Khóa nguyên phân biệt** `key` để sắp BST.
- **Trọng số nguyên** `weight` cho mỗi khóa.
- `size`: số nút/khóa trong cây con.
- `subtree_sum`: tổng trọng số trong cây con.
- `height`: chiều cao AVL theo số cạnh.

Các thao tác:

- `put(key,weight)`: nếu khóa mới thì chèn; nếu đã có thì **thay trọng số**, không thêm nút.
- `remove(key)`: xóa khóa, trả `True` nếu đã xóa.
- `select(k)`: trả `(key,weight)` của khóa nhỏ thứ `k`, với `k` từ `1`.
- `rank_lt(x)`: số khóa nhỏ hơn `x`.
- `prefix_sum_lt(x)`, `prefix_sum_le(x)`: tổng trọng số theo cận khóa.
- `sum_between(low,high)`: tổng trọng số đoạn khóa **đóng**.
- `count_between(low,high)`: số khóa trong đoạn đóng.
- `inorder()`: xuất danh sách `(key,weight)` tăng theo khóa để quan sát.

**Không có khóa trùng vật lý**. Trọng số có thể âm. API chủ động từ chối `bool` khi đầu vào cần `int`, vì `bool` là lớp con của `int` trong Python.

### 17.2. Nút và `pull`

```python
class Node:
    __slots__ = (
        "key", "weight", "left", "right",
        "height", "size", "subtree_sum"
    )

    def __init__(self, key, weight):
        self.key = key
        self.weight = weight

        self.left = None
        self.right = None

        # Nút lá mới: dữ liệu và metadata đã đúng.
        self.height = 0
        self.size = 1
        self.subtree_sum = weight


def height_of(node):
    return -1 if node is None else node.height


def size_of(node):
    return 0 if node is None else node.size


def sum_of(node):
    return 0 if node is None else node.subtree_sum


def pull(node):
    """Hai cây con của node phải có metadata đúng."""
    if node is None:
        return

    node.height = 1 + max(
        height_of(node.left), height_of(node.right)
    )
    node.size = 1 + size_of(node.left) + size_of(node.right)
    node.subtree_sum = (
        sum_of(node.left)
        + node.weight
        + sum_of(node.right)
    )


def balance_factor(node):
    return height_of(node.left) - height_of(node.right)
```

Ta có **hai nhóm metadata khác mục đích**:

- `height` bảo trì cân bằng AVL.
- `size,subtree_sum` phục vụ các truy vấn thứ hạng/tổng.

Nếu ứng dụng chỉ cần `rank` mà không cần tổng, có thể bỏ `subtree_sum`; nếu chỉ cần tổng theo cận khóa mà không cần rank, có thể bỏ `size`, nhưng phải giữ `height` nếu vẫn dùng AVL.

### 17.3. Xoay trái và xoay phải

```python
def rotate_left(x):
    y = x.right
    if y is None:
        raise ValueError("Thiếu con phải để xoay trái")

    x.right = y.left
    y.left = x

    pull(x)  # Nút bị đẩy xuống.
    pull(y)  # Gốc mới.

    return y


def rotate_right(y):
    x = y.left
    if x is None:
        raise ValueError("Thiếu con trái để xoay phải")

    y.left = x.right
    x.right = y

    pull(y)  # Nút bị đẩy xuống.
    pull(x)  # Gốc mới.

    return x
```

Nhờ `pull`, mỗi xoay cập nhật **cả chiều cao, số lượng và tổng trọng số** đúng thứ tự.

### 17.4. Hàm tái cân bằng AVL

```python
def rebalance(node):
    """Cây trái/phải đã hợp lệ và có metadata đúng."""
    pull(node)
    bf = balance_factor(node)

    if bf > 1:
        if balance_factor(node.left) < 0:
            node.left = rotate_left(node.left)
        return rotate_right(node)

    if bf < -1:
        if balance_factor(node.right) > 0:
            node.right = rotate_right(node.right)
        return rotate_left(node)

    return node
```

Một lần `rebalance` dùng nhiều nhất hai phép xoay. Khi xóa, các tổ tiên có thể tiếp tục cần tái cân bằng, nên thuật toán **vẫn phải đi hết đường trở về gốc**.

### 17.5. Chèn hoặc cập nhật trọng số

```python
def put_node(root, key, weight):
    """Trả (new_root, inserted_new_key)."""
    if root is None:
        return Node(key, weight), True

    if key < root.key:
        root.left, inserted = put_node(root.left, key, weight)

    elif key > root.key:
        root.right, inserted = put_node(
            root.right, key, weight
        )

    else:
        # Cùng khóa: chỉ thay weight.
        root.weight = weight
        pull(root)
        return root, False

    return rebalance(root), inserted
```

Khi thay trọng số của một khóa đã có:

- `size` không đổi.
- `subtree_sum` tại nút và các tổ tiên **có thể đổi**.
- `height` và cấu trúc không đổi.

Dù đường quay về vẫn gọi `rebalance`, trường hợp này không làm thay đổi cân bằng nếu trước đó cây AVL đúng.

### 17.6. Tách nguyên nút kế nhiệm khi xóa nút hai con

Để xóa một nút BST có hai con, có thể dùng **kế nhiệm inorder**: nút có khóa nhỏ nhất trong cây con phải.

Một thiết kế an toàn là **di chuyển nguyên đối tượng nút kế nhiệm**, thay vì sao chép chỉ `key` mà quên `weight`.

```python
def pop_min_node(root):
    """Trả (cây_còn_lại, nút_min_đã_tách)."""
    if root.left is None:
        remaining = root.right
        root.right = None
        return remaining, root

    root.left, minimum = pop_min_node(root.left)
    return rebalance(root), minimum
```

Nút nhỏ nhất không có con trái, nhưng **có thể có con phải**, nên phải trả `remaining=root.right` chứ không bỏ con phải ấy.

### 17.7. Xóa một khóa

```python
def delete_node(root, key):
    """Trả (new_root, removed)."""
    if root is None:
        return None, False

    if key < root.key:
        root.left, removed = delete_node(root.left, key)

    elif key > root.key:
        root.right, removed = delete_node(root.right, key)

    else:
        # Đã tìm đúng khóa cần xóa.
        if root.left is None:
            return root.right, True

        if root.right is None:
            return root.left, True

        new_right, successor = pop_min_node(root.right)

        # Dùng nguyên bản ghi key+weight của kế nhiệm.
        successor.left = root.left
        successor.right = new_right

        root.left = None
        root.right = None

        return rebalance(successor), True

    if not removed:
        return root, False

    return rebalance(root), True
```

**Vì sao không chỉ cập nhật tổng ở gốc?** Sau xóa, một cây con trung gian có thể thay đổi giá trị và hình dạng; truy vấn `select` hoặc `prefix_sum` có thể đọc metadata của bất kỳ cây con nào trên đường đi. Thuật toán phải bảo trì **từng nút bị ảnh hưởng**.

### 17.8. Lớp công khai với các truy vấn

```python
class AugmentedAVL:
    def __init__(self):
        self.root = None

    @staticmethod
    def _check_int(value, name):
        if type(value) is not int:
            raise TypeError(f"{name} phải là int")

    def __len__(self):
        return size_of(self.root)

    def put(self, key, weight):
        self._check_int(key, "key")
        self._check_int(weight, "weight")

        self.root, inserted = put_node(
            self.root, key, weight
        )
        return inserted

    def remove(self, key):
        self._check_int(key, "key")

        self.root, removed = delete_node(self.root, key)
        return removed

    def get(self, key):
        """Trả weight nếu có khóa; nếu không trả None."""
        self._check_int(key, "key")

        node = self.root
        while node is not None:
            if key < node.key:
                node = node.left
            elif key > node.key:
                node = node.right
            else:
                return node.weight

        return None

    def select(self, k):
        """Khóa nhỏ thứ k (1-based), trả (key, weight)."""
        self._check_int(k, "k")

        if not 1 <= k <= len(self):
            raise IndexError("k nằm ngoài [1,n]")

        node = self.root

        while node is not None:
            left_size = size_of(node.left)

            if k <= left_size:
                node = node.left
            elif k == left_size + 1:
                return (node.key, node.weight)
            else:
                k -= left_size + 1
                node = node.right

        raise RuntimeError("Metadata size không hợp lệ")

    def rank_lt(self, x):
        self._check_int(x, "x")

        result = 0
        node = self.root

        while node is not None:
            if x <= node.key:
                node = node.left
            else:
                result += size_of(node.left) + 1
                node = node.right

        return result

    def rank_le(self, x):
        self._check_int(x, "x")

        result = 0
        node = self.root

        while node is not None:
            if x < node.key:
                node = node.left
            else:
                result += size_of(node.left) + 1
                node = node.right

        return result

    def prefix_sum_lt(self, x):
        self._check_int(x, "x")

        result = 0
        node = self.root

        while node is not None:
            if x <= node.key:
                node = node.left
            else:
                result += sum_of(node.left) + node.weight
                node = node.right

        return result

    def prefix_sum_le(self, x):
        self._check_int(x, "x")

        result = 0
        node = self.root

        while node is not None:
            if x < node.key:
                node = node.left
            else:
                result += sum_of(node.left) + node.weight
                node = node.right

        return result

    def sum_between(self, low, high):
        """Tổng weight của các key thuộc [low, high]."""
        self._check_int(low, "low")
        self._check_int(high, "high")

        if low > high:
            return 0
        return (
            self.prefix_sum_le(high)
            - self.prefix_sum_lt(low)
        )

    def count_between(self, low, high):
        """Số khóa phân biệt trong đoạn đóng."""
        self._check_int(low, "low")
        self._check_int(high, "high")

        if low > high:
            return 0
        return self.rank_le(high) - self.rank_lt(low)

    @property
    def total_weight(self):
        return sum_of(self.root)

    def inorder(self):
        result = []
        stack = []
        node = self.root

        while node is not None or stack:
            while node is not None:
                stack.append(node)
                node = node.left

            node = stack.pop()
            result.append((node.key, node.weight))
            node = node.right

        return result
```

**Ghi chú hợp đồng:**

- `put(key,weight)` trả `True` nếu chèn khóa mới, `False` nếu chỉ thay trọng số khóa cũ.
- `remove(key)` trả `False` khi khóa không có, cây giữ nguyên.
- Trọng số âm hợp lệ: `prefix_sum` không dựa vào tổng không âm.
- `get(key)` trả `None` nếu không tìm thấy; vì trọng số bắt buộc là `int`, `None` không mơ hồ với một trọng số hợp lệ.
- `select(k)` bắt đầu từ `1`; các hàm rank trả **số khóa**, không phải thứ hạng 1-based.
- `sum_between/count_between` dùng **đoạn khóa đóng `[low,high]`**, không phải đoạn chỉ số.

### 17.9. Ví dụ sử dụng

```python
data = {
    20: 7,
    10: 5,
    30: -2,
    5: 4,
    15: 3,
    25: 6,
    35: 1,
}

tree = AugmentedAVL()

for key, weight in data.items():
    assert tree.put(key, weight)

print(tree.inorder())
# [(5, 4), (10, 5), (15, 3), (20, 7),
#  (25, 6), (30, -2), (35, 1)]

print(len(tree))                # 7
print(tree.total_weight)        # 24
print(tree.select(5))           # (25, 6)
print(tree.rank_lt(25))         # 4
print(tree.prefix_sum_lt(25))   # 19
print(tree.prefix_sum_le(30))   # 23
print(tree.sum_between(10, 30)) # 19
print(tree.count_between(10, 30))  # 5

# Thay weight ở khóa đã có.
assert not tree.put(15, 10)
print(len(tree))                # 7: số khóa không đổi
print(tree.total_weight)        # 31: tăng thêm 7

# Xóa một khóa có tồn tại.
assert tree.remove(30)
print(tree.inorder())
# [(5, 4), (10, 5), (15, 10), (20, 7),
#  (25, 6), (35, 1)]
print(len(tree))                # 6
print(tree.total_weight)        # 33

# Xóa khóa không có: không làm sai metadata.
assert not tree.remove(999)
print(tree.total_weight)        # 33
```

Khi trình bày bài, các ví dụ này là mã để **người học tự thực hành**; chúng không phải kết quả đã chạy bộ test trong bước biên soạn Markdown.

## 18. Xác thực metadata độc lập: đừng chỉ tin kết quả truy vấn

### 18.1. Những bất biến cần kiểm tra

Một validator cho AVL tăng cường nên kiểm tra:

1. Cấu trúc không có **chu trình** hoặc một nút được dùng chung ở hai đường.
2. Với mọi nút, các khóa ở cây trái đều **nhỏ hơn**, khóa ở cây phải đều **lớn hơn**; kiểm tra theo **cận tổ tiên** chứ không chỉ hai con trực tiếp.
3. `size` bằng số nút đếm lại thực tế.
4. `subtree_sum` bằng tổng trọng số tính lại thực tế.
5. `height` bằng chiều cao tính từ con.
6. Chênh lệch chiều cao của hai con không quá `1` tại mọi nút.

### 18.2. Validator hậu thứ tự, không cần sửa cây

```python
def validate_augmented_avl(root):
    """Độc lập tính lại BST, size, sum, height, AVL."""
    if root is None:
        return True

    seen = set()
    actual = {}
    # (node, min_key_exclusive, max_key_exclusive, ready)
    stack = [(root, None, None, False)]

    while stack:
        node, lower, upper, ready = stack.pop()

        if node is None:
            continue
        if not isinstance(node, Node):
            return False

        if not ready:
            identity = id(node)
            if identity in seen:
                return False
            seen.add(identity)

            if (
                type(node.key) is not int
                or type(node.weight) is not int
            ):
                return False

            if lower is not None and node.key <= lower:
                return False
            if upper is not None and node.key >= upper:
                return False

            stack.append((node, lower, upper, True))
            stack.append((node.right, node.key, upper, False))
            stack.append((node.left, lower, node.key, False))

        else:
            ls, lsum, lh = actual.get(node.left, (0, 0, -1))
            rs, rsum, rh = actual.get(node.right, (0, 0, -1))

            expected_size = ls + 1 + rs
            expected_sum = lsum + node.weight + rsum
            expected_height = 1 + max(lh, rh)

            if node.size != expected_size:
                return False
            if node.subtree_sum != expected_sum:
                return False
            if node.height != expected_height:
                return False
            if abs(lh - rh) > 1:
                return False

            actual[node] = (
                expected_size,
                expected_sum,
                expected_height,
            )

    return True
```

Hàm dùng thông tin **đã tính lại từ liên kết thực** của hai con, không lấy `size` hoặc `subtree_sum` đang lưu làm “chứng cứ” để xác thực chính chúng.

Chi phí: **`O(n)` thời gian và `O(n)` bộ nhớ phụ**. Nó phù hợp để học và kiểm thử, nhưng **không** nằm trong đường vận hành tối ưu `O(\log n)` sau mỗi cập nhật.

### 18.3. Kiểm tra bằng mô hình tham chiếu

Để kiểm tra chéo, dùng một `dict` Python làm tập bản ghi tham chiếu:

```python
reference = {}
tree = AugmentedAVL()

operations = [
    ("put", 20, 7),
    ("put", 10, 5),
    ("put", 30, -2),
    ("put", 5, 4),
    ("put", 15, 3),
    ("put", 25, 6),
    ("put", 35, 1),
    ("put", 15, 10),  # cập nhật weight
    ("del", 30, None),
]

for op, key, weight in operations:
    if op == "put":
        tree.put(key, weight)
        reference[key] = weight
    else:
        tree.remove(key)
        reference.pop(key, None)

    expected_keys = sorted(reference)
    expected_pairs = [
        (key, reference[key]) for key in expected_keys
    ]

    assert tree.inorder() == expected_pairs
    assert len(tree) == len(expected_keys)
    assert tree.total_weight == sum(reference.values())
    assert validate_augmented_avl(tree.root)

    for i, k in enumerate(expected_keys, start=1):
        assert tree.select(i) == (k, reference[k])

    for x in [0, 10, 17, 20, 30, 99]:
        expected_rank = sum(k < x for k in reference)
        expected_prefix = sum(
            w for k, w in reference.items() if k < x
        )

        assert tree.rank_lt(x) == expected_rank
        assert tree.prefix_sum_lt(x) == expected_prefix
```

Bộ so sánh này cố ý dùng thuật toán **quét đơn giản** để làm chuẩn tính đúng. Không nên dùng nó sau mỗi truy vấn trong hệ thống yêu cầu hiệu năng logarit.

### 18.4. Bắt lỗi cập nhật một phần metadata

Giả sử sau khi sửa trọng số khóa `15`, mã chỉ cập nhật `subtree_sum(root)` mà bỏ `subtree_sum(10)`. Khi đó:

- Tổng toàn cây ở gốc có thể vẫn đúng.
- Một truy vấn `prefix_sum_lt(20)` dùng metadata cây trái gốc tại `10` có thể sai.
- Validator đọc lại trọng số các nút sẽ phát hiện `subtree_sum(10)` không đúng.

Vì vậy, **một kết quả truy vấn đúng trong một tình huống không chứng minh được mọi metadata đều đúng**.

## 19. Phân tích chi phí của AVL có hai trường tăng cường

Ký hiệu:

- `n`: số khóa phân biệt/nút vật lý.
- `h`: chiều cao theo số cạnh.
- Giả định so sánh khóa, cộng trọng số và thao tác số học trên các số có kích thước giới hạn mất `O(1)`.

| Thao tác | Chiều cao bất kỳ | AVL cân bằng |
|---|---|---|
| `select(k)` | `O(h+1)` | `O(\log(n+1))` |
| `rank_lt(x)` | `O(h+1)` | `O(\log(n+1))` |
| `prefix_sum_lt(x)` / `prefix_sum_le(x)` | `O(h+1)` | `O(\log(n+1))` |
| `sum_between(L,R)` | `O(h+1)` | `O(\log(n+1))` |
| `count_between(L,R)` | `O(h+1)` | `O(\log(n+1))` |
| `put(key,weight)` | `O(h+1)` nếu có phương án cập nhật cấu trúc thích hợp | `O(\log(n+1))` |
| `remove(key)` | `O(h+1)` nếu có phương án cập nhật cấu trúc thích hợp | `O(\log(n+1))` |
| Một lần `pull` | `O(1)` | `O(1)` |
| Một phép xoay đơn + `pull` | `O(1)` | `O(1)` |
| Xuất toàn bộ các khóa/weight | `O(n)` | `O(n)` |
| Validator tính lại toàn cây | `O(n)` | `O(n)` |

### 19.1. Bộ nhớ

- Mỗi nút lưu một số hằng trường → tổng bộ nhớ **`O(n)`**.
- `rank/select/prefix_sum` dùng vòng lặp → **`O(1)` bộ nhớ phụ**.
- `put/remove/pop_min_node` dùng đệ quy → **`O(h+1)` bộ nhớ stack**, tương ứng `O(\log(n+1))` trên AVL.
- `inorder()` tạo kết quả `n` cặp → **`O(n)` bộ nhớ đầu ra**.
- Validator dùng bảng và tập đánh dấu → **`O(n)` bộ nhớ phụ**.

Nếu trọng số là số nguyên tùy ý lớn, chi phí cộng/so sánh và bộ nhớ của từng số còn phụ thuộc **số bit** của nó. Big-O trong bảng dùng mô hình xử lý số học có chi phí hằng, thường đủ cho bài nhập môn.

### 19.2. Vì sao không có “truy vấn nhanh miễn phí”?

Thêm một trường mỗi nút:

- Tăng **bộ nhớ trên mỗi nút**.
- Tăng công việc của `pull` trên các đường cập nhật.
- Tạo thêm **bất biến phải duy trì và kiểm thử**.
- Có thể làm API sửa đổi dữ liệu khó hơn.

Metadata đáng lưu khi **lợi ích từ truy vấn** lớn hơn **chi phí bảo trì và bộ nhớ** cho workload thực tế.

## 20. Khi một tóm tắt hằng kích thước không đủ

### 20.1. Số lượng giá trị phân biệt trong một đoạn tùy ý

Tưởng tượng dãy:

```text
[1,2,1,3,2,4]
```

Muốn đếm số giá trị phân biệt trên mỗi đoạn con:

```text
[1,2,1] → 2 giá trị phân biệt
[1,3,2,4] → 4 giá trị phân biệt
```

Nếu mỗi cây con chỉ lưu:

```text
size
sum
min
max
```

thì không thể xác định chính xác **số giá trị phân biệt** của phép nối hai đoạn, vì còn cần biết **giao giữa các tập giá trị**.

Ví dụ:

```text
A = [1,2]
B = [1,2]   → distinct(A+B) = 2
C = [3,4]   → distinct(A+C) = 4
```

Cả `B` và `C` đều có `2` giá trị phân biệt. Nhưng tác động của chúng khi nối với A khác nhau.

Có thể lưu **tập giá trị** tại mỗi cây con, nhưng kích thước tập có thể tỷ lệ với số phần tử của cây con; gộp tập không còn chi phí hằng nếu miền giá trị không cố định, và tổng bộ nhớ có thể lớn.

Không nên tuyên bố bất khả thi cho **mọi thuật toán**: có thể dùng chỉ mục offline, cấu trúc persistent, phương pháp chia khối, các thuật toán đếm phân biệt chuyên dụng hoặc chấp nhận xấp xỉ. Kết luận đúng ở đây là: **một vài metadata hằng kích thước như `size/sum/min/max` không đủ cho truy vấn chính xác tổng quát này**.

### 20.2. Trung vị của hai cây con không gộp được chỉ từ hai trung vị

Xét:

```text
A = [1, 100, 101]     median(A)=100
B = [2, 100, 200]     median(B)=100
```

Có cùng trung vị, nhưng **phân bố các giá trị còn lại** khác nhau. Trung vị của phép nối với một đoạn thứ ba có thể khác nhau, dù hai trung vị ban đầu giống nhau.

Vì vậy, lưu **chỉ `median` của từng cây con** không cho công thức gộp chính xác cố định cho mọi dữ liệu.

Nếu dữ liệu được tổ chức thành một **BST có thứ tự** và lưu `size`, ta có thể tìm trung vị bằng `select` theo thứ hạng. Đây là cách **dùng bất biến thứ tự của cây** thay vì cố gộp trực tiếp các trung vị cục bộ.

### 20.3. Histogram đầy đủ

Nếu miền giá trị nhỏ, cố định với `M` loại, có thể lưu một vector tần suất độ dài `M` trên mỗi nút và gộp từng thành phần.

Nhưng:

- Gộp tốn `O(M)`, không còn `O(1)` khi `M` là tham số tăng.
- Bộ nhớ là `O(nM)` với `n` nút nếu lưu toàn bộ vector tại mỗi nút.
- Nếu chỉ cần vài truy vấn theo khóa, cấu trúc khác có thể phù hợp hơn.

Đây là ví dụ **tóm tắt có tồn tại**, nhưng chi phí gộp và bộ nhớ có thể không đáp ứng mục tiêu.

## 21. Chọn thông tin phụ tối thiểu và đủ: những tình huống điển hình

### 21.1. Hỏi chỉ có tồn tại phần tử thỏa điều kiện

Nếu mỗi nút có Boolean `ok(u)` và cần biết **trong toàn cây con có nút nào thỏa `P` không**, lưu:

\[
exists(u)=exists(L)\lor P(u)\lor exists(R).
\]

Trường này đủ để trả Boolean cho toàn cây. Nhưng nếu sau đó cần **liệt kê mọi nút thỏa `P`**, Boolean alone không cung cấp danh sách kết quả; nó chỉ giúp cắt một số nhánh chắc chắn không chứa kết quả.

### 21.2. Hỏi giá trị nhỏ nhất và số lần đạt nhỏ nhất

Nếu cần cả:

1. Giá trị nhỏ nhất trong đoạn.
2. Số phần tử bằng giá trị nhỏ nhất.

Thì lưu **một cặp**:

\[
M(S)=(minValue(S),countMin(S)).
\]

Gộp hai đoạn A, B:

- Nếu `minA<minB`: giữ `(minA,countA)`.
- Nếu `minB<minA`: giữ `(minB,countB)`.
- Nếu bằng nhau: giữ `(minA,countA+countB)`.

Trạng thái rỗng có thể là `(+\infty,0)` nếu so sánh hỗ trợ vô cực hoặc là một giá trị sentinel có nhánh kiểm tra.

**Chỉ lưu `min` sẽ không trả được số lần xuất hiện của min**.

### 21.3. Hỏi khoảng cách nhỏ nhất giữa các khóa kề nhau

Nếu một BST lưu các khóa phân biệt theo thứ tự tăng, muốn biết **chênh lệch nhỏ nhất giữa hai khóa kề nhau**, có thể cần:

- `minKey` của cây con.
- `maxKey` của cây con.
- `minGap` nhỏ nhất trong cây con.

Khi gộp dãy tăng A rồi B, khoảng cách tốt nhất hoặc:

- Nằm hoàn toàn trong A.
- Nằm hoàn toàn trong B.
- Nằm giữa khóa cuối của A và khóa đầu của B.

Công thức:

\[
minGap(A+B)=\min(
minGap(A),
minGap(B),
minKey(B)-maxKey(A)
)
\]

với hai đoạn **không rỗng**. Cần định nghĩa giá trị trung hòa khi một đoạn rỗng hoặc có dưới hai khóa.

**Mấu chốt:** vì truy vấn hỏi **khoảng cách giữa hai phần tử ở ranh giới**, metadata phải chứa thông tin về **hai đầu của đoạn**, không chỉ về trị nhỏ nhất hiện có.

### 21.4. Hỏi prefix sum đầu tiên vượt ngưỡng

Với một dãy **trọng số không âm**, lưu `sum` ở từng cây con và tìm vị trí đầu tiên mà tổng tiền tố đạt một ngưỡng `target` bằng cách so với tổng cây trái.

Nhưng nếu trọng số có thể **âm**, các tổng tiền tố không còn đơn điệu. Khi đó, chỉ biết `sum(left)` không đủ để khẳng định không có tiền tố vượt ngưỡng trong nhánh trái.

Có thể cần lưu **maxPrefix** hoặc thông tin phù hợp hơn. Giả thiết dữ liệu **không âm** chính là một phần của chứng minh điều hướng, không phải chi tiết có thể bỏ qua.

## 22. Bảng quyết định chọn metadata và điều kiện bắt buộc

| Mục tiêu truy vấn | Tổ chức dữ liệu phù hợp | Metadata chính | Công thức/ý tưởng | Lưu ý cập nhật |
|---|---|---|---|---|
| Phần tử thứ `k` | BST theo khóa hoặc cây theo vị trí | `size` | `1+size(L)+size(R)` | Xoay/split/merge phải pull |
| Rank khóa `x` | BST theo khóa | `size` | Bỏ qua cây trái theo so sánh khóa | Khóa trùng cần quy ước |
| Tổng toàn cây con | Cây nhị phân | `sum` | `sum(L)+v+sum(R)` | Thay giá trị phải cập nhật tổ tiên |
| Tổng trong đoạn khóa | BST theo khóa | `sum` | Hai tổng tiền tố | Cần thứ tự BST đúng |
| Tổng đoạn vị trí | Cây dãy theo vị trí | `size,sum` | Split đoạn, đọc `sum` | Chèn/xóa và lazy phải đồng bộ |
| Min/max đoạn | Cây dãy | `size,min/max` | Gộp `min/max` | Range add có quy tắc đơn giản |
| Một khoảng giao | BST theo `low` | `maxHigh` | Loại nhánh kết thúc sớm | Phải chứng minh điều hướng |
| Tổng đoạn con lớn nhất | Cây dãy | `sum,pref,suff,best` | Gộp ba vị trí của đáp án | Range add không có cập nhật đơn giản |
| Dãy ngoặc đúng | Cây dãy | `sum,minPref` | Tổng 0, mọi tiền tố không âm | Đảo đoạn cần tóm tắt chiều ngược |
| Min và số lần min | Cây dãy | `min,countMin` | Gộp min và cộng count khi hòa | Chèn/xóa/cập nhật cần pull |
| Khoảng cách khóa kề nhỏ nhất | BST theo khóa | `minKey,maxKey,minGap` | Xét hai đầu ở ranh giới | Khóa phải có thứ tự |
| Tổng tiền tố tới ngưỡng | Cây dãy | `sum` với dữ liệu không âm; hơn thế nếu có âm | Điều hướng theo tổng tiền tố | Kiểm tra giả thiết không âm |
| Số giá trị phân biệt đoạn bất kỳ | Cấu trúc/chỉ mục chuyên dụng | Không đủ với một vài số `size/sum/min` | Cần thông tin giao các tập | Xem chi phí bộ nhớ/gộp |

**Cách đọc bảng:** metadata là **điểm khởi đầu**, không phải thuật toán hoàn chỉnh. Mỗi hàng vẫn cần một cây nền, hợp đồng cập nhật, cơ chế truy vấn và chứng minh độc lập.

## 23. Các giới hạn phải nêu khi thiết kế

### 23.1. Tổng hợp nhanh không bảo đảm cây thấp

Một BST có trường `sum` đúng vẫn có thể **suy biến thành đường thẳng** sau chuỗi chèn có thứ tự:

```text
1 -> 2 -> 3 -> 4 -> 5 -> ...
```

Khi đó, dù mỗi lần `pull` chỉ `O(1)`, số nút trên đường cập nhật hoặc truy vấn có thể là `O(n)`.

Muốn chặn trên logarit chắc chắn, cần cây nền có bảo đảm chiều cao như **AVL/Red–Black Tree**. Với treap ngẫu nhiên, có thể có **thời gian kỳ vọng** logarit dưới các giả thiết phù hợp, không phải bảo đảm cho mọi cấu hình priority.

### 23.2. Sửa khóa khác sửa payload

Trong BST theo khóa, thay `weight` tại khóa `x`:

- **Không đổi vị trí** của nút trong thứ tự BST.
- Cần cập nhật `subtree_sum` ở tổ tiên.

Thay **chính khóa `x`** thành khóa `y` có thể phá thứ tự BST; thường phải **xóa khóa cũ rồi chèn khóa mới**, hoặc có một API cập nhật được thiết kế đúng.

Không được chỉ gán `node.key=y` rồi `pull`; metadata đúng không cứu được một cây đã mất bất biến thứ tự.

### 23.3. Truy vấn đọc nhưng có thể chạm cấu trúc

Trong implicit treap, một số truy vấn đoạn thực hiện:

```text
split → đọc metadata đoạn → merge
```

Về ngữ nghĩa, dãy không đổi. Nhưng về con trỏ, thao tác **có thể sửa cấu trúc trung gian**. Khi có đọc/ghi đồng thời hoặc snapshot bất biến, phải thiết kế cơ chế đồng bộ hay cấu trúc persistent, không mặc định mọi truy vấn là read-only ở mức bộ nhớ.

### 23.4. Overflow và độ chính xác

Metadata `sum`, `product`, `sum_of_squares` có thể tăng lớn:

- Với số nguyên cố định độ rộng, có nguy cơ **tràn số**.
- Với số thực, phép cộng không hoàn toàn kết hợp ở mức bit do **làm tròn**, dù kết hợp trong toán học.
- Với thống kê như trung bình/variance, cần xem xét **độ ổn định số học** của công thức gộp.

Nếu ứng dụng cần kết quả chính xác ở mức số nguyên hoặc xác định bit-for-bit, lựa chọn kiểu dữ liệu và thứ tự gộp là một phần của thiết kế.

### 23.5. Metadata dư thừa cũng có thể hữu ích

Không phải lúc nào “ít trường nhất” cũng là mục tiêu tuyệt đối. Đôi khi lưu đồng thời:

```text
size
sum
min
max
```

giúp nhiều truy vấn trong ứng dụng mà chỉ tăng một số hằng trường mỗi nút. Nhưng nếu mỗi lần cập nhật phải bảo trì hàng chục trường, còn truy vấn hiếm khi dùng, lợi ích có thể không bù chi phí.

Cần cân nhắc theo workload thực tế.

## 24. Các lỗi thường gặp khi chọn và bảo trì thông tin phụ

1. **Thấy một ví dụ dùng `size` rồi áp `size` cho mọi truy vấn.** Tổng, giao khoảng hoặc dãy ngoặc có yêu cầu thông tin khác.
2. **Chỉ nhìn kết quả truy vấn mà quên phép cập nhật.** Metadata gộp nhanh có thể không hỗ trợ lazy update đang cần.
3. **Không định nghĩa tập rỗng.** `sum(empty)=0`, `min(empty)=+\infty` hoặc sentinel phù hợp phải được quy định.
4. **Không nêu đoạn đóng/nửa mở.** `[L,R]` và `[L,R)` khác nhau ở đầu mút.
5. **Nhầm chỉ số từ `0` với rank từ `1`.** Dễ gây lỗi lệch một trong `select`.
6. **Nhầm số khóa phân biệt với số lần xuất hiện.** Cần quy ước và metadata tương ứng.
7. **Dùng `sum` để suy ra số phần tử.** Trọng số có thể âm hoặc bằng không; tổng không xác định số lượng.
8. **Dùng `size` để suy ra tổng trọng số.** Kích thước không phản ánh giá trị tại nút.
9. **Lưu `median` ở từng con rồi cố gộp từ hai median.** Thiếu thông tin phân bố.
10. **Lưu `min/max` rồi cho rằng đếm được bao nhiêu lần đạt min.** Cần thêm `countMin`.
11. **Lưu `sum` rồi cho rằng đủ tính tổng đoạn con lớn nhất.** Cần `pref,suff,best` bổ sung.
12. **Kiểm tra dãy ngoặc chỉ bằng tổng bằng `0`.** Dãy `")("` có tổng `0` nhưng sai vì tiền tố âm.
13. **Lưu `maxHigh` nhưng không tổ chức cây theo đầu trái.** Điều kiện điều hướng chuẩn của interval tree phụ thuộc thứ tự BST.
14. **Cho rằng `maxHigh≥L` chứng minh đã có khoảng giao.** Đây chỉ là một điều kiện chưa thể loại trừ nhánh.
15. **Cho rằng metadata tính từ hai con là cập nhật `O(1)` trong mọi trường hợp.** Phép gộp tập/histogram có thể tốn nhiều thời gian.
16. **Không phân biệt tính kết hợp với tính giao hoán.** Metadata phụ thuộc thứ tự không được tự đổi chỗ hai nhánh.
17. **Xoay cây rồi quên gọi `pull` tại hai nút bị đổi con.** Metadata có thể cũ dù inorder đúng.
18. **Tính metadata gốc mới trước nút bị đẩy xuống khi xoay.** Gốc mới có thể đọc trường con cũ.
19. **Chỉ cập nhật metadata tại gốc toàn cây.** Các cây con trung gian cũng phải đúng.
20. **Thay payload tại nút mà không cập nhật tổ tiên.** Tổng/min/max ở trên có thể sai.
21. **Thay khóa BST tại chỗ mà không tái định vị.** Có thể phá thứ tự bất chấp metadata đúng.
22. **Chèn/xóa nút có hai con nhưng chỉ sao chép khóa của kế nhiệm, bỏ quên payload.** Dữ liệu có thể bị ghép sai.
23. **Dùng chỉ `sum` để tìm tổng tiền tố vượt ngưỡng khi trọng số âm.** Tổng tiền tố có thể không đơn điệu.
24. **Cộng `delta*size` vào `best` khi range add.** Đoạn tối ưu có thể thay đổi độ dài.
25. **Đảo đoạn nhưng không đổi metadata phụ thuộc hướng.** Hash thuận hoặc minPrefix có thể sai.
26. **Thêm lazy tag nhưng không có luật hợp thành tag.** Gán rồi cộng khác cộng rồi gán.
27. **Nhầm `O(1)` của một lần `pull` với `O(1)` của cả lần chèn.** Vẫn cần xử lý đường đi cây.
28. **Tin rằng có metadata thì BST tự cân bằng.** Cần cơ chế cân bằng độc lập.
29. **Gọi validator `O(n)` sau mọi cập nhật rồi tuyên bố tổng chi phí `O(\log n)`.** Kiểm thử phải tách khỏi đường vận hành.
30. **Chỉ thử vài truy vấn trả đúng mà không xác minh metadata từng nút.** Sai trường ở nút giữa có thể chưa lộ.
31. **Lưu tập giá trị lớn ở mọi nút rồi nói bộ nhớ chỉ `O(n)`.** Nếu mỗi tóm tắt có kích thước tăng theo cây con, bộ nhớ có thể lớn hơn.
32. **Bỏ qua số bit của số nguyên và overflow.** Chi phí/đúng đắn của `sum` còn phụ thuộc kiểu số.
33. **Dùng metadata theo thứ tự inorder cho phép xoay nhưng quên xét trường hợp đảo dãy.** Xoay giữ thứ tự, đảo dãy thì không.
34. **Không phân biệt query “một kết quả” và “tất cả kết quả”.** Liệt kê `k` kết quả tốn ít nhất `\Omega(k)`.
35. **Không có chính sách cập nhật khi khóa trùng.** Chọn `count` hay `(key,id)` ngay từ đầu.
36. **Quên rằng một truy vấn dùng split–merge có thể sửa con trỏ tạm thời.** Cần đồng bộ nếu có nhiều luồng.
37. **Cho rằng metadata càng nhiều thì cây càng tốt.** Cần đo lợi ích của truy vấn so với bộ nhớ và chi phí cập nhật.
38. **Không kiểm tra tính đúng bằng mô hình tham chiếu.** Nên so sánh với phép quét đơn giản trong bộ thử nghiệm.
39. **Suy ra công thức gộp từ ví dụ thuận lợi có toàn số dương.** Cần kiểm tra số âm, số không và đoạn rỗng.
40. **Không định nghĩa rõ “phần tử” được đếm.** Có thể là nút, bản ghi, khóa phân biệt hoặc số lần xuất hiện, mỗi cách dẫn tới metadata khác.

## 25. Bài tập thực hành có đáp án

### Bài 1. Chọn trường cho truy vấn rank

Một BST cần trả số khóa nhỏ hơn `x`. Nên lưu trường nào?

**Đáp án:** Lưu **`size` của mỗi cây con** để cộng số khóa ở toàn bộ nhánh trái khi đi phải. Phải kết hợp với bất biến BST theo khóa.

### Bài 2. Vì sao `sum` không đủ cho rank?

Một cây con có tổng trọng số `100`. Có suy ra được số nút của nó không?

**Đáp án:** **Không.** `100` có thể là một nút trọng số `100` hoặc rất nhiều nút có trọng số nhỏ, âm hay bằng không. Cần `size`.

### Bài 3. Tính metadata gốc

Cây có gốc trọng số `7`, cây trái `size=3,sum=12` và cây phải `size=3,sum=5`. Tính `size` và `sum` ở gốc.

**Đáp án:**

\[
size=3+1+3=7,
\]

\[
sum=12+7+5=24.
\]

### Bài 4. Truy vấn chọn thứ hạng

Trong các khóa tăng dần `[5,10,15,20,25,30,35]`, `select(5)` trả khóa gì?

**Đáp án:** **`25`**. Vị trí đánh từ `1`.

### Bài 5. Rank trên khóa không tồn tại

Với tập khóa bài 4, `rankLT(22)` bằng bao nhiêu?

**Đáp án:** **`4`** vì `5,10,15,20<22`. Không yêu cầu `22` có trong cây.

### Bài 6. Tổng tiền tố

Trong cây mẫu có trọng số `4,5,3,7,6,-2,1` theo khóa tăng, `prefixSumLT(25)` bằng bao nhiêu?

**Đáp án:** **`19`**, từ các trọng số `4+5+3+7`.

### Bài 7. Tổng đoạn khóa đóng

Tính `sumBetween(10,30)` trên cây mẫu.

**Đáp án:** **`19`**, vì `5+3+7+6-2=19`. Hoặc `prefixSumLE(30)-prefixSumLT(10)=23-4=19`.

### Bài 8. Thay trọng số và kích thước

Nếu trọng số tại khóa `15` thay từ `3` thành `10`, metadata nào đổi?

**Đáp án:** `subtree_sum` ở nút `15` và các tổ tiên tăng thêm `7`; **`size` không đổi** vì không thêm/bớt nút. `height` không đổi nếu cây không đổi hình dạng.

### Bài 9. Chèn khóa trùng

Ứng dụng cho phép nhiều bản ghi có cùng khóa. Có thể tiếp tục dùng `size(u)=1+size(L)+size(R)` để đếm số **lần xuất hiện** nếu gộp trùng bằng `count` không?

**Đáp án:** **Không.** Nếu một nút đại diện `count(u)` lần, phải dùng `size(u)=count(u)+size(L)+size(R)`.

### Bài 10. Chọn metadata cho giao khoảng

Cây sắp theo đầu trái của các khoảng, cần bỏ một nhánh mà mọi khoảng đều kết thúc trước `L`. Trường phù hợp?

**Đáp án:** **`maxHigh`**, đầu phải lớn nhất của toàn bộ cây con. Nếu `maxHigh<L`, nhánh chắc chắn không giao với `[L,R]` đóng.

### Bài 11. Tại sao `maxHigh≥L` chưa đủ?

Cây con có `maxHigh=100` và truy vấn `[20,30]`. Có chắc cây con chứa khoảng giao không?

**Đáp án:** **Không.** Khoảng đạt đầu phải `100` có thể bắt đầu từ `50`, hoàn toàn sau `30`. Phải xét thêm đầu trái và thứ tự BST.

### Bài 12. Sum và max-subarray

Hai dãy `[4,-5,6]` và `[4,0,1]` đều có tổng bằng `5`. Tổng đoạn con lớn nhất của chúng lần lượt là bao nhiêu?

**Đáp án:** **`6`** và **`5`**. Vì vậy metadata chỉ có `sum` không đủ.

### Bài 13. Bốn trường max-subarray

Kể tên bốn trường giúp gộp truy vấn tổng đoạn con liên tiếp lớn nhất.

**Đáp án:** **`sum,pref,suff,best`**, lần lượt là tổng toàn đoạn, tổng tiền tố lớn nhất, tổng hậu tố lớn nhất và tổng đoạn con liên tiếp lớn nhất, với quy ước đoạn con không rỗng nhất quán.

### Bài 14. Gộp giá trị `best`

Nếu `A,B` là hai đoạn liên tiếp có `best(A)=4`, `best(B)=6`, `suff(A)=-1` và `pref(B)=6`, `best(A+B)` là bao nhiêu?

**Đáp án:**

\[
\max(4,6,-1+6)=6.
\]

### Bài 15. Dãy ngoặc

Dãy `")("` có tổng dấu `0`. Tại sao không hợp lệ?

**Đáp án:** Tổng tiền tố đầu tiên bằng `-1`. Cần thêm metadata **`minPref`**, không chỉ `sum`.

### Bài 16. Gộp tiền tố nhỏ nhất

Với hai đoạn A, B, viết công thức `minPref(A+B)`.

**Đáp án:**

\[
minPref(A+B)=\min(minPref(A),sum(A)+minPref(B)).
\]

### Bài 17. Monoid

Phép tổng các số nguyên với trạng thái rỗng `0` có phải một monoid không? Vì sao?

**Đáp án:** **Có**, vì phép cộng số nguyên **kết hợp** và `0` là phần tử trung hòa: `0+x=x+0=x`.

### Bài 18. Kết hợp và giao hoán

Phép nối chuỗi có kết hợp không? Có giao hoán không?

**Đáp án:** **Kết hợp**, vì nối `(A+B)+C` hay `A+(B+C)` cho cùng thứ tự; **không giao hoán**, vì `"ab"+"cd"` khác `"cd"+"ab"`.

### Bài 19. Một phép xoay cần pull theo thứ tự nào?

Sau xoay trái tại `x` có con phải `y`, cần `pull(x)` hay `pull(y)` trước?

**Đáp án:** **`pull(x)` trước**, vì `x` bị đẩy xuống và metadata mới của nó là đầu vào để tính `y`.

### Bài 20. Range add và sum

Một cây con có `size=8,sum=30`. Cộng `delta=5` vào mọi phần tử. Tổng mới?

**Đáp án:** `30+5×8=70`. Do đó lazy add với `sum` cần biết cả **`size`**.

### Bài 21. Range add với max-subarray

Nếu chỉ lưu `sum,pref,suff,best`, có thể cập nhật `best` bằng `best+=delta*size` cho mọi phép cộng đoạn không?

**Đáp án:** **Không.** Độ dài đoạn con tối ưu có thể đổi sau khi cộng, nên quy tắc đó có thể sai.

### Bài 22. Đảo đoạn và metadata

Những trường nào trong `size,sum,min,max,pref,suff` thường không đổi khi đảo thứ tự một đoạn, và trường nào có thể đổi?

**Đáp án:** **`size,sum,min,max`** không đổi vì phụ thuộc tập giá trị chứ không phụ thuộc thứ tự; **`pref,suff`** có thể đổi vai trò hoặc giá trị.

### Bài 23. Thẻ lazy gán/cộng

Vì sao `assign(5)` rồi `add(3)` khác `add(3)` rồi `assign(5)`?

**Đáp án:** Chuỗi thứ nhất cho giá trị `8`, chuỗi thứ hai cho `5`. Lazy tag cần luật **hợp thành theo đúng thứ tự cập nhật**.

### Bài 24. Số khóa phân biệt

Nếu cần đếm số giá trị phân biệt trong một đoạn dãy tùy ý, `size,sum,min,max` có đủ không?

**Đáp án:** **Không.** Khi nối hai đoạn cần biết các giá trị **xuất hiện ở cả hai đoạn**; một vài số tóm tắt ấy không biểu diễn giao hai tập giá trị.

### Bài 25. Trung vị cục bộ

Có thể lấy trung vị của dãy nối từ trung vị của hai nửa mà không biết thêm dữ liệu nào khác không?

**Đáp án:** **Không**, vì còn phụ thuộc phân bố giá trị ở hai nửa. Nếu dãy được quản lý dưới dạng BST theo khóa, có thể lưu **`size`** và tìm trung vị theo `select`.

### Bài 26. Min và số lần min

Ứng dụng cần biết min và số phần tử bằng min trong một cây con. Tại sao phải lưu `(min,countMin)` thay vì chỉ `min`?

**Đáp án:** Vì khi hai cây con có cùng min, số lần đạt min phải **cộng** từ cả hai. Chỉ `min` không chứa số lần xuất hiện.

### Bài 27. Khoảng cách khóa kề nhỏ nhất

Một BST sắp theo khóa cần biết chênh lệch nhỏ nhất của hai khóa kề nhau. Nêu ba trường thích hợp.

**Đáp án:** **`minKey,maxKey,minGap`**. Khi nối hai vùng khóa tăng dần, còn cần xét khoảng cách giữa `maxKey(left)` và `minKey(right)`.

### Bài 28. Cây nền suy biến

Một BST không cân bằng có `size` và `sum` đúng, nhưng chiều cao `h=n-1`. `select` có bảo đảm `O(\log n)` không?

**Đáp án:** **Không.** Chỉ đi một đường nhưng đường ấy có thể dài `O(n)`. Cần cân bằng cây nền nếu muốn chặn trên logarit chắc chắn.

### Bài 29. Bộ nhớ metadata

Một AVL có `n` nút, mỗi nút thêm hai trường số nguyên `size,sum`. Bậc tăng trưởng bộ nhớ của các trường ấy là bao nhiêu?

**Đáp án:** **`O(n)`**, vì số trường mỗi nút là hằng số. Chi phí chi tiết của số nguyên rất lớn còn phụ thuộc số bit.

### Bài 30. Validator

Một validator chỉ kiểm tra `subtree_sum(root)` bằng tổng toàn bộ trọng số có đủ không?

**Đáp án:** **Không.** `subtree_sum` của các nút trung gian vẫn có thể sai; cần tính lại từ dưới lên tại **mọi nút**, đồng thời kiểm tra thứ tự BST và cấu trúc cân bằng nếu có.

### Bài 31. Tác động của thao tác sửa khóa

Trong BST theo khóa, nếu muốn đổi khóa `10` thành `28`, có thể chỉ gán `node.key=28` rồi `pull` không?

**Đáp án:** **Không.** Khóa mới có thể không còn đúng vị trí BST. Phải tái định vị nút hoặc xóa/chèn theo một thuật toán bảo toàn thứ tự.

### Bài 32. Chọn metadata tối thiểu

Một ứng dụng chỉ cần **kiểm tra có nút nào mang giá trị âm trong cây con hay không**, không cần đếm hay biết giá trị nhỏ nhất. Có thể lưu metadata một bit kiểu nào?

**Đáp án:** Lưu `hasNegative(u)`:

\[
hasNegative(u)=hasNegative(L)
\lor (value(u)<0)
\lor hasNegative(R).
\]

Nếu ứng dụng sau này hỏi **có bao nhiêu** số âm thì Boolean này không đủ; cần lưu một **bộ đếm**.

### Bài 33. Khi nào cần cả `size` và `sum`?

Một cây dãy theo vị trí cần tính tổng trên đoạn chỉ số `[l,r)` bằng split–merge. Vì sao chỉ có `sum` không đủ?

**Đáp án:** **`size` cần để tách đúng `l` phần tử đầu và `r-l` phần tử tiếp theo**; `sum` dùng để đọc kết quả trên cây con đoạn đã tách. Hai trường phục vụ hai phần khác nhau của thuật toán.

### Bài 34. Chi phí gộp histogram

Nếu mỗi nút lưu histogram `M` loại giá trị, phép gộp hai histogram mất thời gian bao nhiêu theo `M`? Bộ nhớ lưu trên `n` nút là bao nhiêu?

**Đáp án:** Thời gian **`O(M)` cho một lần gộp**; nếu mỗi nút lưu đủ `M` ô thì bộ nhớ **`O(nM)`**. Không được gọi chi phí này `O(1)` nếu `M` tăng.

### Bài 35. Chứng minh truy vấn đúng

Nêu hai điều cần chứng minh cho một thuật toán trả lời truy vấn nhanh nhờ metadata.

**Đáp án:** Thứ nhất, **metadata được tính và duy trì đúng sau mọi cập nhật**. Thứ hai, **thuật toán dùng metadata để gộp/bỏ nhánh mà không bỏ sót hoặc đếm trùng đáp án**. Cây nền phải còn giữ bất biến thứ tự/cân bằng mà thuật toán dựa vào.

## 26. Checklist đánh giá một thiết kế cây tăng cường

Trước khi triển khai hoặc đưa vào sản phẩm, có thể tự kiểm tra:

- [ ] Truy vấn được định nghĩa chính xác, kể cả trường hợp rỗng, chỉ số, dấu bằng và khóa trùng.
- [ ] Thứ tự hoặc cách phân hoạch của cây nền đã rõ.
- [ ] Đã nêu metadata tối thiểu cần để định hướng hoặc tổng hợp truy vấn.
- [ ] Có công thức tóm tắt **cây rỗng**, **nút lá**, **nút trong**.
- [ ] Hàm `pull` chỉ dùng dữ liệu tại nút và các cây con đã đúng; chi phí gộp được phân tích.
- [ ] Mọi thao tác chèn, xóa, thay trọng số/khóa, xoay hoặc split/merge có quy tắc bảo trì metadata.
- [ ] Nếu có lazy update: xác định phép áp dụng metadata, luật hợp thành tag, `push` và `pull`.
- [ ] Nếu metadata phụ thuộc thứ tự: không đổi thứ tự gộp; đã xử lý phép đảo đoạn nếu được hỗ trợ.
- [ ] Chứng minh tính đúng của thuật toán truy vấn dựa trên bất biến cây và metadata.
- [ ] Phân biệt **chi phí truy vấn**, **chi phí cập nhật**, **chi phí xây cây**, **bộ nhớ** và **chi phí kiểm thử**.
- [ ] Có validator độc lập và mô hình tham chiếu cho tình huống biên.
- [ ] Các giả thiết về số học, khóa, phân phối priority hoặc cân bằng đều được nêu rõ.

Một thiết kế tốt không nhất thiết lưu ít trường nhất, mà lưu **đúng thông tin đủ để trả lời các truy vấn quan trọng và vẫn duy trì được sau những cập nhật thật sự xảy ra**.

## 27. Tổng kết

**Chọn thông tin phụ cho cây tăng cường** là bài toán thiết kế **từ truy vấn và cập nhật trở về bất biến**, không phải chọn một trường từ danh sách có sẵn rồi hy vọng nó trả lời được mọi câu hỏi.

Một số nguyên tắc có thể tái sử dụng:

1. **Đếm và thứ hạng** cần `size`; nếu có khóa trùng phải quy định `size` đếm nút hay lần xuất hiện.
2. **Tổng trọng số** cần `subtree_sum`; tổng theo đoạn khóa kết hợp `subtree_sum` với thứ tự BST và các truy vấn tiền tố.
3. **Phát hiện một khoảng giao** có thể dùng `maxHigh` kết hợp với BST theo đầu trái; metadata chỉ tạo điều kiện cắt nhánh khi chứng minh đúng.
4. **Truy vấn phụ thuộc thứ tự** như tổng đoạn con lớn nhất hoặc dãy ngoặc có thể cần **nhiều trường liên kết bằng công thức gộp kết hợp**.
5. **Lazy update** chỉ hiệu quả khi ta biết cách áp dụng cập nhật lên metadata và hợp thành các thẻ mà không duyệt toàn bộ cây con.
6. **Tốc độ truy vấn phụ thuộc cả cấu trúc nền**. Metadata không tự cân bằng cây; những thao tác logarit cần giả thiết về chiều cao hoặc chiến lược cân bằng.
7. **Mọi thay đổi cấu trúc phải bảo trì bất biến từ dưới lên**, nhất là sau chèn/xóa và xoay.
8. **Kết quả đúng ở gốc chưa đủ**: phải giữ metadata đúng tại mọi nút có thể được một truy vấn tương lai sử dụng.

Công thức thiết kế tổng quát là:

\[
\boxed{
M(u)=combine(M(u.left),local(u),M(u.right)).
}
\]

Nhưng công thức ấy chỉ có giá trị khi `M` **thực sự đủ thông tin cho truy vấn**, `combine` có chi phí phù hợp, các phép cập nhật có quy tắc bảo trì đúng, và thuật toán truy vấn được chứng minh không bỏ sót kết quả.

Nắm được phương pháp này giúp người học chuyển từ **sử dụng một cấu trúc dữ liệu có sẵn** sang **thiết kế một cấu trúc đáp ứng đúng workload**: lựa chọn giữa mảng, danh sách liên kết, cây tìm kiếm, cây khoảng, cây theo vị trí, cây tổng hợp đoạn hoặc các thiết kế tăng cường khác trên cơ sở **bất biến, thời gian và bộ nhớ**.
