# Polling, thông báo sự kiện và kiểm soát nhịp lấy dữ liệu

Trong tích hợp hệ thống, không phải nguồn dữ liệu nào cũng có khả năng chủ động gửi sự kiện khi dữ liệu thay đổi. Một thư mục SFTP có thể chỉ cho phép liệt kê tệp, một bảng cơ sở dữ liệu có thể chỉ cho phép truy vấn, trong khi broker thông điệp hoặc webhook có thể chủ động thông báo ngay khi phát sinh công việc. Việc chọn **polling**, **nhận thông báo sự kiện** hay **kết hợp cả hai** ảnh hưởng trực tiếp đến độ trễ, tải hệ thống, tính nhất quán, khả năng xử lý trùng và cách phục hồi sau lỗi.

Bài thuộc chương **Adapter tích hợp** của học phần **SPRING_BOOT_INTEGRATION**. Trong phạm vi tích hợp HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter **Spring Integration**, bài tập trung vào hợp đồng nhận dữ liệu, cấu hình nhịp lấy dữ liệu, ranh giới giao dịch, kiểm thử, quản lý lỗi và quan sát luồng tích hợp thực tế.

## 1. Kết quả cần đạt

Sau bài này, người học có thể:

1. Phân biệt polling định kỳ, polling theo lịch, tiếp nhận sự kiện và mô hình thông báo kết hợp đối soát.
2. Mô tả vai trò của **MessageSource**, **SourcePollingChannelAdapter**, **Poller**, **MessageChannel** và handler trong Spring Integration.
3. Cấu hình nhịp lấy dữ liệu, số message tối đa mỗi chu kỳ, giới hạn song song và chính sách dừng khi hạ nguồn quá tải.
4. Thiết kế việc đọc dữ liệu từ DB/SFTP/API sao cho an toàn khi ứng dụng chạy nhiều instance, khởi động lại hoặc mất kết nối.
5. Tách bạch việc **phát hiện có dữ liệu**, **nhận và xác nhận dữ liệu**, **xử lý nghiệp vụ**, **ghi checkpoint**.
6. Chọn điểm đặt giao dịch, idempotency key, retry, dead-letter/quarantine và metric phù hợp với hợp đồng tích hợp.

## 2. Polling và thông báo sự kiện khác nhau ở đâu?

**Polling** là việc ứng dụng chủ động kiểm tra nguồn theo một nhịp hoặc lịch để xem có dữ liệu mới. Một lần kiểm tra có thể trả về một, nhiều hoặc không có phần tử. **Event notification** là việc nguồn chủ động báo rằng đã phát sinh sự kiện, thường qua HTTP webhook, broker hoặc callback. Thông báo có thể chứa toàn bộ dữ liệu hoặc chỉ chứa mã tham chiếu để ứng dụng tự truy vấn bổ sung.

~~~mermaid
flowchart LR
    subgraph Pull["Polling: ứng dụng chủ động lấy"]
      CLOCK["Scheduler / Poller"] --> SOURCE["DB / file / SFTP / HTTP API"]
      SOURCE --> ADAPTER["Inbound polling adapter"]
    end
    subgraph Push["Notification: nguồn chủ động báo"]
      EXTERNAL["Hệ thống bên ngoài"] --> WEBHOOK["Webhook / message listener"]
    end
    ADAPTER --> CHANNEL["MessageChannel"]
    WEBHOOK --> CHANNEL
    CHANNEL --> LOGIC["Validate / transform / handler"]
    LOGIC --> STORE[("DB / broker / service đích")]
~~~

| Tiêu chí | Polling | Thông báo sự kiện |
|---|---|---|
| Bên quyết định thời điểm nhận | Ứng dụng tích hợp | Nguồn phát hoặc broker |
| Độ trễ phát hiện | Thường phụ thuộc chu kỳ poll và backlog | Thường thấp nếu thông báo truyền kịp |
| Tải lên nguồn khi rỗng | Có, vì vẫn phải kiểm tra | Thường ít hơn khi không có sự kiện |
| Khả năng bỏ sót | Có nếu checkpoint/lọc sai hoặc dữ liệu biến mất trước khi đọc | Có nếu webhook/broker không bảo đảm lưu và phát lại |
| Xử lý mất kết nối | Lần poll sau có thể đọc bù nếu nguồn còn dữ liệu | Cần retry, event log, inbox hoặc cơ chế đối soát |
| Điều tiết tải | Điều chỉnh lịch, batch, concurrency, backoff | Broker consumer limit, prefetch, pause/resume, 429 và hàng đợi |
| Phù hợp | DB bảng chờ, file/SFTP, API không hỗ trợ push | Webhook, hàng đợi, stream, thay đổi được nguồn phát |

**Lưu ý về thuật ngữ:** một Kafka consumer có thể dùng cơ chế **poll** ở mức thư viện/protocol, nhưng đối với luồng Spring Integration nó thường cung cấp thông điệp theo kiểu message-driven. Vì vậy không nên kết luận rằng cứ có phương thức tên **poll()** thì đều cần một Spring Integration **Poller**. Phân loại dựa vào ai sở hữu nhịp gọi **MessageSource** của flow.

### 2.1. Ba tình huống nghiệp vụ

- **Đối tác đặt file vào SFTP mỗi giờ:** ứng dụng không được thông báo chính xác lúc upload hoàn tất; dùng polling với bộ lọc, kiểm tra file sẵn sàng và dấu vết file đã nhận.
- **Đối tác gửi webhook “đơn hàng đã thay đổi”:** endpoint tiếp nhận sự kiện, xác thực chữ ký, ghi nhận event ID và xử lý sau; có thể truy vấn HTTP API theo ID để lấy trạng thái mới nhất.
- **Webhook có thể mất trong gián đoạn mạng:** kết hợp nhận webhook nhanh với tác vụ polling đối soát định kỳ theo cursor, tránh bỏ sót cập nhật.

