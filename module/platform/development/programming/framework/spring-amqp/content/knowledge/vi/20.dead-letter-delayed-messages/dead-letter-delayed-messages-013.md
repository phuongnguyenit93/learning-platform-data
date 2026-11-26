# Ngăn chu trình DLX, mất routing key và tăng kích thước header

Trong hệ thống xử lý bất đồng bộ bằng **RabbitMQ và Spring AMQP**, dead-letter exchange (DLX) giúp đưa message không thể xử lý sang tuyến khác. Tuy nhiên, cấu hình DLX sai có thể khiến message quay lại queue cũ liên tục, bị gửi tới exchange mà không có binding phù hợp hoặc mang theo lượng metadata ngày càng lớn. Cả ba lỗi đều khó nhận ra nếu chỉ quan sát việc `@RabbitListener` có ném exception hay không.

Bài học này thuộc chương **Dead-letter và trì hoãn** của **SPRING_AMQP**. Trọng tâm là thiết kế đường đi của message, kiểm soát số lần thử lại, bảo toàn thông tin cần thiết khi đổi routing key và giữ header gọn để hệ thống retry, dead-letter và giám sát hoạt động ổn định.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích khi nào RabbitMQ dead-letter một message và vì sao `basic.nack(requeue=true)` không đồng nghĩa với đi qua DLX.
- Phát hiện vòng lặp qua các queue/exchange và thiết kế điểm kết thúc cho message lỗi.
- Phân biệt **routing key dùng để vào queue ban đầu** với **dead-letter routing key**; kiểm chứng exchange, binding và route thực tế.
- Đọc header `x-death` để điều tra lịch sử dead-letter mà không nhầm nó với tổng số lần gọi consumer.
- Giới hạn retry, header và dữ liệu log; xây một cấu hình Spring AMQP có queue lỗi cuối cùng (terminal DLQ).

## 2. Cơ chế cần nắm trước khi xử lý ba lỗi

Một queue có thể khai báo `x-dead-letter-exchange` (hoặc cấu hình DLX bằng RabbitMQ policy) và tùy chọn `x-dead-letter-routing-key`. Khi message bị dead-letter, **broker** phát hành lại message tới DLX đã cấu hình. Message đi vào queue đích hay không vẫn phụ thuộc **exchange type**, **routing key** và **binding**.

Các sự kiện dead-letter thường gặp:

| Nguyên nhân | Điều kiện | Giá trị `reason` thường thấy trong `x-death` |
| --- | --- | --- |
| Consumer từ chối | `basic.reject` hoặc `basic.nack` với `requeue=false` | `rejected` |
| Message hết TTL | TTL trên message hoặc queue hết hạn | `expired` |
| Queue vượt giới hạn độ dài | Cấu hình giới hạn queue và chính sách tràn phù hợp | `maxlen` |
| Quorum queue vượt delivery limit | Message vượt giới hạn giao lại của quorum queue | `delivery_limit` |

**Phân biệt đặc biệt quan trọng:**

- `basic.nack(requeue=true)` đưa message trở lại luồng giao nhận của queue, **không kích hoạt DLX** chỉ vì consumer thất bại.
- `basic.reject(requeue=false)` hoặc `basic.nack(requeue=false)` yêu cầu broker không xếp lại message; nếu queue có DLX, message được đưa vào tuyến dead-letter.
- Với Spring AMQP, exception ở `@RabbitListener` kết thúc bằng requeue hay reject còn phụ thuộc vào cấu hình container, error handler và retry advice. Đừng xem việc ném exception là bằng chứng message đã vào DLQ.

Ví dụ: producer gửi tới `orders.exchange` với routing key `orders.created`; queue `orders.work` có DLX là `orders.dlx` và dead-letter routing key `orders.failed`. Khi listener từ chối message với `requeue=false`, broker định tuyến **lần hai** qua `orders.dlx` với key `orders.failed`.

~~~mermaid
flowchart LR
    P[Producer] -->|orders.created| EX[orders.exchange]
    EX -->|binding: orders.created| W[orders.work]
    W -->|reject, requeue=false| DX[orders.dlx]
    DX -->|binding: orders.failed| D[orders.dlq]
    D --> O[Điều tra, sửa dữ liệu, replay có kiểm soát]
~~~

