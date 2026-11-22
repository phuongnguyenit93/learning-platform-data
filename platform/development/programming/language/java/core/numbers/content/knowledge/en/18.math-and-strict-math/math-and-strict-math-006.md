# `Math.hypot` và việc giảm nguy cơ overflow trung gian trong Java

## 1. Bài toán: tính căn của tổng hai bình phương

Trong hình học phẳng, độ dài cạnh huyền của tam giác vuông với hai cạnh góc vuông `x`, `y` là:

\[
h=\sqrt{x^2+y^2}.
\]

Công thức này cũng là chuẩn Euclid hai chiều của vectơ `(x, y)` và xuất hiện trong phép tính khoảng cách giữa hai điểm, độ lớn vận tốc, tín hiệu phức, thống kê và các thuật toán số.

Một cách viết trực tiếp bằng Java:

```java
double x = 3.0;
double y = 4.0;
double h = Math.sqrt(x * x + y * y);

System.out.println(h); // 5.0
```

Ở ví dụ nhỏ, công thức hoạt động tốt. Nhưng ở thang giá trị rất lớn hoặc rất nhỏ, các phép **bình phương trung gian** có thể vượt ra ngoài miền biểu diễn hoặc làm tròn về 0, ngay cả khi **kết quả cuối cùng vẫn biểu diễn được** bằng `double`.

Java cung cấp API phù hợp hơn:

```java
double h = Math.hypot(x, y);
```

`Math.hypot(double x, double y)` tính độ lớn tương ứng với \(\sqrt{x^2+y^2}\) bằng thuật toán nhằm tránh overflow/underflow **không cần thiết ở bước trung gian**. `StrictMath.hypot(double,double)` cũng có chức năng cùng ý nghĩa.

**Ghi nhớ ngay:** khi thực sự muốn tính `sqrt(x*x + y*y)` trên số thực hữu hạn, hãy ưu tiên `Math.hypot(x, y)` thay vì tự tạo hai bình phương. Tuy nhiên, `hypot` không thể làm cho một kết quả thực sự quá lớn trở thành số hữu hạn, và không sửa dữ liệu đã mất chính xác từ trước khi gọi.

## 2. Hai lỗi số học khác nhau: overflow và underflow trung gian

### 2.1. Overflow trung gian khi bình phương

`double` chỉ biểu diễn được số hữu hạn đến khoảng:

\[
\texttt{Double.MAX_VALUE}\approx 1.7976931348623157\times10^{308}.
\]

Với `x = y = 1e200`, mỗi bình phương toán học là `1e400`, lớn hơn miền hữu hạn của `double`. Vì vậy:

```java
double x = 1e200;
double y = 1e200;

double naive = Math.sqrt(x * x + y * y);
double stable = Math.hypot(x, y);

System.out.println(naive);  // Infinity
System.out.println(stable); // 1.414213562373095E200
```

Kết quả toán học thực sự là:

\[
\sqrt{(10^{200})^2+(10^{200})^2}
=\sqrt{2}\cdot 10^{200}
\approx 1.414213562373095\times10^{200}.
\]

Giá trị cuối vẫn nhỏ hơn `Double.MAX_VALUE`. `Infinity` ở cách trực tiếp là **overflow giả do cách sắp xếp phép tính**, không phải vì kết quả toán học không chứa được trong `double`.

Trong biểu thức trực tiếp, `x * x` đã thành `Infinity` trước khi `Math.sqrt` có cơ hội lấy căn. Một khi bước trung gian đã thành vô cực, căn không thể phục hồi giá trị hữu hạn vốn có.

### 2.2. Underflow trung gian khi bình phương

`Double.MIN_VALUE` là số `double` **dương khác 0 nhỏ nhất**, khoảng `4.94E-324`. Giá trị `Double.MIN_NORMAL` là ngưỡng số chuẩn hóa dương nhỏ nhất; phía dưới vẫn có số dưới chuẩn (*subnormal*).

Với `x = y = 1e-200`, bình phương toán học là `1e-400`, quá nhỏ để `double` giữ khác 0. Do đó:

```java
double x = 1e-200;
double y = 1e-200;

double naive = Math.sqrt(x * x + y * y);
double stable = Math.hypot(x, y);

System.out.println(naive);  // 0.0
System.out.println(stable); // 1.414213562373095E-200
```

