# Không ghi payload nhạy cảm vào log

## 1. Mục tiêu và phạm vi

Trong chương **Metrics và observability** của module `SPRING_INTEGRATION_CORE`, khả năng quan sát luồng thông điệp phải giúp xác định thông điệp đang ở đâu, bước nào thất bại và hệ thống chậm tại đâu. Khả năng đó không đòi hỏi sao chép dữ liệu nghiệp vụ vào hệ thống log.

Bài này áp dụng cho các luồng Spring Integration sử dụng `Message`, `MessageChannel`, endpoint, gateway và Java DSL. Transformer, router, filter và aggregator đều có thể xử lý dữ liệu nhạy cảm; vì vậy cùng một chính sách ghi log phải đi qua toàn bộ luồng, kể cả nhánh lỗi và nhánh discard.

Sau bài học, bạn có thể:

- Phân biệt dữ liệu nghiệp vụ với metadata được phép phục vụ vận hành.
- Nhận diện những cách ghi log vô tình kéo theo payload, header hoặc nguyên nhân ngoại lệ.
- Viết một luồng Java DSL chỉ xuất các trường đã chọn.
- Thiết kế log lỗi và kết hợp metrics, tracing mà không chuyển dữ liệu nhạy cảm sang nơi khác.
- Xây dựng phép kiểm chứng phát hiện rò rỉ bằng dữ liệu giả.

Các đoạn Java dùng cú pháp Java 17 và Java DSL của Spring Integration 6.x trở lên. Đây là các thành phần minh họa để đặt vào ứng dụng đã có Spring Integration, SLF4J và cấu hình logging; bài không cung cấp một dự án khởi động hoàn chỉnh.

## 2. Vì sao một dòng log có thể tạo thêm một kho dữ liệu nhạy cảm?

Giả sử hệ thống nhận yêu cầu giao hàng. Payload có email và chỉ dẫn giao nhận; header có thông tin xác thực do tầng giao tiếp đưa vào. Endpoint cần một phần dữ liệu đó để hoàn thành nghiệp vụ, nhưng người trực vận hành thường chỉ cần biết:

1. Luồng nào tiếp nhận yêu cầu.
2. Mã quan sát nào dùng để tìm các sự kiện liên quan.
3. Bước xử lý và kết quả.
4. Thời gian xử lý, số lần thử lại và loại lỗi đã chuẩn hóa.

Một đoạn ghi log tiện tay có thể xuất nhiều hơn nhu cầu đó:

~~~java
// Các ví dụ cần tránh.
log.info("Received payload={}", message.getPayload());
log.debug("Received message={}", message);
log.warn("Headers={}", message.getHeaders());
~~~

Với payload là DTO, `toString()` có thể in các trường email, địa chỉ hoặc ghi chú. Với `Message`, biểu diễn chuỗi có thể bao gồm payload và headers. Với map headers, toàn bộ giá trị được phép đi vào bộ định dạng log. Việc một kiểu dữ liệu cụ thể hiện tại chỉ in tên lớp hoặc địa chỉ đối tượng không phải một cam kết bảo mật lâu dài.

Một sự kiện thường còn đi qua console, file, agent thu thập, hàng đợi và nền tảng tìm kiếm. Bản sao có thể xuất hiện trong cảnh báo hoặc gói chẩn đoán. Vì vậy, lọc trên giao diện xem log không loại bỏ dữ liệu đã được thu nhận trước đó.

**Nguyên tắc thiết kế:** tạo một bản biểu diễn riêng cho quan sát, chỉ chứa các trường được cho phép; không dùng đối tượng nghiệp vụ làm bản biểu diễn log.

## 3. Xác định dữ liệu nào được phép xuất

### 3.1. Payload không phải nơi duy nhất chứa thông tin cần bảo vệ

| Vị trí | Ví dụ trong luồng tích hợp | Cách xử lý khi ghi log |
| --- | --- | --- |
| Payload | Email, địa chỉ, nội dung tài liệu, ghi chú khách hàng | Không ghi nguyên đối tượng hoặc toàn bộ nội dung |
| Header giao tiếp | Authorization, Cookie, khóa API | Không đưa vào sự kiện log |
| Header nghiệp vụ | Mã khách hàng, mã hồ sơ, tên người dùng | Đánh giá từng trường; không mặc định cho phép vì là header |
| Exception | Thông báo lỗi chứa request body hoặc phản hồi đối tác | Chuyển thành mã lỗi hữu hạn; không xuất thông báo thô |
| MDC và tracing baggage | Thông tin được gắn tự động vào mọi sự kiện | Có danh sách trường riêng; không sao chép toàn bộ header |
| File hoặc URL | Tên file chứa tên khách hàng, query chứa token | Chỉ xuất mẫu đường dẫn hoặc tên endpoint được kiểm soát |
| Kết quả aggregator | Danh sách các yêu cầu hoặc toàn bộ nhóm thông điệp | Ghi số lượng và trạng thái nhóm nếu được phép; không dump nhóm |

