# Hiển thị mã băm và dữ liệu nhị phân phục vụ chẩn đoán trong Java 17

**Chủ đề:** Java 17  
**Chương:** Dữ liệu hệ mười sáu  
**Bài học:** Hiển thị mã băm và dữ liệu nhị phân phục vụ chẩn đoán

Khi điều tra lỗi liên quan đến dữ liệu, log dạng văn bản đôi khi không đủ để biết chính xác byte nào đã được tạo, gửi hoặc nhận. Một byte có thể chứa ký tự điều khiển, byte ngoài ASCII, giá trị âm khi nhìn qua kiểu `byte` của Java, hoặc một phần của cấu trúc nhị phân. Hiển thị dữ liệu dưới dạng **hexadecimal (hệ mười sáu)** giúp quan sát từng byte rõ ràng và gọn hơn.

Trong Java 17, API `java.util.HexFormat` cung cấp cách chuẩn để định dạng và phân tích dữ liệu nhị phân thành chuỗi hex. Kết hợp với `hashCode()`, `Arrays.hashCode()`, `System.identityHashCode()` và `MessageDigest`, ta có thể tạo thông tin chẩn đoán để so sánh đối tượng, kiểm tra nội dung và truy vết dữ liệu.

Cần phân biệt ba loại thông tin:

- **Mã băm đối tượng (`hashCode`):** giá trị `int` dùng cho cấu trúc dựa trên hash như `HashMap`/`HashSet`; không phải mã định danh duy nhất.
- **Biểu diễn hex của dữ liệu nhị phân:** cách viết mỗi byte bằng hai chữ số hệ mười sáu; có thể chuyển đổi ngược về byte.
- **Digest mật mã** như SHA-256: kết quả băm được thiết kế cho mục tiêu kiểm tra toàn vẹn hoặc ứng dụng mật mã theo thuật toán tương ứng; khác với `hashCode()`.

Các ví dụ dưới đây dùng API ổn định của Java 17, đặc biệt `HexFormat` được bổ sung trong Java 17. Không cần bật preview.

## 1. Vì sao hiển thị dữ liệu dưới dạng hex?

Một byte có 8 bit, do đó có 256 mẫu bit khác nhau. Hệ thập lục phân dùng 16 ký hiệu: `0`–`9` và `A`–`F`. Mỗi chữ số hex biểu diễn 4 bit (*nibble*), vì vậy **một byte luôn được biểu diễn bằng hai chữ số hex**.

| Hệ biểu diễn | Ví dụ một byte | Độ dài |
|---|---|---:|
| Nhị phân | `11001010` | 8 bit |
| Hex | `CA` | 2 chữ số |
| Thập phân không dấu | `202` | 1–3 chữ số |
| Ký tự ASCII (nếu là ký tự in được) | Không tương ứng cố định cho mọi byte | Tùy mã hóa |

Ví dụ byte `0xCA`:

```text
Hex:       CA
Binary:    11001010
Unsigned:  202
```

Hex có các ưu điểm khi chẩn đoán:

- Ngắn hơn nhị phân: 2 ký tự thay vì 8 ký tự cho mỗi byte.
- Giữ nguyên từng byte, không phụ thuộc byte đó có phải ký tự hiển thị được hay không.
- Dễ so sánh với packet capture, hexdump, tài liệu giao thức và dữ liệu từ công cụ hệ thống.
- Có thể chuyển đổi ngược về đúng mảng byte ban đầu nếu chuỗi được định dạng và phân tích nhất quán.

### 1.1. Vì sao không in trực tiếp mảng `byte[]`?

```java
byte[] data = {0x41, 0x42, 0x43};

System.out.println(data);
```

Kết quả thường có dạng tên lớp và mã định danh đối tượng như:

```text
[B@...
```

Đây không phải nội dung mảng. `System.out.println(data)` gọi cách biểu diễn đối tượng mặc định của mảng, không tự in từng byte.

Nếu muốn xem nội dung, cần định dạng mảng:

```java
import java.util.Arrays;

byte[] data = {0x41, 0x42, 0x43};

System.out.println(Arrays.toString(data)); // [65, 66, 67]
```

`Arrays.toString(byte[])` hiển thị các giá trị theo kiểu `byte` có dấu, nên không phải định dạng hex. Để chẩn đoán dữ liệu nhị phân, `HexFormat` thường phù hợp hơn.

## 2. API `HexFormat` trong Java 17

`java.util.HexFormat` là lớp tiện ích bất biến dùng để định dạng byte thành hex và phân tích chuỗi hex trở lại byte. Có thể tạo cấu hình bằng `HexFormat.of()` hoặc cấu hình delimiter, chữ hoa/chữ thường, prefix và suffix.

Import:

```java
import java.util.HexFormat;
```

Ví dụ ngắn nhất:

```java
byte[] bytes = {(byte) 0xCA, (byte) 0xFE, 0x00, 0x7F};

String hex = HexFormat.of().formatHex(bytes);

System.out.println(hex); // cafe007f
```

Mỗi byte được chuyển thành hai chữ số hex viết thường theo cấu hình mặc định.

### 2.1. Định dạng chữ hoa và thêm dấu phân cách

```java
byte[] packet = {
        (byte) 0xCA,
        (byte) 0xFE,
        0x00,
        0x7F,
        (byte) 0x80,
        (byte) 0xFF
};

HexFormat compact = HexFormat.of();
HexFormat spaced = HexFormat.ofDelimiter(" ");
HexFormat colonUpper = HexFormat.ofDelimiter(":").withUpperCase();

System.out.println(compact.formatHex(packet));
System.out.println(spaced.formatHex(packet));
System.out.println(colonUpper.formatHex(packet));
```

Kết quả:

```text
cafe007f80ff
ca fe 00 7f 80 ff
CA:FE:00:7F:80:FF
```

Cách chọn định dạng:

- Không delimiter: thích hợp lưu hoặc truyền chuỗi hex liên tục.
- Dấu cách: dễ đọc khi log hoặc xem dump.
- Dấu hai chấm: quen thuộc với địa chỉ MAC hoặc một số công cụ phân tích packet.
- Chữ hoa hay chữ thường chỉ là quy ước trình bày; giá trị byte không thay đổi.

### 2.2. Các phương thức thường dùng

| Phương thức | Mục đích |
|---|---|
| `HexFormat.of()` | Lấy cấu hình mặc định |
| `HexFormat.ofDelimiter(String)` | Tạo cấu hình có dấu phân cách giữa các byte |
| `withUpperCase()` | Định dạng chữ hex viết hoa |
| `withLowerCase()` | Định dạng chữ hex viết thường |
| `withPrefix(String)` | Thêm prefix theo cấu hình |
| `withSuffix(String)` | Thêm suffix theo cấu hình |
| `formatHex(byte[])` | Định dạng toàn bộ mảng byte |
| `formatHex(byte[], int, int)` | Định dạng một đoạn mảng |
| `parseHex(CharSequence)` | Phân tích chuỗi hex thành byte |
| `toHexDigits(byte)` | Định dạng một byte thành hai chữ số hex |
| `toHexDigits(int)` | Định dạng một `int` thành tám chữ số hex |

Các phương thức `with...` trả về một cấu hình `HexFormat` mới. Không cần sửa trạng thái của formatter hiện tại.

### 2.3. Định dạng một phần mảng

Có thể chỉ hiển thị một vùng byte:

```java
byte[] data = {
        0x10, 0x20, 0x30, 0x40, 0x50, 0x60
};

String middle = HexFormat.of().formatHex(data, 2, 5);

System.out.println(middle); // 304050
```

Khoảng chỉ số là `[fromIndex, toIndex)`: lấy vị trí bắt đầu và không bao gồm vị trí kết thúc. Điều này tương tự quy tắc slice thường gặp trong Java.

## 3. Chuyển đổi hex ngược về `byte[]`

Một lợi ích quan trọng của `HexFormat` là có thể parse dữ liệu hex trở lại byte:

```java
import java.util.HexFormat;
import java.util.Arrays;

public class HexParseExample {
    public static void main(String[] args) {
        String hex = "cafe007f80ff";

        byte[] bytes = HexFormat.of().parseHex(hex);

        System.out.println(Arrays.toString(bytes));
        System.out.println(HexFormat.of().formatHex(bytes));
    }
}
```

Kết quả:

```text
[-54, -2, 0, 127, -128, -1]
cafe007f80ff
```

Các số âm xuất hiện vì Java `byte` là kiểu số nguyên có dấu 8 bit, trong khoảng `-128` đến `127`. Bit pattern của `0xCA` vẫn là `11001010`; giá trị signed của byte đó là `-54`.

### 3.1. Dùng formatter có delimiter khi parse

Nếu chuỗi có delimiter, hãy sử dụng formatter tương ứng:

```java
HexFormat format = HexFormat.ofDelimiter(":");

byte[] bytes = format.parseHex("CA:FE:00:7F");

System.out.println(HexFormat.of().formatHex(bytes));
// cafe007f
```

Formatter được cấu hình delimiter để nhận đúng cách phân tách. Tránh tự xóa ký tự tùy tiện trước khi parse, vì điều đó có thể che giấu lỗi dữ liệu hoặc làm thay đổi ý nghĩa chuỗi.

### 3.2. Xử lý chuỗi hex không hợp lệ

Chuỗi hex phải có số chữ số hợp lệ cho từng byte và chỉ chứa ký tự hex được hỗ trợ cùng delimiter theo cấu hình. Chuỗi không hợp lệ sẽ gây `IllegalArgumentException`.