Kết quả cuối khoảng `1.414E-200`, **lớn hơn rất nhiều** so với `Double.MIN_NORMAL` và hoàn toàn có thể biểu diễn như số hữu hạn chuẩn hóa. Nhưng công thức trực tiếp đánh mất cả hai bình phương trước khi lấy căn.

Điểm chung của hai lỗi: thực hiện phép toán trung gian ở **thang độ lớn quá cao hoặc quá thấp** so với kết quả cuối. Chọn lại cấu trúc thuật toán có thể tránh phải biểu diễn các số trung gian nguy hiểm ấy.

## 3. `Math.hypot` thực hiện điều gì và bảo đảm gì?

Chữ *hypot* viết tắt từ *hypotenuse* (cạnh huyền). Chữ ký phương thức trong Java 17:

```java
public static double hypot(double x, double y)
```

Ý nghĩa toán học:

\[
\operatorname{hypot}(x,y)=\sqrt{x^2+y^2}.
\]

Đối với đối số hữu hạn, kết quả là độ lớn không âm của vectơ `(x,y)`, được tính theo quy tắc số học dấu phẩy động. Thư viện tiêu chuẩn dùng thuật toán số để **giảm nguy cơ tràn hoặc mất dữ liệu trung gian** so với bình phương trực tiếp.

Một vài tính chất đáng nhớ:

- Thứ tự hai đối số không thay đổi giá trị toán học: `hypot(x,y) = hypot(y,x)`.
- Dấu của đối số không thay đổi độ dài: `hypot(-x,y) = hypot(x,y)` về mặt toán học.
- Nếu `x = 0` và `y` hữu hạn, giá trị toán học là `abs(y)`.
- Kết quả hữu hạn không âm; khi kết quả lý tưởng quá lớn để biểu diễn, kết quả có thể là `Infinity`.
- Theo tài liệu API `Math.hypot`, kết quả số hữu hạn có sai số trong khoảng giới hạn **1 ULP** của kết quả chính xác và đáp ứng các yêu cầu chất lượng số được nêu trong đặc tả Java.

`hypot` **không** có nghĩa là tính toán với độ chính xác vô hạn hay hoàn toàn chính xác cho mọi cặp đầu vào. Đó là một phép tính dấu phẩy động có làm tròn, nhưng giảm được một số nguy cơ lớn do biểu thức ngây thơ gây ra.

### Vì sao giá trị trả về là `double`?

Trong Java 17, chữ ký `Math.hypot` nhận hai đối số `double` và trả `double`; không có overload `hypot(float,float)` trả `float`.

```java
float fx = 3.0f;
float fy = 4.0f;

double accurateRange = Math.hypot(fx, fy); // float được nâng sang double
float narrowed = (float) Math.hypot(fx, fy); // có ép kiểu xuống float
```

Nếu ép kết quả về `float`, phép chuyển đổi cuối có thể làm tròn hoặc overflow dù `Math.hypot` trả `double` hữu hạn. Sử dụng kiểu kết quả đúng với miền giá trị và yêu cầu độ chính xác.

## 4. Ý tưởng kỹ thuật: đổi thang trước khi bình phương

Để hiểu cơ chế mà không cần biết chi tiết triển khai của JDK, ta xem xét một biến đổi đại số.

Với `x`, `y` hữu hạn, đặt:

\[
a=\max(|x|,|y|),\quad b=\min(|x|,|y|).
\]

Nếu `a > 0`, thì:

\[
\sqrt{x^2+y^2}
=a\sqrt{1+\left(\frac{b}{a}\right)^2}.
\]

Bởi vì `0 <= b/a <= 1`, việc **bình phương tỷ số** không tạo ra số lớn bất thường. Phép nhân với `a` được dời về cuối, khi đã có độ lớn gần kết quả cần tìm.

Ví dụ với `x = y = 1e200`:

\[
a=10^{200},\quad b/a=1,\quad
h=10^{200}\sqrt{2}.
\]

Thay vì tính `1e400` rồi lấy căn, thuật toán chỉ cần bình phương số `1`. Với `x = y = 1e-200` cũng vậy: tỷ số bằng `1`, không phải bình phương trực tiếp thành `1e-400`.

### Phác thảo thuật toán để học nguyên lý

Phương thức sau chỉ minh họa phép đổi thang, **không phải bản tái triển khai thay thế hoàn chỉnh của `Math.hypot`**:

```java
static double scaledExample(double x, double y) {
    if (Double.isInfinite(x) || Double.isInfinite(y)) {
        return Double.POSITIVE_INFINITY;
    }
    if (Double.isNaN(x) || Double.isNaN(y)) {
        return Double.NaN;
    }

    double a = Math.max(Math.abs(x), Math.abs(y));
    double b = Math.min(Math.abs(x), Math.abs(y));

    if (a == 0.0) {
        return 0.0; // Tránh 0/0 khi cả hai đối số là 0.
    }

    double ratio = b / a; // 0 <= ratio <= 1.
    return a * Math.sqrt(1.0 + ratio * ratio);
}
```

Đoạn trên giải thích tại sao **đưa tỷ lệ về khoảng [0,1]** làm giảm nguy cơ overflow của phép bình phương. Tuy nhiên, một thư viện số chất lượng cao còn phải xử lý chi tiết làm tròn, chênh lệch số mũ rất lớn, số dưới chuẩn, tràn khi nhân cuối, tính chính xác 1 ULP và các trường hợp biên. Bản phác thảo này **không cam kết** cùng chất lượng số với `Math.hypot` trên toàn miền.

`Math.hypot` là lựa chọn mặc định tốt hơn việc tự viết hàm tương đương, trừ khi có yêu cầu chuyên sâu và có kiểm thử số học đầy đủ.

### Tại sao tỷ số có thể làm tròn về 0 mà vẫn hữu ích?

Nếu `a` rất lớn còn `b` vô cùng nhỏ so với `a`, tỷ số `b/a` có thể bị làm tròn thành `0`. Khi đó:

\[
\sqrt{a^2+b^2}\approx a.
\]

Đóng góp của `b` thực sự có thể quá nhỏ so với độ phân giải của kết quả `double` ở cỡ `a`, nên kết quả làm tròn vẫn là `a`. Tuy nhiên, điều này không có nghĩa `b` bằng 0 về mặt toán học; yêu cầu độ chính xác cao hơn phải dùng mô hình số phù hợp.

## 5. `hypot` tránh lỗi trung gian nhưng không tránh tràn của kết quả thật

Một điểm dễ nhầm: `Math.hypot` **không bảo đảm kết quả luôn hữu hạn**.

```java
double x = Double.MAX_VALUE;
double y = Double.MAX_VALUE;

System.out.println(Math.hypot(x, y)); // Infinity
```

Ở đây độ dài toán học bằng \(\sqrt2 \cdot \texttt{Double.MAX_VALUE}\), vượt giá trị hữu hạn tối đa. Overflow ở **kết quả cuối** là một giới hạn không thể giải quyết bằng việc đổi thứ tự phép tính trong cùng kiểu `double`.

Ngược lại:

```java
System.out.println(Math.hypot(1e308, 1e308));
// 1.4142135623730951E308
```

Độ dài toán học vẫn dưới `Double.MAX_VALUE` nên `Math.hypot` có thể trả một số hữu hạn, dù cách `Math.sqrt(x*x + y*y)` đã overflow ở bình phương.

Khi thiết kế chương trình, cần phân biệt:

- **Overflow trung gian có thể tránh:** bình phương hoặc cộng số trung gian quá lớn nhưng kết quả cần tìm vẫn nằm trong miền kiểu.
- **Overflow kết quả không thể tránh bằng `hypot`:** độ dài thực sự lớn hơn miền `double`.
- **Sai số làm tròn vẫn còn:** giá trị toán học nằm trong miền hữu hạn nhưng không có biểu diễn nhị phân chính xác.

Nếu ứng dụng bắt buộc kết quả hữu hạn, vẫn nên xác thực:

```java
double length = Math.hypot(x, y);
if (!Double.isFinite(length)) {
    throw new ArithmeticException("Length is not finite");
}
```

Tùy hợp đồng, có thể cần phân biệt đầu vào vô cực/NaN với overflow do độ lớn kết quả; chỉ nhìn kết quả cuối không đủ cho mọi yêu cầu chẩn đoán.

## 6. `Infinity`, `NaN` và số 0 có dấu

Các phương thức dấu phẩy động của Java có hành vi xác định cho giá trị đặc biệt.

### Vô cực và NaN

