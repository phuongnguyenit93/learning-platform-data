# Unified logging bằng -Xlog:gc và các tag cần thiết — đo lường GC trong Java 15

> **Mục tiêu:** Nắm vững **Unified JVM Logging** của HotSpot qua tham số `-Xlog`, đặc biệt `-Xlog:gc`, `-Xlog:gc*` và các tổ hợp tag như `gc+phases`, `gc+heap`, `gc+ergo`, `gc+ref` và `safepoint`. Biết cách chọn level, xuất file, dùng decorators/rotation, tạo workload kiểm thử, đọc đúng GC pause và heap usage, chẩn đoán những trường hợp không thấy thông tin mong đợi, và quan sát JVM đang chạy bằng `jcmd VM.log`. Chủ đề thuộc nhóm **Đo lường GC** của **Java 15**, nhưng mọi cấu hình ưu tiên kiến thức **còn áp dụng trên HotSpot Java hiện đại**. Ví dụ đầy đủ dùng Java 17+ và đã được biên dịch, chạy trên OpenJDK 24 với G1.

## 1. Kết luận trước khi bắt đầu

**Lựa chọn lệnh theo mục đích:**

| Nhu cầu | Cấu hình JVM | Điều nhận được |
| --- | --- | --- |
| Xem hoạt động GC cơ bản | `-Xlog:gc` | Thông báo GC ở level `info` với **tag set chính xác `gc`**, thường có GC ID, pause, heap trước/sau |
| Xem mọi tag set chứa `gc` | `-Xlog:gc*` | Thêm log dạng `gc,heap`, `gc,phases`, `gc,start`… tại level `info` |
| Điều tra phases và memory | `-Xlog:gc*=info,gc+phases=debug,gc+heap=debug` | Tổng quan GC và chi tiết phases/heap (nếu collector phát ra tag tương ứng) |
| Xem safepoints bên cạnh GC | `-Xlog:gc*,safepoint*=info` | GC và các safepoint messages ở mức `info` |
| Ghi log phục vụ chẩn đoán | `-Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=10M` | GC log có time/tags, file rotation |
| Xem JVM hỗ trợ tag/decorator nào | `java -Xlog:help` | Danh sách **chính xác theo JVM** cùng cú pháp |
| Thay đổi cấu hình live JVM | `jcmd <PID> VM.log ...` | Xem/đổi logging khi JVM đang chạy, nếu được quyền attach |

**Phân biệt hai lệnh thường dễ bị nhầm nhất:**

- `-Xlog:gc` **không tương đương** `-Xlog:gc*`. Không có `*`, logger chỉ chọn **tag set đúng bằng `gc`**. Có `*`, logger chọn **các tag sets chứa `gc`**, kể cả khi kèm `heap`, `phases`, `start`…
- `-Xlog:gc*=info` không tự in mọi chi tiết `debug`/`trace`. Dấu `*` mở rộng **tag match**, không nâng **log level**. Cần thêm level cụ thể nếu muốn chi tiết.

Điều quan trọng nhất khi phân tích: **GC event/cycle**, **Stop-The-World pause**, **concurrent phase**, **heap used/committed** và **latency của API request** là các khái niệm khác nhau. Unified GC logging giúp quan sát collector, nhưng **không tự thay thế ứng dụng telemetry và profiling**.

## 2. Mốc phiên bản: Unified logging có từ JDK 9, vẫn dùng ở Java 15 và hiện nay

**Unified JVM Logging** ra đời từ **JEP 158 (JDK 9)**; **JEP 271 (JDK 9)** đưa GC logging vào framework này. Vì thế:

- Java 15 **không phải lần đầu xuất hiện `-Xlog:gc`**. Nó đã là cách chuẩn đo GC nhiều năm trước Java 15.
- Java 15 dùng cơ chế thống nhất cho GC và nhiều thành phần JVM khác.
- Java 17, 21, 24, 25 và các phiên bản HotSpot mới vẫn dùng `-Xlog` với selector, output, levels, decorators và file rotation.
- Phần **cú pháp chung** tương đối ổn định, nhưng **tags thật sự phát ra, phases, tên collectors, và ý nghĩa các trường nội bộ** có thể khác khi nâng JDK hoặc đổi collector.
- Cờ legacy như `-XX:+PrintGC`, `-XX:+PrintGCDetails`, `-Xloggc`, `-XX:+PrintGCDateStamps`… xuất hiện trong hướng dẫn Java 8 và đã được thay thế/deprecated/removed theo lộ trình JVM. **Không dùng chúng làm lệnh khuyến nghị cho dự án mới**.

Theo `java` man page của JDK 15 và JDK 25, `-Xlog:gc` và `-Xlog:help` vẫn là cách chính thức và có tài liệu. **Đừng lẫn `-Xlog` của JVM với `java.util.logging`, SLF4J, Logback hay Log4j**: chúng quản lý những lớp logging khác nhau, dù đôi khi doanh nghiệp gom log về cùng một hệ thống quan sát.

### GC logger không phụ thuộc loại collector nào?

Hạ tầng `-Xlog` là **chung của HotSpot**, nhưng **nội dung** phụ thuộc collector:

| Collector | Log có thể quan tâm | Lưu ý khi đọc |
| --- | --- | --- |
| **G1** | `gc`, `gc+phases`, `gc+heap`, `gc+ergo`, `gc+age`, `gc+region`, `gc+humongous` | Những tên phase như “Evacuate Collection Set” mang tính G1 |
| **ZGC** | `gc`, `gc+phases`, `gc+heap` và các tags được JVM hỗ trợ | Concurrent marking/relocation duration **không phải pause**; JDK24+ ZGC theo generational mode |
| **Shenandoah** | `gc`, `gc+phases`, `gc+heap`, các phase/tags có trong build | Concurrent mark/evac/update references; phase names và generational mode tùy JDK |
| **Parallel / Serial** | `gc`, `gc+heap`, `gc+phases` khi thực sự phát | Mô hình GC khác, không áp các giả định pause của ZGC/Shenandoah |

**Không có “universal GC line schema” đủ để suy ra toàn bộ ý nghĩa các trường mà không biết collector và phiên bản HotSpot.** Công cụ phân tích production cần kiểm tra tương thích với các JDK/GC configurations mà hệ thống đang chạy.

## 3. Cú pháp -Xlog:what:output:decorators:output-options

Cú pháp khái quát:

~~~text
-Xlog:<what>:<output>:<decorators>:<output-options>
~~~

Trong đó các thành phần **có thể được bỏ qua** từ phải qua trái hoặc dùng dấu `:` để để trống phần trung gian.

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `what` | Tag-selection(s) và level(s) | `gc*=info,gc+phases=debug` |
| `output` | Nơi gửi messages | `stdout`, `stderr`, `file=gc.log` |
| `decorators` | Trường tiền tố mỗi dòng | `time,uptime,level,tags,pid` |
| `output-options` | Tùy chọn output, đặc biệt với file | `filecount=5,filesize=10M` |

Ví dụ:

~~~bash
java -Xlog:gc*=info:file=gc.log:uptime,level,tags:filecount=5,filesize=10M MyApp
~~~

Đây là **lệnh shell**; `MyApp` là tên class thực tế của ứng dụng, không phải ví dụ Java có thể chạy nếu chưa có class này. Để chạy ngay, dùng `GcLoggingDemo` trong mục 10.

### Khi bỏ các thành phần

