# sin, cos, tan và chuyển độ sang radian trong Java

## 1. Vấn đề quan trọng nhất: Java nhận radian

Các hàm lượng giác **Math.sin(double)**, **Math.cos(double)** và **Math.tan(double)** trong Java luôn hiểu đối số là **radian**, không phải độ. Nếu dữ liệu nhập từ giao diện hoặc bài toán hình học dùng độ, hãy chuyển đơn vị **trước khi gọi hàm**.

~~~java
double angleDegrees = 30.0;
double angleRadians = Math.toRadians(angleDegrees);
double value = Math.sin(angleRadians); // xấp xỉ 0.5
~~~

Ngược lại, **Math.sin(30.0)** tính sin của **30 radian**: đó không phải sin(30°) mà học sinh thường gặp ở trường.

Bài học này làm rõ đơn vị góc, công thức lượng giác, cách dùng Math và StrictMath, sai số dấu phẩy động, xử lý góc gần 90°, chương trình chạy bằng Java 17+ và những lỗi lập trình phổ biến.

## 2. Độ, radian và công thức chuyển đổi

- **Độ**: một vòng tròn đầy đủ là **360°**.
- **Radian**: độ lớn góc bằng tỷ số **độ dài cung / bán kính**. Một vòng đầy đủ là **2π rad**.
- **180° = π rad**; **90° = π/2 rad**.

Công thức:

\[
\text{radian}=\text{độ}\times\frac{\pi}{180}
\]

\[
\text{độ}=\text{radian}\times\frac{180}{\pi}
\]

Bảng quy đổi:

| Độ | Radian (toán học) | Gần đúng |
| ---: | --- | ---: |
| 0° | 0 | 0 |
| 30° | π/6 | 0.523599 |
| 45° | π/4 | 0.785398 |
| 60° | π/3 | 1.047198 |
| 90° | π/2 | 1.570796 |
| 180° | π | 3.141593 |
| 270° | 3π/2 | 4.712389 |
| 360° | 2π | 6.283185 |

Hằng **Math.PI** chứa một giá trị **double xấp xỉ π**, vì π có vô hạn chữ số không tuần hoàn. Do đó, phép chuyển đơn vị trong Java có thể phải làm tròn.

### Math.toRadians và Math.toDegrees

~~~java
double radians = Math.toRadians(180.0); // xấp xỉ π
double degrees = Math.toDegrees(Math.PI); // xấp xỉ 180
~~~

**Math.toRadians(double)** đổi độ → radian; **Math.toDegrees(double)** đổi radian → độ. Cả hai đều nhận và trả **double**, không áp đặt rằng độ phải thuộc khoảng 0–360.

~~~java
double negative = Math.toRadians(-45.0); // xấp xỉ -π/4
double repeated = Math.toRadians(720.0); // xấp xỉ 4π
~~~

Giá trị **−45°** có thể biểu diễn chiều quay ngược so với +45°. **720°** là hai vòng đầy đủ, vẫn có thể truyền cho sin/cos/tan. Tuy nhiên, do sai số biểu diễn, các kết quả theo chu kỳ có thể không bằng nhau **từng bit**.

Cũng không được giả định phép đổi sang radian rồi đổi ngược sang độ luôn trả đúng lại double ban đầu theo toán tử **==**. Khi cần xác minh, hãy so sánh theo ngưỡng sai số phù hợp với dữ liệu và ứng dụng.

## 3. Sin, cos, tan trên đường tròn đơn vị

Theo hệ tọa độ toán học chuẩn, góc θ đo từ trục x dương, chiều dương ngược chiều kim đồng hồ. Điểm trên đường tròn đơn vị có:

\[
x=\cos(\theta),\qquad y=\sin(\theta)
\]

**Cos** cho thành phần ngang; **sin** cho thành phần dọc. Khi **cos(θ) khác 0** về mặt toán học:

\[
\tan(\theta)=\frac{\sin(\theta)}{\cos(\theta)}
\]

Các tính chất:

- Với đối số thực hữu hạn, sin và cos nằm trong **[−1, 1]**.
- Tan có thể lớn vô hạn về độ lớn khi tiến đến tiệm cận; không có một biên tuyệt đối cố định.
- **sin(−θ)=−sin(θ)**, **tan(−θ)=−tan(θ)**: các hàm lẻ.
- **cos(−θ)=cos(θ)**: hàm chẵn.
- Sin và cos có chu kỳ **2π**; tan có chu kỳ **π** trong toán học.

