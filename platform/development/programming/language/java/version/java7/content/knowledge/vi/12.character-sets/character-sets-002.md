# Chọn UTF-8 hoặc bảng mã tường minh theo định dạng dữ liệu trong Java

**Chủ đề:** Java 7 — Bảng mã  
**Bài học:** Chọn UTF-8 hoặc bảng mã tường minh theo định dạng dữ liệu  
**Môi trường thực hành:** Java 17+; trình bày các API còn được dùng trong JDK hiện đại, trong đó `StandardCharsets` có từ Java 7, `Files.readString/writeString` có từ Java 11 và `HexFormat` có từ Java 17.

Một `String` của Java biểu diễn văn bản Unicode, còn tệp, gói tin mạng, message queue và nhiều API I/O trao đổi **byte**. Để chuyển đổi qua lại cần một **character encoding (charset)**. Nếu hai phía không thống nhất bảng mã, chương trình vẫn có thể đọc đủ số byte nhưng văn bản trở nên sai — hiện tượng *mojibake* — hoặc mất ký tự do quy tắc thay thế.

**Quy tắc tổng quát:**

> Với định dạng văn bản mới do bạn kiểm soát, **ưu tiên UTF-8 và khai báo tường minh**. Với định dạng, protocol hoặc dữ liệu lịch sử đã có bảng mã được quy định, **tuân thủ đúng bảng mã đó**, không ép thành UTF-8 bằng cách đổi tên hoặc chọn theo cảm tính.

Bài này giải thích tại sao hai lựa chọn này không mâu thuẫn, cách áp dụng API Java chính xác và cách kiểm thử dữ liệu tiếng Việt, ký tự Unicode ngoài BMP, tệp có bảng mã khác cùng tình huống giải mã lỗi.

## 1. Character, code point, String và byte không giống nhau

Một ví dụ:

```text
Văn bản logic       "A€🌿"
       |
       | mã hóa bằng UTF-8
       v
Chuỗi byte          41 E2 82 AC F0 9F 8C BF
       |
       | giải mã bằng UTF-8
       v
Văn bản logic       "A€🌿"
```

- **Unicode code point:** một giá trị ký tự Unicode, ví dụ `U+0041` (A), `U+20AC` (€), `U+1F33F` (🌿).
- **Java String:** biểu diễn Unicode dưới dạng **các đơn vị UTF-16**. Một code point ở ngoài Basic Multilingual Plane thường chiếm **hai `char`** (một surrogate pair).
- **Charset:** quy tắc **mã hóa** văn bản thành byte và **giải mã** byte thành văn bản, ví dụ UTF-8, UTF-16LE hoặc ISO-8859-1.
- **Byte:** đơn vị của tệp/dữ liệu trên mạng. Một byte không tự gắn nhãn “tôi là UTF-8” hoặc “tôi là Windows-1252”.
- **Grapheme cluster:** một ký tự mà người dùng nhìn thấy có thể gồm nhiều code point (chẳng hạn chữ và dấu kết hợp). Số ký tự nhìn thấy cũng không nhất thiết bằng số code point.

Điều cần nhớ: `String.length()` đếm **đơn vị UTF-16**, không phải số byte UTF-8 hoặc số code point. Khi tạo giới hạn độ dài theo protocol (byte), phải **mã hóa theo charset cụ thể rồi tính byte**, không lấy `String.length()` thay thế.

### 1.1. Ví dụ runnable: UTF-8 có số byte khác số char

Tạo tệp `Utf8ContractDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class Utf8ContractDemo {
    public static void main(String[] args) {
        String text = "A€🌿";
        byte[] encoded = text.getBytes(StandardCharsets.UTF_8);
        String decoded =
                new String(encoded, StandardCharsets.UTF_8);

        System.out.println(
                "utf8-hex="
                + HexFormat.of().withUpperCase()
                            .formatHex(encoded));
        System.out.println(
                "utf16-units=" + text.length());
        System.out.println(
                "code-points="
                + text.codePointCount(0, text.length()));
        System.out.println(
                "utf8-bytes=" + encoded.length);
        System.out.println(
                "roundtrip=" + text.equals(decoded));

        String vietnamese = "Tiếng Việt";
        byte[] vietnameseBytes =
                vietnamese.getBytes(StandardCharsets.UTF_8);
        System.out.println(
                "vietnamese-roundtrip="
                + vietnamese.equals(
                    new String(vietnameseBytes,
                               StandardCharsets.UTF_8)));
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac -encoding UTF-8 -Xlint:all Utf8ContractDemo.java
java Utf8ContractDemo
```

**stdout chính xác:**

```text
utf8-hex=41E282ACF09F8CBF
utf16-units=4
code-points=3
utf8-bytes=8
roundtrip=true
vietnamese-roundtrip=true
```

Trong chuỗi `"A€🌿"` có **3 code point**, **4 đơn vị UTF-16** (emoji dùng surrogate pair) nhưng **8 byte UTF-8**. Việc encode/decode bằng **cùng** `StandardCharsets.UTF_8` bảo toàn chuỗi. Ví dụ dùng `HexFormat` để in byte bằng ASCII và có stdout không phụ thuộc khả năng hiển thị Unicode của terminal.

**Tuy nhiên:** round-trip thành công với một chuỗi kiểm thử **không chứng minh** một tệp bên ngoài cũng là UTF-8. Charset của dữ liệu nhập phải được xác định theo hợp đồng nguồn, BOM/quy tắc định dạng hoặc metadata đáng tin, không suy ra chỉ từ việc một phép thử cục bộ chạy thành công.

## 2. UTF-8 là lựa chọn mặc định tốt cho dữ liệu mới

UTF-8 là bảng mã Unicode biến độ dài: một code point có thể cần từ 1 đến 4 byte. Ký tự ASCII được biểu diễn bằng một byte tương thích ASCII; chữ có dấu tiếng Việt và nhiều ký tự khác cần nhiều byte hơn.

