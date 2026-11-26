# Missing queue, sai thuộc tính queue và chính sách dừng container

Trong chương **Listener container** của **SPRING_AMQP**, phương thức **@RabbitListener** không tự mình quản lý kết nối, consumer, việc tìm queue hay khôi phục khi RabbitMQ gặp sự cố. Phần lớn công việc này được thực hiện bởi **message listener container**. Container có thể khởi động, kiểm tra queue, tạo consumer, nhận message, ACK/NACK và thử phục hồi khi kết nối bị gián đoạn.

Một tình huống vận hành rất thường gặp là ứng dụng chạy được nhưng **queue chưa được tạo**, hoặc queue đã có trên broker với **thuộc tính khác** so với định nghĩa trong code. Câu hỏi khi đó không chỉ là “làm sao hết lỗi 404/406?”, mà là **có nên cho container tiếp tục chờ, dừng consumer hay làm ứng dụng khởi động thất bại?**

Bài học hướng dẫn nhận diện missing queue, lỗi queue không tương đương, phân biệt việc **RabbitAdmin khai báo tài nguyên** với việc **container tiêu thụ tài nguyên**, chọn các chính sách **missingQueuesFatal**, **mismatchedQueuesFatal**, **autoDeclare** và **autoStartup**, cũng như xây quy trình kiểm tra và khôi phục an toàn. Những kiến thức này hỗ trợ việc xử lý RabbitTemplate, @RabbitListener, exchange/queue/binding, ACK, retry, dead-letter và giám sát trong các luồng bất đồng bộ đáng tin cậy.

> **Điểm cần nhớ:** **missingQueuesFatal=true** không đồng nghĩa “một queue bất kỳ bị thiếu thì luôn dừng mọi container”; trong cấu hình nhiều queue, việc có ít nhất một queue còn dùng được làm thay đổi hành vi. **mismatchedQueuesFatal=false** cũng **không** làm RabbitMQ chấp nhận queue sai thuộc tính. Hai thuộc tính điều khiển những tình huống khác nhau.

## 1. Một listener container làm những gì?

~~~mermaid
flowchart LR
    A["Spring application<br/>@RabbitListener"] --> C["Listener container"]
    C -->|"Open connection/channel"| B["RabbitMQ"]
    C -->|"Passive queue checks"| Q[("Queue")]
    C -->|"basic.consume"| Q
    Q -->|"Deliveries"| C
    C -->|"Invoke handler"| L["Business logic"]
    L -->|"Success/error"| C
    C -->|"ACK/NACK theo policy"| B
    R["RabbitAdmin"] -.->|"Active declare<br/>khi được cấu hình"| Q
~~~

Container cung cấp những chức năng như:

- Quản lý vòng đời **start/stop**, khởi tạo consumer và thread liên quan.
- Xác minh khả năng dùng các queue đã cấu hình và đăng ký **basic.consume**.
- Kích hoạt handler của **@RabbitListener** khi có message.
- Quản lý **ACK**, **prefetch**, concurrency, retry/requeue theo cấu hình.
- Cố gắng khôi phục consumer sau lỗi **không fatal**.
- Phát một số **application events** để vận hành giám sát.

**RabbitAdmin và listener container không phải cùng một vai trò**. RabbitAdmin giúp khai báo exchange, queue và binding; listener container gắn với queue và nhận message. Tuy nhiên, container có thể **yêu cầu RabbitAdmin khai báo lại tài nguyên** khi phát hiện queue thiếu, tùy thuộc cấu hình autoDeclare và các bean AMQP hiện có.

### 1.1. Hai loại container phổ biến

| Đặc điểm | SimpleMessageListenerContainer (SMLC) | DirectMessageListenerContainer (DMLC) |
|---|---|---|
| Cách gọi listener | Chuyển delivery từ RabbitMQ client sang thread consumer của Spring | Gọi listener gần hơn với thread của RabbitMQ client |
| Concurrency | **concurrentConsumers**, **maxConcurrentConsumers** | **consumersPerQueue** |
| Nhiều queue | Một consumer SMLC có thể phục vụ nhiều queue | Consumer được tổ chức theo từng queue |
| Đổi danh sách queue khi đang chạy | Có thể phải tái tạo các consumer liên quan | Có thể thay đổi consumer của queue đích, ít ảnh hưởng queue khác |
| Khôi phục sau consumer failure | **recoveryInterval/recoveryBackOff** | Giám sát và phục hồi theo **monitorInterval** |
| Kiểm tra sai thuộc tính queue | Hỗ trợ mismatchedQueuesFatal | Hỗ trợ mismatchedQueuesFatal |

Spring Boot thông dụng tự tạo **SimpleRabbitListenerContainerFactory** nếu ứng dụng không chỉ định factory. Có thể chuyển sang direct container bằng thuộc tính **spring.rabbitmq.listener.type=direct**. Các tên option và hành vi cụ thể cần đối chiếu phiên bản Spring Boot/Spring AMQP của dự án.

## 2. Missing queue là lỗi gì?

Một listener có thể khai báo:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class TaskConsumer {
    @RabbitListener(queues = "orders.tasks.q")
    public void handle(String jobId) {
        System.out.println("Processing job " + jobId);
    }
}
~~~

Nếu **orders.tasks.q** chưa tồn tại trong vhost mà connection đang dùng, consumer không thể đăng ký nhận message từ queue đó.

Một log của broker có thể mang thông điệp tương tự:

~~~text
NOT_FOUND - no queue 'orders.tasks.q' in vhost 'app_dev'
reply-code=404
channel.close
~~~

Ở cấp giao thức, một **passive queue declare** trên queue chưa tồn tại có thể gây **404 NOT_FOUND** và broker đóng **channel** đang dùng. Tình huống này khác với việc nhận một message rồi xử lý thất bại.

Các nguyên nhân thường gặp:

1. Pipeline provisioning chưa tạo queue hoặc binding.
2. Ứng dụng kết nối sai **virtual host**, host hoặc RabbitMQ cluster.
3. Tên queue bị đổi, sai chữ hoa/chữ thường hoặc sai profile môi trường.
4. Queue auto-delete hoặc queue có expiration đã biến mất sau giai đoạn không còn consumer.
5. Queue bị xóa bằng công cụ quản trị hoặc trong lúc rollout/migration.
6. Consumer chỉ biết tên queue nhưng không có quyền hoặc cơ chế tự tạo tài nguyên tương ứng.

**Không thấy message đến listener không luôn có nghĩa queue thiếu.** Nếu queue tồn tại nhưng producer dùng sai exchange/routing key, message có thể không được route. Nếu queue có message mà consumer không nhận, còn phải kiểm tra consumer count, quyền read, ACK và trạng thái container.

### 2.1. Missing queue khác broker không kết nối được

| Sự cố | Hiện tượng điển hình | Bước kiểm tra |
|---|---|---|
| **Queue chưa tồn tại** | 404 NOT_FOUND ở passive declare, queue không có trong vhost | Tên queue, vhost, provisioning |
| **Broker chưa sẵn sàng** | Connection refused, timeout, DNS/TLS failure | Host/port, mạng, TLS, readiness của broker |
| **Sai tài khoản/quyền** | ACCESS_REFUSED hoặc authentication failure | Username, vhost permissions |
| **Queue exclusive bị chiếm** | RESOURCE_LOCKED / exclusive consumer conflict | Connection/consumer đang sở hữu |
| **Queue có nhưng không có binding** | Consumer có thể chạy nhưng không nhận message mới | Exchange, routing key, binding |
| **Queue có message nhưng consumer đã dừng** | Ready tăng, Consumers = 0 | Lifecycle, container events, log |

Đừng chỉ tăng thời gian chờ hoặc bật retry vô hạn để “chữa” một lỗi sai vhost hoặc thiếu quyền.

## 3. Sai thuộc tính queue: vì sao RabbitMQ trả 406?

Giả sử RabbitMQ đã có queue:

~~~text
Queue: orders.tasks.q
durable: true
exclusive: false
autoDelete: false
x-queue-type: classic
x-message-ttl: 60000
~~~

Một bản ứng dụng mới active declare cùng tên nhưng với:

~~~text
Queue: orders.tasks.q
durable: false
x-message-ttl: 30000
~~~

RabbitMQ không âm thầm chuyển queue đang tồn tại thành định nghĩa mới. Broker có thể đóng channel khai báo với:

~~~text
PRECONDITION_FAILED - inequivalent arg 'durable'
for queue 'orders.tasks.q' in vhost 'app_dev'
reply-code=406
~~~

Tùy thuộc sự khác biệt cụ thể, thông báo có thể chỉ rõ **x-message-ttl**, **x-queue-type**, **auto-delete** hoặc argument khác.

### 3.1. Những thuộc tính nên đối chiếu

| Thuộc tính | Ví dụ | Ghi chú |
|---|---|---|
| **durable** | true / false | Không thể chuyển tùy ý bằng declare lại |
| **exclusive** | true / false | Liên quan quyền sở hữu connection và vòng đời queue |
| **autoDelete** | true / false | Có thể bị broker xóa sau khi không còn consumer thỏa điều kiện |
| **x-queue-type** | classic / quorum | Không đổi classic sang quorum bằng một active declare cùng tên |
| **x-max-priority** | 4 / 8 | Cấu hình lúc tạo classic priority queue |
| **x-message-ttl** | 60000 | Có thể liên quan policy/arguments; xem nguồn cấu hình thực tế |
| **x-dead-letter-exchange** | tasks.dlx | Ảnh hưởng retry/DLQ, cần kiểm tra topology |
| **x-max-length** | 10000 | Có thể do policy hoặc argument quản lý |

Không phải mọi argument đều có cùng quy tắc tương đương giữa các phiên bản RabbitMQ. **Đọc chính reply-text của lỗi 406** và so sánh định nghĩa thực tế trong broker, policy/operator policy với bean Java. Không suy đoán rằng một thay đổi trong application.yml sẽ tự sửa queue cũ.

### 3.2. Passive declare không xác thực đầy đủ thuộc tính

**queueDeclarePassive(name)** chỉ xác nhận queue có tồn tại và trả về thông tin như số Ready/consumer ở thời điểm kiểm tra. Nó **không xác thực trọn vẹn** durable, autoDelete, x-dead-letter-exchange hoặc các arguments.

**Active declare** có cơ chế kiểm tra tính tương đương và có thể trả 406. Vì vậy, nếu muốn **fail-fast khi topology không đúng**, cần chiến lược kiểm tra/khai báo có quyền phù hợp thay vì chỉ passive check.

## 4. Hai cấu hình fatal có mục đích khác nhau

Hai thuộc tính quan trọng của Spring AMQP listener container:

| Thuộc tính | Mặc định thông dụng | Phát hiện | Kết quả khi bật |
|---|---|---|---|
| **missingQueuesFatal** | **true** | Không có queue khả dụng trong nhóm queue được cấu hình cho container sau các lần thử | Khởi động có thể thất bại; trong lúc chạy container có thể ngừng khi không phục hồi được |
| **mismatchedQueuesFatal** | **false** | Các queue declarable trong context không tương đương với broker, với RabbitAdmin thích hợp | Có thể fail startup hoặc stop container trong recovery |
| **autoDeclare** | **true** | Container thấy queue của mình bị thiếu và có RabbitAdmin phù hợp | Cố gắng khai báo lại AMQP objects |
| **autoStartup** | **true** | Container tham gia Spring lifecycle | Tự start khi application context khởi động |

**Fatal** là chính sách container, không phải một “bit” làm RabbitMQ bỏ qua lỗi. Nếu container dừng, producer vẫn có thể publish vào queue còn tồn tại, làm backlog tăng; ACK/retry của các delivery trước đó phụ thuộc thời điểm dừng và trạng thái channel.

### 4.1. missingQueuesFatal = true

Theo tài liệu Spring AMQP, khi **không queue nào** trong các queue mà container định nghe có thể được sử dụng, trạng thái này được xem là fatal nếu **missingQueuesFatal=true**. Trong khởi động bình thường, application context có thể thất bại khi consumer không tạo được.

