# Ngữ nghĩa số thực luôn nghiêm ngặt từ Java 17

## 1. Vì sao Java 17 nhấn mạnh lại ngữ nghĩa số thực?

Java có hai kiểu số thực nguyên thủy:

- `float`: biểu diễn số thực dấu phẩy động độ chính xác đơn, thường được gọi là binary32.
- `double`: biểu diễn số thực dấu phẩy động độ chính xác kép, thường được gọi là binary64.

Các phép toán trên `float` và `double` tuân theo quy tắc số học dấu phẩy động của Java và IEEE 754. Tuy nhiên, trong một giai đoạn lịch sử của Java, ngôn ngữ cho phép **một số biểu thức dấu phẩy động không strict** sử dụng tập giá trị trung gian có phạm vi số mũ mở rộng trên những nền tảng có phần cứng hỗ trợ. Điều này có thể khiến cùng một chuỗi phép toán cho kết quả trung gian khác nhau giữa các nền tảng.

Từ **Java 17**, ngữ nghĩa số thực luôn nghiêm ngặt (*always-strict floating-point semantics*) được áp dụng cho mọi biểu thức dấu phẩy động. Thay đổi này được mô tả trong **JEP 306 — Restore Always-Strict Floating-Point Semantics**.

Điều cần hiểu chính xác:

- Java 17 làm cho các phép toán dấu phẩy động cơ bản có quy tắc đánh giá nhất quán, không phụ thuộc việc một phương thức/lớp có khai báo `strictfp` hay không.
- Những kết quả trung gian được đánh giá theo tập giá trị `float` hoặc `double` tương ứng, thay vì dùng tập giá trị có phạm vi số mũ mở rộng như một số trường hợp lịch sử.
- Thay đổi này **không biến số thực thành số thập phân chính xác tuyệt đối**.
- Sai số biểu diễn, làm tròn, overflow, underflow, `NaN`, vô cực và signed zero vẫn tồn tại.
- Những hàm toán học như `Math.sin()`, `Math.log()` có hợp đồng riêng; không nên suy ra rằng JEP 306 làm mọi hàm thư viện cho kết quả bit-for-bit giống nhau trên mọi nền tảng.

Đây là kiến thức quan trọng khi đọc code cũ, nâng cấp JDK, thiết kế phép tính khoa học/tài chính và phân tích khác biệt kết quả giữa các môi trường.

## 2. Số dấu phẩy động trong Java: `float` và `double`

### 2.1. Hai kiểu số thực nguyên thủy

| Kiểu | Định dạng IEEE 754 | Độ rộng | Độ chính xác significand | Sử dụng thường gặp |
|---|---|---:|---:|---|
| `float` | binary32 | 32 bit | 24 bit, tính cả bit ẩn đối với số chuẩn hóa | Dữ liệu đồ họa, dữ liệu số lượng lớn cần tiết kiệm bộ nhớ, giao thức yêu cầu float |
| `double` | binary64 | 64 bit | 53 bit, tính cả bit ẩn đối với số chuẩn hóa | Tính toán số thực thông thường, mô phỏng, đo lường |

Một literal số thực không có hậu tố thường có kiểu `double`. Muốn chỉ rõ `float`, thêm hậu tố `f` hoặc `F`:

~~~java
float ratio = 0.25f;
double distance = 12.75;
double scientific = 6.022e23;
~~~

Nếu viết:

~~~java
float ratio = 0.25; // Không hợp lệ nếu không ép kiểu hoặc thêm hậu tố f
~~~

thì literal `0.25` có kiểu `double`, không tự động thu hẹp sang `float`. Hãy viết `0.25f` hoặc ép kiểu có chủ đích.

### 2.2. Cấu trúc IEEE 754 ở mức khái niệm

Một giá trị binary32 hoặc binary64 gồm các phần:

- **Sign bit:** dấu của số.
- **Exponent:** số mũ được mã hóa theo dạng lệch (biased exponent).
- **Fraction/significand:** các bit có ý nghĩa của phần trị.

Số chuẩn hóa thường được hiểu theo dạng:

\[
x = (-1)^s \times 1.f \times 2^{e-bias}
\]

Trong đó `s` là bit dấu, `f` là phần fraction và `e` là exponent đã mã hóa. Công thức này giúp hình dung vì sao một số thập phân không phải lúc nào cũng biểu diễn chính xác trong hệ nhị phân.

Không phải mọi giá trị đều là số chuẩn hóa. IEEE 754 còn có:

- **Subnormal numbers:** biểu diễn các số rất nhỏ gần 0 với độ chính xác giảm dần.
- **Positive/negative infinity:** kết quả vượt phạm vi hữu hạn hoặc phép toán đặc biệt.
- **NaN (Not a Number):** biểu diễn kết quả không phải một số thực thông thường.
- **Positive zero và negative zero:** hai biểu diễn zero có bit dấu khác nhau.

