# Sao chép văn bản bằng `Reader.transferTo` với bộ mã tường minh (Java 10+)

## 1. Bài toán thực hành: copy văn bản đúng ký tự, đúng bộ mã

Một ứng dụng Java cần sao chép tài liệu, log, file CSV, template hoặc nội dung cấu hình từ file nguồn sang file đích. File có thể chứa tiếng Việt, ký tự Unicode nằm ngoài BMP (ví dụ emoji), ký hiệu €, xuống dòng kiểu Windows `\r\n` hoặc kiểu Unix `\n`. Hai file có thể dùng **cùng encoding** hoặc cần **chuyển mã** từ ISO-8859-1 sang UTF-8.

Đây là bài toán **văn bản**, khác với sao chép file ở mức byte:

- Một **Reader** đọc byte từ nguồn sau khi **giải mã** thành các `char` trong Java.
- Một **Writer** nhận những `char` đó và **mã hóa** thành byte đầu ra.
- `Reader.transferTo(Writer)` nối hai luồng này để chuyển **toàn bộ phần ký tự còn lại** mà không cần tự viết vòng lặp `read`/`write`.
- **Charset phải được chọn tường minh ở cả nguồn và đích**, ví dụ `StandardCharsets.UTF_8`.
- Phải đóng Reader/Writer đúng cách, kiểm tra lỗi chuyển mã, và có chính sách rõ về việc file đích đã tồn tại.

`Reader.transferTo(Writer)` xuất hiện trong **Java 10** và **vẫn được hỗ trợ trong JDK hiện hành**. Bài dùng **Java 17+** cho các ví dụ có thể biên dịch và chạy ngay, phù hợp yêu cầu chỉ dùng kiến thức vẫn còn áp dụng.

**Mẫu cơ bản:**

```java
try (Reader in = Files.newBufferedReader(
             source, StandardCharsets.UTF_8);
     Writer out = Files.newBufferedWriter(
             target, StandardCharsets.UTF_8)) {

    long characters = in.transferTo(out);
}
```

Đoạn trên là mã **bên trong một phương thức**, cần import `Reader`, `Writer`, `Files`, `StandardCharsets` và khai báo `source`/`target` kiểu `Path`. Lệnh không tự lưu thêm tên charset vào file: hai tham số `UTF_8` quyết định cách giải mã đầu vào và mã hóa đầu ra.

**Cảnh báo:** overload `Files.newBufferedWriter` không có open options mặc định **tạo file nếu thiếu và cắt rỗng file hiện có**. Nếu ứng dụng không được phép ghi đè, phải chọn chính sách mở file an toàn như `CREATE_NEW`. Bài thực hành đầy đủ sẽ chọn `CREATE_NEW` để tránh xóa dữ liệu.

## 2. Hợp đồng chính xác của `Reader.transferTo(Writer)`

Chữ ký API:

```java
public long transferTo(Writer out) throws IOException
```

Theo Java SE 25/26 Javadoc:

1. Đọc **toàn bộ các ký tự còn lại** từ vị trí hiện tại của Reader.
2. Ghi các ký tự đó vào Writer **theo đúng thứ tự đọc được**.
3. Khi hoàn thành bình thường, Reader đi đến **cuối luồng**.
4. Trả về số lượng **`char` (đơn vị UTF-16)** đã chuyển, dưới dạng `long`.
5. **Không đóng Reader hoặc Writer**.
6. Ném `IOException` khi có lỗi đọc/ghi; ném `NullPointerException` nếu Writer bằng `null`.
7. Nếu lỗi xảy ra giữa chừng, **có thể đã chuyển một phần dữ liệu**; trạng thái luồng và file đích có thể không còn nhất quán.
8. Hoạt động có thể **block** khi đọc/ghi; hành vi trong trường hợp một luồng bị đóng bất đồng bộ hoặc thread bị interrupt phụ thuộc implementation.

**Đây không phải phép sao chép “nguyên file” theo nghĩa bất biến byte**: việc giải mã/mã hóa có thể làm byte đầu ra khác byte nguồn, nhất là khi hai charset khác nhau.

### Chuyển dữ liệu từ vị trí hiện tại

```java
try (Reader reader = new StringReader("ABCD");
     Writer writer = new StringWriter()) {

    reader.read();                      // đã tiêu thụ 'A'
    long count = reader.transferTo(writer);
    // count == 3; writer.toString().equals("BCD")
}
```

Đây là đoạn code minh họa bên trong phương thức; import `StringReader`, `StringWriter`, `Reader` và `Writer`. Nó thể hiện `transferTo` **không quay lại đầu Reader**, mà chuyển phần chưa được đọc.

### `transferTo` không tự đóng luồng

```text
Reader (đang mở)
   |
   | reader.transferTo(writer)
   v
Writer (đang mở)
   |
   +--> Sau khi chuyển xong, cả Reader và Writer
        vẫn do caller chịu trách nhiệm đóng.
```

Trong ví dụ chính, `try-with-resources` giúp đóng cả hai luồng, **kể cả khi có exception**. Đừng hiểu việc chương trình đã trả về `long` nghĩa dữ liệu Writer đã được đóng/flushed một cách an toàn. **Dùng `try-with-resources` và kiểm tra lỗi cả ở bước đóng**, nhất là với BufferedWriter hoặc encoder có thể phát hiện lỗi khi flush/close.

## 3. Vì sao phải khai báo charset cho cả Reader và Writer?

Một file chứa byte, không chứa kiểu dữ liệu Java `String`. Để làm việc với văn bản, cần hai bước:

```text
File nguồn (byte)
      |
      | Giải mã theo sourceCharset
      v
Reader -> chuỗi ký tự UTF-16 trong Java
      |
      | Reader.transferTo(Writer)
      v
Writer
      |
      | Mã hóa theo targetCharset
      v
File đích (byte)
```

Trong Java, các charset thường gặp:

| Charset | Hằng số Java | Ví dụ sử dụng |
| --- | --- | --- |
| UTF-8 | `StandardCharsets.UTF_8` | Text hiện đại có tiếng Việt, emoji, dữ liệu trao đổi |
| ISO-8859-1 | `StandardCharsets.ISO_8859_1` | Văn bản từ hệ thống dùng Latin-1 |
| US-ASCII | `StandardCharsets.US_ASCII` | Nội dung chỉ dùng ký tự ASCII |
| UTF-16 | `StandardCharsets.UTF_16` | Một số định dạng trao đổi dùng UTF-16 và BOM |
| UTF-16LE | `StandardCharsets.UTF_16LE` | Đầu ra có thứ tự byte little-endian theo hợp đồng |
| UTF-16BE | `StandardCharsets.UTF_16BE` | Đầu ra big-endian theo hợp đồng |

**Điều không đúng:** “Java tự biết file có encoding nào.” Một luồng byte **không bảo đảm** mang metadata để nhận diện charset; phần lớn API chỉ dùng charset do caller chỉ định hoặc default. Muốn copy chính xác, phải biết **format và encoding thực của nguồn** từ hợp đồng tích hợp, metadata đáng tin cậy, hoặc quy trình nhập liệu đã xác thực.

Dùng sai charset có thể gây:

- **Mojibake:** ký tự hiển thị sai dù không báo exception.
- Ký tự bị thay thế nếu API dùng chế độ xử lý lỗi `REPLACE`.
- `MalformedInputException` nếu byte sequence không hợp lệ theo charset được khai báo.
- `UnmappableCharacterException` nếu charset đích không biểu diễn được ký tự.
- File đích có nội dung khác dù thao tác sao chép “hoàn thành”.

Không xử lý vấn đề encoding bằng cách đổi `System.setProperty("file.encoding", "...")` khi chương trình đã chạy. Dùng charset **tường minh ở chính điểm đọc/ghi** sẽ rõ ràng và có thể tái lập hơn.

## 4. Lựa chọn API đọc/ghi văn bản còn hiệu lực

### `Files.newBufferedReader(Path, Charset)`

```java
Reader reader = Files.newBufferedReader(
        sourcePath, StandardCharsets.UTF_8);
```

