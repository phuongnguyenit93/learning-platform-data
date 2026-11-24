# Spring Cloud Stream trong hệ sinh thái Spring Boot, Spring Cloud Function và Spring Integration

Spring Cloud Stream giúp xây dựng ứng dụng xử lý sự kiện mà không phải gắn chặt mã nghiệp vụ với API của một message broker cụ thể. Ứng dụng khai báo các hàm xử lý bằng Java, mô tả đầu vào và đầu ra qua binding, sau đó binder kết nối những binding đó với Kafka, RabbitMQ hoặc một hệ thống nhắn tin có binder tương thích, chẳng hạn Pulsar.

Để hiểu đúng vị trí của Spring Cloud Stream, cần nhìn nó trong hệ sinh thái Spring. Spring Boot cung cấp nền tảng chạy ứng dụng và cấu hình; Spring Cloud Function cung cấp mô hình hàm Supplier, Function, Consumer; Spring Integration cung cấp các trừu tượng và mẫu tích hợp dựa trên message; Spring Cloud Stream kết nối mô hình xử lý sự kiện với các destination bên ngoài thông qua binder. Các lớp này phối hợp với nhau nhưng giải quyết những bài toán khác nhau.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò và ranh giới trách nhiệm của Spring Boot, Spring Cloud Function, Spring Integration và Spring Cloud Stream.
- Theo dõi đường đi của một message từ hàm xử lý đến binding, binder, broker và consumer.
- Viết các bean hàm Supplier, Function, Consumer và xác định binding tương ứng.
- Cấu hình destination, consumer group, content type và binder cho từng luồng dữ liệu.
- Hiểu các khác biệt quan trọng giữa Kafka, RabbitMQ và Pulsar khi triển khai cùng một mô hình ứng dụng.
- Nhận biết các vấn đề về partition, schema, retry, dead-letter queue (DLQ), trạng thái Kafka Streams, kiểm thử và bảo đảm giao nhận.

## 1. Bài toán mà Spring Cloud Stream giải quyết

Trong một hệ thống hướng sự kiện, một thành phần phát ra sự kiện khi có điều gì đó xảy ra; một hoặc nhiều thành phần khác nhận và phản ứng với sự kiện đó. Ví dụ, dịch vụ đơn hàng phát sự kiện OrderCreated, dịch vụ thanh toán tiếp nhận để tạo yêu cầu thanh toán, còn dịch vụ thông báo gửi email cho khách hàng.

Nếu mã nghiệp vụ gọi trực tiếp API của Kafka, RabbitMQ hoặc Pulsar, nó phải biết nhiều chi tiết của hạ tầng:

- Cách tạo producer hoặc consumer và quản lý vòng đời kết nối.
- Cách gửi, nhận, xác nhận và xử lý lỗi message.
- Cách ánh xạ topic, exchange, queue hoặc subscription.
- Cách cấu hình serialization, partition, consumer group và cơ chế retry.
- Cách kiểm thử mà không cần khởi chạy broker thật trong mọi bài test.

Những chi tiết này cần thiết ở tầng tích hợp, nhưng thường không phải điều mà logic nghiệp vụ cần quan tâm. Khi đổi broker hoặc thay đổi cách triển khai, mã nghiệp vụ có thể phải thay đổi theo.

Spring Cloud Stream tạo một ranh giới giữa logic xử lý và hệ thống vận chuyển message. Ứng dụng khai báo hàm xử lý và các binding có tên; binder chịu trách nhiệm kết nối binding với broker cụ thể. Nhờ vậy, phần lớn logic nghiệp vụ có thể giữ nguyên khi thay binder, miễn là ứng dụng không phụ thuộc vào những đặc tính riêng của broker.

Sự trừu tượng này không làm cho mọi broker có hành vi giống nhau. Kafka có topic, partition, offset và consumer group; RabbitMQ thường tổ chức luồng qua exchange, queue và acknowledgement; Pulsar có topic, subscription và các chế độ subscription riêng. Binder chuyển đổi giữa mô hình binding chung và cơ chế của broker, nhưng những khác biệt về thứ tự, lưu trữ, phân phối, giao nhận và giao dịch vẫn cần được thiết kế có chủ đích.

## 2. Vai trò của từng thành phần trong hệ sinh thái Spring

### 2.1. Spring Boot: nền tảng chạy ứng dụng

Spring Boot giúp đóng gói và chạy ứng dụng Spring với cấu hình tự động, dependency injection, quản lý bean, cấu hình bên ngoài và tích hợp với các thành phần vận hành như Actuator.

Trong một ứng dụng Spring Cloud Stream, Spring Boot đảm nhiệm các công việc nền tảng:

- Khởi tạo ApplicationContext và các bean.
- Nạp cấu hình từ YAML, properties, biến môi trường hoặc hệ thống cấu hình.
- Kích hoạt auto-configuration dựa trên dependency và cấu hình hiện có.
- Quản lý vòng đời ứng dụng, logging, health check và metrics khi được cấu hình.
- Đóng gói ứng dụng để chạy trong container hoặc môi trường triển khai khác.

Spring Boot không tự định nghĩa cách một message được phân phối tới topic hay queue. Nó cung cấp môi trường để Spring Cloud Function, Spring Integration và Spring Cloud Stream hoạt động.

### 2.2. Spring Cloud Function: mô hình hóa logic bằng hàm

Spring Cloud Function đưa các kiểu hàm Java quen thuộc vào mô hình ứng dụng Spring:

| Kiểu hàm | Đầu vào | Đầu ra | Cách sử dụng điển hình |
|---|---|---|---|
| Supplier<T> | Không có đầu vào từ message | T | Phát sinh sự kiện hoặc dữ liệu theo lịch polling |
| Function<T, R> | T | R | Biến đổi, kiểm tra hoặc làm giàu dữ liệu |
| Consumer<T> | T | Không có đầu ra | Ghi nhận, lưu trữ hoặc thực hiện tác vụ phụ |

