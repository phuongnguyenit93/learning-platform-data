# Giới hạn file descriptor và số tài nguyên đang mở trong Java I/O

## 1. Tại sao một chương trình Java có thể mở được file nhưng lại hết tài nguyên?

Một ứng dụng xử lý tệp lớn thường không bị giới hạn chỉ bởi dung lượng RAM hoặc tốc độ đọc/ghi. Nó còn phải chia sẻ các **tài nguyên hệ điều hành**: file descriptors, handles, sockets, directory streams, bộ nhớ native và các cấu trúc quản lý I/O.

Khi một chương trình mở tệp, thư mục, kết nối mạng hoặc một số loại channel, hệ điều hành thường cần cấp tài nguyên để theo dõi đối tượng đang mở. Trên các hệ thống giống Unix, ứng dụng tương tác với **file descriptor (FD)**, thường là một số nguyên trong bảng descriptor của tiến trình. Trên Windows, cách biểu diễn thường liên quan đến **handles**; không nên giả định mọi tài nguyên đều có một số FD Unix.

~~~text
Java process / JVM
    |
    +-- FileInputStream ─────┐
    +-- FileChannel ─────────┤
    +-- SocketChannel ───────┤
    +-- ServerSocket ────────┤
    +-- DirectoryStream ─────┤ → tài nguyên của OS / provider
    +-- ZipFile ─────────────┤ → giới hạn tiến trình hoặc hệ thống
    +-- Selector / watcher ──┘
    |
    +-- Threads / ByteBuffers / native memory (tài nguyên khác)
~~~

Không có quy tắc phổ quát **mỗi object Java tương ứng đúng một descriptor**. Một object có thể dùng chung tài nguyên nền với object khác; một abstraction có thể cần nhiều handle hoặc tài nguyên native; filesystem provider không phải lúc nào cũng triển khai bằng file descriptor của hệ điều hành. Vì vậy, hãy xem số FD/handle là **tài nguyên hữu hạn cần giám sát**, không phải suy ra trực tiếp bằng cách đếm object trong heap.

**Mục tiêu của bài học:** hiểu ý nghĩa các giới hạn mở tệp, hậu quả khi vượt giới hạn, cách đóng tài nguyên trong Java 17+, công cụ chẩn đoán và cách giới hạn concurrency để ứng dụng phục vụ tải lớn mà không tự làm cạn FD.

## 2. File descriptor là gì?

Trên Unix/Linux, một file descriptor là một số nguyên mà tiến trình dùng để tham chiếu một mục trong bảng descriptor. Hệ điều hành quản lý thông tin nền về tài nguyên tương ứng, chẳng hạn file đang mở, socket hoặc pipe.

Các descriptor chuẩn thường gặp:

| FD | Tên | Vai trò thông thường |
| ---: | --- | --- |
| 0 | stdin | Đầu vào chuẩn của tiến trình |
| 1 | stdout | Đầu ra chuẩn |
| 2 | stderr | Đầu ra báo lỗi |

Các descriptor khác có thể được cấp khi ứng dụng mở file, socket, pipe, thư mục hoặc một tài nguyên tương ứng. **Đừng mặc định các số 0–2 luôn trỏ tới terminal**: trong container, service hoặc chương trình có redirect, chúng có thể trỏ tới pipe, file log hoặc bị thay thế.

Ví dụ server Java có 800 kết nối TCP đồng thời và vài chục file log/dữ liệu đang mở sẽ tiêu thụ một lượng tài nguyên OS đáng kể, dù các request rất nhỏ. Cài đặt một `Selector` để quản lý nhiều socket bằng một thread **không xóa nhu cầu tài nguyên OS của chính từng socket**.

### FD và Java FileDescriptor không hoàn toàn đồng nghĩa

Java có `java.io.FileDescriptor` và những lớp như `FileInputStream`, `RandomAccessFile`, `FileChannel`. Nhưng việc tồn tại class `FileDescriptor` không có nghĩa đây là một công cụ portable để **đếm mọi file descriptor** đang mở trong JVM.

Tương tự, số lượng object `FileChannel` trong heap không phải phép đo chính xác tổng số FD của tiến trình. Muốn biết áp lực tài nguyên thực, dùng metric hoặc công cụ phù hợp với OS, kết hợp giám sát ở tầng ứng dụng.

## 3. Những giới hạn nào có thể gây ra lỗi?

Giới hạn thay đổi theo hệ điều hành, user, container, chính sách service và loại tài nguyên.

### 3.1. Giới hạn trên mỗi tiến trình

Trên nhiều hệ thống Unix, giới hạn số file descriptor đang mở đồng thời được kiểm soát bởi tài nguyên `RLIMIT_NOFILE`, với các khái niệm **soft limit** và **hard limit**:

- **Soft limit:** ngưỡng mà tiến trình đang chịu khi yêu cầu thêm FD.
- **Hard limit:** trần điều chỉnh soft limit mà tiến trình không có đặc quyền phù hợp không được vượt qua.

Các giá trị thực tế khác nhau giữa máy phát triển, CI, container và server. Không nên ghi cứng rằng “Linux cho phép tối đa 1.024 file” hay “mọi JVM có 65.535 FD”.

Trên Unix/Linux, có thể kiểm tra trong shell:

~~~bash
ulimit -Sn   # soft limit của shell hiện tại
ulimit -Hn   # hard limit của shell hiện tại
~~~

