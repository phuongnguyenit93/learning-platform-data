# Phân biệt vùng nhớ dùng chung giữa luồng với vùng nhớ dùng chung giữa tiến trình

## 1. “Dùng chung bộ nhớ” là dùng chung ở cấp nào?

Khi lập trình Java có nhiều threads, nhiều native workers hoặc nhiều JVM processes, cụm từ **shared memory** rất dễ gây hiểu lầm. Có hai tình huống khác nhau về bản chất:

1. **Chia sẻ trong một tiến trình (intra-process, giữa các luồng):** nhiều Java threads cùng sống trong **một JVM process** và có thể cùng truy cập một Java object, một `byte[]`, một `ByteBuffer`, hoặc `MemorySegment` cấp phát từ một arena cho phép nhiều thread.
2. **Chia sẻ giữa các tiến trình (inter-process, IPC):** hai OS processes có **không gian địa chỉ riêng**. Chúng chỉ cùng quan sát hoặc sửa được dữ liệu khi OS thiết lập **cùng một backing resource** (chẳng hạn file-backed memory mapping, POSIX shared-memory object, Windows named file mapping), hoặc khi dùng IPC khác như pipe/socket để trao đổi bản sao dữ liệu.

Sự khác nhau quan trọng không nằm ở “có dùng off-heap hay không”. Một `ByteBuffer.allocateDirect` hoặc `Arena.ofShared().allocate(...)` có thể nằm ngoài Java heap, nhưng vẫn là vùng memory do **một process** sở hữu; **không tự trở thành IPC shared memory**.

Bài này nằm trong chủ đề **Bộ đệm và tệp** của Java Native Interoperability, dùng Java 17+ cho ví dụ NIO và Java 22+ cho phần tích hợp Foreign Function & Memory API (FFM).

### Bạn sẽ học được

- Xác định ranh giới **Java thread**, **JVM process** và **OS virtual address space**.
- Phân biệt chia sẻ **cùng object/backing bytes** giữa threads với chia sẻ **cùng file-backed pages** giữa processes.
- Hiểu vì sao `Arena.ofShared()` không phải “shared memory giữa các JVM”.
- Dùng `FileChannel.map(MapMode.READ_WRITE, ...)` để hai Java processes thao tác trên cùng một tệp.
- Phân biệt `READ_WRITE`, `READ_ONLY` và `PRIVATE` (copy-on-write).
- Hiểu sự khác biệt giữa **visibility**, **synchronization**, **atomicity** và **durability/force**.
- Tự chạy ví dụ **hai threads**, **hai JVM processes** và ví dụ **FFM mapped MemorySegment**.
- Thiết kế kích thước file, binary layout, offset, byte order, vòng đời mappings và quy tắc khóa đúng.
- Nhận diện các giả định sai có thể gây race, stale reads, data corruption hoặc crash native.

## 2. Một sơ đồ, hai kiểu “share”

~~~text
TRƯỜNG HỢP A: CÙNG TIẾN TRÌNH
+-------------------------------------------------------------+
| JVM PROCESS P                                               |
|                                                             |
|   Thread A -----------------+                               |
|                             |                               |
|                             v                               |
|                       [ ByteBuffer ]                        |
|                       [ MemorySegment ]                     |
|                             ^                               |
|   Thread B -----------------+                               |
|                                                             |
|  Một virtual address space, cùng Java heap và native memory  |
+-------------------------------------------------------------+


TRƯỜNG HỢP B: KHÁC TIẾN TRÌNH
+-------------------------+   +------------------------------+
| JVM PROCESS P1          |   | JVM PROCESS P2               |
| Thread A                |   | Thread B                     |
| Virtual address space 1 |   | Virtual address space 2      |
|                         |   |                              |
| Mapped view M1 ---------+---+--------- Mapped view M2       |
+-------------------------+   +------------------------------+
                 \                 /
                  \               /
                   v             v
                 [OS-backed shared resource]
                 [cùng file, offset, length]
~~~

Với **trường hợp A**, có thể chia sẻ chính **Java reference** hoặc **cùng vùng off-heap** khi thuộc cùng process. Với **trường hợp B**, không truyền một Java reference rồi kỳ vọng JVM khác có thể dereference; mỗi process phải tạo **mapping riêng** tới một tài nguyên chung do OS nhận biết.

Hai mapped views trong P1 và P2 **không bắt buộc có cùng địa chỉ ảo**. Hệ điều hành có thể ánh xạ cùng backing bytes vào địa chỉ khác nhau vì ASLR, layout virtual memory và trạng thái tiến trình. Không trao đổi raw pointer bằng một số `long` rồi dùng ở JVM khác.

### 2.1. “Cùng vùng nhớ vật lý” cũng cần hiểu thận trọng

Memory-mapped file được OS quản lý qua page cache và cơ chế virtual-memory mapping. Khi hai processes map cùng file, OS có thể dùng chung backing pages/caches hoặc cơ chế tương đương. Điều này **không có nghĩa** Java cam kết mọi ghi từ P1 xuất hiện **ngay tức thì** trong MappedByteBuffer của P2. Javadoc `FileChannel.map`/`MappedByteBuffer` nói rõ **việc thay đổi ở view của chương trình khác có được nhìn thấy hay không, và khi nào, phụ thuộc OS**.

Vì vậy, nếu ứng dụng cần một giao thức IPC chắc chắn, cần thêm **synchronization/protocol** và kiểm tra giả định về OS/filesystem; không chỉ cùng trỏ tới đường dẫn file.

## 3. Bảng so sánh quyết định

| Tiêu chí | Chia sẻ giữa các threads | Chia sẻ giữa các processes |
| --- | --- | --- |
| Số process | **Một** | **Hai hoặc nhiều** |
| JVM heap | Cùng JVM heap | Mỗi JVM heap độc lập |
| Java object reference | Có thể cùng tham chiếu object | **Không** trực tiếp |
| `static` field | Cùng bản trong một class loader của JVM đó | Mỗi JVM/process có state riêng |
| `byte[]` / `ByteBuffer.allocate` | Có thể chia sẻ giữa threads | Không tự được chia sẻ |
| `ByteBuffer.allocateDirect` | Có thể chia sẻ giữa threads cùng process | Không tự được chia sẻ |
| `Arena.ofShared().allocate` (JDK 22+) | Có thể truy cập từ nhiều threads cùng process | Không tự tạo IPC backing |
| `FileChannel.map(READ_WRITE)` | Các threads có thể dùng cùng mapping | Hai processes có thể map cùng file, với visibility phụ thuộc OS |
| POSIX `shm_open + mmap(MAP_SHARED)` | Có thể dùng | IPC shared memory native khi có cùng named object |
| Windows `CreateFileMapping/MapViewOfFile` | Có thể dùng | IPC shared memory native khi có cùng mapping object |
| Đồng bộ | Java Memory Model: `volatile`, locks, atomics, `Thread.join`... | OS-level protocol: interprocess locks, semaphores, pipes, sockets, process completion... |
| Cleanup | GC, `Arena.close`, native allocator ownership | Ngoài process-local cleanup còn phải quản lý backing resource/file/name |
| Rủi ro | Data race, visibility, premature close | Tất cả rủi ro trên **cộng** stale views, file truncation, ABI/schema và process crash |

Một tệp được memory-map trong **cùng JVM** vừa có tính chất “một số threads có thể dùng chung mapping”, vừa có thể được process khác map. Không cần chọn một danh mục tuyệt đối cho **công nghệ**; hãy hỏi **ai truy cập và backing resource nào thực sự được chia sẻ**.

