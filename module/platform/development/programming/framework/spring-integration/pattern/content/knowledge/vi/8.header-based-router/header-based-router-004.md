# Header bị mất qua adapter

## 1. Một sự cố định tuyến khó nhận biết

Trong Spring Integration, **Header-based Router** đọc thông tin trong **message headers** để chọn output channel. Ví dụ, header `routeRegion=VN` đưa đơn hàng đến nhánh nội địa, còn `routeRegion=INTL` đưa đến nhánh quốc tế. Mô hình này cho phép tách logic điều phối khỏi payload và handler nghiệp vụ.

Nhưng khi message đi qua **inbound/outbound adapter hoặc gateway** của HTTP, JMS, Kafka, AMQP, file hay một transport khác, header có thể bị lọc, đổi tên, đổi kiểu hoặc không được chuyển sang protocol. Router ở phía nhận thấy header vắng mặt nên không thể định tuyến — dù router phía gửi đã hoạt động đúng.

~~~mermaid
flowchart TD
    A["Message<Order>: routeRegion=VN"] --> B[Outbound Adapter]
    B --> C{Header mapping}
    C -->|Có ánh xạ| D[Transport có route metadata]
    C -->|Bỏ header| E[Transport thiếu route metadata]
    D --> F[Inbound Adapter]
    E --> F
    F --> G{HeaderValueRouter}
    G -->|VN| H[(orders.vn)]
    G -->|INTL| I[(orders.intl)]
    G -->|Thiếu/không hợp lệ| J[Rejection / error flow]
~~~

Đây là lỗi ở **hợp đồng chuyển giao metadata**, không nhất thiết là lỗi của Router. Nếu chỉ thêm default route để xử lý một header bị mất, ứng dụng có thể vô tình gửi đơn hàng quốc tế vào nhánh nội địa. Phải lần theo **đường đi của header ở từng ranh giới**, trước khi thay policy định tuyến.

Bài học thuộc chương **Header-based router** của module `SPRING_INTEGRATION_PATTERN`: triển khai Enterprise Integration Patterns bằng Spring Integration để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng. Việc bảo toàn metadata ảnh hưởng đến Router, Filter, Transformer, Gateway, Splitter/Aggregator, retry, error channel, correlation và khả năng kiểm thử/truy vết.

**Mục tiêu:** nhận diện các vị trí mất header, phân biệt Spring MessageHeaders với transport headers, cấu hình HeaderValueRouter đúng, khôi phục header có kiểm soát, kiểm thử qua adapter và xử lý fail closed khi route metadata không còn.

## 2. Phân biệt các lớp header

### 2.1. Header của Spring Message

Trong Spring Messaging, `Message<T>` có payload và `MessageHeaders`. Ví dụ:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> order = MessageBuilder.withPayload("ORD-1001")
        .setHeader("routeRegion", "VN")
        .setHeader("traceId", "trace-ord-1001")
        .setHeader("sourceSystem", "checkout")
        .build();

String region = (String) order.getHeaders().get("routeRegion");
// region == "VN"
~~~

Với flow trong cùng ứng dụng, endpoint nhận `Message<?>` có thể đọc các header này. Nhưng khi đưa dữ liệu ra transport bên ngoài, Spring phải ánh xạ metadata sang định dạng của giao thức đó. Không có bảo đảm mọi `MessageHeaders` đều được ánh xạ hoặc có thể tuần tự hóa.

| Tầng | Ví dụ | Trách nhiệm |
|---|---|---|
| Spring MessageHeaders | `routeRegion=VN` | Giá trị mà HeaderValueRouter cần đọc. |
| Outbound header mapper | `routeRegion` → `x-route-region` | Chọn key/kiểu được phép mang ra ngoài. |
| Transport | HTTP header, Kafka header bytes, JMS property | Lưu/truyền theo quy tắc giao thức. |
| Inbound header mapper | `x-route-region` → `routeRegion` | Đọc và chuẩn hóa thành header nội bộ. |
| Router ở bên nhận | `HeaderValueRouter("routeRegion")` | Định tuyến dựa trên key đã chuẩn hóa. |

Tên `routeRegion` **không tự động đồng nghĩa** với HTTP `X-Route-Region` hoặc Kafka header cùng tên. Adapter cụ thể có thể chỉ cho phép một số header, thêm prefix, chuyển kiểu, hoặc không giữ header tùy biến nếu chưa cấu hình.

### 2.2. Loại header và cách truyền qua biên

| Header | Mục đích | Khi đi qua adapter |
|---|---|---|
| `routeRegion`, `tenantId` | Chọn nhánh theo vùng/tenant | Cần mapping và **kiểm tra tính đáng tin** của nguồn. |
| `traceId` / trace context | Nối log và distributed trace | Cần propagation đúng quy ước protocol/tracing. |
| `correlationId` | Nhóm message liên quan | Quan trọng khi Splitter/Aggregator đi qua process. |
| `sequenceNumber`, `sequenceSize` | Mô tả vị trí/kích thước nhóm | Cần chuyển kiểu và semantics nhất quán nếu sử dụng từ xa. |
| `replyChannel` | Địa chỉ trả lời của request–reply nội bộ | Có thể là object channel JVM; không truyền nguyên object sang JVM khác. |
| `errorChannel` | Nơi xử lý lỗi nội bộ | Không tự trở thành error destination của broker. |
| `id`, `timestamp` | Nhận diện message/điểm tạo | Có thể được sinh lại khi tạo message mới. |
| `history` | Message History của Spring Integration | Không tự là distributed trace bền vững qua nhiều dịch vụ. |

