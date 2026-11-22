# Theo dõi bộ nhớ bản địa, số handle và độ trễ khi chạy lâu dài

**Ngữ cảnh:** Java Advance → native-interoperability → Hiệu năng tương tác.

Một ứng dụng Java gọi thư viện C/C++ qua JNI có thể chạy tốt trong vài phút nhưng tăng dần bộ nhớ của tiến trình, hết file descriptor/handle, hoặc có độ trễ p99 xấu đi sau nhiều giờ. Heap Java không tăng **không chứng minh** rằng bộ nhớ native ổn định; một JNI call nhanh khi thử đơn lẻ **không chứng minh** độ trễ tốt dưới tải liên tục.

Bài này hướng dẫn xây dựng bằng chứng theo thời gian cho ba trục: **native memory**, **tài nguyên dạng handle**, và **latency**. Trọng tâm là chọn đúng phép đo, đặt bộ đếm tại ranh giới sở hữu, phân biệt footprint với leak, chạy soak test có baseline/cooldown, và truy nguyên tín hiệu bất thường. Ví dụ Java 17 + JNI C11 có thể biên dịch trên Linux để quan sát một tài nguyên native được cấp phát, giữ lại và giải phóng đúng vòng đời.

## 1. Ba câu hỏi phải được trả lời đồng thời

1. **Bộ nhớ native:** Mỗi giai đoạn dùng bao nhiêu byte *đang sống*, tiến trình giữ bao nhiêu bộ nhớ thực, và con số nào tăng sau khi đã trở về cùng tải? Cần biết nguồn của allocation, không chỉ một tổng số.
2. **Số handle:** Có bao nhiêu đối tượng native/file descriptor/socket/OS handle còn mở, tổng số đã tạo/đóng, bao nhiêu lần tạo/đóng thất bại? Một handle có thể không chiếm nhiều RAM nhưng chạm giới hạn hệ điều hành.
3. **Độ trễ:** Từ góc nhìn người gọi, p50/p95/p99 và tỷ lệ lỗi/timeout có tăng trong lúc active memory/handle tăng không? Có thể các request chậm do GC, safepoint, native lock, I/O, page fault hoặc allocator, nên cần correlation theo mốc thời gian.

Không chọn duy nhất chỉ số RSS, heap-used hoặc average latency để kết luận. Ví dụ một thư viện giữ một pool 512 MiB sau lần tải đầu tiên có thể khiến RSS cao ổn định; ngược lại, chỉ cần vài nghìn FD bị bỏ quên đã làm request mới thất bại dù RSS gần như đứng yên.

### Bản đồ bộ nhớ cần quan sát

| Tầng | Ví dụ | Nguồn quan sát | Giới hạn của phép đo |
| --- | --- | --- | --- |
| Heap Java | Object, byte[], wrapper của native handle | MemoryMXBean, GC/JFR, heap dump | Không chứa toàn bộ byte mà malloc/native mmap đã cấp. |
| Bộ nhớ của HotSpot/JVM | Thread stack, GC internal, code cache, metadata | Native Memory Tracking (NMT), jcmd | NMT không bao quát mọi malloc của thư viện JNI bên thứ ba; cần xem reserved và committed riêng. |
| Direct/mapped buffers do JVM quản lý | ByteBuffer.allocateDirect, mapped buffer | BufferPoolMXBean direct/mapped | Giá trị *ước lượng*, không phải tổng mọi vùng off-heap do C/C++ tạo. |
| Native allocation do ứng dụng/thư viện sở hữu | malloc/new, memory arena của thư viện, mmap | Counter/histogram tại API allocate/free, native profiler, OS maps | Phải chèn đo tại đúng owner; tùy allocator, byte đã free chưa chắc trả ngay về OS. |
| Bộ nhớ vật lý của tiến trình | Anonymous pages, mapped libraries, stacks, shared pages | RSS/PSS/USS trên OS, container memory | RSS gồm các trang chia sẻ; không bằng tổng live bytes; container limit còn bao gồm thành phần khác. |

**Reserved ≠ committed ≠ RSS ≠ live bytes.** Reserved là không gian địa chỉ đã giữ; committed trong báo cáo JVM là cam kết cấp phát theo cách HotSpot theo dõi; RSS là trang đang cư trú trong RAM; live bytes là tài nguyên mà ứng dụng chưa release. Không cộng NMT committed + direct buffer + RSS thành “tổng native memory”: các phép đo có thể giao nhau hoặc đo những thứ khác nhau.

## 2. Thiết kế contract quan sát tại nơi tài nguyên được tạo

Cần có một **owner** rõ ràng cho từng loại resource: JNI library, wrapper Java, driver C/C++, hoặc một native subsystem. Phía tạo tài nguyên cần công bố tối thiểu:

