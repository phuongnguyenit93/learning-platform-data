# Đưa metadata đã trích xuất vào tham số @Header

RSocket payload có hai phần độc lập: `data` chứa nội dung nghiệp vụ và `metadata` mang thông tin mô tả hoặc điều khiển request. Trong Spring RSocket, metadata có thể được giải mã thành các giá trị có tên rồi truyền trực tiếp vào tham số `@Header` của phương thức `@MessageMapping`.

Để làm được điều đó, ứng dụng cần đăng ký MIME type và decoder cho từng loại metadata tùy chỉnh. `MetadataExtractor` thực hiện việc chuyển byte metadata thành các cặp tên-giá trị; `@Header` lấy một giá trị theo tên, còn `@Headers` nhận toàn bộ các giá trị đã trích xuất.

## 1. Data và metadata có vai trò khác nhau

Một request RSocket có thể mang:

- **Data:** nội dung nghiệp vụ như `CreateOrder`, `SensorReading` hoặc một lệnh điều khiển.
- **Metadata:** route, tenant context, tracing context, thông tin xác thực hoặc các thuộc tính cần thiết để xử lý request.

Data MIME type và metadata MIME type được khai báo trong `SETUP`. Với composite metadata, một request có thể mang nhiều entry metadata độc lập, mỗi entry có MIME type riêng.

Ví dụ một request tạo đơn hàng:

```text
RSocket request
  data:
    { "orderId": "ORD-2026-018", "amount": 125000 }

  composite metadata:
    message/x.rsocket.routing.v0
      orders.create
    application/vnd.acme.tenant+json
      { "tenantId": "tenant-42", "region": "ap-southeast-1" }
    application/vnd.acme.trace+json
      { "traceId": "trace-9f21" }
```

Spring dùng routing metadata để tìm `@MessageMapping`. Các entry metadata tùy chỉnh còn lại có thể được giải mã thành object Java và đưa vào handler như header.

Không nên gộp metadata vào DTO nghiệp vụ chỉ để chuyển thông tin tenant hoặc trace. Tách hai vùng giúp data giữ đúng schema nghiệp vụ, còn metadata giữ ngữ cảnh của request.

## 2. MetadataExtractor làm nhiệm vụ gì?

`MetadataExtractor` nhận metadata đã được serialize và chuyển nó thành map các cặp tên-giá trị. Sau khi trích xuất, Spring có thể cung cấp các giá trị này cho handler thông qua `@Header` hoặc `@Headers`.

`DefaultMetadataExtractor` có hỗ trợ sẵn routing metadata với MIME type `message/x.rsocket.routing.v0`. Route được giải mã thành `String` và lưu dưới key `route`.

Với metadata tùy chỉnh, cần đăng ký:

1. MIME type của entry.
2. Kiểu Java đích để decoder tạo object.
3. Tên key mà handler sẽ sử dụng.

Ví dụ, entry `application/vnd.acme.tenant+json` được giải mã thành `TenantMetadata` và lưu dưới key `tenant`. Handler sau đó có thể khai báo `@Header("tenant") TenantMetadata tenant`.

## 3. Khai báo model và MIME type cho metadata

Tạo các record mô tả metadata:

```java
public record TenantMetadata(
        String tenantId,
        String region
) {}

public record TraceMetadata(
        String traceId
) {}
```

Định nghĩa MIME type ổn định để client và server cùng sử dụng:

```java
public final class RSocketMetadataTypes {

    public static final MimeType TENANT = MimeType.valueOf(
            "application/vnd.acme.tenant+json");

    public static final MimeType TRACE = MimeType.valueOf(
            "application/vnd.acme.trace+json");

    private RSocketMetadataTypes() {}
}
```

MIME type nên phản ánh định dạng và mục đích của metadata. Khi thay đổi cấu trúc, hãy quản lý tương thích phiên bản hoặc bổ sung MIME type mới theo hợp đồng đã thống nhất.

## 4. Đăng ký decoder và metadataToExtract

