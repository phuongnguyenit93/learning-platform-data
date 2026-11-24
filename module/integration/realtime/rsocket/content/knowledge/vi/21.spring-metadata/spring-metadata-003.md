# Trích xuất metadata bằng `MetadataExtractor` và `metadataToExtract`

Trong Spring RSocket, metadata đi cùng payload để cung cấp thông tin định tuyến, xác thực, truy vết hoặc ngữ cảnh nghiệp vụ. Phía nhận cần chuyển vùng byte metadata thành các giá trị mà handler Java có thể sử dụng. `MetadataExtractor` đảm nhiệm việc trích xuất đó; `metadataToExtract(...)` đăng ký cách giải mã một MIME type metadata thành kiểu Java và đặt kết quả vào một message header có tên xác định.

Nhờ cấu hình này, handler có thể nhận metadata bằng `@Header` hoặc đọc toàn bộ message headers mà không phải tự phân tích `ByteBuf` hay Composite Metadata trong từng method. Data payload và metadata vẫn là hai nguồn riêng: payload chứa nội dung nghiệp vụ, còn metadata cung cấp thông tin bổ sung cho tương tác.

## 1. Metadata trong Spring RSocket

Một RSocket `Payload` có hai phần độc lập:

| Thành phần | Mục đích | Ví dụ |
|---|---|---|
| Data | Nội dung chính của request/response. | `OrderQuery`, `DeviceCommand`, JSON hoặc CBOR. |
| Metadata | Thông tin mô tả hoặc điều khiển tương tác. | Route, trace context, tenant, authentication. |

Spring xử lý data bằng message codecs và xử lý metadata bằng cơ chế metadata extraction. Nếu metadata được gửi dưới dạng Composite Metadata, một payload có thể mang nhiều entry, mỗi entry có MIME type và nội dung riêng. Ví dụ một request có thể chứa routing metadata cùng custom trace metadata.

```text
RSocket Payload
┌──────────────────────────┬──────────────────────────────────────────┐
│ Data                     │ Metadata                                 │
│ OrderQuery JSON          │ Composite Metadata                       │
│                          │ ├─ routing MIME -> orders.42.summary      │
│                          │ └─ trace MIME   -> { traceId: "t-123" }   │
└──────────────────────────┴──────────────────────────────────────────┘
```

MIME type cho biết cách diễn giải bytes. Nó không tự chuyển bytes thành object Java; việc đó cần decoder tương ứng. Vì vậy, sender và receiver phải thống nhất MIME type, cấu trúc dữ liệu và codec.

## 2. `MetadataExtractor` làm nhiệm vụ gì?

`org.springframework.messaging.rsocket.MetadataExtractor` là abstraction dùng để chuyển metadata trong một RSocket payload thành một map các message headers. Spring gọi extractor ở bước xử lý message trước khi phân giải tham số của handler.

Luồng xử lý khái quát:

1. Requester tạo payload và gắn metadata, thường qua `RSocketRequester.metadata(...)`.
2. RSocket truyền metadata cùng request đến responder.
3. Spring nhận payload và xác định metadata MIME type của kết nối.
4. `MetadataExtractor` đọc metadata đơn hoặc các entry trong Composite Metadata.
5. Với MIME type đã đăng ký, extractor dùng decoder phù hợp để tạo object Java.
6. Giá trị được đặt vào message headers theo tên đã cấu hình.
7. Handler truy cập giá trị qua `@Header`, `@Headers` hoặc các cơ chế argument resolution tương ứng.

`MetadataExtractor` tách phần giải mã metadata khỏi logic nghiệp vụ. Handler chỉ cần khai báo kiểu dữ liệu và tên header mà nó cần.

## 3. `metadataToExtract(...)` đăng ký mapping MIME type

API `metadataToExtract(...)` được dùng trên registry của `RSocketStrategies` để khai báo ba thông tin:

- **MIME type:** loại metadata mà ứng dụng muốn nhận diện.
- **Target type:** kiểu Java mà decoder sẽ tạo ra.
- **Header name:** tên message header dùng để truy cập object đã giải mã trong handler.

