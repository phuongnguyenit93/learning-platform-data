# formatHex và parseHex cho byte array trong Java 17

Java 17 cung cấp lớp `HexFormat` trong package `java.util`. Lớp này chuyển đổi giữa **mảng byte (`byte[]`)** và **chuỗi biểu diễn hệ mười sáu (hexadecimal)** bằng hai phương thức thường dùng:

- `formatHex(byte[])`: định dạng các byte thành chuỗi hex.
- `parseHex(CharSequence)`: phân tích chuỗi hex thành mảng byte.

Hex thường được dùng khi hiển thị dữ liệu nhị phân trong log kỹ thuật, biểu diễn nội dung gói tin, làm việc với byte sequence, mã hóa dữ liệu trong định dạng văn bản hoặc kiểm tra dữ liệu khi debug.

`HexFormat` là API chuẩn từ **Java 17**. Với code nhắm đến Java 17, có thể dùng trực tiếp mà không cần tự viết vòng lặp chuyển từng byte hoặc phụ thuộc thư viện bên ngoài.

## 1. Hệ mười sáu biểu diễn một byte như thế nào?

Một byte có 8 bit. Mỗi chữ số hex biểu diễn 4 bit, vì vậy **một byte được biểu diễn bằng đúng hai chữ số hex**.

| Giá trị byte theo bit | Giá trị thập phân không dấu | Biểu diễn hex |
| --- | ---: | --- |
| `0000 0000` | 0 | `00` |
| `0000 1010` | 10 | `0a` |
| `0111 1111` | 127 | `7f` |
| `1000 0000` | 128 | `80` |
| `1111 1111` | 255 | `ff` |

Một mảng gồm 5 byte như trên có thể được biểu diễn thành chuỗi `000a7f80ff`. Không có dấu phân cách mặc định: hai ký tự đầu là byte thứ nhất, hai ký tự tiếp theo là byte thứ hai, cứ tiếp tục như vậy.

Java khai báo kiểu `byte` là số nguyên có dấu trong khoảng -128 đến 127. Tuy nhiên, khi định dạng một byte thành hex, ta muốn biểu diễn **mẫu bit 8 bit**, không phải viết dấu âm. `HexFormat` xử lý điều này và tạo đúng hai chữ số cho mỗi byte.

## 2. Dùng `HexFormat.of().formatHex()` để chuyển byte array thành chuỗi

Ví dụ đơn giản:

```java
import java.util.HexFormat;

public class FormatBytes {
    public static void main(String[] args) {
        byte[] data = {
                0x00,
                0x0A,
                0x7F,
                (byte) 0x80,
                (byte) 0xFF
        };

        String hex = HexFormat.of().formatHex(data);

        System.out.println(hex);
    }
}
```

Kết quả:

```text
000a7f80ff
```

Giải thích:

- `HexFormat.of()` tạo formatter mặc định.
- `formatHex(data)` chuyển từng byte thành hai chữ số hex.
- Mặc định, chữ số `a` đến `f` được xuất ở dạng chữ thường.
- Mảng `data` không bị thay đổi; phương thức trả về một `String` mới.

Trong ví dụ, các giá trị `0x80` và `0xFF` phải được ép kiểu `(byte)` vì literal số nguyên tương ứng vượt phạm vi dương của `byte`.

### Đổi sang chữ hoa

Nếu cần chuỗi hex viết hoa:

```java
import java.util.HexFormat;

byte[] data = {(byte) 0x0A, (byte) 0xAF};

String lower = HexFormat.of().formatHex(data);
String upper = HexFormat.of().withUpperCase().formatHex(data);

System.out.println(lower); // 0aaf
System.out.println(upper); // 0AAF
```

`withUpperCase()` trả về một `HexFormat` có cấu hình chữ hoa. `HexFormat` là đối tượng bất biến; các phương thức cấu hình như `withUpperCase()` tạo formatter cấu hình mới, không thay đổi formatter ban đầu.

Có thể dùng `withLowerCase()` để chỉ rõ định dạng chữ thường, dù đó cũng là mặc định.

## 3. Dùng `parseHex()` để khôi phục byte array

Chiều ngược lại dùng `parseHex()`:

```java
import java.util.HexFormat;
import java.util.Arrays;

public class ParseBytes {
    public static void main(String[] args) {
        String hex = "000a7f80ff";

        byte[] data = HexFormat.of().parseHex(hex);

        System.out.println(Arrays.toString(data));
    }
}
```

