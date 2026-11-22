# Math.fma và sự khác biệt với nhân rồi cộng trong Java

**`Math.fma(a, b, c)`** tính phép **fused multiply-add** (FMA): lấy tích `a × b`, cộng `c`, sau đó **làm tròn kết quả cuối cùng một lần** sang `float` hoặc `double`. Trái lại, biểu thức Java thông thường **`a * b + c`** thực hiện **phép nhân có làm tròn trước**, rồi mới cộng và **làm tròn thêm lần nữa**.

Đây không chỉ là khác biệt cú pháp hay hiệu năng. Khi các chữ số thấp của tích bị mất và phép cộng tiếp theo hủy bỏ gần hết phần lớn của tích, hai cách tính có thể trả **hai kết quả số học khác nhau**. FMA đôi khi còn tránh việc **phép nhân trung gian overflow hoặc underflow** dù kết quả toán học của cả biểu thức vẫn biểu diễn được.

```java
double a = 1.0 + 0x1.0p-27;
double b = 1.0 - 0x1.0p-27;

double separate = a * b - 1.0;      // +0.0
double fused = Math.fma(a, b, -1.0); // -2^-54, khác 0
```

Các khai báo trên là **mảnh mã** có thể đặt trong phương thức Java. Bài học này giải thích nguyên nhân của khác biệt, cách dùng API Java 17+, trường hợp biên và giới hạn của việc dùng FMA để cải thiện độ chính xác.

## 1. Bối cảnh: phép tính dấu phẩy động luôn có bước làm tròn

Java cung cấp hai kiểu dấu phẩy động nhị phân thường dùng:

| Kiểu | Tổng bit | Độ chính xác phần trị (significand) | Số mũ | Đặc điểm |
| --- | ---: | ---: | --- | --- |
| `float` | 32 | 24 bit hiệu dụng | Phạm vi hẹp hơn | Nhanh/gọn hơn về lưu trữ; lưới số thưa hơn |
| `double` | 64 | 53 bit hiệu dụng | Phạm vi rộng hơn | Thường là lựa chọn mặc định cho tính toán dấu phẩy động |

Với một số thực toán học, không phải mọi chữ số đều có thể lưu trong `float` hay `double`. Phép toán cần chọn **số biểu diễn được gần nhất**, thông thường theo quy tắc **gần nhất; khi đúng giữa hai số thì chọn phần trị chẵn** (*round to nearest, ties to even*).

Một cách ký hiệu kết quả làm tròn về đúng kiểu là `round(x)`. Với các toán hạng hữu hạn và không gặp ngoại lệ đặc biệt:

```text
Nhân rồi cộng:
intermediate = round(a × b)
result       = round(intermediate + c)

Fused multiply-add:
result       = round((a × b) + c)
               ↑ tích và tổng được xét ở độ chính xác toán học
                 trước khi làm tròn một lần
```

FMA không có nghĩa Java cất một `double` với vô hạn bit; nó có nghĩa **phép nhân trung gian không bị làm tròn độc lập trước phép cộng**. Kết quả trả về vẫn là một `float` hoặc `double` hữu hạn độ chính xác, hoặc một giá trị đặc biệt theo quy tắc IEEE 754.

Đặc biệt, các toán hạng truyền vào hàm có thể **đã bị làm tròn từ trước** khi được tạo ra. FMA chỉ giúp kết hợp phép `a*b+c` đối với **các giá trị đầu vào hiện có**, không khôi phục thông tin đã mất trong bước tính `a`, `b` hay `c` trước đó.

## 2. API `Math.fma` và kiểu kết quả

Java có hai overload chính:

```java
static double Math.fma(double a, double b, double c)
static float  Math.fma(float a, float b, float c)
```

Đây là **chữ ký phương thức**, không phải một chương trình độc lập. Với mọi đối số `double`, phương thức trả `double`; với toàn bộ đối số `float`, có overload trả `float`.

```java
double d = Math.fma(2.0, 3.0, 4.0);  // 10.0
float f = Math.fma(2.0f, 3.0f, 4.0f); // 10.0f
```

