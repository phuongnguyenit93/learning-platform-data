# Giới hạn số lượng, kích thước và thời gian chờ gom lô

Khi một ứng dụng Spring AMQP phải xử lý hàng nghìn sự kiện đơn hàng, gửi hoặc ghi từng message có thể tạo nhiều lần gọi mạng và nhiều giao dịch cơ sở dữ liệu. **Batch processing (xử lý theo lô)** gom nhiều message thành một đơn vị gửi hoặc xử lý để giảm chi phí cố định. Đổi lại, message có thể phải chờ, bộ nhớ bị giữ lại lâu hơn và phạm vi ảnh hưởng của một lỗi có thể lớn hơn.

Vì thế, một batch tốt cần đồng thời xem xét ba giới hạn:

- **Số lượng**: tối đa bao nhiêu message hoặc bản ghi được gom trước khi xử lý?
- **Kích thước**: tổng bao nhiêu byte là phù hợp cho một lần gửi hoặc ghi?
- **Thời gian chờ**: khi lưu lượng thấp, bao lâu thì nên xử lý một lô chưa đầy?

Bài này thuộc chương **Xử lý theo lô** của module **SPRING_AMQP**, tập trung vào RabbitMQ, `RabbitTemplate`, `@RabbitListener`, exchange, queue, binding và cơ chế xác nhận giao nhận. Mục tiêu là chọn các ngưỡng có thể kiểm chứng, tránh giữ lô vô hạn, hạn chế memory spike và không đánh mất khả năng retry, dead-letter, giám sát trong hệ thống bất đồng bộ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **producer batching** với **consumer batching** trong Spring AMQP.
2. Giải thích ý nghĩa và mối quan hệ của `batchSize`, `bufferLimit`, `timeout`, `receiveTimeout`, `batchReceiveTimeout` và `prefetchCount`.
3. Sử dụng `SimpleBatchingStrategy` và `BatchingRabbitTemplate` để gom message khi gửi theo số lượng, byte và thời gian nhàn rỗi.
4. Cấu hình `SimpleRabbitListenerContainerFactory` để consumer nhận `List<Message>` theo số lượng và thời gian chờ.
5. Đặt thêm giới hạn byte tại tầng xử lý nghiệp vụ, hiểu rõ giới hạn này **không** ngăn một message quá lớn đến broker/consumer.
6. Đánh giá hiệu năng, memory, ack, retry, DLQ và xây kịch bản thử nghiệm cho từng điều kiện xả lô.

## 2. Hai cách gom lô có ý nghĩa khác nhau

Thuật ngữ “batch” dễ gây nhầm lẫn vì một ứng dụng Spring AMQP có thể tạo batch tại **hai vị trí**:

| Đặc điểm | Gom lô tại producer | Gom lô tại consumer |
| --- | --- | --- |
| Thành phần tiêu biểu | `BatchingRabbitTemplate` + `SimpleBatchingStrategy` | `SimpleRabbitListenerContainerFactory` + `@RabbitListener` |
| Nguồn dữ liệu | Nhiều message riêng lẻ từ ứng dụng gửi | Nhiều delivery từ RabbitMQ |
| Điều gì được gộp? | Nhiều message logic thành **một message AMQP vật lý** | Nhiều message nhận từ broker thành **một lần gọi listener** |
| Giới hạn số lượng | `batchSize` của batching strategy | `batchSize` của listener container |
| Giới hạn kích thước | `bufferLimit` của strategy | Không có ngưỡng tổng byte tương đương trong cấu hình consumer batching cơ bản |
| Điều kiện thời gian | `timeout` để xả lô chưa đầy khi không có hoạt động thêm message | `receiveTimeout` khi chờ thêm message; `batchReceiveTimeout` để giới hạn thời gian gom |
| Ranh giới ACK / DLX | Broker nhìn thấy message vật lý đã gộp | Broker vẫn có thể nhìn thấy các delivery riêng lẻ nếu producer không gộp |
| Rủi ro chính | Dữ liệu nằm trong bộ nhớ producer trước khi publish; retry cả batch vật lý | Tăng bộ nhớ/độ trễ và lỗi một item có thể ảnh hưởng lần xử lý cả batch |

**Không đánh đồng hai kiểu batch.** Ví dụ một producer đóng gói 100 bản ghi vào một message AMQP, còn consumer đặt `batchSize=100` để gom 100 message AMQP. Khi hai cơ chế kết hợp, listener có thể thấy **nhiều hơn 100 bản ghi logic**. `batchSize` phía consumer là số message **vật lý** nhận từ broker, không bảo đảm số phần tử sau khi tách producer batch.

~~~mermaid
flowchart LR
    subgraph P["Producer batching"]
        P1["Event 1"]
        P2["Event 2"]
        P3["Event 3"]
        BP["BatchingRabbitTemplate"]
        P1 --> BP
        P2 --> BP
        P3 --> BP
    end
    BP -->|"Một message AMQP chứa nhiều event"| Q1["RabbitMQ queue"]
    Q1 --> DB["De-batching"]
    DB --> C1["Listener nhận danh sách event"]

    subgraph C["Consumer batching (đường đi khác)"]
        M1["Message AMQP 1"] --> Q2["RabbitMQ queue"]
        M2["Message AMQP 2"] --> Q2
        M3["Message AMQP 3"] --> Q2
        Q2 --> BC["Container gom delivery"]
        BC --> C2["Listener nhận danh sách message"]
    end
~~~

Nếu mục tiêu là giảm số lần **publish** qua mạng, hãy cân nhắc producer batching. Nếu muốn xử lý **nhiều bản ghi một lần** trong database hoặc API phía consumer, hãy cân nhắc consumer batching. Có thể kết hợp, nhưng phải tính riêng số message vật lý, số bản ghi logic và tổng byte.

## 3. Ba giới hạn: số lượng N, kích thước B, thời gian T

