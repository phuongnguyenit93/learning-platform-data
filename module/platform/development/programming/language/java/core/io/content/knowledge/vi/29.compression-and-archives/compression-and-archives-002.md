# Java GZIPInputStream và GZIPOutputStream: nén, giải nén dữ liệu theo luồng

## 1. Mục tiêu và bối cảnh

Trong Java Core I/O, package `java.util.zip` cung cấp hai lớp quan trọng để làm việc với định dạng **GZIP**:

- **`GZIPOutputStream`**: nhận byte chưa nén, nén bằng cơ chế DEFLATE và ghi ra một luồng ở **định dạng GZIP**.
- **`GZIPInputStream`**: nhận luồng byte GZIP, giải nén để ứng dụng đọc được byte gốc.

Cả hai là **filter stream**: chúng bọc một `OutputStream` hoặc `InputStream` khác. Vì vậy bạn có thể nén file, dữ liệu từ mạng, hoặc dữ liệu trong bộ nhớ mà không phải tự triển khai thuật toán DEFLATE.

Mục tiêu của bài:

1. Hiểu cách GZIP đóng gói dữ liệu nén, khác gì với ZIP và raw DEFLATE.
2. Tạo `.gz` từ file hoặc từ các byte và giải nén lại.
3. Nắm chu trình stream: `write` → `finish`/`close` và `read` tới EOF.
4. Sử dụng buffer để xử lý file lớn thay vì luôn đưa toàn bộ dữ liệu lên heap.
5. Phân biệt lỗi dữ liệu nén, CRC32, stream chưa đóng, charset và dữ liệu không tin cậy.
6. Có chương trình **Java 17+ hoàn chỉnh** minh họa round-trip và stdout rõ ràng.

> **GZIP là phương pháp nén/đóng gói byte, không phải cơ chế mã hóa hay xác thực danh tính.** Nó có checksum để phát hiện một số lỗi dữ liệu, nhưng không bảo đảm an toàn trước người cố ý sửa dữ liệu.

## 2. GZIP hoạt động như thế nào?

Về mặt logic, một luồng GZIP có các thành phần:

```text
Byte nguồn
   |
   v
GZIPOutputStream
   |
   +-- GZIP header
   +-- DEFLATE-compressed payload
   +-- GZIP trailer (CRC32 + ISIZE)
   |
   v
Byte GZIP được ghi ra tệp/luồng
   |
   v
GZIPInputStream
   |
   +-- đọc header, giải nén DEFLATE
   +-- kiểm tra trailer/CRC khi đọc đến phần kết thúc hợp lệ
   |
   v
Byte nguồn được khôi phục
```

Thông thường:

- **Header** chứa chữ ký định dạng GZIP: hai byte đầu là `0x1F` và `0x8B`, cùng các thông tin định dạng khác.
- **Payload** sử dụng DEFLATE để nén. DEFLATE là cơ chế nén, còn GZIP là định dạng bọc quanh dữ liệu DEFLATE và metadata.
- **Trailer** chứa CRC32 của dữ liệu **chưa nén** và kích thước dữ liệu gốc modulo `2^32` (`ISIZE`).

Checksum là cách kiểm tra lỗi ngẫu nhiên/truncation ở định dạng; nó không phải chữ ký số, HMAC hay cơ chế chống giả mạo mật mã.

### GZIP có phải định dạng ZIP không?

**Không.**

| Tiêu chí | GZIP (`.gz`) | ZIP (`.zip`) |
|---|---|---|
| Ý tưởng chính | Nén một luồng dữ liệu byte | Container chứa nhiều entry/file có tên |
| API Java | `GZIPInputStream`, `GZIPOutputStream` | `ZipInputStream`, `ZipOutputStream`, `ZipFile` |
| Đường dẫn/tên file nội bộ | Không phải API quản lý cây entry | Có tên entry và metadata của từng entry |
| Dùng cho một file văn bản/binary | Rất phù hợp | Được, nhưng container phức tạp hơn |
| Đóng gói cả thư mục | Không trực tiếp | Phù hợp |
| Ví dụ phổ biến | `log.txt.gz`, phản hồi HTTP gzip | `backup.zip` chứa nhiều tệp |

Định dạng gzip cho phép những cấu trúc như nhiều gzip member nối tiếp theo đặc tả, nhưng **`GZIPOutputStream` không phải công cụ tạo ZIP entries** và ứng dụng không nên giả định một file `.gz` biểu diễn một thư mục. Kết hợp `tar + gzip` tạo `.tar.gz` là hai lớp định dạng: tar đóng gói nhiều entry, gzip nén luồng tar.

## 3. Hai lớp filter stream và cách lồng luồng

`GZIPOutputStream` mở rộng `DeflaterOutputStream`. Nó bọc một `OutputStream` đích:

```java
try (GZIPOutputStream gzip =
         new GZIPOutputStream(Files.newOutputStream(Path.of("note.txt.gz")))) {
    gzip.write("Xin chào GZIP!\n".getBytes(StandardCharsets.UTF_8));
}
```

