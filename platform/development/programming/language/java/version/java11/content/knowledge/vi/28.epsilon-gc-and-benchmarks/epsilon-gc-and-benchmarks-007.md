# Java 11 — Bật công cụ theo tùy chọn được JDK hiện hành cung cấp

**Ngữ cảnh:** Java 11 → **Epsilon và phép đo**. Bài học chỉ rõ cách **bật Epsilon GC và các công cụ quan sát/kiểm tra liên quan bằng tùy chọn mà bản JDK thực tế hỗ trợ**. Trọng tâm là các cờ khởi động HotSpot, cách tự kiểm chứng collector đã chọn, cấu hình heap và Unified Logging, chạy một thí nghiệm hữu hạn, đọc allocated bytes đúng nghĩa, và xử lý trường hợp JVM không có/từ chối một option. Đây không phải lời khuyên bật Epsilon làm GC mặc định cho dịch vụ.

**Special Note:** Chỉ sử dụng kiến thức **vẫn còn áp dụng hiện nay**, không lấy các cờ Java đã lỗi thời hoặc legacy. Epsilon được giới thiệu bằng JEP 318 ở Java 11, vẫn xuất hiện trong OpenJDK HotSpot hiện hành, nhưng vẫn là **experimental no-op collector**. Việc hỗ trợ tùy thuộc **vendor, JVM implementation và cách build**, không được khẳng định mọi JVM đều có cờ `UseEpsilonGC`. Ví dụ Java được biên dịch bằng `javac --release 11`; các lệnh và stdout xác thực trên OpenJDK Zulu 24.0.2, còn JDK 11/JDK 27 thực tế phải có job kiểm riêng khi cần khẳng định tương thích runtime.

**Mục tiêu:** Sau bài bạn biết:
1. Phân biệt **Epsilon không thu hồi heap** với một GC thông thường và biết khi nào dùng nó để đo.
2. Dùng đúng `-XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC` theo **thứ tự**.
3. Giới hạn `-Xms/-Xmx`, bật `-Xlog:gc`, kiểm cờ bằng `-XX:+PrintFlagsFinal` và bằng `HotSpotDiagnosticMXBean`.
4. So sánh với G1 bằng workload hữu hạn, không nhầm heap-used delta với tổng allocated bytes.
5. Chạy hai chương trình Java 11: **EpsilonConfigCheck.java** và **EpsilonLaunchSmokeTest.java**.
6. Lập experiment an toàn, giải thích sự cố `OutOfMemoryError`, kiểm collector support trên JDK được cài.
7. Biết khác biệt giữa thí nghiệm GC, JFR, ThreadMXBean, JMH và tải production.

## 1. Epsilon là gì và không làm gì?

**Epsilon GC (JEP 318)** là một garbage collector đặc biệt của HotSpot, còn gọi *no-op collector*. Nó **cấp phát heap** nhưng **không thu hồi vùng nhớ của những object đã chết**. Vì vậy, nếu chương trình liên tục tạo object, tổng heap đã dùng có xu hướng tăng cho đến khi chạm giới hạn.

~~~text
Normal collector (ví dụ G1)                  Epsilon (no-op)
  allocate object A                           allocate object A
  allocate object B                           allocate object B
  A/B hết reachable                           A/B hết reachable
  [collector có thể reclaim A/B]             [KHÔNG reclaim A/B]
  vùng trống có thể dùng lại                  phần heap đã cấp phát vẫn bị chiếm
  tiếp tục allocate nếu đủ khả năng            tiếp tục đến khi đầy heap
~~~

**Epsilon không có tác dụng “tắt cơ chế cấp phát”**. Chương trình vẫn tạo arrays/objects, chỉ khác là không có quá trình GC reclaim heap. Nó cũng **không** xóa mọi safepoint, không tắt JIT, không làm allocation không tốn chi phí và không biến mã Java thành ứng dụng không sử dụng heap.

Epsilon có ý nghĩa khi:
- So sánh behavior **khi không có GC reclaim** để cô lập một số chi phí GC, với đủ headroom.
- Thử một **job ngắn** với tổng lượng allocation đã ước tính, kết thúc trước khi hết heap.
- Xây experiment kiểm **giới hạn allocation budget**: chương trình có vượt một mức tổng cấp phát nhất định trước khi kết thúc hay không?
- Phân tích overhead trong một tình huống latency đặc biệt, **không** suy rộng không kiểm chứng sang production.

Epsilon **không phù hợp mặc định** cho server chạy lâu, workload nhiều object tạm, request volume bất định hoặc hệ thống không thể chấp nhận một lần đầy heap sẽ làm process dừng. Epsilon vẫn experimental; việc bật nó trong production cần một threat model, budget và quy trình vận hành rất khác so với GC thông thường.

## 2. Tại sao phải hỏi “JDK hiện hành có option này không?”

`-XX` options là **tùy chọn JVM implementation-specific**. Java language/API Java 11 không bảo đảm mọi JDK distribution, build hoặc JVM khác nhau có cùng flags. Chẳng hạn:

| Thành phần | Điều chắc chắn cần kiểm |
| --- | --- |
| `java` trên PATH | Đang chạy executable của **JDK/JRE nào**, vendor/version nào? |
| `javac --release 11` | Source/bytecode target 11, **không** chứng minh runtime đang là JDK 11. |
| HotSpot `UseEpsilonGC` | Có được compile vào build này không, và còn experimental không? |
| `UnlockExperimentalVMOptions` | Có bật đúng **trước** cờ experimental không? |
| `-Xms/-Xmx` | Có phù hợp container/OS memory limits, overhead và thời lượng job không? |
| JFR/management extensions | Có module `jdk.jfr`, `jdk.management` và quyền truy cập cần thiết không? |
| `jcmd`/`jfr` | Đây là tools thuộc JDK distribution; custom runtime image có thể không gồm. |

Ở thời điểm bài được viết (11/2026), **Java 27 là release GA hiện hành**. Cơ chế chọn `UseEpsilonGC` vẫn hiện diện trong mã nguồn HotSpot OpenJDK chính, với định nghĩa experimental. Nhưng **không** suy rằng cờ đó đã được chạy/QA trên Java 27 chỉ vì JDK 24 có; cần thực sự chạy ma trận trên JDK 11, 17/21/25 và 27 nếu sản phẩm phục vụ các phiên bản này.

### 2.1. Nhận diện executable đang dùng

~~~bash
java -version
javac -version
java -XshowSettings:properties -version
~~~

Lệnh thứ ba cung cấp nhiều properties; có thể kiểm `java.home`, `java.vm.name`, `java.vm.version`, `java.vendor`. Trên máy có nhiều JDK, biến môi trường `JAVA_HOME` và executable `java` trong PATH **có thể trỏ hai bản khác nhau**. Không đo bằng JDK A nhưng ghi báo cáo như thể JDK B.

Trên PowerShell:

~~~powershell
Get-Command java
java -version
javac -version
~~~

Trên macOS/Linux:

~~~bash
command -v java
java -version
javac -version
~~~

**Những lệnh này là kiểm tra môi trường**, không thay đổi project hay hệ thống. Nếu toolchain của CI thay đổi, ghi rõ artifact/commit và runtime version cùng kết quả test.

## 3. Cú pháp chính xác để bật Epsilon trên HotSpot hỗ trợ

Đối với các bản HotSpot có Epsilon GC experimental:

~~~bash
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC \
  -Xms64m -Xmx64m -Xlog:gc=info -version
~~~

**Hai flags quan trọng và thứ tự:**