Giả sử ta chọn các mục tiêu ban đầu:

- `N = 100` message/lô.
- `B = 256 KiB` dữ liệu đóng gói/lô.
- `T = 2.000 ms` chờ lô chưa đầy theo ngữ nghĩa timeout của cơ chế đang dùng.

Về mặt thiết kế, một bộ gom lô nên xả dữ liệu khi đạt **một trong các điều kiện kích hoạt**:

~~~text
Đủ N message
    HOẶC chạm ngưỡng B byte
    HOẶC thỏa điều kiện timeout T
             ↓
       Đưa lô đi xử lý
~~~

Đây là tư duy chung; không nên suy diễn rằng **mọi** API Spring AMQP đều tự cung cấp đủ ba giới hạn giống nhau. `SimpleBatchingStrategy` phía producer có cả ba tham số, trong khi consumer batching tiêu chuẩn tập trung vào count và wait time. Muốn giới hạn tổng byte tại tầng xử lý consumer, ta phải bổ sung logic ứng dụng hoặc giới hạn từ trước.

### 3.1. Số lượng: giới hạn công việc trong một lô

- **N quá nhỏ**: ít tiết kiệm round trip, transaction và chi phí cố định.
- **N quá lớn**: tăng thời gian xử lý mỗi batch, lượng dữ liệu chưa ACK và độ lớn vùng lỗi khi phải retry.
- **N là ngưỡng, không phải mục tiêu phải đợi đủ bằng mọi giá**: ở tải thấp, batch chưa đầy vẫn nên được xử lý khi điều kiện timeout thỏa mãn.

Ví dụ hệ thống nhận trung bình `400 message/giây` và đặt `N=100`. Nếu các message đến đều, thời gian gom đủ 100 message vào khoảng `100 / 400 = 0,25 giây`. Nhưng lưu lượng thực tế có thể theo burst, nên công thức chỉ giúp chọn giá trị ban đầu.

### 3.2. Kích thước: giới hạn byte, không chỉ số bản ghi

100 message, mỗi message 1 KiB, khác hẳn 100 message, mỗi message 100 KiB. Một mình `batchSize` không bảo vệ bộ nhớ nếu message rất không đồng đều.

Với `SimpleBatchingStrategy`, `bufferLimit` áp dụng cho **message batch đã đóng gói** (bao gồm phần overhead định dạng gom lô), không phải là tổng heap của ứng dụng. Strategy đặt phần độ dài 4 byte trước mỗi body logic. Vì vậy có thể ước lượng:

`kích thước đóng gói ≈ tổng độ dài body + 4 × số message`

Ước lượng này không gồm tất cả overhead AMQP/network, header hoặc đối tượng Java trong heap. Khi tính dung lượng, nên để khoảng dự phòng và kiểm soát **kích thước từng message** trước khi đưa vào batch. Một item quá lớn không thể được giải quyết chỉ bằng cách hạ ngưỡng flush của batch.

### 3.3. Thời gian: cần biết timeout bắt đầu và kết thúc khi nào

**Không phải timeout nào cũng là thời hạn tối đa tính từ message đầu tiên.**

- **Producer `SimpleBatchingStrategy.timeout`**: mục tiêu là xả batch còn thiếu khi **không có hoạt động thêm message** trong khoảng thời gian quy định. Nếu liên tục có message mới, timer kiểu nhàn rỗi không nhất thiết tạo một hạn chót tuyệt đối cho message đầu tiên; batch còn có điều kiện count/bytes.
- **Consumer `receiveTimeout`**: thời gian chờ một lần nhận message tiếp theo. Khi đang gom lô mà không có message mới trong khoảng này, container có thể giao **lô một phần** cho listener.
- **Consumer `batchReceiveTimeout`**: giới hạn thời gian dành cho việc gom batch, giúp tránh chờ kéo dài khi các message vẫn đến nhỏ giọt. API này có trong Spring AMQP từ **3.1.2**.

Các timeout là công cụ điều tiết độ trễ, không phải deadline thời gian thực tuyệt đối: lịch thread, độ trễ scheduler, broker/network và xử lý ứng dụng còn ảnh hưởng thời điểm quan sát được.

### 3.4. Ví dụ với các tình huống thực tế

| Tình huống | Điều kiện nên xả lô | Ý nghĩa |
| --- | --- | --- |
| 100 message nhỏ đến rất nhanh | Chạm `N` | Ưu tiên thông lượng |
| 10 message lớn gần chạm 256 KiB | Chạm `B` trước `N` | Bảo vệ kích thước publish |
| Chỉ có 3 message rồi im lặng | Hết timeout phù hợp | Không để message chờ vô hạn |
| 30 message đến cách nhau đều, chậm | Tùy ngữ nghĩa timeout: producer idle timeout có thể được làm mới; consumer batch receive timeout giới hạn thời gian gom | Không gọi chung mọi `timeout` là “max latency” |
| Một message đơn lẻ lớn hơn B | Validate hoặc xử lý riêng theo chính sách | Flush batch không làm message đơn lẻ nhỏ đi |

## 4. Producer batching: `BatchingRabbitTemplate` và ba giới hạn

Spring AMQP cung cấp `SimpleBatchingStrategy(batchSize, bufferLimit, timeout)` để gộp nhiều message logic rồi publish qua `BatchingRabbitTemplate`. Khi producer batching, broker nhận **một message AMQP vật lý** chứa nhiều phần tử, với metadata định dạng batch để listener Spring AMQP tách ra.

Giả sử chúng ta gửi event cập nhật đơn hàng đến exchange `orders.events.exchange` với routing key `orders.import`. Những đoạn mã dưới đây là ví dụ minh họa cho Spring Boot có `spring-boot-starter-amqp`. Cần kiểm tra phiên bản Spring AMQP thực tế để chọn API tương ứng.