**Chú ý:** hai lệnh này nói về **shell đang chạy**, không nhất thiết phản ánh một JVM đã khởi động từ một service manager khác. Với Linux, xem giới hạn của **tiến trình Java đang chạy** bằng công cụ OS, chẳng hạn `/proc/<PID>/limits` nếu procfs được cho phép.

### 3.2. Giới hạn toàn hệ thống và tài nguyên khác

Ngoài giới hạn per-process, OS còn có giới hạn hoặc áp lực toàn hệ thống, quota người dùng, bộ nhớ kernel, bộ nhớ native và giới hạn của filesystem/provider. Một chương trình có thể thất bại dù chưa đạt tới con số soft limit tưởng tượng, ví dụ khi:

- Nguồn lực chung của kernel không đủ.
- Container hoặc service có chính sách hạn chế riêng.
- File system hoặc thiết bị bị lỗi.
- Quá nhiều socket, mapped regions, native buffers hoặc các tài nguyên đồng thời khác.
- Permission/quota cấm cấp tài nguyên.

Trên Unix, hai mã lỗi nổi tiếng là:

| Mã lỗi OS | Ý nghĩa khái quát |
| --- | --- |
| `EMFILE` | Tiến trình đã đạt giới hạn file descriptor của nó |
| `ENFILE` | Hệ thống đã đạt giới hạn tài nguyên file-open liên quan trên phạm vi rộng hơn |

Java có thể chuyển các lỗi này thành `IOException`, `FileSystemException`, `SocketException` hoặc một ngoại lệ I/O có thông báo chứa `Too many open files`. **Không dựa duy nhất vào text của exception để phân loại lỗi trên mọi hệ điều hành**.

Windows sử dụng cơ chế handle với giới hạn và triệu chứng khác; một số công cụ chỉ hiển thị tổng handle count bao gồm nhiều loại tài nguyên **không phải file**. Do đó không so sánh máy Windows và Linux bằng một con số đơn giản mà không biết phép đo là gì.

## 4. Khi quá nhiều file đang mở, điều gì xảy ra?

Một lỗi không chỉ ảnh hưởng thao tác mở file gây ra nó. Khi JVM hết khả năng lấy tài nguyên mới:

- `Files.newInputStream(path)` hoặc `FileChannel.open(path)` có thể thất bại.
- Server có thể không `accept()` được socket mới hoặc không mở được kết nối outbound.
- Bộ ghi log có thể không mở/rotate file.
- Thread kiểm tra health hay bộ giám sát cũng có thể cần mở socket/file và gặp lỗi.
- Tác vụ xử lý tệp theo batch có thể bị lỗi dây chuyền, retry liên tục làm tình hình tệ hơn.

~~~text
Nhu cầu xử lý tăng
        |
        v
Mở 1 channel cho mỗi task
        |
        v
Task bị giữ lâu / quên close
        |
        v
Số tài nguyên đang mở tăng
        |
        v
Chạm giới hạn OS
        |
        +--> open() thất bại
        +--> socket mới thất bại
        +--> logger / healthcheck có thể thất bại
        |
        v
Retry không giới hạn → càng thêm tải
~~~

**Không nên chữa nguyên nhân bằng cách chỉ tăng `ulimit`.** Tăng giới hạn có thể cần thiết khi tải hợp lệ thực sự cao, nhưng nếu ứng dụng rò rỉ resource thì một mức trần lớn hơn chỉ làm quá trình lỗi diễn ra chậm hơn.

## 5. Những Java API nào cần đóng tài nguyên?

Một quy tắc học tập quan trọng: **không phải cứ object Java không còn tham chiếu là tài nguyên OS được trả lại ngay**. Garbage collector giải phóng bộ nhớ quản lý, còn thời điểm đóng file/socket không được dùng GC như cơ chế điều khiển vòng đời đáng tin cậy.

Một số loại cần quản lý rõ ràng:

| API / tài nguyên | Cách giải phóng thông thường | Lưu ý |
| --- | --- | --- |
| `FileInputStream`, `FileOutputStream` | `close()` / try-with-resources | Giải phóng tài nguyên luồng |
| `BufferedInputStream`, `BufferedOutputStream` | Đóng wrapper | Thường đóng cả stream được bọc; xác định quyền sở hữu |
| `FileReader`, `FileWriter`, `BufferedReader`, `BufferedWriter` | `close()` | Không để reader/writer sống vô hạn |
| `FileChannel`, `SeekableByteChannel` | `close()` | Channel đang mở chiếm tài nguyên tương ứng |
| `RandomAccessFile` | `close()` | Có thể chia sẻ tài nguyên nền với channel liên quan |
| `Socket`, `ServerSocket`, `SocketChannel`, `ServerSocketChannel` | `close()` | Socket cũng sử dụng tài nguyên OS |
| `AsynchronousFileChannel` | `close()` | Xử lý tác vụ pending và executor theo thiết kế |
| `DirectoryStream<Path>` | `close()` | Có thể giữ handle để duyệt thư mục |
| `Stream<Path>` từ `Files.list/walk/find` | `Stream.close()` | Đây là stream gắn với filesystem, không phải stream dữ liệu thuần RAM |
| `Stream<String>` từ `Files.lines` | `Stream.close()` | Giữ file mở trong khi stream tồn tại |
| `ZipFile` | `close()` | Quản lý file archive và dữ liệu nội bộ |
| `WatchService`, `Selector` | `close()` | Giải phóng tài nguyên theo dõi I/O |
| `FileSystem` mở mới như ZIP filesystem | `close()` khi sở hữu | Không gọi `close()` bừa bãi lên default filesystem |
| `MappedByteBuffer` | Không có `close()` chuẩn trực tiếp | Mapping có vòng đời đặc biệt; đóng channel không bảo đảm lập tức unmap |

