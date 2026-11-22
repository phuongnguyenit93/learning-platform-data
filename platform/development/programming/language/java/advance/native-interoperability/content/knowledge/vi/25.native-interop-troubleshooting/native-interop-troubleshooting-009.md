# Dùng công cụ kiểm tra bộ nhớ native và hiểu giới hạn của Native Memory Tracking

Ứng dụng Java có thể tiêu thụ nhiều bộ nhớ hơn đáng kể so với phần **Java heap** nhìn thấy trong heap dump hoặc qua chỉ số GC. Với chương trình dùng JNI, JNA, Foreign Function & Memory API (FFM), thư viện C/C++, driver, codec hoặc cơ sở dữ liệu nhúng, bộ nhớ nằm ngoài heap còn có thể tăng do cấp phát native của chính JVM và của thư viện bên ngoài. Để chẩn đoán đúng, phải phối hợp **Native Memory Tracking (NMT)** của HotSpot, số liệu hệ điều hành và khi cần, công cụ theo dõi cấp phát native.

Điểm cần nhớ ngay từ đầu: **NMT không phải máy đo toàn bộ bộ nhớ của tiến trình Java**. NMT theo dõi các cấp phát nội bộ của HotSpot JVM; nó không tự theo dõi những lần malloc/free mà thư viện JNI hoặc thư viện native bên thứ ba thực hiện bên ngoài cơ chế cấp phát của JVM. Vì vậy, thấy RSS tăng trong khi NMT tương đối ổn định không đủ để kết luận công cụ lỗi hay bộ nhớ không bị rò rỉ.

## 1. Xác định loại bộ nhớ đang điều tra

Một tiến trình Java thường có nhiều thành phần:

| Thành phần | Nguồn sử dụng điển hình | Công cụ chẩn đoán phù hợp |
| --- | --- | --- |
| **Java heap** | Đối tượng Java, mảng, cache Java | Chỉ số GC, heap histogram, heap dump, profiler heap |
| **Metaspace / class metadata** | Thông tin class và class loader | NMT Class, số lượng class, class unloading |
| **Thread stacks** | Stack của các thread nền tảng; native thread | NMT Thread, thread dump, công cụ hệ điều hành |
| **Code cache / JIT / GC structures** | Mã biên dịch, cấu trúc GC, compiler | NMT Code, GC, Compiler, tùy phiên bản JDK |
| **Native memory do HotSpot quản lý** | Arena, malloc/mmap của các subsystem HotSpot | NMT summary/detail |
| **Bộ nhớ direct / off-heap của JDK** | DirectByteBuffer hoặc cơ chế cấp phát ngoài heap do JDK sử dụng | Chỉ số direct buffer/JMX, NMT nếu đường cấp phát được theo dõi, OS metrics |
| **Native heap của thư viện ngoài** | malloc/calloc/realloc, new/delete từ JNI/JNA/FFM hoặc thư viện C/C++ | Native allocator profiler, Valgrind, AddressSanitizer/LeakSanitizer, công cụ OS |
| **Memory mapping / thư viện dùng chung** | File mapping, shared libraries, anonymous mappings | /proc, pmap, smaps, VMMap, vmmap |
| **Bộ nhớ cấp cho process/container** | Resident pages, page cache, cgroup accounting | RSS/PSS, cgroup memory.current và memory.stat |

Bảng phân loại chỉ là định hướng, không phải quan hệ một-một giữa số đo và nơi cấp phát. Chẳng hạn, một DirectByteBuffer giữ phần **đối tượng wrapper** trên Java heap nhưng giữ dữ liệu ở ngoài heap; một thư viện native có thể tự cấp phát và ghi vào vùng nhớ mà HotSpot không biết tới. Các cơ chế FFM/JNA/JNI là cách gọi native, **không tự bảo đảm khả năng quan sát toàn bộ bộ nhớ native**.

### Các con số thường bị đánh đồng

- **Reserved:** khoảng **không gian địa chỉ ảo** được dành trước cho một vùng. Một vùng reserved rất lớn chưa đồng nghĩa với một lượng RAM vật lý tương ứng đang sử dụng.
- **Committed:** lượng bộ nhớ được hệ thống/JVM cam kết có thể dùng theo ngữ nghĩa nền tảng; không đồng nghĩa tuyệt đối với số trang vật lý hiện đang resident.
- **RSS (Resident Set Size):** số trang của process hiện ở bộ nhớ vật lý theo cách OS hạch toán; có thể gồm trang shared và file-backed. RSS không bằng tổng tất cả vùng reserved hay committed.
- **PSS (Proportional Set Size, Linux):** phân chia phần trang shared theo số process cùng dùng; hữu ích khi nhiều process chia sẻ thư viện hoặc mapping.
- **VIRT/VSZ:** tổng không gian địa chỉ ảo, thường rất lớn với JVM 64-bit; tăng VIRT riêng lẻ chưa đủ khẳng định leak.
- **Container memory:** bộ nhớ tính theo cgroup, có thể gồm page cache và nhiều process; không lấy trực tiếp một RSS làm đại diện toàn bộ usage của container.

