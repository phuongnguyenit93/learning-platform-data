# Java 7 — Bảng mã: Phân biệt bảng mã với thứ tự byte

## Mục tiêu bài học

Khi ứng dụng Java lưu hoặc gửi dữ liệu, có hai câu hỏi rất dễ bị trộn lẫn:

1. **Bảng mã ký tự (character encoding / charset):** Một chuỗi văn bản, chẳng hạn `"A€😀"`, được chuyển từ các ký tự Unicode thành những byte nào? Ngược lại, byte được diễn giải trở thành chuỗi gì?
2. **Thứ tự byte (byte order / endianness):** Một giá trị có nhiều byte như số nguyên `0x01020304` được đặt byte cao trước (**big-endian**) hay byte thấp trước (**little-endian**)?

Chúng là **hai khía cạnh của biểu diễn dữ liệu**, không phải hai tên gọi cho cùng một cơ chế. Một bản ghi nhị phân hoàn toàn có thể dùng **UTF-8** cho phần văn bản và **little-endian** cho trường `int`. Việc thay đổi `ByteBuffer.order(...)` không tự biến UTF-8 thành UTF-16, và chọn `StandardCharsets.UTF_8` không tự quyết định thứ tự byte cho các số nguyên nhiều byte.

Java 7 đã có `java.nio.charset.StandardCharsets` để chọn các charset chuẩn bằng hằng số, cùng API `java.nio.ByteBuffer` và `java.nio.ByteOrder` để điều khiển cách đọc/ghi các giá trị số nhiều byte. Cả hai nhóm API này vẫn được sử dụng trên JDK hiện đại.

Sau bài, bạn sẽ:

- Phân biệt **Unicode code point**, **UTF-16 code unit**, **charset encoder/decoder** và **byte array**.
- Tính và đọc được byte của UTF-8, UTF-16BE, UTF-16LE; hiểu trường hợp UTF-16 có **BOM**.
- Hiểu tại sao UTF-8 **không có vấn đề little/big-endian trong chuỗi byte mã hóa**, còn UTF-16 có các biến thể byte order.
- Viết và đọc `int`/`short`/`long` bằng `ByteBuffer.order(ByteOrder.BIG_ENDIAN/LITTLE_ENDIAN)`.
- Không nhầm BOM (byte-order mark) với lựa chọn charset cho toàn bộ một bản ghi hay với byte order của các trường số.
- Phân biệt lỗi **giải mã sai charset** (mojibake) với lỗi **đọc sai endianness** (số bị đảo byte).
- Dùng charset tường minh khi làm I/O; khai báo rõ format/length/endianness khi xây binary protocol.
- Kiểm thử round-trip, dấu BOM, chuỗi có ký tự ngoài ASCII, payload không hợp lệ và header sai độ dài.

Tất cả chương trình độc lập trong bài được kiểm tra bằng **`javac --release 17` và `java` trên JDK hiện đại**, cùng stdout cụ thể. Kiến thức chỉ gồm các API và quy tắc vẫn áp dụng; ví dụ mã hóa khác UTF-8 chỉ được dùng để phân tích hoặc tương tác với dữ liệu có định dạng đã thỏa thuận.

## 1. Hai đường biểu diễn khác nhau

Hãy xem sơ đồ:

```text
VĂN BẢN
String: "A€"
   |
   | Charset encoder, ví dụ UTF-8
   v
byte[]: 41 E2 82 AC
   |
   | Truyền/lưu byte[]; bên nhận phải biết charset
   v
Charset decoder UTF-8
   |
   v
String: "A€"


SỐ NGUYÊN
int: 0x01020304
   |
   | Byte order (Big Endian)
   v
byte[]: 01 02 03 04

int: 0x01020304
   |
   | Byte order (Little Endian)
   v
byte[]: 04 03 02 01
```

Trong đường **văn bản**, encoder chọn cách thể hiện các ký tự bằng byte. Trong đường **số nguyên**, byte order chọn vị trí các byte của **cùng một giá trị số** khi đưa ra byte stream.

Không có lý do để `String "A€"` tự “mang một byte order” trước khi được encode. `String` trong Java biểu diễn văn bản theo API Unicode; byte chỉ xuất hiện khi bạn thực sự gọi `getBytes(charset)`, một encoder, hoặc API ghi văn bản.

Tương tự, một biến Java `int` chưa phải chuỗi bốn byte theo format truyền tải bên ngoài. Khi gọi `ByteBuffer.putInt`, bạn đã chọn cách biến giá trị thành bốn byte, phụ thuộc thứ tự byte hiện hành trên buffer.

### Bảng so sánh

| Khía cạnh | Character encoding / charset | Byte order / endianness |
| --- | --- | --- |
| Câu hỏi | “Chuỗi ký tự thành byte gì?” | “Các byte của giá trị nhiều byte nằm theo thứ tự nào?” |
| Input điển hình | Unicode text / `String` | `short`, `char` code unit, `int`, `long`, `float`, `double` |
| API Java | `Charset`, `StandardCharsets`, `String.getBytes`, `CharsetDecoder` | `ByteBuffer.order`, `ByteOrder`, `putInt`, `getLong`... |
| Ví dụ | UTF-8, UTF-16BE, UTF-16LE | BIG_ENDIAN, LITTLE_ENDIAN |
| Nếu chọn sai | Văn bản có thể thành ký tự sai, ký tự thay thế hoặc lỗi decode | Giá trị số sai do hoán đổi vị trí các byte |
| Có tương tác không? | Có, nhất là UTF-16BE/LE vì cách mã hóa code unit cần byte order | Có, nhưng chỉ theo định dạng của trường dữ liệu đang đọc/ghi |
| Tài liệu cần ghi | Charset, BOM nếu có, lỗi decode xử lý ra sao | Byte order và kích thước của **từng trường số** |

**Quy tắc thực hành:** Đừng dùng một từ “encoding” chung để bỏ qua một trong hai lựa chọn. Với binary protocol có text, hãy đặc tả **cả charset cho text** và **byte order cho các trường số**.

## 2. Unicode không đồng nghĩa UTF-8 hoặc UTF-16

**Unicode** xác định tập các ký tự và **code point**. Ví dụ:

- `A` có code point `U+0041`.
- `€` có code point `U+20AC`.
- Emoji mặt cười `😀` có code point `U+1F600`.

**UTF-8** và **UTF-16** là hai dạng biểu diễn (Unicode Transformation Format) có quy tắc riêng để đưa các code point vào byte/code unit.

Trong Java, `String` là một chuỗi được nhìn qua các **UTF-16 code units**. API `String.length()` đếm code units, không nhất thiết đếm số Unicode code points. Một ký tự ngoài BMP, ví dụ `😀`, được biểu diễn bởi **surrogate pair** gồm hai code units trong `String`.

```java
String text = "A\u20AC\uD83D\uDE00";

int units = text.length(); // 4 UTF-16 code units
int points = text.codePointCount(0, text.length()); // 3 Unicode code points
```

Đây là mảnh mã minh họa trong một phương thức. Chuỗi chứa 3 code points nhưng `length() == 4` vì emoji chiếm 2 UTF-16 code units.

