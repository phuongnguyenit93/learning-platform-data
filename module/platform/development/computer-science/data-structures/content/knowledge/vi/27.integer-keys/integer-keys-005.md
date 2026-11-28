# Truy vấn tiền nhiệm, kế nhiệm và phần tử nhỏ nhất theo miền số

Một cấu trúc dữ liệu có thể trả lời rất nhanh câu hỏi **“khóa 70 có tồn tại không?”** nhưng lại gặp khó với câu hỏi **“khóa nào lớn nhất mà vẫn nhỏ hơn 70?”**. Hai câu hỏi này khác nhau: phép đầu tiên là **kiểm tra thuộc tập** (*membership*), còn phép thứ hai là **truy vấn thứ tự** (*ordered-set query*).

Đối với **khóa số nguyên trong một miền hữu hạn**, ta có thể khai thác cách biểu diễn khóa bằng bit để tìm **tiền nhiệm** (*predecessor*), **kế nhiệm** (*successor*), **phần tử nhỏ nhất** (*minimum*) và **phần tử nhỏ nhất trong một đoạn**. Những phép toán này có mặt trong bộ lập lịch, quản lý ID đang dùng, cấp phát ô trống, xử lý thời điểm sự kiện, truy vấn chỉ mục, đồ thị và thuật toán tìm kiếm.

Tuy nhiên, biết khóa thuộc miền nhỏ không tự động khiến mọi truy vấn thứ tự có thời gian O(1). **Mảng địa chỉ trực tiếp** có thể trả lời `contains(x)` bằng một truy cập nhưng phải quét nhiều ô trống để tìm kế nhiệm; **bitset** giảm bước quét bằng phép toán bit; **bitmap nhiều cấp** dùng thông tin tóm tắt để bỏ qua cả nhóm từ rỗng; **cây tìm kiếm cân bằng** giữ thứ tự mà không cần cấp phát theo toàn miền.

Bài này xác định chính xác quy ước so sánh, giải thích cách tìm min/max, tiền nhiệm/kế nhiệm từ số nguyên và từ máy, phân tích các cấu trúc theo `U`, `n`, `w`, rồi cài đặt Java tự chứa một **tập khóa nguyên với bitmap hai cấp**, hỗ trợ tìm trước/sau **O(1) theo số từ được giới hạn trong ví dụ**.

## 1. Mô hình tập khóa hữu hạn và các quy ước

Cho miền khóa liên tục:

\[
\mathcal U=\{a,a+1,\ldots,b\},\qquad U=b-a+1,
\]

và tập `S\subseteq\mathcal U` gồm `n` **khóa phân biệt**, với `0\le n\le U`. Tất cả khóa đều được so sánh theo **thứ tự số nguyên tăng dần**.

Ba tham số thường xuất hiện:

| Ký hiệu | Nghĩa |
| --- | --- |
| `U` | Số giá trị khóa **có thể** xuất hiện trong miền |
| `n` | Số khóa **đang** có trong tập |
| `w` | Số bit của một từ trong mô hình Word-RAM |

Ví dụ quản lý mã từ `0` đến `255`:

\[
U=256.
\]

Giả sử:

\[
S=\{2,5,70,120,254\},\quad n=5.
\]

Tập có năm phần tử đang lưu, dù miền có 256 giá trị có thể sử dụng.

### Truy vấn được định nghĩa ngay cả khi khóa hỏi không có trong tập

Ta có thể hỏi `predecessor(71)` dù khóa 71 chưa từng được chèn. Thuật toán tìm **mục gần nhất theo thứ tự**, chứ không yêu cầu đối số truy vấn đang thuộc tập.

Cần phân biệt:

- **Khóa lưu trữ:** phải thuộc miền khi `insert`.
- **Giá trị dùng làm ngưỡng truy vấn:** có thể không thuộc `S`, thậm chí nằm ngoài đoạn `[a,b]` nếu API cho phép. Ví dụ Java của bài chấp nhận ngưỡng truy vấn là một số nguyên bất kỳ nhưng vẫn từ chối `add/remove/contains` ngoài miền.

Phân biệt này giúp xử lý ranh giới một cách tự nhiên: `successor(-100)` trong một tập khóa từ 0 trở lên có thể trả khóa nhỏ nhất của tập.

## 2. Tiền nhiệm, kế nhiệm, floor và ceiling

Cùng một tập `S`, bốn truy vấn cơ bản **không giống nhau**.

### Tiền nhiệm nghiêm ngặt: `predecessor(x)`

Là khóa lớn nhất trong `S` **nhỏ hơn hẳn** `x`:

\[
\boxed{
\operatorname{pred}_S(x)=\max\{y\in S\mid y<x\}.
}
\]

Nếu tập trong ngoặc rỗng, kết quả là **không có** (*not found*), không tự động trả 0 hoặc `-1`.

### Kế nhiệm nghiêm ngặt: `successor(x)`

Là khóa nhỏ nhất trong `S` **lớn hơn hẳn** `x`:

\[
\boxed{
\operatorname{succ}_S(x)=\min\{y\in S\mid y>x\}.
}
\]

### Floor: `floor(x)`

Là khóa lớn nhất **không vượt** `x`:

\[
\boxed{
\operatorname{floor}_S(x)=\max\{y\in S\mid y\le x\}.
}
\]

Nếu `x\in S`, thì `floor(x)=x`.

### Ceiling: `ceiling(x)`

Là khóa nhỏ nhất **không nhỏ hơn** `x`:

\[
\boxed{
\operatorname{ceil}_S(x)=\min\{y\in S\mid y\ge x\}.
}
\]

Nếu `x\in S`, thì `ceiling(x)=x`.

### Bảng ví dụ

Với `S=\{2,5,70,120,254\}`:

| Ngưỡng `x` | `predecessor(x)` | `floor(x)` | `ceiling(x)` | `successor(x)` |
| ---: | ---: | ---: | ---: | ---: |
| 0 | Không có | Không có | 2 | 2 |
| 5 | 2 | 5 | 5 | 70 |
| 6 | 5 | 5 | 70 | 70 |
| 70 | 5 | 70 | 70 | 120 |
| 71 | 70 | 70 | 120 | 120 |
| 254 | 120 | 254 | 254 | Không có |
| 300 | 254 | 254 | Không có | Không có |

Từ bảng, khi **ngưỡng bằng một khóa đang có**, kết quả strict và inclusive có thể khác nhau rất rõ.

### Quy ước tên API không phải lúc nào cũng giống nhau

Một số tài liệu gọi “successor” là khóa **lớn hơn hoặc bằng** `x`; tài liệu khác gọi nó là khóa **lớn hơn hẳn** `x`. Để tránh sai:

1. Nói rõ dùng dấu `<`, `>`, `\le` hay `\ge`.
2. Đặt tên hàm theo quy ước của thư viện hoặc tách `successor` và `ceiling` thành hai hàm.
3. Viết test với `x` **đang có trong tập** và `x` **vắng mặt**.

Bài này dùng **predecessor/successor nghiêm ngặt**, còn **floor/ceiling bao gồm dấu bằng**.

## 3. Minimum, maximum và phần tử nhỏ nhất trong đoạn

**Phần tử nhỏ nhất của tập**:

\[
\operatorname{minimum}(S)=\min\{x\mid x\in S\}.
\]

**Phần tử lớn nhất**:

\[
\operatorname{maximum}(S)=\max\{x\mid x\in S\}.
\]

Nếu `S=\varnothing`, cả hai phép **không có kết quả**, không phải số 0.

Với ví dụ `S=\{2,5,70,120,254\}`:

```text
minimum(S) = 2
maximum(S) = 254
```

### Phần tử nhỏ nhất thuộc một đoạn số

