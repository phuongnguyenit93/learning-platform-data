# Xây dựng ứng dụng phát, biến đổi và nhận thông điệp đầu tiên

Spring Cloud Stream giúp ứng dụng trao đổi sự kiện qua broker bằng mô hình lập trình hướng hàm. Thay vì tự quản lý client Kafka, RabbitMQ hoặc Pulsar trong từng thành phần, ta khai báo một hàm phát thông điệp, một hàm biến đổi và một hàm nhận thông điệp. Binding nối các hàm với destination; binder đảm nhiệm giao tiếp với broker cụ thể.

Trong bài này, ta xây dựng một pipeline xử lý đơn hàng đơn giản:

1. Supplier tạo sự kiện OrderCreated và phát lên destination orders.created.
2. Function nhận sự kiện, kiểm tra dữ liệu và tạo OrderValidated, rồi phát lên orders.validated.
3. Consumer nhận OrderValidated và ghi nhận kết quả.

Ví dụ dùng Kafka binder để minh họa cách chạy. Cấu trúc hàm và binding vẫn là nền tảng khi chuyển sang RabbitMQ hoặc một binder Pulsar tương thích.

## 1. Chuẩn bị dự án

Spring Cloud Stream chạy trên Spring Boot. Trước khi thêm dependency, chọn phiên bản Spring Boot và Spring Cloud release train tương thích theo bảng tương thích của Spring Cloud. Dùng BOM của Spring Cloud để quản lý phiên bản các thư viện Spring Cloud, tránh tự ghép những phiên bản không tương thích.

Ví dụ phần dependency trong build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'io.spring.dependency-management' version '<dependency-management-version>'
}

ext {
    set('springCloudVersion', '<compatible-spring-cloud-release-train>')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.cloud:spring-cloud-starter-stream-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-stream-test-binder'
}
~~~

Các giá trị phiên bản trong ví dụ là chỗ điền phiên bản đã chọn cho dự án. Không sao chép một release train cũ sang Spring Boot mới mà chưa kiểm tra tính tương thích.

Nếu dùng Maven, khai báo spring-cloud-dependencies trong dependencyManagement, sau đó thêm spring-cloud-starter-stream-kafka và các dependency kiểm thử tương ứng. Với RabbitMQ, thay starter Kafka bằng spring-cloud-starter-stream-rabbit. Với Pulsar, chọn binder Pulsar có phiên bản được công bố tương thích với Spring Cloud Stream đang dùng; kiểm tra đúng artifact và cấu hình kết nối của binder đó thay vì giả định mọi binder dùng chung một thuộc tính broker.

Ứng dụng cần có lớp khởi động Spring Boot:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamGettingStartedApplication {

    public static void main(String[] args) {
        SpringApplication.run(StreamGettingStartedApplication.class, args);
    }
}
~~~

## 2. Khai báo dữ liệu sự kiện

Một message cần có hợp đồng rõ ràng để producer và consumer hiểu cùng một dữ liệu. Với ví dụ đơn hàng, ta dùng hai Java record:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

record OrderCreated(
        String orderId,
        String customerId,
        BigDecimal total) {
}

record OrderValidated(
        String orderId,
        String customerId,
        BigDecimal total,
        String status,
        Instant validatedAt) {
}
~~~

OrderCreated mô tả sự kiện đơn hàng vừa được tạo. OrderValidated là kết quả sau bước kiểm tra. Hai kiểu dữ liệu này minh họa schema của message; khi các dịch vụ có vòng đời triển khai độc lập, nên quản lý hợp đồng bằng schema hoặc tài liệu API sự kiện có quy tắc tương thích, thay vì phụ thuộc vào việc chúng dùng chung một class Java.

Đặt các record trong cùng package với lớp cấu hình và lớp kiểm thử. Có thể giữ chúng trong một file dùng các top-level record không khai báo public như ví dụ, hoặc tách thành hai file riêng và khai báo public cho từng record.

## 3. Viết Supplier, Function và Consumer

Spring Cloud Stream nhận diện các bean hàm theo kiểu Java chuẩn trong java.util.function:

- Supplier<T> không có đầu vào và tạo ra dữ liệu để phát đi.
- Function<T, R> nhận một giá trị kiểu T, xử lý và trả về kết quả kiểu R.
- Consumer<T> nhận dữ liệu kiểu T và thực hiện tác vụ, không phát đầu ra.

Khai báo ba bean trong một lớp cấu hình:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    private final AtomicLong sequence = new AtomicLong();

    @Bean
    public Supplier<OrderCreated> orderSource() {
        return () -> {
            long number = sequence.incrementAndGet();
            return new OrderCreated(
                    "ORD-%04d".formatted(number),
                    "CUSTOMER-01",
                    new BigDecimal("125.50"));
        };
    }

    @Bean
    public Function<OrderCreated, OrderValidated> validateOrder() {
        return order -> {
            if (order.orderId() == null || order.orderId().isBlank()) {
                throw new IllegalArgumentException("orderId is required");
            }
            if (order.total() == null || order.total().signum() <= 0) {
                throw new IllegalArgumentException("total must be positive");
            }
            return new OrderValidated(
                    order.orderId(),
                    order.customerId(),
                    order.total(),
                    "VALIDATED",
                    Instant.now());
        };
    }

    @Bean
    public Consumer<OrderValidated> auditOrder() {
        return order -> System.out.printf(
                "Validated order %s for %s: %s%n",
                order.orderId(),
                order.customerId(),
                order.status());
    }
}
~~~

orderSource là nguồn dữ liệu minh họa. Spring Cloud Stream gọi Supplier thông qua poller và phát giá trị trả về lên binding đầu ra. Poller mặc định thường gọi supplier theo chu kỳ một giây; có thể điều chỉnh nhịp poll bằng cấu hình Spring Integration phù hợp. Trong ứng dụng thật, supplier có thể lấy dữ liệu từ một nguồn có sẵn hoặc phát sự kiện sau khi nghiệp vụ hoàn tất. Không dùng bộ đếm trong bộ nhớ làm định danh đơn hàng trong hệ thống nhiều instance; mỗi instance có thể có bộ đếm riêng. Hãy dùng định danh duy nhất được tạo từ hệ thống nghiệp vụ.

validateOrder nhận sự kiện và trả về kết quả. Khi hàm ném exception, cơ chế xử lý lỗi của binding và binder sẽ quyết định retry hoặc chuyển lỗi theo cấu hình. Ví dụ này chỉ minh họa phép kiểm tra đồng bộ; không nên đưa tác vụ chậm hoặc side effect không idempotent vào hàm mà chưa thiết kế chính sách giao nhận.

auditOrder nhận kết quả đã xác thực. Trong ứng dụng thực tế, consumer có thể ghi dữ liệu vào cơ sở dữ liệu hoặc gọi dịch vụ khác. Nếu message được giao lại, thao tác cần an toàn khi thực hiện nhiều lần.

## 4. Nối các hàm với destination

Spring Cloud Stream tạo tên binding mặc định dựa trên tên bean và hướng dữ liệu:

| Bean | Binding | Hướng |
|---|---|---|
| orderSource | orderSource-out-0 | Đầu ra của Supplier |
| validateOrder | validateOrder-in-0 | Đầu vào của Function |
| validateOrder | validateOrder-out-0 | Đầu ra của Function |
| auditOrder | auditOrder-in-0 | Đầu vào của Consumer |

Tạo src/main/resources/application.yml:

~~~yaml
spring:
  cloud:
    function:
      definition: orderSource;validateOrder;auditOrder
    stream:
      bindings:
        orderSource-out-0:
          destination: orders.created
          content-type: application/json

        validateOrder-in-0:
          destination: orders.created
          group: order-validator
          content-type: application/json

        validateOrder-out-0:
          destination: orders.validated
          content-type: application/json

        auditOrder-in-0:
          destination: orders.validated
          group: order-audit
          content-type: application/json

      kafka:
        binder:
          brokers: localhost:9092
~~~

Thuộc tính spring.cloud.function.definition liệt kê các bean hàm cần kích hoạt. Dấu chấm phẩy phân tách những hàm độc lập; chúng không bị ghép thành một hàm duy nhất. Mỗi hàm có binding riêng và được nối với broker thông qua destination:

- orderSource-out-0 phát message lên orders.created.
- validateOrder-in-0 đọc từ orders.created; hàm xử lý rồi gửi kết quả qua validateOrder-out-0 đến orders.validated.
- auditOrder-in-0 đọc từ orders.validated.

content-type: application/json khai báo định dạng payload. Spring Cloud Stream sử dụng message converter để chuyển đổi giữa message và kiểu Java mà hàm khai báo. Producer và consumer cần thống nhất schema và cách biểu diễn dữ liệu; chỉ đặt content type không tự bảo đảm hai phiên bản ứng dụng tương thích.

group đặt tên nhóm consumer cho binding đầu vào. Nhiều instance chạy cùng order-validator chia tải xử lý luồng orders.created; một nhóm khác có thể đọc độc lập cùng destination. order-audit là nhóm riêng trên orders.validated. Đặt group ổn định giúp broker lưu tiến độ theo cơ chế của nó và hỗ trợ triển khai nhiều instance.

## 5. Khởi chạy và quan sát luồng đầu tiên

Trước khi chạy ứng dụng, khởi động Kafka và bảo đảm broker có thể truy cập tại localhost:9092. Nếu broker không tự tạo topic, hãy tạo trước orders.created và orders.validated với số partition phù hợp. Trong môi trường phát triển, có thể dùng broker cục bộ hoặc container; môi trường triển khai cần cấu hình địa chỉ broker, thông tin xác thực và mã hóa kết nối theo chính sách hạ tầng.

Chạy ứng dụng bằng Gradle:

~~~bash
./gradlew bootRun
~~~

Trên Windows có thể chạy gradlew.bat bootRun. Khi ứng dụng khởi động thành công, supplier bắt đầu phát các sự kiện theo chu kỳ. Function đọc orders.created, kiểm tra payload và phát kết quả lên orders.validated. Consumer đọc kết quả và ghi log tương tự:

~~~text
Validated order ORD-0001 for CUSTOMER-01: VALIDATED
Validated order ORD-0002 for CUSTOMER-01: VALIDATED
~~~

Tên đơn hàng và số thứ tự trong log chỉ là dữ liệu minh họa. Nếu không thấy log, kiểm tra theo thứ tự:

1. Broker có đang chạy và ứng dụng kết nối được đến địa chỉ đã cấu hình không?
2. Các topic orders.created và orders.validated có tồn tại hoặc được phép tự tạo không?
3. spring.cloud.function.definition có đúng tên ba bean không?
4. Tên binding có khớp chính xác với tên bean và hậu tố -in-0 / -out-0 không?
5. Producer và consumer có dùng cùng destination, content type và schema không?
6. Log có báo lỗi chuyển đổi payload, phân quyền, kết nối hoặc xử lý message không?

Nếu ứng dụng kết nối broker từ container, localhost thường trỏ về chính container đó. Khi ấy cần dùng hostname mạng nội bộ hoặc địa chỉ broker có thể truy cập từ container.

## 6. Chọn binder cho broker

Logic Supplier, Function, Consumer và cấu hình binding ở trên mô tả cách ứng dụng xử lý message. Binder chuyển những binding đó thành tài nguyên và thao tác phù hợp với broker.

| Broker | Cách ánh xạ thường gặp | Điều cần kiểm tra |
|---|---|---|
| Kafka | Destination là topic; group là consumer group | Partition, offset, số consumer trong group và chính sách commit |
| RabbitMQ | Destination thường gắn với exchange; group gắn với queue của nhóm | Exchange type, routing key, queue, acknowledgement và dead-letter |
| Pulsar | Destination là topic; group gắn với subscription | Subscription type, tên subscription, phân phối theo key và cursor |

Khi chuyển sang RabbitMQ, thêm Rabbit binder starter tương thích và cấu hình kết nối RabbitMQ theo môi trường. Giữ nguyên tên binding và destination logic nếu muốn; xác minh exchange và queue được binder tạo ra đúng với cách định tuyến mong muốn. Với Pulsar, thêm binder tương thích và cấu hình service URL, xác thực cùng subscription theo hướng dẫn của phiên bản binder đó.

