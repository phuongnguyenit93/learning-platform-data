# Phân biệt thời gian dừng GC với độ trễ toàn yêu cầu (Java 11+)

## 1. Mục tiêu học tập

Trong ứng dụng Java, **GC pause** và **request latency** đều có thể được đo bằng mili giây, nhưng chúng **không cùng phạm vi, không cùng mẫu số và không thể thay thế nhau**.

Ví dụ, một dịch vụ có thể ghi nhận GC pause lớn nhất chỉ 12 ms trong một khoảng quan sát, trong khi p99 HTTP request latency là 400 ms. Điều này không mâu thuẫn: một request còn phải chờ queue, thread scheduling, database, network, downstream service, lock, retry, response transfer và nhiều bước khác.

Bài học này thuộc nhóm **GC độ trễ thấp**, tập trung vào câu hỏi: *Khi nào thời gian GC thực sự góp phần vào độ trễ mà người dùng trải nghiệm, và làm sao chứng minh điều đó?*

Sau bài, bạn cần:
- Phân biệt stop-the-world (STW) pause, concurrent GC, GC cycle, safepoint và độ trễ end-to-end.
- Biết GC pause histogram khác request latency histogram; p99 của hai tập không so bằng phép trừ hoặc cộng tùy tiện.
- Dùng Java Flight Recorder (JFR) `jdk.GCPhasePause`, GC logs và request spans có time windows rõ ràng.
- Tính **hợp các khoảng giao nhau** giữa pause và request, tránh đếm trùng các phase lồng nhau.
- Hiểu **giao nhau về thời gian không tự chứng minh tác động nhân quả**.
- Biết `-XX:MaxGCPauseMillis` của G1 là mục tiêu mềm, **không phải SLO request hoặc hard guarantee**.
- Tạo và đọc một recording JFR thực bằng Java 11, kiểm thử được với `javac --release 11`.

Các API và công cụ được giới thiệu vẫn còn áp dụng trong Java hiện đại. Không sử dụng cấu hình collector hoặc cơ chế kích hoạt thương mại đã lỗi thời.

## 2. Ba thước đo dễ nhầm nhất

### 2.1. GC stop-the-world pause

Một **STW GC pause** là khoảng JVM tạm dừng các application threads bị ảnh hưởng để thực hiện một giai đoạn GC cần safepoint. JVM có thể ghi thời điểm bắt đầu/kết thúc hoặc duration trong event/log.

Với G1, nhiều công việc thu gom diễn ra trong các pause thường tương đối ngắn; ngoài ra còn có giai đoạn làm việc đồng thời với ứng dụng. **G1 không phải bộ thu gom thời gian thực**: pause goal là mục tiêu, không phải cam kết tuyệt đối.

### 2.2. End-to-end request latency

Tùy điểm đo, request latency có thể là:
- **Client-side:** từ khi client khởi tạo request đến khi nhận response đủ theo hợp đồng; có network, proxy, server, transfer.
- **Gateway-side:** từ khi gateway nhận request đến khi gateway hoàn thành response; bao gồm một số hàng đợi/proxy.
- **Server-side:** từ khi handler hoặc middleware ghi timestamp đến khi hoàn thành theo instrumentation; có thể **không** tính queue trước handler, DNS, TLS hoặc thời gian client nhận toàn bộ response.

Khi báo cáo p99, phải nói rõ **đo ở đâu**. Một handler span 20 ms không phủ nhận client request 300 ms, vì còn nhiều thời gian ngoài span.

### 2.3. Elapsed time khác CPU time

**Elapsed/wall-clock time** bao gồm cả thời gian thread bị block, sleep hoặc chờ scheduler. **Thread CPU time** chỉ phản ánh thời gian CPU của thread theo nguồn đo phù hợp.

Nếu một custom JFR `Event` có `begin()`, `Thread.sleep(40)` rồi `end()`, duration event có thể xấp xỉ 40 ms nhưng phần CPU thực của thread có thể rất nhỏ. GC pause cũng không thể được suy chỉ từ CPU samples.

| Đại lượng | Mẫu số | Nó đo gì? |
| --- | --- | --- |
| GC pause duration | Một giai đoạn pause | Thời gian của pause đã instrument |
| GC cycle duration | Một chu kỳ GC | Có thể gồm giai đoạn concurrent và STW |
| Request latency | Một request theo scope cụ thể | Thời gian request trải qua ở điểm đo |
| CPU time | Thread/process | Thời gian dùng CPU |
| Safepoint sync time | Một hoạt động VM/safepoint | Thời gian đi tới safepoint, có semantics riêng |
| p99 GC pause | Tập GC pauses quan sát | Phân vị của pause durations |
| p99 request latency | Tập requests quan sát | Phân vị của request durations |

**Chốt:** GC pause được đo ở **JVM**, request end-to-end được đo ở **luồng nghiệp vụ/HTTP**. Chúng có thể liên quan nhưng không đồng nhất.

## 3. GC cycle không đồng nghĩa thời gian mọi thread bị dừng

G1 có thể thực hiện một số hoạt động **concurrent** trong khi application threads vẫn chạy. Một GC cycle kéo dài 250 ms **không có nghĩa JVM bị STW suốt 250 ms**.

