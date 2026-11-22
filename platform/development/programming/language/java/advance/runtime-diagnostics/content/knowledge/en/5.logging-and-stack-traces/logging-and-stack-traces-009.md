# 5.9. Kiểm soát khối lượng log, dữ liệu bí mật và tác động của việc ghi đồng bộ

Logging giúp tìm lỗi, điều tra sự cố và kiểm toán; nhưng mỗi bản ghi đều tiêu tốn CPU, bộ nhớ, I/O, dung lượng lưu trữ và đôi khi làm tăng độ trễ request. Một dòng log có thể đi qua nhiều bước: tạo đối tượng sự kiện, format, chụp thread/trace context, serialize, khóa appender, ghi stdout/file, container runtime, collector, network, rồi storage/index. Nếu log quá nhiều, hệ thống quan sát có thể trở thành nguyên nhân gây chậm hoặc thậm chí làm lộ bí mật.

Mục tiêu của bài học thuộc **5. Nhật ký và stack trace** là cân bằng ba điều:

- **Đủ chứng cứ:** giữ các sự kiện quan trọng, outcome, errorCode, thời điểm, duration và correlation/trace ID để lần theo một thao tác.
- **Trong ngân sách:** kiểm soát events/second, bytes/second, CPU, allocation/GC, queue, tác động lên p95/p99 latency và chi phí lưu trữ.
- **An toàn:** không để password, token, session secret, thông tin cá nhân, payload nhạy cảm, nội dung exception hoặc dữ liệu hạ tầng bí mật lọt vào log.

**Nguyên tắc:** giảm log không có giá trị *trước khi tạo*, loại secrets *trước khi serialize*, đo chi phí *ở đúng đường thực thi*, và xem async logging là **hàng đợi hữu hạn có chính sách lỗi**, không phải phép màu loại bỏ chi phí.

## 1. Tại sao một lời gọi logger có thể làm ứng dụng chậm?

Xem đường đi tổng quát:

~~~text
Request thread
   |
   | logger.info/debug/error(...)
   v
Level check / filter / sampling
   |
   +-- tạo arguments, message, context, stack/caller data
   |
   v
Encoder / formatter (text, JSON)
   |
   +-- synchronous appender --> stdout / file / network
   |                            --> container / collector / storage
   |
   +-- async appender -------> bounded queue
                                |
                                +--> background writer --> sink
                                |
                                +--> queue full: block / drop / fallback
~~~

Sơ đồ là mô hình ý niệm: việc tạo arguments, format và context có thể xảy ra ở các vị trí khác nhau tùy framework/backend/configuration. Ngay cả khi DEBUG bị tắt hoặc log được đưa vào queue, Java vẫn **đánh giá arguments của method** trước khi gọi logger; những phép tính nặng có thể tốn CPU/heap trước level check.

Các nguồn chi phí thường gặp:
1. **CPU:** serialize DTO/JSON, format stack trace, tạo timestamp, stringify collection, escape chuỗi.
2. **Allocation/GC:** mỗi bản ghi có thể tạo nhiều string, array, object, buffer và snapshot MDC.
3. **Khóa/chờ:** nhiều thread tranh một appender hay stdout stream; lock contention làm p99 tăng.
4. **Đĩa/pipe/network:** stdout trong container là pipe có buffer; khi consumer chậm, write có thể block. File rotation, flush, network retry cũng tạo backpressure.
5. **Bộ nhớ queue:** async logging giữ event trong heap chờ writer; queue càng lớn, memory/flush time có thể càng lớn.
6. **Lưu trữ và tìm kiếm:** data ingest, replication, index, retention và xuất dữ liệu đều tiêu tiền và tài nguyên.

Đừng suy từ tên API `log.info(...)` rằng ghi đã bất đồng bộ. SLF4J là façade; appender/backend mới quyết định cách vận chuyển và xử lý record.

## 2. Đặt ngân sách khối lượng log bằng số liệu

### 2.1. Công thức cơ bản

~~~text
events_per_second ≈ requests_per_second × avg_events_per_request
                    + events_from_jobs_and_background_tasks

raw_bytes_per_second ≈ events_per_second × avg_serialized_event_bytes
~~~

Ví dụ giả định: một service xử lý **2.000 request/s**, mỗi request sinh **4 records**, mỗi record sau khi serialize dài trung bình **600 bytes**; tạm bỏ qua background events.

~~~text
events/s = 2,000 × 4 = 8,000
bytes/s = 8,000 × 600 = 4,800,000 bytes = 4.8 MB/s
bytes/hour = 4,800,000 × 3,600
           = 17,280,000,000 bytes = 17.28 GB/hour
~~~

Ở đây MB/GB là **đơn vị thập phân**, không phải MiB/GiB. Đây là dung lượng **raw serialized log**, chưa kể compression, index, metadata, replication, retention hoặc việc thu thêm qua nhiều sink. Nếu bật DEBUG khiến số event/request gấp đôi, volume thường tăng tương ứng; nếu đồng thời log cả payload lớn, mức tăng còn mạnh hơn.

