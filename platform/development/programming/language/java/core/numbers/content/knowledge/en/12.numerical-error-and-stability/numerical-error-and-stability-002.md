# Sai số tuyệt đối, tương đối và tích lũy qua nhiều bước trong Java

## 1. Mục tiêu và bối cảnh

Kết quả tính toán trong Java có thể khác giá trị toán học lý tưởng vì biểu diễn số hữu hạn, làm tròn ở mỗi phép toán, thứ tự thực hiện phép tính và sai số vốn có trong dữ liệu đầu vào. Với `float` và `double`, những chênh lệch rất nhỏ có thể tích lũy khi thực hiện hàng nghìn hoặc hàng triệu bước.

Bài học tập trung vào ba câu hỏi:

1. **Sai số tuyệt đối**: kết quả tính toán lệch bao nhiêu đơn vị so với giá trị tham chiếu?
2. **Sai số tương đối**: độ lệch đó lớn hay nhỏ so với độ lớn của giá trị tham chiếu?
3. **Sai số tích lũy**: khi thực hiện nhiều phép cộng, trừ, nhân, chia hoặc phép lặp, sai số lan truyền và tăng lên như thế nào, và giảm rủi ro ra sao?

Ta sẽ dùng Java 17+, `double`, `BigDecimal`, `Math.ulp`, thuật toán cộng bù Kahan và các tình huống mất chữ số có nghĩa. Không có một ngưỡng sai số cố định nào phù hợp cho mọi nghiệp vụ.

## 2. Giá trị tham chiếu, giá trị xấp xỉ và nguồn sai số

Ký hiệu:

- \(x\): giá trị đúng (hoặc giá trị tham chiếu được chấp nhận trong bài toán).
- \(\hat{x}\): kết quả xấp xỉ do chương trình tính hoặc đo được.
- \(\hat{x}-x\): **sai số có dấu**; cho biết kết quả cao hơn hay thấp hơn tham chiếu.
- \(|\hat{x}-x|\): **độ lớn sai số**; không phụ thuộc dấu.

Cần phân biệt:

| Nguồn sai số | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Sai số dữ liệu đầu vào | Cảm biến ghi 9,98 m thay vì 10 m | Đầu vào đã không chính xác tuyệt đối |
| Sai số biểu diễn | `0.1` không có biểu diễn nhị phân hữu hạn | Dữ liệu số thực bị làm tròn ngay khi lưu |
| Sai số làm tròn phép toán | Cộng hai `double` rồi lưu kết quả vào `double` | Kết quả chính xác có thể nằm giữa hai giá trị biểu diễn được |
| Sai số cắt cụt thuật toán | Lấy 5 số hạng đầu của chuỗi vô hạn | Xấp xỉ do phương pháp toán học, ngay cả với số thực lý tưởng |
| Sai số tích lũy/lan truyền | Cộng nhiều giá trị nhỏ vào tổng lớn | Lỗi từng bước có thể làm thay đổi kết quả cuối |

Sai số biểu diễn và sai số phép toán thường được gọi chung là **floating-point rounding error**. Sai số cắt cụt xuất phát từ thuật toán và phải được phân tích riêng. Với bài toán đo đạc, giá trị “đúng” có thể không biết; khi đó chỉ có thể nói đến sai số so với tham chiếu có độ tin cậy, khoảng bất định hoặc giới hạn sai số đã được chứng minh.

## 3. Sai số tuyệt đối

**Định nghĩa**:

\[
E_{\mathrm{abs}} = |\hat{x} - x|
\]

Sai số tuyệt đối có **cùng đơn vị đo** với đại lượng ban đầu. Nếu một chiều dài đúng là 100 m và chương trình trả 99 m thì \(E_{\mathrm{abs}}=1\) m.

~~~java
double reference = 100.0;
double approximate = 99.0;
double absoluteError = Math.abs(approximate - reference);

System.out.println(absoluteError); // 1.0
~~~

Đây là đoạn minh họa đặt trong một phương thức.

**Ưu điểm:** dễ giải thích bằng đơn vị nghiệp vụ. Sai lệch 0,5°C, 1 mm hay 2 đồng tiền tệ mang ý nghĩa trực tiếp tùy hoàn cảnh.

