# Cấu hình application.yml và chạy thử luồng đầu cuối

Một ứng dụng Spring Cloud Stream thường được cấu hình qua ba phần: chọn hàm nghiệp vụ cần chạy, ánh xạ input/output binding tới destination, và khai báo binder để kết nối broker. Khi ba phần này khớp nhau, một message gửi vào destination đầu vào sẽ đi qua Supplier, Function hoặc Consumer của ứng dụng theo đúng kiểu hàm đã khai báo.

Bài thực hành dưới đây dùng Kafka để chạy một luồng hoàn chỉnh: gửi chuỗi vào topic `greetings`, xử lý bằng một `Function<String, String>`, rồi đọc kết quả viết hoa từ topic `greetings-uppercase`. Mô hình hàm và binding giữ nguyên khi đổi sang RabbitMQ hoặc Pulsar; phần kết nối và một số semantics phụ thuộc binder sẽ thay đổi.

## 1. Chuẩn bị project và broker

Trước khi cấu hình, cần có:

- Java 17 trở lên và Maven hoặc Maven Wrapper.
- Một ứng dụng Spring Boot khởi động được.
- Apache Kafka đang chạy và có thể truy cập tại `localhost:9092`.
- Công cụ dòng lệnh Kafka để tạo topic, gửi và đọc message.

Nếu tạo project mới bằng Spring Initializr, chọn Spring Boot tương thích với Spring Cloud release train dự định sử dụng. Spring Cloud Stream và binder cần được quản lý phiên bản bằng Spring Cloud BOM tương ứng với phiên bản Spring Boot; không tự ghép các phiên bản khác release train.

Với Maven, thêm dependency quản lý phiên bản và Kafka binder. Ví dụ phần liên quan trong `pom.xml`:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-cloud.version>YOUR_COMPATIBLE_SPRING_CLOUD_VERSION</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-stream-kafka</artifactId>
    </dependency>
</dependencies>
~~~

Thay `YOUR_COMPATIBLE_SPRING_CLOUD_VERSION` bằng phiên bản release train tương thích trong bảng tương thích Spring Cloud. Nếu project đã được Spring Initializr tạo với dependency management tương ứng thì giữ cấu hình BOM hiện có và chỉ bổ sung binder.

Kafka broker phải sẵn sàng trước khi chạy ứng dụng. Bài thực hành giả định broker có địa chỉ `localhost:9092`; nếu chạy ứng dụng trong container, `localhost` có thể trỏ vào chính container ứng dụng. Khi đó cần dùng hostname mà container có thể phân giải tới broker.

## 2. Viết một Function xử lý message

Tạo một bean Function có tên `uppercase`. Hàm nhận chuỗi đầu vào và trả về chuỗi viết hoa:

~~~java
import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class StreamUppercaseApplication {

    public static void main(String[] args) {
        SpringApplication.run(StreamUppercaseApplication.class, args);
    }

    @Bean
    Function<String, String> uppercase() {
        return message -> message.toUpperCase(Locale.ROOT);
    }
}
~~~

Spring Cloud Stream nhận diện bean hàm và tạo các binding theo tên bean cùng vị trí tham số:

| Tên bean | Binding | Vai trò |
|---|---|---|
| `uppercase` | `uppercase-in-0` | Nhận message đầu vào |
| `uppercase` | `uppercase-out-0` | Phát kết quả đầu ra |

Hậu tố `-in-0` biểu thị input thứ nhất, còn `-out-0` biểu thị output thứ nhất. Nếu function có nhiều input hoặc output, chỉ số tăng từ 0 theo thứ tự tham số. Tên binding này là tên logic trong ứng dụng; destination được cấu hình riêng.

## 3. Cấu hình application.yml