| Metric đề xuất | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| native_allocations_total | Số lần cấp phát thành công kể từ khởi động | Counter tăng; so với native_frees_total theo loại resource. |
| native_frees_total | Số lần giải phóng thành công | Một resource phải có một lần release thực sự; không tự đặt lại counter lúc sampling. |
| native_live_blocks / native_live_bytes | Số allocation và byte hiện vẫn thuộc quyền sở hữu của owner | Gauge; xem slope lúc tải cố định và sau cooldown. |
| native_peak_live_bytes | Mốc live bytes cao nhất | Dùng kiểm tra budget/peak, **không** tự suy ra leak từ peak. |
| native_handles_open | Số handle logic còn sống theo từng loại | Phân biệt handle của thư viện với FD/socket của OS. |
| native_handle_open_errors_total / close_errors_total | Lỗi tạo/đóng resource | Cảnh báo cạn tài nguyên, sai vòng đời. |
| native_operation_duration_seconds | Phân phối độ trễ mỗi thao tác, nhãn operation/result | Histogram để tính percentile theo cửa sổ thời gian. |
| native_inflight_operations | Số lời gọi native đang xử lý | Dùng xác định concurrency/queue saturation. |

**Bất biến kế toán:** Nếu một resource có một lần open và một lần close, trên các đường thành công phải có **live = successful_open − successful_close** (sau khi xử lý đúng các handle tồn tại từ trước). Đếm open/close theo **sự kiện thực tế**, kể cả khi exception, timeout hoặc cancellation. Không coi wrapper Java bị garbage collect là bằng chứng resource đã được giải phóng, trừ khi contract sở hữu xác nhận release đã thực thi.

Một số handle **không phải file descriptor**: con trỏ thư viện, phiên GPU, context crypto, connection tới thiết bị, JNI GlobalRef... Linux FD count không nhìn thấy tất cả chúng. Với mỗi loại, đo active count ngay tại API tạo/đóng; dùng OS FD count làm tín hiệu độc lập. Trên Windows có thể đọc process handle count bằng công cụ OS/Win32, nhưng đó cũng không phải số mọi resource logic bên trong thư viện.

Không gắn pointer/address/handle ID vào label của time series: mỗi ID sẽ tạo một chuỗi riêng, gây nổ cardinality. Dùng loại resource, tên operation, kết quả, phiên bản thư viện; khi cần trace một handle cụ thể, ghi ID trong log/tracing có lấy mẫu và có giới hạn lưu giữ.

### Phải có trạng thái vòng đời hữu hạn

Một wrapper hợp lý chuyển trạng thái **OPEN → CLOSING → CLOSED**, bảo đảm cùng một con trỏ không bị giải phóng hai lần. Nếu callback/native thread còn dùng nó, close phải phối hợp bằng reference count, in-flight guard hoặc owner thread; biến địa chỉ về 0 ở Java thôi **không đủ** khi native có alias. Dùng try-with-resources/AutoCloseable, giải phóng trong finally; Cleaner (nếu dùng) chỉ là dự phòng, vì thời điểm GC không quyết định được.

Một native allocator có thể trì hoãn trả trang về OS, nên sau release cần so **native_live_bytes** và footprint OS tách biệt. **live trở về baseline trong khi RSS vẫn cao** có thể là allocator cache/fragmentation hoặc một vùng khác; **live tăng đều sau cooldown** là tín hiệu mạnh hơn để điều tra thiếu release.

## 3. Latency phải được đo theo phân phối và ranh giới lời gọi

Các bước của một lần Java → native có thể là: Java caller → chuẩn bị/copy argument → JNI transition → native queue/lock → native computation/I/O → copy result → Java caller. Hãy đo **end-to-end** bằng đồng hồ đơn điệu từ ngay trước khi gọi đến ngay sau khi nhận kết quả; nếu cần phân rã nguyên nhân, bổ sung timer *bên trong* native ở các giai đoạn có ý nghĩa.

- Dùng **System.nanoTime()** để đo khoảng thời gian bên Java; C/C++ dùng monotonic clock phù hợp nền tảng (ví dụ clock_gettime(CLOCK_MONOTONIC) trên Linux). Không dùng wall-clock hiện thời để tính elapsed, vì đồng hồ hệ thống có thể được điều chỉnh.
- Thu thập latency cho **cả success, error, timeout** theo operation và outcome. Nếu bỏ các cuộc gọi timeout, percentile chỉ còn của nhóm thành công nên có thể trông “nhanh” khi hệ thống tệ đi.
- Theo dõi **p50** (trung vị), **p95**, **p99** và khi có đủ mẫu **p99.9**; luôn kèm sample count, throughput và concurrency. Ví dụ ở 1000 request/phút, 1% tương đương khoảng 10 request/phút; average không thấy hết đuôi phân phối.
- Histogram/percentile phải có **cửa sổ thời gian** rõ (ví dụ 1 phút, 5 phút) và bucket phù hợp SLO. Không lấy trung bình cộng p99 của các cửa sổ để suy ra p99 toàn khoảng; cần ghép histogram/raw samples có cùng chính sách đo.
- Nếu workload là closed-loop (thread đợi request hoàn tất rồi mới gửi tiếp), lúc hệ thống nghẽn lưu lượng gửi thực sẽ giảm và dễ tạo **coordinated omission**. Khi SLO yêu cầu, thử tải open-loop/arrival-rate có kiểm soát và ghi cả queue/timeout.

