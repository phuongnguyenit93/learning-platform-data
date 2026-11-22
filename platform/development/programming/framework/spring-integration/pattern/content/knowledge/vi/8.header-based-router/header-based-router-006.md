# Giá trị null hoặc header vắng mặt

Trong **Spring Integration**, **Header-Based Router** là một biến thể của Enterprise Integration Patterns (EIP) dùng **metadata trong message headers** để chọn channel đích. Thay vì đọc toàn bộ payload, router có thể dựa vào `region`, `messageType`, `priority` hoặc một header được hệ thống xác thực và chuẩn hóa trước đó.

Tuy nhiên, luồng định tuyến thường gặp một câu hỏi dễ bị bỏ qua: **Điều gì xảy ra khi header có giá trị `null` hoặc hoàn toàn không tồn tại?** Nếu không quy định rõ, message có thể bị rơi khỏi luồng, được đưa vào nhánh mặc định không phù hợp, hoặc gây exception khó chẩn đoán. Bài học này tập trung vào cách phân biệt **header vắng mặt**, **giá trị null**, **chuỗi rỗng**, **giá trị không được hỗ trợ** và **sai kiểu dữ liệu**, đồng thời thiết kế fallback/reject có thể kiểm thử.

Bài nằm trong chương **Header-based router** của module **SPRING_INTEGRATION_PATTERN**. Module hướng tới triển khai Enterprise Integration Patterns với Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation để tạo luồng thông điệp ít phụ thuộc, dễ mở rộng và quan sát được.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `MessageHeaders` và cách đọc header khi key không tồn tại hoặc value bằng `null`.
2. Hiểu kết quả khi sử dụng `MessageBuilder.setHeader(name, null)` và sự khác nhau giữa `get` với `containsKey`.
3. Phân biệt trường hợp **thiếu header**, **header có chuỗi rỗng**, **sai kiểu** và **không có mapping**.
4. Chọn hành vi rõ ràng cho header bắt buộc và tùy chọn: fallback, reject/discard hoặc exception.
5. Tích hợp policy Java thuần vào `@Router`, làm việc với `@Header(required = false)` và hiểu giới hạn của `HeaderValueRouter`.
6. Kiểm thử bằng JUnit cả logic quyết định lẫn đường đi qua các channel Spring Integration.
7. Bảo toàn metadata như `traceId`/`correlationId` và tránh tin header do client tự khai báo.

## 2. Vì sao header có thể thiếu?

Một message có hai phần: payload là dữ liệu chính, headers là metadata. Ví dụ cùng một payload `OrderCreated` có thể đến từ nhiều nguồn:

~~~text
Nguồn A (HTTP Gateway)
payload: OrderCreated(orderId=ORDER-1001)
headers: region=NORTH, tenantId=shop-a, traceId=trace-1

Nguồn B (message broker)
payload: OrderCreated(orderId=ORDER-1002)
headers: tenantId=shop-b, traceId=trace-2

Nguồn C (chương trình cũ)
payload: OrderCreated(orderId=ORDER-1003)
headers: region="", traceId=trace-3
~~~

Đối với router theo `region`, nguồn A có giá trị hợp lệ; nguồn B **không mang header region**; nguồn C có **key region** nhưng value là chuỗi rỗng. Cả B và C không xác định được khu vực, song có thể cần cách xử lý **khác nhau**:

- Nếu khu vực là thông tin **tùy chọn**, message không có `region` có thể đi đến `orders.default`.
- Nếu có `region` mà chuỗi rỗng, dữ liệu thể hiện không đúng hợp đồng; có thể cần `orders.invalid`.
- Nếu `region` bắt buộc cho tính toán thuế hoặc phân vùng tenant, **không nên dùng fallback**. Message phải bị từ chối hoặc báo lỗi có cấu trúc.

### Sơ đồ lựa chọn

~~~mermaid
flowchart TD
    IN["Message đầu vào"] --> H{"Có giá trị region?"}
    H -->|Không có / null| OPT{"Region có tùy chọn?"}
    OPT -->|Có| DEF["orders.default"]
    OPT -->|Không| REJ["orders.invalid / error flow"]
    H -->|Có| TYPE{"Đúng kiểu String?"}
    TYPE -->|Không| REJ
    TYPE -->|Có| VALUE{"Giá trị sau trim?"}
    VALUE -->|NORTH| N["orders.north"]
    VALUE -->|SOUTH| S["orders.south"]
    VALUE -->|Rỗng / unknown| REJ
~~~

**Fallback là một quyết định nghiệp vụ**, không nên dùng làm cách che giấu dữ liệu sai hoặc lỗi cấu hình.

## 3. Những trạng thái cần phân biệt

Trong Java, `MessageHeaders` triển khai giao diện đọc gần với `Map<String, Object>`. Hãy quan sát trạng thái của key `region`:

| Trạng thái | `headers.get("region")` | `headers.containsKey("region")` | Ý nghĩa |
|---|---|---|---|
| Key không tồn tại | `null` | `false` | Thiếu metadata |
| Key tồn tại và value là `null` trong một map đặc biệt | `null` | `true` | Key có mặt nhưng không có giá trị; ít gặp qua builder thông thường |
| Value là `""` | `""` | `true` | Có header nhưng chuỗi rỗng |
| Value là `"   "` | `"   "` | `true` | Chỉ có khoảng trắng |
| Value là `"NORTH"` | `"NORTH"` | `true` | Giá trị hợp lệ theo ví dụ |
| Value là `"north"` | `"north"` | `true` | Cần quyết định có cho chuẩn hóa hay không |
| Value là `"WEST"` | `"WEST"` | `true` | Giá trị không nằm trong danh sách được hỗ trợ |
| Value là `42` (`Integer`) | `42` | `true` | Sai kiểu so với hợp đồng String |
| Value là `"null"` (chuỗi) | `"null"` | `true` | **Không phải** giá trị Java `null` |

Điểm mấu chốt:

> `get("region") == null` không tự chứng minh key có mặt hay không. Nếu thật sự cần phân biệt, hãy dùng `containsKey("region")`. Với cách xây dựng message thông thường, setter của builder coi value `null` là thao tác loại header.

### 3.1. `MessageBuilder.setHeader(..., null)`

