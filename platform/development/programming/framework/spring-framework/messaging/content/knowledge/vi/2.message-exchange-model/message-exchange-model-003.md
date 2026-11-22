# Hàng đợi công việc và nhiều bên nhận cạnh tranh

## 1. Bài toán và mục tiêu

Một hệ thống nhận nhiều công việc nền như gửi email, xử lý ảnh, tạo báo cáo, đồng bộ dữ liệu hoặc tính toán hóa đơn. Nếu thực hiện tất cả ngay trong luồng HTTP, thời gian phản hồi sẽ phụ thuộc vào thời gian xử lý của từng công việc. Khi tải tăng, ứng dụng dễ hết thread, timeout hoặc làm chậm các chức năng tương tác trực tiếp với người dùng.

Work queue (hàng đợi công việc) tách thời điểm tiếp nhận yêu cầu khỏi thời điểm thực thi. Producer gửi một thông điệp mô tả công việc đến broker; broker lưu thông điệp trong queue; một consumer lấy thông điệp ra, xử lý rồi xác nhận hoàn tất. Có thể chạy nhiều consumer cùng nghe một queue để chia tải. Mô hình này thường được gọi là competing consumers (các bên nhận cạnh tranh).

Sau bài học, người đọc có thể:

- Phân biệt work queue với publish/subscribe và hiểu vì sao một thông điệp trong competing consumers thường chỉ được giao cho một consumer tại một thời điểm.
- Giải thích cách broker phân phối thông điệp, prefetch, acknowledgement và redelivery.
- Tạo một queue bền vững và nhiều consumer đồng thời bằng Spring AMQP.
- Ước lượng ảnh hưởng của số consumer, thời gian xử lý và prefetch đến throughput.
- Thiết kế xử lý lỗi, retry, dead-letter queue, idempotency và thứ tự xử lý.
- Nhận biết giới hạn của bảo đảm giao nhận và chọn cách triển khai phù hợp với nghiệp vụ.

## 2. Work queue và competing consumers

### 2.1. Các thành phần

Một work queue có ba vai trò chính:

1. **Producer** tạo công việc và gửi message đến broker. Producer không cần biết consumer nào sẽ xử lý.
2. **Broker** nhận message, định tuyến vào queue và quản lý việc giao message cho consumer.
3. **Consumer** nhận message, thực hiện công việc và xác nhận kết quả theo giao thức của broker.

Ví dụ, một dịch vụ đặt hàng có thể gửi message GenerateInvoice vào queue invoice.work. Nhiều worker chạy cùng một ứng dụng hoặc nhiều bản sao ứng dụng có thể cùng đăng ký consumer trên queue đó.

~~~mermaid
flowchart LR
    P[Producer] --> B[Message broker]
    B --> Q[(invoice.work)]
    Q --> C1[Consumer A]
    Q --> C2[Consumer B]
    Q --> C3[Consumer C]
~~~

Các consumer cùng đọc một queue là những người nhận cạnh tranh. Broker phân phối mỗi lần giao message cho một consumer. Khi một consumer đang xử lý message, broker thường giữ trạng thái message chưa được xác nhận; message đó chưa được coi là hoàn tất. Khi consumer xác nhận thành công, broker mới có thể loại message đã xử lý khỏi queue.

### 2.2. Một message cho một consumer hay cho mọi subscriber?

Cần phân biệt hai mô hình:

| Mô hình | Cách phân phối | Trường hợp sử dụng |
|---|---|---|
| Competing consumers trên một queue | Mỗi message được giao cho một consumer trong nhóm; các consumer chia nhau công việc | Gửi email, xử lý ảnh, tạo báo cáo, xử lý đơn hàng |
| Publish/subscribe với nhiều queue | Một sự kiện được phát đến nhiều queue độc lập; mỗi nhóm subscriber nhận bản sao của sự kiện | Một sự kiện OrderCreated cần cập nhật kho, gửi email và ghi dữ liệu phân tích |

Nếu ba consumer cùng nghe một queue công việc, một message không tự động được xử lý ba lần. Nếu cần ba hệ thống đều nhận sự kiện, hãy định tuyến sự kiện đến ba queue hoặc ba subscription độc lập. Không nên tạo ba consumer cạnh tranh rồi kỳ vọng mỗi consumer đều nhận mọi message.

