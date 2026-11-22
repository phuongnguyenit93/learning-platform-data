# Chuyển ký tự hex và phát hiện đầu vào không hợp lệ

## 1. Hệ thập lục phân và cách Java biểu diễn dữ liệu

Hệ thập lục phân (hexadecimal, thường viết tắt là **hex**) dùng cơ số 16. Một chữ số hex có thể nhận một trong 16 giá trị:

| Ký tự | Giá trị thập phân | Ký tự | Giá trị thập phân |
|---|---:|---|---:|
| `0` | 0 | `8` | 8 |
| `1` | 1 | `9` | 9 |
| `2` | 2 | `A` hoặc `a` | 10 |
| `3` | 3 | `B` hoặc `b` | 11 |
| `4` | 4 | `C` hoặc `c` | 12 |
| `5` | 5 | `D` hoặc `d` | 13 |
| `6` | 6 | `E` hoặc `e` | 14 |
| `7` | 7 | `F` hoặc `f` | 15 |

Một chữ số hex biểu diễn được 4 bit, gọi là **nibble**. Hai chữ số hex ghép lại biểu diễn một byte (8 bit):

~~~text
Hex:        A       7
Giá trị:   1010    0111
            \\      /
Byte:       10100111
            = 0xA7
            = 167 (unsigned)
            = -89 (signed byte trong Java)
~~~

Ví dụ:

- `0x10` = 16 ở hệ thập phân.
- `0xFF` = 255 nếu diễn giải như số nguyên không dấu 8 bit.
- `0xA7` = 167 nếu diễn giải unsigned, nhưng cùng 8 bit đó là -89 khi diễn giải bằng kiểu `byte` có dấu của Java.

Trong Java, một ký tự hex có kiểu `char` hoặc nằm trong `String`. Muốn chuyển nó thành giá trị nibble, cần **giải mã ký tự theo cơ số 16**, không phải lấy mã Unicode của ký tự.

~~~java
char hex = 'F';
System.out.println((int) hex); // 70: mã ký tự 'F'
System.out.println(Character.digit(hex, 16)); // 15: giá trị hex
~~~

Đây là điểm xuất phát của bài: chuyển đúng ký tự, xác định chính sách chấp nhận đầu vào và phát hiện lỗi trước khi dữ liệu được dùng trong logic nghiệp vụ.

## 2. Chuyển một ký tự hex sang giá trị số

### 2.1. Dùng `Character.digit(char, radix)`

Java cung cấp `Character.digit(char ch, int radix)` để chuyển ký tự thành giá trị số theo một cơ số:

~~~java
int a = Character.digit('0', 16); // 0
int b = Character.digit('9', 16); // 9
int c = Character.digit('A', 16); // 10
int d = Character.digit('f', 16); // 15
int invalid = Character.digit('G', 16); // -1
~~~

Tham số `radix` là cơ số cần diễn giải. Với hex, dùng `16`. Nếu ký tự không phải chữ số hợp lệ trong cơ số đó hoặc radix nằm ngoài khoảng hợp lệ, method trả về `-1`.

Một hàm nhỏ có thể bọc lại để biến lỗi thành thông báo rõ ràng:

~~~java
static int parseHexDigit(char ch) {
    int digit = Character.digit(ch, 16);
    if (digit < 0) {
        throw new IllegalArgumentException(
                "Ký tự hex không hợp lệ: '" + ch + "'"
        );
    }
    return digit;
}
~~~

Ví dụ:

~~~java
System.out.println(parseHexDigit('B')); // 11
System.out.println(parseHexDigit('e')); // 14
System.out.println(parseHexDigit('8')); // 8
// parseHexDigit('X') -> IllegalArgumentException
~~~

**Không nên tự suy luận giá trị bằng cách ép kiểu `(int) ch`.** `'A'` có mã ký tự 65 nhưng giá trị hex là 10; `'F'` có mã 70 nhưng giá trị hex là 15.

### 2.2. Dùng `Character.forDigit(int digit, int radix)` theo chiều ngược lại

`Character.forDigit` chuyển giá trị số thành ký tự biểu diễn theo cơ số:

~~~java
char zero = Character.forDigit(0, 16);   // '0'
char nine = Character.forDigit(9, 16);   // '9'
char ten = Character.forDigit(10, 16);   // 'a'
char fifteen = Character.forDigit(15, 16); // 'f'
~~~

Với radix 16, chữ cái được trả về ở dạng chữ thường. Muốn hiển thị chữ hoa:

~~~java
char upper = Character.toUpperCase(Character.forDigit(15, 16));
System.out.println(upper); // F
~~~

Nếu chữ số không hợp lệ đối với radix, `Character.forDigit` trả về ký tự null `'\u0000'`. Vì vậy, nếu dữ liệu số đến từ bên ngoài, cần kiểm tra trước:

~~~java
static char toHexDigit(int value) {
    if (value < 0 || value > 15) {
        throw new IllegalArgumentException("Nibble phải nằm trong [0, 15]");
    }
    return Character.toUpperCase(Character.forDigit(value, 16));
}
~~~

### 2.3. Tự kiểm tra ký tự ASCII khi định dạng yêu cầu hex ASCII