Khi nhìn JFR hoặc log:
- Chọn event pause thích hợp, chẳng hạn **`jdk.GCPhasePause`**.
- Không thay thế bằng duration của `jdk.GarbageCollection` nếu event đó biểu diễn tổng chu kỳ GC có concurrent work.
- Phân biệt những phase cấp con có thể nằm trong pause cha; cộng tất cả durations thường gây đếm trùng.
- Nếu đang xem `safepoint` logs, hiểu thời gian để thread đạt safepoint khác với khoảng pause ở safepoint.
- Ghi rõ collector/JDK build, bởi event definitions có thể thay đổi theo JDK và runtime.

**Cũng không nên kết luận GC concurrent “miễn phí”**. Các thread GC chạy đồng thời có thể cạnh tranh CPU, memory bandwidth với application, làm request chậm mà không có STW pause dài. Low-pause không tự động đồng nghĩa low-latency.

## 4. Request latency có nhiều thành phần và phụ thuộc tải

Một request giả định kéo dài 220 ms có thể có những giai đoạn:

```text
0 ms                                                   220 ms
|-----------------------------------------------------------|
 [network] [queue] [handle requests / DB wait] [response]
                     |-------- GC pause ------|
```

Đây là **sơ đồ mô tả**, không đủ dữ liệu để cộng thời gian từng bước. Các hoạt động có thể chồng nhau hoặc chạy async trên nhiều thread/hops.

Một request đang chờ database trong lúc GC pause 10 ms **không nhất thiết bị cộng thêm đủ 10 ms**. Nếu database vẫn chưa phản hồi khi JVM resume, GC pause có thể không nằm trên critical path của request.

Ngược lại, một pause 20 ms có thể khiến **nhiều request đồng thời** bị gián đoạn, làm queue dài thêm; khi load gần ngưỡng năng lực xử lý, ảnh hưởng tới p99 có thể lớn hơn độ dài pause đơn lẻ.

### 4.1. Vì sao queue quan trọng?

Khi arrival rate gần processing capacity:
- Một gián đoạn nhỏ có thể đẩy nhiều request vào hàng đợi.
- Sau pause, thread pool chưa chắc xử lý kịp backlog.
- Timeout/retry có thể khuếch đại traffic.
- GC concurrent work có thể làm giảm capacity trong lúc cần phục hồi.

Vì thế cần đo **RPS, concurrency, queue depth, thread pool saturation, CPU throttling** bên cạnh GC pause.

### 4.2. Vì sao cần cả client và server timings?

Server handler chỉ tính từ khi bắt đầu xử lý. Nếu request nằm chờ ở load balancer hoặc executor 100 ms trước khi handler chạy, handler duration thấp vẫn có thể đi cùng client p99 cao.

Nên instrument:
- Client request total.
- Gateway queue/upstream processing nếu có.
- Server request arrival → handler start.
- Handler start → response commit/complete.
- Outbound calls, DB pool acquisition, lock wait, retries.

Những spans này hỗ trợ xác định **đoạn latency nào bị GC pause chặn**, thay vì chỉ xem một số p99 toàn cục.

## 5. Giao nhau theo thời gian: phép tính đúng nhưng chưa đủ cho nhân quả

### 5.1. Định nghĩa interval

Dùng các khoảng nửa mở:
- Request window: `[R_start, R_end)`.
- GC pause window: `[P_start, P_end)`.

Khoảng giao nhau:

```text
overlap(R, P) =
    max(0, min(R_end, P_end) - max(R_start, P_start))
```

Muốn tính tổng thời gian request **giao với các pause windows**, phải hợp các khoảng pause giao nhau trước khi cộng.

### 5.2. Ví dụ cụ thể

```text
Request:          [100, 220)          120 ms
GC pause A:       [160, 175)           15 ms
GC pause A-child: [168, 172)            4 ms (nằm trong A)
GC pause B:       [205, 215)           10 ms
```

A-child đã nằm trong A, nên **không** cộng 15 + 4 + 10. Hợp các khoảng pause là:

```text
[160,175) UNION [168,172) = [160,175)
[160,175) UNION [205,215) = 2 đoạn rời nhau

Union overlap = 15 + 10 = 25 ms
Request interval = 220 - 100 = 120 ms
Outside specified pause windows = 120 - 25 = 95 ms
```

**Kết luận hợp lệ:** 25 ms thuộc phần giao của request window và các pause windows **giả định** đã gộp.

**Kết luận không hợp lệ:** “GC chắc chắn gây đúng 25 ms trong 120 ms”, hoặc “95 ms còn lại là thời gian CPU không liên quan GC”.

Lý do:
- Request có thể đang chờ network, DB hoặc future trong phần giao.
- Request có thể do một JVM khác xử lý.
- GC có thể tạo ảnh hưởng gián tiếp qua queue hoặc concurrent CPU ngoài thời gian STW.
- Chưa biết thread nào bị pause, ở phase nào của request.
- Các timestamps có thể đến từ host có lệch đồng hồ.

**Union overlap là một tín hiệu điều tra, không phải causal attribution.**

### 5.3. Thuật toán merge interval