Ví dụ:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> message = MessageBuilder
        .withPayload("ORDER-1001")
        .setHeader("region", "NORTH")
        .setHeader("region", null)
        .build();

System.out.println(message.getHeaders().get("region")); // null
System.out.println(message.getHeaders().containsKey("region")); // false
~~~

Trong `MessageBuilder` chuẩn của Spring Messaging, đặt `null` qua `setHeader` có nghĩa là **loại bỏ header**, không mang ý nghĩa “gán giá trị null rồi vẫn giữ key”. Đây là lý do một chương trình đã gắn header có thể vô tình làm mất nó trong bước enrich/transform.

Ví dụ, code sau dễ bị hiểu nhầm:

~~~java
Message<String> changed = MessageBuilder.fromMessage(message)
        .setHeader("region", lookUpRegionOrNull())
        .build();
~~~

Nếu `lookUpRegionOrNull()` trả `null`, `region` sẽ không còn ở message mới. Khi muốn giữ region cũ nếu không tìm được giá trị thay thế, **hãy kiểm tra null trước khi gọi `setHeader`**:

~~~java
MessageBuilder<String> builder = MessageBuilder.fromMessage(message);
String newRegion = lookUpRegionOrNull();

if (newRegion != null) {
    builder.setHeader("region", newRegion);
}

Message<String> updated = builder.build();
~~~

Đoạn này là ví dụ logic minh họa; `lookUpRegionOrNull()` là hàm của ứng dụng. Nên tránh thực hiện lookup mạng/DB trực tiếp trong router; đặt enrichment tại endpoint chuyên trách.

### 3.2. Vì sao header null không giống chuỗi "null"?

~~~java
Message<String> a = MessageBuilder.withPayload("A")
        .setHeader("region", null)
        .build();

Message<String> b = MessageBuilder.withPayload("B")
        .setHeader("region", "null")
        .build();
~~~

Trong `a`, header `region` vắng mặt. Trong `b`, header là chuỗi gồm bốn ký tự `n-u-l-l`; nếu router không kiểm tra danh sách giá trị được chấp nhận, rất có thể chuỗi này bị hiểu nhầm như một tên channel. Luôn phân biệt kiểu và giá trị sau khi decode.

### 3.3. Không sửa trực tiếp MessageHeaders để “vá” header thiếu

~~~java
// Sai: cấu trúc MessageHeaders là read-only.
message.getHeaders().put("region", "NORTH");
~~~

Thao tác này ném `UnsupportedOperationException` trong cách sử dụng `MessageHeaders` thông thường. Khi cần thay đổi metadata, hãy tạo **message mới** bằng `MessageBuilder` hoặc dùng **Header Enricher** trong flow.

## 4. Những hệ quả của `@Header` khi tham số bắt buộc

Spring hỗ trợ binding header vào tham số phương thức được gắn `@Header`:

~~~java
import org.springframework.integration.annotation.Router;
import org.springframework.messaging.handler.annotation.Header;

@Router(inputChannel = "orders.route")
public String route(@Header("region") String region) {
    return "NORTH".equals(region)
            ? "orders.north"
            : "orders.south";
}
~~~

Mặc định, `@Header` yêu cầu header có mặt. Khi không có `region`, **lỗi binding tham số có thể xảy ra trước khi thân phương thức `route` được thực thi**. Vì vậy, lời gọi `"NORTH".equals(region)` không giải quyết được vấn đề thiếu header nếu framework không truyền được tham số vào phương thức.

### 4.1. Chấp nhận thiếu header với `required = false`

~~~java
@Router(inputChannel = "orders.route")
public String route(
        @Header(value = "region", required = false)
        String region) {

    if (region == null) {
        return "orders.default";
    }

    return switch (region.trim().toUpperCase(
            java.util.Locale.ROOT)) {
        case "NORTH" -> "orders.north";
        case "SOUTH" -> "orders.south";
        default -> "orders.invalid";
    };
}
~~~

Đây là cách phù hợp cho **header tùy chọn**. Tuy nhiên, nó chưa phân biệt kiểu header không phải `String` trước khi framework binding tham số. Trong hệ thống nhận metadata từ nguồn ngoài, một cách chặt chẽ hơn là để router nhận `Message<?>` rồi tự kiểm tra `Object`, như mục kế tiếp.

Lưu ý: đoạn `@Router` này là ví dụ **thay thế** cho phương thức ở trên. Một input channel chỉ nên có topology được thiết kế rõ; không đăng ký hai router cạnh tranh xử lý cùng `DirectChannel` chỉ vì sao chép cả hai ví dụ.

### 4.2. Khi nào nên dùng `Message<?>` thay vì `@Header`?

| Nhu cầu | Cách nhận tham số phù hợp |
|---|---|
| Header bắt buộc, kiểu đã được đảm bảo | `@Header("region") String region` |
| Header tùy chọn, vắng mặt là hợp lệ | `@Header(value = "region", required = false) String region` |
| Cần tự phân biệt absent/null/blank/wrong-type | `Message<?>` và `getHeaders()` |
| Cần nhiều headers đã xác thực | `Message<?>`, hoặc một typed context được tạo trước router |
| Cần logic nghiệp vụ lớn, kiểm thử thuần | Tách `RoutingPolicy`, để method router chỉ làm adapter |

Điểm quan trọng là **không dùng `required = false` chỉ để che một header thực tế là bắt buộc** cho bảo mật hoặc xử lý nghiệp vụ.

## 5. Viết một chính sách route thuần

Thay vì đặt nhiều điều kiện rời rạc trong annotation, hãy biểu diễn cách xử lý region bằng một hàm Java thuần.

### 5.1. Hợp đồng chính sách

Trong ví dụ này, `region` là tùy chọn, nhưng nếu đã được khai báo thì phải hợp lệ:

- **Thiếu hoặc null:** `DEFAULT` — áp dụng khi message không có thông tin khu vực.
- **`"NORTH"`:** `NORTH`.
- **`"SOUTH"`:** `SOUTH`.
- **Rỗng, toàn khoảng trắng, sai kiểu, tên khu vực lạ:** `INVALID`.

~~~java
public enum RegionDecision {
    NORTH,
    SOUTH,
    DEFAULT,
    INVALID
}
~~~