```java
System.out.println(Math.hypot(Double.POSITIVE_INFINITY, Double.NaN));
// Infinity

System.out.println(Math.hypot(Double.NaN, 4.0));
// NaN
```

Quy tắc quan trọng của `hypot`: nếu **một đối số là vô cực**, kết quả là vô cực dương, **kể cả khi đối số kia là NaN**. Nếu không có đối số vô cực mà một đối số là `NaN`, kết quả là `NaN`.

Không suy diễn quy tắc này từ việc thay trực tiếp giá trị vào `x*x + y*y`, vì phép cộng với NaN trong biểu thức thông thường có thể tạo `NaN` trong tình huống `hypot` trả vô cực.

### Dấu âm và signed zero

Độ dài Euclid là độ lớn, nên kết quả không âm đối với đối số số thực. Nếu hai đối số đều là số 0, kể cả `-0.0`, kết quả là `+0.0`:

```java
double length = Math.hypot(-0.0, -0.0);

System.out.println(length); // 0.0
System.out.println(
        Long.toHexString(Double.doubleToRawLongBits(length)));
// 0
```

`0.0` và `-0.0` bằng nhau theo toán tử primitive `==`, nhưng có bit dấu khác nhau. `hypot` biểu diễn **độ dài**, do đó dấu của tọa độ âm hoặc của signed zero không được giữ trong kết quả.

### Đầu vào lớn/nhỏ nhưng hữu hạn

`Math.hypot(1e200, 1e200)` và `Math.hypot(1e-200, 1e-200)` đều hữu hạn. Nhưng nếu đầu vào đã là `Infinity`, hoặc được tạo từ một phép tính khác đã overflow, `hypot` không thể khôi phục dữ liệu vốn hữu hạn trước phép toán đó.

Tương tự, nếu một giá trị có độ lớn khác 0 đã underflow thành `0.0` **trước** khi truyền vào `hypot`, thì `hypot` chỉ nhìn thấy `0.0`; nó không khôi phục được giá trị gốc.

## 7. `Math.hypot` và `StrictMath.hypot` khác nhau như thế nào?

Java có hai lớp tiện ích tính toán:

- `java.lang.Math`: tập hợp hàm toán học phổ biến. JVM có thể sử dụng các phép tối ưu hoặc mã nền tảng khi vẫn đáp ứng hợp đồng API.
- `java.lang.StrictMath`: tập hợp hàm toán học được thiết kế với định hướng hành vi số học nhất quán, có các quy định chặt chẽ hơn về khả năng tái lập cho nhiều phép tính. Không nên suy luận rằng **mọi** cặp phương thức trong `Math` và `StrictMath` bắt buộc cho bit kết quả giống nhau trên mọi nền tảng và mọi phiên bản.

Cả hai có phương thức:

```java
double a = Math.hypot(3.0, 4.0);
double b = StrictMath.hypot(3.0, 4.0);
```

Đối với bài toán tính độ dài thông thường, nên ưu tiên `Math.hypot` vì dễ đọc, là API trực tiếp và đáp ứng yêu cầu chất lượng số. Nếu hệ thống có hợp đồng kiểm thử tái lập chi tiết từng bit giữa các môi trường, cần đánh giá **đúng phương thức, JDK, phiên bản và nền tảng** trước khi chọn, thay vì mặc định tên `StrictMath` là lời hứa mọi phép toán toàn hệ thống đều chính xác tuyệt đối.

Đừng dùng `StrictMath.hypot` như biện pháp tự động loại bỏ mọi sai số dấu phẩy động: cả hai đều nhận và trả `double`, nên cùng chịu giới hạn miền biểu diễn.

## 8. Tình huống ứng dụng: khoảng cách giữa hai điểm

Cho hai điểm `P(x1, y1)` và `Q(x2, y2)`:

\[
d(P,Q)=\sqrt{(x_2-x_1)^2+(y_2-y_1)^2}.
\]

Thay vì:

```java
double dx = x2 - x1;
double dy = y2 - y1;
double distance = Math.sqrt(dx * dx + dy * dy);
```

hãy dùng:

```java
double dx = x2 - x1;
double dy = y2 - y1;
double distance = Math.hypot(dx, dy);
```

Hai đoạn trên là **mã minh họa trong ngữ cảnh đã khai báo các tọa độ**. `Math.hypot` loại bỏ nguy cơ overflow/underflow không cần thiết của các bình phương `dx*dx`, `dy*dy`.

