# Chọn BigInteger cho chuỗi số vượt giới hạn long trong Java

## 1. Khi nào cần BigInteger?

Nếu đầu vào là **chuỗi biểu diễn số nguyên thập phân** và giá trị có thể vượt giới hạn kiểu **long**, hãy dùng **java.math.BigInteger** khi cần giữ nguyên **giá trị số học chính xác**.

Miền của long là:

- **Long.MIN_VALUE = −9223372036854775808** (−2^63).
- **Long.MAX_VALUE = 9223372036854775807** (2^63−1).

Ví dụ chuỗi **"9223372036854775808"** chỉ lớn hơn Long.MAX_VALUE đúng 1 đơn vị nhưng đã không thể biểu diễn như số dương trong long. Chuỗi **"-9223372036854775809"** lại nhỏ hơn Long.MIN_VALUE đúng 1 đơn vị. Cả hai đều có thể được biểu diễn chính xác bằng BigInteger.

~~~java
import java.math.BigInteger;

BigInteger aboveMax = new BigInteger("9223372036854775808");
BigInteger belowMin = new BigInteger("-9223372036854775809");
~~~

Hai dòng là đoạn mã minh họa, dùng trong một phương thức/class Java. **BigInteger** biểu diễn số nguyên có dấu với độ chính xác tùy ý (arbitrary precision), chịu các giới hạn tài nguyên và triển khai, thay vì giới hạn ở 64 bit.

**Điểm quyết định không nằm ở độ dài chuỗi đơn thuần**, mà ở **miền giá trị cần hỗ trợ** và **cách sử dụng dữ liệu sau đó**. Một chuỗi dài 30 chữ số bắt đầu bằng nhiều số 0 vẫn có thể là số nhỏ; ngược lại, số dương 19 chữ số đã có thể vượt Long.MAX_VALUE.

## 2. Phân biệt ba bài toán trước khi chọn kiểu

| Tình huống | Cách biểu diễn thường phù hợp | Lý do |
| --- | --- | --- |
| Số nguyên luôn nằm trong miền signed 64 bit | **long/Long** | Gọn, nhanh, có phép toán nguyên thủy |
| Số nguyên có thể vượt signed long và cần tính toán chính xác | **BigInteger** | Không làm tràn miền long theo phép toán thông thường |
| Mã định danh chỉ chứa chữ số, có thể có số 0 đầu, không dùng để tính | **String** | Giữ nguyên toàn bộ ký tự, kể cả số 0 đầu và định dạng |
| Số có phần thập phân cần độ chính xác thập phân | **BigDecimal** | BigInteger chỉ biểu diễn **số nguyên** |
| Chuỗi số không dấu 64 bit nhưng cần giá trị dương đúng đến 2^64−1 | **BigInteger** | long vẫn dùng bit dấu và không chứa được toàn miền dưới dạng số dương |
| Dữ liệu chỉ cần biểu diễn mẫu bit unsigned 64 bit và API được thiết kế cho nó | **long** cùng các API unsigned | Phải thống nhất quy ước unsigned, không coi long là số dương |

Nếu đây là số tài khoản, số điện thoại, mã bưu chính hoặc ID **không có phép toán số học**, giữ dạng String thường đúng hơn. Chuyển **"000123"** sang BigInteger rồi in lại sẽ nhận **"123"**: giá trị số không đổi, nhưng định danh có thể đã sai.

Nếu bài toán thực sự là cộng, trừ, nhân, chia, kiểm tra nguyên tố, lũy thừa nguyên hoặc xử lý số nguyên rất lớn, BigInteger là lựa chọn trực tiếp.

## 3. Vì sao Long.parseLong thất bại và không nên ép số qua double?

~~~java
long maximum = Long.parseLong("9223372036854775807"); // Hợp lệ

// Khi thực thi sẽ ném NumberFormatException:
// long tooLarge = Long.parseLong("9223372036854775808");
~~~