**Không nên chọn “gửi tất cả headers” như giải pháp mặc định.** Một số header chứa đối tượng không tuần tự hóa được; một số chứa thông tin nhạy cảm; một số chỉ có ý nghĩa trong JVM hiện tại. Ở ranh giới hệ thống, hãy xác định **allowlist** metadata, cách encoding và quyền truy cập.

## 3. Các nguyên nhân thường làm mất header

| Nguyên nhân | Hiện tượng | Điều cần kiểm tra |
|---|---|---|
| Outbound mapper lọc header | Spring message có `routeRegion` nhưng request/record ra ngoài không có. | Danh sách outbound header names/patterns, cấu hình adapter. |
| Inbound mapper không khôi phục | Protocol có `x-route-region` nhưng Spring message ở bên nhận không có `routeRegion`. | Inbound mapper, decoder, bước normalization. |
| Tên header không thống nhất | Bên gửi đặt `routeRegion`, router bên nhận đọc `region`. | Contract tên và cách viết hoa/thường/prefix. |
| Kiểu giá trị đổi | Header đến dưới dạng `byte[]`, router mong `String`. | Charset, converter, typed mapper. |
| Tạo message mới chỉ từ payload | Sau custom transformer/adapter, header biến mất. | `MessageBuilder.withPayload(...).build()` có copy header hay không. |
| Header không thể serialize | `replyChannel` là object nội bộ bị bỏ qua hoặc gây lỗi. | Giao thức reply/correlation thay vì truyền object JVM. |
| Gateway tạo reply mới | Request có route header, response message không có. | Contract mapping của reply/response. |
| Nhiều adapter nối tiếp | Mất header tại hop thứ hai hoặc thứ ba. | Quan sát message và protocol ở **từng hop**. |
| Có bước chủ động xóa | `.removeHeaders(...)` hoặc handler làm sạch metadata. | Chính sách lọc header, bảo mật và vị trí chuyển đổi. |

**HTTP:** header tùy biến trong một HTTP request/response phải được mapper của inbound/outbound gateway cho phép. Khi chuẩn hóa HTTP `X-Route-Region` thành `routeRegion`, hãy xác nhận kiểu dữ liệu mà ứng dụng thực sự nhận được. Không tin header do public client cung cấp để quyết định tenant hoặc quyền truy cập.

**Kafka:** Kafka record headers chứa giá trị ở dạng bytes, còn Spring MessageHeaders có thể chứa object đã được converter giải mã. Cách mapping phụ thuộc Spring for Apache Kafka và cấu hình serializer/converter; không mặc định giá trị ở phía nhận luôn là `String`.

**JMS/AMQP:** tên và kiểu properties/headers, metadata transport và chính sách mapper khác nhau. Không coi chúng như một kênh tuần tự hóa arbitrary Java object, đặc biệt các `replyChannel` và `errorChannel` nội bộ.

**File/CSV/JSON:** nội dung file có thể chỉ chứa payload, không có metadata để khôi phục. Nếu cần route metadata sau bước đọc file, hãy thiết kế envelope, manifest hoặc nguồn xác minh phù hợp, thay vì đoán lại giá trị header đã mất.

## 4. HeaderValueRouter đọc header và chọn channel ra sao?

### 4.1. Ba khái niệm phải tách rời

~~~text
Message<Order> (routeRegion=VN)
             |
             v
HeaderValueRouter("routeRegion")
             |
        routing key VN
             |
        channelMapping
             |
          orders.vn
             |
        Domestic Handler
~~~

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Header name | `routeRegion` | Key mà Router tìm trong `MessageHeaders`. |
| Header value / routing key | `VN` | Quyết định dựa trên metadata. |
| Channel destination | `orders.vn` | Bean channel nhận message. |

Một header có thể **có tên đúng nhưng giá trị sai kiểu**, hoặc **có giá trị đúng nhưng tên khác**. Do đó quy trình chẩn đoán phải nhìn cả tên, kiểu, nguồn dữ liệu và mapping đích.

### 4.2. Ba loại lỗi header

1. **Missing:** không có `routeRegion`.
2. **Invalid:** có header nhưng không nằm trong tập cho phép, chẳng hạn `UNKNOWN` hoặc bytes chưa decode.
3. **Untrusted:** `VN` trông hợp lệ nhưng lại do người gửi ngoài hệ thống tự khai báo mà chưa được xác thực.

Đừng chữa tình huống missing bằng cách gán mặc định `VN` nếu nghiệp vụ không cho phép. Với yêu cầu cần cô lập dữ liệu theo tenant/vùng, đó có thể là lỗi bảo mật nghiêm trọng.

### 4.3. Chọn policy khi header không dùng được

| Hoàn cảnh | Chiến lược nên cân nhắc |
|---|---|
| Metadata định tuyến bắt buộc bị mất | Fail closed, ghi event thiếu header, không gửi tới một nhánh hợp lệ tùy tiện. |
| Có vùng ngoài tập hỗ trợ | Business rejection hoặc nhánh `unroutable` có consumer rõ ràng. |
| Giá trị sai kiểu sau mapping | Normalize/decode/validate tại biên. |
| Header do client không tin cậy gửi | Xác thực rồi xác định lại thông tin từ dữ liệu được phép. |
| Lỗi mapping trong deploy | Fail fast và cảnh báo; không che lỗi bằng default route. |

## 5. Ví dụ Java DSL: route theo header đủ điều kiện

Ví dụ hướng tới **Java 17+, Spring Boot 3.x và Spring Integration 6.x**, cùng dependency `spring-boot-starter-integration`. Gồm một Gateway đặt `routeRegion`, một HeaderValueRouter và hai channel nhận. Đây là **đường đi nội bộ**, chưa kiểm tra được adapter thật.

