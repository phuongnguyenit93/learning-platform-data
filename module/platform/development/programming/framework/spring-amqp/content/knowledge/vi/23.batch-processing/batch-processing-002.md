# BatchingRabbitTemplate và BatchingStrategy

## 1. Vì sao cần gửi message theo lô?

Trong ứng dụng sử dụng **Spring AMQP** và **RabbitMQ**, cách gửi quen thuộc là gọi `RabbitTemplate.convertAndSend(...)` cho từng message. Mỗi lời gọi có thể tạo một AMQP message riêng để broker định tuyến qua **exchange**, **binding** và **queue**, sau đó một hoặc nhiều `@RabbitListener` xử lý ở phía nhận.

Với các luồng có nhiều bản ghi nhỏ như nhật ký thao tác, dữ liệu thiết bị, sự kiện thống kê hoặc cập nhật chỉ số, gửi từng message có thể tạo nhiều lượt publish và tăng chi phí xử lý trên kết nối, broker và consumer. **BatchingRabbitTemplate** giúp gom nhiều *message logic* nhỏ thành một *AMQP message vật lý* để gửi đi cùng nhau. Cách này thường cải thiện hiệu suất truyền tải, đổi lại một phần độ trễ và các yêu cầu xử lý lỗi theo lô.

Ví dụ: hệ thống thu thập 1.000 bản ghi đo nhiệt độ mỗi giây. Nếu mỗi bản ghi chỉ dài vài chục byte, nhiều message nhỏ có thể làm tăng overhead. Ta có thể gom tối đa 50 bản ghi hoặc chờ tối đa 200 ms rồi gửi một batch đến queue xử lý.

**Mục tiêu bài học:**

- Hiểu **BatchingRabbitTemplate** làm gì và **BatchingStrategy** quyết định lúc nào tạo batch.
- Khai báo producer batching, exchange, queue, binding và `@RabbitListener` bằng Spring AMQP.
- Phân biệt **producer-side batching**, **de-batching** và **consumer-side batching**.
- Thiết kế batch size, buffer limit, timeout, xác nhận giao nhận, retry, dead-letter và quan sát hệ thống để xử lý bất đồng bộ đáng tin cậy.

> BatchingRabbitTemplate là cơ chế **gom message khi publish** của Spring AMQP. Nó không phải Spring Batch, không tạo transaction phân tán, và không bảo đảm rằng toàn bộ bản ghi trong một batch đều được nghiệp vụ xử lý thành công.

## 2. Ba khái niệm phải phân biệt

| Khái niệm | Nơi thực hiện | Điều xảy ra |
| --- | --- | --- |
| **Producer batching** | Ứng dụng gửi, qua `BatchingRabbitTemplate` | Gom nhiều message logic thành một AMQP message vật lý trước khi publish. |
| **De-batching** | Listener container phía nhận | Tách một AMQP message có định dạng batch thành các message logic để listener xử lý. |
| **Consumer batching** | Listener container phía nhận | Gom nhiều message đã nhận từ broker thành một lần gọi listener; không đòi hỏi producer dùng `BatchingRabbitTemplate`. |

Một message vật lý chứa batch có thể bao gồm nhiều payload logic, nhưng **broker định tuyến, lưu queue và xác nhận ở cấp message vật lý**. Consumer có thể nhìn thấy từng phần tử sau khi de-batch, song điều đó không biến từng phần tử thành một message độc lập trong queue RabbitMQ.

### Luồng minh họa

~~~text
Producer Spring AMQP
  send(E1) -----------┐
  send(E2) -----------┼--> BatchingRabbitTemplate
  send(E3) -----------┘          |
                                | SimpleBatchingStrategy
                                | batchSize / bufferLimit / timeout
                                v
                         AMQP message vật lý
                           [E1 | E2 | E3]
                                |
                                v
                       exchange -- binding
                                |
                                v
                             queue
                                |
                   listener container de-batch
                                |
                 +--------------+--------------+
                 v              v              v
                E1             E2             E3
                                |
                      @RabbitListener xử lý
~~~

