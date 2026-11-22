# Thu log, JFR và dữ liệu môi trường trước khi kết luận lỗi Java 15+

## 1. Nguyên tắc: từ triệu chứng tới bằng chứng, không chẩn đoán bằng cảm giác

Trong một ứng dụng Java, cùng biểu hiện “chậm”, “treo”, “tốn RAM”, “không kết nối được” hay “lỗi sau deploy” có thể xuất phát từ nhiều nguyên nhân: thuật toán, khóa đồng bộ, GC, thiếu CPU, DNS/network, filesystem, database, cấu hình, dữ liệu đầu vào, lỗi upstream, giới hạn container hoặc thay đổi của JDK. **Một dòng exception hoặc một biểu đồ CPU riêng lẻ thường không đủ để kết luận nguyên nhân gốc**.

Trước khi thay JVM flags, tăng heap, restart hàng loạt hoặc quy trách nhiệm cho GC, cần có **bộ bằng chứng tối thiểu** gồm:

1. **Log ứng dụng**: thời gian, loại lỗi, stack trace/cause chain, request/trace ID, version, hành động đã thực hiện và dữ liệu ngữ cảnh *an toàn*.
2. **Java Flight Recorder (JFR)** khi cần quan sát hoạt động bên trong JVM: thời gian thực thi, CPU, thread/lock, GC, allocation, I/O và những event phù hợp.
3. **Dữ liệu môi trường**: JDK vendor/build, GC và JVM flags, OS/container/cgroup, CPU và memory limits, service version/commit, cấu hình mạng và áp lực tài nguyên.
4. **Mốc thời gian chung**: chính xác *khi nào* lỗi xuất hiện, khoảng ảnh hưởng, thay đổi triển khai trước đó và mối liên hệ với logs/JFR/metrics.
5. **Giả thuyết có thể bác bỏ**: mỗi kết luận cần nêu *bằng chứng ủng hộ*, *bằng chứng chưa có* và *phép đo sẽ giúp phân biệt với nguyên nhân khác*.

Bài **“Thu log, JFR và dữ liệu môi trường trước khi kết luận”**, thuộc chủ đề cha **“Chẩn đoán lỗi”** của **Java 15**, hướng dẫn quy trình này bằng những công cụ và API chính thức **vẫn còn được hỗ trợ trên JDK hiện đại**.

### Mục tiêu học tập

Sau bài học, bạn có thể:

- Chuẩn bị một **incident evidence bundle** đủ để tái hiện và phân tích vấn đề.
- Ghi log có **correlation ID** và **exception cause chain** mà không làm lộ credentials/PII.
- Phân biệt **application logs, JVM unified logging, JFR events và OS/container metrics**.
- Dùng `jcmd` để kiểm tra JVM đang chạy và điều khiển JFR **khi có quyền phù hợp**.
- Dùng `jfr summary`/`jfr print` hoặc JDK Mission Control để khai thác file `.jfr`.
- Chọn **settings=default** cho quan sát dài hạn và **settings=profile** cho phiên điều tra ngắn, với giới hạn overhead, disk và retention.
- Lưu môi trường theo **allowlist** thay vì xuất vô điều kiện toàn bộ environment variables/system properties.
- Căn chỉnh log/JFR/metrics theo thời gian rồi dựng timeline *bằng chứng → giả thuyết → kiểm chứng*.
- Chạy chương trình Java 15-compatible minh họa tạo **log, JFR custom event và tệp dữ liệu môi trường** rồi đọc lại để QA.
- Phân biệt sự cố GC/heap, native/container memory, thread contention và network bằng **tín hiệu đo được**, không bằng suy đoán.

**Phạm vi:** ví dụ nhắm tới Java 15+ và sử dụng JDK HotSpot/OpenJDK hiện đại. **Java 15 đã hết giai đoạn hỗ trợ thông thường của nhiều nhà cung cấp**; triển khai thực tế nên sử dụng JDK còn được nhà cung cấp bảo trì. Không dùng logging flags đã lỗi thời như `-XX:+PrintGCDetails` làm hướng dẫn mới, không dựa vào `SecurityManager` làm cơ chế bảo vệ hiện đại và không khuyến nghị API `sun.*` nội bộ.

## 2. Bốn lớp dữ liệu chẩn đoán không thể thay thế lẫn nhau

| Lớp | Dữ liệu điển hình | Trả lời tốt câu hỏi nào? | Giới hạn quan trọng |
| --- | --- | --- | --- |
| **Application logs** | Error/warn/info, requestId, route, exception stack/cause, business state | Yêu cầu/hành động nào thất bại và ứng dụng thấy gì? | Có thể thiếu sự kiện vì sampling, cấu hình logger hoặc process chết đột ngột |
| **Unified JVM logs** | GC, safepoint, class loading, JIT/thread events theo tag và mức | JVM thực hiện những sự kiện nội bộ nào? | Cần chọn tag/level phù hợp; nhiều log làm tăng I/O và chi phí |
| **JFR** | Time-stamped JVM/JDK/application events: CPU, GC, allocation, thread/lock, socket, method samples | JVM đã dành thời gian ở đâu và có sự kiện nào đồng thời với triệu chứng? | Event sampling/threshold có thể bỏ qua sự kiện; recording settings/overhead ảnh hưởng dữ liệu |
| **OS/container/infrastructure** | RSS, cgroup limit/throttling, kernel OOM events, disk latency, network errors, upstream metrics | Môi trường có ép tài nguyên/định tuyến khiến ứng dụng lỗi không? | Số liệu host có thể khác container namespace; clock và granularity khác JVM |

**Không thể thay thế log bằng JFR**: JFR có thể cho thấy một thread chờ lock nhưng không biết *yêu cầu kinh doanh nào* đã làm nó chờ nếu ứng dụng không cung cấp correlation metadata.

**Không thể thay thế JFR bằng stack trace của một exception**: stack trace cho thấy đường đi tới nơi lỗi được ném, nhưng không trực tiếp nêu lịch sử CPU contention, GC stalls, allocations hoặc những threads đang chờ.

**Không thể thay OS metrics bằng `-Xmx`**: heap là một phần của bộ nhớ tiến trình; pod có thể bị OOMKilled bởi cgroup ngay khi heap used chưa chạm maximum.

**Không thể thay bằng “monitoring dashboard xanh”**: dashboards có thể dùng khoảng lấy mẫu 1 phút, trong khi một spike 300 ms đủ làm request P99 vượt SLO. Chọn granularity theo lỗi cần khảo sát.

## 3. Thu thập sớm, nhưng bảo vệ dữ liệu ngay từ đầu

### 3.1. Khi sự cố xảy ra: ghi lại *phạm vi và mốc thời gian*

Bằng chứng dễ mất khi container restart, log rotate, ring buffer bị ghi đè hoặc process bị kill. Hãy tạo một phiếu sự cố với những trường tối thiểu:

| Trường | Ví dụ minh họa | Vì sao quan trọng |
| --- | --- | --- |
| Incident ID | `INC-2026-042` | Liên kết các artifact và trao đổi |
| Thời điểm bắt đầu/kết thúc | ISO-8601 UTC, có offset/cách xác nhận | Xác định đúng cửa sổ logs/JFR/metrics |
| Môi trường | production, region, namespace, pod/service | Tránh đọc nhầm logs của môi trường khác |
| Ứng dụng/build | image digest, commit, release ID | Phân biệt regression sau deploy |
| Số phiên bản runtime | Java vendor, JDK version/build, GC | Cùng code có thể chạy khác trên JDK khác |
| Triệu chứng quan sát | Timeout, HTTP 5xx, `OutOfMemoryError`, process exit | Nêu sự kiện thực chứ không đoán nguyên nhân |
| SLO/tác động | Số request, khách hàng, độ trễ P99, tỷ lệ lỗi | Quyết định mức ưu tiên và thời gian thu dữ liệu |
| Thay đổi gần nhất | deploy, feature flag, DB migration, autoscaling | Tạo giả thuyết cần kiểm chứng |
| Nguồn bằng chứng | log query, `.jfr`, metrics, thread dump, OOM event | Có thể tái kiểm tra kết luận |
| Hành động đã làm | restart, scale, rollback, đổi config, lấy dump | Tránh nhầm dữ liệu *trước* và *sau* can thiệp |

Các giá trị trên là **định dạng minh họa**, không phải dữ liệu thực của người học.

### 3.2. Mốc thời gian phải nhất quán

