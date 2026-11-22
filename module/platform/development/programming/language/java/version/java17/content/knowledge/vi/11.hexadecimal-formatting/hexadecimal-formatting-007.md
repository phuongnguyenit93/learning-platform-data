# Giới hạn đoạn dữ liệu và kiểm tra độ dài trong xử lý hệ mười sáu (Java 17)

Khi biểu diễn byte bằng hệ mười sáu (*hexadecimal*), mỗi byte thường được viết thành hai chữ số hex. Ví dụ, ba byte có giá trị `0x12`, `0xA0`, `0xFF` được biểu diễn thành chuỗi `12a0ff`. Cách biểu diễn này dễ đọc và thuận tiện khi ghi log, trao đổi dữ liệu hoặc kiểm tra nội dung nhị phân.

Nhưng khi chỉ xử lý một phần dữ liệu, cần phân biệt rõ **độ dài chuỗi ký tự hex** với **số byte thực tế**. Đồng thời, mọi thao tác lấy đoạn phải kiểm tra chỉ số bắt đầu, độ dài và giới hạn vùng dữ liệu trước khi đọc hoặc giải mã.

Trong Java 17, `java.util.HexFormat` cung cấp API chuẩn để định dạng và phân tích chuỗi hex. Kết hợp với `Objects.checkFromIndexSize`, bạn có thể xử lý các đoạn byte theo quy tắc rõ ràng, tránh lỗi vượt giới hạn, sai lệch một vị trí (*off-by-one*) và tràn số khi tính `offset + length`.

## 1. Độ dài của dữ liệu hex và dữ liệu byte

Một byte có 8 bit, có thể biểu diễn bằng hai chữ số hệ mười sáu. Mỗi chữ số hex biểu diễn 4 bit:

| Dữ liệu | Giá trị | Biểu diễn hex |
| --- | ---: | --- |
| 1 byte | `0x2A` | `2a` |
| 2 byte | `0x12 0xA0` | `12a0` |
| 4 byte | `0xDE 0xAD 0xBE 0xEF` | `deadbeef` |

Với chuỗi hex không có dấu phân cách, tiền tố hoặc khoảng trắng:

\[
\text{hexCharacterCount} = 2 \times \text{byteCount}
\]

và:

\[
\text{byteCount} = \frac{\text{hexCharacterCount}}{2}
\]

Do đó:

- 2 ký tự hex tương ứng 1 byte.
- 32 ký tự hex tương ứng 16 byte.
- 64 ký tự hex tương ứng 32 byte.
- Chuỗi có số ký tự lẻ không thể biểu diễn một dãy byte đầy đủ theo định dạng hai ký tự mỗi byte.

Ví dụ:

```java
String hex = "12a0ff";
System.out.println(hex.length());       // 6 ký tự
System.out.println(hex.length() / 2);   // 3 byte
```

Không được lấy `hex.length()` làm số byte. Nếu ứng dụng nhận một trường có độ dài được khai báo theo byte, cần đổi đơn vị rõ ràng và xác thực trước khi xử lý.

### 1.1. Khi có dấu phân cách hoặc tiền tố

Độ dài chuỗi không còn luôn bằng hai lần số byte nếu định dạng có thêm ký tự:

```java
import java.util.HexFormat;

byte[] data = {0x12, (byte) 0xA0, (byte) 0xFF};

System.out.println(HexFormat.of().formatHex(data));
// 12a0ff

System.out.println(HexFormat.ofDelimiter(":").formatHex(data));
// 12:a0:ff
```

Với chuỗi `12:a0:ff`, có 8 ký tự hiển thị nhưng vẫn chỉ có 3 byte. Nếu có thêm dấu phân cách, tiền tố hoặc hậu tố, không thể dùng công thức `length / 2` trực tiếp trên toàn chuỗi.

Hãy xác định định dạng đầu vào trước:

- Hex liền nhau: hai ký tự cho mỗi byte.
- Hex có dấu phân cách: số ký tự còn phụ thuộc delimiter.
- Hex có tiền tố như `0x`: phải tính cả quy tắc tiền tố.
- Chuỗi hex có khoảng trắng hoặc ký tự xuống dòng: cần quy định rõ có cho phép hay không; không tự ý bỏ ký tự vì có thể che dữ liệu sai định dạng.

## 2. Dùng HexFormat trong Java 17