Đây là **đoạn mã minh họa**; phải đặt trong method xử lý `IOException`, import `GZIPOutputStream`, `Files`, `Path`, `StandardCharsets`.

Luồng xử lý:

```text
"Xin chào GZIP!\n"
       |
  UTF-8 encode → byte[]
       |
 gzip.write(byte[])
       |
  DEFLATE + header/trailer
       |
 Files.newOutputStream(...)
       |
 note.txt.gz (byte nhị phân)
```

Ngược lại, `GZIPInputStream` bọc `InputStream` nguồn:

```java
try (GZIPInputStream gzip =
         new GZIPInputStream(Files.newInputStream(Path.of("note.txt.gz")))) {
    byte[] bytes = gzip.readAllBytes();
    String text = new String(bytes, StandardCharsets.UTF_8);
}
```

**`GZIPInputStream` trả byte gốc**, chưa tự diễn giải chúng là text UTF-8. Charset là lựa chọn của định dạng dữ liệu hoặc giao thức ứng dụng; dùng `StandardCharsets.UTF_8` minh bạch ở cả hai chiều.

`readAllBytes()` chỉ phù hợp khi chắc dữ liệu **sau giải nén** đủ nhỏ cho bộ nhớ. Với file lớn hoặc đầu vào không tin cậy, dùng vòng lặp với buffer và giới hạn kích thước.

## 4. Nén file theo streaming: không cần nạp toàn bộ vào RAM

Mẫu nên dùng khi nén một file lớn:

```java
static void gzipFile(Path source, Path target) throws IOException {
    try (InputStream in = Files.newInputStream(source);
         OutputStream rawOut = Files.newOutputStream(target);
         GZIPOutputStream gzip = new GZIPOutputStream(rawOut)) {

        byte[] buffer = new byte[16 * 1024];
        int count;

        while ((count = in.read(buffer)) != -1) {
            gzip.write(buffer, 0, count);
        }
    }
}
```

Đây là **một phương thức minh họa**, không phải chương trình độc lập; cần import `InputStream`, `OutputStream`, `IOException`, `Files`, `Path`, `GZIPOutputStream`.

Giải thích:

1. `Files.newInputStream(source)` đọc file nguồn.
2. `Files.newOutputStream(target)` là đích lưu byte đã nén. Tệp đích thông thường được tạo hoặc ghi đè theo options mặc định.
3. `GZIPOutputStream` mã hóa các byte được `write` thành stream GZIP.
4. Vòng lặp đọc tối đa 16 KiB mỗi lần, không phụ thuộc tổng dung lượng file.
5. Khi rời try-with-resources, `gzip.close()` hoàn tất luồng gzip và đóng underlying output stream.

Trong mã trên, `rawOut` vừa có biến riêng vừa được bọc bởi `gzip`. Việc đóng hai lần một số stream tiêu chuẩn thường không gây vấn đề, nhưng **mẫu ownership gọn hơn** là chỉ khai báo `GZIPOutputStream gzip = new GZIPOutputStream(Files.newOutputStream(target))`, để wrapper sở hữu stream dưới. Mẫu có biến `rawOut` được trình bày để giúp thấy rõ pipeline.

**Không nén đè lên chính source path đang đọc.** Nếu output mặc định truncate source trước khi đọc hết, dữ liệu có thể mất. Hãy tạo tệp đích riêng, hoặc ghi tạm rồi thay thế với chính sách atomic/durability phù hợp nếu cập nhật một file quan trọng.

## 5. Giải nén file theo streaming

Mẫu tương ứng:

```java
static void gunzipFile(Path sourceGzip, Path target) throws IOException {
    try (GZIPInputStream gzip =
             new GZIPInputStream(Files.newInputStream(sourceGzip));
         OutputStream out = Files.newOutputStream(target)) {

        byte[] buffer = new byte[16 * 1024];
        int count;

        while ((count = gzip.read(buffer)) != -1) {
            out.write(buffer, 0, count);
        }
    }
}
```

Ở đây mỗi `read` lấy các byte đã giải nén từ `gzip`. `write` của output thường ghi byte vào tệp đích mà không cần lưu cả nội dung vào một mảng khổng lồ.

Điểm lưu ý:

- Chương trình nên xác định policy trước khi ghi: có ghi đè file đích cũ không? Nếu cần tránh file đích bị dang dở khi dữ liệu gzip bị hỏng, **giải nén vào file tạm**, validate rồi thay tên đích.
- `GZIPInputStream.read` có thể ném `ZipException` (một dạng `IOException`) nếu header/trailer hoặc nội dung nén không hợp lệ.
- Nếu không đọc tới EOF và đóng quá sớm, chương trình có thể **chưa đi đến trailer để kiểm tra CRC32/ISIZE**. Với file cần được xác thực về tính toàn vẹn theo format, phải giải nén và kiểm tra đến kết thúc hợp lệ.
- Không lấy số byte đã nén làm giới hạn số byte giải nén. Một file gzip nhỏ có thể nở ra thành dữ liệu rất lớn.