`Character.digit` tuân theo quy tắc Unicode của Java và có thể nhận diện một số ký tự số ngoài ASCII. Điều đó hữu ích với văn bản đa ngôn ngữ, nhưng **không phải định dạng nào cũng cho phép**. Hex trong giao thức, file nhị phân, mã định danh và nhiều chuẩn trao đổi dữ liệu thường chỉ chấp nhận sáu nhóm ASCII: `0-9`, `A-F`, `a-f`.

Nếu hợp đồng đầu vào yêu cầu đúng ASCII, hãy kiểm tra tường minh:

~~~java
static int asciiHexDigit(char ch) {
    if (ch >= '0' && ch <= '9') {
        return ch - '0';
    }
    if (ch >= 'A' && ch <= 'F') {
        return ch - 'A' + 10;
    }
    if (ch >= 'a' && ch <= 'f') {
        return ch - 'a' + 10;
    }
    return -1;
}
~~~

Ví dụ:

~~~java
System.out.println(asciiHexDigit('0')); // 0
System.out.println(asciiHexDigit('9')); // 9
System.out.println(asciiHexDigit('A')); // 10
System.out.println(asciiHexDigit('f')); // 15
System.out.println(asciiHexDigit('G')); // -1
System.out.println(asciiHexDigit(' ')); // -1
~~~

Hai cách có mục tiêu khác nhau:

| Cách | Hành vi | Dùng khi |
|---|---|---|
| `Character.digit(ch, 16)` | Theo quy tắc ký tự số/chữ của Java Unicode | Xử lý ký tự theo ngữ nghĩa Unicode |
| Hàm kiểm tra ASCII | Chỉ nhận `0-9`, `A-F`, `a-f` | Đọc protocol, file hex, token hoặc định dạng yêu cầu ASCII |

Không nên dùng một bộ kiểm tra quá rộng cho dữ liệu giao thức chỉ vì nó “có thể chuyển thành số”. Việc chấp nhận nhiều ký tự hơn đặc tả có thể gây khác biệt giữa các hệ thống, lỗi canonicalization hoặc khó phát hiện dữ liệu bất thường.

## 3. Chuyển cả chuỗi hex thành số nguyên

### 3.1. Dùng `Integer.parseInt(text, 16)`

Khi chuỗi hex biểu diễn một số nguyên có dấu nằm trong phạm vi `int`, có thể dùng:

~~~java
int decimal = Integer.parseInt("7B", 16);
System.out.println(decimal); // 123
~~~

Ví dụ:

~~~java
int a = Integer.parseInt("FF", 16);  // 255
int b = Integer.parseInt("10", 16);  // 16
int c = Integer.parseInt("7fffffff", 16); // Integer.MAX_VALUE
~~~

Phương thức này:

- Chấp nhận chữ số hex viết hoa hoặc viết thường.
- Không tự động hiểu tiền tố `0x` hoặc `0X`.
- Có thể chấp nhận dấu `+` hoặc `-` theo quy tắc parse số nguyên.
- Ném `NumberFormatException` nếu chuỗi rỗng, chứa ký tự không hợp lệ, hoặc giá trị vượt phạm vi `int`.

Ví dụ không hợp lệ:

~~~java
Integer.parseInt("0xFF", 16); // NumberFormatException
Integer.parseInt("FG", 16);   // NumberFormatException
Integer.parseInt("FF ", 16);  // NumberFormatException
~~~

Nếu giao thức cho phép tiền tố `0x`, hãy bỏ tiền tố **theo quy tắc được định nghĩa rõ** trước khi parse:

~~~java
static int parseHexInt(String text) {
    if (text == null) {
        throw new IllegalArgumentException("Giá trị hex không được null");
    }

    String digits = text.startsWith("0x") || text.startsWith("0X")
            ? text.substring(2)
            : text;

    if (digits.isEmpty()) {
        throw new IllegalArgumentException("Thiếu chữ số hex");
    }
    return Integer.parseInt(digits, 16);
}
~~~

Đoạn code này không trim khoảng trắng và không chấp nhận dấu. Đó là một lựa chọn contract có chủ đích; nếu muốn cho phép các dạng đó, cần thêm quy tắc riêng.

### 3.2. Phân biệt số nguyên có dấu và cách diễn giải bit unsigned

Một chuỗi 8 chữ số hex như `FFFFFFFF` biểu diễn 32 bit tất cả đều là 1. Nếu parse bằng `Integer.parseInt`, giá trị vượt phạm vi `Integer.MAX_VALUE` nên bị từ chối:

~~~java
// Ném NumberFormatException:
// int value = Integer.parseInt("FFFFFFFF", 16);
~~~

Nếu muốn diễn giải 32 bit đó như **số nguyên không dấu**, dùng `Integer.parseUnsignedInt`:

~~~java
int bits = Integer.parseUnsignedInt("FFFFFFFF", 16);

System.out.println(bits); // -1: cách Java lưu bit pattern trong int có dấu
System.out.println(Integer.toUnsignedString(bits)); // 4294967295
System.out.println(Integer.toHexString(bits)); // ffffffff
~~~

`int` của Java vẫn là kiểu có dấu. `parseUnsignedInt` cho phép đọc miền unsigned 32-bit và trả lại cùng bit pattern trong kiểu `int`; khi hiển thị số lượng không dấu, dùng `Integer.toUnsignedString` hoặc `Integer.toUnsignedLong`.

Tương tự, `Long.parseUnsignedLong(text, 16)` có thể đọc giá trị unsigned 64-bit và giữ bit pattern trong `long`. Cần chọn API theo **ý nghĩa số học** của dữ liệu, không chỉ theo số chữ số hex.

