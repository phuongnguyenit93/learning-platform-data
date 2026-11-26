# Single consumer cho mỗi message trong remote chunking

Trong **Spring Batch remote chunking**, manager đọc dữ liệu và chia thành các chunk; nhiều worker ở những tiến trình hoặc máy khác nhau nhận chunk qua middleware để xử lý và ghi kết quả. Để có thể mở rộng số worker mà không nhân bản công việc, một yêu cầu xử lý chunk phải được phân phối cho **một consumer thuộc nhóm worker**, thay vì phát cùng yêu cầu cho mọi worker. Đây là yêu cầu nền tảng của middleware dùng cho remote chunking.

Bài học thuộc chương **Middleware remote chunking** của module **SPRING_BATCH_SCALING_OPERATIONS**. Mục tiêu là hiểu chính xác cơ chế *single consumer cho mỗi message*, cách cấu hình mô hình cạnh tranh nhận việc, phân biệt quyền sở hữu message với bảo đảm xử lý đúng một lần, và vận hành an toàn khi tăng số worker cho workload dữ liệu lớn.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao mỗi *chunk request* chỉ nên được giao cho một worker trong một lần phân phối.
2. Phân biệt **queue có nhiều competing consumers** với **publish/subscribe phát mỗi message cho nhiều subscriber**.
3. Chọn cách dùng JMS queue, RabbitMQ queue hoặc Kafka consumer group theo đặc tính của middleware.
4. Thiết kế xử lý *acknowledgement*, giao lại message, idempotency và phản hồi từ worker về manager.
5. Xác minh hệ thống thực sự phân phối công việc, phát hiện lặp, theo dõi backlog và tìm nút thắt khi scale.

## 2. Single consumer có nghĩa chính xác là gì?

Giả sử manager tạo ba request, mỗi request chứa một chunk gồm 100 bản ghi:

| Request | Bản ghi | Worker được giao ở lần phân phối đầu |
| --- | --- | --- |
| `C-101` | 1–100 | Worker A |
| `C-102` | 101–200 | Worker C |
| `C-103` | 201–300 | Worker B |

Có ba worker cùng lắng nghe một queue, nhưng **mỗi message cụ thể được broker giao cho một consumer**, và các message khác nhau có thể được xử lý đồng thời trên các worker khác nhau. Không bắt buộc cố định một worker cho một loại chunk, cũng không bắt buộc chỉ có một worker trong toàn hệ thống.

Hai ý thường bị nhầm lẫn:

- **Single consumer *per message delivery***: khi phân phối một request, broker chọn một consumer có thể nhận việc. Nếu nhiều consumer cùng đăng ký queue, chúng cạnh tranh để nhận các message khác nhau.
- **Exactly-once business processing**: hiệu ứng nghiệp vụ của một request chỉ xảy ra một lần qua toàn bộ vòng đời job, kể cả crash và restart. Chỉ dùng competing consumers **không** tự tạo ra bảo đảm này.

Nếu Worker A đã cập nhật cơ sở dữ liệu nhưng mất kết nối trước khi xác nhận message, broker có thể giao lại chính `C-101` cho Worker B. Đó là **hai lần xử lý theo thời gian**, mặc dù mỗi lần phân phối chỉ chọn một consumer. Ứng dụng phải chịu được tình huống này.

> Quy tắc thực hành: **mỗi request có một consumer trong mỗi lần giao; tác dụng ghi dữ liệu phải an toàn khi request được giao lại**.

## 3. Vị trí của yêu cầu trong kiến trúc Spring Batch

Remote chunking tách một bước chunk-oriented thành hai phía:

- **Manager** sở hữu `ItemReader`, tạo `ChunkRequest` từ các item rồi gửi request qua một outgoing channel. Manager tiếp nhận các `ChunkResponse` để tổng hợp kết quả và trạng thái step.
- **Worker** nhận request, chạy `ItemProcessor` (nếu có) và `ItemWriter`, rồi gửi phản hồi. Nhiều worker dùng chung nguồn request để chia tải.
- **Middleware** vận chuyển request và reply, chịu trách nhiệm phân phối, lưu trữ message, xác nhận nhận việc, tái giao khi có lỗi và hỗ trợ phục hồi.