Ví dụ ứng dụng dùng custom MIME type cho trace context:

```java
private static final MimeType TRACE_MIME_TYPE =
    MimeType.valueOf("application/vnd.acme.trace-context+json");

@Bean
RSocketStrategies rsocketStrategies() {
    return RSocketStrategies.builder()
        .metadataExtractorRegistry(registry -> registry.metadataToExtract(
            TRACE_MIME_TYPE,
            TraceContext.class,
            "traceContext"))
        .build();
}
```

Khi metadata entry có MIME type `application/vnd.acme.trace-context+json`, Spring giải mã nội dung thành `TraceContext` và đặt object vào header `traceContext`.

Tên header là tên do ứng dụng chọn. Tên đó không cần trùng MIME type và cũng không phải tên route. Hãy chọn tên rõ nghĩa, nhất quán giữa cấu hình extractor và handler.

## 4. Cấu hình decoder cho custom metadata

Đăng ký `metadataToExtract(...)` cho Spring biết MIME type, kiểu đích và tên header. Để giải mã JSON thành object, `RSocketStrategies` còn cần một decoder hỗ trợ MIME type đó.

```java
@Bean
RSocketStrategies rsocketStrategies() {
    return RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
        .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
        .metadataExtractorRegistry(registry -> registry.metadataToExtract(
            TRACE_MIME_TYPE,
            TraceContext.class,
            "traceContext"))
        .build();
}
```

Các lớp Jackson JSON ở ví dụ thuộc Spring codec. Trong ứng dụng thực tế, kiểm tra các codec mặc định đã được cấu hình để tránh đăng ký trùng hoặc thay đổi thứ tự ưu tiên không mong muốn. Decoder cần hỗ trợ MIME type mà sender thực sự dùng; nếu không, extractor không thể chuyển metadata thành `TraceContext` như mong đợi.

Ở phía requester, encoder tương ứng phải serialize cùng kiểu metadata:

```java
Mono<OrderSummary> summary = requester
    .route("orders.{orderId}.summary", orderId)
    .metadata(new TraceContext("t-123", "checkout"), TRACE_MIME_TYPE)
    .data(new OrderQuery(true))
    .retrieveMono(OrderSummary.class);
```

Requester và responder có thể có cấu hình `RSocketStrategies` riêng, nhưng MIME type và schema metadata phải tương thích. Cấu hình decoder ở server không tự động thêm encoder vào client và ngược lại.

## 5. Đọc metadata trong handler bằng `@Header`

Sau khi extractor đặt object vào header `traceContext`, handler có thể khai báo tham số `@Header` với đúng tên đó:

```java
@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.{orderId}.summary")
    public Mono<OrderSummary> summary(
            @DestinationVariable("orderId") UUID orderId,
            @Header("traceContext") TraceContext traceContext,
            @Payload OrderQuery query) {

        return orderService.findSummary(orderId, query, traceContext);
    }
}
```

Trong method:

- `orderId` đến từ routing metadata và được trích từ route template.
- `traceContext` đến từ custom metadata đã được `MetadataExtractor` giải mã.
- `query` đến từ data payload và được message codec chuyển đổi.

Ba nguồn dữ liệu này có vai trò khác nhau. Không dùng `@DestinationVariable` để đọc custom metadata, và không dùng `@Header` thay cho data payload.

Nếu header là tùy chọn, có thể khai báo `required = false`:

```java
@Header(name = "traceContext", required = false)
TraceContext traceContext
```

Khi metadata là bắt buộc đối với nghiệp vụ, nên giữ yêu cầu rõ ràng và trả lỗi phù hợp nếu thiếu. Không giả định mọi peer đều gửi custom metadata chỉ vì extractor đã được đăng ký.

## 6. Đọc nhiều metadata header bằng `@Headers`

Nếu handler cần kiểm tra nhiều metadata đã được trích xuất, có thể nhận map headers:

```java
@MessageMapping("orders.{orderId}.submit")
public Mono<SubmitResult> submit(
        @DestinationVariable("orderId") UUID orderId,
        @Headers Map<String, Object> headers,
        @Payload SubmitOrder command) {

    TraceContext trace = (TraceContext) headers.get("traceContext");
    String tenant = (String) headers.get("tenantId");

    return orderService.submit(orderId, tenant, command, trace);
}
```

Map headers hữu ích khi handler có nhu cầu linh hoạt hoặc cần quan sát nhiều giá trị. Nếu chỉ cần một metadata cụ thể, `@Header("name")` thường rõ ràng và an toàn kiểu hơn.

Khi dùng `Map<String, Object>`, cần kiểm tra sự tồn tại và kiểu của từng giá trị. Không ép kiểu trực tiếp một header tùy chọn mà chưa xác minh, vì request từ peer có thể không chứa metadata đó hoặc extractor có thể trả một kiểu khác theo cấu hình.

## 7. Composite Metadata và nhiều MIME type

Composite Metadata cho phép một payload mang nhiều metadata entry độc lập. Đây là cách phổ biến khi request cần đồng thời routing metadata và custom metadata.

Ví dụ requester:

```java
Mono<OrderSummary> result = requester
    .route("orders.{orderId}.summary", orderId)
    .metadata(new TraceContext("t-123", "checkout"), TRACE_MIME_TYPE)
    .metadata(new TenantContext("tenant-7"), TENANT_MIME_TYPE)
    .data(new OrderQuery(true))
    .retrieveMono(OrderSummary.class);
```

Mỗi lời gọi `metadata(...)` thêm một metadata entry với MIME type riêng. Server có thể đăng ký cả hai mapping:

```java
@Bean
RSocketStrategies rsocketStrategies() {
    return RSocketStrategies.builder()
        .metadataExtractorRegistry(registry -> {
            registry.metadataToExtract(
                TRACE_MIME_TYPE, TraceContext.class, "traceContext");
            registry.metadataToExtract(
                TENANT_MIME_TYPE, TenantContext.class, "tenantContext");
        })
        .build();
}
```

Handler nhận cả hai object:

```java
@MessageMapping("orders.{orderId}.summary")
public Mono<OrderSummary> summary(
        @DestinationVariable("orderId") UUID orderId,
        @Header("traceContext") TraceContext trace,
        @Header("tenantContext") TenantContext tenant,
        @Payload OrderQuery query) {

    return orderService.findSummary(orderId, tenant, query, trace);
}
```

Để dùng nhiều entry, metadata MIME type của kết nối phải hỗ trợ Composite Metadata và các peer cần thống nhất cấu hình này. Nếu metadata MIME type của kết nối là một định dạng đơn, không thể giả định nhiều entry Composite Metadata sẽ được giải mã đúng.

## 8. Metadata đơn và Composite Metadata

RSocket có thể dùng một metadata MIME type duy nhất cho toàn bộ vùng metadata, hoặc dùng Composite Metadata để chứa nhiều entry. Cần phân biệt MIME type của vùng metadata với MIME type của từng entry:

| Cấu hình | Ý nghĩa |
|---|---|
| Metadata MIME type là `application/json` | Toàn bộ vùng metadata được hiểu như một nội dung JSON đơn theo cấu hình đó. |
| Metadata MIME type là `message/x.rsocket.composite-metadata.v0` | Vùng metadata là danh sách các entry; mỗi entry có MIME type riêng. |
| Một entry trong Composite Metadata có MIME type custom JSON | Chỉ nội dung entry đó được decoder tương ứng giải mã thành object. |

`metadataToExtract(...)` đăng ký mapping theo MIME type của metadata cần trích xuất. Nếu một MIME type xuất hiện dưới dạng entry trong Composite Metadata, extractor có thể tìm entry tương ứng và giải mã theo mapping. Nếu peer gửi định dạng metadata đơn, cách giải mã phụ thuộc MIME type đơn đã thương lượng và cấu hình extractor.