Khi trộn `float` với `double`, Java có thể chọn overload `double` vì một số đối số cần được nâng kiểu. Do vậy nên **chọn kiểu toán hạng có chủ đích**. Ví dụ `Math.fma(1.0f, 2.0f, 3.0)` trả `double`, còn `Math.fma(1.0f, 2.0f, 3.0f)` trả `float`.

Trong Java 17 trở lên, ngữ nghĩa dấu phẩy động được quy định nhất quán; một biểu thức Java `a * b + c` thông thường **không được tự coi như FMA nếu việc thay thế làm thay đổi kết quả bắt buộc**. Hãy dùng `Math.fma` tường minh khi bạn muốn phép toán fused một lần làm tròn.

## 3. Ví dụ chính: sai số phép nhân bị lộ ra sau khi trừ 1

Đặt:

```text
a = 1 + 2^-27
b = 1 - 2^-27
c = -1
```

Các số `a` và `b` biểu diễn **chính xác** bằng `double`. Tích toán học là:

```text
a × b = (1 + 2^-27)(1 - 2^-27)
      = 1 - 2^-54

a × b + c = (1 - 2^-54) - 1
          = -2^-54
```

**Cách tính thông thường:**

```java
double a = 1.0 + 0x1.0p-27;
double b = 1.0 - 0x1.0p-27;
double separate = a * b - 1.0;
```

Quanh `1.0`, số `double` biểu diễn được ngay phía dưới là `1 - 2^-53`. Giá trị `1 - 2^-54` nằm **gần `1.0` hơn** giá trị phía dưới đó, nên phép nhân được làm tròn thành chính xác `1.0`. Sau khi trừ `1.0`, `separate` là **`+0.0`**: phần dư nhỏ nhưng có thật đã bị mất trong bước nhân.

**Cách tính fused:**

```java
double fused = Math.fma(a, b, -1.0);
```

FMA tính tích và phép trừ dưới dạng một phép toán kết hợp trước khi làm tròn:

```text
round((1 - 2^-54) - 1) = round(-2^-54) = -2^-54
```

Vì `-2^-54` cũng là một số `double` biểu diễn được, FMA giữ chính xác kết quả ấy. Khi in bằng dạng hex floating-point:

```text
separate = 0x0.0p0
fused    = -0x1.0p-54
```

**Điểm mấu chốt:** chênh lệch không đến từ việc gọi hàm thay vì toán tử; nó đến từ **số lần và thời điểm làm tròn**. Cả hai phép tính nhận **cùng ba giá trị đầu vào** nhưng cách tính trung gian khác nhau.

## 4. Vì sao ví dụ này liên quan đến ULP?

**ULP (Unit in the Last Place)** biểu diễn kích cỡ một bước của lưới giá trị dấu phẩy động quanh một độ lớn. Với `double`, `Math.ulp(1.0)` là `2^-52`, nhưng **khoảng cách từ `1.0` xuống số kề dưới** là `2^-53`, vì `1.0` là ranh giới lũy thừa 2.

Trong ví dụ:

- Tích thực `1 - 2^-54` cách `1.0` đúng `2^-54`.
- Bước đến số `double` ngay dưới `1.0` là `2^-53`.
- Khoảng sai lệch `2^-54` là **nửa khoảng ở phía dưới**, nên ở điểm chính giữa, quy tắc *ties to even* chọn `1.0` thay vì số kề dưới (bit phần trị cuối của `1.0` là chẵn).
- Nhân rồi cộng làm mất phần chênh ấy; `Math.fma` giữ phần chênh đến lúc cuối mới làm tròn.

Vì vậy, các biểu thức kiểu `a*b + c` có **cancellation** (tích gần bằng `-c`) là nơi sự khác nhau về độ chính xác thể hiện rõ. Không có bảo đảm FMA làm sai số tuyệt đối của **toàn bộ thuật toán** nhỏ nhất; nó chỉ tính đúng phép fused với một lần làm tròn cuối cùng.

## 5. Cùng hiện tượng ở `float`

`float` có 24 bit significand hiệu dụng, ít hơn `double`. Chọn:

```java
float a = 1.0f + 0x1.0p-13f;
float b = 1.0f - 0x1.0p-13f;

float separate = a * b - 1.0f;      // +0.0f
float fused = Math.fma(a, b, -1.0f); // -2^-26f
```

Tích chính xác là `1 - 2^-26`; phép nhân kiểu `float` thông thường làm tròn thành `1.0f`, sau đó trừ `1.0f` cho 0. FMA trả `-2^-26f`, và hai giá trị được in như sau:

```text
floatSeparate=0x0.0p0
floatFused=-0x1.0p-26
```

Ví dụ này cho thấy cả **overload float** cũng có ý nghĩa fused, không chỉ `double`. Hãy thêm hậu tố `f` cho literal khi muốn duy trì phép tính và kiểu đầu ra `float`. Nếu vô tình dùng literal `double` như `1.0` hoặc `-1.0` trong biểu thức, kết quả có thể được tính ở kiểu khác do quy tắc nâng kiểu và overload.

## 6. Khi phép nhân riêng lẻ overflow nhưng FMA vẫn trả số hữu hạn

Có các phép `a*b+c` mà tích riêng lẻ vượt `Double.MAX_VALUE`, nhưng phép cộng với `c` **triệt tiêu phần vượt giới hạn** trước khi kết quả cuối được làm tròn.

```java
double max = Double.MAX_VALUE;
double separate = max * 2.0 - max;       // +Infinity
double fused = Math.fma(max, 2.0, -max); // Double.MAX_VALUE
```

Giải thích:

- Với phép nhân độc lập, `max * 2.0` vượt dải hữu hạn của `double`, nên được làm tròn thành `+Infinity`.
- Sau đó `+Infinity - max` vẫn là `+Infinity`; thông tin về tích hữu hạn thực đã mất.
- FMA xét biểu thức toán học `max × 2 - max = max` **trước bước làm tròn cuối**. Kết quả `max` vẫn là `double` hữu hạn, nên trả đúng `Double.MAX_VALUE`.

Đây là trường hợp mà khác biệt không chỉ vài bit cuối mà là **Infinity so với một giá trị hữu hạn rất lớn**. Cần phân biệt đầu vào `max` hữu hạn với đầu vào **đã là Infinity**: nếu truyền `Double.POSITIVE_INFINITY` từ trước, FMA không “khôi phục” nó thành `max`.

## 7. Khi tích riêng lẻ underflow và làm mất phần đóng góp nhỏ

Ngược lại, xét số dương subnormal nhỏ nhất:

```java
double tiny = Double.MIN_VALUE; // 2^-1074
double separate = tiny * 0.5 + tiny;
double fused = Math.fma(tiny, 0.5, tiny);
```

- Tích toán học `tiny × 0.5 = 2^-1075` nhỏ hơn bước subnormal nhỏ nhất. Làm tròn phép nhân riêng lẻ thành **`0.0`** (điểm hòa được giải theo *ties to even*).
- Sau đó `0.0 + tiny = tiny`, nên kết quả `separate` bằng **1 đơn vị** `Double.MIN_VALUE`.
- FMA giữ tích nhỏ cho tới khi cộng: `2^-1075 + 2^-1074 = 1.5 × 2^-1074`. Khi làm tròn cuối, kết quả thành **2 đơn vị** `Double.MIN_VALUE` (điểm hòa chọn phần trị chẵn).

Do đó:

```text
separate / Double.MIN_VALUE = 1.0
fused / Double.MIN_VALUE    = 2.0
```

Ví dụ chứng minh việc làm tròn một lần có thể quan trọng ngay tại miền **subnormal/underflow**, không chỉ ở giá trị gần 1 hay khi phép nhân bị overflow.

## 8. Chương trình Java 17+ hoàn chỉnh và kết quả đã kiểm thử

Tạo tệp **`FmaDemo.java`**:

```java
public class FmaDemo {
    public static void main(String[] args) {
        double a = 1.0 + 0x1.0p-27;
        double b = 1.0 - 0x1.0p-27;
        double separate = a * b - 1.0;
        double fused = Math.fma(a, b, -1.0);

        System.out.println("a=" + Double.toHexString(a));
        System.out.println("b=" + Double.toHexString(b));
        System.out.println("separate=" + Double.toHexString(separate));
        System.out.println("fused=" + Double.toHexString(fused));
        System.out.println("fusedExact=" + (fused == -0x1.0p-54));
        System.out.println("plainExample=" + Math.fma(2.0, 3.0, 4.0));

        float fa = 1.0f + 0x1.0p-13f;
        float fb = 1.0f - 0x1.0p-13f;
        System.out.println("floatSeparate=" + Float.toHexString(fa * fb - 1.0f));
        System.out.println("floatFused=" + Float.toHexString(Math.fma(fa, fb, -1.0f)));

        double max = Double.MAX_VALUE;
        System.out.println("separateOverflow=" + (max * 2.0 - max));
        System.out.println("fusedAvoidsOverflow=" + (Math.fma(max, 2.0, -max) == max));

        double tiny = Double.MIN_VALUE;
        double separateUnderflow = tiny * 0.5 + tiny;
        double fusedUnderflow = Math.fma(tiny, 0.5, tiny);
        System.out.println("separateUnderflowUnits=" + (separateUnderflow / tiny));
        System.out.println("fusedUnderflowUnits=" + (fusedUnderflow / tiny));

        System.out.println("nanProduct=" + Double.isNaN(Math.fma(Double.POSITIVE_INFINITY, 0.0, 1.0)));
        System.out.println("nanOppositeInfinities=" + Double.isNaN(
                Math.fma(Double.POSITIVE_INFINITY, 2.0, Double.NEGATIVE_INFINITY)));
        System.out.println("nanOperand=" + Double.isNaN(Math.fma(Double.NaN, 1.0, 2.0)));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac --release 17 -encoding UTF-8 FmaDemo.java
java FmaDemo
```

Stdout chính xác:

```text
a=0x1.0000002p0
b=0x1.ffffffcp-1
separate=0x0.0p0
fused=-0x1.0p-54
fusedExact=true
plainExample=10.0
floatSeparate=0x0.0p0
floatFused=-0x1.0p-26
separateOverflow=Infinity
fusedAvoidsOverflow=true
separateUnderflowUnits=1.0
fusedUnderflowUnits=2.0
nanProduct=true
nanOppositeInfinities=true
nanOperand=true
```

Nhìn vào từng nhóm dòng:

1. `separate=0x0.0p0` và `fused=-0x1.0p-54`: hai phép tính nhận cùng đầu vào nhưng giữ lượng thông tin khác nhau. `fusedExact=true` xác minh phần dư `-2^-54`.
2. `plainExample=10.0`: nếu phép nhân/cộng đều biểu diễn chính xác thì không nhất thiết có khác biệt; `2×3+4` là phép tính đơn giản cho cùng kết quả.
3. `floatSeparate` so với `floatFused`: kiểm chứng overload `float`.
4. `separateOverflow=Infinity`, `fusedAvoidsOverflow=true`: FMA tránh overflow trung gian trong ví dụ cụ thể.
5. `separateUnderflowUnits=1.0`, `fusedUnderflowUnits=2.0`: FMA giữ phần đóng góp rất nhỏ đến bước làm tròn cuối.
6. Ba kết quả `nan...=true`: kiểm tra các quy tắc đặc biệt với `NaN` và vô cực.

Sử dụng `Double.toHexString` và `Float.toHexString` giúp thể hiện chính xác dạng mũ nhị phân của kết quả, tránh việc chỉ nhìn chuỗi thập phân ngắn rồi nhầm `0.0` với một số khác rất nhỏ.

## 9. `NaN`, vô cực, dấu zero và quy tắc trường hợp đặc biệt

Giống các phép toán dấu phẩy động khác, `Math.fma` không thể bỏ qua các giá trị IEEE 754 đặc biệt:

| Tình huống | Kết quả |
| --- | --- |
| Một toán hạng là `NaN` | Kết quả `NaN` |
| `a` hoặc `b` là vô cực, toán hạng kia là zero | `NaN`: tích `0 × ∞` không hợp lệ |
| Tích vô cực và `c` vô cực có dấu ngược | `NaN`: hai lượng vô cực đối nhau |
| Cả ba toán hạng hữu hạn nhưng kết quả toán học vượt kiểu đích | Có thể trả `+Infinity` hoặc `-Infinity` sau làm tròn cuối |
| Kết quả quá nhỏ để thành số subnormal khác 0 | Có thể làm tròn về `+0.0` hoặc `-0.0` |
| Tích trung gian lớn nhưng tổng cuối vẫn hữu hạn | FMA có thể trả số hữu hạn, không bắt buộc overflow như phép nhân riêng |

Ví dụ:

```java
boolean invalid1 = Double.isNaN(
        Math.fma(Double.POSITIVE_INFINITY, 0.0, 1.0)); // true
boolean invalid2 = Double.isNaN(
        Math.fma(Double.POSITIVE_INFINITY, 2.0, Double.NEGATIVE_INFINITY)); // true
```

Các dòng trên là mã minh họa, có thể đặt vào phương thức. Đây là tính chất của toán học dấu phẩy động IEEE 754, **không phải `ArithmeticException`**. Để kiểm tra kết quả, dùng `Double.isFinite`, `Double.isNaN`, `Double.isInfinite` (hoặc API tương ứng của `Float`).

IEEE 754 có cả `+0.0` và `-0.0`. Dấu của một kết quả zero có thể có ý nghĩa trong tính toán (ví dụ phép chia cho zero), mặc dù `+0.0 == -0.0` là `true`. Khi làm việc với zero và phép toán fused, không chỉ so sánh `== 0.0` nếu yêu cầu phân biệt mẫu bit dấu; có thể xem `Double.doubleToRawLongBits`.

## 10. FMA giúp được gì và không giúp được gì?

**Ưu điểm trực tiếp:** với cùng đầu vào đã được biểu diễn trong kiểu đích, FMA loại bỏ phép **làm tròn trung gian giữa nhân và cộng**, nên trả kết quả của `round(a*b+c)` với một bước làm tròn cuối theo quy tắc của API. Điều này đặc biệt có ích trong:

- **Tích lũy tích vô hướng:** `sum = Math.fma(x[i], y[i], sum)` kết hợp nhân và cộng ở mỗi bước, giảm một điểm làm tròn so với `sum += x[i] * y[i]`.
- **Đánh giá đa thức:** bước Horner `value = Math.fma(value, x, coefficient)` khi thích hợp, giảm làm tròn trung gian.
- **Một số bộ lọc số, tính toán hình học và thuật toán numerical linear algebra**, khi độ chính xác gần máy quan trọng và phân tích số cho thấy việc dùng FMA có lợi.

**Giới hạn bắt buộc nhớ:**

1. FMA **không làm mọi số thực trở nên biểu diễn chính xác**. Ví dụ `0.1` vẫn không được lưu hoàn toàn chính xác bằng `double`.
2. Nếu `a`, `b`, `c` đã bị làm tròn hoặc sai từ trước, FMA không thể khôi phục dữ liệu ban đầu.
3. Chuỗi nhiều phép FMA vẫn **làm tròn sau mỗi lời gọi FMA**; không phải toàn bộ vòng lặp được thực hiện bằng độ chính xác vô hạn.
4. Kết quả FMA có thể khác kết quả biểu thức cũ theo một hoặc nhiều bit. Đây là khác biệt tính toán có chủ đích; khi đổi mã sản xuất, cần xác nhận việc thay đổi đáp ứng **hợp đồng kết quả và các bài kiểm thử**, đặc biệt nơi tính tái lập bit là yêu cầu.
5. FMA **không có nghĩa trả số chính xác tuyệt đối cho mọi bài toán** hoặc loại bỏ các vấn đề mất ổn định số, điều kiện bài toán kém hay cancellation ở các bước khác.