### 3.3. Chuyển số nguyên thành chuỗi hex

Các method tiện dụng:

~~~java
String a = Integer.toHexString(255); // "ff"
String b = Long.toHexString(255L);   // "ff"
String c = Integer.toHexString(16);  // "10"
~~~

`toHexString`:

- Trả chữ thường.
- Không thêm tiền tố `0x`.
- Không đảm bảo độ rộng cố định hoặc số 0 ở đầu.
- Với số âm, trả biểu diễn bit của kiểu nguyên thủy tương ứng, không phải chuỗi có dấu trừ.

Ví dụ:

~~~java
System.out.println(Integer.toHexString(15));  // f
System.out.println(Integer.toHexString(-1));  // ffffffff
~~~

Nếu cần độ rộng cố định, có thể dùng định dạng:

~~~java
int value = 15;
String twoDigits = String.format("%02X", value);
System.out.println(twoDigits); // 0F
~~~

Với một byte, cần nhớ byte Java có dấu; dùng `b & 0xff` để lấy giá trị unsigned trước khi định dạng:

~~~java
byte b = (byte) 0xA7;
String hex = String.format("%02X", b & 0xff);
System.out.println(hex); // A7
~~~

Trong Java 17, nếu mục tiêu là chuyển cả mảng byte sang chuỗi hex, `HexFormat` thường rõ ràng hơn việc tự viết vòng lặp format.

## 4. Đọc byte từ hai ký tự hex

### 4.1. Một byte gồm hai nibble

Giả sử có chuỗi `"A7"`:

~~~text
'A' -> 10 -> 1010 (nibble cao)
'7' ->  7 -> 0111 (nibble thấp)

(10 << 4) | 7
= 160 | 7
= 167
= 0xA7
~~~

Code:

~~~java
int high = asciiHexDigit('A');
int low = asciiHexDigit('7');
int unsignedByte = (high << 4) | low;

System.out.println(unsignedByte); // 167
System.out.println(Integer.toHexString(unsignedByte)); // a7
~~~

Biểu thức `(high << 4) | low` ghép nibble cao vào bốn bit cao và nibble thấp vào bốn bit thấp. Trước khi ghép, cả hai nibble phải nằm trong `0..15`; nếu một trong hai là `-1`, kết quả không có ý nghĩa.

### 4.2. Vì sao `Byte.parseByte("FF", 16)` không hoạt động?

`byte` trong Java là số nguyên **có dấu 8 bit**, phạm vi từ -128 đến 127. Chuỗi hex `FF` có giá trị unsigned 255, vượt phạm vi đó:

~~~java
Byte.parseByte("7F", 16); // 127
Byte.parseByte("80", 16); // NumberFormatException
Byte.parseByte("FF", 16); // NumberFormatException
~~~

Nếu cần đọc một byte nhị phân, hãy parse giá trị 0..255 trước rồi chuyển sang bit pattern của `byte`:

~~~java
int unsigned = Integer.parseInt("FF", 16); // 255
byte bits = (byte) unsigned;                // -1

System.out.println(bits);          // -1
System.out.println(bits & 0xff);   // 255
System.out.println(Integer.toHexString(bits & 0xff)); // ff
~~~

Phép ép kiểu `(byte) 255` giữ lại 8 bit thấp `11111111`, được diễn giải là -1 trong Java. Nếu cần biểu diễn byte dưới dạng số không dấu, hãy dùng `bits & 0xff` khi đọc.

### 4.3. Ghép byte và tách nibble

Với một giá trị byte:

~~~java
int value = 0xA7;
int highNibble = (value >>> 4) & 0x0F;
int lowNibble = value & 0x0F;

System.out.println(highNibble); // 10
System.out.println(lowNibble);  // 7
~~~

Với một `byte` có dấu, nên chuyển thành unsigned trước khi dịch:

~~~java
byte raw = (byte) 0xA7;
int unsigned = raw & 0xff;

int high = (unsigned >>> 4) & 0x0f;
int low = unsigned & 0x0f;
~~~

Điều này giúp tránh nhầm lẫn do sign extension khi mở rộng `byte` sang `int`.

## 5. Dùng `HexFormat` trong Java 17

### 5.1. `HexFormat` là API chuẩn từ Java 17

Java 17 có class `java.util.HexFormat` để định dạng và phân tích chuỗi hex. Khi cần chuyển mảng byte thành chuỗi hex hoặc parse chuỗi hex thành byte array, đây thường là lựa chọn dễ đọc và ít lỗi hơn tự viết vòng lặp.

~~~java
import java.util.HexFormat;

public class HexFormatBasic {
    public static void main(String[] args) {
        byte[] data = {
                (byte) 0xCA,
                (byte) 0xFE,
                0x01,
                0x23
        };

        HexFormat hex = HexFormat.of();
        String encoded = hex.formatHex(data);
        byte[] decoded = hex.parseHex(encoded);

        System.out.println(encoded); // cafe0123
        System.out.println(java.util.Arrays.equals(data, decoded)); // true
    }
}
~~~

`HexFormat.of()` tạo formatter mặc định:

- Dùng chữ thường.
- Không có delimiter giữa các byte.
- Không thêm prefix/suffix.
- Mỗi byte được biểu diễn bằng đúng hai chữ số hex.

`HexFormat` là immutable và thread-safe; có thể tái sử dụng một instance đã cấu hình.

