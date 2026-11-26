# Node mất kết nối middleware

Trong hệ thống Spring Batch xử lý dữ liệu lớn, **node mất kết nối middleware** là tình huống một ứng dụng manager hoặc worker còn có thể đang chạy, nhưng không thể gửi, nhận hay xác nhận thông điệp qua tầng trung gian như RabbitMQ, JMS broker hoặc một nền tảng messaging tương đương. Kết nối có thể mất vài giây rồi tự phục hồi, đứt hẳn do sự cố mạng, hoặc chỉ bị lỗi theo một chiều. Đây là bài toán **failover**: hệ thống phải phân biệt công việc chưa nhận, đang chạy, đã commit nhưng chưa được xác nhận, từ đó khôi phục an toàn mà không mất hoặc xử lý trùng dữ liệu.

Bài này thuộc chương **Failover** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module hướng tới mở rộng Spring Batch bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán, đồng thời đo nút thắt, bảo đảm thread safety, retry/restart và vận hành job theo tài nguyên thực tế. Chủ đề hiện tại tập trung vào **kết nối middleware** trong các kiến trúc phân tán; ở mô hình local chunking hoặc local partitioning không sử dụng broker, cách xử lý lỗi sẽ khác.

## 1. Mục tiêu học tập và bối cảnh

Sau bài học, bạn cần giải thích được:

- Điều gì thực sự xảy ra khi **manager**, **worker** hoặc **broker** không liên lạc được với nhau.
- Vì sao việc gửi hoặc nhận thông điệp thành công **không đồng nghĩa** nghiệp vụ đã commit; và commit thành công cũng không bảo đảm phản hồi đã tới manager.
- Cách khác nhau giữa **remote chunking** và **remote partitioning** khi một node mất kết nối.
- Vai trò của delivery acknowledgement (ACK), publisher confirm, redelivery, retry, timeout, dead-letter queue (DLQ), idempotency và JobRepository.
- Một quy trình kiểm tra, cô lập lỗi, khôi phục kết nối, đối soát trạng thái rồi mới restart job.
- Cách thiết kế kiểm thử sự cố và đo các chỉ số để chọn chính sách failover theo tải thực tế.

**Tình huống xuyên suốt:** job xử lý 2 triệu đơn hàng, manager chia công việc cho bốn worker qua broker. Worker W2 đã ghi một lô đơn hàng vào cơ sở dữ liệu, nhưng kết nối với broker bị đứt trước khi ACK hoặc gửi response. Broker hoặc manager có thể cho rằng công việc ấy chưa hoàn tất, dù dữ liệu đã tồn tại. Nếu chạy lại một cách thiếu kiểm soát, hệ thống có thể ghi trùng, gửi hai lần thông báo hoặc tính doanh thu hai lần.

## 2. Đặt middleware đúng vào kiến trúc

**Middleware** trong bài này là tầng truyền thông điệp giữa các node, không phải JobRepository. Broker vận chuyển request/response; JobRepository giữ metadata thực thi batch như JobExecution, StepExecution và ExecutionContext. Nhiều ứng dụng còn dùng một cơ sở dữ liệu nghiệp vụ riêng để lưu kết quả.

~~~mermaid
flowchart LR
    M["Manager / Job coordinator"] <--> B["Messaging middleware"]
    B <--> W1["Worker A"]
    B <--> W2["Worker B"]
    B <--> W3["Worker C"]
    M <--> JR[("JobRepository")]
    W1 -. "Tùy mô hình" .-> JR
    W2 -. "Tùy mô hình" .-> JR
    W3 -. "Tùy mô hình" .-> JR
    W1 --> D[("Business database")]
    W2 --> D
    W3 --> D
~~~

Kết nối nét đứt với JobRepository có ý nghĩa quan trọng: **remote partitioning** thường cho worker sử dụng JobRepository chung để quản lý StepExecution; **remote chunking** có đường đời request/response riêng và không nhất thiết yêu cầu worker cùng ghi metadata StepExecution như remote partitioning. Không thể dùng một quy tắc khôi phục cho mọi kiểu kiến trúc.

| Kiến trúc | Đơn vị gửi qua middleware | Khi worker mất kết nối | Căn cứ khôi phục chính |
| --- | --- | --- | --- |
| **Remote chunking** | Các chunk item từ manager đến worker; worker xử lý/ghi và phản hồi | Chunk đã gửi có thể còn chờ, đã ghi nhưng mất response hoặc được phát lại | Trạng thái manager, correlation/request ID, độ bền thông điệp và đối soát dữ liệu đích |
| **Remote partitioning** | Yêu cầu thực thi một **StepExecution** cho từng partition | Worker có thể đang đọc/ghi nhiều chunk trong partition, dù manager chưa nhận thông báo cuối | StepExecution và ExecutionContext trong JobRepository, cùng bằng chứng worker còn chạy hay đã dừng |
| **Local partitioning** | Không bắt buộc có middleware; các worker chạy trong một JVM | Không có lỗi mạng manager–broker theo thiết kế local; lỗi tiến trình/JVM có phạm vi khác | JobRepository và lifecycle của JVM/StepExecution |

