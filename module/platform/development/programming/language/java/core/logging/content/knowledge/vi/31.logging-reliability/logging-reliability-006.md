# Đích ghi không khả dụng: thiết kế logging đáng tin cậy trong Java

## 1. Vấn đề: ứng dụng vẫn chạy, nhưng log có thể không đến nơi

**Đích ghi log (logging sink/destination)** là nơi nhận sự kiện log: console (stdout/stderr), tệp trên ổ đĩa, hệ thống thu thập log qua mạng, dịch vụ tập trung hoặc một appender do ứng dụng tự triển khai. **Đích ghi không khả dụng** nghĩa là tại một thời điểm, nơi nhận đó không thể tiếp nhận hoặc lưu sự kiện như mong đợi.

Ví dụ thường gặp:

- Ổ đĩa đầy, thư mục log không tồn tại, quyền ghi bị từ chối hoặc filesystem chuyển sang trạng thái chỉ đọc.
- Tệp log đang bị khóa hoặc thao tác rotation/reopen gặp lỗi; container không có volume/đường dẫn như cấu hình.
- Log collector, syslog server, TCP endpoint hoặc logging gateway bị mất mạng, lỗi DNS, timeout, quá tải hoặc từ chối kết nối.
- stdout/stderr bị đóng, pipeline thu log của container trục trặc hoặc tiến trình ghi quá nhanh khiến pipe/agent phía sau không theo kịp.
- Hàng đợi của async appender đầy trong khi worker/sink không tiêu thụ được, dẫn đến block hoặc drop tùy cấu hình.

Tình huống minh họa:

```text
HTTP request
    |
    v
logger.info("Payment accepted")
    |
    v
Async queue --------> Logging worker --------> File / collector
                                           X   destination unavailable
    |
    v
Ứng dụng có thể tiếp tục xử lý request,
nhưng sự kiện log chưa chắc được lưu.
```

**Nguyên tắc đầu tiên:** lệnh `logger.info(...)` chạy xong không đồng nghĩa log đã được ghi bền vững. Thậm chí appender đã được gọi cũng chưa chứng minh collector ở xa đã nhận và lưu sự kiện. Nếu hệ thống yêu cầu nhật ký kiểm toán không được mất, cần một hợp đồng lưu trữ và xác nhận riêng, thay vì mặc định framework logging thông thường bảo đảm điều đó.

## 2. Phân biệt các mức độ “đã ghi thành công”

Một sự kiện có thể đi qua nhiều điểm:

| Trạng thái | Ý nghĩa | Điều chưa được bảo đảm |
| --- | --- | --- |
| `Created` | Ứng dụng đã tạo sự kiện hoặc gọi API logging | Logger level/filter có thể loại bỏ ngay |
| `Accepted` | Backend chấp nhận event theo chính sách của nó | Event có thể chỉ nằm trong bộ nhớ |
| `Queued` | Event nằm trong queue của async appender | Worker chưa xử lý; crash có thể làm mất |
| `Appended` | Appender đã xử lý hoặc ghi vào buffer/stream | Dữ liệu chưa chắc đã đến file/collector bền vững |
| `Sent` | Client đã gửi bytes qua socket hoặc API | Gửi thành công không đồng nghĩa phía xa đã lưu |
| `Acknowledged` | Phía nhận xác nhận theo giao thức | Phạm vi xác nhận phụ thuộc giao thức/nhà cung cấp |
| `Durable` | Dữ liệu đã được lưu với độ bền theo hợp đồng | Cần xác định replication, fsync, retention, khôi phục sau crash |

Không phải framework nào cũng phơi bày tất cả các trạng thái trên. Nhiều logger chỉ cung cấp API ghi một chiều, không có `Future` hoặc acknowledgment cho từng event. Vì vậy:

- **Không mất log** cần nói rõ trong phạm vi nào: không drop khi queue đầy, không mất khi graceful shutdown, hay tồn tại sau process/host crash.
- **At-most-once**: không gửi lại nên ít trùng, nhưng lỗi có thể làm mất event.
- **At-least-once**: có retry/replay cho đến khi nhận xác nhận, có thể tạo event trùng; phải dùng event ID/deduplication nếu cần.
- **Exactly-once** trên toàn pipeline là yêu cầu mạnh, thường cần cơ chế giao dịch và định danh riêng; không xuất hiện chỉ vì bật async logger hoặc retry.

