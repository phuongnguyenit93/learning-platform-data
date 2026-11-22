# Hành vi khi cạn bộ nhớ và giới hạn kịch bản với Epsilon GC (Java 11+)

## 1. Mục tiêu

**Epsilon GC** là garbage collector kiểu *no-op* có trong **OpenJDK/HotSpot từ Java 11** (JEP 318). Nó **vẫn phục vụ cấp phát Java objects** nhưng **không thực hiện thu hồi bộ nhớ**: khi một đối tượng hết tham chiếu và trở thành garbage, vùng heap từng được cấp phát cho đối tượng ấy không được tái sử dụng trong vòng đời tiến trình.

Vì vậy, với Epsilon, bài toán không chỉ là *“hiện còn bao nhiêu object sống?”* mà còn là *“từ lúc khởi động JVM đến giờ đã tiêu thụ tổng cộng bao nhiêu không gian cấp phát?”*. Dù ứng dụng liên tục bỏ tham chiếu tới mảng cũ, nó vẫn có thể cạn heap.

**Nội dung chính của bài học:**

- Epsilon cấp phát và cạn bộ nhớ khác G1/Serial/Parallel như thế nào.
- Ý nghĩa `-Xms`, `-Xmx`, heap `used/committed/max` và vì sao không thể lấy payload size làm mốc OOM chính xác.
- Kết quả của heap exhaustion: `OutOfMemoryError`, JVM termination và `ExitOnOutOfMemoryError`, cùng giới hạn của `catch`/shutdown hooks.
- Ví dụ Java 11 hoàn chỉnh có **3 modes** — `bounded`, `churn`, `retained` — để kiểm tra điều gì xảy ra với Epsilon và GC thông thường.
- Những kịch bản Epsilon **có giá trị** (memory budget test, short-lived jobs, benchmark có kiểm soát) và những kịch bản **không phù hợp** (backend dài hạn, stream processor, phép đo leak thuần).
- Cách thử nghiệm trên child JVM, kiểm tra exit code/GC flags và phân biệt heap OOM với native memory hoặc container OOM.

**Special Note:** Chỉ sử dụng kiến thức **còn áp dụng hiện nay**. Epsilon hiện vẫn là lựa chọn **thử nghiệm/chuyên biệt (experimental)** trong HotSpot, không phải một collector production mặc định; ví dụ chỉ dùng Java 11 public APIs và những JVM flags hiện còn được hỗ trợ trên HotSpot phù hợp.

## 2. Epsilon là no-op GC, không phải “GC chạy rất nhanh”

### 2.1. Nó có làm gì?

Epsilon quản lý một vùng heap dành cho các objects của JVM, hỗ trợ allocator thực hiện `new Object()`, `new byte[]` và những allocations cần thiết khi chương trình chạy. Cấp phát vẫn cần không gian còn trống.

Khác biệt cốt lõi: Epsilon **không có phase mark/sweep, copy, evacuate hoặc compact để thu hồi vùng của những objects đã chết**. Một object đã unreachable có thể không còn giá trị logic đối với chương trình, nhưng chỗ của nó vẫn bị tiêu thụ trong vùng cấp phát Epsilon.

```text
Java application
    |
    v
request new byte[1 MiB]
    |
    +--- Java heap còn chỗ ---> allocation thành công
    |
    +--- Java heap hết chỗ --> Epsilon không thu hồi
                                 |
                                 v
                           Java heap exhaustion
                           OOME / JVM termination
```

Một collector như G1 có thể cố gắng thu gom garbage, cập nhật heap free space rồi tiếp tục cấp phát. Epsilon **không thể** thực hiện bước đó. `System.gc()` không biến Epsilon thành collector thu hồi và không giúp tái sử dụng các object đã chết.

### 2.2. Ba khái niệm phải phân biệt

| Khái niệm | Ý nghĩa | Với Epsilon |
| --- | --- | --- |
| **Allocated bytes / cumulative allocation** | Những yêu cầu cấp phát xảy ra theo thời gian, có overhead/alignment | Tiêu thụ không gian heap, không có reclamation |
| **Reachable/live objects** | Đối tượng vẫn được tham chiếu qua các GC roots | Có thể là một phần nhỏ trong số đối tượng đã tạo |
| **Heap used** | Lượng heap JVM báo đang sử dụng tại mốc đo | Có xu hướng tăng do cấp phát; không được giảm bởi GC reclaim |

Đừng đồng nhất một đối tượng **unreachable** với một vùng memory **available for reuse** khi dùng Epsilon. Đây là hai khái niệm khác nhau.