```java
try {
    byte[] bytes = HexFormat.of().parseHex("12G4");
} catch (IllegalArgumentException exception) {
    System.out.println("Chuỗi hex không hợp lệ");
}
```

Các lỗi phổ biến:

- Có ký tự ngoài `0`–`9`, `a`–`f`, `A`–`F`.
- Số chữ số hex lẻ khi định dạng không có prefix/delimiter đặc biệt.
- Delimiter không khớp cấu hình formatter.
- Dữ liệu bị cắt giữa chừng.

Không nên bỏ qua lỗi parse và thay bằng mảng rỗng; hãy ghi nhận nguyên nhân để biết dữ liệu đầu vào bị sai ở đâu.

## 4. `byte` có dấu và cách đọc byte dưới dạng unsigned

Java không có kiểu primitive `ubyte`. Kiểu `byte` biểu diễn số nguyên có dấu 8 bit:

```java
byte a = 127;
byte b = (byte) 0x80;
byte c = (byte) 0xFF;

System.out.println(a); // 127
System.out.println(b); // -128
System.out.println(c); // -1
```

Trong khi đó, khi phân tích packet hoặc file, ta thường muốn đọc bit pattern dưới dạng số không dấu từ 0 đến 255.

Dùng `Byte.toUnsignedInt(byte)`:

```java
byte value = (byte) 0xFF;

int signed = value;
int unsigned = Byte.toUnsignedInt(value);

System.out.println(signed);   // -1
System.out.println(unsigned); // 255
```

### 4.1. Vì sao `HexFormat` hữu ích với byte âm?

`HexFormat.formatHex(byte[])` định dạng đúng bit pattern 8 bit của từng phần tử. Nó không in dấu âm hay mở rộng dấu thành 32 bit.

```java
byte value = (byte) 0xFF;

System.out.println(value); // -1
System.out.println(HexFormat.of().formatHex(new byte[]{value})); // ff
```

Nếu tự chuyển `byte` sang `int` rồi gọi `Integer.toHexString`, có thể gặp sign extension:

```java
byte value = (byte) 0xFF;

System.out.println(Integer.toHexString(value)); // ffffffff
System.out.println(Integer.toHexString(value & 0xFF)); // ff
```

Biểu thức `value & 0xFF` giữ lại 8 bit thấp, chuyển bit pattern về miền số nguyên không dấu 0–255. Tuy nhiên, khi mục tiêu là định dạng cả mảng byte, nên dùng trực tiếp `HexFormat`.

## 5. Hiển thị dữ liệu ở dạng nhị phân 8 bit

Hex rất gọn, nhưng khi cần xem từng bit — ví dụ cờ giao thức, bit mask hoặc header — có thể chuyển từng byte sang chuỗi nhị phân.

`Integer.toBinaryString(int)` trả về biểu diễn nhị phân không có các số 0 ở đầu. Để mỗi byte luôn đủ 8 bit, cần pad thêm số 0.

```java
static String toBinaryString(byte value) {
    int unsigned = Byte.toUnsignedInt(value);
    String bits = Integer.toBinaryString(unsigned);
    return "0".repeat(8 - bits.length()) + bits;
}
```

Ví dụ:

```java
byte[] data = {(byte) 0x03, (byte) 0x80, (byte) 0xFF};

for (byte value : data) {
    System.out.println(toBinaryString(value));
}
```

Kết quả:

```text
00000011
10000000
11111111
```

Mỗi dòng luôn biểu diễn đúng 8 bit của một byte.

### 5.1. In cả hex và binary cạnh nhau

```java
byte[] data = {(byte) 0x03, (byte) 0x80, (byte) 0xFF};

for (byte value : data) {
    String hex = HexFormat.of().toHexDigits(value);
    String binary = toBinaryString(value);

    System.out.printf("hex=%s binary=%s%n", hex, binary);
}
```

Kết quả:

```text
hex=03 binary=00000011
hex=80 binary=10000000
hex=ff binary=11111111
```

Khi phân tích cờ bit, có thể nhìn ra ngay bit cao nhất có được bật hay không. Ví dụ `0x80` tương ứng `10000000`, tức bit 7 được bật còn các bit khác tắt.

### 5.2. Định dạng bit của một `int`

Một `int` có 32 bit. `Integer.toBinaryString(value)` không hiển thị các số 0 ở đầu, vì vậy có thể viết helper:

```java
static String to32BitBinary(int value) {
    String bits = Integer.toBinaryString(value);
    return "0".repeat(32 - bits.length()) + bits;
}
```

Với giá trị `5`, kết quả là:

```text
00000000000000000000000000000101
```

Với số âm, `Integer.toBinaryString` trả về biểu diễn hai bù đủ 32 bit. Việc pad vẫn giữ chuỗi ở độ dài 32.

