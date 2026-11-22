# Phép toán exact và `BigDecimal` khi kiểu cơ bản không đáp ứng yêu cầu — Java 17+

Các kiểu số nguyên cơ bản (`int`, `long`) và số thực (`float`, `double`) rất hữu ích nhưng có giới hạn:

- **`int` và `long` có miền giá trị hữu hạn.** Phép cộng, trừ hoặc nhân nguyên thông thường có thể **tràn số** (*overflow*) và trả giá trị sai theo phép tính toán học mà không ném ngoại lệ.
- **`float` và `double` biểu diễn số thực bằng hệ nhị phân.** Một số giá trị thập phân như `0.1` không thể biểu diễn chính xác; chúng còn có thể làm tròn, underflow hoặc overflow.
- Khi hệ thống cần **phát hiện tràn số nguyên**, dùng các phương thức `Math.*Exact()`; khi cần **số nguyên rất lớn**, dùng `BigInteger`; khi cần **phép tính thập phân với độ chính xác được quản lý rõ**, dùng `BigDecimal`.

Đây là ba giải pháp cho **những nhu cầu khác nhau**. `Math.addExact` không mở rộng miền `int`; `BigDecimal` không tự động quyết định cách làm tròn cho tất cả bài toán.

## 1. Bảng lựa chọn nhanh

| Vấn đề | Giải pháp Java 17+ | Ý nghĩa |
| --- | --- | --- |
| `int` cộng/trừ/nhân có thể tràn | `Math.addExact`, `subtractExact`, `multiplyExact` | Ném `ArithmeticException` khi kết quả ngoài miền |
| `long` cộng/trừ/nhân có thể tràn | Overload nhận `long` của các phương thức trên | Vẫn dùng kiểu `long`, nhưng kiểm tra overflow |
| Tăng/giảm/đổi dấu ở biên | `incrementExact`, `decrementExact`, `negateExact` | Phát hiện kết quả vượt miền |
| Chuyển `long` sang `int` an toàn | `Math.toIntExact(long)` | Không âm thầm cắt các bit cao |
| Số nguyên lớn hơn `long` | `java.math.BigInteger` | Độ dài số nguyên không bị giới hạn bởi 64 bit, nhưng vẫn phụ thuộc bộ nhớ |
| Tiền, thuế, số lượng thập phân | `java.math.BigDecimal` | Phép tính thập phân theo `unscaled value × 10^(-scale)` |
| Phép chia thập phân không kết thúc | `BigDecimal.divide` cùng `scale`/`RoundingMode` hoặc `MathContext` | Quy định độ chính xác và làm tròn |
| Số thực xấp xỉ, đo đạc khoa học | `double`, kèm chính sách sai số | Thường thích hợp khi độ chính xác nhị phân là chấp nhận được |

**Nguyên tắc:** chọn kiểu số theo **miền giá trị và yêu cầu chính xác của nghiệp vụ**, không chỉ vì cú pháp tiện.

## 2. Phép toán nguyên `exact`: phát hiện overflow

Java không mặc định ném ngoại lệ khi tràn số nguyên:

~~~java
int wrapped = Integer.MAX_VALUE + 1;
System.out.println(wrapped); // -2147483648.
~~~

Giá trị toán học của `2_147_483_647 + 1` là `2_147_483_648`, ngoài miền `int`; phép tính nguyên thông thường cho kết quả bị tràn theo biểu diễn 32-bit.

Để **yêu cầu phép tính phải nằm trong miền**, dùng:

~~~java
int total = Math.addExact(100, 250); // 350.

// Math.addExact(Integer.MAX_VALUE, 1)
// -> nem ArithmeticException khi chay.
~~~

