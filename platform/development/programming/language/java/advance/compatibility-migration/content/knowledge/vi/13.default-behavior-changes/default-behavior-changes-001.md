# Bộ mã ký tự mặc định và chuyển dữ liệu sang UTF-8 có kiểm soát

Trong quá trình nâng cấp Java, một ứng dụng có thể biên dịch thành công và vẫn khởi động bình thường nhưng bắt đầu đọc sai dấu tiếng Việt, tạo CSV bị lỗi ký tự hoặc trao đổi dữ liệu không tương thích với hệ thống khác. Nguyên nhân nhiều khi không nằm ở thuật toán xử lý chuỗi mà ở **bộ mã ký tự mặc định** (*default charset*) được chương trình sử dụng khi chuyển đổi giữa byte và ký tự.

Các phiên bản Java cũ thường lấy default charset từ môi trường vận hành. Chuyển sang JDK mới có thể làm thay đổi hành vi của những lời gọi không khai báo charset. Đặc biệt, từ Java 18, **JEP 400** định hướng UTF-8 trở thành default charset của các API Java SE liên quan, trong khi ứng dụng cũ có thể đang phụ thuộc vào một encoding như Windows-1252, Windows-1258 hoặc một bộ mã theo thiết lập của hệ điều hành. Một thay đổi mặc định tưởng như nhỏ có thể ảnh hưởng tới file, message, log, HTTP, batch job và dữ liệu lưu trữ lâu năm.

Bài học nằm trong chương **Hành vi mặc định** của module **Java Advance Compatibility Migration**. Trọng tâm không chỉ là thêm `StandardCharsets.UTF_8` vào source code, mà là xây dựng cách chuyển đổi **có kiểm kê, có xác định encoding nguồn, có kiểm soát lỗi, có bằng chứng so sánh và có phương án rollback**.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt *byte*, ký tự Unicode, `String` và charset khi đọc/ghi dữ liệu.
- Giải thích ảnh hưởng của `Charset.defaultCharset()` và thay đổi mặc định từ Java 18.
- Nhận diện các API đang sử dụng default charset một cách ngầm định.
- Xác định encoding nguồn của dữ liệu và phân biệt **đọc đúng byte cũ** với **ghi UTF-8 mới**.
- Thiết kế quy trình chuyển đổi có backup, kiểm tra lỗi decoding và khả năng khôi phục.
- Xử lý những vùng dễ bị bỏ sót: `.properties`, console, CSV, log, giao thức HTTP, database và native integration.
- Viết test bảo vệ dữ liệu tiếng Việt, ký tự đặc biệt, BOM, dữ liệu lỗi và luồng hai chiều.

## 2. Bản chất vấn đề: byte và ký tự không giống nhau

### 2.1. `String` lưu ký tự, file lưu byte

Trong chương trình Java, một đối tượng `String` biểu diễn một chuỗi ký tự Unicode theo mô hình của Java. Khi ghi chuỗi ra file hoặc truyền qua mạng, chương trình cần mã hóa chuỗi thành byte. Khi đọc dữ liệu trở lại, chương trình cần giải mã byte thành ký tự.

```text
Ký tự Unicode trong String
          |
          | encode bằng charset cụ thể
          v
        Byte[]
          |
          | ghi file / truyền mạng / lưu blob
          v
       Dữ liệu lưu trữ

        Byte[]
          |
          | decode bằng charset cụ thể
          v
Ký tự Unicode trong String
```

Charset là quy tắc ánh xạ giữa ký tự và byte. Nếu mã hóa và giải mã dùng hai charset không tương thích, dữ liệu có thể bị biến dạng ngay cả khi bản thân byte vẫn đọc được.

Ví dụ:

```java
String value = "Cà phê Việt Nam";

byte[] utf8 = value.getBytes(StandardCharsets.UTF_8);

String restored =
        new String(utf8, StandardCharsets.UTF_8);

System.out.println(restored);
```

Khi hai phía thống nhất UTF-8, chuỗi được khôi phục đúng. Nếu cùng chuỗi được giải mã bằng encoding khác, kết quả có thể chứa những ký tự không mong muốn.

### 2.2. Vì sao các chuỗi ASCII đơn giản dễ che giấu lỗi?

Nhiều charset phổ biến dùng cùng byte cho các ký tự ASCII từ `0x00` đến `0x7F`. Vì thế test chỉ chứa `Hello123` có thể chạy đúng dù chương trình sử dụng sai charset.

Ngược lại, các ký tự như:

```text
Tiếng Việt:  Trường đại học, Nguyễn, dữ liệu
Châu Âu:    café, naïve, résumé
Ký hiệu:    €, ©, →, ✓
Bổ sung:    emoji hoặc ký tự ngoài Basic Multilingual Plane
```

giúp bộc lộ khác biệt nhanh hơn. Bộ test chuyển đổi encoding cần có các nhóm ký tự mà hệ thống thực sự phải xử lý, chứ không chỉ dữ liệu tiếng Anh.

### 2.3. Encoding khác Unicode normalization

UTF-8 là một *encoding*; NFC/NFD là các dạng **chuẩn hóa Unicode**. Hai chuỗi có thể hiển thị giống nhau nhưng có code point hoặc dãy byte khác nhau.

Ví dụ, một ký tự có dấu đôi khi được biểu diễn bằng một code point dựng sẵn hoặc bằng ký tự gốc cộng dấu kết hợp. Chuyển byte sang UTF-8 không tự động chuẩn hóa NFC.

Trong migration, cần phân biệt:

- **Sai charset:** byte được giải mã bằng bảng mã không đúng.
- **Mojibake:** chuỗi hiển thị thành ký tự sai như `Ã`, `Â` hoặc dấu hỏi do một hoặc nhiều lần mã hóa/giải mã không thống nhất.
- **Sai normalization:** code point khác nhau dù hình thức hiển thị tương tự.
- **Mất dữ liệu:** ký tự đã bị thay bằng `?` hoặc `�` trước khi chuyển đổi.

