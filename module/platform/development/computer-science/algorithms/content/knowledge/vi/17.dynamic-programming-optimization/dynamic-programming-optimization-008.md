# Convex hull trick cho các phép chuyển tuyến tính

**Convex Hull Trick (CHT)** là một kỹ thuật tối ưu quy hoạch động khi một chuyển trạng thái có thể được viết dưới dạng **truy vấn giá trị nhỏ nhất hoặc lớn nhất của nhiều hàm tuyến tính**. Mỗi phương án trước đó `j` tạo một đường thẳng `y=m_jx+b_j`; tại trạng thái hiện tại `i`, ta cần chọn đường có giá trị nhỏ nhất/lớn nhất ở tọa độ `x_i`. Thay vì duyệt hết mọi `j<i` với thời gian `O(n²)`, ta duy trì một cấu trúc các đường thẳng để trả lời nhanh.

CHT không phải “mẹo áp dụng cho mọi công thức có phép nhân”. Ta phải **biến đổi đại số đúng**, chứng minh đường nào được đưa vào trước khi truy vấn, kiểm tra thứ tự **hệ số góc (slope)** và **tọa độ hỏi (query x)**, xử lý các đường có cùng slope và tránh lỗi **tràn số khi so sánh giao điểm**.

Trong nhóm **Tối ưu quy hoạch động**, đây là một ví dụ quan trọng của việc nhận ra hình học ẩn sau công thức DP. Bài học trình bày ba mức triển khai:

1. **DP `O(n²)`** làm lời giải gốc để đối chiếu;
2. **Monotone Convex Hull Trick** dùng deque, `O(n)` thao tác khi slope và tọa độ truy vấn có thứ tự thích hợp;
3. **Li Chao tree trên tọa độ rời rạc**, `O(log K)` cho một lần thêm đường/truy vấn khi biết trước `K` tọa độ truy vấn, dùng được khi slope và query **không** theo thứ tự.

Cuối bài là mã Java 17+ hoàn chỉnh, ví dụ stdout và kiểm thử bằng thuật toán chậm độc lập.

## 1. Nhận diện dạng bài toán: min/max các đường thẳng

Giả sử:

```text
dp[i] = base(i) + min_{0 <= j < i} {
    m(j) * x(i) + b(j)
}
```

Trong đó:

- `i`: trạng thái đang tính.
- `j<i`: các trạng thái trước đã có đáp án.
- `x(i)`: giá trị tọa độ dùng để **hỏi** cấu trúc các đường.
- `m(j)`: hệ số góc của đường được sinh từ trạng thái `j`.
- `b(j)`: hệ số tự do, có thể bao gồm `dp[j]`.
- `base(i)`: phần không phụ thuộc vào `j`, cộng sau khi có giá trị min.

Tại thời điểm tính `dp[i]`, các đường hợp lệ là những đường ứng với **chính xác `j<i`**. Ký hiệu:

```text
line_j(x) = m(j) * x + b(j)

best(i) = min_{0 <= j < i} line_j(x(i))

dp[i] = base(i) + best(i)
```

**CHT tối ưu phần `best(i)`, không tự thay đổi định nghĩa DP.** Khi dùng Li Chao/CHT, ta phải đảm bảo không truy vấn đường được sinh từ `dp[i]` hoặc các trạng thái tương lai. Nếu thêm đường `i` **trước** khi tính `dp[i]`, vòng phụ thuộc bị sai và có thể tạo nghiệm không hợp lệ.

### Từ các ứng viên thành “bao dưới” (lower envelope)

Mỗi `j` cho một đường `y=m_jx+b_j`. Hàm cần tìm:

```text
F(x) = min_j (m_j*x + b_j)
```

là **bao dưới** của các đường. Một số đường không bao giờ đạt min ở bất cứ `x` nào trong miền cần xét; chúng có thể bị loại nếu ta có chứng minh đúng. Với truy vấn **max**, dùng bao trên hoặc biến đổi dấu:

```text
max_j(m_j*x + b_j)
= - min_j((-m_j)*x + (-b_j))
```

Dấu âm và hướng thứ tự slope phải được xử lý nhất quán. Bài này triển khai trực tiếp **min**; không lấy nguyên công thức so sánh của min để áp sang max mà không sửa dấu.

### Khi nào chưa thể dùng CHT?

Các công thức có `j` nằm trong một biểu thức phi tuyến **không tách được thành `m_jx_i+b_j`** chưa dùng trực tiếp được CHT. Ví dụ một phép chuyển phụ thuộc vào cả `i,j` theo cách không thể tách, hoặc chi phí có ràng buộc cửa sổ `j∈[L_i,R_i]` thay đổi theo `i`, cần thêm cấu trúc quản lý vòng đời ứng viên hoặc một tối ưu DP khác.

Một điều kiện khác là phải có **thứ tự tính DP hợp lệ**: khi tạo đường từ trạng thái `j`, `dp[j]` phải đã được tính. CHT không sửa được quan hệ phụ thuộc sai hoặc trạng thái thiếu biến.

## 2. Ví dụ xuyên suốt: chi phí bình phương tổng trên từng đoạn

Cho mảng số nguyên `a[0..n−1]`, đặt tổng tiền tố:

```text
S[0] = 0
S[i] = a[0] + a[1] + ... + a[i-1]  (1 <= i <= n)
```

Muốn chia `n` phần tử thành các đoạn liên tiếp không rỗng. Mỗi đoạn `[j,i)` có chi phí:

```text
cost(j,i) = (S[i] - S[j])^2 + C
```

Trong đó `C` là phí cố định của **mỗi đoạn** (có thể dương, bằng 0 hoặc âm; tổng số đoạn vẫn hữu hạn). Đặt `dp[i]` là **tổng chi phí nhỏ nhất để chia `i` phần tử đầu**:

```text
dp[0] = 0

dp[i] = min_{0 <= j < i} {
    dp[j] + (S[i] - S[j])^2 + C
}
```

Bước quy hoạch động đúng vì trong một phương án chia tối ưu của tiền tố `[0,i)`, đoạn cuối là `[j,i)` với một `j<i`. Phần trước `[0,j)` phải có chi phí tối ưu `dp[j]`; nếu không, thay bằng cách chia tốt hơn sẽ cải thiện phương án toàn cục.

### Mở bình phương để xuất hiện đường thẳng

```text
dp[j] + (S[i] - S[j])^2 + C

= dp[j] + S[i]^2 - 2*S[i]*S[j] + S[j]^2 + C

= S[i]^2 + C
  + [(-2*S[j]) * S[i] + (dp[j] + S[j]^2)]
```

Đặt:

```text
x_i = S[i]
m_j = -2*S[j]
b_j = dp[j] + S[j]^2

line_j(x) = m_j*x + b_j
```

Suy ra chính xác:

```text
dp[i] = S[i]^2 + C + min_{0 <= j < i} line_j(S[i])
```

Cách chạy:

```text
1. dp[0] = 0; đưa line_0(x) = 0*x + 0 vào cấu trúc.
2. Với i = 1..n:
     x = S[i]
     best = queryMin(x)              // chỉ có các line_j với j<i
     dp[i] = S[i]^2 + C + best
     addLine(-2*S[i], dp[i] + S[i]^2)
3. Trả dp[n].
```

**Quan hệ giữa hướng tăng/giảm:**