Nếu queue bị xóa trong lúc consumer đang chạy, container có các lần thử tái đăng ký/kiểm tra trước khi quyết định dừng. Ví dụ cấu hình mặc định thường có **3 lần retry sau lần đầu**, cách nhau khoảng 5 giây. Các tham số này có thể điều chỉnh và không nên coi mốc thời gian là SLA chính xác cho mọi phiên bản và môi trường.

**Điểm tinh tế:** Container có **nhiều queue** không nhất thiết dừng hoàn toàn nếu chỉ **một phần queue thiếu**. Nó có thể tiếp tục tiêu thụ từ các queue có sẵn và định kỳ kiểm tra lại queue bị thiếu.

### 4.2. missingQueuesFatal = false

Khi **false**, container có thể tiếp tục vòng **recovery** sau khi hết các lần passive-declare ban đầu thay vì coi việc thiếu toàn bộ queue là fatal. Với SMLC, nó thử lại theo **recoveryInterval/recoveryBackOff**; với DMLC, consumer được giám sát/phục hồi theo **monitorInterval**.

Điều này hữu ích nếu provisioning queue diễn ra **sau khi ứng dụng khởi động**, hoặc queue tạm thời biến mất trong quy trình dự kiến. Nhưng container vẫn không thể nhận message cho đến khi queue có sẵn và consumer thực sự đăng ký thành công.

**False không có nghĩa đã kết nối hoặc đã có consumer hoạt động.** Nếu không có cảnh báo về tình trạng consumer và queue, ứng dụng có thể trông như healthy trong khi không xử lý được một message nào.

### 4.3. mismatchedQueuesFatal = true

Khi bật, listener container dùng cơ chế RabbitAdmin để kiểm tra tính tương đương của các queue đã khai báo trong **ApplicationContext** với broker. Nếu phát hiện xung đột thuộc tính, container có thể làm **startup thất bại**, hoặc **ngừng khi phát hiện trong recovery**.

Có các điều kiện đáng chú ý:

- Cần **một RabbitAdmin duy nhất** trong context, hoặc chỉ định một RabbitAdmin cụ thể cho container.
- Việc kiểm tra có thể bao phủ **các queue declarable của toàn context**, không chỉ các queue listener này đang dùng. Muốn giới hạn phạm vi, cần RabbitAdmin được cấu hình phù hợp và conditional declarations.
- Khi broker chưa sẵn sàng lúc application startup, kiểm tra có thể được thực hiện **khi connection thiết lập lại**; không mặc định startup thất bại ngay tại thời điểm broker đang offline.
- Với bean **@RabbitListener được đánh dấu @Lazy**, kiểm tra mismatch/missing lúc khởi tạo có những giới hạn nhằm tránh deadlock; nên preflight queue trước khi truy cập bean lazy.

### 4.4. mismatchedQueuesFatal = false không loại bỏ lỗi 406

Một nhầm lẫn nghiêm trọng là cho rằng đặt **mismatchedQueuesFatal=false** sẽ cho phép ứng dụng ghi đè queue đang tồn tại. Không đúng.

Nếu **RabbitAdmin** hoặc một thành phần khác **active declare** với thuộc tính không tương đương, RabbitMQ vẫn có thể báo **406 PRECONDITION_FAILED** và đóng channel. Thuộc tính mismatch fatal chỉ điều khiển một lớp kiểm tra/chính sách container; không tắt kiểm tra thuộc tính của broker.

Do đó, **“bỏ cờ fatal để ứng dụng chạy” không phải giải pháp sửa topology**.

## 5. Container có thể tự khai báo lại queue: autoDeclare

Spring AMQP có cơ chế để container nhờ **RabbitAdmin** khai báo lại queue/exchange/binding khi phát hiện thiếu queue, ví dụ một queue **auto-delete** hoặc có expiration đã bị broker xóa.

~~~mermaid
flowchart TD
    S["Listener container start"] --> Q{"Queue khả dụng?"}
    Q -->|"Có"| C["Đăng ký consumer"]
    Q -->|"Thiếu"| A{"autoDeclare và RabbitAdmin phù hợp?"}
    A -->|"Có"| D["RabbitAdmin active declare topology"]
    D --> E{"Declare thành công?"}
    E -->|"Có"| C
    E -->|"Không"| R["Retry/fatal theo lỗi và cấu hình"]
    A -->|"Không"| R
~~~

Lưu ý:

1. **autoDeclare** là thuộc tính **của listener container**. Nó điều khiển việc container chủ động đề nghị khai báo lại khi cần.
2. **RabbitAdmin** cũng có vòng đời tự khai báo riêng khi connection được thiết lập. Tắt autoDeclare của container **không nhất thiết tắt** toàn bộ hành vi auto-declaration của RabbitAdmin.
3. RabbitAdmin cần được ánh xạ đúng với những declarables. Nếu nhiều RabbitAdmin mà không xác định ownership, cơ chế tự khai báo có thể không như mong đợi.
4. Việc container gọi RabbitAdmin không thể biến queue đã tồn tại với thuộc tính sai thành queue đúng; 406 vẫn có thể xảy ra.

### 5.1. Hai mô hình ownership

| Mô hình | Ai tạo queue/exchange/binding? | Hướng cấu hình |
|---|---|---|
| **Ứng dụng sở hữu topology** | RabbitAdmin/bean Queue, Exchange, Binding | Cho phép auto-declaration có kiểm soát; theo dõi 406 khi code/broker khác nhau |
| **Hạ tầng sở hữu topology** | Terraform, Helm, operator, deployment job, RabbitMQ definitions | Consumer chỉ dùng queue đã provisioning, preflight và điều khiển fatal/recovery rõ ràng |

Nếu đội hạ tầng sở hữu topology, **không nên âm thầm tạo queue mới với mặc định thiếu DLX, TTL, queue type hoặc binding** chỉ để consumer khởi động. Queue sai có thể nhận message ở đường định tuyến không đạt yêu cầu độ bền, retry và dead-letter.