## 6. Chu trình `finish()`, `flush()` và `close()`

Đây là phần quan trọng nhất khi viết gzip.

### `GZIPOutputStream.finish()`

`finish()` hoàn tất việc nén, ghi phần dữ liệu còn lại và trailer GZIP xuống stream đích **mà không nhất thiết đóng underlying stream**.

Khi nào hữu ích?

- Cần hoàn tất một member GZIP, nhưng còn muốn thao tác hợp lệ khác trên stream dưới theo một định dạng container chuyên biệt.
- Cần bảo đảm khối GZIP đã được hoàn tất trước một bước xử lý tiếp theo, trong khi vẫn kiểm soát vòng đời stream bên dưới.

Với nhu cầu ghi một file `.gz` thông thường, **dùng try-with-resources rồi đóng GZIPOutputStream** là cách dễ và an toàn nhất.

### `flush()` không thay thế `finish()`

`flush()` chuyển dữ liệu đang được đệm theo cơ chế stream/deflater, nhưng **không kết thúc một file gzip hợp lệ**. Không thể gọi `gzip.flush()` rồi giả định trailer đã có.

`GZIPOutputStream` có constructor `GZIPOutputStream(OutputStream out, int size, boolean syncFlush)`. Khi `syncFlush=true`, lời gọi `flush` có thể yêu cầu DEFLATE thực hiện `SYNC_FLUSH` để bên đọc xử lý dữ liệu đang có với độ trễ thấp hơn; đổi lại có thể ảnh hưởng hiệu quả nén.

Ví dụ minh họa:

```java
try (GZIPOutputStream gzip =
         new GZIPOutputStream(outputStream, 8192, true)) {
    gzip.write(chunk1);
    gzip.flush(); // SYNC_FLUSH, chưa tạo trailer kết thúc member.
    gzip.write(chunk2);
} // close hoàn tất gzip và đóng stream dưới.
```

`outputStream`, `chunk1`, `chunk2` là biến giả định của đoạn mã minh họa. Không nhầm `flush()` với **fsync**: việc buộc dữ liệu xuống thiết bị lưu trữ cần API/cơ chế riêng và không được `GZIPOutputStream.flush` tự bảo đảm.

### `close()`

`close()` của `GZIPOutputStream` kết thúc luồng nén chưa hoàn tất, phát hành dữ liệu còn lại/trailer và đóng luồng được bọc. `close()` có thể ném `IOException`, nên không bỏ qua ngoại lệ rồi coi file là thành công.

**Bẫy:** không làm mất reference đến gzip wrapper trước khi `finish` hoặc `close`. Chỉ đóng `FileOutputStream` ở dưới trong khi gzip chưa kết thúc có thể tạo file `.gz` bị cắt/thiếu trailer.

## 7. Chương trình Java 17+ hoàn chỉnh: nén, nhận diện và giải nén

Chương trình sau sử dụng một file tạm:

1. Tạo chuỗi ASCII để có độ dài byte xác định.
2. Dùng `GZIPOutputStream` nén vào file `.gz`.
3. Kiểm tra hai byte signature GZIP ở đầu file.
4. Dùng `GZIPInputStream` giải nén lại.
5. So sánh bytes gốc và bytes kết quả bằng `Arrays.equals`.
6. Dọn file tạm.

Tạo file **`GzipStreamsDemo.java`**:

```java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

public class GzipStreamsDemo {

    public static void main(String[] args) throws Exception {
        String message = "Java IO: GZIP\n";
        byte[] original = message.getBytes(StandardCharsets.US_ASCII);
        Path gzipFile = Files.createTempFile("gzip-demo-", ".gz");

        try {
            // Ghi toàn bộ byte nguồn vào một GZIP member.
            try (GZIPOutputStream gzip =
                     new GZIPOutputStream(Files.newOutputStream(gzipFile))) {
                gzip.write(original);
            } // close ghi phần kết thúc/trailer.

            boolean hasGzipSignature;
            try (InputStream raw = Files.newInputStream(gzipFile)) {
                int first = raw.read();
                int second = raw.read();
                hasGzipSignature = first == 0x1f && second == 0x8b;
            }

            byte[] restored;
            try (GZIPInputStream gzip =
                     new GZIPInputStream(Files.newInputStream(gzipFile))) {
                restored = gzip.readAllBytes();
            }

            String decoded = new String(
                    restored, StandardCharsets.US_ASCII);

            System.out.println("Original bytes: " + original.length);
            System.out.println("GZIP signature: " + hasGzipSignature);
            System.out.println("Decoded: " + decoded.stripTrailing());
            System.out.println("Round-trip: " + Arrays.equals(original, restored));
        } finally {
            Files.deleteIfExists(gzipFile);
        }
    }
}
```