1. `-XX:+UnlockExperimentalVMOptions`: mở quyền dùng **tùy chọn experimental**.
2. `-XX:+UseEpsilonGC`: chọn **Epsilon GC**.

`UnlockExperimentalVMOptions` phải đứng **trước** `UseEpsilonGC` trong danh sách command-line flags. Đây là quan hệ phụ thuộc được JVM kiểm tại startup, **không** phải convention tùy ý. Có thể đặt `-Xms/-Xmx` và `-Xlog` ở vị trí thích hợp khác, nhưng luôn giữ unlock trước flag experimental.

**Stdout/stderr mẫu đã kiểm chứng trên Zulu OpenJDK 24.0.2:**

~~~text
[...][info][gc] Using Epsilon
[...][info][gc] Consider enabling -XX:+AlwaysPreTouch to avoid memory commit hiccups
openjdk version "24.0.2" 2025-07-15
...
[...][info][gc] Heap: 65536K reserved, 65536K (100.00%) committed, ... used
~~~

Dấu `[...]` và `...` ở ví dụ này **biểu thị phần output khác theo runtime**, **không phải stdout expected cố định**. Đầu ra thực có version string, uptime, heap used, vendor, log configuration và warnings tùy JVM. Điều cần nhìn thấy ở đây là **`Using Epsilon`** hoặc bằng chứng độc lập cờ `UseEpsilonGC=true`.

### 3.1. Lệnh nào bị từ chối?

~~~bash
java -XX:+UseEpsilonGC -version
~~~

Trên build JDK 24 đã thử, lệnh này **exit non-zero** và báo:

~~~text
Error: VM option 'UseEpsilonGC' is experimental and must be enabled via -XX:+UnlockExperimentalVMOptions.
Error: The unlock option must precede 'UseEpsilonGC'.
...
~~~

Lỗi là **đúng thiết kế**: thiếu bước mở khóa. **Không** “sửa” bằng cách xóa `-XX:+UseEpsilonGC` rồi tưởng mình vẫn đang đo Epsilon; khi đó JVM sẽ dùng collector khác theo policy của nó.

### 3.2. Windows PowerShell và bash

**PowerShell** có thể dùng một dòng để tránh vấn đề ký tự continuation:

~~~powershell
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -Xms64m -Xmx64m '-Xlog:gc=info' -version
~~~

**Bash**:

~~~bash
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC \
     -Xms64m -Xmx64m '-Xlog:gc=info' -version
~~~

Cả hai dùng cùng JVM flags; chỉ khác cú pháp shell. `-Xlog:gc=info` dùng **Unified JVM Logging** hợp lệ từ Java 11, không dùng các cờ logging đã legacy của thế hệ JDK cũ.

## 4. Cấu hình heap an toàn cho phép thử

Lệnh minh họa đặt `-Xms64m -Xmx64m` để heap có khoảng giới hạn hữu hạn, dễ quan sát và không tự động tăng `-Xmx` đến một lượng rất lớn. Khi Epsilon chạy, tổng **heap allocations** sau khởi động sẽ chiếm heap và không được reclaim.

| Option | Vai trò | Có phải Epsilon-only? |
| --- | --- | --- |
| `-Xms64m` | Initial heap size 64 MiB; trong ví dụ bằng max. | Không, HotSpot heap option chung. |
| `-Xmx64m` | Giới hạn tối đa Java heap 64 MiB. | Không. |
| `-XX:+AlwaysPreTouch` | Chủ động chạm các trang heap khi khởi tạo để giảm memory commit/page-fault hiccup trong runtime; tăng startup cost. | Không; **tùy chọn**, không bắt buộc. |
| `-Xlog:gc=info` | In một số sự kiện/trạng thái GC như collector được chọn. | Không. |
| `-Xlog:gc*:file=epsilon-gc.log:time,uptime,level,tags` | Ghi log GC chi tiết vào file. | Không. |
| `-XX:+PrintFlagsFinal` | In giá trị flags sau khi JVM xử lý startup options. | Không. |

**Lưu ý:** `-Xmx` chỉ giới hạn **Java heap**, **không** phải tổng memory của process/container. Metaspace, thread stacks, code cache, native memory, direct buffers, JVM runtime và JFR buffers có thể tiêu thêm RAM. Không cấu hình `-Xmx` bằng toàn bộ container memory rồi cho rằng không thể OOM ở OS.

Với Epsilon, tổng allocation **tính từ lúc process bắt đầu**, kể cả class loading, logging, exception handling, instrumentation và tác vụ nền, đều ăn vào budget. Do đó, một workload đề nghị cấp 4 MiB payload trên `-Xmx64m` có thể dùng nhiều hơn 4 MiB heap thực.

### 4.1. Heap cố định có phải quy định bắt buộc?

**Không.** Đặt `-Xms=-Xmx` làm thí nghiệm dễ so sánh và có thể tránh resize/commit hiccup; nhưng nó làm JVM commit heap sớm hơn và có chi phí startup/RSS tùy OS. Thử nghiệm đo startup time có thể muốn một cấu hình khác. Đừng bật `AlwaysPreTouch` chỉ vì log gợi ý, rồi đem so với baseline không bật nó: bạn đã thay thêm một biến.

### 4.2. Ngăn phép thử làm hại môi trường

- Chỉ chạy Epsilon trong **process thử nghiệm riêng**; không đổi startup flags toàn công ty.
- Đặt giới hạn `-Xmx`, memory limit của OS/container, thời gian chạy và số bước cấp phát.
- Tắt auto-restart của job thử nếu nó có thể rơi vào vòng startup→OOM→restart.
- Không chạy dưới credentials có quyền ghi dữ liệu production hoặc kết nối service side-effect.
- Ghi stdout/stderr và **exit code**, không chỉ elapsed time.
- Không tùy tiện nâng heap vô hạn để “làm cho test pass”; như vậy mất ý nghĩa budget.
- Không chủ động tạo OOM trong JVM chính của IDE, test runner tập trung hoặc service thật.

## 5. Xác minh flags thực tế qua `PrintFlagsFinal`

Một lệnh quan trọng để phân biệt “tôi đã gửi flag” và “JVM thực sự bật flag”:

~~~bash
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC \
  -XX:+PrintFlagsFinal -version
~~~

Trong output, tìm hai dòng có ý nghĩa:

~~~text
bool UnlockExperimentalVMOptions = true   {experimental} {command line}
bool UseEpsilonGC                = true   {experimental} {command line}
~~~

Đây là **rút gọn các cột** của một output thực; spacing, nguồn option và thứ tự các thuộc tính có thể khác giữa JDK versions. Dấu `:=` hay `=` ở một số bảng cũ không phải cú pháp Java cần copy, chỉ là cách hiển thị giá trị.

Lọc bằng Bash:

~~~bash
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC \
  -XX:+PrintFlagsFinal -version 2>&1 | grep -E 'UseEpsilonGC|UnlockExperimentalVMOptions'
~~~

Lọc bằng PowerShell:

~~~powershell
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -XX:+PrintFlagsFinal -version 2>&1 | Select-String 'UseEpsilonGC|UnlockExperimentalVMOptions'
~~~

**Đã quan sát trên JDK 24:** `UnlockExperimentalVMOptions=true` và `UseEpsilonGC=true`, đều thuộc nhóm `experimental` và có nguồn `command line`. Đây là bằng chứng mạnh hơn việc chỉ thấy `GC collections reported = 0`, vì một JVM dùng G1 mà workload ngắn quá cũng có thể chưa chạy GC lần nào.

### 5.1. Nếu không có option?