### 2.1. Vì sao nhiều người nhầm “ký tự = byte”?

Với `A` trong ASCII range:

```text
A (U+0041)
UTF-8    -> 41                       (1 byte)
UTF-16BE -> 00 41                    (2 byte)
UTF-16LE -> 41 00                    (2 byte)
```

Với `€`:

```text
€ (U+20AC)
UTF-8    -> E2 82 AC                 (3 byte)
UTF-16BE -> 20 AC                    (2 byte)
UTF-16LE -> AC 20                    (2 byte)
```

Với `😀` (U+1F600):

```text
UTF-8    -> F0 9F 98 80              (4 byte)
UTF-16BE -> D8 3D DE 00              (4 byte: hai code units)
UTF-16LE -> 3D D8 00 DE              (4 byte: hai code units)
```

Đây là các test vector có thể kiểm tra trực tiếp. UTF-8 sử dụng 1–4 byte cho một Unicode code point hợp lệ; UTF-16 dùng một hoặc hai code units 16-bit. Không nên tính kích thước payload bằng `text.length()` hoặc `text.codePointCount(...)` rồi giả định đó là số byte.

### 2.2. UTF-8 không có tùy chọn big/little-endian theo kiểu số nguyên

UTF-8 quy định **thứ tự chính xác** các byte của mỗi ký tự. Dãy `E2 82 AC` tương ứng `€` trong UTF-8. Đảo thành `AC 82 E2` không có nghĩa là “UTF-8 little-endian”; nó là một dãy byte khác và có thể không decode hợp lệ.

Vì vậy bạn không có một cặp charset chuẩn “UTF-8BE”/“UTF-8LE” để lựa chọn. Byte order của một trường số bên cạnh text **không điều khiển** byte order của UTF-8.

**Không được đảo thứ tự các byte UTF-8** vì một protocol ghi “little endian” cho header `int`. Quy tắc little endian ở header chỉ áp dụng cho những trường mà protocol chỉ định.

## 3. Chương trình A — Cùng một String, nhiều cách mã hóa thành byte

Lưu chương trình hoàn chỉnh vào tệp **`CharsetEncodingDemo.java`**:

```java
import java.nio.charset.StandardCharsets;

public final class CharsetEncodingDemo {
    private static String hex(byte[] data) {
        StringBuilder out = new StringBuilder();
        for (byte b : data) {
            if (out.length() > 0) out.append(' ');
            out.append(String.format("%02X", b & 0xFF));
        }
        return out.toString();
    }

    public static void main(String[] args) {
        String text = "A\u20AC\uD83D\uDE00";
        System.out.println("utf16Units=" + text.length());
        System.out.println("codePoints=" + text.codePointCount(0, text.length()));
        System.out.println("UTF8=" + hex(text.getBytes(StandardCharsets.UTF_8)));
        System.out.println("UTF16BE=" + hex(text.getBytes(StandardCharsets.UTF_16BE)));
        System.out.println("UTF16LE=" + hex(text.getBytes(StandardCharsets.UTF_16LE)));
        System.out.println("UTF16=" + hex(text.getBytes(StandardCharsets.UTF_16)));
        System.out.println("utf8RoundTrip=" +
                text.equals(new String(text.getBytes(StandardCharsets.UTF_8),
                        StandardCharsets.UTF_8)));
        System.out.println("utf16RoundTrip=" +
                text.equals(new String(text.getBytes(StandardCharsets.UTF_16),
                        StandardCharsets.UTF_16)));
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 CharsetEncodingDemo.java
java CharsetEncodingDemo
```

**Stdout đã kiểm tra:**

```text
utf16Units=4
codePoints=3
UTF8=41 E2 82 AC F0 9F 98 80
UTF16BE=00 41 20 AC D8 3D DE 00
UTF16LE=41 00 AC 20 3D D8 00 DE
UTF16=FE FF 00 41 20 AC D8 3D DE 00
utf8RoundTrip=true
utf16RoundTrip=true
```

### 3.1. So sánh kết quả

| Hằng số Java | Đầu dãy byte | Đặc tính |
| --- | --- | --- |
| `StandardCharsets.UTF_8` | `41 E2 82 AC F0 9F 98 80` | Chuỗi byte UTF-8, không cần lựa chọn BE/LE |
| `StandardCharsets.UTF_16BE` | `00 41 20 AC D8 3D DE 00` | Mỗi code unit UTF-16 ghi byte cao trước |
| `StandardCharsets.UTF_16LE` | `41 00 AC 20 3D D8 00 DE` | Mỗi code unit UTF-16 ghi byte thấp trước |
| `StandardCharsets.UTF_16` | `FE FF 00 41 20 AC D8 3D DE 00` | Encoder `UTF_16` của Java ghi BOM big-endian trong ví dụ |

Ở UTF-16BE, code unit `U+0041` được xuất thành `00 41`. Ở UTF-16LE, nó được xuất thành `41 00`. Đây là **cách sắp xếp byte của các code units 16-bit trong một charset cụ thể**, không phải thứ tự byte của mọi trường số khác trong cùng payload.

**Ghi chú:** `UTF_16` (không hậu tố BE/LE) có hành vi BOM theo hợp đồng của charset Java. Không suy từ ví dụ rằng *mọi tệp UTF-16 trên thế giới đều bắt buộc có BOM*, hoặc mọi hệ thống phải ghi big-endian. Muốn giao tiếp ổn định, hai đầu phải thống nhất **charset chính xác** và quy tắc BOM.

### 3.2. Vì sao `String.format("%02X", b & 0xFF)`?

Java `byte` có dấu từ `-128` tới `127`. Mask `& 0xFF` đưa nó về giá trị 0–255 để in đúng hai chữ số hex. Không dùng `Integer.toHexString(b)` trực tiếp để in từng byte khi có giá trị âm, vì có thể cho biểu diễn sign-extended không mong muốn.

Với bài này, `hex` chỉ là hàm hỗ trợ quan sát byte; bản thân nó không thực hiện encode/decode hoặc thay đổi byte order.

### 3.3. Round-trip chỉ đúng khi dùng cùng quy tắc

Hai dòng `utf8RoundTrip=true` và `utf16RoundTrip=true` cho thấy việc encode rồi decode bằng **charset tương ứng** phục hồi đúng chuỗi minh họa. Chúng **không chứng minh** rằng có thể decode byte UTF-8 bằng UTF-16 hoặc ngược lại.

Khi làm việc với dữ liệu tùy ý có thể chứa Unicode surrogate không hợp lệ hoặc ký tự không biểu diễn được trong charset được chọn, hành vi phụ thuộc chính sách encoder/decoder, cần xử lý riêng. Không coi một round-trip thành công với một chuỗi Unicode hợp lệ là chứng minh mọi byte ngoài đời đều hợp lệ.

## 4. Byte order áp dụng cụ thể với số nhiều byte

Một `int` Java có 32 bit. Giá trị ví dụ:

```text
0x01020304

Big-endian:     01 02 03 04
Little-endian:  04 03 02 01
```