## 3. Bản chất poller trong Spring Integration

Trong luồng Spring Integration, **polling inbound adapter** đọc từ một **MessageSource** theo lịch và đưa thông điệp vào **MessageChannel** để được xử lý. Một nguồn **event-driven inbound adapter** hoặc **message-driven adapter** phát thông điệp khi nhận dữ liệu từ hệ thống bên ngoài, nên không nhất thiết có poller của Spring Integration cho flow đó.

~~~mermaid
flowchart TD
    TRIGGER["TaskScheduler + Trigger"] --> POLLER["Poller"]
    POLLER --> RECEIVE["MessageSource.receive()"]
    RECEIVE --> RETURN{"Có Message?"}
    RETURN -->|Không: null| EMPTY["Kết thúc lượt poll hiện tại"]
    RETURN -->|Có| CHANNEL["MessageChannel"]
    CHANNEL --> FILTER["Filter / Transformer"]
    FILTER --> HANDLER["Service Activator / Handler"]
    HANDLER --> RESULT[("Hệ thống đích")]
~~~

Các khái niệm cần nắm:

| Thành phần | Trách nhiệm | Giới hạn cần nhớ |
|---|---|---|
| **MessageSource** | Phương thức **receive()** lấy một message hoặc trả **null** khi tạm hết dữ liệu | Mỗi lần gọi không nhất thiết tương đương một hàng DB nếu payload là danh sách |
| **SourcePollingChannelAdapter** | Kết nối lịch poll với MessageSource và đưa kết quả vào flow | Không tự tạo bảo đảm exactly-once |
| **Trigger / TaskScheduler** | Quyết định khi nào chạy lượt polling | Lịch định kỳ không cam kết độ trễ tuyệt đối khi thread bị chiếm |
| **PollerMetadata / PollerSpec** | Quy định nhịp poll, số message mỗi lượt và advice/transaction nếu cần | Nên cấu hình theo từng nguồn, tránh áp mặc định chung một cách mù quáng |
| **MessageChannel** | Chuyển message tới bước sau | DirectChannel xử lý đồng bộ; channel bất đồng bộ thay đổi ranh giới thread/giao dịch |
| **Handler** | Thực thi xử lý nghiệp vụ và phát kết quả/exception | Phải quyết định idempotency, retry, ack/checkpoint |

Trong một chu kỳ, poller gọi **receive()** nhiều nhất theo **maxMessagesPerPoll**, và thường kết thúc sớm khi nhận **null**. Nếu MessageSource luôn trả phần tử, một cấu hình không giới hạn có thể giữ thread hoạt động quá lâu. Nếu source trả một **Message<List<Item>>**, đó vẫn chỉ là **một message** đối với poller; giới hạn số bản ghi trong payload phải được thực thi ở tầng query/source.

### 3.1. Các nhịp phổ biến

- **Fixed delay:** khoảng nghỉ tính sau khi lượt trước kết thúc; phù hợp khi muốn tránh dồn nhịp lên nguồn đang chậm.
- **Fixed rate:** mục tiêu đặt các thời điểm kích hoạt cách nhau một khoảng cố định; lượt chạy bị trễ do scheduler bận hoặc xử lý lâu có thể làm sai nhịp thực tế. Không mặc định hiểu fixed rate là song song vô hạn.
- **Cron:** chạy vào lịch cụ thể, ví dụ đồng bộ lúc đầu mỗi khoảng năm phút. Cron phù hợp yêu cầu giờ kinh doanh hoặc cửa sổ xử lý, cần xác định rõ timezone và ứng xử khi thời điểm chạy bị lỡ.
- **Điều tiết thích ứng:** nhịp thay đổi theo **backlog**, 429/Retry-After, thời gian xử lý, sức chứa downstream hoặc việc nhiều lần liên tiếp không có dữ liệu. Thường cần trigger/chính sách bao quanh thay vì chỉ một fixed delay tĩnh.

Lịch không thay thế hợp đồng dữ liệu. Poll mỗi 100 ms không làm nguồn cập nhật nhanh hơn nếu đối tác chỉ ghi dữ liệu mỗi 15 phút, nhưng lại tăng tải, log và số kết nối.

## 4. Ví dụ Spring Boot: polling từ bảng công việc

Giả sử một hệ thống nhập dữ liệu có bảng **inbound_work** lưu công việc cần xử lý. Có một repository cung cấp thao tác **claimNext()**: chọn và đánh dấu giữ quyền xử lý **một** công việc bằng thao tác nguyên tử/transaction ở DB, trả **Optional.empty()** nếu tạm không còn công việc. Repository cũng chịu trách nhiệm lease và khôi phục phần tử bị bỏ dở sau khi instance chết.

Lớp cấu hình dưới đây dùng Spring Boot 3.x và Spring Integration Java DSL:

~~~java
import java.time.Duration;
import java.util.Optional;
import java.util.UUID;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.core.MessageSource;
import org.springframework.messaging.support.MessageBuilder;

record WorkItem(UUID id, String content) {}

interface WorkItemRepository {
    // Cần được implement bằng claim nguyên tử với lease,
    // tương thích khi nhiều app instance cùng poll.
    Optional<WorkItem> claimNext();
}

interface WorkItemProcessor {
    // Commit kết quả và hoàn tất công việc theo idempotency key.
    void process(WorkItem workItem);
}

@Configuration
@EnableIntegration
class InboundWorkFlowConfig {

    @Bean
    MessageSource<WorkItem> inboundWorkSource(WorkItemRepository repository) {
        return () -> repository.claimNext()
                .map(item -> MessageBuilder.withPayload(item)
                        .setHeader("workId", item.id().toString())
                        .build())
                .orElse(null);
    }

