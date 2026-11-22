# Chuyển đổi qua Number.intValue(), longValue() và doubleValue() trong Java

## 1. Vì sao Java có các phương thức chuyển đổi này?

Trong Java, `java.lang.Number` là **lớp trừu tượng** chung cho các lớp biểu diễn giá trị số, chẳng hạn `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double`, `BigInteger` và `BigDecimal`. `Number` cho phép chương trình làm việc với nhiều loại số qua cùng một kiểu tham chiếu:

~~~java
Number quantity = Integer.valueOf(42);
int count = quantity.intValue();
long total = quantity.longValue();
double measured = quantity.doubleValue();
~~~

Đoạn trên là mã minh họa nằm trong một phương thức. Tại thời điểm chạy, biến `quantity` trỏ đến một đối tượng `Integer`, nên các lệnh gọi được thực hiện theo cài đặt của `Integer`. Nếu thay đối tượng bằng `Double` hoặc `BigDecimal`, **kiểu trả về vẫn cố định**, nhưng quy tắc chuyển đổi cụ thể có thể dẫn đến giá trị khác, mất độ chính xác, hoặc mất các bit cao.

Ba API cốt lõi:

| Phương thức của `Number` | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `intValue()` | `int` có dấu, 32 bit | Lấy giá trị ở dạng số nguyên 32 bit |
| `longValue()` | `long` có dấu, 64 bit | Lấy giá trị ở dạng số nguyên 64 bit |
| `doubleValue()` | `double`, IEEE 754 binary64 | Lấy giá trị ở dạng số thực dấu phẩy động 64 bit |

Những lời gọi này **không tạo ra đối tượng `Integer`, `Long` hay `Double`**: chúng trả về giá trị **primitive**. Nếu gán vào biến wrapper tương ứng, Java có thể tự boxing kết quả, ví dụ `Integer boxed = quantity.intValue();`.

## 2. Lớp Number: kiểu chung, đối tượng thực tế quyết định hành vi

`Number` khai báo bốn phương thức trừu tượng `intValue()`, `longValue()`, `floatValue()` và `doubleValue()`. Ngoài ra, `byteValue()` và `shortValue()` là phương thức cụ thể mặc định, chuyển qua `intValue()` rồi ép kiểu về `byte` hoặc `short`. Các lớp số chuẩn cài đặt hành vi chuyển đổi phù hợp với cách lưu dữ liệu của từng lớp.

~~~java
Number first = Long.valueOf(20L);
Number second = Double.valueOf(20.9);
Number third = new java.math.BigDecimal("20.9");

System.out.println(first.intValue());  // 20
System.out.println(second.intValue()); // 20
System.out.println(third.intValue());  // 20
~~~

Dù ba kết quả giống nhau, nguyên nhân không hoàn toàn giống: `Long` chuyển số nguyên sang `int`; `Double` chuyển số thực sang số nguyên theo quy tắc Java cho floating point; `BigDecimal` loại bỏ phần thập phân rồi lấy phần số nguyên có thể biểu diễn bởi 32 bit. Với những giá trị ngoài giới hạn, sự khác nhau rõ rệt hơn.

`Number` là **lớp**, không phải interface. Vì một tham chiếu `Number` có thể trỏ đến nhiều lớp con, không nên suy đoán mọi `Number` đều chính xác, đều hữu hạn hoặc đều nằm trong khoảng của `int`. Mã dùng `Number` cũng phải xử lý khả năng giá trị bằng `null`.

## 3. intValue(): chuyển sang int 32 bit

`intValue()` trả về `int` trong khoảng từ −2.147.483.648 đến 2.147.483.647.

### 3.1. Nguồn là Integer, Short hoặc Byte

Khi nguồn vốn là `Integer`, kết quả giữ nguyên. `Byte` và `Short` có miền nhỏ hơn `int` nên mọi giá trị đều biểu diễn chính xác khi mở rộng lên `int`.

~~~java
Number a = Byte.valueOf((byte) -7);
Number b = Short.valueOf((short) 32000);
Number c = Integer.valueOf(100000);

System.out.println(a.intValue()); // -7
System.out.println(b.intValue()); // 32000
System.out.println(c.intValue()); // 100000
~~~

### 3.2. Nguồn là Long: giữ 32 bit thấp