Java cung cấp `Float` và `Double` với các hằng số/phương thức để nhận biết các trường hợp này.

### 2.3. Không phải mọi số thập phân đều có biểu diễn nhị phân hữu hạn

Ví dụ quen thuộc:

~~~java
double value = 0.1 + 0.2;
System.out.println(value);          // thường in 0.30000000000000004
System.out.println(value == 0.3);   // false
~~~

Nguyên nhân không phải Java 17 tính sai phép cộng. Các giá trị `0.1`, `0.2` và `0.3` không có biểu diễn nhị phân hữu hạn chính xác trong binary64. Khi chuyển từ literal thập phân sang `double`, mỗi giá trị được làm tròn đến giá trị binary64 gần nhất. Phép cộng sau đó tuân theo quy tắc số học dấu phẩy động và kết quả cũng được làm tròn.

**Ngữ nghĩa strict bảo đảm quy tắc đánh giá nhất quán; nó không xóa sai số vốn có của định dạng.**

## 3. Strict floating-point semantics trước và từ Java 17

### 3.1. Bối cảnh lịch sử

Trong các phiên bản Java ban đầu, biểu thức dấu phẩy động được đánh giá theo ngữ nghĩa nghiêm ngặt. Từ Java 1.2, Java cho phép một số biểu thức không strict được sử dụng *extended-exponent value set* trong những trường hợp nền tảng hỗ trợ.

Tập giá trị có số mũ mở rộng giữ độ chính xác significand tương ứng nhưng cho phép phạm vi exponent rộng hơn so với `float` hoặc `double` tiêu chuẩn. Điều này có thể giảm overflow/underflow tạm thời trong một phép tính trung gian, nhưng cũng tạo ra khả năng kết quả khác nhau giữa các nền tảng.

Từ Java 1.2 đến trước Java 17:

- Biểu thức trong ngữ cảnh strict phải tuân theo tập giá trị chuẩn.
- Từ khóa `strictfp` có thể được dùng để yêu cầu ngữ nghĩa strict cho class, interface hoặc method theo các quy tắc của phiên bản đó.
- Biểu thức không strict có thể được đánh giá với tập giá trị mở rộng trong một số môi trường.

Từ Java 17:

- Mọi biểu thức dấu phẩy động đều strict.
- Không còn khác biệt thực thi giữa ngữ cảnh strict và non-strict cho biểu thức số thực.
- `strictfp` không còn cần thiết để đạt ngữ nghĩa strict; từ khóa được giữ lại vì tương thích mã nguồn cũ nhưng không còn tạo khác biệt hành vi.

### 3.2. Tại sao ngữ nghĩa không strict từng tồn tại?

Một số bộ xử lý cũ, đặc biệt những kiến trúc dùng thanh ghi số thực có phạm vi exponent rộng hơn định dạng `double` lưu trong bộ nhớ, có thể giữ kết quả trung gian trong thanh ghi với phạm vi rộng hơn. Việc này đôi khi cải thiện độ chính xác thực tế hoặc tránh overflow tạm thời.

Nhưng nó cũng khiến:

- Kết quả phụ thuộc vào kiến trúc CPU và cách JVM sử dụng thanh ghi.
- Việc lưu một biến trung gian vào bộ nhớ có thể làm tròn về `double`, trong khi giữ trong thanh ghi có thể duy trì giá trị mở rộng.
- Cùng một đoạn code có khả năng cho kết quả khác nhau khi thay đổi nền tảng hoặc cách tối ưu hóa.

JEP 306 chọn tính nhất quán và khả năng dự đoán làm mặc định trên mọi nền tảng hiện đại.

### 3.3. Ý nghĩa thực tế của thay đổi

Với Java 17, lập trình viên không phải đánh dấu từng lớp hay method để yêu cầu phép toán `float`/`double` tuân theo ngữ nghĩa strict. Mã nguồn có thể biểu đạt ý định tính toán mà không cần phụ thuộc vào vị trí đặt `strictfp`.

Điều này hữu ích cho:

- **Khả năng tái lập phép toán cơ bản:** cùng đầu vào và cùng chuỗi phép toán cơ bản có quy tắc làm tròn xác định.
- **Di chuyển giữa môi trường:** giảm khác biệt do extended-exponent evaluation.
- **Đọc code đơn giản hơn:** không phải quyết định nơi nào cần `strictfp`.
- **Bảo trì code cũ:** hiểu vì sao `strictfp` xuất hiện và vì sao nó không còn cần thiết khi biên dịch/chạy trên Java 17.

Không nên hiểu rằng mọi ứng dụng Java 17 sẽ tự động tạo ra cùng kết quả cho mọi tác vụ số học trên mọi máy. Thư viện native, hàm toán học, thuật toán song song, thứ tự phép toán, dữ liệu đầu vào và các nguồn không xác định khác vẫn có thể ảnh hưởng kết quả tổng thể.

