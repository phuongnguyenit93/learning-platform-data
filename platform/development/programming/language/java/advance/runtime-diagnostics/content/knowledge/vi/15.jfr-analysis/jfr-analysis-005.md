# 15.5 Khoanh cửa sổ thời gian xảy ra triệu chứng rồi đối chiếu nhiều nhóm event

> **Phạm vi:** Phân tích bản ghi **Java Flight Recorder (JFR)** của JVM Java 21 khi ứng dụng có triệu chứng như p99 latency tăng, throughput tụt, request timeout hoặc CPU đột biến. Trọng tâm là chuyển từ *thời điểm triệu chứng bên ngoài* sang **một cửa sổ thời gian có thể kiểm chứng**, rồi nhìn **GC, CPU, lock/thread, I/O, allocation và virtual threads** trong cùng cửa sổ để xây dựng và kiểm tra giả thuyết. Bài học sử dụng JDK Mission Control (JMC), lệnh `jcmd`/`jfr` và API `jdk.jfr.consumer` có sẵn trong JDK 21.

## 1. Mục tiêu và nguyên tắc chẩn đoán

Sau bài học, bạn có thể:

1. Đổi một alert/trace/request log thành khoảng thời gian **tuyệt đối** `[từ, đến)` trên một trục UTC, ghi rõ nguồn timestamp, timezone, độ lệch đồng hồ và thời gian trước/sau để quan sát nguyên nhân, hậu quả.
2. Xác định recording JFR nào bao trùm khoảng đó; trích xuất khoảng cần thiết bằng `JFR.dump begin=... end=...` nếu recording còn hoạt động hoặc lọc event từ tệp `.jfr` có sẵn.
3. Đọc chính xác timestamp **bắt đầu/kết thúc** và **thời lượng** của event; so sánh các nhóm event theo **cùng thời gian**, không lấy event nổi bật ở thời điểm khác để giải thích sự cố.
4. Phân biệt tương quan theo thời gian với nhân quả, đặc biệt với event sampling, threshold, khoảng trống thu thập và các event chồng lấn.
5. Tạo một bảng bằng chứng đủ tái kiểm chứng: triệu chứng, cửa sổ, nguồn JFR, các event/stack liên quan, giả thuyết và phép đo tiếp theo.

**Quy tắc cốt lõi:** *Khoanh thời điểm triệu chứng trước, mới xem event.* Một GC dài, stack CPU nóng hay `SocketRead` lâu ở ngoài cửa sổ p99 tăng chưa phải bằng chứng cho sự cố đang điều tra. Ngược lại, trong cùng cửa sổ có nhiều event tăng cũng chưa chứng minh event nào gây ra event nào.

## 2. Chọn cửa sổ từ dữ liệu triệu chứng

### 2.1. Lấy mốc ngoài JVM

Bắt đầu từ **alert, latency/error dashboard, tracing hoặc log request**. Thu ít nhất: tên service/instance/pod, loại triệu chứng, lúc bắt đầu, lúc kết thúc hoặc đỉnh, độ phân giải metric (1 phút/10 giây), timezone và mức độ chắc chắn.

Ví dụ giả định (không phải dữ liệu thật):

| Nguồn | Quan sát | UTC |
| --- | --- | --- |
| Metrics gateway | p99 từ khoảng 180 ms lên 2,8 s | 10:12:30–10:14:00 |
| Error dashboard | Timeout tăng cùng khoảng | 10:12:40–10:14:10 |
| Distributed trace | Một số span gọi dịch vụ downstream kéo dài | 10:12:45–10:13:50 |
| JVM mục tiêu | `payment-api`, pod `payment-7c9...`, PID và startup time đã xác nhận | Recording bao trùm 10:05–10:25 |

Chọn hai khoảng và luôn phân biệt:

- **Cửa sổ triệu chứng:** ví dụ `[2026-10-29T10:12:30Z, 2026-10-29T10:14:10Z)`. Dùng để tính “trong thời gian sự cố”.
- **Cửa sổ phân tích mở rộng:** ví dụ `[2026-10-29T10:11:30Z, 2026-10-29T10:15:10Z)`, thêm 60 giây trước/sau để phát hiện yếu tố đi trước và quá trình phục hồi. Buffer phải phù hợp nhịp thu metric và độ dài request; không có con số 60 giây đúng cho mọi hệ thống.
- **Cửa sổ đối chứng:** một khoảng bình thường tương đương độ dài, tải, thời điểm warmup và cùng cấu hình recording nếu có, ví dụ 10:07:00–10:10:40 UTC.

Đối với metric được tổng hợp theo bucket một phút, điểm “10:13” có thể biểu diễn dữ liệu tích lũy trong cả một phút theo quy ước của hệ thống. Không khẳng định thời điểm bắt đầu chính xác đến mili giây nếu dashboard chỉ có độ phân giải một phút.