Các đồng nhất thức này đúng chính xác trong toán học; số dấu phẩy động Java có thể chỉ xấp xỉ do làm tròn.

### Các góc đặc biệt

| Góc độ | sin | cos | tan |
| ---: | --- | --- | --- |
| 0° | 0 | 1 | 0 |
| 30° | 1/2 | √3/2 | √3/3 |
| 45° | √2/2 | √2/2 | 1 |
| 60° | √3/2 | 1/2 | √3 |
| 90° | 1 | 0 | **Không xác định** |
| 180° | 0 | −1 | 0 |
| 270° | −1 | 0 | **Không xác định** |
| 360° | 0 | 1 | 0 |

Ở **90°** và **270°**, tan **không xác định theo toán học**. Không viết rằng tan tại hai góc này bằng Infinity: Java không có biểu diễn π/2 chính xác trong double, và tan có thể trả một giá trị hữu hạn rất lớn khi tính gần tiệm cận.

## 4. Math.sin: tính thành phần y và độ cao

~~~java
double sine = Math.sin(Math.toRadians(30.0)); // xấp xỉ 0.5
~~~

Sin dương ở phần tư I và II, âm ở phần tư III và IV. Ở góc 0° và 180°, sin bằng 0 theo toán học; tuy nhiên **Math.sin(Math.PI)** không bắt buộc bằng 0.0 chính xác, vì Math.PI chỉ xấp xỉ π.

Ví dụ vector có độ lớn 10 tạo góc 30° với trục x:

~~~java
double length = 10.0;
double radians = Math.toRadians(30.0);
double y = length * Math.sin(radians); // xấp xỉ 5.0
~~~

Đầu vào của sin phải là radian; hệ tọa độ thực tế có thể có chiều trục y khác quy ước toán học, vì vậy phải kiểm tra trước khi áp dụng vào giao diện hoặc đồ họa.

## 5. Math.cos: tính thành phần x

~~~java
double cosine = Math.cos(Math.toRadians(60.0)); // xấp xỉ 0.5
~~~

Cos dương ở phần tư I và IV, âm ở phần tư II và III. Ở góc 90° và 270°, cos bằng 0 trong toán học. Nhưng:

~~~java
double rightAngle = Math.toRadians(90.0);
boolean exactlyZero = Math.cos(rightAngle) == 0.0; // false trên JDK thông dụng
~~~

Giá trị Math.cos(rightAngle) thường gần **6.123 × 10^−17**; không phải lỗi hình học. Nó là sai số rất nhỏ do các phép chuyển đổi và tính toán trên double.

Ví dụ thành phần x của vector dài 10 ở góc 60°:

~~~java
double x = 10.0 * Math.cos(Math.toRadians(60.0));
// x xấp xỉ 5.0
~~~

## 6. Math.tan: tính độ dốc và tránh điểm cực

~~~java
double tangent = Math.tan(Math.toRadians(45.0)); // xấp xỉ 1.0
~~~

Trong toán học, tan=sin/cos khi cos khác 0. Tan thường được dùng để suy ra tỷ lệ hai cạnh hoặc độ dốc tại góc không thẳng đứng.

**Tại sao tan(90°) không nhất thiết thành Infinity trong Java?**

~~~java
double nearHalfPi = Math.toRadians(90.0);
double c = Math.cos(nearHalfPi);
double t = Math.tan(nearHalfPi);
System.out.println(c == 0.0);        // false
System.out.println(Double.isFinite(t)); // true
~~~

Math.toRadians(90.0) là một double **gần π/2**. Vì cos không bằng chính xác 0, Math.tan trả một giá trị hữu hạn rất lớn ở góc xấp xỉ này. Dù máy trả số, **độ dốc tại góc thẳng đứng không xác định** trong mô hình toán học.

Đối với một ứng dụng không chấp nhận góc quá gần tiệm cận của tan, có thể định nghĩa chính sách kiểm tra:

~~~java
double radians = Math.toRadians(inputDegrees);
if (Math.abs(Math.cos(radians)) < 1.0e-12) {
    throw new IllegalArgumentException("Angle too close to a tan pole");
}
double slope = Math.tan(radians);
~~~

