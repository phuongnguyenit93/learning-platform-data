# finish khác flush và close trong Java: nén và đóng gói dữ liệu

## 1. Ba hành động khác nhau trên một output stream

Các lớp nén và đóng gói trong `java.util.zip` có thể nhận một `OutputStream` bên dưới rồi biến dữ liệu ứng dụng thành ZIP, GZIP hoặc dữ liệu DEFLATE/zlib. Người học thường nhầm ba phương thức:

- **`flush()`**: yêu cầu chuyển các byte đang được đệm theo hợp đồng của stream hiện tại xuống tầng bên dưới. Không đánh dấu định dạng nén đã kết thúc, không đóng stream.
- **`finish()`**: hoàn tất *luồng nén hoặc cấu trúc archive hiện tại*, ghi đủ dữ liệu nén còn lại và metadata cuối cần thiết; **không đóng stream đích bên dưới**.
- **`close()`**: đóng stream nén, thường gọi logic hoàn tất định dạng nếu còn cần, giải phóng tài nguyên và **đóng stream đích được bọc**.

Chỉ gọi `flush()` không khiến một ZIP archive có đủ central directory hay một GZIP member có trailer. Ngược lại, gọi `close()` trên wrapper có thể đóng luôn luồng mà caller hay framework vẫn còn cần sử dụng. `finish()` có ích khi muốn định dạng nén hoàn chỉnh nhưng phải để stream nền tiếp tục mở.

Mục tiêu bài học là xác định đúng vòng đời khi dùng `ZipOutputStream`, `GZIPOutputStream` và `DeflaterOutputStream`; hiểu `ZipOutputStream.closeEntry()`; xây dựng ví dụ Java 17+ chạy được; nhận diện lỗi nén thiếu footer, dùng nhầm quyền sở hữu và nhầm flush với độ bền dữ liệu.

## 2. Một pipeline gồm nhiều tầng

Ví dụ luồng dữ liệu:

~~~text
Application writes bytes
       |
       v
ZipOutputStream / GZIPOutputStream / DeflaterOutputStream
       |    compression / archive metadata
       v
BufferedOutputStream (optional)
       |    Java-side buffering
       v
FileOutputStream / socket OutputStream / ByteArrayOutputStream
       |
       v
Storage / network / memory
~~~

Mỗi tầng quản lý **một kiểu trạng thái khác nhau**. Output của bộ nén có thể chưa tạo đủ byte cuối để dữ liệu thành một archive hợp lệ, dù tầng dưới đã flush mọi byte đang nắm giữ. Ngược lại, sau khi bộ nén finish, tầng dưới vẫn có thể đang mở và còn dữ liệu chưa được lưu bền trên ổ đĩa hay chưa được đối tác mạng xác nhận.

| Yêu cầu | Công cụ phù hợp | Điều không được suy luận |
| --- | --- | --- |
| Muốn đẩy phần đệm nhưng vẫn ghi tiếp | `flush()` | Không có nghĩa archive hoàn tất |
| Muốn ZIP/GZIP hoàn chỉnh nhưng giữ destination mở | `finish()` | Không có nghĩa destination đã đóng |
| Hoàn tất và giải phóng chuỗi stream do mình sở hữu | `close()`, thường qua `try-with-resources` | Không có nghĩa tất cả consumer đã nhận/xử lý |
| Muốn dữ liệu bền trên thiết bị lưu trữ | Giao thức lưu trữ/`FileChannel.force(...)` khi thích hợp | Không phải chỉ gọi `flush()` hoặc `finish()` |
| Muốn chắc consumer đọc thành công | Xác thực archive và acknowledgment của ứng dụng khi cần | Không thay bằng trạng thái close phía gửi |

Vì thế phải trả lời hai câu độc lập: **định dạng đã hoàn chỉnh chưa?** và **ai sở hữu tài nguyên đích?**

## 3. flush() không phải dấu kết thúc dữ liệu nén

`OutputStream.flush()` có tác dụng tùy implementation. Ví dụ `BufferedOutputStream.flush()` chuyển buffer Java xuống stream kế; `DeflaterOutputStream.flush()` có thể chuyển phần dữ liệu đã nén ra ngoài và gọi flush trên output bên dưới.