Với log chẩn đoán thông thường, hệ thống có thể chọn **best effort** và ưu tiên không chặn request. Với audit có ràng buộc pháp lý/tài chính, chính sách có thể yêu cầu ghi giao dịch vào nơi lưu bền vững trước khi xác nhận nghiệp vụ; khi ấy hãy thiết kế cơ chế audit có trạng thái/ack rõ ràng.

## 3. Những nguyên nhân và dấu hiệu cần phân biệt

| Đích | Lỗi thường gặp | Dấu hiệu | Cách chẩn đoán |
| --- | --- | --- | --- |
| File | Hết dung lượng, thiếu quyền, sai đường dẫn, read-only filesystem | Appender báo lỗi mở/ghi file, file ngừng tăng | Kiểm tra quyền, mount, quota, trạng thái filesystem và Logback status |
| Console | Pipe bị đóng, consumer chậm hoặc stdout bị chuyển hướng | Thiếu log ở container/terminal, tiến trình ghi chậm | Kiểm tra runtime/container logging driver và collector |
| Network collector | Mất kết nối, DNS, TLS, timeout, server 429/5xx | Retry tăng, backlog lớn, lượng log ở backend giảm | Metric của transport, trạng thái kết nối, ack/HTTP response |
| Async queue | Sink chậm hơn producer, queue đầy | Producer block, event bị drop hoặc độ trễ log tăng | Queue depth, discarded count, tốc độ enqueue/dequeue |
| Encoder/formatter | Serialization lỗi, cấu hình pattern không hợp lệ, trường dữ liệu đặc biệt | Sự kiện không render được hoặc appender báo error | Test encoder, status/error handler, payload mẫu |
| Rotation/restart | Đổi tên file, đóng/mở handle, shutdown chưa drain | Mất đoạn log sát thời điểm restart, file cũ/mới lệch | Kiểm tra lifecycle, rolling policy và đồng bộ shutdown |
| Collector pipeline | Agent vẫn nhận nhưng ingest/index lỗi | Log có trên node nhưng không thấy khi truy vấn | Metric agent, DLQ/spool, thời gian ingest và sampling |

**Đừng chẩn đoán mọi trường hợp “không tìm thấy log” thành lỗi I/O.** Nguyên nhân cũng có thể là logger level, filter, sai tên service, sai index/time range, timezone, parser, sampling, MDC thiếu trường truy vấn hoặc event bị loại theo chính sách cấu hình.

### Sự khác nhau giữa mất kết nối tạm thời và lỗi kéo dài

- **Transient:** mất mạng vài giây, collector restart, rate limit ngắn; retry có backoff và buffer giới hạn có thể hữu ích.
- **Permanent hoặc lâu dài:** đường dẫn sai, credential hết hạn, volume đầy, endpoint bị thay đổi; retry liên tục mỗi event chỉ làm tăng CPU, log lỗi lặp và áp lực hệ thống. Cần báo động, giảm tải hoặc chuyển tuyến một cách có kiểm soát.
- **Partial failure:** file sink lỗi nhưng console còn hoạt động; appender A hỏng nhưng B vẫn nhận; collector chấp nhận một phần batch. Cần quan sát riêng từng sink và từng bước xác nhận.

## 4. Ứng xử của logging đồng bộ và bất đồng bộ khi sink lỗi

### 4.1. Logging đồng bộ

Với appender đồng bộ, thao tác của sink có thể chạy trên thread nghiệp vụ. Nếu sink rất chậm, request có thể bị tăng latency hoặc đứng chờ ở một lock/IO. Nếu sink ném exception, phản ứng phụ thuộc backend và cách appender triển khai.

**Lưu ý với SLF4J + Logback:** không nên viết code nghiệp vụ mặc định rằng `logger.error(...)` sẽ ném một `IOException` để ta `catch`. Nhiều appender báo lỗi ghi qua hệ thống **status/error handler nội bộ** thay vì truyền checked exception qua facade. Cần kiểm tra loại appender, phiên bản và cấu hình thực tế.

### 4.2. Logging bất đồng bộ

Với Logback `AsyncAppender`, producer đưa event vào queue và worker gửi đến appender đích. Trong quá tải:

- `queueSize` đặt giới hạn hàng đợi nội bộ.
- `discardingThreshold` điều khiển việc loại những sự kiện có mức ưu tiên thấp (thông thường TRACE/DEBUG/INFO) khi queue gần đầy; đặt `0` tắt cơ chế discard theo ngưỡng này.
- `neverBlock=false` khiến producer **có thể phải chờ** khi queue đầy; `neverBlock=true` dùng cách enqueue không chặn và có thể **bỏ sự kiện** khi hết chỗ.
- `maxFlushTime` điều khiển thời gian chờ worker xả queue khi dừng; nếu timeout kết thúc trước khi drain xong, có thể còn event chưa xử lý.

