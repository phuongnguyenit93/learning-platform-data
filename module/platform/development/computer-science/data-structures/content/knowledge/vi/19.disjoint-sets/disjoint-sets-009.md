# Duy trì kích thước và thông tin tổng hợp của mỗi nhóm

Một hệ thống quản lý mạng có nhiều thiết bị. Mỗi thiết bị mang một giá trị đo, chẳng hạn lượng điện tiêu thụ, và một tập cờ biểu thị các khả năng được hỗ trợ. Các liên kết vô hướng lần lượt được thêm vào mạng. Người vận hành không chỉ hỏi “hai thiết bị có cùng thành phần liên thông không?” mà còn muốn biết **thành phần chứa thiết bị x có bao nhiêu thiết bị, tổng lượng điện là bao nhiêu, giá trị nhỏ nhất/lớn nhất là gì, và những khả năng nào xuất hiện trong nhóm**.

**Disjoint Set Union (DSU)**, còn gọi là **Union–Find**, có thể xử lý các yêu cầu đó bằng cách lưu một số thông tin **tại đại diện của mỗi nhóm**. Thay vì quét toàn bộ phần tử mỗi lần hỏi, ta cập nhật thông tin tổng hợp ngay khi hai nhóm được hợp.

Bài học thuộc chương **Tập hợp rời nhau** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**. Học phần rèn cách lựa chọn cấu trúc dữ liệu dựa trên các bất biến, thao tác và chi phí thời gian/bộ nhớ. Bài này tập trung vào **`size[root]` và metadata tổng hợp tại gốc**; giải thích quy tắc hợp, tính đúng đắn, cập nhật thuộc tính phần tử, giới hạn của từng phép tổng hợp, cách triển khai bằng mảng trong Python/C++, và những tình huống phải chọn một cấu trúc khác.

## 1. Mô hình bài toán và yêu cầu truy vấn

Xét tập phần tử có chỉ số:

\[
U=\{0,1,\ldots,n-1\}.
\]

Tại mỗi thời điểm, U được chia thành các nhóm `G₁,G₂,\ldots,G_c`, tạo thành một **phân hoạch**:

- Mỗi nhóm khác rỗng.
- Các nhóm khác nhau không giao nhau.
- Mỗi phần tử thuộc **đúng một nhóm** và hợp các nhóm bằng U.

Giả sử mỗi phần tử x có:

- Giá trị nguyên `value[x]`, có thể âm.
- Mặt nạ bit không âm `flags[x]`, mã hóa những thuộc tính Boolean của phần tử.

Ta cần các truy vấn như:

```text
same(x, y)             Hai phần tử cùng nhóm?
component_size(x)      Nhóm của x có bao nhiêu phần tử?
component_sum(x)       Tổng value của mọi phần tử trong nhóm x?
component_min(x)       Giá trị nhỏ nhất trong nhóm x?
component_max(x)       Giá trị lớn nhất trong nhóm x?
component_flags(x)     Phép OR các cờ của thành viên nhóm x?
component_count()      Hiện có bao nhiêu nhóm?
```

Ví dụ với ba phần tử có giá trị `5,-2,7`:

```text
Ban đầu:
{0} với sum = 5
{1} với sum = -2
{2} với sum = 7

Sau union(0,1):
{0,1} với size = 2, sum = 3

Sau union(1,2):
{0,1,2} với size = 3, sum = 10
```

**Nguyên tắc:** `union(1,2)` không chỉ gắn phần tử 2 với phần tử 1. Nó hợp **toàn bộ hai nhóm chứa chúng**, vì thế mọi dữ liệu tổng hợp của nhóm mới phải bao gồm tất cả thành viên của hai nhóm cũ.

## 2. Nhắc lại rừng cha và đại diện của nhóm

DSU biểu diễn mỗi nhóm bằng **một cây** trong rừng cha:

```text
parent[x] = cha của x
parent[root] = root
```

Ví dụ:

```text
       0                4
      / \               |
     1   2              5
         |
         3

Nhóm {0,1,2,3}     Nhóm {4,5}
```

Hàm `find(x)` đi theo liên kết cha cho đến gốc. Khi hai phần tử có cùng gốc, chúng cùng nhóm:

\[
\operatorname{same}(x,y)
\iff
\operatorname{find}(x)=\operatorname{find}(y).
\]

Trong ví dụ, `find(3)=0` và `find(5)=4`.

### Những bất biến không được phá

1. Mọi `parent[x]` trỏ tới phần tử hợp lệ.
2. Mỗi cây có đúng **một gốc tự trỏ**.
3. Đường cha từ mọi phần tử phải kết thúc ở gốc; không có chu trình cha dài từ hai nút.
4. Hai phần tử cùng nhóm khi và chỉ khi tìm được cùng gốc.
5. Mọi phần tử thuộc đúng một cây.
6. Một `union` thành công hợp **hai gốc khác nhau**, giảm số nhóm đúng một.

Khi thêm thông tin tổng hợp, ta phải duy trì các bất biến trên **và** các bất biến về giá trị lưu tại gốc.

## 3. Vì sao chỉ cần lưu metadata tại gốc?

Giả sử một nhóm có bốn phần tử:

```text
        0
       / \
      1   2
          |
          3

root = 0
```

Nếu mỗi lần hợp nhóm ta phải cập nhật `groupSize[x]` hoặc `groupSum[x]` **ở tất cả phần tử**, một phép hợp có thể tốn `O(n)` chỉ để sửa metadata.

Thay vào đó, DSU lưu metadata **đại diện cho cả cây ở gốc**:

```text
size[0]       = 4
total[0]      = tổng giá trị của {0,1,2,3}
minimum[0]    = giá trị nhỏ nhất trong {0,1,2,3}
maximum[0]    = giá trị lớn nhất trong {0,1,2,3}
flag_or[0]    = OR các cờ của {0,1,2,3}
```

Muốn lấy kích thước nhóm chứa 3:

```text
r = find(3)      // r = 0
answer = size[r]
```

**Không được mặc định `size[3]`, `total[3]` hoặc `minimum[3]` có giá trị đúng cho nhóm hiện tại.** Các vị trí không phải gốc có thể chứa dữ liệu từ lúc chúng còn là gốc, và thuật toán không có nghĩa vụ cập nhật chúng sau khi nối cây.

Quy tắc sử dụng:

\[
\operatorname{componentSize}(x)
=\operatorname{size}[\operatorname{find}(x)].
\]

Các truy vấn khác cũng đọc **qua gốc hiện tại**.

### Root là đại diện kỹ thuật, không phải ID nghiệp vụ bền vững

Khi một nhóm nhỏ hợp vào nhóm lớn, gốc của nhóm nhỏ có thể trở thành nút con. Giá trị `find(x)` thay đổi khi đó là điều bình thường. Nếu ứng dụng cần ID nhóm cố định trong cơ sở dữ liệu, phải lưu **ID nghiệp vụ riêng** và quy tắc hợp metadata phù hợp; không dùng số gốc như khóa ngoại vĩnh viễn.

## 4. Bất biến kích thước nhóm

Ta định nghĩa tại mỗi gốc r:

\[
\operatorname{size}[r]
=
\left|\{x\in U:\operatorname{find}(x)=r\}\right|.
\]

Nói cách khác, `size[r]` bằng **số thành viên thực của nhóm có gốc r**.

Ban đầu mỗi phần tử là một nhóm đơn:

```text
for x in 0..n-1:
    parent[x] = x
    size[x] = 1

components = n
```

Khi nối hai nhóm **khác nhau**, với gốc `ra` và `rb`, giả sử gốc mới là `ra`:

```text
parent[rb] = ra
size[ra] += size[rb]
components -= 1
```

Tổng kích thước tại các gốc hiện tại luôn bằng n:

\[
\boxed{\sum_{\mathrm{parent}[r]=r}\mathrm{size}[r]=n}.
\]

Đồng thời:

\[
\mathrm{components}
=
\#\{r:\mathrm{parent}[r]=r\}.
\]

Hai đẳng thức này rất hữu ích để **kiểm tra tính đúng đắn**.

### Lỗi điển hình: hợp trùng nhưng vẫn cộng size

Nếu `find(x)==find(y)`, hai phần tử đã cùng nhóm. Dòng:

```text
size[root] += size[root]
```

sẽ **nhân đôi kích thước trên giấy** trong khi thành viên thực tế không thay đổi. Vì vậy phải kiểm tra cùng gốc **trước** mọi cập nhật metadata.

## 5. Hợp theo kích thước: vừa giữ cây thấp vừa cập nhật size