Tạo file `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: stream-uppercase

  cloud:
    function:
      definition: uppercase

    stream:
      bindings:
        uppercase-in-0:
          destination: greetings
          group: uppercase-service
          content-type: text/plain

        uppercase-out-0:
          destination: greetings-uppercase
          content-type: text/plain

      kafka:
        binder:
          brokers: ${KAFKA_BROKERS:localhost:9092}
~~~

Đọc cấu hình theo từng phần:

- `spring.application.name` đặt tên ứng dụng Spring Boot, hữu ích cho log và quan sát hệ thống.
- `spring.cloud.function.definition` chọn bean hàm mà Spring Cloud Stream sẽ kích hoạt. Giá trị phải trùng tên bean, ở đây là `uppercase`.
- `uppercase-in-0.destination` ánh xạ input binding tới topic `greetings`.
- `uppercase-in-0.group` đặt consumer group ổn định. Các instance dùng cùng group chia sẻ công việc tiêu thụ theo cơ chế của Kafka.
- `uppercase-in-0.content-type` khai báo kiểu nội dung đầu vào là văn bản.
- `uppercase-out-0.destination` ánh xạ output binding tới topic `greetings-uppercase`.
- `uppercase-out-0.content-type` khai báo kiểu nội dung đầu ra.
- `spring.cloud.stream.kafka.binder.brokers` chỉ địa chỉ Kafka broker. Placeholder cho phép lấy địa chỉ từ biến môi trường `KAFKA_BROKERS`, và dùng `localhost:9092` làm giá trị mặc định.

Trong cấu hình này, `greetings` và `greetings-uppercase` là tên destination trên Kafka. Binding giúp code tham chiếu tới đầu vào và đầu ra theo tên hàm, còn binder chuyển các message giữa binding và broker.

Có thể tách cấu hình theo profile, ví dụ `application-local.yml`, `application-staging.yml` và `application-prod.yml`. Thông tin kết nối, credential và TLS nên được cấp qua biến môi trường hoặc secret manager. Không commit mật khẩu broker vào repository.

## 4. Tạo topic và khởi động ứng dụng

Tạo hai topic trước khi chạy:

~~~bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists --topic greetings --partitions 3 --replication-factor 1
bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists --topic greetings-uppercase --partitions 3 --replication-factor 1
~~~

Nếu dùng Kafka trên Windows, script thường nằm trong `bin\windows` và có phần mở rộng `.bat`, ví dụ `kafka-topics.bat`. Tùy bản phân phối Kafka, đường dẫn thực tế có thể khác.

Khởi động ứng dụng từ thư mục chứa `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows dùng Maven Wrapper:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Quan sát log để xác nhận ứng dụng đã khởi động và Kafka binder đã kết nối, tạo hoặc gán consumer cho input binding. Nếu ứng dụng báo lỗi kết nối, kiểm tra broker đã chạy, địa chỉ bootstrap có thể truy cập từ tiến trình ứng dụng và cổng đã được mở.

Nên khởi động ứng dụng trước khi gửi message trong lần chạy đầu tiên. Như vậy consumer group mới có thể nhận các message được gửi trong bài thực hành mà không phụ thuộc vào vị trí offset đã tồn tại từ lần chạy trước.

## 5. Gửi message và xác nhận kết quả

Mở terminal thứ hai và chạy producer để gửi message vào topic đầu vào:

~~~bash
bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic greetings
~~~

Nhập từng dòng, ví dụ:

~~~text
hello spring cloud stream
order-created
Kafka binder is connected
~~~

Mỗi dòng được gửi thành một Kafka record. Mở terminal thứ ba và đọc topic đầu ra:

~~~bash
bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic greetings-uppercase --from-beginning
~~~

Kết quả mong đợi:

~~~text
HELLO SPRING CLOUD STREAM
ORDER-CREATED
KAFKA BINDER IS CONNECTED
~~~

Khi nhận record ở `greetings`, Kafka binder chuyển payload thành message cho input binding `uppercase-in-0`. Function `uppercase` xử lý payload và trả về kết quả. Output binding `uppercase-out-0` gửi kết quả tới topic `greetings-uppercase`; console consumer đọc được các record đó.

Có thể kiểm tra hai topic bằng lệnh `kafka-console-consumer` tương ứng. Nếu đọc topic đầu vào, sẽ thấy chuỗi gốc; nếu đọc topic đầu ra, sẽ thấy chuỗi đã được viết hoa. Đây là cách xác nhận cả hai chiều của luồng.

## 6. Thử các kiểu hàm Supplier và Consumer

Sau khi luồng Function chạy thành công, có thể thử hai kiểu hàm còn lại để hiểu cách binding được tạo.

### Supplier phát message

Supplier không nhận input; framework gọi hàm để lấy dữ liệu và phát ra output binding:

~~~java
import java.util.function.Supplier;

@Bean
Supplier<String> heartbeat() {
    return () -> "stream-is-alive";
}
~~~

Output binding mặc định là `heartbeat-out-0`. Có thể ánh xạ binding này tới một destination khác:

~~~yaml
spring:
  cloud:
    function:
      definition: heartbeat
    stream:
      bindings:
        heartbeat-out-0:
          destination: heartbeat-events
          content-type: text/plain
~~~

