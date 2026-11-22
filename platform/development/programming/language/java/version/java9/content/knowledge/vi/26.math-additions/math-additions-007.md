# Kiểm tra số âm, biên kiểu, NaN và vô cực trong Java

## Mục tiêu

Khi xử lý dữ liệu số, chỉ kiểm tra một giá trị có nhỏ hơn 0 hay không là chưa đủ. Chương trình còn phải xác định giá trị có nằm trong phạm vi kiểu dữ liệu, phép toán có bị tràn, dữ liệu dấu phẩy động có phải NaN hoặc vô cực, và phép chuyển đổi có làm mất thông tin hay không.

Java cung cấp các hằng số giới hạn trong lớp wrapper, các phương thức kiểm tra trong **Float** và **Double**, các phép toán phát hiện tràn trong **Math**, cùng **BigInteger** và **BigDecimal** cho miền giá trị hoặc độ chính xác lớn hơn.

Bài này tập trung vào các API còn dùng trong Java hiện đại, với ví dụ chạy trên Java 17+.

## 1. Kiểm tra một giá trị có âm hay không

Với kiểu số nguyên, phép so sánh thông thường là đủ:

```java
int balance = -25;

if (balance < 0) {
    System.out.println("Balance is negative");
}
```

Với kiểu dấu phẩy động, phép so sánh cũng kiểm tra được số âm hữu hạn và âm vô cực:

```java
double temperature = -3.5;

if (temperature < 0.0) {
    System.out.println("Temperature is below zero");
}
```

Tuy nhiên, trước khi dùng kết quả so sánh làm kiểm tra dữ liệu đầu vào, cần hiểu ba trường hợp đặc biệt:

- **NaN** không nhỏ hơn 0, không lớn hơn 0 và cũng không bằng 0. Vì vậy `value < 0.0` trả về false nếu value là NaN.
- **Negative infinity** nhỏ hơn 0, nên phép so sánh trả về true.
- **Negative zero (`-0.0`)** được xem là bằng 0 trong phép so sánh số học thông thường: `-0.0 < 0.0` là false.

Nếu yêu cầu là "số âm hữu hạn", hãy kiểm tra hữu hạn trước:

```java
static boolean isNegativeFinite(double value) {
    return Double.isFinite(value) && value < 0.0;
}
```

Nếu yêu cầu là "giá trị có dấu bit âm", kể cả `-0.0` hoặc âm vô cực, đó là một quy tắc khác. Với double, có thể kiểm tra bit dấu:

```java
boolean hasNegativeSign = Double.doubleToRawLongBits(value) < 0;
```

Không nên dùng một định nghĩa "âm" duy nhất cho mọi nghiệp vụ. Ví dụ, kiểm tra số dư không âm thường muốn loại cả NaN và vô cực; kiểm tra dấu bit trong xử lý số học dấu phẩy động có thể cần phân biệt `-0.0`.

### Với BigInteger và BigDecimal

Hai lớp số lớn có phương thức `signum()`:

- Trả về `-1` nếu giá trị âm.
- Trả về `0` nếu bằng 0.
- Trả về `1` nếu dương.

```java
BigInteger count = new BigInteger("-100000000000000000000");
BigDecimal amount = new BigDecimal("-12.50");

boolean negativeCount = count.signum() < 0;
boolean negativeAmount = amount.signum() < 0;
```

`signum()` hữu ích khi miền giá trị vượt quá `long` hoặc khi cần giữ độ chính xác thập phân.

## 2. Giới hạn của các kiểu số nguyên

Các kiểu số nguyên nguyên thủy có miền giá trị cố định:

| Kiểu | Giá trị nhỏ nhất | Giá trị lớn nhất |
|---|---:|---:|
| `byte` | `Byte.MIN_VALUE` (-128) | `Byte.MAX_VALUE` (127) |
| `short` | `Short.MIN_VALUE` (-32,768) | `Short.MAX_VALUE` (32,767) |
| `int` | `Integer.MIN_VALUE` (-2³¹) | `Integer.MAX_VALUE` (2³¹ - 1) |
| `long` | `Long.MIN_VALUE` (-2⁶³) | `Long.MAX_VALUE` (2⁶³ - 1) |