Tùy lỗi, cách xử lý khác nhau:

| Thông báo hoặc trạng thái | Ý nghĩa khả dĩ | Hành động |
| --- | --- | --- |
| `UseEpsilonGC is experimental` | Chưa unlock hoặc thứ tự sai. | Thêm/move `UnlockExperimentalVMOptions` **trước**. |
| `Unrecognized VM option 'UseEpsilonGC'` | VM/build không có option hoặc tên không được hỗ trợ. | Kiểm vendor/version/build; không tự dùng option giả. |
| `Option -XX:+UseEpsilonGC not supported` | Build có tên flag nhưng **không include collector**. | Xem runtime build/release; dùng build có Epsilon cho bài thử. |
| Collector khác được chọn | Startup flags không đúng hoặc xung đột. | Xem log `Using ...`, flags, config/startup scripts. |
| VM không start vì heap quá nhỏ | Metadata/runtime không đủ budget. | Chọn heap hợp lý trong môi trường thử, không test mặc định tại 8 MiB. |
| JVM 11 khác JDK 24 | Mã target 11 không bảo đảm cùng flags/metrics. | Kiểm runtime đích và lặp thí nghiệm. |

**Không thay thế Epsilon bằng `-XX:-UseG1GC`.** Tắt một collector không đồng nghĩa chọn “no-op collector”; JVM có thể chọn collector khác hoặc từ chối tùy cách phối hợp cờ. Chỉ `UseEpsilonGC` khi build hỗ trợ mới chọn Epsilon HotSpot.

## 6. Lệnh so sánh có kiểm soát: Epsilon và G1

Để đối chiếu cùng chương trình, chọn rõ **hai collectors** và giữ các tùy chọn còn lại giống nhau:

~~~bash
# Nhánh Epsilon
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC \
  -Xms64m -Xmx64m EpsilonConfigCheck

# Nhánh đối chứng G1
java -XX:+UnlockExperimentalVMOptions -XX:+UseG1GC \
  -Xms64m -Xmx64m EpsilonConfigCheck
~~~

Vì sao nhánh G1 cũng có `UnlockExperimentalVMOptions`? Để chương trình mẫu có thể **đọc được cờ experimental `UseEpsilonGC` qua MXBean** dù nó đang false. Nếu chạy JVM G1 **không unlock**, một số HotSpot builds không expose cờ này qua `HotSpotDiagnosticMXBean.getVMOption`; bài học sẽ xử lý tình huống đó rõ ràng, không gọi sai là “VM không có Epsilon”.

**Không suy từ “Epsilon nhanh hơn G1” ra “G1 có overhead tương đương chênh lệch”.** Các collectors có allocation path, heap layout/commit policy, TLAB behavior, class loading, barriers, concurrent work khác nhau; để đo latency/throughput có kết luận, cần nhiều forks, cùng workload và benchmark harness phù hợp.

## 7. Chương trình hoàn chỉnh Java 11: `EpsilonConfigCheck.java`

Chương trình xác định cờ HotSpot Epsilon, thực hiện **128 allocations × 32 KiB = 4 MiB payload yêu cầu**, rồi in:
- Collector Epsilon đang `ENABLED`, `DISABLED` hay cờ `FLAG_NOT_EXPOSED`.
- Workload đã chạy đúng (checksum 8128).
- Tổng bytes đã request cho các arrays.
- Per-thread allocated heap bytes từ `ThreadMXBean` nếu được hỗ trợ.
- Heap-used delta từ `MemoryMXBean` (snapshot, **không** là tổng bytes đã cấp phát).
- Tổng GC collection count được management beans báo cáo (không phải bằng chứng chọn collector).

**Mã nguồn độc lập, tệp `EpsilonConfigCheck.java`:**

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.GarbageCollectorMXBean;
import com.sun.management.HotSpotDiagnosticMXBean;
import com.sun.management.ThreadMXBean;

public final class EpsilonConfigCheck {
    private static volatile byte[] lastBlock;
    private static final int BLOCKS = 128;
    private static final int BYTES_PER_BLOCK = 32 * 1024;

    private EpsilonConfigCheck() {}

    static String epsilonStatus() {
        HotSpotDiagnosticMXBean hs =
            ManagementFactory.getPlatformMXBean(HotSpotDiagnosticMXBean.class);
        if (hs == null) return "VM_DIAGNOSTICS_UNAVAILABLE";
        try {
            return Boolean.parseBoolean(
                hs.getVMOption("UseEpsilonGC").getValue())
                ? "ENABLED" : "DISABLED";
        } catch (IllegalArgumentException hiddenOrAbsent) {
            return "FLAG_NOT_EXPOSED";
        }
    }

    public static void main(String[] args) {
        String epsilonStatus = epsilonStatus();
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        java.lang.management.ThreadMXBean platform =
            ManagementFactory.getThreadMXBean();
        ThreadMXBean threadMeter =
            platform instanceof ThreadMXBean ? (ThreadMXBean) platform : null;
        boolean allocationMeter = threadMeter != null &&
            threadMeter.isThreadAllocatedMemorySupported();
        if (allocationMeter && !threadMeter.isThreadAllocatedMemoryEnabled()) {
            threadMeter.setThreadAllocatedMemoryEnabled(true);
        }
        long tid = Thread.currentThread().getId();
        long beforeAllocated = allocationMeter
            ? threadMeter.getThreadAllocatedBytes(tid) : -1;
        long beforeUsed = memory.getHeapMemoryUsage().getUsed();

        long checksum = 0;
        for (int i = 0; i < BLOCKS; i++) {
            byte[] b = new byte[BYTES_PER_BLOCK];
            b[0] = (byte) i;
            lastBlock = b;  // Forces the array to escape; earlier arrays become garbage.
            checksum += b[0] & 0xff;
        }
        if (checksum != 8128) {
            throw new AssertionError("Workload corrupted");
        }

        long afterUsed = memory.getHeapMemoryUsage().getUsed();
        long afterAllocated = allocationMeter
            ? threadMeter.getThreadAllocatedBytes(tid) : -1;
        boolean measurable = allocationMeter &&
            beforeAllocated >= 0 && afterAllocated >= beforeAllocated;
        long gcCount = 0;
        for (GarbageCollectorMXBean gc :
                 ManagementFactory.getGarbageCollectorMXBeans()) {
            long n = gc.getCollectionCount();
            if (n >= 0) gcCount += n;
        }

        System.out.println("epsilon.status=" + epsilonStatus);
        System.out.println("work.blocks=" + BLOCKS);
        System.out.println("work.block.bytes=" + BYTES_PER_BLOCK);
        System.out.println("work.requested.payload.bytes=" +
            (BLOCKS * BYTES_PER_BLOCK));
        System.out.println("work.checksum=" + checksum);
        System.out.println("thread.allocated.bytes.supported=" + measurable);
        if (measurable) {
            System.out.println("thread.allocated.bytes=" +
                (afterAllocated - beforeAllocated));
        }
        System.out.println("heap.used.delta.bytes=" +
            (afterUsed - beforeUsed));
        System.out.println("gc.collections.reported=" + gcCount);
        System.out.println("heap.used.is.not.total.allocation=true");
    }
}
~~~

**Biên dịch một lần, chạy với hai collectors:**

~~~bash
javac --release 11 -encoding UTF-8 EpsilonConfigCheck.java

java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC \
  -Xms64m -Xmx64m EpsilonConfigCheck

java -XX:+UnlockExperimentalVMOptions -XX:+UseG1GC \
  -Xms64m -Xmx64m EpsilonConfigCheck
~~~