Biên dịch/chạy trong thư mục chứa file:

```bash
javac GzipStreamsDemo.java
java GzipStreamsDemo
```

**Stdout chính xác khi tạo/đọc/ghi/xóa file tạm thành công:**

```text
Original bytes: 14
GZIP signature: true
Decoded: Java IO: GZIP
Round-trip: true
```

Giải thích:

- `"Java IO: GZIP\n"` có 14 byte ASCII, nên `original.length == 14`.
- Signature GZIP bắt đầu bằng `0x1f 0x8b`, bất kể độ lớn file nén cụ thể.
- `close()` trong try-with-resources hoàn tất stream gzip trước khi chương trình đọc file.
- `GZIPInputStream.readAllBytes()` phù hợp ở ví dụ vì đầu ra đã biết rất nhỏ; với dữ liệu người dùng cung cấp hoặc file lớn, cần giới hạn streaming.
- `stripTrailing()` chỉ bỏ ký tự xuống dòng khi in message, không thay đổi mảng `restored` dùng để so sánh.
- `Arrays.equals` kiểm tra nội dung byte khôi phục giống hệt byte ban đầu. Điều này **không** chứng minh GZIP mã hóa/chống sửa đổi do đối phương; nó xác nhận round-trip của ví dụ.

Chương trình không in size của `gzipFile` vì kích thước nén có thể chịu ảnh hưởng lựa chọn header/implementation, phiên bản thư viện và nội dung; stdout tập trung vào các giá trị có thể xác định một cách đáng tin.

## 8. Buffer và giải thích cơ chế streaming

Với một file lớn, chu trình thông dụng:

```text
NÉN
┌──────────────┐    16 KiB     ┌──────────────────┐
│ InputStream  │ ────────────> │ GZIPOutputStream │ ──> file.gz
└──────────────┘               └──────────────────┘

GIẢI NÉN
file.gz ──> ┌─────────────────┐   16 KiB      ┌───────────────┐
            │ GZIPInputStream │ ────────────> │ OutputStream  │
            └─────────────────┘               └───────────────┘
```

Kích thước buffer ảnh hưởng số lần gọi I/O và chi phí xử lý, **không bắt buộc lớn bằng toàn bộ file**. Với nhiều ứng dụng, buffer vài KiB đến vài chục KiB là điểm khởi đầu hợp lý; benchmark với dạng dữ liệu, thiết bị và throughput thực tế.

Một số cách viết khác:

```java
try (InputStream source = Files.newInputStream(inputFile);
     GZIPOutputStream output =
         new GZIPOutputStream(Files.newOutputStream(gzipFile))) {
    source.transferTo(output);
}
```

`InputStream.transferTo(OutputStream)` có từ Java 9, dùng được trên Java 17. Nó sao chép byte từ input tới output theo luồng, không bắt buộc ứng dụng tự viết vòng lặp `read/write`. Nhưng **không tự cung cấp giới hạn số byte giải nén hay kiểm tra nội dung nghiệp vụ**; không nên thay bằng `transferTo` mà bỏ các giới hạn dành cho dữ liệu không tin cậy.

Đối với input lớn, tránh:

```java
byte[] whole = Files.readAllBytes(veryLargePath);
gzip.write(whole); // Dễ gây áp lực heap khi file quá lớn.
```

Bản thân `gzip.write(byte[])` vẫn có thể hoạt động đúng; vấn đề nằm ở việc `readAllBytes` nạp toàn bộ file vào bộ nhớ trước.

## 9. Nén văn bản: Charset là trách nhiệm của ứng dụng

`GZIPOutputStream` và `GZIPInputStream` hoạt động ở **mức byte**, không ở mức `String` hay ký tự Unicode.

Khi nén văn bản, phải mã hóa tường minh:

```java
String text = "Tiếng Việt: cà phê ☕\n";
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);

try (GZIPOutputStream gzip = new GZIPOutputStream(output)) {
    gzip.write(utf8);
}
```

Đoạn này là minh họa, `output` phải là `OutputStream` hợp lệ. Lúc giải nén:

```java
try (GZIPInputStream gzip = new GZIPInputStream(input)) {
    byte[] originalUtf8 = gzip.readAllBytes();
    String textAgain =
            new String(originalUtf8, StandardCharsets.UTF_8);
}
```

Tương tự, `input` phải là `InputStream` hợp lệ. Không dùng charset mặc định môi trường khi format đã quy định UTF-8. Nếu file gzip chứa ảnh, dữ liệu nhị phân hoặc serialize object thì **không** tự động biến nó thành String sau giải nén.

### Có thể dùng BufferedReader/Writer không?

Có, khi bạn biết dữ liệu bên trong GZIP thực sự là văn bản. Ví dụ:

```java
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                new GZIPInputStream(Files.newInputStream(path)),
                StandardCharsets.UTF_8))) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý từng dòng.
    }
}
```