### 2.3. Churn: chỉ giữ một mảng mà vẫn OOM

Ví dụ Java:

```java
static volatile byte[] last;

for (int i = 0; i < 100; i++) {
    byte[] buffer = new byte[1024 * 1024];
    buffer[0] = (byte) i;
    last = buffer;
}
```

Biến `last` được cập nhật liên tục, nên những mảng trước đó không còn được biến này giữ tham chiếu. Về logic, chương trình chỉ giữ **khoảng một mảng người dùng ở mỗi thời điểm**.

- **G1:** có thể thu gom các mảng cũ và cấp phát tiếp dưới heap nhỏ.
- **Epsilon:** không reclaim, nên heap bị lấp bởi *cả các mảng đã hết tham chiếu*.

```text
-Xmx32m; minh họa cơ chế, không phải heap layout chính xác.

Sau vòng 1:  [live A][      free .................. ]
Sau vòng 2:  [dead A][live B][free ............... ]
Sau vòng 3:  [dead A][dead B][live C][free ....... ]
Sau nhiều vòng:
             [dead arrays ...........][live][free nhỏ]

Khi một allocation tiếp theo không có đủ chỗ:
             Epsilon OOM, không có thu gom để tái sử dụng.
```

**Kết luận quan trọng:** OOM khi chạy Epsilon **không tự chứng minh memory leak**. Một workload chỉ tạo **temporary garbage** cũng sẽ hết heap nếu tổng cấp phát đủ lớn.

## 3. Heap hết chỗ thì điều gì xảy ra?

### 3.1. Java heap exhaustion

Nếu Epsilon không cấp phát được mảng/object, JVM có thể báo:

```text
Terminating due to java.lang.OutOfMemoryError: Java heap space
```

Đây là **thông báo quan sát được trên một HotSpot runtime trong bài test**, không phải câu chữ bảo đảm giống nhau giữa mọi JDK/vendor. JVM có thể in stack trace, in một thông báo termination đơn giản hoặc tạo những diagnostics khác tùy flags.

Khi Java heap exhausted, ứng dụng **không còn cơ chế reclaim của Epsilon để tự phục hồi**. Vì vậy, cần coi đây là lỗi nghiêm trọng của process. Trên nhiều bản HotSpot Epsilon, process **kết thúc ngay** thay vì truyền OOME qua một handler bình thường.

### 3.2. Vai trò của `ExitOnOutOfMemoryError`

HotSpot có tùy chọn:

```text
-XX:+ExitOnOutOfMemoryError
```

Khi bật, VM kết thúc nếu gặp `OutOfMemoryError`. Với Epsilon, HotSpot thường bật cờ này **mặc định khi chọn Epsilon nếu chưa có cấu hình riêng**, vì collector không có khả năng tái thu hồi chỗ đã tiêu thụ.

Kiểm tra cờ trên chính JVM hiện hành:

```bash
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -XX:+PrintFlagsFinal -version
```

Trong một lần kiểm thử, các giá trị đã quan sát:

```text
ExitOnOutOfMemoryError = true
UseEpsilonGC           = true
```

Không đồng nhất cách HotSpot xử lý với tất cả JVM implementations. Một số vendor hoặc bản phát hành có thể hiển thị flags/exit behavior khác nhau.

### 3.3. Có thể `catch (OutOfMemoryError)` rồi tiếp tục?

Không thiết kế như vậy. Ngay cả khi một cấu hình khác cho phép exception đi qua Java handler, **Epsilon vẫn không có GC reclaim**. Ghi log, tạo chuỗi, mở socket, flush dữ liệu hoặc gọi cleanup callbacks đều có thể cần allocation và thất bại tiếp.

```java
try {
    // Một thao tác có thể làm đầy heap.
} catch (OutOfMemoryError error) {
    // KHÔNG giả định đủ bộ nhớ để ghi log và xử lý tiếp.
}
```

Đây là **anti-pattern minh họa**, không phải mã phục hồi đáng tin cậy.

Cần chuẩn bị bên ngoài tiến trình:

- Child JVM dùng process riêng, có timeout và resource cap.
- Supervisors/orchestrators phát hiện exit nonzero.
- Tác vụ quan trọng phải có checkpoint, retry idempotent, transaction boundary.
- Metrics/logs quan trọng được ghi **trước khi** heap gần hết.
- Không coi JVM shutdown hooks hay `HeapDumpOnOutOfMemoryError` là bảo đảm tuyệt đối có thể hoàn tất sau Epsilon OOM.

### 3.4. Exit code không ổn định giữa các JVM