Tuy nhiên, cần phân tích luôn phép **trừ tọa độ**:

1. Nếu `x1`, `x2` là `double` rất lớn và gần nhau, các chữ số thấp có thể đã bị làm tròn trong bước lưu dữ liệu. `hypot` không phục hồi chênh lệch đã mất.
2. Nếu tọa độ gốc là số nguyên lớn và được chuyển sang `double` trước khi trừ, các số nguyên liên tiếp có thể trở thành cùng giá trị `double`.
3. Nếu dùng kiểu `int` và viết `int dx = x2 - x1`, bản thân phép trừ có thể overflow theo quy tắc số nguyên Java trước khi truyền vào `hypot`.

Với tọa độ `int`, một cách tránh tràn ở phép trừ là **chuyển sang `double` trước khi trừ**:

```java
int x1 = Integer.MIN_VALUE;
int x2 = Integer.MAX_VALUE;

double dx = (double) x2 - (double) x1;
double distance = Math.hypot(dx, 0.0);

System.out.println(distance); // 4.294967295E9
```

Mọi giá trị `int` đều biểu diễn chính xác bằng `double`, nên phép chuyển trước phép trừ không mất bit phần trị của tọa độ `int`. Ngược lại, ép kiểu **sau** phép trừ nguyên không cứu được overflow đã xảy ra.

Nếu tọa độ là `long` rất lớn và cần giữ phân biệt từng đơn vị, chỉ chuyển từng `long` sang `double` có thể làm tròn. Phải chọn cách tính chênh lệch chính xác và kiểu kết quả phù hợp với miền giá trị của ứng dụng.

### Khoảng cách 3 chiều

Với vectơ `(x,y,z)`, có thể lồng hai phép gọi:

```java
double length3D = Math.hypot(Math.hypot(x, y), z);
```

Đây là cách tránh viết ngay `sqrt(x*x + y*y + z*z)` với ba bình phương trung gian. Kết quả vẫn là phép tính `double` có làm tròn; cần xét overflow cuối cùng và sai số tích lũy. Nếu ứng dụng có yêu cầu numerical analysis đặc biệt, có thể cần thuật toán tính chuẩn nhiều chiều chuyên dụng.

## 9. Ví dụ Java 17 đầy đủ và kết quả

Lưu chương trình sau dưới tên `HypotDemo.java`:

```java
public class HypotDemo {
    public static void main(String[] args) {
        double x = 3.0;
        double y = 4.0;

        System.out.println("3-4 naive: "
                + Math.sqrt(x * x + y * y));
        System.out.println("3-4 hypot: " + Math.hypot(x, y));

        double big = 1e200;
        System.out.println("big naive: "
                + Math.sqrt(big * big + big * big));
        System.out.println("big hypot: " + Math.hypot(big, big));

        double tiny = 1e-200;
        System.out.println("tiny naive: "
                + Math.sqrt(tiny * tiny + tiny * tiny));
        System.out.println("tiny hypot: " + Math.hypot(tiny, tiny));

        System.out.println("near max hypot: "
                + Math.hypot(1e308, 1e308));
        System.out.println("result overflow: "
                + Math.hypot(Double.MAX_VALUE, Double.MAX_VALUE));

        System.out.println("infinite with NaN: "
                + Math.hypot(Double.POSITIVE_INFINITY, Double.NaN));
        System.out.println("NaN with finite: "
                + Math.hypot(Double.NaN, 4.0));

        double zeroLength = Math.hypot(-0.0, -0.0);
        System.out.println("signed zero hypot: " + zeroLength);
        System.out.println("signed zero bits: "
                + Long.toHexString(
                        Double.doubleToRawLongBits(zeroLength)));

        int x1 = Integer.MIN_VALUE;
        int x2 = Integer.MAX_VALUE;
        double dx = (double) x2 - (double) x1;
        System.out.println("int coordinate distance: "
                + Math.hypot(dx, 0.0));

        System.out.println("strict hypot: "
                + StrictMath.hypot(big, big));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac HypotDemo.java
java HypotDemo
```

Kết quả điển hình trên JDK 17 tuân thủ hợp đồng Java (những chữ số cuối của phép tính dấu phẩy động phụ thuộc các bảo đảm cụ thể của phương thức và môi trường):

