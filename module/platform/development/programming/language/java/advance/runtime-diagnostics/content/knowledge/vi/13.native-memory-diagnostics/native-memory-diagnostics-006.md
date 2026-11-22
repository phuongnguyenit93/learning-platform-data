# 13.6 Giới hạn NMT: phạm vi HotSpot và các cấp phát native không được theo dõi

## 1. Khi RSS tăng mà NMT gần như đứng yên

Giả sử một dịch vụ Java tăng RSS từ 700 MiB lên 1.100 MiB sau nhiều giờ. Kết quả `jcmd <PID> VM.native_memory summary.diff` lại cho thấy `Total committed` của NMT chỉ tăng 15 MiB. Có chắc 385 MiB còn lại là “rò rỉ native”?

**Chưa thể kết luận như vậy.** Native Memory Tracking (**NMT**) là công cụ của **HotSpot VM** theo dõi những đường cấp phát bộ nhớ mà HotSpot quản lý. Nó không phải trình theo dõi tất cả lời gọi `malloc`, `mmap` hoặc những cấp phát do thư viện C/C++ được nạp vào cùng tiến trình thực hiện. Hơn nữa, NMT `committed` và RSS là hai đại lượng có định nghĩa khác nhau; không được lấy hiệu của chúng làm số byte rò rỉ chính xác.

Người học cần trả lời được: NMT thấy phần bộ nhớ nào; phần nào nằm ngoài phạm vi; cách diễn giải `reserved/committed`; cách đối chiếu với RSS/PSS và các vùng mapping; khi nào phải dùng công cụ native ngoài `jcmd`; và làm sao chứng minh leak thay vì chỉ suy đoán.

## 2. NMT theo dõi được và không theo dõi được những gì?

NMT là khả năng chẩn đoán đặc thù của HotSpot, mặc định tắt và phải bật lúc **khởi động JVM**. Hai cấp độ:

- `-XX:NativeMemoryTracking=summary`: báo cáo số liệu theo nhóm subsystem của VM, với `reserved` và `committed`.
- `-XX:NativeMemoryTracking=detail`: thêm call sites và virtual memory regions của **những cấp phát đã được NMT instrument**. Nó không thu thập mọi native allocation của toàn process.

Các nhóm điển hình là `Java Heap`, `Class`/metaspace, `Thread`, `Code`, `GC`, `Compiler`, `Internal`, `Symbol`, `Other` và `Native Memory Tracking`. Tên, số nhóm và mức độ chi tiết phụ thuộc bản JDK. Sự hiện diện của một nhóm không có nghĩa mọi cấp phát liên quan đến Java hay thư viện chuẩn đều vào nhóm đó.

| Nguồn bộ nhớ | Mức độ NMT quan sát | Không được suy diễn |
| --- | --- | --- |
| Java heap do HotSpot reserve/commit | NMT hiển thị vùng `reserved` và `committed` của VM heap | Không phải `heap used`, live objects hay heap dump |
| HotSpot class metadata/metaspace, code cache, GC structures, một phần thread/stacks và VM runtime | Có các nhóm NMT tương ứng khi cấp phát qua đường VM được instrument | Không bao gồm mặc nhiên mọi byte do Java library/OS cấp phát |
| `malloc`/`mmap` qua bộ cấp phát nội bộ HotSpot có NMT instrumentation | `summary` ghi tổng; `detail` có thông tin call site/region | Không tương đương với profiler của libc `malloc` toàn tiến trình |
| JNI/JNA/native plugin gọi trực tiếp libc `malloc`, `calloc`, `realloc`, `mmap` hoặc allocator riêng | **Nằm ngoài phạm vi bảo đảm theo dõi của NMT HotSpot** | Không thể mặc định sẽ xuất hiện ở mục `Other` |
| Native allocation trong JDK class libraries, CDS archive và giai đoạn khởi động rất sớm | Tài liệu Oracle ghi nhận các **khoảng không được bao phủ đầy đủ** | Không khẳng định toàn bộ API JDK luôn được đếm hoặc luôn bị bỏ sót |
| RSS/PSS/Working Set/cgroup memory | Cần lấy từ OS/container | Không thể đọc trực tiếp từ NMT `Total committed` |

**Quan trọng:** `Other` là nhóm dành cho *những cấp phát HotSpot đã nhận diện được nhưng không khớp nhóm VM chuyên biệt*, không phải nơi gom toàn bộ memory của JNI/third-party libraries. `detail` cũng không truy ngược stack của một allocation mà NMT chưa từng thấy.

