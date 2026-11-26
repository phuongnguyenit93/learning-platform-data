# Giới hạn khác nhau giữa SMLC và DMLC

Trong Spring AMQP, `SimpleMessageListenerContainer` (**SMLC**) và `DirectMessageListenerContainer` (**DMLC**) đều nhận message từ RabbitMQ để chuyển đến `@RabbitListener`. Tuy nhiên, **khả năng xử lý theo lô không giống nhau**. Một số thuộc tính tạo batch thực sự cho listener, một số chỉ giảm số lần gửi ACK, còn một số chỉ tách batch mà producer đã đóng gói trước đó. Chọn sai container hoặc nhầm ý nghĩa cấu hình có thể khiến listener không nhận được `List` như dự kiến, gom ACK ngoài ý muốn hoặc làm tăng số message bị giao lại sau sự cố.

Bài học thuộc chương **Xử lý theo lô** của module **SPRING_AMQP**. Ta sẽ đối chiếu các giới hạn của SMLC và DMLC trong quá trình tích hợp RabbitMQ qua queue, exchange, binding, `RabbitTemplate` và `@RabbitListener`; sau đó xây cấu hình mẫu và cách kiểm chứng ACK, transaction, retry và dead-letter để xử lý bất đồng bộ đáng tin cậy.

## 1. Trước hết, phải phân biệt ba kiểu “batch”

| Cơ chế | Ai gom? | RabbitMQ giao gì? | Listener có nhất thiết nhận `List`? |
|---|---|---|---|
| **Producer-created batch** | Publisher, ví dụ `BatchingRabbitTemplate` | Một *physical AMQP message* chứa nhiều phần tử logic, có metadata batch | Không. Có thể tách để gọi từng phần tử hoặc gọi listener một lần với `List` |
| **Consumer-created batch** | Listener container gom các message **rời** đã nhận từ broker | Nhiều physical deliveries riêng, mỗi delivery có tag | Có, nếu bật `consumerBatchEnabled` và listener hỗ trợ batch |
| **ACK batching** | Listener container trì hoãn/gom acknowledgment | Vẫn nhận từng physical delivery | **Không**. Listener có thể vẫn được gọi từng message |

Điều cần nhớ: **gom ACK ≠ gom payload để xử lý cùng lúc**. Cấu hình cho “20 messages per ACK” không đồng nghĩa method `@RabbitListener` nhận `List` gồm 20 message. Ngược lại, khi publisher gói 20 phần tử vào **một** AMQP message, broker chỉ có **một delivery tag** cho toàn bộ gói đó.

Giả sử publisher gửi liên tiếp ba message `A`, `B`, `C`. Với consumer batching, SMLC có thể gọi:

~~~text
RabbitMQ: A[tag=1]  B[tag=2]  C[tag=3]
SMLC:     gom [A, B, C] --> listener(List<Message>)
~~~

Nếu publisher gửi một envelope chứa ba phần tử:

~~~text
RabbitMQ: [A|B|C][tag=1]  (một message vật lý)
SMLC/DMLC: de-batch --> A, B, C (hoặc listener(List<Message>))
~~~

Hai hình thức có số delivery tag, phạm vi ACK và tác động khi retry khác nhau.

## 2. Kiến trúc SMLC và DMLC

### SMLC: thread consumer độc lập, có bước gom message

SMLC tiếp nhận delivery từ thread của RabbitMQ client, đưa vào hàng đợi nội bộ rồi xử lý trên thread dành cho consumer. Lớp trung gian này hỗ trợ đợi và gom nhiều delivery thành một batch phía consumer. Container có thể khởi tạo số consumer ban đầu, tăng/giảm số consumer theo hoạt động và thực hiện acknowledgment/transaction theo `batchSize`.

### DMLC: gọi listener trên thread RabbitMQ client

DMLC gọi listener trực tiếp trên thread do RabbitMQ client quản lý. Cách này tránh một bước chuyển thread, cho phép thay đổi queue đang lắng nghe hiệu quả hơn và cấu hình số consumer **trên từng queue**. Đổi lại, DMLC **không cung cấp `consumerBatchEnabled` và `batchSize` của SMLC**. Nó có `messagesPerAck` để giảm lượng acknowledgment và vẫn có thể tách batch do producer tạo.