Một hàm có thể tập trung vào quy tắc nghiệp vụ mà không cần biết message được nhận từ Kafka hay RabbitMQ. Spring Cloud Function quản lý việc phát hiện và gọi các bean hàm trong môi trường Spring, đồng thời hỗ trợ các kiểu dữ liệu như Message<T> khi logic cần đọc hoặc tạo header.

Ví dụ, hàm kiểm tra đơn hàng có thể nhận một đối tượng miền và trả về kết quả đã xác thực:

~~~java
@Configuration
class OrderFunctions {

    @Bean
    Function<OrderCreated, OrderValidated> validateOrder() {
        return order -> {
            if (order.total() <= 0) {
                throw new IllegalArgumentException("Order total must be positive");
            }
            return new OrderValidated(order.id(), order.customerId(), order.total());
        };
    }
}

record OrderCreated(String id, String customerId, long total) {}

record OrderValidated(String id, String customerId, long total) {}
~~~

Hàm trên mô tả phép biến đổi dữ liệu. Nó không mở kết nối broker, không chọn topic và không tự xác định consumer group. Những việc đó thuộc lớp binding và binder.

Supplier có cách vận hành khác hai kiểu còn lại: vì không có message đầu vào để kích hoạt, nó thường được gọi bởi một poller. Do đó, cần cấu hình chu kỳ polling và cân nhắc tải phát sinh. Một Supplier tạo sự kiện theo thời gian không nên được xem là nguồn dữ liệu vô hạn mà không có giới hạn tốc độ, cơ chế dừng hoặc chiến lược phục hồi phù hợp.

### 2.3. Spring Integration: các mẫu tích hợp dựa trên message

Spring Integration cung cấp mô hình message và các mẫu Enterprise Integration Patterns để kết nối, định tuyến và biến đổi dữ liệu giữa các thành phần. Những khái niệm thường gặp gồm:

- Message: payload đi kèm header.
- MessageChannel: đường truyền message giữa các thành phần trong ứng dụng.
- Transformer: biến đổi payload hoặc header.
- Filter: chỉ cho message thỏa điều kiện đi tiếp.
- Router: chọn luồng xử lý dựa trên nội dung hoặc header.
- Service Activator: gọi một thành phần nghiệp vụ khi message đến.
- Adapter và gateway: kết nối với hệ thống hoặc API bên ngoài.

Spring Integration phù hợp khi luồng xử lý trong ứng dụng có nhiều bước định tuyến, chuyển đổi, kết hợp hoặc tích hợp với nhiều giao thức. Spring Cloud Stream sử dụng các trừu tượng messaging của hệ sinh thái Spring và kết nối chúng với broker thông qua binder.

Có thể hình dung Spring Integration là bộ công cụ xây dựng luồng tích hợp trong ứng dụng, còn Spring Cloud Stream tập trung vào mô hình ứng dụng hướng sự kiện và việc kết nối các luồng đó với hệ thống messaging bên ngoài. Hai công nghệ có thể được dùng cùng nhau khi bài toán cần cả xử lý nội bộ phức tạp lẫn giao tiếp qua broker.

### 2.4. Spring Cloud Stream: binding và binder

Spring Cloud Stream bổ sung mô hình binding cho đầu vào và đầu ra của ứng dụng:

- **Binding** là cấu hình liên kết một đầu vào hoặc đầu ra logic của ứng dụng với một destination.
- **Destination** là tên tài nguyên messaging được binder ánh xạ sang khái niệm tương ứng của broker, ví dụ topic của Kafka hoặc exchange/queue theo cách binder RabbitMQ tổ chức.
- **Binder** là lớp tích hợp đặc thù cho một hệ thống messaging. Binder tạo và cấu hình kết nối, gửi hoặc nhận message, đồng thời ánh xạ các thuộc tính chung sang cấu hình của broker.

Ứng dụng thường khai báo một bean hàm và cấu hình binding có tên theo quy ước. Spring Cloud Stream tìm hàm, tạo binding tương ứng và dùng binder đang được chọn để kết nối với broker.

### 2.5. Bảng phân biệt nhanh

| Thành phần | Câu hỏi chính mà thành phần trả lời | Trách nhiệm tiêu biểu |
|---|---|---|
| Spring Boot | Ứng dụng được khởi tạo và vận hành thế nào? | Auto-configuration, bean, cấu hình, vòng đời, Actuator |
| Spring Cloud Function | Logic xử lý sự kiện được biểu diễn ra sao? | Supplier, Function, Consumer, function composition |
| Spring Integration | Message đi qua các bước tích hợp nội bộ thế nào? | Channel, router, filter, transformer, adapter |
| Spring Cloud Stream | Hàm kết nối với hệ thống messaging ra sao? | Binding, destination, binder, consumer group, partition và xử lý lỗi |
| Kafka/RabbitMQ/Pulsar | Message được lưu trữ và phân phối thế nào? | Cơ chế vận chuyển, lưu trữ, phân vùng, subscription và acknowledgement |

## 3. Đường đi của message trong một ứng dụng

Một luồng xử lý điển hình có thể mô tả như sau:

~~~mermaid
flowchart LR
    A[Spring Boot khởi tạo ứng dụng] --> B[Spring Cloud Function phát hiện bean hàm]
    B --> C[Spring Cloud Stream tạo binding]
    C --> D[Binder cụ thể]
    D --> E[(Kafka / RabbitMQ / Pulsar)]
    E --> F[Binder phía consumer]
    F --> G[Input binding]
    G --> H[Function hoặc Consumer]
    H --> I[Logic nghiệp vụ]
~~~

Khi ứng dụng khởi động, Spring Boot tạo context và các bean. Spring Cloud Function phát hiện các bean có kiểu hàm. Spring Cloud Stream dựa trên định nghĩa hàm và cấu hình để xác định binding đầu vào, đầu ra. Binder được chọn tạo kết nối tới broker và thiết lập các destination cần thiết theo khả năng của binder.

Khi producer gửi một đối tượng, lớp messaging chuyển đối tượng thành message. Message có payload và có thể có header như content type, correlation ID hoặc thông tin phục vụ định tuyến. Binder chuyển message tới destination. Ở phía nhận, binder nhận message từ broker, chuyển thành message của Spring, sau đó Spring Cloud Function gọi hàm đã đăng ký.