- Nếu **mọi `a[i]≥0`**, thì `S[i]` **không giảm**, nên tọa độ truy vấn `x_i=S[i]` **không giảm**.
- Khi `S[j]` không giảm, slope `m_j=−2S[j]` **không tăng** (tức giảm hoặc bằng nhau).
- Hai điều kiện này phù hợp với CHT dùng **deque** cho truy vấn min trong bài này.
- Nếu có số âm, `S[i]` có thể tăng/giảm thất thường, và slope thêm vào cũng không có thứ tự. Lúc đó **không** được dùng phiên bản deque monotone mà bỏ qua giả định; dùng Li Chao, hoặc cấu trúc khác phù hợp.

### Ví dụ không âm

```text
a = [2, 1, 3, 0, 2]
C = 4
S = [0, 2, 3, 6, 6, 8]
```

Bảng DP chậm:

| `i` | `S[i]` | Các giá trị ứng viên `dp[j]+(S[i]-S[j])²+C` | `dp[i]` |
| ---: | ---: | --- | ---: |
| 0 | 0 | Base | 0 |
| 1 | 2 | `j=0: 0+4+4=8` | **8** |
| 2 | 3 | `j=0: 13; j=1: 8+1+4=13` | **13** |
| 3 | 6 | `j=0: 40; j=1: 28; j=2: 26` | **26** |
| 4 | 6 | `j=0:40; j=1:28; j=2:26; j=3:30` | **26** |
| 5 | 8 | `j=0:68; j=1:48; j=2:42; j=3:34; j=4:34` | **34** |

Kết quả:

```text
dp = [0, 8, 13, 26, 26, 34]
```

Đoạn `a[3]=0` tạo `S[3]=S[4]`, nghĩa là **hai đường có cùng slope**. Một cài đặt đúng phải xử lý được trường hợp này, không chia cho hiệu slope bằng 0.

### Ví dụ có số âm

```text
a = [2, -5, 1, 4]
C = 3
S = [0, 2, -3, -2, 2]

dp[0] = 0
dp[1] = 7
dp[2] = 12
dp[3] = 7
dp[4] = 7
```

Ở đây `S` không tăng đơn điệu, nên slope mới `−2S[j]` cũng không giảm đơn điệu. Phiên bản **Li Chao** ở mục 7 tính được đúng:

```text
dp = [0, 7, 12, 7, 7]
```

## 3. Giải pháp gốc O(n²): oracle để kiểm tra tối ưu

Lời giải trực tiếp theo công thức:

```java
// Hàm minh họa: prefix[] đã là tổng tiền tố kiểu long.
static long[] quadraticDP(long[] prefix, long penalty) {
    int n = prefix.length - 1;
    long[] dp = new long[n + 1];
    for (int i = 1; i <= n; i++) {
        long best = Long.MAX_VALUE;
        for (int j = 0; j < i; j++) {
            long delta = Math.subtractExact(prefix[i], prefix[j]);
            long square = Math.multiplyExact(delta, delta);
            long candidate = Math.addExact(
                Math.addExact(dp[j], square), penalty);
            best = Math.min(best, candidate);
        }
        dp[i] = best;
    }
    return dp;
}
```

Đoạn trên **không phải chương trình độc lập**, vì thiếu import/class. Với `n` phần tử, tổng số cặp `(j,i)` là:

```text
1 + 2 + ... + n = n(n+1)/2 = Θ(n²)
```

Không gian bảng `dp[]` là `O(n)`; thêm `O(n)` cho prefix. Khi `n` rất nhỏ, giải pháp `O(n²)` có thể là **lựa chọn tốt nhất về độ đơn giản**.

Bản chậm có vai trò quan trọng trong QA: nó biểu diễn trực tiếp đặc tả toán học, **không** sử dụng hình học hull hay Li Chao. Đem các kết quả CHT so sánh với bản này trên các bộ input nhỏ giúp phát hiện lỗi về dấu, thứ tự thêm đường và xử lý trùng slope.

**Với số nguyên rất lớn:** `Math.multiplyExact`, `Math.addExact` và `Math.subtractExact` sẽ báo `ArithmeticException` nếu phép tính trung gian vượt miền `long`. Ví dụ Java chính dùng chúng để **không trả kết quả sai âm thầm do overflow**. Đây là hợp đồng có giới hạn giá trị; nếu đề cho dữ liệu khiến bình phương/tổng vượt `long`, cần dùng `BigInteger` hoặc một kiểu số/thủ tục bảo đảm an toàn khác cho toàn bộ phép tính.

## 4. CHT dùng deque khi thêm slope giảm và hỏi x tăng

Với bài **min**, giả sử ta thêm lần lượt các đường có:

```text
m_1 >= m_2 >= m_3 >= ...
```

và các truy vấn có:

```text
x_1 <= x_2 <= x_3 <= ...
```

Ta duy trì một deque các đường còn có thể tối ưu cho truy vấn hiện tại/tương lai. Những đường bị loại khỏi **đầu** hoặc **cuối** deque không bao giờ cần lại, theo các điều kiện thứ tự đã chứng minh.

**Không đảo quy ước:** Đây là cách riêng cho **min, slope không tăng, x không giảm**. Có phiên bản đối xứng cho max/hướng slope khác, nhưng điều kiện pop và so sánh cần chỉnh đúng. Đọc code rồi dùng cho bài `max` khi chưa chuyển dấu có thể tạo sai số nghiêm trọng.

### 4.1. Query min từ đầu deque

Giả sử hai đường đầu `L₁` và `L₂` có slope `m₁>m₂`. Khi `x` tăng, đường slope nhỏ `L₂` cuối cùng sẽ trở nên không kém `L₁` ở mọi giá trị `x` đủ lớn. Nếu tại truy vấn hiện tại:

```text
L₂(x) <= L₁(x)
```

thì từ đây trở đi (với `x'≥x`), `L₂(x')≤L₁(x')`. Vì vậy ta có thể **pop đầu `L₁`** mà không ảnh hưởng tới bất kỳ truy vấn tương lai nào.

Pseudocode:

```text
query(x):
    require x >= x_query_trước
    while deque có ít nhất 2 đường
          và value(deque[1],x) <= value(deque[0],x):
        pop_front()
    return value(deque.front,x)
```

Với hai đường cùng slope, cần xử lý trước trong `addLine`; khi đó deque giữ slope **giảm nghiêm ngặt**, và lập luận về ưu thế trong tương lai rõ ràng hơn.

**Khi giá trị bằng nhau:** Dùng `<=` để loại đường đầu. Tại `x` hiện tại hai đường cho cùng min; từ các truy vấn phía sau, đường slope nhỏ hơn sẽ tốt hơn hoặc bằng, nên pop vẫn đúng **nếu chỉ cần giá trị min**. Nếu đề còn yêu cầu chọn đúng một chỉ số `j` theo luật phá hòa đặc biệt, phải định nghĩa và xử lý tie-break riêng, không mặc định chỉ số trả về giống bản `O(n²)`.

### 4.2. Thêm đường và loại đường ở cuối

Giả sử ba đường liên tiếp `A,B,C` có slope giảm nghiêm ngặt:

```text
m_A > m_B > m_C
```

Khi xét bao dưới, đường `B` chỉ có thể là lựa chọn tốt nhất trên một khoảng `x` nằm giữa thời điểm `B` vượt `A` và thời điểm `C` vượt `B`.

Hoành độ giao điểm:

```text
x_AB = (b_B - b_A) / (m_A - m_B)
x_BC = (b_C - b_B) / (m_B - m_C)
```

Hai mẫu số **dương** theo thứ tự slope đã giả định. Nếu:

```text
x_AB >= x_BC
```

thì `B` không có khoảng nào **tốt hơn nghiêm ngặt cả A lẫn C**, nên có thể loại `B` khỏi bao dưới. Trong trường hợp giao điểm bằng nhau, tại điểm bằng nhau ta vẫn giữ ít nhất một đường đạt min; loại `B` không ảnh hưởng giá trị.