- `-Xlog:gc`: chọn tag set `gc` ở level mặc định `info`, output mặc định `stdout`, decorators mặc định `uptime,level,tags`.
- `-Xlog:gc*=info`: chọn tất cả tag sets chứa `gc` ở mức `info`.
- `-Xlog:gc::uptime,tid`: phần output giữa hai dấu `:` để trống, do đó dùng output mặc định nhưng đổi decorators.
- `-Xlog:gc=debug:file=gc.txt:none`: xuất đúng tag set `gc` ở mức debug ra file mà **không có decorators**.
- `-Xlog:help` là **lệnh trợ giúp**, không phải tag `help` trong GC.

**Lưu ý:** Khi dùng `-Xlog` không kèm selector, JVM có thể ghi rất nhiều log thuộc **mọi bộ phận HotSpot**, không chỉ GC. `-Xlog:disable` còn tắt cả cấu hình warnings/errors mặc định; đây **không phải cấu hình an toàn nên dùng chỉ để giảm noise của GC**.

## 4. Tag set: dấu cộng (+), dấu phẩy (,) và wildcard (*) khác nhau

Một thông điệp JVM được gắn với **một tập tags**, ví dụ:

~~~text
[gc]
[gc,start]
[gc,phases]
[gc,heap]
[gc,ergo,cset]
[safepoint]
~~~

**Tag selection** quyết định tập thông điệp nào được chọn.

### `gc` — exact match

~~~bash
java -Xlog:gc MyApp
~~~

Chọn các dòng với **đúng tag set `gc`** ở mức `info`. Dòng `[gc,heap]` hoặc `[gc,phases]` không tự được chọn bởi selector này.

### `gc*` — wildcard (at least these tags)

~~~bash
java -Xlog:gc*=info MyApp
~~~

Chọn mọi tag set **có chứa tag `gc`**, ví dụ `[gc]`, `[gc,start]`, `[gc,heap]`, `[gc,phases,start]`. Nhưng chỉ các messages có **level từ info trở lên về độ ưu tiên**; không tự thêm `debug`/`trace`.

### `gc+phases` — kết hợp AND, exact nếu không có *

~~~bash
java -Xlog:gc+phases=debug MyApp
~~~

`+` nghĩa một event cần **có cả hai tags**; không phải toán tử cộng cho mức log. Không có wildcard, cần **tag set chính xác** tương ứng. Ví dụ `[gc,phases,start]` có tag thứ ba thì không được match bởi selector exact này.

Nếu muốn mọi tag set **có cả gc và phases**, dù có thêm tag khác:

~~~bash
java -Xlog:gc+phases*=debug MyApp
~~~

### Dấu phẩy — nhiều selectors (OR)

~~~bash
java -Xlog:gc*=info,safepoint*=info MyApp
~~~

Hai selectors cùng tồn tại: match các messages chứa `gc` hoặc chứa `safepoint`. **Không nhầm** với `gc+safepoint` (chỉ match messages mang **cả hai tags**).

Ví dụ do Oracle công bố:

~~~bash
java -Xlog:gc,safepoint MyApp
~~~

Chỉ chọn các tag sets **đúng `gc` hoặc đúng `safepoint`** ở level info. Nó **không** chọn messages `[gc,safepoint]` vì cả hai selectors đều là exact. Khi cần comprehensive logging nên xem xét wildcard `gc*`/`safepoint*` tùy nhu cầu.

### Kết hợp selector có level riêng

~~~bash
java -Xlog:gc*=info,gc+phases=debug,gc+heap=debug MyApp
~~~

Cấu hình này được **chạy kiểm chứng thực tế** trong mục 11. Nó lấy tổng quan `gc*` mức info, đồng thời thêm **debug phases** và **debug heap** cho các tag sets phù hợp, mà không nâng mọi `gc*` lên debug.

**Ghi nhớ:** `*` là wildcard cho **tập tags**, không phải regex/glob nội dung thông điệp; `+` là “cùng tồn tại trong một event”; `,` là nhiều lựa chọn; `=debug` là **ngưỡng level**.

## 5. Log levels: INFO không phải DEBUG, DEBUG không phải TRACE

Các mức thường hỗ trợ:

| Level | Mục đích thực tế |
| --- | --- |
| `off` | Tắt selector/nhóm messages |
| `error` | Lỗi nghiêm trọng hơn |
| `warning` | Cảnh báo |
| `info` | Sự kiện tổng quan, phù hợp làm baseline |
| `debug` | Chi tiết hơn để phân tích GC/heap/phase |
| `trace` | Chi tiết sâu hơn, có thể rất nhiều dữ liệu |

Trên JVM HotSpot, khi chọn `=debug`, các messages phù hợp tags ở **debug và các mức ưu tiên cao hơn** (info/warning/error) được ghi. Chọn `=info` không thu thập các messages chỉ phát ra ở `debug` và `trace`.

**Không dùng `-Xlog:gc*=trace` vô thời hạn trong một ứng dụng tải lớn mà không kiểm tra dung lượng và CPU cost.** Trace có thể tạo nhiều logs và overhead, thậm chí làm méo kết quả latency benchmark. Để tìm bottleneck, thường bắt đầu bằng `gc*=info`, rồi bật đúng tag set ở `debug` trong phạm vi hẹp.

### Log config thay đổi độ nhiều của dữ liệu

| Config | Dữ liệu nhiều hay ít? | Đặt ở đâu? |
| --- | --- | --- |
| `-Xlog:gc` | Ít | Baseline nhanh, stdout |
| `-Xlog:gc*=info` | Trung bình | Quan sát thêm GC phases, heap tags ở info |
| `-Xlog:gc+phases=debug` | Chi tiết chuyên biệt | Phân tích phase timers |
| `-Xlog:gc+heap=debug` | Chi tiết heap | Capacity, regions, usage tùy collector |
| `-Xlog:gc*=debug` | Nhiều hơn | Chẩn đoán ngắn hạn |
| `-Xlog:gc*=trace` | Có thể rất nhiều | Debug chuyên sâu trong môi trường kiểm soát |

Những từ “ít/trung bình/nhiều” là **tương đối**, không phải cam kết số byte; mức output thay đổi theo frequency GC, collector, heap, workload và JDK.

## 6. Các tags GC nên biết và khi nào bật

Dùng `java -Xlog:help` trên **JDK đang chạy** để biết tag có tồn tại. Không phải mọi tag tương ứng đều phát event khi dùng mọi collector.

| Tag selection | Khi cần | Điều cần tránh |
| --- | --- | --- |
| `gc` | Tóm tắt cycles/pauses, collector được chọn | Tưởng nó bao cả heap/phase details |
| `gc*` | Tất cả tag sets chứa `gc` | Tưởng dấu * đồng nghĩa debug |
| `gc+phases=debug` | Chi tiết các bước và thời gian GC phases | Cộng hết durations thành STW time |
| `gc+heap=debug` | Heap sizes, vùng/regions, capacity | Coi heap committed là process RSS |
| `gc+ergo*=debug` | Quyết định ergonomic/heuristics của GC | Coi tên phase/tuning là chuẩn xuyên collector |
| `gc+ref=debug` | Reference processing (weak/soft/phantom) | Nhầm với mọi Java object reference read/write |
| `gc+age=trace` | Tuổi objects/survivors khi collector phát dữ liệu này | Áp dụng vô điều kiện cho ZGC/Shenandoah |
| `gc+region=trace` | Region-level diagnostics (đặc biệt G1) | Bật lâu dài không kiểm soát dung lượng |
| `gc+humongous=debug` | G1 humongous allocations/regions | Dùng sai cho collector không có khái niệm tương tự |
| `gc+remset=debug` | G1 remembered-set diagnostics | Nhầm remembered set với Java Set |
| `gc+metaspace=debug` | Metadata/metaspace liên quan GC nếu có messages | Coi `-Xmx` là giới hạn metaspace |
| `safepoint=info` | Safepoint timings thuộc JVM | Cho rằng mọi safepoint đều do GC |
| `safepoint*=debug` | Thông tin safepoint chi tiết hơn | Bật vô thời hạn mà không kiểm tra overhead |

