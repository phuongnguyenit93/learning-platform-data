# Phân biệt ép kiểu, làm tròn và kiểm tra chuyển đổi `exact` trong Java

## 1. Ba câu hỏi khác nhau khi chuyển đổi số

Khi chuyển một giá trị từ kiểu số này sang kiểu số khác, cần tách ba mục tiêu:

1. **Ép kiểu (cast/conversion)**: đưa giá trị sang một kiểu dữ liệu khác theo quy tắc của Java. Phép chuyển có thể giữ nguyên, làm mất phần thập phân, làm mất bit, hoặc giới hạn giá trị ở biên kiểu đích.
2. **Làm tròn (rounding)**: chọn một giá trị đại diện theo quy tắc rõ ràng (gần nhất, lên, xuống, về 0, quy tắc xử lý trường hợp đúng giữa hai mức...). Làm tròn không đồng nghĩa với đổi kiểu, cũng không đảm bảo kết quả nằm trong miền kiểu đích.
3. **Chuyển đổi chính xác (`exact`)**: yêu cầu kết quả giữ nguyên giá trị số theo hợp đồng API; nếu phải bỏ phần lẻ hoặc vượt giới hạn kiểu đích thì báo lỗi, thường là `ArithmeticException`.

Ví dụ với `12.8`:

- `(int) 12.8` cho `12` vì chuyển `double` sang `int` cắt phần thập phân về phía 0.
- `Math.round(12.8)` cho `13L`, vì hàm chọn số nguyên gần nhất và trả về `long` với đối số `double`.
- `new BigDecimal("12.8").intValueExact()` ném `ArithmeticException`, vì `12.8` không phải số nguyên.

Không có phép nào trong ba phép trên tự động phù hợp mọi nghiệp vụ. Đặc biệt, *`exact`* nói về việc chuyển không làm đổi **giá trị hiện đang được lưu**, chứ không khôi phục được độ chính xác đã mất ở bước tính toán trước đó.

## 2. Nền tảng: miền giá trị, độ rộng và độ chính xác

| Kiểu nguyên thủy | Độ rộng | Miền / đặc tính quan trọng |
| --- | ---: | --- |
| `byte` | 8 bit | `-128` đến `127` |
| `short` | 16 bit | `-32768` đến `32767` |
| `char` | 16 bit | Không dấu `0` đến `65535`; là một đơn vị mã UTF-16 |
| `int` | 32 bit | `-2147483648` đến `2147483647` |
| `long` | 64 bit | `-9223372036854775808` đến `9223372036854775807` |
| `float` | 32 bit | Số dấu phẩy động nhị phân, khoảng 24 bit độ chính xác phần trị |
| `double` | 64 bit | Số dấu phẩy động nhị phân, khoảng 53 bit độ chính xác phần trị |

Giá trị `float`/`double` còn có thể là `NaN`, `+Infinity`, `-Infinity` và `+0.0`/`-0.0`. Chúng không biểu diễn chính xác mọi số thập phân hữu hạn; chẳng hạn `0.1` không có biểu diễn nhị phân hữu hạn chính xác trong `double`.

### Widening không phải lúc nào cũng giữ nguyên độ chính xác

Một số chuyển đổi mở rộng (*widening*) là chính xác: `byte` → `short` → `int` → `long` giữ nguyên giá trị nguyên; `float` → `double` giữ chính xác giá trị `float` **đã có**.

Tuy nhiên, `int` → `float` và `long` → `double` có thể làm mất bit chính xác dù kiểu đích thường được gọi là “rộng hơn”. Ví dụ:

```java
long original = 9_007_199_254_740_993L; // 2^53 + 1
double converted = original;            // 2^53
long back = (long) converted;            // 9_007_199_254_740_992L
```

`double` chỉ có 53 bit phần trị chính xác, nên không biểu diễn được hai số nguyên liên tiếp ở vùng này. Sau khi chuyển thành `double`, thông tin đã mất; ép ngược hoặc gọi một phương thức `exact` sau đó không thể tái tạo số ban đầu. Khi so sánh trực tiếp `original == converted`, Java lại chuyển `long` sang `double` để so sánh, nên cách so sánh đó cũng có thể che giấu mất mát. Hãy kiểm tra trước khi chuyển hoặc dùng một miền số phù hợp.