Không nên suy luận rằng cùng một tên destination có nghĩa là cùng cấu trúc vật lý ở mọi broker. Kafka dùng topic và partition; RabbitMQ thường định tuyến qua exchange đến queue; Pulsar quản lý topic và subscription. Kiểm tra tài nguyên thực tế trên broker là bước cần có khi triển khai.

## 7. Kiểm thử hàm và binding

Nên kiểm tra logic hàm trước, sau đó kiểm tra message đi qua binding. Spring Cloud Stream cung cấp test binder để kiểm thử binding mà không cần khởi động broker thật. Thêm dependency spring-cloud-stream-test-binder vào cấu hình test của dự án.

Ví dụ kiểm thử riêng validateOrder bằng InputDestination và OutputDestination:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest(properties = {
        "spring.cloud.function.definition=validateOrder",
        "spring.cloud.stream.bindings.validateOrder-in-0.destination=orders.in",
        "spring.cloud.stream.bindings.validateOrder-out-0.destination=orders.out"
})
class ValidateOrderBindingTest {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void validatesAnIncomingOrder() {
        OrderCreated event = new OrderCreated(
                "ORD-TEST-1",
                "CUSTOMER-TEST",
                new java.math.BigDecimal("125.50"));

        input.send(
                MessageBuilder.withPayload(event).build(),
                "validateOrder-in-0");

        Message<byte[]> result =
                output.receive(1000, "validateOrder-out-0");

        assertNotNull(result);
        String json = new String(result.getPayload(), StandardCharsets.UTF_8);
        assertTrue(json.contains("ORD-TEST-1"));
        assertTrue(json.contains("VALIDATED"));
    }
}
~~~

Test này xác nhận message đi vào đúng binding, được hàm xử lý và xuất hiện ở binding đầu ra. Nó không thay thế kiểm thử tích hợp với Kafka, RabbitMQ hoặc Pulsar. Với broker thật, cần kiểm tra thêm việc tạo destination, consumer group/subscription, phân phối khi chạy nhiều instance, xác nhận, retry và dead-letter.

## 8. Các nguyên tắc cần giữ khi đưa ví dụ vào ứng dụng thật

Ví dụ trên giúp thấy rõ luồng phát, biến đổi và nhận message. Khi phát triển thành hệ thống nghiệp vụ, cần bổ sung một số quyết định:

- **Định danh sự kiện:** mỗi sự kiện cần eventId ổn định để phát hiện bản tin trùng và hỗ trợ truy vết. Không dùng bộ đếm trong bộ nhớ làm định danh toàn cục.
- **Schema:** thống nhất tên trường, kiểu dữ liệu, đơn vị, trường bắt buộc và quy tắc tương thích giữa các phiên bản producer/consumer.
- **Consumer group:** dùng cùng group khi các instance chia tải cùng một công việc; dùng group riêng khi mỗi dịch vụ cần nhận luồng độc lập.
- **Partition và thứ tự:** nếu cần thứ tự theo đơn hàng, dùng khóa ổn định như orderId và kiểm tra cách broker phân phối theo partition hoặc subscription.
- **Retry và DLQ:** giới hạn số lần thử cho lỗi tạm thời, đưa message không thể xử lý vào nơi cách ly và có quy trình điều tra/phát lại.
- **Idempotency:** thiết kế consumer chịu được giao lại. Một lần gọi broker thành công không đồng nghĩa side effect ở cơ sở dữ liệu hoặc API bên ngoài chỉ xảy ra đúng một lần.
- **Quan sát vận hành:** ghi log có eventId, destination và group; theo dõi độ trễ, lượng message tồn đọng, lỗi xử lý và số message vào DLQ.

Supplier, Function và Consumer tạo nên ba vai trò rõ ràng trong pipeline. Binding nối các vai trò đó với destination, còn binder kết nối ứng dụng với broker được chọn. Khi hiểu và kiểm tra được từng lớp, ta có thể bắt đầu với một luồng message nhỏ, mở rộng thành nhiều consumer group và thay đổi broker mà vẫn giữ được phần lớn logic nghiệp vụ.