Với `SimpleBatchingStrategy`, body của message vật lý gồm các payload nối tiếp nhau theo định dạng có **tiền tố độ dài 4 byte** cho từng payload. Spring AMQP dùng thông tin định dạng batch để tách ở phía nhận. Consumer ngoài Spring AMQP muốn đọc định dạng này phải tự triển khai cách giải mã tương thích; không nên giả định body là một mảng JSON hay chuỗi phân tách bằng dấu phẩy.

## 3. BatchingStrategy: khi nào batch được gửi?

**BatchingStrategy** là giao diện định nghĩa cách gom message và quyết định khi nào đủ điều kiện phát batch. Chiến lược có sẵn thường dùng là **SimpleBatchingStrategy**:

~~~java
import org.springframework.amqp.rabbit.batch.BatchingStrategy;
import org.springframework.amqp.rabbit.batch.SimpleBatchingStrategy;

BatchingStrategy batchingStrategy =
        new SimpleBatchingStrategy(
                50,       // batchSize: tối đa 50 message logic mỗi batch
                128_000,  // bufferLimit: ngưỡng bộ đệm tính theo byte
                200       // timeout: thời gian chờ theo mili giây
        );
~~~

Các tham số không phải là ba điều kiện phải đồng thời thỏa mãn. Khi batch chạm một ngưỡng hoặc tới hạn thời gian, chiến lược có thể kết thúc batch và template publish nó.

| Tham số | Ý nghĩa | Tác động nếu đặt quá lớn |
| --- | --- | --- |
| `batchSize` | Số lượng message logic tối đa muốn gom vào batch. | Batch lớn, tăng độ trễ và ảnh hưởng khi xử lý lỗi cả batch. |
| `bufferLimit` | Giới hạn bộ đệm theo byte để tránh gom quá nhiều dữ liệu. | Tăng bộ nhớ dùng để giữ message chưa gửi. |
| `timeout` | Thời gian tối đa đợi batch khi chưa đủ số lượng/kích thước. | Message ít lưu lượng bị giữ lâu trước khi phát. |

**Ví dụ với batchSize = 4 và timeout = 1.000 ms:**

~~~text
10:00:00.000   send(E1)   bộ đệm: [E1]
10:00:00.100   send(E2)   bộ đệm: [E1, E2]
10:00:00.200   send(E3)   bộ đệm: [E1, E2, E3]
10:00:00.300   send(E4)   đạt batchSize -> publish [E1, E2, E3, E4]

10:00:05.000   send(E5)   bộ đệm: [E5]
10:00:06.xxx              đến timeout -> publish [E5]
~~~

Thời điểm thực tế phụ thuộc `TaskScheduler`, tải hệ thống và network. **Timeout không phải SLA giao hàng chính xác tuyệt đối**. Một message có thể chưa được publish khi phương thức `send(...)` của producer đã trả về.

**Lưu ý về routing:** một AMQP message vật lý chỉ có **một exchange, một routing key và một tập properties của phong bì bên ngoài**. Không dùng batching để trộn các message yêu cầu routing tới nhiều đích khác nhau trong cùng một batch. Hãy cấu hình publisher cho một luồng routing ổn định; nếu ứng dụng cần nhiều exchange/routing key, tách template hoặc phân luồng phù hợp và kiểm chứng hành vi tạo batch của phiên bản đang dùng.

## 4. Cấu hình BatchingRabbitTemplate trong Spring Boot

### 4.1. Dependency và hạ tầng

Với Maven, thêm Spring AMQP qua starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Ứng dụng cần kết nối RabbitMQ qua `spring.rabbitmq.*` theo môi trường. Ví dụ dùng direct exchange `telemetry.events.x`, routing key `telemetry.reading` và queue `telemetry.reading.q`.

### 4.2. Exchange, queue và binding

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.ExchangeBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TelemetryTopology {
    public static final String EXCHANGE = "telemetry.events.x";
    public static final String QUEUE = "telemetry.reading.q";
    public static final String ROUTING_KEY = "telemetry.reading";

    @Bean
    DirectExchange telemetryExchange() {
        return ExchangeBuilder.directExchange(EXCHANGE)
                .durable(true)
                .build();
    }

    @Bean
    Queue telemetryQueue() {
        return QueueBuilder.durable(QUEUE).build();
    }

    @Bean
    Binding telemetryBinding(Queue telemetryQueue,
                             DirectExchange telemetryExchange) {
        return BindingBuilder.bind(telemetryQueue)
                .to(telemetryExchange)
                .with(ROUTING_KEY);
    }
}
~~~