Các phương thức tiện ích như `Files.readString` và `Files.readAllBytes` tự quản lý luồng bên dưới trong quá trình gọi; bạn không giữ một `InputStream` cần đóng do các phương thức đó trả về. Nhưng chúng có thể cần nhiều RAM nếu tệp rất lớn, là **vấn đề riêng** so với FD.

**Nguyên tắc ownership:** ai mở resource thì phải có trách nhiệm bảo đảm resource được đóng, trừ khi quyền sở hữu đã được bàn giao rõ ràng cho thành phần khác.

## 6. try-with-resources: quy tắc quan trọng nhất

Java `try-with-resources` tự gọi `close()` khi ra khỏi khối, kể cả khi có ngoại lệ:

~~~java
Path path = Path.of("input.dat");

try (InputStream input = Files.newInputStream(path)) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = input.read(buffer)) != -1) {
        // Xử lý đúng n byte của từng lần đọc.
    }
}
~~~

Đoạn trên là **mảnh Java minh họa trong phương thức**, yêu cầu import `java.io.InputStream` và `java.nio.file.*`; file phải tồn tại nếu chạy trực tiếp.

Nếu mở nhiều resource trong một khối, Java đóng theo **thứ tự ngược với thứ tự khai báo**:

~~~java
try (InputStream raw = Files.newInputStream(path);
     BufferedInputStream buffered = new BufferedInputStream(raw)) {
    // Đọc buffered.
}
~~~

Trong ví dụ này, `buffered.close()` thường đóng cả `raw`; cơ chế try-with-resources vẫn gọi `raw.close()` khi đến lượt. Hầu hết lớp stream chuẩn xử lý close lặp an toàn, nhưng không nên tự tạo wrapper bất thường rồi giả định mọi API đều có cùng semantics.

### Ngoại lệ khi close và suppressed exceptions

Nếu code trong khối ném lỗi và `close()` cũng ném lỗi, try-with-resources giữ lỗi chính và lưu những lỗi close liên quan dưới dạng **suppressed exceptions**.

~~~java
try (InputStream input = Files.newInputStream(path)) {
    // Xử lý có thể ném IOException.
} catch (IOException ex) {
    System.err.println("I/O error: " + ex.getMessage());
    for (Throwable suppressed : ex.getSuppressed()) {
        System.err.println("Close error: " + suppressed);
    }
}
~~~

Đây là mảnh minh họa. Không nên cố ý nuốt mọi ngoại lệ trong `finally` vì có thể mất thông tin về tình trạng tài nguyên và dữ liệu chưa được flush.

### Không giao trả một resource sắp bị đóng

Sai về ownership:

~~~java
InputStream openWrong(Path path) throws IOException {
    try (InputStream in = Files.newInputStream(path)) {
        return in; // Khi caller nhận thì stream đã đóng!
    }
}
~~~

Mảnh trên chỉ là minh họa anti-pattern. Nếu một phương thức trả về resource mở để caller dùng tiếp, **không đóng ở callee**; phải quy định caller sở hữu và đóng:

~~~java
InputStream openForCaller(Path path) throws IOException {
    return Files.newInputStream(path);
}
~~~

Caller sau đó phải dùng `try-with-resources`. Lựa chọn an toàn hơn nữa là phương thức nhận callback xử lý bên trong khối và không để resource thoát ra ngoài.

## 7. Đừng bỏ sót resource ẩn trong các stream duyệt file

Một lỗi khó phát hiện là nghĩ rằng Java `Stream` luôn chỉ là pipeline tính toán trong bộ nhớ:

~~~java
// Có nguy cơ để directory stream mở cho tới khi được giải phóng muộn.
Stream<Path> paths = Files.list(root);
long files = paths.count();
~~~

`Files.list(root)` trả `Stream<Path>` **gắn với directory đang mở**; stream đó cần được đóng ngay khi dùng xong. Cách đúng:

~~~java
try (Stream<Path> paths = Files.list(root)) {
    long files = paths.count();
    System.out.println(files);
}
~~~

Tương tự:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
         .forEach(path -> {
             // Xử lý từng path.
         });
}
~~~

`Files.walk(...)` và `Files.find(...)` cũng trả filesystem-backed stream cần đóng. `Files.lines(path)` trả stream các dòng dựa trên file đang mở:

~~~java
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEach(System.out::println);
}
~~~

Những đoạn trên là **mảnh mã minh họa**, cần import `java.util.stream.Stream`, `java.nio.file.Files`, `java.nio.file.Path` và `java.nio.charset.StandardCharsets` phù hợp.

Không nên gọi `Files.list(...)` hàng chục lần trong vòng lặp rồi giữ tất cả stream trong một collection cho tới cuối job. Tốt hơn là mở–duyệt–đóng từng thư mục, hoặc xử lý số lượng stream cùng lúc có giới hạn.

### DirectoryStream khác gì?