- Log ứng dụng nên có timestamp **ISO-8601 cùng timezone/offset**, ưu tiên UTC khi tổng hợp từ nhiều máy.
- JFR events có timestamp của JVM, có thể đối chiếu với wall-clock timestamps; các command/log formats tùy JDK có các trường thời gian khác nhau.
- Metrics OS/container thường được scraper lấy theo từng khoảng; biết **sampling interval** và **scrape delay**.
- Trong code, dùng `System.nanoTime()` để đo **elapsed durations**, không xem giá trị `nanoTime` như Unix timestamp hay đem so trực tiếp giữa hai process.
- Đồng bộ clock trong hạ tầng (NTP hoặc cơ chế tương đương) và ghi nhận clock skew nếu các hệ thống khác nhau.
- Giữ lại cả **start/end window** và **time of mitigation**; một JFR sau restart không phản ánh heap/thread state của process đã chết.

Sơ đồ timeline:

```text
10:00:00Z  Deploy build A
10:01:10Z  Error rate bắt đầu tăng
10:01:15Z  Request traceId=... timeout
10:01:15Z  JFR: một nhóm threads blocked / socket wait / GC event
10:01:15Z  Cgroup CPU throttling tăng
10:02:00Z  Thu thập JFR + VM flags + thread snapshot
10:03:00Z  Rollback build A (sự kiện can thiệp)
10:04:00Z  Error rate hồi phục
```

Đây chỉ là **timeline ví dụ**. Đồng thời xảy ra **không tự chứng minh quan hệ nhân quả**; nếu CPU throttle và latency cùng tăng, còn phải xem nguồn throttle, lượng request và các bottlenecks khác.

### 3.3. Bảo vệ và giới hạn ngay khi thu thập

Logs, JFR, thread/heap dumps và bản ghi command line có thể chứa **đường dẫn nội bộ, user identifiers, URL, header, SQL, token, thông số JVM hoặc dữ liệu của người dùng**.

Quy tắc:

1. Dùng **allowlist các trường cần thiết**, hạn chế việc log request/response body hoặc toàn bộ objects.
2. **Redact hoặc không thu từ đầu** credentials, private keys, session cookies, Authorization headers, bearer tokens, passwords, PII.
3. Giới hạn quyền đọc/ghi của thư mục diagnostic; mã hóa khi lưu và khi truyền, đặt retention/xóa theo chính sách.
4. Không dán nguyên `VM.system_properties`, `VM.command_line`, `printenv` hoặc heap dump lên ticket/chat công khai. Các nguồn đó có thể chứa secrets trong arguments/environment.
5. Hạn chế lượng log/JFR, đặc biệt nếu chạy continuous recording; chọn `maxage`/`maxsize`, log rotation và quota.
6. Không để diagnostic tools chạm đúng thời điểm peak rồi gây outage thứ hai; chọn thao tác nhẹ trước, thao tác nặng theo đánh giá tác động.
7. Đánh dấu mỗi artifact **thu trước hay sau mitigation/restart**, tránh ghép bằng chứng không cùng trạng thái.

**Redaction trong log không bảo đảm mọi bản sao trong JFR/heap dump đã an toàn.** Phải đánh giá độc lập từng artifact.

## 4. Application logging: ghi đủ ngữ cảnh mà không tiết lộ dữ liệu

### 4.1. Cần những trường gì?

Một log event có ích cho phân tích nên có:

| Trường | Ví dụ | Ghi chú |
| --- | --- | --- |
| `timestamp` | `2026-11-08T02:00:00Z` | Có timezone/offset |
| `level` | `ERROR` / `WARN` / `INFO` | Phân biệt failure và hành vi vận hành |
| `service` | `orders-api` | Tên service được quản lý |
| `instance` | `pod-...` hoặc instance ID | Phân biệt replicas |
| `release` | build/commit hash | Đối chiếu thay đổi code |
| `requestId` / `traceId` | `req-...` | Kết nối sự kiện theo cùng request/trace |
| `operation` / `stage` | `validate`, `db-query` | Nói lỗi xảy ra ở pha nào |
| `errorType` | `java.net.SocketTimeoutException` | Loại exception, không chỉ message |
| `message` | Mô tả hành vi | Không chứa credentials/PII |
| `elapsedMs` | Thời gian đo bằng monotonic clock | Không nhầm với timestamp |
| `retryAttempt` | Số lần thử nếu có | Giúp biết timeout do retry chain |
| `downstream` | Tên service/DB logical | Không nhất thiết ghi URL chứa secret |

Trong sản phẩm có nhiều service, định dạng **JSON lines với schema nhất quán** thường dễ query. Với bản demo chỉ dùng Java SE, `java.util.logging` + message key-value được dùng để không cần thư viện ngoài; **đó không phải JSON structured logger hoàn chỉnh**. Framework logging như SLF4J/Logback, Log4j 2 hoặc OpenTelemetry instrumentation có thể được dùng theo chính sách hệ thống. Quan trọng là **schema, bảo mật và correlation**, không phải bắt buộc một framework duy nhất.

### 4.2. Vì sao requestId, traceId và exception cause chain quan trọng?

- `requestId` liên kết các dòng trong một service cho một request.
- `traceId`/`spanId` liên kết qua service boundaries khi hệ thống tracing đã được cấu hình; trong distributed tracing có thể dùng **W3C Trace Context**.
- **Stack trace** nêu vị trí throw và call stack lúc lỗi; **cause chain** giúp phân biệt lỗi bao bọc ở tầng API với nguyên nhân sâu hơn.
- `errorType`/mã lỗi có cấu trúc giúp tính frequency; chỉ lọc theo text `"timeout"` dễ nhầm các nguyên nhân khác nhau.
- Correlation ID do client gửi phải **được validate độ dài/định dạng** trước khi log; không cho nhập ký tự xuống dòng/control tạo log injection.
- Các trường trace/request không phải **bằng chứng đã xác thực caller**. Client có thể tự chọn ID; quyền và identity phải được xác thực bằng cơ chế riêng.

Một dòng log chỉ có `"Something went wrong"` mà không có operation, version, timestamp, exception class hoặc correlation ID thường không đủ để tái hiện.

### 4.3. Ghi cả stack trace, không chỉ `getMessage()`

Ví dụ minh họa dùng `java.util.logging`:

```java
try {
    processRequest();
} catch (IllegalStateException ex) {
    logger.log(Level.WARNING,
            "requestId=lab-001 stage=validate outcome=failed", ex);
}
```

Đây là **mảnh mã**, giả định `processRequest()`, `logger` và imports đã có; không phải chương trình độc lập. Truyền đối tượng `Throwable` giúp logging formatter lưu stack trace và *caused by*, thay vì chỉ ghi `ex.getMessage()` rồi mất cấu trúc lỗi.

Tuy nhiên, **stack trace/cause message có thể chứa dữ liệu nhạy cảm**, nhất là khi thư viện đưa input/SQL/URL vào exception text. Dùng policy phân loại/redaction và tránh log lặp ở nhiều tầng cho cùng một exception. Một lỗi nên được ghi đủ ngữ cảnh tại **điểm có trách nhiệm xử lý/báo lỗi**, không phải mọi hàm bắt rồi log thêm.

### 4.4. Log levels, sampling và overflow

- **ERROR:** thất bại ảnh hưởng request/operation hoặc cần can thiệp; không biến mọi retry đã được xử lý thành ERROR.
- **WARN:** dấu hiệu suy giảm, fallback, timeout/điều kiện không bình thường nhưng hệ thống có thể tiếp tục.
- **INFO:** lifecycle, deploy, thay đổi config được cho phép, start/stop, marker của incident.
- **DEBUG/TRACE:** dùng có kiểm soát, tránh bật toàn bộ request bodies hoặc hot-path logs gây CPU/I/O pressure.

Những vấn đề cần quan sát:

- Async logging queue có thể **drop events** khi quá tải; log thiếu không chứng minh sự kiện chưa xảy ra.
- Sampling có thể bỏ đúng request hiếm gây lỗi; dùng chính sách ưu tiên error traces khi cần, trong giới hạn privacy.
- Log rotation/retention quá ngắn có thể xóa dữ liệu trước khi xử lý incident.
- Logging quá nhiều làm tăng disk, CPU, network egress và có thể khiến **vấn đề nặng hơn**.
- Nếu cần tương quan chính xác, ghi **deployment/build instance** trong logs hoặc resource attributes, không chỉ request ID.
- Cần đồng bộ log timestamps, metrics timestamps và JFR event times; không suy đoán thứ tự do log ingestion delay.

## 5. Java Flight Recorder (JFR): bộ bằng chứng ở cấp JVM

