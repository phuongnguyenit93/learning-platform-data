# NumberFormatException do ký tự sai hoặc vượt miền giá trị trong Java

Khi chuyển văn bản sang số nguyên bằng `Integer.parseInt`, `Long.parseLong` hoặc những API tương tự, Java có thể ném **`NumberFormatException`**. Hai nhóm nguyên nhân quan trọng nhất là:

1. **Chuỗi không phù hợp cú pháp số nguyên** của API/radix được chọn: chứa ký tự không hợp lệ, dấu ở sai vị trí, dấu thập phân, khoảng trắng chưa xử lý, tiền tố chưa được API nhận diện…
2. **Chuỗi biểu diễn số vượt miền giá trị** của kiểu đích: ví dụ `2147483648` là một số thập phân hợp lệ về cú pháp nhưng lớn hơn `Integer.MAX_VALUE`.

Điểm cốt lõi: **`parseInt` kiểm tra cú pháp *và* miền biểu diễn**. Khi lỗi, phương thức không trả số gần đúng, không bỏ qua phần đuôi và không “tràn vòng” để cho ra giá trị `int` khác. Bài học thuộc nhóm **Phân tích số nguyên** và tập trung vào cách chẩn đoán, phòng tránh và xử lý đúng các trường hợp này trên Java 17+.

## 1. `NumberFormatException` xảy ra ở đâu?

`NumberFormatException` là một nhánh của `IllegalArgumentException`, thuộc nhóm **unchecked exception**. Vì vậy Java không bắt buộc caller khai báo `throws` hoặc `catch`, nhưng dữ liệu đầu vào không tin cậy vẫn cần chính sách xử lý rõ ràng.

~~~java
int quantity = Integer.parseInt("123"); // 123
long balance = Long.parseLong("123");  // 123L
~~~

Những API thường gặp:

| API | Kiểu kết quả | Khi nào gặp NumberFormatException? |
| --- | --- | --- |
| `Integer.parseInt(text)` | `int` có dấu, hệ 10 | Cú pháp sai hoặc ngoài miền 32-bit |
| `Integer.parseInt(text, radix)` | `int` có dấu, hệ 2–36 | Ký tự không thuộc cơ số, radix không hợp lệ, hoặc ngoài miền `int` |
| `Long.parseLong(text)` | `long` có dấu, hệ 10 | Cú pháp sai hoặc ngoài miền 64-bit |
| `Integer.parseUnsignedInt(text)` | `int` chứa bit của số không dấu 32-bit | Sai cú pháp hoặc ngoài miền 0 đến 2³² − 1 |
| `Long.parseUnsignedLong(text)` | `long` chứa bit của số không dấu 64-bit | Sai cú pháp hoặc ngoài miền 0 đến 2⁶⁴ − 1 |
| `Integer.decode(text)` | `Integer` | Sai cú pháp, tiền tố không hợp lệ hoặc vượt miền kiểu đích |
| `new BigInteger(text)` | `BigInteger` | Cú pháp sai; **không bị chặn bởi giới hạn `int`/`long`** |

`Integer.valueOf(String)` và `Long.valueOf(String)` cũng dựa trên parsing có kiểm tra cú pháp/miền tương ứng. `valueOf` trả wrapper, trong khi `parseInt` / `parseLong` trả primitive; **cả hai không mặc nhiên biến chuỗi lỗi thành null hoặc 0**.

Đừng nhầm `NumberFormatException` với `ArithmeticException` của phép chia số nguyên cho 0 hay `NullPointerException` do unboxing wrapper null. Chúng có điểm phát sinh và chiến lược xử lý khác nhau.

## 2. Những ký tự khiến `Integer.parseInt` thất bại

`Integer.parseInt(text)` mặc định hiểu **chuỗi số nguyên thập phân**, với một dấu `+` hoặc `-` tùy chọn ở **đầu chuỗi**, theo sau là ít nhất một chữ số hợp lệ. Hàm phân tích toàn bộ chuỗi, không chỉ phần tiền tố chứa số.

