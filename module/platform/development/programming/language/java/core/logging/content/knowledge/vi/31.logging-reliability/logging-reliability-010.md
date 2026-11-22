# Mục tiêu độ tin cậy của hệ thống logging trong Java

## 1. Mục tiêu độ tin cậy logging là gì?

**Mục tiêu độ tin cậy logging** là mức chất lượng mà hệ thống cam kết hướng tới khi tạo, vận chuyển, lưu trữ và truy vấn sự kiện log. Một ứng dụng Java có thể hoạt động bình thường nhưng mất một phần log khi queue đầy, agent dừng, ổ đĩa hết chỗ hoặc backend từ chối ingest. Vì vậy, “logger không ném exception” hay “console có in ra một dòng” **không đủ để chứng minh log đã được lưu an toàn**.

Một mục tiêu hữu ích phải nói rõ **sự kiện nào**, **được coi là thành công tại đâu**, **trong thời gian bao lâu**, **trên khoảng đo nào**, và **điều gì được phép mất hoặc trùng**. Ví dụ:

> Trong cửa sổ 30 ngày, ít nhất 99,9% sự kiện ERROR đủ điều kiện do các service phát ra phải truy vấn được từ kho log tập trung trong 120 giây sau khi phát; mọi sự kiện audit bắt buộc phải đi qua tuyến lưu trữ có hợp đồng riêng.

Ví dụ này chỉ là **mục tiêu minh họa**, không phải khuyến nghị áp chung cho tất cả hệ thống. Các hệ thống thanh toán, bảo mật, audit hoặc điều tra sự cố có yêu cầu khác nhau về khả năng lưu trữ, tính toàn vẹn, chi phí và thời hạn lưu.

Ba thuật ngữ quan trọng:

- **SLI (Service Level Indicator):** chỉ số đo mức chất lượng thực tế, ví dụ tỷ lệ event được ingest thành công, độ trễ từ phát log tới lúc truy vấn được, tỷ lệ event thiếu hoặc số bản ghi trùng.
- **SLO (Service Level Objective):** ngưỡng mục tiêu cho SLI trong một cửa sổ đo, ví dụ 99,9% event đủ điều kiện phải tìm được trong 2 phút suốt 30 ngày.
- **SLA (Service Level Agreement):** cam kết mang tính thỏa thuận với bên nhận dịch vụ; có thể quy định hậu quả nếu không đáp ứng. Không tự gọi một SLO nội bộ là SLA.

Logging là một pipeline phân tán; độ tin cậy của từng chặng ảnh hưởng độ tin cậy end-to-end. Mục tiêu phải phản ánh điều mà người vận hành thực sự cần khi xảy ra lỗi: tìm được thông tin đúng, đủ, có thể đối chiếu theo request/trace và trong thời gian hữu ích.

## 2. Phân loại log trước khi đặt mục tiêu

Không phải mọi log phải có cùng mức đảm bảo. Phân nhóm giúp cân bằng hiệu năng, chi phí và rủi ro mất dữ liệu.

| Nhóm log | Ví dụ | Trọng tâm độ tin cậy |
| --- | --- | --- |
| Chẩn đoán thông thường | DEBUG/TRACE chi tiết, INFO lặp ở request thành công | Cho phép level filtering/sampling theo chính sách; không làm nghẽn ứng dụng |
| Lỗi vận hành | WARN/ERROR, timeout, exception, lỗi kết nối | Đủ dữ liệu để điều tra; latency ingest và tỉ lệ mất thấp, có cảnh báo |
| Sự kiện nghiệp vụ quan trọng | Đơn hàng được chấp nhận, thanh toán đổi trạng thái | Khả năng đối chiếu với nguồn nghiệp vụ; xác định tính đầy đủ, tránh đếm trùng |
| Audit/bảo mật/bằng chứng bắt buộc | Thay đổi quyền, hành động quản trị, giao dịch phải lưu | Hợp đồng lưu bền, chống sửa trái phép, phân quyền và retention riêng |