Xét:

\[
\operatorname{rangeMin}(l,r)
=\min\{x\in S\mid l\le x\le r\}.
\]

Ta có thể đưa truy vấn này về **ceiling**:

1. Tính `c=ceiling(l)`.
2. Nếu không có `c` hoặc `c>r`, đoạn không chứa khóa.
3. Ngược lại, `c` là phần tử nhỏ nhất của `S` trong `[l,r]`.

Theo công thức:

\[
\boxed{
\operatorname{rangeMin}(l,r)=
\begin{cases}
\operatorname{ceiling}(l),& \operatorname{ceiling}(l)\le r,\\
\text{không có},&\text{trường hợp khác}.
\end{cases}
}
\]

Hàm cũng phải trả rỗng nếu `l>r`.

Với `S=\{2,5,70,120,254\}`:

| Đoạn | Phần tử nhỏ nhất thuộc đoạn |
| --- | --- |
| `[6,119]` | 70 |
| `[70,120]` | 70 |
| `[71,119]` | Không có |
| `[121,254]` | 254 |
| `[255,500]` | Không có |

**Chú ý:** “phần tử nhỏ nhất trong đoạn” ở đây là **khóa nhỏ nhất thuộc tập `S` nằm trong đoạn miền số**, không phải bài toán **range minimum query (RMQ) trên mảng giá trị**. RMQ trên mảng tìm **giá trị nhỏ nhất trong một đoạn chỉ số** và có kỹ thuật xử lý khác.

### Các phép toán liên hệ

Từ các truy vấn đã định nghĩa:

\[
\operatorname{minimum}(S)=\operatorname{ceiling}(-\infty),
\qquad
\operatorname{maximum}(S)=\operatorname{floor}(+\infty),
\]

theo nghĩa khái niệm. Trên kiểu `int`, có thể dùng cận `Integer.MIN_VALUE` và `Integer.MAX_VALUE` hoặc triển khai `minimum/maximum` riêng; **không cần tạo giá trị vô cực thực** trong Java.

## 4. Hai cách tìm tiền nhiệm và kế nhiệm đơn giản

Trước khi dùng kỹ thuật bit, hãy xét các cấu trúc cơ bản.

### 4.1. Mảng địa chỉ trực tiếp

Giả sử miền `0..9` có cờ tồn tại:

```text
index:      0 1 2 3 4 5 6 7 8 9
present:    0 0 1 0 0 1 0 0 1 0
                  ^     ^     ^
S = {2,5,8}
```

Kiểm tra `contains(5)` chỉ đọc `present[5]` — O(1).

Nhưng `predecessor(8)` theo cách đơn giản phải kiểm tra `present[7]`, `present[6]`, rồi `present[5]`. Với một đoạn trống rất dài, phải đọc nhiều ô.

Mã giả:

```text
predecessor(x):
    i = min(x - 1, U - 1)
    while i >= 0:
        if present[i]:
            return i
        i--
    return NOT_FOUND

successor(x):
    i = max(x + 1, 0)
    while i < U:
        if present[i]:
            return i
        i++
    return NOT_FOUND
```

Đây là mã giả miền `0..U-1`. Trong chương trình có kiểu `int` và ngưỡng cực trị, tính `x\pm1` nên dùng kiểu đủ rộng trước khi kiểm tra cận.

**Độ phức tạp:** O(U) trong trường hợp xấu nhất cho tiền nhiệm/kế nhiệm/min bằng quét. Bảng địa chỉ trực tiếp chỉ đảm bảo O(1) cho **truy vấn một vị trí xác định**, không tự đảm bảo O(1) cho tìm vị trí có khóa gần nhất.

### 4.2. Danh sách khóa đã sắp

Nếu các khóa thực `n` được lưu trong một mảng tăng:

```text
sorted = [2, 5, 70, 120, 254]
```

Ta có thể dùng tìm kiếm nhị phân:

- `lower_bound(x)`: vị trí đầu tiên có khóa `\ge x`.
- `upper_bound(x)`: vị trí đầu tiên có khóa `>x`.

| Truy vấn | Vị trí cần lấy |
| --- | --- |
| `ceiling(x)` | `lower_bound(x)` |
| `successor(x)` | `upper_bound(x)` |
| `predecessor(x)` | Một vị trí trước `lower_bound(x)` |
| `floor(x)` | Một vị trí trước `upper_bound(x)` |

Điều kiện phải kiểm tra trước khi truy cập:

- Nếu vị trí bằng `n`, không có mục ở bên phải.
- Nếu vị trí trừ một nhỏ hơn 0, không có mục ở bên trái.

**Ưu điểm:** O(log n) tìm tiền nhiệm/kế nhiệm, O(1) lấy min/max nếu mảng không rỗng, O(n) bộ nhớ cho các khóa.

**Nhược điểm:** thêm/xóa ở giữa mảng đã sắp cần dịch phần tử, O(n) trong trường hợp xấu nhất. Một tập thưa **ít cập nhật, đọc nhiều** có thể hợp với biểu diễn này.

## 5. Bitset: giảm quét từng ô thành quét từng từ

Với miền `0..U-1`, bitset dùng **một bit trên mỗi khóa khả dĩ**. Nếu máy xử lý `w` bit trong một từ, vị trí `i` thuộc:

\[
q=\left\lfloor\frac{i}{w}\right\rfloor,\qquad
b=i\bmod w.
\]

Ở Java với `long` 64 bit:

```java
int wordIndex = i >>> 6;   // i / 64, khi i không âm
int bitIndex  = i & 63;    // i % 64
long mask = 1L << bitIndex;
```

### Truy vấn thuộc tập

```java
boolean present = (words[wordIndex] & mask) != 0L;
```

Một lần đọc từ và AND mask: O(1) trong mô hình Word-RAM với mảng được cấp phát và khóa/chỉ số hợp lệ.

### Tìm khóa nhỏ nhất trong một từ

Cho `word` khác 0. Bit 1 ít quan trọng nhất (*least significant set bit*) là bit có chỉ số:

```java
int first = Long.numberOfTrailingZeros(word);
```

Ví dụ:

```text
word low bits:       0010 1000
bit 3 và bit 5 bật

numberOfTrailingZeros(word) = 3
```

Đối với bit 1 cao nhất:

```java
int last = 63 - Long.numberOfLeadingZeros(word);
```

**Bắt buộc kiểm tra `word!=0` trước khi dùng hai kết quả làm chỉ số khóa.** Trong Java:

```text
Long.numberOfTrailingZeros(0L) = 64
Long.numberOfLeadingZeros(0L)  = 64
```

Với từ có bit 63 bật, giá trị `long` có thể mang dấu âm; các hàm bit của Java vẫn hoạt động đúng trên **mẫu 64 bit**.

### Tìm phần tử kế tiếp trong cùng một từ

Giả sử cần `ceiling(x)`, đã ánh xạ `x` sang bit `b`. Loại các bit đứng trước `b`:

```java
long candidates = word & (-1L << b); // 0 <= b < 64
```

Nếu `candidates != 0`, lấy `Long.numberOfTrailingZeros(candidates)`. Đối với `successor(x)` nghiêm ngặt, phải bỏ cả bit `b`:

```java
long after = (b == 63)
    ? 0L
    : (word & (-1L << (b + 1)));
```

Kiểm tra `b==63` là cần thiết: dịch `long` 64 vị trí trong Java được diễn giải như dịch 0, không phải một từ toàn 0.

### Tìm tiền nhiệm trong cùng một từ

Đối với `floor(x)`, giữ lại các bit từ 0 đến `b`:

```java
long maskIncludingB = (b == 63)
    ? -1L
    : ((1L << (b + 1)) - 1L);
long candidates = word & maskIncludingB;
```