| Chuỗi | Kết quả khi gọi `Integer.parseInt` | Giải thích |
| --- | --- | --- |
| `"42"` | `42` | Hợp lệ |
| `"+42"` | `42` | Dấu cộng đứng đầu được phép |
| `"-42"` | `-42` | Dấu trừ ASCII đứng đầu được phép |
| `"0012"` | `12` | Số 0 ở đầu không làm `parseInt` tự đổi sang hệ 8 |
| `""` | Ngoại lệ | Không có chữ số |
| `"+"` hoặc `"-"` | Ngoại lệ | Chỉ có dấu, thiếu chữ số |
| `"12x"`, `"1 2"` | Ngoại lệ | Chứa ký tự không phải chữ số ở cơ số 10 |
| `"1_000"` | Ngoại lệ | Dấu gạch dưới không thuộc cú pháp runtime parser |
| `"12.0"`, `"1e3"` | Ngoại lệ | Đây không phải cú pháp số nguyên của `parseInt` |
| `" 42 "` hoặc `"42\n"` | Ngoại lệ | Có khoảng trắng/ký tự xuống dòng |
| `"0x2A"` | Ngoại lệ | `parseInt` hệ 10 không tự xử lý tiền tố `0x` |
| `"−42"` | Ngoại lệ | Dấu trừ Unicode U+2212 không phải dấu trừ ASCII `-` |

**Đặc biệt về dấu gạch dưới:** mã nguồn Java chấp nhận `1_000` là một *integer literal* hợp lệ trong trình biên dịch, nhưng chuỗi runtime `"1_000"` đưa vào `parseInt` **không hợp lệ**. Đừng nhầm cú pháp literal viết trong source code với cú pháp dữ liệu văn bản được API phân tích.

**Đặc biệt về Unicode:** parsing Java sử dụng quy tắc nhận diện chữ số dựa trên `Character.digit`, vì thế một số chữ số Unicode (ví dụ các chữ số fullwidth) có thể được chấp nhận. Nếu định dạng đầu vào của một giao thức buộc phải là ASCII `0–9`, hãy xác minh quy tắc ASCII một cách tường minh, **không** dựa vào việc `parseInt` sẽ từ chối mọi chữ số ngoài ASCII. Ngược lại, dấu trừ Unicode U+2212 không được coi như dấu `-` ASCII.

## 3. Chuỗi đúng cú pháp vẫn có thể vượt miền kiểu số

`int` có dấu của Java là kiểu 32-bit, có miền:

- `Integer.MIN_VALUE = -2147483648`
- `Integer.MAX_VALUE = 2147483647`

Vì vậy:

~~~java
int max = Integer.parseInt("2147483647");  // Hợp lệ
int min = Integer.parseInt("-2147483648"); // Hợp lệ

// Integer.parseInt("2147483648");  // NumberFormatException
// Integer.parseInt("-2147483649"); // NumberFormatException
~~~

`"2147483648"` là chuỗi gồm toàn chữ số hợp lệ. Nó không được chấp nhận vì **giá trị toán học không nằm trong miền `int`**, chứ không phải do “có ký tự lạ”.

Với `long` có dấu, giới hạn tương ứng là:

- `Long.MIN_VALUE = -9223372036854775808`
- `Long.MAX_VALUE = 9223372036854775807`

~~~java
long maxLong = Long.parseLong("9223372036854775807");

// Long.parseLong("9223372036854775808"); // NumberFormatException
~~~

Số `2147483648` có thể parse thành `long`, còn số vượt `Long.MAX_VALUE` có thể được biểu diễn bằng `BigInteger`:

~~~java
long largerThanInt = Long.parseLong("2147483648");
java.math.BigInteger largerThanLong =
        new java.math.BigInteger("9223372036854775808");
~~~

**Một kiểu lớn hơn chỉ giải quyết lỗi vượt miền, không giải quyết chuỗi có ký tự sai.** `new BigInteger("12x")` vẫn ném `NumberFormatException`.

Cũng phải phân biệt **parse** và **phép toán đã parse xong**: `Integer.parseInt("2147483647") + 1` có thể overflow theo quy tắc số nguyên `int`, trong khi `Integer.parseInt("2147483648")` ném ngoại lệ ngay lúc parse. Nếu muốn phát hiện overflow khi cộng, dùng `Math.addExact` hoặc nâng kiểu dữ liệu hợp lý.

## 4. Radix (cơ số) và ký tự hợp lệ