Không cần chia số thực. Nhân chéo với hai mẫu số dương:

```text
(b_B - b_A) * (m_B - m_C)
    >=
(b_C - b_B) * (m_A - m_B)
```

Đó là **điều kiện redundancy** dùng để pop đường cuối thứ hai trong deque khi thêm `C`.

### 4.3. Tránh số thực và tràn phép nhân chéo

Sai lầm thường gặp là tính `x_AB` và `x_BC` bằng `double` rồi so sánh. Với hệ số nguyên rất lớn, sai số làm tròn có thể đảo kết quả khi giao điểm gần nhau. Dùng **nhân chéo trên số nguyên chính xác** sẽ an toàn về toán học.

Tuy nhiên, nhân chéo hai số kiểu `long` có thể **tràn 64 bit**. Trong chương trình Java, bốn hiệu được chuyển sang `BigInteger` trước khi nhân, rồi so sánh bằng `compareTo`. Đây là cách minh bạch để ưu tiên tính đúng; nó có chi phí tạo object và phép tính nhiều bit so với cách tối ưu cực hạn dùng số 128 bit hoặc điều kiện ràng buộc nhỏ.

Cách tiếp cận:

```java
// Minh họa: a,b,c đều là Line; slope a>b>c.
BigInteger left =
    BigInteger.valueOf(b.intercept())
        .subtract(BigInteger.valueOf(a.intercept()))
        .multiply(
            BigInteger.valueOf(b.slope())
                .subtract(BigInteger.valueOf(c.slope())));

BigInteger right =
    BigInteger.valueOf(c.intercept())
        .subtract(BigInteger.valueOf(b.intercept()))
        .multiply(
            BigInteger.valueOf(a.slope())
                .subtract(BigInteger.valueOf(b.slope())));

boolean redundant = left.compareTo(right) >= 0;
```

Đoạn trên minh họa toán tử nhân chéo, không phải class độc lập. Code hoàn chỉnh ở mục 9 dùng `Line` record và phương thức truy cập rút gọn.

### 4.4. Đường cùng slope: giữ intercept tốt nhất

Hai đường `L₁(x)=mx+b₁` và `L₂(x)=mx+b₂` có cùng slope. Trong bài **min**:

- Nếu `b₁<b₂`: `L₁` tốt hơn tại **mọi `x`**; bỏ `L₂`.
- Nếu `b₂<b₁`: bỏ `L₁`.
- Nếu `b₁=b₂`: hai đường giống nhau; chỉ cần giữ một.

**Không được tính giao điểm bằng phép chia cho `m₁−m₂=0`.** Phiên bản deque xử lý bằng nhau ngay khi thêm đường và chỉ dùng công thức nhân chéo cho các slope **giảm nghiêm ngặt**.

Trong ví dụ có `a[i]=0`, tổng tiền tố lặp và sinh đường cùng slope; xử lý này là yêu cầu thiết yếu chứ không chỉ ca “hiếm”.

### 4.5. Tại sao tổng thời gian là O(n) amortized?

Mỗi đường được **push đúng một lần**. Sau đó nó có thể:

- Bị pop ở **cuối deque** vì trở nên dư thừa;
- Hoặc bị pop ở **đầu deque** vì đường kế tốt hơn với mọi truy vấn x về sau;
- Hoặc vẫn nằm trong deque.

Một đường không bao giờ quay lại sau khi pop. Vì thế tổng số lần push/pop trên **toàn bộ n đường** là `O(n)`, dù một lần add/query riêng lẻ có thể pop nhiều đường. Đây là phân tích **amortized**, không phải đảm bảo mọi lời gọi riêng lẻ đều `O(1)` worst-case.

Nếu coi mỗi phép so sánh hệ số nguyên cố định là `O(1)`, tổng **`O(n)` thao tác cấu trúc** và **`O(n)` bộ nhớ xấu nhất** cho deque. Trong chương trình dùng `BigInteger` để so sánh giao điểm, còn có chi phí bit và cấp phát object; với hệ số đầu vào kiểu `long`, số bit của biểu thức nhân chéo bị chặn bởi một hằng số tương đối nhỏ, nhưng overhead JVM vẫn đáng đo khi cần hiệu năng cao.

## 5. Bằng ví dụ hình học: một đường có thể bị loại

Xét ba đường:

```text
A(x) = 5*x + 0
B(x) = 3*x + 1
C(x) = 1*x + 0
```

Slope giảm: `5>3>1`. Giao điểm:

```text
x_AB = (1-0)/(5-3) = 0.5
x_BC = (0-1)/(3-1) = -0.5
```

Vì `0.5≥−0.5`, đường `B` **không bao giờ tốt hơn cả A lẫn C** trên bao dưới, có thể bỏ.

Truy vấn tại các điểm không giảm:

| `x` | `A(x)` | `B(x)` | `C(x)` | Min |
| ---: | ---: | ---: | ---: | ---: |
| `−2` | −10 | −5 | −2 | **−10** |
| `0` | 0 | 1 | 0 | **0** |
| `2` | 10 | 7 | 2 | **2** |

Mỗi lần query, nếu đường ở đầu đã bị đường kế tốt hơn hoặc bằng, ta có thể bỏ nó vĩnh viễn do `x` tiếp theo không giảm. Code Java sẽ in:

```text
Hull lines after redundant removal: 2
Hull queries [-2,0,2]: [-10, 0, 2]
```

Một ví dụ khác:

```text
L1(x)=2*x+5
L2(x)=2*x+3
```

Hai đường cùng slope, `L₂` tốt hơn mọi nơi. Ta giữ `L₂`. Đây cũng là cách tránh phép chia cho 0 trong phép tìm giao điểm.

## 6. Ranh giới áp dụng deque CHT: hai kiểu đơn điệu

Điều kiện đủ của **phiên bản deque trong bài** là:

1. **Thứ tự thêm slope:** mỗi đường mới có slope **không lớn hơn slope trước**. Với hai đường cùng slope, giữ intercept nhỏ hơn.
2. **Thứ tự query:** mỗi `x` mới **không nhỏ hơn `x` của truy vấn trước**.
3. **Yêu cầu là giá trị min**, không có luật tie-break chỉ số phức tạp.
4. Đường được tạo từ các trạng thái đã tính, không cần xóa một đường vì hết hạn theo ràng buộc độc lập.

Nếu **thiếu điều kiện 1**, thêm đường mới có slope tùy ý làm deque không còn thứ tự bao dưới phù hợp. Nếu **thiếu điều kiện 2**, một đường bị pop ở đầu do không tốt tại x hiện tại có thể trở lại tối ưu cho một x **nhỏ hơn** trong tương lai. Đã xóa thì không thể khôi phục.

**Trường hợp chỉ slope đơn điệu nhưng query không đơn điệu:** Có thể giữ các đường trên hull theo thứ tự giao điểm và tìm nhị phân đường tối ưu cho `x`, thay vì pop đầu vĩnh viễn. Thời gian query thường `O(log n)` khi biểu diễn đúng các giao điểm; cần thiết kế thuật toán khác với deque tiêu thụ front trong ví dụ.

**Trường hợp cả hai không có thứ tự:** Có thể dùng **Li Chao tree** khi miền/tọa độ truy vấn được xác định, hoặc cấu trúc hull động tổng quát trong hoàn cảnh thích hợp.

**Bài toán max:** Có thể chuyển mọi đường `(m,b)` thành `(−m,−b)` rồi hỏi min và đổi dấu kết quả, nhưng thứ tự slope sau đổi dấu cũng đảo. Phải xây lại cấu trúc theo hướng mới hoặc chọn phiên bản phù hợp.