### 5.2. Chuyển sang chữ hoa hoặc thêm delimiter

~~~java
import java.util.HexFormat;

byte[] bytes = { 0x01, 0x23, (byte) 0xAB, (byte) 0xFF };

String lower = HexFormat.of().formatHex(bytes);
String upper = HexFormat.of().withUpperCase().formatHex(bytes);
String colon = HexFormat.ofDelimiter(":").formatHex(bytes);
String spaced = HexFormat.ofDelimiter(" ").withUpperCase()
        .formatHex(bytes);

System.out.println(lower);  // 0123abff
System.out.println(upper);  // 0123ABFF
System.out.println(colon);  // 01:23:ab:ff
System.out.println(spaced); // 01 23 AB FF
~~~

Có thể cấu hình prefix và suffix nếu định dạng giao thức cần:

~~~java
HexFormat prefixed = HexFormat.of().withPrefix("0x");
String text = prefixed.formatHex(new byte[] { 0x01, (byte) 0xAF });
~~~

Prefix/suffix/delimiter là một phần của định dạng được cấu hình. Khi parse, phải dùng formatter tương ứng với chính quy tắc đã dùng để tạo chuỗi; không giả định formatter mặc định tự bỏ mọi loại prefix hoặc khoảng trắng.

### 5.3. Parse hex thành byte array

~~~java
import java.util.HexFormat;
import java.util.Arrays;

byte[] bytes = HexFormat.of().parseHex("CAFE0123");

System.out.println(Arrays.toString(bytes));
System.out.println(HexFormat.of().withUpperCase().formatHex(bytes));
~~~

`parseHex` yêu cầu các chữ số ghép thành từng cặp byte. Một chuỗi có số ký tự lẻ không thể tạo thành đầy đủ byte theo định dạng mặc định; chuỗi có ký tự không phải hex cũng bị từ chối bằng `IllegalArgumentException`.

Ví dụ:

~~~java
HexFormat.of().parseHex("ABC");  // IllegalArgumentException: lẻ chữ số
HexFormat.of().parseHex("ABG1"); // IllegalArgumentException: G không phải hex
~~~

Nếu input có delimiter, cấu hình delimiter phù hợp:

~~~java
HexFormat colonHex = HexFormat.ofDelimiter(":");
byte[] data = colonHex.parseHex("CA:FE:01:23");
System.out.println(HexFormat.of().formatHex(data)); // cafe0123
~~~

Không xóa delimiter bằng cách loại bỏ mọi ký tự không phải hex nếu chưa xác định hợp đồng. Cách đó có thể biến đầu vào sai như `"CA:ZZ:FE"` thành một chuỗi khác trông có vẻ hợp lệ sau khi lọc.

### 5.4. Kiểm tra ký tự hex bằng `HexFormat.isHexDigit`

Java 17 cung cấp:

~~~java
System.out.println(HexFormat.isHexDigit('0')); // true
System.out.println(HexFormat.isHexDigit('A')); // true
System.out.println(HexFormat.isHexDigit('f')); // true
System.out.println(HexFormat.isHexDigit('G')); // false
System.out.println(HexFormat.isHexDigit(' ')); // false
~~~

API này phù hợp khi muốn kiểm tra ký tự theo tập chữ số hex ASCII. Nó có thể dùng trong validation trước khi gọi parser hoặc khi tự xây dựng thông báo lỗi có vị trí ký tự.

## 6. Phát hiện đầu vào hex không hợp lệ

### 6.1. Xác định hợp đồng trước khi viết parser

Trước khi parse, cần xác định định dạng đầu vào cho phép những gì:

| Thành phần | Câu hỏi cần quyết định |
|---|---|
| Null | Có được phép không? Nếu không, lỗi nào được trả về? |
| Chuỗi rỗng | Đại diện mảng byte rỗng hay là đầu vào thiếu? |
| Chữ hoa/thường | Có chấp nhận cả hai không? |
| Prefix | Có cho phép `0x`/`0X` không? |
| Khoảng trắng | Có trim hai đầu hoặc cho phép khoảng trắng giữa các byte không? |
| Delimiter | Có cho phép `:`, dấu gạch ngang hoặc khoảng trắng giữa byte không? |
| Số chữ số | Phải chẵn hay cho phép nibble lẻ với quy tắc đệm? |
| Ký tự | Chỉ ASCII hay chấp nhận chữ số Unicode? |
| Độ dài | Có giới hạn số byte để tránh tiêu thụ bộ nhớ quá mức không? |

Một parser an toàn không tự ý đoán định dạng. Nếu API quy định chuỗi hex liền nhau, parser nên từ chối dấu phân cách, prefix và khoảng trắng thay vì tự sửa đầu vào.

### 6.2. Những lỗi thường gặp