## 6. Hiển thị mã băm đối tượng dưới dạng hex

`hashCode()` trả về một `int` 32 bit. Để log gọn và dễ so sánh, có thể hiển thị bit pattern đó dưới dạng tám chữ số hex.

```java
import java.util.HexFormat;

static String hexHash(int hash) {
    return "0x" + HexFormat.of().toHexDigits(hash);
}
```

Ví dụ:

```java
String text = "Java 17";

int hash = text.hashCode();

System.out.println(hash);
System.out.println("0x" + HexFormat.of().toHexDigits(hash));
```

`toHexDigits(int)` định dạng `int` thành tám chữ số hex, kể cả khi giá trị là số âm. Ví dụ `-1` có bit pattern 32 bit toàn `1`, nên dạng hex là `ffffffff`.

### 6.1. Hash code không phải ID duy nhất

Theo hợp đồng của `Object.hashCode()`:

- Nếu hai đối tượng bằng nhau theo `equals()`, chúng phải có cùng hash code.
- Hai đối tượng không bằng nhau **vẫn có thể** có cùng hash code (*collision*).
- Hash code phải nhất quán trong một lần thực thi khi thông tin dùng trong `equals()` không thay đổi.
- Không có bảo đảm chung rằng hash code của mọi kiểu đối tượng ổn định giữa các lần chạy chương trình.

Vì vậy, không dùng hash code để:

- Làm khóa định danh duy nhất của bản ghi.
- Xác định duy nhất một object trong hệ thống.
- Xác minh tính toàn vẹn mật mã của file.
- Tạo token bảo mật.
- Lưu làm ID lâu dài giữa các phiên bản ứng dụng.

Hash code chủ yếu phục vụ các cấu trúc dữ liệu dựa trên hash.

### 6.2. Phân biệt `hashCode()` và `System.identityHashCode()`

`hashCode()` có thể được class override để phản ánh nội dung logic. `System.identityHashCode(object)` trả về hash code theo danh tính đối tượng, không phụ thuộc implementation `hashCode()` đã override.

```java
record User(String name, int age) {}

User first = new User("An", 20);
User second = new User("An", 20);

System.out.println(first.equals(second)); // true
System.out.println(first.hashCode() == second.hashCode()); // true

System.out.println(System.identityHashCode(first));
System.out.println(System.identityHashCode(second));
```

Hai record có nội dung bằng nhau nên `equals()` và `hashCode()` tương ứng. Tuy nhiên, chúng là hai instance khác nhau. Identity hash code thường khác nhau, nhưng **vẫn có thể trùng** vì đó cũng là một số nguyên có giới hạn.

`identityHashCode` không phải địa chỉ bộ nhớ và không bảo đảm duy nhất.

### 6.3. Định dạng hash code thành hex

```java
static String formatHash(Object value) {
    if (value == null) {
        return "null";
    }

    int hash = value.hashCode();
    return "0x" + HexFormat.of().toHexDigits(hash);
}
```

Dạng tám chữ số giúp log nhất quán:

```text
hash=0x0000002a
hash=0x89abcdef
hash=0xffffffff
```

Số 0 ở đầu không có nghĩa giá trị thay đổi. Nó chỉ làm rõ đây là biểu diễn đầy đủ 32 bit.

## 7. Hash nội dung mảng và đối tượng

### 7.1. Mảng Java mặc định không hash theo nội dung

Mảng là object. Gọi trực tiếp `hashCode()` trên mảng thường dùng identity hash, không phải hash từ các byte bên trong.

```java
byte[] first = {1, 2, 3};
byte[] second = {1, 2, 3};

System.out.println(first.equals(second)); // false
System.out.println(first.hashCode() == second.hashCode()); // thường false
```

Để tính hash theo nội dung mảng, dùng `Arrays.hashCode`:

```java
import java.util.Arrays;

byte[] first = {1, 2, 3};
byte[] second = {1, 2, 3};

System.out.println(Arrays.equals(first, second)); // true
System.out.println(Arrays.hashCode(first) == Arrays.hashCode(second)); // true
```

`Arrays.hashCode(byte[])` là hash code 32 bit theo nội dung byte. Hai mảng cùng nội dung sẽ có cùng hash code, nhưng hai mảng khác nội dung vẫn có thể collision.

### 7.2. Hiển thị content hash dưới dạng hex

```java
byte[] payload = {(byte) 0xCA, (byte) 0xFE, 0x01};

int contentHash = Arrays.hashCode(payload);

System.out.println("payload=" + HexFormat.of().formatHex(payload));
System.out.println("hash=0x" + HexFormat.of().toHexDigits(contentHash));
```

Hai dòng log trả lời hai câu hỏi khác nhau:

- `payload=...` cho biết chính xác byte nào có trong dữ liệu.
- `hash=...` là giá trị tóm tắt 32 bit phục vụ so sánh nhanh trong cấu trúc hash.

Không dùng content hash 32 bit để kết luận chắc chắn hai payload giống nhau. Khi cần xác nhận nội dung, so sánh byte trực tiếp bằng `Arrays.equals`.

### 7.3. Dùng `Objects.hash()` cho nhiều trường

Với object thông thường, có thể tạo hash kết hợp từ các trường:

```java
import java.util.Objects;

final class Customer {
    private final long id;
    private final String name;

    Customer(long id, String name) {
        this.id = id;
        this.name = name;
    }

    @Override
    public int hashCode() {
        return Objects.hash(id, name);
    }
}
```

Khi override `hashCode()`, cần tuân theo hợp đồng với `equals()`: nếu hai object được xem là bằng nhau thì hash code phải bằng nhau.

Với mảng primitive như `byte[]`, hãy dùng `Arrays.hashCode(bytes)` để hash nội dung. Không dựa vào `Objects.hash(bytes)` để có hash theo từng byte của mảng primitive.

## 8. Hex dump: hiển thị offset, hex và ký tự đọc được

Một log chẩn đoán dữ liệu nhị phân thường hữu ích hơn khi có:

- Offset: vị trí byte trong dữ liệu.
- Hex: giá trị từng byte.
- ASCII/printable: ký tự hiển thị được, nếu byte thuộc vùng phù hợp.

Ví dụ dữ liệu:

```text
Offset   Hex bytes                 ASCII
0000     48 65 6c 6c 6f 20 4a 61   Hello Ja
0008     76 61 20 31 37            va 17
```

Hex dump giúp xác định dữ liệu bị cắt, byte thừa, byte điều khiển hoặc sai encoding. Với dữ liệu nhị phân tổng quát, cột ASCII chỉ là góc nhìn phụ; byte không in được có thể được thay bằng dấu chấm.

### 8.1. Hàm dump đơn giản bằng Java 17

```java
import java.util.HexFormat;
import java.nio.charset.StandardCharsets;

public class HexDump {
    private static final HexFormat HEX = HexFormat.ofDelimiter(" ");

    static void dump(byte[] data, int bytesPerLine) {
        for (int offset = 0; offset < data.length; offset += bytesPerLine) {
            int end = Math.min(offset + bytesPerLine, data.length);

            String hex = HEX.formatHex(data, offset, end);

            StringBuilder ascii = new StringBuilder();
            for (int i = offset; i < end; i++) {
                int value = Byte.toUnsignedInt(data[i]);

                if (value >= 32 && value <= 126) {
                    ascii.append((char) value);
                } else {
                    ascii.append('.');
                }
            }

            System.out.printf(
                    "%08X  %-47s  %s%n",
                    offset,
                    hex,
                    ascii
            );
        }
    }

    public static void main(String[] args) {
        byte[] data = "Hello Java 17".getBytes(StandardCharsets.US_ASCII);
        dump(data, 8);
    }
}
```

Kết quả:

```text
00000000  48 65 6c 6c 6f 20 4a 61                        Hello Ja
00000008  76 61 20 31 37                                 va 17
```

Hàm này phục vụ minh họa chẩn đoán:

- Offset được in bằng 8 chữ số hex.
- Mỗi byte được in thành hai chữ số.
- ASCII chỉ hiển thị vùng byte 32–126; byte khác thành dấu `.`.
- Dữ liệu cuối dòng ít byte hơn vẫn được xử lý bằng `Math.min`.

Trong công cụ production, có thể bổ sung giới hạn số byte hiển thị, cắt dữ liệu theo trang, hiển thị tổng kích thước và tránh in nội dung nhạy cảm.

### 8.2. Offset không phải địa chỉ bộ nhớ

Offset `00000008` có nghĩa byte đang được hiển thị ở vị trí thứ 8 tính từ đầu mảng (đếm từ 0). Nó không phải địa chỉ RAM hay địa chỉ file tuyệt đối.

Nếu dump một đoạn bắt đầu từ offset ngoài mảng, cần cộng vị trí gốc của đoạn với chỉ số nội bộ để hiển thị offset toàn dữ liệu.

## 9. Dữ liệu nhị phân và mã hóa ký tự

Một `byte[]` không tự mang thông tin rằng nó là UTF-8, UTF-16, ảnh PNG hay packet giao thức. Hex chỉ cho biết byte; để diễn giải thành văn bản cần biết encoding.

### 9.1. Chuyển String thành byte bằng charset tường minh

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

String message = "Xin chào Java 17";

byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
String hex = HexFormat.of().formatHex(bytes);

System.out.println(hex);
```

UTF-8 có thể dùng nhiều byte cho một ký tự. Vì vậy số byte không nhất thiết bằng số ký tự trong chuỗi.

### 9.2. Khôi phục String từ byte

```java
byte[] bytes = HexFormat.of().parseHex(hex);