Không chỉ nhìn tổng số dòng. Hai hệ thống cùng 10.000 records/s nhưng một hệ thống có stack trace dài 30 KB/record và hệ thống kia chỉ 300 bytes sẽ có chi phí rất khác nhau.

### 2.2. Chỉ số cần quan sát

| Chỉ số | Điều cần biết |
| --- | --- |
| `log_events_total` theo service, level, event name | Sự kiện nào chiếm phần lớn traffic? |
| `log_bytes_total` và bytes/s | Phình vì số event hay kích thước event? |
| `log_event_size_bytes` p50/p95/p99 | Stack trace và payload nào quá lớn? |
| `log_dropped_total` theo reason/level | Mất do sampling, filter, queue full hay exporter? |
| Queue occupancy/capacity, enqueue/dequeue rate | Writer có theo kịp producer? |
| Log call/enqueue p95/p99 | Caller có bị chặn hoặc tốn CPU đáng kể? |
| Sink write latency, retry, exporter backlog | Collector, file, stdout hoặc network có chậm? |
| Disk space/inodes, file rotation, retention | Có nguy cơ đầy disk, mất log hoặc tự làm hỏng service? |
| Request latency/throughput, CPU, allocation/GC | Logging có gây suy giảm hiệu năng JVM không? |

Đây là **tên/nhóm metric đề xuất**, không phải chỉ số mặc định luôn có ở mọi Java logger. Phân biệt **log được tạo**, **enqueue thành công**, **ghi vào sink**, và **được backend ingest**; một appender báo nhận sự kiện không chứng minh record đã lưu bền vững ở đích.

### 2.3. Tìm “top talkers” và cardinality

Nhóm volume theo `service`, `environment`, `version`, `level`, `eventName`, `logger`, `route chuẩn hóa`, `instance`. Tránh dùng requestId, userId, URL chứa query params hoặc exception message làm **metric label**: cardinality tăng cực lớn. ID chi tiết nên nằm trong log/trace nếu có lý do hợp lệ; metrics thường dùng nhãn có tập giá trị hữu hạn.

Khi kiểm tra service có 99% INFO từ vòng lặp xử lý item, hãy hỏi **có thể chuyển thành một event tổng hợp + counter/histogram không?** Việc gỡ bỏ nguồn tạo event thường hiệu quả hơn chỉ drop ở collector, bởi collector filtering không hoàn trả CPU/heap đã dùng trong JVM.

## 3. Giảm volume mà vẫn giữ khả năng chẩn đoán

### 3.1. Ghi đúng level và đúng mốc

| Level phổ biến | Nên dùng | Kiểm soát volume |
| --- | --- | --- |
| **ERROR** | Một thao tác thất bại thực sự, có errorCode/cause | Log tại nơi quyết định outcome, tránh mỗi tầng log lại một exception |
| **WARN** | Bất thường có thể khôi phục, retry/fallback | Giới hạn sự kiện lặp, giữ tổng số lỗi và context |
| **INFO** | Mốc lifecycle, outcome, thay đổi cấu hình quan trọng | Ưu tiên log completion có duration/outcome thay vì từng bước |
| **DEBUG** | Quyết định xử lý chi tiết, đặc biệt khi điều tra | Bật theo logger/service và thời lượng giới hạn, sampling hợp lý |
| **TRACE** | Các bước cực nhỏ, volume cao | Chỉ bật có mục tiêu và trên phạm vi tải an toàn |

Không quy mọi HTTP 4xx theo hợp đồng là ERROR; cũng không hạ thấp lỗi thật chỉ để giảm quota. Nếu một exception được log ERROR ở tầng thấp, log ERROR ở controller và tiếp tục log ERROR ở gateway, có thể thành ba bản sao cho một sự cố. Hãy phân biệt **lỗi trung gian được retry thành công** với **outcome cuối cùng thất bại**.

Trước:
~~~text
INFO validating record 1
INFO validating record 2
INFO validating record 3
...
INFO validating record 10000
~~~

Sau (ví dụ dữ liệu minh họa):
~~~json
{"level":"INFO","event":"batch.validation.completed","items":10000,"invalid":42,"durationMs":825,"outcome":"PARTIAL_FAILURE"}
~~~

Nếu cần điều tra 42 lỗi, ghi errorCode và reference đã qua chính sách bảo vệ dữ liệu, hoặc dùng tracing/chi tiết lấy mẫu có kiểm soát. Đừng tự động ghi toàn bộ DTO cho mỗi item.

### 3.2. Sampling, rate limit và aggregation