Nếu hàm là Function<T, R>, kết quả có thể được gửi ra output binding tương ứng. Nếu hàm là Consumer<T>, luồng kết thúc sau khi consumer xử lý. Nếu hàm là Supplier<T>, poller gọi hàm để tạo dữ liệu và đưa kết quả ra output binding.

Các bước chuyển đổi payload và quản lý header cần được hiểu rõ. Một message JSON nhận từ broker phải được chuyển thành kiểu Java mà hàm mong đợi. Cấu hình content type, message converter và schema cần nhất quán giữa producer và consumer.

## 4. Mô hình hàm và quy ước binding

### 4.1. Ba dạng hàm cơ bản

Ví dụ sau minh họa ba loại bean hàm trong cùng một ứng dụng:

~~~java
@Configuration
class EventFunctions {

    @Bean
    Supplier<Heartbeat> heartbeat() {
        return () -> new Heartbeat(Instant.now());
    }

    @Bean
    Function<OrderCreated, OrderValidated> validateOrder() {
        return order -> {
            if (order.total() <= 0) {
                throw new IllegalArgumentException("Invalid order total");
            }
            return new OrderValidated(order.id(), order.customerId(), order.total());
        };
    }

    @Bean
    Consumer<OrderValidated> auditOrder() {
        return order -> System.out.println("Validated order: " + order.id());
    }
}

record Heartbeat(Instant generatedAt) {}
~~~

Trong ví dụ:

- heartbeat tạo dữ liệu và chỉ có output.
- validateOrder nhận dữ liệu ở input, xử lý và phát kết quả ở output.
- auditOrder chỉ nhận dữ liệu và không tạo output binding.

Supplier thường được gọi bởi poller theo chu kỳ. Function và Consumer thường được kích hoạt khi có message đến input binding. Nếu một ứng dụng có nhiều bean hàm, nên chỉ rõ hàm cần bind để tránh việc chọn nhầm hoặc không xác định được hàm.

### 4.2. Đặt tên binding

Với mô hình hàm, Spring Cloud Stream suy ra tên binding từ tên bean và vị trí đầu vào/đầu ra:

| Bean hàm | Binding |
|---|---|
| Supplier<T> heartbeat | heartbeat-out-0 |
| Function<T, R> validateOrder | validateOrder-in-0, validateOrder-out-0 |
| Consumer<T> auditOrder | auditOrder-in-0 |

Hậu tố -in-0 và -out-0 thể hiện hướng và chỉ số của cổng dữ liệu. Với hàm nhiều đầu vào hoặc nhiều đầu ra, chỉ số giúp phân biệt từng binding. Tên binding là tên logic trong cấu hình ứng dụng; nó không bắt buộc phải trùng với tên topic hoặc queue thực tế.

### 4.3. Khai báo hàm cần sử dụng

Khi ứng dụng có nhiều bean Supplier, Function hoặc Consumer, hãy khai báo rõ hàm cần kích hoạt:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
~~~

Nếu không chỉ rõ, ứng dụng có thể gặp tình huống không xác định được hàm phù hợp hoặc chỉ một tập hàm được phát hiện được bind theo quy tắc mặc định. Khai báo tường minh giúp cấu hình dễ đọc và tránh việc một bean mới được thêm vào làm thay đổi hành vi ngoài dự kiến.

Spring Cloud Function cũng hỗ trợ kết hợp các hàm. Ví dụ, một hàm kiểm tra có thể nối với hàm làm giàu dữ liệu để tạo thành một pipeline logic. Khi dùng composition, cần kiểm tra tên hàm tổng hợp và tên binding mà phiên bản thư viện đang sử dụng tạo ra; không nên tự suy đoán tên output từ tên các hàm thành phần.

### 4.4. Cấu hình binding với destination

Ví dụ cấu hình một hàm xử lý sự kiện đơn hàng:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: order-validation
          content-type: application/json
        validateOrder-out-0:
          destination: orders.validated
          content-type: application/json
~~~

Trong cấu hình này:

- validateOrder-in-0 nhận sự kiện từ destination orders.created.
- group xác định nhóm consumer cho input binding.
- validateOrder-out-0 gửi kết quả tới destination orders.validated.
- content-type khai báo định dạng nội dung để lớp chuyển đổi message xử lý payload đúng cách.

Binding tách tên logic khỏi destination. Khi cần đổi tên topic hoặc chuyển sang một môi trường khác, có thể thay đổi cấu hình mà không phải sửa tên bean hay logic nghiệp vụ.

## 5. Binder và khả năng kết nối nhiều broker

### 5.1. Binder làm gì?

Binder là phần triển khai kết nối giữa Spring Cloud Stream và một hệ thống messaging. Binder thường đảm nhiệm:

- Tạo và quản lý producer, consumer hoặc các thành phần tương đương.
- Ánh xạ binding tới destination của broker.
- Hỗ trợ provisioning tài nguyên khi broker và cấu hình cho phép.
- Chuyển message giữa mô hình Spring và API của broker.
- Áp dụng các thuộc tính chung như group, concurrency, partition và retry.
- Cung cấp các thuộc tính riêng để khai thác khả năng đặc thù của broker.

Ứng dụng có thể dùng nhiều binder trong cùng một tiến trình nếu dependency và cấu hình hỗ trợ. Khi đó, từng binding có thể được chỉ định binder tương ứng. Ví dụ cấu hình khái quát:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        validateOrder-in-0:
          binder: kafkaPrimary
        auditOrder-in-0:
          binder: rabbitInternal
      binders:
        kafkaPrimary:
          type: kafka
        rabbitInternal:
          type: rabbit
~~~

Khai báo trên chỉ minh họa cách chọn binder. Địa chỉ broker, thông tin xác thực, TLS, virtual host và các thiết lập kết nối phải được cấu hình theo tài liệu của binder tương ứng, thường thông qua cấu hình bên ngoài hoặc biến môi trường. Không nên ghi thông tin bí mật trực tiếp vào mã nguồn.