String restored = new String(bytes, StandardCharsets.UTF_8);

System.out.println(restored);
```

Dùng cùng charset khi chuyển ngược. Tránh `new String(bytes)` hoặc `getBytes()` không tham số trong code cần kết quả ổn định, vì chúng phụ thuộc charset mặc định của môi trường.

### 9.3. Hex không phải encoding

Các thuật ngữ cần phân biệt:

| Khái niệm | Vai trò |
|---|---|
| Byte | Đơn vị dữ liệu 8 bit |
| Binary | Cách biểu diễn bit bằng 0 và 1 |
| Hexadecimal | Cách biểu diễn bit bằng chữ số hệ 16 |
| UTF-8 | Quy tắc mã hóa ký tự thành byte |
| ASCII | Bộ mã ký tự cơ bản |
| Hex dump | Cách trình bày các byte bằng hex, thường kèm offset và ký tự |

Một chuỗi hex của UTF-8 là **biểu diễn văn bản của các byte UTF-8**, không phải một charset mới.

## 10. Phân biệt hash code với digest mật mã

`hashCode()` trả về `int` 32 bit để hỗ trợ cấu trúc hash trong Java. Nó không được thiết kế để chống va chạm có chủ đích hay bảo đảm toàn vẹn dữ liệu.

Nếu cần một fingerprint mạnh hơn cho dữ liệu, có thể dùng `MessageDigest`, ví dụ SHA-256:

```java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.nio.charset.StandardCharsets;

public class DigestExample {
    public static void main(String[] args) throws NoSuchAlgorithmException {
        byte[] data = "Java 17".getBytes(StandardCharsets.UTF_8);

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] result = digest.digest(data);

        System.out.println(HexFormat.of().formatHex(result));
    }
}
```

SHA-256 tạo digest 256 bit, thường hiển thị thành 64 chữ số hex. Đây là cách biểu diễn thường dùng khi ghi checksum hoặc fingerprint dữ liệu.

### 10.1. So sánh ba khái niệm

| Đặc điểm | `Object.hashCode()` | `Arrays.hashCode(byte[])` | SHA-256 |
|---|---|---|---|
| Kết quả | `int` 32 bit | `int` 32 bit | Digest 256 bit |
| Mục tiêu chính | Hash collection | Hash nội dung mảng trong Java | Fingerprint mật mã |
| Collision | Có thể xảy ra | Có thể xảy ra | Vẫn có xác suất về lý thuyết, nhưng rất khó tìm collision thực tế |
| Dùng làm ID duy nhất | Không | Không | Không nên coi là ID duy nhất tuyệt đối |
| Kiểm tra toàn vẹn | Không phù hợp | Không phù hợp | Phù hợp để phát hiện thay đổi dữ liệu theo mô hình digest |
| Chống giả mạo | Không | Không | Digest đơn lẻ không xác thực nguồn; cần HMAC hoặc chữ ký khi cần xác thực |

Một digest SHA-256 đơn thuần không chứng minh ai đã tạo dữ liệu. Nếu cần xác thực rằng dữ liệu đến từ bên có khóa bí mật, hãy dùng HMAC hoặc chữ ký số theo thiết kế bảo mật phù hợp.

## 11. Ví dụ tổng hợp: chẩn đoán một payload

Một công cụ chẩn đoán thường cần hiển thị đồng thời:

- Kích thước payload.
- Dữ liệu hex.
- Content hash.
- Digest SHA-256.
- Một vài byte đầu dưới dạng binary.

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.HexFormat;

public class PayloadDiagnostics {

    private static final HexFormat HEX = HexFormat.of();

    static String bits(byte value) {
        int unsigned = Byte.toUnsignedInt(value);
        String binary = Integer.toBinaryString(unsigned);
        return "0".repeat(8 - binary.length()) + binary;
    }

    static void print(byte[] payload) throws NoSuchAlgorithmException {
        int contentHash = Arrays.hashCode(payload);

        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(payload);

        System.out.println("length=" + payload.length);
        System.out.println("hex=" + HEX.formatHex(payload));
        System.out.println(
                "contentHash=0x" + HEX.toHexDigits(contentHash)
        );
        System.out.println("sha256=" + HEX.formatHex(digest));

        int previewLength = Math.min(payload.length, 8);
        for (int i = 0; i < previewLength; i++) {
            System.out.printf(
                    "byte[%d] hex=%s binary=%s%n",
                    i,
                    HEX.toHexDigits(payload[i]),
                    bits(payload[i])
            );
        }
    }

    public static void main(String[] args) throws NoSuchAlgorithmException {
        byte[] payload =
                "Java 17 diagnostic".getBytes(StandardCharsets.UTF_8);

        print(payload);
    }
}
```