JFR hữu ích để tương quan thời điểm xảy ra GC, safepoint, thread scheduling, CPU, allocation phía Java và blocking events. JFR thông thường **không phải bộ theo dõi mọi malloc của thư viện C**; nếu nguồn chậm nằm sâu bên native, dùng trace/metrics/profiler native và so timestamp tương ứng.

## 4. Thu thập ba lớp số liệu trên JDK 17 và Linux

### 4.1. NMT: HotSpot dùng bao nhiêu native memory?

Khởi động **tiến trình JVM cần đo** với NMT từ đầu:

~~~bash
java -XX:NativeMemoryTracking=summary -jar your-service.jar
~~~

Ở terminal khác, lấy PID của cùng JVM và lập baseline **sau warm-up**:

~~~bash
jcmd -l
jcmd <PID> VM.native_memory summary
jcmd <PID> VM.native_memory baseline
# Chờ chạy một khoảng dưới workload có kiểm soát.
jcmd <PID> VM.native_memory summary.diff
~~~

Trong lệnh thật, thay **<PID>** bằng số PID; dấu ngoặc nhọn chỉ là ký hiệu minh họa, không gõ nguyên xi vào shell. Với trường hợp cần truy allocation site của HotSpot, khởi động lại bằng **-XX:NativeMemoryTracking=detail** rồi dùng **VM.native_memory detail** và **detail.diff**. Không thể bật NMT đã tắt chỉ bằng một lệnh jcmd sau khi JVM chạy. NMT có overhead cần cân nhắc khi so số liệu latency; nên so với cấu hình đo kiểm nhất quán.

**Đọc kết quả đúng:** nhìn riêng committed/reserved, category như Thread, Class, Code, GC và biến động sau baseline. Theo tài liệu NMT của Oracle JDK 17, NMT chủ yếu theo dõi vùng nhớ nội bộ HotSpot, **không theo dõi đầy đủ allocation của JNI/third-party native libraries hoặc mọi JDK class library**. Vì vậy NMT phẳng không loại trừ một leak ở malloc của thư viện do bạn viết.

### 4.2. OS: footprint và file descriptors

Trên Linux, kiểm tra một tiến trình đang chạy (thay PID thực):

~~~bash
pid=12345
awk '/^(VmRSS|VmHWM|VmSize|Threads):/ {print}' \
  "/proc/$pid/status"
awk '/^(Rss|Pss|Private_Clean|Private_Dirty):/ {print}' \
  "/proc/$pid/smaps_rollup"
find "/proc/$pid/fd" -mindepth 1 -maxdepth 1 -type l 2>/dev/null | wc -l
grep 'Max open files' "/proc/$pid/limits"
~~~

**VmRSS** là resident set hiện tại, **VmHWM** là peak RSS của tiến trình; **Pss** phân chia trang shared cho các process cùng sử dụng; tổng các loại Private_Clean/Private_Dirty giúp ước lượng phần riêng. Các file **/proc** yêu cầu quyền truy cập phù hợp, tùy phiên bản kernel/container. **/proc/PID/fd** liệt kê FD mà process đang giữ; số đếm có thể thay đổi trong lúc công cụ quét. Có thể dùng **lsof -p PID** để xác định loại FD/path/socket đang nhiều lên, nhưng output lsof cần diễn giải đúng cột và không mặc định mọi hàng là một FD riêng biệt.

Trong container, ghi thêm **memory.current** và **memory.stat** của cgroup v2 khi có quyền. Hạn mức cgroup có thể tính cả page cache và các process khác; không đánh đồng nó với RSS của một JVM.

### 4.3. BufferPoolMXBean, FD MXBean và JFR

Trong Java, **java.lang.management.BufferPoolMXBean** có **getCount()**, **getMemoryUsed()** và **getTotalCapacity()** cho các pool (thường có direct/mapped). Đó là **ước lượng**; getMemoryUsed có thể trả **-1** khi không có ước lượng. Trên JDK/OS Unix được hỗ trợ, **com.sun.management.UnixOperatingSystemMXBean.getOpenFileDescriptorCount()** cho biết số FD đang mở trong tiến trình, không phải tất cả native handles. Trên môi trường khác phải dùng adapter OS phù hợp.