**Giới hạn:** cùng sai số tuyệt đối chưa chắc quan trọng như nhau. Sai lệch 1 m đối với đoạn đường 100 m khác hẳn sai lệch 1 m khi đo chiều dài 1.000.000 m. Để so sánh giữa các thang đo, cần sai số tương đối.

### Cẩn trọng khi tính hiệu của hai double

Biểu thức `Math.abs(approximate - reference)` là cách tính thông dụng, nhưng vẫn dùng số học `double`. Nếu hai số hữu hạn cực lớn có dấu trái ngược nhau, phép trừ có thể **overflow** thành `Infinity`; với độ lệch cực nhỏ, sự khác biệt có thể đã bị làm tròn về 0 trước khi ta đo. Vì vậy sai số tính bằng `double` cũng có giới hạn độ chính xác và miền biểu diễn.

Nếu cần sai số thập phân chính xác và dữ liệu đầu vào vốn là số thập phân, hãy giữ chúng bằng `BigDecimal` từ đầu.

## 4. Sai số tương đối

Khi \(x \ne 0\), sai số tương đối được định nghĩa:

\[
E_{\mathrm{rel}} = \frac{|\hat{x}-x|}{|x|}
\]

Nó là tỷ lệ không có đơn vị. Nhân với 100 để đổi sang phần trăm:

\[
E_{\%} = 100E_{\mathrm{rel}}\%
\]

Ví dụ \(\hat{x}=99,\ x=100\):

\[
E_{\mathrm{abs}}=1,\qquad E_{\mathrm{rel}}=0{,}01,\qquad E_{\%}=1\%.
\]

~~~java
double reference = 100.0;
double approximate = 99.0;

double absError = Math.abs(approximate - reference);
double relativeError = absError / Math.abs(reference);
double percentError = relativeError * 100.0;

System.out.println(absError);      // 1.0
System.out.println(relativeError); // 0.01
System.out.println(percentError);  // 1.0
~~~

### Trường hợp giá trị tham chiếu bằng hoặc rất gần 0

Nếu \(x=0\), công thức sai số tương đối **không xác định**, vì mẫu số bằng 0. Không nên báo `Infinity`, `NaN` hoặc tự gán 0% mà không giải thích. Khi kết quả mong muốn bằng 0, có thể dùng **sai số tuyệt đối** theo một ngưỡng phù hợp.

Nếu \(x\) rất gần 0 nhưng khác 0, chỉ một sai số tuyệt đối nhỏ cũng có thể tạo sai số tương đối rất lớn:

| Giá trị đúng | Kết quả | Sai số tuyệt đối | Sai số tương đối |
| --- | --- | --- | --- |
| 100 | 99 | 1 | 1% |
| 1 | 0,99 | 0,01 | 1% |
| 0,000001 | 0,000002 | 0,000001 | 100% |
| 0 | 0,000001 | 0,000001 | Không xác định |

Dòng thứ ba cho thấy một chênh lệch rất nhỏ theo đơn vị có thể là **sai lệch 100%** so với giá trị mục tiêu.

### Relative error khác relative difference

Sai số tương đối đúng nghĩa đòi hỏi có giá trị chuẩn \(x\). Nếu chỉ có hai kết quả xấp xỉ `a` và `b`, ta có thể tính **độ chênh tương đối** bằng một mẫu số do ứng dụng quy định, chẳng hạn \(\max(|a|,|b|)\), nhưng không được mặc nhiên gọi đó là sai số so với “giá trị đúng” chưa biết.

## 5. Vì sao số thực dấu phẩy động có sai số?

Java `float` dùng IEEE 754 binary32 và `double` dùng binary64. Một số thập phân như 0,1 có mẫu nhị phân vô hạn, nên được lưu dưới dạng giá trị nhị phân gần nhất mà kiểu dữ liệu biểu diễn được.

~~~java
double value = 0.1 + 0.2;
System.out.println(value); // 0.30000000000000004
~~~

Trong số học thập phân lý tưởng, \(0{,}1+0{,}2=0{,}3\); còn trong binary64, hai toán hạng đã được làm tròn trước phép cộng, và phép cộng cũng làm tròn. Giá trị in ra thể hiện sự khác biệt có thể quan sát giữa hai kết quả binary64.

**Lưu ý:** số `0.30000000000000004` không chứng tỏ Java thực hiện phép cộng tùy tiện. Đây là kết quả của quy tắc làm tròn xác định. Lỗi xảy ra khi ta đòi hỏi phép toán nhị phân phải có tính chất của phép toán thập phân chính xác.