Không nên cấu hình server chờ Composite Metadata nhưng requester lại gửi metadata đơn, hoặc ngược lại. Lỗi ở ranh giới này thường khiến route/header không xuất hiện hoặc metadata decoder không đọc được nội dung.

## 9. Cấu hình RSocketStrategies cho server

Trong Spring Messaging, `RSocketStrategies` tập hợp encoder, decoder, route matcher và metadata extractor registry. Server dùng strategies này khi chuyển RSocket payload thành message cho handler.

Trong ứng dụng Spring không dùng cấu hình tự động, có thể gắn strategies vào `RSocketMessageHandler`:

```java
@Configuration
public class RSocketMetadataConfiguration {

    @Bean
    RSocketStrategies rsocketStrategies() {
        return RSocketStrategies.builder()
            .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
            .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
            .metadataExtractorRegistry(registry -> {
                registry.metadataToExtract(
                    TRACE_MIME_TYPE, TraceContext.class, "traceContext");
            })
            .build();
    }

    @Bean
    RSocketMessageHandler rSocketMessageHandler(RSocketStrategies strategies) {
        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRSocketStrategies(strategies);
        return handler;
    }
}
```

Trong Spring Boot, auto-configuration có thể tạo `RSocketMessageHandler` và `RSocketStrategies` mặc định. Khi đó, hãy tùy chỉnh strategies theo extension point của phiên bản Boot đang dùng hoặc cung cấp bean phù hợp; không đăng ký một `RSocketMessageHandler` thứ hai nếu auto-configuration đã sở hữu handler server.

Mục tiêu là để server handler sử dụng cùng decoder và metadata extraction registry đã khai báo. Cấu hình requester/client cũng cần encoder tương ứng để tạo metadata đúng schema.

## 10. Dùng metadataToExtract với kiểu generic

Metadata có thể là một cấu trúc generic, ví dụ danh sách quyền hoặc danh sách nhãn. Khi target type có generic parameter, dùng `ParameterizedTypeReference` để giữ thông tin kiểu ở runtime:

```java
private static final MimeType TAGS_MIME_TYPE =
    MimeType.valueOf("application/vnd.acme.tags+json");

@Bean
RSocketStrategies rsocketStrategies() {
    return RSocketStrategies.builder()
        .metadataExtractorRegistry(registry -> registry.metadataToExtract(
            TAGS_MIME_TYPE,
            new ParameterizedTypeReference<List<String>>() {},
            "tags"))
        .build();
}
```

Handler có thể nhận:

```java
@MessageMapping("devices.{deviceId}.status")
public Mono<DeviceStatus> status(
        @DestinationVariable("deviceId") UUID deviceId,
        @Header("tags") List<String> tags) {
    return deviceService.getStatus(deviceId, tags);
}
```

Nếu chỉ truyền `List.class`, thông tin phần tử `String` có thể bị mất trong quá trình giải mã. Dùng `ParameterizedTypeReference` khi kiểu generic là một phần của contract metadata.

## 11. Route metadata và custom metadata không giống nhau

Spring RSocket có xử lý riêng routing metadata. Route được dùng để tìm handler `@MessageMapping`, sau đó các biến route có thể được bind bằng `@DestinationVariable`.

Custom metadata như trace context, tenant context hoặc thông tin ứng dụng cần MIME type và decoder/extractor riêng nếu muốn nhận object Java. Không nên đăng ký custom mapping dùng chung MIME type routing cho một kiểu metadata khác.

| Nhu cầu | Cơ chế Spring |
|---|---|
| Chọn handler theo route | `@MessageMapping` và routing metadata |
| Lấy `{orderId}` từ route template | `@DestinationVariable("orderId")` |
| Giải mã custom metadata thành object | `MetadataExtractor` và `metadataToExtract(...)` |
| Đọc object metadata đã giải mã | `@Header("headerName")` |
| Đọc nhiều header | `@Headers Map<String, Object>` |
| Giải mã data payload thành DTO | Message codec và `@Payload` |