**Chọn dựa trên điều bạn muốn trả lời:** Nếu câu hỏi là **“p99 tăng vì GC pause hay allocation stall?”**, cần ``-Xlog:gc*,safepoint*=info`` và application latency metrics, sau đó xem các tags đặc thù của collector. Nếu câu hỏi là **“bước G1 nào chiếm 80% pause?”**, thêm `gc+phases=debug`. Nếu câu hỏi là **“vì sao G1 chọn collection set này?”**, có thể cần `gc+ergo*=debug` hoặc collector-specific tags mà `-Xlog:help` liệt kê.

**Không suy rằng không có dòng `[gc,ref]` nghĩa Java không hề dùng WeakReference.** Level, heap pressure, GC algorithms và điều kiện phát event đều ảnh hưởng output.

## 7. Cấu hình có mục tiêu: từ tối thiểu đến phân tích sâu

### Preset A — xem GC cơ bản trên console

~~~bash
java -Xlog:gc -jar application.jar
~~~

Tương đương về lựa chọn tag+level với:

~~~bash
java -Xlog:gc=info:stdout:uptime,level,tags -jar application.jar
~~~

Log được viết ra **stdout**, còn ứng dụng của bạn có thể cũng ghi stdout/stderr. Nếu cần phân tích riêng GC và bảo toàn application logs, hãy định tuyến GC logging tới file riêng.

### Preset B — ghi mọi tag sets của GC ở INFO

~~~bash
java -Xlog:gc*=info:file=gc.log:time,uptime,level,tags -jar application.jar
~~~

Phù hợp khi muốn nhiều hơn GC summary nhưng chưa cần debug dày đặc. Đây vẫn chỉ là GC JVM logs, không bảo đảm có allocation profiling hoặc end-to-end traces.

### Preset C — phân tích GC phases và heap, kèm safepoint

~~~bash
java -Xlog:gc*=info,gc+phases=debug,gc+heap=debug,safepoint=info:file=gc-detailed.log:time,uptime,level,tags:filecount=3,filesize=10M -jar application.jar
~~~

Cấu hình **tag selector và levels** đã được chạy bằng JDK24/G1 trong mục 11. `filecount=3,filesize=10M` là lựa chọn ví dụ cho kiểm thử/diagnostics; cần chỉnh dung lượng lưu trữ production theo lưu lượng log thực tế.

### Preset D — chỉ xem reference/heap/ergonomics khi điều tra

~~~bash
java -Xlog:gc*=info,gc+ref=debug,gc+heap=debug,gc+ergo*=debug:file=gc-diagnostics.log:uptime,level,tags:filecount=5,filesize=20M -jar application.jar
~~~

Nếu collector/JDK không phát những tag sets ở level tương ứng, phần log đó có thể trống. **Không coi tag selection chỉ là tùy chọn “tăng độ nhạy”; nó phải khớp các tags thực tế của events.**

### Preset E — chỉ muốn safepoint diagnostics

~~~bash
java -Xlog:safepoint*=info:file=safepoints.log:time,uptime,level,tags -jar application.jar
~~~

Có thể xem safepoint timing independent với GC log. Khi phân tích một thời điểm p99 spike, so thời điểm trên **cùng trục thời gian** với tracing/metrics application và GC events.

### Preset F — local debug ngắn hạn

~~~bash
java -Xlog:gc*=debug:file=gc-debug.log:uptime,level,tags:filecount=2,filesize=10M -jar application.jar
~~~

Nếu muốn `trace` để xem rất sâu, chỉ bật trong môi trường đo lường có giới hạn thời gian và file rotation cụ thể. Log verbosity quá cao ảnh hưởng **I/O, CPU, disk và có thể cả behavior của workload đang đo**.

## 8. Output và decorators: làm log có thể đối chiếu với thời gian thật

Tùy chọn output:

- `stdout`: tiện trong local/container logging.
- `stderr`: phân biệt với stdout của ứng dụng; vẫn có thể được log collector hệ thống thu gom.
- `file=gc.log`: file riêng dễ quản lý rotation và parse.

Decorators hữu ích:

| Decorator | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `time` | Ngày/giờ ISO-8601, có timezone | `[2026-11-08T09:46:40.575+0700]` |
| `utctime` | Giờ UTC | So log giữa services/múi giờ |
| `uptime` | Thời gian JVM chạy đến event | `[0.044s]` |
| `uptimemillis` | Uptime milliseconds | Thuận tiện tính tương đối |
| `pid` | Process ID | Phân biệt nhiều JVM instances |
| `tid` | JVM thread ID | Debug đa luồng/thao tác event |
| `level` | Log level | `[info]`, `[debug]` |
| `tags` | Tag set | `[gc,phases]` |
| `none` | Không in decorators | Chỉ dùng khi thật sự muốn raw message |

Ví dụ có đầy đủ thông tin:

~~~bash
java -Xlog:gc*=info:file=gc-%p-%t.log:time,uptime,pid,level,tags:filecount=5,filesize=10M -jar application.jar
~~~

`%p` và `%t` trong **tên file** được JVM thay bằng PID và startup timestamp, giúp giảm rủi ro **nhiều instances ghi vào cùng file basename**. Cần kiểm tra thư mục log, quyền ghi, retention và volume có giới hạn nếu chạy container. Nếu đường dẫn có dấu cách, shell cần quote **toàn bộ option `-Xlog:...`** phù hợp.

**Lưu ý về correlation:** `uptime` giúp so events **trong cùng JVM lifetime**, còn `time` hoặc `utctime` giúp so với application logs, tracing và các dịch vụ khác. Nếu dùng time, phải chú ý clocks, NTP và timestamps của telemetry. Decorators chỉ là **metadata của log line**, không sửa Java heap hay GC scheduling.

## 9. File rotation và giới hạn dung lượng log

Unified logging hỗ trợ:

~~~text
filecount=<số_file_quay_vòng>,filesize=<ngưỡng_kích_thước>
~~~

Ví dụ:

~~~bash
java -Xlog:gc*=info:file=gc.log:uptime,level,tags:filecount=5,filesize=10M -jar application.jar
~~~

Theo `java -Xlog:help`, `filesize` nhận suffix `K`, `M` hoặc `G`. File rotation là **theo kích thước ghi log**, không phải theo “GC cycle” và không phải kích thước heap.

### Lệnh đã kiểm thử với giới hạn rất nhỏ

~~~bash
java -XX:+UseG1GC -Xms32m -Xmx64m -Xlog:gc*=debug:file=gc-rotate.log:uptime,level,tags:filecount=2,filesize=10K GcRotationDemo
~~~

Trong một thí nghiệm dùng chương trình `GcRotationDemo` ở mục 12, stdout:

~~~text
completed=true
~~~

Và các file đã quan sát:

~~~text
gc-rotate.log     284 bytes
gc-rotate.log.0 10399 bytes
gc-rotate.log.1 10463 bytes
~~~

**Giải thích:** Có một **active file** `gc-rotate.log` và hai rotated files (filecount=2); kích thước target `10K` chỉ mang tính gần đúng, không phải chính xác 10.240 bytes từng file. Đây là số liệu **của một lần chạy**, thay đổi theo version và workload.

**Chú ý:**

