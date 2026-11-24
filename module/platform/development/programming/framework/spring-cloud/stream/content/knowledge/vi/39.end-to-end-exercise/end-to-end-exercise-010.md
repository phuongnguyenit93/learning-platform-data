# Tích hợp Pulsar Binder với schema và subscription phù hợp

Trong bài thực hành này, bạn kết nối một ứng dụng Spring Cloud Stream với Apache Pulsar, gửi sự kiện đơn hàng qua một topic có schema JSON và nhận sự kiện bằng một subscription có tên. Bạn sẽ cấu hình riêng từng binding để producer và consumer dùng cùng hợp đồng dữ liệu, sau đó chọn subscription type theo cách ứng dụng cần mở rộng.

Spring Cloud Stream Binder cho Apache Pulsar giúp ứng dụng tập trung vào các hàm nghiệp vụ. Binder ánh xạ các binding của Spring Cloud Stream tới topic và quản lý việc tạo producer, consumer thông qua Spring for Apache Pulsar. Phần cần thiết kế cẩn thận vẫn là hợp đồng message, tên subscription và cách nhiều consumer chia sẻ công việc.

## Mục tiêu

Sau bài này, bạn có thể:

- Thêm Pulsar Binder vào ứng dụng Spring Cloud Stream.
- Ánh xạ binding đầu ra và đầu vào tới cùng một topic có tên đầy đủ.
- Bật native encoding và native decoding để sử dụng schema của Pulsar.
- Khai báo schema type và Java message type nhất quán ở producer và consumer.
- Đặt consumer group và subscription bền vững, chọn subscription type phù hợp với cách xử lý.
- Kiểm tra luồng sự kiện và xác minh subscription trên Pulsar.

## Bối cảnh thực hành

Giả sử hệ thống thương mại điện tử phát sự kiện **OrderCreated** sau khi đơn hàng được tạo. Dịch vụ xử lý đơn hàng cần nhận sự kiện này để cập nhật trạng thái và kích hoạt các bước tiếp theo. Topic dùng trong bài là:

    persistent://public/default/order-events

Topic có tên đầy đủ gồm loại lưu trữ, tenant, namespace và tên topic. Cách viết đầy đủ giúp tránh nhầm topic khi ứng dụng chạy ở nhiều tenant hoặc namespace.

Luồng xử lý:

    HTTP request
        -> StreamBridge
        -> orderEvents-out-0
        -> Pulsar topic: order-events
        -> processOrderCreated-in-0
        -> Consumer<OrderCreated>

Producer và consumer dùng cùng một kiểu dữ liệu OrderCreated. Consumer thuộc nhóm order-fulfillment-v1. Các instance cùng nhóm chia sẻ một subscription; những nhóm khác có thể nhận bản sao độc lập của sự kiện.

## 1. Thêm Pulsar Binder

Thêm dependency binder vào ứng dụng Maven:

    <dependency>
        <groupId>org.springframework.pulsar</groupId>
        <artifactId>spring-pulsar-spring-cloud-stream-binder</artifactId>
    </dependency>

Ứng dụng cần có thêm Spring Boot Web nếu bạn muốn dùng endpoint HTTP trong ví dụ. Để tránh xung đột phiên bản, hãy dùng BOM và release train tương thích giữa Spring Boot, Spring Cloud Stream và Spring for Apache Pulsar; không tự chọn một phiên bản binder khác dòng với các thư viện nền.

Khi chỉ có một binder trên classpath, Spring Cloud Stream có thể tự chọn binder đó. Nếu ứng dụng có nhiều binder, hãy chỉ định binder cho từng binding theo cấu hình của dự án.

## 2. Khai báo hợp đồng sự kiện

Tạo kiểu dữ liệu OrderCreated. Các trường định danh giúp truy vết và chống xử lý lặp ở tầng nghiệp vụ; amountInCents tránh sai số khi biểu diễn tiền bằng số thực.

    package com.example.orders;

    public record OrderCreated(
            String eventId,
            String orderId,
            String customerId,
            long amountInCents,
            String currency,
            String occurredAt
    ) {
    }

Trong ví dụ, occurredAt là chuỗi thời gian ISO-8601, chẳng hạn 2026-11-24T09:30:00Z. Một hợp đồng sự kiện thực tế nên quy định rõ định dạng, múi giờ, đơn vị tiền tệ, ý nghĩa từng trường và quy tắc tương thích khi thêm hoặc thay đổi trường.

## 3. Viết consumer và publisher