| Input | Vấn đề | Hướng xử lý |
|---|---|---|
| `null` | Không có chuỗi để parse | Từ chối hoặc biểu diễn vắng mặt theo contract |
| `""` | Chuỗi rỗng | Quyết định có đại diện mảng rỗng không |
| `"A"` | Một nibble, chưa đủ byte | Từ chối hoặc định nghĩa rõ quy tắc đệm |
| `"ABC"` | Số ký tự lẻ | Từ chối nếu format yêu cầu từng cặp |
| `"G1"` | `G` không phải hex | Báo vị trí ký tự lỗi |
| `"1Z"` | `Z` không phải hex | Báo vị trí ký tự lỗi |
| `"0xFF"` | Prefix không được parser mặc định chấp nhận | Xử lý prefix tường minh nếu contract cho phép |
| `"FF "` | Khoảng trắng cuối | Từ chối hoặc trim nếu contract quy định |
| `"FF:00"` | Delimiter không thuộc định dạng mặc định | Dùng formatter có delimiter tương ứng |
| `"FFFFFFFF"` với `parseInt` | Vượt phạm vi signed int | Dùng API unsigned hoặc kiểu dữ liệu khác |
| `"FF"` với `Byte.parseByte` | 255 vượt phạm vi signed byte | Parse unsigned 0..255 rồi chuyển bit pattern nếu cần |

### 6.3. Phân biệt lỗi cú pháp với lỗi phạm vi

Hai loại lỗi khác nhau:

- **Lỗi cú pháp:** có ký tự không hợp lệ, chuỗi rỗng, số chữ số lẻ, prefix/delimiter sai định dạng.
- **Lỗi phạm vi:** chuỗi có toàn ký tự hex hợp lệ nhưng giá trị không biểu diễn được bằng kiểu số đích.

Ví dụ:

~~~java
Integer.parseInt("GG", 16); // Lỗi cú pháp
Integer.parseInt("FFFFFFFF", 16); // Lỗi phạm vi int có dấu
~~~

Nếu cần thông báo thân thiện cho người dùng, có thể kiểm tra cú pháp trước, rồi parse vào kiểu đủ rộng hoặc dùng API unsigned phù hợp để tách hai loại lỗi.

## 7. Tự viết parser byte array có thông báo lỗi theo vị trí

### 7.1. Quy tắc của parser ví dụ

Giả sử một API nhận chuỗi hex biểu diễn byte array với các điều kiện:

1. Chuỗi không được null.
2. Chuỗi phải có số ký tự chẵn.
3. Chỉ nhận ký tự ASCII `0-9`, `A-F`, `a-f`.
4. Không chấp nhận prefix `0x`, delimiter hoặc khoảng trắng.
5. Chuỗi rỗng đại diện mảng byte rỗng.

Đây là một contract cụ thể. Một API khác có thể chọn quy tắc khác, nhưng phải mô tả rõ.

### 7.2. Cài đặt parser

~~~java
import java.util.Objects;

public class StrictHexParser {

    private static int digitAt(String input, int index) {
        char ch = input.charAt(index);
        int value = asciiHexDigit(ch);

        if (value < 0) {
            throw new IllegalArgumentException(
                    "Ký tự hex không hợp lệ tại vị trí " +
                    index + ": '" + ch + "'"
            );
        }
        return value;
    }

    private static int asciiHexDigit(char ch) {
        if (ch >= '0' && ch <= '9') {
            return ch - '0';
        }
        if (ch >= 'A' && ch <= 'F') {
            return ch - 'A' + 10;
        }
        if (ch >= 'a' && ch <= 'f') {
            return ch - 'a' + 10;
        }
        return -1;
    }

    public static byte[] parse(String input) {
        Objects.requireNonNull(input, "input");

        if ((input.length() & 1) != 0) {
            throw new IllegalArgumentException(
                    "Chuỗi hex phải có số ký tự chẵn"
            );
        }

        byte[] result = new byte[input.length() / 2];

        for (int i = 0; i < input.length(); i += 2) {
            int high = digitAt(input, i);
            int low = digitAt(input, i + 1);
            int value = (high << 4) | low;
            result[i / 2] = (byte) value;
        }

        return result;
    }
}
~~~

Ví dụ sử dụng:

~~~java
byte[] bytes = StrictHexParser.parse("CAFE0123");

for (byte value : bytes) {
    System.out.printf("%02X ", value & 0xff);
}
~~~

Kết quả:

~~~text
CA FE 01 23
~~~

### 7.3. Vì sao phải kiểm tra độ dài trước?

Mỗi byte cần đúng hai nibble. Nếu độ dài lẻ, vòng lặp có thể truy cập `input.charAt(i + 1)` vượt phạm vi ở cặp cuối. Kiểm tra ngay đầu vào:

~~~java
if ((input.length() & 1) != 0) {
    throw new IllegalArgumentException("...");
}
~~~

giúp lỗi có ý nghĩa rõ hơn và tránh xử lý nửa byte không được định nghĩa.

### 7.4. Vì sao phải kiểm tra cả nibble cao và thấp?

Giá trị ghép:

~~~java
int value = (high << 4) | low;
~~~

chỉ đúng nếu `high` và `low` nằm trong `0..15`. Nếu một hàm chuyển ký tự trả `-1` cho ký tự sai mà không kiểm tra, các phép dịch bit và OR vẫn chạy nhưng tạo ra một kết quả không có ý nghĩa. Vì vậy, parser cần từ chối ký tự lỗi **trước khi ghép byte**.

### 7.5. Giới hạn kích thước đầu vào

Trong hệ thống thực tế, một chuỗi có thể rất dài. Trước khi cấp phát:

~~~java
if (input.length() > MAX_HEX_CHARACTERS) {
    throw new IllegalArgumentException("Payload hex quá dài");
}
~~~

Giới hạn phải dựa trên kích thước payload nghiệp vụ, giao thức hoặc tài nguyên cho phép. Nếu parse dữ liệu từ request không đáng tin cậy, giới hạn này giúp tránh cấp phát mảng quá lớn và giảm nguy cơ tiêu thụ bộ nhớ ngoài dự kiến.