1. Lấy các pause intervals có timestamp trên **cùng timeline đáng tin**.
2. Cắt vào request window.
3. Loại khoảng rỗng.
4. Sắp xếp theo start.
5. Gộp các khoảng chồng nhau.
6. Tính tổng độ dài các khoảng đã gộp.

Không cộng riêng `jdk.GCPhasePause` với mọi `GCPhasePauseLevel*` nếu chúng biểu diễn các pha lồng nhau; có thể đếm một khoảng thời gian nhiều lần. Không trộn pauses từ các JVM khác nhau trong một phép tính local overlap.

## 6. Percentile GC và percentile request không thể hoán đổi

Giả sử trong một phút có:
- 10 GC pauses, thời gian 2–15 ms.
- 15.000 requests, thời gian 5–600 ms.

p99 của 10 pause events và p99 của 15.000 request events thuộc **hai phân phối khác nhau**. Dù đều có đơn vị ms, chúng **không cùng mẫu số**.

Những kết luận sai thường gặp:
- “p99 pause 10 ms thì p99 request phải 10 ms.”
- “p99 request 500 ms, max pause 10 ms nên GC không liên quan.”
- “p99 GC + p99 database + p99 network = p99 request.”

Ngay cả với tổng thời gian của các thành phần A và B:

```text
Latency = A + B
```

nói chung **p99(Latency) không bằng p99(A) + p99(B)**. Percentiles không cộng tuyến tính, đặc biệt khi distributions có tương quan và các thành phần chồng nhau.

Để quy kết:
- Dùng **per-request spans**, không chỉ các percentile tổng hợp.
- Chọn đúng incident time windows.
- Đối chiếu request timelines với GC pause events trên đúng JVM/hop.
- Xem các request **không overlap** GC có chậm tương tự không.
- Xem traffic, CPU, queue và downstream metrics.

## 7. G1 và MaxGCPauseMillis: mục tiêu mềm chứ không phải SLA

Trong Java 11, G1 là lựa chọn GC mặc định trên các cấu hình server-class phổ biến. G1 cố đạt mục tiêu thời gian pause bằng việc điều chỉnh lượng công việc trong mỗi đợt.

Ví dụ về **cú pháp CLI hợp lệ**, không phải cấu hình áp dụng cho mọi ứng dụng:

```bash
java -XX:+UseG1GC -XX:MaxGCPauseMillis=50 -jar app.jar
```

`-XX:MaxGCPauseMillis=50` nghĩa G1 cố hướng đến **pause-time goal 50 ms**. Đây là một mục tiêu **mềm**, không có nghĩa:
- Tất cả GC pause chắc chắn dưới 50 ms.
- HTTP request p99 chắc chắn dưới 50 ms.
- Giảm mục tiêu từ 50 xuống 10 luôn giúp p99 tốt hơn.
- Hệ thống không bị chậm bởi concurrent GC hoặc queueing.

Mục tiêu quá chặt có thể làm GC hoạt động thường xuyên hơn, tốn CPU hơn hoặc giảm throughput. Cần đo throughput, p95/p99, allocation, GC frequency và memory footprint.

### 7.1. Không tuning G1 bằng cách cố định young generation tùy ý

G1 dùng cơ chế điều chỉnh young generation để cố đạt pause goal. Việc cố định kích thước young generation bằng `-Xmn` có thể làm mất khả năng thích nghi của G1, nên **không dùng như một tối ưu chung** cho low-latency.

Bắt đầu bằng G1 defaults phù hợp, heap đủ headroom và dữ liệu thật. Thay đổi từng tham số có đối chứng, không sao chép nhiều cờ JVM từ tài liệu cũ hoặc môi trường khác.

### 7.2. Collector khác có thể phù hợp tùy JDK, không có đáp án tuyệt đối

Các collector hướng latency khác có thể được cân nhắc khi **JDK/vendor/version cụ thể** hỗ trợ và đáp ứng production requirements. Tính sẵn có và độ trưởng thành của một collector ở Java 11 có thể khác đáng kể so với JDK hiện đại.

Không lấy kết quả benchmark trên một JDK khác rồi áp cấu hình nguyên xi. Luôn dùng request-level SLO và tổng tài nguyên để chọn collector, không chỉ histogram pause.

## 8. Dùng JFR để đo GC pause trên JVM thật

### 8.1. Event jdk.GCPhasePause

JFR có loại event **`jdk.GCPhasePause`** dùng để ghi các khoảng dừng GC tương ứng. Trên Java 11, có thể bật theo tên:

```java
recording.enable("jdk.GCPhasePause")
         .withThreshold(Duration.ZERO);
```

Đây là **mảnh mã minh họa** bên trong phương thức có `Recording recording` và import `Duration`. Xem file thực tế và metadata để biết event có được ghi và có trường gì.

Khi đọc:

```java
if ("jdk.GCPhasePause".equals(event.getEventType().getName())) {
    Instant begin = event.getStartTime();
    Instant end = event.getEndTime();
    Duration duration = event.getDuration();
    // Xác định đúng GC pause và time window trước khi phân tích.
}
```

Mảnh mã giả định đã có `RecordedEvent event`, imports `Instant`/`Duration`. Không dùng một event `jdk.GarbageCollection` về chu kỳ tổng thể như thể nó luôn là một STW pause. Kiểm tra schema thực trước khi đọc GC ID/name.

