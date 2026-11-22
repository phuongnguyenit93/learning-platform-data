# Sai số biểu diễn khác sai số thuật toán trong Java

> **Java core – numbers · Sai số và ổn định**  
> **Mục tiêu:** Phân biệt sai số do lưu trữ số trong `float`/`double` với sai số do cách xây dựng phép tính hoặc thuật toán; giải thích tại sao dùng `double` chưa chắc cho kết quả đúng, và biết cách đo, giảm, kiểm thử sai số một cách có cơ sở.

## 1. Cùng một kết quả lệch, nguyên nhân có thể hoàn toàn khác

Giả sử bài toán toán học có kết quả thực là `T`, còn chương trình Java trả `R`. Việc `R ≠ T` **không đủ để kết luận** “do máy tính không lưu được số thực chính xác”.

Có ít nhất ba nguồn khác nhau:

1. **Sai số biểu diễn (*representation error*):** giá trị đầu vào hoặc hằng số toán học không được biểu diễn chính xác bằng bit của kiểu đang dùng, chẳng hạn literal `double 0.1`.
2. **Sai số làm tròn của phép toán (*roundoff error*):** kết quả của phép cộng, trừ, nhân, chia hoặc hàm toán học được làm tròn về định dạng hữu hạn. Nó liên quan đến số học dấu phẩy động nhưng có thể phát sinh **sau khi** đầu vào đã được biểu diễn chính xác.
3. **Sai số thuật toán (*algorithmic error*):** cách tính được lựa chọn gây mất thông tin, phóng đại sai số, dừng xấp xỉ quá sớm hoặc dùng một công thức số học không ổn định. Ngay cả khi dữ liệu được lưu tốt, thuật toán vẫn có thể cho kết quả kém.

Hai nhóm thường được đặt đối chiếu trong môn học này là **sai số biểu diễn** và **sai số thuật toán**; sai số làm tròn trong các phép toán là mắt xích quan trọng kết nối chúng. Cần phân biệt **sai số do bài toán/xấp xỉ** (chẳng hạn chỉ lấy vài số hạng chuỗi Taylor) với **sự bất ổn của cách triển khai** (chẳng hạn trừ hai số gần bằng nhau).

| Vấn đề | Phát sinh từ đâu? | Triệu chứng | Hướng xử lý điển hình |
| --- | --- | --- | --- |
| Biểu diễn | Số toán học không có mẫu bit chính xác trong kiểu | `0.1 + 0.2` không đúng bit với `0.3` | Chọn định dạng/kiểu phù hợp, `BigDecimal` cho decimal exact |
| Làm tròn từng bước | Phép tính có kết quả nằm giữa các số biểu diễn được | Cộng 1 vào `1e16` không thay đổi giá trị `double` | Phân tích ULP, cách nhóm, độ lớn và sai số trung gian |
| Thuật toán thiếu ổn định | Công thức/sơ đồ tính khuếch đại sai số | `sqrt(x*x+1)-x` trả 0 dù đáp án dương | Viết lại công thức tương đương ổn định hơn |
| Sai số xấp xỉ | Thuật toán cố ý dùng gần đúng hoặc dừng sớm | Dùng `1+x` thay cho `e^x` với `x` lớn | Tăng bậc xấp xỉ, kiểm soát tiêu chuẩn dừng |
| Dữ liệu đầu vào | Phép đo, làm tròn trước khi đọc vào chương trình | Hai nguồn dữ liệu đã khác nhau trước Java | Kiểm soát đo lường, định dạng nhập và hợp đồng dữ liệu |

**Điều cần nhớ:** Một lỗi số học có thể là tổng hợp nhiều nguồn sai số. Việc đổi `float` thành `double` đôi khi cải thiện đáng kể; nhưng nếu công thức tính không ổn định hoặc bài toán bị xấp xỉ sai ngay từ đầu, tăng số bit không nhất thiết giải quyết tận gốc.

## 2. Sai số biểu diễn là gì?

Máy tính lưu một số hữu hạn bit. `float` có 32 bit (24 bit chính xác hiệu dụng đối với số normal), `double` có 64 bit (53 bit chính xác hiệu dụng đối với số normal). Tập các số có thể lưu chính xác trong chúng **không phải toàn bộ số thực**.

Trong hệ 2, một số dạng `m / 2^k` có thể có biểu diễn hữu hạn nếu nằm trong miền và độ chính xác của kiểu. Nhưng phân số thập phân như `1/10` có biểu diễn nhị phân vô hạn tuần hoàn:

```text
0.1 (thập phân) = 0.000110011001100110011... (nhị phân)
                                     ^ lặp lại
```

Vì vậy literal:

```java
double x = 0.1;
```

không lưu chính xác phân số toán học `1/10`. Java chọn giá trị `double` gần nhất theo quy tắc làm tròn của dạng literal.

```java
System.out.println(Double.toHexString(0.1));
// 0x1.999999999999ap-4
```

