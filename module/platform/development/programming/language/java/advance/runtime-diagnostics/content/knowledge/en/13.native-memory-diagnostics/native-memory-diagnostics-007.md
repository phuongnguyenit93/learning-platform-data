# 13.7 Đối chiếu NMT với BufferPoolMXBean, số thread và số liệu hệ điều hành

## Mục tiêu

Khi tiến trình Java tăng RSS, vượt giới hạn bộ nhớ container hoặc bị hệ điều hành kết thúc dù **Java heap used** không cao, cần kết hợp nhiều nguồn đo. Bài này hướng dẫn:

1. Đọc **Native Memory Tracking (NMT)**: reserved, committed, các nhóm Java Heap, Thread, Class, Code, GC, Internal/Other; hiểu giới hạn phạm vi của NMT.
2. Lấy số liệu từ **BufferPoolMXBean** cho direct/mapped buffers và phân biệt count, totalCapacity, memoryUsed.
3. Đối chiếu **số platform thread trong JVM**, thread native của tiến trình và phần bộ nhớ mà NMT gán cho Thread.
4. Đọc **RSS, VSZ/VmSize, PSS, anonymous/file-backed memory**, số thread ở Linux và giới hạn cgroup/container.
5. Thiết kế các phép đo **cùng thời điểm, cùng tải, cùng đơn vị** để thu hẹp nguyên nhân, không tính tổng sai hay gắn nhãn “native leak” chỉ từ một snapshot.

**Nguyên tắc xuyên suốt:** NMT, BufferPoolMXBean, ThreadMXBean và số liệu OS là **những góc nhìn có phạm vi và ngữ nghĩa khác nhau**. Chúng giúp kiểm chứng chéo các giả thuyết; thường không thể cộng/trừ chúng thành một phép cân đối chính xác từng byte.

## 1. Bốn lớp quan sát bộ nhớ của cùng một tiến trình

Giả sử một service có **-Xmx512m** nhưng dashboard cho thấy RSS 1,2 GiB. Điều này không tự động chứng minh có leak: tiến trình Java còn sử dụng code cache, metadata, native stacks, GC metadata, direct buffers, JNI/native libraries, memory mappings và nhiều vùng khác. Ngay cả riêng Java heap, **used**, **committed**, **reserved** và **resident** cũng khác nhau.

| Nguồn | Quan sát chủ yếu | Câu hỏi nên hỏi | Điều không thể kết luận trực tiếp |
| --- | --- | --- | --- |
| **JMX MemoryMXBean** | Heap/non-heap usage mà JVM báo | Heap đang dùng/đã commit bao nhiêu? | Tổng resident memory của tiến trình |
| **NMT — jcmd VM.native_memory** | Bộ nhớ mà HotSpot theo dõi, chia theo subsystem và reserved/committed | Phần JVM quản lý đang tăng ở nhóm nào? | Toàn bộ allocation của mọi JNI/library/native code |
| **BufferPoolMXBean** | Số lượng, tổng capacity và memory used ước lượng của các buffer pool JVM expose | Direct/mapped buffers đang tăng không? | Tổng off-heap memory hoặc toàn bộ mmap của tiến trình |
| **ThreadMXBean + OS threads** | Platform threads JVM và native threads tiến trình | Có thread tăng bất thường kéo theo stacks? | Số lượng virtual threads; chính xác từng byte stack resident |
| **OS/process/container metrics** | Pages resident, virtual mappings, shared/private, cgroup charge | Tiến trình/container đang gây áp lực RAM thực sự không? | Chính xác object/class/call site nào giữ memory |

Một tình huống có thể đồng thời xảy ra: NMT **Java Heap committed** = 512 MiB, **heap used** = 240 MiB, BufferPoolMXBean **direct memoryUsed** = 128 MiB, RSS = 820 MiB. Cả bốn giá trị đều có thể hợp lý. Không có quy tắc yêu cầu RSS bằng tổng của các giá trị kia.

**Cách đặt câu hỏi đúng:** “Trong khoảng RSS tăng 300 MiB, NMT nhóm nào tăng, buffer pool nào tăng, thread count nào tăng, và OS cho thấy các trang tăng nằm ở anonymous hay file-backed mappings?”

## 2. Native Memory Tracking (NMT): theo dõi phần nào?

**NMT** là tính năng của **HotSpot JVM**, bật khi khởi động:

~~~bash
java -XX:NativeMemoryTracking=summary -Xmx512m -jar app.jar
~~~

Hoặc chọn **-XX:NativeMemoryTracking=detail** nếu cần phân tích sâu allocation sites. Mặc định NMT tắt. Khi tiến trình đã khởi động mà chưa bật NMT, không thể bật NMT giữa chừng chỉ bằng jcmd; phải khởi động lại với option phù hợp. Có thể dùng **jcmd VM.native_memory shutdown** để dừng theo dõi nhưng không thể dùng nó để khởi động lại NMT.

### 2.1. Summary và detail

