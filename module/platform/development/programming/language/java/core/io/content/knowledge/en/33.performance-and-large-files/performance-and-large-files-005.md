# Heap buffer, direct memory và áp lực bộ nhớ trong Java NIO

## 1. Bài toán thực tế: dữ liệu tệp lớn và bộ nhớ không chỉ nằm ở heap

Khi đọc hoặc ghi tệp lớn bằng Java NIO, chương trình thường tạo các đối tượng `ByteBuffer`. Có hai cách cấp phát dễ thấy:

- `ByteBuffer.allocate(capacity)`: tạo **heap byte buffer**, vùng dữ liệu nằm trong bộ nhớ heap của JVM.
- `ByteBuffer.allocateDirect(capacity)`: yêu cầu tạo **direct byte buffer**, dữ liệu nằm trong vùng bộ nhớ có thể được I/O native truy cập trực tiếp hơn, thường được gọi là *off-heap/direct memory*.

Một sai lầm thường gặp là cho rằng tăng `-Xmx` sẽ giải quyết tất cả lỗi bộ nhớ. Thực tế ứng dụng Java còn tiêu thụ direct buffers, memory-mapped files, thread stacks, metaspace, JIT code cache, thư viện native, page cache của hệ điều hành và nhiều tài nguyên khác. Một chương trình có **Java heap còn dư** vẫn có thể không cấp phát được direct buffer hoặc bị hệ điều hành/container giới hạn tổng mức sử dụng bộ nhớ.

Ngược lại, cũng không nên kết luận “direct luôn nhanh hơn heap”. Direct buffer có lợi trong một số đường truyền dữ liệu qua native I/O, nhưng chi phí cấp phát/thu hồi, cache locality, việc copy dữ liệu từ đối tượng Java và mô hình sử dụng có thể làm nó kém hiệu quả hơn heap buffer.

Mục tiêu bài học:

1. Phân biệt cách tổ chức heap/direct buffer và API nhận biết.
2. Hiểu direct memory được quản lý khác heap như thế nào, cách vòng đời buffer ảnh hưởng áp lực bộ nhớ.
3. Biết khi nào direct buffer có khả năng giảm copy trong FileChannel/SocketChannel và khi nào không.
4. Đọc đúng các chỉ số `BufferPoolMXBean`, Java heap, RSS/container memory.
5. Thiết kế pool, giới hạn kích thước buffer và backpressure cho tệp lớn/tải cao.
6. Viết Java 17+ có ví dụ chạy được, vòng lặp read/write đúng và cleanup rõ ràng.

## 2. Heap ByteBuffer là gì?

`ByteBuffer.allocate(n)` cấp phát một `ByteBuffer` có dung lượng `n` byte. Với heap buffer từ `allocate`, backing storage thông thường là một mảng `byte[]` do GC heap quản lý.

~~~java
ByteBuffer heap = ByteBuffer.allocate(1024);
System.out.println(heap.isDirect()); // false
System.out.println(heap.hasArray()); // true
~~~

Đây là đoạn mã minh họa trong method có import `java.nio.ByteBuffer`. Các tính chất:

- Dữ liệu thực được lưu trong một mảng `byte[]` trên Java heap; heap limit `-Xmx` có liên quan tới dung lượng có thể cấp.
- `hasArray()` cho biết có thể lấy backing array của buffer hiện tại qua `array()`; với writable heap buffer từ `allocate` là `true`.
- `arrayOffset()` và `position()` cùng quan trọng khi chuyển một vùng buffer sang API nhận mảng. Không được mặc định byte hợp lệ bắt đầu tại offset 0.
- `ByteBuffer.wrap(byte[])` tạo một buffer gắn với **mảng do caller cung cấp**; nó không tạo bản sao của mảng đó.
- GC quản lý mảng backing; khi không còn reachable, dữ liệu có thể được thu hồi qua các chu kỳ GC theo chính sách runtime, không phải ngay khi gọi `clear()`.

Heap buffer phù hợp với parser thuần Java, tích hợp API dùng `byte[]`, các buffer sống ngắn hoặc workload mà lợi ích direct I/O không vượt chi phí quản lý native memory.

**Không phải mọi buffer có `isDirect()==false` đều có `hasArray()==true` có thể sử dụng từ ngoài.** Ví dụ read-only heap buffer có thể không cho truy cập backing array. Hãy hỏi `hasArray()` trước khi gọi `array()`, thay vì dựa vào `!isDirect()`.

## 3. Direct ByteBuffer là gì?

`ByteBuffer.allocateDirect(n)` tạo một direct buffer, có backing storage dùng cho I/O native, không nằm trong mảng `byte[]` trên Java heap.

~~~java
ByteBuffer direct = ByteBuffer.allocateDirect(1024);
System.out.println(direct.isDirect()); // true
System.out.println(direct.hasArray()); // false
~~~

Direct buffer vẫn là một đối tượng Java có `position`, `limit`, `capacity` và các phương thức đọc/ghi, nhưng storage dữ liệu thường ở vùng native memory. Hãy phân biệt:

- **Java wrapper object**: có thể được GC nhìn thấy và quản lý vòng đời đối tượng.
- **Off-heap backing memory**: phục vụ bytes của buffer, nằm ngoài phần heap được giới hạn bởi `-Xmx`.
- **Reference graph**: nếu ứng dụng giữ một tham chiếu đến direct buffer hoặc một view như `slice()/duplicate()`, bộ nhớ bên dưới có thể vẫn cần được giữ.
- **Native address**: là chi tiết implementation; API `ByteBuffer` không công khai một giao diện portable để giải phóng hoặc thao tác địa chỉ native tùy ý.