`Integer.parseInt(text, radix)` chấp nhận cơ số từ `Character.MIN_RADIX` = 2 tới `Character.MAX_RADIX` = 36. Một ký tự có giá trị chữ số phải nhỏ hơn radix; với radix 16, chữ `A`–`F` biểu thị 10–15 (không phân biệt hoa/thường trong trường hợp ASCII).

~~~java
int decimalFromBinary = Integer.parseInt("1010", 2); // 10
int decimalFromHex = Integer.parseInt("2A", 16);     // 42

// Integer.parseInt("102", 2);    // NumberFormatException: digit 2 không thuộc hệ 2
// Integer.parseInt("0x2A", 16);  // NumberFormatException: parseInt không bỏ tiền tố 0x
~~~

**Radix và tiền tố là hai cơ chế riêng:**

| Cách gọi | Kết quả | Ghi chú |
| --- | --- | --- |
| `Integer.parseInt("2A", 16)` | `42` | Hệ 16 không kèm tiền tố |
| `Integer.parseInt("0x2A", 16)` | Ngoại lệ | `parseInt` không tự loại `0x` |
| `Integer.decode("0x2A")` | `42` | `decode` nhận tiền tố hexadecimal |
| `Integer.decode("#2A")` | `42` | Một dạng tiền tố hexadecimal khác |
| `Integer.parseInt("010")` | `10` | Hệ 10 mặc định |
| `Integer.decode("010")` | `8` | `decode` nhận số 0 dẫn đầu theo dạng octal |

`Integer.decode` còn hỗ trợ dạng có dấu đặt trước tiền tố, chẳng hạn `"-0x2A"`. Đừng dùng `decode` cho một chuỗi mã định danh có số 0 ở đầu nếu hợp đồng dữ liệu nói rằng mọi giá trị đều là thập phân; hành vi hệ 8 có thể rất bất ngờ.

Nếu input từ giao thức cho phép tiền tố `0x` và radix 16, bạn có thể phân tích tiền tố theo quy tắc của giao thức rồi gọi `parseInt` trên phần chữ số, hoặc dùng `decode` khi đúng tất cả cú pháp mà API ấy định nghĩa. Luôn kiểm tra *miền giá trị* sau khi đã xác định cú pháp/radix.

## 5. Parse số nguyên không dấu: kết quả bit có thể âm khi nhìn như signed

`Integer.parseUnsignedInt` cho phép phân tích miền không dấu 32-bit, từ 0 tới 4294967295. Nhưng kiểu trả về vẫn là **`int` 32-bit**, không có kiểu primitive `uint` riêng trong Java.

~~~java
int bits = Integer.parseUnsignedInt("4294967295");
System.out.println(bits);                       // -1 (in như int có dấu)
System.out.println(Integer.toUnsignedLong(bits)); // 4294967295
~~~

`bits == -1` ở đây không đồng nghĩa quá trình parse thất bại: toàn bộ bit của giá trị unsigned lớn nhất đều bằng 1, nên khi diễn giải dưới dạng signed `int` thì là -1. Dùng `Integer.toUnsignedLong` hoặc `Integer.toUnsignedString` để hiển thị theo ngữ nghĩa unsigned.

~~~java
// Integer.parseUnsignedInt("4294967296"); // NumberFormatException
// Integer.parseUnsignedInt("-1");         // NumberFormatException
~~~

Đối với `Long.parseUnsignedLong`, miền unsigned là 0 tới 18446744073709551615, nhưng kết quả vẫn có kiểu `long`; khi cần in dạng unsigned, dùng `Long.toUnsignedString`. Nếu cần giữ giá trị dương lớn hơn `Long.MAX_VALUE` như một số nguyên toán học có dấu dương trong đối tượng, `BigInteger` thường giúp diễn đạt ý định rõ hơn.

**Không sửa lỗi tràn `parseInt` bằng cách chuyển sang unsigned nếu miền dữ liệu thực sự là số nguyên có dấu.** Chọn đúng API theo đặc tả dữ liệu, không theo mong muốn tạm thời “parse cho qua”.

## 6. Khoảng trắng, normalizing và dữ liệu bên ngoài

`Integer.parseInt(" 42 ")` thất bại do chứa khoảng trắng. Nếu hợp đồng đầu vào cho phép bỏ khoảng trắng ở **đầu và cuối**, có thể làm rõ ở ranh giới nhập:

~~~java
String raw = " 42 ";
String normalized = raw.strip();
int parsed = Integer.parseInt(normalized); // 42
~~~

`strip` dựa trên `Character.isWhitespace`; `trim` và `strip` không nhận diện cùng tập ký tự. Không nên khẳng định một lệnh `strip` giải quyết được mọi kiểu khoảng trắng của mọi chuẩn dữ liệu.

**Chỉ normalize nếu đặc tả cho phép.** Với mã định danh, token chữ ký hoặc dữ liệu tài chính, loại bỏ dấu `+`, số 0 đầu, phân cách nhóm hoặc ký tự “trông giống nhau” có thể làm thay đổi ý nghĩa. Ví dụ, nếu hệ thống cần giữ mã `"0012"` là mã khác với `"12"`, việc chuyển sang `int` đã mất thông tin về số chữ số ban đầu.

Đừng thay `parseInt` bằng `replaceAll("[^0-9]", "")` để “chữa chuỗi bẩn”: biến `"-25"` thành `"25"`, `"1,234"` thành `"1234"` hoặc một giá trị có ký tự lạ thành số khác là **thay dữ liệu âm thầm**, dễ gây sai nghiệp vụ và tạo lỗ hổng kiểm tra.

Nếu dữ liệu chấp nhận định dạng bản địa hóa có dấu phân cách nhóm/thập phân, hãy xác định cú pháp bằng một parser thích hợp (`NumberFormat` có cơ chế phân tích và chính sách riêng). Lưu ý một số parser dạng locale có thể chấp nhận **một phần chuỗi**; cần kiểm tra vị trí parse kết thúc nếu hợp đồng đòi tiêu thụ toàn bộ đầu vào. `Integer.parseInt` bản thân đòi chuỗi hợp lệ toàn phần.

## 7. Kiểm tra lỗi đúng vị trí: không nuốt `NumberFormatException`

Giả sử một cột CSV phải chứa số lượng nguyên `int` dương. Cách xử lý ranh giới đầu vào có thể là:

~~~java
static int parsePositiveQuantity(String raw) {
    if (raw == null) {
        throw new IllegalArgumentException("quantity is required");
    }
    String normalized = raw.strip();
    try {
        int value = Integer.parseInt(normalized);
        if (value <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        return value;
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                "quantity must be a valid 32-bit integer", ex);
    }
}
~~~

Đây là **một phương thức minh họa**, cần đặt bên trong lớp Java; không phải chương trình độc lập. Cấu trúc trên phân biệt:

- **Thiếu trường:** `null` → lỗi “required” rõ ràng.
- **Sai cú pháp hoặc vượt miền:** `NumberFormatException` → chuyển thành lỗi validation có ngữ cảnh và giữ `cause` để chẩn đoán.
- **Đúng số nguyên nhưng sai quy tắc nghiệp vụ:** `0` hoặc giá trị âm → lỗi “must be positive”.

Không dùng một `catch (Exception)` quá rộng quanh cả luồng xử lý rồi mặc định trả 0. Khi nhận input không tin cậy, bạn có thể trả kết quả xác thực thành công/thất bại hoặc thông báo lỗi tương ứng cho người dùng; còn lỗi hệ thống thật phải được phân biệt.

Tránh hiển thị nguyên văn thông báo lỗi cho dữ liệu chứa thông tin nhạy cảm, token hoặc trường cực dài; hãy dùng thông báo ổn định như “Giá trị số nguyên không hợp lệ” và ghi log có kiểm soát. Văn bản `NumberFormatException.getMessage()` không phải giao thức máy đọc ổn định giữa mọi API/phiên bản JDK.

## 8. Tại sao pre-validation bằng regex không đủ?

Bạn có thể kiểm tra cú pháp ASCII decimal có dấu bằng biểu thức chính quy:

~~~java
static boolean looksLikeAsciiInteger(String text) {
    return text != null && text.matches("[+-]?[0-9]+");
}
~~~

Nhưng regex này **chỉ kiểm tra mẫu ký tự**, không kiểm tra miền kiểu số. Chuỗi `"999999999999999999999999999999"` vẫn vượt giới hạn `int`/`long` dù khớp regex.