### 2.3. Vì sao gọi là “cạnh tranh”?

Các consumer cùng cạnh tranh để nhận phần việc tiếp theo trong queue. Khi một consumer rảnh và broker có thể giao message, consumer đó nhận message. Consumer chậm sẽ có ít cơ hội nhận message mới hơn nếu broker giới hạn số message chưa xác nhận bằng prefetch thấp.

Cạnh tranh ở đây là cơ chế chia tải, không phải khóa độc quyền ở tầng nghiệp vụ. Nó không đảm bảo hai message liên quan đến cùng một đơn hàng sẽ được xử lý theo đúng thứ tự, cũng không ngăn hai công việc khác nhau cùng cập nhật một bản ghi. Những ràng buộc đó cần được giải quyết ở tầng dữ liệu hoặc cách phân vùng message.

## 3. Vòng đời giao nhận message

Một luồng xử lý phổ biến gồm các bước:

1. Producer tạo message có định danh và dữ liệu cần thiết.
2. Producer gửi message đến exchange hoặc địa chỉ định tuyến của broker.
3. Broker định tuyến message vào queue.
4. Broker giao message cho một consumer còn khả năng nhận thêm việc.
5. Consumer xác thực dữ liệu, thực hiện nghiệp vụ và ghi kết quả.
6. Khi xử lý thành công, consumer acknowledgement (ack) message.
7. Broker loại message đã được ack khỏi trạng thái chờ xử lý.

Nếu consumer chết hoặc mất kết nối trước khi ack, broker có thể giao lại message cho consumer khác. Điều này giúp tránh mất việc khi worker gặp sự cố, nhưng tạo ra khả năng một message được xử lý nhiều lần.

### 3.1. Acknowledgement

Acknowledgement là xác nhận từ consumer rằng một message đã được xử lý theo chính sách giao nhận.

Với Spring AMQP, listener container thường dùng chế độ xác nhận AUTO: container ack sau khi phương thức listener kết thúc thành công. Nếu listener ném exception, container xử lý việc reject/nack theo cấu hình. Chế độ MANUAL cho phép ứng dụng chủ động ack hoặc nack, nhưng cũng làm tăng trách nhiệm quản lý trạng thái và xử lý mọi nhánh lỗi.

Không nên ack ngay khi vừa nhận message nếu công việc chưa hoàn tất. Nếu worker ack trước, sau đó chết giữa chừng, broker tin rằng công việc đã xong và không giao lại. Ngược lại, nếu nghiệp vụ đã commit vào cơ sở dữ liệu nhưng worker chết trước khi ack, broker có thể giao lại message. Vì vậy, handler phải chịu được việc chạy lặp.

### 3.2. At-most-once, at-least-once và exactly-once

- **At-most-once**: message không được giao lại; có thể mất message nếu consumer lỗi sau khi nhận nhưng trước khi hoàn tất.
- **At-least-once**: message được giao lại khi chưa có xác nhận thành công; giảm nguy cơ mất việc nhưng có thể tạo bản giao trùng.
- **Exactly-once**: nghiệp vụ có hiệu lực đúng một lần. Không thể suy ra bảo đảm này chỉ từ việc dùng queue hoặc ack. Một hệ thống có thể giao message nhiều lần nhưng vẫn tạo hiệu ứng nghiệp vụ một lần nhờ idempotency hoặc deduplication.

Trong đa số hệ thống xử lý công việc, at-least-once kết hợp với handler idempotent là lựa chọn thực tế. Cần thiết kế theo khả năng redelivery ngay từ đầu.

## 4. Chia tải, concurrency và prefetch

### 4.1. Tăng số consumer

Giả sử một công việc mất trung bình 2 giây. Một consumer xử lý tuần tự có năng lực lý thuyết khoảng 0,5 công việc/giây. Ba consumer có thể xử lý song song khoảng 1,5 công việc/giây nếu broker, CPU, database và dịch vụ phụ trợ đều đủ năng lực.

Đây chỉ là ước lượng lý tưởng. Throughput thực tế còn phụ thuộc vào:

- Thời gian xử lý trung bình và độ phân tán thời gian xử lý.
- Số consumer đang hoạt động và số thread mà mỗi consumer sử dụng.
- Prefetch và số message đang ở trạng thái unacknowledged.
- Khả năng của database, HTTP API, filesystem hoặc dịch vụ bên ngoài.
- Chi phí serialize/deserialize, mạng và kết nối broker.
- Retry, redelivery, lock và tranh chấp tài nguyên.

Tăng consumer không phải lúc nào cũng tăng throughput. Nếu tất cả worker cùng ghi vào một bảng có khóa nóng hoặc gọi một API bị giới hạn tốc độ, tăng worker chỉ làm tăng contention, timeout và số lần retry.

### 4.2. Prefetch

Prefetch giới hạn số message broker có thể giao cho một consumer nhưng consumer chưa ack. Với prefetch bằng 1, mỗi consumer chỉ giữ tối đa một message chưa xác nhận. Sau khi hoàn tất và ack, consumer mới nhận message tiếp theo. Cách này thường giúp phân phối tương đối đều khi thời gian xử lý mỗi message khác nhau.

Prefetch cao có thể tăng throughput vì giảm thời gian chờ giao message, nhưng có các đánh đổi:

- Một consumer nhanh có thể giữ nhiều message trong bộ nhớ trong khi các consumer khác không có việc.
- Message đã giao nhưng chưa xử lý xong không còn nằm trong phần ready của queue; số liệu queue depth có thể làm người vận hành đánh giá thấp lượng công việc đang tồn đọng.
- Khi consumer chết, nhiều message chưa ack có thể bị redeliver cùng lúc.
- Tăng prefetch làm tăng bộ nhớ và số công việc đang bay (in-flight).

Không có một giá trị prefetch tối ưu cho mọi hệ thống. Với công việc dài hoặc thời gian xử lý không đồng đều, bắt đầu bằng 1 là cách dễ quan sát. Với công việc ngắn, đồng đều và có thể xử lý theo lô, có thể tăng dần rồi đo throughput, độ trễ và bộ nhớ.

### 4.3. Concurrency của Spring listener

Spring AMQP có thể tạo nhiều consumer cho cùng một listener endpoint. Thuộc tính concurrency của @RabbitListener xác định số consumer đồng thời ban đầu. Khi chạy nhiều instance ứng dụng, tổng số consumer là tổng consumer trên tất cả instance.

Ví dụ: 4 instance, mỗi instance có concurrency 3, tạo khoảng 12 consumer trên cùng queue. Hãy tính tổng này khi giới hạn kết nối, CPU, database pool và quota của dịch vụ ngoài. Không nên chỉ nhìn số instance mà bỏ qua số consumer bên trong từng instance.

## 5. Ví dụ chạy được với Spring AMQP và RabbitMQ

Ví dụ dưới đây tạo một queue bền vững tên demo.work.queue, gửi 12 công việc và chạy ba consumer cạnh tranh trên queue đó. Mỗi consumer giả lập xử lý trong 700 ms. Chương trình dùng Java 17 và Spring Boot 3.3.13.

### 5.1. Cấu trúc dự án

~~~text
work-queue-demo/
├── compose.yaml
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/workqueue/
        │       ├── WorkQueueApplication.java
        │       ├── WorkQueueConfig.java
        │       ├── WorkPublisher.java
        │       └── WorkConsumer.java
        └── resources/
            └── application.properties
~~~

### 5.2. Khởi chạy RabbitMQ

Tạo file compose.yaml:

~~~yaml
services:
  rabbitmq:
    image: rabbitmq:3.13-management
    container_name: work-queue-rabbitmq
    environment:
      RABBITMQ_DEFAULT_USER: demo
      RABBITMQ_DEFAULT_PASS: demo123
    ports:
      - "5672:5672"
      - "15672:15672"
~~~

Tài khoản demo chỉ dành cho môi trường học tập cục bộ. Không dùng mật khẩu này trong môi trường thật.

Khởi chạy broker:

~~~bash
docker compose up -d
~~~

RabbitMQ AMQP lắng nghe ở cổng 5672; trang quản trị mặc định ở http://localhost:15672 với tài khoản demo và mật khẩu demo123.

### 5.3. Khai báo Maven dependency

Tạo file pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>work-queue-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-amqp</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

