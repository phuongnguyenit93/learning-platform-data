# Cây van Emde Boas và phân rã miền khóa đệ quy

Giả sử chương trình quản lý một tập các **khóa số nguyên phân biệt**. Ta muốn biết khóa `x` có tồn tại không, khóa nhỏ nhất/lớn nhất là gì, hoặc tìm **khóa đứng ngay trước/sau `x` theo thứ tự số học**. Một cây AVL hay Red-Black có thể làm được với O(log n) thời gian cho mỗi thao tác, trong đó `n` là số khóa đang lưu. Nhưng khi khóa thuộc một **miền nguyên hữu hạn**, ta có thể tận dụng thêm cấu trúc của chính miền đó.

**Cây van Emde Boas** (thường viết tắt là **vEB tree**, theo tên Peter van Emde Boas) là một cấu trúc tập có thứ tự khai thác **phân rã đệ quy miền khóa**. Trong mô hình chuẩn với miền `U` giá trị, nó hỗ trợ `insert`, `delete`, `member`, `minimum`, `maximum`, `predecessor` và `successor` với các giới hạn đáng chú ý:

\[
\boxed{T_{\mathrm{predecessor/successor/insert/delete}}=O(\log\log U).}
\]

Phiên bản kinh điển thường trả `minimum` và `maximum` trong **O(1)** bằng cách lưu ngay tại nút. Sự đánh đổi lớn là **O(U) không gian** và chi phí cấp phát/khởi tạo đáng kể nếu toàn bộ cấu trúc được dựng sẵn; đây không phải một cây dùng O(n) nút như AVL.

Điểm cốt lõi của vEB không phải “chia đôi các khóa thành hai cây con” như một BST. Nó **chia miền số theo các nhóm có độ rộng gần căn bậc hai của `U`**. Mỗi nhóm chứa một vEB nhỏ hơn, đồng thời một cấu trúc **summary** biết nhóm nào đang có khóa. Nhờ vậy, tìm cụm tiếp theo cũng là một bài toán predecessor/successor trên một miền nhỏ hơn nhiều.

Bài học trong chương **Khóa số nguyên** trình bày từ mô hình `U,n,w`, phép ánh xạ `high/low/index`, bất biến `min/max/summary/cluster`, thuật toán thêm/xóa/tìm tiền nhiệm-kế nhiệm, chứng minh độ phức tạp và bộ nhớ, đến chương trình **Java tự chứa** kiểm tra vEB với `TreeSet`.

## 1. Mô hình bài toán: tập có thứ tự trong một miền hữu hạn

Cho miền chuẩn hóa:

\[
\mathcal U=\{0,1,\ldots,U-1\},
\]

và tập khóa đang lưu:

\[
S\subseteq\mathcal U,\qquad n=|S|.
\]

Ta phân biệt ba đại lượng:

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `U` | **Số khóa có thể xuất hiện**, tức kích thước miền | Mã từ 0 đến 255: `U=256` |
| `n` | **Số khóa đang có** trong tập | Hiện lưu 7 mã: `n=7` |
| `w` | Số bit của một từ máy theo mô hình tính toán | Ví dụ từ 64 bit: `w=64` |

Với tập khóa phân biệt, luôn có `0\le n\le U`.

### Các phép toán cần có

| API | Ý nghĩa | Ví dụ với `S=\{2,7,12,15\}` |
| --- | --- | --- |
| `member(x)` | Có lưu chính khóa `x` không? | `member(7)=true` |
| `insert(x)` | Thêm `x` nếu chưa có | Chèn 9 tạo `\{2,7,9,12,15\}` |
| `delete(x)` | Xóa `x` nếu đang có | Xóa 7 |
| `minimum()` | Khóa nhỏ nhất hiện có | 2 |
| `maximum()` | Khóa lớn nhất hiện có | 15 |
| `predecessor(x)` | Khóa lớn nhất **nhỏ hơn hẳn** `x` | `predecessor(12)=7` |
| `successor(x)` | Khóa nhỏ nhất **lớn hơn hẳn** `x` | `successor(7)=12` |
| `floor(x)` | Khóa lớn nhất `\le x` | `floor(7)=7` |
| `ceiling(x)` | Khóa nhỏ nhất `\ge x` | `ceiling(8)=12` |

Trong bài, `predecessor` và `successor` là **nghiêm ngặt**: dấu `<` và `>`. Hai truy vấn `floor/ceiling` bao gồm dấu bằng. Nếu không có khóa thỏa điều kiện, kết quả là **không có**, không dùng 0 hay `-1` để thay thế một khóa hợp lệ.

### Vì sao xét `U` là lũy thừa của 2?

Phiên bản cổ điển thường giả định:

\[
\boxed{U=2^k,\qquad k\ge1.}
\]

Đây là cách thuận tiện để chia các bit của khóa thành phần cao và phần thấp. Nếu miền có kích thước khác lũy thừa của 2, có thể **đệm lên lũy thừa của 2 kế tiếp** và không chèn những khóa thuộc phần đệm.

Tuy nhiên, phép đệm cần xét **chi phí bộ nhớ**. Chẳng hạn, khoảng có 1.001 giá trị có thể đệm thành 1.024; nhưng một miền cực lớn không được tự động cấp phát chỉ vì công thức lý thuyết cho phép.

## 2. Ý tưởng căn bậc hai: chia khóa thành phần cao và phần thấp

Cho `U=2^k`. Chia `k` bit của khóa thành:

- `k_{\mathrm{low}}=\lfloor k/2\rfloor` bit thấp.
- `k_{\mathrm{high}}=\lceil k/2\rceil` bit cao.

Đặt:

\[
L=2^{k_{\mathrm{low}}},\qquad H=2^{k_{\mathrm{high}}}.
\]

Ta có:

\[
\boxed{U=H\cdot L.}
\]

Mỗi khóa `x\in[0,U-1]` tách thành:

\[
\boxed{
high(x)=\left\lfloor\frac{x}{L}\right\rfloor,\qquad
low(x)=x\bmod L.
}
\]

Ghép ngược một chỉ số cụm `h` và chỉ số bên trong cụm `l`:

\[
\boxed{index(h,l)=hL+l.}
\]

Với `0\le h<H` và `0\le l<L`, ta có:

\[
high(index(h,l))=h,\qquad low(index(h,l))=l.
\]

Nhờ đó, **mọi khóa nằm trong đúng một cụm**. Các cụm là những khoảng khóa liên tục; nếu `h_1<h_2` thì **mọi khóa thuộc cụm `h_1` đều nhỏ hơn mọi khóa thuộc cụm `h_2`**.

### Ví dụ `U=16`: chia khóa 4 bit thành 2 + 2 bit

\[
U=16=2^4,\quad L=4,\quad H=4.
\]

```text
Khóa x:    0  1  2  3 | 4  5  6  7 | 8  9 10 11 |12 13 14 15
high(x):   0  0  0  0 | 1  1  1  1 | 2  2  2  2 | 3  3  3  3
low(x):    0  1  2  3 | 0  1  2  3 | 0  1  2  3 | 0  1  2  3

cluster[0]       cluster[1]       cluster[2]       cluster[3]
     0..3             4..7             8..11           12..15
```

Ví dụ:

\[
high(13)=\lfloor13/4\rfloor=3,\qquad low(13)=13\bmod4=1.
\]

Và:

\[
index(3,1)=3\cdot4+1=13.
\]

Ở dạng nhị phân:

```text
x = 13 = 1101
         ^^ ^^
         |   |
         |   +-- low  = 01 = 1
         +------ high = 11 = 3
```

### Ví dụ `U=32`: tại sao phải xử lý `k` lẻ?

\[
U=32=2^5,\quad k_{\mathrm{low}}=2,\quad k_{\mathrm{high}}=3.
\]

Khi đó:

\[
L=4,\qquad H=8,\qquad H\cdot L=32.
\]

Có **8 cụm**, mỗi cụm rộng **4 khóa**. Không thể dùng hai số nguyên “căn bậc hai” giống nhau để chia 32 thành một tích chính xác mà không xét làm tròn. Trong mã Java, dùng `Integer.numberOfTrailingZeros(U)` để lấy `k`, rồi chia bit cao/thấp; không tính căn bậc hai kiểu dấu phẩy động rồi ép kiểu.

### Vì sao căn bậc hai quan trọng?

Khi `U` lớn, hai cấu trúc đệ quy của vEB chỉ còn miền cỡ:

\[
\sqrt U.
\]

Đường tìm kiếm sẽ giảm `U` thành khoảng `\sqrt U`, sau đó thành `U^{1/4}`, `U^{1/8}`, ... Mỗi lần **giảm khoảng một nửa số bit địa chỉ**. Đây chính là nguồn gốc xuất hiện `\log\log U` trong độ phức tạp.

## 3. Một nút vEB chứa những gì?

Với miền cục bộ `0..U-1`, một nút vEB cổ điển chứa:

```text
VEB(U):
    min       // Khóa nhỏ nhất của tập cục bộ, hoặc EMPTY
    max       // Khóa lớn nhất của tập cục bộ, hoặc EMPTY
    summary   // VEB(H), đánh dấu các cụm không rỗng
    cluster   // Mảng H cây VEB(L)
```

Trong ví dụ Java, tập cục bộ luôn gồm khóa **không âm**; `-1` có thể dùng **nội bộ** làm dấu rỗng vì nó không thuộc miền `0..U-1`. Với API bên ngoài cho khóa có thể âm, ta sẽ chuẩn hóa về offset và trả **`null`** khi không có kết quả.

### Bất biến 1: `min` và `max` phản ánh tập cục bộ

Nếu tập cục bộ rỗng:

\[
min=max=EMPTY.
\]

Nếu không rỗng:

\[
0\le min\le max<U.
\]

Đặc biệt, `min` được lưu **riêng ngay tại nút hiện tại**. **Nó không được lưu lặp lại trong các `cluster` của chính nút ấy.**

Đây là khác biệt rất quan trọng của vEB cổ điển. Nếu bỏ qua quy tắc này, các thuật toán chèn/xóa `min` và đếm khóa sẽ bị sai.

### Bất biến 2: `cluster[h]` chứa các khóa không phải `min` thuộc cụm `h`

Nếu tập cục bộ là `S` và `m=min(S)`, các khóa nằm trong `cluster[h]` được định nghĩa:

\[
C_h=\{low(x)\mid x\in S\setminus\{m\},\ high(x)=h\}.
\]

Những khóa của cùng cụm được lưu dưới dạng `low(x)` trên miền `0..L-1`, không lưu `x` nguyên gốc trong cụm con.

**Không suy rằng mọi khóa của `S` đều được đưa xuống một cluster.** Khóa `min` được “rút ra” và giữ ở tầng cha.

### Bất biến 3: `summary` chứa chính xác chỉ số các cụm không rỗng

\[
\boxed{
h\in summary
\iff C_h\ne\varnothing.
}
\]

Theo đó:

- Khi một cụm chuyển từ **rỗng sang có khóa**, phải thêm `h` vào `summary`.
- Khi một cụm chuyển từ **có khóa sang rỗng**, phải xóa `h` khỏi `summary`.
- Nếu chỉ thay đổi số khóa bên trong một cụm nhưng cụm vẫn không rỗng, `summary` không thay đổi membership của `h`.

`summary` cũng là một **vEB trên miền 0..H-1**. Vì vậy nó tự hỗ trợ `predecessor` và `successor` của **các cụm**.

### Bất biến 4: `max` có thể nằm trong một cụm

Nếu có ít nhất hai khóa ở nút, `max` thường vẫn được lưu bên dưới trong một cluster, đồng thời **được cache** ở trường `max` của nút để trả lời nhanh. Vì vậy:

- `min` là khóa được **rút khỏi** các cụm của nút.
- `max` là **thông tin dư thừa có kiểm soát**, phản ánh khóa lớn nhất nhưng có thể vẫn xuất hiện trong cụm.

Nhầm hai quy tắc này là một lỗi phổ biến khi triển khai vEB.

### Trường hợp cơ sở `U=2`

Với miền `\{0,1\}`, không cần `summary` hay `cluster`. Chỉ cần `min` và `max` để biểu diễn bốn tập:

| Tập | `min` | `max` |
| --- | ---: | ---: |
| `\varnothing` | EMPTY | EMPTY |
| `\{0\}` | 0 | 0 |
| `\{1\}` | 1 | 1 |
| `\{0,1\}` | 0 | 1 |

Phép thêm, xóa, member, predecessor và successor trên miền 2 giá trị đều là O(1).

## 4. Một ví dụ quan trọng: `min` ở ngoài các cụm

Giả sử `U=16`, `S=\{2,3,7,12,15\}`. Vì `L=H=4`, các khóa được chia thành bốn cụm.

Ta có:

```text
VEB(16):
    min = 2
    max = 15

    cluster[0] = {low(3)}         = {3}
    cluster[1] = {low(7)}         = {3}
    cluster[2] = {}               = {}
    cluster[3] = {low(12),low(15)}= {0,3}

    summary = {0,1,3}
```

Lưu ý **khóa 2 không nằm trong `cluster[0]`**. Nó chính là `min` được giữ ở cha. Nếu muốn tái tạo toàn bộ tập:

1. Lấy `min=2`.
2. Duyệt các khóa từ `cluster[0]` rồi ghép `index(0,low)`.
3. Làm tương tự với các cụm còn lại.

Kết quả:

\[
\{2\}\cup\{3\}\cup\{7\}\cup\{12,15\}
=\{2,3,7,12,15\}.
\]

### Khi chỉ có một khóa

Với `S=\{2\}`, ta có `min=max=2`, còn mọi cụm và summary đều rỗng. Để thêm khóa mới, thuật toán phải đưa **khóa từng là min** xuống cụm nếu khóa mới nhỏ hơn nó.

### Khi tập rỗng

Với `S=\varnothing`, `min=max=EMPTY` và **không có cụm nào hoạt động**. Một số bản cài đặt cấp phát sẵn các đối tượng cụm, nhưng mỗi cụm vẫn biểu diễn tập rỗng. Đây là khác biệt giữa **đối tượng đã cấp phát** và **nút đang chứa khóa**.

## 5. Tìm kiếm chính xác: `member(x)`

Khi hỏi `x` trong một nút vEB:

1. Nếu `x=min` hoặc `x=max`, trả **true**.
2. Nếu `U=2` mà không khớp, trả **false**.
3. Tính `h=high(x)`, `l=low(x)`.
4. Hỏi tiếp `cluster[h].member(l)`.

```text
member(V, x):
    if x == V.min or x == V.max:
        return true
    if V.U == 2:
        return false
    return member(V.cluster[high(x)], low(x))
```

Ở đây giả định `0\le x<U`. Nếu người dùng nhập khóa ngoài miền, cần kiểm tra ở API bao ngoài trước khi truy cập mảng cụm.

### Diễn tiến ví dụ `U=16`

Cho `S=\{2,3,7,12,15\}`:

**`member(2)`:** khớp `min` ở gốc, trả true ngay.

**`member(7)`:** không khớp min/max, `high(7)=1`, `low(7)=3`; hỏi `cluster[1].member(3)` và tìm thấy.

**`member(10)`:** `high(10)=2`, `low(10)=2`; `cluster[2]` rỗng nên trả false.

### Vì sao thời gian là O(log log U)?

Mỗi lần đệ quy chỉ đi vào **một cụm có miền kích thước `L\approx\sqrt U`**. Ta có quan hệ:

\[
T_{\mathrm{member}}(U)
=T_{\mathrm{member}}(\sqrt U)+O(1),
\]

bỏ qua chi tiết làm tròn của số bit. Số tầng cho tới `U=2` là O(log log U).

Đặc biệt, **tìm min/max là O(1)** vì nút giữ sẵn hai giá trị; không cần làm phép tìm kiếm này.

## 6. Chèn khóa: giữ min riêng, đưa khóa còn lại vào cụm

Giả sử chỉ chèn khóa chưa có; API public có thể gọi `member` trước để bảo đảm tính chất tập phân biệt.

### Trường hợp A: nút đang rỗng

Nếu `min=EMPTY`, chèn bằng:

```text
emptyInsert(V, x):
    V.min = x
    V.max = x
```

Không cần vào cụm, không cần sửa summary. Thao tác này là O(1) tại nút.

### Trường hợp B: khóa mới nhỏ hơn `min`

Nếu `x<V.min`:

1. Đặt `V.min=x`.
2. Gọi `x` là giá trị **min cũ** vừa bị thay ra.
3. Chèn giá trị min cũ vào cụm phù hợp như một khóa bình thường.

Đây là điểm dễ bỏ sót:

```text
Trước:  S = {7}
        min=max=7, clusters={}

insert(2):
        min=2
        đưa 7 vào cluster[high(7)]
        max vẫn =7

Sau:    S = {2,7}
```

Nếu chỉ sửa `min=2` nhưng **không đưa 7 vào cluster**, `member(7)` còn có thể đúng vì khớp max, nhưng truy vấn thứ tự khác sẽ không tìm thấy cấu trúc đầy đủ. Validator phải phát hiện việc thiếu khóa trong cụm.

### Trường hợp C: chèn vào một cụm rỗng

Sau khi xử lý `min`:

```text
h = high(x)
l = low(x)

if cluster[h] đang rỗng:
    summary.insert(h)
    cluster[h].emptyInsert(l)
else:
    cluster[h].insert(l)

if x > max:
    max = x
```

**Tại sao gọi `emptyInsert` cho cụm rỗng?** Vì chỉ cần đặt min/max của cụm; không cần đệ quy dài xuống cụm ấy. Nhưng **phải chèn chỉ số `h` vào summary**, vì từ nay cụm đã trở thành có dữ liệu.

### Trường hợp D: chèn vào cụm đã có dữ liệu

Nếu `cluster[h]` không rỗng, gọi `insert(l)` bên trong cụm. Không thêm lại `h` vào summary vì `h` đã hiện diện.

### Mã giả đầy đủ

```text
insert(V, x):                  // tiền đề: x chưa thuộc V
    if V.min == EMPTY:
        emptyInsert(V, x)
        return

    if x < V.min:
        swap(x, V.min)          // x nay là min cũ

    if V.U > 2:
        h = high(x)
        l = low(x)
        if V.cluster[h].min == EMPTY:
            insert(V.summary, h)
            emptyInsert(V.cluster[h], l)
        else:
            insert(V.cluster[h], l)

    if x > V.max:
        V.max = x
```

### Vì sao `insert` không đệ quy đồng thời hai nhánh sâu?

- Nếu cụm **đã có khóa**, chỉ `cluster[h].insert` đệ quy; summary không đổi.
- Nếu cụm **rỗng**, chỉ `summary.insert(h)` có thể đệ quy; cụm dùng `emptyInsert` O(1).

Vì vậy mỗi mức có **tối đa một lời gọi đệ quy không tầm thường**, dẫn tới:

\[
T_{\mathrm{insert}}(U)=T(\Theta(\sqrt U))+O(1)
=O(\log\log U).
\]

Nếu bản triển khai cố ý làm thêm việc khác theo kích thước cụm, phải phân tích riêng, không tự mượn bảo đảm của thuật toán chuẩn.

## 7. Tìm `successor(x)`: từ cùng cụm tới cụm kế tiếp

Định nghĩa trong bài:

\[
\operatorname{successor}(x)
=\min\{y\in S\mid y>x\}.
\]

Với `S=\{2,3,7,12,15\}`:

```text
successor(2)  = 3
successor(3)  = 7
successor(8)  = 12
successor(15) = Không có
```

### Bước 1: xử lý các trường hợp dễ

Nếu tập rỗng, không có successor. Nếu `U=2`, chỉ cần xét hai giá trị 0 và 1.

Nếu `x<min`, successor chính là `min`, vì `min` là khóa nhỏ nhất của tập mà vẫn lớn hơn `x`.

Nếu `x\ge max`, không có khóa nào lớn hơn `x`.

### Bước 2: có khóa lớn hơn trong cùng cụm không?

Đặt `h=high(x)` và `l=low(x)`. Giả sử cụm `cluster[h]` không rỗng và:

\[
l<cluster[h].max.
\]

Khi đó có khóa trong **cùng cụm** lớn hơn `l`. Chỉ cần gọi:

\[
l'=cluster[h].successor(l),
\]

rồi ghép lại:

\[
\operatorname{successor}(x)=index(h,l').
\]

Không cần hỏi summary, vì mọi khóa trong cùng cụm mà lớn hơn `x` đều nhỏ hơn mọi khóa của các cụm ở bên phải.

### Bước 3: không còn khóa phù hợp trong cụm

Nếu cụm hiện tại rỗng hoặc không có khóa lớn hơn `l`:

1. Tìm chỉ số cụm kế tiếp:

   \[
   h'=summary.successor(h).
   \]

2. Nếu không có `h'`, successor không tồn tại.
3. Nếu có, lấy **khóa nhỏ nhất trong cụm kế tiếp**, vốn đã cache tại `cluster[h'].min`.
4. Ghép:

   \[
   index(h',cluster[h'].min).
   \]

**Không cần tìm min trong cụm bằng một đệ quy mới**, vì nó đã có sẵn ở trường `min`.

### Mã giả

```text
successor(V, x):
    if V.U == 2:
        if x == 0 and V.max == 1: return 1
        return NONE

    if V.min != EMPTY and x < V.min:
        return V.min

    h = high(x)
    l = low(x)
    if V.cluster[h] không rỗng and l < V.cluster[h].max:
        sub = successor(V.cluster[h], l)
        return index(h, sub)

    nextCluster = successor(V.summary, h)
    if nextCluster == NONE:
        return NONE

    return index(nextCluster, V.cluster[nextCluster].min)
```

Nhờ chỉ **một lời gọi successor sâu** ở mỗi mức, thời gian là O(log log U).

### Ví dụ cụm trống

