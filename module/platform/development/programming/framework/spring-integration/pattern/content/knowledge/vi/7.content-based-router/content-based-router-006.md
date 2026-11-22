# Default route và dead-end route

## 1. Vì sao Content-Based Router cần đường mặc định?

Trong chương **Content-based router** của module **SPRING_INTEGRATION_PATTERN**, chúng ta triển khai Enterprise Integration Patterns bằng Spring Integration để tạo luồng thông điệp ít phụ thuộc, dễ mở rộng, dễ kiểm thử và quan sát. Router định tuyến message theo nội dung, còn Filter, Transformer, Splitter, Aggregator và Gateway xử lý những bước liên quan; retry, error channel và correlation giúp theo dõi các nhánh và xử lý lỗi.

Content-Based Router đưa ra một quyết định: **message này phải đi đến channel nào?** Khi có loại dữ liệu chưa được biết trước, mapping bị thiếu hoặc cấu hình sai, một message có thể không tìm được đường đi.

Ví dụ API nhận các sự kiện:

- **payment.completed** → cập nhật đơn hàng đã thanh toán;
- **payment.failed** → đưa vào luồng xử lý thanh toán thất bại;
- **payment.refunded** → xử lý hoàn tiền;
- một giá trị sự kiện mới **payment.chargeback** → chưa có handler trong phiên bản triển khai hiện tại.

Nếu router không định nghĩa hành vi cho **payment.chargeback**, sự kiện có thể gây exception hoặc bị xử lý sai. Việc có một **default route** rõ ràng cho phép hệ thống nhận diện tình huống chưa hỗ trợ. Nhưng default route cũng có thể bị lạm dụng, khiến lỗi mapping bị che khuất.

**Mục tiêu bài học**

1. Phân biệt default route với dead-end route và đường loại bỏ message có chủ đích.
2. Hiểu lúc nào Spring Integration chuyển message đến default output channel hoặc ném lỗi.
3. Thiết kế các lựa chọn: fail fast, quarantine/unmatched channel, hoặc nullChannel khi bỏ qua là hợp lệ.
4. Cấu hình Content-Based Router với channel mapping, defaultOutputChannel, resolutionRequired và channelKeyFallback.
5. Phân biệt lỗi **không tìm được đích** với lỗi **đã đến channel nhưng không được xử lý**.
6. Kiểm thử routing, xử lý lỗi, correlation và quan sát những message bị kẹt hoặc bỏ sót.

## 2. Ba tình huống thường bị gọi chung là dead-end

Thuật ngữ **dead-end route** thường được dùng theo nghĩa thiết kế hệ thống: message đã tới một điểm **không còn đường xử lý có ích**. Nó **không phải** tên một lớp router đặc biệt trong Spring Integration. Có ít nhất ba trường hợp cần phân biệt:

| Trường hợp | Ví dụ | Hệ quả |
| --- | --- | --- |
| **Không tìm được route** | Routing key không có channel mapping và không có fallback | Router báo lỗi định tuyến theo cấu hình mặc định |
| **Đã có route nhưng không có nơi xử lý** | Message vào một DirectChannel không có subscriber, hoặc QueueChannel không có poller | Send có thể thất bại, hoặc message chờ tồn đọng |
| **Được đưa vào ngõ cụt có chủ đích** | Router đưa loại event không cần xử lý đến nullChannel | Message bị loại theo thiết kế |

Các trường hợp trên cần chính sách và cách giám sát khác nhau. Cứ tăng số lần retry khi message không có route hợp lệ sẽ không tạo ra handler mới. Ngược lại, một QueueChannel có message chờ nhưng consumer tạm ngừng có thể là sự cố vận hành cần khôi phục consumer.

~~~mermaid
flowchart TD
    A["Incoming Message"] --> R{"Content-Based Router"}
    R -->|"Key đã ánh xạ"| C["Đích hợp lệ"]
    R -->|"Key chưa ánh xạ"| D{"Có default route?"}
    D -->|"Có"| U["Unmatched channel"]
    D -->|"Không"| E["Routing exception"]
    C --> H{"Có consumer và xử lý được?"}
    H -->|"Có"| S["Processed"]
    H -->|"Không"| X["Delivery error hoặc backlog"]
    U --> Q["Kiểm tra / quarantine / policy"]
~~~

Sơ đồ minh họa **quyết định ở mức khái niệm**. Trên thực tế, key có thể được diễn giải là tên channel và router có các tùy chọn resolution; phần tiếp theo sẽ giải thích chi tiết.

### 2.1. Default route

**Default route** là tuyến xử lý dự phòng khi router không xác định được channel đích hợp lệ từ dữ liệu hoặc cấu hình mapping. Spring Integration hỗ trợ **defaultOutputChannel** để chỉ ra destination này.

Default route có thể dùng để:

- Đưa sự kiện chưa hỗ trợ sang **unmatchedEventsChannel** để phân loại và điều tra.
- Đưa dữ liệu không được phép xử lý tiếp sang một nhánh kiểm tra **quarantine**, kết hợp lưu trữ hoặc cảnh báo nếu cần.
- Chuyển sự kiện **được phép bỏ qua** đến **nullChannel**.

Đặt default route không có nghĩa xử lý thành công nghiệp vụ. Nó chỉ quyết định **message được gửi tới đâu khi không tìm được đích chính**.

### 2.2. Dead-end do lỗi định tuyến

Một key không có mapping thường cần được coi là **sự kiện chưa được hỗ trợ** hoặc **lỗi cấu hình**. Nếu không có default output channel và không xác định được destination, router mặc định ném exception.

Điều này thường hữu ích: nếu người phát sự kiện đã nâng schemaVersion hoặc đổi tên eventType mà consumer chưa nâng cấp, fail fast giúp phát hiện chênh lệch hợp đồng thay vì bỏ qua im lặng.