Không cần chờ dữ liệu trở thành một mật khẩu mới coi nó là nhạy cảm. Nội dung tự do như ghi chú cũng có thể chứa thông tin cá nhân ngoài dự kiến.

OWASP nêu việc loại bỏ hoặc xử lý đặc biệt đối với token, mật khẩu và thông tin cá nhân trước khi ghi nhận log. Chính sách cụ thể của một luồng cần đi xa hơn việc dò vài tên trường quen thuộc: phải biết chính xác từng trường được xuất và mục đích sử dụng. Xem [hướng dẫn về dữ liệu cần loại trừ trong log của OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude).

### 3.2. Dùng danh sách cho phép thay cho sao chép rồi xóa

Hai cách tiếp cận có độ bền khác nhau:

- **Danh sách cấm:** serialize mọi thứ, rồi xóa các khóa như `password` hoặc `token`.
- **Danh sách cho phép:** tạo sự kiện mới từ các trường đã thống nhất, chẳng hạn `event`, `flow`, `request_id`, `outcome`.

Cách thứ nhất dễ bỏ sót trường mới, đối tượng lồng nhau, tên khác của cùng một bí mật hoặc dữ liệu nằm trong chuỗi tự do. Cách thứ hai mặc định không xuất trường mới khi mô hình nghiệp vụ thay đổi.

Một hợp đồng log cho luồng tiếp nhận đơn hàng có thể là:

| Trường | Nguồn | Ràng buộc |
| --- | --- | --- |
| `event` | Hằng do mã nguồn định nghĩa | Ví dụ `order.received`, `order.completed`, `order.failed` |
| `flow` | Tên luồng cố định | Ví dụ `orders`; không lấy từ payload |
| `request_id` | UUID do tầng biên của ứng dụng tạo | Giữ qua các bước cần liên kết; không chứa email hoặc mã khách hàng |
| `message_id` | ID của Spring Message | Chỉ phục vụ phân biệt một thông điệp |
| `outcome` | Tập giá trị hữu hạn | `SUCCESS`, `FAILURE`, `REJECTED` |
| `error_code` | Bộ phân loại lỗi do ứng dụng định nghĩa | Không dùng `exception.getMessage()` |
| `duration_ms` | Thời gian đo | Số không âm, có đơn vị rõ ràng |
| `attempt` | Trạng thái retry do ứng dụng quản lý | Số nguyên có giới hạn hợp lý |

Danh sách này là một thiết kế minh họa, không phải schema bắt buộc của Spring Integration. Khi thêm trường, cần trả lời được trường đó giúp điều tra vấn đề nào và có thể vô tình nhận dữ liệu bên ngoài hay không.

### 3.3. ID vẫn cần mục đích và giới hạn

`message_id` xác định một Spring Message. Khi transformer tạo message mới hoặc splitter tạo các message con, không nên giả định ID này là mã liên kết ổn định của cả giao dịch.

`request_id` trong bài là header quan sát riêng, được sinh ngẫu nhiên tại tầng biên. Nó không phải mặc định đồng nghĩa với header `correlationId` mà aggregator dùng để nhóm thông điệp. Nếu một transformer tạo message mới thay vì giữ headers, phải chủ động chuyển tiếp các metadata quan sát đã được cho phép.

Một UUID có thể giúp tra cứu ngược đến hồ sơ thông qua hệ thống khác, nên cũng phải nằm trong phạm vi truy cập và thời gian lưu phù hợp. ID quan sát không phải bằng chứng xác thực hay quyền truy cập. Việc kiểm tra đúng định dạng chỉ giới hạn hình dạng dữ liệu, không chứng minh nguồn gửi đáng tin cậy.

## 4. Các điểm dễ ghi lộ dữ liệu trong Spring Integration

### 4.1. Logging Channel Adapter và Java DSL `log()`