Với `U=16`, `S=\{2,3,7,12,15\}`:

```text
successor(8):
    high(8)=2, low(8)=0
    cluster[2] rỗng
    summary={0,1,3}
    summary.successor(2)=3
    cluster[3].min=0
    index(3,0)=12
```

Truy vấn không phải quét lần lượt khóa 9, 10, 11 và không phải tìm từng khóa trong miền.

## 8. Tìm `predecessor(x)`: thuật toán đối xứng

Tiền nhiệm nghiêm ngặt:

\[
\operatorname{predecessor}(x)
=\max\{y\in S\mid y<x\}.
\]

### Bước xử lý

1. Tập rỗng → không có.
2. `U=2` → dùng trường hợp cơ sở.
3. Nếu `x>max` → trả `max`.
4. Nếu cụm hiện tại có khóa **nhỏ hơn `low(x)`**, đệ quy tìm predecessor trong cụm và ghép chỉ số.
5. Nếu không, tìm **cụm không rỗng trước đó** qua `summary.predecessor(high(x))`.
6. Nếu có cụm trước, ghép với `max` của cụm ấy.
7. Nếu **không có cụm trước** mà `x>min`, trả **`min` đang nằm ngoài các cụm**.
8. Còn lại không có tiền nhiệm.

Mã giả:

```text
predecessor(V, x):
    if V.U == 2:
        if x == 1 and V.min == 0: return 0
        return NONE

    if V.max != EMPTY and x > V.max:
        return V.max

    h = high(x)
    l = low(x)
    if V.cluster[h] không rỗng and l > V.cluster[h].min:
        sub = predecessor(V.cluster[h], l)
        return index(h, sub)

    previousCluster = predecessor(V.summary, h)
    if previousCluster != NONE:
        return index(previousCluster,
                     V.cluster[previousCluster].max)

    if V.min != EMPTY and x > V.min:
        return V.min
    return NONE
```

### Vì sao phải xét `min` cuối cùng?

Do `min` **không nằm trong cluster**, một lời gọi predecessor chỉ xét cụm có thể bỏ lỡ đúng **khóa nhỏ nhất của nút**. Ví dụ `S=\{2,3,7,12,15\}`:

```text
predecessor(3):
    high(3)=0, low(3)=3
    cluster[0]={3}, không có low nhỏ hơn 3
    summary.predecessor(0)=NONE
    min=2 < 3 -> trả 2
```

Nếu bỏ bước xét `min`, kết quả sẽ sai dù `member(2)` vẫn đúng.

### Ví dụ phải sang cụm trước

```text
predecessor(12):
    high(12)=3, low(12)=0
    cluster[3]={0,3}, không có low nhỏ hơn 0
    summary.predecessor(3)=1
    cluster[1].max=3
    index(1,3)=7
```

Thời gian mỗi lời gọi O(log log U) theo cùng lập luận như successor.

## 9. Xóa khóa: đẩy min kế tiếp lên và cập nhật summary

Xóa là phép toán dễ sai nhất của vEB vì **khóa nhỏ nhất được lưu ở ngoài các cụm**. Giả sử `delete(x)` chỉ gọi khi `member(x)` đúng.

### Trường hợp A: chỉ có một khóa

Nếu `min=max=x`, xóa làm nút rỗng:

```text
min = EMPTY
max = EMPTY
```

Các cụm và summary lúc này vốn đã rỗng theo bất biến, nên không cần đi xuống.

### Trường hợp B: miền có đúng hai giá trị

Nếu `U=2` và tập có cả 0 lẫn 1:

- Xóa 0 → `min=max=1`.
- Xóa 1 → `min=max=0`.

Không tồn tại cluster trong trường hợp cơ sở.

### Trường hợp C: xóa đúng `min`

Giả sử `U>2` và tập có ít nhất hai khóa. Các khóa còn lại đều đã nằm dưới cụm. Do summary mô tả những cụm có khóa, ta lấy:

1. `h=summary.minimum()` — cụm có chỉ số nhỏ nhất đang hoạt động.
2. `l=cluster[h].minimum()` — khóa thấp nhất của cụm đó.
3. Ghép `x'=index(h,l)` — đây chính là **khóa nhỏ nhất còn lại** trong tập.
4. Gán `min=x'`.
5. Đổi “khóa cần xóa khỏi cụm” thành `x=x'`, vì nó đã được **nâng lên min** và không được phép còn tồn tại đồng thời trong cluster.

```text
Xóa min khỏi S={2,3,7,12,15}:

    min cũ = 2
    summary.min = 0
    cluster[0].min = 3
    min mới = index(0,3) = 3

    Phải xóa 3 khỏi cluster[0].
    Nếu cluster[0] rỗng -> xóa 0 khỏi summary.

Sau: S={3,7,12,15}
```

**Quy tắc cực kỳ quan trọng:** không đơn giản đặt `min=3` rồi để 3 nằm trong cluster[0], vì khi đó **cùng một khóa được biểu diễn hai lần tại nút**.

### Trường hợp D: xóa trong một cụm

Với `x` đã được chọn để xóa khỏi cụm:

```text
h = high(x)
l = low(x)
delete(cluster[h], l)
```

Sau xóa, xét xem cụm còn khóa nào không.

Nếu **cụm rỗng**, phải:

1. Gọi `delete(summary,h)`.
2. Nếu khóa được xóa là `max` cũ, cập nhật max từ **cụm lớn nhất còn hoạt động**, hoặc gán `max=min` nếu không còn cụm nào.

Nếu **cụm vẫn có khóa** và `x` là max cũ, gán:

\[
max=index(h,cluster[h].max).
\]

Nếu `x` không phải max cũ, có thể giữ nguyên `max`.

### Mã giả đầy đủ

```text
delete(V, x):                        // tiền đề: x đang có mặt
    if V.min == V.max:
        V.min = V.max = EMPTY
        return

    if V.U == 2:
        if x == 0: V.min = 1
        else:      V.min = 0
        V.max = V.min
        return

    if x == V.min:
        firstCluster = V.summary.min
        x = index(firstCluster,
                  V.cluster[firstCluster].min)
        V.min = x

    h = high(x)
    l = low(x)
    delete(V.cluster[h], l)

    if V.cluster[h].min == EMPTY:
        delete(V.summary, h)
        if x == V.max:
            if V.summary.max == EMPTY:
                V.max = V.min
            else:
                lastCluster = V.summary.max
                V.max = index(lastCluster,
                              V.cluster[lastCluster].max)
    else if x == V.max:
        V.max = index(h, V.cluster[h].max)
```

### Chú ý khi xóa max

Giả sử `S=\{2,7,12,15\}` và xóa 15. Cluster[3] đang chứa `\{0,3\}` tương ứng khóa 12 và 15. Sau xóa 15, cluster[3] còn `\{0\}`, nên:

```text
max = index(3, cluster[3].max)
    = index(3,0)
    = 12.
```

Ngược lại, nếu cluster[3] chỉ chứa đúng 15, xóa nó làm cụm rỗng; phải xóa 3 khỏi summary, rồi lấy max ở **cụm khác lớn nhất** hoặc dùng min nếu không còn cụm.

### Vì sao xóa vẫn O(log log U), dù có hai lệnh `delete`?

Nhìn mã giả dễ tưởng phải đệ quy sâu vào **cả cluster và summary**:

\[
T(U)\stackrel{?}{=}2T(\sqrt U)+O(1).
\]

Nhưng phải xét **trường hợp xảy ra lời gọi thứ hai**. `delete(summary,h)` chỉ được gọi nếu `cluster[h]` đã **trở thành rỗng**. Theo thuật toán chuẩn, điều đó có nghĩa cụm trước khi xóa chỉ có **một khóa**, và xóa trên cụm ấy dùng ngay trường hợp `min=max` nên chỉ mất **O(1)** tại đầu cụm. Vậy ở một mức:

- **Hoặc** đệ quy không tầm thường vào một cluster còn nhiều khóa.
- **Hoặc** xóa khóa duy nhất của cluster O(1) và đệ quy không tầm thường vào summary.

Do đó, vẫn chỉ có **một nhánh đệ quy thực sự sâu ở mỗi mức**, và:

\[
\boxed{T_{\mathrm{delete}}(U)=O(\log\log U).}
\]

Nếu một cài đặt khác mất O(U) để dọn cụm hoặc tái xây cấu trúc, giới hạn ấy không còn tự động đúng.

## 10. Theo dõi toàn bộ thao tác trên ví dụ `U=16`

Ví dụ này gắn kết các bất biến **min tách khỏi cụm**, **summary đại diện cụm**, **successor theo cụm** và **xóa min**.

### Bước 1: chèn khóa đầu tiên

```text
insert(7)

min = 7
max = 7
summary = {}
cluster[0..3] đều rỗng
```

Không chèn 7 xuống cluster, vì khóa duy nhất nằm ở `min` của nút gốc.

### Bước 2: chèn khóa nhỏ hơn min

```text
insert(2)

min mới = 2
min cũ  = 7

high(7)=1, low(7)=3
cluster[1] vốn rỗng -> emptyInsert(3)
summary.insert(1)
max = 7
```

Trạng thái:

```text
VEB(16):
    min = 2
    max = 7
    cluster[1] = {3}  # khóa gốc 1*4 + 3 = 7
    summary = {1}
```

### Bước 3: thêm khóa vào cụm đã có

`insert(3)`:

```text
high(3)=0, low(3)=3
cluster[0] đang rỗng -> chứa {3}
summary trở thành {0,1}
min=2, max=7
```

### Bước 4: tạo một cụm mới ở bên phải

`insert(12)` và `insert(15)`:

```text
insert(12):
    cluster[3] từ rỗng -> {0}
    summary = {0,1,3}
    max = 12

insert(15):
    cluster[3] từ {0} -> {0,3}
    summary giữ nguyên {0,1,3}
    max = 15
```

Trạng thái:

```text
U = 16, L = 4, H = 4

min = 2
max = 15
summary = {0,1,3}

cluster[0] = {3}       -> khóa gốc 3
cluster[1] = {3}       -> khóa gốc 7
cluster[2] = {}        -> không có khóa
cluster[3] = {0,3}     -> khóa gốc 12,15

Toàn tập = {2,3,7,12,15}
```

### Bước 5: hỏi kế nhiệm và tiền nhiệm

```text
successor(3):
    cluster[0] không có low > 3
    summary.successor(0) = 1
    index(1, cluster[1].min=3) = 7

predecessor(12):
    cluster[3] không có low < 0
    summary.predecessor(3) = 1
    index(1, cluster[1].max=3) = 7

predecessor(3):
    cluster[0] không có low < 3
    summary.predecessor(0) = NONE
    min=2 < 3 -> 2

successor(15):
    không có khóa > max=15 -> NONE
```

### Bước 6: xóa min và một khóa trong cụm cuối

`delete(2)`:

```text
min mới lấy từ cụm nhỏ nhất:
    summary.min = 0
    cluster[0].min = 3
    min <- index(0,3) = 3

xóa 3 khỏi cluster[0] -> cụm rỗng
xóa 0 khỏi summary -> summary={1,3}
max vẫn = 15

Toàn tập = {3,7,12,15}
```

`delete(15)`:

```text
cluster[3] từ {0,3} -> {0}
summary vẫn = {1,3}
max <- index(3,0) = 12

Toàn tập = {3,7,12}
```

### Bước 7: xóa cả cụm cuối

`delete(12)`:

```text
cluster[3] từ {0} -> {}
summary xóa 3 -> {1}
max <- index(1,cluster[1].max=3)=7

Toàn tập = {3,7}
```

Cuối cùng, `delete(7)` làm cluster[1] rỗng, summary rỗng và `min=max=3`. `delete(3)` làm cả nút gốc rỗng với `min=max=EMPTY`.

Ở mọi thời điểm, summary **không cần ghi lại số lượng khóa trong mỗi cụm**: nó chỉ phải biết **cụm đó có ít nhất một khóa hay không**.

## 11. Chứng minh thời gian `O(log log U)`

Đặt `U=2^k`. Phân rã trên một mức làm kích thước miền của cấu trúc được đệ quy đi vào giảm từ khoảng `2^k` xuống `2^{\lceil k/2\rceil}` hoặc `2^{\lfloor k/2\rfloor}`.

Viết `t(k)` là số bước theo `k=\log_2 U`:

\[
t(k)\le t(\lceil k/2\rceil)+O(1).
\]

Số lần chia đôi `k` cho tới 1 là O(log k), nên:

\[
\boxed{t(k)=O(\log k)=O(\log\log U).}
\]

### Tại sao phép tìm kế nhiệm chỉ có một đệ quy đáng kể?

Tại một nút:

- Nếu còn khóa lớn hơn trong **cùng cụm**, ta gọi `successor` trên **một cluster**.
- Ngược lại, gọi `successor` trên **summary**; sau khi tìm được cụm kế tiếp, lấy `cluster[h'].min` trong O(1), không phải đệ quy tìm minimum.

Đó là hai **nhánh loại trừ nhau**, không phải hai lời gọi sâu được thực hiện đồng thời.

### Tại sao phép chèn không nhân đôi nhánh đệ quy?

- **Cụm rỗng:** đệ quy vào summary; đặt min/max của cụm bằng `emptyInsert` O(1).
- **Cụm không rỗng:** đệ quy vào cụm; summary không thay đổi.

Tương tự, với phép xóa, chỉ khi cụm trở về rỗng mới cần xóa chỉ số cụm khỏi summary; chính việc xóa phần tử **duy nhất** của cụm là O(1) tại cụm ấy.

### Bảng tóm tắt

| Thao tác | Thời gian của vEB chuẩn | Lý do |
| --- | --- | --- |
| `minimum`, `maximum` | **O(1)** | Trường `min/max` tại nút |
| `member` | **O(log log U)** | Một cluster ở mỗi mức |
| `insert` | **O(log log U)** | Một nhánh đệ quy đáng kể mỗi mức |
| `delete` | **O(log log U)** | Cụm rỗng thì xóa cục bộ O(1) và cập nhật summary |
| `predecessor`, `successor` | **O(log log U)** | Một cluster hoặc summary, ghép index O(1) |
| `floor`, `ceiling` | O(log log U) | Quy về predecessor/successor hoặc xử lý dấu bằng |
| Liệt kê `r` khóa đầu trong một đoạn | O((r+1) log log U) nếu gọi successor lặp | Chưa tận dụng một iterator chuyên biệt |
| Đếm số khóa trong đoạn | Không tự có O(log log U) | Cần duy trì thông tin hạng/đếm bổ trợ |

**Không nói “min/max O(log log U)”** khi đã lưu sẵn ở nút: đó là một ưu điểm của vEB chuẩn. Ngược lại, **không nói “rank/select O(log log U)”** nếu chỉ có min/max, summary và cluster như bài này; các truy vấn ấy cần thiết kế và bất biến khác.

### Khi `w` là tham số của mô hình

Nếu `U=2^w`, ta có:

\[
\log\log U=\log w
\]

theo một cơ số log cố định. Do đó, giới hạn vEB thường còn được viết **O(log w)** trong mô hình Word-RAM với khóa `w` bit và các phép toán trên một từ có chi phí O(1).

Nhưng độ phức tạp lý thuyết **không bao hàm chi phí cache miss, cấp phát đối tượng hoặc garbage collection**. Một cấu trúc đệ quy nhiều đối tượng có thể chậm hơn bitset hoặc mảng đã sắp trên dữ liệu thực, dù số bước tiệm cận hấp dẫn.

## 12. Không gian `O(U)` và chi phí khởi tạo

Đây là đánh đổi nổi bật nhất của vEB **kinh điển**.

Với `U>2`, nút vEB dựng:

- Một `summary` trên miền `H`.
- Một mảng `H` cụm, mỗi cụm là một vEB trên miền `L`.
- Một số trường `min/max` và thông tin phân rã.

Nếu **cấp phát đệ quy tất cả các cụm**, kể cả cụm chưa có khóa, chi phí có dạng:

\[
S(U)=H\,S(L)+S(H)+O(H)
\]

với `H\approx L\approx\sqrt U`. Nghiệm của cấu trúc cổ điển là:

\[
\boxed{S(U)=O(U)\text{ ô/từ lưu trữ}.}
\]

Để hiểu trực giác: chỉ riêng các cụm ở mức gốc đã biểu diễn một miền tổng cộng `H\cdot L=U` vị trí; đệ quy thêm các tầng tóm tắt và metadata với tổng chi phí cùng bậc `U`.

### `U` có thể lớn hơn `n` cực nhiều

Giả sử:

\[
U=2^{32}=4\,294\,967\,296,\qquad n=100.
\]

Cấu trúc vEB cổ điển cấp phát theo `U` vẫn có mức bộ nhớ tiệm cận O(`2^{32}`) dù chỉ lưu 100 khóa. Nếu một ô lý tưởng dùng 8 byte, riêng `U` ô tương đương khoảng 32 GiB payload; **vEB Java hướng đối tượng thường có overhead lớn hơn**, và con số 8 byte/ô chỉ để minh họa thứ tự tài nguyên, không phải dự báo chính xác bộ nhớ cây.

### Khởi tạo không phải O(1) trong phiên bản cấp phát đầy đủ

Để tạo toàn bộ cây gồm những nút và mảng cụm cần thiết, phải cấp phát/khởi tạo số lượng đối tượng theo `U`:

\[
\boxed{T_{\mathrm{build}}=O(U).}
\]

Sau khi đã có cấu trúc, một thao tác insert/delete có thể đạt O(log log U). Không được bỏ qua chi phí **dựng ban đầu** khi đánh giá hiệu năng một bài toán chỉ có vài truy vấn.

### Cấp phát lười có khắc phục mọi vấn đề không?

Có thể **chưa tạo một cluster** cho tới lần đầu cần lưu khóa vào nó. Tuy nhiên:

- Mảng con trỏ `cluster[]` của một nút vẫn có thể cấp phát theo số nhóm `H`.
- Các nút `summary` cũng cần khởi tạo hoặc cấp phát theo nhu cầu.
- Không còn được mặc nhiên gọi bộ nhớ thực dùng đúng O(n) khi vẫn giữ các mảng chỉ mục dày đặc.
- Phải chứng minh lại chi phí khởi tạo, cập nhật và không gian cho **biến thể cụ thể**.

Trong học thuật, các cấu trúc như **y-fast trie** dùng các kỹ thuật lấy mẫu và bảng băm để đạt thời gian kỳ vọng gần O(log log U) với không gian theo số khóa `n`, nhưng phức tạp hơn nhiều và có những giả định về phép băm/ngẫu nhiên hóa.

**Bản Java trong bài** cố ý dùng **cấp phát sẵn** để bất biến và công thức đệ quy khớp sát với vEB kinh điển, đồng thời đặt giới hạn miền nhỏ để tránh cấp phát không kiểm soát.

## 13. So sánh với các cấu trúc khóa số nguyên khác

| Cấu trúc | Tìm chính xác | Predecessor/successor | Min/max | Bộ nhớ cơ bản |
| --- | --- | --- | --- | --- |
| Mảng địa chỉ trực tiếp | O(1) | O(U) nếu quét | O(U) nếu quét | O(U) ô |
| Bitset dày đặc | O(1) đọc bit | O(U/w) worst-case khi quét từ | O(U/w) khi quét | O(U) bit |
| Bitmap tóm tắt nhiều cấp | O(1) đọc bit | O(log_w U) theo mô hình cụ thể | O(log_w U), có thể cache min/max | O(U) bit |
| Binary trie chưa nén | O(w) | O(w) | O(w) | O(nw) nút |
| AVL/Red-Black tree | O(log n) | O(log n) | O(log n), hoặc cache O(1) | O(n) nút |
| Mảng khóa đã sắp | O(log n) | O(log n) | O(1) | O(n) khóa |
| **vEB cổ điển** | **O(log log U)** | **O(log log U)** | **O(1)** | **O(U) ô** |

Những giới hạn của bảng băm không nằm trong dòng này vì bảng băm thông thường chỉ hỗ trợ **tìm chính xác** O(1) trung bình/kỳ vọng, không tự duy trì thứ tự để tìm predecessor/successor nhanh.

### vEB khác binary trie thế nào?

**Binary trie** đọc **một bit** ở mỗi tầng:

```text
w bit
  ↓
 w-1 bit
  ↓
 w-2 bit
 ...
```

Với miền `U=2^w`, đường trie chưa nén có O(w)=O(log U) tầng.

**vEB** chia nhóm theo **khoảng một nửa số bit còn lại** ở mỗi tầng:

```text
w bit
  ↓
 ~w/2 bit
  ↓
 ~w/4 bit
  ↓
 ~w/8 bit
 ...
```

Do đó số tầng đệ quy O(log w)=O(log log U). Nhưng vEB cấp phát nhiều cụm và summary, nên trả giá ở không gian.

### vEB không phải B-tree/B+ tree

Trong một B-tree/B+ tree, cấu trúc nhiều nhánh thường được thiết kế để **giảm số trang cần đọc**, tối ưu I/O và locality theo khối. Trong vEB, tên “cây” và số nhánh thay đổi theo `U` xuất phát từ **phân rã tập khóa số nguyên**, không phải tự động từ yêu cầu trang đĩa.

Nếu cần lưu hàng triệu bản ghi cùng payload và range scan trên đĩa, B+ tree với các lá liên kết có thể thực tế hơn. Nếu chỉ cần tập ID nguyên, rất nhiều truy vấn predecessor/successor và miền `U` vừa phải, vEB là phương án đáng nghiên cứu.

### Bài toán lựa chọn cụ thể

