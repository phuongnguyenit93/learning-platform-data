# Math.expm1 và log1p cho giá trị gần không

## 1. Cùng công thức toán học, nhưng khác độ ổn định khi tính

Hai phương thức sau được thiết kế cho những biểu thức dễ mất thông tin khi đầu vào gần 0:

| Phương thức | Giá trị toán học cần tính |
| --- | --- |
| `Math.expm1(x)` | `e^x - 1` |
| `Math.log1p(x)` | `ln(1 + x)`, logarit tự nhiên |

Các tên có thể đọc là “exp minus one” và “log one plus”. `log1p` không phải logarit cơ số 10 và không phải `log(x) + 1`.

Cả hai nhận `double`, trả `double`, là phương thức `static` của `java.lang.Math`. API có từ Java 5 và vẫn phù hợp với Java hiện nay.

Về số thực, `expm1(x)` và `exp(x) - 1` biểu diễn cùng công thức. Nhưng khi tính bằng `double`, từng phép tính trung gian đều có thể làm tròn, nên không thể mặc định hai cách viết giữ được cùng độ chính xác.

## 2. Vì sao exp(x) - 1 mất thông tin?

Khi x rất nhỏ, ta có gần đúng:

```text
e^x = 1 + x + x^2/2 + ...
e^x - 1 ≈ x
```

Giá trị `e^x` nằm rất gần 1. Nếu tính `Math.exp(x)` trước, kết quả ấy có thể bị làm tròn thành đúng `1.0`. Trừ tiếp `1.0` chỉ còn 0, mặc dù kết quả toán học là một số nhỏ khác 0.

Ngay cả khi chưa bị làm tròn thành đúng 1, trừ hai số rất gần nhau cũng có thể làm phần sai số của giá trị trung gian trở nên lớn so với hiệu nhỏ cần tính. Đây là mất chữ số có nghĩa do phép trừ gần nhau, thường gọi là triệt tiêu số học (`cancellation`).

`Math.expm1(x)` tính trực tiếp biểu thức `e^x - 1` theo hợp đồng độ chính xác của hàm, tránh buộc chương trình phải lưu `e^x` đã làm tròn rồi mới trừ 1.

Ví dụ với `x = 1e-16` trên môi trường chạy chương trình bên dưới:

```text
Math.exp(x) - 1.0 -> 0.0
Math.expm1(x)     -> xấp xỉ 1e-16
```

Không cần tự viết một khai triển Taylor cắt ngắn để thay API. Khai triển phía trên dùng để hiểu nguyên nhân; nó không mô tả đầy đủ thuật toán bên trong thư viện.

## 3. Vì sao log(1 + x) mất thông tin?

Khi x gần 0:

```text
ln(1 + x) = x - x^2/2 + x^3/3 - ...
ln(1 + x) ≈ x
```

Vấn đề xảy ra ngay ở phép cộng `1.0 + x`. Khoảng cách giữa các số `double` quanh 1 lớn hơn khoảng cách quanh một số rất nhỏ. Với `x = 1e-16`, phép cộng làm tròn thành đúng 1:

```java
double x = 1e-16;
boolean incrementLost = (1.0 + x == 1.0); // true
double direct = Math.log(1.0 + x);        // 0.0
double stable = Math.log1p(x);            // xap xi 1e-16
```

`Math.log1p` nhận **phần tăng x**, nên không cần người gọi thực hiện phép cộng dễ mất thông tin trước.

Điều này cũng chỉ ra giới hạn: nếu đã lưu `y = 1.0 + x` và y bị làm tròn thành 1, gọi `Math.log1p(y - 1.0)` không thể phục hồi x. Hãy giữ phần tăng gốc và truyền trực tiếp nó cho `log1p`.

## 4. Miền xác định và các giá trị đặc biệt

### expm1

`e^x - 1` có nghĩa với mọi x thực. Với dữ liệu `double`:

| Đầu vào | Kết quả |
| --- | --- |
| `+0.0` hoặc `-0.0` | Số 0 cùng dấu |
| `Double.NEGATIVE_INFINITY` | `-1.0` |
| `Double.POSITIVE_INFINITY` | `Double.POSITIVE_INFINITY` |
| `NaN` | `NaN` |

