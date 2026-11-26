# Competing consumers và phân phối công việc

Trong **mô hình AMQP**, *competing consumers* (các consumer cạnh tranh) là cách phân phối nhiều công việc độc lập từ **một queue chung** cho nhiều tiến trình hoặc luồng xử lý. Đây là mẫu quan trọng khi học **SPRING_AMQP**: Spring AMQP dùng **@RabbitListener** để nhận message và **RabbitTemplate** để gửi message, còn RabbitMQ quản lý việc giao message, xác nhận giao nhận và phân phối tải.

Ví dụ: hệ thống nhận 10.000 yêu cầu tạo ảnh thu nhỏ. Một producer đưa từng yêu cầu vào queue; ba worker có thể xử lý ba yêu cầu khác nhau cùng lúc. Khi lưu lượng tăng, có thể bổ sung worker mà không phải thay đổi producer.

## 1. Một queue, nhiều consumer hoạt động như thế nào?

~~~mermaid
flowchart LR
    P["Producer<br/>RabbitTemplate"] --> E["Direct exchange<br/>tasks.exchange"]
    E -->|"routing key: tasks.work"| Q[("Một queue chung<br/>tasks.work.q")]
    Q -->|"job-101"| C1["Consumer A<br/>@RabbitListener"]
    Q -->|"job-102"| C2["Consumer B<br/>@RabbitListener"]
    Q -->|"job-103"| C3["Consumer C<br/>@RabbitListener"]
~~~

**Đặc điểm cốt lõi:** một lần publish vào queue chung không tạo một bản sao cho mỗi consumer. RabbitMQ chọn **một consumer đủ điều kiện** để giao mỗi message tại một thời điểm. Các mũi tên từ queue trong sơ đồ minh họa **các message khác nhau** được giao cho các consumer khác nhau.

- **Producer** chỉ cần biết exchange và routing key, không cần biết có bao nhiêu worker.
- **Exchange và binding** xác định message đi vào queue nào; chúng không quyết định consumer cụ thể bên trong một queue.
- **Queue** giữ các message đang chờ được giao; các message đã giao nhưng chưa ACK được tính là *unacknowledged* (chưa xác nhận).
- **Consumer** lấy việc từ cùng một queue. Khi tăng số consumer, nhiều message độc lập có thể được xử lý đồng thời.
- **ACK/NACK** báo kết quả xử lý cho broker. Message có thể bị giao lại khi việc xử lý hoặc kết nối gặp sự cố.

### Phân biệt competing consumers với publish/subscribe

| Tiêu chí | Competing consumers | Publish/subscribe |
|---|---|---|
| Topology điển hình | Một queue, nhiều consumer | Nhiều queue cùng nhận message từ một exchange |
| Một message vào topology | Thường được giao cho một consumer của queue | Có thể được sao chép đến nhiều queue, mỗi queue có consumer riêng |
| Mục đích | Chia tải xử lý một loại công việc | Phát cùng một sự kiện đến nhiều nhóm xử lý |
| Ví dụ | Ba worker cùng tạo thumbnail | Dịch vụ email và dịch vụ thống kê cùng nhận sự kiện đăng ký |

Ví dụ, nếu cần **cả** email và thống kê đều nhận sự kiện “đặt hàng thành công”, hãy bind **hai queue** vào exchange. Nếu cần **một trong ba** worker tạo hóa đơn, ba worker hãy nghe **cùng một queue**.

## 2. RabbitMQ lựa chọn consumer ra sao?

RabbitMQ phân phối message đến các consumer đủ điều kiện theo trạng thái kết nối, số message chưa xác nhận, giới hạn prefetch và các cấu hình như độ ưu tiên consumer. Trong điều kiện tương đương, việc giao message thường trông giống luân phiên, nhưng **không có cam kết mỗi consumer nhận đúng số lượng bằng nhau**.

Giả sử các job có thời gian xử lý khác nhau:

| Consumer | Thời gian một job | Khi prefetch = 1 |
|---|---:|---|
| A | 0,2 giây | ACK sớm, có thể nhận job kế tiếp sớm |
| B | 3 giây | Giữ một job chưa ACK trong lúc xử lý |
| C | 1 giây | Tiếp tục nhận job sau mỗi lần ACK |

Với **prefetch = 1** và ACK thủ công, mỗi consumer chỉ có tối đa một delivery chưa được ACK tại một thời điểm. Worker nhanh thường có cơ hội nhận nhiều job hơn trong một khoảng thời gian; đó là hành vi hữu ích khi job có độ dài khác nhau.

Với **prefetch = 10**, một consumer có thể đang giữ đến mười delivery chưa ACK. Cấu hình này có thể tăng throughput cho job ngắn nhưng cũng có thể khiến một worker chậm giữ nhiều việc, trong khi worker khác rảnh. Prefetch điều chỉnh **số delivery đang chờ ACK trên consumer**, không phải số thread chạy code bên trong một callback.

**Không nên hiểu round-robin là bảo đảm công bằng hoặc giữ thứ tự.** Khi nhiều consumer xử lý đồng thời, job đến trước có thể hoàn tất sau job đến sau. Nếu xử lý cùng một đối tượng cần đúng thứ tự, cân nhắc queue phân vùng theo khóa đối tượng, một consumer cho mỗi phân vùng, hoặc cơ chế tuần tự hóa phù hợp.

## 3. Vòng đời của message và ý nghĩa ACK

~~~mermaid
stateDiagram-v2
    [*] --> Ready: Message vào queue
    Ready --> Unacked: Broker giao cho consumer
    Unacked --> Done: basicAck
    Unacked --> Ready: basicNack(requeue=true) hoặc mất kết nối
    Unacked --> DeadLetter: basicNack(requeue=false), có DLX
    DeadLetter --> [*]: Queue chứa message lỗi
    Done --> [*]
~~~

- **Ready**: message vẫn đang chờ được giao.
- **Unacked**: broker đã giao nhưng chưa nhận xác nhận; message có thể được giao lại sau khi channel/kết nối đóng.
- **ACK**: xác nhận thành công, broker không cần giao lại delivery đó.
- **NACK với requeue = true**: yêu cầu đưa message trở lại hàng chờ. Nếu lỗi là cố định, việc requeue ngay có thể tạo vòng lặp lỗi liên tục.
- **NACK với requeue = false**: nếu queue có dead-letter exchange (DLX), message được dead-letter để điều tra hoặc xử lý lại; nếu không có DLX phù hợp, message có thể bị loại bỏ.

**ACK chỉ sau khi công việc thực sự hoàn thành theo tiêu chí của ứng dụng.** Ví dụ, nếu lưu kết quả vào database thì nên ACK sau khi transaction lưu thành công. Không ACK trước rồi mới làm việc, vì lỗi xảy ra sau ACK có thể khiến công việc bị mất khỏi queue.

Tuy nhiên, trường hợp database đã commit nhưng ứng dụng chết trước khi gửi ACK vẫn có thể khiến cùng message được giao lại. Do đó, mô hình này cần **xử lý idempotent** (xử lý lặp lại không tạo thêm tác dụng ngoài ý muốn); không nên giả định có bảo đảm *exactly once* từ RabbitMQ.

> Trong Spring AMQP, chế độ listener **AUTO** thường nghĩa là *container tự ACK sau khi listener xử lý thành công*, khác với chế độ *auto-ack/no-ack* của broker. Ví dụ bên dưới dùng **MANUAL** để quan sát rõ khi nào ACK/NACK xảy ra.

## 4. Thực hành với Spring Boot và Spring AMQP

Mục tiêu: producer gửi ID công việc qua một direct exchange; RabbitMQ đưa các ID vào **một queue duy nhất**; ba consumer trong cùng ứng dụng chia nhau xử lý. Job lỗi được chuyển đến dead-letter queue (DLQ) để kiểm tra.