Có thể dùng các hằng số này để kiểm tra một giá trị trước khi chuyển kiểu:

```java
long input = 2_000_000_000L;

if (input >= Integer.MIN_VALUE && input <= Integer.MAX_VALUE) {
    int value = (int) input;
    System.out.println(value);
} else {
    System.out.println("Outside int range");
}
```

Nếu kiểm tra một giá trị `long` trước khi ép sang `int`, hãy so sánh trực tiếp với hai biên. Không nên trừ hoặc cộng để kiểm tra biên vì chính phép tính dùng trong điều kiện có thể bị tràn.

### Ép kiểu số nguyên không tự báo tràn

Ép một `long` lớn hơn miền `int` sang `int` không ném exception. Giá trị bị thu hẹp theo quy tắc chuyển đổi nhị phân của Java và có thể trở thành một số âm hoặc một giá trị khác:

```java
long original = (long) Integer.MAX_VALUE + 1;
int narrowed = (int) original;

System.out.println(narrowed);
```

Với phép chuyển đổi này, kết quả là `-2147483648`. Nếu cần chuyển đổi có kiểm tra, dùng `Math.toIntExact()` thay vì ép kiểu trực tiếp.

## 3. Phát hiện tràn số khi thực hiện phép toán

Phép toán số nguyên thông thường trong Java có thể tràn mà không ném exception. Ví dụ, cộng vượt `Integer.MAX_VALUE` sẽ quay vòng theo biểu diễn số nguyên có độ rộng cố định.

Các phương thức `Math.*Exact` cung cấp lựa chọn phát hiện tràn:

- `Math.addExact(a, b)`
- `Math.subtractExact(a, b)`
- `Math.multiplyExact(a, b)`
- `Math.incrementExact(value)`
- `Math.decrementExact(value)`
- `Math.negateExact(value)`
- `Math.toIntExact(longValue)`

Các overload phù hợp tồn tại cho `int` và/hoặc `long` tùy phép toán. Nếu kết quả không biểu diễn được trong kiểu trả về, phương thức ném `ArithmeticException`.

Ví dụ:

```java
int total = Math.addExact(100, 200);

try {
    int overflow = Math.addExact(Integer.MAX_VALUE, 1);
} catch (ArithmeticException exception) {
    System.out.println("Addition overflow detected");
}
```

Để chuyển `long` sang `int` có kiểm tra:

```java
long id = 2_000_000_000L;
int intId = Math.toIntExact(id);
```

Nếu `id` vượt ngoài miền `int`, `Math.toIntExact()` ném `ArithmeticException`.

### Những trường hợp dễ bỏ sót

`Math.abs()` không thể biểu diễn trị tuyệt đối của giá trị nhỏ nhất đối với kiểu số nguyên có dấu. Vì vậy:

```java
System.out.println(Math.abs(Integer.MIN_VALUE));
System.out.println(Math.abs(Long.MIN_VALUE));
```

Hai kết quả vẫn là số âm tương ứng, do giá trị dương cần thiết vượt quá miền kiểu. Nếu cần phát hiện trường hợp này, có thể kiểm tra giá trị bằng `MIN_VALUE` trước khi gọi `Math.abs()`, hoặc dùng `BigInteger.abs()` cho miền giá trị lớn hơn.

Phép chia số nguyên cho 0 ném `ArithmeticException`. Phép chia số dấu phẩy động cho 0 lại có quy tắc khác: có thể cho ra vô cực hoặc NaN. Cần phân biệt hai nhóm kiểu này khi kiểm tra lỗi.

## 4. Dùng BigInteger khi miền số nguyên không đủ