Với x hữu hạn rất âm, kết quả có thể được làm tròn thành `-1.0`. Với x dương quá lớn, kết quả có thể tràn thành dương vô cực. Hàm ổn định hơn gần 0 không có nghĩa là loại bỏ mọi giới hạn của `double`.

### log1p

Để có logarit thực hữu hạn, cần `1 + x > 0`, tức `x > -1`.

| Đầu vào | Kết quả |
| --- | --- |
| Hữu hạn, lớn hơn -1 | Logarit hữu hạn |
| `-1.0` | `Double.NEGATIVE_INFINITY` |
| Nhỏ hơn -1, kể cả âm vô cực | `NaN` |
| `+0.0` hoặc `-0.0` | Số 0 cùng dấu |
| Dương vô cực | Dương vô cực |
| `NaN` | `NaN` |

Ví dụ `Math.log1p(-0.5)` hợp lệ vì nó tính `ln(0.5)`. Hàm không ném ngoại lệ cho `log1p(-2)`; kết quả là `NaN`. Nếu ứng dụng chỉ chấp nhận đầu vào trong một miền cụ thể, hãy kiểm tra đầu vào và dùng `Double.isNaN`/`Double.isFinite` khi cần.

## 5. Ví dụ ghép hai hàm để giữ phần thay đổi nhỏ

Giả sử cần tính **mức thay đổi tương đối** sau n lần nhân với một hệ số `(1 + r)`:

```text
change = (1 + r)^n - 1
```

Nếu r cực nhỏ, tạo `1 + r` bằng `double` có thể mất r. Nếu kết quả lũy thừa lại gần 1, phép trừ cuối tiếp tục có nguy cơ mất thông tin.

Với `r > -1`, có thể viết theo công thức toán học:

```text
change = exp(n × ln(1 + r)) - 1
```

Và dùng API tương ứng:

```java
double change = Math.expm1(n * Math.log1p(r));
```

Ví dụ `r = 1e-18`, `n = 1_000_000`: cách `Math.pow(1.0 + r, n) - 1.0` cho 0 trong ví dụ, trong khi cách ghép hai hàm giữ được mức thay đổi xấp xỉ `1e-12`.

Đây là kỹ thuật ổn định biểu thức, không phải cam kết tính chính xác tuyệt đối cho mọi r và n. Vẫn phải xét miền dữ liệu, làm tròn của phép nhân và tràn số khi kết quả lớn. Nếu ứng dụng còn có quy tắc làm tròn thập phân riêng, hai hàm này không tự thực hiện quy tắc đó.

## 6. Chương trình chạy đầy đủ

Lưu thành `NearZeroMathDemo.java`. Ví dụ có thể biên dịch với Java 17 trở lên.

```java
import java.util.Locale;

public class NearZeroMathDemo {
    public static void main(String[] args) {
        double x = 1e-16;
        double directExp = Math.exp(x) - 1.0;
        double stableExp = Math.expm1(x);
        double directLog = Math.log(1.0 + x);
        double stableLog = Math.log1p(x);

        System.out.println("1 + x == 1 = " + (1.0 + x == 1.0));
        System.out.println("exp(x) - 1 = " + directExp);
        System.out.println("log(1 + x) = " + directLog);
        System.out.printf(Locale.ROOT, "expm1(x) = %.1e%n", stableExp);
        System.out.printf(Locale.ROOT, "log1p(x) = %.1e%n", stableLog);
        System.out.println("expm1 relative error below 1e-12 = "
                + (Math.abs(stableExp / x - 1.0) < 1e-12));
        System.out.println("log1p relative error below 1e-12 = "
                + (Math.abs(stableLog / x - 1.0) < 1e-12));

        double roundedOnePlusX = 1.0 + x;
        System.out.println("log1p after lost increment = "
                + Math.log1p(roundedOnePlusX - 1.0));

        System.out.println("expm1(-0.0) = " + Math.expm1(-0.0));
        System.out.println("expm1(-infinity) = "
                + Math.expm1(Double.NEGATIVE_INFINITY));
        System.out.println("log1p(-0.0) = " + Math.log1p(-0.0));
        System.out.println("log1p(-1) = " + Math.log1p(-1.0));
        System.out.println("log1p(-2) is NaN = "
                + Double.isNaN(Math.log1p(-2.0)));

        double rate = 1e-18;
        long steps = 1_000_000L;
        double naiveGrowth = Math.pow(1.0 + rate, steps) - 1.0;
        double stableGrowth = Math.expm1(steps * Math.log1p(rate));
        System.out.println("naive relative growth = " + naiveGrowth);
        System.out.printf(Locale.ROOT, "stable relative growth = %.1e%n", stableGrowth);
    }
}
```