`Long.intValue()` tương đương chuyển thu hẹp `(int) longValue`: Java giữ **32 bit thấp** và diễn giải chúng là `int` có dấu. Đây không phải phép chuyển đổi có kiểm tra tràn; giá trị có thể thay đổi mạnh.

~~~java
Number n = Long.valueOf(3_000_000_000L);

System.out.println(n.intValue());  // -1294967296
System.out.println(n.longValue()); // 3000000000
~~~

Vì 3.000.000.000 lớn hơn `Integer.MAX_VALUE`, 32 bit thấp có bit dấu bằng 1; cùng mẫu bit đó được biểu diễn bởi `-1294967296` khi đọc dưới dạng `int`.

Nếu yêu cầu phải bảo toàn giá trị trong miền `int`, với nguồn `long` cụ thể hãy dùng `Math.toIntExact(long)`; API này ném `ArithmeticException` khi giá trị ngoài miền:

~~~java
long raw = 3_000_000_000L;
try {
    int safe = Math.toIntExact(raw);
    System.out.println(safe);
} catch (ArithmeticException ex) {
    System.out.println("Vượt giới hạn int");
}
~~~

### 3.3. Nguồn là Double hoặc Float: bỏ phần lẻ, có quy tắc cho giá trị đặc biệt

Với nguồn `Double`/`Float`, `intValue()` thực hiện quy tắc ép từ floating point về `int` của Java:

- Phần thập phân bị **cắt về phía 0**, không làm tròn gần nhất: `12.9 → 12`; `-12.9 → -12`.
- `NaN → 0`.
- Số dương quá lớn hoặc `+Infinity → Integer.MAX_VALUE`.
- Số âm quá nhỏ hoặc `-Infinity → Integer.MIN_VALUE`.

~~~java
System.out.println(Double.valueOf(12.9).intValue());                // 12
System.out.println(Double.valueOf(-12.9).intValue());               // -12
System.out.println(Double.valueOf(Double.NaN).intValue());         // 0
System.out.println(Double.valueOf(Double.POSITIVE_INFINITY).intValue()); // 2147483647
System.out.println(Double.valueOf(Double.NEGATIVE_INFINITY).intValue()); // -2147483648
~~~

Quy tắc này thường gọi là **saturation** ở trường hợp vượt giới hạn đối với chuyển đổi floating point sang integral. Đừng áp dụng nó cho `Long.intValue()` hoặc `BigInteger.intValue()`; hai loại đó có thể lấy các bit thấp và quay vòng, không chặn ở `Integer.MAX_VALUE`.

### 3.4. Nguồn là BigInteger hoặc BigDecimal

`BigInteger.intValue()` chỉ giữ 32 bit thấp của số nguyên lớn. `BigDecimal.intValue()` trước hết loại phần thập phân, sau đó kết quả cuối có thể chỉ giữ 32 bit thấp. Vì vậy **không thể coi `intValue()` là phép chuyển đổi kiểm tra miền hoặc kiểm tra phần lẻ**.

~~~java
Number huge = new java.math.BigInteger("4294967303"); // 2^32 + 7
Number decimal = new java.math.BigDecimal("-12.99");

System.out.println(huge.intValue());    // 7
System.out.println(decimal.intValue()); // -12
~~~

Nếu nguồn là `BigInteger` hoặc `BigDecimal` và yêu cầu giá trị nguyên chính xác, dùng `intValueExact()` của chính lớp đó. `BigDecimal.intValueExact()` còn báo lỗi nếu phần lẻ khác 0.

## 4. longValue(): chuyển sang long 64 bit

`longValue()` trả về `long` trong khoảng từ −9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807.

- Từ `Byte`, `Short`, `Integer` hoặc `Long`: giá trị số nguyên được bảo toàn vì tất cả nằm trong miền `long`.
- Từ `Double`/`Float`: bỏ phần lẻ về phía 0, `NaN → 0L`, vượt giới hạn dương/`+Infinity → Long.MAX_VALUE`, vượt giới hạn âm/`-Infinity → Long.MIN_VALUE`.
- Từ `BigInteger`: chỉ giữ **64 bit thấp**, kể cả khi số gốc lớn hơn `Long.MAX_VALUE`.
- Từ `BigDecimal`: bỏ phần lẻ rồi có thể mất các bit cao khi nằm ngoài miền `long`.

