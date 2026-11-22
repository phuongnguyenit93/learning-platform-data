# Bảo vệ header khỏi dữ liệu người dùng không tin cậy

## 1. Bối cảnh và mục tiêu

Trong chương **Header-based router** của module **SPRING_INTEGRATION_PATTERN**, chúng ta triển khai Enterprise Integration Patterns với Spring Integration để tạo các luồng thông điệp ít phụ thuộc, dễ mở rộng. Khi Router, Filter, Transformer, Splitter, Aggregator và Gateway trao đổi message, các header có thể được sử dụng để định tuyến, phản hồi, xử lý lỗi, correlation và quan sát. Một header sai nguồn gốc có thể làm cả luồng rẽ sang nhánh ngoài dự kiến.

Ví dụ một API nhận đơn hàng:

- Đơn thông thường đi vào **standardOrdersChannel**.
- Đơn có tổng tiền cao đi vào **manualReviewChannel**.
- Channel đích được chọn từ header **trustedRoute**.

Nếu client bên ngoài tự gửi một header có cùng tên hoặc giá trị tương đương một **tên channel nội bộ**, rồi ứng dụng sao chép nó thẳng vào Spring Message, client có thể điều khiển đường đi của message ngoài ý định. Tương tự, header như **tenantId**, **role**, **replyChannel**, **errorChannel** hoặc **routingSlip** có thể gây hậu quả khi bị coi là thông tin đã được xác thực.

**Mục tiêu của bài:**

1. Xác định ranh giới tin cậy giữa HTTP request, message broker và các MessageChannel nội bộ.
2. Phân biệt **header do client cung cấp**, **header do adapter tạo** và **header do server xác minh/sinh ra**.
3. Xây dựng message mới theo **allowlist**; không sao chép nguyên các header từ nguồn không tin cậy.
4. Cấu hình HeaderValueRouter với channel mapping cố định và **channelKeyFallback(false)**.
5. Đánh giá các header nhạy cảm, việc lọc headers và quy tắc propagation giữa các endpoint.
6. Kiểm thử các tình huống giả mạo route, tenant, channel phản hồi, trace và các trường hợp không có mapping.

## 2. Message headers là metadata, không phải chứng cứ xác thực

Một Spring Message gồm **payload** và **MessageHeaders**:

~~~java
public interface Message<T> {
    T getPayload();
    MessageHeaders getHeaders();
}
~~~

**Header** chứa metadata phục vụ việc giao nhận và xử lý: tên sự kiện, ngữ cảnh tenant, correlation ID, đích reply hoặc thông tin lỗi. Spring Integration có thể dùng header làm input cho **HeaderValueRouter** hoặc các adapter. Metadata này hữu ích nhưng **bản thân sự tồn tại của header không chứng minh giá trị đó đáng tin**.

| Header hoặc nhóm header | Vai trò thường gặp | Rủi ro nếu tin dữ liệu bên ngoài |
| --- | --- | --- |
| **route**, **eventType**, **trustedRoute** | Chọn nhánh xử lý | Người gửi chọn đường nhạy cảm hoặc né bước kiểm tra |
| **tenantId**, **organizationId** | Xác định phạm vi dữ liệu | Chuyển message sang tenant khác |
| **role**, **isAdmin**, **approvalGranted** | Gợi ý quyền nghiệp vụ | Giả mạo quyền phê duyệt |
| **replyChannel** | Đường nhận phản hồi request/reply | Chuyển phản hồi đến channel không mong muốn |
| **errorChannel** | Đường xử lý một số lỗi messaging | Làm sai lệch hoặc che khuất đường quan sát lỗi |
| **routingSlip** | Chỉ dẫn các chặng tích hợp tiếp theo | Thêm chặng ngoài topology được phép |
| **priority** | Thứ tự ưu tiên nếu channel có hỗ trợ | Lạm dụng hàng đợi ưu tiên |
| **correlationId** | Nhóm message liên quan | Trộn nhóm Aggregator, làm khó đối soát |
| **traceId**, **clientRequestId** | Liên kết log và trace | Chèn giá trị giả, quá dài hoặc nhạy cảm vào log |
| **id**, **timestamp** | Metadata được Spring Messaging quản lý | Nhầm với định danh nghiệp vụ hoặc cố gắng thay metadata framework |

**MessageHeaders bất biến về cấu trúc** sau khi tạo, nhưng điều đó không đảm bảo **giá trị ban đầu đáng tin**. Nếu một message được xây dựng từ headers giả mạo, việc nó bất biến chỉ khiến các giá trị giả mạo tiếp tục tồn tại. Ngoài ra payload hoặc giá trị header là đối tượng mutable vẫn có thể thay đổi thông qua tham chiếu chia sẻ.

## 3. Mô hình đe dọa: client điều khiển được gì?

Nguồn bên ngoài có thể kiểm soát:

1. **HTTP request headers** và query/body fields mà API cho phép gửi.
2. **AMQP/Kafka/JMS message headers hoặc properties**, tùy adapter và quyền producer.
3. **JSON field đặt tên giống metadata**, ví dụ một trường route, role hoặc tenantId trong payload.
4. **Giá trị bất thường**: null, chuỗi dài, Unicode, ký tự xuống dòng, kiểu dữ liệu khác dự kiến.
5. **Thông điệp lặp hoặc cố tình làm sai thứ tự**, kể cả khi toàn bộ header đều có kiểu hợp lệ.

Không phải mọi HTTP header đều tự động trở thành Spring Message header; việc chuyển đổi phụ thuộc **HTTP inbound adapter/gateway**, header mapper và cấu hình. Tương tự, adapter broker có quy tắc ánh xạ và serialize riêng. Vì vậy cần kiểm tra **nơi dữ liệu đi vào** flow, thay vì suy đoán mọi header đã được framework lọc sẵn.