Kết quả:

```text
[0, 10, 127, -128, -1]
```

Vì `byte` trong Java là kiểu có dấu, các byte có bit cao nhất bằng 1 được hiển thị thành số âm. Ví dụ:

- Hex `80` tương ứng mẫu bit `1000 0000`, có giá trị byte Java là -128.
- Hex `ff` tương ứng mẫu bit `1111 1111`, có giá trị byte Java là -1.

Đây không phải lỗi chuyển đổi. Mẫu bit được giữ nguyên; cách hiển thị thập phân của kiểu `byte` là có dấu.

Nếu muốn in giá trị mỗi byte theo khoảng không dấu 0 đến 255, dùng `Byte.toUnsignedInt()`:

```java
for (byte value : data) {
    System.out.println(Byte.toUnsignedInt(value));
}
```

Kết quả:

```text
0
10
127
128
255
```

### Round-trip: định dạng rồi phân tích lại

Một phép kiểm tra quan trọng là chuyển mảng byte thành chuỗi hex rồi phân tích chuỗi đó để thu lại mảng byte ban đầu:

```java
import java.util.Arrays;
import java.util.HexFormat;

public class HexRoundTrip {
    public static void main(String[] args) {
        byte[] original = {
                0x00,
                0x0A,
                0x7F,
                (byte) 0x80,
                (byte) 0xFF
        };

        String hex = HexFormat.of().formatHex(original);
        byte[] restored = HexFormat.of().parseHex(hex);

        System.out.println(hex);
        System.out.println(Arrays.equals(original, restored));
    }
}
```

Kết quả:

```text
000a7f80ff
true
```

Với formatter mặc định, mỗi byte được đổi thành hai chữ số hex và `parseHex()` khôi phục lại đúng các byte đó.

## 4. Ví dụ hoàn chỉnh với `formatHex()` và `parseHex()`

Ví dụ sau gom hai chiều chuyển đổi vào một chương trình:

```java
import java.util.Arrays;
import java.util.HexFormat;

public class HexDemo {

    static String encode(byte[] bytes) {
        return HexFormat.of().formatHex(bytes);
    }

    static byte[] decode(String hex) {
        return HexFormat.of().parseHex(hex);
    }

    public static void main(String[] args) {
        byte[] original = {
                0x01,
                0x23,
                0x45,
                0x67,
                (byte) 0x89,
                (byte) 0xAB,
                (byte) 0xCD,
                (byte) 0xEF
        };

        String encoded = encode(original);
        byte[] decoded = decode(encoded);

        System.out.println("Hex: " + encoded);
        System.out.println("Bytes: " + Arrays.toString(decoded));
        System.out.println(
                "Khôi phục đúng: " + Arrays.equals(original, decoded)
        );
    }
}
```

Kết quả:

```text
Hex: 0123456789abcdef
Bytes: [1, 35, 69, 103, -119, -85, -51, -17]
Khôi phục đúng: true
```

Biên dịch và chạy bằng Java 17:

```bash
javac --release 17 -encoding UTF-8 HexDemo.java
java HexDemo
```

Dùng `--release 17` để trình biên dịch giới hạn cú pháp và API đích ở Java 17. `HexFormat` là API có sẵn từ phiên bản này.

## 5. Tùy chỉnh delimiter, prefix, suffix và chữ hoa/thường

Mặc định, `formatHex()` nối các byte liền nhau. Trong một số trường hợp, chuỗi có dấu phân cách sẽ dễ đọc hơn, chẳng hạn khi hiển thị địa chỉ phần cứng, byte của gói tin hoặc dữ liệu kiểm tra.

Dùng `withDelimiter()`:

```java
import java.util.HexFormat;

public class HexDelimiter {
    public static void main(String[] args) {
        byte[] data = {
                0x00,
                0x0A,
                0x7F,
                (byte) 0x80,
                (byte) 0xFF
        };

        HexFormat format = HexFormat.of()
                .withDelimiter(":")
                .withUpperCase();

        String hex = format.formatHex(data);

        System.out.println(hex);
    }
}
```

Kết quả:

```text
00:0A:7F:80:FF
```

Có thể cấu hình thêm prefix và suffix:

```java
HexFormat format = HexFormat.of()
        .withDelimiter(" ")
        .withPrefix("0x")
        .withUpperCase();

String hex = format.formatHex(
        new byte[] {0x01, 0x02, (byte) 0xAF}
);

System.out.println(hex);
```

Kết quả:

```text
0x01 0x02 0xAF
```

Trong cấu hình này:

- `withDelimiter(" ")` đặt một dấu cách giữa các byte.
- `withPrefix("0x")` thêm tiền tố vào từng byte.
- `withUpperCase()` định dạng chữ số hex ở dạng hoa.

`withSuffix()` cũng cho phép đặt hậu tố cho từng byte khi định dạng. Prefix, suffix và delimiter là một phần của cấu hình formatter, vì vậy cần dùng formatter có cấu hình tương ứng khi phân tích chuỗi.

### Phân tích lại chuỗi có delimiter

Dùng chính formatter đã tạo để parse:

```java
import java.util.HexFormat;
import java.util.Arrays;

public class ParseDelimitedHex {
    public static void main(String[] args) {
        HexFormat format = HexFormat.of()
                .withDelimiter(":")
                .withUpperCase();

        String text = "00:0A:7F:80:FF";

        byte[] bytes = format.parseHex(text);

        System.out.println(Arrays.toString(bytes));
        System.out.println(format.formatHex(bytes));
    }
}
```

Kết quả:

```text
[0, 10, 127, -128, -1]
00:0A:7F:80:FF
```

Nếu chuỗi được tạo bằng delimiter `:`, không nên dùng formatter mặc định để parse vì formatter mặc định mong đợi các cặp hex nối liền nhau. Hãy giữ cấu hình formatter thống nhất giữa hai chiều.

## 6. `parseHex()` xử lý dữ liệu không hợp lệ như thế nào?

`parseHex()` yêu cầu chuỗi đầu vào tuân theo định dạng của formatter. Mỗi byte phải có đủ hai chữ số hex và các delimiter/prefix/suffix phải đúng với cấu hình.

Ví dụ:

```java
import java.util.HexFormat;

public class InvalidHex {
    public static void main(String[] args) {
        HexFormat format = HexFormat.of();

        byte[] a = format.parseHex("0a");   // Hợp lệ
        byte[] b = format.parseHex("0AFF"); // Hợp lệ

        // Các dòng sau gây IllegalArgumentException:
        // format.parseHex("0");    // Thiếu một chữ số của byte
        // format.parseHex("0G");   // G không phải chữ số hex
        // format.parseHex("0a:ff");// Formatter mặc định không có delimiter ":"
    }
}
```

Các lỗi thường gặp:

| Đầu vào | Vấn đề |
| --- | --- |
| `0` | Số chữ số lẻ, không tạo thành byte đầy đủ. |
| `0G` | `G` không phải chữ số hệ mười sáu. |
| `0a:ff` với formatter mặc định | Có delimiter `:` nhưng formatter không được cấu hình delimiter này. |
| `0x0a` với formatter mặc định | Có prefix `0x` nhưng formatter không mong đợi prefix đó. |
| `0A:0B` với formatter không có delimiter | Cấu trúc không khớp formatter. |

Khi chuỗi không tuân theo định dạng, `parseHex()` ném `IllegalArgumentException`. Nếu dữ liệu có thể đến từ mạng, tệp hoặc người dùng, hãy bắt ngoại lệ ở ranh giới thích hợp và xử lý như dữ liệu đầu vào không hợp lệ.

Không nên tự bỏ mọi ký tự lạ khỏi chuỗi trước khi parse, vì thao tác đó có thể làm dữ liệu sai định dạng bị diễn giải thành một giá trị khác mà người gửi không chủ định.

## 7. Chuyển đổi một phần mảng bằng chỉ số

Khi chỉ cần định dạng một đoạn của byte array, có thể dùng overload nhận `fromIndex` và `toIndex`:

```java
import java.util.HexFormat;

public class HexSlice {
    public static void main(String[] args) {
        byte[] packet = {
                0x10, 0x20, 0x30, 0x40, 0x50
        };

        String header = HexFormat.of().formatHex(packet, 0, 2);
        String payload = HexFormat.of().formatHex(packet, 2, 5);

        System.out.println(header);
        System.out.println(payload);
    }
}
```

Kết quả:

```text
1020
304050
```