`DirectoryStream<Path>` cho phép duyệt entry trực tiếp:

~~~java
try (DirectoryStream<Path> entries =
        Files.newDirectoryStream(root)) {
    for (Path entry : entries) {
        // Xử lý entry.
    }
}
~~~

Cả `DirectoryStream` lẫn stream từ `Files.list` có thể giữ tài nguyên hệ điều hành khi duyệt. Chúng cần vòng đời ngắn, nhất là trong bộ quét cây thư mục lớn.

## 8. Tệp lớn: không nên mở toàn bộ file cùng lúc

Giả sử batch xử lý 50.000 file:

~~~text
Cách dễ thất bại:
- lấy danh sách 50.000 file
- mở FileChannel cho cả 50.000
- để mở trong khi tính toán
- đóng sau khi mọi task hoàn thành

Cách có kiểm soát:
- duyệt file
- mở tối đa K channel cùng lúc
- đọc/ghi theo streaming
- đóng channel trước khi lấy thêm công việc
- giữ queue công việc có giới hạn
~~~

Tăng concurrency không tạo tăng thông lượng vô hạn. Ổ lưu trữ có throughput và IOPS hữu hạn; quá nhiều file mở có thể tăng context switching, cache pressure, memory mapping pressure và chi phí scheduling. Với nhiều tệp nhỏ, việc đọc song song ở mức vừa phải thường tốt hơn việc mở tất cả tài nguyên và giữ chúng.

Để xử lý dữ liệu lớn, ưu tiên:

1. **Bounded concurrency:** giới hạn số file/channel/socket được mở đồng thời.
2. **Streaming:** đọc theo khối thay vì `readAllBytes` vào RAM nếu tệp quá lớn.
3. **Close sớm:** không giữ descriptor trong lúc CPU-bound processing nếu có thể đóng trước.
4. **Không lưu stream/channel trong cache vô hạn:** cache phải có max size, eviction và cơ chế đóng.
5. **Backpressure:** khi worker bận, giảm tốc độ lấy job mới thay vì mở thêm file.
6. **Dự phòng headroom:** đừng dùng hết mọi FD còn có thể cấp; logging, sockets và thư viện hệ thống cũng cần tài nguyên.

Con số K không có một mức tối ưu cho mọi máy. Phải đo throughput, latency, active FD, lỗi I/O và memory footprint trên môi trường vận hành thực tế.

## 9. Semaphore: tạo ngân sách riêng cho số channel đang mở

`java.util.concurrent.Semaphore` là một primitive để điều khiển số permit được sử dụng đồng thời. Một permit có thể đại diện cho quyền **mở một file channel** trong subsystem do ứng dụng quản lý.

~~~text
Budget = 3 permits

Task 1 lấy 1 permit → mở channel A
Task 2 lấy 1 permit → mở channel B
Task 3 lấy 1 permit → mở channel C
Task 4 không còn permit → chờ, trả lỗi hoặc retry có kiểm soát

A đóng channel và trả permit
Task 4 có thể mở file tiếp
~~~

**Semaphore không thay đổi `ulimit` và không đo FD của hệ điều hành.** Nó chỉ giúp ứng dụng tuân thủ một ngân sách do mình đặt ra. Những file/socket được mở ngoài subsystem vẫn cần tính vào headroom tổng thể.

Một mô hình tốt có ba thuộc tính:

- Lấy permit **trước khi mở** tài nguyên.
- Nếu mở thất bại, **trả permit** ngay; không giữ permit bị thất lạc.
- Nếu mở thành công, resource wrapper trả permit trong `close()`, ngay cả khi quá trình sử dụng có lỗi.

Nếu dùng `Semaphore.acquire()` để đợi permit, cần xác định timeout/interrupt/cancellation. Nếu dùng `tryAcquire()` để trả lỗi nhanh, upstream cần chính sách retry hoặc backpressure thích hợp, không retry tight loop.

## 10. Ví dụ Java 17+ chạy độc lập: giới hạn hai FileChannel

Ví dụ dưới dùng một **ngân sách nhân tạo** gồm hai permit, không cố tạo hàng nghìn FD hoặc đẩy máy tới giới hạn thật. Nó mở hai file channel, thử mở cái thứ ba (bị từ chối an toàn), đóng một channel rồi mở cái thứ ba thành công.

Kết quả là deterministic và không phụ thuộc giới hạn file descriptor của hệ điều hành, miễn là môi trường cho phép tạo ba file tạm và mở hai channel thông thường.

Lưu thành `FileDescriptorBudgetDemo.java`:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.Semaphore;

public class FileDescriptorBudgetDemo {

    static final class Budget {
        private final Semaphore permits;

        Budget(int maximumOpenFiles) {
            if (maximumOpenFiles <= 0) {
                throw new IllegalArgumentException("maximum must be positive");
            }
            this.permits = new Semaphore(maximumOpenFiles);
        }

        Lease open(Path path) throws IOException {
            if (!permits.tryAcquire()) {
                throw new IllegalStateException("Application budget exhausted");
            }

            boolean successful = false;
            try {
                FileChannel channel =
                        FileChannel.open(path, StandardOpenOption.READ);
                successful = true;
                return new Lease(channel, permits);
            } finally {
                if (!successful) {
                    permits.release();
                }
            }
        }

        int available() {
            return permits.availablePermits();
        }
    }