~~~mermaid
flowchart LR
    C["External client<br/>body + HTTP headers"] --> A["HTTP adapter / controller"]
    A --> B["Trust boundary<br/>authenticate + validate"]
    B --> M["Tạo Message mới<br/>chỉ header đã duyệt"]
    M --> R["HeaderValueRouter<br/>allowlist mapping"]
    R --> S["Standard orders"]
    R --> V["Manual review"]
    R --> Q["Unroutable / cảnh báo"]
~~~

**Ranh giới tin cậy** là điểm ứng dụng xác nhận danh tính, quyền và tính hợp lệ dữ liệu, rồi tự quyết định metadata nội bộ. Một message được đẩy qua DirectChannel không tự được tin cậy chỉ vì nó đang nằm trong ApplicationContext. Nếu mọi bean nội bộ đều có thể gửi vào một channel quan trọng, hệ thống phải tổ chức quyền truy cập hoặc kiểm tra ở điểm nhận để không bỏ qua bước xác thực.

### 3.1. Ví dụ giả mạo đường đi

Giả sử client được phép gửi:

~~~json
{
  "orderId": "ORD-107",
  "totalVnd": 250000,
  "route": "manualReviewChannel",
  "tenantId": "tenant-other",
  "approvalGranted": true
}
~~~

Các thuộc tính route, tenantId và approvalGranted do client cung cấp **không có quyền** trở thành quyết định của router, trừ khi ứng dụng đã xác minh và công nhận chúng theo hợp đồng. Với đơn chỉ 250.000 VND, route nội bộ được tính từ policy server có thể phải là **STANDARD**.

**Ví dụ sai** nếu message đầu vào có headers do client kiểm soát:

~~~java
// Không dùng cách này trên ranh giới nguồn chưa tin cậy:
Message<OrderReceived> dangerous = MessageBuilder
        .withPayload(order)
        .copyHeaders(untrustedHeaders)
        .setHeaderIfAbsent("trustedRoute", "STANDARD")
        .build();
~~~

Hai vấn đề:

- **copyHeaders** mang tất cả header mà client gửi, kể cả tên giống header điều khiển nội bộ.
- **setHeaderIfAbsent** không ghi đè khi client đã đặt trustedRoute. Giá trị giả mạo có thể tiếp tục được dùng.

Đơn giản đổi setHeaderIfAbsent thành setHeader vẫn không đủ khi các header nguy hiểm khác được sao chép. Cần **xác định trước danh sách header được phép**, chỉ tạo những trường được server chịu trách nhiệm và xét riêng việc giữ metadata bên ngoài để quan sát.

## 4. Quy tắc thiết kế: header có chủ sở hữu

Một cách quản lý dễ kiểm thử là phân nhóm header theo **nguồn có quyền tạo/cập nhật**:

| Nhóm | Ai có quyền cung cấp/ghi? | Quy tắc |
| --- | --- | --- |
| **Business payload** | Client có thể đề xuất, server phải validate | Dữ liệu nghiệp vụ trong DTO/record |
| **Client diagnostic metadata** | Client cung cấp | Chỉ copy trường allowlist, validate định dạng/độ dài, không dùng để phân quyền |
| **Identity/tenant/role** | Thành phần xác thực hoặc policy server | Xây dựng từ verified principal/tenant context |
| **Routing decision** | Policy nội bộ có test | Tính từ payload đã validate và ngữ cảnh đáng tin |
| **Reply/error destination** | Cấu hình gateway/adapter/endpoint đáng tin | Không nhận tùy ý từ client |
| **Correlation/sequence** | Thành phần orchestration được giao trách nhiệm | Tránh client ép groupId/sequence để làm sai Aggregator |
| **Framework metadata** | Spring Messaging | Để framework quản lý id/timestamp |

### 4.1. Ingress không phải chỗ copy nguyên message

Tại ranh giới client → ứng dụng, tạo một **Message mới từ payload đã validate**. Chỉ thêm các header được server tính hoặc xác minh. Đừng sao chép mọi header rồi cố gắng xóa một vài tên bị cấm: denylist có thể bỏ sót tên mới của adapter hoặc tên tùy chỉnh xuất hiện trong tương lai.

### 4.2. Có thể giữ clientRequestId nhưng phải giới hạn

Một requestId do client đưa lên có thể hữu ích cho hỗ trợ khách hàng, nhưng chỉ để **tra cứu**:

- Giới hạn tập ký tự và độ dài; ví dụ 1–64 ký tự ASCII chữ, số, gạch dưới, gạch nối.
- Không dùng nó như token xác thực, routing key có đặc quyền hoặc idempotency key duy nhất khi chưa có cơ chế kiểm tra.
- Phân biệt **clientRequestId** với **serverEventId** được tạo tại server.
- Tránh đưa giá trị không kiểm soát vào metric label hoặc log có thể bị chèn ký tự điều khiển.

## 5. Ví dụ Java: tạo message sạch tại ranh giới tin cậy

Giả sử API tiếp nhận một đơn hàng. Một thành phần xác thực đã tạo **VerifiedActor** chứa userId và tenantId có thể tin cậy; actor này là kết quả xác minh server, **không được dựng trực tiếp từ body/header do client truyền vào**.

### 5.1. Payload và ngữ cảnh xác thực

~~~java
import java.math.BigDecimal;

record OrderReceived(String orderId, BigDecimal totalVnd) {}

record VerifiedActor(String userId, String tenantId) {}
~~~

Ví dụ factory tạo message mới với allowlist metadata:

~~~java
import java.math.BigDecimal;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class TrustedOrderMessageFactory {
    private static final BigDecimal REVIEW_THRESHOLD =
            new BigDecimal("10000000");

    private TrustedOrderMessageFactory() {}

    static Message<OrderReceived> create(
            OrderReceived order,
            VerifiedActor actor,
            Map<String, ?> externalHeaders) {

        Objects.requireNonNull(actor, "Verified actor required");
        Objects.requireNonNull(externalHeaders, "Headers required");
        if (actor.userId() == null || actor.userId().isBlank()
                || actor.tenantId() == null || actor.tenantId().isBlank()) {
            throw new IllegalArgumentException("Actor chưa được xác minh");
        }
        if (order == null || order.orderId() == null
                || !order.orderId().matches("[A-Za-z0-9-]{1,40}")
                || order.totalVnd() == null
                || order.totalVnd().signum() <= 0) {
            throw new IllegalArgumentException("Đơn hàng không hợp lệ");
        }

        String route = order.totalVnd().compareTo(REVIEW_THRESHOLD) >= 0
                ? "REVIEW" : "STANDARD";

        MessageBuilder<OrderReceived> builder =
                MessageBuilder.withPayload(order)
                        .setHeader("trustedRoute", route)
                        .setHeader("trustedTenant", actor.tenantId())
                        .setHeader("authenticatedUserId", actor.userId())
                        .setHeader("serverEventId", UUID.randomUUID().toString());

        // Chỉ một metadata phục vụ chẩn đoán được phép lấy từ client.
        Object candidate = externalHeaders.get("clientRequestId");
        if (candidate instanceof String value
                && value.matches("[A-Za-z0-9_-]{1,64}")) {
            builder.setHeader("clientRequestId", value);
        }

        // Cố ý không copy các giá trị client gửi như tenantId,
        // trustedRoute, replyChannel, errorChannel, routingSlip.
        return builder.build();
    }
}
~~~

Giải thích:

1. **OrderReceived** chỉ chứa dữ liệu khách hàng có thể đề xuất, không chứa quyền điều phối.
2. **VerifiedActor** phải đến từ authentication/authorization logic của server. Việc đặt tên record là VerifiedActor tự nó không phải cơ chế bảo mật.
3. **trustedRoute** được quyết định bởi tổng tiền **đã validate** và policy server, không phải từ header route của client.
4. **trustedTenant** được gắn từ identity đã xác minh; không lấy trực tiếp giá trị tenantId do client khai.
5. **serverEventId** được tạo phía server. Với event có thể retry hoặc duplicate, hãy áp dụng cơ chế cấp phát eventId/idempotency ổn định phù hợp thay vì tạo UUID mới cho mọi lần gửi lại.
6. **clientRequestId** được chấp nhận chỉ khi hợp lệ và **không dùng cho phân quyền**; giá trị sai định dạng bị bỏ qua theo policy minh họa.

Factory trên là một **ví dụ về nguyên tắc**. Trong ứng dụng thật, xác thực cần dựa trên Spring Security hoặc cơ chế tin cậy tương ứng, kiểm tra quyền theo tenant, giới hạn request size, xác nhận policy review và đặt hạn mức cho dữ liệu được lưu/log. Nên kiểm thử cả đường bỏ qua factory nếu có nhiều producer nội bộ.

### 5.2. Khi dùng MessageBuilder.fromMessage

Phương thức **fromMessage(existing)** phù hợp để tạo message dẫn xuất **trong một vùng đã tin cậy**; nó bắt đầu từ payload/headers của message cũ. Nếu existing là message từ một nguồn không tin cậy, dùng fromMessage có thể **giữ lại header nguy hiểm**.

~~~java
// Chỉ dùng khi incoming đã qua điểm xác thực và chuẩn hóa.
Message<OrderReceived> checked = MessageBuilder.fromMessage(trustedMessage)
        .setHeader("validated", true)
        .build();
~~~

Nếu một Transformer hoặc adapter tự động truyền tiếp headers từ input, hãy kiểm tra quy tắc **header propagation** của endpoint. Việc một bước trả về payload hoặc Message mới không phải lúc nào cũng có nghĩa tất cả headers cũ đã biến mất. Để tạo ranh giới an toàn, hãy thiết kế rõ điểm tạo lại message và kiểm tra đầu ra thực tế bằng integration test.

## 6. Khóa router bằng channel mapping cố định

Trong Spring Integration, **HeaderValueRouter** đọc một header được chỉ định. Giá trị header có thể là một key nghiệp vụ hoặc tên channel. Cách thứ hai rất linh hoạt nhưng **không phù hợp với nguồn không tin cậy**: nếu routing key được dùng trực tiếp làm tên channel, người gửi có thể khiến ứng dụng tìm một bean channel ngoài dự kiến.

Để giảm nguy cơ này, nên kết hợp:

- **Header nội bộ** do server tạo, ví dụ trustedRoute.
- **Mapping cố định** từ giá trị nghiệp vụ STANDARD/REVIEW sang tên channel.
- **channelKeyFallback(false)** để không dùng key không map như tên channel.
- **Default output channel** để xử lý key chưa nhận diện mà không chuyển đi ngẫu nhiên.
- **Không mở đường trực tiếp từ network hoặc broker chưa tin cậy tới trustedIngressChannel**.

### 6.1. Cấu hình HeaderValueRouter

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.router.HeaderValueRouter;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class SecureHeaderRoutingConfig {

    @Bean
    MessageChannel trustedIngressChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel standardOrdersChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel manualReviewChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel unroutableOrdersChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow securedOrderRoutingFlow() {
        HeaderValueRouter router = new HeaderValueRouter("trustedRoute");
        router.setChannelMapping("STANDARD", "standardOrdersChannel");
        router.setChannelMapping("REVIEW", "manualReviewChannel");
        router.setDefaultOutputChannelName("unroutableOrdersChannel");
        router.setChannelKeyFallback(false);

        return IntegrationFlow.from("trustedIngressChannel")
                .route(router)
                .get();
    }
}
~~~

**Quy tắc định tuyến**

| Giá trị trustedRoute | Destination |
| --- | --- |
| STANDARD | standardOrdersChannel |
| REVIEW | manualReviewChannel |
| Giá trị chưa map hoặc null | unroutableOrdersChannel, theo fallback |

Các channel phải có subscriber/endpoint thực sự nhận message. Có thể gắn Service Activator cho mỗi nhánh; nhánh unroutable nên ghi nhận metadata an toàn, phát cảnh báo hoặc quarantine khi lỗi nội bộ cần điều tra. Không tự coi việc rơi vào fallback là **đã xử lý nghiệp vụ thành công**.

