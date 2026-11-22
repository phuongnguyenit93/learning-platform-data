# InputStreamReader, OutputStreamWriter và API Files trong Java

## 1. Bản chất: tệp và mạng lưu byte, Java xử lý ký tự

Trong ứng dụng Java bản địa hóa, một lỗi charset có thể khiến văn bản tiếng Việt, tên người, emoji hoặc dữ liệu từ hệ thống khác trở thành ký tự thay thế `�`, dấu hỏi `?` hoặc chuỗi “mojibake” như `cafÃ©`. Muốn đọc/ghi đúng, phải nắm ranh giới giữa **byte**, **ký tự UTF-16 trong Java** và **quy tắc mã hóa**.

- `InputStream`: đọc **byte** từ nguồn như tệp, socket, bộ nhớ hoặc tài nguyên đóng gói.
- `OutputStream`: ghi **byte** ra đích.
- `Reader`: đọc **char** (đơn vị UTF-16) từ luồng văn bản.
- `Writer`: ghi **char** ra luồng văn bản.
- `Charset`: quy tắc **mã hóa** ký tự thành byte và **giải mã** byte thành ký tự.
- `InputStreamReader`: cầu nối **byte → char** thông qua `CharsetDecoder`.
- `OutputStreamWriter`: cầu nối **char → byte** thông qua `CharsetEncoder`.
- `java.nio.file.Files`: cung cấp API mức cao để đọc/ghi tệp trực tiếp bằng byte, text, reader/writer, line stream và nhiều thao tác filesystem.

**Nguyên tắc cốt lõi:** không có khái niệm “một tệp tự động là tiếng Việt hay tiếng Anh”. Tệp là chuỗi byte; chỉ khi biết đúng charset, chương trình mới giải mã các byte thành văn bản đúng. **Locale** phục vụ bản địa hóa, không tự quyết định byte encoding.

### 1.1. Sơ đồ hai chiều

~~~text
Đọc:
tệp / HTTP / byte[] --InputStream--> byte
     --CharsetDecoder (UTF-8 chẳng hạn)-->
  UTF-16 char trong Reader --> String / xử lý văn bản

Ghi:
String / UTF-16 char --Writer-->
    CharsetEncoder (UTF-8 chẳng hạn)
     --OutputStream--> byte --> tệp / HTTP / bộ nhớ
~~~

Nếu bộ mã **đọc** không khớp bộ mã **đã ghi**, văn bản có thể sai mà chương trình không luôn ném exception. Chẳng hạn chuỗi UTF-8 bị giải mã nhầm theo một charset 8 bit khác có thể trở thành ký tự kỳ lạ nhưng vẫn “hợp lệ” đối với decoder đó.

### 1.2. Đừng nhầm byte, char, code point và grapheme

Trong Java, `char` là đơn vị mã UTF-16. Một Unicode code point ngoài BMP, ví dụ emoji `U+1F603`, chiếm **hai `char`** trong một `String`, nhưng có thể chiếm **bốn byte** khi được mã hóa UTF-8.

Ví dụ một chuỗi gồm chữ ASCII `Cafe`, dấu sắc tổ hợp `U+0301`, hai chữ Hán và emoji:

~~~java
String text = "Cafe\u0301 | \u4F60\u597D | \uD83D\uDE03";
~~~

Đây là câu lệnh minh họa trong một phương thức Java. Chuỗi có **15 UTF-16 code units**, **14 code points** và khi mã hóa UTF-8 sẽ thành **22 byte**. Không dùng `text.length()` để suy ra kích thước tệp UTF-8 hoặc số ký tự nhìn thấy.

## 2. InputStreamReader: giải mã byte thành văn bản

Dùng `InputStreamReader` khi đã có một nguồn **InputStream** và muốn xử lý thành ký tự. Tạo bằng charset tường minh:

~~~java
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;

try (InputStream stream = /* nguồn byte hợp lệ */ null;
     Reader reader = new InputStreamReader(stream, StandardCharsets.UTF_8)) {
    // Đọc các char từ reader.
}
~~~

**Đoạn trên chỉ minh họa cấu trúc**, chưa runnable do placeholder nguồn `null`. Trong mã thật, thay bằng `Files.newInputStream(path)`, một `ByteArrayInputStream` hoặc luồng hợp lệ; có ví dụ độc lập hoàn chỉnh ở mục 8.

Với một `InputStream` đã tồn tại, cách viết ngắn hơn:

~~~java
try (Reader reader =
        new InputStreamReader(source, StandardCharsets.UTF_8)) {
    char[] buffer = new char[4096];
    int n;
    while ((n = reader.read(buffer)) != -1) {
        // Chỉ xử lý buffer[0..n), không phải toàn bộ buffer.
    }
}
~~~

`source` ở đoạn minh họa là `InputStream` hợp lệ được quản lý bởi scope này. **Một lần `read` không đảm bảo lấy toàn bộ nội dung**. Nó trả số `char` thực đọc được, hoặc `-1` khi hết dữ liệu. Duyệt buffer theo `n`, không dùng `buffer.length` làm số ký tự mới.

### 2.1. Charset tường minh so với mặc định

Có nhiều constructor:

| Constructor | Charset dùng | Hệ quả |
| --- | --- | --- |
| `new InputStreamReader(in)` | `Charset.defaultCharset()` | Phụ thuộc cấu hình/môi trường runtime |
| `new InputStreamReader(in, StandardCharsets.UTF_8)` | UTF-8 | Rõ ràng, dễ kiểm thử và tương thích |
| `new InputStreamReader(in, "UTF-8")` | Theo tên charset | Có thể ném `UnsupportedEncodingException` nếu tên không được hỗ trợ |
| `new InputStreamReader(in, decoder)` | Theo `CharsetDecoder` tùy chỉnh | Điều khiển xử lý byte sai/không ánh xạ |

Trên Java 17, **không** dựa vào default charset của máy phát triển hoặc container. Java 18 trở lên thay đổi mặc định theo JEP 400 trong đa số tình huống, nhưng điều này không khiến byte của một tệp legacy tự biến thành UTF-8. Đối với giao thức/tệp xác định encoding, luôn truyền charset trực tiếp.

`StandardCharsets.UTF_8`, `US_ASCII`, `ISO_8859_1`, `UTF_16`, `UTF_16BE`, `UTF_16LE` là các hằng có sẵn. **Không** suy charset từ ngôn ngữ nội dung: một văn bản tiếng Việt có thể được lưu UTF-8, UTF-16 hoặc charset cũ tùy nguồn.

### 2.2. Bộ đệm và ngắt luồng

`InputStreamReader` có thể đọc trước nhiều byte hơn số `char` cần để trả về trong lần `read()` hiện tại, vì một ký tự có thể trải qua nhiều byte. Không phối hợp đọc byte trực tiếp từ cùng một underlying stream trong lúc `InputStreamReader` đang giải mã, vì bộ giải mã đã có thể đọc trước dữ liệu.

Nếu đọc từng dòng, bọc bằng `BufferedReader`:

~~~java
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(source, StandardCharsets.UTF_8))) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý từng dòng.
    }
}
~~~

Đây là snippet cần import `java.io.BufferedReader`. `readLine()` **bỏ ký tự kết thúc dòng**; nếu cần giữ nguyên `CRLF`, `LF`, `CR` hoặc chuỗi gốc từng byte, dùng phương thức khác. Một “dòng” cực dài vẫn có thể tiêu thụ nhiều bộ nhớ, dù `BufferedReader` được dùng.

**Lưu ý đóng tài nguyên:** đóng reader bọc ngoài thường sẽ đóng các lớp reader/stream phía dưới. Dùng try-with-resources để tự động đóng ngay cả khi có lỗi. Nếu underlying stream do framework sở hữu (ví dụ `System.in` hoặc HTTP response do caller quản lý), cần thống nhất ai chịu trách nhiệm đóng; tránh đóng `System.in` ngoài dự kiến.

### 2.3. ready không phải tín hiệu EOF

`Reader.ready()` chỉ cho biết một lần đọc kế tiếp được bảo đảm không block trong ngữ cảnh cụ thể; `false` **không đồng nghĩa đã hết dữ liệu**. Cần đọc cho đến khi `read()` trả `-1`, hoặc `readLine()` trả `null`.

## 3. OutputStreamWriter: mã hóa ký tự thành byte

Dùng `OutputStreamWriter` khi đã có `OutputStream` và cần viết text theo charset cụ thể:

~~~java
try (Writer writer = new OutputStreamWriter(
        destination, StandardCharsets.UTF_8)) {
    writer.write("Xin chào");
}
~~~

Đây là đoạn minh họa trong phương thức, với `destination` là `OutputStream` hợp lệ và import `java.io.Writer`, `java.io.OutputStreamWriter`. Writer **mã hóa UTF-16 char thành byte UTF-8**. Nó không tự chọn ngôn ngữ, không biên dịch resource bundle và không chuyển line ending theo locale.

### 3.1. Vì sao flush/close quan trọng?

`OutputStreamWriter` có bộ đệm byte nội bộ. Nếu chương trình đã gọi `write` nhưng chưa `flush` hoặc `close`, chưa chắc mọi byte đã được chuyển xuống underlying stream. `close()` cũng thực hiện flush trước khi đóng.

~~~java
writer.write(text);
writer.flush();
~~~

Đoạn này là minh họa có biến `writer`, `text`. Với try-with-resources, `close` được gọi tự động; chỉ cần `flush` sớm khi phải làm dữ liệu hiển thị/chuyển tiếp **trước khi** block kết thúc, ví dụ giao thức streaming.

**Đừng hiểu flush = dữ liệu được lưu bền vững lên ổ đĩa.** Flush của Writer đẩy buffer mã hóa xuống stream; yêu cầu durability (fsync/force, atomic replace và quy tắc ghi file) là vấn đề I/O/transaction riêng.

Nếu có nhiều lần `write` nhỏ, có thể dùng `BufferedWriter` bọc ngoài để gom các thao tác ký tự:

~~~java
try (BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(destination, StandardCharsets.UTF_8))) {
    writer.write("dòng một");
    writer.newLine();
    writer.write("dòng hai");
}
~~~