`BigInteger` biểu diễn số nguyên có độ lớn tùy ý, giới hạn thực tế phụ thuộc bộ nhớ và tài nguyên. Nó không bị giới hạn ở `Long.MIN_VALUE` và `Long.MAX_VALUE`.

Ví dụ:

```java
BigInteger maxLong = BigInteger.valueOf(Long.MAX_VALUE);
BigInteger beyondLong = maxLong.add(BigInteger.ONE);

System.out.println(beyondLong);
System.out.println(beyondLong.compareTo(maxLong) > 0);
```

Kết quả:

```text
9223372036854775808
true
```

Các phép toán như `add`, `subtract`, `multiply`, `divide`, `remainder`, `abs` và `compareTo` được cung cấp dưới dạng phương thức. `BigInteger` là immutable: mỗi phép toán trả về một đối tượng kết quả mới.

Khi cần chuyển về kiểu nguyên thủy, dùng phương thức exact:

- `intValueExact()`
- `longValueExact()`
- `shortValueExact()`
- `byteValueExact()`

Các phương thức này ném `ArithmeticException` nếu giá trị không nằm trong miền kiểu đích. Trong khi đó, `intValue()` hoặc `longValue()` có thể làm mất phần cao của giá trị khi nó vượt miền.

## 5. Dùng BigDecimal để kiểm tra giá trị thập phân

`float` và `double` lưu số dấu phẩy động theo chuẩn nhị phân. Nhiều số thập phân hữu hạn, chẳng hạn 0.1, không có biểu diễn nhị phân chính xác. Khi cần biểu diễn thập phân chính xác như tiền tệ hoặc số đo theo quy tắc thập phân, dùng `BigDecimal` với đầu vào phù hợp.

Nên tạo `BigDecimal` từ chuỗi:

```java
BigDecimal price = new BigDecimal("19.95");
BigDecimal taxRate = new BigDecimal("0.08");

BigDecimal total = price.multiply(BigDecimal.ONE.add(taxRate));
System.out.println(total);
```

Tránh `new BigDecimal(0.1)` nếu mong muốn đúng giá trị thập phân 0.1, vì constructor đó chuyển chính xác giá trị double nhị phân đang có. Có thể dùng `BigDecimal.valueOf(0.1)` khi đầu vào hiện có là double và muốn dùng dạng chuỗi chuẩn của nó, nhưng nếu nguồn dữ liệu là văn bản thập phân thì tạo trực tiếp từ chuỗi vẫn rõ ràng hơn.

### So sánh BigDecimal

`compareTo()` so sánh giá trị số, không yêu cầu scale giống nhau. `equals()` kiểm tra cả giá trị và scale:

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.compareTo(b) == 0);
System.out.println(a.equals(b));
```

Stdout:

```text
true
false
```

Khi kiểm tra biên thập phân, thường dùng `compareTo()`:

```java
BigDecimal amount = new BigDecimal("125.50");
BigDecimal lower = new BigDecimal("0.00");
BigDecimal upper = new BigDecimal("1000.00");

boolean inRange =
        amount.compareTo(lower) >= 0 &&
        amount.compareTo(upper) <= 0;
```

### Chuyển BigDecimal về kiểu nguyên thủy có kiểm tra

`intValueExact()` và `longValueExact()` kiểm tra cả phần thập phân lẫn giới hạn kiểu:

```java
int whole = new BigDecimal("125.00").intValueExact();

try {
    int invalid = new BigDecimal("125.75").intValueExact();
} catch (ArithmeticException exception) {
    System.out.println("Fractional value rejected");
}