Ví dụ port nghiệp vụ để bảo đảm mỗi nhánh chỉ thực hiện trách nhiệm riêng:

~~~java
interface StandardOrderPort {
    void accept(OrderReceived order);
}

interface ManualReviewPort {
    void review(OrderReceived order);
}

interface UnroutableOrderPort {
    void quarantine(OrderReceived order);
}
~~~

### 6.2. Producer được phép gửi vào trustedIngressChannel

~~~java
import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.stereotype.Service;

@Service
class OrderIngressService {
    private final MessageChannel trustedIngress;

    OrderIngressService(
            @Qualifier("trustedIngressChannel") MessageChannel trustedIngress) {
        this.trustedIngress = trustedIngress;
    }

    void accept(
            OrderReceived request,
            VerifiedActor verifiedActor,
            Map<String, ?> externalHeaders) {
        Message<OrderReceived> safeMessage =
                TrustedOrderMessageFactory.create(
                        request, verifiedActor, externalHeaders);

        if (!trustedIngress.send(safeMessage)) {
            throw new IllegalStateException("Channel từ chối message");
        }
    }
}
~~~

**Quan trọng:** đây là service minh họa sau khi authentication/authorization đã chạy. Một REST controller phải lấy verifiedActor từ security context, không gọi new VerifiedActor với userId/tenantId trong request body. Nếu các producer khác có thể gửi trực tiếp message vào trustedIngressChannel, cần áp dụng cùng quy tắc xác thực tại những entrypoint đó hoặc thêm lớp kiểm tra thích hợp. **Tên header trustedRoute không tự tạo ra niềm tin**.

### 6.3. Vì sao channelKeyFallback phải tắt?

Theo API của **AbstractMappingMessageRouter**, khi **channelKeyFallback=true**, key không có trong mapping có thể được dùng làm **tên channel để resolve**. Đây là hành vi tiện lợi cho ứng dụng hoàn toàn tin cậy nội bộ, nhưng nguy hiểm nếu dữ liệu bên ngoài ảnh hưởng trực tiếp đến key.

Ví dụ message có:

~~~text
trustedRoute = internalAdminChannel
~~~

Nếu key không map nhưng router được phép giải quyết trực tiếp theo tên, một channel trùng tên có thể bị chọn ngoài allowlist. Trường hợp key trỏ ngược về upstream router còn có thể gây vòng lặp đồng bộ.

Với **channelKeyFallback(false)**, key **internalAdminChannel** không có trong allowlist STANDARD/REVIEW và sẽ đi theo đường fallback hoặc phát lỗi, tùy cấu hình. Từ **Spring Integration 6.0**, đặt default output channel còn tự tắt channelKeyFallback theo mặc định; vẫn có thể cấu hình tường minh false để thể hiện hợp đồng bảo mật và tránh thay đổi ngoài ý muốn.

**resolutionRequired** là tùy chọn khác: nó quyết định có cho phép bỏ qua một **channel name đã xác định nhưng không resolve được** hay không. Với cấu hình định tuyến nhạy cảm, thường giữ **resolutionRequired=true** để sai tên channel không bị che khuất. Default route không thay thế sửa wiring.

### 6.4. HeaderValueRouter khác kiểm tra quyền

Router không biết liệu một verifiedActor có được phép phê duyệt hay xuất dữ liệu của tenant khác hay không. Ngay cả khi header được sinh từ một bước server có xác thực, downstream vẫn cần kiểm tra các điều kiện phân quyền nghiệp vụ quan trọng.

Ví dụ một đơn tổng tiền cao đi nhánh manual review không có nghĩa caller được quyền **bỏ qua review** hoặc **phê duyệt** đơn. Bước phê duyệt phải xác thực người thao tác, quyền, tenant và trạng thái đơn tại thời điểm thực hiện.

## 7. Dùng Header Filter và Header Enricher đúng vị trí

Spring Integration cung cấp **Header Filter** để xóa một số tên header trước bước tiếp theo, và **Header Enricher** để bổ sung headers. Chúng hữu ích để dọn metadata khi một message chuyển sang miền khác:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
IntegrationFlow removeTemporaryHeaderFlow() {
    return IntegrationFlow.from("validatedMessageChannel")
            .headerFilter("debugOnly", "temporaryRouteHint", "externalNote")
            .channel("nextProcessingChannel")
            .get();
}
~~~

Ví dụ trên cần khai báo validatedMessageChannel và nextProcessingChannel. Header Filter loại **những tên đã nêu**, không phải cơ chế tự động lọc tất cả trường có thể nguy hiểm. Nếu API có nguồn không tin cậy, **lọc theo denylist không thay thế được việc tạo lại message theo allowlist tại ingress**.

Header Enricher có thể gắn metadata do server tính:

~~~java
@Bean
IntegrationFlow addVerifiedSourceFlow() {
    return IntegrationFlow.from("internalVerifiedChannel")
            .enrichHeaders(h -> h.header(
                    "sourceSystem", "trusted-order-api"))
            .channel("normalizedEventsChannel")
            .get();
}
~~~

Trong hệ thống thật, đừng hiểu việc đặt tên header là “verified” đồng nghĩa người tạo message đã xác thực. Cần xác định **ai được phép gọi endpoint làm giàu** và **giá trị được lấy từ đâu**.

### 7.1. Không xóa vô tội vạ các header do framework sử dụng

Các header **replyChannel**, **errorChannel**, **correlationId**, **sequenceNumber**, **sequenceSize** có thể cần thiết cho Gateway, Splitter, Aggregator hoặc error flow. Xóa chúng giữa một flow đã xác thực có thể khiến:

- Gateway không tìm được đường gửi reply hoặc bị timeout;
- error handling gửi lỗi sai nơi;
- Aggregator không ghép đủ các message con.

