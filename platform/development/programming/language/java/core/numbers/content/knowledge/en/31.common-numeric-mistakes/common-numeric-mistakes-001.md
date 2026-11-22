# Gán kết quả int đã tràn sang long không thể khôi phục giá trị trong Java

## 1. Sai lầm cốt lõi: kiểu đích rộng không thay đổi kiểu phép tính nguồn

Xét một đoạn Java tưởng như an toàn:

~~~java
int a = 2_000_000_000;
int b = 1_500_000_000;

long result = a + b;
System.out.println(result); // -794967296, KHÔNG phải 3500000000
~~~

Tại sao biến `result` là `long` 64 bit mà vẫn mang số âm?

**Vì `a + b` được tính hoàn toàn bằng `int` 32 bit trước**, vượt quá `Integer.MAX_VALUE = 2_147_483_647`. Kết quả `int` tràn theo quy tắc số nguyên Java. Sau khi phép cộng kết thúc, giá trị `int` **đã sai** mới được chuyển rộng sang `long`. Phép chuyển rộng giữ nguyên giá trị số âm đang có, chứ không biết kết quả toán học ban đầu.

~~~text
int a = 2_000_000_000
int b = 1_500_000_000
       |
       v
a + b   (phép cộng int, 32 bit)
       |
       v
-794_967_296   (đã tràn int)
       |
       v
chuyển int -> long
       |
       v
long result = -794_967_296
~~~

Tổng toán học đúng là `3_500_000_000`, nằm trong miền `long` nhưng không nằm trong miền `int`.

Sửa đúng:

~~~java
long result = (long) a + b; // 3500000000
~~~

Phép ép `(long) a` xảy ra **trước khi cộng**, nên `+` chọn phép cộng `long`; `b` cũng được chuyển sang `long` để thực hiện phép tính.

**Nguyên tắc:** Muốn phép tính dùng kiểu rộng, hãy làm cho **ít nhất một toán hạng phù hợp có kiểu rộng trước khi phép toán diễn ra**, hoặc sử dụng API phát hiện tràn. Không trông chờ kiểu biến nhận ở vế trái cứu kết quả đã tràn.

## 2. Vì sao Java tính bằng int trước khi gán sang long?

Java xác định kiểu của biểu thức `+`, `-`, `*`, `/`, `%` qua **binary numeric promotion** (quy tắc nâng kiểu số cho hai toán hạng):

- Nếu một toán hạng là `double`, phép toán thường thực hiện trong kiểu `double`.
- Nếu không có `double` nhưng có `float`, phép toán thường thực hiện trong kiểu `float`.
- Nếu không có hai kiểu trên nhưng có `long`, phép toán số nguyên thực hiện bằng `long`.
- Nếu chỉ còn các kiểu nguyên nhỏ hơn hoặc bằng `int` (`byte`, `short`, `char`, `int`), chúng được nâng lên `int`.

Trong ví dụ `a` và `b` đều là `int`, nên `a + b` là **biểu thức int**, bất kể nơi gán kết quả là `long`, `double`, `BigInteger` (qua chuyển đổi tường minh) hay một phương thức nhận long.

Thứ tự khái niệm là:

1. Xác định kiểu toán hạng và phép toán.
2. Tính biểu thức, có thể xảy ra tràn hoặc cắt phần lẻ.
3. Chuyển kiểu kết quả theo ngữ cảnh gán/gọi hàm.
4. Gán hoặc truyền giá trị đã tính.

Quy tắc gán mở rộng `int -> long` **không thay đổi bước 1 và bước 2**.

~~~java
int x = 2_000_000_000;
int y = 1_500_000_000;

long late = x + y;           // -794967296
long earlyLeft = (long) x + y; // 3500000000
long earlyRight = x + (long) y; // 3500000000
~~~

Bạn cũng có thể dùng literal có hậu tố `L`:

~~~java
long correct = 2_000_000_000L + 1_500_000_000; // 3500000000
~~~

Ngược lại, chỉ đổi kiểu vế trái không đủ:

~~~java
long wrong = 2_000_000_000 + 1_500_000_000; // -794967296
~~~

**Lưu ý về constant expression:** Java có thể tính biểu thức hằng ngay tại thời điểm biên dịch. Điều đó không có nghĩa phép cộng hai `int` tự động được nâng sang `long`. Hãy kiểm tra **kiểu của toán hạng**, kể cả trong hằng số và biểu thức không có biến.

## 3. Một ví dụ khác: nhân hai int trước khi gán sang long

Ví dụ tính diện tích hoặc tổng tiền:

~~~java
int quantity = 50_000;
int unitPrice = 50_000;

long wrong = quantity * unitPrice;       // -1794967296
long stillWrong = (long) (quantity * unitPrice); // -1794967296
long correct = (long) quantity * unitPrice;      // 2500000000
~~~

Tích toán học là `50_000 × 50_000 = 2_500_000_000`, vượt miền `int`. Khi chỉ có toán hạng int, phép `*` cho kết quả int đã tràn.

Sự khác biệt giữa hai cách viết rất quan trọng:

| Biểu thức | Trình tự | Kết quả |
| --- | --- | ---: |
| `(long) (a * b)` | Tính `int * int` trước, **sau đó** cast | Có thể là số sai đã tràn |
| `(long) a * b` | Cast `a` trước, rồi `long * long` | Giữ được tích của hai int trong miền long |
| `a * (long) b` | Cast `b` trước, rồi `long * long` | Tương tự |
| `1L * a * b` | Nhân với `1L` trước theo thứ tự kết hợp | Tích tính bằng long ngay từ đầu |

Trong Java, **tích toán học của hai giá trị int bất kỳ vừa trong miền long**, nên chuyển ít nhất một toán hạng sang long trước phép nhân là đủ tránh **tràn số nguyên tại phép nhân đó**. Tuy nhiên, một biểu thức chứa nhiều lần nhân hoặc cộng trên các giá trị long vẫn có thể tràn `long` nếu vượt miền 64 bit.

Ví dụ, `a * b * 1L` **có thể sai** vì Java kết hợp phép nhân từ trái sang phải: `a * b` được tính bằng int trước, sau đó mới nhân với `1L`. Hãy viết `1L * a * b` hoặc `(long) a * b`.

## 4. Dấu ngoặc và phép ép: vị trí quyết định tính đúng

So sánh:

~~~java
long a = (long) (x + y); // Quá muộn nếu x+y đã tràn int
long b = (long) x + y;   // x đã là long khi thực hiện phép cộng
~~~

Dấu ngoặc ở biểu thức thứ nhất bắt Java tính `x + y` như một biểu thức `int` trước khi ép; ép kiểu ngoài ngoặc chỉ giữ nguyên giá trị int đã tính xong.

Với nhiều phép toán, cần xem xét **từng phép trung gian**:

~~~java
int a = 1_500_000_000;
int b = 1_500_000_000;
int c = 1;

long wrong = (a + b) + (long) c; // a+b đã tràn int
long correct = (long) a + b + c; // mọi phép cộng trong chuỗi này là long
~~~

Một trường hợp khác:

~~~java
int width = 50_000;
int height = 50_000;

long wrongArea = width * height;          // tràn int
long correctArea = 1L * width * height;   // long ngay từ phép nhân đầu
~~~

Tự hỏi tại **nút phép toán** trong cây biểu thức: hai toán hạng lúc đó có kiểu gì? Câu trả lời có thể quan trọng hơn kiểu khai báo của kết quả.

## 5. Chương trình Java 17 đầy đủ và kết quả chính xác

Tạo file `OverflowBeforeWideningDemo.java`:

~~~java
import java.util.Arrays;