Supplier thông thường được gọi bởi poller. Có thể điều chỉnh chu kỳ polling bằng cấu hình poller của Spring Integration, chẳng hạn `spring.integration.poller.fixed-delay`. Cần bảo đảm Supplier không phát lại một hành động không idempotent ngoài ý muốn mỗi lần được gọi.

### Consumer nhận và xử lý message

Consumer chỉ có input, không phát output binding:

~~~java
import java.util.function.Consumer;

@Bean
Consumer<String> logGreeting() {
    return message -> System.out.println("Received: " + message);
}
~~~

Input binding mặc định là `logGreeting-in-0`. Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: logGreeting
    stream:
      bindings:
        logGreeting-in-0:
          destination: greetings
          group: greeting-logger
          content-type: text/plain
~~~

Các ví dụ Supplier và Consumer là những cấu hình thay thế cho bài thực hành Function. Nếu đưa nhiều bean hàm vào cùng ứng dụng, cần khai báo rõ hàm được kích hoạt. Có thể dùng dấu chấm phẩy để kích hoạt nhiều hàm độc lập, ví dụ `uppercase;logGreeting`; dùng dấu `|` để nối các hàm có kiểu dữ liệu tương thích thành một pipeline, ví dụ `normalize|uppercase`.

## 7. Dùng binder khác

Mô hình hàm và phần lớn cấu hình `spring.cloud.stream.bindings` có thể giữ nguyên khi đổi middleware. Thay dependency binder và phần cấu hình kết nối tương ứng.

| Broker | Dependency | Cấu hình kết nối thường dùng | Destination |
|---|---|---|---|
| Kafka | `org.springframework.cloud:spring-cloud-starter-stream-kafka` | `spring.cloud.stream.kafka.binder.brokers` | Topic |
| RabbitMQ | `org.springframework.cloud:spring-cloud-starter-stream-rabbit` | `spring.rabbitmq.host`, `port`, `username`, `password` | Exchange và queue |
| Pulsar | `org.springframework.pulsar:spring-pulsar-spring-cloud-stream-binder` | `spring.pulsar.client.service-url` | Topic và subscription |

Ví dụ phần kết nối RabbitMQ:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
~~~

Rabbit binder ánh xạ destination tới exchange; với consumer có group, binder tạo queue gắn với exchange để các instance trong cùng group chia sẻ message. Trong production, cần dùng tài khoản riêng và giới hạn quyền truy cập thay vì giữ thông tin mặc định.

Ví dụ phần kết nối Pulsar:

~~~yaml
spring:
  pulsar:
    client:
      service-url: pulsar://localhost:6650
~~~

Pulsar binder ánh xạ destination tới topic và dùng subscription để quản lý consumer. Cần chọn subscription type phù hợp với mô hình chia tải hoặc phát dữ liệu cho nhiều nhóm tiêu thụ. Cấu hình retry, dead-letter và schema của Pulsar có thuộc tính riêng; không sao chép nguyên xi thuộc tính mở rộng của Kafka hoặc RabbitMQ.

Nếu một ứng dụng có nhiều binder trên classpath, cần cấu hình rõ binder cho từng binding theo tên binder đã khai báo. Khi chỉ có một binder, framework thường có thể tự chọn binder đó. Việc dùng chung tên destination không có nghĩa semantics của topic, exchange, queue và subscription hoàn toàn giống nhau.

## 8. Đọc lỗi và xử lý các cấu hình thường sai

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| Ứng dụng khởi động nhưng function không nhận message | `spring.cloud.function.definition` không khớp tên bean hoặc binding sai | So sánh tên bean, `-in-0` và destination trong YAML |
| Broker báo connection refused | Sai hostname/port, broker chưa chạy hoặc container không truy cập được địa chỉ | Kiểm tra địa chỉ broker từ chính môi trường chạy ứng dụng |
| Có message ở input nhưng không có output | Function ném exception, output binding sai hoặc broker từ chối ghi | Đọc stack trace, kiểm tra tên output binding và quyền ghi destination |
| Payload bị chuyển đổi sai | `content-type` không khớp định dạng gửi | Dùng `text/plain` cho chuỗi hoặc cấu hình JSON phù hợp với payload |
| Consumer không đọc lại dữ liệu cũ | Group đã có offset được commit | Hiểu vị trí offset hiện tại; dùng group thử nghiệm mới khi cần kiểm tra độc lập |
| Không tạo được topic hoặc queue | Broker không cho phép tự động provision hoặc tài khoản thiếu quyền | Tạo destination theo quy trình hạ tầng và cấp quyền phù hợp |
| Ứng dụng có nhiều binder và báo không xác định được binder | Có nhiều binder nhưng binding chưa chỉ rõ binder | Khai báo binder tương ứng cho từng binding |