Với `ByteBuffer.allocateDirect`, `Unsafe`, JDK native library hoặc Foreign Function & Memory API, **đừng quyết định “tracked/untracked” chỉ theo tên API**: đường cấp phát có thể thay đổi theo implementation/JDK build. Có allocation đi qua VM và được NMT ghi nhận, có allocation đi thẳng vào thư viện native. Cách đúng là kiểm chứng trên **chính JVM và đường code đang dùng**.

### Giới hạn vận hành

1. NMT **off mặc định**. Khi JVM chạy với NMT off, `jcmd` không bật mới/restart được NMT; phải restart JVM với cấu hình phù hợp.
2. `summary` không thể nâng mức lấy call site lên `detail` chỉ bằng lệnh `jcmd` trong lúc chạy; cần chọn detail từ startup.
3. NMT có chi phí: tài liệu Oracle nêu overhead hiệu năng khoảng **5–10%** trong một số tình huống và metadata bộ nhớ bổ sung; đo trên hệ thống thật phải có kế hoạch.
4. Không có bao phủ hoàn toàn cho CDS archive, một số cấp phát khởi động sớm và native code ngoài HotSpot; cách phân nhóm có thể đổi qua JDK.
5. **NMT tăng không đồng nghĩa leak.** JVM có thể tăng heap committed, code cache, metaspace, GC structures hoặc thread stacks theo tải, rồi giữ lại để tái sử dụng.
6. **NMT không tăng không chứng minh process không leak.** Nó chỉ nói phần HotSpot mà NMT theo dõi chưa cho thấy mức tăng tương ứng.

## 3. Phân biệt reserved, committed, RSS, PSS và heap used

| Đại lượng | Nó đo điều gì? | Bẫy suy luận |
| --- | --- | --- |
| NMT `reserved` | Phạm vi **không gian địa chỉ ảo** dành trước cho vùng JVM quản lý | Đặt trước 2 GiB không có nghĩa đang dùng 2 GiB RAM |
| NMT `committed` | Phần vùng được HotSpot/OS ghi nhận đã commit/backing; gồm cả VM `malloc` mà NMT theo dõi | Không bằng số trang thực sự resident, càng không đại diện tất cả native code |
| Linux RSS (`VmRSS`) | Các trang bộ nhớ thực cư trú được gán cho process, gồm cả shared mappings | Shared pages có thể xuất hiện trong RSS của nhiều process |
| PSS trong `/proc/<PID>/smaps_rollup` | Resident memory chia tỷ lệ với số process cùng map trang shared | Khác RSS và không thay được ownership/allocation-stack |
| `heap used` hoặc live set | Dung lượng Java objects đang sử dụng/được giữ sau GC | Không bằng NMT `Java Heap committed` |
| cgroup v2 `memory.current` | Bộ nhớ được charge cho cgroup, có thể gồm page cache, kernel memory, nhiều process | Không phải RSS của riêng PID Java |

Ví dụ JVM dùng `-Xms256m -Xmx2g` có thể **reserve** gần 2 GiB heap nhưng ban đầu chỉ **commit** một phần. NMT `Java Heap` thể hiện vùng JVM quản lý, không liệt kê từng Java object. Sau GC, `heap used` có thể giảm trong khi `committed` còn cao; điều đó chưa phải leak.

Một bảng giả định:

| Mốc đo | NMT `Total committed` | RSS |
| --- | ---: | ---: |
| `t0`, sau warm-up | 520 MiB | 690 MiB |
| `t1`, sau 20 phút tải tương đương | 530 MiB | 940 MiB |
| Delta | +10 MiB | +250 MiB |

Nhận định có căn cứ: “Phần tăng RSS **không được giải thích bởi xu hướng NMT committed**; cần xem các trang resident và bộ nhớ do thư viện native/OS hạch toán.” Nhận định thiếu căn cứ: “Đã xác định leak 240 MiB trong JNI”. `250 - 10` không phải số byte untracked chính xác, vì reservation/commit, page residency, shared/file mappings, allocator caches và thay đổi tải ảnh hưởng phép so sánh.

## 4. Thu thập dữ liệu NMT đúng phương pháp

### 4.1 Bật lúc startup