Không được hiểu `log-full-message="false"` là “không ghi dữ liệu nhạy cảm”. Logging Channel Adapter mặc định ghi payload; bật full message còn có thể đưa cả headers vào log. Cần cấu hình biểu thức hoặc hàm chọn dữ liệu rõ ràng. Xem [Logging Channel Adapter](https://docs.spring.io/spring-integration/reference/logging-adapter.html).

~~~java
// Chưa chỉ định biểu diễn an toàn; không dùng cho message nhạy cảm.
.log()

// Chỉ trả về metadata đã chọn.
.log(
    LoggingHandler.Level.INFO,
    "integration.safe.orders",
    m -> "event=order.received flow=orders message_id="
            + m.getHeaders().getId()
)
~~~

Phép nối chuỗi ở ví dụ an toàn chỉ kết hợp các hằng và UUID; không có chuỗi nghiệp vụ được đưa vào template. Ở các lời gọi logger thông thường, nên dùng template cố định và tham số đã kiểm soát.

Theo [tài liệu toán tử Java DSL log()](https://docs.spring.io/spring-integration/reference/dsl/java-log.html), toán tử này sử dụng wire tap cùng LoggingHandler. Do đó, dù phần thân luồng không có lời gọi logger trực tiếp, một thao tác quan sát chèn vào DSL vẫn có thể tạo bản ghi chứa dữ liệu. Từ Spring Integration 6.0, `log()` ở cuối luồng không tự biến luồng thành một điểm kết thúc một chiều; ví dụ ở bài sẽ có handler một chiều kết thúc nghiệp vụ.

### 4.2. Wire tap, interceptor và các nhánh phụ

Một wire tap nhận message phục vụ nhánh phụ; nó không tự tạo bản sao đã che dữ liệu. Nếu nhánh đó ghi `message`, `payload` hoặc `headers`, chính sách ở luồng chính không còn đủ.

Các nơi cần áp dụng cùng hợp đồng log gồm:

- `ChannelInterceptor` trước và sau khi gửi.
- Nhánh discard của filter.
- Router và nhánh không khớp điều kiện.
- Nhánh timeout, expire hoặc release của aggregator.
- Advice retry, recovery và kênh chứa thông điệp xử lý thất bại.
- Code quanh gateway, nơi caller có thể ghi toàn bộ request hoặc reply.

Với filter, một sự kiện `order.rejected` cùng `reason_code=UNSUPPORTED_TYPE` thường đủ để đếm và tìm lỗi cấu hình. Nếu lý do được xây từ chính giá trị bị từ chối, nó có thể đưa dữ liệu nghiệp vụ trở lại log.

Với aggregator, có thể ghi `group_size` và trạng thái xử lý; không cần ghi từng phần tử trong nhóm. Khóa nhóm cũng phải được đánh giá: nếu correlation key là email thì ghi khóa nhóm vẫn làm lộ email.

### 4.3. Mức DEBUG, TRACE và `nullChannel`

Chỉ hạ mức log của ứng dụng không loại bỏ mọi đường xuất dữ liệu. Một logger của framework, thư viện HTTP hoặc client broker có thể có cấu hình riêng.

Đặc biệt, `nullChannel` có thể ghi message ở DEBUG theo [tài liệu Special Channels](https://docs.spring.io/spring-integration/reference/channel/special-channels.html). Chuyển message sang đây để kết thúc hoặc loại bỏ xử lý không đồng nghĩa message không thể xuất hiện trong log.

Không bật DEBUG hoặc TRACE rộng cho toàn bộ package tích hợp trên dữ liệu thực khi chưa biết các logger đó ghi gì. Khi cần điều tra, chọn phạm vi hẹp, tái hiện bằng dữ liệu giả và kiểm tra đầu ra thực tế của đúng phiên bản thư viện.

## 5. Thiết kế luồng: quan sát bằng metadata riêng

~~~mermaid
flowchart LR
    A["Tầng biên: tạo request_id"] --> B["orders.input"]
    B --> C["Log metadata được phép"]
    C --> D["Endpoint xử lý Order"]
    D --> E["Log kết quả được phép"]
    C -.-> L["Kho log vận hành"]
    E -.-> L
    D --> F["Xử lý lỗi theo hợp đồng"]
    F -.-> L
~~~

Payload đi tới endpoint cần thực hiện nghiệp vụ. Kho log chỉ nhận biểu diễn quan sát. Đường lỗi phải giữ nguyên nguyên tắc đó.

Có hai ranh giới cần tách rõ:

1. **Ranh giới xử lý nghiệp vụ:** endpoint được phép đọc email hoặc địa chỉ nếu cần.
2. **Ranh giới xuất dữ liệu quan sát:** logger chỉ được nhận các trường đã cho phép.

Việc xây sự kiện log không nên sửa payload gốc. Che dữ liệu bằng cách ghi đè email hoặc token trong message rồi chuyển tiếp có thể làm hỏng hành vi nghiệp vụ, retry hoặc tích hợp bên ngoài.

## 6. Ví dụ: bộ chọn metadata không đọc payload

Đặt lớp sau trong package của ứng dụng. Mọi giá trị xuất ra đều là hằng hoặc UUID; header không đúng kiểu được biểu diễn bằng `missing`.

~~~java
import java.util.Map;
import java.util.UUID;

import org.springframework.messaging.Message;

public final class SafeLogFields {

    public static final String REQUEST_ID = "obsRequestId";

    private SafeLogFields() {
    }

    public static String requestId(Map<String, Object> headers) {
        Object candidate = headers.get(REQUEST_ID);

        // Tầng biên của ứng dụng phải tạo UUID, không chuyển nguyên
        // header bên ngoài vào đây.
        return candidate instanceof UUID id
                ? id.toString()
                : "missing";
    }

    public static String received(Message<?> message) {
        UUID messageId = message.getHeaders().getId();

        return "event=order.received"
                + " flow=orders"
                + " request_id=" + requestId(message.getHeaders())
                + " message_id="
                + (messageId == null ? "missing" : messageId.toString());
    }
}
~~~

Lớp này cố ý không gọi `getPayload()`, không duyệt toàn bộ headers và không serialize `Message`. Nếu payload có thêm trường nhạy cảm, hàm không tự xuất trường mới.

Việc chỉ chấp nhận `UUID` cũng tránh gọi `toString()` trên một đối tượng header tùy ý. Với một header dạng chuỗi, cần một bộ kiểm tra định dạng và độ dài riêng nếu thực sự muốn hỗ trợ; không chuyển thành chuỗi theo thói quen.

Hàm trên kiểm soát nội dung trả về của chính nó. Pattern logging, JSON encoder hoặc MDC vẫn có thể bổ sung dữ liệu khác vào bản ghi cuối cùng; cần kiểm tra các lớp đó độc lập.

## 7. Ví dụ Java DSL: giữ payload phục vụ nghiệp vụ, chỉ log metadata

### 7.1. Khai báo luồng một chiều

Các lớp trong ví dụ thuộc cùng package. `OrderService` là điểm mở rộng để ứng dụng cung cấp xử lý nghiệp vụ thực tế.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.LoggingHandler;

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class SafeOrderFlowConfiguration {

    private static final Logger LOG =
            LoggerFactory.getLogger("integration.safe.orders");

    public record Order(
            String customerEmail,
            String deliveryNote) {
    }

    public interface OrderService {
        void accept(Order order);
    }

    @Bean(name = "orders.input")
    public DirectChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow safeOrdersFlow(OrderService orderService) {
        return IntegrationFlow.from("orders.input")
                .log(
                        LoggingHandler.Level.INFO,
                        "integration.safe.orders",
                        SafeLogFields::received)
                .handle(Order.class, (order, headers) -> {
                    orderService.accept(order);

                    LOG.info(
                            "event=order.completed flow=orders"
                                    + " request_id={} outcome=SUCCESS",
                            SafeLogFields.requestId(headers));

                    // Handler này không tạo reply: luồng một chiều.
                    return null;
                })
                .get();
    }
}
~~~

Ứng dụng cần đăng ký một bean triển khai `OrderService`. Không nên cung cấp một implementation chỉ ghi `order` vào log, vì như vậy sẽ phá vỡ chính sách ngay bên trong service.

`order.received` chỉ có nghĩa message đã đi tới điểm quan sát ở đầu luồng; nó không chứng minh nghiệp vụ đã hoàn tất. `order.completed` trong ví dụ có nghĩa `accept()` đã trả về bình thường. Nếu transaction chỉ commit sau khi handler kết thúc, sự kiện này chưa phải bằng chứng commit bền vững. Với retry, một yêu cầu có thể có nhiều lần nhận hoặc nhiều lần xử lý; ý nghĩa sự kiện phải được mô tả rõ thay vì dùng log như bằng chứng “chính xác một lần”.

### 7.2. Gateway và tầng biên tạo mã quan sát

Có thể khai báo gateway một chiều để caller không phải thao tác trực tiếp với channel:

~~~java
import java.util.UUID;

import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@MessagingGateway(defaultRequestChannel = "orders.input")
public interface OrdersGateway {

    void submit(
            @Payload SafeOrderFlowConfiguration.Order order,
            @Header(SafeLogFields.REQUEST_ID) UUID observationRequestId);
}
~~~

Ví dụ lời gọi trong tầng biên đã nhận và kiểm tra request:

~~~java
UUID observationRequestId = UUID.randomUUID();

ordersGateway.submit(
        new SafeOrderFlowConfiguration.Order(
                "learner@example.test",
                "DELIVERY_NOTE_CANARY"),
        observationRequestId);
~~~

Email và chuỗi canary trên đều là dữ liệu giả cho minh họa. Header quan sát được tạo bởi ứng dụng, không lấy trực tiếp từ `Authorization`, query string hoặc một mã khách hàng.

Nếu cần giữ mã liên kết từ hệ thống gửi, hãy quy định header được phép, giới hạn độ dài, kiểm tra định dạng và tách nó khỏi ID nội bộ. Không dùng việc sao chép toàn bộ headers làm cách truyền ngữ cảnh.

Hai dòng log mong muốn có dạng:

~~~text
event=order.received flow=orders request_id=8f4e8631-7d25-4ea3-9f5c-102c2d770e72 message_id=6ec1ae9e-25b8-4b61-9fd9-63ee86b2801d
event=order.completed flow=orders request_id=8f4e8631-7d25-4ea3-9f5c-102c2d770e72 outcome=SUCCESS
~~~

Tìm theo `request_id` để liên kết sự kiện. Không cần tìm bằng email hoặc nội dung payload.

## 8. Đường lỗi: exception cũng có thể mang theo message gốc

### 8.1. Những mẫu dễ làm lộ dữ liệu

~~~java
// Tránh xuất ErrorMessage hoặc Throwable thô.
log.error("Error message={}", errorMessage);
log.error("Processing failed", exception);
log.warn("Failure detail={}", exception.getMessage());
~~~

Không phải mọi stack trace đều chứa payload. Tuy nhiên, exception message, cause chain và exception do thư viện tích hợp tạo ra có thể đưa dữ liệu request vào biểu diễn lỗi. Tham số `Throwable` ở logger thường được backend xử lý thành stack trace riêng, ngoài phần message đã định dạng.

Trong Spring Integration, đường bất đồng bộ có thể công bố `ErrorMessage` qua header `errorChannel` hoặc kênh lỗi toàn cục. Kênh lỗi mặc định có một LoggingHandler. Vì vậy, thêm một subscriber an toàn không tự loại bỏ logger đã tồn tại trên kênh publish-subscribe. Với `DirectChannel` đồng bộ như ví dụ ở trên, ngoại lệ thường truyền ngược về caller; không được giả định mọi lỗi đều tự đi qua kênh lỗi. Xem [Error Handling](https://docs.spring.io/spring-integration/reference/7.0/error-handling.html).

### 8.2. Tạo biểu diễn lỗi có giới hạn

Bộ phân loại sau không đọc thông báo lỗi:

~~~java
import java.net.SocketTimeoutException;
import java.util.concurrent.TimeoutException;

public final class SafeFailureCode {

    private SafeFailureCode() {
    }

    public static String classify(Throwable failure) {
        Throwable current = failure;

        // Giới hạn số cause được duyệt; không in từng cause.
        for (int depth = 0; current != null && depth < 8; depth++) {
            if (current instanceof TimeoutException
                    || current instanceof SocketTimeoutException) {
                return "DEPENDENCY_TIMEOUT";
            }

            current = current.getCause();
        }

        return "PROCESSING_FAILURE";
    }
}
~~~

Ví dụ dưới đây chỉ minh họa một consumer của kênh lỗi riêng. Không phải cấu hình xử lý lỗi hoàn chỉnh cho mọi adapter:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class SafeOrderErrorLogger {

    private static final Logger LOG =
            LoggerFactory.getLogger("integration.safe.orders");

    @ServiceActivator(inputChannel = "orders.errors")
    public void onError(ErrorMessage error) {
        Throwable failure = error.getPayload();
        Message<?> original = error.getOriginalMessage();

        if (failure instanceof MessagingException messaging
                && messaging.getFailedMessage() != null) {
            original = messaging.getFailedMessage();
        }

        String requestId = original == null
                ? "missing"
                : SafeLogFields.requestId(original.getHeaders());

        LOG.warn(
                "event=order.failed flow=orders"
                        + " request_id={} outcome=FAILURE error_code={}",
                requestId,
                SafeFailureCode.classify(failure));
    }
}
~~~

Ở đây, payload của `ErrorMessage` được đọc vì đó là `Throwable` phục vụ phân loại. Consumer không ghi payload nghiệp vụ của failed message, không ghi toàn bộ `ErrorMessage`, không ghi cause và không truyền `Throwable` cho logger.

Để sử dụng consumer này, ứng dụng phải khai báo kênh `orders.errors` và nối cơ chế phát lỗi của adapter, poller hoặc executor vào kênh đó. Đoạn code không tự thay thế kênh lỗi mặc định hay các logger của client bên ngoài.

Handler trả về `void` là một điểm tiêu thụ cuối trong ví dụ. Với queue hoặc broker, việc tiêu thụ lỗi và kết thúc bình thường có thể ảnh hưởng recovery, acknowledgment hoặc retry. Cần thiết kế riêng quyết định retry, đưa vào nơi lưu thông điệp lỗi hoặc phản hồi lỗi cho gateway. Việc sửa cách ghi log không được vô tình biến một yêu cầu thất bại thành xử lý thành công.

Nếu vẫn cần stack trace phục vụ điều tra, hãy thiết kế cơ chế chẩn đoán có phạm vi dữ liệu được kiểm soát hoặc tái hiện bằng dữ liệu giả. Không giả định bỏ dòng exception đầu tiên sẽ loại được mọi dữ liệu nhạy cảm trong cause chain.

## 9. Masking, redaction và log injection

### 9.1. Vì sao che vài trường chưa đủ?

Một DTO có thể có `email`, nhưng dữ liệu tương tự cũng có thể nằm trong `contact`, JSON lồng nhau hoặc `deliveryNote`. Một regex tìm khóa `password` không bao phủ các vị trí đó.

Các lựa chọn cần phân biệt:

- **Loại bỏ:** không xuất trường; đây là lựa chọn phù hợp khi vận hành không cần giá trị.
- **Masking:** che một phần; phần còn lại vẫn có thể nhận diện người hoặc hồ sơ.
- **Băm:** tạo dấu vết ổn định; dữ liệu có tập giá trị nhỏ có thể bị dò bằng cách tính lại.
- **HMAC:** có thể dùng cho liên kết có kiểm soát khi được thiết kế cùng quản lý khóa và phạm vi sử dụng; vẫn tạo dữ liệu có thể liên kết.
- **Mã hóa:** bảo vệ dữ liệu khi chưa giải mã, nhưng không biến việc thu thập payload vào log thành một nhu cầu vận hành hợp lý.

Trong luồng minh họa, sinh UUID quan sát tránh nhu cầu đưa email hoặc bản băm email vào log.

Nếu phải redaction một cấu trúc để phục vụ mục đích được xác định, hãy tạo bản biểu diễn mới, xử lý cấu trúc lồng nhau, không thay đổi message nghiệp vụ và quy định hành vi khi redaction lỗi. Khi không tạo được biểu diễn an toàn, chỉ xuất sự kiện như `diagnostic.redaction_failed` cùng metadata được phép; không fallback sang serialize đối tượng gốc.

### 9.2. Template cố định chưa đủ nếu giá trị không được kiểm soát

~~~java
// Dù dùng placeholder, giá trị ngoài hệ thống vẫn có thể chứa CR/LF.
log.info("request_id={}", externalRequestId);
~~~

Chuỗi chứa ký tự xuống dòng có thể làm đầu ra text trông như nhiều sự kiện. Cần giới hạn độ dài, kiểm tra định dạng và dùng encoder xử lý đúng giá trị theo định dạng đầu ra. JSON giúp phân định trường nếu được encode đúng, nhưng việc chuyển payload thành JSON vẫn giữ nguyên dữ liệu nhạy cảm trong payload.

OWASP phân biệt template cố định, kiểm tra dữ liệu và encode đầu ra; parameterized logging tự nó không chặn CR/LF log injection. Xem [Logging Cheat Sheet, mục Log Injection](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#log-injection).

Hàm `SafeLogFields` giới hạn trường biến đổi về UUID hoặc hằng `missing`. Cách này thu hẹp cả rủi ro nội dung nhạy cảm lẫn ký tự điều khiển trong chính các trường do hàm xuất ra.

## 10. Kết hợp logs, metrics và traces đúng vai trò

Spring Integration hỗ trợ Micrometer Observation cho metrics và tracing. Observation không đồng nghĩa ứng dụng phải thu thập payload; dữ liệu thêm vào tag, span event hoặc baggage vẫn cần một hợp đồng riêng. Xem [Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html).

| Kênh quan sát | Nên cung cấp điều gì trong ví dụ | Cần tránh |
| --- | --- | --- |
| Logs | Sự kiện, request ID, bước và kết quả đã chuẩn hóa | Payload, headers tổng thể, exception message thô |
| Metrics | Số yêu cầu, số thất bại, phân bố thời gian theo luồng và loại kết quả | Email, token, request ID, message ID làm tag |
| Traces | Quan hệ giữa các bước và hệ thống, thời gian, trace ID/span ID | Request body, baggage chứa thông tin khách hàng, URL thô có query nhạy cảm |

Các ID ngẫu nhiên thường có số lượng giá trị rất lớn. Chúng có ích để tra một lần xử lý trong logs hoặc traces, nhưng đưa chúng vào metric tag làm tăng cardinality mạnh.

Ngược lại, một `error_code` hữu hạn như `DEPENDENCY_TIMEOUT` phù hợp hơn cho phép đếm hoặc phân loại lỗi. Nếu “mã lỗi” được tạo bằng cách ghép nội dung exception, nó vừa có thể làm tăng cardinality vừa làm lộ dữ liệu.

Trace ID có thể tự được thêm vào log thông qua cấu hình MDC. Không nên đặt một bản sao payload vào MDC để “tự động có ngữ cảnh ở mọi nơi”. Khi đi qua `ExecutorChannel` hoặc poller, việc truyền và dọn ngữ cảnh giữa các thread phải theo cơ chế context propagation của ứng dụng; không dựa vào việc thread trước đó tình cờ giữ đúng MDC.

Cũng cần kiểm tra exporter hoặc instrumentation có tự ghi exception event hay không. Một dòng log sạch không chứng minh span tương ứng cũng sạch.

## 11. Kiểm chứng bằng dữ liệu canary

Canary ở đây là chuỗi giả có dấu hiệu rõ ràng, dùng để phát hiện dữ liệu đi nhầm vào đầu ra. Không dùng token hay thông tin khách hàng thật để thử.

### 11.1. Kiểm tra bộ chọn metadata

Các kiểm thử minh họa dùng JUnit 5. Chúng kiểm tra ranh giới chọn trường, không khởi động toàn bộ application context:

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;

class SafeLogFieldsTest {

    @Test
    void emitsExactlyTheAllowedFields() {
        UUID requestId =
                UUID.fromString("8f4e8631-7d25-4ea3-9f5c-102c2d770e72");

        Message<String> message = MessageBuilder
                .withPayload(
                        "EMAIL_CANARY@example.test DELIVERY_NOTE_CANARY")
                .setHeader("Authorization", "Bearer HEADER_SECRET_CANARY")
                .setHeader("Cookie", "session=COOKIE_SECRET_CANARY")
                .setHeader(SafeLogFields.REQUEST_ID, requestId)
                .build();

        String expected = "event=order.received"
                + " flow=orders"
                + " request_id=" + requestId
                + " message_id=" + message.getHeaders().getId();

        assertEquals(expected, SafeLogFields.received(message));
    }

    @Test
    void doesNotStringifyPayloadOrInvalidHeader() {
        Object sensitiveObject = new Object() {
            @Override
            public String toString() {
                throw new AssertionError(
                        "Không được stringify đối tượng nhạy cảm");
            }
        };

        Message<Object> message = MessageBuilder
                .withPayload(sensitiveObject)
                .setHeader(SafeLogFields.REQUEST_ID, sensitiveObject)
                .build();

        String actual = assertDoesNotThrow(
                () -> SafeLogFields.received(message));

        String expected = "event=order.received"
                + " flow=orders"
                + " request_id=missing"
                + " message_id=" + message.getHeaders().getId();

        assertEquals(expected, actual);
    }
}
~~~

Phép so sánh toàn bộ chuỗi trong kiểm thử đầu tiên giúp phát hiện cả việc vô tình thêm trường. Kiểm thử thứ hai phát hiện việc gọi `toString()` trên payload hoặc header sai kiểu, thay vì chỉ kiểm tra một chuỗi bí mật đã biết.

Hai kiểm thử này chưa kiểm tra LoggingHandler, encoder, MDC hoặc log framework. Chúng cũng chưa khẳng định luồng nghiệp vụ hoàn chỉnh giữ nguyên hành vi.

### 11.2. Kiểm tra đầu ra thực tế của cả luồng

Trong môi trường kiểm thử, gửi các trường hợp sau qua gateway hoặc adapter thực:

| Trường hợp | Dữ liệu giả đặt vào đâu | Điều cần kiểm chứng |
| --- | --- | --- |
| Thành công | Payload và header xác thực | Chỉ có metadata theo hợp đồng |
| Service ném lỗi | Exception message và cause có `EXCEPTION_SECRET_CANARY` | Canary không xuất hiện trong log hoặc span |
| Filter từ chối | Ghi chú chứa `DISCARD_SECRET_CANARY` | Nhánh discard chỉ ghi mã lý do |
| Retry rồi thất bại | Message chứa cùng canary qua nhiều lần thử | Mọi lần thử và recovery đều giữ hợp đồng |
| Aggregator timeout | Các message con có `GROUP_SECRET_CANARY` | Không dump nhóm hoặc khóa nhóm nhạy cảm |
| Header không hợp lệ | Chuỗi chứa CR/LF hoặc đối tượng tùy ý | Không tạo sự kiện giả, không stringify đối tượng |
| Bật logger chẩn đoán dự kiến | Canary như các trường hợp trên | Không xuất message thô từ framework hoặc client |

Nếu thu thập sự kiện qua Logback appender trong kiểm thử, đừng chỉ kiểm tra `getFormattedMessage()`. Cần xem thêm throwable proxy, argument hoặc structured fields, marker và MDC. Đầu ra sau encoder cũng cần được kiểm tra vì nó có thể bổ sung trường hoặc biến đổi chuỗi.

Với luồng bất đồng bộ, đợi theo điều kiện hoàn tất và flush cơ chế xuất log trước khi kiểm tra. Một assertion chạy trước khi message được xử lý có thể báo sạch trong khi dữ liệu chưa được ghi.

Canary có thể bị JSON escape, URL encode hoặc biểu diễn lại. Vì vậy, kiểm tra đầu ra đã giải mã phù hợp cùng schema trường được cho phép; tìm chuỗi thô đơn thuần không bao phủ mọi biến đổi. Đồng thời xác nhận email và ghi chú vẫn tới đúng service: bảo vệ log không được làm thay đổi payload nghiệp vụ.

## 12. Điều tra lỗi mà vẫn đủ thông tin

Giả sử dashboard báo số lỗi timeout tăng. Một quy trình điều tra không cần đọc payload có thể là:

1. Xem metric theo `flow=orders` và nhóm kết quả thất bại.
2. Tìm log `event=order.failed`, `error_code=DEPENDENCY_TIMEOUT` trong khoảng thời gian tương ứng.
3. Dùng `request_id`, hoặc trace ID nếu có, để tìm các bước liên quan.
4. So sánh thời gian xử lý, số lần retry và tên endpoint được định nghĩa sẵn.
5. Tái hiện bằng dữ liệu giả với cùng kích thước hoặc đặc điểm cấu trúc khi cần phân tích sâu.

Nếu chỉ cần biết request quá lớn, có thể dùng một bucket kích thước hoặc bộ đếm đã được chấp thuận thay vì ghi nội dung. Không đo bằng cách serialize payload chỉ để xây một dòng log; thao tác đó vừa có chi phí vừa tạo thêm đường xử lý dữ liệu.

Kho lưu message lỗi để replay, nếu hệ thống cần, phải được thiết kế như nơi lưu dữ liệu nghiệp vụ với kiểm soát truy cập tương ứng. Nó không phải kho log vận hành và không nên bị collector tự động đưa toàn bộ nội dung lên hệ thống tìm kiếm log.

Với log đã có, cần xác định nơi được thu thập, ai có quyền tra cứu và thời gian lưu. Nếu phát hiện canary trong thử nghiệm, sửa điểm phát sinh rồi chạy lại các nhánh liên quan; chỉ thêm bộ lọc trên màn hình hiển thị không chứng minh đường xuất đã được xử lý.

## 13. Bài thực hành áp dụng

Thực hiện trên một ứng dụng thử nghiệm có luồng nhận `Order`:

1. Định nghĩa hợp đồng log gồm event, flow, UUID quan sát, outcome và error code hữu hạn.
2. Đặt email giả, ghi chú canary và header xác thực giả vào message; không thêm trường nhạy cảm vào hợp đồng log.
3. Áp dụng `SafeLogFields` cho `log()`, rồi xác nhận service vẫn nhận nguyên dữ liệu cần thiết.
4. Cho service trả về bình thường, ném timeout và ném lỗi có canary trong cause. Xác định đường truyền lỗi của channel đang sử dụng.
5. Bổ sung tình huống filter discard hoặc một nhánh retry nếu ứng dụng có các thành phần này. Kiểm tra cả các logger của nhánh phụ.
6. Thu đầu ra đã encode cùng các trường MDC và exception; đối chiếu trường được phép, không chỉ sự vắng mặt của một chuỗi cụ thể.

Tiêu chí hoàn thành là vẫn liên kết được các sự kiện của một lần xử lý, phân biệt được thành công với thất bại và không tìm thấy dữ liệu canary tại các đầu ra quan sát được kiểm tra. Các nhánh chưa được kiểm tra phải được ghi nhận rõ, không suy rộng từ một kiểm thử thành công.

## 14. Những điểm cần giữ khi mở rộng luồng

Khi thêm transformer, hãy xem message mới có giữ metadata quan sát được phép hay không. Khi thêm router hoặc filter, dùng mã quyết định cố định để mô tả đường đi. Khi thêm aggregator, mô tả trạng thái nhóm bằng số lượng và kết quả, đồng thời đánh giá độ nhạy cảm của khóa nhóm. Khi thêm retry hoặc recovery, kiểm tra cả exception, kênh lỗi và nơi lưu thông điệp lỗi.

Ranh giới quan trọng nhất là đầu ra quan sát: **logger nhận một sự kiện được xây riêng theo danh sách cho phép**. Chỉ đổi mức log, dùng placeholder, bỏ full-message hay chuyển dữ liệu sang tracing đều không thay thế được ranh giới đó.