## 4. `strictfp` trong Java 17

### 4.1. Trước Java 17, `strictfp` dùng để làm gì?

Trước Java 17, `strictfp` được dùng để yêu cầu biểu thức dấu phẩy động trong phạm vi tương ứng sử dụng ngữ nghĩa strict. Ví dụ lịch sử:

~~~java
public strictfp class LegacyCalculator {
    public static double calculate(double a, double b, double c) {
        return a * b + c;
    }
}
~~~

Hoặc trên method:

~~~java
public class LegacyCalculator {
    public strictfp double calculate(double a, double b) {
        return a / b;
    }
}
~~~

Mục tiêu là tránh các kết quả phụ thuộc vào tập giá trị mở rộng của biểu thức non-strict trên nền tảng có hỗ trợ.

### 4.2. Từ Java 17, `strictfp` không còn tác dụng thay đổi ngữ nghĩa

Từ Java 17, mọi biểu thức số thực đã strict. Vì vậy:

~~~java
public class Calculator {
    public double calculate(double a, double b, double c) {
        return a * b + c;
    }
}
~~~

đã có ngữ nghĩa strict mà không cần modifier.

Mã có `strictfp` vẫn được giữ trong Java 17 để tương thích mã nguồn, nhưng modifier không còn tạo ra sự khác biệt trong cách đánh giá biểu thức dấu phẩy động. Trình biên dịch `javac` có thể phát cảnh báo cho modifier này:

~~~text
as of release 17, all floating-point expressions are evaluated strictly
and 'strictfp' is not required
~~~

Thông điệp cảnh báo có thể được trình bày khác đôi chút tùy bản JDK/compiler.

### 4.3. Có nên xóa `strictfp` khỏi codebase?

Nếu dự án đặt Java 17 làm baseline, có thể cân nhắc bỏ modifier dư thừa để code gọn hơn. Tuy nhiên:

- Đây là thay đổi làm sạch mã nguồn, không phải điều kiện để phép toán trở nên strict trên Java 17.
- Nếu cùng một source tree còn cần biên dịch/chạy với JDK cũ, phải xét baseline và mục tiêu tương thích thực tế.
- Không nên xóa hàng loạt mà không hiểu cấu hình build, release target và môi trường runtime của dự án.
- Không dùng `strictfp` như một giải pháp sửa sai số thập phân; nó không làm `0.1 + 0.2` bằng chính xác `0.3`.

## 5. Java 17 đánh giá các phép toán số thực như thế nào?

### 5.1. Các phép toán cơ bản

Những phép toán số thực thường gặp:

- Cộng: `+`
- Trừ: `-`
- Nhân: `*`
- Chia: `/`
- Phần dư: `%`
- Đổi dấu: unary `-`
- Chuyển kiểu số: cast và các quy tắc numeric promotion

Với Java 17, biểu thức chứa `float`/`double` được đánh giá theo ngữ nghĩa strict. Giá trị trung gian không được tùy ý giữ trong tập giá trị extended-exponent như quy tắc non-strict lịch sử.

Ví dụ:

~~~java
double a = 1.0;
double b = 3.0;
double result = a / b;

System.out.println(result);
~~~

Kết quả là một giá trị binary64 gần nhất theo quy tắc làm tròn của phép chia. Không có một `double` hữu hạn nào biểu diễn chính xác (1/3), nên kết quả vẫn là xấp xỉ.

### 5.2. Làm tròn sau các bước tính toán

Giả sử:

~~~java
double a = 1.0;
double b = 1.0 + Math.scalb(1.0, -27);
double c = 1.0 - Math.scalb(1.0, -27);

double separate = b * c - a;
double fused = Math.fma(b, c, -a);
~~~

Phép tính `b * c - a` gồm phép nhân rồi phép trừ. Theo ngữ nghĩa strict, kết quả phép nhân được làm tròn theo định dạng `double` trước khi thực hiện phép trừ tiếp theo.

`Math.fma(b, c, -a)` biểu diễn một phép **fused multiply-add**: tính tích và tổng như một phép toán kết hợp, chỉ làm tròn một lần ở kết quả cuối. Vì thế kết quả của `Math.fma` có thể khác kết quả của `b * c + (-a)`, dù công thức toán học nhìn bề ngoài giống nhau.

FMA là một phép toán được yêu cầu tường minh qua API; ngữ nghĩa strict không có nghĩa JVM được tự do thay thế mọi chuỗi `a * b + c` bằng FMA, vì làm vậy có thể thay đổi kết quả làm tròn.

### 5.3. Ví dụ thể hiện hai lần làm tròn và một lần làm tròn