- **Sampling theo request/trace:** quyết định giữ/không giữ theo ID ổn định để giữ ngữ cảnh của cùng một flow, tránh chọn độc lập từng dòng khiến timeline đứt đoạn.
- **Probabilistic sampling:** 1%, 5% hoặc tỷ lệ tùy traffic; cần hiểu sampling bias khi suy thống kê.
- **Deterministic hash sampling:** hash request/trace ID (không dùng ID cá nhân nhạy cảm trong metric) để các nhánh có thể giữ cùng quyết định; chính sách phải được chia sẻ rõ.
- **Rate limiting:** tối đa N event trong mỗi khoảng, tránh log storm khi một dependency hỏng. Vẫn cần metric số lần bị giảm và thông báo tổng hợp có giới hạn.
- **Aggregation/deduplication:** “timeout tới inventory-api xảy ra 8.432 lần trong 1 phút” có giá trị hơn 8.432 dòng giống nhau, miễn vẫn giữ ngữ cảnh đại diện khi cần.

**Không lấy mẫu/tắt tùy tiện** audit events, sự kiện bảo mật bắt buộc hoặc log được đòi hỏi theo hợp đồng/luật. Với ERROR/WARN, chính sách cũng phải xét sự cố tạo log storm: giữ số lỗi chính xác qua metrics, giới hạn bản ghi trùng lặp, và bảo vệ những event có ý nghĩa pháp lý bằng pipeline khác.

Nếu dùng **tail sampling**, hệ thống thu thập cần giữ dữ liệu cho đến khi biết outcome; không thể “giữ mọi trace lỗi” nếu event đã bị drop từ đầu trước khi quyết định. Sampling ở collector không làm giảm chi phí định dạng log đã xảy ra tại application.

### 3.3. Giới hạn kích thước mỗi record

Các nguồn phình lớn: request/response body, headers, cookie, collection, DB rows, SQL bind parameters, base64 binary, nested DTO và stack trace dài hoặc lặp qua nhiều tầng.

Nên:
- Dùng **schema/allowlist**, chỉ ghi `event, outcome, statusCode, errorCode, durationMs, correlationId` và các thuộc tính có giá trị đã được duyệt.
- Giới hạn độ dài text, số phần tử collection, stack frames hoặc số event chi tiết được tạo, theo yêu cầu điều tra.
- Ghi `truncated=true` hoặc aggregate count khi có chủ đích; không truncate mù quáng khiến JSON thành sai cú pháp.
- Tránh serialize toàn bộ object rồi cắt ở collector: CPU/memory và nguy cơ rò bí mật đã xảy ra ở phía ứng dụng.

## 4. Dữ liệu bí mật: phòng ngừa trước khi serialize

Log là bản sao dữ liệu dễ bị nhân rộng sang console, file, collector, dashboard, SIEM, archive, ticket và chat. Một secret xuất hiện trong log có thể tồn tại lâu sau khi phiên làm việc gốc kết thúc.

### 4.1. Những trường không được ghi nguyên văn

| Loại | Ví dụ | Thay thế hợp lý |
| --- | --- | --- |
| **Authentication** | Password, OTP, access/refresh token, JWT, API key, Authorization header | Chỉ event auth outcome, method, failure code |
| **Session** | Session cookie, session ID, signed URL, CSRF secret | Correlation ID nội bộ không chứa secret |
| **PII** | Email, số điện thoại, địa chỉ, định danh, dữ liệu sức khỏe | Không ghi nếu không cần; nếu được phép thì masking/tokenization có chính sách |
| **Financial/payment** | Số thẻ, CVV, chi tiết tài khoản | Business reference đã được phê duyệt, status và errorCode |
| **Infrastructure** | Private key, DB URL chứa password, secret env var, config secrets | Tên cấu hình, key tồn tại/không tồn tại, trạng thái kết nối |
| **Payload** | Login form, ảnh/tài liệu, raw HTTP request/response | Content type, byte size, route, validation outcome |
| **Exception internals** | Throwable message chứa URL token, SQL bind data hoặc user input | Exception type + stable errorCode, stack/cause đã bảo vệ |

**Không truyền domain object hoặc credential vào logger chỉ vì framework có placeholder**. `logger.info("request={}", request)` vẫn có thể gọi `toString()` chứa password/token/PII. Đặc biệt kiểm tra nested exceptions, request headers, MDC, HTTP client interceptors, ORM SQL parameters và debug wire logs.

### 4.2. Allowlist tốt hơn regex redaction một lớp

Luồng an toàn là tạo một **log event mới chỉ từ các trường được phép**, chẳng hạn:

~~~json
{"level":"WARN","event":"payment.authorize.failed","correlationId":"req-42","errorCode":"DOWNSTREAM_TIMEOUT","durationMs":782}
~~~

Không serialize nguyên `PaymentRequest` để rồi hy vọng regex tìm đủ mọi cách mã hóa token. Redaction tại logging encoder và collector vẫn hữu ích như **phòng tuyến bổ sung**, nhưng không nên là tuyến duy nhất.