**Union by size** dùng kích thước nhóm để chọn gốc:

```text
union(x, y):
    ra = find(x)
    rb = find(y)

    if ra == rb:
        return false

    if size[ra] < size[rb]:
        swap(ra, rb)

    parent[rb] = ra
    size[ra] += size[rb]
    components -= 1
    return true
```

Gốc của **nhóm lớn hơn hoặc bằng** được giữ. Như vậy một mảng `size` thực hiện **hai nhiệm vụ**:

1. Cung cấp kích thước nhóm để trả lời truy vấn.
2. Hạn chế chiều cao cây khi hợp nhóm.

### Tại sao độ cao được chặn `O(log n)`?

Khi một cây kích thước a bị gắn dưới cây kích thước b với `b≥a`, kích thước nhóm mới chứa mỗi nút của cây nhỏ ít nhất là:

\[
a+b\ge 2a.
\]

Mỗi lần độ sâu một nút tăng do phép hợp, kích thước nhóm chứa nó ít nhất **gấp đôi**. Vì nhóm không thể có hơn n thành viên, số lần tăng độ sâu của nút ấy không quá `⌊log₂ n⌋`.

Do đó, **chỉ union by size và chưa nén đường** đã bảo đảm mỗi `find` tốn `O(log n)` trong trường hợp xấu.

Nếu kết hợp **path compression** chuẩn, tổng chi phí chuỗi thao tác được chặn rất tốt theo **hàm nghịch đảo Ackermann** `α(n)`, thường diễn đạt là gần `O(α(n))` **khấu hao** trên mỗi thao tác. Đây không phải chặn `O(1)` worst-case cho từng lần gọi.

## 6. Thông tin tổng hợp: tổng, nhỏ nhất, lớn nhất và OR bit

Giả sử mỗi phần tử x có trọng số `value[x]` và mặt nạ `flags[x]`.

Tại mỗi gốc r ta lưu:

\[
\begin{aligned}
\mathrm{total}[r] &=
\sum_{x\in G_r}\mathrm{value}[x],\\
\mathrm{minimum}[r] &=
\min_{x\in G_r}\mathrm{value}[x],\\
\mathrm{maximum}[r] &=
\max_{x\in G_r}\mathrm{value}[x],\\
\mathrm{flagOr}[r] &=
\bigvee_{x\in G_r}\mathrm{flags}[x].
\end{aligned}
\]

Ký hiệu `∨` là **OR bit**. Ví dụ `0010₂ ∨ 1000₂ = 1010₂`.

Ban đầu, mỗi nhóm chỉ có một phần tử x:

```text
size[x]    = 1
total[x]   = value[x]
minimum[x] = value[x]
maximum[x] = value[x]
flagOr[x]  = flags[x]
```

Khi hợp hai nhóm khác nhau A và B thành C:

| Metadata | Công thức hợp |
|---|---|
| Kích thước | `size[C]=size[A]+size[B]` |
| Tổng | `total[C]=total[A]+total[B]` |
| Nhỏ nhất | `minimum[C]=min(minimum[A],minimum[B])` |
| Lớn nhất | `maximum[C]=max(maximum[A],maximum[B])` |
| OR cờ | `flagOr[C]=flagOr[A] \| flagOr[B]` |
| Số nhóm | `components -= 1` |

**Tại sao công thức đúng?** Hai nhóm trước phép hợp không giao nhau, nên số thành viên và tổng giá trị được **cộng**, còn min/max/OR của hợp hai nhóm có thể tính từ đúng hai kết quả tổng hợp cũ.

### Không lẫn kết quả OR với tổng cờ

Nếu hai phần tử đều có cờ `0010₂`:

```text
0010 OR 0010 = 0010
0010 +  0010 = 0100
```

OR diễn đạt “**có ít nhất một phần tử sở hữu khả năng này**”, còn cộng các mặt nạ như số nguyên không diễn đạt ý nghĩa đó. Hãy chọn phép tổng hợp dựa trên câu hỏi thực tế.

## 7. Ví dụ đầy đủ: bảy phần tử với trọng số và cờ

Ta dùng các dữ liệu ban đầu:

| Phần tử | `value[x]` | `flags[x]` dạng thập phân | Cờ bit |
|---:|---:|---:|---|
| 0 | 5 | 1 | `0001₂` |
| 1 | -2 | 2 | `0010₂` |
| 2 | 7 | 1 | `0001₂` |
| 3 | 4 | 4 | `0100₂` |
| 4 | 1 | 2 | `0010₂` |
| 5 | 8 | 8 | `1000₂` |
| 6 | -3 | 1 | `0001₂` |

```text
value  = [5,-2,7,4,1,8,-3]
flags  = [1,2,1,4,2,8,1]
parent = [0,1,2,3,4,5,6]
size   = [1,1,1,1,1,1,1]
components = 7
```

Thực hiện các phép hợp theo đúng thứ tự:

```text
union(0,1)
union(2,3)
union(1,2)
union(4,5)
union(3,5)
union(6,0)
```

Dùng union by size; khi kích thước bằng nhau, giữ gốc nhóm của đối số đầu sau khi đã gọi `find`.

### Bảng tổng hợp tại gốc sau từng bước

| Bước | Nhóm mới được hợp | Gốc mới | Size | Tổng | Min | Max | OR cờ | Số nhóm |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | Chưa hợp | — | — | — | — | — | — | 7 |
| 1 | `{0,1}` | 0 | 2 | 3 | -2 | 5 | 3 | 6 |
| 2 | `{2,3}` | 2 | 2 | 11 | 4 | 7 | 5 | 5 |
| 3 | `{0,1,2,3}` | 0 | 4 | 14 | -2 | 7 | 7 | 4 |
| 4 | `{4,5}` | 4 | 2 | 9 | 1 | 8 | 10 | 3 |
| 5 | `{0,1,2,3,4,5}` | 0 | 6 | 23 | -2 | 8 | 15 | 2 |
| 6 | `{0,1,2,3,4,5,6}` | 0 | 7 | 20 | -3 | 8 | 15 | 1 |

Giải thích:

- **Bước 1:** tổng `5+(-2)=3`, min `-2`, max `5`, cờ `0001₂ OR 0010₂ = 0011₂ = 3`.
- **Bước 3:** hợp hai nhóm cùng size 2. Tổng `3+11=14`; OR `3 OR 5=7`.
- **Bước 5:** hợp nhóm size 4 với nhóm size 2. Tổng `14+9=23`; OR `7 OR 10=15`.
- **Bước 6:** thêm phần tử 6 có trọng số `-3`. Tổng giảm còn `23-3=20`; min giảm thành `-3`. Cờ OR vẫn là 15 vì bit 1 đã có trong nhóm cũ.

### Mảng cha sau mỗi bước

Vì `find` có nén đường, mảng cha còn tùy thời điểm các nút được truy vấn. Với thứ tự nêu trên và **full path compression**, có thể thu được:

```text
Ban đầu:      [0,1,2,3,4,5,6]
union(0,1):   [0,0,2,3,4,5,6]
union(2,3):   [0,0,2,2,4,5,6]
union(1,2):   [0,0,0,2,4,5,6]
union(4,5):   [0,0,0,2,4,4,6]
union(3,5):   [0,0,0,0,0,4,6]
union(6,0):   [0,0,0,0,0,4,0]
```

Nút 5 vẫn có `parent[5]=4` sau bước cuối, nhưng `find(5)=0`. Để lấy tổng hoặc kích thước nhóm của 5, phải đọc `total[find(5)]` và `size[find(5)]` — **không** đọc metadata tại nút 5 hoặc nút 4.

## 8. Thuật toán hợp nhóm cùng lúc cập nhật tất cả metadata

Giả mã cho miền chỉ số liên tục:

```text
union_with_aggregates(x, y):
    ra = find(x)
    rb = find(y)

    if ra == rb:
        return false

    if size[ra] < size[rb]:
        swap(ra, rb)

    // ra là gốc mới; rb sẽ thành nút con.
    parent[rb] = ra

    size[ra]    += size[rb]
    total[ra]   += total[rb]
    minimum[ra]  = min(minimum[ra], minimum[rb])
    maximum[ra]  = max(maximum[ra], maximum[rb])
    flagOr[ra]  |= flagOr[rb]
    components  -= 1

    return true
```

**Tất cả kết quả dùng đúng metadata ở hai gốc trước phép hợp.** Vì `rb` không còn là gốc, không cần ghi kết quả mới vào `size[rb]` hoặc `total[rb]`.

### Tránh cập nhật hai lần