**Long.parseLong** ném **NumberFormatException** khi chuỗi không đúng cú pháp *hoặc* khi giá trị vượt phạm vi long. Nếu cần phân biệt lỗi cú pháp với vượt miền, hãy xác thực chuỗi theo quy ước đầu vào rồi so sánh giá trị BigInteger với hai biên long.

Không chuyển qua **double** để né giới hạn long: double có thể biểu diễn số rất lớn về *độ lớn* nhưng không thể biểu diễn chính xác mọi số nguyên khi độ lớn tăng. Số nguyên liền kề có thể làm tròn thành cùng một double, vì significand double chỉ có 53 bit chính xác.

~~~java
double a = 9007199254740992.0; // 2^53
double b = 9007199254740993.0; // làm tròn về cùng double như a
boolean equal = (a == b);       // true
~~~

Nếu chuỗi đã đi qua hệ thống ngoài Java, ví dụ JSON consumer dùng JavaScript Number, giá trị có thể đã mất độ chính xác **trước** khi vào Java. Đối với số lớn cần chính xác xuyên hệ thống, truyền chuỗi thập phân hoặc dùng kiểu số lớn được hai phía thỏa thuận.

## 4. Tạo BigInteger trực tiếp từ String

Thêm import:

~~~java
import java.math.BigInteger;
~~~

Constructor phổ biến nhất là **new BigInteger(String val)**, giải mã giá trị nguyên thập phân có dấu:

~~~java
BigInteger zero = new BigInteger("0");
BigInteger positive = new BigInteger("+123456789012345678901234567890");
BigInteger negative = new BigInteger("-123456789012345678901234567890");
BigInteger withZeros = new BigInteger("00000099"); // giá trị số 99
~~~

Chuỗi đầu vào có thể có dấu **+** hoặc **−** ở đầu; dấu không được đứng riêng. Constructor sẽ từ chối cú pháp không hợp lệ bằng NumberFormatException.

Ví dụ các chuỗi **không nên đưa thẳng vào constructor thập phân**:

| Chuỗi | Vấn đề |
| --- | --- |
| **""** | Không có chữ số |
| **"+"**, **"-"** | Chỉ có dấu |
| **"12.0"** | Có phần thập phân, không phải số nguyên |
| **"1_000"** | Dấu gạch dưới chỉ là cú pháp literal trong mã nguồn Java, không phải cú pháp thập phân của chuỗi |
| **" 123 "** | Có khoảng trắng ở đầu/cuối; constructor không tự trim |
| **"0xFF"** | Prefix 0x không tự được nhận diện bởi constructor thập phân |

Nếu nghiệp vụ cho phép khoảng trắng ngoài chuỗi, có thể gọi **strip()** trước khi parse. Nhưng phải quyết định quy tắc này ở ranh giới nhập liệu; không tự động xóa ký tự khi chúng có ý nghĩa.

### Chọn cơ số với constructor hai tham số

**new BigInteger(String val, int radix)** cho phép đọc cơ số từ **Character.MIN_RADIX = 2** tới **Character.MAX_RADIX = 36**:

~~~java
BigInteger binary = new BigInteger("101010", 2); // 42
BigInteger hex = new BigInteger("FF", 16);        // 255
BigInteger negativeHex = new BigInteger("-FF", 16); // -255
~~~

Khi dùng radix 16, truyền **"FF"**, không truyền **"0xFF"** vào constructor rồi mong nó tự loại bỏ prefix. Nếu định dạng đầu vào quy định prefix **0x**, hãy xác thực và loại bỏ đúng prefix theo giao thức trước khi gọi constructor.

**BigInteger.toString()** cho dạng thập phân chuẩn hóa; **toString(16)** cho chuỗi hexadecimal (mặc định chữ thường, không có prefix "0x"). Giá trị âm có dấu trừ:

~~~java
BigInteger value = new BigInteger("9223372036854775808");
String hex = value.toString(16);   // "8000000000000000"
BigInteger parsedBack = new BigInteger(hex, 16);
boolean same = parsedBack.equals(value); // true
~~~