`reader.readLine()` bỏ dấu xuống dòng khỏi giá trị trả về; nếu tái xuất văn bản, việc tự nối `\n` có thể thay đổi kiểu newline so với bản gốc. Nếu yêu cầu **đúng byte gốc**, nên giải nén dưới dạng byte stream.

## 10. Dữ liệu hỏng: header, payload, CRC32 và EOF

Những lỗi thường gặp khi đọc gzip:

- File không phải GZIP nhưng bị đặt tên `.gz` → header có thể sai và `GZIPInputStream` ném lỗi.
- Tệp bị cắt trước khi DEFLATE hoàn tất → giải nén có thể ném `EOFException` hoặc `ZipException`.
- Trailer CRC32/ISIZE không đúng → lỗi kiểm tra dữ liệu khi đọc đến điểm kiểm tra.
- Tệp đang được writer ghi dở → reader có thể thấy thiếu dữ liệu hoặc trailer chưa xuất hiện.
- Underlying stream có lỗi disk/network → phát sinh `IOException`.

`GZIPInputStream` thường báo những lỗi định dạng qua `ZipException`, vốn kế thừa `IOException`. Ứng dụng nên bắt `IOException` ở ranh giới I/O và bổ sung thông tin đường dẫn/nguồn dữ liệu phù hợp.

Ví dụ:

```java
try (GZIPInputStream gzip =
         new GZIPInputStream(Files.newInputStream(path))) {
    byte[] bytes = gzip.readAllBytes(); // Nhỏ và nguồn đáng tin.
    // Chỉ dùng bytes sau khi giải nén tới EOF thành công.
} catch (ZipException ex) {
    // GZIP không hợp lệ hoặc dữ liệu/trailer không khớp.
    throw new IOException("GZIP hỏng: " + path, ex);
}
```

Đây là đoạn minh họa. Không khẳng định **mọi dạng tệp hỏng** đều ném đúng một subclass ngoại lệ; nên quản lý `IOException` tổng quát và kiểm tra dữ liệu ứng dụng sau khi giải nén.

Một tệp có hai byte signature `0x1f 0x8b` **chưa đủ chứng minh file gzip hợp lệ**. Kiểm tra signature chỉ là bước nhận diện sơ bộ; chỉ sau giải nén/kiểm tra tới EOF và kiểm tra nội dung ứng dụng mới có cơ sở tốt hơn.

### CRC32 khác chữ ký bảo mật

CRC32 phát hiện nhiều lỗi dữ liệu ngẫu nhiên; một đối tượng cố ý sửa byte có thể tính lại CRC32. Do đó không dùng CRC để:

- Xác thực người gửi.
- Kiểm tra nội dung có bị thay đổi bởi kẻ tấn công.
- Thay thế TLS, HMAC hoặc chữ ký số.
- Quyết định một file cấu hình không tin cậy có đủ quyền chạy nội dung hay không.

Dữ liệu bảo mật cần cơ chế xác thực/kiểm tra riêng, cộng với kiểm tra schema và giới hạn tài nguyên sau giải nén.

## 11. Zip bomb/GZIP bomb và giới hạn bộ nhớ

**Tỷ lệ nén cao** có thể khiến một file đầu vào nhỏ giải nén thành hàng gigabyte dữ liệu. Đây là dạng **decompression bomb**, có thể tiêu thụ đĩa, RAM, CPU hoặc làm nghẽn dịch vụ.

Đặc biệt nguy hiểm:

```java
// Phản ví dụ với đầu vào không tin cậy.
byte[] all = new GZIPInputStream(untrustedInput).readAllBytes();
```

`readAllBytes` có thể cố cấp phát mảng rất lớn. Thay vào đó, kiểm tra số byte **đã giải nén** trong khi streaming.

### Ví dụ helper giải nén có giới hạn

```java
static long copyGzipWithLimit(
        InputStream compressed, OutputStream output, long maxUncompressedBytes)
        throws IOException {

    if (maxUncompressedBytes < 0) {
        throw new IllegalArgumentException("Negative limit");
    }

    long total = 0L;

    try (GZIPInputStream gzip = new GZIPInputStream(compressed)) {
        byte[] buffer = new byte[8192];
        int count;

        while ((count = gzip.read(buffer)) != -1) {
            if (count > maxUncompressedBytes - total) {
                throw new IOException("Uncompressed data exceeds limit");
            }

            output.write(buffer, 0, count);
            total += count;
        }
    }

    return total;
}
```

Đây là một **phương thức minh họa** cần import `InputStream`, `OutputStream`, `IOException`, `GZIPInputStream`. Nó giả định `maxUncompressedBytes` không âm. Mẫu `count > maxUncompressedBytes - total` tránh tràn số khi cộng, với bất biến `0 <= total <= maxUncompressedBytes`.

Lưu ý:

- Phương thức **đóng `compressed`** gián tiếp khi đóng `GZIPInputStream` vì wrapper sở hữu nguồn. Nó **không đóng `output`**; caller quyết định đóng output.
- Nếu phát hiện vượt hạn mức sau khi đã ghi một phần output, file đích có thể đang chứa dữ liệu chưa hoàn chỉnh. Trong hệ thống thực nên ghi ra file tạm rồi chỉ công bố khi copy và validation thành công.
- Hạn mức số byte **không tự giới hạn CPU/time**. Với ứng dụng nhận file từ người lạ, cần thêm timeout, quota, số phiên xử lý đồng thời, dung lượng đĩa và giới hạn độ sâu/loại định dạng dữ liệu sau giải nén.
- Với buffer có `length > 0`, `InputStream` tuân thủ hợp đồng trả số byte dương khi có dữ liệu hoặc `-1` khi EOF; code giả định stream hợp lệ.
- Nếu nguồn gzip là stream rất chậm, chỉ một giới hạn byte chưa đủ tránh chiếm worker lâu.

### Giới hạn tỷ lệ nén

Tùy bài toán, có thể giới hạn cả kích thước file nén (`Files.size(path)`) lẫn kích thước output. Nhưng tỷ lệ nén không cố định; file text lặp có thể nén rất tốt, còn file đã nén/đã mã hóa gần như không giảm. Đừng từ chối mọi file có tỷ lệ cao nếu ứng dụng cần dữ liệu đó; hãy xây chính sách dựa trên nguồn tin cậy và quota thực tế.

## 12. Chọn mức nén và buffer

`GZIPOutputStream` sử dụng Deflater. Java cung cấp cấu hình ở mức `Deflater` (ví dụ `BEST_SPEED`, `DEFAULT_COMPRESSION`, `BEST_COMPRESSION`) thông qua API liên quan, nhưng constructor `GZIPOutputStream` thường dùng cấu hình mặc định.

Tham số `size` trong constructor:

```java
new GZIPOutputStream(output, 8192);
```

là **kích thước buffer nội bộ**, không phải “compression level 8192”. Không nhầm kích thước buffer với mức nén hay kích thước file nguồn. Với ứng dụng cần mức nén tùy chỉnh, cần xem xét API `Deflater`/cách xây dựng stream phù hợp; đừng sửa thuộc tính nội bộ không public hoặc dựa vào reflection như một API ổn định.

GZIP thường phù hợp cho:

- Văn bản lặp, JSON, XML, log.
- Payload truyền qua hệ thống chấp nhận `Content-Encoding: gzip`.
- Một số dữ liệu định dạng nhị phân có dư thừa.

GZIP thường ít giúp ích hoặc có thể tăng dung lượng đối với:

- JPEG, PNG, MP4 và file đã nén tốt sẵn.
- Dữ liệu được mã hóa với entropy cao.
- Payload quá nhỏ, nơi chi phí header/trailer chiếm đáng kể.

Không khẳng định GZIP **luôn nhỏ hơn** dữ liệu gốc. Với dữ liệu ngắn hoặc không nén được, output gzip có thể lớn hơn input.

## 13. GZIP trong HTTP và trao đổi mạng

Header `Content-Encoding: gzip` trong HTTP chỉ cách body đã được mã hóa/nén; nó khác với extension file `.gz` trên đĩa.

Ví dụ về giao thức:

```text
Client request:
Accept-Encoding: gzip

Server response:
Content-Encoding: gzip
Content-Type: application/json

[body bytes ở định dạng gzip]
```

- Bên gửi phải thực sự gửi byte gzip tương thích với `Content-Encoding` đã khai báo.
- Bên nhận phải giải nén **trước** khi parse JSON/text.
- Một số HTTP client Java hoặc thư viện web có thể tự xử lý content encoding; **không** bọc thêm `GZIPInputStream` lần nữa nếu response đã được giải nén bởi stack HTTP.
- Header nén không xác thực dữ liệu; bảo mật và độ tin cậy kết nối cần công cụ riêng như TLS và policy kiểm tra nội dung.
- Đối với dữ liệu lấy từ mạng, giới hạn output giải nén vẫn rất quan trọng vì content length nén không phải kích thước dữ liệu gốc.

Nên để tầng HTTP/application framework quản lý negotiation và content encoding khi có sẵn, thay vì tự thêm `Accept-Encoding` rồi đoán mọi server đều trả gzip.

## 14. Khi nào nên dùng GZIPInputStream/GZIPOutputStream?