**Không dùng phép tính RSS − NMT committed để suy ra chính xác lượng bộ nhớ JNI bị rò rỉ.** Các đại lượng khác phạm vi thu thập và phương pháp hạch toán. Phép so sánh hữu ích nhất là **xu hướng tại cùng thời điểm** và quan hệ của chúng với workload, GC, số thread, số handle và malloc của thư viện.

## 2. Native Memory Tracking (NMT) thực sự đo gì?

NMT là tính năng chẩn đoán của **HotSpot VM**. Khi được bật lúc khởi động JVM, NMT ghi nhận những cấp phát được HotSpot instrument theo nhóm như Java Heap, Class, Thread, Code, GC, Compiler, Internal, Other, Symbol và Native Memory Tracking. Tên, cách phân nhóm, chi tiết thống kê có thể thay đổi giữa các bản JDK.

Có hai mức phổ biến:

| Mức NMT | Thông tin nhận được | Khi nào dùng |
| --- | --- | --- |
| **summary** | Tổng reserved/committed và số liệu theo nhóm subsystem | Điều tra ban đầu và so sánh theo thời gian với chi phí thấp hơn detail |
| **detail** | Thông tin summary cộng thêm các vùng/call site native do HotSpot theo dõi | Khoanh vùng nhóm HotSpot tăng bất thường; cần điều tra sâu |

NMT **mặc định tắt** trên nhiều bản HotSpot; phải bật qua cờ JVM khi khởi chạy:

~~~bash
# Mức tổng hợp:
java -XX:NativeMemoryTracking=summary -jar app.jar

# Hoặc mức chi tiết:
java -XX:NativeMemoryTracking=detail -jar app.jar
~~~

Nếu process đã khởi chạy khi NMT tắt, **jcmd không thể bật hoặc khởi động lại NMT cho process đó**. Cần lập kế hoạch restart với cờ thích hợp, hoặc chuyển sang số liệu OS/native profiler trong thời gian chờ.

NMT có chi phí thực thi và bộ nhớ; tài liệu Oracle mô tả overhead xấp xỉ **5–10%** trong một số cấu hình. NMT cũng sử dụng bộ nhớ để tự theo dõi và có nhóm thống kê dành cho chính nó. Không mặc định bật detail trên mọi production JVM mà không đánh giá tác động.

### Ranh giới quan sát quan trọng

1. **NMT không bao quát cấp phát native bên ngoài HotSpot**, như malloc/new trực tiếp trong thư viện C/C++ do JNI gọi. Cần profiler native hoặc công cụ của hệ điều hành.
2. **NMT không cho biết đối tượng Java nào giữ tham chiếu gây leak Java heap.** Dòng Java Heap trong NMT phản ánh reserved/committed; muốn tìm object graph phải dùng heap dump/histogram.
3. **NMT detail không phải Java call stack profiler** và cũng không mặc nhiên biết hàm Java nào đã gọi mã C từ một thư viện bên ngoài. Call site NMT chủ yếu là nơi cấp phát trong HotSpot.
4. Một số vùng native/JDK, mapping đặc biệt và Class Data Sharing có phạm vi thống kê không đầy đủ; không suy diễn NMT là tổng kế toán tuyệt đối của process.
5. **Malloc đang sống** khác với **malloc đã được giải phóng nhưng allocator còn giữ arena/pages**. RSS không giảm ngay sau free không tự chứng minh leak.
6. NMT không tự phát hiện use-after-free, buffer overflow hoặc double free; AddressSanitizer/Valgrind và kiểm tra quyền sở hữu mới phù hợp hơn cho những lỗi đó.

Các giới hạn trên đặc biệt quan trọng khi cùng một tiến trình có cả HotSpot và nhiều thư viện native do nhà cung cấp khác nhau quản lý.

## 3. Các lệnh NMT và cách đọc đúng

Sử dụng công cụ **jcmd** từ JDK tương thích và có quyền attach tới JVM đích. Thực tế thường phải chạy trên cùng máy và cùng user hiệu dụng với process Java. Trong container, PID namespace, quyền hệ thống hoặc việc không có công cụ JDK trong image có thể khiến jcmd không attach được.

### Xác định JVM và chụp snapshot

~~~bash
# Liệt kê JVM có thể nhìn thấy trong namespace hiện tại:
jcmd -l

# Nếu chưa rõ JVM hỗ trợ lệnh nào:
jcmd <PID> help VM.native_memory

# Xem số liệu NMT tổng hợp:
jcmd <PID> VM.native_memory summary scale=MB