Tách rõ các cơ chế này giúp handler dễ hiểu và giảm lỗi do đọc nhầm metadata thành data hoặc route.

## 12. Kiểm tra metadata thiếu, sai MIME type hoặc sai schema

Một request có thể không có metadata tùy chỉnh, dùng MIME type không được đăng ký hoặc gửi nội dung không đúng schema. Ứng dụng nên xác định hành vi mong muốn cho từng trường hợp:

- **Metadata tùy chọn:** handler nhận header không bắt buộc và dùng default phù hợp.
- **Metadata bắt buộc:** từ chối request nếu thiếu hoặc không hợp lệ.
- **MIME type không được hỗ trợ:** không ép giải mã bằng một decoder không tương thích; trả lỗi rõ ràng hoặc bỏ qua theo chính sách đã thống nhất.
- **Schema không tương thích:** version hóa metadata hoặc hỗ trợ nhiều schema trong giai đoạn chuyển đổi.

Ví dụ kiểm tra metadata trước khi gọi service:

```java
@MessageMapping("orders.{orderId}.submit")
public Mono<SubmitResult> submit(
        @DestinationVariable("orderId") UUID orderId,
        @Header(name = "tenantContext", required = false) TenantContext tenant,
        @Payload SubmitOrder command) {

    if (tenant == null) {
        return Mono.error(new IllegalArgumentException(
            "tenantContext metadata is required"));
    }

    return orderService.submit(orderId, tenant, command);
}
```

Nếu metadata đại diện cho tenant hoặc principal, không dùng giá trị client gửi làm bằng chứng xác thực. Hãy kiểm tra nó với security context đáng tin cậy và xác minh caller có quyền truy cập tài nguyên tương ứng.

## 13. Version hóa custom metadata

Metadata schema có thể thay đổi theo thời gian. Nếu sender và receiver triển khai khác phiên bản, việc thay đổi field hoặc kiểu dữ liệu có thể khiến decoder thất bại hoặc tạo object sai nghĩa.

Một số cách quản lý:

1. Dùng MIME type có version rõ ràng, ví dụ `application/vnd.acme.trace-context.v1+json`.
2. Thay đổi tương thích ngược trước: thêm field tùy chọn, giữ nguyên ý nghĩa field cũ.
3. Nếu thay đổi không tương thích, phát hành MIME type/version mới và đăng ký song song trong giai đoạn chuyển đổi.
4. Không tái sử dụng cùng MIME type cho hai schema không tương thích.
5. Kiểm thử kết hợp các phiên bản requester/responder mà hệ thống thực sự hỗ trợ.

Ví dụ đăng ký hai phiên bản:

```java
registry.metadataToExtract(
    MimeType.valueOf("application/vnd.acme.trace-context.v1+json"),
    TraceContextV1.class,
    "traceContextV1");

registry.metadataToExtract(
    MimeType.valueOf("application/vnd.acme.trace-context.v2+json"),
    TraceContextV2.class,
    "traceContextV2");
```

Nếu cả hai phiên bản cùng được hỗ trợ, handler hoặc một lớp adapter có thể chuẩn hóa chúng thành một mô hình nội bộ duy nhất.

## 14. Kiểm thử MetadataExtractor

Kiểm thử nên đi qua RSocket message handling để xác minh toàn bộ đường đi: requester encode metadata, transport chuyển payload, extractor decode metadata và handler nhận đúng header.

Các trường hợp nên có:

1. Gửi metadata custom đúng MIME type và xác minh handler nhận đúng object.
2. Gửi nhiều Composite Metadata entry và xác minh từng header được ánh xạ riêng.
3. Gửi metadata thiếu và xác minh hành vi optional/required.
4. Gửi MIME type không được đăng ký và xác minh chính sách xử lý.
5. Gửi JSON sai schema hoặc dữ liệu không giải mã được và xác minh lỗi.
6. Kiểm tra `ParameterizedTypeReference` giữ đúng kiểu phần tử generic.
7. Xác minh routing metadata vẫn được dùng để chọn handler, không bị nhầm với custom metadata.
8. Kiểm tra requester và responder dùng MIME type/codec tương thích.

