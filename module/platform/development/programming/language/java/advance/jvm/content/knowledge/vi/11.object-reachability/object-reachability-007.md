# GC thu hồi bộ nhớ khác với đóng file, socket và tài nguyên bên ngoài

## 1. Luận điểm chính: một object chết không đồng nghĩa tài nguyên bên ngoài đã được đóng

Trong Java, **garbage collector (GC)** quản lý khả năng tái sử dụng **bộ nhớ của những Java objects** mà chương trình không còn cần tới theo quy tắc reachability. Nhưng một Java object có thể chỉ là **lớp bao (wrapper)** của một tài nguyên không thuộc Java heap, chẳng hạn:

- File descriptor hoặc OS handle của một tệp.
- Socket và kết nối TCP.
- Database connection hoặc cursor/statement/result set.
- Direct/native buffer, native allocation hoặc mapping của file.
- Process, executor, thread pool và các đối tượng gắn với vòng đời tác vụ.
- Khóa, đăng ký listener, timer, resource của thư viện native.

**GC không phải API đóng tài nguyên theo lịch xác định.** Có thể một Java object đã hết lexical scope, bị bỏ reference hoặc trở thành eligible for collection, nhưng file vẫn đang mở, TCP connection vẫn tồn tại, native allocation vẫn chưa được thu hồi hoặc transaction chưa được rollback/commit.

Ví dụ:

```java
void readFile(Path file) throws IOException {
    InputStream stream = Files.newInputStream(file);
    int firstByte = stream.read();
    // Không gọi close() và không dùng try-with-resources.
}
```

Đây là **mã minh họa**, cần đặt trong class và khai báo các imports phù hợp. Biến local `stream` không còn dùng sau method, nhưng **Java không cam kết file descriptor sẽ được đóng ngay khi method return**. Một số implementation/library có cơ chế Cleaner hay giải phóng dự phòng; đó không phải lý do để dựa vào GC thay cho `close()`.

Cách nên viết:

```java
void readFile(Path file) throws IOException {
    try (InputStream stream = Files.newInputStream(file)) {
        int firstByte = stream.read();
        // Xử lý kết quả.
    }
}
```

`try-with-resources` thiết lập một đường **đóng có thứ tự, theo luồng điều khiển của Java**, dù block hoàn tất bình thường hay bằng exception.

**Phân biệt ba câu hỏi:**

1. **Object có còn strongly reachable không?** → liên quan tới GC và reachability.
2. **External resource có đang open/allocated không?** → phụ thuộc API/OS và state của resource.
3. **Ai chịu trách nhiệm gọi close/release/rollback/shutdown?** → là **ownership contract** của ứng dụng và thư viện.

Không thể trả lời câu 2 hoặc 3 chỉ từ câu 1.

## 2. Bản đồ bộ nhớ heap và tài nguyên bên ngoài

```text
               Java heap                     Hệ điều hành / native
        +---------------------+             +-------------------------+
        | FileInputStream     | --handle--> | File descriptor/handle  |
        | hoặc FileChannel    |             | file đang mở             |
        +---------------------+             +-------------------------+

        +---------------------+             +-------------------------+
        | Socket Java object  | --handle--> | Socket TCP kernel state  |
        +---------------------+             +-------------------------+

        +---------------------+             +-------------------------+
        | Connection wrapper  | --owns?---> | DB session / pool slot   |
        +---------------------+             +-------------------------+

        +---------------------+             +-------------------------+
        | Native buffer owner | --owns?---> | Native bytes / mapping   |
        +---------------------+             +-------------------------+
```

Sơ đồ thể hiện **mối liên hệ trách nhiệm**, không khẳng định mỗi tài nguyên luôn có một wrapper duy nhất hoặc một OS handle riêng: thư viện có thể chia sẻ descriptors, quản lý connection pool, tái sử dụng channels hay dùng nhiều native structures.

### 2.1. Java heap do GC quản lý

Theo **JVMS §2.5.3**, heap dùng để cấp phát class instances và arrays. VM dùng automatic storage management để reclaim heap storage của objects không còn cần. Garbage collector có thể chạy theo chính sách riêng; `System.gc()` không cho một deadline portable để mọi object không còn dùng được thu hồi.

Điều GC **không thể tự suy ra từ một kiểu object tùy ý** là “giải quyết transaction”, “flush dữ liệu nghiệp vụ”, “gửi protocol close frame”, “trả lại connection pool slot đúng deadline” hoặc “đóng file handle vào thời điểm yêu cầu”.

### 2.2. External resource có giới hạn riêng

Ví dụ hệ điều hành có thể giới hạn số file descriptors của một process. Một ứng dụng giữ hàng nghìn sockets chưa đóng có thể gặp lỗi kiểu **too many open files** hoặc resource exhaustion ngay cả khi Java heap còn khá nhiều.

Một connection pool có thể hết connections dù heap còn trống. Một native allocation có thể làm process RSS tăng ngoài phần bộ nhớ Java heap. **Tăng `-Xmx` không tự xử lý external resource leak** và đôi khi làm ngân sách native memory của container khan hiếm hơn.

### 2.3. Mỗi loại “release” có hiệu ứng khác nhau

| Hoạt động | Tác động trực tiếp | Không tự bảo đảm |
| --- | --- | --- |
| Bỏ reference local | Giảm một đường tham chiếu trong đồ thị Java | Object GC ngay; socket/file tự đóng |
| `System.gc()` | Gợi ý runtime thực hiện GC | Một resource bất kỳ sẽ được đóng trước deadline |
| `close()` | Thực hiện hợp đồng đóng của resource tương ứng | Java heap object được free tức thời |
| `shutdown()` của executor | Bắt đầu quy trình dừng theo API | Mọi task đã hoàn thành ngay |
| `commit()` / `rollback()` | Điều khiển transaction theo JDBC/database | Connection wrapper bị GC ngay |
| `Files.delete(...)` | Yêu cầu xóa directory entry/file theo OS | Mọi open handle liên quan tự đóng hoặc có cùng semantics trên mọi OS |

**Điều cần thiết kế là state/lifecycle**, không chỉ số byte sử dụng.

## 3. Scope, reachability và resource lifetime là ba trục độc lập

Xét:

```java
InputStream in = Files.newInputStream(path);
try {
    consume(in);
} finally {
    in.close();
}
```

Đây là **mã minh họa**, cần có `path`, `consume`, imports và xử lý exception theo ứng dụng. Trong đoạn này:

- Biến local `in` có **scope** riêng.
- Object stream có **reachability** riêng; còn có thể được giữ ở phương thức khác hoặc bởi field nếu code chia sẻ reference.
- File descriptor có **open/closed state** theo API/OS; lời gọi `close()` chủ động chuyển lifecycle qua bước đóng.

Bạn có thể chủ động **close resource khi Java wrapper object vẫn strongly reachable**, ví dụ `in.close(); System.out.println(in != null);`. Biến `in` vẫn có giá trị reference; điều này không có nghĩa file còn open.

Ngược lại, bạn có thể bỏ mọi local reference tới một wrapper nhưng chưa có bảo đảm external resource đã được đóng theo deadline.

### 3.1. Object còn sống nhưng tài nguyên đã đóng

```java
InputStream stream = Files.newInputStream(path);
stream.close();
boolean wrapperStillReferenced = stream != null;
```

