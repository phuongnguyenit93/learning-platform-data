# Bản đồ primitive, wrapper, Number, BigInteger và BigDecimal trong Java

> **Chủ đề:** Java core – numbers · **Nhóm:** Tổng quan  
> **Mục tiêu:** Nhận diện các họ kiểu số trong Java, hiểu quan hệ giữa chúng, chọn đúng kiểu lưu trữ/tính toán và tránh lỗi chuyển đổi, tràn số, sai số thập phân.

## 1. Bức tranh tổng thể

Java có hai cách biểu diễn số thường gặp: **primitive** lưu một giá trị theo kiểu nguyên thủy; **object** biểu diễn số qua lớp wrapper hoặc các lớp số trong thư viện. Không có một “kiểu Number” chung bao trùm cả primitive lẫn object.

```text
Giá trị số trong Java
├── Primitive (không kế thừa Object/Number)
│   ├── Số nguyên có dấu: byte, short, int, long
│   ├── Số thực dấu phẩy động: float, double
│   └── char: mã UTF-16 16 bit không dấu, dùng được trong vài phép số học
└── Reference / object
    ├── java.lang.Number (lớp trừu tượng)
    │   ├── Byte, Short, Integer, Long
    │   ├── Float, Double
    │   └── java.math.BigInteger, java.math.BigDecimal
    └── Character (wrapper của char; KHÔNG extends Number)

boolean / Boolean: kiểu logic, không phải kiểu số.
```

Cây trên là **bản đồ khái niệm**, không phải cây thừa kế từ primitive sang wrapper. Primitive `int` không phải lớp con của `Integer`; `Integer` mới là một đối tượng thuộc nhánh `Number`. `Character` và `Boolean` là wrapper nhưng không thuộc nhánh `Number`. Một số lớp chuyên dụng khác cũng kế thừa `Number`, nhưng không cần thiết để hiểu bộ kiểu số nền tảng này.

## 2. Primitive: các kiểu nền tảng và miền giá trị

| Kiểu | Kích thước | Ý nghĩa và phạm vi đáng nhớ | Ví dụ |
| --- | --- | --- | --- |
| `byte` | 8 bit | Số nguyên có dấu: −128 đến 127 | `byte b = 100;` |
| `short` | 16 bit | −32.768 đến 32.767 | `short s = 32000;` |
| `int` | 32 bit | −2³¹ đến 2³¹ − 1 | `int n = 1_000_000;` |
| `long` | 64 bit | −2⁶³ đến 2⁶³ − 1 | `long n = 3_000_000_000L;` |
| `float` | 32 bit | IEEE 754 nhị phân; thường khoảng 6–7 chữ số thập phân có nghĩa | `float f = 1.5f;` |
| `double` | 64 bit | IEEE 754 nhị phân; thường khoảng 15–16 chữ số thập phân có nghĩa | `double d = 1.5;` |
| `char` | 16 bit | Mã đơn vị UTF-16 không dấu: 0 đến 65.535; chủ yếu biểu diễn ký tự | `char c = 'A';` |

**Phân biệt phạm vi và độ chính xác:** `float`/`double` biểu diễn được những số có trị tuyệt đối rất lớn/nhỏ nhưng không biểu diễn chính xác mọi số thập phân. “15–16 chữ số” là ước lượng độ chính xác, không phải cam kết rằng một giá trị thập phân bất kỳ sẽ được giữ nguyên.

- Phép cộng, trừ, nhân trên `byte`, `short`, `char` thường được nâng lên `int` trước khi cho kết quả; ví dụ `byte x = 1, y = 2; int z = x + y;`. Muốn gán lại `byte` cần chuyển kiểu tường minh và tự chịu rủi ro mất dữ liệu.
- Một biểu thức `int * int` được tính bằng `int`, dù biến nhận kết quả là `long`. Phải mở rộng ít nhất một toán hạng **trước phép nhân**.
- Dùng chữ `L` (nên viết hoa) cho literal `long`; `f` hoặc `F` cho literal `float`. Dấu gạch dưới trong literal như `1_000_000` chỉ giúp đọc dễ hơn.
- `boolean` không tham gia tính toán số học; `char` có thể nâng lên `int`, nhưng không phải lựa chọn phù hợp để lưu đại lượng số thông thường.

**Tràn số nguyên:** khi phép tính primitive nguyên vượt miền kiểu, kết quả có thể quay vòng theo biểu diễn bit, không tự báo lỗi. `Math.addExact`, `Math.multiplyExact` và các hàm `*Exact` liên quan phát hiện tràn và ném `ArithmeticException`. Chúng không mở rộng miền giá trị; nếu cần vượt miền `long`, dùng `BigInteger`.