### 5.2. Logic thuần, không phụ thuộc Spring

~~~java
import java.util.Locale;

public final class RegionRoutingPolicy {

    public RegionDecision decide(Object regionHeader) {
        if (regionHeader == null) {
            return RegionDecision.DEFAULT;
        }

        if (!(regionHeader instanceof String region)) {
            return RegionDecision.INVALID;
        }

        String normalized = region.trim()
                .toUpperCase(Locale.ROOT);

        return switch (normalized) {
            case "NORTH" -> RegionDecision.NORTH;
            case "SOUTH" -> RegionDecision.SOUTH;
            default -> RegionDecision.INVALID;
        };
    }
}
~~~

Hàm `decide` có các tính chất hữu ích:

- Nhận một giá trị đầu vào, không đọc trạng thái ẩn.
- Không sửa `MessageHeaders`, không gửi message và không gọi HTTP/DB.
- Với cùng một `Object` có giá trị bất biến, trả cùng quyết định.
- Chỉ cho phép hai giá trị region đã biết, nên chuỗi `"orders.admin"` từ bên ngoài không thể trở thành tên channel nội bộ.
- Ngữ nghĩa **missing** được xác định rõ. Một `String` rỗng không bị coi là missing.

Với một policy không cần phân biệt map key có mặt nhưng mang `null`, chỉ cần truyền `headers.get("region")` vào hàm trên. Nếu hệ thống có trường hợp đặc biệt cần phân biệt **key có mặt với value null** và **key vắng mặt**, mở rộng input của policy thành `HeaderSnapshot(boolean present, Object value)` thay vì chỉ truyền một giá trị.

### 5.3. Khi có trường hợp null nhưng business khác missing

~~~java
public record HeaderSnapshot(boolean present, Object value) {}

public HeaderSnapshot inspectRegion(
        org.springframework.messaging.Message<?> message) {
    var headers = message.getHeaders();
    return new HeaderSnapshot(
            headers.containsKey("region"),
            headers.get("region"));
}
~~~

Đoạn này giúp phân biệt theo hợp đồng `Map`:

- `present=false, value=null`: key không có.
- `present=true, value=null`: key có nhưng giá trị null, nếu một cơ chế tạo headers cho phép tình huống đó.
- `present=true, value=""`: header có chuỗi rỗng.

Trong luồng dùng `MessageBuilder.setHeader(..., null)` tiêu chuẩn, trường hợp thứ hai không phải cách biểu diễn thông thường. Đừng tạo nhiều trạng thái khó hiểu nếu nghiệp vụ không cần chúng.

## 6. Kết nối policy với `@Router` và channel

Một endpoint nhỏ gọi policy và ánh xạ kết quả sang channel đã khai báo:

~~~java
import org.springframework.integration.annotation.Router;
import org.springframework.messaging.Message;

public final class RegionMessageRouter {

    private final RegionRoutingPolicy policy;

    public RegionMessageRouter(RegionRoutingPolicy policy) {
        this.policy = policy;
    }

    @Router(inputChannel = "orders.route")
    public String destination(Message<?> message) {
        Object region = message.getHeaders().get("region");

        return switch (policy.decide(region)) {
            case NORTH -> "orders.north";
            case SOUTH -> "orders.south";
            case DEFAULT -> "orders.default";
            case INVALID -> "orders.invalid";
        };
    }
}
~~~

Router nhận **cả message**, nên thiếu header không gây lỗi binding `@Header(required=true)`. Code cũng không ép kiểu mù từ `Object` sang `String`: nếu giá trị sai kiểu, policy chuyển sang `INVALID` có chủ đích.

### 6.1. Khai báo các channel

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class RegionRoutingConfiguration {

    @Bean(name = "orders.route")
    public MessageChannel incoming() {
        return new DirectChannel();
    }

    @Bean(name = "orders.north")
    public PollableChannel north() {
        return new QueueChannel();
    }

    @Bean(name = "orders.south")
    public PollableChannel south() {
        return new QueueChannel();
    }

    @Bean(name = "orders.default")
    public PollableChannel fallback() {
        return new QueueChannel();
    }

    @Bean(name = "orders.invalid")
    public PollableChannel invalid() {
        return new QueueChannel();
    }

    @Bean
    public RegionRoutingPolicy regionRoutingPolicy() {
        return new RegionRoutingPolicy();
    }

    @Bean
    public RegionMessageRouter regionMessageRouter(
            RegionRoutingPolicy policy) {
        return new RegionMessageRouter(policy);
    }
}
~~~

Ở đây, `QueueChannel` giúp dễ quan sát kết quả trong bài tập và JUnit. Trong hệ thống thực, mỗi channel thường nối đến một handler hoặc flow xử lý riêng; `QueueChannel` mặc định không cung cấp lưu bền vững qua restart.

### 6.2. Gửi message có và không có header

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> known = MessageBuilder
        .withPayload("ORDER-1001")
        .setHeader("region", "NORTH")
        .setHeader("traceId", "trace-1001")
        .build();

Message<String> missing = MessageBuilder
        .withPayload("ORDER-1002")
        .setHeader("traceId", "trace-1002")
        .build();

Message<String> blank = MessageBuilder
        .withPayload("ORDER-1003")
        .setHeader("region", "  ")
        .build();
~~~

Khi gửi ba message vào `orders.route`, topology ví dụ định tuyến lần lượt đến `orders.north`, `orders.default`, `orders.invalid`. Router chỉ chuyển message, do đó payload và headers như `traceId` tiếp tục đi theo message gốc; không cần tự tạo message mới chỉ để đổi nhánh.

**Cần lưu ý:** channel `orders.invalid` trong ví dụ là đường xử lý **dữ liệu không hợp lệ**, không nhất thiết là Spring Integration `errorChannel`. Một nhánh invalid được định tuyến bình thường và một exception do endpoint ném ra có ý nghĩa khác nhau.

## 7. Dùng `HeaderValueRouter` có sẵn

Spring Integration cung cấp `HeaderValueRouter`, một router chuyên dùng giá trị của **một header** để chọn channel đích. Nó hữu ích khi chỉ cần ánh xạ header → channel, không có những phân biệt nghiệp vụ phức tạp.

### 7.1. Cấu hình mapping

