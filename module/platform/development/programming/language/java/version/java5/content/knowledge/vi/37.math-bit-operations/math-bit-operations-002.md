# Math.sinh, cosh và tanh

## 1. Ba hàm hyperbolic dùng để làm gì?

`Math.sinh`, `Math.cosh` và `Math.tanh` tính các hàm hyperbolic, thường được gọi là hàm sin hyperbolic, cos hyperbolic và tang hyperbolic. Chúng liên hệ với hàm mũ, khác với các hàm lượng giác `sin`, `cos`, `tan` của đường tròn.

Có thể bắt đầu bằng ba đặc điểm:

- `sinh(x)` đi qua 0, nhận cả giá trị âm và dương, tăng nhanh khi độ lớn của x tăng.
- `cosh(x)` đối xứng qua trục tung, đạt giá trị nhỏ nhất 1 tại x = 0.
- `tanh(x)` tạo đường cong chữ S đi qua 0, tiến gần -1 và 1 khi x đi xa về hai phía.

Chúng hữu ích khi công thức của bài toán có dạng tăng trưởng theo hàm mũ, hình dạng dây treo lý tưởng, hoặc phép biến đổi trơn có đầu ra bị giới hạn như `tanh`. Không cần tự ghép các lệnh `exp` để tính chúng trong mã ứng dụng.

Java cung cấp trực tiếp:

```java
double s = Math.sinh(x);
double c = Math.cosh(x);
double t = Math.tanh(x);
```

Đây là các phương thức `static`, nhận và trả về `double`. `Math` nằm trong `java.lang`, được import tự động. Chúng vẫn là API hiện hành; ví dụ trong bài tương thích Java 17+.

## 2. Công thức và ý nghĩa hình học

Với e là cơ số của logarit tự nhiên:

```text
sinh(x) = (e^x - e^(-x)) / 2
cosh(x) = (e^x + e^(-x)) / 2
tanh(x) = sinh(x) / cosh(x)
        = (e^x - e^(-x)) / (e^x + e^(-x))
```

Từ công thức có thể thấy:

```text
sinh(0) = 0
cosh(0) = 1
tanh(0) = 0
```

Liên hệ hình học giúp phân biệt với lượng giác thông thường:

```text
cos²(x) + sin²(x) = 1        → đường tròn đơn vị
cosh²(x) - sinh²(x) = 1      → hyperbol đơn vị
```

Điểm có tọa độ `(cosh(x), sinh(x))` nằm trên nhánh phải của hyperbol trong toán học chính xác. Tham số x không phải một góc độ thông thường cần đổi bằng `Math.toRadians`.

Đầu vào của các hàm mũ trong định nghĩa là một tham số không thứ nguyên. Nếu bài toán vật lý có đại lượng mang đơn vị, công thức thường chuẩn hóa chúng thành tỷ số, chẳng hạn x/a với x và a cùng đơn vị. Đừng tự chuyển độ sang radian chỉ vì tên hàm có chữ sin/cos/tan.

Các công thức trên giải thích ý nghĩa toán học; chúng không phải hướng dẫn thay phương thức thư viện bằng đúng biểu thức `Math.exp` đó trên toàn miền `double`.

## 3. Đọc tính chất để dự đoán kết quả

| Tính chất | sinh | cosh | tanh |
| --- | --- | --- | --- |
| Giá trị tại 0 | 0 | 1 | 0 |
| Đối xứng | Hàm lẻ | Hàm chẵn | Hàm lẻ |
| Quan hệ dấu | Cùng dấu với x | Dương | Cùng dấu với x |
| Giới hạn trong toán học | Không bị chặn | Không bị chặn phía trên | Nằm giữa -1 và 1 |
| Khi x dương rất lớn | Gần e^x/2 | Gần e^x/2 | Tiến gần 1 |

“Hàm lẻ” nghĩa là `sinh(-x) = -sinh(x)` và `tanh(-x) = -tanh(x)`. “Hàm chẵn” nghĩa là `cosh(-x) = cosh(x)`.

Một vài giá trị gần đúng:

| x | sinh(x) | cosh(x) | tanh(x) |
| ---: | ---: | ---: | ---: |
| -2 | -3.626860 | 3.762196 | -0.964028 |
| -1 | -1.175201 | 1.543081 | -0.761594 |
| 0 | 0.000000 | 1.000000 | 0.000000 |
| 1 | 1.175201 | 1.543081 | 0.761594 |
| 2 | 3.626860 | 3.762196 | 0.964028 |

Không nên suy ra `sinh` hoặc `cosh` cũng bị chặn bởi 1 chỉ vì tên gần với `sin` và `cos`.

Với x rất gần 0, có các xấp xỉ:

```text
sinh(x) ≈ x
cosh(x) ≈ 1 + x²/2
tanh(x) ≈ x
```