Ví dụ JFR cho một JVM dịch vụ đang chạy:

~~~bash
jcmd <PID> JFR.start name=NativeObserve settings=default disk=true \
  maxage=30m maxsize=128m
# Khi cần điều tra một khoảng thời gian:
jcmd <PID> JFR.dump name=NativeObserve filename=native-observe.jfr
# Khi không cần giữ recording nữa:
jcmd <PID> JFR.stop name=NativeObserve
~~~

Dùng recording **default** cho quan sát kéo dài, profile cho đợt điều tra ngắn cần thêm chi tiết. Chọn kích thước/maxage, nơi lưu và chi phí quan sát tương ứng với production. Thu metric tự viết cùng mốc UTC và monotonic elapsed để ghép với JFR/OS; không đọc clock giữa tiến trình bằng cách trừ trực tiếp hai giá trị System.nanoTime từ các JVM khác nhau.

## 5. Ví dụ Java 17 + JNI C11: đo native live bytes, handles logic và p95/p99

Mục tiêu của ví dụ nhỏ này là cho thấy **instrumentation tại đúng API cấp phát/giải phóng**. Java gọi C để malloc/free một block native; C quản lý hai atomic gauge **liveBlocks/liveBytes**. Java giữ lại có chủ đích 1/100 block để thấy đường đi của active resources, sau đó đóng hết. Cùng lúc Java thu khoảng thời gian mở/đóng (microseconds), ước lượng direct-buffer bytes và số FD nếu JVM/OS hỗ trợ.

**Lưu ý mô hình:** Giá trị trả về kiểu long chỉ là handle opaque; Java không tự dereference địa chỉ. Ví dụ có **một owner thread** cho từng Block và không cho alias. Nếu thư viện native có thread dùng cùng pointer, cần quản lý in-flight/reference count trước khi free. Hai atomic gauge độc lập chỉ phù hợp quan sát xấp xỉ khi concurrent, không phải một snapshot nguyên tử đa biến.

**Tệp NativeSoak.java**

~~~java
import com.sun.management.UnixOperatingSystemMXBean;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Deque;
import java.util.Locale;

public final class NativeSoak {
    static {
        System.loadLibrary("nativesoak");
    }

    private static native long allocate(int bytes);
    private static native void release(long address);
    private static native long liveBlocks();
    private static native long liveBytes();

    private static final class Block implements AutoCloseable {
        private long address;

        Block(int size) {
            address = allocate(size);
            if (address == 0) {
                throw new IllegalStateException("No native address");
            }
        }

        @Override
        public synchronized void close() {
            long old = address;
            if (old != 0) {
                address = 0;
                release(old);
            }
        }
    }

    private static long directMemoryUsed() {
        for (BufferPoolMXBean pool
                : ManagementFactory.getPlatformMXBeans(
                        BufferPoolMXBean.class)) {
            if ("direct".equals(pool.getName())) {
                return pool.getMemoryUsed();
            }
        }
        return -1; // Không có pool/ước lượng khả dụng.
    }

    private static long openFileDescriptors() {
        var os = ManagementFactory.getOperatingSystemMXBean();
        if (os instanceof UnixOperatingSystemMXBean unix) {
            return unix.getOpenFileDescriptorCount();
        }
        return -1; // Không hỗ trợ từ nền tảng hiện tại.
    }

    private static double percentileUs(
            long[] nanos, int from, int to, double q) {
        long[] sorted = Arrays.copyOfRange(nanos, from, to);
        Arrays.sort(sorted);
        int position = (int) Math.ceil(q * sorted.length) - 1;
        return sorted[position] / 1_000.0;
    }

    private static void report(
            String label, long[] samples, int from, int to) {
        System.out.printf(Locale.ROOT,
            "%s ops=%d active=%d bytes=%d directBytes=%d "
                + "fds=%d p95_us=%.2f p99_us=%.2f%n",
            label, to - from, liveBlocks(), liveBytes(),
            directMemoryUsed(), openFileDescriptors(),
            percentileUs(samples, from, to, 0.95),
            percentileUs(samples, from, to, 0.99));
    }

