# Phạm vi Java Core I/O và khác biệt theo phiên bản JDK

> **Ngữ cảnh:** Java Core – I/O, thuộc nhóm **Tổng quan I/O**. Bài học xác định phần I/O nào thuộc Java SE, cách chọn API theo loại dữ liệu và những khác biệt cần kiểm tra khi chạy hoặc biên dịch với các phiên bản JDK. Những mốc bên dưới là thay đổi tiêu biểu, không phải danh mục đầy đủ mọi thay đổi của từng bản JDK.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận diện các gói Java SE cung cấp I/O, phân biệt chúng với framework hay thư viện bên ngoài.
- Chọn giữa luồng **byte**, luồng **ký tự**, thao tác **tệp/đường dẫn**, **channel/buffer** và cơ chế blocking/asynchronous.
- Nhận biết API có sẵn ở Java 8, mới xuất hiện từ Java 9/10/11/12, cùng thay đổi **charset mặc định** từ JDK 18.
- Viết mã đọc/ghi tệp có charset tường minh, đóng tài nguyên đúng và kiểm tra biên dịch theo phiên bản Java mục tiêu.
- Hiểu sự khác nhau giữa API được phép dùng lúc biên dịch, môi trường runtime và tác động của virtual threads trong JDK 21.

## 2. Phạm vi Java Core I/O là gì?

**I/O (Input/Output)** là hoạt động nhận dữ liệu hoặc xuất dữ liệu ra ngoài phần tính toán: tệp, bộ nhớ, thiết bị chuẩn, kết nối mạng và hệ thống tệp. Ở đây **Java Core** chỉ API chuẩn trong Java SE do JDK cung cấp; bạn không cần thêm dependency Maven/Gradle để dùng các lớp sau.

| API chuẩn | Công dụng chính | Ví dụ |
| --- | --- | --- |
| `java.io` | Byte stream, character stream, buffering, dữ liệu nguyên thủy, serialization | `InputStream`, `OutputStream`, `Reader`, `Writer`, `BufferedReader`, `DataInputStream` |
| `java.nio` | Buffer và những cấu trúc dữ liệu hỗ trợ I/O | `ByteBuffer` |
| `java.nio.channels` | Channel, truy cập theo vị trí, I/O không chặn cho những channel hỗ trợ | `FileChannel`, `SocketChannel`, `Selector` |
| `java.nio.file`, `java.nio.file.attribute` | Đường dẫn, đọc/ghi tệp, quản lý thư mục, file metadata | `Path`, `Files`, `FileVisitor`, `BasicFileAttributes` |
| `java.nio.charset` | Quy tắc mã hóa byte ↔ ký tự | `Charset`, `StandardCharsets`, `CharsetDecoder` |
| `java.util.zip` | Nén/giải nén trên các luồng | `ZipInputStream`, `GZIPOutputStream` |

Các luồng chuẩn `System.in`, `System.out` và `System.err` cũng thuộc Java SE; `System.out` là `PrintStream`. I/O mạng có API chuẩn `java.net`, nhưng phân tích socket/HTTP chi tiết thuộc chủ đề networking. JDBC, servlet container, Spring Web và những lớp tiện ích của framework không phải là API Java Core I/O chỉ vì chúng cũng đọc/ghi dữ liệu.

### 2.1. Byte stream, character stream và file API