Ngược lại, `parseInt` có thể nhận một số chữ số Unicode mà regex ASCII trên từ chối. Nếu hệ thống yêu cầu chuẩn ASCII chặt chẽ, đó là chủ ý có thể đúng. Nếu dữ liệu phải chấp nhận chữ số Unicode hợp lệ, chọn quy tắc xác thực khác.

**Nguyên tắc:** kiểm tra cú pháp theo hợp đồng dữ liệu trước (nếu thực sự cần), nhưng vẫn phải gọi parser phù hợp và **xử lý `NumberFormatException`** vì lỗi miền giá trị vẫn có thể xảy ra. Một lời gọi parse với `try/catch` hẹp thường đơn giản hơn việc tự viết bộ kiểm tra giá trị ở mọi vị trí.

## 9. Ví dụ Java 17+ hoàn chỉnh: phân biệt lỗi ký tự và lỗi miền

Lưu thành tệp `ParseFailuresDemo.java`:

~~~java
import java.math.BigInteger;

public class ParseFailuresDemo {
    static void checkInt(String input) {
        try {
            System.out.println("parseInt(" + String.valueOf(input)
                    + ") = " + Integer.parseInt(input));
        } catch (NumberFormatException ex) {
            System.out.println("parseInt(" + String.valueOf(input)
                    + ") = NumberFormatException");
        }
    }

    public static void main(String[] args) {
        checkInt("2147483647");
        checkInt("2147483648");
        checkInt("-2147483648");
        checkInt("-2147483649");
        checkInt("12x");
        checkInt("1_000");
        checkInt(" 42 ");
        checkInt("12.0");
        checkInt("");
        checkInt(null);
        checkInt("+42");
        checkInt("0x2A");

        System.out.println("binary 1010 = "
                + Integer.parseInt("1010", 2));
        try {
            Integer.parseInt("102", 2);
        } catch (NumberFormatException ex) {
            System.out.println("binary 102 = NumberFormatException");
        }
        System.out.println("hex 2A = "
                + Integer.parseInt("2A", 16));
        System.out.println("decode 0x2A = "
                + Integer.decode("0x2A"));
        System.out.println("parseInt 010 = "
                + Integer.parseInt("010"));
        System.out.println("decode 010 = "
                + Integer.decode("010"));

        int unsigned = Integer.parseUnsignedInt("4294967295");
        System.out.println("unsigned bits as int = " + unsigned);
        System.out.println("unsigned as long = "
                + Integer.toUnsignedLong(unsigned));
        try {
            Integer.parseUnsignedInt("4294967296");
        } catch (NumberFormatException ex) {
            System.out.println("unsigned 4294967296 = NumberFormatException");
        }
        try {
            Long.parseLong("9223372036854775808");
        } catch (NumberFormatException ex) {
            System.out.println("long overflow = NumberFormatException");
        }
        System.out.println("BigInteger = "
                + new BigInteger("9223372036854775808"));
        System.out.println("strip then parse = "
                + Integer.parseInt(" 42 ".strip()));
    }
}
~~~

Lệnh biên dịch/chạy:

~~~bash
javac ParseFailuresDemo.java
java ParseFailuresDemo
~~~

Stdout dự kiến (đã xử lý ngoại lệ trong chương trình nên không in stack trace):

~~~text
parseInt(2147483647) = 2147483647
parseInt(2147483648) = NumberFormatException
parseInt(-2147483648) = -2147483648
parseInt(-2147483649) = NumberFormatException
parseInt(12x) = NumberFormatException
parseInt(1_000) = NumberFormatException
parseInt( 42 ) = NumberFormatException
parseInt(12.0) = NumberFormatException
parseInt() = NumberFormatException
parseInt(null) = NumberFormatException
parseInt(+42) = 42
parseInt(0x2A) = NumberFormatException
binary 1010 = 10
binary 102 = NumberFormatException
hex 2A = 42
decode 0x2A = 42
parseInt 010 = 10
decode 010 = 8
unsigned bits as int = -1
unsigned as long = 4294967295
unsigned 4294967296 = NumberFormatException
long overflow = NumberFormatException
BigInteger = 9223372036854775808
strip then parse = 42
~~~

