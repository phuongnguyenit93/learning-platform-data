# Bảng trách nhiệm đóng tài nguyên theo từng API trong Java I/O

## 1. Cách đọc bảng: ai mở, ai đóng?

Trong Java, **quyền sở hữu tài nguyên (resource ownership)** quyết định thành phần nào chịu trách nhiệm gọi **close()**. Một đối tượng có phương thức close() chưa đủ để kết luận rằng đoạn mã đang sử dụng nó được phép đóng: đối tượng có thể được tạo tại đây, được mượn từ bên ngoài hoặc được chuyển giao quyền sở hữu theo hợp đồng API.

| Tình huống | Ai phải đóng? | Nguyên tắc |
|---|---|---|
| Phương thức tự mở file, socket, channel, directory stream… | Phương thức đã mở | Dùng try-with-resources để đóng trên mọi đường đi, kể cả khi có ngoại lệ. |
| Phương thức **nhận** một InputStream, OutputStream, Reader, Writer… do caller truyền vào | Thông thường caller | Callee dùng rồi trả lại; chỉ đóng khi API công khai rằng nó nhận quyền sở hữu. |
| Phương thức trả về một đối tượng còn giữ tài nguyên đang mở | Caller nhận kết quả | Viết rõ trong hợp đồng rằng caller phải đóng; tránh trả về tài nguyên ẩn, khó theo dõi. |
| Đặt wrapper quanh stream/channel | Bên sở hữu wrapper **và** tài nguyên nền theo hợp đồng | Đóng wrapper thường đóng luôn tài nguyên nền. Nếu nền là tài nguyên mượn, không tự ý đóng wrapper. |
| API đọc/ghi trọn vẹn trong một lời gọi, chỉ trả về dữ liệu/Path/kết quả | Chính API | Không còn đối tượng tài nguyên để caller đóng; việc xóa file hoặc dọn dữ liệu là trách nhiệm khác. |

**Quy tắc mặc định để tra cứu nhanh:** nếu mã của bạn tự tạo tài nguyên có vòng đời mở/đóng, hãy đưa nó vào try-with-resources; nếu chỉ được truyền vào một tài nguyên có sẵn, **không đóng** khi chưa có hợp đồng chuyển giao. Các ngoại lệ cụ thể cần đọc theo từng API ở dưới.

## 2. Bảng tra cứu java.io: stream, reader, writer và wrapper

| API hoặc cách tạo | Chủ sở hữu thông thường | Cần làm khi xong? | Tác động và lưu ý |
|---|---|---|---|
| **new FileInputStream(file)**, **new FileOutputStream(file)** | Mã gọi constructor | **close()** | Giải phóng file descriptor; OutputStream.close() đóng luồng ghi, không thay thế cơ chế bảo đảm dữ liệu đã bền vững trên đĩa. |
| **new FileReader(file, charset)**, **new FileWriter(file, charset)** | Mã mở file | **close()** | Đóng reader/writer và tài nguyên file; chỉ rõ charset nếu nội dung cần tái lập ổn định. |
| **new BufferedInputStream(input)**, **new BufferedOutputStream(output)** | Mã sở hữu wrapper theo hợp đồng | **close() wrapper** | Đóng wrapper sẽ đóng stream nền; với luồng ghi, close() còn flush dữ liệu được đệm. |
| **new BufferedReader(reader)**, **new BufferedWriter(writer)** | Mã sở hữu wrapper | **close() wrapper** | Đóng wrapper kéo theo đóng reader/writer bên dưới; với writer, cần đóng hoặc flush để đẩy dữ liệu đệm. |
| **new InputStreamReader(input, charset)**, **new OutputStreamWriter(output, charset)** | Mã sở hữu wrapper | **close() wrapper** | Đóng tầng chuyển đổi byte ↔ ký tự và đóng stream nền. |
| **new DataInputStream(input)**, **new DataOutputStream(output)** | Mã sở hữu wrapper | **close() wrapper** | Đóng stream nền; close() của DataOutputStream cũng kết thúc đường ghi. |
| **new ObjectInputStream(input)**, **new ObjectOutputStream(output)** | Mã sở hữu wrapper | **close() wrapper** | Đóng stream nền; phải hoàn tất/flush chuỗi đối tượng ghi ra trước khi kết thúc. Không dùng ObjectOutputStream cho dữ liệu Java Serialization không đáng tin. |
| **new PrintStream(output)**, **new PrintWriter(writer/output)** | Mã sở hữu wrapper | **close() nếu sở hữu đầu ra** | Đóng wrapper sẽ đóng đích ghi. Hai lớp này có thể ghi nhận lỗi thay vì ném IOException trong một số thao tác; kiểm tra **checkError()** khi cần phát hiện lỗi ghi. |
| **new RandomAccessFile(file, mode)** | Mã mở file | **close()** | Giải phóng file; **getChannel()** trả về channel liên kết cùng file, đóng một phía có thể ảnh hưởng phía còn lại. |
| **new ByteArrayInputStream(bytes)**, **new ByteArrayOutputStream()** | Mã tạo đối tượng | Không có handle hệ điều hành bắt buộc đóng | close() không có tác dụng đối với hai lớp này; cần phân biệt với các wrapper có tài nguyên nền thật. |
| **new StringReader(text)**, **new StringWriter()** | Mã tạo đối tượng | Không có file/socket cần giải phóng | StringReader.close() đánh dấu đóng, đọc tiếp không hợp lệ; StringWriter.close() không có tác dụng. Không suy từ hai lớp này ra toàn bộ Reader/Writer. |

