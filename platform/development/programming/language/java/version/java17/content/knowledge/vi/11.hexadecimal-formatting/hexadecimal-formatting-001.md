# Vai trò của HexFormat trong xử lý byte và văn bản trong Java 17

Khi làm việc với dữ liệu nhị phân, lập trình viên thường cần xem một mảng byte dưới dạng chuỗi ký tự dễ đọc, chẳng hạn `48656c6c6f`, `48:65:6C:6C:6F` hoặc `0x48 0x65 0x6c`. Java 17 cung cấp lớp **`java.util.HexFormat`** để thực hiện việc chuyển đổi giữa **byte và biểu diễn hexadecimal (hệ mười sáu)** một cách thống nhất.

`HexFormat` được bổ sung trong JDK 17. Lớp này giúp:

- Chuyển `byte[]` thành chuỗi hex bằng `formatHex(...)`.
- Chuyển chuỗi hex trở lại `byte[]` bằng `parseHex(...)`.
- Chọn chữ hoa hoặc chữ thường cho chữ số hex.
- Cấu hình dấu phân cách, tiền tố và hậu tố cho từng byte.
- Chỉ xử lý một đoạn của mảng byte hoặc chuỗi đầu vào khi cần.

Hexadecimal là **cách biểu diễn dữ liệu**, không phải mã hóa bảo mật. Một chuỗi hex có thể đổi ngược về đúng các byte ban đầu; ai có chuỗi đó đều có thể khôi phục dữ liệu. Vì vậy, `HexFormat` hữu ích khi debug, log, hiển thị byte, kiểm tra hash, làm việc với giao thức nhị phân hoặc biểu diễn dữ liệu trong tài liệu.

## 1. Hexadecimal và mối liên hệ với byte

Một byte có 8 bit, nên có 256 mẫu bit khác nhau, từ `00000000` đến `11111111`. Một chữ số hexadecimal biểu diễn được 4 bit:

| Hex | Nhị phân | Giá trị thập phân |
| --- | --- | ---: |
| `0` | `0000` | 0 |
| `1` | `0001` | 1 |
| `9` | `1001` | 9 |
| `A` | `1010` | 10 |
| `B` | `1011` | 11 |
| `C` | `1100` | 12 |
| `D` | `1101` | 13 |
| `E` | `1110` | 14 |
| `F` | `1111` | 15 |

Do một byte có 8 bit, nó được biểu diễn bằng **hai chữ số hex**. Ví dụ:

| Byte (nhị phân) | Hex | Thập phân không dấu |
| --- | --- | ---: |
| `0000 0000` | `00` | 0 |
| `0000 1010` | `0A` | 10 |
| `0100 1000` | `48` | 72 |
| `0111 1111` | `7F` | 127 |
| `1000 0000` | `80` | 128 |
| `1111 1111` | `FF` | 255 |

Trong Java, kiểu `byte` là số nguyên có dấu 8 bit, có miền giá trị từ -128 đến 127. Tuy nhiên, khi biểu diễn byte dưới dạng hex, ta quan tâm đến **mẫu 8 bit** của nó. Vì vậy:

- `byte` có giá trị `72` được biểu diễn là `48`.
- `byte` có giá trị `-1` có mẫu bit `11111111`, được biểu diễn là `FF` hoặc `ff`.
- Mỗi byte luôn tạo hai chữ số hex, kể cả khi byte nhỏ hơn `0x10` như `0A`.

Ví dụ một dãy byte:

```text
Byte:  0x48  0x65  0x6C  0x6C  0x6F
ASCII:   H     e     l     l     o
Text:  Hello
Hex:   48 65 6c 6c 6f
```

Hex giúp nhìn thấy chính xác byte đang được truyền hoặc lưu. Nó không tự nói lên dữ liệu đó là văn bản, ảnh, số nguyên, khóa hay một cấu trúc giao thức; cách diễn giải phụ thuộc định dạng của ứng dụng.

## 2. HexFormat trong Java 17

Lớp nằm trong package `java.util`:

```java
import java.util.HexFormat;
```

Để dùng cách mặc định:

```java
HexFormat hex = HexFormat.of();
```

`HexFormat.of()` tạo một formatter mặc định:

- Dùng chữ số hex **chữ thường** (`a` đến `f`).
- Không thêm dấu phân cách giữa các byte.
- Không thêm tiền tố hoặc hậu tố cho byte.

Ví dụ:

```java
import java.util.HexFormat;

public class HexFormatBasic {
    public static void main(String[] args) {
        byte[] bytes = {0x48, 0x65, 0x6C, 0x6C, 0x6F};

        HexFormat hex = HexFormat.of();
        String encoded = hex.formatHex(bytes);

        System.out.println(encoded);
    }
}
```

Kết quả:

```text
48656c6c6f
```

`formatHex` ghép hai chữ số hex của từng byte theo thứ tự mảng. Mảng có 5 byte tạo ra chuỗi có 10 ký tự hex. Nếu mảng rỗng, kết quả là chuỗi rỗng.

## 3. Chuyển byte[] thành chuỗi hex bằng formatHex

### 3.1. Chuyển toàn bộ mảng

Phương thức thường dùng nhất:

```java
String hexText = HexFormat.of().formatHex(bytes);
```

Mỗi byte được chuyển thành hai ký tự hex. Thứ tự byte trong mảng được giữ nguyên; `HexFormat` không đảo byte theo endian.

```java
byte[] data = {
        0x00, 0x01, 0x0A, 0x10, 0x7F, (byte) 0x80, (byte) 0xFF
};

String text = HexFormat.of().formatHex(data);
System.out.println(text);
```

Kết quả:

```text
00010a107f80ff
```

Hai điểm đáng chú ý:

1. Byte `0x0A` được viết đủ `0a`, không bị rút thành `a`.
2. Các giá trị hex từ `0x80` đến `0xFF` cần ép kiểu `(byte)` khi viết literal lớn hơn miền dương của `byte`.

### 3.2. Chỉ chuyển một đoạn mảng

Nếu chỉ cần một vùng dữ liệu, có thể chỉ định chỉ số bắt đầu và kết thúc:

```java
byte[] packet = {
        0x01, 0x02, 0x48, 0x65, 0x6C, 0x6C, 0x6F, 0x7F
};

String payloadHex = HexFormat.of().formatHex(packet, 2, 7);
System.out.println(payloadHex);
```

Kết quả:

```text
48656c6c6f
```

Phạm vi được tính theo quy tắc **`fromIndex` inclusive, `toIndex` exclusive**:

- Bắt đầu lấy tại vị trí `fromIndex`.
- Dừng trước vị trí `toIndex`.
- Độ dài phần được chuyển là `toIndex - fromIndex`.

Trong ví dụ, vị trí `2` được lấy, vị trí `7` không được lấy. Phương thức kiểm tra giới hạn mảng; chỉ số âm, chỉ số vượt quá độ dài hoặc khoảng chỉ số không hợp lệ sẽ gây `IndexOutOfBoundsException`.

### 3.3. Ghi kết quả vào Appendable

Ngoài việc trả về một `String`, `HexFormat` còn có overload ghi vào một `Appendable`:

```java
import java.io.IOException;
import java.util.HexFormat;

public class HexAppendable {
    public static void main(String[] args) throws IOException {
        byte[] bytes = {0x01, 0x23, (byte) 0xFE};
        StringBuilder output = new StringBuilder();

        HexFormat.of().formatHex(output, bytes);
        System.out.println(output);
    }
}
```

Kết quả:

```text
0123fe
```

`StringBuilder` triển khai `Appendable`, nên có thể dùng để ghép kết quả vào nội dung đang xây dựng. Cách này hữu ích khi cần ghi nối tiếp nhiều vùng byte vào cùng một bộ đệm, thay vì tạo nhiều chuỗi trung gian. Overload nhận `Appendable` có thể ném `IOException` theo hợp đồng của `Appendable`.

## 4. Chuyển chuỗi hex trở lại byte bằng parseHex

Chuyển đổi theo chiều ngược lại dùng `parseHex(...)`:

```java
byte[] bytes = HexFormat.of().parseHex("48656c6c6f");
```

Ví dụ hoàn chỉnh:

```java
import java.util.Arrays;
import java.util.HexFormat;

public class HexParseBasic {
    public static void main(String[] args) {
        String encoded = "48656c6c6f";
        byte[] bytes = HexFormat.of().parseHex(encoded);

        System.out.println(Arrays.toString(bytes));
        System.out.println(HexFormat.of().formatHex(bytes));
    }
}
```

Kết quả:

```text
[72, 101, 108, 108, 111]
48656c6c6f
```

Các byte trong mảng được hiển thị dưới dạng số có dấu bởi `Arrays.toString(byte[])`; điều đó không làm thay đổi mẫu bit của byte. Để hiển thị theo hex, dùng `formatHex`.

### 4.1. Chuỗi đầu vào phải có số chữ số phù hợp

Mỗi byte tương ứng với hai chữ số hex. Vì vậy chuỗi hex mặc định phải có **số ký tự chẵn**:

```java
byte[] valid = HexFormat.of().parseHex("0a7f"); // 2 byte

// Chuỗi lẻ ký tự không thể chia thành các cặp byte:
// byte[] invalid = HexFormat.of().parseHex("abc");
```

Nếu chuỗi có ký tự không phải chữ số hex, hoặc cấu trúc delimiter/prefix/suffix không đúng với formatter, `parseHex` ném `IllegalArgumentException`. Không nên bỏ qua ngoại lệ rồi giả định dữ liệu đã được giải mã đầy đủ.

### 4.2. Phân biệt chữ hoa và chữ thường khi parse

Hexadecimal cho phép cả `a`–`f` và `A`–`F`. Formatter mặc định tạo chữ thường, nhưng parser có thể đọc chữ số hex viết hoa hoặc viết thường:

```java
import java.util.Arrays;
import java.util.HexFormat;

HexFormat hex = HexFormat.of();

byte[] lower = hex.parseHex("0aff");
byte[] upper = hex.parseHex("0AFF");

System.out.println(Arrays.equals(lower, upper)); // true
```

`withUpperCase()` và `withLowerCase()` quyết định cách **format** chữ cái hex. Chúng không biến hai biểu diễn hex hợp lệ thành hai bộ byte khác nhau.

### 4.3. Parse một đoạn chuỗi

Có thể chỉ parse một đoạn của `CharSequence`:

```java
String frame = "HDR:48656c6c6f:END";

// Phạm vi [4, 14) là chuỗi "48656c6c6f".
byte[] payload = HexFormat.of().parseHex(frame, 4, 14);

System.out.println(new String(
        payload, java.nio.charset.StandardCharsets.UTF_8
));
```

Kết quả:

```text
Hello
```

Đây là thao tác trên đoạn ký tự của chuỗi nguồn; các vị trí `fromIndex` và `toIndex` vẫn theo quy tắc bắt đầu được lấy, kết thúc không được lấy. Đoạn được parse phải chứa một chuỗi hex hợp lệ theo cấu hình của `HexFormat`.

## 5. Tùy chỉnh chữ hoa và chữ thường

Mặc định `HexFormat.of()` sử dụng chữ thường. Có thể tạo formatter chữ hoa:

```java
HexFormat lower = HexFormat.of();
HexFormat upper = HexFormat.of().withUpperCase();

byte[] bytes = {0x0A, 0x2B, (byte) 0xCD};

System.out.println(lower.formatHex(bytes));
System.out.println(upper.formatHex(bytes));
```

Kết quả:

```text
0a2bcd
0A2BCD
```

`withUpperCase()` và `withLowerCase()` trả về một `HexFormat` được cấu hình tương ứng. Các formatter là đối tượng bất biến; có thể giữ formatter đã cấu hình trong hằng số `static final` để dùng lại.

```java
private static final HexFormat HEX_UPPER =
        HexFormat.of().withUpperCase();
```

Chữ hoa hay chữ thường chỉ là quy ước hiển thị. Hai chuỗi `0a2bcd` và `0A2BCD` biểu diễn cùng dãy byte.