Khoảng chỉ số dùng dạng **đầu bao gồm, cuối không bao gồm**: `fromIndex` được lấy, còn `toIndex` không được lấy. Ví dụ `(packet, 2, 5)` xử lý các vị trí 2, 3 và 4.

`parseHex()` cũng có overload nhận chuỗi cùng khoảng chỉ số:

```java
import java.util.HexFormat;
import java.util.Arrays;

public class ParseHexSlice {
    public static void main(String[] args) {
        String input = "xx00aaffyy";

        byte[] bytes = HexFormat.of().parseHex(input, 2, 8);

        System.out.println(Arrays.toString(bytes));
    }
}
```

Kết quả:

```text
[0, -86, -1]
```

Khoảng ký tự từ chỉ số 2 đến trước chỉ số 8 là `00aaff`, gồm ba byte. Hai ký tự `xx` và `yy` ở ngoài đoạn được chọn nên không được parse.

Các chỉ số phải nằm trong phạm vi hợp lệ của mảng hoặc chuỗi. Nếu truyền chỉ số sai, phương thức ném ngoại lệ chỉ số phù hợp. Chỉ dùng overload đoạn khi thực sự cần xử lý một phần dữ liệu; với toàn bộ mảng hoặc chuỗi, overload đơn giản dễ đọc hơn.

## 8. Byte có dấu và lỗi sign extension khi tự chuyển đổi

Một lý do nên dùng `HexFormat` là tránh các lỗi khi tự chuyển byte âm thành chuỗi hex.

Trong Java, khi một giá trị `byte` được mở rộng sang `int`, dấu của nó được giữ. Ví dụ:

```java
byte value = (byte) 0xFF;

System.out.println(value); // -1
System.out.println(Integer.toHexString(value));
```

Kết quả dòng thứ hai có thể là:

```text
ffffffff
```

Lý do: `value` được mở rộng dấu thành `int` -1, có mẫu bit 32 bit toàn 1. `Integer.toHexString()` định dạng cả 32 bit đó, nên kết quả là tám chữ `f`, thay vì hai chữ số `ff` cần cho một byte.

Có thể xử lý thủ công bằng cách chuyển sang số không dấu 8 bit trước:

```java
byte value = (byte) 0xFF;

String hex = Integer.toHexString(Byte.toUnsignedInt(value));

System.out.println(hex); // ff
```

Nhưng khi xử lý cả mảng, `HexFormat.of().formatHex(bytes)` đơn giản và ít rủi ro hơn:

```java
byte[] data = {(byte) 0x80, (byte) 0xFF};

System.out.println(HexFormat.of().formatHex(data)); // 80ff
```

Không cần tự mask từng byte bằng `& 0xFF` khi dùng `HexFormat`.

## 9. Hex khác với văn bản và charset

Một byte array có thể chứa dữ liệu nhị phân hoặc các byte mã hóa văn bản. Chuỗi hex chỉ là **một cách biểu diễn các byte**; nó không tự xác định văn bản gốc.

Nếu muốn chuyển chuỗi Java thành hex, trước tiên phải chọn charset để biến văn bản thành byte:

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class TextToHex {
    public static void main(String[] args) {
        String message = "Hello Java 17";

        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
        String hex = HexFormat.of().formatHex(bytes);

        byte[] restoredBytes = HexFormat.of().parseHex(hex);
        String restoredText = new String(
                restoredBytes,
                StandardCharsets.UTF_8
        );

        System.out.println(hex);
        System.out.println(restoredText);
    }
}
```

Kết quả:

```text
48656c6c6f204a617661203137
Hello Java 17
```

Luồng chuyển đổi là:

```text
String
  |
  | getBytes(StandardCharsets.UTF_8)
  v
byte[]
  |
  | HexFormat.formatHex(...)
  v
Chuỗi hex
  |
  | HexFormat.parseHex(...)
  v
byte[]
  |
  | new String(bytes, StandardCharsets.UTF_8)
  v