**Giá trị số không đổi.** Chỉ có thứ tự các byte trong biểu diễn ngoài bộ nhớ/stream đang được lựa chọn. Trong Java, khi thao tác với `ByteBuffer`:

```java
ByteBuffer buffer = ByteBuffer.allocate(4);
buffer.order(ByteOrder.LITTLE_ENDIAN);
buffer.putInt(0x01020304);
byte[] result = buffer.array(); // 04 03 02 01
```

Đây là mảnh mã minh họa; cần import `java.nio.ByteBuffer` và `java.nio.ByteOrder`. Cờ byte order của buffer điều khiển các thao tác **đọc/ghi giá trị nhiều byte** tương ứng như `putShort`, `putInt`, `putLong`, `putChar` và các `get...` tương ứng. Còn `put(byte[])` **đặt các byte đã có vào buffer**, không tự encode lại ký tự hay đảo dãy byte nguồn.

### 4.1. Chương trình B — `NumberByteOrderDemo.java`

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;

public final class NumberByteOrderDemo {
    private static String hex(byte[] data) {
        StringBuilder out = new StringBuilder();
        for (byte b : data) {
            if (out.length() > 0) out.append(' ');
            out.append(String.format("%02X", b & 0xFF));
        }
        return out.toString();
    }

    public static void main(String[] args) {
        int number = 0x01020304;
        byte[] big = ByteBuffer.allocate(4).order(ByteOrder.BIG_ENDIAN)
                .putInt(number).array();
        byte[] little = ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN)
                .putInt(number).array();
        System.out.println("big=" + hex(big));
        System.out.println("little=" + hex(little));
        System.out.println("readBigCorrect=" + ByteBuffer.wrap(big)
                .order(ByteOrder.BIG_ENDIAN).getInt());
        System.out.println("readBigAsLittle=" + ByteBuffer.wrap(big)
                .order(ByteOrder.LITTLE_ENDIAN).getInt());
        ByteBuffer mixed = ByteBuffer.allocate(6)
                .order(ByteOrder.LITTLE_ENDIAN);
        mixed.putInt(number);
        mixed.put("A".getBytes(StandardCharsets.UTF_16BE));
        System.out.println("mixedLittleIntBigText=" + hex(mixed.array()));
        ByteBuffer codeUnit = ByteBuffer.allocate(2)
                .order(ByteOrder.LITTLE_ENDIAN);
        codeUnit.putChar('A');
        System.out.println("putCharLittle=" + hex(codeUnit.array()));
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 NumberByteOrderDemo.java
java NumberByteOrderDemo
```

**Stdout chính xác:**

```text
big=01 02 03 04
little=04 03 02 01
readBigCorrect=16909060
readBigAsLittle=67305985
mixedLittleIntBigText=04 03 02 01 00 41
putCharLittle=41 00
```

### 4.2. Nhận xét quan trọng

- `big` và `little` khác byte order nhưng được tạo từ **cùng `int number`**.
- `readBigCorrect` đọc `01 02 03 04` theo big-endian và nhận giá trị thập phân `16909060`, tức `0x01020304`.
- `readBigAsLittle` đọc **cùng bốn byte** theo little-endian và nhận giá trị `67305985`, tức `0x04030201`. Đây là lỗi endian kinh điển.
- `mixed` được cấu hình `LITTLE_ENDIAN`. `putInt(number)` ghi `04 03 02 01`, nhưng `put("A".getBytes(UTF_16BE))` **không** đảo bytes từ encoder; nó giữ `00 41`. Vì vậy tổng là `04 03 02 01 00 41`.
- `putChar('A')` ghi một **UTF-16 code unit 16-bit** theo byte order của buffer, nên trong little-endian tạo `41 00`. Điều này **không biến `ByteBuffer.putChar` thành một charset encoder cho Unicode text tùy ý**, đặc biệt với ký tự cần surrogate pair.

### 4.3. Vì sao ví dụ mixed hợp lệ?

Bởi binary record có thể định nghĩa từng trường khác nhau:

```text
Trường 1: 4 byte của int, little-endian
Trường 2: 2 byte của một code unit/text UTF-16BE
```

Không có luật “cùng một message thì mọi trường bắt buộc có cùng endian”. Có format định nghĩa đồng nhất các trường numeric; có format định nghĩa riêng từng nhóm. Điều quan trọng là **đặc tả rõ mỗi trường** và encoder/decoder hai phía làm giống nhau.

## 5. BOM (Byte Order Mark) là gì và không phải là gì?

**BOM** là một dấu hiệu byte được dùng trong một số biểu diễn Unicode để giúp nhận biết thứ tự byte hoặc báo hiệu cách diễn giải dữ liệu. Code point liên quan là `U+FEFF`.

Với UTF-16, các byte đầu thường được giải thích:

| Hai byte đầu | Ý nghĩa thông dụng với UTF-16 có BOM |
| --- | --- |
| `FE FF` | BOM báo big-endian |
| `FF FE` | BOM báo little-endian |

Nhưng **BOM không phải một nhãn tổng quát** cho mọi trường trong cả file. Ví dụ một record có header 4 byte little-endian và payload UTF-16BE có BOM: BOM liên quan phần text UTF-16, không tự thay đổi byte order của header 4 byte.

### 5.1. Java `UTF_16` và `UTF_16BE/LE` khác nhau

Trong các charset chuẩn của Java:

- `StandardCharsets.UTF_16` là dạng UTF-16 có quy tắc BOM. Java decoder của charset này nhận BOM BE/LE để chọn byte order; khi không có BOM, nó sử dụng mặc định big-endian theo hợp đồng charset Java.
- `StandardCharsets.UTF_16BE` chỉ định byte order lớn trước một cách tường minh.
- `StandardCharsets.UTF_16LE` chỉ định byte order nhỏ trước một cách tường minh.
- Với decoder `UTF_16BE`/`UTF_16LE`, **không nên giả định BOM tự động bị bỏ** theo cách decoder `UTF_16` xử lý: một `U+FEFF` ở đầu có thể được giải mã thành **ký tự trong `String`**.
- Khi dùng encoder `UTF_16` của Java, output minh họa bắt đầu bằng `FE FF`. Với `UTF_16BE` và `UTF_16LE`, ví dụ không phát sinh BOM ở đầu.

Điểm này cần được kiểm tra trên **định dạng thực tế**. Không dựa vào việc tên charset “na ná” nhau rồi bỏ qua vài byte đầu trong mọi trường hợp.

### 5.2. Chương trình C — `BomDecodeDemo.java`

```java
import java.nio.charset.StandardCharsets;

public final class BomDecodeDemo {
    private static String points(String text) {
        StringBuilder sb = new StringBuilder();
        text.codePoints().forEach(cp -> {
            if (sb.length() > 0) sb.append(' ');
            sb.append(String.format("U+%04X", cp));
        });
        return sb.toString();
    }