Dạng hexadecimal floating-point hiển thị số nhị phân thực sự đã được lưu. Chuỗi này mô tả chính xác một giá trị `double` gần 0.1, nhưng **không** biến nó thành phân số thập phân 0.1 chính xác.

Một biểu hiện quen thuộc:

```java
System.out.println(0.1 + 0.2);        // 0.30000000000000004
System.out.println(0.1 + 0.2 == 0.3); // false
```

Ở đây đã có **sai số biểu diễn của đầu vào** và quá trình cộng/làm tròn. Việc in ra một chuỗi dài không có nghĩa bản thân `System.out.println` tính sai; nó chỉ chuyển giá trị nhị phân được lưu sang chuỗi thập phân để hiển thị.

### Khi số có thể biểu diễn chính xác

Không phải số decimal nào cũng bị sai số biểu diễn trong nhị phân:

```java
double a = 0.5;    // 1/2, biểu diễn chính xác
double b = 0.25;   // 1/4, biểu diễn chính xác
double c = 0.125;  // 1/8, biểu diễn chính xác

System.out.println(a + b + c); // 0.875
```

Các ví dụ này đều là tổng các phân số có mẫu là lũy thừa của 2 và có độ lớn vừa miền. Ngược lại, số nguyên đủ lớn cũng có thể mất thông tin khi chuyển sang `double`, dù viết hoàn toàn bằng chữ số nguyên thập phân.

## 3. Biểu diễn số nguyên lớn trong double cũng có giới hạn

`double` có 53 bit chính xác hiệu dụng. Nó biểu diễn chính xác mọi số nguyên trong miền từ `−2^53` đến `2^53`, nhưng không thể giữ **mọi** số nguyên lớn hơn thế với bước cách nhau 1.

```java
long original = 9_007_199_254_740_993L; // 2^53 + 1
double stored = original;

System.out.println((long) stored);
// 9007199254740992
```

Giá trị `long` ban đầu là số nguyên chính xác, nhưng chuyển sang `double` làm tròn về `9_007_199_254_740_992`. Nếu sau đó ép `double` về `long` thì con số đã mất **không được khôi phục**.

Đây là một ví dụ rõ ràng của **sai số biểu diễn/chuyển đổi dữ liệu**, không cần đến thuật toán phức tạp nào. Khi giữ ID, tiền nguyên đơn vị nhỏ nhất hoặc bộ đếm lớn, hãy dùng kiểu nguyên phù hợp (`long`, `BigInteger`) thay vì qua `double`.

**Quy tắc quan trọng:** Chọn kiểu dữ liệu theo **miền giá trị và yêu cầu chính xác**, không chỉ vì `double` có khả năng biểu diễn số rất lớn đến khoảng `1.8×10^308`. Miền độ lớn rộng không đồng nghĩa độ phân giải bằng 1 trên toàn miền.

## 4. Sai số làm tròn trong phép toán khác với sai số của đầu vào

Ngay cả khi mọi toán hạng được biểu diễn chính xác, **phép toán trung gian** vẫn có thể tạo ra kết quả không biểu diễn được với độ chính xác của kiểu.

Ví dụ:

```java
double large = 1.0e16; // số nguyên này biểu diễn chính xác bằng double
double one = 1.0;       // biểu diễn chính xác

System.out.println(large + one == large); // true
System.out.println(Math.ulp(large));      // 2.0
```

`10^16` và 1 đều có thể biểu diễn chính xác riêng lẻ. Nhưng khoảng cách giữa hai `double` kề nhau quanh `10^16` là 2, nên `10^16 + 1` nằm giữa hai giá trị biểu diễn được và được làm tròn về `10^16`.

Vì vậy câu nói “nếu đầu vào chính xác thì kết quả tính cũng chính xác” là **sai** đối với dấu phẩy động.

Một phản ví dụ về thứ tự cộng:

```java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
```

Hai biểu thức có cùng giá trị trong số thực toán học, nhưng khác vì **vị trí xảy ra phép làm tròn**. Nó minh họa sai số phép toán và ảnh hưởng của thuật toán/cách nhóm, không phải chỉ lỗi khi gõ literal 0.1.

Các phép toán số thực dấu phẩy động cũng chịu giới hạn **exponent**: tính trung gian có thể thành `Infinity` (overflow) hoặc rất gần 0 tới mức thành `subnormal`/`0.0` (underflow). Chọn thứ tự và dạng công thức đôi khi quyết định tình trạng đó.

## 5. Sai số thuật toán là gì? Không chỉ là “code sai”

Thuật toán là **trình tự phép tính** được chọn để tìm hoặc xấp xỉ lời giải. Sai số thuật toán có thể đến từ những nguyên nhân khác nhau:

- Dùng một phép **xấp xỉ toán học** thay cho hàm chính xác (ví dụ `e^x ≈ 1+x` khi `x` không đủ nhỏ).
- **Cắt cụt chuỗi/vòng lặp** trước khi đạt dung sai yêu cầu.
- Lựa chọn công thức **kém ổn định số** khiến sai số làm tròn hoặc sai số đầu vào bị khuếch đại.
- Dùng cách **cộng dồn** khiến các số nhỏ bị hấp thụ vào tổng lớn.
- Dùng sơ đồ giải phương trình hay tính đạo hàm số nhạy với bước lưới, độ chính xác hoặc số vòng lặp.

Đây không nhất thiết là lỗi logic kiểu “viết sai công thức”. Hai công thức **tương đương tuyệt đối trên số thực** vẫn có thể có chất lượng tính toán rất khác nhau khi chuyển thành một chuỗi phép toán `double`.

### Phân biệt truncation/approximation error và floating-point rounding

Một thuật toán có thể chủ động lấy gần đúng:

\[
e^x = 1+x+\frac{x^2}{2!}+\cdots
\]

Nếu dùng đúng hai số hạng đầu:

\[
e^x \approx 1+x
\]

thì tại `x = 1` giá trị xấp xỉ là **2**, trong khi giá trị toán học là khoảng **2.718281828459045...**. Chênh lệch lớn này chủ yếu do **bỏ các số hạng chuỗi**, **không** phải do Java thiếu bit lưu số 2.

```java
double firstOrder = 1.0 + 1.0;
double reference = Math.exp(1.0);

System.out.println(firstOrder); // 2.0
System.out.println(reference);  // 2.718281828459045
```

`Math.exp` vẫn trả một giá trị `double` đã làm tròn, không phải số vô hạn chữ số; nhưng kết quả này đủ để cho thấy sai số của phép xấp xỉ hai số hạng là vấn đề **thuật toán** lớn hơn rất nhiều so với một ULP quanh 2.

## 6. Một công thức toán học đúng nhưng triển khai không ổn định

Xét hàm:

\[
f(x)=\sqrt{x^2+1}-x,\qquad x>0.
\]

Trên số thực, biểu thức này luôn **dương**. Thế nhưng nếu `x` đủ lớn, `x²+1` có thể làm tròn thành `x²`, khiến kết quả gần 0 hoặc đúng bằng 0 trong `double`.

Dùng `x = 100_000_000.0`:

```java
double x = 1.0e8;
double naive = Math.sqrt(x * x + 1.0) - x;

System.out.println(naive); // 0.0
```

Giải thích tuần tự:

1. `x*x = 10^16` biểu diễn được.
2. Khi cộng 1.0 vào `10^16`, bước biểu diễn `double` quanh đó có độ rộng 2.0, nên `10^16+1` bị làm tròn lại thành `10^16`.
3. `sqrt(10^16)` trả `10^8`.
4. Trừ `x=10^8` cho kết quả `0.0`.

**Sai số biểu diễn của literal không phải thủ phạm chính:** `x = 1e8` và 1.0 đều biểu diễn chính xác. Vấn đề nằm ở **cách tổ chức phép tính trung gian**, gây mất số hạng +1 rồi trừ hai số gần bằng nhau.

### Biến đổi công thức để ổn định hơn

Nhân cả tử và mẫu với biểu thức liên hợp:

\[
\sqrt{x^2+1}-x
=\frac{(\sqrt{x^2+1}-x)(\sqrt{x^2+1}+x)}
       {\sqrt{x^2+1}+x}
=\frac{1}{\sqrt{x^2+1}+x}.
\]

Áp dụng:

```java
double x = 1.0e8;
double stable = 1.0 / (Math.sqrt(x * x + 1.0) + x);
System.out.println(stable); // 5.0E-9
```

Tuy việc tính `sqrt(x*x+1)` vẫn nhận `x` với bộ dữ liệu này, phép chia `1/(2*x)` giữ được **độ lớn đúng** của kết quả cực nhỏ: khoảng `5×10^-9`, thay vì 0.

Hai công thức **bằng nhau trong đại số số thực** (với `x>0`), nhưng dưới `double` khác hẳn về độ ổn định.

**Giới hạn của mẹo này:** Công thức đã biến đổi vẫn có thể overflow nếu `x*x` vượt miền `double`, hoặc có vấn đề ở miền đầu vào khác. Với nhiều bài toán độ lớn lớn, nên xét `Math.hypot(x, 1.0)` để tính `sqrt(x*x+1)` theo cách giảm rủi ro overflow/underflow. Không kết luận một phép biến đổi liên hợp xử lý hoàn hảo mọi đầu vào.

## 7. Công thức tính log: log1p tránh mất x gần 0

Trong toán học:

\[
\log(1+x)
\]

là công thức hoàn toàn đúng. Nhưng khi `x` cực nhỏ, phép cộng `1+x` trong `double` có thể làm tròn ngay về 1 trước khi gọi log.