Giá trị SHA-256 được in ra sẽ cố định cho cùng một dãy byte đầu vào. Content hash cũng xác định theo nội dung trong Java, nhưng chỉ có 32 bit và có thể collision. Hex dump thể hiện byte thực tế, giúp kiểm tra encoding hoặc dữ liệu bị thay đổi ở đâu.

## 12. Các lỗi thường gặp khi hiển thị mã băm và dữ liệu nhị phân

### Lỗi 1. In trực tiếp `byte[]`

```java
System.out.println(bytes);
```

Cách này in dạng định danh đối tượng, không phải nội dung. Dùng `HexFormat.of().formatHex(bytes)` hoặc `Arrays.toString(bytes)` tùy mục tiêu.

### Lỗi 2. Nhầm byte âm với dữ liệu sai

```java
byte value = (byte) 0xFF;
System.out.println(value); // -1
```

Đây là biểu diễn signed của cùng bit pattern `11111111`. Dùng `Byte.toUnsignedInt(value)` nếu muốn số 255, hoặc `HexFormat` nếu muốn hex `ff`.

### Lỗi 3. Chuyển byte âm sang int rồi định dạng mà không mask

```java
byte value = (byte) 0x80;

System.out.println(Integer.toHexString(value)); // ffffff80
```

Đây là sign extension lên 32 bit. Dùng `HexFormat.of().toHexDigits(value)` hoặc `value & 0xFF` nếu cần định dạng bằng API số nguyên.

### Lỗi 4. Dùng `hashCode()` như fingerprint bảo mật

Hash code 32 bit có thể collision và không có thiết kế chống tấn công. Dùng `MessageDigest` với thuật toán phù hợp khi cần digest.

### Lỗi 5. Nghĩ hai object có cùng hash code thì bằng nhau

Hai object khác nhau có thể có cùng hash code. Cần kiểm tra `equals()` hoặc so sánh dữ liệu cụ thể.

### Lỗi 6. Dùng `hashCode()` của array để so sánh nội dung

Mảng không override `equals()`/`hashCode()` theo nội dung. Dùng `Arrays.equals()` và `Arrays.hashCode()`.

### Lỗi 7. Dùng charset mặc định

`new String(bytes)` và `text.getBytes()` có thể tạo kết quả khác nhau giữa môi trường. Chỉ định `StandardCharsets.UTF_8` hoặc charset giao thức yêu cầu.

### Lỗi 8. Parse hex bằng formatter không đúng delimiter

Nếu log dùng `:` giữa byte, cần parse với `HexFormat.ofDelimiter(":")`. Đừng xóa delimiter tùy tiện nếu cần kiểm tra tính hợp lệ định dạng.

### Lỗi 9. Cho rằng hex dump là dữ liệu gốc

Hex dump là **cách trình bày** dữ liệu. Nếu sao chép log, có thể đã thêm prefix, delimiter, offset hoặc cột ASCII. Khi parse lại, chỉ đưa phần hex byte hợp lệ vào formatter.

### Lỗi 10. Ghi toàn bộ payload nhạy cảm vào log

Payload có thể chứa thông tin cá nhân, token, khóa, dữ liệu xác thực hoặc nội dung nghiệp vụ. Công cụ chẩn đoán nên giới hạn độ dài, che trường nhạy cảm và chỉ bật log chi tiết khi có lý do vận hành phù hợp.

## 13. Quy trình chẩn đoán dữ liệu bằng hex

Khi hai hệ thống tạo dữ liệu khác nhau, có thể thực hiện theo trình tự:

1. **Kiểm tra kích thước:** hai payload có cùng số byte không?
2. **Hiển thị hex:** dùng `HexFormat` để xác định byte đầu tiên khác nhau.
3. **Kiểm tra encoding:** nếu payload là văn bản, xác định UTF-8 hay charset khác.
4. **Xem binary:** khi cần phân tích bit flag, byte header hoặc mask.
5. **So sánh nội dung:** dùng `Arrays.equals()` thay vì chỉ so hash code.
6. **Tạo digest:** dùng SHA-256 để so sánh fingerprint của payload lớn hoặc trao đổi giữa hệ thống.
7. **Ghi rõ ngữ cảnh:** offset, độ dài, charset, delimiter và thời điểm capture.

Ví dụ tìm vị trí khác nhau:

```java
static int firstDifference(byte[] left, byte[] right) {
    int commonLength = Math.min(left.length, right.length);

    for (int i = 0; i < commonLength; i++) {
        if (left[i] != right[i]) {
            return i;
        }
    }

    return left.length == right.length ? -1 : commonLength;
}
```

Nếu trả về `-1`, hai mảng giống nhau. Nếu trả về một chỉ số không âm, đó là vị trí byte khác đầu tiên hoặc vị trí nơi một mảng kết thúc trước mảng còn lại.