~~~mermaid
flowchart LR
    G[OrderGateway] --> I[(orders.input)]
    I --> R{HeaderValueRouter: routeRegion}
    R -->|VN| V[(orders.vn)]
    R -->|INTL| X[(orders.intl)]
    R -. Missing / unknown .-> E[Failure / error flow]
    V --> VH[VN Handler]
    X --> XH[International Handler]
~~~

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.router.HeaderValueRouter;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.handler.annotation.Header;

record Order(String orderId, long amount) {}
record Receipt(String orderId, String route, String status) {}

@MessagingGateway
interface OrderGateway {
    @Gateway(requestChannel = "orders.input")
    Receipt submit(Order order, @Header("routeRegion") String region);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class HeaderRegionRoutingConfig {

    @Bean(name = "orders.input")
    MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "orders.vn")
    MessageChannel domestic() {
        return new DirectChannel();
    }

    @Bean(name = "orders.intl")
    MessageChannel international() {
        return new DirectChannel();
    }

    @Bean
    HeaderValueRouter regionRouter() {
        HeaderValueRouter router = new HeaderValueRouter("routeRegion");
        router.setChannelMapping("VN", "orders.vn");
        router.setChannelMapping("INTL", "orders.intl");
        router.setChannelKeyFallback(false);
        router.setResolutionRequired(true);
        return router;
    }

    @Bean
    IntegrationFlow routeOrders(HeaderValueRouter regionRouter) {
        return IntegrationFlow.from("orders.input")
                .route(regionRouter)
                .get();
    }

    @Bean
    IntegrationFlow processDomesticOrders() {
        return IntegrationFlow.from("orders.vn")
                .handle(Order.class, (order, headers) ->
                        new Receipt(order.orderId(), "VN", "ACCEPTED"))
                .get();
    }

    @Bean
    IntegrationFlow processInternationalOrders() {
        return IntegrationFlow.from("orders.intl")
                .handle(Order.class, (order, headers) ->
                        new Receipt(order.orderId(), "INTL", "PENDING_EXPORT"))
                .get();
    }
}
~~~

**Giải thích:**

- `@MessagingGateway` chuyển lời gọi Java thành message và đợi reply.
- `@Header("routeRegion")` chỉ định header dùng để route. Caller phải được kiểm soát hoặc đã xác minh region.
- `setChannelMapping` tách **key `VN`/`INTL`** khỏi channel bean `orders.vn`/`orders.intl`.
- `setChannelKeyFallback(false)` tránh thử dùng key chưa mapping làm tên bean channel; `setResolutionRequired(true)` yêu cầu có đích được phân giải.
- `DirectChannel` thuận tiện cho ví dụ request–reply đồng bộ; kết quả `Receipt` chỉ là mô phỏng, không phải xử lý thật ở broker/database.

Caller nội bộ có thể gọi:

~~~java
Receipt vn = orderGateway.submit(
        new Order("ORD-101", 200_000L), "VN");
// vn.route() == "VN" và vn.status() == "ACCEPTED"

Receipt intl = orderGateway.submit(
        new Order("ORD-102", 200_000L), "INTL");
// intl.route() == "INTL" và intl.status() == "PENDING_EXPORT"
~~~

Mẫu này chứng minh Router hoạt động khi header đã đúng, **không chứng minh** HTTP/Kafka/JMS adapter đã chuyển header thành công. Phải kiểm thử riêng ở ranh giới.

## 6. Tái hiện lỗi mất header khi dựng message mới

### 6.1. Sai lầm phổ biến: chỉ copy payload

Giả sử custom adapter nhận message rồi dựng một message mới chỉ từ payload:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> source = MessageBuilder.withPayload("ORD-1001")
        .setHeader("routeRegion", "VN")
        .setHeader("traceId", "trace-1001")
        .build();

// Sai: chỉ truyền payload, không truyền metadata định tuyến.
Message<String> broken = MessageBuilder
        .withPayload(source.getPayload())
        .build();

System.out.println(source.getHeaders().get("routeRegion")); // VN
System.out.println(broken.getHeaders().get("routeRegion")); // null
~~~

Đoạn này **cố ý làm mất header** để minh họa vấn đề. Không nên suy luận rằng mọi `Transformer` trong Spring Integration đều làm mất header: hạ tầng framework có cơ chế truyền headers trong nhiều loại endpoint; rủi ro xuất hiện khi custom code, adapter hoặc converter tái tạo message mà không tuân thủ contract.

Nếu tiếp tục gửi `broken` vào `HeaderValueRouter("routeRegion")`, router không có giá trị để chọn kênh. Việc thêm `defaultOutputChannel("orders.vn")` chỉ khiến lỗi khó phát hiện hơn và có thể route sai.

### 6.2. Tạo message mới nhưng bảo toàn metadata nội bộ

Khi thực sự cần copy headers trong **cùng vùng tin cậy**, có thể xây dựng từ message gốc:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> preserved = MessageBuilder
        .fromMessage(source)
        .build();

System.out.println(preserved.getHeaders().get("routeRegion")); // VN
System.out.println(preserved.getHeaders().get("traceId")); // trace-1001
~~~

Hoặc khi đổi payload:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<NormalizedOrder> normalize(Message<Order> input) {
    Order original = input.getPayload();
    NormalizedOrder normalized =
            new NormalizedOrder(original.orderId(), original.amount());

    return MessageBuilder.withPayload(normalized)
            .copyHeaders(input.getHeaders())
            .build();
}
~~~