### 4.1. Khai báo dependency và kết nối

Thêm starter AMQP vào dự án Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Ví dụ cấu hình khi RabbitMQ đang chạy trên máy phát triển:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
~~~

Tài khoản mặc định **guest** chỉ phù hợp để học trên localhost. Môi trường triển khai thực tế cần tài khoản và phân quyền riêng.

### 4.2. Khai báo exchange, queue, binding, DLQ và listener factory

~~~java
import org.springframework.amqp.core.*;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableRabbit
public class WorkQueueConfig {
    public static final String EXCHANGE = "tasks.exchange";
    public static final String QUEUE = "tasks.work.q";
    public static final String ROUTING_KEY = "tasks.work";
    public static final String DLX = "tasks.dlx";
    public static final String DLQ = "tasks.failed.q";
    public static final String DEAD_KEY = "tasks.failed";

    @Bean
    public Declarables workTopology() {
        DirectExchange exchange = new DirectExchange(EXCHANGE, true, false);
        DirectExchange deadExchange = new DirectExchange(DLX, true, false);

        Queue workQueue = QueueBuilder.durable(QUEUE)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey(DEAD_KEY)
                .build();
        Queue failedQueue = QueueBuilder.durable(DLQ).build();

        return new Declarables(
                exchange,
                deadExchange,
                workQueue,
                failedQueue,
                BindingBuilder.bind(workQueue).to(exchange).with(ROUTING_KEY),
                BindingBuilder.bind(failedQueue).to(deadExchange).with(DEAD_KEY)
        );
    }

    @Bean
    public SimpleRabbitListenerContainerFactory workListenerFactory(
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setAcknowledgeMode(AcknowledgeMode.MANUAL);
        factory.setConcurrentConsumers(3);
        factory.setMaxConcurrentConsumers(3);
        factory.setPrefetchCount(1);
        return factory;
    }
}
~~~

Trong ví dụ:

- **Direct exchange** chuyển message có routing key **tasks.work** vào queue **tasks.work.q**.
- Queue công việc và DLQ được khai báo bền vững (*durable*) để định nghĩa queue không mất khi broker khởi động lại; **durable không đồng nghĩa mọi message đều bền vững**. Cần cả message persistent và cấu hình độ tin cậy phù hợp.
- Khi consumer NACK với **requeue = false**, queue công việc dead-letter message qua **tasks.dlx** đến **tasks.failed.q**.
- **setConcurrentConsumers(3)** tạo ba consumer độc lập trong một tiến trình với **SimpleRabbitListenerContainer**.
- **setPrefetchCount(1)** giới hạn mỗi consumer giữ tối đa một delivery chưa ACK. Đây là điểm khởi đầu dễ quan sát, không phải giá trị tối ưu cho mọi workload.

Trong hệ thống đang tồn tại queue cùng tên, thay đổi các queue argument như DLX có thể làm broker từ chối khai báo lại vì định nghĩa không tương đương. Cần quản lý thay đổi topology có chủ đích; RabbitMQ policy thường linh hoạt hơn cho việc vận hành DLX.

### 4.3. Producer gửi công việc bằng RabbitTemplate

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class JobPublisher {
    private final RabbitTemplate rabbitTemplate;

    public JobPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void submit(String jobId) {
        rabbitTemplate.convertAndSend(
                WorkQueueConfig.EXCHANGE,
                WorkQueueConfig.ROUTING_KEY,
                jobId
        );
    }
}
~~~

Gọi **submit("job-101")**, **submit("job-102")** ... từ API hoặc một tác vụ chủ động để tạo việc. **RabbitTemplate** thực hiện publish tới exchange; nó không gọi trực tiếp consumer và không chỉ định worker nào sẽ nhận.

Ví dụ dùng payload dạng **String** để tập trung vào cơ chế phân phối. Ứng dụng thực tế có thể gửi DTO/JSON, kèm **jobId**, mã đối tượng và phiên bản schema; hai phía phải thống nhất cơ chế serialize/deserialize.

