# BigInteger, BigDecimal và các lớp Number khác trong JDK

Java có các kiểu nguyên thủy `byte`, `short`, `int`, `long`, `float`, `double` để lưu số trong miền và độ chính xác hữu hạn. Khi những kiểu này không đáp ứng yêu cầu, JDK cung cấp các **lớp đối tượng biểu diễn số**: wrapper như `Integer`/`Double`, số nguyên độ lớn tùy ý `BigInteger`, số thập phân độ chính xác tùy ý `BigDecimal`, cùng các bộ đếm phục vụ lập trình đồng thời như `AtomicInteger`, `AtomicLong` và `LongAdder`.

Nhiều lớp trong số đó kế thừa lớp trừu tượng `java.lang.Number`, nhưng **cùng là Number không có nghĩa chúng có cùng miền giá trị, độ chính xác, tính bất biến, quy tắc bằng nhau hay cách thực hiện phép toán**. Cần chọn kiểu theo ngữ nghĩa dữ liệu và hiểu rõ giới hạn của mỗi API.

## 1. Bức tranh tổng quan

| Nhóm | Các lớp tiêu biểu | Mục đích chính | Những điều cần lưu ý |
| --- | --- | --- | --- |
| Primitive | `byte`, `short`, `int`, `long`, `float`, `double` | Phép toán số học trực tiếp bằng toán tử | Miền cố định; `float`/`double` có sai số biểu diễn |
| Wrapper của primitive số | `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double` | Biểu diễn số bằng đối tượng, generic, collection, boxing | Bất biến; chuyển đổi và so sánh cần để ý kiểu |
| Số nguyên lớn | `java.math.BigInteger` | Số nguyên chính xác vượt `long` | Bất biến; giới hạn thực tế là tài nguyên bộ nhớ/CPU |
| Số thập phân lớn | `java.math.BigDecimal` | Số thập phân chính xác theo cách biểu diễn thập phân và quy tắc làm tròn | Bất biến; phân biệt `scale`, `precision`, `equals` và `compareTo` |
| Bộ đếm đồng thời | `AtomicInteger`, `AtomicLong` | Cập nhật giá trị số nguyên với thao tác nguyên tử | Có thể thay đổi trạng thái; không phải số lớn tùy ý |
| Bộ cộng dồn đồng thời | `LongAdder`, `DoubleAdder`, `LongAccumulator`, `DoubleAccumulator` | Tổng/bộ tích lũy dưới cạnh tranh luồng cao | Có trạng thái; giá trị đọc có thể không phải snapshot nguyên tử |

Những lớp trên nằm trong các package khác nhau: wrapper và `Number` ở `java.lang`, hai lớp lớn ở `java.math`, còn nhóm atomic/adder/accumulator ở `java.util.concurrent.atomic`.

## 2. java.lang.Number là gì?

`Number` là một **lớp trừu tượng** đại diện cho những đối tượng có thể cung cấp giá trị dưới dạng các kiểu số nguyên thủy. Bốn phương thức trừu tượng quan trọng là:

~~~java
public abstract int intValue();
public abstract long longValue();
public abstract float floatValue();
public abstract double doubleValue();
~~~

Ngoài ra `Number` có `byteValue()` và `shortValue()` dạng phương thức cụ thể, về cơ bản dựa trên chuyển đổi thu hẹp từ `intValue()` trừ khi lớp con cung cấp cách triển khai riêng.

Bạn có thể dùng tham chiếu `Number` cho nhiều loại đối tượng:

~~~java
Number count = Integer.valueOf(42);
Number pi = Double.valueOf(3.14);
Number huge = new java.math.BigInteger("12345678901234567890");
Number amount = new java.math.BigDecimal("19.95");
~~~

Các phương thức `intValue()`, `longValue()`, `floatValue()`, `doubleValue()` hỗ trợ chuyển đổi **giá trị**, nhưng không tự đảm bảo chuyển đổi chính xác hay bảo toàn toàn bộ miền số. Ví dụ, `new BigDecimal("1.99").intValue()` trả 1: phần thập phân bị bỏ đi.

**Number không cung cấp phép toán đa hình tổng quát**. Một biến `Number` không có phương thức `add(Number)` trong lớp cơ sở, và Java không cho áp dụng toán tử `+` trực tiếp giữa hai tham chiếu `Number` theo nghĩa số học tổng quát.

~~~java
Number a = Integer.valueOf(2);
Number b = Long.valueOf(3);
// Number result = a + b; // Lỗi: không có toán tử cộng chung cho Number
~~~