~~~java
public class FmaExample {
    public static void main(String[] args) {
        double a = 1.0 + Math.scalb(1.0, -27);
        double b = 1.0 - Math.scalb(1.0, -27);
        double c = -1.0;

        double separate = a * b + c;
        double fused = Math.fma(a, b, c);

        System.out.println("Separate: " + separate);
        System.out.println("Fused:    " + fused);
    }
}
~~~

Với các giá trị trên, tích chính xác của hai toán hạng là (1 - 2^{-54}). Phép nhân riêng được làm tròn về `1.0` ở binary64; trừ tiếp `1.0` cho kết quả `0.0`. FMA giữ tích chính xác trong nội bộ phép toán kết hợp rồi mới làm tròn, do đó cho kết quả khác 0.

Đây không phải lỗi của strict semantics. Hai đoạn code **định nghĩa hai chuỗi phép toán khác nhau** về mặt làm tròn. Hãy chọn FMA khi thuật toán cần đặc tính fused và đã được thiết kế/kiểm thử cho điều đó.

## 6. Strict không đồng nghĩa chính xác tuyệt đối

### 6.1. Sai số biểu diễn

~~~java
double x = 0.1;
System.out.printf("%.20f%n", x);
~~~

Giá trị hiển thị có thể cho thấy một xấp xỉ nhị phân. `double` có khoảng 15–17 chữ số thập phân có ý nghĩa trong nhiều trường hợp, nhưng không phải mọi số thập phân đều biểu diễn chính xác.

### 6.2. Sai số tích lũy

~~~java
double sum = 0.0;
for (int i = 0; i < 10_000; i++) {
    sum += 0.1;
}
System.out.println(sum);
~~~

Mỗi lần cộng có thể làm tròn; sai số nhỏ có thể tích lũy. Strict semantics giúp từng bước được đánh giá nhất quán, nhưng không loại bỏ sai số của thuật toán.

Khi cộng nhiều số có độ lớn chênh lệch lớn, thứ tự cộng có thể ảnh hưởng kết quả. Nếu yêu cầu độ chính xác cao, cân nhắc thuật toán cộng bù (compensated summation, chẳng hạn Kahan summation), thay đổi thứ tự cộng có chủ đích hoặc kiểu số phù hợp.

### 6.3. Overflow và underflow

~~~java
double huge = Double.MAX_VALUE;
double overflow = huge * 2.0;

double tiny = Double.MIN_VALUE;
double underflow = tiny / 2.0;

System.out.println(overflow);  // Infinity
System.out.println(underflow); // Có thể làm tròn về 0.0
~~~

`Double.MAX_VALUE` là giá trị hữu hạn lớn nhất của `double`; phép nhân vượt phạm vi tạo vô cực. `Double.MIN_VALUE` là giá trị dương subnormal nhỏ nhất khác 0 của `double`, không phải số âm nhỏ nhất và cũng không phải độ lớn nhỏ nhất của số chuẩn hóa. Chia nó cho 2 có thể làm tròn về zero.

Luôn kiểm tra nếu thuật toán không chấp nhận các kết quả không hữu hạn:

~~~java
if (!Double.isFinite(result)) {
    throw new ArithmeticException("Kết quả không hữu hạn");
}
~~~

### 6.4. NaN và vô cực

Java cung cấp:

~~~java
double notANumber = Double.NaN;
double positiveInfinity = Double.POSITIVE_INFINITY;
double negativeInfinity = Double.NEGATIVE_INFINITY;

System.out.println(Double.isNaN(notANumber));       // true
System.out.println(Double.isInfinite(positiveInfinity)); // true
System.out.println(Double.isFinite(1.25));          // true
~~~

Một số quy tắc cần nhớ:

- `NaN == NaN` là `false`.
- `NaN != NaN` là `true`.
- Các phép so sánh `<`, `<=`, `>`, `>=` với NaN đều là `false`.
- `Double.isNaN(value)` là cách kiểm tra NaN rõ ràng.
- `Double.isFinite(value)` trả false với NaN và hai vô cực.
- Phép toán tạo vô cực hoặc NaN vẫn tuân theo quy tắc IEEE 754; strict không biến chúng thành exception tự động.

Ví dụ:

~~~java
double invalid = 0.0 / 0.0;
double infinity = 1.0 / 0.0;

System.out.println(Double.isNaN(invalid)); // true
System.out.println(Double.isInfinite(infinity)); // true
~~~

Không nên dựa vào `value == Double.NaN` để kiểm tra NaN.

### 6.5. Positive zero và negative zero

IEEE 754 có cả `+0.0` và `-0.0`:

~~~java
double positiveZero = 0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero); // true
System.out.println(1.0 / positiveZero);            // Infinity
System.out.println(1.0 / negativeZero);            // -Infinity
System.out.println(Double.compare(negativeZero, positiveZero)); // -1
~~~