    public static void main(String[] args) {
        final int blockSize = 8192;
        final int total = 10_000;
        final int window = 2500;
        Deque<Block> retained = new ArrayDeque<>();

        // Warm-up không ghi vào tập mẫu, để thư viện/JIT khởi động.
        for (int i = 0; i < 2000; i++) {
            try (Block ignored = new Block(blockSize)) {
                // Chỉ đo vòng đời native allocation.
            }
        }

        long[] nanos = new long[total];
        try {
            for (int i = 0; i < total; i++) {
                long start = System.nanoTime();
                Block block = new Block(blockSize);

                if (i % 100 == 0) {
                    retained.addLast(block);
                } else {
                    block.close();
                }

                nanos[i] = System.nanoTime() - start;

                if ((i + 1) % window == 0) {
                    report("window", nanos, i + 1 - window, i + 1);
                }
            }

            System.out.printf(
                "before_cleanup active=%d bytes=%d%n",
                liveBlocks(), liveBytes());
        } finally {
            while (!retained.isEmpty()) {
                retained.removeFirst().close();
            }
        }

        System.out.printf(
            "after_cleanup active=%d bytes=%d%n",
            liveBlocks(), liveBytes());
    }
}
~~~

**Tệp nativesoak.c**

~~~c
#include <jni.h>
#include <stdint.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdlib.h>

typedef struct {
    size_t size;
    unsigned char payload[];
} NativeBlock;

static _Atomic long active_blocks = 0;
static _Atomic long active_bytes = 0;

static void throw_java(JNIEnv *env, const char *type,
                       const char *message) {
    jclass exceptionClass = (*env)->FindClass(env, type);
    if (exceptionClass != NULL) {
        (*env)->ThrowNew(env, exceptionClass, message);
        (*env)->DeleteLocalRef(env, exceptionClass);
    }
}

JNIEXPORT jlong JNICALL
Java_NativeSoak_allocate(JNIEnv *env, jclass cls, jint bytes) {
    (void)cls;
    if (bytes <= 0) {
        throw_java(env, "java/lang/IllegalArgumentException",
                   "bytes must be positive");
        return 0;
    }

    size_t n = (size_t)bytes;
    if (n > SIZE_MAX - sizeof(NativeBlock)) {
        throw_java(env, "java/lang/OutOfMemoryError",
                   "native size overflow");
        return 0;
    }

    NativeBlock *block = malloc(sizeof(NativeBlock) + n);
    if (block == NULL) {
        throw_java(env, "java/lang/OutOfMemoryError",
                   "native malloc failed");
        return 0;
    }

    block->size = n;
    block->payload[0] = (unsigned char)(n & 0xffu);

    // Chỉ đếm tài nguyên của API này, không đếm toàn bộ process.
    atomic_fetch_add_explicit(
        &active_blocks, 1, memory_order_relaxed);
    atomic_fetch_add_explicit(
        &active_bytes, (long)n, memory_order_relaxed);
    return (jlong)(intptr_t)block;
}

JNIEXPORT void JNICALL
Java_NativeSoak_release(JNIEnv *env, jclass cls, jlong address) {
    (void)env;
    (void)cls;
    if (address == 0) {
        return;
    }

    NativeBlock *block = (NativeBlock *)(intptr_t)address;
    long n = (long)block->size;
    free(block);

    atomic_fetch_sub_explicit(
        &active_bytes, n, memory_order_relaxed);
    atomic_fetch_sub_explicit(
        &active_blocks, 1, memory_order_relaxed);
}

JNIEXPORT jlong JNICALL
Java_NativeSoak_liveBlocks(JNIEnv *env, jclass cls) {
    (void)env;
    (void)cls;
    return (jlong)atomic_load_explicit(
        &active_blocks, memory_order_relaxed);
}

JNIEXPORT jlong JNICALL
Java_NativeSoak_liveBytes(JNIEnv *env, jclass cls) {
    (void)env;
    (void)cls;
    return (jlong)atomic_load_explicit(
        &active_bytes, memory_order_relaxed);
}
~~~

**Biên dịch/chạy trên Linux x86-64 với JDK 17+ và GCC hỗ trợ C11** (JAVA_HOME trỏ đến JDK):

~~~bash
javac -h . NativeSoak.java
gcc -std=c11 -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libnativesoak.so nativesoak.c
java -Djava.library.path=. NativeSoak
~~~

**Hai dòng kiểm tra có kết quả xác định khi chạy thành công:**

~~~text
before_cleanup active=100 bytes=819200
after_cleanup active=0 bytes=0
~~~

Bốn dòng **window** được in trước hai dòng này; giá trị **p95_us/p99_us, fds, directBytes** phụ thuộc JVM, lịch chạy và OS nên không có stdout cố định đáng tin cho các dòng đó. Chương trình không tạo một leak thực sự: nó **giữ 100 block trong giai đoạn thử tải rồi release tất cả trong finally**. Số 100 là 10.000 / 100; mỗi block có 8.192 byte → 819.200 byte. Gauge chỉ đo bộ nhớ do hai API allocate/release này quản lý, không thay thế RSS, NMT hoặc native profiler.