`HexFormat` là API chuẩn trong `java.util`, có từ Java 17. Nó hỗ trợ chuyển byte thành chuỗi hex, phân tích chuỗi hex thành byte và làm việc với một vùng chỉ số của dữ liệu.

### 2.1. Chuyển byte array thành chuỗi hex

```java
import java.util.HexFormat;

public class FormatHexDemo {
    public static void main(String[] args) {
        byte[] data = {0x12, (byte) 0xA0, (byte) 0xFF};

        String hex = HexFormat.of().formatHex(data);
        System.out.println(hex); // 12a0ff
    }
}
```

Byte trong Java là kiểu `byte` có dấu, nhưng `HexFormat` định dạng mẫu bit của byte thành hai chữ số hex. Khi viết literal lớn hơn 127, cần ép kiểu như `(byte) 0xA0`.

### 2.2. Phân tích chuỗi hex thành byte array

```java
import java.util.HexFormat;

public class ParseHexDemo {
    public static void main(String[] args) {
        byte[] data = HexFormat.of().parseHex("12a0ff");

        for (byte value : data) {
            System.out.printf("%02x ", value & 0xff);
        }
    }
}
```

Kết quả:

```text
12 a0 ff
```

`parseHex` kiểm tra ký tự theo định dạng hex và trả về byte array. Chuỗi có ký tự không hợp lệ hoặc số chữ số không phù hợp sẽ bị từ chối bằng `IllegalArgumentException`.

### 2.3. Chọn chữ hoa và dấu phân cách

```java
import java.util.HexFormat;

byte[] data = {0x01, 0x23, (byte) 0xAB};

String lower = HexFormat.of().formatHex(data);
String upper = HexFormat.of().withUpperCase().formatHex(data);
String separated = HexFormat.ofDelimiter(":").formatHex(data);

System.out.println(lower);     // 0123ab
System.out.println(upper);     // 0123AB
System.out.println(separated); // 01:23:ab
```

Chữ hoa và chữ thường là hai cách viết hợp lệ của chữ số hex. Khi so sánh chuỗi, cần thống nhất định dạng hoặc so sánh byte sau khi parse thay vì so sánh văn bản chưa chuẩn hóa.

## 3. Quy ước đoạn dữ liệu: offset, length và end index

Khi xử lý một phần mảng byte, thường có ba đại lượng:

- `offset`: vị trí bắt đầu.
- `length`: số byte cần lấy.
- `end`: vị trí kết thúc theo quy ước không bao gồm (*exclusive*).

Quan hệ:

\[
end = offset + length
\]

Quy ước vùng `[offset, end)` bao gồm vị trí `offset` và không bao gồm vị trí `end`.

Ví dụ mảng:

```text
Index:  0    1    2    3    4    5
Data:  12   A0   FF   34   56   78
       |---------|
        [1, 4) = A0 FF 34
```

Đoạn bắt đầu ở index 1 và có độ dài 3 gồm các phần tử tại index 1, 2, 3. Index kết thúc là 4 nhưng không được lấy phần tử tại index 4.

Một cách đọc phổ biến trong Java là:

`fromIndex` inclusive, `toIndex` exclusive.

Ví dụ:

```java
byte[] data = {
        0x12, (byte) 0xA0, (byte) 0xFF,
        0x34, 0x56, 0x78
};

int from = 1;
int to = 4;

for (int i = from; i < to; i++) {
    System.out.printf("%02x ", data[i] & 0xff);
}
```

Kết quả là `a0 ff 34`.

Không dùng `i <= to` trong vòng lặp cho vùng `[from, to)`, vì như vậy sẽ lấy thêm một phần tử ngoài đoạn.

## 4. Kiểm tra giới hạn vùng byte an toàn

Giả sử có một mảng `data`, cần lấy `length` byte bắt đầu từ `offset`. Các điều kiện hợp lệ là:

1. `offset` không âm.
2. `length` không âm.
3. Vùng được yêu cầu nằm hoàn toàn trong mảng.

Một cách kiểm tra dễ đọc là:

```java
if (offset < 0 || length < 0 || offset + length > data.length) {
    throw new IndexOutOfBoundsException("Invalid byte range");
}
```

Tuy nhiên, phép tính `offset + length` có thể **tràn số nguyên int** nếu hai giá trị lớn. Khi bị tràn, kết quả có thể âm hoặc nhỏ hơn dự kiến, làm điều kiện kiểm tra sai.

### 4.1. Dùng Objects.checkFromIndexSize

