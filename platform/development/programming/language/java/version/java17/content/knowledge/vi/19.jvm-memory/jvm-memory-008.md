# Phân biệt rò rỉ heap, metaspace và bộ nhớ native trong Java 17

Một tiến trình Java có thể tăng mức sử dụng bộ nhớ dù heap chưa đầy. Ngược lại, heap có thể đầy dù hệ điều hành vẫn còn nhiều RAM. Để chẩn đoán đúng, cần phân biệt **Java heap**, **metaspace** và các vùng **native memory** khác. Cần nhớ rằng metaspace cũng được cấp phát từ bộ nhớ native của tiến trình.

- **Heap leak:** object không còn cần cho nghiệp vụ nhưng vẫn được giữ bởi tham chiếu có thể đi tới từ GC root.
- **Metaspace leak:** metadata class tiếp tục tồn tại vì class loader sở hữu các class đó vẫn còn được giữ sống.
- **Native memory growth/leak:** bộ nhớ ngoài heap tăng do thread stack, direct buffer, JNI/native library, code cache hoặc cấu trúc nội bộ JVM.

Bài này giải thích triệu chứng, nguyên nhân, các chỉ số JVM và hệ điều hành, cùng công cụ chẩn đoán còn dùng tốt trong Java 17.

## 1. Bản đồ bộ nhớ của một tiến trình Java

~~~text
Tiến trình Java
|
+-- Java heap
|   +-- Object và array
|   +-- Instance data
|
+-- Native memory
|   +-- Metaspace: metadata của class
|   +-- Thread stacks
|   +-- Direct buffers / NIO
|   +-- JIT code cache
|   +-- Cấu trúc nội bộ GC và JVM
|   +-- JNI và native libraries
|
+-- Các vùng ánh xạ file và vùng do hệ điều hành quản lý
~~~

Đây là sơ đồ khái niệm, không phải bố trí địa chỉ vật lý chính xác. Các vùng có thể được reserve hoặc commit theo cách khác nhau; công cụ đo của JVM và hệ điều hành cũng có thể phân loại chúng khác nhau.

### 1.1. Heap chứa object của ứng dụng

~~~java
User user = new User("An");
byte[] payload = new byte[1024 * 1024];
~~~

Các object và array này thường được cấp phát trên heap. Garbage Collector (GC) thu hồi heap object khi chúng không còn reachable từ GC root.

Heap thường được giới hạn bằng:

~~~bash
java -Xms512m -Xmx2g -jar app.jar
~~~

- `-Xms`: kích thước heap ban đầu.
- `-Xmx`: giới hạn heap tối đa.

`-Xmx` không phải giới hạn tổng bộ nhớ của tiến trình. Metaspace, thread stack, direct buffer, code cache và các vùng native khác còn sử dụng bộ nhớ bên ngoài heap.

### 1.2. Metaspace lưu metadata class

Metaspace lưu metadata phục vụ JVM quản lý class, method, field, runtime constant pool và các thông tin liên quan đến kiểu đã nạp.

Metaspace nằm trong **native memory**, không nằm trong Java heap. Vì thế:

- Heap có thể còn nhiều chỗ nhưng metaspace vẫn có thể cạn.
- Tăng `-Xmx` không trực tiếp giải quyết lỗi thiếu metaspace.
- Class loader còn sống có thể giữ metadata của các class do nó nạp.
- Khi class loader đủ điều kiện được thu hồi và class unloading diễn ra, metadata tương ứng có thể được giải phóng.

Metaspace có thể được giới hạn bằng `-XX:MaxMetaspaceSize`. Đặt giới hạn quá thấp có thể gây lỗi dù ứng dụng không có leak.

### 1.3. Native memory rộng hơn metaspace

Native memory là phần bộ nhớ tiến trình dùng ngoài heap. Ngoài metaspace, các vùng đáng chú ý gồm:

- Stack của từng platform thread.
- Direct byte buffer.
- JIT compiler và code cache.
- Cấu trúc nội bộ của JVM, GC, symbol table.
- Bộ nhớ được cấp phát bởi JNI hoặc native library.
- Một số vùng ánh xạ file hoặc vùng phục vụ I/O.

Do đó, **metaspace là một phần của native memory**, còn native memory là khái niệm rộng hơn.

## 2. Rò rỉ bộ nhớ nghĩa là gì?

Rò rỉ bộ nhớ xảy ra khi chương trình tiếp tục giữ bộ nhớ mà nó không còn cần cho công việc thực tế. Bộ nhớ đó không thể được tái sử dụng vì vẫn có tham chiếu hoặc cơ chế quản lý giữ nó lại.

Trong Java, GC tự động thu hồi object không còn reachable. Nhưng GC không thể tự biết object nào “không còn hữu ích” theo ý nghĩa nghiệp vụ. Nếu object vẫn reachable qua static field, cache, listener hoặc thread, GC phải coi nó còn sống.

### 2.1. Phân biệt leak với allocation rate cao

| Hiện tượng | Mô tả | Dấu hiệu thường thấy |
|---|---|---|
| Allocation rate cao | Tạo nhiều object nhưng chúng sớm unreachable | GC chạy thường xuyên; heap sau GC giảm rõ |
| Live set lớn | Nhiều object vẫn cần cho trạng thái hiện tại | Heap sau GC cao nhưng ổn định theo tải |
| Heap leak | Object không còn cần vẫn bị giữ tham chiếu | Heap sau GC tăng dần qua các chu kỳ tương đương |
| Native memory growth | Vùng native tăng theo thread, buffer, class metadata hoặc thư viện | RSS tăng trong khi heap không tăng tương ứng |