### 2.3. Dead-end sau khi đã định tuyến

Giả sử router chọn **invoiceCommandsChannel**, nhưng không có endpoint nào đang nhận message. Với DirectChannel, send() có thể không hoàn tất bình thường vì không có subscriber. Với QueueChannel, send() có thể thành công trong khi message tiếp tục nằm trong queue do không có poller.

**Default output channel của router không tự cứu hai trường hợp này.** Nó xử lý giai đoạn **chọn đích**, không thay thế cơ chế retry, DLQ, error channel hoặc monitoring của channel đã nhận message.

## 3. Phân biệt fallback, discard và dead-letter

Các đường đi sau có mục đích khác nhau:

| Đường đi | Ý nghĩa | Điều bắt buộc làm rõ |
| --- | --- | --- |
| **Default output channel** | Nơi nhận khi routing không xác định được channel chính | Ai sẽ kiểm tra/tiếp tục xử lý? |
| **nullChannel** | Đích nhận rồi loại bỏ message | Loại nào được phép bỏ? Có cần metric? |
| **Quarantine / unmatched channel** | Lưu hoặc xử lý riêng dữ liệu chưa có route | Lưu ở đâu, thời hạn giữ, ai xem xét? |
| **errorChannel** | Nhận ErrorMessage theo cơ chế xử lý lỗi của endpoint/adapter | Lỗi nào được chuyển tới đây? |
| **Dead-letter queue (DLQ)** | Giữ message xử lý thất bại sau chính sách retry/redelivery | Nguyên nhân, số lần thử, thao tác phục hồi |

Đặt tên một MessageChannel là **deadLetterChannel** chưa tự tạo khả năng lưu bền, giới hạn retry hay dead-letter semantics. Muốn bảo đảm có thể khôi phục message sau restart, cần MessageStore bền, broker hoặc cơ chế lưu trữ phù hợp.

**Nguyên tắc:** message không được định tuyến là **unmatched**, message bị lỗi trong xử lý là **failed**, còn message được thiết kế để bỏ qua là **discarded**. Giám sát ba nhóm riêng giúp tránh đếm sai chất lượng hệ thống.

## 4. Cơ chế channel mapping của Content-Based Router

Content-Based Router thường xác định một **routing key** từ payload hoặc header, rồi ánh xạ key thành **tên MessageChannel**. Trong Spring Integration có nhiều cách:

- **HeaderValueRouter**: lấy key từ một header.
- **PayloadTypeRouter**: lấy key từ kiểu payload.
- **SpEL-based router**: tính key bằng biểu thức.
- **Custom/POJO router**: chạy hàm Java để quyết định key hoặc destination.
- **IntegrationFlow DSL**: khai báo hàm chọn key và các **channelMapping**.

Ví dụ miền thanh toán:

| Routing key | Channel | Ý nghĩa |
| --- | --- | --- |
| COMPLETED | completedPaymentsChannel | Xử lý thanh toán thành công |
| FAILED | failedPaymentsChannel | Xử lý thanh toán thất bại |
| REFUNDED | refundedPaymentsChannel | Xử lý hoàn tiền |
| CHARGEBACK | Chưa mapping | Sự kiện chưa hỗ trợ ở phiên bản hiện tại |

### 4.1. Mapping key khác với tên channel

Key **COMPLETED** chỉ là một **nhãn nghiệp vụ**. Channel thật được khai báo với tên **completedPaymentsChannel**. Giữ hai khái niệm này riêng giúp:

- Quy tắc route không phụ thuộc vào tên bean kỹ thuật.
- Đổi tên channel mà không yêu cầu producer đổi eventType.
- Giới hạn những nơi message được phép đi bằng **allowlist mapping**.

Không nên để external client gửi thẳng tên bean channel rồi router tự resolve tùy ý: có thể dẫn tới định tuyến vào channel không mong muốn, thậm chí tạo vòng lặp. Hãy validate giá trị, ánh xạ rõ sang các destination được phép và tránh dùng input chưa tin cậy để điều khiển topology.

## 5. Ví dụ Java DSL: default route đến unmatched channel

Ví dụ dùng Java 17+ với Spring Integration Java DSL. Ta xây dựng **routing function thuần** và ba nhánh xử lý được phép, còn sự kiện mới sẽ tới **unmatchedPaymentsChannel**.

### 5.1. Model và quyết định route

~~~java
import java.math.BigDecimal;
import java.util.Locale;

record PaymentEvent(
        String eventId,
        String paymentId,
        String eventType,
        BigDecimal amountVnd) {}

final class PaymentRoutingRules {
    private PaymentRoutingRules() {}

    static String routeKey(PaymentEvent event) {
        if (event == null || event.eventType() == null) {
            return "UNKNOWN";
        }

        return switch (event.eventType().trim()
                .toUpperCase(Locale.ROOT)) {
            case "PAYMENT.COMPLETED" -> "COMPLETED";
            case "PAYMENT.FAILED" -> "FAILED";
            case "PAYMENT.REFUNDED" -> "REFUNDED";
            default -> "UNKNOWN";
        };
    }
}
~~~

Hàm **routeKey** chỉ quyết định loại sự kiện, không gọi database, không gửi message và không biết bean channel. Với đầu vào thiếu eventType, hàm trả **UNKNOWN** để router có thể xử lý qua đường unmatched. Đây là chính sách minh họa; nếu hệ thống yêu cầu từ chối message thiếu trường bắt buộc, hãy validate ở ranh giới trước router và phát lỗi phù hợp.