Java 17 cung cấp `Objects.checkFromIndexSize(fromIndex, size, length)` để kiểm tra vùng `[fromIndex, fromIndex + size)` có nằm trong giới hạn hay không:

```java
import java.util.Objects;

static void validateRange(byte[] data, int offset, int length) {
    Objects.requireNonNull(data, "data");
    Objects.checkFromIndexSize(offset, length, data.length);
}
```

Phương thức này kiểm tra chỉ số âm, độ dài âm và trường hợp vùng vượt giới hạn, đồng thời xử lý phép kiểm tra theo cách tránh lỗi tràn số khi cộng chỉ số.

Khi không hợp lệ, phương thức ném `IndexOutOfBoundsException` (hoặc lớp con phù hợp). Bạn có thể để ngoại lệ chuẩn truyền lên caller hoặc chuyển thành lỗi đầu vào theo hợp đồng API của ứng dụng.

### 4.2. Tự kiểm tra theo cách tránh tràn số

Nếu cần viết logic kiểm tra riêng, hãy kiểm tra dấu trước rồi so sánh `offset` với phần còn lại của mảng:

```java
static void checkRange(byte[] data, int offset, int length) {
    if (data == null) {
        throw new NullPointerException("data");
    }
    if (offset < 0 || length < 0 || offset > data.length - length) {
        throw new IndexOutOfBoundsException("Invalid byte range");
    }
}
```

Sau khi xác nhận `length >= 0`, biểu thức `data.length - length` không bị tràn số nguyên dương; nếu `length` lớn hơn mảng thì giới hạn bên phải sẽ âm và điều kiện loại bỏ vùng đó.

Trong Java 17, `Objects.checkFromIndexSize` thường là lựa chọn ngắn gọn, ít lỗi và diễn đạt đúng ý nghĩa kiểm tra vùng.

## 5. Lấy đoạn byte và định dạng trực tiếp bằng HexFormat

`HexFormat` có overload nhận vùng chỉ số. Điều này giúp định dạng một đoạn byte mà không cần tạo mảng con:

```java
import java.util.HexFormat;
import java.util.Objects;

public class HexSegmentDemo {
    static String formatSegment(byte[] data, int offset, int length) {
        Objects.requireNonNull(data, "data");
        Objects.checkFromIndexSize(offset, length, data.length);

        return HexFormat.of().formatHex(data, offset, offset + length);
    }

    public static void main(String[] args) {
        byte[] data = {
                0x12, (byte) 0xA0, (byte) 0xFF,
                0x34, 0x56, 0x78
        };

        System.out.println(formatSegment(data, 1, 3)); // a0ff34
        System.out.println(formatSegment(data, 0, 2)); // 12a0
    }
}
```

API `formatHex(bytes, fromIndex, toIndex)` dùng `fromIndex` inclusive và `toIndex` exclusive. Sau khi `Objects.checkFromIndexSize` xác nhận vùng hợp lệ, phép cộng `offset + length` được bảo đảm nằm trong phạm vi độ dài mảng.

### 5.1. Tạo mảng con khi cần sở hữu dữ liệu riêng

Nếu cần lưu hoặc truyền riêng đoạn byte, có thể dùng `Arrays.copyOfRange`:

```java
import java.util.Arrays;
import java.util.HexFormat;
import java.util.Objects;

static byte[] copySegment(byte[] data, int offset, int length) {
    Objects.requireNonNull(data, "data");
    Objects.checkFromIndexSize(offset, length, data.length);
    return Arrays.copyOfRange(data, offset, offset + length);
}

static String hexOfSegment(byte[] data, int offset, int length) {
    return HexFormat.of().formatHex(copySegment(data, offset, length));
}
```

So sánh:

| Cách làm | Đặc điểm |
| --- | --- |
| `HexFormat.formatHex(data, from, to)` | Định dạng trực tiếp đoạn dữ liệu; không cần tạo byte array con. |
| `Arrays.copyOfRange(data, from, to)` | Tạo bản sao dữ liệu; hữu ích khi cần giữ đoạn độc lập hoặc truyền cho API khác. |
| `ByteBuffer` với view phù hợp | Có thể dùng khi cần đọc nhiều trường theo vị trí mà không sao chép; cần quản lý position/limit rõ ràng. |