Ví dụ này đo thời gian cấp phát **kèm thao tác release Java→JNI** và một tỷ lệ retention có chủ đích; nó không phải benchmark throughput/latency end-to-end của một dịch vụ sản xuất. Nếu máy không hỗ trợ UnixOperatingSystemMXBean, giá trị **fds=-1** mang nghĩa “không có dữ liệu”, tuyệt đối không diễn giải là 0 FD. **NativeSoak.release** giả định handle hợp lệ, đúng owner, chưa free; raw pointer bị dùng trùng ở một wrapper khác sẽ gây lỗi native nghiêm trọng. Mẫu triển khai sản xuất nên dùng bảng handle kiểm tra generation/id và phối hợp với tác vụ đang chạy, thay vì xuất con trỏ raw.

## 6. Nâng ví dụ thành thử nghiệm chạy lâu (soak test)

Một vòng lặp 10.000 operation chỉ kiểm tra cơ chế; phát hiện leak chậm đòi hỏi **thời gian** và **khối lượng workload đại diện**. Với service có JNI thật, giữ nguyên cấu hình JVM/GC, phiên bản thư viện, CPU/memory limit, allocator, traffic mix và số worker để các lần đo có thể so sánh.

### Kịch bản đề nghị

| Pha | Điều kiện | Cần thu và so sánh |
| --- | --- | --- |
| 1. Khởi động/warm-up | Nạp thư viện native, JIT, khởi tạo pool, cache | Chờ metric ổn định; phân biệt tăng khởi tạo với leak. |
| 2. Baseline | Tải thấp hoặc tải chuẩn ổn định | RSS/PSS, NMT committed/reserved, direct pool, live bytes, active handles/FD, p95/p99, throughput, error rate. |
| 3. Steady load | Chạy nhiều giờ cùng arrival rate/concurrency | Xu hướng live resources, độ dốc RSS, số FD, tail latency; lưu sample cùng timestamp. |
| 4. Burst/peak | Tăng tải trong giới hạn dự kiến | Peak handle/memory, allocator behavior, p99, timeout và thời gian hồi phục. |
| 5. Cooldown | Trả về **cùng mức tải** ở baseline, rồi dừng tác vụ còn pending | So active resources với baseline; RSS có thể chưa thu hẹp dù live giảm. |
| 6. Graceful shutdown | Chờ in-flight = 0 rồi release hết owner-managed resources | Đếm opens/closes và bytes còn sống; kiểm tra error/close failures. |

Ví dụ cadence thực tế có thể là metric 1–10 giây và snapshot NMT/OS mỗi 1–5 phút, nhưng phải điều chỉnh theo tốc độ lỗi và chi phí lấy mẫu. Chỉ số đuôi nên được tính từ histogram trên từng cửa sổ rõ ràng. Lưu cả **workload offered/accepted/completed**, số request đang chờ và phân loại kết quả; nếu lượng request đến thay đổi thì trend bộ nhớ tuyệt đối có thể không so sánh được.

Để phát hiện **retained leak**, đo trạng thái sau khi xử lý hết in-flight ở **cùng điều kiện**. Ví dụ:
- Baseline: 100 active handle vì pool thường trực; sau 6 giờ cùng tải, liên tục tăng lên 1.300 và không quay lại ~100 → cần điều tra đường thiếu close.
- Bản đồ memory sống không tăng, nhưng RSS lên rồi giữ plateau sau burst → có thể là allocator cache, fragmentation, mappings, JVM heap commitment. Cần thêm bằng chứng trước khi gọi là leak.
- Với mỗi cửa sổ, so **live_bytes / số tác vụ đang hoạt động** và **mức thay đổi sau cooldown**; cùng workload nhưng trend dương kéo dài đáng nghi hơn một mức RSS cao đơn lẻ.

### Thu chuỗi OS đơn giản ở Linux

Với một PID đã xác định, chỉ dùng script dưới đây để quan sát **cùng tiến trình**, không nhầm sang JVM khác. Sampling FD là xấp xỉ vì các open/close có thể xảy ra trong lúc liệt kê:

~~~bash
pid=12345
while kill -0 "$pid" 2>/dev/null; do
  date -Is
  awk '/^(VmRSS|VmHWM|Threads):/ {print}' \
    "/proc/$pid/status"
  printf 'open_fds='
  find "/proc/$pid/fd" -mindepth 1 -maxdepth 1 -type l \
    2>/dev/null | wc -l
  sleep 60
done
~~~

Đưa output vào hệ thống metrics/log đã có nếu cần theo dõi dài hạn; kèm process ID, thời điểm deploy, JVM version và phiên bản native library. Theo dõi tỷ lệ sample bị lỗi/không có quyền; nếu một nguồn metric không khả dụng, cần thể hiện unknown thay vì biến giá trị thành 0.

## 7. Diễn giải tín hiệu: loại bất thường nào đang xảy ra?