So sánh toán tử `==` coi hai giá trị zero này bằng nhau, nhưng dấu của zero có thể ảnh hưởng kết quả phép toán sau đó. `Double.compare` phân biệt `-0.0` và `+0.0` theo thứ tự quy định.

Đây là một chi tiết quan trọng khi xử lý thuật toán hình học, số học khoa học hoặc các phép tính có hướng.

## 7. Phép toán strict và các hàm trong `Math`/`StrictMath`

### 7.1. Không đánh đồng phép toán cơ bản với hàm toán học

JEP 306 nói về **ngữ nghĩa đánh giá biểu thức dấu phẩy động**. Điều đó không có nghĩa mọi method trong `Math` đều trở thành một phép toán strict giống `+`, `*` hoặc `/`.

Ví dụ:

- `Math.sqrt(x)`
- `Math.sin(x)`
- `Math.log(x)`
- `Math.pow(x, y)`

được định nghĩa theo hợp đồng API riêng. Các method này có yêu cầu về độ chính xác và tính chất kết quả, nhưng `Math` có thể sử dụng triển khai tối ưu theo nền tảng trong phạm vi đặc tả cho phép.

### 7.2. Khi nào dùng `Math`, khi nào cân nhắc `StrictMath`?

| API | Mục đích |
|---|---|
| `Math` | Các hàm toán học hiệu năng tốt, triển khai có thể tận dụng tối ưu nền tảng, tuân theo giới hạn chính xác được API quy định |
| `StrictMath` | Các hàm được đặc tả để có kết quả nhất quán giữa các nền tảng theo thuật toán quy định (historically fdlibm-based) |
| `Math.fma` | Phép fused multiply-add tường minh, một lần làm tròn cho phép toán kết hợp |

Nếu yêu cầu là **kết quả của hàm toán học phải tái lập nhất quán trên nhiều nền tảng**, hãy xem xét `StrictMath` và đặc tả của method cụ thể. Nếu yêu cầu là hiệu năng và sai số trong giới hạn API, `Math` thường là lựa chọn thông dụng.

Không nên thay tất cả `Math` bằng `StrictMath` theo thói quen. Hãy căn cứ vào hợp đồng độ chính xác, tính tái lập và hiệu năng của ứng dụng.

### 7.3. Một ứng dụng vẫn có thể không deterministic dù dùng Java 17

Các nguồn khác biệt có thể đến từ:

- Thứ tự cộng/nhân khác nhau trong thuật toán song song.
- Dữ liệu đầu vào khác nhau hoặc khác thứ tự.
- Hàm toán học có hợp đồng cho phép triển khai khác nhau.
- Native code hoặc thư viện ngoài JVM.
- Sử dụng `float` ở một nơi và `double` ở nơi khác.
- Làm tròn ở các ranh giới chuyển kiểu hoặc serialize/deserialize.

Strict semantics giải quyết một nguồn không nhất quán quan trọng của phép toán cơ bản; nó không thay thế thiết kế deterministic cho toàn bộ pipeline.

## 8. Khi nào không nên dùng float/double cho tiền tệ?

### 8.1. Binary floating point không biểu diễn chính xác mọi số thập phân

Giá trị tiền tệ thường cần tuân thủ đơn vị nhỏ nhất, quy tắc làm tròn và số chữ số thập phân theo đồng tiền. `double` phù hợp với nhiều phép tính khoa học, nhưng không tự bảo đảm các phép tính thập phân tài chính chính xác theo quy tắc nghiệp vụ.

Ví dụ:

~~~java
double price = 0.1;
double quantity = 3;
double total = price * quantity;

System.out.println(total); // Có thể là giá trị xấp xỉ
~~~

### 8.2. Dùng `BigDecimal` khi cần số thập phân chính xác theo hợp đồng

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal unitPrice = new BigDecimal("0.10");
BigDecimal quantity = new BigDecimal("3");

BigDecimal total = unitPrice.multiply(quantity);
BigDecimal rounded = total.setScale(2, RoundingMode.HALF_UP);

System.out.println(rounded); // 0.30
~~~

Nên khởi tạo `BigDecimal` từ **chuỗi thập phân** hoặc từ nguồn số nguyên có ý nghĩa rõ ràng:

~~~java
BigDecimal correct = new BigDecimal("0.1");
BigDecimal fromDouble = new BigDecimal(0.1);
BigDecimal convenient = BigDecimal.valueOf(0.1);
~~~

- `new BigDecimal("0.1")` biểu diễn chính xác giá trị thập phân 0.1.
- `new BigDecimal(0.1)` chuyển giá trị binary64 hiện có thành số thập phân chính xác của chính giá trị binary đó, nên thường chứa nhiều chữ số ngoài dự kiến.
- `BigDecimal.valueOf(0.1)` dùng biểu diễn thập phân chuẩn hóa từ `Double.toString`, thường là cách thuận tiện hơn nếu đầu vào ban đầu đã là `double`. Tuy nhiên, tốt nhất là không đi qua `double` nếu dữ liệu nguồn vốn là số thập phân chính xác.