**Kết quả Epsilon trong một lần chạy thật trên Zulu JDK 24.0.2:**

~~~text
epsilon.status=ENABLED
work.blocks=128
work.block.bytes=32768
work.requested.payload.bytes=4194304
work.checksum=8128
thread.allocated.bytes.supported=true
thread.allocated.bytes=4197256
heap.used.delta.bytes=4245104
gc.collections.reported=0
heap.used.is.not.total.allocation=true
~~~

**Kết quả G1 cùng JVM/heap/workload trong lần thử đó:**

~~~text
epsilon.status=DISABLED
work.blocks=128
work.block.bytes=32768
work.requested.payload.bytes=4194304
work.checksum=8128
thread.allocated.bytes.supported=true
thread.allocated.bytes=4197256
heap.used.delta.bytes=3145728
gc.collections.reported=0
heap.used.is.not.total.allocation=true
~~~

**Phân loại stdout đúng:**
- `epsilon.status=ENABLED` hoặc `DISABLED` là điều kiện cố định **khi dùng chính hai lệnh trên ở bản HotSpot hỗ trợ**.
- `work.blocks=128`, `work.block.bytes=32768`, `work.requested.payload.bytes=4194304` và `work.checksum=8128` là dữ liệu cố định của source.
- `thread.allocated.bytes` và `heap.used.delta.bytes` là **số đo biến thiên** theo JDK/heap/layout/JIT/background allocations, không được assert đúng số từ output ví dụ.
- `thread.allocated.bytes.supported` có thể false nếu VM không cung cấp tính năng; khi đó chương trình không in con số allocated bytes.
- `gc.collections.reported=0` xuất hiện **cả Epsilon và G1 trong lần thử ngắn**. Một kết quả 0 GC **không đủ** để chứng minh Epsilon được bật.

### 7.1. Vì sao dùng `lastBlock` là volatile?

`lastBlock` giữ tham chiếu cuối; từng block cũ trở thành unreachable khi thay tham chiếu. Việc lưu mảng vào static `volatile` khiến object escape rõ ràng và giảm nguy cơ phép cấp phát bị JIT xóa. **Không** có nghĩa toàn bộ arrays còn reachable; chỉ block cuối là reachable theo tham chiếu này.

Với collector thông thường, JVM **có thể** reclaim các blocks cũ nếu cần. Với Epsilon, phần heap đã dùng cho các block đó không được thu hồi. Dùng thử nghiệm hữu hạn 4 MiB giúp minh họa mà không cố tình làm process hết heap.

### 7.2. `ThreadMXBean` và `MemoryMXBean` khác nhau

`getThreadAllocatedBytes(threadId)` phản ánh **byte heap mà một thread đã cấp phát** trong khoảng đo (ước lượng); `getHeapMemoryUsage().getUsed()` là **heap snapshot của toàn JVM** ở hai thời điểm. Mặc dù chương trình in cả hai, chúng không phải cùng một metric.

**Kết quả trong lần thử:** hai collectors có cùng số `thread.allocated.bytes=4197256` nhưng `heap.used.delta.bytes` khác. Điều đó minh họa lý do **không dùng delta heap used như allocation rate/B/op**, bởi heap-used chịu ảnh hưởng collector, accounting và những hoạt động ngoài thread đo. Không suy theo một lần chạy rằng G1 giảm allocation của application khi checksum/source vẫn như cũ.

## 8. Cách đọc option đang bị khóa qua MXBean

`HotSpotDiagnosticMXBean` tồn tại trong module `jdk.management`; `getVMOption("UseEpsilonGC")` trả `VMOption` nếu flag được expose. Tuy nhiên **experimental flags có thể không được expose khi chưa bật unlock**. Trong lần thử:

~~~bash
java -Xms64m -Xmx64m EpsilonConfigCheck
~~~

Output bắt đầu:

~~~text
epsilon.status=FLAG_NOT_EXPOSED
...
~~~

Đây là **trường hợp khác với `DISABLED`**. `FLAG_NOT_EXPOSED` có nghĩa phép đọc diagnostic option không thành công (có thể cờ bị khóa/không hiện hữu), **không** kết luận collector Epsilon không tồn tại. Muốn phân biệt, kiểm lệnh JVM và `PrintFlagsFinal` với unlock theo JDK/vm cụ thể.

Nếu chạy trên JVM không có `HotSpotDiagnosticMXBean`, chương trình trả `VM_DIAGNOSTICS_UNAVAILABLE`; không được suy đó là “Epsilon false” và tiếp tục bài thí nghiệm như đã chọn đúng collector. `ThreadMXBean` cũng chỉ là extension có thể unsupported; code báo rõ nếu không đo được.

## 9. Chương trình Java 11 thứ hai: kiểm lệnh khởi chạy bằng JVM con

Một regression test hữu ích cho tooling là **tạo process con** với các JVM flags, kiểm exit code và output. Điều này phát hiện khi một bản JDK bị thay, một startup option bị gỡ, một collector không được build hoặc script bỏ quên unlock.

**Tệp `EpsilonLaunchSmokeTest.java`**, chạy cùng thư mục/classpath với `EpsilonConfigCheck.class`:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class EpsilonLaunchSmokeTest {
    private EpsilonLaunchSmokeTest() {}

    static final class Run {
        final int exit;
        final String output;
        Run(int exit, String output) {
            this.exit = exit;
            this.output = output;
        }
    }

    static Run run(String... flags) throws Exception {
        String exe = System.getProperty("os.name").toLowerCase()
            .contains("win") ? "java.exe" : "java";
        String java = Paths.get(System.getProperty("java.home"),
            "bin", exe).toString();
        List<String> command = new ArrayList<>();
        command.add(java);
        command.addAll(Arrays.asList(flags));
        command.add("-cp");
        command.add(System.getProperty("java.class.path"));
        command.add("EpsilonConfigCheck");
        Process process = new ProcessBuilder(command)
            .redirectErrorStream(true)
            .start();
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        process.getInputStream().transferTo(output);
        int exit = process.waitFor();
        return new Run(exit, output.toString("UTF-8"));
    }

    public static void main(String[] args) throws Exception {
        Run epsilon = run(
            "-XX:+UnlockExperimentalVMOptions", "-XX:+UseEpsilonGC",
            "-Xms64m", "-Xmx64m");
        Run g1 = run(
            "-XX:+UnlockExperimentalVMOptions", "-XX:+UseG1GC",
            "-Xms64m", "-Xmx64m");
        Run missingUnlock = run(
            "-XX:+UseEpsilonGC", "-Xms64m", "-Xmx64m");

        boolean epsilonSelected = epsilon.exit == 0 &&
            epsilon.output.contains("epsilon.status=ENABLED");
        boolean g1Selected = g1.exit == 0 &&
            g1.output.contains("epsilon.status=DISABLED");
        boolean checksumCorrect =
            epsilon.output.contains("work.checksum=8128") &&
            g1.output.contains("work.checksum=8128");
        boolean rejected = missingUnlock.exit != 0;
        if (!epsilonSelected || !g1Selected ||
            !checksumCorrect || !rejected) {
            throw new AssertionError(
                "Incompatible JDK flags; inspect child JVM output");
        }

        System.out.println("epsilon.launch.exit=" + epsilon.exit);
        System.out.println("g1.launch.exit=" + g1.exit);
        System.out.println("missing.unlock.rejected=" + rejected);
        System.out.println("epsilon.flag.true=" + epsilonSelected);
        System.out.println("g1.flag.false=" + g1Selected);
        System.out.println("business.checksum.equal=" + checksumCorrect);
    }
}
~~~