`NormalizedOrder` ở đây là DTO minh họa, cần định nghĩa trong ứng dụng nếu sử dụng code. Việc `copyHeaders` **không** có nghĩa mọi header nên đi sang transport bên ngoài. Vẫn cần lọc theo hợp đồng outbound, đặc biệt với object như `replyChannel`, `errorChannel` và metadata bảo mật.

### 6.3. Không thể khôi phục header không còn nguồn

Nếu message `broken` chỉ còn một string `ORD-1001`, không có transport header, payload không chứa vùng và không có nguồn xác thực độc lập, **không có phép biến đổi nào khôi phục chính xác `routeRegion`**. Đừng đoán `VN` từ một tiền tố ID hoặc đặt default chỉ để flow chạy tiếp.

Các hướng xử lý hợp lệ là:

1. **Sửa mapper ở biên gửi/nhận** để giữ metadata vốn có theo allowlist.
2. **Tính lại từ nguồn đáng tin cậy** nếu business contract cho phép, ví dụ tra cứu vùng từ bản ghi đơn hàng đã được xác minh.
3. **Từ chối và yêu cầu gửi lại** khi metadata bắt buộc bị thiếu.
4. **Đưa vào nhánh quarantine/manual recovery** được thiết kế với quyền truy cập, retention và replay policy rõ ràng.

## 7. Ánh xạ header qua ranh giới transport một cách có kiểm soát

### 7.1. Thiết kế một envelope nhỏ

Ví dụ dưới đây mô phỏng cách một adapter **encode** message thành dữ liệu trên đường truyền và cách inbound adapter **decode** lại. Đây là đoạn Java độc lập để giải thích hợp đồng mapping, **không phải cấu hình sẵn của adapter HTTP, Kafka hoặc JMS**:

~~~java
import java.util.Map;
import java.util.Set;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record WireEnvelope(Order payload, Map<String, String> metadata) {}

final class TransportOrderMapper {
    private static final Set<String> ALLOWED_REGIONS =
            Set.of("VN", "INTL");

    WireEnvelope encode(Message<Order> message) {
        Object raw = message.getHeaders().get("routeRegion");
        if (!(raw instanceof String region)
                || !ALLOWED_REGIONS.contains(region)) {
            throw new IllegalArgumentException(
                    "Missing or invalid routeRegion before sending");
        }

        // Hợp đồng minh họa: chỉ truyền metadata được cho phép.
        return new WireEnvelope(
                message.getPayload(),
                Map.of("x-route-region", region));
    }

    Message<Order> decode(WireEnvelope wire) {
        String region = wire.metadata().get("x-route-region");
        if (region == null || !ALLOWED_REGIONS.contains(region)) {
            throw new IllegalArgumentException(
                    "Missing or invalid region after transport");
        }

        return MessageBuilder.withPayload(wire.payload())
                .setHeader("routeRegion", region)
                .build();
    }
}
~~~

**Ý nghĩa:** transport dùng `x-route-region`; router nội bộ dùng `routeRegion`. Mapper là nơi **dịch tên và kiểu**. Hợp đồng này giúp phát hiện rõ khi metadata thiếu thay vì route sang một kênh mặc định không chính xác.

**Giới hạn bảo mật:** `decode` mới kiểm tra vùng **hợp lệ về cú pháp**, chưa kiểm tra người gửi có quyền chọn vùng ấy. Ở một public ingress hoặc consumer nhận message từ đối tác, phải xác thực nguồn và xác định vùng từ dữ liệu được cấp quyền; không đặt niềm tin vào một header do bên ngoài tự khai.

### 7.2. Map header thế nào cho từng transport?

Với adapter thực tế, thiết kế nên có **hợp đồng rõ** thay vì cấu hình wildcard mọi headers:

| Transport | Điểm cần cấu hình/kiểm tra | Ví dụ chẩn đoán |
|---|---|---|
| HTTP | Inbound/outbound header mapper; tên HTTP, multi-value, case/prefix, response mapping | `X-Route-Region` có xuất hiện trên wire và được chuẩn hóa thành `routeRegion`? |
| Kafka | Record headers bytes, serializer/converter/header mapper, header patterns | `routeRegion` ở record là bytes kiểu gì, consumer nhận `byte[]` hay `String`? |
| JMS | Properties/header mapping, các kiểu được phép, tên thuộc tính | Thuộc tính application có được gửi thành property và đọc lại không? |
| AMQP | Message properties/header mapping, converter và policy broker | `routeRegion` đã đi ra AMQP headers và trở về Spring headers chưa? |
| File/CSV | Schema/envelope/manifest | File có lưu metadata route hay chỉ payload? |
| Custom adapter | Hàm chuyển đổi `Message<?>` ↔ protocol | Code có tạo `MessageBuilder.withPayload` mà quên headers? |

Không sử dụng kiểu dữ liệu tùy ý một cách tràn lan. Với Kafka, nếu ứng dụng chủ động đọc một header bytes theo hợp đồng UTF-8, có thể decode có kiểm tra:

~~~java
import java.nio.charset.StandardCharsets;

String decodeRegion(Object raw) {
    if (raw instanceof String region) {
        return region;
    }
    if (raw instanceof byte[] bytes) {
        return new String(bytes, StandardCharsets.UTF_8);
    }
    throw new IllegalArgumentException("Unsupported routeRegion type");
}
~~~

Hàm này chỉ giải thích **chuẩn hóa kiểu theo hợp đồng đã biết**. Không được tự động coi mọi `byte[]` là UTF-8 nếu producer thực tế dùng format khác; cũng không dùng giá trị sau decode để quyết định tenant trước khi xác thực nguồn.