Cần quyết định toán học cụ thể (số nguyên chính xác, số thực dấu phẩy động, thập phân...) trước khi thực hiện phép tính. Không nên tự động đưa mọi `Number` về `double` rồi tính nếu chương trình đòi bảo toàn chữ số.

### 2.1. Number là kiểu tham chiếu, không phải kiểu số nguyên thủy

Bạn không thể viết `Number x = 42.5 + 1.0` rồi kỳ vọng Number tự chọn một hệ số học đa hình. Biểu thức nguyên thủy được tính trước bằng `double` và **boxing** thành `Double` khi được gán vào `Number`.

~~~java
Number x = 42;      // int -> Integer (boxing) -> Number
Number y = 3.5;     // double -> Double (boxing) -> Number
System.out.println(x.getClass().getSimpleName()); // Integer
System.out.println(y.getClass().getSimpleName()); // Double
~~~

Java hỗ trợ boxing tự động cho primitive và wrapper tương ứng, nhưng **không tự động boxing `int` thành `BigInteger`** hoặc `double` thành `BigDecimal`. Hai lớp này cần factory/constructor riêng.

### 2.2. Number không hàm ý bất biến

`Integer`, `Long`, `BigInteger` và `BigDecimal` bất biến: phép tính tạo đối tượng kết quả mới. Nhưng `AtomicInteger`/`LongAdder` cũng là `Number` và có trạng thái thay đổi.

Vì thế, nếu API nhận `Number`, đừng mặc định rằng giá trị của đối tượng luôn giữ nguyên giữa hai lần gọi `doubleValue()`. Mức đồng thời và độ nhất quán phải theo hợp đồng của lớp cụ thể.

## 3. BigInteger: số nguyên độ lớn tùy ý

`BigInteger` biểu diễn số nguyên có dấu với độ chính xác tùy ý theo giới hạn khả thi của bộ nhớ/CPU và giới hạn triển khai. Nó phù hợp khi `long` (miền -2^63 đến 2^63-1) không đủ lớn: hệ đếm tổ hợp, mật mã học, số nguyên cực lớn, thuật toán cần kết quả nguyên chính xác.

Tạo đối tượng:

~~~java
import java.math.BigInteger;

BigInteger a = new BigInteger("123456789012345678901234567890");
BigInteger b = BigInteger.valueOf(42L);
BigInteger zero = BigInteger.ZERO;
BigInteger one = BigInteger.ONE;
BigInteger ten = BigInteger.TEN;
~~~

Dùng chuỗi thập phân để tạo số quá miền `long`. `BigInteger.valueOf(long)` tiện với giá trị `long` có sẵn, nhưng đầu vào của nó vẫn bị giới hạn bởi `long`. Không có constructor `new BigInteger(long)`.

### 3.1. Phép toán trên BigInteger

Vì là đối tượng, `BigInteger` không hỗ trợ toán tử `+`, `-`, `*`, `/` như primitive. Sử dụng phương thức:

| Mục tiêu | Phương thức |
| --- | --- |
| Cộng, trừ | `add(...)`, `subtract(...)` |
| Nhân, chia lấy phần nguyên | `multiply(...)`, `divide(...)` |
| Số dư | `remainder(...)`; `mod(...)` với mô-đun dương |
| Lũy thừa | `pow(int exponent)` (số mũ nguyên không âm) |
| UCLN | `gcd(...)` |
| Dịch bit | `shiftLeft(n)`, `shiftRight(n)` |
| Lũy thừa mô-đun | `modPow(exponent, modulus)` |
| So sánh | `compareTo(...)`, `equals(...)` |

~~~java
BigInteger a = new BigInteger("100000000000000000000");
BigInteger b = BigInteger.valueOf(3);
BigInteger sum = a.add(b);
BigInteger quotient = a.divide(b);
BigInteger remainder = a.remainder(b);
BigInteger square = b.pow(2);
~~~

Đây là đoạn minh họa cần đặt trong lớp Java và có import `java.math.BigInteger`. Với `divide`, thương là **số nguyên**, phần dư bị tách riêng. Nó không tạo ra phân số hay số thập phân như `BigDecimal`. Chia cho số 0 ném `ArithmeticException`.

**Phân biệt `remainder` và `mod`:** `remainder` có dấu theo phép chia số nguyên; `mod` yêu cầu mô-đun dương và trả kết quả không âm. Đừng thay thế vô điều kiện hai phương thức trong thuật toán xử lý số âm.