`wrapperStillReferenced` bằng true khi đoạn code hoàn tất bình thường. Nhưng tài nguyên stream đã được yêu cầu đóng. **Object memory lifetime ≠ resource open state**.

Một số API cho phép gọi `close` lặp lại; một số API/implementation có hành vi riêng. Đừng đồng nhất “wrapper còn sống” với “resource có thể tiếp tục dùng hợp lệ”.

### 3.2. Object hết scope nhưng resource có thể vẫn open

```java
static void openAndForget(Path path) throws IOException {
    InputStream stream = Files.newInputStream(path);
    stream.read();
    // Không close.
}
```

Đây là **anti-pattern**. Sau return không nên suy đoán OS handle đã được giải phóng. Có thư viện cung cấp cleanup dự phòng thông qua reference processing, nhưng thời điểm GC/cleaner không xác định; không được thiết kế resource ownership dựa vào may rủi đó.

### 3.3. Reference còn sống nhưng resource không còn sử dụng được

Một socket/stream/DB connection đã đóng có thể vẫn là một Java object bình thường. Nhưng gọi read/write/query sau khi đóng có thể ném exception hoặc hành xử theo API tương ứng.

**Không dùng `object != null` làm phép kiểm tra duy nhất rằng resource vẫn open.** State và errors phải được lấy từ hợp đồng của resource.

## 4. Tại sao finalization không thể là chiến lược đóng file/socket đáng tin?

Finalization từng cho phép class ghi đè `finalize()` để thực thi code khi runtime nhận thấy điều kiện đặc biệt liên quan object reachability. Cơ chế này có nhiều vấn đề:

- Không có hạn định khi nào GC phát hiện object cần xử lý.
- Finalizer có thể chậm, không được chạy trước khi process kết thúc.
- Có rủi ro trì hoãn reclaim bộ nhớ, deadlock, vấn đề security/concurrency và object resurrection.
- Runtime mới có thể vô hiệu hóa hoặc loại bỏ tính năng.
- Finalizer không có cơ chế business transaction đáng tin cậy để đảm bảo dữ liệu đã flush/commit.

**JEP 421** deprecate finalization for removal từ JDK 18. Code mới không nên viết `finalize` để đóng file descriptor, network session hay database connection. Nên dùng `try-with-resources`/`AutoCloseable` hoặc explicit lifecycle.

### 4.1. Finalizer đã chạy không có nghĩa logic resource hoàn tất

Đóng file có thể thất bại bởi `IOException`; transaction có thể cần rollback/commit theo quy tắc; network close có thể phụ thuộc protocol và trạng thái peer. Những tình huống này cần có **luồng xử lý lỗi do caller kiểm soát**.

Nếu chỉ dựa vào finalization, caller không có một điểm rõ ràng để nhận và xử lý lỗi đóng trước khi trả kết quả nghiệp vụ.

## 5. `AutoCloseable` và `Closeable` — ngôn ngữ của quyền sở hữu

**`AutoCloseable`** cung cấp phương thức `close()`:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

`java.io.Closeable` mở rộng `AutoCloseable` với hợp đồng `close()` thích hợp cho I/O (thường khai báo `IOException`). Không phải mọi AutoCloseable đều là Closeable; không phải mọi `close` đều có cùng semantics idempotency hoặc loại exception.

### 5.1. `try-with-resources` thực hiện việc gì?

Với:

```java
try (Resource resource = open()) {
    use(resource);
}
```

Java compiler đảm bảo `close()` được gọi khi rời body nếu resource được tạo thành công, **kể cả khi body ném exception**. Khi có nhiều resources, chúng được đóng **theo thứ tự ngược lại thứ tự khởi tạo**.

Đoạn này chỉ là **mẫu cấu trúc**, `Resource`, `open` và `use` cần khai báo tương ứng. Bài thực hành độc lập ở phần tiếp theo dùng file thật để kiểm chứng.

### 5.2. Đừng hiểu `AutoCloseable` là Java destructor

- `close()` chỉ làm những gì API/implementation quy định.
- Object Java vẫn có thể tồn tại sau `close()`.
- `close()` có thể flush/rollback/trả tài nguyên pool/thả native handle theo từng API.
- Một `AutoCloseable` có thể không sở hữu native resource nào; nó vẫn có thể quản lý lifecycle logic.
- `try-with-resources` không ép GC chạy.

### 5.3. Quyền sở hữu phải được xác định

Khi method nhận một `InputStream` từ caller, cần phân biệt:

- **Callee sở hữu:** method có trách nhiệm đóng sau khi dùng.
- **Caller sở hữu:** method chỉ mượn stream và không đóng, trừ khi hợp đồng API nói khác.

Ví dụ:

```java
static byte[] readWithoutClosing(InputStream borrowed)
        throws IOException {
    return borrowed.readAllBytes();
}
```

Đây là một **method minh họa**. Caller có trách nhiệm đóng stream nếu nó sở hữu resource. Việc callee tự close có thể làm hỏng thao tác tiếp theo của caller. Cách đặt tên/documentation cần nói rõ ownership; không phải cứ thấy `InputStream` là mọi method đều nên gọi `close`.

## 6. Ví dụ Java 17+ đầy đủ: file thật, close đảo thứ tự, suppressed exception

Tạo tệp **`ResourceLifecycleDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ResourceLifecycleDemo {
    static final class Tracked implements AutoCloseable {
        private final String name;
        private boolean closed;

        Tracked(String name) {
            this.name = name;
        }

        void use() {
            System.out.println("using " + name);
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("closed " + name);
            }
        }
    }

    static final class FailingClose implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("resource-lifecycle-", ".txt");

        try {
            try (BufferedWriter writer =
                         Files.newBufferedWriter(file, StandardCharsets.UTF_8)) {
                writer.write("Hello JVM");
            }

            try (BufferedReader reader =
                         Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                System.out.println("file content: " + reader.readLine());
            }
        } finally {
            Files.deleteIfExists(file);
        }

        try (Tracked first = new Tracked("first");
             Tracked second = new Tracked("second")) {
            first.use();
            second.use();
        }

        try (FailingClose failing = new FailingClose()) {
            throw new IllegalStateException("body failed");
        } catch (IllegalStateException error) {
            System.out.println("primary: " + error.getMessage());
            System.out.println("suppressed count: "
                    + error.getSuppressed().length);
            System.out.println("suppressed type: "
                    + error.getSuppressed()[0]
                            .getClass().getSimpleName());
        }

        System.out.println("done");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 ResourceLifecycleDemo.java
java ResourceLifecycleDemo
```

**Stdout chính xác trong lần chạy bình thường**, khi có quyền tạo/đọc/xóa file tạm trong thư mục tạm hệ thống:

```text
file content: Hello JVM
using first
using second
closed second
closed first
primary: body failed
suppressed count: 1
suppressed type: IOException
done
```

Ví dụ được kiểm tra bằng `javac --release 17` và chạy trên OpenJDK 21, stdout khớp. Chương trình sử dụng file tạm thực qua `Files.createTempFile`, không in đường dẫn ngẫu nhiên, để đầu ra ổn định giữa các lần chạy có môi trường I/O hợp lệ.

### 6.1. Phần file I/O giải quyết resource lifecycle

`Files.newBufferedWriter` mở một writer, ghi `Hello JVM` và try-with-resources đóng writer khi block kết thúc; việc đóng writer cũng đảm bảo thực hiện những hoạt động flush/close phù hợp hợp đồng API. Sau đó reader được mở riêng, đọc dòng và đóng.