### 4.1. Khai báo topology RabbitMQ

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BatchTopology {

    public static final String EXCHANGE = "orders.events.exchange";
    public static final String ROUTING_KEY = "orders.import";
    public static final String QUEUE = "orders.import.queue";

    public static final String DLX = "orders.events.dlx";
    public static final String DEAD_KEY = "orders.import.failed";
    public static final String DLQ = "orders.import.dlq";

    @Bean
    DirectExchange ordersEventsExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue ordersImportQueue() {
        return QueueBuilder.durable(QUEUE)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey(DEAD_KEY)
                .build();
    }

    @Bean
    Binding ordersImportBinding() {
        return BindingBuilder.bind(ordersImportQueue())
                .to(ordersEventsExchange())
                .with(ROUTING_KEY);
    }

    @Bean
    DirectExchange ordersEventsDlx() {
        return new DirectExchange(DLX, true, false);
    }

    @Bean
    Queue ordersImportDlq() {
        // Điểm kết thúc: không khai báo DLX quay lại queue làm việc.
        return QueueBuilder.durable(DLQ).build();
    }

    @Bean
    Binding ordersImportDeadBinding() {
        return BindingBuilder.bind(ordersImportDlq())
                .to(ordersEventsDlx())
                .with(DEAD_KEY);
    }
}
~~~

Topology này dùng để minh họa cả hai phương án gom lô. Khi thử nghiệm, nên chọn **một kiểu producer và một kiểu consumer phù hợp** ở mỗi kịch bản, tránh vô tình kết hợp hai tầng batching mà không tính số phần tử cuối cùng.

### 4.2. Cấu hình số lượng, byte và timeout tại producer

~~~java
import org.springframework.amqp.rabbit.batch.SimpleBatchingStrategy;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.BatchingRabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration
public class ProducerBatchConfiguration {

    @Bean
    ThreadPoolTaskScheduler batchTaskScheduler() {
        var scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("amqp-batch-");
        return scheduler;
    }

    @Bean
    BatchingRabbitTemplate batchingRabbitTemplate(
            ConnectionFactory connectionFactory,
            ThreadPoolTaskScheduler batchTaskScheduler) {

        int maxMessages = 100;
        int maxBufferBytes = 256 * 1024; // 256 KiB
        long idleTimeoutMs = 2_000L;

        var batchingStrategy = new SimpleBatchingStrategy(
                maxMessages, maxBufferBytes, idleTimeoutMs);

        return new BatchingRabbitTemplate(
                connectionFactory, batchingStrategy, batchTaskScheduler);
    }
}
~~~

Ý nghĩa ba tham số:

| Tham số | Giá trị ví dụ | Điều cần nhớ |
| --- | --- | --- |
| `batchSize` | 100 | Khi đủ số message, batch được phát hành |
| `bufferLimit` | 256 KiB | Khi thêm message làm vượt ngân sách byte, có thể xả một batch chưa đủ count; cần kiểm tra item quá lớn riêng |
| `timeout` | 2 giây | Xả batch chưa đầy sau khoảng nhàn rỗi tương ứng; cần scheduler hoạt động |

`SimpleBatchingStrategy` mặc định chỉ hỗ trợ gom các message gửi cùng **exchange/routing key** trong một batch. Không dùng một strategy để coi các destination khác nhau như những record tùy ý trong cùng một batch. Các header/properties của message vật lý được lấy từ message đầu tiên; nếu từng event cần header riêng (ví dụ correlation ID, tenant ID, TTL), đừng giả định mọi header trên từng phần tử sẽ được giữ độc lập sau khi gộp.

### 4.3. Publish message với `send`

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.BatchingRabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderBatchPublisher {

    private static final int MAX_EVENT_BODY_BYTES = 64 * 1024;

    private final BatchingRabbitTemplate template;

    public OrderBatchPublisher(BatchingRabbitTemplate template) {
        this.template = template;
    }

    public void publishJson(String jsonEvent) {
        byte[] body = jsonEvent.getBytes(StandardCharsets.UTF_8);

        if (body.length == 0 || body.length > MAX_EVENT_BODY_BYTES) {
            throw new IllegalArgumentException(
                    "Event rỗng hoặc vượt 64 KiB");
        }

        Message message = MessageBuilder.withBody(body)
                .setContentType(MessageProperties.CONTENT_TYPE_JSON)
                .build();

        template.send(
                BatchTopology.EXCHANGE,
                BatchTopology.ROUTING_KEY,
                message);
    }
}
~~~

Ở ví dụ này, `send(exchange, routingKey, message)` là lời gọi phù hợp để batching strategy gom dữ liệu. **Cẩn thận với overload có `CorrelationData`**: với `BatchingRabbitTemplate`, lời gọi `send(exchange, routingKey, message, correlationData)` không đi theo cùng đường gom lô; không mặc định rằng mọi overload của `RabbitTemplate` đều được batching.

### 4.4. Điều gì xảy ra trong bộ gom producer?

Giả sử các event có kích thước body:

~~~text
event A: 90 KiB
event B: 80 KiB
event C: 100 KiB
event D:  2 KiB
...
~~~

Khi gom A và B, tổng body khoảng 170 KiB. Nếu thêm C khiến kích thước đóng gói vượt 256 KiB, strategy có thể xả batch A+B trước, rồi bắt đầu batch kế tiếp với C. Không cần chờ đạt 100 message.

Khi chỉ nhận được 5 event rồi không có event mới, timeout sẽ giúp xả lô còn thiếu. Nếu ứng dụng bị dừng đột ngột **trước khi publish**, các message vẫn nằm trong bộ nhớ của producer có thể bị mất. `BatchingRabbitTemplate.flush()` có thể chủ động xả batch chưa đủ khi kết thúc tác vụ hoặc trong quá trình shutdown có kiểm soát:

~~~java
batchingRabbitTemplate.flush();
~~~