```text
3-4 naive: 5.0
3-4 hypot: 5.0
big naive: Infinity
big hypot: 1.414213562373095E200
tiny naive: 0.0
tiny hypot: 1.414213562373095E-200
near max hypot: 1.4142135623730951E308
result overflow: Infinity
infinite with NaN: Infinity
NaN with finite: NaN
signed zero hypot: 0.0
signed zero bits: 0
int coordinate distance: 4.294967295E9
strict hypot: 1.414213562373095E200
```

Ví dụ kiểm chứng hai tình huống quan trọng:

- Với `big`, phép nhân trung gian overflow thành `Infinity`, trong khi `Math.hypot` vẫn hữu hạn.
- Với `tiny`, phép nhân trung gian làm tròn thành `0.0`, trong khi `Math.hypot` giữ kết quả hữu hạn khác 0.

Trường hợp `Double.MAX_VALUE` cho thấy `Math.hypot` **không** thể tránh tràn ở kết quả cuối nếu độ dài thật vượt cận.

## 10. Vì sao không tự thay bằng biểu thức “đã rút gọn”?

### `Math.sqrt(x*x + y*y)` nhanh và ngắn nhưng có giới hạn

Công thức trực tiếp thường được dạy trong toán học và có thể đủ khi độ lớn đầu vào đã được giới hạn chặt. Tuy nhiên, khi số liệu có thể trải qua miền rất lớn/nhỏ, nó làm phát sinh các phép nhân nguy hiểm mà `hypot` được thiết kế để giảm.

### Dùng `Math.abs(x)+Math.abs(y)` làm độ dài có đúng không?

Không. Đây là chuẩn Manhattan (`L1`) trong hai chiều, khác chuẩn Euclid (`L2`):

\[
|x|+|y| \neq \sqrt{x^2+y^2}
\]

trừ một số trường hợp đặc biệt. Với `(3,4)`, tổng tuyệt đối là `7` còn độ dài Euclid là `5`. Không thay đổi phép đo chỉ để tránh overflow mà không xác định lại bài toán.

### Dùng `x / max`, `y / max` rồi nhân lại có luôn an toàn?

Kỹ thuật scaling là cơ sở tốt nhưng một phép cài đặt đơn giản có thể gặp khó ở số cực nhỏ, mất độ chính xác của tỷ số hoặc sai số làm tròn ở nhân cuối. Cần xử lý `max == 0`, `NaN`, vô cực, dấu, tỷ lệ rất lệch và kết quả gần giới hạn biểu diễn. Dùng `Math.hypot` thay cho mã tự phát triển trừ khi thật sự cần thuật toán đặc thù.

### Đổi sang `BigDecimal` sau khi có `Infinity` có giúp không?

Không. Nếu `x*x` đã thành `Infinity`, mọi chữ số về giá trị hữu hạn trước đó đã mất trong phép nhân. `BigDecimal` cũng không nhận trực tiếp vô cực làm giá trị decimal.

Nếu thực sự cần miền lớn hơn `double` hoặc tính toán decimal chính xác, phải giữ **đầu vào nguyên bản** dưới kiểu phù hợp và chọn thuật toán căn số cao độ chính xác riêng, chứ không chuyển một kết quả đã overflow sang `BigDecimal` và mong phục hồi.

## 11. Độ chính xác, ULP và kiểm thử

### `hypot` có thể làm tròn nhưng thường đáng tin hơn biểu thức ngây thơ

Dù tránh được nhiều lỗi trung gian, `Math.hypot` vẫn trả một giá trị `double`, tức độ dài thường phải được làm tròn. Cần phân biệt hai yêu cầu:

- **Đúng miền giá trị:** phép tính không overflow/underflow sai do trung gian khi kết quả có thể biểu diễn được.
- **Đúng độ chính xác:** kết quả nằm gần giá trị toán học chuẩn trong giới hạn sai số quy định.

Tài liệu `Math.hypot` nêu yêu cầu chất lượng về **ULP** (unit in last place). ULP là bước đơn vị của phần trị ở vùng số cụ thể, không phải một ngưỡng sai số tuyệt đối cố định trong toàn miền `double`.

```java
double h = Math.hypot(3.0, 4.0);
double ulpAtResult = Math.ulp(h);
```