Định tuyến từ exchange tới queue không thay đổi vì batching. RabbitMQ nhìn thấy **một message vật lý mỗi batch**; Spring AMQP xử lý cấu trúc body của message tại ứng dụng.

### 4.3. Tạo BatchingStrategy, scheduler và template

~~~java
import org.springframework.amqp.rabbit.batch.BatchingStrategy;
import org.springframework.amqp.rabbit.batch.SimpleBatchingStrategy;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.BatchingRabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.beans.factory.annotation.Qualifier;

@Configuration
public class TelemetryBatchingConfig {

    @Bean("amqpBatchScheduler")
    ThreadPoolTaskScheduler amqpBatchScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("amqp-batch-");
        return scheduler;
    }

    @Bean("telemetryBatchingTemplate")
    BatchingRabbitTemplate telemetryBatchingTemplate(
            ConnectionFactory connectionFactory,
            @Qualifier("amqpBatchScheduler") TaskScheduler scheduler) {

        BatchingStrategy strategy =
                new SimpleBatchingStrategy(
                        50,       // 50 payload logic
                        128_000,  // ngưỡng tổng kích thước
                        200       // tối đa 200 ms chờ batch
                );

        return new BatchingRabbitTemplate(
                connectionFactory, strategy, scheduler);
    }
}
~~~

`ThreadPoolTaskScheduler` kích hoạt việc gửi batch khi hết hạn chờ, ngay cả khi lượng message thấp hơn `batchSize`. Khi được quản lý như Spring bean, scheduler có vòng đời do Spring quản lý.

`BatchingRabbitTemplate` **kế thừa `RabbitTemplate`**, nhưng mục đích của nó là gửi theo lô. Nếu ứng dụng cũng dùng một RabbitTemplate thông thường để publish message quan trọng yêu cầu hành vi gửi ngay, nên tiêm đúng bean bằng `@Qualifier` để tránh vô tình đi qua bộ đệm. Spring Boot có thể điều chỉnh việc tự cấu hình `RabbitTemplate` khi ứng dụng tự định nghĩa bean cùng loại; hãy kiểm tra dependency injection của ứng dụng.

> Ví dụ dùng API batching thuộc Spring AMQP. Một số API và lựa chọn lifecycle có thể thay đổi giữa các dòng phiên bản. Dùng bộ Spring Boot/Spring AMQP tương thích và thử nghiệm bằng broker thật trước khi đưa cấu hình vào production.

## 5. Gửi dữ liệu bằng BatchingRabbitTemplate

Publisher chỉ cần gọi các phương thức gửi quen thuộc. Sự khác biệt nằm ở bean mà publisher sử dụng.

~~~java
import org.springframework.amqp.rabbit.core.BatchingRabbitTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class TelemetryPublisher {
    private final BatchingRabbitTemplate template;

    public TelemetryPublisher(
            @Qualifier("telemetryBatchingTemplate")
            BatchingRabbitTemplate template) {
        this.template = template;
    }

    public void publishReading(String deviceId, int temperature) {
        // Payload String để dùng MessageConverter mặc định.
        // Production nên có schema/version và định danh event rõ ràng.
        String payload = deviceId + "," + temperature;

        template.convertAndSend(
                TelemetryTopology.EXCHANGE,
                TelemetryTopology.ROUTING_KEY,
                payload
        );
    }
}
~~~

Gọi thử:

~~~java
for (int i = 0; i < 120; i++) {
    telemetryPublisher.publishReading("sensor-A", 25 + (i % 3));
}
~~~

Giả sử các message nhỏ và scheduler chưa flush xen giữa, ngưỡng 50 message có thể tạo hai batch đủ 50 và một batch còn 20 được gửi khi timeout tới hạn. **Đây chỉ là ví dụ cách chia lô**: số message vật lý thực tế còn phụ thuộc kích thước body, thời điểm publish, scheduler và trạng thái publisher. Không được khẳng định luôn có đúng ba message vật lý trong mọi lần chạy.