**Biên dịch và chạy smoke test (không cần JUnit):**

~~~bash
javac --release 11 -encoding UTF-8 EpsilonConfigCheck.java EpsilonLaunchSmokeTest.java
java EpsilonLaunchSmokeTest
~~~

**Stdout đã được thực thi và kiểm chứng trên Zulu OpenJDK 24.0.2:**

~~~text
epsilon.launch.exit=0
g1.launch.exit=0
missing.unlock.rejected=true
epsilon.flag.true=true
g1.flag.false=true
business.checksum.equal=true
~~~

Bài test này có **điều kiện môi trường**: nó áp dụng khi JVM hiện tại là một HotSpot build hỗ trợ Epsilon experimental và có G1. Nếu chạy trên OpenJ9, custom VM image hoặc bản release trong tương lai thay đổi flag contract, **test phải báo fail/incompatible**, không được lén bỏ Epsilon và coi pass.

### 9.1. Tại sao dùng `ProcessBuilder`?

- Mỗi startup flag được JVM parser xử lý **trước main**, không thể đổi collector an toàn bằng `System.setProperty` sau khi JVM đã chạy.
- Với `ProcessBuilder`, mỗi nhánh A/B khởi động **JVM con mới**, không dùng chung collector state.
- Test đọc cả stderr do `redirectErrorStream(true)` nên thấy thông báo experimental/unsupported.
- `java.home/bin/java` giúp dùng executable của chính runtime chạy test; không suy từ hệ thống PATH.
- Exit code **0** là điều kiện cần nhưng không đủ; test còn kiểm `epsilon.status` và checksum.
- Nhánh thiếu unlock **phải fail** trên HotSpot còn experimental; đó là negative test có chủ đích.

**Caveat:** Chương trình con có thể không khởi động nếu môi trường hạn chế tạo processes, `java.home` không có executable, RAM/CPU bị giới hạn, JDK đã cắt bỏ modules. Khi ấy báo test environment failure, không tự suy rằng Epsilon đã bị xóa.

## 10. Vì sao không cố bắt `OutOfMemoryError` trong cùng JVM Epsilon?

Epsilon không reclaim heap. Khi `-Xmx` cạn, HotSpot có thể **kết thúc tiến trình ngay** thay vì cho application tiếp tục catch `OutOfMemoryError`. Trong JDK 24 đã thử, một vòng tạo các arrays 1 MiB trong tiến trình con với `-Xmx32m` khiến output dạng:

~~~text
Terminating due to java.lang.OutOfMemoryError: Java heap space
~~~

và exit code **khác 0**. Không có gì bảo đảm một `catch (OutOfMemoryError ...)` của chính ứng dụng sẽ chạy hoặc in thêm được log trước khi JVM bị chấm dứt. Đây là behavior có thể phụ thuộc JVM/flags, nhưng đủ để thấy việc cố ép Epsilon tới cạn heap trong một **service** là nguy hiểm.

**Do đó bài này KHÔNG đặt vòng tạo OOM trong chương trình demo mặc định.** Nếu cần kiểm termination policy, phải chạy trong **process/container riêng**, có heap/CPU/time limits và thu **exit code + stderr** từ process giám sát. Không làm trong Gradle daemon, Maven reactor chung hoặc JVM đang xử lý dữ liệu quan trọng.

### 10.1. Công thức ngân sách

Nếu mỗi item đòi `b` byte payload, có `n` items, thời gian sống process còn tạo thêm metadata/objects `H` thì một điều kiện thực dụng là:

\[
n \cdot b + H + \mathrm{safetyMargin} < Xmx
\]

Đây chỉ là **ước lượng budget**; object headers, array alignment, JIT, logging, class init, JFR instrumentation, native memory và TLAB làm con số thực tế khác. Vì Epsilon không thu hồi, với một job dài phải tính **tổng allocations trong suốt quá trình**, không chỉ số object còn sống tại một thời điểm.

Ví dụ chương trình mục 7 yêu cầu 128 × 32,768 = **4,194,304 payload bytes**; `ThreadMXBean` trong lần thử báo khoảng 4,197,256 bytes của thread. Dù các block cũ đã unreachable, Epsilon vẫn không reclaim heap của chúng.

### 10.2. Không dùng `System.gc()` làm “cứu cánh”

`System.gc()` không thể biến Epsilon thành collector có memory reclamation. Không chèn `System.gc()` vào vòng cấp phát rồi kỳ vọng các blocks cũ được thu hồi. Cũng không dùng `-XX:+DisableExplicitGC` như một cách chọn Epsilon: option đó chỉ liên quan xử lý yêu cầu explicit GC, **không chọn no-op collector**.

## 11. Đo với Unified JVM Logging hiện hành

Java 11 dùng **Unified Logging**. Những lệnh hữu ích:

~~~bash
# Nhận diện collector và các thông tin GC mức info:
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC \
  -Xms64m -Xmx64m '-Xlog:gc=info' EpsilonConfigCheck

# Ghi log ra file trong môi trường thử có quyền ghi:
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC \
  -Xms64m -Xmx64m \
  '-Xlog:gc*:file=epsilon-gc.log:time,uptime,level,tags' EpsilonConfigCheck

# Nhánh đối chứng G1 với cùng log settings:
java -XX:+UnlockExperimentalVMOptions -XX:+UseG1GC \
  -Xms64m -Xmx64m \
  '-Xlog:gc*:file=g1-gc.log:time,uptime,level,tags' EpsilonConfigCheck
~~~

**Các lệnh trên dùng flags hợp lệ của Java 11 HotSpot**, log mức chi tiết tùy JVM. File sẽ được tạo trong thư mục hiện hành, cần quyền ghi; nếu muốn tránh ghi file, dùng logging ra console.

**Cần quan sát:**
- Collector được chọn tại startup: `Using Epsilon` hoặc `Using G1`.
- Heap reserved/committed/used, GC events thực sự.
- Exit status (0 với workload hữu hạn).
- Các warning optional tuning (ví dụ `AlwaysPreTouch`) không tự động là lỗi.
- Không dùng “không thấy GC pause” làm kết luận “không có allocation”; khi Epsilon không reclaim, cấp phát vẫn xảy ra.

**Không dùng flags legacy** để tạo tài liệu mới, như `-XX:+PrintGCDetails` hoặc `-Xloggc`, nếu mục tiêu là hướng dẫn cho Java 11 và JDK hiện hành. Dùng `-Xlog:gc...`.

## 12. Các công cụ chẩn đoán khác của JDK và cách bật đúng

Epsilon chỉ là một **collector**, không phải một profiler hoàn chỉnh. Với JDK distribution có tools phù hợp, có thể bổ sung:

| Công cụ / kỹ thuật | Dùng để làm gì | Ràng buộc |
| --- | --- | --- |
| `java -XX:+PrintFlagsFinal` | Xem JVM flags thực tế, nguồn và trạng thái. | Output rất dài; lọc đúng flag. |
| `-Xlog:gc=info` | Xem collector được chọn và thông tin GC. | Output phụ thuộc build/log level. |
| `-Xlog:gc*:file=...` | Lưu GC events vào file. | Không đồng nhất lượng GC events với allocated bytes. |
| `jcmd PID VM.flags` | Xem flags của JVM đang chạy. | JDK tool, quyền attach, process sống, container/PID namespace. |
| `jcmd PID VM.command_line` | Xem JVM startup command line. | Có thể chứa secrets, cần lọc khi log/chia sẻ. |
| `jcmd PID GC.heap_info` | Xem thông tin heap hiện tại nếu lệnh được hỗ trợ. | Command/format có thể khác collector/version. |
| `-XX:StartFlightRecording=...` | Bắt đầu Java Flight Recorder lúc JVM startup. | Có overhead/memory; module `jdk.jfr` cần có. |
| `jfr summary/print` | Tóm tắt/đọc file JFR có sẵn. | File có thể chứa thông tin nhạy cảm. |
| `ThreadMXBean` | Đếm allocated heap bytes theo thread nếu JVM hỗ trợ. | Không đo retained heap hoặc tổng process tự động. |
| JMH | Benchmark có forks/warm-up và profiler. | Thư viện/harness riêng, không nằm trong JDK. |