**Nên chọn UTF-8 khi:**

- Định nghĩa tệp văn bản, định dạng trao đổi hoặc API mới mà bạn kiểm soát cả hai phía.
- Đọc/ghi log, cấu hình, tài liệu, CSV mới do hệ thống quy định rõ là UTF-8.
- Xây dựng phần lớn tích hợp hiện đại sử dụng JSON theo quy tắc của định dạng.
- Truyền nội dung quốc tế hóa (tiếng Việt, Nhật, emoji) mà không muốn giới hạn trong bảng mã một byte.
- Cần một chính sách nhất quán giữa local, CI, container và máy chủ.

**Hợp đồng phải có cả hai phía:** “ghi UTF-8” chỉ giải quyết nửa bài toán nếu bên nhận đoán bảng mã khác. Cần ghi rõ encoding trong định dạng/schema, tài liệu API, trường metadata hoặc quy tắc của protocol. Kiểm tra bằng test với ký tự **ngoài ASCII**; một test chỉ dùng `"hello"` có thể thành công cả khi hai phía dùng bảng mã khác nhau và che giấu lỗi.

### 2.1. UTF-8 không phải phép sửa dữ liệu đã bị đọc sai

Nếu các byte thật là ISO-8859-1 nhưng bạn gọi `new String(bytes, UTF_8)`, việc giải mã đã diễn giải sai. **Ghi lại chuỗi sai đó bằng UTF-8 không tự khôi phục byte nguồn ban đầu.**

Cách chuyển đổi đúng:

```text
Byte nguồn --giải mã bằng charset nguồn--> Unicode String
Unicode String --mã hóa bằng UTF-8--> Byte đích
```

Không được làm như sau:

```java
// Sai về ý nghĩa nếu sourceBytes thực tế là ISO-8859-1:
// String text = new String(sourceBytes, StandardCharsets.UTF_8);
// byte[] output = text.getBytes(StandardCharsets.UTF_8);
```

Đoạn trên là **mã minh họa lỗi logic**, không phải chương trình độc lập. Nó chỉ nhất quán về cú pháp, nhưng phần giải mã đầu vào đã sai charset.

## 3. Dùng StandardCharsets thay vì tên charset rải rác

Java 7 cung cấp `java.nio.charset.StandardCharsets` với những hằng charset chuẩn:

| Hằng | Ý nghĩa | Dùng khi nào |
| --- | --- | --- |
| `StandardCharsets.UTF_8` | UTF-8 | Lựa chọn ưu tiên cho định dạng văn bản mới |
| `StandardCharsets.US_ASCII` | ASCII 7 bit | Protocol cũ bắt buộc ASCII |
| `StandardCharsets.ISO_8859_1` | Latin-1 | Chỉ khi định dạng nguồn/đích công bố dùng ISO-8859-1 |
| `StandardCharsets.UTF_16` | UTF-16 có cách xử lý byte-order mark theo quy tắc charset | Khi hợp đồng yêu cầu UTF-16 |
| `StandardCharsets.UTF_16LE` | UTF-16 little-endian | Khi định dạng yêu cầu thứ tự byte LE cụ thể |
| `StandardCharsets.UTF_16BE` | UTF-16 big-endian | Khi định dạng yêu cầu thứ tự byte BE cụ thể |

Các charset nói trên được Java SE yêu cầu hỗ trợ. Không nên biến danh sách này thành gợi ý “nên dùng Latin-1/UTF-16 thay UTF-8 cho mọi tệp”; **format contract quyết định**.

Cách viết nên ưu tiên:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String result = new String(bytes, StandardCharsets.UTF_8);
```

Đây là **snippet trong method** có import `java.nio.charset.StandardCharsets`, `text` và `bytes` phù hợp. Dùng các hằng giúp tránh lỗi gõ tên, làm rõ ý định với người review và không cần xử lý tên charset không được nhận diện.

### 3.1. Khi format bắt buộc một charset không nằm trong StandardCharsets

Một số hệ thống lịch sử quy định `windows-1252`, `Shift_JIS`, `GB18030` hoặc bảng mã khác. Khi đó, **không** đổi sang `ISO_8859_1` chỉ vì nó “gần giống”. Ví dụ Windows-1252 và ISO-8859-1 khác nhau ở một số vùng byte; chọn sai sẽ làm hỏng ký tự hoặc ý nghĩa điều khiển.

```java
import java.nio.charset.Charset;