Hạn chế:
- **Masking** như che bớt email vẫn có thể là dữ liệu cá nhân; phải tuân thủ mục đích và chính sách xử lý.
- **Hash email/điện thoại** không tự động thành vô danh: có thể đoán được qua từ điển. Nếu cần khả năng liên kết, cân nhắc tokenization/HMAC với khóa quản lý và mục đích được phê duyệt.
- **Log injection:** input có newline/control characters hoặc chuỗi giả timestamp có thể tạo log giả khi ghép text. Validate input và dùng structured encoder escape đúng.
- **Secret in Throwable:** thông điệp lỗi từ HTTP/DB có thể chứa URL query, credentials; truyền Throwable cần kèm cơ chế bảo vệ nội dung.
- **Log trong môi trường khác:** DEBUG được phép ở staging không có nghĩa production được lưu raw payload; staging cũng phải bảo vệ dữ liệu thật nếu có.

### 4.3. Bảo vệ vòng đời log

Áp dụng các lớp: least-privilege access, mã hóa khi truyền/lưu, retention theo mục đích, phân quyền export, lịch sử truy cập, xóa bản sao theo chính sách và theo dõi ai có thể đọc log. Không để log file ở thư mục public hoặc cùng phân vùng quan trọng mà không có quota/rotation.

Nếu phát hiện token/password đã lộ qua log, việc “ẩn dòng khỏi dashboard” **không đủ**. Cần đánh giá mọi nơi dữ liệu đã được gửi, cô lập/truy hồi quyền truy cập, xóa bản sao theo khả năng, điều tra phạm vi lộ và revoke/rotate credential khi phù hợp. Bản log tạm được gửi vào ticket hay công cụ bên ngoài cũng phải được tính đến.

## 5. Vì sao ghi đồng bộ có thể kéo p99 latency tăng?

**Synchronous appender** thực hiện phần việc ghi trên đường caller, đôi khi phải chờ lock, output buffer, disk, stdout pipe, rotation hoặc network. Chi phí có thể rất dao động. Ví dụ **minh họa** cùng một request:

~~~text
business work:                   10.0 ms
format log on caller:             0.3 ms
wait for appender/stdout write:  15.0 ms
business work:                    5.0 ms
-----------------------------------------
approx elapsed:                 30.3 ms
~~~

Trong ví dụ các đoạn tuần tự, phần chờ write chiếm phần lớn thời gian tăng thêm dù CPU thực thi logic nghiệp vụ ít. Đây **không phải benchmark thực tế**; một logger có thể buffered và không flush từng bản ghi, hoặc sink có thể đủ nhanh khi không tải.

Nguồn chặn thường bị bỏ qua:
- `ConsoleAppender` hoặc `System.out` ghi qua pipe; collector/container runtime chậm khiến buffer đầy và write block.
- `FileAppender` có lock/flush/rotation, chịu filesystem latency và disk-full.
- Network appender trực tiếp có thể gặp timeout/reconnect; quy tắc ghi lại phụ thuộc backend.
- Ghi Throwable stack trace tốn CPU/strings ngay cả khi file nhanh.
- Khi nhiều worker cùng gọi appender, lock contention có thể dồn vào tail latency.

**Synchronous write không có nghĩa durable:** file write thành công có thể mới vào OS page cache, chưa fsync; stdout write được nhận có thể chưa tới backend. Cần phân biệt `logged/enqueued`, `written`, `flushed` và `ingested`.

### Argument evaluation: tắt DEBUG vẫn có thể tốn CPU

Hai đoạn sau là **minh họa dùng SLF4J**, không chạy độc lập vì cần logger, DTO và helper trong ứng dụng:

~~~java
logger.debug("payload={}", expensiveSerialize(payload));
~~~

`expensiveSerialize(payload)` **vẫn được gọi** do Java đánh giá arguments trước method call, kể cả khi level DEBUG bị tắt. Nếu tính summary đắt đỏ, dùng guard:

~~~java
if (logger.isDebugEnabled()) {
    logger.debug("payloadSummary={}", safeSummary(payload));
}
~~~

Trong ứng dụng thật nên dùng API lazy/supplier phù hợp backend khi có, không serialize raw payload nhạy cảm. Đừng quên một object `toString()` có thể tự thực hiện logic nặng hoặc lộ dữ liệu.

## 6. Logging bất đồng bộ: tách sink nhưng không xóa backpressure

Async appender có **producer thread** đưa record vào queue và **writer thread** xử lý sink. Điều này có thể giảm thời gian caller phải đợi I/O, nhưng vẫn có phí enqueue, allocation và context capture. Memory queue có giới hạn, writer phải theo kịp lượng log phát ra.

### 6.1. Khi queue đầy, chuyện gì sẽ xảy ra?