~~~mermaid
flowchart LR
    S[(Nguồn dữ liệu)] --> M["Manager<br/>ItemReader → chunk"]
    M -->|ChunkRequest| Q[("Request queue<br/>competing consumers")]
    Q -->|chọn một consumer| A["Worker A"]
    Q -->|hoặc| B["Worker B"]
    Q -->|hoặc| C["Worker C"]
    A --> D[(Đích dữ liệu)]
    B --> D
    C --> D
    A -->|ChunkResponse| R[("Reply queue")]
    B -->|ChunkResponse| R
    C -->|ChunkResponse| R
    R --> M
~~~

Ba đường từ request queue sang ba worker thể hiện **ba đích có thể được chọn**; chúng không có nghĩa một message được sao chép thành ba bản. Nếu một request được giao cho A, B và C không cùng nhận request đó trong lần giao ấy.

Spring Batch Integration có các thành phần như `ChunkMessageChannelItemWriter`, `ChunkRequest`, `ChunkResponse` và builder cho manager/worker để thực hiện trao đổi. Trong remote chunking, việc đọc và chia chunk vẫn tập trung ở manager; tăng worker chỉ giúp khi khâu xử lý/ghi tốn thời gian hơn khâu đọc và gửi. Nếu manager hoặc cơ sở dữ liệu đích đã bão hòa, thêm consumer có thể không làm tăng throughput.

### 3.1. Không được nhầm request với reply

Thông thường cần hai luồng logic:

| Luồng | Nội dung | Ý nghĩa của single consumer |
| --- | --- | --- |
| Request | Manager → các worker | Một chunk request được giao cho một worker trong một lần phân phối |
| Reply | Worker → manager | Reply phải về đúng manager/step đang chờ; nếu có nhiều manager, chúng phải được định tuyến hoặc tương quan đúng |

Không thể suy ra rằng vì request queue hoạt động tốt nên reply queue tự động đúng. Hệ thống còn phải bảo toàn thông tin tương quan request–reply và xử lý trường hợp reply bị trễ, trùng hoặc thất lạc.

## 4. Competing consumers và publish/subscribe khác nhau ra sao?

### 4.1. Cấu hình đúng: nhiều worker chung một logical queue

Ví dụ broker có queue `batch.chunk.requests` và ba worker cùng nhận từ queue đó:

~~~text
Manager -- C-101, C-102, C-103 --> batch.chunk.requests
                                          |
                           +--------------+--------------+
                           |              |              |
                        Worker A       Worker B       Worker C
                           |              |              |
                         C-101          C-103          C-102
~~~

Việc worker nào nhận message nào phụ thuộc lịch phân phối, số consumer khả dụng, lượng message chưa ack, prefetch và chính sách broker. Phân phối thường không bảo đảm round-robin tuyệt đối; mục tiêu là **chia việc, không nhân bản việc**.

### 4.2. Cấu hình sai cho request: mỗi worker một subscription độc lập

Giả sử manager publish `C-101` lên topic, và mỗi worker có subscription/queue riêng:

~~~text
                          +--> subscription-A --> Worker A --> xử lý C-101
Manager -- C-101 --> Topic
                          +--> subscription-B --> Worker B --> xử lý C-101
                          +--> subscription-C --> Worker C --> xử lý C-101
~~~

Kết quả: ba worker có thể cùng ghi một chunk. Nếu writer thực hiện tăng số dư, trừ tồn kho hoặc gọi API có tác dụng phụ, sai lệch nghiệp vụ có thể xảy ra ngay cả khi từng worker xử lý thành công.

Đối với **request remote chunking**, hãy dùng mô hình *work queue* hoặc cơ chế *consumer group* tương đương. Pub/sub có thể phù hợp với phát sự kiện cho nhiều hệ thống độc lập, nhưng không phù hợp nếu mục tiêu là chia một khối lượng công việc duy nhất giữa các worker.

### 4.3. Đối chiếu middleware thường gặp