## 3. Ép kiểu nguyên thủy: kết quả có thể mất dữ liệu mà không báo lỗi

### 3.1. Từ số nguyên lớn xuống số nguyên nhỏ

Phép chuyển thu hẹp (*narrowing*) bằng cast, như `(int) someLong` hay `(byte) someInt`, giữ các bit thấp phù hợp với độ rộng kiểu đích. Với kiểu có dấu, mẫu bit kết quả được diễn giải theo bù hai.

```java
int a = 130;
byte b = (byte) a; // -126

long large = 3_000_000_000L;
int narrowed = (int) large; // -1294967296
```

Với `130`, 8 bit thấp là `1000_0010`, mang giá trị `-126` trong `byte`. Với `3_000_000_000L`, 32 bit thấp tương ứng với giá trị `int` âm. Java **không ném ngoại lệ** khi cast nguyên thủy mất bit.

Với `char`, kết quả nằm trong `0..65535`; giá trị lớn hơn cũng bị giữ 16 bit thấp. Vì `char` là đơn vị mã UTF-16, không nên coi cast số → `char` là thao tác chuyển số Unicode code point bất kỳ thành ký tự đầy đủ.

### 3.2. Từ `float`/`double` sang `int`/`long`

Với giá trị hữu hạn còn nằm trong miền kiểu đích, Java **cắt phần thập phân về phía 0** (*truncation toward zero*), khác với làm tròn số nguyên gần nhất:

| Biểu thức | Kết quả |
| --- | ---: |
| `(int) 2.9` | `2` |
| `(int) -2.9` | `-2` |
| `(long) 2.9` | `2L` |
| `(long) -2.9` | `-2L` |

Các biên đặc biệt quan trọng:

- `NaN` chuyển sang `int`/`long` thành `0`.
- Giá trị quá lớn phía dương (kể cả `+Infinity`) chuyển thành `Integer.MAX_VALUE` hoặc `Long.MAX_VALUE`.
- Giá trị quá nhỏ phía âm (kể cả `-Infinity`) chuyển thành `Integer.MIN_VALUE` hoặc `Long.MIN_VALUE`.
- Cast không ném `ArithmeticException` khi xảy ra các trường hợp trên.

Ví dụ `(int) 1e20` cho `2147483647`; `(int) Double.NaN` cho `0`. Vì vậy cast **không phải** một phép xác thực đầu vào.

Đối với ép `double` → `float`, Java cũng có thể làm tròn theo độ chính xác nhị phân thấp hơn; giá trị có độ lớn quá lớn có thể trở thành vô cực, giá trị rất nhỏ có thể thành 0 (hoặc số subnormal). Đây là quy tắc chuyển dấu phẩy động, không phải hành vi cắt phần thập phân của `double` → `int`.

### 3.3. Cú pháp cast khác với parse

`(int) d` chuyển một giá trị số có sẵn. `Integer.parseInt("123")` đọc một **chuỗi ký tự** thành số nguyên, kiểm tra cú pháp và miền `int`, có thể ném `NumberFormatException`.

```java
int a = (int) 12.9;         // 12
int b = Integer.parseInt("12"); // 12
// Integer.parseInt("12.9"); // NumberFormatException
```

Nếu đầu vào người dùng phải là số nguyên và không được mất phần lẻ, hãy phân tích chuỗi bằng API phù hợp (`Integer.parseInt`, hoặc `BigDecimal` nếu có định dạng thập phân cần kiểm tra), thay vì parse sang `double` rồi cast.

## 4. Làm tròn: xác định đúng hướng và quy tắc khi gặp giá trị giữa hai mức

### 4.1. Cast, `floor`, `ceil`, `round` và `rint`

Các API toán học của `Math` trả kết quả theo những quy tắc khác nhau:

| Phép toán | Quy tắc | Ví dụ với `2.5` | Ví dụ với `-2.5` |
| --- | --- | --- | --- |
| `(int) x` | Cắt về phía 0 (nếu hữu hạn, trong miền) | `2` | `-2` |
| `Math.floor(x)` | Số nguyên lớn nhất `<= x`, kết quả `double` | `2.0` | `-3.0` |
| `Math.ceil(x)` | Số nguyên nhỏ nhất `>= x`, kết quả `double` | `3.0` | `-2.0` |
| `Math.round(x)` | Số nguyên gần nhất; khi đúng giữa hai số, chọn số lớn hơn | `3` | `-2` |
| `Math.rint(x)` | Số nguyên gần nhất ở dạng `double`; hòa chọn số chẵn | `2.0` | `-2.0` |