## 3. Wrapper: đối tượng tương ứng primitive

| Primitive | Wrapper | Kế thừa `Number`? |
| --- | --- | --- |
| `byte` | `Byte` | Có |
| `short` | `Short` | Có |
| `int` | `Integer` | Có |
| `long` | `Long` | Có |
| `float` | `Float` | Có |
| `double` | `Double` | Có |
| `char` | `Character` | Không |
| `boolean` | `Boolean` | Không |

Wrapper là các lớp **bất biến (immutable)**: không sửa được giá trị bên trong đối tượng sau khi tạo. Giá trị wrapper có thể là `null` vì đó là tham chiếu; primitive không thể là `null`.

Java hỗ trợ:

- **Boxing:** `int` → `Integer`; ví dụ `Integer a = 42;`.
- **Unboxing:** `Integer` → `int`; ví dụ `int b = a;`. Nếu `a == null`, unboxing ném `NullPointerException`.
- **Chuyển đổi tường minh:** `Integer.parseInt("42")` trả `int`, còn `Integer.valueOf("42")` trả `Integer`. `Long.parseLong`, `Double.parseDouble`... có vai trò tương tự.

Wrapper hữu ích khi API đòi đối tượng: `List<Integer>` hợp lệ, `List<int>` không hợp lệ; khi cần biểu diễn giá trị thiếu bằng `null`; hoặc khi dùng API nhận `Number`. Mảng `int[]` và `Integer[]` là hai loại khác nhau; không có tự động chuyển cả mảng.

**So sánh:** `==` giữa hai wrapper tham chiếu so sánh danh tính đối tượng; `equals` so sánh giá trị theo cùng kiểu wrapper. Một số wrapper có bộ nhớ đệm đối tượng nhỏ, nên kết quả `==` có thể gây hiểu lầm. Với hai `Integer`, dùng `a.equals(b)` nếu chắc chắn khác `null`, hoặc `Objects.equals(a, b)` nếu có thể `null`. Đừng dùng `==` để kết luận hai đối tượng wrapper có cùng giá trị.

**Chi phí:** primitive thường đơn giản hơn cho dữ liệu số dày đặc và tính toán liên tục. Boxing/unboxing trong vòng lặp hoặc collection có thể tạo thêm chi phí đối tượng và rủi ro `null`. Chỉ tối ưu dựa trên nhu cầu và đo đạc thực tế.

## 4. `Number` là gì, và không phải là gì?

`java.lang.Number` là **abstract class** chung của nhiều lớp biểu diễn số. Nó cung cấp hợp đồng lấy giá trị theo kiểu primitive:

```java
Number value = Integer.valueOf(42);
int i = value.intValue();
double d = value.doubleValue();
```

Các phương thức chính gồm `byteValue()`, `shortValue()`, `intValue()`, `longValue()`, `floatValue()` và `doubleValue()`. Hai phương thức đầu có thể có triển khai chung dựa trên `intValue()`; bốn phương thức còn lại là thành phần trừu tượng trọng tâm của hợp đồng `Number`.

**Giới hạn quan trọng:**

1. `Number` là kiểu tham chiếu, nên không thể khai báo `Number n = 5;` rồi coi nó là primitive. Phép boxing cho phép gán `5` thành `Integer` rồi lên `Number`, nhưng biến `n` vẫn là tham chiếu.
2. Không thể viết `n1 + n2` khi cả hai biến khai báo kiểu `Number`; `Number` không định nghĩa toán tử cộng đa hình. Chọn kiểu cụ thể hoặc thiết kế phép toán riêng sau khi biết chính xác yêu cầu.
3. `intValue()`, `longValue()`... là **phép chuyển đổi**, có thể cắt phần thập phân, tràn hoặc làm tròn. Chúng không bảo toàn độ chính xác tùy ý: ví dụ `BigInteger` cực lớn chuyển sang `long` sẽ mất các bit cao.
4. `Number` không khiến `BigDecimal`, `BigInteger` và `Double` có cùng quy tắc so sánh hoặc cùng khả năng biểu diễn. Không ép mọi số sang `double` chỉ để xử lý qua giao diện chung.

Ví dụ ngắn: một API thống kê chấp nhận `Number` có thể đọc `doubleValue()` nếu chấp nhận mất độ chính xác. API kế toán cần tính toán tiền nên công khai `BigDecimal` trong hợp đồng, tránh ép sang `double`.