### 5.2. Không để RabbitAdmin che khuất bài test missing queue

Nếu bạn khai báo:

~~~java
@Bean
public Queue ordersQueue() {
    return QueueBuilder.durable("orders.tasks.q").build();
}
~~~

và Spring Boot đã tạo RabbitAdmin tự động, bean queue có thể được active-declare **trước khi listener kiểm tra**. Khi đó thí nghiệm “queue bị thiếu thì sao” không còn kiểm tra trạng thái thiếu ban đầu, vì queue đã được tạo lại.

Muốn thử **missing queue thật sự**:

- Dùng profile/ứng dụng chỉ có **@RabbitListener(queues = "...")**, **không đăng ký bean Queue/Declarables** cho queue đó.
- Tắt **Spring Boot tự tạo AmqpAdmin** bằng cấu hình **spring.rabbitmq.dynamic=false** nếu cần, đồng thời bảo đảm không có RabbitAdmin tự tạo khác.
- Chuẩn bị một vhost phát triển riêng và xác minh queue không có trong Management UI.
- Chọn missingQueuesFatal rõ ràng để quan sát fail-fast hoặc recovery.

Cấu hình **spring.rabbitmq.dynamic=false** chỉ ngăn **Spring Boot tự tạo AmqpAdmin**; nếu ứng dụng tự khai báo một RabbitAdmin, phải quản lý vòng đời của bean đó riêng.

## 6. Thực hành A: phân biệt chính sách fail-fast và chờ khôi phục

Ví dụ này dùng **Spring Boot 3.x + Spring AMQP 3.x**, nhưng các khái niệm cũng áp dụng cho phiên bản mới hơn sau khi đối chiếu API. Chọn **SimpleMessageListenerContainer** để minh họa.

### 6.1. Maven và kết nối

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    virtual-host: app_dev
    username: learn_amqp
    password: ${RABBITMQ_PASSWORD}
    dynamic: false
    listener:
      type: simple
~~~

Trong ví dụ, **dynamic=false** kết hợp với **không khai báo Queue bean** giúp quan sát khả năng queue bị thiếu khi container start. Thực tế cần cung cấp password bằng môi trường và đảm bảo user/vhost được cấp quyền.

### 6.2. Hai container factory với hai chính sách

~~~java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ListenerPoliciesConfig {

    @Bean("strictListenerFactory")
    public SimpleRabbitListenerContainerFactory strictListenerFactory(
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMissingQueuesFatal(true);
        factory.setConcurrentConsumers(1);
        factory.setPrefetchCount(10);
        return factory;
    }

    @Bean("recoveringListenerFactory")
    public SimpleRabbitListenerContainerFactory recoveringListenerFactory(
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMissingQueuesFatal(false);
        factory.setRecoveryInterval(5_000L);
        factory.setConcurrentConsumers(1);
        factory.setPrefetchCount(10);
        return factory;
    }
}
~~~

**Hai factory không đồng nghĩa sẽ có hai consumer.** Chúng là hai lựa chọn cấu hình; một listener chỉ chọn factory qua **containerFactory**. Khi thử, chạy **một listener và một chính sách tại một thời điểm** để tránh can thiệp nhau.

Tạo listener cho queue có tên cố định:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersTaskListener {

    @RabbitListener(
            id = "ordersTaskListener",
            queues = "orders.tasks.q",
            containerFactory = "recoveringListenerFactory"
    )
    public void receive(String jobId) {
        System.out.println("Received task " + jobId);
    }
}
~~~

Để thử fail-fast, đổi **containerFactory** thành **strictListenerFactory** rồi khởi động lại. Không thay đổi queue đã tồn tại chỉ để “tạo lỗi”, mà hãy dùng một vhost/broker test nơi bạn có thể kiểm soát rõ dữ liệu.

### 6.3. Kết quả mong đợi

| Trường hợp | strictListenerFactory | recoveringListenerFactory |
|---|---|---|
| Queue tồn tại | Consumer đăng ký nhận | Consumer đăng ký nhận |
| Queue không tồn tại, broker hoạt động | Sau các lần thử, có thể làm startup fail vì missingQueuesFatal=true | Không coi missing là fatal; tiếp tục vòng recovery |
| Queue được tạo **sau** khi app chạy | Nếu app đã fail startup thì cần start lại/điều phối restart | Container đang chờ có thể khôi phục consumer |
| Sai quyền read hoặc sai vhost | Không phải đơn thuần retry missing | Không tự sửa được quyền hoặc vhost |

Quy trình:

1. Không tạo queue **orders.tasks.q** trong vhost **app_dev**.
2. Chạy thử **strictListenerFactory** và quan sát log startup, broker và container.
3. Chạy thử **recoveringListenerFactory**, quan sát việc kết nối/retry nhưng không có consumer nhận message.
4. Trước khi tạo queue đúng bằng Management UI hoặc quy trình provisioning của môi trường thử nghiệm, kiểm tra vhost và danh sách queue:
   
   ~~~bash
   rabbitmqctl list_vhosts
   rabbitmqctl list_queues -p app_dev name durable auto_delete arguments
   ~~~

   Các lệnh trên chỉ **đọc thông tin**. Sau đó mới tạo queue bằng Management UI hoặc lệnh provisioning chính thức dành cho môi trường thử nghiệm.
5. Sau khi queue được tạo với quyền phù hợp, quan sát consumer ở recovering factory tự đăng ký và bắt đầu nhận message.
6. Publish thử bằng RabbitTemplate đến **default exchange**:

   ~~~java
   rabbitTemplate.convertAndSend(
           "",
           "orders.tasks.q",
           "job-001"
   );
   ~~~

7. Xác minh listener in **Received task job-001**.

**Chú ý:** Việc queue tự xuất hiện có thể do RabbitAdmin hoặc thành phần provisioning khác. Thử nghiệm chỉ thực sự phản ánh recovery khi bạn kiểm soát được những nguồn tạo queue.

## 7. Thực hành B: mismatch queue và chính sách dừng

Phần này sử dụng **vhost phát triển riêng**, không dùng queue chứa message quan trọng. Mục tiêu là minh họa lỗi 406 và tác dụng của mismatch detection, **không** phải thay đổi queue production.