Trong bảng, `Math.round(double)` trả về **`long`**, còn `Math.round(float)` trả về **`int`**. `Math.floor`, `Math.ceil`, `Math.rint` trả kiểu `double`; **kiểu trả về khác nhau** dù các kết quả nhìn giống số nguyên.

Các ví dụ khác:

```java
Math.round(2.5);  // 3L
Math.round(-1.5); // -1L
Math.rint(3.5);   // 4.0
Math.rint(2.5);   // 2.0
Math.floor(-2.2); // -3.0
Math.ceil(-2.2);  // -2.0
```

`Math.round` cũng xử lý `NaN` thành `0` và bão hòa ở biên `int`/`long` với vô cực hoặc giá trị vượt miền. Vì vậy, dù có chữ “round”, kết quả của hàm **không có nghĩa là** đã xác thực giới hạn kiểu đích. `Math.floor`/`ceil`/`rint` giữ kết quả dạng `double` và có quy tắc riêng với `NaN`/vô cực; nếu sau đó cast, các quy tắc mất dữ liệu của cast vẫn áp dụng.

### 4.2. RoundingMode của `BigDecimal`

Khi cần kiểm soát số chữ số thập phân, đặc biệt với tiền, thuế hoặc dữ liệu yêu cầu quy tắc làm tròn được chỉ định, dùng `BigDecimal.setScale(scale, roundingMode)`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal x = new BigDecimal("12.345");
BigDecimal a = x.setScale(2, RoundingMode.HALF_UP);   // 12.35
BigDecimal b = x.setScale(2, RoundingMode.HALF_EVEN); // 12.34
```

Ở đây `scale = 2` nghĩa là hai chữ số bên phải dấu thập phân; **không** phải hai chữ số có nghĩa. Các chế độ thường dùng:

| Chế độ | Quy tắc chính | Ví dụ làm tròn thành số nguyên |
| --- | --- | --- |
| `UP` | Ra xa 0 khi phải bỏ chữ số khác 0 | `-2.1 → -3` |
| `DOWN` | Về phía 0 | `-2.9 → -2` |
| `CEILING` | Về phía dương vô cực | `-2.1 → -2` |
| `FLOOR` | Về phía âm vô cực | `-2.1 → -3` |
| `HALF_UP` | Gần nhất; đúng giữa hai mức thì ra xa 0 | `-2.5 → -3` |
| `HALF_DOWN` | Gần nhất; đúng giữa hai mức thì về 0 | `-2.5 → -2` |
| `HALF_EVEN` | Gần nhất; đúng giữa hai mức thì chọn chữ số cuối chẵn | `2.5 → 2`, `3.5 → 4` |
| `UNNECESSARY` | Không cho phép bỏ phần có giá trị; cần làm tròn thì ném lỗi | `2.5` về scale 0 → lỗi |

`Math.round(-2.5)` là `-2`, nhưng `new BigDecimal("-2.5").setScale(0, RoundingMode.HALF_UP)` là `-3`. Cả hai đều đúng theo quy tắc riêng; không nên gọi chung chung là “làm tròn kiểu thông thường”.

Để tính decimal ổn định, ưu tiên `new BigDecimal("0.1")` hoặc `BigDecimal.valueOf(0.1)`. `new BigDecimal(0.1)` ghi lại **giá trị nhị phân chính xác của `double` đã làm tròn**, vốn không bằng chính xác `0.1` trong hệ thập phân. `BigDecimal.valueOf(double)` sử dụng chuỗi thập phân chuẩn của giá trị `double`, nhưng không thể phục hồi các chữ số mà phép tính dấu phẩy động trước đó đã làm mất.

## 5. Các API chuyển đổi `exact` kiểm tra điều gì?

### 5.1. `Math.toIntExact(long)`: thu hẹp `long` → `int` có kiểm tra miền

```java
int ok = Math.toIntExact(42L); // 42