**Ghi log không thay thế hệ thống giao dịch.** Với sự kiện nghiệp vụ phải được bảo toàn, chỉ gọi `logger.info(...)` rồi tiếp tục xử lý thường không đủ để chứng minh đã ghi bền vững. Có thể cần transactional outbox, event stream hoặc kho audit có đảm bảo riêng và cơ chế reconciliation. Log quan sát cho vận hành và chứng từ bắt buộc cần được thiết kế theo trách nhiệm khác nhau.

Khi áp sampling, cần định nghĩa tập sự kiện **đủ điều kiện**. Ví dụ 10% INFO được lựa chọn có chủ đích thì 90% event còn lại không phải là “mất do lỗi pipeline”. Ngược lại, ERROR được yêu cầu giữ đầy đủ mà bị queue bỏ phải được tính là mất dữ liệu.

## 3. Những chiều đo độ tin cậy cốt lõi

| Chiều đo | SLI có thể sử dụng | Điều cần làm rõ |
| --- | --- | --- |
| **Delivery/completeness** | Tỷ lệ event đủ điều kiện đến đích và tìm được | Đếm từ source hay từ agent? Lọc có chủ đích đã loại khỏi denominator chưa? |
| **Timeliness** | Tỷ lệ event tìm được trong `T` giây; p95/p99 ingest lag | Đồng hồ source/backend có lệch không? Đo bằng timestamp nào? |
| **Integrity** | Tỷ lệ event có payload, severity, ID, checksum/fields hợp lệ | “Đã nhận” có nghĩa JSON/metadata được parse đúng chưa? |
| **Duplication** | Số bản ghi thừa trên mỗi event ID; tỷ lệ duplicate | Retry có thể gửi trùng; backend có hỗ trợ dedup không? |
| **Durability** | Event đã xác nhận được lưu sống sót qua crash/restart theo hợp đồng | Ack xác nhận nhận vào RAM, vào queue bền hay đã lưu cuối cùng? |
| **Availability** | Tỷ lệ thời gian pipeline có thể nhận log theo hợp đồng | Khả dụng tại cổng ingest khác với queryable ở backend |
| **Ordering** | Tỷ lệ cặp sự kiện vi phạm thứ tự được cam kết | Có cần thứ tự theo key/request/partition không? Không giả định thứ tự toàn cục |
| **Retention/retrievability** | Có truy vấn được event trong thời hạn bắt buộc không? | Lifecycle policy, quyền đọc, tier lưu trữ, phục hồi dữ liệu |

Các chiều đo này liên quan nhưng không tương đương. Một pipeline có 100% thành công HTTP tại Collector vẫn có thể có lỗi parse JSON sau đó, mất dữ liệu vì backend không đủ quota, hoặc lưu nhầm project/tenant. Do đó, **SLI end-to-end** nên phản ánh khả năng dùng dữ liệu ở đích cuối, cùng với các chỉ số thành phần để chẩn đoán.

## 4. Xây SLI/SLO có thể đo và kiểm chứng

Giả sử chính sách là giữ toàn bộ log ERROR có cấu trúc và không lấy mẫu. Có thể định nghĩa:

```text
eligible = số sự kiện ERROR thuộc phạm vi đã định,
           được nguồn ghi nhận là phải gửi trong cửa sổ đo

successful_120s = số event ID duy nhất trong tập eligible
                  truy vấn được ở backend trong vòng 120 giây

delivery_SLI_120s = successful_120s / eligible × 100%
```

Nếu `eligible = 1.000.000` và SLO là **99,9% trong 120 giây**, ít nhất **999.000** event phải truy vấn được đúng hạn; “ngân sách” còn lại là tối đa **1.000 event** đến chậm hoặc không xuất hiện trong phép đo đó. Đây là tính toán của **SLO timeliness/completeness kết hợp**; event đến sau 120 giây được coi là vi phạm SLO này dù cuối cùng vẫn tồn tại, nên cần thêm một SLI riêng nếu muốn phân biệt **trễ** với **mất vĩnh viễn**.

Các chi tiết bắt buộc khi thiết kế mẫu số và tử số:

1. **Đếm từ nguồn độc lập:** nếu chỉ lấy số event đã đến backend làm denominator, ta không nhìn thấy event mất trước Collector. Có thể dùng counter ở producer, counter export ở agent và đối chiếu ID trong môi trường kiểm chứng.
2. **Định nghĩa tập hợp rõ:** service, environment, severity, loại event, tỷ lệ sampling, cửa sổ đo và policy khi client không có kết nối.
3. **Dùng event ID ổn định:** request ID chỉ định danh request, trong khi một request có nhiều log; cần khóa riêng cho từng event nếu muốn chống trùng và đếm chính xác.
4. **Đo theo thời gian:** đánh dấu thời điểm tạo event và thời điểm backend có thể truy vấn; kiểm tra sai lệch đồng hồ và ingest delay. Khi cần kết luận chính xác, dùng phép đo có kiểm soát với đồng hồ đồng bộ hoặc tracing/probe thích hợp.
5. **Đếm trùng đúng cách:** không coi một event được retry 3 lần là 3 sự kiện tốt. Numerator của delivery SLI nên dùng **event ID duy nhất** nếu hợp đồng là giao mỗi sự kiện một lần về mặt logic.
6. **Theo dõi phần không biết:** nếu nguồn ghi nhận event bị crash trước khi tăng counter, phép đo có thể bỏ sót. Với audit nghiêm ngặt, cần một nguồn đối chiếu độc lập, ví dụ transaction/outbox record.

SLO cần có cửa sổ (ví dụ 7 hoặc 30 ngày), phạm vi môi trường và chính sách ngoại lệ được định nghĩa trước. Số mục tiêu cao không có nghĩa tự động có thể triển khai: cần capacity, bền vững của queue, retry và ngân sách tương ứng.

## 5. Delivery semantics: at-most-once, at-least-once, exactly-once

Một quyết định nền tảng là ứng dụng và pipeline **chấp nhận mất log hay chấp nhận trùng log**.

| Semantics | Điều có thể đảm bảo theo hợp đồng | Đánh đổi và cách dùng |
| --- | --- | --- |
| **At-most-once** | Event được gửi tối đa một lần; không retry tạo bản sao từ đường này | Có thể mất khi network/consumer lỗi; đơn giản, phù hợp log chẩn đoán có thể bỏ |
| **At-least-once** | Hệ thống nỗ lực gửi lại cho đến khi được xác nhận theo hợp đồng trong điều kiện giả định của nó | Có thể xuất hiện trùng; cần event ID, dedup và giới hạn retry/durability |
| **Exactly-once effect** | Kết quả nghiệp vụ quan sát được chỉ áp dụng một lần khi có thiết kế transactional/idempotent đủ mạnh | Không phải thuộc tính mặc định của logger/HTTP/async queue; phải nêu ranh giới, khóa và cơ chế phục hồi |

**Retry không tự tạo exactly-once.** Khi backend đã lưu event nhưng response ACK bị mất, client không biết việc ghi đã thành công và có thể gửi lại. Điều này tạo bản sao nếu đích lưu không idempotent. Với logging quan sát thông thường, thường chấp nhận duplicate và sửa ở tầng phân tích, nhưng không được nhầm là log phát từ nguồn hai lần.

Hợp đồng còn phụ thuộc **cấp độ xác nhận**. “Enqueued” có thể chỉ là vào RAM, “accepted” có thể là Collector chấp nhận HTTP, còn “durably committed” có thể yêu cầu dữ liệu đã được ghi vào storage bền vững. Xác nhận tại chặng đầu không chứng minh toàn bộ chặng sau thành công.

Nếu cần bảo đảm mạnh hơn cho một sự kiện quan trọng, hãy xác định rõ: điểm commit, cơ chế retry, idempotency key, thời hạn giữ event chưa giao, recovery sau crash, chính sách khi ổ đĩa đầy và cách đối chiếu dữ liệu đã xử lý.

## 6. Ví dụ Java 17 chạy độc lập: ACK bị mất, retry và dedup

Ví dụ này mô phỏng một kho log có **khả năng chống ghi trùng theo event ID**, để thấy vì sao retry có thể phát sinh *duplicate attempt*. Nó chỉ dùng JDK và cố ý không mô phỏng toàn bộ cloud backend hay persistence sau crash.

Tình huống:

- Event A được “lưu” vào `Set`, nhưng ACK đầu tiên bị mô phỏng là mất và client nhận `IOException`.
- Client retry cùng event ID. Kho thấy ID đã tồn tại, không tạo bản ghi logic thứ hai nhưng tính một lần gửi trùng.
- Event B được gửi bình thường.
- Cuối cùng có 3 lần gọi transport, 2 event duy nhất, 1 lần thử gửi trùng.

Lưu thành **`LoggingReliabilityDemo.java`**:

```java
import java.io.IOException;
import java.util.LinkedHashSet;
import java.util.Set;

public final class LoggingReliabilityDemo {
    record LogEvent(String eventId, String severity, String message) {}

    static final class SimulatedStore {
        private final Set<String> storedIds = new LinkedHashSet<>();
        private boolean loseFirstAck = true;
        private int sendAttempts;
        private int duplicateAttempts;

        void send(LogEvent event) throws IOException {
            sendAttempts++;

            if (!storedIds.add(event.eventId())) {
                duplicateAttempts++;
            }

            // Đã lưu logic nhưng phản hồi ACK bị mất.
            if (loseFirstAck) {
                loseFirstAck = false;
                throw new IOException("simulated lost acknowledgement");
            }
        }

        int attempts() {
            return sendAttempts;
        }

        int uniqueCount() {
            return storedIds.size();
        }

        int duplicateCount() {
            return duplicateAttempts;
        }
    }

    static void sendWithRetry(
            LogEvent event, SimulatedStore store, int maxAttempts)
            throws IOException {
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                store.send(event);
                return;
            } catch (IOException ex) {
                if (attempt == maxAttempts) {
                    throw ex;
                }
            }
        }
    }

    public static void main(String[] args) throws IOException {
        SimulatedStore store = new SimulatedStore();

        sendWithRetry(
                new LogEvent("request-42:step-1", "INFO", "accepted"),
                store, 3);
        sendWithRetry(
                new LogEvent("request-42:step-2", "ERROR", "payment failed"),
                store, 3);

        System.out.printf(
                "send_attempts=%d stored_unique=%d duplicate_attempts=%d%n",
                store.attempts(), store.uniqueCount(),
                store.duplicateCount());
    }
}
```

Chạy bằng Java 17 trở lên:

```bash
javac LoggingReliabilityDemo.java
java LoggingReliabilityDemo
```

Stdout chính xác:

```text
send_attempts=3 stored_unique=2 duplicate_attempts=1
```

Diễn giải: Event A mất ACK sau khi được thêm vào `storedIds`, nên lần retry tạo `duplicateAttempts=1`. Event B chỉ cần một lượt. Nếu `storedIds` không có kiểm tra `add` theo khóa, pipeline có thể tạo 3 bản ghi dù ứng dụng chỉ có hai sự kiện logic.

**Giới hạn quan trọng:** `LinkedHashSet` lưu trong RAM, không bền qua crash và không an toàn nếu nhiều thread gọi `send` đồng thời. Demo chạy tuần tự để kiểm chứng semantics retry/dedup, **không** đại diện cho một hệ thống lưu trữ production. Đối với hệ thống thật, dedup cần backend hoặc storage có tính nguyên tử và bền vững; retry cần timeout, jitter, exponential backoff, giới hạn thời gian, metrics và chính sách khi hết lượt. Không nên tự viết vòng retry đồng bộ vô hạn trong thread request.

## 7. Đảm bảo tính toàn vẹn của event

Một log được xem là có ích khi nội dung phù hợp với sự kiện gốc:

- **Định danh:** mỗi event có ID phù hợp phạm vi; `trace_id` và `span_id` dùng cho correlation nhưng không thay cho ID riêng nếu một span có nhiều log.
- **Thời gian:** biết event timestamp và ingestion timestamp, định dạng UTC hoặc offset nhất quán; kiểm clock skew trước khi dùng latency SLI.
- **Thông tin nguồn:** tên service, environment, phiên bản, instance/pod và operation để khoanh vùng lỗi.
- **Payload:** severity, event name, error code, message và exception data không bị cắt/parse sai.
- **Kết cấu:** JSON Lines nên giữ một event trên một dòng; newline trong message hoặc stack trace phải được encode hoặc collector xử lý multiline đúng.
- **Bảo mật:** loại secrets, token, password, dữ liệu cá nhân không cần thiết tại nguồn. Che dữ liệu tại Collector là lớp bổ sung vì dữ liệu có thể đã đi vào buffer trước đó.