**JFR** là hệ thống ghi các **events có timestamp** từ JVM, JDK và ứng dụng. Nó có module/API chính thức `jdk.jfr` và công cụ `jfr`/`jcmd` trong JDK. Các events có thể liên quan đến **GC, CPU, class loading, compilation, thread scheduling, lock contention, socket/file I/O, heap/allocation, exceptions** — nhưng **chỉ những event types đã được enable và đáp ứng threshold/sampling** mới xuất hiện.

JFR rất hữu ích khi log ứng dụng nói “request timeout” nhưng không nói thread thực sự đang **chờ socket, chờ lock, dùng CPU hay bị GC/OS stall**.

### 5.1. `default` và `profile` không phải “low overhead vs zero overhead”

Hai template chuẩn thường gặp:

| Template | Mục đích | Cách dùng phù hợp |
| --- | --- | --- |
| `settings=default` | Bộ event tương đối tiết kiệm, phù hợp recording dài hạn/liên tục theo hướng dẫn JDK | Giữ một rolling window, dump khi có sự cố |
| `settings=profile` | Thu thêm dữ liệu phục vụ profiling, thường chi tiết hơn | Điều tra ngắn có kiểm soát, cân nhắc overhead và storage |

**Không khẳng định JFR luôn có overhead bằng 0.** Tác động phụ thuộc sự kiện được bật, threshold, stack traces, sampling period, dữ liệu của ứng dụng và storage. Đặc biệt, bật các event rất chi tiết hoặc thu stack traces dày đặc có thể thay đổi hiệu năng đúng lúc đang điều tra.

Các event names/field layouts/default settings có thể đổi theo JDK version. Hãy dùng `jfr summary`, `jfr metadata` hoặc JDK Mission Control để **kiểm tra file thật có event nào**, thay vì giả định template đã ghi mọi event cần thiết.

### 5.2. Bật JFR khi khởi động

Ví dụ ghi một recording profiling **có thời lượng cố định**, phù hợp một ứng dụng chạy đủ lâu:

```bash
java -XX:StartFlightRecording=name=incident,settings=profile,duration=2m,filename=incident.jfr -jar service.jar
```

`service.jar` là tên tệp ứng dụng giả định, lệnh không chạy độc lập nếu tệp không tồn tại. Với process kết thúc trước 2 phút, cách ghi/tệp output có thể khác điều mong đợi: chọn duration theo lifetime thật và công cụ để dump trước khi process dừng.

Ví dụ cấu hình **rolling recording** khi startup:

```bash
java -XX:StartFlightRecording=name=baseline,settings=default,disk=true,maxage=30m,maxsize=256m,dumponexit=true -jar service.jar
```

- `maxage=30m` giữ một khoảng thời gian theo cấu hình rolling retention.
- `maxsize=256m` giới hạn lượng dữ liệu recording được lưu theo chính sách của JFR; không phải quota tất cả logs/JVM diagnostics.
- `dumponexit=true` yêu cầu dump lúc JVM kết thúc bình thường theo cơ chế hỗ trợ; **không thể trông chờ sẽ kịp dump nếu OS kill -9 hoặc cgroup OOMKill**.
- `settings=default` là lựa chọn tương đối nhẹ cho quan sát baseline; phải đo overhead và disk budget trong workload thực.

Trong môi trường container, bảo đảm nơi ghi và các quyền truy cập cần thiết, giới hạn file size và không để recording chứa secrets tự động upload ra nơi không tin cậy.

### 5.3. Bật JFR trên một JVM đang chạy bằng `jcmd`

Khi có quyền attach vào đúng process (trong cùng host/namespace và môi trường hỗ trợ), trước hết xác định PID. Ví dụ PID **12345** dưới đây chỉ là số minh họa; **không** copy nguyên số đó mà phải chọn PID đã xác minh là service đích.

```bash
jcmd -l
jcmd 12345 help JFR.start
jcmd 12345 JFR.start name=incident settings=profile duration=2m filename=incident.jfr
jcmd 12345 JFR.check
```

Những bước trên thường dùng được với HotSpot/JDK phù hợp, nhưng `jcmd -l` có thể **không liệt kê các process trong một Docker PID namespace khác**. Nếu command attach bị từ chối, kiểm tra user/process ownership, namespace/container và policy của OS; không dùng quyền root bừa bãi hoặc tắt security controls để chạy bằng mọi giá.

Nếu muốn lấy snapshot trong lúc recording **vẫn đang chạy**:

```bash
jcmd 12345 JFR.dump name=incident filename=incident-snapshot.jfr
```

Theo JDK hiện đại, `JFR.dump` ghi ra một file và **recording có thể tiếp tục chạy**. Khi chấm dứt recording được đặt tên (nếu nó chưa tự kết thúc theo `duration`):

```bash
jcmd 12345 JFR.stop name=incident
```

Tùy vào lệnh khởi tạo, tên recording và phiên bản JDK, `JFR.stop`/dump behavior hoặc file cần kiểm tra theo `jcmd 12345 help JFR.stop`. **Không gọi stop một recording production không thuộc phạm vi điều tra**. Kết thúc đúng thời điểm và giữ file đã dump theo quy trình.

### 5.4. Kiểm tra file `.jfr`

Các lệnh JDK hiện hành:

```bash
jfr summary incident-snapshot.jfr
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause incident-snapshot.jfr
jfr metadata incident-snapshot.jfr
```

- `jfr summary` cho biết **loại event, số lượng và kích thước dữ liệu**, rất hữu ích để biết recording có ghi đúng dữ liệu hay không.
- `jfr print --events ...` lọc events theo tên; các sự kiện GC/pause có thể khác theo collector và version. Nếu không thấy `jdk.GCPhasePause`, không kết luận “không có GC pause”: trước hết kiểm tra template, threshold, recording duration và event names.
- `jfr metadata` giúp đọc cấu trúc loại event trong bản ghi.
- JDK Mission Control (JMC) cho phép phân tích tương tác: timeline, GC/CPU/memory, lock contention, method samples và event browser, tùy những events có sẵn.

**Phân biệt:** `jfr summary` có thể thống kê số events, nhưng không có nghĩa file ghi **mọi occurrence**. Event bị disable, dưới threshold hoặc không được sample sẽ không xuất hiện.

### 5.5. JFR custom events: nối ứng dụng với JVM

Khi ứng dụng định nghĩa `@Name("demo.DiagnosticCheckpoint")` cho một class kế thừa `jdk.jfr.Event`, bạn có thể ghi các trường đã được thiết kế như:

- `requestId` (đã validate, không nhạy cảm).
- `stage`/`operation`.
- `outcome`/error category.
- Các số đo độ dài/thời gian cần thiết theo kiểu JFR hỗ trợ.

Ưu điểm: khi phân tích `.jfr` có thể đối chiếu một checkpoint ứng dụng với events JVM trên cùng timeline.

Nhưng **không nhét raw request body, auth tokens hoặc private customer data vào custom JFR fields**. Những trường Java kiểu `String` của custom event được ghi như dữ liệu quan sát, không được mã hóa tự động như secret. Event names và schema phải có versioning nếu ứng dụng cần phân tích dài hạn.

## 6. `jcmd`: đọc trạng thái JVM đúng process, đúng mức tác động

`jcmd` gửi diagnostic commands đến một JVM hỗ trợ cơ chế attach. Các commands hiện có phụ thuộc JDK/vendor/build; **luôn xác nhận bằng `jcmd 12345 help` hoặc `help <command>`** trước khi chạy tác vụ quan trọng.

| Lệnh minh họa | Dữ liệu thu được | Cảnh báo |
| --- | --- | --- |
| `jcmd 12345 VM.version` | Full HotSpot/JDK build | Đọc đúng JVM process, không chỉ `java -version` của shell |
| `jcmd 12345 VM.uptime` | Thời gian JVM đã chạy | Giúp biết startup/restart gần incident |
| `jcmd 12345 VM.flags` | Các JVM flags đang có hiệu lực | Một số giá trị có thể cần bảo mật |
| `jcmd 12345 VM.info` | Thông tin tổng quát về VM và môi trường | Khối lượng dữ liệu phụ thuộc runtime |
| `jcmd 12345 GC.heap_info` | Tổng quan trạng thái heap/GC | Snapshot hiện tại, không phải heap history hoặc live set chính xác |
| `jcmd 12345 Thread.print -l` | Stack traces và lock information của threads | Có thể tốn thời gian với rất nhiều threads; dữ liệu có thể nhạy cảm |
| `jcmd 12345 VM.native_memory summary` | Phân loại native memory do JVM theo dõi | Cần bật NMT trước; không bao quát mọi native allocation |
| `jcmd 12345 JFR.check` | Recording nào đang chạy | Không tự cung cấp toàn bộ dữ liệu events |