Nếu nghiệp vụ cần biết broker đã nhận message hay chưa, cần cấu hình **publisher confirm** và xử lý lỗi publish. Nếu cần phát hiện message không route được đến queue, cân nhắc **mandatory return**. Hai cơ chế này giải quyết phía **publish**, còn ACK của listener giải quyết phía **consume**.

### 4.4. Consumer nhận và xác nhận message

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class JobWorker {
    private static final Logger log =
            LoggerFactory.getLogger(JobWorker.class);

    private final JobService jobService;

    public JobWorker(JobService jobService) {
        this.jobService = jobService;
    }

    @RabbitListener(
            queues = WorkQueueConfig.QUEUE,
            containerFactory = "workListenerFactory"
    )
    public void handle(
            String jobId,
            Channel channel,
            @Header(AmqpHeaders.DELIVERY_TAG) long deliveryTag
    ) throws IOException {
        try {
            jobService.processIdempotently(jobId);
        } catch (Exception ex) {
            log.error("Job {} failed; move to DLQ", jobId, ex);
            channel.basicNack(deliveryTag, false, false);
            return;
        }

        channel.basicAck(deliveryTag, false);
        log.info("Completed job {}", jobId);
    }
}
~~~

**JobService** là service nghiệp vụ cần tự triển khai và đăng ký dưới dạng Spring bean. Hợp đồng được dùng trong ví dụ:

~~~java
public interface JobService {
    // Triển khai phải xử lý lặp lại cùng jobId một cách an toàn.
    void processIdempotently(String jobId);
}
~~~

Cần một bean triển khai interface này để ứng dụng chạy. Phần nghiệp vụ có thể ghi kết quả vào database, gọi dịch vụ xử lý file hoặc cập nhật trạng thái job.

Giải thích các tham số quan trọng:

- **deliveryTag** là mã delivery trên **channel** hiện tại, không phải mã nghiệp vụ toàn cục của job.
- **basicAck(deliveryTag, false)** xác nhận đúng một delivery. Tham số **multiple = false** tránh ACK đồng loạt các delivery khác.
- **basicNack(deliveryTag, false, false)** từ chối một delivery và **không requeue**; với topology trên, message đi đến DLQ.
- Thao tác ACK/NACK phải dùng đúng **channel** đã nhận delivery. Không lưu channel/tag để ACK tùy tiện từ worker khác.

Ví dụ chủ động đưa mọi lỗi nghiệp vụ vào DLQ. Đây là cách đơn giản để kiểm chứng hành vi; ở môi trường thực, cần phân biệt lỗi vĩnh viễn (dữ liệu sai) với lỗi tạm thời (dịch vụ phụ thuộc bị gián đoạn) và thiết kế chính sách retry hữu hạn.

### 4.5. Thử nghiệm phân phối công việc

1. Khởi động RabbitMQ và ứng dụng đã có bean **JobService**.
2. Gửi lần lượt khoảng 12 ID khác nhau, ví dụ **job-001** đến **job-012**.
3. Quan sát log, luồng xử lý và RabbitMQ Management UI: một queue có **3 consumers**. Nếu các job còn đang chạy, số **Unacked** có thể lên đến 3 vì prefetch = 1.
4. Cho một job xử lý chậm hơn các job khác. Các consumer còn lại vẫn có thể xử lý việc mới sau khi chúng ACK.
5. Ném lỗi nghiệp vụ với một ID thử nghiệm. Quan sát message chuyển sang queue **tasks.failed.q** thay vì bị requeue liên tục.
6. Khởi động thêm một instance ứng dụng cùng cấu hình: số consumer lý thuyết tăng từ 3 lên 6 nếu cả hai instance đều kết nối bình thường. Các instance **cùng nghe queue tasks.work.q**, không khai báo queue mới.