~~~mermaid
flowchart TB
    subgraph S["SMLC"]
      S1["RabbitMQ client delivery"] --> S2["Hàng đợi nội bộ"]
      S2 --> S3["Thread của consumer"]
      S3 --> S4{"consumerBatchEnabled?"}
      S4 -->|"Có"| S5["Gom tối đa batchSize physical messages"]
      S4 -->|"Không"| S6["Chuyển từng message"]
      S5 --> S7["@RabbitListener nhận List"]
      S6 --> S8["@RabbitListener nhận từng message"]
    end
    subgraph D["DMLC"]
      D1["RabbitMQ client delivery"] --> D2["Gọi listener trực tiếp"]
      D2 --> D3["@RabbitListener nhận từng message"]
      D3 --> D4["messagesPerAck: gom ACK, không gom payload"]
    end
~~~

Sơ đồ mô tả **message rời từ broker**. Với **producer-created batch**, cả hai container đều hỗ trợ de-batching; trường hợp đó không thuộc nhánh `consumerBatchEnabled`.

## 3. Bảng giới hạn: tính năng nào thuộc container nào?

| Khả năng / thuộc tính | SMLC | DMLC | Hệ quả khi chọn |
|---|---|---|---|
| Gom các message rời do broker giao thành `List` | **Có**, `consumerBatchEnabled` | **Không** | Muốn xử lý 10–50 message rời trong một callback: chọn SMLC |
| `batchSize` | **Có** | **Không** | Ở SMLC, ảnh hưởng kích thước consumer batch, tần suất ACK và giao dịch tùy chế độ |
| `receiveTimeout`, `batchReceiveTimeout` khi gom batch | **Có** | **Không** | SMLC có thể trả về partial batch khi không đủ message |
| `messagesPerAck`, `ackTimeout` | Không dùng theo cơ chế DMLC | **Có** | DMLC giảm số ACK mà vẫn gọi listener từng delivery |
| De-batching batch do producer tạo | **Có** | **Có** | DMLC vẫn có thể hỗ trợ batch listener cho producer-created batch |
| `batchListener = true` với `List` đầu vào | **Có** | **Có** cho batch do producer tạo | Chỉ định kiểu adapter; tự nó không bật gom message rời |
| Giao dịch AMQP (`channelTransacted`) | **Có** | **Có** | Nhưng `messagesPerAck` của DMLC **không được dùng cùng transacted channel** |
| Gom nhiều message trong một lần AMQP commit qua `batchSize` | **Có** | **Không** | Với DMLC, message được ACK/commit riêng trong từng transaction |
| `concurrentConsumers` / `maxConcurrentConsumers` và autoscaling | **Có** | **Không** | DMLC dùng `consumersPerQueue`, thay đổi lập trình được |
| `consumersPerQueue` | Không | **Có** | DMLC cấu hình số consumer cho mỗi queue |
| Thêm/bớt queue khi đang chạy | Có, thường phải khởi tạo lại consumer liên quan | Có, ảnh hưởng ít hơn đến consumer của queue khác | DMLC thuận tiện khi danh sách queue thay đổi |
| Listener method trả về reply khi nhận batch `List` | **Không được hỗ trợ trong batch listener** | **Không được hỗ trợ trong batch listener** | Với nhiều đầu vào, không rõ cách ghép một reply với từng request |

**Không kết luận “DMLC không hỗ trợ batch” theo nghĩa tuyệt đối.** Điều đúng là DMLC **không tự gom nhiều physical deliveries rời thành consumer-side batch**. Nó vẫn hiểu batch được đóng gói từ phía publisher, và vẫn có tối ưu hóa ACK.

## 4. SMLC: cấu hình consumer-side batching

Giả sử nghiệp vụ cần ghi hàng loạt hóa đơn: publisher gửi từng sự kiện lên `billing.work.x` với routing key `billing.created`, binding đến `billing.work.q`. Consumer muốn gọi DAO theo lô để giảm chi phí database.