~~~bash
# Chọn MỘT mức khi khởi động:
java -XX:NativeMemoryTracking=summary -jar app.jar
# Hoặc:
java -XX:NativeMemoryTracking=detail -jar app.jar
~~~

Hai dòng là **hai lựa chọn độc lập**, không chạy đồng thời cho cùng tiến trình. Mức `detail` chi tiết hơn nhưng có thể gây overhead cao hơn. Ghi lại JDK vendor/build, PID, container quota, workload và mốc thời gian. Dùng `jcmd` tương thích với JVM và tài khoản đủ quyền attach.

### 4.2 Baseline sau warm-up, rồi so delta

~~~bash
jcmd <PID> VM.native_memory summary scale=MB
jcmd <PID> VM.native_memory baseline
# Sau khi tái hiện giai đoạn tăng RSS:
jcmd <PID> VM.native_memory summary.diff scale=MB
~~~

Nếu **đã khởi động bằng detail**, có thể dùng thêm:

~~~bash
jcmd <PID> VM.native_memory detail scale=MB
jcmd <PID> VM.native_memory detail.diff scale=MB
~~~

Thay `<PID>` bằng PID thật. Baseline nên được chốt **sau khi JVM/app warm-up**, trước khoảng đo cần điều tra. So sánh trên cùng PID, workload và JDK, chụp nhiều mốc thay vì một snapshot. `summary.diff`/`detail.diff` thể hiện thay đổi **trong phạm vi HotSpot được theo dõi**, không đo mọi `malloc` ở thư viện ngoài.

Đọc các nhóm cho đúng:

- `Java Heap` tăng committed: JVM mở rộng heap. Muốn biết Java objects giữ gì cần GC/live set, heap histogram hoặc heap dump.
- `Class`/`Code` tăng: kiểm tra class loading, metaspace hoặc JIT code cache trước khi gọi là leak.
- `Thread` tăng: có thể do **platform thread** và native stacks liên quan; không quy một virtual thread thành một native stack.
- `GC`/`Internal`/`Native Memory Tracking` tăng: xem cơ chế VM hoặc overhead của công cụ.
- `malloc`/`mmap`/`arena` ở detail: chỉ những đường mà HotSpot đã instrument; các arena có thể được quản lý theo khối.

`jcmd <PID> VM.native_memory shutdown` dừng theo dõi nhưng **không thể bật lại NMT bằng jcmd**. Không dùng shutdown khi còn cần các snapshot trong cùng phiên.

## 5. Đối chiếu OS khi NMT có khoảng trống

Trên Linux, dùng **cùng PID, cùng timestamp** với báo cáo NMT:

~~~bash
# Thay 12345 bằng PID Java thực tế; chạy trên host/namespace nhìn thấy PID.
PID=12345
ps -o pid,rss,vsz,comm -p "$PID"
grep -E '^VmRSS:|^VmSize:|^RssAnon:|^RssFile:' "/proc/$PID/status"
cat "/proc/$PID/smaps_rollup"
pmap -x "$PID"
~~~

`ps rss` và `VmRSS` thường là KiB. `smaps_rollup` hiển thị tổng RSS/PSS; `/proc/<PID>/smaps` giúp truy theo mapping cụ thể: anonymous/private, file-backed, shared libraries, thread stacks, allocator mappings. `VmSize/VSZ` là vùng địa chỉ ảo, không phải RAM resident. Có thể cần quyền đọc `/proc` hoặc namespace phù hợp.

Với cgroup **v2**:

~~~bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events
~~~

Cgroup có thể gồm nhiều process, page cache và memory charges khác; không đồng nhất cgroup memory với RSS của một PID. Trong Kubernetes, cần kiểm tra pod/container namespace, OOMKilled, sidecar và quota. Trên Windows so Private Bytes/Working Set và memory mappings bằng Process Explorer/VMMap; trên macOS dùng `vmmap` và Instruments. Không giả định lệnh Linux chạy được ở mọi OS.

### Ma trận suy luận từ chuỗi thời gian

