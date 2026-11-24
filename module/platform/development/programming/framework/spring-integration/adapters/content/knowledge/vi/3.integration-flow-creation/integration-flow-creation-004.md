# @MessagingGateway gọi integration flow

## 1. Mục tiêu và vị trí của messaging gateway

Trong chương **Tạo integration flow** của module **SPRING_INTEGRATION_ADAPTERS**, ta đã biết một luồng Spring Integration trao đổi dữ liệu qua `Message<?>`, `MessageChannel` và các endpoint. Module hướng đến việc kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller, với các tình huống file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; đồng thời kiểm soát hợp đồng message, lỗi và vòng đời kết nối.

**`@MessagingGateway`** là annotation dùng để khai báo **giao diện Java** mà ứng dụng có thể gọi như một service bình thường, trong khi Spring Integration tự tạo proxy chuyển lời gọi phương thức thành message gửi vào một integration flow. Nếu flow trả kết quả, proxy chuyển message phản hồi thành giá trị trả về của phương thức.

Ví dụ, code nghiệp vụ chỉ cần:

~~~java
PaymentResponse response = paymentGateway.submit(
        new PaymentRequest("ORD-1001", new BigDecimal("250000")),
        "trace-ord-1001");
~~~

Trong khi phía sau lời gọi có thể là tuyến **validate → transform → service activator**, hoặc tuyến kết nối HTTP, SFTP, JMS, AMQP, Kafka và database.

Sau bài này, người học có thể:

- Khai báo interface `@MessagingGateway` và đăng ký proxy với Spring.
- Phân biệt `defaultRequestChannel`, `requestChannel`, `replyChannel` và `errorChannel`.
- Ánh xạ tham số method thành **payload/headers**, rồi chuyển reply thành kiểu Java.
- Xây dựng flow **request–reply** và flow **one-way** theo đúng hợp đồng.
- Phân tích thread, timeout, exception, retry và trường hợp phản hồi không đến.
- Kiểm thử qua gateway thật cùng Spring context.
- Chọn messaging gateway khi cần API Java, thay vì nhầm với inbound/outbound gateway của giao thức ngoài.

**Điểm cốt lõi:** gateway ở đây là **cửa vào bằng phương thức Java** cho integration flow. Nó không tự tạo kết nối HTTP, không chủ động poll file, và không bảo đảm hệ thống ngoài đã xử lý thành công.

## 2. Từ lời gọi method đến message

Giả sử lớp nghiệp vụ muốn xử lý một đơn hàng. Không dùng Spring Integration, nó thường gọi trực tiếp chuỗi service. Khi dùng messaging gateway, lớp nghiệp vụ phụ thuộc vào interface; các bước tích hợp nằm trong flow.

~~~mermaid
sequenceDiagram
    participant C as Java caller
    participant G as @MessagingGateway proxy
    participant CH as request MessageChannel
    participant F as IntegrationFlow
    participant H as handler
    C->>G: submit(PaymentRequest, traceId)
    G->>CH: Message<PaymentRequest> + headers
    CH->>F: filter → transform
    F->>H: Message<PaymentCommand>
    H-->>G: PaymentResponse qua reply channel
    G-->>C: PaymentResponse
~~~

| Khái niệm | Vai trò |
| --- | --- |
| **Gateway interface** | Định nghĩa API Java dành cho caller; ví dụ `submit(PaymentRequest)`. |
| **Gateway proxy** | Được Spring Integration tạo, xây message từ tham số và gửi đến request channel. |
| **Request channel** | Chuyển message từ proxy đến flow hoặc endpoint. |
| **Payload** | Dữ liệu nghiệp vụ, ví dụ `PaymentRequest`. |
| **Headers** | Metadata như `traceId`, `correlationId`, `replyChannel`, `errorChannel`. |
| **IntegrationFlow** | Validate, transform, route, gọi service hoặc adapter. |
| **Reply channel** | Đường phản hồi về gateway khi phương thức có kết quả trả về. |
| **Method result** | Payload hoặc message được chuyển thành kiểu trả về của method gateway. |

Trong request–reply, gateway thêm thông tin để định tuyến reply về đúng lời gọi đang chờ. Nếu chặng cuối của flow trả về object, framework có thể xây message phản hồi và gửi về `replyChannel` tương ứng. Khi handler không phát reply, phương thức trả kết quả có thể chờ đến timeout.

## 3. Phân biệt bốn khái niệm gateway thường bị nhầm

