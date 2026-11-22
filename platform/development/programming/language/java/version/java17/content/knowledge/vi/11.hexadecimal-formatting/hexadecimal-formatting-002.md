# Tạo HexFormat mặc định, chữ hoa hoặc chữ thường trong Java 17

Java 17 bổ sung lớp **`java.util.HexFormat`** để chuyển mảng byte thành chuỗi hệ mười sáu (hexadecimal) và parse chuỗi hex trở lại byte. API này hữu ích khi hiển thị dữ liệu nhị phân trong log, kiểm tra payload, đọc dump dữ liệu, biểu diễn hash hoặc trao đổi dữ liệu với hệ thống bên ngoài.

`HexFormat` cho phép cấu hình chữ số **chữ thường hoặc chữ hoa**, dấu phân cách, tiền tố và hậu tố. Mặc định, `HexFormat.of()` sử dụng chữ số hex **chữ thường**, không có delimiter, prefix hoặc suffix. Muốn chữ hoa, dùng `withUpperCase()`; muốn chữ thường tường minh, dùng `withLowerCase()`.

Đây là API chính thức từ Java 17, không phải preview và không cần thư viện ngoài.

## 1. Hệ thập lục phân và dữ liệu byte

Hệ thập lục phân sử dụng 16 ký hiệu:

~~~text
0 1 2 3 4 5 6 7 8 9 a b c d e f
~~~

Một chữ số hex biểu diễn 4 bit (một nibble). Hai chữ số hex biểu diễn 8 bit, tương ứng một byte.

| Byte (hex) | Nhị phân | Giá trị byte có dấu trong Java |
| --- | --- | ---: |
| `00` | `00000000` | 0 |
| `0A` | `00001010` | 10 |
| `7F` | `01111111` | 127 |
| `80` | `10000000` | -128 |
| `FF` | `11111111` | -1 |

Java định nghĩa `byte` là số nguyên có dấu 8 bit, trong khoảng -128 đến 127. Khi hiển thị dữ liệu byte theo hex, ta muốn nhìn toàn bộ **mẫu bit 8 bit**. Vì vậy byte có giá trị Java là -1 sẽ được định dạng thành `ff`, không phải chuỗi biểu diễn dấu âm.

~~~java
byte[] data = {
        0x00,
        0x0A,
        0x7F,
        (byte) 0x80,
        (byte) 0xFF
};
~~~

Mảng trên có 5 byte. Mỗi byte cần hai chữ số hex để biểu diễn đầy đủ mẫu bit.

## 2. Tạo HexFormat mặc định

Import lớp:

~~~java
import java.util.HexFormat;
~~~

Tạo formatter mặc định và định dạng mảng:

~~~java
import java.util.HexFormat;

public class HexDefaultDemo {
    public static void main(String[] args) {
        byte[] data = {
                0x00, 0x0A, 0x7F, (byte) 0x80, (byte) 0xFF
        };

        HexFormat hex = HexFormat.of();

        String result = hex.formatHex(data);
        System.out.println(result);
    }
}
~~~

Kết quả:

~~~text
000a7f80ff
~~~

Đặc điểm của `HexFormat.of()`:

- Dùng chữ số `a` đến `f` ở dạng **chữ thường**.
- Không thêm dấu phân cách giữa các byte.
- Không thêm tiền tố như `0x`.
- Không thêm hậu tố.
- Mỗi byte được biểu diễn bằng đúng hai chữ số hex.

Với mảng có `n` byte, chuỗi hex mặc định có độ dài `2n` ký tự. Ví dụ mảng 5 byte tạo chuỗi 10 ký tự.

`HexFormat` là đối tượng cấu hình bất biến và an toàn khi chia sẻ giữa các thread. Có thể tạo một instance rồi tái sử dụng ở nhiều phương thức thay vì tạo formatter mới cho mỗi lần chuyển đổi.

## 3. Tạo HexFormat chữ hoa