`Files.deleteIfExists(file)` trong `finally` xóa file tạm dù phần thao tác I/O thành công hay ném exception (với các giới hạn lỗi của file system). Không có dòng nào phải gọi `System.gc()` để hoàn thành vòng đời file.

**Chú ý:** `deleteIfExists` không luôn thành công; ví dụ `IOException` có thể xảy ra do quyền truy cập/hệ thống file. Điều kiện “stdout chính xác” ở trên áp dụng **khi thao tác file tạm thành công bình thường**, không khẳng định mọi môi trường sandbox đều cho phép I/O.

### 6.2. `close()` diễn ra theo thứ tự ngược

Hai tài nguyên:

```java
try (Tracked first = new Tracked("first");
     Tracked second = new Tracked("second")) {
    first.use();
    second.use();
}
```

được tạo theo thứ tự `first` rồi `second`. Khi thoát block, compiler đóng `second` trước `first`:

```text
using first
using second
closed second
closed first
```

Thứ tự ngược đặc biệt có ích khi resource thứ hai phụ thuộc vào resource thứ nhất; ví dụ wrapper buffering trùm trên stream gốc. Tuy nhiên, nếu hai wrappers **cùng trỏ tới một underlying resource**, phải hiểu riêng hợp đồng ownership để tránh đóng lặp hoặc đóng quá sớm.

### 6.3. `close()` có thể ném exception khi body đã thất bại

Ở ví dụ:

```java
try (FailingClose failing = new FailingClose()) {
    throw new IllegalStateException("body failed");
}
```

Khi rời body, Java vẫn gọi `FailingClose.close()`. `close` ném `IOException("close failed")`, nhưng vì **body đã có primary exception** `IllegalStateException("body failed")`, exception từ close được đính vào mảng **suppressed exceptions** của primary exception.

Bởi vậy output cho thấy:

```text
primary: body failed
suppressed count: 1
suppressed type: IOException
```

**Không được đánh mất suppressed exception khi debug.** Nó có thể chứa thông tin rằng một file/socket/channel không đóng sạch dù lỗi chính xuất phát từ xử lý nội dung.

### 6.4. Khi cả body và `close` thành công

`close` vẫn được gọi, nhưng không có exception. Chương trình không cần và không nên dùng `System.gc()` chỉ để “kích hoạt” đóng file.

## 7. Ngoại lệ, thứ tự đóng và partial acquisition

`try-with-resources` giải quyết những góc khó của cleanup:

### 7.1. Resource thứ hai mở thất bại

```java
try (InputStream first = openFirst();
     InputStream second = openSecond()) {
    use(first, second);
}
```

Đây là code minh họa, chưa độc lập. Nếu `openFirst()` thành công nhưng `openSecond()` ném exception, Java sẽ **đóng `first` đã được khởi tạo thành công**. Đây là một ưu điểm so với code mở nhiều resources rồi chỉ gọi `close` ở cuối body.

### 7.2. Nhiều `close` cùng ném lỗi

Các resource được đóng theo thứ tự ngược; nếu body đã ném lỗi, các lỗi trong close được **suppressed** phù hợp. Nếu body hoàn tất bình thường nhưng một close ném lỗi, lỗi từ close có thể trở thành primary exception. Với nhiều close errors, những lỗi tiếp theo có thể được suppressed vào lỗi chính theo quy tắc Java.

Do đó, không thể suy luận mọi trường hợp `close` thất bại đều bị nuốt; cần kiểm tra exception chain và `getSuppressed()`.

### 7.3. Đừng thay `try-with-resources` bằng `finally` sai

Ví dụ dễ mất thông tin:

```java
Resource r = open();
try {
    doWork(r);
} finally {
    r.close(); // Nếu cũng ném, có nguy cơ che lấp lỗi gốc.
}
```

Đây là code minh họa chưa độc lập. Khi có thể, `try-with-resources` giúp Java giữ quan hệ primary/suppressed exception đúng hơn so với một khối finally tự viết chưa xét đầy đủ các tình huống lỗi.

### 7.4. Đừng bắt mọi lỗi rồi tiếp tục như thể đóng thành công

`IOException` từ `close` có thể báo flush không thành công, mất kết nối, hỏng đĩa hoặc một sự cố I/O khác. Cách xử lý đúng tùy nghiệp vụ: propagate, retry có giới hạn, đánh dấu transaction thất bại, báo lỗi hoặc log có ngữ cảnh.

Không làm:

```java
try {
    resource.close();
} catch (Exception ignored) {
    // Luôn coi thành công: anti-pattern.
}
```

Mã trên là **anti-pattern minh họa**, không phải quy tắc khuyến nghị.

## 8. File, stream và channel: đóng đúng đối tượng sở hữu

### 8.1. `InputStream`, `OutputStream`, `Reader`, `Writer`

Các stream/writer thường đại diện khả năng đọc/ghi. Việc đóng:

- Kết thúc sử dụng resource theo hợp đồng API.
- Có thể flush các buffers phù hợp trước khi release.
- Có thể chuyển OS handle sang trạng thái đã đóng.
- Có thể ném exception; phải xử lý.

Nếu dùng `BufferedInputStream` bọc một stream khác, cần xác định wrapper có sở hữu underlying stream không. Trong API thông thường, đóng wrapper cũng đóng underlying stream; nếu underlying stream còn được dùng ở nơi khác, việc đóng wrapper có thể làm hỏng caller.

### 8.2. `FileChannel` và `SeekableByteChannel`

`FileChannel` là một `Channel` và có `close()` theo API. Dùng try-with-resources:

```java
try (java.nio.channels.FileChannel channel =
         java.nio.channels.FileChannel.open(path,
                 java.nio.file.StandardOpenOption.READ)) {
    long size = channel.size();
    // Xử lý size.
}
```

Đây là **code minh họa**, `path` được khai báo trong context. Đóng channel là hoạt động lifecycle độc lập với GC heap object.

### 8.3. `MappedByteBuffer` và mapped memory

Memory-mapped files phức tạp hơn vì mapping và OS pages có vòng đời riêng. Dùng `FileChannel.map` có thể tạo một mapped buffer; **đóng FileChannel không đồng nghĩa mọi mapping được unmapped ngay** theo mọi tình huống.

Không hứa “try-with-resources cho channel sẽ lập tức unmap mọi buffer còn reachable”. Việc lifecycle của mapping còn phụ thuộc buffer, JVM/OS và các API hỗ trợ. Nếu cần deterministic unmapping, thiết kế qua API thích hợp của JDK mục tiêu thay vì dùng private `Unsafe` tricks không portable.

### 8.4. Flush không phải close, và close không phải fsync universal

- `flush()` thường yêu cầu đẩy dữ liệu đã buffer xuống tầng dưới, theo API.
- `close()` kết thúc sử dụng resource, đôi khi flush trước khi release.
- Bảo đảm dữ liệu đã thực sự **durable** trên thiết bị lưu trữ là vấn đề khác, có thể cần các API như `FileChannel.force` và cân nhắc hợp đồng OS/file system.

Đừng nhầm “file descriptor đóng xong” với “mọi byte đã được đảm bảo ghi vĩnh viễn bất chấp mất điện”.