| Khái niệm | Đầu vào | Đầu ra | Khi dùng |
| --- | --- | --- | --- |
| `@MessagingGateway` | Phương thức Java được code nội bộ gọi. | Message vào Spring Integration và reply về method. | Cung cấp API Java có kiểu cho flow. |
| HTTP inbound gateway | HTTP request từ client bên ngoài. | Message đi vào flow và HTTP response trả client. | Xây endpoint HTTP nhận request–reply. |
| Outbound gateway | Message trong flow. | Request đến hệ thống ngoài và reply được đưa lại flow. | Gọi HTTP/JMS/AMQP/... rồi xử lý response. |
| Inbound adapter dùng poller | Lịch poll kích hoạt `MessageSource`. | Message một chiều vào channel. | File, SFTP, JDBC hoặc nguồn cần quét định kỳ. |

`@MessagingGateway` hoạt động ở **ranh giới Java caller ↔ message flow**. Outbound gateway hoạt động ở **ranh giới message flow ↔ hệ thống ngoài có phản hồi**. Hai thành phần có thể phối hợp: phương thức Java gọi messaging gateway, flow dùng HTTP outbound gateway gọi API đối tác, rồi response trở lại caller.

Với một tuyến one-way, service activator hoặc outbound adapter có thể kết thúc luồng mà không tạo reply. Method gateway lúc đó nên có chữ ký tương ứng (ví dụ trả `void`), tránh để caller chờ kết quả vốn không tồn tại.

## 4. Cấu hình tối thiểu

Với dự án Spring Boot dùng dependency management của Spring Boot, Maven có thể khai báo:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
~~~

Một interface gateway thông thường:

~~~java
@MessagingGateway(defaultRequestChannel = "payments.requests")
interface PaymentGateway {
    PaymentResponse submit(PaymentRequest request);
}
~~~

Để Spring tạo proxy cho interface, cần cơ chế scan/đăng ký gateway. Trong ứng dụng Spring Boot, có thể đặt `@IntegrationComponentScan` trên class cấu hình hoặc ứng dụng:

~~~java
@SpringBootApplication
@IntegrationComponentScan
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

`@IntegrationComponentScan` tìm các interface gateway trong phạm vi package được scan. `@SpringBootApplication` cũng có component scan thông thường cho các bean Java, nhưng không nên suy ra rằng một interface `@MessagingGateway` luôn được đăng ký nếu thiếu cơ chế scan/đăng ký gateway phù hợp.

Annotation `@MessagingGateway` đặt trên **interface** thể hiện hợp đồng mà caller sử dụng. Đừng dùng toán tử `new PaymentGateway()`: proxy được Spring quản lý và được inject qua constructor hoặc tìm từ application context.

## 5. Ví dụ đầy đủ: phương thức Java gọi IntegrationFlow

Bài toán: bộ phận nhận đơn hàng cần kiểm tra đơn có mã hợp lệ và số tiền dương, biến đổi thành lệnh xử lý, trả về trạng thái `ACCEPTED`. Mọi thứ được xử lý trong bộ nhớ để tập trung vào gateway. Ví dụ không thu tiền thật hay gọi hệ thống ngân hàng.

### 5.1. Tạo ứng dụng và flow

Đặt mã sau trong tệp `PaymentGatewayApplication.java`, package `demo.gateway`. Ví dụ dùng Java 17+ với `record` và Spring Integration 6.x / Spring Boot tương thích.

~~~java
package demo.gateway;

import java.math.BigDecimal;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@SpringBootApplication
@IntegrationComponentScan
public class PaymentGatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(PaymentGatewayApplication.class, args);
    }

    @Bean(name = "payments.requests")
    MessageChannel paymentRequestChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow paymentFlow() {
        return IntegrationFlow.from("payments.requests")
                .filter(PaymentRequest.class,
                        request -> request.orderId() != null
                                && !request.orderId().isBlank()
                                && request.amount() != null
                                && request.amount().signum() > 0,
                        endpoint -> endpoint.throwExceptionOnRejection(true))
                .transform(PaymentRequest.class,
                        request -> new PaymentCommand(
                                request.orderId(), request.amount()))
                .handle(PaymentCommand.class,
                        (command, headers) -> new PaymentResponse(
                                command.orderId(),
                                "ACCEPTED",
                                (String) headers.get("traceId")))
                .get();
    }

    @Bean
    CommandLineRunner demo(PaymentGateway gateway) {
        return args -> {
            var request = new PaymentRequest(
                    "ORD-1001", new BigDecimal("250000"));
            var response = gateway.submit(request, "trace-ord-1001");
            System.out.println(response);
        };
    }
}

@MessagingGateway(
        defaultRequestChannel = "payments.requests",
        defaultReplyTimeout = "5000")