## 6. Thêm delimiter, prefix và suffix

Trong log hoặc tài liệu kỹ thuật, chuỗi hex liền nhau có thể khó đọc. `HexFormat` cho phép cấu hình:

- **Delimiter:** chuỗi phân cách giữa các byte.
- **Prefix:** chuỗi đứng trước phần hex của từng byte.
- **Suffix:** chuỗi đứng sau phần hex của từng byte.

### 6.1. Thêm dấu phân cách giữa các byte

```java
byte[] bytes = {0x48, 0x65, 0x6C, 0x6C, 0x6F};

HexFormat colon = HexFormat.ofDelimiter(":");
HexFormat space = HexFormat.ofDelimiter(" ");

System.out.println(colon.formatHex(bytes));
System.out.println(space.formatHex(bytes));
```

Kết quả:

```text
48:65:6c:6c:6f
48 65 6c 6c 6f
```

Delimiter được chèn **giữa các byte**, không chèn ở đầu hoặc cuối toàn bộ chuỗi.

### 6.2. Thêm tiền tố cho từng byte

```java
HexFormat prefixed = HexFormat.of()
        .withDelimiter(" ")
        .withPrefix("0x")
        .withUpperCase();

byte[] bytes = {0x01, 0x0A, (byte) 0xFF};
System.out.println(prefixed.formatHex(bytes));
```

Kết quả:

```text
0x01 0x0A 0xFF
```

Prefix `0x` xuất hiện trước **mỗi byte**, vì mỗi phần tử được định dạng độc lập. Với một chuỗi byte liên tiếp không delimiter, `withPrefix("0x")` tạo dạng như `0x010x0a0xff`.

### 6.3. Thêm hậu tố cho từng byte

```java
HexFormat bracketed = HexFormat.of()
        .withDelimiter(", ")
        .withPrefix("[")
        .withSuffix("]");

byte[] bytes = {0x01, 0x02, 0x03};
System.out.println(bracketed.formatHex(bytes));
```

Kết quả:

```text
[01], [02], [03]
```

Prefix và suffix được áp dụng cho từng byte; delimiter nằm giữa các byte đã định dạng. Điều này giúp tạo định dạng hiển thị tùy ý mà không phải tự lặp vòng lặp và nối chuỗi.

### 6.4. Kết hợp các cấu hình

```java
HexFormat packetView = HexFormat.of()
        .withDelimiter(" | ")
        .withPrefix("0x")
        .withSuffix("")
        .withUpperCase();

byte[] packet = {0x01, 0x02, 0x10, (byte) 0xFE};
System.out.println(packetView.formatHex(packet));
```

Kết quả:

```text
0x01 | 0x02 | 0x10 | 0xFE
```

Các phương thức `with...` có thể nối tiếp để tạo formatter dễ đọc. Vì `HexFormat` bất biến, mỗi lần gọi trả về một cấu hình mới; không làm thay đổi formatter gốc.

## 7. Parse chuỗi có delimiter, prefix và suffix

Formatter có cấu hình tương ứng có thể parse định dạng mà chính nó tạo ra:

```java
HexFormat format = HexFormat.of()
        .withDelimiter(":")
        .withPrefix("0x")
        .withUpperCase();

String text = "0x48:0x65:0x6C:0x6C:0x6F";
byte[] bytes = format.parseHex(text);

System.out.println(format.formatHex(bytes));
```

Kết quả:

```text
0x48:0x65:0x6C:0x6C:0x6F
```

Parser dùng delimiter, prefix và suffix của formatter để nhận diện cấu trúc. Nếu định dạng đầu vào không khớp, dữ liệu sẽ không được parse như mong muốn và có thể ném `IllegalArgumentException`.

### 7.1. Formatter mặc định không tự bỏ `0x`

Một chuỗi phổ biến trong tài liệu là `0x48656c6c6f`. Nhưng `HexFormat.of()` mặc định không có prefix:

```java
// Không parse được bằng formatter mặc định:
// HexFormat.of().parseHex("0x48656c6c6f");

HexFormat prefixed = HexFormat.of().withPrefix("0x");
byte[] bytes = prefixed.parseHex("0x48656c6c6f");
```