### 3.2. Bất biến và phép cộng bị bỏ quên

~~~java
BigInteger n = BigInteger.TEN;
n.add(BigInteger.ONE);        // Kết quả mới bị bỏ đi; n vẫn bằng 10
n = n.add(BigInteger.ONE);    // n trỏ đến đối tượng bằng 11
~~~

Lỗi tương tự xảy ra với `BigDecimal`. Trong JDK, cả hai đều là đối tượng **immutable**, nên bản thân lời gọi `add` không sửa đối tượng cũ.

### 3.3. Chuyển về primitive có thể làm mất dữ liệu

~~~java
BigInteger huge = BigInteger.ONE.shiftLeft(40); // 2^40
int truncated = huge.intValue();                // 0, chỉ còn 32 bit thấp
// int exact = huge.intValueExact();            // ném ArithmeticException
~~~

Các API an toàn hơn khi yêu cầu giữ nguyên giá trị gồm `intValueExact()`, `longValueExact()`, `shortValueExact()` và `byteValueExact()`. Chúng ném `ArithmeticException` nếu số nguyên không vừa kiểu đích.

Chuyển về `float` hoặc `double` có thể làm tròn hoặc thành vô cực với số quá lớn. Vì vậy, nếu cần giữ số nguyên chính xác, đừng lưu kết quả BigInteger vào `double` để “tiện tính tiếp”.

## 4. BigDecimal: số thập phân chính xác theo unscaled value và scale

`BigDecimal` biểu diễn một số thập phân dưới dạng **số nguyên không giới hạn độ lớn mang dấu (unscaled value)** kết hợp với **scale**:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

Ví dụ:

- `new BigDecimal("12.34")` có `unscaledValue() = 1234` và `scale() = 2`.
- `new BigDecimal("2.00")` có `unscaledValue() = 200` và `scale() = 2`.
- `new BigDecimal("2.0")` có `unscaledValue() = 20` và `scale() = 1`.
- Hai giá trị `2.00` và `2.0` giống nhau về số học, nhưng **biểu diễn scale khác nhau**.

`BigDecimal` giúp biểu diễn **chính xác giá trị thập phân đã nhập** và thực hiện các phép toán có kiểm soát độ chính xác/làm tròn. “Độ chính xác tùy ý” không có nghĩa mọi phép chia đều cho kết quả thập phân hữu hạn, hoặc mọi phép tính đều vô hạn tài nguyên và không cần chính sách làm tròn.

### 4.1. Tạo BigDecimal: ưu tiên chuỗi thập phân

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");    // Giá trị thập phân 0.1 chính xác
BigDecimal b = new BigDecimal("0.2");    // Giá trị thập phân 0.2 chính xác
BigDecimal sum = a.add(b);               // Chính xác 0.3
BigDecimal c = BigDecimal.valueOf(0.1);  // Tạo từ Double.toString(0.1): "0.1"
~~~

Đặc biệt cần hiểu:

~~~java
BigDecimal exactDecimal = new BigDecimal("0.1");
BigDecimal fromBinary = new BigDecimal(0.1);
BigDecimal fromValueOf = BigDecimal.valueOf(0.1);
~~~

`new BigDecimal(0.1)` nhận trực tiếp **giá trị nhị phân double** của literal 0.1 (vốn không chính xác bằng 0.1 thập phân), nên nó biểu diễn giá trị nhị phân đó ở dạng thập phân rất dài. `BigDecimal.valueOf(0.1)` dùng biểu diễn chuỗi chuẩn của `double` rồi chuyển sang `BigDecimal`, nên trong ví dụ cho giá trị `0.1` thập phân mong muốn.

Điều này không có nghĩa `BigDecimal.valueOf(double)` khôi phục được mọi thông tin thập phân gốc đã mất khi chuyển sang `double`. **Khi đầu vào ban đầu là chuỗi số thập phân, hãy parse trực tiếp chuỗi đó thành BigDecimal** để tránh mất độ chính xác trước bước chuyển đổi.

Với dữ liệu nguyên đã có trong `long`, có thể dùng `BigDecimal.valueOf(long)`; với `BigInteger`, dùng `new BigDecimal(bigInteger)`. Không có chuyển đổi tự động từ primitive sang `BigDecimal`.

### 4.2. Phép toán và chính sách làm tròn

Những phương thức cơ bản:

~~~java
BigDecimal price = new BigDecimal("19.95");
BigDecimal quantity = new BigDecimal("3");
BigDecimal total = price.multiply(quantity);    // 59.85
BigDecimal discounted = total.subtract(new BigDecimal("1.50")); // 58.35
~~~

`add`, `subtract` và `multiply` có thể cho kết quả thập phân chính xác với các toán hạng đã biểu diễn, nếu không giới hạn thêm bằng `MathContext`. **Chia** phức tạp hơn: nhiều thương không có khai triển thập phân hữu hạn, điển hình `1 / 3`.

~~~java
BigDecimal numerator = BigDecimal.ONE;
BigDecimal denominator = new BigDecimal("3");

// numerator.divide(denominator); // ArithmeticException: thương không kết thúc
BigDecimal ratio = numerator.divide(
        denominator, 2, java.math.RoundingMode.HALF_UP); // 0.33
~~~

Khi cần chỉ rõ số chữ số sau dấu thập phân, dùng `divide(divisor, scale, roundingMode)` hoặc `setScale(scale, roundingMode)`. Khi muốn giới hạn **số chữ số có nghĩa**, dùng `MathContext`:

~~~java
import java.math.MathContext;
import java.math.RoundingMode;

MathContext context = new MathContext(5, RoundingMode.HALF_EVEN);
BigDecimal third = BigDecimal.ONE.divide(new BigDecimal("3"), context);
// Giá trị: 0.33333 (5 chữ số có nghĩa)
~~~

Cẩn thận phân biệt:

- **Scale:** số chữ số thập phân theo phép biểu diễn `unscaled × 10^-scale`; có thể âm.
- **Precision:** số chữ số có nghĩa của phần unscaled biểu diễn bằng chữ số thập phân (bỏ qua dấu).
- **RoundingMode:** luật xử lý phần phải bỏ đi, ví dụ `HALF_UP` hay `HALF_EVEN`.
- **MathContext:** precision và rounding mode áp dụng khi thực hiện những phép tính nhận context.

Ví dụ `new BigDecimal("123.45").setScale(1, RoundingMode.HALF_UP)` trả `123.5`. Trong ứng dụng tài chính, một scale 2 và một rounding mode được thống nhất phải đến từ **quy định nghiệp vụ, loại tiền, hợp đồng hoặc chính sách hệ thống**, không phải luôn mặc định một cách tùy ý.

### 4.3. equals khác compareTo

Đây là bẫy quan trọng nhất của `BigDecimal` khi đưa vào collection:

~~~java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.equals(b));       // false
System.out.println(a.compareTo(b));    // 0
~~~

`equals` đòi cùng **giá trị số và scale**; `compareTo` so sánh theo **giá trị số**, bỏ qua khác biệt scale. Vì thế:

- `HashSet<BigDecimal>` dùng `equals`/`hashCode` nên có thể chứa cả `2.0` và `2.00` như hai phần tử.
- `TreeSet<BigDecimal>` theo thứ tự tự nhiên `compareTo` sẽ coi chúng là cùng một khóa, nên chỉ giữ một phần tử.
- Để kiểm tra hai BigDecimal bằng nhau về **mặt số học**, dùng `a.compareTo(b) == 0`. Để kiểm tra cùng biểu diễn (bao gồm scale), dùng `a.equals(b)`.
- `stripTrailingZeros()` có thể chuẩn hóa phần zero cuối nhưng cũng có thể làm scale âm hoặc đổi dạng chuỗi sang ký hiệu khoa học, ví dụ số nguyên có nhiều zero. Không tự động chuẩn hóa trên toàn hệ thống nếu scale mang ý nghĩa nghiệp vụ.

Hai collection có hành vi khác nhau là kết quả từ hợp đồng API, không phải lỗi Java.

### 4.4. Chuyển BigDecimal sang kiểu nguyên

~~~java
BigDecimal amount = new BigDecimal("1.99");
int truncated = amount.intValue();    // 1: bỏ phần thập phân
// int exact = amount.intValueExact(); // ném ArithmeticException
~~~

`intValue()` có thể bỏ phần lẻ và/hoặc mất bit cao nếu giá trị ngoài miền. `intValueExact()` yêu cầu vừa miền kiểu `int` **và không có phần lẻ khác 0**. Các phương thức `longValueExact()` và `toBigIntegerExact()` tương tự khi cần bảo toàn số nguyên.

`toBigInteger()` không làm tròn: nó bỏ phần lẻ theo hướng về 0. Nếu phải làm tròn rồi lấy số nguyên, hãy chọn `setScale(0, roundingMode)` trước và sau đó chuyển đổi exact theo yêu cầu.