| Tình huống | Hướng tiếp cận |
|---|---|
| Nén một file log thành `.gz` | `Files.newInputStream` → `GZIPOutputStream` |
| Giải nén file `.gz` vào file khác | `GZIPInputStream` → `Files.newOutputStream` |
| Giải nén vài KB vào bộ nhớ | `GZIPInputStream.readAllBytes` nếu biết chắc giới hạn |
| Giải nén file lớn | Vòng lặp buffer và streaming |
| Nhận dữ liệu gzip từ nguồn không tin cậy | Streaming có giới hạn, validate, timeout/quota |
| Nén String UTF-8 | `text.getBytes(UTF_8)` rồi ghi vào gzip |
| Ghi nhiều file có tên vào một archive | `ZipOutputStream`/`ZipFile`, không phải GZIP stream đơn giản |
| Tạo `.tar.gz` | Tạo tar stream trước rồi nén toàn bộ tar bằng GZIP |
| Xử lý HTTP gzip | Dựa vào `Content-Encoding` và khả năng của HTTP stack |
| Muốn giảm file đã là JPEG/MP4/ZIP | Đo trước; gzip thường đem lại ít lợi ích |
| Cần đảm bảo file đích không bị ghi dở | Ghi file tạm, hoàn tất gzip, validate rồi công bố theo chính sách |

## 15. Sai lầm thường gặp

1. **Tưởng GZIP = ZIP.** GZIP không tự cung cấp danh sách named entries và cây thư mục.
2. **Không đóng `GZIPOutputStream`.** Luồng có thể thiếu trailer/byte cuối và không giải nén hợp lệ.
3. **Chỉ `flush()` rồi coi file đã hoàn tất.** `flush` không thay `finish`/`close`.
4. **Gọi `finish()` rồi tiếp tục ghi thêm dữ liệu như thể cùng một gzip member vẫn đang mở.** Member đã hoàn tất; hãy thiết kế định dạng/lifecycle phù hợp.
5. **Đóng underlying output trước khi đóng wrapper gzip.** Wrapper có thể không ghi được trailer.
6. **Đọc không hết stream rồi mặc định CRC đã được kiểm tra.** Kiểm tra trailer phụ thuộc việc đọc đến điểm kết thúc hợp lệ.
7. **Dùng `readAllBytes` với file không tin cậy.** Có nguy cơ decompression bomb hoặc hết heap.
8. **Dùng charset mặc định cho văn bản.** GZIP xử lý byte; phải thống nhất encoding/decoding.
9. **Dựa vào phần mở rộng `.gz` để tin dữ liệu hợp lệ.** Kiểm tra format và giải nén thực tế.
10. **Tưởng hai byte signature đủ chứng minh file hoàn chỉnh.** File có thể bị cắt hoặc CRC sai.
11. **Tin CRC32 có khả năng chống giả mạo.** CRC không phải primitive mật mã.
12. **Dùng GZIP để mã hóa dữ liệu nhạy cảm.** Nén không làm bí mật dữ liệu; cần mã hóa/bảo mật riêng.
13. **Nén trực tiếp vào chính file đang đọc.** Truncate output có thể làm mất input.
14. **Giải nén trực tiếp vào file đích quan trọng.** Khi input lỗi giữa chừng, file đích có thể chứa dữ liệu dang dở.
15. **Không có giới hạn byte giải nén.** File nén nhỏ có thể tạo output rất lớn.
16. **Tưởng file gzip luôn nhỏ hơn file gốc.** Header/DEFLATE overhead có thể làm dữ liệu ngắn hoặc không nén được lớn hơn.
17. **Quên quyền sở hữu stream.** Đóng gzip wrapper thường đóng stream bên dưới; API cần nêu rõ ownership.
18. **Dùng buffer khổng lồ vì nghĩ mới xử lý được file lớn.** Streaming với buffer vừa phải thường phù hợp hơn.
19. **Bỏ qua lỗi `IOException` khi close.** Việc hoàn tất gzip có thể lỗi lúc ghi footer.
20. **Giải nén lại dữ liệu đã được HTTP client tự decode.** Có thể gặp lỗi “not in GZIP format” vì xử lý hai lần.
21. **Cho rằng `flush` đồng nghĩa dữ liệu đã fsync ra đĩa.** Hai tầng trách nhiệm khác nhau.
22. **Lấy số byte nén làm số byte gốc mà không kiểm tra.** Compression ratio không cố định.

## 16. Thiết kế file đầu ra an toàn hơn

Trong hệ thống thực, nén file log hoặc sao lưu quan trọng nên có quy trình:

1. Chọn **file đích riêng** hoặc tạo **file tạm trong cùng thư mục** với đích.
2. Nén theo buffer tới tệp tạm, bảo đảm mọi `write` cần thiết thành công.
3. Đóng `GZIPOutputStream` để hoàn tất footer.
4. Nếu có yêu cầu, kiểm tra lại file gzip hoặc metadata/checksum nghiệp vụ.
5. Chỉ sau khi file đã hoàn chỉnh mới công bố bằng thao tác di chuyển/đổi tên theo khả năng filesystem, hoặc giữ tên output mới độc lập.
6. Dọn temp khi lỗi; có chính sách phục hồi file temp còn sót nếu tiến trình chết bất ngờ.