### 5.2. Định nghĩa channel và flow

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class PaymentRouterConfig {

    @Bean
    MessageChannel paymentInputChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel completedPaymentsChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel failedPaymentsChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel refundedPaymentsChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel unmatchedPaymentsChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow paymentRouterFlow() {
        return IntegrationFlow.from("paymentInputChannel")
                .<PaymentEvent, String>route(
                        PaymentRoutingRules::routeKey,
                        mapping -> mapping
                                .channelMapping(
                                        "COMPLETED", "completedPaymentsChannel")
                                .channelMapping(
                                        "FAILED", "failedPaymentsChannel")
                                .channelMapping(
                                        "REFUNDED", "refundedPaymentsChannel")
                                .defaultOutputChannel(
                                        "unmatchedPaymentsChannel"))
                .get();
    }
}
~~~

Trong Spring Integration **6.0 trở lên**, khi cấu hình default output channel cho mapping router, Spring tự vô hiệu hóa **channelKeyFallback** theo mặc định. Nhờ vậy key **UNKNOWN** không bị thử làm tên bean channel; nó được đưa đến **unmatchedPaymentsChannel**. Với các phiên bản cũ hơn hoặc cấu hình tùy chỉnh, cần kiểm tra cụ thể **channelKeyFallback** và **resolutionRequired** như phần 7.

Router chỉ kết nối đường đi. Để message được xử lý, cần đăng ký **endpoint/subscriber** cho từng channel. Ví dụ:

~~~java
interface PaymentEventService {
    void onCompleted(PaymentEvent event);
    void onFailed(PaymentEvent event);
    void onRefunded(PaymentEvent event);
}

interface UnmatchedPaymentService {
    void quarantine(PaymentEvent event);
}
~~~

Các bean IntegrationFlow xử lý nhánh có thể được đặt trong cùng lớp PaymentRouterConfig:

~~~java
@Bean
IntegrationFlow completedFlow(PaymentEventService service) {
    return IntegrationFlow.from("completedPaymentsChannel")
            .handle(PaymentEvent.class, (event, headers) -> {
                service.onCompleted(event);
                return null;
            })
            .get();
}

@Bean
IntegrationFlow failedFlow(PaymentEventService service) {
    return IntegrationFlow.from("failedPaymentsChannel")
            .handle(PaymentEvent.class, (event, headers) -> {
                service.onFailed(event);
                return null;
            })
            .get();
}

@Bean
IntegrationFlow refundedFlow(PaymentEventService service) {
    return IntegrationFlow.from("refundedPaymentsChannel")
            .handle(PaymentEvent.class, (event, headers) -> {
                service.onRefunded(event);
                return null;
            })
            .get();
}

@Bean
IntegrationFlow unmatchedFlow(UnmatchedPaymentService service) {
    return IntegrationFlow.from("unmatchedPaymentsChannel")
            .handle(PaymentEvent.class, (event, headers) -> {
                service.quarantine(event);
                return null;
            })
            .get();
}
~~~

**UnmatchedPaymentService** có thể ghi message và metadata tối thiểu vào một nơi lưu trữ để điều tra, báo cảnh báo khi số sự kiện không khớp tăng, hoặc trả về lỗi rõ ràng nếu sự kiện đến từ một Gateway đồng bộ. Nếu cần phục hồi sau restart, việc service chỉ ghi log hoặc giữ message trong RAM sẽ **không đủ**.

### 5.3. Gửi message

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

// paymentInputChannel là bean được inject từ Spring context.
PaymentEvent event = new PaymentEvent(
        "evt-710", "pay-710",
        "payment.chargeback",
        new BigDecimal("1500000"));

Message<PaymentEvent> message = MessageBuilder.withPayload(event)
        .setHeader("businessCorrelationId", event.paymentId())
        .setHeader("schemaVersion", 1)
        .build();

boolean accepted = paymentInputChannel.send(message);
~~~

Event payment.chargeback đi vào nhánh **unmatched** do key **UNKNOWN**. **accepted == true** chỉ chứng minh thao tác gửi vào flow theo semantics của channel thành công; nó không tự bảo đảm quarantine đã được lưu bền nếu nhánh chuyển sang bất đồng bộ hoặc hệ thống lưu trữ bên ngoài có lỗi.

### 5.4. Hành vi mong đợi

| eventType | routeKey | Destination |
| --- | --- | --- |
| payment.completed | COMPLETED | completedPaymentsChannel |
| payment.failed | FAILED | failedPaymentsChannel |
| payment.refunded | REFUNDED | refundedPaymentsChannel |
| payment.chargeback | UNKNOWN | unmatchedPaymentsChannel |
| rỗng/null | UNKNOWN | unmatchedPaymentsChannel hoặc validate trước router |

Điểm thiết kế quan trọng: **unmatched không đồng nghĩa invalid**. Một eventType mới có thể hoàn toàn hợp lệ theo producer nhưng consumer chưa hỗ trợ. Luồng quarantine nên lưu lý do đủ để bổ sung mapping hoặc replay message khi đã nâng cấp consumer.

## 6. Không cấu hình default route: fail fast

Một số trường hợp không nên có fallback âm thầm. Ví dụ hệ thống thanh toán chỉ chấp nhận ba trạng thái đã được thống nhất trong một hợp đồng nội bộ; mọi key khác nghĩa là producer gửi sai hoặc phiên bản không tương thích.

~~~java
@Bean
IntegrationFlow strictPaymentRouterFlow() {
    return IntegrationFlow.from("strictPaymentInputChannel")
            .<PaymentEvent, String>route(
                    PaymentRoutingRules::routeKey,
                    mapping -> mapping
                            .channelMapping("COMPLETED",
                                    "completedPaymentsChannel")
                            .channelMapping("FAILED",
                                    "failedPaymentsChannel")
                            .channelMapping("REFUNDED",
                                    "refundedPaymentsChannel")
                            .channelKeyFallback(false))
            .get();
}
~~~

