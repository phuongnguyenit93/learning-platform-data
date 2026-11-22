# Triệt tiêu chữ số khi trừ hai số gần bằng nhau trong Java

## 1. Hiện tượng cần hiểu

Trong tính toán dấu phẩy động, **triệt tiêu chữ số** (*cancellation*) xảy ra khi trừ hai số có giá trị gần nhau. Các chữ số đầu giống nhau bị triệt tiêu, phần hiệu rất nhỏ trở thành kết quả. Nếu hai toán hạng đã chứa sai số làm tròn, sai số ấy có thể chiếm tỷ lệ rất lớn so với hiệu. Trường hợp làm mất nghiêm trọng độ chính xác tương đối thường gọi là **catastrophic cancellation**.

Ví dụ, trong số thực toán học:

\[
(10^{16}+1)-10^{16}=1.
\]

Nhưng với `double` Java:

```java
double base = 1e16;
double plusOne = base + 1.0;
double difference = plusOne - base;

System.out.println(difference);  // 0.0
```

Lý do: `1e16` là một giá trị `double` biểu diễn được, nhưng số nguyên `10^16 + 1` nằm giữa hai giá trị `double` liền kề ở vùng đó. Biểu thức `base + 1.0` được làm tròn trở về `base`. Đến lúc thực hiện phép trừ, chương trình đang trừ **hai giá trị `double` bằng nhau**, vì vậy nhận `0.0`. Giá trị thực cần tìm là `1`, tức sai số tuyệt đối bằng `1` và sai số tương đối của kết quả bằng **100%**.

Điểm cốt lõi: phép trừ có thể thực hiện hoàn toàn chính xác trên **hai số `double` đã được lưu**, nhưng vẫn khác xa hiệu của **hai giá trị toán học ban đầu**. Không nên quy mọi sai số cho riêng toán tử `-`; nguồn sai số thường xuất hiện từ bước tạo toán hạng hoặc phép tính trước đó.

## 2. Vì sao dấu phẩy động dễ gặp triệt tiêu chữ số?

`float` và `double` biểu diễn tập hữu hạn các số nhị phân, với độ chính xác phần trị lần lượt khoảng **24 bit** và **53 bit**. Không phải mọi số thực hay mọi số nguyên lớn đều biểu diễn được chính xác. Khi kết quả nằm giữa hai giá trị đại diện được, Java phải làm tròn theo quy tắc IEEE 754.

Một mô hình sai số đơn giản:

\[
\widehat a=a+\delta_a,\qquad
\widehat b=b+\delta_b
\]

trong đó `a`, `b` là các giá trị toán học dự định, còn `â`, `b̂` là hai giá trị đã lưu. Khi trừ:

\[
\widehat a-\widehat b
=(a-b)+(\delta_a-\delta_b).
\]

Nếu `a` và `b` gần bằng nhau thì `|a-b|` rất nhỏ, trong khi `δa` và `δb` có thể tương đối lớn **so với hiệu**. Ví dụ:

- Giá trị thật: `a = 1_000_000_001`, `b = 1_000_000_000`, hiệu bằng `1`.
- Giả sử hai toán hạng sau làm tròn lần lượt thành `1_000_000_000` và `1_000_000_000`. Hiệu tính được bằng `0`, dù sai số của từng toán hạng chỉ khoảng một phần tỷ so với độ lớn của chúng.

Sai số tuyệt đối của phép trừ có thể nhỏ khi so với toán hạng, nhưng sai số tương đối của kết quả có thể rất lớn. Với `float`, hiện tượng xuất hiện ở mức độ lớn thấp hơn `double` vì số bit chính xác ít hơn.

### Chỉ số nhạy cảm của phép trừ

Với `a != b`, một thước đo độ nhạy đối với sai số tương đối của hai toán hạng là:

\[
\kappa_{\mathrm{sub}}=\frac{|a|+|b|}{|a-b|}.
\]

Khi `a` và `b` gần nhau nhưng có độ lớn đáng kể, mẫu số tiến gần 0 nên `κ` rất lớn. Điều này báo rằng **sai số tương đối nhỏ ở đầu vào có thể bị khuếch đại** khi tính hiệu.

Ví dụ `a ≈ 1_000_000`, `b ≈ 999_999`, thì `|a-b| ≈ 1` và `κ` khoảng hai triệu. Đây là đặc tính độ nhạy của bài toán, không phải bằng chứng một thuật toán cụ thể đã sai. Nếu đầu vào là số chính xác tuyệt đối và hiệu vẫn biểu diễn được, phép trừ có thể không gây thêm sai số.