Có thể hiển thị vùng xung quanh vị trí đó:

```java
int difference = firstDifference(left, right);

if (difference >= 0) {
    int from = Math.max(0, difference - 4);
    int leftTo = Math.min(left.length, difference + 5);
    int rightTo = Math.min(right.length, difference + 5);

    System.out.println("left:  " + HexFormat.ofDelimiter(" ")
            .formatHex(left, from, leftTo));
    System.out.println("right: " + HexFormat.ofDelimiter(" ")
            .formatHex(right, from, rightTo));
}
```

Trong ứng dụng thực tế, nếu hai mảng có độ dài khác nhau, cần xử lý `from` phù hợp với từng mảng trước khi gọi `formatHex`; ví dụ trên giả định vùng bắt đầu hợp lệ cho cả hai.

## 14. Bài tập tự luyện

### Bài 1. Đổi byte sang hex

Cho:

```java
byte[] values = {0, 15, 16, 127, (byte) 128, (byte) 255};
```

**Câu hỏi:** `HexFormat.of().formatHex(values)` trả về gì?

**Đáp án:** `000f107f80ff`. Mỗi byte có hai chữ số hex, bao gồm cả số 0 ở đầu.

### Bài 2. Giải thích số âm

Cho:

```java
byte value = (byte) 0xFF;
System.out.println(value);
System.out.println(Byte.toUnsignedInt(value));
```

**Đáp án:** Dòng đầu in `-1`; dòng sau in `255`. Bit pattern vẫn là `11111111`.

### Bài 3. Chọn hash đúng cho mảng

Cho hai mảng byte có cùng nội dung. Nên dùng `first.hashCode()` hay `Arrays.hashCode(first)` nếu muốn hash theo nội dung?

**Đáp án:** `Arrays.hashCode(first)`. Mảng Java không hash theo nội dung khi gọi trực tiếp `hashCode()`.

### Bài 4. Phân biệt collision

Hai object khác nhau có cùng `hashCode()`. Có thể kết luận chúng bằng nhau không?

**Đáp án:** Không. Hash code trùng chỉ là collision; cần `equals()` để kiểm tra bằng nhau theo logic class.

### Bài 5. Chọn API cho payload

Cần log payload nhị phân và chuyển lại chính xác thành byte sau khi copy log. Nên dùng gì?

**Đáp án:** `HexFormat` với quy ước delimiter rõ ràng, sau đó parse bằng formatter tương ứng. Cần loại phần offset và cột ASCII khỏi chuỗi đưa vào parser.

### Bài 6. Hash code hay SHA-256?

Một hệ thống cần fingerprint payload để so sánh giữa hai máy chủ. Nên chọn `Arrays.hashCode()` hay SHA-256?

**Đáp án:** SHA-256 phù hợp hơn cho fingerprint dữ liệu vì digest dài và có tính chất mật mã. `Arrays.hashCode()` chỉ là hash 32 bit cho cấu trúc dữ liệu Java, có thể collision thường xuyên hơn và không có mục tiêu chống va chạm.

### Bài 7. Tại sao phải chỉ định charset?

Một chuỗi có dấu tiếng Việt được chuyển thành byte trên hai môi trường khác nhau. Vì sao hex có thể khác?

**Đáp án:** Nếu dùng charset mặc định, mỗi môi trường có thể mã hóa khác nhau. Dùng `getBytes(StandardCharsets.UTF_8)` để tạo byte nhất quán.

## 15. Tài liệu tham khảo chính thức

- [JDK 17 API — HexFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html): định dạng và phân tích dữ liệu byte thành hex, delimiter, chữ hoa/chữ thường và chuyển đổi từng byte.
- [JDK 17 API — Object.hashCode()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#hashCode()): hợp đồng hash code của đối tượng Java.
- [JDK 17 API — System.identityHashCode(Object)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#identityHashCode(java.lang.Object)): hash code theo danh tính đối tượng.
- [JDK 17 API — Arrays](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): `equals`, `hashCode`, `deepHashCode` và các tiện ích xử lý mảng.
- [JDK 17 API — Byte](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Byte.html): chuyển đổi signed/unsigned và các phương thức xử lý byte.
- [JDK 17 API — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): API digest mật mã như SHA-256.

**Ghi nhớ:** Dùng `HexFormat` để hiển thị và khôi phục byte; dùng `Byte.toUnsignedInt` khi cần đọc byte theo miền 0–255; dùng `Arrays.hashCode` cho hash nội dung mảng; dùng `hashCode()` cho mục đích cấu trúc hash của object; và chọn digest như SHA-256 khi cần fingerprint dữ liệu. Hex là cách trình bày bit pattern, không tự thay đổi hay mã hóa lại nội dung gốc.
