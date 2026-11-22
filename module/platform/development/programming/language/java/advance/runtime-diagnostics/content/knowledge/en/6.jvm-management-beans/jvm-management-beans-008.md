# 6.8 BufferPoolMXBean và ClassLoadingMXBean cho bộ đệm ngoài heap hoặc lớp được nạp

Trong chẩn đoán JVM, nhìn **heap used** thôi thường chưa đủ. Một dịch vụ có thể có Java heap tương đối ổn định nhưng **resident memory của process hoặc container tiếp tục tăng**; một dịch vụ khác có thể có số lớp đã được nạp ngày càng nhiều, trong khi số lớp đang còn được nạp gần như không đổi. Hai nhóm chỉ số quản trị Java SE 21 giúp đặt câu hỏi đúng là **BufferPoolMXBean** và **ClassLoadingMXBean**.

- **BufferPoolMXBean** mô tả các pool bộ đệm NIO mà JVM công bố, chẳng hạn **direct** và **mapped**. Nó cung cấp ước lượng số buffer, tổng dung lượng logic và lượng bộ nhớ đang được pool dùng.
- **ClassLoadingMXBean** mô tả hệ thống nạp lớp của JVM: số lớp hiện được nạp, tổng số lớp đã nạp từ lúc tiến trình khởi động, tổng số lớp đã unload, và trạng thái verbose của class loading.

Đây là **bằng chứng bổ sung**, không phải phép đo toàn bộ native memory, RSS, Metaspace hay công cụ tìm nguồn leak tự động. Bài này tập trung vào **API chuẩn Java SE 21** trong module **java.management**, sử dụng Java 21/HotSpot để minh họa khi cần; kết quả cụ thể có thể khác giữa các JVM, GC, workload và hệ điều hành.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Dùng **ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)** để liệt kê các buffer pool thực sự có trên JVM hiện tại.
2. Đọc đúng **getName()**, **getCount()**, **getTotalCapacity()**, **getMemoryUsed()**, đơn vị byte, tính xấp xỉ và trường hợp không có số liệu.
3. Dùng **ManagementFactory.getClassLoadingMXBean()** đọc **getLoadedClassCount()**, **getTotalLoadedClassCount()** và **getUnloadedClassCount()**.
4. Phân biệt **snapshot**, **counter tích lũy**, **delta/rate** và **gauge**, tránh kết luận leak từ một lần chụp.
5. Phân biệt **direct buffer**, **mapped buffer**, Java heap, Metaspace, memory mapping, native allocations và RSS/container memory.
6. Đọc MXBean qua API Java hoặc **platform JMX MBeanServer**, sử dụng đúng ObjectName/attribute.
7. Thiết kế cách lấy mẫu ít tác động, đối chiếu GC, classloader, NMT, file mappings và quá trình tăng tải.
8. Biết lúc nào chỉ số có ý nghĩa và khi nào cần thêm bằng chứng để kết luận **direct-memory retention** hoặc **classloader retention**.

## 2. MXBean là gì và vì sao cần hai loại này?

**MXBean** là management bean theo cơ chế JMX, dùng các kiểu dữ liệu có thể biểu diễn dưới dạng JMX open types để công cụ quản trị truy cập dễ dàng. Những MXBean nền tảng được đăng ký trong **platform MBeanServer** của chính JVM và có thể được đọc **trực tiếp trong code**, hoặc thông qua một **MBeanServerConnection** khi kết nối JMX phù hợp.

Đối với đề mục này, hai API chuẩn thuộc package **java.lang.management**:

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
~~~

Đây chỉ là **đoạn import minh họa**, không phải một chương trình Java độc lập. Hai cách lấy bean:

~~~java
var pools = ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class);
var loading = ManagementFactory.getClassLoadingMXBean();
~~~

Đây cũng là **đoạn sử dụng API minh họa**, sẽ được đặt vào chương trình chạy hoàn chỉnh ở phần thực hành. Với Java SE 21:

- Một JVM có thể có **một hoặc nhiều BufferPoolMXBean**, tùy implementation và những pool được công bố; không giả định bắt buộc chỉ có hai pool.
- Một JVM có **một ClassLoadingMXBean** cho thông tin nạp lớp ở cấp tiến trình.
- Hai bean này **đọc trạng thái của JVM đang thực thi code**; không phải mặc định đọc mọi Java process khác trên host.
- JMX từ xa cần một kết nối được xác thực/cho phép và chính sách bảo mật phù hợp. Không mở cổng JMX không bảo vệ lên mạng công cộng chỉ để xem số liệu.

### 2.1. Vì sao heap ổn định nhưng container vẫn tăng memory?

**-Xmx** và **MemoryMXBean.getHeapMemoryUsage()** chủ yếu nói về Java heap. Ngoài heap còn có thể có:

- Bộ nhớ của **direct ByteBuffer** do NIO dùng cho I/O.
- **Memory-mapped regions** gắn với file thông qua **FileChannel.map**.
- **Metaspace/class metadata** của các lớp và classloader.
- **Thread stacks**, bộ nhớ native của GC/JIT/runtime, code cache và các cấu trúc nội bộ.
- Memory được cấp phát bằng **JNI**, native libraries, allocator bên thứ ba, vùng shared memory, page cache và các yếu tố do OS/container tính toán.

**BufferPoolMXBean chỉ quan sát một phần trong số đó.** Nếu pool direct không tăng, không thể kết luận không có native-memory leak. Nếu số lớp đang nạp tăng, cũng chưa thể kết luận Metaspace tăng tương ứng từng byte hoặc classloader bị rò rỉ.

## 3. BufferPoolMXBean: định nghĩa các chỉ số

API **java.lang.management.BufferPoolMXBean** có các phương thức chính:

| Phương thức | Kiểu trả về | Ý nghĩa theo Java SE 21 |
| --- | --- | --- |
| **getName()** | String | Tên của buffer pool, ví dụ **direct** hoặc **mapped** trên HotSpot phổ biến. |
| **getCount()** | long | **Ước lượng** số buffer trong pool, không phải số lần cấp phát tích lũy từ lúc JVM khởi động. |
| **getTotalCapacity()** | long | **Ước lượng** tổng dung lượng của các buffer trong pool, tính bằng **byte**. |
| **getMemoryUsed()** | long | **Ước lượng** bộ nhớ JVM dùng cho pool, tính bằng **byte**, hoặc **-1L** nếu không có ước lượng. |
| **getObjectName()** | ObjectName | Danh tính MBean để truy cập qua JMX. |

**Điều được API bảo đảm:** các giá trị liên quan đến **pool** do JVM công bố; riêng **getMemoryUsed()** có thể **-1**. **Đừng giả định getCount hoặc getTotalCapacity là số hoàn toàn chính xác tại từng nano-giây**: tài liệu gọi chúng là **estimate**.