Một sự kiện có thể đến đích nhưng **không tìm được** vì sai index, sai project/workspace, retention quá ngắn hoặc thiếu quyền truy vấn. Do đó, SLI “số ACK thành công” khác với SLI “event truy vấn được và nội dung đúng”.

Với yêu cầu audit, chống sửa trái phép, kiểm soát truy cập, retention và bằng chứng về tính toàn vẹn có thể quan trọng hơn latency thấp. Không đánh đồng một JSON log có `trace_id` với bản ghi audit đã được chứng thực.

## 8. Kiến trúc pipeline và điểm có thể mất log

```text
Java service
  -> logger/backend
  -> buffer / async queue
  -> stdout/file/OTLP
  -> runtime log capture / agent
  -> collector + processors + exporter
  -> network
  -> log storage + index
  -> query / alert
```

Mỗi mũi tên là một ranh giới có thể mất dữ liệu:

| Điểm | Lỗi điển hình | Cách giảm rủi ro |
| --- | --- | --- |
| Ứng dụng | Logger không khởi tạo, level/filter sai, exception dựng log | Test cấu hình, giữ log quan trọng, có counters |
| Async queue | Đầy queue, drop, shutdown chưa flush, crash | Bounded capacity, policy backpressure, đo queue/drop, graceful stop |
| stdout/container runtime | Truncated lines, file rotation, pod bị xóa trước khi agent đọc | JSON Lines, agent đủ capacity, kiểm restart/rotation |
| File appender | Full disk, file permission, rotation làm mất offset | Quota/alerts, log shipper theo dõi offset, spool bền khi cần |
| Agent/Collector | Parse lỗi, memory pressure, sai pipeline, exporter không có | Self-metrics, health checks, parse error/drop counters |
| Mạng | Timeout, mất ACK, DNS, TLS, network partition | Retry có hạn, exponential backoff/jitter, idempotency |
| Cloud backend | Ingest quota, throttling, quyền IAM sai, sai region | Quota alarms, routing validation, replay nếu hợp đồng hỗ trợ |
| Lưu trữ/truy vấn | Retention hết, index lag, access sai | Retention policy, query probes, kiểm rights và tier |

**At-least-once tại một chặng không suy ra at-least-once end-to-end.** Chẳng hạn SDK gửi đủ đến Collector, nhưng Collector sau đó drop do buffer đầy. Phải kiểm tra và định nghĩa hợp đồng của **toàn tuyến**, kể cả queue, persistent storage, shutdown và mô hình lỗi mà hệ thống chịu được.

## 9. Queue, backpressure và ưu tiên độ tin cậy

Khi producer tạo log nhanh hơn consumer có thể ghi, queue sẽ đầy. Mỗi chính sách đều có đánh đổi:

| Chính sách | Lợi ích | Rủi ro |
| --- | --- | --- |
| **Block producer** | Giảm nguy cơ bỏ event tại queue | Request bị chặn, timeout hoặc kéo theo sự cố lan rộng |
| **Drop một số mức log** | Bảo vệ throughput và latency của ứng dụng | Có thể mất dữ liệu chẩn đoán; cần policy minh bạch |
| **Fallback sync** | Tiếp tục ghi khi queue đầy | Tạo latency spike bất ngờ |
| **Retry và buffering** | Chịu được mất kết nối tạm thời | Dùng RAM/disk, vẫn có giới hạn; nếu crash/mất đĩa có thể mất |
| **Sampling/aggregation tại nguồn** | Giảm tải trước pipeline | Có thể làm thiếu chuỗi sự kiện nếu chọn mẫu sai đơn vị |

Đối với log chẩn đoán, **fail-open** thường có nghĩa cho phép nghiệp vụ tiếp tục ngay cả khi pipeline log lỗi, theo chính sách drop/đếm lỗi. Đối với sự kiện audit bắt buộc, có thể cần **fail-closed** hoặc đảm bảo commit bản ghi nghiệp vụ và sự kiện audit cùng một giao dịch. Đây là quyết định kiến trúc theo yêu cầu nghiệp vụ; không bật chế độ block vô hạn rồi kỳ vọng hệ thống vừa không mất log vừa không giảm availability.