### 2.2. Chuẩn hóa thời gian và định danh

Trong Java, event JFR có `Instant getStartTime()` và `Instant getEndTime()`. Dùng **UTC hoặc `Instant`** làm trục chung; chỉ đổi sang giờ địa phương để trình bày.

```text
2026-10-29 17:12:30 +07:00 = 2026-10-29T10:12:30Z
2026-10-29 17:14:10 +07:00 = 2026-10-29T10:14:10Z
```

Phải kiểm tra:

- **Clock skew:** máy chạy app, collector, database và gateway có đồng bộ NTP không? Độ lệch vài giây có thể đổi thứ tự suy luận “event xảy ra trước request”.
- **Trace/span timestamps:** dấu thời gian bắt đầu và duration khác loại “thời điểm kết thúc request”; dựng lại khoảng request `[start, start + duration)` thay vì chỉ căn theo log hoàn thành.
- **JVM identity:** PID có thể bị tái sử dụng sau restart; ghi tên pod, host, container ID, JDK build và *startup time*. Chỉ so cùng instance/recording khi kết luận về cùng quá trình.
- **Time zone/JFR CLI:** `JFR.dump begin/end` chấp nhận `Instant` dạng `Z` theo JDK 21; thời gian không có timezone có thể được diễn giải theo local time. Ưu tiên ISO 8601 với `Z` và ghi rõ múi giờ của log.
- **Điểm biên:** định nghĩa cửa sổ `[start,end)` giúp không đếm event tức thời tại ranh giới `end` hai lần khi chia bucket liên tiếp.

Nếu không thể ước tính clock skew, mở rộng khoảng quan sát và ghi **sai số căn thời gian** trong kết luận.

## 3. Đọc event đúng cách trước khi đối chiếu

JFR có **instant events** (timestamp là một điểm), **duration events** (khoảng `[start,end]`) và **sampling events** (mẫu chọn tại một thời điểm). Không phải mỗi hàng event có ý nghĩa như nhau.

- **`startTime` và `endTime`:** event dài có thể **bắt đầu trước** cửa sổ triệu chứng và **kết thúc trong** cửa sổ. Lọc chỉ bằng `startTime >= from` sẽ bỏ sót event đang kéo dài. Nên xét giao giữa `[eventStart,eventEnd)` và `[from,to)`; instant event thì kiểm tra timestamp nằm trong `[from,to)`.
- **`duration`:** độ dài của chính event, không mặc nhiên là thời gian request bị ảnh hưởng. Một `SocketRead` dài có thể chứa thời gian chờ peer; một `JavaMonitorEnter` thể hiện thời gian chờ vào monitor.
- **`eventThread`/thread ID, stack trace:** giúp liên kết event theo thread hoặc call site; thread không nhất thiết trùng request vì executor/virtual-thread scheduling, và một request có thể đi qua nhiều thread.
- **Count / total duration / p95 duration:** chỉ số dùng được nếu cùng event type, cùng threshold và cửa sổ có độ dài so sánh được. Không cộng toàn bộ `duration` giữa những event chồng lấn rồi gọi đó là “JVM downtime”.
- **`jdk.ExecutionSample` và `jdk.ObjectAllocationSample`:** số mẫu cho biết xu hướng hot path/allocations trong điều kiện sampling, **không** là số lần thực thi hoặc số allocation chính xác.
- **Sự kiện vắng mặt:** có thể do cấu hình recording, threshold, sampling, buffer loss, thiếu stack trace hoặc cửa sổ không bao trùm. Phải xác minh bật event trước khi kết luận “không có vấn đề”.

Trên JDK 21, nhiều event chặn I/O/monitor chỉ ghi sau khi vượt threshold (thường khoảng **20 ms** theo cấu hình); cấu hình `.jfc` quyết định giá trị thực tế. Cùng một thao tác bị lặp hàng nghìn lần nhưng mỗi lần 5 ms có thể không tạo hàng nghìn event tương ứng.

## 4. Bản đồ các nhóm event cần đối chiếu