Đây là snippet cần import `java.io.BufferedWriter`; `newLine()` viết **line separator của platform**. Nếu file hoặc giao thức yêu cầu chính xác `\\n` (LF), hãy ghi `writer.write('\\n')` theo contract thay vì trông cậy vào `newLine()`.

### 3.2. UTF-8 không phải “mỗi char là một byte”

Hàm viết:

~~~java
String s = "Cafe\u0301";
byte[] encoded = s.getBytes(StandardCharsets.UTF_8);
~~~

cho kết quả 5 UTF-16 units nhưng 6 byte UTF-8, do dấu tổ hợp `U+0301` chiếm hai byte. Với emoji supplementary, cặp surrogate được encoder ghép thành bốn byte. Cần đo `encoded.length` khi giao thức giới hạn **byte**, và `s.length()` khi API giới hạn **UTF-16 units**.

## 4. Luồng byte và luồng ký tự: chọn đúng lớp

| Tình huống | API thích hợp | Vì sao |
| --- | --- | --- |
| Đọc PNG, PDF, ZIP, dữ liệu mã hóa, byte giao thức | `InputStream`, `Files.readAllBytes` cho file nhỏ | Dữ liệu **nhị phân**, không giải mã thành text |
| Đọc tệp UTF-8 nhỏ, cần nguyên text | `Files.readString(path, UTF_8)` | Đơn giản, charset rõ ràng |
| Đọc nhiều dòng trong tệp lớn | `Files.newBufferedReader(path, UTF_8)` | Duyệt từng dòng, không cần giữ cả file |
| Nhận text qua socket hoặc ByteArrayInputStream | `InputStreamReader(in, UTF_8)` | Chuyển byte vào Reader |
| Ghi chuỗi text ra tệp nhỏ | `Files.writeString(path, text, UTF_8)` | Đơn giản, đóng file tự động |
| Ghi text lớn hoặc ghi theo dòng | `Files.newBufferedWriter(path, UTF_8)` | Ghi từng đoạn, quản lý buffer |
| Ghi text vào HTTP/socket/byte[] | `OutputStreamWriter(out, UTF_8)` | Chuyển char thành byte |
| Xử lý sai encoding cần phân biệt reject/replace | `CharsetDecoder`/`CharsetEncoder` | Cấu hình `CodingErrorAction` |

**Không bao giờ** chuyển arbitrary binary bytes qua `new String(bytes, UTF_8)` rồi `getBytes(UTF_8)` để “giữ nguyên” file nhị phân: byte không phải UTF-8 hợp lệ có thể bị thay thế, làm dữ liệu mất mát. Dùng API byte khi dữ liệu không phải text.

## 5. API Files: mức cao và có charset rõ ràng

`java.nio.file.Files` làm việc với `Path` và cung cấp cả API text và API bytes. Các ví dụ dưới đây là **đoạn minh họa trong phương thức có `throws IOException` hoặc xử lý ngoại lệ**, trừ chương trình hoàn chỉnh ở mục 8.

### 5.1. readString/writeString (Java 11+)

~~~java
Path file = Path.of("message.txt");
Files.writeString(file, text, StandardCharsets.UTF_8);
String restored = Files.readString(file, StandardCharsets.UTF_8);
~~~

`Files.writeString(path, text, charset)` ghi **chính xác chuỗi ký tự được cung cấp**, không tự thêm ký tự xuống dòng. Nếu không truyền `OpenOption`, phương thức mặc định mở để **CREATE**, **TRUNCATE_EXISTING**, **WRITE**: file mới được tạo, file đã tồn tại bị ghi đè (xóa nội dung cũ trước khi viết). Đừng dùng mẫu này trên tệp quan trọng mà không có chiến lược sao lưu hoặc ghi an toàn.

`Files.readString(path, charset)` đọc cả file thành một `String` và giữ những ký tự xuống dòng theo dữ liệu nguồn. Nó **không phải** bộ đọc cho file quá lớn; có thể tốn RAM hoặc gây `OutOfMemoryError`.

Trong Java 17:

- `Files.readString(path)` **mặc định UTF-8**.
- `Files.writeString(path, text)` **mặc định UTF-8**.

Điều này khác với việc gọi `new InputStreamReader(in)` **không truyền charset**, vốn dùng default charset của runtime. Đừng gom các API ấy vào một phát biểu chung rằng “tất cả Java I/O mặc định UTF-8” trên Java 17.

### 5.2. newBufferedReader/newBufferedWriter

~~~java
Path path = Path.of("lines.txt");

try (BufferedWriter writer =
        Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("first");
    writer.newLine();
    writer.write("second");
}

try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
~~~

Đoạn này có thể nằm trong phương thức `throws IOException`; yêu cầu import `java.nio.file.Files`, `Path`, `StandardCharsets`, `BufferedWriter`, `BufferedReader`. Nếu không truyền options, `newBufferedWriter` cũng mở theo **CREATE**, **TRUNCATE_EXISTING**, **WRITE**.

Mặc định các overload **không nhận Charset** của `Files.newBufferedReader` và `Files.newBufferedWriter` là UTF-8 trong Java 17. Dù vậy, với mã cần contract tường minh, truyền `StandardCharsets.UTF_8` giúp người đọc không phải nhớ sự khác nhau giữa các nhóm API.