Nếu định dạng có prefix ở từng byte và delimiter, phải cấu hình đúng cả hai:

```java
HexFormat format = HexFormat.of()
        .withPrefix("0x")
        .withDelimiter(" ");

byte[] bytes = format.parseHex("0x48 0x65 0x6c");
```

Đừng xóa ký tự đầu vào theo vị trí cố định nếu không biết định dạng nguồn. Cấu hình formatter diễn đạt rõ prefix/delimiter mong đợi và giúp việc format/parse nhất quán.

### 7.2. Chữ hoa/thường không phải delimiter

Parser nhận chữ số hex hoa hoặc thường; cấu hình uppercase chủ yếu quyết định cách xuất chuỗi. Ví dụ formatter uppercase có thể parse chuỗi chữ thường nếu các delimiter/prefix/suffix vẫn phù hợp.

## 8. HexFormat và văn bản: byte không tự động là ký tự

Một lỗi dễ gặp là cho rằng hex của chuỗi văn bản chính là các mã ký tự Unicode. Thực tế, quy trình cần phân biệt:

1. **Văn bản** là một dãy ký tự Java (`String`).
2. **Charset** như UTF-8 chuyển văn bản thành byte.
3. `HexFormat` biểu diễn những byte đó thành chữ số hex.

Muốn đổi một chuỗi văn bản thành hex, hãy mã hóa bằng charset rõ ràng trước:

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

String message = "Xin chào";
byte[] bytes = message.getBytes(StandardCharsets.UTF_8);

String hexText = HexFormat.of().formatHex(bytes);
System.out.println(hexText);
```

Muốn khôi phục văn bản, parse hex thành byte rồi giải mã bằng **cùng charset**:

```java
byte[] restoredBytes = HexFormat.of().parseHex(hexText);
String restoredText = new String(
        restoredBytes, StandardCharsets.UTF_8
);

System.out.println(restoredText);
```

Nếu dùng UTF-8 ở chiều mã hóa thì cũng phải dùng UTF-8 ở chiều giải mã. Không dùng `new String(bytes)` hoặc `getBytes()` không truyền charset khi cần kết quả nhất quán giữa các máy, vì các overload đó phụ thuộc charset mặc định của môi trường.

### 8.1. Ví dụ hoàn chỉnh: String ↔ UTF-8 bytes ↔ hex

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class TextToHex {
    public static void main(String[] args) {
        String original = "Java 17 - Xin chào";

        byte[] utf8 = original.getBytes(StandardCharsets.UTF_8);
        String hex = HexFormat.of().formatHex(utf8);

        byte[] decodedBytes = HexFormat.of().parseHex(hex);
        String restored = new String(
                decodedBytes, StandardCharsets.UTF_8
        );

        System.out.println("Original: " + original);
        System.out.println("Hex:      " + hex);
        System.out.println("Restored: " + restored);
    }
}
```

Chuỗi hex cụ thể phụ thuộc đúng các byte UTF-8; ký tự có dấu tiếng Việt có thể chiếm nhiều byte. Kết quả `restored` khôi phục nội dung nếu byte ban đầu là UTF-8 hợp lệ.

### 8.2. Hex không đồng nghĩa với ASCII

Các ký tự ASCII cơ bản có mã byte tương ứng với giá trị của chúng, ví dụ `A` là `41`. Nhưng tiếng Việt có dấu, emoji và nhiều ký tự Unicode khác thường được mã hóa thành nhiều byte UTF-8. Vì vậy, không thể lấy từng cặp hex rồi ép thành một ký tự Java theo giả định ASCII.

Ví dụ:

```java
String text = "é";
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
System.out.println(HexFormat.of().formatHex(utf8));
```

Với UTF-8, chữ `é` ở dạng Unicode dựng sẵn được mã hóa thành hai byte `c3 a9`, nên chuỗi hex là `c3a9`. Hex thể hiện **byte encoding**, không phải trực tiếp mã code point của Java `char`.

## 9. Vai trò trong debug, log và giao thức nhị phân