Với `DeflaterOutputStream` và `GZIPOutputStream`, constructor có tham số `syncFlush=true` để khi flush thực hiện chế độ `Deflater.SYNC_FLUSH`. Nó hỗ trợ việc bên nhận giải nén **một phần luồng đang tiếp diễn**, dù bộ nén chưa nhận tín hiệu kết thúc. Điều này quan trọng với streaming, nhưng có thể giảm tỷ lệ nén nếu flush quá thường xuyên.

Tuy nhiên:

1. `flush()` không đặt tín hiệu *end-of-input* cho bộ nén.
2. `flush()` không viết ZIP central directory để kết thúc toàn archive.
3. `flush()` không bảo đảm ghi GZIP trailer chứa CRC32 và ISIZE.
4. `flush()` không tự giải phóng tài nguyên nén hay đóng destination.
5. `flush()` không thay cho việc yêu cầu dữ liệu bền trên đĩa hoặc TCP acknowledgment.

Đoạn mã minh họa:

~~~java
GZIPOutputStream gzip = new GZIPOutputStream(destination, true);
gzip.write(payloadPart1);
gzip.flush();                // Cho consumer nhận được thêm dữ liệu đang nén.
gzip.write(payloadPart2);   // Vẫn có thể tiếp tục thêm payload.
gzip.finish();               // Chỉ bây giờ mới hoàn tất GZIP member.
~~~

Các biến `destination`, `payloadPart1` và `payloadPart2` phải được khai báo, code cần import và xử lý `IOException`. Đây không phải chương trình độc lập. Nếu muốn đóng destination vì hàm đang sở hữu nó, cần gọi `close()` hoặc có cấu trúc quản lý tài nguyên thích hợp.

**Phân biệt:** `flush()` có thể làm bytes trước mắt giải nén được nhưng **không chứng minh compressed stream đã hợp lệ như một đơn vị hoàn chỉnh**. Một số decoder sẽ chờ hoặc báo EOF bất thường khi trailer/metadata cuối bị thiếu.

## 4. finish(): hoàn tất luồng nén nhưng giữ stream đích mở

`finish()` là tín hiệu **đã viết đủ mọi byte thuộc nội dung nén này**. Bộ nén phải xả phần output cuối, kết thúc compressed stream và ghi metadata phụ thuộc định dạng. Ví dụ:

- `ZipOutputStream.finish()`: hoàn tất ZIP archive, viết central directory và các record kết thúc.
- `GZIPOutputStream.finish()`: hoàn tất DEFLATE payload rồi viết GZIP trailer với checksum và kích thước.
- `DeflaterOutputStream.finish()`: hoàn tất luồng nén từ `Deflater`, đẩy dữ liệu cuối ra bên dưới.

Theo hợp đồng các lớp này, `finish()` **không đóng output stream nền**. Điều đó giúp caller quyết định khi nào đóng destination sau khi xử lý thêm các bước hợp lệ của pipeline.

**Không thể tiếp tục thêm dữ liệu vào cùng compressed stream/ZIP archive sau finish.** Để ghi nội dung còn lại, phải thực hiện nó **trước** finish. Nếu có nhu cầu nhiều compressed messages trên cùng kết nối, cần một giao thức framing hoặc cấu trúc container riêng và các object writer/reader tương ứng. Không giả định nối bytes tùy ý sau ZIP/GZIP đã hoàn thành sẽ được mọi consumer hỗ trợ.

Khi `finish()` ném `IOException`, không được đánh dấu output là thành công. Bộ nén có thể đã ghi phần lớn payload nhưng chưa ghi đủ metadata cuối. Archive có thể bị hỏng ngay cả khi các lệnh `write()` trước đó đã thành công.

## 5. close(): kết thúc vòng đời và truyền thao tác đóng xuống dưới