| Nhóm / ví dụ tên event trên Java 21 | Điều có thể quan sát | Câu hỏi kiểm tra tiếp |
| --- | --- | --- |
| **CPU/sampling** — `jdk.CPULoad`, `jdk.ThreadCPULoad`, `jdk.ExecutionSample` | JVM/machine CPU, mức sử dụng thread, stack được lấy mẫu | CPU JVM tăng trước hay sau p99? Có hot stack lặp lại trong cửa sổ? |
| **GC/safepoint** — `jdk.GarbageCollection`, `jdk.GCPhasePause`, `jdk.SafepointBegin` (nếu có) | Thời điểm GC, giai đoạn pause, safepoint | Pause nào giao với cửa sổ? Có giải thích được một phần latency không? |
| **Allocation/heap** — `jdk.ObjectAllocationSample`, `jdk.GCHeapSummary` | Đối tượng được lấy mẫu cấp phát, heap trước/sau GC | Áp lực allocation/GC tăng trước khi p99 xấu đi? |
| **Monitor/parking** — `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`, `jdk.ThreadPark`, `jdk.ThreadSleep` | Chờ khóa monitor, `Object.wait`, park/sleep | Stack hoặc tài nguyên tranh chấp nào lặp lại? Thread chờ có nằm trong request critical path không? |
| **Socket/file I/O** — `jdk.SocketRead`, `jdk.SocketWrite`, `jdk.FileRead`, `jdk.FileWrite` | Các thao tác I/O dài được ghi nhận, thời lượng và một số trường peer/path | Chậm ở kết nối/host/file nào, trùng các span downstream nào? |
| **Virtual threads (Java 21)** — `jdk.VirtualThreadPinned` | Virtual thread chặn khi đang pinned carrier, thời lượng/stack (nếu bật) | Pinning đủ lâu, đủ thường xuyên để giảm khả năng phục vụ không? |
| **Ngoại lệ/phụ trợ** — `jdk.JavaExceptionThrow`, `jdk.JavaErrorThrow` (nếu bật) | Một số exception/error phát sinh | Có tăng gần lúc timeout, liên quan stack nào? Chi phí khi bật event rất nhiều có chấp nhận được không? |

**Không mặc định tất cả event đều được bật trong `settings=default` hoặc `settings=profile`.** Kiểm tra metadata và cấu hình recording thực tế; event có trong JDK không đồng nghĩa đã ghi trong tệp. Chọn các nhóm liên quan triệu chứng trước rồi mở rộng theo bằng chứng.

Các tên event trên là tên đầy đủ **`jdk.*`** của Java 21; khi dùng `jfr print --events` có thể kết hợp bằng dấu phẩy. Một số event không có thông tin về request ID, endpoint hoặc tên service downstream; chỉ có stack/thread/host là dấu hiệu gián tiếp. Nên kết hợp APM/log để xác định ứng dụng.

## 5. Thu và khoanh tệp JFR bằng công cụ JDK 21

### 5.1. Một recording có sẵn trong JVM đang chạy

Kiểm tra đúng JVM có thể attach; trên Linux yêu cầu cùng máy/user phù hợp. Các lệnh chứa `<PID>` là **mẫu**, phải thay bằng PID đã xác minh:

```bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> JFR.check
jcmd <PID> help JFR.dump
```

Nếu recording phù hợp **đang chạy và còn giữ dữ liệu**, có thể lấy riêng cửa sổ với `JFR.dump`:

```bash
jcmd <PID> JFR.dump name=incident \
  begin=2026-10-29T10:11:30Z end=2026-10-29T10:15:10Z \
  filename=/srv/diagnostics/incident-window.jfr
```

**Các timestamp và đường dẫn chỉ là ví dụ giả định.** Đường dẫn phải ghi được trong **filesystem của JVM đích**, không nhất thiết là máy người gọi. `JFR.dump` không dừng recording đang chạy; JDK 21 hỗ trợ `begin`/`end` bằng thời gian tuyệt đối (ví dụ Instant `...Z`) hoặc dạng local, và các tùy chọn `maxage`/`maxsize`. Nó chỉ có thể trích những event **đã tồn tại trong dữ liệu recording còn được giữ lại**; không khôi phục đoạn trước khi recording bắt đầu hoặc đã bị retention xóa.

Chú ý: event dài ở mép cửa sổ, metadata và cách cắt dữ liệu giữa các chunk có thể làm kết quả khác một phép lọc từng event theo giao khoảng ở bước phân tích. Khi cần chứng minh chính xác event bắt đầu trước cửa sổ, hãy giữ **bản recording gốc đủ rộng** rồi lọc theo `getStartTime/getEndTime` ở mục 7.

### 5.2. Chưa bật JFR khi sự cố xảy ra

Nếu recording chưa có, bạn chỉ có thể thu **từ lúc bật trở đi**, không tái tạo các event quá khứ. Với cuộc điều tra tiếp tục hoặc triệu chứng tái diễn, sau khi cân nhắc overhead và nơi lưu:

```bash
jcmd <PID> JFR.start name=incident settings=profile \
  disk=true maxage=30m maxsize=256m
jcmd <PID> JFR.check
```

Khi đủ dữ liệu:

```bash
jcmd <PID> JFR.dump name=incident \
  filename=/srv/diagnostics/incident-all.jfr
```