Nếu còn bit 1, khóa mong muốn là **bit cao nhất còn lại**:

```java
int answerBit = 63 - Long.numberOfLeadingZeros(candidates);
```

Đối với `predecessor(x)` nghiêm ngặt, chỉ giữ các bit **nhỏ hơn `b`**:

```java
long maskBeforeB = (b == 0)
    ? 0L
    : ((1L << b) - 1L);
```

### Nếu từ hiện tại không còn bit phù hợp?

Ta phải tìm một **từ khác 0 ở phía trước hoặc phía sau**. Cách đơn giản:

```text
ceiling(x):
    kiểm tra các bit >= offset(x) trong words[q]
    nếu có -> trả bit 1 thấp nhất
    nếu không:
        q++
        while q < wordCount and words[q] == 0:
            q++
        nếu hết -> không có
        trả bit 1 thấp nhất của words[q]
```

So với mảng cờ, mỗi vòng lặp quét **một từ `w` bit** thay vì một khóa. Nhưng nếu có rất nhiều từ rỗng:

\[
\boxed{T_{\text{successor}}=O(\lceil U/w\rceil)}
\]

trong trường hợp xấu nhất đối với cách quét tuyến tính từ máy, chưa tính chi phí cấp phát/khởi tạo.

## 6. Bitmap hai cấp: tóm tắt những từ không rỗng

Để **không quét từng từ rỗng**, ta có thể bổ sung một **bitmap tóm tắt** (*summary bitmap*).

Giả sử miền có tối đa `U=4096` khóa sau chuẩn hóa. Dùng từ 64 bit:

\[
\left\lceil\frac{4096}{64}\right\rceil=64
\]

từ dữ liệu. Chỉ cần **một từ 64 bit `summary`** để đánh dấu từ dữ liệu nào có ít nhất một bit bật.

### Cấu trúc

```text
                summary: 64 bit
             [ 1 0 0 1 0 1 ... ]
                |     |   |
                v     v   v
data words:    W0    W3  W5       ... W63
               64b   64b 64b

summary bit q = 1  <=>  words[q] != 0
```

Ví dụ, `words[0]` có khóa 3, `words[3]` có khóa 198, `words[5]` có khóa 333; những từ còn lại rỗng. Khi đó summary bật các bit 0, 3, 5. Nếu một truy vấn cần bỏ qua mọi từ sau 0 và trước 3, ta chỉ cần **một phép lọc bit trên summary**, thay vì đọc `words[1]`, `words[2]`.

### Bất biến quan trọng

\[
\boxed{
\text{bit}_q(summary)=1
\iff words[q]\ne0
}
\]

đối với mọi `0\le q<\lceil U/64\rceil`.

Đây là điều kiện bắt buộc. Nếu xóa phần tử cuối của một từ nhưng không xóa bit summary tương ứng, thuật toán có thể chọn một từ rỗng rồi tính bit bằng một kết quả không hợp lệ.

Nếu thêm phần tử đầu tiên vào một từ đang rỗng mà quên cập nhật summary, các phép tìm kế nhiệm và minimum có thể **bỏ qua cả từ ấy**.

### Chèn

```text
q = offset(x) / 64
b = offset(x) % 64

old = words[q]
if bit b đã bật: không đổi
else:
    words[q] |= (1L << b)
    if old == 0:
        summary |= (1L << q)
    size++
```

### Xóa

```text
q = offset(x) / 64
b = offset(x) % 64

if bit b chưa bật: không đổi
else:
    words[q] &= ~(1L << b)
    if words[q] == 0:
        summary &= ~(1L << q)
    size--
```

Các thao tác này cập nhật **một từ dữ liệu và một bit summary**, nên có thời gian O(1) trong mô hình với tối đa 64 từ dữ liệu.

### Tìm minimum và maximum

Nếu `summary==0`, tập rỗng.

Nếu không:

1. **Minimum:** lấy vị trí bit 1 thấp nhất của summary → từ dữ liệu đầu tiên khác 0; sau đó lấy bit 1 thấp nhất của từ đó.
2. **Maximum:** lấy vị trí bit 1 cao nhất của summary → từ dữ liệu cuối cùng khác 0; sau đó lấy bit 1 cao nhất của từ đó.

```text
minimum:
  q = trailingZeros(summary)
  b = trailingZeros(words[q])
  offset = 64*q + b

maximum:
  q = 63 - leadingZeros(summary)
  b = 63 - leadingZeros(words[q])
  offset = 64*q + b
```

Nhờ summary, không cần quét qua nhiều từ rỗng để tìm min/max. **Trong cấu trúc giới hạn `U\le4096` này**, cả hai phép là O(1) với từ 64 bit.

## 7. Tiền nhiệm và kế nhiệm bằng summary

### Tìm ceiling(x)

Cho vị trí bit đã chuẩn hóa `i`, `q=i/64` và `b=i\%64`:

1. Trong `words[q]`, lấy các bit **`\ge b`**.
2. Nếu có bit 1, chọn bit 1 thấp nhất và trả khóa.
3. Nếu không, từ `summary` chỉ giữ những bit **có chỉ số lớn hơn `q`**.
4. Lấy bit 1 thấp nhất trong phần summary còn lại. Nó chỉ tới **từ dữ liệu gần nhất về bên phải có khóa**.
5. Lấy bit 1 thấp nhất của từ được chọn.

```text
Trong words[q]:
  candidates = words[q] & (-1L << b)

Nếu candidates == 0:
  nextWords = summary & mask(indices > q)
  nếu nextWords == 0 -> không có
  q2 = trailingZeros(nextWords)
  b2 = trailingZeros(words[q2])
  return minKey + 64*q2 + b2
```

Chú ý **`q=63`**: không có từ thứ 64 trong summary, nên mask bên phải phải bằng 0; không tính `-1L << 64` rồi tưởng kết quả rỗng.

### Tìm floor(x)

1. Trong `words[q]`, lấy các bit **`\le b`**.
2. Nếu còn bit 1, chọn bit 1 cao nhất.
3. Nếu không, từ `summary` chỉ giữ các bit **có chỉ số nhỏ hơn `q`**.
4. Chọn bit 1 cao nhất của phần summary còn lại.
5. Chọn bit 1 cao nhất của từ dữ liệu tương ứng.

```text
candidates = words[q] & mask(bits <= b)

Nếu candidates == 0:
  previousWords = summary & mask(indices < q)
  nếu previousWords == 0 -> không có
  q2 = highestSetBit(previousWords)
  b2 = highestSetBit(words[q2])
  return minKey + 64*q2 + b2
```

### Đưa truy vấn nghiêm ngặt về truy vấn bao gồm dấu bằng

Vì khóa là **số nguyên rời rạc**:

\[
\boxed{
\operatorname{predecessor}(x)=\operatorname{floor}(x-1)
}
\]

và

\[
\boxed{
\operatorname{successor}(x)=\operatorname{ceiling}(x+1)
}
\]

với điều kiện phép tính `x-1`, `x+1` **không tràn**.

Ví dụ Java sẽ nhận ngưỡng dưới dạng `long` khi tính trung gian, nên:

```java
Integer predecessor(int x) {
    return floor((long) x - 1L);
}

Integer successor(int x) {
    return ceiling((long) x + 1L);
}
```

Cách này an toàn ngay cả với `x=Integer.MIN_VALUE` hoặc `x=Integer.MAX_VALUE` vì trừ/cộng được thực hiện trong `long`.

### Ví dụ vượt ranh giới từ máy

Miền chuẩn hóa `0..255`, tập:

```text
S = {5, 63, 64, 70, 190, 200}
```