Tuy nhiên, `flush()` **không tự bảo đảm** broker đã lưu dữ liệu bền vững. Khi yêu cầu xác nhận xuất bản, cần thiết kế và kiểm chứng publisher confirms/returns ở mức message vật lý và kế hoạch phục hồi dữ liệu. Không suy luận thành công của từng event chỉ từ việc gọi `send()` hoặc `flush()`.

### 4.5. Tách message producer batch ở consumer

Spring AMQP dùng header `springBatchFormat=lengthHeader4` để nhận biết cấu trúc batch từ `SimpleBatchingStrategy`. Listener container có thể tách các phần tử, hoặc đưa chúng vào `List` cho batch listener.

Nếu chỉ cần nhận đúng các **batch do producer tạo** mà không gom thêm nhiều AMQP delivery tại consumer, có thể dùng một factory riêng:

~~~java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ProducerBatchListenerConfiguration {

    @Bean
    SimpleRabbitListenerContainerFactory producerBatchListenerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setBatchListener(true);

        // Không bật consumerBatchEnabled tại factory này:
        // listener nhận batch do producer gửi, không gom thêm
        // nhiều delivery từ RabbitMQ thành một batch lớn.
        return factory;
    }
}
~~~

Listener sử dụng factory này có thể nhận `List<org.springframework.amqp.core.Message>`. Lưu ý rằng producer batch vẫn là **một message AMQP vật lý**: broker ACK/requeue/DLX theo message vật lý đó; một phần tử lỗi có thể khiến toàn batch bị reject và được giao lại.

## 5. Consumer batching: giới hạn số lượng và thời gian chờ nhận

Trong phương án này, producer thông thường dùng `RabbitTemplate` gửi từng message riêng lẻ. Container của Spring AMQP gom các delivery vào `List` rồi gọi listener một lần.

Để bật **consumer-created batching** với `SimpleRabbitListenerContainerFactory`, cần:

- `setConsumerBatchEnabled(true)`: container tạo batch từ các delivery riêng lẻ.
- `setBatchListener(true)`: listener được gọi với danh sách; từ Spring AMQP 3.0, bật consumer batching đã tự bật batch listener nhưng khai báo tường minh vẫn rõ ràng.
- `setBatchSize(N)`: mục tiêu số **message vật lý** mỗi lần giao batch cho listener.
- `setReceiveTimeout(ms)` và, ở phiên bản hỗ trợ, `setBatchReceiveTimeout(ms)`: chặn thời gian chờ batch.
- `setPrefetchCount(...)`: kiểm soát số message broker có thể giao mà chưa được ACK.

### 5.1. Cấu hình một consumer batch

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ConsumerBatchConfiguration {

    @Bean
    SimpleRabbitListenerContainerFactory consumerBatchFactory(
            ConnectionFactory connectionFactory) {

        var factory = new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);

        factory.setBatchListener(true);
        factory.setConsumerBatchEnabled(true);

        factory.setBatchSize(50);
        factory.setReceiveTimeout(300L);
        factory.setBatchReceiveTimeout(1_500L); // Spring AMQP >= 3.1.2
        factory.setPrefetchCount(100);

        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setDefaultRequeueRejected(false); // Cần cấu hình DLX/DLQ
        return factory;
    }
}
~~~

Cấu hình trên có nghĩa:

1. Nếu đủ khoảng 50 delivery vật lý, container có thể chuyển batch tới listener.
2. Nếu không có message mới trong một lượt chờ `receiveTimeout=300 ms`, batch chưa đầy có thể được giao sớm.
3. Nếu việc gom kéo dài, `batchReceiveTimeout=1.500 ms` giới hạn khoảng thời gian gom; giá trị này giúp tránh trường hợp cứ có message nhỏ giọt nên mãi không xảy ra “nhàn rỗi”.
4. `prefetchCount=100` cho phép broker giao trước nhiều message chưa ACK; đây **không phải** ngưỡng byte.
5. Với `AcknowledgeMode.AUTO`, container quản lý ACK/reject theo kết quả xử lý; exception không phải là ACK thành công.

**Chú ý về version:** `setBatchReceiveTimeout(Long)` xuất hiện từ Spring AMQP **3.1.2**. Nếu đang dùng bản cũ hơn, không sao chép nguyên đoạn cấu hình này; hãy kiểm tra API của phiên bản triển khai. Trường hợp không có tùy chọn đó, `receiveTimeout` vẫn có thể kết thúc lô một phần khi không nhận được message mới, nhưng không đại diện cùng loại giới hạn thời gian gom tổng thể.

### 5.2. Listener xử lý cả batch

~~~java
import java.util.List;

import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderImportBatchListener {

    private final IdempotentBatchWriter batchWriter;

    public OrderImportBatchListener(IdempotentBatchWriter batchWriter) {
        this.batchWriter = batchWriter;
    }

    @RabbitListener(
            queues = BatchTopology.QUEUE,
            containerFactory = "consumerBatchFactory")
    public void receive(List<Message> messages) {
        batchWriter.writeAllIdempotently(messages);
    }
}
~~~

~~~java
import java.util.List;
import org.springframework.amqp.core.Message;

// Hợp đồng của tầng lưu dữ liệu. Triển khai thực tế phải có
// kiểm soát transaction và chống ghi trùng theo eventId.
public interface IdempotentBatchWriter {
    void writeAllIdempotently(List<Message> messages);
}
~~~

Trong hệ thống thực tế, `IdempotentBatchWriter` có thể gom nhiều INSERT/UPSERT, cập nhật chỉ mục tìm kiếm, hoặc gửi một API bulk. Việc listener nhận `List<Message>` giúp nhìn thấy byte[] gốc và metadata khi cần thiết. Nếu đã cấu hình converter, cũng có thể dùng `List<OrderEvent>` để code nghiệp vụ gọn hơn, nhưng khi đó cần một cách khác để biết kích thước body đã mã hóa.