**getMemoryUsed() có thể khác getTotalCapacity().** JVM hoặc allocator có thể cần thêm overhead cho căn chỉnh địa chỉ, quản lý và cách cấp phát cụ thể. Không nên ép điều kiện **memoryUsed == totalCapacity** thành assert production. Khi tính dashboard, hiển thị riêng **count**, **capacity bytes** và **memoryUsed bytes**.

**Tên pool không phải danh sách cố định theo chuẩn.** Tên **direct** và **mapped** thường gặp trên HotSpot, nhưng code nên **liệt kê danh sách thực** và không hardcode rằng chắc chắn chỉ có hai. Một số implementation có thể công bố thêm nhóm mapped đặc biệt.

### 3.1. Direct buffers: vì sao nằm ngoài heap?

**ByteBuffer.allocateDirect(capacity)** tạo một **direct byte buffer**. Đối tượng Java **ByteBuffer** và metadata của nó vẫn là object quản lý được trên heap, nhưng nội dung buffer thường được chứa ở vùng bộ nhớ thuận lợi cho native I/O, có thể nằm ngoài Java heap. Java SE mô tả direct buffers có thể có chi phí cấp phát/giải phóng cao hơn và được dùng khi có lợi ích I/O đo được.

Ví dụ khái niệm:

~~~java
java.nio.ByteBuffer buffer =
        java.nio.ByteBuffer.allocateDirect(1024 * 1024);
~~~

Đây là đoạn minh họa, chưa phải chương trình độc lập. **Capacity** ở đây là **1.048.576 byte**. Pool **direct** trên HotSpot có thể phản ánh vùng cấp phát đó, nhưng không được khẳng định **getMemoryUsed** sẽ tăng chính xác 1.048.576 byte: còn các buffer của JVM, căn chỉnh và thời điểm cập nhật/thu hồi.

**Nhầm lẫn thường gặp:** thấy **heap used = 400 MiB**, **direct memory = 800 MiB** rồi kết luận process RSS = 1.200 MiB. Process còn Metaspace, stacks, code cache, shared mappings, tài nguyên OS...; các đại lượng có thể phản ánh khác nhau, nên phép cộng trên **không phải công thức RSS**.

### 3.2. Mapped buffers: dung lượng vùng map không đồng nghĩa RAM thực cư trú

**FileChannel.map(...)** trả về **MappedByteBuffer**, đại diện cho một vùng ánh xạ file. Dung lượng logic của vùng mapping có thể xuất hiện trong pool **mapped**.

Một mapping dung lượng **1 GiB** không nhất thiết làm process chiếm ngay **1 GiB RAM resident**:

- Mapping mô tả **vùng địa chỉ** và khả năng truy cập nội dung file.
- Các page có thể được nạp theo nhu cầu và bị OS thu hồi/đưa vào page cache.
- RSS, committed memory, file-backed pages và kích thước mapping không phải cùng một chỉ số.
- **getTotalCapacity** của pool mapped là tổng capacity logic ước tính, **không phải số page chắc chắn đang resident**.
- Việc đóng **FileChannel** không tự động làm mapping mất hiệu lực; vòng đời mapping gắn với mapped buffer và cơ chế thu hồi của JVM/OS.

Vì vậy, dùng BufferPoolMXBean để nhận diện **số lượng và quy mô buffer/mapping**, sau đó mới đối chiếu OS metrics khi muốn biết RAM thực tế.

### 3.3. Pool nào không được bao phủ?

Không tự động tính mọi khoản **Unsafe/native malloc**, JNI allocations, malloc của thư viện C/C++, custom native allocator, thread stacks, toàn bộ memory-mapped file do native code tự tạo, hay bộ nhớ kernel/container. Một thư viện có thể dùng direct ByteBuffer nhưng cũng có thể dùng native memory theo cách **không đi qua những pool mà MXBean theo dõi**.

Ngay cả khi **pool direct** tăng ổn định rồi dừng, process RSS vẫn có thể tăng từ nguồn khác. **BufferPoolMXBean là một tín hiệu cần phối hợp**, không phải native memory profiler tổng quát.

## 4. ClassLoadingMXBean: ba bộ đếm về lớp được nạp

**ClassLoadingMXBean** cung cấp:

| Phương thức | Kiểu | Loại metric | Ý nghĩa |
| --- | --- | --- | --- |
| **getLoadedClassCount()** | int | **Gauge** | Số lớp **hiện đang** được JVM nạp. Có thể tăng hoặc giảm. |
| **getTotalLoadedClassCount()** | long | **Counter tích lũy** | Tổng số lớp **đã nạp từ khi JVM bắt đầu chạy**. |
| **getUnloadedClassCount()** | long | **Counter tích lũy** | Tổng số lớp **đã được unload từ khi JVM bắt đầu chạy**. |
| **isVerbose()** | boolean | Trạng thái | Kiểm tra tính năng verbose class-loading output có bật không. |
| **setVerbose(boolean)** | void | Điều khiển | Bật/tắt verbose class-loading output **ở mức JVM toàn cục**; có thể gây overhead/log volume. |
| **getObjectName()** | ObjectName | Danh tính JMX | MBean cho class loading của process. |

Dùng:

~~~java
var bean = ManagementFactory.getClassLoadingMXBean();
long total = bean.getTotalLoadedClassCount();
int currentlyLoaded = bean.getLoadedClassCount();
long unloaded = bean.getUnloadedClassCount();
~~~

Đoạn trên chỉ minh họa cách gọi. **Counter tích lũy** như total/unloaded thường được phân tích bằng **chênh lệch giữa hai thời điểm trong cùng một lần chạy JVM**; không lấy tổng từ hai process khác nhau để tính rate.

### 4.1. Loaded hiện tại khác total loaded

Giả sử trong một JVM, tại thời điểm t1:

~~~text
loaded-now = 8.000
total-loaded-since-start = 10.000
unloaded-since-start = 2.000
~~~

Sau một khoảng thời gian, t2:

~~~text
loaded-now = 8.300
total-loaded-since-start = 10.500
unloaded-since-start = 2.200
~~~

Với các con số giả định:

- **Δtotal-loaded = +500**: có thêm 500 lượt nạp lớp được ghi nhận.
- **Δunloaded = +200**: có thêm 200 lượt unload được ghi nhận.
- **Δloaded-now = +300**: số lớp còn loaded tăng 300.

Nếu cửa sổ là **10 giây**, rate tải lớp trung bình theo counter là **500 / 10 = 50 lớp/giây**; unload rate là **20 lớp/giây**.

**Không buộc ba số phải thỏa đẳng thức tại mọi khoảnh khắc theo từng lần đọc method**, vì API được gọi tuần tự khi JVM khác thread vẫn có thể load/unload; đây **không phải snapshot transactionally consistent**. Trong dữ liệu đã làm tròn hoặc sampling qua JMX, chênh lệch còn có thể bị ảnh hưởng bởi timestamp, reset khi restart hoặc missing sample.

### 4.2. Class loading không phải số classloader hay byte Metaspace