Ví dụ cần khai báo strictPaymentInputChannel và ba channel đích. **channelKeyFallback(false)** giúp tránh việc router thử tìm bean có tên trùng một routing key chưa được mapping. Khi **UNKNOWN** không map sang channel và không có default, router phát **MessagingException/MessageDeliveryException** tùy endpoint và phiên bản, thay vì tự bỏ message.

**Fail fast phù hợp khi:**

- Hợp đồng eventType đóng và thay đổi phải được triển khai đồng bộ;
- Bỏ qua message có thể gây mất tiền hoặc thiếu dữ liệu kiểm toán;
- Không có cơ chế xử lý thủ công an toàn cho loại sự kiện lạ;
- Lỗi cấu hình cần làm build/deployment hoặc xử lý runtime thất bại rõ ràng.

Với **DirectChannel** đồng bộ, exception từ router thường có thể truyền về caller của send(). Với inbound adapter/ExecutorChannel/poller, lỗi có thể đi theo cơ chế error channel của thành phần đó; không mặc định mong đợi caller HTTP ban đầu sẽ luôn nhận cùng một exception.

## 7. resolutionRequired và channelKeyFallback: hai quyết định khác nhau

Đây là phần dễ gây nhầm lẫn nhất khi cấu hình default route. Cả hai đều liên quan đến quá trình **từ routing key tìm ra MessageChannel**, nhưng tác động ở hai bước khác nhau.

### 7.1. channelKeyFallback: có thử key như tên channel không?

Giả sử routeKey trả **SPECIAL** và **không tồn tại channelMapping("SPECIAL", "...")**.

- Khi **channelKeyFallback=true**, router có thể thử tìm trực tiếp một bean channel tên **SPECIAL**.
- Khi **channelKeyFallback=false**, router không suy luận channel từ chuỗi **SPECIAL**; kết quả được xử lý bằng default output channel hoặc báo lỗi theo hợp đồng hiện có.

Trong Spring Integration, mapping router truyền thống có **channelKeyFallback=true** theo mặc định. **Từ phiên bản 6.0, đặt default output channel sẽ tự đặt channelKeyFallback=false**, trừ khi ứng dụng chủ động thay đổi lại. Cấu hình này giúp fallback hoạt động như nhánh **default** của Java switch và tránh route đến bean trùng tên key ngoài ý muốn.

Với một hệ thống nhận eventType từ bên ngoài, nên ưu tiên **allowlist mapping**; tuyệt đối không dựa vào tính năng tìm channel từ key chưa được validate làm cơ chế phân quyền.

### 7.2. resolutionRequired: có bắt buộc phân giải được channel không?

Giả sử key **COMPLETED** đã map đến **completedPaymentsChannel**, nhưng channel đó không tồn tại trong ApplicationContext:

- **resolutionRequired=true** (mặc định): router báo lỗi khi không thể phân giải destination.
- **resolutionRequired=false**: router có thể bỏ qua destination không phân giải được; nếu có default output channel, message có thể được chuyển tới đó theo quy tắc router.

Vì đây thường là **lỗi triển khai**, không phải một eventType mới, tắt resolutionRequired có thể khiến sai tên channel bị che. Chỉ cho phép fallback trong trường hợp **đã xác định rõ** việc channel tùy chọn có thể vắng mặt.

### 7.3. Ma trận quyết định

| Tình huống | Hướng xử lý dự kiến | Nên giám sát |
| --- | --- | --- |
| Key đã map và channel tồn tại | Gửi đến channel đã map | Số message và lỗi của handler |
| Key chưa map, có default và channelKeyFallback=false | Gửi đến default | Unmatched event count |
| Key chưa map, không có default và không cho fallback theo key | Ném lỗi định tuyến | Unknown route exception |
| Key chưa map, channelKeyFallback=true, bean trùng tên key tồn tại | Có thể route trực tiếp đến bean đó | Nguy cơ route ngoài allowlist |
| Key đã map nhưng bean channel không tồn tại, resolutionRequired=true | Ném lỗi phân giải destination | Lỗi cấu hình/deployment |
| Key đã map nhưng bean channel không tồn tại, resolutionRequired=false và có default | Có thể chuyển đến default | Bất thường channel missing |
| Đã tìm được channel, send thất bại hoặc handler lỗi | Lỗi dispatch/processing; default không nhất thiết được dùng | Send failure / ErrorMessage |
| Đã tìm được QueueChannel, không có poller | Message có thể tồn đọng | Queue depth, message age |

**Lưu ý về phiên bản:** các tổ hợp cấu hình và API của router đã thay đổi theo thời gian. Ví dụ từ Spring Integration 6.0, tổ hợp có **defaultOutputChannel**, đồng thời ép **channelKeyFallback=true** và **resolutionRequired=true**, bị xem là mâu thuẫn và bị từ chối khi khởi tạo router. Luôn kiểm tra version thực tế của ứng dụng khi di chuyển từ Spring Integration 5.x sang 6.x/7.x.

### 7.4. Cấu hình tùy chọn khi channel có thể vắng mặt

~~~java
@Bean
IntegrationFlow optionalRouteFlow() {
    return IntegrationFlow.from("optionalEventsChannel")
            .<PaymentEvent, String>route(
                    PaymentRoutingRules::routeKey,
                    spec -> spec
                            .channelMapping("COMPLETED",
                                    "optionalCompletedChannel")
                            .defaultOutputChannel("unmatchedPaymentsChannel")
                            .resolutionRequired(false))
            .get();
}
~~~