Để dùng các chữ số `A` đến `F`, gọi `withUpperCase()`:

~~~java
import java.util.HexFormat;

public class HexUpperCaseDemo {
    public static void main(String[] args) {
        byte[] data = {
                0x00, 0x0A, 0x7F, (byte) 0x80, (byte) 0xFF
        };

        HexFormat hex = HexFormat.of().withUpperCase();

        System.out.println(hex.formatHex(data));
    }
}
~~~

Kết quả:

~~~text
000A7F80FF
~~~

`withUpperCase()` trả về một `HexFormat` có cấu hình chữ hoa. Vì `HexFormat` bất biến, lời gọi này không sửa formatter ban đầu; có thể giữ hai cấu hình riêng:

~~~java
HexFormat lower = HexFormat.of();
HexFormat upper = lower.withUpperCase();

byte[] data = {(byte) 0xAF};

System.out.println(lower.formatHex(data)); // af
System.out.println(upper.formatHex(data)); // AF
~~~

Đây là cách hữu ích khi cùng một dữ liệu cần hiển thị theo hai quy ước khác nhau, chẳng hạn log ứng dụng dùng chữ thường trong khi tài liệu kỹ thuật hoặc giao thức yêu cầu chữ hoa.

## 4. Tạo HexFormat chữ thường tường minh

Mặc định đã là chữ thường. Tuy nhiên, API cũng có `withLowerCase()` để thể hiện rõ chủ đích:

~~~java
HexFormat hex = HexFormat.of().withLowerCase();
~~~

Ví dụ:

~~~java
byte[] data = {(byte) 0xAB, (byte) 0xCD, (byte) 0xEF};

String lower = HexFormat.of()
        .withLowerCase()
        .formatHex(data);

String upper = HexFormat.of()
        .withUpperCase()
        .formatHex(data);

System.out.println(lower); // abcdef
System.out.println(upper); // ABCDEF
~~~

Có thể dùng `withLowerCase()` khi formatter được tạo từ một cấu hình khác và muốn chuẩn hóa chữ số. Nếu formatter vốn là `HexFormat.of()`, gọi thêm `withLowerCase()` không làm thay đổi kết quả.

| Cách tạo | Chữ số hex | Ví dụ với byte `0xAF` |
| --- | --- | --- |
| `HexFormat.of()` | Chữ thường mặc định | `af` |
| `HexFormat.of().withLowerCase()` | Chữ thường | `af` |
| `HexFormat.of().withUpperCase()` | Chữ hoa | `AF` |

## 5. Tạo formatter có dấu phân cách

Mặc định, các byte được nối liền nhau. Khi cần dễ đọc, có thể thêm delimiter bằng `withDelimiter(...)` hoặc factory `ofDelimiter(...)`.

### 5.1. Dùng dấu hai chấm

~~~java
byte[] data = {(byte) 0x0A, (byte) 0xAF, (byte) 0xFF};

HexFormat hex = HexFormat.ofDelimiter(":");
System.out.println(hex.formatHex(data));
~~~

Kết quả:

~~~text
0a:af:ff
~~~

### 5.2. Dùng khoảng trắng hoặc dấu gạch ngang

~~~java
HexFormat spaced = HexFormat.ofDelimiter(" ");
HexFormat dashed = HexFormat.ofDelimiter("-");

System.out.println(spaced.formatHex(data)); // 0a af ff
System.out.println(dashed.formatHex(data)); // 0a-af-ff
~~~

Delimiter được chèn **giữa các byte**, không chèn ở đầu hoặc cuối chuỗi.

### 5.3. Kết hợp delimiter và chữ hoa

~~~java
HexFormat hex = HexFormat.ofDelimiter(":")
        .withUpperCase();

System.out.println(hex.formatHex(data));
~~~

Kết quả:

~~~text
0A:AF:FF
~~~