# Với process đã bật NMT detail:
jcmd <PID> VM.native_memory detail scale=KB
~~~

Ở đây **<PID> phải được thay bằng PID thực**. Những dòng trên là lệnh mẫu, không chạy nguyên văn với dấu ngoặc góc.

### So sánh với một mốc nền (baseline)

Để đo tác động của workload, hãy khởi động, chờ warm-up/JIT/class loading cơ bản ổn định rồi đặt mốc:

~~~bash
jcmd <PID> VM.native_memory baseline
~~~

Sau khi chạy một lượng công việc xác định:

~~~bash
jcmd <PID> VM.native_memory summary.diff scale=KB
~~~

Nếu process bật detail từ đầu:

~~~bash
jcmd <PID> VM.native_memory detail.diff scale=KB
~~~

**summary.diff** và **detail.diff** là thay đổi **so với baseline gần nhất**, không phải tốc độ cấp phát tức thời. Sau mỗi giai đoạn muốn so sánh độc lập, đặt baseline mới và ghi lại mốc thời gian. Nếu workload mới khởi động, cache và JIT tăng là hiện tượng bình thường; phải quan sát qua nhiều chu kỳ rồi mới đánh giá có xu hướng tăng không giới hạn.

### Đọc từng nhóm trong báo cáo

Một số nhóm thường cần chú ý:

- **Java Heap:** vùng heap được reserved/committed; không cho biết số object đang sống. GC có thể giữ committed capacity ngay cả khi đã thu hồi object.
- **Class:** class metadata, metaspace, class space; tăng cùng số class/classloader có thể là hợp lệ hoặc liên quan classloader retention.
- **Thread:** cấu trúc thread và các thông số stack mà HotSpot theo dõi; số lượng platform thread tăng không kiểm soát có thể làm tăng bộ nhớ và tài nguyên OS.
- **Code:** code cache và mã JIT; thường tăng trong quá trình warm-up.
- **GC:** native structures phục vụ GC; phụ thuộc collector, heap layout và workload.
- **Internal / Other:** các nhóm tổng hợp; **không được xem Other là bằng toàn bộ bộ nhớ thư viện JNI bên ngoài**.
- **Native Memory Tracking:** overhead do bản thân hệ thống theo dõi.

NMT có thể cho thấy cấu trúc đại loại như:

~~~text
Native Memory Tracking:
Total: reserved=...KB, committed=...KB
- Java Heap (reserved=...KB, committed=...KB)
- Class     (reserved=...KB, committed=...KB)
- Thread    (reserved=...KB, committed=...KB)
- Code      (reserved=...KB, committed=...KB)
- GC        (reserved=...KB, committed=...KB)
- Other     (reserved=...KB, committed=...KB)
~~~

Đây là **hình dạng minh họa**, không phải output thực tế hoặc danh sách đầy đủ; nhiều bản JDK còn có thêm nhóm và thành phần con như malloc, mmap, arena. Các giá trị thay đổi theo JDK, flags, GC, OS và thời điểm chụp. Nếu ở mức diff, số thay đổi có thể mang dấu cộng hoặc trừ.

**Reserved tăng mạnh nhưng committed gần như giữ nguyên**: có thể đang dành không gian địa chỉ, chưa phải bằng chứng tiêu thụ RAM tương ứng.

**Committed tăng ở Thread/Class/GC**: có căn cứ để điều tra subsystem liên quan, nhưng cần đối chiếu số thread/class, lifecycle và workload. Không gán nhãn “memory leak” chỉ dựa trên một snapshot.

**RSS tăng còn NMT gần như đứng yên**: chuyển hướng xem các vùng OS mapping, bộ nhớ thư viện ngoài, direct/mapped buffers, page residency, allocator fragmentation hoặc các phần ngoài phạm vi NMT.

## 4. Đo bộ nhớ process bằng công cụ của hệ điều hành

NMT trả lời: **HotSpot đã ghi nhận những vùng nào?** Công cụ OS trả lời: **process hiện có những vùng address/mapping/resident nào?** Phải chụp hai nhóm số liệu gần cùng thời điểm, dưới cùng workload.

### Linux

~~~bash
# Bộ nhớ RSS/VSZ của process (đơn vị RSS và VSZ thường là KiB):
ps -p <PID> -o pid,rss,vsz,etime,args

# Trạng thái và số liệu memory process:
cat /proc/<PID>/status

# Tổng hợp mapping; chỉ có khi kernel/quyền truy cập hỗ trợ:
cat /proc/<PID>/smaps_rollup

# Chi tiết các vùng mapping:
cat /proc/<PID>/smaps

# Tổng quan bảng mapping (nếu có tiện ích pmap):
pmap -x <PID>
~~~