### 7.3. Headers có thể bị bỏ vì chính sách bảo mật — không phải bug

Một adapter có thể cố tình không gửi `Authorization`, cookie, token, object `MessageChannel` hoặc header chứa dữ liệu nhạy cảm. Đó thường là **hành vi đúng**. Vì vậy:

- Với **routing metadata**, truyền chỉ các trường đã được phê duyệt và không nhạy cảm ở ranh giới thích hợp.
- Với **security context**, dùng cơ chế xác thực của transport/identity đáng tin cậy; không copy token hoặc quyền qua mọi message.
- Với **reply path**, dùng giao thức request–reply và correlation/return-address được transport hỗ trợ, không serialize object channel của JVM gốc.
- Với **trace context**, dùng propagation chuẩn khi đã cấu hình tracing thay vì sao chép tùy tiện mọi header nội bộ.

Giải pháp đúng cho “header bị mất” nhiều khi là **thay đổi cách truyền ý nghĩa của nó**, chứ không phải ép adapter giữ nguyên đối tượng gốc.

## 8. Header-based Router, Filter và lỗi routing liên quan nhau ra sao?

### 8.1. Kiểm tra trước Router

Để Router không tự đối mặt với mọi kiểu giá trị tùy ý từ bên ngoài, nên có bước validation/normalization tại biên:

~~~text
External system
   -> Inbound Adapter
   -> Map/normalize header
   -> Validate allowed region + identity
   -> Header-based Router
       -> orders.vn
       -> orders.intl
~~~

Đừng nhầm **Message Filter** với **Content-Based Router**:

- Filter quyết định **message có được đi tiếp** hay không.
- Router chọn **channel đích** cho message đủ điều kiện.
- Transformer/Header Enricher có thể chuẩn hóa hoặc bổ sung metadata theo contract trước khi route.

Nếu Filter bỏ message mà không có reject reply/discard flow phù hợp, Gateway đang chờ request–reply có thể timeout. Nếu route thiếu header, nên trả lỗi có nghĩa hoặc chuyển nhánh `unroutable` được thiết kế có consumer, không im lặng loại message.

### 8.2. Cấu hình default channel không giải quyết nguyên nhân

Một default channel chỉ phù hợp nếu nghiệp vụ quy định rõ “mọi vùng khác phải được xử lý thủ công”. Nó **không nên** biến missing `routeRegion` do mapper lỗi thành một yêu cầu `VN`. Với adapter thay đổi giữa hai phiên bản, default có thể che một regression làm phần lớn message đi sai.

Phân loại lỗi giúp chọn hành động:

| Loại lỗi | Retry có ích không? | Cách xử lý |
|---|---|---|
| Header thiếu do mapper config cố định | Retry nguyên request thường không giúp. | Sửa mapping, quarantine/replay khi hợp đồng cho phép. |
| Header thiếu trong message một lần do nguồn gửi | Chỉ có ích nếu nguồn có thể gửi lại đầy đủ. | Reject, phản hồi validation, audit. |
| Header có giá trị ngoài tập hỗ trợ | Retry với cùng dữ liệu không giúp. | Business rejection hoặc manual review. |
| Channel đích đầy hoặc consumer tạm ngừng | Có thể, nếu lỗi tạm thời. | Bounded retry/backoff, overload policy, idempotency. |
| Outbound network timeout | Có thể, nếu operation an toàn để thử lại. | Quản lý retry và kết quả không chắc chắn/duplicate. |

### 8.3. Khi mất correlation hoặc reply metadata

`routeRegion` không phải header duy nhất quan trọng. Trong flow có Splitter/Aggregator:

~~~mermaid
flowchart LR
    O[Order] --> S[Splitter]
    S --> A[Item A]
    S --> B[Item B]
    A --> T[Adapter / Broker]
    B --> T
    T --> G[Aggregator theo correlation]
    G --> R[OrderResult]
~~~

Nếu correlation/sequence metadata bị bỏ khi đi qua transport, Aggregator phía nhận có thể không biết các item thuộc **cùng một nhóm**, hoặc không có đủ thông tin để release đúng. Giải pháp là định nghĩa **correlation key** ổn định trong protocol, mapping cả ở phía gửi và nhận, cùng expiration/recovery policy; không trông chờ header nội bộ `replyChannel` tự đi qua broker.

Với request–reply, khi inbound adapter tạo message mới, nó có thể tạo **reply channel khác**, hoặc cần thông tin correlation của transport. Không sử dụng một `replyChannel` object của ứng dụng gửi như địa chỉ trong JVM nhận. Khi thiết kế luồng nhiều dịch vụ phải phân biệt:

1. **Business ID** như `orderId`.
2. **Message ID** của message cụ thể.
3. **Correlation ID** của nhóm/request.
4. **Trace ID** của hành trình quan sát.
5. **Reply destination** thực sự hợp lệ trong transport.

## 9. Truy nguyên chính xác header mất ở đâu

### 9.1. Năm điểm quan sát

Để tìm nguyên nhân có hệ thống, đặt các điểm quan sát tối thiểu:

~~~text
P1  Trước outbound adapter: Spring MessageHeaders
P2  Tại transport: protocol headers / envelope
P3  Sau inbound adapter: Spring MessageHeaders
P4  Trước HeaderValueRouter: normalized routing metadata
P5  Sau Router: kênh nhánh đã thực sự nhận message
~~~

Nếu `P1` có `routeRegion` nhưng `P2` không có, lỗi ở **outbound mapping**. Nếu `P2` có mà `P3` không, kiểm tra **inbound mapping/converter**. Nếu `P3` có nhưng `P4` không, kiểm tra custom Transformer, Header Enricher/Filter hoặc chỗ dựng lại message. Nếu `P4` có đúng kiểu nhưng `P5` không nhận, kiểm tra **Router mapping/channel resolution/subscriber/dispatch**, đừng sửa adapter.