~~~java
Number fromInt = Integer.valueOf(-150);
Number fromDouble = Double.valueOf(98.75);
Number fromHuge = new java.math.BigInteger("18446744073709551617"); // 2^64 + 1

System.out.println(fromInt.longValue());    // -150
System.out.println(fromDouble.longValue()); // 98
System.out.println(fromHuge.longValue());   // 1
~~~

Ở ví dụ cuối, `18446744073709551617 = 2^64 + 1`. Khi chỉ còn 64 bit thấp, mẫu bit bằng 1. Dùng `BigInteger.longValueExact()` hoặc `BigDecimal.longValueExact()` để phát hiện chuyển đổi mất giá trị, nếu loại nguồn tương ứng hỗ trợ.

### Vì sao intValue và longValue không có cùng kết quả?

Cùng một `Number` có thể cho kết quả khác nhau theo số bit đích:

~~~java
Number n = Long.valueOf(4_294_967_296L); // 2^32

System.out.println(n.intValue());  // 0
System.out.println(n.longValue()); // 4294967296
~~~

`intValue()` giữ 32 bit thấp toàn số 0; `longValue()` giữ đủ số nguyên 64 bit.

## 5. doubleValue(): chuyển sang double 64 bit nhưng chỉ có 53 bit chính xác cho số nguyên

`double` sử dụng chuẩn IEEE 754 binary64: 1 bit dấu, 11 bit số mũ và 52 bit phần trị được lưu (thêm 1 bit dẫn đầu ngầm định cho số hữu hạn thông thường). Vì vậy độ chính xác hiệu dụng khoảng **53 bit nhị phân**, tương đương khoảng 15–17 chữ số thập phân có nghĩa.

Điều này có hai hệ quả:

1. Mọi số nguyên có độ lớn không quá **2^53 = 9.007.199.254.740.992** đều chuyển sang `double` **chính xác**. Một số lớn hơn vẫn có thể chính xác nếu biểu diễn được, nhưng **không còn bảo đảm cho mọi số nguyên liên tiếp**.
2. Số nguyên lớn như `long` và `BigInteger` hoặc số thập phân như `BigDecimal` có thể bị **làm tròn**. `doubleValue()` không báo lỗi vì mất độ chính xác.

~~~java
Number exact = Long.valueOf(9_007_199_254_740_992L); // 2^53
Number next = Long.valueOf(9_007_199_254_740_993L);  // 2^53 + 1

System.out.println(exact.doubleValue() == next.doubleValue()); // true
~~~

Hai số `long` liền nhau nhưng cùng được làm tròn về một giá trị `double`. Đây là lý do không dùng `doubleValue()` làm phép chuyển đổi không mất dữ liệu cho ID lớn, số đếm tuyệt đối lớn, hoặc khóa so sánh chính xác.

### BigDecimal và số thập phân không thể biểu diễn chính xác

~~~java
java.math.BigDecimal price = new java.math.BigDecimal("0.1");
double approximated = price.doubleValue();
System.out.println(approximated); // 0.1
~~~

Kết quả in là `0.1` vì `Double.toString` chọn biểu diễn thập phân ngắn có thể round-trip về cùng bit, **không có nghĩa 0,1 được lưu chính xác trong hệ nhị phân**. Nếu phải cộng tiền, tính thuế, kiểm tra sự bằng nhau chính xác theo đơn vị thập phân, giữ phép tính trong `BigDecimal` và quy định scale/rounding thích hợp.

Với `BigDecimal` hoặc `BigInteger` cực lớn, `doubleValue()` có thể tạo `Double.POSITIVE_INFINITY` hoặc `Double.NEGATIVE_INFINITY`; số khác 0 nhưng quá gần 0 cũng có thể bị làm tròn về `0.0` hoặc `-0.0` khi chuyển từ `BigDecimal` sang `double`. `double` không có miền hữu hạn hoặc độ chính xác để chứa mọi số thập phân.

## 6. Chương trình Java 17+ chạy đầy đủ