spring-boot-starter-amqp cung cấp Spring AMQP, RabbitTemplate, listener container và tích hợp cấu hình với Spring Boot.

### 5.4. Cấu hình kết nối và listener

Tạo src/main/resources/application.properties:

~~~properties
spring.application.name=work-queue-demo

spring.rabbitmq.host=localhost
spring.rabbitmq.port=5672
spring.rabbitmq.username=demo
spring.rabbitmq.password=demo123

# Mỗi consumer chỉ giữ tối đa một message chưa ack.
spring.rabbitmq.listener.simple.prefetch=1
~~~

Prefetch được đặt bằng 1 để dễ quan sát việc chia công việc giữa ba consumer. Ví dụ dùng acknowledgement mặc định của listener container: listener kết thúc bình thường thì message được ack.

### 5.5. Khai báo queue

Tạo WorkQueueConfig.java:

~~~java
package com.example.workqueue;

import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class WorkQueueConfig {

    public static final String WORK_QUEUE = "demo.work.queue";

    @Bean
    Queue workQueue() {
        return QueueBuilder.durable(WORK_QUEUE).build();
    }
}
~~~

durable(true) giữ khai báo queue qua lần broker khởi động lại. Điều này không tự động bảo đảm mọi message đều bền vững: độ bền của queue và delivery mode của message là hai thuộc tính riêng. Hệ thống production còn cần publisher confirms và chính sách lưu trữ phù hợp.

### 5.6. Ứng dụng Spring Boot

Tạo WorkQueueApplication.java:

~~~java
package com.example.workqueue;

import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@EnableRabbit
public class WorkQueueApplication {

    public static void main(String[] args) {
        SpringApplication.run(WorkQueueApplication.class, args);
    }
}
~~~

@EnableRabbit bật xử lý các phương thức có @RabbitListener.

### 5.7. Consumer cạnh tranh

Tạo WorkConsumer.java:

~~~java
package com.example.workqueue;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class WorkConsumer {

    @RabbitListener(
        queues = WorkQueueConfig.WORK_QUEUE,
        concurrency = "3"
    )
    public void handle(String task) throws InterruptedException {
        String worker = Thread.currentThread().getName();

        System.out.printf("%s nhận %s%n", worker, task);
        Thread.sleep(700);
        System.out.printf("%s hoàn tất %s%n", worker, task);
    }
}
~~~

concurrency = "3" yêu cầu listener container tạo ba consumer. Cả ba cùng đăng ký trên demo.work.queue; broker phân phối message cho một consumer tại mỗi lần giao. Thread.sleep chỉ mô phỏng công việc tốn thời gian; không dùng cách này để chờ trong mã nghiệp vụ thật.

### 5.8. Producer gửi công việc

Tạo WorkPublisher.java:

~~~java
package com.example.workqueue;

import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class WorkPublisher implements CommandLineRunner {

    private final RabbitTemplate rabbitTemplate;

    public WorkPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    @Override
    public void run(String... args) {
        for (int i = 1; i <= 12; i++) {
            String task = "task-" + i;
            rabbitTemplate.convertAndSend(
                WorkQueueConfig.WORK_QUEUE,
                task
            );
            System.out.println("Đã gửi " + task);
        }
    }
}
~~~

Khi dùng overload convertAndSend(routingKey, message) của RabbitTemplate, message được gửi qua default exchange với routing key là tên queue. Queue đã được khai báo bằng bean ở bước trước.

### 5.9. Chạy chương trình

Yêu cầu: JDK 17+, Maven và Docker Compose.

~~~bash
docker compose up -d
mvn spring-boot:run
~~~

Trong log sẽ có các dòng gửi, nhận và hoàn tất công việc. Tên thread thực tế do Spring tạo ra; thứ tự message giữa các worker phụ thuộc lịch chạy và thời gian xử lý. Có thể thấy một worker nhận task-1, worker khác nhận task-2, worker còn lại nhận task-3; sau khi một worker ack công việc, nó có thể nhận message tiếp theo.

Không dùng một thứ tự log cụ thể làm tiêu chí đúng duy nhất. Tiêu chí của ví dụ là cả 12 message được xử lý, tại một thời điểm có thể có tối đa ba listener xử lý đồng thời, và một message chỉ được giao cho một consumer trong nhóm tại mỗi lần giao.