Về hiệu năng, một số CPU có chỉ thị FMA và JVM có thể tận dụng; nhưng **không nên coi `Math.fma` luôn nhanh hơn** phép nhân/cộng trong mọi môi trường. JVM, kiến trúc, khả năng tối ưu và tải công việc đều ảnh hưởng. Cân nhắc benchmark như JMH khi hiệu năng là mục tiêu chính, và ưu tiên lựa chọn FMA theo **ngữ nghĩa số học** trước.

## 11. Ví dụ ứng dụng: dot product và Horner

### Tích vô hướng

Một thuật toán thường tính:

```java
// Giả sử x và y là hai mảng double có cùng chiều dài.
double sum = 0.0;
for (int i = 0; i < x.length; i++) {
    sum = Math.fma(x[i], y[i], sum);
}
```

Đoạn này là **mảnh code** cần đặt trong phương thức có sẵn mảng `x`, `y`. Mỗi bước tính tích một phần tử `x[i] * y[i]` cộng vào `sum`, rồi làm tròn một lần. So với `sum += x[i] * y[i]`, nó loại bỏ một bước làm tròn của tích tại từng vòng.

Tuy nhiên, thứ tự các số hạng vẫn có thể ảnh hưởng; khi các giá trị khác bậc độ lớn hoặc có hủy triệt tiêu mạnh, một phương pháp cộng bù (Kahan/Neumaier), chia nhóm hoặc thuật toán số khác có thể cần thiết. Dùng FMA **không tự bảo đảm** kết quả chính xác hoặc độc lập thứ tự phép cộng.

### Đánh giá đa thức theo Horner

Với `p(x) = a*x*x + b*x + c`, cách Horner là `(a*x + b)*x + c`. Nếu thuật toán muốn dùng FMA tại mỗi bước:

```java
double result = Math.fma(Math.fma(a, x, b), x, c);
```

Đây là **mảnh mã** khi `a`, `b`, `c`, `x` là các biến `double` đã có. Mỗi lời gọi FMA chỉ làm tròn một lần. Kết quả có thể khác `a*x*x + b*x + c` vì **cả cấu trúc đánh giá lẫn số lần làm tròn** đã thay đổi; với bài toán cần kết quả tham chiếu, hãy chọn thứ tự phép tính rõ ràng và kiểm chứng sai số.

## 12. Khi nào không nên thay `a*b+c` thành `Math.fma(a,b,c)`?

Có thể không phù hợp nếu:

- **Yêu cầu tương thích kết quả bit-for-bit** với chương trình từng sử dụng hai phép toán làm tròn riêng. Đổi sang FMA có thể là thay đổi hành vi, dù đôi khi chính xác hơn.
- **Muốn quan sát hoặc kiểm tra tích trung gian** (`product`) như một kết quả có ý nghĩa riêng; FMA chỉ trả kết quả tổng, không lộ tích đã làm tròn.
- **Phép toán thuộc hệ số nguyên, decimal exact hoặc tiền tệ**. `Math.fma` là API cho `float` và `double`, không phải `BigDecimal`, không loại bỏ sai số nhị phân của số thập phân; với tài chính có thể cần `BigDecimal` và chính sách `MathContext`/rounding rõ ràng.
- **Biên `NaN`, Infinity, zero** có ngữ nghĩa nghiệp vụ cần xử lý tường minh. FMA có quy tắc đặc biệt và không tự “sửa” dữ liệu không hợp lệ.
- **Hiệu năng là lý do duy nhất** nhưng chưa có benchmark trên nền tảng mục tiêu. Tập trung lựa chọn dựa trên độ chính xác và phép đo thực tế.

Ngược lại, nếu yêu cầu phép toán fused đúng đặc tả và muốn giảm làm tròn trung gian, `Math.fma` là API thể hiện ý định rõ nhất trong Java.

## 13. Những lỗi và nhầm lẫn thường gặp