Consumer được khai báo bằng mô hình hàm của Spring Cloud Stream:

    package com.example.orders;

    import java.util.function.Consumer;

    import org.springframework.boot.SpringApplication;
    import org.springframework.boot.autoconfigure.SpringBootApplication;
    import org.springframework.context.annotation.Bean;

    @SpringBootApplication
    public class OrderEventApplication {

        public static void main(String[] args) {
            SpringApplication.run(OrderEventApplication.class, args);
        }

        @Bean
        Consumer<OrderCreated> processOrderCreated() {
            return event -> {
                System.out.printf(
                        "Received eventId=%s orderId=%s amount=%d %s%n",
                        event.eventId(),
                        event.orderId(),
                        event.amountInCents(),
                        event.currency()
                );

                // Gọi service nghiệp vụ để cập nhật đơn hàng.
                // Service nên dùng eventId hoặc orderId để bảo đảm idempotency.
            };
        }
    }

Publisher sử dụng StreamBridge để gửi một đối tượng OrderCreated tới binding đầu ra đã cấu hình:

    package com.example.orders;

    import org.springframework.cloud.stream.function.StreamBridge;
    import org.springframework.http.HttpStatus;
    import org.springframework.http.ResponseEntity;
    import org.springframework.web.bind.annotation.PostMapping;
    import org.springframework.web.bind.annotation.RequestBody;
    import org.springframework.web.bind.annotation.RequestMapping;
    import org.springframework.web.bind.annotation.RestController;

    @RestController
    @RequestMapping("/api/order-events")
    public class OrderEventController {

        private final StreamBridge streamBridge;

        public OrderEventController(StreamBridge streamBridge) {
            this.streamBridge = streamBridge;
        }

        @PostMapping
        public ResponseEntity<Void> publish(@RequestBody OrderCreated event) {
            boolean sent = streamBridge.send("orderEvents-out-0", event);
            if (!sent) {
                return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
            }
            return ResponseEntity.accepted().build();
        }
    }

Tên orderEvents-out-0 là tên binding đầu ra mà StreamBridge sử dụng. Tên processOrderCreated-in-0 được suy ra từ tên bean hàm processOrderCreated. Nếu đổi tên hàm hoặc ánh xạ binding, phải cập nhật các khóa cấu hình tương ứng.

## 4. Cấu hình kết nối, schema và subscription

Tạo application.yml:

    server:
      port: 8090

    spring:
      pulsar:
        client:
          service-url: pulsar://localhost:6650
        admin:
          service-url: http://localhost:8080
      cloud:
        function:
          definition: processOrderCreated
        stream:
          bindings:
            orderEvents-out-0:
              destination: persistent://public/default/order-events
              producer:
                use-native-encoding: true
            processOrderCreated-in-0:
              destination: persistent://public/default/order-events
              group: order-fulfillment-v1
              consumer:
                use-native-decoding: true
          pulsar:
            bindings:
              orderEvents-out-0:
                producer:
                  schema-type: JSON
                  message-type: com.example.orders.OrderCreated
              processOrderCreated-in-0:
                consumer:
                  schema-type: JSON
                  message-type: com.example.orders.OrderCreated
                  subscription:
                    name: order-fulfillment-v1
                    type: Shared
                    mode: Durable
                    initial-position: Earliest

Hai nhóm thuộc tính trong cấu hình có vai trò khác nhau:

| Thuộc tính | Vai trò |
|---|---|
| spring.cloud.stream.bindings.*.destination | Chọn topic mà binding sử dụng |
| spring.cloud.stream.bindings.*.group | Đặt consumer group có tên, áp dụng cho binding đầu vào |
| producer.use-native-encoding | Để Pulsar client mã hóa payload theo schema được khai báo |
| consumer.use-native-decoding | Để Pulsar client giải mã payload theo schema được khai báo |
| spring.cloud.stream.pulsar.bindings.*.producer.schema-type | Schema type của message được gửi |
| spring.cloud.stream.pulsar.bindings.*.consumer.schema-type | Schema type của message được nhận |
| producer/consumer.message-type | Kiểu Java dùng để tạo hoặc đọc dữ liệu theo schema |
| consumer.subscription.* | Tên, loại, chế độ và vị trí khởi tạo subscription |

Trong ví dụ, group và subscription.name cùng là order-fulfillment-v1 để tên nhóm ở Spring Cloud Stream khớp với subscription trên Pulsar. Subscription Durable giữ cursor khi các consumer tạm dừng. initial-position: Earliest chỉ có tác dụng khi Pulsar tạo subscription lần đầu; nó không tua lại một subscription đã tồn tại.

spring.pulsar.client.service-url là địa chỉ giao thức của broker. spring.pulsar.admin.service-url là địa chỉ HTTP của Pulsar Admin, được binder dùng khi cần provision topic. Hai địa chỉ này thường lần lượt là cổng 6650 và 8080 trong môi trường Pulsar standalone. Ứng dụng mẫu dùng cổng HTTP 8090 để không chiếm cổng Admin 8080.