### 9.2. Ghi log theo nguyên tắc tối thiểu

Ví dụ schema sự kiện có cấu trúc (do ứng dụng định nghĩa, không phải output mặc định):

~~~text
event=OUTBOUND_PREPARED  orderId=ORD-1 traceId=T-1
  routeHeaderPresent=true routeRegion=VN

event=TRANSPORT_RECEIVED orderId=ORD-1 traceId=T-1
  mappedRouteHeaderPresent=false

event=ROUTING_REJECTED orderId=ORD-1 traceId=T-1
  reason=MISSING_ROUTE_HEADER component=regionRouter
~~~

Điểm quan trọng là **sự hiện diện**, **tên**, **kiểu** và **nguồn** của header. Không cần log nguyên payload, access token hay tất cả message headers. Đối với metadata nhạy cảm như tenant, có thể log một mã vùng an toàn hoặc hashed identifier phù hợp chính sách.

`Message History` giúp quan sát các component Spring Integration mà message đã đi qua khi bật tracking; nó không tự ghi header diff ở mỗi bước và không tự trở thành distributed trace qua broker. Nếu flow bất đồng bộ qua executor hoặc process khác, cần tracing/log propagation rõ ràng. MDC của thread cũ không tự xuất hiện trên thread mới.

### 9.3. Chỉ số đáng theo dõi

| Chỉ số | Khi tăng bất thường |
|---|---|
| `routing_header_missing_total` | Inbound mapper/nguồn gửi có thể bị regression. |
| `routing_header_invalid_total` | Schema hoặc kiểu header thay đổi; nguồn gửi không đúng contract. |
| `routing_header_untrusted_total` | Có thể có spoofing hoặc sai cấu hình trust boundary. |
| `unresolved_route_total` | Channel mapping/bean registration/route key có vấn đề. |
| `branch_received_total` theo vùng hữu hạn | Kiểm tra phân phối vào nhánh sau Router. |
| `processing_errors_total` theo nhánh | Phân biệt route đúng nhưng handler thất bại. |
| `retry_attempts_total` | Quan sát recovery, tránh retry storm. |

Không dùng `orderId` hoặc `traceId` làm metric label vì cardinality lớn. ID riêng phù hợp hơn trong log/tracing có quyền truy cập và retention kiểm soát.

## 10. Kiểm thử header propagation và nhánh routing

### 10.1. Unit test chứng minh tạo message mới có thể làm mất header

JUnit 5 cho phép kiểm thử nguyên nhân trước khi dùng Spring context:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class HeaderCopyTest {

    @Test
    void rebuildingPayloadOnlyDropsCustomHeaders() {
        Message<String> original = MessageBuilder
                .withPayload("ORD-1001")
                .setHeader("routeRegion", "VN")
                .build();

        Message<String> broken = MessageBuilder
                .withPayload(original.getPayload())
                .build();

        assertEquals("VN",
                original.getHeaders().get("routeRegion"));
        assertNull(broken.getHeaders().get("routeRegion"));
    }

    @Test
    void rebuildingFromOriginalRetainsRoutingHeader() {
        Message<String> original = MessageBuilder
                .withPayload("ORD-1001")
                .setHeader("routeRegion", "VN")
                .build();

        Message<String> preserved = MessageBuilder
                .fromMessage(original)
                .build();

        assertEquals("VN",
                preserved.getHeaders().get("routeRegion"));
    }
}
~~~

**Lưu ý:** test này cố tình không khẳng định `MessageHeaders.ID` giữa hai message giống hay khác nhau. Cái cần kiểm chứng là **routing metadata đã có hoặc mất**; nếu cần trace nhiều message mới, dùng business/trace/correlation ID phù hợp.

### 10.2. Unit test mô phỏng outbound/inbound mapping

Với `TransportOrderMapper` ở phần 7:

~~~java
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderEnvelopeMapperTest {
    private final TransportOrderMapper mapper =
            new TransportOrderMapper();

    @Test
    void routeRegionSurvivesTheEnvelopeRoundTrip() {
        Message<Order> original = MessageBuilder
                .withPayload(new Order("ORD-10", 400_000L))
                .setHeader("routeRegion", "INTL")
                .build();

        WireEnvelope wire = mapper.encode(original);
        Message<Order> restored = mapper.decode(wire);

        assertEquals("INTL",
                wire.metadata().get("x-route-region"));
        assertEquals("INTL",
                restored.getHeaders().get("routeRegion"));
    }

    @Test
    void missingRegionIsRejectedInsteadOfDefaulted() {
        WireEnvelope wire = new WireEnvelope(
                new Order("ORD-11", 200_000L), Map.of());

        assertThrows(IllegalArgumentException.class,
                () -> mapper.decode(wire));
    }
}
~~~

Test này chứng minh hợp đồng mapper **do ứng dụng tự viết**, không chứng minh Spring HTTP/Kafka/JMS adapter đã được cấu hình giống mapper. Khi chuyển sang adapter thật, phải có thêm **integration test đi qua transport hoặc test fixture của adapter**.

### 10.3. Integration test cho HeaderValueRouter

Kiểm thử Spring Test/JUnit 5 với `HeaderRegionRoutingConfig` ở phần 5:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(HeaderRegionRoutingConfig.class)
class HeaderRegionRouterTest {
    @Autowired
    private OrderGateway gateway;

    @Autowired
    @Qualifier("orders.input")
    private MessageChannel input;