`newBufferedReader` làm việc theo dòng. Nó trả dữ liệu văn bản đã giải mã và có thể ném `IOException` khi gặp byte sai charset; đừng dùng để giữ nguyên byte hoặc line separators.

### 5.3. Files.lines và readAllLines

~~~java
try (java.util.stream.Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.filter(s -> !s.isBlank()).count();
    System.out.println(count);
}
~~~

Đây là snippet, biến `path` đã được khai báo. `Files.lines` trả **Stream đọc trễ** còn giữ file đang mở. **Phải đóng stream** bằng try-with-resources. Ngoại lệ I/O khi xử lý stream sau lúc mở có thể được bọc thành `UncheckedIOException`, khác với ngoại lệ ở bước mở file.

`Files.readAllLines(path, UTF_8)` trả `List<String>`, tiện cho file nhỏ nhưng đọc toàn bộ các dòng vào bộ nhớ; các dấu kết thúc dòng không còn là phần của từng string. Khi cần nguyên văn file và file vừa phải, `readString` hợp hơn; khi cần xử lý dòng lớn/streaming, dùng `newBufferedReader` hoặc `lines`.

### 5.4. Files.readAllBytes và Files.write

~~~java
byte[] raw = Files.readAllBytes(path);
Files.write(path, raw);
~~~

Các lệnh này thao tác **byte** chứ không giải mã text. Nếu bạn cần kiểm tra header, BOM, signature, dữ liệu nhị phân hoặc so raw bytes trước/sau, đây là công cụ phù hợp cho **file nhỏ**. `readAllBytes` không nên dùng cho file cực lớn; để streaming, dùng `Files.newInputStream` hoặc các channel.

## 6. Lỗi charset: replacement khác REPORT

Một điểm dễ bị bỏ qua: các API có thể áp dụng **chính sách xử lý byte/ký tự sai** khác nhau. Hai loại lỗi phổ biến:

- **Malformed input:** chuỗi byte không hợp lệ theo charset, ví dụ `C3 28` không phải một UTF-8 sequence đúng.
- **Unmappable character:** ký tự hoặc byte không có biểu diễn phù hợp trong charset đích/nguồn.

Các lựa chọn `CodingErrorAction`:

| Chế độ | Nghĩa | Hệ quả |
| --- | --- | --- |
| `REPORT` | Báo lỗi thay vì lặng lẽ sửa | Có thể ném `MalformedInputException` hoặc `UnmappableCharacterException` |
| `REPLACE` | Thay đoạn lỗi bằng replacement | Dữ liệu **không còn giữ nguyên** |
| `IGNORE` | Bỏ qua đoạn lỗi | Có thể **mất dữ liệu âm thầm** |

### 6.1. InputStreamReader(InputStream, Charset) và replacement

Khi tạo trực tiếp từ `Charset`, `InputStreamReader` thay input byte sai bằng ký tự thay thế mặc định cho decoder trong trường hợp đã kiểm tra. Điều này thuận tiện khi đọc văn bản để hiển thị nhưng **không thích hợp khi dữ liệu lỗi phải bị từ chối**.

Ví dụ có hai byte:

~~~text
C3 28
~~~

Byte đầu `C3` báo bắt đầu một UTF-8 sequence nhiều byte, nhưng `28` không phải continuation byte phù hợp. Đọc với `InputStreamReader(..., StandardCharsets.UTF_8)` trong ví dụ hoàn chỉnh có ký tự đầu **U+FFFD** (replacement), còn `(` tiếp tục được đọc.

Nếu ứng dụng xử lý tài liệu cần chính xác hoặc kiểm toán, thay thế im lặng có thể nguy hiểm: bạn không còn biết chính xác byte gốc từ chuỗi đã giải mã. Cần validate đầu vào bằng decoder nghiêm ngặt hoặc giữ lại byte gốc để phân tích.

### 6.2. CharsetDecoder cấu hình REPORT

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Reader reader = new InputStreamReader(source, decoder)) {
    // Đọc, lỗi decoding sẽ được báo.
}
~~~

Đây là đoạn minh họa có `source` là `InputStream` hợp lệ; import `java.nio.charset.CharsetDecoder`, `CodingErrorAction`. Với input `C3 28`, việc đọc phát sinh `MalformedInputException` thay vì hoàn thành với replacement.

**Tránh dùng chung `CharsetDecoder` mutable giữa các thread:** decoder giữ trạng thái mã hóa/giải mã; tạo mới theo reader hoặc quản lý rõ concurrency.

### 6.3. Files.readString nghiêm ngặt hơn trường hợp trên

Theo API Java 17, `Files.readString(path, charset)` báo `IOException` khi gặp byte **malformed hoặc unmappable**. Trong ví dụ được kiểm chứng, đọc file chứa `C3 28` bằng `Files.readString(..., UTF_8)` ném `MalformedInputException` và được ghi là `Files malformed=REJECTED`.

Vì vậy hai đoạn:

~~~java
new InputStreamReader(source, StandardCharsets.UTF_8)
Files.readString(path, StandardCharsets.UTF_8)
~~~

**không nên được quảng bá là có cùng chính sách lỗi byte**. Cả hai đều dùng UTF-8 nhưng khác API và cách xử lý malformed mặc định. Nếu yêu cầu reject toàn bộ byte UTF-8 không hợp lệ, chọn API có hợp đồng phù hợp hoặc decoder `REPORT`.