Hàm `publishReading()` trở về **không chứng minh message đã tới RabbitMQ**: nó có thể mới được thêm vào bộ đệm của producer. Đây là điểm khác biệt vận hành quan trọng so với việc nhìn lệnh `convertAndSend()` như một hành động gửi xong ngay.

### Tính ổn định của định dạng payload

Payload `deviceId,temperature` dễ hiểu nhưng chưa đủ cho production vì một device ID có thể chứa dấu phân tách, và không có định danh chống trùng. Với hệ thống thật, có thể dùng JSON kèm các trường:

~~~json
{
  "eventId": "evt-001",
  "schemaVersion": 1,
  "deviceId": "sensor-A",
  "temperature": 26,
  "recordedAt": "2026-11-26T03:00:00Z"
}
~~~

Khi đó cần cấu hình message converter JSON tương thích ở **producer và consumer**. Nên bảo đảm từng message logic chứa **eventId** riêng: AMQP properties ngoài của batch không nhất thiết bảo tồn đầy đủ mọi metadata như khi từng message được publish độc lập.

## 6. Consumer nhận message đã de-batch

### 6.1. Listener xử lý từng message logic

Với listener container Spring AMQP có **de-batching** bật (cấu hình mặc định thường dùng), nó nhận một AMQP message có thông tin batch, tách các phần tử rồi gọi listener với từng message logic. Listener vẫn có chữ ký thông thường:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class TelemetryListener {

    @RabbitListener(queues = TelemetryTopology.QUEUE)
    public void handle(String reading) {
        // Ví dụ: "sensor-A,26"
        // Nghiệp vụ thực nên parse an toàn, kiểm tra schema,
        // và ghi nhận eventId để không xử lý trùng.
        System.out.println("Received: " + reading);
    }
}
~~~

Nếu một batch vật lý có 50 phần tử, listener có thể được gọi 50 lần; broker vẫn chỉ giao **một delivery vật lý** cho batch đó. Container phải quản lý de-batching và ACK tương ứng cho delivery vật lý.

### 6.2. Nhận List trong một lần gọi listener

Nếu bài toán phù hợp xử lý nhiều bản ghi cùng lúc ở phía consumer, cấu hình **batch listener**. Một ví dụ sử dụng `SimpleRabbitListenerContainerFactory`:

~~~java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TelemetryConsumerConfig {
    @Bean("telemetryBatchListenerFactory")
    SimpleRabbitListenerContainerFactory telemetryBatchListenerFactory(
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setBatchListener(true);
        factory.setDeBatchingEnabled(true);
        return factory;
    }
}
~~~

Và listener:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.List;

import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class TelemetryBatchListener {
    @RabbitListener(
            queues = TelemetryTopology.QUEUE,
            containerFactory = "telemetryBatchListenerFactory"
    )
    public void handleBatch(List<Message> messages) {
        for (Message message : messages) {
            String reading = new String(
                    message.getBody(), StandardCharsets.UTF_8);
            System.out.println("Received in batch: " + reading);
        }
    }
}
~~~

**Chỉ triển khai một trong hai listener** cho cùng queue trong bài thử; nếu bật cả hai listener, chúng sẽ cạnh tranh lấy delivery và kết quả quan sát không nhất quán. `setBatchListener(true)` thay đổi cách listener được gọi, còn `setDeBatchingEnabled(true)` bảo đảm container nhận diện/tách message do producer tạo batch. Chế độ consumer batching tổng quát có thể gom nhiều delivery độc lập thêm nữa tùy cấu hình; không nên nhầm số phần tử trong List với số delivery vật lý.

Trong môi trường thực tế, hãy thống nhất kiểu listener, converter, prefetch, ACK mode và cơ chế retry. Nếu chỉ cần xử lý từng event độc lập, listener đơn giản ở mục 6.1 thường dễ cô lập lỗi hơn.

## 7. Xác nhận giao nhận, lỗi một phần tử và dead-letter

Batching đem lại hiệu suất nhưng đặt ra một giới hạn: **RabbitMQ ACK/NACK ở cấp AMQP delivery vật lý**. Ví dụ một batch chứa E1–E5, consumer đã ghi E1–E3 vào database nhưng xử lý E4 gặp lỗi:

~~~text
AMQP message vật lý: [ E1, E2, E3, E4, E5 ]
                                ^
                                | E4 lỗi sau khi E1-E3 đã ghi DB