`ofDelimiter(":")` là cách tạo formatter với delimiter ngay từ đầu. Cách tương đương là `HexFormat.of().withDelimiter(":")`.

### 5.4. Delimiter có thể là chuỗi nhiều ký tự

~~~java
HexFormat hex = HexFormat.ofDelimiter(" | ")
        .withUpperCase();

System.out.println(hex.formatHex(data));
~~~

Kết quả:

~~~text
0A | AF | FF
~~~

Nên chọn delimiter dễ đọc và phù hợp định dạng mà hệ thống nhận dữ liệu mong đợi. Nếu cần parse lại, hãy dùng chính formatter có cấu hình tương ứng.

## 6. Thêm prefix và suffix

`HexFormat` cho phép thêm tiền tố và hậu tố cho **từng byte** bằng `withPrefix(...)` và `withSuffix(...)`.

~~~java
byte[] data = {(byte) 0x0A, (byte) 0xAF, (byte) 0xFF};

HexFormat hex = HexFormat.ofDelimiter(" ")
        .withPrefix("0x")
        .withUpperCase();

System.out.println(hex.formatHex(data));
~~~

Kết quả:

~~~text
0x0A 0xAF 0xFF
~~~

Prefix `0x` được thêm trước mỗi byte, còn delimiter nằm giữa các byte.

Có thể thêm suffix:

~~~java
HexFormat hex = HexFormat.ofDelimiter(", ")
        .withPrefix("[")
        .withSuffix("]");

System.out.println(hex.formatHex(data));
~~~

Kết quả:

~~~text
[0a], [af], [ff]
~~~

Cần phân biệt:

- `withPrefix("0x")` không có nghĩa là thêm `0x` một lần trước toàn bộ mảng.
- `withSuffix(...)` thêm hậu tố vào từng byte.
- `withDelimiter(...)` nằm giữa hai byte liên tiếp.
- Formatter mặc định không có prefix, suffix hoặc delimiter.

Nếu giao thức yêu cầu một tiền tố chung cho cả chuỗi, có thể nối tiền tố ở ngoài formatter:

~~~java
String payload = "0x" + HexFormat.of().formatHex(data);
~~~

Khi parse, cần bỏ tiền tố chung đó trước hoặc thiết kế định dạng đầu vào phù hợp.

## 7. Ví dụ tổng hợp: cùng dữ liệu với nhiều định dạng

~~~java
import java.util.HexFormat;

public class HexVariantsDemo {
    public static void main(String[] args) {
        byte[] data = {
                0x00, 0x0A, 0x7F, (byte) 0x80, (byte) 0xFF
        };

        HexFormat lower = HexFormat.of();
        HexFormat upper = HexFormat.of().withUpperCase();
        HexFormat colon = HexFormat.ofDelimiter(":");
        HexFormat upperColon = HexFormat.ofDelimiter(":")
                .withUpperCase();
        HexFormat prefixed = HexFormat.ofDelimiter(" ")
                .withPrefix("0x")
                .withUpperCase();

        System.out.println("default    = " + lower.formatHex(data));
        System.out.println("uppercase  = " + upper.formatHex(data));
        System.out.println("colon      = " + colon.formatHex(data));
        System.out.println("upperColon = " + upperColon.formatHex(data));
        System.out.println("prefixed   = " + prefixed.formatHex(data));
    }
}
~~~

Kết quả:

~~~text
default    = 000a7f80ff
uppercase  = 000A7F80FF
colon      = 00:0a:7f:80:ff
upperColon = 00:0A:7F:80:FF
prefixed   = 0x00 0x0A 0x7F 0x80 0xFF
~~~

Chỉ thay cấu hình formatter, mảng byte đầu vào vẫn giữ nguyên. Đây là lợi ích của việc tách dữ liệu khỏi quy tắc hiển thị.

## 8. Chuyển chuỗi hex trở lại byte bằng parseHex