**Một lớp có thể được nạp bởi các classloader khác nhau** và xuất hiện là những runtime classes khác nhau ngay cả khi cùng tên nhị phân. Đếm lớp **không cho bạn danh sách classloader gây ra chúng**, không chỉ ra object Java nào giữ classloader, và **không cho biết số byte Metaspace chính xác**.

Class unloading gắn với vòng đời loader và các điều kiện reachability/GC/VM. Không thể suy luận **đã bỏ tham chiếu tới một Class<?>** là lớp chắc chắn unload ngay. Nếu **getUnloadedClassCount()** không tăng trong một phút, có thể đơn giản là chưa có điều kiện unload, workload mới load lớp hoặc collector chưa thu gom tại thời điểm đó.

Để chẩn đoán classloader leak, cần phối hợp **số lớp**, **Metaspace memory**, **số/lifecycle của classloader**, **GC behavior**, **heap dump/classloader graph** hoặc những công cụ HotSpot phù hợp. Chỉ số MXBean chỉ giúp đặt giả thuyết.

### 4.3. Có nên gọi setVerbose(true)?

**isVerbose()** chỉ đọc trạng thái. **setVerbose(true)** bật xuất log class loading ở cấp **JVM toàn cục**, có thể tạo rất nhiều dòng. Tài liệu Java SE nói định dạng và nơi ghi verbose output **phụ thuộc implementation**; lời gọi đồng thời từ nhiều thread thay đổi **cùng một trạng thái toàn cục**.

Trong JDK 21 HotSpot, nếu cần chẩn đoán chi tiết, người vận hành thường có thể chọn Unified Logging như **-Xlog:class+load=info** hoặc dùng công cụ **jcmd PID VM.log** khi supported; không coi điều này là đồng nghĩa 1:1 với phương thức chuẩn **setVerbose** trên mọi JVM. Trước khi tăng log, cần biết file/stdout, quyền, duration, overhead và cách hoàn nguyên.

**Không đưa setVerbose(true) vào vòng polling của dashboard**. Đây là **hành động thay đổi hệ thống**, không phải getter. Khi truy cập JMX từ xa, chỉ cấp quyền ghi/mutate cho người vận hành có trách nhiệm và giới hạn truy cập.

## 5. So sánh các loại metric: tránh đánh đồng tên gọi

| Chỉ số | Phạm vi | Điều không được suy ra |
| --- | --- | --- |
| **MemoryMXBean.heapMemoryUsage.used** | Java heap theo JVM | Không phải process RSS/container usage. |
| **MemoryMXBean.nonHeapMemoryUsage.used** | Các vùng non-heap JVM báo qua MemoryMXBean | Không phải toàn bộ native memory hay tự động bằng direct+mapped. |
| **BufferPoolMXBean direct.memoryUsed** | Ước lượng memory của pool direct do JVM công bố | Không bao gồm tất cả native allocation của JNI/thư viện/VM. |
| **BufferPoolMXBean mapped.totalCapacity** | Tổng logical mapped capacity ước tính | Không bằng resident RAM hay chắc chắn bằng file bytes trên disk. |
| **MemoryPoolMXBean (Metaspace)** | Một memory pool JVM, thường thấy trên HotSpot | Không cho biết chính xác classloader nào gây giữ bộ nhớ. |
| **ClassLoadingMXBean.loadedClassCount** | Số class còn loaded | Không phải số classloader, byte metadata hoặc số object trên heap. |
| **ClassLoadingMXBean.totalLoadedClassCount** | Tổng classes loaded từ startup | Tăng không đủ chứng minh leak: nó là counter tích lũy. |
| **ClassLoadingMXBean.unloadedClassCount** | Tổng classes unloaded từ startup | Bằng 0 không tự chứng minh unloading bị hỏng. |
| **Process RSS / container memory** | Góc nhìn OS/cgroup về tài nguyên tiến trình/nhóm | Không quy nguyên nhân vào một pool Java khi chưa đối chiếu. |

Về đơn vị:

- Buffer count là số lượng, không phải byte.
- Capacity/memoryUsed được công bố bằng **byte**.
- **1 MiB = 1.048.576 byte**; chia cho **1024 × 1024** khi hiển thị MiB, ghi rõ đơn vị.
- Class count là **số lớp**, không phải memory size.
- Khi **memoryUsed = -1**, biểu diễn **unknown/unavailable**, **không vẽ như -1 byte hoặc 0 byte**.

## 6. Java 21 runnable: đọc snapshot của cả hai MXBean

Chương trình sau **chỉ đọc** các bean đang có ở chính JVM chạy chương trình. Nó chụp hai snapshot cách nhau một khoảng thời gian, in ra các pool được tìm thấy, và tính delta cho class-loading counters.

**Tệp MxBeanSurvey.java**

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

public final class MxBeanSurvey {
    record Classes(int now, long total, long unloaded) {}

    record Pool(String name, long count, long capacity, long used) {}

    record Snapshot(long tick, Classes classes, List<Pool> pools) {}

    private static Snapshot sample() {
        ClassLoadingMXBean loading =
                ManagementFactory.getClassLoadingMXBean();

        Classes c = new Classes(
                loading.getLoadedClassCount(),
                loading.getTotalLoadedClassCount(),
                loading.getUnloadedClassCount());

        List<Pool> pools = new ArrayList<>();
        for (BufferPoolMXBean bean
                : ManagementFactory.getPlatformMXBeans(
                        BufferPoolMXBean.class)) {
            pools.add(new Pool(
                    bean.getName(),
                    bean.getCount(),
                    bean.getTotalCapacity(),
                    bean.getMemoryUsed()));
        }
        pools.sort(Comparator.comparing(Pool::name));
        return new Snapshot(System.nanoTime(), c, pools);
    }

    private static String showBytes(long bytes) {
        return bytes < 0 ? "unavailable" : Long.toString(bytes);
    }