Đoạn code chỉ minh họa tùy chọn; cần có optionalEventsChannel và unmatchedPaymentsChannel thật. Với nhánh **COMPLETED**, nếu channel được map không tồn tại, resolutionRequired(false) cho phép router sử dụng đường mặc định theo semantics đã cấu hình. Chọn cách này khi **sự vắng mặt của channel là trạng thái có thể chấp nhận được**, không phải khi viết nhầm tên bean.

## 8. Loại message có chủ đích với nullChannel

Đôi khi Router nhận một message **không cần xử lý tiếp** theo yêu cầu nghiệp vụ. Chẳng hạn analytics chỉ theo dõi một tập eventType, và toàn bộ sự kiện khác được phép bỏ qua.

Spring Integration có một channel đặc biệt tên **nullChannel**: nó chấp nhận message rồi loại bỏ. Có thể dùng làm default output channel:

~~~java
@Bean
IntegrationFlow optionalAnalyticsFlow() {
    return IntegrationFlow.from("analyticsInputChannel")
            .<PaymentEvent, String>route(
                    PaymentRoutingRules::routeKey,
                    mapping -> mapping
                            .channelMapping("COMPLETED",
                                    "analyticsCompletedChannel")
                            .defaultOutputChannel("nullChannel"))
            .get();
}
~~~

Ví dụ giả định analyticsInputChannel và analyticsCompletedChannel được khai báo, nhánh analytics có consumer thật. Event COMPLETED đi đến analyticsCompletedChannel; event chưa có mapping được đưa đến nullChannel và kết thúc.

**Không nên dùng nullChannel khi cần khả năng phát lại, điều tra hoặc đối soát.** Vì message bị loại, bạn sẽ không có payload để khôi phục sau khi bỏ qua. Nếu cần thống kê, hãy đo/ghi nhận trước điểm loại bỏ hoặc dùng một endpoint chuyên trách rồi mới gửi sang nullChannel.

### NullChannel khác dead-letter queue

| Điểm so sánh | nullChannel | Dead-letter queue / nơi lưu lỗi |
| --- | --- | --- |
| Mục đích | Bỏ message theo thiết kế | Lưu message không thể xử lý thành công |
| Có thể phát lại? | Không, trừ khi đã ghi ở nơi khác | Có thể nếu hệ thống lưu và công cụ replay hỗ trợ |
| Cần storage bền? | Không | Thường cần nếu recovery là yêu cầu |
| Dùng khi eventType chưa hỗ trợ nhưng quan trọng? | Không nên | Nên quarantine/đưa nơi kiểm tra |
| Có tự tạo retry? | Không | Không; cần cấu hình retry/redelivery riêng |

**Không dùng default nullChannel như cách che lỗi mapping** trong luồng thanh toán, tồn kho hoặc kế toán. Nếu hệ thống có ràng buộc kiểm toán, một message có business key chưa rõ thường phải được **báo lỗi hoặc giữ để phân loại**.

## 9. Dead-end sau router: channel đúng nhưng không có downstream hữu ích

Một route có tên và được phân giải thành bean chưa chắc đã là **đường đi thành công**.

~~~mermaid
flowchart TD
    R["Router đã chọn channel"] --> C{"Loại channel"}
    C -->|"DirectChannel"| D{"Có subscriber?"}
    D -->|"Không"| E["Dispatch failure"]
    D -->|"Có"| H["Handler thực thi"]
    C -->|"QueueChannel"| Q{"Có poller/consumer?"}
    Q -->|"Không"| B["Backlog tăng / queue đầy"]
    Q -->|"Có"| W["Consumer xử lý"]
    C -->|"ExecutorChannel"| X{"Executor chấp nhận?"}
    X -->|"Không"| F["Rejection / quá tải"]
    X -->|"Có"| A["Worker xử lý về sau"]
~~~

### 9.1. DirectChannel không có subscriber

DirectChannel dispatch trực tiếp đến **một subscriber được chọn**. Nếu không có subscriber, lỗi gửi có thể xuất hiện ngay trong call stack. Đây là lỗi **wiring**, khác với routing key không map được; đặt default output channel trên router không tự chuyển lỗi này sang unmatched channel.

Nếu một channel có nhiều subscriber, chúng là các ứng viên nhận **một lần dispatch**, không phải tự tạo chuỗi A → B → C. Nếu yêu cầu nhiều bước xử lý, hãy nối các endpoint qua các channel theo thứ tự hoặc dùng IntegrationFlow.

### 9.2. QueueChannel không có poller

QueueChannel là PollableChannel: send có thể chấp nhận message vào hàng đợi, nhưng **không ai nhận** nếu không có consumer gọi receive() hoặc endpoint poller. Khi queue đầy, producer có thể bị chặn hoặc send trả false theo timeout.

Thông thường QueueChannel dùng bộ nhớ; khi restart, backlog có thể mất. Nếu muốn xử lý message về sau và sống qua restart, cần persistent MessageStore hoặc broker bền vững, cộng với chính sách ack, retry và idempotency.

### 9.3. ExecutorChannel và lỗi sau khi send

ExecutorChannel chuyển công việc cho Executor. Lời gọi send có thể trả về trước khi handler xử lý, vì thế một exception xảy ra sau đó không tự quay lại caller. Lỗi còn phụ thuộc vào executor rejection policy, error handler và cách endpoint được cấu hình. Default route chỉ có thể giải quyết **không tìm thấy đích**; nó không thay thế xử lý lỗi bất đồng bộ.

### 9.4. Vòng lặp định tuyến

Một mapping sai có thể đưa message **quay về inputChannel**, gây vòng lặp ngay trong một thread đồng bộ hoặc tạo backlog vô hạn trong flow async. Khi channelKeyFallback được bật và routing key đến từ input chưa tin cậy, đây là một rủi ro đáng chú ý.