| Chính sách | Tác dụng | Rủi ro |
| --- | --- | --- |
| **Block producer** | Chờ có chỗ trống, giảm nguy cơ bỏ log trong ngắn hạn | Request thread bị chặn, timeout, pool saturation, có thể gây outage nếu sink chết |
| **Drop record mới** | Giữ latency caller ít bị tác động | Mất log đúng lúc sự cố, điều tra thiếu chứng cứ |
| **Ưu tiên severity** | Giữ WARN/ERROR khi queue gần đầy, bỏ bớt TRACE/DEBUG/INFO | Không đảm bảo giữ tất cả high severity nếu full/kill; không thay audit |
| **Spill/buffer ra đĩa** | Chịu gián đoạn network ngắn | Tốn disk, I/O, policy dọn và rủi ro disk-full |
| **Fallback sync** | Có thể giữ một số event quan trọng | Lại đặt I/O vào critical path, p99 tăng đúng lúc quá tải |

Không có chính sách nào đúng cho mọi hệ thống. “Never block” thường đánh đổi khả năng mất event, trong khi “never drop” bằng cách chặn có thể đánh đổi availability. Với audit events bắt buộc, cần kênh có semantics delivery/durability rõ ràng, không dựa đơn thuần vào async logger.

### 6.2. Logback AsyncAppender: ví dụ cấu hình và trade-off

Với Logback Classic đã có dependency phù hợp, ví dụ XML dưới đây **chỉ minh họa các công tắc**, không phải khuyến nghị mặc định trên production:

~~~xml
<configuration>
  <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{ISO8601} %-5level [%thread] %logger - %msg%n</pattern>
    </encoder>
  </appender>
  <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>1024</queueSize>
    <discardingThreshold>0</discardingThreshold>
    <neverBlock>false</neverBlock>
    <maxFlushTime>2000</maxFlushTime>
    <appender-ref ref="STDOUT"/>
  </appender>
  <root level="INFO">
    <appender-ref ref="ASYNC"/>
  </root>
</configuration>
~~~

- `queueSize=1024`: số event tối đa trong queue, **không phải số bytes tối đa**. Event lớn/stack trace dài vẫn có thể tốn heap.
- `discardingThreshold=0`: tắt cơ chế tự loại bớt level thấp khi queue gần đầy theo ngưỡng của Logback, **không đảm bảo không bao giờ mất log**.
- `neverBlock=false`: khi queue đầy, producer có thể **bị block** để chờ. Chọn `true` có thể dẫn đến drop nếu queue không nhận record.
- `maxFlushTime=2000`: trong shutdown bình thường, chờ xử lý queue theo giới hạn thời gian (ms); nếu hết hạn hoặc process bị kill/crash thì không chắc đã flush tất cả.
- Appender cuối vẫn là stdout; **pipe/container/collector vẫn có thể chậm**. Bọc AsyncAppender không làm stdout vô hạn.
- Pattern này chỉ xuất plain text, **không tự redaction** hoặc gắn trace ID/correlation ID. Muốn production-safe phải cấu hình encoder/context và bảo vệ secrets riêng.

Logback có cơ chế mặc định loại các event level thấp khi queue gần đầy trong một số phiên bản, và `discardingThreshold` thay đổi hành vi đó. **Đọc manual của đúng version đang sử dụng**; backend khác có cấu hình và semantics khác. Chỉ số INFO bị drop không phải sự kiện ERROR được đảm bảo giữ trọn vẹn.

### 6.3. Shutdown, ordering, retry và mất mát

- Khi service dừng bình thường cần flush/stop logger theo lifecycle và đủ termination grace period. SIGKILL/OOM/crash có thể mất event chưa xử lý.
- Async queue có thể giao thứ tự riêng; nhiều producer và nhiều services có thể xuất hiện thứ tự khác nhau ở backend. Giữ event timestamp, traceId/spanId.
- Retry tại exporter có thể tạo duplicates; queue drop và collector failure tạo gaps. Không mặc định exactly-once.
- MDC/trace context cần được capture khi event phát sinh/propagate đúng qua executor; writer thread không tự biết request gốc.
- Queue tăng mãi là dấu hiệu producer nhanh hơn sink; chỉ tăng queue size làm chậm thời điểm vỡ và tăng heap.
- Theo dõi `queue_size`, `dropped_total`, `write_duration`, exporter errors và request p99 khi thay cấu hình.

## 7. Java 17+ chạy độc lập: sampling, allowlist và chống log injection

Ví dụ này dùng `System.out` để **minh họa chọn event và bảo vệ dữ liệu**, không phải benchmark synchronous/async. Nó xử lý 12 input; giữ 2 event lỗi, lấy mẫu 4 event thành công, bỏ 6 event còn lại. Dữ liệu có email/token trong object **không được đưa vào log**; reference có ký tự newline sẽ bị từ chối.

**Lưu ý:** quy tắc giữ “mỗi request thứ ba” chỉ giúp tạo output xác định; với traffic thật, sampling theo thứ tự có thể sai lệch và không thay thế sampling nhất quán theo request/trace ID.

Tệp **SafeLogBudgetDemo.java**:

~~~java
import java.time.Instant;
import java.util.Locale;
import java.util.regex.Pattern;