Queue `orders.dlq` trong mô hình này là **điểm kết thúc**: không tự khai báo DLX quay về `orders.work` và không có consumer tự động đưa tất cả message lỗi trở lại luồng chính.

## 3. Lỗi thứ nhất: Chu trình DLX và message chạy vòng

### 3.1. Chu trình hình thành thế nào?

**Trường hợp A — DLX trỏ ngược queue gốc:**

1. Message ở `orders.work` bị reject với `requeue=false`.
2. DLX dùng routing key có thể đưa message trở lại `orders.work`.
3. Consumer nhận lại, tiếp tục reject; các bước lặp lại.

**Trường hợp B — retry queue có TTL:**

~~~text
orders.work
    -- dead-letter vì bị reject -->
orders.retry.10s
    -- dead-letter vì hết TTL -->
orders.work
    -- lỗi nữa --> ...
~~~

Đây có thể là một chiến lược delay/retry **có chủ ý**, nhưng nó trở thành vòng lặp vô hạn nếu không có giới hạn số lần thử và điều kiện chuyển sang DLQ cuối cùng.

**Trường hợp C — DLX là default exchange (`""`):** Exchange mặc định định tuyến trực tiếp theo **tên queue**. Nếu dead-letter routing key trùng với tên queue gốc, message có thể trở lại đúng queue đó. Nếu routing key không trùng tên queue nào, message có thể không tới đâu.

RabbitMQ có cơ chế phát hiện một số **dead-letter cycle** và bỏ message khi vòng đi qua không có lần **reject** nào. Cơ chế này không đảm bảo dập mọi vòng lặp: một vòng có các lần `reject(requeue=false)` vẫn có thể tiếp tục. Vì vậy, **không sử dụng tính năng tự phát hiện cycle của broker làm giới hạn retry**.

### 3.2. Quy tắc thiết kế để chặn chu trình

- **Vẽ graph định tuyến:** mỗi queue là một nút; mỗi quan hệ DLX/TTL/replay là một cạnh. Đánh dấu các cạnh có thể quay về queue cũ và chỉ cho phép quay về khi có **retry budget hữu hạn**.
- **Đặt terminal DLQ:** queue cuối cùng không có DLX tự động quay về nguồn. Việc replay từ DLQ là một thao tác riêng, có kiểm tra dữ liệu và giới hạn tốc độ.
- **Giới hạn lần thử ở tầng ứng dụng:** chọn tối đa N lần thực thi; hết N lần phải reject sang DLQ hoặc chuyển sang một luồng lỗi cuối cùng có xác nhận.
- **Tách lỗi tạm thời và lỗi không thể phục hồi:** timeout từ dịch vụ phụ thuộc có thể retry; dữ liệu sai schema hoặc thiếu trường bắt buộc cần đưa vào DLQ sớm.
- **Có backoff:** retry liên tiếp trong vài mili giây vừa tạo áp lực lên broker vừa không giúp dịch vụ phụ thuộc phục hồi.
- **Không nhầm requeue với retry có kiểm soát:** requeue trực tiếp có thể gây vòng giao lại rất nhanh, không có delay hay đếm lần thử ứng dụng.

Nếu dùng nhiều retry queue theo TTL, bản thân việc đặt TTL **không tự tạo giới hạn retry**. Cần logic chuyển trạng thái rõ ràng (ví dụ retry theo nấc hữu hạn và DLQ cuối) hoặc sử dụng retry hữu hạn trong listener như phần ví dụ dưới đây.

## 4. Lỗi thứ hai: Mất hoặc sai routing key khi dead-letter

RabbitMQ dùng routing key **tại thời điểm dead-letter** để định tuyến qua DLX:

- Khi queue **không cấu hình** `x-dead-letter-routing-key`, broker thường dùng routing key gốc của message (và có những chi tiết bổ sung với các routing key từ `CC`).
- Khi queue **cấu hình** `x-dead-letter-routing-key`, broker dùng key được chỉ định để dead-letter. Đây là routing key mới cho chặng đến DLX, không nhất thiết trùng key producer đã gửi.
- Với **direct exchange**, binding key phải khớp chính xác. Với **topic exchange**, binding pattern phải khớp routing key được gửi tới DLX. Với default exchange, key phải trùng tên queue đích.

Ví dụ binding ở DLX là `orders.failed`:

| Cấu hình của `orders.work` | Routing key ở chặng DLX | Kết quả |
| --- | --- | --- |
| `x-dead-letter-exchange=orders.dlx`; `x-dead-letter-routing-key=orders.failed` | `orders.failed` | Đến `orders.dlq` nếu binding khớp |
| Có DLX nhưng **không** có dead-letter routing key | Thường giữ `orders.created` | Không vào `orders.dlq` nếu chỉ bind `orders.failed` |
| DLX là default exchange `""` và key là `orders.dlq` | `orders.dlq` | Đến queue mang tên `orders.dlq` nếu queue tồn tại |
| DLX là default exchange `""` và key là `orders.work` | `orders.work` | Có nguy cơ quay lại queue gốc |

### 4.1. Checklist lần theo tuyến

Khi không thấy message trong DLQ, hãy kiểm tra **từ nguồn đến đích**, theo thứ tự:

1. Queue nguồn có đúng DLX và dead-letter routing key đang áp dụng không? Cấu hình bằng **policy** và cấu hình bằng queue argument có thể khác nhau; argument khai báo trực tiếp có thể được ưu tiên.
2. Listener thực sự reject với `requeue=false`, hay đang requeue khiến message chưa từng đi vào DLX?
3. DLX đã tồn tại, đúng tên, đúng virtual host, đúng loại exchange và có quyền cần thiết không?
4. Binding từ DLX sang DLQ dùng **routing key sau khi dead-letter**, thay vì ngầm giả định key của lần publish đầu?
5. Queue đích có tồn tại và sẵn sàng nhận message không? Có thể thử một message kiểm tra riêng với cùng exchange/key để xác minh đường routing.
6. Nếu **ứng dụng tự republish** để retry, code đã gửi vào đúng exchange/key chưa? `RabbitTemplate.convertAndSend` không suy ra key từ tên queue.

Đừng suy luận message chắc chắn đã vào DLQ chỉ vì source queue giảm `messages_ready`. Dead-lettering là hoạt động publish nội bộ của broker; một tuyến DLX không thể route hoặc đích không sẵn sàng có thể khiến message biến mất trong cấu hình thông thường. Nếu cần đảm bảo cao hơn, phải đánh giá cơ chế dead-letter **at-least-once** của quorum queue theo phiên bản RabbitMQ và policy triển khai, cùng với giám sát và xử lý trùng lặp.

## 5. Lỗi thứ ba: Header lớn dần khi retry hoặc republish

RabbitMQ đính kèm lịch sử dead-letter trong header `x-death`. Mỗi mục có thể ghi nhận queue, nguyên nhân, số lần, exchange, routing key và thời điểm dead-letter; broker cũng có thể cung cấp các trường mô tả lần dead-letter đầu/cuối tùy phiên bản.

Ví dụ **minh họa logic** (không phải định dạng byte AMQP thực tế):

~~~json
{
  "x-death": [
    {
      "queue": "orders.work",
      "reason": "rejected",
      "count": 3,
      "exchange": "orders.exchange",
      "routing-keys": ["orders.created"]
    },
    {
      "queue": "orders.retry.10s",
      "reason": "expired",
      "count": 2,
      "exchange": "orders.retry.exchange",
      "routing-keys": ["orders.wait"]
    }
  ]
}
~~~

**Chi tiết dễ bị hiểu sai:** RabbitMQ **gộp/đếm** các sự kiện `x-death` có cùng cặp **queue + reason**. Một vòng lặp lặp lại đúng hai queue/reason không nhất thiết sinh thêm một phần tử `x-death` ở mỗi vòng. Tuy vậy, header vẫn có thể lớn khi message đi qua nhiều queue hoặc lý do khác nhau, và đặc biệt khi **ứng dụng liên tục thêm metadata mới** vào mỗi lần republish.

Các kiểu phát triển header nguy hiểm gồm:

- Ghi thêm toàn bộ stack trace vào `x-last-error` hoặc một danh sách `x-error-history` ở mỗi lần thất bại.
- Sao chép toàn bộ headers cũ rồi thêm nhiều bản `x-retry-*`, payload, HTTP response hoặc thông tin nhạy cảm.
- Dùng routing flow thay đổi queue động, khiến lịch sử `x-death` có nhiều cặp queue/reason.
- Đưa nội dung lớn vào headers thay vì body hoặc một kho lưu trữ bên ngoài.