### 5.2. Kafka binder

Kafka binder ánh xạ binding tới topic và sử dụng các khái niệm của Kafka như partition, offset, consumer group và broker cluster. Các quyết định quan trọng khi triển khai gồm:

- Chọn số partition phù hợp với throughput và mức song song mong muốn.
- Đặt group ổn định cho consumer cần nhận dữ liệu liên tục.
- Chọn key để các sự kiện cùng một thực thể có thể được định tuyến về cùng partition.
- Xác định chính sách offset, retry, DLQ và giao dịch.
- Theo dõi consumer lag, rebalance và tình trạng partition.

Kafka phù hợp với luồng sự kiện cần lưu trữ theo thời gian, đọc lại dữ liệu và xử lý theo partition. Tuy nhiên, ứng dụng cần hiểu rằng thứ tự được đảm bảo trong phạm vi một partition, không phải thứ tự toàn cục giữa mọi partition.

### 5.3. RabbitMQ binder

RabbitMQ binder ánh xạ binding sang các cấu trúc như exchange và queue. Exchange định tuyến message tới queue theo loại exchange và binding rule; consumer đọc từ queue và xác nhận message theo cơ chế acknowledgement.

Khi dùng RabbitMQ, cần quan tâm đến:

- Loại exchange và quy tắc binding phù hợp với mô hình định tuyến.
- Queue bền vững, message bền vững và chính sách lưu trữ.
- Acknowledgement, prefetch và số consumer đồng thời.
- Dead-letter exchange, dead-letter queue và chính sách retry.
- Cấu hình publisher confirm và xử lý tình huống broker từ chối hoặc mất kết nối.

Một destination trong cấu hình Spring Cloud Stream không có nghĩa là mọi broker đều tạo cùng một loại tài nguyên. Với RabbitMQ, binder quyết định cách destination, group và queue được ánh xạ theo quy ước của binder.

### 5.4. Pulsar binder

Pulsar có mô hình topic và subscription, hỗ trợ nhiều kiểu subscription và cơ chế lưu trữ/phân phối riêng. Khi tích hợp qua Spring Cloud Stream, cần chọn binder Pulsar phù hợp với phiên bản Spring Cloud Stream và hệ sinh thái thư viện đang dùng.

Mức độ hỗ trợ, tên artifact, các thuộc tính cấu hình và khả năng tương thích của binder Pulsar có thể khác theo phiên bản hoặc nhà cung cấp. Vì vậy, hãy kiểm tra tài liệu và ma trận tương thích của đúng phiên bản trước khi chọn dependency. Nếu không có binder tương thích, có thể cân nhắc Spring Pulsar hoặc adapter Spring Integration để tích hợp trực tiếp, nhưng khi đó ranh giới trừu tượng và cách quản lý message sẽ khác.

### 5.5. Trừu tượng hóa không xóa bỏ khác biệt của broker

Có thể giữ nguyên một phần lớn bean hàm khi đổi binder, nhưng không nên giả định rằng chỉ cần thay type: kafka thành type: rabbit là toàn bộ hệ thống giữ nguyên ngữ nghĩa. Cần rà soát ít nhất:

| Khía cạnh | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| Đơn vị lưu trữ/định tuyến thường gặp | Topic và partition | Exchange, queue và binding | Topic và subscription |
| Tiến độ consumer | Offset theo partition | Acknowledgement của message | Cursor/acknowledgement theo subscription |
| Song song | Phân phối partition trong group | Nhiều consumer đọc queue | Phụ thuộc kiểu subscription và partition |
| Đọc lại dữ liệu | Có thể đọc lại theo offset trong thời gian lưu giữ | Phụ thuộc queue và cấu hình lưu trữ | Phụ thuộc retention và subscription |
| Cấu hình lỗi | Retry, offset, DLQ theo binder | Requeue, DLX/DLQ, acknowledgement | Redelivery và dead-letter policy theo binder |

Bảng trên là định hướng khái niệm, không thay thế tài liệu vận hành của từng broker. Khi chuyển broker, cần kiểm thử lại thứ tự, khả năng đọc lại, retry, DLQ, partitioning và giao dịch.

## 6. Message, header, content type và schema

### 6.1. Payload và header

Message trong Spring có hai phần:

- **Payload**: dữ liệu nghiệp vụ, chẳng hạn OrderCreated.
- **Header**: metadata đi kèm, chẳng hạn content type, correlation ID, partition key hoặc thông tin phục vụ tracing.

Khi chỉ cần dữ liệu nghiệp vụ, hàm có thể nhận trực tiếp kiểu payload. Khi cần đọc hoặc giữ lại header, có thể dùng Message<T>:

~~~java
@Bean
Function<Message<OrderCreated>, Message<OrderValidated>> validateWithHeaders() {
    return message -> {
        OrderCreated order = message.getPayload();
        OrderValidated result =
                new OrderValidated(order.id(), order.customerId(), order.total());

        return MessageBuilder.withPayload(result)
                .copyHeadersIfAbsent(message.getHeaders())
                .build();
    };
}
~~~

Chỉ nên truyền tiếp những header thực sự có ý nghĩa ở luồng sau. Không nên sao chép mù quáng mọi header từ broker hoặc từ message đầu vào vì một số header có thể mang ý nghĩa riêng của transport, chứa dữ liệu nhạy cảm hoặc gây xung đột với header do binder tạo.

### 6.2. Content type và chuyển đổi dữ liệu

Producer và consumer phải thống nhất cách biểu diễn payload. Với JSON, cấu hình application/json giúp Spring chọn cơ chế chuyển đổi phù hợp. Nếu producer gửi JSON nhưng consumer lại xử lý như chuỗi hoặc byte array mà không có chuyển đổi tương ứng, ứng dụng có thể gặp lỗi kiểu dữ liệu hoặc lỗi parse.

Một số nguyên tắc thực hành:

- Dùng kiểu payload có ý nghĩa nghiệp vụ thay vì truyền chuỗi JSON xuyên suốt mọi hàm.
- Xác định rõ content type tại binding hoặc message khi cần.
- Tránh serialize một đối tượng thành JSON string rồi để framework serialize lần nữa thành chuỗi JSON có dấu nháy và ký tự escape.
- Kiểm thử cả trường hợp payload hợp lệ, thiếu field, sai kiểu và dữ liệu không tương thích.
- Không xem header là nơi thay thế cho schema của payload.

### 6.3. Thiết kế schema và tương thích phiên bản

Sự kiện thường được nhiều dịch vụ tiêu thụ trong thời gian dài. Vì vậy, schema cần được thiết kế theo hướng hỗ trợ tiến hóa:

- Thêm field tùy chọn có giá trị mặc định thường an toàn hơn đổi tên hoặc đổi kiểu field hiện có.
- Consumer nên chịu được field mới mà nó chưa sử dụng.
- Không tái sử dụng tên field với ý nghĩa khác.
- Xác định quy tắc tương thích ngược và tương thích xuôi trước khi triển khai producer hoặc consumer mới.
- Nếu dùng schema registry, phải cấu hình và kiểm thử serializer/deserializer tương ứng với binder và định dạng schema đã chọn.

Schema registry là một khả năng phụ thuộc hệ sinh thái broker và cấu hình tích hợp. Không phải mọi binder đều có cùng cách hỗ trợ hoặc cùng thuộc tính cấu hình.

## 7. Consumer group, partition và khả năng mở rộng

### 7.1. Consumer group

Consumer group mô tả một nhóm consumer cùng xử lý một luồng dữ liệu theo cơ chế phân phối của broker. Trong Kafka, các consumer cùng group chia nhau các partition của topic. Hai group khác nhau có thể đọc độc lập cùng một topic, nhờ đó hai dịch vụ có thể cùng nhận một sự kiện mà không phải gửi hai bản sao từ producer.

Ví dụ:

- Group order-validation nhận sự kiện để xác thực đơn hàng.
- Group order-notification nhận cùng sự kiện để gửi thông báo.

Mỗi dịch vụ có mục đích xử lý riêng nên dùng group riêng. Nếu nhiều instance cùng phục vụ một chức năng, chúng thường dùng chung group để broker phân phối tải giữa các instance.

Trong Spring Cloud Stream, có thể đặt group trên input binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: order-validation
~~~

Nếu không khai báo group, binder có thể tạo nhóm consumer ẩn danh hoặc tài nguyên tạm theo quy tắc riêng. Hành vi này thường không phù hợp với consumer cần tiếp tục nhận dữ liệu sau khi khởi động lại. Với luồng xử lý bền vững, hãy đặt group có tên ổn định và hiểu rõ cách binder ánh xạ group sang broker.

### 7.2. Partition và thứ tự xử lý

Partition chia một luồng dữ liệu thành nhiều phần để tăng khả năng ghi và đọc song song. Với Kafka, mỗi partition có thứ tự riêng. Nếu các sự kiện của cùng một đơn hàng cần được xử lý theo thứ tự, producer nên dùng một key ổn định như orderId để những sự kiện đó được đưa về cùng partition.

Spring Cloud Stream hỗ trợ cấu hình partition key và số partition ở producer. Ví dụ khái quát:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          producer:
            partition-key-expression: payload.customerId
            partition-count: 6
~~~

Biểu thức key phải phù hợp với payload thực tế. Nếu chọn key có cardinality thấp, một số partition có thể nhận phần lớn lưu lượng và trở thành điểm nghẽn. Nếu chọn key thay đổi giữa các sự kiện của cùng một thực thể, thứ tự xử lý theo thực thể có thể bị phá vỡ.

### 7.3. Concurrency và số instance

Có thể tăng concurrency của consumer hoặc chạy nhiều instance ứng dụng. Tuy nhiên, tăng số luồng không luôn làm tăng throughput:

- Với Kafka, trong cùng một consumer group, một partition tại một thời điểm chỉ được gán cho một consumer. Số consumer hoạt động hữu ích vì thế bị giới hạn bởi số partition.
- Với RabbitMQ, số consumer, prefetch và thời gian xử lý ảnh hưởng tới tốc độ phân phối và mức công bằng giữa consumer.
- Với Pulsar, mức song song phụ thuộc kiểu subscription, số partition và cách binder triển khai consumer.

Khi scale, cần cân bằng số partition, số instance, concurrency, tài nguyên CPU/bộ nhớ và thời gian xử lý. Theo dõi lag hoặc độ sâu queue để biết hệ thống có theo kịp tốc độ phát sinh sự kiện hay không.

## 8. Retry, DLQ và xử lý lỗi

### 8.1. Phân loại lỗi

Không phải lỗi nào cũng nên retry:

- **Lỗi tạm thời**: timeout, mất kết nối ngắn hạn hoặc dịch vụ phụ thuộc đang quá tải. Retry có backoff có thể giúp xử lý thành công.
- **Lỗi dữ liệu**: payload sai định dạng, thiếu trường bắt buộc hoặc vi phạm quy tắc nghiệp vụ. Retry không thay đổi dữ liệu thường không giải quyết được vấn đề.
- **Lỗi lập trình**: lỗi bất ngờ trong logic. Cần log, cảnh báo và xử lý theo chính sách phù hợp; retry liên tục có thể làm tăng tải.

Một cấu hình retry chung có thể đặt số lần thử và backoff:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        validateOrder-in-0:
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2
~~~

Các thuộc tính trên mô tả chính sách retry ở tầng consumer. Cách retry tương tác với acknowledgement, transaction và redelivery còn phụ thuộc binder. Cần xác minh chính sách thực tế trong broker, đặc biệt khi kết hợp retry của framework với retry hoặc redelivery do broker quản lý.

### 8.2. Dead-letter queue

Khi message vẫn thất bại sau số lần thử cho phép, hệ thống có thể chuyển message sang DLQ hoặc dead-letter destination để điều tra và xử lý sau. DLQ giúp message lỗi không chặn mãi luồng chính, đồng thời giữ lại dữ liệu để phân tích.