`BigDecimal` không phải kiểu primitive và có chi phí lớn hơn `double`; hãy dùng khi hợp đồng nghiệp vụ yêu cầu số học thập phân chính xác và quy tắc scale/rounding rõ ràng.

### 8.3. Dùng số nguyên cho đơn vị nhỏ nhất khi phù hợp

Một lựa chọn khác là lưu tiền bằng số nguyên đơn vị nhỏ nhất:

~~~java
long amountInCents = 1_250_000L;
long taxInCents = 100_000L;
long totalInCents = Math.addExact(amountInCents, taxInCents);
~~~

Cách này tránh sai số binary floating point khi mọi giá trị có thể biểu diễn bằng đơn vị nhỏ nhất cố định. Cần kiểm soát overflow của kiểu nguyên thủy; các method `Math.addExact`, `Math.multiplyExact` có thể phát hiện tràn số.

## 9. Kiểm thử và gỡ lỗi phép tính số thực

### 9.1. Tránh so sánh bằng tuyệt đối một cách máy móc

Với kết quả gần đúng, thay vì:

~~~java
if (actual == expected) {
    // ...
}
~~~

có thể dùng sai số cho phép:

~~~java
static boolean nearlyEqual(double actual, double expected, double epsilon) {
    return Math.abs(actual - expected) <= epsilon;
}
~~~

Nhưng `epsilon` phải phù hợp với **thang đo và miền giá trị**. Một epsilon tuyệt đối không phù hợp cho mọi bài toán, nhất là khi giá trị gần 0 hoặc có độ lớn rất khác nhau.

Một cách so sánh kết hợp sai số tuyệt đối và tương đối:

~~~java
static boolean nearlyEqual(
        double actual,
        double expected,
        double absoluteTolerance,
        double relativeTolerance
) {
    if (Double.doubleToLongBits(actual) ==
            Double.doubleToLongBits(expected)) {
        return true;
    }

    if (!Double.isFinite(actual) || !Double.isFinite(expected)) {
        return false;
    }

    double difference = Math.abs(actual - expected);
    double scale = Math.max(Math.abs(actual), Math.abs(expected));

    return difference <= Math.max(
            absoluteTolerance,
            relativeTolerance * scale
    );
}
~~~

Đây chỉ là một mẫu tiện ích; tolerance phải được lựa chọn theo sai số thuật toán và đơn vị đo. Nếu cần phân biệt `+0.0` với `-0.0`, hoặc xử lý NaN/infinity theo quy tắc riêng, cần bổ sung chính sách rõ ràng.

### 9.2. In giá trị và biểu diễn bit khi cần điều tra

~~~java
double value = 0.1;

System.out.println(value);
System.out.println(Double.toHexString(value));
System.out.println(Long.toBinaryString(
        Double.doubleToRawLongBits(value)
));
~~~

`Double.toHexString` hữu ích để quan sát biểu diễn binary64 ở dạng thập lục phân. `doubleToRawLongBits` cung cấp bit pattern, bao gồm cả payload NaN nếu cần kiểm tra ở mức thấp.

Với `float`, có các API tương ứng trong `Float`, ví dụ `Float.toHexString` và `Float.floatToRawIntBits`.

### 9.3. Kiểm thử các trường hợp biên

Một bộ test số thực nên cân nhắc:

- Giá trị hữu hạn bình thường.
- `0.0` và `-0.0`.
- `Float.MIN_VALUE`/`Double.MIN_VALUE` và các giá trị subnormal.
- `Float.MAX_VALUE`/`Double.MAX_VALUE`.
- Overflow và underflow.
- `NaN`, positive infinity, negative infinity.
- Các giá trị nằm gần ngưỡng làm tròn.
- Đầu vào khác nhau về độ lớn nhiều bậc.

Java 17 giúp phép toán cơ bản có ngữ nghĩa thống nhất, nhưng test vẫn cần phản ánh hợp đồng nghiệp vụ và độ chính xác được chấp nhận.

## 10. Ảnh hưởng đến dự án khi nâng cấp lên Java 17

### 10.1. Kiểm tra `strictfp` trong code cũ

Khi chuyển dự án từ Java 8 hoặc Java 11 lên Java 17, có thể gặp các khai báo:

~~~java
public strictfp class ScientificService {
    public strictfp double compute(double input) {
        return input * input;
    }
}
~~~

Trên Java 17, các modifier này không còn cần thiết để yêu cầu strict evaluation. Có thể giữ lại trong giai đoạn nâng cấp để hạn chế diff, rồi cân nhắc loại bỏ trong một thay đổi làm sạch riêng nếu baseline dự án là Java 17.