interface PaymentGateway {

    PaymentResponse submit(
            @Payload PaymentRequest request,
            @Header("traceId") String traceId);
}

record PaymentRequest(String orderId, BigDecimal amount) {}

record PaymentCommand(String orderId, BigDecimal amount) {}

record PaymentResponse(
        String orderId, String status, String traceId) {}
~~~

Các `record` và interface ở ví dụ là kiểu package-private đặt cùng tệp cho ngắn gọn. Trong ứng dụng thật, nên tách mỗi interface/DTO ra tệp riêng và giữ package scan thích hợp.

### 5.2. Dòng chảy dữ liệu

Với lời gọi:

~~~java
gateway.submit(
        new PaymentRequest("ORD-1001", new BigDecimal("250000")),
        "trace-ord-1001");
~~~

Các bước thực hiện:

1. Spring trả một proxy triển khai `PaymentGateway` khi inject.
2. Proxy dùng `@Payload` để đưa `PaymentRequest` vào payload, dùng `@Header("traceId")` để thêm header.
3. Proxy gửi `Message<PaymentRequest>` vào channel `payments.requests`. Flow đăng ký consumer của channel này.
4. `filter` kiểm tra `orderId` và `amount`. Nếu dữ liệu không hợp lệ, `throwExceptionOnRejection(true)` làm phát sinh exception thay vì bỏ message im lặng.
5. `transform` biến `PaymentRequest` thành `PaymentCommand`. Các header cần thiết, trong đó có `traceId` và đường reply, được framework duy trì theo cách biến đổi payload thông thường.
6. `handle` tạo `PaymentResponse` từ payload và header. Vì gateway cần kết quả, reply trở lại proxy qua channel phản hồi tương ứng.
7. Caller nhận `PaymentResponse("ORD-1001", "ACCEPTED", "trace-ord-1001")` dưới dạng object Java.

Ví dụ sử dụng `DirectChannel`, nên các bước của flow thông thường thực hiện trên cùng thread gọi gateway. Dùng gateway **không tự tạo bất đồng bộ**.

### 5.3. Tại sao ví dụ không cần tự đặt reply channel?

Gateway tạo thông tin phản hồi khi gọi method có kết quả; handler cuối trả object để framework tạo message reply. Đây là tuyến request–reply đơn giản nên không phải khai báo thêm `.channel("payments.replies")`.

Nếu luồng tự chuyển message sang channel khác, dùng router, split/aggregate hoặc endpoint giao thức có kiểu phản hồi khác, cần kiểm tra đường reply còn tồn tại và không bị đổi/mất. Dùng `outputChannel`, `defaultReplyChannel` hay `replyChannel` chỉ khi có lý do thiết kế cụ thể và đã hiểu nơi reply được tiêu thụ.

## 6. Ánh xạ tham số gateway thành payload và header

Một phương thức gateway là **hợp đồng Java** cho integration flow. Nên ghi rõ mỗi tham số có ý nghĩa nghiệp vụ hay metadata.

~~~java
@MessagingGateway(defaultRequestChannel = "orders.input")
interface OrderGateway {

    OrderResult submit(
            @Payload OrderCommand command,
            @Header("tenantId") String tenantId,
            @Header("correlationId") String correlationId);
}
~~~

Các kiểu `OrderCommand` và `OrderResult` ở snippet là DTO do ứng dụng định nghĩa.

| Thành phần method | Message nhận được | Ghi chú |
| --- | --- | --- |
| `@Payload OrderCommand command` | Payload là `OrderCommand`. | Kiểu Java phía caller không nhất thiết trùng kiểu payload sau transformer. |
| `@Header("tenantId") String tenantId` | Header `tenantId` chứa chuỗi. | Consumer có thể dùng để route, nhưng phải kiểm tra quyền dữ liệu trước khi tin tưởng. |
| `@Header("correlationId") String correlationId` | Header phục vụ tracing/đối soát. | Cần bảo toàn qua các bước nếu còn cần. |
| Kiểu trả về `OrderResult` | Payload phản hồi cần chuyển được sang `OrderResult`. | Nếu nhận sai kiểu, caller có thể gặp lỗi chuyển đổi. |

Spring Integration cung cấp nhiều cách map dữ liệu, nhưng một gateway interface rõ ràng với **một payload có kiểu + các header có tên** thường dễ đọc và kiểm thử nhất.