Ví dụ cấu hình Java (phù hợp Spring AMQP **3.1.2+** cho thuộc tính `batchReceiveTimeout`):

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BatchListenerConfiguration {

    @Bean("consumerBatchFactory")
    SimpleRabbitListenerContainerFactory consumerBatchFactory(
            ConnectionFactory connectionFactory) {

        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);

        // Kích hoạt nhận một List các message rời từ broker.
        factory.setBatchListener(true);
        factory.setConsumerBatchEnabled(true);
        factory.setBatchSize(20);

        // Trả partial batch nếu lưu lượng thấp.
        factory.setReceiveTimeout(200L);
        factory.setBatchReceiveTimeout(1_000L);

        factory.setConcurrentConsumers(2);
        factory.setMaxConcurrentConsumers(4);
        factory.setPrefetchCount(40);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        return factory;
    }
}
~~~

Listener nhận dữ liệu dạng một danh sách:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class BillingBatchListener {
    private final BillingService billingService;

    public BillingBatchListener(BillingService billingService) {
        this.billingService = billingService;
    }

    @RabbitListener(
            queues = "billing.work.q",
            containerFactory = "consumerBatchFactory")
    public void handle(List<Message> batch) {
        List<String> events = batch.stream()
                .map(m -> new String(m.getBody(), StandardCharsets.UTF_8))
                .toList();

        billingService.saveAll(events); // Ném lỗi nếu toàn batch thất bại.
    }
}
~~~

`BillingService.saveAll` là hàm nghiệp vụ giả định, cần được cài đặt trong ứng dụng. Việc chuyển body thành `String` chỉ nhằm minh họa; production nên xác thực schema và sử dụng `MessageConverter` tương ứng. `List<org.springframework.amqp.core.Message>` cho phép truy cập header và delivery tag; nếu khai báo `List<Invoice>` với converter thích hợp, method nhận payload đã chuyển đổi.

**Ý nghĩa từng cấu hình:**

1. `batchListener(true)`: chọn listener adapter nhận một danh sách. Trong Spring AMQP **3.0+**, `consumerBatchEnabled(true)` trên factory cũng tự bật chế độ batch listener; khai báo tường minh cả hai giúp ví dụ dễ hiểu.
2. `consumerBatchEnabled(true)`: yêu cầu SMLC **gom các message rời**. Khi bật, `deBatchingEnabled` cần là `true` và factory sẽ bảo đảm điều này.
3. `batchSize(20)`: giới hạn mục tiêu là **20 physical messages nhận từ RabbitMQ**, không nhất thiết là 20 phần tử logic sau de-batching producer batches.
4. `receiveTimeout`: một trong những mốc để giao partial batch khi không đủ lưu lượng. `batchReceiveTimeout` (có từ Spring AMQP 3.1.2) giới hạn tổng thời gian gom batch; không có nó ở phiên bản cũ.
5. `prefetchCount(40)`: RabbitMQ có thể giữ tối đa số lượng unacked tương ứng trên **mỗi consumer**; phải tính thêm số consumer đang hoạt động khi dự trù bộ nhớ.
6. `AUTO`: container tự ACK khi listener hoàn tất thành công; nếu listener ném exception, xử lý lỗi/requeue tuân theo chính sách. Không tự gọi `basicAck` trong method này.

**Quan trọng:** SMLC có thể giao **ít hơn** 20 message khi timeout; nếu một physical message là batch do producer tạo, danh sách đã tách có thể có **nhiều hơn** 20 phần tử logic. Vì vậy, thiết kế service nên chấp nhận batch có kích thước biến thiên.

## 5. DMLC: `messagesPerAck` chỉ tối ưu acknowledgment

Nếu mục tiêu là xử lý từng message độc lập nhưng giảm số lệnh ACK trên đường truyền, dùng DMLC với `messagesPerAck`:

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.DirectRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DirectListenerConfiguration {

    @Bean("directFactory")
    DirectRabbitListenerContainerFactory directFactory(
            ConnectionFactory connectionFactory) {

        DirectRabbitListenerContainerFactory factory =
                new DirectRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);

        factory.setConsumersPerQueue(2);
        factory.setPrefetchCount(40);
        factory.setMessagesPerAck(20);
        factory.setAckTimeout(1_000L);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        return factory;
    }
}
~~~

~~~java
@RabbitListener(queues = "billing.work.q", containerFactory = "directFactory")
public void handleOne(byte[] body) {
    billingService.saveOne(body);
}
~~~