```java
double x = 1.0e-16;

System.out.println(1.0 + x == 1.0); // true
System.out.println(Math.log(1.0 + x)); // 0.0
System.out.println(Math.log1p(x));     // 1.0E-16
```

Vì `x` nhỏ hơn nửa bước ULP quanh 1.0, `1+x` bị làm tròn thành 1.0. Sau đó `log(1.0)=0` là kết quả đúng của giá trị đầu vào **đã bị làm tròn**, không phải bản thân `Math.log` “không biết log”.

`Math.log1p(x)` được thiết kế để tính **log(1+x)** chính xác hơn khi `x` gần 0, tránh hình thành trung gian `1+x` kém chính xác. Tương tự, `Math.expm1(x)` tính **exp(x)-1** với độ chính xác tốt hơn khi `x` gần 0 so với cách viết `Math.exp(x)-1.0`.

Đây là ví dụ quan trọng để phân biệt:

- **Sai số biểu diễn đầu vào:** `x=1e-16` được lưu bằng một giá trị `double` gần số thập phân đó.
- **Sai số do cách tính:** biểu thức `1+x` làm mất thay đổi nhỏ trước khi áp dụng `log`.
- **Giải pháp:** chọn **hàm số học chuyên dụng** để tránh trung gian có độ phân giải không đủ.

## 8. Cộng một dãy số: thuật toán khác nhau có thể giữ hoặc mất số hạng nhỏ

Cho dãy:

```java
double[] values = {1.0e16, 1.0, -1.0e16};
```

Tổng số thực chính xác bằng 1. Cộng tuần tự:

```java
double sum = 0.0;
for (double value : values) {
    sum += value;
}
System.out.println(sum); // 0.0
```

Sau khi `sum=1e16`, cộng 1.0 bị làm tròn về `1e16`. Cộng `-1e16` tiếp theo cho 0.0. Số hạng +1 đã mất.

Nếu thay đổi thứ tự thành `{1e16, -1e16, 1.0}`, tổng tuần tự cho 1.0. Chênh lệch phát sinh từ **vị trí làm tròn**, không phải vì mỗi số hạng đầu vào không biểu diễn được.

### Neumaier compensated summation

Một thuật toán giảm sai số của phép cộng dồn là *Neumaier summation*, thuộc nhóm **compensated summation**. Thuật toán giữ biến bù để ghi nhận một phần sai số bị loại:

```java
static double neumaierSum(double[] values) {
    double sum = 0.0;
    double correction = 0.0;

    for (double x : values) {
        double t = sum + x;
        if (Math.abs(sum) >= Math.abs(x)) {
            correction += (sum - t) + x;
        } else {
            correction += (x - t) + sum;
        }
        sum = t;
    }
    return sum + correction;
}
```

Đây là **phương thức minh họa** phải đặt trong một lớp Java. Với dãy trên, nó cho 1.0. Nhưng thuật toán không bảo đảm kết quả đúng vô hạn chữ số cho mọi bộ dữ liệu, đặc biệt khi có overflow, NaN, vô cực hoặc dữ liệu vượt miền ổn định. Sự khác nhau nằm ở **thuật toán tích lũy** dù kiểu `double` và dữ liệu đầu vào vẫn như cũ.

Ở các bài toán tổng lớn, còn có **pairwise summation** (cộng theo cây cân bằng) hoặc thuật toán chuyên biệt cho mục tiêu tái lập bit-for-bit. Cần định nghĩa rõ độ chính xác và tính tái lập trước khi chọn cách song song hóa phép tổng.

## 9. Bài toán nhạy với đầu vào: condition number không phải sai số biểu diễn

Không phải mọi kết quả biến động mạnh đều do thuật toán tính kém.

Giả sử bài toán cần tính:

\[
g(x)=\frac{1}{1-x}.
\]

Khi `x` tiến sát 1, chỉ cần thay đổi rất nhỏ ở đầu vào cũng làm kết quả biến đổi đáng kể. Ví dụ trên số thực:

\[
g(0.99)=100,\qquad g(0.999)=1000.
\]

Hai giá trị đầu vào khác nhau chỉ 0.009 nhưng kết quả khác gấp 10 lần. Đây là đặc tính **nhạy đầu vào của bài toán** (*conditioning*), không chỉ do ngôn ngữ lập trình.

Phân biệt:

- **Bài toán điều kiện tốt (*well-conditioned*):** thay đổi nhỏ ở đầu vào thường chỉ gây thay đổi tương ứng nhỏ ở đầu ra theo thước đo đang xét.
- **Bài toán điều kiện kém (*ill-conditioned*):** thay đổi nhỏ ở đầu vào có thể tạo thay đổi lớn ở đầu ra.
- **Thuật toán ổn định (*numerically stable*):** cách tính không khuếch đại sai số vượt mức bất hợp lý so với độ nhạy vốn có của bài toán; cách diễn đạt định lượng cần xác định chuẩn, miền và loại ổn định (ví dụ *backward stability*).