| Nhầm lẫn | Sự thật | Cách xử lý |
| --- | --- | --- |
| `Math.fma(a,b,c)` luôn bằng `a*b+c` | Hai bước làm tròn so với một bước có thể khác nhau | Kiểm thử ví dụ cancellation và các biên |
| FMA “làm tròn tích chính xác hơn” rồi mới cộng | FMA **không làm tròn tích riêng** | Hiểu công thức `round((a×b)+c)` |
| FMA luôn giảm sai số của cả chương trình | Chỉ bảo đảm ngữ nghĩa của **một phép fused** | Phân tích sai số cả thuật toán |
| Dùng `double` thì không còn cancellation | `double` vẫn có số bit fraction hữu hạn | Xem ví dụ `-2^-54` |
| Tràn khi `a*b` nghĩa FMA cũng phải trả Infinity | Nếu `a*b+c` cuối cùng hữu hạn, FMA có thể trả hữu hạn | `Math.fma(MAX,2,-MAX)` |
| Underflow ở tích nhỏ không quan trọng | Sau khi cộng, phần đóng góp có thể thay đổi việc làm tròn | Thử `Double.MIN_VALUE` |
| `Math.fma` dùng được cho `BigDecimal` | API chỉ có overload dấu phẩy động | Dùng phương thức `BigDecimal.multiply/add` theo yêu cầu |
| `Math.fma` biến literal `0.1` thành chính xác | Literal đã làm tròn khi trở thành `double` | Chọn biểu diễn decimal chính xác nếu cần |
| Thay toàn bộ `a*b+c` là tối ưu hiển nhiên | Có thể đổi bit kết quả; hiệu năng không bất biến | Kiểm thử tính đúng và benchmark |
| Một kết quả `NaN` nghĩa Java ném lỗi | IEEE 754 có thể trả `NaN` mà không có exception | Dùng `Double.isNaN`/isFinite |

## 14. Tự kiểm tra

1. **`Math.fma(a,b,c)` khác `a*b+c` ở đâu?** FMA cộng tích chính xác với `c` rồi làm tròn **một lần**; biểu thức thường làm tròn sau nhân và sau cộng.
2. **Với `a=1+2^-27`, `b=1-2^-27`, `c=-1`, kết quả fused là gì?** `-2^-54`. Nhân rồi cộng cho `0.0` vì mất phần chênh ở bước nhân.
3. **FMA có thể giúp khi phép nhân riêng overflow không?** Có trong một số trường hợp, ví dụ `Math.fma(Double.MAX_VALUE,2.0,-Double.MAX_VALUE)` trả `Double.MAX_VALUE` hữu hạn.
4. **FMA có thể tạo kết quả khác ở miền subnormal không?** Có, vì tích rất nhỏ có thể chỉ đóng góp đủ để đổi lựa chọn làm tròn sau khi cộng.
5. **Khi nào `Math.fma` vẫn trả `NaN`?** Ví dụ khi một đối số là `NaN`, khi nhân vô cực với 0, hoặc khi tích vô cực bị cộng với vô cực trái dấu.
6. **Nếu `a` đã bị làm tròn từ một số thực nhập vào thì FMA có lấy lại giá trị thực gốc không?** Không. Nó chỉ xử lý chính xác phép fused trên những toán hạng hiện có.
7. **Đối số đều là `float`, kiểu trả về là gì?** `float` khi overload `Math.fma(float,float,float)` được chọn. Có `double` trong lời gọi thì overload `double` có thể được chọn.
8. **FMA có nên thay mọi phép tính tiền bằng `double` không?** Không. Yêu cầu thập phân chính xác và chính sách làm tròn cần cách biểu diễn phù hợp, thường là `BigDecimal`.
9. **FMA có làm toàn bộ vòng lặp dot product tính bằng vô hạn độ chính xác không?** Không. Mỗi lời gọi FMA vẫn làm tròn kết quả một lần, vòng lặp vẫn có thể tích lũy sai số.

**Ghi nhớ:** `Math.fma(a,b,c)` biểu diễn **fused multiply-add**, tức **một bước làm tròn cuối sau khi nhân và cộng**. Với dữ liệu nhạy ở phần bit thấp hoặc cancellation, kết quả có thể khác hoàn toàn biểu thức `a*b+c` gồm hai bước làm tròn. Dùng FMA để kiểm soát ngữ nghĩa và đôi khi cải thiện độ chính xác, nhưng luôn kiểm tra đầu vào, trường hợp biên và yêu cầu kết quả của ứng dụng.