- **summary**: tổng hợp memory theo các nhóm VM như Java Heap, Class, Thread, Code, GC, Compiler, Internal, Other, Symbol, Native Memory Tracking. Tên nhóm và nội dung có thể thay đổi giữa các bản JDK/HotSpot.
- **detail**: thêm call sites và virtual memory map cho các allocation do NMT theo dõi. Đây không phải profile Java allocation theo từng object, cũng không phải call stack ứng dụng cho mọi malloc của thư viện native.
- NMT có overhead CPU và memory; tài liệu Oracle mô tả chi phí hiệu năng có thể vào khoảng **5–10%** tùy workload/cấu hình. Bật có chủ đích rồi đo chi phí thực tế.

### 2.2. Reserved và committed: không đọc thành RSS

Trong đầu ra NMT, ví dụ **minh họa số liệu, không phải kết quả bắt buộc của JVM**:

~~~text
Native Memory Tracking:
Total: reserved=6144MB, committed=850MB

- Java Heap (reserved=512MB, committed=512MB)
- Class     (reserved=1050MB, committed=75MB)
- Thread    (reserved=420MB, committed=35MB)
- Code      (reserved=250MB, committed=45MB)
...
~~~

- **reserved**: dải **không gian địa chỉ ảo** đã đặt trước cho một mục đích. Có thể rất lớn mà chưa cần lượng RAM vật lý tương ứng. Ví dụ vùng compressed class space hoặc heap reserve.
- **committed**: phần bộ nhớ mà HotSpot đã commit hoặc malloc trong phạm vi NMT. Committed không có nghĩa toàn bộ byte đó đang là trang **resident** tại chính thời điểm OS đo; paging, cấp phát lười và cơ chế OS ảnh hưởng số trang thực đang ở RAM.
- **Java Heap reserved** có thể tương ứng cấu hình heap tối đa; **Java Heap committed** là dung lượng được JVM commit; **Java heap used** là lượng object/heap đang sử dụng theo MemoryMXBean/GC. Không dùng một số để thay thế số kia.
- **NMT Total** đã gồm nhóm **Java Heap** và các nhóm khác mà NMT theo dõi. Đừng lấy NMT Total cộng thêm NMT Java Heap lần nữa.

NMT được thiết kế để theo dõi **bộ nhớ do HotSpot/JVM theo dõi**, không phải một công cụ tổng kiểm toán mọi bộ nhớ của process. Tài liệu Oracle lưu ý NMT không bao phủ đầy đủ allocations của third-party native code và JDK class libraries; các phần của CDS và một số cấp phát ngoài subsystem theo dõi cũng có giới hạn. Vì vậy có thể xảy ra **RSS tăng trong khi NMT gần như không đổi**, nhưng đó mới là dấu hiệu phải điều tra thêm, chưa phải chứng cứ chắc chắn của JNI leak.

### 2.3. NMT baseline và diff: xem thay đổi thay vì một ảnh chụp

~~~bash
# Sau khi JVM đã warm up và tải đã tương đối ổn định:
jcmd <PID> VM.native_memory summary scale=MB
jcmd <PID> VM.native_memory baseline

# Sau một khoảng tải đại diện:
jcmd <PID> VM.native_memory summary.diff scale=MB

# Chỉ áp dụng khi JVM đã bật NMT detail:
jcmd <PID> VM.native_memory detail.diff scale=MB
~~~

Trong báo cáo diff, phần **+NMB/-NMB** mô tả biến động so với baseline của chính **quy trình NMT**, không phải biến động RSS hoặc tổng số byte object leak. Ví dụ:

~~~text
- Thread (reserved=... +80MB, committed=... +4MB)
- Class  (reserved=... +0MB,  committed=... +32MB)
~~~

Đây là số minh họa. Thread reserved tăng lớn trong khi committed tăng ít gợi ý có thêm stack reservations; Class committed tăng có thể do load thêm class hoặc class metadata. Cần xem class-load/thread count, workload và xu hướng trước khi nói có leak.

**Quan trọng:** NMT baseline là một mốc nội bộ; máy chủ, GC, compiler, cache, class loading có thể còn warm-up sau baseline. So sánh các mốc có tải gần tương đương và ưu tiên **tăng kéo dài** thay vì tăng một lần trong giai đoạn khởi động.

## 3. BufferPoolMXBean đo gì?

API **java.lang.management.BufferPoolMXBean** cho biết các buffer pool mà JVM expose qua JMX. Với HotSpot, thường thấy **direct**, **mapped** và có thể có pool riêng cho non-volatile mapped buffers tùy JDK/cấu hình. Đừng hard-code rằng mọi JVM luôn có đúng hai hay ba pool.

Ba phép đo chính:

| Phương thức | Đơn vị/ý nghĩa | Lưu ý diễn giải |
| --- | --- | --- |
| **getCount()** | Ước lượng số buffer trong pool | Không phải số byte; có thể thay đổi theo cleaner/lifecycle và cấu trúc buffer |
| **getTotalCapacity()** | Ước lượng tổng capacity của các buffer, **bytes** | Capacity logic, không nhất thiết là memory allocation thực tế |
| **getMemoryUsed()** | Ước lượng byte memory JVM đang dùng cho pool | Có thể khác totalCapacity do alignment/allocator; **-1** nếu JVM không có ước lượng |