Do đó, biện pháp tốt nhất là **ngăn nguồn không tin cậy tạo ra header điều khiển**, rồi bảo toàn metadata được framework hoặc component đáng tin quản lý ở những chặng cần thiết. Header Filter chỉ nên dùng khi biết rõ header nào đã hết vòng đời.

### 7.2. HTTP và broker header mapper

Các adapter có thể ánh xạ header từ HTTP, JMS, AMQP hoặc Kafka sang Spring Message headers. Quy tắc cụ thể phụ thuộc adapter, cấu hình inbound/outbound mapper và phiên bản framework. Nếu ứng dụng chỉ cần một vài header chẩn đoán, hãy:

1. Cấu hình mapping theo **allowlist** ở adapter nếu adapter hỗ trợ.
2. Kiểm tra kiểu, độ dài và định dạng của header được chấp nhận.
3. Tách **header bên ngoài** khỏi **header nội bộ** bằng tên và trách nhiệm rõ ràng.
4. Tạo lại message tại ranh giới xác thực trước khi đưa vào các channel nhạy cảm.
5. Kiểm thử adapter thật để phát hiện trường hợp mapped header trùng tên header nội bộ.

Không nên tin rằng một tên bắt đầu bằng **X-** hay một chuỗi được đưa vào HTTP Authorization header tự động là chứng cứ xác thực. Sự tin cậy đến từ **quá trình kiểm chứng**, không đến từ tên trường.

## 8. Những đường tấn công thường gặp và biện pháp

| Tình huống | Rủi ro | Biện pháp chính |
| --- | --- | --- |
| Client tự gửi trustedRoute=MANUAL_REVIEW | Điều khiển routing trái policy | Server tính route, mapping allowlist |
| Client gửi route bằng tên channel tùy ý | Resolve bean/channel ngoài dự kiến | channelKeyFallback(false) |
| Client gửi tenantId của tổ chức khác | Truy cập sai tenant | Lấy tenant từ verified principal, kiểm tra quyền ở consumer |
| Client gửi role=ADMIN | Leo thang đặc quyền | Không coi header là authority |
| Client gửi replyChannel do mình đặt | Có thể làm sai đường trả lời | Gateway/endpoint tin cậy sở hữu reply destination |
| Client gửi errorChannel bất thường | Gây sai đường báo lỗi | Quản lý error flow qua config và trusted headers |
| Client điều khiển routingSlip | Điều hướng qua chặng bất ngờ | Không nhận routingSlip tùy ý tại ingress |
| Client đặt correlationId trùng nhóm khác | Trộn group hoặc làm sai Aggregator | Orchestrator tạo group key từ dữ liệu kiểm chứng |
| Client đặt priority rất cao | Chiếm tài nguyên ở PriorityChannel | Kiểm tra quyền và policy ưu tiên |
| Header chứa CR/LF hoặc giá trị dài bất thường | Log injection, tăng tài nguyên | Validate định dạng, giới hạn kích thước, escape log |
| Chuyển qua Transformer rồi vô tình giữ headers | Header giả mạo tồn tại ở downstream | Kiểm tra propagation và test output từng endpoint |
| Bỏ qua factory, gửi trực tiếp vào channel nội bộ | Bypass bước xác thực | Bảo vệ/kiểm soát ingress, test tất cả producer |

**Ngăn chặn nhiều lớp** là hợp lý: kiểm soát input, xác thực identity, tạo metadata tin cậy, mapping allowlist, kiểm tra quyền ở consumer và monitoring. Không biện pháp đơn lẻ nào thay thế toàn bộ những bước còn lại.

## 9. Khi routing key không hợp lệ: fallback, fail fast và quarantine

Ngay cả với dữ liệu được server tạo, vẫn có thể có lỗi logic, phiên bản hoặc cấu hình: ví dụ policy server trả về REVIEW_FAST nhưng router chỉ cho STANDARD và REVIEW.

~~~mermaid
flowchart TD
    M["Message có trustedRoute"] --> R{"HeaderValueRouter"}
    R -->|"STANDARD"| A["Standard handler"]
    R -->|"REVIEW"| B["Manual review handler"]
    R -->|"Giá trị chưa map"| F["Unroutable channel"]
    F --> Q["Lưu nguyên nhân, cảnh báo, điều tra"]
~~~

**Ba chính sách thường dùng:**

1. **Fail fast:** không có default channel, router báo lỗi nếu không resolve được đích. Thích hợp khi mọi key đều phải nằm trong hợp đồng đóng.
2. **Quarantine:** default output channel nhận các message chưa map để điều tra. Nếu cần phục hồi sau restart, endpoint phải ghi bền message và metadata.
3. **Discard có chủ đích:** default đến nullChannel khi ứng dụng thật sự cho phép bỏ message. Với nghiệp vụ thanh toán, phê duyệt hoặc kiểm toán thường không nên bỏ im lặng.

**Default output channel không cứu mọi lỗi.** Nếu router đã chọn một DirectChannel nhưng không có subscriber, hoặc handler downstream ném exception, đó là lỗi dispatch/processing. Với QueueChannel, send có thể thành công dù consumer chưa xử lý. Từng tình huống cần error flow, retry và metrics riêng.

Không lặp vô hạn một message chưa có mapping: retry không làm policy mới xuất hiện. Hãy tách **unknown key** khỏi **lỗi hệ thống tạm thời**.

## 10. Header tin cậy trong Router, Filter, Transformer, Splitter và Aggregator

Trong một pipeline hoàn chỉnh, bảo vệ headers cần đi cùng các pattern khác:

| Pattern | Cách headers có thể ảnh hưởng | Nguyên tắc bảo vệ |
| --- | --- | --- |
| **Router** | eventType, routeCode quyết định channel | Chỉ dùng key đã chuẩn hóa và mapping tường minh |
| **Filter** | tenantId, priority, featureFlag quyết định chấp nhận | Không xem client header là bằng chứng quyền |
| **Transformer** | Có thể copy/propagate headers đầu vào | Dọn metadata hết hiệu lực, kiểm tra output |
| **Splitter** | Tạo message con, gắn correlation/sequence | Để component tin cậy quản lý grouping |
| **Aggregator** | Ghép nhóm dựa trên correlation và release strategy | Chặn group key giả, giới hạn message store |
| **Gateway** | replyChannel, errorChannel và request/reply | Chỉ cho gateway tin cậy quản lý reply/error routing |
| **Retry** | Đường lỗi có thể gửi lại message | Event ID ổn định, idempotent consumer |
| **Observability** | traceId, correlationId xuất hiện trong log/metric | Phân biệt giá trị client cung cấp và trace server xác thực |

### 10.1. Không nhầm correlation ID với định danh/ủy quyền

Một correlationId như ORD-107 chỉ dùng để nhóm hoặc lần theo message; nó không tự chứng minh người gửi sở hữu ORD-107. Nếu consumer dựa vào correlationId để tải dữ liệu, vẫn phải kiểm tra tenant và quyền.

Với Splitter/Aggregator, việc cho người ngoài tùy ý chọn correlationId hoặc sequenceSize có thể làm sai grouping, tăng số nhóm chờ hoặc tạo áp lực lên MessageStore. Một bước đáng tin phải tạo/kiểm chứng nhóm trước khi Aggregator xử lý.

### 10.2. Header không đủ làm chữ ký nguồn gửi

Gắn một header như verified=true, internal=true hoặc sourceSystem=trusted-api **không phải bằng chứng mật mã**. Nếu message đi qua broker có nhiều producer hoặc một hệ thống không tin cậy, cần cơ chế xác thực producer, kiểm soát truy cập topic/queue, kênh truyền được bảo vệ và nếu cần, kiểm tra chữ ký hoặc một giao thức bảo đảm tính toàn vẹn của dữ liệu.

Ngược lại, một hệ thống nội bộ được kiểm soát không nhất thiết phải ký từng header. Mức bảo vệ phụ thuộc mô hình đe dọa và ranh giới triển khai.

## 11. Kiểm thử: dữ liệu giả mạo không ảnh hưởng quyết định của server

Một bài kiểm thử chỉ chứng minh HeaderValueRouter đọc được header chưa đủ cho yêu cầu bảo mật. Cần kiểm tra **đường đi trọn vẹn**: input từ client → điểm xác thực/chuẩn hóa → message được tạo → router → đúng destination.

### 11.1. Unit test factory tạo message sạch

Ví dụ dùng JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;

class TrustedOrderMessageFactoryTest {

    @Test
    void untrustedHeadersCannotOverrideRouteTenantOrReplyChannel() {
        OrderReceived order = new OrderReceived(
                "ORD-107", new BigDecimal("250000"));
        VerifiedActor actor = new VerifiedActor(
                "user-42", "tenant-A");

        Map<String, Object> clientHeaders = Map.of(
                "trustedRoute", "manualReviewChannel",
                "trustedTenant", "tenant-victim",
                "replyChannel", "privilegedOpsChannel",
                "errorChannel", "privilegedOpsChannel",
                "routingSlip", "privilegedOpsChannel",
                "clientRequestId", "REQ_107");

        Message<OrderReceived> result =
                TrustedOrderMessageFactory.create(
                        order, actor, clientHeaders);

        assertEquals("STANDARD",
                result.getHeaders().get("trustedRoute"));
        assertEquals("tenant-A",
                result.getHeaders().get("trustedTenant"));
        assertEquals("user-42",
                result.getHeaders().get("authenticatedUserId"));
        assertEquals("REQ_107",
                result.getHeaders().get("clientRequestId"));
        assertNotNull(result.getHeaders().get("serverEventId"));

        assertNull(result.getHeaders().get("replyChannel"));
        assertNull(result.getHeaders().get("errorChannel"));
        assertNull(result.getHeaders().get("routingSlip"));
    }

    @Test
    void highValueOrderUsesReviewPolicyRegardlessOfClientHint() {
        OrderReceived order = new OrderReceived(
                "ORD-108", new BigDecimal("12000000"));

        Message<OrderReceived> result =
                TrustedOrderMessageFactory.create(
                        order,
                        new VerifiedActor("user-42", "tenant-A"),
                        Map.of("trustedRoute", "STANDARD"));

        assertEquals("REVIEW",
                result.getHeaders().get("trustedRoute"));
    }

    @Test
    void invalidOrderIsRejectedBeforeRouting() {
        assertThrows(IllegalArgumentException.class,
                () -> TrustedOrderMessageFactory.create(
                        new OrderReceived("", BigDecimal.ZERO),
                        new VerifiedActor("user-42", "tenant-A"),
                        Map.of("trustedRoute", "REVIEW")));
    }

    @Test
    void malformedDiagnosticHeaderIsNotPropagated() {
        Message<OrderReceived> result =
                TrustedOrderMessageFactory.create(
                        new OrderReceived(
                                "ORD-109", new BigDecimal("500000")),
                        new VerifiedActor("user-42", "tenant-A"),
                        Map.of("clientRequestId", "bad\nvalue"));

        assertNull(result.getHeaders().get("clientRequestId"));
    }
}
~~~

Unit test chứng minh header giả mạo không được giữ lại và quyết định định tuyến xuất phát từ policy server. Nó **không** tự chứng minh API đã lấy VerifiedActor từ nguồn đáng tin; cần kiểm thử tầng authentication/inbound adapter riêng.

### 11.2. Integration test: key lạ không biến thành tên channel

Test này cố ý gửi một message trực tiếp vào **trustedIngressChannel** với key bằng tên một channel nội bộ khác để kiểm tra hàng rào thứ hai: **channelKeyFallback=false**. Nó minh họa tính an toàn của cấu hình router ngay cả khi một producer nội bộ bị lỗi hoặc bỏ qua factory.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.router.HeaderValueRouter;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(HeaderRoutingIsolationTest.TestConfig.class)
class HeaderRoutingIsolationTest {