Trong /proc/<PID>/status, chú ý VmRSS, VmSize, VmHWM, Threads. Trong smaps_rollup hoặc smaps, chú ý Rss, Pss, Private_Clean/Private_Dirty, Anonymous và các vùng file-backed. Để phân biệt anonymous native heap, stack, shared libraries và file mapping, dùng bảng mapping cùng dữ liệu smaps; đường dẫn map và quyền vùng chưa đủ để biết chính xác “hàm nào đã malloc”.

**Container/cgroup v2:** thêm số liệu từ cgroup **đúng với process đích**:

~~~bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events
~~~

Các đường dẫn này là trường hợp phổ biến khi tiến trình nằm ngay trong cgroup được mount; vị trí thực tế có thể khác nếu cấu hình mount hoặc cgroup namespace khác. Container memory.current có thể gồm cả page cache và usage của các process thuộc cgroup, nên không so sánh 1:1 với RSS của một JVM. Nếu process bị OOMKilled mà không xuất hiện Java OutOfMemoryError, kiểm tra memory.events, container status và native/RSS bên cạnh heap metrics.

### Windows

Dùng **Process Explorer** để xem private bytes, working set, image mapping và số thread; dùng **VMMap** để phân tích các vùng committed/reserved, private data, image và mapped file. Bổ sung bộ đếm Process trong Performance Monitor nếu cần chuỗi thời gian. Working Set không đồng nghĩa với Private Bytes và cũng không được cộng nguyên xi với NMT committed.

### macOS

Dùng **Activity Monitor** để nhận diện xu hướng ban đầu, **vmmap <PID>** để xem các vùng memory và mapping, **Instruments/Allocations hoặc Leaks** khi cần truy nguyên native allocation. Một số công cụ yêu cầu quyền/entitlement phù hợp. Không coi resident memory do hệ điều hành báo là cùng đại lượng với NMT reserved.

### Quy tắc thu thập chung

Ghi kèm: bản JDK/vendor, JVM flags, build native library, PID, thời điểm, số request/operation, heap used/committed, RSS/PSS, thread count, NMT category và giới hạn cgroup. So sánh các mẫu cùng tải, cùng pha warm-up; làm lại nhiều chu kỳ để tránh kết luận từ một điểm đo có biến động do GC hoặc OS reclaim.

## 5. Khi nào dùng profiler cấp phát native?

Nếu bộ nhớ tăng nằm **ngoài phạm vi NMT**, cần công cụ ghi nhận cấp phát và giải phóng tại mức native.

| Công cụ | Điểm mạnh | Lưu ý |
| --- | --- | --- |
| **Valgrind Memcheck** (Linux và môi trường hỗ trợ) | Phát hiện nhiều lỗi đọc/ghi sai vùng và leak, cung cấp native stack trace | Chạy rất chậm; toàn bộ JVM lớn sinh nhiều noise; nên thu nhỏ thành repro native |
| **AddressSanitizer / LeakSanitizer** (ASan/LSan) | Phát hiện buffer overflow, use-after-free và các leak tương ứng khi build/instrument phù hợp | Cần build native code với instrumentation; đưa sanitizer vào process JVM có thể cần thêm cấu hình |
| **heaptrack** (Linux) | Theo dõi cấp phát native theo call stack và mức memory sử dụng theo thời gian | Overhead khi thu thập; có thể cần symbol/debug info để call stack hữu ích |
| **jemalloc/tcmalloc profiling** | Phân tích các allocation đi qua allocator tương ứng | Chỉ quan sát allocation thực sự được định tuyến qua allocator đó |
| **eBPF/perf/native tracing** (Linux) | Quan sát allocator/syscalls và xu hướng theo process trong môi trường phù hợp | Cần quyền kernel, biểu tượng và cách giải thích allocation stack chính xác |
| **VMMap, Instruments** | Xem chi tiết bản đồ vùng nhớ hoặc native allocations trên OS tương ứng | Mức độ chi tiết/nguồn dữ liệu khác nhau tùy công cụ |

Không có profiler duy nhất bao phủ mọi cơ chế. Một thư viện có thể dùng malloc, mmap, allocator riêng hoặc GPU/device memory; cần chọn bộ cảm biến theo **cơ chế cấp phát thực tế**. Ví dụ, hook mỗi malloc không tự quan sát mọi mmap. Với native code do mình sở hữu, biên dịch debug symbols và dùng sanitizer trong bản test cô lập thường cho tín hiệu rõ hơn việc chạy Valgrind trên toàn JVM production.

Khi phân tích leak, phân biệt:

- **Definitely lost:** chương trình không còn đường dẫn tới vùng cấp phát (nếu công cụ định nghĩa được).
- **Still reachable / retained cache:** bộ nhớ còn giữ bởi allocator hoặc cache; có thể là chủ ý.
- **Fragmentation:** allocator khó hoàn trả trang hoặc tái sử dụng khối phù hợp.
- **High-water mark:** hệ điều hành hiển thị đỉnh sử dụng, không phải bộ nhớ đang sống.
- **Mmap/file cache:** có thể làm thay đổi RSS/cgroup mà không xuất hiện là malloc sống.
- **Unreleased handle/resource:** ngoài vùng byte còn có tài nguyên file descriptor, thread, socket, GPU allocation.