Ví dụ, đóng BufferedReader được tạo từ FileReader sẽ lan xuống FileReader; không cần đóng từng lớp riêng theo cách thủ công. Ngược lại, một BufferedWriter bọc **System.out** không được tự ý đóng, vì hành động đó sẽ đóng luôn stream chuẩn đang được các thành phần khác sử dụng.

## 3. Bảng tra cứu java.nio.file.Files

Phân biệt **phương thức trả về tài nguyên mở** với **phương thức tự thực hiện toàn bộ I/O rồi trả dữ liệu**.

| API | Kết quả | Trách nhiệm đóng |
|---|---|---|
| **Files.newInputStream(path)**, **Files.newOutputStream(path)** | InputStream/OutputStream đang mở | **Caller đóng** stream trả về. |
| **Files.newBufferedReader(path, charset)**, **Files.newBufferedWriter(path, charset, options…)** | BufferedReader/BufferedWriter đang mở | **Caller đóng** reader/writer trả về. |
| **Files.newByteChannel(path, options…)** | SeekableByteChannel đang mở | **Caller đóng** channel. |
| **Files.newDirectoryStream(dir)**, biến thể có glob/filter | DirectoryStream đang mở | **Caller đóng** sau khi duyệt; kể cả khi ngừng duyệt sớm hoặc xảy ra lỗi. |
| **Files.lines(path, charset)** | Stream&lt;String&gt; gắn với file đang mở | **Caller đóng Stream** bằng try-with-resources. count(), forEach(), findFirst()… **không tự đóng** nguồn. |
| **Files.list(dir)** | Stream&lt;Path&gt; có thể giữ tài nguyên thư mục | **Caller đóng Stream**. |
| **Files.walk(start, …)**, **Files.find(start, …)** | Stream&lt;Path&gt; duyệt cây thư mục | **Caller đóng Stream**; nguồn có thể giữ các directory handle trong lúc duyệt. |
| **Files.readAllBytes(path)**, **Files.readAllLines(path, charset)**, **Files.readString(path, charset)** | byte[], List&lt;String&gt;, String | API tự quản lý I/O bên trong; **caller không có stream phải đóng**. Cân nhắc bộ nhớ nếu file lớn. |
| **Files.write(path, bytes/lines, …)**, **Files.writeString(path, text, charset, …)** | Path | API tự mở/đóng tài nguyên nội bộ; **caller không phải đóng Path**. |
| **Files.copy(sourcePath, targetPath, …)**, **Files.move(source, target, …)** | Path | API tự quản lý handle nội bộ; không có stream trả về để đóng. |
| **Files.copy(inputStream, targetPath, …)** | long (số byte) | API **không đóng inputStream** do caller truyền vào; caller giữ trách nhiệm. |
| **Files.copy(sourcePath, outputStream)** | long (số byte) | API **không đóng outputStream** do caller truyền vào; caller giữ trách nhiệm. |
| **Files.walkFileTree(start, visitor)** | Path | API quản lý việc mở/đóng directory trong quá trình duyệt; nhưng mọi tài nguyên mà visitor tự mở vẫn phải được visitor đóng. |
| **Files.exists/isRegularFile/size/delete/deleteIfExists/createTempFile** | Giá trị/Path, không trả stream | Không có handle để caller đóng; **file tạm vẫn phải được xóa nếu ứng dụng chịu trách nhiệm dọn dẹp**. |

**Lỗi dễ mắc:** viết Files.lines(path).filter(...).count() mà không đặt Stream trả về vào try-with-resources. Một terminal operation chỉ kết thúc phép tính Stream; nó không đồng nghĩa với close(). Đối với Stream lấy từ collection thuần bộ nhớ như list.stream(), không có tài nguyên ngoài cần giải phóng trong trường hợp thông thường.