Một ULP ở cỡ `5` khác hoàn toàn một ULP ở cỡ `1e200`. Không dùng số `1e-9` chung cho mọi phép so sánh nếu bài toán trải qua nhiều thang số.

### Test những miền nào?

| Tình huống | Ví dụ | Mục tiêu |
| --- | --- | --- |
| Tam giác quen thuộc | `(3,4)` | Kết quả cơ bản `5` |
| Hai thành phần lớn | `(1e200,1e200)` | Không overflow trung gian |
| Hai thành phần nhỏ | `(1e-200,1e-200)` | Không underflow trung gian thành 0 |
| Gần cận hữu hạn | `(1e308,1e308)` | Trả độ dài hữu hạn nếu có thể |
| Kết quả thật vượt cận | `(MAX_VALUE,MAX_VALUE)` | Nhận biết `Infinity` hợp lệ |
| Một thành phần 0 | `(3,0)`, `(0,-4)` | Độ dài bằng trị tuyệt đối thành phần còn lại |
| Hai signed zero | `(-0.0,-0.0)` | Kết quả `+0.0` |
| Giá trị đặc biệt | `(NaN,4)`, `(Infinity,NaN)` | Đúng quy tắc API |
| Một lớn, một rất nhỏ | `(1e200,1)` | Không giả định số nhỏ luôn ảnh hưởng bit kết quả |
| Tọa độ nguyên gần biên | `Integer.MIN_VALUE`, `MAX_VALUE` | Tránh overflow khi tính hiệu nguyên |

Với bài toán có độ chính xác cao, kiểm thử có thể dùng kết quả tham chiếu từ thuật toán số chính xác hơn, so sánh theo ULP hoặc theo sai số tương đối/tuyệt đối phù hợp. Không nên so sánh tất cả kết quả dấu phẩy động bằng `==` nếu phép tính có làm tròn; nhưng những trường hợp được bảo đảm chính xác như `(3,4)` cũng có thể kiểm tra kết quả cụ thể.

## 12. Những lỗi thường gặp

1. **Viết `Math.sqrt(x*x+y*y)` cho dữ liệu không giới hạn thang đo.** Bình phương có thể overflow/underflow dù kết quả cuối còn biểu diễn được.
2. **Cho rằng `Math.hypot` luôn trả số hữu hạn.** Nếu độ dài thật vượt `Double.MAX_VALUE`, kết quả có thể `Infinity`.
3. **Chỉ thử số nhỏ nên không nhìn thấy lỗi.** Các case `(3,4)` không phơi lộ overflow trung gian như `(1e200,1e200)`.
4. **Cho rằng mọi underflow cuối đều do lỗi `hypot`.** Nếu độ dài toán học thật quá nhỏ so với độ phân giải, kết quả làm tròn về 0 có thể là đúng quy tắc của `double`.
5. **Dùng `Double.MIN_VALUE` như số âm nhỏ nhất.** Nó là số dương khác 0 nhỏ nhất, không phải cận âm.
6. **Bỏ qua `NaN`/vô cực trong dữ liệu nguồn.** `hypot(Infinity,NaN)` cho vô cực, không nhất thiết giống cách lan truyền NaN của biểu thức trực tiếp.
7. **Trừ `int` rồi mới chuyển sang `double`.** Overflow có thể xảy ra ở hiệu `int` trước khi `hypot` được gọi.
8. **Chuyển `long` rất lớn sang `double` rồi kỳ vọng giữ từng đơn vị.** Giá trị nguyên có thể đã mất bit phần thấp.
9. **Tưởng `StrictMath.hypot` cho độ chính xác vô hạn.** API vẫn làm việc với `double`.
10. **Coi công thức scaling vài dòng là chắc chắn tương đương thư viện.** Phải xử lý sai số, subnormal, overflow cuối và mọi góc biên.
11. **Thay Euclid bằng `abs(x)+abs(y)` không xét ý nghĩa.** Đây là chuẩn khác, làm thay đổi bài toán.
12. **Không kiểm tra kết quả trong ứng dụng đòi hỏi finite.** `Math.hypot` có thể trả `Infinity` hoặc `NaN`, cần chính sách xử lý.
13. **Kỳ vọng `hypot` khôi phục thông tin đầu vào đã mất.** Các phép toán trước đó có thể đã làm tròn hoặc overflow; `hypot` chỉ nhận các `double` hiện tại.
14. **Nhầm độ chính xác của phép tính với độ chính xác của dữ liệu nguồn.** Một thuật toán ổn định không thể sửa số đo hoặc biểu diễn ban đầu đã thiếu độ phân giải.