Trong một lần chạy thực tế, Epsilon OOM trả **exit code 3**; một case G1 heap OOM khác trả **exit code 1**. Hai giá trị đó **không phải hợp đồng Java SE**.

Với automation: cần kiểm tra exit **khác 0**, và xác nhận nguyên nhân từ log/runtime, không hardcode một mã số như chỉ báo duy nhất. Một nonzero exit do `Unrecognized VM option` hoặc sai classpath **không được nhận nhầm là Epsilon OOM test PASS**.

### 3.5. Phân biệt Java heap OOM và container OOM kill

`-Xmx` giới hạn **Java heap**, không giới hạn toàn bộ memory của tiến trình Java. Ngoài heap còn:

- Metaspace / class metadata.
- Thread stacks.
- Code cache/JIT.
- Direct `ByteBuffer` và native allocations.
- JNI, native libraries, runtime bookkeeping.

Một container với cgroup limit thấp có thể bị **OS OOM killer** giết process trước khi JVM báo `OutOfMemoryError: Java heap space`. Đó là tình huống khác, cần xem container events, host logs, memory RSS và exit status.

| Hiện tượng | Dữ liệu cần kiểm tra |
| --- | --- |
| `Java heap space` với Epsilon | `-Xmx`, heap used, cumulative allocations |
| G1 Java heap OOME | Live set, GC logs, retention, Xmx |
| Direct/native memory issue | RSS, direct buffers, native tracking |
| Container OOMKilled | Cgroup/OS/container event logs |
| Metaspace OOME | Class loading, metaspace limits |

## 4. `-Xms`, `-Xmx` và ngưỡng cấp phát

### 4.1. Đặt giới hạn nhỏ khi test

```text
-Xms32m    # Yêu cầu heap ban đầu khoảng 32 MiB
-Xmx32m    # Đặt giới hạn tối đa khoảng 32 MiB
```

Khi bằng nhau, quá trình thử nghiệm dễ so sánh vì hạn chế biến số heap mở rộng. Nhưng **không có nghĩa bạn cấp phát được đúng 32 mảng 1 MiB** rồi mới OOME.

Java arrays còn object headers, alignment; class loading, runtime helper structures và TLAB management cũng dùng heap. Vì vậy chương trình có thể hết chỗ **sớm hơn tổng payload 32 MiB**.

### 4.2. Heap metrics qua `MemoryMXBean`

Public API Java 11:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

MemoryUsage usage = ManagementFactory
        .getMemoryMXBean()
        .getHeapMemoryUsage();