`formatHex(...)` chuyển `byte[]` thành chuỗi. Chiều ngược lại dùng `parseHex(...)`:

~~~java
import java.util.Arrays;
import java.util.HexFormat;

public class HexParseDemo {
    public static void main(String[] args) {
        HexFormat hex = HexFormat.of();

        String text = "00aaff";
        byte[] data = hex.parseHex(text);

        System.out.println(Arrays.toString(data));
        System.out.println(hex.formatHex(data));
    }
}
~~~

Kết quả:

~~~text
[0, -86, -1]
00aaff
~~~

Giá trị `-86` và `-1` là cách Java hiển thị byte có dấu. Mẫu bit của chúng lần lượt là `0xAA` và `0xFF`.

### 8.1. Parse chuỗi chữ hoa

Formatter mặc định có thể parse chữ số hex chữ hoa hoặc chữ thường. Việc chọn uppercase/lowercase chủ yếu ảnh hưởng **cách định dạng đầu ra**, không giới hạn đầu vào parse chỉ theo một kiểu chữ.

~~~java
byte[] bytes = HexFormat.of().parseHex("00Aaff");
~~~

### 8.2. Parse chuỗi có delimiter

Khi dùng formatter có delimiter, chuỗi đầu vào phải theo cấu trúc formatter đó:

~~~java
HexFormat hex = HexFormat.ofDelimiter(":")
        .withUpperCase();

byte[] data = hex.parseHex("0A:AF:FF");
~~~

Formatter đã biết delimiter là `:` nên có thể phân tách các byte. Đừng parse chuỗi có delimiter bằng `HexFormat.of()` mặc định, vì cấu hình mặc định mong đợi các chữ số hex liền nhau.

### 8.3. Parse prefix và suffix

Nếu formatter được cấu hình prefix/suffix cho từng byte, `parseHex(...)` cũng sử dụng cấu hình đó:

~~~java
HexFormat hex = HexFormat.ofDelimiter(" ")
        .withPrefix("0x")
        .withUpperCase();

byte[] data = hex.parseHex("0x0A 0xAF 0xFF");
~~~

Đây là lý do nên dùng cùng một cấu hình formatter cho cả định dạng và phân tích ngược khi dữ liệu được trao đổi theo một quy ước riêng.

### 8.4. Round-trip

Một thuộc tính hữu ích để kiểm tra là dữ liệu sau khi format rồi parse phải bằng dữ liệu gốc:

~~~java
import java.util.Arrays;
import java.util.HexFormat;

byte[] original = {0x00, 0x01, (byte) 0x80, (byte) 0xFF};

HexFormat hex = HexFormat.ofDelimiter(":").withUpperCase();

String encoded = hex.formatHex(original);
byte[] decoded = hex.parseHex(encoded);

System.out.println(Arrays.equals(original, decoded)); // true
~~~

Round-trip này phù hợp để kiểm tra cách biểu diễn byte. Nó không phải mã hóa bảo mật: chuỗi hex chỉ là một cách biểu diễn dữ liệu nhị phân, ai đọc được chuỗi đều có thể khôi phục byte ban đầu.

## 9. Xử lý chuỗi hex không hợp lệ

`parseHex(...)` yêu cầu đầu vào tuân thủ cấu trúc mà formatter mô tả. Các lỗi phổ biến:

- Có ký tự không phải chữ số hex (`0`–`9`, `a`–`f`, `A`–`F`).
- Thiếu một chữ số trong một byte.
- Sai delimiter hoặc thiếu delimiter giữa các byte.
- Prefix hoặc suffix không khớp với formatter đang dùng.
- Định dạng đầu vào có khoảng trắng hoặc dấu phân cách không nằm trong cấu hình.

Ví dụ với formatter mặc định:

~~~java
HexFormat hex = HexFormat.of();

hex.parseHex("abc");   // IllegalArgumentException: số chữ số không đủ cặp
hex.parseHex("0g");    // IllegalArgumentException: g không phải hex digit
hex.parseHex("00:ff"); // IllegalArgumentException: delimiter không được cấu hình
~~~