Biện pháp: quản lý allowlist channel, review topology, dùng default route an toàn, đặt giới hạn/hop count khi thiết kế có nhiều router và test trường hợp key lạ. Không cần dùng loop detection tự động nếu ứng dụng không có cơ chế đó; hãy chủ động bảo vệ cấu hình.

## 10. Error channel, retry và dead-end trong vận hành

### 10.1. Khi nào exception quay về caller?

Trong chuỗi DirectChannel đồng bộ, exception từ router hoặc downstream thường có thể đi ngược về phương thức send(). Đó là hành vi hữu ích khi Gateway/API cần báo ngay rằng message không được định tuyến.

Trong luồng bất đồng bộ với ExecutorChannel, QueueChannel/poller hoặc inbound adapter, exception xảy ra **sau** send() thường phải được xử lý ở phía consumer. ErrorMessage có thể được gửi đến **errorChannel** theo cấu hình, nhưng không phải mọi exception mặc nhiên được gửi vào một channel chung.

### 10.2. Không retry vô điều kiện lỗi thiếu route

| Loại lỗi | Retry có giúp? | Cách xử lý ưu tiên |
| --- | --- | --- |
| Unknown eventType | Không, nếu chưa cập nhật mapping | Quarantine, cảnh báo, bổ sung handler |
| Channel bean thiếu vì cấu hình sai | Không, khi topology chưa được sửa | Fail fast, sửa cấu hình/triển khai |
| DirectChannel không có subscriber | Không, khi endpoint chưa được gắn | Sửa wiring/khởi động endpoint |
| QueueChannel có consumer bị chậm | Có thể xử lý khi consumer hồi phục | Theo dõi backlog, capacity, health |
| REST downstream timeout | Có thể, nếu giao dịch idempotent | Retry có giới hạn và backoff |
| Handler đã ghi side effect rồi mất phản hồi | Retry có thể tạo duplicate | Idempotency key, deduplication |

Retry một routing key **UNKNOWN** hàng nghìn lần không làm hệ thống tự hiểu eventType mới. Với lỗi hợp đồng, cần có **đường xử lý thủ công hoặc quy trình cập nhật version**.

### 10.3. Quarantine và replay

Một unmatched service cần quyết định những thông tin nào đủ để xử lý sự kiện sau:

1. **eventId** hoặc business key ổn định để tránh phát lại trùng lặp.
2. **eventType gốc**, schemaVersion, thời gian tiếp nhận và routing reason.
3. **Payload cần thiết** để phục hồi, được bảo vệ theo chính sách dữ liệu.
4. **Trạng thái xử lý**: received, pending review, ready to replay, replayed, rejected.
5. **Số lần replay** và lý do thất bại cuối cùng.

Không cần dồn tất cả vào message headers; các thông tin audit thường được lưu trong schema riêng. Một MessageChannel tự nó không phải database, nên **unmatchedPaymentsChannel** chỉ tạo đường đi; endpoint phía sau phải thực hiện lưu bền nếu hợp đồng yêu cầu.

### 10.4. Khi replay gặp phiên bản schema mới

Một message từng là unknown có thể trở thành supported sau khi deploy router mới. Trước khi replay, phải bảo đảm:

- Consumer hiểu schemaVersion và payload.
- Event chưa được xử lý qua một nhánh khác hoặc đã có idempotency.
- Thứ tự nghiệp vụ vẫn hợp lệ (ví dụ refund không thể xử lý trước payment completed nếu state machine yêu cầu).
- Truy vết phân biệt **lần nhận ban đầu** và **lần replay**.

Không thay thế nguyên eventId nếu consumer sử dụng eventId làm khóa deduplication. Có thể thêm metadata replayAttempt hoặc replayReason ở nơi lưu trữ thay vì sửa eventId.

## 11. Quan sát route mặc định và đường cụt

Các loại message bị loại/không khớp có thể tăng âm thầm trong khi hệ thống vẫn trả lời các nhánh hợp lệ. Vì vậy default route nên có metrics và dashboard tối thiểu:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| **route_selected_total{route}** | Số message đến từng route, phát hiện nhánh ít hoạt động |
| **route_unmatched_total{eventType}** | Sự kiện chưa được mapping; cardinality của label cần được kiểm soát |
| **route_resolution_failed_total** | Lỗi channel không phân giải được |
| **route_send_failed_total{channel}** | Destination có lỗi khi dispatch |
| **dead_end_backlog_age** | Độ tuổi message chờ lâu nhất trong queue |
| **quarantine_pending_total** | Số message chưa được phân loại/replay |
| **replay_failed_total** | Lỗi khi xử lý lại event |

Chú ý không dùng eventId/orderId làm label metric vì cardinality có thể bùng nổ. Nên dùng eventType đã chuẩn hóa hoặc route name giới hạn số giá trị; sử dụng trace/log đã lọc dữ liệu nhạy cảm để tra cứu theo eventId khi cần.

### Correlation theo nghiệp vụ

Các header như **businessCorrelationId** giúp theo dõi nhiều sự kiện của cùng payment/order; **traceId/spanId** giúp quan sát từng nhánh xử lý. Hai cơ chế này không đồng nghĩa; correlation không tự bảo đảm delivery hay retry an toàn.

Khi một message đi default route, hãy giữ businessCorrelationId để hỗ trợ điều tra, nhưng chỉ log thông tin cần thiết. Dữ liệu thẻ, token và thông tin nhạy cảm không nên được đưa vào headers/log thông thường.

## 12. Kiểm thử default route và dead-end

Kiểm thử chỉ kiểm tra happy path không phát hiện được eventType mới, mapping sai tên hoặc channel không có consumer. Cần phối hợp **unit test rule**, **integration test router** và test với hạ tầng thực khi cần durability.