## 9. Socket: lifetime của Java wrapper khác kết nối TCP

Một `java.net.Socket` thường đại diện một endpoint TCP. Khi socket đã kết nối, OS giữ trạng thái network, buffers và descriptors ngoài Java heap.

### 9.1. Đóng socket chủ động

Ví dụ Java source minh họa:

```java
import java.net.Socket;

try (Socket socket = new Socket("example.com", 443)) {
    socket.setSoTimeout(5000);
    // Giao tiếp theo protocol tương ứng.
}
```

**Không phải chương trình độc lập**: cần method/exception handling thích hợp, network access và một protocol hợp lệ. Đừng coi ví dụ là HTTP/TLS client hoàn chỉnh vì kết nối TCP tới port 443 không tự thực hiện TLS handshake hay HTTP request.

Khi try block kết thúc, `Socket.close()` được gọi theo hợp đồng. GC không phải tác nhân được dùng để đảm bảo socket đóng đúng thời điểm.

### 9.2. Đóng socket không phải xác nhận dữ liệu đã đến peer

TCP là một protocol có trạng thái. `close()` bắt đầu/hoàn tất những hoạt động đóng phía local theo API/OS, nhưng **không tự trở thành một ACK ở mức nghiệp vụ** rằng server đã xử lý transaction hoặc ghi dữ liệu vào database.

Muốn xác nhận xử lý thành công, ứng dụng cần protocol response, timeout và chiến lược retry/idempotency phù hợp.

### 9.3. `shutdownInput`, `shutdownOutput` khác `close`

`shutdownOutput()` và `shutdownInput()` có hợp đồng **half-close** của socket ở những trường hợp được hỗ trợ; không nên tùy tiện coi chúng tương đương `Socket.close()`.

Một ứng dụng streaming đôi khi cần báo đã gửi xong data bằng half-close nhưng vẫn đọc response. Nếu gọi close quá sớm, nó có thể phá hỏng protocol flow.

### 9.4. Socket timeout không thay resource cleanup

`setSoTimeout` điều chỉnh thời gian chờ đọc theo API, giúp tránh một số blocking read vô thời hạn. Nhưng timeout không mặc nhiên đóng socket, không tự dọn listeners hoặc đóng connection pool khi hết request. Cleanup và timeout là **hai lớp bảo vệ bổ sung**.

### 9.5. `ServerSocket` cũng cần close

`ServerSocket` có thể giữ port bind và OS descriptor. Hết scope của biến server socket không hứa port được release ngay. Dùng try-with-resources và explicit shutdown/cancellation cho accept loop khi phù hợp.

## 10. JDBC: `Connection.close()` có thể trả về pool, không phải đóng TCP thật

Trong ứng dụng production, kết nối database thường đi qua **connection pool**. Một lời gọi:

```java
try (java.sql.Connection connection =
         dataSource.getConnection()) {
    // Sử dụng connection.
}
```

là **đoạn mã minh họa**, `dataSource` phải được cấu hình. Với một connection wrapper từ pool, `close()` thường có nghĩa **trả logical connection về pool** sau khi xử lý trạng thái phù hợp, không nhất thiết hủy underlying physical socket.

Đây là ví dụ điển hình rằng:

> **Hợp đồng đóng một resource không được suy ra từ tên kiểu Java mà phải đọc tài liệu của provider và ownership model.**

### 10.1. Đóng cả `ResultSet`, `Statement` khi sở hữu

```java
try (Connection c = dataSource.getConnection();
     PreparedStatement p =
             c.prepareStatement("SELECT name FROM users WHERE id = ?")) {
    p.setLong(1, userId);
    try (ResultSet rs = p.executeQuery()) {
        if (rs.next()) {
            String name = rs.getString(1);
            // Xử lý name.
        }
    }
}
```

Đây là code minh họa, cần `dataSource`, `userId` và imports/driver phù hợp. Việc đóng theo scope giúp tránh giữ cursor, statement hoặc connection pool slot không cần thiết.

### 10.2. Transaction lifecycle khác GC

Một transaction cần logic rõ:

- `commit()` khi nghiệp vụ thành công và các điều kiện được thỏa.
- `rollback()` khi gặp lỗi hoặc validation thất bại.
- `close()`/trả connection theo hợp đồng provider.

**Không giả định `GC đã thu hồi Connection object` đồng nghĩa transaction đã commit.** Việc connection được close có thể làm transaction rollback theo behavior của driver/pool/DB, nhưng không thay quyết định giao dịch rõ ràng.

### 10.3. Connection pool exhaustion

Một endpoint quên gọi close có thể làm pool hết available connections. Lúc đó hệ thống có thể treo chờ hoặc timeout dù **Java heap còn rất nhiều memory**.

Cần theo dõi pool metrics: active, idle, pending acquisition, timeout, connection age và ứng xử release. GC logs không đủ để chứng minh pool lifecycle đúng.

## 11. Executor, thread và process: “đóng” không phải một thao tác chung

Không phải mọi tài nguyên đều có đúng method tên `close` hoặc cùng hợp đồng:

| Resource | API lifecycle thường dùng | Lưu ý |
| --- | --- | --- |
| `InputStream` / `Reader` | `close()` | Có thể ném `IOException` |
| `FileChannel` | `close()` | File/channel ownership |
| `Socket` / `ServerSocket` | `close()` | OS socket và protocol semantics |
| JDBC `Connection` | `close()` | Có thể trả connection vào pool |
| JDBC `Statement`, `ResultSet` | `close()` | Thường cần nested try-with-resources |
| `ExecutorService` | `shutdown()`, `shutdownNow()`, `awaitTermination()` | Dừng nhận task và đợi task kết thúc theo API |
| `Process` | `destroy()`, `destroyForcibly()`, `waitFor()` | Điều khiển tiến trình con, không phải GC |
| Application listener/registration | `removeListener`, `unregister` | Phải cắt nguồn callback khi hết lifecycle |
| `ThreadLocal` | `remove()` | Tránh giữ request state giữa các pool tasks |
| Lock/semaphore | `unlock()` / `release()` | Cân bằng acquire/release, không phải heap free |

**Lưu ý phiên bản:** JDK 17 `ExecutorService` chủ yếu dùng `shutdown`/`awaitTermination`; không áp dụng bừa những tiện ích hoặc cách dùng try-with-resources được thêm vào interface ở các JDK mới hơn cho code `--release 17`.

### 11.1. Executor shutdown đúng cách

```java
ExecutorService pool = Executors.newFixedThreadPool(2);
try {
    // Submit công việc và xử lý kết quả theo hợp đồng.
} finally {
    pool.shutdown();
    if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
        pool.shutdownNow();
    }
}
```

Đây là code minh họa, cần imports và xử lý `InterruptedException`. `shutdown()` là yêu cầu ngừng nhận công việc mới và cho các tasks đang có cơ hội hoàn tất; nó **không bảo đảm tức thì mọi thread đã chết**. `awaitTermination` giúp caller chờ có giới hạn. `shutdownNow` cố gắng ngắt theo cơ chế tương ứng, không cam kết kill mọi tác vụ bất kể chúng có phản hồi interruption không.

### 11.2. ThreadLocal retention

Một worker thread trong pool có thể sống qua hàng nghìn requests. Dù biến local của request đã hết scope, giá trị `ThreadLocal` có thể vẫn được giữ qua thread-local map.