Nếu parse dữ liệu từ người dùng hoặc file bên ngoài, hãy xử lý `IllegalArgumentException` tại ranh giới đầu vào:

~~~java
static byte[] decodeHex(String input) {
    try {
        return HexFormat.of().parseHex(input);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "Dữ liệu hex không hợp lệ", ex);
    }
}
~~~

Không nên chỉ kiểm tra độ dài chuỗi. Một chuỗi có số ký tự chẵn vẫn có thể chứa ký tự không hợp lệ hoặc sai cấu trúc.

Đầu vào `null` không phải một chuỗi hex hợp lệ và sẽ dẫn đến `NullPointerException`; nếu API cần thông báo lỗi nghiệp vụ riêng, hãy kiểm tra null trước khi gọi parser.

## 10. Định dạng một phần mảng byte

Khi chỉ cần hiển thị một vùng của mảng, có thể dùng overload nhận chỉ số bắt đầu và kết thúc:

~~~java
byte[] data = {
        (byte) 0xDE, (byte) 0xAD, (byte) 0xBE, (byte) 0xEF
};

HexFormat hex = HexFormat.of().withUpperCase();

System.out.println(hex.formatHex(data, 1, 3));
~~~

Kết quả:

~~~text
ADBE
~~~

Khoảng chỉ số dùng quy tắc **bao gồm `fromIndex`, không bao gồm `toIndex`**, tương tự cách cắt range phổ biến trong Java. Trong ví dụ, các phần tử ở vị trí 1 và 2 được định dạng; phần tử vị trí 3 không được lấy.

Chỉ số phải nằm trong giới hạn mảng và vùng bắt đầu không được vượt quá vùng kết thúc. Nếu phạm vi không hợp lệ, API báo lỗi chỉ số.

Nếu muốn lấy byte trước khi format, có thể dùng `Arrays.copyOfRange`, nhưng overload range giúp tránh tạo mảng trung gian khi chỉ cần chuỗi hiển thị.

## 11. HexFormat không quyết định byte order

Một chuỗi hex thể hiện **thứ tự byte đang có trong mảng**. Nó không tự diễn giải số nguyên nhiều byte theo big-endian hay little-endian.

Ví dụ cùng số nguyên `0x12345678` có hai cách sắp xếp byte:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.HexFormat;

int value = 0x12345678;

byte[] bigEndian = ByteBuffer.allocate(Integer.BYTES)
        .order(ByteOrder.BIG_ENDIAN)
        .putInt(value)
        .array();

byte[] littleEndian = ByteBuffer.allocate(Integer.BYTES)
        .order(ByteOrder.LITTLE_ENDIAN)
        .putInt(value)
        .array();

HexFormat hex = HexFormat.of().withUpperCase();

System.out.println(hex.formatHex(bigEndian));    // 12345678
System.out.println(hex.formatHex(littleEndian)); // 78563412
~~~

Cả hai chuỗi đều là biểu diễn hex hợp lệ. Khác biệt xuất phát từ thứ tự byte do `ByteBuffer.order(...)` quyết định trước khi truyền mảng vào `HexFormat`.

Khi đọc protocol hoặc file nhị phân, cần biết byte order mà định dạng quy định. Không thể nhìn chuỗi hex rồi kết luận số nguyên gốc mà không biết thứ tự byte.

## 12. Khi nào dùng HexFormat thay cho cách cũ?

Trước Java 17, người viết thường tự lặp mảng byte và gọi `String.format`, `Integer.toHexString` hoặc tự tra bảng ký tự.

Ví dụ một cách thủ công:

~~~java
static String toHex(byte[] bytes) {
    StringBuilder result = new StringBuilder();
    for (byte value : bytes) {
        result.append(String.format("%02x", value & 0xff));
    }
    return result.toString();
}
~~~