### Một phản ví dụ về việc pop đầu rồi hỏi x giảm

Với `A(x)=5x` và `C(x)=x`:

- Ở `x=2`, `C(2)=2` tốt hơn `A(2)=10`. Monotone deque có thể bỏ `A`.
- Nếu lần sau hỏi `x=−2`, `A(−2)=−10` lại tốt hơn `C(−2)=−2`.
- Vì `A` đã bị bỏ, kết quả có thể sai.

Vì vậy điều kiện query x không giảm là **tiền điều kiện bắt buộc**, không phải một chi tiết tối ưu.

## 7. Li Chao tree khi slope và x không đơn điệu

**Li Chao tree** lưu một tập các đường thẳng trên một miền tọa độ `x`. Ý tưởng là ở mỗi nút quản lý một đoạn tọa độ, giữ một đường có giá trị tốt ở **tọa độ giữa**; khi thêm một đường mới, so sánh ở một vài điểm để quyết định đường nào giữ ở nút và đường nào có thể còn tốt hơn ở **một nửa đoạn**.

Đặc tính cho bài **min**:

- Có thể thêm đường với **slope bất kỳ**.
- Có thể hỏi các `x` theo **thứ tự bất kỳ**.
- Với miền tọa độ rời rạc gồm `K` điểm đã biết trước, thêm một đường hoặc hỏi một điểm tốn **`O(log K)`** trên cây phân đoạn phù hợp.
- Bộ nhớ cây **`O(K)`** nút/ô trên miền rời rạc, không kể danh sách đường ngoài cấu trúc.

### 7.1. Dùng n tọa độ query biết trước trong DP

Ở bài chia đoạn, mọi tọa độ query là:

```text
x_i = S[i], i=1..n
```

Mặc dù `dp[i]` chưa biết trước, **S[i]` vẫn tính được từ mảng đầu vào**. Vì vậy ta có thể:

1. Lấy danh sách `S[1],...,S[n]`.
2. **Sort và khử trùng** để có `xs[0..K−1]` tăng nghiêm ngặt.
3. Xây Li Chao tree trên các vị trí chỉ số `0..K−1`, mỗi vị trí có tọa độ thật `xs[index]`.
4. Với mỗi `i`, query ở `S[i]` (bắt buộc thuộc `xs`), tính `dp[i]`, rồi thêm đường ứng với `j=i`.

Điều này gọi là **Li Chao trên tọa độ nén/rời rạc (discrete-coordinate Li Chao)**. Nó không cần giả định thứ tự truy vấn hoặc slope. Nhưng **bắt buộc biết trước các tọa độ query hợp lệ**. Nếu ứng dụng cần hỏi một `x` bất kỳ chưa có trong danh sách, phải dùng biến thể Li Chao trên miền số nguyên thực sự (hoặc cấu trúc khác), không truy vấn tùy tiện vào cây chỉ chứa các điểm rời rạc.

### 7.2. Thêm một đường: điểm trái và điểm giữa

Một nút quản lý các tọa độ `xs[l..r]` có đường hiện tại `old`. Khi thêm `incoming`:

- So sánh `incoming` với `old` tại tọa độ trái `xs[l]` và giữa `xs[mid]`.
- Đường tốt hơn tại **điểm giữa** được giữ ở nút.
- Đường còn lại chỉ có thể cải thiện giá trị min trên **một** nhánh con vì hiệu của hai đường thẳng cũng là một hàm tuyến tính, chỉ có tối đa một lần đổi dấu.
- Chọn nhánh trái nếu quan hệ tốt/hơn ở trái và giữa khác nhau, ngược lại chọn nhánh phải.
- Tiếp tục cho tới nút lá hoặc gặp nút chưa chứa đường.

Trong code dùng so sánh **`<` nghiêm ngặt**, khi bằng nhau một đường được giữ theo quy tắc triển khai; vì chỉ cần giá trị min, thứ tự chọn giữa hai đường hòa không ảnh hưởng đáp án.

Cách phân tích `O(log K)`: một lần thêm đường chỉ đi xuống **một nhánh** ở mỗi mức; độ sâu cây cân bằng theo số tọa độ `K`.

### 7.3. Query một tọa độ

Tìm vị trí `index` của `x` trong mảng `xs` tăng. Đi từ gốc đến lá tương ứng, lấy min của:

```text
value(line_at_node, x)
```

trên tất cả các nút có đường dọc đường đi. Bất biến của Li Chao đảm bảo min thu được bằng giá trị nhỏ nhất của **mọi đường đã thêm** tại `x`. Đường bị giữ ở một nút cao hơn vẫn được xét khi truy vấn xuống nút con.

**Không cần lưu tất cả các đường tại một nút.** Một đường được thay thế ở nút có thể được đẩy xuống nhánh phù hợp để giữ khả năng đóng góp vào min.

### 7.4. Độ phức tạp trong DP

Có tối đa `n` tọa độ `S[1..n]`, trùng nhau có thể làm `K<n`:

- Tạo prefix: `O(n)`.
- Sort/dedup tọa độ: `O(n log n)`.
- Khoảng `n+1` lần thêm đường, `n` lần query: `O(n log K)`.
- Tổng **`O(n log n)` thời gian**, `O(n)` bộ nhớ ngoài input cho prefix, tọa độ, dp và cây.
- Không có giả định `a[i]≥0`.

Li Chao có thể **chậm hơn deque** trên input đơn điệu vì chi phí cây và sắp tọa độ. Chỉ nên chọn cấu trúc tổng quát khi bài toán thực sự cần.

## 8. Lỗi chính xác số học và giá trị lớn

### 8.1. Sai số khi tính giao điểm bằng double

Giả sử hệ số góc và intercept có độ lớn sát giới hạn số nguyên. Hai hoành độ giao điểm có thể chênh nhau rất nhỏ so với độ lớn của chúng. `double` chỉ có khoảng 53 bit chính xác ở phần trị, nên so sánh qua phép chia có thể làm tròn hai giao điểm thành cùng giá trị hoặc đảo thứ tự.

Với dữ liệu nguyên, tốt hơn là **nhân chéo trên số nguyên chính xác**. Nếu nhân chéo có nguy cơ tràn `long`, dùng `BigInteger` cho phần so sánh.

### 8.2. Tràn khi tính giá trị đường thẳng

Trong Java:

```java
long y = slope * x + intercept;
```

có thể bị **tràn trước khi cộng** mà không báo lỗi. Một kết quả âm giả có thể trở thành “min” và làm toàn bộ DP sai.

Chương trình dùng:

```java
long y = Math.addExact(
    Math.multiplyExact(slope, x),
    intercept);