Một node có thể gặp lỗi broker nhưng **vẫn kết nối được database**. Vì vậy, trạng thái “worker mất kết nối” chưa đủ để kết luận transaction nghiệp vụ đã rollback.

## 3. Phân loại tình huống mất kết nối

Mất kết nối middleware không phải một trạng thái duy nhất:

| Điểm lỗi | Biểu hiện thường gặp | Điều chưa thể suy ra |
| --- | --- | --- |
| Manager không publish được request | Timeout, socket reset, publisher confirm không đến | Request chắc chắn chưa tới broker hay đã bị mất |
| Worker không consume được | Consumer count giảm; backlog tăng; log reconnect | Worker chắc chắn không còn làm việc với dữ liệu nhận trước đó |
| Worker mất ACK hoặc response | Message được redeliver; manager vẫn chờ kết quả | Ghi DB đã thất bại |
| Broker không sẵn sàng | Nhiều node lỗi kết nối đồng thời, hàng đợi không truy cập được | Toàn bộ thông điệp bền vững đều bị mất |
| Network partition hoặc lỗi DNS/TLS | Một nhóm node lỗi, nhóm khác vẫn kết nối bình thường | Có thể an toàn khởi tạo một manager mới ngay |
| Consumer xử lý rất chậm | Ack timeout, heartbeat miss, queue lag tăng | Có sự cố mạng thật; có thể chỉ là CPU/GC/DB nghẽn |

Hãy phân biệt **lỗi kết nối** với **lỗi tiêu thụ chậm**. Ví dụ một worker bị stop-the-world GC lâu hoặc chờ lock DB có thể ngừng gửi heartbeat; broker đóng connection và phát lại request, trong khi thao tác DB cũ chưa thực sự kết thúc.

Ngoài ra, tính năng *automatic connection recovery* của client messaging chỉ giúp dựng lại kết nối/channel/consumer theo khả năng thư viện. Nó **không tự khôi phục toàn bộ giao dịch nghiệp vụ** hay quyết định chunk hoặc partition nào nên chạy lại.

## 4. Trình tự nguy hiểm: commit đã thành công nhưng mất xác nhận

~~~mermaid
sequenceDiagram
    autonumber
    participant M as Manager
    participant B as Broker
    participant W as Worker W2
    participant D as Database
    M->>B: Gửi work R-42
    B->>W: Giao work R-42
    W->>D: BEGIN; xử lý và ghi
    D-->>W: COMMIT thành công
    Note over W,B: Mất kết nối trước ACK/response
    W--xB: ACK/response không tới
    B->>W: Redelivery R-42 sau khi kết nối phục hồi
    W->>D: Ghi lại cùng operation ID
    D-->>W: Dedup/UPSERT, không nhân đôi tác động
    W->>B: ACK khi đã xử lý an toàn
    B-->>M: Trả trạng thái tương ứng
~~~

Sơ đồ mô tả một tình huống **khả dĩ**, không mặc định tất cả hệ thống đều redeliver hay dùng đúng thứ tự ACK như nhau. Quy tắc ACK phụ thuộc giao thức, cấu hình broker và cách tích hợp. Một số tầng framework quản lý acknowledgement thay ứng dụng; không nên tự ý ACK thủ công nếu container đang sở hữu transaction/ACK.

Điểm mấu chốt là có **cửa sổ bất định** giữa hai hoạt động:

1. **Commit cơ sở dữ liệu**: kết quả nghiệp vụ đã được lưu bền vững.
2. **Xác nhận qua middleware**: broker hoặc manager biết công việc đã hoàn thành.

Nếu hai hoạt động này không nằm trong cùng một distributed transaction, chúng có thể không thành công cùng lúc. Khi mất xác nhận, một request có thể được phát lại theo cơ chế *at-least-once*. Hệ thống phải chấp nhận khả năng xử lý lại và làm cho **tác động nghiệp vụ an toàn khi lặp**, thay vì giả định mỗi request chỉ tới đúng một lần.

### Ba cửa sổ lỗi khác nhau