**Không dùng header như nơi chứa toàn bộ dữ liệu nghiệp vụ.** Payload biểu thị lệnh hoặc event; header dùng cho metadata điều phối, đối soát và routing. Nếu chuyển message qua HTTP, JMS hoặc Kafka, header nội bộ như `replyChannel` có thể là đối tượng Spring `MessageChannel`; đừng serialize và phát tán trực tiếp toàn bộ headers ra bên ngoài. Hãy dùng header mapper/DTO phù hợp giao thức.

### 6.1. Bảo toàn header qua transformer

Trong ví dụ mục 5, `transform` đổi payload nhưng vẫn cần `traceId`. Khi trả về object payload thông thường, cơ chế transformer của Spring Integration giữ ngữ cảnh cần thiết trong message đầu ra. Nếu handler tự tạo `Message<?>` hoặc bỏ các header bằng mapper tùy chỉnh, phải kiểm tra rằng các header quan trọng (`correlationId`, `replyChannel`, `errorChannel`) vẫn được xử lý đúng.

Không tự tạo một `replyChannel` mới chỉ để lưu correlation ID. Hai thông tin có vai trò khác nhau: correlation ID dùng theo dõi nghiệp vụ; reply channel quyết định **nơi message phản hồi phải được gửi**.

## 7. Cấu hình channel theo từng phương thức với @Gateway

Nếu cùng một gateway interface có nhiều thao tác đi đến các flow khác nhau, dùng `@Gateway` để chỉ định channel cho từng method:

~~~java
@MessagingGateway
interface ShippingGateway {

    @Gateway(requestChannel = "shipping.estimate")
    Quote estimate(ShippingRequest request);

    @Gateway(requestChannel = "shipping.submit")
    void submit(ShippingRequest request);
}
~~~

Trong ví dụ này, `ShippingRequest` và `Quote` là các kiểu ứng dụng tự định nghĩa; các channel `shipping.estimate` và `shipping.submit` cần có endpoint tiếp nhận tương ứng.

- `estimate(...)` là request–reply vì method trả `Quote`.
- `submit(...)` là one-way vì method trả `void`; flow không bắt buộc tạo reply.
- `@Gateway(requestChannel = ...)` đặt channel cho method cụ thể.
- `@MessagingGateway(defaultRequestChannel = ...)` phù hợp khi đa số method cùng dùng một channel mặc định.

Đừng định nghĩa nhiều method cùng gọi một channel rồi giả định Spring tự phân biệt loại nghiệp vụ qua tên method. Nếu nhiều loại lệnh dùng chung channel, có thể dùng payload type, header lệnh hoặc router có hợp đồng rõ ràng.

## 8. Gateway request–reply và one-way

### 8.1. Request–reply

Đây là trường hợp method có giá trị trả về:

~~~java
@MessagingGateway(defaultRequestChannel = "inventory.check")
interface InventoryGateway {
    InventoryResult check(InventoryQuery query);
}
~~~

Một flow nhận `InventoryQuery` phải phát reply thích hợp để caller nhận `InventoryResult`. Nếu handler cuối trả `null`, filter loại message hoặc adapter đi đến đích không phản hồi, gateway có thể chờ cho đến giới hạn thời gian chờ.

### 8.2. One-way (fire-and-forget ở góc độ hợp đồng)

Trường hợp caller chỉ cần đưa command vào flow:

~~~java
@MessagingGateway(defaultRequestChannel = "audit.events")
interface AuditGateway {
    void record(AuditEvent event);
}
~~~

Endpoint cuối có thể là `@ServiceActivator` trả `void` hoặc outbound adapter một chiều:

~~~java
@ServiceActivator(inputChannel = "audit.events")
public void publishAudit(AuditEvent event) {
    auditClient.send(event);
}
~~~

`AuditEvent` và `auditClient` do ứng dụng cung cấp; snippet giả định method nằm trong một Spring bean đã được scan.

**Lưu ý:** method `void` không đồng nghĩa việc gửi đã chạy nền. Với `DirectChannel`, caller có thể bị chặn cho đến khi handler gửi ra bên ngoài hoàn tất; exception đồng bộ vẫn có thể lan về caller. Nếu channel chuyển việc sang thread khác, method có thể trả sớm hơn nhưng phải thiết kế error handling, độ bền và xác nhận riêng.

### 8.3. Thiết kế kết quả nghiệp vụ thay cho trả về boolean mơ hồ

Nếu caller cần biết việc đối tác đã chấp nhận, đừng chỉ trả `true` khi `MessageChannel.send(...)` thành công. Nên có kiểu `SubmissionResult` hoặc `PaymentResponse` với mã nghiệp vụ, trạng thái, thời điểm, reference đối tác và ý nghĩa rõ ràng.

Có thể phân biệt:

- **Accepted:** hệ thống tích hợp đã tiếp nhận yêu cầu.
- **Submitted:** yêu cầu đã được gửi tới hệ thống ngoài và nhận xác nhận ở mức protocol.
- **Completed:** hệ thống ngoài đã hoàn tất nghiệp vụ theo quy ước đối soát.

Các trạng thái này không nhất thiết có cùng một thời điểm. Gateway request–reply phù hợp khi tác vụ đích có thời hạn phản hồi hợp lý; với quy trình kéo dài, có thể trả tracking ID trước và thông báo kết quả sau.

## 9. Timeout: requestTimeout và replyTimeout khác nhau thế nào?

`@MessagingGateway` hỗ trợ cấu hình thời hạn chờ, thường gặp là:

~~~java
@MessagingGateway(
        defaultRequestChannel = "orders.requests",
        defaultRequestTimeout = "2000",
        defaultReplyTimeout = "5000")
interface OrdersGateway {
    OrderResult submit(OrderCommand command);
}
~~~

Các kiểu `OrderCommand` và `OrderResult` là DTO do ứng dụng định nghĩa.

| Thuộc tính | Điều cần giới hạn | Hiểu đúng |
| --- | --- | --- |
| `defaultRequestTimeout` | Thời gian đợi để **gửi message vào request channel** khi channel hỗ trợ thao tác gửi có thể block. | Có ý nghĩa đặc biệt với queue/channel có dung lượng hoặc khả năng gửi bị chặn. |
| `defaultReplyTimeout` | Thời gian gateway **đợi message phản hồi** sau khi request đã được gửi. | Khi không nhận được reply theo đường trả về, cần xác định hành vi timeout của caller. |
| Timeout của HTTP/JDBC/JMS client | Thời gian giao tiếp với hệ thống ngoài. | Phải cấu hình tại client/adapter; không thể thay thế đơn giản bằng reply timeout của gateway. |

**Điểm dễ nhầm:** với `DirectChannel`, việc gọi handler thường diễn ra đồng bộ trong thao tác gửi. Nếu handler bên trong giữ thread 30 giây, `defaultReplyTimeout = "5000"` không phải cơ chế cắt ngang lời gọi đó sau đúng 5 giây. Cần timeout của network client và giới hạn xử lý phù hợp.

Một flow dùng `ExecutorChannel`, `QueueChannel` hoặc broker có thể chuyển xử lý sang thread khác; lúc này gateway có thể gửi request xong rồi chờ reply theo thời hạn. Nếu reply đến sau khi gateway đã hết hạn chờ, cần quyết định cách ghi nhận message đến muộn và chống gửi lặp khi caller thử lại.

### 9.1. Đặt timeout theo ngân sách thời gian của toàn tuyến

Nếu request đi qua:

~~~text
Gateway → Queue → Validation → HTTP outbound gateway → Partner API
~~~

thời gian chờ tổng thể cần tính thời gian nằm trong queue, thời gian xử lý, network timeout, retry và độ trễ phản hồi. Đặt reply timeout ngắn hơn một lượt retry bình thường có thể khiến caller báo lỗi dù đích vẫn đang xử lý. Đặt quá dài có thể giữ nhiều request chờ và làm cạn tài nguyên.

Hãy có chính sách riêng cho request đang xử lý, request hết hạn, kết quả đến muộn và kết quả chưa rõ.

## 10. Exception, error channel và các đường thất bại

### 10.1. Lỗi trên flow đồng bộ

Với flow mục 5 sử dụng `DirectChannel`, `filter` được cấu hình `throwExceptionOnRejection(true)`. Khi request không hợp lệ, framework phát exception và gateway có thể chuyển exception đó về lời gọi Java, thay vì trả `PaymentResponse` thành công.

Các lỗi tương tự có thể xuất hiện từ transformer, service activator hoặc client outbound. Loại exception nhìn thấy ở caller có thể phụ thuộc cách framework bọc exception, vì vậy test nên kiểm tra loại lỗi phù hợp và nguyên nhân gốc khi cần.

### 10.2. Lỗi khi handler bất đồng bộ

Khi message rời thread gọi gateway, exception của worker không tự động bay ngược vào method Java đã trả về. Spring Integration có thể phát `ErrorMessage` vào error channel khi endpoint/poller/adapter được cấu hình để làm như vậy. Cần có consumer xử lý và quyết định phản hồi cho caller.

Nếu chọn `errorChannel` ở gateway hoặc trên message, đừng chỉ gửi log rồi quên reply cho một method đang đợi kết quả. Một chính sách lỗi rõ ràng thường bao gồm **message lỗi được ghi ở đâu**, **caller nhận gì**, **có retry hay không**, **sự kiện nào cần đối soát**.