// Ném ArithmeticException vì vượt Integer.MAX_VALUE:
int overflow = Math.toIntExact(3_000_000_000L);
```

`Math.toIntExact` không có overload nhận `double` hoặc `BigDecimal`; nó chỉ dùng cho một giá trị `long` muốn chuyển sang `int`. Trái với `(int) someLong`, hàm này **từ chối** giá trị ngoài phạm vi `int`. Nếu cần kiểm tra tràn số của phép cộng/nhân nguyên trong quá trình tính, có các hàm liên quan `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`...; đó là kiểm tra **phép tính**, không phải ép kiểu.

### 5.2. `BigInteger.intValueExact()` / `longValueExact()`

`BigInteger` có thể lớn hơn miền `long`. Hai phương thức `intValueExact()` và `longValueExact()` ném `ArithmeticException` nếu giá trị không vừa kiểu đích.

```java
import java.math.BigInteger;

BigInteger small = new BigInteger("2147483647");
int ok = small.intValueExact(); // 2147483647

BigInteger tooLarge = new BigInteger("2147483648");
// tooLarge.intValueExact(); // ArithmeticException
long fitsLong = tooLarge.longValueExact(); // 2147483648L
```

Trong khi đó, `.intValue()`/`.longValue()` có thể làm mất bit; tên không có `Exact` không đảm bảo giữ nguyên giá trị.

### 5.3. `BigDecimal.intValueExact()` / `longValueExact()`

Với `BigDecimal`, `exact` kiểm tra **cả phần lẻ lẫn phạm vi**:

```java
import java.math.BigDecimal;

new BigDecimal("12.00").intValueExact(); // 12: phần thập phân chỉ gồm 0
new BigDecimal("-4").longValueExact();   // -4L

// new BigDecimal("12.01").intValueExact();  // ArithmeticException: có phần lẻ
// new BigDecimal("2147483648").intValueExact(); // ArithmeticException: quá miền
```

Điều kiện không phải `scale == 0`: `12.00` có scale là 2 nhưng vẫn biểu thị chính xác số nguyên 12. Các phương thức `.intValue()` và `.longValue()` thông thường không phát tín hiệu khi bỏ phần lẻ hoặc vượt miền.

Nếu mục tiêu là **phải có số nguyên**, hãy gọi `intValueExact()` trực tiếp lên giá trị `BigDecimal` gốc. Nếu nghiệp vụ cho phép làm tròn trước, hãy chọn rõ `RoundingMode`, rồi gọi `intValueExact()` lên giá trị đã làm tròn. Hai quy trình này có ý nghĩa khác nhau:

```java
BigDecimal input = new BigDecimal("12.8");

// Không được làm mất phần lẻ: input.intValueExact() sẽ ném lỗi.
int rounded = input.setScale(0, java.math.RoundingMode.HALF_UP)
                   .intValueExact(); // 13
