# Điều tiết tốc độ nhận và xử lý lại sự kiện

Một consumer Event Hubs có thể đọc dữ liệu nhanh hơn tốc độ mà database, API nội bộ hoặc hệ thống phân tích xử lý được. Khi đó, event tích tụ trong bộ đệm cục bộ, bộ nhớ tăng, độ trễ xử lý kéo dài hoặc downstream bị quá tải. Ở chiều ngược lại, khi consumer bị dừng hoặc cần xây dựng lại read model, nhóm phát triển phải đọc lại một phần hay toàn bộ event lịch sử. Hai nhu cầu này liên quan trực tiếp: **điều tiết tốc độ nhận/xử lý** giúp hệ thống theo kịp tải trong vận hành bình thường; **replay có kiểm soát** giúp phục hồi và tái xử lý dữ liệu mà không gây side effect ngoài ý muốn.

Bài học thuộc chương **Sự kiện Azure** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa cloud provider. Trong bài này, trọng tâm là Azure Event Hubs, Azure SDK for Java và cấu hình Spring Cloud Azure cho consumer.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **prefetch**, batch receive, concurrency limit, rate limit, backpressure và throttling.
- Giải thích vì sao tăng số consumer instance không phải lúc nào cũng tăng throughput.
- Điều chỉnh **prefetchCount**, **maxBatchSize**, **maxWaitTime** và tốc độ xử lý downstream.
- Thiết kế consumer không tạo hàng đợi nội bộ vô hạn và không checkpoint event chưa xử lý bền vững.
- Phân loại throttling từ dịch vụ với tình trạng consumer tự làm chậm để bảo vệ downstream.
- Replay từ earliest, latest, timestamp, offset hoặc sequence number trong phạm vi retention.
- Dùng consumer group riêng để replay mà không làm thay đổi tiến độ consumer production.
- Dùng Event Hubs Capture hoặc archive khi cần đọc lại dữ liệu đã hết retention.
- Tích hợp EventProcessorClient, EventHubConsumerClient hoặc Spring Cloud Stream binder với Spring Boot.
- Xây dựng kiểm thử cho backpressure, checkpoint, duplicate, replay, throttling và chi phí.

## 2. Phân biệt điều tiết, backpressure và throttling

Các khái niệm thường được dùng lẫn nhau nhưng tác động ở những vị trí khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ trong Event Hubs |
|---|---|---|
| **Prefetch** | Số event được yêu cầu trước và đệm cục bộ | Consumer giữ sẵn event trong bộ nhớ để giảm round-trip |
| **Batch receive** | Gom nhiều event thành một lần callback | Xử lý 100 event cùng partition trong một batch |
| **Concurrency limit** | Giới hạn số tác vụ đang chạy cùng lúc | Tối đa 12 thao tác ghi DB đồng thời |
| **Rate limit** | Giới hạn số thao tác trong một khoảng thời gian | Không vượt 200 lần gọi API/giây |
| **Backpressure** | Khi downstream chậm, làm chậm upstream hoặc ngừng yêu cầu thêm dữ liệu | Callback xử lý chậm khiến processor không tiếp tục lấy thêm event từ partition đó |
| **Throttling** | Dịch vụ từ chối hoặc hạn chế request do chạm capacity/quota/chính sách | Event Hubs báo lỗi tạm thời khi namespace bị quá tải |

**prefetchCount** không phải giới hạn event/giây. Nó điều chỉnh số event được đệm sẵn trên mỗi partition. Một consumer có thể prefetch 200 event rồi xử lý 2.000 event/giây nếu downstream đủ nhanh; cũng có thể chỉ xử lý 10 event/giây nếu handler chậm.

**Backpressure** là cơ chế bảo vệ luồng xử lý: nếu callback không hoàn tất, EventProcessorClient không tiếp tục đẩy thêm event xuống callback đó và không yêu cầu thêm event từ partition theo nhịp bình thường. **Rate limit** là chính sách tốc độ rõ ràng do ứng dụng đặt ra. **Throttling** có thể đến từ Event Hubs hoặc dịch vụ downstream và cần chẩn đoán theo metric/lỗi cụ thể.

## 3. Đường đi của event và các điểm điều tiết

~~~mermaid
flowchart LR
    P["Producer"] --> EH["Event Hubs partition"]
    EH --> PF["Prefetch buffer"]
    PF --> BA["Batch / callback"]
    BA --> RL["Rate + concurrency control"]
    RL --> DB["Database / downstream API"]
    DB --> CP["Checkpoint store"]
    CP --> NEXT["Read next events"]
    RL -. "Downstream chậm" .-> BP["Backpressure"]
    BP -. "Giảm tốc nhận" .-> PF
~~~

Ứng dụng có thể kiểm soát tải ở nhiều tầng:

1. **Receive buffer:** giới hạn số event prefetch theo partition.
2. **Batch:** chọn số event và thời gian chờ để gom batch.
3. **Callback:** xử lý tuần tự hoặc theo concurrency được kiểm soát.
4. **Downstream:** giới hạn connection pool, request rate, bulkhead và timeout.
5. **Checkpoint:** ghi tiến độ theo batch/interval phù hợp, tránh ghi quá thường xuyên.
6. **Replay:** giới hạn tốc độ đọc lại để không gây tải đột biến lên hệ thống đích.

Không có một tham số đơn lẻ giải quyết mọi vấn đề. Tăng batch size có thể giảm overhead nhưng tăng latency và memory; giảm prefetch có thể giảm heap nhưng làm giảm throughput; tăng consumer instance có thể tăng tải DB hoặc gây rebalance.

## 4. Event Hubs nhận và phân phối event như thế nào?