Mỗi loại đòi hỏi hướng xử lý riêng. Không thể sửa mọi trường hợp bằng cách “chuyển lại UTF-8”.

## 3. Default charset thay đổi theo phiên bản Java thế nào?

### 3.1. Trước Java 18: thường phụ thuộc môi trường

Ở các JDK trước Java 18, default charset của nhiều API Java SE có thể được chọn theo hệ điều hành, locale, cấu hình môi trường hoặc cách khởi chạy JVM.

Ví dụ, một chương trình sử dụng:

```java
byte[] data = text.getBytes();
String decoded = new String(data);
```

đã ngầm dùng `Charset.defaultCharset()` để chuyển đổi. Nó có thể chạy đúng trên một máy phát triển nhưng hỏng khi chạy trên máy hoặc container khác có default charset không giống nhau.

Không nên khẳng định cứ chạy trên Windows là charset X hoặc Linux là UTF-8. Kết quả thực tế phải được xác minh trên môi trường và JDK cụ thể.

### 3.2. Java 18+: JEP 400 và UTF-8 mặc định

**JEP 400 (UTF-8 by Default)** được đưa vào từ Java 18. Với các API Java SE thuộc phạm vi thay đổi này, default charset được chuẩn hóa thành UTF-8, giúp hành vi ổn định hơn giữa nhiều nền tảng.

Điều này có hai mặt:

- **Lợi ích:** mã mới ít phụ thuộc locale hệ điều hành hơn; dữ liệu UTF-8 được xử lý nhất quán hơn.
- **Rủi ro tương thích:** mã cũ có thể ngầm giả định default charset là một encoding khác. Khi chuyển JDK, cùng `new String(bytes)` hoặc `FileReader` có thể giải mã khác trước.

Không phải **mọi** xử lý văn bản trong Java đều tự động chuyển sang UTF-8. Những API có quy tắc charset riêng, các giao thức truyền thông, file `.properties` và luồng console có đặc điểm đặc thù, cần kiểm tra riêng.

### 3.3. Kiểm tra default charset đang dùng

Có thể ghi log trong môi trường kiểm thử:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

public final class CharsetDiagnostics {
    public static void main(String[] args) {
        System.out.println("Default charset: "
                + Charset.defaultCharset());
        System.out.println("file.encoding: "
                + System.getProperty("file.encoding"));
        System.out.println("native.encoding: "
                + System.getProperty("native.encoding"));
        System.out.println("UTF-8 available: "
                + Charset.isSupported(StandardCharsets.UTF_8.name()));
    }
}
```

Đọc kết quả cùng thông tin JDK vendor/version và JVM arguments. `native.encoding` cung cấp thông tin về encoding nền tảng ở những JDK hỗ trợ property này; nó không đồng nghĩa mọi API đang dùng encoding đó.

Nếu cần quan sát hành vi vận hành, hãy đo bằng chính chương trình đọc/ghi file đại diện, thay vì kết luận hoàn toàn từ một system property.

### 3.4. `file.encoding` không nên là API điều khiển dữ liệu lâu dài

Một số ứng dụng cố điều khiển default charset bằng:

```bash
java -Dfile.encoding=UTF-8 -jar application.jar
```

Trên các JDK thuộc giai đoạn trước và sau JEP 400, quy tắc và giá trị được hỗ trợ của property này khác nhau; Java 18+ có cơ chế tương thích như `-Dfile.encoding=COMPAT` cho mục đích quay về cách chọn encoding theo môi trường trong những trường hợp được hỗ trợ.

**Không nên thay đổi `file.encoding` bằng `System.setProperty` trong lúc ứng dụng đang chạy rồi kỳ vọng mọi API lập tức thay charset.** Khả năng khởi tạo/cache, thời điểm chọn charset và hành vi theo JDK có thể không đáp ứng kỳ vọng đó.

Dùng property kiểu này, nếu bắt buộc, chỉ nên là **giải pháp chuyển tiếp được kiểm thử**. Giải pháp lâu dài là chọn charset tường minh tại biên đọc/ghi dữ liệu.

### 3.5. Bảng rủi ro theo giai đoạn migration

| Giai đoạn | Hành vi cần chú ý | Rủi ro |
| --- | --- | --- |
| Java 8–17 | Default charset của nhiều API có thể phụ thuộc môi trường. | Dữ liệu chỉ đúng ở một máy/locale; container khác đọc sai. |
| Java 18+ | UTF-8 trở thành default charset cho những API thuộc JEP 400. | File cũ không phải UTF-8 bị đọc sai dù source không đổi. |
| Đổi JVM vendor/container | Locale, timezone, OS image, font và encoding của công cụ ngoài có thể khác. | Log, file batch, import/export hoặc terminal không thống nhất. |
| Chuyển sang encoding tường minh | Từng luồng dùng charset được xác định trong contract. | Cần xác định đúng encoding nguồn; không được giả định mọi dữ liệu cũ là UTF-8. |

## 4. Những API dễ vô tình dùng default charset

### 4.1. Chuyển đổi `String` và `byte[]`

**Không tường minh:**

```java
byte[] bytes = text.getBytes();
String value = new String(bytes);
```

**Tường minh UTF-8:**

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String value = new String(bytes, StandardCharsets.UTF_8);
```

Nếu byte đầu vào là dữ liệu cũ ở một charset khác, việc thay `new String(bytes)` bằng UTF-8 mà không kiểm tra nguồn sẽ không làm dữ liệu trở nên đúng. Charset **đọc** phải tương ứng với dữ liệu nguồn; charset **ghi** phải tương ứng contract đích.

### 4.2. Reader, Writer và stream