Một thuật toán tốt không thể “đánh bại” mọi độ nhạy cố hữu của dữ liệu. Ví dụ đầu vào có sai số đo lường từ cảm biến, việc chuyển sang `BigDecimal` không thể tự phục hồi thông tin vật lý chưa từng được đo chính xác.

**Nguyên tắc chẩn đoán:** trước khi quy mọi lệch về `double`, hãy hỏi “với dữ liệu chính xác, bài toán có nhạy không?” và “thuật toán đang đưa sai số bổ sung vào ở bước nào?”.

## 10. Đo sai số: tuyệt đối, tương đối và ULP

Giả sử có kết quả tham chiếu `T` với độ tin cậy cao và kết quả tính `R`.

### 10.1. Sai số tuyệt đối

\[
E_{\mathrm{abs}} = |R-T|
\]

Ví dụ mong đợi 100.0 và nhận 100.01 thì sai số tuyệt đối là 0.01. Nó được đo bằng **cùng đơn vị** với giá trị (đồng, mét, giây...), nên thường dễ liên hệ với nghiệp vụ.

### 10.2. Sai số tương đối

Khi `T ≠ 0`:

\[
E_{\mathrm{rel}} = \frac{|R-T|}{|T|}
\]

Sai số tương đối hữu ích khi độ lớn dữ liệu trải rộng. Nhưng gần `T=0`, biểu thức này có thể rất lớn hoặc không xác định; **không dùng mỗi sai số tương đối** làm tiêu chuẩn so sánh khi mốc đúng bằng hoặc gần 0.

### 10.3. ULP (unit in the last place)

`Math.ulp(x)` thể hiện kích cỡ một bước biểu diễn quanh `x`. Ví dụ:

```java
System.out.println(Math.ulp(1.0));    // 2.220446049250313E-16
System.out.println(Math.ulp(1.0e16)); // 2.0
```

ULP giúp hiểu tại sao `double` “có độ chính xác cao” vẫn mất +1 khi cộng vào `1e16`. Nhưng **một giới hạn ULP** chỉ phù hợp khi bài toán cần đánh giá sai số gắn với các giá trị `double`, không phải mọi sai số nghiệp vụ đều được mô tả tốt bằng ULP.

### 10.4. Khi nào tham chiếu đáng tin?

Không lấy một phép tính `double` khác làm “đáp án tuyệt đối” nếu chính nó cũng chịu lỗi tương tự. Các nguồn tham chiếu tốt hơn có thể gồm:

- kết quả phân tích toán học hoặc nghiệm chính xác của trường hợp đơn giản;
- số học nguyên/bội số của 10 được lưu chính xác nếu bài toán cho phép;
- `BigDecimal` khởi tạo từ chuỗi với đủ precision và chế độ làm tròn được xác định;
- thư viện độ chính xác cao, thuật toán đã kiểm định hoặc dữ liệu chuẩn độc lập.

Với tính toán gần đúng thực tế, nên kiểm tra nhiều độ lớn, đặc biệt miền **gần 0**, **gần biên**, **dữ liệu gần bằng nhau** và **đầu vào làm đổi nhánh thuật toán**.

## 11. Chọn BigDecimal có chữa được mọi sai số không?