## 5. `BigInteger`: số nguyên lớn tùy ý độ chính xác

`java.math.BigInteger` biểu diễn **số nguyên có dấu** vượt phạm vi cố định của `long`. Độ lớn chủ yếu chịu giới hạn bộ nhớ/chi phí xử lý, không bị giới hạn 64 bit như primitive. Nó là đối tượng bất biến và kế thừa `Number`.

```java
import java.math.BigInteger;

BigInteger population = new BigInteger("9223372036854775808");
BigInteger next = population.add(BigInteger.ONE);
BigInteger squared = next.multiply(next);
```

Các thao tác phổ biến: `add`, `subtract`, `multiply`, `divide` (chia lấy phần nguyên), `remainder`, `pow` (số mũ nguyên không âm), `gcd`, `compareTo`. `mod` dùng số chia dương và cho số dư không âm; phân biệt nó với `remainder` khi làm việc với số âm. Mỗi phép toán trả một kết quả mới; gọi `population.add(BigInteger.ONE)` mà bỏ kết quả **không thay đổi** `population`.

Tạo đối tượng bằng `new BigInteger("...")` cho số lớn dạng chuỗi, hoặc `BigInteger.valueOf(123L)` cho giá trị đã nằm trong `long`. Dùng `toString()` để xuất và `intValueExact()`/`longValueExact()` khi muốn ném `ArithmeticException` nếu giá trị không vừa kiểu đích. `intValue()`/`longValue()` thông thường có thể mất phần cao mà không báo lỗi.

**Khi chọn:** đếm số nguyên khổng lồ, tính toán tổ hợp/chỉnh hợp lớn, thuật toán số học nguyên. Nếu `long` đã đủ và chạy trong vòng lặp hiệu năng cao, chưa có lý do mặc định chuyển mọi thứ sang `BigInteger`.

## 6. `BigDecimal`: số thập phân chính xác theo hệ 10

`java.math.BigDecimal` biểu diễn số thập phân bằng **giá trị nguyên không chia tỉ lệ (unscaled value)** và **scale**: về mặt toán học, giá trị = `unscaledValue × 10^(-scale)`. Ví dụ `"12.340"` có unscaled value `12340`, scale `3`. Nó bất biến, kế thừa `Number` và hỗ trợ độ chính xác thập phân do người lập trình kiểm soát.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal price = new BigDecimal("19.90");
BigDecimal tax = new BigDecimal("1.99");
BigDecimal total = price.add(tax); // 21.89

BigDecimal oneThird = BigDecimal.ONE.divide(
    new BigDecimal("3"), 2, RoundingMode.HALF_UP
); // 0.33
```

**Khởi tạo đúng rất quan trọng:**

- `new BigDecimal("0.1")` biểu diễn đúng số thập phân `0.1`.
- `BigDecimal.valueOf(0.1)` dùng dạng chuỗi của `double` và cho `0.1` trong ví dụ này; có ích khi đầu vào đã là `double`, nhưng không thể khôi phục mọi ý định/độ chính xác đã mất trước đó.
- `new BigDecimal(0.1)` nhận **giá trị nhị phân thực tế** của literal `double`; kết quả không đúng bằng thập phân `0.1`. Tránh cách này nếu nguồn là số tiền hoặc số thập phân định trước.
- `BigDecimal.valueOf(123L)` hữu ích cho số nguyên nhỏ; dùng chuỗi cho literal thập phân cần chính xác.

**Phép tính và rounding:**

- `add`, `subtract`, `multiply` không bắt buộc làm tròn nếu không truyền `MathContext`, nhưng kết quả có scale/precision theo phép toán.
- Chia có thể tạo biểu diễn thập phân vô hạn: `BigDecimal.ONE.divide(new BigDecimal("3"))` ném `ArithmeticException` nếu không chỉ định quy tắc làm tròn. Chọn scale + `RoundingMode`, hoặc `MathContext` phù hợp với nghiệp vụ.
- `setScale(2, RoundingMode.HALF_UP)` điều chỉnh số chữ số sau dấu thập phân; `MathContext(precision, roundingMode)` giới hạn **tổng chữ số có nghĩa**, không phải số chữ số sau dấu thập phân.
- Không có một quy tắc làm tròn đúng cho mọi ứng dụng. `HALF_EVEN` hay `HALF_UP` phụ thuộc chuẩn và quy định nghiệp vụ; với tiền tệ, số chữ số lẻ còn tùy loại tiền/đơn vị và quy trình.

**So sánh và lưu khóa:**

```java
BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");