### 12.1. `jcmd`: kiểm tiến trình thực

Khi JVM có PID (theo OS/container tương ứng):

~~~bash
jcmd <PID> VM.flags
jcmd <PID> VM.command_line
jcmd <PID> GC.heap_info
~~~

Đây là **lệnh minh họa với placeholder `<PID>`**; thay bằng PID thực. Không chạy dòng y nguyên trong shell. `jcmd` cần JDK tooling và quyền truy cập process. Nếu JVM không có command đó, không dùng kết quả rỗng để kết luận heap không tồn tại. `VM.command_line` có thể lộ token/secret trong arguments; không đăng nguyên output production lên public ticket.

### 12.2. JFR ở chế độ bổ sung

Nếu build có `jdk.jfr`, có thể thu recording ngắn khi nghiên cứu allocation/CPU:

~~~bash
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC \
  -Xms256m -Xmx256m \
  '-XX:StartFlightRecording=filename=epsilon-run.jfr,settings=profile,dumponexit=true' \
  EpsilonConfigCheck
~~~

**Lệnh tùy chọn, không nằm trong stdout QA chính**: recording tạo thêm allocations và có thể làm một bài thử Epsilon với heap nhỏ OOM sớm hơn; ví dụ chủ động dùng `256m` rộng hơn. Mức overhead và settings phù hợp cần kiểm ở runtime đích. File `.jfr` có thể được xem bằng `jfr summary epsilon-run.jfr` hoặc JDK Mission Control, tuân thủ privacy/retention policy.

Không gọi JFR event count là tổng số object: `jdk.ObjectAllocationInNewTLAB` và `jdk.ObjectAllocationOutsideTLAB` trong Java 11 phản ánh các đường cấp phát cụ thể/sampling, **không phát một event cho mỗi object**. Muốn đo B/op, dùng counter/harness phù hợp hơn.

## 13. Thiết kế phép thử đo Epsilon và GC thường

Một experiment công bằng cần *tối thiểu*:

1. **Mục tiêu định lượng**: so per-thread allocated bytes, elapsed time, throughput, CPU, heap usage hay GC pauses?
2. **Workload hữu hạn, có checksum**: tránh JVM tối ưu xóa công việc và tránh cạn heap.
3. **Cùng version/vendor JVM và cùng flags khác collector**: không so JDK 11 Epsilon với JDK 27 G1 rồi quy hết chênh lệch cho GC.
4. **Cùng input, seed và output**: xác nhận business equivalence trước khi xem số liệu.
5. **Warm-up JIT**: tránh so interpreter/C1 với C2, kiểm code compilation có đủ warm state.
6. **Nhiều trials và JVM forks**: không kết luận từ một thời gian startup ngắn.
7. **Bounded heap lớn hơn tổng allocation Epsilon**: nếu một nhánh OOM thì thí nghiệm throughput **không so sánh công bằng**.
8. **Ghi flags & logs**: dùng `PrintFlagsFinal`, `-Xlog:gc`, runtime vendor/version, commit/build.
9. **Guardrails**: p95/p99, error rate, CPU, RSS/native memory và mức an toàn của service.
10. **Không chạy production** trước khi có một mục tiêu ngắn hạn/điều kiện dừng rõ.

### 13.1. Phân biệt so chi phí GC với so throughput

Cùng một workload có thể có số lần GC bằng 0 cả ở G1 và Epsilon nếu heap đủ rộng cho job ngắn; kết quả thời gian có thể khác vì allocation path, bookkeeping, threads, JIT và nhiễu hệ thống. Kết luận “Epsilon loại bỏ 100% chi phí GC” theo số lượng pause của sample quá ngắn là không có giá trị vì baseline **cũng chưa GC**.

Nếu thực sự muốn đo “ảnh hưởng của GC reclaim”:
- Chọn workload đủ tạo GC ở collector bình thường nhưng vẫn **an toàn** cho Epsilon bằng một budget đủ lớn/hữu hạn.
- Hoặc đo riêng từng câu hỏi: GC pause/throughput ở G1 và allocation overhead với Epsilon, không ép làm một con số duy nhất.
- Không chấp nhận một test Epsilon OOM rồi so thời gian đến OOM với thời gian xử lý hoàn tất của G1 như thể cùng công việc.

### 13.2. Dữ liệu định lượng nên ghi

| Metric | Nhánh Epsilon | Nhánh GC thông thường | Cần diễn giải |
| --- | --- | --- | --- |
| Chọn collector | `UseEpsilonGC=true` | `UseEpsilonGC=false`, ví dụ G1 | Xác nhận flag, không suy từ 0 GC. |
| Workload checksum | 8128 | 8128 | Cùng 128 blocks sample. |
| Payload requested | 4,194,304 B | 4,194,304 B | Payload không bằng total heap allocation. |
| Per-thread allocated bytes | Đo | Đo | Bao gồm allocation của thread trong khoảng, không phải live heap. |
| Heap-used delta | Đo snapshot | Đo snapshot | Chịu ảnh hưởng GC, accounting, background allocation. |
| GC collection count | Theo MXBeans | Theo MXBeans | Có thể là 0 ở cả hai. |
| Elapsed time/CPU | Đo nhiều forks | Đo nhiều forks | Không kết luận từ một startup. |
| Exit code/OOM | 0 theo test hữu hạn | 0 theo test hữu hạn | Cần đều hoàn tất mới so hợp lệ. |
| RSS/process memory | Đo nếu quan trọng | Đo nếu quan trọng | `-Xmx` không phải toàn process memory. |

## 14. Những điều Epsilon không đo chính xác

### 14.1. Không phải heap profiler theo allocation site

Epsilon cho phép chạy **không reclaim**, giúp cô lập yếu tố GC trong một số experiment. Nó **không tự hiển thị class/stack nào tạo nhiều object**. Muốn tìm hotspot, dùng JFR allocation events, Java Flight Recorder/JMC, profiler hoặc JVMTI sampling tùy mục tiêu.

### 14.2. Không phải công cụ đo số object sống

Vì Epsilon không reclaim, `heap-used` có thể tăng ngay cả khi nhiều objects không còn reachable. Do đó, lấy `used heap` của Epsilon làm **retained/live heap** là sai. Muốn tìm memory leak/retention, phải dùng GC/heap dump/dominator tree thích hợp trên một collector có reclamation, và phân tích reachability/GC roots.

### 14.3. Không trực tiếp cho allocation rate chính xác

`heap-used.delta.bytes` của Epsilon có thể gần tổng allocation trong một đoạn vì không thu hồi, nhưng đây vẫn là **heap snapshot toàn JVM** chịu ảnh hưởng thời điểm accounting, TLABs và background allocations. Khi cần B/op có định nghĩa rõ, dùng `ThreadMXBean` hoặc JMH `gc.alloc.rate.norm` trong harness, và giữ denominator.