Một đợt tải cao có thể làm heap tăng hợp lệ. Không kết luận leak chỉ từ một ảnh chụp memory usage; cần quan sát xu hướng theo thời gian và so sánh ở tải tương đương.

### 2.2. GC không thể thu hồi object còn reachable

~~~java
import java.util.ArrayList;
import java.util.List;

public class HeapLeakExample {
    private static final List<byte[]> CACHE = new ArrayList<>();

    public static void retainForever() {
        while (true) {
            CACHE.add(new byte[1024 * 1024]);
        }
    }
}
~~~

Mỗi vòng lặp tạo một mảng khoảng 1 MiB rồi thêm vào static list. Vì list giữ tham chiếu đến tất cả mảng, chúng vẫn reachable. GC không thể thu hồi chúng.

Đây là leak do logic lưu giữ dữ liệu không có giới hạn. Cách sửa là thiết kế vòng đời dữ liệu:

- Đặt giới hạn kích thước cache.
- Dùng eviction policy phù hợp.
- Xóa dữ liệu khi hết hạn hoặc khi phiên làm việc kết thúc.
- Không giữ object lâu hơn nhu cầu nghiệp vụ.
- Kiểm soát số lượng listener, callback và task được đăng ký.

### 2.3. Một số nguồn gây heap leak phổ biến

| Nguồn giữ tham chiếu | Ví dụ | Cách xử lý |
|---|---|---|
| Static collection | List hoặc Map tích lũy object mãi mãi | Giới hạn kích thước, xóa phần tử theo vòng đời |
| Cache không giới hạn | Cache key tăng theo từng request | TTL, maximum size, eviction |
| Listener không hủy đăng ký | Event source giữ đối tượng đã hết vòng đời | Gọi unregister/remove listener |
| ThreadLocal | Thread pool giữ giá trị của request trước | Gọi `remove()` khi hoàn tất |
| Queue không tiêu thụ kịp | Producer nhanh hơn consumer | Backpressure và giới hạn queue |
| Session hoặc registry | Session cũ vẫn còn trong Map | Expiration và cleanup |
| Callback/future | Closure giữ object graph lớn | Hoàn tất/hủy tác vụ, bỏ tham chiếu không cần |
| ClassLoader bị giữ trong heap | Registry vẫn giữ loader của plugin cũ | Dọn registry, thread và context class loader |

Ví dụ với `ThreadLocal` trong thread pool:

~~~java
private static final ThreadLocal<RequestContext> CONTEXT =
        new ThreadLocal<>();

void handle(Request request) {
    try {
        CONTEXT.set(new RequestContext(request));
        process(request);
    } finally {
        CONTEXT.remove();
    }
}
~~~

Thread pool tái sử dụng thread sau khi request hoàn tất. Nếu không xóa giá trị, thread có thể giữ `RequestContext` và object graph liên quan lâu hơn dự kiến.

## 3. Nhận diện ba nhóm vấn đề qua triệu chứng

| Quan sát | Heap leak | Metaspace leak | Native memory growth |
|---|---|---|---|
| Heap used sau GC | Thường tăng dần | Có thể ổn định | Có thể ổn định |
| Số class đã nạp | Có thể ổn định | Thường tăng hoặc không unload | Có thể ổn định |
| Số class loader | Có thể ổn định | Có thể tăng liên tục | Có thể tăng nếu liên quan loader |
| Thread count | Có thể ổn định | Có thể ổn định | Có thể tăng nếu stack là nguồn |
| Direct buffer memory | Không nhất thiết tăng | Không nhất thiết tăng | Có thể tăng |
| Process RSS | Có thể tăng | Có thể tăng | Có thể tăng dù heap ổn định |
| OOME thường gặp | `Java heap space` | `Metaspace` | `Direct buffer memory`, `unable to create native thread` |

Bảng này định hướng điều tra, không phải quy tắc tuyệt đối. Một heap leak có thể giữ class loader và làm metaspace không được giải phóng; một native library leak có thể không xuất hiện trong heap dump.

## 4. Điều tra heap leak

### 4.1. Quan sát heap sau GC

Một chỉ số hữu ích là lượng heap còn được sử dụng sau khi GC đã có cơ hội thu hồi object không còn reachable.

Nếu heap used tăng sau nhiều chu kỳ GC trong khi tải và trạng thái nghiệp vụ tương đương, hãy điều tra object đang được giữ lại.

Không chỉ nhìn heap used tức thời. Trong lúc ứng dụng chạy, heap có thể tăng do allocation trước khi GC diễn ra.

### 4.2. Bật GC log trong Java 17

Java 17 dùng Unified JVM Logging:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

GC log giúp quan sát:

- Thời điểm và loại GC.
- Heap trước và sau GC.
- Tần suất GC.
- Pause time.
- Mức heap được thu hồi qua từng chu kỳ.

Nếu heap sau GC liên tục cao hơn ở các giai đoạn tải tương đương, đó là dấu hiệu cần điều tra live object và retention path.

### 4.3. Dùng jcmd xem histogram và heap dump

Tìm PID của tiến trình Java rồi dùng `jcmd`:

~~~bash
jcmd <pid> GC.class_histogram
~~~

Histogram cho biết số lượng instance và tổng byte theo class. So sánh nhiều snapshot có thể chỉ ra class nào tăng bất thường.