### 6.4. OutputStreamWriter và CharsetEncoder

`OutputStreamWriter` với `Charset` có thể thay ký tự malformed/unmappable bằng byte substitution của charset. Nếu bắt buộc ghi không mất dữ liệu, dùng `CharsetEncoder` với `REPORT`:

~~~java
CharsetEncoder encoder = StandardCharsets.UTF_8.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Writer writer = new OutputStreamWriter(destination, encoder)) {
    writer.write(text);
}
~~~

Đây là snippet minh họa có `destination` là `OutputStream` hợp lệ và `text` là `String`. Trường hợp malformed surrogate pair trong nguồn hoặc dùng charset không có khả năng mã hóa một ký tự cần được báo và xử lý; không biến lỗi thành dấu `?` mà không có chủ ý.

**Không đồng nhất thao tác `new String(bytes, UTF_8)` với xác thực byte UTF-8 nghiêm ngặt**. Với constructor dạng charset, dữ liệu lỗi có thể được thay thế; nếu cần reject, dùng decoder `REPORT` hoặc API đã bảo đảm báo lỗi.

## 7. BOM, legacy encodings và line endings

### 7.1. BOM là dữ liệu byte ở đầu, không phải ngôn ngữ

UTF-8 BOM thường là dãy **EF BB BF**. UTF-8 không bắt buộc có BOM, và nhiều file UTF-8 hoàn toàn không có BOM. BOM có thể xuất hiện do hệ thống xuất tệp.

- Đừng giả định **mọi** tệp UTF-8 đều có BOM.
- Đừng tự loại ba byte đầu nếu không xác định chúng thật sự là `EF BB BF`.
- Khi đã decode sang `String`, một BOM UTF-8 có thể xuất hiện như ký tự `U+FEFF` ở đầu nếu API không tự loại bỏ; kiểm thử hành vi của API/file pipeline mục tiêu.
- Một số giao thức hoặc nội dung CSV/JSON có chính sách BOM riêng. Hãy tuân theo contract, không “đoán” từ locale.

Với UTF-16, các biến thể `UTF_16`, `UTF_16BE` và `UTF_16LE` khác nhau về cách dùng BOM và endian. Không xem UTF-16LE bytes là UTF-8 rồi chờ reader tự nhận diện chính xác.

### 7.2. Mã hóa cũ không tự chuyển thành UTF-8

Nếu đối tác gửi tệp theo Windows-1252, ISO-8859-1 hoặc charset cũ, bạn phải biết encoding thật (thông số kỹ thuật, HTTP headers đáng tin cậy, file metadata/hợp đồng nguồn) mới decode chính xác.

Ví dụ minh họa:

~~~java
Charset legacy = Charset.forName("windows-1252");
String value = Files.readString(path, legacy);
Files.writeString(output, value, StandardCharsets.UTF_8);
~~~

Đoạn này chỉ chạy khi **file đầu vào thật sự có charset đã định**; cần import `Charset`, `Files`, `Path`/các biến. Chuyển đổi encoding đúng là **decode theo charset nguồn rồi encode theo charset đích**. Nếu bước decode dùng sai charset, ghi ra UTF-8 chỉ làm dữ liệu sai được bảo quản ở một mã hóa mới.

### 7.3. Line endings

Ba kiểu phổ biến:

- LF: `\\n`.
- CRLF: `\\r\\n`.
- CR: `\\r`.

`Files.readString` giữ các ký tự line ending thực tế đã decode. `BufferedReader.readLine()` bỏ line terminators; `BufferedWriter.newLine()` dùng line separator của nền tảng. Nếu chuyển file giữa Windows và Linux mà cần bảo toàn **byte hoặc line ending chính xác**, đừng đọc theo line rồi viết `newLine()` mà không có chính sách đổi dòng.

## 8. Chương trình Java 17 hoàn chỉnh: UTF-8 round-trip và decoder lỗi

File **`CharsetFilesDemo.java`** sau có thể biên dịch/chạy trên Java 17+. Nó tạo hai file tạm bằng `Files.createTempFile` và xóa trong `finally`; không phụ thuộc file bên ngoài hoặc default charset của máy chạy. Đầu vào dùng Unicode escapes để terminal không cần nhập emoji.

~~~java
import java.io.*;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.HexFormat;

public class CharsetFilesDemo {
    static String readAll(Reader reader) throws IOException {
        StringBuilder text = new StringBuilder();
        char[] buffer = new char[4];
        int count;
        while ((count = reader.read(buffer)) != -1) {
            text.append(buffer, 0, count);
        }
        return text.toString();
    }