long used = usage.getUsed();
long committed = usage.getCommitted();
long max = usage.getMax();
```

Đây là **snippet**, cần đặt trong class/method. `used` phản ánh sử dụng heap tại thời điểm đọc; `committed` là memory đã cam kết; `max` là giới hạn heap (nếu runtime có dữ liệu). **Heap committed không đồng nghĩa heap used**, và cả hai không phải RSS.

### 4.3. Vì sao không dùng “heap used tăng từng MiB chính xác”?

- `byte[1 MiB]` có header và alignment.
- Có allocations khác từ thư viện, JVM và logging.
- TLAB waste và allocator policies ảnh hưởng.
- JIT/escape analysis có thể thay đổi lượng allocation thực tế trong những pattern nhất định.
- Metrics đọc một snapshot chứ không phải bộ đếm byte chính xác cho từng dòng.

Trong bài test, ta xác minh rằng heap used **tăng** khi giữ 4 mảng, nhưng không assert mức tăng đúng `4 * 1024 * 1024`.

## 5. Epsilon có ý nghĩa trong những kịch bản nào?

### 5.1. Kiểm thử ngân sách cấp phát

Với một tác vụ hữu hạn như parse/transform/generate report ngắn:

1. Chạy workload với Epsilon và `-Xmx` dự kiến.
2. Nếu hoàn tất, đó là bằng chứng một workload **cụ thể** không làm cạn heap theo cấu hình ấy.
3. Nếu OOM, có thể do tổng allocations vượt budget, dù live set nhỏ.
4. Xem source của allocations; giảm chuyển đổi chuỗi, boxing, duplicate buffers hoặc giảm tổng công việc.
5. Chạy lại với input cực hạn, nhiều kích thước payload và concurrency.

**Giới hạn:** một test Epsilon hoàn tất không phải bằng chứng “không có leak”, không phải bảo đảm mọi production workload đều an toàn, và không chứng minh process RSS ≤ `-Xmx`.

### 5.2. So sánh chi phí GC trong benchmark

Epsilon giúp tạo một **baseline không chạy các chu kỳ reclamation** để so với collector có GC. Nhưng chỉ so khi **cả hai process hoàn tất cùng lượng công việc** và Epsilon còn đủ heap.

Không suy luận máy móc:

```text
time(G1) - time(Epsilon) = chính xác CPU time của GC
```

Chênh lệch có thể đến từ allocator, TLAB, barriers, memory layout, JIT optimization, heap pressure hoặc cache behavior. Muốn kết luận, phải dùng thời gian đo đủ dài, các lần chạy lặp lại, thống kê variance, GC logs, CPU, RSS, throughput và latency.

### 5.3. Short-lived jobs có ngân sách biết trước

Một job chạy rất ngắn, tạo lượng object **hữu hạn**, kết thúc process ngay sau khi xong có thể không cần reclamation. Epsilon có thể giảm chi phí đặc biệt trong trường hợp này, nhưng phải:

- Đo cumulative allocation budget **thực tế**.
- Đặt giới hạn input, thời gian, retries và concurrency.
- Có margin cho warm-up/class loading/JIT/libraries.
- Có process isolation và recovery khi OOM.
- So với collector thông thường, chỉ chọn Epsilon nếu lợi ích đủ rõ.

**Không chọn Epsilon cho web server, stream processor hoặc consumer chạy liên tục**, vì các yêu cầu cấp phát không ngừng sẽ làm cạn heap theo thời gian ngay cả khi không có retention leak.

### 5.4. Bảng tình huống

| Tình huống | Epsilon phù hợp? | Lý do |
| --- | --- | --- |
| Unit/integration test memory budget | Có, nếu cô lập process | OOME đánh dấu budget exhaustion |
| Benchmark micro/short task đủ heap | Có thể | So hiệu năng với các collectors |
| Batch rất ngắn, input giới hạn | Có thể, sau kiểm thử | Tổng allocations có thể nằm trong ngân sách |
| HTTP API server 24/7 | Thường không | Mỗi request tiếp tục cấp phát |
| Stream pipeline có retry/backpressure | Thường không | Tổng số objects tăng theo runtime |
| Memory leak profiling/live set | Không thay thế GC bình thường | Epsilon không reclaim, không tạo heap-after-GC |
| App cần tiếp tục hoạt động sau OOME | Không | Không có đường reclaim, thường exit |
| Container RAM rất hạn chế không kiểm soát RSS | Rủi ro lớn | Native + heap có thể vượt giới hạn |

## 6. Chương trình Java 11 hoàn chỉnh: ba mode để chứng minh cơ chế

Mục tiêu của ví dụ là **không phụ thuộc Internet hoặc thư viện ngoài JDK**. Chỉ cần JDK có HotSpot Epsilon GC và một thư mục thử nghiệm riêng.

- `bounded`: giữ 4 mảng 1 MiB, dùng Epsilon với heap 32 MiB và in số arrays/GC counter.
- `churn`: tạo 100 mảng 1 MiB, nhưng `last` là tham chiếu duy nhất tới mảng mới nhất của workload. Với G1, mảng cũ có thể được thu hồi; với Epsilon, tổng cấp phát tiến tới OOME.
- `retained`: giữ tất cả mảng trong `HELD`; với heap 32 MiB, một collector bình thường cũng không thể chứa 100 MiB payload còn reachable.

**Mỗi mode phải chạy trong một JVM process mới.** Không gây OOM có chủ đích trong JVM đang chạy service hoặc trong cùng process với test runner.

### 6.1. Tệp `EpsilonExhaustionLab.java`

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.util.ArrayList;
import java.util.List;

public class EpsilonExhaustionLab {
    private static final int MIB = 1024 * 1024;
    private static final List<byte[]> HELD = new ArrayList<>();
    private static volatile byte[] last;

    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException("mode: bounded, churn, or retained");
        }
        String mode = args[0];
        switch (mode) {
            case "bounded":
                runBounded();
                break;
            case "churn":
                runChurn();
                break;
            case "retained":
                runRetained();
                break;
            default:
                throw new IllegalArgumentException(mode);
        }
    }

    private static void runBounded() {
        MemoryMXBean heap = ManagementFactory.getMemoryMXBean();
        long usedBefore = heap.getHeapMemoryUsage().getUsed();

        for (int i = 0; i < 4; i++) {
            byte[] buffer = new byte[MIB];
            buffer[0] = (byte) (i + 1);
            HELD.add(buffer);
        }

        System.out.println("mode: bounded");
        System.out.println("retained arrays: " + HELD.size());
        System.out.println("retained payload MiB: " + HELD.size());
        System.out.println("heap used increased: " +
                (heap.getHeapMemoryUsage().getUsed() > usedBefore));
        long count = 0;
        boolean counterKnown = true;
        for (GarbageCollectorMXBean gc :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            if (gc.getCollectionCount() < 0) {
                counterKnown = false;
            } else {
                count += gc.getCollectionCount();
            }
        }
        System.out.println("GC counter available: " + counterKnown);
        System.out.println("observed GC count: " + count);
    }

    private static void runChurn() {
        System.out.println("mode: churn");
        System.out.println("live user arrays at once: ~1");
        for (int i = 0; i < 100; i++) {
            byte[] b = new byte[MIB];
            b[0] = (byte) i;
            last = b;
        }
        System.out.println("finished allocations: 100");
    }

    private static void runRetained() {
        System.out.println("mode: retained");
        for (int i = 0; i < 100; i++) {
            byte[] b = new byte[MIB];
            b[0] = (byte) i;
            HELD.add(b);
        }
        System.out.println("finished retained allocations: 100");
    }
}
```