    public static void main(String[] args) {
        byte[] beBom = {(byte) 0xFE, (byte) 0xFF, 0, 65};
        byte[] leBom = {(byte) 0xFF, (byte) 0xFE, 65, 0};
        System.out.println("genericBE=" + points(
                new String(beBom, StandardCharsets.UTF_16)));
        System.out.println("genericLE=" + points(
                new String(leBom, StandardCharsets.UTF_16)));
        System.out.println("explicitLE=" + points(
                new String(leBom, StandardCharsets.UTF_16LE)));
        System.out.println("wrongEndian=" + points(
                new String(new byte[]{0, 65}, StandardCharsets.UTF_16LE)));
        System.out.println("unmarkedGeneric=" + points(
                new String(new byte[]{0, 65}, StandardCharsets.UTF_16)));
        System.out.println("utf8BOM=" + points(new String(
                new byte[]{(byte) 0xEF, (byte) 0xBB, (byte) 0xBF, 65},
                StandardCharsets.UTF_8)));
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 BomDecodeDemo.java
java BomDecodeDemo
```

**Stdout:**

```text
genericBE=U+0041
genericLE=U+0041
explicitLE=U+FEFF U+0041
wrongEndian=U+4100
unmarkedGeneric=U+0041
utf8BOM=U+FEFF U+0041
```

### 5.3. Phân tích từng trường hợp

1. `beBom` có `FE FF 00 41`: decoder `UTF_16` nhận BOM BE và trả chuỗi chỉ chứa `A`, nên biểu diễn code points là `U+0041`.
2. `leBom` có `FF FE 41 00`: decoder `UTF_16` nhận BOM LE và vẫn trả `A`.
3. Dùng **decoder `UTF_16LE` tường minh** với `FF FE 41 00`: output gồm `U+FEFF` rồi `A`. Dấu BOM ở đây không tự được loại bỏ như khi dùng `UTF_16`.
4. Đọc `00 41` bằng `UTF_16LE` diễn giải code unit thành `U+4100`, **không phải `U+0041`**. Đây là lỗi thứ tự byte **trong định dạng UTF-16**.
5. Đọc `00 41` không BOM bằng `UTF_16` cho `A`, phản ánh quy tắc mặc định BE của charset Java khi không có dấu BOM.
6. `EF BB BF` là dạng byte được gọi là **UTF-8 BOM/signature**. Với decoder UTF-8 của Java trong thí nghiệm, nó được giải mã thành code point `U+FEFF` đứng trước `A`. UTF-8 không cần BOM để xác định BE/LE, và không được hiểu `EF BB BF` là một dấu “chọn little-endian” cho UTF-8.

**Lưu ý liên thông:** Có ứng dụng chủ động bỏ UTF-8 BOM trước khi parse text; có ứng dụng bảo toàn `U+FEFF`. Nếu định dạng đầu vào có quy tắc về signature, hãy làm đúng quy tắc đó. Không xóa mọi `U+FEFF` trong cả chuỗi vì một ký tự `U+FEFF` không mặc nhiên là metadata ở mọi vị trí.

## 6. Mojibake: giải mã đúng byte nhưng dùng sai charset

**Mojibake** là hiện tượng văn bản hiển thị sai vì byte được diễn giải bằng charset không đúng. Nó **khác** với lỗi đọc một số `int` sai byte order.

Ví dụ ký tự `€` có UTF-8 bytes:

```text
E2 82 AC
```

Nếu bên nhận dùng charset một-byte như ISO-8859-1 để decode ba byte đó, nó sẽ tạo ba code points khác, chứ không tạo `U+20AC`. Ví dụ này dùng ISO-8859-1 **chỉ để minh họa đọc sai charset và tương thích dữ liệu có sẵn**, không phải khuyến nghị chọn mã hóa đó cho ứng dụng mới.

### 6.1. Hai loại sai khác nhau

| Sai lệch | Byte được đọc | Chọn sai | Hệ quả |
| --- | --- | --- | --- |
| Mojibake | `E2 82 AC` | Decode UTF-8 bytes bằng ISO-8859-1 | Các code points khác với `€` |
| Sai endian số nguyên | `01 02 03 04` | Đọc theo little thay vì big | `0x04030201` thay cho `0x01020304` |
| Sai endian của UTF-16 | `00 41` | Decode UTF-16LE thay vì UTF-16BE | `U+4100` thay cho `U+0041` |
| Hiểu nhầm BOM | `FF FE 41 00` | Dùng decoder/contract không phù hợp | Có thể xuất hiện `U+FEFF` trong text hoặc decode sai |
| Header độ dài sai endian | `03 00 00 00` | Đọc big thay vì little | 50.331.648 thay vì 3 |

Cả hai lỗi đều xảy ra trên **byte array**, nhưng câu hỏi để sửa khác nhau. Đừng vá lỗi mojibake bằng đảo byte một cách thử-sai; hãy xác định đúng **charset gốc**. Đừng vá trường số sai bằng thay `UTF_8` thành `UTF_16LE`; hãy dùng đúng byte order khi đọc số.

## 7. Chương trình D — Decode sai charset và xử lý byte UTF-8 hỏng

Lưu thành **`DecoderMismatchDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public final class DecoderMismatchDemo {
    private static String hex(byte[] data) {
        StringBuilder out = new StringBuilder();
        for (byte b : data) {
            if (out.length() > 0) out.append(' ');
            out.append(String.format("%02X", b & 0xFF));
        }
        return out.toString();
    }

    private static String points(String text) {
        StringBuilder sb = new StringBuilder();
        text.codePoints().forEach(cp -> {
            if (sb.length() > 0) sb.append(' ');
            sb.append(String.format("U+%04X", cp));
        });
        return sb.toString();
    }

    public static void main(String[] args) {
        byte[] utf8 = "\u20AC".getBytes(StandardCharsets.UTF_8);
        String correct = new String(utf8, StandardCharsets.UTF_8);
        String wrong = new String(utf8, StandardCharsets.ISO_8859_1);
        System.out.println("utf8Bytes=" + hex(utf8));
        System.out.println("correct=" + points(correct));
        System.out.println("wrong=" + points(wrong));
        System.out.println("wrongReencoded=" +
                hex(wrong.getBytes(StandardCharsets.UTF_8)));

        byte[] malformed = {(byte) 0xC3, (byte) 0x28};
        System.out.println("replacement=" +
                points(new String(malformed, StandardCharsets.UTF_8)));
        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(malformed));
            System.out.println("unexpected-success");
        } catch (CharacterCodingException e) {
            System.out.println("strictFailure=" + e.getClass().getSimpleName());
        }
    }
}
```

Lệnh chạy:

```bash
javac --release 17 -encoding UTF-8 DecoderMismatchDemo.java
java DecoderMismatchDemo
```

**Stdout đúng:**

```text
utf8Bytes=E2 82 AC
correct=U+20AC
wrong=U+00E2 U+0082 U+00AC
wrongReencoded=C3 A2 C2 82 C2 AC
replacement=U+FFFD U+0028
strictFailure=MalformedInputException
```

### 7.1. Giải thích lỗi giải mã

- Khi dùng UTF-8 đúng, `E2 82 AC` cho `U+20AC`.
- Khi giải mã như ISO-8859-1, từng byte trở thành code point độc lập: `U+00E2`, `U+0082`, `U+00AC`.
- Sau đó encode chuỗi sai ấy bằng UTF-8, bytes trở thành `C3 A2 C2 82 C2 AC`. **Việc re-encode không tự chữa mojibake**; nó chỉ biến các code points đang sai thành một chuỗi byte khác.
- Với `C3 28`, byte `C3` báo đầu một sequence UTF-8 cần byte tiếp theo hợp lệ; `28` không thỏa mãn.
- `new String(malformed, UTF_8)` dùng hành vi thay thế cho byte hỏng theo API, tạo `U+FFFD U+0028` trong ví dụ.
- `CharsetDecoder` cấu hình `REPORT` báo lỗi `MalformedInputException` thay vì âm thầm thay dữ liệu. `REPORT` đặc biệt phù hợp khi **định dạng bắt buộc UTF-8 hợp lệ**, ví dụ nạp dữ liệu cần bảo toàn tính chính xác hoặc kiểm tra dữ liệu đầu vào.

### 7.2. Byte không hợp lệ không giống “sai endian”

Mojibake do dùng một charset khác có thể tạo **chuỗi Unicode hợp lệ nhưng sai nghĩa** mà không có exception. Ngược lại, một chuỗi byte không hợp lệ theo UTF-8 có thể bị decoder thay bằng `U+FFFD` hoặc từ chối tùy chính sách.

Đảo byte hoặc đổi `ByteBuffer.order` **không sửa** được hai vấn đề ấy. Với dữ liệu do bên ngoài cung cấp, xác định charset từ contract, header được định nghĩa, HTTP metadata đáng tin cậy hoặc định dạng tài liệu chính thức; đừng tự đoán từ một vài ký tự hiển thị.

### 7.3. Khi nào nên dùng decoder strict?

- Dữ liệu phải tuân một định dạng xác định, không cho phép mất ký tự.
- Dữ liệu đầu vào không tin cậy, cần từ chối encoding lỗi trước khi parse.
- Phần checksum/signature hoặc xử lý định danh đòi hỏi giữ chính xác các code points.

Còn với trình xem văn bản hướng tới người dùng, một chính sách replacement có thể chấp nhận được nếu đã được xác định. Chọn theo contract, không coi “không ném exception” đồng nghĩa dữ liệu đúng.

## 8. Bản ghi hỗn hợp: header số nguyên và payload text

Một định dạng nhị phân thực tế thường có ít nhất hai phần:

```text
[length: 4 byte little-endian] [payload: UTF-8 text bytes]
```

Hai quy tắc độc lập:

1. `length` là **số byte của payload**, được mã hóa thành một `int` 4 byte theo little-endian.
2. `payload` là **UTF-8 bytes** được tạo từ text; thứ tự byte đúng theo UTF-8, không bị `ByteBuffer.order` đảo lại.

Nếu sender dùng little-endian cho length nhưng receiver đọc big-endian, receiver có thể nghĩ một payload chỉ 3 byte dài 50.331.648 byte. Đây không phải lỗi bảng mã; đây là **lỗi đọc trường số**.

### 8.1. Chương trình E — `MixedRecordDemo.java`

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;

public final class MixedRecordDemo {
    private static String hex(byte[] data) {
        StringBuilder out = new StringBuilder();
        for (byte b : data) {
            if (out.length() > 0) out.append(' ');
            out.append(String.format("%02X", b & 0xFF));
        }
        return out.toString();
    }

    private static byte[] encode(String text) {
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(4 + payload.length)
                .order(ByteOrder.LITTLE_ENDIAN)
                .putInt(payload.length)
                .put(payload)
                .array();
    }

    private static String decode(byte[] record) {
        ByteBuffer buffer = ByteBuffer.wrap(record)
                .order(ByteOrder.LITTLE_ENDIAN);
        if (buffer.remaining() < 4) {
            throw new IllegalArgumentException("header missing");
        }
        int length = buffer.getInt();
        if (length < 0 || length > buffer.remaining()) {
            throw new IllegalArgumentException("bad length");
        }
        byte[] payload = new byte[length];
        buffer.get(payload);
        if (buffer.hasRemaining()) {
            throw new IllegalArgumentException("trailing data");
        }
        return new String(payload, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) {
        String input = "C\u00E0";
        byte[] record = encode(input);
        System.out.println("record=" + hex(record));
        System.out.println("decodedMatches=" + input.equals(decode(record)));
        System.out.println("bigEndianHeader=" + ByteBuffer.wrap(record)
                .order(ByteOrder.BIG_ENDIAN).getInt());
        try {
            byte[] bad = record.clone();
            bad[0] = 50;
            decode(bad);
            System.out.println("unexpected-success");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalidHeader=" + ex.getMessage());
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 MixedRecordDemo.java
java MixedRecordDemo
```

**Stdout:**

```text
record=03 00 00 00 43 C3 A0
decodedMatches=true
bigEndianHeader=50331648
invalidHeader=bad length
```

### 8.2. Tại sao mã hóa ra đúng byte ấy?

`input` là `"Cà"`:

- `C` tương ứng byte UTF-8 `43`.
- `à` (U+00E0) tương ứng hai byte UTF-8 `C3 A0`.
- Payload vì vậy dài **3 byte**, dù `String.length() == 2` UTF-16 code units và có 2 code points.
- Header `int length = 3` được ghi little-endian thành `03 00 00 00`.
- `buffer.put(payload)` chép nguyên bytes UTF-8: `43 C3 A0`.

Kết quả:

```text
03 00 00 00 | 43 C3 A0
  int LE    | text UTF-8
```

Trong ví dụ, `bigEndianHeader` đọc bốn byte đầu theo big-endian, ra `0x03000000` = `50331648`. **Chọn đúng charset UTF-8 cho phần text không sửa được lỗi đọc length**.

### 8.3. Bảo vệ khi đọc header từ dữ liệu không tin cậy

Trước khi allocate `new byte[length]`, phải kiểm tra:

- Bản ghi có tối thiểu đủ 4 byte cho header hay không.
- `length` không âm.
- `length` không vượt số byte còn lại.
- Có một **giới hạn kích thước ứng dụng** hay không; ví dụ vài megabyte thay vì tin mù quáng dữ liệu ngoài.
- Protocol có cho phép trailing bytes không; bài demo từ chối chúng.
- Text có phải UTF-8 hợp lệ không; code demo dùng `new String` (có replacement policy), nên nếu cần strict UTF-8 phải thay bằng decoder với `CodingErrorAction.REPORT`.

**Chú ý bổ sung cho ví dụ demo:** `ByteBuffer.allocate(4 + payload.length)` dành cho payload nhỏ được kiểm soát. Trong ứng dụng với input rất lớn, cần giới hạn `payload.length` và tránh overflow khi cộng kích thước trước khi cấp phát.

### 8.4. Byte order không đổi khi gọi `buffer.put(payload)`

Dù buffer đã đặt `LITTLE_ENDIAN`, thao tác `put(byte[])` chỉ chép nguyên chuỗi byte. Nó không biết `payload` là UTF-8, không biết các ký tự Unicode là gì và không tự chuyển từ UTF-8 sang UTF-16LE.

Nếu encoder và decoder hai phía không nhất quán, nội dung text có thể lỗi ngay cả khi header length được đọc đúng. Vì vậy cần test **riêng** trường số và payload.

## 9. Về `ByteBuffer.putChar` và UTF-16: gần nhau nhưng không tương đương hoàn toàn

Một ký tự Java `char` là một **UTF-16 code unit 16-bit**. `ByteBuffer.putChar` ghi **hai byte** của code unit ấy theo byte order của buffer.

```java
ByteBuffer b = ByteBuffer.allocate(2)
        .order(ByteOrder.LITTLE_ENDIAN);
b.putChar('A'); // 41 00
```

Đây là mảnh code minh họa, cần import `ByteBuffer` và `ByteOrder`. Với `'A'` thuộc BMP, kết quả giống hai byte UTF-16LE của ký tự `A`. Tuy nhiên:

- Một Unicode code point ngoài BMP dùng **hai `char` (surrogate pair)**.
- `putChar` chỉ ghi một code unit; nó **không tự phân tách code point thành surrogate pair** như một charset encoder hoàn chỉnh.
- `putChar` không tự quản lý BOM hoặc chính sách đối với dữ liệu Unicode không hợp lệ.
- Khi bạn cần encode một `String` sang UTF-16LE, nên dùng `text.getBytes(StandardCharsets.UTF_16LE)` hoặc `CharsetEncoder` tương ứng.

Không đánh đồng “chọn endian cho `char`” với “thiết kế hệ thống Unicode đúng hoàn toàn”.

## 10. Charset mặc định và byte order mặc định: đừng phụ thuộc ngầm

Trong code Java có những API cho phép bỏ qua tham số charset, ví dụ `String.getBytes()` và `new String(byte[])`. Các overload ấy sử dụng **default charset** của môi trường/runtime theo phiên bản và cấu hình; với dữ liệu truyền giữa hệ thống, nên **tránh dựa vào mặc định**.

Hãy viết rõ:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
```

Mảnh minh họa này cần `text` và import `StandardCharsets`. Trong chương trình mới, Unicode text trao đổi qua mạng/tệp thường chọn UTF-8 khi định dạng cho phép. Nếu hợp đồng bên ngoài yêu cầu UTF-16LE hoặc một charset cụ thể khác, phải tuân theo hợp đồng ấy một cách tường minh.

Với `ByteBuffer`, byte order mặc định của một buffer mới thường là `BIG_ENDIAN` theo hợp đồng API, nhưng khi format yêu cầu một thứ tự cụ thể, **luôn gọi `order(...)` rõ ràng tại nơi tạo/đọc buffer**:

```java
ByteBuffer out = ByteBuffer.allocate(4)
        .order(ByteOrder.LITTLE_ENDIAN);
out.putInt(42);

ByteBuffer in = ByteBuffer.wrap(out.array())
        .order(ByteOrder.LITTLE_ENDIAN);
int value = in.getInt(); // 42
```

Đây là đoạn minh họa. Mục tiêu không phải “mọi ứng dụng đều chọn little-endian”; mục tiêu là **sender và receiver cùng tuân một format**.

### 10.1. Không suy endian từ hệ điều hành hoặc CPU

Một protocol có thể quy định big-endian bất kể CPU của máy gửi là little-endian. `ByteOrder.nativeOrder()` cho biết thứ tự byte native của môi trường cụ thể, nhưng **không phải lời thay thế cho đặc tả protocol**.

Đọc file/packet bằng `nativeOrder()` chỉ vì máy đang chạy trên CPU nào đó sẽ gây nguy cơ lỗi khi chuyển nền tảng hoặc giao tiếp đa hệ thống. Luôn ưu tiên byte order được protocol quy định.

### 10.2. Không dựa vào biểu diễn hex trong debugger để suy charset

Một dãy byte có thể là:

- UTF-8 text.
- UTF-16 code units.
- Header numeric.
- Dữ liệu nén/mã hóa.
- Sequence nhị phân hỗn hợp chứa nhiều trường.

Muốn hiểu nghĩa, phải có **schema**. Chỉ có byte hex không đủ kết luận chúng là text hay là số nguyên.

## 11. I/O tệp văn bản và tệp nhị phân: chọn API phù hợp

### 11.1. Khi tệp là văn bản

Dùng các API text có charset xác định, chẳng hạn:

```java
Path file = Path.of("message.txt");
Files.writeString(file, text, StandardCharsets.UTF_8);
String loaded = Files.readString(file, StandardCharsets.UTF_8);
```

Mảnh minh họa cần import `java.nio.file.Path`, `java.nio.file.Files`, `java.nio.charset.StandardCharsets` và biến `text`. `Files.writeString`/`readString` có trên JDK hiện đại; mục đích là tránh sự mơ hồ charset. Khi ứng dụng xử lý tệp lớn, có thể dùng buffered reader/writer và quản lý tài nguyên bằng try-with-resources.

Với text UTF-8 như trên, không cần thiết lập `ByteOrder.LITTLE_ENDIAN` cho `Files.writeString`. Byte order của số nguyên không phải một tham số của phép encode UTF-8.

### 11.2. Khi tệp là bản ghi nhị phân

Dùng `ByteBuffer` hoặc codec rõ ràng để ghi các trường numeric, và encoder cho trường text:

```java
byte[] nameBytes = name.getBytes(StandardCharsets.UTF_8);
ByteBuffer out = ByteBuffer.allocate(4 + nameBytes.length)
        .order(ByteOrder.LITTLE_ENDIAN);
out.putInt(nameBytes.length);
out.put(nameBytes);
byte[] record = out.array();
```

Đây là mảnh minh họa, cần `name` và import `ByteBuffer`, `ByteOrder`, `StandardCharsets`. Với dữ liệu ngoài phạm vi demo, bổ sung giới hạn payload/overflow như mục 8.

**Lưu ý quan trọng:** Ghi `String.length()` vào header rồi ghi UTF-8 bytes là một lỗi phổ biến. Nếu chuỗi có ký tự multibyte, `length()` không bằng số byte. Phải ghi `nameBytes.length`, trừ khi protocol thực sự định nghĩa length theo đơn vị khác và decoder cũng tuân đúng.

### 11.3. Khi tệp chứa cả text lẫn các trường nhị phân

Có thể có:

```text
Magic bytes | version | length (int, LE) | UTF-8 payload | checksum
```

Hãy ghi rõ **byte offset, width, endian cho numeric fields, charset và độ dài byte cho payload**. Chỉ ghi “đây là file UTF-8” là chưa đủ, vì phần header hoặc checksum có thể không phải text. Ngược lại, chỉ ghi “file little-endian” cũng không đủ để giải mã payload text.

## 12. Một số lỗi hiểu sai thường gặp

### 12.1. “UTF-8 little-endian” và “UTF-8 big-endian”

UTF-8 không định nghĩa hai phiên bản BE/LE như UTF-16. Đảo byte UTF-8 sẽ thay đổi hoặc làm hỏng chuỗi mã hóa. Nếu format có số nguyên little-endian bên cạnh UTF-8, hãy diễn đạt “header little-endian; payload UTF-8”, không gán byte order cho chính UTF-8.

### 12.2. “Đổi `ByteBuffer.order` là đổi encoding của String”

Không đúng. `ByteBuffer.order` ảnh hưởng các `get/put` nhiều byte tương ứng của buffer, không thay cách `StandardCharsets.UTF_8`/`UTF_16BE` mã hóa string. `buffer.put(encodedBytes)` chép dữ liệu nguyên vẹn.

### 12.3. “BOM UTF-8 cho biết file đang little-endian”

Sai. `EF BB BF` là dấu UTF-8 signature/BOM trong một số tệp, **không biểu thị big/little-endian** cho UTF-8. Trên decoder UTF-8 của Java trong ví dụ, nó xuất hiện dưới dạng `U+FEFF`.

### 12.4. “UTF-16 lúc nào cũng có BOM”

Không đúng. `UTF_16BE` và `UTF_16LE` là những lựa chọn tường minh; nhiều format dựa trên endian đã được định nghĩa mà không cần BOM. Với Java `UTF_16` generic, decoder có quy tắc BOM/mặc định BE riêng.

### 12.5. “ByteBuffer little-endian làm UTF-16LE tự động”

Sai. Nếu dùng `put(byte[])` với UTF-16BE bytes, buffer sẽ chép chúng nguyên vẹn. Nếu dùng `putChar`, bạn chỉ đang ghi code unit theo byte order của buffer, không quản lý toàn bộ encoding/BOM/Unicode text.

### 12.6. “String có ba ký tự thì cần ba byte UTF-8”

Không đúng. Ký tự khác nhau có kích thước UTF-8 khác nhau. `"A€😀"` có 3 code points nhưng 8 byte UTF-8; `String.length()==4` vì có surrogate pair. Nếu header ghi số byte, lấy `encodedBytes.length`.

### 12.7. “`new String(bytes)` luôn đọc UTF-8 đúng”

Không nên dựa vào overload mặc định khi dữ liệu phải tương thích liên hệ thống. Chỉ định charset rõ ràng. Với dữ liệu không hợp lệ, chọn decoder policy đúng chứ không giả định một overload bất kỳ sẽ luôn báo lỗi.

### 12.8. “Mojibake được sửa bằng đảo byte”

Thông thường không. Mojibake là vấn đề dùng sai charset hoặc đã decode/encode sai qua nhiều bước. Đảo các byte theo cặp không khôi phục mặc định được code points gốc. Phải hiểu đường truyền và format gốc.

### 12.9. “Đọc sai số header nhưng charset đúng thì record vẫn ổn”

Sai. Header length sai endian có thể khiến parser cấp phát quá nhiều, báo thiếu dữ liệu hoặc cắt payload. Việc decode text đúng không sửa được length/offset.

### 12.10. “Lỗi decode luôn ném exception”

Không đúng. Nhiều cách decode văn bản có **replacement policy** và tạo ký tự `U+FFFD` cho bytes hỏng. Nếu dữ liệu cần validation nghiêm, cấu hình `CharsetDecoder` với `CodingErrorAction.REPORT`.

### 12.11. “Native order là order của protocol”

Không đúng. Một format được xác định độc lập với CPU. Không chọn `ByteOrder.nativeOrder()` để parse dữ liệu ngoài chỉ vì nó có vẻ tối ưu trên máy hiện tại.

### 12.12. “Chọn UTF-16LE cho text nghĩa là mọi int cùng little-endian”

Không có suy luận ấy. Một record hỗn hợp có thể có quy tắc riêng cho các trường. Cần schema chi tiết thay vì suy từ charset của một trường.

## 13. Ma trận kiểm thử byte-level

Bảng sau tóm tắt các vector đã được kiểm chứng:

| Input / cách xử lý | Byte hoặc giá trị quan sát | Kết luận |
| --- | --- | --- |
| `"A€😀"` encode UTF-8 | `41 E2 82 AC F0 9F 98 80` | Không cần endian cho UTF-8 |
| Cùng string encode UTF-16BE | `00 41 20 AC D8 3D DE 00` | Byte cao của code unit trước |
| Cùng string encode UTF-16LE | `41 00 AC 20 3D D8 00 DE` | Byte thấp của code unit trước |
| Cùng string encode Java `UTF_16` | `FE FF 00 41 20 AC D8 3D DE 00` | Có BOM BE trong output Java |
| `FE FF 00 41` decode bằng Java `UTF_16` | `U+0041` | Nhận BOM BE |
| `FF FE 41 00` decode bằng Java `UTF_16` | `U+0041` | Nhận BOM LE |
| `FF FE 41 00` decode bằng Java `UTF_16LE` | `U+FEFF U+0041` | Explicit LE không tự bỏ U+FEFF như generic |
| `EF BB BF 41` decode UTF-8 trong Java demo | `U+FEFF U+0041` | UTF-8 BOM không biểu thị endian |
| `0x01020304` ghi `putInt` BE | `01 02 03 04` | Numeric big-endian |
| `0x01020304` ghi `putInt` LE | `04 03 02 01` | Numeric little-endian |
| `01 02 03 04` đọc `getInt` LE | `0x04030201` | Sai endian gây sai số |
| `"€"` UTF-8 giải mã ISO-8859-1 | `U+00E2 U+0082 U+00AC` | Mojibake do sai charset |
| `C3 28` decode UTF-8 theo replacement | `U+FFFD U+0028` | Byte UTF-8 không hợp lệ được thay thế |
| `C3 28` decode UTF-8 strict | `MalformedInputException` | Strict validation phát hiện lỗi |
| `"Cà"` ghi length int LE + payload UTF-8 | `03 00 00 00 43 C3 A0` | Header và text có hai quy tắc độc lập |
| Đọc `03 00 00 00` theo BE | `50331648` | Header sai endian có thể rất nguy hiểm |

### 13.1. Quy trình viết test

1. Dùng một test vector **chỉ chứa ASCII** để xác nhận baseline.
2. Thêm ký tự nhiều byte UTF-8 (`€`, `à`) và code point ngoài BMP (`😀`).
3. Kiểm tra output bằng **hex bytes**, không chỉ chuỗi hiển thị trên terminal; terminal có cấu hình charset riêng.
4. Kiểm tra cả UTF-16BE, UTF-16LE và UTF-16 có/không BOM theo contract.
5. Với số nguyên, kiểm tra giá trị `0x01020304` để dễ nhìn thứ tự byte thay vì `0` hoặc `1` (vì các giá trị nhỏ dễ che lỗi endian).
6. Tạo parser record vừa đúng vừa sai byte order; bảo đảm chặn header length ngoài giới hạn.
7. Tạo malformed UTF-8 và xác minh chính sách replacement hoặc REPORT.
8. Thực hiện round-trip encode/decode đúng charset; không xem nó là bằng chứng tương tác đa ngôn ngữ khi chưa thử với đầu ngoài.
9. Khi có hệ thống ngoài Java, sử dụng cùng một **test vector hex công khai**, xác minh byte order và charset của từng field.
10. Kiểm tra metadata/version/width nếu format thực sự cần, không chỉ nhìn kết quả String.

### 13.2. Thời điểm so sánh byte và thời điểm so sánh text

Nếu cần kiểm chứng **giao thức**, so sánh byte đã encode với expected hex. Nếu chỉ kiểm tra ý nghĩa văn bản sau quá trình decode có lossless contract, so sánh `String.equals` có thể đủ cho nội dung — nhưng phải biết decoder đã dùng đúng charset và không âm thầm thay ký tự hỏng.

Nếu giao thức có BOM, việc so raw bytes vẫn cần xét BOM hợp lệ theo contract. Hai payload có cùng text nhưng khác BOM hoặc byte order có thể **không bằng nhau ở mức byte**, dù được decoder phù hợp diễn giải thành text giống nhau.

## 14. Thực hành tại dự án: checklist thiết kế API

Trước khi viết một adapter đọc/ghi file/socket:

- [ ] Đã phân biệt source là text, numeric binary hay mixed record.
- [ ] Đã chọn charset **tường minh** cho mỗi trường text.
- [ ] Không suy byte length từ `String.length()` khi dùng UTF-8.
- [ ] Đã chỉ định byte order tường minh cho các trường có nhiều byte.
- [ ] Không dùng `ByteOrder.nativeOrder()` thay cho contract truyền tải.
- [ ] Nếu có UTF-16, đã xác định BE/LE, BOM, và hành vi với input không BOM.
- [ ] Nếu có UTF-8 BOM, đã xác định giữ/bỏ signature đúng theo spec.
- [ ] Đã kiểm tra các ký tự ngoài ASCII và ngoài BMP.
- [ ] Header length được kiểm tra âm, vượt buffer, vượt quota, overflow và trailing data.
- [ ] Có chính sách với malformed/unmappable sequences (REPORT hoặc replacement) theo hợp đồng.
- [ ] Có test vector byte-level cho số `0x01020304` và text đa ngôn ngữ.
- [ ] Không đảo byte của text UTF-8 khi xử lý endian của header.
- [ ] Có test sender → receiver của đúng API/format đang sử dụng.
- [ ] Với dữ liệu quan trọng, không coi byte-stream hiển thị đúng một lần là đủ; có automated regression tests.

## 15. Bài tập tự luyện

**Bài 1 — Hai khái niệm.** Giải thích bằng một câu cho từng việc: chọn `StandardCharsets.UTF_8` và chọn `ByteOrder.LITTLE_ENDIAN`. Vì sao chúng có thể được dùng trong cùng một hàm serialize?

**Bài 2 — Tính byte.** Dự đoán bytes của `"A€"` khi encode UTF-8, UTF-16BE, UTF-16LE. Chạy `CharsetEncodingDemo` để đối chiếu.

**Bài 3 — Code point và code unit.** Với `"A€😀"`, tại sao có 3 code points nhưng `String.length() == 4`? Kết quả UTF-8 có bao nhiêu byte?

**Bài 4 — Header endian.** Viết lại `NumberByteOrderDemo` với `0x0A0B0C0D`. Dự đoán byte BE/LE và giá trị nhận được khi dùng decoder sai endian.

**Bài 5 — BOM UTF-16.** Vì sao `new String(FF FE 41 00, UTF_16)` và `new String(FF FE 41 00, UTF_16LE)` cho số code points khác nhau trong thí nghiệm Java? Nêu rõ vai trò `U+FEFF`.

**Bài 6 — BOM UTF-8.** Dữ liệu `EF BB BF 41` có chứa một ký tự `U+FEFF` khi decode bằng Java `UTF_8`. Bạn sẽ xử lý dấu này thế nào nếu một format chỉ cho phép chữ `A` và không cho signature?

**Bài 7 — Mojibake.** Lấy UTF-8 bytes của `€` và decode bằng ISO-8859-1 như phản ví dụ. So code points và bytes sau khi encode lại bằng UTF-8. Vì sao re-encode không tự khôi phục dữ liệu gốc?

**Bài 8 — Strict decoding.** Thử UTF-8 bytes `C3 28`. So `new String(bytes, UTF_8)` với `UTF_8.newDecoder().onMalformedInput(REPORT)`. Khi nào mỗi chính sách phù hợp?

**Bài 9 — Mixed record.** Sửa `MixedRecordDemo` để thay length 4 byte bằng big-endian, đồng thời đổi decoder đúng theo contract. Payload UTF-8 có cần thay đổi byte order không?

**Bài 10 — Sửa lỗi header.** Một receiver nhận `03 00 00 00 43 C3 A0` nhưng đọc 4 byte đầu thành `50331648`. Xác định lỗi ở charset hay byte order; vì sao không nên allocate mảng theo con số sai ấy?

**Bài 11 — Interoperability.** Một service khác Java gửi `UTF-16LE` không BOM. Hãy chọn decoder phù hợp và test với `41 00 AC 20`. Nếu người viết dùng `UTF_16` generic thay vì `UTF_16LE`, điều gì có thể xảy ra?

**Bài 12 — Đánh giá API.** Một method nhận `String`, ghi `getBytes()` không truyền charset, rồi `putInt(length)` không chọn order. Hãy liệt kê mọi giả định ngầm và viết lại bằng `StandardCharsets.UTF_8`, `ByteOrder` và length tính theo số byte thực tế.

## Tài liệu chính thức còn được sử dụng

- [Java SE 17 — `java.nio.charset.StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): các hằng số UTF-8, UTF-16BE, UTF-16LE, UTF-16 và charset chuẩn.
- [Java SE 17 — `java.nio.charset.Charset`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html): khái niệm charset, byte/code-unit conversion, BOM.
- [Java SE 17 — `java.nio.charset.CharsetDecoder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): cách giải mã byte thành ký tự.
- [Java SE 17 — `java.nio.charset.CodingErrorAction`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CodingErrorAction.html): `REPORT`, `REPLACE` và xử lý dữ liệu lỗi.
- [Java SE 17 — `java.nio.ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `order`, `putInt`, `getInt`, `putChar` và raw byte operations.
- [Java SE 17 — `java.nio.ByteOrder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteOrder.html): big-endian và little-endian.
- [Java SE 17 — `java.lang.String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `getBytes(Charset)`, `String(byte[], Charset)`, `length()` và `codePointCount()`.
- [Java SE 17 — `java.nio.file.Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `readString`/`writeString` với charset tường minh.

**Kết luận:** **Charset** trả lời *ký tự biến thành byte như thế nào*; **byte order** trả lời *các byte của một giá trị nhiều byte được sắp xếp ra sao*. UTF-8 không có hai biến thể little/big-endian; UTF-16 có cách sắp byte của code units và quy tắc BOM cần ghi rõ. Với record chứa cả text và số, định nghĩa charset của payload và endianness của header **riêng biệt**, kiểm chứng bằng hex, xử lý đúng dữ liệu không hợp lệ và không dựa vào mặc định của runtime.