## 4. Bảng tra cứu channel, filesystem và các đối tượng NIO khác

| API | Ai đóng? | Ghi chú quan trọng |
|---|---|---|
| **FileChannel.open(path, options…)** | Caller đóng FileChannel | Đóng channel giải phóng file descriptor. |
| **AsynchronousFileChannel.open(path, options…)** | Caller đóng AsynchronousFileChannel | Đóng channel sau khi xử lý/đồng bộ các tác vụ bất đồng bộ theo thiết kế; tránh sử dụng sau khi đóng. |
| **Files.newByteChannel(path)** | Caller đóng SeekableByteChannel | Khi cắt qua lớp abstraction, quyền sở hữu vẫn đi theo đối tượng trả về. |
| **Channels.newInputStream(channel)** / **Channels.newOutputStream(channel)** | Thành phần sở hữu wrapper | Đóng stream chuyển đổi sẽ đóng channel nền; không làm vậy nếu channel được mượn. |
| **FileLock** từ FileChannel.lock()/tryLock() | Bên nhận lock giải phóng | Dùng release() hoặc AutoCloseable.close(); đóng channel cũng giải phóng lock liên quan, nhưng không nên dùng thay cho vòng đời lock rõ ràng. |
| **FileChannel.map(…) → MappedByteBuffer** | Không có phương thức close() công khai trên buffer | Đóng FileChannel **không bảo đảm** vùng nhớ ánh xạ được unmap ngay; việc unmap thường phụ thuộc vòng đời buffer/GC. Không giả định delete/truncate thành công tức thời trên mọi hệ điều hành. |
| **FileSystems.newFileSystem(…)** (ví dụ ZIP filesystem) | Mã tạo FileSystem | Đóng FileSystem khi dùng xong để giải phóng các tài nguyên của provider. |
| **FileSystems.getDefault()** | Runtime JVM | **Không đóng** default filesystem. |
| **FileSystems.getFileSystem(uri)** | Tùy hợp đồng nguồn gốc | Đây là filesystem đang tồn tại; không đóng nếu đang mượn hoặc dùng chung. |
| **FileSystems.getDefault().newWatchService()** | Mã tạo WatchService | Đóng WatchService để giải phóng hệ thống theo dõi thư mục. |
| **Path**, **Files.readAttributes(…)**, **BasicFileAttributes** | Không áp dụng | Path và thông tin thuộc tính không phải handle đang mở; không có close() để gọi. |

Channel và các stream được tạo trên cùng một nguồn có thể **chia sẻ vòng đời**. Không mở đồng thời nhiều wrapper rồi giả định có thể đóng một wrapper mà những wrapper còn lại vẫn hoạt động.

## 5. Bảng tra cứu API I/O thường dùng ngoài java.io/nio

| API | Trách nhiệm | Góc cạnh cần tránh |
|---|---|---|
| **new Scanner(path, charset)**, **new Scanner(inputStream/reader)** | Đóng Scanner nếu nó sở hữu đầu vào; Scanner.close() sẽ đóng nguồn nếu nguồn là Closeable | Scanner(System.in).close() cũng sẽ đóng **System.in**; thông thường không đóng đầu vào chuẩn dùng chung. |
| **new ZipInputStream(input)**, **new GZIPInputStream(input)** | Chủ sở hữu wrapper đóng wrapper | Việc đóng lan xuống input bên dưới; mỗi entry trong ZipInputStream kết thúc bằng closeEntry() để chuyển entry, nhưng **closeEntry() không thay thế close() toàn stream**. |
| **new ZipOutputStream(output)**, **new GZIPOutputStream(output)** | Chủ sở hữu wrapper đóng wrapper | Có thể dùng finish() để hoàn tất định dạng nén mà vẫn giữ stream nền mở theo thiết kế API; **close()** của wrapper còn đóng output nền. |
| **new ZipFile(path)**, **new JarFile(path)** | Mã mở file archive | Đóng ZipFile/JarFile; InputStream lấy qua getInputStream(entry) cũng nên được đóng trong phạm vi sử dụng, trước khi đóng archive. |
| **Socket**, **ServerSocket** do ứng dụng tạo/accept | Mã nhận quyền sở hữu socket đóng socket | Đóng socket hoặc stream của socket thường kéo theo đóng kết nối; không đóng một stream của socket khi cần tái sử dụng kết nối. |
| **URL.openStream()** | Mã gọi | Đóng InputStream nhận được; việc quản lý kết nối HTTP chuyên biệt cần theo hợp đồng thư viện đang dùng. |
| **Process.getInputStream/getErrorStream/getOutputStream** | Mã quản lý Process và các stream của nó | Đóng stream khi không sử dụng, tiêu thụ stdout/stderr tránh nghẽn và quản lý vòng đời Process riêng; chỉ close stream không đồng nghĩa tiến trình kết thúc. |