System.out.println(x.equals(y));           // false
System.out.println(x.compareTo(y) == 0);    // true
```

`equals` xét **cả giá trị và scale**; `compareTo` so sánh giá trị số học. Vì vậy `BigDecimal` dùng làm key của `HashMap` hoặc phần tử `HashSet` phải có quy tắc chuẩn hóa scale rõ ràng nếu nghiệp vụ coi `1.0` và `1.00` tương đương. `stripTrailingZeros()` có thể đưa scale về 0 hoặc âm, nên đừng mặc định dạng hiển thị sẽ giữ nguyên. `toPlainString()` hữu ích khi muốn chuỗi thập phân không dùng ký pháp lũy thừa.

## 7. Lựa chọn kiểu theo yêu cầu

| Tình huống | Lựa chọn thường phù hợp | Lý do chính |
| --- | --- | --- |
| Biến đếm/chỉ số/mã số nguyên vừa miền 32 bit | `int` | Tự nhiên trong Java, nhẹ, dễ dùng |
| Số nguyên cần phạm vi 64 bit | `long` | Miền lớn hơn `int` nhưng vẫn hữu hạn |
| Dữ liệu thô/định dạng nhị phân yêu cầu 8 hoặc 16 bit | `byte`, `short` | Khớp giao thức/định dạng; không vì thế mà mọi phép toán được thực hiện ở 8/16 bit |
| Đo lường khoa học, đồ họa, thống kê chấp nhận xấp xỉ | `double` (hoặc `float` khi có lý do) | Tốc độ và miền số thực dấu phẩy động |
| Số nguyên vượt `long` và cần phép toán chính xác | `BigInteger` | Không tràn tại biên 64 bit |
| Tiền, đơn giá, tỷ lệ thập phân có quy tắc làm tròn rõ | `BigDecimal` | Biểu diễn thập phân chính xác và kiểm soát rounding |
| API generic cần chấp nhận một họ đối tượng số | `Number` | Hợp đồng chuyển đổi chung; không hàm ý phép tính chính xác chung |
| Collection/generic hoặc dữ liệu có thể thiếu | Wrapper tương ứng | Đối tượng, có thể `null`; chú ý unboxing |

Không dùng `BigDecimal` chỉ vì `double` “không đủ lớn”: hai kiểu giải quyết hai vấn đề khác nhau là **số thực xấp xỉ nhị phân** và **số thập phân có độ chính xác/rounding kiểm soát**. Cũng không dùng `BigInteger` để thay `BigDecimal` nếu phép tính có phần thập phân.

## 8. Ví dụ Java 17+ chạy độc lập: kết nối cả bản đồ

Tạo tệp `NumberMapDemo.java`:

```java
import java.math.BigDecimal;
import java.math.BigInteger;