### ULP, machine epsilon và unit roundoff

- `Math.ulp(x)` trả về độ lớn của một **unit in the last place** tại giá trị `x`, theo quy tắc của API Java.
- `Math.ulp(1.0)` bằng \(2^{-52}\approx 2{,}220446049250313\times10^{-16}\): khoảng cách giữa 1,0 và số `double` kế tiếp lớn hơn 1,0.
- Với binary64 làm tròn gần nhất, *unit roundoff* thường ký hiệu \(u=2^{-53}\approx1{,}1102230246251565\times10^{-16}\). Trong nhiều tài liệu, thuật ngữ “machine epsilon” được dùng cho \(2^{-52}\) hoặc đôi khi cho \(u\); cần kiểm tra **định nghĩa** của tài liệu trước khi so sánh số liệu.

~~~java
System.out.println(Math.ulp(1.0)); // 2.220446049250313E-16
System.out.println(1.0 + Math.ulp(1.0) > 1.0); // true
~~~

**ULP không phải một hằng số cho mọi độ lớn.** Khoảng cách giữa các số `double` kề nhau thay đổi theo số mũ. Ở giá trị lớn, một bước ULP có thể lớn hơn 1; ở vùng gần 0, có các số subnormal với bước nhỏ nhất `Double.MIN_VALUE`.

## 6. Sai số tích lũy qua phép cộng lặp

Một ví dụ đơn giản là cộng `0.1` mười lần:

~~~java
double total = 0.0;
for (int i = 0; i < 10; i++) {
    total += 0.1;
}
System.out.println(total); // 0.9999999999999999
~~~

Kết quả mong muốn theo số học thập phân chính xác là 1.0. Sau mỗi phép cộng, Java lưu một giá trị `double` đã làm tròn. Sai số của những bước trước trở thành dữ liệu đầu vào cho bước tiếp theo.

Một phép nhân được biểu diễn khác:

~~~java
System.out.println(0.1 * 10.0); // 1.0
~~~

Trong trường hợp này, tích được làm tròn đến đúng `1.0`. Không nên kết luận “nhân luôn chính xác hơn cộng”: hai chuỗi phép toán khác nhau dẫn tới cách làm tròn khác nhau, và điều ngược lại có thể xảy ra với dữ liệu khác.

### Có phải sai số luôn tăng từng bước?

Không. Sai số có dấu có thể cộng dồn, triệt tiêu nhau hoặc thay đổi hướng; không phải mỗi bước đều khiến sai số tuyệt đối lớn hơn. Tuy nhiên, với nhiều thao tác, **giới hạn trên của sai số** thường tăng và kết quả có thể trở nên nhạy cảm với thứ tự tính toán.

Điều này khiến hai cách tổng hợp cùng một tập số thực có thể cho các kết quả hơi khác, đặc biệt khi dữ liệu trải rộng trên nhiều bậc độ lớn.

## 7. Mất chữ số có nghĩa (catastrophic cancellation)

Một số rất lớn cộng một số rất nhỏ có thể làm mất hoàn toàn phần nhỏ:

~~~java
double large = 1e16;
System.out.println(large + 1.0 == large); // true
System.out.println(Math.ulp(large));       // 2.0
~~~

Vì khoảng cách giữa các số binary64 kề nhau tại \(10^{16}\) là 2, thêm 1 nằm tại ranh giới làm tròn và kết quả được làm tròn về `large`. Nếu sau đó trừ `large`, ta thu được:

~~~java
double lost = (1e16 + 1.0) - 1e16;
double kept = (1e16 - 1e16) + 1.0;

System.out.println(lost); // 0.0
System.out.println(kept); // 1.0
~~~

Trong số học thực, cả hai kết quả là 1.0. Với binary64, kết quả trung gian đã làm mất số 1 nên phép trừ không thể khôi phục nó.

**Cancellation** còn xảy ra khi trừ hai số gần nhau. Bản thân phép trừ giữa hai số floating point có thể được làm tròn rất tốt hoặc thậm chí chính xác, nhưng **sai số tương đối của dữ liệu đầu vào** bị phóng đại khi kết quả đúng của phép trừ rất gần 0. Do đó phải xét độ chính xác của cả đầu vào và phép tính, thay vì luôn đổ lỗi cho phép trừ cuối cùng.

