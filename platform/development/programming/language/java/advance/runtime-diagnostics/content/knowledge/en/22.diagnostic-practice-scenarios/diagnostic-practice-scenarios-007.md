# 22.7 Thu và phân tích GC log cùng JFR trong một giai đoạn cấp phát mạnh

## Mục tiêu và kết quả đầu ra

Một ứng dụng Java có thể **cấp phát rất nhiều object tạm thời** mà không hề bị memory leak. Khi allocation rate tăng, bộ thu gom rác (GC) thường hoạt động nhiều hơn, nhưng cần phân biệt **chính xác workload cấp phát**, **lần GC và thời gian pause**, **đối tượng/call site đóng góp nhiều allocation**, và **dữ liệu còn sống sau GC**.

Bài thực hành kết hợp hai công cụ có góc nhìn bổ sung:

- **Unified GC log** của HotSpot: ghi quá trình GC theo thời gian, ví dụ collector, GC ID, lý do, heap used trước/sau collection, thời lượng pause, các pha nếu được bật.
- **Java Flight Recorder (JFR):** thu event có timestamp cho GC, heap, CPU và *mẫu* allocation kèm class/stack; có thể thêm event tự định nghĩa để đánh dấu thời điểm bắt đầu/kết thúc phép thử.

Sau bài này, bạn có thể:

1. Chuẩn bị một chương trình **Java 17+ chạy được**, tạo một đợt allocation mạnh nhưng giữ rất ít dữ liệu sống lâu, không cần gây OOME.
2. Khởi động **cùng một tiến trình JVM** với GC unified logging và JFR, thu đủ hai artifact từ một lượt chạy.
3. Đọc `GC(n)`, `48M->4M(128M)`, `Pause Young`, thời lượng pause; tránh cộng trùng log của cùng GC.
4. Dùng `jfr summary`, `jfr print` và JDK Mission Control để xem các event `jdk.GarbageCollection`, `jdk.GCPhasePause`, `jdk.GCHeapSummary`, `jdk.ObjectAllocationSample` và event đánh dấu pha.
5. Ghép theo **timestamp và GC ID** để tạo timeline giữa pha cấp phát, allocation sample, GC pause và heap sau GC.
6. Phân biệt **allocation pressure**, **GC overhead**, **working set hợp lệ** và **giữ tham chiếu ngoài ý muốn**, với kết luận có điều kiện và công cụ kiểm chứng tiếp.

**Phạm vi:** HotSpot/OpenJDK Java 17+ với **G1GC** trong bài lab. Ví dụ và lệnh đã được chạy/kiểm tra với OpenJDK 24; nội dung nền áp dụng JDK 17/21 nhưng số lượng GC, symbol, event count và thời lượng thay đổi theo máy và bản JDK. Không lấy một lần chạy minh họa làm số chuẩn hiệu năng production.

## 1. Câu hỏi điều tra: allocation, GC hay leak?

Hãy đặt ba giả thuyết riêng trước khi thu dữ liệu:

| Giả thuyết | Dấu hiệu có thể quan sát | Chưa đủ để kết luận |
| --- | --- | --- |
| **Allocation churn** — nhiều object ngắn hạn | Allocation samples tập trung ở một call site; GC young xảy ra thường xuyên; heap used sau young GC trở về gần nền | Không tự chứng minh bug hoặc leak |
| **GC overhead ảnh hưởng latency** | Tổng/số lần stop-the-world pause tăng ở giai đoạn nóng; p95/p99 trùng hoặc gần những pause | Chỉ thấy GC hoạt động không chứng minh chính GC làm request chậm |
| **Retention / leak nghi vấn** | Heap used *sau các GC tương đương* tiếp tục tăng qua nhiều chu kỳ tải-hạ tải, kể cả khi công việc kết thúc | Không thể xác nhận leak chỉ từ số lần GC hoặc một ảnh chụp heap |

**Allocation rate** là lượng bộ nhớ được cấp phát trong một đơn vị thời gian. **Live set/retention** là lượng object vẫn còn reachable ở các thời điểm phù hợp. Hai khái niệm độc lập: một chương trình có thể cấp phát hàng gigabyte nhưng giữ lại rất ít, hoặc cấp phát chậm mà tích lũy hàng triệu object sống lâu.

Đọc hai nguồn cùng nhau:

```text
Application workload / object allocation
         |                         |
         |                         v
         |                 JFR allocation samples
         |                 (class, weight, stack, time)
         v                         |
Heap occupancy / GC triggers      |
         |                         |
         +----> Unified GC log <---+
         |       GC(n), before->after, pause, time
         |
         +----> JFR GC / heap events
                  startTime, gcId, pause, heap
         
Ghép theo timestamp + gcId + mốc pha của ứng dụng
=> giải thích khi nào, vì sao và ở đâu GC tăng
```

**Không đồng nhất** lượng byte chương trình yêu cầu tạo array với toàn bộ allocation mà JVM thực tế ghi nhận: ngoài object payload còn có header, alignment, các cấp phát khác, JIT/escape analysis và hoạt động nội bộ JVM.

## 2. Chuẩn bị môi trường đo an toàn

### Điều kiện cần

- JDK 17 trở lên có đủ `java`, `javac` và `jfr`. Ví dụ dùng JDK 24; với JDK 21 nên kiểm tra các tùy chọn bằng `java -Xlog:help` và `jfr help`.
- Một thư mục lab **riêng, có quyền ghi** để nhận `gc.log` và `burst.jfr`. Đặt tên/thư mục riêng cho mỗi lượt để không trộn artifact.
- Khoảng **128 MiB Java heap** cho JVM ví dụ cùng bộ nhớ ngoài heap hợp lý. Lượng cấp phát cộng dồn lớn hơn heap vì object cũ được thu gom liên tục; phép thử sẽ không cố giữ 468,75 MiB sống cùng lúc.
- Không chạy workload tạo hàng trăm MB allocation trên production hoặc môi trường có ít bộ nhớ/quota không rõ. Đây là **thí nghiệm kiểm soát trong máy phát triển/CI**.

Kiểm tra runtime:

```bash
java -version
javac -version
jfr help
java -Xlog:help
```

