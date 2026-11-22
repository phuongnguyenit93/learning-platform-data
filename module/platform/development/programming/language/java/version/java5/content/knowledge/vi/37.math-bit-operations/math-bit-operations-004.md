# Math.hypot và việc kiểm soát sai số trung gian

## 1. Cùng công thức toán học chưa chắc cùng hành vi tính toán

Độ dài của vectơ hai chiều `(x, y)` là:

```text
r = sqrt(x² + y²)
```

Một cách viết trực tiếp trong Java là:

```java
double r = Math.sqrt(x * x + y * y);
```

Nhưng máy tính phải tính từng bước: nhân `x` với chính nó, nhân `y` với chính nó, cộng hai kết quả rồi mới lấy căn. Những giá trị trung gian có thể vượt hoặc hụt dưới phạm vi của `double`, dù độ dài cuối cùng vẫn biểu diễn được.

`Math.hypot(x, y)` tính cùng đại lượng toán học, đồng thời tránh tràn số và hụt dưới trung gian trong phép tính này:

```java
double r = Math.hypot(x, y);
```

Hàm hữu ích khi tính độ dài vectơ, khoảng cách Euclid hai chiều, độ lớn của hai thành phần vuông góc hoặc độ lớn số phức. Nó không phải phép tính cạnh huyền chỉ dùng được khi đầu vào dương; dấu của hai thành phần không làm thay đổi độ dài.

## 2. Tràn số trung gian: kết quả chưa chắc quá lớn

Xét `x = y = 1e200`.

Theo số học thực:

```text
sqrt((10^200)² + (10^200)²)
= sqrt(2) × 10^200
≈ 1.4142 × 10^200
```

Độ lớn này vẫn nằm trong phạm vi hữu hạn của `double`. Nhưng mỗi bình phương có độ lớn `10^400`, vượt xa giới hạn khoảng `1.8 × 10^308`.

Khi viết công thức trực tiếp:

```text
x * x -> Infinity
y * y -> Infinity
Infinity + Infinity -> Infinity
sqrt(Infinity) -> Infinity
```

Phép lấy căn cuối không thể biết vô cực đó xuất phát từ những toán hạng hữu hạn nào để khôi phục thông tin đã mất.

Trong khi đó, `Math.hypot(1e200, 1e200)` trả một giá trị hữu hạn gần `sqrt(2) × 10^200`.

Đây là ví dụ **kết quả hữu hạn nhưng đường tính trực tiếp tạo trung gian vô cực**. Không nên kết luận mọi lần gặp `Infinity` đều có nghĩa đại lượng toán học cuối cùng quá lớn.

## 3. Hụt dưới trung gian: số khác 0 bị biến thành 0

Xét `x = y = 1e-200`.

Bình phương có độ lớn `10^-400`, quá nhỏ để được giữ dưới dạng một `double` khác 0. Vì thế:

```text
x * x -> 0.0
y * y -> 0.0
sqrt(0.0 + 0.0) -> 0.0
```

Nhưng kết quả toán học là khoảng `1.4142 × 10^-200`, hoàn toàn biểu diễn được dưới dạng hữu hạn khác 0.

`Math.hypot(1e-200, 1e-200)` giữ được độ lớn đó.

Cần phân biệt:

- **Tràn số (overflow):** độ lớn vượt miền hữu hạn, có thể thành vô cực trong phép toán dấu phẩy động.
- **Hụt dưới (underflow):** kết quả quá nhỏ, có thể mất độ chính xác hoặc thành 0.
- **Làm tròn thông thường:** kết quả vẫn nằm trong miền nhưng không khớp chính xác một giá trị nhị phân biểu diễn được.

`double` có các số rất nhỏ dưới chuẩn (subnormal), nhưng điều đó không có nghĩa biểu diễn được mọi giá trị dương nhỏ tùy ý.

## 4. Ý tưởng thay đổi thang đo

Có thể hiểu cách tránh bình phương trực tiếp bằng một phép biến đổi đại số. Với đầu vào hữu hạn, đặt:

```text
a = abs(x)
b = abs(y)
m = max(a, b)
n = min(a, b)
```

Nếu `m > 0`:

```text
sqrt(x² + y²)
= m × sqrt(1 + (n / m)²)
```

Vì `0 <= n/m <= 1`, phép tính bên trong căn không phải bình phương những giá trị rất lớn như `1e200`.