**Lưu ý về quy trình:** thu các lệnh đọc ít tác động trước. Khi sự cố thuộc loại deadlock/thread starvation, một thread snapshot có thể hữu ích. Với memory leak, histogram/heap dump có thể cần nhưng tạo overhead, stop-the-world/GC hoặc file rất lớn; **không** xem heap dump là bước mặc định cho mọi lỗi.

### 6.1. JVM đang chạy mới là nguồn sự thật của flags

Lệnh `java -version` trong terminal có thể chỉ đúng JVM **của shell**, không phải JVM đã khởi chạy service. Đối với một process Java cụ thể, đối chiếu:

- PID/JVM build từ `jcmd PID VM.version`.
- JVM flags đang sử dụng từ `VM.flags`.
- Command line/process metadata **sau khi kiểm tra secrets**, nếu thực sự cần.
- Container image ID/tag/digest và launcher config của service.
- GC mode/heap Xms/Xmx/soft max thực tế, không chỉ các giá trị mà bạn nghĩ deployment đã áp dụng.

Ví dụ một service chạy trên JDK 24 có ZGC generational mặc định cho `-XX:+UseZGC`, khác JDK 15 ZGC; không thể suy rằng một thay đổi latency chắc chắn do app code nếu JVM mode cũng thay đổi. **Từ JDK 24, non-generational ZGC đã bị loại bỏ**: không hướng dẫn người học thêm `ZGenerational` đã lỗi thời.

### 6.2. `VM.system_properties` và `VM.command_line` có rủi ro

Hai lệnh này có thể hiển thị thông tin giúp debug nhưng cũng **có thể lộ passwords, API keys hoặc các thông tin nội bộ** nếu ứng dụng đã đưa secrets vào `-D...` hoặc command arguments.

```bash
jcmd 12345 VM.system_properties
jcmd 12345 VM.command_line
```

Đó là **ví dụ về nguồn dữ liệu nhạy cảm phải kiểm soát**, không phải hai lệnh luôn phải chạy/tải lên. Tốt hơn:

- Thu bằng truy cập được ủy quyền, qua kênh/thiết bị có kiểm soát.
- Redact tại nguồn hoặc qua quy trình kiểm duyệt trước khi chia sẻ.
- Dùng **allowlist** các thuộc tính thực sự liên quan nếu cần một summary công khai nội bộ.
- Không vô tình lưu đầy đủ token trong ticket, CI log hoặc nơi lưu chẩn đoán không có ACL.

### 6.3. Native Memory Tracking không phải “memory monitor tổng quát”

HotSpot có thể bật NMT từ khi JVM khởi động:

```bash
java -XX:NativeMemoryTracking=summary -jar service.jar
```

Sau đó quan sát:

```bash
jcmd 12345 VM.native_memory summary
```

Cấu hình này chỉ hữu ích nếu JVM được khởi động với NMT, và NMT có **overhead**. NMT theo dõi các hạng mục memory do JVM quản lý theo phạm vi của HotSpot; **không đo hết native allocations của mọi thư viện bên ngoài**. Phải kết hợp process RSS/cgroup memory/các công cụ OS thích hợp.

**Đừng cộng reserved virtual address space rồi gọi đó là RSS**. Một số collector, nhất là ZGC, có thể reserve không gian địa chỉ ảo lớn hơn memory thực tế đã commit/được OS tính.

### 6.4. Heap dump, thread dump, crash file: mức rủi ro khác nhau

- **Thread dump:** có thể tốn thời gian khi rất nhiều threads; nhìn được stack và locks nhưng chỉ là một snapshot, không phải hồ sơ đầy đủ của mọi request.
- **Heap dump:** có thể tốn nhiều dung lượng và gây tác động đáng kể; có thể chứa passwords, tokens, dữ liệu khách hàng, cached payloads. Không thu nếu chưa có lý do và phương án bảo vệ.
- **Fatal error log `hs_err_pid*.log`:** thường chứa build, thread, native stack và môi trường khi JVM crash; nên bảo vệ như artifact nhạy cảm.
- **OS core dump:** có thể chứa gần như toàn bộ process memory; chỉ tạo khi có nhu cầu và quyền phù hợp.
- **JFR:** overhead thường quản lý được nhưng không phải bằng 0, chứa thông tin vận hành và có thể cả giá trị do custom events ghi.
- **Application logs:** có thể tạo rủi ro privacy lớn nếu log payload/raw headers.

Ưu tiên **artifact có giá trị chẩn đoán cao nhất với tác động nhỏ nhất**, thay vì thu mọi thứ ngay lần đầu.

## 7. Snapshot môi trường tối thiểu nhưng hữu ích

### 7.1. JVM + application

Nên ghi những thông tin được quản lý:

- JVM vendor, version, build và architecture.
- GC collector/mode, flags chính (`-Xms`, `-Xmx`, container awareness, GC logging).
- Service name, build hash, git commit/image digest, feature flags **không nhạy cảm**.
- Startup time/uptime, PID trong namespace, replica/instance ID.
- Classpath/module path *nếu cần* nhưng phải kiểm duyệt để không đưa secrets/đường dẫn nhạy cảm vào ticket.
- Số threads, heap used/committed/max, request concurrency, allocation rate; nêu **timestamp** cho từng measurement.
- Có agent/instrumentation nào đang chạy, chúng có thể tạo overhead hoặc thay đổi stack/JFR events.

### 7.2. OS và container

- OS/kernel version, architecture và CPU model khi liên quan.
- Số CPU JVM thấy (ví dụ `Runtime.availableProcessors()`) **không đủ** để mô tả CPU quota/CPUs thực tế trong mọi container; phải đối chiếu CPU limit/throttling.
- Container memory limit, current/peak usage, OOM kill counters/events.
- Process RSS/working set, page faults, swap pressure.
- Disk free space/latency, file descriptors, connection limits.
- Network: DNS results, retries/timeouts, interface/route/MTU, upstream status, packet loss — khi triệu chứng liên quan.
- NTP/clock synchronization và timezone để ghép timeline.
- Thời điểm deployment, node migration, autoscaling, liveness/readiness probes, restart counts.

Các tên cgroup files và commands OS **khác nhau giữa cgroup v1/v2, Windows và môi trường container**; không hard-code một file path như “cách đo portable duy nhất”. Dùng observability của runtime/orchestrator và công cụ OS phù hợp.

### 7.3. Chọn thông tin nào theo triệu chứng?

| Triệu chứng | Evidence nên ưu tiên | Điều phải đối chiếu thêm |
| --- | --- | --- |
| **Request P99 tăng** | Traces, app logs, JFR CPU/thread/I/O events, GC/safepoint logs | CPU throttling, request rate, DB/upstream latency, queue |
| **`OutOfMemoryError: Java heap space`** | JVM heap flags, GC logs, occupancy trends, JFR allocation, heap dump có kiểm soát | Live set/cache retention, memory leak, load shape |
| **Container OOMKilled** | Cgroup events, RSS, memory limit, native/direct memory, `-Xmx` | Kernel/container logs; Java có thể không có OOME |
| **Deadlock hoặc thread hang** | Multiple thread dumps, JFR monitor/thread park, request logs | Lock ordering, blocked vs waiting vs I/O |
| **Socket timeout** | Request/trace logs, JFR socket events, connection pool metrics | DNS, network policy, server upstream, queueing |
| **CPU cao** | Process CPU, JFR execution samples, JIT/GC CPU, OS scheduler | User code hot path, GC pressure, background agents |
| **Lỗi sau deploy** | Build/version, release flags, schema/config changes, error class stack trace | So sánh trước–sau với cùng workload |
| **GC pause bị nghi dài** | GC `-Xlog`, JFR GCPhasePause/GC events, application latency | Phân biệt pause vs concurrent cycle vs scheduling |
| **File I/O chậm** | JFR file read/write events, disk metrics, thread states | Disk throughput, storage limits, antivirus/network mounts |
| **Khác nhau theo máy** | JDK/build, OS/kernel, cgroup, CPU arch, enabled modules | Container image, system properties được cho phép, timezone |

Đây là **bảng ưu tiên thu thập**, không phải quy tắc “chỉ cần nhìn một event là có kết luận”. Cần xác minh đặc tính của workload và hệ thống thực tế.