| Tình huống | Cấu trúc nên cân nhắc | Vì sao |
| --- | --- | --- |
| 64 trạng thái bật/tắt | Một từ bit hoặc bitset | Rất đơn giản, bộ nhớ ít |
| 4.096 ID, tìm ID kế tiếp thường xuyên | Bitmap hai cấp hoặc vEB | Cả hai khai thác miền hữu hạn |
| Một triệu khóa rất thưa trong miền 64 bit | Cây cân bằng, y-fast trie khi phù hợp | Không muốn cấp phát theo `U=2^{64}` |
| Dữ liệu gần như tĩnh, khóa đã sắp | Mảng sorted + binary search | Gọn và thuận cache |
| Chỉ cần `contains`, ít truy vấn thứ tự | Bảng băm | Truy cập điểm, ít overhead cấu trúc thứ tự |
| Cần phân cấp tiền tố bit/XOR | Binary trie hoặc Patricia | Cấu trúc đường bit phục vụ truy vấn chuyên biệt |
| Cần ordered set, `U` vừa và mức trễ lý thuyết hấp dẫn | vEB | O(log log U) ordered operations, đổi lấy O(U) không gian |

Không có ngưỡng `U`/`n` duy nhất bảo đảm vEB “nhanh nhất”. Cần xét **khởi tạo**, giới hạn RAM, loại truy vấn, cache, khối lượng cập nhật và thư viện thực tế.

## 14. Java hoàn chỉnh: `BoundedVebSet` với miền lũy thừa của 2

Chương trình dưới đây cài đặt **vEB kinh điển, cấp phát toàn bộ các cụm**. Nó sử dụng một miền **`U=2^k` khóa liên tiếp** có thể bắt đầu từ số âm:

```text
Miền công khai:  [minKey, minKey+U-1]
Miền bên trong: [0, U-1]
offset(x) = x - minKey
```

Để người học có thể kiểm tra bộ nhớ hợp lý trong JVM, ví dụ giới hạn **`2\le U\le4096`**. Đây là **giới hạn có chủ ý của mã học tập**, không phải giới hạn toán học của vEB. Với các số `int` cực trị, dùng `long` **trước phép trừ/cộng** để tránh tràn khi chuẩn hóa.

Chương trình gồm:

- `VebNode`: cấu trúc đệ quy, giữ `min/max`, `summary` và các `clusters`.
- `BoundedVebSet`: API có khóa `int`, chuyển đổi thành offset không âm, quản lý `size` và truy vấn ngoài miền.
- Các phép `add/remove/contains/minimum/maximum/predecessor/successor/floor/ceiling/minimumInRange`.
- `keysInOrder`: liệt kê khóa bằng successor, không dùng để giả vờ bảo đảm O(n) cho toàn bộ quá trình.
- Bộ kiểm tra `verify` dựng lại tập khóa từ **min riêng + các cụm**, xác minh summary và trường max, đồng thời phát hiện alias/chu trình trong các đối tượng nút.
- Kiểm thử đối chiếu với `TreeSet<Integer>` sau chuỗi cập nhật, gồm các phép tính theo thứ tự.

**Quan trọng:** trong `VebNode`, dấu rỗng nội bộ là `-1` vì offset hợp lệ luôn không âm. Trong `BoundedVebSet`, ta trả `Integer` có thể `null` thay vì dùng `-1` làm kết quả, bởi khóa công khai `-1` có thể **đang thuộc tập**.