Nếu một phép hợp được gọi giữa hai phần tử đã thuộc cùng nhóm:

```text
ra = find(x)
rb = find(y)
ra == rb
```

phải **trả `false` ngay**. Nếu vẫn thực hiện `total[ra]+=total[rb]`, ta cộng một nhóm vào chính nó, khiến kết quả gấp đôi sai thực tế.

Đây là một trong những lỗi nguy hiểm nhất vì cấu trúc `parent` có thể vẫn đúng, nhưng thông tin tổng hợp đã bị sai âm thầm.

## 9. Chứng minh tính đúng đắn bằng quy nạp

Đặt nhóm do gốc r đại diện là:

\[
G_r=\{x\in U:\operatorname{find}(x)=r\}.
\]

Với các gốc hiện tại, ta muốn duy trì:

\[
\begin{aligned}
\mathrm{size}[r]&=|G_r|,\\
\mathrm{total}[r]&=\sum_{x\in G_r}\mathrm{value}[x],\\
\mathrm{minimum}[r]&=\min_{x\in G_r}\mathrm{value}[x],\\
\mathrm{maximum}[r]&=\max_{x\in G_r}\mathrm{value}[x],\\
\mathrm{flagOr}[r]&=\bigvee_{x\in G_r}\mathrm{flags}[x].
\end{aligned}
\]

### Bước cơ sở

Lúc khởi tạo, mỗi nhóm là `{x}`. Metadata được lấy trực tiếp từ `value[x]` và `flags[x]`, còn `size[x]=1`. Vì vậy các đẳng thức đều đúng.

### Bước tìm đại diện

`find(x)` không nén chỉ đọc cha; `find(x)` có path compression chỉ rút ngắn liên kết cha **trong cùng một cây**. Cả hai đều không đổi tập thành viên `G_r`. Do đó không cần sửa bất cứ metadata nào.

### Bước hợp trùng

Nếu `ra=rb`, hai phần tử đã thuộc một nhóm. Thuật toán trả về ngay, nên thành viên và metadata không đổi. Các đẳng thức vẫn đúng.

### Bước hợp hai nhóm khác nhau

Hai nhóm `G_{ra}` và `G_{rb}` không giao nhau. Khi nối gốc rb dưới ra, nhóm mới là:

\[
G_{\mathrm{new}}=G_{ra}\cup G_{rb}.
\]

Với hai tập không giao nhau:

\[
|G_{\mathrm{new}}|=|G_{ra}|+|G_{rb}|,
\]

và:

\[
\sum_{x\in G_{\mathrm{new}}}value[x]
=
\sum_{x\in G_{ra}}value[x]
+
\sum_{x\in G_{rb}}value[x].
\]

Tương tự, min và max của hợp hai tập là min/max của hai kết quả cũ; OR cờ cũng là OR của hai mặt nạ cũ. Thuật toán cập nhật đúng các công thức đó ở **gốc mới**.

Các nhóm khác không đổi. Số nhóm giảm đúng một. Bằng quy nạp, bất biến tổng hợp được duy trì sau mọi chuỗi thao tác hợp lệ.

## 10. Từ nhiều ví dụ tới quy tắc tổng hợp tổng quát

Nhiều metadata có thể được mô tả bằng một phép kết hợp:

\[
A(G_1\cup G_2)=A(G_1)\ \otimes\ A(G_2)
\]

khi `G_1` và `G_2` **không giao nhau**.

Một phép tổng hợp thích hợp cho DSU thường có các tính chất:

- **Kết hợp (associative):** `(a⊗b)⊗c=a⊗(b⊗c)`. Kết quả không phụ thuộc cách chia các lần hợp.
- **Giao hoán (commutative):** `a⊗b=b⊗a` nếu nhóm không có thứ tự. Kết quả không phụ thuộc gốc nào được giữ.
- **Có phần tử đơn vị (identity)** nếu cần tổng hợp tập rỗng hoặc muốn dùng một giá trị khởi đầu.
- **Tính được với chi phí phù hợp**: mỗi lần hợp metadata không nên quá đắt so với yêu cầu hiệu năng.

Đại số gọi một tập giá trị với phép kết hợp và phần tử đơn vị là **monoid**. Nếu thêm tính giao hoán, đó là **monoid giao hoán**.

### Bảng ví dụ

| Đại lượng nhóm | `a⊗b` | Giá trị đơn vị khi có | Chú ý |
|---|---|---|---|
| Đếm phần tử | `a+b` | 0 | Mỗi phần tử đóng góp 1 |
| Tổng trọng số | `a+b` | 0 | Cẩn thận tràn số và số thực |
| Giá trị nhỏ nhất | `min(a,b)` | `+∞` | Mỗi nhóm DSU đang dùng không rỗng |
| Giá trị lớn nhất | `max(a,b)` | `−∞` | Cần quy định cách xử lý NaN nếu dùng số thực |
| OR mặt nạ bit | `a \| b` | 0 | Cho biết bit nào xuất hiện ít nhất một lần |
| AND mặt nạ bit | `a & b` | Mặt nạ toàn bit 1 | Cần xác định **độ rộng bit** |
| XOR mặt nạ bit | `a ^ b` | 0 | Theo một độ rộng bit được quy định |
| Tích số | `a·b` | 1 | Dễ tràn số hoặc rơi về 0 |

**Lưu ý:** `min` và `max` trên nhóm không rỗng không bắt buộc phải biểu diễn giá trị `±∞` trong mã thực tế: khi khởi tạo nhóm đơn, lấy chính giá trị của phần tử; khi hợp nhóm, gọi `min`/`max` trên hai kết quả.

### Vì sao giao hoán quan trọng?

Nếu metadata là **chuỗi ký tự** và phép hợp là nối chuỗi, `"ab"+"cd"` khác `"cd"+"ab"`. Trong DSU, `union(x,y)` và `union(y,x)` phải tạo cùng **phân hoạch logic**, nhưng quy tắc union by size có thể chọn gốc khác nhau, khiến kết quả nối chuỗi khác thứ tự.

Nếu ứng dụng đòi một thứ tự cụ thể, ví dụ liệt kê thành viên theo ID tăng dần, **không thể mặc định dùng phép nối chuỗi như một tổng hợp vô thứ tự**. Phải xác định quy tắc sắp xếp hoặc cấu trúc duy trì thứ tự và tính thêm chi phí đó.

## 11. Cài đặt Python: tổng hợp cố định tại gốc

Ví dụ đầy đủ dưới đây dùng mảng cho các ID liên tục `0..n-1`. Mỗi phần tử có `value[x]` (số nguyên có dấu) và `flags[x]` (mặt nạ bit không âm).

Để bài minh bạch, **thuộc tính của từng phần tử được coi là cố định trong lớp này**. Sau `union` chỉ metadata tại các gốc thay đổi; lớp chưa cung cấp hàm cập nhật `value[x]` hay `flags[x]`.

```python
class AggregateDSU:
    def __init__(self, values: list[int], flags: list[int]):
        if len(values) != len(flags):
            raise ValueError("values và flags phải cùng số phần tử")

        for v in values:
            if not isinstance(v, int) or isinstance(v, bool):
                raise TypeError("values chỉ chứa số nguyên")

        for mask in flags:
            if not isinstance(mask, int) or isinstance(mask, bool):
                raise TypeError("flags chỉ chứa số nguyên")
            if mask < 0:
                raise ValueError("Mặt nạ flags phải không âm")

        n = len(values)

        self.parent = list(range(n))
        self.size = [1] * n
        self.total = values.copy()
        self.minimum = values.copy()
        self.maximum = values.copy()
        self.flag_or = flags.copy()
        self.components = n

    def _check(self, x: int) -> None:
        if not isinstance(x, int) or isinstance(x, bool):
            raise TypeError("Chỉ số phải là số nguyên")
        if not 0 <= x < len(self.parent):
            raise IndexError("Chỉ số ngoài miền")

    def find(self, x: int) -> int:
        self._check(x)

        root = x
        while self.parent[root] != root:
            root = self.parent[root]

        # Full path compression, không đổi metadata.
        while self.parent[x] != x:
            old_parent = self.parent[x]
            self.parent[x] = root
            x = old_parent

        return root

    def union(self, x: int, y: int) -> bool:
        ra = self.find(x)
        rb = self.find(y)

        if ra == rb:
            return False

        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra

        self.parent[rb] = ra
        self.size[ra] += self.size[rb]
        self.total[ra] += self.total[rb]
        self.minimum[ra] = min(self.minimum[ra], self.minimum[rb])
        self.maximum[ra] = max(self.maximum[ra], self.maximum[rb])
        self.flag_or[ra] |= self.flag_or[rb]
        self.components -= 1
        return True

    def same(self, x: int, y: int) -> bool:
        return self.find(x) == self.find(y)

    def summary(self, x: int) -> dict[str, int]:
        r = self.find(x)
        return {
            "root": r,
            "size": self.size[r],
            "total": self.total[r],
            "minimum": self.minimum[r],
            "maximum": self.maximum[r],
            "flags": self.flag_or[r],
        }

    def component_count(self) -> int:
        return self.components


weights = [5, -2, 7, 4, 1, 8, -3]
masks = [1, 2, 1, 4, 2, 8, 1]
dsu = AggregateDSU(weights, masks)

assert dsu.component_count() == 7

assert dsu.union(0, 1)
assert dsu.union(2, 3)
assert dsu.union(1, 2)

assert dsu.summary(3) == {
    "root": 0,
    "size": 4,
    "total": 14,
    "minimum": -2,
    "maximum": 7,
    "flags": 7,
}

assert dsu.union(4, 5)
assert dsu.union(3, 5)
assert dsu.component_count() == 2

assert dsu.union(6, 0)
assert dsu.component_count() == 1

assert dsu.summary(5) == {
    "root": 0,
    "size": 7,
    "total": 20,
    "minimum": -3,
    "maximum": 8,
    "flags": 15,
}

# Không có thêm phần tử nào được hợp.
assert dsu.union(1, 4) is False
assert dsu.component_count() == 1
assert dsu.summary(6)["total"] == 20
```