### 10.3. Filter im lặng loại message

Trong request–reply, một filter trả `false` rồi bỏ message có thể khiến caller chờ đến timeout. Có hai hướng thiết kế:

- Request không hợp lệ là **lỗi**, filter ném exception hoặc chuyển vào nhánh tạo lỗi nghiệp vụ.
- Request bị từ chối là **kết quả nghiệp vụ bình thường**, flow trả một response thể hiện trạng thái từ chối thay vì mất message.

Tránh để hành vi timeout trở thành cách ngầm báo "dữ liệu không hợp lệ".

### 10.4. Lỗi khi hệ thống ngoài đã xử lý nhưng gateway timeout

Ví dụ flow gửi lệnh tạo hóa đơn sang HTTP outbound gateway. Đối tác tạo hóa đơn thành công nhưng mất phản hồi. Method Java timeout; caller gọi lại có thể tạo hóa đơn thứ hai.

Cần thiết kế **idempotency key** ổn định theo thao tác nghiệp vụ, cơ chế kiểm tra trạng thái tại đối tác hoặc transactional outbox và đối soát. Retry phải phân biệt lỗi chắc chắn chưa xử lý với lỗi chưa rõ kết quả. `@MessagingGateway` không tự biến việc gửi message thành exactly-once.

## 11. Gateway kết hợp các loại MessageChannel

| Channel | Hành vi điển hình | Tác động đến gateway |
| --- | --- | --- |
| `DirectChannel` | Subscriber xử lý trực tiếp trên thread sender. | Method gateway có thể block khi handler chạy; exception đồng bộ thường lan ra. |
| `QueueChannel` | Message lưu trong hàng đợi để endpoint khác poll. | Cần poller/consumer; nếu method chờ reply, phải tính thời gian nằm trong queue. |
| `ExecutorChannel` | Bàn giao việc xử lý cho `TaskExecutor`. | Request/reply có thể vượt ranh giới thread, cần timeout và error handling phù hợp. |
| `PublishSubscribeChannel` | Gửi cùng message đến nhiều subscriber. | Nếu dùng cho request–reply, phải định nghĩa rõ subscriber nào tạo reply và cách xử lý nhiều reply. |

Một ứng dụng có thể dùng gateway request–reply trên `DirectChannel` ở phần xử lý nhanh; tách tác vụ dài sang queue, trả tracking ID sớm, rồi gửi thông báo hoàn thành qua event hoặc callback.

Không tự động đổi `DirectChannel` sang `ExecutorChannel` chỉ để "tăng tốc": nếu tốc độ nguồn vượt tốc độ đích, sẽ phát sinh backlog, cạn thread/queue hoặc mất thông tin lỗi nếu chưa thiết kế giới hạn tài nguyên.

## 12. Kết hợp messaging gateway với các adapter ngoài hệ thống

Gateway là API gọi flow từ Java, còn adapter/gateway khác quyết định cách flow tương tác với thế giới bên ngoài:

~~~mermaid
flowchart TB
    APP["Java service / REST controller"]
    G["@MessagingGateway"]
    CH["MessageChannel"]
    FLOW["Validate → Transform → Route"]
    H1["HTTP outbound gateway"]
    H2["JMS / AMQP / Kafka outbound adapter"]
    H3["File / SFTP outbound adapter"]
    H4["JDBC / database service activator"]
    APP --> G --> CH --> FLOW
    FLOW --> H1
    FLOW --> H2
    FLOW --> H3
    FLOW --> H4
    H1 -. "Response nếu có" .-> G
~~~

| Nhu cầu | Thiết kế hợp lý | Điều cần xác nhận |
| --- | --- | --- |
| Java service gọi HTTP API đối tác và cần kết quả. | `@MessagingGateway` → transform → HTTP outbound gateway → reply. | Timeout, HTTP status, schema response, tính idempotent. |
| Java service yêu cầu gửi event Kafka. | Gateway method `void` → outbound adapter. | Producer ack/timeout, delivery semantics và xử lý lỗi callback. |
| Tạo file hoặc gửi SFTP. | Gateway → transform thành file/nội dung → outbound adapter. | Ghi tạm và rename, file đã gửi, retry/duplicate. |
| Ghi đơn vào database. | Gateway → service activator/JDBC outbound. | Transaction, unique constraint, rollback/retry. |
| File/SFTP inbound poller đã đẩy message vào flow. | Inbound adapter + poller → channel → flow; có thể tái sử dụng service nghiệp vụ. | Không cần gọi gateway để kích hoạt source đã tự polling. |