```

`setScale(0, ...)` giải quyết chuyện phần lẻ; `intValueExact()` sau đó vẫn kiểm tra miền `int`. Nếu muốn không bao giờ phải làm tròn, có thể dùng `RoundingMode.UNNECESSARY` và kiểm tra chính xác.

### 5.4. Có phương thức `exact` cho `double` → `int` không?

Không có `Math.toIntExact(double)` trong Java 17. Với dữ liệu `double` hiện có, hãy kiểm tra hữu hạn, nguyên vẹn và trong miền `int` **trước khi cast**:

```java
static int requireInt(double value) {
    if (!Double.isFinite(value)
            || value != Math.rint(value)
            || value < Integer.MIN_VALUE
            || value > Integer.MAX_VALUE) {
        throw new ArithmeticException("Cannot convert exactly to int");
    }
    return (int) value;
}
```

Ở đây `Math.rint(value)` giúp xác nhận giá trị `double` hiện tại là số nguyên (không cần làm tròn); dấu `==`/`!=` có thể so sánh chính xác trong trường hợp này vì ta so sánh hai `double` và đã lọc `NaN`/vô cực. Giá trị `-0.0` được chấp nhận thành `int` 0, vì `int` không phân biệt dấu của số 0.

**Bẫy biên `long`:** không sao chép mù quáng điều kiện `value > Long.MAX_VALUE` vào phép kiểm tra `double` → `long`. `Long.MAX_VALUE` khi chuyển sang `double` làm tròn thành `2^63`, nên phép so sánh đó có thể chấp nhận sai một giá trị ngoài miền. Nếu cần chuyển `double` thành `long` đúng với **giá trị `double` đang có**, dùng giới hạn nửa mở, chẳng hạn:

```java
static long requireLong(double value) {
    if (!Double.isFinite(value)
            || value != Math.rint(value)
            || value < -0x1.0p63
            || value >= 0x1.0p63) {
        throw new ArithmeticException("Cannot convert exactly to long");
    }
    return (long) value;
}
```

`0x1.0p63` là literal `double` biểu diễn chính xác `2^63`; `Long.MIN_VALUE == -2^63` vẫn hợp lệ, nhưng `+2^63` đã vượt `Long.MAX_VALUE`. Dẫu vậy, nếu một `long` lớn đã được đổi sang `double` và mất bit trước đó, cả kiểm tra này lẫn cast đều không thể phát hiện hay sửa lại giá trị `long` ban đầu. Khi có dữ liệu thập phân ban đầu, hãy giữ dữ liệu trong `BigDecimal` và dùng phương thức `...ValueExact()` ngay trên nguồn đó.

## 6. Chọn phép toán theo yêu cầu nghiệp vụ

| Yêu cầu | Lựa chọn phù hợp | Cảnh báo |
| --- | --- | --- |
| Chuyển `int` thành `long` | Gán trực tiếp `long n = i;` | Giữ nguyên giá trị |
| Chuyển `long` thành `int`, phải nguyên vẹn | `Math.toIntExact(n)` | Ném `ArithmeticException` nếu ngoài miền |
| Chuyển `long` thành `int`, cố ý giữ bit thấp | `(int) n` | Có thể đổi dấu/giá trị |
| Chuyển số thực thành số nguyên bằng cách cắt về 0 | Cast sau khi xác thực phạm vi nếu cần | `NaN` và quá miền có kết quả đặc biệt |
| Làm tròn đến số nguyên gần nhất, hòa về phía dương | `Math.round(...)` | Không dùng để chứng minh đầu vào nằm trong miền |
| Làm tròn đến số nguyên gần nhất, hòa về số chẵn | `Math.rint(double)` hoặc `BigDecimal` `HALF_EVEN` | `rint` vẫn trả `double` |
| Làm tròn tiền thành hai chữ số thập phân | `BigDecimal.setScale(2, mode)` | Quy tắc `mode` phải đến từ yêu cầu nghiệp vụ |
| Chuyển decimal thành `int` không mất thông tin | `BigDecimal.intValueExact()` | Cần là số nguyên và vừa miền `int` |
| Chuyển `BigInteger` thành `long` không mất thông tin | `BigInteger.longValueExact()` | Không vừa miền sẽ ném lỗi |
| Nhập chuỗi số nguyên từ người dùng | `Integer.parseInt` / `Long.parseLong` | Lỗi chuỗi/miền là `NumberFormatException` |

Không chọn `Math.round` chỉ vì tên gọi nghe “an toàn”. `round`, `cast` và `exact` trả lời ba câu hỏi khác nhau về cách xử lý phần lẻ, tràn miền và thất thoát dữ liệu.

## 7. Ví dụ Java 17 đầy đủ và kết quả kiểm chứng

Lưu tệp `NumericConversionDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class NumericConversionDemo {
    public static void main(String[] args) {
        System.out.println("cast 2.9 = " + (int) 2.9);
        System.out.println("cast -2.9 = " + (int) -2.9);
        System.out.println("cast byte 130 = " + (byte) 130);
        System.out.println("cast NaN = " + (int) Double.NaN);
        System.out.println("cast 1e20 = " + (int) 1e20);

        System.out.println("round 2.5 = " + Math.round(2.5));
        System.out.println("round -2.5 = " + Math.round(-2.5));
        System.out.println("rint 2.5 = " + Math.rint(2.5));
        System.out.println("rint 3.5 = " + Math.rint(3.5));
        System.out.println("floor -2.2 = " + Math.floor(-2.2));
        System.out.println("ceil -2.2 = " + Math.ceil(-2.2));

        BigDecimal negativeHalf = new BigDecimal("-2.5");
        BigDecimal positiveHalf = new BigDecimal("2.5");
        System.out.println("HALF_UP -2.5 = "
                + negativeHalf.setScale(0, RoundingMode.HALF_UP));
        System.out.println("HALF_EVEN 2.5 = "
                + positiveHalf.setScale(0, RoundingMode.HALF_EVEN));

        System.out.println("Math.toIntExact(42) = " + Math.toIntExact(42L));
        System.out.println("BigDecimal 12.00 exact = "
                + new BigDecimal("12.00").intValueExact());

        try {
            Math.toIntExact(3_000_000_000L);
        } catch (ArithmeticException e) {
            System.out.println("long to int overflow: ArithmeticException");
        }

        try {
            new BigDecimal("12.5").intValueExact();
        } catch (ArithmeticException e) {
            System.out.println("decimal with fraction: ArithmeticException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac NumericConversionDemo.java
java NumericConversionDemo
```

Kết quả:

```text
cast 2.9 = 2
cast -2.9 = -2
cast byte 130 = -126
cast NaN = 0
cast 1e20 = 2147483647
round 2.5 = 3
round -2.5 = -2
rint 2.5 = 2.0
rint 3.5 = 4.0
floor -2.2 = -3.0
ceil -2.2 = -2.0
HALF_UP -2.5 = -3
HALF_EVEN 2.5 = 2
Math.toIntExact(42) = 42
BigDecimal 12.00 exact = 12
long to int overflow: ArithmeticException
decimal with fraction: ArithmeticException
```

Ví dụ dùng literal `double` và `BigDecimal` từ chuỗi rõ ràng để tránh trộn lẫn kết quả làm tròn nhị phân với quy tắc rounding thập phân.

## 8. Khi dữ liệu đến từ chuỗi hoặc phép tính thập phân

Hãy xét yêu cầu: người dùng nhập số lượng sản phẩm ở dạng `"12.00"`, hệ thống chỉ chấp nhận số lượng nguyên trong miền `int`. Cách phù hợp là:

```java
import java.math.BigDecimal;

public class QuantityParser {
    public static int parseQuantity(String raw) {
        BigDecimal parsed = new BigDecimal(raw);
        int quantity = parsed.intValueExact();
        if (quantity < 0) {
            throw new IllegalArgumentException("Quantity must be non-negative");
        }
        return quantity;
    }

    public static void main(String[] args) {
        System.out.println(parseQuantity("12.00")); // 12
    }
}
```

```bash
javac QuantityParser.java
java QuantityParser
```

```text
12
```

`new BigDecimal(raw)` có thể ném `NumberFormatException` nếu chuỗi không hợp lệ; `intValueExact()` có thể ném `ArithmeticException` nếu số có phần lẻ hoặc vượt miền. Sau đó mới kiểm tra luật nghiệp vụ (ví dụ không âm). Như vậy mỗi lỗi có ý nghĩa riêng và không bị âm thầm cắt dữ liệu.

Trái lại, nếu yêu cầu là *cho phép số lẻ và làm tròn số lượng* thì phải xác định `RoundingMode` rõ ràng trước khi dùng `intValueExact()`. Không tự quyết định `HALF_UP` hay `HALF_EVEN` chỉ dựa vào thói quen.

Một tình huống tương tự là tính tiền. Nếu tổng tiền cần hai chữ số thập phân, giữ giá trị trong `BigDecimal`, tính với độ chính xác phù hợp, rồi dùng `setScale(2, mode)` theo yêu cầu kế toán. Cast sang `int` chỉ giữ phần nguyên và khiến phần lẻ bị loại bỏ, không tương đương làm tròn đến đơn vị tiền nhỏ.

## 9. Những lỗi phổ biến và cách phát hiện

1. **Cho rằng cast là làm tròn.** `(int) -2.9 == -2`, còn `Math.floor(-2.9) == -3.0`; các phép toán phục vụ mục đích khác nhau.
2. **Cho rằng cast tự báo tràn.** `(int) 3_000_000_000L` cho giá trị âm; `Math.toIntExact(3_000_000_000L)` mới ném `ArithmeticException`.
3. **Cho rằng `Math.round` bảo đảm không vượt miền.** `Math.round(Double.POSITIVE_INFINITY)` trả `Long.MAX_VALUE`; `Math.round(Double.NaN)` trả `0`.
4. **Trộn quy tắc hòa khi làm tròn.** `Math.round(-2.5) == -2`, `HALF_UP` của `BigDecimal("-2.5")` cho `-3`, còn `HALF_EVEN` chọn chữ số cuối chẵn.
5. **Tạo `BigDecimal` từ `double` mà không hiểu dữ liệu nguồn.** `new BigDecimal(0.1)` ghi lại giá trị nhị phân của `double`; nếu yêu cầu đúng số thập phân `0.1` từ đầu vào, dùng chuỗi hoặc dữ liệu decimal nguyên gốc.
6. **Làm mất dữ liệu trước khi kiểm tra `exact`.** `(long) someDouble` đã có thể cắt/bão hòa; `Math.toIntExact((long) someDouble)` chỉ kiểm tra `long` sau bước cast, không thể kiểm tra phần lẻ hoặc vô cực của nguồn ban đầu.
7. **Dùng `Long.MAX_VALUE` làm cận trên cho `double` → `long`.** Giá trị `Long.MAX_VALUE` khi chuyển sang `double` không biểu diễn chính xác; cận trên an toàn là `value < 0x1.0p63`.
8. **Chỉ kiểm tra phần lẻ mà quên giới hạn kiểu đích.** `1e20` là một giá trị `double` không có phần lẻ, nhưng không vừa trong `int` hoặc `long`; kiểm tra `x == Math.rint(x)` là chưa đủ.
9. **Nhầm chữ `Exact` là “luôn cho ra đáp án thập phân chính xác”.** `BigDecimal.intValueExact` bảo đảm chuyển integer value hiện có, không sửa sai số từ phép tính `double` trước đó.
10. **Bỏ qua kiểu trả về.** `Math.round(float)` trả `int`, `Math.round(double)` trả `long`, còn `Math.floor`/`Math.ceil`/`Math.rint` trả `double`. Việc ép tiếp sang kiểu nhỏ hơn cần kiểm tra riêng.
11. **Dùng `parseInt` để hiểu chuỗi decimal.** `"12.00"` không hợp lệ với `Integer.parseInt` dù có thể được `BigDecimal.intValueExact()` chuyển thành 12 sau khi parse thành decimal.
12. **Lấy `RoundingMode` từ trực giác.** Quy tắc kế toán, điều chỉnh điểm, thống kê và hiển thị có thể khác nhau; phải ghi rõ cách xử lý phần lẻ, dấu âm và trường hợp đúng giữa hai mức.

## 10. Bài tập tự kiểm tra

Hãy dự đoán kết quả hoặc ngoại lệ trước khi chạy Java:

```java
(int) -7.9
Math.round(-7.5)
Math.rint(7.5)
Math.toIntExact((long) Integer.MAX_VALUE + 1)
new java.math.BigDecimal("15.000").intValueExact()
new java.math.BigDecimal("15.001").intValueExact()
new java.math.BigDecimal("-1.5")
    .setScale(0, java.math.RoundingMode.HALF_UP)
```

**Đáp án theo thứ tự:**

1. `-7` vì cast cắt phần lẻ về phía 0.
2. `-7L` vì `Math.round` chọn số nguyên gần nhất, đúng giữa hai số chọn phía dương.
3. `8.0` vì `Math.rint` hòa về số chẵn.
4. `ArithmeticException` vì lớn hơn `Integer.MAX_VALUE`.
5. `15` vì phần thập phân chỉ chứa các chữ số 0.
6. `ArithmeticException` vì còn phần lẻ khác 0.
7. `-2` dưới dạng `BigDecimal` vì `HALF_UP` ra xa 0 khi đúng giữa hai mức.

**Quy tắc ghi nhớ:** khi muốn **thay kiểu** có thể cast (và chấp nhận quy tắc mất dữ liệu), khi muốn **chọn giá trị gần mức nào** phải chỉ rõ rounding, còn khi muốn **bảo toàn giá trị** hãy dùng `...Exact()` hoặc một phép kiểm tra tương đương **trước** khi thực hiện cast. Nếu dữ liệu bắt đầu từ chuỗi thập phân, giữ chúng ở dạng decimal cho đến khi hoàn tất xác thực và làm tròn theo yêu cầu.