Không được kết luận rằng mọi kết quả số thực cũ và mới chắc chắn giống nhau. Nếu code trước đây được thực thi trên nền tảng/JVM có sử dụng extended-exponent evaluation trong biểu thức non-strict, kết quả trung gian có thể thay đổi khi chạy theo ngữ nghĩa Java 17 luôn strict.

### 10.2. Đánh giá các kiểm thử phụ thuộc kết quả bit

Nếu dự án so sánh kết quả `double` bằng bit pattern hoặc snapshot chính xác, hãy xác định:

- Kết quả kỳ vọng dựa trên đặc tả nào?
- Code cũ có dùng `strictfp` hay không?
- Runtime trước đây chạy trên kiến trúc nào?
- Phép toán có dùng thư viện native hoặc `Math` method không?
- Có thay đổi thứ tự tính toán, JIT hoặc dependency đồng thời với nâng JDK không?

Chỉ thay đổi expected value khi có lý do từ đặc tả/thuật toán; không cập nhật snapshot chỉ để làm test xanh.

### 10.3. Không cần thay mọi phép toán double bằng BigDecimal

Java 17 không yêu cầu đổi toàn bộ `double` sang `BigDecimal`. Hãy phân loại theo hợp đồng:

| Miền nghiệp vụ | Lựa chọn thường phù hợp |
|---|---|
| Đồ họa, mô phỏng, thống kê, đo lường chấp nhận sai số | `double`/`float` và thuật toán phù hợp |
| Tiền tệ, thuế, tỷ lệ có quy tắc decimal cụ thể | `BigDecimal` hoặc số nguyên đơn vị nhỏ nhất |
| Bộ đếm nguyên, số lượng rời rạc | `int`/`long`, cân nhắc kiểm tra overflow |
| API ngoài gửi số thập phân | Xác định schema, độ chính xác, scale và cách parse trước khi chọn kiểu |

Ngữ nghĩa strict giải quyết tính nhất quán đánh giá floating point, còn lựa chọn kiểu dữ liệu vẫn là trách nhiệm thiết kế nghiệp vụ.

## 11. Những hiểu nhầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Java 17 strict nghĩa là không còn sai số số thực.” | Vẫn có làm tròn và sai số biểu diễn; strict chỉ thống nhất quy tắc đánh giá. |
| “`strictfp` là bắt buộc để có kết quả chuẩn trên Java 17.” | Mọi biểu thức đã strict; modifier không còn tác dụng thay đổi ngữ nghĩa. |
| “`strictfp` đã bị xóa khỏi cú pháp Java.” | Từ khóa còn được giữ để tương thích mã nguồn nhưng không còn cần thiết. |
| “Mọi hàm trong `Math` đều có kết quả bit-for-bit giống nhau trên mọi nền tảng nhờ JEP 306.” | JEP 306 chủ yếu chuẩn hóa biểu thức floating point; hàm toán học có hợp đồng API riêng. |
| “Strict cho phép JVM tự thay `a*b+c` bằng FMA.” | FMA là phép toán kết hợp với một lần làm tròn; dùng `Math.fma` tường minh khi muốn ngữ nghĩa đó. |
| “`double` luôn chính xác hơn `float` nên dùng cho tiền tệ.” | `double` có độ chính xác nhị phân cao hơn nhưng không biểu diễn chính xác mọi số thập phân. |
| “Overflow của double tự ném exception.” | Nhiều phép toán tạo `Infinity` hoặc `NaN`; cần kiểm tra nếu miền không chấp nhận. |
| “`Double.MIN_VALUE` là số âm nhỏ nhất.” | Đó là giá trị dương subnormal nhỏ nhất khác 0. |
| “NaN có thể kiểm tra bằng `x == Double.NaN`.” | Phải dùng `Double.isNaN(x)`. |
| “Strict semantics làm toàn ứng dụng deterministic.” | Thứ tự thuật toán, thư viện, native code, dữ liệu và các hàm toán học vẫn có thể ảnh hưởng kết quả. |

## 12. Bài tập thực hành

### Bài 1 — Quan sát sai số biểu diễn

Viết chương trình:

~~~java
double a = 0.1;
double b = 0.2;
double c = a + b;

System.out.println(c);
System.out.println(c == 0.3);
System.out.println(Double.toHexString(a));
System.out.println(Double.toHexString(b));
System.out.println(Double.toHexString(c));
~~~

Giải thích vì sao Java 17 strict vẫn cho kết quả không bằng chính xác `0.3`. Phân biệt sai số biểu diễn với sai lệch do ngữ nghĩa non-strict lịch sử.

### Bài 2 — Kiểm tra strictfp

