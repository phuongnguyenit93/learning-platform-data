# Giới hạn tài nguyên cho đầu vào BigInteger hoặc BigDecimal rất lớn

## 1. Vì sao số “chính xác, không giới hạn” vẫn cần giới hạn?

`java.math.BigInteger` và `java.math.BigDecimal` khắc phục giới hạn miền giá trị hoặc độ chính xác của các kiểu số nguyên/số thực nguyên thủy trong nhiều trường hợp. Tuy vậy, **độ lớn tùy ý** (*arbitrary precision*) không có nghĩa bộ nhớ, CPU, thời gian xử lý hoặc độ dài đầu ra đều vô hạn.

Khi nhận chuỗi số từ người dùng, API, file hoặc message queue, ứng dụng có thể đối mặt với ba loại đầu vào:

1. **Dãy chữ số rất dài**: ví dụ một số nguyên chứa hàng triệu chữ số. Chỉ riêng việc nhận, lưu, kiểm tra và phân tích chuỗi đã tốn tài nguyên; tạo `BigInteger` còn phải xây dựng biểu diễn số nguyên lớn.
2. **Chuỗi ngắn nhưng số mũ rất lớn**: ví dụ `"1E+1000000000"`. Số ký tự đầu vào rất ít nhưng giá trị `BigDecimal` có scale âm rất lớn. Nếu cố xuất dạng thông thường bằng `toPlainString()` có thể phải tạo một chuỗi khổng lồ.
3. **Giá trị đầu vào có vẻ vừa phải nhưng phép toán phình to**: ví dụ dịch trái một `BigInteger` hàng triệu bit hoặc lũy thừa với số mũ rất lớn. Kết quả trung gian có thể lớn hơn hẳn đầu vào.

Hậu quả có thể gồm sử dụng quá nhiều RAM, áp lực GC, CPU quá tải, độ trễ lớn, lỗi `OutOfMemoryError`, quá thời gian xử lý, cạn quota của dịch vụ hoặc từ chối dịch vụ (*denial of service*). Không nên giả định constructor sẽ tự áp dụng hạn mức phù hợp với nghiệp vụ.

**Mục tiêu thiết kế:** đặt ngân sách tài nguyên từ trước khi parse, trước phép toán có khả năng mở rộng kích thước và trước khi chuyển số thành chuỗi đầu ra. Mọi giới hạn cần được xác định theo **ngữ cảnh nghiệp vụ**, không lấy các hằng số ví dụ trong bài làm giá trị mặc định cho sản phẩm.

## 2. Hiểu kích thước dữ liệu và chi phí

### BigInteger: dãy chữ số và số bit

`BigInteger` biểu diễn số nguyên độ lớn tùy ý. Chuỗi thập phân dài `d` chữ số thường cần khoảng \(d \times \log_2(10)\), tức khoảng \(3.322d\) bit để biểu diễn độ lớn (ước lượng, không bao gồm overhead object, mảng và bộ nhớ tạm).

Ví dụ một triệu chữ số thập phân tương đương khoảng 3,32 triệu bit, tức hàng trăm KiB chỉ riêng dữ liệu bit ở mức lý thuyết. Nhưng quy trình thực tế còn phải giữ chuỗi đầu vào, mảng, đối tượng, cấu trúc tạm và tài nguyên của thuật toán parse/tính toán. **Không dùng ước lượng số bit làm cam kết về RAM thực tế.**

`BigInteger.bitLength()` cho biết độ dài bit tối thiểu theo hợp đồng API (cách xử lý số âm có quy tắc riêng); `toString().length()` là độ dài biểu diễn thập phân, có thể đòi hỏi chuyển đổi đáng kể. Khi đầu vào chưa được tin cậy, **đếm số chữ số trên chuỗi trước**, rồi mới dựng `BigInteger`.

Các phép toán có thể làm kết quả tăng rất nhanh:

- `a.multiply(b)`: số bit kết quả xấp xỉ tổng số bit của hai toán hạng.
- `a.shiftLeft(n)`: số bit có thể tăng khoảng `n` với `n` rất lớn.
- `a.pow(n)`: số chữ số/bit kết quả có thể tăng theo `n`, ngay cả khi `a` ngắn.
- `modPow`, chia, `gcd`, kiểm tra nguyên tố: chi phí thời gian phụ thuộc kích thước toán hạng và thuật toán; chỉ giới hạn chiều dài đầu vào là chưa đủ.