Header lớn làm tăng dữ liệu truyền và bộ nhớ, khiến log/trace khó quan sát và có thể gặp các giới hạn kích thước hoặc tài nguyên của broker/client. Không có con số giới hạn chung đúng cho mọi phiên bản RabbitMQ và cấu hình hệ thống.

### 5.1. Chọn metadata cần giữ

| Nên giữ dưới dạng nhỏ, cố định | Nên tránh trong header |
| --- | --- |
| `messageId`, `correlationId`, `traceId` | Stack trace nhiều trang |
| `x-attempt` là một số nguyên được cập nhật, có chặn ngưỡng | Mảng lịch sử lỗi nối thêm vô hạn |
| `errorCode` ngắn, có danh mục | Payload sao chép nhiều lần |
| Khóa tham chiếu tới bản ghi lỗi/log | Thông tin cá nhân, token, HTTP response thô |

Giữ nguyên các header broker quản lý khi **broker tự dead-letter**. Nếu **ứng dụng republish** bằng một message mới, hãy tạo metadata theo whitelist và chỉ mang sang những trường thực sự cần thiết; đừng giả mạo hoặc tự điều chỉnh `x-death`. Muốn giữ chi tiết chẩn đoán, ghi vào log hoặc kho lưu trữ có giới hạn dung lượng/thời gian, gắn với `messageId`.

### 5.2. Đọc `x-death` để chẩn đoán, không đánh đồng với attempt

Ví dụ cách đọc an toàn về mặt kiểu dữ liệu khi nhận Spring AMQP `Message`:

~~~java
Object raw = message.getMessageProperties()
        .getHeaders()
        .get("x-death");

if (raw instanceof java.util.List<?> deaths) {
    for (Object entry : deaths) {
        if (entry instanceof java.util.Map<?, ?> death) {
            Object queue = death.get("queue");
            Object reason = death.get("reason");
            Object count = death.get("count"); // thường là Number
            log.info("deadLetter queue={} reason={} count={}",
                    queue, reason, count);
        }
    }
}
~~~

`x-death.count` là số lần dead-letter của một nhóm lịch sử do **broker** ghi nhận; nó **không** phản ánh mọi lần ứng dụng xử lý hoặc retry nội bộ trong cùng một lần giao nhận. Một `RetryInterceptor` có thể thử bốn lần trong listener nhưng chỉ tạo **một** sự kiện dead-letter khi đã hết retry. Không dùng `x-death` như bộ đếm duy nhất cho tất cả cơ chế retry, và không giả định thứ tự/mô hình lịch sử không bao giờ thay đổi giữa các phiên bản broker.

## 6. Ví dụ Spring AMQP: retry hữu hạn và terminal DLQ

Ví dụ sau dùng Spring Boot có dependency `spring-boot-starter-amqp`. Message mới được gửi vào `orders.work`, listener thử xử lý tối đa **4 lần** trong cùng quá trình retry, rồi từ chối message với `requeue=false` để broker dead-letter sang `orders.dlq`. Không cấu hình DLX cho `orders.dlq` nên tuyến lỗi có điểm dừng rõ ràng.

### 6.1. Khai báo exchange, queue và binding

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderMessagingTopology {

    public static final String WORK_EXCHANGE = "orders.exchange";
    public static final String WORK_QUEUE = "orders.work";
    public static final String WORK_KEY = "orders.created";

    public static final String DLX_EXCHANGE = "orders.dlx";
    public static final String DLQ = "orders.dlq";
    public static final String DEAD_KEY = "orders.failed";

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange(WORK_EXCHANGE, true, false);
    }

    @Bean
    DirectExchange ordersDeadLetterExchange() {
        return new DirectExchange(DLX_EXCHANGE, true, false);
    }

    @Bean
    Queue ordersWorkQueue() {
        return QueueBuilder.durable(WORK_QUEUE)
                .deadLetterExchange(DLX_EXCHANGE)
                .deadLetterRoutingKey(DEAD_KEY)
                .build();
    }

    @Bean
    Queue ordersDeadLetterQueue() {
        // Không cấu hình DLX cho terminal DLQ.
        return QueueBuilder.durable(DLQ).build();
    }

    @Bean
    Binding ordersWorkBinding() {
        return BindingBuilder.bind(ordersWorkQueue())
                .to(ordersExchange())
                .with(WORK_KEY);
    }

    @Bean
    Binding ordersDeadBinding() {
        return BindingBuilder.bind(ordersDeadLetterQueue())
                .to(ordersDeadLetterExchange())
                .with(DEAD_KEY);
    }
}
~~~