**Không dùng cùng lúc** producer batching và consumer batching ở các ví dụ trên rồi cho rằng listener chỉ nhận tối đa 50 **event logic**. Nếu broker giao 50 message vật lý và mỗi message là batch có 100 event, danh sách sau khi de-batch có thể lớn hơn nhiều so với 50.

### 5.3. `batchSize` còn ảnh hưởng ACK, transaction và prefetch

Đối với `SimpleMessageListenerContainer`, `batchSize` không chỉ là con số dành cho `List`:

- Khi ở chế độ tự động ACK, nó liên quan tần suất gửi ACK.
- Khi có channel transaction, nó ảnh hưởng phạm vi/nhịp commit.
- Nếu `prefetchCount` nhỏ hơn `batchSize`, container có thể tự tăng prefetch để phù hợp batch size.

Vì vậy tăng `batchSize` không chỉ tăng số record xử lý chung mà còn có thể tăng số message đang nằm trong bộ nhớ và số message chưa được broker xác nhận. `DirectMessageListenerContainer` có mô hình cấu hình khác; đừng sao chép các setter dành cho Simple container sang Direct container mà không kiểm tra API.

## 6. Bắt buộc giới hạn theo byte ở consumer thì làm thế nào?

**`consumerBatchEnabled` không có một `bufferLimit` giống `SimpleBatchingStrategy`.** Container gom số delivery, còn byte thực tế phụ thuộc message nhận được. Có ba lớp bảo vệ khác nhau:

1. **Trước khi publish:** xác thực và giới hạn body của từng message; hạn chế payload khổng lồ, tránh nhét stack trace/file lớn vào header.
2. **Tại broker/topology:** áp dụng giới hạn message và tài nguyên phù hợp với RabbitMQ đang dùng; cấu hình queue, prefetch, memory alarm, tải đồng thời.
3. **Tại listener:** chia `List<Message>` thành các chunk nhỏ hơn theo **cả count và body bytes** trước khi gọi thao tác bulk.

Lớp thứ ba chỉ giới hạn **đơn vị xử lý bên trong ứng dụng**. Nó không thu nhỏ một message đã nhận và cũng không hoàn toàn ngăn bộ nhớ tăng khi container đã chuyển một batch lớn vào listener.

### 6.1. Hàm chia chunk theo cả count và byte

Ví dụ sau giới hạn **mỗi lần gọi bulk write** ở mức tối đa 25 message và 128 KiB tổng body:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.amqp.core.Message;

public final class BoundedBatchChunks {

    private BoundedBatchChunks() {
    }

    public static List<List<Message>> split(
            List<Message> input, int maxItems, long maxBodyBytes) {

        if (maxItems <= 0 || maxBodyBytes <= 0) {
            throw new IllegalArgumentException("Giới hạn phải > 0");
        }

        List<List<Message>> chunks = new ArrayList<>();
        List<Message> current = new ArrayList<>();
        long currentBytes = 0L;

        for (Message message : input) {
            long bodyBytes = message.getBody().length;

            if (bodyBytes > maxBodyBytes) {
                throw new IllegalArgumentException(
                        "Một message vượt ngưỡng body của chunk");
            }

            boolean exceedsCount = current.size() >= maxItems;
            boolean exceedsBytes =
                    currentBytes + bodyBytes > maxBodyBytes;

            if (!current.isEmpty() && (exceedsCount || exceedsBytes)) {
                chunks.add(List.copyOf(current));
                current.clear();
                currentBytes = 0L;
            }

            current.add(message);
            currentBytes += bodyBytes;
        }

        if (!current.isEmpty()) {
            chunks.add(List.copyOf(current));
        }

        return chunks;
    }
}
~~~

Tại listener:

~~~java
@RabbitListener(
        queues = BatchTopology.QUEUE,
        containerFactory = "consumerBatchFactory")
public void receive(List<org.springframework.amqp.core.Message> messages) {
    var chunks = BoundedBatchChunks.split(
            messages, 25, 128L * 1024);

    for (var chunk : chunks) {
        batchWriter.writeAllIdempotently(chunk);
    }
}
~~~

Đây là **mã thay thế** phần thân `receive()` ở mục 5.2, không tạo thêm một listener thứ hai cùng nhận một queue. Hàm `split()` bảo đảm mỗi **chunk xử lý** tuân theo count và body bytes, nhưng chưa tính object overhead, headers, dữ liệu sau deserialize hoặc bộ nhớ của repository. Nếu cần giới hạn chặt hơn, phải đo kích thước dữ liệu thực và áp dụng thêm bộ giới hạn trước khi nhận/publish.

### 6.2. Khi một message vượt giới hạn

Không nên âm thầm xóa hoặc cắt body. Hãy định nghĩa chính sách rõ ràng: từ chối tại API đầu vào, lưu đối tượng lớn ở object storage rồi chỉ gửi reference, hoặc đưa message lỗi vào tuyến điều tra/DLQ.

Trong ví dụ, nếu `split()` ném exception, **cả lần gọi batch listener** thất bại. Với `defaultRequeueRejected(false)` và queue đã có DLX, message thuộc batch thất bại có thể bị dead-letter theo cách container xử lý việc reject. Đừng coi việc ném exception giữa chừng là “chỉ loại đúng một item lỗi”.

### 6.3. Vì sao tính idempotent bắt buộc khi chia nhiều chunk?

Giả sử listener nhận 50 message, chia thành 2 chunk. Chunk 1 đã ghi thành công; chunk 2 lỗi database. Nếu Spring AMQP giao lại cả batch hoặc chuyển cả batch sang DLQ, lần xử lý tiếp theo có thể thấy lại dữ liệu của chunk 1.

Vì thế, bulk writer cần xử lý bản ghi trùng một cách an toàn, ví dụ unique key theo `eventId` và UPSERT có ràng buộc phù hợp. Khi side effect phải nguyên tử, cần thiết kế transaction và phạm vi ACK riêng. Chia chunk **không tự động** biến các ACK thành độc lập cho từng item.