```java
try {
    CONTEXT.set(requestContext);
    handleRequest();
} finally {
    CONTEXT.remove();
}
```

Code trên là **mẫu minh họa**, cần định nghĩa `CONTEXT`, `requestContext` và `handleRequest`. `remove()` là cleanup của **logical scope request**, không phải lệnh yêu cầu GC.

## 12. `Cleaner`: cleanup dự phòng khi object trở thành phantom reachable

Java 9+ có `java.lang.ref.Cleaner` để đăng ký một cleaning action tương ứng object. Cleaner dựa trên **`PhantomReference` và `ReferenceQueue`** để nhận biết thay đổi reachability.

Cần hiểu ba điểm:

1. Cleaning action được chạy khi GC/reference processing báo object trở thành **phantom reachable**, hoặc khi code **explicitly gọi `Cleanable.clean()`**.
2. **Không có deadline bảo đảm** khi action do GC kích hoạt; trước khi process kết thúc có thể nó chưa chạy.
3. **Action không được giữ strong reference tới object được đăng ký**, nếu không object có thể không trở thành phantom reachable và cleaner tự động sẽ không được kích hoạt.

Vì thế **Cleaner là safety net**, không thay `try-with-resources` hoặc explicit close với file/socket/DB cần release đúng thời điểm.

### 12.1. Ví dụ pattern an toàn

```java
import java.lang.ref.Cleaner;

final class NativeHandle implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        private boolean cleaned;

        @Override
        public synchronized void run() {
            if (cleaned) return;
            cleaned = true;
            // Release native handle do State sở hữu.
        }
    }

    private final State state = new State();
    private final Cleaner.Cleanable cleanable =
            CLEANER.register(this, state);

    @Override
    public void close() {
        cleanable.clean();
    }
}
```

Đây là **class minh họa**, chưa thật sự cấp phát native handle. `State` được khai báo `static` để không capture `NativeHandle.this`. Trong code thật, `State` phải giữ đủ dữ liệu để giải phóng tài nguyên, nhưng **không được vô tình giữ chính wrapper referent**.

**Không đăng ký `this::cleanup` hoặc lambda dùng fields của `this` làm cleaning action** nếu nó giữ strong reference tới referent, bởi điều này có thể cản trở GC-based cleanup.

## 13. Ví dụ Java 17+ đầy đủ: gọi Cleaner chủ động, không đợi GC

Tạo tệp **`CleanerSafetyDemo.java`**:

```java
import java.lang.ref.Cleaner;
import java.util.concurrent.atomic.AtomicBoolean;

public final class CleanerSafetyDemo implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        private final AtomicBoolean cleaned = new AtomicBoolean();

        @Override
        public void run() {
            if (cleaned.compareAndSet(false, true)) {
                System.out.println("cleaned once");
            }
        }
    }

    private final Cleaner.Cleanable cleanable =
            CLEANER.register(this, new State());

    void use() {
        System.out.println("using wrapper");
    }

    @Override
    public void close() {
        cleanable.clean();
    }

    public static void main(String[] args) {
        try (CleanerSafetyDemo resource = new CleanerSafetyDemo()) {
            resource.use();
        }
        System.out.println("explicit close finished");
    }
}
```

Chạy:

```bash
javac --release 17 CleanerSafetyDemo.java
java CleanerSafetyDemo
```

**Stdout chính xác:**

```text
using wrapper
cleaned once
explicit close finished
```

Ví dụ đã được biên dịch với `--release 17` và chạy thành công trên OpenJDK 21.

Giải thích:

- `Cleaner.register(this, new State())` đăng ký wrapper là referent và một `State` **không tham chiếu tới wrapper**.
- `try-with-resources` chủ động gọi `close()`.
- `close()` gọi `cleanable.clean()`, nên action chạy theo đường **explicit** và in `cleaned once` trước khi block hoàn tất.
- Code **không gọi GC**, không đợi phantom reachability; vì vậy stdout không phụ thuộc lịch GC.
- `AtomicBoolean` làm hành vi action idempotent trong demo; theo hợp đồng Cleaner, một cleanable action được thực thi tối đa một lần theo cơ chế thích hợp.
- Demo **không quản lý OS handle thật**, chỉ biểu diễn mối quan hệ giữa close và Cleaner. Các tài nguyên thật cần logic release chính xác và xử lý lỗi riêng.

### 13.1. Tại sao Cleaner không nên được dùng cho transaction quan trọng?

Nếu chương trình bỏ quên `close()`, action phụ thuộc GC có thể chỉ chạy muộn hoặc không kịp trước khi process kết thúc. Transaction không thể dựa vào “đến khi object phantom reachable thì commit/rollback” để có consistency theo deadline.

## 14. `Reference.reachabilityFence` và native resource wrappers

Một trường hợp tinh vi xuất hiện khi Java wrapper sở hữu native handle, nhưng native operation chỉ nhận một giá trị số như địa chỉ/handle:

```java
static void perform(NativeWrapper owner) {
    long handle = owner.handle();
    nativeCall(handle);
    java.lang.ref.Reference.reachabilityFence(owner);
}
```

Đây là **mã minh họa**; `NativeWrapper` và `nativeCall` chưa được khai báo. Compiler/JIT có thể nhận thấy bản thân `owner` không còn được sử dụng qua Java reference trong native operation sau khi lấy `handle`, trong khi cleaning mechanism có thể release native handle nếu wrapper trở thành phantom reachable quá sớm.

`Reference.reachabilityFence(owner)` bảo đảm **object strongly reachable ít nhất tới sau invocation này**, giúp ngăn một số trường hợp cleanup sớm khi native operation vẫn đang sử dụng handle.

Nhưng nó:

- Không gọi `close()`.
- Không gọi `System.gc()`.
- Không pin object tại một địa chỉ heap bất biến.
- Không giải quyết vấn đề thread khác chủ động gọi `close()` đồng thời.
- Không thay một ownership protocol có synchronization phù hợp.

Đối với file stream Java thông thường, **try-with-resources** thường là abstraction đúng hơn; `reachabilityFence` đặc biệt phù hợp ở các tầng native-resource wrapper được thiết kế cẩn thận.

## 15. Native/off-heap buffers có vòng đời riêng

Một số API phân bổ bộ nhớ **ngoài Java heap**, chẳng hạn direct buffers hoặc native allocations. Số byte Java heap nhìn thấy trong profiler có thể nhỏ hơn tổng RSS của tiến trình.

### 15.1. `ByteBuffer.allocateDirect`

```java
java.nio.ByteBuffer direct =
        java.nio.ByteBuffer.allocateDirect(1024 * 1024);
```

Đây là code minh họa. Direct buffer giữ data vùng memory mà VM cố gắng hỗ trợ I/O/native access hiệu quả, không phải một mảng Java heap `byte[]` thông thường.

Khả năng reclaim native memory của direct buffer phụ thuộc VM và các cơ chế buffer/reference processing. **Không có `close()` chuẩn trên mọi `ByteBuffer`** để ứng dụng gọi như `InputStream`.

Với những resources đòi deterministic lifecycle, chọn API có hỗ trợ **explicit ownership/release** ở JDK mục tiêu, ví dụ các cấu trúc Foreign Function & Memory API nếu dùng JDK hỗ trợ ổn định. Không dùng private `Unsafe.invokeCleaner` như một lời hứa portable của Java SE.