Hàm mở file để đọc văn bản, giải mã byte theo charset chỉ định và trả `BufferedReader`. Tài liệu Oracle nói **lỗi byte không hợp lệ hoặc không thể giải mã** sẽ được báo qua `IOException` khi đọc, thay vì tự động coi toàn bộ byte là ký tự hợp lệ.

### `Files.newBufferedWriter(Path, Charset, OpenOption...)`

```java
Writer writer = Files.newBufferedWriter(
        targetPath,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE);
```

Hàm mở Writer có buffer và encoder theo charset đích. Khi không thể mã hóa ký tự, lỗi `IOException` có thể xuất hiện trong `write`, `flush` hoặc `close` do có buffering.

**Ý nghĩa các open options:**

| Open option | Tác dụng |
| --- | --- |
| `CREATE_NEW` | Chỉ tạo file mới; **thất bại nếu file đích đã tồn tại** |
| `CREATE` | Tạo file nếu chưa có; **không tự bảo vệ khỏi file đã tồn tại** |
| `TRUNCATE_EXISTING` | Cắt rỗng file có sẵn khi mở để ghi |
| `WRITE` | Cho phép ghi dữ liệu |
| `APPEND` | Thêm vào cuối file thay vì thay nội dung (không phải copy mới) |

Nếu **không truyền open options**, `Files.newBufferedWriter` mặc định tương đương `CREATE`, `TRUNCATE_EXISTING` và `WRITE` cho file thường.

Trong thực hành an toàn này, dùng **`CREATE_NEW` + `WRITE`**. Nó không cho phép ghi đè file đã tồn tại, giảm nguy cơ xóa nhầm dữ liệu. Tuy nhiên, nếu lần ghi **đã tạo file mới rồi gặp lỗi**, file mới đó vẫn có thể **chỉ chứa một phần** dữ liệu; `CREATE_NEW` không tự làm thao tác trở thành transaction.

### Tại sao chọn buffered streams?

`Reader.transferTo` truyền ký tự theo luồng; `Files.newBufferedReader/newBufferedWriter` đã thêm buffer phù hợp để giảm số thao tác I/O nhỏ. Không cần `Files.readString` tải toàn bộ nội dung vào một chuỗi lớn chỉ để copy.

**Không khẳng định buffer luôn cho throughput tốt nhất ở mọi storage hay với mọi kích cỡ file**. Thử đo khi ứng dụng xử lý file rất lớn hoặc nhiều file song song.

## 5. Mẫu mã ngắn nhất với charset tường minh

Nếu ứng dụng được phép tạo/cắt rỗng file đích, một phương thức ngắn:

```java
import java.io.IOException;
import java.nio.charset.Charset;
import java.nio.file.Files;
import java.nio.file.Path;

static long copyText(Path from, Path to, Charset cs)
        throws IOException {
    try (var reader = Files.newBufferedReader(from, cs);
         var writer = Files.newBufferedWriter(to, cs)) {
        return reader.transferTo(writer);
    }
}
```

**Phương thức trên là ví dụ đặt trong một class**. Nó minh họa bản chất `Reader.transferTo` nhưng **không có bảo vệ chống ghi đè** và cả source/destination đều dùng cùng charset.

Để dùng trong công cụ thật, cần xem xét:

- File đích có được phép tồn tại trước khi copy không?
- Input và output có thể là **cùng một file** (kể cả alias/hard link/symlink) không?
- Có cần chuyển mã giữa hai charset khác nhau không?
- Nếu đang copy mà xảy ra exception thì có chấp nhận một file đích dở dang không?
- Có cần giữ timestamp, quyền truy cập và metadata file không? `Reader.transferTo` chỉ chuyển **ký tự**, không tự copy attributes.
- File có phải là văn bản **thật** hay là binary/định dạng byte cần được giữ nguyên?

Bài mẫu đầy đủ sau xử lý rõ hơn nhiều nhánh sai lầm phổ biến.

## 6. Chương trình Java 17+ đầy đủ: copy, chuyển mã và kiểm thử lỗi

Tạo file **`TransferTextDemo.java`** với toàn bộ mã sau. Chương trình **không lấy file người dùng làm input**: nó tạo thư mục tạm, viết fixture với charset tường minh, chạy các phép copy, xác minh kết quả rồi tự dọn. Như vậy người học có thể chạy mà không đụng dữ liệu production.

### 6.1. Toàn bộ source `TransferTextDemo.java`

```java
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.io.StringReader;
import java.io.StringWriter;
import java.nio.charset.Charset;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.charset.UnmappableCharacterException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import java.util.Comparator;

public final class TransferTextDemo {

    static long copyText(Path source, Path target,
            Charset sourceCharset, Charset targetCharset)
            throws IOException {

        if (Files.exists(target)
                && Files.isSameFile(source, target)) {
            throw new IllegalArgumentException(
                    "Source and target refer to the same file");
        }

        try (Reader reader = Files.newBufferedReader(
                     source, sourceCharset);
             Writer writer = Files.newBufferedWriter(
                     target, targetCharset,
                     StandardOpenOption.CREATE_NEW,
                     StandardOpenOption.WRITE)) {

            return reader.transferTo(writer);
        }
    }

    static final class TrackingReader extends StringReader {
        boolean closed;

        TrackingReader(String text) {
            super(text);
        }

        @Override
        public void close() {
            closed = true;
            super.close();
        }
    }

    static final class TrackingWriter extends StringWriter {
        boolean closed;

        @Override
        public void close() {
            closed = true;
        }
    }

    static void require(boolean pass, String why) {
        if (!pass) {
            throw new AssertionError(why);
        }
    }

    public static void main(String[] args)
            throws Exception {

        Path folder = Files.createTempDirectory(
                "text-transfer-demo-");

        try {
            Path utf8Source =
                    folder.resolve("source-utf8.txt");
            Path utf8Target =
                    folder.resolve("copy-utf8.txt");

            String content =
                    "Xin ch\u00E0o \uD83C\uDF0D!\r\n"
                    + "D\u00F2ng 2: \u20AC v\u00E0 \u6F22\u5B57\n";

            Files.writeString(
                    utf8Source, content, StandardCharsets.UTF_8);

            long copied = copyText(
                    utf8Source, utf8Target,
                    StandardCharsets.UTF_8,
                    StandardCharsets.UTF_8);

            boolean sameText = Files.readString(
                    utf8Target, StandardCharsets.UTF_8)
                    .equals(content);

            boolean sameBytes = Arrays.equals(
                    Files.readAllBytes(utf8Source),
                    Files.readAllBytes(utf8Target));

            int codePoints = content.codePointCount(
                    0, content.length());

            System.out.println("utf8.chars=" + copied);
            System.out.println(
                    "utf8.codePoints=" + codePoints);
            System.out.println(
                    "utf8.sameText=" + sameText);
            System.out.println(
                    "utf8.sameBytes=" + sameBytes);
            System.out.println(
                    "utf8.crlfPreserved="
                    + Files.readString(
                            utf8Target, StandardCharsets.UTF_8)
                            .contains("\r\n"));

            Path latin1Source =
                    folder.resolve("latin1.txt");
            Path latin1Target =
                    folder.resolve("converted-utf8.txt");

            String latin1 = "caf\u00E9\r\n";

            Files.writeString(
                    latin1Source, latin1,
                    StandardCharsets.ISO_8859_1);

            long converted = copyText(
                    latin1Source, latin1Target,
                    StandardCharsets.ISO_8859_1,
                    StandardCharsets.UTF_8);

            boolean transcodeText = Files.readString(
                    latin1Target, StandardCharsets.UTF_8)
                    .equals(latin1);

            System.out.println(
                    "transcode.chars=" + converted);
            System.out.println(
                    "transcode.sourceBytes="
                    + Files.size(latin1Source));
            System.out.println(
                    "transcode.targetBytes="
                    + Files.size(latin1Target));
            System.out.println(
                    "transcode.sameText=" + transcodeText);

            Path badSource =
                    folder.resolve("invalid-utf8.txt");
            Path badTarget =
                    folder.resolve("invalid-output.txt");

            Files.write(
                    badSource,
                    new byte[] {(byte) 0xC3, (byte) 0x28});

            boolean malformedRejected = false;
            try {
                copyText(badSource, badTarget,
                        StandardCharsets.UTF_8,
                        StandardCharsets.UTF_8);
            } catch (MalformedInputException expected) {
                malformedRejected = true;
            }
            System.out.println(
                    "malformed.rejected="
                    + malformedRejected);

            Path asciiTarget =
                    folder.resolve("ascii-output.txt");
            boolean unmappableRejected = false;
            try {
                copyText(utf8Source, asciiTarget,
                        StandardCharsets.UTF_8,
                        StandardCharsets.US_ASCII);
            } catch (UnmappableCharacterException expected) {
                unmappableRejected = true;
            }
            System.out.println(
                    "unmappable.rejected="
                    + unmappableRejected);

            boolean sameFileRejected = false;
            try {
                copyText(utf8Source, utf8Source,
                        StandardCharsets.UTF_8,
                        StandardCharsets.UTF_8);
            } catch (IllegalArgumentException expected) {
                sameFileRejected = true;
            }
            System.out.println(
                    "sameFile.rejected="
                    + sameFileRejected);

            boolean existingTargetRejected = false;
            try {
                copyText(utf8Source, utf8Target,
                        StandardCharsets.UTF_8,
                        StandardCharsets.UTF_8);
            } catch (FileAlreadyExistsException expected) {
                existingTargetRejected = true;
            }
            System.out.println(
                    "existingTarget.rejected="
                    + existingTargetRejected);

            TrackingReader probeReader =
                    new TrackingReader("OK");
            TrackingWriter probeWriter =
                    new TrackingWriter();

            long probeCount =
                    probeReader.transferTo(probeWriter);

            boolean stayedOpen = !probeReader.closed
                    && !probeWriter.closed
                    && probeCount == 2;

            probeWriter.write("!");

            boolean writableAfterTransfer =
                    "OK!".equals(probeWriter.toString());

            probeReader.close();
            probeWriter.close();

            System.out.println(
                    "transfer.keptStreamsOpen="
                    + stayedOpen);
            System.out.println(
                    "transfer.writerUsable="
                    + writableAfterTransfer);

            require(copied == content.length(),
                    "UTF-16 character count");
            require(codePoints < copied,
                    "Supplementary Unicode count");
            require(sameText && sameBytes,
                    "UTF-8 content and byte comparison");
            require(converted == latin1.length()
                    && transcodeText
                    && Files.size(latin1Source) == 6
                    && Files.size(latin1Target) == 7,
                    "ISO-8859-1 to UTF-8 conversion");
            require(malformedRejected && unmappableRejected,
                    "Encoding errors must be rejected");
            require(sameFileRejected
                    && existingTargetRejected,
                    "Unsafe overwrite must be rejected");
            require(stayedOpen && writableAfterTransfer,
                    "transferTo must not close streams");

            System.out.println("tests=PASS");
        } finally {
            try (var paths = Files.walk(folder)) {
                for (var path : paths
                        .sorted(Comparator.reverseOrder())
                        .toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
```