### 7.1. Tạo trước một queue với thuộc tính trái ngược

Ví dụ tạo bằng công cụ quản trị:

~~~text
Queue name: orders.tasks.strict.q
durable: false
autoDelete: false
queue type: classic
~~~

Giữ queue này không có message. Phía Spring AMQP lại khai báo:

~~~java
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class StrictQueueTopology {

    @Bean
    public Queue ordersStrictQueue() {
        return QueueBuilder
                .durable("orders.tasks.strict.q")
                .build();
    }
}
~~~

Khi RabbitAdmin active-declare queue **durable=true** trên một queue hiện có **durable=false**, broker có thể trả **406 PRECONDITION_FAILED**. Queue cũ không được âm thầm đổi sang durable.

### 7.2. Bật mismatch fatal trên container factory

~~~java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class StrictQueueCheckConfig {

    @Bean("verifiedFactory")
    public SimpleRabbitListenerContainerFactory verifiedFactory(
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMissingQueuesFatal(true);
        factory.setMismatchedQueuesFatal(true);
        factory.setConcurrentConsumers(1);
        return factory;
    }
}
~~~

Ví dụ listener:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class StrictOrdersListener {

    @RabbitListener(
            id = "strictOrdersListener",
            queues = "orders.tasks.strict.q",
            containerFactory = "verifiedFactory"
    )
    public void handle(String message) {
        System.out.println(message);
    }
}
~~~

**Điều kiện để mismatch detection hoạt động đúng:** ứng dụng cần đúng một **RabbitAdmin** có thể xử lý queue declarable trong context, hoặc container phải tham chiếu tới một RabbitAdmin phù hợp. Nếu chạy ví dụ với **spring.rabbitmq.dynamic=false** và không có RabbitAdmin tùy chỉnh, kiểm tra mismatch fatal **không có đủ điều kiện**. Vì vậy, chạy phần này trong **profile riêng** với RabbitAdmin/auto-declaration được bật.

**Mức độ fail và thời điểm exception phụ thuộc đường đi khai báo**:

- RabbitAdmin có thể gặp **406** trước khi listener tiến đến bước kiểm tra mismatch.
- Container có thể phát hiện sự không tương đương khi **mismatchedQueuesFatal=true**.
- Trong cả hai trường hợp, lỗi thật nằm ở **khai báo queue không tương đương**; việc bỏ cờ mismatch fatal không sửa được nó.

### 7.3. Khắc phục một mismatch đúng cách

1. Đọc reply-text để biết thuộc tính gây lỗi.
2. Xem queue thực tế trong **đúng vhost** và đối chiếu với Queue bean.
3. Xác định nguồn chân lý: broker provisioning hay định nghĩa ứng dụng.
4. Nếu code sai, sửa bean để **khớp** queue đúng nghiệp vụ.
5. Nếu cần thay thuộc tính **không đổi được trực tiếp**, tạo queue tên mới, thiết kế binding và chuyển backlog có kiểm soát.
6. Kiểm chứng message còn chờ và consumer đã xử lý trước khi retire queue cũ.

**Không xóa queue đang chứa dữ liệu để giải quyết 406.** Việc xóa có thể mất Ready/Unacked và gây gián đoạn các service khác.

## 8. AutoStartup và chính sách dừng có chủ đích

Có những hệ thống chỉ muốn listener chạy **sau khi** topology, database và downstream services sẵn sàng. Khi đó, dùng **autoStartup=false** để trì hoãn start, thay vì cho listener thử sai vô hạn.

### 8.1. Cấu hình từ application.yml

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        auto-startup: false
~~~

Khi cấu hình này áp dụng cho factory mặc định, listener container được tạo nhưng không tự tham gia nhận message khi context start. Ứng dụng hoặc bộ điều phối phải gọi start khi các điều kiện đã đủ.

Bạn cũng có thể chỉ định trên listener cụ thể:

~~~java
@RabbitListener(
        id = "manualOrdersListener",
        queues = "orders.tasks.q",
        autoStartup = "false"
)
public void handleManuallyStarted(String jobId) {
    System.out.println(jobId);
}
~~~

**Lưu ý:** Đây là một **listener khác** với OrdersTaskListener ở mục 6, dùng cho bài thử độc lập. Nếu bật cả hai cùng nghe một queue, chúng trở thành competing consumers.

### 8.2. Start/stop qua RabbitListenerEndpointRegistry

~~~java
import org.springframework.amqp.rabbit.listener.MessageListenerContainer;
import org.springframework.amqp.rabbit.listener.RabbitListenerEndpointRegistry;
import org.springframework.stereotype.Service;

@Service
public class ListenerLifecycleControl {
    private final RabbitListenerEndpointRegistry registry;

    public ListenerLifecycleControl(
            RabbitListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void startOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("manualOrdersListener");
        if (container == null) {
            throw new IllegalStateException("Listener ID not found");
        }
        container.start();
    }

    public void stopOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("manualOrdersListener");
        if (container != null) {
            container.stop();
        }
    }
}
~~~

**start() không tự chứng minh queue đã tồn tại hoặc consumer đã sẵn sàng**; cần quan sát events/metrics và xác nhận broker. Không gọi start/stop liên tục từ mọi request; hãy dùng quy trình lifecycle có trạng thái rõ ràng.

### 8.3. Stop bình thường, forceStop và message đang Unacked

Các listener container có thể nhận nhiều message trước khi ACK, tùy **prefetch** và chế độ xác nhận.

| Lựa chọn | Hành vi cần hiểu |
|---|---|
| **container.stop()** | Yêu cầu ngừng nhận; cách xử lý message đã prefetch phụ thuộc loại container và cấu hình |
| **forceStop=false** (mặc định trong SMLC ở các bản hiện hành) | Container thường cố xử lý các message đã prefetch trước khi dừng |
| **forceStop=true** | Có thể dừng sau message đang xử lý và để message prefetch còn lại được requeue |
| **shutdownTimeout** | Giới hạn chờ graceful shutdown |
| **forceCloseChannel** | Khi consumer không dừng trong thời hạn, đóng channel có thể khiến Unacked được broker requeue |