### BigDecimal: precision, scale và exponent

`BigDecimal` gồm một giá trị nguyên không chia tỷ lệ (*unscaled value*) và một số `scale` kiểu `int`:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

`precision()` là số chữ số của unscaled value (trường hợp số 0 có precision 1). `scale()` có thể âm, dương hoặc bằng 0:

| Đầu vào | Precision | Scale | Ý nghĩa |
|---|---:|---:|---|
| `"123.4500"` | 7 | 4 | Giá trị 123.4500, giữ 4 chữ số sau dấu thập phân |
| `"1E+6"` | 1 | -6 | Giá trị một triệu |
| `"1E-7"` | 1 | 7 | Giá trị một phần mười triệu |
| `"0.00"` | 1 | 2 | Giá trị 0 với scale 2 |

**Precision nhỏ không đồng nghĩa đầu ra nhỏ.** `new BigDecimal("1E+1000000")` có unscaled value `1` và scale `-1000000` nhưng `toPlainString()` phải trình bày số 1 và một triệu số 0. Trong khi đó `toString()` có thể giữ dạng khoa học rất ngắn. Vì vậy cần chính sách riêng cho **scale/exponent** và **độ dài chuỗi kết quả**.

Ngay cả nếu chuỗi exponent vượt miền mà Java cho phép và constructor ném `NumberFormatException`, ứng dụng vẫn không nên giao việc phát hiện cho constructor sau khi đã nhận một payload không có hạn mức. Giới hạn sớm giúp kết quả kiểm soát được và giảm rủi ro trước khi tạo đối tượng lớn.

## 3. Lớp phòng vệ thứ nhất: giới hạn đầu vào trước parse

Một chính sách đầu vào số cần nêu rõ:

| Hạn mức | Bảo vệ điều gì? | Cách áp dụng |
|---|---|---|
| Tổng kích thước request/file/message | Bộ nhớ và I/O của toàn payload | Hạn mức ở HTTP gateway, message consumer, file reader |
| `maxTextChars` hoặc `maxBytes` | Bộ nhớ chuỗi và chi phí quét | Kiểm tra trước khi dựng số, giới hạn byte từ lớp nhận dữ liệu |
| Số chữ số mantissa/số nguyên | Chi phí parse và độ lớn unscaled value | Đếm ký tự `0..9` trước constructor |
| Số chữ số exponent | Không nhận exponent dài bất thường | Kiểm tra phần sau `E`/`e` |
| Độ lớn tuyệt đối của exponent | Tránh scale cực đoan và chuỗi đầu ra phình to | Parse exponent theo số nguyên có kiểm tra tràn |
| Độ lớn tuyệt đối của scale | Giới hạn dạng thập phân/scientific và các phép toán | Xác minh `scale()` sau parse, có ngân sách parse từ trước |
| Độ dài chuỗi cần xuất | Tránh `toPlainString()` phát sinh chuỗi quá dài | Ước tính trước khi gọi hàm tạo chuỗi |
| Ngân sách bit và phép toán | Kết quả trung gian lớn, CPU cao | Dự báo độ lớn và từ chối phép toán vượt quota |

**Không chỉ dùng `text.length()`.** Chuỗi `"1E+1000000"` chỉ có ít ký tự nhưng việc xuất số ở dạng thập phân có thể rất lớn. Ngược lại, chuỗi có hàng triệu số 0 cần chặn ngay cả khi giá trị toán học bằng 0.

Đối với dữ liệu không tin cậy, ưu tiên một **ngữ pháp đơn giản đã thống nhất**: chỉ ký tự ASCII, dấu `+`/`-` tùy chính sách, đúng một dấu `.` nếu là số thập phân, phần exponent tùy chọn với `E`/`e`, và cấm khoảng trắng/ký tự lạ. Điều này cũng tránh nhầm dấu phân cách theo locale: parser `BigDecimal(String)` dùng cú pháp số của Java, không phải cú pháp tùy tiện của giao diện vùng miền.