Đây là các xấp xỉ cục bộ, không thay thế công thức cho x lớn. Do làm tròn `double`, `cosh` có thể trả đúng 1.0 với một số đầu vào rất nhỏ dù giá trị toán học lớn hơn 1 một lượng rất nhỏ.

## 4. Tanh là phép biến đổi trơn, không phải clamp

Trong toán học, với mọi x hữu hạn:

```text
-1 < tanh(x) < 1
```

`tanh` không giữ nguyên các giá trị đã nằm trong [-1, 1]. Chẳng hạn `tanh(0.5)` gần 0.462117, không phải 0.5.

Phép kẹp khoảng như `Math.max(-1.0, Math.min(1.0, x))` có ý nghĩa khác: giữ nguyên phần giữa và cắt cụt phần ngoài. `tanh` thay đổi liên tục, trơn và tăng dần trên toàn trục số.

Có thể điều chỉnh mức bão hòa bằng một hệ số:

```java
double output = Math.tanh(gain * input);
```

Đoạn này nằm trong một phương thức, với `gain` và `input` đã được khai báo. Khi `gain` dương và tăng, đường cong tiến gần hai đầu -1/1 nhanh hơn. Giá trị âm của gain đổi chiều; gain bằng 0 làm mọi đầu vào hữu hạn cho kết quả 0.

Trong phép tính `double`, kết quả có thể được làm tròn thành đúng `1.0` hoặc `-1.0` ngay cả khi x hữu hạn. Đây là giới hạn biểu diễn của kết quả gần đúng, không mâu thuẫn với bất đẳng thức nghiêm ngặt của hàm toán học.

Nếu dùng `tanh` trong một công thức cần độ thay đổi nhỏ ở vùng bão hòa, phải lưu ý rằng các đầu vào khác nhau có thể cùng trả về 1.0. Không thể lấy lại khác biệt đó từ kết quả đã bão hòa.

## 5. Giá trị đặc biệt của double

| Đầu vào | Math.sinh | Math.cosh | Math.tanh |
| --- | --- | --- | --- |
| `+0.0` | `+0.0` | `1.0` | `+0.0` |
| `-0.0` | `-0.0` | `1.0` | `-0.0` |
| `Double.POSITIVE_INFINITY` | `+Infinity` | `+Infinity` | `1.0` |
| `Double.NEGATIVE_INFINITY` | `-Infinity` | `+Infinity` | `-1.0` |
| `Double.NaN` | NaN | NaN | NaN |

Java `double` có cả số 0 dương và số 0 âm. Chúng bằng nhau dưới toán tử `==`, nhưng vẫn có thể phân biệt bằng bit hoặc trong phép chia nghịch đảo. `sinh` và `tanh` giữ dấu của đầu vào 0; `cosh` trả 1.0 cho cả hai.

Không kiểm tra NaN bằng `value == Double.NaN`; dùng `Double.isNaN(value)`. Để phát hiện kết quả hữu hạn, dùng `Double.isFinite(value)`.