Không coi rename là giao dịch tự động bền trên mọi filesystem. Mẫu `temp + move` giải quyết rủi ro reader nhìn thấy file bị ghi dở khi thao tác move có tính nguyên tử phù hợp; còn durability qua mất điện và đồng bộ thư mục cần phân tích riêng.

### Với pipeline nhiều lớp filter

Ví dụ ghi văn bản UTF-8 qua writer:

```java
try (Writer writer = new OutputStreamWriter(
        new GZIPOutputStream(Files.newOutputStream(gzipPath)),
        StandardCharsets.UTF_8)) {
    writer.write("Dữ liệu UTF-8\n");
}
```

Đoạn minh họa cần `Writer`, `OutputStreamWriter` và các import tương ứng. Thứ tự đóng: đóng `Writer` → writer đóng gzip → gzip kết thúc member và đóng file output. Đây là cách thuận tiện khi nguồn dữ liệu là ký tự thay vì byte.

Lưu ý `OutputStreamWriter` có encoder charset; không trộn trực tiếp `gzip.write(byte[])` với `writer.write(String)` cùng một luồng khi chưa quản lý bộ đệm/chính sách flush rõ ràng.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `GZIPOutputStream` nhận String hay byte?  
**Nhận byte.** Mã hóa String bằng charset xác định trước khi ghi, hoặc dùng `OutputStreamWriter` bọc gzip.

**Câu 2.** Có thể giải nén file `.gz` bằng `ZipInputStream` rồi lặp `ZipEntry` không?  
**Không nên.** GZIP và ZIP là hai định dạng khác; dùng `GZIPInputStream` cho gzip.

**Câu 3.** Vì sao cần `close()` của GZIPOutputStream?  
**Để hoàn tất dữ liệu nén và trailer** cùng việc đóng stream bên dưới; nếu bỏ qua có thể tạo gzip chưa hoàn chỉnh.

**Câu 4.** `gzip.flush()` có luôn tạo CRC32 trailer và kết thúc file không?  
**Không.** Muốn kết thúc, dùng `finish()` hoặc `close()`.

**Câu 5.** File gzip 50 KB có bảo đảm giải nén ra ít hơn 50 MB không?  
**Không.** Một số dữ liệu có thể nén cực tốt; phải giới hạn output dựa trên số byte đã giải nén.

**Câu 6.** Nếu `GZIPInputStream` đọc được một phần văn bản nhưng chưa tới EOF, CRC trailer đã chắc chắn được kiểm tra chưa?  
**Chưa chắc.** Cần đọc tới điểm kết thúc hợp lệ để kiểm tra toàn vẹn theo định dạng.

**Câu 7.** Hai byte đầu `1F 8B` có đủ để tin nội dung gzip an toàn không?  
**Không.** Đó là signature nhận diện sơ bộ; vẫn phải giải nén, kiểm tra lỗi/trailer và validate dữ liệu ứng dụng.

**Câu 8.** GZIP có mã hóa bảo mật không?  
**Không.** Không được dùng nén thay cho bảo mật hay chữ ký.

**Câu 9.** Một file `.tar.gz` chứa nhiều file bên trong có mâu thuẫn với GZIP là stream không?  
**Không.** Tar là lớp đóng gói nhiều entry thành **một stream**; GZIP nén stream tar đó.

**Câu 10.** Nén JPEG bằng gzip chắc chắn giảm dung lượng?  
**Không.** File JPEG đã nén có thể hầu như không giảm, thậm chí lớn hơn do overhead.

**Câu 11.** Khi giải nén vào file đích quan trọng, cách nào giúp tránh công bố file dở nếu gzip hỏng?  
**Giải nén vào file tạm**, kiểm tra thành công đến EOF rồi mới công bố theo chính sách filesystem phù hợp.

## 18. Tóm tắt

- **`GZIPOutputStream` nén byte sang định dạng GZIP; `GZIPInputStream` giải nén từ định dạng đó.**
- **GZIP là luồng nén, không phải ZIP archive có named entries.** Muốn lưu nhiều file có cấu trúc, chọn ZIP hoặc tar trước khi gzip.
- **Luôn hoàn tất `GZIPOutputStream` bằng `close()` hoặc `finish()`**; `flush()` đơn thuần không thay thế trailer.
- **Dùng streaming với buffer** cho file lớn, và **đặt giới hạn byte giải nén** cho nguồn không tin cậy.
- **CRC32 giúp phát hiện lỗi, không xác thực bảo mật.** Cần validation, hạn mức tài nguyên và cơ chế bảo vệ bổ sung.
- **Charset không nằm trong trách nhiệm của GZIP stream**; văn bản cần encoding/decoding thống nhất.
- Với file quan trọng, **ghi file tạm rồi công bố sau khi hoàn tất** thay vì ghi đè trực tiếp vào đích.

### Tài liệu Java SE 17

- [GZIPInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPInputStream.html)
- [GZIPOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPOutputStream.html)
- [DeflaterOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/DeflaterOutputStream.html)
- [ZipInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipInputStream.html)
- [InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html)