Đặt câu hỏi “cấp phát nào chưa được giải phóng sau vòng đời nghiệp vụ?” thay vì chỉ hỏi “RSS có giảm ngay sau khi free không?”.

## 6. Thực hành Java 17 + JNI: nhìn thấy khoảng trống của NMT

Thực hành này tạo hai đợt tiêu thụ bộ nhớ ngoài heap trong cùng JVM:

1. **32 MiB DirectByteBuffer** qua API JDK, giữ tham chiếu để vùng nhớ tồn tại trong suốt giai đoạn đo.
2. **32 MiB malloc** trực tiếp từ thư viện C do JNI gọi, rồi free.

Ta so sánh **NMT** và **RSS/PSS** ở ba thời điểm. Mục tiêu là hiểu phạm vi đo; số thay đổi cụ thể phụ thuộc JDK, libc, OS, cách hệ thống cấp phát trang và các tác vụ JVM đồng thời.

### 6.1. Tệp Java: NativeMemoryProbe.java

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

public final class NativeMemoryProbe {
    private static final int MIB = 1024 * 1024;
    private static final BufferedReader IN = new BufferedReader(
            new InputStreamReader(System.in, StandardCharsets.UTF_8));

    // Giữ tham chiếu sống qua các điểm đo.
    private static volatile ByteBuffer direct;

    static {
        System.loadLibrary("nmtprobe");
    }

    private static native void nativeAllocate(int mebibytes);
    private static native void nativeFree();

    private static void pause(String stage) throws IOException {
        System.out.println(stage + " | PID=" + ProcessHandle.current().pid());
        System.out.println("Chụp NMT/RSS ở terminal khác rồi nhấn Enter.");
        if (IN.readLine() == null) {
            throw new IllegalStateException("Cần chạy trong terminal tương tác");
        }
    }

    public static void main(String[] args) throws IOException {
        pause("P0: Chưa tạo buffer/native malloc");

        direct = ByteBuffer.allocateDirect(32 * MIB);
        // Chạm từng trang nhằm làm rõ sự khác biệt giữa cấp phát và resident pages.
        for (int i = 0; i < direct.capacity(); i += 4096) {
            direct.put(i, (byte) 1);
        }
        pause("P1: Đã tạo DirectByteBuffer 32 MiB");

        nativeAllocate(32);
        try {
            pause("P2: Đã malloc 32 MiB từ JNI");
        } finally {
            nativeFree();
        }

        pause("P3: Đã free malloc JNI; DirectByteBuffer vẫn còn sống");
        direct = null; // Không bảo đảm bộ nhớ direct được thu hồi ngay.
    }
}
~~~

Lớp dùng Java 17, ProcessHandle và ByteBuffer có sẵn trong JDK. Chương trình chủ động chờ input nên có thể chụp NMT/OS giữa các pha. Chúng ta **không đưa ra stdout số PID cố định**, vì PID thay đổi theo lần chạy.

### 6.2. Tệp C: nativeprobe.c

~~~c
#include <jni.h>
#include <stdlib.h>
#include <string.h>

static unsigned char *native_block = NULL;

static void throw_java(JNIEnv *env, const char *type, const char *message) {
    jclass error = (*env)->FindClass(env, type);
    if (error != NULL) {
        (*env)->ThrowNew(env, error, message);
    }
}

JNIEXPORT void JNICALL
Java_NativeMemoryProbe_nativeAllocate(JNIEnv *env, jclass unused, jint mib) {
    (void) unused;

    if (mib <= 0) {
        throw_java(env, "java/lang/IllegalArgumentException", "mib must be positive");
        return;
    }
    if (native_block != NULL) {
        throw_java(env, "java/lang/IllegalStateException", "already allocated");
        return;
    }

    size_t bytes = (size_t) mib * 1024u * 1024u;
    native_block = (unsigned char *) malloc(bytes);
    if (native_block == NULL) {
        throw_java(env, "java/lang/OutOfMemoryError", "malloc failed");
        return;
    }

    // Ghi thực sự vào từng trang qua memset để vùng cấp phát có resident pages.
    memset(native_block, 0x5a, bytes);
}

JNIEXPORT void JNICALL
Java_NativeMemoryProbe_nativeFree(JNIEnv *env, jclass unused) {
    (void) env;
    (void) unused;

    free(native_block);
    native_block = NULL;
}
~~~