Ví dụ `x = y = 1e200` cho:

```text
m = 1e200
n / m = 1
kết quả = 1e200 × sqrt(2)
```

Với hai giá trị `1e-200`, phần bên trong căn cũng ở thang đo bình thường thay vì tạo hai bình phương bằng 0.

Đây là **mô hình giải thích ý tưởng điều chỉnh thang đo**, không phải mã nguồn cam kết của `Math.hypot`, cũng không phải chứng minh một cách viết giản lược tự tạo sẽ đáp ứng toàn bộ hợp đồng sai số của thư viện.

Nếu tự triển khai chỉ bằng công thức trên, còn phải xử lý:

- Hai đầu vào đều bằng 0 để tránh `0/0`.
- Vô cực và `NaN` theo đúng thứ tự.
- Các số dưới chuẩn.
- Những trường hợp gần ngưỡng làm tròn.
- Phần rất nhỏ so với phần lớn và sai số từng phép toán.
- Giới hạn sai số và tính đơn điệu theo hợp đồng API.

Vì vậy, để tính đại lượng này trong mã ứng dụng, dùng `Math.hypot` giúp tránh phải tự gánh toàn bộ những trường hợp đó.

## 5. Hàm ổn định hơn không có nghĩa chính xác tuyệt đối

Nhiều căn bậc hai không có biểu diễn nhị phân hữu hạn. Ví dụ `sqrt(2)` phải được xấp xỉ khi trả về một `double`.