## 8. Ví dụ chạy được: tạo log, JFR và môi trường bằng Java 15

Chương trình dưới đây sử dụng **thư viện của JDK**, không cần thêm dependency:

1. Ghi một số trường môi trường **được chọn trước** vào `environment-demo.txt`.
2. Tạo `java.util.logging.FileHandler` và ghi một tình huống lỗi minh họa với `requestId`, `stage` và **cause chain**.
3. Bật một `jdk.jfr.Recording` cấu hình `default`, enable **custom JFR event** `demo.DiagnosticCheckpoint`.
4. Ghi checkpoint đồng thời với log ứng dụng, rồi dừng và dump JFR ra `incident-demo.jfr`.
5. Đọc lại file JFR ngắn bằng `RecordingFile.readAllEvents(...)` và xác minh event đã được ghi.
6. In ra **những điều kiện boolean ổn định**, không hard-code file size/timestamp/stack line numbers phụ thuộc máy.

**Mục đích:** tạo một *bộ bằng chứng nhỏ có thể tái kiểm chứng*. Không phải thiết kế logging framework production hoàn chỉnh; trong dịch vụ thật thường cần JSON logger, trace propagation, rotation, security/retention, lifecycle của JFR và metadata hạ tầng.

### 8.1. File `DiagnosticEvidenceDemo.java`

Tạo file đúng tên:

```java
import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.logging.FileHandler;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.logging.SimpleFormatter;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.Configuration;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class DiagnosticEvidenceDemo {
    @Name("demo.DiagnosticCheckpoint")
    @Label("Diagnostic checkpoint")
    public static final class DiagnosticCheckpoint extends Event {
        @Label("Request ID") public String requestId;
        @Label("Stage") public String stage;
        @Label("Outcome") public String outcome;
    }

    private static void writeAllowlistedEnvironment(Path path)
            throws IOException {
        String summary = "capturedAtUtc=" + Instant.now() + "\n"
                + "javaVersion=" + System.getProperty("java.version") + "\n"
                + "javaVendor=" + System.getProperty("java.vendor") + "\n"
                + "vmName=" + System.getProperty("java.vm.name") + "\n"
                + "osName=" + System.getProperty("os.name") + "\n"
                + "osArch=" + System.getProperty("os.arch") + "\n"
                + "availableProcessors="
                + Runtime.getRuntime().availableProcessors() + "\n"
                + "maxHeapBytes=" + Runtime.getRuntime().maxMemory() + "\n"
                + "gcBeans="
                + ManagementFactory.getGarbageCollectorMXBeans().size() + "\n";
        Files.writeString(path, summary, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        Path log = Path.of("incident-demo.log");
        Path recordingFile = Path.of("incident-demo.jfr");
        Path environment = Path.of("environment-demo.txt");

        Logger logger = Logger.getLogger("demo.DiagnosticEvidenceDemo");
        logger.setUseParentHandlers(false);
        FileHandler fileHandler = new FileHandler(log.toString(), false);
        fileHandler.setFormatter(new SimpleFormatter());
        logger.addHandler(fileHandler);

        try {
            writeAllowlistedEnvironment(environment);
            try (Recording recording = new Recording(
                    Configuration.getConfiguration("default"))) {
                recording.setName("incident-demo");
                recording.enable(DiagnosticCheckpoint.class)
                        .withThreshold(Duration.ZERO);
                recording.start();

                logger.info(
                    "requestId=lab-001 stage=validate outcome=started");

                DiagnosticCheckpoint checkpoint =
                        new DiagnosticCheckpoint();
                checkpoint.requestId = "lab-001";
                checkpoint.stage = "validate";

                try {
                    throw new IllegalStateException(
                            "demo validation failed",
                            new IllegalArgumentException("bad demo input"));
                } catch (IllegalStateException exception) {
                    checkpoint.outcome = "failed";
                    logger.log(Level.WARNING,
                            "requestId=lab-001 "
                            + "stage=validate outcome=failed",
                            exception);
                } finally {
                    checkpoint.commit();
                }
                recording.stop();
                recording.dump(recordingFile);
            }
        } finally {
            logger.removeHandler(fileHandler);
            fileHandler.close();
        }

        long checkpoints = 0;
        for (RecordedEvent event :
                RecordingFile.readAllEvents(recordingFile)) {
            if (event.getEventType().getName()
                    .equals("demo.DiagnosticCheckpoint")) {
                checkpoints++;
            }
        }

        String savedLog =
                Files.readString(log, StandardCharsets.UTF_8);
        String savedEnvironment =
                Files.readString(environment, StandardCharsets.UTF_8);

        System.out.println("logNonEmpty=" + (Files.size(log) > 0));
        System.out.println("requestIdLogged="
                + savedLog.contains("requestId=lab-001"));
        System.out.println("exceptionChainLogged="
                + savedLog.contains(
                    "Caused by: java.lang.IllegalArgumentException"));
        System.out.println("jfrNonEmpty="
                + (Files.size(recordingFile) > 0));
        System.out.println("customCheckpointRecorded="
                + (checkpoints == 1));
        System.out.println("environmentAllowlistWritten="
                + (savedEnvironment.contains("javaVersion=")
                    && savedEnvironment.contains("maxHeapBytes=")));
    }
}
```

### 8.2. Biên dịch và chạy

Dùng JDK hỗ trợ `jdk.jfr` và target Java 15 (ví dụ JDK 17/21/25 từ nhà cung cấp phù hợp):

```bash
javac --release 15 -encoding UTF-8 DiagnosticEvidenceDemo.java
java DiagnosticEvidenceDemo
```

**Stdout chính xác khi chạy thành công với JFR được hỗ trợ:**

```text
logNonEmpty=true
requestIdLogged=true
exceptionChainLogged=true
jfrNonEmpty=true
customCheckpointRecorded=true
environmentAllowlistWritten=true
```

Chương trình này đã được **biên dịch với `javac --release 15` và chạy thành công trên OpenJDK 21**; cả sáu dòng boolean đều đúng. Lệnh `jfr summary incident-demo.jfr` cũng xác nhận có đúng **một event `demo.DiagnosticCheckpoint`** trong recording thử nghiệm.

File `incident-demo.log` chứa timestamp và stack/cause chain; file `environment-demo.txt` chứa các thuộc tính được allowlist. **Giá trị cụ thể** như timestamp, JDK version, CPU count, heap maximum, file sizes và dòng stack có thể khác trên máy khác; vì vậy ví dụ không hard-code chúng thành stdout.

Để kiểm tra bản ghi sau khi chạy:

```bash
jfr summary incident-demo.jfr
jfr print --events demo.DiagnosticCheckpoint incident-demo.jfr
```

Nếu dùng PowerShell, các lệnh `javac`, `java` và `jfr` trên cũng có thể chạy trực tiếp khi JDK `bin` có trong `PATH`, tại thư mục bạn có quyền ghi.

### 8.3. Vì sao không dump toàn bộ biến môi trường?

Method `writeAllowlistedEnvironment(...)` cố ý chỉ lấy:

- Timestamp UTC theo `Instant.now()`.
- Java runtime version/vendor/VM name.
- OS name/architecture.
- CPU count mà JVM thấy.
- Maximum heap do `Runtime.maxMemory()` báo.
- Số `GarbageCollectorMXBean` hiện diện.

Nó **không** gọi `System.getenv()` hoặc `System.getProperties()` rồi dump tất cả. Hai API này hợp lệ nhưng **dữ liệu trả về có thể chứa thông tin nhạy cảm** (đặc biệt variables chứa tokens, secrets, endpoint credentials). Khi cần mở rộng summary, thêm từng trường vào **allowlist đã review**; không đẩy raw env vào artifact gửi bên thứ ba.

### 8.4. Vì sao dùng `FileHandler` và `logger.log(..., exception)`?

- `FileHandler(log.toString(), false)` tạo log file mới trong thư mục lab.
- `logger.setUseParentHandlers(false)` tránh nhân đôi output tới console trong demo; production cần chiến lược logger hierarchy, rotation và centralized collection phù hợp.
- `SimpleFormatter` ghi log người đọc hiểu được; message có `requestId` và `stage` để minh họa correlation. **Nó chưa thay thế structured JSON logging production**.
- `logger.log(Level.WARNING, ..., exception)` giữ lại exception class, stack và `Caused by`.
- Chương trình chỉ dùng exception **giả lập không chứa secrets**. Trong ứng dụng thật, cần xem liệu exception message/stack có chứa dữ liệu nhạy cảm không.
- `FileHandler.close()` trong `finally` giúp flush/đóng tài nguyên sau khi recording kết thúc.
- Không in nguyên log ra console để tránh phụ thuộc timestamp/locale/stack line numbers.