Nếu dữ liệu đến trong JSON, cân nhắc nhận giá trị thập phân chính xác dưới dạng **chuỗi** khi cần bảo toàn văn bản/precision; đặt giới hạn body và giới hạn chiều dài giá trị **trước** khi các tầng chuyển đổi tự dựng `BigInteger`/`BigDecimal`. Tránh parse một số tùy ý thành `double` trước rồi mới chuyển sang `BigDecimal` vì có thể làm mất độ chính xác.

## 4. Chương trình Java 17+ kiểm tra trước khi dựng số và trước khi xuất

Đây là ví dụ có **chính sách minh họa**, không phải bộ thông số khuyến nghị cho mọi hệ thống: chuỗi tối đa 80 ký tự UTF-16, tối đa 20 chữ số trong phần số, exponent tối đa 3 ký tự và độ lớn không quá 30, `|scale| <= 30`, dạng plain tối đa 32 ký tự, kết quả dịch trái tối đa 128 bit. Trong ví dụ, toàn bộ dữ liệu đầu vào chỉ cho phép ký tự ASCII nên `String.length()` trùng số ký tự đầu vào; giới hạn byte của request vẫn cần xử lý ở lớp vận chuyển.

Lưu file **`SafeBigNumbers.java`**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;

public class SafeBigNumbers {
    private static final int MAX_TEXT_CHARS = 80;
    private static final int MAX_DIGITS = 20;
    private static final int MAX_EXPONENT_DIGITS = 3;
    private static final int MAX_ABS_EXPONENT = 30;
    private static final int MAX_ABS_SCALE = 30;
    private static final int MAX_PLAIN_CHARS = 32;
    private static final int MAX_RESULT_BITS = 128;

    private static boolean decimalDigit(char c) {
        return c >= '0' && c <= '9';
    }

    public static BigInteger parseInteger(String text) {
        if (text == null || text.isEmpty()
                || text.length() > MAX_TEXT_CHARS) {
            throw new IllegalArgumentException("invalid integer length");
        }

        int i = (text.charAt(0) == '-' || text.charAt(0) == '+')
                ? 1 : 0;
        int digits = 0;

        for (; i < text.length(); i++) {
            if (!decimalDigit(text.charAt(i))) {
                throw new IllegalArgumentException("integer has non-digit");
            }
            if (++digits > MAX_DIGITS) {
                throw new IllegalArgumentException("too many integer digits");
            }
        }

        if (digits == 0) {
            throw new IllegalArgumentException("missing digits");
        }
        return new BigInteger(text);
    }

    public static BigDecimal parseDecimal(String text) {
        if (text == null || text.isEmpty()
                || text.length() > MAX_TEXT_CHARS) {
            throw new IllegalArgumentException("invalid decimal length");
        }

        int i = (text.charAt(0) == '-' || text.charAt(0) == '+')
                ? 1 : 0;
        int digits = 0;
        boolean pointSeen = false;

        while (i < text.length()) {
            char c = text.charAt(i);
            if (c == 'e' || c == 'E') {
                break;
            }

            if (c == '.') {
                if (pointSeen) {
                    throw new IllegalArgumentException("two decimal points");
                }
                pointSeen = true;
            } else if (decimalDigit(c)) {
                if (++digits > MAX_DIGITS) {
                    throw new IllegalArgumentException("too many decimal digits");
                }
            } else {
                throw new IllegalArgumentException(
                        "invalid decimal character");
            }
            i++;
        }

        if (digits == 0) {
            throw new IllegalArgumentException(
                    "missing mantissa digits");
        }

        if (i < text.length()) {
            i++; // Bỏ qua E/e.
            if (i < text.length()
                    && (text.charAt(i) == '+'
                            || text.charAt(i) == '-')) {
                i++;
            }

            int exponentDigits = 0;
            int magnitude = 0;

            for (; i < text.length(); i++) {
                char c = text.charAt(i);
                if (!decimalDigit(c)) {
                    throw new IllegalArgumentException(
                            "invalid exponent character");
                }
                if (++exponentDigits > MAX_EXPONENT_DIGITS) {
                    throw new IllegalArgumentException(
                            "exponent text too long");
                }

                int digit = c - '0';
                if (magnitude > (MAX_ABS_EXPONENT - digit) / 10) {
                    throw new IllegalArgumentException(
                            "exponent too large");
                }
                magnitude = magnitude * 10 + digit;
            }

            if (exponentDigits == 0) {
                throw new IllegalArgumentException(
                        "missing exponent digits");
            }
        }

        BigDecimal value = new BigDecimal(text);
        // Cast sang long trước khi dùng abs để an toàn với int MIN_VALUE.
        if (Math.abs((long) value.scale()) > MAX_ABS_SCALE) {
            throw new IllegalArgumentException("scale too large");
        }
        if (plainLength(value) > MAX_PLAIN_CHARS) {
            throw new IllegalArgumentException(
                    "plain representation too long");
        }
        return value;
    }