## 4. Vì sao các threads trong cùng JVM có thể chia sẻ object?

Mỗi Java thread có call stack và trạng thái thực thi riêng, nhưng các threads trong cùng JVM có thể giữ references đến **cùng một Java object**. Ví dụ:

~~~java
int[] numbers = { 1, 2, 3 };

Thread worker = new Thread(() -> {
    numbers[0] = 42; // cùng array object với thread tạo nó
});
worker.start();
worker.join();

System.out.println(numbers[0]); // 42
~~~

Đây là **snippet trong một method** có xử lý hoặc khai báo `InterruptedException`, không phải file chương trình độc lập.

`worker.join()` là một phép đồng bộ: khi main trở lại từ `join` thành công, các hành động của worker trước khi kết thúc được nhìn thấy đúng theo quan hệ *happens-before* trong Java Memory Model (JMM). Trong ví dụ, chỉ worker ghi rồi main đọc **sau join**, nên không có cập nhật đồng thời.

Nếu main đọc `numbers[0]` trong khi worker đang ghi và **không** có đồng bộ, không thể dựa vào “cùng object” để đảm bảo tính nhất quán. Chia sẻ **địa chỉ/bộ nhớ** và chia sẻ **giá trị với visibility đúng** là hai chuyện.

### 4.1. Direct ByteBuffer vẫn là bộ nhớ thuộc một process

~~~java
ByteBuffer direct = ByteBuffer.allocateDirect(1024);
~~~

Bộ đệm direct thường được JVM cấp phát ngoài heap, có thể hỗ trợ native I/O giảm copies. **Nó không phải tên của một OS shared-memory object** và không có cơ chế hai JVM độc lập “cùng `allocateDirect(1024)` là nhận cùng 1.024 bytes”.

Hai lời gọi:

~~~java
// Process P1:
ByteBuffer a = ByteBuffer.allocateDirect(1024);

// Process P2:
ByteBuffer b = ByteBuffer.allocateDirect(1024);
~~~

tạo hai allocations process-local **khác nhau**. Kể cả nếu OS trả về số địa chỉ ảo trùng nhau (không có bảo đảm), nội dung vẫn thuộc những address spaces khác nhau.

### 4.2. ByteBuffer không tự thread-safe

Khi hai threads chia sẻ **cùng `ByteBuffer` object**, các thuộc tính `position`, `limit` và `mark` cũng là trạng thái mutable. Các phương thức `putInt()`/`getInt()` không offset có thể thay đổi `position`, dẫn đến race trong thao tác tuần tự.

Một pattern đơn giản là dùng **absolute access**:

~~~java
buffer.putInt(0, 42);
int x = buffer.getInt(0);
~~~

Hoặc tạo `duplicate()` / `slice()` cho mỗi worker để có **cursor state riêng**, nhưng vẫn cùng backing bytes. Việc tách cursor **không** tự đồng bộ các bytes dùng chung.

## 5. Ví dụ Java 17+ số 1: hai threads dùng chung DirectByteBuffer