Ví dụ minh họa:

~~~text
name=direct count=200 totalCapacity=134217728 memoryUsed=134217728
name=mapped count=12  totalCapacity=268435456 memoryUsed=268435456
~~~

Số liệu không có tính bắt buộc. Nếu direct **memoryUsed** tăng cùng lúc số direct buffer tăng, hãy điều tra vị trí tạo/sở hữu/lifetime của direct buffers. Nếu mapped pool tăng, hãy kiểm tra file mappings và vòng đời mapping; file-backed pages có thể hoặc không resident trong RAM tại cùng thời điểm.

**BufferPoolMXBean không đo “tất cả off-heap”.** Các memory allocation tự quản lý bởi native library, malloc qua JNI, native arenas, thread stacks, compiler buffers và nhiều vùng khác có thể nằm ngoài các pool này. Direct buffer cũng có thể là vùng do thư viện khác cấp phát hoặc vùng shared theo cách không thể suy từ count; con số pool do JVM báo cần được diễn giải theo triển khai.

### 3.1. Vì sao BufferPoolMXBean và NMT không cộng được với nhau?

Một phần backing memory của direct buffers có thể đồng thời xuất hiện trong **NMT ở nhóm VM thích hợp** và trong **BufferPoolMXBean**. Hai số có thể **đếm cùng memory** ở hai góc nhìn. Ngược lại, một loại buffer hoặc thư viện có thể nằm ngoài phạm vi đo của một trong hai nguồn.

Không sử dụng:

~~~text
RSS = NMT Total committed + BufferPoolMXBean direct memoryUsed
RSS = Java heap used + direct capacity + tổng stackSize của thread
native leak = RSS - NMT Total committed
~~~

Đây không phải các đẳng thức accounting hợp lệ. Chúng vừa có thể **đếm trùng** vừa bỏ sót thành phần, và trộn khái niệm committed/resident/capacity.

### 3.2. Một số trường hợp cần chú ý

- **DirectByteBuffer:** ByteBuffer.allocateDirect thường dùng backing memory ngoài Java heap; Java wrapper vẫn là Java object. Khi wrapper không còn reachable, bộ nhớ backing có thể được giải phóng theo cơ chế Cleaner/GC, **không bảo đảm ngay tại lúc bỏ reference**.
- **MappedByteBuffer:** giá trị pool đo mapped buffers theo JVM; không tương đương số trang file đang resident. Mapped capacity lớn có thể đi cùng RSS thấp nếu phần lớn trang chưa được truy cập.
- **Slice/duplicate views:** các view không nhất thiết tạo một backing allocation mới. Đừng lấy số lượng ByteBuffer objects trên heap nhân với capacity để suy physical memory.
- **getMemoryUsed() = -1:** phải hiển thị “unknown/unavailable”, không tự ép thành 0 hoặc biến đổi thành số dương.
- **-XX:MaxDirectMemorySize:** có thể giới hạn một nhóm direct buffer allocations theo HotSpot/JDK, nhưng **không phải giới hạn toàn bộ native memory của tiến trình**. Không dùng nó thay cho container memory limit.

## 4. Số thread: Java, JVM native và OS đang đếm khác gì?

### 4.1. ThreadMXBean đếm platform threads

Trong **Java 21**, **ThreadMXBean.getThreadCount()** báo số **live platform threads**, gồm daemon và non-daemon. **Không tính virtual threads**. Các phương thức getPeakThreadCount() và getTotalStartedThreadCount() cũng nói về platform threads.

Một **platform thread** thường gắn với một OS thread; trong khi **virtual thread** được JVM lên lịch trên các carrier/platform threads, không cần một OS thread riêng cho mỗi virtual thread. Vì vậy số virtual threads lớn không suy ra số native OS thread tương ứng. Virtual threads cũng có bộ nhớ stack/state, nhưng chi phí/mapping khác platform threads.

### 4.2. NMT Thread không phải phép nhân số thread với -Xss

NMT nhóm **Thread** ghi nhận những thành phần JVM theo dõi cho threads, bao gồm thread structures, stack reservations/commit và các cấu trúc liên quan. Với HotSpot, **-Xss** liên quan cấu hình kích thước stack của Java platform threads, nhưng:

- Thread stack **reserved** không đồng nghĩa tất cả đã **committed**.
- Stack **committed** không đồng nghĩa toàn bộ đang resident ở RAM.
- JVM có nhiều native/internal threads, thread stack có guard pages, điều chỉnh alignment, platform-specific defaults.
- Native threads do thư viện ngoài JVM tạo có thể bị OS đếm nhưng không xuất hiện đầy đủ trong ThreadMXBean/NMT.
- Một chương trình có nhiều virtual threads không được ước lượng chi phí bằng **virtual-thread-count × -Xss**.