Các dòng đầu cho thấy parser **không phân biệt lỗi cú pháp với lỗi vượt miền bằng loại exception**: cả hai đều thuộc `NumberFormatException`. Caller có thể dựa vào hợp đồng dữ liệu để hiển thị lời nhắc phù hợp, nhưng không nên suy ra nguyên nhân bằng cách parse chuỗi thông báo ngoại lệ của JDK.

## 10. Khi không muốn exception làm luồng chương trình dừng

Có hai chiến lược phổ biến và đều cần thể hiện rõ mục đích:

**Chiến lược A — báo lỗi ngay (fail fast).** Dùng trong dữ liệu bắt buộc chính xác hoặc thông tin cấu hình hệ thống.

~~~java
static int requirePort(String value) {
    int port = Integer.parseInt(value);
    if (port < 1 || port > 65535) {
        throw new IllegalArgumentException("port outside 1..65535");
    }
    return port;
}
~~~

Nếu chuỗi `value` sai hoặc vượt miền, lỗi vẫn là `NumberFormatException` ngay ở bước parse; nếu số `int` hợp lệ nhưng nằm ngoài miền cổng, ứng dụng ném `IllegalArgumentException`. Việc phân biệt này giúp sửa đúng nguồn lỗi.

**Chiến lược B — kết quả parse có thể thất bại.** Dùng khi dữ liệu đầu vào bình thường có thể thiếu/sai và caller phải tự quyết định.

~~~java
static java.util.OptionalInt tryParseInt(String raw) {
    if (raw == null) {
        return java.util.OptionalInt.empty();
    }
    try {
        return java.util.OptionalInt.of(Integer.parseInt(raw));
    } catch (NumberFormatException ex) {
        return java.util.OptionalInt.empty();
    }
}
~~~

Đây là phương thức minh họa trong một class. `OptionalInt.empty()` báo thất bại mà không giả vờ kết quả là 0. **Đổi lại, chiến lược này gộp “ký tự sai” và “vượt miền” thành một trạng thái thất bại**. Nếu giao diện cần chỉ ra lỗi chính xác, thiết kế một kiểu kết quả có thông tin lỗi hoặc xác thực đầu vào ở lớp ứng dụng.

Với luồng đọc hàng triệu giá trị, đừng dùng ngoại lệ lặp đi lặp lại như một bộ tokenizer thay cho thiết kế dữ liệu; hãy cân nhắc parser có hợp đồng trả trạng thái và đo hiệu năng thực tế. Dù tối ưu thế nào, vẫn phải kiểm tra miền biểu diễn.

## 11. Những nhầm lẫn cần tránh

1. **“Chuỗi toàn chữ số thì parse chắc chắn được.”** Sai: `2147483648` không chứa ký tự lạ nhưng vượt miền `int`.
2. **“`parseInt` sẽ tự overflow như phép cộng `int`.”** Sai: nó kiểm tra miền và ném `NumberFormatException`.
3. **“`parseInt` hiểu cú pháp literal Java.”** Sai: dấu gạch dưới, hậu tố `L` và tiền tố `0x` không tự hợp lệ trong `parseInt(text)`.
4. **“Tăng radix để đọc được `0xFF`.”** Không: `parseInt("0xFF", 16)` vẫn chứa `x` không hợp lệ; dùng `"FF"` cùng radix 16 hoặc `Integer.decode("0xFF")` nếu đúng hợp đồng.
5. **“`parseInt("010")` là bát phân.”** Sai: `parseInt` mặc định hệ 10, khác `Integer.decode`.
6. **“Dùng `strip` xong thì mọi ký tự ‘lạ’ đều hết.”** Sai: `strip` chỉ xử lý tập ký tự whitespace được nhận diện ở hai đầu.
7. **“Ép về `long`, `BigInteger` sẽ làm chuỗi có ký tự lỗi hợp lệ.”** Sai: kiểu lớn hơn giải quyết miền giá trị, không giải quyết sai cú pháp.
8. **“Số không dấu phải luôn in ra một số dương khi giữ trong `int`.”** Sai: bit unsigned lớn có thể hiện thành số âm dưới diễn giải signed.
9. **“Regex hợp lệ chứng minh không thể có NumberFormatException.”** Sai: regex cơ bản thường không kiểm tra giới hạn số.
10. **“Catch ngoại lệ rồi trả `0` là an toàn.”** Sai: làm mất khả năng phân biệt dữ liệu 0 hợp lệ và parse thất bại.
11. **“Thông báo `NumberFormatException` là giao diện API ổn định để phân loại nguyên nhân.”** Không nên parse message: nó có thể thay đổi và không phải contract nghiệp vụ.
12. **“Số 0 đứng đầu không có ý nghĩa.”** Với parse thành `int` bạn có thể đã làm mất ý nghĩa định dạng của mã định danh. Nếu cần giữ chuỗi như `0012`, lưu dưới dạng chuỗi thay vì ép sang số.