Trong ví dụ này, framework vẫn gọi `handleOne` **một lần cho mỗi physical delivery**. Sau khi các callback xử lý thành công, container có thể gộp acknowledgment cho một nhóm message. `ackTimeout` chỉ là ngưỡng thời gian *xấp xỉ*: khi lưu lượng thấp, ACK có thể được gửi ở lần nhận tiếp theo hoặc khi vòng monitor kiểm tra; không hứa chính xác 1.000 ms.

Khi listener ném exception, DMLC xử lý các pending acknowledgments phù hợp rồi reject message lỗi; vì thế `messagesPerAck` cũng ảnh hưởng phạm vi giao lại khi kết nối chết trước khi ACK. Nếu `prefetchCount` đặt nhỏ hơn `messagesPerAck`, container tăng prefetch để không làm ngưỡng ACK bị kẹt.

Không bật `channelTransacted(true)` đồng thời với `messagesPerAck(20)`: **hai cấu hình không tương thích**. Với channel transacted, DMLC ACK/commit mỗi message trong transaction riêng. Đây là khác biệt then chốt so với việc SMLC dùng `batchSize` để gom nhiều message vào một lần commit.

## 6. DMLC vẫn nhận được batch từ producer

Một publisher có thể dùng `BatchingRabbitTemplate` với `SimpleBatchingStrategy` để đóng gói nhiều phần tử vào **một** physical AMQP message. Strategy mặc định dạng này ghi metadata `springBatchFormat=lengthHeader4` để consumer biết cách tách payload. Việc gom trên publisher có thể giữ message trong bộ nhớ trước khi gửi; cần timeout, giới hạn dung lượng và cân nhắc mất message chưa flush khi tiến trình dừng đột ngột.

Cả SMLC và DMLC có thể de-batch kiểu message đó. Trong các phiên bản Spring AMQP hiện đại (hỗ trợ từ **2.2.7** cho dạng `List<Message>` với listener hỗ trợ batch), cấu hình `batchListener(true)` cho DMLC để method nhận các phần tử trong một envelope:

~~~java
@Bean("producerBatchDirectFactory")
DirectRabbitListenerContainerFactory producerBatchDirectFactory(
        ConnectionFactory connectionFactory) {
    DirectRabbitListenerContainerFactory factory =
            new DirectRabbitListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setBatchListener(true);
    factory.setConsumersPerQueue(2);
    return factory;
}
~~~

~~~java
@RabbitListener(
        queues = "billing.producer-batch.q",
        containerFactory = "producerBatchDirectFactory")
public void onProducerBatch(List<org.springframework.amqp.core.Message> fragments) {
    billingService.saveAllFragments(fragments);
}
~~~

**Giới hạn:** method nhận danh sách vì **publisher đã gói sẵn**. Nếu publisher gửi 100 message rời, DMLC không tự gom 100 message đó vào danh sách bằng `batchSize` hay `messagesPerAck`; phải đổi sang SMLC với `consumerBatchEnabled`, hoặc chủ động gom ở tầng ứng dụng bằng một cơ chế riêng có kiểm soát.

Khi `batchListener(true)` được bật mà không bật consumer batching, quá trình de-batch producer message được chuyển về listener adapter. Cách cấu hình này không nên dùng chung với listener nhiều method `@RabbitHandler`, vì batch-enabled factory không hỗ trợ kiểu multi-method listener.

## 7. ACK, transaction và phạm vi thất bại không giống nhau

Điều quan trọng không chỉ là bao nhiêu message trong `List`, mà là **đơn vị RabbitMQ coi là đã giao và đã ACK**.

| Tình huống | Tác động chính |
|---|---|
| **SMLC consumer-created batch** gồm 10 physical deliveries, listener ném exception | Nhiều delivery của batch có thể bị ảnh hưởng bởi cách ACK/rollback/requeue; không được giả định một phần tử xử lý thành công sẽ luôn được ACK riêng |
| **DMLC `messagesPerAck(10)`** và callback xử lý từng message | Listener vẫn xử lý từng delivery; ACK có thể trì hoãn/gom. Kết nối chết trước ACK có thể khiến các message đã chạy nghiệp vụ được giao lại |
| **Producer-created batch** gồm 10 phần tử trong một physical delivery | Broker chỉ biết **một** delivery; reject hoặc dead-letter có thể ảnh hưởng **cả envelope**, dù chỉ một phần tử logic lỗi |
| **SMLC `channelTransacted(true)` và `batchSize`** | Có thể gom nhiều delivery vào một transaction AMQP; rollback làm tăng phạm vi giao lại |
| **DMLC `channelTransacted(true)`** | Hỗ trợ transaction, nhưng không có cơ chế `batchSize` gom nhiều delivery trong cùng AMQP transaction |