Đối với tài nguyên mượn từ framework, container, thư viện hoặc callback, **hợp đồng API cụ thể có thể thay đổi quyền sở hữu mặc định**. Ví dụ framework có thể gọi callback với một OutputStream mà framework sẽ tự đóng sau khi callback trả về.

## 6. Mẫu đúng/sai theo tình huống

### 6.1. Tự mở: tự đóng

~~~java
try (var reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String firstLine = reader.readLine();
    // Sử dụng firstLine tại đây.
} // reader.close() chạy cả khi readLine() ném IOException.
~~~

Với FileInputStream bọc BufferedInputStream, đối tượng cần quản lý ở lớp ứng dụng thường là **wrapper ngoài cùng**: đóng wrapper sẽ đóng stream gốc. Nếu việc khởi tạo các lớp phức tạp có thể thất bại giữa chừng, thiết kế từng bước acquisition trong các scope try-with-resources phù hợp để nguồn đã mở không bị rò rỉ.

### 6.2. Mượn OutputStream: ghi nhưng không đóng

~~~java
static void copyToCallerOwnedDestination(Path source, OutputStream destination)
        throws IOException {
    Files.copy(source, destination);
    destination.flush(); // Chỉ khi hợp đồng cần dữ liệu được đẩy ra lúc này.
    // Không đóng destination: caller sở hữu nó.
}
~~~

Ví dụ này thể hiện **hợp đồng caller-owned**; cần ghi rõ điều đó trong JavaDoc của phương thức thực tế. flush() không phải close(), và không bảo đảm dữ liệu đã được đồng bộ bền vững lên thiết bị lưu trữ. Bọc destination trong try-with-resources với BufferedOutputStream rồi đóng wrapper tại đây sẽ vô tình đóng cả destination do caller đang sở hữu.

### 6.3. Stream trả về: người nhận phải đóng

~~~java
static long countLines(Path file) throws IOException {
    try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
        return lines.count();
    }
}
~~~

Sai về vòng đời tài nguyên:

~~~java
long count = Files.lines(file).count(); // Stream chứa tài nguyên file không được đóng.
~~~

Khi thiết kế API trả về Stream gắn file, nên tài liệu hóa trách nhiệm close của caller. Nếu dữ liệu nhỏ và không cần lazy evaluation, cân nhắc trả về List đã đọc xong trong một scope try-with-resources để đơn giản hóa ownership.

### 6.4. Hệ thống chuẩn và tài nguyên dùng chung

- **System.in, System.out, System.err** thường là tài nguyên chung của ứng dụng/JVM; tránh đóng trong một helper hoặc bài thực hành. Chỉ flush đầu ra chuẩn khi cần.
- **Wrapper đóng lan xuống nguồn:** Scanner(System.in), BufferedWriter(new OutputStreamWriter(System.out, …)) và PrintWriter(System.out) đều có thể đóng nguồn chuẩn khi wrapper bị close().
- **Tài nguyên chia sẻ hoặc pooled:** không đóng nguồn được mượn nếu thư viện/owner chưa chuyển quyền sở hữu. Một adapter không đóng nguồn phải được thiết kế rõ ràng; việc chỉ bỏ qua close() trên một BufferedWriter có thể làm dữ liệu đệm chưa được xuất ra.

## 7. Chương trình Java 17+ có thể chạy

Đây là một ví dụ độc lập chứng minh khác biệt giữa API tự quản lý tài nguyên (**readAllLines**, **writeString**), API trả về handle (**newBufferedReader**, **newDirectoryStream**) và Stream cần đóng (**Files.lines**). File tạm được xóa ở finally; thao tác xóa độc lập với close().