- **Trước khi worker nhận request:** nếu thông điệp đã được broker lưu bền vững và chưa ACK, nó có cơ hội được giao cho consumer khác sau khi broker/client phục hồi. Nếu publisher chưa xác nhận, manager không biết chắc broker đã nhận; việc gửi lại phải giữ cùng định danh nghiệp vụ.
- **Sau khi worker nhận nhưng trước commit:** transaction dữ liệu có thể rollback, sau đó request được xử lý lại. Với side effect nằm ngoài transaction (API ngoài, gửi email), rollback DB không bảo đảm side effect đã được hoàn tác.
- **Sau commit nhưng trước ACK/response:** kết quả đã có, nhưng request có thể được gửi lại. Đây là lúc unique constraint, idempotency key và reconciliation trở nên thiết yếu.

## 5. Delivery guarantee không đồng nghĩa business guarantee

| Thuật ngữ | Đảm bảo ở tầng nào | Hạn chế đối với Spring Batch |
| --- | --- | --- |
| **At-most-once** | Thông điệp không được phát lại sau khi đã coi là nhận | Có thể bỏ sót công việc khi consumer chết trước khi xử lý |
| **At-least-once** | Hệ thống cố gắng phát lại thông điệp chưa xác nhận | Có thể xử lý cùng một công việc nhiều lần |
| **Exactly-once** | Một sản phẩm/giao thức có thể cung cấp đảm bảo cụ thể trong phạm vi được định nghĩa | Không mặc nhiên áp dụng xuyên broker, JobRepository, DB nghiệp vụ và API bên ngoài |
| **Idempotent effect** | Thực hiện lại cùng operation ID không nhân đôi kết quả nghiệp vụ | Cần thiết kế khóa, transaction, version và chính sách side effect phù hợp |

Ví dụ, Kafka có cơ chế transaction/processing guarantee trong những phạm vi nhất định; JMS và RabbitMQ có ngữ nghĩa ACK, transaction và redelivery riêng. Không nên suy từ tính năng “exactly once” của một tầng sang bảo đảm **end-to-end** cho cả việc ghi PostgreSQL và gọi API thanh toán.

Để tránh mất request khi broker hoặc đường truyền lỗi, hệ thống thường cần kết hợp **durable queue/topic tương ứng**, thông điệp có độ bền phù hợp, xác nhận publish, ACK theo đúng thời điểm và chính sách redelivery. Chỉ bật một trong các tùy chọn ấy chưa đủ. Cách cấu hình cụ thể phụ thuộc middleware và adapter Spring Integration đang sử dụng.

## 6. Khác biệt khi failover giữa remote chunking và remote partitioning

### 6.1. Remote chunking: manager là bên điều phối các chunk

Trong remote chunking, manager thường sở hữu ItemReader và chia đầu vào thành chunk. Worker nhận yêu cầu, chạy phần xử lý/ghi của chunk rồi gửi response. Hãy xem xét các trường hợp:

1. **Không nhận response:** manager chưa thể xác nhận chunk đã xong, nhưng worker có thể đã commit dữ liệu. Đừng mặc định chuyển toàn bộ job sang FAILED rồi chạy một job mới với tham số khác.
2. **Manager mất kết nối khi publish:** việc publish đã thành công nhưng confirm bị mất là trường hợp có thể xảy ra. Một lần publish lại cần giữ **request/correlation ID ổn định** và cơ chế chống tác động trùng.
3. **Reply bị trễ hoặc mất:** cần theo dõi request đang chờ và đối chiếu dữ liệu/response theo ID; timeout chỉ báo **không có xác nhận đúng hạn**, không chứng minh nghiệp vụ thất bại.
4. **Manager restart:** kiểm tra cách tích hợp lưu trạng thái đọc, request đang bay và reply. Đừng tự suy rằng chỉ cần reader restart là mọi chunk đã gửi sẽ được xử lý đúng một lần.

Trong hệ thống thực, cách gửi/nhận reply và cơ chế durable request tùy thuộc Spring Batch Integration cùng cấu hình Spring Integration của ứng dụng. Phải kiểm tra đường đi **request lẫn response**, không chỉ queue của worker.

### 6.2. Remote partitioning: worker chạy StepExecution

Trong remote partitioning, manager gửi yêu cầu gắn với một StepExecution của partition. Worker truy xuất metadata và thực thi step, có thể gồm hàng nghìn chunk. Thực thi thường sử dụng một JobRepository được truy cập nhất quán bởi manager và các worker.

Nếu response mất nhưng JobRepository cho thấy partition đã **COMPLETED**, cần xem đây là bằng chứng mạnh để đối soát. Ngược lại, nếu metadata vẫn là **STARTED** nhưng node không còn chạy, trạng thái có thể là một execution bị bỏ dở; không được tự ý coi là COMPLETED hoặc lập tức mở execution khác khi chưa loại trừ worker cũ còn đang xử lý.

Khi phục hồi:

- Tra theo **JobInstance/JobExecution ID, partition name và StepExecution ID** để tránh nhầm giữa lần chạy cũ và lần restart.
- Xác minh worker thực sự ngừng hoặc còn sở hữu công việc; một worker mất middleware vẫn có thể đang ghi DB.
- Đối soát trạng thái chunk và dữ liệu kết quả trước khi cho restart các partition không hoàn tất.
- Giữ ổn định tên partition, phạm vi dữ liệu và JobParameters khi restart; thay đổi thuật toán phân vùng có thể làm dữ liệu mới không khớp ExecutionContext cũ.

**Không chỉnh trực tiếp các bảng metadata Spring Batch** để “ép” COMPLETED nếu chưa hiểu vòng đời job. Đây là hành động có thể che giấu dữ liệu chưa được ghi hoặc cho phép hai worker cùng xử lý một vùng.

## 7. Điều kiện để phục hồi sau đứt kết nối

Một thiết kế failover đủ tin cậy cần giải quyết đồng thời các tầng sau.

| Tầng | Cần thiết kế | Cần kiểm chứng |
| --- | --- | --- |
| **Kết nối** | Reconnect có exponential backoff và jitter; timeout phù hợp; TLS/DNS được quản lý | Node tự kết nối lại mà không tạo vòng lặp reconnect quá dày |
| **Broker** | Queue/stream bền vững, retention phù hợp, publisher confirm, consumer ACK/redelivery | Request chưa ACK sống sót qua lỗi mong đợi theo hợp đồng của broker |
| **Flow control** | Giới hạn số request in-flight, prefetch/concurrency, kích thước queue | Không bơm hàng triệu work item mới trong lúc downstream đang nghẽn |
| **Dữ liệu** | Transaction, unique key, idempotency, version hoặc outbox | Replay không tăng số tác động nghiệp vụ |
| **Batch metadata** | JobRepository bền vững; trạng thái StepExecution và ExecutionContext có thể khôi phục | Restart tiếp tục đúng vùng/đúng tham số |
| **Điều phối** | Tránh nhiều manager cùng nhận quyền điều khiển một job; quy trình fencing/leader nếu cần | Không có hai chủ sở hữu đồng thời của cùng một execution |
| **Quan sát** | Trace/correlation ID và metric end-to-end | Phân biệt mất message, chờ ACK, worker đang chạy và transaction đã commit |

### Retry kết nối khác retry nghiệp vụ

**Retry kết nối** do messaging client, listener container hoặc tầng integration phụ trách. Nó xử lý việc quay lại broker; không nên gắn toàn bộ vòng retry của kết nối trực tiếp vào ItemProcessor.

**Retry nghiệp vụ** của Spring Batch xử lý lỗi trong read/process/write, ví dụ một SQL transient exception:

~~~java
// Ví dụ trong một chunk-oriented worker Step của Spring Batch 5.x.
new StepBuilder("partitionWorkerStep", jobRepository)
        .<InputItem, OutputItem>chunk(200, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

Đoạn minh họa trên là **phần xử lý nghiệp vụ của worker Step**, không phải cấu hình reconnect cho RabbitMQ/JMS/Kafka. Tùy loại remote chunking hay partitioning, worker được lắp vào topology bằng thành phần Spring Batch Integration tương ứng. Không nên đưa một bước retry toàn bộ chunk vào callback reconnect mà không hiểu trạng thái commit và ACK cũ.

Một chính sách kết nối có thể bắt đầu từ exponential backoff có giới hạn và jitter, ví dụ khoảng nghỉ tăng từ 1 đến 2, 4, 8 giây đến trần 30 giây. Đây là **tham số minh họa**, phải đo theo SLA, tốc độ khôi phục broker và giới hạn tải. Retry không giới hạn tốc độ hoặc không có jitter dễ làm broker vừa phục hồi bị quá tải vì mọi worker kết nối lại cùng lúc.

### Readiness và liveness

Hãy tách hai câu hỏi:

- **Liveness:** process có còn đáp ứng và có thể phục hồi không?
- **Readiness:** process hiện có nên nhận **công việc mới** không?

Nếu broker tạm đứt, worker có thể vẫn live nhưng **unready** để nhận yêu cầu mới. Không cần thiết kế liveness để tự động kill container ở mọi lỗi ngắn; vòng restart liên tục có thể làm mất thông tin chẩn đoán hoặc kéo dài hồi phục. Tuy nhiên, nếu hệ thống không tự reconnect được vì trạng thái lỗi không hồi phục, cần có quy trình restart node có kiểm soát.

## 8. Idempotency: lớp bảo vệ quan trọng nhất của xử lý lại

Giả sử một đơn hàng có ID `order-8742` thuộc cùng một job input snapshot. Worker có thể nhận lại chunk chứa đơn này sau khi kết nối phục hồi. Mục tiêu là: **tác động ghi kết quả của đơn này chỉ xuất hiện một lần về mặt nghiệp vụ**.

### 8.1. Chọn khóa idempotency

Khóa nên phản ánh **đơn vị công việc logic** thay vì một lần giao thông điệp:

- Với ghi kết quả theo item: `(business_job_key, item_id, input_version)`.
- Với xử lý một hành động không lặp: `operation_id` được tạo trước lần publish đầu và giữ nguyên qua mọi lần redelivery.
- Với remote partitioning: partition ID có ích để nhận diện vùng công việc, nhưng **một partition thường chứa nhiều transaction/chunk**, nên không thể lấy một cờ “partition đã bắt đầu” để bỏ qua toàn bộ khi restart.

Không dùng delivery tag, consumer connection ID hoặc retry attempt ID làm khóa nghiệp vụ duy nhất: các giá trị này có thể đổi sau redelivery. Nếu hai phiên bản đầu vào cần được xử lý như hai công việc hợp lệ, khóa phải phân biệt được phiên bản.

### 8.2. Ví dụ writer idempotent trong Spring Batch

Ví dụ dùng PostgreSQL và Spring Batch 5.x; khóa duy nhất theo job logic và order ID. Dữ liệu đầu vào cần ổn định trong suốt một lần chạy/restart.

~~~sql
CREATE TABLE processed_order (
    job_key      VARCHAR(100) NOT NULL,
    order_id     BIGINT NOT NULL,
    net_total    NUMERIC(18, 2) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (job_key, order_id)
);
~~~

~~~java
record ProcessedOrder(String jobKey, long orderId, BigDecimal netTotal) {}

@Bean
JdbcBatchItemWriter<ProcessedOrder> idempotentOrderWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<ProcessedOrder>()
            .dataSource(dataSource)
            .sql("""
                 INSERT INTO processed_order (job_key, order_id, net_total)
                 VALUES (:jobKey, :orderId, :netTotal)
                 ON CONFLICT (job_key, order_id)
                 DO UPDATE SET net_total = EXCLUDED.net_total
                 """)
            .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                            .addValue("jobKey", item.jobKey())
                            .addValue("orderId", item.orderId())
                            .addValue("netTotal", item.netTotal()))
            .build();
}
~~~

Ghi lại cùng cặp `(job_key, order_id)` chỉ cập nhật một dòng. Tuy nhiên, **UPSERT không tự xử lý mọi nghiệp vụ**: nếu hai lần xử lý cùng khóa tính ra giá trị khác nhau, bản ghi có thể bị ghi đè. Phải cố định nguồn dữ liệu hoặc dùng version/checksum để phát hiện xung đột. Nếu có gửi tiền, trừ tồn kho hoặc gọi API ngoài, cần cơ chế idempotency cho **chính side effect đó**.

### 8.3. Inbox/dedup marker trong cùng transaction

Đối với một message đại diện cho một hành động nghiệp vụ, có thể dùng bảng đánh dấu đã xử lý:

~~~sql
CREATE TABLE processed_operation (
    consumer_name VARCHAR(100) NOT NULL,
    operation_id  VARCHAR(160) NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, operation_id)
);
~~~

Quy trình minh họa:

~~~text
BEGIN database transaction
  INSERT INTO processed_operation(consumer_name, operation_id)
  VALUES ('billing-worker', 'job-2026-11-26:order-8742')
  ON CONFLICT DO NOTHING

  IF insert không thêm dòng:
      => operation đã được xử lý trong một transaction đã commit
      => không thực hiện lại business write
  ELSE:
      => thực hiện business write và, nếu cần, ghi outbox event
COMMIT

Sau commit thành công: cho tầng messaging xác nhận request theo cơ chế của nó.
Nếu transaction rollback: marker cũng rollback, redelivery sau đó được phép thử lại.
~~~

Đây là **pseudocode giao dịch**, không phải SQL thuần có thể dán chạy nguyên khối. Việc kiểm tra số dòng INSERT cần thực hiện trong cùng transaction và cùng database với thay đổi nghiệp vụ. Unique constraint giúp các lần xử lý đồng thời cùng operation ID được phân xử nhất quán.

Nếu cần phát thông điệp mới sau khi ghi dữ liệu, **transactional outbox** thường phù hợp: cùng một DB transaction lưu dữ liệu nghiệp vụ và bản ghi outbox; tiến trình gửi riêng chuyển outbox qua broker rồi đánh dấu đã gửi, với consumer phía nhận có idempotency. Mô hình này tránh kiểu “DB commit thành công nhưng gửi event thất bại” làm mất sự kiện đầu ra.

## 9. State machine vận hành khi node mất kết nối

Có thể dùng mô hình trạng thái sau **để thiết kế vận hành và quan sát**; đây không phải enum hay state machine mặc định do Spring Batch cung cấp:

~~~mermaid
stateDiagram-v2
    [*] --> READY
    READY --> DEGRADED: Heartbeat trễ / publish latency tăng
    DEGRADED --> DISCONNECTED: Connection mất / broker unreachable
    DISCONNECTED --> RECONNECTING: Backoff hết hạn
    RECONNECTING --> DISCONNECTED: Kết nối lại thất bại
    RECONNECTING --> RECONCILING: Kết nối và xác thực thành công
    RECONCILING --> READY: Đối soát in-flight / state xong
    RECONCILING --> NEEDS_OPERATOR: Metadata hoặc dữ liệu mâu thuẫn
    NEEDS_OPERATOR --> RECONCILING: Đã xử lý nguyên nhân
~~~

Khi chuyển từ **RECONNECTING** sang **RECONCILING**, đừng mở hết concurrency ngay lập tức. Cần làm rõ request nào chưa ACK, response nào đã đến muộn, worker nào còn sở hữu StepExecution và liệu có công việc nào cần đưa vào queue lại. Mở concurrency tăng dần có thể giúp broker và database tránh bị nghẽn sau khi downtime.

Đặc biệt với manager failover, nếu một manager cũ bị mất kết nối nhưng vẫn hoạt động, manager mới có nguy cơ cùng phân phối công việc. Cần cơ chế xác định **một chủ sở hữu có hiệu lực** của việc điều phối, ví dụ leader/lease với fencing token phù hợp, và kiểm tra điều kiện chạy đồng thời của Spring Batch JobRepository. Không chỉ dựa vào một biến boolean trong bộ nhớ tiến trình.

## 10. Runbook xử lý sự cố trong môi trường vận hành

### Bước 1 — Khoanh vùng, giữ bằng chứng

Ghi lại **thời điểm bắt đầu**, danh sách node lỗi, môi trường/broker endpoint, loại giao thức, job name và JobExecution ID. Trích xuất log có correlation ID của request, partition name, StepExecution ID, message ID, transaction ID (nếu có). Dùng múi giờ thống nhất khi so sánh sự kiện.

Ưu tiên hành động có thể đảo ngược: tạm **ngừng publish công việc mới** hoặc giảm concurrency nếu backlog đang tăng nhanh, giữ dữ liệu trong queue theo khả năng broker, tránh vô tình kích hoạt một đợt chạy trùng. Không xóa queue/DLQ để “giải phóng” sự cố.

### Bước 2 — Xác định thành phần thực sự lỗi

Kiểm tra từ **cả manager và worker**: DNS, route, firewall, TLS certificate, xác thực, quota connection/channel, broker health, queue depth, consumer count, thời gian ACK, CPU/GC và DB connection pool. Một node timeout khi kết nối broker nhưng các node khác bình thường thường là dấu hiệu sự cố cục bộ hoặc network partition; nhiều node cùng lỗi có thể liên quan broker hoặc hạ tầng chung.

Đối với Kafka, xem consumer group lag và số lần rebalance; với RabbitMQ/JMS, xem backlog, unacked/unconsumed và trạng thái consumer/session theo công cụ tương ứng. Các metric cụ thể khác nhau giữa từng middleware, không nên coi chúng là cùng một khái niệm.

### Bước 3 — Kiểm tra công việc đang bay (in-flight)

Lập bảng đối soát nhỏ nhưng chính xác:

| Định danh | Tình trạng messaging | Metadata batch | Dữ liệu nghiệp vụ | Quyết định |
| --- | --- | --- | --- | --- |
| R-41 | ACK/response đã nhận | Hoàn tất | Đã ghi | Không chạy lại |
| R-42 | ACK/response mất | Có thể chưa xác nhận | Đã ghi | Chỉ cho replay nếu idempotent; khớp request ID |
| R-43 | Chưa giao | Chưa bắt đầu | Chưa ghi | Chờ broker redelivery/điều phối lại |
| partition-7 | Worker không gửi kết quả | StepExecution vẫn STARTED | Chưa chắc | Xác minh worker còn chạy trước khi restart |

Các hàng là **tình huống ví dụ**. Khi làm thật, quyết định phải dựa trên log, JobRepository, dấu hiệu worker sống và truy vấn DB, không dựa vào timeout một mình.

### Bước 4 — Khôi phục kết nối và xử lý hàng đợi

Sau khi broker hoặc đường mạng hoạt động trở lại, kiểm tra kết nối đã authenticated, producer publish/confirm và consumer ACK/response vận hành được. Cho phép worker reconnect theo backoff; quan sát backlog giảm, retry không tăng liên tục và pool DB còn dư tải.