try {
    int tooLarge = new BigDecimal("2147483648").intValueExact();
} catch (ArithmeticException exception) {
    System.out.println("Out-of-range value rejected");
}
```

Giá trị `125.00` chuyển được vì phần thập phân bằng 0; `125.75` không thể chuyển thành int mà giữ nguyên giá trị, còn `2147483648` vượt miền int.

## 6. NaN và vô cực trong float, double

Các kiểu `float` và `double` có những giá trị đặc biệt:

- `Float.NaN`, `Double.NaN`: Not-a-Number, thường xuất hiện từ phép toán không có kết quả số thực hợp lệ như `0.0 / 0.0`.
- `Float.POSITIVE_INFINITY`, `Double.POSITIVE_INFINITY`: dương vô cực.
- `Float.NEGATIVE_INFINITY`, `Double.NEGATIVE_INFINITY`: âm vô cực.

Java cung cấp các phương thức kiểm tra:

| Phương thức | Ý nghĩa |
|---|---|
| `Double.isNaN(value)` / `Float.isNaN(value)` | Giá trị có phải NaN không |
| `Double.isInfinite(value)` / `Float.isInfinite(value)` | Giá trị có phải vô cực không |
| `Double.isFinite(value)` / `Float.isFinite(value)` | Giá trị có phải số hữu hạn không |

Ví dụ:

```java
double invalid = Double.NaN;
double positiveInfinity = Double.POSITIVE_INFINITY;
double negativeInfinity = Double.NEGATIVE_INFINITY;
double normal = 12.5;

System.out.println(Double.isNaN(invalid));
System.out.println(Double.isInfinite(positiveInfinity));
System.out.println(Double.isFinite(normal));
```

Stdout:

```text
true
true
true
```

Khi nhận một giá trị double từ phép tính hoặc đầu vào, nếu nghiệp vụ chỉ cho phép số hữu hạn, hãy kiểm tra `Double.isFinite(value)` trước khi kiểm tra miền hoặc lưu dữ liệu. Với float, dùng `Float.isFinite(value)`.

### Quy tắc so sánh NaN

NaN có hành vi khác các giá trị số thông thường:

- `NaN == NaN` là false.
- `NaN != NaN` là true.
- `NaN < value`, `NaN > value`, `NaN <= value` và `NaN >= value` đều là false.

Vì vậy, không thể kiểm tra NaN bằng `value == Double.NaN`. Hãy dùng `Double.isNaN(value)`.

NaN có thể lan truyền qua phép tính. Ví dụ, cộng NaN với một số hữu hạn vẫn cho NaN. Nếu không kiểm tra, một phép tính tổng hợp hoặc so sánh có thể cho kết quả không như mong đợi.

### Vô cực và chia cho 0

Với dấu phẩy động:

- Một số hữu hạn dương chia cho `0.0` có thể tạo dương vô cực.
- Một số hữu hạn âm chia cho `0.0` có thể tạo âm vô cực.
- `0.0 / 0.0` tạo NaN.

Khác với số nguyên, những phép chia dấu phẩy động này không ném `ArithmeticException`. Hãy dùng `isFinite`, `isInfinite` và `isNaN` để kiểm tra kết quả theo yêu cầu.

## 7. Phân biệt -0.0 và +0.0

IEEE 754 có hai biểu diễn zero với bit dấu khác nhau:

- `+0.0`
- `-0.0`

Trong phép so sánh thông thường, `-0.0 == +0.0` là true và cả hai đều không nhỏ hơn 0. Tuy nhiên, một số phép toán phân biệt chúng, ví dụ `1.0 / +0.0` là dương vô cực còn `1.0 / -0.0` là âm vô cực.

Có thể quan sát dấu zero bằng `Double.doubleToRawLongBits()`:

```java
double negativeZero = -0.0;

boolean negativeByComparison = negativeZero < 0.0;
boolean hasNegativeSign = Double.doubleToRawLongBits(negativeZero) < 0;

System.out.println(negativeByComparison);
System.out.println(hasNegativeSign);
```

Stdout:

```text
false
true
```

Chỉ kiểm tra bit dấu khi nghiệp vụ thực sự cần phân biệt hai zero. Trong hầu hết kiểm tra số âm thông thường, `-0.0` được xem là bằng 0.

## 8. Kiểm tra đầu vào và chuyển đổi an toàn

Các phương thức parse như `Integer.parseInt()`, `Long.parseLong()`, `Float.parseFloat()` và `Double.parseDouble()` có thể ném `NumberFormatException` nếu chuỗi không đúng định dạng hoặc giá trị vượt phạm vi kiểu đích.

Ví dụ:

```java
String text = "2147483648";