Đây là **cấu hình của Logback AsyncAppender**, không phải quy tắc chung cho mọi backend/phiên bản. Các lựa chọn của Log4j2 AsyncLogger, async appender và logging agent mạng có thể khác.

Quan trọng hơn: **queue trong bộ nhớ không tự biến thành nơi lưu bền vững**. Khi JVM crash, OOM hoặc host restart đột ngột, event còn trong queue có thể mất. Nếu appender đích ghi thất bại nhưng worker vẫn lấy event khỏi queue, việc queue đã “drain” cũng **không chứng minh** event đã đến nơi.

### 4.3. Tác động đến nghiệp vụ

Một chính sách có thể ưu tiên:

1. **Availability:** request tiếp tục, log được ghi theo best effort; chấp nhận khả năng mất một phần log.
2. **Backpressure:** producer chờ một thời gian có giới hạn để tăng cơ hội giao log; chấp nhận tăng latency.
3. **Durability:** ghi tạm xuống spool bền vững và chỉ xóa sau khi nhận ack; chấp nhận thêm I/O, phức tạp và phải xử lý trùng sự kiện.
4. **Fail closed:** từ chối một thao tác nghiệp vụ khi bản ghi audit bắt buộc không thể được lưu/xác nhận; chỉ chọn khi yêu cầu nghiệp vụ/pháp lý quy định như vậy.

Không có một lựa chọn đúng cho mọi loại log. Log debug và sự kiện audit thanh toán thường cần hợp đồng đáng tin cậy khác nhau.

## 5. Các chiến lược khi đích ghi không khả dụng

### 5.1. Dùng một đường ghi độc lập dự phòng

Ví dụ ứng dụng đang ghi file và đồng thời ghi stdout để platform thu thập. Khi file lỗi, stdout **có thể** vẫn được ghi nếu appender này còn hoạt động. Đây là hai kênh song song, **không mặc nhiên là tự động failover**: khi cả hai tốt, một event có thể xuất hiện ở cả hai sink. Muốn “chỉ ghi B khi A lỗi” phải có cơ chế giám sát và chuyển tuyến rõ ràng.

Đường dự phòng nên độc lập tương đối với lỗi chính. Ví dụ nếu file log bị đầy vì cả phân vùng chứa ứng dụng đầy, một spool khác trên **cùng phân vùng** có thể cũng thất bại. stdout cũng có thể bị nghẽn nếu runtime log driver gặp lỗi.

### 5.2. Buffer có giới hạn và backpressure có chủ đích

Buffer giúp hấp thụ outage ngắn, nhưng luôn phải có **capacity** và chính sách khi đầy:

| Chính sách | Lợi ích | Đánh đổi |
| --- | --- | --- |
| Chặn producer | Có thể giảm drop khi sự cố ngắn | Tăng tail latency, có nguy cơ lan sự cố sang request |
| Drop event ít quan trọng | Bảo vệ đường xử lý nghiệp vụ | Mất dữ liệu chẩn đoán, cần metric drop |
| Drop oldest/newest | Giới hạn bộ nhớ | Thay đổi khoảng thời gian log còn được giữ |
| Spill sang disk spool | Có thể chịu outage dài hơn memory queue | Cần dung lượng, cleanup, replay, bảo vệ dữ liệu |
| Sampling/rate limit | Giảm log lặp | Không giữ từng sự kiện; phải định nghĩa ngoại lệ |

**Không dùng queue vô hạn** để “không mất log”: với sink hỏng kéo dài, bộ nhớ sẽ tăng cho đến khi ứng dụng thiếu RAM hoặc sập. Mọi buffer hữu hạn rốt cuộc cần quyết định **block, drop, chuyển sink hoặc từ chối tác vụ**.

### 5.3. Retry và phục hồi

Với collector từ xa, retry chỉ có ý nghĩa khi lỗi có khả năng hồi phục. Nên có:

- Timeout cho kết nối và gửi batch, không chờ vô hạn.
- Exponential backoff có giới hạn, thêm jitter để nhiều instance không cùng retry ồ ạt.
- Giới hạn số lần hoặc thời gian retry, circuit breaker và kiểm tra phục hồi có kiểm soát.
- Khả năng gửi lại **đúng batch chưa được xác nhận**; không coi network write thành công là ack bền vững nếu protocol không nói vậy.
- Event ID và deduplication khi có khả năng trạng thái mơ hồ: collector có thể đã nhận rồi nhưng response/ack bị mất.
- Metric retry, số event tồn, thời gian chờ lâu nhất và số event cuối cùng bị bỏ.

Retry cũng có thể tạo **log lỗi của chính pipeline logging**. Không để logger bên trong transport lỗi lại đi qua đúng transport đang lỗi gây đệ quy vô hạn. Dùng status listener, metric hoặc kênh khẩn cấp độc lập và giới hạn số cảnh báo.

### 5.4. Spool bền vững và replay

Nếu yêu cầu cần chịu outage dài, có thể dùng agent hoặc pipeline hỗ trợ **disk buffering/spooling**:

```text
Application -> stdout / local agent -> bounded disk spool
                                        |
                                        v
                          retry + remote acknowledgment
                                        |
                                        v
                                    Collector
```

Thiết kế này cần trả lời rõ: ghi vào spool đã fsync hay chỉ ở page cache? Khi nào xóa bản ghi? Nếu crash giữa gửi và ack thì replay gây trùng ra sao? Dung lượng/spool đầy xử lý thế nào? Dữ liệu log trong spool có phải mã hóa và giới hạn retention hay không?

Spool không bảo đảm vô hạn: ổ đĩa vẫn có thể đầy, hỏng hoặc bị xóa. Vì vậy hãy đặt giới hạn và monitor dung lượng; test khôi phục sau restart thay vì chỉ test retry khi process còn sống.

## 6. Ví dụ Java 17: mô phỏng đích ghi lỗi và chuyển sang dự phòng

Để hiểu ranh giới lỗi, ví dụ này sử dụng **một pipeline ghi log thu nhỏ tự xây để minh họa cơ chế**, không giả định SLF4J/Logback tự động làm đúng như vậy. `PrimarySink` mô phỏng file bị lỗi I/O một cách tất định; `EmergencySink` ghi vào stdout. Sau lần thất bại đầu tiên, pipeline chuyển sang chế độ degraded và không lặp lại thao tác primary trên mỗi event.

Tạo tệp `SinkFailureDemo.java`:

```java
import java.io.IOException;

public class SinkFailureDemo {

    @FunctionalInterface
    interface PrimarySink {
        void write(String event) throws IOException;
    }

    @FunctionalInterface
    interface EmergencySink {
        void write(String event);
    }

    static final class ResilientWriter {
        private final PrimarySink primary;
        private final EmergencySink emergency;
        private boolean degraded;

        ResilientWriter(PrimarySink primary, EmergencySink emergency) {
            this.primary = primary;
            this.emergency = emergency;
        }

        // synchronized giữ thứ tự và trạng thái khi nhiều thread cùng gọi.
        synchronized void log(String event) {
            if (!degraded) {
                try {
                    primary.write(event);
                    return;
                } catch (IOException failure) {
                    degraded = true;
                    emergency.write("ALERT primary unavailable: "
                            + failure.getMessage());
                }
            }

            emergency.write("FALLBACK " + event);
        }
    }

    public static void main(String[] args) {
        PrimarySink unavailableDisk = event -> {
            throw new IOException("simulated disk full");
        };
        EmergencySink console = System.out::println;

        ResilientWriter writer =
                new ResilientWriter(unavailableDisk, console);

        writer.log("INFO requestId=r-7 started");
        writer.log("ERROR requestId=r-7 failed");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac SinkFailureDemo.java
java SinkFailureDemo
```

**Stdout chính xác:**

```text
ALERT primary unavailable: simulated disk full
FALLBACK INFO requestId=r-7 started
FALLBACK ERROR requestId=r-7 failed
```

Điều có thể rút ra:

1. Thao tác gửi event đầu tiên tới primary gặp `IOException`. Event này **chưa được primary lưu**, vì vậy pipeline thử ghi sang emergency.
2. Cờ `degraded` khiến lần log tiếp theo không liên tục thử một đích đã được xác định là hỏng. Thông báo cảnh báo chỉ phát một lần.
3. Từ khóa `synchronized` giữ thứ tự quan sát theo thứ tự thread lấy được lock trong ví dụ, đồng thời bảo vệ trạng thái `degraded`. Điều này **không bảo đảm thứ tự nghiệp vụ toàn cục** giữa những request đồng thời.
4. Không có retry/reopen tự động; một hệ thống thật cần cơ chế health probe, phục hồi và tránh ở lại chế độ degraded vĩnh viễn.
5. stdout là kênh minh họa để output dễ kiểm tra. Bản thân stdout cũng có thể bị nghẽn hoặc lỗi, và `PrintStream` có cách báo lỗi riêng; việc gọi `println` không phải ack bền vững.
6. Không dùng nguyên `ResilientWriter` làm logging framework production: lệnh ghi dự phòng đang chạy trong lock và có thể block request, không giới hạn kích thước record, chưa có metrics, circuit breaker phục hồi, chiến lược multi-sink hay xử lý lỗi của emergency. Mục đích là làm rõ **phát hiện → chuyển tuyến → tiếp tục log** bằng ví dụ có đầu ra tất định.

Nếu ứng dụng dùng SLF4J, hãy cấu hình backend/appender hoặc agent logging để xử lý sự cố và giám sát ở tầng phù hợp. Không bọc mọi `logger.info(...)` bằng `try/catch (IOException)` vì facade logging không cung cấp checked exception I/O theo cách đó.

## 7. Logback: cấu hình nhiều đích và quan sát lỗi

Ví dụ tối thiểu của `logback.xml` cho ứng dụng có SLF4J + Logback:

```xml
<configuration>
    <statusListener
        class="ch.qos.logback.core.status.OnConsoleStatusListener"/>

    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/application.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

Ví dụ này gửi một event tới **cả hai** appender nếu chúng hoạt động và vượt qua filter; nó **không phải bộ chuyển tuyến có điều kiện**. Khi file không mở/ghi được, Logback có thể báo lỗi qua status system trong khi appender console vẫn hoạt động. Không nên dựa vào status in console làm cơ chế cảnh báo duy nhất nếu console/collector cũng có thể lỗi.

Hạn chế của cấu hình tối thiểu:

- `FileAppender` trong ví dụ **không tự xoay vòng file**. Production cần chiến lược rotation, giới hạn dung lượng và retention phù hợp (thường dùng `RollingFileAppender`).
- Đường dẫn `logs/application.log` là tương đối so với working directory và phụ thuộc quyền ghi/volume khi triển khai.
- Hai appender hoạt động tốt sẽ tạo hai bản sao ở hai sink; nếu hệ thống thu cả file và stdout vào cùng collector, có thể gây duplicate, tốn phí và đếm sai nếu không deduplicate.
- Appender có thể báo lỗi lúc startup hoặc runtime khác nhau tùy loại và phiên bản. Không nên coi sự hiện diện của `FILE` trong XML là bằng chứng file thật đang được cập nhật.
- Cần kiểm tra backend có một provider SLF4J duy nhất, tên file cấu hình thực sự được nạp và các override theo profile.

Đối với ứng dụng Spring Boot, `logback-spring.xml` hỗ trợ cấu hình dựa trên profile; nếu dùng `<springProfile>`, đó là phần mở rộng của Spring Boot chứ không phải XML Logback thuần. Trước khi thêm appender file/remote, cân nhắc nền tảng triển khai đã có collector cho stdout hay chưa.

### Khi kết hợp AsyncAppender

Nếu bọc một appender bằng `AsyncAppender`, appender đích có thể thực hiện I/O ở thread worker. Đó là giải pháp hạn chế thời gian chờ của producer **cho tới khi queue đầy**, không phải giải pháp tự lưu bền vững hoặc tự chuyển sang đích khác. Nếu queue đầy hoặc async worker hỏng, vẫn phải có chính sách block/drop có giám sát và kiểm tra shutdown.

Một số bộ thu tập trung có client hoặc agent hỗ trợ queue/disk spool/retry độc lập. Cần hiểu ranh giới nơi nào nhận acknowledgment và cơ chế đó thực sự được bật trong cấu hình hiện tại.

## 8. Khôi phục sau khi đích ghi hoạt động lại

Giả sử collector bị ngắt 30 giây rồi hoạt động lại. Một pipeline có buffer/retry cần chuyển từ **degraded** về **healthy** mà không xóa hoặc gửi trùng event một cách mù quáng.

Quy trình khái niệm:

1. Phát hiện endpoint có thể truy cập lại qua health probe hoặc lần gửi thử **có giới hạn**.
2. Mở lại kết nối/file handle theo quy tắc an toàn; không chặn tất cả request trong lúc kiểm tra.
3. Gửi các event còn trong spool theo thứ tự/ưu tiên được định nghĩa. Nếu gửi theo batch, giữ metadata mỗi batch và trạng thái ack.
4. Chỉ xóa record đã đạt **mốc ack** phù hợp. Nếu trạng thái gửi mơ hồ, có thể phải replay và deduplicate bằng `eventId`.
5. Ghi nhận thời gian gián đoạn, lượng backlog, số event mất/được replay và thời điểm phục hồi.
6. Trở lại chính sách thường sau khi queue/spool ổn định; tránh nhiều instance cùng replay bùng nổ.

**Thứ tự xử lý** không nên được hứa quá rộng: một queue đơn producer FIFO thường dễ hiểu, nhưng nhiều producer, nhiều worker, batch retry và mạng có thể làm event đến collector không cùng thứ tự tạo. Khi cần tái dựng chuỗi sự kiện, dùng timestamp đáng tin trong giới hạn đồng hồ, correlation ID và sequence/event ID có phạm vi rõ.

Với file sink, khôi phục có thể cần mở lại file do log rotation hoặc mount thay đổi. Cần phối hợp với cơ chế rolling/reopen của backend; không tự ý đóng/mở handle từ một thread bất kỳ mà không hiểu lifecycle.

## 9. Quan sát khi chính hệ thống logging bị lỗi

Rủi ro lớn là **không thể dùng đường log đang hỏng để báo rằng nó hỏng**. Vì vậy, khả năng quan sát phải dựa thêm vào kênh tương đối độc lập:

| Chỉ số/tín hiệu | Giá trị |
| --- | --- |
| `log_appender_errors_total` | Số lần appender/sink gặp lỗi |
| `log_dropped_events_total` | Số event bị loại theo policy |
| `log_retry_attempts_total` | Mức độ retry, dấu hiệu outage kéo dài |
| `log_queue_depth` / capacity | Backlog và nguy cơ block/drop |
| `log_spool_bytes` / quota | Dung lượng dự phòng còn lại |
| `log_last_successful_delivery_age` | Bao lâu rồi sink chưa báo giao thành công |
| `log_delivery_latency` | Tốc độ xử lý/drain so với tạo log |
| Synthetic canary/probe | Kiểm tra event thử đã thực sự xuất hiện ở collector |

Đây là **tên metric minh họa**, không phải những metric mặc định có sẵn của Logback. Cần instrument hoặc dùng metric do agent/backend cung cấp, tùy hệ thống. Cảnh báo nên theo **thời gian outage, tốc độ tăng backlog và tỷ lệ drop**, không chỉ số lần IOException thô.

Nếu triển khai trong Kubernetes/container, metric từ log agent/node cũng quan trọng như metric trong ứng dụng. Ứng dụng có thể ghi stdout thành công mà collector upstream bị lỗi ingest. Để biết end-to-end, cần quan sát phần cuối pipeline.

### Không tạo vòng lặp logging sự cố

Ví dụ không nên:

```text
RemoteAppender gửi lỗi -> logger.error("RemoteAppender failed")
    -> RemoteAppender lại nhận sự kiện đó -> tiếp tục lỗi -> ...