Với các output stream nén chuẩn trong `java.util.zip`, `close()` thực hiện việc hoàn tất định dạng khi còn cần, đóng stream nén và đóng stream bên dưới theo hợp đồng lớp. Nó còn giúp giải phóng những tài nguyên mà stream nén sở hữu.

Khi **chính hàm mở output file** để tạo ZIP, cách thông thường:

~~~java
Path output = Path.of("archive.zip");
try (ZipOutputStream zip = new ZipOutputStream(
        Files.newOutputStream(output))) {
    zip.putNextEntry(new ZipEntry("hello.txt"));
    zip.write("hello".getBytes(StandardCharsets.UTF_8));
    zip.closeEntry();
} // zip.close() hoàn tất ZIP nếu cần và đóng file stream.
~~~

Đây là đoạn code minh họa cần đặt trong method có xử lý `IOException` và import các lớp tương ứng. Nếu ngay sau khi ghi entry đã định đóng ZIP, **không cần gọi `finish()` tường minh** vì `close()` đã có trách nhiệm hoàn tất.

Tuy nhiên, khi **destination do caller cung cấp** (ví dụ output stream do web framework quản lý), bạn không được tùy tiện đóng nó chỉ vì muốn ZIP hoàn tất. Có thể dùng `finish()` và giao quyền đóng destination cho caller; nếu cần đóng wrapper để giải phóng trạng thái nén nhưng không đóng destination, cần một adapter non-closing có hợp đồng rõ ràng. Phần ownership ở bên dưới trình bày chi tiết.

## 6. ZIP: closeEntry() khác finish() như thế nào?

Một ZIP archive chứa một hoặc nhiều `ZipEntry`. Quy trình thường gặp:

~~~text
putNextEntry("a.txt")
write bytes of a.txt
closeEntry()            [hoàn tất entry thứ nhất]
putNextEntry("b.txt")
write bytes of b.txt
closeEntry()            [hoàn tất entry thứ hai]
finish()                [viết metadata cuối cho cả ZIP archive]
close()                 [đóng stream và stream đích nếu có quyền]
~~~

`ZipOutputStream.closeEntry()` chỉ kết thúc **entry hiện tại**. Đối với entry DEFLATED, code nén/metadata như kích thước và CRC có thể được hoàn tất ở bước này theo ZIP format. Nhưng ZIP có thêm **central directory** ở cuối archive dùng để mô tả các entry và record *End of Central Directory*. Chúng được viết khi `finish()`/`close()` hoàn tất archive.

Vì vậy, một file ZIP đã `closeEntry()` nhưng chưa `finish()` **có thể chưa mở được bằng `ZipFile`** hoặc các công cụ đọc ZIP dựa vào central directory. Không dùng việc `ZipInputStream` đôi khi đọc được entry đầu tiên như bằng chứng toàn archive đã hoàn chỉnh: `ZipInputStream` đọc tuần tự; `ZipFile` cần thông tin thư mục trung tâm.

### Ví dụ xây archive có hai entry

~~~java
ZipOutputStream zip = new ZipOutputStream(destination);

zip.putNextEntry(new ZipEntry("a.txt"));
zip.write("A".getBytes(StandardCharsets.UTF_8));
zip.closeEntry();

zip.putNextEntry(new ZipEntry("b.txt"));
zip.write("B".getBytes(StandardCharsets.UTF_8));
zip.closeEntry();

zip.finish(); // Có central directory; destination vẫn còn mở.
~~~

Đây là đoạn minh họa. `destination` phải là `OutputStream` hợp lệ và các import được cung cấp khi dùng thật. Không thêm entry vào object ZIP đã `finish()`; muốn nhiều file trong **một** ZIP, đưa chúng thành nhiều entries trước khi finish, chứ không nối thêm ZIP khác một cách tùy tiện.

Với `ZipEntry.STORED` (không nén), entry cần thông tin kích thước và CRC phù hợp trước khi ghi theo API, khác với trường hợp `DEFLATED`. Quy định ở mức entry không thay đổi nguyên tắc `closeEntry()` khác `finish()`.

## 7. GZIP: flush không ghi GZIP trailer

Một GZIP member thường có cấu trúc:

~~~text
+-------------+-------------------+------------------+
| GZIP header | DEFLATE payload   | GZIP trailer     |
+-------------+-------------------+------------------+
                                    CRC32 + ISIZE
~~~

`GZIPOutputStream.finish()` hoàn tất compressed data rồi viết trailer. `CRC32` là checksum cho dữ liệu chưa nén; `ISIZE` lưu kích thước chưa nén modulo 2^32. Vì vậy receiver chỉ nên coi member đã hoàn chỉnh khi cấu trúc cuối được ghi và đọc đúng, không chỉ dựa vào `gzip.flush()`.

Khi dùng:

~~~java
GZIPOutputStream gzip = new GZIPOutputStream(destination, true);
gzip.write("hello".getBytes(StandardCharsets.UTF_8));
gzip.flush();  // syncFlush: hữu ích cho streaming, vẫn chưa có trailer kết thúc.
gzip.finish(); // Hoàn tất member và ghi trailer, không đóng destination.
~~~

Đây là mảnh minh họa, không phải chương trình độc lập. Có thể gọi `gzip.close()` sau finish nếu thực sự sở hữu stream đích.

Khác ZIP, GZIP thường đóng gói **một luồng dữ liệu** chứ không có nhiều entry với tên path. Mặc dù có những decoder hỗ trợ ghép nối nhiều GZIP members, không được mặc định mọi consumer hoặc protocol của bạn chấp nhận cách này. Nếu cần gửi nhiều message, định nghĩa framing rõ ràng và kiểm thử receiver.

## 8. DeflaterOutputStream: tầng nén, không phải ZIP container

`DeflaterOutputStream` cung cấp luồng dữ liệu nén bằng `Deflater`. Một `Deflater` mặc định thường tạo luồng zlib-wrapped DEFLATE; `GZIPOutputStream` và `ZipOutputStream` có metadata khác bao quanh DEFLATE.

| Đối tượng writer | Nội dung | Khi finish cần ghi gì |
| --- | --- | --- |
| `DeflaterOutputStream` | Luồng nén do `Deflater` cấu hình, mặc định zlib-wrapped DEFLATE | Kết thúc compressed stream của deflater, gồm trailer/checksum zlib khi áp dụng |
| `GZIPOutputStream` | Một GZIP member | Phần DEFLATE cuối và GZIP trailer |
| `ZipOutputStream` | Một archive nhiều entry ZIP | Metadata kết thúc entry và central directory/end record |

`DeflaterOutputStream.finish()` không thể thay thế `ZipOutputStream.finish()` khi mục tiêu là file ZIP hoàn chỉnh. Cũng không thể lấy bytes của `DeflaterOutputStream` mặc định cho `GZIPInputStream` hoặc `ZipFile` mà mong hai reader tự nhận ra định dạng: zlib, GZIP và ZIP không phải cùng file format.

Với `DeflaterOutputStream`, `syncFlush=true` giúp yêu cầu `Deflater.SYNC_FLUSH` trong `flush()` để streaming có thể tiến triển, nhưng điểm kết thúc chính thức vẫn là `finish()`/`close()`.

## 9. Ví dụ hoàn chỉnh Java 17+: ZIP và GZIP cùng ba phương thức

Chương trình `CompressionLifecycleDemo.java` dùng `ByteArrayOutputStream` làm storage và một `TrackedOutput` để quan sát xem `close()` đã được chuyển xuống destination chưa. Cần tracker vì `ByteArrayOutputStream.close()` là no-op: không thể chỉ hỏi một `ByteArrayOutputStream` còn cho phép truy cập mảng để suy ra wrapper đã đóng luồng hay chưa.