### 4.5. Hiển thị BigDecimal

`toString()` có thể dùng ký hiệu số mũ; `toPlainString()` không dùng ký hiệu số mũ; `toEngineeringString()` có quy tắc khác phù hợp biểu diễn kỹ thuật. Các phương thức này liên quan **chuỗi hiển thị**, không làm thay đổi đối tượng.

Đừng dùng việc format chuỗi hoặc làm tròn khi hiển thị như bằng chứng rằng tính toán nội bộ đã chính xác đến số chữ số đó. Khi xuất dữ liệu thanh toán, cũng cần quy tắc về scale, làm tròn và định dạng theo miền ứng dụng.

## 5. Những lớp Number khác trong JDK

### 5.1. Primitive wrapper: Byte, Short, Integer, Long, Float, Double

Sáu wrapper đều kế thừa `Number`; chúng đại diện cho giá trị primitive tương ứng nhưng là **đối tượng bất biến**. Chúng cần thiết khi dùng generics/collection hoặc khi API yêu cầu kiểu tham chiếu:

~~~java
java.util.List<Integer> ids = java.util.List.of(1, 2, 3);
Number first = ids.get(0);
long converted = first.longValue();
~~~

Các wrapper cung cấp factory như `Integer.valueOf(...)`, parser như `Integer.parseInt(...)`, phương thức chuyển đổi và các hằng MIN/MAX. Chúng có cùng giới hạn số học của primitive nền:

- `Integer`/`Long` không thay thế được `BigInteger` nếu cần số nguyên vượt miền.
- `Float`/`Double` vẫn có sai số nhị phân, NaN và vô cực; là wrapper không biến phép tính thành thập phân chính xác.
- `equals` của wrapper quan tâm **kiểu đối tượng**, ví dụ `Integer.valueOf(1).equals(Long.valueOf(1L))` là `false` dù số học cùng 1.
- Boxing và unboxing không phải lúc nào cũng miễn phí, và unboxing một tham chiếu `null` có thể gây `NullPointerException`.

Đối với danh sách `List<Number>` có nhiều kiểu con, đừng giả định mọi phần tử sẽ so sánh bằng nhau bằng `equals` nếu chúng mang giá trị toán học bằng nhau.

### 5.2. AtomicInteger và AtomicLong

`java.util.concurrent.atomic.AtomicInteger` và `AtomicLong` kế thừa `Number`, nhưng có trạng thái **mutable** và các phương thức cập nhật nguyên tử (atomic), ví dụ `incrementAndGet()`, `getAndAdd(...)` và `compareAndSet(...)`.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger requests = new AtomicInteger(7);
int updated = requests.incrementAndGet(); // 8
Number asNumber = requests;
int snapshot = asNumber.intValue();       // 8 tại thời điểm đọc
~~~

Chúng phù hợp cho counter/biến trạng thái cần cập nhật đồng thời trong miền `int` hoặc `long`, không phải “BigInteger có thể tự cập nhật”. Phép tăng có thể tràn miền như số nguyên primitive; nó không tự mở rộng thành số lớn.

### 5.3. LongAdder, DoubleAdder và Accumulator

Nhóm `LongAdder`/`DoubleAdder` được thiết kế để cộng dồn hiệu quả khi có nhiều luồng cạnh tranh. `LongAccumulator` và `DoubleAccumulator` cho phép phép tích lũy theo một hàm kết hợp đã chỉ định cùng giá trị khởi tạo.

~~~java
import java.util.concurrent.atomic.LongAdder;

LongAdder hits = new LongAdder();
hits.add(10);
hits.increment();

Number n = hits;
System.out.println(n.longValue()); // 11 trong ví dụ chạy tuần tự
~~~

`LongAdder.sum()` lấy một giá trị quan sát được, nhưng **không phải snapshot nguyên tử** khi các luồng khác đang cập nhật. Nó hợp cho thống kê/counter throughput cao, không nên được xem như thay thế trực tiếp cho giao dịch cần kiểm tra-cập nhật chính xác cùng thời điểm.

`DoubleAdder` tích lũy số thực nhị phân nên kết quả vẫn chịu sai số làm tròn và có thể phụ thuộc thứ tự cập nhật. Nó không thay `BigDecimal` trong bài toán thập phân chính xác.