**Các điểm thiết kế của chương trình:**

1. `copyText` nhận **hai Charset độc lập** nên có thể copy UTF-8→UTF-8 hoặc **transcode** ISO-8859-1→UTF-8.
2. `Files.newBufferedReader` thực hiện giải mã nghiêm ngặt theo charset được truyền.
3. `Files.newBufferedWriter` thực hiện mã hóa theo charset đích và có thể báo lỗi khi ký tự không thể biểu diễn.
4. `CREATE_NEW` bảo vệ file đích đã tồn tại, không tự cắt rỗng file cũ.
5. `Files.isSameFile` kiểm tra hai đường dẫn đang trỏ đến cùng một file nếu đích tồn tại (kể cả một số alias/hard link/symlink).
6. `try-with-resources` đóng cả Reader và Writer; Writer được đóng **sau khi kết thúc transfer**, giúp flush/finalize dữ liệu.
7. Toàn bộ đầu vào được tạo ở thư mục tạm; test không đụng file của ứng dụng.
8. `TrackingReader` và `TrackingWriter` xác nhận `transferTo` **không tự đóng** nguồn/đích.
9. Các phép `require` biến bài demo thành kiểm thử có điều kiện PASS/FAIL, không chỉ in output mà không kiểm tra.
10. Dọn dẹp trong `finally` để tránh giữ file thử nghiệm. Nếu hệ điều hành không cho xóa file tạm vì bị ứng dụng khác khóa, lỗi cleanup phải được xử lý riêng trong công cụ production.

**Cảnh báo:** bảo vệ `Files.isSameFile` + `CREATE_NEW` phù hợp cho demo và nhiều trường hợp thông thường, nhưng không tạo ra **giao dịch atomic** chống mọi race hoặc thay đổi symlink do tác nhân không đáng tin. Khi thư mục đích là shared/untrusted directory, cần chính sách filesystem/permissions và kỹ thuật ghi an toàn mạnh hơn.

### 6.2. Biên dịch và chạy

Dùng JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 TransferTextDemo.java
java TransferTextDemo
```

`-encoding UTF-8` xác định encoding của **source code Java trong lệnh javac**, khác hoàn toàn với `sourceCharset`/`targetCharset` của **file được sao chép tại runtime**.

Chương trình Java cố dùng escape Unicode trong string fixture để không phụ thuộc encoding terminal; các file sinh ra vẫn dùng charset tường minh.

### 6.3. Stdout đã kiểm chứng trên OpenJDK 24 HotSpot

```text
utf8.chars=30
utf8.codePoints=29
utf8.sameText=true
utf8.sameBytes=true
utf8.crlfPreserved=true
transcode.chars=6
transcode.sourceBytes=6
transcode.targetBytes=7
transcode.sameText=true
malformed.rejected=true
unmappable.rejected=true
sameFile.rejected=true
existingTarget.rejected=true
transfer.keptStreamsOpen=true
transfer.writerUsable=true
tests=PASS
```

Output trên được thu từ **chương trình đã biên dịch và chạy thật** bằng JDK 24, với thư mục tạm tạo trong lúc chạy, không phải một chuỗi log phỏng đoán.

Mục tiêu của test là xác nhận **hợp đồng Java API** trong môi trường xác định. Một chương trình production cần thêm giới hạn tài nguyên, logging có kiểm soát, validation path/charset, chiến lược recovery và phép đo I/O phù hợp.

## 7. Giải thích từng nhánh kiểm thử và kết quả

### 7.1. UTF-8 → UTF-8, giữ nguyên ký tự và xuống dòng

Nguồn trong chương trình tương đương:

```text
Xin chào 🌍!
Dòng 2: € và 漢字
```

Dòng đầu kết thúc bởi **CRLF** (`\r\n`), dòng thứ hai kết thúc bởi **LF** (`\n`).

Khi dùng:

```java
long copied = copyText(
        utf8Source, utf8Target,
        StandardCharsets.UTF_8,
        StandardCharsets.UTF_8);
```

lần thử nghiệm thu được:

```text
utf8.chars=30
utf8.codePoints=29
utf8.sameText=true
utf8.sameBytes=true
utf8.crlfPreserved=true
```

Điều đó chứng minh:

- Toàn bộ ký tự được đọc/ghi đúng thứ tự.
- Chuỗi Unicode sau giải mã bằng UTF-8 **bằng hệt chuỗi gốc**.
- Trong fixture UTF-8 hợp lệ này, byte file nguồn và file đích trùng nhau.
- Kết thúc dòng CRLF **không bị chuẩn hóa** thành LF, vì `Reader.transferTo` không xử lý theo từng dòng.
- Số `char` được chuyển khác số Unicode code point do có emoji nằm ngoài BMP.

**Không suy rộng “cứ UTF-8→UTF-8 là mọi file byte-identical”**. Nếu đầu vào chứa byte không hợp lệ, việc giải mã có thể thất bại; nếu có chính sách bỏ/thay ký tự, đầu ra có thể khác. BOM, Unicode normalization hoặc việc xử lý nội dung thêm bởi lớp khác cũng có thể ảnh hưởng. Test ở đây dùng UTF-8 hợp lệ, không biến đổi nội dung ngoài chuyển Reader→Writer.

### 7.2. ISO-8859-1 → UTF-8, chữ giữ nguyên nhưng byte thay đổi

Fixture:

```java
String latin1 = "caf\u00E9\r\n";