public final class SafeLogBudgetDemo {
    private static final Pattern SAFE_REF =
            Pattern.compile("[A-Z0-9-]{1,20}");
    private static final Instant BASE =
            Instant.parse("2026-10-29T00:00:00Z");

    private record Incoming(
            String orderRef,
            String email,
            String accessToken) { }

    private static String allowedRef(String raw) {
        return raw != null && SAFE_REF.matcher(raw).matches()
                ? raw : "[omitted]";
    }

    public static void main(String[] args) {
        int observed = 0;
        int sampledSuccess = 0;
        int emittedErrors = 0;
        int suppressed = 0;

        for (int i = 1; i <= 12; i++) {
            Incoming input = new Incoming(
                    i == 6 ? "BAD\nFORGED" : "ORD-" + i,
                    "private@example.invalid",
                    "demo-token-not-for-log"
            );
            observed++;

            boolean failed = (i % 5 == 0);
            boolean sampleSuccess = !failed && (i % 3 == 0);

            if (!failed && !sampleSuccess) {
                suppressed++;
                continue;
            }

            String level = failed ? "ERROR" : "INFO";
            String event = failed
                    ? "order.failed" : "order.sampled_success";
            String safeRef = allowedRef(input.orderRef());
            String requestId = "req-" + i;

            System.out.printf(Locale.ROOT,
                    "%s level=%s event=%s requestId=%s orderRef=%s%n",
                    BASE.plusSeconds(i), level, event,
                    requestId, safeRef);

            if (failed) {
                emittedErrors++;
            } else {
                sampledSuccess++;
            }
        }

        System.out.printf(Locale.ROOT,
                "summary observed=%d sampledSuccess=%d errors=%d suppressed=%d%n",
                observed, sampledSuccess, emittedErrors, suppressed);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SafeLogBudgetDemo.java
java SafeLogBudgetDemo
~~~

**Stdout chính xác**:

~~~text
2026-10-29T00:00:03Z level=INFO event=order.sampled_success requestId=req-3 orderRef=ORD-3
2026-10-29T00:00:05Z level=ERROR event=order.failed requestId=req-5 orderRef=ORD-5
2026-10-29T00:00:06Z level=INFO event=order.sampled_success requestId=req-6 orderRef=[omitted]
2026-10-29T00:00:09Z level=INFO event=order.sampled_success requestId=req-9 orderRef=ORD-9
2026-10-29T00:00:10Z level=ERROR event=order.failed requestId=req-10 orderRef=ORD-10
2026-10-29T00:00:12Z level=INFO event=order.sampled_success requestId=req-12 orderRef=ORD-12
summary observed=12 sampledSuccess=4 errors=2 suppressed=6
~~~

**Diễn giải:**
- 4 success logs (3, 6, 9, 12) và 2 error logs (5, 10); 6 success events bị suppress theo policy.
- Ở request 6, `orderRef` chứa newline không hợp lệ; code in `[omitted]`, không tạo thêm dòng log giả.
- `email` và `accessToken` tồn tại trong `Incoming` nhưng logger chỉ nhận `requestId`, event và reference đã kiểm tra. Không serialize toàn bộ input object.
- Timestamp cố định giúp test stdout; production phải dùng event time thực, cùng timezone/trace context.
- Chương trình ghi đồng bộ bằng `System.out.printf` nên **không chứng minh** async hay cải thiện p99. Cần benchmark backend/appender thật với workload và sink thực tế.
- Giữ mọi lỗi trong **12 record minh họa** không có nghĩa việc log mọi ERROR ở tải không giới hạn là miễn phí. Pipeline thật vẫn cần capacity/aggregation và kênh bảo vệ audit/security độc lập.

## 8. Đo tác động của synchronous và async logging một cách công bằng

Một thử nghiệm có ích phải giữ nguyên workload, event size, logging level, encoder, host/container, disk/collector và thời lượng. Cần có warm-up, số mẫu đủ lớn và ít nhất hai lần chạy ổn định trước khi so p99.

Các bước:
1. **Baseline:** ghi request p50/p95/p99, throughput, CPU, allocation rate, GC pauses, event/s, bytes/s, dropped events.
2. **Synchronous configuration:** đo thời gian lời gọi logger/appender, lock contention, stdout/file latency và số event tới backend.
3. **Async configuration:** giữ nguyên dữ liệu log, đo thời gian enqueue, queue occupancy, drop/block, writer latency và ingestion count.
4. **Tình huống sink chậm:** giả lập collector down/pipe đầy/disk chậm có kiểm soát trong môi trường thử nghiệm; quan sát ứng dụng block hay drop.
5. **Shutdown:** thử dừng bình thường và abrupt kill; đánh giá logs còn trong queue, ghi rõ giới hạn durability.
6. **Kết luận:** cải thiện p99 chỉ được coi là thành công nếu chất lượng chứng cứ và yêu cầu audit/security vẫn được bảo vệ.

Một đoạn đo khoảng thời gian bằng Java:

~~~java
long startNanos = System.nanoTime();
// Gọi logging thực sự cần đo nằm ở đây trong bài test.
long elapsedNanos = System.nanoTime() - startNanos;
~~~

Đoạn trên chỉ **minh họa boundary đo**; không phải benchmark độc lập. Đo một lần log cực nhỏ chịu overhead của chính phép đo. Một async logger trả về nhanh có thể **chỉ enqueue** chứ chưa ghi log xuống sink. Dùng thông tin của appender và collector để phân biệt.

### Bảng dấu hiệu và giả thuyết

| Dấu hiệu | Khả năng | Kiểm chứng |
| --- | --- | --- |
| p99 request tăng sau bật DEBUG | Eager serialization, log locks, I/O | CPU profiler, log call timing, allocation, bytes/s |
| CPU vẫn tăng khi DEBUG bị filter | Code tạo arguments trước check level | Kiểm tra serialize/toString và level guards |
| Async queue gần đầy, p99 tăng | Producer block chờ queue | Enqueue latency, full count, `neverBlock` |
| p99 giảm nhưng thiếu nhiều log lỗi | Queue drop hoặc exporter/collector mất dữ liệu | Dropped counter, written/ingested counts |
| GC tăng khi async queue lớn | Buffered events chiếm heap | Queue memory, heap usage, allocation, GC |
| Disk hết nhanh sau deploy | More events, larger payload, rotation/retention thiếu | Bytes/event, file sizes, disk/inode, collector |
| Log có token trong exception | Throwable/header/body chưa được sanitize | Review exception messages, encoder, collector filter |
| Không thấy log nhưng request có chạy | Filter, sampling, queue drop, flush chưa xong | Pipeline metrics, trace, appender config |

## 9. Phân loại nguồn log theo yêu cầu độ tin cậy

| Nguồn | Mục tiêu | Chính sách tham khảo |
| --- | --- | --- |
| DEBUG/TRACE | Chẩn đoán chi tiết | Có thể sampling, TTL ngắn, rate limit, drop có metric |
| Operational INFO | Outcome, latency, lifecycle | Giữ mốc quan trọng, giảm lặp, aggregate hot paths |
| WARN/ERROR | Chẩn đoán sự cố | Giữ code/context, theo dõi drop, giới hạn lặp có kiểm soát |
| Security telemetry | Xác định hành vi bất thường | Event schema, integrity, quyền và retention nghiêm ngặt |
| Audit trail bắt buộc | Kiểm toán, trách nhiệm, phục hồi | Durable pipeline với delivery/failure semantics cụ thể |

**Operational logging không tự động là audit trail.** Nếu một sự kiện bắt buộc phải tồn tại sau khi transaction commit, có thể cân nhắc transactional outbox, durable queue hoặc event store với cơ chế replay, deduplication và retention rõ. Chỉ đổi ConsoleAppender sang AsyncAppender không tạo bảo đảm exactly-once.

**Fail-open hay fail-closed khi logger lỗi?**
- Với diagnostics không thiết yếu, thường ưu tiên request vẫn phục vụ, ghi metric/cảnh báo về mất log.
- Với audit/security bắt buộc, chính sách có thể yêu cầu dừng hoặc giới hạn thao tác khi không thể ghi chứng cứ; quyết định phải căn cứ rủi ro và yêu cầu pháp lý, không áp dụng chung.
- Tránh vòng lặp khi bản thân logger/collector lỗi; không spam “failed to log” qua đúng pipeline đang hỏng.

## 10. Các tình huống trước và sau

**A. INFO trong vòng lặp nóng.** Trước: mỗi request sinh 8 records, stdout pipe bị nghẽn; sau: chỉ log kết thúc với `outcome/durationMs/traceId` và dùng metrics cho số item. Đo lại bytes/s và request p99 thay vì chỉ so số dòng.

**B. Async appender giúp p99 nhưng mất chứng cứ.** Queue nhỏ + cấu hình nonblocking có thể drop khi collector chậm. Sau: bổ sung queue/dropped metrics, chọn policy theo severity, tăng capacity có kiểm chứng, kiểm tra shutdown và tách audit channel khi cần. Không chỉ “tăng queueSize thật lớn”.

**C. Secret lọt vào exception.** Request URL chứa access token được gắn vào Throwable message; log ERROR tự động đưa message đó vào storage. Sau: bỏ secret khỏi URL, xây errorCode an toàn và áp dụng redaction cho exception/context; đánh giá việc rotate token đã lộ.

**D. Bật DEBUG làm OOM nặng hơn.** Serialize object graph lớn và queue async giữ events khiến heap/GC tăng. Sau: giới hạn event size, lấy mẫu theo mục tiêu, đo allocation/heap/queue và tự động hết hạn debug override.

**E. Mất log lúc shutdown.** Async worker vẫn còn queue khi container bị kill; những dòng cuối biến mất. Sau: graceful shutdown/flush theo timeout, điều chỉnh grace period, đo event gaps; với audit cần kênh durable khác.

**F. Log volume thành vấn đề bảo mật.** Raw request/response ở production chứa email và cookie; trước đó mỗi request được lưu hàng tuần. Sau: allowlist fields, retention ngắn đúng mục đích, phân quyền, redaction và quy trình xóa/bảo vệ bản sao.

## 11. Các lỗi suy luận thường gặp

- **“Một dòng INFO nhỏ không ảnh hưởng.”** Hàng nghìn dòng mỗi giây và nhiều sink cộng thành CPU, I/O, storage và tail latency.
- **“DEBUG disabled nghĩa là không tốn gì.”** Arguments Java có thể được tạo trước logger call.
- **“Async luôn non-blocking.”** Queue đầy có thể block, drop hoặc fallback; mỗi chính sách có trade-off.
- **“Tăng queueSize sẽ không bao giờ drop.”** Queue hữu hạn, có shutdown và sink failure; queue lớn còn làm tăng heap.
- **“Log lỗi ở mọi tầng giúp điều tra hơn.”** Stack trace lặp làm tăng volume, phình search và nguy cơ lộ bí mật.
- **“Bật DEBUG thì nên dump nguyên payload.”** Body/header có PII, cookies và secrets; luôn dùng allowlist.
- **“Regex ở collector xóa hết secrets.”** Secrets có thể đã đi qua stdout/file và có nhiều biểu diễn lồng nhau.
- **“Hash email là vô danh.”** Dữ liệu có thể vẫn tái nhận diện; đánh giá theo rủi ro và chính sách.
- **“Không thấy log nghĩa là sự kiện không xảy ra.”** Có thể bị level filter, sampling, drop, sink lỗi hoặc đang trễ ingest.
- **“Ứng dụng đã enqueue là log được lưu rồi.”** Producer, queue, sink, collector và backend là nhiều giai đoạn.
- **“Ghi file đồng bộ có nghĩa dữ liệu chắc chắn durable.”** OS cache/fsync, filesystem và rotation quyết định khác nhau.
- **“RequestId tốt cho metric label.”** Đây thường là cardinality quá cao.
- **“Xóa log ở dashboard giải quyết secret leak.”** Cần xem các bản sao và revoke/rotate secret nếu phù hợp.
- **“Bật TRACE khi incident rồi quên tắt cũng không sao.”** Chi phí và rủi ro dữ liệu kéo dài; cần thời hạn và quyền bật.

## 12. Checklist production

**Trước khi phát hành:**
1. Đặt schema/allowlist event theo level, service, event, errorCode, outcome, duration và correlation/trace ID.
2. Kiểm thử không có password/token/PII trong message, DTO, headers, MDC, exception và debug libraries.
3. Tính ngân sách event/s, bytes/s, event size và retention cho traffic dự kiến và tình huống lỗi bùng nổ.
4. Dùng metric và sampling/rate limit phù hợp cho hot paths, không xóa audit/security events tùy tiện.
5. Kiểm tra effective logging level, chi phí eager argument formatting và giới hạn size của log record.
6. Ghi rõ appender synchronous/async, queue capacity, block/drop, fallback, retry, shutdown flush và metrics phản ánh loss.
7. Kiểm tra disk/pipe/collector quotas, quyền đọc, encryption và rotation/retention; tránh shared disk exhaustion.

**Khi chứng minh cải thiện hiệu năng:**
1. Giữ nguyên workload, JDK, backend, event size và sink để so baseline.
2. Đo p95/p99 request, throughput, CPU/GC, log call/enqueue latency, queue occupancy và dropped events.
3. Giả lập collector chậm/disk đầy/queue full/kill ở môi trường thử nghiệm, xác nhận behavior khi lỗi.
4. So số event emitted với written và backend ingested; kiểm tra các lỗi có correlation ID còn tìm được.
5. Ghi quyết định trade-off: trường hợp nào ưu tiên availability, trường hợp nào cần audit durability, ai phê duyệt điều chỉnh.
6. Giới hạn thời gian DEBUG/TRACE tăng cường và đánh giá lại secrets/cost sau thay đổi.

**Ghi nhớ:** giảm log **ở nguồn**, bảo vệ secret **trước serialization**, theo dõi **events/s và bytes/s**, đo **chi phí đồng bộ trên critical path**, và coi **async queue luôn hữu hạn**. Một chiến lược logging tốt phải vừa giúp điều tra sự cố, vừa không trở thành nguyên nhân của sự cố.

### Tài liệu tham khảo

- OWASP, Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- Logback, AsyncAppender manual: https://logback.qos.ch/manual/appenders-async-sift.html
- OpenTelemetry, Logs Data Model: https://opentelemetry.io/docs/specs/otel/logs/data-model/
- Java SE 17, PrintStream API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html

Hành vi thực tế của appender và chính sách drop phụ thuộc phiên bản thư viện, sink và runtime. Cần đối chiếu cấu hình triển khai thật với metrics, không coi các ví dụ minh họa là cấu hình bắt buộc.