## 5. Kiểm tra đầu vào trước khi parse số quá lớn

Constructor BigInteger báo lỗi cú pháp, nhưng đối với đầu vào không tin cậy, ứng dụng thường cần quy định **giới hạn độ dài** và **bộ chữ số được chấp nhận** để ngăn tiêu thụ tài nguyên quá mức.

Ví dụ, một hợp đồng chỉ chấp nhận **chữ số ASCII 0..9**, một dấu tùy chọn ở đầu và tối đa N chữ số. Hàm sau xác thực theo đúng hợp đồng đó:

~~~java
static BigInteger parseDecimal(String text, int maxDigits) {
    if (text == null || maxDigits < 1) {
        throw new IllegalArgumentException("Invalid input or limit");
    }

    int start = text.startsWith("+") || text.startsWith("-") ? 1 : 0;
    int count = text.length() - start;

    if (count < 1 || count > maxDigits) {
        throw new IllegalArgumentException("Invalid digit count");
    }

    for (int i = start; i < text.length(); i++) {
        char digit = text.charAt(i);
        if (digit < '0' || digit > '9') {
            throw new IllegalArgumentException("Expected ASCII decimal digits");
        }
    }

    return new BigInteger(text);
}
~~~

Đây là **phương thức thành viên đặt bên trong class**, cần import java.math.BigInteger. Hàm sẽ:

1. Từ chối null hoặc maxDigits không hợp lệ.
2. Cho phép một dấu **+/-** tùy chọn, không tính vào hạn mức chữ số.
3. Từ chối chuỗi không có chữ số, quá dài hoặc chứa ký tự khác ASCII 0..9.
4. Chỉ tạo BigInteger khi cú pháp đã đạt điều kiện.

Hàm này có chủ đích **không nhận khoảng trắng, dấu phân nhóm, dấu gạch dưới, chữ số Unicode ngoài ASCII, exponent notation**. Nếu sản phẩm cần các định dạng đó, hãy định nghĩa parser tương ứng thay vì lặng lẽ chấp nhận.

Hạn mức **maxDigits** không phải hằng cố định cho mọi ứng dụng: đặt theo hợp đồng API và sức chịu tải. Một số gồm hàng triệu chữ số vừa tốn chi phí parse/lưu, vừa có thể khiến các phép nhân hoặc lũy thừa về sau tốn CPU/bộ nhớ lớn. Giới hạn tài nguyên vẫn cần thiết dù BigInteger không bị giới hạn 64 bit.

## 6. So sánh một BigInteger có nằm trong miền long không

Không dùng **longValue()** để kiểm tra liệu số có vừa long hay không: phương thức đó có thể **cắt bỏ bit cao** mà không báo lỗi.

Dùng **compareTo** với hai đầu miền:

~~~java
static final BigInteger LONG_MIN = BigInteger.valueOf(Long.MIN_VALUE);
static final BigInteger LONG_MAX = BigInteger.valueOf(Long.MAX_VALUE);

static boolean fitsLong(BigInteger value) {
    return value.compareTo(LONG_MIN) >= 0
            && value.compareTo(LONG_MAX) <= 0;
}
~~~

Đây là các trường/phương thức đặt trong class. **BigInteger.compareTo** trả về số âm, 0 hoặc số dương tùy quan hệ lớn/nhỏ/bằng; không so sánh BigInteger bằng toán tử **<** hay **>**.

Nếu chắc chắn giá trị nằm trong miền long, chuyển chính xác bằng **longValueExact()**:

~~~java
BigInteger ok = new BigInteger("1234567890123");
long n = ok.longValueExact(); // 1234567890123L
~~~

Nếu vượt miền, **longValueExact()** ném **ArithmeticException** thay vì tạo kết quả sai. Các phương thức **intValueExact()**, **shortValueExact()** và **byteValueExact()** cung cấp hành vi tương tự cho miền nhỏ hơn.