File độc lập **`ThreadSharedBufferDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public final class ThreadSharedBufferDemo {
    private ThreadSharedBufferDemo() {
    }

    public static void main(String[] args) throws InterruptedException {
        ByteBuffer shared = ByteBuffer.allocateDirect(Integer.BYTES);
        shared.order(ByteOrder.BIG_ENDIAN);

        // Main chuẩn bị dữ liệu trước khi worker.start().
        shared.putInt(0, 41);

        Thread worker = new Thread(() -> {
            int oldValue = shared.getInt(0);
            shared.putInt(0, oldValue + 1);
        }, "writer");

        worker.start();
        worker.join();

        // Worker đã hoàn tất; happens-before thông qua join().
        System.out.println("thread shared value=" + shared.getInt(0));
        System.out.println("buffer is direct=" + shared.isDirect());
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file bằng **JDK 17 trở lên**:

~~~bash
javac ThreadSharedBufferDemo.java
java ThreadSharedBufferDemo
~~~

Stdout:

~~~text
thread shared value=42
buffer is direct=true
~~~

Vì sao output ổn định?

1. Main tạo **một** `ByteBuffer` direct và ghi 41.
2. Worker nhận **cùng reference Java** tới `shared`, đọc 41 rồi ghi 42.
3. Main chờ `worker.join()` kết thúc trước khi đọc kết quả, không có hai thread cùng sửa field này.
4. `allocateDirect` tạo direct buffer nên `isDirect()` là `true`.

**Demo này không có hai JVM.** Nó cho thấy **off-heap data có thể được chia sẻ giữa threads của một process**, không phải cơ chế IPC.

### 5.1. Nếu bỏ `join()` thì sao?

Nếu main chỉ gọi `worker.start()` rồi đọc giá trị ngay, thời điểm thực thi worker không xác định. Main có thể đọc 41 hoặc 42; nếu có nhiều writers không đồng bộ thì cả atomicity và ordering cũng trở thành vấn đề.

Giải pháp theo mục đích:

- Chờ worker kết thúc: `Thread.join()` / `Future.get()` / `CountDownLatch`.
- Cần shared mutable state nhiều threads: `synchronized`, `ReentrantLock`, `AtomicInteger` hoặc `VarHandle` memory-ordering/atomic access modes.
- Với một `ByteBuffer`, không giả định `getInt` + `putInt` là một atomic increment.
- Nếu cần phối hợp Java/native threads cùng process, phải hiểu cả Java Memory Model và synchronization do native code tham gia.

## 6. Từ Thread sang Process: ranh giới không gian địa chỉ

Một OS process có riêng virtual address space. Khi Java chạy hai lệnh:

~~~bash
java AppA
java AppB
~~~

thông thường OS tạo **hai JVM processes** khác nhau. Ngay cả khi hai chương trình dùng cùng tên class và cùng biến:

~~~java
static int counter = 1;
~~~

chúng có **hai bản `counter` độc lập**. Khi `AppA` tăng lên 10, `AppB` không tự thấy 10 chỉ vì class name trùng nhau.

`ProcessBuilder` cũng khởi chạy một **process con**, không phải thread mới trong JVM hiện tại:

~~~java
Process child = new ProcessBuilder(
        "java", "AppB").start();
~~~

Đây chỉ là minh họa; với production, dùng đúng Java executable, classpath, OS path và điều kiện dừng.

### 6.1. Java reference và native pointer không thể tự vượt process

Một Java reference không phải một định danh toàn cục có thể gửi dưới dạng `long` rồi dereference trong JVM khác. Với native pointer cũng tương tự:

~~~text
P1: địa chỉ ảo 0x1234 --> page trong process P1
P2: địa chỉ ảo 0x1234 --> page khác hoặc không mapped trong P2
~~~

Để P2 đọc cùng dữ liệu với P1, P2 cần OS mapping tới **cùng resource** hoặc dữ liệu được chuyển qua IPC. Mỗi process nhận **handle/mapping/Java wrapper riêng**.

Trường hợp hiếm mà hệ điều hành và native code có thể chia sẻ raw address qua kỹ thuật đặc biệt không phải hợp đồng portable của Java NIO/FFM; tránh thiết kế hệ thống dựa trên sự trùng khớp địa chỉ ảo.

### 6.2. “Cùng máy” không có nghĩa “cùng bộ nhớ ứng dụng”

Hai JVM trên cùng máy dùng chung RAM vật lý do OS quản lý, nhưng trang bộ nhớ **private** vẫn bị cách ly bằng virtual memory protection. “Máy có một khối RAM” không cấp quyền tự đọc bộ nhớ của process khác. Cơ chế IPC được thiết kế có chủ đích mới tạo quyền cùng truy cập.

## 7. OS tạo shared backing bằng cách nào?

Có nhiều phương án:

- **File-backed mapping:** hai processes cùng ánh xạ **cùng tệp** và **cùng vùng offset/length** ở chế độ chia sẻ được. Trong Java chuẩn, `FileChannel.map(FileChannel.MapMode.READ_WRITE, ...)` là điểm vào phổ biến.
- **POSIX shared memory:** native code dùng `shm_open` tạo/mở một named shared-memory object, đặt kích thước bằng `ftruncate` và `mmap(..., MAP_SHARED, ...)`. Có thể tích hợp Java qua JNI/FFM và tuân theo POSIX permissions/lifetime.
- **Windows named file mapping:** native code dùng `CreateFileMapping` / `OpenFileMapping` và `MapViewOfFile`. Một named mapping có thể được mở trong nhiều processes theo security attributes.
- **Anonymous mappings có quan hệ fork:** một số OS cho phép các processes có quan hệ nhất định chia sẻ pages từ anonymous `mmap(MAP_SHARED)`, nhưng đây không phải lựa chọn portable cho hai JVM do Java launcher tạo độc lập.
- **Các IPC không dùng shared memory:** pipe, domain socket, TCP, gRPC, message queue. Chúng chuyển **messages/bytes** giữa processes thay vì buộc hai bên cùng đọc/ghi một shared region.

**Điểm nhận diện:** shared memory **giữa processes** cần một **backing resource hoặc cơ chế OS mà cả hai cùng mở/tham chiếu**. Tên biến Java, tên `Arena`, đường dẫn classpath hay cùng CPU không đủ.

## 8. FileChannel.map và các chế độ ánh xạ

Java `java.nio.channels.FileChannel` có API chuẩn từ lâu:

~~~java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE,
        0L,
        4096L);
~~~

Cần mở `channel` phù hợp, ví dụ bằng `FileChannel.open(path, READ, WRITE)`, và đảm bảo tệp đã có kích thước phù hợp trước khi map.

### 8.1. Ba MapMode khác nhau

| MapMode | Ghi từ view | Ảnh hưởng tới backing file | Hỗ trợ bài toán |
| --- | --- | --- | --- |
| `READ_ONLY` | Không được sửa (`ReadOnlyBufferException`) | Không sửa từ view này | Readers, shared read-only data |
| `READ_WRITE` | Được sửa | Các thay đổi sẽ được truyền về file; thời điểm và việc thấy ở mapping của **process khác** tùy OS | Shared file-backed update / IPC có protocol |
| `PRIVATE` | Copy-on-write, view có thể sửa | **Không truyền thay đổi về file** và không làm process khác thấy những thay đổi private | Isolated snapshot/private calculation |

**Mấu chốt: `PRIVATE` không phải shared write.** Nếu hai JVM map cùng file nhưng ở `PRIVATE` rồi tự ghi vào view, các thay đổi thuộc private copies của chúng, không được publish về file để process khác nhận.

### 8.2. Buffer mapping sống bao lâu?

Với API ba tham số `FileChannel.map(mode, position, size)`, `MappedByteBuffer` và underlying mapping được giữ hợp lệ cho đến khi buffer được garbage-collected theo API contract. **Đóng `FileChannel` không tự unmap `MappedByteBuffer` đã tạo.**

Điều này có hệ quả:

- File descriptor/channel và memory mapping có lifetime **khác nhau**.
- Không nên đếm vào `try (FileChannel ...)` để khẳng định mapping chắc chắn đã bị unmapped tức thì.
- Trên Windows, tệp đang được map có thể không được xóa/rename khi bạn muốn; cơ chế cleanup phụ thuộc OS và runtime.
- Nếu cần quản lý thời gian sống mapping **xác định**, xem `FileChannel.map(..., Arena)` của JDK 22+ ở phần 12.
- Không truncate/delete file đang có mappings ở processes khác mà không có giao thức; vùng mapped có thể bất ngờ không còn truy cập được.

### 8.3. Không lẫn mapped file với buffer cấp phát direct

~~~java
ByteBuffer a = ByteBuffer.allocateDirect(4096);  // Off-heap process-local

MappedByteBuffer b = fileChannel.map(
        FileChannel.MapMode.READ_WRITE, 0L, 4096L);
~~~

Cả hai có thể là **direct buffers**, nhưng **chỉ b** trong ví dụ có backing resource là **một tệp** có thể được processes khác mở và map. Thuộc tính `isDirect()` một mình không cho biết có thể IPC hay không.

## 9. Ví dụ Java 17+ số 2: hai JVM processes, cùng một file-backed mapping

Đây là demo **đầy đủ, chạy được** bằng Java 17+. Để tránh phụ thuộc vào thời điểm P1 “tự thấy ngay” thay đổi trong một mapped view cũ của P2, demo dùng **giao thức có thứ tự**:

1. Parent tạo temporary file trên local storage, đặt kích thước đúng **4 bytes**.
2. Parent map file bằng `READ_WRITE`, ghi số 41, gọi `MappedByteBuffer.force()`.
3. Parent tạo **Java process con** và truyền **đường dẫn file** qua command-line argument.
4. Child mở cùng file, map riêng, đọc 41, ghi 42, `force()` và thoát.
5. Parent đợi `Process.waitFor()` thành công, sau đó **đọc lại nội dung file qua FileChannel**, không giả định nội dung đã được phản ánh tức thì trong mapped view cũ.
6. Parent xác nhận số 42, in stdout.

Thực hành sử dụng **file hệ thống cục bộ** và quyền read/write bình thường. Với network filesystem, semantics về coherence và flush phụ thuộc OS/protocol; cần kiểm thử riêng.

### 9.1. File `TwoProcessesMappedFile.java`

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Locale;

public final class TwoProcessesMappedFile {
    private static final int SIZE = Integer.BYTES;

    private TwoProcessesMappedFile() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 2 && args[0].equals("child")) {
            child(Path.of(args[1]));
            return;
        }

        if (args.length != 0) {
            throw new IllegalArgumentException(
                    "Run with no arguments, or: child <file>");
        }

        Path file = Files.createTempFile("mapped-ipc-", ".bin");
        // Best-effort dọn tệp khi JVM parent thoát.
        file.toFile().deleteOnExit();

        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE,
                StandardOpenOption.TRUNCATE_EXISTING)) {

            // FileChannel.truncate(4) không làm file rỗng dài ra.
            // Ghi đủ 4 byte trước khi map.
            ByteBuffer initial = ByteBuffer.allocate(SIZE);
            while (initial.hasRemaining()) {
                channel.write(initial);
            }

            MappedByteBuffer mapped =
                    channel.map(FileChannel.MapMode.READ_WRITE,
                                0L, SIZE);
            mapped.order(ByteOrder.BIG_ENDIAN);
            mapped.putInt(0, 41);
            mapped.force();

            System.out.println("parent mapped write=41");
            System.out.flush();

            // Chạy cùng JDK hiện tại để không phụ thuộc PATH.
            String executable = System.getProperty("os.name")
                    .toLowerCase(Locale.ROOT)
                    .startsWith("windows")
                    ? "java.exe" : "java";

            Path java = Path.of(
                    System.getProperty("java.home"),
                    "bin", executable);

            Process process = new ProcessBuilder(
                    java.toString(),
                    "-cp",
                    System.getProperty("java.class.path"),
                    TwoProcessesMappedFile.class.getName(),
                    "child",
                    file.toString())
                    .inheritIO()
                    .start();

            int exit = process.waitFor();

            if (exit != 0) {
                throw new IOException(
                        "Child JVM failed with exit code " + exit);
            }
        }

        // Đọc file qua channel mới sau khi child đã force + exit.
        // Không cần giả định view mapped cũ đã thấy ghi mới ngay.
        try (FileChannel verify = FileChannel.open(
                file, StandardOpenOption.READ)) {
            ByteBuffer bytes = ByteBuffer.allocate(SIZE);
            bytes.order(ByteOrder.BIG_ENDIAN);

            while (bytes.hasRemaining()) {
                int n = verify.read(bytes);
                if (n < 0) {
                    throw new EOFException("File shorter than 4 bytes");
                }
            }

            bytes.flip();
            int value = bytes.getInt();

            if (value != 42) {
                throw new IllegalStateException(
                        "Expected 42, got " + value);
            }

            System.out.println("parent file read=42");
        }
    }

    private static void child(Path file) throws Exception {
        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {

            if (channel.size() != SIZE) {
                throw new IOException(
                        "Unexpected file size: " + channel.size());
            }

            MappedByteBuffer mapped =
                    channel.map(FileChannel.MapMode.READ_WRITE,
                                0L, SIZE);
            mapped.order(ByteOrder.BIG_ENDIAN);

            int before = mapped.getInt(0);
            if (before != 41) {
                throw new IllegalStateException(
                        "Expected 41, got " + before);
            }

            mapped.putInt(0, before + 1);
            mapped.force();

            System.out.println("child mapped read=41");
            System.out.println("child mapped write=42");
        }
    }
}
~~~

### 9.2. Lệnh biên dịch và chạy

~~~bash
javac TwoProcessesMappedFile.java
java TwoProcessesMappedFile
~~~

Chương trình tự khởi động JVM con bằng `ProcessBuilder`. **Không cần** tự mở terminal thứ hai. File tạm được tạo bằng `Files.createTempFile` trên default temporary directory; parent gửi path qua argument, không gửi Java object `MappedByteBuffer`.

Không cần native C compiler, JNI library hay `--enable-native-access` vì đây là Java NIO có từ lâu.

### 9.3. Stdout thành công

~~~text
parent mapped write=41
child mapped read=41
child mapped write=42
parent file read=42
~~~

Thứ tự dòng đã được thiết kế:

- Parent in dòng đầu và `flush` trước khi start process con.
- Child chỉ chạy sau khi parent đã ghi và `force()`, nên nó đọc dữ liệu đã được ghi.
- Child in hai dòng rồi kết thúc; parent dùng `waitFor()` để chờ child hoàn tất.
- Parent đọc file **sau** khi child đã `force()` và exit, kiểm tra số 42 rồi mới in dòng cuối.

**Giới hạn quan trọng:** Đây là ví dụ **trao đổi có thứ tự qua file-backed mapping** trên filesystem cục bộ, **không phải** kiểm chứng rằng mọi OS đều cung cấp tức thì coherence của nhiều mappings khi hai processes đọc/ghi đồng thời. Javadoc cho phép mức độ visibility khác nhau theo OS. Đối với giao thức concurrent IPC, cần cơ chế lock/notification phù hợp và platform testing.

### 9.4. Vì sao không chỉ `Thread.join()`?

Parent và child là **hai JVM processes**. `Thread.join()` chỉ chờ một thread thuộc JVM của caller; nó không tự chờ OS process con. Trong ví dụ, **`Process.waitFor()`** là barrier của giao thức parent-child.

Tương tự, `synchronized(lock)` hoặc `AtomicInteger` trong parent không khóa JVM con, vì Java object `lock`/`AtomicInteger` trong child là object **khác**. Nếu hai processes cùng cập nhật concurrently, cần **interprocess synchronization**.

### 9.5. Lưu ý về tệp tạm

`deleteOnExit()` là best-effort, không phải phần giao thức IPC. File mapping kiểu `MappedByteBuffer` có thể tồn tại cho tới GC; trên Windows hoặc filesystem đặc biệt, tệp có thể còn bị giữ/mapped. Trong ứng dụng thật, hãy có lifecycle dọn file và xử lý cleanup failures, thay vì coi việc close channel là unmap ngay.

**Không truncate file trong lúc child còn map**, và không giả định xóa file ở một OS sẽ làm các process khác lập tức mất mapping theo cách đồng nhất trên mọi nền tảng.

## 10. `force()`, visibility, ordering và durability không phải một

Có ít nhất bốn câu hỏi khác nhau:

1. **Sharing:** P1 và P2 có cùng backing bytes (cùng file, offset và mapping mode) không?
2. **Visibility:** Khi P1 ghi, P2 sẽ thấy dữ liệu nào, vào lúc nào?
3. **Ordering/atomicity:** Có đọc phải record đang ghi dở không? Hai tiến trình cùng cập nhật counter có bị mất lần tăng không?
4. **Durability:** Dữ liệu đã được ghi bền xuống thiết bị lưu trữ chưa, hay còn trong cache?

`MappedByteBuffer.force()` giải quyết chủ yếu **durability** của những thay đổi trên mapping `READ_WRITE`. Theo API JDK 17, khi file ở **local storage**, sau khi force thành công, các thay đổi của mapping được bảo đảm ghi tới thiết bị lưu trữ; trên storage không cục bộ không có bảo đảm tương đương.

`force()` **không phải**:

- Một Java `volatile` write.
- Một interprocess mutex.
- Một atomic transaction cho cả record.
- Cam kết hai processes sẽ thấy mọi lần ghi tức thì ở một buffer mapped cũ.
- Cơ chế báo “message mới đã tới” cho consumer.
- Một cách an toàn để đọc dữ liệu trong khi writer đang truncate file.

Nếu `force` không có coordination mà cả hai processes cùng ghi `counter = counter + 1`, dữ liệu vẫn có thể bị lost update. `force` chỉ ép bytes ra storage, không tự giải quyết race.

### 10.1. `FileChannel.force` không thay thế `MappedByteBuffer.force`

Có hai API dễ nhầm:

~~~java
channel.force(true);
mapped.force();
~~~

- `channel.force(metaData)` nói về những cập nhật file thực hiện qua các phương thức channel và một số loại stream liên quan. Đặc tả nói **không bảo đảm** nó force tất cả thay đổi được thực hiện thông qua `MappedByteBuffer`.
- `mapped.force()` là API dành riêng cho **các thay đổi qua mapped buffer**.

Trong demo, mỗi process sửa dữ liệu thông qua mapping nên gọi **`mapped.force()`**.

### 10.2. Một phép đọc khác với một phép cập nhật nguyên tử

Giả sử hai JVM cùng làm:

~~~java
// Snippet nguy hiểm nếu chạy đồng thời hai processes:
int current = mapped.getInt(0);
mapped.putInt(0, current + 1);
mapped.force();
~~~

Hai processes có thể **cùng đọc một giá trị cũ** rồi ghi cùng giá trị mới; kết quả mất một lần tăng. Không có bảo đảm atomic increment chỉ từ `MappedByteBuffer.getInt`/`putInt`.

Muốn concurrent updates phải có **giao thức đồng bộ liên tiến trình**: cooperative FileLock, named OS mutex, semaphore hoặc thuật toán IPC memory ordering đã được kiểm chứng trên ABI/platform cụ thể.

## 11. Đồng bộ Java threads và đồng bộ OS processes khác nhau thế nào?

### 11.1. Trong cùng JVM: Java Memory Model

Java có quan hệ *happens-before*, ví dụ:

- Actions trước `thread.start()` được publish theo quy tắc start.
- Actions của worker trước khi kết thúc được quan sát sau `thread.join()` thành công.
- `volatile` read/write, `synchronized` lock/unlock, `java.util.concurrent` utilities có semantics được tài liệu hóa.
- `AtomicInteger.incrementAndGet` đảm bảo một phép atomic update cho object trong JVM đó.
- Với FFM/native segments shared, `VarHandle` có access modes để thao tác atomics/memory ordering khi carrier/layout phù hợp.

Đây là các quy tắc **cấp Java threads**. Nếu P1 và P2 mỗi bên tự tạo một `AtomicInteger(0)`, chúng **không có cùng object** để đồng bộ.

### 11.2. Khác JVMs: cần IPC protocol

Hai JVM processes không dùng chung Java monitor, class-loader state hoặc Java `AtomicInteger`. Với file-backed IPC, lựa chọn dễ hiểu:

- **Một writer, một reader, có thời điểm handoff rõ ràng:** như ví dụ `Process.waitFor`.
- **Nhiều độc lập processes:** dùng `FileChannel.lock()` / `tryLock()` khi phù hợp, với quy tắc cooperative lock ở tất cả participants.
- **Thông báo có dữ liệu mới:** pipe/socket/message queue/event primitive; mapping chỉ chứa bytes, không phải cơ chế notification.
- **Rất low latency:** dùng native shared memory cộng interprocess atomics/semaphores trên nền tảng kiểm soát được, có careful memory ordering/ABI.

### 11.3. FileLock có những giới hạn gì?

`FileChannel.lock()` tạo `FileLock` có thể được OS nhìn thấy từ processes khác. Nhưng Java API nhấn mạnh:

- Một số OS chỉ hỗ trợ **advisory locking**: chương trình khác không tuân theo giao thức vẫn có thể đọc/ghi.
- File locks được giữ **thay mặt cả JVM process**, không nên dùng để bảo vệ threads trong cùng một JVM.
- Shared locks có thể được OS chuyển thành exclusive nếu không hỗ trợ shared locking.
- Một số OS/filesystems có ràng buộc hoặc lỗi khi **map file và lock cùng vùng**; ứng dụng phải kiểm tra platform.
- Trên network filesystems có thể có giới hạn alignment/size và protocol-specific behavior.
- Không dùng `FileLock` làm phép “flush dữ liệu xuống storage”. Locking và durability là các nhiệm vụ khác nhau.

Mẫu giao thức cho processes **hợp tác** (snippet trong method, không phải chương trình chạy riêng):

~~~java
try (FileChannel channel = FileChannel.open(
        path, StandardOpenOption.READ, StandardOpenOption.WRITE);
     FileLock lock = channel.lock()) {

    // Cả producer và consumer phải tuân theo cùng quy tắc lock.
    // Đọc/ghi một bản ghi đầy đủ trong critical section.
    // Nếu dùng mapped memory, force khi cần durability.
}
~~~

**Không** lấy ví dụ trên làm bằng chứng `FileLock` sẽ chặn mọi OS mapping access của bất kỳ process nào: đó phụ thuộc OS. Với process không tuân thủ lock, ứng dụng vẫn có nguy cơ đọc/ghi dữ liệu không nhất quán.

## 12. FFM và `Arena.ofShared()`: “shared” có nghĩa gì?

Từ **JDK 22**, FFM có `Arena`:

~~~java
try (Arena arena = Arena.ofShared()) {
    MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);

    // Mọi Java thread có quyền truy cập segment này
    // khi arena còn mở, nếu thuật toán đồng bộ phù hợp.
}
~~~

Đây là snippet cần import `java.lang.foreign.Arena`, `MemorySegment` và `ValueLayout`.

`Arena.ofShared()`:

- Không có owner thread cố định; những Java threads trong **cùng process** được phép truy cập các segments cấp phát từ arena.
- Khi `close()` thành công, **mọi segment thuộc arena** trở nên hết hiệu lực; truy cập FFM sau close ném `IllegalStateException`.
- Không tự làm `get`/`set` thành atomic, không cấp interprocess permissions và không đặt tên OS shared-memory object.
- Không tự biến `arena.allocate(1024)` thành POSIX `shm_open`, Windows named mapping hoặc file-backed mapped segment.
- Không cho JVM khác tự lấy cùng Java `MemorySegment` bằng cách biết tên biến hoặc địa chỉ ảo của process đầu.

### 12.1. So sánh ba nguồn MemorySegment (JDK 22+)

| Segment nguồn | Có thể dùng nhiều threads? | Có thể là backing giữa processes? |
| --- | --- | --- |
| `Arena.ofConfined().allocate(...)` | Chỉ owner thread | **Không** chỉ bằng allocation này |
| `Arena.ofShared().allocate(...)` | Có, nhưng cần synchronization | **Không** chỉ bằng allocation này |
| `FileChannel.map(READ_WRITE, ..., Arena.ofShared())` | Có, khi arena còn sống | **Có khả năng**, do **cùng file-backed mapping** và OS protocol, không phải vì tên Arena |

**Công thức:** *Arena policy* quyết định **thread access và lifetime trong Java**; *mapping source* quyết định **backing resource**, có thể do OS dùng chung giữa processes.

## 13. JDK 22+: `FileChannel.map(..., Arena)` là cầu nối rõ ràng

JDK 22 bổ sung overload:

~~~java
MemorySegment mapped = fileChannel.map(
        FileChannel.MapMode.READ_WRITE,
        0L,
        4096L,
        arena);
~~~

Đây là snippet, với `fileChannel` đã mở đúng mode, tệp đủ lớn và `arena` còn sống.

**API này khác `arena.allocate(...)`.** `fileChannel.map` lấy bytes từ **file-backed mapped region**; `arena` chỉ điều khiển **lifetime và quy tắc thread access của Java segment view**. Khi một closeable arena đóng, mapped region được **unmapped** theo API contract.

### 13.1. Hai chiều ownership

~~~text
File-backed source:
  Path/OS file -> FileChannel.map(..., arena) -> MemorySegment
                  ^                             ^
                  |                             |
             OS backing                    Java view/scope
             cross-process                 arena thread policy
             theo OS + protocol            + close/unmap

Native allocation:
  Arena.ofShared().allocate(...) -> MemorySegment
     |                                   |
     +--> process-local allocation       +--> Java threads share
          KHÔNG phải file-backed               same view/lifetime
~~~

Cùng là `MemorySegment` nhưng **resource nguồn** khác nhau. Vì vậy không đặt tên API `ofShared` làm lý do dữ liệu được chia sẻ xuyên processes.

### 13.2. Mapped MemorySegment và MappedByteBuffer

| Đặc điểm | `FileChannel.map(mode, offset, size)` | `FileChannel.map(mode, offset, size, arena)` |
| --- | --- | --- |
| JDK | Có từ các phiên bản Java cũ, chạy Java 17 | Thêm từ Java 22 |
| Trả về | `MappedByteBuffer` | `MemorySegment` |
| Lifetime view | Gắn với GC của mapped buffer | Gắn với `Arena` được cung cấp |
| Cleanup rõ thời điểm | Không có public unmap trực tiếp | `Arena.close()` với closeable arena |
| Đa thread | Có thể dùng chung, phải đồng bộ | Dùng shared arena để cho nhiều threads truy cập |
| Cross-process backing | Tùy mapped file/mode và OS | Tùy mapped file/mode và OS |
| Flush | `mapped.force()` | `mappedSegment.force()` |
| Truy cập dữ liệu | `getInt`/`putInt` / ByteBuffer APIs | `get`/`set` / ValueLayout và VarHandle |

**Chú ý:** `FileChannel` định nghĩa một default implementation của overload `map(..., Arena)` có thể ném `UnsupportedOperationException` nếu provider không hỗ trợ. JDK 22+ chuẩn sử dụng native file channels có hỗ trợ, nhưng code portable vẫn nên xử lý platform/provider constraints.

## 14. Ví dụ Java 22+ số 3: file mapping thành MemorySegment và explicit unmap

File **`FFMMappedSegmentDemo.java`**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class FFMMappedSegmentDemo {
    private FFMMappedSegmentDemo() {
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("ffm-mapping-", ".bin");
        file.toFile().deleteOnExit();

        MemorySegment segment;
        ValueLayout.OfInt layout = ValueLayout.JAVA_INT
                .withOrder(ByteOrder.BIG_ENDIAN);

        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE,
                StandardOpenOption.TRUNCATE_EXISTING);
             Arena arena = Arena.ofShared()) {

            ByteBuffer initial = ByteBuffer.allocate(Integer.BYTES);
            while (initial.hasRemaining()) {
                channel.write(initial);
            }

            segment = channel.map(
                    FileChannel.MapMode.READ_WRITE,
                    0L,
                    Integer.BYTES,
                    arena);

            segment.set(layout, 0L, 17);
            segment.force();

            System.out.println(
                    "FFM mapped value=" + segment.get(layout, 0L));
        } // Arena.close(): segment scope hết sống, mapping được unmap.

        System.out.println(
                "scope alive=" + segment.scope().isAlive());

        try (FileChannel verify = FileChannel.open(
                file, StandardOpenOption.READ)) {

            ByteBuffer raw = ByteBuffer.allocate(Integer.BYTES);
            raw.order(ByteOrder.BIG_ENDIAN);

            while (raw.hasRemaining()) {
                if (verify.read(raw) < 0) {
                    throw new java.io.EOFException(
                            "File shorter than 4 bytes");
                }
            }

            raw.flip();
            System.out.println("file value=" + raw.getInt());
        }
    }
}
~~~

Chạy trên **JDK 22+**:

~~~bash
javac FFMMappedSegmentDemo.java
java FFMMappedSegmentDemo
~~~

Với provider file channel thông dụng có hỗ trợ mapping FFM, stdout:

~~~text
FFM mapped value=17
scope alive=false
file value=17
~~~

Giải thích:

- File có đúng 4 bytes trước khi map; demo **không** trông chờ `FileChannel.truncate(4)` tự mở rộng file rỗng.
- `segment` là mapped view của **một file**, không phải bộ nhớ mới được `arena.allocate`.
- `Arena.ofShared()` cho phép nhiều threads trong cùng JVM truy cập segment trong lifetime đó, nhưng demo chỉ dùng một thread để có kết quả xác định.
- `ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN)` quy định byte order khớp `ByteBuffer` khi verify.
- `segment.force()` yêu cầu write-back của thay đổi trên mapped region.
- Khi ra khỏi `try`, Arena đóng và mapped `MemorySegment` hết hiệu lực; `scope.isAlive()==false`.
- Mở lại file và đọc 17 sau khi close cho thấy **tệp giữ dữ liệu** sau khi view Java kết thúc. Đây không phải live read của process khác, nên không chứng minh latency coherence giữa processes.

Với một file-mapped region được chia sẻ giữa processes thực sự, **mỗi process phải tự mở cùng file và map**. Không chuyển Java object `segment` từ JVM P1 sang P2.

### 14.1. Nếu dùng `Arena.ofConfined()` thay vì shared?

MemorySegment mapped từ file có backing resource có thể được nhiều processes cùng mở, nhưng **Java view nằm trong confined arena vẫn chỉ được truy cập bởi owner thread trong mỗi JVM đó**. Ngay trong P1, Java thread khác truy cập view confined sẽ ném `WrongThreadException`. Tuy nhiên P2 có thể có **mapping riêng** của cùng file; đây là hai tầng kiểm soát khác nhau.

Đây là ví dụ rất tốt để ghi nhớ: **cùng backing file không hủy các quy tắc confinement của riêng mỗi Java MemorySegment**.

## 15. Định dạng dữ liệu IPC: không chỉ có bốn bytes

Bài chạy dùng một `int` để làm rõ cơ chế. Khi dữ liệu phức tạp hơn, hai processes phải thống nhất **binary protocol**:

| Trường | Mục đích |
| --- | --- |
| Magic | Nhận ra file hoặc shared-memory block đúng loại |
| Version | Kiểm tra layout tương thích giữa các chương trình |
| Length | Kích thước payload thực tế, tránh đọc vượt vùng mapped |
| State | READY / WRITING / ACKNOWLEDGED theo protocol |
| Sequence number | Phân biệt bản ghi mới/cũ hoặc retry |
| Payload | Dữ liệu theo layout đã công bố |
| Checksum/CRC | Phát hiện bytes hỏng hoặc write dở |
| Padding/alignment | Khớp ABI nếu dùng native structs hoặc atomics |

Ví dụ thiết kế layout (minh họa, không phải định nghĩa API Java sẵn):

~~~text
Offset  Size  Meaning
0       4     MAGIC = 0x4A564D49 ("JVMI")
4       4     VERSION = 1
8       4     STATE (0 empty / 1 writing / 2 ready)
12      4     LENGTH
16      8     SEQUENCE NUMBER
24      ...   PAYLOAD
~~~

Cần chọn rõ **big-endian** hay **little-endian** cho mọi trường. Trong Java, `ByteBuffer.order(ByteOrder.BIG_ENDIAN)` hoặc tương đương `ValueLayout.withOrder`. Với C/C++, kiểm tra `sizeof`, alignment, packing và CPU endianness; đừng “cast” raw mapped bytes thành native struct tùy ý rồi tin hai tiến trình khác compiler/ABI sẽ cùng layout.

### 15.1. Producer/consumer không được nhìn record ghi dở

Một giao thức dựa trên cooperative file lock có thể là:

~~~text
PRODUCER                          CONSUMER
---------                         --------
acquire exclusive IPC lock       acquire same IPC lock later
STATE = WRITING                   only after producer releases
write payload                     validate MAGIC / VERSION
write LENGTH / CRC                check STATE == READY
STATE = READY                     read whole record
force mapped changes if needed    validate CRC / LENGTH
release IPC lock                  process data
                                 release IPC lock
~~~

Đây là **sơ đồ giao thức**, không phải nguồn runnable. Nếu cần báo ngay khi có dữ liệu, dùng IPC notification bổ sung; không busy-spin một byte `STATE` trên mapped buffer rồi mặc định visibility được Java bảo đảm trên mọi OS.

**Mọi participants phải tuân theo cùng quy tắc lock/protocol.** Trong một số OS, locks là advisory nên process bỏ qua khóa vẫn có thể phá dữ liệu.

### 15.2. Hai writers cùng tăng một counter

Trường hợp sai:

~~~text
P1 đọc 10                  P2 đọc 10
P1 ghi 11                  P2 ghi 11
Kết quả 11 nhưng đã có hai increments
~~~

Một cách an toàn ở mức ứng dụng là serialized update qua **một interprocess lock** hoặc đưa các increments thành messages cho **một owner process**. Dùng Java `AtomicInteger` tại P1 không cứu được `AtomicInteger` độc lập của P2.

Với native shared memory và interprocess atomics, cần cam kết rõ về **atomic alignment, memory order, process-shared synchronization primitives, ABI và hệ điều hành**. Đừng lấy các access modes của Java `VarHandle` làm lời hứa portable về synchronization giữa các JVM processes: Java Memory Model mô tả intra-JVM threads, còn cross-process effects phụ thuộc OS và cơ chế mapping.

## 16. Không phải IPC nào cũng nên dùng shared memory

Shared memory giúp nhiều processes truy cập một vùng backing mà không nhất thiết copy toàn bộ payload qua pipe/socket ở mỗi thao tác. Nhưng nó đòi thiết kế **protocol, synchronization, schema, lifetime và failure recovery** phức tạp hơn.

Chọn công cụ theo nhu cầu:

| Nhu cầu | Giải pháp dễ phù hợp |
| --- | --- |
| Hai threads cùng JVM trao đổi trạng thái nhỏ | `AtomicInteger` / concurrent queue / locks |
| Hai threads cùng JVM xử lý buffer lớn | Shared Java object/ByteBuffer, FFM `Arena.ofShared()` nếu cần native memory |
| Hai JVM liên lạc thông điệp nhỏ | Pipe, Unix-domain socket, TCP, gRPC hoặc message queue |
| Hai JVM trao đổi một batch lớn có thể ghi vào tệp | FileChannel read/write, memory-mapped file khi có lợi |
| Hai JVM trên cùng máy cần vùng backing chung low-latency | Native OS shared-memory mapping + process-shared synchronization |
| Persistent dataset đọc bởi nhiều processes | Read-only file mapping, versioning và file replacement protocol |
| Chỉ cần chia sẻ thông tin với client trên máy khác | Network IPC; local shared memory không xuyên máy |
| Cần transactional updates/durability mạnh | Database hoặc storage engine với journaling/locking |

**Thực tế:** Memory mapping có overhead khởi tạo và quản lý, nên **không luôn nhanh hơn** đọc/ghi vài KB bằng `FileChannel.read/write`. Đo lường trên dữ liệu và filesystem thật; tránh chọn mmap chỉ vì tên “shared memory” nghe có vẻ tiết kiệm copies.

## 17. Vòng đời và lỗi vận hành của mapped files

### 17.1. Mapped view không phải file channel

Với Java 17:

~~~java
MappedByteBuffer mapped;

try (FileChannel channel = FileChannel.open(
        path, StandardOpenOption.READ)) {
    mapped = channel.map(
            FileChannel.MapMode.READ_ONLY, 0L, fileSize);
}

// Channel đã đóng nhưng mapped vẫn có thể hợp lệ.
~~~

Snippet giả định `path`, `fileSize` đã xác định và region nằm trong file. Closing channel không tự unmap mapping.

Với Java 22 FFM:

~~~java
MemorySegment mapped;

try (FileChannel channel = FileChannel.open(
        path, StandardOpenOption.READ);
     Arena arena = Arena.ofShared()) {

    mapped = channel.map(
            FileChannel.MapMode.READ_ONLY,
            0L, fileSize, arena);
}

// Arena đã đóng: mapped scope không còn sống.
~~~

Snippet Java 22 cũng giả định `path`/`fileSize` hợp lệ; sau close không đọc dữ liệu từ `mapped` nữa. Đây là khác biệt **lifetime management** của `MappedByteBuffer` và mapped `MemorySegment`.

### 17.2. Tệp bị truncate hoặc thay thế

Nếu một process đang map bytes [0, 4096) mà process khác **truncate file xuống 100 bytes**, phần mapping ngoài file có thể trở nên không thể truy cập. Tùy OS có thể phát sinh exception, native fault hoặc vấn đề ánh xạ khác. Java javadoc yêu cầu đặc biệt thận trọng với thay đổi nội dung/kích thước backing file từ programs đồng thời.

**Quy tắc:** Không sửa kích thước hoặc xóa backing resource cho tới khi mọi processes đã dừng sử dụng mapping hoặc đã chuyển sang version khác theo protocol.

### 17.3. Process crash giữa lần ghi

Nếu producer chết sau khi ghi nửa payload mà trước khi đặt `STATE=READY`, consumer cần nhận diện data chưa hoàn tất và không đọc như bản ghi hợp lệ. Với dữ liệu phải bền:

- Ghi format gồm version/length/checksum.
- Có transaction/commit marker hoặc journal phù hợp.
- Dùng force theo nhu cầu durability.
- Xem xét atomic file replacement bằng viết file mới rồi rename theo khả năng của filesystem và giao thức mở mappings mới.
- Kiểm thử recovery sau process crash, `kill` và mất điện.

`force()` của một mapped buffer **không biến chuỗi nhiều ghi thành transaction nguyên tử**.

### 17.4. Security và quyền truy cập file

Nếu dùng memory-mapped file như IPC, **bảo mật phụ thuộc file permissions, đường dẫn và OS handle**:

- File trong thư mục world-writable có thể bị process khác mở/sửa.
- Hai bên nên xác thực path/canonical identity và permissions, tránh symlink swap khi liên quan dữ liệu nhạy cảm.
- Không dùng file-backed shared memory để chứa secrets dài hạn mà không có lifecycle và access control rõ.
- Với POSIX named shared memory hoặc Windows named mapping, áp dụng permissions/security descriptor thích hợp.

Không dùng "cùng đường dẫn text" làm bằng chứng hai processes đang mở **cùng file identity**: symlinks, mount namespaces, file replacement hoặc container isolation có thể làm đường dẫn trỏ tới đối tượng khác.

## 18. Những lỗi và hiểu lầm thường gặp

| Nhầm lẫn / hiện tượng | Vì sao sai | Cách giải quyết |
| --- | --- | --- |
| “`Arena.ofShared()` là RAM cho mọi JVM” | Shared ở đây là **thread-access scope trong một process** | Dùng OS-backed named/file mapping nếu cần IPC |
| “DirectByteBuffer là bộ nhớ toàn máy” | Direct vẫn là allocation process-local | Phân biệt direct memory với mapped file |
| “Hai `static` fields trùng tên ở hai JVM là cùng một biến” | Mỗi process/JVM có state độc lập | Dùng IPC hoặc storage chung |
| “Gửi native pointer từ P1 sang P2 sẽ dùng được” | Virtual address spaces khác nhau | Trao resource identifier và map riêng ở P2 |
| “`MappedByteBuffer.PRIVATE` publish các ghi cho mọi process” | PRIVATE là copy-on-write | Dùng READ_WRITE khi cần shared backing update |
| “`force()` là interprocess mutex” | Force xử lý write-back, không atomicity | Dùng protocol và cross-process synchronization |
| “`force()` luôn làm mapping cũ của P2 thấy ngay” | Visibility mapping khác process tùy OS | Thiết kế handoff/notification, verify/coherence theo platform |
| “`Thread.join()` chờ process con” | Join chỉ thread | Dùng `Process.waitFor()` hoặc IPC ack |
| “`synchronized` trên Java object khóa JVM khác” | Mỗi JVM có object khác | Dùng FileLock/native mutex/IPC |
| “`FileLock` bảo vệ các Java threads cùng process” | Locks mang phạm vi cả JVM | Dùng Java locks cho threads; FileLock giữa processes |
| “Mọi FileLock luôn cưỡng chế ngăn process khác ghi” | Nhiều OS dùng advisory locks | Tất cả participants phải tuân thủ protocol |
| “Đóng FileChannel là unmap MappedByteBuffer” | Mapping sống đến GC của buffer | Quản lý lifecycle; cân nhắc FFM map + Arena |
| “`truncate(4096)` làm file 0 bytes thành 4096” | `truncate` không mở rộng file | Ghi bytes để đảm bảo file size trước map |
| “Map file rồi bỏ qua endianness” | Hai processes/ngôn ngữ có thể diễn giải bytes khác | Chuẩn hóa binary layout/ByteOrder |
| “Một process crash không ảnh hưởng mapped data” | Record có thể bị ghi dở hoặc backing chưa flush | Version, commit marker, checksum, recovery |
| “File map chỉ sống tới khi process đóng channel” | Channel và mapped view là resources khác | Dọn mappings và backup file theo OS |
| “Shared arena tự bảo đảm data race free” | Quyền truy cập ≠ synchronization | Java atomics/locks cho threads, IPC protocol cho processes |

## 19. Câu hỏi ôn tập có đáp án

**Câu 1.** Hai threads cùng tham chiếu `ByteBuffer.allocateDirect(1024)` trong một JVM. Đây có phải shared memory liên tiến trình không?

**Đáp án:** Không. Đây là **shared off-heap memory giữa threads trong một process**. Direct allocation không tự có backing resource được JVM khác map.

**Câu 2.** Hai JVM độc lập đều gọi `Arena.ofShared().allocate(4096)` trên JDK 22. Chúng có cùng 4.096 bytes không?

**Đáp án:** Không. Mỗi JVM cấp phát process-local memory riêng. `ofShared` chỉ cho phép nhiều threads **của cùng process** truy cập segment.

**Câu 3.** Muốn Java P1 và Java P2 trao đổi dữ liệu trong một mapped file, cần gì?

**Đáp án:** Cùng **file identity**, vùng offset/length, mapping mode cho phép chia sẻ ghi khi cần; mỗi process tự mở/mapping và có một **protocol đồng bộ**. Không truyền Java ByteBuffer reference từ process này sang process kia.

**Câu 4.** Vì sao `FileChannel.MapMode.PRIVATE` không phù hợp để P1 ghi và P2 đọc kết quả?

**Đáp án:** PRIVATE tạo copy-on-write: thay đổi của P1 không được propagate về backing file và không trở thành thay đổi mà P2 nhìn thấy.

**Câu 5.** `MappedByteBuffer.force()` và `Thread.join()` khác nhau thế nào?

**Đáp án:** `force` nhằm ghi thay đổi mapped file ra storage. `join` tạo thời điểm chờ và quan hệ happens-before giữa threads trong JVM. Chúng giải quyết **hai khía cạnh khác nhau**.

**Câu 6.** `Process.waitFor()` trong demo hai JVM đảm nhiệm gì?

**Đáp án:** Parent chờ child đã hoàn tất thao tác và thoát, tạo một **handoff theo trình tự** trước khi parent đọc lại file. Nó không biến hai JVM thành cùng memory heap hoặc cam kết real-time mmap coherence.

**Câu 7.** Tại sao demo parent đọc lại bằng `FileChannel` sau khi child thoát thay vì dùng mapped buffer cũ?

**Đáp án:** Java mapping APIs cho phép khả năng thay đổi từ process khác được nhìn thấy tại các thời điểm phụ thuộc OS. Đọc lại file sau khi child force/exit phù hợp với bài demo tuần tự và tránh gán bảo đảm không có trong javadoc cho mapped view cũ.

**Câu 8.** Hai JVM cùng tăng counter trong một mapped file bằng `getInt` rồi `putInt`. Kết quả có luôn đúng không?

**Đáp án:** Không. Hai phép riêng có race; cần protocol có interprocess lock/atomic primitives thích hợp, không chỉ `force`.

**Câu 9.** Dùng `FileChannel.lock()` có khóa các threads Java trong cùng một process không?

**Đáp án:** Không phù hợp: `FileLock` được giữ thay mặt JVM và nhắm tới phối hợp với processes khác. Threads cùng JVM nên dùng Java concurrency primitives.

**Câu 10.** Khi dùng `FileChannel.map(READ_WRITE, ..., arena)` ở JDK 22, điều gì làm dữ liệu có thể IPC: `Arena.ofShared()` hay backing file?

**Đáp án:** **Backing file** và OS mapping. Arena chỉ quyết định temporal/thread access của `MemorySegment` ở JVM hiện tại.

**Câu 11.** Close `Arena` của một mapped `MemorySegment` có xóa tệp không?

**Đáp án:** Không. Close làm segment hết scope và unmap local view. Backing file tồn tại theo filesystem lifecycle riêng, cho tới khi được xóa theo OS permissions và policy.

**Câu 12.** Nếu P1 và P2 cùng map một file, nhưng P1 dùng big-endian còn P2 dùng little-endian thì sao?

**Đáp án:** Cùng bytes được diễn giải thành **hai giá trị khác nhau**. Cần thống nhất byte order, kích thước primitive, padding và schema giữa processes/ngôn ngữ.

**Câu 13.** File bị truncate trong lúc P2 đang map. P2 có bảo đảm đọc an toàn tới hết mapping cũ không?

**Đáp án:** Không. Một phần vùng mapped có thể trở nên inaccessible; Java docs không cam kết exception/thời điểm đồng nhất. Phải dùng protocol quản lý resize/unmap.

**Câu 14.** Tại sao không dùng `FileChannel.force(true)` thay cho `MappedByteBuffer.force()`?

**Đáp án:** Javadoc `FileChannel.force` không bảo đảm nó flush toàn bộ thay đổi thực hiện qua mapped buffer; dùng `mapped.force()` cho mapped writes.

**Câu 15.** Nếu P1 và P2 chạy trên hai máy khác nhau, có thể dùng named OS shared memory của máy P1 như một Java object ở P2 không?

**Đáp án:** Không. Native shared memory và mmap local thường giới hạn trong một host/OS environment. Với hai máy, dùng network protocol hoặc shared storage có semantics được thiết kế phù hợp.

## 20. Tài liệu chính thức

- [Oracle Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): `map`, `force`, file locks và giới hạn OS-dependent visibility.
- [Oracle Java SE 17 — FileChannel.MapMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.MapMode.html): `READ_ONLY`, `READ_WRITE`, `PRIVATE`.
- [Oracle Java SE 17 — MappedByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html): file-backed direct buffers, `force`, mapped lifetime và thay đổi nội dung từ programs khác.
- [Oracle Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): direct/heap buffers, absolute operations và `ByteOrder`.
- [Oracle Java SE 17 — FileLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileLock.html): locks cấp tiến trình, advisory/mandatory, giới hạn filesystem.
- [Oracle Java SE 17 — Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `start`/`join`, luồng Java và lifecycle.
- [Oracle Java SE 17 — Process](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Process.html): `waitFor` và process lifecycle.
- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): `ofShared`, confined/shared scope và lifetime.
- [Oracle Java SE 22 — FileChannel.map(..., Arena)](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/channels/FileChannel.html): mapped `MemorySegment` gắn với Arena và explicit unmap.
- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): scope, native memory và mapped segment operations.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): chuẩn hóa FFM ở JDK 22.

**Kết luận:** **Dùng chung giữa luồng** nghĩa là nhiều threads của **một JVM process** có quyền truy cập cùng object/backing bytes và phải tuân theo Java concurrency rules. **Dùng chung giữa tiến trình** đòi một **resource do OS chia sẻ**, ví dụ file-backed `FileChannel.map(READ_WRITE)` hoặc named shared-memory mapping, mỗi process mở view riêng và phối hợp qua **IPC synchronization/protocol**. `Arena.ofShared()` không biến process-local allocation thành shared memory liên tiến trình; còn `MappedByteBuffer.force()` không thay thế visibility, atomicity hay locking.