    public static void main(String[] args) throws IOException {
        String original = "Cafe\u0301 | \u4F60\u597D | \uD83D\uDE03";
        ByteArrayOutputStream output = new ByteArrayOutputStream();

        try (Writer writer = new OutputStreamWriter(
                output, StandardCharsets.UTF_8)) {
            writer.write(original);
        }
        byte[] bytes = output.toByteArray();
        System.out.println("encoded bytes=" + bytes.length);
        System.out.println("encoded hex=" +
                HexFormat.of().formatHex(bytes));

        String decoded;
        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(bytes),
                StandardCharsets.UTF_8)) {
            decoded = readAll(reader);
        }
        System.out.println("stream roundtrip=" +
                original.equals(decoded));

        Path file = Files.createTempFile(
                "charset-files-demo-", ".txt");
        Path invalidFile = Files.createTempFile(
                "charset-invalid-", ".bin");
        try {
            Files.writeString(file, original,
                    StandardCharsets.UTF_8);
            System.out.println("Files roundtrip=" +
                    original.equals(Files.readString(
                            file, StandardCharsets.UTF_8)));
            System.out.println("Files size=" + Files.size(file));

            byte[] invalid = {(byte) 0xC3, (byte) 0x28};
            String replacement;
            try (Reader reader = new InputStreamReader(
                    new ByteArrayInputStream(invalid),
                    StandardCharsets.UTF_8)) {
                replacement = readAll(reader);
            }
            System.out.println("default replacement=" +
                    (replacement.codePointAt(0) == 0xFFFD));

            CharsetDecoder strict =
                    StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT);
            try (Reader reader = new InputStreamReader(
                    new ByteArrayInputStream(invalid), strict)) {
                readAll(reader);
                System.out.println("strict decoder=ACCEPTED");
            } catch (MalformedInputException ex) {
                System.out.println("strict decoder=REJECTED");
            }

            Files.write(invalidFile, invalid);
            try {
                Files.readString(invalidFile,
                        StandardCharsets.UTF_8);
                System.out.println("Files malformed=ACCEPTED");
            } catch (MalformedInputException ex) {
                System.out.println("Files malformed=REJECTED");
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(invalidFile);
        }
    }
}
~~~

Biên dịch và chạy (yêu cầu JDK 17+ do có `HexFormat`):

~~~bash
javac -encoding UTF-8 CharsetFilesDemo.java
java CharsetFilesDemo
~~~

**Stdout đã kiểm tra** trên Java:

~~~text
encoded bytes=22
encoded hex=43616665cc81207c20e4bda0e5a5bd207c20f09f9883
stream roundtrip=true
Files roundtrip=true
Files size=22
default replacement=true
strict decoder=REJECTED
Files malformed=REJECTED
~~~

Giải thích:

1. `Cafe` dùng 4 byte ASCII; `U+0301` dùng 2 byte UTF-8, các dấu cách/`|` thêm 6 byte; hai chữ Hán dùng 6 byte và emoji `U+1F603` dùng 4 byte. Tổng `4 + 2 + 6 + 6 + 4 = 22`.
2. `encoded hex` là đúng 22 byte vừa được `OutputStreamWriter` ghi vào `ByteArrayOutputStream`, không phụ thuộc console charset.
3. `InputStreamReader` giải mã các byte hợp lệ theo UTF-8, nên `stream roundtrip=true`.
4. `Files.writeString` và `Files.readString` cũng bảo toàn Unicode hợp lệ; `Files.size(file)` đo **byte** trên tệp.
5. Với byte UTF-8 sai `C3 28`, decoder mặc định của `InputStreamReader(InputStream, Charset)` sử dụng replacement, nên ký tự đầu là `U+FFFD`.
6. Khi dùng `CharsetDecoder` với `REPORT`, lỗi được báo bằng `MalformedInputException`.
7. `Files.readString(invalidFile, UTF_8)` cũng từ chối file malformed và ném `MalformedInputException` trong chương trình này.
8. Hai file tạm được xóa sau khi kiểm tra; trong ứng dụng thật, xử lý lỗi cần cân nhắc cả trường hợp ghi/xóa file không thành công.

Không sao chép các giá trị hex để khẳng định tất cả văn bản Unicode có độ dài này; đây là kết quả **của đúng chuỗi mẫu**. Mọi phép đo byte phải dựa trên bytes thực sự encode và charset được chọn.

## 9. Chọn API theo quy mô và vòng đời tài nguyên

| Yêu cầu | Cách thường thích hợp | Ràng buộc |
| --- | --- | --- |
| File cấu hình/README nhỏ, UTF-8 | `Files.readString` | Toàn bộ file lên RAM |
| File báo cáo nhỏ | `Files.writeString` | Chú ý ghi đè mặc định |
| File log/csv nhiều dòng | `newBufferedReader` hoặc `Files.lines` | Đóng tài nguyên, hạn chế dòng cực dài |
| Text được sinh dần | `newBufferedWriter` | Chốt charset, line ending, options |
| Network InputStream | `InputStreamReader` | Đúng charset theo contract HTTP/protocol |
| Network OutputStream | `OutputStreamWriter` | Flush/cấp phát charset encoder đúng |
| Byte chính xác để checksum/signature | `Files.newInputStream` hoặc `readAllBytes` | Không chuyển sang text khi không cần |
| File lớn không thể đọc hết RAM | Buffered/streaming I/O | Giới hạn input size, không gom vào `StringBuilder` khổng lồ |
| Dữ liệu có thể malformed | Strict decoder hoặc Files text API có báo lỗi | Tránh thay thế âm thầm nếu cần audit |