Đoạn trên nằm bên trong method có biến **inputDegrees**. **1e−12 không phải ngưỡng đúng cho mọi bài toán**: đây chỉ là ví dụ yêu cầu miền đầu vào; phải chọn tiêu chí theo độ nhạy và sai số cho phép. Kiểm tra cosine khác 0 bằng toán tử **!=** vẫn có thể chấp nhận các độ dốc lớn phi thực tế.

**Math.tan(x)** có thể không trùng từng bit với **Math.sin(x)/Math.cos(x)**, vì thuật toán và bước làm tròn khác nhau. Khi cần tan, gọi trực tiếp Math.tan; nếu cần vector, hãy tính sin/cos theo từng trục.

## 7. Trigonometry trong ứng dụng: vector và tọa độ

Một vector dài **r** và góc **θ** từ trục x dương theo chiều ngược kim đồng hồ có:

\[
x=r\cos(\theta),\qquad y=r\sin(\theta)
\]

Với **r=10, θ=30°**:

~~~java
double magnitude = 10.0;
double angleDegrees = 30.0;
double angleRadians = Math.toRadians(angleDegrees);
double x = magnitude * Math.cos(angleRadians); // xấp xỉ 8.660254
double y = magnitude * Math.sin(angleRadians); // xấp xỉ 5.0
~~~

Công thức xuất hiện trong đồ họa, robot, mô phỏng, vật lý, lực, vận tốc và hình học. Tuy nhiên màn hình máy tính thường có **y tăng xuống dưới**, khác hệ trục toán học. Một chương trình đồ họa có thể phải đổi dấu thành phần y hoặc đổi quy tắc đo góc. Không áp dụng máy móc khi chưa xác định hệ tọa độ.

Nguyên tắc quan trọng khi thiết kế API: đặt tên **angleDegrees** hoặc **angleRadians**; nếu tương tác với nhiều thư viện, ghi rõ quy tắc trục, chiều dương và đơn vị góc tại điểm giao tiếp.


## 8. Math và StrictMath khác gì nhau?

Java có **java.lang.Math** và **java.lang.StrictMath**, đều cung cấp **sin**, **cos**, **tan**, **toRadians**, **toDegrees**.

- **Math** có thể được JVM tối ưu bằng các cách thực thi khác nhau, miễn đáp ứng các cam kết của đặc tả API. Với một số phép toán, bit kết quả có thể khác đôi chút giữa nền tảng.
- **StrictMath** được thiết kế cho hành vi tái lập của các hàm toán học cốt lõi theo thuật toán được chỉ định, phù hợp khi cần tính nhất quán kết quả giữa các triển khai Java.
- **Cả hai đều nhận góc radian** cho sin/cos/tan.
- StrictMath **không làm cho π trở thành số biểu diễn chính xác** và không bảo đảm tất cả đồng nhất thức lượng giác đúng từng bit.

Ví dụ:

~~~java
double rad = Math.toRadians(30.0);
double fast = Math.sin(rad);
double reproducible = StrictMath.sin(rad);
// Cả hai xấp xỉ 0.5; không nên giả định luôn cùng mẫu bit.
~~~

Tài liệu Java 17 cho **Math.sin/cos/tan** nêu yêu cầu độ chính xác trong phạm vi **1 ulp** của kết quả đúng toán học và tính **semi-monotonic**. Điều này không có nghĩa Math.cos(π/2) phải bằng chính xác 0, bởi π/2 đưa vào đã bị xấp xỉ.

Trong đa số ứng dụng Java Core, **Math** phù hợp. Chọn **StrictMath** khi yêu cầu sản phẩm có ràng buộc cụ thể về tái lập kết quả bit của các hàm được đặc tả.

## 9. Sai số floating-point và so sánh gần đúng

Double có độ chính xác hữu hạn. Những biểu thức có kết quả toán học đẹp như 0, 0.5 hoặc 1 không luôn tạo đúng những bit tương ứng do chuyển đơn vị, phép tính xấp xỉ hoặc cách giảm đối số.

Ví dụ:

~~~java
boolean equal = Math.sin(Math.toRadians(180.0)) == 0.0;
// false trên JDK thông dụng, dù sin(180°)=0 trong toán học
~~~

Khi kiểm thử trên miền giá trị có giới hạn, một hàm so sánh **sai số tuyệt đối** hữu ích:

~~~java
static boolean nearlyEqual(double a, double b, double tolerance) {
    return Double.isFinite(a) && Double.isFinite(b)
            && tolerance >= 0.0
            && Math.abs(a - b) <= tolerance;
}
~~~