    @Bean
    IntegrationFlow inboundWorkFlow(
            MessageSource<WorkItem> inboundWorkSource,
            WorkItemProcessor processor) {

        return IntegrationFlow
                .from(inboundWorkSource, endpoint -> endpoint
                        .poller(Pollers.fixedDelay(Duration.ofSeconds(2))
                                .maxMessagesPerPoll(20)))
                .handle(WorkItem.class, (item, headers) -> {
                    processor.process(item);
                    return null; // Terminal handler: không tạo reply
                })
                .get();
    }
}
~~~

**Tại sao ví dụ tách interface?** Cấu hình adapter diễn tả lịch và đường đi message; việc claim/lease, commit và xử lý trùng là hợp đồng riêng của tầng lưu trữ/nghiệp vụ. Không nên biến một lệnh SELECT đơn giản thành **claimNext()** và giả định an toàn khi có hai pod. Một triển khai DB có thể dùng giao dịch với row locking và **SKIP LOCKED** nếu cơ sở dữ liệu hỗ trợ, hoặc update trạng thái có điều kiện và kiểm tra số hàng cập nhật. Khi claim xong rồi xử lý thất bại, cần lease expiry, retry state hoặc hàng lỗi để công việc quay lại.

**Cách đọc cấu hình:**

1. Mỗi lượt lịch, poller gọi source cho đến khi nhận **null** hoặc đã lấy tối đa 20 **Message**.
2. Payload **WorkItem** đi tới handler qua flow; mặc định với đường đồng bộ, thời gian handler chạy cộng vào thời gian thực thi lượt poll.
3. Khi processor lỗi, cần chính sách xử lý exception và thu hồi lease/khôi phục việc bị bỏ dở; code chỉ thể hiện điểm gắn, chưa cài đặt toàn bộ vòng đời công việc.
4. Nếu ứng dụng chạy nhiều instance, mỗi instance có scheduler riêng. Việc tránh trùng phải dựa vào claim nguyên tử/idempotency của nguồn hoặc một cơ chế điều phối có độ tin cậy phù hợp.

### 4.1. Chọn đúng điểm đặt transaction

Ba hoạt động cần tách rõ:

- **Đọc và claim:** một transaction ngắn để chiếm quyền xử lý, lưu **claimed_by**, **lease_until**, trạng thái và attempt; tránh giữ DB lock suốt thời gian gọi HTTP chậm.
- **Xử lý nghiệp vụ:** có thể gọi HTTP/broker hoặc ghi DB đích. Kết quả chưa chắc chắc chắn sau timeout; cần mã yêu cầu để đối soát.
- **Hoàn tất/ack:** chỉ đánh dấu **DONE** khi tác động nghiệp vụ cần thiết đã được commit hoặc có cách khôi phục ổn định.

Poller có thể sử dụng transaction advice/transaction manager. Tuy nhiên transaction trong Spring chủ yếu có hiệu lực trên cùng thread và resource tham gia; chuyển sang **ExecutorChannel** hoặc gửi sang broker tạo ranh giới khác. Một transaction bao quanh lần gọi **receive()** không mặc nhiên đồng bộ với ghi DB đích, HTTP request và ACK của broker.

Với hệ thống yêu cầu bền vững cao, cân nhắc mô hình **inbox/outbox** và consumer idempotent. Đừng hứa exactly-once chỉ vì đã cấu hình Spring Integration transaction.

## 5. Cấu hình nhịp lấy dữ liệu theo mục tiêu vận hành

Bốn tham số chính cần thiết kế cùng nhau: **chu kỳ kích hoạt**, **kích thước batch**, **số lượng xử lý đồng thời** và **năng lực hạ nguồn**.

| Tham số | Tăng lên sẽ ảnh hưởng gì? | Rủi ro và điều kiện |
|---|---|---|
| **Tần suất poll** | Phát hiện dữ liệu sớm hơn nếu nguồn cập nhật thường xuyên | Tăng query/API call, quota, connection và các lần poll rỗng |
| **maxMessagesPerPoll** | Giảm overhead một chu kỳ, có thể tăng throughput | Một chu kỳ kéo dài, thiếu công bằng giữa các nguồn, giữ thread lâu |
| **Batch trong query** | Giảm số lần truy cập nguồn cho nhiều bản ghi | Lần đọc lớn tăng memory, transaction lock, packet và thời gian khôi phục |
| **Concurrency** | Tăng số việc xử lý cùng lúc | Dễ vượt connection pool, rate limit, có thể làm sai thứ tự |
| **Backoff** | Giảm tải khi lỗi hoặc nguồn rỗng | Làm tăng độ trễ phục hồi hoặc phát hiện |
| **Jitter** | Phân tán thời điểm poll giữa nhiều pod | Thời điểm thực tế khó dự đoán hơn; cần đo thay vì dựa vào lịch lý thuyết |

### 5.1. Ước lượng thông lượng

Với một flow đồng bộ, mỗi lượt lấy tối đa **B** message và khoảng nghỉ **D** giây sau khi hoàn tất, thời gian xử lý trung bình mỗi message **L** giây, một ước lượng khi luôn đầy batch là:

\[
R \approx \frac{B}{D + B \times L}
\]

Ví dụ **B = 20**, **D = 2 giây**, **L = 0,1 giây** cho thông lượng lý thuyết khoảng **5 message/giây** (20 message trong 4 giây). Nếu bỏ qua thời gian xử lý và chỉ lấy **B/D = 10 message/giây**, ta đã đánh giá quá cao khả năng thực tế. Công thức chưa tính chi phí DB/network, retry, thời gian scheduler, queueing và contention; phải đo khi tải thử.

Với mô hình bất đồng bộ, tốc độ nhận nguồn có thể vượt xa tốc độ xử lý. Cần thêm giới hạn queue, task executor và downstream, nếu không poller chỉ chuyển áp lực từ nguồn sang bộ nhớ ứng dụng.

### 5.2. Dùng fixed delay, fixed rate và cron

~~~java
// Nghỉ 2 giây sau khi lượt poll trước kết thúc.
Pollers.fixedDelay(Duration.ofSeconds(2))
       .maxMessagesPerPoll(20);