### 12.1. Unit test: xác định routing key

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class PaymentRoutingRulesTest {

    @Test
    void returnsMappedKeysForSupportedEvents() {
        PaymentEvent completed = new PaymentEvent(
                "evt-1", "pay-1",
                "payment.completed", BigDecimal.TEN);
        PaymentEvent refunded = new PaymentEvent(
                "evt-2", "pay-2",
                "payment.refunded", BigDecimal.TEN);

        assertEquals("COMPLETED",
                PaymentRoutingRules.routeKey(completed));
        assertEquals("REFUNDED",
                PaymentRoutingRules.routeKey(refunded));
    }

    @Test
    void usesUnknownKeyForNewOrMissingEventTypes() {
        PaymentEvent unknown = new PaymentEvent(
                "evt-3", "pay-3",
                "payment.chargeback", BigDecimal.TEN);
        PaymentEvent missingType = new PaymentEvent(
                "evt-4", "pay-4",
                null, BigDecimal.TEN);

        assertEquals("UNKNOWN", PaymentRoutingRules.routeKey(unknown));
        assertEquals("UNKNOWN", PaymentRoutingRules.routeKey(missingType));
    }
}
~~~

Unit test giúp đảm bảo thuật toán phân loại, nhưng chưa kiểm chứng Spring tạo channel và endpoint đúng.

### 12.2. Integration test: unknown đi fallback, key hợp lệ không đi fallback

Ví dụ dựng Spring context tối thiểu có hai destination DirectChannel và router. Test đăng ký subscriber trong phạm vi từng test rồi hủy đăng ký ở finally để tránh ảnh hưởng test khác.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(DefaultRouteIntegrationTest.TestConfig.class)
class DefaultRouteIntegrationTest {

    @Configuration
    @EnableIntegration
    static class TestConfig {
        @Bean
        MessageChannel input() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel completed() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel unmatched() {
            return new DirectChannel();
        }

        @Bean
        IntegrationFlow routeEvents() {
            return IntegrationFlow.from("input")
                    .<PaymentEvent, String>route(
                            PaymentRoutingRules::routeKey,
                            r -> r.channelMapping("COMPLETED", "completed")
                                  .defaultOutputChannel("unmatched"))
                    .get();
        }
    }

    @Autowired
    @Qualifier("input")
    MessageChannel input;

    @Autowired
    @Qualifier("completed")
    SubscribableChannel completed;

    @Autowired
    @Qualifier("unmatched")
    SubscribableChannel unmatched;

    @Test
    void unknownEventGoesOnlyToDefaultChannel() {
        AtomicInteger completedCount = new AtomicInteger();
        AtomicInteger unmatchedCount = new AtomicInteger();
        MessageHandler completedHandler =
                message -> completedCount.incrementAndGet();
        MessageHandler unmatchedHandler =
                message -> unmatchedCount.incrementAndGet();
        completed.subscribe(completedHandler);
        unmatched.subscribe(unmatchedHandler);

        try {
            PaymentEvent event = new PaymentEvent(
                    "evt-10", "pay-10",
                    "payment.chargeback", new BigDecimal("10000"));

            assertTrue(input.send(MessageBuilder.withPayload(event).build()));
            assertEquals(0, completedCount.get());
            assertEquals(1, unmatchedCount.get());
        } finally {
            completed.unsubscribe(completedHandler);
            unmatched.unsubscribe(unmatchedHandler);
        }
    }

    @Test
    void supportedEventDoesNotGoToDefaultChannel() {
        AtomicInteger completedCount = new AtomicInteger();
        AtomicInteger unmatchedCount = new AtomicInteger();
        MessageHandler completedHandler =
                message -> completedCount.incrementAndGet();
        MessageHandler unmatchedHandler =
                message -> unmatchedCount.incrementAndGet();
        completed.subscribe(completedHandler);
        unmatched.subscribe(unmatchedHandler);

        try {
            PaymentEvent event = new PaymentEvent(
                    "evt-11", "pay-11",
                    "payment.completed", new BigDecimal("50000"));

            assertTrue(input.send(MessageBuilder.withPayload(event).build()));
            assertEquals(1, completedCount.get());
            assertEquals(0, unmatchedCount.get());
        } finally {
            completed.unsubscribe(completedHandler);
            unmatched.unsubscribe(unmatchedHandler);
        }
    }
}
~~~

Trong test này DirectChannel đồng bộ giúp kiểm tra kết quả ngay sau send(). Nếu thay destination bằng ExecutorChannel, cần đợi handler hoàn tất bằng CountDownLatch hoặc cơ chế đồng bộ test khác. Không dùng sleep tùy ý để suy đoán timing.

### 12.3. Test dead-end đã có route

Một integration test hữu ích khác tạo DirectChannel **không có subscriber**, map một key đến channel đó, rồi xác minh send() gây lỗi theo hợp đồng. Test tương ứng với QueueChannel nên chứng minh message tồn tại trong queue hoặc bị báo đầy khi không có poller, thay vì mong đợi router tự chuyển sang default channel.

Để tránh nhầm lẫn, hãy đặt tên test rõ:

- **unknownKeyUsesDefaultRoute**
- **mappedKeyUsesMappedChannel**
- **unknownKeyWithoutDefaultFailsFast**
- **mappedKeyWithMissingChannelFailsResolution**
- **mappedDirectChannelWithoutSubscriberFailsDelivery**
- **queueWithoutConsumerAccumulatesBacklog**
- **nullChannelDropsOnlyWhitelistedIgnoredEvents**

Ngoài ra, test trường hợp mapping sai trong quá trình deploy bằng kiểm tra bean/channel và startup verification; khi yêu cầu durability, phải thực hiện test restart process hoặc broker chứ không chỉ mock MessageStore.

## 13. Bài thực hành: xây dựng fallback an toàn