```

Nếu toán học vượt miền `long` ở bước trung gian, API ném `ArithmeticException` thay vì trả giá trị sai. Đây là thiết kế **fail-fast**, không phải phép tính số lớn tùy ý.

### 8.3. Tràn khi mở bình phương và tính slope

`S[i]^2` và `−2*S[j]` cũng có thể tràn. Code dùng `Math.multiplyExact`, `Math.addExact`, `Math.subtractExact` ở các bước tương ứng. Với input rất lớn cần chuyển **toàn bộ** chuỗi tính sang `BigInteger` (cả dp, slope, intercept, giá trị query) hoặc dùng giới hạn số học chặt chẽ, không chỉ sửa một phép nhân.

### 8.4. Phần giao điểm chỉ cần chính xác thứ tự, không cần giá trị x thực

Trong deque CHT, ta không cần biết vị trí giao điểm đến bao nhiêu chữ số. Chỉ cần biết `x_AB≥x_BC` hay không. So sánh phân số bằng nhân chéo đúng thứ tự là đủ. Với slope giảm nghiêm ngặt, các mẫu số dương; nếu slope không theo thứ tự, công thức nhân chéo **không còn đúng với cùng dấu bất đẳng thức**.

### 8.5. Trường hợp hòa

Nếu hai đường cho cùng giá trị min tại `x`, bất kỳ đường nào cũng trả **giá trị đúng**. Nhưng nếu bài yêu cầu khôi phục cách chia đoạn sao cho ưu tiên `j` nhỏ nhất hoặc lớn nhất, cần lưu `id=j` trong đường và áp dụng tie-break có chứng minh riêng. Mã minh họa dưới đây **trả giá trị DP**, không cam kết chỉ số chuyển tiếp `j` nào được chọn khi có nhiều nghiệm tối ưu.

## 9. Java 17+ — DP chậm, deque CHT và discrete Li Chao

Chương trình **ConvexHullDPDemo.java** gồm:

- `quadraticDP(a,C)`: công thức gốc `O(n²)`, đóng vai trò oracle.
- `monotoneCHT(a,C)`: chỉ chấp nhận `a[i]≥0`, dùng deque các đường có slope không tăng và các query `x_i` không giảm.
- `liChaoDP(a,C)`: chấp nhận số âm/dương, thêm đường bất kỳ, query x bất kỳ thuộc danh sách tổng tiền tố đã nén.
- `MonotoneHull`: thêm đường, khử slope trùng, loại đường dư thừa bằng `BigInteger`, pop front ở các query x không giảm.
- `DiscreteLiChao`: cây theo các tọa độ query biết trước; mỗi nút lưu tối đa một đường.
- `verifySmallCases()`: duyệt toàn bộ input ngắn có giá trị nhỏ, đối chiếu **hai** cách tối ưu với lời giải `O(n²)` và kiểm tra các trường hợp số âm, số 0, slope trùng.

**Đặc tả code:** Input `int[]` không bị sửa; fee `C` kiểu `long`; output `long[]` gồm `dp[0]..dp[n]` để người học nhìn được toàn bộ bảng. `Math.*Exact` ném ngoại lệ nếu các phép toán vượt giới hạn của `long`. Mảng rỗng hợp lệ và trả `[0]`.

### Mã đầy đủ: ConvexHullDPDemo.java

```java
import java.math.BigInteger;
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Deque;

public class ConvexHullDPDemo {
    record Line(long slope, long intercept) {
        long at(long x) {
            return Math.addExact(
                Math.multiplyExact(slope, x), intercept);
        }
    }

    static long square(long x) {
        return Math.multiplyExact(x, x);
    }

    static long[] prefix(int[] a) {
        if (a == null) {
            throw new IllegalArgumentException("null input");
        }
        long[] s = new long[a.length + 1];
        for (int i = 0; i < a.length; i++) {
            s[i + 1] = Math.addExact(s[i], a[i]);
        }
        return s;
    }

    // Từ j: line_j(x) = -2*S[j]*x + dp[j] + S[j]^2.
    static Line makeLine(long sj, long dpj) {
        return new Line(
            Math.multiplyExact(-2L, sj),
            Math.addExact(dpj, square(sj)));
    }

    // Lời giải gốc O(n^2), dùng để kiểm thử.
    static long[] quadraticDP(int[] a, long fee) {
        long[] s = prefix(a);
        int n = a.length;
        long[] dp = new long[n + 1];

        for (int i = 1; i <= n; i++) {
            long best = Long.MAX_VALUE;
            for (int j = 0; j < i; j++) {
                long delta = Math.subtractExact(s[i], s[j]);
                long candidate = Math.addExact(
                    Math.addExact(dp[j], square(delta)), fee);
                best = Math.min(best, candidate);
            }
            dp[i] = best;
        }
        return dp;
    }

    static final class MonotoneHull {
        // Yêu cầu thêm slope không tăng, query x không giảm.
        private final Deque<Line> lines = new ArrayDeque<>();
        private long lastQuery = Long.MIN_VALUE;

        // Với ma > mb > mc, b dư thừa nếu x_ab >= x_bc.
        private static boolean redundant(Line a, Line b, Line c) {
            BigInteger left =
                BigInteger.valueOf(b.intercept())
                    .subtract(BigInteger.valueOf(a.intercept()))
                    .multiply(
                        BigInteger.valueOf(b.slope())
                            .subtract(BigInteger.valueOf(c.slope())));
            BigInteger right =
                BigInteger.valueOf(c.intercept())
                    .subtract(BigInteger.valueOf(b.intercept()))
                    .multiply(
                        BigInteger.valueOf(a.slope())
                            .subtract(BigInteger.valueOf(b.slope())));
            return left.compareTo(right) >= 0;
        }

        void add(Line incoming) {
            if (!lines.isEmpty()
                    && incoming.slope() > lines.peekLast().slope()) {
                throw new IllegalArgumentException(
                    "slopes must be nonincreasing");
            }

            // Cùng slope: chỉ giữ intercept nhỏ nhất.
            if (!lines.isEmpty()
                    && incoming.slope() == lines.peekLast().slope()) {
                if (incoming.intercept()
                        >= lines.peekLast().intercept()) {
                    return;
                }
                lines.removeLast();
            }

            // Kiểm tra đường thứ hai từ cuối có còn cần thiết.
            while (lines.size() >= 2) {
                Line b = lines.removeLast();
                Line a = lines.peekLast();
                if (!redundant(a, b, incoming)) {
                    lines.addLast(b);
                    break;
                }
            }
            lines.addLast(incoming);
        }

        long query(long x) {
            if (lines.isEmpty()) {
                throw new IllegalStateException("no lines");
            }
            if (x < lastQuery) {
                throw new IllegalArgumentException(
                    "queries must be nondecreasing");
            }
            lastQuery = x;

            while (lines.size() >= 2) {
                Line first = lines.removeFirst();
                Line second = lines.peekFirst();
                if (second.at(x) <= first.at(x)) {
                    // first sẽ không còn tốt hơn ở x tương lai.
                    continue;
                }
                lines.addFirst(first);
                break;
            }
            return lines.peekFirst().at(x);
        }

        int size() {
            return lines.size();
        }
    }

    // Dùng khi a[i] >= 0 để S[i] và query x không giảm.
    static long[] monotoneCHT(int[] a, long fee) {
        long[] s = prefix(a);
        for (int value : a) {
            if (value < 0) {
                throw new IllegalArgumentException(
                    "monotone CHT needs nonnegative increments");
            }
        }

        int n = a.length;
        long[] dp = new long[n + 1];
        MonotoneHull hull = new MonotoneHull();
        hull.add(makeLine(s[0], dp[0]));

        for (int i = 1; i <= n; i++) {
            long x = s[i];
            long best = hull.query(x);
            dp[i] = Math.addExact(
                Math.addExact(square(x), fee), best);

            // Chỉ đưa line_i vào SAU khi dp[i] đã hoàn tất.
            hull.add(makeLine(x, dp[i]));
        }
        return dp;
    }

    static final class DiscreteLiChao {
        private final long[] xs;  // Tăng nghiêm ngặt.
        private final Line[] tree;