try {
    int value = Integer.parseInt(text);
    System.out.println(value);
} catch (NumberFormatException exception) {
    System.out.println("Invalid int input");
}
```

Đối với chuỗi dấu phẩy động, `Double.parseDouble("NaN")` và `Double.parseDouble("Infinity")` có thể trả về các giá trị đặc biệt tương ứng. Vì vậy, parse thành công không có nghĩa là giá trị hữu hạn hoặc phù hợp với nghiệp vụ. Hãy kiểm tra tiếp `Double.isFinite()` nếu cần.

Một quy trình xác thực số thường gồm:

1. Kiểm tra chuỗi có parse được sang kiểu dự kiến không.
2. Kiểm tra NaN/vô cực nếu kiểu là float hoặc double.
3. Kiểm tra dấu và miền giá trị theo quy tắc nghiệp vụ.
4. Dùng phép toán exact hoặc kiểu BigInteger/BigDecimal nếu kết quả có thể vượt giới hạn hoặc cần độ chính xác thập phân.
5. Chỉ chuyển về kiểu nhỏ hơn sau khi đã xác minh giá trị biểu diễn được.

Không nên chỉ bắt `Exception` chung rồi coi đầu vào là hợp lệ. Hãy xử lý các lỗi dự kiến như `NumberFormatException` hoặc `ArithmeticException` theo đúng ý nghĩa.

## 9. Ví dụ Java hoàn chỉnh

Tạo tệp `NumericChecksDemo.java`:

```java
import java.math.BigDecimal;
import java.math.BigInteger;

public class NumericChecksDemo {
    public static void main(String[] args) {
        int balance = -25;
        System.out.println("negative int: " + (balance < 0));

        System.out.println("int min: " + Integer.MIN_VALUE);
        System.out.println("int max: " + Integer.MAX_VALUE);

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException exception) {
            System.out.println("int overflow detected");
        }

        try {
            Math.toIntExact((long) Integer.MAX_VALUE + 1L);
        } catch (ArithmeticException exception) {
            System.out.println("long to int overflow detected");
        }