Hãy thiết kế Content-Based Router cho hệ thống đơn hàng với các sự kiện:

| eventType | Route dự kiến |
| --- | --- |
| order.created | orderCreatedChannel |
| order.cancelled | orderCancelledChannel |
| order.fulfilled | orderFulfilledChannel |
| order.returned | Chưa hỗ trợ, cần quarantine |
| missing/unknown | Theo policy validation hoặc quarantine |

**Yêu cầu thực hiện**

1. Xây dựng record **OrderEvent(eventId, orderId, eventType, schemaVersion)**.
2. Viết hàm Java thuần chọn routing key; tránh trả trực tiếp tên bean từ input người dùng.
3. Dùng IntegrationFlow Java DSL khai báo các **channelMapping** và **defaultOutputChannel("unmatchedOrdersChannel")**.
4. Tạo endpoint cho unmatched channel để ghi lại eventId, routing key, schemaVersion và lý do chưa hỗ trợ.
5. Viết test để đảm bảo **order.returned** đi vào unmatched, **order.created** chỉ đi vào orderCreatedChannel.
6. Tạo thêm phiên bản strict không có default route, tắt channelKeyFallback, rồi xác minh unknown key gây lỗi.
7. Thử thay một destination DirectChannel thành QueueChannel nhưng **không** cấu hình poller; mô tả cách theo dõi backlog thay vì kết luận rằng routing đã thất bại.
8. Đề xuất giải pháp lưu bền và replay khi consumer mới hỗ trợ order.returned; yêu cầu consumer idempotent.

### Mở rộng: chọn default hay fail fast?

Cho từng sự kiện sau, hãy đưa ra một **quyết định và lý do**:

| Tình huống | Một chính sách hợp lý |
| --- | --- |
| Dịch vụ thanh toán nhận eventType chưa có trong hợp đồng | Fail fast, cảnh báo hoặc quarantine bền |
| Bộ thu analytics gặp sự kiện mới nhưng có chính sách chỉ ghi ba loại | Drop có metrics hoặc quarantine theo yêu cầu |
| Router đã map COMPLETED nhưng thiếu completedPaymentsChannel | Fail fast để sửa cấu hình |
| Consumer chậm khiến QueueChannel đầy | Backpressure, timeout, giới hạn retry và theo dõi tải |
| Email notification có lỗi mạng tạm thời | Retry cục bộ có backoff, không retry toàn tuyến nếu gây duplicate |

Các lựa chọn không có câu trả lời đúng duy nhất; chúng phải xuất phát từ mức độ quan trọng của dữ liệu, nghĩa vụ lưu trữ, khả năng replay và tác động của việc xử lý trùng.

### Câu hỏi tự kiểm tra

1. Default output channel được dùng ở bước nào của router?
2. Vì sao một channel có tên hợp lệ vẫn có thể là dead-end route?
3. Khi nào dùng nullChannel là hợp lý, khi nào là nguy hiểm?
4. channelKeyFallback khác resolutionRequired như thế nào?
5. Trong Spring Integration 6+, đặt default output channel tác động đến channelKeyFallback ra sao?
6. Vì sao mapped channel không tồn tại không nên được coi là unknown eventType?
7. Retry message thiếu routing key có giải quyết vấn đề không?
8. Nếu QueueChannel đã nhận message nhưng consumer không hoạt động thì giám sát tín hiệu gì?
9. Vì sao replay từ quarantine có thể cần idempotency?

## 14. Checklist trước khi phát hành Content-Based Router

- Danh sách routing key hợp lệ và mapping được mô tả/kiểm thử.
- Mỗi route có channel tồn tại và downstream handler/poller tương ứng.
- Phân biệt key mới chưa được hỗ trợ với lỗi sai bean/channel trong cấu hình.
- Chọn rõ một trong ba chính sách **fail fast, quarantine, discard**.
- Default output channel có consumer hoặc cơ chế lưu/quan sát phù hợp.
- Chỉ dùng nullChannel khi việc bỏ qua message được chấp nhận công khai trong hợp đồng.
- Kiểm soát channelKeyFallback và resolutionRequired theo phiên bản Spring Integration.
- Lỗi gửi/handler async được xử lý bằng error flow và retry phù hợp.
- Replay được bảo vệ bởi eventId ổn định và consumer idempotent.
- Có metrics cho unmatched, resolution failures, downstream failures và queue backlog.
- Integration test có cả route đúng, route mặc định, route thiếu consumer và eventType không hợp lệ.

**Nguyên tắc thực hành:** Content-Based Router đưa ra **quyết định đường đi**, default route giải quyết **không có đích phù hợp**, còn dead-end route là tình trạng **message không còn tiến tới một bước xử lý hữu ích**. Định nghĩa rõ các trạng thái này giúp hệ thống Spring Integration phát hiện lỗi sớm, không vô tình đánh mất message quan trọng và giữ được khả năng quan sát các nhánh.

## Tài liệu tham khảo

- [Spring Integration Reference — Router Implementations](https://docs.spring.io/spring-integration/reference/router/implementations.html): Content-Based Router, router theo payload/header và Java DSL.
- [Spring Integration Reference — Common Router Parameters](https://docs.spring.io/spring-integration/reference/router/common-parameters.html): default output channel, resolution required, channel key fallback và send failures.
- [Spring Integration API — AbstractMappingMessageRouter](https://docs.spring.io/spring-integration/api/org/springframework/integration/router/AbstractMappingMessageRouter.html): channelKeyFallback và default channel ở các phiên bản hiện hành.
- [Spring Integration API — RouterSpec](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/dsl/RouterSpec.html): khai báo channelMapping và các lựa chọn mapping router.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, QueueChannel, ExecutorChannel và nullChannel.