Files.writeString(
        latin1Source,
        latin1,
        StandardCharsets.ISO_8859_1);

long converted = copyText(
        latin1Source, latin1Target,
        StandardCharsets.ISO_8859_1,
        StandardCharsets.UTF_8);
```

Kết quả:

```text
transcode.chars=6
transcode.sourceBytes=6
transcode.targetBytes=7
transcode.sameText=true
```

Giải thích: trong ISO-8859-1, ký tự **é** có một byte; trong UTF-8, **é** mã hóa bằng hai byte. Vì thế file đích lớn hơn **1 byte** dù văn bản vẫn chính xác.

**Không được suy rằng `long` trả về từ `transferTo` là số byte đã copy**, và cũng không lấy kích thước byte để dự đoán số ký tự của file Unicode.

### 7.3. Input UTF-8 không hợp lệ phải bị từ chối

Fixture byte:

```java
Files.write(
        badSource,
        new byte[] {(byte) 0xC3, (byte) 0x28});
```

Byte `0xC3` mở đầu một chuỗi UTF-8 hai byte nhưng byte tiếp theo `0x28` không phải continuation hợp lệ. Khi dùng `Files.newBufferedReader(..., UTF_8)`, test bắt:

```text
malformed.rejected=true
```

Đó là **hành vi fail closed khi giải mã** theo hợp đồng của API đang dùng, không phải một tính năng nhận diện charset tự động. Nếu một input thực sự là Latin-1 nhưng bị đọc nhầm thành UTF-8, có thể gây lỗi; cách sửa đúng là xác định charset nguồn từ hợp đồng dữ liệu.

### 7.4. Output ASCII không thể ghi tiếng Việt, euro và emoji

Input chứa các ký tự không thuộc ASCII; đích cấu hình `StandardCharsets.US_ASCII`. Khi mã hóa, `Files.newBufferedWriter` không thể biểu diễn các ký tự ấy, nên test bắt:

```text
unmappable.rejected=true
```

Lỗi `UnmappableCharacterException` có thể chỉ xuất hiện khi **flush/close** Writer vì buffering; `try-with-resources` bao trùm cả quá trình này.

**Điểm vận hành:** đừng tùy tiện chuyển sang chế độ thay ký tự thành `?` nếu nghiệp vụ yêu cầu bảo toàn nội dung. Nếu đích cần chứa toàn bộ Unicode, dùng charset phù hợp như UTF-8 theo hợp đồng hệ thống.

### 7.5. File nguồn và đích không được là cùng file

Chương trình thử `copyText(utf8Source, utf8Source,...)` và nhận:

```text
sameFile.rejected=true
```

Nếu không kiểm tra và mở Writer ở chế độ mặc định `TRUNCATE_EXISTING`, file nguồn có thể bị cắt rỗng **trước khi Reader kịp đọc dữ liệu**. Đây là một lỗi phá dữ liệu thường gặp khi “copy” mà không xác nhận hai Path độc lập.

### 7.6. Không ghi đè đích đã tồn tại

Vì chọn `CREATE_NEW`, chạy lại copy tới cùng file đích sẽ bị từ chối:

```text
existingTarget.rejected=true
```

Điều này **không phải lỗi** của `Reader.transferTo`, mà là **chính sách OpenOption** do ứng dụng chủ động thiết kế. Nó phù hợp khi phải tránh xóa nội dung cũ.

### 7.7. Reader/Writer không bị đóng bởi `transferTo`

Hai đối tượng TrackingReader/TrackingWriter đặt cờ `closed` khi `close` được gọi. Sau `transferTo`, kiểm thử thấy cả hai cờ vẫn `false`, Writer vẫn ghi thêm `"!"` được:

```text
transfer.keptStreamsOpen=true
transfer.writerUsable=true
```

Đó là lý do `try-with-resources` hoặc chính sách close rõ ràng vẫn cần thiết. **Không** dựa vào `transferTo` để đóng hoặc flush Writer; nó không có trách nhiệm đó theo hợp đồng.

## 8. Số ký tự, Unicode code point và byte là ba đại lượng khác nhau

Java `char` là một **đơn vị mã UTF-16 16-bit**, không nhất thiết tương đương một Unicode code point. Emoji 🌍 thường được biểu diễn bằng **hai `char` liên tiếp** (một surrogate pair).

Ví dụ:

```java
String s = "\uD83C\uDF0D"; // 🌍