    // Độ dài số ký tự toPlainString() dự kiến, không tạo chuỗi lớn.
    private static long plainLength(BigDecimal n) {
        long p = n.precision();
        long scale = n.scale();
        long length;

        if (n.signum() == 0 && scale <= 0) {
            length = 1;
        } else if (scale <= 0) {
            length = p - scale;
        } else if (p > scale) {
            length = p + 1;   // Bao gồm dấu thập phân.
        } else {
            length = scale + 2; // "0." và các chữ số thập phân.
        }

        return length + (n.signum() < 0 ? 1 : 0);
    }

    public static BigInteger shiftLeftBounded(
            BigInteger value, int bits) {
        if (bits < 0
                || (long) value.bitLength() + bits > MAX_RESULT_BITS) {
            throw new IllegalArgumentException(
                    "shift would exceed bit limit");
        }
        return value.shiftLeft(bits);
    }

    private static void expectRejected(
            String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": NOT REJECTED");
        } catch (IllegalArgumentException ok) {
            System.out.println(label + ": rejected");
        }
    }

    public static void main(String[] args) {
        BigInteger integer = parseInteger("12345678901234567890");
        BigDecimal decimal = parseDecimal("1.25E+2");

        System.out.println("integer digits: "
                + integer.toString().length());
        System.out.println("decimal plain: " + decimal.toPlainString());
        System.out.println("bounded shift: "
                + shiftLeftBounded(BigInteger.valueOf(3), 10));
        System.out.println("scientific plain length: "
                + plainLength(parseDecimal("1E+30")));

        expectRejected("too many digits",
                () -> parseInteger("123456789012345678901"));
        expectRejected("large exponent",
                () -> parseDecimal("1E+999"));
        expectRejected("large plain output",
                () -> parseDecimal("100.0E+30"));
        expectRejected("oversize shift",
                () -> shiftLeftBounded(BigInteger.ONE, 128));
    }
}
```

Biên dịch và chạy:

```bash
javac SafeBigNumbers.java
java SafeBigNumbers
```

Kết quả:

```text
integer digits: 20
decimal plain: 125
bounded shift: 3072
scientific plain length: 31
too many digits: rejected
large exponent: rejected
large plain output: rejected
oversize shift: rejected
```

### Đọc hiểu từng lớp kiểm tra

**`parseInteger`:** kiểm tra null/rỗng và tổng độ dài; chỉ cho phép một dấu ở đầu và tối đa 20 chữ số `0..9`, sau đó mới gọi `new BigInteger(text)`. Ký tự lạ hoặc dấu lặp bị từ chối. Các số 0 đầu vẫn **được đếm** vào hạn mức vì chúng vẫn làm dài đầu vào và gây chi phí parse.

**`parseDecimal`:** quét phần mantissa, đếm mọi chữ số và không chấp nhận hai dấu chấm. Với exponent, chương trình kiểm soát **cả độ dài lẫn giá trị** trước khi dựng `BigDecimal`. Phép kiểm tra `magnitude > (MAX_ABS_EXPONENT - digit) / 10` phát hiện vượt giới hạn trước phép nhân 10/cộng chữ số, tránh tự làm tràn biến `int` trong quá trình parse exponent. Chính sách này chấp nhận các dạng như `1.25E+2` và `.5` nhưng không nhận khoảng trắng, ký tự phân nhóm hàng nghìn hoặc biểu diễn số theo locale.

**Kiểm soát scale:** sau khi tạo giá trị đã được giới hạn textual input, kiểm tra `Math.abs((long) value.scale())`. Việc chuyển sang `long` trước `abs` tránh lỗi đặc biệt với `Integer.MIN_VALUE`. Đây là kiểm tra **bổ sung sau parse**, không thay thế giới hạn textual input/exponent trước constructor.

**`plainLength`:** chỉ ước tính độ dài chuỗi thập phân thuần, không thực hiện `toPlainString()`. Công thức dùng `precision()` và `scale()`; có một trường hợp riêng cho số 0 có scale không dương và một ký tự dấu khi số âm. Trong ví dụ, `1E+30` có độ dài plain 31 nên được phép; `100.0E+30` có plain dài 33 nên bị từ chối theo ngân sách 32.

**`shiftLeftBounded`:** dùng tổng `bitLength + bits` làm **cận trên bảo thủ** trước `shiftLeft`. Với miền nhập và chính sách này, kiểm tra chặn các yêu cầu có thể vượt 128 bit; đôi khi nó cũng từ chối một kết quả thực tế có thể nhỏ hơn cận, điều có thể chấp nhận trong chính sách an toàn tài nguyên. Với phép dịch phải, mũ lũy thừa, nhân/chia hoặc modPow, cần xây dựng giới hạn riêng trước mỗi phép toán.

**`expectRejected`:** minh họa các trường hợp bị từ chối bằng `IllegalArgumentException`; trong ứng dụng thực, chuyển các lỗi kiểm tra đó thành phản hồi validation có cấu trúc và **không trả dữ liệu đầu vào quá dài vào log/error response**.

Các hằng số trong chương trình chỉ phục vụ ví dụ. Một hệ thống kế toán, tính toán khoa học hay xử lý mật mã có ngân sách và đặc trưng dữ liệu rất khác nhau. Hãy đặt giới hạn theo yêu cầu của sản phẩm và tài nguyên triển khai.

## 5. Dự đoán kích thước đầu ra trước khi chuyển chuỗi

Rất dễ bỏ sót vấn đề đầu ra. Xét:

```java
BigDecimal value = new BigDecimal("1E+1000000");