Với file nhỏ, ít boilerplate thường quan trọng hơn performance. Với file nhiều GB, **đọc hết vào một `String`** không thực tế và có thể tạo nhiều bản sao ở bộ nhớ. Nên xử lý tuần tự theo buffer hoặc dòng và giới hạn tài nguyên.

### 9.1. Chỉ định OpenOption rõ khi cần

`Files.writeString` hoặc `Files.newBufferedWriter` **mặc định truncate file đã có** nếu không chỉ định options. Khi muốn nối thêm:

~~~java
Files.writeString(path, "more text",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND);
~~~

Đây là snippet cần import `StandardOpenOption` và các biến. Nếu định nối text bằng APPEND, phải bảo đảm file đã có **cùng charset**, không nối UTF-8 vào file legacy đang dùng encoding khác. Nếu muốn không bao giờ ghi đè, cân nhắc `CREATE_NEW` và xử lý `FileAlreadyExistsException`.

Một thao tác write không tự bảo đảm **atomic replace** hay tính nhất quán trong trường hợp process crash. Nếu ghi file cấu hình quan trọng, thường cần tệp tạm cùng filesystem và chiến lược thay thế an toàn theo `Files.move`, xem xét `ATOMIC_MOVE` khi provider hỗ trợ. Không nhầm việc đóng stream với giao dịch file nguyên tử.

### 9.2. Files.lines phải đóng

Đừng viết:

~~~java
long n = Files.lines(path).count();
~~~

rồi bỏ quên stream như thể nó là collection trong RAM. `Files.lines` giữ file mở; hãy dùng:

~~~java
try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
    long n = lines.count();
}
~~~

Hai snippet là minh họa trong phương thức xử lý `IOException`; đoạn đầu là **cách không khuyến khích** vì thiếu đóng. Với file được ghi đồng thời trong lúc stream đang đọc, kết quả có thể không xác định theo hợp đồng API.

## 10. Lỗi thực tế và cách khắc phục

| Lỗi | Hiện tượng | Cách xử lý |
| --- | --- | --- |
| Đọc UTF-8 bằng charset không đúng | Mojibake, chữ tiếng Việt lỗi | Xác định charset nguồn, decode đúng |
| Dùng `new InputStreamReader(in)` trên Java 17 | Phụ thuộc default charset runtime | Truyền `StandardCharsets.UTF_8` |
| Tưởng `Files.readString` luôn giống `InputStreamReader` | Khác chính sách malformed input | Đọc hợp đồng API, dùng decoder REPORT khi cần |
| Dùng `new String(bytes)` không charset | Phụ thuộc default charset | `new String(bytes, charset)` khi chỉ cần decode nhanh |
| Dùng `OutputStreamWriter` không flush/close | Byte còn trong buffer, thiếu dữ liệu | try-with-resources, flush đúng lúc |
| Trộn đọc byte trực tiếp với Reader cùng stream | Reader có thể read-ahead | Dùng một tầng I/O nhất quán |
| Dùng `available()` hoặc `ready()` làm điều kiện kết thúc | Đọc thiếu nội dung | Đọc đến `-1` hoặc `null` |
| Dùng `Files.writeString` lên file có sẵn không kiểm tra | File bị truncate | Chọn `CREATE_NEW`, APPEND hoặc quy trình replace |
| `readLine()` rồi `newLine()` để copy nguyên file | Line endings đổi, có thể thêm/bớt newline | Dùng byte copy hoặc `readString/writeString` khi phù hợp |
| Dùng `String.length()` như số byte UTF-8 | Sai với Unicode ngoài ASCII | Đo `getBytes(UTF_8).length` hoặc file size |
| Không xử lý malformed/unmappable | Dữ liệu thay thế/mất âm thầm | Đặt chính sách REPORT/REPLACE có kiểm soát |
| Dùng `Files.readString` với file rất lớn | RAM cao hoặc OOME | Streaming Reader/Files.lines |
| Quên đóng `Files.lines` | File descriptor/handle rò rỉ | try-with-resources |
| Dùng reader text cho file nhị phân | Byte thay đổi hoặc lỗi decode | InputStream/OutputStream, byte APIs |
| Chuyển charset mà bỏ qua BOM/line ending | File không tương thích downstream | Xác định contract BOM/newline |
| Cho phép path do người dùng tự chỉ định vô điều kiện | Path traversal / ghi đè file ngoài phạm vi | Kiểm tra quyền, đường dẫn và giới hạn |

### 10.1. An toàn dữ liệu không chỉ là đúng charset

Khi nhận tệp từ người dùng hoặc hệ thống bên ngoài:

- Giới hạn kích thước tệp, số dòng và độ dài tối đa của mỗi dòng.
- Không dùng tên tệp/path chưa kiểm soát để truy cập tùy ý ngoài thư mục cho phép; cân nhắc symlink, race và quyền file.
- Kiểm tra encoding theo hợp đồng đã công bố, không tự đoán từ `Locale`.
- Quyết định rõ **reject hoặc replace** khi input sai charset; với hóa đơn, chữ ký, dữ liệu kế toán hoặc dữ liệu cần audit, thay thế âm thầm thường không phù hợp.
- Nếu nội dung được render thành HTML, còn phải escape HTML để tránh injection; đọc đúng UTF-8 **không** đồng nghĩa nội dung an toàn để đưa vào markup.
- Với text quốc tế, normalization Unicode, xử lý ký tự vô hình, grapheme và so sánh locale là vấn đề riêng, không được giải quyết chỉ bằng charset.