Trong demo này, tất cả thao tác native diễn ra tuần tự từ main thread; biến static native_block **không phải thiết kế thread-safe** cho ứng dụng có nhiều caller. Với hệ thống thật, phải tuân thủ policy đồng thời và vòng đời handle của thư viện, đồng thời tránh static global state không có chủ sở hữu rõ ràng.

### 6.3. Biên dịch trên Linux với JDK và GCC

~~~bash
# JAVA_HOME trỏ đúng đến thư mục JDK 17+.
javac -h . NativeMemoryProbe.java

gcc -O0 -g -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  nativeprobe.c -o libnmtprobe.so

# Chạy trong terminal tương tác, giữ lại để nhấn Enter giữa các pha.
java -XX:NativeMemoryTracking=detail \
  -Djava.library.path=. NativeMemoryProbe
~~~

**javac -h** tạo header JNI từ đúng tên phương thức; chữ ký C bên trên tương ứng lớp không khai báo package. Trên Windows/macOS, tên thư viện, cờ linker và thư mục include theo OS khác; ví dụ lệnh build này chủ ý dành riêng cho Linux. Để áp dụng ở môi trường khác, biên dịch shared library theo toolchain và JNI headers của nền tảng.

Trong **terminal thứ hai**, thay PID được chương trình in ra:

~~~bash
# Tại P0, chụp hệ điều hành rồi đặt NMT baseline:
ps -p <PID> -o pid,rss,vsz
jcmd <PID> VM.native_memory baseline

# Tại P1 và P2:
jcmd <PID> VM.native_memory summary.diff scale=KB
ps -p <PID> -o pid,rss,vsz
cat /proc/<PID>/smaps_rollup

# Khi cần xem call site HotSpot (vì JVM đã bật detail):
jcmd <PID> VM.native_memory detail.diff scale=KB
~~~

Sau khi ở P1, có thể ghi snapshot và **đặt baseline mới ngay tại P1** để isolate sự thay đổi P1 → P2; ghi rõ thời điểm trong log để tránh lẫn các mốc. Tại P3 chụp lại khi malloc đã free.

### 6.4. Dự đoán và giải thích kết quả

| Pha | Thao tác | Điều nên kiểm tra |
| --- | --- | --- |
| **P0** | Chưa tạo buffer trong demo | Dùng làm baseline; JVM vẫn tiêu thụ bộ nhớ khởi động |
| **P1** | ByteBuffer.allocateDirect 32 MiB, chạm trang | RSS có thể tăng; các phần cấp phát qua đường JDK/HotSpot có thể xuất hiện ở NMT, tùy implementation/phiên bản |
| **P2** | malloc/memset 32 MiB trong thư viện JNI | RSS/anonymous resident thường tăng; NMT **không ghi nhận trực tiếp chính malloc của thư viện ngoài** |
| **P3** | free malloc JNI | Số allocation sống giảm; RSS có thể giảm hoặc vẫn cao do allocator giữ pages; DirectByteBuffer còn sống |

Khi thấy P2 làm RSS tăng rõ mà NMT không xuất hiện khoản tăng tương ứng, đó là minh họa điển hình của **giới hạn NMT**. Tuy nhiên các hoạt động HotSpot xảy ra đồng thời vẫn có thể khiến NMT thay đổi đôi chút. Không ép số liệu bằng đúng 32 MiB, không giả định nhãn NMT nhất định là Other cho mọi JVM, và không kết luận “leak” từ một malloc **được free đúng** như demo này.

Nếu muốn điều tra một leak thực tế, thay bằng một native module có lifecycle rõ ràng, chạy lặp nhiều vòng nghiệp vụ và so sánh **số byte allocated còn sống** với snapshot/call stack từ profiler. Khi viết repro, phải tránh làm hỏng hệ thống production bằng cách cố ý tích lũy malloc không giới hạn.

## 7. Quy trình điều tra khi RSS cứ tăng dù heap Java ổn định

Đây là cách làm có thể áp dụng cho ứng dụng Java giao tiếp native:

**Bước 1 — Xác minh triệu chứng và phạm vi.** Ghi thời điểm tăng, tải, restart, OOMKilled, Java OutOfMemoryError, số process trong container và limit OS. Phân biệt “Java heap used tăng” với “RSS/private bytes tăng”; lưu cả peak và current.

**Bước 2 — Thu thập số đo đồng bộ.** Lấy heap used/committed và số thread, NMT summary hoặc diff, RSS/PSS, các vùng mappings; đồng thời ghi số lượng native handle và số lần open/close thực tế nếu adapter có metrics.

**Bước 3 — Dùng NMT khoanh vùng phần HotSpot.** Nếu tăng rõ ở Class/Thread/Code/GC, kiểm tra classloader/thread lifecycle/warm-up/GC tương ứng. Nếu không thấy tăng phù hợp, coi **untracked native allocation** là giả thuyết cần kiểm chứng, không phải kết luận duy nhất.