Event Hubs là một event stream được chia thành partition. Consumer đọc theo offset trong consumer group; EventProcessorClient quản lý partition ownership và checkpoint. Event Hubs không dùng mô hình lock/complete cho từng event như Service Bus.

Các hệ quả quan trọng:

- Event được lưu trong partition theo thứ tự append; thứ tự chỉ có ý nghĩa trong từng partition.
- Nhiều consumer group có thể đọc cùng stream độc lập.
- Các instance trong cùng consumer group chia partition; một partition không được chia thành nhiều owner đồng thời để tăng parallelism trong cùng group.
- EventProcessorClient giao event cho callback; callback chậm có thể làm partition đó xử lý chậm.
- Prefetch buffer nằm trong bộ nhớ của process; restart có thể làm event chưa checkpoint được đọc lại.
- Checkpoint lưu vị trí đọc đã xử lý, không phải xác nhận nghiệp vụ exactly-once.

Vì vậy, điều tiết tốc độ nhận phải được thiết kế cùng checkpoint và idempotency. Nếu ứng dụng làm chậm callback để bảo vệ database, lag có thể tăng nhưng dữ liệu vẫn còn trong retention. Nếu checkpoint vượt qua event chưa được xử lý, backpressure không thể cứu dữ liệu đã bị bỏ qua.

## 5. Điều chỉnh prefetchCount

### 5.1. Prefetch hoạt động ra sao?

Azure SDK for Java cho phép cấu hình **prefetchCount** trên EventProcessorClientBuilder. Giá trị mặc định hiện được tài liệu SDK mô tả là **500 event cho mỗi partition**. Khi receive link có credit, Event Hubs có thể gửi trước số event đó; client đưa chúng vào bộ đệm cục bộ để callback có dữ liệu xử lý ngay mà không cần chờ một request mạng mới.

- Prefetch quá thấp: client phải yêu cầu thêm credit thường xuyên, tăng round-trip/ACK và có thể giảm throughput.
- Prefetch quá cao: nhiều event nằm trong bộ nhớ chờ xử lý, làm tăng heap, GC và nguy cơ OOM.
- Payload lớn hoặc handler chậm: nên bắt đầu với prefetch nhỏ hơn.
- Payload nhỏ, luồng đều và handler nhanh: có thể thử prefetch cao hơn nếu heap còn dư.

Prefetch được áp dụng **theo partition**, không phải một tổng duy nhất cho toàn ứng dụng.

### 5.2. Ước lượng bộ nhớ

Giả sử một instance đang sở hữu 12 partition và **prefetchCount = 500**:

\[
12 \times 500 = 6.000 \text{ event được đệm tối đa theo cấu hình}
\]

Nếu payload trung bình khoảng 8 KiB, riêng dữ liệu payload thô tương đương khoảng 46,9 MiB. Heap thực tế sẽ lớn hơn do object metadata, byte array, header, collection, runtime và các buffer khác. Đây là phép ước lượng tải bộ nhớ, không phải giới hạn heap chính xác.

Nếu instance sở hữu nhiều partition hoặc event có kích thước biến động lớn, hãy đo heap ở tải đỉnh. Không chọn **prefetchCount** chỉ theo số event/giây.

### 5.3. Cấu hình trong EventProcessorClient

Ví dụ cấu hình SDK trực tiếp trong Spring Boot:

~~~java
import com.azure.messaging.eventhubs.EventProcessorClient;
import com.azure.messaging.eventhubs.EventProcessorClientBuilder;
import com.azure.messaging.eventhubs.checkpointstore.blob.BlobCheckpointStore;
import com.azure.storage.blob.BlobContainerAsyncClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class EventProcessorConfiguration {

    @Bean(destroyMethod = "stop")
    EventProcessorClient eventProcessorClient(
            EventHubProperties properties,
            DefaultAzureCredential credential,
            BlobContainerAsyncClient checkpointContainer,
            OrderEventHandler handler) {

        return new EventProcessorClientBuilder()
                .consumerGroup(properties.consumerGroup())
                .credential(
                        properties.namespace(),
                        properties.eventHubName(),
                        credential)
                .checkpointStore(new BlobCheckpointStore(checkpointContainer))
                .prefetchCount(200)
                .processEvent(eventContext ->
                        handler.process(eventContext.getEventData()))
                .processError(error ->
                        logger.warn("Event processor error",
                                error.getThrowable()))
                .buildEventProcessorClient();
    }
}
~~~

Giá trị **200** là điểm bắt đầu minh họa, không phải khuyến nghị chung. Trong production cần đưa nó vào cấu hình theo môi trường, đo heap, callback duration, consumer lag và throughput trước khi điều chỉnh. Không tạo client mới cho mỗi request; dùng một bean theo lifecycle ứng dụng.

## 6. Batch receive và processEventBatch

### 6.1. Khi nào nên dùng batch?

**processEvent** gọi callback cho từng event. Cách này dễ hiểu và phù hợp tải thấp hoặc vừa. Với luồng lớn, chi phí gọi callback liên tục có thể làm giảm hiệu năng. **processEventBatch** nhận nhiều event trong một callback, giảm overhead và phù hợp khi downstream hỗ trợ batch write.

Hai tham số quan trọng:

- **maxBatchSize:** số event tối đa mong muốn trong một batch.
- **maxWaitTime:** thời gian tối đa chờ gom batch trước khi callback được gọi với số event hiện có; batch có thể nhỏ hơn maxBatchSize.

Batch lớn hơn có thể tăng throughput và giảm overhead, nhưng cũng tăng thời gian chờ, bộ nhớ và lượng event có thể phải replay khi một batch thất bại.

### 6.2. Chọn batch size theo latency và payload