public class NumberMapDemo {
    public static void main(String[] args) {
        int primitive = 42;
        Integer wrapper = Integer.valueOf(primitive);
        Number general = wrapper;

        BigInteger huge = new BigInteger("9223372036854775808");
        BigInteger next = huge.add(BigInteger.ONE);

        BigDecimal decimal = new BigDecimal("0.10")
                .add(new BigDecimal("0.20"));

        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");

        System.out.println("primitive=" + primitive);
        System.out.println("wrapper=" + wrapper);
        System.out.println("Number->int=" + general.intValue());
        System.out.println("BigInteger=" + next);
        System.out.println("BigDecimal=" + decimal.toPlainString());
        System.out.println("equals=" + a.equals(b));
        System.out.println("compareTo=" + (a.compareTo(b) == 0));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac NumberMapDemo.java
java NumberMapDemo
```

Kết quả chuẩn:

```text
primitive=42
wrapper=42
Number->int=42
BigInteger=9223372036854775809
BigDecimal=0.30
equals=false
compareTo=true
```

Ý nghĩa: `int` được boxing thành `Integer` rồi tham chiếu bằng `Number`; `BigInteger` vượt miền `long`; phép cộng `BigDecimal` giữ scale trong kết quả `0.30`; hai số thập phân bằng nhau về số học nhưng khác biểu diễn scale có kết quả `equals` khác nhau.

## 9. Thử nghiệm lỗi thường gặp: tràn, sai số và unboxing

Tạo tệp `NumericPitfalls.java`:

```java
import java.math.BigDecimal;

public class NumericPitfalls {
    public static void main(String[] args) {
        int amount = 1_500_000_000;
        long overflowed = amount * 2;
        long safe = (long) amount * 2;

        double binary = 0.1 + 0.2;
        BigDecimal exact = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));

        System.out.println("overflowed=" + overflowed);
        System.out.println("safe=" + safe);
        System.out.println("double=" + binary);
        System.out.println("decimal=" + exact.toPlainString());

        Integer maybeMissing = null;
        try {
            int value = maybeMissing; // unboxing null
            System.out.println(value);
        } catch (NullPointerException e) {
            System.out.println("unboxing=null -> NullPointerException");
        }
    }
}
```

```bash
javac NumericPitfalls.java
java NumericPitfalls
```

Kết quả:

```text
overflowed=-1294967296
safe=3000000000
double=0.30000000000000004
decimal=0.3
unboxing=null -> NullPointerException
```

Giải thích: `amount * 2` được tính ở 32 bit trước khi gán cho `long`; ép `(long) amount` trước phép nhân giúp phép nhân diễn ra ở 64 bit. `0.1` và `0.2` ở dạng `double` không biểu diễn chính xác tuyệt đối theo hệ nhị phân; hai chuỗi `"0.1"` và `"0.2"` ở `BigDecimal` giữ được giá trị thập phân mong muốn. Cuối cùng, tham chiếu wrapper có thể `null` và lỗi xuất hiện khi unboxing.

## 10. Những nhầm lẫn cần tránh

1. **“Mọi số đều là `Number`.”** Sai: primitive không kế thừa lớp nào, và `char`/`Character` không thuộc nhánh `Number`.
2. **“Wrapper giống hệt primitive.”** Sai: wrapper là object, có `null`, phương thức, danh tính đối tượng và chi phí liên quan.
3. **“Gán vào `long` tránh mọi tràn `int`.”** Sai nếu biểu thức trước phép gán vẫn tính bằng `int`.
4. **“`double` chính xác cho mọi số tiền vì có nhiều chữ số.”** Sai: biểu diễn nhị phân của nhiều phân số thập phân là xấp xỉ.
5. **“`new BigDecimal(0.1)` tương đương `new BigDecimal("0.1")`.”** Sai: đối số `double` đã mang giá trị nhị phân xấp xỉ.
6. **“`BigDecimal.divide` luôn chạy được.”** Sai: phép chia không có biểu diễn thập phân hữu hạn có thể cần chỉ định rounding.
7. **“Mọi `equals` số học đều nhất quán giữa các lớp.”** Sai: wrapper khác kiểu và `BigDecimal` khác scale có quy tắc `equals` riêng.
8. **“Chuyển qua `Number.doubleValue()` không mất dữ liệu.”** Sai với số nguyên rất lớn và nhiều số thập phân; chuyển sang primitive có thể làm tròn/tràn.
9. **“Gọi `add` sẽ sửa `BigInteger`/`BigDecimal`.”** Sai: cả hai bất biến; cần lưu kết quả trả về.
10. **“`float`/`double` chỉ có các số hữu hạn.”** Sai: còn có `NaN`, dương/vô cực âm và số 0 có dấu. Các trường hợp này cần được xử lý rõ khi kiểm tra dữ liệu và so sánh.

## 11. Checklist khi thiết kế một giá trị số

- Giá trị có phần thập phân không? Nếu có, ứng dụng chấp nhận **xấp xỉ nhị phân** hay cần **thập phân chính xác có rounding**?
- Giá trị nguyên lớn nhất/nhỏ nhất có vừa `int` hoặc `long` không? Cần phát hiện tràn hay miền số tùy ý?
- API cần primitive hay object? Có chấp nhận `null` không, và đâu là điểm unboxing?
- Có phép chuyển `Number` → primitive nào mất dữ liệu không?
- Với `BigDecimal`: nguồn vào là chuỗi hay `double`; quy tắc scale, rounding, `equals`/`compareTo` và định dạng hiển thị được quyết định ở đâu?
- Với dữ liệu đưa vào collection/map, quy tắc bằng nhau và chuẩn hóa đã nhất quán chưa?

**Ghi nhớ bản đồ:** `int/long/double` giải quyết phép toán primitive theo miền hữu hạn; wrapper cung cấp đối tượng cho những giá trị đó; `Number` là điểm chung để **đọc/chuyển đổi** số trong các lớp; `BigInteger` giải quyết **số nguyên rất lớn**; `BigDecimal` giải quyết **thập phân chính xác với quy tắc scale/rounding**.