**Bước 4 — Xem OS mapping và allocator.** Với Linux, so sánh smaps và anonymous/private dirty regions, số thread, mapped files; kiểm tra thư viện cấp phát bằng malloc hay mmap/allocator riêng. Với container, kiểm tra cgroup limit và page cache riêng biệt.

**Bước 5 — Khoanh native component bằng thí nghiệm đối chứng.** Chạy cùng workload có và không kích hoạt tính năng native đáng nghi; thay đổi số lượng handle hoặc số request; kiểm tra memory sau khi hoàn tất vòng đời và sau thời gian đủ dài để allocator tái sử dụng. Không lấy kết quả của hai mức traffic khác nhau để so sánh trực tiếp.

**Bước 6 — Dùng native profiler/sanitizer.** Trên bản repro với symbol/debug build, thu call stack cấp phát còn sống; đối chiếu mã create/destroy, malloc/free, new/delete, mmap/munmap. Với memory corruption, ưu tiên ASan/Valgrind trên native component riêng; leak chỉ là một trong nhiều dạng lỗi bộ nhớ.

**Bước 7 — Sửa quyền sở hữu và chứng minh hồi quy.** Mỗi native resource phải có điểm tạo, owner, thời điểm sử dụng cuối, đường dọn dẹp bình thường và ngoại lệ. Đo lại nhiều chu kỳ có cùng tải; xác nhận memory sống ngừng tăng hoặc đạt trạng thái ổn định, đồng thời test concurrency/timeout/shutdown.

### Bảng diễn giải các tình huống thường gặp

| Quan sát | Giả thuyết cần kiểm tra | Bước tiếp theo |
| --- | --- | --- |
| NMT Thread tăng và OS thread count tăng | Tạo quá nhiều platform/native threads hoặc không shutdown executor | Thread dump, cấu hình pool, vòng đời thread |
| NMT Class/Metaspace tăng sau mỗi deploy/reload | ClassLoader retention hoặc class generation liên tục | Số classloader/class, heap roots, unloading |
| NMT Code/Compiler tăng khi warm-up | Hoạt động JIT bình thường | So sánh sau warm-up và dưới tải ổn định |
| NMT GC tăng cùng thay đổi cấu hình heap/collector | Cấu trúc GC tăng hợp lệ | Đối chiếu JVM flags/heap sizing và GC logs |
| RSS tăng mạnh nhưng NMT ổn định | malloc của JNI, thư viện thứ ba, mmap hoặc page residency/fragmentation | smaps, native profiler, log handle allocation |
| NMT reserved rất lớn, committed thấp | Vùng địa chỉ được dành trước | So committed, RSS/PSS; tránh coi reserved là RAM dùng thực tế |
| Native free đã gọi mà RSS không hạ ngay | Allocator giữ arena/fragmentation hoặc OS chưa reclaim | Theo dõi outstanding allocation, reuse và mapping |
| Heap histogram ổn định nhưng container OOMKilled | Phần ngoài heap, page cache, sidecar/process khác, limit cgroup | memory.stat/events, RSS/PSS từng process |

Một snapshot tại lúc process sắp OOM thường không đủ. Chuỗi dữ liệu có workload và baseline rõ ràng giá trị hơn một bảng con số rời rạc.

## 8. Những giới hạn khi điều tra buffer trực tiếp, FFM và mapping

**DirectByteBuffer:** byte[] hoặc object Java không chứa toàn bộ dung lượng data off-heap. Java heap dump có thể cho biết wrapper/đường giữ tham chiếu, nhưng không có nghĩa toàn bộ nội dung native buffer được lưu trong dump. Theo dõi direct buffer pool qua BufferPoolMXBean hoặc Metrics tương ứng để có thêm góc nhìn; tổng buffer pool cũng không phải “tất cả native memory”.

**JNI:** một thư viện C được nạp vào cùng process có thể giữ con trỏ malloc trên biến global hoặc native handle mà phía Java không còn nhìn thấy. Nếu quên nativeFree/nativeDestroy, heap dump Java có thể hoàn toàn bình thường. NMT không tự kiểm kê allocation do thư viện đó trực tiếp làm.

**FFM:** các MemorySegment/Arena có quy tắc quyền sở hữu và vòng đời. Một vùng bộ nhớ do thư viện bên ngoài trả về qua downcall cần được quản lý theo contract của thư viện; chỉ quan sát NMT không xác minh đã gọi đúng free. FFM đã trở thành API chuẩn từ **JDK 22**; trên JDK 17 không dùng cú pháp FFM chuẩn JDK 22. Nếu ví dụ chạy trên Java 17, JNI như phần thực hành là một lựa chọn có sẵn.