Nếu chỉ cần hiển thị đoạn byte dưới dạng hex, định dạng trực tiếp thường đơn giản hơn. Nếu cần thay đổi hoặc lưu riêng đoạn dữ liệu, tạo bản sao có thể phù hợp hơn.

## 6. Cắt một đoạn từ chuỗi hex

Khi chuỗi hex không có delimiter, mỗi byte chiếm hai ký tự. Vì vậy, nếu muốn lấy đoạn byte `[byteOffset, byteOffset + byteLength)`, vị trí tương ứng trong chuỗi là:

\[
charFrom = 2 \times byteOffset
\]

\[
charTo = 2 \times (byteOffset + byteLength)
\]

Ví dụ chuỗi `12a0ff345678`:

```text
Hex character index:
0 1 2 3 4 5 6 7 8 9 10 11
1 2 a 0 f f 3 4 5 6  7  8

Byte index:
0   1   2   3   4   5
12  a0  ff  34  56  78

Lấy byte [1, 4) = a0 ff 34
Lấy char [2, 8) = a0ff34
```

### 6.1. Kiểm tra toàn bộ chuỗi trước khi đổi byte offset sang char offset

Ví dụ hàm:

```java
import java.util.HexFormat;
import java.util.Objects;

static byte[] parseByteSegment(
        String hex,
        int byteOffset,
        int byteLength) {

    Objects.requireNonNull(hex, "hex");

    if ((hex.length() & 1) != 0) {
        throw new IllegalArgumentException(
                "Hex string must contain an even number of characters");
    }

    int byteCount = hex.length() / 2;
    Objects.checkFromIndexSize(byteOffset, byteLength, byteCount);

    int charFrom = byteOffset * 2;
    int charTo = (byteOffset + byteLength) * 2;

    return HexFormat.of().parseHex(hex, charFrom, charTo);
}
```

Vì đã xác nhận chuỗi có số ký tự chẵn, `byteCount` là số byte được biểu diễn. Sau `checkFromIndexSize`, cả `byteOffset + byteLength` và các phép nhân 2 đều nằm trong giới hạn của chuỗi, nên việc tính chỉ số ký tự không vượt `int`.

Ví dụ:

```java
byte[] segment = parseByteSegment("12a0ff345678", 1, 3);
System.out.println(HexFormat.of().formatHex(segment)); // a0ff34
```

### 6.2. Parse trực tiếp theo chỉ số ký tự

Nếu caller đã làm việc bằng chỉ số ký tự thay vì chỉ số byte, `HexFormat` hỗ trợ parse một vùng của `CharSequence`:

```java
String hex = "12a0ff345678";
byte[] segment = HexFormat.of().parseHex(hex, 2, 8);

System.out.println(HexFormat.of().formatHex(segment)); // a0ff34
```

Các giới hạn:

- `fromIndex` và `toIndex` là chỉ số ký tự của chuỗi.
- `toIndex` không bao gồm ký tự ở vị trí đó.
- Độ dài vùng phải là số chẵn để biểu diễn các byte đầy đủ.
- Mọi ký tự trong vùng phải là chữ số hex hợp lệ.

Nếu đầu vào là chuỗi do người dùng hoặc hệ thống ngoài gửi đến, hãy kiểm tra giới hạn kích thước tổng thể trước khi parse để tránh tạo mảng ngoài dự kiến.

## 7. Kiểm tra độ dài đầu vào trước khi parse

Không nên parse dữ liệu hex không giới hạn rồi mới kiểm tra kích thước byte. Với đầu vào lớn, việc tạo chuỗi hoặc byte array có thể tiêu tốn nhiều bộ nhớ và thời gian.

Ví dụ hàm chỉ chấp nhận tối đa `maxBytes`:

```java
import java.util.HexFormat;
import java.util.Objects;

static byte[] parseHexWithLimit(String hex, int maxBytes) {
    Objects.requireNonNull(hex, "hex");

    if (maxBytes < 0) {
        throw new IllegalArgumentException("maxBytes must not be negative");
    }

    long maxHexChars = 2L * maxBytes;
    if (hex.length() > maxHexChars) {
        throw new IllegalArgumentException("Hex input is too long");
    }

    if ((hex.length() & 1) != 0) {
        throw new IllegalArgumentException("Hex input length must be even");
    }

    return HexFormat.of().parseHex(hex);
}
```

Dùng `long` cho phép tính `2L * maxBytes` để tránh tràn `int`. Sau khi kiểm tra kích thước, `parseHex` sẽ kiểm tra các ký tự và tạo byte array.