Hợp đồng Java SE 25 của `Math.hypot` yêu cầu sai số trong 1,5 ulp so với kết quả chính xác; khi cố định một tham số, kết quả phải có tính bán đơn điệu theo tham số còn lại. Các trường hợp đặc biệt cũng được quy định rõ. Xem [Java API: Math.hypot](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html#hypot(double,double)).

Một ulp có thể hiểu là bước phân giải của kiểu dấu phẩy động tại một độ lớn đang xét. Bước này thay đổi theo độ lớn, nên không thể thay toàn bộ hợp đồng bằng một sai số tuyệt đối cố định như `0.000001`.

Không nên diễn giải bảo đảm trên thành:

- Kết quả luôn bằng giá trị thực với mọi chữ số.
- Hàm luôn làm tròn đúng về giá trị `double` gần nhất trong mọi trường hợp.
- Kết quả luôn bằng từng bit với cách viết `Math.sqrt(x*x + y*y)`.
- Mọi JDK/triển khai phải in cùng một chữ số cuối với mọi đầu vào.

Khi cần dựa vào một giới hạn sai số cụ thể, đối chiếu hợp đồng của JDK mục tiêu. Chương trình trong bài dùng các API có trên JDK 17 trở lên và chọn cách kiểm chứng không phụ thuộc chữ số cuối của các kết quả vô tỷ.

## 6. NaN, vô cực và số 0 có dấu

| Đầu vào | Kết quả của `Math.hypot` |
|---|---|
| Một tham số là vô cực, kể cả tham số còn lại là `NaN` | Dương vô cực |
| Có `NaN`, không có tham số vô cực | `NaN` |
| Cả hai bằng 0, kể cả âm 0 | Dương 0 |
| `-3.0` và `4.0` | `5.0` |
| Hai giá trị hữu hạn nhưng độ dài cuối vượt miền biểu diễn | Có thể dương vô cực |

Đáng chú ý: `Math.hypot(Infinity, NaN)` cho `Infinity`. Nếu một hàm tự viết kiểm tra `NaN` trước rồi trả ngay `NaN`, nó đã khác hợp đồng này.

Các biểu thức trực tiếp có thể khác:

```java
Math.sqrt(Double.POSITIVE_INFINITY * Double.POSITIVE_INFINITY
        + Double.NaN * Double.NaN); // NaN

Math.hypot(Double.POSITIVE_INFINITY, Double.NaN); // Infinity
```

Đây là các biểu thức minh họa, không phải chương trình độc lập.

Nếu miền dữ liệu ứng dụng yêu cầu tất cả tọa độ đều hữu hạn, hãy kiểm tra bằng `Double.isFinite` theo hợp đồng đầu vào. Đừng chỉ kiểm tra kết quả có phải `NaN` rồi suy ra không có `NaN` ở dữ liệu gốc; trường hợp kết hợp với vô cực cho thấy suy luận đó không đúng.

Về dấu số 0, `Math.hypot(-0.0, -0.0)` trả `+0.0`. So sánh `==` không phân biệt hai dấu 0; chương trình phía dưới dùng các bit để kiểm chứng dấu dương.

## 7. Giới hạn của việc tránh tràn/hụt trung gian

### 7.1. Kết quả cuối vẫn có miền biểu diễn hữu hạn

`Math.hypot(Double.MAX_VALUE, Double.MAX_VALUE)` không thể tạo một số hữu hạn lớn hơn mọi `double` hữu hạn. Độ dài toán học xấp xỉ `sqrt(2) × Double.MAX_VALUE`, quá lớn.

Vì vậy, kết quả vô cực ở đây khác bản chất với ví dụ `1e200`: nó phản ánh giới hạn của kết quả cuối, không phải chỉ do bình phương quá sớm.

Cũng cần hiểu giới hạn độ chính xác ở vùng rất nhỏ. Tránh hụt dưới trung gian không bổ sung thêm bit cho kiểu `double`; kết quả vẫn được biểu diễn trong tập giá trị hữu hạn của kiểu này.

### 7.2. Hàm không sửa phép toán đã sai trước lời gọi

Các đối số được tính trước khi `Math.hypot` nhận chúng. Nếu một phép trừ số nguyên đã tràn hoặc một bước trước đã làm mất thông tin, hàm chỉ thấy kết quả sau cùng của bước đó.

Ví dụ:

```java
int left = Integer.MIN_VALUE;
int right = Integer.MAX_VALUE;

double wrong = Math.hypot(right - left, 0.0);
double corrected = Math.hypot((double) right - left, 0.0);
```

`right - left` tính bằng `int` trước, tràn thành `-1`, nên `wrong` là `1.0`.

Ở dòng sửa, `right` được chuyển thành `double` trước phép trừ, khiến phép trừ dùng số học `double`. Với miền `int` ở ví dụ, hiệu `4294967295` biểu diễn chính xác được.

Ép kiểu **sau** phép trừ, như `(double) (right - left)`, là quá muộn.

### 7.3. Giá trị double đầu vào có thể đã mất phân biệt

Với độ lớn `1e16`, cộng thêm `1.0` không tạo một `double` khác:

```java
double a = 1e16;
double b = a + 1.0;

System.out.println(a == b); // true
```

Khi tính `Math.hypot(b - a, 0.0)`, kết quả là 0 vì hai giá trị đầu vào đã bằng nhau trong biểu diễn đang dùng.

Không có hàm độ dài nào suy ra được một đơn vị chênh lệch đã mất trước đó. Nếu cần giữ chính xác những chênh lệch nhỏ trên tọa độ rất lớn, phải thiết kế biểu diễn đầu vào, gốc tọa độ hoặc kiểu số phù hợp từ trước.

## 8. Chương trình chạy đầy đủ

Lưu thành `HypotDemo.java`:

```java
import java.util.Locale;

public class HypotDemo {
    private static double direct(double x, double y) {
        return Math.sqrt(x * x + y * y);
    }

    public static void main(String[] args) {
        System.out.println("hypot(-3, 4)=" + Math.hypot(-3.0, 4.0));

        double large = 1e200;
        System.out.println("large direct=" + direct(large, large));
        double largeHypot = Math.hypot(large, large);
        System.out.println("large hypot finite=" + Double.isFinite(largeHypot));
        System.out.printf(Locale.ROOT, "large hypot / 1e200=%.6f%n",
                largeHypot / large);

        double small = 1e-200;
        System.out.println("small direct=" + direct(small, small));
        double smallHypot = Math.hypot(small, small);
        System.out.println("small hypot positive=" + (smallHypot > 0.0));
        System.out.printf(Locale.ROOT, "small hypot / 1e-200=%.6f%n",
                smallHypot / small);

        System.out.println("inf and NaN="
                + Math.hypot(Double.POSITIVE_INFINITY, Double.NaN));
        System.out.println("finite and NaN=" + Math.hypot(2.0, Double.NaN));
        double zero = Math.hypot(-0.0, -0.0);
        System.out.println("zero bits=0x"
                + Long.toHexString(Double.doubleToRawLongBits(zero)));
        System.out.println("minimum with zero positive="
                + (Math.hypot(Double.MIN_VALUE, 0.0) > 0.0));
        System.out.println("final overflow="
                + Double.isInfinite(Math.hypot(Double.MAX_VALUE, Double.MAX_VALUE)));

        int x = 30000;
        int y = 40000;
        System.out.println("int expression=" + Math.sqrt(x * x + y * y));
        System.out.println("int arguments to hypot=" + Math.hypot(x, y));
        System.out.println("cast after expression="
                + Math.sqrt((double) (x * x + y * y)));

        int left = Integer.MIN_VALUE;
        int right = Integer.MAX_VALUE;
        System.out.println("subtract as int="
                + Math.hypot(right - left, 0.0));
        System.out.println("convert before subtract="
                + Math.hypot((double) right - left, 0.0));

        double a = 1e16;
        double b = a + 1.0;
        System.out.println("input distinction lost=" + (a == b));
        System.out.println("distance after loss=" + Math.hypot(b - a, 0.0));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 HypotDemo.java
java HypotDemo
```

Stdout:

```text
hypot(-3, 4)=5.0
large direct=Infinity
large hypot finite=true
large hypot / 1e200=1.414214
small direct=0.0
small hypot positive=true
small hypot / 1e-200=1.414214
inf and NaN=Infinity
finite and NaN=NaN
zero bits=0x0
minimum with zero positive=true
final overflow=true
int expression=NaN
int arguments to hypot=50000.0
cast after expression=NaN
subtract as int=1.0
convert before subtract=4.294967295E9
input distinction lost=true
distance after loss=0.0
```

Hai tỷ lệ vô tỷ được in đến sáu chữ số sau dấu thập phân bằng `Locale.ROOT` để dấu phân cách ổn định. Điều này giúp quan sát độ lớn mà không coi một chuỗi đủ mọi chữ số là hợp đồng xuyên mọi triển khai.

Các kiểm tra hữu hạn/khác 0 xác nhận điều quan trọng hơn ở đây: kết quả không bị biến thành vô cực hoặc 0 chỉ vì giá trị trung gian.

## 9. Số nguyên: chuyển kiểu phải diễn ra trước phép nhân

Một lỗi khác xuất hiện ngay với các số không lớn trong miền `double`:

```java
int x = 30000;
int y = 40000;

double direct = Math.sqrt(x * x + y * y);
double robust = Math.hypot(x, y);
```

Hai bình phương riêng lẻ còn nằm trong miền `int`, nhưng tổng là `2500000000`, vượt `Integer.MAX_VALUE`. Tổng bị tràn thành số âm, nên `sqrt` nhận số âm và trả `NaN`.

Trong lời gọi `Math.hypot(x, y)`, từng đối số `int` được mở rộng thành `double` khi truyền vào; không có phép nhân số nguyên trong biểu thức đối số.

Nếu vẫn cần minh họa công thức trực tiếp với `int`, phải chuyển kiểu trước phép nhân:

```java
double widened = Math.sqrt((double) x * x + (double) y * y);
```

Cách đó xử lý lỗi tràn số nguyên của ví dụ này. Nó không biến công thức trực tiếp thành một thuật toán ổn định cho mọi giá trị `double` rất lớn hoặc rất nhỏ.

Với `long`, mở rộng sang `double` còn có thể làm mất chính xác số nguyên khi giá trị vượt khả năng giữ mọi số nguyên liên tiếp của `double`. Không suy rộng kết luận “chuyển trước phép toán là chính xác” của ví dụ `int` cho mọi giá trị `long`.

## 10. Khoảng cách giữa hai điểm

Với các tọa độ đã là `double`:

```java
static double distance(double x1, double y1, double x2, double y2) {
    double dx = x2 - x1;
    double dy = y2 - y1;
    return Math.hypot(dx, dy);
}
```

Đây là một phương thức minh họa đặt trong lớp. Nó tránh bình phương trực tiếp `dx`, `dy`; nó vẫn chịu giới hạn của việc biểu diễn tọa độ và phép trừ trước đó.

Với tọa độ `int`, chuyển kiểu trước khi trừ:

```java
static double distance(int x1, int y1, int x2, int y2) {
    double dx = (double) x2 - x1;
    double dy = (double) y2 - y1;
    return Math.hypot(dx, dy);
}
```

Chỉ đổi kiểu của biến nhận kết quả sang `double` là chưa đủ: `double dx = x2 - x1;` vẫn thực hiện phép trừ `int` trước.

Nếu cần độ dài ba chiều, có thể ghép:

```java
double length = Math.hypot(Math.hypot(x, y), z);
```

Tuy nhiên, khi ghép nhiều lời gọi, mỗi lời gọi đều có làm tròn. Không suy ra bảo đảm sai số của một lời gọi hai đối số tự động trở thành cùng một bảo đảm cho một vectơ rất nhiều chiều. Với tính toán nhiều chiều chuyên dụng, cần thuật toán chuẩn vectơ và kiểm chứng sai số tương ứng.

## 11. Kiểm chứng sai số đúng trọng tâm

Một chiến lược kiểm tra hữu ích gồm nhiều nhóm:

| Nhóm | Ví dụ | Điều cần quan sát |
|---|---|---|
| Giá trị quen thuộc | `3,4`, `-3,4` | Kết quả `5`, không phụ thuộc dấu thành phần |
| Độ lớn cao | `1e200,1e200` | Hữu hạn khi độ dài còn trong miền |
| Độ lớn thấp | `1e-200,1e-200` | Khác 0 khi độ dài biểu diễn được |
| Chênh thang đo | Một thành phần rất lớn, một rất nhỏ | Kết quả phản ánh giới hạn độ phân giải tại thang lớn |
| Đặc biệt | 0 có dấu, `NaN`, vô cực | Khớp hợp đồng API |
| Trước lời gọi | Hiệu tọa độ `int` gần biên | Không tràn trước khi được mở rộng kiểu |
| Kết quả cuối quá lớn | Hai `Double.MAX_VALUE` | Phân biệt giới hạn kết quả với lỗi trung gian |

Không dùng công thức trực tiếp làm “đáp án chuẩn” cho các trường hợp mà chính nó đang tràn/hụt. Một tham chiếu độc lập phải có độ chính xác và miền biểu diễn phù hợp với điều đang kiểm chứng.

Một ngưỡng tuyệt đối duy nhất cũng có thể làm kiểm tra số rất nhỏ mất ý nghĩa. Ví dụ, nếu cho phép sai số tuyệt đối `1e-12`, thì giá trị sai bằng 0 vẫn rất gần `1e-200` theo ngưỡng đó. Cần kiểm tra riêng tính khác 0, thang đo và/hoặc sai số theo ulp hay tương đối phù hợp.

Khi so sánh có `NaN` hoặc vô cực, xử lý chúng riêng; các công thức sai số như `abs(actual - expected)` có thể tự tạo `NaN` ở trường hợp vô cực trừ vô cực.

Nếu cần khả năng tái hiện theo một thuật toán thư viện được quy định chặt hơn giữa các nền tảng, xem hợp đồng của [StrictMath.hypot](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StrictMath.html#hypot(double,double)). Điều đó vẫn không làm số dấu phẩy động trở thành số thực chính xác vô hạn và không sửa lỗi trong các biểu thức tạo đối số.

## 12. Bài tập tự kiểm tra

1. Vì sao `sqrt(x*x+y*y)` với `x=y=1e200` có thể cho vô cực dù đáp án cuối còn hữu hạn?
2. Vì sao hai bình phương của `1e-200` thành 0 không có nghĩa độ dài hai chiều phải bằng 0?
3. `Math.hypot(Double.NaN, Double.NEGATIVE_INFINITY)` cho gì?
4. Viết `Math.sqrt((double) (x*x+y*y))` có sửa được lỗi tràn `int` trong ví dụ 30000/40000 không?
5. `Math.hypot` có thể khôi phục chênh lệch đã mất khi `a` và `a+1.0` trở thành cùng một `double` không?
6. Tránh tràn trung gian có bảo đảm mọi kết quả cuối đều hữu hạn không?

Đáp án:

1. Bình phương có độ lớn `1e400`, vượt miền trước khi lấy căn.
2. Độ dài có độ lớn khoảng `1.4142e-200`, vẫn biểu diễn được; lỗi nằm ở đường tính trung gian.
3. Dương vô cực, vì trường hợp có vô cực được ưu tiên theo hợp đồng.
4. Không. Phép nhân/cộng số nguyên đã xảy ra trước ép kiểu.
5. Không. Hàm chỉ nhận các giá trị đã được biểu diễn.
6. Không. Độ dài thật có thể vượt miền hữu hạn, như khi cả hai đối số bằng `Double.MAX_VALUE`.