NACK/requeue delivery vật lý
            |
            v
Batch có thể được giao lại -> E1, E2, E3 có nguy cơ xử lý lại
~~~

Không có lệnh ACK cấp broker cho riêng E1 rồi NACK riêng E4 trong cùng một message vật lý. Việc listener container gọi callback cho từng phần tử cũng không tạo ra khả năng xác nhận riêng ở broker. Tùy loại listener, chế độ ACK và batch error handling, kết quả retry/redelivery có thể tác động tới cả batch.

Vì vậy:

1. **Idempotency từng phần tử:** dùng `eventId` hoặc business key ổn định để tránh ghi trùng khi batch được giao lại.
2. **Retry có giới hạn:** với lỗi tạm thời, dùng retry/backoff phù hợp; tránh requeue vô hạn cùng một batch lỗi.
3. **DLQ và xử lý lỗi:** cấu hình dead-letter exchange/queue để phân tích delivery thất bại; cần hiểu rằng broker có thể dead-letter **message batch vật lý**, không phải chỉ phần tử E4.
4. **Chính sách partial failure:** nếu nghiệp vụ yêu cầu lưu thành công E1–E3 và tách riêng E4, cần tự quản lý trạng thái từng phần tử và cơ chế phát lại/phục hồi nghiệp vụ, không chỉ dựa vào NACK.
5. **Transaction nghiệp vụ:** việc ghi database và ACK ở RabbitMQ thường không nằm trong cùng một transaction nguyên tử. Cần thiết kế duplicate-safe processing, outbox/inbox hoặc trạng thái tác vụ nếu yêu cầu độ tin cậy cao.

Với message quan trọng cần cách ly lỗi độc lập từng event, cân nhắc **không gom nhiều event vào một delivery vật lý**, hoặc chuyển sang xử lý batch có lưu trạng thái riêng cho từng event.

### Publisher confirms và returns

Publisher confirms/returns là cơ chế theo dõi việc broker nhận và định tuyến **publish vật lý**. Với BatchingRabbitTemplate, thời điểm thực sự publish có thể xảy ra sau lời gọi `send()`, và một batch có thể chứa nhiều message logic. Vì vậy:

- Không được xem `convertAndSend()` trả về là một confirm cho từng event.
- Xác nhận cho một publish batch không chứng minh từng event đã được nghiệp vụ xử lý.
- Các API callback/correlation của template thông thường không nhất thiết ánh xạ một-một đến từng message logic khi batching. Cần kiểm chứng hỗ trợ confirms/returns và hành vi failure của **đúng phiên bản Spring AMQP** đang triển khai; không gắn callback rồi giả định có một xác nhận riêng cho mỗi phần tử.

Đối với sự kiện nghiệp vụ không được mất, hãy ghi sự kiện bền vững trước khi gửi (ví dụ **transactional outbox**) rồi xóa/đánh dấu đã phát theo một quy trình có khả năng retry; không lấy bộ đệm RAM của Batch template làm nơi lưu tin cậy.

## 8. Bộ đệm phía producer và vòng đời ứng dụng

**Một nguy cơ thường bị bỏ qua:** message đang nằm trong buffer của `BatchingRabbitTemplate` **chưa đến broker**. Nếu tiến trình dừng đột ngột, mất điện hoặc bị kill trước khi batch được publish, các message còn trong RAM có thể mất.

Hãy thiết kế vòng đời rõ ràng:

- Tránh timeout quá dài đối với dữ liệu quan trọng; nếu lưu lượng thấp, timeout phải đủ ngắn để batch được gửi kịp.
- Khi shutdown có kiểm soát, bảo đảm luồng phát sự kiện dừng nhận dữ liệu mới, chờ xử lý các batch còn tồn theo cơ chế phù hợp của phiên bản thư viện, sau đó mới đóng kết nối. Không mặc định việc JVM thoát sẽ đẩy mọi buffer.
- Đo cả số event đã **xếp vào buffer** và số batch thực sự **được publish**, thay vì gộp hai chỉ số.
- Nếu không chấp nhận mất dữ liệu khi producer crash, dùng một cơ chế lưu bền vững trước khi gửi như outbox, log bền vững hoặc bảng trạng thái.