| Middleware | Cách tạo một consumer cho mỗi lần giao | Bẫy thường gặp |
| --- | --- | --- |
| **JMS** | Nhiều `MessageListener` cùng consume **cùng một Queue** | Dùng Topic hoặc nhiều durable subscription độc lập khiến mỗi subscriber nhận bản riêng |
| **RabbitMQ / AMQP** | Các worker consume **cùng một queue**, có thể có nhiều consumer trong mỗi worker | Bind mỗi worker vào queue khác nhau trên cùng fanout exchange sẽ phát việc lặp |
| **Kafka** | Các worker nằm trong **cùng `group.id`**; mỗi partition được gán cho một consumer trong group tại một thời điểm | Mỗi worker dùng `group.id` khác nhau khiến mỗi group nhận đầy đủ luồng; số consumer hữu ích bị giới hạn bởi số partition |

Kafka là log có offset, không phải work queue với ack từng message theo kiểu AMQP/JMS. Khi dùng Kafka làm transport cần thiết kế adapter, commit offset, retry và định tuyến reply phù hợp với Spring Batch Integration, thay vì coi cơ chế Kafka là bản sao cơ chế queue.

Một số hệ thống yêu cầu thứ tự xử lý theo khóa nghiệp vụ. **Single consumer cho mỗi message không đồng nghĩa giữ thứ tự toàn cục**. Có thể cần định tuyến cùng khóa vào một partition/nhóm tuần tự hoặc thiết kế writer chịu được xử lý lệch thứ tự. Việc khóa toàn bộ queue vào một consumer thường loại bỏ lợi ích mở rộng.

## 5. Acknowledgement, giao lại và độ tin cậy

Mục tiêu của middleware remote chunking thường gồm ba phần:

1. Message đã được manager gửi thành công phải có khả năng tồn tại qua sự cố broker/worker theo chính sách durability đã chọn.
2. Mỗi lần broker giao request, một consumer nhận quyền xử lý request đó.
3. Nếu chưa ghi nhận xử lý thành công, request có thể được **redeliver** theo chính sách retry/ack.

Ba phần này hợp lại thường dẫn đến cơ chế **at-least-once delivery**, tức *có thể xử lý trùng*. Broker không thể tự bảo đảm một phép ghi DB và một ack message là thao tác nguyên tử nếu chúng thuộc hai tài nguyên giao dịch độc lập.

### 5.1. Trình tự điển hình

~~~text
1. Manager tạo C-101 và gửi vào durable request queue.
2. Broker giao C-101 cho Worker A; message đang in-flight/unacked.
3. Worker A xử lý item và commit thay đổi nghiệp vụ.
4. Worker A gửi response thành công về luồng reply.
5. Consumer/broker hoàn tất ack theo cơ chế transport đã cấu hình.
6. Manager tương quan response với request C-101 và tổng hợp StepContribution.
~~~

Đây là mô hình tư duy, không phải cam kết mọi adapter luôn thực thi đúng thứ tự 3–5. Cần kiểm tra ranh giới transaction, cơ chế ack và xử lý reply của công nghệ cụ thể.

### 5.2. Phân tích điểm lỗi

| Thời điểm phát sinh sự cố | Rủi ro | Thiết kế mong muốn |
| --- | --- | --- |
| Trước khi worker commit DB | Request chưa hoàn tất | Rollback; broker có thể giao lại |
| Sau khi worker commit DB nhưng trước khi ack | DB đã thay đổi, broker có thể giao lại | Writer idempotent hoặc dedup trong cùng transaction nghiệp vụ |
| Broker đã coi request hoàn tất nhưng reply không đến manager | Manager chờ hoặc timeout | Có cơ chế phục hồi reply/trạng thái, theo dõi in-flight và xử lý tương quan |
| Worker nhận lại request từ lần chạy trước | Tác dụng nghiệp vụ có nguy cơ lặp | Nhận diện request đã thực hiện, tránh ghi lặp và bảo toàn hợp đồng reply |
| Message lỗi liên tục | Retry vô hạn, nghẽn hàng đợi | Retry có giới hạn, backoff và dead-letter queue để xử lý riêng |

**Không ack sớm chỉ để làm queue giảm backlog.** Nếu ack trước khi lưu kết quả bền vững mà worker crash, message có thể bị mất trong khi job chưa thực hiện công việc. Ngược lại, ack muộn có thể tăng redelivery; điều này phải được xử lý ở tầng dữ liệu.