## 7. Chọn thông số theo tải và độ trễ

Không có một bộ `N/B/T` tối ưu cho mọi hệ thống. Điểm khởi đầu phụ thuộc ít nhất vào kích thước message, tốc độ đến, độ trễ tối đa chấp nhận, số consumer, thời gian bulk write và bộ nhớ.

### 7.1. Ước lượng thời gian lấp đầy theo số lượng

Nếu tốc độ trung bình là `λ` message/giây thì:

\[
t_{\text{fill}} \approx \frac{N}{\lambda}
\]

Ví dụ:

| Lưu lượng trung bình | N | Thời gian dự kiến để nhận đủ N |
| --- | ---: | ---: |
| 500 message/giây | 100 | 0,2 giây |
| 50 message/giây | 100 | 2 giây |
| 5 message/giây | 100 | 20 giây |

Số liệu này chỉ là **ước tính khi tốc độ đến đều**. Nếu yêu cầu xử lý event trong vòng khoảng 2 giây ở tải 5 message/giây, không nên chờ đủ 100 bản ghi. Cần timeout thích hợp hoặc giảm `N`.

### 7.2. Ước lượng số lượng theo kích thước

Với body trung bình `2 KiB`, budget `256 KiB` có thể chứa khoảng 128 body trước overhead; một batch `N=100` thường được xả theo count trước. Nếu body trung bình `16 KiB`, buffer 256 KiB chỉ chứa khoảng 16 body, nên điều kiện bytes sẽ kích hoạt sớm hơn.

Nhưng sử dụng **trung bình** không đủ cho an toàn: hãy đo thêm percentile kích thước message (`p95`, `p99`) và kích thước lớn nhất được phép. Một số message lớn bất thường có thể làm lô xả rất sớm hoặc gây lỗi giới hạn broker.

### 7.3. Ước lượng bộ nhớ consumer

Một công thức gần đúng để hình dung nguy cơ là:

\[
\text{body bytes chưa ACK} \lesssim
\text{consumer concurrency} \times
\text{prefetch} \times
\text{body size tối đa}
\]

Ví dụ 4 consumer, prefetch 100, mỗi body tối đa 32 KiB cho ra khoảng `12,5 MiB` **chỉ tính body**. Thực tế cần cộng overhead Java/AMQP, bản sao, headers, danh sách, dữ liệu sau deserialize và bộ đệm của database. Đây không phải quota heap cứng, mà là cách nhận ra vì sao tăng concurrency, prefetch và kích thước message cùng lúc có thể gây memory spike.

### 7.4. Ma trận chọn trade-off

| Mục tiêu | Xu hướng cấu hình | Đánh đổi cần đo |
| --- | --- | --- |
| Giảm latency | Giảm `N`, giảm timeout | Nhiều lô nhỏ, chi phí mạng/DB tăng |
| Tăng throughput | Tăng `N` vừa phải, tăng hiệu quả bulk write | Độ trễ chờ và thời gian xử lý mỗi lô tăng |
| Giảm memory | Giảm `B` phía producer, giới hạn item, giảm prefetch | Tăng số lần publish hoặc giảm số message xử lý đồng thời |
| Hạn chế một lỗi ảnh hưởng nhiều event | Chia batch nhỏ, xử lý idempotent, phân loại lỗi | Ít tiết kiệm chi phí xử lý lô |
| Chịu burst | Prefetch và concurrency có kiểm soát, đo queue depth | Có thể tăng số message unacked và áp lực DB |

**Khởi đầu thực dụng:** chọn kích thước mỗi item và mục tiêu latency trước, sau đó tăng `N` theo benchmark thực tế. Đừng tăng tất cả tham số đến cực đại chỉ vì một lần thử throughput ngắn cho kết quả tốt.

## 8. ACK, retry, DLQ và độ tin cậy của từng loại batch

### 8.1. Producer batch: một frame vật lý, nhiều event logic

`SimpleBatchingStrategy` gói nhiều event thành một message AMQP vật lý theo định dạng riêng. Broker không thể ACK hay dead-letter từng event logic bên trong message vật lý theo cách nó xử lý các message thông thường.

Hệ quả:

- Broker xác nhận việc nhận **message vật lý** sau khi batch đã được publish; đó không phải 100 xác nhận riêng biệt cho 100 event.
- Nếu message vật lý bị reject và đưa vào DLQ, toàn bộ nội dung batch được chuyển theo cơ chế dead-letter.
- Nếu một fragment logic lỗi, việc retry có thể kéo cả fragment tốt đi cùng.
- Để replay từng event, cần tách batch ở ứng dụng, xác định event lỗi và xuất bản lại có kiểm soát.

Ngoài ra, message nằm trong buffer producer trước khi flush **chưa nằm trong RabbitMQ**. Nếu ứng dụng crash, RabbitMQ không thể cứu các event chưa được publish. Với yêu cầu không mất dữ liệu, hãy cân nhắc transactional outbox hoặc lưu bền vững trước khi đưa vào bộ gom, rồi xác nhận phát hành theo đúng đơn vị thực tế.

### 8.2. Consumer batch: nhiều delivery, một lần xử lý listener

Ở consumer batching, việc gọi listener với danh sách **không biến** các message nguồn thành một message vật lý. Tuy nhiên, với cơ chế xử lý batch, lỗi phát sinh từ một phần tử thường khiến **lần gọi listener của cả batch** bị xem là lỗi. Cách broker nhận ACK/reject/requeue cụ thể phụ thuộc container, acknowledgment mode, transaction và error handler.

Với `AcknowledgeMode.AUTO`, chỉ coi xử lý thành công khi listener hoàn tất mà không có exception. Nếu một batch có một event không hợp lệ, các cách tiếp cận có thể là:

1. Trả lỗi và đưa batch vào tuyến retry/DLQ đã thiết kế, rồi dùng công cụ điều tra để phân loại.
2. Nếu có thể xử lý độc lập từng event, ghi kết quả/idempotency riêng, lưu các item thất bại vào nơi bền vững, sau đó kết thúc batch thành công **chỉ khi** mọi item đã có kết quả xử lý hoặc lưu lỗi đáng tin cậy.
3. Với nghiệp vụ yêu cầu ACK/reject theo item, đánh giá xử lý từng message hoặc thiết kế cơ chế manual ACK có kiểm chứng thay vì giả định batch listener mặc định đáp ứng được.

Đặc biệt, `defaultRequeueRejected(false)` sẽ không an toàn nếu queue **không có DLX/DLQ** hoặc không có chính sách xử lý lỗi cuối cùng. Ví dụ topology ở mục 4 đã khai báo terminal DLQ để tránh message lỗi bị bỏ mà không có nơi điều tra.

### 8.3. Không biến batching thành request–reply đồng bộ

Batch listener thường không có quan hệ 1:1 giữa **một lần gọi listener** và **một reply** cho từng message đầu vào. Đừng mặc định một `@RabbitListener` nhận `List<...>` có thể trả về một object và RabbitMQ sẽ tự phân phối object đó thành nhiều reply tương ứng. Với request–reply cần correlation theo từng message, thiết kế riêng contract và đường trả lời.

## 9. Giám sát để biết ngưỡng có thực sự phù hợp

Đặt một bộ số cố định mà không đo lường sẽ khiến độ trễ, memory hoặc DLQ tăng dần mà khó phát hiện. Nên ghi nhận:

| Chỉ số | Vì sao quan trọng |
| --- | --- |
| `batch_items_count` theo p50/p95/p99 | Lô thường đầy theo count hay luôn xả sớm? |
| `batch_body_bytes` theo p50/p95/p99 | B có quá nhỏ, quá lớn hay xuất hiện outlier? |
| `batch_wait_ms`, `batch_processing_ms` | Phân biệt thời gian chờ gom với thời gian bulk write |
| `flush_reason=count/bytes/timeout/manual` (nếu có instrumentation tại producer) | Tìm ngưỡng nào thường xuyên kích hoạt |
| `queue_depth`, `messages_unacked`, `redelivered` | Phát hiện consumer chậm hoặc retry vòng lặp |
| `consumer_heap`, GC pause, scheduler backlog | Tìm nguy cơ memory hoặc flush trễ |
| `publish_confirm_failures`, `publisher_returns` | Tìm lỗi gửi/route message vật lý |
| `dlq_count`, tuổi message DLQ | Phát hiện poison batch và việc replay chưa xử lý |
| Số event trùng theo `eventId` | Kiểm tra idempotency khi batch bị giao lại |

Mỗi phép đo nên phân biệt **message vật lý RabbitMQ** với **event logic**. Ví dụ metric “5 message được publish” có thể chỉ là 5 batch vật lý chứa 500 event logic. Không so sánh hai loại số đếm nếu chưa quy đổi cùng đơn vị.

## 10. Kịch bản kiểm thử giới hạn số lượng, byte và thời gian

Không cần thử nghiệm tải cực lớn ngay từ đầu. Nên kiểm tra từng cơ chế xả batch trên môi trường riêng, quan sát đồng thời log và số liệu RabbitMQ.

### Kịch bản 1 — Producer xả vì đủ số lượng

Đặt `SimpleBatchingStrategy(5, 256 * 1024, 10_000)`. Publish 5 message nhỏ, cùng exchange/routing key, trong thời gian ngắn. Kỳ vọng có một batch vật lý xuất hiện mà không phải chờ 10 giây. Xác nhận ở listener số phần tử logic là 5 nếu nhận theo chế độ batch.

### Kịch bản 2 — Producer xả vì gần ngưỡng byte

Đặt `batchSize=100`, `bufferLimit=16 KiB` và gửi các message khoảng 6 KiB/body. Khi thêm message mới có nguy cơ vượt budget, batch một phần được xả dù chưa đủ 100 item. Đo kích thước payload thực, đừng giả định kích thước JSON bằng kích thước đối tượng Java.

### Kịch bản 3 — Producer xả vì timeout

Đặt `batchSize=100` và `timeout=1.000 ms`, gửi 3 message rồi dừng gửi. Kỳ vọng lô chưa đầy được phát hành sau thời gian nhàn rỗi tương ứng, với sai số do scheduling. Thử tiếp một chuỗi message nhỏ giọt có khoảng cách ngắn hơn timeout để thấy timeout kiểu nhàn rỗi khác với “hạn chót kể từ message đầu”.

### Kịch bản 4 — Consumer xả batch một phần

Dùng producer thông thường, cấu hình consumer `batchSize=10`, `receiveTimeout=300 ms`, `batchReceiveTimeout=1.500 ms`. Gửi 3 message rồi dừng. Kỳ vọng listener được gọi với một batch **ít hơn 10** thay vì chờ mãi. Sau đó thử chuỗi message đến cách nhau 100–200 ms để xem giới hạn thời gian gom tổng thể hoạt động.

### Kịch bản 5 — Giới hạn byte ở tầng bulk write

Cho listener nhận message có kích thước body khác nhau, rồi chia bằng `BoundedBatchChunks.split(batch, 25, 128 * 1024)`. Kiểm tra mọi chunk đều có số phần tử không quá 25 và tổng body không vượt 128 KiB. Gửi một message có body vượt 128 KiB để xác minh chính sách lỗi, DLQ và logging.

### Kịch bản 6 — Lỗi giữa batch và giao lại