Ở đây, hai khóa `orders.created` và `orders.failed` **cố ý khác nhau**. Queue `orders.work` thuộc exchange nghiệp vụ; queue `orders.dlq` thuộc DLX và chỉ nhận các message có dead-letter routing key khớp.

### 6.2. Giới hạn retry trong listener container

~~~java
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderListenerRetryConfig {

    @Bean
    SimpleRabbitListenerContainerFactory rabbitListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setDefaultRequeueRejected(false);
        factory.setAdviceChain(
                RetryInterceptorBuilder.stateless()
                        .maxAttempts(4)
                        .backOffOptions(1_000, 2.0, 5_000)
                        .recoverer(new RejectAndDontRequeueRecoverer())
                        .build());
        return factory;
    }
}
~~~

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    @RabbitListener(queues = OrderMessagingTopology.WORK_QUEUE)
    public void process(String event) {
        if (event == null || event.isBlank() || event.contains("INVALID")) {
            throw new IllegalArgumentException("Invalid order event");
        }

        // Ví dụ: kiểm tra dữ liệu, ghi kết quả idempotent,
        // hoặc gọi dịch vụ xử lý đơn hàng.
    }
}
~~~

Cấu hình `maxAttempts(4)` **bao gồm lần chạy đầu tiên**: tối đa bốn lần gọi xử lý trong chu kỳ retry này. Khi các lần thử đều thất bại, `RejectAndDontRequeueRecoverer` yêu cầu reject mà không requeue; DLX trên `orders.work` đưa message sang `orders.dlq`.

Ví dụ này phù hợp để minh họa giới hạn retry tại listener. Trong hệ thống thực tế, cần phân loại exception để lỗi dữ liệu không bị thử lại vô ích; tránh retry trong listener quá lâu với tác vụ mất nhiều thời gian; đặt timeouts khi gọi hệ thống phụ thuộc; và làm xử lý **idempotent** vì message có thể được giao lại sau lỗi kết nối hoặc khởi động lại. Retry nội bộ không phải bộ đếm bền vững xuyên qua mọi lần consumer khởi động.

**Lưu ý về queue đã tồn tại:** thay đổi queue argument như `x-dead-letter-exchange` trực tiếp trong code có thể xung đột với queue đã khai báo trên broker. Trong môi trường vận hành, nên quản lý topology/policy nhất quán và lên kế hoạch thay đổi queue thay vì mặc định redeclare sẽ sửa được cấu hình cũ.

### 6.3. Khi nào cần delay queue?

Nếu cần retry sau vài chục giây hoặc vài phút mà không giữ consumer đang chờ, có thể dùng queue trung gian có TTL:

~~~text
orders.work -- reject, requeue=false --> orders.retry.30s
orders.retry.30s -- expired --> orders.work
~~~

Nhưng topology đó **chưa an toàn nếu đứng một mình**: queue chính vẫn có thể bị reject lặp mãi. Với flow này, ứng dụng phải theo dõi retry budget theo cách rõ ràng và **đưa message sang terminal DLQ khi hết lượt**; queue delay chỉ chịu trách nhiệm về thời gian chờ. Việc chọn tuyến retry hay DLQ cần logic xuất bản/định tuyến có xác nhận tương ứng, bởi một queue chỉ có một bộ cấu hình DLX áp dụng cho các lần dead-letter của nó.

Khi tự publish message sang queue retry hoặc DLQ trong ứng dụng, nên bật **publisher confirms**, xử lý **publisher returns** cho message không route được, và chỉ ack message nguồn sau khi đã có kết quả publish phù hợp. Nếu ack trước rồi publish thất bại, có nguy cơ mất message; nếu publish thành công nhưng ack thất bại, có thể xuất hiện bản sao nên consumer cần idempotency.

## 7. Quan sát và xử lý sự cố theo triệu chứng