Công thức **threads × -Xss** có ích để đặt giả thuyết về *quy mô đặt trước địa chỉ stack* cho platform threads, nhưng không phải cách đo RAM thực tế.

### 4.3. Đối chiếu ba nguồn đếm

| Nguồn | Ví dụ thông số | Diễn giải |
| --- | --- | --- |
| Java **ThreadMXBean** | getThreadCount() | Live **platform threads** được JVM quản lý trong Java 21 |
| NMT nhóm **Thread** | threads #...; reserved/committed | Thread resources được HotSpot theo dõi |
| Linux **/proc/PID/status** | Threads | Số kernel tasks/native threads thuộc tiến trình tại thời điểm đọc |

Số OS Threads có thể lớn hơn ThreadMXBean do GC/compiler/service/internal/native-library threads. Các số được thu ở thời điểm khác nhau cũng có thể lệch do thread ngắn hạn. **Không suy ra leak chỉ vì ba số khác nhau.** Tìm **xu hướng** thread tăng và khớp nó với NMT Thread, OS native thread count, thread names/stacks và kiểu executor.

## 5. Số liệu hệ điều hành: RSS, VSZ, PSS và container

Để biết tiến trình có đang sử dụng nhiều bộ nhớ vật lý hoặc vượt giới hạn runtime không, phải xem số liệu OS. Ví dụ bên dưới dành cho **Linux**, dùng PID thực của JVM.

### 5.1. /proc/PID/status

~~~bash
PID=12345
grep -E '^(Name|VmSize|VmRSS|RssAnon|RssFile|RssShmem|VmSwap|Threads):' /proc/"$PID"/status
ps -o pid,rss,vsz,nlwp,cmd -p "$PID"
~~~

- **VmSize / VSZ:** tổng không gian địa chỉ ảo của process; có thể lớn do heap reserve, class space reserve, thread stack reserve và mappings. VSZ lớn **không đồng nghĩa RAM đã dùng lớn**.
- **VmRSS / RSS:** số trang của process đang resident theo cách OS đếm. RSS gồm cả anonymous, file-backed và shared mappings; có thể có trang được chia sẻ với process khác.
- **RssAnon:** phần resident anonymous; thường hữu ích để xem heap/native malloc/stacks đã được chạm tới, nhưng **không tách riêng Java heap khỏi mọi native allocation**.
- **RssFile:** resident file-backed mappings, gồm shared libraries, file mappings; có thể tăng khi đọc file mà không phải heap leak.
- **RssShmem:** resident shared-memory mapping.
- **VmSwap:** số trang phù hợp đã swap theo định nghĩa Linux; không phải “phần heap bị swap” độc lập.
- **Threads / nlwp:** native OS thread count tại thời điểm đo.

**Lưu ý chất lượng đo:** tài liệu Linux cho biết số VmRSS trong **/proc/PID/status** có thể không chính xác hoàn toàn do tối ưu accounting. Khi cần phân tích sâu hoặc chứng minh chênh lệch nhỏ, dùng **smaps/smaps_rollup** và xét chi phí đọc.

### 5.2. /proc/PID/smaps_rollup và PSS

~~~bash
grep -E '^(Rss|Pss|Pss_Anon|Pss_File|Private_Clean|Private_Dirty|Shared_Clean|Shared_Dirty|Swap):' \
  /proc/"$PID"/smaps_rollup
~~~

Các trường có sẵn phụ thuộc kernel. **RSS** ở đây là tổng resident mappings; **PSS (Proportional Set Size)** chia trang shared theo số bên cùng sử dụng, có ích để ước tính phần đóng góp của một process khi shared libraries/mapped files bị chia sẻ. **Private_Dirty/Private_Clean** giúp tách trang chỉ thuộc process; **Shared_*** phản ánh các trang chia sẻ.

PSS **không phải số native memory JVM**, và smaps_rollup **không gắn tên Java object/BufferPoolMXBean với từng OS page**. Muốn tìm mapping cụ thể, đọc **/proc/PID/smaps** hoặc **/proc/PID/maps** và công cụ profiling native. Quyền đọc một số file /proc có thể bị hạn chế trong container hoặc hệ thống production.

### 5.3. Container/cgroup: thêm một lớp accounting

Với **cgroup v2** thường thấy:

~~~bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.stat
~~~

Đường dẫn phụ thuộc cgroup mount và namespace; không mặc định đây là đúng cgroup cho PID nếu chạy từ host khác. **memory.current** ghi charge của **toàn cgroup**, có thể gồm các process trong cgroup và file cache theo quy tắc accounting; nó **không phải RSS riêng JVM**. **memory.max** là giới hạn cgroup nếu được đặt, có thể là chuỗi **max** khi không giới hạn theo trường này.

Một service có heap nhỏ vẫn có thể gặp **container OOM** do tổng heap, native, cache, memory được charge của các tiến trình khác và limits. Hãy xem OOM events, container metrics và quy tắc cgroup tương ứng trước khi chỉ tăng **-Xmx** hoặc giảm **-Xss**.