### Các quyết định thiết kế trong lớp

- `find` thực hiện **nén đường đi** nhưng không chỉnh `total`, `minimum`, `maximum` hay `flag_or`, vì phân hoạch không thay đổi.
- `union` chỉ cập nhật metadata **sau khi** xác định hai gốc khác nhau.
- `summary(x)` luôn gọi `find(x)` trước, nên trả kết quả **ở gốc hiện tại**.
- Các mảng tổng hợp được **sao chép** từ dữ liệu đầu vào, tránh sửa ngoài ý muốn nếu người gọi thay đổi danh sách gốc.
- `flags` bị giới hạn là số nguyên không âm để OR bit có ý nghĩa rõ ràng trong ví dụ.
- Nếu `n=0`, `components=0` và không có phần tử hợp lệ để truy vấn `summary`; việc gọi với bất kỳ chỉ số nào sẽ bị từ chối.

Hàm này dành cho **đơn luồng**; `find` có nén đường ghi vào `parent`. Không mặc định các lần truy vấn đồng thời trên cùng đối tượng là thread-safe.

## 12. C++17: lưu tổng, min/max và OR trong các vector

Khi đầu vào là các chỉ số liên tục, `std::vector` là cách tự nhiên để lưu `parent` và metadata. Mã C++17 dưới đây dùng `std::int64_t` cho trọng số/tổng và `std::uint32_t` cho mặt nạ bit.

```cpp
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <vector>

class AggregateDSU {
public:
    AggregateDSU(
        const std::vector<std::int64_t>& values,
        const std::vector<std::uint32_t>& flags
    )
        : parent_(values.size()),
          size_(values.size(), 1),
          total_(values),
          minimum_(values),
          maximum_(values),
          flag_or_(flags),
          components_(values.size()) {

        if (values.size() != flags.size()) {
            throw std::invalid_argument("values/flags size mismatch");
        }
        std::iota(parent_.begin(), parent_.end(), std::size_t{0});
    }

    std::size_t find(std::size_t x) {
        if (x >= parent_.size()) {
            throw std::out_of_range("DSU index out of range");
        }

        // Path halving.
        while (parent_[x] != x) {
            parent_[x] = parent_[parent_[x]];
            x = parent_[x];
        }
        return x;
    }

    bool unite(std::size_t x, std::size_t y) {
        std::size_t ra = find(x);
        std::size_t rb = find(y);

        if (ra == rb) return false;

        if (size_[ra] < size_[rb]) {
            std::swap(ra, rb);
        }

        parent_[rb] = ra;
        size_[ra] += size_[rb];
        total_[ra] += total_[rb];
        minimum_[ra] = std::min(minimum_[ra], minimum_[rb]);
        maximum_[ra] = std::max(maximum_[ra], maximum_[rb]);
        flag_or_[ra] |= flag_or_[rb];
        --components_;
        return true;
    }

    std::size_t group_size(std::size_t x) {
        return size_[find(x)];
    }

    std::int64_t group_total(std::size_t x) {
        return total_[find(x)];
    }

    std::int64_t group_minimum(std::size_t x) {
        return minimum_[find(x)];
    }

    std::int64_t group_maximum(std::size_t x) {
        return maximum_[find(x)];
    }

    std::uint32_t group_flags(std::size_t x) {
        return flag_or_[find(x)];
    }

    std::size_t component_count() const {
        return components_;
    }

private:
    std::vector<std::size_t> parent_;
    std::vector<std::size_t> size_;
    std::vector<std::int64_t> total_;
    std::vector<std::int64_t> minimum_;
    std::vector<std::int64_t> maximum_;
    std::vector<std::uint32_t> flag_or_;
    std::size_t components_;
};

int main() {
    AggregateDSU dsu(
        {5, -2, 7, 4, 1, 8, -3},
        {1u, 2u, 1u, 4u, 2u, 8u, 1u}
    );

    dsu.unite(0, 1);
    dsu.unite(2, 3);
    dsu.unite(1, 2);

    std::cout << dsu.group_size(3) << '\n';    // 4
    std::cout << dsu.group_total(3) << '\n';   // 14
    std::cout << dsu.group_minimum(3) << '\n'; // -2

    dsu.unite(4, 5);
    dsu.unite(3, 5);
    dsu.unite(6, 0);

    std::cout << dsu.group_size(5) << '\n';    // 7
    std::cout << dsu.group_total(5) << '\n';   // 20
    std::cout << dsu.group_flags(5) << '\n';   // 15
    std::cout << dsu.component_count() << '\n'; // 1
}
```

### Các giới hạn của ví dụ C++

- `std::int64_t` có phạm vi hữu hạn. Nếu tổng vượt miền biểu diễn, phép cộng số nguyên có dấu có thể **tràn và gây hành vi không xác định** trong C++. Phải kiểm tra giới hạn hoặc chọn kiểu số/phương pháp xử lý phù hợp với bài toán.
- Mặt nạ `std::uint32_t` có đúng 32 bit; nếu cần nhiều cờ hơn, phải dùng nhiều từ máy hoặc một bitset thích hợp.
- Lớp chỉ lưu dữ liệu tổng hợp từ **giá trị tĩnh** của từng phần tử. Nếu giá trị thay đổi, metadata phải được cập nhật theo một hợp đồng khác.
- Các hàm truy vấn gọi `find` có **path halving**, có thể sửa `parent_`, nên không phải truy vấn chỉ đọc về mặt bộ nhớ.

Mã Python dùng full compression, C++ dùng halving; vì vậy mảng `parent` nội bộ có thể khác, nhưng **size, sum, min, max, OR và số nhóm** phải khớp theo cùng chuỗi hợp.

## 13. Truy vấn trung bình, đếm và tỉ lệ từ metadata hiện có

Khi đã có `size[root]` và `total[root]`, có thể tính **trung bình số học** của thuộc tính:

\[
\operatorname{average}(G)
=\frac{\operatorname{total}(G)}{|G|}.
\]

Ví dụ nhóm `{0,1,2,3}` trong phần 7 có:

\[
\operatorname{average}
=\frac{14}{4}=3.5.
\]

Mỗi nhóm DSU đang quản lý đều không rỗng, nên `size[root]≥1`. Không chia cho 0 khi truy vấn phần tử hợp lệ.

### Trung bình không cần lưu một trường metadata riêng

Nếu lưu cả trung bình và kích thước, không được tính trung bình sau hợp bằng công thức sai:

```text
averageNew = (averageA + averageB) / 2   // Sai nếu sizeA != sizeB.
```

Công thức đúng là **trung bình có trọng số theo số thành viên**:

\[
\overline{x}_{\mathrm{new}}
=
\frac{size_A\cdot \overline{x}_A
      +size_B\cdot \overline{x}_B}
     {size_A+size_B}.
\]

Dùng `total/size` trực tiếp thường rõ ràng hơn, miễn là chọn kiểu số và quy tắc làm tròn phù hợp.

### Tỉ lệ thuộc tính Boolean