String ban đầu
```

Phải dùng cùng charset ở hai chiều. Nếu mã hóa bằng UTF-8 nhưng giải mã bằng một charset khác, chuỗi kết quả có thể bị sai ký tự.

Không dùng `new String(bytes)` mà bỏ qua charset trong ví dụ cần kết quả nhất quán giữa các máy. Hãy chỉ rõ `StandardCharsets.UTF_8` hoặc charset phù hợp với định dạng dữ liệu.

### Hex không phải mã hóa bảo mật

Chuyển byte thành hex **không phải encryption**. Bất kỳ ai có chuỗi hex đều có thể dùng `parseHex()` để lấy lại byte ban đầu.

- Hex encoding: biểu diễn byte bằng ký tự dễ truyền/đọc hơn.
- Encryption: biến đổi dữ liệu bằng thuật toán và khóa để hạn chế người không có khóa đọc được.
- Hashing: tạo giá trị băm một chiều theo thuật toán; không thể khôi phục dữ liệu gốc chỉ bằng cách “giải mã”.

Không lưu mật khẩu bằng cách chuyển mật khẩu thành hex. Với mật khẩu, dùng thuật toán băm mật khẩu chuyên dụng có salt và work factor phù hợp. Hex chỉ có thể là cách biểu diễn kết quả byte của một phép xử lý khác.

## 10. Xử lý mảng rỗng và đầu vào null

Mảng rỗng là dữ liệu hợp lệ:

```java
byte[] empty = {};

String hex = HexFormat.of().formatHex(empty);
byte[] restored = HexFormat.of().parseHex(hex);

System.out.println("[" + hex + "]");
System.out.println(restored.length);
```

Kết quả:

```text
[]
0
```

Chuỗi hex rỗng tương ứng với mảng byte rỗng. Đây là hành vi hữu ích khi xử lý trường dữ liệu có độ dài bằng 0.

Cần phân biệt mảng rỗng với tham chiếu `null`. `HexFormat` không biến `null` thành mảng rỗng; truyền tham chiếu null vào phương thức sẽ gây `NullPointerException`. Nếu API của bạn cho phép null, hãy quyết định rõ chính sách trước khi gọi:

```java
import java.util.HexFormat;
import java.util.Objects;

static String encode(byte[] bytes) {
    Objects.requireNonNull(bytes, "bytes không được null");
    return HexFormat.of().formatHex(bytes);
}
```

Dùng `Objects.requireNonNull()` giúp thông báo lỗi rõ ngay tại biên của API. Nếu nghiệp vụ xem null là không có dữ liệu, có thể biểu diễn riêng bằng `Optional` hoặc một quy ước rõ ràng khác; không nên âm thầm nhầm null với mảng rỗng.

## 11. Dùng lại formatter cấu hình sẵn

`HexFormat` là immutable và thread-safe, nên có thể giữ formatter dùng chung trong một hằng số:

```java
import java.util.HexFormat;

public final class HexCodec {
    private static final HexFormat HEX = HexFormat.of();

    private HexCodec() {
    }

    public static String encode(byte[] bytes) {
        return HEX.formatHex(bytes);
    }

    public static byte[] decode(String hex) {
        return HEX.parseHex(hex);
    }
}
```

Nếu định dạng giao tiếp cần delimiter và chữ hoa, có thể khai báo cấu hình riêng:

```java
private static final HexFormat PACKET_HEX = HexFormat.of()
        .withDelimiter(":")
        .withUpperCase();