Tạo heap dump:

~~~bash
jcmd <pid> GC.heap_dump filename=heap.hprof
~~~

Có thể mở heap dump bằng Eclipse Memory Analyzer (MAT) hoặc VisualVM tương thích. Tập trung vào:

- Dominator tree.
- Retained heap.
- Path to GC roots.
- Collection hoặc cache đang giữ nhiều object.
- Các instance tăng mạnh giữa hai snapshot.

Heap dump có thể làm ứng dụng pause và cần dung lượng đĩa lớn. File dump cũng có thể chứa dữ liệu nhạy cảm; lưu trữ và chia sẻ theo chính sách bảo vệ dữ liệu của hệ thống.

### 4.4. Retained heap và dominator

Shallow size là kích thước trực tiếp của object. Retained heap là lượng bộ nhớ có thể được giải phóng nếu object đó không còn giữ các object khác sống.

Một cache có thể chỉ chiếm vài KB ở bản thân Map, nhưng giữ hàng trăm MB object thông qua các entry. Khi điều tra leak, retained heap và đường dẫn từ GC root thường hữu ích hơn việc chỉ xem shallow size.

## 5. Metaspace leak và vòng đời class loader

Metaspace chứa metadata của các class đã được JVM nạp. Một class gắn với class loader đã định nghĩa nó. Khi class loader còn reachable, JVM không thể đơn giản giải phóng metadata của các class do loader đó định nghĩa.

Trong ứng dụng chạy lâu, đặc biệt hệ thống có plugin, hot reload, application server hoặc framework tạo class động, class loader có thể bị giữ lại sau khi module đã ngừng hoạt động.

### 5.1. Một tình huống class loader leak

1. Ứng dụng tạo class loader mới để nạp plugin.
2. Plugin được sử dụng.
3. Ứng dụng dừng plugin về mặt nghiệp vụ.
4. Một registry static vẫn giữ tham chiếu tới class hoặc class loader của plugin.
5. Class loader không trở thành unreachable, nên metadata không được giải phóng.

Các nguồn giữ loader thường gặp:

- Static Map chứa class, instance hoặc loader.
- Thread còn chạy code của plugin.
- Thread context class loader vẫn trỏ tới loader cũ.
- ThreadLocal giữ object do plugin định nghĩa.
- Listener, executor, timer hoặc callback chưa được hủy.
- Cache của framework giữ reflection metadata.

### 5.2. Class unloading không phải thao tác unload tùy ý

JVM thường thu hồi metadata của các class khi class loader định nghĩa chúng đủ điều kiện được thu hồi và cơ chế class unloading diễn ra. Vì thế, dọn một tham chiếu tới object instance chưa chắc đủ; cần kiểm tra toàn bộ đường tham chiếu tới class loader.

`URLClassLoader.close()` đóng resource mà loader dùng, chẳng hạn JAR file handle. Lệnh này **không tự làm class loader unreachable và không đảm bảo class được unload**. Ứng dụng vẫn phải dọn các tham chiếu sống tới loader.

### 5.3. Dấu hiệu metaspace tăng

- Metaspace used tăng theo số lần deploy/reload plugin.
- Số class đã nạp tăng liên tục.
- Số class loader tăng theo từng vòng đời module.
- Heap dump cho thấy loader cũ vẫn reachable.
- GC không làm giảm đáng kể metaspace dù đã dừng các module cũ.

Metaspace tăng không luôn đồng nghĩa leak. Ứng dụng có thể nạp thêm class hợp lệ theo tải hoặc cấu hình; cần so sánh với số class loader, class đã nạp và vòng đời deploy.

### 5.4. Theo dõi class loading bằng JMX

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;

ClassLoadingMXBean classLoading =
        ManagementFactory.getClassLoadingMXBean();

System.out.println("Loaded: " + classLoading.getLoadedClassCount());
System.out.println("Total loaded: " + classLoading.getTotalLoadedClassCount());
System.out.println("Unloaded: " + classLoading.getUnloadedClassCount());
~~~

- `getLoadedClassCount`: số class hiện đang được nạp.
- `getTotalLoadedClassCount`: tổng số class đã được nạp kể từ khi JVM khởi động.
- `getUnloadedClassCount`: tổng số class đã được unload.

Nếu tổng loaded tăng là bình thường, nhưng số currently loaded cứ tăng theo từng lần reload và không giảm, hãy điều tra class loader và khả năng unload.

## 6. Giới hạn và theo dõi metaspace

### 6.1. MaxMetaspaceSize

Có thể đặt giới hạn:

~~~bash
java -XX:MaxMetaspaceSize=256m -jar app.jar
~~~

Khi metadata cần thiết vượt giới hạn, JVM có thể ném:

~~~text
java.lang.OutOfMemoryError: Metaspace
~~~

Không tăng giới hạn chỉ để che dấu leak. Nếu class loader cũ bị giữ sống, tăng giới hạn chỉ kéo dài thời gian trước khi lỗi xuất hiện và làm tăng áp lực bộ nhớ native.

### 6.2. MetaspaceSize không phải MaxMetaspaceSize

| Tùy chọn | Ý nghĩa |
|---|---|
| `-XX:MetaspaceSize` | Ngưỡng ban đầu liên quan tới việc kích hoạt GC để thu hồi class metadata |
| `-XX:MaxMetaspaceSize` | Giới hạn tối đa cho metaspace |