## 8. Parse số hex và parse byte array là hai việc khác nhau

Một chuỗi hex có thể được hiểu theo nhiều cách:

- Là **một số nguyên** có dấu hoặc không dấu.
- Là **một dãy byte**.
- Là **một mã định danh** có độ rộng cố định.
- Là **một biểu diễn nhị phân** cho giao thức hoặc dữ liệu mã hóa.

Ví dụ `"FF"`:

| Cách diễn giải | Kết quả |
|---|---|
| `Integer.parseInt("FF", 16)` | số nguyên 255 |
| `Integer.parseUnsignedInt("FF", 16)` | bit pattern của int có giá trị unsigned 255 |
| `HexFormat.of().parseHex("FF")` | byte array có một byte bit pattern `11111111` |
| `Byte.parseByte("FF", 16)` | lỗi vì 255 ngoài phạm vi byte có dấu |
| `Character.digit('F', 16)` | nibble 15 |

Không nên chọn API chỉ dựa trên việc “đầu vào là chuỗi hex”. Hãy xác định kết quả mong muốn là số nguyên, nibble, byte hay byte array.

### 8.1. Đọc byte array thành số nguyên nhiều byte

Giả sử dữ liệu `"0102"` biểu diễn một số nguyên 16-bit big-endian:

~~~java
byte[] bytes = HexFormat.of().parseHex("0102");

int value = ((bytes[0] & 0xff) << 8)
        | (bytes[1] & 0xff);

System.out.println(value); // 258
~~~

Đối với dữ liệu nhiều byte, cần biết rõ **endianness**:

- Big-endian: byte có trọng số cao đứng trước.
- Little-endian: byte có trọng số thấp đứng trước.

Hex string chỉ cho biết thứ tự byte được viết ra; nó không tự nói ý nghĩa byte order của trường số nguyên trong giao thức.

### 8.2. Dùng ByteBuffer khi đọc cấu trúc nhị phân

Với dữ liệu nhị phân có nhiều trường, `ByteBuffer` có thể làm rõ byte order:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.HexFormat;

byte[] bytes = HexFormat.of().parseHex("01020304");

int bigEndian = ByteBuffer.wrap(bytes)
        .order(ByteOrder.BIG_ENDIAN)
        .getInt();

int littleEndian = ByteBuffer.wrap(bytes)
        .order(ByteOrder.LITTLE_ENDIAN)
        .getInt();

System.out.println(bigEndian);    // 16909060
System.out.println(littleEndian); // 67305985
~~~

Chỉ dùng cách này khi độ dài và cấu trúc input đã được kiểm tra. `ByteBuffer.getInt()` yêu cầu đủ bốn byte từ vị trí hiện tại; nếu thiếu, sẽ phát sinh `BufferUnderflowException`.

## 9. Xử lý lỗi đúng cách trong ứng dụng

### 9.1. Không bắt lỗi rồi trả về giá trị giả

Tránh:

~~~java
static int unsafeParse(String input) {
    try {
        return Integer.parseInt(input, 16);
    } catch (NumberFormatException ex) {
        return 0; // Che giấu đầu vào sai
    }
}
~~~

Nếu đầu vào `"G1"` hoặc `"ZZ"` bị chuyển thành 0, hệ thống có thể hiểu nhầm đó là dữ liệu hợp lệ. Giá trị mặc định chỉ nên được dùng nếu hợp đồng nghiệp vụ quy định rõ.

### 9.2. Nêu rõ lỗi và giữ nguyên nguyên nhân

~~~java
static int parseUserHex(String input) {
    if (input == null) {
        throw new IllegalArgumentException("Mã hex không được null");
    }
    if (input.isEmpty()) {
        throw new IllegalArgumentException("Mã hex không được rỗng");
    }

    try {
        return Integer.parseInt(input, 16);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                "Mã hex không hợp lệ: " + input,
                ex
        );
    }
}
~~~

Ở tầng API, có thể bắt `IllegalArgumentException` tại boundary và chuyển thành phản hồi validation phù hợp. Không nên để stack trace nội bộ hoặc dữ liệu nhạy cảm xuất hiện trong thông báo gửi ra ngoài.

### 9.3. Validation trước parse hay dùng parser chuẩn?

Nếu cần thông báo lỗi chi tiết theo vị trí, có thể kiểm tra từng ký tự trước. Nếu chỉ cần biết toàn bộ chuỗi có hợp lệ hay không, `HexFormat.parseHex` hoặc `Integer.parseInt` thường đủ.

Không nên lặp lại toàn bộ parser thư viện nếu không có yêu cầu đặc biệt. Tự viết parser có trách nhiệm về:

- Cặp ký tự và vị trí lỗi.
- Quy tắc ASCII/Unicode.
- Độ dài tối đa.
- Prefix, delimiter và whitespace.
- Tràn số và byte order.
- Tương thích với format của hệ thống khác.

## 10. Các lựa chọn định dạng và chuẩn hóa

### 10.1. Chuỗi hex liên tục

~~~text
CAFE0123
~~~

Ưu điểm: gọn, dễ lưu trong JSON hoặc log. Nhược điểm: với payload dài, con người khó đếm byte và tìm vị trí lỗi.

### 10.2. Dùng dấu hai chấm hoặc khoảng trắng giữa byte