Khi định nghĩa reliability target, phải ghi rõ response khi hết buffer, mất network dài, shutdown cưỡng bức hoặc backend trả lỗi kéo dài. “Sẽ retry” là chưa đủ: giới hạn retry, nơi lưu event chưa gửi, cách phục hồi, hành vi khi timeout và số event được phép mất mới là hợp đồng có thể kiểm chứng.

## 10. Transactional outbox cho sự kiện bắt buộc

Nếu nghiệp vụ cần cả thay đổi dữ liệu và phát sự kiện một cách bền vững, có thể ghi **business state** và một **outbox row** trong cùng transaction của database:

```text
Transaction:
  update orders set status = 'PAID'
  insert outbox(event_id, type, payload, status)
  COMMIT

Background publisher:
  đọc outbox chưa giao
  -> gửi message/event đến downstream
  -> đánh dấu đã giao theo cơ chế phù hợp
  -> retry nếu gặp lỗi
```

Ví dụ là **sơ đồ khái niệm**, không phải mã SQL hoặc Java chạy độc lập. Outbox giúp tránh trường hợp database commit nhưng ứng dụng crash trước khi phát event ra ngoài. Tuy nhiên publisher vẫn có thể gửi lại khi mất ACK: phía consumer cần dedup/idempotent handling theo event ID. Các thao tác phải xử lý cạnh tranh, retry, cleanup, retention và câu hỏi “khi nào được đánh dấu delivered” trong hệ thống thật.

Không dùng outbox cho mọi dòng DEBUG. Chi phí và độ phức tạp của transaction/reconciliation phù hợp hơn với audit hoặc nghiệp vụ bắt buộc phải có bản ghi đáng tin cậy.

## 11. Java logging framework: độ tin cậy nằm ở cấu hình runtime

Trong Java, gọi `java.util.logging.Logger` hoặc SLF4J mới là bước phát thông điệp. Độ tin cậy phụ thuộc backend/handler/appender và nơi nhận.

- **JUL:** Handler quyết định nơi ghi, level, filter, formatter và flush/close; ứng dụng phải quản lý vòng đời hợp lý. Gọi `logger.info(...)` không bảo đảm một storage bền vững bên ngoài JVM đã ghi.
- **SLF4J:** là facade. Provider/backend như Logback/Log4j2 (với phiên bản tương thích) quyết định appender, async queue, filter, retry hoặc discard. Chỉ có API không tạo ra đường xuất bền vững.
- **Logback/Log4j2 async:** chính sách queue, mức nào có thể bị bỏ, khi nào block, caller data, shutdown/flush và giới hạn bộ nhớ tùy framework/phiên bản/cấu hình.
- **OpenTelemetry Logs/OTLP:** exporter có thể gửi batch qua Collector; response từ Collector không tự khẳng định dữ liệu đã được index hoặc retained bởi cloud backend. Chỉ đặt biến môi trường OTEL chưa đủ nếu không có SDK/agent/instrumentation phát log record.
- **Runtime/container:** stdout/stderr có thể được agent thu thập nhưng vẫn có rotation, quota, restart và ingest lag; không phải một queue bền vững tuyệt đối.

Ứng dụng nên tách log phục vụ chẩn đoán khỏi cơ chế phát sự kiện bắt buộc có hợp đồng khác. Khi thử độ tin cậy, dùng **cấu hình và phiên bản đang chạy thực sự**: test với một memory appender nhanh không đủ để kết luận một Collector bên ngoài không làm mất log.

## 12. Theo dõi SLO và error budget

Mục tiêu chỉ hữu ích khi có dashboard và alert phản ánh nó. Nên quan sát ít nhất:

| Signal | Ý nghĩa |
| --- | --- |
| `events_eligible_total` | Tổng sự kiện phải giữ theo chính sách tại nguồn |
| `events_exported_total` | Số event thử gửi qua exporter |
| `events_accepted_total` | Số được chặng ingest chấp nhận |
| `events_queryable_total` | Số event ID duy nhất tìm được ở backend (thường bằng phép đối chiếu/probe) |
| `events_dropped_total` | Sự kiện mất do queue, filter ngoài policy hoặc lỗi khác |
| `retry_attempts_total` | Số lượt gửi lại; không phải số event logic |
| `queue_depth`, `oldest_event_age` | Backlog, nguy cơ vượt deadline SLO |
| `ingestion_lag_seconds` | Thời gian từ phát event đến lúc dữ liệu sẵn sàng để truy vấn |
| `parse_errors_total`, `export_errors_total` | Dữ liệu không đúng định dạng hoặc đường xuất lỗi |
| `duplicate_events_total` | Event ID lặp tại đích hoặc trong phép đối chiếu |

Các tên metric này **chỉ là ví dụ thiết kế**, không phải tên metric mặc định của mọi Java logging library hay Collector. Các component thật có metric và đơn vị khác nhau; cần map đúng theo exporter/agent phiên bản sử dụng.

Có thể tính **error budget** theo số event: nếu SLO là 99,9% trên 1.000.000 event đủ điều kiện trong cửa sổ, tối đa 1.000 event có thể không đạt hạn 120 giây. Khi lượng traffic thay đổi, ngân sách theo event thay đổi; đồng thời cần giám sát tỷ lệ theo các cửa sổ ngắn để phát hiện sự cố nhanh, tránh để lỗi bị làm mờ bởi lịch sử tốt.

Alert nên kết hợp cảnh báo SLO burn rate với dấu hiệu vận hành như queue gần đầy, exporter retry tăng, log ingestion delay hoặc probe không thấy event. Một pipeline “im lặng hoàn toàn” cần được phát hiện bằng heartbeat/canary và metric độc lập, nếu không dashboard chỉ dựa trên log có thể cũng biến mất khi log hỏng.

## 13. Kiểm thử độ tin cậy thực tế

Cần thử cả **đường thành công** và **đường lỗi**:

1. **Kiểm trace/request correlation:** cùng một request có các trường định danh đúng qua thread pool/service, và ID không bị rò rỉ giữa các request.
2. **Giả lập drop:** queue đạt capacity, policy xử lý đúng, `dropped_total` tăng và alert hoạt động.
3. **Mất ACK:** downstream đã nhận nhưng response thất lạc, exporter retry; xác nhận chính sách duplicate và dedup.
4. **Mất mạng:** ngắt đường exporter trong thời gian có giới hạn; kiểm buffer, retry/backoff, giới hạn RAM/disk và recovery.
5. **Kill process giữa lúc ghi:** xác nhận những event nào đã được commit bền, những event nào có thể mất do RAM queue.
6. **Restart/rotation:** container, file shipper và Collector khôi phục offset/buffer đúng, không bỏ sót hoặc nhân đôi ngoài hợp đồng.
7. **Sai cấu hình/schema:** JSON lỗi, level/filter sai, backend project/region nhầm; phân biệt lỗi transport với dữ liệu đến nhưng không truy vấn được.
8. **Quá tải:** producer burst, backend throttling/quota; đo latency của cả logging và request nghiệp vụ.
9. **Retention và quyền:** event giữ đúng thời hạn, chỉ người có quyền mới truy vấn/xóa; đảm bảo log không làm lộ dữ liệu nhạy cảm.
10. **End-to-end probe:** định kỳ phát event ID canary, tìm ở backend trong deadline, phân tích mất/trễ/trùng và cảnh báo khi vi phạm.

Các test phải có deadline/timeout, điều kiện hoàn tất rõ ràng và báo được event ID bị thiếu, bị trùng hoặc sai metadata. Không nên chỉ gọi `Thread.sleep(1000)` rồi kết luận async queue đã flush. Trong môi trường stress, các kết quả ngẫu nhiên có thể do scheduler hoặc network; hãy ghi lại config, tải, thời điểm và điểm lỗi thực tế để tái hiện.