Ví dụ cấu hình Java cho object router:

~~~java
import org.springframework.integration.router.HeaderValueRouter;

public HeaderValueRouter createRouter() {
    HeaderValueRouter router =
            new HeaderValueRouter("region");

    router.setChannelMapping("NORTH", "orders.north");
    router.setChannelMapping("SOUTH", "orders.south");
    router.setDefaultOutputChannelName("orders.default");

    return router;
}
~~~

Để router thực sự nhận message, cần gắn object này vào một **endpoint/IntegrationFlow** và khai báo các channel đích. Đoạn trên chỉ trình bày cấu hình mapping, chưa tự tạo một flow hoàn chỉnh.

Có thể biểu diễn cùng ý tưởng trong **Java DSL**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow simpleHeaderRoute() {
    return IntegrationFlow.from("orders.simple.input")
            .route("headers['region']", spec -> spec
                    .channelMapping("NORTH", "orders.north")
                    .channelMapping("SOUTH", "orders.south")
                    .defaultOutputChannel("orders.default"))
            .get();
}
~~~

Ví dụ này minh họa routing biểu thức khi header đã được chuẩn hóa thành `"NORTH"` hoặc `"SOUTH"`. Cần có bean `orders.simple.input` và các channel đích tương ứng; tên channel trong ví dụ là hợp đồng của flow.

### 7.2. Default output giải quyết vấn đề gì?

Router dựa trên mapping cần cách ứng xử khi không xác định được channel đích. `defaultOutputChannel` có thể đóng vai trò nhánh dự phòng cho những trường hợp **không có route phù hợp**, tùy chính xác cấu hình router và tính năng phiên bản Spring Integration.

Cần đặc biệt chú ý: một fallback chung thường **không phân biệt** giữa header vắng mặt và header có giá trị không có mapping. Nếu business muốn:

- **Thiếu header** → `orders.default`;
- **Header sai kiểu hoặc giá trị ngoài danh sách** → `orders.invalid`;

thì chính sách `RegionRoutingPolicy` kết hợp `@Router` ở mục 5–6 diễn đạt yêu cầu chính xác hơn. Đừng mặc định rằng cấu hình `defaultOutputChannel` sẽ tự phân loại các trường hợp này cho bạn.

### 7.3. `resolutionRequired` và không có channel đích

Các router của Spring Integration có chính sách quyết định việc **không resolve được kênh** là lỗi hay có thể bỏ qua. Khi cần bảo đảm message không âm thầm mất, hãy xác minh cách cấu hình `resolutionRequired`, default output và channel mapping trong chính phiên bản thư viện bạn đang dùng.

Phân biệt ba loại tình huống:

| Tình huống | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Header vắng mặt | Producer không gửi metadata tùy chọn | Fallback **nếu hợp đồng cho phép** |
| Header có giá trị nhưng không có mapping | Ví dụ `WEST` hoặc phiên bản schema mới | Reject, quarantine, hoặc cập nhật mapping theo chính sách |
| Router trả tên channel không tồn tại | Sai tên bean hoặc cấu hình thiếu | Báo lỗi cấu hình và sửa deployment; không âm thầm fallback |

Với message bắt buộc phải xử lý, hãy có test đảm bảo mọi nhánh hợp lệ resolve được channel và không bị drop khi thiếu mapping.

## 8. Header bắt buộc: reject hoặc exception, không fallback mù

Không phải header nào cũng được phép thiếu. Ví dụ `tenantId` ảnh hưởng tới phân quyền dữ liệu và `eventType` có thể quyết định validator/schema áp dụng. Nếu thiếu, đưa message sang `orders.default` có thể tạo lỗi an toàn hoặc nghiệp vụ.

### 8.1. Policy cho header bắt buộc

~~~java
public enum TenantRoute {
    TENANT_A,
    TENANT_B,
    REJECT
}

public TenantRoute tenantRoute(Object trustedTenantHeader) {
    if (!(trustedTenantHeader instanceof String tenant)) {
        return TenantRoute.REJECT;
    }

    return switch (tenant) {
        case "tenant-a" -> TenantRoute.TENANT_A;
        case "tenant-b" -> TenantRoute.TENANT_B;
        default -> TenantRoute.REJECT;
    };
}
~~~

Đây là ví dụ hàm Java thuần: thiếu, null, blank, sai kiểu hoặc tenant không được hỗ trợ đều bị từ chối. Không suy rằng tên tenant trong header là bằng chứng quyền truy cập; tầng authentication/authorization phải xác minh trước, và router chỉ được dùng giá trị **đã tin cậy**.

### 8.2. Filter trước Router

Nếu hệ thống muốn tách validation khỏi routing:

~~~mermaid
flowchart LR
    IN["Inbound adapter"] --> V{"Validation / authorization"}
    V -->|Fail| REJ["Reject response / discard channel"]
    V -->|Pass| E["Header enrichment"]
    E --> ROUTER{"Header-Based Router"}
    ROUTER --> A["Channel A"]
    ROUTER --> B["Channel B"]
~~~

Có thể dùng `Filter` để loại message thiếu header bắt buộc, kèm `discardChannel` để quan sát hoặc phản hồi. Nếu cần báo lỗi trực tiếp cho Gateway, có thể chọn ném exception và xử lý qua error flow phù hợp. Việc Filter reject bình thường khác với exception:

- **Filter với discard channel:** đưa message bị từ chối đến một channel xử lý riêng, nếu được cấu hình.
- **Exception:** có thể quay về caller trong luồng đồng bộ hoặc đi qua cơ chế error handling ở luồng bất đồng bộ.
- **Router trả `orders.invalid`:** là một route bình thường, hữu ích nếu cần giữ payload/headers gốc để phân loại lỗi tại handler chuyên trách.

Chọn một cách phù hợp với hợp đồng, tránh gửi **cùng một lỗi** tới cả discard và error flow rồi tính hai lần.

## 9. Những chi tiết nhỏ dễ gây lỗi

### 9.1. Tên header có phân biệt chữ hoa/thường

`region` và `Region` là hai key khác nhau theo hợp đồng `Map`. Nếu một inbound adapter hoặc thư viện bên ngoài đổi tên header, router có thể thấy `null` dù người vận hành tin rằng metadata tồn tại.