### 6.2. Biên dịch

```bash
javac --release 11 -encoding UTF-8 EpsilonExhaustionLab.java
```

`--release 11` đảm bảo source/API Java 11, dù compiler chạy từ JDK mới hơn. Epsilon là JVM-specific GC: không phải mọi JVM implementation có `-XX:+UseEpsilonGC`.

### 6.3. Chạy `bounded` với Epsilon: dự kiến thành công

```bash
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -Xms32m -Xmx32m EpsilonExhaustionLab bounded
```

**Stdout chính xác trong lần test đã thực hiện (6 dòng):**

```text
mode: bounded
retained arrays: 4
retained payload MiB: 4
heap used increased: true
GC counter available: true
observed GC count: 0
```

Exit code trên máy thử nghiệm: **0**. Hai dòng `GC counter` phụ thuộc sự hỗ trợ của Management MXBeans và JVM runtime; nếu counter không xác định có thể xuất giá trị khác. Nguyên tắc cố định của Epsilon vẫn là **không reclaim**.

### 6.4. Chạy `churn` với G1: đối chứng có reclamation

```bash
java -XX:+UseG1GC -Xms32m -Xmx32m EpsilonExhaustionLab churn
```

**Stdout đã kiểm thử:**

```text
mode: churn
live user arrays at once: ~1
finished allocations: 100
```

Exit code **0** trong lần chạy. Tổng payload của 100 lượt là 100 MiB nhưng chỉ giữ khoảng một mảng trong biến `last`; G1 thu hồi những mảng cũ nên có thể chạy dưới heap 32 MiB.

Đây là kết quả thử nghiệm với một HotSpot runtime cụ thể. Đừng dùng nó như một cam kết nếu thay GC flags, heap sizing, CPU pressure, JDK vendor hoặc dữ liệu workload.

### 6.5. Chạy `churn` với Epsilon: negative case

**Chỉ thực hiện ở môi trường lab/CI có process isolation.**

```bash
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -Xms32m -Xmx32m EpsilonExhaustionLab churn
```

**Output đã quan sát:**

```text
mode: churn
live user arrays at once: ~1
Terminating due to java.lang.OutOfMemoryError: Java heap space
```

Exit code của lần chạy: **3** (nonzero). Hãy kỳ vọng **failure do heap exhaustion**, không hardcode exit=3 trên mọi JDK. Thông báo có thể xuất hiện ở stderr và có hình thức khác.

Sự khác biệt với G1: **chỉ giữ khoảng một mảng nhưng Epsilon vẫn cạn heap**. Đây là phép chứng minh trực quan rằng Epsilon không thu hồi garbage.

### 6.6. Chạy `retained` với G1: đối chứng live set vượt ngân sách

```bash
java -XX:+UseG1GC -Xms32m -Xmx32m EpsilonExhaustionLab retained
```

Trong test, G1 cũng OOM, exit code **1**, vì chương trình cố giữ 100 mảng × 1 MiB trong `HELD`, nhiều hơn heap 32 MiB. Đây là trường hợp **live set thực sự vượt ngân sách**, khác với churn. Không cố gắng đo chính xác số mảng đã giữ ở thời điểm lỗi vì còn overhead và phụ thuộc JVM.

| Mode | Collector | Kết quả đã kiểm thử |
| --- | --- | --- |
| `bounded` | Epsilon | Thành công, 4 mảng retained, exit 0 |
| `churn` | G1 | Thành công 100 allocations, exit 0 |
| `churn` | Epsilon | Hết heap, nonzero exit |
| `retained` | G1 | Hết heap, nonzero exit |