    @Configuration
    @EnableIntegration
    static class TestConfig {
        @Bean
        MessageChannel trustedIngressChannel() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel standardOrdersChannel() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel manualReviewChannel() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel unroutableOrdersChannel() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel privilegedOpsChannel() {
            return new DirectChannel();
        }

        @Bean
        IntegrationFlow routingFlow() {
            HeaderValueRouter router =
                    new HeaderValueRouter("trustedRoute");
            router.setChannelMapping(
                    "STANDARD", "standardOrdersChannel");
            router.setChannelMapping(
                    "REVIEW", "manualReviewChannel");
            router.setDefaultOutputChannelName(
                    "unroutableOrdersChannel");
            router.setChannelKeyFallback(false);
            return IntegrationFlow.from("trustedIngressChannel")
                    .route(router)
                    .get();
        }
    }

    @Autowired
    @Qualifier("trustedIngressChannel")
    MessageChannel input;

    @Autowired
    @Qualifier("unroutableOrdersChannel")
    SubscribableChannel unroutable;

    @Autowired
    @Qualifier("privilegedOpsChannel")
    SubscribableChannel privileged;

    @Test
    void arbitraryChannelNameCannotEscapeTheAllowlist() {
        List<String> received = new ArrayList<>();
        MessageHandler fallbackHandler =
                message -> received.add("unroutable");
        MessageHandler privilegedHandler =
                message -> received.add("privileged");

        unroutable.subscribe(fallbackHandler);
        privileged.subscribe(privilegedHandler);
        try {
            assertTrue(input.send(
                    MessageBuilder.withPayload("probe")
                            .setHeader(
                                    "trustedRoute",
                                    "privilegedOpsChannel")
                            .build()));

            assertEquals(List.of("unroutable"), received);
        } finally {
            unroutable.unsubscribe(fallbackHandler);
            privileged.unsubscribe(privilegedHandler);
        }
    }
}
~~~

Test đặt sẵn bean **privilegedOpsChannel** để bảo đảm key chưa map **không được resolve trực tiếp** thành channel đó. Khi dùng DirectChannel đồng bộ, có thể kiểm tra kết quả ngay sau send(). Nếu chuyển một destination sang ExecutorChannel hoặc QueueChannel, test phải chờ và kiểm tra kết quả theo semantics async.

### 11.3. Ma trận kiểm thử bảo mật nên có

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Client tự đặt trustedRoute=REVIEW cho đơn nhỏ | Route server vẫn là STANDARD |
| Client tự đặt trustedRoute=STANDARD cho đơn lớn | Route server vẫn là REVIEW |
| Client giả mạo trustedTenant của tenant khác | Header nội bộ giữ tenant từ verified identity |
| Client gửi replyChannel/errorChannel/routingSlip | Không được copy nguyên vào message nội bộ |
| Key chưa map trùng tên một channel khác | Đi fallback hoặc báo lỗi, không đi channel ngoài allowlist |
| Thiếu/malformed clientRequestId | Không làm thay đổi auth hay routing |
| Client gửi payload thiếu dữ liệu hoặc sai kiểu | Bị từ chối trước router theo validation policy |
| HTTP adapter map header trùng tên route | Ranh giới ingress loại hoặc tạo lại header đúng |
| Có producer nội bộ bỏ qua ingress factory | Bị ngăn theo cơ chế kiểm soát/kiểm tra đầu vào nội bộ |
| Gateway request/reply có header do framework tạo | Reply/error path vẫn hoạt động sau khi chuẩn hóa |
| Message sang Splitter/Aggregator | Correlation/sequence chỉ đến từ thành phần đáng tin |
| Retry cùng event sau lỗi | Không tạo tác động trùng nhờ eventId/idempotency policy |

### 11.4. Kiểm thử cả trường hợp hợp lệ

Bảo mật quá chặt có thể làm luồng bình thường bị hỏng. Ngoài negative test, cần xác minh:

- Đơn STANDARD đến đúng handler và được xử lý.
- Đơn REVIEW đến nhánh kiểm tra thủ công.
- ClientRequestId hợp lệ vẫn giúp tra cứu log nhưng không trở thành authority.
- Gateway xử lý request/reply vẫn có replyChannel đúng do framework quản lý.
- Correlation ID/sequence do Splitter phát ra vẫn tới Aggregator và giải phóng group đúng điều kiện.
- Router chỉ quyết định channel; Service Activator phía sau còn kiểm tra tenant, role và trạng thái nghiệp vụ trước thao tác nhạy cảm.

## 12. Quan sát và phản ứng khi phát hiện header bất thường

Các rủi ro giả mạo header có thể xảy ra mà ứng dụng không ném exception, nên nên đo một số tín hiệu:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| **invalid_external_header_count** | Input bị loại do sai định dạng hoặc độ dài |
| **routing_fallback_count** | Trusted route chưa map hoặc message đến fallback |
| **channel_resolution_failure_count** | Cấu hình route sai hoặc thiếu channel |
| **tenant_authorization_denied_count** | Consumer từ chối thao tác không đúng tenant |
| **unexpected_header_propagation_count** | Phát hiện header cấm xuất hiện phía sau trust boundary |
| **reply_or_error_route_failure_count** | Gateway hoặc error handler không tìm được đường trả |
| **event_replay_duplicate_count** | Event bị gửi/nhận lại nhưng đã xử lý trước đó |

Metric label nên dùng tên route và loại lỗi **có tập giá trị giới hạn**, không dùng trực tiếp userId, raw header hoặc eventId làm label. Log cần được escape và hạn chế dữ liệu nhạy cảm. Với nghi ngờ giả mạo, ghi dấu thời điểm, nguồn đã xác thực, loại policy bị vi phạm và correlation hợp lệ do server tạo để hỗ trợ điều tra.

Một cảnh báo về header sai **không tự chứng minh tấn công**: adapter có thể đang cấu hình nhầm hoặc consumer mới đưa header lạ. Điều tra dựa trên bằng chứng và kiểm tra đường mapping thực tế.