| Phương thức | Ví dụ | Kết quả nếu vượt miền |
| --- | --- | --- |
| `Math.addExact(a, b)` | `Math.addExact(100, 250)` → `350` | `ArithmeticException` |
| `Math.subtractExact(a, b)` | `Math.subtractExact(10, 15)` → `-5` | `ArithmeticException` |
| `Math.multiplyExact(a, b)` | `Math.multiplyExact(100, 200)` → `20000` | `ArithmeticException` |
| `Math.incrementExact(a)` | `Math.incrementExact(5)` → `6` | `ArithmeticException` |
| `Math.decrementExact(a)` | `Math.decrementExact(5)` → `4` | `ArithmeticException` |
| `Math.negateExact(a)` | `Math.negateExact(-5)` → `5` | `ArithmeticException` |
| `Math.toIntExact(x)` | `Math.toIntExact(42L)` → `42` | `ArithmeticException` nếu không vừa `int` |

Các phương thức này **không trả về số có độ rộng tùy ý**. `Math.multiplyExact(int, int)` vẫn trả `int`; muốn nhận một tích có thể lớn hơn `int` thì dùng toán hạng và kiểu `long` phù hợp, hoặc `BigInteger`.

**Cẩn thận thứ tự:** `Math.addExact(a * b, c)` không phát hiện overflow đã xảy ra **trong `a * b`**. Hãy kiểm tra chính phép nhân bằng `Math.multiplyExact(a, b)` trước khi đưa kết quả vào phép cộng.

`Math.*Exact` không biến phép tính số thực `double` thành thập phân chính xác; chúng dành cho số nguyên và chuyển đổi số nguyên theo các overload được hỗ trợ.

## 3. Chương trình Java 17+ độc lập và chạy được