Đây là các **điều khiển lifecycle**, không phải policy dành cho missing queue. Đừng nhầm **forceStop** với **missingQueuesFatal**. Khi triển khai rolling deployment, cần bảo đảm consumer không ACK quá sớm, idempotency khi redelivery và đủ thời gian để job đang chạy hoàn tất.

## 9. Nếu container đang nghe nhiều queue, mất một queue thì sao?

Giả sử một listener container được cấu hình với hai queue:

~~~java
@RabbitListener(
        id = "multiQueueListener",
        queues = {"orders.tasks.q", "orders.audit.q"},
        containerFactory = "recoveringListenerFactory"
)
public void process(String body) {
    System.out.println(body);
}
~~~

Nếu **orders.tasks.q** tồn tại nhưng **orders.audit.q** tạm thiếu, container có thể **tiếp tục tiêu thụ queue đang có** và định kỳ passive-check queue bị thiếu. Không nên khái quát rằng chỉ một missing queue làm mọi listener trong ứng dụng dừng ngay.

Spring AMQP cho phép thêm/xóa queue ở runtime:

- **SimpleMessageListenerContainer** có thể tái tạo các consumer khi cấu hình queue thay đổi.
- **DirectMessageListenerContainer** quản lý consumer của từng queue riêng, giảm ảnh hưởng tới queue khác.
- Nếu một queue bị xóa vĩnh viễn, phải **cập nhật cấu hình listener** thay vì để container liên tục tìm một queue không còn được sử dụng.

Trong thực hành, một container đa queue có thể tạo **partial availability**: một loại message vẫn được xử lý, loại khác không. Đối với nghiệp vụ quan trọng, nên có **metrics/alert theo từng queue**, không chỉ một cờ “container running”.

## 10. DMLC, SMLC và chính sách recovery

SMLC và DMLC đều hỗ trợ các cơ chế quản lý queue và consumer, nhưng có sự khác biệt khi consumer gặp lỗi và khi thêm/xóa queue.

| Điều kiện | SMLC | DMLC |
|---|---|---|
| Retry lỗi non-fatal | **recoveryInterval/recoveryBackOff** | **monitorInterval** giám sát và tái tạo consumer |
| Consumer concurrency | concurrentConsumers / maxConcurrentConsumers | consumersPerQueue |
| Nhiều queue bị cấu hình thiếu một phần | Có thể tiếp tục queue còn tồn tại | Có thể phục hồi consumer của queue thiếu độc lập |
| Thay đổi cấu hình queue runtime | Có thể recycle consumers | Có thể cập nhật consumer của queue đích |
| Missing queues fatal | Có | Có |
| Mismatched queues fatal | Có | Có |

Để chọn DMLC trong Spring Boot:

~~~yaml
spring:
  rabbitmq:
    listener:
      type: direct
      direct:
        missing-queues-fatal: false
        consumers-per-queue: 2
~~~

Đoạn này chỉ minh họa cách chọn **DMLC** cùng chính sách missing queue. Tránh đồng thời đặt các tùy chọn concurrency dành riêng cho SMLC và kỳ vọng chúng điều khiển DMLC. **mismatchedQueuesFatal** có thể cấu hình qua factory/container hoặc topology validation có kiểm soát; không giả định mọi thuộc tính Java đều có đối ứng trực tiếp trong Boot YAML.

Cần đối chiếu phiên bản Spring Boot cụ thể: property names và hỗ trợ API thay đổi theo release.

## 11. Đọc trạng thái container từ Spring application events

Spring AMQP có application events cho các tình huống như **MissingQueueEvent**, **ListenerContainerConsumerFailedEvent**, consumer bắt đầu/khôi phục và listener idle.

Ví dụ quan sát:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.listener.ListenerContainerConsumerFailedEvent;
import org.springframework.amqp.rabbit.listener.MissingQueueEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ListenerEventsLogger {
    private static final Logger log =
            LoggerFactory.getLogger(ListenerEventsLogger.class);

    @EventListener
    public void missingQueue(MissingQueueEvent event) {
        log.warn("Missing RabbitMQ queue: {}", event.getQueue());
    }

    @EventListener
    public void consumerFailed(ListenerContainerConsumerFailedEvent event) {
        log.error(
                "Listener consumer failed: fatal={}, reason={}",
                event.isFatal(),
                event.getReason(),
                event.getThrowable()
        );
    }
}
~~~

Đây là quan sát, **không tự sửa queue**. Các sự kiện fatal/non-fatal giúp phân biệt lỗi khiến container ngừng với lỗi mà container sẽ thử phục hồi.

Ghi log và tăng metric theo **queue, listener id, vhost, error type và fatal flag**. Tránh ghi mỗi một log của từng vòng retry mà không có giới hạn để khỏi làm log quá tải khi queue thiếu lâu dài.

### 11.1. Metrics và readiness

| Chỉ số | Ý nghĩa |
|---|---|
| **Queue exists** | Tài nguyên có tồn tại trong đúng vhost? |
| **Consumer count** | Có consumer đăng ký trên broker? |
| **Container running** | Container đã được start? |
| **Listener failure events** | Có lỗi fatal/non-fatal mới xảy ra? |
| **Queue Ready** | Message chưa được giao đang tồn đọng? |
| **Queue Unacked** | Có message đang giao nhưng chưa ACK? |
| **Oldest message age** (nếu đo được) | Message cũ nhất đang chờ bao lâu? |
| **Mismatch / 406 count** | Topology đã drift khỏi định nghĩa chưa? |
| **Missing / 404 count** | Queue nào liên tục không tìm thấy? |

**Container.isRunning() không tự chứng minh consumer của mọi queue đã đăng ký thành công.** Readiness đối với dịch vụ xử lý message quan trọng nên kiểm tra trạng thái queue/consumer theo hợp đồng, hoặc dựa trên sự kiện xác nhận consumer hoạt động cùng metrics broker.