| Quan sát cùng khoảng thời gian | Giả thuyết ưu tiên | Kiểm tra tiếp |
| --- | --- | --- |
| Java heap gần ổn định; RSS tăng; counter native_live_bytes tăng sau cooldown | Bỏ quên free/handle ở library native | Ghép allocation stack/call site, mở/đóng theo operation, tìm đường exception/cancel. |
| RSS tăng; NMT committed tăng rõ ở Thread | Số thread hoặc thread stack tăng | Thread count, JFR, stack traces, thread pool và shutdown. |
| RSS tăng; NMT gần phẳng; direct pool phẳng | Native allocation ngoài HotSpot hoặc mapping/fragmentation | Custom counters, /proc/PID/smaps_rollup, native heap profiler, malloc tracing ở môi trường kiểm soát. |
| FD count tăng đều nhưng native malloc counters ổn định | Socket/file/pipe/eventfd không được đóng | lsof, /proc/PID/fd, Java/native resource ownership, close/error paths. |
| Custom native_handles_open tăng nhưng OS FD không đổi | Opaque handle của thư viện không đại diện cho FD | Log/metrics của API create/release, kiểm tra callback/child owners. |
| p99 tăng theo active handles/in-flight; CPU không quá cao | Queueing, contention, lock hoặc I/O backlog | Timer từng giai đoạn native, thread state, queue length, timeout. |
| p99 spike trùng GC/safepoint | Pauses phía JVM ảnh hưởng end-to-end | JFR/GC logs, allocation rate, thời lượng pause; không vội kết luận C chậm. |
| RSS ở plateau cao sau load nhưng native_live_bytes trở về mức cũ | Allocator cache/fragmentation hoặc bộ nhớ HotSpot còn committed | So PSS, NMT, mmap/allocator stats, kiểm tra xu hướng qua nhiều chu kỳ. |
| Active handle sụt nhưng lỗi double-free/crash | Sai ownership/alias; close đua với tác vụ đang dùng | Generation-safe handle registry, refcount/in-flight guard, sanitizer phù hợp native. |

Không kết luận nguyên nhân từ một đồ thị. Ví dụ “RSS tăng trong khi NMT ổn định” chỉ **gợi ý** thứ nằm ngoài phạm vi NMT; phải kết hợp live allocations, direct buffer, mmap, native profiler và khối lượng hoạt động. **Heap dump** không hiện đầy đủ payload đã malloc nhưng có thể cho biết Java wrapper nào còn giữ reference đến native resource.

## 8. Các bẫy trong đo lường kéo dài

**Observer effect:** Mỗi debug log, stack trace allocation và profiler đều tốn CPU/RAM; NMT detail và JFR profile có thể đổi tail latency. Đo overhead riêng và dùng chính sách sampling hợp lý trước khi đem số trong môi trường debug so với production.

**Sai mốc và sai mẫu:** So RSS đầu ngày lúc idle với RSS cuối ngày lúc peak tạo kết luận lệch. Percentile 99 trên vài chục lời gọi không có độ phân giải ý nghĩa. Mẫu chỉ lấy request success bỏ quên timeout; số thống kê có thể đẹp hơn trong đợt lỗi.

**GC và Cleaner:** ByteBuffer/Java wrapper có thể đã unreachable nhưng native cleanup chưa chạy. Không dùng System.gc() làm cơ chế cleanup của thiết kế; một lần ép GC trong bài test có thể giúp phân biệt retain qua Java wrapper nhưng làm sai nhịp vận hành bình thường. Dùng close xác định và báo metric release thực tế.

**Allocator reuse:** free có thể đưa block về cache/tcache/arena mà không hạ RSS; native memory fragmentation có thể làm footprint tăng dù live bytes ổn định. Quan sát OS mapping/allocator stats và các chu kỳ tải đủ dài trước khi đánh giá.

**Race trong counters:** Nếu update native_live_bytes không atomic hoặc skip một đường lỗi, chính monitoring sẽ sai. Hai gauge được đọc rời rạc trong lúc concurrent có thể không khớp cùng một thời điểm; muốn snapshot nhất quán phải chụp dưới cùng lock/version protocol, không chỉ đọc hai atomic liên tiếp.

**Giới hạn handle:** Linux có per-process **RLIMIT_NOFILE** và system-wide limits; không lấy “số FD thấp hơn giới hạn” làm bảo chứng socket/pool không leak. Số FD có thể giảm tạm khi retry/connection timeout rồi tăng lại. Cần đo age, type, open/close rates và hoạt động của owner.