### 7.1. `batchSize` không phải một transaction database

Với SMLC, `batchSize` có thể quyết định thời điểm ACK hoặc commit của **AMQP channel transaction** khi các chế độ tương ứng được bật. Nó **không tự biến** các lệnh ghi cơ sở dữ liệu thành một transaction chung với RabbitMQ. Nếu database đã commit nhưng broker chưa nhận ACK, sau khi consumer chết RabbitMQ có thể giao lại các message đó. Một consumer an toàn phải dùng khóa idempotency, kiểm tra trùng lặp theo business key hoặc inbox table.

### 7.2. Retry một phần tử thất bại không hẳn là retry riêng phần tử đó

Giả sử batch gồm `A`, `B`, `C`; service ghi `A` thành công rồi `B` thất bại. Nếu listener ném exception để hệ thống retry toàn batch, `A` có thể bị ghi lại. Với producer-created batch, cả ba phần tử nằm trong cùng một physical message nên broker không thể ACK riêng `A`. Với consumer-created batch, mỗi phần tử có tag riêng nhưng container và acknowledgment policy vẫn quyết định đơn vị được commit/requeue.

Hai hướng thiết kế thường dùng:

- **All-or-nothing:** nghiệp vụ xử lý toàn batch trong transaction database phù hợp; khi lỗi, batch được thử lại; phải chống trùng lặp nếu xảy ra retry sau commit.
- **Tách kết quả từng phần tử:** ghi nhận phần tử thành công bằng idempotency; các phần tử lỗi được publish lại sang retry/DLX có kiểm soát bằng `RabbitTemplate`, chờ publisher confirm trước khi xác nhận đầu vào phù hợp. Cần thiết kế rõ mối quan hệ giữa ACK gốc và publish bản sao để không làm mất message.

Không gọi `basicAck` cho từng phần tử đã de-batch từ cùng một producer envelope: các phần tử logic **không có delivery tag vật lý riêng**. Với chế độ `MANUAL` và consumer batch gồm các physical deliveries rời, chỉ ACK đúng các tag hợp lệ trên đúng channel; một ACK dùng `multiple=true` có thể xác nhận cả delivery khác mà bạn chưa xử lý xong.

## 8. Concurrency, latency và backpressure

SMLC cho phép cấu hình `concurrentConsumers`, `maxConcurrentConsumers` cùng các ngưỡng mở rộng/thu hẹp. Nó có bước bàn giao từ RabbitMQ client thread tới consumer thread và vì thế thích hợp khi cần gom batch hoặc muốn điều khiển việc tăng giảm consumer theo hoạt động. DMLC dùng `consumersPerQueue` và thread pool của RabbitMQ client; không có bộ autoscaling kiểu SMLC, nhưng số consumer trên từng queue có thể điều chỉnh trong lúc chạy.

Ví dụ cùng lắng nghe 3 queue:

~~~text
SMLC concurrentConsumers=2:
  2 consumer threads dùng để lấy message từ các queue đã cấu hình.

DMLC consumersPerQueue=2:
  3 queue × 2 consumers/queue = 6 consumers được tạo ở phía broker.
~~~

Không xem hai con số “2” là hai cấu hình tương đương về tài nguyên hoặc mức song song. Ngoài ra, prefetch được áp dụng theo consumer; nếu cấu hình prefetch cao và message lớn, cả lượng message chưa ACK lẫn bộ nhớ sử dụng có thể tăng nhanh.

Một mô hình ước lượng ban đầu:

~~~text
Số physical deliveries có thể đang unacked
  ≈ tổng số consumer đang hoạt động × prefetch mỗi consumer

Bộ nhớ tối thiểu cho payload đang giữ
  ≈ số deliveries trong bộ đệm × kích thước payload trung bình
~~~