Đây là phương thức đặt trong class. Ví dụ:

~~~java
boolean valid = nearlyEqual(
        Math.sin(Math.toRadians(30.0)), 0.5, 1.0e-12);
~~~

**1e−12 chỉ là lựa chọn minh họa** đối với phép tính lượng giác đơn giản trên miền gần [−1, 1]. Không tự sử dụng ngưỡng này cho mọi hệ thống. Với đại lượng có đơn vị, cần xác định giới hạn nghiệp vụ; với dữ liệu độ lớn khác nhau, có thể dùng sai số tương đối hoặc ULP tùy hợp đồng.

Việc làm tròn mọi kết quả nhỏ thành 0 có thể che dấu thông tin số học quan trọng. Nếu ứng dụng muốn đánh dấu các góc đặc biệt như 90° hoặc 180°, phải định nghĩa quy tắc xử lý góc và ngưỡng xấp xỉ ở mức nghiệp vụ, không gắn cứng vào Math.

## 10. Chương trình Java 17+ biên dịch và chạy độc lập

Lưu chương trình thành **TrigAngleDemo.java**:

~~~java
import java.util.Locale;

public class TrigAngleDemo {
    static boolean nearlyEqual(double a, double b, double tolerance) {
        return Double.isFinite(a) && Double.isFinite(b)
                && tolerance >= 0.0
                && Math.abs(a - b) <= tolerance;
    }

    static void show(double degrees) {
        double radians = Math.toRadians(degrees);
        System.out.printf(Locale.US,
                "%5.0f deg -> rad=%8.5f, sin=% .6f, cos=% .6f, tan=% .6f%n",
                degrees, radians, Math.sin(radians),
                Math.cos(radians), Math.tan(radians));
    }

    public static void main(String[] args) {
        show(0.0);
        show(30.0);
        show(45.0);
        show(60.0);
        show(-45.0);

        double rightAngle = Math.toRadians(90.0);
        double halfTurn = Math.toRadians(180.0);

        System.out.println("cos(90) == 0: "
                + (Math.cos(rightAngle) == 0.0));
        System.out.printf(Locale.US, "cos(90) approx: %.3e%n",
                Math.cos(rightAngle));
        System.out.println("tan(90) is finite: "
                + Double.isFinite(Math.tan(rightAngle)));
        System.out.println("sin(180) == 0: "
                + (Math.sin(halfTurn) == 0.0));

        System.out.println("sin(30) near 0.5: "
                + nearlyEqual(Math.sin(Math.toRadians(30.0)),
                        0.5, 1.0e-12));
        System.out.println("StrictMath.sin(30) near 0.5: "
                + nearlyEqual(
                        StrictMath.sin(StrictMath.toRadians(30.0)),
                        0.5, 1.0e-12));

        System.out.printf(Locale.US, "roundtrip: %.10f deg%n",
                Math.toDegrees(Math.toRadians(123.0)));
        System.out.println("sin(infinity) is NaN: "
                + Double.isNaN(Math.sin(Double.POSITIVE_INFINITY)));
        System.out.println("sin(-0.0) keeps negative zero: "
                + (Double.doubleToRawLongBits(Math.sin(-0.0))
                        == Double.doubleToRawLongBits(-0.0)));
    }
}
~~~

Lệnh dùng với JDK 17+:

~~~bash
javac --release 17 TrigAngleDemo.java
java TrigAngleDemo
~~~

Stdout trên JDK đã kiểm tra (giữ nguyên các khoảng trắng đầu dòng do printf):

~~~text
    0 deg -> rad= 0.00000, sin= 0.000000, cos= 1.000000, tan= 0.000000
   30 deg -> rad= 0.52360, sin= 0.500000, cos= 0.866025, tan= 0.577350
   45 deg -> rad= 0.78540, sin= 0.707107, cos= 0.707107, tan= 1.000000
   60 deg -> rad= 1.04720, sin= 0.866025, cos= 0.500000, tan= 1.732051
  -45 deg -> rad=-0.78540, sin=-0.707107, cos= 0.707107, tan=-1.000000
cos(90) == 0: false
cos(90) approx: 6.123e-17
tan(90) is finite: true
sin(180) == 0: false
sin(30) near 0.5: true
StrictMath.sin(30) near 0.5: true
roundtrip: 123.0000000000 deg
sin(infinity) is NaN: true
sin(-0.0) keeps negative zero: true
~~~