int utf16Units = s.length();                  // 2
int codePoints = s.codePointCount(0, s.length()); // 1
int utf8Bytes = s.getBytes(StandardCharsets.UTF_8).length; // 4
```

Đây là **đoạn minh họa nằm trong một phương thức**. `transferTo` nhận/ghi luồng `char` nên số `long` thường so được với `String.length()` khi truyền nguyên chuỗi qua `StringReader`, **không** phải số code points hay UTF-8 bytes.

Trong bài test:

| Thước đo | Kết quả | Ý nghĩa |
| --- | ---: | --- |
| `utf8.chars` | 30 | Số `char`/UTF-16 code units chuyển |
| `utf8.codePoints` | 29 | Số Unicode code point trong chuỗi |
| `transcode.chars` | 6 | Số ký tự UTF-16 khi đổi Latin-1 → UTF-8 |
| `transcode.sourceBytes` | 6 | Số byte ở ISO-8859-1 |
| `transcode.targetBytes` | 7 | Số byte sau mã hóa UTF-8 |

Nếu cần **số byte** đã xử lý, đo `Files.size` trước/sau khi tất cả Writer đã đóng, hoặc dùng thống kê byte stream riêng. Nếu cần **số code point**, phải giải mã và đếm theo Unicode code point, không trực tiếp dùng giá trị return `transferTo`.

**Đặc biệt:** nếu một file chứa các đoạn UTF-16 surrogate sai hoặc một charset không biểu diễn được ký tự, việc mã hóa/giải mã có thể thất bại theo error policy. Không có phép đếm nào tự làm dữ liệu sai trở thành đúng.

## 9. Giữ nguyên CRLF/LF: vì sao `transferTo` khác `readLine`?

`Reader.transferTo` chuyển các ký tự **theo đúng luồng**, bao gồm các ký tự điều khiển xuống dòng. Nó không tự chuyển `\r\n` thành `\n`.

Ngược lại, các cách xử lý theo từng dòng có thể bỏ line separators rồi thêm lại line separator theo hệ điều hành:

```java
String line;
while ((line = reader.readLine()) != null) {
    writer.write(line);
    writer.write(System.lineSeparator());
}
```

Đoạn trên **chỉ minh họa** khi `reader` là `BufferedReader`; nó không phải bản sao chép byte/text tương đương: `readLine` loại bỏ separator gốc, còn `System.lineSeparator()` có thể khác hệ điều hành hoặc kiểu dòng trong file nguồn.

Nếu yêu cầu “sao chép văn bản **không đổi line endings**”, `Reader.transferTo` phù hợp hơn vòng lặp `readLine` rồi `newLine`. Nếu nghiệp vụ chủ động yêu cầu chuẩn hóa xuống dòng, đó là **tác vụ biến đổi văn bản riêng**, không phải hành vi mặc định của `transferTo`.

**Caveat:** khi Reader/Writer nằm sau một lớp transform/filter tự sửa newline, kết quả có thể khác. Phép bảo toàn CRLF áp dụng khi dùng Reader/Writer file thông thường, không có transform bổ sung, như test trong bài.

## 10. Sao chép văn bản khác `Files.copy` và `InputStream.transferTo`

Chọn công cụ theo **đơn vị dữ liệu muốn giữ**:

| Mục tiêu | API nên cân nhắc | Lý do |
| --- | --- | --- |
| Copy nguyên byte, bất kể là text/binary | `Files.copy(Path, Path, ...)` | Không giải mã/mã hóa, bảo toàn byte nội dung |
| Chuyển byte từ InputStream tới OutputStream | `InputStream.transferTo(OutputStream)` | Luồng byte, không thực hiện charset conversion |
| Copy văn bản với charset xác định | **`Reader.transferTo(Writer)`** | Chuyển ký tự đã giải mã |
| Đổi ISO-8859-1 sang UTF-8 | **Reader UTF-8? Không: Reader Latin-1, Writer UTF-8** | Charset nguồn và đích khác nhau |
| Đổi line endings theo policy | Vòng lặp/transform văn bản có chủ đích | `transferTo` không chuẩn hóa dòng |
| Thay thế một file production an toàn | Ghi sang file tạm, validate, rồi move theo policy | Tránh file đích bị ghi dở khi lỗi |

Ví dụ muốn copy **byte chính xác**, không chuyển mã:

```java
Files.copy(source, target);
```

Theo API, nếu target đã tồn tại và không có replace option phù hợp, thao tác có thể báo `FileAlreadyExistsException`. `Files.copy` không phải luôn atomic và có policy về attributes/symlink cần xem tùy ứng dụng; đừng tự suy nó tương đương backup transaction.

Ví dụ xử lý byte stream:

```java
try (var in = Files.newInputStream(source);
     var out = Files.newOutputStream(
             target, StandardOpenOption.CREATE_NEW)) {
    long byteCount = in.transferTo(out);
}
```

Đây là **sao chép byte**, nên `byteCount` khác với `Reader.transferTo` khi có nhiều byte cho một Unicode character. **Đừng dùng Reader cho file ảnh, ZIP, PDF, encrypted data hoặc format nhị phân**; việc giải mã sẽ làm mất hoặc làm sai dữ liệu.

## 11. Hành vi khi file đích trùng nguồn và nguy cơ truncate

Mẫu nguy hiểm thường thấy:

```java
try (var in = Files.newBufferedReader(path, UTF_8);
     var out = Files.newBufferedWriter(path, UTF_8)) {
    in.transferTo(out);
}
```

**Không dùng** đoạn code này. Khi Writer mở cùng Path với chế độ mặc định có `TRUNCATE_EXISTING`, nguồn có thể bị cắt rỗng, dẫn tới mất dữ liệu.

Cần xác định:

- Hai Path có bằng nhau sau chuẩn hóa tuyệt đối không?
- Có thể là alias symlink/hardlink cùng file không?
- Path đích có tồn tại và chính sách có cho overwrite không?
- Các tác nhân khác có thể sửa Path giữa thời điểm check và mở file không?

Trong demo, `Files.exists(target) && Files.isSameFile(source,target)` giúp phát hiện trùng file đã tồn tại, và `CREATE_NEW` từ chối mọi target tồn tại. Nhưng đây không phải bảo đảm chống **race/symlink attack** trong môi trường chia sẻ thiếu kiểm soát.

Nếu xử lý file từ người dùng không tin cậy, phải áp chính sách bảo mật filesystem: thư mục đích được kiểm soát, validation path, quyền truy cập hạn chế, và cần chống follow symlink khi yêu cầu an toàn cao.

## 12. Lỗi giữa chừng: dữ liệu có thể đã được ghi một phần

`Reader.transferTo` không đưa ra bảo đảm “hoặc copy đầy đủ, hoặc file đích nguyên vẹn”. Khi `IOException` xảy ra:

- Reader có thể mới tiêu thụ một phần ký tự.
- Writer có thể đã ghi **một phần** dữ liệu.
- Writer còn buffer dữ liệu chưa flush.
- File đích có thể đã tồn tại với nội dung **không hoàn chỉnh**.
- Nếu ký tự không thể encode, lỗi có thể xuất hiện khi Writer **đóng**.
- Nếu `transferTo` trả về bình thường nhưng `close`/`flush` lỗi, toàn thao tác vẫn phải được xem là **thất bại**.

Vì vậy nên thiết kế một số chính sách:

**Với file đích mới và được phép thất bại:**

- Dùng `CREATE_NEW`.
- Nếu lỗi, ghi nhận và xóa file đích dở dang **khi chắc chắn ứng dụng sở hữu file đó**.
- Không công bố file đó đã hoàn chỉnh trước khi Writer đóng thành công.

**Với file đích quan trọng đang tồn tại:**

- Không viết thẳng vào target bằng `TRUNCATE_EXISTING`.
- Tạo file tạm trong **cùng thư mục/filesystem** đích.
- Ghi/đóng thành công, kiểm tra nội dung/encoding và chính sách metadata nếu cần.
- Dùng `Files.move` với lựa chọn `ATOMIC_MOVE` khi filesystem hỗ trợ, cùng chính sách xử lý khi target tồn tại.
- Nếu atomic move không được hỗ trợ, **không tự hạ yêu cầu đảm bảo** một cách âm thầm: báo lỗi hoặc áp quy trình fallback đã được sản phẩm phê duyệt.

**Lưu ý:** `ATOMIC_MOVE` phụ thuộc filesystem/provider, và khi target tồn tại có những hành vi implementation-specific theo API. Không nói rằng “thêm hai open options là mọi overwrite trở thành atomic transaction”. Với dữ liệu quan trọng cần durability sau mất điện, còn phải xét **fsync/directory sync**, filesystem và chính sách lưu trữ.

Trong demo, những file `invalid-output.txt` và `ascii-output.txt` có thể đã được tạo trước khi xuất hiện lỗi encoding. Chương trình **xóa toàn bộ thư mục tạm** trong `finally`, không để chúng bị dùng nhầm làm kết quả thành công.

## 13. Bộ mã tường minh chưa đủ nếu không biết nguồn được mã hóa như thế nào

Ví dụ file thực sự là **ISO-8859-1** nhưng bạn dùng:

```java
Files.newBufferedReader(path, StandardCharsets.UTF_8);
```

Có hai khả năng:

1. Byte sequence không hợp lệ theo UTF-8 → ném `MalformedInputException` khi đọc.
2. Byte tình cờ hợp lệ theo UTF-8 → tạo ra **nội dung sai** mà không có exception, tức mojibake.

**Không tồn tại một cách “đọc đại” bằng UTF-8 rồi fallback Latin-1 là luôn đúng**. Vì Latin-1 có thể diễn giải nhiều byte hợp lệ, fallback không chứng minh encoding dự kiến. Phải dùng **hợp đồng dữ liệu** như metadata có xác thực, cấu hình nguồn, đặc tả protocol hoặc quy tắc nhập đã được thống nhất.

Với CSV:

- Charset là một phần format; nội dung có thể chứa dấu phân tách và newline.
- `transferTo` chỉ copy văn bản, **không parse CSV** hay xử lý quoting.
- File có encoding đúng chưa có nghĩa CSV schema/escaping hợp lệ.
- Nếu cần validate/canonicalize CSV, sử dụng parser và encoder đúng chuẩn, không viết logic tách dấu phẩy tự tạo.

Với JSON:

- UTF-8 thường là lựa chọn trao đổi phù hợp.
- `transferTo` không xác nhận cú pháp hoặc schema JSON.
- Nếu file chứa nội dung không đáng tin, cần kiểm tra theo hợp đồng ứng dụng ngoài việc sao chép.

## 14. Charset encoder/decoder xử lý lỗi như thế nào?

Một điểm dễ sai là nghĩ **mọi API nhận Charset đều xử lý lỗi byte giống nhau**.

### `Files.newBufferedReader` và `Files.newBufferedWriter`

Theo Javadoc của `Files`:

- `newBufferedReader(path, cs)` báo `IOException` nếu byte đầu vào malformed hoặc unmappable.
- `newBufferedWriter(path, cs, ...)` báo `IOException` khi ký tự không thể mã hóa, đôi khi trong `flush` hoặc `close`.

Đó là lý do bài test có thể bắt `MalformedInputException` và `UnmappableCharacterException`.

### `InputStreamReader` / `OutputStreamWriter` có constructor tiện lợi

Một số constructor tiện lợi của `InputStreamReader(InputStream, Charset)` và `OutputStreamWriter(OutputStream, Charset)` sử dụng **chiến lược thay thế dữ liệu không hợp lệ** theo quy tắc của implementation/API; đặc biệt Javadoc `OutputStreamWriter` nêu nó thay malformed surrogate và unmappable sequences bằng substitution mặc định. Nếu cần fail-closed, **không giả định hai constructor tiện lợi luôn giống phương thức strict của `Files`**.

Có thể dùng `CharsetDecoder` và `CharsetEncoder` để **quy định rõ error policy**. Ví dụ hai cấu hình:

```java
var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