Nếu yêu cầu độ dài chính xác, chẳng hạn đầu vào phải đúng 16 byte:

```java
static byte[] parseExactly(String hex, int expectedBytes) {
    Objects.requireNonNull(hex, "hex");

    if (expectedBytes < 0) {
        throw new IllegalArgumentException("expectedBytes must not be negative");
    }

    long expectedChars = 2L * expectedBytes;
    if (hex.length() != expectedChars) {
        throw new IllegalArgumentException(
                "Expected " + expectedBytes + " bytes");
    }

    return HexFormat.of().parseHex(hex);
}
```

Với đầu vào không có delimiter, kiểm tra độ dài chính xác theo byte đồng thời kiểm tra số ký tự cần có. `parseHex` tiếp tục xác nhận nội dung ký tự.

### 7.1. Giới hạn trước khi đọc dữ liệu từ mạng hoặc file

Nếu một thông điệp có trường độ dài do bên gửi cung cấp, không nên tin trường đó ngay lập tức:

1. Đọc header có kích thước cố định.
2. Kiểm tra độ dài khai báo không âm và không vượt giới hạn giao thức.
3. Kiểm tra độ dài có thể chuyển đổi an toàn sang kích thước mảng hoặc buffer.
4. Chỉ sau đó mới cấp phát hoặc đọc payload.
5. Xác nhận số byte thực tế nhận được đúng với số byte yêu cầu.

Nếu đọc từ `InputStream`, phương thức `read(byte[])` có thể trả về ít byte hơn số yêu cầu. Khi cần đủ dữ liệu, dùng `readNBytes(...)` và kiểm tra số byte thực nhận, hoặc `DataInputStream.readFully(...)` nếu hợp đồng yêu cầu phải đọc đủ.

Độ dài khai báo trong header là dữ liệu đầu vào không đáng tin cậy. Cần kiểm tra giới hạn nghiệp vụ và giới hạn tài nguyên trước khi cấp phát bộ nhớ.

## 8. Phân biệt độ dài chuỗi, byte và chỉ số

Trong xử lý hex, có thể xuất hiện ba hệ chỉ số khác nhau:

| Đối tượng | Đơn vị của index/length | Ví dụ |
| --- | --- | --- |
| `byte[]` | Số byte | `data.length == 3` nghĩa là 3 byte. |
| Chuỗi hex không delimiter | Số ký tự hex | `hex.length() == 6` biểu diễn 3 byte. |
| Chuỗi Java nói chung | Đơn vị UTF-16 code unit (`char`) | `String.length()` đếm đơn vị char, không phải số byte UTF-8. |

Với hex ASCII, mỗi ký tự là một `char` đơn vị UTF-16 và có thể ánh xạ 2 ký tự thành một byte. Nhưng đừng áp dụng phép chia đôi cho một chuỗi văn bản UTF-8 bất kỳ. Độ dài văn bản và độ dài byte mã hóa là hai khái niệm khác nhau.

### 8.1. Không lấy substring bằng chỉ số byte trực tiếp

Ví dụ sai về ý nghĩa:

```java
String hex = "12a0ff345678";

// Muốn lấy byte số 1 đến byte số 3 nhưng lại dùng char index 1..4.
String wrong = hex.substring(1, 4);
System.out.println(wrong); // 2a0
```

Kết quả `2a0` không phải một đoạn byte hoàn chỉnh theo ranh giới hai ký tự. Đúng ra phải lấy chỉ số ký tự từ 2 đến 8:

```java
String correct = hex.substring(2, 8);
System.out.println(correct); // a0ff34
```

Hoặc dùng `HexFormat.parseHex(hex, 2, 8)` để vừa lấy đoạn vừa parse thành byte array.

### 8.2. Đừng nhầm chỉ số bit với chỉ số byte

Một byte có 8 bit và hai chữ số hex. Nếu giao thức mô tả offset theo bit, cần xác định rõ đoạn có bắt đầu ở ranh giới byte hay không. `HexFormat` làm việc theo byte, không trực tiếp cắt một nhóm bit tùy ý.

Nếu offset hoặc length không chia hết cho 8 bit, cần xử lý mask và dịch bit trên byte phù hợp, đồng thời định nghĩa thứ tự bit (*bit order*) của giao thức. Không thể chỉ nhân hoặc chia chỉ số theo byte một cách tùy tiện.

## 9. Xử lý chuỗi hex có delimiter