### 8.5. Vì sao `Recording` được cấu hình trước `start()`?

Theo Javadoc, cấu hình setting và event types **trước khi start** giúp recording nhất quán và tránh thay đổi thiết lập giữa chừng.

- `Configuration.getConfiguration("default")` dùng template tiêu chuẩn cho recording nền.
- `recording.enable(DiagnosticCheckpoint.class).withThreshold(Duration.ZERO)` cho phép ghi custom event dù thời lượng rất ngắn.
- `checkpoint.commit()` ghi event với `requestId`, `stage` và `outcome`. Các trường đó tạo điểm nối với log ứng dụng.
- `recording.stop()` rồi `recording.dump(...)` tạo `.jfr` có thể phân tích.
- `try-with-resources` đóng recording và giải phóng tài nguyên JFR.
- `RecordingFile.readAllEvents(...)` tiện cho **file demo nhỏ**, **không nên đọc mọi event của một file production nhiều GiB vào memory**. Với bản ghi lớn, dùng `RecordingFile` theo luồng, `jfr`/JMC hoặc pipeline phân tích có giới hạn.

**Nếu runtime không có JFR** hoặc không được phép tạo recording/repository/file, chương trình có thể ném exception. Đó là điều kiện môi trường cần báo rõ, không tự coi như một lần ghi thành công.

### 8.6. Những điều demo cố tình không khẳng định

- Một custom checkpoint được ghi **không có nghĩa** toàn bộ request trace đã được tự động đưa vào JFR.
- File log có `requestId` **không có nghĩa** request là của đúng người đã xác thực.
- Recording file tồn tại **không có nghĩa** mọi GC/I/O events đều được ghi; phải xem enable/threshold/template.
- Environment summary có `maxHeapBytes` **không có nghĩa** process RSS bằng Java heap maximum.
- Exception demo **không chứng minh** ứng dụng thật đã lỗi ở cùng stack.
- Ghi ba tệp thành công **không phải** là chẩn đoán nguyên nhân gốc. Nó chỉ xác nhận **thu thập dữ liệu** hoạt động.

## 9. Ghi và đọc GC logs đúng cách trong một sự cố hiệu năng

Khi nghi vấn liên quan GC, dùng **Unified JVM Logging**:

```bash
java -Xlog:gc*,safepoint:file=gc-safepoint.log:time,uptime,level,tags:filecount=5,filesize=20M -jar service.jar
```

`service.jar` là ứng dụng giả định. Cấu hình này ghi các events GC/safepoint vào file có rotation theo JDK hỗ trợ. Chọn tag/level thực tế theo câu hỏi cần giải đáp, test overhead/disk và bảo vệ nội dung. **Đừng bật toàn bộ debug/trace logs không giới hạn** trong lúc hệ thống đang thiếu CPU/disk.

Phân tích:

1. **Có GC cycle/pause nào đúng thời điểm latency tăng?**
2. **Pause duration** là bao nhiêu? Phân biệt pause phases với **concurrent cycle duration**.
3. Heap used/capacity trước/sau GC, live-set trend có tăng bất thường không?
4. Có **allocation stalls** hoặc liên tiếp các cycles cho thấy collector không theo kịp?
5. CPU/cgroup throttling có xảy ra cùng lúc? GC có bị cạnh tranh CPU?
6. Request latency tăng có còn xảy ra **ngoài** GC events không?
7. Nếu đổi JDK/collector giữa hai lần so sánh, hai cấu hình có thật sự tương đương không?

**Không suy ra P99 request latency từ P99 GC pause.** Một request có thể chịu I/O, lock contention, queueing và scheduling ngoài GC. Ngược lại, pause nhỏ không chứng minh JVM không gây tail latency.

### Một chú ý về JFR GC events

`jdk.GarbageCollection` là sự kiện về hoạt động GC; các loại `jdk.GCPhasePause` mô tả các pha pause khi được bật/ghi. Tên/fields và lượng event phụ thuộc JDK/collector/settings. **Thiếu event trong file JFR chưa chứng minh JVM không làm GC**; kiểm tra event settings, recording window, sampling/threshold và logs.

## 10. Điều tra CPU, lock, thread và I/O mà không quy hết cho GC

### 10.1. CPU cao

**Giả thuyết:** một đoạn code nóng hoặc GC sử dụng nhiều CPU.

Thu:

- OS/process CPU và cgroup throttling cùng timeline.
- JFR `jdk.ExecutionSample` nếu setting đã enable, stack samples, JIT compilation/safepoint events khi phù hợp.
- Application request rates và các endpoint đang có tải cao.
- GC CPU/cycles/logs để xem collector chiếm phần nào.
- Nếu có thể, CPU profile trên workload đại diện nhưng đánh giá overhead.

**Đừng kết luận “memory leak” chỉ vì CPU cao**. CPU có thể bị chi phối bởi serialization, regex, crypto, locks hoặc polling loop; memory leak cần bằng chứng object retention/heap growth riêng.

### 10.2. Thread hang/deadlock

**Giả thuyết:** nhiều threads chờ lock hoặc deadlock.

Thu:

```bash
jcmd 12345 Thread.print -l
```

Kết hợp với JFR monitor enter/park events và request logs. Nếu snapshot cho thấy một thread đang `WAITING`, nó **chưa chắc deadlock**: thread pool worker, queue consumers và timers thường chờ bình thường. Cần xem các threads liên quan, lock owners, blocked times và **nhiều snapshots** nếu cần phân biệt transient wait với stuck state.

Không kết luận chỉ từ một stack frame `SocketInputStream.read` rằng network “hỏng”: ứng dụng có thể đang chờ response hợp lệ, timeout có thể do upstream load hoặc routing.

### 10.3. Socket timeout và network lỗi

**Giả thuyết:** request thất bại do mạng hay upstream.

Thu:

- Exception class/message/cause, hostname/endpoint **đã kiểm duyệt**, request ID và retry count.
- JFR socket read/write durations khi có event phù hợp được bật.
- Connection pool occupancy/queue, DNS lookup latency và cache behavior.
- Upstream service logs/metrics, server-side latency, firewall/route, TCP retransmission nếu có đo từ OS.
- Phân biệt `connect timeout`, `read timeout`, `pool acquisition timeout` và application deadline.

**Không chỉ tăng timeout** vì thấy một lần `SocketTimeoutException`; hãy xác định chậm ở tầng nào và tác động latency/throughput.

### 10.4. Heap OOM so với container OOMKilled

Hai tình huống thường bị gộp nhầm:

- **`OutOfMemoryError: Java heap space`:** JVM không cấp phát đủ trong heap theo các ràng buộc/GC hiện có. Cần GC/heap logs, live set, object retention, allocation rate, `-Xmx`; heap dump có thể giúp khi được phép.
- **Container/OOMKilled từ cgroup/OS:** tổng memory charge của container vượt giới hạn; có thể không có Java OOME hoặc stack trace vì OS kill process. Cần cgroup events, RSS, direct buffers, metaspace, code cache, thread stacks, native allocations, sidecars và container limit.

**Đừng kết luận tăng `-Xmx` sẽ chữa mọi OOM**. Tăng heap có thể làm container OOMKilled sớm hơn nếu native overhead vẫn cao.

### 10.5. Khi lỗi xuất hiện ngay sau deploy

Thu:

- Build hash và dependency/runtime versions trước–sau.
- Feature flags và configuration diffs **đã loại secrets**.
- Request mix, traffic rate và deployment/canary split.
- GC/JFR/logs ở phiên bản tốt và lỗi **trên workload tương đương**.
- OS/container limits, node placement và JVM build có thay đổi hay không.

**Rollback làm lỗi giảm là tín hiệu mạnh về quan hệ với thay đổi**, nhưng chưa nói chính xác *dòng code nào* là nguyên nhân; cần tiếp tục phân tích thay đổi có thể là config, dependency, data migration hay resource quotas.

## 11. Phân biệt bằng chứng, giả thuyết và kết luận

Một quy trình chẩn đoán có trách nhiệm:

| Bước | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Quan sát** | Điều gì đã xảy ra, lúc nào? | 5xx tăng 10:01–10:03Z |
| **Thu bằng chứng** | Log/JFR/metrics nào xác nhận hiện tượng? | 150 request timeouts, CPU throttling tăng |
| **Đặt giả thuyết** | Cơ chế nào có thể giải thích? | GC quá tải, upstream chậm, lock contention |
| **Tìm phản chứng** | Điều gì sẽ sai nếu giả thuyết đúng? | Nếu GC là nguyên nhân chính, cần events/stalls tương ứng với timeline |
| **Thử can thiệp có kiểm soát** | Có thể giảm một yếu tố mà giữ yếu tố khác? | Giữ traffic, so sánh CPU quota trong staging |
| **Đánh giá kết quả** | Hiệu ứng có lặp lại và đủ lớn hơn nhiễu? | P99 giảm cùng với throttling khi tăng CPU, nhiều lần chạy |
| **Kết luận có điều kiện** | Đã biết gì, chưa biết gì? | Trong môi trường X, CPU throttling là yếu tố đóng góp; cần kiểm tra thêm upstream |
| **Khắc phục và phòng ngừa** | Làm sao tránh tái phát? | Alert quota, load test, cap queue và runbook evidence |

### “Cùng lúc” không đồng nghĩa “do”

Ví dụ JFR cho thấy một GC event tại 10:01:15Z và request bị timeout cùng giây ấy. Chưa đủ để nói “GC gây timeout”:

- Request có thể đã chờ DB 2 giây trước khi GC xuất hiện.
- CPU bị throttled có thể làm **cả GC và application chậm**.
- A request timeout có thể xảy ra đúng lúc GC theo xác suất khi load cao.
- JFR event settings/sampling có thể chỉ ghi một phần.
- Clock skew hoặc log ingestion delay có thể khiến hai events trông trùng giờ.

Để củng cố giả thuyết, cần **thời gian pause/GC stall thực, request timeline và dữ liệu CPU/I/O/lock**, kiểm tra nhiều events/runs hoặc làm phép thử có kiểm soát.

### Bảng “dữ kiện / suy luận / chưa biết”

Trong báo cáo, phân biệt rõ:

```text
Quan sát:
  - 10:01:10Z–10:03:00Z: tỉ lệ timeout tăng lên 8%.
  - Trong cùng khoảng: cgroup CPU throttling tăng.
  - JFR có các thread samples cho thấy CPU bận ở khu vực X.

Giả thuyết:
  - Thiếu CPU góp phần kéo dài thời gian xử lý request.

Chưa biết:
  - Upstream DB latency có góp phần hay không.
  - Việc tăng CPU quota có loại được timeout dưới cùng tải hay không.

Bước tiếp:
  - So sánh cùng workload, giữ nguyên build, tăng CPU quota trong staging.
  - Kiểm tra trace durations của DB và JFR CPU/thread samples.
```

Đây là cấu trúc báo cáo **minh họa**, không phải incident đã xảy ra thật.

## 12. Thiết kế “incident evidence bundle” đủ dùng, không tràn lan

Một **bundle** cho một incident có thể có cấu trúc logic:

```text
incident-042/
  manifest.txt               # incidentId, UTC window, service/version, hashes
  app-logs-redacted.txt      # eventId/requestId/traceId, errors, stack/cause
  jvm-gc.log                 # selected GC/safepoint data
  flight-recording.jfr       # recording đã giới hạn timeframe
  thread-snapshot.txt        # nếu symptoms liên quan threads
  environment-allowlist.txt  # JDK, OS, GC flags, resource limits (đã kiểm duyệt)
  metrics-summary.csv        # timestamps + latency/CPU/RSS/cgroup metrics
  timeline.txt               # thay đổi, deploy, mitigation, kết quả
  notes.txt                  # hypotheses, evidence, unknowns, safe next actions
```

Đây là **sơ đồ logic**, không phải lệnh tạo thư mục hay yêu cầu phải thu mọi artifact. Nếu incident chỉ liên quan một lỗi validate đầu vào có stack trace rõ, có thể không cần JFR/heap dump. Nếu nghi JVM crash/OOM, bằng chứng heap/native/hs_err sẽ quan trọng hơn.

### 12.1. Một manifest đáng tin

Nên ghi:

- Incident ID; thời gian tạo và phạm vi UTC.
- Service/instance/container/pod ID; release/image digest.
- JDK vendor/build, OS/architecture; heap/GC mode và thông số cấu hình cần thiết.
- Nguồn file, phiên bản công cụ đã xuất, quy tắc redaction áp dụng.
- Mỗi file: **kích thước và checksum** (ví dụ SHA-256) để phát hiện thay đổi trong quá trình truyền.
- Ai có quyền truy cập, retention deadline và nơi lưu.
- Những dữ liệu không thu được (**missing evidence**) và nguyên nhân: process đã chết, log rotated, không có JFR, attach bị từ chối.
- Các hành động đã thay đổi trạng thái hệ thống trong lúc thu thập.

Checksum giúp kiểm tra **tính toàn vẹn của bản sao** khi so với nguồn đáng tin, **không tự chứng minh** nội dung chính xác hoặc ai là tác giả của file. Nếu cần chuỗi quản lý bằng chứng chặt chẽ, áp dụng quy trình ký/lưu trữ/audit phù hợp.

### 12.2. Thu thập có tác động thấp trước

Một thứ tự thường hợp lý:

1. Xác nhận PID/instance/release và incident window từ monitoring.
2. Lưu logs/timestamps và metrics đã sẵn có, không restart process vội.
3. Kiểm tra VM version/flags và JFR recording có sẵn, nếu có quyền.
4. Dump **rolling JFR** hoặc bắt recording ngắn phù hợp.
5. Lấy thread snapshots khi nghi hang/lock; cân nhắc số threads và overhead.
6. Khi vẫn cần, mới xét allocation profiling/heap histograms/heap dump/native diagnostic ops theo mức độ tác động.
7. Sau khi giữ được chứng cứ cốt lõi, thực hiện mitigation được ủy quyền và ghi chính xác thời điểm thay đổi.
8. Redact, review permissions, checksum, lưu retention, chia sẻ cho người xử lý sự cố.

Một **process đã chết** không thể được `jcmd` attach trở lại. Nếu dự kiến lỗi hiếm, rolling JFR và log rotation an toàn từ trước có thể hữu ích hơn cố khởi động JFR sau khi sự cố kết thúc.

## 13. Hướng dẫn bảo mật cho từng artifact

| Artifact | Có thể chứa dữ liệu nhạy cảm | Cách bảo vệ |
| --- | --- | --- |
| Application log | Request IDs, user data, URLs, exception messages | Allowlist fields, redact, ACL, retention, access logging |
| GC/safepoint log | Paths, JVM info, memory/CPU patterns | Nội bộ có quyền, giới hạn volume |
| JFR recording | Command line/JVM props, stack traces, class/thread names, custom event values | Bảo vệ như diagnostic dump, không public URL |
| Thread dump | Class/method names, stack traces, locked monitors, thông tin nội bộ | Chỉ đọc bởi người được phép |
| Heap dump | Secrets, tokens, private data, cached payloads | Mã hóa và giới hạn quyền cao, retention ngắn |
| VM.command_line | JVM args/`-D` properties có thể lộ secrets | Không tự thu/chia sẻ vô điều kiện |
| VM.system_properties | Properties có thể gồm credentials/paths | Chỉ trích những trường được phép |
| Environment snapshot | OS/container ids, internal endpoints, quotas | Allowlist, review, restrict access |
| OS core dump | Toàn bộ memory/native internals | Quy trình mức nhạy cảm cao nhất |
| Metrics/traces | Resource attributes, spans, service names/labels | Kiểm soát cardinality và dữ liệu người dùng |

Nếu cần chia sẻ dữ liệu ra ngoài tổ chức, chuẩn bị **bản đã được rà soát và loại thông tin nhạy cảm**; bản gốc vẫn phải nằm trong nơi lưu có quyền phù hợp. Một số artifact sau khi “scrub” vẫn có thể tiết lộ thông tin qua stack names hoặc metrics; cần kiểm tra nội dung kết quả.

Không dùng `jfr print --json` rồi đưa toàn bộ nội dung không kiểm duyệt vào một hệ thống tập trung nếu file gốc chứa thông tin cần bảo vệ.

## 14. Những lỗi thường gặp khi chẩn đoán Java