### Giải thích dòng output

- **0°, 30°, 45°, 60°, −45°** được đưa qua Math.toRadians trước khi tính. Số có 6 chữ số thập phân chỉ là chuỗi đã format, không phải độ chính xác đầy đủ của kết quả double.
- **sin(30°) ≈ 0.5**, **cos(60°) ≈ 0.5**, tan(45°) xấp xỉ 1 theo công thức toán học.
- **cos(90) == 0** và **sin(180) == 0** false vì đầu vào radian và kết quả đều xấp xỉ ở kiểu double.
- **tan(90) is finite** true không có nghĩa tan tại góc thẳng đứng xác định theo toán học.
- **roundtrip: 123.0000000000 deg** được làm tròn đến 10 chữ số hiển thị; không phải lời bảo đảm rằng mọi góc double đều round-trip chính xác.
- **sin(infinity) is NaN** và bit dấu của **sin(−0.0)** minh họa các trường hợp dấu phẩy động đặc biệt.

## 11. NaN, infinity và zero có dấu

Các hàm sin/cos/tan của Java có các hành vi đặc biệt:

| Đối số double | sin | cos | tan |
| --- | --- | --- | --- |
| NaN | NaN | NaN | NaN |
| +Infinity hoặc −Infinity | NaN | NaN | NaN |
| +0.0 | +0.0 | 1.0 | +0.0 |
| −0.0 | −0.0 | 1.0 | −0.0 |

Hai giá trị **+0.0 và −0.0** bằng nhau theo toán tử == nhưng khác bit dấu. Nếu cần kiểm tra dấu âm zero:

~~~java
boolean negativeZeroRetained =
        Double.doubleToRawLongBits(Math.sin(-0.0))
                == Double.doubleToRawLongBits(-0.0); // true
~~~

Nếu dữ liệu biểu thị một **góc vật lý thực**, thường nên kiểm tra đầu vào hữu hạn:

~~~java
if (!Double.isFinite(angleDegrees)) {
    throw new IllegalArgumentException("Angle must be finite");
}
double radians = Math.toRadians(angleDegrees);
~~~

Đoạn minh họa nằm trong method có biến angleDegrees đã khai báo. Không so một giá trị với Double.NaN qua ==, vì NaN không bằng chính nó. Dùng **Double.isNaN** để kiểm tra.

## 12. Góc âm, nhiều vòng và góc rất lớn

Sin và cos có chu kỳ 2π, tan có chu kỳ π trong toán học. Vì vậy góc 30° và 390° cho cùng giá trị sin/cos lý tưởng. Nhưng trong số dấu phẩy động, phép nhân và phép giảm theo chu kỳ có thể làm tròn.

Nếu cần một góc chuẩn hóa theo độ trong **[0,360)** cho dữ liệu hữu hạn thông thường:

~~~java
double normalized = ((angleDegrees % 360.0) + 360.0) % 360.0;
~~~

Công thức minh họa này không phải phương pháp giảm đối số chính xác tuyệt đối cho **mọi double cực lớn**. Khi góc tích lũy qua quá nhiều vòng, phần lẻ của góc có thể bị mất do độ phân giải của double. Thiết kế tốt là giữ góc trong miền hữu hạn vừa phải ngay từ đầu nếu quy trình cho phép.

Cũng cần phân biệt chu kỳ với miền: một góc âm có thể chứa thông tin chiều quay, nên không tự gọi **Math.abs** trước khi tính sin.

## 13. Lấy góc trở lại bằng Math.atan2

Khi có tọa độ **(x,y)** và muốn suy ra góc, dùng **Math.atan2(y, x)** để lấy góc dưới dạng radian rồi **Math.toDegrees** nếu muốn độ:

~~~java
double x = Math.sqrt(3.0);
double y = 1.0;
double radians = Math.atan2(y, x);
double degrees = Math.toDegrees(radians); // xấp xỉ 30.0
~~~

**Thứ tự đối số atan2 là (y, x)**, rất dễ nhầm với tọa độ thường ghi (x,y). Khác với atan(y/x), atan2 phân biệt phần tư và có quy tắc cho trục tọa độ, zero có dấu. Hàm atan2 hữu ích khi đi theo chiều ngược từ vector sang góc.

Đây là kiến thức bổ sung liên quan: mục đích chính của bài vẫn là chuyển **độ sang radian trước khi dùng sin/cos/tan**.