~~~text
CA:FE:01:23
CA FE 01 23
~~~

Ưu điểm: dễ đọc và kiểm tra bằng mắt. Nhược điểm: parser cần thống nhất delimiter, không được tùy tiện bỏ dấu.

### 10.3. Prefix `0x`

~~~text
0xCAFE
~~~

Prefix thường giúp người đọc nhận biết cơ số, nhưng không phải mọi API parse đều chấp nhận nó. `Integer.parseInt("0xFF", 16)` và `HexFormat.of().parseHex("0xFF")` không tự động loại bỏ prefix trong cấu hình mặc định.

Nếu format quy định prefix một lần ở đầu chuỗi, hãy xác thực và loại bỏ đúng một prefix trước khi parse; không xóa mọi ký tự `x` hoặc `0` bằng thao tác thay thế tổng quát.

### 10.4. Chữ hoa hay chữ thường

Hex có thể biểu diễn bằng chữ hoa hoặc chữ thường. Hai cách biểu diễn cùng một byte:

~~~text
ca fe 01 23
CA FE 01 23
~~~

Khi dữ liệu dùng làm chữ ký, hash, cache key hoặc chuỗi so sánh chính xác, nên có **quy tắc canonicalization** (ví dụ chữ thường, không delimiter, không prefix) để tránh hai biểu diễn khác nhau của cùng dữ liệu.

## 11. Bảo mật và dữ liệu đầu vào không đáng tin cậy

Hex thường xuất hiện trong token, digest, key ID, dữ liệu nhị phân, request hoặc file. Validation cần gắn với mục đích sử dụng:

- **Giới hạn độ dài trước khi cấp phát:** tránh payload cực lớn làm tiêu tốn bộ nhớ.
- **Từ chối ký tự ngoài format:** không âm thầm xóa ký tự không hợp lệ.
- **Không trim hoặc chuẩn hóa ngoài hợp đồng:** tránh hai tầng hệ thống hiểu khác nhau một chuỗi.
- **Kiểm tra số byte chính xác:** ví dụ một hash có độ dài cố định cần đúng số byte, không chỉ đúng ký tự hex.
- **Không ghi secret vào log:** nếu chuỗi hex là key, token hoặc credential, tránh đưa toàn bộ vào exception message/log.
- **Phân biệt encoding với encryption:** hex chỉ là cách biểu diễn byte thành ký tự; nó không mã hóa bí mật và không cung cấp tính toàn vẹn.

Ví dụ kiểm tra độ dài digest:

~~~java
import java.util.HexFormat;

static byte[] parseSha256Hex(String input) {
    if (input == null || input.length() != 64) {
        throw new IllegalArgumentException(
                "SHA-256 hex phải có đúng 64 ký tự"
        );
    }

    byte[] bytes = HexFormat.of().parseHex(input);
    if (bytes.length != 32) {
        throw new IllegalArgumentException("Độ dài digest không hợp lệ");
    }
    return bytes;
}
~~~

SHA-256 tạo digest 256 bit, tương ứng 32 byte và 64 chữ số hex. Độ dài đúng không chứng minh digest đúng hoặc đáng tin; việc xác thực cần đối chiếu với giá trị kỳ vọng hoặc quy trình xác minh phù hợp.

## 12. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Ép `(int) 'F'` để lấy giá trị hex | Nhận mã ký tự 70 thay vì 15 | Dùng `Character.digit('F', 16)` |
| Không kiểm tra `Character.digit` trả -1 | Ghép nibble không hợp lệ thành byte sai | Kiểm tra từng digit trước khi shift/OR |
| Dùng `Character.digit` khi protocol chỉ cho ASCII | Có thể chấp nhận ký tự Unicode ngoài contract | Dùng kiểm tra ASCII tường minh hoặc `HexFormat.isHexDigit` |
| Dùng `Integer.parseInt` với prefix `0x` | `NumberFormatException` | Xác thực và bỏ prefix theo contract |
| Gọi `trim()`/lọc ký tự sai mà không có quy tắc | Che giấu input lỗi hoặc thay đổi dữ liệu | Từ chối hoặc xử lý đúng delimiter đã định nghĩa |
| Dùng `Byte.parseByte("FF", 16)` | Lỗi phạm vi signed byte | Parse 0..255 rồi cast nếu cần bit pattern |
| Dùng `Integer.parseInt("FFFFFFFF",16)` | Tràn signed int | Dùng `parseUnsignedInt` khi đúng ngữ nghĩa |
| Quên kiểm tra số chữ số chẵn khi parse byte array thủ công | Lỗi index hoặc nibble lẻ không xác định | Xác thực độ dài trước vòng lặp |
| Không kiểm tra độ dài tối đa | Có thể cấp phát bộ nhớ quá lớn | Áp dụng giới hạn theo giao thức |
| Nhầm hex với encryption | Dữ liệu vẫn đọc được công khai | Dùng cơ chế mật mã đúng mục đích |
| Dùng `HexFormat` mặc định với input có delimiter/prefix | Parser từ chối định dạng | Cấu hình formatter phù hợp và thống nhất hai chiều |
| Quên `& 0xff` khi hiển thị byte | Byte trên 127 được hiển thị thành số âm | Chuyển thành unsigned khi hiển thị |

## 13. Bài tập thực hành

### Bài 1 — Chuyển một ký tự hex