Các constructor không chỉ định charset như `new FileReader(file)`, `new FileWriter(file)`, `new InputStreamReader(in)` và `new OutputStreamWriter(out)` thường dùng default charset.

Ví dụ một đường đọc ổn định:

```java
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("data/input.txt");

try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
```

Ghi file:

```java
try (var writer =
        Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("Dữ liệu UTF-8");
}
```

Những helper trên thể hiện rõ contract UTF-8 tại chỗ đọc/ghi. Nếu phải hỗ trợ Java 8, dùng `Paths.get(...)` và khai báo kiểu biến tường minh thay cho `Path.of` và `var`.

### 4.3. Một số API mặc định **đã** là UTF-8

Không phải API nào bỏ qua tham số charset cũng sử dụng `Charset.defaultCharset()`. Chẳng hạn:

- `Files.readString(Path)` / `Files.writeString(Path, ...)` (Java 11+) mặc định dùng UTF-8.
- `Files.newBufferedReader(Path)` và `Files.newBufferedWriter(Path)` mặc định dùng UTF-8.
- `Files.readAllLines(Path)` mặc định dùng UTF-8.
- `Files.lines(Path)` mặc định dùng UTF-8.

Vì vậy phải đọc contract **từng API**. Không áp dụng quy tắc máy móc “không truyền charset tức dùng default charset”.

Với code cần làm rõ chủ đích, phiên bản có tham số `StandardCharsets.UTF_8` thường dễ audit hơn.

### 4.4. `Scanner`, `PrintWriter`, `PrintStream` và công cụ I/O cấp cao

Một số overload của `Scanner`, `PrintWriter` hoặc `PrintStream` có thể chọn charset mặc định theo contract của JDK đang dùng. Các overload khác cho phép khai báo charset tường minh.

Khi audit, không chỉ tìm `new String`; cần kiểm tra constructors, factories, wrappers và thư viện bên thứ ba có thể làm việc đọc/ghi thay ứng dụng.

## 5. Tìm các điểm dùng charset ngầm trong repository

Có thể dùng tìm kiếm mã nguồn như một bước đầu:

```bash
rg -n 'new String\(|\.getBytes\(\)|new FileReader\(|new FileWriter\(|new InputStreamReader\(|new OutputStreamWriter\(' src
```

Tìm những luồng ghi/đọc khác:

```bash
rg -n 'Scanner\(|PrintWriter\(|PrintStream\(|readAllBytes\(|Files\.readString\(|Files\.writeString\(|getProperty\("file.encoding"|Charset\.defaultCharset' .
```

Các kết quả chỉ là **điểm điều tra**, không phải lỗi chắc chắn. Có lời gọi cần default charset theo contract hệ thống; có lời gọi `new String` đã dùng charset ở tham số khác; có thư viện dùng encoding tường minh nhưng source app không thể hiện.

Với mỗi điểm, ghi lại:

| Trường | Cần xác định |
| --- | --- |
| Nguồn byte | File, network, database BLOB, clipboard, process output, queue hay plugin. |
| Charset nguồn | Giá trị được công bố, cấu hình hoặc xác minh từ dữ liệu gốc. |
| API decode | Method/constructor chuyển byte thành `String`. |
| API encode | Method/constructor chuyển `String` thành byte. |
| Charset đích | UTF-8, legacy charset, protocol-mandated charset hoặc binary không chuyển. |
| Chủ sở hữu dữ liệu | Service, đối tác, hệ thống batch hoặc team triển khai. |
| Môi trường | JDK/OS/container/locale nơi luồng đang chạy. |
| Bằng chứng | Byte sample, metadata, test, đặc tả giao thức và log. |

Mục tiêu là xác định **ranh giới chuyển đổi** thay vì thay hàng loạt tất cả lời gọi bằng UTF-8.

## 6. Phân loại dữ liệu trước khi chuyển sang UTF-8

### 6.1. Dữ liệu text thuần

Ví dụ `.txt`, tài liệu export hoặc log text. Có thể đọc bằng charset nguồn rồi ghi UTF-8 sau khi xác minh các dòng thực tế.

Những thuộc tính cần ghi nhận:

- Kiểu xuống dòng: LF, CRLF hoặc CR.
- BOM có hay không.
- Ký tự đặc biệt hoặc control character.
- Encoding gốc và nguồn xác nhận.
- Quy ước tên file, timestamp và quyền truy cập.

### 6.2. Dữ liệu có định dạng riêng

CSV, XML, HTML, JSON, YAML và các file cấu hình đều là text nhưng có **hợp đồng định dạng** khác nhau.

Ví dụ, đổi byte của CSV sang UTF-8 vẫn phải giữ delimiter, quote escaping, thứ tự cột và cách thể hiện newline. XML cần nhất quán giữa byte thực tế và `encoding` trong XML declaration. HTML có thể chứa charset trong HTTP header hoặc thẻ `meta`.

Không xử lý định dạng có cấu trúc như một chuỗi byte để tìm-thay các ký tự tùy tiện. Hãy dùng parser/serializer phù hợp nếu cần biến đổi nội dung.

### 6.3. Dữ liệu binary hoặc hỗn hợp

Ảnh, PDF, ZIP, protobuf, encrypted payload, file nén và database BLOB không phải văn bản tùy ý. Không “convert sang UTF-8” các byte này.

Có những định dạng chứa cả phần binary và trường văn bản. Cần dùng parser của định dạng để xác định **chính xác trường cần chuyển encoding**, tránh làm hỏng signature, length field, checksum hoặc cấu trúc nhị phân.

### 6.4. Dữ liệu không xác định encoding

Không phải lúc nào có thể nhận diện encoding một cách chắc chắn chỉ từ byte. Một dãy byte ASCII cũng là UTF-8 hợp lệ và có thể hợp lệ trong nhiều charset khác.