Không nhầm `MetaspaceSize` là dung lượng metaspace tối đa. Thay đổi ngưỡng GC không thay thế việc xử lý class loader leak.

### 6.3. Xem thống kê class loader

Có thể dùng:

~~~bash
jcmd <pid> VM.classloader_stats
~~~

Lệnh này cung cấp thống kê class loader và lượng metadata liên quan. Kết hợp với số class đã nạp, số class unload và heap dump để tìm loader nào vẫn còn tồn tại.

Có thể xem các memory pool qua JMX; tên pool cụ thể phụ thuộc JVM:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;

for (MemoryPoolMXBean pool :
        ManagementFactory.getMemoryPoolMXBeans()) {
    System.out.println(
            pool.getName() + " : " + pool.getUsage()
    );
}
~~~

Tìm pool có tên liên quan tới Metaspace hoặc Compressed Class Space trên HotSpot. Không hard-code tên pool nếu ứng dụng cần chạy trên nhiều JVM vendor.

## 7. Native memory ngoài metaspace

Khi heap và metaspace không giải thích được mức tăng RSS, hãy điều tra các vùng native khác.

### 7.1. Thread stack

Mỗi platform thread có stack riêng để lưu frame, local variable và trạng thái gọi hàm. Nhiều thread đồng thời có thể làm native memory tăng đáng kể.

Các yếu tố cần xem:

- Số lượng thread đang sống.
- Kích thước stack cấu hình cho mỗi thread.
- Mức stack thực tế đã commit.
- Giới hạn thread/process của hệ điều hành.
- Bộ nhớ còn lại cho tiến trình.

`-Xss` cấu hình kích thước stack cho mỗi thread:

~~~bash
java -Xss512k -jar app.jar
~~~

Giảm `-Xss` quá mức có thể dẫn tới `StackOverflowError` nếu call stack sâu. Tăng số thread mà không giới hạn có thể dẫn tới `OutOfMemoryError: unable to create native thread`.

Theo dõi thread:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

ThreadMXBean threads = ManagementFactory.getThreadMXBean();

System.out.println("Live threads: " + threads.getThreadCount());
System.out.println("Peak threads: " + threads.getPeakThreadCount());
~~~

Nếu thread count tăng liên tục, hãy tìm thread leak: executor không shutdown, tạo thread theo request, task bị kẹt hoặc thread giữ tài nguyên lâu hơn dự kiến.

### 7.2. Direct ByteBuffer

`ByteBuffer.allocateDirect` cấp phát bộ nhớ ngoài heap:

~~~java
ByteBuffer buffer = ByteBuffer.allocateDirect(16 * 1024 * 1024);
~~~

Direct buffer hữu ích trong một số luồng I/O vì có thể giảm sao chép giữa heap và native I/O. Tuy nhiên, nó vẫn tiêu thụ bộ nhớ của tiến trình.

Nếu ứng dụng tạo direct buffer liên tục và giữ tham chiếu, native memory tăng dù heap object chứa buffer wrapper tương đối nhỏ.

Không nên cấp phát direct buffer mới cho mọi thao tác nhỏ. Hãy cân nhắc tái sử dụng buffer, pooling có giới hạn và theo dõi vòng đời.

Theo dõi qua `BufferPoolMXBean`:

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

for (BufferPoolMXBean pool :
        ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
    System.out.println("Pool: " + pool.getName());
    System.out.println("Count: " + pool.getCount());
    System.out.println("Used: " + pool.getMemoryUsed());
    System.out.println("Capacity: " + pool.getTotalCapacity());
}
~~~

Pool thường có tên `direct` và `mapped` trên HotSpot. `getMemoryUsed` và `getTotalCapacity` là các số liệu riêng; không cộng chúng một cách máy móc với heap used để suy ra RSS.

Nếu direct memory bị cạn, có thể gặp:

~~~text
java.lang.OutOfMemoryError: Direct buffer memory
~~~

Có thể cấu hình giới hạn direct memory bằng `-XX:MaxDirectMemorySize`, nhưng cần điều tra việc tạo/giữ buffer trước khi tăng giới hạn.

### 7.3. JNI và native library

Ứng dụng có thể gọi mã native qua JNI hoặc thư viện bên thứ ba. Bộ nhớ do mã native cấp phát không nhất thiết được phản ánh trong heap dump.

Dấu hiệu:

- RSS tăng trong khi heap used và metaspace tương đối ổn định.
- NMT không giải thích hết phần tăng.
- Leak xuất hiện sau khi gọi một native library hoặc driver cụ thể.
- Bộ nhớ chỉ được giải phóng khi tiến trình kết thúc.

Điều tra cần kết hợp log của thư viện, profiler native, công cụ hệ điều hành và kiểm tra việc giải phóng tài nguyên native ở phía JNI. Đừng giả định GC sẽ thu hồi mọi vùng mà native code tự cấp phát.

### 7.4. JIT code cache và cấu trúc nội bộ JVM

JVM dùng native memory cho code cache chứa mã máy được JIT compiler sinh ra, cùng các cấu trúc quản lý GC, symbol, compiler và runtime.

Nếu code cache gần đầy, JVM có thể ghi cảnh báo hoặc giảm khả năng biên dịch tối ưu; đây không nhất thiết là heap leak.

Hãy quan sát log, thống kê NMT và các chỉ số JVM trước khi thay đổi cấu hình code cache. Không quy mọi mức tăng native memory chưa giải thích được thành metaspace.

## 8. So sánh các loại OutOfMemoryError