Tạo tệp `NumberConversionsDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;

public class NumberConversionsDemo {
    public static void main(String[] args) {
        Number whole = Integer.valueOf(42);
        Number large = Long.valueOf(3_000_000_000L);
        Number fraction = Double.valueOf(-12.75);
        Number decimal = new BigDecimal("123.99");
        Number huge = new BigInteger("4294967303");

        System.out.println("Integer -> " + whole.intValue() + ", " +
                whole.longValue() + ", " + whole.doubleValue());
        System.out.println("Long -> " + large.intValue() + ", " +
                large.longValue() + ", " + large.doubleValue());
        System.out.println("Double -> " + fraction.intValue() + ", " +
                fraction.longValue() + ", " + fraction.doubleValue());
        System.out.println("BigDecimal -> " + decimal.intValue() + ", " +
                decimal.longValue() + ", " + decimal.doubleValue());
        System.out.println("BigInteger -> " + huge.intValue() + ", " +
                huge.longValue() + ", " + huge.doubleValue());

        System.out.println("NaN as int -> " + Double.valueOf(Double.NaN).intValue());
        System.out.println("Infinity as long -> " +
                Double.valueOf(Double.POSITIVE_INFINITY).longValue());

        try {
            ((BigDecimal) decimal).intValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("Decimal exact -> ArithmeticException");
        }

        Number aboveExactDouble = new BigInteger("9007199254740993");
        BigDecimal roundedAsDecimal = BigDecimal.valueOf(aboveExactDouble.doubleValue());
        System.out.println("53-bit boundary -> " +
                aboveExactDouble.longValue() + " / " +
                roundedAsDecimal.toPlainString());
    }
}
~~~

Chạy:

~~~bash
javac NumberConversionsDemo.java
java NumberConversionsDemo
~~~

Kết quả:

~~~text
Integer -> 42, 42, 42.0
Long -> -1294967296, 3000000000, 3.0E9
Double -> -12, -12, -12.75
BigDecimal -> 123, 123, 123.99
BigInteger -> 7, 4294967303, 4.294967303E9
NaN as int -> 0
Infinity as long -> 9223372036854775807
Decimal exact -> ArithmeticException
53-bit boundary -> 9007199254740993 / 9007199254740992
~~~

Cần quan sát:

- Giá trị 3 tỷ chuyển sang `int` cho ra số âm vì bị giới hạn 32 bit.
- `-12.75` thành `-12` ở kiểu nguyên vì cắt về phía 0.
- `BigDecimal("123.99").intValue()` bỏ phần lẻ trong khi `intValueExact()` phát hiện mất dữ liệu.
- `2^32 + 7` chuyển sang `int` còn 7.
- `2^53 + 1` không thể giữ chính xác trong `double`; cách in cuối đối chiếu giá trị số nguyên gốc với giá trị đã được làm tròn khi đổi qua `double`.

## 7. Bảng tổng hợp quy tắc theo loại đối tượng

| Nguồn thực tế | `intValue()` | `longValue()` | `doubleValue()` |
| --- | --- | --- | --- |
| `Byte` / `Short` / `Integer` | Chính xác nếu nằm trong miền `int`; các lớp này đều thỏa | Chính xác | Chính xác cho tất cả giá trị `int` |
| `Long` | Giữ 32 bit thấp; có thể đổi giá trị | Chính xác | Có thể làm tròn với số nguyên lớn |
| `Float` / `Double` | Cắt phần lẻ; NaN → 0; tràn thì chặn biên `int` | Cắt phần lẻ; NaN → 0; tràn thì chặn biên `long` | `Double` giữ nguyên giá trị; `Float` mở rộng chính xác mẫu floating point đã lưu sang `double` |
| `BigInteger` | Giữ 32 bit thấp | Giữ 64 bit thấp | Có thể làm tròn hoặc thành ±Infinity |
| `BigDecimal` | Bỏ phần lẻ, có thể mất bit cao | Bỏ phần lẻ, có thể mất bit cao | Có thể làm tròn, underflow hoặc overflow |

**Ghi chú về `Float.doubleValue()`:** Phép mở rộng từ `float` sang `double` bảo toàn chính xác **giá trị nhị phân của `float`**, nhưng không phục hồi độ chính xác thập phân đã mất khi số ban đầu được lưu dưới `float`. Ví dụ:

~~~java
Number n = Float.valueOf(0.1f);
System.out.println(n.doubleValue()); // 0.10000000149011612
~~~

## 8. Cách chuyển đổi có kiểm tra mất dữ liệu

### Với nguồn long

`Math.toIntExact(long)` trả `int` nếu trong giới hạn, ngược lại ném `ArithmeticException`:

~~~java
long value = 50_000L;
int safe = Math.toIntExact(value);
System.out.println(safe); // 50000
~~~

### Với nguồn BigInteger hoặc BigDecimal

Dùng các phương thức `intValueExact()` và `longValueExact()` thay cho `intValue()`/`longValue()` khi không thể chấp nhận bị cắt giá trị:

~~~java
java.math.BigDecimal amount = new java.math.BigDecimal("19.00");
System.out.println(amount.intValueExact()); // 19

java.math.BigDecimal bad = new java.math.BigDecimal("19.01");
try {
    System.out.println(bad.longValueExact());
} catch (ArithmeticException ex) {
    System.out.println("Có phần thập phân");
}
~~~

`19.00` có phần biểu diễn thập phân nhưng **giá trị toán học là số nguyên** nên `intValueExact()` thành công. Ngược lại, `19.01` không thể chuyển thành `long` chính xác.

### Với Double và Float

`Number` không có `intValueExact()` chung. Nếu thực sự cần chuyển từ `double` sang số nguyên **đúng giá trị và trong giới hạn**, hãy kiểm tra `Double.isFinite`, phần lẻ, miền giá trị và những điều kiện chính xác theo yêu cầu trước khi chuyển. Cần đặc biệt cẩn thận tại biên `long`: `(double) Long.MAX_VALUE` được làm tròn lên thành 2^63 và không còn đại diện chính xác cho `Long.MAX_VALUE`.

Một cách tường minh cho các giá trị `double` hữu hạn là dùng `BigDecimal.valueOf(d).toBigIntegerExact()` để kiểm tra tính nguyên của **biểu diễn thập phân round-trip của `double`**, sau đó `longValueExact()`/`intValueExact()` để kiểm tra miền. Tuy nhiên, cách này **không phục hồi chữ số đã mất trước đó** khi dữ liệu được chuyển thành `double`. Nếu đầu vào gốc có tính chính xác thập phân (như tiền), nên parse/lưu nó bằng `BigDecimal` ngay từ đầu.

## 9. Khi nào chọn intValue, longValue hay doubleValue?

| Nhu cầu | Lựa chọn hợp lý | Điều cần xác minh |
| --- | --- | --- |
| Lấy số đếm nhỏ từ `Number` | `intValue()` | Có thể bị cắt phần lẻ/tràn? |
| Lấy timestamp/ID nguyên theo miền `long` | `longValue()` | Đối tượng nguồn có thực sự là số nguyên và trong miền `long`? |
| Dùng tính toán số thực hoặc phép đo chấp nhận sai số | `doubleValue()` | Độ chính xác floating point có đủ không? |
| Chuyển `BigDecimal` sang số nguyên không mất dữ liệu | `intValueExact()`/`longValueExact()` | Ném `ArithmeticException` nếu không biểu diễn chính xác |
| Chuyển `long` thành `int` mà không tràn | `Math.toIntExact()` | Xử lý `ArithmeticException` |
| Tính toán tiền tệ và cần chính xác số thập phân | Giữ `BigDecimal` | Scale, quy tắc làm tròn, phép so sánh |
| Tính toán số nguyên lớn hơn 64 bit | Giữ `BigInteger` | Không cắt xuống `int` hoặc `long` nếu chưa kiểm tra |

Đừng nhầm **chuyển giá trị** với **parse chuỗi**. `number.intValue()` chỉ áp dụng khi đã có một đối tượng `Number`. Đầu vào `"123.45"` là `String`, cần parse phù hợp trước (chẳng hạn `new BigDecimal("123.45")`); `Number` không khai báo phương thức static `parse` hay `valueOf` dùng chung.

## 10. Đa hình, null và lớp Number tùy biến

Một API có thể nhận `Number` để làm việc với các lớp con:

~~~java
static double twice(Number n) {
    if (n == null) {
        throw new IllegalArgumentException("Number must not be null");
    }
    return n.doubleValue() * 2;
}
~~~

Đoạn trên là phương thức minh họa; không phải chương trình độc lập. Việc chuyển sang `double` phù hợp nếu hợp đồng của API **cho phép sai số**. Nếu API yêu cầu chính xác với `BigDecimal` hoặc `BigInteger`, giao diện nhận `Number` quá rộng và việc tự gọi `doubleValue()` có thể làm mất dữ liệu. Khi đó nên chọn một kiểu tham số cụ thể hoặc mô tả rõ giới hạn và chính sách chuyển đổi.

Một lớp kế thừa `Number` tùy biến phải cài đặt bốn phương thức abstract; vì thế các quy tắc chung phía trên mô tả **các lớp Number chuẩn**, không bảo đảm mọi lớp con do bên thứ ba tự viết tuân theo cùng cách làm tròn, tràn hoặc chuyển đổi.

## 11. Lỗi thường gặp

1. **Cho rằng `intValue()` có kiểm tra tràn.** Sai với `Long`, `BigInteger` và `BigDecimal`. Khi cần chính xác, dùng API `Exact` tương ứng.
2. **Cho rằng bỏ phần lẻ là làm tròn.** `12.9` trở thành `12` và `-12.9` trở thành `-12`; hãy dùng quy tắc làm tròn rõ ràng trước khi chuyển nếu nghiệp vụ cần.
3. **Dùng `doubleValue()` cho số tiền hoặc khóa số nguyên rất lớn.** `double` có thể mất chữ số; ưu tiên `BigDecimal`/`BigInteger`.
4. **Giả định NaN hoặc Infinity sẽ gây lỗi khi chuyển sang nguyên.** Với `Double` và `Float`, phép chuyển theo quy tắc Java tạo 0 hoặc giá trị biên.
5. **Ép `Number` về lớp cụ thể vô điều kiện.** `(BigDecimal) number` sẽ ném `ClassCastException` nếu đối tượng thực tế là `Integer`, `Long` hoặc `Double`; hãy kiểm tra loại hoặc thiết kế API chặt hơn.
6. **Nhầm `Number` với cơ chế chuyển chuỗi.** Dùng parser/phương thức khởi tạo phù hợp để tạo đối tượng số trước.
7. **Quên null.** Gọi `n.intValue()` khi `n == null` sẽ ném `NullPointerException`.

## 12. Câu hỏi tự kiểm tra

**1.** Vì sao `Long.valueOf(4294967296L).intValue()` trả `0`?

Vì chuyển từ 64 bit xuống 32 bit chỉ giữ 32 bit thấp. `4294967296 = 2^32` có 32 bit thấp bằng 0.

**2.** `Double.valueOf(-3.9).longValue()` trả bao nhiêu?

`-3L`, vì chuyển floating point sang integer loại phần lẻ về phía 0.

**3.** Có thể thay `new BigDecimal("123.45")` bằng `Double.valueOf(123.45)` trong xử lý tiền rồi gọi `doubleValue()` không?

Có thể thực hiện về mặt cú pháp, nhưng số thập phân có thể được biểu diễn xấp xỉ trong binary64. Khi yêu cầu chính xác cho nghiệp vụ tiền tệ, giữ `BigDecimal` cùng quy tắc scale/rounding.

**4.** Tại sao `BigInteger.intValue()` và `Double.intValue()` có thể khác quy tắc với số lớn?

Vì `BigInteger` lấy 32 bit thấp của số nguyên tùy ý; `Double` tuân theo chuyển đổi dấu phẩy động sang nguyên của Java, bão hòa ở min/max khi vượt miền.

**5.** Muốn ép `BigDecimal("100.0")` thành `int` và chắc chắn không mất thông tin phải làm gì?

Gọi `new BigDecimal("100.0").intValueExact()`; kết quả là `100` vì giá trị toán học đúng là số nguyên, mặc dù biểu diễn có một chữ số thập phân.

## 13. Ghi nhớ

- `Number` cung cấp một giao diện phương thức chung cho nhiều loại đối tượng số; **kiểu đối tượng thực tế quyết định** cách chuyển đổi.
- `intValue()` và `longValue()` trả giá trị nguyên primitive; có thể cắt phần thập phân, mất bit cao hoặc bão hòa, **tùy loại nguồn**.
- `doubleValue()` cho phép làm việc với số thực nhưng có giới hạn **53 bit độ chính xác hiệu dụng** và có thể làm tròn, tràn thành Infinity hoặc mất giá trị rất nhỏ.
- Khi không được phép mất dữ liệu, kiểm tra miền và tính nguyên; dùng `Math.toIntExact`, `BigInteger.intValueExact/longValueExact` hoặc `BigDecimal.intValueExact/longValueExact` theo loại nguồn. Giữ `BigDecimal`/`BigInteger` trong các phép tính cần độ chính xác cao.