Một flow có thể được nhiều entry point sử dụng nếu đã chuẩn hóa cùng **kiểu payload và header contract**. Tuy nhiên, đường reply của request Java khác với file polling one-way: file không có caller trực tiếp chờ result. Nếu phối hợp hai nguồn vào cùng một flow, hãy xác định rõ nơi lưu kết quả và lỗi cho mỗi nguồn.

## 13. Kiểm thử qua gateway thật

Unit test gọi trực tiếp method transform chỉ chứng minh logic transform. Để chắc chắn proxy, channel, flow và reply hoạt động, cần một integration test khởi động Spring context rồi gọi **gateway interface**.

Thêm `spring-boot-starter-test` ở scope test:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Đặt ví dụ JUnit 5 sau trong `PaymentGatewayApplicationTest.java` cùng package `demo.gateway`:

~~~java
package demo.gateway;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.MessagingException;

@SpringBootTest
class PaymentGatewayApplicationTest {

    @Autowired
    PaymentGateway gateway;

    @Test
    void returnsTypedResponseWithTraceId() {
        PaymentResponse result = gateway.submit(
                new PaymentRequest(
                        "ORD-2001", new BigDecimal("120.50")),
                "trace-test-2001");

        assertEquals("ORD-2001", result.orderId());
        assertEquals("ACCEPTED", result.status());
        assertEquals("trace-test-2001", result.traceId());
    }

    @Test
    void rejectsNonPositiveAmount() {
        assertThrows(MessagingException.class, () -> gateway.submit(
                new PaymentRequest("ORD-2002", BigDecimal.ZERO),
                "trace-test-2002"));
    }
}
~~~

Test kiểm tra rằng:

1. Spring tạo được bean proxy `PaymentGateway`.
2. Method gọi đúng channel và đi vào `IntegrationFlow`.
3. Filter/transform/handler làm việc và giữ được header `traceId`.
4. Gateway chuyển reply thành `PaymentResponse`.
5. Request không hợp lệ gây lỗi thay vì trả thành công.

Với cấu hình hoặc phiên bản khác, exception có thể được bọc thành một loại `MessagingException` khác; khi đó kiểm tra nguyên nhân gốc liên quan tới message rejection. Ví dụ test này **không** kiểm tra hệ thống ngoài hoặc các semantics giao hàng thật.

### 13.1. Kiểm thử timeout và phản hồi đến muộn

Để kiểm thử reply timeout có ý nghĩa, cần một flow có endpoint bất đồng bộ hoặc queue khiến việc gửi request hoàn thành trước khi có reply. Kiểm tra riêng:

- Message không có consumer hoặc không được trả reply.
- Handler trả reply muộn hơn thời hạn chờ.
- Handler ném exception ở worker thread và error channel có/không có consumer.
- Caller retry sau timeout nhưng thao tác nghiệp vụ đầu tiên vẫn đang chạy.
- Trường hợp nhiều request đồng thời cần correlation chính xác.

Đừng dùng thời gian ngủ tùy ý như bằng chứng tuyệt đối cho timeout; dùng công cụ đồng bộ test với thời hạn rõ ràng, kiểm tra kết quả và log bằng correlation ID.

## 14. Những lỗi hay gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Spring báo không tìm thấy bean gateway. | Interface chưa được quét bởi `@IntegrationComponentScan`, package không nằm trong phạm vi scan. | Kiểm tra annotation và vị trí package, hoặc đăng ký gateway bean tường minh. |
| Lời gọi gateway không tới flow. | `defaultRequestChannel` sai tên hoặc channel không có endpoint nhận. | So khớp tên bean channel với `IntegrationFlow.from(...)`/`@ServiceActivator`. |
| Gateway chờ đến timeout. | Flow không tạo reply, filter bỏ message, reply sai channel hoặc handler chạy quá lâu. | Theo dõi request/reply path, filter rejection, cấu hình timeout và endpoint. |
| `@Header` không thấy trong handler. | Quên annotation, sai tên header, mapper đã lọc bỏ. | Kiểm tra contract và test message qua proxy. |
| Dữ liệu trả về không đúng kiểu. | Payload reply không tương thích với return type Java. | Chuẩn hóa DTO response hoặc thêm bước transform thích hợp. |
| `void` vẫn khiến caller bị chặn. | `DirectChannel` và outbound client làm việc đồng bộ. | Giới hạn timeout client; chọn async/queue nếu có yêu cầu và đã quản lý backpressure. |
| Retry sau timeout tạo duplicate. | Đích đã xử lý nhưng response mất hoặc client retry không có ID ổn định. | Idempotency key, đối soát, outbox hoặc kiểm tra trạng thái giao dịch. |
| Không bắt được exception trong caller. | Xử lý đã chạy sang thread khác. | Thiết kế `errorChannel`, DLQ/quarantine và kênh phản hồi nghiệp vụ. |
| Reply timeout không ngắt một HTTP call chậm. | Timeout chỉ áp dụng khi đợi reply qua gateway, còn handler đồng bộ đang block. | Cấu hình timeout ở HTTP client/outbound gateway và ngân sách thời gian toàn tuyến. |
| Hai nguồn khác nhau đi cùng flow nhưng một nguồn chờ reply vô hạn. | Hợp đồng request–reply và one-way chưa được tách rõ. | Thiết kế entry point riêng, quy ước output và error flow phù hợp cho từng nguồn. |