Lệnh:

```shell
javac --release 17 -encoding UTF-8 NearZeroMathDemo.java
java NearZeroMathDemo
```

Stdout:

```text
1 + x == 1 = true
exp(x) - 1 = 0.0
log(1 + x) = 0.0
expm1(x) = 1.0e-16
log1p(x) = 1.0e-16
expm1 relative error below 1e-12 = true
log1p relative error below 1e-12 = true
log1p after lost increment = 0.0
expm1(-0.0) = -0.0
expm1(-infinity) = -1.0
log1p(-0.0) = -0.0
log1p(-1) = -Infinity
log1p(-2) is NaN = true
naive relative growth = 0.0
stable relative growth = 1.0e-12
```

`Locale.ROOT` giữ dấu chấm và cách định dạng số ổn định khi in. Định dạng `%.1e` chỉ hiển thị gọn kết quả; nó không thay đổi các giá trị `double` dùng trong phép kiểm tra.

Hai dòng có nhãn `relative error` so sánh với x, là xấp xỉ bậc một của hai hàm khi x rất nhỏ. Đây là kiểm tra hợp lý cho riêng dữ liệu thử đó, không phải phép đo sai số so với một giá trị tham chiếu chính xác tùy ý cho mọi x.

## 7. Độ chính xác cần hiểu đúng

Hợp đồng API yêu cầu kết quả của `expm1` và `log1p` nằm trong 1 ulp của kết quả chính xác và giữ tính đơn điệu theo quy định của hàm. Ulp gắn với khoảng cách của các giá trị dấu phẩy động ở độ lớn tương ứng, không phải một epsilon thập phân dùng chung.

Vì vậy:

- Không dùng `expm1(x) == Math.exp(x) - 1` làm tiêu chí xác nhận hai API “đúng”; sự khác biệt gần 0 chính là lý do dùng hàm chuyên biệt.
- Không mặc định `Math.log1p(Math.expm1(x)) == x` cho mọi x. Mỗi lời gọi đều có làm tròn; khi `expm1(x)` đã thành -1 hoặc vô cực, thông tin còn có thể mất hoàn toàn.
- Không kỳ vọng hàm phục hồi dữ liệu đầu vào đã bị mất trước lời gọi.
- Một số bit thấp có thể khác giữa các triển khai `Math` mà vẫn tuân theo hợp đồng; nếu cần tính tái lập chặt chẽ hơn, phải xem yêu cầu và API `StrictMath` tương ứng.

Với giá trị không gần 0, các hàm vẫn có định nghĩa và có thể dùng bình thường; không cần tự đặt một ngưỡng tùy ý rồi chia đôi mã thành hai công thức nếu chưa có nhu cầu được kiểm chứng.

## 8. Lỗi thường gặp và bài tập

Các lỗi cần tránh:

1. Truyền `1 + x` vào `log1p`: hàm đó sẽ tính `ln(2 + x)`, khác biểu thức mong muốn.
2. Viết `Math.expm1(x) - 1` khi muốn `e^x - 1`: đã trừ thêm một lần.
3. Cho rằng x âm luôn không hợp lệ với `log1p`: khoảng `-1 < x < 0` hoàn toàn hợp lệ.
4. Chỉ kiểm tra kết quả bằng `== Double.NaN`; hãy dùng `Double.isNaN`.
5. Dùng một hàm chính xác hơn ở cuối sau khi đã làm mất phần tăng trong phép cộng đầu.

Tự kiểm tra:

- Muốn tính `ln(1 + delta)` với delta rất nhỏ, nên truyền giá trị nào vào `Math.log1p`?
- `Math.log1p(-1.0)` trả gì?
- `Math.expm1(0.0)` bằng 0 hay 1?
- Nếu `y = 1.0 + delta` đã bằng 1, `Math.log1p(y - 1.0)` có khôi phục delta không?

Đáp án lần lượt: truyền trực tiếp `delta`; âm vô cực; `+0.0`; không thể phục hồi phần đã mất.

Tham khảo API hiện hành: [Math.expm1](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#expm1(double)) và [Math.log1p](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#log1p(double)) trong Java SE 21.