### Tại sao longValue() có thể nguy hiểm?

~~~java
BigInteger above = new BigInteger("9223372036854775808");
long truncated = above.longValue(); // -9223372036854775808
// above.longValueExact() -> ArithmeticException
~~~

**9223372036854775808 = 2^63**. Khi chuyển theo **longValue()**, 64 bit thấp được diễn giải là một long có dấu, trở thành **Long.MIN_VALUE**. Dữ liệu bị đổi dấu nhưng không có exception.

Nguyên tắc thực hành: dùng **longValueExact()** tại ranh giới API cần long, và chỉ dùng **longValue()** khi chủ động muốn lấy các bit thấp theo ngữ nghĩa được tài liệu mô tả.

## 7. Thực hiện phép toán chính xác với BigInteger

Khác kiểu nguyên thủy, BigInteger là **đối tượng bất biến** (immutable). Mỗi phép toán tạo/trả đối tượng kết quả; không cập nhật giá trị toán học của đối tượng cũ.

| Bài toán | API BigInteger |
| --- | --- |
| Cộng, trừ | **add**, **subtract** |
| Nhân | **multiply** |
| Chia nguyên | **divide** |
| Số dư theo phép chia | **remainder** |
| Thương và dư cùng lúc | **divideAndRemainder** |
| So sánh | **compareTo**, **equals** |
| Trị tuyệt đối, đổi dấu | **abs**, **negate** |
| Lũy thừa nguyên không âm | **pow(int exponent)** |
| Dịch bit | **shiftLeft**, **shiftRight** |
| Kiểm tra số bit | **bitLength**, **testBit** |

Ví dụ:

~~~java
BigInteger a = new BigInteger("9223372036854775808");
BigInteger b = a.add(BigInteger.TWO);           // 9223372036854775810
BigInteger product = a.multiply(BigInteger.valueOf(3));
// 27670116110564327424

BigInteger[] result = a.divideAndRemainder(BigInteger.valueOf(10));
// result[0] = 922337203685477580, result[1] = 8
~~~

Các hằng **BigInteger.ZERO**, **ONE**, **TEN** dùng được trong Java 17; **BigInteger.TWO** cũng có từ Java 9. Tránh viết **a + b** khi a, b là BigInteger vì không có operator overloading cho dấu cộng trên đối tượng.

**BigInteger.divide** là chia nguyên, làm tròn thương về 0. Nếu cần số thập phân của phép chia, hãy sử dụng **BigDecimal** hoặc định dạng phân số theo hợp đồng. Với số âm, **remainder** và **mod** không phải luôn thay thế được nhau: **mod** yêu cầu modulus dương và trả giá trị không âm.

## 8. Chuỗi unsigned 64 bit: hai miền khác nhau

Miền số nguyên unsigned 64 bit là **0 .. 18446744073709551615** (2^64−1), lớn hơn miền long dương tối đa.

~~~java
String digits = "18446744073709551615";
BigInteger unsignedMax = new BigInteger(digits); // dương, chính xác
long bits = Long.parseUnsignedLong(digits);      // -1 theo long có dấu
String recovered = Long.toUnsignedString(bits);  // "18446744073709551615"
~~~

**Long.parseUnsignedLong** phù hợp khi cần lưu **mẫu bit 64 bit** và dùng các API **compareUnsigned**, **divideUnsigned**, **remainderUnsigned**, **toUnsignedString** đúng quy ước. Nếu nghiệp vụ cần so sánh, cộng/trừ/tính toán một **số nguyên dương không dấu** với những giá trị có thể vượt 2^64−1, BigInteger thường trực tiếp và ít nhầm lẫn hơn.

Đừng lấy **Long.parseUnsignedLong** rồi so sánh bằng toán tử **>** thông thường: giá trị long bên trong có thể âm do bit dấu. Phải giữ nhất quán signed-vs-unsigned.

## 9. Khi dữ liệu đến từ API, JSON, CSV và database