### Tính kết hợp không còn bảo đảm

Về mặt toán học, \((a+b)+c=a+(b+c)\). Trong floating point, thứ tự làm tròn khác nhau, nên phép cộng **không có tính kết hợp tuyệt đối**. Trình tự cộng, nhân song song và cách gộp các kết quả từng phần có thể ảnh hưởng các bit thấp của kết quả.

## 8. Đánh giá sai số khi có nhiều bước tính

Giả sử cộng \(n\) số trong `double` và ta dùng mô hình làm tròn tương đối chuẩn:

\[
\operatorname{fl}(a+b) = (a+b)(1+\delta), \qquad |\delta|\le u
\]

với \(u=2^{-53}\) của binary64 làm tròn gần nhất, khi phép toán thuộc miền mà mô hình trên áp dụng (không có overflow và các vấn đề underflow làm mô hình không còn đúng).

Một giới hạn thường dùng trong phân tích tổng tuần tự là:

\[
|\widehat{S}-S|\ \le\ \gamma_{n-1}\sum_{i=1}^{n}|x_i|,
\quad
\gamma_k=\frac{ku}{1-ku},
\quad ku<1,
\]

trong đó \(S=\sum_i x_i\) là tổng chính xác của **những số thực đã đưa vào phép cộng**, còn \(\widehat{S}\) là tổng được tính với làm tròn ở từng bước. Đây là giới hạn lý thuyết trong các giả thiết nêu trên; nó **không bao gồm sai số khi chuyển dữ liệu thập phân hoặc phép đo ban đầu thành binary64**.

Có ba điểm cần hiểu:

1. Khi \(nu\) nhỏ, \(\gamma_{n-1}\) xấp xỉ \((n-1)u\); nhiều phép cộng hơn có thể cho giới hạn sai số lớn hơn.
2. Giới hạn có \(\sum |x_i|\). Nếu các số dương và âm gần triệt tiêu, tổng thật \(S\) có thể nhỏ, nên **sai số tương đối của tổng** có thể rất lớn dù sai số tuyệt đối còn nhỏ.
3. Đây là **cận xấu nhất theo mô hình**, không phải lời hứa sai số thực tế bằng \((n-1)u\) hoặc chắc chắn tăng đều. Các sai số làm tròn có thể triệt tiêu; trong một số mô hình ngẫu nhiên, tốc độ tăng sai số thực tế nhỏ hơn cận xấu nhất.

Khi phép toán chỉ có vài bước, thường kiểm tra bằng dữ liệu biên và lời giải tham chiếu đủ chính xác. Khi số bước lớn, ngoài kiểm thử còn nên lựa chọn thuật toán ổn định và phân tích miền giá trị.

## 9. Phép cộng bù Kahan để giảm mất mát khi cộng dồn

**Kahan compensated summation** giữ thêm một biến hiệu chỉnh nhỏ để bù lại phần thấp bị mất khi cộng số nhỏ vào tổng hiện tại.

~~~java
static double kahanSum(double[] values) {
    double sum = 0.0;
    double correction = 0.0;

    for (double value : values) {
        double adjusted = value - correction;
        double next = sum + adjusted;
        correction = (next - sum) - adjusted;
        sum = next;
    }
    return sum;
}
~~~

Đây là **phương thức độc lập ở cấp lớp**, có thể đặt trong một lớp Java rồi gọi từ `main`. Thuật toán dùng các phép toán số thực thông thường và có lợi cho nhiều dãy cộng dài.

Ví dụ áp dụng:

~~~java
double[] tenths = new double[10];
java.util.Arrays.fill(tenths, 0.1);
System.out.println(kahanSum(tenths)); // 1.0
~~~

Trong ví dụ này, Kahan trả `1.0`, cải thiện so với phép cộng tuần tự thông thường `0.9999999999999999`.

**Giới hạn:** Kahan không làm mọi phép cộng trở thành số học thực chính xác; kết quả còn phụ thuộc cách biểu diễn đầu vào, thứ tự phép toán, overflow, underflow và đặc tính dãy số. Nó cũng không khôi phục sai số đo hoặc chữ số đã mất **trước khi** các phần tử được đưa vào mảng.

Các cách khác nên cân nhắc là **pairwise summation** (cộng theo cây cân bằng), sắp xếp dãy theo độ lớn khi phù hợp, dùng thuật toán ổn định về mặt số học hoặc tăng độ chính xác của biểu diễn.