    private static void print(String label, Snapshot s) {
        System.out.printf(Locale.ROOT,
                "%s classes-now=%d classes-total=%d classes-unloaded=%d%n",
                label, s.classes.now,
                s.classes.total, s.classes.unloaded);
        for (Pool p : s.pools) {
            System.out.printf(Locale.ROOT,
                    "%s pool=%s count=%d capacityBytes=%d usedBytes=%s%n",
                    label, p.name, p.count, p.capacity,
                    showBytes(p.used));
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        int seconds = args.length == 0
                ? 2 : Integer.parseInt(args[0]);
        if (seconds < 1 || seconds > 60) {
            throw new IllegalArgumentException(
                    "interval must be 1..60 seconds");
        }

        Snapshot first = sample();
        Thread.sleep(seconds * 1000L);
        Snapshot second = sample();

        System.out.println("pid=" + ProcessHandle.current().pid());
        print("first", first);
        print("second", second);

        double elapsed =
                (second.tick - first.tick) / 1_000_000_000.0;
        System.out.printf(Locale.ROOT,
                "delta total=%d unloaded=%d current=%d elapsed=%.3fs%n",
                second.classes.total - first.classes.total,
                second.classes.unloaded - first.classes.unloaded,
                second.classes.now - first.classes.now,
                elapsed);
    }
}
~~~

Biên dịch và chạy bằng **JDK 21**:

~~~bash
javac --release 21 MxBeanSurvey.java
java MxBeanSurvey 2
~~~

**Đầu ra không có số cố định**. Chương trình luôn in một dòng **pid=...**, tiếp theo số lớp ở hai snapshot và một dòng cho **mỗi pool mà JVM công bố** trong từng snapshot, sau cùng là **delta total=... unloaded=... current=... elapsed=...s** nếu hoàn tất bình thường. Tên pool, thứ tự pool (được sắp theo tên), số byte, PID và delta phụ thuộc VM/load.

**Đọc đúng code:**

1. Dùng **getPlatformMXBeans(...)** thay vì tự giả định tên pool direct/mapped luôn có.
2. Với **getMemoryUsed()**, số âm được hiển thị **unavailable**, không dùng để tính MiB/rate.
3. Đọc các getter tuần tự; không có bảo đảm snapshot đồng thời 100% trên tất cả counters.
4. **System.nanoTime()** phù hợp để đo elapsed time trong process; thời điểm cụ thể khi đọc từng getter có sai số nhỏ so với timestamp cuối snapshot.
5. Đây là chương trình **demo chẩn đoán**, không phải collector production. Trong production cần metrics exporter, polling interval, storage và error handling phù hợp.
6. Mỗi lần chạy một process mới sẽ reset các **cumulative counters** của ClassLoadingMXBean; không gộp delta xuyên process hoặc replica.

**Lưu ý dùng jlink:** module **java.management** phải hiện diện trong runtime image nếu muốn dùng các API này. Một image quá tối giản có thể không cung cấp đầy đủ module/công cụ dù ứng dụng Java khác vẫn chạy được.

## 7. Java 21 runnable: quan sát direct và mapped buffer

Ví dụ dưới đây cố ý tạo **một direct ByteBuffer 1 MiB** và **một file mapping 4 KiB**; sau đó in các pool. Nó chỉ minh họa nơi tìm số liệu, **không phải bài benchmark hoặc công cụ chứng minh leak**.

**Tệp DirectMappedDemo.java**

~~~java
import java.io.IOException;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.ref.Reference;
import java.nio.ByteBuffer;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Comparator;
import java.util.List;

public final class DirectMappedDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile(
                "mxbean-mapping-", ".bin");
        file.toFile().deleteOnExit();