| Sai lầm | Vì sao kết luận sai hoặc nguy hiểm | Cách sửa |
| --- | --- | --- |
| Thấy `OutOfMemoryError` là tăng `-Xmx` ngay | Có thể live set tăng/leak, native/container pressure hoặc lỗi không thuộc heap | Thu loại OOME, heap/GC, cgroup/NMT trước |
| Thấy GC event gần timeout rồi quy lỗi cho GC | Correlation không phải causation | Xem pause/stall duration, request span và CPU/I/O |
| Chỉ có `ex.getMessage()` | Thiếu stack/cause chain | Log exception object an toàn tại boundary |
| Log raw request body/Authorization header | Lộ credentials/PII | Allowlist/redact, kiểm thử log injection |
| In toàn bộ `System.getenv()` | Variables có thể chứa secrets | Thu allowlist và review |
| `java -version` rồi cho là version service | Shell và service có thể dùng JVM khác | Lấy `jcmd PID VM.version`/deployment evidence |
| Có `.jfr` rồi cho là đủ mọi events | Event settings, threshold và window có thể thiếu dữ liệu | `jfr summary`/`metadata` + đối chiếu logs |
| Không ghi thời gian recording | Không thể đối chiếu với incident | Lưu UTC window và process uptime |
| Ghi `-Xlog` ở mức trace mọi nơi | Chi phí I/O/disk và dữ liệu quá nhiều | Chọn tags/levels, rotation, load test overhead |
| Chạy `GC.heap_dump` mặc định | Có thể tốn memory/disk/pause và tiết lộ private data | Chỉ dùng khi có giả thuyết rõ và được phép |
| Dùng `VM.system_properties` đưa thẳng lên ticket | Có thể lộ `-Dsecret` | Kiểm duyệt/allowlist |
| Giải thích JFR thiếu event là không xảy ra event | Sampling/disabled/threshold hoặc process chết | Kiểm tra settings, duration và GC/application logs |
| Gọi `jcmd` sai process/container | Thu nhầm artifact hoặc tác động process khác | Xác minh PID/namespace/service trước khi dùng |
| Dùng metrics 1 phút để kết luận không có 300ms spike | Khoảng sampling làm mất sự kiện ngắn | Thu event-level/JFR/tracing có granularity thích hợp |
| Restart trước khi thu được gì | Mất heap/thread/JFR ring buffer trạng thái lỗi | Lưu bằng chứng khả dụng trước mitigation nếu an toàn |
| Thấy một thread `WAITING` là deadlock | Thread pool/queues chờ là bình thường | Xem lock owner, nhiều snapshots, JFR |
| Coi RSS bằng `-Xmx` | Native memory và virtual reservations khác heap | OS/cgroup metrics + heap/NMT |
| So sánh JDK 15 và JDK 24 ZGC không nêu mode | Collector đã thay đổi; JDK24 chỉ generational ZGC | Ghi build/flags/mode |
| Loại run/outlier gây kết quả xấu | Selection bias, mất dấu hiệu lỗi hiếm | Giữ data, điều tra anomalies |
| Thay JVM flag đồng thời rollback code | Không biết yếu tố nào làm hệ thống hồi phục | Ghi actions và kiểm chứng có kiểm soát |
| Xóa JFR/log ngay sau khi điều tra | Không thể tái kiểm tra RCA | Retention theo policy, có checksum/manifest |
| Đưa một giả thuyết thành kết luận chắc chắn | Bỏ qua alternative explanations | Báo evidence, uncertainty và next test |

## 15. Checklist trước khi đưa ra kết luận lỗi

- [ ] Đã xác định **incident ID, môi trường, service/instance, UTC start/end** và mức ảnh hưởng?
- [ ] Đã ghi **JDK vendor/build**, application version/commit/image và GC mode/flags của **process thật**?
- [ ] Đã giữ logs chứa error class, stack, cause chain, request/trace ID mà không lộ secrets?
- [ ] Log files có rotation, retention và source timestamps đủ cho incident window?
- [ ] Nếu cần JFR, đã chọn `default` hay `profile` theo mục tiêu, biết event threshold/sampling và chi phí?
- [ ] Đã kiểm tra recording có đúng event types bằng `jfr summary`/`metadata`, không chỉ kiểm tra file tồn tại?
- [ ] Có căn chỉnh **JFR timestamps, application logs và metrics** theo cùng clock/window?
- [ ] Có dữ liệu về CPU quota/throttling, process RSS/container limit, heap/GC nếu symptoms liên quan tài nguyên?
- [ ] Có xác minh PID/container namespace, quyền attach trước khi chạy `jcmd`?
- [ ] Có tránh thu `VM.system_properties`/`VM.command_line` không kiểm duyệt?
- [ ] Có phân biệt **GC pause**, **concurrent GC work**, **thread blocking**, **I/O wait** và **request latency**?
- [ ] Có ghi **trước/sau restart/rollback/deploy** để không đánh đồng hai trạng thái?
- [ ] Nếu một artifact không có, đã ghi rõ **missing evidence** và giới hạn của kết luận?
- [ ] Có ít nhất **một giả thuyết cạnh tranh** và phép đo để bác bỏ giả thuyết chính?
- [ ] Có đánh giá tác động/truy cập/retention của thread dump, heap dump, JFR và crash data?
- [ ] Có viết kết luận theo mức chắc chắn phù hợp với bằng chứng, tránh ngôn ngữ “chắc chắn” khi chưa đủ?
- [ ] Có ghi lại **hành động khắc phục, kết quả kiểm chứng và ngăn ngừa tái diễn**?
- [ ] Nếu vấn đề chỉ xảy ra với workload production, đã cân nhắc môi trường staging có CPU/memory/traffic tương đương?
- [ ] Các công cụ và JVM flags dùng có được phiên bản JDK hiện tại hỗ trợ, không copy tài liệu legacy?
- [ ] Bộ bằng chứng được lưu **an toàn**, chỉ chia sẻ theo quyền và có thời hạn giữ phù hợp?

## 16. Tài liệu chính thức còn áp dụng

- **Oracle JDK 25 — Diagnostic Tools**: tổng quan `jcmd`, JFR và hướng phân tích lỗi: https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html
- **Oracle JDK 25 — `jcmd` command**: `VM.version`, `VM.flags`, `Thread.print`, `GC.heap_info`, `JFR.start/dump/check/stop` và impacts: https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html
- **Oracle JDK 25 — `jfr` command**: `summary`, `metadata`, `print`, `scrub` và xử lý recordings: https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html
- **Oracle JDK 25 — Java command**: `-XX:StartFlightRecording` và Unified Logging `-Xlog`: https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
- **Oracle JDK 15 — `jdk.jfr.Recording`**: API `enable/start/stop/dump/close`: https://docs.oracle.com/en/java/javase/15/docs/api/jdk.jfr/jdk/jfr/Recording.html
- **Oracle JDK 15 — `jdk.jfr.Event`**: custom event types, fields, `commit` và `shouldCommit`: https://docs.oracle.com/en/java/javase/15/docs/api/jdk.jfr/jdk/jfr/Event.html
- **Oracle JDK 15 — `jdk.jfr.consumer.RecordingFile`**: đọc các recordings nhỏ/streaming: https://docs.oracle.com/en/java/javase/15/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html
- **Oracle JDK 15 — `java.util.logging.Logger` / `FileHandler`**: logging với `Throwable` và file handler: https://docs.oracle.com/en/java/javase/15/docs/api/java.logging/java/util/logging/Logger.html và https://docs.oracle.com/en/java/javase/15/docs/api/java.logging/java/util/logging/FileHandler.html
- **Oracle JDK 25 — Flight Recorder API Programmer’s Guide**: recording configurations, custom events và dữ liệu: https://docs.oracle.com/en/java/javase/25/jfapi/
- **Oracle JDK 25 — Troubleshooting Guide**: quy trình thu thập bằng chứng, crash, memory và diagnostic tools: https://docs.oracle.com/en/java/javase/25/troubleshoot/
- **OpenJDK JEP 377 — ZGC production từ JDK 15**: https://openjdk.org/jeps/377
- **OpenJDK JEP 490 — Remove Non-Generational ZGC từ JDK 24**: https://openjdk.org/jeps/490
- **W3C Trace Context**: quy tắc truyền trace identity giữa các thành phần phân tán: https://www.w3.org/TR/trace-context/

**Kết luận:** trước khi kết luận một lỗi Java đến từ GC, JVM, ứng dụng hay hạ tầng, hãy **thu log ứng dụng có correlation và cause chain, JFR đúng recording window, môi trường JVM/OS/container của process thật và timeline của incident**. Bằng chứng phải có **quyền truy cập/retention/redaction phù hợp**. Sau đó xây dựng **giả thuyết có thể kiểm tra, đối chiếu các nguồn và ghi rõ điều chưa biết**. Cách làm này giảm những “bản sửa chữa” chỉ dựa trên suy đoán và vẫn phù hợp với Java 15+ cũng như các JDK đang được bảo trì.