## 13. Bài thực hành: bảo vệ router cho hệ thống hoàn tiền

Thiết kế một flow nhận **RefundRequested(refundId, paymentId, amountVnd)**. Client có thể đề xuất yêu cầu hoàn tiền nhưng không có quyền tự lựa chọn người duyệt.

**Yêu cầu nghiệp vụ:**

1. Refund dưới 2 triệu và hợp lệ có thể đi nhánh kiểm tra chuẩn.
2. Refund từ 2 triệu trở lên cần kiểm tra tăng cường.
3. Mọi request cần liên kết với tenant và danh tính đã xác thực.
4. Không cho client chọn đích **manualApprovalChannel**, **adminOverrideChannel** hoặc replyChannel.
5. Header chỉ dùng cho diagnostic như clientRequestId phải có giới hạn định dạng/độ dài.
6. Router chỉ có mapping từ **STANDARD** và **ENHANCED_REVIEW** đến channel hợp lệ; key lạ phải đi quarantine hoặc báo lỗi.

**Các bước thực hiện:**

1. Xây dựng record RefundRequested và VerifiedActor; xác định ranh giới tạo VerifiedActor từ security context.
2. Viết RefundMessageFactory nhận payload/actor và một map headers chưa tin cậy; chỉ giữ clientRequestId hợp lệ.
3. Sinh header **trustedRefundRoute** từ amountVnd sau khi kiểm tra dữ liệu và quyền.
4. Khai báo HeaderValueRouter với hai channel mapping, channelKeyFallback(false) và default output channel.
5. Viết unit test client gửi trustedRefundRoute=adminOverrideChannel, fake tenantId, replyChannel và routingSlip; kiểm tra message nội bộ không giữ chúng.
6. Thêm integration test một key lạ trùng tên adminOverrideChannel, xác minh nó không rơi vào channel đó.
7. Mô phỏng nhánh xử lý async và kiểm tra error channel, retry, idempotency theo refundId/eventId.
8. Viết kịch bản kiểm thử Gateway nhận phản hồi mà không lấy replyChannel từ client.

### Câu hỏi tự kiểm tra

1. Vì sao MessageHeaders bất biến không đồng nghĩa header đáng tin?
2. Những dữ liệu bên ngoài nào có thể ảnh hưởng tới header của Spring Message?
3. Vì sao copyHeaders cộng setHeaderIfAbsent không an toàn tại trust boundary?
4. channelKeyFallback(true) có thể gây hệ quả gì khi routing key do client điều khiển?
5. channelKeyFallback và resolutionRequired khác nhau như thế nào?
6. Khi nào có thể giữ clientRequestId do client gửi?
7. Tại sao không nên tự xóa replyChannel giữa một flow Gateway đã xác thực?
8. Vì sao header tenantId hoặc role không thể thay thế kiểm tra quyền?
9. Retry và Aggregator có thể gặp vấn đề gì nếu cho client quyết định correlationId?
10. Phải kiểm thử thế nào để chứng minh message chỉ đi tới các channel trong allowlist?

## 14. Checklist trước khi đưa Header-Based Router vào vận hành

- Đã phân loại các **nguồn dữ liệu** và xác định trust boundary ở từng adapter/gateway.
- Identity, tenant và quyền được xác minh bởi server, không sao chép từ input do client đặt.
- Routing header được tính từ policy và dữ liệu đã validate.
- Router có **channel mapping allowlist** và **channelKeyFallback(false)**.
- Missing/unknown key có chính sách **fail fast, quarantine hoặc discard rõ ràng**.
- Không copy headers không tin cậy, kể cả replyChannel, errorChannel, routingSlip và priority.
- Header dùng cho chẩn đoán có giới hạn độ dài/định dạng và không quyết định quyền truy cập.
- Đã kiểm tra propagation qua Transformer, Filter, Gateway và adapters.
- Kiểm tra quyền tại consumer trước khi thực hiện side effect nhạy cảm.
- Có test giả mạo route, tenant, channel name, header điều khiển và test đường đi hợp lệ.
- Error flow, retry, idempotency và correlation do các thành phần tin cậy chịu trách nhiệm.
- Metrics và log phát hiện key lạ nhưng không lộ dữ liệu nhạy cảm.

**Kết luận:** Header-Based Router đưa ra quyết định từ **metadata**. Metadata chỉ an toàn khi có **nguồn gốc được xác minh và trách nhiệm tạo/cập nhật rõ ràng**. Hãy tạo message sạch từ payload đã kiểm tra, gắn thông tin tenant/quyền từ server, dùng mapping cố định và tắt fallback theo tên channel. Khi bảo vệ cả điểm vào và các consumer, Spring Integration có thể kết hợp Router, Filter, Gateway và các pattern khác mà vẫn duy trì được luồng xử lý có thể kiểm chứng.

## Tài liệu tham khảo

- [Spring Integration Reference — Router Implementations](https://docs.spring.io/spring-integration/reference/router/implementations.html): HeaderValueRouter, channel mapping và cơ chế giải quyết destination.
- [Spring Integration API — AbstractMappingMessageRouter](https://docs.spring.io/spring-integration/api/org/springframework/integration/router/AbstractMappingMessageRouter.html): channelKeyFallback, resolutionRequired, defaultOutputChannel và cảnh báo về routing key độc hại.
- [Spring Integration Reference — Transformer / Header Filter](https://docs.spring.io/spring-integration/reference/transformer.html): loại bỏ các header cụ thể và quy tắc transformation.
- [Spring Integration Reference — Content Enricher](https://docs.spring.io/spring-integration/reference/content-enrichment.html): Header Enricher và metadata thuộc trách nhiệm của các endpoint.
- [Spring Integration Reference — HTTP Header Mappings](https://docs.spring.io/spring-integration/reference/http/header-mapping.html): ánh xạ headers tại HTTP adapter/gateway.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): tác động của loại channel đến dispatch, thread và lỗi.