**Không.** `BigDecimal` giúp biểu diễn và tính toán **số thập phân chính xác theo định dạng đầu vào**, trong phạm vi tính toán và tài nguyên phù hợp. Nó đặc biệt hữu ích cho tiền hoặc dữ liệu decimal mà một chữ số cuối có ý nghĩa pháp lý/nghiệp vụ.

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
System.out.println(a.add(b)); // 0.3
```

Đây là phép cộng thập phân chính xác vì hai toán hạng được tạo từ **chuỗi**.

Nhưng:

```java
BigDecimal fromDouble = new BigDecimal(0.1);
System.out.println(fromDouble);
// 0.1000000000000000055511151231257827021181583404541015625
```

Constructor nhận `double` diễn giải chính xác **giá trị nhị phân đã được lưu**, nên không thể tự biết người dùng ban đầu muốn phân số 1/10. Nếu có một `double` và muốn tạo BigDecimal từ chuỗi decimal mà `Double.toString` biểu diễn, có thể dùng `BigDecimal.valueOf(double)`; nhưng đây là **một quy tắc chuyển đổi khác**, không phải khôi phục mọi độ chính xác bị mất.

Ngoài ra, khi dùng `MathContext` giới hạn precision, `BigDecimal` cũng có làm tròn; khi một công thức được xấp xỉ sai hoặc thuật toán dừng quá sớm, đổi kiểu không tự biến thuật toán thành chính xác.

Bảng quyết định:

| Trường hợp | Lựa chọn |
| --- | --- |
| Tiền theo chữ số thập phân, yêu cầu rounding xác định | `BigDecimal` từ chuỗi/đầu vào decimal, quy định scale và rounding |
| Tính khoa học cần tốc độ, chấp nhận dung sai số học | `double` với thuật toán ổn định và kiểm thử |
| Cần giữ số nguyên rất lớn chính xác | `BigInteger` |
| Cần tính `log(1+x)` khi `x` rất nhỏ | `Math.log1p(x)` |
| Cần tổng dài mà sai số cộng dồn đáng kể | Compensated/pairwise summation phù hợp dữ liệu |
| Bài toán đầu vào vốn không chính xác | Đánh giá sai số nguồn, sensitivity và độ bất định |
| Thuật toán lấy gần đúng quá thô | Tăng bậc/số bước hoặc đổi thuật toán, không chỉ đổi kiểu |

## 12. Thực hành kiểm thử số học an toàn

Một hàm kiểm tra gần bằng có thể kết hợp dung sai tuyệt đối và tương đối, có kiểm tra các giá trị đặc biệt:

```java
static boolean nearlyEqual(double a, double b,
                           double absoluteTolerance,
                           double relativeTolerance) {
    if (Double.isNaN(a) || Double.isNaN(b)) {
        return false;
    }
    if (a == b) {
        return true;
    }
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }

    double difference = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return difference <= Math.max(absoluteTolerance,
                                  relativeTolerance * scale);
}
```

Đây là **phương thức minh họa**, cần nằm trong một lớp. Một triển khai production phải validate hai dung sai **hữu hạn, không âm** và xử lý tình huống tràn trong việc tính sai khác/tích tương đối nếu miền dữ liệu có thể rất lớn. Không có bộ ngưỡng tùy tiện như `1e-9` phù hợp mọi bài toán.

Phải làm rõ hợp đồng so sánh:

- **Bằng nhau về biểu diễn bit:** cần cùng mẫu IEEE 754; muốn phân biệt số 0 có dấu hoặc các NaN raw bits thì dùng API raw bits phù hợp.
- **Bằng nhau theo số học thông thường:** `+0.0 == -0.0` là `true`; `NaN == NaN` là `false`.
- **Gần bằng theo nghiệp vụ:** dựa trên đơn vị đo, độ lớn đầu vào, giới hạn sai số và mức độ an toàn chấp nhận được.

**Không dùng `Double.MIN_VALUE` làm epsilon chung.** Đó là số dương subnormal nhỏ nhất, không phải ngưỡng sai số hợp lý quanh mọi giá trị.

## 13. Chương trình Java 17+ chạy độc lập

Tạo tệp **`RepresentationVsAlgorithmErrorDemo.java`**:

```java
import java.math.BigDecimal;

public class RepresentationVsAlgorithmErrorDemo {
    private static double neumaierSum(double[] values) {
        double sum = 0.0;
        double correction = 0.0;

        for (double x : values) {
            double t = sum + x;
            if (Math.abs(sum) >= Math.abs(x)) {
                correction += (sum - t) + x;
            } else {
                correction += (x - t) + sum;
            }
            sum = t;
        }
        return sum + correction;
    }