Ví dụ kiểm tra handler nhận metadata:

```java
StepVerifier.create(
        requester.route("orders.{orderId}.summary", orderId)
            .metadata(new TraceContext("t-123", "checkout"), TRACE_MIME_TYPE)
            .data(new OrderQuery(true))
            .retrieveMono(OrderSummary.class))
    .expectNextMatches(summary -> summary.orderId().equals(orderId))
    .verifyComplete();
```

Để kiểm tra chính xác giá trị trace đã bind, có thể dùng service mock hoặc test probe ghi lại đối số mà handler chuyển xuống service. Chỉ kiểm tra response không đủ nếu response không phản ánh metadata đã nhận.

## 15. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Đăng ký `metadataToExtract` nhưng quên decoder | Spring biết mapping nhưng không có codec phù hợp để tạo target object. | Cấu hình decoder hỗ trợ MIME type đó trong `RSocketStrategies`. |
| MIME type ở requester và responder khác nhau | Extractor không tìm thấy mapping tương ứng. | Dùng chung hằng MIME type và kiểm thử contract hai phía. |
| Nhầm tên header với MIME type | Handler đọc sai key trong message headers. | Dùng đúng header name đã truyền cho `metadataToExtract`. |
| Dùng `@DestinationVariable` để đọc custom metadata | Route variable và metadata entry là hai nguồn khác nhau. | Dùng `@Header` sau khi extractor đã ánh xạ. |
| Gửi nhiều entry nhưng kết nối không dùng Composite Metadata | Metadata decoder không thể tách entry như mong đợi. | Đồng bộ metadata MIME type của kết nối và dùng Composite Metadata. |
| Dùng `List.class` cho metadata generic | Mất thông tin kiểu phần tử. | Dùng `ParameterizedTypeReference<List<T>>`. |
| Coi metadata tenant do client gửi là danh tính đã xác thực | Client có thể giả mạo giá trị metadata. | Kiểm tra với principal/security context và phân quyền ở server. |
| Thay schema nhưng giữ nguyên MIME type | Hai phiên bản có thể giải mã cùng bytes theo ý nghĩa khác nhau. | Version hóa MIME type hoặc giữ tương thích ngược. |
| Đọc metadata raw trong mọi handler | Lặp logic parse và phụ thuộc vào chi tiết wire format. | Tập trung giải mã ở `MetadataExtractor`. |

## Tài liệu tham khảo

- [Spring Framework — RSocket Metadata](https://docs.spring.io/spring-framework/reference/rsocket.html#rsocket-metadata) — metadata extraction, `RSocketStrategies` và Composite Metadata.
- [Spring Framework Javadoc — MetadataExtractor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/MetadataExtractor.html) — hợp đồng trích xuất metadata thành message headers.
- [Spring Framework Javadoc — DefaultMetadataExtractor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/DefaultMetadataExtractor.html) — extractor mặc định và cấu hình mapping.
- [Spring Framework Javadoc — RSocketStrategies](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.html) — cấu hình codec và metadata extractor registry.

## Kết luận

`MetadataExtractor` chuyển metadata của RSocket payload thành message headers mà Spring handler có thể sử dụng. `metadataToExtract(...)` đăng ký MIME type, kiểu Java đích và tên header; decoder tương ứng phải có trong `RSocketStrategies`. Requester gửi metadata với cùng MIME type, còn handler nhận object đã giải mã qua `@Header` hoặc map `@Headers`. Khi dùng Composite Metadata, mỗi entry có MIME type riêng và kết nối phải được cấu hình tương thích. Tách metadata extraction khỏi logic handler, version hóa schema và kiểm tra metadata với security context giúp ứng dụng Spring RSocket dễ mở rộng, an toàn và tương thích giữa các phiên bản.