Nếu muốn biết tỷ lệ phần tử thỏa điều kiện, lưu **số lượng phần tử thỏa điều kiện** tại mỗi gốc. Khi hợp hai nhóm, cộng hai số đếm; tỷ lệ là:

\[
\mathrm{ratio}
=\frac{\mathrm{matchingCount}[root]}{\mathrm{size}[root]}.
\]

**Không** dùng OR bit để suy ra có bao nhiêu phần tử mang cờ: OR chỉ trả lời “cờ này có xuất hiện ở ít nhất một thành viên không?”.

## 14. Dữ liệu phần tử có thể thay đổi: cập nhật tổng bằng delta

Đến đây các ví dụ giả định `value[x]` và `flags[x]` **cố định**. Nếu một thiết bị cập nhật số đo, liệu DSU có hỗ trợ không?

Đối với **tổng**, ta có một phép cập nhật điểm đơn giản:

1. Tìm gốc hiện tại `r=find(x)`.
2. Tính `delta=newValue-oldValue`.
3. Cập nhật `total[r]+=delta`.
4. Lưu `value[x]=newValue`.

Vì số thành viên không đổi nên **không** sửa `size` hoặc `components`.

### Cài đặt Python riêng cho tổng động

```python
class DynamicSumDSU:
    def __init__(self, values: list[int]):
        self.value = values.copy()
        n = len(values)
        self.parent = list(range(n))
        self.size = [1] * n
        self.total = values.copy()
        self.components = n

    def find(self, x: int) -> int:
        if not isinstance(x, int) or isinstance(x, bool):
            raise TypeError("Chỉ số phải là số nguyên")
        if not 0 <= x < len(self.parent):
            raise IndexError("Chỉ số ngoài miền")

        root = x
        while self.parent[root] != root:
            root = self.parent[root]

        while self.parent[x] != x:
            old_parent = self.parent[x]
            self.parent[x] = root
            x = old_parent

        return root

    def union(self, x: int, y: int) -> bool:
        ra = self.find(x)
        rb = self.find(y)

        if ra == rb:
            return False

        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra

        self.parent[rb] = ra
        self.size[ra] += self.size[rb]
        self.total[ra] += self.total[rb]
        self.components -= 1
        return True

    def set_value(self, x: int, new_value: int) -> None:
        if not isinstance(new_value, int) or isinstance(new_value, bool):
            raise TypeError("Giá trị mới phải là số nguyên")

        root = self.find(x)
        self.total[root] += new_value - self.value[x]
        self.value[x] = new_value

    def group_sum(self, x: int) -> int:
        return self.total[self.find(x)]


d = DynamicSumDSU([5, -2, 7])

assert d.union(0, 1)
assert d.group_sum(1) == 3

d.set_value(1, 4)    # Delta = 4 - (-2) = 6.
assert d.group_sum(0) == 9

assert d.union(1, 2)
assert d.group_sum(2) == 16
assert d.components == 1

d.set_value(2, -1)   # Delta = -1 - 7 = -8.
assert d.group_sum(0) == 8
```

**Điều kiện quan trọng:** giữ `value[x]` của từng phần tử để biết **giá trị cũ**. Nếu chỉ lưu tổng tại gốc mà không lưu giá trị cũ (và không được cung cấp bởi hệ thống bên ngoài), không thể tính delta một cách đúng đắn.

### Vậy còn XOR?

Với XOR trên các mặt nạ bit có độ rộng xác định:

\[
X_{\mathrm{new}}=
X_{\mathrm{old}}\oplus oldMask\oplus newMask.
\]

Phép XOR **tự triệt tiêu** khi cùng một giá trị xuất hiện hai lần, nên có thể cập nhật point value bằng cách bỏ giá trị cũ qua XOR rồi thêm giá trị mới. Phải lưu mặt nạ cũ và nhất quán về độ rộng bit.

## 15. Vì sao min, max và OR khó cập nhật khi thuộc tính thay đổi?

Không phải phép tổng hợp nào cũng có “phép trừ” để gỡ đóng góp cũ.

Giả sử:

```text
Nhóm G = {0,1,2}
value  = [2,5,9]
minimum[G] = 2
```

Nếu đổi `value[0]` từ 2 thành 10, min mới là **5**, không phải 10. Chỉ biết `minimum[G]=2` và giá trị cũ/mới của phần tử 0 **không đủ** để biết 5 là phần tử nhỏ thứ hai.

Tương tự, với OR bit:

```text
flags = [0010, 0010, 1000]
OR ban đầu = 1010
```

Nếu phần tử đầu đổi từ `0010` thành `0000`, OR của nhóm **vẫn là 1010** vì phần tử thứ hai vẫn mang bit `0010`. Nhưng nếu cả hai phần tử đầu đều bỏ bit ấy, OR mới là `1000`.

Một phép tính đơn giản như:

```text
newOR = oldOR & ~oldMask | newMask  // Không đúng tổng quát.
```

có thể xóa bit mà **những phần tử khác vẫn sở hữu**.

### Hướng xử lý đúng

- **Thuộc tính tĩnh, chỉ hợp nhóm:** dùng min/max/OR gộp `O(1)` như ở trên.
- **Có cập nhật ít, nhóm nhỏ:** quét lại thành viên hoặc toàn miền khi thật sự cần, chấp nhận chi phí.
- **Cần min/max động:** duy trì cấu trúc bổ sung như multiset, heap kèm xử lý giá trị cũ, hoặc cây cân bằng; phân tích chi phí hợp và cập nhật của cấu trúc đó.
- **Cần OR bit động:** duy trì **số phần tử đang bật từng bit** trong nhóm; OR có bit b bật khi bộ đếm bit b lớn hơn 0. Với B bit, có thể cần `O(B)` bộ nhớ trên mỗi nhóm hiện hoạt và xử lý gộp/cập nhật theo B.

Không nên đưa một hàm `set_value` vào lớp vừa lưu min/max tĩnh nhưng chỉ cập nhật tổng: khi đó API sẽ âm thầm trả kết quả min/max cũ và không còn đúng.

## 16. Metadata của đỉnh khác metadata của cạnh

Trong bài toán đồ thị, cần phân biệt:

- **Tổng thuộc tính của các đỉnh** trong thành phần.
- **Tổng thuộc tính của các cạnh** nằm trong thành phần.

Hai loại này có quy tắc cập nhật **khác nhau**.

Nếu mỗi đỉnh v có trọng số `value[v]`, một cạnh `(u,v)` được thêm khi hai đầu **đã cùng thành phần** không làm thay đổi thành viên, nên tổng trọng số đỉnh **không đổi**.

Nhưng nếu cần đếm **tất cả cạnh đã thêm** trong thành phần (kể cả cạnh tạo chu trình, cạnh song song hoặc khuyên), thì **mỗi lần thêm cạnh đều tăng số cạnh**, ngay cả khi phép union trả `false`.

### Ví dụ thêm cạnh tạo chu trình

```text
Đỉnh: {0,1,2}
Ban đầu: ba nhóm đơn, mỗi nhóm có 0 cạnh.

Thêm (0,1) → hợp thành {0,1}, có 1 cạnh.
Thêm (1,2) → hợp thành {0,1,2}, có 2 cạnh.
Thêm (0,2) → hai đầu đã cùng nhóm;
             không hợp nhóm mới, nhưng có 3 cạnh.
```

Nếu chỉ tăng `edgeCount` khi `union` thành công, hệ thống sẽ **bỏ sót cạnh (0,2)**.

### Giả mã duy trì số cạnh trong thành phần

```text
add_edge(u, v):
    ru = find(u)
    rv = find(v)

    if ru == rv:
        edgeCount[ru] += 1
        return false       // Không hợp hai nhóm mới.

    if size[ru] < size[rv]:
        swap(ru, rv)

    parent[rv] = ru
    size[ru] += size[rv]
    edgeCount[ru] += edgeCount[rv] + 1
    components -= 1
    return true
```

Khi hai thành phần khác nhau được nối bởi **một cạnh mới**, tổng số cạnh của thành phần mới bằng tổng cạnh của hai thành phần cũ **cộng 1**.

Nếu hai đầu đã trong cùng thành phần, phép hợp không cần thực hiện, nhưng `edgeCount` vẫn **cộng 1** vì có một cạnh thực sự vừa được thêm.

**Bất biến:** `edgeCount[root]` là số cạnh đã thêm có cả hai đầu thuộc nhóm hiện tại.

Với đồ thị vô hướng liên thông không xét hướng, nếu thành phần có v đỉnh và e cạnh thì:

- `e=v-1` khi thành phần là cây (không chu trình).
- `e≥v` khi thành phần có chu trình (bao gồm chu trình do cạnh song song hoặc khuyên theo quy ước đồ thị đa cạnh).

Không được lẫn **cạnh của đồ thị gốc** với **liên kết `parent` của DSU**; rừng cha chỉ là cấu trúc đại diện nội bộ.

## 17. Liệt kê thành viên nhóm không phải truy vấn O(1)

Metadata gốc trả lời tổng, min/max và size rất nhanh, nhưng **không lưu sẵn danh sách từng thành viên**.

Nếu chỉ có mảng `parent`, cách đơn giản để liệt kê thành viên nhóm chứa x:

```text
r = find(x)

members = []
for v from 0 to n-1:
    if find(v) == r:
        members.append(v)
```

Cách này phải kiểm tra **toàn bộ n phần tử**, nên có ít nhất `Ω(n)` thời gian, chưa kể công tìm gốc. Với DSU tối ưu, có thể mô tả chi phí gần `O(nα(n))` cho các phép tìm trên chuỗi được xét, cộng chi phí tạo danh sách; mỗi lần gọi riêng còn phụ thuộc trạng thái các cây.

Nếu ứng dụng thường xuyên yêu cầu danh sách thành viên, có thể lưu metadata bổ sung:

- Danh sách thành viên ở mỗi gốc, gộp danh sách nhỏ vào danh sách lớn.
- Danh sách liên kết với thao tác nối nếu chấp nhận đánh đổi thao tác khác.
- Cấu trúc ánh xạ hoặc tập hợp riêng tùy yêu cầu tra cứu.

Nhưng cần **tính chi phí gộp danh sách**: nếu di chuyển từng thành viên khi hợp, phép union không còn chi phí bổ sung `O(1)`. Với chiến lược gộp tập nhỏ vào tập lớn, một phần tử thường chỉ bị di chuyển `O(log n)` lần, nhưng tổng chi phí còn phụ thuộc kiểu tập và thao tác chèn.

## 18. Không phải metadata nào cũng gộp với chi phí hằng số

Bài toán chỉ cần số thành viên, tổng, min/max trên số có kích thước cố định hoặc OR trên **một từ máy** thường có phép gộp `O(1)`.

Nhưng có thể gặp metadata lớn:

| Metadata | Vấn đề khi hợp nhóm |
|---|---|
| Bitset B bit trên nhiều từ | OR hai bitset có thể tốn `O(B/w)` với từ máy w bit |
| Tập các giá trị phân biệt | Cần gộp set; tốn công theo số phần tử được chuyển |
| Danh sách các thành viên | Có thể cần sao chép hoặc nối cấu trúc |
| Histogram nhiều nhãn | Cần cộng nhiều bộ đếm hoặc gộp map |
| Median/percentile chính xác | Không thể suy từ mỗi trung bình/tổng/min/max; cần phân phối hoặc cấu trúc thứ tự |
| Chuỗi có thứ tự | Kết quả phụ thuộc thứ tự ghép, không phải tổng hợp nhóm giao hoán |

Nếu chi phí gộp metadata là `C`, một phép union thành công có chi phí:

\[
T_{\mathrm{union}}
=T_{\mathrm{find}}(x)+T_{\mathrm{find}}(y)+O(1)+C.
\]

Với DSU dùng union by size và path compression, phần tìm gốc có chặn khấu hao gần `α(n)`, **nhưng chi phí C có thể chi phối tổng thời gian**.

Ví dụ nếu một nhóm lưu bitset có hàng triệu bit và mỗi lần hợp phải OR toàn bộ vùng nhớ, không được báo rằng **toàn bộ phép hợp** luôn gần hằng số chỉ vì `find` nhanh.

## 19. Trường hợp có thêm phần tử mới khi đang chạy

Khi miền `0..n-1` đã cố định, khởi tạo `parent[x]=x` và metadata cho mọi x mất `O(n)`.

Nếu ứng dụng cho phép thêm phần tử mới động, phải đồng thời thêm mục vào **tất cả mảng**:

```text
add(value, flags):
    x = parent.length

    parent.append(x)
    size.append(1)
    total.append(value)
    minimum.append(value)
    maximum.append(value)
    flagOr.append(flags)

    components += 1
    return x
```

**Không được** thêm vào `parent` nhưng quên một mảng metadata, vì các chỉ số sẽ lệch và truy vấn cho phần tử mới bị sai.

Cũng không được gọi lại `make_set(x)` theo kiểu `parent[x]=x` với một phần tử đã tồn tại trong nhóm: thao tác ấy có thể tách x khỏi cây cũ mà không cập nhật size và các tổng hợp.

Nếu ID bên ngoài là chuỗi hoặc số nguyên rất thưa, có thể dùng **hash map `externalID→index`** rồi giữ DSU dạng mảng bên trong. Chi phí ánh xạ và cấp phát cần tính riêng; không mặc định đọc hash map có worst-case `O(1)` cho mọi đầu vào.

## 20. Độ phức tạp thời gian và bộ nhớ

Đặt:

- `n` là số phần tử.
- `m` là số phép tìm/hợp/truy vấn tổng hợp trong một chuỗi.
- `h` là chiều cao cây tại thời điểm xét.
- `α` là hàm **Ackermann ngược** tăng cực kỳ chậm.
- `k` là số trường metadata có thể gộp bằng thao tác hằng số.

Với `k` cố định như `size, total, min, max, flagOr`:

| Thao tác | Union by size, chưa nén | Union by size + compression |
|---|---|---|
| Khởi tạo n nhóm | `Θ(nk)` để khởi tạo tất cả trường | `Θ(nk)` |
| `find(x)` | `O(log n)` worst-case | `O(log n)` worst-case một lần; gần `O(α(n))` khấu hao |
| `union(x,y)` | `O(log n+k)` worst-case | `O(α(n)+k)` khấu hao |
| `summary(x)` trả k trường | `O(log n+k)` worst-case | `O(α(n)+k)` khấu hao |
| `component_count()` | `O(1)` | `O(1)` |
| Bộ nhớ metadata + parent | `O(nk)` | `O(nk)` |

Với **k là hằng số**, ta thường đơn giản hóa bộ nhớ thành **`O(n)`** và một phép union/summary thành **gần `O(α(n))` khấu hao**.

### Lưu ý về số trường k

Nếu bài toán đòi hàng trăm hoặc hàng nghìn bộ đếm trên mỗi nhóm, k không còn là hằng số nhỏ. Khi ấy:

- Khởi tạo có thể cần `O(nk)` thời gian/bộ nhớ.
- Mỗi lần hợp có thể cần `O(k)` phép cộng hoặc kết hợp.
- Trả về toàn bộ k trường cũng cần `Ω(k)` thời gian chỉ để tạo kết quả.

**Độ phức tạp DSU cho tìm gốc không xóa được chi phí metadata.**

### Chi phí tổng của chuỗi thao tác

Một cách viết dễ dùng khi metadata gộp `O(k)` và có `n` phần tử ban đầu là:

\[
O\bigl(nk+m\alpha(n)+u\,k\bigr),
\]

trong đó u là số **phép hợp thành công**, theo cách trình bày khấu hao thông dụng với các điều kiện phù hợp. Với `k=O(1)` và `u≤n-1` khi không thêm phần tử mới, biểu thức rút gọn rất thuận lợi.

Với số thực, tổng hợp min/max, bảng băm hoặc cấu trúc phức tạp, cần phân tích thêm **chi phí số học, cấp phát và gộp dữ liệu** theo đúng mô hình thực tế.

## 21. Bài toán ứng dụng: tổng trọng số từng thành phần liên thông

Cho đồ thị **vô hướng** có trọng số đặt **trên đỉnh**. Ban đầu chưa có cạnh, mỗi đỉnh là một nhóm. Khi thêm cạnh `(u,v)`, ta gọi `union(u,v)`.

Câu hỏi:

> “Thành phần liên thông chứa đỉnh x hiện có bao nhiêu đỉnh và tổng trọng số các đỉnh bằng bao nhiêu?”

Giải pháp:

```text
Khởi tạo:
  parent[x] = x
  size[x] = 1
  total[x] = value[x]

Mỗi lần thêm cạnh (u,v):
  union(u,v)      // Chỉ hợp khi hai gốc khác nhau.

Trả lời query(x):
  r = find(x)
  return (size[r], total[r])
```

Với `V` đỉnh và `E` cạnh thêm, phần DSU có chi phí gần:

\[
O(V+E\alpha(V))
\]