**Tệp: ResourceCloseTableDemo.java**

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class ResourceCloseTableDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("close-table-", ".txt");

        try {
            Files.writeString(file, "alpha\nbeta\n", StandardCharsets.UTF_8);

            // Files tự mở/đóng nguồn; kết quả List không cần close().
            List<String> all = Files.readAllLines(file, StandardCharsets.UTF_8);
            System.out.println("readAllLines=" + all.size());

            // Caller sở hữu BufferedReader, nên dùng try-with-resources.
            try (BufferedReader reader =
                    Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                System.out.println("first=" + reader.readLine());
            }

            // count() không đóng Stream: try-with-resources mới đóng.
            try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
                long count = lines.filter(s -> s.startsWith("b")).count();
                System.out.println("b-lines=" + count);
            }

            // DirectoryStream có handle cần đóng sau khi duyệt.
            try (DirectoryStream<Path> entries =
                    Files.newDirectoryStream(
                            file.getParent(), file.getFileName().toString())) {
                int matches = 0;
                for (Path entry : entries) {
                    if (entry.equals(file)) {
                        matches++;
                    }
                }
                System.out.println("matching-files=" + matches);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac ResourceCloseTableDemo.java
java ResourceCloseTableDemo
~~~

**stdout dự kiến:**

~~~text
readAllLines=2
first=alpha
b-lines=1
matching-files=1
~~~

Giải thích: Files.writeString() và Files.readAllLines() đóng các tài nguyên nội bộ của chúng; Files.newBufferedReader(), Files.lines() và Files.newDirectoryStream() trả về đối tượng cần caller đóng. try-with-resources đóng tài nguyên trước khi finally xóa file tạm, tránh xóa khi handle vẫn đang mở.

## 8. Ngoại lệ, close() và thứ tự giải phóng

~~~java
try (InputStream input = Files.newInputStream(path);
     BufferedInputStream buffered = new BufferedInputStream(input)) {
    // Đọc dữ liệu từ buffered.
}
~~~

Đây là ví dụ thể hiện **thứ tự đóng ngược với thứ tự khai báo**: buffered.close() trước, input.close() sau. Vì đóng BufferedInputStream vốn đóng InputStream bên dưới, nguồn có thể bị đóng lần nữa trong ví dụ này; mẫu này hữu ích khi cần bảo đảm InputStream đã mở vẫn được đóng nếu việc tạo wrapper thất bại. Khi chọn thiết kế, kiểm tra tính an toàn của thao tác close nhiều lần ở API cụ thể; nếu không có nhu cầu xử lý lỗi khởi tạo wrapper, thường chỉ cần quản lý wrapper ngoài cùng trong try-with-resources.

Nếu phần thân try ném ngoại lệ và close() cũng ném, try-with-resources giữ ngoại lệ của thân làm **ngoại lệ chính** và ghi ngoại lệ lúc đóng dưới dạng **suppressed exception** (xem Throwable.getSuppressed()). Khi nhiều tài nguyên đóng, Java thử đóng theo thứ tự ngược dù một lần close có lỗi. Tránh tự viết finally khiến lỗi close che mất lỗi gốc hoặc bỏ qua lỗi mà không có chủ đích.

**Không phụ thuộc vào GC hay finalize() để đóng file/socket/channel.** Thời điểm thu gom không xác định. Tương tự, deleteIfExists() dọn tên file trong hệ thống file; nó không thay thế việc đóng stream/channel đang giữ file.

## 9. Checklist tra cứu trước khi gọi close()

1. **Nguồn gốc:** Tài nguyên được tạo tại đây, được caller truyền vào, hay do framework/connection pool cấp?
2. **Giá trị trả về:** API trả về dữ liệu thuần (byte[], String, List, Path) hay trả về đối tượng đang mở (Stream, Reader, Writer, Channel, DirectoryStream, Socket…)?
3. **Wrapper:** close() có lan xuống stream/channel bên dưới không? Nếu có, mình thực sự được quyền đóng nguồn đó chứ?
4. **Tính lazy:** Stream từ Files.lines/list/walk/find có được đóng trong try-with-resources, kể cả khi duyệt sớm dừng?
5. **Lỗi và hoàn tất ghi:** Tài nguyên có được đóng khi có ngoại lệ? Dữ liệu buffered/ZIP/object output có được hoàn tất theo hợp đồng API? Có cần checkError() cho PrintStream/PrintWriter?
6. **Phạm vi chuyển giao:** Nếu trả tài nguyên đang mở cho caller, trách nhiệm close đã được ghi trong hợp đồng? Nếu nhận tài nguyên mượn, phương thức có giữ nguyên trạng thái đóng/mở của nó không?
7. **Dọn dẹp khác close:** Việc xóa temp file, release lock, quản lý process hoặc đồng bộ bền vững dữ liệu có được xử lý riêng khi cần không?

Khi cần xác minh một API chưa có trong bảng, tìm kiểu trả về, phần mô tả **close/ownership** trong JavaDoc và hành vi đóng nguồn nền của wrapper. Nguyên tắc quyết định là **hợp đồng vòng đời**, không phải chỉ dựa vào tên phương thức hoặc việc đối tượng có implements AutoCloseable hay không.