        BigInteger beyondLong =
                BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE);
        System.out.println("beyond long: "
                + (beyondLong.compareTo(BigInteger.valueOf(Long.MAX_VALUE)) > 0));

        BigDecimal exactDecimal = new BigDecimal("123.00");
        System.out.println("exact decimal to int: "
                + exactDecimal.intValueExact());

        try {
            new BigDecimal("123.45").intValueExact();
        } catch (ArithmeticException exception) {
            System.out.println("fractional decimal rejected");
        }

        double nan = Double.NaN;
        double infinity = Double.POSITIVE_INFINITY;
        System.out.println("NaN detected: " + Double.isNaN(nan));
        System.out.println("NaN less than zero: " + (nan < 0.0));
        System.out.println("infinity detected: " + Double.isInfinite(infinity));
        System.out.println("finite value accepted: " + Double.isFinite(1.5));

        double negativeZero = -0.0;
        System.out.println("negative zero less than zero: "
                + (negativeZero < 0.0));
        System.out.println("negative zero sign bit: "
                + (Double.doubleToRawLongBits(negativeZero) < 0));

        try {
            Integer.parseInt("2147483648");
        } catch (NumberFormatException exception) {
            System.out.println("out-of-range int text rejected");
        }
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac --release 17 NumericChecksDemo.java
java NumericChecksDemo
```

Stdout chính xác:

```text
negative int: true
int min: -2147483648
int max: 2147483647
int overflow detected
long to int overflow detected
beyond long: true
exact decimal to int: 123
fractional decimal rejected
NaN detected: true
NaN less than zero: false
infinity detected: true
finite value accepted: true
negative zero less than zero: false
negative zero sign bit: true
out-of-range int text rejected
```

## 10. Lỗi thường gặp

1. **Chỉ dùng `value < 0` để xác thực double**: NaN không bị phát hiện và `-0.0` không được xem là âm theo phép so sánh thông thường. Kiểm tra hữu hạn và quy tắc dấu riêng.
2. **Cho rằng ép kiểu sẽ báo tràn**: ép `long` sang `int` có thể làm thay đổi giá trị mà không ném exception. Dùng `Math.toIntExact()` hoặc kiểm tra biên trước.
3. **Cho rằng phép cộng/trừ số nguyên tự phát hiện overflow**: toán tử thông thường không ném exception khi tràn. Dùng `Math.addExact()` và các phương thức exact tương ứng nếu cần phát hiện.
4. **Dùng `Math.abs(Integer.MIN_VALUE)` để lấy trị tuyệt đối**: kết quả vẫn âm do trị tuyệt đối vượt miền int. Kiểm tra riêng hoặc dùng BigInteger.
5. **So sánh NaN bằng `== Double.NaN`**: phép so sánh luôn false. Dùng `Double.isNaN()`.
6. **Chỉ kiểm tra parse thành công**: chuỗi `"NaN"` hoặc `"Infinity"` có thể parse thành công với double nhưng không phải số hữu hạn. Kiểm tra `Double.isFinite()` khi cần.
7. **Dùng `new BigDecimal(0.1)` cho số thập phân chính xác**: constructor nhận double và giữ giá trị nhị phân thực tế. Ưu tiên chuỗi thập phân hoặc `BigDecimal.valueOf()` khi phù hợp.
8. **Dùng `BigDecimal.equals()` để so sánh giá trị số**: `2.0` và `2.00` không equals vì scale khác nhau. Dùng `compareTo() == 0` nếu chỉ quan tâm giá trị.
9. **Dùng `intValue()` hoặc `longValue()` khi cần bảo toàn dữ liệu**: các phép chuyển đổi này có thể mất phần thập phân hoặc phần cao. Dùng phương thức `*ValueExact()` để kiểm tra.
10. **Nhầm `Double.MIN_VALUE` với số âm nhỏ nhất**: `Double.MIN_VALUE` là số dương khác 0 nhỏ nhất (subnormal), còn giá trị hữu hạn âm có độ lớn lớn nhất là `-Double.MAX_VALUE`. Dùng đúng hằng số theo mục đích.

## 11. Chọn công cụ theo yêu cầu

| Nhu cầu | Cách phù hợp |
|---|---|
| Kiểm tra số nguyên âm | `value < 0` |
| Kiểm tra giá trị BigInteger/BigDecimal âm | `signum() < 0` |
| Kiểm tra biên int/long | `MIN_VALUE`, `MAX_VALUE` |
| Phát hiện overflow khi tính số nguyên | `Math.*Exact()` |
| Chuyển long sang int có kiểm tra | `Math.toIntExact()` |
| Số nguyên vượt miền long | `BigInteger` |
| Số thập phân cần độ chính xác | `BigDecimal` |
| Kiểm tra NaN | `Double.isNaN()` / `Float.isNaN()` |
| Kiểm tra vô cực | `Double.isInfinite()` / `Float.isInfinite()` |
| Chỉ chấp nhận số dấu phẩy động hữu hạn | `Double.isFinite()` / `Float.isFinite()` |
| Phân biệt signed zero | `doubleToRawLongBits()` hoặc `floatToRawIntBits()` |

Kiểm tra số cần bám theo kiểu dữ liệu và hợp đồng nghiệp vụ. Với số nguyên, quan tâm miền giá trị và overflow; với số dấu phẩy động, cần xét thêm NaN, vô cực và signed zero; với số thập phân chính xác hoặc miền giá trị lớn, cân nhắc BigDecimal và BigInteger.