### 14.4. Không thay thế kiểm p95/p99 production

Một no-GC run có thể giảm một số pauses nhưng không phản ánh long-lived, mixed workload, classloading, memory leaks, spikes, container budget hoặc failure handling. Số đo Epsilon chỉ hợp lệ trong **phạm vi experiment cụ thể**, không tự cho phép rollout với no-op GC.

## 15. Đo allocation bằng ThreadMXBean khi Epsilon chạy

`com.sun.management.ThreadMXBean` (Java 11, module `jdk.management`) có thể đọc `getThreadAllocatedBytes(threadId)`. Phép đo delta:

~~~java
long threadId = Thread.currentThread().getId();
long before = meter.getThreadAllocatedBytes(threadId);
long checksum = workload();
long after = meter.getThreadAllocatedBytes(threadId);
long allocatedBytes = after - before;
~~~

Đây là **snippet minh họa**, `meter` phải được lấy từ `ManagementFactory`, kiểm `isThreadAllocatedMemorySupported`, bật `setThreadAllocatedMemoryEnabled(true)` nếu cần và xử lý `-1` khi không được hỗ trợ. Trong mã đầy đủ ở mục 7, các bước capability check đã được cài đặt.

**Quan trọng:**
- Số byte thuộc **threadId**, không phải toàn bộ JVM hoặc một request phân tán trên nhiều workers.
- `getThreadAllocatedBytes` có thể là xấp xỉ; không assert exact bytes ở mọi JDK.
- `Thread.currentThread().getId()` là API tương thích Java11; đừng dùng `threadId()` của bản Java mới trong source target11.
- Nếu workload có task async/thread pools, cần phương pháp attribution khác hoặc JVM-wide profiling.
- Khi chạy JMH, nhớ chia `B/benchmark invocation` cho số items trong invocation nếu muốn B/item.

## 16. Epsilon với ứng dụng modular, custom runtime image và vendor khác

Java 11 hỗ trợ `jlink` custom image; nếu ứng dụng chỉ đóng gói module tối thiểu, có thể thiếu `jdk.management`, `jdk.jfr` hoặc các tools `jcmd/jfr`. Khi đó:
- **Main application** vẫn có thể chạy nếu các module dùng thật được đóng gói đúng.
- `EpsilonConfigCheck` cần `jdk.management` và `java.management` để đọc diagnostic/allocated bytes.
- Nếu chỉ cần kiểm Epsilon flag, `-Xlog:gc=info`/`PrintFlagsFinal` có thể phù hợp hơn.
- `jcmd` là công cụ JDK bên ngoài; không xuất hiện trong mọi runtime image.
- Với GraalVM Native Image, OpenJ9 hoặc JVM khác, không giả định `UseEpsilonGC` là tên collector hợp lệ.

**Ví dụ phân biệt implementations:** Eclipse OpenJ9 có chính sách `nogc` với cú pháp `-Xgcpolicy:nogc` / `-XX:+UseNoGC` ở những bản hỗ trợ; đó **không phải Epsilon HotSpot cùng flags**. Không trộn hai cú pháp vào cùng câu lệnh rồi kỳ vọng portability. Hãy kiểm runtime documentation và thông báo startup thật của vendor.

### 16.1. Không phát hiện/đổi GC bằng reflection sau khi JVM đã chạy

GC được chọn khi JVM **khởi động**; không thể bật Epsilon đúng cách bằng cách gọi một setter Java reflection sau khi business service đã bắt đầu. Phải cấu hình launch command, script, Docker entrypoint, Kubernetes container args hoặc test harness **trước khi start JVM**. Sau deploy, đọc effective flags/logs để xác minh.

Nếu nhiều runtime được triển khai, đừng chỉ sửa `JAVA_TOOL_OPTIONS` trên machine cá nhân rồi công bố toàn bộ pods đã dùng Epsilon. Mỗi process/pod cần chứng cứ startup riêng; cẩn thận vì `JAVA_TOOL_OPTIONS` áp dụng cho nhiều Java processes và có thể vô tình ảnh hưởng build tools/scheduled tasks.

## 17. Cảnh báo về `-XX:+AlwaysPreTouch` và những “tuning” không mặc định

Khi Epsilon khởi động, HotSpot có thể gợi ý:

~~~text
Consider enabling -XX:+AlwaysPreTouch to avoid memory commit hiccups
~~~

Gợi ý **không đồng nghĩa lỗi**. `AlwaysPreTouch` có thể đưa công việc page fault/commit tới startup, hữu ích trong một số measurement về steady-state, nhưng có thể tăng startup time và mức RAM commit sớm. Nếu mục tiêu là đo startup, không bật nó một phía rồi so với bên kia.

Tương tự, các cờ Epsilon-specific khác có thể khác nhau theo bản JDK. **Không copy một danh sách tuning flags trên blog cũ** như thể chúng đã được đảm bảo ở JDK27. Hãy tìm bằng `PrintFlagsFinal` trên **JDK thực**, kiểm release notes và chỉ dùng option đã tồn tại/được hỗ trợ.

## 18. Troubleshooting: chạy sai collector hoặc không có kết quả đáng tin

| Triệu chứng | Nguyên nhân cần xét | Hướng kiểm |
| --- | --- | --- |
| Lệnh không start: experimental | Unlock thiếu/sai thứ tự. | Đặt unlock trước `UseEpsilonGC`. |
| Unrecognized/unsupported option | JVM/vendor/build không hỗ trợ. | `java -version`, release docs, `PrintFlagsFinal`. |
| Log báo `Using G1` thay vì Epsilon | Flags bị bỏ/không áp đúng process. | Xem process command line và effective flags. |
| `epsilon.status=FLAG_NOT_EXPOSED` | Experimental VM option chưa unlock hoặc không có. | Không kết luận false; chạy CLI với unlock để phân biệt. |
| `gc.collections.reported=0` cho G1 | Workload ngắn/heap đủ lớn. | Không dùng count này để xác định collector. |
| Epsilon hết heap | Tổng allocations > budget, không reclaim. | Dừng experiment, giảm workload hoặc cấp heap có kiểm soát. |
| Test thỉnh thoảng OOM khi bật JFR | Instrumentation cũng allocate. | Tăng headroom hợp lý, log params, tách profiler run. |
| B/item khác JDK24 | Object layout/JIT/accounting khác. | Ghi VM version/flags và đo lại target runtime. |
| Epsilon có allocations nhưng không có GC log cycles | Đây là no-op collector. | Dùng ThreadMXBean/JFR cho allocation. |
| Heap-used delta lớn hơn payload | Array headers, TLAB, JVM allocations và metadata. | Không tính heapUsed như payload exact. |
| Heap-used delta nhỏ hơn per-thread allocated | Different scopes/accounting/reclamation và time. | Không so hai metric như cùng đại lượng. |
| `jcmd` không attach được | Thiếu JDK tools, quyền/PID namespace, container policy. | Dùng launcher logs/flags trong startup. |
| Process chết mà catch OOM không chạy | Epsilon/VM termination policy. | Quản lý job bằng process con + exit status. |
| Dùng cờ legacy báo unrecognized | Tùy chọn lỗi thời/đã bị gỡ. | Dùng flags chính thức của JDK đang chạy. |

**Đừng tự retry một ứng dụng sản xuất với collector khác nếu đây là bài test bắt buộc Epsilon.** Nếu VM từ chối option, đó là thất bại của test setup; cần ghi rõ để tránh báo cáo kết quả của một collector khác dưới nhãn Epsilon.

## 19. Bài tập thực hành