var encoder = StandardCharsets.UTF_8.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
```

Đây là **đoạn minh họa trong một phương thức**, cần import `CodingErrorAction`. Nó cho thấy chủ đích “**báo lỗi thay vì thay ký tự**”.

Nếu dùng trực tiếp `InputStreamReader`/`OutputStreamWriter` với các đối tượng decoder/encoder:

```java
try (Reader reader = new BufferedReader(
             new InputStreamReader(
                     Files.newInputStream(source), decoder));
     Writer writer = new BufferedWriter(
             new OutputStreamWriter(
                     Files.newOutputStream(
                             target, StandardOpenOption.CREATE_NEW),
                     encoder))) {
    long copied = reader.transferTo(writer);
}
```

Đây là một đoạn code nằm trong phương thức có sẵn `source`, `target`, `decoder`, `encoder` và import tương ứng. Nó làm rõ cách quản lý error action. Tuy nhiên, với mục tiêu **copy file văn bản thông thường**, `Files.newBufferedReader/newBufferedWriter` với Charset tường minh ngắn hơn, dễ review và đã cung cấp behavior báo lỗi như bài thực hành.

**Không thay malformed input bằng `CodingErrorAction.IGNORE` một cách âm thầm** nếu dữ liệu cần giữ nguyên; làm vậy sẽ mất ký tự mà không chứng minh output đúng.

## 15. Byte-order mark (BOM) và Unicode normalization

Một số file UTF có **Byte Order Mark** (BOM); cách xử lý khác nhau theo charset:

- Với `UTF-16`, BOM có vai trò chỉ thứ tự byte của dữ liệu và encoder có thể phát ra BOM theo charset.
- Với `UTF-16LE`/`UTF-16BE`, thứ tự byte đã nằm trong charset name; cách đọc/ghi BOM có quy tắc riêng theo `Charset`.
- Với UTF-8, BOM không cần thiết để xác định byte order và có thể được giải mã thành ký tự **U+FEFF**; không tự giả định mọi Reader luôn bỏ BOM.
- `Reader.transferTo` **không phải một BOM sanitizer**, cũng không tự chuyển Unicode từ NFC sang NFD hoặc ngược lại.

Nếu file được kỳ vọng “bản sao text không còn BOM” hoặc “chuẩn hóa NFC”, cần một bước **biến đổi văn bản có chủ đích** trước khi ghi. Khi đã làm transform, đừng quảng cáo kết quả là copy nguyên ký tự nữa.

Việc cùng một văn bản hiển thị giống nhau chưa chắc có cùng code points hoặc bytes nếu Unicode normalization khác. `transferTo` truyền những `char` mà Reader trả về; nó không kiểm tra tương đương ngôn ngữ.

## 16. Cách copy file có encoding khác nhưng vẫn giữ nguyên nội dung

Một phương thức tái sử dụng gồm **hai charset** như demo:

```java
static long transcode(Path source, Path target,
        Charset sourceCharset, Charset targetCharset)
        throws IOException {

    try (Reader reader =
                 Files.newBufferedReader(source, sourceCharset);
         Writer writer =
                 Files.newBufferedWriter(
                         target,
                         targetCharset,
                         StandardOpenOption.CREATE_NEW,
                         StandardOpenOption.WRITE)) {

        return reader.transferTo(writer);
    }
}
```

Đây là phương thức nằm trong class; **chưa có guard same-file rõ ràng**, nhưng `CREATE_NEW` từ chối target đã tồn tại. Khi dùng làm API sản phẩm, hãy thêm validation path/owner policy giống demo `copyText`.

Ví dụ:

```java
long chars = transcode(
        inputLatin1,
        outputUtf8,
        StandardCharsets.ISO_8859_1,
        StandardCharsets.UTF_8);
```

Nếu source chứa ký tự Unicode không biểu diễn được theo charset của Writer, sẽ có lỗi. Một chiến lược khác như thay bằng `?` chỉ phù hợp khi có **quy tắc business cụ thể cho phép mất thông tin**, và cần log/QA rõ.

**Không dùng `String.getBytes` cùng với `new String(bytes, charset)` để convert toàn file rất lớn** khi một Reader/Writer streaming đơn giản đáp ứng yêu cầu. Cách đọc toàn file vào byte array/String có thể tiêu tốn bộ nhớ tỷ lệ với kích thước file.

## 17. Khi nào không nên dùng `Reader.transferTo`?

**Không nên dùng cho:**

- Ảnh `.png`, `.jpg`, video hoặc âm thanh.
- File `.zip`, `.jar`, `.pdf`, định dạng nén hoặc nhị phân.
- Dữ liệu đã mã hóa hoặc có chữ ký số dựa trên byte gốc.
- File yêu cầu **byte identity** tuyệt đối nhưng encoding chưa được xác định.
- Trường hợp cần chuyển đổi theo **line-based semantics** hoặc normalize nội dung; chỉ `transferTo` không đủ.
- Nguồn là untrusted stream không có giới hạn thời gian/tài nguyên và có thể block vô hạn, trừ khi môi trường đã có timeout/cancellation policy.
- Các pipeline cần transaction/durability mạnh hơn một phép ghi thẳng vào file.

Đối với file thực sự cần **sao chép byte nguyên vẹn**, dùng `Files.copy` hoặc `InputStream.transferTo`.

**Vẫn nên dùng `Reader.transferTo`** khi nhiệm vụ chính là **chuyển văn bản theo charset**, nhất là khi muốn streaming, bảo toàn các ký tự xuống dòng và có thể transcode giữa hai encoding khác nhau.

## 18. So với vòng lặp thủ công trên Reader/Writer

Trước Java 10 hoặc khi cần logic xử lý từng chunk, người học có thể viết:

```java
char[] buffer = new char[8192];
int n;
long total = 0;

while ((n = reader.read(buffer)) != -1) {
    writer.write(buffer, 0, n);
    total += n;
}
```

Đây là **mẫu minh họa** trong một phương thức có sẵn `reader` và `writer`. Vòng lặp tạo một mảng `char[]` và chuyển từng chunk, nhưng phải tự quản lý count/error/resource.

Với Java 10+:

```java
long total = reader.transferTo(writer);
```

Ưu điểm:

- Giảm boilerplate và nguy cơ viết sai offset/length.
- Trả về tổng số `char` đã chuyển.
- Hoạt động theo luồng, không cần tải toàn file thành `String`.
- Dễ kết hợp charset được khai báo tại lúc tạo Reader/Writer.

Tuy nhiên, khi ứng dụng cần **lọc ký tự, kiểm tra từng dòng, chuẩn hóa, tính checksum sau chuyển đổi hoặc báo tiến độ chi tiết**, có thể cần vòng lặp/reader wrapper hoặc pipeline khác. `transferTo` ưu tiên **chuyển ký tự nguyên trạng**, không cung cấp callback từng chunk.

**Đừng tự thay vòng lặp tối ưu riêng trong hệ thống throughput cao mà không benchmark**, nhưng cũng đừng giữ vòng lặp legacy chỉ vì trước đây chưa có `Reader.transferTo` nếu nó không đem lại tính năng cần thiết.

## 19. Kiểm thử ranh giới và nhánh lỗi nên có trong CI

Một bộ test chất lượng cho hàm copy văn bản nên có ít nhất:

| Ca | Input/Output | Điều phải xác minh |
| --- | --- | --- |
| File rỗng | UTF-8 → UTF-8 | `transferTo` trả `0`, file đích rỗng |
| Chỉ ASCII | UTF-8 → UTF-8 | Chữ và byte đầu ra đúng |
| Tiếng Việt | UTF-8 → UTF-8 | Không mojibake |
| Emoji ngoài BMP | UTF-8 → UTF-8 | UTF-16 count khác codePointCount |
| CRLF và LF trộn | UTF-8 → UTF-8 | Line ending giữ nguyên |
| Latin-1 có `é` | ISO-8859-1 → UTF-8 | Text giống, byte counts khác |
| Input UTF-8 malformed | Byte sequence không hợp lệ | **Fail closed**, không coi output là thành công |
| Output US-ASCII có ký tự ngoài ASCII | Unmappable | **Fail closed**, dọn partial output |
| Target tồn tại | `CREATE_NEW` | Không bị ghi đè |
| Source == target | Cùng file/alias | Bị từ chối trước khi làm hỏng dữ liệu |
| File nguồn không tồn tại | Input path sai | IOException phù hợp |
| Không đủ quyền | File/directory bị OS từ chối | Exception được báo; không ép ghi đè |
| Disk full/quota | Writer không ghi hết | Không công bố output là hoàn chỉnh |
| Writer close thất bại | Flush/finalization lỗi | Coi là copy thất bại |
| Concurrent modification | File nguồn bị thay trong lúc đọc | Xác định policy nhất quán/snapshot riêng |
| File quá lớn | Streaming | Không tải toàn bộ vào RAM |
| Target symlink/hardlink lạ | File destination untrusted | Đảm bảo không làm sai vùng ghi ngoài phạm vi |

Trong demo đã kiểm thử phần lớn các nhánh logic cốt lõi. Các nhánh liên quan disk-full, permissions, concurrency và symlink race **chưa được chạy trên filesystem bị hạn chế**, vì đó là các phép thử tích hợp có thể gây tác động, cần môi trường test riêng.

**Đừng viết unit test dựa trên exact wording của exception message**: thông điệp phụ thuộc OS/provider. Có thể assert loại lỗi chính hoặc các điều kiện bất biến; với nhiều hệ thống, cần kiểm tra exception cause chain.

## 20. Quy trình dùng trong batch import/export production

Một pipeline văn bản có thể tổ chức theo từng giai đoạn:

```text
Input Path + source Charset từ hợp đồng dữ liệu
        |
        v