Ngay cả khi byte hợp lệ theo cú pháp UTF-8, điều đó **chưa đủ chứng minh** tác giả đã dùng UTF-8. Phải ưu tiên metadata có thẩm quyền: đặc tả, HTTP `Content-Type`, contract đối tác, cấu hình hệ thống cũ hoặc xác nhận từ người tạo dữ liệu.

Nếu không đủ bằng chứng, đánh dấu trạng thái *chưa xác định*, lấy thêm sample và không ghi đè dữ liệu gốc.

## 7. Chuyển đổi có kiểm soát: decode nguồn → encode đích

### 7.1. Sai lầm: thay charset ở đầu ra nhưng không biết đầu vào

Ví dụ không an toàn:

```java
byte[] oldBytes = Files.readAllBytes(source);
String text = new String(oldBytes, StandardCharsets.UTF_8);
Files.write(target, text.getBytes(StandardCharsets.UTF_8));
```

Nếu `oldBytes` vốn mã hóa bằng Windows-1258, việc dùng UTF-8 để decode có thể tạo ký tự thay thế hoặc dữ liệu biến dạng; ghi UTF-8 sau đó sẽ **lưu cố định lỗi**.

Quy trình đúng:

```text
Byte nguồn (legacy charset đã xác định)
             |
             | Decode bằng charset nguồn
             v
      Ký tự Unicode đúng
             |
             | Kiểm tra nội dung, lỗi, ký tự đặc biệt
             v
       Encode bằng UTF-8
             |
             v
   Byte đích UTF-8 và metadata cập nhật
```

### 7.2. Ví dụ đơn giản cho dữ liệu legacy đã biết encoding

Nếu đặc tả nguồn xác nhận ISO-8859-1:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path source = Path.of("legacy.txt");
Path target = Path.of("converted.txt");

byte[] originalBytes = Files.readAllBytes(source);
String content =
        new String(originalBytes, StandardCharsets.ISO_8859_1);

Files.write(target, content.getBytes(StandardCharsets.UTF_8));
```

Đây là ví dụ về **hướng chuyển đổi**, không phải cách tự phát hiện charset. ISO-8859-1 không phù hợp để mã hóa đầy đủ tiếng Việt; nó chỉ được sử dụng khi nguồn thật sự xác nhận charset đó.

Trong hệ thống dữ liệu tiếng Việt cũ, có thể gặp Windows-1258, TCVN3/ABC hoặc VNI. **TCVN3 và VNI có thể cần bộ chuyển mã chuyên dụng**, không thể giả định `Charset.forName` của Java hỗ trợ trực tiếp mọi quy ước legacy. Với Windows-1258, kiểm tra charset được JDK cụ thể hỗ trợ và xác nhận dữ liệu mẫu trước khi dùng.

### 7.3. Vì sao cần decoding nghiêm ngặt?

Một số convenience API như `new String(bytes, charset)` có thể thay chuỗi byte sai bằng ký tự thay thế thay vì ném lỗi. Khi chuyển dữ liệu hàng loạt, hành vi này rất nguy hiểm: công cụ có thể “thành công” nhưng đánh mất khả năng khôi phục ký tự ban đầu.

Khi yêu cầu không mất dữ liệu, sử dụng `CharsetDecoder` với:

- `CodingErrorAction.REPORT` cho malformed input.
- `CodingErrorAction.REPORT` cho unmappable character khi giải mã.
- Xử lý lỗi riêng, không âm thầm dùng `REPLACE` hoặc `IGNORE`.

Ví dụ:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.Charset;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;

static String decodeStrict(byte[] bytes, Charset source)
        throws java.nio.charset.CharacterCodingException {
    CharsetDecoder decoder = source.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);

    CharBuffer chars = decoder.decode(ByteBuffer.wrap(bytes));
    return chars.toString();
}
```

Nếu decoder báo lỗi, cần giữ nguyên file nguồn, ghi lại vị trí/số lượng lỗi theo khả năng của công cụ, và chuyển trường hợp đó sang luồng xử lý riêng. Không tự sửa byte lỗi khi chưa có quy tắc được phê duyệt.

### 7.4. Ví dụ chuyển đổi file có backup và ghi file tạm