        DiscreteLiChao(long[] queryCoordinates) {
            if (queryCoordinates == null
                    || queryCoordinates.length == 0) {
                throw new IllegalArgumentException(
                    "need at least one query coordinate");
            }
            long[] sorted = queryCoordinates.clone();
            Arrays.sort(sorted);
            int count = 0;
            for (long x : sorted) {
                if (count == 0 || sorted[count - 1] != x) {
                    sorted[count++] = x;
                }
            }
            this.xs = Arrays.copyOf(sorted, count);
            if (count > (Integer.MAX_VALUE - 5) / 4) {
                throw new IllegalArgumentException("too many x values");
            }
            this.tree = new Line[4 * count + 5];
        }

        void add(Line line) {
            addAt(1, 0, xs.length - 1, line);
        }

        // Giữ tại nút đường tốt nhất ở tọa độ giữa.
        private void addAt(int node, int left, int right,
                           Line incoming) {
            if (tree[node] == null) {
                tree[node] = incoming;
                return;
            }

            int mid = left + (right - left) / 2;
            Line incumbent = tree[node];
            boolean betterLeft =
                incoming.at(xs[left]) < incumbent.at(xs[left]);
            boolean betterMid =
                incoming.at(xs[mid]) < incumbent.at(xs[mid]);

            if (betterMid) {
                tree[node] = incoming;
                incoming = incumbent;
            }
            if (left == right) {
                return;
            }

            if (betterLeft != betterMid) {
                addAt(2 * node, left, mid, incoming);
            } else {
                addAt(2 * node + 1, mid + 1, right, incoming);
            }
        }

        long query(long x) {
            int index = Arrays.binarySearch(xs, x);
            if (index < 0) {
                throw new IllegalArgumentException(
                    "x not in known coordinates");
            }
            if (tree[1] == null) {
                throw new IllegalStateException("no lines");
            }
            return queryAt(1, 0, xs.length - 1, index, x);
        }

        private long queryAt(int node, int left, int right,
                             int index, long x) {
            long best = tree[node] == null
                    ? Long.MAX_VALUE : tree[node].at(x);
            if (left == right) {
                return best;
            }
            int mid = left + (right - left) / 2;
            long child = index <= mid
                    ? queryAt(2 * node, left, mid, index, x)
                    : queryAt(2 * node + 1, mid + 1, right, index, x);
            return Math.min(best, child);
        }
    }

    // Mọi a[i] được phép âm, dương hoặc bằng 0.
    static long[] liChaoDP(int[] a, long fee) {
        long[] s = prefix(a);
        int n = a.length;
        long[] dp = new long[n + 1];
        if (n == 0) {
            return dp;
        }

        long[] queries = Arrays.copyOfRange(s, 1, n + 1);
        DiscreteLiChao hull = new DiscreteLiChao(queries);
        hull.add(makeLine(s[0], dp[0]));

        for (int i = 1; i <= n; i++) {
            long x = s[i];
            long best = hull.query(x);
            dp[i] = Math.addExact(
                Math.addExact(square(x), fee), best);
            hull.add(makeLine(x, dp[i]));
        }
        return dp;
    }

    record Verification(int arbitraryCases, int monotoneCases) {}

    static Verification verifySmallCases() {
        int arbitrary = 0;
        int monotone = 0;

        // Mọi mảng độ dài 0..5 trên {-2,-1,0,1,2}:
        // 1+5+25+125+625+3125 = 3906 mảng.
        int variants = 1;
        for (int n = 0; n <= 5; n++) {
            for (int encoded = 0; encoded < variants; encoded++) {
                int[] a = new int[n];
                int code = encoded;
                for (int i = 0; i < n; i++) {
                    a[i] = code % 5 - 2;
                    code /= 5;
                }

                for (long fee : new long[]{-2L, 0L, 3L}) {
                    long[] expected = quadraticDP(a, fee);
                    long[] actual = liChaoDP(a, fee);
                    if (!Arrays.equals(expected, actual)) {
                        throw new AssertionError(
                            "Li Chao mismatch: " + Arrays.toString(a));
                    }
                    arbitrary++;
                }
            }
            variants *= 5;
        }

        // Mọi mảng độ dài 0..6 trên {0,1,2}:
        // 1+3+9+27+81+243+729 = 1093 mảng.
        variants = 1;
        for (int n = 0; n <= 6; n++) {
            for (int encoded = 0; encoded < variants; encoded++) {
                int[] a = new int[n];
                int code = encoded;
                for (int i = 0; i < n; i++) {
                    a[i] = code % 3;
                    code /= 3;
                }

                for (long fee : new long[]{-2L, 0L, 3L}) {
                    long[] expected = quadraticDP(a, fee);
                    long[] actual = monotoneCHT(a, fee);
                    if (!Arrays.equals(expected, actual)
                            || !Arrays.equals(expected, liChaoDP(a, fee))) {
                        throw new AssertionError(
                            "monotone mismatch: " + Arrays.toString(a));
                    }
                    monotone++;
                }
            }
            variants *= 3;
        }
        return new Verification(arbitrary, monotone);
    }