| Quan sát | Giả thuyết hợp lý | Dữ liệu cần bổ sung |
| --- | --- | --- |
| NMT `Class`/`Code`/`GC` committed tăng cùng RSS | VM mở rộng vùng nội bộ; có thể bình thường theo tải | Detail call sites, class count, compiler/GC behavior, thời điểm growth |
| NMT `Java Heap committed` tăng; RSS cũng tăng | Heap đang commit thêm | Heap used/live set, GC logs, histogram; chưa khẳng định Java leak |
| RSS tăng liên tục, NMT committed gần phẳng | Native allocations không được NMT bao phủ **hoặc** thay đổi residency/mapping/allocator | `smaps`, per-library allocation stats, malloc/free call stacks |
| NMT `reserved` tăng mạnh, RSS ổn định | Virtual address reservation tăng | `committed` và OS mapping; không gọi là RAM leak |
| Sau `free`/GC, RSS không giảm ngay | Allocator cache/arena fragmentation hoặc VM vẫn giữ committed memory | Live allocations, allocator stats, nhiều vòng lặp dùng/nhả |

Một **memory leak** được chứng minh khi những cấp phát **đáng lẽ đã hết vòng đời** vẫn còn live và tích lũy qua chu kỳ hoạt động. High-water mark, cache hợp lệ, arena giữ để tái sử dụng hoặc file-mapped pages vẫn có thể làm RSS cao mà không phải leak.

### Chọn công cụ theo phạm vi

- **HotSpot growth:** NMT `detail.diff`, class loading/GC/code-cache metrics.
- **Java object retention:** heap histogram, heap dump, JFR Java allocations khi thích hợp.
- **JNI/JNA/C/C++ `malloc/free` ngoài HotSpot:** instrument allocation/free, native allocator statistics, heaptrack, Valgrind Massif, LeakSanitizer/AddressSanitizer trên môi trường thử nghiệm, hoặc eBPF/uprobes/perf theo điều kiện hệ thống.
- **`mmap`/file mappings:** `smaps`/`pmap`, thông tin mapping và owner/lifecycle.
- **Thư viện dùng cache/arena riêng:** debug counters và profiling của chính thư viện (ví dụ jemalloc/tcmalloc nếu thực sự dùng).

Không thay thế câu hỏi “thư viện nào còn giữ allocation?” bằng một con số `Total committed`. OS cho biết *trang nằm đâu*; profiler cho biết *ai cấp phát và ai chưa giải phóng*; NMT cho biết *HotSpot đã quản lý gì*.

## 6. Lab Java 17+ và JNI: cấp phát native mà HotSpot NMT không theo dõi

Lab độc lập này dành cho **Linux 64-bit, JDK 17+ và GCC**, minh họa một thư viện C gọi libc `malloc`, ghi vào các trang để RSS tăng, giữ vùng 64 MiB trong khi đo, rồi `free`. Bản thân NMT vẫn hoạt động để giám sát HotSpot; nó không được thiết kế để ghi lại từng `malloc` của C library này.

### File `NmtBlindSpotLab.java`

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;

public final class NmtBlindSpotLab {
    private static final long BYTES = 64L * 1024 * 1024;

    private static native long mallocAndTouch(long bytes);
    private static native void nativeFree(long address);

    private static void pause(BufferedReader input, String prompt)
            throws IOException {
        System.out.println(prompt);
        if (input.readLine() == null) {
            throw new IOException("Run interactively from a terminal");
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && "--help".equals(args[0])) {
            System.out.println("Usage: java NmtBlindSpotLab");
            return;
        }

        System.loadLibrary("nmtblindspot");
        BufferedReader input = new BufferedReader(
                new InputStreamReader(System.in));
        System.out.println("PID=" + ProcessHandle.current().pid());
        pause(input, "BEFORE: collect NMT and RSS, then press Enter");

        long address = mallocAndTouch(BYTES);
        try {
            pause(input, "ALLOCATED 64 MiB: collect NMT and RSS, then press Enter");
        } finally {
            nativeFree(address);
        }
        pause(input, "FREED: collect NMT and RSS, then press Enter to exit");
    }
}
~~~

### File `nmtblindspot.c`

~~~c
#include <jni.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>

static void throw_java(JNIEnv *env, const char *name, const char *message) {
    jclass type = (*env)->FindClass(env, name);
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
    }
}

JNIEXPORT jlong JNICALL
Java_NmtBlindSpotLab_mallocAndTouch(
        JNIEnv *env, jclass owner, jlong requested) {
    (void)owner;
    if (requested <= 0 || (uint64_t)requested > SIZE_MAX) {
        throw_java(env, "java/lang/IllegalArgumentException", "Invalid size");
        return 0;
    }

    size_t size = (size_t)requested;
    volatile unsigned char *memory =
            (volatile unsigned char *)malloc(size);
    if (memory == NULL) {
        throw_java(env, "java/lang/OutOfMemoryError", "malloc failed");
        return 0;
    }
    for (size_t offset = 0; offset < size; offset += 4096) {
        memory[offset] = 0x5A;
    }
    memory[size - 1] = 0x5A;
    return (jlong)(intptr_t)memory;
}