```java
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Objects;
import java.util.Random;
import java.util.TreeSet;

public class VanEmdeBoasRecursiveDemo {
    private static final int EMPTY = -1;
    private static final int DEMO_MAX_UNIVERSE = 4096;

    // Classic eagerly allocated recursive vEB tree on [0, universe-1].
    static final class VebNode {
        final int universe;
        final int lowerSize;    // Number of low-bit possibilities, L.
        final int upperSize;    // Number of high-bit possibilities, H.
        final VebNode summary;
        final VebNode[] clusters;

        int min = EMPTY;
        int max = EMPTY;

        VebNode(int universe) {
            if (universe < 2
                    || Integer.bitCount(universe) != 1) {
                throw new IllegalArgumentException(
                    "Universe must be a power of two >= 2");
            }
            this.universe = universe;
            if (universe == 2) {
                this.lowerSize = 0;
                this.upperSize = 0;
                this.summary = null;
                this.clusters = null;
                return;
            }

            int bitCount = Integer.numberOfTrailingZeros(universe);
            int lowBits = bitCount / 2;
            this.lowerSize = 1 << lowBits;
            this.upperSize = universe / lowerSize;

            // EAGER allocation: includes currently empty clusters.
            this.summary = new VebNode(upperSize);
            this.clusters = new VebNode[upperSize];
            for (int i = 0; i < upperSize; i++) {
                clusters[i] = new VebNode(lowerSize);
            }
        }

        private int high(int key) {
            return key / lowerSize;
        }

        private int low(int key) {
            return key % lowerSize;
        }

        private int index(int h, int l) {
            return h * lowerSize + l;
        }

        private void emptyInsert(int key) {
            if (min != EMPTY) {
                throw new IllegalStateException(
                    "emptyInsert on a nonempty node");
            }
            min = key;
            max = key;
        }

        boolean member(int key) {
            if (key == min || key == max) {
                return true;
            }
            if (universe == 2 || min == EMPTY) {
                return false;
            }
            return clusters[high(key)].member(low(key));
        }

        // Precondition: key is absent, 0 <= key < universe.
        void insert(int key) {
            if (min == EMPTY) {
                emptyInsert(key);
                return;
            }

            if (key < min) {
                int oldMin = min;
                min = key;
                key = oldMin; // Move the old min into its cluster.
            }

            if (universe > 2) {
                int h = high(key);
                int l = low(key);
                VebNode cluster = clusters[h];
                if (cluster.min == EMPTY) {
                    summary.insert(h);
                    cluster.emptyInsert(l);
                } else {
                    cluster.insert(l);
                }
            }

            if (key > max) {
                max = key;
            }
        }

        // Precondition: key is present.
        void delete(int key) {
            if (min == max) {
                min = EMPTY;
                max = EMPTY;
                return;
            }

            if (universe == 2) {
                min = key == 0 ? 1 : 0;
                max = min;
                return;
            }

            // The old min is not in any cluster. Promote the
            // next minimum and then remove its old cluster copy.
            if (key == min) {
                int firstCluster = summary.min;
                key = index(firstCluster,
                            clusters[firstCluster].min);
                min = key;
            }

            int h = high(key);
            int l = low(key);
            VebNode cluster = clusters[h];
            cluster.delete(l);

            if (cluster.min == EMPTY) {
                summary.delete(h);
                if (key == max) {
                    if (summary.max == EMPTY) {
                        max = min;
                    } else {
                        int lastCluster = summary.max;
                        max = index(lastCluster,
                                    clusters[lastCluster].max);
                    }
                }
            } else if (key == max) {
                max = index(h, cluster.max);
            }
        }

        // Smallest stored key strictly greater than key.
        // Precondition: 0 <= key < universe.
        int successor(int key) {
            if (universe == 2) {
                return key == 0 && max == 1 ? 1 : EMPTY;
            }
            if (min != EMPTY && key < min) {
                return min;
            }
            if (max == EMPTY || key >= max) {
                return EMPTY;
            }

            int h = high(key);
            int l = low(key);
            VebNode cluster = clusters[h];
            if (cluster.max != EMPTY && l < cluster.max) {
                int answerLow = cluster.successor(l);
                return index(h, answerLow);
            }

            int nextCluster = summary.successor(h);
            if (nextCluster == EMPTY) {
                return EMPTY;
            }
            return index(nextCluster, clusters[nextCluster].min);
        }

        // Largest stored key strictly less than key.
        // Precondition: 0 <= key < universe.
        int predecessor(int key) {
            if (universe == 2) {
                return key == 1 && min == 0 ? 0 : EMPTY;
            }
            if (max != EMPTY && key > max) {
                return max;
            }
            if (min == EMPTY || key <= min) {
                return EMPTY;
            }

            int h = high(key);
            int l = low(key);
            VebNode cluster = clusters[h];
            if (cluster.min != EMPTY && l > cluster.min) {
                int answerLow = cluster.predecessor(l);
                return index(h, answerLow);
            }

            int previousCluster = summary.predecessor(h);
            if (previousCluster != EMPTY) {
                return index(previousCluster,
                             clusters[previousCluster].max);
            }
            // The node's minimum is outside the clusters.
            return key > min ? min : EMPTY;
        }
    }

    // Public integer-key API with optional negative minKey.
    static final class BoundedVebSet {
        private final int minKey;
        private final int maxKey;
        private final int universe;
        private final VebNode root;
        private int size;

        BoundedVebSet(int minKey, int universe) {
            if (universe < 2
                    || universe > DEMO_MAX_UNIVERSE
                    || Integer.bitCount(universe) != 1) {
                throw new IllegalArgumentException(
                    "Demo requires power-of-two U in [2,4096]");
            }
            long max = (long) minKey + universe - 1L;
            if (max > Integer.MAX_VALUE) {
                throw new IllegalArgumentException(
                    "Bounded interval exceeds int range");
            }
            this.minKey = minKey;
            this.maxKey = (int) max;
            this.universe = universe;
            this.root = new VebNode(universe);
        }

        int size() {
            return size;
        }

        int universeSize() {
            return universe;
        }

        private int checkedOffset(int key) {
            if (key < minKey || key > maxKey) {
                throw new IllegalArgumentException(
                    "Key outside universe: " + key);
            }
            // Widen BEFORE subtraction.
            return (int) ((long) key - (long) minKey);
        }

        private Integer keyOrNull(int offset) {
            return offset == EMPTY
                ? null
                : (int) ((long) minKey + offset);
        }

        boolean contains(int key) {
            return root.member(checkedOffset(key));
        }

        boolean add(int key) {
            int offset = checkedOffset(key);
            if (root.member(offset)) {
                return false;
            }
            root.insert(offset);
            size++;
            return true;
        }

        boolean remove(int key) {
            int offset = checkedOffset(key);
            if (!root.member(offset)) {
                return false;
            }
            root.delete(offset);
            size--;
            return true;
        }

        Integer minimum() {
            return keyOrNull(root.min);
        }

        Integer maximum() {
            return keyOrNull(root.max);
        }

        // Strict successor. Query threshold may be outside domain.
        Integer successor(long threshold) {
            if (size == 0 || threshold >= (long) maxKey) {
                return null;
            }
            if (threshold < (long) minKey) {
                return minimum();
            }
            int offset = (int) (threshold - (long) minKey);
            return keyOrNull(root.successor(offset));
        }

        // Strict predecessor. Query threshold may be outside domain.
        Integer predecessor(long threshold) {
            if (size == 0 || threshold <= (long) minKey) {
                return null;
            }
            if (threshold > (long) maxKey) {
                return maximum();
            }
            int offset = (int) (threshold - (long) minKey);
            return keyOrNull(root.predecessor(offset));
        }

        // Inclusive ceiling = smallest stored key >= threshold.
        Integer ceiling(long threshold) {
            if (size == 0 || threshold > (long) maxKey) {
                return null;
            }
            if (threshold <= (long) minKey) {
                return minimum();
            }
            return successor(threshold - 1L);
        }

        // Inclusive floor = greatest stored key <= threshold.
        Integer floor(long threshold) {
            if (size == 0 || threshold < (long) minKey) {
                return null;
            }
            if (threshold >= (long) maxKey) {
                return maximum();
            }
            return predecessor(threshold + 1L);
        }

        Integer minimumInRange(long from, long to) {
            if (from > to) {
                return null;
            }
            Integer candidate = ceiling(from);
            return candidate != null && (long) candidate <= to
                ? candidate : null;
        }

        List<Integer> keysInOrder() {
            List<Integer> result = new ArrayList<>(size);
            Integer current = minimum();
            while (current != null) {
                result.add(current);
                current = successor((long) current);
            }
            return result;
        }

        // Debug-only: independently reconstruct local sets and
        // verify min/max, summary, uniqueness and pointer identity.
        void verify() {
            List<Integer> offsets = checkNode(
                root, new IdentityHashMap<VebNode, Boolean>());
            if (offsets.size() != size) {
                throw new IllegalStateException(
                    "Wrong public size");
            }
        }
    }

    // Return all stored local keys in ascending order. This
    // validator does not call insert/delete/member/successor.
    private static List<Integer> checkNode(
            VebNode node, IdentityHashMap<VebNode, Boolean> seen) {
        if (seen.put(node, Boolean.TRUE) != null) {
            throw new IllegalStateException(
                "Cycle or shared vEB node detected");
        }
        if ((node.min == EMPTY) != (node.max == EMPTY)) {
            throw new IllegalStateException("Partial empty state");
        }
        if (node.min != EMPTY
                && (node.min < 0 || node.min > node.max
                    || node.max >= node.universe)) {
            throw new IllegalStateException("Invalid min/max");
        }

        List<Integer> reconstructed = new ArrayList<>();
        if (node.min != EMPTY) {
            reconstructed.add(node.min);
        }
        if (node.universe == 2) {
            if (node.summary != null || node.clusters != null) {
                throw new IllegalStateException("Bad base node");
            }
            if (node.max != EMPTY && node.max != node.min) {
                reconstructed.add(node.max);
            }
        } else {
            if (node.summary == null || node.clusters == null
                    || node.clusters.length != node.upperSize
                    || node.lowerSize * node.upperSize != node.universe) {
                throw new IllegalStateException("Bad decomposition");
            }

            List<Integer> summaryKeys = checkNode(node.summary, seen);
            List<Integer> activeClusters = new ArrayList<>();
            for (int h = 0; h < node.upperSize; h++) {
                VebNode child = node.clusters[h];
                if (child == null || child.universe != node.lowerSize) {
                    throw new IllegalStateException(
                        "Missing/mis-sized cluster");
                }
                List<Integer> lows = checkNode(child, seen);
                if (!lows.isEmpty()) {
                    activeClusters.add(h);
                }
                for (int l : lows) {
                    reconstructed.add(h * node.lowerSize + l);
                }
            }
            if (!activeClusters.equals(summaryKeys)) {
                throw new IllegalStateException(
                    "Summary does not match nonempty clusters");
            }
        }

        int previous = EMPTY;
        for (int key : reconstructed) {
            if (key <= previous) {
                throw new IllegalStateException(
                    "Duplicate or unsorted local keys");
            }
            previous = key;
        }
        if (reconstructed.isEmpty()) {
            if (node.min != EMPTY || node.max != EMPTY) {
                throw new IllegalStateException("Nonempty min/max");
            }
        } else {
            if (node.min != reconstructed.get(0)
                    || node.max != reconstructed.get(
                        reconstructed.size() - 1)) {
                throw new IllegalStateException(
                    "Stored min/max do not match contents");
            }
        }
        return reconstructed;
    }

    private static void require(boolean condition, String reason) {
        if (!condition) {
            throw new IllegalStateException(reason);
        }
    }

    private static void compareAgainst(
            BoundedVebSet set, TreeSet<Integer> oracle) {
        set.verify();
        require(set.size() == oracle.size(), "Size mismatch");
        Integer first = oracle.isEmpty() ? null : oracle.first();
        Integer last = oracle.isEmpty() ? null : oracle.last();
        require(Objects.equals(set.minimum(), first),
                "Minimum mismatch");
        require(Objects.equals(set.maximum(), last),
                "Maximum mismatch");
        require(set.keysInOrder().equals(new ArrayList<>(oracle)),
                "Ordered contents mismatch");

        for (int key = -8; key <= 7; key++) {
            require(set.contains(key) == oracle.contains(key),
                    "Membership mismatch for " + key);
        }

        int[] probes = {
            Integer.MIN_VALUE, -100, -9, -8, -7, -6,
            -5, -4, -1, 0, 1, 4, 7, 8, 100,
            Integer.MAX_VALUE
        };
        for (int q : probes) {
            require(Objects.equals(
                set.predecessor((long) q), oracle.lower(q)),
                "Predecessor mismatch for " + q);
            require(Objects.equals(set.floor((long) q), oracle.floor(q)),
                "Floor mismatch for " + q);
            require(Objects.equals(
                set.ceiling((long) q), oracle.ceiling(q)),
                "Ceiling mismatch for " + q);
            require(Objects.equals(
                set.successor((long) q), oracle.higher(q)),
                "Successor mismatch for " + q);
        }
    }

    public static void main(String[] args) {
        // Public keys [-8,7] correspond to offsets [0,15].
        BoundedVebSet set = new BoundedVebSet(-8, 16);
        TreeSet<Integer> oracle = new TreeSet<>();

        for (int x : new int[] {-6, -5, -1, 4, 7}) {
            require(set.add(x) == oracle.add(x),
                    "Initial insertion mismatch");
        }
        compareAgainst(set, oracle);

        System.out.println("U=" + set.universeSize()
            + ", size=" + set.size());
        System.out.println("keys=" + set.keysInOrder());
        System.out.println("minimum=" + set.minimum());
        System.out.println("maximum=" + set.maximum());
        System.out.println("contains(-6)=" + set.contains(-6));
        System.out.println("contains(0)=" + set.contains(0));
        System.out.println("successor(-5)=" + set.successor(-5L));
        System.out.println("predecessor(4)=" + set.predecessor(4L));
        System.out.println("ceiling(0)=" + set.ceiling(0L));
        System.out.println("floor(0)=" + set.floor(0L));
        System.out.println("minimumInRange[-4,5]="
            + set.minimumInRange(-4L, 5L));

        System.out.println("remove(-6)=" + set.remove(-6));
        oracle.remove(-6);
        System.out.println("minimum after remove=" + set.minimum());
        System.out.println("remove(7)=" + set.remove(7));
        oracle.remove(7);
        System.out.println("maximum after remove=" + set.maximum());
        System.out.println("add(-8)=" + set.add(-8));
        oracle.add(-8);
        System.out.println("add(-1) again=" + set.add(-1));
        System.out.println("remove(6)=" + set.remove(6));
        System.out.println("keys now=" + set.keysInOrder());
        compareAgainst(set, oracle);

        // Differential test: many duplicates, missing deletes,
        // disappearing/reappearing clusters and changing min/max.
        Random random = new Random(20261128L);
        for (int step = 0; step < 500; step++) {
            int key = -8 + random.nextInt(16);
            boolean adding = random.nextBoolean();
            boolean expected = adding
                ? oracle.add(key) : oracle.remove(key);
            boolean actual = adding
                ? set.add(key) : set.remove(key);
            require(expected == actual,
                    "Update mismatch at step " + step);
            compareAgainst(set, oracle);
        }
        System.out.println("Random updates checked: 500");

        // Small power-of-two universe at the base case.
        BoundedVebSet tiny = new BoundedVebSet(0, 2);
        tiny.add(0);
        tiny.add(1);
        require(Objects.equals(tiny.successor(0L), 1),
                "Tiny successor mismatch");
        tiny.remove(0);
        require(Objects.equals(tiny.minimum(), 1),
                "Tiny delete mismatch");
        tiny.remove(1);
        tiny.verify();
        require(tiny.minimum() == null, "Tiny should be empty");

        // Signed int boundaries: intermediate arithmetic uses long.
        BoundedVebSet nearMin = new BoundedVebSet(
            Integer.MIN_VALUE, 8);
        nearMin.add(Integer.MIN_VALUE);
        nearMin.add(Integer.MIN_VALUE + 7);
        require(Objects.equals(
            nearMin.ceiling((long) Integer.MIN_VALUE - 1L),
            Integer.MIN_VALUE), "MIN boundary ceiling");
        require(nearMin.predecessor((long) Integer.MIN_VALUE) == null,
                "MIN boundary predecessor");
        nearMin.verify();

        BoundedVebSet nearMax = new BoundedVebSet(
            Integer.MAX_VALUE - 7, 8);
        nearMax.add(Integer.MAX_VALUE - 7);
        nearMax.add(Integer.MAX_VALUE);
        require(Objects.equals(
            nearMax.floor((long) Integer.MAX_VALUE + 1L),
            Integer.MAX_VALUE), "MAX boundary floor");
        require(nearMax.successor((long) Integer.MAX_VALUE) == null,
                "MAX boundary successor");
        nearMax.verify();

        System.out.println("Boundary checks: OK");
        System.out.println("All invariants: OK");
    }
}
```

Đầu ra dự kiến:

```text
U=16, size=5
keys=[-6, -5, -1, 4, 7]
minimum=-6
maximum=7
contains(-6)=true
contains(0)=false
successor(-5)=-1
predecessor(4)=-1
ceiling(0)=4
floor(0)=-1
minimumInRange[-4,5]=-1
remove(-6)=true
minimum after remove=-5
remove(7)=true
maximum after remove=4
add(-8)=true
add(-1) again=false
remove(6)=false
keys now=[-8, -5, -1, 4]
Random updates checked: 500
Boundary checks: OK
All invariants: OK
```

### Đọc mã theo các ý tưởng cốt lõi

**`VebNode` chỉ nhận khóa cục bộ không âm.** Khi đệ quy vào một cụm, thuật toán truyền `low(x)`; khi nhận kết quả trong cụm, nó ghép lại bằng `index(high,low)`. Nếu truyền nguyên khóa gốc xuống cụm, chỉ số và cận của trie đệ quy sẽ sai.

**`min` được giữ ngoài các cụm.** Khi chèn khóa nhỏ hơn min, mã chuyển min cũ vào cụm; khi xóa min, mã nâng min mới từ cụm nhỏ nhất và xóa bản sao trong cụm ấy.

**`summary` chỉ mô tả các cụm có khóa.** Khi một cụm rỗng lần đầu nhận khóa, mã chèn chỉ số cụm vào summary; khi xóa làm cụm rỗng, mã xóa chỉ số ấy khỏi summary.

**`max` luôn đúng sau xóa.** Nếu cụm bị xóa rỗng và đó là cụm của khóa max cũ, thuật toán lấy max ở cụm lớn nhất còn lại, hoặc min nếu không còn cụm nào.