Các trường hợp đặc biệt và giới hạn sai số được quy định trong [Math API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html#sinh(double)). Kết quả của ba hàm được yêu cầu nằm trong 2.5 ulp so với kết quả chính xác; ulp là đơn vị gắn với khoảng cách giữa các số dấu phẩy động tại độ lớn đang xét.

## 6. Vì sao không tự viết bằng exp một cách trực tiếp?

### 6.1. Trừ hai số gần bằng nhau làm mất chữ số có nghĩa

Với x rất nhỏ, `Math.exp(x)` và `Math.exp(-x)` đều rất gần 1. Khi chúng bị làm tròn thành cùng một giá trị, phép trừ cho 0:

```java
double x = 1e-20;
double naive = (Math.exp(x) - Math.exp(-x)) / 2.0;
double direct = Math.sinh(x);
```

Trong ví dụ này, `naive` bằng 0.0 nhưng `direct` gần 1e-20. Công thức toán học đúng không bảo đảm một cách tính bằng `double` ổn định trên mọi đầu vào.

### 6.2. Giá trị trung gian có thể tràn trước kết quả cuối

`Math.exp(710.0)` tràn thành Infinity. Nhưng `sinh(710.0)`, gần `e^710 / 2`, vẫn còn nằm trong miền hữu hạn của `double`. Nếu tính exp trước rồi chia 2, thông tin đã mất vì Infinity chia 2 vẫn là Infinity.

Hàm thư viện có thể xử lý các khoảng đầu vào bằng cách phù hợp hơn, thay vì tạo ra trung gian đó một cách trực tiếp.

### 6.3. Tanh không nên tính bằng sinh/cosh với đối số rất lớn

Với x = 1000, cả `sinh(x)` và `cosh(x)` đều tràn. Vì thế:

```java
double ratio = Math.sinh(1000.0) / Math.cosh(1000.0);
// Infinity / Infinity → NaN.

double direct = Math.tanh(1000.0);
// 1.0.
```

Tỷ số toán học có giới hạn rõ ràng, nhưng hai số gần đúng trung gian không còn chứa đủ thông tin. Gọi đúng hàm `Math.tanh` tránh phải tính một tỷ số đã tràn.

Tràn số dấu phẩy động thường tạo Infinity hoặc NaN; ba phương thức này không dùng `ArithmeticException` để báo mọi đầu vào quá lớn.

## 7. Chương trình hoàn chỉnh

Lưu thành `HyperbolicDemo.java`. Chương trình in các giá trị thông thường với sáu chữ số thập phân để dễ đọc, đồng thời kiểm tra các trường hợp đặc biệt bằng boolean.

```java
import java.util.Locale;

public class HyperbolicDemo {
    private static void row(double x) {
        System.out.printf(Locale.ROOT, "%.1f | %.6f | %.6f | %.6f%n",
                x, Math.sinh(x), Math.cosh(x), Math.tanh(x));
    }

    private static boolean close(double a, double b) {
        return Double.isFinite(a) && Double.isFinite(b)
                && Math.abs(a - b) <= 1e-12;
    }

    public static void main(String[] args) {
        System.out.println("x | sinh | cosh | tanh");
        for (double x : new double[] {-2.0, -1.0, 0.0, 1.0, 2.0}) {
            row(x);
        }

        double s = Math.sinh(1.0);
        double c = Math.cosh(1.0);
        System.out.println("hyperbolaIdentity=" + close(c * c - s * s, 1.0));
        System.out.println("sinhOdd=" + close(Math.sinh(-1.0), -s));
        System.out.println("coshEven=" + close(Math.cosh(-1.0), c));

        double tiny = 1e-20;
        double naiveSinh = (Math.exp(tiny) - Math.exp(-tiny)) / 2.0;
        System.out.println("naiveTinySinhIsZero=" + (naiveSinh == 0.0));
        System.out.println("directTinySinhNonzero=" + (Math.sinh(tiny) != 0.0));

        System.out.println("exp710Infinite=" + Double.isInfinite(Math.exp(710.0)));
        System.out.println("sinh710Finite=" + Double.isFinite(Math.sinh(710.0)));

        double ratio = Math.sinh(1000.0) / Math.cosh(1000.0);
        System.out.println("largeRatioNaN=" + Double.isNaN(ratio));
        System.out.println("tanh1000=" + Math.tanh(1000.0));
        System.out.println("tanhMinus1000=" + Math.tanh(-1000.0));

        System.out.println("sinhNegativeZero=" + Math.sinh(-0.0));
        System.out.println("coshNegativeZero=" + Math.cosh(-0.0));
        System.out.println("tanhNegativeZero=" + Math.tanh(-0.0));
        System.out.println("sinhNegativeInfinity="
                + Math.sinh(Double.NEGATIVE_INFINITY));
        System.out.println("coshNegativeInfinity="
                + Math.cosh(Double.NEGATIVE_INFINITY));
        System.out.println("tanhPositiveInfinity="
                + Math.tanh(Double.POSITIVE_INFINITY));
        System.out.println("sinhNaN=" + Double.isNaN(Math.sinh(Double.NaN)));
        System.out.println("coshNaN=" + Double.isNaN(Math.cosh(Double.NaN)));
        System.out.println("tanhNaN=" + Double.isNaN(Math.tanh(Double.NaN)));

        double a = 2.0;
        double horizontal = 2.0;
        double height = a * Math.cosh(horizontal / a);
        System.out.printf(Locale.ROOT, "catenaryHeight=%.6f%n", height);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 HyperbolicDemo.java
java HyperbolicDemo
```

Stdout:

```text
x | sinh | cosh | tanh
-2.0 | -3.626860 | 3.762196 | -0.964028
-1.0 | -1.175201 | 1.543081 | -0.761594
0.0 | 0.000000 | 1.000000 | 0.000000
1.0 | 1.175201 | 1.543081 | 0.761594
2.0 | 3.626860 | 3.762196 | 0.964028
hyperbolaIdentity=true
sinhOdd=true
coshEven=true
naiveTinySinhIsZero=true
directTinySinhNonzero=true
exp710Infinite=true
sinh710Finite=true
largeRatioNaN=true
tanh1000=1.0
tanhMinus1000=-1.0
sinhNegativeZero=-0.0
coshNegativeZero=1.0
tanhNegativeZero=-0.0
sinhNegativeInfinity=-Infinity
coshNegativeInfinity=Infinity
tanhPositiveInfinity=1.0
sinhNaN=true
coshNaN=true
tanhNaN=true
catenaryHeight=3.086161
```

`Locale.ROOT` giữ dấu chấm trong phần số thập phân, tránh stdout thay đổi theo thiết lập ngôn ngữ của máy. Sáu chữ số được in là định dạng hiển thị, không có nghĩa các phép tính chỉ dùng sáu chữ số.

Hàm `close` dùng dung sai tuyệt đối 1e-12 cho các giá trị nhỏ đã chọn trong ví dụ; không phải một hàm so sánh tổng quát cho mọi độ lớn. Nó từ chối NaN và Infinity trước khi kiểm tra hiệu.

Dòng cuối minh họa công thức đường dây treo lý tưởng `y = a × cosh(x/a)`, với a dương. Khi a = 2 và x = 2, y gần 3.086161; tại x = 0 thì y = a. Đây là minh họa cách dùng hàm trong công thức, không phải chương trình tính toàn bộ một hệ dây treo thực tế.

## 8. Độ chính xác và cách kiểm tra hợp lý

Các đẳng thức toán học không nhất thiết đúng từng bit sau nhiều phép toán `double`. Ví dụ `cosh(x)² - sinh(x)² = 1` có thể sai lệch do làm tròn. Khi x lớn, còn có nguy cơ:

- Hai bình phương rất lớn làm phép trừ mất thông tin tương đối.
- Bình phương tràn dù bản thân sinh/cosh còn hữu hạn.
- Infinity trừ Infinity thành NaN.

Vì vậy đừng dùng đẳng thức này làm kiểm thử chính xác bằng `==` trên toàn miền đầu vào. Hãy chọn miền vừa phải khi kiểm tra tính chất và chọn dung sai phù hợp với bài toán.

`Math` cho phép một số khác biệt ở các bit cuối giữa những cách triển khai, miễn đáp ứng hợp đồng độ chính xác. Nếu yêu cầu tái lập theo đặc tả các hàm của `StrictMath`, hãy xem các phương thức tương ứng `StrictMath.sinh`, `StrictMath.cosh`, `StrictMath.tanh`. Dù dùng `StrictMath`, phép tính vẫn là gần đúng, vẫn có NaN/Infinity và không có nghĩa mọi đẳng thức toán học trở thành chính xác.

Không bọc kết quả `double` vào `BigDecimal` rồi cho rằng đã có sinh/cosh/tanh với độ chính xác thập phân tùy ý. Phần thông tin bị mất trước đó không được khôi phục bằng việc đổi kiểu chứa.

## 9. Lỗi thường gặp

- Nhầm `sinh` với `sin`: một hàm tăng nhanh theo hàm mũ, một hàm dao động tuần hoàn.
- Gọi `Math.toRadians` theo thói quen dù công thức không có góc đo bằng độ.
- Hiểu `tanh` là hàm nghịch đảo của tan hoặc là 1/tan; đây là hàm hyperbolic riêng.
- Tự ghép exp rồi gặp triệt tiêu gần 0 hoặc tràn ở giá trị lớn.
- Tính `tanh` bằng tỷ số hai hàm đã tràn.
- Cho rằng kết quả của `tanh` luôn khác ±1 trong `double`, vì hàm toán học có giới hạn mở.
- Dùng `== Double.NaN` hoặc đợi ngoại lệ để phát hiện mọi lỗi số học.
- Dùng một dung sai cố định cho mọi dữ liệu mà không xét độ lớn và yêu cầu sai số.

## 10. Thực hành

1. Dự đoán dấu của sinh, cosh và tanh tại x = -3 trước khi chạy. Hàm nào giữ nguyên kết quả khi đổi x thành -x?
2. Tạo bảng cho x = -0.5, 0, 0.5. So sánh tanh(x) với x và giải thích vì sao đây không phải phép kẹp khoảng.
3. Thay x rất nhỏ trong công thức sinh tự ghép bằng 1e-8, 1e-12 và 1e-20. So sánh sai số với `Math.sinh`; đừng chỉ in ít chữ số đến mức che mất khác biệt.
4. Tìm một giá trị hữu hạn khiến `Math.tanh(x)` trả đúng 1.0 trên JDK đang dùng. Vì sao không nên xem đó là một ngưỡng toán học chung?
5. Kiểm tra `Math.cosh(Double.NEGATIVE_INFINITY)` và `Math.tanh(Double.NEGATIVE_INFINITY)`. Giải thích sự khác nhau bằng tính chẵn/lẻ và giới hạn.
6. Với công thức `y = a × cosh(x/a)`, kiểm tra a > 0 và quan hệ y(-x) = y(x) trong một miền hữu hạn vừa phải. Nếu cần tính độ cao so với điểm thấp nhất, hãy giải thích vì sao phải trừ a.

Khi đánh giá kết quả, phân biệt giá trị toán học, kết quả gần đúng `double` và số chữ số đang được in ra. Ba lớp này trả lời những câu hỏi khác nhau.