JNIEXPORT void JNICALL
Java_NmtBlindSpotLab_nativeFree(
        JNIEnv *env, jclass owner, jlong address) {
    (void)env;
    (void)owner;
    free((void *)(intptr_t)address);
}
~~~

**Giải thích:** Java giữ một địa chỉ native dạng `long`; dữ liệu 64 MiB nằm ngoài Java `byte[]` heap. C gọi libc `malloc` trực tiếp; ghi ít nhất một byte trên mỗi trang 4 KiB để kích hoạt OS cấp resident pages thay vì chỉ reserve địa chỉ. Dùng `finally` để gọi `free` đúng một lần khi kết thúc giai đoạn đo. Trong hệ thống thực, cần thiết kế owner/handle an toàn thay vì phát tán con trỏ thô. Thí nghiệm giả định Linux x86_64/kiến trúc trang phổ biến; các con số OS vẫn có sai số.

Compile ở cùng thư mục hai file; `JAVA_HOME` phải trỏ đến JDK có `include/jni.h`:

~~~bash
javac -h . NmtBlindSpotLab.java
gcc -std=c11 -O0 -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -o libnmtblindspot.so nmtblindspot.c
java -XX:NativeMemoryTracking=detail \
  -Djava.library.path=. NmtBlindSpotLab
~~~

Chương trình in `PID=...` và chờ ở thông báo `BEFORE`. Mở **terminal thứ hai** và thay PID ví dụ bằng số chương trình đã in:

~~~bash
PID=12345
jcmd "$PID" VM.native_memory summary scale=MB
jcmd "$PID" VM.native_memory baseline
grep -E '^VmRSS:|^VmSize:' "/proc/$PID/status"
~~~

Tại terminal Java, nhấn Enter **một lần** để C cấp phát/chạm 64 MiB. Khi thấy `ALLOCATED`, lấy snapshot mới:

~~~bash
jcmd "$PID" VM.native_memory summary.diff scale=MB
grep -E '^VmRSS:|^VmSize:' "/proc/$PID/status"
cat "/proc/$PID/smaps_rollup"
~~~

**Dự đoán cần kiểm chứng:** RSS thường tăng gần cỡ allocation 64 MiB, tùy allocator, trang OS và môi trường; NMT `summary.diff` không hiện thêm đúng 64 MiB trong một nhóm HotSpot tương ứng với libc `malloc` đó. Một vài nhóm NMT vẫn có thể biến động nhẹ do hoạt động JVM không liên quan. Nhấn Enter lần nữa để `free`, chụp thêm snapshot; allocator có thể giữ bộ nhớ để tái sử dụng nên RSS không nhất thiết giảm ngay. Đây là **lab minh họa ranh giới theo dõi**, không dùng giá trị giả định làm bằng chứng của một incident thực tế.

Nếu máy không có GCC/Linux, người học vẫn có thể thực hiện phần **NMT + OS metrics** với công cụ tương ứng; bản Java cần JNI shared library mới chạy đủ phần malloc. Lệnh `java NmtBlindSpotLab --help` chỉ kiểm tra interface Java mà không nạp thư viện C.

## 7. Tình huống điều tra: thư viện native xử lý ảnh

Một dịch vụ Java nạp thư viện C/C++ để xử lý ảnh. Sau mỗi đợt 500 request, RSS tăng thêm 100 MiB dù throughput trở về mức nền; NMT `Class`, `GC`, `Java Heap committed` ít thay đổi.

Cách điều tra có kiểm chứng:

1. **Đồng bộ số đo** cùng PID/time window/JDK, cùng cấu hình container, tải và ảnh đầu vào; lấy RSS/PSS, NMT delta, heap used/live set, lỗi và số native handles.
2. **Kiểm tra chênh semantics:** NMT không tương đương RSS; xem `smaps` có tăng private anonymous mappings hay mapped files không, và có quá nhiều process trong cùng cgroup không.
3. **Khoanh vùng thư viện:** xác định call path JNI/JNA, context/pool, thời điểm `malloc`/`mmap`, phương thức `free/close`, allocation tăng sau request nào và exception path nào.
4. **Profile native memory:** ở staging, thu call stack allocation/free hoặc dùng allocator stats; kiểm tra live allocations qua nhiều chu kỳ sau khi các request hoàn thành.
5. **Thay đổi một biến:** giới hạn đồng thời hoặc bắt buộc đóng native handle của một nhánh đường chạy; đo lại trong điều kiện tải tương đương. Nếu live native bytes ngừng tăng và RSS ổn định, có bằng chứng nhân quả mạnh hơn.
6. **Sửa tại resource owner:** đảm bảo cleanup trong `finally`/`close`, dọn đường lỗi/cancel, sửa thư viện nếu có bug, hạn chế cache có chủ đích; xác nhận trên nhiều vòng workload.

Không được gọi “leak 100 MiB mỗi 500 request” chỉ vì RSS tăng: bộ nhớ có thể là cache/arena hợp lệ. Phải kiểm tra live allocations có đang mất owner hay không. Nếu cgroup memory tăng mà RSS riêng PID không tăng, cần điều tra sidecar/page cache/kernel charges trước khi kết luận JNI gây ra.

## 8. Những ngộ nhận phổ biến

1. **“NMT `Total committed` là tổng RAM JVM.”** Sai; nó chỉ là HotSpot-tracked committed và không cùng nghĩa với RSS.
2. **“`detail` sẽ thấy mọi `malloc` của JNI.”** Sai; detail chỉ sâu hơn trong phạm vi được NMT theo dõi.
3. **“`Other` là mọi cấp phát native ngoài JVM.”** Sai; đó là nhóm HotSpot được NMT ghi nhận.
4. **“Heap `reserved` 2 GiB nghĩa là dùng 2 GiB RAM.”** Sai; reserved là địa chỉ ảo, không phải resident.
5. **“RSS cao sau GC chứng minh leak.”** Sai; heap committed, allocator high-water mark, cache/arena và mappings có thể giữ RSS.
6. **“NMT phẳng chứng minh không có leak.”** Sai; JNI/native library có thể tăng ngoài phạm vi NMT.
7. **“Tăng RSS trừ tăng NMT là dung lượng leak.”** Sai vì các con số khác semantics và có phần shared/page residency.
8. **“Chỉ cần một `summary.diff` là tìm ra thư viện gây leak.”** Sai; cần OS mapping và native allocation stacks/ownership theo chuỗi thời gian.
9. **“Có thể bật NMT bằng `jcmd` giữa chừng.”** Sai nếu JVM đã start với off.
10. **“`free` xong RSS không giảm tức thì là free thất bại.”** Sai; allocator/OS có thể giữ vùng cho lần sau, cần quan sát live blocks và reuse.

## 9. Checklist kết luận đúng phạm vi

- [ ] Ghi chính xác HotSpot/JDK build, PID, CPU/memory quota, NMT level và thời điểm đo.
- [ ] NMT đã bật khi startup, baseline lập sau warm-up và có nhiều snapshot cùng workload.
- [ ] Diễn giải `reserved`/`committed` riêng với `heap used`, RSS/PSS và cgroup charges.
- [ ] Phân tích HotSpot category nếu NMT tăng; không mặc định mọi tăng trưởng là leak.
- [ ] Nếu RSS tăng nhưng NMT phẳng, kiểm tra OS mappings, JNI/JNA/C library, `malloc/mmap`, allocator caches và native handles.
- [ ] Nếu nghi leak, có bằng chứng native live allocations theo call site và resource lifecycle, không chỉ có chênh byte giữa hai công cụ.
- [ ] Đo lại sau chỉnh sửa, có cùng tải, p95/p99, error, RSS/PSS, NMT diff và native allocation stats khi khả dụng.
- [ ] Báo cáo phân biệt rõ **quan sát**, **giả thuyết** và **thử nghiệm xác nhận**.

### Tài liệu chính thức

- Oracle Java 21 — Native Memory Tracking: https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html
- Oracle Java 21 — Diagnostic Tools/NMT categories: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle Java troubleshooting — native memory leaks và JNI: https://ops.java/troubleshooting/articles/memory-leaks/

**Nguyên tắc:** NMT trả lời “HotSpot đang reserve/commit những vùng nào mà nó biết?”. Muốn biết “toàn process đang resident bao nhiêu RAM và allocation native nào còn sống?”, phải đối chiếu với OS/container metrics và công cụ profiling đúng allocator.