```text
words[0] giữ khóa 5, 63
words[1] giữ khóa 64, 70
words[2] giữ khóa 190
words[3] giữ khóa 200

summary có các bit 0,1,2,3 bật.

successor(63) = 64   (chuyển sang từ tiếp theo)
predecessor(64) = 63 (chuyển về từ trước)
ceiling(71) = 190    (bỏ qua phần còn lại của words[1])
floor(199) = 190
minimum = 5
maximum = 200
```

Phần khó nhất không phải lấy min/max trong một từ, mà là **duy trì summary đúng sau nhiều lần thêm và xóa**, nhất là khi một từ đổi từ rỗng sang không rỗng hoặc ngược lại.

## 8. Nếu miền lớn hơn 4096 thì sao?

Một từ summary chỉ có 64 bit nên **không thể** tóm tắt trực tiếp hơn 64 từ dữ liệu. Với `U>4096`, có thể tạo **nhiều tầng bitmap tóm tắt**:

```text
Tầng 0: bitmap của tất cả U khóa
Tầng 1: mỗi bit đại diện một từ không rỗng ở tầng 0
Tầng 2: mỗi bit đại diện một từ không rỗng ở tầng 1
...
Tầng cuối: một từ hoặc số từ rất nhỏ
```

Với từ `w` bit:

| Tầng | Số từ ở bậc lớn |
| --- | --- |
| Dữ liệu | `\lceil U/w\rceil` |
| Tóm tắt 1 | `\lceil U/w^2\rceil` |
| Tóm tắt 2 | `\lceil U/w^3\rceil` |
| ... | ... |

Nếu duy trì các tầng và tìm theo các bit không rỗng, số tầng là:

\[
\boxed{O(\log_w U)}
\]

trong mô hình từ có `w` bit và thao tác trên từ được tính O(1). Bộ nhớ phụ của các tầng tóm tắt là một chuỗi hình học:

\[
O\left(\frac{U}{w^2}+\frac{U}{w^3}+\cdots\right)\text{ từ},
\]

ngoài `O(U/w)` từ dữ liệu. Tổng dung lượng vẫn là **O(U) bit** theo bậc lớn. Với `w=64`, số tầng khá ít cho những miền vừa phải, nhưng **không được gọi thời gian tổng quát là O(1) độc lập với `U`**.

### Cần điều chỉnh cả thuật toán cập nhật

Khi một từ của tầng thấp chuyển từ 0 sang khác 0, phải bật bit của nó trong tầng trên. Nếu **từ của tầng trên** cũng chuyển từ 0 sang khác 0, tiếp tục lan thay đổi. Xóa phần tử cuối cũng cần lan việc tắt bit qua những tầng trở thành rỗng.

Việc xây đúng các tầng này đòi hỏi quản lý biên của mỗi nhóm `w` từ, chỉ số từ cuối và xử lý những nhóm không đầy. Ví dụ Java bên dưới cố tình giới hạn `U\le4096` để trình bày một cấu trúc **hai tầng hoàn chỉnh và dễ xác minh**, không giả vờ đã cài đặt phiên bản nhiều tầng.

## 9. Các cấu trúc khác cho ordered-set queries

Không phải mọi ứng dụng đều muốn cấp phát bitmap theo `U`. Bảng dưới đây nêu những lựa chọn thường gặp:

| Cấu trúc | `contains` | `pred/succ` | Min/max | Bộ nhớ chính | Đánh đổi |
| --- | --- | --- | --- | --- | --- |
| Mảng cờ trực tiếp | O(1) | O(U) khi quét | O(U) khi quét | O(U) ô/bit | Đơn giản, miền nhỏ |
| Bitset chia từ không tóm tắt | O(1) | O(⌈U/w⌉) worst-case khi quét | O(⌈U/w⌉) khi quét | O(U) bit | Bỏ qua 64 vị trí mỗi từ |
| **Bitmap hai cấp** `U\le w^2` | **O(1)** | **O(1)** | **O(1)** | O(U/w) từ + một summary | Miền giới hạn, xử lý bit cẩn thận |
| Bitmap tóm tắt nhiều cấp | O(1) | O(log_w U) | O(log_w U) | O(U) bit | Cần bảo trì nhiều tầng |
| Mảng khóa đã sắp | O(log n) | O(log n) | O(1) | O(n) khóa | Chèn/xóa O(n) do dịch mảng |
| AVL/Red-Black | O(log n) | O(log n) | O(log n), hoặc O(1) nếu giữ con trỏ tới biên | O(n) nút | Duy trì cân bằng |
| B-tree/B+ tree phân trang | Theo chiều cao và tìm trong nút | Dựa vào đường tìm/iterator lá | Dựa vào đường biên | Theo số mục và trang | Phù hợp chỉ mục có I/O |
| Sparse set hai mảng không sắp | O(1) | O(n) nếu quét dense | O(n) nếu quét dense | O(U+n) ô | Duyệt tập O(n), không duy trì thứ tự |
| Bảng băm thông thường | O(1) trung bình/kỳ vọng | O(n) nếu quét các khóa | O(n) nếu quét | O(n) theo tải | Không duy trì thứ tự |

Chi phí min/max ghi trong bảng dành cho **truy vấn độc lập trên cấu trúc cơ bản**. Một cây hoặc bảng có thể **lưu thêm con trỏ/phần tử min và max** để truy vấn nhanh hơn, nhưng khi xóa đúng phần tử cực trị phải tìm giá trị thay thế; không có nghĩa mọi cấu trúc mặc định hỗ trợ xóa min mà không tốn công.

### Trie nhị phân

Một **binary trie** duyệt từng bit khóa, mỗi bước chọn nhánh 0/1. Với khóa `w` bit, thao tác cơ bản có thể mất O(w) bước; có thể bổ sung số lượng nút con hoặc điều hướng để tìm khóa gần nhất. Nó khai thác **biểu diễn nguyên theo bit**, nhưng không tự bảo đảm O(1) khi `w` là tham số tăng.

### van Emde Boas tree

**Van Emde Boas tree** (vEB) là cấu trúc lý thuyết cho khóa nguyên trên một miền hữu hạn (thường giả định `U` là lũy thừa của 2). Phiên bản cổ điển hỗ trợ `insert/delete/min/max/predecessor/successor` với thời gian O(log log U) cho các phép thao tác chính trong mô hình thích hợp, nhưng cấu trúc cổ điển cần **O(U) bộ nhớ** do phân rã miền, thường không phù hợp với `U` khổng lồ và rất thưa.

Ý tưởng vEB khác một bitset hai cấp đơn giản: nó phân nhóm miền theo **căn bậc hai**, lưu tóm tắt các nhóm có dữ liệu và thường duy trì **min/max** của các cụm để tránh thao tác không cần thiết. Có thể học tiếp vEB sau khi hiểu bất biến của bitmap tóm tắt.

### Khi nào chọn cây cân bằng?

Nếu `U` quá lớn nhưng `n` nhỏ, cây AVL/Red-Black hoặc ordered map thường hợp lý:

- Bộ nhớ tỷ lệ theo số khóa được lưu.
- Có `lower/floor/ceiling/higher` với O(log n) worst-case.
- Có iterator tăng dần và truy vấn khoảng.
- Không cần đánh dấu mọi giá trị khả dĩ trong miền.

**Không nên chọn chỉ dựa vào O(1) với hằng số:** một bảng bit khổng lồ có thể tốn hàng gigabyte để phục vụ vài trăm khóa; cây cân bằng O(log n) có thể nhanh và gọn hơn trong điều kiện thực tế.

## 10. Các vấn đề biên trong truy vấn thứ tự

### Tập rỗng

Với `S=\varnothing`:

```text
minimum()        -> không có
maximum()        -> không có
predecessor(x)   -> không có
successor(x)     -> không có
floor(x)         -> không có
ceiling(x)       -> không có
rangeMin(l,r)    -> không có
```

Không dùng 0 hay `-1` làm dấu không tìm thấy nếu đó có thể là **khóa hợp lệ**. Java ví dụ sẽ dùng `Integer` có thể `null` để biểu thị không có kết quả; một API khác có thể dùng `OptionalInt`.

### Khóa âm và chuẩn hóa miền

Với `[a,b]`, offset của khóa `x`:

\[
\boxed{i=x-a.}
\]

Nếu `a=-5`, khóa `-5` có offset 0, khóa `59` có offset 64 và khóa `140` có offset 145. Mọi thao tác bitmap làm việc trên **offset**; kết quả trả ra phải đổi lại thành:

\[
x=a+i.
\]

### Tràn khi lấy hiệu

Với kiểu Java `int`:

```java
long u = (long) maxKey - (long) minKey + 1L;
long index = (long) key - (long) minKey;
```

Phải chuyển sang kiểu `long` **trước khi trừ**, vì `Integer.MAX_VALUE-Integer.MIN_VALUE+1` tương ứng `2^{32}`, không vừa `int` có dấu.

### Số âm khi thao tác bit 63

Một từ `long` có bit 63 bật được biểu diễn bằng số âm theo cách hiểu **có dấu**, nhưng đây vẫn là mẫu bit hợp lệ. Các phép:

```java
Long.numberOfTrailingZeros(word)
Long.numberOfLeadingZeros(word)
Long.bitCount(word)
```

đếm trên **mẫu 64 bit**, không cần đổi từ thành số dương.

### Ngưỡng ở ngoài miền

Nếu miền `[-5,140]`:

- `ceiling(-100)` nên trả **minimum**, nếu tập không rỗng.
- `floor(1_000)` nên trả **maximum**, nếu tập không rỗng.
- `ceiling(141)` không có kết quả.
- `floor(-6)` không có kết quả.
- `predecessor(-5)` không có kết quả vì không có khóa nào thuộc miền nhỏ hơn `-5`.
- `successor(140)` không có kết quả vì không có khóa nào thuộc miền lớn hơn `140`.

Đây là lựa chọn API ở bài: **ngưỡng truy vấn có thể ở ngoài miền**. Đối với `add/remove/contains`, khóa ngoài miền sẽ bị từ chối.

### Truy vấn min trong đoạn rỗng

Khi `l>r`, `rangeMin(l,r)` phải trả không có kết quả mà không cố gắng đánh đổi thứ tự cận. Với đoạn `[l,r]` không chứa khóa nhưng miền có nhiều khóa ở nơi khác, `rangeMin` cũng phải trả rỗng.

## 11. Java hoàn chỉnh: tập số nguyên với bitmap hai cấp

Chương trình `OrderedIntBitmapDemo` xây một **tập số nguyên có thứ tự** trên miền tối đa **4096 khóa liên tiếp**:

- `words[]`: mỗi từ `long` lưu 64 bit.
- `summary`: bit `q` bật **khi và chỉ khi** `words[q]` khác 0.
- `size`: số bit bật, được duy trì cùng các phép cập nhật.
- `contains/add/remove`: kiểm tra và sửa khóa.
- `minimum/maximum`: tìm biên bằng summary.
- `floor/ceiling`: tìm trong từ hiện tại, nếu không có thì nhảy sang **từ không rỗng kế tiếp/trước đó qua summary**.
- `predecessor/successor`: strict, dựa trên floor/ceiling với ngưỡng kiểu `long` an toàn.
- `minimumInRange`: phần tử nhỏ nhất trong đoạn đóng.
- `valuesInRange`: liệt kê khóa trong đoạn tăng dần.
- `verify`: kiểm tra summary, số bit và bit ngoài miền.