Các giá trị `30m`/`256m` là **ví dụ**; điều chỉnh theo tốc độ phát event, retention và dung lượng đĩa. `settings=profile` thường thu nhiều dữ liệu hơn `default`, có thể tăng overhead; thử trên staging/canary trước khi dùng kéo dài. Nếu cần ngưỡng khác để bắt I/O ngắn, lập `.jfc` riêng hoặc dùng cấu hình JFR đã kiểm chứng và ghi lại thay đổi.

### 5.3. Trường hợp đã có một file `.jfr` được giao

**Giữ bản gốc bất biến**, ghi checksum/source và dùng các công cụ đọc:

```bash
jfr summary incident-all.jfr
jfr metadata --events jdk.GarbageCollection,jdk.SocketRead incident-all.jfr
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause incident-all.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.ThreadPark incident-all.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite incident-all.jfr
jfr print --events jdk.CPULoad,jdk.ExecutionSample incident-all.jfr
```

`jfr summary` cho số lượng/kích thước event và khoảng recording; **không** thay dashboard triệu chứng. `jfr metadata` cho biết layout trường trong bản ghi. `jfr print` lọc theo **tên event** hoặc **category**, không có đối số `--start/--end` trong cú pháp `jfr print` của JDK 21. Để lọc chính xác theo thời gian khi chỉ có file, dùng JMC chọn interval hoặc API Java ở mục 7.

Khi tìm stack chi tiết:

```bash
jfr print --stack-depth 64 \
  --events jdk.JavaMonitorEnter,jdk.SocketRead incident-all.jfr
```

Không đặt kỳ vọng mọi event sẽ có stack. Output có thể dài và chứa đường dẫn/method nội bộ; chuyển file và chia sẻ theo quy trình bảo mật.

## 6. Đối chiếu trực quan trong JDK Mission Control

JMC là công cụ giao diện để khám phá recording (có thể cần cài riêng). Tên trang/tab cụ thể thay đổi theo phiên bản JMC; quy trình quan trọng hơn tên nút:

1. **Mở bản `.jfr` gốc** và xác nhận JVM metadata, duration, timezone, record settings; đảm bảo khoảng alert nằm trong thời gian recording.
2. **Đặt vùng chọn trên timeline** bao trùm cửa sổ mở rộng. Đối chiếu timestamp bắt đầu/kết thúc hiện trong JMC với UTC alert, không dựa vào vị trí tương đối của thanh kéo.
3. **Đọc CPU/GC timeline** trước để thấy các đỉnh dài, đợt GC và khoảng trễ. Chọn đúng cùng interval khi chuyển giữa các trang.
4. **Xem Method Profiling / Java Application / Threads** (tùy phiên bản). Xem sample/call tree, monitor contention và park; đọc stack cùng thread/time ở khoảng đã chọn.
5. **Xem Socket I/O / File I/O**, phân nhóm theo host/đường dẫn và stack; so với span downstream/DB khi có.
6. **Xem allocation và virtual thread event** nếu recording có bật; không suy luận “không có” khi event không được ghi.
7. **Chuyển sang cửa sổ đối chứng** dài bằng cửa sổ sự cố, áp dụng cùng phép nhóm/định nghĩa chỉ số để tránh cherry-pick.

Với event kéo dài, hãy kiểm tra cả **bắt đầu và kết thúc**. Ví dụ một socket read bắt đầu 10:12:10, kết thúc 10:13:20 sẽ giao với cửa sổ bắt đầu 10:12:30 dù `startTime` của nó nằm bên ngoài.

## 7. Lọc và thống kê cửa sổ bằng API Java 21

Dưới đây là chương trình Java độc lập **`WindowJfrReport.java`**, sử dụng module `jdk.jfr` có sẵn trong JDK 21. Nó **stream** từng event bằng `RecordingFile` thay vì nạp toàn bộ recording vào RAM; nhận hai thời điểm ISO 8601 có offset (`Z` hoặc `+07:00`), chọn những event được liệt kê và in **count** cùng **tổng mili giây giao cửa sổ** theo *event type*.

Tạo tệp **`WindowJfrReport.java`**:

```java
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class WindowJfrReport {
    private static final Map<String, String> GROUPS = Map.ofEntries(
        Map.entry("jdk.CPULoad", "CPU"),
        Map.entry("jdk.ThreadCPULoad", "CPU"),
        Map.entry("jdk.ExecutionSample", "CPU"),
        Map.entry("jdk.GarbageCollection", "GC"),
        Map.entry("jdk.GCPhasePause", "GC"),
        Map.entry("jdk.ObjectAllocationSample", "ALLOC"),
        Map.entry("jdk.JavaMonitorEnter", "WAIT"),
        Map.entry("jdk.JavaMonitorWait", "WAIT"),
        Map.entry("jdk.ThreadPark", "WAIT"),
        Map.entry("jdk.ThreadSleep", "WAIT"),
        Map.entry("jdk.SocketRead", "IO"),
        Map.entry("jdk.SocketWrite", "IO"),
        Map.entry("jdk.FileRead", "IO"),
        Map.entry("jdk.FileWrite", "IO"),
        Map.entry("jdk.VirtualThreadPinned", "VTHREAD"),
        Map.entry("demo.PhaseMarker", "MARKER")
    );

    static final class Stat {
        final String group;
        long count;
        long overlapNanos;

        Stat(String group) {
            this.group = group;
        }

        void add(long nanos) {
            count++;
            overlapNanos += nanos;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println(
                "Usage: java WindowJfrReport file.jfr fromISO toISO");
            return;
        }
        Path path = Path.of(args[0]);
        Instant from = OffsetDateTime.parse(args[1]).toInstant();
        Instant to = OffsetDateTime.parse(args[2]).toInstant();
        if (!to.isAfter(from)) {
            throw new IllegalArgumentException("to must be after from");
        }

        Map<String, Stat> stats = new TreeMap<>();
        try (RecordingFile recording = new RecordingFile(path)) {
            while (recording.hasMoreEvents()) {
                RecordedEvent event = recording.readEvent();
                String type = event.getEventType().getName();
                String group = GROUPS.get(type);
                if (group == null) {
                    continue;
                }

                Instant begin = event.getStartTime();
                Instant end = event.getEndTime();
                boolean point = !end.isAfter(begin);

                boolean intersects = point
                    ? !begin.isBefore(from) && begin.isBefore(to)
                    : begin.isBefore(to) && end.isAfter(from);
                if (!intersects) {
                    continue;
                }

                long nanos = 0;
                if (!point) {
                    Instant clippedStart =
                        begin.isAfter(from) ? begin : from;
                    Instant clippedEnd =
                        end.isBefore(to) ? end : to;
                    nanos = Duration.between(
                        clippedStart, clippedEnd).toNanos();
                }
                stats.computeIfAbsent(
                    type, key -> new Stat(group)).add(nanos);
            }
        }

        System.out.println("WINDOW UTC: " + from + " .. " + to);
        System.out.printf(
            "%-9s %-29s %8s %12s%n",
            "GROUP", "EVENT", "COUNT", "OVERLAP_MS");
        for (Map.Entry<String, Stat> row : stats.entrySet()) {
            Stat stat = row.getValue();
            System.out.printf(
                Locale.ROOT, "%-9s %-29s %8d %12.1f%n",
                stat.group, row.getKey(), stat.count,
                stat.overlapNanos / 1_000_000.0);
        }
        if (stats.isEmpty()) {
            System.out.println("No selected events in window");
        }
    }
}
```

Biên dịch/chạy trên JDK 21, **không cần thư viện ngoài** và không dùng preview:

```bash
javac WindowJfrReport.java
java WindowJfrReport incident-all.jfr \
  2026-10-29T10:11:30Z 2026-10-29T10:15:10Z
```

Hai timestamp là **cửa sổ minh họa**, cần thay đúng thời gian của recording. Vì sự kiện trong file thật thay đổi, **không có bảng stdout cố định**. Các nhãn cột in ra là `GROUP`, `EVENT`, `COUNT`, `OVERLAP_MS`. Nếu file không có loại event được chọn trong khoảng, in `No selected events in window`.

**Cách diễn giải đúng kết quả chương trình:**

- `COUNT` là số **event đã được ghi** mà khoảng thời gian giao với cửa sổ. Nó không bằng số request, số lần cấp phát hay số operation nếu có threshold/sampling.
- `OVERLAP_MS` là tổng phần **thời lượng giao cửa sổ** của từng event, nên không cộng phần kéo ra ngoài cửa sổ. Với event tức thời/sampled, thời lượng này bằng 0 mặc dù count có thể lớn.
- Các event GC có thể **lồng nhau** (`GarbageCollection` và `GCPhasePause`); event I/O/park có thể song song ở nhiều thread. **Không cộng `OVERLAP_MS` qua các type/group để tính “downtime”** hoặc tỷ lệ CPU.
- Code lọc theo **event overlap**, không lọc theo thread, stack hay tác nhân phía ngoài. Đây là **bảng đầu mối**; điều tra nguyên nhân vẫn phải drill down vào event, `eventThread`, stack, host/peer và trace của request.
- Event bị mất do giới hạn recording hay chưa bật không thể xuất hiện trở lại nhờ bộ lọc.

Đối với tập tin rất lớn, `RecordingFile.readAllEvents` có thể chiếm nhiều RAM; vòng lặp `hasMoreEvents/readEvent` ở ví dụ tránh lưu toàn bộ event trong danh sách.