**Kết luận quan trọng:** G1 có thể reclaim garbage của churn nhưng không thể reclaim những arrays còn reachable trong retained. Epsilon không reclaim trong cả hai trường hợp; việc heap cạn khi churn **không đủ** để nói ứng dụng có leak.

## 7. Quy trình thử nghiệm an toàn trong PowerShell hoặc CI

Chạy bốn lệnh Java phía trên trong **bốn child processes**. Nếu muốn tự động kiểm tra exit status trên Windows PowerShell:

```powershell
java '-XX:+UnlockExperimentalVMOptions' '-XX:+UseEpsilonGC' '-Xms32m' '-Xmx32m' EpsilonExhaustionLab bounded
if ($LASTEXITCODE -ne 0) { throw 'bounded expected success' }

java '-XX:+UseG1GC' '-Xms32m' '-Xmx32m' EpsilonExhaustionLab churn
if ($LASTEXITCODE -ne 0) { throw 'G1 churn expected success' }

java '-XX:+UnlockExperimentalVMOptions' '-XX:+UseEpsilonGC' '-Xms32m' '-Xmx32m' EpsilonExhaustionLab churn
if ($LASTEXITCODE -eq 0) { throw 'Epsilon churn expected failure' }

java '-XX:+UseG1GC' '-Xms32m' '-Xmx32m' EpsilonExhaustionLab retained
if ($LASTEXITCODE -eq 0) { throw 'G1 retained expected failure' }

Write-Output 'Epsilon experiment assertions passed'
```

Đây là **script minh họa dựa trên các lệnh Java đã kiểm thử**, không thay thế việc kiểm tra nguyên nhân OOME. Với CI thực tế, cần:

1. Chạy bounded trước để xác nhận Epsilon flags được runtime chấp nhận; nếu bounded không chạy thì không được coi OOME case là PASS.
2. Xác nhận negative cases **thất bại vì heap exhaustion**, không phải classpath/cú pháp flag/permission.
3. Đặt timeout và giới hạn tài nguyên.
4. Bảo vệ logs, giữ input giả và không dùng production secrets.
5. Xóa artifacts/process còn lại khi kết thúc.

Trên bash có `set -e`, lệnh OOM cố ý nonzero có thể chấm dứt script. Đặt lệnh trong `if` hoặc quản lý exit code đúng cách. **Không nuốt mọi nonzero** bằng cách vô điều kiện chuyển thành success.

## 8. Kiểm tra collector và bộ nhớ bằng công cụ JDK hiện hành

### 8.1. Xác nhận Epsilon được bật

```bash
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -Xms32m -Xmx32m -Xlog:gc -version
```

Một HotSpot runtime đã thử xuất dòng gần như:

```text
[...][info][gc] Using Epsilon
```

Timestamp, heap size metrics và các dòng log khác phụ thuộc runtime. Lệnh `-Xlog:gc` thuộc unified JVM logging được hỗ trợ từ Java 9 và hiện vẫn áp dụng.

### 8.2. Xác nhận cờ OOME

```bash
java -XX:+UnlockExperimentalVMOptions -XX:+UseEpsilonGC -XX:+PrintFlagsFinal -version
```

Xem `UseEpsilonGC`, `ExitOnOutOfMemoryError`, `MaxHeapSize` và các flag liên quan. Cờ Epsilon thuộc nhóm thử nghiệm trên HotSpot, cần đặt `-XX:+UnlockExperimentalVMOptions` **trước** `-XX:+UseEpsilonGC`.

### 8.3. Chọn thêm metrics

Có thể thu:

- Heap used/committed/max qua `MemoryMXBean` hoặc JVM diagnostic tools có hỗ trợ.
- GC events/allocations qua JFR trên workload **không cố làm OOM**.
- Process RSS và cgroup usage để hiểu native/heap tổng thể.
- Elapsed time, throughput, p95/p99 latency và số operation đã hoàn tất.
- Logs startup flags và JDK version/vendor để so được các lần thử nghiệm.

**JFR có thể hỗ trợ quan sát allocations khi Epsilon chạy**, nhưng nó không tạo một đường heap-after-GC giống G1. Không dùng recording Epsilon để kết luận object retention leak nếu chưa có phương pháp độc lập.

## 9. Giới hạn của Epsilon đối với phép đo và benchmark

### 9.1. Memory budget test không giống leak test

Một workload có **peak live heap 20 MiB** nhưng cấp phát tạm cộng dồn hàng trăm MiB trong suốt process có thể chạy ổn với G1 và `-Xmx64m`, nhưng OOM với Epsilon `-Xmx64m`.

Vì thế:

- Epsilon kiểm tra **cumulative allocation budget** trong một lần chạy.
- Collector có thu hồi giải quyết vấn đề **live object set và heap reclamation**.
- Khi nghi leak phải xem GC roots, strong references, cache/queue growth và heap-after-GC trends.
- Epsilon OOM không phân biệt được object đã chết và object còn sống chỉ từ thông báo lỗi.

### 9.2. Benchmark yêu cầu cùng lượng công việc hoàn tất

Khi một process Epsilon dừng sau 30 requests nhưng G1 xử lý được 10.000 requests, không được lấy elapsed time của hai lượt và so throughput/latency như thể cùng bài kiểm tra.

Cách làm đúng:

1. Cố định input, operations, concurrency và payload.
2. Chọn heap đủ lớn để Epsilon **hoàn tất toàn bộ workload**.
3. Chạy mỗi GC trong JVM mới, warm-up/measurement được quản lý.
4. Thu allocations, CPU, RSS, time, p95/p99 và GC logs.
5. Lặp nhiều lần, xem variance/confidence.
6. Không cho negative OOM runs vào số liệu hiệu năng bình thường.

**Không tuyên bố `time(G1) - time(Epsilon)` bằng GC CPU cost chính xác**: collector ảnh hưởng allocator/heap barriers/cache locality/JIT. Epsilon chỉ cung cấp một baseline thử nghiệm có những điều kiện khác.

### 9.3. Không cố “fix” bằng cách tăng heap mãi

Nếu ứng dụng liên tục cấp phát và không thể giới hạn tổng công việc, nâng `-Xmx` **chỉ trì hoãn** Epsilon OOM. Giải pháp để service chạy lâu là dùng một collector **có reclamation**, hoặc chia batch thành các JVM process hữu hạn, đủ ngân sách và có lifecycle/restart kiểm soát.

## 10. Những lỗi phổ biến

| Nhận định sai | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Epsilon rất nhanh nên vẫn có GC thu hồi” | Nó không reclaim | Hiểu đúng no-op collector |
| “Object unreachable tự được giải phóng” | Epsilon không reuse chỗ đó | Theo dõi cumulative allocations |
| “`System.gc()` sẽ cứu Epsilon” | Không có collection mechanism | Chọn collector có thu hồi |
| “Epsilon OOM nghĩa chắc chắn leak” | Churn cũng OOM dù không giữ mảng cũ | So retained vs temporary objects |
| “`-Xmx32m` = 32 mảng 1MiB” | Heap overhead, alignment, runtime allocations | Chỉ coi Xmx là giới hạn dung lượng heap |
| “Không có GC pause thì không có pause nào” | Vẫn có scheduling, I/O, JIT, safepoints | Đo latency end-to-end |
| “Có thể catch OOME rồi tiếp tục” | VM có thể exit, không có reclaim | Fail fast, supervisor/checkpoint |
| “Exit code Epsilon OOM phải bằng 3” | Không bảo đảm giữa VM/version | Kiểm tra nonzero + nguyên nhân |
| “Xmx giới hạn toàn bộ process memory” | Native/RSS ngoài heap | Theo dõi container/process memory |
| “Epsilon bounded pass = production an toàn” | Input/retries có thể vượt budget | Test stress và cực hạn |
| “Benchmark Epsilon OOM vẫn so được với G1” | Công việc hoàn thành không tương đương | Chỉ so completed workloads |
| “HeapDumpOnOOME luôn tạo được dump” | VM termination, permission, disk, native failure có thể cản | Không phụ thuộc một hook cuối |
| “Đổi GC giữa chừng bằng System.gc” | Collector được chọn khi JVM khởi động | Chạy separate JVM processes |
| “GC normally luôn cứu được retained case” | Live set có thể > heap max | Cần giảm retention/tăng capacity thích hợp |
| “Native Image `--gc=epsilon` là lệnh HotSpot” | Cú pháp khác hệ thống | Với HotSpot dùng `UseEpsilonGC` đúng cách |

## 11. Bài tập

**Bài 1 — Churn và retention.** Tại sao `churn` với G1 thành công nhưng Epsilon hết heap?  
*Đáp án:* G1 có thể thu hồi mảng cũ, Epsilon thì không.

**Bài 2 — Live set.** Tại sao `retained` khiến G1 cũng OOM với 32 MiB?  
*Đáp án:* `HELD` giữ 100 mảng xấp xỉ 100 MiB payload, không thể reclaim.

**Bài 3 — Exit behavior.** Nếu script thấy exit=3, có thể kết luận chắc chắn do Epsilon OOM?  
*Đáp án:* Không. Phải xác nhận flags, runtime, output và lỗi cụ thể.