        try (FileChannel channel = FileChannel.open(
                file, StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {

            ByteBuffer seed = ByteBuffer.allocate(4096);
            while (seed.hasRemaining()) {
                channel.write(seed);
            }

            ByteBuffer direct =
                    ByteBuffer.allocateDirect(1024 * 1024);
            MappedByteBuffer mapped = channel.map(
                    FileChannel.MapMode.READ_WRITE, 0, 4096);
            direct.put(0, (byte) 42);
            mapped.put(0, (byte) 7);

            System.out.println(
                    "direct capacity=" + direct.capacity());
            System.out.println(
                    "mapped capacity=" + mapped.capacity());

            List<BufferPoolMXBean> pools =
                    ManagementFactory.getPlatformMXBeans(
                            BufferPoolMXBean.class);
            pools.stream()
                    .sorted(Comparator.comparing(
                            BufferPoolMXBean::getName))
                    .forEach(pool -> System.out.printf(
                            "pool=%s count=%d capacity=%d used=%d%n",
                            pool.getName(),
                            pool.getCount(),
                            pool.getTotalCapacity(),
                            pool.getMemoryUsed()));

            Reference.reachabilityFence(direct);
            Reference.reachabilityFence(mapped);
        }
    }
}
~~~

~~~bash
javac --release 21 DirectMappedDemo.java
java DirectMappedDemo
~~~

Hai dòng đầu khi thành công có giá trị **chính xác**:

~~~text
direct capacity=1048576
mapped capacity=4096
~~~

Những dòng bắt đầu bằng **pool=** có giá trị phụ thuộc runtime, kể cả trường hợp **used=-1** nếu JVM không có ước lượng; không có stdout số pool cố định. Trên HotSpot thường có các pool **direct** và **mapped**, nhưng API không hứa danh sách chỉ gồm hai tên đó.

**Vì sao code dùng Reference.reachabilityFence?** Để đánh dấu **direct/mapped buffer vẫn có thể đạt tới** tới cuối vùng quan sát; nếu không có tham chiếu dùng về sau, JIT và GC có thể làm thời điểm giải phóng tài nguyên thay đổi. Điều này **không biến số liệu thành snapshot nguyên tử**, chỉ tránh một yếu tố gây nhiễu phổ biến.

**Vì sao không xóa file ngay sau FileChannel.close?** Mapping còn có thể tồn tại sau khi channel đóng; hành vi xóa file đã mapped phụ thuộc OS, đặc biệt trên Windows. Ví dụ dùng **deleteOnExit()** cho file tạm của tiến trình; nếu cleanup bị giới hạn bởi OS, bạn có thể phải dọn theo chính sách file temp của môi trường thử nghiệm.

**Không tăng kích thước buffer tới hàng GiB để quan sát trong production.** Ví dụ 1 MiB/4 KiB đủ để hiểu cách dùng API. Việc tạo direct buffer tiêu tốn native memory thật và có thể gây OutOfMemoryError khi vượt giới hạn JVM/OS.

## 8. Cách phân tích delta, rate và xu hướng

**Snapshot đơn lẻ** chỉ cho biết trạng thái tại một thời điểm. Muốn đánh giá xu hướng, cần **nhiều mẫu** và chọn metric đúng loại.

### 8.1. Với ClassLoadingMXBean

Ký hiệu:

- **L(t)** = loaded classes hiện tại (gauge).
- **T(t)** = total loaded classes since startup (counter).
- **U(t)** = total unloaded classes since startup (counter).

Trong cùng một lần chạy JVM, với cửa sổ thời gian **Δt**:

~~~text
newly loaded    = T(t2) - T(t1)
newly unloaded  = U(t2) - U(t1)
net loaded      = L(t2) - L(t1)

load rate       = newly loaded / Δt
unload rate     = newly unloaded / Δt
~~~

Vì các getter không được chụp atomically, chênh lệch nhỏ giữa các phép tính cùng một lần đọc không tự là lỗi. Khi process restart, counters reset và cần mở một **series mới**; nếu delta âm hoặc instance/PID thay đổi, đừng biểu diễn bằng một rate âm thông thường.

**Ví dụ toán học xác định** với cửa sổ 10 giây:

~~~text
T(t1) = 10000      T(t2) = 10400
U(t1) =  2000      U(t2) =  2080
L(t1) =  8000      L(t2) =  8320

newly loaded   = 400
newly unloaded = 80
net loaded     = 320
load rate      = 40 classes/s
unload rate    = 8 classes/s
~~~

Một bài tập Java 21 có **stdout chính xác** để kiểm tra phép tính, không đọc hệ thống thật:

**Tệp CounterMath.java**

~~~java
public final class CounterMath {
    public static void main(String[] args) {
        long totalBefore = 10000, totalAfter = 10400;
        long unloadedBefore = 2000, unloadedAfter = 2080;
        int liveBefore = 8000, liveAfter = 8320;
        long elapsedSeconds = 10;

        long loadedDelta = totalAfter - totalBefore;
        long unloadedDelta =
                unloadedAfter - unloadedBefore;
        int liveDelta = liveAfter - liveBefore;

        System.out.println("loadedDelta=" + loadedDelta);
        System.out.println("unloadedDelta=" + unloadedDelta);
        System.out.println("liveDelta=" + liveDelta);
        System.out.println(
                "loadRate=" + loadedDelta / elapsedSeconds + "/s");
        System.out.println(
                "unloadRate=" + unloadedDelta / elapsedSeconds + "/s");
    }
}
~~~

~~~bash
javac --release 21 CounterMath.java
java CounterMath
~~~

**stdout chính xác:**

~~~text
loadedDelta=400
unloadedDelta=80
liveDelta=320
loadRate=40/s
unloadRate=8/s
~~~

**Đừng hiểu nhầm:** total loaded tăng đều theo thời gian là hành vi bình thường của một counter tích lũy; vấn đề đáng điều tra là **load rate bất thường, loaded-now/Metaspace tăng dai dẳng**, hoặc không unload khi lifecycle có lý do phải kết thúc, kết hợp bằng chứng khác.

### 8.2. Với BufferPoolMXBean

Các giá trị **count**, **capacity**, **memoryUsed** là **ước lượng trạng thái tại thời điểm đọc**, không phải counter số lượng allocation từ startup. Vì vậy:

~~~text
delta direct used (bytes) = direct.used(t2) - direct.used(t1)
delta direct count        = direct.count(t2) - direct.count(t1)
delta mapped capacity     = mapped.capacity(t2) - mapped.capacity(t1)
~~~

**Không diễn giải delta count=+10 nghĩa là có đúng 10 lần allocate**: trong cùng cửa sổ có thể đã cấp phát hàng nghìn buffer và giải phóng gần hết; pool chỉ thể hiện số buffer còn nằm trong thống kê lúc lấy mẫu. **Không tính delta/rate nếu memoryUsed=-1**.

Với trực tiếp NIO, nên theo dõi ít nhất **direct.count**, **direct.totalCapacity**, **direct.memoryUsed**. Với mapped, theo dõi count/capacity/memoryUsed, kết hợp mapping/RSS của OS khi cần. Đọc label **pool name** làm danh tính series; không gộp tất cả pool thành một và tự gọi là “off-heap memory của JVM”.

### 8.3. Sampling và biến động tự nhiên

- Mỗi mẫu không hoàn toàn đồng thời giữa hai bean; với workload biến động mạnh, một vài chênh lệch “không khớp” là khả dĩ.
- Sampling quá thưa có thể bỏ sót burst allocate/release, classloading spike hoặc unload xảy ra giữa các mốc.
- Sampling quá dày làm tăng overhead khi exporter/JMX/serialization nhiều instance; chọn interval theo độ nhạy và chi phí.
- Biểu đồ rate phải ghi **số giây thực giữa mẫu**, không mặc định luôn chính xác 5 giây vì scheduler có thể trễ.
- Các series gắn với **JVM process identity**: container/Pod ID, PID theo namespace, process start time, app version, JDK vendor và GC.
- Tách **startup/warmup** khỏi **steady-state**: classloading cao ở phút đầu có thể bình thường, còn loading lặp mãi sau mỗi request là dấu hiệu cần điều tra.

## 9. Truy cập bằng JMX: ObjectName và attribute

Theo Java SE 21, những MXBean này được đăng ký trên **platform MBeanServer**.

| MXBean | ObjectName |
| --- | --- |
| **ClassLoadingMXBean** | **java.lang:type=ClassLoading** |
| **BufferPoolMXBean** | **java.nio:type=BufferPool,name=<pool name>** |

Với ClassLoadingMXBean, JMX thường hiển thị các attributes:

~~~text
LoadedClassCount
TotalLoadedClassCount
UnloadedClassCount
Verbose
~~~

Với từng buffer pool, các attributes như:

~~~text
Name
Count
TotalCapacity
MemoryUsed
~~~

**Đừng hardcode một MBeanName từ suy đoán.** Để lấy đúng tên đã được JVM đăng ký, dùng **bean.getObjectName()** trong Java hoặc liệt kê domain **java.nio** của platform MBeanServer. Nếu tên pool chứa ký tự đặc biệt, cách quote/biểu diễn ObjectName có thể cần xử lý phù hợp theo JMX.

Ví dụ đọc qua MBeanServer **bên trong process**; đây là một đoạn code minh họa (không phải file Java độc lập):

~~~java
var server = ManagementFactory.getPlatformMBeanServer();
var cls = ManagementFactory.getClassLoadingMXBean();
Object loadedNow = server.getAttribute(
        cls.getObjectName(), "LoadedClassCount");
~~~

Đoạn trên sử dụng biến **ManagementFactory** với import như phần trước, và **getAttribute** cần xử lý checked exceptions trong code thật. Một ứng dụng quản trị có thể dùng **MBeanServerConnection** và proxy thay cho local server, với quyền mạng/JMX phù hợp.

**JConsole/JMX** giúp xem các MBeans mà không phải viết collector riêng. Khi kết nối từ xa, **không mở JMX public port thiếu xác thực/TLS**. Những thông tin này tiết lộ hạ tầng và trạng thái JVM; quyền ghi các attributes như **Verbose** cũng có thể làm thay đổi hệ thống.

## 10. Kết nối với Metaspace, direct-memory limits và chỉ số OS

### 10.1. Direct memory không đồng nghĩa mọi non-heap memory

**-XX:MaxDirectMemorySize** là cờ triển khai HotSpot liên quan giới hạn một nhóm cấp phát direct buffer. Nó **không phải trần chung cho mọi native memory allocation** và không chứng minh mọi mapped pages, JNI native malloc hoặc thread stacks đều nằm trong chỉ số direct của BufferPoolMXBean.

Ví dụ bạn thấy:

~~~text
heap used          = 600 MiB
direct pool used   = 400 MiB
mapped capacity    = 2.000 MiB
container memory   = 1.800 MiB
~~~

Bốn giá trị này **không thể cộng/so sánh bằng một công thức duy nhất**: mapped capacity là kích thước logic; container memory có cách hạch toán của cgroup và có thể bao gồm page cache; heap used không bằng reserved/committed heap; direct used có thể gồm overhead khác capacity. Trước khi kết luận vi phạm memory limit, kiểm tra hệ thống đang đo **memory.current/usage**, RSS, mapped pages, shared pages và byte units nào.

### 10.2. Metaspace thường biến động cùng classloading nhưng không theo tỷ lệ cố định

Trên HotSpot, **Metaspace** lưu class metadata trong native memory. Nhiều classloader bị giữ có thể khiến số lớp đang loaded và Metaspace cùng tăng, nhưng mỗi lớp có kích thước metadata khác nhau, có code cache, loader data, layout và các nguồn native allocation khác.

Để hiểu hiện tượng, có thể đối chiếu:

- **ClassLoadingMXBean loaded-now**, load/unload rate.
- **MemoryPoolMXBean** cho **Metaspace** và khi có **Compressed Class Space**, đọc pool theo tên thực tế.
- **JVM GC/unloading events** ở thời điểm tương ứng.
- **HotSpot jcmd VM.classloader_stats** nếu command được JVM hỗ trợ và người vận hành có quyền; nó cung cấp góc nhìn classloader hữu ích, nhưng không tự xác định nguyên nhân giữ tham chiếu.
- **Heap dump hoặc classloader graph** khi thật sự cần phân tích giữ object; đánh giá tác động/dung lượng trước khi tạo dump.

**Không chạy GC.class_histogram hoặc heap dump lặp đi lặp lại trên production chỉ để cập nhật dashboard.** Những thao tác có thể đắt đỏ hoặc ảnh hưởng pause, không thay thế getter MXBean nhẹ hơn.

### 10.3. Native Memory Tracking hỗ trợ nhưng có phạm vi riêng

Trên **HotSpot JDK 21**, **Native Memory Tracking (NMT)** có thể giúp quan sát memory nội bộ VM. Để sử dụng trong một process, thông thường cần bật **-XX:NativeMemoryTracking=summary** hoặc **detail** lúc khởi động; tài liệu nêu NMT có overhead và **không được bật lại bằng jcmd nếu trước đó tắt**.

Ví dụ khi đã bật NMT và xác nhận PID/công cụ:

~~~bash
jcmd 12345 VM.native_memory summary
jcmd 12345 VM.native_memory baseline
jcmd 12345 VM.native_memory summary.diff
~~~

**12345 là PID minh họa**, lệnh phải chạy theo khả năng attach của JVM đích. NMT cũng không phải profiler mọi native malloc: tài liệu chính thức giới hạn ở memory nội bộ JVM/HotSpot, không bao phủ hoàn toàn native allocations của thư viện bên thứ ba hoặc mọi thư viện JDK.

Vì thế, khi **RSS tăng mà BufferPoolMXBean không đổi**, NMT, allocator metrics của thư viện, mappings và OS/container metrics là **bằng chứng bổ sung**, không phải lý do “bỏ qua” cảnh báo.

## 11. Bài toán A: direct buffer tăng trong một JVM chạy lâu

**Triệu chứng giả định:** ứng dụng xử lý network I/O; heap ổn định gần 500 MiB, nhưng container memory tăng. Dashboard cho thấy:

| Thời điểm | Direct count | Direct total capacity | Direct memory used | Heap used |
| --- | ---: | ---: | ---: | ---: |
| 10:00 | 800 | 150 MiB | 158 MiB | 500 MiB |
| 10:10 | 2.100 | 420 MiB | 435 MiB | 505 MiB |
| 10:20 | 4.500 | 860 MiB | 890 MiB | 498 MiB |

Dữ liệu **giả định**, chỉ để luyện phân tích. Mẫu gợi ý **nhóm direct buffers đang tăng cả count, capacity và memory used**, trong khi heap gần ổn định. Điều đó củng cố giả thuyết có **direct buffer retention hoặc workload đang tăng số buffer sống**, nhưng **không tự chứng minh leak**.

Quy trình:

1. Kiểm tra **request concurrency, load, connection pool, queue depth, message sizes** có tăng tương ứng không. Nếu load tăng gấp ba, số direct buffer lớn hơn có thể là thiết kế pool bình thường.
2. Tách **warmup** khỏi steady-state, xác định các mốc lúc traffic trở về baseline. Nếu count/capacity vẫn tăng qua nhiều chu kỳ ổn định, cần điều tra mạnh hơn.
3. Xem **collector/reclaim behavior** và lifetime của ByteBuffer wrappers; không yêu cầu **System.gc()** như phương pháp sửa leak mặc định.
4. Kiểm tra **Netty/JNI/native allocator metrics** nếu thư viện có bộ đệm riêng; không giả định tất cả được BufferPoolMXBean thống kê.
5. Đối chiếu **RSS/cgroup memory**, file mappings, NMT (nếu bật), phiên bản Java, giới hạn **MaxDirectMemorySize** và OOM traces.
6. Chỉ sau khi có bằng chứng hãy chọn phương án: đóng resource đúng vòng đời, giới hạn pooling, thay ownership/release logic, điều chỉnh concurrency hoặc sửa code.

**Phân biệt hai trạng thái:** pool count có thể giữ cao vì **buffer pool được thiết kế giữ lại bộ đệm để tái sử dụng**, trong khi memory plateau; đó không nhất thiết là leak. Ngược lại, **giới hạn MaxDirectMemorySize** có thể gây lỗi cấp phát trước khi process chạm container limit. Cần xem loại lỗi cụ thể.

## 12. Bài toán B: lớp được nạp tăng sau mỗi lần redeploy trong cùng JVM

**Triệu chứng giả định:** server ứng dụng/plugin framework cho phép unload/reload module mà **không restart JVM**. Sau mỗi 10 phút:

| Mốc | loaded-now | total-loaded | unloaded | Metaspace used |
| --- | ---: | ---: | ---: | ---: |
| A | 9.000 | 12.000 | 3.000 | 180 MiB |
| B | 10.500 | 14.000 | 3.500 | 225 MiB |
| C | 12.200 | 16.200 | 4.000 | 275 MiB |

Các con số **giả định**. Mặc dù **unloaded** vẫn tăng, **loaded-now** và **Metaspace** tiếp tục đi lên. Điều này **gợi ý** số lớp/classloader sống tăng qua các chu kỳ, nhưng cũng có thể do module mới hoặc caches đúng thiết kế.

Cần kiểm tra:

- Mỗi reload tạo bao nhiêu **ClassLoader instance**, bao nhiêu class và có đóng loader đúng lifecycle không?
- **Thread context class loader**, threads trong plugin, static registries, shutdown hooks, ThreadLocal, scheduled tasks, logger handlers hoặc external registries có giữ tham chiếu tới loader cũ không?
- **GC/unloading** đã xảy ra chưa, collector có điều kiện unload các lớp không, và có thực sự cần kỳ vọng số loaded-now giảm ngay sau reload?
- **VM.classloader_stats**, Metaspace metrics, heap dump/classloader graph/JFR khi có quyền và mức tác động phù hợp cho thấy đối tượng nào còn giữ loader?

**Không kết luận từ total-loaded tăng.** Counter này **phải tăng** khi JVM load lớp mới; ngay cả một JVM hoạt động đúng có thể có total-loaded tăng vô hạn theo thời gian nếu liên tục tạo lớp rồi unload. Dấu hiệu đáng quan tâm hơn là **retained current count và Metaspace sau nhiều chu kỳ tương đương**, với workload/GC được kiểm soát.

## 13. Bài toán C: mapped capacity lớn nhưng RSS không tăng tương ứng

Một ứng dụng dùng **FileChannel.map** với các file lớn có thể có **mapped.totalCapacity = 8 GiB**, còn RSS thấp hơn nhiều. Không lập tức tạo incident “8 GiB RAM bị giữ”.

Phân tích đúng:

1. **Mapped capacity** chủ yếu phản ánh kích thước logical mappings, không phải resident pages.
2. MemoryUsed của pool là **estimate**, vẫn không cung cấp bản đồ từng page hay số byte file thực nằm trong RAM.
3. **RSS** ghi nhận trang memory có mặt ở physical memory theo OS tại thời điểm đo; **shared/file-backed pages** có phương pháp tính riêng, phụ thuộc OS và công cụ.
4. Nếu ứng dụng đọc liên tục, page cache có thể tăng và tác động cgroup; cũng không có nghĩa mapped buffer count bằng số file descriptor.
5. Khi mapped count/capacity không giảm sau khi đóng channel, cần nhớ **mapping sống đến khi mapped buffer bị thu gom**; phải kiểm tra tham chiếu và GC/lifecycle, không chỉ file handle.

Nếu mục tiêu là xác định file mapping cụ thể, cần OS process mappings/procfs và application metadata thích hợp. **BufferPoolMXBean không chứa danh sách từng path hoặc ByteBuffer instance**.

## 14. Triển khai theo dõi trên production

### 14.1. Metric names và nhãn gợi ý

Thiết kế một metrics exporter đọc MXBean có thể cung cấp:

~~~text
jvm_buffer_pool_count{pool="direct"}
jvm_buffer_pool_capacity_bytes{pool="direct"}
jvm_buffer_pool_used_bytes{pool="direct"}

jvm_buffer_pool_count{pool="mapped"}
jvm_buffer_pool_capacity_bytes{pool="mapped"}
jvm_buffer_pool_used_bytes{pool="mapped"}

jvm_classes_loaded_current
jvm_classes_loaded_total
jvm_classes_unloaded_total
~~~

**Đây là tên metric minh họa do bài học đề xuất**, không bảo đảm là tên chính xác của Micrometer/Prometheus/JMX exporter cụ thể. Khi dùng exporter thật, kiểm tra naming conventions, version, unit và giá trị unsupported.

- **Buffer pool** cần label **pool** từ **getName()** thay vì hardcode danh sách.
- **Class counters** là process-wide, gắn **instance/JVM identity**; nếu dùng Prometheus, tính rate per-process và xử lý resets.
- Không đặt **class name** hoặc **buffer instance** thành label; MXBean này không cung cấp chúng và high cardinality gây tốn tài nguyên monitoring.
- Khi pool **getMemoryUsed = -1**, cân nhắc **không xuất series used**, hoặc báo trạng thái unavailable theo convention. Không biểu diễn -1 thành giá trị memory thực.
- Dùng **bytes** nhất quán, không gắn suffix _mb nếu đang xuất byte.

### 14.2. Nên cảnh báo ở ngưỡng nào?

Không có ngưỡng **direct count**, **mapped capacity** hay **loaded-now** phù hợp mọi ứng dụng. Cảnh báo nên kết hợp:

- Dạng tăng bền vững qua nhiều cửa sổ tương đương, không chỉ một spike.
- Sức chứa memory thực của container/host và headroom OS.
- **Load, concurrency, throughput**, GC mode, pool warmup và retention policy của framework.
- Các dấu hiệu đi kèm: **OutOfMemoryError direct buffer memory**, Metaspace OOM, RSS increase, classloader count growth.
- Kế hoạch scale/deploy và mức chấp nhận rủi ro.

Nếu target JVM chỉ chạy vài phút rồi restart, bộ đếm total-loaded có thể tăng nhanh ở mỗi lần khởi động; metric phải **reset đúng và tách theo process lifecycle**. Đừng cộng toàn bộ số loaded-now của replicas rồi coi đó là memory hay lớp duy nhất của hệ thống.

### 14.3. Giới hạn khi lấy mẫu qua JMX từ xa

JMX remote có serialization/network cost và bảo mật cần kiểm soát. Nếu một collector poll hàng nghìn JVM với interval cực ngắn, bản thân việc polling có thể tạo tải. Bắt đầu bằng chu kỳ hợp lý theo sự cố cần phát hiện (ví dụ mỗi **5–30 giây** tùy tải), rồi đánh giá chi phí và mức mất spike.

Không cần kích hoạt **verbose class logging** hoặc tạo heap dump mỗi lần scrape. Getter MXBean hữu ích như nền giám sát nhẹ, còn tracing/profiling/heap dump chỉ nên bật khi có giả thuyết và chuẩn bị tác động.

## 15. Những lỗi thường gặp và cách sửa cách nghĩ

1. **“Pool direct.memoryUsed là tổng native memory.”** Không; nó là số liệu của pool do JVM công bố.
2. **“Pool mapped.capacity 8 GiB tức 8 GiB RAM resident.”** Không; logical mapping khác resident pages.
3. **“Buffer count là số lần allocate kể từ startup.”** Không; nó là ước lượng **số buffer trong pool** tại snapshot.
4. **“used phải luôn bằng totalCapacity.”** Không; alignment/allocator có thể tạo khác biệt.
5. **“MemoryUsed=-1 nghĩa là pool đang âm bộ nhớ hoặc chưa dùng gì.”** Không; nó nghĩa là ước lượng không sẵn có.
6. **“JVM luôn có đúng hai pool direct, mapped.”** Không; liệt kê MBeans thực tế và xét implementation.
7. **“Heap usage ổn định nghĩa là process memory ổn định.”** Không; direct, native, metaspace và OS còn nằm ngoài phạm vi heap.
8. **“Class total-loaded tăng nên có classloader leak.”** Không; đó là counter tăng theo mọi lần nạp.
9. **“Loaded-now tăng nghĩa là Metaspace tăng chính xác cùng tỷ lệ.”** Không; size mỗi class và VM metadata khác nhau.
10. **“Unloaded không tăng trong một phút nghĩa là GC hỏng.”** Không; unload có điều kiện và timing.
11. **“getLoadedClassCount == total-loaded - unloaded ở mọi sample.”** Không nên assert snapshot không nguyên tử, nhất là khi có class loading đồng thời.
12. **“setVerbose(true) chỉ là đọc metric.”** Sai; nó thay đổi logging toàn JVM và có overhead.
13. **“JMX ObjectName direct chắc chắn hiện trên mọi JVM.”** Không; kiểm tra getPlatformMXBeans/getObjectName.
14. **“Native Memory Tracking tự có và theo dõi mọi JNI/native malloc.”** Không; NMT cần bật từ startup và có phạm vi riêng.
15. **“Có thể so counter trước restart với sau restart như cùng một chuỗi.”** Sai; counters reset theo process lifecycle.
16. **“Direct buffer được giải phóng ngay khi close một FileChannel.”** Không; direct buffer/mapping có vòng đời riêng.
17. **“Càng scrape thường xuyên càng chứng minh leak tốt.”** Không; số mẫu nhiều nhưng lệch giai đoạn hoặc thiếu metadata vẫn sai.
18. **“Cần tạo heap dump ngay khi thấy pool direct tăng.”** Chưa; nên kiểm tra load, lifecycle, metrics và mức tác động trước.

## 16. Checklist chẩn đoán bằng MXBeans

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Đang đo đúng **JVM process** chưa? | PID, JVM start time, container/Pod, JDK vendor và version. |
| Đọc được đúng các MXBean không? | Danh sách BufferPoolMXBean và singleton ClassLoadingMXBean, không đoán ObjectName. |
| Metric mang đơn vị gì? | Count / byte / cumulative count / gauge. |
| Có giá trị unsupported không? | Kiểm tra memoryUsed = -1, không nội suy là 0. |
| Có nhiều mẫu đủ theo thời gian không? | timestamp, sampling interval, startup vs steady-state. |
| Counter có reset do restart không? | Process identity, uptime, deploy events. |
| Direct pool tăng có tương ứng workload không? | request rate, concurrency, buffer pool design, load tests. |
| Mapped capacity có phải memory resident không? | Đối chiếu OS mappings/RSS/page cache, không cộng trực tiếp. |
| Class-loaded hiện tại và Metaspace cùng tăng không? | ClassLoadingMXBean, MemoryPoolMXBean, GC/classloader evidence. |
| Có cơ sở để làm heap dump/NMT/JFR không? | Giả thuyết cụ thể, quyền, overhead, dung lượng và phương án khôi phục. |
| Kết luận đã phân biệt quan sát với giả thuyết chưa? | Có bằng chứng đối chiếu, giải thích cạnh tranh và mức chắc chắn. |

## 17. Tự kiểm tra và bài tập

**Câu 1.** Direct pool có **count=4.000**, **totalCapacity=300 MiB**, **memoryUsed=310 MiB**. Đây có phải lỗi số liệu không?

**Đáp án:** không nhất thiết. **memoryUsed** là estimate memory mà JVM dùng cho pool; có thể khác capacity do căn chỉnh, allocator và implementation. Ghi rõ đơn vị và đối chiếu xu hướng.

**Câu 2.** Tổng class đã nạp tăng từ **100.000 lên 105.000** sau một ngày, nhưng loaded-now gần 15.000 và Metaspace không đổi nhiều. Có kết luận classloader leak?

**Đáp án:** chưa. Tổng loaded là **counter tích lũy**, tăng khi có lớp mới; sự ổn định của loaded-now/Metaspace sau chu kỳ GC có thể phù hợp hoạt động bình thường. Cần kiểm tra classloader lifecycle và unload rate nếu có vấn đề.

**Câu 3.** Mapped pool báo capacity **12 GiB** nhưng RSS process khoảng **2 GiB**. Số nào sai?

**Đáp án:** có thể không số nào sai. Mapped capacity đo logical mapping, RSS đo resident memory; hai đại lượng không thể so trực tiếp.

**Câu 4.** MBean không có tên **direct**, nhưng có một pool khác do VM công bố. Có nên hardcode lỗi fatal?

**Đáp án:** không. API cho phép JVM có một hoặc nhiều pool với tên do implementation cung cấp. Chỉ đặt yêu cầu cụ thể khi biết rõ VM và cấu hình cần theo dõi.

**Câu 5.** **memoryUsed = -1** nên xuất **-1** lên dashboard bytes hay không?

**Đáp án:** không nên coi -1 là memory thực; biểu diễn unavailable/absent theo convention. Nếu cần cảnh báo, tách tình trạng thiếu số liệu khỏi ngưỡng memory.

**Câu 6.** Sau khi hạ load, direct count vẫn cao nhưng ổn định; có nhất thiết leak?

**Đáp án:** chưa. Buffer pool/framework có thể giữ lại tài nguyên để tái sử dụng. So plateau, chính sách pool, workload và memory headroom trước khi gọi là retention bất thường.

**Câu 7.** ClassLoadingMXBean.isVerbose() trả false. Muốn xem class load có nên tự setVerbose(true) trong endpoint health?

**Đáp án:** không. Đó là thay đổi **toàn JVM**, có thể tạo logging overhead. Hãy dùng công cụ logging/diagnostics có thời hạn, quyền và rollback phù hợp.

**Câu 8.** Vì sao **RSS tăng, heap ổn định, direct pool ổn định** vẫn có thể do native-memory issue?

**Đáp án:** vì BufferPoolMXBean không bao phủ mọi native allocation. Cần kiểm tra Metaspace, threads, code cache, OS mappings, NMT được bật từ đầu và allocator của thư viện/native code.

**Câu 9.** JMX collector lấy mẫu lúc 10:00 và 10:01 ở hai JVM khác nhau cùng service; có thể dùng hiệu số total-loaded để tính rate?

**Đáp án:** không. Counter là **per process**, không được trừ hai process/instance khác nhau. Phải giữ nhãn process identity và tính rate trên một chuỗi liên tục.

**Câu 10.** Dùng lệnh **jcmd PID GC.class_histogram** mỗi giây sẽ có lợi hơn MXBean không?

**Đáp án:** không phù hợp làm collector nền. Histogram có thể gây tác động cao; đọc MXBean định kỳ, chỉ lấy histogram/dump khi cần điều tra sâu và có chuẩn bị.

## Tài liệu tham khảo chính thức

- [Java SE 21 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): các chỉ số pool, đơn vị, độ chính xác và giá trị -1 của memoryUsed.
- [Java SE 21 — ClassLoadingMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html): các counter class loading và verbose mode.
- [Java SE 21 — ManagementFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html): platform MXBeans, MBeanServer và ObjectName.
- [Java SE 21 — ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): direct buffer, allocateDirect và đặc tính native I/O.
- [Java SE 21 — MappedByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/MappedByteBuffer.html): vòng đời mapping, page/file behavior.
- [Java SE 21 — FileChannel.map](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html#map(java.nio.channels.FileChannel.MapMode,long,long)): mapping và điều kiện lifetime.
- [JDK 21 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html): phạm vi, giới hạn và cách bật từ startup.
- [JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): các diagnostic commands, impact và điều kiện attach.
- [JDK 21 — java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): các tùy chọn runtime như MaxDirectMemorySize, NMT và class loading logs.

**Kết luận sử dụng được ngay:** đọc **BufferPoolMXBean** để theo dõi **các buffer pool được JVM công bố**, đọc **ClassLoadingMXBean** để theo dõi **tình trạng và nhịp nạp/unload lớp**, rồi đặt hai nhóm số liệu vào cùng timeline với **heap, Metaspace, RSS/container memory, GC và workload**. Chỉ đưa ra kết luận về leak khi đã loại trừ tính chất counter tích lũy, pooling bình thường, delay của GC và khác biệt phạm vi đo.