    public static void main(String[] args) {
        int[] nonnegative = {2, 1, 3, 0, 2};
        System.out.println("Prefix nonnegative: "
                           + Arrays.toString(prefix(nonnegative)));
        System.out.println("Quadratic: "
                           + Arrays.toString(quadraticDP(nonnegative, 4)));
        System.out.println("Deque CHT: "
                           + Arrays.toString(monotoneCHT(nonnegative, 4)));
        System.out.println("Li Chao: "
                           + Arrays.toString(liChaoDP(nonnegative, 4)));

        int[] signed = {2, -5, 1, 4};
        System.out.println("Prefix signed: "
                           + Arrays.toString(prefix(signed)));
        System.out.println("Quadratic signed: "
                           + Arrays.toString(quadraticDP(signed, 3)));
        System.out.println("Li Chao signed: "
                           + Arrays.toString(liChaoDP(signed, 3)));

        MonotoneHull simple = new MonotoneHull();
        simple.add(new Line(5, 0));
        simple.add(new Line(3, 1));
        simple.add(new Line(1, 0));
        System.out.println("Hull lines after redundant removal: "
                           + simple.size());
        long[] queries = {
            simple.query(-2), simple.query(0), simple.query(2)
        };
        System.out.println("Hull queries [-2,0,2]: "
                           + Arrays.toString(queries));

        MonotoneHull equalSlope = new MonotoneHull();
        equalSlope.add(new Line(2, 5));
        equalSlope.add(new Line(2, 3));
        equalSlope.add(new Line(1, 5));
        System.out.println("Equal slopes: "
                           + Arrays.toString(
                               new long[]{
                                   equalSlope.query(0),
                                   equalSlope.query(5)}));

        System.out.println("Empty DP: "
                           + Arrays.toString(liChaoDP(new int[0], 4)));

        Verification v = verifySmallCases();
        System.out.println(
            "Verified: " + v.arbitraryCases()
            + " arbitrary DP cases, " + v.monotoneCases()
            + " monotone DP cases");
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ConvexHullDPDemo.java
java ConvexHullDPDemo
```

**Stdout dự kiến**:

```text
Prefix nonnegative: [0, 2, 3, 6, 6, 8]
Quadratic: [0, 8, 13, 26, 26, 34]
Deque CHT: [0, 8, 13, 26, 26, 34]
Li Chao: [0, 8, 13, 26, 26, 34]
Prefix signed: [0, 2, -3, -2, 2]
Quadratic signed: [0, 7, 12, 7, 7]
Li Chao signed: [0, 7, 12, 7, 7]
Hull lines after redundant removal: 2
Hull queries [-2,0,2]: [-10, 0, 2]
Equal slopes: [3, 10]
Empty DP: [0]
Verified: 11718 arbitrary DP cases, 3279 monotone DP cases
```

### Tại sao các kết quả trên có ý nghĩa?

- Với dữ liệu **không âm**, prefix `S` không giảm. Deque CHT và Li Chao trả **cùng toàn bộ `dp[]`** với công thức chậm, gồm cả vị trí có `a[i]=0` dẫn tới **slope trùng**.
- Với dữ liệu **có số âm**, prefix và slope không còn đơn điệu. Li Chao vẫn trả đúng `[0,7,12,7,7]`; không chạy deque monotone vì không thỏa hợp đồng.
- Đường `B(x)=3x+1` ở ví dụ hình học bị loại trong ba đường `5x,3x+1,x`, nên deque còn 2 đường. Truy vấn `x=-2,0,2` tăng dần và trả `[-10,0,2]`.
- Trường hợp hai đường slope 2, intercept 5 và 3: giữ đường intercept 3; query ở `x=0` và `x=5` có giá trị min `3` và `10`.
- Mảng rỗng `n=0` có `dp[0]=0` theo định nghĩa “chia không phần tử”; code không tạo Li Chao với danh sách tọa độ rỗng.
- Kiểm thử 3 giá trị `C∈{-2,0,3}` trên **3906 mảng bất kỳ** độ dài 0..5 từ `{-2,-1,0,1,2}`, thành **11.718 ca Li Chao** so với DP chậm.
- Kiểm thử thêm **1093 mảng không âm** độ dài 0..6 từ `{0,1,2}`, mỗi mảng với 3 giá trị `C`, thành **3.279 ca**, đối chiếu **cả deque lẫn Li Chao** với DP chậm.
- Kiểm thử dùng công thức quy hoạch động gốc như oracle, không dùng chính cấu trúc hull để tự xác nhận hull. Điều đó giúp phát hiện sai ở điều kiện pop đầu/cuối và cách xử lý trùng slope.

### Tính an toàn của code mẫu

**Input:** `prefix(int[])` đọc mảng `a[]` mà không sửa. `DiscreteLiChao` sort trên **bản clone** của tập tọa độ. Các mảng `dp`, tree và deque được cấp phát mới; không viết vào dữ liệu của caller.

**Giới hạn giá trị:** Mọi phép bình phương, nhân slope với tọa độ và cộng số có thể tràn `long` đều dùng `Math.*Exact`. Khi không đủ miền `long`, phương thức ném ngoại lệ, **không** âm thầm trả một số min sai.

**So sánh giao điểm:** `BigInteger` chỉ được dùng ở điều kiện redundant của monotone hull để tránh tràn khi nhân chéo. Các giá trị `dp` và line evaluation vẫn dùng `long`, nên nếu đề cho cực trị vượt `long` phải mở rộng toàn bộ kiểu dữ liệu.

**Li Chao chỉ hỏi tọa độ đã khai báo:** `query(x)` dùng `Arrays.binarySearch(xs,x)`; nếu `x` không có trong mảng nén, code ném `IllegalArgumentException`. Đây là quy tắc hợp lệ của **cấu trúc rời rạc**, không phải hạn chế toán học của CHT tổng quát.

**Khởi tạo tại thời điểm đúng:** Trước `dp[1]` chỉ có `line_0`. Ở mỗi bước `i`, code query trước, cập nhật `dp[i]`, rồi mới add `line_i`. Vì thế không bao giờ vô tình dùng `j=i` cho điều kiện `j<i`.

## 10. Phân tích thời gian, bộ nhớ và lựa chọn phương pháp

| Cách giải | Điều kiện | Thời gian | Bộ nhớ ngoài input |
| --- | --- | --- | --- |
| DP chậm | Không cần monotonicity | `O(n²)` | `O(n)` cho prefix và dp |
| Monotone deque CHT | Slope thêm không tăng, query x không giảm, hỏi min | `O(n)` thao tác deque/amortized | `O(n)` cho prefix, dp và hull |
| Li Chao tọa độ rời rạc | Biết trước `K` tọa độ query, slope/x thứ tự tùy ý | `O(n log n)` gồm sort/nén, `O(log K)` mỗi add/query | `O(n+K)` |
| Hull đơn điệu + binary search giao điểm | Slope có thứ tự, query có thể tùy ý | Tùy cách xây; thường `O(log n)`/query trên hull được duy trì đúng | `O(n)` |
| Li Chao trên miền số nguyên cố định | Biết khoảng tọa độ, không nhất thiết biết từng x | `O(log R)`/thao tác với miền rộng `R`, theo biến thể | Tùy số nút cấp phát |

Với **bảng `dp[mask][last]` hoặc những bài toán không biểu diễn được thành min đường thẳng**, CHT không áp dụng trực tiếp. Với **đầu vào/đáp án vượt `long`**, thời gian phép toán đa độ dài phải được tính, và code mẫu cần chỉnh kiểu số.

**Làm rõ O(n) của deque:** Đây là tổng số push/pop khi thêm/hỏi n lần, cộng việc tính prefix, dp, bình phương theo số học có độ rộng cố định. Trong Java demo, tính `BigInteger` ở mỗi so sánh giao điểm có overhead nhưng số lần kiểm tra vẫn `O(n)`; đừng lấy một benchmark nhỏ để tuyên bố deque luôn thắng Li Chao ở mọi dữ liệu.

**Không có thuật toán tối ưu nào luôn tốt nhất.** Nếu `n` chỉ khoảng vài chục, code `O(n²)` ngắn gọn có thể rẻ hơn cấu trúc CHT phức tạp. Nếu `n` lớn nhưng input không đơn điệu, dùng deque sai không thể bù bằng tốc độ; Li Chao hoặc kỹ thuật khác mới đúng.

## 11. Lỗi phổ biến khi tối ưu DP bằng CHT

**1. Biến đổi đại số sai dấu.** Mở `(S_i−S_j)²` thành `S_i²−2S_iS_j+S_j²`. Thiếu dấu trừ trong slope `m_j=−2S_j` sẽ sai toàn bộ query.

**2. Quên cộng phần `base(i)`.** CHT chỉ trả `min_j(m_jx_i+b_j)`. Với bài chia đoạn vẫn phải cộng `S[i]²+C` sau khi query.

**3. Thêm `line_i` trước khi tính `dp[i]`.** Vi phạm `j<i`, có thể dùng chính trạng thái đang tính và tạo nghiệm không hợp lệ.

**4. Áp deque khi slope không đơn điệu.** Mảng có số âm tạo tổng tiền tố tăng giảm; phải chứng minh lại thứ tự thêm slope, không nhìn công thức rồi giả định.

**5. Áp deque khi query x giảm.** Đường đã pop đầu có thể trở lại tối ưu tại x nhỏ hơn. Dùng binary search trên hull không tiêu thụ, Li Chao hoặc phương pháp phù hợp khác.

**6. Không khử slope bằng nhau.** Hai đường song song không có giao điểm hữu hạn. Với min giữ intercept nhỏ, với max giữ intercept lớn.

**7. Sai chiều bất đẳng thức redundant.** Điều kiện ở đây dành cho **min và slope giảm**. Nếu đổi dấu/slope/query mà vẫn dùng `>=` cũ, có thể loại đường đang cần.

**8. So sánh giao điểm bằng `double` cho số nguyên cực lớn.** Sai số gần giao điểm có thể đảo thứ tự; dùng nhân chéo chính xác.

**9. Nhân chéo trên `long` rồi bỏ qua overflow.** Phép nhân có thể tràn ngay cả khi từng slope/intercept vừa `long`; dùng `BigInteger` hoặc kiểu/bounds bảo đảm đủ rộng.

**10. Chỉ kiểm tra tràn ở công thức dp, bỏ tràn line evaluation.** `m*x+b` có thể tràn trước khi query trả min. Dùng kiểm tra trên cả slope, intercept, bình phương và evaluation.

**11. Dùng Li Chao rời rạc để query x chưa nén.** Cây trên các vị trí `xs[]` chỉ được bảo đảm cho tập tọa độ đó. Muốn query ngoài tập phải xây cấu trúc trên miền khác.

**12. Nhầm Li Chao O(log K) với O(1).** Mỗi thao tác đi qua độ sâu cây, và bước sort/nén cũng cần tính vào chi phí đầu vào.

**13. Không xử lý trường hợp `n=0`.** Cần trả `dp[0]=0` và tránh xây Li Chao với danh sách tọa độ rỗng.

**14. Xóa đường đang còn tác dụng vì chỉ nhìn một truy vấn.** Pop đầu chỉ đúng khi query x tương lai không giảm và slope theo đúng hướng; pop cuối phải theo chứng minh giao điểm chứ không theo giá trị ở một x ngẫu nhiên.

**15. Nhầm min với max.** Nếu mục tiêu là max, phải đổi dấu hoặc dùng cấu trúc bao trên với thứ tự/điều kiện đúng.

**16. Truy vết không có chính sách tie-break.** Nhiều `j` có thể đạt cùng min. Nếu chỉ cần giá trị, loại một đường hòa là hợp lệ; nếu cần chỉ số `j`, phải lưu id và quy định cách phá hòa.

**17. Không đo tổng chi phí và tài nguyên.** Li Chao có overhead sắp/nén, cây và nhiều lần query. Deque có overhead BigInteger kiểm tra giao điểm. Đối với n nhỏ, `O(n²)` vẫn có thể dễ bảo trì và đủ nhanh.

## 12. Bài tập tự luyện

**Bài 1 — Mở bình phương.** Với `dp[i]=min_{j<i}(dp[j]+(S_i−S_j)^2+C)`, xác định `x_i`, slope `m_j`, intercept `b_j` và `base(i)`. Giải thích tại sao `j=i` không được phép.

**Bài 2 — Bảng DP gốc.** Dùng `a=[2,1,3,0,2]` và `C=4`, tính `S`, tất cả ứng viên `j<i` và `dp[0..5]`. So sánh với output mẫu.

**Bài 3 — Số âm phá đơn điệu.** Với `a=[2,−5,1,4]` và `C=3`, viết chuỗi `S` và dãy slope `−2S[j]`; chỉ ra lần nào slope tăng ngược điều kiện, rồi tính kết quả bằng DP chậm.

**Bài 4 — Ba đường dư thừa.** Cho `A=5x`, `B=3x+1`, `C=x`. Tính `x_AB`, `x_BC` và nhân chéo để chứng minh `B` không bao giờ cần cho min.

**Bài 5 — Đường song song.** Có ba đường `2x+7`, `2x−3`, `2x+1`. Với bài min, giữ đường nào? Với bài max, giữ đường nào? Tại sao phép tính giao điểm thông thường không dùng được?

**Bài 6 — Hai hướng đơn điệu.** Giải thích vì sao với min, slope giảm và query x tăng, ta được phép pop đầu deque. Cho phản ví dụ khi query lại giảm để thấy một đường đã pop có thể cần trở lại.

**Bài 7 — Li Chao rời rạc.** Có các query x là `[5,−2,5,0]`. Sau sort và khử trùng, mảng tọa độ có gì? Vì sao Li Chao không cần biết thứ tự các query nhưng vẫn cần biết những tọa độ được phép hỏi?

**Bài 8 — Dựng đường đi trong DP.** Nếu muốn lấy các điểm chia đoạn tối ưu, mỗi line cần giữ thêm thông tin gì? Khi hai line cùng cho một min, bạn muốn ưu tiên `j` nhỏ hay lớn? Vì sao phải xác định quy tắc này trước khi dùng pop theo dấu bằng?

**Bài 9 — Độ phức tạp.** Chứng minh tổng thao tác push/pop của monotone deque qua n lần thêm là `O(n)`. So sánh với việc quét mọi `j<i` cần `n(n+1)/2` ứng viên.

**Bài 10 — Lỗi số học.** Cho slope/intercept lớn gần `Long.MAX_VALUE`, tìm tình huống `slope*x+intercept` hoặc nhân chéo bị overflow. Vì sao dùng `BigInteger` chỉ ở redundancy chưa đủ nếu bản thân `dp` vượt `long`?

**Bài 11 — Thêm trạng thái phi tuyến.** Xét chuyển tiếp có `j` trong `j²·x_i²` và một phần còn phụ thuộc vào `i·j`. Hãy thử nhóm theo `x_i` để kiểm tra liệu có thể biểu diễn thành line hay cần hàm bậc cao hơn/cấu trúc khác. Không áp CHT khi chưa chứng minh biểu diễn tuyến tính.

**Bài 12 — Kiểm thử độc lập.** Sinh mọi mảng độ dài 0..5 với giá trị `−2..2` và các `C` nhỏ, so sánh Li Chao với `O(n²)`. Sinh mảng không âm cho deque và thử thêm các số 0 để tạo slope trùng. Vì sao các trường hợp này bắt được lỗi không dễ thấy ở input toàn số dương tăng?

## 13. Checklist trước khi dùng Convex Hull Trick

1. **Có biến đổi được không?** Công thức phải tách thành `base(i)+min_j(m_jx_i+b_j)` hoặc dạng max tương ứng.
2. **Tập j hợp lệ là gì?** Chỉ thêm đường từ các trạng thái đã giải, bảo đảm `j<i` hoặc điều kiện bài cụ thể.
3. **Xác định min/max?** Dùng đúng bao dưới/bao trên; nếu đổi dấu, hướng slope thay đổi thế nào?
4. **Thứ tự slope?** Có chứng minh slope thêm vào không tăng/không giảm không? Có các slope bằng nhau cần loại?
5. **Thứ tự query?** Query x có không giảm hoặc không tăng như cấu trúc yêu cầu không?
6. **Chọn cấu trúc đúng?** Deque cho hai thứ tự đơn điệu phù hợp; hull tìm nhị phân nếu query không thứ tự; Li Chao khi slope/x tùy ý với miền tọa độ đã xác định.
7. **So sánh giao điểm chính xác?** Dùng nhân chéo đúng chiều; có kiểm soát overflow hoặc dùng `BigInteger`?
8. **Hàm evaluation an toàn?** `m*x+b`, `S²`, `−2S` và cộng phí có vượt kiểu số không?
9. **Xử lý hòa?** Chỉ cần giá trị min hay cần id/parent của phương án tối ưu?
10. **Phân tích đúng Big-O?** Tổng `O(n²)` của bản gốc, `O(n)` amortized cho deque, `O(nlog n)` cho Li Chao rời rạc, tính thêm chi phí bộ nhớ/sort.
11. **Edge cases?** `n=0`, `n=1`, toàn số 0, mảng có số âm, slope trùng, giao điểm trùng và chi phí `C` âm/dương.
12. **Có oracle?** So với DP nguyên bản `O(n²)` trên các input nhỏ, không chỉ đối chiếu hai phiên bản tối ưu với nhau.

**Tiêu chí hoàn thành:** Bạn có thể mở một phép chuyển DP bình phương thành **truy vấn min của các đường thẳng**, chứng minh khi nào deque CHT đúng, áp dụng công thức loại đường bằng so sánh giao điểm chính xác, nhận ra lúc nào phải dùng **Li Chao tree**, triển khai Java 17+ không âm thầm overflow và đối chiếu đầu ra với một DP chậm độc lập.