**`minimum/maximum` là O(1).** Hai trường được đọc trực tiếp từ gốc; `keysInOrder` không phải thao tác O(n) được bảo đảm bởi thuật toán đang viết, vì nó dùng các lời gọi successor liên tiếp.

**`verify` có độ phức tạp lớn hơn thao tác thông thường.** Nó duyệt cả các nút được cấp phát, kể cả cụm rỗng; mục tiêu là kiểm tra độc lập các bất biến, không phải được gọi sau mỗi thao tác trong hệ thống sản xuất.

### Một lưu ý về `contains` và truy vấn ngoài miền

API `add/remove/contains` trong ví dụ **ném `IllegalArgumentException`** nếu khóa công khai nằm ngoài đoạn `[minKey,maxKey]`. Trong khi đó `predecessor/successor/floor/ceiling` được phép nhận **ngưỡng ngoài miền**, vì hỏi “khóa tiếp theo sau một ngưỡng lớn hơn mọi khóa” có kết quả tự nhiên là rỗng.

Đây là một hợp đồng API hợp lệ nhưng **không phải lựa chọn duy nhất**. Trong thư viện thật, có thể chọn `contains` trả false cho khóa ngoài miền; điều quan trọng là nêu rõ và kiểm tra nhất quán.

### Một lưu ý về giới hạn của mã

Chương trình không hỗ trợ payload đi kèm khóa, khóa trùng, tự mở rộng miền, bất biến đa phiên bản hoặc truy cập đồng thời. `VebNode` cấp phát cả những cụm rỗng, nên không phù hợp với miền rất lớn; cố tình không triển khai `U=2^{32}` trong RAM. Trường hợp mã dạy học sử dụng **int làm số lượng và offset**, trong khi định nghĩa toán học tổng quát không bị ràng buộc ở giới hạn mảng Java.

## 15. Kiểm thử độc lập sau mỗi chuỗi cập nhật

Đối với vEB, chỉ kiểm tra `member(x)` là **chưa đủ**. Một lỗi ở `summary` có thể khiến tất cả cụm vẫn lưu khóa nhưng `successor` không thể nhảy tới cụm phù hợp. Một lỗi ở `max` có thể khiến `member` vẫn đúng nhưng `maximum` sai.

### Oracle theo thứ tự

Trong Java, `TreeSet<Integer>` là một **tập chuẩn độc lập** có thứ tự tăng theo số nguyên có dấu:

| vEB API | Oracle từ `TreeSet` |
| --- | --- |
| `contains(x)` | `contains(x)` |
| `add(x)` | `add(x)` |
| `remove(x)` | `remove(x)` |
| `minimum()` | `isEmpty()?null:first()` |
| `maximum()` | `isEmpty()?null:last()` |
| `predecessor(x)` | `lower(x)` |
| `floor(x)` | `floor(x)` |
| `ceiling(x)` | `ceiling(x)` |
| `successor(x)` | `higher(x)` |

Bài thử phải kiểm tra cả **ngưỡng chính xác bằng một khóa đang có** lẫn ngưỡng **nằm giữa hai khóa**. Vì `predecessor`/`successor` trong bài là nghiêm ngặt, `predecessor(7)` **khác** `floor(7)` khi khóa 7 hiện diện.

### Những bất biến cần kiểm tra trực tiếp

Trong mỗi nút vEB:

1. `min/max` hoặc **cùng rỗng**, hoặc cả hai hợp lệ và `min\le max`.
2. Với `U>2`, cấu trúc có đúng `H` cluster với miền cục bộ `L`.
3. Mỗi chỉ số `h` nằm trong summary **khi và chỉ khi** cluster `h` không rỗng.
4. `min` của nút không được xuất hiện lại trong các cluster của chính nút.
5. `max` bằng khóa lớn nhất có thể dựng từ min và các cluster.
6. Không có khóa trùng, không có khóa ngoài miền cục bộ.
7. Những cấu trúc summary và cluster phải là **các nút cây độc lập**, không dùng chung một đối tượng nút theo nhiều đường con trỏ.
8. Số khóa dựng lại ở nút gốc bằng `size` công khai.

Trong ví dụ Java, `checkNode` kiểm tra danh tính nút bằng `IdentityHashMap`, dựng lại dãy khóa cục bộ theo thứ tự, đối chiếu summary với danh sách các cụm đang hoạt động rồi so `min/max`. **Không cần tin vào chính `member` hoặc `successor`** để kiểm tra cấu trúc, giúp phát hiện lỗi chung của các hàm thao tác.

### Các trường hợp biên dễ bắt lỗi

| Kịch bản | Nguy cơ phát hiện |
| --- | --- |
| `U=2`, tập rỗng, một khóa, hai khóa | Sai trường hợp cơ sở |
| `U=8,32,128` (số bit mũ lẻ) | Sai tách `H/L` |
| Thêm khóa nhỏ hơn min | Quên chuyển min cũ xuống cụm |
| Thêm khóa lớn hơn max | Quên cập nhật max |
| Thêm vào cụm rỗng | Quên thêm chỉ số cụm vào summary |
| Thêm vào cụm đã có khóa | Thêm lặp chỉ số cụm không đúng |
| Xóa min | Quên nâng min mới/xóa bản sao khỏi cụm |
| Xóa max ở cụm còn khóa | Max không được cập nhật từ cluster |
| Xóa khóa cuối của một cụm | Quên xóa chỉ số cụm khỏi summary |
| Xóa đến một khóa rồi tập rỗng | Sai `min=max` hoặc còn cluster hoạt động |
| Thêm trùng/xóa vắng | Thay đổi cấu trúc dù tập không đổi |
| Successor sang cụm khác | Trả nhầm min cụm hoặc cụm không rỗng gần nhất |
| Predecessor trước mọi cluster | Quên xét min tách riêng |
| Ngưỡng âm, cận `Integer.MIN/MAX_VALUE` | Tràn khi tính offset hoặc `x\pm1` |
| Kiểm tra identity node | Nhầm chia sẻ đối tượng thành cây hợp lệ |

### Chuỗi cập nhật mẫu để tái hiện lỗi

```text
U=16, miền [0,15]

add(7)
add(2)          -> min mới 2, đẩy 7 vào cluster[1]
add(3)          -> cluster[0] xuất hiện
add(12)
add(15)         -> cluster[3] có hai khóa
assert successor(3) == 7
assert predecessor(3) == 2

remove(2)       -> min mới 3, cluster[0] rỗng
assert predecessor(7) == 3
assert successor(3) == 7

remove(15)      -> max cập nhật thành 12
remove(12)      -> cluster[3] rỗng, max chuyển thành 7
assert maximum() == 7

remove(7)       -> chỉ còn 3
remove(3)       -> tập rỗng
assert minimum() == NONE
assert maximum() == NONE
```

Một bộ kiểm thử ngẫu nhiên nên dùng **seed cố định**, chọn miền nhỏ để các trường hợp **thêm trùng, xóa vắng, cụm rỗng→đầy và đầy→rỗng** xảy ra thường xuyên, rồi gọi validator và so `TreeSet` **sau từng bước**.

## 16. Những nhầm lẫn thường gặp

1. **Nhầm `U` với `n`.** `U` là số giá trị khóa có thể xuất hiện; `n` là số khóa đang có. Bộ nhớ vEB cổ điển phụ thuộc mạnh vào `U`.
2. **Cho rằng vEB luôn có O(n) bộ nhớ vì được gọi là cây.** Bản cấp phát đủ cluster kinh điển có O(U) không gian.
3. **Chia miền bằng căn bậc hai dấu phẩy động và bỏ qua số bit lẻ.** Với `U=32` cần `H=8,L=4` hoặc một quy ước tương đương bảo đảm tích đúng `U`.
4. **Đưa nguyên khóa `x` xuống cluster thay vì `low(x)`.** Miền cục bộ của cụm chỉ có `0..L-1`.
5. **Ghép kết quả từ cụm bằng `h+l`.** Phải dùng `index(h,l)=hL+l`.
6. **Lưu `min` trùng trong cluster của chính nút.** Thuật toán vEB chuẩn rút `min` ra khỏi các cụm; nếu lưu lặp, sẽ sai khi xóa và tái tạo tập.
7. **Cho rằng `max` luôn nằm ngoài cụm giống min.** `max` thường vẫn được chứa trong một cluster, còn trường `max` chỉ cache để truy vấn nhanh.
8. **Quên cập nhật summary khi cụm rỗng→không rỗng.** Successor có thể bỏ qua cả cụm vừa được thêm.
9. **Quên cập nhật summary khi cụm có khóa→rỗng.** Predecessor/successor có thể chọn nhầm một cụm đã rỗng.
10. **Đổi `min` khi chèn khóa nhỏ hơn nhưng đánh mất min cũ.** Min cũ phải được đưa xuống cluster phù hợp.
11. **Xóa min bằng cách chỉ gán `min=summary.min`.** `summary.min` là **chỉ số cụm**, không phải khóa gốc; cần ghép với `cluster[h].min`.
12. **Nâng min mới từ cluster lên nhưng không xóa nó khỏi cluster.** Khi đó cùng một khóa xuất hiện hai lần.
13. **Xóa max mà không cập nhật max theo cụm còn khóa.** `maximum()` có thể trả khóa đã xóa.
14. **Cắt một cluster/summary chỉ vì vừa xóa một khóa.** Chỉ được coi cụm rỗng khi `cluster[h].min==EMPTY`.
15. **Quên xử lý tập chỉ có một khóa trước khi đi vào summary.** Khi tập còn một khóa, summary có thể rỗng và không có cụm nào chứa min.
16. **Quên trường hợp cơ sở `U=2`.** Không có summary hay cluster; đệ quy tiếp sẽ sai hoặc không kết thúc.
17. **Nhầm predecessor nghiêm ngặt với floor.** Nếu `x` đang thuộc tập, `predecessor(x)<x`, còn `floor(x)=x`.
18. **Nhầm successor nghiêm ngặt với ceiling.** Nếu `x` thuộc tập, `successor(x)>x`, còn `ceiling(x)=x`.
19. **Quên xét min ngoài cluster khi tìm predecessor.** Có thể trả rỗng dù `min` chính là tiền nhiệm cần tìm.
20. **Cho rằng mỗi mức xóa luôn có hai nhánh đệ quy sâu nên phải là O(log U).** Cần phân tích điều kiện cụm rỗng: xóa phần tử duy nhất khỏi cụm là O(1).
21. **Gọi khởi tạo vEB cấp phát đủ cụm là O(1).** Dựng đầy đủ O(U) không gian thường cần O(U) thời gian.
22. **Cho rằng O(log log U) chắc chắn nhanh hơn O(log n) trên mọi máy.** Hằng số, cache, phân bổ đối tượng và kích thước miền có thể quyết định kết quả.
23. **Dùng `-1` làm sentinel kết quả công khai trong miền có khóa âm.** Tách trạng thái “không thấy” bằng `null`/`OptionalInt` hoặc một kiểu kết quả riêng.
24. **Tính `key-minKey` bằng `int` khi cận cực trị.** Phải mở rộng sang `long` trước phép trừ.
25. **Nhận mọi miền `U` nhưng không kiểm tra lũy thừa 2.** Các công thức high/low/summary cụ thể trong bài cần `U=2^k`.
26. **Nghĩ rằng mọi phiên bản vEB đều cấp phát sẵn hoặc đều tiết kiệm O(n).** Cần phân biệt bản cổ điển, cấp phát lười và các biến thể khác.
27. **Cho rằng vEB tự có rank/select O(log log U).** Không có bất biến đếm phù hợp thì không được suy ra độ phức tạp ấy.
28. **Đánh giá kiểm thử theo riêng `member`.** Lỗi summary hoặc cache min/max có thể làm ordered queries sai mà membership vẫn đúng.
29. **Dùng vòng quét toàn miền trong mỗi update rồi gọi tổng chi phí O(log log U).** Validator O(U) là phần bổ sung để debug, không phải thao tác nền của vEB.
30. **Nhầm vEB với B-tree lưu trên đĩa.** Một cấu trúc phân rã miền khóa không tự động có đặc tính I/O của chỉ mục phân trang.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Định nghĩa ngắn gọn cây van Emde Boas và loại khóa nó khai thác.