Cả nhóm atomic lẫn adder chứng minh một điều cốt lõi: **kế thừa Number không đồng nghĩa đối tượng immutable hay phép đọc luôn phản ánh một trạng thái toàn cục cố định**.

## 6. Ví dụ chạy độc lập bằng Java 17+

Tạo tệp **NumberFamiliesDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.MathContext;
import java.math.RoundingMode;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;

public class NumberFamiliesDemo {
    public static void main(String[] args) {
        Number boxed = Integer.valueOf(42);
        System.out.println("Number intValue: " + boxed.intValue());

        BigInteger large = new BigInteger("123456789012345678901234567890");
        System.out.println("BigInteger + 10: " + large.add(BigInteger.TEN));
        System.out.println("2^100 bits: " + BigInteger.ONE.shiftLeft(100).bitLength());
        System.out.println("2^40 intValue: " + BigInteger.ONE.shiftLeft(40).intValue());
        try {
            BigInteger.ONE.shiftLeft(40).intValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("BigInteger exact conversion: overflow");
        }

        BigDecimal decimalSum = new BigDecimal("0.1").add(new BigDecimal("0.2"));
        System.out.println("decimal 0.1 + 0.2: " + decimalSum.toPlainString());
        System.out.println("from double exact? "
                + new BigDecimal(0.1).equals(new BigDecimal("0.1")));
        System.out.println("valueOf double: "
                + BigDecimal.valueOf(0.1).toPlainString());

        BigDecimal one = new BigDecimal("2.0");
        BigDecimal two = new BigDecimal("2.00");
        System.out.println("equals with scale: " + one.equals(two));
        System.out.println("compareTo with scale: " + one.compareTo(two));

        System.out.println("1 / 3 (scale 2): "
                + BigDecimal.ONE.divide(new BigDecimal("3"), 2, RoundingMode.HALF_UP));
        System.out.println("1 / 3 (precision 5): "
                + BigDecimal.ONE.divide(new BigDecimal("3"),
                        new MathContext(5, RoundingMode.HALF_EVEN)));
        try {
            BigDecimal.ONE.divide(new BigDecimal("3"));
        } catch (ArithmeticException ex) {
            System.out.println("1 / 3 without rounding: non-terminating");
        }

        System.out.println("rounded scale: "
                + new BigDecimal("123.45").setScale(1, RoundingMode.HALF_UP));
        System.out.println("intValue truncates: " + new BigDecimal("1.99").intValue());
        try {
            new BigDecimal("1.99").intValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("BigDecimal exact conversion: fractional");
        }

        Set<BigDecimal> hash = new HashSet<>();
        Set<BigDecimal> sorted = new TreeSet<>();
        hash.add(one);
        hash.add(two);
        sorted.add(one);
        sorted.add(two);
        System.out.println("HashSet size: " + hash.size());
        System.out.println("TreeSet size: " + sorted.size());

        AtomicInteger counter = new AtomicInteger(7);
        System.out.println("AtomicInteger increment: " + counter.incrementAndGet());
        LongAdder adder = new LongAdder();
        adder.add(10);
        adder.increment();
        Number accumulator = adder;
        System.out.println("LongAdder as Number: " + accumulator.longValue());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac NumberFamiliesDemo.java
java NumberFamiliesDemo
~~~

Đầu ra chính xác:

~~~text
Number intValue: 42
BigInteger + 10: 123456789012345678901234567900
2^100 bits: 101
2^40 intValue: 0
BigInteger exact conversion: overflow
decimal 0.1 + 0.2: 0.3
from double exact? false
valueOf double: 0.1
equals with scale: false
compareTo with scale: 0
1 / 3 (scale 2): 0.33
1 / 3 (precision 5): 0.33333
1 / 3 without rounding: non-terminating
rounded scale: 123.5
intValue truncates: 1
BigDecimal exact conversion: fractional
HashSet size: 2
TreeSet size: 1
AtomicInteger increment: 8
LongAdder as Number: 11
~~~

Chương trình minh họa đồng thời ba khác biệt cần ghi nhớ: `BigInteger` giữ được số nguyên lớn nhưng `intValue()` không giữ toàn bộ; `BigDecimal` giữ giá trị thập phân và phân biệt scale ở `equals`; còn `AtomicInteger`/`LongAdder` là các lớp `Number` **có trạng thái**, phục vụ cập nhật/bộ đếm thay vì số học độ chính xác tùy ý.

## 7. Chọn kiểu nào cho bài toán?

| Nhu cầu | Lựa chọn thường phù hợp | Vì sao |
| --- | --- | --- |
| Đếm, chỉ số, số nguyên trong miền đã xác định | `int` hoặc `long` | Nhanh, cú pháp đơn giản; cần kiểm soát tràn |
| Số nguyên cực lớn/chính xác | `BigInteger` | Số nguyên tùy ý độ lớn; có kiểm tra chuyển đổi exact |
| Giá trị thập phân chính xác theo input/đặc tả | `BigDecimal` | Có mô hình scale và rounding mode |
| Tính toán gần đúng quy mô khoa học/kỹ thuật | `double` (hoặc `float` khi có yêu cầu) | Nhanh và phù hợp IEEE 754 nếu quản lý sai số |
| Truyền số vào API tổng quát chỉ cần đọc | `Number` hoặc generic theo mục đích | Abstraction, nhưng phải quy định chuyển đổi |
| Counter chia sẻ giữa nhiều thread | `AtomicInteger`/`AtomicLong` | Cập nhật nguyên tử |
| Counter thống kê contention cao | `LongAdder` | Có thể giảm contention, chấp nhận semantics snapshot |

Nếu hệ thống xử lý tiền, `BigDecimal` **không tự đảm bảo nghiệp vụ tiền tệ đúng**: vẫn cần xác định đơn vị, scale, loại tiền, cách làm tròn, thời điểm làm tròn, quy định thuế/phí và cách serialize. Với một số thiết kế, lưu số tiền dưới dạng **số nguyên đơn vị nhỏ nhất** (như số xu) bằng `long`/`BigInteger` có thể phù hợp hơn.

Nếu cần số học chính xác phân số như `1/3`, `BigDecimal` hữu hạn cũng không lưu được kết quả thập phân vô hạn chính xác trong một giá trị hữu hạn. Bạn phải chọn làm tròn, hoặc sử dụng mô hình **phân số hữu tỉ** có tử và mẫu là `BigInteger` (tự xây dựng hoặc thư viện phù hợp), tùy yêu cầu.

## 8. Những lỗi phổ biến và cách tránh

**Lỗi 1 — Dùng `new BigDecimal(double)` cho số tiền thập phân.**  
Giá trị `double` đã trải qua chuyển đổi nhị phân có thể không biểu diễn chính xác dữ liệu gốc. Khi đầu vào là chuỗi thập phân, tạo trực tiếp từ chuỗi; khi lấy từ `double`, hiểu giới hạn của `BigDecimal.valueOf(double)`.

**Lỗi 2 — Cho rằng `Number.doubleValue()` luôn giữ nguyên số.**  
BigInteger nhiều chữ số có thể mất độ chính xác khi thành `double`; BigDecimal chuyển thành `double` cũng có thể làm tròn/overflow. Đừng dùng `doubleValue()` như lớp chuyển đổi chung khi cần kết quả exact.

**Lỗi 3 — Quên BigInteger/BigDecimal bất biến.**  
`amount.add(extra)` không đổi `amount`; phải dùng `amount = amount.add(extra)` hoặc lưu đối tượng kết quả riêng.

**Lỗi 4 — Gọi `BigDecimal.divide` không có chính sách làm tròn cho 1/3.**  
Phép chia chính xác không có khai triển thập phân kết thúc sẽ ném `ArithmeticException`. Chọn scale/precision và rounding theo đặc tả.

**Lỗi 5 — Dùng `BigDecimal.equals` để kiểm tra bằng nhau về số học.**  
`new BigDecimal("2.0")` và `new BigDecimal("2.00")` có `equals=false`, dù `compareTo=0`. Hãy chọn định nghĩa bằng nhau mong muốn trước khi dùng làm khóa.

**Lỗi 6 — Nhầm các Number đều immutable.**  
`AtomicInteger`, `AtomicLong`, `LongAdder` là đối tượng mutable; phép `intValue()` hoặc `longValue()` phản ánh trạng thái khi đọc theo hợp đồng của lớp.

**Lỗi 7 — Chuyển BigInteger/BigDecimal về int bằng `intValue()` không kiểm tra.**  
Có thể mất phần lẻ hoặc bit cao. Dùng các phương thức `...Exact()` khi yêu cầu bảo toàn giá trị, xử lý `ArithmeticException` đúng cách.

**Lỗi 8 — Cho rằng BigDecimal không có giới hạn.**  
`BigDecimal` không cho phép vô hạn tài nguyên, có thể bị ràng buộc bởi phạm vi scale và tài nguyên tính toán; phép chia thập phân vô hạn cần rounding. Lựa chọn này không thay thế thiết kế thuật toán và kiểm soát đầu vào.

**Lỗi 9 — So sánh các wrapper bằng `==` theo danh tính object.**  
Khi cả hai vế là reference, `==` kiểm tra **danh tính tham chiếu**, trừ trường hợp unboxing dẫn tới toán tử primitive. Dùng `equals` hoặc API so sánh phù hợp, nhưng nhớ `equals` cũng có thể không đồng nhất giữa các kiểu `Number` khác nhau.

## 9. Bài tập tự kiểm tra

**Câu 1.** `Number n = new BigInteger("999999999999999999999");` có hợp lệ không, và `n.intValue()` có đảm bảo trả toàn bộ số không?  
**Đáp án:** Hợp lệ vì `BigInteger` kế thừa `Number`. `intValue()` không bảo toàn số lớn; hãy ép lại về `BigInteger` một cách có kiểm tra hoặc giữ tham chiếu kiểu cụ thể, rồi dùng `intValueExact()` nếu cần đổi sang `int`.

**Câu 2.** Vì sao `new BigDecimal("0.1").add(new BigDecimal("0.2"))` cho giá trị 0.3 chính xác, còn `0.1 + 0.2` có thể khác 0.3?  
**Đáp án:** BigDecimal tạo từ chuỗi lưu thập phân đúng 0.1 và 0.2; phép cộng BigDecimal chính xác trong trường hợp này. `double` lưu xấp xỉ nhị phân của 0.1 và 0.2, nên kết quả `0.30000000000000004`.

**Câu 3.** `new BigDecimal("1").divide(new BigDecimal("3"))` cho kết quả gì?  
**Đáp án:** Ném `ArithmeticException` vì thương 1/3 không có biểu diễn thập phân hữu hạn. Cung cấp `scale`/`RoundingMode` hoặc `MathContext`.

**Câu 4.** Vì sao `HashSet<BigDecimal>` chứa cả 2.0 và 2.00, còn `TreeSet<BigDecimal>` thường chỉ có một?  
**Đáp án:** `HashSet` dùng `equals`/`hashCode` xét cả scale; `TreeSet` dùng `compareTo` theo giá trị số, coi hai giá trị này bằng nhau khi so sánh.

**Câu 5.** `Number` có phù hợp làm interface chung cho mọi phép cộng số chính xác không?  
**Đáp án:** Không. `Number` chỉ định các phép chuyển về primitive, không định nghĩa phép `add(Number)` hay loại số học. Cần giao diện/domain type và quy tắc chuyển đổi cụ thể nếu xây một thư viện phép tính.

**Câu 6.** `AtomicInteger` và `LongAdder` có phải các loại BigInteger hiệu quả hơn khi đa luồng không?  
**Đáp án:** Không. Chúng phục vụ cập nhật/cộng dồn các giá trị miền cố định, có trạng thái và hợp đồng đồng thời riêng. BigInteger là số nguyên bất biến độ lớn tùy ý.

**Câu 7.** Nên dùng `BigDecimal.intValue()` hay `intValueExact()` khi nhập tuổi nguyên từ giá trị thập phân?  
**Đáp án:** `intValueExact()` nếu yêu cầu tuổi phải là số nguyên và nằm trong miền `int`; phương thức này từ chối các giá trị có phần lẻ hoặc vượt miền thay vì âm thầm làm mất thông tin.

## 10. Ghi nhớ

- `Number` là **lớp trừu tượng chuyển đổi giá trị số** sang các primitive, không phải phép tính chung cho mọi loại số.
- `BigInteger` phục vụ **số nguyên lớn chính xác**; các phép toán là phương thức, kết quả là đối tượng mới; kiểm soát chuyển kiểu bằng `...Exact()`.
- `BigDecimal` phục vụ **thập phân có kiểm soát**; tạo từ chuỗi khi cần giữ đầu vào gốc, quản lý `scale`/`precision`/`RoundingMode`, phân biệt `equals` và `compareTo`.
- Wrapper primitive có miền cố định và bất biến; các lớp `AtomicInteger`/`AtomicLong`/`LongAdder` cũng là `Number` nhưng có trạng thái và mục đích đồng thời.
- Chọn kiểu số dựa trên **độ lớn, độ chính xác, tính bất biến, yêu cầu đồng thời, quy tắc làm tròn và hiệu năng**, không chỉ dựa trên việc một lớp có kế thừa `Number` hay không.