Dùng chung một bộ `java`/`javac`/`jfr` của JDK khi có thể. Ghi JDK vendor/version, OS, heap flags, GC, CPU quota và timestamp trước mỗi lần chạy. Nếu không dùng HotSpot hoặc đang dùng collector khác, định dạng log/JFR và chu kỳ GC có thể khác.

### Các artifact mục tiêu

| Artifact | Nguồn | Công dụng |
| --- | --- | --- |
| `GcJfrBurstLab.java` | Mã ví dụ bên dưới | Tạo pha baseline, burst và recovery; ghi event đánh dấu |
| `gc.log` | `-Xlog` của JVM | Các lần GC, heap trước/sau, pause và timestamps |
| `burst.jfr` | JFR khởi động cùng JVM | GC events, allocation samples, custom phase markers |
| `stdout` của chương trình | `System.out.println` | Xác nhận workload đã chạy và byte payload dự kiến |
| Nhật ký phân tích | Ghi tay hoặc công cụ riêng | Timeline/correlated findings và giới hạn phép đo |

Khi so các lượt, giữ cả artifacts của **cùng một PID/JVM**, không lấy GC log từ lượt A ghép JFR của lượt B.

## 3. Chương trình Java 17+ tạo pha cấp phát mạnh

Chương trình tạo 30.000 mảng `byte[]`, mỗi mảng chứa **16 KiB payload**. Mảng mới liên tục thay thế vị trí trong một vòng đệm chỉ **32 mảng**, nên hầu hết mảng cũ sẽ không còn được giữ sau khi vị trí bị ghi đè. Cuối pha, chương trình đọc lại dữ liệu trong ring để đảm bảo mảng có công dụng quan sát được; điều này hạn chế khả năng phép đo chỉ là mã đã bị compiler loại bỏ.

Bốn mốc tùy chỉnh `lab.AllocationPhase`:

- `baseline`: sau khi chương trình vào `main`.
- `burst-start`: ngay trước vòng cấp phát mạnh.
- `burst-end`: ngay sau vòng cấp phát; ghi tổng payload yêu cầu.
- `recovery`: sau một khoảng nghỉ để nhìn phần hoạt động sau burst.

**Lưu ý:** nghỉ 600 ms trước/sau chỉ tạo khoảng thời gian quan sát, không cam kết có GC trong lúc nghỉ và không thay thế đo leak qua nhiều chu kỳ.

### Mã hoàn chỉnh: `GcJfrBurstLab.java`

```java
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

public class GcJfrBurstLab {
    private static final int BLOCKS = 30_000;
    private static final int BLOCK_BYTES = 16 * 1024;
    private static volatile int retainedChecksum;

    @Name("lab.AllocationPhase")
    @Label("Allocation Phase")
    public static class AllocationPhase extends Event {
        @Label("Phase") public String phase;
        @Label("Nominal Allocated Bytes") public long nominalBytes;
    }

    private static void phase(String name, long nominalBytes) {
        AllocationPhase event = new AllocationPhase();
        event.phase = name;
        event.nominalBytes = nominalBytes;
        event.commit();
        System.out.println("phase=" + name);
    }

    private static int allocateBurst() {
        byte[][] ring = new byte[32][];
        for (int i = 0; i < BLOCKS; i++) {
            byte[] block = new byte[BLOCK_BYTES];
            block[0] = (byte) (i & 127);
            block[BLOCK_BYTES - 1] = (byte) (i >> 8);
            ring[i % ring.length] = block;
        }
        int checksum = 0;
        for (byte[] block : ring) {
            checksum += Byte.toUnsignedInt(block[0]);
        }
        return checksum;
    }

    public static void main(String[] args) throws Exception {
        phase("baseline", 0L);
        Thread.sleep(600);
        phase("burst-start", 0L);
        retainedChecksum = allocateBurst();
        phase("burst-end", (long) BLOCKS * BLOCK_BYTES);
        Thread.sleep(600);
        phase("recovery", 0L);
        System.out.println("blocks=" + BLOCKS);
        System.out.println("blockBytes=" + BLOCK_BYTES);
        System.out.println("nominalBytes=" + ((long) BLOCKS * BLOCK_BYTES));
        System.out.println("checksum=" + retainedChecksum);
    }
}
```

Giải thích về tính an toàn và ý nghĩa dữ liệu:

1. `byte[][] ring = new byte[32][]` giữ tối đa 32 array cùng lúc trong scope, nên không cố giữ tất cả 30.000 mảng. Phần ring có khoảng 32 × 16 KiB = 512 KiB **payload cuối**, cộng overhead object và các object khác.
2. `(long) BLOCKS * BLOCK_BYTES` tính ra **491.520.000 byte = 468,75 MiB payload danh nghĩa** được yêu cầu trong vòng lặp. Đây **không phải** kích thước live heap cuối cùng và cũng không phải tổng allocation của cả JVM.
3. Mốc JFR `phase("burst-start")`/`phase("burst-end")` giúp tìm đúng khoảng thời gian trong timeline; custom event không phải một lời gọi `System.gc()` và không tự ép thu gom rác.
4. `retainedChecksum` là field `volatile` và kết quả được in; phép tính có hiệu ứng quan sát. Nó không phải biện pháp thay thế JMH cho microbenchmark.
5. `Thread.sleep(600)` giúp phân chia pha rõ hơn trên timeline, nhưng scheduler có thể làm thời gian thực tế khác 600 ms.
6. Dữ liệu được tạo để quan sát **allocation churn**, không phải mô phỏng memory leak. Thay đổi chương trình để cố giữ vô hạn object hoặc tăng `-Xmx` có thể tạo một thí nghiệm hoàn toàn khác.

## 4. Thu GC log và JFR trong cùng một lượt JVM

### 4.1. Lệnh khởi động đã kiểm chứng

Tại thư mục chứa source, dùng Bash/Linux/macOS:

```bash
javac GcJfrBurstLab.java

java -Xms128m -Xmx128m -XX:+UseG1GC \
  '-Xlog:gc*=info,safepoint=info:file=gc.log:time,uptime,level,tags:filecount=1,filesize=20m' \
  '-XX:StartFlightRecording=filename=burst.jfr,settings=profile,dumponexit=true' \
  GcJfrBurstLab
```