### 5.4. So sánh trên Windows và macOS

Nếu không chạy Linux, dùng công cụ OS tương ứng để đọc **working set/resident**, **private bytes/commit** và **thread count**, ví dụ Process Explorer/Performance Monitor trên Windows hoặc Activity Monitor/vmmap trên macOS. Tên và semantics không đồng nhất hoàn toàn với Linux RSS/PSS; khi so sánh giữa hệ điều hành, cần ghi rõ loại metric và source, tránh gán nhãn chung “RAM” cho các đại lượng khác nhau.

## 6. Ví dụ Java 17+ có thể chạy: đọc ba nhóm số liệu ngay trong process

Chương trình dưới đây đọc Java heap từ MemoryMXBean, các BufferPoolMXBean và platform-thread count. Nó giữ **4 direct ByteBuffer, mỗi buffer 1 MiB**, cho phép thu NMT và OS metrics trước/sau allocation trong **cùng một tiến trình**.

Tạo file **NativeMemoryCompare.java**:

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.lang.management.ThreadMXBean;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

public final class NativeMemoryCompare {
    private static final List<ByteBuffer> HELD = new ArrayList<>();
    private static final long MIB = 1024L * 1024L;

    private static String mib(long bytes) {
        if (bytes < 0) {
            return "n/a";
        }
        return String.format(Locale.ROOT, "%.2f MiB", bytes / (double) MIB);
    }

    private static void snapshot(String phase) {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        MemoryUsage heap = memory.getHeapMemoryUsage();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();

        System.out.println("SNAPSHOT: " + phase);
        System.out.println("  heap used=" + mib(heap.getUsed())
                + ", committed=" + mib(heap.getCommitted()));
        System.out.println("  platform threads=" + threads.getThreadCount());

        List<BufferPoolMXBean> pools = new ArrayList<>(
                ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class));
        pools.sort(Comparator.comparing(BufferPoolMXBean::getName));

        for (BufferPoolMXBean pool : pools) {
            System.out.println("  pool=" + pool.getName()
                    + ", count=" + pool.getCount()
                    + ", capacity=" + mib(pool.getTotalCapacity())
                    + ", memoryUsed=" + mib(pool.getMemoryUsed()));
        }
    }

    public static void main(String[] args) throws Exception {
        BufferedReader input = new BufferedReader(
                new InputStreamReader(System.in));

        System.out.println("PID: " + ProcessHandle.current().pid());
        snapshot("before allocation");

        System.out.println("PHASE 1 READY - collect NMT baseline, then press Enter");
        input.readLine();

        for (int i = 0; i < 4; i++) {
            HELD.add(ByteBuffer.allocateDirect(1024 * 1024));
        }
        System.out.println("PHASE 2 READY - allocated four 1 MiB direct buffers");
        snapshot("after allocation");

        System.out.println("Collect NMT diff and OS metrics, then press Enter");
        input.readLine();

        HELD.clear();
        System.out.println("PHASE 3 READY - cleared retained references");
        snapshot("after clear");

        System.out.println("Press Enter to exit");
        input.readLine();
    }
}
~~~

Biên dịch và chạy trong terminal tương tác, với **HotSpot/OpenJDK 17+**:

~~~bash
javac NativeMemoryCompare.java
java -Xmx128m -XX:NativeMemoryTracking=summary NativeMemoryCompare
~~~

Các dòng mốc **chắc chắn được chương trình in theo đúng thứ tự** (đan xen với PID, snapshots và các dòng pool có giá trị động):

~~~text
PHASE 1 READY - collect NMT baseline, then press Enter
PHASE 2 READY - allocated four 1 MiB direct buffers
PHASE 3 READY - cleared retained references
Press Enter to exit
~~~

**Không có output byte/threads cố định**: PID, các pool khả dụng, class loading, allocator, GC và hoạt động JVM thay đổi theo runtime. Bạn nên thấy dấu hiệu direct pool tăng sau bước allocate trong HotSpot điển hình; **không ép kết quả bằng chính xác 4 buffer/4 MiB** nếu JVM đã có buffer khác hoặc implementation có khác biệt.

**HELD.clear() không giải phóng native backing memory đồng bộ.** Nó chỉ bỏ các strong references từ List. Việc reclaim phụ thuộc vào việc wrapper còn reachable ở đâu khác, GC/Cleaner và quy tắc triển khai. Không dùng thời điểm clear() để tuyên bố RSS/memoryUsed phải giảm ngay.

### 6.1. Thu mẫu đồng bộ cho từng phase

Trong một terminal thứ hai, thay PID thật mà chương trình vừa in:

~~~bash
PID=12345

# Khi thấy PHASE 1 READY, ghi các số đang có rồi đặt NMT baseline:
date -Is
jcmd "$PID" VM.native_memory summary scale=MB
jcmd "$PID" VM.native_memory baseline
grep -E '^(VmSize|VmRSS|RssAnon|RssFile|Threads):' /proc/"$PID"/status
~~~