## 15. Thực hành mở rộng

**Bài toán:** xây một `OrderGateway` cho ứng dụng Java dùng chung flow chuẩn hóa đơn hàng trước khi gửi tới hệ thống đối tác.

Yêu cầu chức năng:

1. Tạo interface `@MessagingGateway` với method `submit(OrderRequest request, @Header("traceId") String traceId)` trả `OrderReceipt`.
2. Flow validate `orderId` không rỗng, `quantity > 0` và `currency` thuộc tập được hỗ trợ; message không hợp lệ phải có kết quả lỗi rõ ràng.
3. Transformer chuyển `OrderRequest` thành `PartnerOrder` rồi gửi tới một client giả lập. Client trả mã tham chiếu đối tác khi thành công.
4. Method gateway khác tên `enqueue(...)` trả `void`, dùng channel và handler phù hợp tác vụ nền.
5. Thêm test thành công, test validation, test header truyền qua, test reply timeout khi endpoint bất đồng bộ không trả kết quả.
6. Mô phỏng một request đã được partner xử lý nhưng reply bị mất; thiết kế `idempotencyKey` và cách đối soát để tránh tạo trùng.
7. Nếu thay đích bằng HTTP outbound gateway hoặc Kafka outbound adapter, ghi rõ thời điểm kết thúc nào được coi là thành công đối với method Java.

**Tiêu chí đạt:** caller không cần biết các endpoint trong flow; gateway method có kiểu trả về rõ; code kiểm thử gọi interface proxy thực; lỗi và timeout có quy ước; các bên thống nhất payload/headers, ack và duplicate.

## 16. Câu hỏi tự kiểm tra

1. `@MessagingGateway` khác HTTP inbound gateway như thế nào?
2. Tại sao gateway được khai báo trên interface, và khi nào Spring tạo proxy?
3. `@Payload` và `@Header` thay đổi message mà gateway gửi ra sao?
4. Tại sao một handler trả `PaymentResponse` có thể trở thành giá trị trả về của method?
5. Nếu flow không phát reply nhưng method trả DTO, điều gì có thể xảy ra?
6. `defaultReplyTimeout` có nhất thiết ngắt được handler `DirectChannel` đang chạy chậm không?
7. Khi method trả `void`, vì sao nó vẫn có thể block?
8. Khác biệt giữa lỗi trên `DirectChannel` và lỗi sau `ExecutorChannel` là gì?
9. Trong một flow gọi HTTP đối tác, tại sao timeout có thể dẫn đến duplicate nếu caller retry?
10. Nếu hai method dùng hai channel, nên cấu hình `@Gateway` thế nào?

Gợi ý: gateway là proxy chuyển lời gọi Java thành message; đường request/reply đi qua channel, method contract và endpoint; timeout cần phân biệt giai đoạn gửi message, đợi reply và gọi hệ thống ngoài. Độ tin cậy còn phụ thuộc transaction, xác nhận và idempotency.

## 17. Ghi nhớ

`@MessagingGateway` giúp **gọi một integration flow như một API Java có kiểu**. Interface định nghĩa cách caller đưa payload và headers vào hệ thống, request channel chuyển message tới flow, còn reply channel đưa kết quả về caller khi hợp đồng cần phản hồi.

Khi kết nối file, SFTP, HTTP, JMS, AMQP, Kafka hoặc cơ sở dữ liệu, gateway Java có thể là cửa vào tiện lợi cho service nội bộ; các adapter và outbound gateway thực hiện trao đổi với hệ thống ngoài. Thiết kế hoàn chỉnh phải làm rõ **one-way hay request–reply**, thời gian chờ, mapping dữ liệu, đường lỗi, trạng thái thành công và cách chống duplicate sau retry.