**Batching không tạo transaction cho các message logic.** Với publish qua buffer, ranh giới của lệnh gửi vật lý có thể khác thời điểm bắt đầu/commit một transaction tại service gọi. Nếu ứng dụng dùng transaction RabbitMQ hoặc cần đồng bộ giao dịch database–message, phải thử nghiệm tương tác cụ thể và lựa chọn kiến trúc bảo đảm phù hợp; không mặc định các lời gọi `convertAndSend()` trở thành một transaction duy nhất.

## 9. Chọn batchSize, bufferLimit và timeout

Không có cấu hình tối ưu cho mọi luồng. Ba mục tiêu thường xung đột:

- **Throughput cao:** batch lớn có thể giảm overhead trên mỗi event.
- **Latency thấp:** batch nhỏ và timeout ngắn giúp event xuất hiện sớm trong queue.
- **Khả năng phục hồi lỗi:** batch nhỏ giới hạn số event cần xử lý lại khi một delivery thất bại.

Ví dụ tham khảo để **bắt đầu benchmark**, không phải con số bắt buộc:

| Mẫu tải | batchSize | bufferLimit | timeout | Điều cần đo |
| --- | ---: | ---: | ---: | --- |
| Event nhỏ, lưu lượng cao | 50 | 128 KB | 200 ms | Message/s, kích thước batch, CPU broker, thời gian chờ. |
| Event nhỏ, lưu lượng thất thường | 20 | 64 KB | 100 ms | Tỷ lệ batch rất nhỏ, P95/P99 latency. |
| Phản hồi nghiệp vụ cần ngay | 1 hoặc RabbitTemplate thường | Tùy payload | Không chờ gom | End-to-end latency và độ tin cậy. |

Với `batchSize = 50`, nếu chỉ có 2 event mỗi giây và timeout 200 ms, phần lớn batch sẽ được gửi do **timeout** chứ không đầy 50 phần tử. Ngược lại, với hàng nghìn event mỗi giây, batch thường đầy trước timeout. Kích thước mỗi phần tử biến đổi lớn cũng làm `bufferLimit` trở thành ngưỡng quan trọng hơn.

Một phương pháp đo cơ bản:

1. Đặt mức tải và kích thước payload gần với production.
2. Chạy baseline dùng `RabbitTemplate` thường.
3. Chạy lần lượt các cấu hình batching với cùng exchange, queue và số lượng consumer.
4. Đo **throughput thực nhận**, latency từ lúc tạo event đến lúc xử lý, P95/P99, số message vật lý, số event logic, RAM producer và tải broker.
5. Lặp lại trong điều kiện consumer chậm, mạng gián đoạn, broker restart và publisher shutdown để kiểm tra giới hạn độ tin cậy.

Không chỉ nhìn queue depth: một phần event có thể **đang chờ trong producer buffer** nên chưa hiện trong queue của RabbitMQ.

## 10. Quan sát và xử lý sự cố

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Listener chưa thấy message dù producer gọi send | Chưa đủ batchSize/bufferLimit, timeout chưa đến; batch còn ở bộ đệm. | Đợi quá timeout, kiểm tra scheduler, đo thời điểm publish vật lý. |
| Consumer thấy dữ liệu khó đọc hoặc sai định dạng | Chưa de-batch, converter không tương thích, consumer không biết định dạng `lengthHeader4`. | Kiểm tra container, batch header, raw payload và chiến lược giải mã. |
| Queue có rất ít message nhưng listener xử lý rất nhiều event | Nhiều event logic được đóng trong một message vật lý. | Đo riêng delivery count và logical event count. |
| Một event lỗi làm nhiều event bị xử lý lại | Cùng nằm trong một delivery vật lý; NACK/requeue cả batch. | Thêm idempotency, chính sách retry/DLQ và xử lý partial failure. |
| Latency tăng khi ít message | Timeout cao, batch ít khi đầy. | Giảm timeout hoặc dùng RabbitTemplate thường. |
| Event mất khi producer crash | Batch còn trong RAM, chưa publish. | Thiết kế outbox hoặc lưu bền vững trước publish. |
| Bean RabbitTemplate không như mong đợi | BatchingRabbitTemplate kế thừa RabbitTemplate, gây nhập nhằng injection/autoconfiguration. | Dùng `@Qualifier`, phân tách các publisher theo chức năng. |
| Memory tăng khi tải cao | Producer tạo quá nhiều event chờ, không giới hạn upstream; consumer/broker chậm. | Kiểm soát tốc độ gửi, kích thước batch, backpressure và tình trạng kết nối. |