- `filecount=0` tắt rotation và có thể ghi đè log cũ có cùng tên.
- Nếu path/file name trùng giữa các instances, log có thể bị overwrite hoặc trộn/khó điều tra. Dùng `%p`/`%t` hoặc phân chia thư mục.
- Log rotation nội bộ JVM **không thay thế retention policy trên hệ thống lưu trữ**, upload tập trung và quota/cleanup khi chương trình tạo nhiều processes.
- Đừng bật `gc*=trace` rồi chỉ đặt một file cực nhỏ: bạn có thể **mất đúng khoảng log sự cố** vì files quay vòng quá nhanh.
- Filecount/filesize điều khiển **JVM log files**, không điều chỉnh collection set, young generation, -Xmx, hoặc cách G1 thu hồi rác.

## 10. Chương trình Java 17+ đầy đủ: tạo GC có thể quan sát

Tạo file **GcLoggingDemo.java**. Để có logs dễ quan sát trong thí nghiệm, chương trình liên tục cấp phát mảng 16 KiB với tổng cộng 60.000 lần, nhưng chỉ giữ một nhóm nhỏ trong một static array. Phần còn lại có thể trở thành unreachable khi những tham chiếu tạm thời không còn cần.

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;

public final class GcLoggingDemo {
    private static final byte[][] retained = new byte[96][];
    private static volatile long checksum;

    public static void main(String[] args) {
        final int allocations = 60_000;
        for (int i = 0; i < allocations; i++) {
            byte[] data = new byte[16 * 1024];
            data[0] = (byte) i;
            data[data.length - 1] = (byte) (i >>> 8);
            if ((i % 8) == 0) {
                retained[(i / 8) % retained.length] = data;
            }
            checksum += (data[0] & 0xff)
                    + (data[data.length - 1] & 0xff);
        }

        int reachable = 0;
        for (byte[] bytes : retained) {
            if (bytes != null) {
                reachable++;
            }
        }

        boolean gcCountPositive = false;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            long count = bean.getCollectionCount();
            if (count > 0) {
                gcCountPositive = true;
            }
        }

        System.out.println("allocations=" + allocations);
        System.out.println("retained=" + reachable);
        System.out.println("checksumPositive=" + (checksum > 0));
        System.out.println("gcCountPositive=" + gcCountPositive);
    }
}
~~~

### Tại sao code tạo GC logs?

- 60.000 lần cấp phát mảng 16 KiB tạo gần 1 GiB allocation throughput theo tổng lượng bytes yêu cầu, dù heap giới hạn chỉ 64 MiB và không cần giữ tất cả cùng lúc.
- Chỉ tối đa 96 slots trong `retained` giữ mảng còn reachable ở cuối. Những mảng bị ghi đè hoặc chỉ tồn tại trong vòng lặp có thể trở thành garbage.
- `checksum` khiến chương trình sử dụng dữ liệu của mảng mới cấp phát, giảm khả năng phép thử chỉ bị tối ưu đi.
- `GarbageCollectorMXBean.getCollectionCount()` giúp kiểm tra trên môi trường thử nghiệm đã có GC được ghi nhận. Số đếm **có thể là -1** nếu một bean không hỗ trợ; chương trình chỉ xét `>0`.
- `GcLoggingDemo` không tự gọi `System.gc()`; việc GC diễn ra do heap pressure và collector tự chọn, phù hợp quan sát bản chất thực tế.

**Điều không nên suy diễn:** số vòng lặp cố định không bảo đảm mỗi JVM/provider đều có đúng 37 GC log lines. Các JVM khác có thể có số cycles khác, capacity khác, hoặc compiler/GC heuristics khác. Số “96” đến từ cấu trúc array, không phải kiểm chứng GC đã compact bao nhiêu objects.

### Biên dịch

~~~bash
javac --release 17 -encoding UTF-8 GcLoggingDemo.java
~~~

Chương trình chạy với Java 17+ (khi JVM hỗ trợ các API chuẩn đó). `--release 17` chỉ là **compile target**; `-Xlog` và collector được chọn ở **runtime** bằng lệnh `java`.

### Chạy với -Xlog:gc (cơ bản)

~~~bash
java -XX:+UseG1GC -Xms32m -Xmx64m -Xlog:gc=info:file=gc-basic.log:uptime,level,tags GcLoggingDemo
~~~

### Chạy với -Xlog:gc*=info (nhiều tag sets)

~~~bash
java -XX:+UseG1GC -Xms32m -Xmx64m -Xlog:gc*=info:file=gc-all.log:uptime,level,tags GcLoggingDemo
~~~

### Chạy với phases+heap DEBUG và safepoint INFO

~~~bash
java -XX:+UseG1GC -Xms32m -Xmx64m -Xlog:gc*=info,gc+phases=debug,gc+heap=debug,safepoint=info:file=gc-detailed.log:time,uptime,level,tags:filecount=3,filesize=1M GcLoggingDemo
~~~

**Các lệnh đã được chạy và kiểm tra trên OpenJDK/Zulu 24.0.2.** `-XX:+UseG1GC` chọn G1 tường minh để mẫu log dễ đối chiếu. Nó là cấu hình **thí nghiệm**, không có nghĩa production luôn phải chọn G1. Heap `-Xmx64m` nhỏ để tạo nhiều GC nhanh, **không phải sizing khuyến nghị cho service thật**.

### Stdout từ cả ba lần chạy đã kiểm chứng

~~~text
allocations=60000
retained=96
checksumPositive=true
gcCountPositive=true
~~~

Đây là output của **ứng dụng**, không phải file GC log. Vì cấu hình dùng `file=...`, những log của JVM đi vào file tương ứng và không trộn với các dòng trên trong stdout ở thí nghiệm.

## 11. So sánh logs thực nghiệm: exact tag vs wildcard vs debug

Với **cùng source code**, cùng GC và cùng heap sizing, nhưng ba cách cấu hình log khác nhau, kết quả quan sát:

| File | Lệnh tag/level chính | Tổng số dòng trong lần thử | Những gì nhìn thấy |
| --- | --- | ---: | --- |
| `gc-basic.log` | `gc=info` | **37** | GC summary với `[gc]`; không có debug phases/heap |
| `gc-all.log` | `gc*=info` | **548** | Có thêm `[gc,start]`, `[gc,phases]` và tags kết hợp |
| `gc-detailed.log` | `gc*=info,gc+phases=debug,gc+heap=debug,safepoint=info` | **4.591** | Có cả phase/heap debug, safepoint |

**Kết quả grep/check tag trong `gc-detailed.log` của lần thử:**

~~~text
[debug][gc,phases...] : 3560 dòng
[debug][gc,heap...]   :  401 dòng
[safepoint...]        :   40 dòng
~~~

Các bộ đếm trên được tổng hợp bằng **lọc tag/level và đếm dòng**, không phải “có 3.560 GC cycles”. **Một GC ID có thể xuất hiện trên nhiều dòng** (start, phases, heap, summary); số lượng lines tăng nhanh khi bật debug.

### Ví dụ dòng có thật từ lần thử

`gc-basic.log`:

~~~text
[0.007s][info][gc] Using G1
[0.044s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 18M->3M(34M) 0.899ms
~~~

`gc-all.log`:

~~~text
[0.008s][info][gc     ] Using G1
[0.030s][info][gc,start    ] GC(0) Pause Young (Normal) (G1 Evacuation Pause)
[0.030s][info][gc,phases   ] GC(0)   Pre Evacuate Collection Set: 0.04ms
[0.030s][info][gc,phases   ] GC(0)   Evacuate Collection Set: 0.43ms
[0.030s][info][gc,phases   ] GC(0)   Post Evacuate Collection Set: 0.07ms
~~~

`gc-detailed.log` cũng bổ sung các dòng `[debug][gc,phases]` và `[debug][gc,heap]`, cũng như `[info][safepoint]`. Timestamps `time` phản ánh thời điểm chạy và tất nhiên khác mỗi lần.

### Giải thích một GC summary

~~~text
GC(0) Pause Young (Normal) (G1 Evacuation Pause) 18M->3M(34M) 0.899ms
~~~

- `GC(0)`: ID của event/cycle được HotSpot đặt cho việc đối chiếu các dòng cùng GC.
- `Pause Young`: một young-collection pause theo G1; đây là **stop-the-world pause** của collector được ghi nhận.
- `(Normal)`: tên phân loại pause theo G1; không phải mức “error/normal” của ứng dụng.
- `(G1 Evacuation Pause)`: G1 đang evacuate live objects của collection set trong pause.
- `18M->3M(34M)`: heap used **trước → sau GC**, kèm heap capacity/committed theo ngữ cảnh event, đơn vị hiển thị của HotSpot.
- `0.899ms`: thời lượng **GC pause của event này**, không phải thời gian toàn bộ request và không phải thời gian ứng dụng chờ network hoặc locks.

**Không dùng 18M−3M để khẳng định JVM trả 15 MB vật lý về hệ điều hành ngay**. Reclaimed heap space có thể nằm lại bên trong Java heap để được tái sử dụng, trong khi committed memory và process RSS là các thước đo khác.

### Các lines cùng GC(0) có thể chia sẻ một sự kiện

~~~text
GC(0) Pause Young ...
GC(0) Pre Evacuate Collection Set ...
GC(0) Evacuate Collection Set ...
GC(0) Post Evacuate Collection Set ...
GC(0) ... summary ...
~~~

Đây không phải 5 GC cycles độc lập. Việc đếm `GC(0)` xuất hiện 5 lần rồi nói “GC chạy 5 lần” là sai. Nếu xây log parser, cần nhóm theo **GC ID, event type và collector-specific phase semantics**, không đếm bừa các dòng chứa `GC(`.

## 12. Chương trình Java phụ kiểm thử log rotation

Để quan sát rotation ngay trên máy, tạo file **GcRotationDemo.java**:

~~~java
public class GcRotationDemo {
    private static final byte[][] roots = new byte[32][];

    public static void main(String[] args) {
        long sum = 0;
        for (int i = 0; i < 25_000; i++) {
            byte[] b = new byte[16 * 1024];
            b[0] = (byte) i;
            roots[i % roots.length] = b;
            sum += b[0];
        }
        System.out.println("completed=" + (sum != 0));
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 -encoding UTF-8 GcRotationDemo.java
java -XX:+UseG1GC -Xms32m -Xmx64m -Xlog:gc*=debug:file=gc-rotate.log:uptime,level,tags:filecount=2,filesize=10K GcRotationDemo
~~~

**Stdout thực nghiệm:**

~~~text
completed=true
~~~

Sau khi chương trình kết thúc, thư mục làm việc chứa active file và có thể chứa các rotated files tùy lượng log phát sinh. Trong lần thử đã xác minh, có đủ `gc-rotate.log`, `gc-rotate.log.0` và `gc-rotate.log.1`, đúng với `filecount=2`.

**Không nên thay `filesize=10K` này vào production.** Nó cố tình nhỏ để biểu diễn tính năng rotation và sẽ khiến lịch sử log bị thay thế nhanh khi workload có nhiều GC events.

## 13. Các cách lọc log để kiểm tra ngay

### PowerShell trên Windows

~~~powershell
Select-String -Path .\gc-basic.log -Pattern 'Using G1','Pause '
Select-String -Path .\gc-all.log -Pattern '\[gc,phases','\[gc,heap'
Select-String -Path .\gc-detailed.log -Pattern '\[debug\]\[gc,phases','\[debug\]\[gc,heap'
Select-String -Path .\gc-detailed.log -Pattern '\[safepoint'
~~~

Lệnh `Select-String` trên đọc file đã sinh, không làm thay đổi chúng. Ký tự `\` là escape của **regular expression** trong `-Pattern`, không phải escape Java String. Dùng `Select-String -SimpleMatch` khi muốn match chuỗi đơn giản không có regex metacharacters.

Đếm các dòng:

~~~powershell
(Get-Content .\gc-basic.log | Measure-Object -Line).Lines
(Get-Content .\gc-all.log | Measure-Object -Line).Lines
(Get-Content .\gc-detailed.log | Measure-Object -Line).Lines
~~~

**Thận trọng:** `Get-Content` toàn bộ file có thể tốn RAM khi log nhiều GB. Với log lớn, streaming, bộ lọc/collector trung tâm hoặc công cụ phân tích chuyên dụng sẽ phù hợp hơn. Không gọi `Get-Content` lên toàn bộ rotation history ở production mà không có giới hạn.

### Linux/macOS

~~~bash
grep -E 'Using G1|Pause ' gc-basic.log
grep -E '\[gc,(phases|heap)' gc-all.log
grep -E '\[debug\]\[gc,(phases|heap)' gc-detailed.log
grep 'safepoint' gc-detailed.log
wc -l gc-basic.log gc-all.log gc-detailed.log
~~~

**Không dùng grep thuần túy làm công cụ tính GC pause histogram chính xác** khi log chứa concurrent phases, multiple event types và collector-specific formats. Nó rất hữu ích để kiểm tra nhanh “đã phát đúng tag chưa”, sau đó mới dùng GC analyzer tương thích với JVM hiện hành để tính percentile/pause distributions.

## 14. Đọc log đúng ở G1, ZGC và Shenandoah

### G1: Young evacuation pause là một STW event

Ở G1, các dòng `Pause Young`/`Pause Full` thường phản ánh GC pauses, và `gc+phases=debug` cho biết những bước con của pause, chẳng hạn `Evacuate Collection Set`. Có thể dùng chúng để tìm pha nào chiếm phần lớn thời lượng GC pause.

**Đừng lấy từng phase duration rồi cộng tất cả khi chúng nằm trong quan hệ parent/child**, vì có thể double-count. Dùng tổng duration của event và cấu trúc phases tương ứng; kiểm tra xem phase con có overlap/bao hàm nhau hay không.

### ZGC/Shenandoah: concurrent phase không bằng pause

Bạn có thể gặp:

~~~text
GC(7) Concurrent Mark 12.5ms
GC(7) Pause Mark Start 0.03ms
GC(7) Concurrent Relocate 2.1ms
~~~

Ba dòng trên **chỉ là minh họa định dạng/ý nghĩa, không phải trích stdout thực nghiệm**. `Concurrent Mark 12.5ms` có thể diễn ra **trong khi ứng dụng vẫn chạy**, còn `Pause Mark Start 0.03ms` là một điểm stop-the-world ngắn. **Không** báo “GC làm đứng service 14.63ms” bằng cách cộng hai khoảng concurrent vào pause.

Với collector generational, một dòng log young/old, mark/relocation có thể khác cách G1 trình bày. Người phân tích cần biết collector đã được chọn và mode đúng runtime.

### Safepoint không đồng nghĩa GC

JVM safepoints là những điểm phối hợp giữa VM và Java threads, có thể phục vụ GC **hoặc công việc JVM khác**. `safepoint=info` cho biết thời gian/các sự kiện phối hợp, giúp đối chiếu những quãng application threads bị dừng, nhưng không nên gộp tất cả vào GC collection count.

**Muốn giải thích “application đứng 50ms”** cần so GC pauses với safepoint durations, application traces và scheduling/contention/CPU, không chỉ một dòng GC summary.

## 15. Xác định đúng nguyên nhân khi không thấy GC logs mong muốn

**Tình huống A — `-Xlog:gc` không in [gc,phases].** Đúng thiết kế: exact tag set `gc` không match `gc+phases`. Dùng `-Xlog:gc*` hoặc `gc+phases=debug`.

**Tình huống B — `-Xlog:gc*` có phases nhưng không đủ chi tiết.** Dấu `*` chỉ mở tag selection; muốn debug/trace cần level tương ứng.

**Tình huống C — `-Xlog:gc+heap=debug` hầu như không có data.** Có thể collector không phát tag set chính xác đó tại debug, hoặc chỉ có message ở tag set có thêm tag khác. Kiểm tra `java -Xlog:help` và log khi dùng `gc+heap*=debug` nếu cần các superset tag sets.

**Tình huống D — lệnh log chạy nhưng không có GC pause.** Workload rất nhỏ, live set nhỏ, heap rộng, hoặc GC không cần chạy trước khi process kết thúc. **Không tự suy ra logging hỏng** nếu không thấy GC events. Dùng workload kiểm thử có kiểm soát (mục 10) hoặc quan sát service thật.

**Tình huống E — output không nằm ở nơi tưởng.** Nếu có `file=gc.log`, đường dẫn tương đối là **relative với working directory của JVM process**, không nhất thiết thư mục chứa source/JAR. Trong container, xác định working directory và volume có quyền ghi.

**Tình huống F — đã chọn `-Xlog:gc` nhưng collector names khác tài liệu.** Lệnh không tự chọn GC; HotSpot/version/flags quyết định collector. Dùng `java -XX:+PrintFlagsFinal -version` hoặc JVM logging phù hợp để xác định collector thật, không suy ra từ một ví dụ G1.

**Tình huống G — file log bị ghi đè khi restart.** Kiểm tra basename, `filecount`/`filesize` và `%p`/`%t`. Nếu nhiều JVM chung file, không thể dùng rotation thay cho per-process isolation.

**Tình huống H — có GC log nhưng API p99 vẫn xấu.** Có thể vì allocation stalls, network latency, application locks, CPU saturation, disk, hoặc JVM safepoints khác. Phải phối hợp nhiều metrics.

**Tình huống I — `gc+ref=debug` không có dòng cho WeakReference.** Reference processing logs phụ thuộc GC phase và actual references được xử lý, không có nghĩa code không có WeakReference.

**Tình huống J — collector mới, parse tool báo lỗi.** GC log messages/tags là **diagnostics**, không phải cấu trúc dữ liệu API bắt buộc giữ nguyên từng field. Cập nhật parser phù hợp JDK/collector hoặc dùng tool hỗ trợ.

## 16. Đổi logging khi JVM đang chạy: jcmd VM.log

Trong HotSpot, `jcmd` có **diagnostic command `VM.log`** để liệt kê và thay đổi Unified Logging configuration khi một JVM **đang chạy**. Có ích khi production cần điều tra ngắn mà không restart.

Trên **cùng máy**, với quyền attach phù hợp:

~~~bash
jcmd <PID> VM.log list
~~~

Dòng trên chỉ là **lệnh mẫu**; thay `<PID>` bằng **số PID thật** của process do bạn quản lý. Không gõ dấu ngoặc nhọn vào shell.

Ví dụ cấu hình thêm/đổi output cho live JVM theo giao diện `VM.log`:

~~~bash
jcmd 12345 VM.log output=file=gc-live.log what=gc*=info decorators=uptime,level,tags output_options=filecount=3,filesize=5M
~~~

`12345` là **PID ví dụ**, không phải PID được thử trong bài. Tham số `output` đặt đích, `what` chọn tag/level, `decorators` chọn trường log và `output_options` chọn rotation. Sau khi chỉnh:

~~~bash
jcmd 12345 VM.log list
~~~

để xác nhận cấu hình đã được JVM nhận. Dùng `jcmd 12345 help VM.log` nếu runtime/version khác để lấy đúng accepted arguments.

**Giới hạn vận hành:** `jcmd` cần quyền attach, thường phải cùng host và cùng effective user/group phù hợp; có thể bị JVM/container/security policy từ chối. **Không tự attach vào JVM của người khác hoặc đọc private application data**. Logging có thể tăng output/overhead ngay lập tức; đặt thời điểm bật, thời điểm tắt và retention phù hợp.

**Đừng nhầm `jcmd VM.log` với `System.setProperty("logging.level.gc",...)` hoặc Logback dynamic reconfiguration.** `VM.log` cấu hình **JVM Unified Logging**; cấu hình Java application logger là subsystem khác.

## 17. Những flags/kiểu logging nào không nên mang từ Java 8 vào hệ thống mới?

Trên JVM hiện đại, ưu tiên:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar application.jar
~~~

Thay vì lấy các tutorials dùng:

~~~text
-XX:+PrintGC
-XX:+PrintGCDetails
-XX:+PrintGCTimeStamps
-XX:+PrintGCDateStamps
-Xloggc:gc.log
-XX:+UseGCLogFileRotation
-XX:NumberOfGCLogFiles=...
-XX:GCLogFileSize=...
~~~

Đây là **các ví dụ cờ lịch sử, không phải lệnh được khuyến nghị**. Chúng từng thuộc hệ thống logging cũ, hoặc đã deprecated/removed/được ánh xạ tạm thời ở một số JDK. Phần thay thế thống nhất là `-Xlog`. **Không cần chèn `-XX:+UnlockExperimentalVMOptions` để dùng `-Xlog:gc`**.

**Đặc biệt ở Java 15:** Không ép người học “vì bài thuộc Java 15 nên phải dùng GC flags như Java 8”. Kiến thức vẫn đúng trong Java hiện đại là `-Xlog`, tag sets, levels và output controls; kiến thức không còn phù hợp là quy trình quản lý GC logging bằng các legacy flags.

## 18. Log không thay thế JFR, JMX và service metrics

### GC logging trả lời điều gì?

- JVM đang dùng collector nào (khi log collector selection)?
- GC cycles xảy ra khi nào?
- Pause events kéo dài bao lâu?
- Heap usage/capacity thay đổi ra sao quanh một collection?
- Những phases/heuristics nào chiếm thời gian?
- Có Full GC, allocation stalls, safepoint events cần điều tra không?

### Điều log GC một mình không trả lời đủ

- Người dùng nào bị chậm hoặc request route nào?
- p99 của service là bao nhiêu trong từng khung thời gian?
- CPU bị bão hòa do GC threads hay application code?
- Network timeout, DB locking hay disk I/O có đóng góp gì?
- Allocation hot spot chính xác đến Java method/class nào?
- RSS của container có vượt limit vì native memory, direct buffers hoặc thread stacks không?

**Bổ sung nên dùng:**

- **JFR (Java Flight Recorder):** profile allocations, thread state, GC/safepoints, CPU (theo enabled events và JDK).
- **JMX/`ManagementFactory`:** GC bean collection counts/times, heap/non-heap memory usage; nếu collector có nhiều GC beans phải hiểu semantics từng bean.
- **Service metrics:** latency p50/p95/p99, throughput, CPU, allocation rate, errors.
- **Tracing:** tương quan request-level latency với GC event timestamps.

Ví dụ lấy số GC collections từ JMX trong code:

~~~java
for (GarbageCollectorMXBean bean :
        ManagementFactory.getGarbageCollectorMXBeans()) {
    System.out.println(
            bean.getName() + ": " + bean.getCollectionCount());
}
~~~

Đây là **mã đặt trong method** với imports `java.lang.management.*`; không đảm bảo output cố định vì GC bean names/counts phụ thuộc collector, JVM và hoạt động chương trình.

**Đừng cộng `getCollectionTime()` của tất cả các beans một cách mù quáng** khi collector phát các beans đại diện cho cả cycles lẫn pauses. Cần đọc semantics của runtime và kiểm chứng với GC log.

## 19. Kinh nghiệm vận hành: log đúng mức và không làm sai kết quả đo

### Production baseline

Một cấu hình xuất file tương đối hữu ích:

~~~bash
java -Xlog:gc*:file=gc-%p-%t.log:time,uptime,level,tags:filecount=5,filesize=10M -jar application.jar
~~~

Đây là **ví dụ ban đầu**, không phải policy bắt buộc. Hệ thống cần xem volume/disk quota, số instances, rotation và khả năng gửi log tập trung. Một số workloads có tần suất GC rất cao sẽ ghi log nhiều hơn dự kiến, cần tăng quota hoặc giảm verbosity.

### Khi có spike

- Xác nhận một sự kiện slow request bằng application metrics.
- Đối chiếu wall-clock timestamp với GC log và safepoint log.
- Xác định GC pause nào trùng với spike; phân biệt `Concurrent` với `Pause`.
- Bật `gc+phases=debug` hoặc `gc+heap=debug` **có giới hạn thời gian**.
- Xem memory headroom, allocation rate, CPU, và có Full GC/stall hay không.
- Nếu vẫn chưa đủ, dùng JFR/heap analysis hoặc profiling ứng dụng.
- Sau khi điều tra, trả logging về mức phù hợp, tránh giữ debug/trace vô hạn.

### Khi làm benchmark

Chạy một cấu hình GC logging giống nhau ở các lần so sánh để tránh **khác logging overhead làm biến dạng kết quả**. Nếu so G1 với ZGC/Shenandoah, đừng kết luận chỉ từ số lượng log lines: collectors dùng tags và phases khác nhau. So các metrics có ý nghĩa **như GC pause distributions, latency percentiles, throughput và memory** trong điều kiện hardware/JDK/workload nhất quán.

## 20. Những lỗi và hiểu nhầm thường gặp

1. **“`-Xlog:gc` in mọi dòng có chữ gc.”** Sai: exact tag set `gc`, không phải tìm substring trong message.
2. **“`-Xlog:gc*` nghĩa là bật TRACE.”** Sai: mở rộng tag matching, level mặc định vẫn info.
3. **“`gc+phases` là phép OR.”** Sai: `+` yêu cầu đồng thời cả tags; `,` tạo nhiều selectors.
4. **“`-Xlog:gc,safepoint` bao gồm mọi kết hợp chứa một trong hai.”** Sai khi không dùng wildcard; có thể bỏ sót tag sets có thêm tags.
5. **“Có debug selector thì mọi GC messages đều ở debug.”** Sai: selector và level áp theo tập tag phù hợp.
6. **“`-Xlog:gc*=info` chắc chắn in debug phase timer.”** Sai: cần `gc+phases=debug` hoặc mức tương ứng.
7. **“`gc+heap=debug` lúc nào cũng có đúng cùng fields.”** Sai: phụ thuộc collector, runtime và tag sets thực tế.
8. **“GC line count chính là GC count.”** Sai: một GC có nhiều lines/phases/heap stats.
9. **“`GC(0)` là memory address hoặc thread ID.”** Sai: là GC event/cycle ID để correlation.
10. **“`18M->3M(34M)` nghĩa OS được trả 15M.”** Sai: Java heap reclamation khác heap commitment/process RSS.
11. **“`Pause ... 0.9ms` là latency của toàn bộ HTTP request.”** Sai: đó là khoảng pause trong GC log, không cộng I/O/application delays.
12. **“`Concurrent Mark 20ms` là STW pause 20ms.”** Sai: concurrent phase chạy chồng với application.
13. **“Mọi safepoint đều là GC.”** Sai: JVM có nhiều nguyên nhân safepoint khác.
14. **“Đã bật -Xlog thì JVM chọn G1.”** Sai: logging độc lập với GC selection; ví dụ dùng G1 chỉ để có mẫu cụ thể.
15. **“Chạy chương trình ngắn không thấy GC nghĩa -Xlog hỏng.”** Sai: có thể chưa có collection nào.
16. **“`filecount=5` nghĩa tổng cộng chỉ có 5 file kể cả file active.”** Sai: theo help hiện đại, có thể có **active file + 5 rotated**.
17. **“`filesize=10M` đảm bảo từng file đúng 10.000.000 byte.”** Sai: rotation target gần đúng và suffix unit theo JVM help.
18. **“`file=gc.log` luôn tạo file cạnh JAR.”** Sai: relative path giải theo working directory của process.
19. **“Có thể dùng cùng filename cho mọi JVM instances.”** Có nguy cơ overwrite/collision; dùng `%p`/`%t` hoặc tách paths.
20. **“`-Xlog:gc*=trace` miễn phí.”** Sai: quá nhiều log ảnh hưởng CPU/I/O/disk và kết quả benchmark.
21. **“Cờ `-XX:+PrintGCDetails` là cấu hình tốt nhất cho Java 25.”** Sai: dùng Unified Logging `-Xlog`.
22. **“JMX GC bean names/counts luôn giống một ví dụ.”** Sai: collector-specific và version-specific.
23. **“GC log chứng minh không có memory leak.”** Sai: live set tăng lâu dài có thể do references vẫn reachable.
24. **“`-Xmx` là toàn bộ RAM/RSS mà JVM dùng.”** Sai: còn native memory, thread stacks, metaspace, direct memory.
25. **“`jcmd VM.log` có thể đổi GC algorithm đang chạy.”** Sai: nó điều chỉnh logging, không chuyển GC collector/memory model.
26. **“Không cần biết Java vendor/GC khi parse logs.”** Sai: format, tags, phases và mức chi tiết khác nhau.
27. **“Có thể xem file rotated cuối cùng là toàn bộ lịch sử.”** Sai: rotation tự ghi đè các phần cũ, phải có retention/copy phù hợp.
28. **“GC logs thay thế p99 service metrics.”** Sai: chỉ chứa một phần nguyên nhân của latency.
29. **“Dùng `-Xlog:disable` để tắt riêng GC.”** Sai: nó tắt cả logging framework config, bao gồm warning/error mặc định; phải chọn selectors cụ thể.
30. **“`java -Xlog:help` trên laptop mô tả chính xác tags của JVM production khác.”** Sai: hãy kiểm tra help trên **đúng version/build** của JVM đang triển khai.

## 21. Checklist QA cho cấu hình GC logging

| Mục tiêu kiểm tra | Điều cần đạt |
| --- | --- |
| Runtime đúng phiên bản? | Ghi `java -version` và VM vendor/build |
| Dùng cờ logging hiện hành? | `-Xlog` thay legacy PrintGC flags |
| Tag selector đã hiểu? | Phân biệt `gc`, `gc*`, `gc+phases` và `gc+phases*` |
| Level đúng nhu cầu? | Info baseline; debug/trace khi cần và có giới hạn |
| Output đích chính xác? | stdout/stderr/file, kiểm tra working directory |
| Decorators đủ để đối chiếu? | `time/uptime/level/tags`; PID khi nhiều processes |
| Rotation phù hợp retention? | `filecount`/`filesize` và hệ thống thu gom log |
| JVM có phát tag đó không? | `java -Xlog:help`; kiểm tra thực tế sau khi chạy |
| Đã xác định collector? | G1/ZGC/Shenandoah/Parallel theo runtime flags |
| Có biết lines nào là pause? | Nhìn đúng `Pause`, không lẫn `Concurrent` |
| Có parser version-aware không? | Nhận diện collector, GC ID, tag sets và phase semantics |
| Đã đo application latency chưa? | Có p95/p99 và tracing tương quan timestamps |
| Có quan sát heap và allocation stalls? | Đủ heap sizing/CPU/alloc metrics để giải thích |
| Có đo overhead logging? | Tránh debug/trace dày đặc trong benchmark không tương đương |
| Kết quả có tái lập? | Cùng JDK/build, workload, GC, flags, môi trường |

## 22. Bài luyện tập và tiêu chí đạt

**Bài 1 — Đúng timeline.** Giải thích Unified JVM Logging và Unified GC Logging được đưa vào JDK nào; Java 15 đóng vai trò gì. **Đạt** khi biết JEP 158/JEP 271 có từ JDK 9, Java 15 tiếp tục hỗ trợ `-Xlog:gc`.

**Bài 2 — Exact vs wildcard.** Chạy `-Xlog:gc` và `-Xlog:gc*` với cùng workload. **Đạt** khi `gc*` có thể ghi các tags `gc,phases`/`gc,heap` mà `gc` không có.

**Bài 3 — Tách selectors.** Phân biệt `gc+phases=debug` với `gc+phases*=debug`. **Đạt** khi nêu ý nghĩa exact tag set và superset match.

**Bài 4 — Level.** Tạo cấu hình chỉ ``gc*=info`` rồi thêm `gc+phases=debug`. **Đạt** khi thấy thêm phase debug lines mà không bật mọi GC debug tags.

**Bài 5 — Safepoint.** Thêm `safepoint=info` hoặc `safepoint*=info`. **Đạt** khi không gộp safepoint count vào GC count và biết một safepoint không nhất thiết do GC.

**Bài 6 — Chọn tag đúng vấn đề.** Từ bảng mục 6, đề xuất tags cho ba vấn đề: GC phases chậm, heap sau GC không giảm, G1 humongous allocations. **Đạt** khi chọn phù hợp mà không bật `all=trace`.

**Bài 7 — Chạy GcLoggingDemo.** Biên dịch `--release 17`, chạy G1 với 64 MiB max heap. **Đạt** khi thấy 60.000 allocations, 96 retained slots và collector có cơ hội chạy; không assert số GC cycles cố định.

**Bài 8 — Đọc một summary.** Giải thích `18M->3M(34M) 0.899ms`. **Đạt** khi phân biệt used before/after, capacity và pause duration, không nhầm với OS RSS hay end-to-end latency.

**Bài 9 — Không đếm GC theo số lines.** Một cycle có 7 phase lines và 1 summary line. **Đạt** khi nhóm theo GC ID và phân biệt event/phase trước khi đếm cycles.

**Bài 10 — Rotation.** Chạy `GcRotationDemo` với `filecount=2,filesize=10K`. **Đạt** khi thấy active + rotated files, hiểu filecount là số files quay vòng và sizes chỉ gần đúng.

**Bài 11 — Time correlation.** Bật `time,uptime,pid,level,tags`, so một khoảng request p99 spike với GC events. **Đạt** khi dùng timestamp của cùng JVM và biết concurrent time không bằng pause.

**Bài 12 — Đổi cấu hình live.** Trên JVM do chính bạn quản lý, dùng `jcmd <PID> VM.log list` rồi theo hướng dẫn `help VM.log` thử bật logging phù hợp. **Đạt** khi xác nhận cấu hình live đã thay đổi mà không restart, và nêu đúng các yêu cầu attach permissions.

**Bài 13 — Collector-specific.** Chạy cùng `GcLoggingDemo` dưới G1 và một collector concurrent được runtime hỗ trợ. **Đạt** khi nhận thấy phase names/tags khác và không đem mẫu G1 áp nguyên cho collector khác.

**Bài 14 — Benchmark overhead.** So một workload với `gc*=info` và `gc*=debug` có cùng runtime/heap/GC. **Đạt** khi đo thời gian, CPU, log size và p99 thay vì mặc định logging free.

**Bài 15 — JVM trong container.** Chạy app với `file=gc.log` và nhiều instances. **Đạt** khi xác định working directory, file permissions, memory/disk quota, PID/time tokens và retention.

**Bài 16 — Giới hạn log.** Một file rotated bị mất sự kiện cũ cần điều tra. **Đạt** khi biết rotation không thay retention lưu trữ trung tâm và điều chỉnh output/retention phù hợp.

**Bài 17 — Triệu chứng không có data.** `-Xlog:gc+ref=debug` không phát dòng. **Đạt** khi kiểm tra tag support, selector exact/wildcard, level, GC events thực tế thay vì tự kết luận “JDK hỏng”.

**Bài 18 — Phân biệt phân tích.** Một service có GC pause tối đa 1ms nhưng p99 100ms. **Đạt** khi điều tra allocation stalls, CPU, locks, I/O, safepoints và tracing, không đổ mọi latency cho GC.

## 23. Tài liệu chính thức và còn giá trị

- [JEP 158 — Unified JVM Logging](https://openjdk.org/jeps/158): kiến trúc logging thống nhất của JVM.
- [JEP 271 — Unified GC Logging](https://openjdk.org/jeps/271): chuyển GC log sang framework thống nhất.
- [Oracle Java SE 15 — The java Command](https://docs.oracle.com/en/java/javase/15/docs/specs/man/java.html): `-Xlog:gc`, `gc*`, tags/levels, output và file rotation ở đúng phiên bản Java 15.
- [Oracle Java SE 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): cú pháp `-Xlog` hiện hành, exact vs wildcard tag-selection, decorators, rotation, samples và mapping legacy flags.
- [Oracle Java SE 25 — The jcmd Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): `VM.log` list/what/output/decorators/output_options và yêu cầu attach.
- [Oracle Java SE 25 — HotSpot VM Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/25/gctuning/index.html): chọn GC và quan sát/troubleshoot heap/collector behavior.
- [Oracle Java SE 25 — Garbage-First G1 GC](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html): ý nghĩa G1 phases, `gc+phases=debug`, heap/evacuation.
- [Oracle Java SE 25 — Troubleshoot Memory Leaks](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshooting-memory-leaks.html): ví dụ `-Xlog:gc*,gc+phases=debug` và cách GC logs hỗ trợ phát hiện live-set patterns.
- [Oracle Java SE 25 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): GC collection counts/times trong runtime.
- [Oracle Java SE 25 — Java Flight Recorder Runtime Guide](https://docs.oracle.com/en/java/javase/25/jfapi/java-flight-recorder-api-programmers-guide.html): JFR như công cụ bổ trợ cho GC logs trong phân tích.

**Ghi nhớ:** `-Xlog:gc` là **exact tag set `gc` ở level info**. Để xem các tags kết hợp, dùng `-Xlog:gc*`; để thấy timing/heap chi tiết, thêm `gc+phases=debug`, `gc+heap=debug` có chủ đích. Muốn liên hệ với latency, bật timestamps, safepoint logs, rotation hợp lý và đối chiếu application metrics. **Đừng nhầm số dòng log với số chu kỳ GC, concurrent time với STW pause, hay heap reclaimed với OS RSS**; luôn kiểm tra `java -Xlog:help` trên đúng JVM và dùng kiến thức còn hỗ trợ thay các flags GC logging đời cũ.