    static final class Lease implements AutoCloseable {
        private final FileChannel channel;
        private final Semaphore permits;
        private boolean closed;

        Lease(FileChannel channel, Semaphore permits) {
            this.channel = channel;
            this.permits = permits;
        }

        FileChannel channel() {
            if (closed) {
                throw new IllegalStateException("Lease already closed");
            }
            return channel;
        }

        @Override
        public void close() throws IOException {
            if (!closed) {
                closed = true;
                try {
                    channel.close();
                } finally {
                    permits.release();
                }
            }
        }
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("fd-budget-");
        Path first = dir.resolve("one.txt");
        Path second = dir.resolve("two.txt");
        Path third = dir.resolve("three.txt");

        try {
            Files.writeString(first, "one", StandardCharsets.US_ASCII);
            Files.writeString(second, "two", StandardCharsets.US_ASCII);
            Files.writeString(third, "three", StandardCharsets.US_ASCII);

            Budget budget = new Budget(2);

            try (Lease one = budget.open(first)) {
                try (Lease two = budget.open(second)) {
                    System.out.println("available with two open="
                            + budget.available());

                    boolean rejected = false;
                    try (Lease extra = budget.open(third)) {
                        // Không tới đây khi budget đã hết.
                    } catch (IllegalStateException ex) {
                        rejected = true;
                    }
                    System.out.println("third rejected=" + rejected);
                }

                System.out.println("available after second closes="
                        + budget.available());

                try (Lease three = budget.open(third)) {
                    ByteBuffer buffer = ByteBuffer.allocate(16);
                    three.channel().read(buffer);
                    buffer.flip();
                    System.out.println("third content="
                            + StandardCharsets.US_ASCII.decode(buffer));
                }
            }

            System.out.println("available after all closes="
                    + budget.available());
        } finally {
            Files.deleteIfExists(first);
            Files.deleteIfExists(second);
            Files.deleteIfExists(third);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac FileDescriptorBudgetDemo.java
java FileDescriptorBudgetDemo
~~~

Stdout trong môi trường đọc/ghi tệp tạm bình thường:

~~~text
available with two open=0
third rejected=true
available after second closes=1
third content=three
available after all closes=2
~~~

Diễn giải:

1. `Budget(2)` tạo hai permit: tối đa hai channel do **subsystem này** sở hữu được mở đồng thời.
2. Mở `one` lấy permit đầu; mở `two` lấy permit thứ hai. `available() == 0`.
3. Lần mở `third` tiếp theo bị từ chối **trước khi gọi FileChannel.open** vì hết permit, tránh cố chạm ngưỡng OS.
4. Khối try-with-resources của `two` kết thúc, `Lease.close()` đóng channel và trả một permit. `available() == 1` trong khi `one` vẫn mở.
5. Mở `three` dùng lại permit vừa được trả; đọc file `three.txt` và in `three`.
6. `three` rồi `one` được đóng; tất cả permit được trả về, `available() == 2`.
7. Nếu `FileChannel.open` thất bại, khối `finally` trong `Budget.open` cũng trả permit để không gây rò rỉ ngân sách.
8. Nếu thao tác trong khối try ném lỗi, try-with-resources vẫn gọi `close()`. Ví dụ dùng `boolean closed` đơn giản phù hợp khi mỗi `Lease` thuộc quyền sở hữu một luồng; trong hệ thống đa luồng có thể dùng `AtomicBoolean` nếu nhiều thread có khả năng đóng cùng lease.

**Giới hạn ví dụ:** permit không tương đương số lượng FD chính xác của OS. `available()==2` chỉ chứng minh không còn lease mở do wrapper này theo dõi, **không** khẳng định JVM không có file descriptor nào khác. Nếu `channel.close()` ném IOException, mã vẫn hoàn trả permit của ngân sách ứng dụng; ứng dụng production cần log/chẩn đoán lỗi close và không tự khẳng định tài nguyên OS đã giải phóng thành công trong mọi trường hợp.

## 11. Lỗi mở file thất bại giữa chừng: phải trả permit và đóng thứ đã mở

Khi job cần nhiều resource, các lỗi có thể xuất hiện ở bước thứ hai hoặc thứ ba:

~~~text
acquire permit A → open file A thành công
acquire permit B → open file B thất bại
                    |
                    └── nếu không finally:
                           permit B bị mất
                           file A có thể bị giữ mở
~~~

Một cách tổ chức tốt là **cấu trúc ownership theo lexical scope**:

~~~java
try (FileChannel input = FileChannel.open(inPath,
             StandardOpenOption.READ);
     FileChannel output = FileChannel.open(outPath,
             StandardOpenOption.CREATE,
             StandardOpenOption.WRITE)) {
    // Chuyển dữ liệu với vòng read/write kiểm tra số byte.
}
~~~

Đây là mảnh minh họa, có `Path inPath`/`outPath` hợp lệ. Nếu lần mở `output` thất bại, resource `input` đã mở sẽ được đóng tự động theo ngữ nghĩa try-with-resources.

Nếu job giữ channel trong queue tới lúc worker chạy thì việc đếm resource cần bao gồm **thời gian chờ trong queue**. Thường tốt hơn là đưa **Path**/ID vào queue, và chỉ mở channel **khi worker thực sự sẵn sàng xử lý**.

## 12. Giám sát số FD trên Linux

Trên Linux, một số nguồn quan sát hữu ích (cần quyền truy cập phù hợp):

~~~bash
# Xem soft/hard limit của shell đang chạy:
ulimit -Sn
ulimit -Hn

# Xem giới hạn được hệ điều hành công bố cho tiến trình:
cat /proc/<PID>/limits

# Liệt kê descriptor hiện đang mở của tiến trình:
ls -l /proc/<PID>/fd

# Đếm các entry trong /proc/<PID>/fd:
ls -1 /proc/<PID>/fd | wc -l

# Lệnh lsof (nếu được cài) để xem tài nguyên của tiến trình:
lsof -p <PID>
~~~

`<PID>` là placeholder cho process ID thực tế, không gõ nguyên chuỗi có dấu ngoặc nhọn vào shell. Những lệnh này là hướng dẫn cho Linux/Unix, **không chạy trực tiếp trên Windows PowerShell**.

Cẩn thận với phép đếm từ `/proc/<PID>/fd`: số lượng có thể thay đổi trong lúc đọc; permission hoặc container namespace có thể che một phần dữ liệu. Đếm bằng `lsof` và bằng procfs đôi khi cho kết quả khác do cách hiển thị resource và thời điểm quan sát. Dùng một nguồn metric nhất quán để xem **xu hướng**, không kết luận “không có leak” từ một snapshot duy nhất.

### Trên macOS và Windows

- **macOS/Unix:** `lsof -p PID` thường hữu ích để xem open files/sockets; giới hạn launch context có thể khác giữa shell và service.
- **Windows:** dùng Process Explorer, Resource Monitor hoặc công cụ giám sát handle của tiến trình. **Handle count** thường bao gồm cả loại handle khác file; đừng gọi số đó là “số file descriptor Unix”.
- **Trong container/service:** so sánh đúng process limit đang áp dụng, không chỉ cấu hình của interactive shell mà lập trình viên đang đăng nhập.

Khi xảy ra lỗi “Too many open files”, thu thập **thời điểm**, **PID**, **loại resource tăng**, **số resource đang mở**, **giới hạn của chính process** và **stack trace của thao tác thất bại** để khoanh vùng nguyên nhân.

## 13. Quan sát FD từ Java trên hệ thống Unix hỗ trợ

JDK có một extension monitoring bean trên các nền tảng hỗ trợ Unix, thường qua `com.sun.management.UnixOperatingSystemMXBean`:

~~~java
import java.lang.management.ManagementFactory;

public class FdMetricDemo {
    public static void main(String[] args) {
        java.lang.management.OperatingSystemMXBean os =
                ManagementFactory.getOperatingSystemMXBean();

        if (os instanceof com.sun.management.UnixOperatingSystemMXBean unix) {
            System.out.println("open FDs="
                    + unix.getOpenFileDescriptorCount());
            System.out.println("max FDs="
                    + unix.getMaxFileDescriptorCount());
        } else {
            System.out.println("Unix FD metric unavailable");
        }
    }
}
~~~

Đây là **chương trình Java 17+ chạy độc lập**, nhưng stdout phụ thuộc hệ điều hành và trạng thái tiến trình:

~~~bash
javac FdMetricDemo.java
java FdMetricDemo
~~~

Trên một runtime có hỗ trợ Unix bean, kết quả là hai con số động `open FDs=...` và `max FDs=...`. Trên platform không có extension đó, output là:

~~~text
Unix FD metric unavailable
~~~

Các phương thức `getOpenFileDescriptorCount()` và `getMaxFileDescriptorCount()` là extension JDK/platform, **không phải phần có thể giả định luôn tồn tại trên mọi Java implementation**. Ở một số nền tảng, metric có thể không khả dụng hoặc có cách diễn giải/giá trị đặc biệt theo implementation.

Đừng log hai con số mỗi microsecond chỉ để kiểm tra leak; sampling theo chu kỳ có mục tiêu, alert theo tỉ lệ `open/max` và theo xu hướng sau khi tải ngừng sẽ hữu ích hơn.

## 14. Làm sao phân biệt FD leak với tải đồng thời hợp lệ?

Giả sử monitor báo:

~~~text
Thời gian    Active requests    Open FDs
10:00             10               120
10:05            500               610
10:10             10               125
~~~

Số FD tăng khi tải tăng, rồi gần trở về baseline có thể là hành vi bình thường. Nhưng:

~~~text
Thời gian    Active requests    Open FDs
10:00             10               120
10:05            500               610
10:10             10               605
10:20             10               900
~~~

Nếu số tài nguyên tiếp tục cao hoặc tăng khi lưu lượng đã thấp, cần điều tra leak hoặc cache/pool mở quá rộng. Tuy nhiên, **chỉ ba số đo không tự chứng minh leak**: resource pooling, idle socket timeout hoặc startup behavior cũng có thể khiến baseline thay đổi. Phải kết hợp với stack traces, thông tin active resources và thiết kế ứng dụng.

Một quy trình:

1. Ghi nhận baseline sau startup và sau warm-up.
2. Chạy workload có mức đồng thời biết trước.
3. Đo active FD/handle và số channel/socket do ứng dụng quản lý.
4. Chờ job hoàn tất, theo dõi các resource có quay về mức kỳ vọng hay không.
5. Nếu không, khoanh vùng theo API (file, socket, directory stream, ZipFile...).
6. Dùng profiling, metrics ownership hoặc log tạm có stack mở/đóng với sampling để truy vị trí quên close.
7. Xác minh bằng bài test lặp nhiều vòng mà không phải tăng tải vô hạn.

Nếu cần instrument việc tạo resource, nên để một factory/wrapper hoặc resource manager chịu trách nhiệm cấp và đóng tài nguyên, tránh rải lệnh `FileChannel.open` trong hàng chục lớp mà không có nơi ghi nhận.

## 15. File descriptor có liên quan gì đến memory mapping?

`FileChannel.map(...)` tạo một `MappedByteBuffer` gắn với một vùng dữ liệu file thông qua cơ chế memory mapping. Đây là kỹ thuật hữu ích khi xử lý file lớn nhưng nó có giới hạn riêng.

Điều cần tránh:

- Không giả định mỗi mapping dùng đúng một FD suốt vòng đời; OS có cơ chế mapping khác nhau.
- `FileChannel.close()` **không bảo đảm** mapping tự biến mất ngay khi channel đóng.
- `MappedByteBuffer` không cung cấp `close()` chuẩn như `FileChannel`.
- Vòng đời mapping có thể liên quan đến GC, bộ nhớ địa chỉ, tài nguyên native và khả năng sửa/xóa tệp trên một số hệ điều hành.
- Mapping hàng nghìn vùng rất lớn có thể gây áp lực tài nguyên khác ngay cả khi không tăng open FD theo cách trực tiếp.

Nếu không thật sự cần random access mapping, streaming `FileChannel.read(ByteBuffer)` với buffer hữu hạn thường có vòng đời tài nguyên dễ kiểm soát hơn. Nếu cần mapping, giới hạn số vùng map đồng thời và thiết kế ownership/vòng đời rõ ràng; không ép gọi những API unmap nội bộ không được hỗ trợ mà không hiểu rủi ro.

## 16. Connection pools, Selector và giới hạn tài nguyên

### Một Selector quản lý nhiều SocketChannel

NIO Selector giúp một thread xử lý readiness của nhiều socket, cải thiện mô hình thread-per-connection trong một số workload. Tuy nhiên **mỗi SocketChannel vẫn có tài nguyên kết nối**. Đừng suy luận “một Selector nghĩa là chỉ một FD cho mọi client”.

Nên có các giới hạn:

- Số kết nối TCP đang hoạt động tối đa.
- Số kết nối pending/handshake đang chờ tối đa.
- Timeout cho kết nối idle và tác vụ không tiến triển.
- Queue outbound/backpressure per connection.
- Phạm vi nhận client mới khi nguồn lực gần ngưỡng.
- Đóng `SocketChannel` ở tất cả đường thoát, kể cả handshake lỗi, timeout hoặc `SelectionKey` bị cancel.

`key.cancel()` chỉ hủy đăng ký selection; nếu vòng đời socket kết thúc, chương trình còn phải đóng channel phù hợp. Không dùng cancel như sự thay thế mặc định cho close.

### Pool không phải leak, nhưng cũng có giới hạn

Một pool socket/file handle giữ resource mở để tái sử dụng có thể giảm chi phí open/close nhưng tiêu tốn FD lâu hơn. Pool cần max size, eviction, idle timeout và policy khi hệ thống quá tải.

Nếu mỗi tenant hoặc request tự tạo một pool riêng không có giới hạn tổng, sự cố trông giống resource leak ngay cả khi từng pool có cơ chế close đầy đủ trên lý thuyết.

## 17. Khi gặp Too many open files nên làm gì?

Một quy trình ứng phó an toàn:

1. **Giữ thông tin chẩn đoán**: stack trace của các thao tác mở thất bại, OS error, PID, FD count/limit, active requests, loại tài nguyên.
2. **Dừng/giảm việc tạo resource mới** nếu có thể: áp dụng backpressure, từ chối job mới, giới hạn accept/retry.
3. **Không retry vòng lặp nóng**: retry liên tục khi không có FD trống sẽ làm CPU và log pressure tăng.
4. **Xác định resource được giữ bởi ai**: thử tìm stream/channel/directory listing chưa close, socket idle, pool không giới hạn, watcher/selector chưa giải phóng.
5. **Sửa ownership**: try-with-resources, close ở failure path, factory/wrapper quản lý tài nguyên, timeout/eviction.
6. **Đo lại dưới tải đại diện**: open count có quay về baseline thích hợp, số lỗi có giảm, throughput ổn không.
7. **Chỉ điều chỉnh giới hạn OS khi thật sự cần**: cân nhắc mức concurrent workload, dự phòng hệ thống, container/service policy và khả năng tài nguyên khác.

Một kỹ thuật production nâng cao là giữ một ít headroom hoặc một descriptor dự phòng để có thể xử lý tình huống hết FD khi accept socket; cách làm cụ thể phụ thuộc OS và server architecture. Đây không phải phép sửa căn nguyên thay cho giới hạn admission và xử lý leak.

## 18. Những lỗi thường gặp

**Lỗi 1 — Nghĩ JVM có GC nên không cần close().** GC không cung cấp thời điểm đóng file/socket đáng tin. Dùng try-with-resources và ownership rõ ràng.

**Lỗi 2 — Đếm số FileChannel object để suy ra toàn bộ FD.** Một số tài nguyên có thể dùng chung, nằm ngoài Java heap hoặc thuộc các API khác. Dùng OS/JMX metric phù hợp.

**Lỗi 3 — Mở stream Files.list/Files.walk/Files.lines mà không đóng.** Đây là filesystem-backed stream; phải try-with-resources.

**Lỗi 4 — Mở hết hàng chục nghìn file cùng lúc rồi mới xử lý.** Chạm giới hạn FD và tăng áp lực hệ thống. Giới hạn concurrency, mở resource sát lúc dùng.

**Lỗi 5 — Tăng ulimit là xong.** Với leak, chỉ kéo dài thời gian tới khi lỗi. Trước tiên sửa ownership/close và đo lại.

**Lỗi 6 — Không trả permit khi FileChannel.open thất bại.** Semaphore mất permit dần, tự làm nghẽn ứng dụng dù OS còn tài nguyên.

**Lỗi 7 — Dùng semaphore nhưng code khác mở FD ngoài budget không kiểm soát.** Budget chỉ bảo vệ subsystem đi qua nó; phải dành headroom cho socket, logger, thư viện và hệ thống.

**Lỗi 8 — Chỉ đóng khi xử lý thành công.** Exception path là nơi phổ biến bị leak. Dùng finally/try-with-resources.

**Lỗi 9 — Đóng FileChannel rồi kết luận mọi MappedByteBuffer đã unmap.** Mapping có vòng đời riêng, không được kiểm soát chỉ bằng việc channel đóng.

**Lỗi 10 — Chỉ dựa vào handle count trên Windows rồi cho rằng đó là số Unix FD.** Handle count bao gồm nhiều loại tài nguyên, cần giải thích metric đúng nền tảng.

**Lỗi 11 — Cancel SelectionKey nhưng quên close channel.** Cancel chỉ thay đăng ký với selector; channel có thể vẫn mở.

**Lỗi 12 — Retry liên tục ngay khi EMFILE.** Retry không giới hạn làm tăng tải/log mà không giải phóng FD. Cần điều phối admission, backoff và khắc phục resource owner.

## 19. Câu hỏi tự kiểm tra

1. File descriptor là gì? **Tham chiếu số nguyên của tiến trình tới tài nguyên I/O trên Unix/Linux**, với chi tiết quản lý do OS thực hiện.
2. Mọi `FileChannel` có tương ứng đúng một FD không? **Không thể khẳng định chung cho mọi provider/implementation**.
3. `EMFILE` khác `ENFILE` thế nào? **EMFILE thường liên quan giới hạn descriptor của tiến trình; ENFILE liên quan giới hạn tài nguyên file-open rộng hơn ở cấp hệ thống**.
4. Vì sao tạo một `Selector` không làm vô hạn số socket có thể mở? **Mỗi kết nối vẫn sử dụng tài nguyên OS**, Selector chủ yếu thay cách theo dõi readiness.
5. `Files.list` có cần đóng stream trả về không? **Có**, vì nó dựa trên tài nguyên thư mục.
6. Dùng `Files.readString` có trả ra InputStream phải tự close không? **Không**; phương thức trả về String và tự quản lý resource nội bộ.
7. Tại sao `try-with-resources` tốt hơn close() chỉ ở dòng cuối hàm? **Resource được đóng trên các đường thoát có ngoại lệ**, và lỗi close được lưu phù hợp.
8. Budget semaphore có nâng `RLIMIT_NOFILE` không? **Không**; nó giới hạn số resource do ứng dụng tự cấp qua subsystem.
9. Nếu lấy permit rồi `FileChannel.open` thất bại, phải làm gì? **Trả permit trong finally/catch**.
10. Số FD tăng từ 100 lên 600 khi tải tăng rồi trở về 110 khi tải giảm có tự chứng minh leak không? **Không**; có thể là tải đồng thời hợp lệ.
11. `FileChannel.close()` có luôn unmap ngay mọi `MappedByteBuffer` không? **Không có bảo đảm đó**.
12. Trên Linux, muốn biết soft limit của **JVM đang chạy** thì chỉ nhìn `ulimit -Sn` trong shell khác có đủ không? **Không**; cần xem giới hạn của chính process hoặc service context.
13. Vì sao xử lý 10.000 file theo batch nên giới hạn số channel mở đồng thời? **Để không chạm giới hạn FD, kiểm soát áp lực OS và đạt throughput có thể dự đoán**.
14. Chạm giới hạn FD trong một server có thể ảnh hưởng logger/healthcheck không? **Có**, vì những thành phần đó cũng có thể cần mở file hoặc socket.
15. Lựa chọn ưu tiên khi ứng dụng thường xuyên báo “Too many open files” là gì? **Đo FD usage, tìm resource bị giữ quá lâu/không đóng, giới hạn concurrency và chỉ sau đó cân nhắc tăng OS limit**.

**Ghi nhớ:** file descriptor/handle là tài nguyên hữu hạn của hệ điều hành. Khi xử lý file lớn hoặc phục vụ nhiều kết nối đồng thời, ứng dụng Java phải **quản lý vòng đời bằng try-with-resources**, đóng cả các filesystem-backed streams, giới hạn số resource mở đồng thời, chừa headroom cho thành phần khác và theo dõi FD theo đúng môi trường. **Tăng giới hạn OS không thay thế sửa leak hoặc thiết kế concurrency có kiểm soát.**