Trong Spring, cấu hình `RSocketStrategies` để có decoder JSON và đăng ký từng entry metadata với `metadataExtractorRegistry`:

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
                            RSocketMetadataTypes.TENANT,
                            TenantMetadata.class,
                            "tenant");

                    registry.metadataToExtract(
                            RSocketMetadataTypes.TRACE,
                            TraceMetadata.class,
                            "trace");
                })
                .build();
    }
}
```

Lệnh `metadataToExtract(mimeType, targetClass, name)` có nghĩa:

- Khi gặp metadata entry có MIME type đã đăng ký, dùng decoder phù hợp để tạo object `targetClass`.
- Đặt object vừa giải mã vào map metadata dưới key `name`.
- Handler truy cập object đó qua `@Header(name)`.

Trong ví dụ, map sau khi trích xuất có dạng khái niệm:

```text
route  -> "orders.create"
tenant -> TenantMetadata(tenantId="tenant-42", region="ap-southeast-1")
trace  -> TraceMetadata(traceId="trace-9f21")
```

`RSocketMessageHandler` ở phía server cần dùng cùng `RSocketStrategies`:

```java
@Bean
RSocketMessageHandler rsocketMessageHandler(RSocketStrategies strategies) {
    RSocketMessageHandler handler = new RSocketMessageHandler();
    handler.setRSocketStrategies(strategies);
    return handler;
}
```

Nếu Spring Boot đã tự cấu hình `RSocketStrategies`, có thể mở rộng cấu hình hiện có bằng cách đăng ký metadata extractor phù hợp. Tránh tạo hai bộ strategy khác nhau mà client/server không đồng bộ decoder hoặc MIME type.

## 5. Gửi metadata từ RSocketRequester

Phía requester thêm metadata entry bằng `.metadata(value, mimeType)`. Với composite metadata mặc định, có thể thêm nhiều entry trên cùng một request:

```java
Mono<OrderAccepted> response = requester
        .route("orders.create")
        .metadata(
                new TenantMetadata("tenant-42", "ap-southeast-1"),
                RSocketMetadataTypes.TENANT)
        .metadata(
                new TraceMetadata("trace-9f21"),
                RSocketMetadataTypes.TRACE)
        .data(new CreateOrder("ORD-2026-018", new BigDecimal("125000")))
        .retrieveMono(OrderAccepted.class);
```

Để encode các object metadata, client cũng cần encoder phù hợp trong `RSocketStrategies`. Ví dụ JSON encoder đã đăng ký ở phần trước hỗ trợ tuần tự hóa hai record metadata.

Route được đặt bằng `.route(...)`; Spring tạo routing metadata tương ứng. Không cần tự tạo thêm một entry JSON chỉ để lặp lại route nếu ứng dụng đã sử dụng routing metadata chuẩn.

## 6. Đưa metadata vào tham số @Header

Sau khi metadata đã được trích xuất, handler lấy một entry bằng `@Header`:

```java
@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.create")
    public Mono<OrderAccepted> create(
            @Payload CreateOrder command,
            @Header("tenant") TenantMetadata tenant,
            @Header(name = "trace", required = false) TraceMetadata trace) {

        return orderService.create(command, tenant, trace);
    }
}
```

Ở đây:

- `@Payload` nhận DTO nghiệp vụ được giải mã từ vùng data.
- `@Header("tenant")` nhận object `TenantMetadata` đã được `MetadataExtractor` tạo dưới key `tenant`.
- `@Header(name = "trace", required = false)` nhận `TraceMetadata` nếu có; nếu entry không được gửi, tham số có thể là `null`.

Tên trong `@Header` phải khớp chính xác với key truyền vào `metadataToExtract`. Nếu đăng ký key là `tenantContext` nhưng handler đọc `@Header("tenant")`, Spring không thể tìm thấy giá trị theo tên đó.

Khi metadata bắt buộc, để `required` mặc định là `true` hoặc khai báo rõ `required = true`. Khi metadata tùy chọn, dùng `required = false` và xử lý trường hợp `null` trong code.

## 7. Nhận toàn bộ metadata bằng @Headers

Nếu handler cần nhiều entry hoặc muốn xử lý metadata linh hoạt, có thể nhận map bằng `@Headers`:

```java
@MessageMapping("orders.inspect")
Mono<OrderInspection> inspect(
        @Payload OrderQuery query,
        @Headers Map<String, Object> metadata) {

    TenantMetadata tenant = (TenantMetadata) metadata.get("tenant");
    TraceMetadata trace = (TraceMetadata) metadata.get("trace");

    return inspectionService.inspect(query, tenant, trace);
}
```

`@Headers Map<String, Object>` chứa các giá trị đã được metadata extractor đăng ký và giải mã. Đây không phải map byte thô của toàn bộ composite metadata. Nếu một MIME type chưa được đăng ký, Spring không tự biết cách chuyển entry đó thành object nghiệp vụ.

Khi có thể xác định rõ metadata cần dùng, ưu tiên tham số `@Header` có kiểu cụ thể. Cách này giúp chữ ký handler dễ đọc, thể hiện dependency rõ ràng và giảm ép kiểu thủ công. Dùng `@Headers` khi handler thực sự cần xử lý một tập key động hoặc cần kiểm tra nhiều metadata tùy chọn.

## 8. Trích xuất JSON metadata thành Map

Không phải metadata nào cũng cần một DTO riêng. Với metadata JSON có cấu trúc linh hoạt, có thể đăng ký kiểu `Map<String, String>` bằng `ParameterizedTypeReference` và hàm chuyển map đã decode vào output map:

```java
MimeType CLIENT_CONTEXT = MimeType.valueOf(
        "application/vnd.acme.client-context+json");