Thông báo OOME thường cung cấp manh mối ban đầu:

| Thông báo | Vùng/vấn đề có thể liên quan | Hướng điều tra |
|---|---|---|
| `Java heap space` | Không thể cấp phát object trên heap | Heap dump, GC log, retained heap, `-Xmx` |
| `GC overhead limit exceeded` | GC dành quá nhiều thời gian nhưng thu hồi rất ít heap | Heap leak, live set quá lớn, allocation pattern |
| `Metaspace` | Không đủ vùng chứa class metadata hoặc chạm giới hạn | Class loader, class loading/unloading, `MaxMetaspaceSize` |
| `Compressed class space` | Không đủ vùng compressed class space | Số class, class loader, cấu hình class space |
| `Direct buffer memory` | Không thể cấp phát thêm direct buffer | BufferPoolMXBean, buffer lifecycle, direct memory limit |
| `unable to create native thread` | Không tạo được thread native mới | Thread count, stack, OS process/thread limit, RAM |
| `Native memory allocation (malloc) failed` | JVM hoặc native code không cấp phát được vùng native | NMT, OS memory, container limit, JNI/native libraries |

Một thông báo không luôn chỉ ra duy nhất nguyên nhân. Ví dụ `unable to create native thread` có thể do giới hạn thread của hệ điều hành dù máy vẫn còn RAM. `Java heap space` có thể do `-Xmx` quá thấp so với live set hợp lệ chứ chưa chắc là leak.

## 9. Đo heap và non-heap bằng Java Management API

Java cung cấp các API quản lý bộ nhớ trong `java.lang.management`.

### 9.1. MemoryMXBean

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;

MemoryMXBean memory = ManagementFactory.getMemoryMXBean();

MemoryUsage heap = memory.getHeapMemoryUsage();
MemoryUsage nonHeap = memory.getNonHeapMemoryUsage();

System.out.println("Heap used: " + heap.getUsed());
System.out.println("Heap committed: " + heap.getCommitted());
System.out.println("Heap max: " + heap.getMax());

System.out.println("Non-heap used: " + nonHeap.getUsed());
System.out.println("Non-heap committed: " + nonHeap.getCommitted());
System.out.println("Non-heap max: " + nonHeap.getMax());
~~~

Các trường:

- `used`: lượng bộ nhớ đang được sử dụng theo pool/region được báo cáo.
- `committed`: lượng bộ nhớ JVM đã cam kết có thể dùng.
- `max`: giới hạn tối đa nếu xác định được; có thể không xác định.

**Non-heap trong MemoryMXBean không đồng nghĩa với toàn bộ native memory.** Nó phản ánh các vùng non-heap mà JVM memory management quản lý, ví dụ metaspace và code cache trên HotSpot. Thread stack, native allocation từ JNI và nhiều vùng khác không được thể hiện đầy đủ ở đây.

### 9.2. Xem từng MemoryPoolMXBean

~~~java
for (MemoryPoolMXBean pool :
        ManagementFactory.getMemoryPoolMXBeans()) {

    MemoryUsage usage = pool.getUsage();

    System.out.printf(
            "%s: used=%d, committed=%d, max=%d%n",
            pool.getName(),
            usage == null ? -1 : usage.getUsed(),
            usage == null ? -1 : usage.getCommitted(),
            usage == null ? -1 : usage.getMax()
    );
}
~~~

Tên và cách phân nhóm memory pool phụ thuộc JVM và collector. Không nên giả định mọi JVM đều trả về đúng một tên pool giống nhau.

### 9.3. Đừng dùng Runtime.freeMemory để đo native memory

~~~java
Runtime runtime = Runtime.getRuntime();

long heapUsed = runtime.totalMemory() - runtime.freeMemory();
long heapMax = runtime.maxMemory();
~~~

Các số liệu trên liên quan tới heap của JVM. Chúng không phải tổng RAM tiến trình, không bao gồm toàn bộ metaspace/direct memory/thread stack/native library.

Đây là nguồn nhầm lẫn thường gặp khi log một con số “memory used” rồi kết luận toàn bộ tiến trình chỉ dùng từng ấy bộ nhớ.

## 10. Native Memory Tracking (NMT)

HotSpot cung cấp Native Memory Tracking để theo dõi nhiều nhóm cấp phát native do JVM quản lý. NMT phải được bật khi khởi động JVM; không thể bật đầy đủ hồi tố cho một tiến trình đã chạy mà chưa bật tracking.

### 10.1. Bật NMT

Chế độ summary:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Chế độ detail:

~~~bash
java -XX:NativeMemoryTracking=detail -jar app.jar
~~~

`detail` cung cấp thông tin chi tiết hơn nhưng có overhead lớn hơn. Hãy chọn mức tracking phù hợp với môi trường điều tra.

### 10.2. Xem thống kê NMT bằng jcmd

~~~bash
jcmd <pid> VM.native_memory summary
~~~

Có thể yêu cầu đơn vị:

~~~bash
jcmd <pid> VM.native_memory summary scale=MB
~~~

Tạo baseline:

~~~bash
jcmd <pid> VM.native_memory baseline
~~~

Sau một khoảng thời gian hoặc sau một đợt tải, so sánh:

~~~bash
jcmd <pid> VM.native_memory summary.diff scale=MB
~~~

NMT diff giúp nhìn nhóm native memory nào tăng kể từ baseline, chẳng hạn Class, Thread, Code, GC hoặc các nhóm khác.