Viết method `int parseNibble(char ch)` dùng `Character.digit(ch, 16)`. Method phải ném `IllegalArgumentException` nếu kết quả âm. Thử các đầu vào `'0'`, `'9'`, `'A'`, `'f'`, `'G'` và khoảng trắng.

Sau đó viết một phiên bản chỉ chấp nhận ASCII bằng `HexFormat.isHexDigit` hoặc kiểm tra khoảng ký tự.

### Bài 2 — Chuyển số thành ký tự hex

Viết `char toHexDigit(int value)` cho miền 0..15. Dùng `Character.forDigit`, trả chữ hoa và từ chối các giá trị -1, 16, 100.

### Bài 3 — Đọc một byte

Viết method nhận hai ký tự hex và trả `byte`. Kiểm tra ký tự đầu/cuối, ghép nibble bằng shift/OR và thử `FF`, `80`, `00`. Giải thích vì sao giá trị in ra của `(byte) 0xFF` là -1 nhưng bit pattern vẫn là 255 unsigned.

### Bài 4 — Parse byte array

Viết parser chỉ nhận chuỗi hex ASCII liền nhau, độ dài chẵn, không prefix, không delimiter, và giới hạn tối đa 4.096 byte. Khi sai, báo vị trí ký tự không hợp lệ hoặc lý do độ dài.

So sánh với `HexFormat.of().parseHex(input)`: trường hợp nào nên dùng thư viện, trường hợp nào cần parser riêng?

### Bài 5 — Định dạng dữ liệu

Cho mảng byte:

~~~java
byte[] data = { 0x01, 0x23, (byte) 0xAB, (byte) 0xFF };
~~~

Tạo bốn chuỗi:

1. Hex chữ thường, liền nhau.
2. Hex chữ hoa, liền nhau.
3. Hex có delimiter `: `.
4. Hex có delimiter là khoảng trắng.

Dùng `HexFormat`, sau đó parse lại từng chuỗi bằng formatter tương ứng và so sánh byte array.

### Bài 6 — Phân biệt lỗi cú pháp và phạm vi

Với `Integer.parseInt(input, 16)`, thử:

- `"G1"`
- `"FFFFFFFF"`
- `"7FFFFFFF"`
- `""`
- `"0xFF"`

Phân loại lỗi cú pháp, lỗi phạm vi và trường hợp hợp lệ. Viết một API unsigned nếu yêu cầu của bạn là đọc đủ 32 bit.

### Bài 7 — Kiểm tra hash đầu vào

Viết hàm parse một chuỗi SHA-256 hex:

- Không null.
- Đúng 64 ký tự ASCII hex.
- Không prefix, delimiter hoặc whitespace.
- Trả byte array 32 byte.

Giải thích vì sao đúng định dạng/độ dài không chứng minh nội dung digest hợp lệ về mặt xác thực.

## 14. Câu hỏi tự kiểm tra

1. Một nibble có bao nhiêu bit và một byte có bao nhiêu chữ số hex?
2. Vì sao `(int) 'A'` khác `Character.digit('A', 16)`?
3. `Character.digit` trả giá trị nào khi ký tự không hợp lệ?
4. Khác biệt giữa `Character.digit` và kiểm tra ASCII tường minh?
5. `Character.forDigit(15, 16)` trả ký tự nào?
6. Vì sao `Integer.parseInt("0xFF", 16)` không tự bỏ prefix?
7. Khác nhau giữa `parseInt` và `parseUnsignedInt` khi đọc `FFFFFFFF`?
8. Vì sao `Byte.parseByte("FF", 16)` ném exception?
9. Vì sao phải dùng `b & 0xff` khi đọc byte như số unsigned?
10. `HexFormat` được cung cấp từ Java nào và giải quyết bài toán gì?
11. Khi nào `HexFormat.parseHex` ném `IllegalArgumentException`?
12. Vì sao chuỗi hex biểu diễn byte array thường cần số ký tự chẵn?
13. Tại sao không nên âm thầm loại bỏ mọi ký tự không phải hex?
14. Endianness ảnh hưởng thế nào khi ghép nhiều byte thành số?
15. Vì sao hex không phải encryption?

## 15. Tài liệu tham khảo

- [Java SE 17 API — HexFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html): API chuẩn từ Java 17 để định dạng, kiểm tra và parse hex.
- [Java SE 17 API — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): `digit`, `forDigit` và quy tắc chuyển ký tự thành giá trị theo radix.
- [Java SE 17 API — Integer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): `parseInt`, `parseUnsignedInt`, `toHexString` và các phương thức unsigned.
- [Java SE 17 API — Byte](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Byte.html): phạm vi và chuyển đổi của kiểu byte có dấu.
- [Java SE 17 API — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): đọc dữ liệu nhị phân theo byte order.
- [Java Language Specification, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/index.html): kiểu nguyên thủy, chuyển đổi số và biểu diễn giá trị trong Java.

Khi xử lý hex, hãy xác định trước bạn đang chuyển **một ký tự thành nibble, một chuỗi thành số nguyên hay một chuỗi thành byte array**. Dùng `Character.digit` hoặc `HexFormat` cho đúng mục đích, kiểm tra độ dài và ký tự theo contract, đồng thời phân biệt số nguyên có dấu với bit pattern unsigned. Validation rõ ràng giúp dữ liệu hex sai bị từ chối ngay tại ranh giới thay vì âm thầm trở thành giá trị khác trong các tầng xử lý phía sau.