## 5. Hiểu cách schema được áp dụng

Spring Cloud Stream có cơ chế chuyển đổi message riêng. Nếu không bật native encoding/decoding, framework thường chuyển payload qua message converter; dữ liệu được gửi xuống Pulsar dưới dạng byte[] với Schema.BYTES. Content type application/json trong trường hợp đó mô tả cách Spring chuyển đổi payload, không có nghĩa topic đang lưu schema JSON của Pulsar.

Khi bật native encoding ở producer và native decoding ở consumer, Pulsar chịu trách nhiệm mã hóa và giải mã bằng schema. Vì vậy, cấu hình phải có đủ các thông tin sau:

1. Producer bật use-native-encoding.
2. Consumer bật use-native-decoding.
3. Producer và consumer khai báo schema-type tương thích.
4. message-type trỏ tới kiểu Java đúng với dữ liệu cần ghi hoặc đọc.

JSON phù hợp khi muốn hợp đồng dễ đọc và tích hợp với nhiều hệ thống. AVRO hoặc PROTOBUF phù hợp khi nhóm cần quản lý schema có cấu trúc và quy trình tiến hóa hợp đồng chặt chẽ hơn. Với AVRO, PROTOBUF hoặc JSON, producer và consumer phải thống nhất schema type và cách diễn giải trường. Nếu schema có cả key và value, binder còn hỗ trợ khai báo message-key-type và message-value-type.

Không nên thay đổi kiểu dữ liệu của một trường đang được consumer sử dụng mà không kiểm tra chính sách tương thích của schema trên namespace. Khi thêm trường, hãy thiết kế giá trị mặc định hoặc cách xử lý trường vắng mặt; triển khai consumer có thể đọc cả dữ liệu cũ trước khi producer phát schema mới. Luôn kiểm tra schema được đăng ký trên broker trong môi trường tích hợp trước khi phát hành.

## 6. Chọn subscription type

Subscription xác định cách Pulsar phân phối message cho các consumer đang đăng ký cùng một tên subscription. Chọn type theo yêu cầu về song song, thứ tự và dự phòng:

| Type | Cách phân phối | Trường hợp phù hợp |
|---|---|---|
| Exclusive | Một consumer hoạt động trên subscription | Tác vụ đơn luồng hoặc cần một consumer duy nhất |
| Failover | Một consumer hoạt động, consumer khác chờ dự phòng | Muốn có standby và chuyển vai trò khi consumer chính mất |
| Shared | Nhiều consumer cùng nhận message từ subscription | Xử lý song song, tăng số instance theo tải |
| Key_Shared | Nhiều consumer cùng xử lý; message có cùng key được định tuyến nhất quán theo key | Cần song song giữa các đơn hàng nhưng giữ thứ tự theo từng orderId |

Bài thực hành chọn Shared vì mục tiêu là chia tải cho nhiều instance xử lý đơn hàng. Với Shared, các message có thể được phân phối tới các consumer khác nhau; không giả định thứ tự toàn cục được giữ nguyên. Nếu nghiệp vụ yêu cầu mọi sự kiện của cùng một orderId đi theo cùng một luồng xử lý, hãy cân nhắc Key_Shared và bảo đảm producer gửi Pulsar message key theo orderId. Đồng thời kiểm tra giới hạn và yêu cầu về batching của Key_Shared trong phiên bản Pulsar đang triển khai.

Một subscription có tên nên đại diện cho một mục đích xử lý ổn định, ví dụ order-fulfillment-v1. Các dịch vụ độc lập cần nhận bản sao của mọi sự kiện nên dùng tên subscription khác nhau. Các instance của cùng một dịch vụ xử lý cạnh tranh nên dùng chung tên subscription.

## 7. Chạy và kiểm tra luồng sự kiện

Khởi động một Pulsar standalone có mở cổng broker 6650 và Admin HTTP 8080, sau đó chạy ứng dụng Spring Boot. Binder có thể tự provision topic cơ bản khi topic chưa tồn tại; nếu môi trường không cho phép tự tạo topic, hãy tạo topic trước bằng công cụ quản trị và cấp quyền phù hợp cho ứng dụng.

Gửi một sự kiện thử nghiệm tới endpoint bằng PowerShell:

    $body = @{
        eventId = "evt-001"
        orderId = "ORD-001"
        customerId = "CUS-007"
        amountInCents = 125000
        currency = "VND"
        occurredAt = "2026-11-24T09:30:00Z"
    } | ConvertTo-Json

    Invoke-RestMethod -Method Post -Uri "http://localhost:8090/api/order-events" -ContentType "application/json" -Body $body

Kết quả mong đợi:

- HTTP trả về 202 Accepted khi StreamBridge chấp nhận gửi message vào binding đầu ra.
- Log consumer hiển thị eventId là evt-001, orderId là ORD-001 và amountInCents là 125000.
- Pulsar hiển thị topic order-events cùng subscription order-fulfillment-v1.

Có thể xem thống kê topic bằng Pulsar Admin:

    bin/pulsar-admin topics stats persistent://public/default/order-events

Trong kết quả, kiểm tra subscription có tên đúng, số consumer đang kết nối và backlog. Gửi thêm một sự kiện rồi quan sát consumer nhận được. Khởi chạy thêm một instance ứng dụng với cùng group để kiểm tra Shared subscription phân phối message giữa các instance. Mỗi message trong cùng subscription được giao cho một consumer tại một thời điểm; một nhóm subscription khác vẫn có thể nhận bản sao riêng.

HTTP 202 chỉ xác nhận thao tác gửi qua binding được chấp nhận. Nó không chứng minh logic nghiệp vụ phía consumer đã hoàn tất. Trong hệ thống thật, cần theo dõi kết quả xử lý, retry, dead-letter topic và trạng thái backlog riêng.

## 8. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Ứng dụng không kết nối được broker | Sai service URL, DNS, cổng hoặc cấu hình TLS | Kiểm tra spring.pulsar.client.service-url và khả năng truy cập cổng Pulsar |
| Không tạo được topic | Admin URL sai hoặc thiếu quyền quản trị | Kiểm tra spring.pulsar.admin.service-url, quyền tenant/namespace và log provisioner |
| Producer gửi được nhưng consumer không đọc | Sai destination, function definition hoặc binding name | Đối chiếu processOrderCreated-in-0 và orderEvents-out-0 |
| Lỗi schema hoặc không giải mã được payload | Schema type hoặc message type không khớp | Đối chiếu schema-type, message-type và schema đã đăng ký trên topic |
| Consumer đọc dữ liệu dưới dạng byte[] | Native decoding chưa bật hoặc cấu hình sai binding | Kiểm tra consumer.use-native-decoding và cấu hình Pulsar consumer |
| Instance thứ hai không tham gia subscription | Subscription type không hỗ trợ nhiều consumer hoặc tên subscription khác nhau | Kiểm tra subscription.type và subscription.name trên mọi instance |
| Consumer khởi động nhưng không nhận message cũ | Subscription đã tồn tại với cursor ở vị trí khác | Kiểm tra backlog và nhớ rằng initial-position chỉ áp dụng lúc tạo subscription |
| Xử lý trùng sự kiện | Retry, redelivery hoặc producer phát lại cùng sự kiện | Dùng eventId làm khóa idempotency ở tầng nghiệp vụ |

Không xử lý trùng chỉ bằng cách giả định broker luôn giao message đúng một lần. Consumer nên ghi nhận eventId đã xử lý trong cùng ranh giới giao dịch với cập nhật nghiệp vụ, hoặc dùng một cơ chế idempotency tương đương.

## 9. Bài tập mở rộng

1. Thay JSON bằng AVRO. Khai báo schema tương ứng, cập nhật schema-type và kiểm tra producer/consumer cùng đọc được dữ liệu.
2. Chạy hai instance consumer với cùng group, quan sát cách Shared subscription chia message.
3. Tạo một consumer group thứ hai tên order-audit-v1. Xác minh nhóm kiểm toán nhận bản sao độc lập với nhóm fulfillment.
4. Chuyển sang Key_Shared, gửi message có key là orderId và kiểm tra các sự kiện cùng đơn hàng được xử lý theo cùng tuyến consumer.
5. Thêm một trường tùy chọn vào OrderCreated. Kiểm tra khả năng đọc dữ liệu cũ và mới trước khi triển khai producer mới.
6. Cấu hình retry và dead-letter topic cho lỗi xử lý có thể phục hồi; theo dõi backlog và số message chuyển sang DLQ.

## Tiêu chí hoàn thành

- Ứng dụng kết nối được Pulsar bằng broker URL và Admin URL phù hợp.
- Binding đầu ra và đầu vào cùng trỏ tới topic order-events.
- Producer và consumer dùng native encoding/decoding cùng schema JSON và cùng message type.
- Consumer có group và subscription name ổn định, subscription ở chế độ Durable và dùng Shared cho mục tiêu chia tải.
- Gửi được sự kiện thử nghiệm và quan sát được consumer nhận đúng các trường.
- Giải thích được vì sao Shared phù hợp với chia tải và khi nào nên chọn Key_Shared.

## Tài liệu tham khảo

- [Spring Cloud Stream Binder for Apache Pulsar](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring Cloud Stream Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Boot Apache Pulsar Support](https://docs.spring.io/spring-boot/3.5/reference/messaging/pulsar.html)
- [Spring Boot Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