**Phạm vi:** mô hình hai cấp chỉ hoạt động khi số từ dữ liệu `\le64`, tương đương `U\le4096`. Nếu cần miền lớn hơn, phải dùng bitmap nhiều cấp hoặc cấu trúc khác; không tự bỏ ràng buộc trong constructor.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class OrderedIntBitmapDemo {

    static final class BoundedOrderedSet {
        private static final int WORD_BITS = 64;
        private static final int MAX_UNIVERSE = 64 * 64;

        private final int minKey;
        private final int maxKey;
        private final int universe;
        private final long[] words;

        // Summary bit q == 1 iff words[q] != 0.
        private long summary;
        private int size;

        BoundedOrderedSet(int minKey, int maxKey) {
            if (minKey > maxKey) {
                throw new IllegalArgumentException(
                    "Invalid key interval");
            }
            long u = (long) maxKey - (long) minKey + 1L;
            if (u < 1L || u > MAX_UNIVERSE) {
                throw new IllegalArgumentException(
                    "Two-level bitmap supports at most 4096 keys");
            }
            this.minKey = minKey;
            this.maxKey = maxKey;
            this.universe = (int) u;
            int wordCount = (universe + WORD_BITS - 1) / WORD_BITS;
            this.words = new long[wordCount];
        }

        int size() {
            return size;
        }

        int universeSize() {
            return universe;
        }

        // Used only for keys that must BELONG to the bounded domain.
        private int checkedOffset(int key) {
            if (key < minKey || key > maxKey) {
                throw new IllegalArgumentException(
                    "Key outside universe: " + key);
            }
            return (int) ((long) key - (long) minKey);
        }

        private int keyFromWordAndBit(int q, int bit) {
            long offset = (long) q * WORD_BITS + bit;
            return (int) ((long) minKey + offset);
        }

        boolean contains(int key) {
            int offset = checkedOffset(key);
            int q = offset >>> 6;
            int bit = offset & 63;
            return (words[q] & (1L << bit)) != 0L;
        }

        boolean add(int key) {
            int offset = checkedOffset(key);
            int q = offset >>> 6;
            int bit = offset & 63;
            long mask = 1L << bit;
            long old = words[q];

            if ((old & mask) != 0L) {
                return false; // Key already present.
            }
            words[q] = old | mask;
            if (old == 0L) {
                summary |= (1L << q);
            }
            size++;
            return true;
        }

        boolean remove(int key) {
            int offset = checkedOffset(key);
            int q = offset >>> 6;
            int bit = offset & 63;
            long mask = 1L << bit;

            if ((words[q] & mask) == 0L) {
                return false; // Key absent.
            }
            words[q] &= ~mask;
            if (words[q] == 0L) {
                summary &= ~(1L << q);
            }
            size--;
            return true;
        }

        Integer minimum() {
            if (summary == 0L) {
                return null;
            }
            int q = Long.numberOfTrailingZeros(summary);
            int bit = Long.numberOfTrailingZeros(words[q]);
            return keyFromWordAndBit(q, bit);
        }

        Integer maximum() {
            if (summary == 0L) {
                return null;
            }
            int q = 63 - Long.numberOfLeadingZeros(summary);
            int bit = 63 - Long.numberOfLeadingZeros(words[q]);
            return keyFromWordAndBit(q, bit);
        }

        // Smallest key >= threshold. Threshold may be outside domain.
        Integer ceiling(long threshold) {
            if (summary == 0L || threshold > (long) maxKey) {
                return null;
            }
            if (threshold <= (long) minKey) {
                return minimum();
            }

            int offset = (int) (threshold - (long) minKey);
            int q = offset >>> 6;
            int bit = offset & 63;

            // Keep bits at positions >= bit in this word.
            long candidates = words[q] & (-1L << bit);
            if (candidates != 0L) {
                int answerBit =
                    Long.numberOfTrailingZeros(candidates);
                return keyFromWordAndBit(q, answerBit);
            }

            // Find the next NONEMPTY word via summary.
            // q == 63 has no larger summary-word index.
            long later = q == 63
                ? 0L
                : (summary & (-1L << (q + 1)));
            if (later == 0L) {
                return null;
            }
            int nextQ = Long.numberOfTrailingZeros(later);
            int answerBit =
                Long.numberOfTrailingZeros(words[nextQ]);
            return keyFromWordAndBit(nextQ, answerBit);
        }

        // Largest key <= threshold. Threshold may be outside domain.
        Integer floor(long threshold) {
            if (summary == 0L || threshold < (long) minKey) {
                return null;
            }
            if (threshold >= (long) maxKey) {
                return maximum();
            }

            int offset = (int) (threshold - (long) minKey);
            int q = offset >>> 6;
            int bit = offset & 63;

            // Keep bits at positions <= bit in this word.
            long mask = bit == 63
                ? -1L
                : ((1L << (bit + 1)) - 1L);
            long candidates = words[q] & mask;
            if (candidates != 0L) {
                int answerBit =
                    63 - Long.numberOfLeadingZeros(candidates);
                return keyFromWordAndBit(q, answerBit);
            }

            // Keep summary bits with indices < q.
            long earlier = q == 0
                ? 0L
                : (summary & ((1L << q) - 1L));
            if (earlier == 0L) {
                return null;
            }
            int previousQ =
                63 - Long.numberOfLeadingZeros(earlier);
            int answerBit =
                63 - Long.numberOfLeadingZeros(words[previousQ]);
            return keyFromWordAndBit(previousQ, answerBit);
        }

        // Strict predecessor: greatest stored key < key.
        Integer predecessor(int key) {
            return floor((long) key - 1L);
        }

        // Strict successor: smallest stored key > key.
        Integer successor(int key) {
            return ceiling((long) key + 1L);
        }

        Integer minimumInRange(int from, int to) {
            if (from > to) {
                return null;
            }
            Integer candidate = ceiling((long) from);
            if (candidate == null || candidate > to) {
                return null;
            }
            return candidate;
        }

        List<Integer> valuesInRange(int from, int to) {
            List<Integer> result = new ArrayList<>();
            if (from > to) {
                return result;
            }
            Integer value = ceiling((long) from);
            while (value != null && value <= to) {
                result.add(value);
                value = successor(value);
            }
            return result;
        }

        // Full clear touches every data word.
        void clear() {
            Arrays.fill(words, 0L);
            summary = 0L;
            size = 0;
        }

        // Debug-only validation, O(number of data words).
        void verify() {
            int counted = 0;
            long expectedSummary = 0L;
            for (int q = 0; q < words.length; q++) {
                long word = words[q];
                counted += Long.bitCount(word);
                if (word != 0L) {
                    expectedSummary |= (1L << q);
                }
            }
            if (expectedSummary != summary || counted != size) {
                throw new IllegalStateException(
                    "Broken summary or key count");
            }

            // Extra positions in the last word are not valid keys.
            int usedBitsInLastWord = universe & 63;
            if (usedBitsInLastWord != 0
                    && (words[words.length - 1]
                            >>> usedBitsInLastWord) != 0L) {
                throw new IllegalStateException(
                    "Bit set outside bounded universe");
            }
        }
    }

    public static void main(String[] args) {
        BoundedOrderedSet set = new BoundedOrderedSet(-5, 140);
        int[] keys = {-5, -1, 0, 58, 59, 60, 64, 65, 120, 140};

        for (int key : keys) {
            set.add(key);
        }
        set.verify();

        System.out.println("size=" + set.size()
            + ", U=" + set.universeSize());
        System.out.println("minimum=" + set.minimum());
        System.out.println("maximum=" + set.maximum());
        System.out.println("predecessor(59)="
            + set.predecessor(59));
        System.out.println("successor(58)="
            + set.successor(58));
        System.out.println("floor(61)=" + set.floor(61));
        System.out.println("ceiling(61)=" + set.ceiling(61));
        System.out.println("rangeMin[62,119]="
            + set.minimumInRange(62, 119));
        System.out.println("rangeMin[66,119]="
            + set.minimumInRange(66, 119));
        System.out.println("floor(-6)=" + set.floor(-6));
        System.out.println("ceiling(141)=" + set.ceiling(141));

        System.out.println("remove(59)=" + set.remove(59));
        System.out.println("successor(58) after remove="
            + set.successor(58));
        System.out.println("range[58,65]="
            + set.valuesInRange(58, 65));

        System.out.println("add(59)=" + set.add(59));
        System.out.println("add(59) again=" + set.add(59));
        System.out.println("contains(59)=" + set.contains(59));
        set.verify();

        set.clear();
        System.out.println("after clear, size=" + set.size());
        System.out.println("minimum after clear=" + set.minimum());
        set.verify();
        System.out.println("Invariants: OK");
    }
}
```

Đầu ra dự kiến:

```text
size=10, U=146
minimum=-5
maximum=140
predecessor(59)=58
successor(58)=59
floor(61)=60
ceiling(61)=64
rangeMin[62,119]=64
rangeMin[66,119]=null
floor(-6)=null
ceiling(141)=null
remove(59)=true
successor(58) after remove=60
range[58,65]=[58, 60, 64, 65]
add(59)=true
add(59) again=false
contains(59)=true
after clear, size=0
minimum after clear=null
Invariants: OK
```

### Tại sao ví dụ vượt ranh giới từ?

Miền `[-5,140]` có `U=146`, nên dùng **ba từ dữ liệu**. Những khóa đã chèn ánh xạ:

| Khóa | Offset `x-(-5)` | Từ `q` | Bit trong từ |
| ---: | ---: | ---: | ---: |
| -5 | 0 | 0 | 0 |
| -1 | 4 | 0 | 4 |
| 0 | 5 | 0 | 5 |
| 58 | 63 | 0 | 63 |
| 59 | 64 | 1 | 0 |
| 60 | 65 | 1 | 1 |
| 64 | 69 | 1 | 5 |
| 65 | 70 | 1 | 6 |
| 120 | 125 | 1 | 61 |
| 140 | 145 | 2 | 17 |

`successor(58)=59` buộc hàm đi từ **bit 63 của từ 0** sang **bit 0 của từ 1**. Trường hợp này phát hiện lỗi thường gặp khi viết `1L << 64` hoặc bỏ quên từ kế tiếp.

`predecessor(59)=58` kiểm tra chiều ngược lại, từ **bit 0 của từ 1** về **bit 63 của từ 0**. Những trường hợp biên tương tự là lý do ví dụ không chỉ dùng vài khóa nằm trong cùng một từ.

### Vì sao `ceiling(61)=64`?

Miền có khóa 60, 64, 65, nhưng không có 61, 62, 63. Khóa nhỏ nhất không nhỏ hơn 61 là 64. Với bitmap hai cấp, nếu còn khóa phù hợp trong từ hiện tại, thuật toán **không cần nhảy sang từ khác**.

### Vì sao `rangeMin[66,119]` rỗng?

Khóa 65 nhỏ hơn cận dưới 66, còn khóa tiếp theo là 120 lớn hơn cận trên 119. Vì vậy `ceiling(66)=120` nhưng kiểm tra `120\le119` sai, dẫn tới không có kết quả.

### Những quy tắc mã cần ghi nhớ

1. **`summary` chỉ bật bit cho từ khác 0**; khi xóa phần tử cuối trong một từ phải tắt bit tương ứng.
2. **Dùng `long` cho ngưỡng floor/ceiling** để tạo predecessor/successor strict mà không tràn.
3. **Kiểm tra từ khác 0** trước khi gọi hàm xác định vị trí bit 1.
4. **Xử lý `q=63` trước khi dịch `q+1`** để tránh dịch 64 vị trí.
5. **Không đếm bit ngoài miền** ở từ cuối; `verify()` kiểm tra phần dư.
6. **`clear()` ở cài đặt này là O(U/w)** vì xóa dữ liệu các từ, không chỉ đặt `summary=0` và để bit cũ trong các từ.

### Giới hạn của cài đặt

Đây là một tập khóa nguyên trong RAM, không phải một cấu trúc có cơ chế lưu trữ bền vững, đồng thời hay nén bitmap. Nó hỗ trợ miền **liên tục** và tối đa 4096 khóa; mỗi `long` được dùng như **mẫu 64 bit**, không diễn giải giá trị có dấu của từ lưu bit thành một khóa. Trong hệ thống lớn hơn, cần triển khai các tầng summary tiếp theo hoặc chọn một cấu trúc phù hợp khác.

## 12. Kiểm tra đúng đắn bằng một tập chuẩn

Khi xây cấu trúc tiền nhiệm/kế nhiệm, chỉ kiểm tra `contains` là **chưa đủ**. Một lỗi cập nhật summary có thể khiến các khóa vẫn có trong `words[]` nhưng **không thể được tìm bằng successor/minimum**.

Với Java, ta có thể dùng `TreeSet<Integer>` làm oracle:

| API đang kiểm | API tương ứng của `TreeSet` |
| --- | --- |
| `contains(x)` | `contains(x)` |
| `add(x)` | `add(x)` |
| `remove(x)` | `remove(x)` |
| `predecessor(x)` | `lower(x)` |
| `floor(x)` | `floor(x)` |
| `ceiling(x)` | `ceiling(x)` |
| `successor(x)` | `higher(x)` |
| `minimum()` | `isEmpty()?null:first()` |
| `maximum()` | `isEmpty()?null:last()` |

Trong test, sau mỗi lần thêm/xóa:

```text
apply same add/remove to bitmap and TreeSet
assert both return the same success/failure flag
assert sizes are equal
bitmap.verify()