### 9.1. Quan sát packet hoặc byte buffer

Khi nhận dữ liệu từ socket, file hoặc API nhị phân, hex giúp đọc byte theo thứ tự:

```java
byte[] packet = {
        0x01, 0x10, 0x00, 0x2A,
        0x48, 0x69, (byte) 0xFF
};

String dump = HexFormat.ofDelimiter(" ")
        .withUpperCase()
        .formatHex(packet);

System.out.println(dump);
```

Kết quả:

```text
01 10 00 2A 48 69 FF
```

Đây là cách nhanh để đối chiếu với tài liệu giao thức, log từ thiết bị hoặc dữ liệu kỳ vọng trong test. `HexFormat` không phân tích cấu trúc packet; bạn vẫn phải biết byte nào là header, length, payload, checksum hoặc cờ trạng thái.

### 9.2. Chỉ log vùng payload

Nếu mảng chứa header và payload, có thể format riêng payload:

```java
int payloadStart = 4;
int payloadEnd = packet.length - 1; // Bỏ byte checksum cuối

String payloadDump = HexFormat.ofDelimiter(" ")
        .formatHex(packet, payloadStart, payloadEnd);
```

Phạm vi kết thúc không bao gồm `payloadEnd`. Cần tính chỉ số từ cấu trúc thực tế của giao thức và xác nhận giới hạn trước khi gọi phương thức.

### 9.3. Định dạng hash hoặc checksum để hiển thị

Một giá trị hash là một dãy byte. Có thể hiển thị nó bằng hex:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public class DigestHex {
    public static void main(String[] args)
            throws NoSuchAlgorithmException {
        byte[] input = "sample".getBytes(StandardCharsets.UTF_8);
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(input);

        String hexDigest = HexFormat.of().formatHex(digest);
        System.out.println(hexDigest);
    }
}
```

`MessageDigest` tạo digest; `HexFormat` chỉ chuyển mảng digest thành chuỗi dễ đọc. **Không nhầm HexFormat với thuật toán hash** và không dùng hex như một biện pháp bảo mật. Hash không thể được tạo ra bằng cách chỉ đổi byte sang hex.

## 10. Byte có dấu, thứ tự byte và endian

`HexFormat` định dạng từng phần tử `byte` theo mẫu bit 8 bit của nó. Nó không quyết định cách diễn giải một nhóm byte thành số nguyên nhiều byte.

Ví dụ:

```java
byte[] bytes = {(byte) 0x01, (byte) 0x02, (byte) 0x03, (byte) 0x04};
System.out.println(HexFormat.ofDelimiter(" ").formatHex(bytes));
```

Kết quả:

```text
01 02 03 04
```

Chuỗi này giữ đúng thứ tự phần tử trong mảng. Nếu giao thức xem bốn byte đó là một số nguyên 32 bit:

- Big-endian có thể diễn giải là `0x01020304`.
- Little-endian có thể diễn giải là `0x04030201`.

`HexFormat` vẫn hiển thị `01 02 03 04` trong cả hai trường hợp; việc diễn giải endian thuộc về code đọc số, chẳng hạn `ByteBuffer.order(...)`, không thuộc trách nhiệm của `HexFormat`.

Ngoài ra, `byte` là kiểu có dấu trong Java. Nếu in trực tiếp bằng `System.out.println(bytes[i])`, giá trị `0xFF` sẽ xuất hiện là `-1`; `HexFormat` vẫn in `ff` vì nó biểu diễn mẫu 8 bit.

## 11. Tính bất biến và tái sử dụng formatter

`HexFormat` là lớp bất biến và thread-safe. Những phương thức cấu hình như:

- `withDelimiter(String)`
- `withPrefix(String)`
- `withSuffix(String)`
- `withUpperCase()`
- `withLowerCase()`

trả về formatter mới. Chúng không sửa formatter ban đầu.

Ví dụ:

```java
HexFormat base = HexFormat.of();
HexFormat colonUpper = base.withDelimiter(":").withUpperCase();

byte[] bytes = {0x0A, 0x0B};