## 11. Kiểm thử cần có

Một module I/O/charset đáng tin nên kiểm thử:

1. **ASCII:** cùng nội dung qua reader/writer UTF-8, số byte khớp.
2. **Tiếng Việt có dấu:** ký tự dựng sẵn và dạng dấu tổ hợp `U+0301`, bảo toàn code point gốc.
3. **Unicode ngoài BMP:** emoji `U+1F603`, kiểm tra hai UTF-16 `char` được encode/decode đúng.
4. **Hán tự/RTL:** các script khác nhau không làm đổi charset hay mất chữ.
5. **Byte malformed:** `C3 28`, đối chiếu REPLACE với REPORT.
6. **Ký tự unmappable:** thử encode một ký tự Unicode ngoài phạm vi US-ASCII với `CharsetEncoder` báo lỗi.
7. **Mismatched charset:** cố ý đọc UTF-8 bằng charset khác để nhận diện mojibake; không gọi đó là Unicode normalization.
8. **BOM:** file UTF-8 có/không có `EF BB BF`; xác minh chính sách consumer.
9. **Newline:** LF, CRLF, CR, file cuối có/không có newline; so `readLine` và `readString`.
10. **OpenOption:** file có sẵn bị truncate mặc định; `APPEND` và `CREATE_NEW` cần hành vi đã định.
11. **Close/flush:** Writer được đóng/flush trước khi kiểm tra bytes, Files.lines luôn đóng stream.
12. **Large files:** streaming theo buffer/dòng mà không giữ toàn bộ trong RAM; kiểm tra dòng cực dài.
13. **Permission/IO failure:** file không tồn tại, không được truy cập, hết dung lượng ổ, lỗi ghi một phần.
14. **Portability:** chạy trên JDK 17+ với charset được truyền tường minh; không phụ thuộc default locale/charset của OS.
15. **File chính xác:** so raw bytes, file size và hash khi contract yêu cầu bảo toàn byte; so `String.equals` khi contract yêu cầu bảo toàn text.

### Bài tập 1 — cùng chuỗi, khác đơn vị độ dài

Đo `length()`, `codePointCount` và `getBytes(UTF_8).length` cho chuỗi mẫu. Giải thích tại sao số byte là 22 dù số `char` là 15 và số code point là 14.

### Bài tập 2 — so sánh API mặc định

Đọc tài liệu Java SE 17 rồi giải thích sự khác biệt giữa `new InputStreamReader(in)` và `Files.readString(path)` về **charset mặc định**. Dùng `Charset.defaultCharset()` để quan sát môi trường đang chạy, nhưng không dùng thông tin đó như giao thức của file UTF-8.

### Bài tập 3 — malformed input

Với byte `C3 28`, thử `InputStreamReader` dùng UTF-8 Charset, một decoder REPORT và `Files.readString`. Giải thích trường hợp nào có ký tự thay thế, trường hợp nào ném lỗi.

### Bài tập 4 — chuyển đổi encoding có kiểm soát

Giả sử file nguồn thực sự dùng `windows-1252`. Viết chương trình đọc bằng charset nguồn, rồi ghi UTF-8; xác minh text sau round-trip bằng sample có ký tự nằm ngoài ASCII. Không được suy charset từ ngôn ngữ.

### Bài tập 5 — tệp nhiều dòng

Dùng `Files.newBufferedWriter` ghi hai dòng có Unicode, đọc lại bằng `Files.newBufferedReader`, sau đó so `Files.readString` để tìm hiểu vì sao một API giữ line endings và API kia bỏ chúng trong kết quả dòng.

## 12. Tổng kết

`InputStreamReader` và `OutputStreamWriter` là **hai cầu nối giữa byte streams và character streams**. Luôn chọn `Charset` theo nguồn và đích thật, thường là `StandardCharsets.UTF_8` với giao thức hiện đại; đừng để default charset của Java 17 hoặc thiết lập locale quyết định dữ liệu vô tình.

`Files` cung cấp API tiện lợi: `readString/writeString` cho file nhỏ, `newBufferedReader/newBufferedWriter` hoặc `lines` cho xử lý theo dòng và stream, `newInputStream/readAllBytes` khi cần byte. Phải kiểm soát **đóng tài nguyên**, **mở/ghi đè file**, **line endings**, **BOM** và **malformed/unmappable sequences**.

**Đúng charset chưa đủ:** một hệ thống I/O tốt còn tách byte và văn bản, quy định chấp nhận/từ chối dữ liệu lỗi, bảo toàn nội dung theo contract, kiểm thử Unicode và không phụ thuộc ngầm vào môi trường chạy.

**Tài liệu tham khảo:**

- Java SE 17, `InputStreamReader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html
- Java SE 17, `OutputStreamWriter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html
- Java SE 17, `Files`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Java SE 17, `Charset`, `CharsetDecoder`, `CharsetEncoder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/package-summary.html
- Java SE 17, `StandardCharsets`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html
- Java SE 17, `HexFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html