trong cách diễn đạt khấu hao phổ biến khi metadata gộp hằng số. Nếu còn `Q` truy vấn, cộng thêm khoảng `O(Q\alpha(V))` cho phần DSU.

**Tình huống sử dụng:** theo dõi tổng tiêu thụ điện trong mỗi vùng kết nối, số tài khoản trong một cụm, tổng dung lượng của các máy trong cùng mạng hoặc số thiết bị có một tính năng ở từng thành phần.

### Kruskal và tổng trọng số thành phần

Trong thuật toán **Kruskal**, DSU dùng để xác định hai đầu cạnh có thuộc hai thành phần khác nhau hay không, tránh tạo chu trình trong rừng cạnh đã chọn.

Nếu còn muốn tổng trọng số **đỉnh** của từng thành phần tại mỗi bước, có thể gắn thêm `total[root]` như bài này mà không đổi logic chọn cạnh.

Nhưng **trọng số cạnh của cây khung** là một đại lượng khác: tổng trọng số những cạnh đã **chấp nhận** phải được cộng theo các cạnh Kruskal chọn, chứ không tự lấy từ `total[root]` của đỉnh.

## 22. Lỗi thường gặp và cách phòng tránh

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Đọc `size[x]` khi x không phải gốc | Có thể là kích thước nhóm cũ | `size[find(x)]` |
| Đọc `total[x]` ở nút con | Tổng đã lỗi thời | `total[find(x)]` |
| Cộng metadata khi `ra==rb` | Đếm cùng nhóm hai lần | Trả `false` trước khi gộp |
| Đổi `parent[y]=x` thay vì gắn hai gốc | Có thể tách nhầm nhóm cũ | Luôn `find` hai gốc |
| Chỉ cộng size mà quên total/min/max/flags | Metadata các trường không nhất quán | Gộp toàn bộ trong một hàm union |
| Gộp metadata ở gốc sẽ thành con | Truy vấn sau hợp có thể đọc thiếu dữ liệu | Cập nhật tại gốc được giữ |
| Xem OR bit là số phần tử mang cờ | OR chỉ nói có/không | Lưu bộ đếm cờ riêng |
| Tính trung bình mới bằng trung bình của hai average | Sai với hai nhóm kích thước khác nhau | Dùng total/size hoặc trung bình có trọng số |
| Thay value của đỉnh mà không cập nhật total | Tổng nhóm bị cũ | Lưu giá trị cũ và cộng delta |
| Thay phần tử đang là min mà chỉ sửa min bằng giá trị mới | Không biết giá trị nhỏ thứ hai | Dùng cấu trúc phụ hoặc quét lại |
| Bỏ qua cạnh tạo chu trình khi đếm tất cả cạnh | Thiếu edgeCount dù union trùng | Cộng cạnh cả khi hai đầu cùng gốc |
| Coi root là mã nhóm cố định | Có thể đổi đại diện | Tách định danh nghiệp vụ |
| Bỏ qua tràn số khi cộng total | Có thể gây sai hoặc lỗi kiểu số | Chọn kiểu, kiểm tra giới hạn |
| Gộp dữ liệu lớn nhưng vẫn báo union `O(α(n))` | Bỏ sót chi phí metadata | Cộng chi phí kết hợp metadata |
| Nén đường rồi cập nhật size lần nữa | Đếm trùng thành viên | `find` không thay metadata nhóm |
| Chạy nhiều luồng không đồng bộ | Có thể hỏng rừng/metadata | Khóa hoặc concurrent DSU chuyên dụng |

### Số thực và tính kết hợp

Về toán học, phép cộng có tính kết hợp. Nhưng trên **số thực dấu chấm động**, thứ tự cộng có thể tạo kết quả làm tròn khác nhau:

```text
(a + b) + c  có thể khác  a + (b + c)
```

Union by size/rank và thứ tự các phép hợp có thể thay đổi thứ tự cộng các tổng trung gian. Nếu yêu cầu tính toán tiền tệ hoặc kết quả tái lập chính xác, cân nhắc **số nguyên đơn vị nhỏ nhất, decimal chính xác**, hoặc phương pháp tích lũy phù hợp thay vì mặc định dùng `float`.

## 23. Kiểm thử bất biến bằng một mô hình tham chiếu

Không chỉ kiểm tra đầu ra của vài phép union. Với dữ liệu nhỏ, có thể duyệt mọi phần tử và dựng lại các nhóm từ kết quả `find`, rồi đối chiếu từng metadata với dữ liệu gốc.

### Kiểm tra tất cả tổng hợp tại các gốc

```python
def validate_aggregates(
    dsu: AggregateDSU,
    values: list[int],
    flags: list[int],
) -> None:
    groups: dict[int, list[int]] = {}

    for x in range(len(values)):
        r = dsu.find(x)
        groups.setdefault(r, []).append(x)

    assert len(groups) == dsu.component_count()

    for root, members in groups.items():
        assert dsu.parent[root] == root
        assert dsu.size[root] == len(members)
        assert dsu.total[root] == sum(values[x] for x in members)
        assert dsu.minimum[root] == min(values[x] for x in members)
        assert dsu.maximum[root] == max(values[x] for x in members)

        expected_flags = 0
        for x in members:
            expected_flags |= flags[x]
        assert dsu.flag_or[root] == expected_flags

    assert sum(dsu.size[r] for r in groups) == len(values)


validate_aggregates(dsu, weights, masks)
```

Hàm này cố ý **quét toàn bộ các thành viên**; phù hợp với unit test hoặc kiểm tra dữ liệu nhỏ, **không** nên chạy sau mọi thao tác trên n rất lớn nếu cần hiệu năng.

### Giới hạn của hàm kiểm tra

Nếu `parent` đã hỏng và có chu trình, `find` có thể không dừng. Trình kiểm tra trên **giả định rừng cha hợp lệ**. Để kiểm tra dữ liệu không đáng tin, cần bổ sung một bước xác minh **chỉ số cha hợp lệ và không có chu trình** trước khi gọi `find` tiêu chuẩn.

Đối với đồ thị nhỏ, có thể duy trì thêm một **mảng nhãn nhóm tham chiếu** hoặc dùng BFS/DFS trên các cạnh đã thêm, rồi đối chiếu `same` và metadata của DSU sau mỗi bước.

## 24. Chọn phép tổng hợp theo câu hỏi nghiệp vụ

| Câu hỏi | Metadata nên duy trì | Những gì cần lưu ý |
|---|---|---|
| Nhóm có bao nhiêu phần tử? | `size[root]` | Chỉ cập nhật khi union hai gốc khác nhau |
| Tổng trọng số các phần tử? | `total[root]` | Cộng tổng khi union; hỗ trợ point update qua delta |
| Giá trị thấp/cao nhất? | `min/max[root]` | Dễ gộp khi tĩnh; khó xử lý thay đổi phần tử cực trị |
| Có ít nhất một phần tử mang cờ b? | `flagOr[root]` | OR không phải số lượng phần tử mang cờ |
| Có bao nhiêu phần tử mang cờ b? | Bộ đếm từng cờ | Tổng số đếm khi hợp; lưu theo số bit cần thiết |
| Giá trị trung bình? | `total[root]` và `size[root]` | Chia tổng cho số lượng, không lấy trung bình của hai average |
| Có bao nhiêu cạnh trong thành phần? | `edgeCount[root]` | Tăng cả khi thêm cạnh nội bộ; khác metadata của đỉnh |
| Có bao nhiêu nhãn phân biệt? | Set hoặc bản đồ tần suất ở gốc | Chi phí gộp không hằng số tổng quát |
| Giá trị trung vị/percentile? | Cấu trúc duy trì phân phối | Không suy được từ tổng/min/max |
| Danh sách thành viên theo thứ tự? | Danh sách/cây có thứ tự phụ | Chi phí duy trì thứ tự và tạo kết quả |
| Cần xóa cạnh/tách nhóm? | Thuật toán liên thông động hoặc offline/rollback | DSU cơ bản không có split |

**Kết luận thiết kế:** hãy xác định **phép toán tổng hợp** và **các loại cập nhật phải hỗ trợ** trước khi thêm trường metadata. Một tổng hợp rất dễ cập nhật khi **chỉ gộp nhóm** có thể trở nên khó khi **thuộc tính phần tử thay đổi hoặc nhóm bị tách**.

## 25. Bài tập tự kiểm tra có lời giải

**Câu 1.** Một nhóm có gốc 2, `size[2]=5`. Có thể suy ra `size[x]=5` với mọi phần tử x cùng nhóm không?