**Một recording 2 giây có 0 `GCPhasePause` events không chứng minh GC không bao giờ xảy ra.** Có thể đơn giản không có hoạt động GC phù hợp trong cửa sổ đó, event disabled, retention cắt dữ liệu hoặc dump sai thời điểm.

### 8.2. Đo request spans cùng timeline

Nên instrument request ở scope rõ, ví dụ handler:

```java
RequestSpan event = new RequestSpan();
event.begin();
try {
    doWork();
} finally {
    event.end();
    if (event.shouldCommit()) {
        event.operationGroup = "catalog";
        event.status = 200;
        event.commit();
    }
}
```

Đây là **mảnh mã minh họa**, không độc lập: cần định nghĩa `RequestSpan`/`doWork()`. Trong sản phẩm thực phải xử lý status/error đúng theo kết quả công việc, không hardcode HTTP 200. Bài này chỉ minh họa vị trí begin/end.

Để đo **end-to-end client latency**, ghi thêm ở phía client/gateway. Không kỳ vọng server handler span bao phủ queue trước handler hoặc network truyền response tới client.

### 8.3. Các vấn đề về timestamp

- `System.nanoTime()` thích hợp đo **hiệu thời gian monotonic trong cùng JVM**; không phải epoch timestamp xuyên host.
- `RecordedEvent.getStartTime()/getEndTime()` trả `Instant` để đối chiếu các event cùng recording.
- Clock skew, time resolution và async boundaries làm việc ghép sự kiện từ nhiều host kém chính xác.
- Cần trace/span context, request ID có phạm vi rõ và các local durations ở mỗi hop.

Không công bố con số pause overlap chính xác tới microsecond nếu dữ liệu chỉ có các timestamps không đồng bộ giữa nhiều máy.

## 9. GC logs và safepoint logs giúp đối chiếu

Trong Java 11, **unified logging `-Xlog`** cho phép lấy GC và safepoint diagnostics:

```bash
java -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags -jar app.jar
```

Cú pháp đã được kiểm tra với JVM hiện có. File `gc.log` chỉ là ví dụ đường dẫn, cần quyền truy cập và retention riêng. Không bật logging quá chi tiết trong production thiếu budget.

Cần phân biệt:
- Thời gian GC STW phase.
- Thời gian GC cycle (có thể concurrent).
- Thời gian synchronization tới safepoint.
- Thời gian JVM ở safepoint.
- Các log lines mô tả phase con/phần việc đồng thời.

**Không cộng mọi duration GC + safepoint + phase** để suy ra “total request delay”, vì những intervals có thể chồng/lồng nhau hoặc đo các khái niệm khác.

### 9.1. jcmd và jfr tool

Ví dụ với JVM mà bạn có quyền quản trị:

```bash
jcmd -l
jcmd <PID> help JFR.start
jcmd <PID> JFR.start name=gc-window settings=profile disk=true maxage=10m maxsize=128m dumponexit=false
jcmd <PID> JFR.check
jcmd <PID> JFR.dump name=gc-window filename=/secure/jfr/gc-window.jfr
jcmd <PID> JFR.stop name=gc-window
jfr summary /secure/jfr/gc-window.jfr
jfr print --events jdk.GCPhasePause /secure/jfr/gc-window.jfr
```

`<PID>` và `/secure/jfr` là placeholders. Chọn đúng tiến trình, xác minh options bằng `jcmd <PID> help JFR.start`, và dùng đường dẫn an toàn. Cấu hình `profile` có thể tăng chi phí; chỉ chạy trong giai đoạn thực sự cần.

File `.jfr` có thể chứa stack traces, class names, host/path và custom payload nhạy cảm. Có ACL, TTL, encryption và quy trình chia sẻ được phép; không đưa raw JFR lên ticket công khai.

## 10. Chương trình Java 11 hoàn chỉnh, đã biên dịch và chạy

Chương trình tự chứa `GcPauseVsRequestDemo` kết hợp **JFR thực** và **mô phỏng toán học interval**:

1. Tạo recording từ `Configuration.getConfiguration("default")`.
2. Bật custom duration event `lesson.RequestSpan` và `jdk.GCPhasePause`.
3. Dùng `setToDisk(true)`, repository limit 5 phút/32 MiB, tắt dump-on-exit.
4. Tạo hai request spans bằng `Thread.sleep(40)` và `Thread.sleep(20)`. Duration dương đến từ elapsed time, **không chứng minh hai span dùng CPU liên tục**.
5. Dump `.jfr`, đọc bằng `RecordingFile`, kiểm tra hai request spans và dữ liệu an toàn của custom schema.
6. Đọc mọi `jdk.GCPhasePause` nếu có, kiểm tra start/end; **không bắt buộc xảy ra GC trong bài test ngắn**.
7. Tính union overlap từ ba **pause windows giả định**, với một khoảng lồng nhau, kết quả 25 ms.
8. Xóa file demo và in stdout đã kiểm chứng.

Lưu ý: Những số `100`, `160`, `220`... là dữ liệu toán học **giả định**, không phải measurement của JVM đang chạy. Chương trình không gọi `System.gc()` để cưỡng bức thu gom.