~~~java
var headers = message.getHeaders();

Object a = headers.get("region");
Object b = headers.get("Region");

// Hai khóa khác nhau; không nên trộn tên tùy tiện.
~~~

Hãy định nghĩa header names thành hằng số trong ứng dụng, dùng header mapper/normalizer ở ranh giới giao thức và kiểm thử adapter thực tế. Với HTTP headers, quy tắc case-insensitive ở giao thức HTTP **không tự cho phép** tùy ý xử lý các key trong `MessageHeaders` như cùng một key.

### 9.2. Chuỗi rỗng, khoảng trắng và giá trị mặc định

Một số đoạn code coi mọi chuỗi không khớp là `default`:

~~~java
// Không nên khi dữ liệu rỗng hoặc sai phải bị reject:
return "NORTH".equals(region) ? "orders.north" : "orders.default";
~~~

Cách này gửi cả `"SOUTH"`, `""`, `"WEST"` và có thể cả `null` về cùng một nhánh, che giấu lỗi dữ liệu. Nên viết bảng quyết định rõ ràng.

### 9.3. Không ép kiểu mù

~~~java
// Dễ gây ClassCastException nếu header là Integer:
String region = (String) message.getHeaders().get("region");
~~~

Nếu header có thể đến từ producer hoặc adapter không đồng nhất, dùng `instanceof String` rồi xử lý không hợp lệ. Không dùng `String.valueOf(raw)` nếu điều đó khiến `null` thành literal `"null"` hoặc số thành chuỗi trông có vẻ hợp lệ.

### 9.4. Giá trị header null không phải payload null

Thông thường một message phải có payload hợp lệ; việc metadata `region` vắng mặt không đồng nghĩa payload vắng mặt. Luồng xử lý nên phân biệt lỗi decode/payload với lỗi header routing.

### 9.5. Header chứa object mutable

`MessageHeaders` có cấu trúc read-only trong message đã tạo, nhưng nếu giá trị header là `List`/`Map` mutable thì nội dung object vẫn có thể thay đổi qua tham chiếu. Hãy dùng chuỗi/enum/record bất biến cho routing key; nếu cần collection, tạo snapshot phòng vệ. Điều này quan trọng trong `PublishSubscribeChannel` và luồng executor bất đồng bộ.

### 9.6. Không dùng client header làm tên channel

~~~java
// Không an toàn khi đích được quyết định hoàn toàn bởi client:
return message.getHeaders().get("nextChannel", String.class);
~~~

Một caller có thể chọn tên channel nội bộ ngoài phạm vi được phép. Thay vào đó, ánh xạ **giá trị đã được xác thực và nằm trong whitelist** sang tập channel đích cố định.

## 10. Fallback, reject và báo lỗi: bảng quyết định

Trước khi triển khai, đội ngũ nên viết hợp đồng cho từng header.

| Tình huống | `region` tùy chọn | `tenantId` bắt buộc | `messageType` bắt buộc |
|---|---|---|---|
| Header vắng mặt | `orders.default` | Reject/authorization error | Reject/unsupported message |
| `null` sau khi builder loại header | Coi như vắng mặt | Reject | Reject |
| Chuỗi `""` hoặc trắng | Invalid | Reject | Reject |
| Sai kiểu | Invalid | Reject | Reject |
| Giá trị hợp lệ | Route theo mapping | Route tenant đã xác thực | Chọn handler theo schema |
| Giá trị không biết | Invalid/quarantine | Reject | Reject/quarantine |
| Channel đích không tồn tại | Lỗi cấu hình | Lỗi cấu hình | Lỗi cấu hình |

Không có một chính sách đúng cho mọi ứng dụng. Một header có thể là optional ở luồng thông báo nhưng bắt buộc ở luồng thanh toán. **Điều cần bảo đảm là chính sách được viết rõ, nhất quán và kiểm thử trước khi chạy production.**

### 10.1. Trường hợp không có subscriber/handler phía sau

Router trả được tên channel không có nghĩa downstream đã có consumer hoặc công việc đã hoàn tất. Tùy loại channel và topology, message có thể không được tiêu thụ hoặc gây lỗi khi gửi. Hãy kiểm thử endpoint thực tế, subscriber count với `SubscribableChannel` khi cần, và cấu hình nhận lỗi theo yêu cầu. Giá trị `send()==true` không chứng minh thành công nghiệp vụ trong toàn flow, đặc biệt khi có bất đồng bộ.

## 11. Kiểm thử policy bằng JUnit 5

Hàm thuần ở mục 5 có thể kiểm thử mà không khởi tạo Spring application context.

### 11.1. Kiểm thử từng loại giá trị

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class RegionRoutingPolicyTest {

    private final RegionRoutingPolicy policy =
            new RegionRoutingPolicy();

    static Stream<Arguments> values() {
        return Stream.of(
                Arguments.of("NORTH", RegionDecision.NORTH),
                Arguments.of("north", RegionDecision.NORTH),
                Arguments.of("  south  ", RegionDecision.SOUTH),
                Arguments.of("", RegionDecision.INVALID),
                Arguments.of("  ", RegionDecision.INVALID),
                Arguments.of("WEST", RegionDecision.INVALID),
                Arguments.of("null", RegionDecision.INVALID),
                Arguments.of(42, RegionDecision.INVALID));
    }

    @ParameterizedTest
    @MethodSource("values")
    void handlesSupportedAndUnsupportedValues(
            Object header, RegionDecision expected) {
        assertEquals(expected, policy.decide(header));
    }

    @Test
    void missingHeaderUsesDefault() {
        assertEquals(RegionDecision.DEFAULT, policy.decide(null));
    }
}
~~~

Đây là một test đọc rõ **ngữ nghĩa**: chỉ null/missing mới đến default, trong khi header có giá trị nhưng không đúng được đưa vào invalid. Test cả `"null"` giúp chống lỗi chuyển đổi chuỗi ngoài ý muốn.