Với DLQ, phân loại nguyên nhân: lỗi tạm thời có thể replay sau khi sửa, lỗi schema/poison message cần cô lập để điều tra. Khi đưa DLQ vào lại, **giữ idempotency key**, log số lần phát lại và giới hạn tốc độ. Không republish ồ ạt mọi thông điệp mà không biết chúng từng commit hay chưa.

### Bước 5 — Đối soát JobRepository rồi restart

**Remote partitioning:** xác nhận worker cũ không còn xử lý cùng StepExecution; tra trạng thái StepExecution và ExecutionContext, đặc biệt các partition STARTED/FAILED/UNKNOWN. Tùy trường hợp, dùng cơ chế stop/restart được Spring Batch và quy trình vận hành cho phép, với **cùng bộ JobParameters định danh JobInstance** khi muốn restart. Không tạo JobInstance mới chỉ để vượt qua metadata của execution còn dang dở.

**Remote chunking:** đối chiếu các chunk/request chưa có response với dấu vết broker và kết quả DB; xác minh chiến lược restart manager/reader và reply correlation theo đúng implementation. Nếu không chứng minh được an toàn, cần đưa work item vào luồng reconciliation thay vì tự gửi lại toàn bộ dữ liệu.

### Bước 6 — Kết thúc sự cố bằng bằng chứng

Xác nhận tất cả partition/chunk cần hoàn tất đã được ghi nhận, dữ liệu đầu ra khớp số item kỳ vọng, không có side effect trùng, DLQ/queue lag nằm trong giới hạn và các node đã về trạng thái READY. Sau đó lưu timeline sự cố và cập nhật threshold/alert/runbook.

## 11. Giám sát và cảnh báo đúng trọng tâm

Một dashboard hiệu quả cần ghép **tầng messaging**, **tầng Spring Batch** và **tầng nghiệp vụ**:

| Nhóm | Metric hoặc tín hiệu | Câu hỏi trả lời |
| --- | --- | --- |
| Connectivity | Reconnect count, connection errors, time từ disconnect tới ready | Node phục hồi trong bao lâu? |
| Producer | Publish latency, confirm timeout, số request in-flight | Manager đang gửi được hay bị nghẽn? |
| Consumer | Consumer count, backlog/lag, redelivery rate, age of oldest message | Worker có theo kịp tốc độ gửi không? |
| Batch | Job/StepExecution status, read/write/skip/rollback count theo partition | Công việc nào chưa hoàn tất hoặc có dấu hiệu chạy lại? |
| Database | Commit latency, lock wait, connection pool usage, số conflict/dedup | Có phải DB làm node trễ ACK? |
| Business | Số key nguồn/đích, số lần operation được dedup, số side effect ngoài | Tính đúng đắn có còn được giữ? |

**Cảnh báo nên gắn với tác động**, ví dụ “consumer count = 0 đồng thời oldest-message age tiếp tục tăng” hoặc “partition STARTED quá lâu mà worker owner không còn heartbeat”. Một dòng log “connection reset” rồi reconnect ngay chưa đủ để gọi là sự cố nghiêm trọng.

Những ngưỡng như 30 giây mất kết nối hoặc 5 phút backlog chỉ là ví dụ. Hãy chọn ngưỡng dựa trên thời gian xử lý chunk/partition phân vị cao, SLA và khả năng chịu tải của broker, không lấy một timeout chung cho mọi job.

## 12. Kiểm thử failover có kiểm soát

Chỉ đánh giá hệ thống phục hồi được khi đã **chủ động tạo lỗi** trong môi trường thử nghiệm phù hợp. Bộ thử nghiệm tối thiểu:

| Kịch bản đưa lỗi vào | Kỳ vọng | Cách xác minh |
| --- | --- | --- |
| Ngắt mạng worker trước khi nhận request | Request còn tồn tại theo hợp đồng durability/redelivery | Message chưa mất; worker khác hoặc worker phục hồi nhận được |
| Ngắt sau khi worker nhận, trước DB commit | Transaction rollback hoặc được giải quyết nhất quán | Không có dữ liệu nửa chừng; replay thành công |
| Ngắt sau DB commit, trước ACK | Request có thể được giao lại | Không có hai tác động nghiệp vụ; dedup/unique key hoạt động |
| Chặn response về manager | Manager không xác nhận nhầm chunk thành công/thất bại | Reconciliation nhận ra DB đã ghi, không nhân đôi |
| Tắt broker trong khoảng ngắn | Node reconnect có backoff; không làm quá tải DB khi broker lên | Backlog giảm, hệ thống về READY, không lỗi dữ liệu |
| Worker chết giữa partition | Metadata phản ánh execution chưa hoàn tất | Restart đúng partition, đúng cutoff/source snapshot |
| Manager cũ còn sống khi manager mới khởi động | Chỉ một manager có quyền điều phối cùng execution | Không có hai execution/dispatch trùng hợp lệ |