**Đáp án:** Đây là cấu trúc ordered set cho **khóa số nguyên trong miền hữu hạn**, phân rã miền đệ quy thành các cụm gần căn bậc hai kích thước ban đầu và dùng một summary chỉ các cụm có khóa.

**Câu 2.** Phân biệt `U`, `n` và `w`.

**Đáp án:** `U` là số khóa có thể có; `n` là số khóa đang lưu; `w` là số bit trong từ máy theo mô hình sử dụng.

**Câu 3.** Vì sao bản vEB cổ điển thường giả định `U=2^k`?

**Đáp án:** Nhờ đó có thể chia khóa thành phần bit cao/thấp với kích thước nguyên, tách thành `H` cụm mỗi cụm `L` khóa và `HL=U`.

**Câu 4.** Với `U=16`, tính `L`, `H`, `high(13)` và `low(13)`.

**Đáp án:** `L=4,H=4,high(13)=3,low(13)=1`.

**Câu 5.** Với `U=32`, vì sao không nên chọn `H=L=\lfloor\sqrt{32}\rfloor`?

**Đáp án:** `\lfloor\sqrt{32}\rfloor=5`, nhưng `5\cdot5=25\ne32`. Chia 5 bit thành `k_{\mathrm{low}}=2` và `k_{\mathrm{high}}=3` cho `L=4,H=8`.

**Câu 6.** Hàm `index(h,l)` dùng để làm gì?

**Đáp án:** Ghép cụm `h` với khóa cục bộ `l` để nhận khóa ở miền cha: `index(h,l)=hL+l`.

**Câu 7.** Một nút vEB có bốn thành phần logic nào?

**Đáp án:** `min`, `max`, `summary` và các `clusters`.

**Câu 8.** `summary` lưu những giá trị nào?

**Đáp án:** Các **chỉ số `h` của những cluster đang không rỗng**, không phải trực tiếp các khóa gốc nằm trong cluster.

**Câu 9.** Khóa nhỏ nhất `min` của một nút có được lưu đồng thời trong cluster của chính nút đó không?

**Đáp án:** Không trong vEB cổ điển của bài; min được rút ra khỏi các cụm của nút.

**Câu 10.** Còn `max` có luôn được rút khỏi các cluster không?

**Đáp án:** Không. Max thường vẫn được lưu trong cluster tương ứng, còn trường `max` tại nút là thông tin cache.

**Câu 11.** Với `S=\{2,3,7,12,15\}` trong miền `U=16`, summary ở gốc là tập nào?

**Đáp án:** `\{0,1,3\}` vì min=2 được giữ ở gốc, còn các cụm 0, 1 và 3 có khóa khác min.

**Câu 12.** Vì sao `cluster[0]` trong ví dụ trên chỉ chứa `\{3\}`, không phải `\{2,3\}`?

**Đáp án:** Khóa 2 là min của nút gốc nên không nằm trong cluster; khóa 3 có `high=0,low=3`.

**Câu 13.** Nếu tập rỗng, `min` và `max` có trạng thái gì?

**Đáp án:** Cả hai cùng là dấu rỗng, và không có cụm hoạt động trong summary.

**Câu 14.** Khi `insert(x)` gặp một nút rỗng, cần sửa những gì?

**Đáp án:** Đặt `min=max=x`. Chưa cần thêm vào cluster hoặc summary của nút.

**Câu 15.** Tại sao khi thêm khóa nhỏ hơn min cũ lại phải chèn min cũ vào một cluster?

**Đáp án:** Vì min mới sẽ nằm ngoài các cụm; min cũ vẫn thuộc tập nên cần được biểu diễn trong cụm để không mất khóa khi tìm/xóa theo cấu trúc.

**Câu 16.** Khi thêm phần tử đầu tiên vào một cluster rỗng, cần cập nhật gì?

**Đáp án:** Thêm chỉ số cụm `h` vào summary và đặt min/max của cluster thành `low(x)`.

**Câu 17.** Với `S=\{2,3,7,12,15\}`, `successor(8)` và `predecessor(12)` là gì?

**Đáp án:** `successor(8)=12` và `predecessor(12)=7`.

**Câu 18.** Vì sao `predecessor(3)` cần xét min khi summary không có cụm trước cụm hiện tại?

**Đáp án:** Vì khóa min=2 được giữ **ngoài cluster**, và chính là khóa lớn nhất nhỏ hơn 3.

**Câu 19.** Khi xóa min=2 của tập `\{2,3,7,12,15\}`, min mới và summary ở gốc là gì?

**Đáp án:** Min mới là 3, sau khi xóa bản sao 3 khỏi cluster[0] khiến nó rỗng thì summary đổi từ `\{0,1,3\}` thành `\{1,3\}`.

**Câu 20.** Nếu xóa khóa lớn nhất của một cluster nhưng cluster vẫn còn khóa, cập nhật max ở nút cha thế nào?

**Đáp án:** Nếu đó là max của nút cha, đặt `max=index(h,cluster[h].max)`.

**Câu 21.** Nếu xóa làm cluster của max rỗng, làm sao tìm max mới?

**Đáp án:** Xóa `h` khỏi summary; nếu summary rỗng thì `max=min`, nếu không lấy chỉ số cụm lớn nhất trong summary và ghép với max của cụm đó.

**Câu 22.** Vì sao delete chuẩn vẫn O(log log U) dù đôi khi có lời gọi xóa trên cả cluster và summary?

**Đáp án:** Khi cụm trở về rỗng, xóa ở cụm là **xóa khóa duy nhất** nên O(1); chỉ nhánh cập nhật summary có thể đệ quy sâu. Nếu cụm chưa rỗng, không xóa gì khỏi summary.

**Câu 23.** Độ phức tạp lý thuyết của `minimum` và `maximum` trong vEB cổ điển là bao nhiêu?

**Đáp án:** O(1), vì đọc trực tiếp trường `min/max` của gốc.

**Câu 24.** Tại sao các phép `member`, `insert`, `delete` và successor của vEB có O(log log U) theo miền?

**Đáp án:** Mỗi mức đệ quy giảm số bit còn lại xuống xấp xỉ một nửa, tức giảm miền từ `U` xuống gần `\sqrt U`, và chỉ có một lời gọi đệ quy sâu ở mỗi mức.

**Câu 25.** Với `U=2^{32}` và chỉ `n=100` khóa, vấn đề lớn nhất của bản vEB cấp phát toàn bộ là gì?

**Đáp án:** **Không gian/khởi tạo theo `U`** có thể quá lớn so với 100 khóa; O(log log U) cho truy vấn không bù được việc cấp phát miền khổng lồ.

**Câu 26.** Trong chương trình Java, vì sao phải chuẩn hóa khóa công khai `x` thành offset `x-minKey`?

**Đáp án:** Các nút vEB đệ quy xử lý miền cục bộ không âm `0..U-1`; offset cho phép khóa có thể âm và giữ đúng chỉ số, với phép trừ phải thực hiện trong kiểu `long` đủ rộng.

**Câu 27.** `predecessor(x)` khác `floor(x)` thế nào khi `x` có mặt trong tập?

**Đáp án:** Predecessor đòi khóa **nhỏ hơn hẳn** `x`, còn floor cho phép trả chính `x`.

**Câu 28.** Tại sao bộ kiểm tra phải đối chiếu summary với các cluster không rỗng, không chỉ so số lượng khóa?

**Đáp án:** Summary có thể thiếu hoặc thừa một chỉ số cụm nhưng tổng số khóa ở các cụm vẫn đúng; lỗi đó làm predecessor/successor sai dù membership và size có thể chưa phát hiện.

## 18. Tóm tắt và sơ đồ quyết định

**Ý tưởng trung tâm của vEB** là **chia miền khóa nguyên thành các cụm có độ rộng gần căn bậc hai của U**, quản lý cụm có khóa bằng một `summary` đệ quy, và giữ **`min/max` ngay tại nút**. Kết quả là:

\[
\begin{array}{ll}
\text{minimum, maximum} & O(1),\\
\text{member, insert, delete} & O(\log\log U),\\
\text{predecessor, successor} & O(\log\log U),\\
\text{không gian bản cổ điển} & O(U).
\end{array}
\]

Một cách chọn cấu trúc dữ liệu theo nhu cầu:

```text
Có một miền khóa số nguyên hữu hạn?
  |
  +-- Không -> dùng cấu trúc khóa tổng quát (hash/tree...)
  |
  +-- Có:
       |
       +-- Chỉ cần membership, U nhỏ?
       |      -> bitset/bảng địa chỉ trực tiếp
       |
       +-- Cần thứ tự, U rất lớn nhưng n nhỏ?
       |      -> cây cân bằng / cấu trúc sparse phù hợp
       |
       +-- Cần prefix/XOR theo bit?
       |      -> binary trie hoặc Patricia trie
       |
       +-- Cần predecessor/successor nhanh theo U,
              chấp nhận O(U) bộ nhớ và khởi tạo?
              -> cân nhắc van Emde Boas tree
```

**Điểm ghi nhớ:** `min` được **tách khỏi các cluster**, `max` được **cache**, còn `summary` phải chứa **đúng những chỉ số cụm không rỗng**. Chèn khóa nhỏ hơn min phải chuyển min cũ xuống cụm; xóa min phải nâng khóa nhỏ nhất còn lại rồi xóa nó khỏi cụm. Sai một trong những bất biến này có thể khiến truy vấn predecessor/successor sai dù kiểm tra thuộc tập vẫn có vẻ đúng. **Độ phức tạp O(log log U) là lợi thế theo miền số**, nhưng phải luôn đặt cạnh **O(U) không gian của bản cổ điển** và nhu cầu bộ nhớ, cập nhật, truy vấn thực tế của hệ thống.