Ví dụ, Kafka binder có cấu hình DLQ riêng cho consumer:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          validateOrder-in-0:
            consumer:
              enable-dlq: true
~~~

Đây là thuộc tính đặc thù của Kafka binder; không nên sao chép nguyên cấu hình này sang RabbitMQ hoặc Pulsar. RabbitMQ thường dùng dead-letter exchange và dead-letter queue; Pulsar có dead-letter policy theo subscription và khả năng của binder tương ứng.

Một quy trình DLQ có trách nhiệm cần xác định:

1. Điều kiện nào khiến message bị chuyển vào DLQ.
2. Metadata nào được giữ lại để biết nguồn, lỗi, thời điểm và số lần thử.
3. Ai hoặc thành phần nào theo dõi DLQ và cảnh báo khi có message mới.
4. Cách sửa dữ liệu hoặc logic trước khi phát lại.
5. Cách tránh phát lại lặp vô hạn cùng một message lỗi.

Không nên tự động phát lại toàn bộ DLQ mà không phân loại nguyên nhân. Một message không hợp lệ có thể tiếp tục thất bại và tạo vòng lặp gây tải.

### 8.3. Idempotency và bảo đảm giao nhận

Trong hệ thống phân tán, một message có thể được giao lại khi consumer xử lý xong nhưng chưa xác nhận thành công, khi kết nối bị gián đoạn hoặc khi consumer khởi động lại. Vì vậy, consumer nên được thiết kế để xử lý lặp an toàn.

Idempotency có nghĩa là xử lý cùng một sự kiện nhiều lần vẫn tạo ra kết quả nghiệp vụ tương đương với xử lý một lần. Một số cách triển khai:

- Gán event ID duy nhất và lưu dấu các event đã xử lý.
- Dùng unique constraint hoặc khóa nghiệp vụ trong cơ sở dữ liệu.
- Thiết kế thao tác cập nhật theo trạng thái đích thay vì cộng dồn không kiểm soát.
- Dùng inbox table để ghi nhận message trước khi thực hiện tác động nghiệp vụ.
- Dùng transactional outbox khi cần ghi thay đổi nghiệp vụ và sự kiện phát ra trong cùng một giao dịch cơ sở dữ liệu.

Không nên mặc định rằng binding bảo đảm exactly-once cho toàn bộ nghiệp vụ. Cơ chế giao nhận phụ thuộc broker, binder, cấu hình acknowledgement/transaction và phạm vi tác động của consumer. Ngay cả khi Kafka Streams hỗ trợ xử lý exactly-once trong phạm vi Kafka, một lời gọi HTTP hoặc một giao dịch tới cơ sở dữ liệu bên ngoài vẫn cần chiến lược nhất quán riêng.

## 9. Xử lý có trạng thái với Kafka Streams

Các hàm Supplier, Function, Consumer thông thường phù hợp với xử lý từng message. Một số bài toán cần trạng thái tích lũy theo khóa, cửa sổ thời gian hoặc phép tổng hợp liên tục. Kafka Streams cung cấp mô hình xử lý stream có trạng thái cho các trường hợp này; Spring Cloud Stream có Kafka Streams binder để tích hợp mô hình đó với ứng dụng Spring.

Kafka Streams phân biệt một số kiểu dữ liệu quan trọng:

- KStream: luồng các bản ghi, mỗi bản ghi là một sự kiện độc lập.
- KTable: biểu diễn trạng thái mới nhất theo key, gần với một bảng được cập nhật liên tục.
- GlobalKTable: bảng trạng thái được sao chép tới các instance theo mô hình Kafka Streams.

Ví dụ, hệ thống có thể đếm số đơn hàng theo khách hàng bằng cách nhóm sự kiện theo customerId rồi tổng hợp:

~~~java
@Bean
Function<KStream<String, OrderCreated>, KTable<String, Long>> countOrdersByCustomer(
        Serde<OrderCreated> orderSerde) {

    return orders -> orders
            .groupBy(
                    (key, order) -> order.customerId(),
                    Grouped.with(Serdes.String(), orderSerde))
            .count(Materialized.as("orders-by-customer"));
}
~~~

Đây là ví dụ minh họa ý tưởng; ứng dụng thực tế cần khai báo Serde phù hợp cho key và value, cấu hình binding Kafka Streams và kiểm thử topology với đúng phiên bản binder.

### 9.1. State store và khôi phục trạng thái

Kafka Streams có thể lưu trạng thái xử lý trong state store cục bộ. Để khôi phục trạng thái sau khi instance lỗi hoặc chuyển sang máy khác, Kafka Streams sử dụng changelog topic và các cơ chế nội bộ liên quan. Khi một instance mới nhận partition, nó có thể phục hồi state store từ dữ liệu đã lưu trên Kafka.

Vì trạng thái gắn với topology và cấu hình ứng dụng, cần chú ý:

- Đặt application.id ổn định và phù hợp với topology; các ứng dụng xử lý độc lập không nên vô tình dùng chung ID.
- Cấp quyền truy cập và dung lượng lưu trữ cần thiết cho state store và các topic nội bộ.
- Dùng Serde tương thích với dữ liệu đã ghi để có thể phục hồi sau khi nâng cấp.
- Lập kế hoạch thay đổi topology, tên store và schema vì chúng có thể ảnh hưởng tới khả năng phục hồi.
- Theo dõi thời gian restore và trạng thái rebalance khi triển khai hoặc scale.

### 9.2. Exactly-once trong Kafka Streams

Kafka Streams có cấu hình processing guarantee để kiểm soát tính nhất quán giữa việc đọc offset, cập nhật state và ghi kết quả Kafka. Mức bảo đảm khả dụng phụ thuộc phiên bản Kafka và cấu hình. Phạm vi này không tự động bao phủ side effect bên ngoài Kafka, ví dụ cập nhật một hệ thống thanh toán qua HTTP.