## 8. Lab tái hiện cửa sổ bằng một recording tự tạo

Để thực hành mà không cần service thật, dùng `WindowLab.java` ghi custom `demo.PhaseMarker` (đánh dấu giai đoạn) và `jdk.ThreadSleep` (một duration event). Cửa sổ sẽ có các mark `warmup`, `slow`, `recovery` và những lần `sleep` với độ dài khác nhau. Đây là lab **không mô phỏng sự cố production**: chỉ tập đọc timeline/cửa sổ.

Tạo tệp **`WindowLab.java`**:

```java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.Configuration;

public class WindowLab {
    @Name("demo.PhaseMarker")
    @Label("Lab Phase")
    static class PhaseMarker extends Event {
        @Label("Phase")
        String phase;
    }

    private static void mark(String phase) {
        PhaseMarker event = new PhaseMarker();
        event.phase = phase;
        event.commit();
    }

    public static void main(String[] args) throws Exception {
        try (Recording recording =
                 new Recording(Configuration.getConfiguration("default"))) {
            recording.setToDisk(true);
            recording.enable(PhaseMarker.class);
            recording.enable("jdk.ThreadSleep")
                     .withThreshold(Duration.ofMillis(1));
            recording.start();

            mark("warmup");
            Thread.sleep(40);
            mark("slow");
            Thread.sleep(180);
            mark("recovery");
            Thread.sleep(40);

            recording.stop();
            recording.dump(Path.of("window-lab.jfr"));
        }
        System.out.println("LAB DONE: window-lab.jfr");
    }
}
```

Chạy với JDK 21:

```bash
javac WindowLab.java
java WindowLab
jfr summary window-lab.jfr
jfr print --events demo.PhaseMarker,jdk.ThreadSleep window-lab.jfr
```

**Stdout nghiệp vụ duy nhất của `WindowLab`** (không tính output của lệnh `jfr`):

```text
LAB DONE: window-lab.jfr
```

`Thread.sleep(180)` là lời gọi chặn có chủ đích, không phải bằng chứng CPU spike. Số lượng `jdk.ThreadSleep`, khoảng timestamp và stack trace sẽ phụ thuộc runtime; không giả định file có đúng ba event ngủ nếu JVM ghi thêm thread khác. `demo.PhaseMarker` có timestamp điểm, còn `ThreadSleep` là duration event; thực hành chọn một cửa sổ chứa riêng giai đoạn `slow` rồi so với toàn recording.

Sau khi xem các mốc `startTime` do `jfr print` hiển thị, chọn hai timestamp ISO offset phù hợp và chạy `WindowJfrReport` đã biên dịch:

```bash
java WindowJfrReport window-lab.jfr \
  2026-10-29T10:00:00Z 2026-10-29T11:00:00Z
```

**Đổi hai thời điểm** thành khoảng thật xuất hiện trong `window-lab.jfr`; dòng trên chỉ minh họa cú pháp, có thể trả về không có event nếu thời gian khác. Thử thu hẹp khoảng 20–30 ms quanh một marker để thấy điểm biên và event ngủ kéo dài có thể giao cửa sổ dù bắt đầu trước đó.

## 9. Từ bảng event đến giả thuyết: ví dụ điều tra

Giả sử symptom p99 từ 180 ms lên 2,8 s trong 10:12:30–10:14:10 UTC, dữ liệu JFR cùng JVM (tất cả số liệu dưới đây **giả lập để luyện phân tích**, không phải output của chương trình ở trên):

| Khoảng UTC | JFR / telemetry | Bằng chứng giả lập | Nhận xét ban đầu |
| --- | --- | --- | --- |
| 10:11:30–10:12:30 | GC + CPU | GC pause tổng 50 ms; JVM CPU 42% | Cửa sổ trước sự cố tương đối bình thường |
| 10:12:30–10:13:10 | Socket I/O | Nhiều `jdk.SocketRead` 400–900 ms, cùng peer/backend | Chờ downstream là giả thuyết mạnh; cần trace kết nối cụ thể |
| 10:13:10–10:13:50 | Thread parking/monitor | `ThreadPark` tăng; `JavaMonitorEnter` lặp trên cùng stack | Có thể là đợi pool/khóa thứ cấp khi request dồn ứ |
| 10:12:30–10:14:10 | GC pause | Một số pause ngắn, không trùng đỉnh request timeout | GC chưa giải thích được toàn bộ p99 |
| 10:12:30–10:14:10 | CPU samples + load | CPU JVM vẫn dưới mức saturation, không có hot path nổi bật | Giảm ưu tiên giả thuyết CPU-bound, nhưng sample có giới hạn |
| 10:14:10–10:15:10 | Socket + latency | SocketRead trở lại thấp và p99 giảm | Có tương quan phục hồi; vẫn cần dữ liệu ở peer |