Một quy trình đơn giản dùng Java 11+ có thể gồm:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.Charset;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public final class SafeTextConverter {
    public static void convert(Path source, Path target, Charset sourceCharset)
            throws Exception {
        // Chỉ đọc source, không ghi đè file gốc.
        byte[] raw = Files.readAllBytes(source);

        CharsetDecoder decoder = sourceCharset.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        CharBuffer chars = decoder.decode(ByteBuffer.wrap(raw));
        ByteBuffer utf8 = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(chars);

        byte[] converted = new byte[utf8.remaining()];
        utf8.get(converted);

        Path absoluteTarget = target.toAbsolutePath();
        Path directory = absoluteTarget.getParent();
        Path temp = Files.createTempFile(directory, "utf8-", ".tmp");

        try {
            Files.write(temp, converted);
            // Không thay thế file đích đang tồn tại nếu chưa được duyệt.
            Files.move(temp, absoluteTarget);
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
```

Đoạn code trên là **mẫu minh họa** cho luồng decode-then-encode và staging, chưa phải tiện ích migration hoàn chỉnh. `Files.move(temp, target)` không bảo đảm atomic move trên mọi filesystem; nếu cần atomicity và durability phải kiểm tra khả năng của filesystem, chính sách ghi đồng thời, fsync, quyền file và quy trình recover. Nó cũng giả định đủ RAM để giữ toàn bộ file; với file lớn cần chuyển đổi theo luồng bằng decoder/encoder có trạng thái, xử lý đúng multibyte sequence qua ranh giới buffer.

Trong migration thực tế, nên sao lưu dữ liệu gốc vào vị trí bất biến hoặc có version trước khi chạy batch. Không dùng code này để tự ghi đè hàng loạt dữ liệu chưa được phê duyệt.

### 7.5. Đừng chuyển lại file đã là UTF-8

Trước khi chạy batch, mỗi file/record cần có trạng thái:

| Trạng thái | Hành động |
| --- | --- |
| Encoding nguồn đã xác nhận là legacy | Decode nguồn, validate, encode UTF-8. |
| Đã là UTF-8 đúng | Giữ nguyên hoặc chuẩn hóa metadata nếu cần; không biến đổi không cần thiết. |
| Encoding chưa xác định | Không tự động chuyển; yêu cầu xác minh. |
| Dữ liệu đang bị mojibake | Điều tra lịch sử encode/decode; không áp dụng pipeline legacy-to-UTF8 thông thường. |
| Dữ liệu đã mất ký tự | Khôi phục từ backup hoặc hệ thống nguồn nếu có; re-encode không cứu được thông tin mất. |
| Binary | Không chuyển charset. |

Cần thiết kế batch **idempotent**: chạy lại không được làm dữ liệu sai thêm lần nữa. Cách phổ biến là lưu manifest chứa nguồn, version, charset, checksum, trạng thái và kết quả chuyển đổi.

## 8. BOM, newline và Unicode normalization

### 8.1. BOM trong UTF-8

UTF-8 có thể xuất hiện với byte order mark `EF BB BF` ở đầu file. UTF-8 không cần BOM để xác định thứ tự byte, nhưng một số công cụ hoặc hệ thống cũ dùng BOM làm dấu nhận diện.

Một số parser có thể chấp nhận BOM, trong khi ứng dụng khác lại coi nó là ký tự `U+FEFF` ở đầu chuỗi và xử lý sai header, tên cột hoặc identifier.

Trước khi chuyển:

- Xác định consumer có yêu cầu BOM không.
- Xác định nguồn có BOM UTF-8, UTF-16LE hoặc UTF-16BE.
- Không chỉ strip ba byte `EF BB BF` nếu file thực tế chưa được xác định là UTF-8.
- Không tự động loại bỏ ký tự `U+FEFF` giữa nội dung khi nó có thể mang ý nghĩa dữ liệu.

### 8.2. Newline và delimiter

Thay encoding không nhất thiết phải thay newline. Nếu job đang xuất CRLF để hệ thống ngoài đọc, việc đổi sang LF có thể làm hợp đồng thay đổi dù mọi ký tự đều hiển thị đúng.

Đối với CSV, cần giữ nguyên quy tắc quote và delimiter; với TSV, cần kiểm tra ký tự tab trong dữ liệu. Tách vấn đề **charset** khỏi những thay đổi cấu trúc file khác để dễ đối chiếu và rollback.

### 8.3. Normalization

Nếu hệ thống cần so khớp chuỗi tiếng Việt với nhau, có thể phải thống nhất Unicode normalization, ví dụ NFC. Tuy nhiên, **không nên tự normalize toàn bộ dữ liệu** trong cùng một batch chuyển mã trừ khi đặc tả yêu cầu, vì có thể làm thay đổi dãy code point, checksum hoặc ý nghĩa của dữ liệu đầu vào.

Thay charset và chuẩn hóa Unicode là hai quyết định độc lập; mỗi thay đổi cần test riêng.

## 9. Các biên hệ thống dễ bị ảnh hưởng

### 9.1. File CSV/Excel

Một hệ thống batch có thể xuất CSV để người dùng mở bằng phần mềm bảng tính. Consumer có thể dựa vào locale, BOM hoặc cấu hình import để hiểu encoding.

Khi chuyển sang UTF-8:

- Thỏa thuận encoding với bên nhận.
- Dùng UTF-8 tường minh khi tạo file.
- Test mở/import trên đúng công cụ và phiên bản khách hàng sử dụng.
- Xác định có cần UTF-8 BOM không, thay vì tự thêm trong mọi trường hợp.
- Test dấu tiếng Việt, ký tự phân tách và dấu xuống dòng trong ô.

Việc file hợp lệ theo UTF-8 không đảm bảo phần mềm nhận tự chọn UTF-8.

### 9.2. HTTP và API

Với dữ liệu truyền qua HTTP, charset là một phần của **contract nội dung** cùng với media type và header. Ví dụ `Content-Type: text/plain; charset=UTF-8` giúp consumer xác định cách decode.

Không chỉ thay code `getBytes()` rồi bỏ qua header. Server, client, reverse proxy và framework có thể áp dụng mặc định khác nhau cho từng media type.

Khi gửi JSON, dùng quy tắc encoding của giao thức và thư viện JSON được hỗ trợ; khi gửi form hoặc plain text, xác định rõ encoding theo chuẩn và hợp đồng đối tác. Không áp dụng một giả định duy nhất cho mọi giao thức.

### 9.3. Database

Cơ sở dữ liệu có encoding, collation và cấu hình driver riêng. Java `String` được chuyển thành dữ liệu wire/database theo contract của driver và connection.

Các điểm cần rà soát:

- Encoding của database/schema/column.
- Charset và cấu hình kết nối JDBC.
- Dữ liệu có đang lưu đúng Unicode hay chỉ “đúng” vì từng bị decode sai nhưng dùng cùng cách đọc lại.
- Import/export CSV hoặc dump SQL có charset tường minh không.
- Collation, normalization và so sánh chuỗi có thay đổi ngoài ý muốn không.

Đổi `Charset.defaultCharset()` không phải thao tác chuyển đổi encoding toàn bộ database. Với dữ liệu BLOB chứa văn bản legacy, phải biết charset của nội dung BLOB rồi mới chuyển.

### 9.4. Message queue và file trao đổi

Nếu payload được truyền dưới dạng `byte[]`, cả producer và consumer cần thống nhất encoding. Nếu framework tự serialize object hoặc JSON, cần kiểm tra cấu hình serializer.

Một producer nâng JDK có thể bắt đầu ghi UTF-8 trong khi consumer cũ vẫn đọc theo encoding cũ. Vì vậy nên triển khai contract/versioning trước khi bật thay đổi, hoặc hỗ trợ song song theo cơ chế được thống nhất.

### 9.5. Console, stdout, stderr và log

Encoding của terminal, console hoặc output stream có thể khác với `Charset.defaultCharset()` tùy JDK, OS và cách JVM được khởi chạy. Không được suy luận rằng mọi dòng `System.out.println` sẽ tự động phù hợp với file log của container.

Kiểm tra riêng:

- Console tương tác của người phát triển.
- Output được redirect vào file.
- Output của process Java được chương trình khác đọc bằng `ProcessBuilder`.
- File log do logging framework tạo.
- Log được thu thập và hiển thị bởi container/logging platform.

Nếu application ghi file log văn bản, cấu hình encoder/file appender của logging framework với charset rõ ràng. Nếu đọc stdout của process khác, phải xác định encoding mà process đó thực sự xuất.

### 9.6. Native integration

JNI/JNA hoặc chương trình ngoài có thể dùng kiểu chuỗi/byte theo quy ước nền tảng. Không áp dụng UTF-8 cho một API native mà contract của nó quy định encoding khác.

Với `ProcessBuilder`, Java khởi động command ngoài nhưng không tự chuyển nội dung stdout/stderr thành UTF-8 đúng cho mọi chương trình. Khi đọc stream, xác định charset của process ở môi trường thực tế.

## 10. Các ngoại lệ quan trọng: Properties và ResourceBundle

### 10.1. `Properties.load(InputStream)` không dùng default charset theo cách thông thường

`java.util.Properties.load(InputStream)` có quy tắc riêng: byte trong stream được đọc theo ISO-8859-1, với ký tự ngoài phạm vi đó có thể được biểu diễn bằng Unicode escape trong định dạng properties tương ứng.

Ví dụ:

```java
Properties config = new Properties();

try (InputStream in = Files.newInputStream(Path.of("legacy.properties"))) {
    config.load(in);
}
```

Không nên nghĩ rằng chỉ vì JVM default charset đã là UTF-8 nên đoạn code trên tự đọc `.properties` như UTF-8. Quy tắc của overload `InputStream` vẫn độc lập với `Charset.defaultCharset()`.

Nếu đặc tả của file xác nhận UTF-8, có thể dùng overload `Reader`:

```java
Properties config = new Properties();

try (Reader reader = Files.newBufferedReader(
        Path.of("utf8.properties"), StandardCharsets.UTF_8)) {
    config.load(reader);
}
```

Cần xét cả quy trình tạo và tiêu thụ properties; một file cũ với escape sequence không giống file UTF-8 raw text trong mọi tình huống.

### 10.2. ResourceBundle property files

Cách `ResourceBundle` xử lý property resource có quy tắc riêng theo JDK và thay đổi từ Java 9. Khi nâng từ Java 8, cần kiểm tra các resource bundle đã đóng gói trong JAR, nhất là file có tiếng Việt hoặc ký tự ngoài ASCII.

Đừng tự suy luận từ `Charset.defaultCharset()`. Kiểm tra contract của phiên bản Java mục tiêu và các property điều khiển encoding nếu có; chạy test với đúng resource, locale và class loader thực tế.

### 10.3. Source file encoding và runtime charset là hai vấn đề khác nhau

Compiler đọc file `.java` dựa trên cấu hình của nó, còn chương trình sau khi chạy đọc/ghi file nghiệp vụ theo API runtime.

Một dự án có thể biên dịch source UTF-8 thành công nhưng xử lý dữ liệu đầu vào sai vì `FileReader` dùng default charset không mong muốn.

Với Maven/Gradle, cấu hình encoding của source và resources phù hợp; với `javac` thuần có thể dùng `-encoding UTF-8` cho mã nguồn. Điều này không tự đổi encoding của các file nghiệp vụ mà app đọc sau khi triển khai.

## 11. Kiểm thử migration theo ma trận môi trường

### 11.1. Thiết kế test có ký tự phân biệt

Tập dữ liệu mẫu nên có:

```text
ASCII:        Hello 123
Tiếng Việt:   Hà Nội, Đà Nẵng, Cần Thơ, Nguyễn
Có dấu:       tiếng Việt, dữ liệu, kiểm thử
Ký hiệu:      €, £, ©, →, ✓
Ngoài BMP:    một ký tự emoji phù hợp với contract
Biên đặc biệt: dòng trống, newline, tab, dấu nháy kép
```

Nếu hệ thống không hỗ trợ một nhóm ký tự, ghi rõ giới hạn contract thay vì im lặng mất ký tự.

### 11.2. Kiểm tra cả byte và nội dung

Không chỉ so sánh chuỗi hiển thị trên terminal. Cần kiểm tra:

1. Byte đầu vào và checksum trước chuyển đổi.
2. Charset nguồn được xác định bằng bằng chứng.
3. Kết quả decode strict có lỗi hay không.
4. Nội dung Unicode có giống mẫu mong đợi không.
5. Byte đích là UTF-8 hợp lệ và đúng contract không.
6. Dữ liệu sau khi consumer thật đọc vào có giữ nguyên nghĩa không.

Có thể xem byte file bằng các công cụ hex viewer. Đừng dùng một terminal đang decode sai encoding để khẳng định file gốc đã hỏng.

### 11.3. Test với default charset khác nhau

Lập ma trận thử nghiệm theo môi trường hỗ trợ:

| Ca thử | JDK/môi trường | Đầu vào | Kết quả mong muốn |
| --- | --- | --- | --- |
| Baseline | JDK cũ, locale hiện tại | File legacy thật | Ghi lại output và byte hiện hành. |
| JDK mới | JDK mục tiêu với cấu hình mặc định | Cùng file legacy | Kết quả được giải mã theo charset nguồn tường minh. |
| UTF-8 chuẩn | JDK mục tiêu | File UTF-8 hợp lệ | Không thay đổi ký tự. |
| Dữ liệu lỗi | JDK mục tiêu | Byte không hợp lệ với charset khai báo | Báo lỗi và giữ nguyên nguồn. |
| Đã chuyển | JDK mục tiêu | File UTF-8 có manifest | Không chuyển lặp gây biến dạng. |
| Tích hợp | Producer mới, consumer hiện tại | Message/file/API | Consumer nhận đúng ký tự và metadata. |

Nếu ứng dụng phải chạy trên nhiều JDK hoặc hệ điều hành, test trên các môi trường đó theo phạm vi hỗ trợ. **Cấu hình charset tường minh** là cách quan trọng để giảm phụ thuộc vào ma trận môi trường.

### 11.4. Unit test ví dụ cho UTF-8

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class Utf8RoundTripTest {
    @Test
    void preservesVietnameseCharacters() {
        String original = "Đà Nẵng – dữ liệu UTF-8";
        byte[] encoded = original.getBytes(StandardCharsets.UTF_8);
        String decoded =
                new String(encoded, StandardCharsets.UTF_8);

        assertEquals(original, decoded);
    }
}
```

Test trên bảo vệ một luồng round trip cơ bản. **Chưa đủ** để xác nhận logic chuyển dữ liệu legacy: nếu decoder nguồn sai nhưng cả encode/decode sau đó cùng sai theo một cách, round trip mới vẫn có thể pass. Test migration nên dùng byte fixture legacy đã biết trước và expected Unicode do nguồn dữ liệu xác nhận.

## 12. Lộ trình chuyển dữ liệu sang UTF-8 có kiểm soát

### Bước 1: Chụp baseline

Ghi lại JDK vendor/version, default charset thực tế, cấu hình source encoding, OS/locale, container image, JVM arguments và danh sách biên đọc/ghi dữ liệu.

Lưu sample byte thật, checksum và kết quả hiện tại của các luồng quan trọng. Tạo backup trước khi thay đổi.

### Bước 2: Kiểm kê nguồn và chủ sở hữu

Tìm những API dùng charset ngầm định, hệ thống lưu file legacy, batch job và luồng trao đổi dữ liệu ngoài. Gắn mỗi nguồn với chủ sở hữu và contract đã công bố.

Không đánh đồng “text trong source repository” với “mọi file nghiệp vụ”.

### Bước 3: Xác định charset nguồn

Ưu tiên tài liệu và metadata nguồn. Nếu cần phân tích byte, kết hợp nhiều sample và ý kiến chủ sở hữu. Không để công cụ heuristic tự kết luận cho toàn bộ tập dữ liệu.

Các file chưa xác định phải đi vào danh sách chờ xử lý, không được âm thầm chuyển.

### Bước 4: Chuẩn hóa contract UTF-8 tại biên hệ thống

Trước khi sửa batch converter, thống nhất consumer nào nhận UTF-8, định dạng có cần BOM không, header nào phải đổi, và hỗ trợ chuyển tiếp song song ra sao.

Với API và message queue, nên chuẩn bị cả producer và consumer; không chỉ nâng một phía rồi kỳ vọng mọi phía tự nhận diện được charset mới.

### Bước 5: Sửa mã I/O sang charset tường minh

Thay những chỗ đang dựa ngầm vào default charset bằng đọc theo **charset nguồn** và ghi theo **charset đích**. Với luồng dữ liệu mới có contract UTF-8, dùng `StandardCharsets.UTF_8`.

Tách rõ các API theo quy tắc riêng như `Properties.load(InputStream)`, `ResourceBundle` và output console.

### Bước 6: Thử chuyển đổi trên bản sao

Chạy batch trên staging với dữ liệu sao chép. Decode strict, lưu báo cáo lỗi, kiểm tra byte đầu ra, so sánh nội dung nghiệp vụ và thử nhập vào consumer thật.

Tránh chạy trực tiếp trên dữ liệu production ở lần thử đầu tiên.

### Bước 7: Lập manifest và cơ chế rollback

Manifest có thể chứa:

| Thuộc tính | Ví dụ ý nghĩa |
| --- | --- |
| Dataset / file ID | Định danh ổn định của dữ liệu nguồn. |
| Source encoding | Giá trị đã được xác minh. |
| Target encoding | `UTF-8`. |
| Source checksum | Phát hiện nguồn bị thay đổi giữa các lần chạy. |
| Backup location | Vị trí khôi phục, có phân quyền. |
| Conversion version | Phiên bản tool/thuật toán đã dùng. |
| Converted checksum | Kiểm tra đầu ra đúng phiên bản. |
| Status | Pending, converted, validated, quarantined. |
| Validation evidence | Test, sample, người xác nhận. |

Khả năng rollback phải dựa trên backup hoặc bản gốc bất biến, không dựa vào việc luôn có thể chuyển ngược dữ liệu đã bị thay thế ký tự.

### Bước 8: Rollout từng phần và theo dõi

Ưu tiên canary hoặc một tập dữ liệu nhỏ. Đo lỗi decode, số lượng file bị cách ly, số record lỗi, tỷ lệ consumer đọc thành công và các sự cố hiển thị ký tự.

Khi kết quả ổn định, mở rộng theo batch có giới hạn, tránh sửa toàn bộ dữ liệu một lần khó khôi phục.

### Bước 9: Chốt contract và loại bỏ workaround

Sau chuyển đổi, cập nhật tài liệu API/file format, source encoding trong build, ví dụ import/export và runbook vận hành. Nếu từng dùng `-Dfile.encoding=COMPAT` như bước chuyển tiếp, lập kế hoạch bỏ sau khi các luồng phụ thuộc ngầm đã được xử lý.

## 13. Lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân có thể | Bước điều tra |
| --- | --- | --- |
| Ký tự tiếng Việt thành `Ã...` hoặc chuỗi lạ | UTF-8 được giải mã bằng charset khác, hoặc decode/encode lặp sai. | Xem raw bytes, lịch sử chuyển đổi, encoding nguồn/đích. |
| Ký tự thành `?` | Encoder không biểu diễn được ký tự và đã dùng replacement. | Kiểm tra bộ mã ở lần ghi đầu tiên; tìm backup gốc. |
| Ký tự `�` xuất hiện | Decoder đã dùng replacement cho byte sai. | Tìm nguồn byte gốc và bật decode strict. |
| File đọc đúng ở máy dev nhưng sai trên server | Default charset khác giữa môi trường. | Log `Charset.defaultCharset()` và audit API không có charset. |
| CSV hiện dấu lỗi khi mở Excel | Consumer chọn encoding khác hoặc mong đợi BOM/import option. | Thử đúng công cụ đích, thỏa thuận UTF-8/BOM. |
| File `.properties` không đúng tiếng Việt | Dùng sai overload hoặc hiểu nhầm quy tắc charset. | Kiểm tra `load(InputStream)` so với `load(Reader)`. |
| XML/HTML báo encoding sai | Declaration/header không khớp byte. | Kiểm tra metadata và byte thực tế. |
| Log trên container sai nhưng file output đúng | Charset của console/collector khác với file encoder. | Kiểm tra stdout, appender, collector, terminal. |
| Dữ liệu vẫn sai sau khi ghi UTF-8 | Chuỗi trong bộ nhớ đã bị decode sai trước đó. | Kiểm tra đúng bước decode đầu tiên; không chỉ bước encode. |
| Batch chuyển lần hai làm hỏng file | Không lưu trạng thái, không idempotent. | Thêm manifest, checksum và chặn convert lặp. |

Một nguyên tắc quan trọng: **đừng sửa ký tự đang hiển thị sai trước khi xác định raw byte ở biên gây lỗi**. Nếu sai ở terminal chứ không ở file, chuyển file sẽ tạo thêm vấn đề.

## 14. Về hiệu năng và dữ liệu lớn

Ví dụ `Files.readAllBytes` phù hợp cho file nhỏ hoặc bài thực hành, nhưng đọc hàng GB dữ liệu vào RAM có thể gây áp lực bộ nhớ hoặc `OutOfMemoryError`.

Với dữ liệu lớn, nên dùng:

- `InputStream` kết hợp `InputStreamReader` có `CharsetDecoder` cấu hình strict.
- `OutputStream` kết hợp `OutputStreamWriter` sử dụng UTF-8.
- Buffer phù hợp và xử lý đúng chuỗi byte multibyte qua ranh giới buffer.
- Cơ chế ghi file tạm, checkpoint, checksum và retry idempotent.
- Phân vùng batch theo file hoặc record để cách ly lỗi.

Nếu chuyển đổi qua `Reader`/`Writer`, kiểm tra chính sách BOM, newline và cách xử lý invalid input. Đo throughput với dữ liệu đại diện nhưng không hy sinh kiểm soát lỗi để lấy tốc độ.

## 15. Checklist hoàn tất migration charset

- [ ] Đã phân biệt byte-level encoding với Unicode text và normalization.
- [ ] Đã ghi lại default charset của JDK cũ và JDK mục tiêu trong môi trường thực tế.
- [ ] Đã xác định tác động của JEP 400 nếu migration lên Java 18+.
- [ ] Đã rà soát các lời gọi `new String(byte[])`, `getBytes()`, Reader/Writer và các thư viện I/O.
- [ ] Đã xác nhận các API có quy tắc charset riêng, không dùng default charset theo giả định.
- [ ] Đã kiểm kê file, API, queue, log, database import/export và native integration.
- [ ] Đã xác định charset nguồn bằng metadata hoặc bằng chứng đáng tin cậy.
- [ ] Đã phân loại dữ liệu UTF-8 sẵn, legacy, chưa xác định, mojibake và binary.
- [ ] Đã có backup, checksum, manifest, dry run và phương án rollback.
- [ ] Đã dùng decoder strict hoặc một chính sách lỗi được phê duyệt, không thay ký tự âm thầm.
- [ ] Đã xác nhận BOM, newline, delimiter và metadata file/giao thức.
- [ ] Đã thử dữ liệu tiếng Việt, ký tự đặc biệt, dữ liệu lỗi và file đã chuyển.
- [ ] Đã xác minh consumer thật đọc đúng UTF-8, không chỉ unit test encode/decode.
- [ ] Đã chuẩn hóa contract và loại bỏ workaround default charset khi an toàn.

## 16. Kết luận

Default charset là một **hành vi môi trường**, không phải một hợp đồng dữ liệu đáng tin cậy cho hệ thống cần chạy trên nhiều phiên bản Java và nền tảng khác nhau. Với Java 18+, UTF-8 trở thành mặc định cho những API thuộc phạm vi JEP 400, nhưng dữ liệu được tạo từ JDK cũ vẫn có thể dùng charset khác và không thể được sửa chỉ bằng cách đổi default charset.

Con đường migration bền vững là xác định rõ charset tại mọi biên byte–text, **giải mã bằng charset nguồn đã xác minh, mã hóa đích bằng UTF-8, kiểm soát lỗi và bảo toàn bản gốc**, sau đó kiểm thử trên consumer thực tế. Khi thông tin encoding trở thành một phần của contract và quy trình vận hành, ứng dụng sẽ ít phụ thuộc vào thay đổi mặc định của JDK hơn và việc nâng cấp Java trở nên dễ dự đoán hơn.