// Mã minh họa tại nơi cấu hình charset:
Charset legacy = Charset.forName("windows-1252");
```

Nếu charset yêu cầu không được runtime hỗ trợ, `Charset.forName` có thể ném lỗi runtime. Một ứng dụng nhận tên charset từ cấu hình nên **validate bằng allowlist** các charset thực sự thuộc hợp đồng tích hợp và xử lý cấu hình sai rõ ràng. Không để client tùy ý điều khiển charset của mọi parser mà không có giới hạn, vì nó có thể gây sai dữ liệu hoặc các vấn đề tương thích không dự tính.

**Không dùng tên hiển thị như “ANSI”** làm charset contract. “ANSI” trong một số phần mềm có thể chỉ code page địa phương khác nhau tùy máy. Cần tên charset cụ thể và được tài liệu hóa, ví dụ `windows-1252` hoặc `ISO-8859-1`, đúng theo hệ thống nguồn.

## 4. Vì sao không nên phụ thuộc default charset?

Một số API Java có overload **không nhận charset**:

```java
byte[] encoded = text.getBytes();
String decoded = new String(bytes);
```

Đây là snippet minh họa; những overload đó dùng **default charset của môi trường Java**, không phải giá trị được khai báo theo định dạng dữ liệu.

Về lịch sử:

- **Trước JDK 18**, default charset thường phụ thuộc hệ điều hành, locale và cấu hình runtime. Cùng byte/tệp có thể cho kết quả khác khi chuyển máy.
- **Từ JDK 18**, JEP 400 đặt UTF-8 làm default charset mặc định cho các API Java SE được bao phủ, có cơ chế tương thích/cấu hình cho một số môi trường. **Không lấy thay đổi đó làm lý do bỏ charset tường minh ở ranh giới dữ liệu**.
- `Charset.defaultCharset()` cho biết charset mặc định **của runtime hiện tại**, không chứng minh charset đúng của tệp lịch sử hay gói tin do đối tác gửi.
- Default charset dùng để giải mã **dữ liệu bên ngoài** vẫn có thể sai cho dù nó là UTF-8, vì nguồn có thể là ISO-8859-1 hoặc Windows-1252.
- Encoding của **Java source file** và encoding của **dữ liệu chương trình** là hai hợp đồng khác nhau. Dùng `javac -encoding UTF-8` khi build nguồn UTF-8 giúp tránh lệ thuộc vào cấu hình/compiler mặc định.

**Khuyến nghị:** khai báo `StandardCharsets.UTF_8` hoặc charset được protocol yêu cầu tại mọi boundary I/O quan trọng. Có thể để mặc định ở những thao tác chỉ phục vụ người dùng interactive/cục bộ theo đúng API, nhưng không dựa vào default để định nghĩa format lưu trữ lâu dài.

### 4.1. Không dựa vào default để phát hiện charset nguồn

Ghi log `Charset.defaultCharset()` chỉ hỗ trợ điều tra môi trường; nó không phải công cụ **tự nhận biết encoding của byte[]**. Một tệp có thể chứa ASCII thuần và hợp lệ dưới nhiều bảng mã; một tệp khác có byte không hợp lệ trong UTF-8. Dò đoán tự động thường có thể sai, đặc biệt với tệp ngắn.

Nếu format có charset field hoặc HTTP `Content-Type` hợp lệ, đọc **metadata đáng tin theo quy tắc protocol**. Nếu format không quy định, yêu cầu nguồn cung cấp thông tin hoặc làm rõ chính sách nhập; không cố phục hồi bằng một phép thử “nếu decode không ném lỗi thì chắc đúng”.

## 5. Khi buộc phải đọc dữ liệu Latin-1: decode đúng rồi mới chuyển UTF-8

Ví dụ tệp có byte:

```text
43 61 66 E9
```

Theo ISO-8859-1, các byte tương ứng với `"Café"`. Byte `E9` đứng riêng **không** phải chuỗi UTF-8 hợp lệ; chữ `é` trong UTF-8 có hai byte `C3 A9`.

Tạo tệp `LegacyDecodeDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.StandardCharsets;