## 13. Bài tập và đáp án

**Bài 1.** Tại sao `Math.sqrt(1e200*1e200 + 1e200*1e200)` có thể trả `Infinity`, trong khi kết quả toán học cỡ `1.4e200`?

**Đáp án:** Hai phép bình phương trung gian tạo `1e400`, vượt miền hữu hạn của `double`; toán tử nhân cho `Infinity` trước khi có thể lấy căn. `Math.hypot(1e200,1e200)` tránh các bình phương trung gian quá lớn nên giữ kết quả hữu hạn.

**Bài 2.** Tại sao `Math.sqrt(1e-200*1e-200 + 1e-200*1e-200)` cho `0.0`?

**Đáp án:** Các bình phương cỡ `1e-400` nhỏ hơn số `double` dương khác 0 nhỏ nhất, bị làm tròn về `0.0`; cộng và lấy căn không khôi phục được chúng. `Math.hypot` đổi thang và cho khoảng `1.414E-200`.

**Bài 3.** `Math.hypot(Double.MAX_VALUE,Double.MAX_VALUE)` có phải lỗi của API nếu trả `Infinity`?

**Đáp án:** Không. Bản thân độ dài thực sự lớn hơn giá trị hữu hạn tối đa của `double`. `hypot` giảm **overflow trung gian không cần thiết**, không bảo đảm tránh overflow khi kết quả đúng vượt miền.

**Bài 4.** Với `x = 3`, `y = -4`, kết quả toán học của `Math.hypot(x,y)` là bao nhiêu? Dấu âm có được giữ không?

**Đáp án:** `5.0`. Độ dài luôn không âm; dấu của từng thành phần không trở thành dấu âm của kết quả.

**Bài 5.** Nếu một đối số là `Infinity` và đối số kia là `NaN`, `Math.hypot` trả gì?

**Đáp án:** Vô cực dương. Quy tắc đặc biệt của `hypot` ưu tiên vô cực nếu bất kỳ đối số nào là vô cực.

**Bài 6.** Muốn tính khoảng cách giữa hai điểm với hoành độ kiểu `int`, tại sao nên dùng `(double)x2 - x1` trước khi gọi `hypot`?

**Đáp án:** Nếu trừ hai giá trị `int` gần hai biên đối dấu, phép trừ `int` có thể overflow. Mọi giá trị `int` đều biểu diễn chính xác dưới dạng `double`, nên chuyển trước phép trừ tránh được overflow nguyên trong trường hợp này.

**Bài 7.** `Math.hypot(1e308,1e308)` có thể hữu hạn không? Vì sao?

**Đáp án:** Có. Giá trị đúng khoảng `1.4142135623730951E308`, nhỏ hơn `Double.MAX_VALUE` khoảng `1.7976931348623157E308`; cách tính ổn định tránh được overflow bình phương.

**Bài 8.** Nếu một giá trị `float` được ép từ kết quả `Math.hypot`, có chắc không overflow không?

**Đáp án:** Không. `Math.hypot` trả `double`; khi ép về `float`, số đó có thể vượt `Float.MAX_VALUE` và thành vô cực, hoặc bị làm tròn/mất độ chính xác.

**Bài 9.** Nếu thuật toán 3D viết `Math.hypot(Math.hypot(x,y),z)`, có loại bỏ hoàn toàn mọi sai số không?

**Đáp án:** Không. Cách này tránh nhiều nguy cơ từ các phép bình phương trung gian nhưng vẫn làm tròn ở mỗi kết quả `double`. Với yêu cầu độ chính xác đặc biệt, cần phân tích sai số và kiểm tra trên miền dữ liệu thực tế.

**Ghi nhớ:** `Math.hypot(x,y)` là cách trực tiếp và đáng tin để tính \(\sqrt{x^2+y^2}\) trong Java 17+, nhất là khi thành phần có độ lớn rất lớn hoặc rất nhỏ. Hiểu **overflow trung gian** khác **overflow kết quả thực**, và kiểm tra cả chất lượng đầu vào lẫn giá trị trả về khi ứng dụng cần bảo đảm miền hữu hạn.