public class OverflowBeforeWideningDemo {
    public static void main(String[] args) {
        int a = 2_000_000_000;
        int b = 1_500_000_000;

        long sumTooLate = a + b;
        long sumCorrect = (long) a + b;
        System.out.println("sum too late = " + sumTooLate);
        System.out.println("sum widened = " + sumCorrect);

        int x = 50_000;
        int y = 50_000;
        long productTooLate = (long) (x * y);
        long productCorrect = (long) x * y;
        System.out.println("product too late = " + productTooLate);
        System.out.println("product widened = " + productCorrect);

        try {
            Math.addExact(a, b);
            System.out.println("Unexpected add success");
        } catch (ArithmeticException ex) {
            System.out.println("addExact = overflow detected");
        }

        try {
            Math.multiplyExact(x, y);
            System.out.println("Unexpected multiply success");
        } catch (ArithmeticException ex) {
            System.out.println("multiplyExact = overflow detected");
        }

        int[] numbers = {1_500_000_000, 1_500_000_000, 1};
        int wrongSum = Arrays.stream(numbers).sum();
        long correctSum = Arrays.stream(numbers).asLongStream().sum();
        System.out.println("int stream sum = " + wrongSum);
        System.out.println("long stream sum = " + correctSum);

        int min = Integer.MIN_VALUE;
        long wrongAbs = Math.abs(min);
        long correctAbs = Math.abs((long) min);
        System.out.println("abs too late = " + wrongAbs);
        System.out.println("abs widened = " + correctAbs);

        long daysWrong = 30 * 24 * 60 * 60 * 1000;
        long daysCorrect = 30L * 24 * 60 * 60 * 1000;
        System.out.println("30 days millis wrong = " + daysWrong);
        System.out.println("30 days millis correct = " + daysCorrect);
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac OverflowBeforeWideningDemo.java
java OverflowBeforeWideningDemo
~~~

Kết quả:

~~~text
sum too late = -794967296
sum widened = 3500000000
product too late = -1794967296
product widened = 2500000000
addExact = overflow detected
multiplyExact = overflow detected
int stream sum = -1294967295
long stream sum = 3000000001
abs too late = -2147483648
abs widened = 2147483648
30 days millis wrong = -1702967296
30 days millis correct = 2592000000
~~~

**Giải thích kết quả:**

1. Phép cộng `2_000_000_000 + 1_500_000_000` vượt `Integer.MAX_VALUE`, nên kết quả int là `-794_967_296`. Cast trước phép cộng giữ kết quả `3_500_000_000`.
2. Phép nhân `50_000 × 50_000` cho `2_500_000_000`, cũng vượt int; kiểu `long` phải tham gia **trước** phép nhân.
3. `Math.addExact(int, int)` và `Math.multiplyExact(int, int)` phát hiện tràn bằng `ArithmeticException`, thay vì âm thầm wrap.
4. `IntStream.sum()` trả int nên tổng có thể tràn; chuyển các phần tử sang long bằng `asLongStream()` **trước khi cộng dồn** tránh tràn int tại bước tổng.
5. `Math.abs(Integer.MIN_VALUE)` trả lại chính `Integer.MIN_VALUE` vì `2147483648` không thuộc miền int dương. Ép đầu vào lên long **trước** `Math.abs` cho `2147483648`.
6. Tích `30 × 24 × 60 × 60 × 1000` (mili giây trong 30 ngày, bỏ qua DST và chỉ minh họa số học độ dài cố định) cho `2_592_000_000`, vượt int. Dùng `30L` ngay từ đầu để kết quả tính bằng long.

Những dòng ra ở trên là cố định, không phụ thuộc vào luồng, thời gian thực hoặc đầu vào bên ngoài.

## 6. Tại sao long chỉ giữ lại kết quả đã tràn?

Với các phép số nguyên cộng, trừ, nhân Java, overflow **không tự ném exception**. Về mặt giá trị, phép toán int dùng 32 bit; kết quả khi vượt miền có thể “quay vòng” theo bit thấp, rồi được diễn giải lại như số int có dấu.

Phép cộng ví dụ:

~~~text
Tổng toán học:         3,500,000,000
2^32:                  4,294,967,296
Kết quả int có dấu:     -794,967,296
Mở rộng sang long:      -794,967,296
~~~

Khi chuyển từ `int` âm sang `long`, Java thực hiện phép mở rộng dấu (*sign extension*) để **giữ nguyên giá trị số âm**, không cố khôi phục bit đã loại trong phép tính trước đó. Nói cách khác, phép `int -> long` tự nó có thể chính xác — vấn đề nằm ở **phép tính int trước khi chuyển**.

Một điểm tinh tế: Có thể có nhiều tổng toán học khác nhau cùng tạo một giá trị int giống nhau sau tràn. Chẳng hạn `-794_967_296` có thể là giá trị hợp lệ chưa tràn hoặc là phần dư sau phép cộng `3_500_000_000`. Chỉ dựa vào một kết quả int đã lưu, không thể tự xác định tổng chính xác ban đầu là gì nếu không có thêm toán hạng hoặc thông tin khác.

Nếu dữ liệu nguồn vẫn được giữ nguyên, bạn có thể **tính lại** bằng long. Đó là tính lại từ nguồn, **không phải** khôi phục phép tính đã tràn chỉ bằng một phép ép trên kết quả sai.

## 7. Phòng tránh: nâng kiểu trước khi tính hoặc phát hiện tràn

Có ba chiến lược hay gặp.

### Chiến lược A — Tính bằng long khi miền kết quả đủ chứa

~~~java
int price = 50_000;
int quantity = 50_000;

long total = (long) price * quantity;
~~~

Dùng khi kết quả đúng có thể vượt int nhưng vẫn nằm trong long. Với tổng nhiều int, cho biến tích lũy là long từ đầu:

~~~java
int[] values = {1_500_000_000, 1_500_000_000, 1};

long total = 0L;
for (int v : values) {
    total += v; // long + int -> long
}
~~~

Đừng cộng toàn bộ bằng int rồi chuyển tổng sang long:

~~~java
int partial = 0;
for (int v : values) {
    partial += v; // Có thể tràn int ở vòng lặp!
}
long wrong = partial;
~~~

### Chiến lược B — Bắt overflow khi kiểu kết quả bắt buộc là int

Nếu hợp đồng API yêu cầu giá trị kiểu int và vượt miền phải bị từ chối:

~~~java
int safeSum = Math.addExact(a, b);
int safeProduct = Math.multiplyExact(a, b);
~~~

`Math.addExact`, `subtractExact`, `multiplyExact`, `incrementExact`, `decrementExact` và `negateExact` có những overload cho kiểu nguyên thích hợp và báo `ArithmeticException` khi kết quả không biểu diễn được.

Ví dụ:

~~~java
int count = Integer.MAX_VALUE;
int next = Math.incrementExact(count);
// ArithmeticException, thay vì quay vòng sang Integer.MIN_VALUE.
~~~

Nếu tính bằng long rồi cần chuyển về int, dùng:

~~~java
long wide = (long) a + b;
int checked = Math.toIntExact(wide);
~~~

`Math.toIntExact` nhận giá trị long đã tính chính xác và chỉ cho phép chuyển khi vừa int. Nhưng `Math.toIntExact(a + b)` là **sai thứ tự** nếu `a + b` đã tràn int: overload nhận long chỉ thấy kết quả int đã sai được chuyển sang long; phép kiểm tra có thể không phát hiện vấn đề.

### Chiến lược C — Dùng BigInteger khi long cũng không đủ

`long` có miền hữu hạn: `-9_223_372_036_854_775_808` đến `9_223_372_036_854_775_807`. Các phép long cộng/nhân vẫn có thể tràn.

Khi bài toán cần số nguyên lớn hơn miền long:

~~~java
import java.math.BigInteger;

BigInteger left = BigInteger.valueOf(Long.MAX_VALUE);
BigInteger answer = left.add(BigInteger.ONE);
System.out.println(answer); // 9223372036854775808
~~~

Đây là **mảnh code**, cần đặt trong lớp/phương thức để chạy. `BigInteger` có độ chính xác số nguyên tùy ý, giới hạn thực tế bởi bộ nhớ và tài nguyên hệ thống.

Nếu các toán hạng đã là `long`, chuyển **trước phép tính**, không phải sau khi long đã tràn:

~~~java
BigInteger aBig = BigInteger.valueOf(longA);
BigInteger bBig = BigInteger.valueOf(longB);
BigInteger correct = aBig.multiply(bBig);
~~~

`BigInteger.valueOf(longA * longB)` vẫn có thể nhận một kết quả long **đã tràn**, nên không có tác dụng bảo toàn phép nhân.

## 8. Những bẫy cùng bản chất: Math.abs, phép chia và phép phủ định

### 8.1. Math.abs(Integer.MIN_VALUE)

`Integer.MIN_VALUE` là `-2147483648`. Giá trị tuyệt đối toán học `2147483648` vượt `Integer.MAX_VALUE`:

~~~java
int min = Integer.MIN_VALUE;

long wrong = Math.abs(min);         // -2147483648
long correct = Math.abs((long) min); // 2147483648
~~~

`Math.abs(int)` trả int, nên không thể tạo ra số dương 2147483648. Cast đầu vào trước làm Java chọn `Math.abs(long)`, sau đó mới lấy trị tuyệt đối.

Đây cũng là ví dụ vì sao **chọn overload** dựa trên kiểu toán hạng có thể quan trọng: kiểu biến nhận `long` không làm phương thức `Math.abs(int)` trở thành `Math.abs(long)`.

### 8.2. Phủ định số int nhỏ nhất

~~~java
int min = Integer.MIN_VALUE;

long wrong = -min;        // -2147483648: phủ định int bị tràn
long correct = -(long) min; // 2147483648
~~~

Phép toán unary `-` trên biến int cũng cho kết quả int. Chuyển sau khi phủ định không sửa được kết quả. `Math.negateExact(min)` báo overflow, phù hợp khi kiểu đích bắt buộc int.

### 8.3. Chia Integer.MIN_VALUE cho -1

Đây là trường hợp đặc biệt của phép chia nguyên int:

~~~java
int min = Integer.MIN_VALUE;

long wrong = min / -1;          // -2147483648
long correct = (long) min / -1; // 2147483648
~~~

`-2147483648 / -1` có thương toán học `2147483648`, vượt miền int. Java quy định trường hợp này cho kết quả `Integer.MIN_VALUE` nếu phép chia được thực hiện bằng int. Trong khi đó, một toán hạng long chuyển phép chia sang long và cho thương đúng.

Một phép chia thông thường còn có rủi ro **cắt phần lẻ trước khi gán**:

~~~java
int numerator = 5;
int denominator = 2;

double wrong = numerator / denominator;          // 2.0
double correctApprox = (double) numerator / denominator; // 2.5
~~~

Đây không phải overflow; nguyên nhân vẫn là **phép toán trên kiểu nguồn hoàn tất trước khi kết quả được gán**. Nếu cần độ chính xác thập phân có quy tắc, dùng `BigDecimal.divide` với scale và `RoundingMode` phù hợp.

## 9. Ngữ cảnh gọi hàm cũng không tự cứu phép tính

Lỗi không chỉ xuất hiện trong phép gán:

~~~java
static void report(long value) {
    System.out.println(value);
}
~~~

Với `int a` và `int b`:

~~~java
report(a + b);         // a+b là int, có thể tràn, rồi mới truyền cho long
report((long) a + b);  // cộng bằng long trước khi truyền
~~~

Đây là các **mảnh mã** cần đặt trong lớp chứa phương thức `report` và các biến tương ứng.

Tương tự, API nhận `long` không tự nâng kiểu của một biểu thức con đã là `int`:

~~~java
long millis = 30 * 24 * 60 * 60 * 1000;   // int overflow
long fixedMillis = 30L * 24 * 60 * 60 * 1000; // long
~~~

Một cách tránh phép nhân thủ công khi chuyển đơn vị thời gian là chọn API thời gian phù hợp (ví dụ `Duration.ofDays(30).toMillis()`) và hiểu rõ ngữ nghĩa khoảng thời gian/đơn vị lịch. `Duration` tính độ dài thời gian theo đơn vị xác định; nó không đồng nghĩa tự cộng 30 **ngày lịch tại múi giờ cụ thể**, khi có chuyển giờ mùa hè (DST).

## 10. Tích lũy: kiểm tra kiểu của cả biến tổng lẫn từng phép cộng

Lỗi thường gặp trong thống kê và stream:

~~~java
int[] numbers = {1_500_000_000, 1_500_000_000, 1};

int sum = java.util.Arrays.stream(numbers).sum();
// -1294967295 vì sum của IntStream là int.

long wrong = java.util.Arrays.stream(numbers).sum();
// Vẫn -1294967295: gán rộng sau khi IntStream.sum() hoàn tất.

long correct = java.util.Arrays.stream(numbers)
        .asLongStream()
        .sum();
// 3000000001: mỗi phần tử được đưa vào phép cộng long.
~~~

`mapToLong(value -> value).sum()` cũng là lựa chọn để nâng từng phần tử trước khi cộng.

Trong vòng lặp, phải dùng biến tổng long **ngay từ đầu**:

~~~java
long total = 0L;
for (int number : numbers) {
    total += number; // long + int => long
}
~~~

Tuy nhiên `long total` không bảo đảm an toàn vô điều kiện: tổng của một danh sách đủ dài hoặc giá trị rất lớn vẫn có thể vượt miền long. Nếu trường hợp đó thực tế có thể xảy ra và không cho phép mất dữ liệu, dùng `Math.addExact(long, long)` cho từng lần cộng hoặc tích lũy bằng `BigInteger`.

## 11. Phân biệt overflow số nguyên với lỗi precision của float/double

Có người sửa bằng cách chuyển sang `double`:

~~~java
int a = 2_000_000_000;
int b = 1_500_000_000;

double wrong = a + b;            // -794967296.0
double betterHere = (double) a + b; // 3500000000.0
~~~

Đổi một toán hạng sang double trước phép cộng tránh overflow int trong trường hợp này; nhưng **double không giữ chính xác mọi giá trị số nguyên lớn**. `double` chỉ có 53 bit chữ số có nghĩa nhị phân, nên không nên dùng như giải pháp tổng quát cho tính toán số nguyên chính xác trong miền long.

Ví dụ:

~~~java
long n = 9_007_199_254_740_993L; // 2^53 + 1
double d = (double) n;            // Không biểu diễn đúng n.
~~~

Nếu cần kết quả nguyên chính xác của các phép toán trên int và kết quả vừa miền long, lựa chọn tự nhiên là **long**, không phải double. Nếu long không đủ, hãy chuyển sang `BigInteger` trước khi tính.

Cũng đừng dùng `(long) (doubleExpression)` để tự động “phục hồi” chữ số đã mất trong `double`: chuyển kiểu ngược không tạo lại thông tin ban đầu.

## 12. Điều kiện phát hiện overflow và giới hạn kiểu kết quả

Có hai mục tiêu khác nhau:

### A. Muốn một kết quả rộng và chính xác

~~~java
int a = Integer.MAX_VALUE;
int b = 1;

long total = (long) a + b; // 2147483648
~~~

### B. Muốn giữ kết quả int và từ chối nếu không biểu diễn được

~~~java
int a = Integer.MAX_VALUE;
int b = 1;

// int total = Math.addExact(a, b); // ArithmeticException
~~~

Khi ứng dụng yêu cầu báo lỗi thay vì tự động chuyển sang long, `Math.addExact` phù hợp hơn.

Có thể kiểm tra thủ công bằng cách tính bằng long rồi so biên:

~~~java
static int checkedAdd(int a, int b) {
    long exact = (long) a + b;
    if (exact < Integer.MIN_VALUE || exact > Integer.MAX_VALUE) {
        throw new ArithmeticException("int overflow");
    }
    return (int) exact;
}
~~~

Với **tổng của hai int**, long luôn chứa được kết quả toán học, nên kiểm tra biên trên long là chính xác. Phương thức `Math.addExact(a, b)` ngắn gọn hơn và đã được chuẩn hóa.

Trường hợp `Math.toIntExact(wide)` cũng hợp lệ khi biến `wide` thật sự chứa giá trị đúng từ một phép tính rộng hoặc từ dữ liệu ngoài:

~~~java
long wide = (long) a + b;
int value = Math.toIntExact(wide); // Ném ArithmeticException nếu ngoài int.
~~~

Điểm quan trọng là biến `wide` phải được tạo **trước khi overflow**, chứ không phải `long wide = a + b`.

## 13. Những lỗi phổ biến cần nhận diện ngay khi review code

| Mã dễ sai | Lý do | Mã thay thế / điều kiện |
| --- | --- | --- |
| `long s = a + b;` với hai int | Tổng int có thể tràn trước khi gán | `long s = (long) a + b;` |
| `long p = a * b;` | Tích int có thể tràn | `long p = (long) a * b;` |
| `long p = (long)(a * b);` | Cast quá muộn | `long p = (long)a * b;` |
| `long p = a * b * 1L;` | `a*b` đã tính trước | `long p = 1L*a*b;` |
| `Math.toIntExact(a + b)` | `a+b` đã tràn trong int nên kiểm tra không thấy | `Math.addExact(a,b)` hoặc `Math.toIntExact((long)a+b)` |
| `long x = Math.abs(intValue);` | `Math.abs(int)` có thể tràn tại MIN_VALUE | `long x = Math.abs((long)intValue);` |
| `long x = -intValue;` | Unary negation vẫn tính bằng int | `long x = -(long)intValue;` |
| `long m = 30*24*60*60*1000;` | Toàn literal int; phép nhân tràn | `long m = 30L*24*60*60*1000;` |
| `long sum = intStream.sum();` | `sum()` của IntStream trả int | `long sum = intStream.asLongStream().sum();` |

Trong code review, đừng chỉ hỏi “biến cuối cùng có phải long không?”. Hãy đi ngược lên từng biểu thức, phương thức, overload và thao tác trung gian, rồi xác định **kiểu tại lúc phép tính thực sự chạy**.

## 14. Phép tràn có thể không tạo số âm rõ ràng

Không phải overflow nào cũng lộ ra như một số âm khiến người lập trình nghi ngờ. Kết quả sau wrap có thể là **số dương trông hợp lý**, **số 0**, hoặc một giá trị bất kỳ trong miền int.

Ví dụ:

~~~java
int value = Integer.MAX_VALUE;
int doubled = value * 2; // -2
~~~

Nhưng khi cộng tiếp nhiều giá trị, kết quả có thể vòng qua miền và trở lại giá trị dương. Việc thấy “kết quả dương”, “kết quả không ném lỗi”, hoặc “gán được vào long” không bảo đảm phép tính chính xác.

Không nên lấy dấu của kết quả hay ngưỡng tùy tiện làm bộ phát hiện overflow tổng quát. Ví dụ `result < 0` không phải dấu hiệu đầy đủ vì các toán hạng có thể âm hợp lệ, và overflow có thể cho số dương. Dùng `Math.*Exact` hoặc tính trước bằng kiểu đủ rộng và so phạm vi.

## 15. Bài tập có đáp án

### Bài 1: Sửa một phép nhân diện tích

~~~java
int width = 70_000;
int height = 70_000;
long area = width * height;
~~~

**Đáp án:** `long area = (long) width * height;`, kết quả chính xác `4_900_000_000`. Bản ban đầu thực hiện phép nhân int trước và có thể cho số sai.

### Bài 2: Dự đoán giá trị

~~~java
int a = 2_000_000_000;
int b = 1_500_000_000;

long first = a + b;
long second = (long) a + b;
long third = (long) (a + b);
~~~

**Đáp án:** `first = -794967296`, `second = 3500000000`, `third = -794967296`. Chỉ `second` chuyển một toán hạng trước khi tính.

### Bài 3: Vì sao Math.toIntExact vẫn có thể không bắt được lỗi?

~~~java
int a = 2_000_000_000;
int b = 1_500_000_000;
int result = Math.toIntExact(a + b);
~~~

**Đáp án:** `a+b` đã tràn int thành `-794967296`. Khi đối số được chuyển thành long để truyền cho `toIntExact`, nó vẫn nằm trong miền int; `toIntExact` trả chính giá trị âm ấy và **không báo lỗi**. Sửa thành `Math.addExact(a,b)` (sẽ ném exception) hoặc `Math.toIntExact((long)a+b)`.

### Bài 4: Tổng stream

Với `int[] values = {1_500_000_000, 1_500_000_000, 1}`, tại sao `long sum = Arrays.stream(values).sum();` không đúng?

**Đáp án:** `IntStream.sum()` hoàn tất phép cộng theo int rồi mới chuyển kết quả sang long. Dùng `Arrays.stream(values).asLongStream().sum()` để cộng thành long từ đầu, kết quả `3000000001`.

### Bài 5: Trị tuyệt đối

Vì sao `long magnitude = Math.abs(Integer.MIN_VALUE);` âm?

**Đáp án:** Overload `Math.abs(int)` trả int và không thể biểu diễn trị tuyệt đối toán học của `Integer.MIN_VALUE`. Sửa `Math.abs((long) Integer.MIN_VALUE)` để nhận `2147483648`.

### Bài 6: Cách chọn chính sách lỗi

Một API trả `int` bắt buộc, yêu cầu tổng `a+b` không được mất dữ liệu. Nên chọn kiểu long và ép lại không kiểm tra, hay gọi `Math.addExact`?

**Đáp án:** Gọi `Math.addExact(a,b)` để từ chối trường hợp vượt int. Nếu yêu cầu nghiệp vụ cho phép tổng lớn hơn và kiểu kết quả có thể là long, dùng `(long)a+b`. Chọn theo **hợp đồng dữ liệu đích**, không theo thói quen cast.

## 16. Checklist trước khi gán kết quả tính toán số nguyên

1. **Hai toán hạng tại từng phép cộng/nhân/trừ/chia đang có kiểu gì?** Có `int` ở một phép trung gian không?
2. **Kiểu rộng có xuất hiện trước phép toán rủi ro chưa?** `(long)(a*b)` không thay thế cho `(long)a*b`.
3. **Các dấu ngoặc và thứ tự kết hợp có tạo phần `int` đã tràn trước khi gặp long không?**
4. **Có overload phương thức trả int không?** Đặc biệt `Math.abs(int)`, `IntStream.sum()`, `Math.max(int,int)`.
5. **Có tính qua literal int trước khi gán long không?** Dùng `L` đúng vị trí hoặc API chuyên biệt.
6. **Hợp đồng muốn kết quả rộng hay phát hiện overflow?** Chọn `long`, `Math.*Exact` hoặc `BigInteger` phù hợp.
7. **Nếu phép tính đã xảy ra rồi, còn giữ các toán hạng gốc để tính lại chính xác không?** Cast kết quả sai không thể khôi phục dữ liệu.
8. **Đã test sát biên chưa?** `Integer.MAX_VALUE + 1`, `Integer.MIN_VALUE`, phép nhân lớn, cộng dồn dài, `MIN_VALUE / -1`.

**Kết luận:** Trong Java, **kiểu biến nhận không quyết định kiểu của phép toán trước đó**. `long result = a + b` vẫn tính int nếu `a` và `b` là int, và một khi biểu thức đó đã tràn, chuyển thành long chỉ lưu **giá trị đã tràn**. Muốn đúng, **nâng ít nhất một toán hạng trước phép toán**, dùng `Math.*Exact` để phát hiện lỗi khi phải giữ int, hoặc dùng `BigInteger` nếu long cũng không đủ.