```

Cần hạn chế số cảnh báo, dùng backend status channel hoặc metric độc lập. Nếu fallback cũng lỗi, phải có chiến lược cuối cùng rõ ràng và tuyệt đối không bỏ qua yêu cầu bảo đảm audit nếu hợp đồng nghiệp vụ không cho phép.

## 10. Kiểm thử lỗi đích ghi (fault injection)

Kiểm thử chỉ thấy log bình thường xuất hiện là chưa đủ. Cần chủ động mô phỏng sink ngừng hoạt động, có thể lặp lại và không gây tác động đến tài nguyên production.

### 10.1. Kiểm thử đơn vị với sink giả lập

Dựa trên mô hình `ResilientWriter` ở phần 6, có thể thay `PrimarySink` bằng fake đếm số lời gọi và ném `IOException` tại lần được chọn. Các assertion quan trọng:

- Event phát ra trước lỗi đến primary.
- Event tại lần primary ném exception được chuyển sang dự phòng **một lần theo chính sách ví dụ**.
- Sau chuyển degraded, các event mới không tiếp tục gọi primary.
- Cảnh báo lỗi chính không phát lặp cho từng event.
- Nếu có cơ chế reset/retry, chỉ trở lại primary sau kiểm tra hồi phục được định nghĩa.

Test nên dùng `List` hoặc `BlockingQueue` để thu event và so sánh nội dung, không phụ thuộc vào việc file có thật hay thời gian ngẫu nhiên. Với multi-thread, dùng bộ thu thread-safe và assertion theo tập/ID thay vì thứ tự xen kẽ scheduler.

### 10.2. Integration test file appender

- Tạo vùng file tạm dành riêng cho test; không can thiệp log thật của máy.
- Mô phỏng lỗi quyền, đường dẫn bất hợp lệ hoặc thay sink bằng `OutputStream` ném `IOException`. Ví dụ, tạo **một file thường** rồi thử dùng nó như thư mục chứa log để ép lỗi mở file trong môi trường phù hợp.
- Khởi động cấu hình Logback thật, kiểm tra status/error handler có ghi nhận lỗi và appender độc lập còn nhận sự kiện.
- Khôi phục quyền/đường dẫn, kiểm tra file appender có tự phục hồi hay phải khởi tạo lại theo backend đã chọn.
- Cleanup logger context, appender, file tạm trong `finally`; đừng sửa cấu hình root logger toàn bộ test suite rồi để trạng thái rò sang test khác.

Không dùng cách làm đầy phân vùng hệ thống để tạo lỗi `ENOSPC` trong CI. Để mô phỏng write failure, dùng fake sink, filesystem quota/container cô lập hoặc cơ chế fault injection có kiểm soát.

### 10.3. Integration test collector qua mạng

Dùng collector test hoặc proxy điều khiển được, rồi:

1. Gửi một số event có ID duy nhất khi collector đang hoạt động và xác nhận đã nhận.
2. Ngắt kết nối hoặc trả 429/503 có kiểm soát, theo dõi retry, queue và latency producer.
3. Giữ outage đủ để kiểm tra ngưỡng buffer; xác nhận chính sách block/drop/spool **đúng cấu hình**.
4. Cho collector hoạt động lại, chờ drain với timeout rõ ràng rồi so sánh event IDs và số bản sao.
5. Restart agent/process trong lúc còn backlog (nếu yêu cầu durability) để kiểm tra replay.
6. Đọc metric/log trạng thái từ kênh độc lập; không suy luận “không có lỗi” chỉ vì logger không ném exception.

Nếu protocol không có ack cho từng event, test chỉ kết luận theo mức quan sát được. Không tuyên bố end-to-end exactly-once từ việc mọi event của một lần chạy thử đã xuất hiện.

### 10.4. Kiểm thử shutdown và queue đầy

Đối với async appender, kiểm tra riêng các trường hợp:

- Worker đang tiêu thụ bình thường, gọi graceful stop và quan sát event đã tới sink.
- Worker bị chặn ở sink, queue đầy, producer bị block hoặc drop theo cấu hình. Dùng `CountDownLatch` điều khiển thời điểm; không dùng `Thread.sleep` như bằng chứng chắc chắn.
- Ngắt quá trình bất ngờ: event còn trong memory queue có thể mất. Đây là thử nghiệm độ bền, phải chạy trong môi trường cô lập với quy trình cleanup.
- Đối với log audit bắt buộc, kiểm tra ứng dụng không trả lời “nghiệp vụ thành công” khi trạng thái lưu audit chưa đạt tiêu chí đã cam kết.

Đặt timeout hữu hạn cho test, giải phóng latch ở `finally` để tránh deadlock, và dọn tài nguyên sau từng case.

## 11. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách làm phù hợp |
| --- | --- | --- |
| “`logger.info` không throw nên log đã lưu” | Backend có thể nuốt/report I/O error, queue có thể chưa drain | Theo dõi status/metric và kiểm tra sink thực tế |
| Dùng queue vô hạn để tránh mất log | Outage dài gây OOM | Bounded queue, policy khi đầy, cảnh báo |
| Ghi dự phòng vào cùng ổ đĩa đã đầy | Hai sink có thể cùng lỗi | Chọn miền lỗi độc lập, test failover |
| Retry liên tục không backoff | Khuếch đại sự cố, lãng phí CPU/network | Exponential backoff, jitter, circuit breaker |
| Không có event ID khi replay | Sự kiện có thể trùng sau ack timeout | Deduplicate theo ID khi cần |
| Mặc định async logging là durable | Memory queue mất khi crash | Spool bền vững nếu cần, test restart |
| Log lỗi của logger vào chính logger lỗi | Đệ quy, nghẽn hoặc spam | Kênh status/metric độc lập, rate limit |
| Thấy file tồn tại là cho rằng file đang được ghi | File có thể là bản cũ, appender không hoạt động | Probe actual write và kiểm tra modified/collector |
| Bỏ qua stdout vì đã có file | File có thể hỏng, nhưng console là tuyến thay thế khả thi | Thiết kế rõ multi-sink và tránh duplicate không chủ ý |
| Đặt mất log audit ngang với mất DEBUG | Mức độ rủi ro khác nhau | Tách pipeline/hợp đồng durability và chính sách fail closed |
| Chỉ xem lỗi ở ứng dụng | Agent/collector ingest có thể hỏng sau stdout | Quan sát pipeline end-to-end |
| Kiểm thử bằng sleep cố định | Async worker/remote collector không có thời hạn chắc chắn | Barrier, ack, poll với timeout, event ID |

## 12. Quy trình xử lý sự cố thực tế

Khi hệ thống báo thiếu log, có thể đi theo thứ tự sau:

1. **Xác minh sự kiện có được tạo hay không:** log level, filter, điều kiện code, logger name, sampling.
2. **Kiểm tra sink gần ứng dụng nhất:** file, stdout hoặc appender; đối chiếu event ID và thời điểm.
3. **Kiểm tra trạng thái lỗi và backlog:** status manager, metric queue, drop, retry, connection.
4. **Khoanh vùng vị trí mất dữ liệu:** ứng dụng → agent → transport → collector → storage/index/query.
5. **Giảm tác động đến nghiệp vụ:** nếu producer đang bị block, đánh giá chính sách timeout/drop/failover và yêu cầu audit.
6. **Sửa nguyên nhân gốc:** quyền file, quota, cấu hình mount, DNS/TLS, token, collector capacity, rotation hoặc encoding.
7. **Phục hồi có kiểm soát:** nối lại sink, replay backlog nếu có, kiểm tra event trùng và dung lượng sau hồi phục.
8. **Chốt dữ liệu mất thực tế:** ghi rõ khoảng thời gian, loại event, số lượng ước tính có căn cứ và giới hạn của hệ thống đo.
9. **Ngăn tái diễn:** alert độc lập, test outage định kỳ, giới hạn queue/spool, hướng dẫn ứng phó.

Nếu **không có ack hoặc số đếm cuối pipeline**, chỉ có thể ước tính phần đã mất; không khẳng định đã khôi phục 100% dựa vào việc sau sửa lỗi ta lại thấy log mới.

## 13. Checklist thiết kế và vận hành

- [ ] Phân loại rõ log chẩn đoán, vận hành, bảo mật và audit theo mức độ cần giữ.
- [ ] Xác định ranh giới “đã giao thành công”: accepted, queued, appended, acknowledged hay durable.
- [ ] Đặt timeout, queue/buffer capacity, discard/backpressure policy và khả năng fallback có kiểm soát.
- [ ] Biết sink thay thế có độc lập với kiểu lỗi chính hay không; tránh tạo trùng log không chủ ý.
- [ ] Ghi nhận failure, drop, retry, queue/spool depth và last successful delivery bằng metric/kênh độc lập.
- [ ] Thử outage ngắn, outage dài, đầy queue, mất quyền file, collector restart và graceful shutdown.
- [ ] Nếu có replay, có cơ chế event ID, ack, dedup và kiểm tra thứ tự/retention theo contract.
- [ ] Đảm bảo log/spool được bảo vệ khỏi rò token, mật khẩu và dữ liệu nhạy cảm.
- [ ] Có hướng dẫn khởi động lại appender/agent, xử lý backlog và đo khoảng trống log.
- [ ] Không để lỗi logger làm đổi kết quả nghiệp vụ trừ trường hợp audit bắt buộc đã được thiết kế rõ.

**Ghi nhớ:** khi đích ghi không khả dụng, câu hỏi quan trọng không chỉ là “ứng dụng có tiếp tục chạy không?” mà còn là **sự kiện đã đến mốc nào, event nào có thể mất, cơ chế nào phát hiện được và hệ thống phục hồi thế nào**. Hãy chọn chính sách rõ theo độ quan trọng của dữ liệu, thiết kế đường dự phòng và giới hạn queue, rồi kiểm chứng bằng fault injection thay vì tin rằng việc gọi logger thành công nghĩa là log đã được lưu.