System.out.println(base.formatHex(bytes));
System.out.println(colonUpper.formatHex(bytes));
```

Kết quả:

```text
0a0b
0A:0B
```

Do formatter không giữ trạng thái thay đổi giữa các lần gọi, có thể khai báo formatter dùng chung:

```java
private static final HexFormat HEX =
        HexFormat.of().withUpperCase();
```

Điều này giúp thống nhất định dạng log hoặc giao tiếp giữa các module.

## 12. Xử lý lỗi khi parse dữ liệu không tin cậy

Chuỗi hex đến từ file, người dùng hoặc mạng có thể sai định dạng. Những lỗi thường gặp:

- Có số ký tự hex lẻ trong định dạng mặc định.
- Có ký tự ngoài `0`–`9`, `a`–`f`, `A`–`F`.
- Thiếu prefix, suffix hoặc delimiter đã cấu hình.
- Có delimiter ở vị trí không đúng.
- Chỉ số đoạn đầu vào không hợp lệ.

Có thể bắt `IllegalArgumentException` ở ranh giới dữ liệu:

```java
import java.util.HexFormat;

static byte[] tryParseHex(String input) {
    try {
        return HexFormat.of().parseHex(input);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "Dữ liệu phải là chuỗi hex hợp lệ", ex
        );
    }
}
```

Trong ứng dụng thực tế, cần xác định hợp đồng đầu vào trước khi parse: có cho phép dấu cách, dấu hai chấm, `0x`, hay chữ hoa không? Hãy cấu hình `HexFormat` tương ứng hoặc chuẩn hóa theo một quy tắc được công bố rõ. Không xóa mọi ký tự không phải hex một cách tùy tiện; thao tác đó có thể biến dữ liệu lỗi thành một chuỗi khác mà người gửi không hề định gửi.

Nếu dữ liệu có kích thước lớn, cần kiểm tra giới hạn độ dài trước khi cấp phát mảng byte để tránh nhận một chuỗi khổng lồ ngoài dự kiến. `HexFormat` là công cụ chuyển đổi, không thay thế validation kích thước và quy tắc giao thức.

## 13. So sánh HexFormat với cách làm thủ công

Trước Java 17, thường phải tự tạo vòng lặp và tra bảng ký tự:

```java
static String toHexManually(byte[] bytes) {
    char[] digits = "0123456789abcdef".toCharArray();
    StringBuilder result = new StringBuilder(bytes.length * 2);

    for (byte value : bytes) {
        int unsigned = value & 0xFF;
        result.append(digits[unsigned >>> 4]);
        result.append(digits[unsigned & 0x0F]);
    }

    return result.toString();
}
```

Đoạn code phải tự xử lý:

1. Chuyển byte có dấu thành giá trị 0–255 bằng `& 0xFF`.
2. Lấy 4 bit cao bằng dịch phải.
3. Lấy 4 bit thấp bằng mask.
4. Chọn ký tự từ bảng chữ số.
5. Tạo chuỗi đủ hai chữ số cho mỗi byte.
6. Nếu cần delimiter, prefix, suffix hoặc uppercase, phải tự bổ sung thêm logic.

Trong Java 17, `HexFormat` diễn đạt mục tiêu trực tiếp:

```java
String hex = HexFormat.of().formatHex(bytes);
```

Với code mới, `HexFormat` giúp giảm boilerplate và thống nhất hành vi parse/format. Vòng lặp thủ công chỉ nên giữ khi cần một định dạng đặc thù mà API không cung cấp hoặc khi có lý do hiệu năng đã được đo và xác nhận.

## 14. Các nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `HexFormat` chuyển văn bản Unicode trực tiếp thành hex. | Nó nhận byte; muốn biểu diễn văn bản, trước hết mã hóa String bằng charset như UTF-8. |
| Hex là mã hóa bảo mật. | Hex chỉ là encoding có thể đảo ngược; không che giấu dữ liệu. |
| Một byte chỉ cần một chữ số hex nếu giá trị nhỏ. | `HexFormat` luôn biểu diễn mỗi byte bằng hai chữ số, ví dụ `0a`. |
| `byte` có giá trị âm thì hex cũng là số âm. | Hex thể hiện mẫu bit 8 bit; `-1` có dạng `ff`. |
| `formatHex` tự đổi endian. | Nó giữ thứ tự byte trong mảng. |
| Formatter mặc định tự bỏ `0x` hoặc dấu `:`. | Cần cấu hình prefix/delimiter tương ứng; mặc định là chuỗi hex liền nhau. |
| `withUpperCase()` thay đổi byte gốc. | Nó chỉ thay đổi cách biểu diễn chữ cái hex. |
| Prefix chỉ xuất hiện một lần ở đầu toàn chuỗi. | Prefix/suffix áp dụng cho từng byte; delimiter ngăn cách các byte. |
| `parseHex` tự bỏ khoảng trắng tùy ý. | Parser tuân theo cấu hình formatter; định dạng mặc định không có delimiter. |
| Chuỗi hex hợp lệ đồng nghĩa payload hợp lệ. | Parse chỉ xác nhận cú pháp hex; cấu trúc và ý nghĩa payload cần được kiểm tra riêng. |

## 15. Bài tập thực hành

### Bài 1 — Chuyển byte thành hex

Cho mảng:

```java
byte[] data = {0x00, 0x0F, 0x10, 0x7F, (byte) 0x80, (byte) 0xFF};
```

Hãy:

1. Dùng `HexFormat.of().formatHex(data)` để tạo chuỗi hex mặc định.
2. Dùng formatter chữ hoa để tạo chuỗi thứ hai.
3. Giải thích vì sao `0x0F` phải có hai chữ số và `0xFF` có thể tương ứng với `byte` mang giá trị `-1`.

### Bài 2 — Định dạng packet

Cho mảng byte chứa header và payload. Tạo formatter hiển thị byte theo mẫu `0x01:0x02:0x03`, chữ hoa. Chỉ format vùng payload, bỏ hai byte header và một byte checksum cuối.

### Bài 3 — Parse chuỗi hex

Parse chuỗi `48656c6c6f` thành byte array rồi giải mã bằng `StandardCharsets.UTF_8`. In ra `Hello`. Thử thay chuỗi bằng `48656c6c6g` và giải thích ngoại lệ.

### Bài 4 — Prefix và delimiter

Tạo formatter với prefix `0x`, delimiter là một dấu cách và chữ hoa. Format `{0x0A, 0x2B, 0x7F}`. Sau đó dùng chính formatter để parse chuỗi đã tạo và xác nhận hai mảng byte bằng nhau.

### Bài 5 — Phân biệt hex và charset

Mã hóa `"Xin chào"` bằng UTF-8, format byte thành hex rồi parse và giải mã trở lại. Giải thích tại sao một ký tự tiếng Việt có thể chiếm nhiều hơn một byte.

### Bài 6 — Phân tích endian

Cho byte array `{0x01, 0x02, 0x03, 0x04}`. In hex bằng `HexFormat`, sau đó giải thích vì sao cách diễn giải thành số 32 bit có thể khác nhau giữa big-endian và little-endian dù chuỗi hex không đổi.

## 16. Tài liệu chính thức Java 17

- [Java SE 17 API — HexFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html): danh sách phương thức, cách cấu hình formatter, format/parse byte và xử lý đoạn dữ liệu.
- [Java SE 17 API — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): các phương thức chuyển đổi và xử lý văn bản.
- [Java SE 17 API — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset chuẩn như UTF-8.
- [Java SE 17 API — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): đọc và diễn giải dữ liệu nhiều byte với thứ tự byte cụ thể.

`HexFormat` phù hợp khi cần một cách chuẩn hóa để **đưa byte thành văn bản hex và parse văn bản hex trở lại byte**. Khi xử lý văn bản, luôn xác định charset trước khi chuyển sang byte; khi xử lý packet, luôn giữ rõ thứ tự byte và cấu trúc giao thức. Hex chỉ giúp quan sát và trao đổi biểu diễn dữ liệu, không tự quyết định ý nghĩa hay bảo vệ dữ liệu đó.