Ở Spring AMQP, `AcknowledgeMode.AUTO` nghĩa container ack sau khi listener hoàn tất thành công, **không** có nghĩa broker tự ack ngay lúc giao message. `AcknowledgeMode.MANUAL` buộc ứng dụng chủ động ack/nack; thích hợp khi có yêu cầu phối hợp hoặc kiểm soát đặc biệt, nhưng đòi hỏi xử lý lỗi chặt chẽ. Các giá trị mặc định, retry và requeue phụ thuộc cấu hình listener container.

## 6. Bảo đảm tác dụng nghiệp vụ không bị nhân đôi

Mỗi chunk request thường bao gồm danh sách item và thông tin để manager tương quan kết quả. Tuy nhiên, **khử trùng theo số thứ tự chunk đơn độc là không đủ**: hai job khác nhau có thể đều có chunk số 1, và restart có thể tạo request mới với phạm vi công việc giao nhau. Cần chọn khóa nhận diện theo phạm vi thích hợp.

Có hai mức idempotency nên phân biệt:

- **Cấp chunk/message**: dùng định danh request ổn định trong đúng ngữ cảnh thực thi (chẳng hạn định danh execution cùng sequence) để tránh thực hiện cùng request nhiều lần. Nếu broker redeliver, worker cần vẫn đáp ứng đúng giao thức reply; không được im lặng bỏ qua request khiến manager chờ mãi.
- **Cấp nghiệp vụ/item**: dùng khóa duy nhất có ý nghĩa lâu dài, ví dụ `order_id` + `calculation_version`, để bảo đảm re-run job hoặc chunk mới có chứa cùng order cũng không tạo tác dụng phụ hai lần.

### 6.1. Ví dụ writer idempotent

Giả sử job tính tổng đơn hàng, kết quả mong muốn là một dòng tổng hợp cho mỗi `order_id`. Với PostgreSQL:

~~~sql
CREATE TABLE order_summary (
    order_id BIGINT PRIMARY KEY,
    total_amount NUMERIC(18, 2) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Có thể thực hiện lại cho cùng order_id mà không tạo thêm dòng.
INSERT INTO order_summary (order_id, total_amount)
VALUES (:order_id, :total_amount)
ON CONFLICT (order_id)
DO UPDATE SET
    total_amount = EXCLUDED.total_amount,
    updated_at = now();
~~~

Ở đây phép ghi có dạng **gán trạng thái đích xác định**, nên retry cùng giá trị không cộng dồn tiền. Ngược lại:

~~~sql
-- Không idempotent: nếu chạy lại sẽ cộng tiền hai lần.
UPDATE account_balance
SET balance = balance + :amount
WHERE account_id = :account_id;
~~~

Với nghiệp vụ bắt buộc tạo tác dụng phụ như chuyển tiền, gửi email hoặc gọi API thanh toán, hãy dùng **idempotency key được phía đích công nhận**, ràng buộc unique hoặc bảng ghi nhận xử lý kết hợp transaction/outbox. Không nên chỉ dựa vào bộ nhớ tại một worker: request có thể được giao lại cho worker khác.

### 6.2. Bảng dedup ở cấp request

Một phương án minh họa là:

~~~sql
CREATE TABLE processed_chunk_request (
    request_scope VARCHAR(160) NOT NULL,
    chunk_sequence INT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (request_scope, chunk_sequence)
);
~~~

`request_scope` phải được xây dựng từ định danh ổn định phù hợp với vòng đời request, có phân biệt job/step khi cần. Ở Spring Batch, các accessor của `ChunkRequest` có thể khác nhau giữa phiên bản (ví dụ định danh job trong API 5.x và 6.x), vì vậy hãy kiểm tra chính xác version dùng trong dự án.

Khi xử lý, thao tác đánh dấu request và cập nhật dữ liệu nghiệp vụ nên nằm trong **cùng một transaction của cùng database** nếu có thể. Nếu insert dấu đã xử lý commit trước nhưng ghi nghiệp vụ thất bại, lần redelivery sẽ bị bỏ qua sai. Nếu ghi nghiệp vụ thành công trước khi lưu dấu, redelivery vẫn có thể ghi lặp. Cũng cần lưu hoặc tái tạo một reply hợp lệ khi gặp message trùng, phù hợp với hợp đồng của manager.

Không nên triển khai một lớp dedup tự chế bên ngoài pipeline Spring Batch mà bỏ qua retry/skip và cách framework tính `StepContribution`. Khi cần khử trùng ở tầng message, hãy tích hợp tại ranh giới transaction đã hiểu rõ và kiểm tra tình huống reply trùng.

## 7. Cấu hình tham khảo với Spring Batch Integration

Spring Batch Integration cung cấp builder để tạo flow xử lý chunk ở worker. Ví dụ Java bên dưới minh họa **Spring Batch 5.x** (đối chiếu chữ ký API nếu dùng 6.x):

~~~java
import org.springframework.batch.integration.chunk.RemoteChunkingWorkerBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
class RemoteChunkWorkerConfiguration {

    @Bean
    IntegrationFlow remoteChunkWorker(
            MessageChannel incomingChunkRequests,
            MessageChannel outgoingChunkReplies,
            ItemProcessor<Long, OrderSummary> orderProcessor,
            ItemWriter<OrderSummary> orderWriter) {

        return new RemoteChunkingWorkerBuilder<Long, OrderSummary>()
                .itemProcessor(orderProcessor)
                .itemWriter(orderWriter)
                .inputChannel(incomingChunkRequests)
                .outputChannel(outgoingChunkReplies)
                .build();
    }
}
~~~

`OrderSummary` là kiểu dữ liệu nghiệp vụ minh họa; các `MessageChannel`, processor, writer và kết nối broker phải được khai báo riêng. Ví dụ thể hiện **worker flow**; nó chưa tạo queue, chưa cấu hình message converter, chưa tạo manager job, chưa xử lý mọi yêu cầu vận hành.

Các instance của worker có thể dùng cùng cấu hình flow. Điều quyết định single consumer nằm ở **cách inbound adapter của `incomingChunkRequests` nhận message từ broker**: mọi worker phải nhận từ cùng một logical work queue (hoặc cùng consumer group nếu dùng transport kiểu Kafka).

### 7.1. Ví dụ giới hạn concurrency của RabbitMQ listener

Với ứng dụng dùng **Spring AMQP `@RabbitListener` và SimpleRabbitListenerContainer** để nhận message từ cùng một queue, cấu hình minh họa:

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        concurrency: 2
        max-concurrency: 4
        prefetch: 1
        acknowledge-mode: auto
~~~

Cấu hình này điều chỉnh listener container tương ứng; **không mặc nhiên điều chỉnh** mọi Spring Integration AMQP inbound adapter. Với adapter Spring Integration, phải áp dụng concurrency/prefetch/ack vào container mà adapter thực sự sử dụng. Tránh tạo một request queue riêng cho từng worker.

`prefetch: 1` giúp hạn chế lượng message chưa ack trên mỗi consumer khi xử lý chậm, cho phép tải phân phối đều hơn trong một số tình huống; đó là lựa chọn thử nghiệm ban đầu, không phải giá trị tối ưu cho mọi workload. Có thể tăng prefetch khi xử lý nhanh và broker/DB còn dư tài nguyên, sau khi đã đo.

### 7.2. Thiết kế tên queue và định tuyến

Ví dụ một job có một nhóm worker:

~~~text
Direct exchange: batch.remote.request
Routing key:     order-summary.chunk
Queue chung:     batch.order-summary.requests
Consumers:       worker-1, worker-2, worker-3

Reply exchange:  batch.remote.reply
Reply queue:     batch.order-summary.replies.<manager-instance>
~~~

Tên chỉ mang tính minh họa. Nếu có nhiều manager hoặc nhiều job chạy đồng thời, cần chỉ rõ phạm vi reply và bảo đảm manager nhận đúng response. Không chuyển reply tới tất cả manager rồi để từng manager tự xử lý tùy ý; phải thiết kế routing/correlation có kiểm soát.

Đặc biệt với **JMS + Spring Integration**, các header phục vụ tương quan/aggregate reply như `correlationId`, `sequenceNumber`, `sequenceSize` phải được giữ qua mapper và adapter. Một số phiên bản Spring Integration dùng allowlist header; nếu thiếu mapping thì request đã xử lý xong nhưng manager vẫn có thể không tổng hợp được reply.

## 8. Chọn số consumer mà không phá tính đúng đắn

Single consumer không cấm concurrency. Nếu có 12 request độc lập và 4 consumer, một thời điểm có thể có tối đa 4 request được xử lý đồng thời ở 4 consumer (chưa tính cơ chế nhận trước/prefetch). Nhu cầu tài nguyên gần đúng:

\[
\text{Throughput worker tối đa lý tưởng (chunk/s)}
\approx \frac{\text{số consumer đang chạy}}{\text{thời gian xử lý trung bình mỗi chunk (s)}}
\]

Ví dụ, mỗi chunk cần trung bình 0,4 giây và có 6 consumer bận liên tục, khả năng lý tưởng của tầng worker là khoảng **15 chunk/giây**. Nếu manager chỉ cung cấp 8 chunk/giây thì worker rảnh; nếu DB đích chỉ chịu được 10 chunk/giây, tăng lên 12 consumer cũng không nâng throughput đến 30 chunk/giây.

Khi tuning, theo dõi đồng thời:

| Quan sát | Dấu hiệu | Hướng kiểm tra |
| --- | --- | --- |
| `ready/queued` tăng liên tục, workers luôn bận | Tốc độ xử lý thấp hơn tốc độ phát request | CPU, thời gian xử lý chunk, số consumer, độ chậm DB |
| `unacked/in-flight` cao nhưng write throughput thấp | Worker chậm, prefetch quá cao hoặc treo tác vụ | Latency, thread dump, transaction, network |
| Worker rảnh, manager xử lý ít chunk | Nút thắt ở reader/manager hoặc nguồn dữ liệu | Query reader, network gửi request, kích thước chunk |
| DB connection pool đầy, deadlock tăng | Oversubscription tại đích | Giảm concurrency, xem index/lock và transaction |
| Reply trễ, manager timeout | Nghẽn reply channel hoặc lỗi correlation | Reply queue, header mapping, consumer manager, log request ID |
| Redelivery/DLQ tăng | Lỗi lặp hoặc consumer crash | Retry/backoff, lỗi nghiệp vụ, poison message, dedup |

Không tăng consumer chỉ dựa vào độ dài queue. Hãy đo **chunk/s hoàn tất, p95/p99 latency, CPU, I/O, DB connection, lock waits, số lần redelivery** và tỉ lệ lỗi. Một thay đổi về concurrency có thể tăng tốc trong điều kiện ít tải nhưng làm DB đích sụp ở tải thực.

### 8.1. Thread safety vẫn là yêu cầu bắt buộc

Một instance worker có thể chạy nhiều listener thread. `ItemProcessor`, `ItemWriter`, dịch vụ gọi từ chúng và mọi cache/shared state phải an toàn khi concurrent. Tránh dùng biến instance mutable để lưu `currentOrder` hoặc `currentChunk` nếu chúng bị chia sẻ giữa thread. Ưu tiên dữ liệu bất biến, trạng thái cục bộ trong lời gọi và writer hỗ trợ concurrency đúng cách.

Single consumer cho một request **không** bảo đảm một đối tượng Spring bean chỉ được một thread truy cập. Khi cần tuần tự theo account/order, có thể dùng khóa nghiệp vụ, phân tuyến theo key hoặc cơ chế serialize thích hợp; đừng giả định mỗi queue chỉ một thread.

## 9. Restart, retry và quy tắc xử lý message trùng

Một job có thể restart sau khi manager hoặc worker ngừng. Manager thường phải khôi phục trạng thái job từ `JobRepository`, còn broker có thể vẫn giữ request chưa ack hoặc reply đến muộn. Cần phân biệt:

- **Retry trong worker**: thử lại xử lý một request/item theo chính sách retry khi gặp lỗi tạm thời. Cần backoff và giới hạn thử.
- **Broker redelivery**: broker giao lại một message chưa được ack; worker nhận lại có thể là instance khác.
- **Job restart**: tạo bước thực thi tiếp theo từ trạng thái lưu trong repository; có thể phát sinh request với dữ liệu nghiệp vụ đã từng được xử lý trước đó.

Điều kiện vận hành tốt là worker thực hiện các tác dụng nghiệp vụ có thể lặp an toàn và manager không mất khả năng biết request nào đã hoàn thành. Bảo đảm thực tế cần xem xét riêng theo transport, transaction và cấu hình framework; **không gọi toàn hệ thống là exactly once chỉ vì mỗi queue delivery có một consumer**.

Khi response bị lặp, manager/reply aggregator phải có hành vi có kiểm soát. Khi response thất lạc sau DB commit, chỉ tăng timeout không giải quyết tận gốc. Với tích hợp phức tạp, cần thiết kế phục hồi trạng thái, dedup response hoặc outbox cho sự kiện/reply tùy ranh giới hệ thống, và kiểm chứng bằng thử nghiệm crash.

### 9.1. Chính sách DLQ

Một message không thể giải mã, dữ liệu vi phạm ràng buộc hoặc lỗi nghiệp vụ cố định không nên được requeue vô hạn. Dùng cơ chế retry có giới hạn rồi đưa vào **dead-letter queue (DLQ)** kèm metadata đủ để điều tra:

~~~json
{
  "job": "orderSummaryJob",
  "requestId": "job-instance-87/chunk-12",
  "messageId": "C-101",
  "attempt": 5,
  "errorType": "InvalidOrderData",
  "errorSummary": "Missing currency for order 9012"
}
~~~

Đây là payload quan sát minh họa, không phải định dạng `ChunkRequest` mặc định của Spring Batch. Việc xử lý DLQ cần phân biệt message có thể phát lại an toàn với message phải sửa dữ liệu trước khi phát lại; mọi lần phát lại vẫn phải đi qua cơ chế idempotency.

## 10. Kịch bản kiểm thử single consumer

Triển khai một môi trường có một manager, một request queue và ba worker. Mỗi request được gắn một định danh quan sát ổn định; ghi log khi bắt đầu, khi commit, khi reply và khi ack. Trên dữ liệu thử nghiệm, thực hiện các bước:

| Kiểm thử | Thực hiện | Kết quả mong đợi |
| --- | --- | --- |
| 1. Chia tải | Gửi 100 chunk độc lập, ba worker cùng nghe một queue | Nhiều worker nhận các request khác nhau; một request không được đồng thời fan-out tới cả ba như ba bản sao độc lập |
| 2. Sai topology | Tạm chuyển sang ba queue/subscription riêng, mỗi worker một queue | Quan sát request bị nhân bản; xác nhận đây là cấu hình không phù hợp |
| 3. Crash trước commit | Giết worker khi transaction chưa commit | Request được giao lại hoặc xử lý theo failure policy; DB không lưu tác dụng nửa chừng |
| 4. Crash sau commit, trước ack | Mô phỏng mất ack sau khi DB đã commit | Có thể redeliver; kết quả nghiệp vụ cuối cùng không bị nhân đôi |
| 5. Duplicate reply | Gửi lại phản hồi cùng request khi thử nghiệm | Manager không tính đóng góp thành hai chunk và có hành vi logging/handling rõ ràng |
| 6. Manager/reply lỗi | Chặn reply tạm thời hoặc làm mất header correlation trong môi trường thử | Có metric/cảnh báo về request chờ; xác định được nguyên nhân, không báo job hoàn tất sai |
| 7. Tăng workers | So sánh 1, 2, 4, 8 consumer ở cùng workload | Throughput tăng đến khi gặp nút thắt; số bản ghi/kết quả nghiệp vụ không đổi |

Trước khi chạy trên production, cố định bộ dữ liệu đầu vào và kiểm tra được bất biến:

~~~text
Số order_summary duy nhất cuối cùng
    == số order hợp lệ cần tổng hợp

Giá trị total_amount của từng order
    == giá trị tính từ nguồn đáng tin cậy

Không có request bị mất âm thầm
    và mọi request thất bại có dấu vết để xử lý
~~~

Khi đo số lần *nhận request* trong log, một request có thể xuất hiện nhiều lần do retry. Điều cần giữ là **không fan-out chủ ý một work item đến nhiều worker** và **không tạo tác dụng nghiệp vụ lặp**.

## 11. Những nhầm lẫn thường gặp

| Nhận định | Đánh giá và lý do |
| --- | --- |
| “Muốn single consumer thì chỉ được chạy một worker.” | **Sai.** Có thể chạy nhiều worker cạnh tranh trên cùng queue; mỗi request được giao cho một consumer trong một lần phân phối. |
| “Một queue có ba consumer sẽ xử lý message đúng một lần.” | **Sai.** Crash sau commit nhưng trước ack có thể gây redelivery; cần idempotency. |
| “Mỗi worker có queue riêng và cùng bind vào fanout exchange sẽ cân bằng tải.” | **Sai.** Fanout có thể sao chép message đến mọi queue được bind. |
| “Bật manual ack là giải quyết được exactly once.” | **Sai.** Ack không tự nguyên tử với transaction DB và reply. |
| “Một consumer cho mỗi message bảo đảm order toàn cục.” | **Sai.** Nhiều message có thể chạy song song và hoàn tất lệch thứ tự. |
| “Thêm consumer luôn tăng throughput.” | **Sai.** Manager, broker, cơ sở dữ liệu đích, kết nối và lock có thể là nút thắt. |
| “Kafka có cùng `group.id` thì tăng bao nhiêu consumer cũng được.” | **Sai.** Số consumer xử lý đồng thời trong một group bị giới hạn thực tế bởi số partition được gán. |

## 12. Câu hỏi tự kiểm tra

1. Vì sao một JMS Topic có ba subscription độc lập là cấu hình nguy hiểm cho request remote chunking, dù cả ba worker đều chạy thành công?
2. Phân biệt một message được giao cho một consumer **tại một thời điểm** với yêu cầu kết quả nghiệp vụ **chỉ xảy ra một lần**.
3. Worker ghi xong một đơn hàng rồi crash trước ack. Những thành phần nào phải phối hợp để xử lý request được giao lại?
4. Khi tăng từ 4 lên 8 worker mà throughput không đổi và DB lock wait tăng, bạn sẽ điều chỉnh gì trước?
5. Nếu request queue hoạt động tốt nhưng manager treo vì không nhận reply, bạn cần kiểm tra topology và metadata nào?

**Gợi ý đáp án:** (1) Topic phát các bản message cho nhiều subscription, dẫn đến xử lý cùng chunk nhiều lần. (2) Điều đầu là phân phối của broker; điều sau là thuộc tính của cả quy trình, cần idempotency/transaction. (3) Broker redelivery, worker idempotent, transaction và reply/manager correlation. (4) Kiểm tra DB contention và giảm/điều tiết concurrency. (5) Reply route/queue, trạng thái consumer nhận reply, `correlationId` và các header sequence cần thiết.

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing, Remote Chunking](https://docs.spring.io/spring-batch/reference/scalability.html): mô hình manager/worker và yêu cầu middleware cho remote chunking.
- [Spring Batch Reference — Externalizing Batch Process Execution](https://docs.spring.io/spring-batch/reference/spring-batch-integration/externalizing-execution.html): cách sử dụng Spring Integration, luồng request/reply và lưu ý mapping header JMS.
- [Spring Batch 5.2 API — RemoteChunkingWorkerBuilder](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/integration/chunk/RemoteChunkingWorkerBuilder.html): tham khảo cách cấu hình worker flow; cần đối chiếu với version sử dụng.
- [Spring AMQP — Message Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): concurrency, prefetch, ack và đặc tính listener container.
- [Apache Kafka — KafkaConsumer API](https://kafka.apache.org/39/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html): consumer group và nguyên tắc phân chia partition.

**Điểm cần nắm vững:** Remote chunking mở rộng bằng cách để nhiều worker **cạnh tranh nhận các chunk request khác nhau** qua một luồng công việc chung. Yêu cầu “single consumer cho mỗi message” là quy tắc phân phối một request; độ tin cậy khi retry, restart và redelivery vẫn phải được bảo đảm bằng thiết kế transaction, idempotency và reply correlation.