### 11.2. Kiểm thử `setHeader(..., null)`

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class NullHeaderBuilderTest {

    @Test
    void assigningNullRemovesHeader() {
        Message<String> input = MessageBuilder
                .withPayload("ORDER-1001")
                .setHeader("region", "NORTH")
                .build();

        Message<String> output = MessageBuilder
                .fromMessage(input)
                .setHeader("region", null)
                .build();

        assertTrue(input.getHeaders().containsKey("region"));
        assertFalse(output.getHeaders().containsKey("region"));
        assertNull(output.getHeaders().get("region"));
    }
}
~~~

Test này còn kiểm tra rằng thao tác tạo message mới không sửa metadata của message ban đầu.

## 12. Kiểm thử flow thực với Spring Integration

Unit test ở trên chưa chứng minh channel đã được Spring resolve đúng. Cần gửi message qua `orders.route` và kiểm tra output queue. Ví dụ dùng Java 17+, JUnit Jupiter 5, Spring Test và `spring-integration-core`, dựa trên `RegionRoutingConfiguration` ở mục 6.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = RegionRoutingConfiguration.class)
class RegionRoutingFlowTest {

    @Autowired
    @Qualifier("orders.route")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.north")
    PollableChannel north;

    @Autowired
    @Qualifier("orders.south")
    PollableChannel south;

    @Autowired
    @Qualifier("orders.default")
    PollableChannel fallback;

    @Autowired
    @Qualifier("orders.invalid")
    PollableChannel invalid;

    @Test
    void knownHeaderGoesToNorth() {
        assertTrue(input.send(MessageBuilder
                .withPayload("ORDER-1001")
                .setHeader("region", "NORTH")
                .setHeader("traceId", "trace-1001")
                .build()));

        Message<?> received = north.receive(1000);

        assertNotNull(received);
        assertEquals("ORDER-1001", received.getPayload());
        assertEquals("trace-1001",
                received.getHeaders().get("traceId"));

        assertNull(south.receive(0));
        assertNull(fallback.receive(0));
        assertNull(invalid.receive(0));
    }

    @Test
    void missingHeaderGoesToFallback() {
        assertTrue(input.send(MessageBuilder
                .withPayload("ORDER-1002")
                .setHeader("traceId", "trace-1002")
                .build()));

        Message<?> received = fallback.receive(1000);

        assertNotNull(received);
        assertEquals("ORDER-1002", received.getPayload());
        assertEquals("trace-1002",
                received.getHeaders().get("traceId"));

        assertNull(north.receive(0));
        assertNull(south.receive(0));
        assertNull(invalid.receive(0));
    }

    @Test
    void blankHeaderGoesToInvalid() {
        assertTrue(input.send(MessageBuilder
                .withPayload("ORDER-1003")
                .setHeader("region", "  ")
                .build()));

        assertNotNull(invalid.receive(1000));
        assertNull(north.receive(0));
        assertNull(south.receive(0));
        assertNull(fallback.receive(0));
    }

    @Test
    void wrongTypeGoesToInvalid() {
        assertTrue(input.send(MessageBuilder
                .withPayload("ORDER-1004")
                .setHeader("region", 42)
                .build()));

        assertNotNull(invalid.receive(1000));
        assertNull(north.receive(0));
        assertNull(south.receive(0));
        assertNull(fallback.receive(0));
    }
}
~~~

Tất cả output channel ở cấu hình được sử dụng là `QueueChannel`, nên trong test đồng bộ có thể `receive(...)` để quan sát route. Test xác minh:

- Header vắng mặt **không làm phương thức @Router lỗi binding**.
- Null/absent được xử lý có chủ đích theo policy.
- Một giá trị blank hoặc sai kiểu không bị fallback nhầm.
- `traceId` còn nguyên trên message được chuyển qua router.
- Message chỉ đi đến **một** nhánh mong muốn.

Nếu bật xử lý song song hoặc đổi topology, cần đảm bảo các test có context/queue tách biệt để tránh tranh chấp message. Nếu muốn kiểm thử channel thực sự có handler, thay `QueueChannel` bằng handler có fake repository/counter và kiểm chứng side effect phù hợp.

## 13. Kết hợp với các Enterprise Integration Patterns khác

### 13.1. Transformer và Header Enricher

Nếu message đi vào chưa có region nhưng hệ thống có thể suy ra từ payload hoặc nguồn đáng tin, một bước **Header Enricher** trước router có thể gắn `region`:

~~~mermaid
flowchart LR
    IN["Inbound message"] --> V["Validate"]
    V --> E["Trusted Header Enricher"]
    E --> R{"Header-Based Router"}
    R --> A["NORTH"]
    R --> B["SOUTH"]
    R --> D["Fallback / Reject"]
~~~

Nếu Transformer trả một `Message<?>` hoàn chỉnh, phải chủ động giữ các header cần thiết. Transformer trả payload thường được framework truyền headers đầu vào theo quy tắc endpoint. Vì vậy, khi một header “đột nhiên mất” trước router, kiểm tra bước transform/enrich ngay trước đó cùng cấu hình header propagation.

### 13.2. Filter và Router

Filter trả lời “message hợp lệ hay cần bỏ?”, còn Router trả lời “message đi nhánh nào?”. Nếu `region` bắt buộc, Filter có thể chuyển message thiếu region sang `orders.rejected` trước khi router chạy. Nếu region tùy chọn, Router có thể chọn `orders.default`.

Không dùng Filter để phân biệt hàng loạt nhánh nghiệp vụ phức tạp nếu Router với policy sẽ rõ ràng hơn; cũng không dùng Router để thay toàn bộ việc xác thực/validation.

### 13.3. Splitter và Aggregator

Sau một `Splitter`, mỗi phần của đơn hàng có thể cần thông tin `correlationId`, `sequenceNumber`, `sequenceSize` để Aggregator gom đúng nhóm. Khi tạo message mới trên từng nhánh, cần bảo toàn metadata này theo hợp đồng. Header `region` phục vụ routing **không mặc nhiên thay cho correlation ID**.

Nếu các phần của cùng một đơn bị thiếu region, cần quyết định có chấp nhận fallback từng phần hay reject cả nhóm. Nếu Aggregator chờ đủ số lượng part nhưng một nhánh bị discard, nhóm có thể không bao giờ hoàn tất theo release strategy hiện tại; cần timeout và chính sách incomplete group.

### 13.4. Gateway, retry và error channel