**CSV/text:** nhập như String, xác thực cú pháp/độ dài, parse BigInteger. Khi xuất, gọi **toString()**. Nếu cần giữ zero đầu hoặc cách viết nguyên gốc, lưu thêm **chuỗi gốc**, vì BigInteger chuẩn hóa biểu diễn số.

**JSON:** theo chuẩn JSON, token số không đảm bảo mọi consumer lưu chính xác số nguyên cực lớn. Nhiều ứng dụng JavaScript dùng **Number** và chỉ biểu diễn chính xác các số nguyên trong miền an toàn **±(2^53−1)**. Nên có hợp đồng truyền số lớn dưới dạng **chuỗi**, hoặc dùng cơ chế parser/BigInt phù hợp được thống nhất. Không mặc nhiên gửi BigInteger như JSON number rồi cho rằng mọi client sẽ đọc chính xác.

**Database:** chọn kiểu cột hỗ trợ miền dữ liệu và thư viện ánh xạ tương ứng, như một kiểu **DECIMAL/NUMERIC** với precision đủ lớn nếu hệ quản trị hỗ trợ. Không giả sử kiểu BIGINT SQL hỗ trợ BigInteger không giới hạn, vì nhiều hệ quản trị dùng BIGINT 64 bit. Kiểm tra precision, scale, overflow/truncation và driver theo cơ sở dữ liệu thực tế.

**Message queue/gRPC:** cần có định dạng giao tiếp cụ thể. Một trường int64 cố định không thể biểu diễn số dương trên 2^63−1 theo signed semantics. Có thể dùng chuỗi decimal hoặc biểu diễn byte có quy ước rõ nếu hệ thống yêu cầu.

## 10. Chương trình đầy đủ Java 17+ và kết quả thực tế

Tạo tệp **BigIntegerTextDemo.java**:

~~~java
import java.math.BigInteger;

public class BigIntegerTextDemo {
    static final BigInteger LONG_MIN = BigInteger.valueOf(Long.MIN_VALUE);
    static final BigInteger LONG_MAX = BigInteger.valueOf(Long.MAX_VALUE);

    static BigInteger parseDecimal(String text, int maxDigits) {
        if (text == null || maxDigits < 1) {
            throw new IllegalArgumentException("Invalid input or limit");
        }

        int start = text.startsWith("+") || text.startsWith("-") ? 1 : 0;
        int count = text.length() - start;

        if (count < 1 || count > maxDigits) {
            throw new IllegalArgumentException("Invalid digit count");
        }

        for (int i = start; i < text.length(); i++) {
            char digit = text.charAt(i);
            if (digit < '0' || digit > '9') {
                throw new IllegalArgumentException("Expected ASCII decimal digits");
            }
        }
        return new BigInteger(text);
    }

    static boolean fitsLong(BigInteger value) {
        return value.compareTo(LONG_MIN) >= 0
                && value.compareTo(LONG_MAX) <= 0;
    }