| Kịch bản | Cách bắt đầu |
|---|---|
| Event nhỏ, traffic đều, DB hỗ trợ bulk insert | Thử batch lớn hơn và đo throughput |
| Event lớn, xử lý CPU nặng | Batch nhỏ để kiểm soát heap |
| Traffic thưa, cần latency thấp | Batch nhỏ và maxWaitTime ngắn |
| Downstream có giới hạn request | Batch theo kích thước mà API/DB hỗ trợ |
| Một event lỗi có thể làm hỏng cả batch | Dùng manual checkpoint, dedup và quarantine theo từng event |

Không đặt **maxWaitTime** dài chỉ để đạt đủ batch size nếu SLO yêu cầu event được xử lý nhanh. Với traffic thấp, chờ đủ batch có thể làm latency tăng dù hệ thống không quá tải.

### 6.3. Ví dụ batch callback với EventProcessorClient

**EventBatchContext** cung cấp danh sách event của một partition và phương thức cập nhật checkpoint cho event cuối cùng trong batch. Chỉ checkpoint khi mọi event trong batch đã được xử lý bền vững hoặc đã được quarantine theo policy.

~~~java
import com.azure.messaging.eventhubs.EventData;
import com.azure.messaging.eventhubs.EventProcessorClient;
import com.azure.messaging.eventhubs.EventProcessorClientBuilder;
import com.azure.messaging.eventhubs.checkpointstore.blob.BlobCheckpointStore;
import java.time.Duration;
import java.util.List;

EventProcessorClient processor = new EventProcessorClientBuilder()
        .consumerGroup("orders-replay")
        .credential(namespace, eventHubName, credential)
        .checkpointStore(new BlobCheckpointStore(checkpointContainer))
        .prefetchCount(200)
        .processEventBatch(batchContext -> {
            List<EventData> events = batchContext.getEvents();
            if (events.isEmpty()) {
                return;
            }

            for (EventData event : events) {
                // Mỗi event phải được xử lý idempotent và commit bền vững.
                handler.processAndCommit(event);
            }

            // Chỉ checkpoint event cuối batch sau khi toàn bộ batch an toàn.
            batchContext.updateCheckpoint();
        }, 100, Duration.ofSeconds(1))
        .processError(error ->
                logger.warn("Event processor error",
                        error.getThrowable()))
        .buildEventProcessorClient();
~~~