- **Byte stream** (`InputStream`/`OutputStream`) làm việc với byte thô: ảnh, PDF, ZIP, protocol nhị phân. `InputStream.read()` trả giá trị 0–255 hoặc `-1` lúc hết dữ liệu; `read(byte[])` có thể trả số byte ít hơn độ dài buffer.
- **Character stream** (`Reader`/`Writer`) làm việc với ký tự. Khi kết nối với tệp hay socket, byte phải được giải mã theo charset; một ký tự Unicode có thể chiếm nhiều byte UTF-8. Ví dụ `InputStreamReader` nối một byte stream với reader.
- **`Path` và `Files`** quản lý đường dẫn và filesystem: tạo, đọc, ghi, di chuyển, kiểm tra thuộc tính tệp. `Path.of("data.txt")` chỉ tạo đường dẫn tương đối, không tạo tệp và không kiểm tra tệp tồn tại. `java.io.File` là API cũ, có thể chuyển sang `Path` bằng `file.toPath()`.
- **Channel/Buffer** hỗ trợ dữ liệu theo khối, truy cập vị trí bất kỳ, non-blocking với channel thích hợp và các lựa chọn nâng cao. Không phải lớp nào trong gói `java.nio` cũng non-blocking: `Files.readAllBytes` vẫn chặn trong khi đọc.
- **NIO.2** gồm API `Path`, `Files`, `WatchService`, `AsynchronousFileChannel` có từ **Java 7**; không cần chờ Java 11 hay 21 mới có.

### 2.2. Nguyên tắc chung không phụ thuộc phiên bản JDK

I/O có thể thất bại do tệp không tồn tại, thiếu quyền, hỏng thiết bị, thiếu chỗ lưu, đường dẫn không hợp lệ hay lỗi mạng; xử lý `IOException` theo chính sách ứng dụng. Đóng `InputStream`, `Reader`, `Writer`, `FileChannel` và stream do `Files.list`/`Files.walk`/`Files.lines` trả về khi xong việc; thường dùng **try-with-resources**. Với dữ liệu lớn, tránh nạp toàn bộ vào RAM bằng `readAllBytes` hoặc `readString`; xử lý từng dòng hoặc dùng buffer có kích thước cố định.

Phân biệt **blocking I/O** (lời gọi có thể chờ dữ liệu) với non-blocking/asynchronous I/O (có cơ chế theo dõi tiến triển mà không chặn kiểu cũ). Tên gói `nio` không đủ để quyết định cơ chế thực thi.

## 3. Bảng mốc phiên bản JDK quan trọng

| Phiên bản | API/thay đổi tiêu biểu | Ý nghĩa |
| --- | --- | --- |
| **Java 7** | NIO.2: `Path`, `Files`, `WatchService`, `AsynchronousFileChannel`; try-with-resources | Nền tảng file API hiện đại và cơ chế tự đóng tài nguyên đã có từ trước Java 8. |
| **Java 8** | `Files.lines`, `Files.list`, `Files.walk`, `Files.find` | Phối hợp file/directory API với Stream API; stream giữ tài nguyên phải đóng đúng cách. |
| **Java 9** | `InputStream.readAllBytes()`, `readNBytes(byte[],int,int)`, `transferTo(OutputStream)`; `javac --release` | Thao tác stream thuận tiện hơn, kiểm tra API mục tiêu khi biên dịch. |
| **Java 10** | `Reader.transferTo(Writer)` | Sao chép nội dung ký tự từ reader sang writer gọn hơn. |
| **Java 11 (LTS)** | `Path.of(...)`, `Files.readString`, `Files.writeString`, `InputStream.readNBytes(int)`, `InputStream.nullInputStream()` | API thao tác chuỗi/tệp/byte đơn giản hơn nhưng không có trên Java 8. |
| **Java 12** | `Files.mismatch(Path,Path)`, `InputStream.skipNBytes(long)` | Tìm vị trí byte đầu tiên khác giữa hai tệp; bỏ qua đúng lượng byte nếu có đủ. |
| **Java 17 (LTS)** | Baseline triển khai phổ biến, kế thừa những API ở trên | Không được suy ra rằng mọi API I/O hay charset mặc định đều mới đổi ở Java 17. |
| **Java 18** | **JEP 400: UTF-8 by Default** | Các Java SE API dựa vào default charset dùng UTF-8 theo cấu hình mặc định; có thể thay đổi hành vi so với JDK 8/11/17. |
| **Java 21 (LTS)** | **Virtual threads** chính thức theo JEP 444 | Có lựa chọn mở rộng số tác vụ chờ I/O đồng thời; không thay thế toàn bộ `Files`/`InputStream`. |