Nếu định dạng yêu cầu chuỗi có dấu `:`, có thể tạo parser tương ứng:

```java
import java.util.HexFormat;

HexFormat colonFormat = HexFormat.ofDelimiter(":");

byte[] data = colonFormat.parseHex("12:a0:ff");
System.out.println(colonFormat.formatHex(data)); // 12:a0:ff
```

Với định dạng này, không nên áp dụng `hex.length() / 2`, vì dấu phân cách làm thay đổi số ký tự. Hãy để `HexFormat` parse theo cấu hình và kiểm tra độ dài byte sau khi parse:

```java
byte[] data = HexFormat.ofDelimiter(":").parseHex("12:a0:ff");

if (data.length != 3) {
    throw new IllegalArgumentException("Expected 3 bytes");
}
```

Nếu cần giới hạn đầu vào trước khi parse, hãy đặt một giới hạn ký tự tối đa phù hợp với số byte và delimiter dự kiến. Với delimiter dài `d` ký tự, chuỗi gồm `n` byte có dạng tổng quát `2*n + d*(n-1)` ký tự nếu không có prefix/suffix.

Định dạng delimiter phải thống nhất. Không nên vừa tự xóa mọi dấu câu, khoảng trắng, vừa parse vì có thể chấp nhận nhầm đầu vào sai định dạng hoặc làm thay đổi ý nghĩa dữ liệu.

## 10. Các lỗi biên giới thường gặp

### 10.1. Off-by-one

Lỗi:

```java
for (int i = offset; i <= offset + length; i++) {
    process(data[i]);
}
```

Vòng lặp trên xử lý `length + 1` phần tử. Nếu vùng có độ dài 3 bắt đầu tại 1, chỉ số hợp lệ là 1, 2, 3.

Đúng:

```java
for (int i = offset; i < offset + length; i++) {
    process(data[i]);
}
```

Hoặc tính `endExclusive` sau khi đã xác thực range.

### 10.2. Cho phép length âm

Nếu chỉ kiểm tra `offset + length <= data.length`, giá trị length âm có thể lọt qua trong một số trường hợp. Luôn xác nhận `length >= 0`.

### 10.3. Cộng offset và length trước khi xác thực

```java
int end = offset + length; // Có thể overflow trước khi kiểm tra.
if (end <= data.length) {
    // Không đủ an toàn.
}
```

Hãy kiểm tra bằng `Objects.checkFromIndexSize(offset, length, data.length)` trước; sau đó mới tính `end`.

### 10.4. Cắt chuỗi hex tại vị trí lẻ

Chuỗi hex liền nhau phải được cắt theo cặp ký tự. Nếu bắt đầu hoặc kết thúc ở giữa một cặp, đoạn thu được không đại diện byte hoàn chỉnh.

### 10.5. Tin độ dài do người gửi khai báo

Một header có thể khai báo kích thước rất lớn hoặc âm. Kiểm tra giới hạn trước khi cấp phát mảng; không để một con số do client kiểm soát quyết định trực tiếp lượng bộ nhớ cần dùng.

### 10.6. Coi byte là số nguyên không dấu

Java `byte` nằm trong khoảng -128 đến 127. Khi hiển thị giá trị byte như số không dấu, dùng:

```java
int unsignedValue = data[index] & 0xff;
System.out.printf("%02x%n", unsignedValue);
```

Phép AND `0xff` giữ lại 8 bit thấp và mở rộng thành `int` trong khoảng 0 đến 255. `HexFormat` đã định dạng đúng bit của byte, nhưng khi tự tính toán hoặc in số thập phân, cần hiểu sự khác nhau giữa byte có dấu và giá trị octet không dấu.

## 11. Ví dụ tổng hợp: đọc một trường hex có giới hạn

Giả sử một ứng dụng nhận chuỗi hex không delimiter, chỉ chấp nhận tối đa 64 byte. Sau khi parse, ứng dụng cần lấy một đoạn con để xử lý:

```java
import java.util.HexFormat;
import java.util.Objects;

public class BoundedHexData {
    private static final int MAX_BYTES = 64;

    static byte[] decode(String hex) {
        Objects.requireNonNull(hex, "hex");

        if ((hex.length() & 1) != 0) {
            throw new IllegalArgumentException("Hex length must be even");
        }
        if (hex.length() > 2L * MAX_BYTES) {
            throw new IllegalArgumentException("Payload exceeds 64 bytes");
        }

        return HexFormat.of().parseHex(hex);
    }

    static String segmentAsHex(byte[] data, int offset, int length) {
        Objects.requireNonNull(data, "data");
        Objects.checkFromIndexSize(offset, length, data.length);
        return HexFormat.of().formatHex(data, offset, offset + length);
    }

    public static void main(String[] args) {
        byte[] payload = decode("12a0ff345678");

        System.out.println("Byte count: " + payload.length);
        System.out.println("Segment: " + segmentAsHex(payload, 1, 3));
    }
}
```

Kết quả:

```text
Byte count: 6
Segment: a0ff34
```

Hàm `decode` giới hạn kích thước trước khi tạo byte array. Hàm `segmentAsHex` kiểm tra vùng byte theo `[offset, offset + length)` rồi định dạng trực tiếp đoạn cần lấy.

Trong ứng dụng thực tế, có thể thay `MAX_BYTES` bằng giới hạn của giao thức hoặc cấu hình được kiểm soát. Tránh nhận một giới hạn không đáng tin cậy trực tiếp từ client.

## 12. Bài tập thực hành

### Bài 1: Kiểm tra chuỗi hex có đúng 16 byte

Viết hàm nhận chuỗi hex và từ chối nếu:

- Chuỗi null.
- Số ký tự lẻ.
- Độ dài không đúng 32 ký tự.
- Có ký tự ngoài `0-9`, `a-f`, `A-F`.

Gợi ý: kiểm tra độ dài trước, sau đó dùng `HexFormat.of().parseHex(...)` để xác nhận nội dung.

### Bài 2: Lấy 4 byte từ vị trí thứ 3

Với byte array:

```java
byte[] data = {
        0x00, 0x11, 0x22, 0x33,
        0x44, 0x55, 0x66, 0x77
};
```

Lấy đoạn có `offset = 2`, `length = 4`. Kết quả hex mong đợi là `22334455`. Hãy dùng `Objects.checkFromIndexSize` và `HexFormat.formatHex`.

### Bài 3: Cắt đoạn byte từ chuỗi hex

Với chuỗi `0011223344556677`, viết hàm lấy byte offset 2, length 4 mà không tạo substring trung gian. Gợi ý: chuyển byte offset thành char offset, kiểm tra range và gọi `HexFormat.parseHex(hex, from, to)`.

### Bài 4: Kiểm tra độ dài khai báo

Một header khai báo payload length. Viết hàm từ chối nếu length âm hoặc vượt 4096 byte trước khi cấp phát. Sau khi đọc payload, xác nhận số byte nhận được đúng bằng độ dài đã khai báo.

## 13. Ghi nhớ khi xử lý dữ liệu hệ mười sáu

- Chuỗi hex liền nhau có **2 ký tự cho mỗi byte**; độ dài chuỗi không phải số byte.
- Quy ước vùng nên dùng `[from, to)` với `to` không bao gồm.
- Khi caller truyền `offset` và `length`, xác thực range trước khi tính `offset + length`.
- `Objects.checkFromIndexSize` là API Java 17 phù hợp để kiểm tra vùng an toàn.
- `HexFormat` có thể định dạng và parse trực tiếp một vùng; không cần luôn tạo mảng con.
- Với chuỗi hex, phân biệt chỉ số ký tự với chỉ số byte; chỉ số byte phải nhân 2 khi chuyển sang chỉ số ký tự trong định dạng không delimiter.
- Kiểm tra kích thước đầu vào trước khi parse hoặc cấp phát bộ nhớ.
- Khi dùng delimiter, prefix hoặc suffix, không áp dụng công thức độ dài của chuỗi hex liền nhau.
- `byte` có dấu trong Java; dùng `& 0xff` khi cần giá trị octet không dấu.

## Tài liệu tham khảo chính thức

- [Java SE 17 API — `java.util.HexFormat`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html): định dạng, parse hex và các overload nhận chỉ số vùng.
- [Java SE 17 API — `java.util.Objects`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): `checkFromIndexSize` và các hàm kiểm tra chỉ số.
- [Java SE 17 API — `java.util.Arrays`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): thao tác và sao chép đoạn mảng.
- [Java SE 17 API — `java.io.InputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): đọc byte và xử lý số byte thực tế nhận được.
- [Java SE 17 API — `java.io.DataInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): `readFully` khi cần đọc đủ dữ liệu.