    public static void main(String[] args) {
        // Biểu diễn thập phân trong kiểu dấu phẩy động nhị phân.
        System.out.println("0.1 hex = " + Double.toHexString(0.1));
        System.out.println("0.1 + 0.2 = " + (0.1 + 0.2));
        BigDecimal exactDecimal =
                new BigDecimal("0.1").add(new BigDecimal("0.2"));
        System.out.println("decimal sum = " + exactDecimal);

        // Mất thông tin khi chuyển số nguyên quá lớn sang double.
        long original = 9_007_199_254_740_993L;
        double rounded = original;
        System.out.println("long preserved = "
                + ((long) rounded == original));
        System.out.println("rounded long = " + (long) rounded);

        // Hai công thức tương đương toán học nhưng khác độ ổn định.
        double x = 1.0e8;
        double naive = Math.sqrt(x * x + 1.0) - x;
        double stable = 1.0 / (Math.sqrt(x * x + 1.0) + x);
        System.out.println("naive formula = " + naive);
        System.out.println("stable formula = " + stable);

        // Hàm chuyên dụng bảo toàn độ chính xác gần 0 tốt hơn.
        double tiny = 1.0e-16;
        System.out.println("log(1+x) = " + Math.log(1.0 + tiny));
        System.out.println("log1p(x) = " + Math.log1p(tiny));

        // Cộng dồn theo hai thuật toán khác nhau.
        double[] values = {1.0e16, 1.0, -1.0e16};
        double normalSum = 0.0;
        for (double value : values) {
            normalSum += value;
        }
        System.out.println("simple sum = " + normalSum);
        System.out.println("corrected sum = " + neumaierSum(values));

        // Sai số xấp xỉ do cố ý cắt chuỗi Taylor, không phải
        // chỉ vì số 2.0 bị lưu kém chính xác.
        double firstOrder = 1.0 + 1.0;
        System.out.println("first-order exp(1) = " + firstOrder);
        System.out.println("Math.exp(1) = " + Math.exp(1.0));
    }
}
```

Trong thư mục chứa tệp:

```bash
javac RepresentationVsAlgorithmErrorDemo.java
java RepresentationVsAlgorithmErrorDemo
```

**Kết quả chuẩn trên Java 17+:**

```text
0.1 hex = 0x1.999999999999ap-4
0.1 + 0.2 = 0.30000000000000004
decimal sum = 0.3
long preserved = false
rounded long = 9007199254740992
naive formula = 0.0
stable formula = 5.0E-9
log(1+x) = 0.0
log1p(x) = 1.0E-16
simple sum = 0.0
corrected sum = 1.0
first-order exp(1) = 2.0
Math.exp(1) = 2.718281828459045
```

**Giải thích đầu ra theo nguồn sai số:**

1. `0.1` không thể lưu chính xác dạng nhị phân hữu hạn: **sai số biểu diễn**.
2. `2^53 + 1` không thể giữ nguyên khi đưa vào `double`: **sai số chuyển đổi/biểu diễn**, dù đầu vào nguyên hoàn toàn chính xác.
3. `sqrt(x*x+1)-x` ra 0 trong khi công thức liên hợp ra khoảng `5e-9`: **thuật toán/công thức kém ổn định dưới rounding**.
4. `log(1+x)` ra 0 còn `log1p(x)` giữ số nhỏ: **chọn hàm tính ổn định hơn**.
5. Tổng tuần tự mất +1 còn tổng có bù giữ được +1: **khác nhau về thuật toán tổng** trên cùng dữ liệu.
6. `1+x` thay cho `exp(x)` ở `x=1` sai số lớn vì **cắt chuỗi xấp xỉ**, ngay cả với các số đơn giản có thể lưu chính xác.

## 14. Lỗi nhận định thường gặp

| Kết luận sai | Cách hiểu đúng |
| --- | --- |
| “Mọi phép tính sai vì `double` không lưu chính xác 0.1” | Có lỗi từ biểu diễn, rounding phép toán, thuật toán, dữ liệu và điều kiện bài toán |
| “Đầu vào là số nhị phân chính xác thì đầu ra chắc chắn chính xác” | Phép toán trung gian có thể làm tròn hoặc tràn |
| “Dùng `double` thay `float` sửa mọi lỗi” | Cải thiện độ chính xác nhưng không sửa thuật toán kém ổn định hoặc xấp xỉ sai |
| “Công thức tương đương đại số cho kết quả Java giống nhau” | Đổi ngoặc/dạng công thức thay vị trí làm tròn |
| “Cứ tính nhiều vòng lặp hơn thì luôn chính xác hơn” | Có thể giảm truncation error nhưng tích lũy roundoff hoặc bất ổn |
| “Bài toán nhạy đầu vào là do thuật toán lập trình sai” | Conditioning là thuộc tính của bài toán; stability là thuộc tính thuật toán |
| “Phép trừ gần bằng nhau tự động sai” | Nó có thể chính xác trên toán hạng đã lưu; rủi ro là làm lộ/phóng đại sai số tương đối có sẵn |
| “`BigDecimal` chữa được input double đã sai” | Không tự phục hồi dữ liệu đã bị làm tròn hoặc thông tin chưa được đo |
| “`Math.log(1+x)` tốt như `Math.log1p(x)` ở gần 0” | Bước `1+x` có thể làm mất x trước khi log chạy |
| “Cộng mảng bằng thứ tự nào cũng như nhau” | Kết quả floating-point phụ thuộc các bước làm tròn và thứ tự gộp |
| “`Double.MIN_VALUE` là dung sai mặc định tốt” | Không; cần xác định dung sai theo thang đo và nghiệp vụ |
| “Tham chiếu `Math.exp` là số thực vô hạn chính xác” | Hàm trả giá trị `double` hữu hạn có sai số xấp xỉ/làm tròn theo quy tắc API |

## 15. Bài tập tự kiểm tra và lời giải

**Bài 1.** Vì sao `0.1 + 0.2 == 0.3` có thể `false`? Đây là sai số biểu diễn hay thuật toán?  
**Đáp án:** `0.1`, `0.2`, `0.3` được làm tròn từ các giá trị thập phân sang các giá trị `double` nhị phân; phép cộng cũng có làm tròn. Ví dụ thể hiện ảnh hưởng biểu diễn và rounding, **chưa tự nó chứng minh công thức thuật toán sai**.

**Bài 2.** `long n = 9_007_199_254_740_993L; double d = n;` có giữ được `n` không?  
**Đáp án:** Không. `n=2^53+1` không thể biểu diễn như `double` chính xác; `d` làm tròn về `2^53`. Đây là mất dữ liệu khi chuyển kiểu.

**Bài 3.** Khi `x=1e8`, vì sao `sqrt(x*x+1)-x` cho 0 dù kết quả toán học dương?  
**Đáp án:** `x*x+1` làm tròn về `x*x`; căn trả `x` rồi trừ `x` thành 0. Công thức liên hợp `1/(sqrt(x*x+1)+x)` tránh phép trừ kém ổn định cho miền giá trị này.

**Bài 4.** Tại sao `Math.log1p(1e-16)` tốt hơn `Math.log(1+1e-16)`?  
**Đáp án:** `1+1e-16` trong `double` làm tròn thành 1, làm mất độ lớn nhỏ trước khi log. `log1p` được thiết kế tính chính `log(1+x)` khi x gần 0 mà không bị lỗi trung gian ấy.

**Bài 5.** Nếu chương trình lấy `1+x` để xấp xỉ `exp(x)` tại `x=1`, thay `double` bằng `BigDecimal` có làm đáp án bằng `e` không?  
**Đáp án:** Không. Sai số do bỏ số hạng bậc hai trở lên của chuỗi Taylor; phải đổi/tăng độ chính xác của thuật toán xấp xỉ.

**Bài 6.** Phân biệt một bài toán *ill-conditioned* với một thuật toán *unstable*.  
**Đáp án:** Ill-conditioned nghĩa là nghiệm toán học nhạy với thay đổi nhỏ ở đầu vào. Unstable nghĩa là quá trình tính số gây sai số vượt mức chấp nhận so với độ nhạy của bài toán. Có thể có bài toán nhạy nhưng thuật toán vẫn tương đối ổn định, hoặc bài toán vốn tốt nhưng triển khai kém.

**Bài 7.** Khi so sánh kết quả gần 0, tại sao chỉ dùng tỷ lệ sai số tương đối có thể gây khó?  
**Đáp án:** Vì mẫu tham chiếu gần 0 làm tỷ lệ rất lớn hoặc không xác định khi tham chiếu bằng 0. Dung sai tuyệt đối có ý nghĩa hơn trong vùng này, kết hợp dung sai tương đối ở vùng độ lớn lớn hơn.

**Bài 8.** Với mảng `{1e16,1.0,-1e16}`, cách đơn giản cho 0.0 nhưng tổng toán học là 1. Thuật toán nào có thể cải thiện?  
**Đáp án:** Tổng có bù kiểu Neumaier hoặc thuật toán phù hợp dữ liệu có thể giữ lại số 1 trong ví dụ này. Cần kiểm thử khi đổi dữ liệu, không mặc định mọi phương pháp bù đều đúng tuyệt đối.

## 16. Checklist phân tích sai số trước khi sửa chương trình

1. **Định nghĩa kết quả đúng**: số thực lý tưởng, giá trị decimal theo hợp đồng, hay kết quả thuật toán có dung sai?
2. **Kiểm tra dữ liệu đầu vào**: đã có sai số đo đạc, parse, cast, literal thập phân hoặc chuyển `long → double` chưa?
3. **Kiểm tra các trung gian**: có cộng số rất nhỏ vào số lớn, trừ hai số gần bằng nhau, overflow/underflow hay mất bit không?
4. **Kiểm tra công thức**: có cách viết tương đương ổn định hơn, `Math.log1p`/`Math.expm1`/`Math.hypot` hoặc thuật toán đặc biệt không?
5. **Phân biệt sai số xấp xỉ**: bậc chuỗi, bước lưới, tiêu chuẩn dừng, số vòng lặp có đáp ứng mục tiêu không?
6. **Đánh giá conditioning**: bài toán nhạy với đầu vào đến mức nào; đầu vào đo được có đủ độ chính xác cần thiết?
7. **Chọn kiểu và thuật toán theo mục tiêu**: primitive, `BigInteger`, `BigDecimal`, tổng có bù hay thuật toán độ chính xác cao?
8. **Đặt thước đo rõ ràng**: sai số tuyệt đối, tương đối hoặc ULP; xử lý trường hợp 0, NaN, vô cực và miền giá trị rất lớn.
9. **Kiểm thử tình huống biên**: khác nhau nhiều bậc độ lớn, số gần bằng nhau, gần zero, giá trị sát giới hạn kiểu, dữ liệu âm và dương xen kẽ.
10. **Ghi lại giả định và dung sai** trong API, test và tài liệu; đừng vá lỗi bằng một epsilon cố định không có cơ sở.

**Kết luận:** *Sai số biểu diễn* xuất hiện khi một giá trị không vừa chính xác trong định dạng lưu trữ; *sai số phép toán* xuất hiện khi các bước tính phải làm tròn; *sai số thuật toán* xuất hiện vì lựa chọn phép tính/xấp xỉ có thể mất hoặc khuếch đại thông tin. Ba nguồn có thể cộng hưởng. Muốn xử lý đúng, hãy tìm **bước đầu tiên thông tin bị mất**, đánh giá đặc tính bài toán, rồi chọn kiểu dữ liệu và công thức thích hợp thay vì chỉ tăng số chữ số in ra.