Đoạn code là ví dụ cấu trúc; **namespace**, **eventHubName**, **credential**, **checkpointContainer**, **handler** và **logger** là dependency đã được cấu hình. Trong Spring Boot, đặt processor trong bean và quản lý **start()**/**stop()** theo lifecycle thay vì tạo processor cục bộ trong method request.

Nếu event thứ 80 lỗi sau khi 79 event trước đã commit, callback không nên checkpoint batch. Khi batch được đọc lại, 79 event đầu sẽ xuất hiện lại; inbox/unique event ID phải ngăn side effect lặp. Nếu event lỗi là poison event, chỉ checkpoint qua nó sau khi quarantine đã ghi bền vững và policy cho phép tiếp tục.

## 7. Backpressure trong callback

EventProcessorClient gọi callback theo từng partition. Callback xử lý lâu sẽ làm chậm việc phát thêm event xuống ứng dụng và làm giảm nhịp yêu cầu event tiếp theo từ partition đó. Đây là một dạng backpressure tự nhiên.

### 7.1. Những cách tạo backpressure an toàn

- Xử lý đồng bộ trong callback nếu công việc có thời gian ổn định và phù hợp throughput.
- Giới hạn số thao tác DB/API đồng thời bằng bulkhead hoặc semaphore.
- Dùng connection pool có kích thước phù hợp với tổng số partition và instance.
- Nếu chuyển công việc sang worker khác, chỉ checkpoint sau khi đã ghi công việc vào **hàng đợi bền vững** hoặc transaction/outbox; không checkpoint chỉ vì đã đẩy vào queue trong RAM.
- Giới hạn kích thước hàng đợi nội bộ; khi đầy, chặn callback hoặc trả lỗi theo policy thay vì tạo queue vô hạn.
- Dùng batch write nếu downstream hỗ trợ và có thể giữ tính nguyên tử cần thiết.

### 7.2. Tránh queue nội bộ không giới hạn

~~~mermaid
flowchart TD
    EH["Event Hubs"] --> CB["Processor callback"]
    CB --> Q{"Bounded queue còn chỗ?"}
    Q -->|Có| W["Worker / database"]
    Q -->|Không| BP["Block hoặc giảm tốc"]
    W --> COMMIT["Commit side effect"]
    COMMIT --> CP["Checkpoint"]
    BP -. "Không checkpoint" .-> CB
~~~

Nếu callback đưa event vào queue RAM không giới hạn rồi checkpoint ngay, ứng dụng có thể nhận event nhanh hơn khả năng xử lý, tăng heap cho tới OOM. Nếu process chết, các event đã checkpoint nhưng chỉ nằm trong RAM sẽ mất khỏi luồng xử lý nghiệp vụ.

Hàng đợi nội bộ chỉ an toàn để checkpoint ngay khi việc enqueue đã tạo ra một cam kết bền vững, ví dụ insert vào bảng work/outbox trong transaction hoặc publish sang một broker bền vững khác và nhận xác nhận phù hợp.

### 7.3. Giới hạn concurrency khác giới hạn tốc độ

Semaphore/bulkhead giới hạn số tác vụ đang chạy đồng thời. Nó không giới hạn số thao tác mỗi giây. Nếu một request hoàn tất trong 5 ms, 10 permit có thể cho phép tốc độ rất cao. Rate limiter giới hạn số lần gọi trong một khoảng thời gian; hai cơ chế thường cần phối hợp.

Nếu dùng rate limiter theo từng pod, tổng rate có thể bằng rate/pod nhân số replica. Muốn giới hạn toàn deployment, cần chia quota cho mỗi replica hoặc dùng một limiter phân tán. Cũng cần xác định rate cap áp dụng cho từng partition, từng tenant hay toàn dịch vụ.

## 8. Giới hạn tốc độ xử lý downstream

Ví dụ: Event Hubs nhận trung bình 1.000 event/giây, nhưng database chỉ xử lý ổn định 700 event/giây. Nếu không điều tiết, backlog tăng xấp xỉ 300 event/giây. Sau 5 phút, lượng tồn đọng có thể tăng khoảng 90.000 event, chưa tính burst và retry.

Có thể dùng:
- **Rate limiter:** giới hạn số lần gọi API hoặc ghi DB theo giây/phút.
- **Bulkhead:** giới hạn số tác vụ đồng thời để không chiếm hết thread/connection.
- **Timeout:** dừng chờ downstream vô hạn.
- **Batch write:** giảm overhead theo từng event.
- **Adaptive concurrency:** giảm concurrency khi latency/error tăng và tăng lại khi hệ thống ổn định.
- **Producer throttling:** khi có thể, phản hồi trạng thái quá tải hoặc giảm tốc producer upstream.

Không retry liên tục khi rate limiter từ chối vì điều đó làm tăng tải. Nếu callback chưa thể xử lý event, giữ event chưa checkpoint và áp dụng backpressure hoặc lưu vào nơi bền vững để xử lý sau.

### 8.1. Mẫu kết hợp RateLimiter và Bulkhead

Ví dụ dưới đây mô tả cách kết hợp Resilience4j ở service layer; cấu hình rate/timeout là ví dụ cần điều chỉnh theo SLO:

~~~java
import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.ratelimiter.RateLimiter;
import org.springframework.stereotype.Service;

@Service
class DownstreamEventWriter {
    private final RateLimiter rateLimiter;
    private final Bulkhead bulkhead;
    private final DatabaseWriter databaseWriter;

    DownstreamEventWriter(
            RateLimiter rateLimiter,
            Bulkhead bulkhead,
            DatabaseWriter databaseWriter) {
        this.rateLimiter = rateLimiter;
        this.bulkhead = bulkhead;
        this.databaseWriter = databaseWriter;
    }

    void write(EventRecord record) {
        if (!rateLimiter.acquirePermission()) {
            throw new IllegalStateException("Downstream rate limit reached");
        }

        Runnable write = Bulkhead.decorateRunnable(
                bulkhead,
                () -> databaseWriter.writeIdempotently(record));

        write.run();
    }
}
~~~

Ví dụ này giới hạn rate và concurrency trong một instance. Nếu **write** ném exception, handler không được checkpoint event như thể đã thành công. Cần xác định exception nào có thể retry, exception nào phải quarantine và cách xử lý kết quả commit không rõ. Không dùng cùng một limiter cục bộ để tuyên bố đã áp một global rate limit cho nhiều replica.

## 9. Điều tiết qua Spring Cloud Stream Event Hubs binder

Spring Cloud Azure Stream Event Hubs binder cung cấp các cấu hình consumer để điều chỉnh prefetch, batch, checkpoint và initial partition position.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        consume-in-0:
          consumer:
            batch-mode: true
    eventhubs:
      bindings:
        consume-in-0:
          consumer:
            prefetch-count: 200
            batch:
              max-size: 100
              max-wait-time: 1s
            checkpoint:
              mode: MANUAL
~~~

Ý nghĩa:
- **batch-mode: true:** function nhận payload dạng danh sách event.
- **prefetch-count:** số event được consumer chủ động nhận và xếp hàng cục bộ theo partition.
- **batch.max-size:** kích thước batch tối đa mong muốn.
- **batch.max-wait-time:** thời gian chờ gom batch.
- **checkpoint.mode: MANUAL:** ứng dụng tự gọi Checkpointer sau khi xử lý bền vững.

Tên property và behavior phải khớp BOM Spring Cloud Azure đang dùng. **BATCH** checkpoint mode là cơ chế tự động của binder; nếu cần đảm bảo transaction nghiệp vụ đã commit trước checkpoint, chọn **MANUAL** và gọi Checkpointer sau khi service transaction hoàn tất. Không giả định **batch-mode** tự động đồng nghĩa với checkpoint an toàn cho database.

### 9.1. Consumer function nhận batch

~~~java
import com.azure.spring.messaging.AzureHeaders;
import com.azure.spring.messaging.checkpoint.Checkpointer;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import java.util.List;
import java.util.function.Consumer;

@Bean
Consumer<Message<List<String>>> consume(OrderService orderService) {
    return message -> {
        List<String> events = message.getPayload();

        // Xử lý và commit toàn bộ batch theo transaction phù hợp.
        orderService.processBatchIdempotently(events);

        Checkpointer checkpointer = message.getHeaders()
                .get(AzureHeaders.CHECKPOINTER, Checkpointer.class);

        if (checkpointer == null) {
            throw new IllegalStateException(
                    "Manual checkpoint header is missing");
        }

        checkpointer.success().block();
    };
}
~~~

Đây là skeleton minh họa; cần đối chiếu kiểu payload/header và cách checkpoint batch theo phiên bản binder. Nếu batch có event lỗi, không gọi success cho toàn batch trừ khi từng event lỗi đã được quarantine bền vững và chính sách cho phép tiếp tục. Trong ứng dụng reactive, compose publisher thay vì gọi **block()** trên event loop.

## 10. Khi nào cần giảm tốc độ nhận?

Không phải mọi consumer lag đều cần giảm tốc độ nhận. Nếu handler nhanh và downstream còn dư năng lực, giảm prefetch quá thấp có thể làm throughput tệ hơn.

| Triệu chứng | Nguyên nhân có thể | Hành động ưu tiên |
|---|---|---|
| Heap tăng, GC liên tục, OOM | Prefetch cao, event lớn, queue nội bộ vô hạn | Giảm prefetch, giới hạn buffer, đo payload |
| DB connection pool cạn | Concurrency vượt năng lực DB | Bulkhead, pool sizing, batch write |
| Event processing latency cao | Handler chậm hoặc API ngoài chậm | Trace từng bước, timeout, rate limit |
| Consumer lag tăng nhưng CPU thấp | Chờ DB/network, partition không được sở hữu hoặc callback block | Kiểm tra downstream, ownership, network |
| Throttling từ Event Hubs tăng | Namespace capacity/quota hoặc burst | Kiểm tra metrics, giảm burst, xem xét capacity |
| Một partition lag, partition khác bình thường | Hot partition hoặc event đặc biệt nặng | Kiểm tra key distribution và per-partition lag |
| Checkpoint age tăng nhưng handler đã xử lý | Checkpoint store chậm hoặc checkpoint quá thưa | Kiểm tra Blob, chọn checkpoint interval |
| Duplicate tăng sau deploy | Replay do checkpoint/rebalance | Kiểm tra checkpoint và idempotency |

Phân biệt lỗi ở Event Hubs với lỗi ở database/HTTP API. Nếu downstream từ chối request, tăng throughput hoặc thêm consumer có thể làm sự cố nặng hơn. Nếu consumer lag tăng do thiếu partition ownership hoặc processor dừng, giảm prefetch không giải quyết nguyên nhân.

## 11. Throttling và retry

### 11.1. Phân loại lỗi

- **Transient service/network error:** SDK có retry policy cho một số lỗi tạm thời.
- **Quota/capacity throttling:** dịch vụ hạn chế request; cần xem namespace metrics, SKU/capacity và mức sử dụng.
- **Authentication/authorization:** sai credential hoặc thiếu role; không retry vô hạn.
- **Invalid event/schema:** dữ liệu không hợp lệ; sửa hoặc quarantine.
- **Downstream throttling:** database/API giới hạn request; điều tiết tại consumer và tôn trọng retry guidance của downstream.

Azure SDK for Java biểu diễn nhiều lỗi Event Hubs qua exception AMQP. Kiểm tra **isTransient**, error condition và error context thay vì chỉ nhìn message text. Retry policy của SDK không thay thế rate limiter nghiệp vụ.

### 11.2. Tránh retry storm

Nếu SDK retry 3 lần, service layer retry 3 lần và job scheduler cũng retry 3 lần, một event có thể gây nhiều lần gọi downstream. Tổng attempts có thể tăng theo tích của các tầng retry. Hãy chọn một nơi chịu trách nhiệm retry chính, giới hạn attempts và đặt deadline tổng.

Khi timeout sau khi ghi DB hoặc gửi event, kết quả có thể chưa rõ. Giữ event ID ổn định và kiểm tra inbox/idempotency record trước khi lặp side effect. Không checkpoint event chỉ vì một lần retry đã bắt đầu.

## 12. Checkpoint và điều tiết tốc độ

Checkpoint có chi phí mạng vì mỗi lần ghi vào Blob checkpoint store là một thao tác HTTP. Checkpoint sau mọi event có thể làm giảm throughput đáng kể. Checkpoint quá thưa thì replay window lớn hơn khi process chết.

| Chiến lược | Ưu điểm | Đánh đổi |
|---|---|---|
| Mỗi event | Replay ít event | Nhiều Blob write, giảm throughput |
| Mỗi N event | Ít thao tác checkpoint | Có thể đọc lại một đoạn event đã xử lý |
| Theo thời gian | Điều chỉnh được replay window theo thời gian | Số event replay phụ thuộc traffic |
| Sau batch commit | Gắn tiến độ với batch đã bền vững | Phải bảo đảm không checkpoint vượt event chưa hoàn tất |

Với batch callback, checkpoint chỉ ghi vị trí event cuối batch. Nếu một event ở giữa batch thất bại, toàn batch có thể được đọc lại; dedup/inbox phải xử lý các event trước đó đã commit. Nếu xử lý bất đồng bộ, chỉ checkpoint tới vị trí liên tục mà mọi event trước đó đã hoàn tất hoặc được quarantine bền vững.

Checkpoint store không phải nơi archive event. Nó không giữ payload và không kéo dài retention.

## 13. Replay là gì và khi nào cần?

**Replay** là đọc lại event lịch sử từ một vị trí trước đó để khôi phục, kiểm chứng hoặc xây dựng lại kết quả. Các tình huống thường gặp:

- Consumer bị dừng nhưng dữ liệu còn trong retention.
- Handler trước đây có bug và cần xử lý lại event sau khi sửa.
- Cần dựng lại projection/read model từ event gốc.
- Cần chạy thêm consumer mới như fraud detection hoặc analytics trên dữ liệu lịch sử.
- Cần đối soát một khoảng thời gian sau incident.
- Cần đọc archive dài hạn sau khi dữ liệu đã hết retention trong Event Hubs.

Replay khác với **resume**:
- Resume tiếp tục từ checkpoint hiện có.
- Replay chủ động bắt đầu từ earliest, timestamp, offset hoặc sequence number cũ hơn.
- Consumer group mới có tiến độ đọc độc lập; nó không reset checkpoint của production group.

## 14. Chọn vị trí bắt đầu replay

EventPosition có thể biểu diễn:
- **earliest():** event sớm nhất còn trong retention.
- **latest():** event mới được enqueue sau thời điểm bắt đầu đọc.
- **fromEnqueuedTime(Instant):** event từ một thời điểm enqueue.
- **fromOffset(String):** vị trí theo offset.
- **fromSequenceNumber(long, boolean):** vị trí theo sequence number và lựa chọn inclusive/exclusive.

Offset và sequence number thuộc từng partition; khi replay toàn event hub, phải áp dụng vị trí phù hợp cho từng partition. Timestamp enqueue giúp chọn theo thời gian nhưng không thay thế aggregate version hoặc thứ tự nghiệp vụ.

### 14.1. Initial position chỉ dùng khi chưa có checkpoint

EventProcessorClient ưu tiên checkpoint đã lưu cho consumer group/partition. **initialPartitionEventPosition** chỉ được dùng khi checkpoint cho partition đó chưa tồn tại. Vì vậy, muốn replay an toàn thường nên dùng **consumer group riêng** và checkpoint store logic riêng, rồi đặt initial position rõ ràng.

Không thay initial position trong cấu hình của consumer group đang có checkpoint và kỳ vọng processor tự đọc lại từ đầu. Cũng không xóa checkpoint production để replay nếu chưa dừng toàn bộ processor và chưa có kế hoạch đối soát.

## 15. Replay bằng EventProcessorClient và consumer group riêng

Ví dụ tạo processor cho một replay run. Consumer group và checkpoint store phải dành riêng cho replay; **replayFrom** là thời điểm bắt đầu đã được xác định theo yêu cầu nghiệp vụ.

~~~java
import com.azure.messaging.eventhubs.EventData;
import com.azure.messaging.eventhubs.EventPosition;
import com.azure.messaging.eventhubs.EventProcessorClient;
import com.azure.messaging.eventhubs.EventProcessorClientBuilder;
import com.azure.messaging.eventhubs.checkpointstore.blob.BlobCheckpointStore;
import com.azure.messaging.eventhubs.models.EventBatchContext;
import java.time.Duration;
import java.time.Instant;
import java.util.List;

EventProcessorClient replayProcessor = new EventProcessorClientBuilder()
        .consumerGroup("orders-replay")
        .credential(namespace, eventHubName, credential)
        .checkpointStore(new BlobCheckpointStore(replayCheckpointContainer))
        .initialPartitionEventPosition(
                partitionId -> EventPosition.fromEnqueuedTime(replayFrom))
        .prefetchCount(100)
        .processEventBatch(batch -> {
            List<EventData> events = batch.getEvents();
            if (events.isEmpty()) {
                return;
            }

            for (EventData event : events) {
                replayHandler.processIdempotently(event);
            }

            batch.updateCheckpoint();
        }, 50, Duration.ofSeconds(2))
        .processError(error ->
                logger.warn("Replay processor error",
                        error.getThrowable()))
        .buildEventProcessorClient();
~~~

Đây là ví dụ cấu trúc; **namespace**, **eventHubName**, **credential**, **replayCheckpointContainer**, **replayHandler** và **logger** là dependency đã được cấu hình. Khởi động processor theo lifecycle có giới hạn thời gian và tốc độ. Sau replay, dừng processor và lưu kết quả run để có thể đối soát.

Lưu ý:
- Nếu replay group/checkpoint store đã có checkpoint, initial position không ghi đè checkpoint cũ.
- Nếu một batch lỗi giữa chừng, không gọi **updateCheckpoint**; event đã xử lý trước đó có thể được đọc lại.
- Giữ event ID gốc và dùng idempotency ở đích.
- Không replay đồng thời nhiều bản sao cùng một business side effect nếu chưa có cơ chế dedup.
- Replay có thể làm tăng outgoing throughput, Blob checkpoint operations, DB writes và chi phí network.

## 16. Replay một partition bằng EventHubConsumerClient

Khi cần đọc một partition hoặc một khoảng nhỏ để điều tra, EventHubConsumerClient cho phép chỉ định partition, số event tối đa, vị trí bắt đầu và thời gian chờ:

~~~java
import com.azure.messaging.eventhubs.EventHubClientBuilder;
import com.azure.messaging.eventhubs.EventHubConsumerClient;
import com.azure.messaging.eventhubs.EventPosition;
import com.azure.messaging.eventhubs.models.PartitionEvent;
import com.azure.core.util.IterableStream;
import java.time.Duration;

try (EventHubConsumerClient consumer = new EventHubClientBuilder()
        .credential(namespace, eventHubName, credential)
        .consumerGroup(replayConsumerGroup)
        .prefetchCount(100)
        .buildConsumerClient()) {

    IterableStream<PartitionEvent> events =
            consumer.receiveFromPartition(
                    partitionId,
                    100,
                    EventPosition.fromEnqueuedTime(replayFrom),
                    Duration.ofSeconds(5));

    for (PartitionEvent partitionEvent : events) {
        replayHandler.inspect(partitionEvent.getData());
    }
}
~~~

Cách này hữu ích cho một lần đọc có giới hạn hoặc công cụ điều tra. EventHubConsumerClient là consumer cấp thấp: ứng dụng phải tự quản lý partition, vị trí tiếp theo, checkpoint bền vững và recovery. Nó không tự cân bằng ownership trên toàn partition như EventProcessorClient.

Nếu cần replay tất cả partition trong thời gian dài hoặc chạy nhiều instance, EventProcessorClient với consumer group riêng thường phù hợp hơn.

## 17. Replay từ Event Hubs Capture khi retention không đủ

Event Hubs chỉ giữ event trong khoảng retention theo SKU/cấu hình. Nếu consumer ngừng lâu hơn thời gian đó, offset cũ có thể không còn dữ liệu để đọc. **Event Hubs Capture** có thể ghi stream ra Azure Blob Storage hoặc Data Lake Storage theo partition, thường ở định dạng Avro.

Quy trình replay archive:
1. Xác định khoảng thời gian và partition cần khôi phục.
2. Đọc file Capture tương ứng từ Blob/ADLS.
3. Giải mã Avro và kiểm tra schema/metadata.
4. Đưa event vào một pipeline replay riêng hoặc ghi vào destination mới.
5. Giữ event ID gốc, thêm replay run ID và kiểm soát tốc độ.
6. Đối soát số event đọc, số event thành công, duplicate và event lỗi.

Capture là cơ chế archive theo cấu hình; nó không tự tạo API để EventProcessorClient đọc trực tiếp từ archive như thể dữ liệu vẫn nằm trong partition. Muốn xử lý lại archive, cần một consumer/pipeline đọc file Avro rồi đưa dữ liệu vào đích thích hợp.

Archive cũng phát sinh chi phí storage, transaction, data transfer và xử lý batch. Cần retention/lifecycle riêng cho file Capture và quyền đọc archive được tách theo môi trường.

## 18. Replay an toàn với nghiệp vụ và idempotency

Replay kỹ thuật thành công không có nghĩa side effect nghiệp vụ được phép chạy lại. Ví dụ:
- Dựng lại projection có thể ghi vào bảng projection mới.
- Tính lại analytics có thể ghi vào dataset riêng.
- Gửi email, thanh toán hoặc gọi API đối tác có thể không được phép thực hiện lần nữa.
- Event đã được xử lý trước đó có thể bị inbox/dedup loại bỏ nếu dùng cùng consumer identity.

Trước replay, xác định **mục tiêu đích**:
- Rebuild read model: dùng bảng/schema mới hoặc consumer identity mới.
- Reconcile dữ liệu: chạy logic so sánh/đối soát, không tự phát lại mọi side effect.
- Retry event lỗi: chỉ replay event đã quarantine và giữ nguyên event ID.
- Re-run business action: cần idempotency key và phê duyệt theo nghiệp vụ.

Bảng dedup thường dùng khóa **(consumer_name, event_id)**. Nếu rebuild projection, consumer_name hoặc bảng dedup cần phân biệt replay target để không bỏ qua toàn bộ event đã xử lý bởi projection cũ. Ngược lại, không đổi consumer name chỉ để vượt qua dedup khi mục tiêu là gửi lại payment/email; cần một quy trình nghiệp vụ riêng.

## 19. Quan sát lag, buffer và replay

Theo dõi ít nhất:

| Chỉ số | Ý nghĩa | Cách dùng |
|---|---|---|
| Prefetch count | Số event được đệm theo partition | Kết hợp heap và payload size để chọn |
| Batch size / wait time | Số event và thời gian gom batch | Cân bằng throughput và latency |
| Callback duration | Thời gian xử lý event/batch | Phát hiện handler làm chậm partition |
| Consumer lag | Khoảng cách giữa vị trí consumer và cuối stream | Xác định consumer có theo kịp không |
| Oldest event age | Tuổi event chưa xử lý | So với SLO và retention |
| Heap / GC | Bộ nhớ và áp lực thu gom rác | Phát hiện prefetch hoặc queue quá lớn |
| Downstream latency/error | DB/API response time và failure | Điều chỉnh rate/concurrency |
| Checkpoint age/failure | Tiến độ lưu vào Blob | Phát hiện checkpoint store chậm/lỗi |
| Throttled requests | Request bị dịch vụ hạn chế | Phân biệt service capacity với downstream |
| Replay throughput | Tốc độ đọc lại | Tránh replay làm quá tải production |
| Duplicate suppressed | Event trùng bị loại bỏ | Đánh giá replay/rebalance và idempotency |

Nếu có thể, đo lag theo partition. Một partition nóng có thể lag mạnh dù tổng throughput toàn hub vẫn ổn. Khi replay, gắn **replayRunId**, consumer group và target vào log/metric để phân biệt traffic replay với traffic live.

## 20. Kiểm thử điều tiết và replay

Dùng Event Hub, consumer group, checkpoint container và database test riêng. Không reset checkpoint production hoặc cố tình gây throttling trên namespace thật để thử.

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| Prefetch nhỏ/lớn | Chạy cùng tải với các giá trị prefetch khác nhau | Đo được throughput, heap và latency |
| Batch size | Thử batch 10/50/100 event | Chọn điểm cân bằng throughput/latency |
| Batch wait | Thử traffic cao và thấp | Traffic thấp không bị chờ quá lâu |
| Handler chậm | Tăng thời gian DB/API trong test | Lag tăng có kiểm soát, heap không tăng vô hạn |
| Downstream rate limit | Giới hạn số request/giây của DB/API giả lập | Callback backpressure, không retry storm |
| Queue nội bộ đầy | Dùng bounded queue nhỏ | Không checkpoint event chưa được lưu bền vững |
| Checkpoint failure | Tạm thời từ chối quyền Blob test | Event có thể replay; dedup ngăn side effect lặp |
| Replay timestamp | Consumer group mới đọc từ một thời điểm | Đọc đúng phạm vi event còn retention |
| Replay offset/sequence | Chỉ định vị trí theo partition | Tiếp tục từ vị trí mong muốn |
| Existing checkpoint | Tạo checkpoint rồi thay initial position | Processor resume theo checkpoint, không tự reset |
| Capture archive | Đọc file Avro trong storage test | Đếm/đối soát được event replay |
| Poison event | Gửi payload không hợp lệ | Quarantine bền vững hoặc dừng theo policy |
| Duplicate side effect | Gửi lại cùng event ID | Inbox/idempotency ngăn side effect lặp |
| Replay load | Tăng dần tốc độ replay | Database và network không bị quá tải |
| Multi-instance | Scale consumer cùng group | Ownership/rebalance ổn định, lag được theo dõi |

Load test cần ghi lại event size, ingress rate, processing rate, batch size, prefetch, heap, CPU, DB latency, checkpoint frequency và cost. Nếu chỉ thay đổi một tham số nhưng không giữ tải đầu vào tương đương, kết quả khó so sánh.

## 21. Tình huống vận hành thường gặp

### Tình huống A: heap tăng khi traffic cao

Consumer đang sở hữu nhiều partition, prefetch 500 mỗi partition, event payload lớn và handler ghi DB chậm. Giảm prefetch theo từng bước, đo heap sau GC, kiểm tra số partition mỗi instance và loại bỏ queue nội bộ không giới hạn. Sau đó đánh giá batch size để cân bằng overhead.

### Tình huống B: consumer lag tăng dù CPU thấp

Có thể callback đang chờ DB/API, connection pool cạn, network tới Blob checkpoint store chậm hoặc một partition bị hot key. Xem callback duration, DB pool wait, checkpoint age và lag theo partition trước khi tăng số pod.

### Tình huống C: tăng batch size nhưng latency người dùng xấu đi

Batch chờ đủ số event hoặc maxWaitTime quá dài. Giảm wait time, cân nhắc batch size nhỏ hơn hoặc dùng processEvent cho traffic thấp. Đo p95/p99 end-to-end thay vì chỉ throughput.

### Tình huống D: replay làm database quá tải

Replay dùng cùng capacity và downstream với consumer live. Tạo replay consumer group riêng, giới hạn rate/concurrency, dùng read replica hoặc target riêng nếu phù hợp, chạy ngoài giờ cao điểm và theo dõi backlog live. Không tăng prefetch để replay nhanh hơn khi database đã quá tải.

### Tình huống E: replay không đọc từ earliest dù cấu hình đã đổi

Consumer group đang có checkpoint. Initial position chỉ áp dụng khi checkpoint chưa tồn tại. Dùng consumer group mới cho replay hoặc thực hiện reset checkpoint theo runbook khi tất cả processor đã dừng và đã đánh giá tác động.

### Tình huống F: dữ liệu cần replay đã hết retention

Event Hubs không còn giữ offset cũ. Kiểm tra Event Hubs Capture, archive hoặc nguồn lưu trữ khác. Nếu không có archive, phải xác định khoảng dữ liệu không thể phục hồi và xử lý theo quy trình nghiệp vụ; không thể khôi phục event đã bị xóa chỉ bằng cách thay checkpoint.

## 22. Checklist trước production

- **Prefetch:** được chọn theo event size, số partition mỗi instance, heap và throughput.
- **Batch:** max size/wait time đáp ứng latency và downstream batch limits.
- **Backpressure:** callback chậm có kiểm soát; không có queue RAM vô hạn.
- **Rate/concurrency:** giới hạn theo downstream capacity; global limit được thiết kế rõ khi có nhiều replica.
- **Checkpoint:** chỉ sau side effect/quarantine bền vững; tần suất cân bằng giữa Blob cost và replay window.
- **Idempotency:** event ID ổn định, inbox/unique constraint và side effect ngoài DB có guard.
- **Replay:** consumer group riêng, initial position rõ, tốc độ replay có giới hạn và target được xác định.
- **Retention/archive:** biết thời gian giữ event; Capture/ADLS archive đáp ứng yêu cầu replay dài hạn.
- **Observability:** lag theo partition, oldest event age, heap/latency, callback duration, checkpoint age, throttling và replay run ID.
- **Security:** Managed Identity/RBAC riêng cho Event Hubs và Blob; archive được mã hóa và phân quyền.
- **Testing:** đã thử handler chậm, checkpoint failure, duplicate, replay, retention expiry và downstream throttling.
- **Operations:** có runbook dừng replay, giảm tốc consumer, xử lý poison event và đối soát dữ liệu.

## 23. Tổng kết

Điều tiết Event Hubs cần phối hợp **prefetch, batch, callback duration, concurrency, rate limit, backpressure và checkpoint**. Prefetch kiểm soát lượng event đệm cục bộ; batch giảm overhead; callback chậm tạo backpressure tự nhiên; rate limiter/bulkhead bảo vệ downstream. Không tham số nào thay thế cho idempotency và checkpoint đúng thời điểm.

Replay nên dùng **consumer group riêng**, chọn vị trí theo earliest/latest/time/offset/sequence và giới hạn tốc độ xử lý lại. Nếu dữ liệu đã hết retention, dùng Event Hubs Capture hoặc archive; checkpoint không thể khôi phục event đã bị xóa. Khi tích hợp Spring Boot, hãy đo lag/heap/latency theo partition, giữ event ID gốc, tách replay target khỏi side effect production và kiểm thử đầy đủ trên tài nguyên riêng.

## Tài liệu tham khảo

- Azure SDK for Java — Troubleshoot Event Hubs performance: https://learn.microsoft.com/en-us/azure/developer/java/sdk/troubleshooting-messaging-event-hubs-performance
- Azure SDK for Java — Troubleshoot EventProcessorClient: https://learn.microsoft.com/en-us/azure/developer/java/sdk/troubleshooting-messaging-event-hubs-processor
- Azure SDK for Java — EventProcessorClientBuilder API: https://learn.microsoft.com/en-us/java/api/com.azure.messaging.eventhubs.eventprocessorclientbuilder?view=azure-java-stable
- Azure SDK for Java — EventHubConsumerClient API: https://learn.microsoft.com/en-us/java/api/com.azure.messaging.eventhubs.eventhubconsumerclient?view=azure-java-stable
- Spring Cloud Azure — Event Hubs binder reference: https://microsoft.github.io/spring-cloud-azure/current/reference/html/index.html
- Azure Event Hubs — Capture overview: https://learn.microsoft.com/en-us/azure/event-hubs/event-hubs-capture-overview
- Azure Event Hubs — FAQ and retention: https://learn.microsoft.com/en-us/azure/event-hubs/event-hubs-faq