**Đáp án:** Không. Chỉ `size[root]` của **gốc hiện tại** được duy trì là kích thước nhóm. Phải dùng `size[find(x)]`.

**Câu 2.** Ban đầu có n nhóm đơn. Sau k lần `union` thật sự nối hai gốc khác nhau, số nhóm còn bao nhiêu nếu không thêm phần tử mới?

**Đáp án:** `n-k`. Những lần union trùng không làm giảm số nhóm.

**Câu 3.** Hai nhóm có kích thước 3 và 4, tổng trọng số lần lượt 10 và -2. Sau hợp, size và tổng là bao nhiêu?

**Đáp án:** Size **7**, tổng **8**. Cần tính tổng của **toàn hai nhóm**, không chỉ hai phần tử truyền vào union.

**Câu 4.** Hai nhóm có min lần lượt -5 và 2, max lần lượt 4 và 9. Sau hợp, min và max bằng bao nhiêu?

**Đáp án:** Min **-5**, max **9**.

**Câu 5.** Nhóm A có cờ OR `0101₂`, nhóm B `1010₂`. OR sau hợp bằng gì?

**Đáp án:** `1111₂`, tức **15**.

**Câu 6.** Trong ví dụ bảy phần tử, sau các phép `union(0,1), union(2,3), union(1,2)`, kích thước và tổng nhóm chứa 3 là bao nhiêu?

**Đáp án:** Size **4**, tổng **14**; nhóm là `{0,1,2,3}`.

**Câu 7.** Sau khi hợp thêm nhóm `{4,5}` vào nhóm `{0,1,2,3}`, tổng là bao nhiêu?

**Đáp án:** `14+(1+8)=23`, size **6**, min **-2**, max **8**, OR cờ **15**.

**Câu 8.** Khi thêm phần tử 6 có giá trị -3 vào nhóm trên, tổng mới là bao nhiêu?

**Đáp án:** `23+(-3)=20` và size **7**.

**Câu 9.** Nếu `union(x,y)` gọi lại trong cùng một nhóm, có được cộng `total[root]` thêm lần nữa không?

**Đáp án:** Không. Hai gốc bằng nhau, không có phần tử mới; cộng sẽ đếm trùng.

**Câu 10.** Vì sao `find` có nén đường không cập nhật `size` và `total`?

**Đáp án:** Nén đường chỉ rút ngắn liên kết cha trong **cùng một nhóm**. Số thành viên và giá trị từng thành viên không đổi.

**Câu 11.** Hai nhóm có `size=2, total=12` và `size=6, total=18`. Trung bình của nhóm sau hợp bằng bao nhiêu?

**Đáp án:** `(12+18)/(2+6)=30/8=3.75`, không phải trung bình của hai giá trị `6` và `3` bằng 4.5.

**Câu 12.** Nếu thay `value[x]` từ 4 thành 11, tổng nhóm phải thay đổi bao nhiêu khi x không chuyển nhóm?

**Đáp án:** Tăng **7**; cập nhật `total[find(x)]+=11-4` và lưu giá trị mới của x.

**Câu 13.** Với nhóm có các giá trị `[2,5,9]`, nếu thay 2 bằng 10, tại sao không thể chỉ gán `minimum[root]=10`?

**Đáp án:** Min mới là **5**. Chỉ lưu min cũ không cung cấp giá trị nhỏ thứ hai; cần dữ liệu bổ sung hoặc quét lại thành viên.

**Câu 14.** Nhóm có OR `1010₂` và một phần tử bỏ bit `0010₂`. Có chắc OR mới là `1000₂` không?

**Đáp án:** Không. Phần tử khác có thể vẫn giữ bit `0010₂`. Muốn cập nhật OR đúng khi có thay đổi bit, phải theo dõi đóng góp của các phần tử khác (ví dụ bộ đếm theo bit).

**Câu 15.** Thêm một cạnh giữa hai đỉnh đã liên thông. `union` trả false. Có cần tăng `edgeCount` nếu đang đếm tất cả cạnh đã thêm không?

**Đáp án:** **Có**. Cạnh vẫn tồn tại trong đồ thị dù không làm thay đổi thành phần; `edgeCount` phải tăng một.

**Câu 16.** Trong một thành phần vô hướng có 5 đỉnh và 4 cạnh, có thể suy ra điều gì về chu trình?

**Đáp án:** Nếu thành phần liên thông và đếm các cạnh đúng theo mô hình đồ thị vô hướng, `e=v-1` nên nó là **cây**, không có chu trình.

**Câu 17.** Một thành phần có 5 đỉnh và 5 cạnh. Nó có chu trình không?

**Đáp án:** **Có**, vì đồ thị vô hướng liên thông có ít nhất một chu trình khi `e≥v`; cạnh song song và khuyên cũng được tính là chu trình theo mô hình đồ thị đa cạnh.

**Câu 18.** Nếu metadata là một bitset dài B bit, có thể mặc định hợp bitset tốn `O(1)` như một OR của từ máy không?

**Đáp án:** Không. Nếu lưu trên nhiều từ máy w bit, chi phí OR có thể là **`O(B/w)`**; cần cộng phần này vào thời gian union.

**Câu 19.** Vì sao nối hai chuỗi mô tả thành viên không phải một tổng hợp nhóm vô thứ tự an toàn theo mặc định?

**Đáp án:** Nối chuỗi không giao hoán: `"ab"+"cd"` khác `"cd"+"ab"`. DSU có thể chọn gốc theo size/rank hoặc thứ tự tham số, dẫn tới kết quả phụ thuộc thứ tự hợp.

**Câu 20.** Nếu dùng union by rank thay vì size, có còn thể duy trì `size[root]` và `total[root]` không?

**Đáp án:** **Có.** Rank quyết định gốc được giữ, còn size và total là metadata độc lập. Khi hợp hai gốc khác nhau, vẫn cộng size và total ở gốc mới.

**Câu 21.** Một DSU cần hỗ trợ liên tục **xóa cạnh khiến nhóm bị tách**. Có thể chỉ sửa `size[root]` và `total[root]` để giải quyết không?

**Đáp án:** Không. DSU chuẩn không biết cách tách rừng theo liên thông thực sau xóa cạnh. Cần dựng lại từ các cạnh còn lại hoặc chọn thuật toán dynamic connectivity/offline rollback thích hợp.

**Câu 22.** Nếu `size[root]` luôn đúng nhưng `total[root]` sai, có thể kết luận parent forest chắc chắn sai không?

**Đáp án:** Không. Rừng cha và phân hoạch có thể vẫn đúng, trong khi metadata bị lỗi do cộng trùng, bỏ sót phép cập nhật hoặc dùng sai phép tổng hợp. Phải kiểm tra **cả bất biến cấu trúc lẫn bất biến dữ liệu**.

## Ghi nhớ

- **Thông tin tổng hợp thuộc về gốc hiện tại.** Muốn lấy kích thước, tổng, min/max hoặc cờ của nhóm chứa x, hãy lấy `r=find(x)` rồi đọc metadata tại r.
- **Khi union hai gốc khác nhau**, kích thước và tổng được **cộng**, min/max lấy min/max của hai nhóm cũ, OR cờ lấy OR hai mặt nạ. Nếu hai gốc trùng nhau, phải **no-op**, không cộng metadata hay trừ số nhóm.
- **Union by size** vừa duy trì kích thước thật vừa giữ cây có chiều cao `O(log n)` khi chưa nén; kết hợp path compression cho chi phí gần hằng số **khấu hao** của các phép tìm/hợp.
- Các phép gộp tổng hợp nên **kết hợp**, và thường cần **giao hoán** khi nhóm không có thứ tự. Với metadata lớn, phải cộng chi phí gộp thay vì mặc định union luôn `O(α(n))`.
- **Tổng có thể hỗ trợ cập nhật điểm bằng delta**, nhưng **min/max và OR không thể luôn gỡ đóng góp cũ từ một giá trị tổng hợp đơn lẻ**. Khi cho phép thuộc tính phần tử thay đổi, phải thiết kế thêm dữ liệu hỗ trợ.
- Phân biệt **thuộc tính đỉnh** với **thuộc tính cạnh**: thêm cạnh nội bộ không đổi tổng trọng số đỉnh, nhưng vẫn làm tăng số cạnh thực trong thành phần nếu đang đếm chúng.
- DSU chuẩn phù hợp với **hợp nhóm dần và truy vấn liên thông**, không tự hỗ trợ **tách nhóm/xóa cạnh, xuất danh sách thành viên O(1) hoặc giao dịch đồng thời thiếu đồng bộ**.