Một phép đối soát trên PostgreSQL, với giả định mỗi đơn đầu vào phải có đúng một kết quả cho `job_key` tương ứng:

~~~sql
-- Bản ghi đầu vào chưa có kết quả
SELECT i.id
FROM inbound_order AS i
LEFT JOIN processed_order AS o
  ON o.order_id = i.id
 AND o.job_key = :job_key
WHERE i.batch_key = :source_batch_key
  AND o.order_id IS NULL;

-- Kiểm tra tổng số kết quả cho một job logic
SELECT COUNT(*)
FROM processed_order
WHERE job_key = :job_key;
~~~

Hai câu truy vấn chỉ minh họa điều kiện đối soát; cần điều chỉnh tên bảng/cột, quy tắc filter/skip và kiểm tra giá trị nghiệp vụ thực tế. Primary key trên `(job_key, order_id)` chặn bản ghi trùng khóa, nhưng không chứng minh side effect ngoài DB không bị lặp. Nếu có item được filter hợp lệ, **số kết quả có thể nhỏ hơn số đầu vào** mà vẫn đúng.

### Tiêu chí vượt qua bài kiểm thử

1. Không có item cần xử lý bị thất lạc khi broker phục hồi, xét theo phạm vi durability đã cam kết.
2. Replay/redelivery không nhân đôi business effect; các lệnh ngoại vi có khóa idempotency hoặc cơ chế bù rõ ràng.
3. Worker và manager có thể phục hồi trạng thái điều phối từ metadata/dấu vết bền vững, không phụ thuộc vào một biến RAM.
4. Chỉ restart phần việc cần thiết, không làm sai vùng partition hoặc JobParameters.
5. Queue lag, số retry và thời gian phục hồi nằm trong ngưỡng SLA thực đo, không khiến database hay broker sụp tải lần hai.

## 13. Chọn chiến lược theo tài nguyên và yêu cầu

Với workload chưa vượt giới hạn của một máy, **local partitioning** giảm số loại sự cố vì không có đường truyền broker giữa manager và worker. Tuy vậy, local có giới hạn CPU/RAM/DB connections trong một JVM và không giải quyết tính sẵn sàng khi máy chết.

**Remote partitioning** phù hợp khi cần chia tập đầu vào thành các vùng độc lập, lưu trạng thái StepExecution và có thể restart từng partition. Nó đòi hỏi quản lý tính nhất quán của JobRepository, lifecycle worker và tránh việc hai node cùng xử lý một partition.

**Remote chunking** phù hợp khi manager kiểm soát việc đọc đầu vào còn worker chịu trách nhiệm xử lý/ghi các chunk trên nhiều máy. Trong kiến trúc này, cần đầu tư đặc biệt cho request/reply, ACK, in-flight request và writer idempotent.

Nếu middleware là điểm nghẽn lớn nhất, tăng số worker sẽ không làm job nhanh hơn; có thể chỉ làm queue/connection tăng và phục hồi chậm hơn. Hãy đo throughput, broker capacity, DB pool và thời gian xử lý thực tế trước khi quyết định mở rộng thêm node hoặc đổi kiến trúc.

## 14. Checklist triển khai

- [ ] Có định danh ổn định cho mỗi request/partition và correlation giữa request, response, JobExecution.
- [ ] Đã xác định hợp đồng durability, ACK và redelivery cho middleware đang dùng.
- [ ] Mọi thao tác có khả năng chạy lại đều idempotent hoặc có cơ chế bù rõ ràng.
- [ ] JobRepository bền vững; restart dùng đúng JobParameters, tên partition và source snapshot.
- [ ] Worker có reconnect backoff và giới hạn concurrency/in-flight.
- [ ] Có quy trình phân biệt worker mất broker với worker đã chết hoặc đang kẹt DB/GC.
- [ ] Có dashboard cho queue lag, retry, in-flight, trạng thái step và dấu hiệu dữ liệu trùng/thiếu.
- [ ] Đã thử lỗi “commit xong nhưng mất ACK/response” và lỗi manager bị thay thế trong lúc còn sống.
- [ ] Có runbook đối soát trước khi replay DLQ hoặc restart job.

**Ghi nhớ:** Khi node mất kết nối middleware, câu hỏi quan trọng không phải chỉ là *“đã kết nối lại chưa?”* mà là **“mỗi đơn vị công việc đã thực sự đến đâu, bằng chứng nào xác nhận điều đó, và replay có an toàn hay không?”**. Failover đúng của Spring Batch là sự kết hợp giữa truyền thông tin cậy, JobRepository nhất quán, idempotency ở tầng dữ liệu, kiểm soát quyền điều phối và quan sát đủ sâu để đưa ra quyết định khôi phục.