Nếu bạn dùng **missingQueuesFatal=false** để cho app chạy trong khi queue chưa có, phải bảo đảm việc app được xem là ready **không đánh lừa hệ thống điều phối** rằng mọi chức năng nghiệp vụ đã sẵn sàng.

## 12. Quy trình chẩn đoán từ log đến nguyên nhân gốc

~~~mermaid
flowchart TD
    A["Listener không nhận message"] --> B{"Có connection tới đúng RabbitMQ/vhost?"}
    B -->|"Không"| C["Sửa host/port/vhost/TLS/user/quyền"]
    B -->|"Có"| D{"Queue tồn tại?"}
    D -->|"Không"| E["404 missing queue<br/>xem provisioning/RabbitAdmin"]
    D -->|"Có"| F{"Queue properties đúng hợp đồng?"}
    F -->|"Không"| G["406 / topology mismatch<br/>sửa định nghĩa hoặc migration"]
    F -->|"Có"| H{"Consumer count > 0?"}
    H -->|"Không"| I["Container lifecycle, fatal/recovery, quyền"]
    H -->|"Có"| J["Kiểm tra exchange/binding,<br/>Ready/Unacked, ACK và handler"]
~~~

Các bước thực hiện:

1. Ghi lại **listener ID**, tên queue, exchange, routing key, vhost và thời gian lỗi.
2. Xem **RabbitMQ Management UI** trong **đúng vhost**.
3. Xác nhận queue tồn tại, durable/autoDelete/type/arguments đúng contract.
4. Xem log **RabbitAdmin**, **listener container** và lỗi channel đầu tiên; đừng chỉ đọc stack trace cuối.
5. Nếu là **404**, xác định vì sao queue thiếu; không tự tạo queue sai hợp đồng.
6. Nếu là **406**, đối chiếu thuộc tính broker và code; không xóa queue đang có message.
7. Nếu queue đúng nhưng listener dừng, xem **missingQueuesFatal/mismatchedQueuesFatal**, autoStartup và sự kiện fatal.
8. Nếu consumer chạy nhưng không nhận message, kiểm tra producer RabbitTemplate, binding, Ready/Unacked và permission.

Các lệnh CLI chỉ đọc dưới đây hữu ích khi có quyền quản trị broker:

~~~bash
rabbitmq-diagnostics server_version
rabbitmqctl list_vhosts
rabbitmqctl list_queues -p app_dev name durable auto_delete arguments consumers messages_ready messages_unacknowledged
rabbitmqctl list_bindings -p app_dev source_name destination_name routing_key
~~~

Lưu ý RabbitMQ CLI có thể chạy trên node broker hoặc qua môi trường container tùy hạ tầng. Không dùng lệnh xóa queue để “kiểm tra” trong hệ thống đang mang dữ liệu.

### 12.1. Bảng nhanh: triệu chứng và chính sách liên quan

| Triệu chứng | Nguyên nhân/cấu hình cần xét |
|---|---|
| **404 NOT_FOUND khi queueDeclarePassive** | Queue không tồn tại trong vhost, sai tên hoặc bị xóa |
| **406 PRECONDITION_FAILED khi RabbitAdmin declare** | Queue cùng tên sai durable/type/arguments |
| Application không khởi động, queue thiếu | missingQueuesFatal=true cùng tình huống all queues unavailable |
| Application chạy nhưng không consumer | missingQueuesFatal=false đang recovery, autoStartup=false, hoặc lỗi khác |
| Container dừng sau khi mất queue | Fatal policy và các lần retry/recovery thất bại |
| Một queue thiếu nhưng listener vẫn xử lý queue khác | Partial availability trong multi-queue listener |
| Mismatch flag false mà vẫn 406 | Broker luôn kiểm tra active declaration |
| Container running nhưng backlog tăng | Consumer không đủ, listener lỗi, prefetch/ACK, queue routing |
| Không thấy MissingQueueEvent lúc startup của bean @Lazy | Giới hạn kiểm tra ở lazy initialization, cần preflight riêng |

## 13. Chọn chính sách cho từng loại workload

| Bối cảnh | Chính sách nên cân nhắc | Lý do |
|---|---|---|
| Queue **bắt buộc** cho một chức năng chính | Fail-fast + readiness nghiêm ngặt, mismatch detection | Không cho dịch vụ nhận traffic khi topology chưa đúng |
| Queue do hạ tầng tạo sau khi app start | missingQueuesFatal=false + cảnh báo và deadline provisioning | Cho phép recover mà không cần khởi động lại liên tục |
| Queue auto-delete/ephemeral | Recovery + RabbitAdmin phù hợp | Queue có thể biến mất theo lifecycle |
| Queue consumer phụ trợ, không cản trở chức năng chính | Container riêng, recovery riêng, giám sát partial outage | Không kéo sập toàn bộ chức năng không liên quan |
| Queue dùng để xử lý tài chính quan trọng | Fail-fast cho schema/topology drift, migration có kiểm soát | Sai DLX/TTL/type có thể gây mất hoặc trễ message |
| Nhiều queue và nhiều bounded context | Tách listener container/factory theo SLA | Tránh một queue thiếu làm khó xác định trạng thái toàn hệ thống |

### 13.1. Một chính sách hợp lý cần có những gì?

Không chỉ đặt các flag true/false, hãy ghi rõ:

- Ai **sở hữu topology** và nguồn định nghĩa chính thức.
- Queue nào là **bắt buộc** để service được xem là ready.
- Queue nào được phép vắng mặt tạm thời và trong **bao lâu**.
- Có **autoDeclare** hay hoàn toàn provisioning bên ngoài.
- Khi lỗi **404, 406, ACCESS_REFUSED** thì ai được cảnh báo, có tự retry không.
- Khi recovery vượt SLO thì container dừng, deployment restart hay cần can thiệp.
- Khi phải đổi queue type/arguments thì có kế hoạch **migration** và bảo toàn backlog thế nào.

**Retry vô hạn không có cảnh báo** có thể che giấu một hệ thống ngừng xử lý message hàng giờ. **Fail-fast mọi queue** lại có thể làm một thành phần phụ trợ kéo sập cả dịch vụ. Cấu hình đúng phải theo mức độ quan trọng của từng nghiệp vụ.