## 12. Checklist khi xử lý chuỗi số nguyên từ bên ngoài

1. Xác định **mục đích**: số lượng, ID, mã bưu chính, port hay bit unsigned? Không phải dữ liệu toàn chữ số nào cũng nên lưu dưới dạng số.
2. Định nghĩa **cú pháp đầu vào**: dấu cộng/trừ, cơ số, tiền tố `0x`, Unicode digit, khoảng trắng, ký tự nhóm số có được phép không?
3. Chọn **kiểu và miền**: `int`, `long`, unsigned hoặc `BigInteger`; nêu miền giá trị của nghiệp vụ nếu hẹp hơn kiểu.
4. Normalizing **chỉ theo hợp đồng**; không tự xóa mọi ký tự “không phải chữ số”.
5. Parse bằng API đúng, bắt `NumberFormatException` ở **ranh giới dữ liệu** nơi có đủ thông tin để xử lý.
6. Phân biệt lỗi **sai cú pháp**, **vượt miền kiểu**, **ngoài miền nghiệp vụ** và **thiếu dữ liệu** trong thông báo hoặc kết quả validation nếu cần.
7. Không che thất bại bằng `0` hoặc một số sentinel có thể là dữ liệu hợp lệ; log có kiểm soát, giữ nguyên đầu vào gốc khi cần chẩn đoán.

## 13. Tự kiểm tra

**Câu 1.** Vì sao `Integer.parseInt("2147483648")` ném `NumberFormatException` dù toàn ký tự đều là chữ số?

**Đáp án:** Giá trị toán học 2147483648 lớn hơn `Integer.MAX_VALUE`. Parser xác minh cả cú pháp và miền kiểu.

**Câu 2.** `Integer.parseInt("1_000")` có hợp lệ vì Java cho phép viết literal `1_000` không?

**Đáp án:** Không. Dấu gạch dưới là cú pháp literal trong source Java, không thuộc ngữ pháp chuỗi runtime của `parseInt`.

**Câu 3.** Với hệ nhị phân, `Integer.parseInt("102", 2)` lỗi vì điều gì? Cách đổi chuỗi `"1010"` sang thập phân?

**Đáp án:** Chữ số 2 không hợp lệ trong radix 2. `Integer.parseInt("1010", 2)` trả 10.

**Câu 4.** `Integer.parseInt("010")` và `Integer.decode("010")` có bằng nhau không?

**Đáp án:** Không: lần lượt trả 10 và 8 theo quy tắc cơ số của mỗi API.

**Câu 5.** Nếu `Integer.parseUnsignedInt("4294967295")` in `-1`, có phải parser sai không?

**Đáp án:** Không. Bit pattern unsigned 32-bit lớn nhất, khi đọc như signed `int` là -1. Dùng `Integer.toUnsignedLong` hoặc `Integer.toUnsignedString` để xem giá trị không dấu.

**Câu 6.** Một chuỗi số hợp lệ vượt cả `Long.MAX_VALUE` cần xử lý thế nào? Lúc nào `BigInteger` vẫn không giúp được?

**Đáp án:** Chọn `BigInteger` nếu nghiệp vụ cho phép số lớn tùy ý. `BigInteger` vẫn ném `NumberFormatException` khi chuỗi có cú pháp số nguyên không hợp lệ.

## Tài liệu tham khảo

- [Java SE 21 — Integer.parseInt, parseUnsignedInt và decode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html).
- [Java SE 21 — Long.parseLong và parseUnsignedLong](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Long.html).
- [Java SE 21 — NumberFormatException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/NumberFormatException.html).
- [Java SE 21 — BigInteger](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigInteger.html).
- [Java Language Specification `3.10.1 — Integer Literals](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html#jls-3.10.1): phân biệt cú pháp literal trong source với parser chuỗi runtime.