### 10.3. NMT có giới hạn

NMT hữu ích nhưng không phải công cụ đo toàn bộ mọi byte của tiến trình:

- NMT theo dõi các nhóm cấp phát native mà HotSpot quản lý.
- Native allocation của thư viện bên thứ ba/JNI có thể không được phản ánh đầy đủ.
- NMT không thay thế heap dump.
- NMT không thay thế công cụ hệ điều hành để xem RSS, virtual memory hoặc cgroup usage.
- Tracking có overhead; detail mode tốn thêm tài nguyên hơn summary.

Nếu RSS tăng mà NMT gần như không đổi, hãy điều tra phần native do thư viện ngoài JVM quản lý và số liệu từ hệ điều hành.

## 11. So sánh heap, metaspace và process memory

Các số liệu thường được dùng cho những câu hỏi khác nhau:

| Chỉ số | Trả lời câu hỏi | Nguồn |
|---|---|---|
| Heap used | Object trên heap đang dùng bao nhiêu? | MemoryMXBean, GC log |
| Heap after GC | Sau GC, còn bao nhiêu object sống? | GC log, heap dump |
| Metaspace used | Metadata class đang dùng bao nhiêu? | MemoryPoolMXBean, NMT |
| Direct buffer memory | Direct/mapped buffer đang sử dụng bao nhiêu? | BufferPoolMXBean |
| Thread count | Có bao nhiêu thread đang sống? | ThreadMXBean, `jcmd Thread.print` |
| Native memory categories | JVM đang dùng native memory ở nhóm nào? | NMT |
| RSS / working set | Bao nhiêu trang bộ nhớ đang resident trong RAM? | OS/process tools |
| Container memory | Container đang dùng bao nhiêu memory theo cgroup? | Container runtime / cgroup metrics |

### 11.1. RSS không bằng heap + metaspace một cách đơn giản

RSS là số trang tiến trình hiện đang resident trong RAM theo cách đo của hệ điều hành. RSS có thể bao gồm nhiều vùng khác nhau và chịu ảnh hưởng của shared pages, mapped files, page residency và cách hệ điều hành tính.

Vì vậy, không nên lấy heap used cộng metaspace used rồi mong ra đúng RSS. Cũng không nên coi tổng committed là số RAM vật lý đang thực sự resident.

### 11.2. Container memory limit

Trong container, giới hạn bộ nhớ thường áp dụng cho toàn bộ tiến trình/container, không chỉ heap.

Một ứng dụng có thể:

- Heap chưa chạm `-Xmx`.
- Metaspace vẫn còn dưới giới hạn.
- Nhưng thread stack, direct buffers và native allocations làm tổng memory vượt cgroup limit.
- Container runtime hoặc kernel dừng tiến trình do OOM.

Khi chạy trong container, phải theo dõi cả JVM metrics lẫn container memory usage/limit. Đừng đặt `-Xmx` bằng toàn bộ memory limit mà không dành phần cho native memory và overhead.

## 12. Quy trình điều tra theo dấu hiệu

Một quy trình có thứ tự giúp tránh thay đổi cấu hình theo cảm tính.

### Bước 1: Xác định chỉ số nào đang tăng

Thu thập cùng thời điểm:

- Heap used và heap after GC.
- Non-heap/metaspace usage.
- Direct buffer usage.
- Thread count.
- Process RSS/working set.
- Container memory nếu có.

Cần có chuỗi thời gian, không chỉ một snapshot.

### Bước 2: Nếu heap after GC tăng, lấy heap dump

Dùng GC log để xác định xu hướng, sau đó lấy hai heap dump ở các thời điểm có tải tương đương nếu cần. So sánh retained heap và path to GC roots để tìm collection, cache, thread hoặc listener giữ object.

### Bước 3: Nếu metaspace tăng, điều tra class loading

Quan sát:

- Loaded class count.
- Unloaded class count.
- Class loader statistics.
- Metaspace pool.
- Heap dump để tìm reference tới class loader cũ.

Đặc biệt xem các lần deploy/reload plugin, dynamic proxy, bytecode generation hoặc framework tạo class.

### Bước 4: Nếu heap ổn định nhưng RSS tăng, xem native memory

Bật NMT trong lần khởi chạy điều tra tiếp theo nếu chưa có. Lấy baseline, chạy workload, xem diff. Đồng thời kiểm tra:

- Direct buffer pool.
- Thread count và stack configuration.
- JNI/native libraries.
- Code cache và các nhóm native JVM.
- Container/OS memory metrics.

### Bước 5: Xác nhận bằng cách thay đổi một yếu tố

Sau khi tìm được nguồn nghi vấn, kiểm chứng bằng workload có thể lặp lại:

- Giới hạn cache rồi xem retained heap.
- Dọn ThreadLocal rồi xem object có được thu hồi không.
- Hủy listener hoặc executor rồi quan sát class loader.
- Giới hạn direct buffer pool rồi theo dõi BufferPoolMXBean.
- Giảm số thread hoặc điều chỉnh pool rồi xem native usage.

Không thay đổi đồng thời nhiều giới hạn vì sẽ khó xác định nguyên nhân thực sự.

## 13. Các lệnh chẩn đoán thường dùng trên Java 17