**JNI/FFM lifetime:** JNI local/global refs, native buffers và arena/MemorySegment có quy tắc sống riêng. Nếu thư viện giữ pointer sau khi Java scope đã kết thúc, sẽ có use-after-free dù counter RAM tạm ổn. Với JDK 22+ FFM, Arena.ofShared chỉ cho nhiều thread truy cập trong phạm vi hợp lệ, không tự bảo đảm thread safety hoặc tự đếm malloc tùy ý của bên C.

**Lỗi lúc shutdown:** Cần chờ native thread/callback/in-flight về 0 trước khi giải phóng. Kiểm tra timeout, exception, cancellation, retry, partial initialization, close được gọi nhiều lần và đường dừng do deploy; đó thường là những nơi bỏ sót cleanup.

## 9. Quy trình điều tra và tiêu chí hoàn thành

1. **Xác định scope:** JVM/OS nào, phiên bản thư viện native nào, loại handle/operation nào; ghi rõ owner tài nguyên và contract close.
2. **Lập baseline sau warm-up:** chụp heap + direct pool + NMT + OS RSS/PSS + FD/custom handles + histogram latency cùng điều kiện tải.
3. **Lấy chuỗi thời gian có timestamp:** đo theo cửa sổ, có count/throughput/errors/in-flight; giữ lại điểm peak và dữ liệu cooldown.
4. **Tìm divergence:** nếu native_live tăng mà GC heap không tăng, tìm API allocate/free; nếu FD tăng, tìm các open/close; nếu p99 tăng, so queue/GC/native timer.
5. **Tái hiện có kiểm soát:** tăng số vòng, traffic mix, cancellation, timeouts, burst và shutdown. Có thể cố ý giữ resource trong một thử nghiệm nhỏ như ví dụ để xác nhận cảnh báo.
6. **Sửa tại owner và chạy lại cùng workload:** thêm close/finally, xử lý vòng đời callback/thread hoặc giảm contention; không chỉ thêm GC/restart định kỳ để che lỗi.
7. **Đặt regression gate:** sau cùng thời gian/cùng tải, active resource không trôi liên tục, không có close error, giới hạn FD/memory còn headroom, p99/error rate nằm trong SLO được phê duyệt.

Một tiêu chí tham khảo cần **định lượng theo hệ thống**: sau soak đủ dài và cooldown, **outstanding native allocations/handles** quay về baseline trong biên dao động chấp nhận được; không có xu hướng tăng kéo dài khi normalize theo workload; p99 và tỷ lệ timeout ổn định trong budget; các metric vẫn tồn tại khi native/JVM lỗi. Ngưỡng số học cụ thể phụ thuộc loại dịch vụ, không nên áp một mức MiB/phút hoặc p99 chung cho mọi dự án.

## 10. Câu hỏi tự kiểm tra

1. Vì sao NMT summary.diff có thể không thay đổi trong lúc một thư viện JNI gọi malloc liên tục không free?
2. Khi directBuffer getMemoryUsed và RSS khác nhau, tại sao không thể lấy số lớn hơn làm “native live bytes”?
3. Nếu native malloc được free nhưng RSS giữ nguyên sau cooldown, những dữ liệu nào bạn cần trước khi kết luận leak?
4. OS FD đếm không tăng nhưng active opaque handles do C library tăng; bạn nên đặt metric ở đâu?
5. Tại sao p99 của request **thành công** có thể giảm trong cùng lúc timeout rate tăng?
6. Ví dụ NativeSoak vì sao phải đóng các Block giữ lại trong finally; khi nào synchronized close vẫn chưa đủ để ngăn use-after-free?
7. Làm thế nào để chứng minh lỗi là do native lock/queue thay vì GC, OS page fault hoặc phối hợp thread Java?
8. Vì sao phải so baseline và cooldown dưới cùng mức tải và cùng phiên bản JVM/native library?

**Nguyên tắc cốt lõi:** Quan sát lâu dài chỉ đáng tin khi đo được *vòng đời tài nguyên tại owner* và *footprint thực của process* đồng thời với *phân phối latency và workload*. RSS/NMT/FD/histogram bổ sung cho nhau, không cái nào riêng lẻ chứng minh ứng dụng JNI không leak hoặc không bị tăng tail latency.

## Tài liệu tham khảo

- [Oracle JDK 17 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html): phạm vi HotSpot, summary/detail, baseline/diff, overhead.
- [Oracle JDK 17 — jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): VM.native_memory, JFR.start/dump/stop.
- [Java 17 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): số lượng, capacity và ước lượng memoryUsed.
- [Java 17 — UnixOperatingSystemMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/UnixOperatingSystemMXBean.html): số file descriptors trên Unix.
- [Oracle JDK 17 — JNI Function Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): quy tắc JNI, reference và native interface.
- [Linux proc(5) — /proc/PID/status, smaps và fd](https://man7.org/linux/man-pages/man5/proc.5.html): dữ liệu về tiến trình và bộ nhớ.