// Mục tiêu kích hoạt theo nhịp mỗi 5 giây;
// thời điểm thực tế còn phụ thuộc scheduler và thời gian thực thi.
Pollers.fixedRate(Duration.ofSeconds(5))
       .maxMessagesPerPoll(10);

// Chạy ở giây 0 của mỗi mốc 5 phút.
// Cần cấu hình timezone khi yêu cầu lịch địa phương.
Pollers.cron("0 */5 * * * *")
       .maxMessagesPerPoll(100);
~~~

Các biểu thức trên là những **mẫu PollerSpec** để gắn vào endpoint tương ứng; đây không phải ba poller đồng thời áp dụng cho một nguồn. Tên overload/API cần đối chiếu với phiên bản Spring Integration đang dùng. Nếu nhiều flow có lịch khác nhau, cấu hình tại từng endpoint giúp tránh một default poller quá mạnh áp cho nguồn nhỏ.

### 5.3. Quy tắc thiết kế nhịp

1. Chọn **SLO độ trễ**: dữ liệu cần hiển thị trong 2 giây, 30 giây hay 15 phút?
2. Đo **tần suất sinh dữ liệu** và số bản ghi mỗi đợt; giờ cao điểm thường khác trung bình.
3. Xác định **quota nguồn**: số API call/phút, connection DB tối đa, chu kỳ quét SFTP hợp lý.
4. Xác định **tốc độ xử lý hạ nguồn**: DB write/s, broker quota, HTTP RPS, thread pool.
5. Đặt **batch, timeout, retry, backoff và giới hạn xử lý đồng thời** trong ngân sách này.
6. Đo backlog/lag, p95/p99 end-to-end; tinh chỉnh bằng số liệu thay vì giảm fixed delay vô hạn.

## 6. Áp lực ngược: khi nguồn đến nhanh hơn khả năng xử lý

**Backpressure** là khả năng giảm hoặc tạm ngừng tốc độ nhận khi phần xử lý sau không theo kịp. Cơ chế này quan trọng kể cả khi poller chủ động lấy, bởi nhiều luồng có thể đọc cùng một DB hoặc API.

~~~mermaid
flowchart LR
    SRC["DB / API / SFTP"] --> POLL["Bounded polling"]
    POLL --> QUEUE["Bounded buffer / durable queue"]
    QUEUE --> WORK["Worker pool có giới hạn"]
    WORK --> DEST[("DB / external service")]
    MON["Đo queue depth, backlog age, error, latency"] -.-> POLL
    MON -.-> WORK
    DEST -. "429, 503, timeout" .-> MON
~~~

Nếu tích hợp bằng **DirectChannel**, handler chạy đồng bộ trên thread gửi, tạo giới hạn tự nhiên theo thời gian handler; nhưng nó cũng khiến scheduler bị chiếm lâu. Nếu dùng **QueueChannel** hoặc executor channel, poller có thể đọc tiếp khi handler chưa xử lý xong. Lúc này cần xác định rõ:

- Kích thước queue tối đa và cách phản ứng khi queue đầy; queue trong RAM có thể mất dữ liệu khi pod bị huỷ.
- Giới hạn thread/connection cho downstream, phân biệt tác vụ CPU-bound và IO-bound.
- Tốc độ pause/resume polling; retry có jitter và backoff theo loại lỗi.
- Cơ chế khôi phục phần tử đã claim nhưng chưa được xử lý sau khi crash.
- Việc tăng số worker có phá vỡ thứ tự sự kiện theo từng tài khoản/đơn hàng hay không.

Không nên đặt queue nội bộ không giới hạn rồi coi đó là giải pháp chịu tải. Nếu queue đầy, chọn **chặn đọc tiếp**, **trả lỗi có kiểm soát**, hoặc **ghi vào hàng đợi bền vững** theo hợp đồng; không lặng lẽ vứt bỏ dữ liệu quan trọng.

### 6.1. Adaptive backoff và quota HTTP

Giả sử adapter poll API đối tác theo cursor. Nếu nhận **429 Too Many Requests**, ưu tiên tôn trọng **Retry-After** khi hợp lệ và được phép; nếu không có, dùng exponential backoff có giới hạn và jitter. Đối với **5xx** hoặc lỗi mạng tạm thời, thử lại có hạn mức; đối với **401/403** thường phải kiểm tra credential/quyền thay vì retry nhanh. Tránh chia sẻ một lịch retry vô giới hạn cho cả fetch lẫn bước ghi DB.

Khi API trả trang dữ liệu, cần lưu cursor hoặc checkpoint an toàn. Một response timeout không nói rõ server đã thực hiện truy vấn hay chưa, nhưng thường đọc lại trang bằng cursor ổn định có thể xử lý trùng; việc ghi vào hệ thống đích vẫn phải idempotent.

## 7. Thông báo sự kiện: nhận nhanh nhưng phải xác định độ tin cậy

Các nguồn event-driven phổ biến trong hệ Spring Boot:

| Cơ chế | Cách adapter nhận | Điều kiện để không mất sự kiện quan trọng |
|---|---|---|
| HTTP webhook | Spring MVC/WebFlux endpoint hoặc Spring Integration HTTP inbound gateway | Xác thực nguồn, lưu inbox bền vững trước khi xác nhận nếu cần at-least-once, hỗ trợ replay và dedupe |
| Broker queue (RabbitMQ, JMS, v.v.) | Listener/message-driven inbound adapter | Chọn ack mode, retry/requeue, DLQ, consumer concurrency và idempotency |
| Kafka/stream | Consumer inbound adapter | Commit offset đúng lúc, xử lý trùng, partition ordering và quản lý lag |
| Spring application event | Listener hoặc adapter nội bộ ứng dụng | Không xem sự kiện in-process như hàng đợi bền vững qua restart |
| File system watcher | Notification từ OS hoặc adapter hỗ trợ watcher | File change event có thể mất/được gom; thường cần quét đối soát và kiểm tra file đã ghi xong |