**Hai cách kiểm tra khác nhau:** Nếu dự án nhắm Java 8 thì một lời gọi chỉ có từ Java 11 **không hợp lệ ở bước biên dịch với API Java 8**. Ngược lại, cùng source đã biên dịch vẫn có thể đổi hành vi khi nâng **runtime**, ví dụ lúc dùng charset mặc định.

## 4. Charset và khác biệt trước/sau JDK 18

Dữ liệu trong tệp gồm **byte**, còn `String`/`Reader` biểu diễn **ký tự**. Khi chuyển đổi, chương trình phải dùng charset như UTF-8. Nếu người ghi mã hóa theo UTF-8 nhưng người đọc giải mã theo charset khác, tiếng Việt có thể lỗi hoặc thao tác đọc báo dữ liệu không hợp lệ.

- **JDK 17 trở về trước:** `Charset.defaultCharset()` thường phụ thuộc hệ điều hành/locale/cấu hình; cùng một chương trình có thể chạy khác nhau trên các máy.
- **Từ JDK 18:** JEP 400 quy định **UTF-8 là charset mặc định của Java SE API liên quan theo cấu hình mặc định**. Không có nghĩa mọi byte bên ngoài đều UTF-8, hay nâng runtime sẽ tự chuyển mã tệp cũ.
- **Ngoại lệ rất quan trọng:** Một số overload `Files` đã **quy định UTF-8 độc lập với charset mặc định** từ trước JDK 18, chẳng hạn `Files.newBufferedReader(path)`, `Files.newBufferedWriter(path)`; từ Java 11 có `Files.readString(path)`/`writeString(path, text)` cũng dùng UTF-8. Trong khi đó `new InputStreamReader(input)`, `new String(bytes)` và `text.getBytes()` (không đối số charset) phụ thuộc vào default charset.
- Muốn hành vi ổn định giữa JDK/OS, dùng overload có `StandardCharsets.UTF_8`: `new InputStreamReader(input, StandardCharsets.UTF_8)`, `new String(bytes, StandardCharsets.UTF_8)`, `text.getBytes(StandardCharsets.UTF_8)` và `Files.readString(path, StandardCharsets.UTF_8)`.
- Với kho dữ liệu lịch sử dùng charset khác, phải xác định **charset thật** trước khi di chuyển; ép UTF-8 khi đọc dữ liệu cũ không làm byte tự đổi thành UTF-8.

**Ví dụ không nên phụ thuộc default charset:** đọc byte từ tệp cũ rồi gọi `new String(bytes)`. Kết quả có thể khác giữa Java 8/17 và Java 18/21. Cách đúng là biết charset ghi của tệp và truyền charset đó khi decode.

## 5. Ví dụ Java 8: API tệp và UTF-8 ổn định