RSocketStrategies strategies = RSocketStrategies.builder()
        .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
        .metadataExtractorRegistry(registry -> registry.metadataToExtract(
                CLIENT_CONTEXT,
                new ParameterizedTypeReference<Map<String, String>>() {},
                (decoded, output) -> output.putAll(decoded)))
        .build();
```

Giả sử metadata có dạng:

```json
{
  "locale": "vi-VN",
  "clientVersion": "2.4.1"
}
```

Sau khi trích xuất, handler có thể đọc các key `locale` và `clientVersion` qua `@Header` hoặc `@Headers`:

```java
@MessageMapping("profile.summary")
Mono<ProfileSummary> summary(
        @Payload ProfileQuery query,
        @Header(name = "locale", required = false) String locale,
        @Header(name = "clientVersion", required = false) String clientVersion) {

    return profileService.summary(query, locale, clientVersion);
}
```

Kiểu Map linh hoạt nhưng ít an toàn kiểu hơn DTO. Nếu key là một phần hợp đồng quan trọng, nên dùng record có field rõ ràng để compiler và validation hỗ trợ kiểm tra.

## 9. Composite metadata và trường hợp không dùng composite

Composite metadata cho phép một payload chứa nhiều entry độc lập, mỗi entry có MIME type riêng. Đây là cách thuận tiện để kết hợp routing, tenant context, tracing hoặc authentication metadata trong một request.

Tuy nhiên, requester có thể không hỗ trợ composite metadata hoặc ứng dụng có thể chọn một định dạng metadata khác. Khi đó `DefaultMetadataExtractor` có thể cần logic tùy chỉnh để ánh xạ object đã decode vào map output. Ví dụ một entry JSON duy nhất có thể chứa nhiều key, sau đó callback tách các key cần thiết và đưa vào output map.

Không giả định metadata extractor có thể đọc mọi MIME type. Mỗi định dạng tùy chỉnh cần decoder tương ứng và đăng ký rõ ràng. Client và server phải thống nhất cả cách serialize entry lẫn MIME type của nó.

## 10. Metadata không thay thế xác thực và phân quyền

Metadata do requester gửi vẫn là dữ liệu đầu vào. Việc Spring giải mã thành `TenantMetadata` không chứng minh requester thực sự thuộc tenant đó.

Các nguyên tắc an toàn:

- Không tin `tenantId`, `userId`, `role` hoặc `isAdmin` chỉ vì chúng xuất hiện trong metadata.
- Xác thực requester bằng cơ chế bảo mật RSocket phù hợp; lấy principal đã xác thực từ security context.
- Đối chiếu tenant metadata với danh tính và quyền đã xác thực ở server.
- Kiểm tra quyền truy cập tài nguyên trong service/domain layer, không chỉ dựa trên route hoặc `@Header`.
- Không ghi access token hoặc secret ra log. Nếu metadata chứa bearer token, để Spring Security hoặc tầng xác thực xử lý; không tự coi chuỗi token là principal.
- Giới hạn kích thước metadata, độ dài chuỗi và số entry để tránh tiêu thụ tài nguyên quá mức.

Ví dụ, service nên xác minh tenant context trước khi tạo đơn hàng:

```java
public Mono<OrderAccepted> create(
        CreateOrder command,
        TenantMetadata requestedTenant,
        TraceMetadata trace) {

    return currentPrincipal()
            .flatMap(principal -> tenantAccessService
                    .verifyTenant(principal, requestedTenant.tenantId()))
            .then(orderRepository.save(command))
            .map(order -> new OrderAccepted(
                    order.id(), trace != null ? trace.traceId() : null));
}
```

`currentPrincipal()` và `verifyTenant(...)` là các thành phần ứng dụng minh họa. Điểm quan trọng là metadata cung cấp ngữ cảnh được yêu cầu; server vẫn tự xác minh quyền trước khi thực hiện nghiệp vụ.

## 11. Metadata theo request và metadata cấp kết nối

Không phải mọi metadata đều thuộc một request cụ thể:

- **Request metadata:** đi kèm request như routing, tenant context hoặc trace context. Các giá trị đã trích xuất có thể được đưa vào `@Header` của `@MessageMapping`.
- **SETUP metadata:** được gửi khi mở kết nối, có thể dùng để khởi tạo ngữ cảnh hoặc xác thực kết nối thông qua `@ConnectMapping`.
- **METADATA_PUSH:** thông báo metadata ở cấp kết nối, không gắn với một request cụ thể. Spring có thể xử lý loại sự kiện này bằng `@ConnectMapping`.

`@ConnectMapping` xử lý `SETUP` và metadata push, còn `@MessageMapping` xử lý request thông thường. Nếu một giá trị ổn định cho toàn phiên, có thể cân nhắc đặt trong setup/session context thay vì lặp lại trong mọi request. Nếu giá trị có thể thay đổi theo request, hãy gửi nó trong request metadata.

## 12. Kiểm thử metadata extraction

Kiểm thử cần xác nhận toàn bộ chuỗi serialize → truyền entry → decode → map key → bind vào tham số handler.

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Metadata MIME type đã đăng ký | Decoder tạo đúng object Java |
| Key đã đăng ký | `@Header` nhận đúng object theo tên |
| Metadata tùy chọn không có | Tham số `required = false` nhận `null` |
| Metadata bắt buộc không có | Request thất bại ở bước resolve header theo hợp đồng |
| MIME type không có decoder | Metadata không được giải mã như object đã khai báo; lỗi được ghi nhận rõ |
| `@Headers` | Map chứa các giá trị đã trích xuất với đúng key |
| Nhiều entry composite | Tenant và trace được giải mã độc lập |
| Metadata sai cấu trúc | Request bị từ chối có kiểm soát; handler không dùng dữ liệu lỗi |
| Tenant giả mạo | Service từ chối khi metadata không khớp principal đã xác thực |
| Log và tracing | Correlation/trace ID được ghi đúng; secret không xuất hiện |

Ví dụ kiểm thử handler với metadata:

```java
StepVerifier.create(requester
        .route("orders.create")
        .metadata(new TenantMetadata("tenant-42", "ap-southeast-1"),
                RSocketMetadataTypes.TENANT)
        .metadata(new TraceMetadata("trace-9f21"),
                RSocketMetadataTypes.TRACE)
        .data(new CreateOrder("ORD-2026-018", new BigDecimal("125000")))
        .retrieveMono(OrderAccepted.class))
        .assertNext(result -> assertThat(result.status()).isEqualTo("ACCEPTED"))
        .verifyComplete();