String compact = value.toString();     // Dạng khoa học, ngắn.
// String huge = value.toPlainString(); // Có thể sinh > 1 triệu ký tự.
```

`BigDecimal.toString()` chọn dạng khoa học khi phù hợp với scale/adjusted exponent. `toPlainString()` **bắt buộc không dùng E** và có thể thêm vô số chữ số 0 khi scale rất âm hoặc rất dương. `toEngineeringString()` cũng có cách trình bày khác, nhưng không nên dùng như một cơ chế giới hạn kích thước tổng quát.

Một cách dự báo độ dài plain cho phần lớn các số khác 0:

- `scale <= 0`: số chữ số thường là `precision - scale`.
- `scale > 0` và `precision > scale`: cần `precision + 1` ký tự (bao gồm dấu chấm).
- `scale > 0` và `precision <= scale`: cần `scale + 2` ký tự, gồm `0.` và phần thập phân.
- Nếu âm, cộng một ký tự cho dấu trừ. Với số 0 có scale không dương, `toPlainString()` là `"0"`.

Các phép tính ước lượng cần dùng `long` hoặc phép toán kiểm tra tràn, không cộng/trừ `int` bừa bãi khi scale có thể nằm gần giới hạn kiểu `int`. Khi đã có một hạn mức nhỏ, **so sánh chiều dài dự kiến trước khi gọi phương thức tạo chuỗi**.

Ngoài `toPlainString()`, kiểm tra đường đi dữ liệu qua JSON serialization, ghi log, sinh báo cáo, CSV, HTML, các API nhận chuỗi, hoặc trường cơ sở dữ liệu. Một giá trị dưới dạng khoa học ngắn ở tầng nhận có thể trở thành đầu ra rất lớn sau một phép chuẩn hóa định dạng.

## 6. Giới hạn tài nguyên trước phép toán

Kể cả nếu hai toán hạng qua kiểm tra đầu vào, phép toán tiếp theo vẫn có thể tạo số vượt ngân sách:

| Phép toán | Rủi ro | Giới hạn nên có |
|---|---|---|
| `BigInteger.multiply` | Kích thước kết quả xấp xỉ tổng kích thước bit của toán hạng | Ước lượng cận bit kết quả; chặn giá trị vượt ngân sách |
| `BigInteger.shiftLeft` | `n` có thể rất lớn dù toán hạng ngắn | Giới hạn cả `n` và bit kết quả dự kiến |
| `BigInteger.pow` | Số chữ số kết quả tăng theo số mũ | Giới hạn số mũ và ngân sách bit/precision |
| `BigInteger.modPow` | Tốn thời gian với modulus/số mũ lớn | Giới hạn bitLength và số phép/độ trễ |
| `BigInteger.gcd`, chia/mod | Chi phí phụ thuộc kích thước toán hạng | Giới hạn bitLength đầu vào và quota xử lý |
| `BigDecimal.multiply` | Unscaled value và scale có thể tăng | Giới hạn precision/scale dự kiến và kết quả |
| `BigDecimal.divide` | Có thể có khai triển thập phân vô hạn hoặc sinh nhiều chữ số | Chỉ định precision/scale và `RoundingMode` theo nghiệp vụ |
| `BigDecimal.pow` | Precision, exponent, scale và chi phí trung gian có thể lớn | Giới hạn số mũ, precision, scale và chi phí |
| `toPlainString` | Chuỗi đầu ra có thể lớn dù unscaled value nhỏ | Tính trước độ dài plain, chặn trước khi tạo |

Ví dụ về dự đoán:

- Với phép nhân hai số nguyên có độ dài bit `a` và `b`, bitLength kết quả không vượt quá xấp xỉ `a + b`; dùng tổng này làm cận trên bảo thủ trước khi nhân.
- Với `shiftLeft(n)`, cộng `n` vào bitLength hiện có làm cận trên đơn giản; từ chối `n` âm hoặc lớn quá giới hạn.
- Với `pow(exponent)`, sản phẩm `bitLength × exponent` có thể quá lớn. Dùng kiểu rộng hoặc phép kiểm tra tràn trước khi ước lượng, đặc biệt khi exponent do người dùng kiểm soát.

`MathContext` giới hạn **precision của kết quả làm tròn** trong các API `BigDecimal` hỗ trợ, nhưng **không phải lá chắn tổng quát chống tiêu tốn bộ nhớ/CPU**. Một thuật toán có thể vẫn cần tạo intermediate lớn hoặc xử lý toán hạng khổng lồ trước khi làm tròn. `new MathContext(20)` không biến việc parse chuỗi hàng triệu ký tự hoặc tính toán lũy thừa lớn thành an toàn tài nguyên.

Cũng cần nhớ rằng một số phép chia `BigDecimal.divide(BigDecimal)` không có scale/rounding context có thể ném `ArithmeticException` nếu thương không biểu diễn hữu hạn; điều đó là một vấn đề **khác** với việc dùng quá nhiều tài nguyên. Hãy giới hạn đầu vào trước và chỉ định cách chia thích hợp.

## 7. Ngân sách ở cấp hệ thống, không chỉ trong một hàm parse

Một validator tốt không đủ nếu các tầng trước nó đã đọc toàn bộ request khổng lồ vào bộ nhớ. Hãy phân lớp:

1. **Cổng tiếp nhận dữ liệu:** giới hạn byte của HTTP request, body JSON, upload, message và kích thước batch; tránh dựng object lớn khi payload đã vượt hạn mức.
2. **Phân tích cú pháp:** quét input trong thời gian tuyến tính, hạn chế chiều dài, số chữ số, exponent và scale trước khi dựng đối tượng lớn; không dùng regex thiếu kiểm soát trên chuỗi tùy ý.
3. **Mô hình dữ liệu:** mô tả giới hạn nghiệp vụ theo trường, ví dụ số chữ số tối đa, scale hợp lệ, miền giá trị và cách xử lý dấu/số 0.
4. **Tính toán:** ước lượng độ phình của kết quả và số vòng lặp trước phép nhân, lũy thừa, shift, chuyển đổi định dạng; giới hạn tổng số tác vụ song song và thời lượng xử lý.
5. **Đầu ra và lưu trữ:** giới hạn chuỗi xuất, số dòng/trường, độ dài log, kích thước database column; không vô tình chuyển số khoa học ngắn thành plain dài.
6. **Khả năng phục hồi:** dùng timeout, quota theo request/người dùng, giới hạn concurrency/bộ nhớ, cơ chế từ chối sớm và đo lường tác vụ vượt hạn mức.

Không nên coi `try/catch (OutOfMemoryError)` là cơ chế kiểm soát đầu vào. Khi lỗi này xảy ra, JVM có thể đã ở trạng thái thiếu tài nguyên nghiêm trọng; phòng tránh bằng giới hạn trước khi cấp phát và kiểm soát tài nguyên ở mức quy trình/hạ tầng đáng tin cậy hơn.

Nếu thực sự cần hỗ trợ tính toán số cực lớn, hãy **thiết kế kiến trúc cho workload đó**: job bất đồng bộ có quota rõ ràng, bộ nhớ/CPU giới hạn, lưu kết quả theo định dạng phù hợp, có thể hủy/giới hạn tiến trình và theo dõi tài nguyên. Không nới tất cả giới hạn trong API đồng bộ dành cho request thông thường.

## 8. Các lỗi thiết kế thường gặp

### “Đã giới hạn số chữ số nên chắc chắn an toàn”

Giới hạn mantissa 20 chữ số vẫn có thể chấp nhận `1E+1000000000` nếu không kiểm soát exponent. Giá trị có thể biểu diễn gọn nhưng `toPlainString()` cực lớn. Ngược lại, `BigInteger.ONE.shiftLeft(100000000)` có đầu vào chỉ một bit mà kết quả rất lớn. Phải kiểm tra cả **mô tả số**, **phép toán** và **cách xuất**.

### “parse xong rồi gọi precision() và bitLength() kiểm tra”

Kiểm tra sau constructor có thể hữu ích nhưng đã quá muộn để chặn tài nguyên dành cho parse một chuỗi không giới hạn. Với dữ liệu không tin cậy, luôn đặt giới hạn thô và đếm chữ số **trước** khi tạo `BigInteger`/`BigDecimal`.

### “Precision thấp thì toPlainString() ngắn”

`new BigDecimal("1E+1000000")` có precision 1 nhưng chuỗi plain dài hơn một triệu ký tự. **Precision** mô tả số chữ số của unscaled value, còn **scale** quyết định vị trí dấu chấm và số lượng số 0 cần trình bày.

### “stripTrailingZeros() làm mọi thứ nhỏ lại”

`stripTrailingZeros()` có thể giảm số chữ số của unscaled value và thay đổi scale, đôi khi tạo scale âm, khiến `toString()` dùng dạng khoa học. Nó không phải giải pháp kiểm soát kích thước đầu ra; sau đó gọi `toPlainString()` vẫn có thể tạo chuỗi dài. Không dùng phương thức này như thay thế cho giới hạn tài nguyên hoặc chính sách precision/scale.

### “Dùng BigDecimal với MathContext nhỏ là đủ”

Một `MathContext` nhỏ ràng buộc precision của kết quả ở những phép toán có sử dụng nó; không chặn chuỗi nhập khổng lồ, exponent ngoài chính sách, số lần gọi phép toán, hoặc mọi bộ nhớ tạm. Giới hạn tài nguyên phải xuất hiện **trước** các bước có thể tốn nhiều tài nguyên.

### “Dùng double để giảm chi phí mà không ảnh hưởng dữ liệu”

`double` có miền và độ chính xác hữu hạn theo nhị phân. Chuyển số tài chính hoặc dữ liệu thập phân chính xác sang `double` có thể làm mất chữ số hoặc đổi giá trị. Nếu cần giới hạn dữ liệu `BigDecimal`, hãy **từ chối các giá trị ngoài chính sách** hoặc định nghĩa phép làm tròn tường minh, thay vì âm thầm đổi kiểu.

### “Chặn lỗi rồi log nguyên đầu vào”

Khi phản hồi hoặc ghi log in nguyên chuỗi có hàng triệu chữ số, chính bước báo lỗi lại gây áp lực bộ nhớ/I/O. Log chỉ thông tin an toàn như mã lỗi, tên field, độ dài đã giới hạn và request ID; tránh phản chiếu cả payload vào thông báo.

## 9. Định nghĩa chính sách theo miền nghiệp vụ

Không có một hạn mức đúng cho mọi ứng dụng:

- **Tiền tệ:** thường cần giới hạn precision, scale, miền giá trị, phép làm tròn và định dạng theo đồng tiền hoặc hợp đồng. Giá trị âm, dấu cộng, số 0 cuối và số mũ có thể được cho phép hoặc cấm theo đặc tả API.
- **Số lượng sản phẩm / bộ đếm:** nên giới hạn miền số nguyên (và không âm nếu nghiệp vụ yêu cầu); có thể chỉ cần `long` nếu miền cho phép. `BigInteger` chỉ hữu ích khi yêu cầu thật sự vượt miền kiểu nguyên thủy.
- **Tính toán khoa học:** có thể cần exponent lớn, độ chính xác cao và dạng khoa học; nên đặt ngân sách theo độ dài unscaled value, precision, scale, số thao tác và chi phí đầu ra.
- **Số học mật mã:** `BigInteger` có thể dùng để biểu diễn số lớn, nhưng việc xử lý bí mật cần xem xét thời gian thực thi, hạn mức, API bảo mật và các thuộc tính phụ kênh; không mặc định mọi phép toán BigInteger phù hợp cho xử lý bí mật.
- **API công cộng:** thêm quota theo người dùng, giới hạn kích thước request, timeout và phản hồi validation rõ ràng, vì đầu vào có thể không đáng tin.

Ví dụ một schema có thể quy định “tối đa 30 chữ số, scale 0–4, trị tuyệt đối dưới ngưỡng X, không nhận E”; schema khác có thể cho phép `E` nhưng giới hạn exponent và chuỗi plain. Khi triển khai, cần **diễn đạt giới hạn bằng điều kiện kiểm thử được**, không chỉ ghi chú chung “số không được quá lớn”.

## 10. Checklist kiểm thử

Kiểm thử không chỉ các giá trị hợp lệ thông thường mà cả biên tài nguyên:

- Chuỗi rỗng, chỉ dấu `+`/`-`, ký tự lạ, khoảng trắng, nhiều dấu chấm, exponent thiếu chữ số.
- Giá trị đúng bằng hạn mức và vượt hạn mức một ký tự/chữ số.
- Chuỗi dài toàn số 0, giá trị bằng 0 nhưng mantissa vẫn quá dài.
- Exponent có nhiều chữ số, mang dấu âm/dương, vượt hạn mức hoặc có thể gây tràn nếu cộng dồn sai.
- Scale dương rất lớn (`1E-1000000`) và scale âm rất lớn (`1E+1000000`).
- Đầu vào ngắn dẫn tới phép `pow` hoặc `shiftLeft` mở rộng ngoài ngân sách.
- `toString()` ngắn nhưng `toPlainString()` rất dài.
- Nhiều request/tác vụ song song cùng sử dụng ngân sách gần ngưỡng.
- Đầu ra báo lỗi/log không vô tình sao chép lại toàn bộ số lớn.

**Tự kiểm tra 1:** Vì sao giới hạn “tối đa 50 ký tự đầu vào” chưa đủ để bảo vệ `toPlainString()`? Vì dạng khoa học như `1E+1000000` rất ngắn nhưng tạo hàng triệu ký tự ở dạng thập phân đầy đủ.

**Tự kiểm tra 2:** Vì sao kiểm tra `BigInteger.bitLength()` sau `new BigInteger(text)` không thay thế việc giới hạn chuỗi? Vì đã phải nhận và parse chuỗi, có thể gây chi phí lớn trước khi kiểm tra.

**Tự kiểm tra 3:** `new BigDecimal("1E+30")` có precision 1; liệu có thể kết luận phép nhân và đầu ra đều rẻ? **Không.** Precision không chứa đủ thông tin về scale, định dạng hoặc chi phí của các phép toán tiếp theo.

**Ghi nhớ:** `BigInteger` và `BigDecimal` cho phép biểu diễn độ chính xác lớn, nhưng an toàn tài nguyên là trách nhiệm của ứng dụng. Hãy giới hạn **đầu vào trước parse**, **scale/exponent**, **độ lớn kết quả trước phép toán**, **độ dài chuỗi trước xuất** và **quota thực thi cấp hệ thống**.