    public static void main(String[] args) {
        BigInteger above = parseDecimal("9223372036854775808", 24);
        BigInteger below = parseDecimal("-9223372036854775809", 24);
        BigInteger unsignedMax =
                parseDecimal("18446744073709551615", 24);

        System.out.println("Long.MAX_VALUE: " + Long.MAX_VALUE);
        System.out.println("First above long: " + above);
        System.out.println("Above fits long: " + fitsLong(above));
        System.out.println("Below fits long: " + fitsLong(below));
        System.out.println("Unsigned 64 max: " + unsignedMax);
        System.out.println("Unsigned max fits signed long: "
                + fitsLong(unsignedMax));

        System.out.println("Leading zeros: "
                + parseDecimal("+0009223372036854775808", 24));
        System.out.println("Above + 2: " + above.add(BigInteger.TWO));
        System.out.println("Above * 3: "
                + above.multiply(BigInteger.valueOf(3)));

        System.out.println("Above in hex: " + above.toString(16));
        System.out.println("Round trip: "
                + new BigInteger(above.toString(16), 16).equals(above));
        System.out.println("Truncated longValue: " + above.longValue());

        try {
            System.out.println(above.longValueExact());
        } catch (ArithmeticException e) {
            System.out.println("longValueExact: out of range");
        }

        try {
            System.out.println(Long.parseLong("9223372036854775808"));
        } catch (NumberFormatException e) {
            System.out.println("parseLong: out of range");
        }

        try {
            parseDecimal("1_000", 24);
        } catch (IllegalArgumentException e) {
            System.out.println("strict decimal: invalid syntax");
        }

        System.out.println("Matches MAX + ONE: "
                + above.equals(LONG_MAX.add(BigInteger.ONE)));
        System.out.println("Unsigned parse as long: "
                + Long.parseUnsignedLong("18446744073709551615"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 BigIntegerTextDemo.java
java BigIntegerTextDemo
~~~

Kết quả stdout:

~~~text
Long.MAX_VALUE: 9223372036854775807
First above long: 9223372036854775808
Above fits long: false
Below fits long: false
Unsigned 64 max: 18446744073709551615
Unsigned max fits signed long: false
Leading zeros: 9223372036854775808
Above + 2: 9223372036854775810
Above * 3: 27670116110564327424
Above in hex: 8000000000000000
Round trip: true
Truncated longValue: -9223372036854775808
longValueExact: out of range
parseLong: out of range
strict decimal: invalid syntax
Matches MAX + ONE: true
Unsigned parse as long: -1
~~~

**Ý nghĩa chính:**

- Số dương **2^63** không vừa signed long nhưng BigInteger giữ nguyên.
- Khi chuyển ngược về long, **longValue()** lấy 64 bit thấp và có thể thành số âm; **longValueExact()** sẽ báo lỗi.
- Số nguyên **2^64−1** có thể lưu dưới dạng BigInteger dương, nhưng Long.parseUnsignedLong trả về mẫu bit mà long signed đọc là −1.
- Chuỗi có dấu cộng và zero đầu được parse thành **giá trị số chuẩn hóa**, không giữ hình thức chuỗi.
- Các phép toán add/multiply vẫn chính xác trong miền minh họa.

## 11. Hiệu năng và an toàn tài nguyên

BigInteger hỗ trợ số nguyên rất lớn, nhưng **không miễn phí**:

- Parse chuỗi dài tạo các cấu trúc dữ liệu lớn và cần thời gian CPU.
- Phép nhân, chia, lũy thừa và modular exponentiation có chi phí tăng theo độ dài số.
- Nếu một yêu cầu mạng có thể gửi chuỗi hàng triệu chữ số, cần giới hạn **số chữ số và tài nguyên** trước khi tạo hoặc tính trên BigInteger.
- Nếu mọi giá trị được chứng minh nằm trong long, primitive long thường đơn giản và hiệu quả hơn.
- BigInteger là immutable và thread-safe theo cách dùng giá trị bất biến, nhưng vẫn phải quản lý cập nhật tham chiếu chia sẻ đúng quy tắc đồng thời.

Không tối ưu bằng cách **cắt chuỗi 19 chữ số đầu rồi parse long**: cách đó làm mất dữ liệu và có thể xử lý sai dấu, zero đầu, hoặc số có nhiều chữ số. Nếu cần chính xác, parse đúng giá trị hoặc từ chối với thông báo có căn cứ.

## 12. Những lỗi phổ biến

| Sai lầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Dùng Long.parseLong rồi nghĩ nó tự mở rộng khi tràn | NumberFormatException | Parse BigInteger nếu miền có thể vượt long |
| Dùng double để chứa số nguyên cực lớn | Có thể mất các chữ số thấp | Dùng BigInteger khi yêu cầu chính xác nguyên |
| Dùng BigInteger.longValue() để kiểm tra có vừa long | Cắt bit cao, có thể đổi dấu | compareTo với biên hoặc longValueExact() |
| Cho rằng độ dài > 19 chữ số luôn vượt long | Zero đầu có thể làm giá trị nhỏ | Parse/chuẩn hóa rồi so sánh miền |
| Cho rằng 19 chữ số luôn vừa long | 9223372036854775808 đã vượt Long.MAX_VALUE | So sánh với hai biên chính xác |
| Cho rằng parseUnsignedLong cho long dương vượt MAX_VALUE | Kết quả là mẫu bit long có dấu | Dùng API unsigned nhất quán hoặc BigInteger |
| Dùng toán tử + cho hai BigInteger | Không biên dịch | Dùng a.add(b) |
| Không gán giá trị trả về từ phép cộng | Đối tượng cũ không đổi | Gán result = a.add(b) |
| Cho rằng BigInteger giữ zero đầu | toString chuẩn hóa dạng số | Giữ bản String gốc nếu cần |
| Parse số khổng lồ không giới hạn từ client | Rủi ro tốn CPU và bộ nhớ | Giới hạn độ dài và phạm vi xử lý |
| Dùng BigInteger cho số thập phân có dấu phẩy | NumberFormatException | Xem xét BigDecimal |
| Coi SQL BIGINT đồng nghĩa BigInteger | Có thể bị giới hạn 64 bit | Kiểm tra kiểu cột và precision |

## 13. Bài tập tự kiểm tra

**Bài 1.** Vì sao **"9223372036854775808"** không parse được bằng Long.parseLong nhưng parse được bằng BigInteger?

*Đáp án:* Giá trị bằng **2^63**, vượt cực đại signed long **2^63−1**; BigInteger không bị giới hạn ở 64 bit.

**Bài 2.** Nếu chuyển BigInteger biểu diễn **2^63** bằng longValue(), kết quả có dấu là bao nhiêu?

*Đáp án:* **−9223372036854775808** do 64 bit thấp được diễn giải theo long có dấu. **longValueExact()** phải ném ArithmeticException.

**Bài 3.** Chuỗi **"00000000000000000000000042"** có nhất thiết lớn hơn Long.MAX_VALUE không?

*Đáp án:* Không; giá trị nguyên là 42. Số lượng chữ số nguyên bản không đủ để xác định miền khi có zero đầu.

**Bài 4.** Tại sao một mã định danh **"00042"** có thể không nên chuyển sang BigInteger?

*Đáp án:* Nếu các số 0 đầu là một phần định danh, BigInteger sẽ chuẩn hóa thành "42" và làm mất dạng gốc.

**Bài 5.** Nếu ứng dụng dùng unsigned 64 bit và nhận chuỗi **"18446744073709551615"**, nên chọn cách nào để tính toán tiếp trên một **giá trị dương**?

*Đáp án:* BigInteger biểu diễn số dương đó trực tiếp. Nếu lưu long làm mẫu bit, phải dùng nhất quán API unsigned; toán tử signed có thể cho kết quả âm.

**Bài 6.** Làm sao trả về long khi một BigInteger vừa miền, đồng thời từ chối khi không vừa?

*Đáp án:* Dùng **longValueExact()**, có thể kiểm tra trước với **compareTo(Long.MIN_VALUE/MAX_VALUE)** đã chuyển thành BigInteger.

**Bài 7.** Vì sao phải giới hạn số chữ số đầu vào dù BigInteger có độ chính xác tùy ý?

*Đáp án:* Parse, lưu trữ và tính toán số cực lớn vẫn có chi phí CPU/bộ nhớ; giới hạn ngăn việc dùng tài nguyên không kiểm soát.

## 14. Tài liệu chính thức

- [BigInteger Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): constructor theo String/radix, toString, compareTo, phép toán bất biến và longValueExact.
- [Long Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html): giới hạn signed 64 bit, parseLong, parseUnsignedLong, toUnsignedString.
- [BigDecimal Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): khi dữ liệu có phần thập phân.
- [Java Language Specification SE 17 — Integer Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.1): miền và biểu diễn primitive int/long.