Nếu topology vừa ghi dữ liệu Kafka vừa gọi hệ thống ngoài, cần thiết kế idempotency, outbox/inbox hoặc một quy trình bù trừ phù hợp. Không nên diễn giải exactly-once thành cam kết toàn hệ thống rằng mọi side effect chỉ xảy ra đúng một lần.

## 10. Kiểm thử ứng dụng Spring Cloud Stream

Một chiến lược kiểm thử tốt chia thành nhiều lớp để phát hiện lỗi sớm mà không phụ thuộc broker thật trong mọi bài test.

### 10.1. Unit test cho hàm nghiệp vụ

Vì logic được biểu diễn bằng hàm Java, có thể gọi trực tiếp hàm trong unit test. Kiểm tra các trường hợp hợp lệ, dữ liệu biên và lỗi nghiệp vụ:

~~~java
class ValidateOrderTest {

    @Test
    void rejectsOrderWithNonPositiveTotal() {
        Function<OrderCreated, OrderValidated> function =
                order -> {
                    if (order.total() <= 0) {
                        throw new IllegalArgumentException("Invalid order total");
                    }
                    return new OrderValidated(
                            order.id(), order.customerId(), order.total());
                };

        assertThrows(
                IllegalArgumentException.class,
                () -> function.apply(new OrderCreated("o-1", "c-1", 0)));
    }
}
~~~

Unit test tập trung vào quy tắc nghiệp vụ, không cần khởi tạo Spring context hay broker.

### 10.2. Kiểm thử binding bằng test binder

Spring Cloud Stream cung cấp test binder để kiểm tra luồng message trong bộ nhớ. Test có thể gửi message vào input binding và đọc message từ output binding mà không cần broker bên ngoài.

Ví dụ cấu trúc kiểm thử:

~~~java
@SpringBootTest
class OrderStreamTest {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void validatesIncomingOrder() {
        OrderCreated order = new OrderCreated("o-1", "c-1", 2500);
        Message<OrderCreated> message = MessageBuilder
                .withPayload(order)
                .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
                .build();

        input.send(message, "validateOrder-in-0");

        Message<byte[]> result =
                output.receive(1000, "validateOrder-out-0");

        assertNotNull(result);
    }
}
~~~

Test binder giúp kiểm tra wiring, tên binding và một phần chuyển đổi message. Nó không mô phỏng đầy đủ partition assignment, acknowledgement, broker outage, transaction hoặc DLQ của broker thật.

### 10.3. Integration test với broker thật

Với những hành vi phụ thuộc broker, nên có integration test dùng broker tương ứng, thường có thể khởi chạy bằng Testcontainers trong pipeline kiểm thử:

- Kafka: kiểm tra partition, consumer group, offset, retry và DLQ.
- RabbitMQ: kiểm tra exchange, queue, acknowledgement, routing và dead-letter.
- Pulsar: kiểm tra subscription, redelivery và dead-letter policy.
- Kafka Streams: kiểm tra topology, state store, restore và kết quả sau khi khởi động lại.

Kiểm thử cần xác minh cả kết quả thành công lẫn hành vi khi broker mất kết nối, consumer dừng đột ngột, message lỗi hoặc cùng message được giao lại.

## 11. Triển khai và vận hành

Một ứng dụng chạy được trên máy phát triển chưa đủ để bảo đảm luồng sự kiện ổn định khi triển khai. Cần đưa các đặc tính vận hành vào thiết kế từ đầu.

### 11.1. Quản lý cấu hình theo môi trường

Đưa broker endpoint, credentials, TLS, tên destination và các giới hạn tài nguyên ra cấu hình môi trường. Dùng secret manager hoặc cơ chế quản lý bí mật của nền tảng triển khai cho thông tin xác thực. Giữ tên binding logic ổn định giữa các môi trường khi có thể, đồng thời thay destination theo môi trường.

Không đưa mật khẩu, token hoặc certificate private key vào repository. Hãy kiểm tra cấu hình thực tế của container hoặc pod đã nhận đúng giá trị trước khi đưa traffic vào.

### 11.2. Health, metrics và tracing

Nên theo dõi:

- Tình trạng kết nối và health của binder/broker.
- Số message nhận, gửi, xử lý thành công và thất bại.
- Thời gian xử lý và tỷ lệ lỗi theo binding.
- Consumer lag hoặc queue depth.
- Số lần retry, số message trong DLQ và tuổi của message cũ nhất.
- Số lần rebalance, trạng thái restore của Kafka Streams và tài nguyên state store.

Actuator có thể cung cấp health và metrics ở mức ứng dụng; các chỉ số chi tiết còn phụ thuộc binder, broker exporter và hệ thống quan sát. Correlation ID hoặc trace context giúp nối log của producer, broker và consumer thành một luồng điều tra thống nhất. Cần tránh ghi toàn bộ payload hoặc dữ liệu nhạy cảm vào log.

### 11.3. Scale và graceful shutdown

Khi tăng instance, broker có thể phân phối lại partition hoặc consumer. Khi dừng ứng dụng, consumer cần có thời gian hoàn tất hoặc nhường lại message theo cơ chế acknowledgement phù hợp. Cấu hình thời gian shutdown, timeout của nền tảng và thời gian xử lý message cần thống nhất.

Không nên tăng concurrency vượt xa khả năng phân phối của broker hoặc số partition hữu ích. Với tác vụ xử lý lâu, cần đo thời gian xử lý thực tế và kiểm tra hành vi khi instance bị dừng giữa chừng.

### 11.4. Giao dịch và tính nhất quán dữ liệu

Một consumer có thể cần vừa cập nhật cơ sở dữ liệu vừa phát một sự kiện mới. Nếu hai thao tác không nằm trong cùng một transaction được hỗ trợ, có thể xuất hiện trạng thái chỉ cập nhật database nhưng chưa phát event, hoặc đã phát event nhưng database rollback.

Transactional outbox là một mẫu phổ biến: ghi thay đổi nghiệp vụ và bản ghi outbox trong cùng transaction database; một tiến trình riêng đọc outbox và phát message. Consumer tiếp nhận cũng nên idempotent. Mẫu này giúp giảm khoảng trống nhất quán giữa database và broker mà không giả định có một transaction phân tán bao trùm mọi hệ thống.