## 3. Triệt tiêu chữ số không đồng nghĩa “phép trừ luôn thiếu chính xác”

Có một kết quả quan trọng trong số học dấu phẩy động: **bổ đề Sterbenz (Sterbenz's lemma)**. Với hai số dấu phẩy động hữu hạn dương `x`, `y` đã biểu diễn được, nếu

\[
\frac{x}{2}\le y\le 2x,
\]

thì trong số học nhị phân tuân thủ làm tròn và xử lý số dưới chuẩn phù hợp, phép trừ `x - y` có thể được biểu diễn **chính xác**. Java dùng IEEE 754 với số dưới chuẩn, nên đây là một cách giải thích hữu ích cho nhiều phép trừ số gần nhau.

Ví dụ:

```java
double a = Math.nextUp(1.0);  // 1.0000000000000002
double b = 1.0;
double delta = a - b;         // 2.220446049250313E-16
```

Cả `a`, `b` là những giá trị `double` xác định và hiệu của chúng được biểu diễn chính xác. Nếu ta **định nghĩa bài toán trên đúng hai giá trị `double` này**, phép trừ không mất thêm chữ số.

Nhưng nếu `a` và `b` là kết quả của những bước tính gần đúng trước đó, hiệu đúng của **dữ liệu ban đầu** vẫn có thể khác nhiều. Do đó:

1. **Cancellation** mô tả các chữ số đầu triệt tiêu khi lấy hiệu.
2. **Catastrophic cancellation** nhấn mạnh việc sai số có trước bị phóng đại tương đối đến mức làm kết quả kém tin cậy.
3. **Làm tròn của phép trừ** là vấn đề riêng; đôi khi phép trừ giữa hai số `double` gần nhau được thực hiện chính xác.

Nhận ra khác biệt này giúp chọn đúng biện pháp: chỉnh công thức để tránh làm mất thông tin **trước phép trừ**, thay đổi cách lưu đầu vào, hoặc dùng độ chính xác cao hơn khi thực sự cần.

## 4. ULP và ví dụ mất hẳn phần chênh lệch

**ULP** (*unit in the last place*) là đơn vị khoảng cách giữa các giá trị biểu diễn ở một vùng. Java cung cấp `Math.ulp(float)` và `Math.ulp(double)` để quan sát độ lớn ULP tại giá trị cụ thể.

```java
double x = 1e16;

System.out.println(Math.ulp(x));       // 2.0
System.out.println(x + 1 == x);        // true
System.out.println((x + 1) - x);       // 0.0
System.out.println((x + 2) - x);       // 2.0
```

Ở `1e16`, khoảng cách giữa các số `double` liền kề là `2`. Do đó:

- `x + 1` nằm đúng giữa hai số biểu diễn; quy tắc hòa về phần trị chẵn làm tròn về `x`.
- `x + 2` nằm ở số `double` kế tiếp, nên hiệu là `2`.
- Không có ngoại lệ nào được ném; `0.0` là một kết quả `double` hợp lệ.

Nếu thay `double` bằng `float`, khoảng cách nhảy lên `2` ngay tại `2^24 = 16_777_216`, khiến các số nguyên gần nhau bị nhập thành cùng một giá trị sớm hơn nhiều.

Tránh suy luận rằng `double` có “15–16 chữ số thập phân” thì mọi hiệu của hai số có cỡ 15 chữ số đều có chừng ấy chữ số đáng tin. Độ chính xác đáng tin của **hiệu** còn phụ thuộc vào sai số từng toán hạng và khoảng cách giữa chúng.

## 5. Dạng công thức dễ gặp: hiệu của hai căn bậc hai

Xét biểu thức:

\[
d(x)=\sqrt{x+1}-\sqrt{x},\qquad x\ge 0.
\]

Khi `x` lớn, hai căn rất gần nhau. Nếu tính trực tiếp, sự khác biệt nhỏ có thể bị làm tròn đến 0. Nhân với biểu thức liên hợp:

\[
\begin{aligned}
d(x)
&=\frac{(\sqrt{x+1}-\sqrt{x})(\sqrt{x+1}+\sqrt{x})}
{\sqrt{x+1}+\sqrt{x}}\\
&=\frac{(x+1)-x}{\sqrt{x+1}+\sqrt{x}}\\
&=\boxed{\frac{1}{\sqrt{x+1}+\sqrt{x}}}.
\end{aligned}
\]

Công thức cuối **tránh trừ trực tiếp hai số gần bằng nhau**. Với `x = 1e16`:

```java
double x = 1e16;
double naive = Math.sqrt(x + 1.0) - Math.sqrt(x);
double stable = 1.0 / (Math.sqrt(x + 1.0) + Math.sqrt(x));

System.out.println(naive);  // 0.0
System.out.println(stable); // 5.0E-9
```

Giá trị toán học đúng xấp xỉ `5 × 10^-9`. Công thức liên hợp cho kết quả hợp lý ở đây ngay cả khi `x + 1.0` đã làm tròn thành `x`; mẫu số chủ yếu phụ thuộc vào `sqrt(x)`.

**Giới hạn cần biết:** biến đổi đại số làm phép tính ổn định hơn trong nhiều miền, không bảo đảm tránh mọi overflow/underflow hoặc làm tròn. Khi `x` gần `Double.MAX_VALUE`, riêng `x + 1` có thể vẫn bằng `x`; khi `x` quá lớn, tổng các căn có thể gây vấn đề trong những biến thể công thức khác. Phải xét miền đầu vào và yêu cầu chính xác của bài toán, nhất là với các công thức tổng quát như `sqrt(a) - sqrt(b)`, nơi `(a - b)` cũng có thể đã mất thông tin.

Một trường hợp tổng quát hữu ích, khi mẫu số khác 0:

\[
\sqrt{a}-\sqrt{b}=\frac{a-b}{\sqrt{a}+\sqrt{b}}.
\]

Nếu `a` và `b` đều là số đã làm tròn đến cùng một giá trị thì biến đổi này **không** phục hồi chênh lệch đã bị mất; cần giữ hoặc tính `a-b` theo cách chính xác hơn từ dữ liệu ban đầu.

## 6. Dùng API chuyên dụng: `Math.expm1` và `Math.log1p`

Một số hàm thư viện được thiết kế riêng cho hiệu nhỏ để tránh triệt tiêu chữ số.

### `Math.expm1(x)` thay cho `Math.exp(x) - 1`

Khi `x` gần 0, giá trị `e^x` rất gần `1`. Nếu `Math.exp(x)` được làm tròn thành `1.0`, trừ `1.0` cho `0` dù kết quả toán học gần `x`.

```java
double tiny = 1e-16;

System.out.println(Math.exp(tiny) - 1.0); // 0.0
System.out.println(Math.expm1(tiny));     // 1.0E-16
```

`Math.expm1(x)` được định nghĩa là `e^x - 1` và được triển khai để có độ chính xác cao hơn với `x` gần 0. Trong bài toán tích lũy lãi nhỏ, hàm phân phối xác suất hoặc các phép biến đổi mũ, đây thường là cách thay thế trực tiếp có ý nghĩa.

### `Math.log1p(x)` thay cho `Math.log(1 + x)`

Tương tự, khi `x` quá nhỏ, biểu thức `1.0 + x` có thể được làm tròn thành `1.0` trước khi gọi `Math.log`:

```java
double tiny = 1e-16;

System.out.println(Math.log(1.0 + tiny)); // 0.0
System.out.println(Math.log1p(tiny));     // 1.0E-16
```

`Math.log1p(x)` tính `ln(1 + x)` với độ chính xác tốt hơn gần 0. Miền số thực của `log1p(x)` là `x >= -1` (`x = -1` cho âm vô cực, `x < -1` cho `NaN`). Không thay đổi mù quáng các biểu thức đại số khác thành `log1p` nếu không có cùng ý nghĩa toán học.

Điểm chung: các API này nhận **số chênh nhỏ `x` từ đầu**, không cần dựng giá trị gần `1` rồi trừ hoặc lấy log. Nhờ vậy, phần chênh không bị đánh mất tại bước trung gian.

## 7. Nghiệm phương trình bậc hai: cách tính tránh trừ hai số gần nhau

Xét `a*x^2 + b*x + c = 0` với `a != 0`, biệt thức `D = b*b - 4*a*c >= 0`. Công thức quen thuộc:

\[
x_{1,2}=\frac{-b\pm\sqrt D}{2a}.
\]

Nếu `-b` và `sqrt(D)` gần bằng nhau, một nghiệm có thể bị sai số nghiêm trọng khi dùng dấu trừ. Ví dụ `a = 1`, `b = -10^8`, `c = 1`: nghiệm nhỏ xấp xỉ `10^-8`, còn hai số bị trừ đều cỡ `10^8`.

Một công thức thay thế khi `q != 0`:

\[
q=-\frac12\left(b+\operatorname{copySign}(\sqrt D,b)\right),
\qquad x_1=\frac qa,\quad x_2=\frac cq.
\]

Trong `Math.copySign(magnitude, sign)`, dấu của tham số thứ hai được áp lên độ lớn của tham số thứ nhất. Cách tính `q` chọn phép **cộng hai lượng cùng dấu** để tránh triệt tiêu ở nghiệm lớn; nghiệm còn lại dùng tích hai nghiệm `x1*x2 = c/a`.

Ví dụ minh họa từng phép tính:

```java
double a = 1.0;
double b = -1e8;
double c = 1.0;
double discriminant = b * b - 4 * a * c;
double root = Math.sqrt(discriminant);

double naiveSmall = (-b - root) / (2 * a);
double q = -0.5 * (b + Math.copySign(root, b));
double stableLarge = q / a;
double stableSmall = c / q;

System.out.println(naiveSmall);  // 7.450580596923828E-9
System.out.println(stableSmall); // 1.0E-8
System.out.println(stableLarge); // 1.0E8
```

Hiệu trừ để tính nghiệm nhỏ bằng công thức trực tiếp có sai số đáng kể; dùng `c/q` cho kết quả gần hơn. Đây là ví dụ về **đổi cấu trúc phép toán**, thay vì chỉ tăng kiểu từ `float` sang `double`.

Đây **chưa phải bộ giải phương trình bậc hai hoàn chỉnh**. Trong chương trình thực tế phải xử lý `a == 0`, `D < 0`, `q == 0`, nghiệm kép, số vô cực/`NaN`, overflow/underflow khi tính biệt thức, và miền giá trị rất lớn hoặc rất nhỏ. Không dùng đoạn code minh họa này như bộ giải đầu vào tùy ý.

## 8. Demo Java 17 đầy đủ, chạy được

Lưu chương trình dưới tên `CancellationDemo.java`:

```java
import java.math.BigDecimal;

public class CancellationDemo {
    public static void main(String[] args) {
        double base = 1e16;
        double plusOne = base + 1.0;

        System.out.println("ulp = " + Math.ulp(base));
        System.out.println("plusOne equals base = " + (plusOne == base));
        System.out.println("difference = " + (plusOne - base));

        double x = 1e16;
        double naiveRoot = Math.sqrt(x + 1.0) - Math.sqrt(x);
        double stableRoot = 1.0 / (Math.sqrt(x + 1.0) + Math.sqrt(x));
        System.out.println("sqrt naive = " + naiveRoot);
        System.out.println("sqrt stable = " + stableRoot);

        double tiny = 1e-16;
        System.out.println("exp naive = " + (Math.exp(tiny) - 1.0));
        System.out.println("expm1 = " + Math.expm1(tiny));
        System.out.println("log naive = " + Math.log(1.0 + tiny));
        System.out.println("log1p = " + Math.log1p(tiny));

        BigDecimal preciseA = new BigDecimal("10000000000000001");
        BigDecimal preciseB = new BigDecimal("10000000000000000");
        System.out.println("decimal difference = "
                + preciseA.subtract(preciseB));

        double a = 1.0;
        double b = -1e8;
        double c = 1.0;
        double disc = b * b - 4 * a * c;
        double squareRoot = Math.sqrt(disc);
        double naiveSmall = (-b - squareRoot) / (2 * a);
        double q = -0.5 * (b + Math.copySign(squareRoot, b));
        double stableSmall = c / q;
        System.out.println("quadratic naive small = " + naiveSmall);
        System.out.println("quadratic stable small = " + stableSmall);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac CancellationDemo.java
java CancellationDemo
```

Kết quả:

```text
ulp = 2.0
plusOne equals base = true
difference = 0.0
sqrt naive = 0.0
sqrt stable = 5.0E-9
exp naive = 0.0
expm1 = 1.0E-16
log naive = 0.0
log1p = 1.0E-16
decimal difference = 1
quadratic naive small = 7.450580596923828E-9
quadratic stable small = 1.0E-8
```

Ví dụ dùng `BigDecimal` từ hai chuỗi thập phân **chưa bị làm tròn**. Vì vậy phép trừ `10000000000000001 - 10000000000000000` giữ đúng hiệu `1`. Trái lại, tạo `BigDecimal.valueOf(plusOne)` và `BigDecimal.valueOf(base)` ở đây chỉ nhìn thấy cùng giá trị `double` là `1e16`; lớp `BigDecimal` không thể phục hồi số `+1` đã mất.

Đầu ra của các phép dấu phẩy động trong ví dụ phản ánh hành vi Java với những giá trị đã chọn; khi sửa tham số, kết quả và mức sai số có thể thay đổi.

## 9. Các cách giảm rủi ro triệt tiêu chữ số

### Chuyển đổi công thức trước khi tính

Khi hiệu của hai giá trị gần nhau là mục tiêu, thử tìm một biểu thức toán học tương đương ít phép trừ hơn. Các ví dụ điển hình:

- `sqrt(x+1) - sqrt(x)` → `1 / (sqrt(x+1) + sqrt(x))` với `x >= 0`.
- `exp(x) - 1` → `Math.expm1(x)` khi `x` nhỏ.
- `log(1+x)` → `Math.log1p(x)` khi `x` nhỏ.
- Nghiệm nhỏ của phương trình bậc hai → phương pháp dùng `q` và hệ thức tích hai nghiệm, với các kiểm tra miền hợp lệ.

Mục tiêu là tránh tạo ra rồi trừ hai giá trị đã bị làm tròn thành gần như bằng nhau.

### Giữ biểu diễn chính xác từ nguồn khi nghiệp vụ cần

Nếu đầu vào là decimal chính xác, hãy giữ dạng chuỗi hoặc `BigDecimal` và thực hiện phép tính trong hệ thập phân:

```java
BigDecimal a = new BigDecimal("10000000000000001");
BigDecimal b = new BigDecimal("10000000000000000");
BigDecimal diff = a.subtract(b); // 1
```

Không viết `new BigDecimal(0.1)` với kỳ vọng nó khôi phục số thập phân `0.1` chính xác; constructor nhận `double` chuyển **giá trị nhị phân đã có**. Dùng `new BigDecimal("0.1")` khi dữ liệu nguồn là số thập phân đúng. `BigDecimal.valueOf(double)` thường hữu ích khi muốn biểu diễn thập phân ngắn theo `Double.toString`, nhưng vẫn không thể phục hồi thông tin đã mất do phép tính trước đó.

`BigDecimal` không phải lựa chọn mặc định cho mọi tính toán khoa học: cần cân nhắc hiệu năng, quy tắc chia/làm tròn (`MathContext` khi cần) và tính đúng đắn của mô hình số.

### Chọn độ chính xác phù hợp

`double` thường giảm rủi ro so với `float` vì có 53 bit phần trị so với 24 bit. Tuy nhiên, `double` **không** tự chữa được các biểu thức nhạy cảm. Nếu kết quả cần phân biệt các số nguyên lớn liên tiếp, dùng `long` hoặc `BigInteger` thay vì lưu chúng trong `double`; nếu dữ liệu decimal cần chính xác, cân nhắc `BigDecimal` từ nguồn chính xác.

### Đánh giá sai số bằng dữ liệu kiểm thử có chủ đích

Nên kiểm tra các đầu vào:

- Hai toán hạng bằng nhau hoặc chỉ khác nhau khoảng một ULP.
- Hai toán hạng rất lớn nhưng hiệu mong đợi rất nhỏ.
- Giá trị ở gần 0, giá trị âm, `+0.0`/`-0.0`, và biên có thể gây overflow/underflow.
- Trường hợp có nghiệm gần bằng 0 trong công thức bậc hai hoặc hiệu của các căn.
- Một bộ giá trị tham chiếu có độ chính xác cao hơn (chẳng hạn `BigDecimal` từ chuỗi, tính số học ký hiệu hoặc phần mềm chuyên dụng), khi việc so sánh là có ý nghĩa.

So sánh với mốc tham chiếu có thể dùng sai số tuyệt đối `|computed - expected|` và sai số tương đối `|computed - expected|/|expected|` khi `expected != 0`. Nếu giá trị đúng gần hoặc bằng 0, chỉ dùng sai số tương đối có thể gây hiểu nhầm; nên kết hợp ngưỡng tuyệt đối dựa trên đơn vị nghiệp vụ.

### Đừng dùng biện pháp không giải quyết gốc vấn đề

- **`Math.abs(a - b) < epsilon` chỉ kiểm tra gần bằng nhau**, không phục hồi một hiệu đã mất độ chính xác. Một ngưỡng `epsilon` cố định cũng có thể vô nghĩa ở các thang số rất khác nhau.
- **Định dạng thêm chữ số khi in** (`printf`, `DecimalFormat`) không tạo lại chữ số đã mất.
- **Ép kiểu rồi ép ngược** không khôi phục thông tin bị bỏ khi chuyển `long` sang `double` hay khi cộng `1` vào một `double` quá lớn.
- **Kahan summation** có thể giảm sai số khi cộng dồn nhiều số, nhưng không sửa được hai toán hạng vốn đã trùng nhau trước phép trừ. Đây là bài toán khác.
- **Dùng `BigDecimal` sau khi đã tính sai bằng `double`** chỉ chuyển giá trị sai sang một biểu diễn khác, không tự tái tạo dữ liệu gốc.

## 10. Bài tập và đáp án

**Bài 1.** Giải thích tại sao chương trình sau in `true`:

```java
double n = 1e16;
System.out.println(n == n + 1.0);
```

**Đáp án:** `Math.ulp(1e16) == 2.0`. Khoảng cách giữa hai số `double` đại diện được là `2` ở vùng này; `n + 1` nằm đúng giữa hai giá trị, và quy tắc hòa về chẵn đưa kết quả về `n`.

**Bài 2.** Hai cách tính `sqrt(1e16+1) - sqrt(1e16)` trực tiếp và qua liên hợp cho kết quả nào?

**Đáp án:** Trực tiếp: `0.0`. Qua công thức `1 / (sqrt(1e16+1) + sqrt(1e16))`: `5.0E-9` trong Java với các giá trị đã chọn. Trong số học thực, giá trị đúng gần `5 × 10^-9`.

**Bài 3.** `Math.exp(1e-16) - 1` có thể thành `0.0`. Cần dùng hàm nào nếu mục tiêu là `e^x - 1` với `x` rất nhỏ?

**Đáp án:** `Math.expm1(x)`. Tương tự, với `ln(1+x)` và `x` nhỏ, dùng `Math.log1p(x)`.

**Bài 4.** “Trừ hai `double` rất gần nhau luôn làm mất chữ số trong chính phép trừ.” Đúng hay sai?

**Đáp án:** Sai. Bổ đề Sterbenz cho thấy nhiều phép trừ của hai giá trị floating đã đại diện được và đủ gần nhau được thực hiện chính xác. Sai số nghiêm trọng thường do **hai toán hạng đã gần đúng** hoặc do một công thức khiến sai số tương đối của hiệu tăng mạnh.

**Bài 5.** Vì sao `BigDecimal.valueOf(base + 1.0).subtract(BigDecimal.valueOf(base))` không trả `1` với `base = 1e16`?

**Đáp án:** Phép cộng `base + 1.0` đã được làm tròn thành `base` ở kiểu `double` trước khi gọi `BigDecimal.valueOf`; phép trừ chính xác của hai giá trị bằng nhau cho `0`.

**Bài 6.** Một người muốn đo chênh lệch của hai phép đo `1000000.001` và `1000000.000`. Nên chú ý điều gì?

**Đáp án:** Mức chính xác của từng phép đo và cách lưu đầu vào quyết định hiệu `0.001` đáng tin đến đâu. Cần biết đơn vị, độ phân giải đo, sai số thiết bị và yêu cầu nghiệp vụ; phép trừ trong `double` không thể làm hiệu chính xác hơn thông tin nguồn. Nếu đầu vào là decimal cần giữ nguyên các chữ số đã công bố, có thể dùng `BigDecimal` từ chuỗi.

**Ghi nhớ:** Triệt tiêu chữ số khiến hiệu của hai số gần nhau đặc biệt nhạy với sai số của từng toán hạng. Hãy kiểm tra nguồn sai số, quan sát ULP, ưu tiên công thức ổn định (`expm1`, `log1p`, liên hợp, phương pháp tính nghiệm thích hợp), và giữ dữ liệu ở dạng chính xác từ trước khi thông tin bị làm tròn mất.