Đây chỉ là ước lượng dung lượng, chưa tính object overhead, body sau chuyển đổi, danh sách batch, task đang chạy hay dữ liệu trong ứng dụng. Với SMLC consumer batching, nên đo đồng thời **kích thước batch thực tế**, **thời gian chờ fill batch** và **thời gian xử lý batch**. Batch quá lớn có thể làm tăng độ trễ của message đầu tiên và tạo nhóm retry lớn khi có lỗi.

## 9. So sánh hai cấu hình thực tế

Giả sử dịch vụ gửi 120 sự kiện hóa đơn mỗi giây, database có API `saveAll` hiệu quả, và mỗi sự kiện được publish **riêng lẻ** bằng `RabbitTemplate`.

**Phương án A — SMLC consumer batching**

~~~text
Producer --> 120 physical deliveries/s --> SMLC
  consumerBatchEnabled=true; batchSize=20
  --> @RabbitListener(List<Message>)
  --> saveAll(20 events) hoặc partial batch
~~~

Đây là lựa chọn tự nhiên khi ứng dụng thật sự muốn gộp nhiều message broker thành một thao tác database/API. Độ trễ của từng phần tử phụ thuộc tốc độ tích lũy batch và thời gian chờ, còn lỗi của một phần tử có thể ảnh hưởng phần tử khác nếu chưa xử lý kết quả riêng.

**Phương án B — DMLC ACK batching**

~~~text
Producer --> 120 physical deliveries/s --> DMLC
  messagesPerAck=20
  --> @RabbitListener(byte[] body) mỗi message
  --> saveOne(event)
  --> container gom ACK
~~~

Phương án này chỉ giảm overhead acknowledgment; database vẫn nhận khoảng 120 lời gọi `saveOne` mỗi giây. Nếu lưu lượng 120 sự kiện/giây trên toàn ứng dụng nhưng có nhiều consumer, mỗi consumer nhận ít hơn; thực tế có thể gửi ACK theo timeout trước khi đạt ngưỡng 20.

**Phương án C — Producer-created batch + DMLC**

~~~text
BatchingRabbitTemplate --> envelopes chứa N phần tử
  --> DMLC batchListener=true
  --> @RabbitListener(List<Message>) mỗi envelope
~~~

Phương án C cho phép dùng DMLC nhưng đòi hỏi producer chịu trách nhiệm gom và flush. Nó không thay thế khả năng gom các delivery rời của SMLC, và một lỗi trong envelope ảnh hưởng đơn vị ACK ở cấp physical message.

## 10. Chọn container theo yêu cầu

| Yêu cầu thực tế | Lựa chọn khởi đầu | Cần kiểm tra thêm |
|---|---|---|
| Các producer gửi message rời, consumer cần nhận `List` để `saveAll` | **SMLC + consumerBatchEnabled** | BatchSize, timeout, converter, chính sách lỗi từng record |
| Muốn giảm lưu lượng ACK, listener vẫn xử lý từng message | **DMLC + messagesPerAck** | ACK trễ, prefetch, duplicate sau mất kết nối |
| Producer đã tạo batch và listener muốn nhận `List` | **SMLC hoặc DMLC + batchListener** | Format `springBatchFormat`, phạm vi reject một envelope |
| Cần nhiều delivery trong cùng AMQP transaction theo `batchSize` | **SMLC** | Rollback, duplicate, không đồng nhất nguyên tử với DB |
| Thường xuyên thêm/bỏ queue khi runtime, không cần consumer batching | **DMLC** | consumersPerQueue, thread pool, prefetch |
| Muốn autoscaling consumer có ngưỡng min/max | **SMLC** | Trigger, khoảng thời gian tăng/giảm |
| Cần reply cho từng yêu cầu trong `List` | Thiết kế lại request/reply | Batch listener không hỗ trợ reply tự động |

Một lỗi cấu hình thường gặp là đổi Spring Boot listener type từ `simple` sang `direct` rồi giữ nguyên ý định dùng `batchSize` để gọi `List`. Đổi loại container **không tự chuyển** logic consumer batching sang DMLC. Nên gắn `containerFactory` tường minh cho những listener có yêu cầu batching đặc biệt.

## 11. Kiểm chứng bằng thí nghiệm nhỏ