Lưu tệp **`CompressionLifecycleDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

public class CompressionLifecycleDemo {
    private static final byte[] HELLO =
            "hello".getBytes(StandardCharsets.UTF_8);

    static final class TrackedOutput extends FilterOutputStream {
        boolean closed;
        TrackedOutput(OutputStream out) { super(out); }
        @Override public void close() throws IOException {
            try { super.close(); } finally { closed = true; }
        }
    }

    public static void main(String[] args) throws IOException {
        zipExample();
        gzipExample();
    }

    private static void zipExample() throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        TrackedOutput destination = new TrackedOutput(bytes);
        ZipOutputStream zip = new ZipOutputStream(destination);
        zip.putNextEntry(new ZipEntry("hello.txt"));
        zip.write(HELLO);
        zip.closeEntry();
        zip.flush();
        int sizeAfterFlush = bytes.size();
        System.out.println("ZIP flush closed destination: " + destination.closed);
        zip.finish();
        System.out.println("ZIP finish added bytes: " + (bytes.size() > sizeAfterFlush));
        System.out.println("ZIP finish closed destination: " + destination.closed);
        zip.close();
        System.out.println("ZIP close closed destination: " + destination.closed);

        try (ZipInputStream in = new ZipInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            ZipEntry entry = in.getNextEntry();
            System.out.println("ZIP entry: " + entry.getName());
            System.out.println("ZIP content: " +
                    new String(in.readAllBytes(), StandardCharsets.UTF_8));
        }
    }

    private static void gzipExample() throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        TrackedOutput destination = new TrackedOutput(bytes);
        GZIPOutputStream gzip = new GZIPOutputStream(destination, true);
        gzip.write(HELLO);
        gzip.flush();
        int sizeAfterFlush = bytes.size();
        System.out.println("GZIP flush closed destination: " + destination.closed);
        gzip.finish();
        System.out.println("GZIP finish added bytes: " + (bytes.size() > sizeAfterFlush));
        System.out.println("GZIP finish closed destination: " + destination.closed);
        gzip.close();
        System.out.println("GZIP close closed destination: " + destination.closed);

        try (GZIPInputStream in = new GZIPInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            System.out.println("GZIP content: " +
                    new String(in.readAllBytes(), StandardCharsets.UTF_8));
        }
    }
}
~~~

Lệnh biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac CompressionLifecycleDemo.java
java CompressionLifecycleDemo
~~~

Stdout đã được kiểm tra thực tế trên JDK:

~~~text
ZIP flush closed destination: false
ZIP finish added bytes: true
ZIP finish closed destination: false
ZIP close closed destination: true
ZIP entry: hello.txt
ZIP content: hello
GZIP flush closed destination: false
GZIP finish added bytes: true
GZIP finish closed destination: false
GZIP close closed destination: true
GZIP content: hello
~~~

Giải thích:

1. Sau `zip.flush()`, tracker cho thấy destination chưa đóng. Archive khi ấy chưa được bảo đảm có central directory.
2. Sau `zip.finish()`, số byte tăng do metadata kết thúc ZIP được ghi, nhưng `destination.closed` vẫn false.
3. `zip.close()` đóng wrapper và chuyển `close()` tới tracker, khiến flag thành true. Giải nén phần hoàn chỉnh thành công với entry `hello.txt` và text `hello`.
4. Tương tự, `gzip.flush()` (ở đây bật syncFlush) chưa ghi trailer kết thúc member; `gzip.finish()` thêm bytes cuối mà không đóng destination.
5. `gzip.close()` đóng destination; `GZIPInputStream` giải nén thành `hello` sau khi format hoàn chỉnh.
6. Các dòng `finish added bytes: true` là **kết quả cụ thể của ví dụ**. Không suy luận mỗi lần finish ở mọi trạng thái/implementation luôn tăng kích thước đúng như vậy. Điều cần dựa vào là hợp đồng hoàn tất định dạng, không phải số byte cố định.

Demo để từng đối tượng compressed writer có destination riêng. Nó không gửi ra mạng và không đưa bytes chưa finish vào reader rồi kết luận reader phải luôn báo lỗi; chi tiết decoder với input dở dang có thể phụ thuộc cách kiểm tra.

## 10. Ai có quyền đóng destination?

**Quy tắc ưu tiên:** nơi **tạo và sở hữu** resource quyết định khi nào resource được đóng; nơi **mượn** stream phải tuân thủ hợp đồng của caller.

Trường hợp tạo file độc lập:

~~~java
Path file = Path.of("backup.zip");
try (ZipOutputStream zip = new ZipOutputStream(Files.newOutputStream(file))) {
    zip.putNextEntry(new ZipEntry("metadata.txt"));
    zip.write("done".getBytes(StandardCharsets.UTF_8));
    zip.closeEntry();
} // Có quyền đóng, nên try-with-resources phù hợp.
~~~

Đây là mảnh code trong method, cần imports và xử lý IOException. Nếu `close()` thành công, ZIP được kết thúc rồi file output đóng. Nếu close báo lỗi, không được publish file đó như output hợp lệ.

Trường hợp một method chỉ nhận `OutputStream destination`:

~~~java
static void writeZip(OutputStream destination) throws IOException {
    ZipOutputStream zip = new ZipOutputStream(destination);
    zip.putNextEntry(new ZipEntry("note.txt"));
    zip.write("sample".getBytes(StandardCharsets.UTF_8));
    zip.closeEntry();
    zip.finish();
    // Không gọi zip.close() ở đây theo hợp đồng destination là của caller.
}
~~~

Đây là method minh họa. Nó hoàn tất archive nhưng tránh đóng destination của caller. Nhược điểm: wrapper nén không được close ngay; với code production muốn cleanup chắc chắn mà vẫn giữ destination mở, có thể dùng wrapper **non-closing** để zip.close chỉ đóng lớp nén và flush xuống caller, không đóng destination thực.

Adapter minh họa (không thuộc thư viện chuẩn):

~~~java
final class NonClosingOutputStream extends FilterOutputStream {
    NonClosingOutputStream(OutputStream wrapped) { super(wrapped); }

    @Override
    public void close() throws IOException {
        flush(); // Không đóng wrapped.
    }
}
~~~

Khi dùng:

~~~java
try (ZipOutputStream zip =
        new ZipOutputStream(new NonClosingOutputStream(destination))) {
    zip.putNextEntry(new ZipEntry("note.txt"));
    zip.write("sample".getBytes(StandardCharsets.UTF_8));
    zip.closeEntry();
} // zip.close: finish ZIP; adapter close chỉ flush destination.
~~~

Đây cũng là mã minh họa, các biến/import cần phù hợp. Trách nhiệm cuối cùng của caller là flush/close destination vào thời điểm nó sở hữu. Không biến non-closing wrapper thành mặc định cho mọi stream, vì như vậy có thể che giấu resource leak.

Nếu hàm mượn một stream từ servlet/HTTP framework, cần kiểm tra chính sách của framework. Không tự ý đóng HTTP response output nếu framework còn phải ghi framing/headers/body khác. Ngược lại, không bỏ qua lỗi finish trong một response nén: client có thể nhận GZIP/ZIP thiếu cấu trúc cuối dù HTTP status là thành công.

## 11. finish không đồng nghĩa flush xuống ổ đĩa và không bảo đảm transaction

Có ít nhất bốn cột mốc độc lập:

~~~text
Application writes content
          |
          v
Compression finish   -> archive/member có cấu trúc cuối
          |
          v
Output buffer flush  -> bytes được giao cho tầng I/O dưới
          |
          v
OS/storage sync      -> yêu cầu ghi bền dữ liệu theo hợp đồng storage
          |
          v
Application ACK      -> bên nhận/tiêu thụ xác nhận nghiệp vụ
~~~

Thứ tự thật tùy kiến trúc nhưng **không bước nào tự thay thế những bước còn lại**. Đóng một ZIP stream có thể hoàn tất format và đóng file descriptor, nhưng không biến chuỗi cập nhật nhiều tệp thành transaction nguyên tử. `FileChannel.force(true)` được thiết kế cho yêu cầu đồng bộ dữ liệu/metadata của channel, nhưng cũng không tự tạo atomic transaction cho nhiều lần ghi.

Nếu cần xuất tệp ZIP an toàn cho consumer:

1. Tạo file tạm trong nơi dự định lưu trữ.
2. Ghi nội dung qua `ZipOutputStream`.
3. Hoàn tất và đóng writer, xử lý mọi lỗi khi finish/close.
4. Nếu yêu cầu, xác thực archive và yêu cầu durability qua API/lớp storage thích hợp.
5. Chỉ khi đã đạt yêu cầu mới publish tên file chính thức, ví dụ move atomically **khi nền tảng hỗ trợ**.

Không áp dụng move atomic như một lời hứa tuyệt đối trên mọi network filesystem hay provider. Nếu `finish()`/`close()` lỗi, nên xử lý file tạm thất bại và không cập nhật metadata nghiệp vụ thành trạng thái “hoàn thành”.

## 12. Flush trên socket/HTTP: có giúp streaming không?

Trên mạng, `GZIPOutputStream(..., true)` với syncFlush có thể giúp consumer giải nén các byte đã nhận trong lúc luồng vẫn mở. Nhưng thời điểm nhận ở peer còn phụ thuộc network stack, HTTP framing, TLS, flow control và cách receiver đọc. Không có lời hứa rằng mỗi flush tạo một packet hay consumer đã nhìn thấy một message nghiệp vụ hoàn chỉnh.

Với ZIP, nếu định dạng consumer cần central directory thì không được sử dụng `flush()` làm tín hiệu “ZIP tải xuống đã đầy đủ”. Hãy finish archive trước khi kết thúc response. Cũng không nên nối thêm bytes không có framing vào cuối ZIP/GZIP với hy vọng reader sẽ bỏ qua phần dư.

Nếu server gửi nhiều message trên một socket, hãy thiết kế một trong các phương án: length-prefix, các bản ghi được đóng gói theo protocol, hoặc một container nén có các entry rõ ràng. `finish()` của một object không tự định nghĩa message boundary cho mọi protocol.

Một mẹo đo hiệu suất: flush quá nhiều lần trong lúc compression có thể tạo overhead và giảm tỷ lệ nén; chỉ yêu cầu syncFlush khi latency cần thiết, không dựa vào thói quen “gọi flush sau mỗi write”.

## 13. Xử lý ngoại lệ: write thành công không có nghĩa finish thành công

Các bước `finish()` và `close()` cũng phải ghi thêm bytes metadata, nên có thể ném `IOException`/`ZipException`. Ví dụ ổ đĩa đầy đúng lúc ghi central directory thì các entry đã nén vẫn có thể nằm trong file nhưng ZIP không hoàn chỉnh.

Sai:

~~~java
try {
    zip.finish();
} catch (IOException ignored) {
    // Publish ZIP dù finish thất bại: sai.
}
~~~

Đây là đoạn minh họa **anti-pattern**. Cần phát tín hiệu lỗi, cleanup tệp tạm, không chuyển trạng thái thành thành công. Với `try-with-resources`, Java vẫn thử close khi có exception; exception lúc close có thể xuất hiện dưới dạng *suppressed exception* nếu đã có lỗi chính.

Cũng nên giới hạn tài nguyên khi giải nén archive từ nguồn không tin cậy. GZIP/ZIP có thể có tỷ lệ nén cao bất thường; `ZipInputStream` đọc data không giới hạn có thể khiến ứng dụng tốn RAM/thời gian vì decompression bomb. `ByteArrayOutputStream` trong demo chỉ dành cho input nhỏ để kiểm tra round-trip; với file lớn nên dùng streaming và giới hạn đầu ra.

## 14. Lỗi điển hình và cách xử lý

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Chỉ `zip.flush()` rồi publish ZIP | Thiếu central directory | `zip.finish()` hoặc `close()` |
| Chỉ `closeEntry()` cuối cùng | Entry xong, chưa chắc archive xong | `finish()` cho toàn ZIP |
| Chỉ `gzip.flush()` rồi báo hoàn thành | Có thể thiếu GZIP trailer | `finish()`/`close()` |
| Gọi `close()` khi chỉ mượn destination | Đóng tài nguyên do caller sở hữu | `finish()` và quy tắc ownership/non-closing adapter |
| Gọi `finish()` rồi thêm ZIP entry | Sai vòng đời archive | Thêm mọi entry trước khi finish |
| Đóng stream tự mở không được bảo đảm | Có thể rò rỉ resource và output chưa hoàn chỉnh | `try-with-resources` |
| Tưởng `flush()` là fsync | Hiểu sai durability | Cơ chế storage sync riêng |
| Cho rằng flush là ACK từ client | Client có thể chưa nhận hay xử lý | Giao thức xác nhận ứng dụng |
| Luôn bật syncFlush | Tăng overhead, giảm hiệu quả nén | Chỉ bật khi streaming latency cần |
| Nuốt `IOException` của finish/close | Publish archive hỏng | Báo lỗi và cleanup |
| Dùng `ByteArrayOutputStream.close()` để kiểm tra sự lan truyền close | close của BAOS là no-op | Dùng tracking wrapper trong test |
| Đưa zlib bytes vào GZIP/ZIP reader | Sai file format | Dùng đúng reader cho định dạng |
| Nối bytes tùy ý sau ZIP/GZIP | Không portable | Định nghĩa container/framing |

## 15. Câu hỏi tự kiểm tra

1. Gọi `zip.flush()` rồi đọc ZIP bằng `ZipFile` có bảo đảm đọc được toàn archive không? **Không**, central directory có thể chưa tồn tại.
2. `closeEntry()` và `finish()` khác nhau như thế nào? **Một cái hoàn tất entry hiện tại; một cái kết thúc ZIP archive**.
3. `zip.finish()` có đóng stream đích không? **Không**.
4. `zip.close()` có tự hoàn tất ZIP nếu chưa finish không? **Có**, trước khi đóng output.
5. `gzip.flush()` với `syncFlush=true` có ghi CRC32/ISIZE trailer kết thúc member không? **Không**, cần `finish()`/`close()`.
6. Trailer của GZIP chứa gì? **CRC32 và ISIZE** của dữ liệu chưa nén (ISIZE modulo 2^32).
7. Có thể gọi `putNextEntry()` sau `zip.finish()` không? **Không**; archive đã kết thúc.
8. Hàm nhận output do framework quản lý có nên luôn close `ZipOutputStream` bọc trực tiếp output đó không? **Không mặc định**; cần tuân thủ ownership, có thể finish hoặc dùng non-closing adapter.
9. Trong code tự tạo ZIP file, `try-with-resources` có đủ để hoàn tất archive và đóng file không? **Có**, nếu close thành công.
10. Vì sao finish có thể lỗi dù write trước đó thành công? **Footer/central directory vẫn cần được ghi ra destination**.
11. `flush()` bảo đảm dữ liệu bền trên SSD chưa? **Không**; cần hợp đồng durability riêng.
12. Vì sao demo cần `TrackedOutput`? Vì close của `ByteArrayOutputStream` không cho ta biết wrapper đã gọi close tới stream bên dưới hay chưa.
13. `GZIPOutputStream` và `ZipOutputStream` có cùng định dạng byte không? **Không**, dù cùng có thể dùng thuật toán DEFLATE.
14. Có nên coi file nén đã hợp lệ nếu giải nén được một phần payload? **Không**, cần hoàn tất format và xác thực toàn bộ theo yêu cầu.
15. Nếu cần nhiều message trên cùng socket thì chỉ việc finish một ZIP/GZIP và nối thêm bytes khác là đủ chưa? **Chưa**, protocol phải quy định framing và reader tương thích.

## Tài liệu API tham khảo

- [Java SE 17 — ZipOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipOutputStream.html): `putNextEntry`, `closeEntry`, `finish`, `close`.
- [Java SE 17 — GZIPOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPOutputStream.html): `finish`, constructor `syncFlush` và metadata GZIP.
- [Java SE 17 — DeflaterOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/DeflaterOutputStream.html): `finish`, `flush`, `close` và `Deflater.SYNC_FLUSH`.
- [Java SE 17 — OutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html): hợp đồng `flush()` và `close()`.
- [Java SE 17 — ZipInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipInputStream.html), [ZipFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipFile.html), [GZIPInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPInputStream.html): đọc và xác minh định dạng.