**Bài 4 — Heap vs RSS.** Vì sao process có thể dùng nhiều hơn `-Xmx`?  
*Đáp án:* Metaspace, threads, native allocations, direct buffers, code cache nằm ngoài heap.

**Bài 5 — Phục hồi.** Cách nào phù hợp hơn catch OOME trong process?  
*Đáp án:* Child process/supervisor, retry idempotent, checkpoint và memory-budget control trước failure.

**Bài 6 — Đo lường.** Có thể lấy Epsilon OOM làm bằng chứng không có cache leak?  
*Đáp án:* Không. Cần retained references và heap-after-GC khi dùng collector thu hồi.

**Bài 7 — Benchmark.** Khi nào có thể so Epsilon và G1?  
*Đáp án:* Cùng input, cùng tổng completed work, heap đủ để Epsilon hoàn tất, JDK/version/flags được ghi nhận và có nhiều lần đo.

**Bài 8 — Tải thực.** Vì sao service liên tục không phù hợp Epsilon ngay cả khi request objects chỉ sống vài ms?  
*Đáp án:* Mỗi request tiếp tục cấp phát, không reclaim, cumulative budget sẽ cạn.

## 12. Checklist trước khi chọn Epsilon

- [ ] Mục tiêu là test, benchmark hoặc job rất ngắn chứ không phải backend chạy mãi.
- [ ] Runtime thực sự hỗ trợ Epsilon (`UseEpsilonGC` là cờ HotSpot thử nghiệm).
- [ ] Flags `-XX:+UnlockExperimentalVMOptions`, `-XX:+UseEpsilonGC`, `-Xmx` được đặt đúng.
- [ ] Đã kiểm tra `ExitOnOutOfMemoryError` theo runtime.
- [ ] Có ngân sách **tổng allocation** và margin cho runtime overhead.
- [ ] Có giới hạn input, concurrency, retries và job lifetime.
- [ ] OOM negative tests chạy ở child process cách ly.
- [ ] Có process exit handling, không trông chờ catch/hook cuối.
- [ ] Phân biệt Java heap OOME với native/container OOM.
- [ ] Không xem Epsilon OOM là chứng cứ memory leak.
- [ ] Benchmark so cùng lượng công việc hoàn tất.
- [ ] GC/heap/CPU/RSS metrics và JDK version được ghi lại.
- [ ] Không đưa secrets/PII vào test OOM hoặc diagnostic dump.

## 13. Ghi nhớ và tài liệu chính thức

**Epsilon cấp phát nhưng không thu hồi**; vì vậy nó có thể cạn heap ngay cả khi ứng dụng chỉ giữ một object đang sống tại mỗi thời điểm. **Khi heap cạn, JVM có thể báo OOME rồi dừng**, và Epsilon không có bước reclaim để phục hồi. Đây là điều hữu ích để kiểm thử memory budget nhưng là giới hạn cơ bản khi chạy lâu.

Bốn case của `EpsilonExhaustionLab` đã được chạy với `javac --release 11` và heap 32 MiB: Epsilon `bounded` thành công, G1 `churn` thành công, Epsilon `churn` hết heap, G1 `retained` hết heap. Chúng làm rõ **cumulative allocation khác retained live set**.

**Tham khảo chính thức, còn áp dụng:**

1. [OpenJDK JEP 318 — Epsilon, A No-Op Garbage Collector](https://openjdk.org/jeps/318).
2. [Oracle JDK 11 Release Notes — JEP 318 Epsilon](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html).
3. [Oracle Java 11 — Java launcher options](https://docs.oracle.com/en/java/javase/11/tools/java.html).
4. [OpenJDK source — UseEpsilonGC hiện vẫn có trong GC flags](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shared/gc_globals.hpp).
5. [OpenJDK Epsilon implementation — ExitOnOutOfMemoryError](https://cr.openjdk.org/~shade/8232051/webrev.01/src/hotspot/share/gc/epsilon/epsilonArguments.cpp.html).
6. [Oracle Java 11 — MemoryMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/MemoryMXBean.html).
7. [Oracle Java 11 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html).
8. [Oracle JDK 25 — Available Collectors](https://docs.oracle.com/en/java/javase/25/gctuning/available-collectors.html).

**Phạm vi lệnh:** Epsilon của HotSpot dùng `-XX:+UseEpsilonGC`. Đừng dùng hướng dẫn `--gc=epsilon` của **GraalVM Native Image** thay thế trực tiếp vào lệnh `java`, vì đó là công cụ/định dạng triển khai khác.