    @Test
    void routesDomesticRequest() {
        Receipt receipt = gateway.submit(
                new Order("ORD-21", 200_000L), "VN");

        assertEquals("VN", receipt.route());
        assertEquals("ACCEPTED", receipt.status());
    }

    @Test
    void routesInternationalRequest() {
        Receipt receipt = gateway.submit(
                new Order("ORD-22", 300_000L), "INTL");

        assertEquals("INTL", receipt.route());
    }

    @Test
    void failsWhenRoutingHeaderIsMissing() {
        assertThrows(MessagingException.class, () ->
                input.send(MessageBuilder
                        .withPayload(new Order("ORD-23", 100_000L))
                        .build(), 0));
    }

    @Test
    void failsForUnknownRouteInsteadOfUsingChannelName() {
        assertThrows(MessagingException.class, () ->
                gateway.submit(
                        new Order("ORD-24", 100_000L), "UNKNOWN"));
    }
}
~~~

Trong test, loại exception chi tiết có thể phụ thuộc phiên bản framework, gateway và cấu hình router; các assertion trên nhắm tới họ `MessagingException` ở cấu hình ví dụ. Khi chạy thực tế, hãy xác nhận kiểu/cause phù hợp rồi bổ sung assertion về lỗi **MISSING_ROUTE_HEADER** hoặc **UNKNOWN_ROUTE**, không dựa duy nhất vào một exception message dễ thay đổi.

Hai test đầu **chưa chứng minh adapter propagation** vì Gateway nội bộ tự đặt header. Muốn kiểm tra header qua HTTP/JMS/Kafka cần test end-to-end qua adapter thực sự, bao gồm mapper, converter, tên transport header, kiểu sau giải mã và đúng channel đích.

### 10.4. Ma trận kiểm thử adapter trước khi deploy

| Tình huống | Kết quả mong đợi |
|---|---|
| Outbound message có `routeRegion=VN` | Header được chuyển ra wire đúng protocol contract. |
| Outbound message có `routeRegion=INTL` | Header được chuyển đi với tên/encoding đúng. |
| Inbound transport có header hợp lệ | Spring message khôi phục `routeRegion` đúng kiểu và giá trị. |
| Inbound transport thiếu header | Từ chối hoặc route quarantine theo contract, không tự `VN`. |
| Header có giá trị không hỗ trợ | Business rejection hoặc error, không tự chọn bean channel. |
| Header có bytes sai encoding | Decode fail rõ ràng, không sinh key ngẫu nhiên. |
| Header giả mạo từ client | Không bypass authorization/tenant isolation. |
| Custom Transformer chỉ copy payload | Test phát hiện header bị mất. |
| Adapter reply tạo message mới | Reply/correlation contract được xác minh, không phụ thuộc object nội bộ. |
| Nhánh Router không có consumer | Lỗi dispatch hoặc timeout có thể quan sát; không báo processed. |
| Splitter/Aggregator qua broker | Correlation/sequence được map và group release đúng chính sách. |
| Hệ thống retry một message lỗi | Không nhân đôi side effect; có idempotency và audit. |

## 11. Quy trình chẩn đoán sự cố theo từng bước

Giả sử Router ở ứng dụng B báo không tìm thấy `routeRegion` cho `orderId=ORD-5001`. Không chỉnh default ngay; làm lần lượt:

1. **Xác định danh tính nghiệp vụ và trace:** lấy `orderId`, khoảng thời gian, nguồn và `traceId`; đừng dựa duy nhất vào Message ID vì có thể đổi khi dựng message mới.
2. **Kiểm tra trước outbound adapter:** có `routeRegion` không? Tên/kiểu thực tế là gì? Có bị một Transformer trước đó xóa không?
3. **Kiểm tra wire format:** HTTP/broker thực sự có key và giá trị không? Xem mapper, allowlist và converter; không log payload nhạy cảm.
4. **Kiểm tra ngay sau inbound adapter:** có metadata không? Tên chuẩn nội bộ có khớp `routeRegion` hay không? Kiểu `String` hay `byte[]`?
5. **Kiểm tra trước Router:** có bước xây dựng lại `Message`, `removeHeaders` hoặc filter tùy biến làm mất header không?
6. **Kiểm tra Router mapping:** key đã được chuẩn hóa và có trong `channelMapping` chưa? Có `channelKeyFallback` không mong muốn hoặc default che lỗi không?
7. **Kiểm tra channel và consumer:** channel tồn tại, endpoint running, queue/poller/executor hoạt động chưa? Có thể đã route đúng nhưng dispatch hoặc xử lý thất bại.
8. **Kiểm tra error/retry:** nguồn có gửi lại đầy đủ metadata không? Retry có an toàn/idempotent không? Có nhóm Aggregator bị thiếu correlation và pending vô thời hạn không?
9. **Sửa tại đúng ranh giới:** bổ sung header mapper/normalizer, chỉnh contract với producer, hoặc sửa custom code; thêm test hồi quy cho case vừa gặp.

Nếu phát hiện **không còn nguồn đáng tin nào để khôi phục region**, phải xem đây là dữ liệu thiếu, không đoán giá trị. Với nghiệp vụ quan trọng, chọn quarantine/reject/replay theo chính sách đã phê duyệt.

## 12. Những lỗi thiết kế thường gặp