## 14. Sai lầm thường gặp khi định nghĩa mục tiêu

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Logger không báo lỗi là 100% tin cậy” | Gửi async/collector có thể lỗi về sau | Định nghĩa điểm thành công và kiểm event tại đích |
| Chỉ dùng số event backend đã nhận làm mẫu số | Event mất trước backend biến mất khỏi phép đo | Dùng counter/ID ở nguồn hoặc reconciliation độc lập |
| Coi log đến trễ là mất vĩnh viễn | Hai hành vi và cách xử lý khác nhau | Tách delivery deadline SLI và eventual completeness SLI |
| Coi mỗi retry là một event mới | Numerator bị thổi phồng | Dùng event ID logic và đo duplicate riêng |
| Nghĩ retry bảo đảm exactly-once | ACK có thể thất lạc sau khi lưu | Dùng idempotency/dedup và hợp đồng commit |
| Không phân biệt log INFO đã sampling với log rơi do lỗi | Đo loss rate sai | Định nghĩa eligible events đúng policy |
| Dùng một SLO cho DEBUG và audit | Đánh đổi chi phí hoặc mất bằng chứng | Phân nhóm log theo độ quan trọng |
| Async queue không có giới hạn | RAM tăng, OOM gây mất cả ứng dụng | Bounded queue, backpressure policy, đo backlog |
| Block mọi request khi log backend lỗi | Sự cố logging lan sang tính khả dụng nghiệp vụ | Chọn fail-open/fail-closed theo mức quan trọng |
| Chỉ xem uptime của Collector | Vẫn có thể sai parse, route hoặc index | Kết hợp self-metrics với end-to-end query probes |
| Không test shutdown và crash | Queue trong RAM có thể mất | Test thực tế điểm durable và recovery |
| Đo bằng đồng hồ không đồng bộ | Ingest lag giả cao/âm | Đồng bộ clock hoặc thiết kế phép đo phù hợp |

## 15. Một mẫu SLO để bắt đầu thảo luận

Với một Java service có event nghiệp vụ thông thường và log lỗi, một bản phác thảo **chưa phải cam kết chính thức** có thể là:

| Nhóm | SLI | SLO minh họa | Hành động nếu vi phạm |
| --- | --- | --- | --- |
| ERROR | Tỷ lệ event ID ERROR đủ điều kiện truy vấn được trong 120 giây | ≥ 99,9% trên 30 ngày | Alert, kiểm exporter/drop/ingest delay |
| INFO quan trọng | Tỷ lệ event đủ điều kiện có thể truy vấn trong 5 phút | ≥ 99,5% trên 30 ngày | Kiểm queue/backpressure, giảm log lặp |
| Chất lượng metadata | Tỷ lệ event đến đích có service/env/severity và ID cần thiết | ≥ 99,9% trong mẫu đo | Sửa encoder, mapping và propagation |
| Audit bắt buộc | Đối chiếu event phải có với nguồn nghiệp vụ bền vững | Mục tiêu và ngoại lệ phải được quyết định theo chính sách nghiệp vụ | Dùng storage/transaction/outbox, điều tra thiếu dữ liệu |

Các ngưỡng chỉ giúp minh họa cách viết SLO có thể đo; thay bằng giá trị được chốt từ nhu cầu điều tra, ràng buộc dữ liệu, năng lực hạ tầng và chi phí. Đặc biệt, không sử dụng tỷ lệ 99,x% làm lý do cho phép mất một sự kiện audit quan trọng mà hợp đồng yêu cầu đầy đủ.

**Checklist khi đưa vào vận hành:** xác định event đủ điều kiện; phân nhóm log; chốt deadline và cửa sổ SLO; instrument source/agent/backend; nêu rõ ack/durability, retry/dedup và buffer policy; đo loss, lag, duplicate, metadata và retention; kiểm failure scenario; có dashboard, canary và alert; đồng thời kiểm xem sự cố logging có làm hỏng khả năng phục vụ request hay không.

**Ghi nhớ:** mục tiêu độ tin cậy logging phải được định nghĩa từ **event do ứng dụng cần ghi** đến **dữ liệu thật sự có thể tìm và dùng tại đích**. Đặt SLO rõ ràng, đo đúng mẫu số, hiểu delivery semantics và thử hành vi khi lỗi mới giúp hệ thống vừa quan sát được vừa vận hành an toàn.