## 12. Khi nào dùng từng thành phần?

Các công nghệ trong hệ sinh thái có thể được kết hợp theo độ phức tạp của bài toán:

| Nhu cầu | Thành phần phù hợp |
|---|---|
| Xây dựng ứng dụng Spring, quản lý bean và cấu hình môi trường | Spring Boot |
| Viết logic xử lý có thể gọi độc lập và tái sử dụng ở nhiều runtime | Spring Cloud Function |
| Kết nối, định tuyến, lọc hoặc biến đổi message giữa nhiều thành phần nội bộ | Spring Integration |
| Bind hàm với Kafka, RabbitMQ hoặc binder messaging khác; cấu hình group, partition và consumer | Spring Cloud Stream |
| Xử lý stream có trạng thái, window, aggregate và state store trên Kafka | Kafka Streams cùng Kafka Streams binder |

Với một luồng đơn giản nhận sự kiện, biến đổi và phát kết quả, mô hình hàm kết hợp Spring Cloud Stream thường dễ đọc và dễ kiểm thử. Khi luồng tích hợp có nhiều nhánh, bộ định tuyến, bộ lọc hoặc giao thức khác nhau, có thể dùng Spring Integration cho phần orchestration nội bộ. Khi cần trạng thái liên tục và phép tổng hợp theo key hoặc cửa sổ thời gian trên Kafka, hãy cân nhắc Kafka Streams.

## 13. Những lỗi thiết kế thường gặp

1. **Để logic nghiệp vụ phụ thuộc trực tiếp vào API broker**: điều này làm giảm khả năng thay đổi binder và khó unit test. Hãy giữ logic trong hàm và giới hạn mã đặc thù broker ở cấu hình hoặc adapter cần thiết.
2. **Không khai báo rõ function definition khi có nhiều bean hàm**: ứng dụng có thể bind sai hoặc không bind được hàm mong muốn. Hãy chỉ rõ định nghĩa hàm và kiểm tra binding khi khởi động.
3. **Nhầm tên binding với tên destination**: binding là tên logic của cổng vào/ra; destination là tài nguyên messaging được binder ánh xạ.
4. **Dùng group ngẫu nhiên cho consumer cần lưu tiến độ**: khi khởi động lại, consumer có thể không tiếp tục từ tiến độ mong muốn. Hãy đặt group ổn định và hiểu chính sách lưu trữ của broker.
5. **Giả định mọi broker có cùng semantics**: partition, thứ tự, acknowledgement, retention và DLQ khác nhau. Hãy kiểm thử hành vi cụ thể trước khi chuyển binder.
6. **Không thiết kế idempotency**: redelivery có thể khiến cùng một sự kiện tạo tác động nghiệp vụ nhiều lần. Hãy dùng event ID và cơ chế chống xử lý trùng.
7. **Retry vô hạn hoặc retry lỗi dữ liệu**: điều này làm tăng tải và giữ message lỗi trong luồng chính. Hãy phân loại lỗi, đặt backoff và có DLQ cùng quy trình xử lý.
8. **Thay đổi schema không tương thích**: producer mới có thể làm consumer cũ lỗi. Hãy xác định quy tắc tương thích và triển khai theo thứ tự phù hợp.
9. **Tăng consumer mà không xem số partition**: instance mới có thể không nhận thêm công việc. Hãy theo dõi lag và phân phối partition.
10. **Tin rằng test binder đại diện đầy đủ cho broker thật**: test binder không mô phỏng mọi cơ chế của broker. Hãy bổ sung integration test cho các đặc tính phụ thuộc transport.
11. **Coi exactly-once là bảo đảm cho mọi side effect**: transaction của Kafka không tự bao phủ database hoặc HTTP service. Hãy dùng outbox/inbox và idempotency khi cần.
12. **Bỏ qua trạng thái Kafka Streams khi nâng cấp**: thay đổi topology, Serde hoặc state store có thể ảnh hưởng khả năng restore. Hãy có kế hoạch migration và kiểm thử phục hồi.

## 14. Quy trình thiết kế một luồng sự kiện

Khi xây dựng một luồng mới, có thể đi theo trình tự sau:

1. Xác định sự kiện nghiệp vụ, chủ sở hữu dữ liệu và consumer nào cần nhận sự kiện.
2. Thiết kế payload, event ID, schema, content type và quy tắc tương thích.
3. Chọn hàm Supplier, Function hoặc Consumer theo trách nhiệm xử lý.
4. Đặt tên bean và binding rõ ràng; khai báo function definition nếu ứng dụng có nhiều hàm.
5. Chọn destination, binder, consumer group và partition key.
6. Xác định concurrency, số instance và yêu cầu về thứ tự.
7. Thiết kế retry, backoff, DLQ, idempotency và quy trình phát lại.
8. Viết unit test cho logic, test binder cho wiring và integration test cho semantics của broker.
9. Cấu hình health, metrics, tracing, secrets và graceful shutdown.
10. Kiểm thử tình huống broker gián đoạn, consumer khởi động lại, message trùng và schema thay đổi trước khi phát hành.

## Kết luận

Spring Boot cung cấp môi trường chạy ứng dụng; Spring Cloud Function giúp biểu diễn logic dưới dạng hàm; Spring Integration cung cấp các công cụ xử lý và định tuyến message; Spring Cloud Stream nối các hàm với destination thông qua binder. Sự phân chia này giúp mã nghiệp vụ dễ kiểm thử và giảm phụ thuộc vào broker, trong khi vẫn cho phép khai thác các đặc tính của Kafka, RabbitMQ hoặc Pulsar khi cần.

Một thiết kế tốt cần hiểu cả hai phía của ranh giới: mô hình binding chung của Spring Cloud Stream và semantics thật của broker. Consumer group, partition, schema, retry, DLQ, state store, idempotency và kiểm thử tích hợp quyết định hệ thống có xử lý sự kiện tin cậy khi tải tăng hoặc thành phần gặp lỗi hay không.