Dừng ứng dụng bằng Ctrl+C; dừng broker khi không cần nữa:

~~~bash
docker compose down
~~~

## 6. Xử lý lỗi và message được giao lại

### 6.1. Consumer chết giữa chừng

Giả sử consumer nhận task-7, bắt đầu cập nhật dữ liệu rồi tiến trình bị dừng trước khi ack. Broker phát hiện kết nối consumer đã mất và có thể đưa message trở lại trạng thái có thể giao. Một consumer khác có thể nhận lại task-7.

Đây là hành vi cần thiết để phục hồi, nhưng nó cũng có nghĩa handler phải chấp nhận redelivery. Đừng giả định một message chỉ xuất hiện đúng một lần trong toàn bộ vòng đời.

### 6.2. Phân loại lỗi

Không phải lỗi nào cũng nên retry:

- **Lỗi tạm thời**: timeout mạng, dịch vụ ngoài tạm unavailable, deadlock có thể phục hồi. Có thể retry với backoff.
- **Lỗi dữ liệu hoặc nghiệp vụ vĩnh viễn**: thiếu trường bắt buộc, mã trạng thái không hợp lệ, tài khoản không tồn tại. Retry vô hạn không sửa được dữ liệu.
- **Lỗi hệ thống cần điều tra**: lỗi mapping, bug trong code, schema không tương thích. Cần log đủ ngữ cảnh và giới hạn số lần thử.

Với RabbitMQ, việc reject message có thể requeue hoặc dead-letter tùy cờ reject và cấu hình queue. Cấu hình requeue mặc định không phải một chiến lược retry hoàn chỉnh. Nếu message lỗi cứ được requeue ngay lập tức, consumer có thể nhận lại cùng message liên tục, gây vòng lặp nóng và làm queue không tiến triển.

### 6.3. Retry có giới hạn và dead-letter queue

Một thiết kế production thường có:

1. Giới hạn số lần thử.
2. Khoảng nghỉ tăng dần giữa các lần thử, chẳng hạn 1 giây, 5 giây, 30 giây.
3. Dead-letter exchange/queue (DLX/DLQ) cho message đã hết lượt hoặc không thể xử lý.
4. Công cụ quan sát và quy trình kiểm tra, sửa dữ liệu, rồi phát lại message có kiểm soát.

DLQ là nơi cách ly message lỗi để điều tra. Nó không tự sửa message và không nên được coi là nơi lưu trữ vô thời hạn. Cần đặt cảnh báo khi DLQ tăng, xác định ai xử lý, cách replay và cách tránh phát lại message đã tạo hiệu ứng nghiệp vụ.

### 6.4. Ví dụ cấu hình DLQ ở mức queue

Với RabbitMQ, có thể khai báo dead-letter exchange và queue riêng. Đoạn cấu hình dưới đây minh họa cách liên kết queue công việc với DLX:

~~~java
@Bean
DirectExchange deadLetterExchange() {
    return new DirectExchange("demo.work.dlx");
}

@Bean
Queue deadLetterQueue() {
    return QueueBuilder.durable("demo.work.dead").build();
}

@Bean
Binding deadLetterBinding(
        Queue deadLetterQueue,
        DirectExchange deadLetterExchange) {
    return BindingBuilder.bind(deadLetterQueue)
        .to(deadLetterExchange)
        .with("demo.work.dead");
}

@Bean
Queue workQueue() {
    return QueueBuilder.durable(WorkQueueConfig.WORK_QUEUE)
        .deadLetterExchange("demo.work.dlx")
        .deadLetterRoutingKey("demo.work.dead")
        .build();
}
~~~

Đây là đoạn minh họa bổ sung cho cấu hình queue ở ví dụ trước; khi dùng, thay bean workQueue() cũ bằng phiên bản có DLX và bổ sung các import DirectExchange, Binding, BindingBuilder. Muốn giới hạn số lần retry, cần kết hợp retry policy hoặc các queue retry có TTL và dead-letter routing. Chỉ khai báo DLQ chưa tự tạo giới hạn số lần thử.

## 7. Idempotency: xử lý lặp mà không tạo hiệu ứng lặp