| Mục đích | Lệnh |
|---|---|
| Liệt kê tiến trình Java | `jcmd -l` |
| Xem VM flags | `jcmd <pid> VM.flags` |
| Xem class loader statistics | `jcmd <pid> VM.classloader_stats` |
| Xem histogram object | `jcmd <pid> GC.class_histogram` |
| Tạo heap dump | `jcmd <pid> GC.heap_dump filename=heap.hprof` |
| In thread dump | `jcmd <pid> Thread.print` |
| Xem NMT summary | `jcmd <pid> VM.native_memory summary` |
| Tạo NMT baseline | `jcmd <pid> VM.native_memory baseline` |
| So sánh NMT | `jcmd <pid> VM.native_memory summary.diff` |
| Bắt đầu JFR recording | `jcmd <pid> JFR.start name=MemoryProfile settings=profile duration=60s filename=memory.jfr` |

Một số lệnh có thể gây pause hoặc tạo file lớn. Thực hiện trên môi trường phù hợp, bảo đảm dung lượng lưu trữ và quyền truy cập file dump/recording.

### 13.1. Dùng Java Flight Recorder

JFR có thể ghi lại sự kiện cấp phát object, GC, thread, lock và nhiều hoạt động JVM khác. Bắt đầu recording:

~~~bash
jcmd <pid> JFR.start name=MemoryProfile settings=profile duration=60s filename=memory.jfr
~~~

Sau đó mở file `memory.jfr` bằng JDK Mission Control tương thích để phân tích.

JFR hữu ích khi cần tìm:

- Allocation hotspot.
- Tần suất và thời gian GC.
- Thread activity.
- Những đoạn code tạo object nhiều.
- Sự kiện JVM liên quan tới bộ nhớ.

JFR không thay thế heap dump khi cần xem object graph và đường tham chiếu giữ object sống. Hai công cụ trả lời hai câu hỏi khác nhau.

## 14. Những cách xử lý sai thường gặp

### 14.1. Tăng -Xmx để che heap leak

Tăng heap có thể giảm tần suất OOME trong ngắn hạn, nhưng nếu cache hoặc collection vẫn tích lũy vô hạn, leak vẫn tiếp diễn.

Hãy tìm retained object và đường tham chiếu trước khi quyết định thay đổi heap size.

### 14.2. Tăng MaxMetaspaceSize mà không kiểm tra class loader

Nếu class loader cũ vẫn bị giữ, tăng metaspace chỉ trì hoãn lỗi. Trước hết hãy tìm loader nào không được thu hồi và tham chiếu nào đang giữ nó.

### 14.3. Gọi System.gc() để xử lý leak

`System.gc()` chỉ yêu cầu JVM xem xét chạy GC; nó không đảm bảo mọi object sẽ được thu hồi. Object còn reachable vẫn phải được giữ lại. Gọi GC liên tục còn có thể làm giảm hiệu năng.

### 14.4. Chỉ nhìn heap để kết luận bộ nhớ tiến trình

Heap ổn định không có nghĩa native memory ổn định. Hãy theo dõi metaspace, direct buffer, thread và RSS cùng lúc.

### 14.5. Chỉ nhìn RSS để kết luận heap leak

RSS tăng có thể do thread stack, direct buffer, metaspace, native library hoặc page residency. Cần ghép số liệu JVM và OS để khoanh vùng.

### 14.6. Tắt GC hoặc ép giảm heap để tiết kiệm RAM

Thay đổi collector hoặc cấu hình heap mà không hiểu workload có thể làm pause tăng và khiến lỗi khó tái hiện hơn. Hãy thu thập số liệu trước, xác định vùng memory đang tăng rồi mới điều chỉnh.

## 15. Ví dụ tổng hợp: ghi nhận heap, non-heap, direct buffer và thread

Tạo file **`MemorySnapshot.java`**:

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.lang.management.ThreadMXBean;

public class MemorySnapshot {

    public static void main(String[] args) {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();

        printUsage("Heap", memory.getHeapMemoryUsage());
        printUsage("Non-heap", memory.getNonHeapMemoryUsage());

        System.out.println("Direct / mapped buffer pools:");

        for (BufferPoolMXBean pool :
                ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
            System.out.printf(
                    "%s: count=%d, used=%d, capacity=%d%n",
                    pool.getName(),
                    pool.getCount(),
                    pool.getMemoryUsed(),
                    pool.getTotalCapacity()
            );
        }

        ThreadMXBean threads = ManagementFactory.getThreadMXBean();

        System.out.println("Live threads: " + threads.getThreadCount());
        System.out.println("Peak threads: " + threads.getPeakThreadCount());

        Runtime runtime = Runtime.getRuntime();

        long heapUsed = runtime.totalMemory() - runtime.freeMemory();

        System.out.println("Runtime heap used: " + heapUsed);
        System.out.println("Runtime heap max: " + runtime.maxMemory());
    }