Cho bulk writer ghi chunk đầu thành công nhưng ném exception ở chunk sau. Quan sát ACK/requeue/DLQ ở container đang dùng. Phát lại dữ liệu để xác minh unique key hoặc UPSERT ngăn side effect trùng lặp. Đây là kiểm thử bắt buộc nếu mỗi event có tác động kinh doanh.

### Kịch bản 7 — Tắt ứng dụng khi producer còn batch dở

Gửi chưa đủ count/bytes và dừng tiến trình trước khi timeout. Thử shutdown có `flush()` và tình huống crash đột ngột; phân biệt dữ liệu đã vào broker với dữ liệu chỉ còn trong heap. Nếu mất dữ liệu là không chấp nhận được, phải bổ sung cơ chế lưu bền vững chứ không dựa vào timer.

### Kịch bản 8 — Kết hợp producer batching với consumer batching

Cố ý tạo 4 message vật lý, mỗi message chứa 10 fragment; dùng container gom nhiều delivery. Đo kích thước `List` tại listener và xác nhận không thể coi `batchSize=4` là “tối đa 4 event”. Chọn một trong hai cách batching hoặc đặt thêm giới hạn xử lý trên danh sách sau khi de-batch.

## 11. Các lỗi cấu hình thường gặp

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Chỉ đặt `batchSize`, bỏ qua kích thước từng message | Một batch ít item vẫn có thể rất lớn | Giới hạn từng body, đặt `bufferLimit` khi producer batching và kiểm tra broker limits |
| Hiểu `timeout` producer là deadline tuyệt đối | Message có thể chờ lâu hơn dự kiến khi có hoạt động thêm đều đặn | Hiểu idle timeout, đo độ tuổi thực, thiết kế deadline riêng nếu có SLA chặt |
| Không cấu hình `batchReceiveTimeout` khi cần hạn chót gom phía consumer | Luồng message nhỏ giọt có thể kéo dài thời gian gom | Dùng phiên bản hỗ trợ và đặt ngưỡng phù hợp |
| Tăng `prefetchCount` quá cao | Memory/unacked tăng cùng số consumer | Ước lượng tài nguyên và benchmark |
| Dùng producer batch đồng thời với consumer batch nhưng chỉ đo `batchSize` | Số event logic tại listener lớn bất ngờ | Đo số fragment sau de-batch, tách giới hạn hai tầng |
| Xem mỗi fragment đã có ACK riêng | Retry/DLQ cả batch gây trùng | Thiết kế idempotency và biết ranh giới message vật lý |
| Gọi `flush()` rồi cho rằng đã lưu bền vững | Crash/network error vẫn có thể mất event | Dùng publisher confirms/returns và durable source/outbox khi cần |
| Không có DLQ khi reject batch | Message có thể bị loại bỏ mà không điều tra được | Cấu hình terminal DLQ và quan sát |
| Chia chunk nhưng writer không idempotent | Retry lại có thể ghi trùng chunk trước | Dùng idempotency key/unique constraint |
| Đặt toàn bộ payload/metadata vào header | Header phình và khó quan sát | Payload trong body, header chỉ chứa metadata nhỏ cần thiết |

## 12. Checklist áp dụng trong hệ thống Spring AMQP

Trước khi triển khai, hãy xác nhận:

- [ ] Xác định đang gom ở producer, consumer hay cả hai; có số đo **physical message** và **logical event**.
- [ ] Đã chọn `N` dựa trên thông lượng và kích thước lô có thể retry.
- [ ] Có giới hạn **kích thước từng message** và giới hạn tổng byte phù hợp ở tầng được chọn.
- [ ] Hiểu `timeout` producer là điều kiện nhàn rỗi; hiểu `receiveTimeout`/`batchReceiveTimeout` consumer và phiên bản Spring AMQP.
- [ ] Producer có scheduler cho flush timeout và cơ chế xử lý shutdown/crash phù hợp với yêu cầu mất dữ liệu.
- [ ] Không giả định header từng fragment được giữ độc lập trong producer batch.
- [ ] `prefetch`, concurrency, heap và số message chưa ACK đã được ước lượng và thử nghiệm.
- [ ] Bulk writer idempotent; xử lý một record lỗi không gây retry vô hạn hoặc mất toàn bộ lô mà không có dấu vết.
- [ ] DLX/DLQ, retry budget, publisher confirms/returns đã được xem xét theo ranh giới message vật lý.
- [ ] Có metric số item, byte, wait time, process time, flush reason, redelivery và tuổi DLQ.

## 13. Kết luận

Trong **SPRING_AMQP**, giới hạn lô là sự cân bằng giữa **thông lượng, độ trễ, bộ nhớ và mức độ ảnh hưởng khi lỗi**. Ở producer, `SimpleBatchingStrategy` có thể xả khi đạt số lượng, vượt ngân sách kích thước hoặc hết khoảng nhàn rỗi; cần nhớ dữ liệu trước khi publish vẫn ở trong bộ nhớ ứng dụng. Ở consumer, `SimpleRabbitListenerContainerFactory` gom các delivery theo `batchSize`, `receiveTimeout` và `batchReceiveTimeout`; giới hạn byte cho bước bulk write phải được thiết kế riêng.

Một cấu hình đáng tin cậy luôn trả lời được bốn câu hỏi: *Lô được tạo ở đâu? Khi nào nó được xả? Một lỗi ảnh hưởng bao nhiêu message? Và làm sao chứng minh không mất hoặc xử lý trùng dữ liệu?* Khi những câu hỏi đó có câu trả lời rõ ràng, batching mới thực sự giúp RabbitMQ và Spring AMQP xử lý bất đồng bộ hiệu quả mà vẫn có thể vận hành, retry và quan sát an toàn.

### Tài liệu đối chiếu

- [Spring AMQP — Sending Messages, Batching](https://docs.spring.io/spring-amqp/reference/amqp/sending-messages.html)
- [Spring AMQP — @RabbitListener with Batching](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/batch.html)
- [Spring AMQP — Message Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html)