Một webhook có thể được gửi nhiều lần khi hệ thống bên ngoài không nhận được HTTP response, dù lần đầu đã được ứng dụng xử lý. Ngoài ra event có thể đến không theo thứ tự. Vì vậy **event ID**, **resource ID**, **event version**, **event timestamp** và **cơ chế đối soát trạng thái chuẩn** quan trọng hơn việc tối ưu vài mili giây độ trễ.

### 7.1. Ví dụ luồng webhook an toàn

~~~mermaid
sequenceDiagram
    participant Ext as External partner
    participant API as Spring Boot webhook
    participant DB as Inbox DB
    participant Worker as Integration worker
    participant Target as Business DB/service
    Ext->>API: POST event (eventId, resourceId)
    API->>API: Verify signature, schema, replay window
    API->>DB: Insert inbox by unique eventId
    DB-->>API: Committed / duplicate known
    API-->>Ext: 2xx acknowledgment
    Worker->>DB: Claim pending inbox items
    Worker->>Target: Idempotent business operation
    Target-->>Worker: Committed / reconciled
    Worker->>DB: Mark inbox DONE
~~~

Trong kịch bản này, **2xx** xác nhận **đã tiếp nhận bền vững**, không đồng nghĩa mọi xử lý nghiệp vụ đã hoàn tất. Nếu đối tác yêu cầu xử lý đồng bộ trước khi chấp nhận, phải điều chỉnh hợp đồng HTTP, timeout và mã lỗi cho phù hợp. Khi xác thực chữ ký hoặc schema thất bại, không gửi 2xx giả tạo; cần phân biệt lỗi xác thực với retryable failure. Khi ghi inbox thất bại, phản hồi lỗi retryable theo hợp đồng của đối tác.

Luồng trên cố tình dùng inbox và worker để minh hoạ ranh giới giữa **thông báo** và **xử lý**. Adapter Spring Integration có thể nhận trực tiếp qua HTTP inbound gateway, RabbitMQ/Kafka adapter hoặc channel nội bộ; cách gắn cơ chế nguồn phải đi kèm cấu hình ack, error handling và persistence tương ứng.

### 7.2. Khi nào dùng webhook kèm polling?

Thông báo có thể chỉ đóng vai trò **tín hiệu**: “resource X thay đổi”. Ứng dụng ghi nhận tín hiệu, rồi pull trạng thái mới nhất từ API theo resource ID. Cách này hữu ích nếu event payload không đầy đủ, nhưng không giải quyết việc mất event khi kết nối lỗi.

Một thiết kế bền hơn:

1. Webhook giúp phát hiện nhanh các thay đổi mới.
2. Poller đối soát định kỳ tất cả thay đổi từ cursor đã xác nhận hoặc khoảng thời gian có chồng lấn.
3. Inbox/idempotency key bảo đảm webhook và poller gặp cùng một resource không tạo hai tác động nghiệp vụ.
4. Checkpoint chỉ tiến sau khi dữ liệu tương ứng đã được ghi/được đưa vào hàng đợi bền vững.
5. Theo dõi **độ lệch webhook-to-processed** và **reconciliation lag** để nhận ra event bị thiếu.

## 8. Cursor, checkpoint và tránh bỏ sót dữ liệu

Polling không an toàn nếu chỉ hỏi “có gì mới sau lần trước?” mà không xác định ranh giới trang, thứ tự sắp xếp, độ trễ nguồn và thời điểm commit.

### 8.1. Không dùng offset phân trang vô điều kiện

Với bảng hàng chờ, các bản ghi đổi từ **PENDING** sang **DONE** khi được xử lý. Nếu dùng **OFFSET 100** trên tập **PENDING** đang thu hẹp, vị trí hàng sẽ dịch và có thể bỏ sót các bản ghi. Với API phân trang thay đổi theo thời gian, offset có vấn đề tương tự.

Ưu tiên:

- **Claim theo trạng thái/lease** trên hàng chờ có transaction nguyên tử.
- **Keyset pagination** theo cặp ổn định, chẳng hạn **(updated_at, id)**, nếu hợp đồng dữ liệu cho phép.
- **Cursor do nguồn cung cấp** nếu cursor bảo đảm đúng thứ tự và khả năng resume.
- Cơ chế **overlap window** để đọc lại một phần khi sự kiện đến muộn; downstream phải idempotent.

### 8.2. Phân biệt high-watermark, checkpoint và trạng thái xử lý

- **High-watermark:** giá trị lớn nhất đã nhìn thấy từ nguồn, ví dụ thời gian cập nhật hoặc sequence.
- **Checkpoint đã commit:** vị trí mà hệ thống có thể resume mà không bỏ sót dữ liệu theo hợp đồng đã chọn.
- **Trạng thái từng phần tử:** PENDING, CLAIMED, DONE, FAILED hoặc QUARANTINED.

Không cập nhật checkpoint trước khi batch đã được lưu vào nơi bền vững hoặc xử lý hoàn tất theo hợp đồng. Nếu cập nhật sớm rồi pod crash, dữ liệu sau checkpoint có thể biến mất khỏi phạm vi poll tiếp theo. Nếu cập nhật muộn, sẽ đọc lại; đó là lý do cần idempotency.

Ví dụ với nguồn có **updated_at** không được bảo đảm tăng theo thời điểm ứng dụng nhìn thấy, filter **updated_at > lastSeen** có thể bỏ sự kiện đến muộn. Một cách giảm rủi ro là dùng lookback window, kết hợp **(updated_at, id)** và dedupe; nhưng độ dài lookback cần dựa trên SLA độ trễ nguồn hoặc cam kết cursor, không tự đặt theo cảm tính.

### 8.3. File/SFTP cần tiêu chí “sẵn sàng”

Việc file xuất hiện trong thư mục chưa chắc đối tác đã ghi xong. Những quy ước được dùng trong thực tế gồm:

- Đối tác upload tên tạm, đổi tên nguyên tử khi hoàn tất.
- Có file marker **.done** hoặc manifest chứa danh sách/tổng checksum.
- Poller kiểm tra size/mtime ổn định qua nhiều chu kỳ (chỉ là heuristic, không thay hợp đồng producer).
- Chỉ đánh dấu file đã xử lý sau khi dữ liệu đích commit; lưu danh tính file, fingerprint/checksum hoặc business ID chống lặp.

Bộ lọc file của inbound adapter cần cơ chế lưu trạng thái lâu dài khi yêu cầu restart-safe; bộ lọc chỉ trong bộ nhớ có thể cho nhận lại file sau restart. Nhận lại không nhất thiết là lỗi nếu hệ thống xử lý idempotent.

## 9. Nhiều instance cùng polling: tranh chấp và bảo đảm xử lý

Khi Spring Boot được triển khai thành ba pod, mỗi pod có poller của riêng nó. Cùng một lịch **fixedDelay(2s)** sẽ có ba chu kỳ độc lập; Spring Integration không tự biến một flow thành một cron job phân tán duy nhất.

~~~mermaid
flowchart TD
    A["Pod A: poller"] --> Q[("Shared work table / source")]
    B["Pod B: poller"] --> Q
    C["Pod C: poller"] --> Q
    Q --> CLAIM["Atomic claim / partition ownership"]
    CLAIM --> HANDLE["Process idempotently"]
    HANDLE --> CHECK["Commit business effect + completion"]
~~~

Có ba kiểu phối hợp thường dùng:

| Mẫu | Ý tưởng | Khi phù hợp |
|---|---|---|
| Mỗi pod tự poll, **claim atomically** | Nhiều consumer chia tải, mỗi work item thuộc một lease/owner | Hàng công việc trong DB, cơ chế lấy phần tử độc lập |
| Chỉ một leader poll | Leader election hoặc distributed lock giới hạn scheduler đang hoạt động | Nguồn cũ không hỗ trợ song song, API quota cực thấp |
| Chia partition/cursor | Mỗi consumer được gán partition/key-range riêng | Dữ liệu lớn, có partition ổn định và yêu cầu ordering |

**Một distributed lock không đủ để bảo đảm xử lý đúng một lần:** lock có thể hết hạn, holder cũ tiếp tục chạy; failover có thể tạo trạng thái chưa rõ. Với side effect quan trọng, cần idempotency tại đích, giao dịch DB, fencing token nếu cần và quy trình đối soát.

**Một claim chỉ là bước nhận quyền tạm thời:** khi pod chết, lease phải hết hạn để được lấy lại. Work item có thể được xử lý hai lần nếu pod chết sau khi commit side effect nhưng trước khi mark DONE; downstream cần nhận diện idempotency key ổn định.

## 10. Lỗi, retry và việc kiểm soát nhịp sau lỗi

Chính sách cần khác nhau giữa lỗi poll nguồn, lỗi biến đổi dữ liệu và lỗi hạ nguồn:

| Lỗi | Hành động thích hợp | Điều nên tránh |
|---|---|---|
| Không kết nối được DB/SFTP/API nguồn | Timeout hữu hạn, backoff có giới hạn, alert khi vượt SLO | Poll liên tục gây log storm/đè nguồn |
| HTTP 429 / quota | Tôn trọng Retry-After, giảm tốc độ hoặc tạm dừng | Retry tức thì trên mọi pod |
| Cấu hình sai, 401/403, schema không hợp lệ | Phân loại không retry nhanh; cảnh báo và sửa cấu hình/dữ liệu | Xem là lỗi mạng tạm thời |
| Một record lỗi dữ liệu nhưng nguồn còn dữ liệu | Quarantine/DLQ kèm mã lỗi và id, tiếp tục theo chính sách | Để một poison message khoá toàn bộ pipeline vô thời hạn |
| Downstream timeout sau side effect | Ghi trạng thái uncertain, tra cứu/idempotency trước khi retry | Tự động gửi lại POST không có request ID |
| Queue/buffer đầy | Tạm ngừng nhận, điều tiết source hoặc từ chối có kiểm soát | Queue RAM không giới hạn, bỏ âm thầm |

Ở Spring Integration, lỗi của poller có thể được định tuyến qua **errorChannel**/error flow, và có thể kết hợp advice cho retry, transaction, circuit breaker. Cần kiểm tra lỗi ở mức **lượt poll** lẫn **từng phần tử**; một exception từ handler đồng bộ có thể làm kết thúc lượt poll hiện tại. Nếu chuyển qua channel bất đồng bộ, exception phát sinh ở worker thread có thể không quay lại đúng thread poller để rollback transaction nguồn.

### 10.1. Ba cấp retry không được chồng vô hạn

1. **Retry kết nối/đọc:** xử lý một lần lỗi truy cập nguồn, giới hạn thời gian và số lần thử.
2. **Retry xử lý nghiệp vụ:** dùng idempotency key và trạng thái attempt của mỗi phần tử, có delay/backoff.
3. **Retry toàn lượt hoặc tác vụ theo lịch:** chu kỳ poll sau hoặc job reconciliation đọc lại công việc chưa DONE.

Khi ba cấp cùng có retry, số lần thực thi có thể nhân lên đáng kể. Phải xác định **chủ sở hữu retry** theo ranh giới và có ngân sách tổng: timeout, max attempts, cooldown, retention và TTL của idempotency marker.

### 10.2. Kiểm soát thứ tự và việc mất trùng

Polling theo nhiều worker thường không còn xử lý theo thứ tự toàn cục. Nếu cùng một order có các cập nhật **CREATED**, **PAID**, **CANCELLED**, xử lý sai thứ tự có thể ghi đè trạng thái mới bằng trạng thái cũ.

Giải pháp tuỳ nguồn:

- Partition theo **orderId** và giữ thứ tự bên trong partition.
- So sánh version/sequence từ hệ thống nguồn trước khi cập nhật.
- Chuyển event thành thao tác “fetch current state” khi hợp đồng cho phép.
- Đặt unique key theo event ID và business version tại DB đích.

Một message được nhận lại sau timeout có thể là duplicate hợp lệ của mô hình **at-least-once**. Log lỗi nên phân biệt duplicate đã xử lý và lỗi hệ thống thực sự.

## 11. Quan sát: đo nhịp thực tế và hiệu quả nghiệp vụ

Báo cáo rằng job “đang chạy mỗi 2 giây” chưa đủ để đánh giá dữ liệu có được xử lý đúng hạn. Cần đo từ lúc nguồn cập nhật đến lúc hệ thống đích commit.

| Nhóm | Metric cần theo dõi | Ý nghĩa |
|---|---|---|
| Scheduler | Số lượt poll, khoảng cách giữa hai lượt thực tế, độ trễ kích hoạt | Có bị scheduler starvation, chạy chồng hoặc dồn lịch? |
| Source | Số message/poll, tỷ lệ poll rỗng, thời gian fetch, lỗi/timeout, quota | Poll quá dày hay nguồn chậm? |
| Backlog | Pending count, tuổi record cũ nhất, checkpoint lag, thời gian drain ước tính | Pipeline có theo kịp lượng dữ liệu mới? |
| Processing | Throughput thành công, duration p95/p99, concurrency, queue depth | Handler hoặc downstream là nút thắt? |
| Reliability | Retry attempts, duplicate count, claim lease expired, DLQ/quarantine, unknown result | Có xử lý lặp, bỏ sót hoặc công việc kẹt? |
| Downstream | DB connection pool, broker lag, HTTP 429/503, số lần circuit mở | Polling có đẩy lỗi sang dịch vụ khác? |

Dùng **Micrometer/Actuator** cho metric, log có **correlation ID**, **source name**, **poll cycle ID**, **record ID**, attempt và trạng thái checkpoint. Chỉ đặt nhãn có cardinality thấp như tên adapter hoặc loại lỗi; không dùng toàn bộ cursor, URL chứa token hay ID của từng bản ghi làm tag metric.

**Cảnh báo nên hướng tới kết quả:** backlog age vượt SLO, không có bản ghi xử lý thành công dù nguồn có công việc, liên tiếp không poll được, hoặc queue gần đầy. Tỷ lệ poll rỗng cao tự nó không nhất thiết báo sự cố: có thể nguồn ít thay đổi và hệ thống đang chờ đúng thiết kế.

## 12. Kiểm thử polling và notification

Một flow nên được kiểm thử ở ít nhất ba cấp: unit test chính sách, integration test adapter và fault-injection test cho môi trường nhiều instance hoặc phụ thuộc bên ngoài.

| Kịch bản | Tác động tạo ra | Kỳ vọng |
|---|---|---|
| MessageSource rỗng | **receive()** trả null | Kết thúc lượt poll, không phát message giả, không tăng lỗi |
| Batch lớn hơn giới hạn | Tạo nhiều hơn **maxMessagesPerPoll** phần tử sẵn sàng | Một chu kỳ không lấy vượt giới hạn số message; chu kỳ sau lấy tiếp |
| Handler chạy chậm | Chèn latency vào xử lý | Fixed delay được đo đúng và không phát tán vô hạn sang queue |
| Hạ nguồn quá tải | DB pool đầy, HTTP 429/503 | Backoff/bulkhead hoạt động, backlog tăng có kiểm soát |
| App crash sau claim, trước DONE | Dừng instance ở điểm kiểm soát | Lease/cơ chế recovery cho phép xử lý lại, không mất work item |
| App crash sau side effect, trước ACK | Commit DB đích rồi dừng | Idempotency ngăn tạo side effect lần hai |
| Hai pod cùng poll | Cho hai instance chạy chung nguồn | Claim nguyên tử hoặc partition tránh hai tác động nghiệp vụ |
| Webhook duplicate hoặc đảo thứ tự | Gửi lại cùng eventId, đổi thứ tự version | Dedupe, version check hoặc reconciliation giữ trạng thái đúng |
| Notification bị mất | Ngắt webhook trong một khoảng, nguồn vẫn lưu trạng thái | Poll đối soát đọc bù đầy đủ |
| Thay đổi timezone/lịch | Chạy thử cron ở timezone mong muốn | Thời điểm kích hoạt đúng yêu cầu, xử lý rõ hành vi khi miss schedule |
| SFTP file chưa xong | Upload nhiều đợt | Không xử lý file chưa hoàn tất, không bỏ sót file sau restart |

**Với poller, không viết test dựa thuần vào ngủ chờ số giây rồi đoán đã chạy.** Ưu tiên kiểm soát được thời điểm kích hoạt, fake MessageSource, đồng bộ bằng latch/event hoặc dùng test scheduler có thể điều khiển, và assert chính xác số lần gọi **receive()**, số message được xử lý và trạng thái checkpoint. Integration test chỉ bằng mock handler chưa thể chứng minh lease, failover, khả năng chạy nhiều pod hay cơ chế ACK của broker.

## 13. Tình huống tổng hợp: đồng bộ trạng thái vận chuyển từ đối tác

Một dịch vụ Spring Boot cập nhật trạng thái giao hàng. Đối tác có webhook báo thay đổi, đồng thời cung cấp HTTP API truy vấn cập nhật theo cursor. Yêu cầu: trạng thái hiển thị mới trong vài giây khi webhook ổn định, và cuối cùng phải nhận đủ thay đổi dù webhook bị mất tạm thời.