Nhấn Enter trong terminal Java để thực hiện allocation. Khi thấy **PHASE 2 READY**, lấy mẫu ngay:

~~~bash
date -Is
jcmd "$PID" VM.native_memory summary.diff scale=MB
grep -E '^(VmSize|VmRSS|RssAnon|RssFile|Threads):' /proc/"$PID"/status
grep -E '^(Rss|Pss|Private_Dirty|Private_Clean):' /proc/"$PID"/smaps_rollup
~~~

Nhấn Enter thêm lần nữa để **HELD.clear()**, thu mẫu lần 3 và ghi nhận liệu direct pool và OS RSS có đổi hay chưa. **Không cần cưỡng bức GC để tạo ra một kết quả đẹp**; mục tiêu là thấy sự khác nhau giữa reference lifecycle, NMT accounting và residency. Nếu làm thí nghiệm có GC để đối chiếu, phải ghi rõ **đã yêu cầu GC**, GC có thực sự xảy ra không và thời điểm lấy mẫu.

Để xem NMT allocation sites sâu hơn ở một lần chạy khác, đổi sang **-XX:NativeMemoryTracking=detail** ngay từ khi khởi động rồi dùng **jcmd PID VM.native_memory detail** hoặc **detail.diff**. Không thể đổi trực tiếp summary → detail cho JVM đang chạy.

## 7. Cách đọc một bộ số liệu chung

Lý tưởng mỗi mốc đo đều có:

| Nhóm | Trường tối thiểu | Ý nghĩa |
| --- | --- | --- |
| Thời điểm/điều kiện | Timestamp, PID, JDK, cgroup, traffic hoặc phase | Bảo đảm dữ liệu đủ điều kiện so sánh |
| Heap | Heap used/committed/max, GC activity | Kiểm tra heap có tăng kéo dài không |
| NMT | Total committed/reserved, Java Heap, Thread, Class, Code, GC, Other và diff | Xác định subsystem JVM nào đang thay đổi |
| Buffer pool | Mỗi pool: name, count, capacity, memoryUsed | Kiểm tra direct/mapped buffers có tăng không |
| Threads | Java platform thread count; OS native thread count; NMT Thread | Tìm gia tăng threads/stacks |
| OS | RSS, VSZ, anonymous/file-backed, PSS/private, swap khi có | Xem memory resident và mapped |
| Container | memory.current/max, OOM events, bộ nhớ cgroup | Kiểm tra vì sao workload bị giới hạn |

Để tránh false positive, nên quan sát **ít nhất hai mốc có điều kiện tải tương đương**, và nếu có thể **baseline sau warm-up**. Tần suất đo đủ dày để thấy xu hướng nhưng không quá dày đến mức jcmd/detail/smaps tạo thêm overhead đáng kể.

### 7.1. Những mô hình thường gặp

**Mô hình A — RSS và NMT Java Heap cùng tăng; heap used sau GC cũng tăng.** Điều tra **heap retention**: cache/collection/objects giữ lâu, class histogram, heap dump và Paths to GC Roots. NMT Java Heap committed không đủ chứng minh leak; phải xem live object set và vòng đời ứng dụng.

**Mô hình B — RSS và BufferPoolMXBean direct tăng; heap used tương đối ổn định.** Điều tra **direct buffers**: allocation hotspots, owner, pool, vòng đời release/Cleaner và giới hạn direct buffer. So với NMT categories chỉ để kiểm chứng; không giả định NMT Other = direct bytes trên mọi JDK.

**Mô hình C — NMT Thread reserved tăng, OS Threads và ThreadMXBean tăng.** Nghi **nở platform threads/pool**. Thu thread dump, xem thread names, thread states, executor queue và vòng đời. Reserved tăng nhiều chưa chắc RSS tăng tương xứng.

**Mô hình D — RSS tăng mạnh, NMT Total committed gần như đứng yên, direct/mapped pool và platform threads cũng ổn định.** Xem **/proc/PID/smaps**, anonymous vs file-backed, JNI/native libraries, malloc arenas, mapping, OS page residency và cgroup charge. Cũng cân nhắc các trang đã committed trước nhưng mới được chạm tới nên resident tăng. **Chưa thể khẳng định leak ngoài JVM** chỉ từ chênh lệch này.

**Mô hình E — VSZ tăng mạnh, RSS/PSS và committed ổn định.** Có thể đơn giản là thêm **address space reservations** (stack/class space/mappings), chưa thể khẳng định áp lực RAM vật lý tăng.

**Mô hình F — Container memory.current tăng nhưng process RSS không tăng tương ứng.** Xem **page cache và các process khác trong cùng cgroup**, kernel memory/cgroup stats; đừng gán toàn bộ memory.current cho một PID Java.

## 8. Bảng tình huống so sánh (số liệu giả định)

Hai mốc cách nhau 30 phút, tải tương đương và đã qua warm-up:

| Metric | T0 | T1 | Nhận định cần điều tra |
| --- | ---: | ---: | --- |
| Java heap used sau GC | 180 MiB | 183 MiB | Không cho thấy tăng retention heap đáng kể |
| NMT Total committed | 520 MiB | 525 MiB | Các nhóm VM được NMT theo dõi khá ổn định |
| BufferPoolMXBean direct memoryUsed | 32 MiB | 33 MiB | Direct buffer pool không tăng đáng kể |
| ThreadMXBean platform threads | 84 | 85 | Không có nở Java platform thread rõ rệt |
| Linux Threads | 112 | 113 | Native threads tương đối ổn định |
| Process RSS | 640 MiB | 980 MiB | Resident process tăng 340 MiB |
| RssAnon | 480 MiB | 815 MiB | Phần tăng chủ yếu anonymous |

**Không kết luận “native leak 335 MiB”.** Phần anonymous có thể gồm malloc/JNI allocations không được NMT tính, các vùng JVM committed từ trước giờ mới chạm tới, allocator giữ pages để tái sử dụng hoặc thành phần native khác. Bước kế tiếp là phân tích smaps, library/profiler native, quá trình tải, vòng đời vùng cấp phát và số liệu theo thời gian.

Đổi lại, nếu trong cùng giai đoạn BufferPoolMXBean direct memoryUsed cũng tăng ~300 MiB, cần ưu tiên điều tra vòng đời direct buffers; nhưng vẫn phải xác minh trước khi khẳng định một pool chính là nguyên nhân toàn bộ RSS delta.

## 9. Quy trình chẩn đoán thực tế khi RSS tăng hoặc container OOM

### Bước 1. Cố định ngữ cảnh quan sát

Ghi PID, container/cgroup thực tế, phiên bản JDK, GC đang dùng, -Xms/-Xmx, -Xss nếu có, direct memory limit nếu được cấu hình, traffic/request rate và thời điểm. Nếu có nhiều JVM, không dùng RSS của process A so với NMT của process B.

### Bước 2. Kiểm tra heap trước

Quan sát heap used **sau GC**, committed, GC log hoặc JFR nếu đã bật. Heap used sau GC tăng đều sẽ gợi ý retention; heap committed lớn nhưng used thấp có thể phản ánh chính sách giữ heap, chưa chứng minh leak.

### Bước 3. Đọc NMT theo nhóm và theo thời gian

NMT summary/diff để biết **HotSpot subsystems** nào tăng; detail khi cần call sites và có thể chấp nhận overhead. Phân biệt một lần class loading bình thường với tăng liên tục của Class metadata; phân biệt NMT Thread **reserved** và **committed**.

### Bước 4. Đối chiếu BufferPoolMXBean

Thu direct/mapped **count/capacity/memoryUsed** cùng thời điểm. Nếu tăng, xác định ai tạo và giữ buffers. Có thể cần JFR/heap dump để tìm Java wrappers và reference chains; nhớ rằng **heap dump không cho thấy toàn bộ native backing memory**.

### Bước 5. Đối chiếu thread count và stack

Dùng ThreadMXBean (platform threads), NMT Thread và Linux Threads/nlwp. Nếu đều tăng, xem thread dumps, pool sizing, blocked tasks, native library threads và shutdown lifecycle. Trên Java 21, rất nhiều virtual threads không trực tiếp tương đương rất nhiều OS threads.

### Bước 6. Xem các trang OS thực sự ở đâu

Kiểm tra RSS/PSS, RssAnon/RssFile/RssShmem, smaps/smaps_rollup, native mappings và cgroup usage. Chỉ trong bước này mới có căn cứ hơn để phân biệt anonymous pressure, file-backed mappings, third-party native allocations hay chênh lệch do residency.

### Bước 7. Thử giả thuyết nhỏ, đo lại

Ví dụ giảm tồn đọng queue, đóng/release buffer đúng lifecycle, sửa thread pool không giới hạn, giải quyết JNI allocation. Sau thay đổi, đo lại **cùng workload và khoảng thời gian**. Kết luận chỉ khi chuỗi bằng chứng phù hợp: nguyên nhân code/lifecycle, biến động NMT/JMX và OS sau sửa.

## 10. Những nhầm lẫn cần tránh