### 15.2. `FileChannel.map` / mapped buffers

Mapped memory có thể tồn tại sau khi channel đóng. Mặc dù channel close giải phóng những resources theo API, memory mapping có semantics/lifetime riêng. Đừng coi GC của Java wrapper hay đóng channel là bằng chứng mapping đã được unmap tại đúng thời điểm.

### 15.3. RSS cao không đồng nghĩa heap leak

Khi container bị kill vì vượt memory limit, kiểm tra thêm:

- Heap used/committed và GC.
- Metaspace/class metadata.
- Native allocations, direct/mapped buffers.
- Thread stacks.
- Code cache, VM/GC native structures.
- File/socket handles và những hệ quả tài nguyên khác.

Đây là phần mở rộng để giải thích **ngoài-heap**, không có nghĩa mọi FD leak tự làm RSS tăng theo cùng tỉ lệ; FD count và heap/RSS là những chỉ số độc lập.

## 16. Idempotency, thread safety và đóng nhiều lần

Không được giả định tất cả `close()` của mọi `AutoCloseable` đều có cùng semantics. Một số resource được thiết kế **idempotent close**; một số có state hoặc exception behavior riêng.

Trong code ứng dụng tự viết, có thể ưu tiên `close` idempotent nếu điều đó phù hợp hợp đồng:

```java
final class Gate implements AutoCloseable {
    private boolean closed;

    @Override
    public void close() {
        if (closed) return;
        closed = true;
        releaseOwnedResource();
    }
}
```

Đây là **mã minh họa**, `releaseOwnedResource` chưa được định nghĩa. Với nhiều threads, biến `closed` không có synchronization phù hợp **không đủ bảo đảm thread-safe close**. Cần lập kế hoạch state machine, atomic/synchronized operations, tránh use-after-close và double-free.

### 16.1. Close cùng lúc với read/write

Nếu một thread đang sử dụng socket/channel, thread khác gọi close, kết quả phụ thuộc API (có thể ném exception/hủy blocking I/O). Không coi GC hoặc `volatile boolean closed` đơn giản là giải pháp cho concurrency correctness.

Trong API low-level native, use-after-free còn có thể gây lỗi nghiêm trọng. Quy tắc ownership phải xác định ai đang mượn handle và khi nào có quyền release nó.

### 16.2. Nested resources và shared underlying handle

Nếu tạo hai wrappers cùng sở hữu một underlying stream, đóng một wrapper có thể làm wrapper khác không dùng tiếp được. Không mặc định “mỗi wrapper đóng một lần” là luôn đúng khi có **shared ownership**.

Khi thực sự muốn stream còn open cho caller, dùng API có hợp đồng mượn/lending rõ hoặc wrapper non-closing được thiết kế riêng, thay vì lặng lẽ bỏ close và hy vọng GC dọn.

## 17. Phân biệt resource leak và memory leak

| Hiện tượng | Dấu hiệu thường gặp | Điều cần xem |
| --- | --- | --- |
| **Java heap retention/leak** | Live heap hoặc retained object graph tăng | GC roots, static collections, cache, ThreadLocal |
| **File descriptor leak** | Số OS FDs tăng, không mở được file/socket mới | Paths mở chưa đóng, resource ownership |
| **Socket/connection leak** | TCP connections/pool active tăng, timeout khi lấy connection | `Socket.close()`, pool metrics, protocol/lifecycle |
| **Native memory leak** | RSS/native allocation tăng ngoài heap | Direct buffers, JNI/native allocations, NMT |
| **Thread leak** | Threads sống lâu không cần thiết, stack memory tăng | Executor shutdown, task cancellation |
| **Database cursor leak** | Cursor/statement resource exhaustion | `ResultSet`, `Statement`, driver/pool semantics |
| **Mapped memory retention** | Memory mappings/handles persist | Mapped buffers và API unmap/lifecycle |
| **Class loader retention** | Metaspace/class counts tăng sau redeploy | Loader references, reflection caches, listeners |

Một resource leak có thể dẫn đến memory pressure, nhưng **không bắt buộc luôn biểu hiện trước bằng `OutOfMemoryError: Java heap space`**. Một heap leak cũng không nhất thiết liên quan FD count.

**Đừng dùng “GC log trông bình thường” để bác bỏ resource leak.** GC logs quan sát memory-management behavior, không đếm mọi external resource đang giữ.

## 18. Chẩn đoán trên JVM và hệ điều hành

### 18.1. Đếm file descriptors

Trên Linux, có thể xem OS-level FD count với những công cụ như `lsof` hoặc `/proc/<pid>/fd` (phụ thuộc quyền truy cập/container):

```bash
lsof -p <pid>
ls /proc/<pid>/fd
```

`<pid>` là placeholder, thay bằng PID thật của Java process. Đây là lệnh quan sát phục vụ chẩn đoán; không phải hành vi phải chạy trong chương trình Java.

**Không phải mọi nền tảng đều có `/proc` hoặc `lsof`.** Windows có công cụ handles/process monitoring riêng; không chuyển lệnh Linux sang Windows rồi kỳ vọng chạy được.

### 18.2. Theo dõi pool và sockets

- Database connection pool: active/idle/pending/timeouts.
- HTTP client connection pool: leased/idle/available connections.
- Server sockets: accepted connections, thời điểm đóng, số concurrent connections.
- OS socket states: established, close-wait, time-wait… phải diễn giải theo TCP semantics và OS, không xem mọi `TIME_WAIT` là leak.

Ví dụ nhiều `CLOSE_WAIT` kéo dài có thể gợi ý phía local chưa đóng socket sau khi peer đóng, nhưng cần đối chiếu application behavior và hệ điều hành.

### 18.3. JVM tools

Trên HotSpot JDK có thể dùng:

```bash
jcmd -l
jcmd <pid> GC.class_histogram
jcmd <pid> Thread.print
```

Để xem native memory theo NMT nếu đã bật từ startup:

```bash
jcmd <pid> VM.native_memory summary
```

**NMT không phải bộ đếm FDs/sockets.** Nó theo dõi nhiều hạng mục native allocations của VM, không nhất thiết bao gồm toàn bộ thư viện native bên ngoài hoặc lifecycle của mọi connection.

`GC.class_histogram` cho thấy số instance Java theo type, nhưng không chứng minh bao nhiêu file handles chưa đóng. Một `FileInputStream` object có thể còn trong heap nhưng đã đóng; một provider có thể có wrappers pooling/handles riêng.

### 18.4. Resource telemetry quan trọng hơn một lần lấy heap dump

Nên theo dõi theo thời gian:

- FD/handle count.
- Socket count theo trạng thái.
- Pool active/idle/waiting.
- Open-file/channel counts nếu thư viện công bố metrics.
- Heap allocated/live/committed và GC.
- Native/RSS memory.
- Rate của successful/failed close.
- Latency và timeout của resource acquisition.

Dùng cùng workload để so sánh trước/sau bản sửa. Không kết luận “sửa leak” chỉ vì một snapshot có con số thấp.

### 18.5. Quan sát close có xảy ra trong mọi control path?

Một kỹ thuật kiểm thử là wrap resource bằng lớp có đếm:

```java
final class CloseCounter implements AutoCloseable {
    int closes;
    @Override
    public void close() { closes++; }
}
```