for selected query thresholds x:
    assert bitmap.predecessor(x) == oracle.lower(x)
    assert bitmap.floor(x)       == oracle.floor(x)
    assert bitmap.ceiling(x)     == oracle.ceiling(x)
    assert bitmap.successor(x)   == oracle.higher(x)

assert bitmap.minimum() == first key or null
assert bitmap.maximum() == last key or null
```

### Kiểm thử bắt buộc ở các vị trí biên

- **Tập rỗng:** mọi truy vấn thứ tự trả không có.
- **Chỉ một khóa:** predecessor/successor strict tại khóa đó đều rỗng; floor/ceiling tại khóa đó đều bằng khóa.
- **Khóa ở bit 0, 63, 64, 127, 128, 4095** (nếu miền đủ lớn).
- **Từ dữ liệu từ 0 sang khác 0:** thêm khóa đầu tiên vào từ và xác minh summary bật.
- **Từ dữ liệu từ khác 0 về 0:** xóa khóa cuối của từ và xác minh summary tắt.
- **Thêm trùng, xóa khóa vắng:** không thay bộ đếm hoặc summary.
- **Ngưỡng nhỏ/lớn hơn miền:** kết quả được chặn đúng.
- **Khóa âm và gần `Integer.MIN_VALUE` hoặc `Integer.MAX_VALUE`:** không tràn khi chuẩn hóa/tạo strict query.
- **`rangeMin(l,r)` có `l=r`, `l>r` hoặc đoạn không chứa khóa.**
- **Min/max sau khi xóa phần tử cực trị.**

### Chuỗi cập nhật giúp phát hiện lỗi

```text
S ban đầu = {}
add(0), add(63), add(64), add(127)
remove(63), remove(0)     -> words[0] trở về 0
minimum() phải là 64
predecessor(64) phải rỗng
add(1)                    -> words[0] từ 0 thành khác 0
minimum() phải là 1
successor(1) phải là 64
```

Bộ test nên sinh các dãy thao tác ngẫu nhiên có **seed cố định**, áp dụng cùng thao tác lên bitmap và `TreeSet`, rồi kiểm tra bất biến sau **mỗi bước**. Với miền nhỏ `U\le4096`, việc quét toàn miền trong test có thể chấp nhận được, dù không nên đưa quét O(U) vào thao tác runtime rồi gọi kết quả là O(1).

## 13. Phân tích độ phức tạp và lựa chọn thực tế

### Bitmap hai cấp trong bài

Với `U\le w^2`, `w=64` và `U\le4096`:

| Thao tác | Chi phí theo mô hình từ máy |
| --- | --- |
| `contains` | O(1) worst-case |
| `add/remove` | O(1) worst-case, với mảng được cấp phát |
| `minimum/maximum` | O(1) worst-case |
| `floor/ceiling` | O(1) worst-case |
| `predecessor/successor` | O(1) worst-case |
| `minimumInRange` | O(1) worst-case |
| Liệt kê `r` khóa của một đoạn | O(r+1) trong cấu trúc giới hạn này |
| `clear()` thật | O(⌈U/w⌉) vì xóa từng từ |
| `verify()` | O(⌈U/w⌉), chỉ dùng khi test/debug |
| Khởi tạo | O(⌈U/w⌉) từ dữ liệu |
| Bộ nhớ | `8\lceil U/64\rceil+8` byte payload cho `words` và summary, chưa kể metadata |

**Bảo đảm O(1) ở đây có điều kiện rất cụ thể:** phần tóm tắt vừa **một từ 64 bit**. Không áp dụng kết luận đó cho bitset bất kỳ lớn hơn một triệu hay một tỷ khóa mà không bổ sung cấu trúc hỗ trợ.

### Cân bằng thời gian và bộ nhớ

Với một ứng dụng:

- **Miền rất nhỏ:** trực tiếp dùng một từ bit hoặc bitmap hai cấp có thể đơn giản và nhanh.
- **Miền vừa, tương đối dày:** bitset chia từ, có thể thêm các tầng summary nếu predecessor/successor quan trọng.
- **Miền cực lớn, `n` nhỏ:** ordered map/cây cân bằng thường tiết kiệm bộ nhớ hơn cấp phát dày đặc.
- **Dữ liệu gần như tĩnh và đã sắp:** mảng khóa + binary search có thể hiệu quả về cache.
- **Chỉ cần membership:** bảng băm hoặc bitset có thể đủ; không nhất thiết xây cấu trúc successor.
- **Dữ liệu phân trang:** B+ tree và iterator lá có thể phù hợp hơn bitmap dày đặc theo toàn miền.

Ví dụ thực tế: một bộ lập lịch chỉ có 1.024 khe thời gian mỗi ngày có thể dùng **bitset** để đánh dấu khe đã có sự kiện; tìm khe kế tiếp bằng bitmap là khả thi. Nhưng nếu mã sự kiện là ID 64 bit phân bố rải rác trên nhiều năm, không nên cấp phát bitmap cho toàn bộ miền ID.

## 14. Các sai lầm thường gặp

1. **Nhầm `predecessor` với `floor`.** Khi `x` có trong tập, predecessor strict phải nhỏ hơn `x`.
2. **Nhầm `successor` với `ceiling`.** Khi `x` có trong tập, successor strict phải lớn hơn `x`.
3. **Yêu cầu khóa truy vấn phải có sẵn.** Truy vấn thứ tự hoàn toàn có thể nhận khóa không nằm trong `S`.
4. **Dùng `-1` làm dấu không tìm thấy khi `-1` là khóa hợp lệ.** Cần trạng thái rỗng riêng.
5. **Cho rằng `contains(x)` O(1) khiến `successor(x)` cũng O(1).** Bảng cờ trực tiếp có thể phải quét O(U).
6. **Cho rằng bitset thường tìm successor O(1) worst-case.** Có thể cần quét O(U/w) từ rỗng nếu không có summary.
7. **Không cập nhật summary khi thêm phần tử đầu tiên vào một từ rỗng.** Các phép tìm theo summary sẽ bỏ qua từ mới.
8. **Không tắt summary khi xóa phần tử cuối của một từ.** Có thể lấy vị trí bit không hợp lệ từ một từ bằng 0.
9. **Gọi `numberOfTrailingZeros(0)` rồi xem kết quả 64 là bit hợp lệ.** Phải kiểm tra từ khác 0.
10. **Dùng `1L << 64`.** Java dịch theo số bit thấp; kết quả không phải bit 64.
11. **Quên xử lý `q=63` trước khi lọc các từ đứng sau.** Phép dịch `q+1=64` không tạo mặt nạ rỗng.
12. **Giải thích giá trị `long` âm như khóa âm.** Bit 63 bật làm từ có dấu âm, nhưng thuật toán đang xử lý mẫu bit.
13. **Dùng `x+1` hoặc `x-1` trong `int` ở cận cực trị.** Phải mở rộng sang `long` trước phép toán.
14. **Tính `U=b-a+1` trong `int` với toàn miền `int`.** Có thể tràn; phải kiểm tra phạm vi.
15. **Bỏ qua chuyển khóa âm thành offset.** `words[-1]` không phải chỉ số hợp lệ.
16. **Cho rằng `summary=0` là đủ để clear toàn bộ cấu trúc có thể thêm lại.** Các bit cũ trong `words[]` phải được dọn hoặc phải dùng cơ chế thế hệ riêng có bất biến phù hợp.
17. **Coi O(1) của bitmap hai cấp áp dụng cho mọi `U`.** Cần điều kiện `U\le w^2` để summary vừa một từ.
18. **Nhầm range-min của tập khóa với RMQ trên mảng.** Một bài tìm khóa đầu tiên trong đoạn, bài kia tìm giá trị nhỏ nhất trên đoạn chỉ số.
19. **Bỏ qua sự khác biệt giữa API trả `null` và API ném ngoại lệ khi không có phần tử.** Phải xác định hợp đồng.
20. **Chỉ kiểm tra tập khóa mà không kiểm tra min/pred/succ.** Summary sai có thể không ảnh hưởng membership nhưng làm truy vấn thứ tự sai.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Với `S=\{2,5,70,120,254\}`, `predecessor(70)` trả gì?

**Đáp án:** 5, vì tiền nhiệm strict phải **nhỏ hơn** 70.

**Câu 2.** Với tập đó, `floor(70)` và `ceiling(70)` trả gì?

**Đáp án:** Cả hai trả 70, vì floor/ceiling cho phép dấu bằng.

**Câu 3.** `successor(70)` bằng bao nhiêu?

**Đáp án:** 120.

**Câu 4.** `predecessor(0)` và `ceiling(0)` lần lượt là gì?

**Đáp án:** Không có tiền nhiệm; ceiling bằng 2.

**Câu 5.** `minimum(S)` và `maximum(S)` là gì?

**Đáp án:** Minimum bằng 2, maximum bằng 254.

**Câu 6.** `rangeMin(71,119)` có kết quả không?

**Đáp án:** Không, vì khóa lớn hơn 71 gần nhất là 120, vượt cận 119.

**Câu 7.** Làm thế nào giảm `rangeMin(l,r)` về một truy vấn `ceiling`?

**Đáp án:** Tìm `c=ceiling(l)`; trả `c` nếu tồn tại và `c\le r`, ngược lại trả rỗng.

**Câu 8.** Vì sao một mảng cờ trực tiếp có thể tìm `contains` O(1) nhưng predecessor O(U)?

**Đáp án:** Membership đọc một vị trí cố định, còn predecessor có thể cần quét qua nhiều vị trí không có khóa.

**Câu 9.** Với mảng khóa tăng đã sắp, `predecessor(x)` dùng tìm nhị phân như thế nào?

**Đáp án:** Lấy phần tử ngay trước `lower_bound(x)`, nếu vị trí đó hợp lệ.

**Câu 10.** Với từ 64 bit, offset 130 thuộc từ nào và bit nào?

**Đáp án:** Từ 2, bit 2.

**Câu 11.** Dùng hàm Java nào lấy vị trí bit bật thấp nhất của một từ khác 0?

**Đáp án:** `Long.numberOfTrailingZeros(word)`.

**Câu 12.** Dùng hàm nào lấy vị trí bit bật cao nhất?

**Đáp án:** `63-Long.numberOfLeadingZeros(word)`, khi `word!=0`.

**Câu 13.** Từ có tất cả bit bằng 0 được đánh dấu thế nào trong summary?

**Đáp án:** Bit summary tương ứng phải bằng 0.

**Câu 14.** Nếu xóa khóa cuối cùng của `words[5]`, cần cập nhật gì?

**Đáp án:** Tắt bit 5 của summary và giảm `size` đúng một.

**Câu 15.** Vì sao bitmap hai cấp trên từ 64 bit chỉ bao phủ trực tiếp tối đa 4096 khóa?

**Đáp án:** Một từ summary có 64 bit, mỗi bit đại diện một từ dữ liệu 64 bit; tổng `64\times64=4096` khóa.

**Câu 16.** `successor(63)` khi tập `\{5,63,64,70\}` là gì?

**Đáp án:** 64, vì phải bỏ khóa bằng 63 và chuyển sang từ tiếp theo.

**Câu 17.** Vì sao việc tạo `predecessor(x)` bằng `floor(x-1)` cần lưu ý kiểu số?

**Đáp án:** Nếu `x=Integer.MIN_VALUE`, trừ 1 trong `int` sẽ tràn; dùng `(long)x-1L`.

**Câu 18.** Với miền `[-5,140]`, khóa `59` có offset và vị trí từ/bit nào?

**Đáp án:** Offset 64, tức từ 1 và bit 0.

**Câu 19.** Bảng so sánh cho biết cấu trúc nào phù hợp khi `U` rất lớn nhưng `n` nhỏ và cần predecessor?

**Đáp án:** Cây tìm kiếm cân bằng hoặc ordered map thường phù hợp vì O(n) bộ nhớ và O(log n) cho predecessor/successor.

**Câu 20.** Tại sao cần kiểm thử thứ tự sau chuỗi thêm/xóa chứ không chỉ kiểm tra `contains`?

**Đáp án:** Vì membership chỉ xem bit dữ liệu, còn min/pred/succ còn dựa vào summary; một bit summary thiếu hoặc thừa có thể làm truy vấn thứ tự sai dù membership vẫn đúng.

**Điểm ghi nhớ:** **Predecessor/successor** tìm phần tử **nhỏ hơn/lớn hơn nghiêm ngặt**; **floor/ceiling** cho phép bằng ngưỡng. **Minimum** của một tập và **phần tử nhỏ nhất trong đoạn số** có thể lấy bằng định tuyến tới khóa bật đầu tiên phù hợp. Mảng trực tiếp cho membership O(1) nhưng có thể phải quét O(U) để tìm lân cận; bitset quét theo **từ máy**, còn **bitmap tóm tắt** cho phép bỏ qua cả từ rỗng. Với `U\le4096` và từ 64 bit, cấu trúc bitmap hai cấp của bài hỗ trợ min/max/floor/ceiling/pred/succ O(1) sau cấp phát, đổi lại bộ nhớ theo miền. Khi `U` lớn và tập thưa, hãy cân nhắc **cây cân bằng hoặc cấu trúc tiền nhiệm chuyên dụng** thay vì mở rộng bitmap dày đặc không giới hạn.