### 10.1. Mã nguồn GcPauseVsRequestDemo.java

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;
import jdk.jfr.Category;
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.StackTrace;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class GcPauseVsRequestDemo {
    @Name("lesson.RequestSpan")
    @Category({"Application", "Latency"})
    @StackTrace(false)
    public static class RequestSpan extends Event {
        public String operationGroup;
        public String phase;
        public int status;
    }

    private static void request(String phase, int sleepMillis)
            throws InterruptedException {
        RequestSpan e = new RequestSpan();
        e.begin();
        Thread.sleep(sleepMillis);
        e.end();
        if (e.shouldCommit()) {
            e.operationGroup = "synthetic-catalog";
            e.phase = phase;
            e.status = 200;
            e.commit();
        }
    }

    // Hợp các đoạn giao với request; không phải ước lượng nguyên nhân.
    private static long unionOverlap(long requestStart, long requestEnd,
            long[][] pauses) {
        long[][] intervals = new long[pauses.length][2];
        for (int i = 0; i < pauses.length; i++) {
            intervals[i] = pauses[i].clone();
        }
        Arrays.sort(intervals, (a, b) -> Long.compare(a[0], b[0]));
        long result = 0;
        long mergedStart = -1;
        long mergedEnd = -1;
        for (long[] pause : intervals) {
            long start = Math.max(requestStart, pause[0]);
            long end = Math.min(requestEnd, pause[1]);
            if (end <= start) {
                continue;
            }
            if (mergedStart < 0) {
                mergedStart = start;
                mergedEnd = end;
            } else if (start > mergedEnd) {
                result += mergedEnd - mergedStart;
                mergedStart = start;
                mergedEnd = end;
            } else {
                mergedEnd = Math.max(mergedEnd, end);
            }
        }
        if (mergedStart >= 0) {
            result += mergedEnd - mergedStart;
        }
        return result;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Give a new temporary .jfr path");
        }
        Path dump = Path.of(args[0]);
        boolean gcPhasePauseEnabled;
        try (Recording recording =
                new Recording(Configuration.getConfiguration("default"))) {
            recording.setToDisk(true);
            recording.setMaxSize(32L * 1024 * 1024);
            recording.setMaxAge(Duration.ofMinutes(5));
            recording.setDumpOnExit(false);
            recording.enable(RequestSpan.class)
                    .withThreshold(Duration.ZERO).withoutStackTrace();
            recording.enable("jdk.GCPhasePause")
                    .withThreshold(Duration.ZERO);
            gcPhasePauseEnabled = "true".equals(
                    recording.getSettings().get("jdk.GCPhasePause#enabled"));
            recording.start();
            request("db-wait", 40);
            request("serialize", 20);
            recording.stop();
            recording.dump(dump);
        }

        int requests = 0;
        int pauses = 0;
        boolean requestDurationsPositive = true;
        boolean safePayload = true;
        boolean requestStacksAbsent = true;
        try (RecordingFile file = new RecordingFile(dump)) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();
                String name = event.getEventType().getName();
                if ("lesson.RequestSpan".equals(name)) {
                    requests++;
                    requestDurationsPositive &=
                            event.getDuration().toNanos() > 0;
                    safePayload &= "synthetic-catalog".equals(
                            event.getString("operationGroup"));
                    safePayload &= event.getInt("status") == 200;
                    Set<String> fields = new HashSet<>();
                    event.getEventType().getFields()
                            .forEach(f -> fields.add(f.getName()));
                    safePayload &= !fields.contains("authorization");
                    safePayload &= !fields.contains("requestBody");
                    requestStacksAbsent &= event.getStackTrace() == null;
                } else if ("jdk.GCPhasePause".equals(name)) {
                    pauses++;
                    if (event.getEndTime().isBefore(event.getStartTime())) {
                        throw new AssertionError("Invalid GC pause window");
                    }
                }
            }
        }

        long requestMs = 220 - 100;
        long overlapMs = unionOverlap(100, 220, new long[][]{
            {160, 175}, {168, 172}, {205, 215}
        });
        System.out.println("requestSpans=" + requests);
        System.out.println("requestDurationsPositive=" + requestDurationsPositive);
        System.out.println("requestPayloadSafe=" + safePayload);
        System.out.println("requestStacksAbsent=" + requestStacksAbsent);
        System.out.println("gcPhasePauseEnabled=" + gcPhasePauseEnabled);
        System.out.println("hypotheticalRequestMs=" + requestMs);
        System.out.println("hypotheticalPauseWindowOverlapMs=" + overlapMs);
        System.out.println("hypotheticalOutsidePauseWindowsMs=" +
                (requestMs - overlapMs));
        System.out.println("overlapIsCausalityProof=false");
        System.out.println("recordingFileCreated=" + (Files.size(dump) > 0));
        Files.delete(dump);
        System.out.println("demoFileDeleted=" + !Files.exists(dump));
        if (requests != 2 || !requestDurationsPositive
                || !safePayload || !requestStacksAbsent
                || !gcPhasePauseEnabled || requestMs != 120 || overlapMs != 25) {
            throw new AssertionError("Demo validation failed");
        }
        // Số pause trong một bản ghi ngắn là không xác định trước.
        if (pauses < 0) {
            throw new AssertionError("Invalid count");
        }
    }
}
```

### 10.2. Biên dịch và chạy

Chạy trong thư mục thử nghiệm và dùng một file `sample.jfr` **mới**, không trùng file quan trọng, vì code xóa file ở đường dẫn này sau khi đọc:

```bash
javac -encoding UTF-8 --release 11 GcPauseVsRequestDemo.java
java GcPauseVsRequestDemo sample.jfr
```

**Stdout đã kiểm chứng khi biên dịch `--release 11` và chạy trên JDK 24:**

```text
requestSpans=2
requestDurationsPositive=true
requestPayloadSafe=true
requestStacksAbsent=true
gcPhasePauseEnabled=true
hypotheticalRequestMs=120
hypotheticalPauseWindowOverlapMs=25
hypotheticalOutsidePauseWindowsMs=95
overlapIsCausalityProof=false
recordingFileCreated=true
demoFileDeleted=true
```

### 10.3. Diễn giải từng kết quả

- `requestSpans=2`: đúng hai custom duration events được phát và đọc lại.
- `requestDurationsPositive=true`: các request spans có elapsed duration dương; code dùng sleep nên duration **không bằng CPU time**.
- `requestPayloadSafe=true`: custom events dùng một group giả lập, status 200, và schema không có hai field nhạy cảm được kiểm tra. **Không chứng minh mọi built-in event trong file không có dữ liệu nhạy cảm**.
- `requestStacksAbsent=true`: stack traces cho custom events đã bị tắt theo thiết kế.
- `gcPhasePauseEnabled=true`: đã bật `jdk.GCPhasePause` trong recording; **không khẳng định có GC pause được ghi**. Nếu không có GC trong phiên rất ngắn, `pauses` có thể bằng 0.
- `hypotheticalRequestMs=120`: request window toán học, không phải duration measured của hai custom events.
- `hypotheticalPauseWindowOverlapMs=25`: hợp [160,175) và [205,215), bỏ phần lồng [168,172).
- `hypotheticalOutsidePauseWindowsMs=95`: thời gian nằm ngoài các pause windows giả định, **không phải 95 ms “non-GC CPU”**.
- `overlapIsCausalityProof=false`: phép đo giao nhau không tự xác định root cause.
- `recordingFileCreated=true`: file .jfr có dữ liệu.
- `demoFileDeleted=true`: file thử nghiệm được xóa bằng `Files.delete`; không phải cam kết secure erase trên ổ đĩa/backups.

Chương trình thử nghiệm không đo end-to-end HTTP thật, không thực hiện load test và không tính pause overlap từ các GC events đo được. Nó **minh họa hai bước tách biệt**: đọc event JFR thật và kiểm chứng thuật toán union intervals bằng dữ liệu tổng hợp.

## 11. Dùng thuật toán overlap trên dữ liệu production

Để áp dụng cách tính vào request thật:
1. Thu `jdk.GCPhasePause` start/end trên JVM đúng instance.
2. Thu server request spans hoặc phase spans với timestamp trên cùng trục thời gian đáng tin.
3. Nếu client request xuyên nhiều service, phải **tách theo từng hop/JVM**, không dùng pause ở host A để quy kết latency xảy ra ở host B.
4. Loại các GC event levels lồng nhau hoặc dùng thuật toán union để không đếm trùng.
5. Tính union overlap cho mỗi request.
6. So sánh request/trace state trong phần overlap: đang chạy Java, blocked trên lock, đợi network, hay chưa có thread xử lý?
7. Đối chiếu p99, queue, CPU quota, downstream, retries và GC concurrent work.
8. Ghi rõ mức độ chắc chắn của nguyên nhân, không chỉ xuất một bảng “GC cost per request” thiếu điều kiện.

Đối với nhiều host, time synchronization là rủi ro đáng kể. `Instant` từ hai máy có thể lệch, nhất là khi NTP adjustment, virtualization và log collection có delay. Trace propagation và local durations đáng tin hơn việc tự ghép timestamps raw không có offset.

### 11.1. Overlap bằng 0 có chứng minh GC không liên quan?

Không. GC concurrent work có thể cạnh tranh tài nguyên, hoặc STW pause trước request đã làm backlog tăng và request bị queue sau đó. Mô hình overlap chỉ trả lời câu hỏi “bao nhiêu thời gian giao với những pause windows này?”, **không** trả lời mọi tác động dây chuyền.

### 11.2. Overlap dương có chứng minh GC gây delay?

Không. Nếu request đang đợi DB, pause và DB latency có thể trùng nhau nhưng không nhất thiết kéo dài completion. Muốn quy kết mạnh hơn cần thread state, data path, queue state và can thiệp có đối chứng.

## 12. Bốn kịch bản điều tra

### 12.1. GC pause nhỏ, request p99 lớn

Thử kiểm tra:
- Network/gateway latency.
- Queue trước handler, thread pool saturation.
- DB/downstream latency, connection pool acquisition.
- Lock contention và blocking.
- CPU throttling hoặc retries.
- GC concurrent overhead, dù STW pause nhỏ.

Không vội tăng heap hoặc đổi collector khi phần lớn latency nằm ở downstream.

### 12.2. Có STW pause 100 ms trùng với request spike

Đây là tín hiệu quan trọng, nhưng cần xác định request spans nào overlap và thread state. Một pause có thể chặn nhiều Java threads cùng lúc, ảnh hưởng tail latency hoặc queue. Tuy nhiên **không tự cộng đủ 100 ms vào tất cả request durations**.

### 12.3. Giảm MaxGCPauseMillis nhưng p99 vẫn tăng

GC có thể chạy thường hơn, mất CPU/throughput hoặc cùng lúc có yếu tố khác. So pause histogram, pause frequency, total pause time, concurrent work, allocation rate, heap pressure và p99 ở workload tương đương. Pause thấp là một phần KPI, không phải KPI cuối.

### 12.4. Không có event GC trong JFR

Cần xác minh recording settings và phạm vi time window, không coi count=0 là khẳng định “GC vô can”. Có thể không có pause trong cửa sổ, event không được bật hoặc dữ liệu đã bị loại do retention. Có thể đối chiếu GC logs/metrics, nhưng tránh suy luận từ những khoảng không có dữ liệu.

## 13. Quy trình chẩn đoán có đối chứng

### Bước 1 — Định nghĩa SLO

Cho biết client p99, gateway p99 hay server handler p99. Chọn endpoint/request groups và cửa sổ tải.

### Bước 2 — Thu baseline đồng bộ

Thu GC pause events, GC/safepoint logs, request traces, CPU, heap, allocation, queue, network/downstream và traffic. Ghi JDK build, collector, GC options, JFR settings và recording duration.

### Bước 3 — Lập giả thuyết cụ thể

Ví dụ: “Trong spike, request handler trên JVM X đang runnable khi GC pause bắt đầu, bị dừng, và sau đó backlog tăng”.

### Bước 4 — Tìm bằng chứng phủ định

Có requests chậm mà không overlap GC không? Có requests overlap GC nhưng vẫn nhanh không? Downstream/CPU quota có tăng đồng thời không? Nếu có, cần sửa giả thuyết hoặc khoanh vùng.

### Bước 5 — Thử nghiệm một thay đổi

Thay heap size hoặc mục tiêu GC pause **một yếu tố mỗi lượt** ở môi trường an toàn, giữ traffic mix, CPU quota, cache và downstream gần tương đương. Đo nhiều lần, có rollback/A-B/A khi phù hợp.

### Bước 6 — Kết luận theo mức độ chắc chắn

| Mức | Câu nên dùng |
| --- | --- |
| Quan sát | “GC pause 18ms overlap với server request span 200ms trên cùng JVM.” |
| Giả thuyết | “GC có thể góp một phần vào tail latency.” |
| Bằng chứng cơ chế | “Request thread bị ảnh hưởng tại safepoint; queue tăng sau pause.” |
| Đối chứng | “Thay đổi có kiểm soát giảm pause và cải thiện p99/throughput ở các lượt đo lặp.” |
| Hạn chế | “Chưa kiểm tra network jitter/downstream của toàn bộ production traffic.” |

Chỉ nâng mức kết luận khi có bằng chứng tương ứng.

## 14. Những lỗi phổ biến

| Hiểu nhầm | Điều đúng |
| --- | --- |
| GC pause và request end-to-end latency cùng một metric. | Đo hai phạm vi khác nhau. |
| Pause p99 10 ms nghĩa request p99 tối đa 10 ms. | Request còn queue, I/O, network, lock, retries. |
| MaxGCPauseMillis là hard SLA. | Với G1 nó là mục tiêu mềm. |
| GC cycle 300 ms là STW 300 ms. | Cycle có thể có concurrent phases. |
| Concurrent GC không ảnh hưởng request. | Có thể cạnh tranh CPU/memory bandwidth. |
| Mọi event GCPhasePause cấp con đều cộng vào total. | Có thể lồng nhau; phải merge/loại trùng. |
| Pause overlap 25 ms = GC gây delay 25 ms. | Overlap không phải causal attribution. |
| Outside overlap 95 ms = 95 ms CPU. | Vẫn có thể bị blocked/waiting. |
| Overlap bằng 0 nghĩa GC vô can. | Có ảnh hưởng gián tiếp qua concurrent work/queue. |
| p99 GC + p99 DB + p99 network = request p99. | Percentiles không cộng tuyến tính. |
| GC pause histogram và request histogram có cùng N. | Một bên đếm pauses, một bên requests. |
| Handler duration bằng client latency. | Handler có thể không bao phủ network và queue. |
| JFR không có GCPhasePause nghĩa JVM không có GC. | Recording coverage/settings/retention có giới hạn. |
| Giảm mục tiêu pause luôn làm p99 tốt hơn. | Có tradeoff với throughput, CPU và GC frequency. |
| Tăng mọi event để có đầy đủ bằng chứng. | Tăng overhead và rủi ro dữ liệu nhạy cảm. |
| Timestamp từ hai hosts luôn tương đương. | Có clock skew và instrumentation delay. |

## 15. Bài tập và đáp án

**Câu 1.** Request 200 ms giao với GC pause 10 ms; GC chắc chắn gây 10 ms latency không?

**Đáp án:** Không. Cần biết thread/request state và critical path; overlap chỉ chứng minh cùng khoảng thời gian.

**Câu 2.** GC pause 5 ms nhưng p99 request 400 ms, có mâu thuẫn không?

**Đáp án:** Không. Request có queue, I/O, network, downstream và nhiều cơ chế khác.

**Câu 3.** `-XX:MaxGCPauseMillis=20` có bảo đảm mọi pause dưới 20 ms?

**Đáp án:** Không. G1 pause target là mục tiêu mềm.

**Câu 4.** Một GC cycle 300 ms có thể chỉ có STW pause 15 ms không?

**Đáp án:** Có thể, vì cycle có concurrent phases; cần xem event/log cụ thể để xác định.

**Câu 5.** Tại sao không cộng 15 ms parent pause và 4 ms child pause?

**Đáp án:** Child nằm trong parent, cộng sẽ đếm trùng. Cần hợp intervals.

**Câu 6.** Request `[100,220)`, pauses `[160,175)`, `[168,172)`, `[205,215)`. Union overlap?

**Đáp án:** **25 ms**.

**Câu 7.** 95 ms ngoài pause windows có phải 95 ms CPU?

**Đáp án:** Không. Có thể gồm sleep, lock, network và scheduling.

**Câu 8.** Có thể cộng p99 GC + p99 DB để ra p99 HTTP không?

**Đáp án:** Không. Percentiles trên các distributions khác nhau không cộng như vậy.

**Câu 9.** Vì sao client p99 và server handler p99 khác nhau?

**Đáp án:** Điểm đo và phạm vi khác; client gồm network/proxy/queue hoặc response transfer.

**Câu 10.** GCPhasePause event không xuất hiện trong 1s recording, có chứng minh không có GC trong cả ngày không?

**Đáp án:** Không. Phạm vi recording quá ngắn và phụ thuộc event settings.

**Câu 11.** `RecordedEvent.getDuration()` có phải CPU time không?

**Đáp án:** Không. Nó là elapsed duration của event được instrument.

**Câu 12.** GC concurrent có thể gây latency dù pause rất ngắn không?

**Đáp án:** Có thể, vì dùng CPU và memory bandwidth.

**Câu 13.** Một pause 100 ms có chắc mỗi request bị thêm đủ 100 ms không?

**Đáp án:** Không. Tác động phụ thuộc vị trí request trên critical path và thread đang làm gì.

**Câu 14.** Nên dùng `System.nanoTime()` làm gì?

**Đáp án:** Đo duration monotonic **trong cùng JVM**; không dùng như epoch timestamp xuyên các host.

**Câu 15.** Ngoài GC pause phải đo gì khi thử tuning G1?

**Đáp án:** Request p95/p99, throughput, CPU, GC frequency, heap/allocation, queue và downstream.

**Câu 16.** Khi nào kết luận “GC là nguyên nhân” đáng tin hơn?

**Đáp án:** Khi có timeline đúng JVM, cơ chế thread/queue rõ, dữ liệu độc lập đối chiếu và thí nghiệm có đối chứng lặp lại.

## 16. Tổng kết và tài liệu chính thức

- **GC pause** là một khoảng dừng JVM, **request latency** là thời gian của yêu cầu theo một scope client/gateway/server. Chúng không phải một đại lượng.
- **GC cycle** có thể có concurrent phases; **safepoint sync** không được cộng chồng bừa với pause.
- **`jdk.GCPhasePause`**, JFR và unified GC/safepoint logs là công cụ Java 11 hữu ích để đo và đối chiếu.
- **Union overlap** chỉ cho độ phủ thời gian giao nhau, không tự tính ảnh hưởng nhân quả của GC lên request.
- **G1 MaxGCPauseMillis là mục tiêu mềm**, không phải cam kết p99 của application.
- Nghiên cứu low-latency phải dùng request SLO, queue, CPU, throughput, downstream và GC metrics cùng nhau.
- Ví dụ chạy Java 11 xác minh hai custom request spans và phép tính union pause giả định 25 ms trong request 120 ms.
- Chỉ kết luận nguyên nhân với dữ liệu đủ coverage, cơ chế có căn cứ và kiểm thử có đối chứng.

Tài liệu chính thức còn áp dụng:

- [Oracle Java SE 11 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/11/gctuning/garbage-first-g1-garbage-collector3.html).
- [Oracle Java SE 11 — G1 Tuning](https://docs.oracle.com/en/java/javase/11/gctuning/garbage-first-garbage-collector-tuning1.html).
- [Oracle Java SE 11 — Recording](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html).
- [Oracle Java SE 11 — Event](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html).
- [Oracle Java SE 11 — EventSettings](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventSettings.html).
- [Oracle Java SE 11 — RecordedEvent](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html).
- [Oracle Java SE 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html).
- [Oracle Java SE 11 — jfr tool](https://docs.oracle.com/en/java/javase/11/tools/jfr.html).
- [Oracle Java SE 11 — jcmd](https://docs.oracle.com/en/java/javase/11/tools/jcmd.html).
- [Oracle Java SE 11 — java -Xlog options](https://docs.oracle.com/en/java/javase/11/tools/java.html).
- [OpenJDK — JEP 328 Flight Recorder](https://openjdk.org/jeps/328).