Đây là snippet minh họa. Có thể dùng nó trong unit test để xác minh cleanup dù body ném exception hoặc return sớm. Với concurrency, dùng thread-safe counters nếu nhiều threads thao tác cùng đối tượng.

## 19. Trường hợp dễ bỏ sót: phản hồi HTTP và stream trả về

Ví dụ một thư viện HTTP cho phép truy cập **response body dưới dạng stream**. Dù client object/response wrapper còn scope ngắn, body stream hoặc response object có thể phải đóng theo tài liệu để:

- Trả connection về pool.
- Tránh leak underlying socket.
- Cho phép tái sử dụng connection.
- Đảm bảo chunked/body data được xử lý theo chính sách hợp lệ.

Với Java 11+ `java.net.http.HttpClient`, các body handlers khác nhau có lifecycle khác nhau. Đặc biệt, nếu nhận body dưới dạng `InputStream`, caller cần quản lý đóng stream theo API; không suy luận chỉ từ `HttpClient` object có bị GC hay chưa.

Một ứng dụng có thể dùng hàng nghìn HTTP requests nhưng lại giữ response streams lâu hơn yêu cầu, làm cạn connection pool trước khi Java heap hết.

## 20. Thiết kế ownership theo tầng

Một hướng kiến trúc rõ ràng:

```text
Application startup
     |
     +--> tạo long-lived pools/clients
     |         |
     |         +--> shutdown một lần lúc application stop
     |
     +--> mỗi request / task
               |
               +--> borrow connection/stream
               |
               +--> try-with-resources
               |       |
               |       +--> xử lý
               |       +--> commit/rollback theo nghiệp vụ
               |       +--> close / trả pool slot
               |
               +--> trả response
```

Không bắt buộc tạo/đóng một client heavyweight cho mọi request. Một số clients/pools **được thiết kế để tái sử dụng** và phải được đóng lúc application shutdown, còn các sessions/connections/response streams có scope ngắn hơn.

### 20.1. Bảng câu hỏi nên ghi trong API contract

| Câu hỏi | Ví dụ câu trả lời cần có |
| --- | --- |
| Ai tạo resource? | Factory hoặc pool |
| Ai sở hữu? | Caller, callee, application singleton |
| Ai có quyền đóng? | Owner hoặc wrapper có trách nhiệm |
| Đóng bằng cách nào? | `close`, `shutdown`, `rollback`, `cancel` |
| Khi nào đóng? | Cuối request, cuối transaction, application shutdown |
| Nếu close lỗi thì sao? | Propagate/log/retry/mark failure phù hợp |
| Dùng đồng thời có an toàn không? | Theo tài liệu thread-safety |
| Sau close có được tái sử dụng? | Theo contract từng API |
| Có fallback Cleaner không? | Chỉ bảo vệ phụ, không phụ thuộc deadline |

### 20.2. Bọc tài nguyên trong abstraction có lifecycle

Nếu business code thao tác file/native handle phức tạp, hãy tạo class **implement `AutoCloseable`**, có state machine rõ và tài liệu ownership. Sau đó callers dùng try-with-resources để đóng tài nguyên **dự đoán được**, không phải một collection event.

## 21. Những hiểu lầm phổ biến

### Sai lầm 1: “Java có GC nên không cần `close()`”
GC dọn Java heap theo reachability, không bảo đảm đóng mọi external resource đúng thời điểm.

### Sai lầm 2: “Biến ra khỏi `{ }` là OS file descriptor giải phóng”
Lexical scope không là deadline của OS resource. Cleanup phải dựa theo lifecycle/ownership.

### Sai lầm 3: “Đặt stream = null thì file đóng”
Đặt null chỉ thay reference edge. Không buộc library gọi close hay OS release handle ngay.

### Sai lầm 4: “`System.gc()` là cách chuẩn để dọn sockets”
Không. GC scheduling không phải network resource release API.

### Sai lầm 5: “Một resource đã close thì Java object phải biến mất”
Java wrapper vẫn có thể reachable; close và reclaim là hai trạng thái khác nhau.

### Sai lầm 6: “Nếu heap có nhiều dung lượng thì không thể hết FD”
FD pool/OS handles có giới hạn độc lập.

### Sai lầm 7: “`close()` của pooled JDBC connection chắc chắn đóng physical TCP socket”
Không. Trong pool, close có thể là trả logical connection về pool.

### Sai lầm 8: “try-with-resources chỉ close lúc body chạy thành công”
Sai. Java gọi close cả khi body ném exception hoặc return sớm; cần đọc primary/suppressed exception rules.

### Sai lầm 9: “Close exception luôn thay thế exception gốc”
Không. try-with-resources có suppressed exceptions để giữ thông tin đóng thất bại khi body đã có primary exception.

### Sai lầm 10: “Mọi `AutoCloseable.close` đều idempotent và thread-safe”
Không. Phải đọc hợp đồng cụ thể; tự viết `close` thread-safe khi có multi-thread ownership.

### Sai lầm 11: “Đóng `FileChannel` luôn unmap mapped buffer ngay”
Không có bảo đảm portable như vậy.

### Sai lầm 12: “Socket.close xác nhận remote server đã commit”
Không. TCP close không thay application-level acknowledgement.

### Sai lầm 13: “Cleaner thay được transaction rollback/commit”
Không. Cleaner do GC kích hoạt không có deadline hoặc transaction semantics.

### Sai lầm 14: “Làm Cleaner action gọi `this.close()` là an toàn”
Có thể giữ strong reference tới referent, khiến action không bao giờ chạy theo đường GC. Nên tách State khỏi wrapper.

### Sai lầm 15: “Finalizer chắc chắn chạy trước shutdown”
Không. Finalization deprecated for removal và không cho progress guarantee.

### Sai lầm 16: “GC heap ổn định thì không có native leak”
Sai. Native allocations, FD counts và sockets độc lập.

### Sai lầm 17: “`ThreadLocal` tự clear khi HTTP request kết thúc”
Sai. Worker thread có thể sống qua nhiều requests; request-scope cleanup cần explicit remove.

### Sai lầm 18: “Close/cleanup lỗi có thể bỏ qua vì GC sẽ xử lý lại”
Không có guarantee GC sẽ sửa được tình trạng resource đang lỗi hay chạy đúng logic cleanup thêm một lần.

## 22. Bài tập tự kiểm tra và đáp án

**Câu 1.** Tại sao `new FileInputStream(path)` tạo một Java object không có nghĩa file sẽ đóng khi biến local hết scope?

**Đáp án:** Vì wrapper object và OS file descriptor có vòng đời khác nhau. GC không bảo đảm tự gọi close đúng thời điểm; dùng try-with-resources.

**Câu 2.** Khi `InputStream.close()` chạy thành công, Java wrapper có được GC ngay không?

**Đáp án:** Không bắt buộc. Wrapper có thể vẫn reachable; close quản lý tài nguyên chứ không free Java heap object.

**Câu 3.** Hai `AutoCloseable` được khai báo theo thứ tự `a` rồi `b` trong try-with-resources. Thứ tự close là gì?

**Đáp án:** `b.close()` trước `a.close()`.

**Câu 4.** Body ném `IllegalStateException`, close ném `IOException`. Với try-with-resources, đâu là primary exception?

**Đáp án:** Thông thường `IllegalStateException` từ body là primary; `IOException` từ close được lưu trong suppressed exceptions của primary theo quy tắc.