Cách này có thể hoạt động, nhưng phải tự xử lý:

- Byte có dấu bằng cách mask `value & 0xff`.
- Độ rộng hai chữ số và leading zero.
- Chữ hoa/chữ thường.
- Delimiter, prefix và suffix.
- Parse ngược và kiểm tra dữ liệu lỗi.
- Hiệu năng khi format nhiều byte.

Với Java 17, `HexFormat` cung cấp API chuyên dụng và dễ đọc hơn:

~~~java
String result = HexFormat.of().formatHex(bytes);
~~~

| Cách làm | Ưu điểm | Hạn chế |
| --- | --- | --- |
| `HexFormat` | API chuẩn, format/parse, cấu hình chữ hoa và delimiter | Có từ Java 17; dự án cũ hơn không có API này |
| `String.format` | Dễ tùy biến mẫu chuỗi | Gọi format nhiều lần có overhead; cần cẩn thận với byte âm |
| `Integer.toHexString` | Tiện chuyển một giá trị số | Không tự đảm bảo hai chữ số cho mỗi byte; cần xử lý dấu và padding |
| Tự tra bảng hex | Có thể tối ưu cho tình huống đặc biệt | Phải tự duy trì logic và kiểm thử |

Nếu dự án target Java 17 trở lên, ưu tiên `HexFormat` cho việc chuyển đổi byte array sang chuỗi hex. Nếu cần hỗ trợ Java 8/11, phải cân nhắc API tương thích hoặc thư viện riêng.

## 13. HexFormat có phải mã hóa hoặc hash không?

Không. `HexFormat` chỉ **đổi cách biểu diễn** byte thành ký tự và ngược lại.

~~~java
byte[] secret = {0x01, 0x02, 0x03};
String hex = HexFormat.of().formatHex(secret);
byte[] restored = HexFormat.of().parseHex(hex);
~~~

Bất kỳ ai có chuỗi `010203` đều có thể khôi phục mảng byte. Hex không cung cấp:

- Mã hóa bảo mật.
- Tính bí mật.
- Tính toàn vẹn.
- Chữ ký số.
- Khả năng chống sửa đổi.

Nếu cần hash, dùng API trong `java.security.MessageDigest`; nếu cần mã hóa, dùng các API mật mã phù hợp. Sau khi đã có kết quả hash hoặc ciphertext dạng byte, có thể dùng `HexFormat` để **hiển thị** chúng.

Ví dụ định dạng digest:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public class DigestHexDemo {
    public static void main(String[] args) throws NoSuchAlgorithmException {
        byte[] input = "Java 17".getBytes(StandardCharsets.UTF_8);

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] hash = digest.digest(input);

        String hex = HexFormat.of().formatHex(hash);
        System.out.println(hex);
    }
}
~~~

Kết quả là chuỗi hex biểu diễn byte của SHA-256. Thuật toán hash thực hiện bởi `MessageDigest`; `HexFormat` chỉ định dạng output.

## 14. Các phương thức và cấu hình thường dùng

| API | Tác dụng |
| --- | --- |
| `HexFormat.of()` | Tạo formatter mặc định, chữ thường và không delimiter |
| `HexFormat.ofDelimiter(delimiter)` | Tạo formatter có delimiter |
| `withUpperCase()` | Chọn chữ số hex chữ hoa |
| `withLowerCase()` | Chọn chữ số hex chữ thường |
| `withDelimiter(delimiter)` | Đặt delimiter giữa các byte |
| `withPrefix(prefix)` | Đặt prefix trước mỗi byte |
| `withSuffix(suffix)` | Đặt suffix sau mỗi byte |
| `formatHex(bytes)` | Định dạng toàn bộ mảng byte |
| `formatHex(bytes, from, to)` | Định dạng một vùng của mảng |
| `parseHex(text)` | Parse chuỗi theo cấu hình formatter |
| `toString()` | Trả về mô tả cấu hình formatter |