**Bài 1 — đọc lệnh:** Giải thích tại sao `java -XX:+UseEpsilonGC -version` có thể fail và viết lại lệnh đúng. **Đáp án:** cần `-XX:+UnlockExperimentalVMOptions` phía trước.

**Bài 2 — chạy thử an toàn:** Tạo thư mục riêng, lưu `EpsilonConfigCheck.java`, biên dịch `--release 11`, chạy dưới `-Xms64m -Xmx64m` với Epsilon. Kiểm `epsilon.status=ENABLED` và checksum 8128; **không yêu cầu bytes exact**.

**Bài 3 — đối chứng:** Chạy lại với `-XX:+UseG1GC` + unlock; giải thích vì sao `gc.collections.reported=0` có thể xuất hiện ở cả hai mà không có nghĩa cùng collector.

**Bài 4 — flag hidden:** Chạy `java -Xms64m -Xmx64m EpsilonConfigCheck` không unlock. Tại sao `FLAG_NOT_EXPOSED` không phải cùng `DISABLED`?

**Bài 5 — measurement:** Với Epsilon, 128 blocks × 32KiB tương ứng 4,194,304 requested payload bytes. `ThreadMXBean` báo 4,197,256 bytes. Phần chênh do những yếu tố nào? Có được suy ra array header cố định 2,952 bytes không? **Không**.

**Bài 6 — exit code:** Chạy `EpsilonLaunchSmokeTest.java`. Khi thiếu unlock, vì sao test phải assert nonzero exit của JVM con thay vì bắt Java exception từ `main`?

**Bài 7 — heap budget:** Nếu job cần cấp phát tổng 80MiB và container chỉ có budget heap 64MiB, nó có thể hoàn thành với Epsilon không? **Không thể kỳ vọng**, dù phần lớn objects chết sớm.

**Bài 8 — no reclamation:** Tại sao gọi `System.gc()` không tạo ra reclamation thực trong Epsilon? So với G1 ở tình huống nhiều objects unreachable.

**Bài 9 — Unified Logging:** Thêm `-Xlog:gc=info` vào hai lệnh và tìm dòng `Using Epsilon`/`Using G1`. Không coi warnings về `AlwaysPreTouch` là lỗi fatal.

**Bài 10 — JFR:** Tạo một recording ngắn với đủ heap headroom, mở bằng JMC; phân biệt allocation events với total object count.

**Bài 11 — time budget:** Khi Epsilon OOM, tại sao thêm `try/catch (OutOfMemoryError)` không bảo đảm giữ process sống? Thiết kế một parent/child process test có wall-time và memory limits.

**Bài 12 — vendor portability:** Một bản JVM không có `UseEpsilonGC` nhưng có no-op policy tên khác. Nêu cách tra tài liệu vendor/build và vì sao không thể đổi cờ mà vẫn coi đó là thí nghiệm HotSpot Epsilon giống hệt.

**Bài 13 — báo cáo:** Thiết kế bảng có JVM version/vendor, flags, workload, checksum, allocated bytes, heap delta, GC events, exit code, runtime và giới hạn ngoại suy.

**Bài 14 — JDK hiện hành:** Khi chuyển từ JDK24 sang JDK27, cần kiểm gì trước khi dùng lại benchmark? **Gợi ý:** flag support, current GC defaults, compilation/runtime version, VM options, output format, JFR/management modules.

## 20. Checklist triển khai công cụ theo option hiện hành

- [ ] Xác định chính xác `java -version`, vendor, VM và JDK runtime.
- [ ] Xác định mục đích là experiment Epsilon, không phải GC mặc định cho production.
- [ ] `UseEpsilonGC` tồn tại/được hỗ trợ trong build này; không suy từ source Java11.
- [ ] `UnlockExperimentalVMOptions` **đứng trước** `UseEpsilonGC`.
- [ ] Có heap `-Xms/-Xmx` hữu hạn và process/container memory limits.
- [ ] Có startup log `Using Epsilon` hoặc xác nhận cờ `UseEpsilonGC=true`.
- [ ] Không fallback silently sang GC khác khi test yêu cầu Epsilon.
- [ ] Workload hữu hạn, có checksum, không cố tình gây OOM trong JVM chính.
- [ ] Nếu test OOM, dùng process riêng, theo dõi exit status và log.
- [ ] Log GC dùng `-Xlog` hiện hành, không dùng cờ logging legacy.
- [ ] Phân biệt heap-used delta, per-thread allocated bytes, live/retained heap và RSS.
- [ ] Không dùng 0 GC collections làm bằng chứng chọn Epsilon.
- [ ] Khi bật JFR/profiling, tính cả instrumentation allocation vào budget.
- [ ] Ghi JDK/flags/heap/workload/seed, số đo động, trials và limitations.
- [ ] Chạy benchmark nhiều forks trước khi đưa ra tuyên bố throughput/latency.
- [ ] Có test target runtime Java11 thật nếu sản phẩm chạy Java11, dù source đã build `--release 11`.
- [ ] Không thay đổi `JAVA_TOOL_OPTIONS`/container flags của hệ thống production ngoài phạm vi thử nghiệm.

## 21. Tài liệu chính thức và nguồn kiểm chứng

1. [OpenJDK JEP 318 — Epsilon: A No-Op Garbage Collector (Experimental)](https://openjdk.org/jeps/318): mục đích, trade-offs và phân loại experimental từ Java 11.
2. [Oracle JDK 11 Release Notes — JEP 318 Epsilon](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html): xác nhận no-op GC chỉ cấp phát, không reclaim.
3. [Oracle Java SE 27 — java command specification](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): `UnlockExperimentalVMOptions`, `-Xms/-Xmx` và Unified Logging; dùng để đối chiếu release hiện hành.
4. [OpenJDK HotSpot source — gc_globals.hpp](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shared/gc_globals.hpp): `UseEpsilonGC` còn được định nghĩa là experimental trong source chính.
5. [OpenJDK HotSpot source — gcConfig.cpp](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shared/gcConfig.cpp): việc include Epsilon collector tùy cấu hình build.
6. [Java SE 11 — HotSpotDiagnosticMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html): đọc diagnostic VM options.
7. [Java SE 11 — ThreadMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.management/com/sun/management/ThreadMXBean.html): per-thread allocated bytes và limitations.
8. [Java SE 11 — MemoryMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap used/committed snapshots.
9. [Java SE 11 — RuntimeMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/RuntimeMXBean.html): runtime input arguments.
10. [Java SE 11 — Flight Recorder](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/module-summary.html): recording/profiling API.
11. [OpenJDK JMH](https://github.com/openjdk/jmh): repeatable microbenchmarks và GC profiler.
12. [Oracle JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): cập nhật các flags/JDK thành phần hiện hành.

**Kết luận:** Trên một **HotSpot có hỗ trợ Epsilon**, cách bật đúng cho Java 11 và những bản JDK hiện hành còn hỗ trợ cờ này là `-XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC`, kèm `-Xms/-Xmx` để **chặn rủi ro cạn heap** trong một process test riêng. Xác minh bằng **startup `Using Epsilon`** và `PrintFlagsFinal`/`HotSpotDiagnosticMXBean`; không dựa vào “0 lần GC”. Epsilon chỉ cấp phát, **không reclaim heap**, nên workload phải hữu hạn; thiếu heap có thể **kết thúc JVM ngay**. Đo allocated bytes qua counter/harness, dùng JFR/logs để chẩn đoán, ghi rõ vendor/JDK, và không lấy kết quả của JDK thử nghiệm làm cam kết hiệu năng production.