Lưu tệp UTF-8 tên **`ExactAndBigDecimalDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

public class ExactAndBigDecimalDemo {
    public static void main(String[] args) {
        System.out.println("== exact integers ==");
        System.out.println("wrappedInt=" + (Integer.MAX_VALUE + 1));
        System.out.println("safeAdd=" + Math.addExact(100, 250));
        System.out.println("safeLongMultiply="
                + Math.multiplyExact(50_000L, 50_000L));

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException ex) {
            System.out.println("addOverflow=ArithmeticException");
        }

        try {
            Math.multiplyExact(50_000, 50_000);
        } catch (ArithmeticException ex) {
            System.out.println("multiplyOverflow=ArithmeticException");
        }

        try {
            Math.subtractExact(Integer.MIN_VALUE, 1);
        } catch (ArithmeticException ex) {
            System.out.println("subtractOverflow=ArithmeticException");
        }

        try {
            Math.toIntExact(3_000_000_000L);
        } catch (ArithmeticException ex) {
            System.out.println("narrowingOverflow=ArithmeticException");
        }

        System.out.println("== big integers ==");
        BigInteger left = new BigInteger("3000000000");
        BigInteger right = new BigInteger("4000000000");
        BigInteger product = left.multiply(right);
        System.out.println("bigProduct=" + product);
        System.out.println("bigProductPlusOne="
                + product.add(BigInteger.ONE));

        System.out.println("== exact decimals ==");
        BigDecimal a = new BigDecimal("0.1");
        BigDecimal b = new BigDecimal("0.2");
        System.out.println("decimalSum=" + a.add(b).toPlainString());
        System.out.println("binaryDoubleSum=" + (0.1 + 0.2));

        BigDecimal price = new BigDecimal("19.99");
        BigDecimal quantity = new BigDecimal("3");
        System.out.println("lineTotal="
                + price.multiply(quantity).toPlainString());

        BigDecimal amount = new BigDecimal("12.50");
        amount.add(new BigDecimal("0.50"));
        System.out.println("unchangedAmount=" + amount.toPlainString());
        amount = amount.add(new BigDecimal("0.50"));
        System.out.println("updatedAmount=" + amount.toPlainString());

        System.out.println("== division and rounding ==");
        System.out.println("oneEighth="
                + BigDecimal.ONE.divide(new BigDecimal("8")));

        try {
            BigDecimal.ONE.divide(new BigDecimal("3"));
        } catch (ArithmeticException ex) {
            System.out.println("nonTerminating=ArithmeticException");
        }

        System.out.println("oneThirdRounded="
                + BigDecimal.ONE.divide(
                        new BigDecimal("3"), 2, RoundingMode.HALF_UP));
        System.out.println("halfUp="
                + new BigDecimal("10.005").setScale(
                        2, RoundingMode.HALF_UP));
        System.out.println("halfEvenDown="
                + new BigDecimal("2.345").setScale(
                        2, RoundingMode.HALF_EVEN));
        System.out.println("halfEvenUp="
                + new BigDecimal("2.355").setScale(
                        2, RoundingMode.HALF_EVEN));

        System.out.println("== construction and equality ==");
        BigDecimal fromText = new BigDecimal("0.1");
        BigDecimal fromDouble = new BigDecimal(0.1);
        System.out.println("doubleConstructorEquals="
                + fromText.equals(fromDouble));
        System.out.println("valueOfEquals="
                + fromText.equals(BigDecimal.valueOf(0.1)));

        BigDecimal twoOneDecimal = new BigDecimal("2.0");
        BigDecimal twoTwoDecimals = new BigDecimal("2.00");
        System.out.println("scaleSensitiveEquals="
                + twoOneDecimal.equals(twoTwoDecimals));
        System.out.println("numericCompare="
                + twoOneDecimal.compareTo(twoTwoDecimals));
        System.out.println("stripZeros="
                + twoTwoDecimals.stripTrailingZeros().toPlainString());

        System.out.println("intExact="
                + new BigDecimal("123.00").intValueExact());
        try {
            new BigDecimal("123.5").intValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("fractionToInt=ArithmeticException");
        }
    }
}
~~~

Dùng **JDK 17 trở lên**, mở PowerShell hoặc Bash tại thư mục chứa tệp:

~~~bash
java -version
javac -version
javac -encoding UTF-8 ExactAndBigDecimalDemo.java
java ExactAndBigDecimalDemo
~~~

**Expected stdout chính xác** của riêng lệnh `java ExactAndBigDecimalDemo`:

~~~text
== exact integers ==
wrappedInt=-2147483648
safeAdd=350
safeLongMultiply=2500000000
addOverflow=ArithmeticException
multiplyOverflow=ArithmeticException
subtractOverflow=ArithmeticException
narrowingOverflow=ArithmeticException
== big integers ==
bigProduct=12000000000000000000
bigProductPlusOne=12000000000000000001
== exact decimals ==
decimalSum=0.3
binaryDoubleSum=0.30000000000000004
lineTotal=59.97
unchangedAmount=12.50
updatedAmount=13.00
== division and rounding ==
oneEighth=0.125
nonTerminating=ArithmeticException
oneThirdRounded=0.33
halfUp=10.01
halfEvenDown=2.34
halfEvenUp=2.36
== construction and equality ==
doubleConstructorEquals=false
valueOfEquals=true
scaleSensitiveEquals=false
numericCompare=0
stripZeros=2
intExact=123
fractionToInt=ArithmeticException
~~~

Đầu ra của `java -version` và `javac -version` tùy thuộc phiên bản JDK cài trên máy nên không tính trong khối stdout cố định.

## 4. `BigInteger` khi `long` không đủ lớn

`BigInteger` trong `java.math` lưu số nguyên có độ chính xác tùy ý (giới hạn thực tế bởi tài nguyên máy và các giới hạn triển khai). Nó phù hợp khi kết quả vượt `Long.MAX_VALUE`:

~~~java
BigInteger a = new BigInteger("3000000000");
BigInteger b = new BigInteger("4000000000");
BigInteger result = a.multiply(b);
// result = 12000000000000000000.
~~~

| Kiểu | Phép tính minh họa | Ghi chú |
| --- | --- | --- |
| `int` | `int c = a + b;` | Tràn số nếu giá trị ngoài miền |
| `long` | `long c = a + b;` | Miền rộng hơn `int` nhưng vẫn hữu hạn |
| `BigInteger` | `a.add(b)`, `a.multiply(b)` | Phương thức trả **đối tượng mới** chứa giá trị mới |

`BigInteger` là **immutable**: `a.add(b)` không tự sửa `a`; muốn cập nhật biến, viết `a = a.add(b)`. Nó không có phép cộng trực tiếp bằng toán tử `+` giữa hai đối tượng `BigInteger`.

Đừng nghĩ `BigInteger` thay thế `BigDecimal` cho mọi dữ liệu: `BigInteger` là **số nguyên**, không lưu phần thập phân.

## 5. `BigDecimal`: thập phân có scale, không phải kiểu số thực vô hạn

`BigDecimal` biểu diễn số bằng **unscaled integer** cùng **scale**:

~~~text
Gia tri = unscaledValue × 10^(-scale)

"19.99" -> unscaledValue = 1999, scale = 2
"2.00"  -> unscaledValue = 200,  scale = 2
~~~

Với đầu vào thập phân được biểu diễn bằng chuỗi, phép cộng, trừ và nhân của `BigDecimal` có thể tính **chính xác theo hệ thập phân** mà không mang sai số nhị phân kiểu `double`:

~~~java
BigDecimal x = new BigDecimal("0.1");
BigDecimal y = new BigDecimal("0.2");
BigDecimal sum = x.add(y); // 0.3.
~~~

### Tạo `BigDecimal` đúng cách

| Cách tạo | Khuyến nghị | Lý do |
| --- | --- | --- |
| `new BigDecimal("0.1")` | **Ưu tiên** nếu nguồn là dữ liệu thập phân | Diễn đạt chính xác 0.1 |
| `BigDecimal.valueOf(0.1)` | Thường phù hợp khi đã có `double` | Dùng biểu diễn thập phân của `Double.toString` |
| `new BigDecimal(0.1)` | **Tránh nếu chủ đích là 0.1 thập phân** | Chuyển chính xác giá trị nhị phân xấp xỉ sẵn có |
| `BigDecimal.valueOf(100L)` | Phù hợp với số nguyên | Tạo giá trị đúng từ `long` |

`new BigDecimal(0.1)` không làm tròn về `0.1` thập phân; nó biểu diễn chính xác giá trị `double` đang có. Vì thế demo in `doubleConstructorEquals=false` khi so với `new BigDecimal("0.1")`.

**Sai số đã phát sinh trước lúc tạo `BigDecimal` không được tự động sửa**. Nếu cần tính tiền, nên đọc số tiền thập phân trực tiếp từ chuỗi/kiểu dữ liệu chính xác, không tính qua `double` rồi mới chuyển.

## 6. Phép chia có thể cần quy tắc làm tròn

Không phải thương của hai số thập phân đều có biểu diễn thập phân **hữu hạn**:

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

// one.divide(three); // ArithmeticException: 1/3 vo han chu so thap phan.
BigDecimal rounded = one.divide(three, 2, RoundingMode.HALF_UP);
// 0.33.
~~~

| Cách chia | Hành vi |
| --- | --- |
| `one.divide(new BigDecimal("8"))` | Chính xác, trả `0.125` |
| `one.divide(new BigDecimal("3"))` | Ném `ArithmeticException` vì khai triển thập phân không kết thúc |
| `one.divide(new BigDecimal("3"), 2, RoundingMode.HALF_UP)` | Làm tròn hai chữ số sau dấu thập phân, trả `0.33` |
| `one.divide(divisor, new MathContext(10, RoundingMode.HALF_EVEN))` | Giới hạn **10 chữ số có nghĩa**, khác với scale = 10 |

**`scale` và `precision` không giống nhau**:

- `scale = 2` biểu thị **hai chữ số sau dấu thập phân** (đối với scale dương).
- `MathContext(10, ...)` quy định **10 chữ số có nghĩa** cho phép tính.

`RoundingMode.HALF_UP` làm tròn trường hợp đúng nửa theo hướng ra xa 0. `RoundingMode.HALF_EVEN` chọn chữ số cuối chẵn khi đúng trường hợp giữa hai kết quả, hữu ích trong một số quy tắc kế toán nhưng **không được tự ý coi là yêu cầu nghiệp vụ của mọi hệ thống**.

### Làm tròn có chủ đích

~~~java
BigDecimal price = new BigDecimal("10.005");
BigDecimal rounded = price.setScale(2, RoundingMode.HALF_UP);
// 10.01.
~~~

Nếu dùng `RoundingMode.UNNECESSARY`, phép toán sẽ ném `ArithmeticException` khi yêu cầu một phép làm tròn không thể thực hiện mà vẫn chính xác. Đây là cơ chế hữu ích khi muốn **chứng minh kết quả chính xác ở scale định trước**.

## 7. So sánh `BigDecimal`: `equals` khác `compareTo`

~~~java
BigDecimal first = new BigDecimal("2.0");
BigDecimal second = new BigDecimal("2.00");

System.out.println(first.equals(second)); // false.
System.out.println(first.compareTo(second) == 0); // true.
~~~

- `equals` xét **giá trị cùng scale**; `2.0` và `2.00` khác scale nên không `equals`.
- `compareTo` so **giá trị số học**; cả hai bằng nhau về mặt số học, nên trả 0.

Nếu mục đích là kiểm tra **giá trị tiền tương đương**, thường sử dụng `compareTo(...) == 0` sau khi đã xác định chính sách scale. Nếu cấu trúc dữ liệu dùng `HashSet` hoặc `HashMap` thì chúng dựa trên `equals` và `hashCode`, nên việc coi `2.0` và `2.00` là hai giá trị khác nhau có thể ảnh hưởng hành vi. Đừng trộn hai khái niệm bình đẳng mà không quy định rõ.

`stripTrailingZeros()` có thể tạo một `BigDecimal` với scale khác nhưng cùng giá trị số học. Khi cần biểu diễn văn bản ổn định, `toPlainString()` tránh notation khoa học mà `toString()` có thể chọn.

## 8. Chọn công cụ theo đúng giới hạn

Một số nguyên **quá lớn** và một số thập phân **cần chính xác** là hai vấn đề khác nhau. Kết hợp hợp lý:

~~~java
// Chi can phat hien overflow khi van muon int:
int count = Math.addExact(currentCount, addedCount);

// Neu so nguyen co the vuot long:
BigInteger idSequence = new BigInteger("999999999999999999999");

// Neu thanh tien can tinh theo thap phan:
BigDecimal unitPrice = new BigDecimal("19.99");
BigDecimal total = unitPrice.multiply(new BigDecimal("3"));
~~~

Đoạn này là ví dụ khái niệm, cần khai báo `currentCount`/`addedCount` ở phạm vi sử dụng thực tế; chương trình runnable ở mục 3 đã tự khai báo đầy đủ mọi biến.

**Đừng coi bất kỳ kiểu nào là “vô hạn” về tài nguyên.** `BigInteger`/`BigDecimal` có thể dùng nhiều bộ nhớ và CPU hơn primitive; chúng cũng không tự giải quyết lỗi đầu vào, đơn vị tiền tệ, chính sách làm tròn, overflow khi chuyển ngược về primitive hoặc yêu cầu hiệu năng.

Khi chuyển một `BigDecimal` có phần lẻ sang `int`, `intValue()` có thể mất thông tin. Nếu bắt buộc **không mất phần lẻ** và không vượt miền, dùng `intValueExact()` (hoặc `longValueExact()`). Demo cho thấy `"123.00"` chuyển được thành 123, còn `"123.5"` ném `ArithmeticException`.

## 9. Những hiểu nhầm thường gặp

| Hiểu nhầm | Điều đúng |
| --- | --- |
| “`Math.addExact` tự mở rộng `int` thành `long`.” | Không; nó **ném lỗi** nếu vượt miền |
| “`Math.addExact(a * b, c)` phát hiện mọi overflow.” | Không; `a * b` có thể tràn trước |
| “`long` đủ cho mọi số nguyên thực tế.” | Không; `BigInteger` dùng khi cần vượt miền `long` |
| “`BigDecimal` dùng toán tử `+` như primitive.” | Không; dùng `add`, `subtract`, `multiply`, `divide` |
| “`new BigDecimal(0.1)` bằng đúng 0.1 thập phân.” | Không; nó phản ánh chính xác giá trị `double` xấp xỉ |
| “`BigDecimal.divide` luôn trả kết quả.” | Phép chia như 1/3 cần quy tắc làm tròn |
| “`scale` và `precision` là một.” | Không; một bên là vị trí dấu thập phân, một bên là số chữ số có nghĩa |
| “`equals` chỉ nhìn giá trị số của `BigDecimal`.” | Không; `equals` còn xét scale |
| “Chuyển `BigDecimal` về `int` luôn an toàn.” | Có thể mất phần lẻ/vượt miền; dùng `intValueExact` khi cần |
| “`BigDecimal` tự đảm bảo mọi quy tắc tài chính.” | Không; phải quy định rounding, scale, đơn vị và điều kiện nhập liệu |

## 10. Bài tập tự kiểm tra

1. `Math.addExact(Integer.MAX_VALUE, 1)` trả giá trị gì?  
   *Đáp án:* Không trả số `int`; ném `ArithmeticException`.
2. Muốn tính chính xác tích của hai số nguyên có thể vượt `long`, chọn kiểu nào?  
   *Đáp án:* `BigInteger`.
3. Vì sao `new BigDecimal("0.1").add(new BigDecimal("0.2"))` cho 0.3 trong khi `0.1 + 0.2` bằng 0.30000000000000004?  
   *Đáp án:* Chuỗi vào `BigDecimal` xác định giá trị thập phân đúng; `double` dùng biểu diễn nhị phân xấp xỉ.
4. `BigDecimal.ONE.divide(new BigDecimal("3"))` làm gì?  
   *Đáp án:* Ném `ArithmeticException` nếu không cung cấp quy tắc rounding/precision phù hợp cho thương vô hạn.
5. `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` và `compareTo` lần lượt thế nào?  
   *Đáp án:* `false` và `0`.
6. `new BigDecimal("10.005").setScale(2, RoundingMode.HALF_UP)` bằng bao nhiêu?  
   *Đáp án:* `10.01`.
7. `new BigDecimal("123.5").intValueExact()` trả gì?  
   *Đáp án:* Ném `ArithmeticException` vì có phần lẻ.

## Checklist

- [ ] Biết primitive `int`/`long` có thể tràn âm thầm.
- [ ] Dùng `Math.*Exact` khi muốn phép toán nguyên **báo lỗi ngay khi tràn**.
- [ ] Dùng `BigInteger` cho số nguyên vượt miền primitive.
- [ ] Tạo `BigDecimal` từ chuỗi thập phân chính xác khi dữ liệu ban đầu là thập phân.
- [ ] Hiểu `BigDecimal` là immutable, dùng phương thức thay toán tử số học.
- [ ] Xác định `scale`, `precision` và `RoundingMode` trước các phép chia/làm tròn cần thiết.
- [ ] Phân biệt `equals` (giá trị và scale) với `compareTo` (giá trị số học).
- [ ] Dùng `intValueExact`/`longValueExact` khi chuyển ngược về primitive mà không được mất dữ liệu.

**Kết luận:** Khi `int`/`long` không đáp ứng yêu cầu, hãy quyết định rõ **phát hiện overflow** (`Math.*Exact`) hay **nâng miền số nguyên** (`BigInteger`). Khi `double` không phù hợp cho phép tính thập phân, dùng `BigDecimal` với **nguồn dữ liệu chính xác và chính sách làm tròn được thiết kế rõ ràng**.