Đây là **chuỗi bằng chứng** chứ chưa phải bản án “downstream gây lỗi”. Phải kiểm chứng:

1. Event `jdk.SocketRead` nằm trên **cùng request path**, đọc `eventThread`, stack/endpoint nếu có, so timestamp với span outbound và server-side latency.
2. Kiểm tra `ThreadPark` là chờ connection pool, semaphore hay task queue nào; lượng chờ tăng **sau** SocketRead dài gợi ý hiệu ứng thứ cấp nhưng cần thêm metric queue/pool.
3. Quan sát CPU/GC trước, trong, sau; GC ngắn vẫn có thể gây jitter cụ thể, nhưng nếu tổng bằng chứng không giải thích mức p99 thì không khẳng định GC là nguyên nhân chính.
4. So với **cửa sổ đối chứng** có request volume tương đương; số `SocketRead` tăng có thể chỉ do lưu lượng tăng. Chuẩn hóa theo requests/s hoặc event/s khi phù hợp.
5. Nếu có thay đổi cấu hình/deploy/traffic đúng lúc, thêm chúng vào timeline để tránh bỏ sót nguyên nhân bên ngoài JVM.

Một bảng báo cáo tốt nên ghi rõ **nguyên nhân còn phải xác thực** và dữ liệu tiếp theo cần thu, thay vì liệt kê mọi event cao nhất trong file.

## 10. Ba bẫy khi so sánh nhiều nhóm event

### 10.1. Nhầm đồng thời với nhân quả

Một request tắc ở DB sẽ sinh `SocketRead` dài; hàng chờ tăng có thể làm `ThreadPark` tăng; retries tiếp tục tăng I/O. Cả ba nhóm xuất hiện cùng phút nhưng không có nghĩa “park gây network timeout”. Hãy lập thứ tự theo **thời điểm xuất hiện đầu tiên, khoảng duration, thread/stack và span quan hệ cha-con**.

Mốc thời gian cần có sai số: khi metric bucket là 60 giây và JFR timestamp chính xác hơn, không được tuyên bố “GC xảy ra 2 ms trước p99 spike” dựa vào bucket minute.

### 10.2. Nhầm số lượng event với mức độ nghiêm trọng

- `jdk.ExecutionSample` 1.000 mẫu không phải 1.000 lần thực thi function. Dùng tỷ lệ sample theo stack để tìm hotspot, với cùng sampling settings.
- `jdk.CPULoad` là số liệu CPU định kỳ có field phần trăm; đếm số event không phải %CPU. Khi kết luận, đọc **giá trị** trong event và đối chiếu CPU OS/container.
- `jdk.GarbageCollection` và các `jdk.GCPhasePause` trong cùng GC cycle không được cộng hai lần rồi báo pause time.
- `jdk.ThreadPark`, `SocketRead` có duration của các thread **chồng lên nhau**; tổng duration của 100 threads có thể vượt wall clock thời gian cửa sổ rất nhiều.
- `jdk.VirtualThreadPinned` trên Java 21 phản ánh carrier pinning khi virtual thread chặn; một event ngắn không chứng minh throughput xấu; phải so tần suất, duration và tải.
- `ObjectAllocationSample` dùng sampling, không thay tỷ lệ allocation chính xác từ GC/allocator metrics.

### 10.3. Bỏ qua cấu hình recording và loss

Khi không thấy `SocketRead` hoặc `JavaMonitorEnter`, hỏi theo thứ tự:

1. Trong recording có **event type** tương ứng không (`jfr metadata`, `jfr summary`)?
2. Event có được bật trong `.jfc` hoặc cấu hình tại runtime không? **Threshold** là bao nhiêu?
3. Cửa sổ symptom có nằm hoàn toàn trong recording/retention? Có GC pause hay request kéo từ **trước** cửa sổ vào không?
4. Có sampling interval, overhead hoặc dữ liệu mất/bị cắt do recording buffer/chunk/retention?
5. JVM/instance/clock có đúng với metrics và trace đang so sánh?
6. Có nguồn log/OS metrics khác xác nhận vấn đề nằm ngoài phạm vi JFR không (downstream network, kernel, cgroup, load balancer)?

**Không có event** là kết quả quan sát về tập dữ liệu hiện có, không tự động là kết luận **không có vấn đề**.

## 11. Quy trình làm việc 15 phút đầu tiên của một cuộc điều tra

Đây là một thứ tự thao tác mẫu, không phải SLA cứng:

1. **Bảo toàn symptom**: chụp query/graph link, ghi rõ p95/p99, error/throughput, host/pod, `from/to` UTC và độ phân giải metric.
2. **Xác minh đúng recording**: JDK build, PID/startup time, `.jfr` có phủ khoảng và event settings cần dùng.
3. **Khoanh cửa sổ**: giữ mốc symptom, thêm buffer trước/sau; luôn có khoảng đối chứng tương đương.
4. **Lọc event**: JMC chọn interval; khi recording còn hoạt động dùng `jcmd ... JFR.dump begin/end`; với file có sẵn dùng `WindowJfrReport` hoặc filter API. Giữ bản gốc.
5. **So nhóm có thứ tự**: GC/CPU trước, lock/park và I/O sau, allocation và virtual threads nếu có chỉ dấu. Ghi timestamp, type, duration, stack, thread/peer.
6. **Lập giả thuyết có thể bác bỏ**: ví dụ “p99 tăng do chờ connection pool sau khi downstream chậm”, không viết kết luận chung chung “JVM chậm”.
7. **Đòi bằng chứng độc lập**: trace downstream, timeout/connection pool metrics, host CPU/I/O hoặc change log; so lại cửa sổ đối chứng.
8. **Ghi báo cáo và quyết định**: nêu sự cố, timeline, mức tin cậy, dữ liệu thiếu, phép đo tiếp theo hoặc mitigation. Không chỉnh production chỉ dựa trên một biểu đồ.

**Mẫu báo cáo ngắn:**

```text
Service/JVM:       <service, instance/pod, JDK build, PID/startup>
Symptom UTC:       <from> .. <to>; metric bucket=<resolution>
Analysis UTC:      <from-buffer> .. <to+buffer>
Reference window:  <from> .. <to> (same load/settings)
Recording:         <file, start/end, JFR settings, checksum>
Observations:      <event type, timestamps, duration, stacks/peer>
Hypothesis:        <mechanism, evidence for/against>
Unknowns:          <clock skew, missing event, threshold, lost data>
Next verification: <trace/metric/reproduction and expected result>
Decision:          <owner, action and success metric>
```

Khi dùng phần mềm tự động hóa báo cáo, lưu **timestamp gốc và đơn vị** bên cạnh mọi số liệu; không chỉ lưu screenshot vì chúng khó tái phân tích.

## 12. Bài tập tự kiểm chứng

1. Từ một alert có timezone `+07:00`, đổi ra UTC và thiết lập cửa sổ trước/sau. Kiểm tra bằng `Instant`, không đổi chỉ bằng suy đoán.
2. Tạo `window-lab.jfr`, xem marker `warmup`, `slow`, `recovery` và `ThreadSleep` tương ứng. Chọn 3 cửa sổ, chạy `WindowJfrReport`, giải thích tại sao event kéo dài có thể giao cửa sổ dù bắt đầu trước đó.
3. Trên recording sample hoặc hệ thống thử nghiệm, tạo bảng từ **ít nhất ba nhóm**: GC, CPU và I/O/lock, kèm một khoảng đối chứng. Trình bày điều mà event **không thể chứng minh**.
4. Thay đổi threshold của event I/O trong cấu hình JFR thử nghiệm; so counts và overhead. Giải thích vì sao so kết quả từ hai cấu hình khác nhau phải có ghi chú.
5. Giả sử `jdk.GarbageCollection` và `jdk.GCPhasePause` cùng xuất hiện trong 500 ms. Giải thích vì sao tổng `duration` không phải 1.000 ms downtime.
6. So sánh hai câu: “`SocketRead` dài và p99 tăng cùng lúc” và “socket read gây p99 tăng”. Viết dữ liệu bổ sung cần có để chuyển từ tương quan sang giả thuyết nhân quả chắc hơn.

**Tự kiểm tra khi kết thúc:** đã chuẩn hóa UTC/offset; xác minh đúng JVM/recording/cấu hình; lọc event theo giao cửa sổ; dùng cùng interval so nhóm; biết threshold/sampling/duration overlap; có cửa sổ đối chứng và bằng chứng độc lập; ghi rõ mức tin cậy.

## 13. Nguồn tham khảo Java 21

- [Oracle JDK 21 — `jcmd`: `JFR.start`, `JFR.check`, `JFR.dump begin/end`, retention](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 21 — `jfr`: `summary`, `metadata`, `print`, `view`, các giới hạn bộ lọc](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle JDK 21 — `RecordedEvent` (`getStartTime`, `getEndTime`, `getDuration`)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html)
- [Oracle JDK 21 — `RecordingFile` (`hasMoreEvents`, `readEvent`, `write`)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
- [Oracle JDK 21 — `Recording`, `Configuration`, bật event trong chương trình lab](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [Oracle — Troubleshoot Performance Issues Using Flight Recorder: CPU, I/O, blocking và threshold](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