```

Giữ cấu hình ở một nơi giúp tránh trường hợp một phần ứng dụng tạo chuỗi theo kiểu có dấu phân cách nhưng phần khác lại parse bằng formatter mặc định.

Tên hằng số và chính sách định dạng nên thể hiện rõ mục đích. Ví dụ, formatter cho log debug có thể khác formatter của một giao thức hoặc định dạng tệp.

## 12. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `cannot find symbol: HexFormat` | Đang biên dịch với JDK/API đích cũ hơn Java 17 hoặc import thiếu. | Dùng JDK hỗ trợ `--release 17` và `import java.util.HexFormat;`. |
| `IllegalArgumentException` khi parse | Có ký tự không phải hex, thiếu chữ số, delimiter hoặc prefix không đúng cấu hình. | Kiểm tra dữ liệu đầu vào và dùng đúng formatter đã tạo chuỗi. |
| Kết quả có `ff` nhưng `byte` in thành `-1` | `byte` trong Java là số có dấu. | Dùng `Byte.toUnsignedInt()` nếu muốn hiển thị số 0–255. |
| Tự chuyển byte âm ra `ffffffff` | Byte được mở rộng dấu thành `int` trước khi gọi `Integer.toHexString`. | Dùng `HexFormat`, hoặc chuyển bằng `Byte.toUnsignedInt` nếu có lý do phải tự xử lý. |
| Parse chuỗi có dấu `:` thất bại | Formatter mặc định không dùng delimiter đó. | Dùng `HexFormat.ofDelimiter(":")` khi parse. |
| Parse chuỗi có `0x` thất bại | Formatter không được cấu hình prefix. | Dùng formatter có `withPrefix("0x")` tương ứng. |
| Chuỗi sau parse thành văn bản bị lỗi dấu | Dùng charset không thống nhất hoặc byte ban đầu không phải dữ liệu văn bản của charset đó. | Chọn charset rõ ràng, ví dụ UTF-8, ở cả encode và decode văn bản. |
| Nghĩ rằng hex bảo vệ dữ liệu bí mật | Nhầm encoding với encryption hoặc hashing. | Dùng cơ chế bảo mật đúng mục đích; hex không che giấu dữ liệu. |

## 13. Bài thực hành

### Bài 1 — chuyển mảng byte thành hex

Tạo mảng:

```java
byte[] data = {
        0x01,
        0x02,
        0x0A,
        (byte) 0xFE
};
```

Dùng `HexFormat.of().formatHex(data)` để tạo chuỗi hex. Dự đoán kết quả trước khi chạy chương trình.

### Bài 2 — parse và so sánh mảng byte

Cho chuỗi `"deadbeef"`. Hãy:

1. Parse thành `byte[]`.
2. In mảng bằng `Arrays.toString()`.
3. Định dạng ngược lại bằng `formatHex()`.
4. So sánh chuỗi kết quả với chuỗi ban đầu (không phân biệt hoa/thường nếu bạn đã đổi kiểu chữ).

### Bài 3 — formatter có delimiter

Tạo formatter có delimiter `:` và chữ hoa. Chuyển `{0x01, 0x02, 0x03}` thành chuỗi. Sau đó dùng chính formatter để parse lại và kiểm tra `Arrays.equals()`.

### Bài 4 — xử lý dữ liệu không hợp lệ

Thử parse các chuỗi:

- `"1"`
- `"0G"`
- `"00:ff"` bằng formatter mặc định.
- `"00:FF"` bằng formatter delimiter `:`.

Xác định trường hợp nào parse thành công và trường hợp nào ném `IllegalArgumentException`.

### Bài 5 — chuyển văn bản qua UTF-8 và hex

Chuyển chuỗi `"Java 17"` thành byte bằng `StandardCharsets.UTF_8`, định dạng thành hex rồi parse trở lại. Dùng cùng UTF-8 để dựng chuỗi cuối và so sánh với chuỗi ban đầu.

## 14. Ghi nhớ nhanh

| Nhu cầu | Cách dùng |
| --- | --- |
| Byte array sang chuỗi hex | `HexFormat.of().formatHex(bytes)` |
| Chuỗi hex sang byte array | `HexFormat.of().parseHex(hex)` |
| Định dạng chữ hoa | `HexFormat.of().withUpperCase()` |
| Định dạng chữ thường | `HexFormat.of().withLowerCase()` |
| Thêm delimiter | `HexFormat.ofDelimiter(":")` hoặc `withDelimiter()` |
| Thêm prefix/suffix | `withPrefix()` và `withSuffix()` |
| Định dạng một đoạn byte array | `formatHex(bytes, fromIndex, toIndex)` |
| Parse một đoạn chuỗi | `parseHex(text, fromIndex, toIndex)` |
| Hiển thị byte theo số không dấu | `Byte.toUnsignedInt(value)` |
| Chuyển văn bản sang byte | `text.getBytes(StandardCharsets.UTF_8)` |
| Chuyển byte thành văn bản | `new String(bytes, StandardCharsets.UTF_8)` |

**Nguyên tắc cốt lõi:** Trong Java 17, dùng `HexFormat` để chuyển byte array sang chuỗi hex và parse trở lại. `formatHex()` tạo biểu diễn hai chữ số cho mỗi byte; `parseHex()` khôi phục mẫu bit từ chuỗi đúng định dạng. Nếu dữ liệu là văn bản, hãy xác định charset riêng; nếu dữ liệu cần bí mật, hãy dùng cơ chế mã hóa phù hợp vì hex chỉ là biểu diễn, không phải bảo mật.