**Memory-mapped files:** mapping lớn làm tăng virtual address space; số trang resident phụ thuộc trang nào đã được chạm và OS cache/reclaim. NMT không là công cụ đầy đủ để phân biệt file-backed RSS, anonymous RSS và cache. Dùng smaps/VMMap và xem logic unmap/close cùng lifecycle của file.

**C/C++ allocator:** malloc có thể giữ arena sau free. Một số thư viện dùng allocator riêng và giữ buffer pool để tái sử dụng. Kết luận leak cần chứng cứ về **outstanding allocations hoặc tăng kéo dài qua các chu kỳ công việc tương đương**, không chỉ từ việc RSS không giảm ngay.

## 9. Những lỗi chẩn đoán phổ biến

1. **Đọc -Xmx thành giới hạn RAM của toàn process.** -Xmx chỉ chủ yếu giới hạn dung lượng Java heap; ngoài heap còn có stack, code cache, native heap, mmap và overhead khác.
2. **Thấy NMT không tăng rồi loại bỏ nghi vấn JNI leak.** Malloc trong thư viện ngoài không thuộc phạm vi tracking HotSpot.
3. **Coi reserved là physical memory.** Reserved có thể là địa chỉ ảo chưa có trang resident tương ứng; đọc committed/RSS/PSS và xu hướng.
4. **Chụp NMT diff trước khi baseline.** Không có mốc so sánh hợp lệ; phải baseline sau warm-up hoặc pha muốn điều tra.
5. **Chạy detail trên process chỉ bật summary.** Mức detail cần được bật khi JVM khởi động; jcmd không tự nâng mức theo dõi đã thiếu.
6. **Cho rằng timeout/restart/finalizer sẽ tự giải phóng mọi native allocation.** Native library có contract cấp phát/giải phóng riêng; cần owner, cleanup chính xác và bảo vệ trước use-after-free.
7. **Dùng heap dump để truy con trỏ native không được Java quản lý.** Heap dump có thể thấy wrapper, nhưng chưa đủ xác định native allocation stack.
8. **Quên đồng bộ hóa thời điểm đo.** RSS sau GC và NMT trước GC là hai trạng thái khác nhau; snapshot lệch workload dễ làm sai hướng.
9. **Chạy công cụ nặng trên production process khi chưa đánh giá tác động.** Sanitizer và Valgrind thường nên chạy trên bản repro/test; NMT cũng có overhead.
10. **Sửa bằng cách giảm heap mù quáng.** Giảm -Xmx có thể tạo khoảng trống cho native memory trong container, nhưng không sửa được malloc leak/handle leak gốc và có thể gây Java heap OOM.

## 10. Checklist thực tế khi xử lý sự cố native memory

- [ ] Xác nhận HotSpot/JDK vendor và phiên bản, JVM flags, native library version, nền tảng OS.
- [ ] Phân biệt **heap used**, **heap committed**, **NMT committed**, **RSS/PSS**, **container memory**.
- [ ] Xác nhận NMT bật từ khởi động và biết là summary hay detail.
- [ ] Ghi baseline và chụp diff sau các giai đoạn workload có thời điểm rõ ràng.
- [ ] Nếu NMT báo nhóm tăng, đối chiếu subsystem, thread/class count và GC/JIT warm-up.
- [ ] Nếu RSS tăng ngoài NMT, xem mappings, allocator của thư viện và native call stacks.
- [ ] Có phép thử tắt/bật đúng tính năng native hoặc giữ nguyên tải để cô lập nguyên nhân.
- [ ] Chứng minh native handle/buffer/mapping được giải phóng trên mọi đường xử lý, kể cả ngoại lệ và shutdown.
- [ ] Kiểm thử lại nhiều chu kỳ và lưu evidence để so với bản sửa.
- [ ] Không khẳng định “đã hết leak” chỉ vì RSS giảm một lần; kiểm tra outstanding allocation và xu hướng ổn định.

### Nguồn kỹ thuật chính thức để đối chiếu theo JDK

- [Oracle JDK 17 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html): phạm vi NMT, hạn chế native code bên ngoài, cách bật và các lệnh cơ bản.
- [Oracle JDK 21 — Diagnostic Tools, Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): ví dụ NMT report, baseline/diff và diễn giải category.
- [Oracle JDK 21 — jcmd command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): cú pháp chính xác của VM.native_memory và các lệnh chẩn đoán.

**Kết luận:** NMT rất hữu ích để phân tích **bộ nhớ do HotSpot quản lý**, đặc biệt khi xem thay đổi theo subsystem và call site. Nhưng chẩn đoán native interoperability phải đi thêm một lớp: số liệu OS để biết process đang chiếm những trang nào, và native profiler/sanitizer để biết **thư viện C/C++ đã cấp phát, giữ hoặc giải phóng những khối nào**. Chỉ ghép các nguồn chứng cứ này với vòng đời tài nguyên và workload mới xác định được nguyên nhân thực của sự tăng bộ nhớ.