Nên có metric tối thiểu cho **logical event created**, **logical event buffered**, **physical batch published**, **batch size phân phối**, **publish error**, **consumer processing success/failure**, **redelivery**, **DLQ count** và **end-to-end latency**. Gắn trace hoặc eventId từ lúc tạo event đến khi xử lý để điều tra mất/trùng mà không phụ thuộc duy nhất vào AMQP delivery tag.

## 11. Bài thực hành hoàn chỉnh

**Bối cảnh:** Mỗi cảm biến gửi bản ghi nhiệt độ. Ứng dụng cần gom bản ghi trước khi publish để giảm overhead, sau đó tách batch và lưu từng bản ghi an toàn.

**Yêu cầu:**

1. Khởi động RabbitMQ và cấu hình `spring-boot-starter-amqp`. Tạo direct exchange, durable queue, binding như mục 4.
2. Khai báo `BatchingRabbitTemplate` với `SimpleBatchingStrategy(10, 16_384, 1_000)` và `ThreadPoolTaskScheduler`.
3. Gửi 7 message String, chờ quá 1 giây rồi kiểm tra listener nhận đủ 7 bản ghi. Ghi thời điểm tạo và nhận để thấy hiệu ứng timeout.
4. Gửi liên tiếp 25 message nhỏ. Quan sát tổng event logic đã nhận, số batch vật lý và các điều kiện khiến batch được flush.
5. Bật listener thường để xử lý từng phần tử; sau đó **tắt listener này** và thử listener nhận `List<Message>` với `batchListener = true`.
6. Thêm `eventId` cho từng bản ghi, giả lập exception ở bản ghi thứ 4 và quan sát retry/redelivery khi cấu hình retry/ACK phù hợp. Đảm bảo những event đã lưu không bị ghi trùng.
7. Tắt đột ngột producer ngay sau khi chỉ gửi 1 message với timeout dài. Giải thích vì sao event có thể chưa xuất hiện ở broker và đề xuất outbox nếu cần bảo đảm không mất.

**Bài kiểm tra tư duy:** Producer đã gọi `convertAndSend()` 8 lần thành công với `batchSize = 10` và `timeout = 5 giây`. Broker đang có 0 message mới trong queue. Điều này có nhất thiết là lỗi RabbitMQ không?

**Trả lời:** Không. Tám message logic có thể vẫn nằm trong buffer của template. Khi timeout đến (hoặc ngưỡng khác buộc batch được phát), mới có AMQP message vật lý đi tới exchange và queue. Việc hàm gửi trả về không đồng nghĩa broker đã nhận 8 message.

**Bài kiểm tra thứ hai:** Consumer đã xử lý thành công 9 phần tử đầu của batch 10 phần tử rồi lỗi ở phần tử cuối. Có thể gửi NACK chỉ cho phần tử cuối không?

**Trả lời:** Không theo cơ chế ACK/NACK broker cho batch vật lý: RabbitMQ thấy một delivery. Muốn xử lý riêng lỗi từng bản ghi phải có cơ chế idempotency và lưu trạng thái/phát lại ở cấp ứng dụng, hoặc giảm mức batching để các event thành delivery riêng.

## 12. Tổng kết

**BatchingRabbitTemplate** giúp giảm số lần publish vật lý bằng cách gom nhiều message logic; **BatchingStrategy** như **SimpleBatchingStrategy** quyết định tạo batch dựa trên số phần tử, kích thước bộ đệm và timeout. Phía nhận có thể **de-batch** về listener từng message hoặc dùng **batch listener** để nhận danh sách. Để dùng tốt trong Spring AMQP, cần thiết kế cùng lúc **exchange–queue–binding**, giới hạn latency, quản lý buffer producer, phân biệt xác nhận vật lý với thành công nghiệp vụ, và bảo đảm **idempotency**, **retry**, **DLQ** và quan sát hệ thống.