Các phương thức `with...` trả về formatter cấu hình tương ứng; không thay đổi instance ban đầu. Có thể kết hợp nhiều cấu hình:

~~~java
HexFormat wireFormat = HexFormat.ofDelimiter("-")
        .withUpperCase()
        .withPrefix("0x");
~~~

Vì formatter bất biến, có thể khai báo hằng dùng chung:

~~~java
private static final HexFormat HEX =
        HexFormat.of().withUpperCase();
~~~

Không cần tạo mới mỗi lần gọi `formatHex` nếu cấu hình không thay đổi.

## 15. Bài tập thực hành

### Bài 1 — So sánh chữ hoa và chữ thường

Tạo mảng:

~~~java
byte[] data = {0x01, 0x0A, (byte) 0xAF, (byte) 0xFF};
~~~

In mảng bằng `HexFormat.of()`, `withUpperCase()` và `withLowerCase()`. Giải thích vì sao số byte không đổi dù chuỗi hiển thị khác nhau.

### Bài 2 — Thêm delimiter

Dùng delimiter `:` và tạo kết quả:

~~~text
01:0a:af:ff
~~~

Sau đó đổi sang chữ hoa:

~~~text
01:0A:AF:FF
~~~

### Bài 3 — Prefix và suffix

Tạo formatter để hiển thị từng byte theo dạng:

~~~text
[0x01] [0x0a] [0xaf] [0xff]
~~~

Thử `withPrefix`, `withSuffix` và `withDelimiter`. Phân biệt prefix/suffix theo từng byte với tiền tố chung của toàn chuỗi.

### Bài 4 — Round-trip

Format một mảng byte bất kỳ rồi parse trở lại. Dùng `Arrays.equals` xác nhận mảng ban đầu và mảng khôi phục bằng nhau. Lặp lại với formatter có delimiter và prefix.

### Bài 5 — Xử lý dữ liệu không hợp lệ

Thử parse các chuỗi `abc`, `0g`, `00:ff` bằng formatter mặc định. Bắt `IllegalArgumentException` và hiển thị thông báo lỗi phù hợp.

### Bài 6 — Byte order

Dùng `ByteBuffer` chuyển `0x12345678` thành byte array theo big-endian và little-endian. Dùng `HexFormat` in cả hai, rồi giải thích vì sao hai chuỗi khác nhau.

### Bài 7 — Hiển thị hash

Tạo SHA-256 bằng `MessageDigest`, sau đó định dạng digest thành hex chữ thường và chữ hoa. Giải thích vì sao `HexFormat` không thực hiện thuật toán hash.

## 16. Nguyên tắc sử dụng

Trong Java 17, `HexFormat` là API tiêu chuẩn để biểu diễn và phân tích dữ liệu byte dưới dạng hex. `HexFormat.of()` mặc định dùng chữ thường; `withUpperCase()` và `withLowerCase()` cho phép chọn cách viết chữ số; `withDelimiter()`, `withPrefix()` và `withSuffix()` điều chỉnh cách hiển thị từng byte.

Khi sử dụng:

- Dùng `formatHex(byte[])` để chuyển mảng byte thành chuỗi hex.
- Dùng `parseHex(...)` để khôi phục byte từ chuỗi theo đúng cấu hình.
- Tái sử dụng formatter vì nó bất biến và an toàn khi chia sẻ.
- Nhớ rằng `byte` có dấu trong Java nhưng hex biểu diễn mẫu bit 8 bit.
- Phân biệt thứ tự byte (endianness) với thứ tự chữ số hex.
- Xử lý chuỗi đầu vào không hợp lệ tại ranh giới dữ liệu.
- Không coi hex là mã hóa hoặc cơ chế bảo mật.

Tách riêng dữ liệu nhị phân khỏi quy tắc hiển thị giúp log, test và giao tiếp với hệ thống khác nhất quán hơn.