~~~mermaid
flowchart TD
    EXT["Partner shipping system"] -->|Webhook eventId| WEB["HTTP inbound / validate"]
    EXT -->|GET changes?cursor=...| POLL["Scheduled reconciliation poller"]
    WEB --> INBOX[("Inbox / dedupe by event ID")]
    POLL --> INBOX
    INBOX --> WORK["Worker idempotent"]
    WORK --> API["Fetch canonical shipment state if needed"]
    API --> DB[("Shipment DB with version check")]
    DB --> DONE["Mark DONE / advance committed cursor"]
    METRIC["Lag, errors, retry, pending age"] -.-> POLL
    METRIC -.-> WORK
~~~

Một cách phân chia trách nhiệm hợp lý:

1. **Webhook inbound:** xác thực chữ ký, timestamp/replay protection, schema; insert inbox với unique event ID; chỉ xác nhận sau khi dữ liệu đã ghi bền vững.
2. **Reconciliation poller:** chạy theo lịch phù hợp quota đối tác; đọc theo cursor hoặc lookback window, giới hạn kích thước mỗi page; ghi từng event/update vào inbox rồi commit checkpoint an toàn.
3. **Handler:** thực hiện đối soát trạng thái chuẩn, dùng shipment ID và version để bỏ qua cập nhật cũ; transaction DB đích bảo đảm không ghi trạng thái lùi.
4. **Error handling:** 429 thực hiện backoff theo đối tác; 5xx retry có hạn; 401/403 báo cấu hình; event độc hại/sai schema vào quarantine; timeout sau side effect được tra cứu trước khi gửi lại.
5. **Backpressure:** buffer bền vững, giới hạn số worker và số lệnh HTTP; khi hàng tồn đọng lớn, giảm nhịp poll hoặc ưu tiên xử lý inbox trước.
6. **Monitoring:** độ trễ từ event time tới DB commit, tuổi bản ghi pending, số event đọc bù, duplicate rate, API quota và checkpoint lag.

Nếu webhook nhận một event và poller đọc cùng event, đây là hành vi bình thường: **dedupe/idempotency** phải khiến cập nhật đích chỉ có tác động nghiệp vụ một lần. Nếu sự cố mất mạng kéo dài hơn retention của API, runbook phải có phương án full backfill hoặc đối soát lại tất cả shipment còn hiệu lực.

## 14. Lỗi thiết kế thường gặp

| Lỗi thiết kế | Hậu quả | Cách sửa |
|---|---|---|
| Poll quá nhanh để giảm latency | Nguồn bị đè, nhiều lần poll rỗng, phát sinh 429 | Dựa vào SLO, source update frequency, backlog và quota |
| Không giới hạn **maxMessagesPerPoll** | Một lượt có thể chiếm scheduler lâu khi nguồn luôn còn dữ liệu | Giới hạn message/batch, phân bổ tài nguyên giữa các flow |
| Lấy dữ liệu bằng SELECT rồi xử lý ở nhiều pod | Một record có thể bị xử lý trùng | Atomic claim/partition/leader và idempotency |
| Đánh dấu DONE trước side effect | Crash có thể làm mất công việc | Commit theo ranh giới rõ ràng, inbox/outbox nếu cần |
| Xem webhook 2xx là hoàn tất nghiệp vụ | Đối tác tin dữ liệu đã đồng bộ dù worker vẫn đang chạy | Định nghĩa rõ “accepted” và “processed”, theo dõi trạng thái riêng |
| Retry mọi exception | Amplify lỗi hoặc chạy lại nghiệp vụ nhiều lần | Phân loại lỗi, idempotency, bounded retry và DLQ |
| Dùng offset trên bảng trạng thái thay đổi | Bỏ sót hàng do dịch vị trí | Claim/Keyset/cursor ổn định và checkpoint |
| Queue nội bộ không giới hạn | Tăng RAM, crash và mất dữ liệu chưa commit | Bounded buffer hoặc durable broker |
| Chỉ đo số lần trigger | Không phát hiện lag, backlog và dữ liệu sai | Đo end-to-end lag, checkpoint, success và duplicate |
| Coi cron là cơ chế HA phân tán | Nhiều pod cùng chạy một job | Tách lịch với phân phối ownership, chứng minh xử lý an toàn |

## 15. Checklist trước khi triển khai

- [ ] Đã xác định nguồn nào **polling**, nguồn nào **notification**, trường hợp nào cần kết hợp đối soát.
- [ ] Hợp đồng nêu rõ event ID, message ID, thứ tự, cursor, retention, retry và mức bảo đảm giao nhận.
- [ ] Poller có khoảng chạy, batch/maxMessagesPerPoll, timeout và giới hạn concurrency cụ thể.
- [ ] Đã cân bằng nhịp lấy dữ liệu với quota của nguồn, throughput downstream và SLO end-to-end.
- [ ] Có backpressure, bounded queue hoặc durable buffer; hành vi khi queue đầy đã xác định.
- [ ] Claim/checkpoint/ACK có ranh giới transaction rõ ràng; có cơ chế recovery sau crash.
- [ ] Mọi tác động nghiệp vụ quan trọng có idempotency và cách đối soát kết quả không xác định.
- [ ] Nhiều instance được kiểm thử để tránh mất hoặc xử lý trùng dữ liệu ngoài dự kiến.
- [ ] Webhook/broker có xác thực, replay protection và chính sách retry/DLQ phù hợp.
- [ ] Có metric backlog age, poll duration, effective throughput, lỗi, retry, duplicate và end-to-end lag.
- [ ] Đã thử lỗi mạng, 429/503, file chưa hoàn tất, dữ liệu đến muộn, mất webhook và restart giữa quá trình xử lý.

**Kết luận nghiệp vụ:** polling tạo nhịp **đi tìm dữ liệu**, còn thông báo sự kiện giúp nguồn **báo dữ liệu đã thay đổi**. Spring Integration cung cấp adapter, poller và kênh truyền để nối các bước, nhưng độ tin cậy của luồng còn phụ thuộc vào việc giới hạn tốc độ, nhận lại dữ liệu an toàn, commit checkpoint đúng thời điểm, xử lý trùng và quan sát được backlog trong cả điều kiện bình thường lẫn khi lỗi.