```

Test này giả định client và server đã dùng cùng MIME type, encoder/decoder và metadata extractor. Ngoài test thành công, hãy gửi thiếu entry bắt buộc, sai MIME type và tenant không có quyền để kiểm tra các nhánh từ chối.

## 13. Checklist triển khai

- [ ] Xác định metadata nào thuộc từng request và metadata nào thuộc vòng đời kết nối.
- [ ] Dùng composite metadata khi cần nhiều entry có MIME type độc lập.
- [ ] Định nghĩa MIME type và schema/version cho metadata tùy chỉnh.
- [ ] Đăng ký encoder/decoder phù hợp trong `RSocketStrategies`.
- [ ] Đăng ký `metadataToExtract` với đúng target type và key.
- [ ] Đảm bảo `RSocketMessageHandler` sử dụng strategies có extractor đã cấu hình.
- [ ] Dùng `@Header("key")` cho giá trị cụ thể; dùng `@Headers` khi cần map metadata.
- [ ] Đánh dấu metadata tùy chọn bằng `required = false` và xử lý null.
- [ ] Không nhầm route metadata mặc định với metadata nghiệp vụ tùy chỉnh.
- [ ] Xác thực principal và phân quyền độc lập với giá trị metadata do client gửi.
- [ ] Giới hạn kích thước metadata và không log secret.
- [ ] Kiểm thử MIME type, key mapping, missing entry, composite entries và tenant giả mạo.

`@Header` chỉ nhận được metadata sau khi `MetadataExtractor` đã giải mã và đưa giá trị vào map theo key. Khi đăng ký đúng MIME type, decoder và tên key, handler có thể nhận metadata dưới dạng tham số Java có kiểu rõ ràng. Hãy coi metadata là ngữ cảnh của request, giữ schema ổn định và luôn xác minh mọi thông tin liên quan đến danh tính hoặc quyền truy cập ở phía server.

## Tài liệu tham khảo

- [Spring Framework — RSocket và MetadataExtractor](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework — `MetadataExtractor`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/MetadataExtractor.html)
- [Spring Framework — `DefaultMetadataExtractor`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/DefaultMetadataExtractor.html)
- [Spring Framework — `@Header`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Header.html)
- [Spring Framework — `@Headers`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Headers.html)