Có thể kiểm tra tác động của prefetch bằng cách đổi từ **1** thành **10** rồi thử các job có thời gian xử lý khác nhau. Hãy so sánh **Ready**, **Unacked**, độ trễ xử lý và mức cân bằng tải; đừng kỳ vọng số job nhận được phân chia chính xác 50/50 hay 1/3.

## 5. Thiết kế độ tin cậy khi nhiều worker cùng xử lý

### 5.1. Xử lý trùng (idempotency)

Ví dụ chuỗi sự kiện hợp lệ:

1. Worker A xử lý **job-101** và commit kết quả vào database.
2. Kết nối tới RabbitMQ bị ngắt ngay trước khi ACK đến broker.
3. Broker giao lại **job-101** cho worker B.
4. Nếu worker B lặp lại tác dụng phụ, kết quả có thể bị ghi hoặc tính tiền hai lần.

Giải pháp: dùng **jobId** làm khóa idempotency, có ràng buộc duy nhất trong storage dùng chung giữa các instance. Gắn thao tác đánh dấu đã xử lý với transaction lưu trạng thái phù hợp; nếu tác dụng phụ ở dịch vụ ngoài, truyền idempotency key và thiết kế khôi phục khi transaction bị gián đoạn. Chỉ ghi “đã xử lý” trước khi thực hiện công việc **không tự động bảo đảm an toàn**, vì worker có thể chết giữa hai thao tác.

### 5.2. Retry và dead-letter queue

| Loại lỗi | Cách xử lý thường phù hợp |
|---|---|
| Payload sai, tài nguyên không tồn tại | NACK không requeue, đưa vào DLQ để kiểm tra |
| Database hoặc HTTP downstream tạm lỗi | Retry có giới hạn, có delay/backoff; sau ngưỡng cho vào DLQ |
| Worker mất kết nối trước ACK | Broker có thể tự giao lại delivery chưa ACK |
| Job đã làm xong nhưng ACK bị mất | Delivery có thể lặp; bảo vệ bằng idempotency |

Không nên gọi **basicNack(..., true)** ngay lập tức mãi mãi đối với message chắc chắn luôn lỗi: cùng một message có thể được giao đi giao lại với tốc độ cao. Có thể thực hiện retry hữu hạn thông qua retry queue có TTL + DLX, cơ chế delay hoặc cấu hình retry/recovery phù hợp của Spring AMQP. Sau số lần thử tối đa, chuyển message sang DLQ và thiết lập quy trình kiểm tra/phát lại có kiểm soát.

### 5.3. Chọn concurrency và prefetch

Số listener xử lý đồng thời tối đa thường phụ thuộc vào:

**Số consumer đang chạy ≈ số instance × số concurrent consumers mỗi instance**

Ví dụ hai instance, mỗi instance cấu hình 3 consumer, có thể có 6 consumer đang kết nối vào cùng queue. Nhưng throughput thực tế còn bị giới hạn bởi database, API phụ thuộc, CPU, network, thời gian chạy mỗi job và số message trong queue.

- Với việc **nặng CPU**, tăng worker quá số tài nguyên xử lý có thể làm giảm hiệu quả.
- Với việc **chờ I/O**, tăng concurrency hợp lý có thể cải thiện throughput, nhưng cần bảo vệ connection pool và dịch vụ downstream.
- **Prefetch thấp** giúp giới hạn số job đang giữ và dễ quan sát mức cân bằng; **prefetch cao** có thể tăng hiệu năng khi xử lý message nhanh.
- Tăng consumer không giải quyết vấn đề một tác vụ cần giữ thứ tự tuyệt đối hoặc tài nguyên chung đang là nút thắt.

Đừng đồng nhất **consumer** với **message**: một consumer có thể nhận tuần tự nhiều message, và số message chờ trong queue có thể lớn hơn nhiều số consumer.

### 5.4. Khi nào không nên dùng competing consumers?