**Câu 5.** `Connection.close()` trong JDBC pool có nhất thiết đóng physical socket không?

**Đáp án:** Không. Provider có thể trả logical connection về pool; đọc tài liệu của pool/driver.

**Câu 6.** Heap còn 300 MiB free nhưng process mở file mới thất bại do FD limit. Tăng `-Xmx` là giải pháp gốc không?

**Đáp án:** Không. Cần tìm file/socket handles mở mà chưa close, giới hạn OS và lifecycle của chúng.

**Câu 7.** `System.gc()` có là cách chắc chắn release socket không?

**Đáp án:** Không. Dùng explicit `Socket.close()` hoặc try-with-resources.

**Câu 8.** Một Cleaner action capture chính wrapper đang đăng ký sẽ gây nguy cơ gì?

**Đáp án:** Strong reference từ action tới referent có thể khiến object không trở thành phantom reachable, ngăn automatic cleaning.

**Câu 9.** Tại sao khi dùng Cleaner vẫn nên gọi `Cleanable.clean()` từ `close()`?

**Đáp án:** Để cleanup theo lịch do caller kiểm soát; không phụ thuộc khi nào GC báo phantom reachability.

**Câu 10.** `Reference.reachabilityFence(owner)` có tự đóng file không?

**Đáp án:** Không. Nó đảm bảo owner strongly reachable qua điểm gọi, không thực hiện resource close.

**Câu 11.** `Socket.close()` có chứng minh server đã xử lý và lưu thành công transaction không?

**Đáp án:** Không. Cần application-level response/acknowledgement phù hợp.

**Câu 12.** Vì sao đóng `FileChannel` không đủ để khẳng định mapped buffer đã được unmap ngay?

**Đáp án:** Mapping có lifecycle/semantics riêng; channel close không áp đặt một guarantee unmap tức thì cho mọi JDK.

**Câu 13.** Một ThreadLocal value còn giữ object graph sau request; caller local đã ra scope. Object còn sống bằng cách nào?

**Đáp án:** Worker thread giữ thread-local map entry/value. Dùng `remove()` khi request kết thúc nếu state chỉ thuộc request.

**Câu 14.** `CleanerSafetyDemo` tự in `cleaned once` bằng cơ chế gì?

**Đáp án:** `try-with-resources` gọi `close()`, và close gọi `cleanable.clean()` explicit; không cần GC.

**Câu 15.** Một client HTTP dùng connection pool nên được tạo và đóng cho mỗi request không?

**Đáp án:** Không nhất thiết. Có thể reuse client/pool lâu dài; response body streams hoặc borrowed connections được đóng ở scope ngắn hơn theo API.

**Câu 16.** Chỉ xem `GC.class_histogram` có đủ kết luận file handles được đóng đúng không?

**Đáp án:** Không. Phải quan sát FD count, close behavior và resource ownership; histogram chỉ cho số Java objects theo type.

**Câu 17.** Tại sao nên xem suppressed exceptions?

**Đáp án:** Vì close của resource có thể thất bại khi body đã có lỗi chính; suppressed exceptions lưu nguyên nhân đóng thất bại có giá trị chẩn đoán.

**Câu 18.** `ByteBuffer.allocateDirect` có thể làm tăng native memory mà heap usage không tăng tương ứng không?

**Đáp án:** Có. Direct buffer liên quan native/off-heap memory; accounting và reclamation phụ thuộc VM.

## 23. Checklist áp dụng trong dự án

1. Với mỗi tài nguyên, ghi rõ **owner, borrow semantics, cách đóng và điểm đóng**.
2. Ưu tiên **try-with-resources** cho `AutoCloseable` với scope hữu hạn.
3. Đóng resource theo thứ tự phù hợp, tránh double-close shared handle.
4. Giữ suppressed exceptions khi body và close đều thất bại.
5. Trong JDBC, phân biệt transaction lifecycle, statement/result set và connection pool semantics.
6. Trong network code, phân biệt close local, half-close, timeout và acknowledgement nghiệp vụ.
7. Dùng explicit shutdown/cancellation cho executors, tasks, streams/listeners theo API.
8. Với `ThreadLocal` request data, dùng `finally` để `remove()` khi thích hợp.
9. Dùng Cleaner chỉ như **fallback**, bảo đảm action không capture referent.
10. Không dựa vào `finalize`, `System.gc()` hoặc `Thread.sleep` như cách đóng tài nguyên.
11. Với native wrappers, cân nhắc `reachabilityFence` và đồng bộ ownership khi có cạnh tranh giữa use/close.
12. Tách metrics heap/GC khỏi FD counts, socket states, pool metrics và native RSS.
13. Test đường success, exception, timeout, cancellation, partial acquisition và shutdown.
14. Đo resource usage qua nhiều requests/redeploy cycles thay vì một snapshot.
15. Nếu OS handle count tăng mãi, sửa **resource lifecycle** trước khi chỉ tăng giới hạn hệ điều hành.
16. Khi dùng mapped memory hoặc native FFM, đọc hợp đồng API theo JDK mục tiêu, tránh private implementation shortcuts.
17. Đảm bảo log lỗi đóng có ngữ cảnh nhưng không làm lộ secrets/PII.
18. Đừng tuyên bố **GC “không bao giờ” giúp release resource**: một số library có fallback cleanup; nhận định đúng là **GC không là cơ chế release deterministic theo deadline**.

### Tóm tắt cuối

```text
                Java object wrapper
                       |
        +--------------+---------------+
        |                              |
        v                              v
  Heap reachability            External resource state
        |                              |
        v                              v
  GC may reclaim               explicit close / release
  object memory                (owner-controlled)
        |                              |
        +--------------+---------------+
                       |
         KHÔNG đồng nghĩa cùng thời điểm

try-with-resources:
  cấp phát -> sử dụng -> close chắc chắn theo Java control flow
  (khi thực thi tới các điểm tương ứng; close vẫn có thể thất bại)

Cleaner:
  fallback cleanup theo phantom reachability;
  không có deadline, nên explicit clean/close là đường chính
```

**Thông điệp cần nhớ:** **GC quản lý bộ nhớ Java objects; ứng dụng phải quản lý tài nguyên bên ngoài theo hợp đồng sở hữu và đóng rõ ràng.** File descriptor, socket, connection, native allocation và worker threads không được phép phụ thuộc vào lúc một biến hết scope hay lúc collector tình cờ chạy.

### Tài liệu chuẩn

- [JVMS §2.5.3 — Heap (Java SE 17)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3): heap objects và automatic storage management.
- [JLS §14.20.3 — try-with-resources (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): quy tắc khởi tạo/đóng theo thứ tự ngược, exceptions và suppressed exceptions.
- [AutoCloseable API (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng close và khuyến nghị try-with-resources.
- [Closeable API (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html): close với I/O resources.
- [Cleaner API (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): phantom reachability, explicit `clean` và ngăn action capture referent.
- [Reference.reachabilityFence API (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object)): giữ mạnh wrapper tới điểm dùng cuối.
- [Socket API (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): close, half-close và timeout.
- [Files.newBufferedWriter (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#newBufferedWriter(java.nio.file.Path,java.nio.charset.Charset,java.nio.file.OpenOption...)): mở writer trên filesystem.
- [Connection API (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): transaction và close theo JDBC.
- [OpenJDK JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421): hạn chế và lộ trình loại bỏ finalization.