1. **“NMT Total chính là RAM của process.”** Sai: NMT theo dõi phạm vi HotSpot và biểu diễn reserved/committed; OS RSS/PSS có scope và ngữ nghĩa khác.
2. **“Native memory = NMT Total − Java Heap.”** Sai: ngoài phạm vi theo dõi còn native allocations của thư viện và các memory maps khác; NMT không phải phép kiểm kê toàn bộ off-heap.
3. **“RSS − heap used = off-heap leak.”** Sai: chênh lệch còn gồm heap committed-but-unused, code/class/GC, stacks, native allocations, file-backed/share và paging.
4. **“NMT committed + direct memoryUsed + stack size = RSS.”** Sai vì **đếm trùng** và trộn committed/reserved/capacity/resident.
5. **“MappedByteBuffer capacity lớn tương đương số RAM đang resident.”** Sai: mapping có thể lớn nhưng chỉ một phần trang nằm trong RSS.
6. **“BufferPoolMXBean memoryUsed bằng -1 nghĩa là không dùng bộ nhớ.”** Sai: đó là trường hợp estimate không khả dụng.
7. **“ThreadMXBean đếm cả virtual threads Java 21.”** Sai: API này chỉ hỗ trợ platform threads; native OS thread count lại có thêm JVM/native internal threads.
8. **“200 threads và -Xss1m chắc chắn đang tiêu thụ 200 MiB RAM vật lý.”** Sai: reservation, commitment và page residency khác nhau.
9. **“RSS tăng khi NMT không đổi là chắc chắn JNI leak.”** Sai: kiểm tra resident pages mới được chạm, file mappings, native allocator caching và phạm vi NMT.
10. **“VSZ rất cao là OOM sắp xảy ra.”** Sai: virtual reservations có thể lớn mà RSS/committed thấp; phải xem giới hạn address space và memory charge thực tế.
11. **“memory.current của container là RSS của Java PID.”** Sai: đó là usage/charge ở phạm vi cgroup, gồm tài nguyên khác tùy cấu hình.
12. **“Một lần snapshot đã đủ kết luận.”** Sai: cần trend, điều kiện tương đương và bằng chứng lifecycle.
13. **“NMT summary và detail là phép đo miễn phí.”** Sai: có overhead; detail phù hợp với giai đoạn điều tra có kiểm soát.
14. **“GC sẽ luôn trả ngay direct buffer native memory sau clear().”** Sai: giải phóng phụ thuộc reachability/Cleaner/GC và có thể có độ trễ; dùng close/release đúng API khi có quy định tài nguyên rõ ràng.

## 11. Bài tự kiểm tra

**Câu 1.** NMT báo Java Heap **reserved=2 GiB**, **committed=500 MiB**; MemoryMXBean báo heap **used=220 MiB**; RSS=700 MiB. Có gì mâu thuẫn?  
**Đáp án:** Không. Reserved là address space, committed là memory JVM đã commit, used là lượng heap đang dùng, RSS là resident process với nhiều vùng khác. Không thể suy leak từ bốn số đó.

**Câu 2.** BufferPoolMXBean direct memoryUsed tăng 400 MiB; NMT một nhóm cũng tăng 400 MiB. Có cộng hai số thành 800 MiB native usage không?  
**Đáp án:** Không. Hai nguồn có thể phản ánh cùng backing allocations. Đối chiếu xu hướng/nguồn gốc, không cộng các khung accounting khác nhau.

**Câu 3.** Có 30.000 virtual threads trên Java 21 nhưng ThreadMXBean chỉ 120 platform threads; Linux Threads=150. Vì sao?  
**Đáp án:** Virtual threads không có riêng một OS thread mỗi thread; ThreadMXBean Java 21 chỉ đếm platform threads; Linux còn đếm native/JVM internal threads.

**Câu 4.** NMT Thread reserved tăng 500 MiB nhưng committed chỉ tăng 10 MiB và RSS tăng 6 MiB. Có phải process đã tiêu 500 MiB RAM mới?  
**Đáp án:** Không. Reserved chủ yếu là không gian địa chỉ ảo, không phải resident memory.

**Câu 5.** NMT, BufferPoolMXBean và thread count gần như ổn định nhưng RSS và RssAnon tăng qua nhiều mốc tải tương đương. Bước tiếp theo là gì?  
**Đáp án:** Xem smaps/smaps_rollup và các native allocations ngoài NMT, kiểm tra JNI/native libraries, allocator caching và residency, sau đó thử giả thuyết dưới tải đại diện. Không khẳng định leak khi chưa tìm thấy vòng đời allocations không được giải phóng.

**Câu 6.** memory.current tăng 600 MiB, process RSS chỉ tăng 50 MiB. Được phép gán 550 MiB còn lại cho “JVM native leak” không?  
**Đáp án:** Không. Cần xem process khác cùng cgroup, file cache, memory.stat, OOM events và cách cgroup accounting.

## 12. Tài liệu để kiểm chứng

- [Oracle JDK 21 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html) — phạm vi, mức tracking, overhead, baseline/diff và giới hạn.
- [Oracle JDK 21 — Diagnostic Tools / NMT Categories](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html) — reserved/committed, các nhóm memory và quy trình điều tra.
- [Oracle JDK 21 — BufferPoolMXBean API](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/BufferPoolMXBean.html) — count, totalCapacity, memoryUsed và trường hợp -1.
- [Oracle JDK 21 — ThreadMXBean API](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html) — platform threads và giới hạn với virtual threads.
- [Oracle JDK 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html) — mô hình carrier threads và tài nguyên.
- [Linux man-pages — /proc/PID/status](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html) — VmRSS, VmSize, RssAnon, RssFile, Threads.
- [Linux Kernel — proc filesystem / smaps](https://www.kernel.org/doc/html/latest/filesystems/proc.html) — RSS/PSS/shared/private và smaps_rollup.