Một Gateway có thể chờ reply, vì vậy fallback/reject phải tạo kết quả đúng hợp đồng request–reply hoặc ném exception được xử lý rõ ràng; không gửi vào queue rồi để caller chờ vô hạn.

Trong xử lý đồng bộ, exception ở router hoặc handler có thể nổi về caller. Trong luồng bất đồng bộ, lỗi thường đi qua error handling theo cấu hình `errorChannel`. Không coi một route invalid là `ErrorMessage` tự động; đó là message được định tuyến đến channel invalid như những route khác.

Lỗi thiếu header bắt buộc là lỗi **dữ liệu cố định**: retry cùng message mà không có bước enrich hợp lệ thường không giúp ích. Retry nên dành cho lỗi tạm thời ở DB, broker, HTTP hoặc những nguyên nhân có thể phục hồi, cùng chính sách idempotency.

### 13.5. Publish–Subscribe khác Header-Based Router

`PublishSubscribeChannel` gửi tới **mọi** subscriber đã đăng ký, trong khi header-based router như ví dụ chọn **một** channel theo metadata. Khi muốn gửi đồng thời audit, analytics và notification, không nên tự chọn sai kiểu channel chỉ vì message có header `eventType`. Có thể đặt Publish–Subscribe ở downstream của route nếu cần fan-out trong từng nhánh.

## 14. Quan sát và chẩn đoán header thiếu

Khi router đưa một message vào fallback, cần đủ dữ liệu để xác định đây là hành vi dự kiến hay lỗi producer.

### 14.1. Những thông tin nên theo dõi

| Trường/metric | Mục đích | Cách dùng an toàn |
|---|---|---|
| `traceId` | Truy vết một lần xử lý | Không dùng giá trị làm metric label có cardinality cao |
| `businessCorrelationId` | Liên kết nhiều bước của nghiệp vụ | Giữ trong log theo chính sách dữ liệu |
| `routeDecision` | Biết message đi NORTH/SOUTH/DEFAULT/INVALID | Có thể làm label cardinality thấp |
| `routeReason` | `MISSING_REGION`, `BLANK_REGION`, `UNSUPPORTED_REGION` | Dùng mã lỗi ổn định |
| `sourceSystem` | Xác định producer nào thiếu metadata | Chỉ dùng nguồn đã được xác minh |
| `schemaVersion` | Phân tích thay đổi hợp đồng | Kiểm tra producer và converter thực tế |

Giữ logic policy thuần bằng cách đặt logging/metrics ở **adapter hoặc handler theo dõi**, không gọi hệ thống quan sát trực tiếp từ `decide`.

### 14.2. Không ghi toàn bộ headers vào log

Headers có thể chứa địa chỉ reply/error, token, dữ liệu người dùng hoặc thông tin nội bộ. Chỉ log những khóa đã kiểm duyệt. Nếu phát hiện client gửi header `nextChannel` hoặc `admin=true`, không bao giờ coi đó là nguồn tin cậy mà không có validation/authorization.

## 15. Những lỗi phổ biến

### Lỗi 1 — Cho rằng `get() == null` có nghĩa “key có nhưng value null”

**Nguyên nhân:** `Map.get` cũng trả null khi key không tồn tại, và `MessageBuilder.setHeader(..., null)` xóa key trong cách dùng thông thường.

**Khắc phục:** dùng `containsKey` nếu hợp đồng cần phân biệt, rồi quyết định rõ cách xử lý null và absent.

### Lỗi 2 — `@Header` mặc định required nhưng code muốn fallback

**Triệu chứng:** method router chưa chạy thì đã có lỗi argument resolution.

**Khắc phục:** dùng `@Header(value = "region", required = false)` hoặc nhận `Message<?>` để đọc header chủ động. Chỉ làm như vậy nếu thiếu region hợp lệ.

### Lỗi 3 — Gộp missing, empty và unsupported vào cùng fallback

**Triệu chứng:** message có `region="WEST"` cũng được xử lý như message chưa có region.

**Khắc phục:** dùng bảng quyết định: chỉ missing hợp lệ mới dùng default; blank/type mismatch/unknown đi reject, trừ khi contract quy định khác.

### Lỗi 4 — Null làm mất header khi copy/enrich

**Triệu chứng:** bước trước router gọi `setHeader("region", null)` và các bước sau không còn region.

**Khắc phục:** không set null nếu muốn giữ giá trị cũ; dùng builder có kiểm tra điều kiện và test propagation.

### Lỗi 5 — Định tuyến trực tiếp theo chuỗi tên channel từ client

**Triệu chứng:** producer có thể gửi đến channel ngoài phạm vi được cho phép.

**Khắc phục:** xác thực nguồn, chuẩn hóa metadata và ánh xạ qua enum/whitelist cố định. Không dùng arbitrary value làm destination.

### Lỗi 6 — Bỏ qua tên key và kiểu dữ liệu

**Triệu chứng:** producer gửi `Region` thay `region`, hoặc gửi `region=7`, khiến router không tìm thấy/không hiểu giá trị.

**Khắc phục:** định nghĩa schema headers chung, kiểm tra tại ingress và viết integration test trên adapter thực tế.

### Lỗi 7 — Fallback biến lỗi cấu hình thành thành công giả

**Triệu chứng:** channel chính bị đổi tên nhưng mọi message đều đi fallback, không ai phát hiện.

**Khắc phục:** kiểm thử tất cả mapping/channel beans, theo dõi số fallback và phân biệt default business với lỗi resolve channel.

### Lỗi 8 — Retry vô hạn cho message thiếu header bắt buộc

**Triệu chứng:** message không có tenantId bị đưa lại cùng router nhiều lần.

**Khắc phục:** phân loại lỗi dữ liệu và lỗi tạm thời; reject/quarantine khi input cố định không thể sửa; chỉ retry nếu bước bổ sung dữ liệu có thể phục hồi.

## 16. Bài tập thực hành: luồng định tuyến theo region

**Bối cảnh:** một ứng dụng nhận sự kiện `OrderCreated` từ HTTP và một broker. Bản tin mới có `region` bằng `NORTH` hoặc `SOUTH`; bản tin cũ có thể không có header. Người gửi cũng có thể gửi chuỗi rỗng hoặc giá trị không hợp lệ.

### 16.1. Yêu cầu