## 10. Chương trình Java 17+ hoàn chỉnh

Lưu mã thành tệp `ErrorMetricsDemo.java`:

~~~java
import java.math.BigDecimal;
import java.util.Arrays;

public class ErrorMetricsDemo {
    static double absoluteError(double approximate, double reference) {
        return Math.abs(approximate - reference);
    }

    static double relativeError(double approximate, double reference) {
        if (reference == 0.0) {
            throw new IllegalArgumentException("Reference must not be zero");
        }
        return absoluteError(approximate, reference) / Math.abs(reference);
    }

    static double naiveSum(double[] values) {
        double sum = 0.0;
        for (double value : values) {
            sum += value;
        }
        return sum;
    }

    static double kahanSum(double[] values) {
        double sum = 0.0;
        double correction = 0.0;
        for (double value : values) {
            double adjusted = value - correction;
            double next = sum + adjusted;
            correction = (next - sum) - adjusted;
            sum = next;
        }
        return sum;
    }

    public static void main(String[] args) {
        System.out.println("absolute=" + absoluteError(99.0, 100.0));
        System.out.println("relative=" + relativeError(99.0, 100.0));

        double[] values = new double[10];
        Arrays.fill(values, 0.1);
        System.out.println("naive=" + naiveSum(values));
        System.out.println("kahan=" + kahanSum(values));
        System.out.println("product=" + (0.1 * 10.0));

        System.out.println("ulp(1)=" + Math.ulp(1.0));
        System.out.println("ulp(1e16)=" + Math.ulp(1e16));

        double lost = (1e16 + 1.0) - 1e16;
        double kept = (1e16 - 1e16) + 1.0;
        System.out.println("lost=" + lost);
        System.out.println("kept=" + kept);

        BigDecimal decimalSum = BigDecimal.ZERO;
        for (int i = 0; i < 10; i++) {
            decimalSum = decimalSum.add(new BigDecimal("0.1"));
        }
        System.out.println("decimal=" + decimalSum);
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac --release 17 ErrorMetricsDemo.java
java ErrorMetricsDemo
~~~

Kết quả stdout:

~~~text
absolute=1.0
relative=0.01
naive=0.9999999999999999
kahan=1.0
product=1.0
ulp(1)=2.220446049250313E-16
ulp(1e16)=2.0
lost=0.0
kept=1.0
decimal=1.0
~~~

Giải thích:

- Sai số tuyệt đối giữa 99 và 100 bằng 1, còn sai số tương đối bằng 0,01 = 1%.
- Cộng `0.1` tuần tự mười lần không cho chính xác `1.0`; Kahan giảm mất mát làm tròn trong ví dụ này.
- `Math.ulp` tại \(10^{16}\) là 2, nên thêm 1 không thể làm tăng giá trị lưu trữ trong trường hợp này.
- Hai cách đặt dấu ngoặc cho phép trừ chứng minh thứ tự tính toán có thể thay đổi kết quả.
- `BigDecimal("0.1")` giữ đúng **giá trị thập phân 0,1**, nên cộng mười lần cho chuỗi thập phân `1.0`.

## 11. So sánh số thực bằng tolerance

Dùng `a == b` chỉ khi nghiệp vụ thực sự cần **cùng giá trị binary floating point**. Nếu hai kết quả được tính qua các quy trình khác nhau, so sánh xấp xỉ thường dùng kết hợp **ngưỡng tuyệt đối** và **ngưỡng tương đối**:

\[
|a-b|\ \le\ \text{absTol}+\text{relTol}\times\max(|a|,|b|).
\]

- `absTol` có đơn vị tương ứng đại lượng và hữu ích khi hai giá trị gần 0.
- `relTol` không có đơn vị, giúp dung sai tăng phù hợp với thang giá trị lớn.
- Các ngưỡng phải xuất phát từ **yêu cầu bài toán hoặc cận sai số** chứ không phải hằng “epsilon” được sao chép tùy tiện.

Ví dụ minh họa dành cho các số hữu hạn có hiệu và phép nhân ngưỡng vẫn biểu diễn được bằng `double`:

~~~java
static boolean nearlyEqual(double a, double b,
                           double absTol, double relTol) {
    if (!Double.isFinite(a) || !Double.isFinite(b)
            || !Double.isFinite(absTol) || !Double.isFinite(relTol)
            || absTol < 0.0 || relTol < 0.0) {
        return false;
    }

    double limit = absTol
            + relTol * Math.max(Math.abs(a), Math.abs(b));
    return Math.abs(a - b) <= limit;
}
~~~

Đây là **phương thức minh họa bên trong một lớp**, không phải chương trình độc lập. Với giá trị quá lớn, `Math.abs(a-b)` hoặc `limit` có thể overflow thành Infinity; khi so sánh độ chính xác cao trên toàn miền `double`, cần thuật toán so sánh được thiết kế tránh tràn/underflow hoặc chuyển sang mô hình biểu diễn thích hợp.

Ví dụ `nearlyEqual(0.1 + 0.2, 0.3, 1e-12, 1e-9)` cho `true` với các giá trị nhỏ này. Tuy nhiên, điều đó không chứng minh mọi số gần nhau đều tương đương về nghiệp vụ. Với tiền, mã định danh, số lượng chính xác hoặc điều kiện an toàn, tolerance có thể không phù hợp.

### Kiểm thử sai số cần so sánh với điều gì?

Nếu không có lời giải toán học chính xác, có thể sử dụng:

- Bộ dữ liệu có đáp án được suy ra độc lập và đáng tin cậy.
- Tính toán tham chiếu bằng `BigDecimal` hoặc phần mềm số chính xác cao khi mô hình toán học tương thích.
- Kiểm tra tính chất bất biến và miền kết quả của thuật toán.
- Thử nhiều thứ tự cộng, dữ liệu cực lớn/cực nhỏ, số gần triệt tiêu và các trường hợp ở sát số 0.

`BigDecimal` không tự giải quyết sai số cắt cụt thuật toán hoặc sai số đo từ đầu vào. Nếu tạo bằng `new BigDecimal(0.1)`, nó sẽ giữ **giá trị binary64 đã xấp xỉ**, khác với `new BigDecimal("0.1")`.

## 12. Những tình huống khiến sai số tích lũy thành vấn đề lớn

### 12.1. Tổng giá trị khác nhau rất nhiều về độ lớn

Ví dụ dãy `[1e16, 1, 1, -1e16]` có tổng chính xác bằng 2. Nhưng cộng tuần tự đơn giản có thể làm mất hai số 1 và trả về 0. Sắp xếp/gộp có chủ đích hoặc cộng bù có thể cải thiện một số trường hợp, nhưng cần đánh giá theo loại dãy số thực tế.

### 12.2. Vòng lặp cộng bước thời gian

Đo thời gian bằng `time += delta` trong rất nhiều bước có thể dẫn đến giá trị cuối khác `steps * delta` do sai số tích lũy. Nếu `delta` cố định, có thể tính từ chỉ số bước nguyên: `time = stepIndex * delta` khi phù hợp, nhằm tránh một chuỗi cộng dồn dài. Phép nhân vẫn làm tròn, nên phải kiểm tra kết quả với sai số cho phép.

### 12.3. Tích và chia qua nhiều bước

Sai số của nhân/chia có thể tích lũy theo hệ số tương đối. Tích của nhiều số lớn/nhỏ có thể overflow hoặc underflow trước khi ra kết quả mong muốn. Với bài toán như xác suất rất nhỏ, có thể dùng miền logarithm hoặc thuật toán chuẩn hóa để giảm các giá trị trung gian ngoài miền biểu diễn.

### 12.4. Sai số lan truyền trong thuật toán lặp

Một thuật toán như cập nhật vị trí `position += velocity * dt` tích lũy sai số từ dữ liệu đầu vào, phép nhân, phép cộng và số bước. Nếu thuật toán còn có **tính nhạy với điều kiện ban đầu**, sai số nhỏ có thể lớn nhanh theo thời gian. Khi đó chỉ dùng kiểu `double` chưa chắc giải quyết được; cần phân tích mô hình, bước tính, điều kiện ổn định và quy tắc dừng.

## 13. Forward error, backward error và điều kiện bài toán

Ba khái niệm giúp phân tích kỹ hơn:

- **Forward error:** độ lệch giữa kết quả tính \(\hat{y}\) và kết quả lý tưởng \(f(x)\) của *cùng đầu vào chuẩn* \(x\).
- **Backward error:** tìm xem \(\hat{y}\) có thể được hiểu là kết quả đúng \(f(x+\Delta x)\) của một đầu vào được nhiễu rất nhỏ hay không.
- **Conditioning:** bản thân bài toán nhạy tới mức nào trước thay đổi nhỏ của đầu vào. Đây là thuộc tính của bài toán, khác với tính ổn định của cách cài đặt thuật toán.

Một thuật toán được gọi là **backward stable** trong điều kiện phân tích thích hợp khi kết quả của nó tương đương nghiệm đúng của một đầu vào gần đầu vào ban đầu. Tuy nhiên, nếu bài toán *ill-conditioned*, sai số đầu vào nhỏ vẫn có thể làm thay đổi kết quả rất lớn. Vì vậy “thuật toán ổn định” không đồng nghĩa “sai số tương đối đầu ra luôn nhỏ”.

Ví dụ khi trừ hai số gần bằng nhau, kết quả thực nhỏ hơn nhiều so với cả hai toán hạng. Sai số tương đối của hai số đầu vào có thể bị phóng đại trong hiệu của chúng. Nếu hiểu điều kiện bài toán, ta sẽ tránh kỳ vọng không thực tế rằng chỉ thay `float` bằng `double` là có thể giữ đủ mọi chữ số có nghĩa.

## 14. Các biện pháp giảm sai số và lựa chọn kiểu dữ liệu

| Biện pháp | Phù hợp khi | Lưu ý |
| --- | --- | --- |
| `double` thay cho `float` | Cần thêm độ chính xác và miền số | `double` vẫn làm tròn |
| Cộng bù Kahan hoặc pairwise summation | Tổng nhiều số floating point | Đo hiệu quả trên tập dữ liệu đại diện |
| Đổi thứ tự hoặc biến đổi công thức ổn định | Có nguy cơ mất chữ số/cancellation | Phải bảo toàn ý nghĩa toán học và xử lý trường hợp biên |
| `Math.fma(a, b, c)` | Tính \(a\times b+c\) cần một lần làm tròn | Không giải quyết mọi sai số hoặc mất dữ liệu đầu vào |
| `Math.hypot(x, y)` | Tính \(\sqrt{x^2+y^2}\) | Giảm overflow/underflow trung gian |
| `BigDecimal` với chuỗi thập phân | Tiền và phép tính thập phân cần chính xác | Chia có thể cần `MathContext`/quy tắc làm tròn |
| Giá trị tham chiếu có độ chính xác cao | Kiểm thử giới hạn sai số thuật toán | Chọn tham chiếu độc lập và đúng miền toán học |
| Absolute + relative tolerance | So sánh kết quả tính xấp xỉ | Quy định ngưỡng theo nghiệp vụ |

### Trường hợp cần ưu tiên số chính xác

Với số nguyên đếm được trong miền `long`, dùng `long` để tránh sai số làm tròn của `double`. Với số nguyên vượt 64 bit, dùng `BigInteger`. Với số tiền cần chính xác theo thập phân, dùng `BigDecimal` hoặc số nguyên đơn vị nhỏ nhất theo quy tắc nghiệp vụ.

Thêm nhiều chữ số sau dấu phẩy trong biểu diễn text **không làm tăng độ chính xác** của giá trị `double` vốn đã được tính.

## 15. Lỗi phổ biến

1. **So sánh `double` bằng `==` trong mọi hoàn cảnh.** Khi phép tính có làm tròn, so sánh xấp xỉ cần ngưỡng và điều kiện bài toán.
2. **Dùng `Double.MIN_VALUE` làm epsilon.** Đây là số subnormal dương nhỏ nhất, không phải sai số tương đối điển hình hay độ phân giải quanh 1.0.
3. **Gọi `Math.ulp(1.0)` là giới hạn sai số cho mọi số.** ULP phụ thuộc độ lớn số đang xét và mô hình tính.
4. **Tính sai số tương đối khi tham chiếu bằng 0.** Công thức không xác định; cần chỉ tiêu phù hợp.
5. **Cho rằng sai số luôn tăng đơn điệu sau mỗi phép tính.** Sai số có thể cộng hoặc triệt tiêu; chỉ cận sai số và đặc tính thuật toán cho dự đoán đáng tin.
6. **Tin `BigDecimal.valueOf(double)` hoặc `new BigDecimal(double)` phục hồi số đo/chuỗi đã mất chính xác.** Chúng tạo từ một `double` đã làm tròn; muốn giữ đúng số thập phân văn bản thì parse trực tiếp từ chuỗi.
7. **Chỉ kiểm tra dữ liệu dễ như toàn số nguyên nhỏ.** Cần thử gần 0, hiệu hai số gần nhau, quy mô khác nhau, tổng dài, giá trị biên và thứ tự gộp khác nhau.
8. **Đọc sai số in từ `System.out.println` như toàn bộ sai số thật.** Cách định dạng và round-trip của `Double.toString` không cung cấp chứng minh về cận sai số của thuật toán.
9. **Bỏ qua `NaN` và `Infinity`.** Các giá trị đặc biệt có thể khiến so sánh/ngưỡng không còn ý nghĩa; cần chính sách kiểm tra đầu vào và kết quả.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Kết quả 198 so với tham chiếu 200 có sai số tuyệt đối, tương đối và phần trăm là bao nhiêu?

Đáp án: \(E_{\mathrm{abs}}=2\), \(E_{\mathrm{rel}}=2/200=0{,}01\), tức **1%**.

**Câu 2.** Nếu giá trị tham chiếu bằng 0, tại sao không thể nói sai số tương đối bằng 0%?

Đáp án: Vì mẫu số trong \(|\hat{x}-x|/|x|\) bằng 0; công thức không xác định. Có thể dùng sai số tuyệt đối hoặc một thước đo thay thế được định nghĩa rõ.

**Câu 3.** Vì sao phép cộng mười lần `0.1` có thể khác phép nhân `10 * 0.1`?

Đáp án: Hai biểu thức có số lượng và trình tự làm tròn khác nhau. Từng phép cộng có thể tích lũy sai số; phép nhân chỉ có một phép toán arithmetic sau khi các toán hạng đã được biểu diễn.

**Câu 4.** Tại sao `(1e16 + 1.0) - 1e16` có thể bằng 0 nhưng `(1e16 - 1e16) + 1.0` bằng 1?

Đáp án: `1e16 + 1` không tăng giá trị binary64 tại độ lớn này, nên phép trừ cuối mất thông tin. Thứ tự trừ trước giữ lại số 1.

**Câu 5.** Có phải Kahan luôn cho tổng chính xác như `BigDecimal` không?

Đáp án: Không. Kahan giảm một số sai số làm tròn trong tổng floating point nhưng vẫn dùng `double` và không thay thế số học thập phân chính xác hay giải quyết mọi trường hợp.

**Câu 6.** Nếu sai số tuyệt đối của hai lời giải nhỏ nhưng sai số tương đối rất lớn, thường cần kiểm tra điều gì?

Đáp án: Giá trị tham chiếu có thể rất gần 0; kiểm tra thang đo, tiêu chí sai số, khả năng cancellation và tính nhạy của bài toán.

## 17. Ghi nhớ và tài liệu tham khảo

- **Sai số tuyệt đối:** \(E_{\mathrm{abs}}=|\hat{x}-x|\), có đơn vị như đại lượng.
- **Sai số tương đối:** \(E_{\mathrm{rel}}=E_{\mathrm{abs}}/|x|\) khi \(x\ne0\), thích hợp so sánh giữa các thang đo; gần 0 phải thận trọng.
- **Tích lũy sai số:** mỗi lần làm tròn có thể ảnh hưởng bước sau; thứ tự phép tính và conditioning của bài toán quyết định độ tin cậy kết quả.
- **Giảm sai số:** chọn thuật toán ổn định, Kahan/pairwise summation khi cộng dài, dùng `Math.fma`/công thức số ổn định khi phù hợp, kiểm thử bằng tham chiếu đáng tin và xác định dung sai theo nghiệp vụ.
- **Lựa chọn kiểu:** `double` phù hợp nhiều bài toán số học xấp xỉ; `BigDecimal`/số nguyên phù hợp khi cần kết quả thập phân hoặc số đếm chính xác.

Nguồn tra cứu chính thức:

- [Java Language Specification 17 — Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3).
- [Java SE 17 API — Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `ulp`, `fma`, `hypot`.
- [Java SE 17 API — Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): giới hạn và biểu diễn binary64.
- [Java SE 17 API — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): số thập phân chính xác và kiểm soát làm tròn.