Khi kiểm tra consumer group Kafka, dùng lệnh sau để xem trạng thái và lag:

~~~bash
bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group uppercase-service
~~~

Lệnh này giúp quan sát partition được gán, offset đã commit, log-end offset và lag. Khi chạy nhiều instance, theo dõi số partition và số consumer đang hoạt động để hiểu mức độ song song.

## 9. Kiểm thử trước khi tích hợp broker thật

Luồng chạy thủ công với Kafka giúp xác nhận kết nối thực tế, nhưng không nên dùng thao tác terminal làm kiểm thử tự động duy nhất. Có thể bổ sung:

- Unit test cho function, kiểm tra chuỗi thường, chuỗi rỗng và ký tự Unicode.
- Test binder với `spring-cloud-stream-test-binder` để gửi message vào `InputDestination` và nhận kết quả từ `OutputDestination` mà không cần broker thật.
- Integration test với Kafka thật hoặc Testcontainers để xác nhận broker URL, topic, group, serialization, partition và offset.
- Kiểm thử lỗi khi broker ngắt kết nối, function ném exception hoặc output destination không khả dụng.

Test binder hữu ích để kiểm tra wiring và xử lý message trong ứng dụng. Nó không chứng minh cấu hình broker, phân vùng, rebalance, transaction hay DLQ hoạt động đúng. Các hành vi phụ thuộc broker cần được kiểm tra bằng integration test.

## 10. Những điểm cần giữ khi chuyển sang môi trường triển khai

Trước khi đưa ứng dụng lên staging hoặc production:

- Đưa broker URL, credential, TLS và các giá trị theo môi trường ra khỏi source code.
- Dùng consumer group ổn định để duy trì tiến trình tiêu thụ giữa các lần khởi động.
- Tạo topic, exchange, queue, partition, retention và subscription theo cấu hình hạ tầng được quản lý.
- Đặt timeout, retry và DLQ theo thời gian xử lý nghiệp vụ; thiết kế consumer idempotent để chịu được message được giao lại.
- Theo dõi throughput, processing latency, consumer lag, lỗi kết nối và số message đi vào DLQ.
- Kiểm thử shutdown, restart và scale nhiều instance để xác nhận message đang xử lý được hoàn tất hoặc giao lại an toàn.

Một lần gửi thành công tới broker không tự chứng minh nghiệp vụ đã được xử lý đúng một lần. Producer, broker, consumer và side effect trong cơ sở dữ liệu có ranh giới giao nhận riêng. Hãy xác định rõ acknowledgment hoặc offset được commit khi nào, dữ liệu được lưu bền vững ra sao và consumer xử lý trùng như thế nào.

## 11. Bài thực hành hoàn chỉnh và tiêu chí đạt

Thực hiện theo thứ tự:

1. Tạo project Spring Boot và thêm Kafka binder cùng Spring Cloud BOM tương thích.
2. Viết bean `Function<String, String>` tên `uppercase`.
3. Khai báo `spring.cloud.function.definition`, hai binding `uppercase-in-0` và `uppercase-out-0`, hai destination và content type trong `application.yml`.
4. Khởi động Kafka, tạo hai topic và chạy ứng dụng.
5. Gửi ít nhất ba message vào topic `greetings`; xác nhận topic `greetings-uppercase` nhận đúng ba kết quả đã viết hoa.
6. Khởi động thêm một instance với cùng consumer group; quan sát cách Kafka phân phối partition khi có đủ partition.
7. Thay đổi group trong môi trường thử nghiệm và quan sát việc tạo nhóm tiêu thụ độc lập.
8. Chạy unit test, test binder và integration test với broker.

Hoàn thành bài khi có thể giải thích chính xác đường đi của một message từ producer, destination đầu vào, input binding, function, output binding tới destination đầu ra; biết vị trí cấu hình từng thành phần; và chẩn đoán được lỗi kết nối, sai binding, sai content type hoặc consumer group.

## 12. Tài liệu tham khảo chính thức

- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/index.html) — kiến trúc, functional model, binding và binder.
- [Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html) — quy tắc đặt tên input/output binding.
- [Binding properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html) — cấu hình destination, group và content type.
- [Kafka binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html) — kết nối và thuộc tính mở rộng của Kafka.
- [RabbitMQ binder](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html) — ánh xạ exchange, queue và cấu hình Rabbit.
- [Pulsar binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html) — kết nối, topic, subscription và schema của Pulsar.
- [Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html) — test binder và kiểm thử luồng binding.