| Nhầm lẫn | Hậu quả | Cách làm đúng |
|---|---|---|
| “Spring MessageHeaders tự đi qua mọi adapter.” | Router bên nhận mất key. | Thiết kế outbound/inbound header mapping rõ ràng. |
| “Tên HTTP header luôn giống tên Spring header.” | Bên nhận dùng nhầm `X-Route-Region` và `routeRegion`. | Chuẩn hóa tại biên, thống nhất contract. |
| “Kafka header nào cũng là `String`.” | Cast sai hoặc route theo `byte[]`. | Dùng converter/decoder theo format đã thỏa thuận. |
| “`copyHeaders(*)` giải quyết mọi lỗi.” | Truyền object không hỗ trợ hoặc làm lộ metadata nhạy cảm. | Chỉ copy đúng phần được phép, nhất là qua trust boundary. |
| “Mất header thì mặc định `VN`.” | Route sai tenant/vùng, có thể gây rủi ro bảo mật. | Fail closed hoặc lấy lại từ nguồn xác thực. |
| “Header từ client luôn đáng tin.” | Người gửi giả mạo quyền hoặc khu vực. | Xác thực và tái tính quyết định từ context tin cậy. |
| “Router đã chọn channel là xử lý thành công.” | Không phát hiện subscriber stopped hoặc handler lỗi. | Theo dõi `ROUTE_DECIDED`, `BRANCH_ENTERED` và outcome. |
| “Retry tự chữa được lỗi mapping cố định.” | Retry storm mà vẫn thiếu header. | Phân loại lỗi, khắc phục cấu hình, replay an toàn. |
| “Reply channel nội bộ chuyển sang broker nguyên vẹn.” | Không có reply hợp lệ ở hệ thống khác. | Thiết kế return address/correlation của transport. |
| “Không cần giữ correlation khi Splitter qua adapter.” | Aggregator không gom được nhóm. | Mapping correlation/sequence và timeout/release strategy. |
| “Message History là distributed trace.” | Không nối được hành trình qua nhiều process. | Dùng trace propagation và quan sát thích hợp. |

## 13. Bài tập tự thực hành

1. **Tái hiện lỗi:** tạo message có `routeRegion`, sau đó tạo message mới chỉ từ payload. Gửi từng message vào HeaderValueRouter và ghi nhận kết quả; giải thích tại sao chỉ một trường hợp có thể route đúng.
2. **Tạo mapper:** sử dụng `TransportOrderMapper`, đổi field wire `x-route-region` thành một tên mới và viết test phát hiện mismatch tên inbound/outbound.
3. **HTTP:** dựng flow với HTTP inbound gateway hoặc adapter có cấu hình header mapper; gửi HTTP `X-Route-Region: VN`, kiểm tra tên/kiểu header nội bộ trước Router. Test riêng khi thiếu header.
4. **Kafka/JMS:** kiểm thử với adapter thực và một header routing tùy biến, xác nhận producer/consumer dùng cùng encoding và mapping; không trộn header nghiệp vụ với metadata offset/topic của transport.
5. **Authorization:** cố tình gửi `routeRegion=INTL` từ một caller chỉ được phép vùng `VN`. Thiết kế validation tại trust boundary và khẳng định request không được route sai.
6. **Correlated flow:** Splitter tạo ba message item, gửi qua adapter rồi gom lại. Kiểm tra `correlationId` và sequence sau mapping; mô phỏng một message thiếu và xử lý group expiration.
7. **Retry/recovery:** giả lập outbound mapping lỗi do deployment. Chứng minh retry nguyên message không có ích; thiết kế quarantine/replay sau khi mapper được sửa.
8. **Observability:** tạo metric `routing_header_missing_total`, log `HEADER_MAPPING_FAILED` và `ROUTE_DECIDED` theo business ID/trace ID; viết test xác định lỗi xảy ra trước Router hay ở channel đích.

### Câu hỏi tự kiểm tra

**Câu 1:** Vì sao `MessageBuilder.withPayload(old.getPayload()).build()` có thể làm HeaderValueRouter thiếu key? **Đáp án:** message mới không tự kế thừa headers từ `old`; phải chủ động truyền metadata phù hợp.

**Câu 2:** Transport đã nhận HTTP `X-Route-Region: VN` nhưng Router đọc `routeRegion` vẫn thấy `null`. Nên kiểm tra đâu trước? **Đáp án:** inbound header mapping/normalization, sau đó các bước trung gian trước Router.

**Câu 3:** Có nên truyền nguyên `replyChannel` là object Java sang Kafka để nhận reply ở JVM khác không? **Không.** Cần hợp đồng correlation và reply destination của transport thực tế.

**Câu 4:** Thiếu header dùng để chọn tenant có nên tự động route tới tenant mặc định không? **Không**, trừ khi có hợp đồng nghiệp vụ và chính sách bảo mật cho phép rõ ràng; thông thường phải fail closed.

**Câu 5:** Một message qua adapter có đủ `routeRegion` nhưng không được handler tiếp nhận. Có thể khẳng định header mapping sai không? **Chưa.** Cần kiểm tra channel mapping, subscriber, lifecycle và lỗi dispatch/downstream.

**Kết luận:** Khi Header-based Router định tuyến sai sau adapter, hãy kiểm tra **header đã được ánh xạ sang giao thức và khôi phục vào Spring MessageHeaders hay chưa**, thay vì vội sửa Router. Phân biệt dữ liệu nghiệp vụ, routing metadata, correlation và trace context; chỉ chuyển những header được phép qua biên tin cậy, chuẩn hóa tên/kiểu, từ chối dữ liệu thiếu hoặc không đáng tin, rồi kiểm thử end-to-end qua adapter. Cách làm này giúp các flow EIP với Router, Gateway, Transformer, Splitter/Aggregator, retry và error channel giữ được ý nghĩa điều phối, dễ truy nguyên và phục hồi có kiểm soát.