| Triệu chứng | Kiểm tra đầu tiên | Hành động sửa |
| --- | --- | --- |
| Consumer nhận lại cùng message liên tục | `requeue`, retry policy, DLX quay về queue nguồn | Chặn requeue vô hạn, thêm retry budget và terminal DLQ |
| Queue nguồn giảm nhưng DLQ không tăng | DLX, binding, dead-letter routing key, queue đích | Thử gửi bằng đúng exchange/key; sửa binding hoặc policy |
| `x-death.count` tăng, message vẫn quay lại | Đường đi giữa work/retry queues và quy tắc dừng | Đặt ngưỡng retry và tuyến lỗi cuối |
| Header hoặc log lớn bất thường | Custom error history, copy nguyên headers khi republish | Chỉ giữ metadata tối thiểu, giới hạn dữ liệu lỗi |
| Nhiều message ở DLQ, không có cảnh báo | Dashboard và alarm cho `messages_ready`/độ tuổi message | Theo dõi kích thước DLQ, tốc độ vào, tuổi message; đặt cảnh báo |
| Message xử lý trùng sau khôi phục | Ack, publish confirm, redelivery, idempotency | Dùng khóa nghiệp vụ hoặc `messageId` để chống áp dụng tác dụng phụ hai lần |

Những chỉ số nên thu thập: độ sâu `orders.work` và `orders.dlq`, số message vào DLQ theo `reason`, tốc độ reject/redelivery, độ trễ xử lý, số lần retry, độ tuổi message lỗi, số publish bị return, và kích thước header nếu ứng dụng republish. Khi logging, ưu tiên `messageId`, `correlationId`, queue, reason, count, exception code; hạn chế log toàn bộ payload hoặc header.

## 8. Kịch bản kiểm chứng trước khi đưa vào vận hành

1. **Luồng thành công:** publish event hợp lệ tới `orders.exchange` với key `orders.created`; listener xử lý một lần và message không nằm trong DLQ.
2. **Poison message:** publish event chứa `INVALID`; xác minh listener thử tối đa bốn lần trong một chu kỳ retry, sau đó message xuất hiện ở `orders.dlq`. Header `x-death` thể hiện sự kiện `rejected` từ `orders.work`.
3. **Sai routing key:** trên môi trường kiểm thử, bỏ binding `orders.failed` hoặc đổi dead-letter key sang giá trị không khớp; xác minh cảnh báo/phép kiểm route nhận ra sự cố. Khôi phục binding trước khi kiểm tiếp.
4. **Tự quay vòng:** lập sơ đồ topology TTL/retry dự kiến; xác minh message hết budget được đưa vào terminal DLQ, không quay lại queue xử lý nữa.
5. **Header:** lặp thất bại có kiểm soát và so sánh độ lớn header; kiểm tra không có stack trace, dữ liệu nhạy cảm hoặc mảng lịch sử do ứng dụng nối thêm vô hạn.
6. **Khôi phục/replay:** sửa nguyên nhân lỗi, replay **một số lượng giới hạn** từ DLQ qua đường publish nghiệp vụ; theo dõi message trùng và kết quả idempotent.

Để điều tra một message cụ thể, ghi lại **exchange gốc → routing key gốc → queue nguồn → nguyên nhân dead-letter → DLX → dead-letter routing key → binding → queue đích**. Chuỗi này cho biết chính xác message đã đi sai ở đâu.

## 9. Tổng kết

Thiết kế DLX đáng tin cậy cần ba lớp phòng vệ bổ trợ nhau:

1. **Đường đi có điểm dừng:** chỉ cho phép vòng retry có giới hạn, và có terminal DLQ không tự quay lại source.
2. **Định tuyến tường minh:** kiểm tra key ở chặng dead-letter cùng exchange type, binding và queue đích; không mặc định routing key ban đầu luôn được giữ.
3. **Metadata có giới hạn:** hiểu `x-death` là lịch sử broker quản lý, tránh nối thêm lỗi/stack trace trong header, và theo dõi kích thước cùng tốc độ message lỗi.

Trong **Spring AMQP**, `RabbitTemplate`, `@RabbitListener`, retry advice, DLX và RabbitMQ policy phải được thiết kế như **một luồng giao nhận thống nhất**. Một message thất bại nên có số phận có thể dự đoán được: được xử lý thành công trong số lần thử cho phép, hoặc đến queue lỗi cuối cùng với đủ thông tin để điều tra và replay an toàn.