## 14. Bài thực hành có kiểm soát

Chỉ thực hiện các thí nghiệm với RabbitMQ/vhost **dành riêng cho phát triển**. Không xóa hoặc chỉnh queue đang có message quan trọng.

### Bài A — Missing queue và fail-fast

1. Đặt **spring.rabbitmq.dynamic=false**, không khai báo Queue bean cho **orders.tasks.q**.
2. Dùng **strictListenerFactory**.
3. Khởi động listener khi queue chưa tồn tại.
4. Ghi lại log 404, số lần thử và kết quả startup/container.
5. Tạo queue đúng và thử lại, đối chiếu kết quả.

### Bài B — Missing queue và tự khôi phục

1. Dùng **recoveringListenerFactory** với **missingQueuesFatal=false**.
2. Khởi động khi queue chưa tồn tại.
3. Quan sát app không coi missing là fatal nhưng **không có consumer xử lý message**.
4. Provision queue sau đó và quan sát consumer khôi phục.
5. Publish **job-001**, xác nhận listener nhận message và queue Ready giảm.

### Bài C — Mismatch và lỗi 406

1. Tạo queue **orders.tasks.strict.q** có **durable=false**, không có message.
2. Chạy profile có Queue bean **durable=true** và một RabbitAdmin phù hợp.
3. Quan sát lỗi **PRECONDITION_FAILED / inequivalent arg**.
4. Kiểm tra queue trên broker vẫn giữ durable ban đầu.
5. Sửa định nghĩa/provisioning cho nhất quán mà **không xóa queue production**.
6. Giải thích vì sao **mismatchedQueuesFatal=false** không tắt kiểm tra của RabbitMQ.

### Bài D — Multi-queue partial availability

1. Tạo **orders.tasks.q**, không tạo **orders.audit.q**.
2. Dùng listener đa queue ở mục 9 cùng factory recovery.
3. Gửi message vào tasks, kiểm tra vẫn nhận được.
4. Tạo audit queue và quan sát listener bắt đầu nhận message từ cả hai.
5. Ghi metrics riêng cho từng queue; giải thích tại sao một cờ running không đủ.

### Bài E — Điều khiển lifecycle

1. Đặt **@RabbitListener(autoStartup="false")** cho một listener thử nghiệm.
2. Khởi động ứng dụng, xác minh chưa có consumer.
3. Gọi **RabbitListenerEndpointRegistry.getListenerContainer(id).start()** sau khi queue tồn tại.
4. Quan sát consumer tăng; publish message và kiểm tra xử lý.
5. Gọi stop khi còn backlog; quan sát Ready/Unacked và cách message được xử lý lại nếu có.

### Câu hỏi tự đánh giá

1. Vì sao **404 NOT_FOUND** khi passive declare khác **406 PRECONDITION_FAILED** khi active declare?
2. **missingQueuesFatal=true** có luôn dừng toàn bộ container khi thiếu đúng một trong ba queue không?
3. Vì sao bật **missingQueuesFatal=false** có thể làm ứng dụng trông healthy nhưng vẫn không xử lý được message?
4. Vì sao đặt **mismatchedQueuesFatal=false** không cho phép đổi durable queue bằng khai báo lại?
5. RabbitAdmin tự tạo queue có thể khiến bài kiểm tra missing queue bị sai như thế nào?
6. Khi nào chọn **autoStartup=false** thay vì để container tự recover?
7. Tại sao cần kiểm tra **Consumer count** cùng với **container running** khi đánh giá readiness?
8. Nếu một queue đang có message mà cần chuyển classic sang quorum, vì sao phải có migration?

## 15. Tổng kết

- **Listener container** quản lý vòng đời consumer, passive queue checks, ACK và recovery; **RabbitAdmin** quản lý việc khai báo tài nguyên, dù container có thể yêu cầu khai báo lại.
- **Missing queue** thường biểu hiện 404 ở passive declaration; **queue sai thuộc tính** thường biểu hiện 406 khi active declaration không tương đương.
- **missingQueuesFatal=true** mặc định xử lý việc **không có queue khả dụng** là fatal sau các lần thử; **false** cho phép recovery tiếp tục.
- **mismatchedQueuesFatal=false** là mặc định, nhưng không tắt khả năng RabbitMQ từ chối active declare sai thuộc tính. Bật **true** cần RabbitAdmin phù hợp và hiểu phạm vi kiểm tra.
- **autoDeclare** không đồng nghĩa với mọi hành vi tự khai báo của RabbitAdmin; **autoStartup** chỉ điều khiển thời điểm container start.
- **SMLC** phục hồi theo recovery interval/backoff; **DMLC** giám sát consumer theo monitor interval và quản lý queue riêng linh hoạt hơn.
- **Container running** không chứng minh mọi queue đã có consumer. Cần events, metrics và readiness theo từng queue/bounded context.
- Khi topology sai, **sửa định nghĩa hoặc migration có kiểm soát** thay vì tắt mọi cờ fatal hoặc xóa queue; đây là nền tảng cho một luồng RabbitTemplate/@RabbitListener có retry, dead-letter và độ tin cậy thực tế.

### Tài liệu tham khảo chính thức

- [Spring AMQP — Message Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): missingQueuesFatal, mismatchedQueuesFatal, autoDeclare, autoStartup và recovery.
- [Spring AMQP — Listener Container Queues](https://docs.spring.io/spring-amqp/reference/amqp/listener-queues.html): nhiều queue, thiếu một phần và thêm/xóa queue runtime.
- [Spring AMQP — Choosing a Container](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/choose-container.html): so sánh SMLC/DMLC.
- [Spring AMQP — Consumer Events](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/consumer-events.html): ListenerContainerConsumerFailedEvent và MissingQueueEvent.
- [Spring Boot — AMQP](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): cấu hình @RabbitListener, default factory và listener type.
- [RabbitMQ — Queues](https://www.rabbitmq.com/docs/queues): khai báo queue, vòng đời, thuộc tính và consumer.