| Yêu cầu | Hướng thiết kế |
|---|---|
| Mỗi nhóm dịch vụ đều phải nhận cùng một sự kiện | Mỗi nhóm có queue riêng cùng bind vào exchange |
| Phải xử lý đúng thứ tự mọi message của một luồng | Xem xét single active consumer hoặc thiết kế một consumer/phân vùng |
| Các job cùng khóa không được chạy đồng thời | Phân vùng theo khóa, khóa nghiệp vụ hoặc điều phối theo đối tượng |
| Tác vụ cần hoàn tất ngay trong request/response | Cân nhắc xử lý đồng bộ; queue phù hợp khi chấp nhận bất đồng bộ |
| Cần bảo đảm tác dụng phụ không lặp | Kết hợp idempotency và transaction; thêm consumer không giải quyết yêu cầu này |

RabbitMQ có cơ chế **Single Active Consumer** cho trường hợp một queue chỉ nên có một consumer chủ động tại một thời điểm. Đây là mục đích khác với competing consumers, nơi nhiều consumer cùng hoạt động để chia tải.

## 6. Quan sát và xử lý sự cố

Trong RabbitMQ Management UI hoặc hệ thống metrics, nên theo dõi:

| Chỉ số / hiện tượng | Diễn giải và gợi ý kiểm tra |
|---|---|
| **Ready** tăng liên tục | Producer đưa việc vào nhanh hơn tốc độ xử lý; kiểm tra throughput và backlog |
| **Unacked** cao kéo dài | Consumer đang giữ nhiều message; xem prefetch, thời gian job, ACK bị thiếu |
| **Consumers = 0** | Chưa có listener hoạt động; kiểm tra kết nối, queue name, bean và container |
| **DLQ** tăng | Có lỗi không thể hoàn tất ở lần xử lý hiện tại; phân loại, cảnh báo và điều tra |
| Job trùng | Kiểm tra reconnect/redelivery, ACK sau commit và idempotency |
| Tải phân phối không đều | Kiểm tra độ dài job, prefetch, consumer priority và mức sử dụng tài nguyên |

Nếu một queue tăng backlog dù đã tăng nhiều consumer, hãy đo **thời gian xử lý từng job** và độ trễ của tài nguyên downstream trước khi tiếp tục tăng concurrency. Trường hợp database bão hòa, thêm listener chỉ khiến nhiều yêu cầu cùng tranh chấp database.

## 7. Ghi nhớ và bài tập tự kiểm tra

Một queue có nhiều consumer là mẫu **chia công việc**, không phải phát sự kiện cho tất cả subscriber. Bản chất đáng tin cậy của mẫu này đến từ **ACK đúng thời điểm, xử lý trùng an toàn, retry có giới hạn và quan sát queue**, chứ không chỉ từ việc tăng số thread.

Thử trả lời và thực nghiệm các câu hỏi sau:

1. Vì sao ba **@RabbitListener** đọc cùng một queue không đồng nghĩa cả ba đều nhận cùng một message?
2. Khi worker A xử lý job lâu hơn B, **prefetch = 1** có thể ảnh hưởng thế nào đến phân phối?
3. Nếu worker lưu database thành công rồi chết trước ACK, job có thể xuất hiện lại không? Làm gì để tránh tác dụng phụ bị nhân đôi?
4. Khi đổi từ **NACK requeue = false** sang **true** cho payload lỗi cố định, Ready/Unacked và log có thể thay đổi ra sao?
5. Hãy khởi chạy hai instance, mỗi instance ba consumer. Kiểm tra trên RabbitMQ xem có bao nhiêu consumer đăng ký và kết quả phân phối có ổn định, bằng nhau tuyệt đối hay không.

**Kết luận cần nắm:** producer gửi vào exchange, binding đưa message tới **queue chung**, các consumer nhận những job khác nhau, còn ACK/NACK quyết định số phận của mỗi delivery. Spring AMQP giúp cấu hình concurrency và vòng đời listener, nhưng ứng dụng vẫn chịu trách nhiệm bảo vệ idempotency và khả năng khôi phục lỗi.