public class LegacyDecodeDemo {
    public static void main(String[] args) {
        byte[] legacy = {
            0x43, 0x61, 0x66, (byte) 0xE9
        };

        String correct = new String(
                legacy, StandardCharsets.ISO_8859_1);
        String wrong = new String(
                legacy, StandardCharsets.UTF_8);

        System.out.println(
                "correct-final-codepoint="
                + correct.codePointAt(3));
        System.out.println(
                "wrong-has-replacement="
                + wrong.contains("\uFFFD"));
        System.out.println(
                "utf8-byte-length="
                + correct.getBytes(
                    StandardCharsets.UTF_8).length);
        System.out.println(
                "latin1-byte-length=" + legacy.length);

        CharsetDecoder strict =
                StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try {
            strict.decode(ByteBuffer.wrap(legacy));
            System.out.println("unexpected-valid-utf8");
        } catch (CharacterCodingException ex) {
            System.out.println(
                "strict-error="
                + ex.getClass().getSimpleName());
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all LegacyDecodeDemo.java
java LegacyDecodeDemo
```

**stdout chính xác:**

```text
correct-final-codepoint=233
wrong-has-replacement=true
utf8-byte-length=5
latin1-byte-length=4
strict-error=MalformedInputException
```

Giải thích:

1. Byte `E9` trong ISO-8859-1 giải mã thành code point **U+00E9 = 233**.
2. `new String(legacy, UTF_8)` có chính sách **thay thế các chuỗi byte không hợp lệ** bằng ký tự thay thế Unicode `U+FFFD`; chương trình có thể tiếp tục chạy nhưng văn bản đã bị sai.
3. Mã hóa lại `"Café"` bằng UTF-8 cho **5 byte** thay vì 4 byte Latin-1. Đây là chuyển mã đúng, không phải tăng/giảm độ dài String một cách tùy tiện.
4. `CharsetDecoder` được cấu hình `CodingErrorAction.REPORT` từ chối dữ liệu UTF-8 không hợp lệ bằng `MalformedInputException`. Điều này phù hợp khi muốn **phát hiện dữ liệu sai** thay vì tự động thay ký tự.
5. `new String(byte[], Charset)` là API tiện dụng, nhưng **không phải parser strict** cho mọi dữ liệu; cần chủ động chọn chính sách lỗi giải mã khi dữ liệu phải đúng tuyệt đối.

**Với dữ liệu cũ:** phải biết rõ bảng mã thật sự. Nhiều ký tự văn bản tiếng Việt không biểu diễn được trong ISO-8859-1, nên ví dụ chữ `é` chỉ minh họa một byte Latin-1 hợp lệ, **không phải khuyến nghị dùng ISO-8859-1 cho tiếng Việt**.

## 6. Đọc và ghi tệp văn bản theo charset cụ thể

Từ Java 11, `Files.readString`/`Files.writeString` hỗ trợ charset tường minh, thuận tiện khi tệp nhỏ/vừa và bạn muốn lấy/toàn bộ văn bản:

```java
Path path = Path.of("message.txt");

Files.writeString(path, "Xin chào",
                  StandardCharsets.UTF_8);
String text = Files.readString(path,
                               StandardCharsets.UTF_8);
```

Đây là **snippet trong một method**, cần import `Path`, `Files`, `StandardCharsets` và xử lý `IOException`. Nếu tệp lớn, không nên tự động nạp hết vào một `String`; dùng reader/stream để xử lý dần.

### 6.1. Ví dụ runnable: UTF-8 và tệp legacy

Tạo `FileCharsetDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileCharsetDemo {
    public static void main(String[] args)
            throws IOException {
        Path temp = Files.createTempFile(
                "charset-demo-", ".txt");

        try {
            String source = "Tiếng Việt 🌿";
            Files.writeString(
                    temp, source, StandardCharsets.UTF_8);

            String restored = Files.readString(
                    temp, StandardCharsets.UTF_8);
            System.out.println(
                    "utf8-file-equal="
                    + source.equals(restored));

            byte[] legacy = {
                0x43, 0x61, 0x66, (byte) 0xE9
            };
            Files.write(temp, legacy);

            String latin1 = Files.readString(
                    temp, StandardCharsets.ISO_8859_1);
            System.out.println(
                    "latin1-final-codepoint="
                    + latin1.codePointAt(3));

            try {
                Files.readString(
                        temp, StandardCharsets.UTF_8);
                System.out.println("unexpected-valid-file");
            } catch (MalformedInputException ex) {
                System.out.println(
                    "utf8-file-error="
                    + ex.getClass().getSimpleName());
            }
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all FileCharsetDemo.java
java FileCharsetDemo
```

```text
utf8-file-equal=true
latin1-final-codepoint=233
utf8-file-error=MalformedInputException
```

Ví dụ tạo file tạm bằng `Files.createTempFile`, ghi/đọc UTF-8, sau đó **thay nội dung** bằng 4 byte Latin-1 để kiểm tra lỗi giải mã. Tệp được xóa bằng `Files.deleteIfExists` trong `finally`. `Files.readString` với charset có thể **ném `MalformedInputException`** khi byte sequence không hợp lệ — khác với constructor `new String(bytes, Charset)` dạng tiện ích đã thay dữ liệu không hợp lệ ở ví dụ trước.

**Điểm học quan trọng:** Chọn charset đúng là một phần hợp đồng dữ liệu, còn **chính sách khi dữ liệu sai encoding** cũng cần xác định. Với tệp bên ngoài, một chương trình strict có thể từ chối rõ ràng, giúp phát hiện lỗi đầu vào sớm thay vì lưu thành chuỗi sai và gây hỏng ở nhiều bước sau.

### 6.2. BufferedReader / BufferedWriter trên Java 17+

Đối với file lớn hoặc đọc từng dòng, dùng NIO với charset cụ thể:

```java
try (BufferedReader reader =
         Files.newBufferedReader(path,
                                 StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
```

Đây là **mã minh họa**, giả sử có import và `process`. Với ghi từng dòng:

```java
try (BufferedWriter writer =
         Files.newBufferedWriter(path,
                                 StandardCharsets.UTF_8)) {
    writer.write("Dữ liệu");
    writer.newLine();
}
```

Các lớp `Files.newBufferedReader`/`newBufferedWriter` có từ Java 7. Dùng `try-with-resources` để đóng reader/writer ngay khi xong; đừng chờ garbage collector. `newLine()` sử dụng dấu kết thúc dòng theo platform và **không** phải trách nhiệm của charset: nếu giao thức yêu cầu chính xác LF `\n`, hãy ghi ký tự `'\n'` tường minh.

**Tách hai loại chuẩn hóa:** Charset chọn byte encoding, còn **line ending (LF/CRLF)**, BOM, dấu phân cách CSV, delimiter, escape, Unicode normalization đều là thuộc tính khác của format. “UTF-8” tự nó **không** bảo đảm các thuộc tính đó.

## 7. Stream I/O: chỉ rõ charset ở tầng chuyển byte ↔ character

Với API dùng `InputStream`/`OutputStream`, hãy đặt codec tại biên tương ứng:

- `InputStream` nhận byte; `InputStreamReader(stream, charset)` **giải mã** thành character.
- `OutputStream` ghi byte; `OutputStreamWriter(stream, charset)` **mã hóa** character.
- `BufferedReader`/`BufferedWriter` bổ sung bộ đệm/đọc dòng; chúng **không** quyết định charset nếu phía dưới đã là `Reader`/`Writer`.
- Đóng writer trong TWR giúp hoàn tất việc đẩy dữ liệu có bộ đệm theo hợp đồng. Nhưng close/flush **không đồng nghĩa** với bảo đảm fsync, transaction commit hoặc peer đã nhận dữ liệu.

### 7.1. Ví dụ runnable: cùng một charset hai phía

Tạo `StreamCharsetDemo.java`:

```java
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;

public class StreamCharsetDemo {
    public static void main(String[] args)
            throws IOException {
        String source = "Xin chào 🌿";
        ByteArrayOutputStream sink =
                new ByteArrayOutputStream();

        try (Writer writer = new OutputStreamWriter(
                sink, StandardCharsets.UTF_8)) {
            writer.write(source);
        }

        byte[] payload = sink.toByteArray();
        String restored;

        try (BufferedReader reader =
                new BufferedReader(
                    new InputStreamReader(
                        new ByteArrayInputStream(payload),
                        StandardCharsets.UTF_8))) {
            restored = reader.readLine();
        }

        System.out.println(
                "stream-roundtrip="
                + source.equals(restored));
        System.out.println(
                "utf8-payload-not-empty="
                + (payload.length > 0));
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all StreamCharsetDemo.java
java StreamCharsetDemo
```

```text
stream-roundtrip=true
utf8-payload-not-empty=true
```

**Phân tích:**

1. `OutputStreamWriter` chọn UTF-8 **khi mã hóa** String thành byte.
2. Khi TWR đóng writer, dữ liệu đã được đưa vào `ByteArrayOutputStream`; đây là stream **trong bộ nhớ**, không phải minh họa cho fsync/network acknowledgement.
3. `InputStreamReader` chọn **cùng UTF-8** để giải mã payload; kết quả khớp bản gốc.
4. Nếu nguồn chứa nhiều dòng, dùng loop `readLine()`. Nhưng `readLine()` loại bỏ dấu kết thúc dòng; nếu cần bảo toàn byte-for-byte file gốc, đừng round-trip qua đọc dòng mà không định nghĩa quy tắc newline.
5. Với payload từ hệ thống bên ngoài, nên xác định charset theo metadata/protocol, không chỉ sao chép `UTF_8` từ ví dụ.

### 7.2. Chọn REPORT thay vì REPLACE khi cần phát hiện lỗi

Các overload tiện dụng với `Charset` có thể thay byte không hợp lệ bằng ký tự replacement. Nếu phải từ chối dữ liệu sai, có thể cấu hình một `CharsetDecoder` riêng:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8
        .newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Reader reader = new InputStreamReader(stream, decoder)) {
    // Đọc sẽ báo lỗi khi gặp byte không hợp lệ.
}
```

Đây là **mã minh họa** với import `CharsetDecoder`, `CodingErrorAction`, `Reader`, `InputStreamReader` và biến `stream`. Không coi mọi phương thức trả String đều có chính sách lỗi mặc định giống nhau; hãy xem JavaDoc của **API thực sự được dùng**.

**Malformed input** là chuỗi byte/code unit không hợp lệ theo mã hóa. **Unmappable character** là ký tự hợp lệ nhưng **không thể biểu diễn** bằng charset đích. Đây là hai loại lỗi khác nhau và có thể cần chính sách riêng.

## 8. Chọn encoder strict để không làm mất ký tự

Một lỗi dễ bị bỏ qua: xuất dữ liệu tiếng Nhật/Việt sang bảng mã không chứa được các ký tự đó. Một số overload tiện ích **thay thế những ký tự không ánh xạ được**, khiến chương trình vẫn chạy mà dữ liệu trở thành dấu hỏi hay ký tự thay thế khác.

Nếu dùng dữ liệu làm định danh, số hợp đồng, thông điệp quan trọng hoặc export cần bảo toàn tuyệt đối, **không nên âm thầm thay nội dung**. Có thể dùng `CharsetEncoder` với `CodingErrorAction.REPORT`.

### 8.1. Ví dụ runnable: từ chối ký tự không biểu diễn được

Tạo `StrictEncoderDemo.java`:

```java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.StandardCharsets;

public class StrictEncoderDemo {
    public static void main(String[] args) {
        String source = "東京";

        byte[] lossy = source.getBytes(
                StandardCharsets.ISO_8859_1);
        String restored = new String(
                lossy, StandardCharsets.ISO_8859_1);

        System.out.println(
                "lossless=" + source.equals(restored));
        System.out.println(
                "lossy-byte-count=" + lossy.length);

        CharsetEncoder strict =
                StandardCharsets.ISO_8859_1
                .newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try {
            strict.encode(CharBuffer.wrap(source));
            System.out.println("unexpected-encodable");
        } catch (CharacterCodingException ex) {
            System.out.println(
                "strict-error="
                + ex.getClass().getSimpleName());
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all StrictEncoderDemo.java
java StrictEncoderDemo
```

```text
lossless=false
lossy-byte-count=2
strict-error=UnmappableCharacterException
```

`String.getBytes(ISO_8859_1)` trả một biểu diễn đã **mất thông tin** cho hai chữ Kanji không nằm trong Latin-1. Khi chuyển ngược lại, chuỗi không bằng bản gốc. `CharsetEncoder` strict báo `UnmappableCharacterException`, phù hợp với yêu cầu “không thể xuất nếu có ký tự vượt bảng mã”.

**Phân biệt hai chính sách:**

- **REPORT:** ưu tiên với dữ liệu quan trọng, schema nghiêm ngặt, tích hợp cần xác minh encoding; ghi lỗi rõ cho caller hoặc quy trình xử lý.
- **REPLACE:** chỉ khi định dạng/tác vụ chấp nhận mất một phần dữ liệu và đã tài liệu hóa cách thay thế. Không dùng làm mặc định vô thức cho import/export dữ liệu cần chính xác.

Không phải mọi ký tự bị mất đều được thay bằng cùng một ký tự trên mọi charset/API; vì thế hãy test **khả năng bảo toàn nội dung**, thay vì hard-code giả định ký tự thay thế nào đó.

## 9. Byte order mark (BOM): charset không phải toàn bộ format

**BOM (byte order mark)** là dấu byte có thể xuất hiện ở đầu một số tệp. Với UTF-8, chuỗi byte BOM quen thuộc là:

```text
EF BB BF
```

UTF-8 không cần BOM để xác định byte order; BOM có thể được một vài ứng dụng dùng như dấu nhận diện. Một hệ thống khác lại coi đó là ký tự `U+FEFF` trong nội dung hoặc từ chối BOM theo quy tắc format.

- **UTF-8:** ưu tiên không thêm BOM khi tạo định dạng mới nếu không có yêu cầu cụ thể; tuân thủ format/consumer. Ví dụ JSON trao đổi theo chuẩn RFC 8259 **không được thêm BOM khi gửi**.
- **UTF-16:** thứ tự byte có thể liên quan BOM hoặc do charset cụ thể `UTF_16LE`/`UTF_16BE` và định dạng quy định.
- **Reader UTF-8 trong Java:** đừng mặc nhiên giả định mọi decoder/reader **tự loại bỏ UTF-8 BOM**. Nếu protocol cho phép BOM và yêu cầu bỏ dấu này, xử lý đúng tại **đầu file** theo quy định.
- **CSV:** không có một hợp đồng charset/BOM thống nhất cho mọi hệ thống; khi tích hợp phần mềm bảng tính, xác định rõ encoding, BOM (nếu cần), delimiter, quote và newline trong hợp đồng trao đổi.

### 9.1. Ví dụ runnable: BOM vẫn được đọc như U+FEFF

Tạo `Utf8BomDemo.java`:

```java
import java.nio.charset.StandardCharsets;

public class Utf8BomDemo {
    public static void main(String[] args) {
        byte[] payload = {
            (byte) 0xEF, (byte) 0xBB, (byte) 0xBF,
            0x41, 0x42
        };

        String decoded = new String(
                payload, StandardCharsets.UTF_8);

        System.out.println(
                "starts-with-bom="
                + decoded.startsWith("\uFEFF"));
        System.out.println(
                "first-codepoint="
                + decoded.codePointAt(0));
        System.out.println(
                "decoded-length=" + decoded.length());

        String withoutLeadingBom =
                decoded.startsWith("\uFEFF")
                ? decoded.substring(1) : decoded;
        System.out.println(
                "clean-content=" + withoutLeadingBom);
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all Utf8BomDemo.java
java Utf8BomDemo
```

```text
starts-with-bom=true
first-codepoint=65279
decoded-length=3
clean-content=AB
```

`U+FEFF` có giá trị thập phân `65279`. Ví dụ chỉ loại bỏ **một BOM ở đầu**, không xóa mọi ký tự U+FEFF ở mọi vị trí trong dữ liệu. Nếu định dạng cấm BOM, ứng dụng có thể chọn **báo lỗi** thay vì tự động bỏ nó.

**Không tự nhầm BOM với lỗi charset:** một file UTF-8 hợp lệ có BOM vẫn được giải mã thành Unicode, nhưng consumer cần quy định rõ có giữ/loại bỏ code point ở đầu hay không. Vấn đề này tách biệt với tình huống giải mã byte ISO-8859-1 sai thành UTF-8.

## 10. Charset là một phần của hợp đồng giao tiếp

Chọn encoding theo **format và phía nhận**, không chỉ theo thư viện Java.

| Dữ liệu/định dạng | Cách chọn charset |
| --- | --- |
| Tệp văn bản mới do đội tự thiết kế | Quy định UTF-8 trong spec, ghi/đọc tường minh |
| JSON trao đổi giữa hệ thống theo chuẩn RFC 8259 | **UTF-8** cho trao đổi ngoài hệ sinh thái đóng, không phát BOM ở đầu |
| Tệp CSV nhập từ hệ thống đối tác | Lấy từ contract của đối tác: có thể UTF-8 hoặc một charset lịch sử; thống nhất delimiter, quote, newline và BOM riêng |
| Tệp có nhãn ISO-8859-1 chuẩn xác | Decode `ISO_8859_1`, rồi chuyển sang UTF-8 nếu muốn lưu format mới |
| Tệp quy định `windows-1252` | Dùng `Charset.forName("windows-1252")` khi runtime hỗ trợ; không tự coi là `ISO_8859_1` |
| XML / HTML | Tuân thủ quy tắc xác định encoding của **chính định dạng** và metadata transport, không tự chọn một cách có thể mâu thuẫn |
| Giao thức thuần byte | Không biến mọi payload thành String; chỉ decode trường **được định nghĩa là văn bản** |
| Nội dung nhận qua HTTP | Xét media type, `charset` parameter khi có ý nghĩa và quy tắc chuẩn của media type; không suy từ encoding của terminal |
| Database/text columns | Đối chiếu API driver, encoding kết nối/database và collation; **collation không đồng nghĩa charset** |
| Java source files | Thống nhất source encoding UTF-8 và đặt `javac -encoding UTF-8` trong build khi cần nhất quán |

**Đừng đoán encoding chỉ từ phần mở rộng** `.txt`/`.csv`/`.json` trong mọi tình huống. Một định dạng có thể quy định charset (như JSON trao đổi chuẩn), trong khi định dạng khác để câu trả lời phụ thuộc contract của nhà cung cấp.

### 10.1. Định dạng JSON và CSV không có cùng quy tắc

JSON trao đổi ngoài hệ sinh thái đóng theo RFC 8259 phải mã hóa UTF-8. Một parser JSON có thể có cách xử lý BOM phù hợp chuẩn, nhưng **generator không nên thêm BOM**. JSON về cơ bản có những quy tắc escape, syntax, Unicode riêng; chỉ dùng UTF-8 chưa đủ để làm một tệp text tự biến thành JSON hợp lệ.

CSV không có một bảng mã duy nhất cho tất cả biến thể và consumer. Với CSV phải ghi rõ:

- Charset (ví dụ UTF-8 hoặc chính xác bảng mã legacy).
- Có BOM hay không.
- Dấu phân tách cột (dấu phẩy, chấm phẩy, tab ...).
- Quy tắc escape cho dấu quote/delimiter và newline.
- Header, encoding của line endings, schema dữ liệu.

Những chi tiết này **độc lập** với quyết định `StandardCharsets.UTF_8` trong Java, nhưng đều cần thống nhất để dữ liệu interoperable.

### 10.2. Không dùng charset như công cụ chuẩn hóa văn bản

Hai chuỗi Unicode trông giống nhau có thể dùng các chuỗi code point khác nhau, ví dụ ký tự dựng sẵn và ký tự kết hợp dấu. **Cùng encode UTF-8** không tự làm hai chuỗi chuẩn hóa về cùng dạng. Nếu nghiệp vụ cần equality/search ổn định, cân nhắc `java.text.Normalizer` (ví dụ NFC) với chính sách rõ ràng trước khi lưu/so sánh.

Tương tự, **case folding**, locale, collation, grapheme clustering và cắt chuỗi theo ký tự người dùng nhìn thấy là bài toán khác. UTF-8 chỉ xác định cách biến chuỗi Unicode thành byte.

## 11. Ví dụ thực hành: chính sách charset được chọn từ schema

Một ứng dụng có thể xuất hai định dạng: format mới UTF-8 và format lịch sử Latin-1. Thay vì dùng default charset tùy máy, định nghĩa mapping bằng enum/format contract.

Tạo `FormatPolicyDemo.java`:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

public class FormatPolicyDemo {
    enum Format {
        MODERN_UTF8,
        LEGACY_LATIN1
    }

    static Charset charsetFor(Format format) {
        return switch (format) {
            case MODERN_UTF8 ->
                    StandardCharsets.UTF_8;
            case LEGACY_LATIN1 ->
                    StandardCharsets.ISO_8859_1;
        };
    }

    static byte[] encode(String value, Format format) {
        return value.getBytes(charsetFor(format));
    }

    static String decode(byte[] bytes, Format format) {
        return new String(bytes, charsetFor(format));
    }

    public static void main(String[] args) {
        String source = "Café";

        byte[] modern =
                encode(source, Format.MODERN_UTF8);
        byte[] legacy =
                encode(source, Format.LEGACY_LATIN1);

        System.out.println(
                "modern-bytes=" + modern.length);
        System.out.println(
                "legacy-bytes=" + legacy.length);
        System.out.println(
                "modern-roundtrip="
                + source.equals(
                    decode(modern, Format.MODERN_UTF8)));
        System.out.println(
                "legacy-roundtrip="
                + source.equals(
                    decode(legacy, Format.LEGACY_LATIN1)));
        System.out.println(
                "wrong-format-equal="
                + source.equals(
                    decode(modern, Format.LEGACY_LATIN1)));
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all FormatPolicyDemo.java
java FormatPolicyDemo
```

```text
modern-bytes=5
legacy-bytes=4
modern-roundtrip=true
legacy-roundtrip=true
wrong-format-equal=false
```

`switch` expression là cú pháp hiện hành ổn định trên Java 17. Mapping với enum **không** làm mỗi khách hàng thích bảng mã nào cũng được: nó làm **contract trở nên hữu hình và có thể kiểm thử**. Dữ liệu Unicode ngoài phạm vi Latin-1 vẫn cần strict encoder khi phải bảo đảm không mất ký tự; method `encode` ở trên dùng convenience API để minh họa mapping, **không phải cổng export strict**.

**Thiết kế tốt hơn cho ứng dụng nhiều format:** validate format tại boundary, chỉ cho các giá trị đã hỗ trợ, đóng gói `Charset` cạnh format handler, test bằng fixture byte thực tế thay vì chỉ round-trip từ dữ liệu tự tạo. Không dùng một nhãn charset tự do đến từ người dùng để “đoán” mọi file.

## 12. Cảnh báo bảo mật và tính toàn vẹn dữ liệu

Chọn sai charset không chỉ làm chữ bị lỗi hiển thị. Nó có thể gây ảnh hưởng đến:

- **Định danh người dùng/khóa nghiệp vụ:** ký tự được thay thế khiến các identifier khác nhau bị đồng nhất hoặc không tra cứu được.
- **Chữ ký số, MAC, hash:** các thuật toán làm việc trên **byte chính xác**; encode khác charset cho byte khác, hash/signature khác. Hai phía phải thống nhất charset và chuẩn hóa nếu protocol yêu cầu.
- **Phân tích log và audit:** nếu byte sai giải mã thành replacement char rồi ghi lại, rất khó khôi phục bằng chứng gốc.
- **Tách dòng/parse delimiter:** một byte stream được diễn giải sai có thể khiến parser nhận sai cấu trúc, nhất là với các bộ mã đa byte hoặc định dạng đặc thù.
- **Tích hợp CSV/API:** ký tự tên, địa chỉ, sản phẩm bị hỏng có thể gây lỗi hệ thống về sau dù request ban đầu không có exception.

**Cách phòng tránh:** khi nhận dữ liệu bên ngoài, xác thực charset theo spec, dùng decoder với `REPORT` ở boundary nghiêm ngặt, giới hạn kích thước payload, log lỗi kèm thông tin nguồn/offset phù hợp và không ghi dữ liệu nhạy cảm thô vào log. Có thể lưu byte nguồn theo chính sách bảo mật/retention nếu cần điều tra và được phép.

Một chuỗi Unicode được tạo ra thành công **không có nghĩa** byte đầu vào đã hợp lệ theo charset mong đợi. Constructor `new String(bytes,Charset)` có thể thay byte lỗi; dùng đúng API strict khi yêu cầu toàn vẹn.

## 13. Checklist code review

Khi đọc một PR có thao tác String/byte/tệp:

1. **Boundary ở đâu?** Đọc byte từ file, HTTP, socket, DB, message queue hay từ một API đã trả String?
2. **Charset được định nghĩa ở đâu?** Trong RFC/protocol, schema, content-type, file metadata hay thỏa thuận đối tác?
3. **Đây là format mới hay legacy?** Format mới thường nên chọn UTF-8; format legacy phải theo bảng mã nguồn chính xác.
4. **Có API nào dùng default charset ngầm không?** Tìm `getBytes()`, `new String(byte[])`, `FileReader`/`FileWriter` không charset hoặc các constructor Reader/Writer thiếu charset.
5. **Encode/decode có đối xứng theo format không?** Kiểm thử bằng byte fixtures và văn bản ngoài ASCII.
6. **Khi byte đầu vào sai, hành vi là gì?** Reject bằng `REPORT` hay có chủ đích dùng `REPLACE`?
7. **Khi ký tự không encode được, hành vi là gì?** Tránh làm mất dữ liệu im lặng ở dữ liệu quan trọng; strict encoder khi cần.
8. **Có BOM không?** Format cho phép, cấm hay bắt buộc? Nếu xử lý, chỉ tại vị trí và phạm vi quy định.
9. **Có phụ thuộc newline/CSV delimiter/normalization không?** Charset không giải quyết những quy tắc ấy.
10. **Nguồn và terminal encoding có bị nhầm?** Lỗi hiển thị stdout không chứng minh byte tệp sai; test byte độc lập.
11. **Có load toàn bộ file quá lớn không?** Chuyển sang stream/buffer với charset tường minh và giới hạn kích thước phù hợp.
12. **Có tự động đoán charset không?** Nếu có, cần kiểm tra thuật toán, tính không chắc chắn và chính sách khi nhận diện không đủ tin cậy.
13. **Có dùng tên charset do client gửi không?** Validate danh sách được phép, không chấp nhận tuỳ ý nếu không thuộc hợp đồng.
14. **Có test tích hợp nhiều môi trường không?** Cần dữ liệu tiếng Việt, emoji, legacy bytes, malformed UTF-8, BOM và trailing newline.

## 14. Bài tập

**Bài 1 — Byte và ký tự:** chạy `Utf8ContractDemo`, giải thích vì sao 3 code point nhưng 4 đơn vị UTF-16 và 8 byte UTF-8. Thay text bằng `"Tiếng Việt"` và xem UTF-8 byte khác số `char` như thế nào.

**Bài 2 — Sai charset:** chạy `LegacyDecodeDemo`, xác định byte `E9` có nghĩa gì trong ISO-8859-1 và tại sao nó không hợp lệ khi đứng một mình trong UTF-8. So sánh convenience decoding và strict decoding.

**Bài 3 — File strict:** chạy `FileCharsetDemo`, thay Latin-1 payload bằng UTF-8 hợp lệ và xác nhận `Files.readString(..., UTF_8)` thành công. Ghi nguyên text Latin-1 bằng `Files.writeString(..., ISO_8859_1)` và so sánh byte thực tế.

**Bài 4 — Stream:** chạy `StreamCharsetDemo`, thay source bằng chuỗi có newline. Viết vòng lặp `BufferedReader.readLine()` và giải thích vì sao round-trip không giữ nguyên dấu xuống dòng gốc nếu tự nối lại tùy ý.

**Bài 5 — Mất ký tự:** chạy `StrictEncoderDemo`, thử chuỗi tiếng Việt chứa ký tự ngoài Latin-1. Xem `getBytes(ISO_8859_1)` và `CharsetEncoder` có `REPORT` phản ứng khác nhau thế nào.

**Bài 6 — BOM:** chạy `Utf8BomDemo`, giải thích vì sao `decoded.length()==3` dù nội dung hiển thị chỉ là `AB`. Chọn giữa reject BOM hoặc bỏ BOM đầu file tùy theo hai contract giả định.

**Bài 7 — Format contract:** chạy `FormatPolicyDemo` và thêm một `Format` chỉ có UTF-16LE nếu đối tác thực sự yêu cầu. Test byte order, round-trip và xác định có cần BOM/metadata theo định dạng không.

**Bài 8 — Tích hợp:** thiết kế một pipeline nhập CSV có charset rõ, delimiter/quote rõ và giới hạn kích thước. Viết test đọc tệp có UTF-8, legacy encoding và byte không hợp lệ; phân biệt lỗi encoding với lỗi cấu trúc CSV.

**Bài 9 — Review:** tìm các overload không charset trong một dự án, phân loại theo “phụ thuộc default có chủ đích” và “đang lưu/truyền format cần cố định”. Chỉ sửa chỗ cần theo hợp đồng, tránh thay hàng loạt mà không xét nguồn dữ liệu.

## 15. Ghi nhớ nhanh

- **UTF-8** là lựa chọn ưu tiên cho **format văn bản mới** và tương thích quốc tế; **format có bảng mã đã quy định phải tuân thủ đúng**.
- **Bảng mã nằm ở ranh giới byte ↔ String**. Java `String` không tự mang nhãn charset đã dùng khi tạo nó.
- `StandardCharsets.UTF_8`, `ISO_8859_1`, `UTF_16LE`... rõ ràng, ổn định hơn dựa vào default charset.
- **JDK 18+ mặc định UTF-8 cho nhiều API** theo JEP 400, nhưng điều đó **không làm mọi byte đầu vào thành UTF-8**; hợp đồng dữ liệu vẫn cần tường minh.
- **Không lấy `String.length()` làm số byte UTF-8.** UTF-16 code units, Unicode code points, grapheme clusters và bytes là các phép đo khác nhau.
- **Không dùng sai charset để “đọc tạm” rồi ghi lại UTF-8**; hãy decode đúng charset nguồn trước.
- **Malformed/unmappable có thể bị thay thế** bởi một số convenience API; dùng `CharsetDecoder`/`CharsetEncoder` với `CodingErrorAction.REPORT` khi cần integrity.
- **BOM, newline, CSV quoting, Unicode normalization** là các khía cạnh format riêng, không được giải quyết chỉ bằng cách chọn UTF-8.
- **Round-trip tự tạo chưa đủ** để chứng minh charset của dữ liệu từ đối tác; test bằng byte fixtures và hợp đồng thực tế.

## Tài liệu chuẩn nên đọc

- [StandardCharsets — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html): các hằng charset chuẩn được hỗ trợ.
- [Charset / CharsetDecoder / CharsetEncoder — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html): cơ chế encode/decode và xử lý lỗi.
- [Files — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): đọc/ghi text với charset tường minh.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): default charset từ JDK 18.
- [RFC 8259 — JSON Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259): yêu cầu UTF-8 cho JSON trao đổi giữa các hệ thống.