Để xác nhận lựa chọn container trong môi trường của bạn, dùng queue thử nghiệm với dead-letter exchange và các binding tách biệt. Publisher lần lượt gửi message rời, rồi thử producer-created batch.

| Thí nghiệm | Mong đợi ở SMLC | Mong đợi ở DMLC |
|---|---|---|
| Gửi 30 message rời, cấu hình batchSize=10 | Khi bật consumerBatchEnabled, nhận nhiều lần callback `List` theo batch size/timeout | Không có consumer-side batch; nhận từng delivery |
| Chỉ gửi 3 message rồi ngừng | Có thể nhận partial batch khi hết thời gian chờ | Không có khái niệm partial consumer batch |
| Gửi producer envelope chứa nhiều phần tử | Có thể de-batch để đưa vào listener `List` | Cũng có thể de-batch producer envelope vào `List` |
| Dùng `messagesPerAck=10` | Không áp dụng cho SMLC | Listener vẫn chạy một message/lần, ACK gom theo ngưỡng/timeout |
| Bật `channelTransacted=true` cùng messagesPerAck | Không thuộc cấu hình SMLC | Cấu hình không hợp lệ |
| Dừng consumer khi đã xử lý nhưng chưa ACK | Có thể redeliver các message trong phạm vi chưa ACK/commit | Có thể redeliver những message đang chờ ACK |
| Làm một phần tử trong producer batch bị lỗi | Cần xét cả physical envelope | Cần xét cả physical envelope |
| Thêm queue lúc runtime | Các consumer liên quan có thể phải khởi tạo lại | Các consumer của queue khác ít bị ảnh hưởng |

Quan sát trên RabbitMQ Management và log ứng dụng: số consumers, unacked, redelivered, ACK rate, chiều sâu dead-letter queue, kích thước `List` nhận được, tổng số lời gọi service và độ trễ ACK. **Không đánh đồng “gọi listener ít lần” với “gửi ACK ít lần”**; hai chỉ số phản ánh hai tối ưu hóa khác nhau.

## 12. Những giới hạn cần ghi nhớ

1. **SMLC có `consumerBatchEnabled`; DMLC không có.** Đây là khác biệt quyết định khi nhiều publisher gửi message rời và consumer muốn nhận `List`.
2. **SMLC `batchSize` đa nghĩa:** kích thước physical consumer batch khi đã bật consumer batching, ngưỡng ACK ở chế độ `AUTO`, và phạm vi commit trên AMQP transactional channel.
3. **DMLC `messagesPerAck` chỉ gom acknowledgment**, với `ackTimeout` gần đúng; không biến các message rời thành một callback và không dùng cùng transacted channel.
4. **Cả hai có thể de-batch producer-created message**; broker vẫn ACK/reject theo physical envelope, nên một phần tử logic lỗi có thể kéo theo phần tử khác.
5. **Batch lớn hơn làm tăng hiệu quả thông lượng nhưng mở rộng phạm vi duplicate, độ trễ và bộ nhớ.** Cần thiết kế idempotency, retry hữu hạn, dead-letter queue và quan sát vận hành ngay từ đầu.

### Tài liệu chính thức để đối chiếu theo phiên bản

- [Spring AMQP — Choosing a Container](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/choose-container.html): kiến trúc, các tính năng SMLC có mà DMLC không có.
- [Spring AMQP — Message Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): bảng thuộc tính, ACK, transaction, prefetch, timeout và hỗ trợ theo container.
- [Spring AMQP — @RabbitListener with Batching](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/batch.html): listener `List`, `consumerBatchEnabled`, producer batching và các giới hạn của batch listener.
- [Spring AMQP — Batched Messages](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/de-batching.html): cách de-batch và khác biệt giữa message rời với batch tạo từ producer.

Kết luận cho thiết kế: hãy chọn **SMLC khi cần container gom các message rời thành một lô để xử lý nghiệp vụ**, và chọn **DMLC khi cần xử lý từng delivery với mô hình thread trực tiếp hoặc muốn gom ACK**. Nếu đã có producer-created batch, cả hai đều có thể tiêu thụ theo `List`. Sau khi chọn, hãy kiểm tra phạm vi acknowledgment, transaction, retry và message có thể bị giao lại; chính các ranh giới này quyết định tính đáng tin cậy của hệ thống.