Trong **Windows PowerShell**, có thể chạy câu lệnh Java trên **một dòng**, tránh dùng dấu `\` nối dòng của Bash:

```powershell
javac GcJfrBurstLab.java
java -Xms128m -Xmx128m -XX:+UseG1GC '-Xlog:gc*=info,safepoint=info:file=gc.log:time,uptime,level,tags:filecount=1,filesize=20m' '-XX:StartFlightRecording=filename=burst.jfr,settings=profile,dumponexit=true' GcJfrBurstLab
```

Lệnh chạy tốt với **OpenJDK 24 trên Windows** trong một phép kiểm tra thực. Với Java 17/21, syntax unified logging và Startup Flight Recording này có sẵn trên HotSpot, nhưng các event/default recording và số kết quả có thể khác; xác minh trên bản JDK của bạn.

**Từng flag làm gì?**

| Flag | Vai trò |
| --- | --- |
| `-Xms128m -Xmx128m` | Đặt heap initial/max cùng 128 MiB để phần heap capacity ổn định hơn; không hạn chế tổng process RSS bằng 128 MiB |
| `-XX:+UseG1GC` | Cố định G1 để ví dụ `Pause Young (G1 Evacuation Pause)` có ý nghĩa |
| `-Xlog:gc*=info,safepoint=info` | Thu thông điệp có tag GC (kể cả tổ hợp GC tags) và safepoint ở level info |
| `file=gc.log` | Ghi GC log ra file; chạy ở thư mục mới để tránh nhầm file cũ |
| `time,uptime,level,tags` | Hiển thị wall-clock timestamp (có múi giờ), JVM uptime và nhãn để đối chiếu JFR |
| `filecount=1,filesize=20m` | Cho phép log rotation có giới hạn trong demo; **phải kiểm tra tất cả file rotated** nếu chạy dài |
| `-XX:StartFlightRecording=...` | Khởi động JFR cùng tiến trình, tránh bỏ lỡ burst đầu tiên |
| `settings=profile` | Template có thêm dữ liệu profiling; tốn tài nguyên hơn `default` và không hứa mọi event đã bật |
| `filename=burst.jfr,dumponexit=true` | Ghi JFR ra file khi JVM thoát bình thường; không cam kết cứu đầy đủ khi `SIGKILL`/crash |

**Không chạy lại trong cùng thư mục** nếu còn cần so artifact cũ: `gc.log` hoặc `burst.jfr` có thể bị ghi đè. Trong dịch vụ/CI, dùng thư mục hoặc tên file riêng theo run ID và có chính sách retention. Nếu buộc phải giữ toàn bộ GC log dài hạn, chọn rotation size/count đủ cho cửa sổ cần điều tra; không chỉ nhìn file mới nhất khi có nhiều file xoay vòng.

### 4.2. Stdout đúng của chương trình

```text
phase=baseline
phase=burst-start
phase=burst-end
phase=recovery
blocks=30000
blockBytes=16384
nominalBytes=491520000
checksum=1008
```

Đây là **stdout xác định của ví dụ**, đã được biên dịch và chạy kiểm chứng bằng JDK 24. JVM còn có thể in thông báo khởi động JFR **riêng** ra console; thông tin startup như PID, filename và maxsize thay đổi. Số lượng GC, pause, allocation samples, thời điểm, dung lượng file và độ trễ cũng thay đổi giữa các lượt chạy.

### 4.3. Xác nhận đủ hai artifact

Sau khi Java process **kết thúc thành công**, kiểm tra:

```bash
ls -lh gc.log burst.jfr
jfr summary burst.jfr
```

PowerShell tương đương:

```powershell
Get-Item .\gc.log, .\burst.jfr | Select-Object Name,Length
jfr summary burst.jfr
```

Nếu `burst.jfr` không xuất hiện, kiểm tra exit code, JFR startup message, quyền ghi và việc tiến trình có thoát bình thường không. Nếu `gc.log` thiếu các event dự kiến, kiểm tra JVM có thực chạy với `-Xlog` không, collector/heap flags và log rotation. **Không đọc file tồn tại từ lần trước rồi tuyên bố phép thu lần này thành công.**

Có thể thu một recording trên JVM đã chạy bằng `jcmd <PID> JFR.start settings=profile ...` và dump khi cần; tuy nhiên cho bài này khởi động cả GC log/JFR **ngay từ đầu cùng một PID** giúp tránh lệch cửa sổ. Khi phải attach vào dịch vụ, đọc `jcmd <PID> help JFR.start`, `JFR.check` và kế hoạch vận hành riêng; JFR attach sau burst không thể phục hồi event đã qua.

## 5. Phân tích GC log: số lần GC, heap trước/sau, pause

### 5.1. Đọc header khởi động của JVM

Vì bật `gc*=info`, phần đầu file có thể liệt kê collector và các thông số:

```text
[...][info][gc     ] Using G1
[...][info][gc,init] Heap Initial Capacity: 128M
[...][info][gc,init] Heap Max Capacity: 128M
```

Các dòng trên được rút gọn từ **một lần chạy ví dụ**. Chúng xác nhận collector và heap limit, giúp tránh nhầm JVM thực tế dùng collector khác. `128M` là Java heap cap, **không phải toàn bộ RSS**, không bao gồm metaspace, thread stacks, code cache và nhiều vùng native.

### 5.2. Đọc một dòng Pause Young

Trong lần kiểm chứng với OpenJDK 24, có dòng:

```text
[2026-10-29T18:19:02.690+0700][0.835s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 48M->4M(128M) 2.355ms
```

Ý nghĩa từng phần:

| Phần | Giải nghĩa |
| --- | --- |
| `2026-10-29T18:19:02.690+0700` | Thời điểm log hiển thị theo wall-clock, gồm UTC offset |
| `0.835s` | Uptime của chính JVM tại thời điểm log; không phải số giây từ khi burst bắt đầu |
| `info` và `gc` | Log level và GC tag |
| `GC(0)` | GC ID của VM trong lượt chạy đó, có ích khi nối event JFR cùng `gcId` |
| `Pause Young (Normal)` | Một lần thu gom young generation có stop-the-world pause |
| `G1 Evacuation Pause` | Pha evacuation của G1 |
| `48M->4M(128M)` | Heap used **trước/sau** GC, và heap capacity được hiển thị (với flags demo là 128 MiB) |
| `2.355ms` | Thời lượng pause mà GC log báo cho lần thu gom này |

**Không đọc `48M->4M` thành “JVM đã giải phóng đúng 44 MiB object leak”.** Nó cho thấy heap used giảm ròng qua một lần young GC; phân tích nguyên nhân còn phụ thuộc allocation rate, vùng tuổi của object, promotions và collector.

### 5.3. Phân biệt log bắt đầu, kết thúc và pha chi tiết

Với `gc*=info`, cùng một GC có thể có nhiều dòng:

```text
[...][info][gc,start] GC(0) Pause Young (Normal) (G1 Evacuation Pause)
[...][info][gc]       GC(0) Pause Young (Normal) (G1 Evacuation Pause) 48M->4M(128M) 2.355ms
```

Cộng số dòng có chữ `Pause Young` thành số lần GC là **đếm trùng**. Chỉ đếm một dòng tóm tắt hoàn thành cho mỗi `GC(n)`; các dòng tag `gc,phases`, `gc,heap`, `gc,cpu` có thể mô tả chi tiết của cùng GC đó. Không cộng toàn bộ thời lượng pha con vào tổng pause nếu pha đã nằm bên trong pause tổng.

### 5.4. Kết quả GC thực nghiệm của một lần chạy

Đây là số liệu **đã thu trong một lượt ví dụ trên OpenJDK 24**, không phải output cố định cho mọi máy:

| GC ID | Heap used trước → sau (capacity) | Pause |
| --- | --- | ---: |
| `GC(0)` | 48M → 4M (128M) | 2.355 ms |
| `GC(1)` | 59M → 4M (128M) | 1.651 ms |
| `GC(2)` | 71M → 4M (128M) | 1.774 ms |
| `GC(3)` | 76M → 4M (128M) | 2.064 ms |
| `GC(4)` | 76M → 4M (128M) | 1.549 ms |
| `GC(5)` | 76M → 4M (128M) | 1.722 ms |
| `GC(6)` | 76M → 4M (128M) | 1.494 ms |
| **Tổng 7 pause** | — | **12.609 ms** |

Cách tính tổng trên là cộng **bảy thời lượng trên bảy dòng GC hoàn thành**, không phải cộng lại cả dòng `gc,start` hay các GC phase con. Số liệu dùng để học cách đọc; kết quả chạy của bạn có thể có ít/nhiều lần GC, mức heap sau GC khác, hoặc không cùng khoảng pause.

**Nhận xét hợp lệ của lượt này:** trong pha cấp phát mạnh, heap used tăng giữa các young GC nhưng giảm trở lại gần 4M sau từng lần; điều này **phù hợp với nhiều object ngắn hạn**. Nó không chứng minh toàn bộ ứng dụng không có leak, nhất là nếu phép thử quá ngắn hoặc chưa chạy các chu kỳ tải khác.

### 5.5. Các metrics cần rút ra

| Metric | Cách lấy | Giới hạn |
| --- | --- | --- |
| Số GC trong burst | Đếm GC IDs duy nhất có timestamp trong cửa sổ burst | Cần loại log bắt đầu/pha con và GC ngoài cửa sổ |
| Tổng GC pause | Cộng pause **tổng** của các GC thuộc cửa sổ | Không cộng các cấp GCPhasePauseLevel1/2/... như thể độc lập |
| Pause ratio trong cửa sổ | `sum(STW pause duration) / wall duration` | Không trực tiếp bằng %CPU GC; concurrent GC và queue latency khác |
| GC frequency | `số GC / thời gian quan sát` | Phụ thuộc heap size, workload, collector; không tự cho biết bug |
| Heap used sau GC | So các mốc **sau GC tương đương** | Young GC không loại bỏ mọi object old generation |
| Độ lớn vùng heap trước/sau | GC log occupancy | Không phải lượng byte phân bổ bởi tất cả objects trong kỳ |
| Throughput/latency ứng dụng | Metrics độc lập hoặc load-test | Không suy ra trực tiếp chỉ từ `gc.log` |

Nếu mục tiêu là latency người dùng, cần thêm request traces/metrics ở cùng timeline. Không có metric latency thì chỉ kết luận về **GC behavior trong lab**, không gọi GC pause là nguyên nhân của một SLO violation.

## 6. Đọc JFR: event GC và allocation sample

### 6.1. Kiểm tra danh mục/số event

Trong thư mục lab:

```bash
jfr summary burst.jfr
jfr metadata --events jdk.ObjectAllocationSample burst.jfr
jfr metadata --events lab.AllocationPhase burst.jfr
```

`jfr summary` cho số instance mỗi event type **đã được lưu trong file**; `metadata` mô tả schema, không phải bằng chứng đã có event instance. Ví dụ, một file có định nghĩa `jdk.ObjectAllocationSample` nhưng 0 instance có thể do chưa bật, không đủ activity, sampling/throttle hoặc cửa sổ không bao trùm burst.

**Một lần chạy được kiểm chứng** có các số sau:

```text
jdk.ObjectAllocationSample       120
jdk.GCHeapSummary                 14
jdk.GCPhasePause                   7
jdk.GarbageCollection              7
lab.AllocationPhase                4
```

Đây chỉ là **trích lược hai cột tên event và count** từ output `jfr summary`, không phải stdout nguyên văn của lệnh. 120 allocation samples **không có nghĩa chỉ có 120 object được cấp phát**; ứng dụng đã yêu cầu 30.000 array. Hai phép đếm có ý nghĩa hoàn toàn khác nhau.

### 6.2. Xem phase markers để xác định cửa sổ

```bash
jfr print --events lab.AllocationPhase burst.jfr
```

Trích một số dòng **từ lượt kiểm chứng**:

```text
lab.AllocationPhase {
  startTime = 18:19:02.082 (2026-10-29)
  phase = "baseline"
  nominalBytes = 0
}
lab.AllocationPhase {
  startTime = 18:19:02.683 (2026-10-29)
  phase = "burst-start"
  nominalBytes = 0
}
lab.AllocationPhase {
  startTime = 18:19:02.741 (2026-10-29)
  phase = "burst-end"
  nominalBytes = 491520000
}
lab.AllocationPhase {
  startTime = 18:19:03.342 (2026-10-29)
  phase = "recovery"
  nominalBytes = 0
}
```

Các mốc này cho biết chính chương trình bắt đầu/kết thúc vòng cấp phát; **không phải bốn GC**. `nominalBytes=491520000` là dữ liệu nghiệp vụ do code tự báo, không phải số byte JFR tự đo.

Trong dữ liệu này, khoảng `burst-start` → `burst-end` là **xấp xỉ 58 ms**, nhưng không dùng độ dài đó để tuyên bố throughput production. JIT, CPU, OS, GC, nền tảng và overhead từ JFR ảnh hưởng thời lượng. Nếu cần phân tích GC theo một pha, chọn đúng cửa sổ markers thay vì nhìn toàn bộ file.

### 6.3. Xem GC events và so với GC log

```bash
jfr print --events jdk.GarbageCollection burst.jfr
jfr print --events jdk.GCPhasePause burst.jfr
jfr print --events jdk.GCHeapSummary burst.jfr
```

Ví dụ `GCPhasePause` cho `gcId=0`:

```text
jdk.GCPhasePause {
  startTime = 18:19:02.688 (2026-10-29)
  duration = 2.30 ms
  gcId = 0
  name = "GC Pause"
  eventThread = "VM Thread" (...)
}
```

Cùng lần GC có dòng GC log `GC(0) ... 2.355ms` với timestamp gần nhau. **gcId và cửa sổ thời gian** củng cố rằng hai nguồn đang nói về cùng GC; sai khác nhỏ do vị trí đặt mốc, độ phân giải, rounding và định nghĩa thời lượng, không tự chứng minh log sai.

Phân biệt loại event:

| JFR event | Diễn giải | Không nên làm |
| --- | --- | --- |
| `jdk.GarbageCollection` | Thông tin về một lần collection, có `gcId`, name, cause và thời lượng/phần pause tùy JDK | Coi duration của concurrent cycle là toàn bộ STW pause |
| `jdk.GCPhasePause` | Một stop-the-world GC pause, có `gcId` và duration | Cộng thêm pha con `GCPhasePauseLevel1/2/3/4` vào tổng |
| `jdk.GCHeapSummary` | Heap snapshot tương ứng trước/sau GC, có `gcId`/`when`, dữ liệu heap | Coi heap committed là heap used hoặc RSS |
| `jdk.ObjectAllocationSample` | Mẫu allocation có object class, weight, thread, stack trace nếu được thu | Đếm sample như đếm chính xác số object |
| `lab.AllocationPhase` | Event tự định nghĩa để đánh dấu bước của bài lab | Coi custom marker là dữ liệu GC/JVM tự phát hiện |

Nếu `jdk.GCHeapSummary` có `when=Before GC` và `After GC`, so với occupancy của **cùng `gcId`**. Thuộc tính và cách hiển thị có thể đổi theo JDK/collector; kiểm tra schema bằng `jfr metadata` thay vì giả định mọi field xuất hiện.

### 6.4. Xem allocation samples để tìm class và call site

```bash
jfr print --events jdk.ObjectAllocationSample --stack-depth 8 burst.jfr
```

Ví dụ event trong lần chạy thử:

```text
jdk.ObjectAllocationSample {
  startTime = 18:19:02.683 (2026-10-29)
  objectClass = byte[] (classLoader = bootstrap)
  weight = 522.6 kB
  eventThread = "main" (javaThreadId = 3)
  stackTrace = [
    GcJfrBurstLab.allocateBurst() line: 28
    GcJfrBurstLab.main(String[]) line: 44
  ]
}
```

Diễn giải:

- **`objectClass=byte[]`**: loại object được lấy mẫu. Trong lab, chúng ta biết mảng được tạo trong `allocateBurst()`.
- **`stackTrace`**: giúp liên hệ allocation với call path; nếu thiếu, kiểm tra event settings/stackTrace và dữ liệu recorder.
- **`weight`**: **trọng số của mẫu** dùng cho ước lượng áp lực cấp phát khi tổng hợp đủ mẫu, không phải kích thước object đơn lẻ và cũng không phải số byte thực tế ứng dụng đã cấp phát ở thời điểm đó.
- **`eventThread=main`**: thread tại mẫu, không nói mọi allocation đều xảy ra từ một thread.

JFR allocation sampling là **thống kê**. Những event `jdk.ObjectAllocationInNewTLAB`/`OutsideTLAB` (nếu có/bật) có semantics khác và cũng không mặc định mô tả **mọi** object. Đừng cộng mọi loại event allocation với nhau như các nguồn đo độc lập rồi báo tổng byte chính xác. Nếu muốn biết class chiếm allocation nhiều nhất, dùng **weighted samples được tổng hợp đúng** trong JDK Mission Control hoặc công cụ hỗ trợ, sau đó kiểm tra call stacks.

Ngoài ra, 30.000 lần tạo `byte[]` trong mã Java không đảm bảo có đúng 30.000 allocation event: tùy compiler, JFR throttle/sampling, cache, framework và đường thu. Số **120 samples** không phải thiếu 29.880 event theo định nghĩa; nó là kết quả sampling.

## 7. Ghép GC log và JFR trên cùng timeline

Một báo cáo tốt cần thể hiện **mốc pha → allocation stack → GC event → heap/pauses → trạng thái sau burst**.

### 7.1. Chọn một hệ thời gian chung

GC log đã bật hai decorator:

- **`time`:** thời gian tuyệt đối có UTC offset, ví dụ `2026-10-29T18:19:02.690+0700`.
- **`uptime`:** số giây kể từ lúc JVM start, ví dụ `0.835s`.

JFR `jfr print` hiển thị `startTime` theo local timezone và có thể dùng timezone/format phụ thuộc công cụ. Khi ghép, cần kiểm tra **múi giờ, ngày, PID và JVM start time**. Không ghép các event chỉ vì có số giây giống nhau nhưng một bên là uptime và bên kia là wall-clock.

Trong lab này:

```text
JFR marker: burst-start          18:19:02.683
GC log:    GC(0) start           18:19:02.687
JFR:       GCPhasePause gcId=0   18:19:02.688, 2.30 ms
GC log:    GC(0) completed       18:19:02.690, 2.355 ms
...
GC log:    GC(6) completed       18:19:02.738
JFR marker: burst-end            18:19:02.741
JFR marker: recovery             18:19:03.342
```

Đây là timeline **trích từ một lượt kiểm chứng**. Bảy lần young GC khớp cửa sổ burst được đánh dấu. JFR và GC log dùng thời gian/gcId để làm **cross-check**, không chỉ một nguồn tự xác nhận chính nó.

### 7.2. Bảng phân tích giai đoạn

| Pha | Kỳ vọng ở chương trình | GC log | JFR |
| --- | --- | --- | --- |
| **Baseline** | Chưa bắt đầu vòng tạo 30.000 array | Có thể vẫn có hoạt động JVM startup/GC khác | Marker `baseline`; event trước pha nóng không tính vào burst |
| **Burst-start → burst-end** | Tạo byte arrays ngắn hạn, yêu cầu 491.520.000 byte payload | Thường nhiều young GC và heap occupancy tăng-giảm; phải đo thật | Allocation samples `byte[]` ở `allocateBurst()`; `GarbageCollection`/`GCPhasePause` gần cùng timestamp |
| **Recovery** | Vòng tạo object đã kết thúc, ứng dụng nghỉ ngắn | Có thể không có GC mới; heap used chưa chắc tự giảm nếu GC không chạy | Marker `recovery` và GC/heap events nào được thu |
| **Sau khi kết thúc process** | Chương trình thoát bình thường | `gc.log` đã được flush theo cơ chế log | `burst.jfr` được dump nhờ `dumponexit=true` |

**Đừng suy “heap còn cao ở recovery ⇒ leak”** nếu chưa có một GC thích hợp sau recovery. Heap usage có thể đang chứa garbage chưa thu và memory đã committed chưa nhất thiết trả ngay về OS. Cần so các mốc sau GC tương đương qua nhiều chu kỳ, không yêu cầu JVM phải luôn trả heap used bằng 0 sau khi ứng dụng nghỉ.

### 7.3. Đối chiếu theo `gcId`

Trong một HotSpot JVM, các event GC cùng một collection thường chia sẻ `gcId`, tương ứng nhãn `GC(n)` của GC log. Với demo, `GC(0)` đi cùng `jdk.GCPhasePause gcId=0`. Tuy nhiên nếu JFR được bật muộn, event bị lọc/mất, snapshot trích cửa sổ hẹp, hoặc collector có concurrent phases, **tổng số event không bắt buộc bằng số dòng log**.

Quy trình thủ công đáng tin:

1. Lấy thời gian của `burst-start` và `burst-end`.
2. Lọc các dòng **GC hoàn thành** trong khoảng đó; ghi `GC(n)`, type, before/after và pause duration.
3. Trong JFR, lọc `jdk.GarbageCollection`/`GCPhasePause` theo thời gian; ghi `gcId`, duration.
4. Nối trên `gcId` và đối chiếu timestamp; không nối theo thứ tự các dòng in ra nếu số event khác.
5. Từ JFR allocation samples trong **cùng khoảng pha**, chọn class và call stacks có trọng số cao, thay vì đọc tất cả sample trên toàn recording.
6. Từ `GCHeapSummary`/log after GC, xem heap có trở về gần baseline hay tăng bền qua nhiều pha.

### 7.4. Cách đọc khi số liệu hai nguồn không khớp

| Hiện tượng | Kiểm tra trước |
| --- | --- |
| GC log có 7 young GC, JFR chỉ thấy 5 | JFR start/end, retention, enabled, event types, thời gian export |
| GC log 2.355ms, JFR pause 2.30ms | Độ phân giải, rounding, thời điểm bắt đầu/kết thúc event; GC ID |
| JFR allocation sample 120, chương trình tạo 30.000 array | Sampling, throttle/weight, không phải nhật ký từng allocation |
| `jdk.GCHeapSummary` thấy heap lớn nhưng GC log after nhỏ | Đúng `when=Before/After`, `gcId`, đơn vị, heap used hay committed, collector |
| Có high allocation nhưng không có GC đáng kể | Heap đủ rộng, allocation nằm ngoài cửa sổ, JFR sample thiếu; kiểm tra data trước |
| Sau recovery heap chưa giảm | Không có GC ở recovery, object còn reachable hoặc GC policy giữ heap committed |
| JFR không có custom marker | Kiểm tra đúng file, event settings, JFR bắt đầu trước main và quá trình dump |

## 8. Đọc trong JDK Mission Control (JMC)

Nếu có JDK Mission Control, mở `burst.jfr` và kiểm tra theo thứ tự:

1. **General/Recording information:** start/end, duration, JVM/JDK, recording settings để chắc đây là file của lượt đo.
2. **Event Browser:** tìm `lab.AllocationPhase`, đọc bốn mốc, chọn **cửa sổ burst**.
3. **Memory/Allocations:** xem allocation pressure theo thời gian; group theo class và allocation stack. `byte[]` và `GcJfrBurstLab.allocateBurst` là đường dự kiến trong demo.
4. **Garbage Collections / GC Pauses:** đối chiếu số lần, loại GC, longest/sum of pauses, `gcId`/timestamp với file `gc.log`.
5. **Heap statistics/usage:** phân biệt used, committed, before/after GC; nếu event heap summary có nhiều snapshot, dùng cùng gcId.
6. **CPU and Threads:** xem workload có CPU saturation khác hoặc compiler/GC worker activity gây nhiễu không.
7. **Export notes:** lưu bảng timeline/các screenshot cần thiết, luôn ghi JDK/event settings và time range. Đồ thị tổng quan chỉ là diễn giải; giữ file gốc để kiểm toán.

**Không giả định mọi máy đều có JMC**, vì JMC là công cụ có thể cài riêng. Các lệnh `jfr summary`/`jfr print` của JDK vẫn cho phép làm bài. Nếu JMC đặt timezone/filter khác, đừng so từng nhãn giờ một cách máy móc; chuẩn hóa timezone trước.

## 9. Phân tích: allocation churn không phải memory leak

Trong lượt thực nghiệm:

- Chương trình yêu cầu tạo khoảng **468,75 MiB array payload** trong một đợt rất ngắn.
- Heap cap chỉ **128 MiB**.
- GC log ghi **7 lần young GC**; mức used sau mỗi young GC quan sát gần **4 MiB**, trong khi trước GC thường tăng đến vài chục MiB.
- JFR có **120 `jdk.ObjectAllocationSample`** và các sample `byte[]` từ `GcJfrBurstLab.allocateBurst()`.
- Bốn marker ghi rõ khi nào burst bắt đầu và kết thúc.

Dữ liệu trên **ủng hộ mạnh** nhận định rằng đợt cấp phát này chủ yếu tạo ra mảng ngắn hạn và GC có thể thu hồi phần lớn ở các lần young collection. **Chưa có bằng chứng leak từ phép thử ngắn này.** Nhưng không thể khẳng định mọi loại object đều ngắn hạn hay production chắc chắn không leak nếu không có thêm workload và thời gian đo.

### Để nghi retention/leak, cần thử thêm gì?

Thiết kế nhiều vòng **tăng tải → hạ tải → lặp lại**, với workload và concurrency đã cố định:

- Đo heap used sau các điểm GC có thể so sánh, không chỉ heap used trước GC.
- So lần trước và sau warm-up; tách cache/connection pool/session/index hợp lệ khỏi object không cần nữa.
- Nếu sau mỗi vòng số object reachable không còn cần thiết vẫn tăng, lấy heap dump/histogram và phân tích dominator/GC roots **theo chính sách vận hành**.
- Không ép `System.gc()` vô điều kiện như một “kiểm tra leak chuẩn”: nó thay đổi hành vi ứng dụng và tùy JVM có thể không chạy như mong đợi. Chỉ thực hiện phép thử GC có kiểm soát ở môi trường được phép.
- Kiểm tra direct buffers, JNI/native memory, metaspace và RSS nếu memory của process tăng mà Java heap/JFR object allocations không giải thích được.

### Khi nào gọi là GC performance problem?

Một hệ thống có allocation mạnh **chỉ thành vấn đề** nếu gây tác động đáng kể lên latency/throughput, CPU hoặc chi phí mà mục tiêu sản phẩm quan tâm. Cần thêm:

- **Request latency và SLO** cùng timestamp; có request overlap với GC STW pause không?
- **Sum of pauses / wall duration**, longest pause, GC frequency và GC CPU time nếu có. GC concurrent work không giống stop-the-world pause.
- **Allocation rate theo endpoint hoặc class/call stack** từ JFR weighted samples và metrics độc lập.
- **Cùng tải và cấu hình** để so trước/sau tối ưu: JDK, GC, heap, flags, payload, cache, RPS, concurrency, quota.
- **Can thiệp xác minh**: giảm allocation trong hot path, pool/cache hợp lý hoặc điều chỉnh cấu trúc dữ liệu, rồi đo lại p95/GC/alloc. Không bắt đầu bằng đổi GC flags theo cảm giác.

## 10. Các lỗi đo và diễn giải thường gặp

**1. Đếm hai dòng `GC(0)` thành hai collection.** Dòng `gc,start` và dòng tóm tắt hoàn thành có cùng GC ID. Đếm một lần theo ID và mục tiêu báo cáo.

**2. Cộng GC phase con lặp vào pause tổng.** `GCPhasePauseLevel1/2/3/4` có thể là các pha lồng nhau. Đừng cộng chúng vào `GCPhasePause` rồi kết luận ứng dụng dừng lâu hơn thực tế.

**3. Coi `48M->4M(128M)` là allocation chính xác 44 MiB.** Đây là heap occupancy trước/sau GC, không phải lượng đã cấp phát giữa hai GC hay số byte bị leak.

**4. Coi JFR allocation sample count là object count.** Sampling weight đại diện phép ước lượng; 120 samples không phủ định 30.000 lần tạo mảng.

**5. Cộng tất cả `weight` mà không kiểm tra cửa sổ và phương pháp tổng hợp.** Trọng số chỉ có ý nghĩa thống kê trong đúng event type/setting. Nếu JFR throttle hay sampling thay đổi, phép so giữa lượt A/B dễ sai.

**6. Coi `nominalBytes=491520000` là heap live size.** Đây là tổng payload yêu cầu bởi mã ví dụ; các array cũ bị ghi đè khỏi ring, GC có thể thu hồi liên tục.

**7. Ghép sai GC log và JFR từ hai lần chạy.** Phải giữ cùng JVM/PID, clock/timezone, file và runtime build; dùng marker/gcId và timestamp.

**8. So trực tiếp `uptime` GC log với thời gian JFR local.** Một bên là khoảng từ start, một bên là wall-clock. Phải quy về cùng hệ thời gian.

**9. Đọc file JFR trước khi process có cơ hội dump khi exit.** `dumponexit=true` của demo xuất khi thoát bình thường; nếu muốn snapshot giữa chương trình dài, dùng `jcmd JFR.dump` và xác minh file.

**10. Kết luận không có leak vì sau một young GC còn 4 MiB.** Old gen, cache hợp lệ hoặc leak chậm có thể không lộ ra trong một đợt ngắn. Cần theo dõi sau GC cùng điều kiện qua nhiều chu kỳ.

**11. Kết luận GC gây p95 cao khi chưa thu latency.** GC có pause nhưng chưa chắc trùng request bị chậm; cần metric/tracing ứng dụng và time alignment.

**12. Gắn `gc*=debug` hay full allocation tracing không giới hạn trên production.** Log rất chi tiết, JFR sampling dày và nhiều stack traces có overhead/file growth; đặt time window và storage budget.

**13. Bật JFR muộn khi burst đã qua.** Không thể hồi phục event đã xảy ra trước recording. Đặt JFR từ startup hoặc schedule capture đủ sớm.

**14. So kết quả với collector/heap khác mà không ghi nhận.** Cùng workload với G1/Parallel/ZGC có log types, pause distribution và event counts khác; đây là biến độc lập cần được kiểm soát.

**15. Chỉ xem Java heap mà bỏ RSS/native.** GC/JFR object allocation không đại diện mọi bộ nhớ ngoài heap. Metaspace, thread stacks, direct/native buffers và JNI có đường đo khác.

## 11. Thực hành mở rộng có đối chứng

Sau khi chạy đúng ví dụ gốc, có thể tạo ba lượt **trong thư mục riêng**, chỉ đổi một biến ở mỗi lượt:

| Lượt | Biến thay đổi | Dự đoán cần kiểm chứng |
| --- | --- | --- |
| A | `-Xms128m -Xmx128m`, code gốc | Nhiều young GC trong burst, JFR samples ở `byte[]` |
| B | Tăng heap phù hợp tài nguyên máy, giữ code/collector | Có thể ít GC hơn; không bảo đảm allocation payload giảm |
| C | Giảm `BLOCKS` theo hệ số xác định, giữ heap | Tổng payload giảm, GC pressure thường giảm; cần đo thật |

Nếu sửa source, phải biên dịch lại; so đúng cùng Java/JFR flags, workload và thời điểm. **Không dự đoán cứng số GC** vì collector heuristics và môi trường. Ghi output của từng lượt cùng `GC(n)`, pause sum, JFR allocation samples và phase timestamps.

### Bảng ghi kết quả

| Thông số | Lượt A | Lượt B | Lượt C |
| --- | --- | --- | --- |
| JDK/OS/G1/heap flags | | | |
| `BLOCKS` × `BLOCK_BYTES`, nominal bytes | | | |
| Marker burst-start/burst-end | | | |
| Số GC IDs trong burst | | | |
| Tổng STW pause trong burst | | | |
| Longest pause | | | |
| Heap used after GC cuối thuộc burst | | | |
| Event count `jdk.ObjectAllocationSample` | | | |
| Top allocation classes/call sites theo weights | | | |
| Ý nghĩa/giới hạn | | | |

### Câu hỏi tự kiểm tra

1. Có 30.000 lần `new byte[]` nhưng JFR chỉ có 120 allocation samples; có mất 29.880 object không? **Không thể suy thế.** Đây là sampled events, không phải log mỗi lần cấp phát.
2. `GC(0) 48M->4M(128M)` nói gì? **Heap used trước/sau một GC**, với heap capacity hiển thị 128 MiB; không phải 44 MiB leak.
3. Vì sao JFR `GCPhasePause gcId=0` và log `GC(0)` có thể có duration hơi khác? **Vì độ phân giải, rounding và điểm đánh dấu/định nghĩa**; cần xác nhận cùng GC và thời gian.
4. Nếu recovery marker đã xuất hiện nhưng heap chưa tự giảm, có leak không? **Chưa đủ.** Có thể chưa có GC sau recovery; cần các thời điểm sau collection so sánh được.
5. Vì sao phải lấy timestamp của burst thay vì xem toàn JFR? **Để loại hoạt động startup/background**, tập trung đúng khoảng cấp phát mạnh.
6. Vì sao tổng pause không bằng tổng CPU dùng cho GC? **Concurrent GC có CPU work ngoài stop-the-world pause**, và nhiều pha nằm trong pause tổng.
7. Nếu JFR không có `jdk.ObjectAllocationSample`, có nghĩa không cấp phát? **Không.** Xem profile/settings, sampling/throttle, recording window và artifact.
8. Khi nào cần heap dump? **Khi nghi retention kéo dài và cần tìm GC roots/owner**, không phải mặc định mỗi khi GC xảy ra nhiều.

## 12. Checklist trước khi chốt báo cáo

- [ ] Đúng một JVM run, ghi JDK build, collector, heap flags, PID, clock/timezone và thư mục artifact riêng.
- [ ] Cả `gc.log` và `burst.jfr` có thật, đọc được; kiểm tra exit status và log rotation.
- [ ] Có đủ bốn marker `baseline`, `burst-start`, `burst-end`, `recovery` ở đúng khoảng thời gian.
- [ ] GC log được đọc theo **GC ID duy nhất**, không đếm lặp dòng start/phase.
- [ ] Đã tách **heap used**, **heap capacity**, **total allocated payload**, **object sample weight** và **RSS**.
- [ ] Tổng pause được tính từ các STW pauses không lặp; không cộng nested phase.
- [ ] JFR event names/số instances, event enabled và sampling đã được kiểm chứng.
- [ ] Đã nối `GC(n)` với JFR `gcId` và timestamp trong cùng cửa sổ burst.
- [ ] Top allocation classes/call sites đến từ JFR; tránh coi sample count là object count.
- [ ] Không gọi leak từ một burst; nếu nghi giữ tham chiếu, có chu kỳ so sau GC và điều tra owner.
- [ ] Nếu kết luận tác động hiệu năng, có request latency/throughput metrics độc lập và bằng chứng thời gian.
- [ ] Đã ghi rõ **quan sát**, **giả thuyết**, **cách kiểm chứng** và giới hạn của demo.

**Kết luận:** Unified GC log cho biết *GC nào xảy ra, khi nào, heap used thay đổi ra sao và dừng JVM bao lâu*. JFR cho biết *sự kiện GC cùng gcId, mẫu object nào được cấp phát ở call stack nào và các mốc workload*. Khi ghép **GC ID + timestamp + phase markers** trong cùng một JVM, bạn có thể mô tả đợt **allocation churn mạnh** bằng bằng chứng hai nguồn mà không nhầm nó với **memory leak** hoặc một lỗi GC đã được chứng minh.

## Tài liệu tham khảo chính thức

- Oracle JDK 21 — `java`, Unified Logging, `-Xlog`, log decorators/rotation: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle JDK 21 — `jcmd`, `JFR.start`/`JFR.check`/`JFR.dump`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — `jfr` (`summary`, `print`, `metadata`): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Oracle JDK 21 — Diagnostic Tools and Flight Recorder: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle JDK 21 — HotSpot Garbage Collection Tuning Guide: https://docs.oracle.com/en/java/javase/21/gctuning/
- Oracle JDK 21 — `jdk.jfr` API: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html