    private static void printUsage(String name, MemoryUsage usage) {
        System.out.printf(
                "%s: used=%d, committed=%d, max=%d%n",
                name,
                usage.getUsed(),
                usage.getCommitted(),
                usage.getMax()
        );
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 MemorySnapshot.java
java MemorySnapshot
~~~

Các số byte thay đổi theo máy và thời điểm chạy. Cần đọc chúng theo đúng phạm vi:

- Heap: vùng object do GC quản lý.
- Non-heap: các memory pool non-heap mà JVM báo cáo.
- Direct/mapped pool: bộ nhớ buffer được quản lý qua NIO buffer pools.
- Live threads: số thread đang sống.
- Runtime heap: số liệu heap, không phải tổng memory tiến trình.

Không cộng các số này một cách tùy tiện vì một số nhóm có thể có quan hệ bao hàm hoặc cách tính khác nhau giữa JVM vendor.

## 16. Bài tập thực hành

### Bài 1: Phân biệt leak và allocation rate cao

Một ứng dụng có heap used tăng lên 1 GB trước GC, sau GC giảm còn 250 MB. Lặp lại nhiều lần và mức sau GC tương đối ổn định.

**Câu hỏi:** Có đủ bằng chứng để kết luận heap leak không?

**Đáp án:** Chưa. Đây có thể là allocation rate cao nhưng object được thu hồi bình thường. Cần theo dõi heap sau GC ở các giai đoạn tải tương đương và điều tra retained object nếu xu hướng tăng.

### Bài 2: Static cache tăng vô hạn

Một static Map lưu request theo ID nhưng không xóa entry khi request hoàn tất.

**Câu hỏi:** Vùng nào tăng và vì sao GC không thu hồi entry?

**Đáp án:** Heap tăng vì static Map giữ key/value và object graph liên quan. Các object vẫn reachable qua static field nên GC không thể thu hồi. Cần giới hạn cache, TTL hoặc xóa entry theo vòng đời nghiệp vụ.

### Bài 3: Heap ổn định nhưng OOME Metaspace

Ứng dụng deploy plugin nhiều lần. Mỗi lần deploy tạo class loader mới; sau undeploy, registry vẫn giữ một Class object của plugin.

**Câu hỏi:** Vì sao metaspace có thể tăng?

**Đáp án:** Class object giữ liên hệ với class loader định nghĩa nó. Registry giữ class loader sống, nên metadata của các class thuộc loader đó chưa đủ điều kiện unload. Cần dọn registry và các tham chiếu tới loader, thread, ThreadLocal và callback liên quan.

### Bài 4: Direct buffer

Ứng dụng dùng `ByteBuffer.allocateDirect` để tạo buffer 32 MiB cho mỗi request nhưng không giới hạn số request đồng thời.

**Câu hỏi:** Vì sao heap dump có thể không giải thích hết RSS?

**Đáp án:** Payload buffer nằm ngoài heap. Heap dump chủ yếu cho thấy object wrapper và tham chiếu; cần theo dõi `BufferPoolMXBean`, NMT và số liệu OS để điều tra native/direct memory.

### Bài 5: Thread leak

Thread count tăng theo thời gian, heap sau GC ổn định nhưng container memory tăng.

**Câu hỏi:** Cần kiểm tra gì?

**Đáp án:** Kiểm tra thread dump, executor có được shutdown không, thread có bị block không, số thread tạo theo request và cấu hình `-Xss`. Stack của mỗi platform thread tiêu thụ native memory.

### Bài 6: NMT không giải thích được RSS

RSS tăng 800 MB nhưng NMT diff chỉ tăng 100 MB.

**Câu hỏi:** Có thể kết luận NMT sai không?

**Đáp án:** Không. NMT theo dõi các nhóm native memory do HotSpot quản lý và không bao quát mọi allocation của native library bên thứ ba. Cần điều tra JNI/native code, mapped memory, buffer và số liệu hệ điều hành.

## 17. Ghi nhớ

Khi chẩn đoán bộ nhớ Java 17, hãy phân biệt đúng ba phạm vi:

- **Heap leak:** object không còn cần nhưng vẫn reachable. Dùng GC log, heap dump, dominator tree và path to GC roots.
- **Metaspace leak:** class metadata không được giải phóng vì class loader vẫn còn sống. Theo dõi class loading, class unloading, class loader statistics và reference giữ loader.
- **Native memory growth:** bộ nhớ ngoài heap tăng do thread stack, direct buffer, JNI/native library, code cache hoặc cấu trúc JVM. Kết hợp NMT, BufferPoolMXBean, ThreadMXBean và OS metrics.

Metaspace thuộc native memory, nhưng không đại diện cho toàn bộ native memory. Heap used, non-heap used, direct buffer usage và process RSS là những chỉ số khác nhau; hãy dùng đúng chỉ số cho đúng câu hỏi.

Đừng chỉ tăng giới hạn bộ nhớ để che triệu chứng. Hãy tìm vùng đang tăng, xác định object hoặc resource nào giữ bộ nhớ, sửa vòng đời hoặc giới hạn tài nguyên, rồi xác nhận bằng workload có thể lặp lại.

## 18. Tài liệu tham khảo

- [Oracle Java SE 17 — MemoryMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html): số liệu heap và non-heap memory.
- [Oracle Java SE 17 — MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): thống kê các memory pool của JVM.
- [Oracle Java SE 17 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): số liệu direct và mapped buffer pool.
- [Oracle Java SE 17 — ClassLoadingMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html): số class đang nạp, tổng class đã nạp và class đã unload.
- [Oracle Java SE 17 — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): số liệu thread của JVM.
- [Oracle Java SE 17 — jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): lệnh chẩn đoán tiến trình Java, heap dump, class histogram, class loader và NMT.
- [Oracle Java SE 17 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html): cách bật và đọc thống kê native memory của HotSpot.
- [Oracle Java SE 17 — Troubleshooting Memory Leaks](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshooting-memory-leaks.html): quy trình điều tra heap leak và công cụ chẩn đoán.
- [OpenJDK JEP 195 — Handle Metaspace Allocation Failure](https://openjdk.org/jeps/195): bối cảnh quản lý lỗi cấp phát metaspace trong HotSpot.