Khai báo hai class: một class có `strictfp`, một class không có. Biên dịch trên JDK 17 và quan sát cảnh báo (nếu có). Giải thích vì sao hai class có cùng ngữ nghĩa đánh giá floating point trên Java 17 và `strictfp` từng có ý nghĩa gì ở các phiên bản cũ.

### Bài 3 — Phân biệt phép nhân cộng và FMA

Dùng:

~~~java
double a = 1.0 + Math.scalb(1.0, -27);
double b = 1.0 - Math.scalb(1.0, -27);
double c = -1.0;

System.out.println(a * b + c);
System.out.println(Math.fma(a, b, c));
~~~

Giải thích tại sao hai kết quả khác nhau. Nêu rõ vị trí làm tròn trong phép toán tách rời và trong FMA.

### Bài 4 — Xử lý giá trị không hữu hạn

Viết method nhận hai `double`, thực hiện phép chia và trả kết quả hoặc báo lỗi nếu:

- Mẫu số bằng positive/negative zero.
- Kết quả không hữu hạn.
- Đầu vào NaN hoặc vô cực.

Xác định chính sách đối với signed zero và NaN. Không chỉ dựa vào phép chia để suy ra mọi trường hợp đầu vào hợp lệ.

### Bài 5 — Chọn kiểu cho bài toán giá tiền

Một đơn hàng có giá đơn vị 0.10 và số lượng 3. Viết hai cách:

1. Tính bằng `double` và quan sát kết quả.
2. Tính bằng `BigDecimal` được tạo từ chuỗi, sau đó áp dụng scale/rounding phù hợp.

Giải thích cách biểu diễn nào phản ánh đúng hợp đồng tiền tệ và vì sao Java 17 strict không làm cách thứ nhất trở nên chính xác thập phân.

### Bài 6 — Tính tổng với sai số tích lũy

So sánh tổng 10.000 lần cộng `0.1` với:

- Cộng tuần tự bằng `double`.
- Một thuật toán cộng bù như Kahan summation.
- `BigDecimal` khi yêu cầu phép cộng thập phân chính xác.

Phân biệt lợi ích về sai số số học với chi phí hiệu năng và loại dữ liệu.

## 13. Câu hỏi tự kiểm tra

1. `float` và `double` tương ứng với những định dạng IEEE 754 nào?
2. Extended-exponent value set trước Java 17 có vai trò gì?
3. JEP 306 thay đổi điều gì trong ngữ nghĩa số thực?
4. Vì sao mọi biểu thức floating point trên Java 17 không cần `strictfp`?
5. Từ khóa `strictfp` có bị loại bỏ hoàn toàn khỏi cú pháp không?
6. Strict semantics có làm `0.1 + 0.2 == 0.3` trở thành true không?
7. Vì sao `Math.fma(a, b, c)` có thể khác `a * b + c`?
8. Khác biệt giữa phép toán cơ bản và hàm `Math.sin`/`StrictMath.sin` là gì?
9. Overflow và underflow của `double` thường biểu hiện thế nào?
10. Cách kiểm tra NaN, infinity và finite value?
11. Vì sao `+0.0 == -0.0` nhưng phép chia cho hai giá trị có thể cho dấu vô cực khác nhau?
12. Khi nào nên dùng `BigDecimal` hoặc số nguyên thay vì `double`?
13. JEP 306 có đảm bảo toàn bộ ứng dụng deterministic trên mọi hệ thống không?
14. Khi nâng cấp lên Java 17, cần kiểm tra những phép tính hoặc test nào có thể phụ thuộc ngữ nghĩa floating point cũ?

## 14. Tài liệu tham khảo

- [OpenJDK JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306): mô tả thay đổi được chuẩn hóa trong Java 17 và bối cảnh lịch sử của strict/non-strict floating point.
- [Java Language Specification, Java SE 17 — Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): các kiểu, định dạng và giá trị số thực.
- [Java Language Specification, Java SE 17 — Floating-Point Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.4): ngữ nghĩa strict của biểu thức số thực.
- [Java SE 17 API — Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): các hàm toán học, `fma` và hợp đồng API.
- [Java SE 17 API — StrictMath](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StrictMath.html): các hàm toán học có yêu cầu kết quả nhất quán theo đặc tả.
- [Java SE 17 API — Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): hằng số và phương thức kiểm tra giá trị binary64.
- [Java SE 17 API — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): số học thập phân có độ chính xác tùy ý và quy tắc scale/rounding.

Java 17 làm cho phép toán số thực luôn được đánh giá theo ngữ nghĩa strict, giúp loại bỏ khác biệt lịch sử do extended-exponent evaluation. Khi áp dụng, hãy tách bạch **tính nhất quán của quy tắc tính toán** với **độ chính xác của định dạng và thuật toán**: strict không biến binary floating point thành số thập phân chính xác, không loại bỏ NaN/infinity và không tự quyết định chính sách làm tròn của miền nghiệp vụ.