`direct.array()` không dùng được vì direct buffer không có backing `byte[]` công khai. Nếu code cần dùng một API chỉ nhận mảng, phải tổ chức copy bytes sang mảng, hoặc dùng một API chấp nhận `ByteBuffer`.

### Direct không đồng nghĩa “bên ngoài GC hoàn toàn”

Bộ nhớ direct **không chiếm dung lượng mảng trong heap** nhưng vòng đời của nó thường được liên kết với khả năng reachability/cleaner của các object Java. Trên các JDK triển khai phổ biến, bộ nhớ native được giải phóng khi runtime xác định không còn tham chiếu phù hợp và tiến hành cleanup. **Không có cam kết nó được thu hồi ngay khi biến cục bộ ra khỏi scope.**

Vì thế, trong ứng dụng cần cấp phát/thu hồi nhanh, việc tạo `allocateDirect` mới cho mọi request có thể gây áp lực bộ nhớ và GC, dù heap sử dụng ít. Dùng direct buffer có giới hạn số lượng và tái sử dụng có thể giúp giảm áp lực này.

### Direct allocation có thể thất bại khi heap còn dư

Khi vượt hạn mức direct memory hoặc runtime/OS không thể cấp phát native backing, quá trình cấp phát có thể ném `OutOfMemoryError` liên quan đến direct buffer memory. Không được kết luận `OutOfMemoryError` chỉ liên quan đến `Java heap space`. Cũng không được tự động tăng `-Xmx` và coi là đã giải quyết.

## 4. ByteBuffer vẫn có position, limit, capacity và mark

Heap và direct buffer tuân theo cùng mô hình con trỏ:

- `capacity`: kích thước vùng dữ liệu được cấp ban đầu, không đổi trong đời của buffer.
- `position`: vị trí đọc/ghi kế tiếp của các thao tác tương đối.
- `limit`: ranh giới các vị trí hiện tại được phép thao tác.
- `mark`: điểm position được đánh dấu tùy chọn.

Mẫu ghi rồi đọc:

~~~java
ByteBuffer buffer = ByteBuffer.allocateDirect(16);
buffer.put(new byte[] {65, 66, 67}); // Viết A B C; position=3.
buffer.flip();                       // limit=3, position=0.
while (buffer.hasRemaining()) {
    System.out.print((char) buffer.get());
}
buffer.clear(); // Chuẩn bị ghi tiếp, KHÔNG giải phóng native memory.
~~~

Đây là đoạn minh họa. Việc `clear()` **không xóa bytes**, không bảo đảm zeroize dữ liệu nhạy cảm và **không giải phóng backing storage**. Nó chỉ thay đổi các chỉ số trạng thái.

Tương tự, `compact()` di chuyển các byte chưa đọc về đầu buffer rồi thiết lập lại chỉ số để tiếp tục ghi. Trên buffer lớn, di chuyển bytes cũng có chi phí. Thiết kế parser/queue nên tránh compact dữ liệu quá nhiều lần không cần thiết.

### View chia sẻ storage dù cursor độc lập

`duplicate()`, `slice()` và `asReadOnlyBuffer()` tạo các view có trạng thái con trỏ riêng nhưng vẫn chia sẻ backing bytes với buffer gốc.

~~~java
ByteBuffer root = ByteBuffer.allocateDirect(4);
root.put(new byte[] {1, 2, 3, 4});
ByteBuffer view = root.duplicate();
view.put(0, (byte) 9);
System.out.println(root.get(0)); // 9
~~~

Đây là đoạn mã minh họa. Hai object khác nhau không phải hai allocation native độc lập. Nếu một thread đang thao tác vùng bytes qua `root` và thread khác qua `view`, đồng bộ con trỏ riêng **không** tự bảo đảm tính an toàn của backing storage.

View read-only cấm write qua view đó nhưng không làm backing bytes bất biến nếu một alias ghi được vẫn còn tồn tại. Vì vậy, khi đưa buffer cho worker hoặc socket operation, phải xác định ownership và thời điểm producer được phép reuse.

## 5. Heap và direct ảnh hưởng I/O performance ra sao?

Một số channel/native I/O API có thể truyền dữ liệu từ/to direct memory mà không phải sao chép qua một mảng heap trung gian. Đây là **lý do direct buffer được khuyến nghị cân nhắc với các I/O operation cường độ cao**, không phải lời hứa mọi thao tác đều zero-copy.

Trong một số implementation, khi truyền một heap buffer qua FileChannel/SocketChannel, runtime có thể dùng một vùng native tạm để đưa dữ liệu vào syscall, kéo theo copy. Khi dùng direct buffer, một số copy nội bộ đó có thể được tránh.

Tuy nhiên:

1. Nếu dữ liệu ban đầu là `byte[]` hoặc `String`/object trên heap, copy vào direct buffer vẫn là copy. Đừng bỏ qua chi phí chuyển dữ liệu ban đầu.
2. Đọc file từ ổ đĩa thường liên quan đến **kernel page cache** và copy giữa kernel/user memory; direct `ByteBuffer` không tự động bật kernel zero-copy.
3. Các API như `FileChannel.transferTo/transferFrom` có thể dùng đường truyền tối ưu hóa hoặc fallback tùy OS, filesystem, channel và điều kiện runtime. Chúng khác với chỉ dùng `allocateDirect`.
4. Direct allocation/cleanup đắt hơn heap allocation ở nhiều tình huống. Buffer nhỏ sống ngắn có thể chạy chậm hơn khi dùng direct.
5. CPU cache, paging, memory pressure, container memory và cách truy cập `get/put` đều ảnh hưởng throughput.
6. Với tệp nhỏ hoặc parser xử lý dữ liệu trên heap, direct không chắc đem lại lợi ích đo được.
7. Đọc một file rất lớn không có nghĩa phải cấp phát một direct buffer cực lớn. Thường hiệu quả hơn là streaming bằng các chunk vừa phải và có bounded queue.