1. Tạo `RegionDecision` và `RegionRoutingPolicy` như mục 5. Quy định `null` → DEFAULT, `NORTH/SOUTH` → nhánh tương ứng, còn lại → INVALID.
2. Viết unit test cho `null`, `""`, `"  "`, `"north"`, `"WEST"`, `"null"` và số nguyên.
3. Dùng `MessageBuilder` tạo message có `region=NORTH` rồi xóa bằng `setHeader("region", null)`; chứng minh `containsKey` chuyển từ true sang false.
4. Viết `@Router` nhận `Message<?>` và ánh xạ enum tới bốn channel tương ứng.
5. Tạo `QueueChannel` cho `orders.north`, `orders.south`, `orders.default` và `orders.invalid`, gửi message và assert đúng nhánh.
6. Bảo toàn `traceId` qua router và kiểm thử cả fallback/reject.
7. Đổi chính sách để `region` bắt buộc: null/absent phải đi reject, không dùng default. So sánh kết quả test trước và sau.
8. Thử thay `@Router` bằng mapping `HeaderValueRouter` cho trường hợp đơn giản; kiểm thử behavior khi header vắng mặt, unknown và sai kiểu trên phiên bản Spring Integration sử dụng.
9. Tình huống nâng cao: header `tenantId` do client gửi khác với tenant lấy từ principal; chỉ dùng tenant **đã xác thực** để route.
10. Tình huống nâng cao: một Gateway gửi request không có region và chờ reply; thiết kế nhánh default/reject trả kết quả có mã lỗi đúng hợp đồng.

### 16.2. Tiêu chí hoàn thành

- Mọi trạng thái của header có kết quả rõ ràng.
- Không có exception do unboxing hoặc ép kiểu mù trong policy.
- Trường hợp thiếu header tùy chọn được fallback đúng; trường hợp sai dữ liệu không bị xử lý nhầm là hợp lệ.
- Message không bị route đến channel được client tự nhập.
- Tests kiểm tra cả **policy Java thuần** và **channel thực**.
- Metadata phục vụ truy vết đi theo message; nhánh lỗi vẫn đủ thông tin quan sát.
- Các lỗi parse/validation và lỗi hạ tầng có đường xử lý khác nhau.

### Câu hỏi tự kiểm tra

1. `MessageHeaders.get("region")` trả null trong những trường hợp nào?
2. `MessageBuilder.setHeader("region", null)` thường dẫn đến điều gì?
3. Vì sao `region=""` không nên mặc nhiên coi là vắng mặt?
4. Khi nào dùng `@Header(required = false)`, khi nào nên nhận `Message<?>`?
5. Nếu `tenantId` bắt buộc cho authorization, có nên dùng default tenant khi thiếu header không?
6. Vì sao `HeaderValueRouter` với default output có thể không đủ để tách missing và unknown?
7. Vì sao `RegionRoutingPolicy` trả enum có lợi hơn trả chuỗi tên channel trực tiếp?
8. Test nào phát hiện router trỏ đến channel bean không tồn tại?
9. Router qua nhánh invalid có tự gửi `ErrorMessage` không?
10. Khi message bị replay, cách nào giúp chính sách route cho cùng input giữ kết quả ổn định?

## 17. Checklist thiết kế

- [ ] Đã mô tả rõ header nào bắt buộc, header nào tùy chọn.
- [ ] Đã phân biệt absent, null, blank, wrong-type và unsupported value.
- [ ] Biết rằng `setHeader(name, null)` thường làm mất key khỏi message mới.
- [ ] Đã chọn chính sách default/reject/error theo hợp đồng nghiệp vụ.
- [ ] Không dùng header chưa được xác thực cho quyền truy cập hoặc chọn channel.
- [ ] Router nhận đúng dạng input để xử lý header thiếu mà không lỗi binding ngoài ý muốn.
- [ ] Mapping nằm trong whitelist; tất cả output channels tồn tại.
- [ ] Có validation/normalization ở nơi tiếp nhận khi cần.
- [ ] Metadata trace/correlation được bảo toàn xuyên route và các bước transform.
- [ ] Error channel và discard/reject channel có ngữ nghĩa tách biệt.
- [ ] Đã có unit test policy, test builder null và integration test về đúng nhánh.
- [ ] Không retry vô hạn với dữ liệu thiếu bắt buộc, sai kiểu hay unknown cố định.
- [ ] Có metric fallback/reject nhưng tránh log secret và dữ liệu cá nhân.

## 18. Tổng kết

**Header-Based Router** giúp luồng xử lý ra quyết định từ metadata mà không cần mọi handler biết cấu trúc payload. Tuy nhiên, một header bị thiếu, bị đặt thành `null`, để chuỗi rỗng hoặc mang kiểu không mong đợi có thể làm kết quả định tuyến sai. Vì vậy, hãy định nghĩa **bảng quyết định rõ ràng cho từng trạng thái header** trước khi chọn kỹ thuật triển khai.

Trong Spring Integration, `get` trả `null` khi key không tồn tại; `containsKey` giúp kiểm tra sự có mặt của key; `MessageBuilder.setHeader(..., null)` thường loại key. `@Header(required=false)` cho phép router nhận trường hợp thiếu; `Message<?>` cho phép kiểm tra type và value chủ động. Khi cần tách default hợp lệ khỏi invalid dữ liệu, một policy thuần trả enum và một `@Router` ánh xạ sang channel giúp kiểm thử nhất quán và dễ bảo trì.

Hãy giữ validation, authorization và header enrichment ở ranh giới thích hợp; chuyển message qua Router với tracing/correlation rõ ràng, xử lý lỗi đúng hợp đồng Gateway/retry/error channel và kiểm thử trên channel thực. Các nguyên tắc này giúp module **SPRING_INTEGRATION_PATTERN** xây dựng những luồng thông điệp ít phụ thuộc, có thể mở rộng và quan sát được.

### Tài liệu tham khảo

- Spring Integration Reference — Router: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration API — HeaderValueRouter: https://docs.spring.io/spring-integration/api/org/springframework/integration/router/HeaderValueRouter.html
- Spring Framework API — MessageHeaders: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html
- Spring Framework API — MessageBuilder: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html
- Spring Framework API — @Header: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Header.html