Validate path, permissions, metadata, expected size
        |
        v
Decode bằng Reader (charset explicit)
        |
        +-- nếu malformed -> FAIL, quarantine source
        |
        v
transferTo(Writer)
        |
        +-- nếu unmappable -> FAIL, không công bố output
        |
        v
Đóng Writer thành công (flush/encoding hoàn tất)
        |
        v
Validate output content / checksum thích hợp
        |
        v
Publish bằng move/commit policy được chấp thuận
        |
        v
Record số char, số byte, charset, duration, kết quả
```

**Ghi log có ý nghĩa nhưng không lộ nội dung:**

- Path/identifier đã được phép quan sát, không log dữ liệu nhạy cảm.
- Charset nguồn và charset đích.
- Số UTF-16 `char` được `transferTo` báo.
- Số byte nguồn và đích sau khi đóng.
- Trạng thái success/failure, loại exception và stage xảy ra lỗi.
- Thời gian xử lý nếu cần theo dõi throughput.
- Hash byte khi bài toán thật sự cần xác minh **byte equality**, nhưng hiểu hash trước/sau transcode sẽ khác dù text đúng.

Nếu cần kiểm tra **text equivalence**, có thể decode cả nguồn và đích bằng đúng charset của từng file rồi so chuỗi hoặc tính digest trên một representation text đã quy định. Với input lớn cần kiểm tra streaming thay vì tải hết nội dung. Tránh coi file byte khác sau transcode là lỗi.

## 21. Lưu ý về hiệu năng và khả năng mở rộng

`Reader.transferTo` thuận tiện nhưng không làm biến mất chi phí:

- **Decode** byte → char.
- **Encode** char → byte.
- Buffered filesystem I/O.
- Kiểm tra malformed/unmappable sequences.
- Đọc/ghi trên storage chậm, remote mount hoặc các file rất lớn.

Với streaming, bộ nhớ cần cho pipeline có thể được giữ tương đối ổn định theo buffer (khác với `Files.readString` có thể dùng bộ nhớ tỷ lệ kích thước file). Tuy nhiên, **không hứa “O(1) memory cho mọi Reader/Writer”** vì implementation tùy chỉnh có thể buffering thêm, và Java process còn các chi phí khác.

Nếu ứng dụng muốn copy nhiều file:

- Giới hạn số tác vụ I/O song song phù hợp storage/CPU/memory.
- Quản lý số file descriptors.
- Không chuyển sang parallel stream bừa bãi với hàng nghìn tệp.
- Giữ mỗi Reader/Writer trong đúng thread/lifecycle, tránh chia sẻ instance không có đồng bộ.
- Nếu có yêu cầu cancellation/timeout, thiết kế trong tầng orchestration/stream thực tế; `Reader.transferTo` có thể block và không có tham số timeout riêng.

**Không sử dụng kết quả `long` làm bằng chứng dữ liệu đã được ghi bền xuống thiết bị**. Với BufferedWriter, việc đóng thành công cho thấy hoàn tất ở cấp API nhưng durability qua mất điện có yêu cầu fsync/filesystem riêng.

## 22. Những lỗi hiểu nhầm thường gặp

| Nhầm lẫn | Vì sao sai | Cách đúng |
| --- | --- | --- |
| “`transferTo` trả số byte.” | `Reader` chuyển `char`, không phải raw byte | Đếm UTF-16 units; đo byte riêng |
| “Java 10 Reader.transferTo đã lỗi thời.” | Vẫn có trong Java SE 25/26 | Dùng khi copy văn bản |
| “`transferTo` tự đóng cả hai stream.” | Reader Javadoc nói **không đóng** | Dùng try-with-resources |
| “`transferTo` luôn flush/đóng Writer.” | Không có hợp đồng đó | Đóng/flush riêng và bắt lỗi |
| “Nếu trả `long` thì file chắc chắn hoàn chỉnh.” | Có thể lỗi trong close/flush hoặc chưa publish | Xem toàn thao tác I/O |
| “Dùng default charset đủ an toàn cho mọi file.” | Có thể khác hợp đồng nguồn | Dùng Charset explicit |
| “Tất cả Charset overload thay ký tự sai theo cùng cách.” | Files.* có hợp đồng báo lỗi, constructor tiện lợi khác | Chọn strict APIs/coder policy |
| “UTF-8 → UTF-8 luôn byte-identical.” | Có thể input không hợp lệ/transform/BOM | Xác minh theo yêu cầu |
| “Chỉ cần đếm `String.length()` là Unicode code points.” | Emoji có surrogate pair | Dùng `codePointCount` khi cần |
| “Văn bản được copy bởi Reader chắc chắn giữ file attributes.” | Reader chỉ truyền ký tự | Quản lý metadata riêng |
| “`readLine` + `newLine` giống `transferTo`.” | Có thể đổi CRLF ↔ LF | Dùng transferTo nếu muốn giữ dòng |
| “Dùng `Reader.transferTo` để copy ZIP/PDF.” | Giải mã sẽ làm sai binary | Dùng Files.copy hoặc byte stream |
| “`CREATE_NEW` nghĩa không có file partial khi lỗi.” | File mới có thể đã tạo và ghi dở | Cleanup hoặc staged publish |
| “`Files.isSameFile` loại bỏ mọi race.” | Check và open là các thao tác riêng | Kiểm soát filesystem/untrusted paths |
| “Chuyển Latin-1 sang UTF-8 mà size khác là lỗi.” | Số byte mỗi ký tự có thể khác | So văn bản đã decode |
| “Đổi `file.encoding` sau startup giải quyết mọi file.” | Không phải cấu hình charset cho từng file | Pass Charset tại Reader/Writer |
| “Input có byte malformed thì có thể cứ bỏ qua.” | Có thể mất dữ liệu hoặc sai nghĩa | Báo lỗi, xử lý theo data contract |
| “Chỉ gọi `transferTo` là đủ để update file production.” | Lỗi có thể làm output dở dang | Stage/validate/publish theo policy |
| “Có file output là PASS.” | File partial cũng có thể tồn tại | Chỉ công bố sau close và QA |

## 23. Câu hỏi và bài tập tự kiểm tra

### Câu 1. `Reader.transferTo` khác `InputStream.transferTo` thế nào?

**Đáp án:** Reader chuyển **ký tự** và trả số UTF-16 `char`; InputStream chuyển **byte** và trả số byte. Dùng Reader khi cần biết charset/đổi mã; dùng InputStream hoặc Files.copy để giữ byte.

### Câu 2. Vì sao cần hai Charset?

**Đáp án:** Input cần biết cách **giải mã** byte; output cần biết cách **mã hóa** ký tự. ISO-8859-1 → UTF-8 là ví dụ hai Charset khác nhau. Nếu chỉ khai báo một bên còn bên kia dùng default, kết quả phụ thuộc môi trường ngoài ý định.

### Câu 3. Có phải 30 chars = 30 code points?

**Đáp án:** Không. Trong fixture có emoji 🌍, `Reader.transferTo` trả `30` UTF-16 units còn `String.codePointCount` trả `29` code points. Emoji được biểu diễn bằng hai đơn vị UTF-16.

### Câu 4. Tại sao Latin-1 sang UTF-8 nguồn 6 bytes, đích 7 bytes?

**Đáp án:** `"café\r\n"` có sáu đơn vị UTF-16, trong Latin-1 chữ `é` dùng một byte và trong UTF-8 dùng hai byte. Văn bản không đổi nhưng số byte có thể tăng.

### Câu 5. Nếu muốn tránh ghi đè file cũ?

**Đáp án:** Mở file đích với `StandardOpenOption.CREATE_NEW`, không dùng overload Writer mặc định cắt file đã tồn tại. Đồng thời phải có chính sách dọn output partial nếu exception.

### Câu 6. File nguồn và đích cùng Path có an toàn không?

**Đáp án:** Không. Writer chế độ truncate có thể xóa file trước khi đọc. Kiểm tra same-file và dùng chính sách mở không phá dữ liệu; trong môi trường có symlink/race cần kiểm soát thư mục và filesystem mạnh hơn.

### Câu 7. Exception xảy ra khi đóng Writer, không phải lúc transferTo: QA có được PASS?

**Đáp án:** Không. Writer buffer/encoder có thể chỉ phát hiện lỗi khi `flush` hoặc `close`. Toàn bộ khối try-with-resources phải hoàn tất không lỗi rồi mới coi thao tác thành công.

### Câu 8. Dùng `Files.newBufferedReader(path, UTF8)` đọc byte `0xC3 0x28`?

**Đáp án:** Đó là UTF-8 malformed; API có thể ném `MalformedInputException` khi đọc. Đừng đổi sang Latin-1 chỉ để hết exception nếu chưa có hợp đồng xác định charset thực.

### Câu 9. `transferTo` có giữ nguyên CRLF không?

**Đáp án:** Với Reader/Writer file thông thường không có text transform, **có**, vì `\r` và `\n` đều là ký tự được chuyển nguyên trạng. Vòng `readLine` rồi `newLine` có thể đổi separators.

### Câu 10. Sao chép PDF có dùng `Reader.transferTo` được không?

**Đáp án:** Không phù hợp. PDF là định dạng byte/binary; phải dùng `Files.copy` hoặc byte streams để tránh hỏng file do giải mã văn bản.

### Câu 11. Có thể dùng `CharsetDecoder`/`CharsetEncoder` làm gì?

**Đáp án:** Định nghĩa rõ chính sách khi gặp malformed/unmappable sequences, ví dụ `CodingErrorAction.REPORT` để từ chối thay vì âm thầm sửa. Với Files.newBufferedReader/newBufferedWriter, Javadoc đã mô tả việc báo lỗi đọc/ghi khi dữ liệu không hợp lệ cho charset.

## 24. Checklist trước khi dùng `Reader.transferTo` trong ứng dụng

1. File nguồn có thực sự là **văn bản** chứ không phải binary?
2. Charset nguồn được quy định ở đâu? Có đáng tin và được lưu cùng metadata/config không?
3. Charset đích có phù hợp hệ thống nhận file không?
4. Có dùng **`StandardCharsets` constants** thay vì đoán default charset?
5. Có đóng Reader/Writer bằng **try-with-resources**, kể cả lỗi close?
6. Có hiểu `long` trả về là **UTF-16 char units**, không phải bytes/code points?
7. Có xử lý malformed input và unmappable output **theo data policy**?
8. Có tránh **ghi đè/cắt rỗng** target ngoài ý định?
9. Có kiểm tra cùng file/symlink và quyền ở môi trường thật?
10. Khi lỗi xảy ra, có dọn **partial output** hoặc staging file?
11. Nếu cần thay file đang tồn tại, có chính sách **validate rồi publish** và atomic move khi hỗ trợ?
12. Có phân biệt CRLF/LF và yêu cầu normalize rõ ràng không?
13. Có cần BOM/Unicode normalization không, và có test riêng nếu có?
14. Nếu yêu cầu byte identity, có chuyển sang **`Files.copy`** không?
15. Nếu file lớn, có dùng streaming thay vì tải toàn bộ lên heap?
16. Có giới hạn số tác vụ song song/file descriptors phù hợp?
17. Có log số ký tự và số byte như **hai số đo khác nhau**?
18. Có test emoji, tiếng Việt, Latin-1→UTF-8 và các nhánh fail-closed?
19. Có đảm bảo không công bố file thành công **trước khi đóng Writer và QA**?
20. Có chạy trên **JDK/runtime còn được bảo trì** và đúng container/image triển khai?

## Kết luận

`Reader.transferTo(Writer)` là API **từ Java 10 và vẫn còn áp dụng** để chuyển **toàn bộ ký tự còn lại** từ Reader sang Writer, theo đúng thứ tự, và trả về **số đơn vị UTF-16 `char` đã chuyển**. Nó **không** đóng hai luồng; người gọi phải quản lý `try-with-resources` và lỗi I/O.

Cách thực hành đúng với văn bản là mở nguồn và đích bằng **Charset tường minh**, ví dụ `Files.newBufferedReader(source, UTF_8)` và `Files.newBufferedWriter(target, UTF_8, CREATE_NEW, WRITE)`. Khi đổi ISO-8859-1 → UTF-8, nội dung ký tự có thể giữ nguyên nhưng số byte thay đổi. Lỗi malformed UTF-8, ký tự không thể encode và tình huống trùng/đã tồn tại file đích cần được xử lý **có chủ đích**.

Bộ ví dụ Java 17+ đã được biên dịch và chạy với kết quả **`tests=PASS`** cho các nhánh Unicode, xuống dòng, chuyển mã và fail-closed. Đây là nền tảng để xây dựng pipeline sao chép/chuyển mã văn bản an toàn; khi yêu cầu backup byte-perfect hoặc file binary, **`Files.copy`/byte streams** mới là API đúng.

## Tài liệu tham khảo chính thức và còn hiệu lực

- [Oracle Java SE 25 — `Reader.transferTo(Writer)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Reader.html#transferTo(java.io.Writer)): mô tả chuyển tất cả ký tự, return số char, không đóng luồng, lỗi I/O và `since 10`.
- [Oracle Java SE 25 — `Files.newBufferedReader`, `Files.newBufferedWriter`, `Files.copy`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): charset explicit, encoding errors và open options.
- [Oracle Java SE 25 — `StandardCharsets`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF_8, ISO_8859_1, US_ASCII, UTF_16, UTF_16LE/BE.
- [Oracle Java SE 25 — `CharsetDecoder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetDecoder.html): error handling khi giải mã, mặc định REPORT.
- [Oracle Java SE 25 — `CharsetEncoder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetEncoder.html): error handling khi mã hóa, mặc định REPORT.
- [Oracle Java SE 25 — `CodingErrorAction`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CodingErrorAction.html): REPORT, REPLACE và IGNORE.
- [Oracle Java SE 25 — `OutputStreamWriter`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/OutputStreamWriter.html): mã hóa ký tự sang byte và lưu ý substitution/surrogate.
- [Oracle Java SE 25 — `InputStreamReader`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/InputStreamReader.html): giải mã byte thành char với Charset hoặc CharsetDecoder.
- [Oracle Java SE 25 — `StandardOpenOption`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/StandardOpenOption.html): CREATE_NEW, CREATE, TRUNCATE_EXISTING, WRITE, APPEND.
- [Oracle Java SE 25 — `String.length()` và `codePointCount`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): Unicode UTF-16 code units và code points.
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): bối cảnh default charset JDK hiện hành; vẫn nên chọn charset tường minh khi hợp đồng file yêu cầu.