Idempotency là thuộc tính mà việc xử lý cùng một yêu cầu nhiều lần vẫn tạo ra kết quả nghiệp vụ tương đương với một lần xử lý. Đây là tuyến phòng thủ quan trọng khi dùng at-least-once delivery.

Ví dụ, message tạo hóa đơn nên có eventId hoặc taskId ổn định. Trước khi áp dụng thay đổi, consumer kiểm tra định danh đã được xử lý chưa. Bảng inbox có thể dùng khóa duy nhất trên event_id:

~~~sql
CREATE TABLE processed_message (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Trong cùng một transaction database:

1. Thử ghi event_id vào bảng processed_message.
2. Nếu khóa đã tồn tại, coi đây là message trùng và không lặp lại nghiệp vụ.
3. Nếu ghi thành công, thực hiện thay đổi nghiệp vụ.
4. Commit transaction.
5. Để listener container ack message sau khi listener kết thúc thành công.

Cần xử lý trường hợp insert trùng khóa bằng cách nhận diện đúng lỗi duplicate key, không nuốt mọi exception. Việc ghi dấu đã xử lý và cập nhật dữ liệu nghiệp vụ phải nằm trong cùng transaction để tránh trạng thái “đã đánh dấu nhưng chưa thực hiện” hoặc “đã thực hiện nhưng chưa đánh dấu”.

Idempotency key cần đại diện cho một hành động nghiệp vụ ổn định. Không tạo UUID mới mỗi lần consumer nhận message, vì khi redelivery UUID mới sẽ khiến hệ thống tưởng đó là công việc khác.

Nếu consumer gọi một dịch vụ ngoài không tham gia transaction database, transaction nội bộ không thể tự bảo đảm hiệu ứng bên ngoài đúng một lần. Khi đó cần idempotency key mà dịch vụ ngoài hỗ trợ, hoặc một quy trình đối soát/reconciliation.

## 8. Thứ tự xử lý và phân vùng công việc

Queue có thể giữ thứ tự message theo thứ tự nhận, nhưng nhiều consumer xử lý song song khiến thứ tự hoàn tất không còn được bảo đảm. Ví dụ task-1 được giao trước nhưng mất 5 giây, còn task-2 được giao sau nhưng chỉ mất 100 ms; task-2 có thể hoàn tất trước.

Nếu nghiệp vụ yêu cầu thứ tự:

- Dùng một consumer tuần tự cho phạm vi dữ liệu cần giữ thứ tự, chấp nhận throughput thấp hơn.
- Phân vùng theo khóa nghiệp vụ, chẳng hạn orderId, để các message của cùng một đơn hàng đi vào cùng một partition/queue.
- Dùng một consumer tuần tự cho mỗi partition nếu broker và kiến trúc hỗ trợ.
- Kiểm tra version hoặc sequence number ở database để từ chối cập nhật cũ đến sau cập nhật mới.

Không nên bật nhiều consumer cho một queue rồi mặc định rằng các thao tác trên cùng khách hàng, đơn hàng hoặc tài khoản sẽ hoàn tất đúng thứ tự. Thứ tự phải được thiết kế theo khóa và ranh giới nghiệp vụ.

## 9. Backpressure và khả năng mở rộng

Queue giúp hấp thụ đột biến tải trong một khoảng thời gian, nhưng queue không tạo ra năng lực xử lý vô hạn. Nếu producer gửi nhanh hơn consumer xử lý trong thời gian dài, độ dài queue sẽ tăng.

Các biện pháp cần cân nhắc:

- Đặt giới hạn concurrency dựa trên năng lực thật của database và dịch vụ phụ trợ.
- Giám sát tốc độ enqueue/dequeue và tuổi của message cũ nhất.
- Giới hạn tốc độ producer hoặc trả trạng thái tiếp nhận có kiểm soát khi hệ thống quá tải.
- Tách queue theo loại công việc có thời gian xử lý hoặc mức ưu tiên khác nhau.
- Đặt timeout cho lời gọi bên ngoài và giới hạn số lần retry.
- Dùng giới hạn dung lượng hoặc chính sách TTL phù hợp để queue không chiếm tài nguyên vô hạn.
- Scale consumer theo backlog và độ trễ, đồng thời tránh scale nhanh hơn khả năng cấp connection của các hệ thống phụ trợ.

Độ dài queue không phải chỉ số duy nhất. Cần xem cả số message ready, số message unacknowledged, số consumer hoạt động, throughput, thời gian xử lý, tỷ lệ redelivery và DLQ. Một queue có ít message ready nhưng rất nhiều message unacknowledged vẫn có thể đang bị nghẽn ở consumer.

## 10. Độ bền dữ liệu và xác nhận từ producer

Một queue durable chỉ giữ lại định nghĩa queue sau khi broker khởi động lại. Để tăng khả năng phục hồi message, cần xem xét đồng thời:

- Queue/exchange có cấu hình durable phù hợp.
- Message được đánh dấu persistent.
- Broker có publisher confirms để producer biết broker đã nhận trách nhiệm với message.
- Producer xử lý trường hợp gửi thất bại hoặc không nhận được confirm.
- Consumer ack sau khi nghiệp vụ đã hoàn tất.
- Có backup, replication hoặc queue type phù hợp với yêu cầu sẵn sàng.

Không nên đánh đồng “phương thức gửi không ném exception” với “message đã được lưu bền vững và chắc chắn sẽ được xử lý”. Publisher confirm, routing result và consumer acknowledgement giải quyết các giai đoạn khác nhau của vòng đời message.

Với RabbitMQ, có thể bật publisher confirms trong cấu hình Spring Boot và dùng callback/returned message để xử lý trường hợp broker từ chối hoặc không định tuyến được message. Cấu hình cụ thể phụ thuộc phiên bản Spring Boot/Spring AMQP và topology của hệ thống; cần kiểm tra cả confirm và mandatory return thay vì chỉ dựa vào log của producer.

## 11. Transaction, outbox và ranh giới nhất quán

Một lỗi thường gặp là cập nhật database rồi gửi message bằng hai thao tác độc lập:

1. Database commit thành công.
2. Ứng dụng chết trước khi gửi message.

Kết quả là dữ liệu nghiệp vụ đã đổi nhưng không có message để worker xử lý. Trường hợp ngược lại cũng có thể xảy ra nếu message được gửi trước rồi transaction database rollback.

Transactional outbox giải quyết khoảng trống này bằng cách ghi thay đổi nghiệp vụ và một bản ghi outbox trong cùng transaction database. Một publisher riêng đọc outbox và gửi message đến broker; sau khi gửi thành công, nó đánh dấu bản ghi đã phát. Publisher có thể gửi trùng khi gặp sự cố, vì vậy consumer vẫn cần idempotency.

Ở phía consumer, nếu cần cập nhật database rồi ack broker, hãy hiểu rõ transaction manager và thời điểm commit. Transaction database và acknowledgement RabbitMQ không tự động trở thành một transaction phân tán chỉ vì listener có @Transactional. Hãy thiết kế để redelivery an toàn và dùng outbox/inbox khi cần nhất quán giữa nhiều hệ thống.

## 12. Quan sát và vận hành

Các chỉ số nên theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Ready messages | Số message đang chờ consumer nhận |
| Unacknowledged messages | Số message đã giao nhưng chưa ack |
| Consumer count | Số consumer hiện đang đăng ký |
| Publish/ack rate | Tốc độ gửi và tốc độ xử lý hoàn tất |
| Oldest message age | Thời gian message cũ nhất đã chờ |
| Redelivery rate | Tần suất message được giao lại |
| DLQ depth | Số message đã bị cách ly |
| Processing latency | Thời gian từ lúc consumer nhận đến lúc hoàn tất |
| Failure rate | Tỷ lệ lỗi theo loại công việc |

Log nên chứa messageId, taskId, correlationId, loại công việc, số lần thử (nếu có), thời gian xử lý và kết quả. Không ghi token, mật khẩu, dữ liệu cá nhân nhạy cảm hoặc toàn bộ payload nếu không cần thiết.

Một cảnh báo chỉ dựa trên queue depth có thể gây nhiễu khi hệ thống đang xử lý một đợt batch bình thường. Nên kết hợp backlog với tuổi message, tốc độ xử lý và ngưỡng thời gian hoàn thành mà nghiệp vụ chấp nhận.

## 13. Lỗi thiết kế thường gặp

- **Nhiều consumer nhưng vẫn kỳ vọng mọi consumer nhận mọi message**: đây là publish/subscribe, cần nhiều queue hoặc subscription.
- **Ack trước khi hoàn tất nghiệp vụ**: worker chết sau ack có thể làm mất công việc.
- **Giả định không có message trùng**: redelivery là hành vi bình thường của at-least-once.
- **Retry vô hạn ngay lập tức**: tạo vòng lặp nóng, tốn CPU và che khuất lỗi dữ liệu.
- **Prefetch quá lớn**: một consumer có thể giữ quá nhiều message chưa xử lý, làm phân phối mất cân bằng.
- **Tăng concurrency không đo giới hạn phụ trợ**: có thể làm database hoặc API ngoài quá tải.
- **Cho rằng queue FIFO đồng nghĩa với hoàn tất FIFO**: nhiều consumer làm thứ tự hoàn tất thay đổi.
- **Không có DLQ và quy trình replay**: message lỗi có thể bị mất dấu hoặc gây nghẽn queue.
- **Chỉ dùng durable queue mà bỏ qua persistent message và publisher confirm**: chưa đủ để xác nhận producer đã bàn giao message an toàn.
- **Gắn transaction database với ack broker một cách máy móc**: hai tài nguyên không tự động commit/rollback nguyên tử.

## 14. Khi nào nên dùng competing consumers?

Nên dùng khi có một luồng công việc cần phân phối cho nhiều worker, từng message chỉ cần một worker thực hiện, và có thể chấp nhận xử lý bất đồng bộ. Ví dụ: gửi email, xử lý tệp, tạo thumbnail, đồng bộ dữ liệu, chạy báo cáo và xử lý tác vụ nền có thể retry.

Cần xem xét mô hình khác khi:

- Mỗi dịch vụ đều phải nhận một sự kiện: dùng publish/subscribe với queue riêng cho từng nhóm.
- Cần thứ tự nghiêm ngặt theo một khóa: dùng partitioning hoặc xử lý tuần tự theo khóa.
- Công việc có ưu tiên hoặc SLA khác nhau: tách queue hoặc thiết kế routing/priority phù hợp.
- Công việc rất ngắn và số lượng cực lớn: đo chi phí broker, batching và khả năng xử lý theo lô.
- Công việc cần phản hồi tức thời: cân nhắc xử lý đồng bộ hoặc trả trạng thái job để client truy vấn sau.

## 15. Checklist trước khi đưa vào production

- [ ] Queue và topology được khai báo rõ ràng, có quy trình thay đổi tương thích.
- [ ] Producer xử lý publish failure, publisher confirm và message không được route.
- [ ] Message có định danh ổn định, schema có version và payload không chứa dữ liệu thừa.
- [ ] Consumer ack sau khi hoàn tất nghiệp vụ.
- [ ] Handler idempotent và có kiểm thử redelivery.
- [ ] Retry có giới hạn, có backoff và có DLQ.
- [ ] Có người chịu trách nhiệm kiểm tra và replay DLQ.
- [ ] Concurrency, prefetch và connection pool được đo dưới tải thực tế.
- [ ] Có timeout, rate limit và backpressure cho dịch vụ phụ trợ.
- [ ] Có giám sát ready, unacknowledged, consumer count, latency, redelivery và DLQ.
- [ ] Đã xác định yêu cầu thứ tự theo khóa nghiệp vụ.
- [ ] Có phương án xử lý message cũ, schema cũ và triển khai phiên bản consumer mới.

## 16. Tổng kết

Competing consumers là mẫu hình mở rộng work queue theo chiều ngang: nhiều consumer cùng đăng ký trên một queue và chia nhau các message. Broker giúp phân phối công việc, nhưng ứng dụng vẫn phải quyết định cách xác nhận, retry, xử lý trùng, giữ thứ tự và giới hạn tải.

Khi triển khai bằng Spring AMQP, @RabbitListener với concurrency tạo nhiều consumer cho cùng endpoint; prefetch kiểm soát số message đang bay; acknowledgement xác định thời điểm broker coi một message đã hoàn tất. Một hệ thống đáng tin cậy cần kết hợp at-least-once delivery với idempotency, retry có giới hạn, DLQ, publisher confirms, quan sát backlog và thiết kế transaction phù hợp với nghiệp vụ.