Tạo **`IoJava8.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class IoJava8 {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("io-java8-", ".txt");
        try {
            byte[] data = "Xin chào Java".getBytes(StandardCharsets.UTF_8);
            Files.write(file, data);

            byte[] restored = Files.readAllBytes(file);
            System.out.println(new String(restored, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac IoJava8.java
java IoJava8
~~~

Stdout chính xác:

~~~text
Xin chào Java
~~~

`Files.createTempFile` tạo một tệp tên ngẫu nhiên và `finally` cố xóa tệp sau khi dùng, kể cả có lỗi. `Files.write` ghi byte nên không liên quan charset mặc định; charset được chọn khi chuyển `String` sang byte và ngược lại. Ví dụ này chạy được trên **Java 8** và JDK mới hơn, vì chỉ dùng các API có sẵn từ Java 7–8. Dùng `readAllBytes` ở đây vì nội dung nhỏ; không lấy nó làm mẫu đọc tệp nhiều gigabyte.

## 6. Ví dụ Java 11+: `Files.readString` và `Files.writeString`

Tạo **`IoJava11.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class IoJava11 {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("io-java11-", ".txt");
        try {
            Files.writeString(file, "Dữ liệu UTF-8\n", StandardCharsets.UTF_8);
            String text = Files.readString(file, StandardCharsets.UTF_8);
            System.out.print(text);
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac IoJava11.java
java IoJava11
~~~

Stdout:

~~~text
Dữ liệu UTF-8
~~~

`Files.writeString/readString` có từ **JDK 11**. Không dùng đoạn code này khi dự án vẫn target Java 8. `Files.readString` đọc toàn bộ file trong một lần, có thể tốn bộ nhớ nếu file lớn; nó quản lý việc mở/đóng file nội bộ. `Files.writeString` nếu không truyền `OpenOption` sẽ tạo file nếu cần và ghi đè nội dung cũ; cần chỉ rõ yêu cầu “append” hay “overwrite” trong ứng dụng thật.

Với tệp văn bản lớn, **Java 8 cũng có** `Files.newBufferedReader` để đọc từng dòng:

~~~java
// Minh họa đặt bên trong một phương thức có thể ném IOException.
// path là biến Path chỉ tới một tệp văn bản UTF-8.
try (java.io.BufferedReader reader =
         java.nio.file.Files.newBufferedReader(
             path, java.nio.charset.StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý dòng tại đây; không gom toàn bộ nội dung vào List/String.
    }
}
~~~

Đây là **fragment minh họa**, chưa phải chương trình độc lập vì `path` và phần xử lý dòng do người gọi cung cấp. `readLine` loại bỏ ký tự kết thúc dòng, cần lưu ý nếu phải giữ nguyên định dạng tệp.

## 7. Sao chép luồng byte: Java 8 và Java 9

Để sao chép nội dung nhị phân, đừng biến nó thành `String`. Với Java 8:

~~~java
// in là InputStream và out là OutputStream đã mở.
byte[] buffer = new byte[8192];
int n;
while ((n = in.read(buffer)) != -1) {
    out.write(buffer, 0, n);
}
~~~

Giá trị `n` là **số byte thực đọc**. Viết `out.write(buffer)` thay vì `out.write(buffer,0,n)` có thể ghi lại byte thừa từ lần đọc trước, đặc biệt ở lần cuối. Caller chịu trách nhiệm đóng `in` và `out` đúng cách.

Từ Java 9, có thể rút ngắn:

~~~java
// in: InputStream, out: OutputStream (API từ Java 9).
long count = in.transferTo(out);
~~~

`InputStream.transferTo` sao chép toàn bộ byte còn lại và trả số byte đã chuyển, **không tự đóng** hai stream. `InputStream.readAllBytes()` cũng từ Java 9 nhưng đọc toàn bộ vào RAM. `InputStream.readNBytes(byte[],off,len)` từ Java 9 cố đọc đến đủ số lượng yêu cầu hoặc EOF; khác với `read(byte[])` có thể trả ít hơn dù chưa EOF. Những lựa chọn này không loại bỏ nhu cầu xử lý `IOException`.

## 8. Chọn API theo công việc, không chỉ theo phiên bản

| Công việc | API nên cân nhắc | Lưu ý |
| --- | --- | --- |
| Đọc văn bản nhỏ, JDK 11+ | `Files.readString(path, UTF_8)` | Dễ hiểu, tránh phụ thuộc charset hệ thống; nạp cả tệp vào RAM. |
| Ghi văn bản nhỏ, JDK 11+ | `Files.writeString(path, text, UTF_8)` | Quy định rõ tạo tệp, overwrite, append bằng `OpenOption` khi cần. |
| Đọc văn bản lớn, kể cả Java 8 | `Files.newBufferedReader(path, UTF_8)` | Dùng try-with-resources, xử lý từng dòng. |
| Đọc/ghi ảnh, ZIP, nhị phân | `InputStream`/`OutputStream` hoặc `Files.newInputStream`/`newOutputStream` | Sao chép byte nguyên vẹn, không decode làm text. |
| Liệt kê/duyệt thư mục | `Files.list`, `Files.walk` hoặc `Files.walkFileTree` | Xử lý quyền, symlink, lỗi; đóng stream khi cần. |
| Vị trí bất kỳ trong tệp | `FileChannel` hoặc `RandomAccessFile` | Quản lý vị trí/buffer; không đồng nghĩa với async. |
| Hàng nghìn socket đang chờ | Channel/selector hoặc mô hình thread phù hợp | Là thiết kế networking/concurrency, cần benchmark workload thật. |
| Triển khai Java 8 | `Files`/`Path`/buffered streams API có trước Java 9 | Không vô tình dùng `readString` hoặc `transferTo` mới. |

`Files.lines(path)` trả về một `Stream<String>` có thể đọc theo tiến trình và phải đóng để giải phóng tài nguyên; `Files.readAllLines(path)` đọc toàn bộ dòng vào `List<String>`. Stream API **không làm I/O tự động non-blocking**. Cũng không nên coi `Files.readAllBytes` là phương pháp tối ưu chỉ vì hàm ngắn.

## 9. API compatibility và runtime compatibility

### 9.1. Biên dịch theo API mục tiêu

Nếu phân phối ứng dụng chạy trên Java 8, kiểm tra không dùng method mới hơn. Trên `javac` hỗ trợ `--release` (JDK 9+), biên dịch ví dụ Java 8 như sau:

~~~bash
javac --release 8 IoJava8.java
java IoJava8
~~~

Nếu cố `javac --release 8 IoJava11.java`, biên dịch lỗi vì `Files.readString/writeString` không tồn tại trong API Java 8. `--release` giới hạn level ngôn ngữ, bytecode và Java SE API để build phù hợp target. Nó không thay cho chạy test bằng runtime Java 8 thật, nhất là với permission, OS/file system provider và dữ liệu thực.

### 9.2. Kiểm tra runtime và môi trường

Nâng từ JDK 8/11/17 lên 21 có thể không đụng tới API trong source nhưng vẫn lộ lỗi do **charset mặc định đã đổi ở JDK 18**, đường dẫn tương đối, working directory, quyền trên tệp, symbolic link và tương tác với file system. Cần thử cả dữ liệu tiếng Việt, tên tệp Unicode, empty file, file thiếu/quá lớn và tình huống thất bại khi đọc/ghi.

Các lệnh định danh môi trường:

~~~bash
java -version
javac -version
~~~

Trong Gradle/Maven, đừng nhầm **JDK dùng để chạy build tool**, **JDK/toolchain biên dịch**, **release/API đích** và **runtime production**. Chúng có thể khác nhau. Thiết lập cụ thể phải tương ứng JDK mục tiêu, rồi chạy test trong môi trường triển khai thực tế.

## 10. Virtual threads trong Java 21 ảnh hưởng gì tới I/O?

Java 21 chính thức hóa **virtual threads** (JEP 444), giúp ứng dụng có nhiều tác vụ đồng thời đang chờ I/O dùng tài nguyên thread hiệu quả hơn trong các tình huống được runtime hỗ trợ. Nhưng điều này **không làm tệp hay mạng nhanh hơn**, không biến `Files.readString` thành API trả `Future` và không bắt buộc thay toàn bộ code cũ.

Một virtual thread có thể tạm nhường carrier thread khi blocking I/O được runtime hỗ trợ; vẫn phải xem xét thao tác trong `synchronized` hoặc native call, vì ở JDK 21 có tình huống **pinning** làm carrier bị giữ trong lúc chờ. Các lựa chọn **NIO selector**, **AsynchronousFileChannel** và **virtual threads** phục vụ mô hình đồng thời khác nhau, lựa chọn theo workload. Với bài học tổng quan này, trọng tâm vẫn là chọn loại dữ liệu, charset, xử lý lỗi và đóng tài nguyên; threading có bài chuyên sâu riêng.

## 11. Lỗi phổ biến

1. **“NIO luôn non-blocking.”** Sai: `Files.readAllBytes` có thể blocking. Xem hợp đồng method/channel cụ thể.
2. **“Một lần `read(buffer)` nhận đủ buffer.”** Sai: dùng số byte trả về; `-1` là EOF.
3. **“Dùng Reader sao chép ZIP cũng được.”** Sai: decode text có thể làm thay đổi byte gốc.
4. **“Charset hệ thống luôn là UTF-8.”** Không đúng với mọi JDK/cấu hình; chọn charset tường minh.
5. **“Nâng lên JDK 21 sẽ đọc đúng tệp mã hóa cũ.”** Không: cần biết encoding thực tế của dữ liệu lưu.
6. **“Files.lines/list/walk không cần đóng.”** Các stream này có thể giữ tài nguyên hệ thống; dùng try-with-resources.
7. **“readAllBytes thích hợp mọi kích thước tệp.”** Có nguy cơ thiếu heap; dùng buffer/dòng khi dữ liệu lớn.
8. **“Method có mặt trên máy JDK 21 tức chạy được trên Java 8.”** Kiểm tra `--release 8` và runtime mục tiêu.
9. **“Ghi string sẽ tự append.”** `Files.writeString` mặc định ghi đè nội dung; cần xác định open options.
10. **“Path.of tạo tệp ngay.”** Nó chỉ tạo đối tượng đường dẫn. Path tương đối còn phụ thuộc working directory.
11. **“I/O thất bại luôn không để lại dữ liệu.”** Có thể đã đọc/ghi một phần trước lỗi; xác định chiến lược cleanup, backup, ghi tạm + replace khi cần nguyên tử.

## 12. Tự kiểm tra

1. Nên dùng `InputStream` hay `Reader` để copy ảnh PNG? Vì sao?
2. Vì sao project target Java 8 không biên dịch được `Files.readString`?
3. Vòng lặp `read(buffer)` cần ghi bao nhiêu byte mỗi lần?
4. JDK nào thay đổi default charset sang UTF-8, và điều đó có tự giải quyết dữ liệu lưu theo charset cũ không?
5. `Files.lines` và `Files.readAllLines` khác nhau ở thời điểm nạp dữ liệu, bộ nhớ và quản lý tài nguyên thế nào?

**Gợi ý đáp án:** (1) byte stream để giữ nguyên byte; (2) method bắt đầu từ Java 11; (3) đúng số byte `n` trả về; (4) JDK 18, không tự chuyển mã tệp; (5) lazy stream cần đóng so với `List` chứa toàn bộ dòng.

## Tài liệu chuẩn để đối chiếu theo JDK

- [Oracle Java SE 11: InputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/InputStream.html) — kiểm tra mục “Since” cho `readAllBytes`, `readNBytes`, `transferTo`.
- [Oracle Java SE 11: Files](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html) — overload đọc/ghi chuỗi và UTF-8.
- [Oracle Java SE 21: Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html) — hợp đồng file API trên JDK hiện đại.
- [OpenJDK JEP 400 – UTF-8 by Default](https://openjdk.org/jeps/400) — thay đổi từ JDK 18.
- [OpenJDK JEP 444 – Virtual Threads](https://openjdk.org/jeps/444) — phiên bản JDK 21 và mối quan hệ với blocking I/O.

**Quy tắc thực hành:** lựa chọn API dựa vào **loại dữ liệu**, **kích thước**, **charset**, **cơ chế đồng thời** và **JDK tối thiểu**. Khi nâng JDK, kiểm tra cả API lúc biên dịch lẫn hành vi runtime; nguyên tắc xử lý lỗi và đóng tài nguyên vẫn luôn cần thiết.