## 14. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Gọi Math.sin(30) khi 30 là độ | Tính sin của 30 radian | Math.sin(Math.toRadians(30)) |
| Quên chia cho 180 khi dùng Math.PI | Sai đơn vị góc | Dùng Math.toRadians |
| Cho rằng Math.PI biểu diễn chính xác π | So sánh == tại π, π/2 thất bại | So sánh gần đúng có chính sách |
| Mong tan tại 90° luôn bằng Infinity | Java có thể cho số hữu hạn rất lớn | Xử lý tiệm cận/miền góc |
| Dùng tan để biểu diễn đường thẳng đứng | Độ dốc toán học không xác định | Xử lý riêng vector/đường đứng |
| So Math.cos(Math.PI/2) == 0 | Có thể false do làm tròn | Dùng kiểm tra phù hợp |
| Dùng epsilon cố định cho mọi góc | Có thể quá lớn hoặc quá nhỏ | Chọn ngưỡng theo yêu cầu |
| Tự lấy Math.abs của góc âm | Mất hướng quay, sai sin/tan | Giữ dấu theo hợp đồng |
| Nghĩ StrictMath nhận độ | Cũng nhận radian | Chuyển đơn vị trước |
| Dùng sin/cos rồi chia thay tan và kỳ vọng đúng bit | Thuật toán/làm tròn khác nhau | Gọi Math.tan nếu cần tan |
| Không kiểm tra NaN/infinity | Tạo NaN lan truyền | Kiểm tra Double.isFinite nếu cần |
| Dùng y dương xuống như y dương lên | Vector quay không đúng theo hình học | Xác định hệ tọa độ |
| Cộng số vòng rất lớn rồi giảm modulo tùy tiện | Độ phân giải double có thể mất pha | Giữ góc ở miền vừa phải |

## 15. Bài tập và đáp án

**Bài 1.** Muốn tính sin 60° trong Java, viết biểu thức nào?

*Đáp án:* **Math.sin(Math.toRadians(60.0))**, gần **0.8660254**.

**Bài 2.** 45° bằng bao nhiêu radian? Tan(45°) bằng bao nhiêu trong toán học?

*Đáp án:* **π/4 rad** và **1**. Giá trị Java là xấp xỉ.

**Bài 3.** Math.cos(Math.toRadians(90.0)) có luôn là 0.0 không?

*Đáp án:* Không. Math.PI và quá trình tính double có sai số, nên thường ra khoảng **6.123e−17**.

**Bài 4.** Vì sao tan(90°) không nên dùng để tính độ dốc đường thẳng đứng?

*Đáp án:* Tan tại 90° không xác định trong toán học; Math.tan được gọi với góc double gần π/2 có thể cho giá trị hữu hạn rất lớn và cực nhạy.

**Bài 5.** Cho vector độ dài 10 ở góc 30°. Thành phần x và y xấp xỉ bao nhiêu?

*Đáp án:* **x≈8.660254**, **y≈5** nếu lấy trục x dương làm góc 0° và chiều dương ngược kim đồng hồ.

**Bài 6.** Đầu vào đã là radian thì có nên gọi Math.toRadians thêm lần nữa không?

*Đáp án:* Không. Truyền trực tiếp góc radian cho Math.sin/cos/tan.

**Bài 7.** Math.sin(Double.POSITIVE_INFINITY) trả gì?

*Đáp án:* **NaN**, kiểm tra bằng **Double.isNaN**.

**Bài 8.** Khi nào chọn StrictMath.sin?

*Đáp án:* Khi yêu cầu tính tái lập theo đặc tả StrictMath giữa các triển khai; cả Math lẫn StrictMath vẫn nhận radian.

**Bài 9.** Vì sao chuyển độ sang radian rồi trở về độ có thể không chính xác bằng ==?

*Đáp án:* Số π và các kết quả double đều hữu hạn độ chính xác, nên phép chuyển đổi có thể phải làm tròn.

## 16. Tài liệu gốc

- [Math Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): sin, cos, tan, PI, toRadians, toDegrees, độ chính xác của các hàm.
- [StrictMath Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StrictMath.html): tính tái lập của các hàm toán học.
- [Double Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): NaN, Infinity, isFinite và raw bits.
- [Java Language Specification 17 — Floating-Point Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): biểu diễn double, zero có dấu, NaN và infinity.