Do vậy, hãy benchmark **đúng pipeline sản phẩm**: file size, I/O pattern, OS, filesystem, SSD/HDD, concurrency, buffer size và tải GC. Không dùng một microbenchmark đơn giản để khẳng định “direct nhanh hơn X%” trong mọi hệ thống.

## 6. Một ví dụ Java 17+ độc lập, biên dịch/chạy được

Chương trình dưới đây cho thấy: heap/direct buffer nhận biết qua `isDirect()/hasArray()`; `duplicate()` dùng chung byte nhưng có position riêng; direct buffer được dùng với `FileChannel.write` và heap buffer dùng để đọc lại; cuối cùng lấy metric về direct buffer pool từ management API.

Lưu tệp **`BufferMemoryDemo.java`**:

~~~java
import java.io.IOException;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class BufferMemoryDemo {
    public static void main(String[] args) throws IOException {
        ByteBuffer heap = ByteBuffer.allocate(16);
        ByteBuffer direct = ByteBuffer.allocateDirect(16);
        System.out.println("Heap: direct=" + heap.isDirect()
                + ", hasArray=" + heap.hasArray());
        System.out.println("Direct: direct=" + direct.isDirect()
                + ", hasArray=" + direct.hasArray());

        heap.put("ABCD".getBytes(StandardCharsets.UTF_8));
        ByteBuffer duplicate = heap.duplicate();
        duplicate.put(0, (byte) 'Z');
        duplicate.position(2);
        System.out.println("Shared bytes: " + (char) heap.get(0));
        System.out.println("Independent positions: " +
                (heap.position() != duplicate.position()));

        Path file = Files.createTempFile("nio-direct-", ".dat");
        try {
            direct.put("DATA".getBytes(StandardCharsets.UTF_8));
            direct.flip();
            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                while (direct.hasRemaining()) {
                    channel.write(direct);
                }
                channel.position(0);
                ByteBuffer received = ByteBuffer.allocate(16);
                while (true) {
                    int n = channel.read(received);
                    if (n == -1 || !received.hasRemaining()) break;
                }
                received.flip();
                System.out.println("File: " +
                        StandardCharsets.UTF_8.decode(received));
            }
        } finally {
            Files.deleteIfExists(file);
        }

        for (BufferPoolMXBean bean : ManagementFactory
                .getPlatformMXBeans(BufferPoolMXBean.class)) {
            if ("direct".equals(bean.getName())) {
                System.out.println("Direct pool observable: " +
                        (bean.getCount() >= 1));
            }
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac BufferMemoryDemo.java
java BufferMemoryDemo
~~~

**Stdout thực tế đã biên dịch và chạy trên JDK thử nghiệm:**

~~~text
Heap: direct=false, hasArray=true
Direct: direct=true, hasArray=false
Shared bytes: Z
Independent positions: true
File: DATA
Direct pool observable: true
~~~

Diễn giải:

- `allocate(16)` tạo heap buffer có backing array truy cập được; `allocateDirect(16)` tạo direct buffer không đưa `byte[]` ra ngoài.
- Sau `heap.put("ABCD")`, `heap.position()` là 4. `duplicate.position(2)` không sửa position của heap gốc, nhưng `duplicate.put(0, 'Z')` thay cùng storage, nên `heap.get(0)` trả chữ `Z`.
- `FileChannel.write(direct)` có thể chỉ ghi **một phần** số byte còn lại, vì thế vòng `while (direct.hasRemaining())` là đúng thay vì tin một lệnh write luôn đủ. Sau ghi, code đặt `channel.position(0)` rồi đọc vào heap buffer.
- `received.flip()` chuyển từ ghi vào buffer sang giải mã; `StandardCharsets.UTF_8.decode(received)` trả dữ liệu `DATA`.
- `Files.createTempFile` tạo file test riêng; `finally` xóa file, `try-with-resources` đóng channel.
- `BufferPoolMXBean` tên `direct` quan sát native/direct buffer pool do JDK quản lý. Dòng cuối chỉ kiểm tra đã có ít nhất một direct buffer trong pool tại thời điểm quan sát; nó **không được dùng làm quy tắc số lượng cố định trên mọi JDK/phiên bản**.

Ở demo, `FileChannel` là blocking file I/O với tệp rất nhỏ, nên vòng đọc cuối không cần một bộ selector hay thuật toán riêng cho mạng non-blocking. Trong production, muốn giảm rủi ro vòng lặp không tiến triển nếu provider trả 0 nhiều lần, cần kiểm tra `n==0`, timeout/budget hoặc quy tắc mode/provider cụ thể. Code ở đây không dùng `FileChannel.force()`, nên không trình bày tính bền dữ liệu.

## 7. Đếm bộ nhớ đúng: heap, direct, mapped và native khác

Một sơ đồ đơn giản hóa:

~~~text
Java process
  |
  +-- Java heap: objects, byte[], heap ByteBuffer backing arrays
  |
  +-- Native/off-heap:
  |     +-- Direct ByteBuffer backing memory
  |     +-- MappedByteBuffer mappings (memory-mapped regions)
  |     +-- Thread stacks
  |     +-- Metaspace / code cache / JVM internals
  |     +-- JNI/native libraries, allocators, buffers khác
  |
  +-- Process virtual address space / resident memory (RSS)
  |
OS:
  +-- Filesystem page cache và phần memory do kernel quản lý
  +-- Container/cgroup memory accounting tùy hệ thống
~~~

Sơ đồ chỉ để định hướng, không phải một bảng cộng số học tuyệt đối. Memory mapping có thể khiến cùng những physical pages của file xuất hiện trong thống kê RSS và page cache theo quy tắc kernel; không được cộng mọi con số từ công cụ giám sát như các bộ nhớ độc lập rồi kết luận tổng.

Một vài khái niệm quan trọng:

- **Heap used:** lượng object/data dùng trong heap được GC quản lý.
- **Heap committed:** dung lượng heap JVM đã commit; có thể khác `-Xmx`.
- **Direct buffer capacity:** tổng dung lượng logic của direct buffers được JVM buffer pool theo dõi; không nhất thiết bằng toàn bộ native memory của process.
- **Direct buffer memory used:** thống kê bytes native backing theo management bean; có thể khác tổng capacity do alignment/implementation.
- **Mapped buffer capacity/used:** thống kê mapping mà JVM theo dõi; nó không nói toàn bộ pages đều resident trong RAM.
- **RSS:** số trang resident của process theo OS, chứa nhiều nhóm memory khác nhau, không phải riêng heap/direct.
- **Container memory usage:** có thể phản ánh thêm cách kernel tính page cache/anonymous memory; thay đổi theo container/cgroup runtime.

**Không suy luận “heap usage 30% thì còn 70% RAM cho direct”.** Heap limit, direct limit, process RSS và container memory limit là các ràng buộc khác nhau.

## 8. Giới hạn và cấp phát direct memory

Tùy runtime, HotSpot có lựa chọn JVM `-XX:MaxDirectMemorySize=<size>` để kiểm soát giới hạn direct buffer allocations mà cơ chế direct buffer của JDK quản lý. Ví dụ cách chỉ định:

~~~bash
java -XX:MaxDirectMemorySize=256m -Xmx512m MyApplication
~~~

Đây là lệnh **minh họa**, `MyApplication` phải là main class thực tế. Flag này là tùy chọn của HotSpot/implementation, không phải đặc tả portable cho mọi JVM.

Không tự giả định giá trị mặc định của `MaxDirectMemorySize` giống nhau giữa các nhà cung cấp JDK, các phiên bản và cách cấu hình. Kiểm tra runtime thực tế và tài liệu phù hợp.

Tăng giới hạn direct memory có thể cho phép ứng dụng dùng thêm direct buffer nhưng **không tạo thêm RAM vật lý**. Trong container bị giới hạn memory, tăng heap + direct limit quá cao so với budget có thể khiến process bị OOM killer kill trước khi ứng dụng kịp bắt lỗi hoặc chạy cleanup.

Ví dụ ngân sách cần tính:

~~~text
Total process / container budget:
    Java heap committed
  + direct buffer backing allocations
  + metaspace and code cache
  + thread stacks
  + native/JNI allocations
  + mapped/resident pages and OS overhead
  + headroom for burst, GC, runtime, monitoring
~~~

Đây là mô hình lập ngân sách, không phải công thức cộng chính xác từ các chỉ số đo vì chúng có thể chồng lấn cách hạch toán. Nên có **headroom thực tế** thay vì đặt mỗi giới hạn độc lập sát trần container.

### Lỗi khi cấp phát quá nhiều

`ByteBuffer.allocateDirect(n)` có thể gây `OutOfMemoryError` khi đạt hạn mức direct memory được JDK quản lý hoặc native allocation thất bại. Triệu chứng khác có thể là latency spike do JVM cố dọn vùng direct không còn sử dụng.

Nếu thấy OOME kiểu *Cannot reserve ... bytes of direct buffer memory* trên một bản HotSpot, cần điều tra size/count/lifetime của buffer và giới hạn hiện tại thay vì chỉ tăng heap. Thông điệp chính xác không phải phần của Java SE API contract; đừng parse log theo một chuỗi duy nhất để xác định mọi nguyên nhân.

## 9. Vòng đời và vì sao pool thường quan trọng

Có hai cách dùng direct buffer:

**Không tái sử dụng, allocation per request:**

~~~java
ByteBuffer buffer = ByteBuffer.allocateDirect(64 * 1024);
try {
    // Xử lý một request.
} finally {
    // Không có method close() portable trên ByteBuffer.
}
~~~

Đây là mã minh họa. Tạo nhiều buffer cho các request nhanh có thể sinh hàng loạt native allocations. `ByteBuffer` **không triển khai `AutoCloseable`**, nên không thể dùng `try (ByteBuffer buffer = ...)` để đóng direct memory bằng API chuẩn.

**Dùng pool với giới hạn:**

~~~text
Application starts:
  allocate N direct buffers of size S
Request:
  acquire one buffer -> use -> clear -> return to pool
On overload:
  wait bounded / reject / backpressure
Application shutdown:
  stop using buffers, drop references, let supported runtime clean up
~~~

Pool giúp tái sử dụng allocation, nhưng **pool không tự giảm usage**: giữ 100 direct buffers 1 MiB nghĩa là giữ lượng backing memory tương ứng ngay cả khi tải đã xuống thấp. Dùng size classes, high-watermark và chính sách trim/evict khi phù hợp. Không tạo pool unbounded.

Một ví dụ tính capacity của pool (chỉ là phép tính ngân sách): 128 buffers × 256 KiB = **32 MiB** tổng dung lượng data backing theo capacity, chưa tính object/native overhead/alignment và các buffer khác của ứng dụng. Nếu concurrency thực tế vượt 128, phải chờ/trả lỗi/backpressure thay vì cứ tự cấp phát vô hạn.

### Ownership khi trả buffer vào pool

Không được trả buffer về pool **trước khi I/O async hoàn thành**. Nếu một task đang viết từ buffer mà thread khác gọi `clear()` rồi dùng buffer ấy cho request kế tiếp, dữ liệu truyền có thể bị đổi hoặc sai thứ tự.

Một protocol đúng cần:

1. Buffer được lease độc quyền cho request/operation.
2. Trong lúc đã giao cho channel operation/worker, producer không được sửa nội dung/cursor.
3. Với non-blocking `write`, buffer vẫn có bytes pending cho tới khi `hasRemaining()==false`.
4. Khi tất cả bên dùng đã hoàn tất và không còn view còn sống cần tham chiếu, owner mới trả buffer vào pool.
5. Buffer được `clear()`/zeroize nếu yêu cầu bảo mật trước khi cấp cho tenant/request mới.
6. Pool bounded có xử lý overload, shutdown và leak detection (lease chưa trả).

Đặc biệt, `duplicate()/slice()/asReadOnlyBuffer()` chia sẻ backing memory. Nếu một view còn được worker dùng mà root buffer đã trả về pool thì có nguy cơ dữ liệu bị ghi đè. Cursor độc lập không thay thế ownership của bytes.

## 10. Áp lực bộ nhớ với nhiều connection và tệp lớn

Một thiết kế như “mỗi kết nối có một direct buffer 1 MiB” có thể nhanh chóng tiêu tốn rất nhiều native memory. Với 10.000 kết nối, chỉ riêng danh nghĩa input buffer 1 MiB mỗi kết nối đã xấp xỉ **9,77 GiB** dữ liệu buffer, chưa tính outbound queue, TLS buffers, heap, thread stacks và native runtime.

Không cần một buffer đầy đủ cho mọi file:

- Dùng **bounded chunk buffers** 8 KiB–1 MiB tùy benchmark/load, không ép cứng kích thước.
- **Stream** file qua các chunks, xử lý xong tới đâu gửi/ghi tới đó.
- Với per-connection buffers, cấp phát lazy khi cần, giới hạn số bytes queued và có chính sách reclaim.
- Nếu dữ liệu có thể rất lớn, không gọi `Files.readAllBytes(path)` trên toàn tệp nếu vượt memory budget.
- Khi producer nhanh hơn consumer, **backpressure**: dừng đọc tạm thời, chặn bounded queue, giới hạn đồng thời hoặc fail fast.
- Nếu dùng async/non-blocking I/O, quản lý partial reads/writes và không tái sử dụng buffer khi operation còn pending.

Điểm cốt lõi là **số lượng buffer × capacity × concurrency × thời gian giữ** quyết định native footprint, không chỉ kích thước từng file.

### Áp lực heap gián tiếp dù dùng direct

Direct buffers có wrapper objects trên heap và references trong các collection/pools. Các object giữ native memory sống dài có thể nhỏ trên heap nhưng “ghim” vùng off-heap lớn. Do vậy một heap dump với rất ít byte object có thể chưa giải thích vì sao direct memory đang gần hết.

Ngoài ra, chuyển đổi bytes `String`, mã hóa UTF-8, parsing JSON, tạo array copies vẫn cấp phát trên heap. Dùng direct buffer cho FileChannel không loại bỏ toàn bộ heap allocations của ứng dụng.

## 11. FileChannel: read/write đúng và không nhầm zero-copy

Khi ghi từ `ByteBuffer`:

~~~java
while (buffer.hasRemaining()) {
    int written = channel.write(buffer);
    if (written == 0) {
        // Chưa có tiến triển: tùy loại channel/mode mà chờ hoặc đổi chiến lược.
    }
}
~~~

Đây là đoạn minh họa. Một lời gọi `write` **không được mặc định** chuyển hết `buffer.remaining()`. Với `SocketChannel` non-blocking, `write()==0` có thể xảy ra thường xuyên; phải đợi `OP_WRITE` thay vì busy-spin. Với `FileChannel` truyền thống, behavior phụ thuộc provider/mode và điều kiện I/O; code production vẫn nên xử lý lỗi và progress.

Khi đọc:

~~~java
int n = channel.read(buffer);
if (n == -1) {
    // EOF.
} else if (n > 0) {
    buffer.flip();
    // Xử lý bytes đã nhận.
    buffer.compact(); // Giữ bytes frame chưa được tiêu thụ, nếu có.
} else {
    // 0 byte lần này: không kết luận EOF.
}
~~~

Đây cũng là mã minh họa, cần `channel` và `buffer` hợp lệ. Nếu đã tiêu thụ hết bytes nhận được thì `clear()` có thể phù hợp; nếu còn frame chưa đủ, `compact()` giữ phần còn lại.

**Zero-copy không đồng nghĩa direct buffer:** thuật ngữ thường nói tới đường dữ liệu có thể tránh những lần copy giữa kernel/user space, chẳng hạn một số triển khai của `FileChannel.transferTo/transferFrom`. Cần kiểm tra giới hạn và return count của những phương thức này; có thể chỉ chuyển một phần dữ liệu hoặc dùng fallback. `allocateDirect` không bảo đảm luôn đi qua kernel zero-copy.

## 12. Memory-mapped file khác direct allocation thông thường

`FileChannel.map(...)` tạo `MappedByteBuffer` đại diện một vùng được ánh xạ tới file. Nó là một loại direct buffer nhưng **khác về mô hình bộ nhớ** với `ByteBuffer.allocateDirect()`:

- Storage gắn với memory-mapped region do hệ điều hành quản lý.
- Truy cập buffer có thể kéo các file-backed pages vào bộ nhớ resident theo nhu cầu (page faults).
- Mapping rất lớn không nhất thiết làm toàn bộ file lập tức resident trong RAM.
- Vòng đời mapping và giải phóng vùng nhớ phụ thuộc reachability/runtime; API Java 17 `MappedByteBuffer` không cung cấp một `close()` chuẩn cho mapping.
- Đóng `FileChannel` không có nghĩa mapping đã bị unmapped ngay.
- Khi file bị truncate/change bất thường hoặc hệ điều hành trả lỗi mapping, hành vi có thể phụ thuộc nền tảng và vùng truy cập.

Ví dụ minh họa:

~~~java
try (FileChannel channel = FileChannel.open(path, StandardOpenOption.READ)) {
    MappedByteBuffer mapped = channel.map(FileChannel.MapMode.READ_ONLY, 0, size);
    // Truy cập các byte trong mapped; không tự assume toàn bộ file đã resident.
}
~~~

Đây là mã minh họa; `path` phải tồn tại, `size` hợp lệ trong giới hạn buffer mapping, import `MappedByteBuffer`, `FileChannel` và `StandardOpenOption`. Nếu muốn xử lý một file lớn vượt giới hạn addressable của một `ByteBuffer`, phải map thành nhiều vùng với windowing hoặc dùng read/write theo chunk. Không map cả file nhiều terabyte thành một buffer duy nhất rồi hy vọng `capacity()` chứa được số lớn hơn phạm vi int.

### Khi nào dùng mapped file?

Memory mapping có thể hữu ích với random access, index lớn, hoặc truy cập lặp nhiều vùng file với pattern hợp lý. Nhưng với tệp chỉ cần copy tuần tự một lần, `FileChannel.read` hoặc `transferTo` có thể đơn giản hơn và đôi khi nhanh hơn; cần đo thực tế.

Mapped buffer còn tạo ra các quan tâm riêng: kiểm soát page cache, mapping lifecycle, truncate races, virtual memory address usage và cơ chế flush metadata/durability. `MappedByteBuffer.force()` yêu cầu thay đổi ở vùng mapped được ghi xuống storage theo hợp đồng API; không phải transaction và không áp dụng tương đương cho mọi loại direct buffer.

## 13. Quan sát direct memory qua BufferPoolMXBean

Java Management API có `java.lang.management.BufferPoolMXBean` để quan sát các pool buffer mà VM quản lý. Có thể lấy danh sách bằng:

~~~java
for (BufferPoolMXBean pool : ManagementFactory.getPlatformMXBeans(
        BufferPoolMXBean.class)) {
    System.out.printf("%s: count=%d, capacity=%d, used=%d%n",
            pool.getName(),
            pool.getCount(),
            pool.getTotalCapacity(),
            pool.getMemoryUsed());
}
~~~

Đây là đoạn minh họa cần import `BufferPoolMXBean` và `ManagementFactory`, có thể đặt trong method. Tên pool thường gặp ở HotSpot gồm `direct` và `mapped`, nhưng tập tên/counters là đặc tính của implementation và phiên bản JDK.

- `getCount()`: số buffer được pool quản lý.
- `getTotalCapacity()`: tổng dung lượng `capacity` của buffer trong pool tính bằng byte.
- `getMemoryUsed()`: ước lượng số bytes bộ nhớ được pool sử dụng, có thể lớn/nhỏ khác capacity do cách quản lý/native alignment. **Giá trị có thể là -1** nếu implementation không có số đo.
- Những chỉ số này **không bao phủ mọi native memory**. JNI `malloc`, thread stack hoặc allocations của một thư viện C có thể không được cộng trong direct buffer pool.
- Con số có thể thay đổi do GC/cleaners, cache direct buffer tạm, hoạt động I/O và thời điểm đo.

Dùng số đo này cùng heap metrics, GC logs, RSS/container metrics thay vì dựa một chỉ số để quyết định vấn đề là leak hay workload peak.

### Native Memory Tracking (NMT)

Trên một số bản HotSpot có **Native Memory Tracking**, có thể chạy JVM với cấu hình như:

~~~bash
java -XX:NativeMemoryTracking=summary -Xmx512m MyApplication
~~~

Sau đó có thể dùng công cụ JDK như `jcmd <pid> VM.native_memory summary` trên một process phù hợp, nếu cấu hình và quyền truy cập cho phép. Đây là lệnh minh họa với PID giả định, không phải kết quả đo cho chương trình demo.

NMT phân loại nhiều allocations do JVM theo dõi nhưng **không phải hệ thống đo mọi native allocation của thư viện ngoài JVM**. RSS, procfs, container metrics, profiler native và allocation tracing có thể cần thiết để truy dấu các vùng ngoài phạm vi.

## 14. Đọc biểu hiện OOME và áp lực bộ nhớ

Một số hiện tượng:

| Hiện tượng | Khả năng cần kiểm tra | Hướng điều tra |
| --- | --- | --- |
| `OutOfMemoryError: Java heap space` | Heap objects/mảng chiếm quá mức `-Xmx` | Heap dump, GC logs, object retaining paths |
| OOME liên quan `direct buffer memory` | Direct buffer allocations vượt budget hoặc không giải phóng kịp | BufferPoolMXBean, pool leases, `MaxDirectMemorySize`, retention |
| Container bị kill không có Java stacktrace rõ | Tổng RSS/cgroup memory vượt limit | Container events, RSS, page cache, heap+native budget |
| Heap thấp nhưng RSS cao | Direct/native/mmap/code cache/thread stacks | JMX buffer pools, NMT, OS profiler |
| GC hoạt động nhiều khi direct allocations tăng | Native cleanup/allocator pressure hoặc heap refs | GC logs, allocation profile, object references |
| Latency tăng lúc tải cao | Pool exhaustion, allocation cost, page faults, backpressure thiếu | Metrics theo connection, queue depth, timeouts |
| Mapped memory lớn nhưng heap thấp | Mapping virtual space/file-backed pages | Mapped buffer counters, RSS/maps, page residency |

Không phải cứ thấy direct buffer count tăng là memory leak. Một pool được thiết kế để giữ buffers tới mức high-watermark sẽ khiến count tăng rồi ổn định. **Leak** thường thể hiện ở buffer/lease/retained references tăng mà không giảm theo vòng đời mong đợi, hoặc số buffers đang được giữ không tương ứng với workload.

### Thứ tự xử lý sự cố

1. Đo heap used/committed/max, GC pauses và object retention.
2. Đo direct/mapped buffer count/capacity/memory used theo thời gian.
3. Đo RSS/process virtual memory và container limit/usage.
4. Kiểm tra tham số JVM như `-Xmx` và `-XX:MaxDirectMemorySize` ở runtime thật.
5. Tìm nơi `allocateDirect` được gọi nhiều hoặc pool không được trả.
6. Đối chiếu số connection, buffers leased, pending output, worker queue và file mapping count.
7. Thử giới hạn concurrent operations và buffer size để xác nhận causal relationship.
8. Chỉ sau khi hiểu nguyên nhân mới điều chỉnh memory budgets hoặc cấu trúc allocator.

Đặt `System.gc()` thành cách giải quyết thường xuyên để “dọn direct memory” là một anti-pattern: GC không phải API thu hồi direct buffer có thời điểm xác định, có thể tăng latency và che giấu quản lý buffer sai.

## 15. ByteBuffer và an toàn đa luồng

`ByteBuffer` là mutable. Heap hay direct không thay đổi điều này. Hai thread thao tác `position/limit` của cùng object mà không có ownership/đồng bộ có thể gây lỗi cursor. Hai view khác object cũng có thể chia sẻ byte vùng backing, nên ghi đồng thời vẫn có nguy cơ race.

Các lựa chọn an toàn:

- **Thread confinement**: một buffer do một event loop/thread sở hữu ở từng thời điểm.
- **Per-connection buffers**: mỗi kết nối có input/decoder state riêng; output queue riêng.
- **Ownership transfer**: chuyển giao buffer cho worker, không tái sử dụng cho tới khi worker hoàn tất.
- **Copy immutable payload**: copy bytes nhỏ sang `byte[]` riêng hoặc object immutable khi cần giảm coupling.
- **Read-only views**: ngăn sửa qua view đó nhưng vẫn phải đảm bảo không có alias ghi từ thread khác.
- **Buffer slices phân vùng**: hai views trên vùng byte không chồng lấn có thể an toàn hơn khi ownership được xác định; nếu storage chung và lifetime chung cần quản lý đầy đủ.

Đặc biệt khi một buffer được truyền cho `AsynchronousFileChannel` hoặc API I/O bất đồng bộ, đừng mutate nội dung/position hay trả về pool trước khi operation kết thúc. Một buffer bị reuse sớm có thể khiến byte được ghi ra file không còn là payload ban đầu, dù không có exception.

## 16. Khi nào nên chọn loại buffer nào?

| Tình huống | Điểm khởi đầu hợp lý | Điều cần thử nghiệm |
| --- | --- | --- |
| Parser Java xử lý bytes nhỏ, cần `byte[]` | Heap `ByteBuffer.allocate` hoặc mảng byte | Allocation/GC, parser throughput |
| Socket/FileChannel throughput cao, buffer tái dùng | Direct ByteBuffer có pool bounded | Native memory pressure, copy count, throughput |
| Mỗi request rất nhỏ, sống cực ngắn | Heap buffer, hoặc pool phù hợp | Direct allocation cost có vượt benefit không |
| Copy file tuần tự rất lớn | FileChannel streaming, cân nhắc `transferTo` | Copy path, OS/filesystem behavior |
| Random access vào file lớn | `MappedByteBuffer` theo window hoặc FileChannel positional reads | Page faults, map lifetime, truncation risk |
| Nhiều client chậm | Queue/buffer bounded và backpressure | Memory per connection, high/low watermarks |
| Cross-language library cần `byte[]` | Heap hoặc explicit copy từ direct | Tổng copy và API integration |
| Container memory thấp | Đặt budget cho heap và native; đo trực tiếp | RSS, direct pool metrics, OS kill |

**Không chọn direct chỉ vì từ “performance”.** Khi source/consumer đều làm việc với object/mảng heap, direct có thể tăng số lần copy. Khi I/O native lặp nhiều trên cùng buffer, direct có thể hữu ích. Cần quyết định dựa trên số liệu.

## 17. Benchmark thực tế: tránh kết luận sai

Một benchmark NIO nên đo:

1. **Warmup/JIT**: tránh so sánh code chưa được JIT tối ưu với code đã warm.
2. **Allocation path**: phân biệt tốc độ cấp phát direct/heap với tốc độ read/write khi buffer đã được reuse.
3. **I/O thật**: dùng file sizes, access pattern, storage và concurrency gần sản phẩm.
4. **Cold vs warm page cache**: lần đọc đầu có thể chủ yếu đo storage, lần sau đo cache.
5. **GC + native stats**: throughput tốt nhưng OOME/latency spike thì không phải kết quả tốt.
6. **CPU, RSS và memory bandwidth**: chi phí copy, context switch và page fault có thể thay đổi.
7. **Độ lớn buffer**: thử nhiều kích thước, ví dụ các dải 8 KiB, 64 KiB, 1 MiB trên workload; không xem một kích thước là tối ưu phổ quát.
8. **Kịch bản overload**: client chậm, file lớn, request nhiều, queue đầy, cancellation.
9. **JMH cho microbenchmark CPU** và harness I/O riêng cho benchmark end-to-end; không suy luận từ một vòng đo `System.nanoTime()` đơn lẻ.

Nếu benchmark dùng `ByteArrayOutputStream` làm destination, nó không đo thực tế FileChannel/SocketChannel và không xác nhận lợi ích native I/O của direct buffer. Nếu data hoàn toàn nằm trong page cache, kết quả không thể đại diện cho cold disk.

## 18. Checklist thiết kế và vận hành

- [ ] Đã phân biệt heap limit, direct buffer limit và total container/RSS budget?
- [ ] Đã biết số connection/operations đồng thời và số buffer cần giữ tối đa?
- [ ] Đã xác định mỗi buffer cần capacity bao nhiêu, có size classes và giới hạn queue?
- [ ] Đã có backpressure khi producer nhanh hơn consumer?
- [ ] Đã đảm bảo `flip/clear/compact` theo trạng thái data, không dùng `clear()` để giải phóng memory?
- [ ] Đã rõ view nào cùng chia sẻ backing storage và vòng đời pool lease?
- [ ] Đã không tái sử dụng buffer trước khi async/partial write hoàn tất?
- [ ] Đã có metrics cho `direct`/`mapped` buffer pools và RSS/container memory?
- [ ] Đã tính chi phí mapped pages, thread stacks, metaspace, native libraries, không chỉ heap?
- [ ] Đã kiểm tra lỗi và cleanup cho native allocation, channel close, mapping lifecycle?
- [ ] Đã benchmark workload thật và so sánh heap/direct/mapped/transfer methods?
- [ ] Đã có giới hạn theo tệp lớn, không gom mọi bytes vào một mảng hoặc direct buffer?
- [ ] Đã tránh dùng `System.gc()`/reflection/private Cleaner API như workaround mặc định?
- [ ] Đã xét nguy cơ dữ liệu cũ khi trả buffer cho request/tenant khác và cần zeroization?
- [ ] Đã đặt headroom cho burst/GC/JVM/OS thay vì cộng các giới hạn sát trần?

## 19. Câu hỏi tự kiểm tra

1. `ByteBuffer.allocateDirect(1024)` có cấp backing array `byte[]` trên Java heap không? **Không**, đây là direct buffer với backing memory dùng cho native I/O.
2. `direct.isDirect()` và `direct.hasArray()` thường lần lượt là gì? **true và false**.
3. Heap buffer từ `ByteBuffer.allocate(1024)` thường cho `hasArray()` gì? **true**; nhưng read-only hoặc buffer đặc biệt không nhất thiết có backing array truy cập được.
4. `clear()` trên direct buffer có giải phóng native memory không? **Không**, nó chỉ đặt lại các cursor.
5. Có thể sử dụng direct buffer sau khi method scope kết thúc nếu view vẫn còn tham chiếu không? **Có thể**, vì lifetime phụ thuộc reachability, không phụ thuộc riêng scope lexical.
6. Vì sao `duplicate()` không giúp tách hoàn toàn dữ liệu giữa hai thread? Vì view có cursor riêng nhưng **cùng backing bytes**.
7. Direct buffer có luôn zero-copy với disk không? **Không**; lợi ích tùy đường native I/O, OS và API thực tế.
8. Heap used thấp mà container RSS cao có thể do đâu? Direct/mapped memory, native allocations, thread stacks, code cache và các nhóm khác.
9. `BufferPoolMXBean.getMemoryUsed()` có bao phủ mọi JNI `malloc` không? **Không**; chỉ là thống kê pool tương ứng theo JVM.
10. `-XX:MaxDirectMemorySize` có làm máy có thêm RAM không? **Không**; nó là một giới hạn/cấu hình cấp phát ở JVM triển khai có hỗ trợ.
11. Vì sao pool 256 MiB buffers có thể giữ native memory ngay cả khi không có request? Vì các buffer vẫn reachable qua pool để tái sử dụng.
12. Khi nào mới trả output buffer vào pool trong non-blocking write? **Sau khi mọi byte pending đã được chuyển/operation hoàn tất**, theo ownership protocol.
13. FileChannel đọc tệp 100 GiB có cần một direct buffer 100 GiB không? **Không**, dùng streaming/chunking hoặc mapping theo windows.
14. `MappedByteBuffer` khác `allocateDirect` ở đâu? Nó ánh xạ **vùng file** qua cơ chế memory mapping của OS và có lifecycle/page residency khác.
15. `FileChannel.transferTo` có phải cách khác tên của `allocateDirect` không? **Không**, đây là API truyền bytes giữa channels, có thể dùng tối ưu hóa khác.
16. Nếu hàng đợi output tăng vô hạn, có thể chữa triệt để bằng thêm direct buffers không? **Không**; cần backpressure và bounded queues.
17. Một Java heap dump có đủ để giải thích mọi native leak không? **Không**, cần buffer pool/NMT/OS metrics và phân tích references tương ứng.
18. Có nên benchmark chỉ một lần trên file nhỏ sau JIT rồi kết luận direct tốt hơn heap không? **Không**, phải kiểm tra nhiều workloads, allocation patterns và native memory.
19. Nếu direct buffer được lấy từ pool và một `slice()` vẫn được worker đọc, có an toàn để trả root về pool ngay không? **Không**, alias vẫn tham chiếu cùng backing storage.
20. Thực hành quan trọng nhất với direct memory là gì? **Giới hạn capacity × concurrency × lifetime, phân quyền ownership, đo native memory và chỉ dùng direct khi có lợi ích được xác nhận**.

## Tài liệu API tham khảo

- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `allocate`, `allocateDirect`, `isDirect`, `hasArray`, views và buffer cursor semantics.
- [Java SE 17 — Buffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html): `position`, `limit`, `capacity`, `flip`, `clear`.
- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): `read/write`, `map`, `transferTo/transferFrom`.
- [Java SE 17 — MappedByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html): force, mapping-backed memory và cách đồng bộ.
- [Java SE 17 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): `getCount`, `getMemoryUsed` và `getTotalCapacity`.
- [Java SE 17 — ManagementFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html): lấy platform management beans.
- [Oracle Java Troubleshooting Guide — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html): công cụ quan sát native memory của HotSpot.
