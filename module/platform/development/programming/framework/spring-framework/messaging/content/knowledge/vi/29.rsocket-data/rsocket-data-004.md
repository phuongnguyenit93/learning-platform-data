# Composite Metadata và nhiều mục metadata trong một payload

## 1. Vì sao cần Composite Metadata?

Một RSocket `Payload` có hai phần độc lập:

- **Data** chứa nội dung nghiệp vụ mà handler xử lý, chẳng hạn mã đơn hàng, đối tượng yêu cầu hoặc dữ liệu của một bản tin.
- **Metadata** chứa thông tin bổ trợ cho việc định tuyến và xử lý bản tin, chẳng hạn route, thông tin xác thực, tenant, trace ID hoặc phiên bản giao thức.

Nếu một request cần đồng thời nhiều loại thông tin, một khối metadata đơn lẻ với một định dạng cố định sẽ khó mở rộng. Ví dụ, route cần được hiểu theo Routing Metadata extension, token có định dạng Authentication riêng, còn trace context có thể dùng định dạng của hệ thống quan sát.

**Composite Metadata** là phần mở rộng của RSocket cho phép ghép nhiều mục metadata độc lập vào cùng một metadata payload. Mỗi mục có MIME type và nội dung được mã hóa riêng. Vì vậy, một request có thể mang route, token và trace context cùng lúc mà không phải nhét tất cả vào một JSON chung.

Ví dụ về một request:

| Thành phần | MIME type | Giá trị minh họa |
|---|---|---|
| Route | `message/x.rsocket.routing.v0` | `orders.create` |
| Tenant | `application/vnd.acme.tenant-id.v1` | `tenant-42` |
| Trace | `application/vnd.acme.trace-id.v1` | `trace-7f31` |
| Data | MIME type của data trên connection | `order-1001` |

Các mục metadata không thay thế phần data. Chúng cung cấp ngữ cảnh để responder định tuyến, xác thực, ghi log hoặc áp dụng chính sách cho phần data.

## 2. Composite Metadata nằm ở đâu trong RSocket?

Trong bước thiết lập connection, requester gửi frame `SETUP` để khai báo MIME type dùng cho data và metadata; responder nhận các tham số này và áp dụng chúng cho connection. Với Spring `RSocketRequester`, MIME type metadata mặc định là:

```text
message/x.rsocket.composite-metadata.v0
```

Đây là MIME type của **container Composite Metadata**. Nó cho biết metadata payload chứa một chuỗi các entry. MIME type nằm bên trong từng entry mới mô tả cách giải mã giá trị cụ thể, ví dụ Routing, Authentication hoặc MIME type do ứng dụng định nghĩa.

Cần phân biệt ba cấp:

1. **Metadata MIME type của connection**: cho biết cách diễn giải toàn bộ metadata payload. Với Composite Metadata, giá trị là `message/x.rsocket.composite-metadata.v0`.
2. **Entry MIME type**: cho biết định dạng của một mục bên trong container.
3. **Data MIME type**: mô tả phần data, độc lập với metadata.

Trong request thông thường, route và metadata bổ trợ được gửi trong metadata của frame mở đầu interaction như `REQUEST_RESPONSE`, `REQUEST_STREAM`, `REQUEST_CHANNEL` hoặc `REQUEST_FNF`. Phần data vẫn nằm riêng trong payload.

## 3. Cấu trúc nhị phân của một metadata entry

Composite Metadata là các entry được nối liên tiếp. Không có dấu phẩy, ký tự xuống dòng hay separator giữa các entry. Mỗi entry tự mô tả MIME type và độ dài dữ liệu của nó:

```text
+----------------------+---------------------------+
| M | MIME ID / Length | MIME type nếu là custom  |
+----------------------+---------------------------+
| Metadata Length (24 bit)                         |
+--------------------------------------------------+
| Metadata bytes                                   |
+--------------------------------------------------+
| Entry tiếp theo ...                              |
+--------------------------------------------------+
```

Ý nghĩa các trường:

- **M bit** xác định cách biểu diễn MIME type.
  - Khi bit M được bật, 7 bit còn lại là ID của một well-known MIME type. Cách này tiết kiệm không gian vì không phải ghi cả chuỗi MIME type.
  - Khi bit M không được bật, 7 bit còn lại biểu diễn độ dài của MIME type tùy chỉnh; tiếp theo là chuỗi MIME type dạng US-ASCII, không có ký tự null kết thúc.
- **Metadata Length** là số nguyên unsigned 24-bit, big-endian, biểu diễn số byte của phần metadata value. Giá trị tối đa là 16.777.215 byte cho một entry.
- **Metadata bytes** là nội dung đã được mã hóa theo MIME type của entry đó.

Ví dụ về thứ tự logic của metadata payload:

```text
[Routing entry]
[Tenant entry]
[Trace entry]
[Authentication entry]
```

Khi giải mã, receiver đọc header để biết MIME type, đọc độ dài để lấy đúng số byte của entry, sau đó tiếp tục tại byte kế tiếp. Nhờ có độ dài riêng, receiver có thể bỏ qua một MIME type mà nó không hỗ trợ và tiếp tục đọc entry sau.

Một số quy tắc quan trọng của extension:

- Có thể có nhiều entry trong cùng một metadata payload.
- Nhiều entry có thể dùng cùng MIME type.
- Thứ tự entry phải được giữ nguyên khi chuyển đến responder.
- MIME type và nội dung phải thống nhất với encoder/decoder mà hai phía sử dụng.
- Composite Metadata extension hiện được định nghĩa ở phiên bản `v0`.

**Đừng nhầm độ dài entry với độ dài metadata của frame.** Frame RSocket có thể có trường metadata length ở cấp frame; trường đó bao phủ toàn bộ composite metadata bytes. Bên trong khối đó, mỗi entry lại có Metadata Length 24-bit riêng.

## 4. Gửi nhiều mục metadata bằng Spring RSocketRequester

Spring cung cấp `RSocketRequester` để gửi request bằng object Java thay vì tự thao tác với `ByteBuf` hoặc tự ghép byte. Khi dùng Composite Metadata (mặc định), gọi `metadata(value, mimeType)` nhiều lần sẽ thêm các entry vào cùng metadata payload.

Ví dụ dưới đây gửi route, tenant ID và trace ID trong một request:

```java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;

public class OrderClient {

    private static final MimeType TENANT_ID_MIME =
            MimeTypeUtils.parseMimeType("application/vnd.acme.tenant-id.v1");

    private static final MimeType TRACE_ID_MIME =
            MimeTypeUtils.parseMimeType("application/vnd.acme.trace-id.v1");

    private final RSocketRequester requester;

    public OrderClient() {
        this.requester = RSocketRequester.builder()
                .tcp("localhost", 7000);
    }

    public Mono<String> createOrder(String orderId,
                                    String tenantId,
                                    String traceId) {
        return requester.route("orders.create")
                .metadata(tenantId, TENANT_ID_MIME)
                .metadata(traceId, TRACE_ID_MIME)
                .data(orderId)
                .retrieveMono(String.class);
    }
}
```

Trong ví dụ:

- `route("orders.create")` thêm Routing Metadata để responder tìm đúng handler.
- Lần gọi `metadata` thứ nhất thêm tenant ID với MIME type riêng.
- Lần gọi `metadata` thứ hai thêm trace ID với MIME type riêng.
- `data(orderId)` gửi nội dung nghiệp vụ trong phần data.
- `retrieveMono(String.class)` khai báo kiểu dữ liệu phản hồi mong đợi.

Spring mã hóa các giá trị object bằng `Encoder` phù hợp đã đăng ký trong `RSocketStrategies`. Các codec cơ bản của Spring hỗ trợ `String`, `byte[]` và `ByteBuffer`. Nếu metadata là một POJO hoặc JSON, cần đăng ký encoder tương ứng ở phía gửi và decoder tương ứng ở phía nhận.

`metadata(value, mimeType)` chỉ dùng được khi connection sử dụng Composite Metadata. Nếu connection được cấu hình với một metadata MIME type đơn lẻ, Spring có thể ném `IllegalArgumentException` khi gọi phương thức này. Khi dùng Composite Metadata mặc định, route cũng được mã hóa thành một entry có MIME type `message/x.rsocket.routing.v0`.

## 5. Khai báo cách giải mã metadata ở responder

Gửi một entry có MIME type riêng chưa đủ để Spring tự động biến giá trị đó thành header. Responder cần đăng ký cách giải mã entry và tên header mà handler sẽ nhận.

`RSocketMessageHandler` hỗ trợ Composite Metadata và Routing Metadata mặc định. `DefaultMetadataExtractor` có sẵn cách xử lý Routing Metadata: giải mã route thành `String` và lưu dưới key `route`. Với MIME type tùy chỉnh, cần đăng ký decoder và mapping tương ứng.

Ví dụ cấu hình server để ánh xạ hai entry thành header `tenantId` và `traceId`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketMessageHandler;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

@Configuration
public class RSocketMetadataConfig {

    static final MimeType TENANT_ID_MIME =
            MimeTypeUtils.parseMimeType("application/vnd.acme.tenant-id.v1");

    static final MimeType TRACE_ID_MIME =
            MimeTypeUtils.parseMimeType("application/vnd.acme.trace-id.v1");

    @Bean
    RSocketStrategies rsocketStrategies() {
        return RSocketStrategies.builder()
                .metadataExtractorRegistry(registry -> {
                    registry.metadataToExtract(
                            TENANT_ID_MIME, String.class, "tenantId");
                    registry.metadataToExtract(
                            TRACE_ID_MIME, String.class, "traceId");
                })
                .build();
    }

    @Bean
    RSocketMessageHandler rsocketMessageHandler(
            RSocketStrategies strategies) {
        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRSocketStrategies(strategies);
        return handler;
    }
}
```

Các MIME type ở server phải khớp chính xác với MIME type phía client. Tên `tenantId` và `traceId` là tên key mà ứng dụng chọn để truy cập giá trị đã giải mã; chúng không phải tên MIME type.

Handler có thể nhận các giá trị đó bằng `@Header`:

```java
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class OrderRSocketController {

    @MessageMapping("orders.create")
    public Mono<String> create(
            @Payload String orderId,
            @Header("tenantId") String tenantId,
            @Header("traceId") String traceId) {

        String result = "accepted order=" + orderId
                + ", tenant=" + tenantId
                + ", trace=" + traceId;

        return Mono.just(result);
    }
}
```

Với cấu hình trên, Spring thực hiện luồng xử lý:

```text
Client
  route("orders.create")
  metadata(tenantId, TENANT_ID_MIME)
  metadata(traceId, TRACE_ID_MIME)
  data(orderId)
        |
        v
Composite Metadata trong request
  [routing] [tenant] [trace]
        |
        v
MetadataExtractor
  route    -> orders.create
  tenantId -> tenant-42
  traceId  -> trace-7f31
        |
        v
@MessageMapping("orders.create")
  @Payload orderId
  @Header tenantId
  @Header traceId
```

Đoạn cấu hình trên là các thành phần của một ứng dụng Spring có RSocket responder. Nó không phải chương trình Java độc lập để chạy chỉ bằng `javac`: ứng dụng cần các dependency Spring Messaging/RSocket, Reactor, cấu hình transport và một connection RSocket đang hoạt động. Với Spring Boot, có thể dùng auto-configuration phù hợp; nếu tự cấu hình Spring Framework, cần đăng ký `RSocketMessageHandler` làm responder cho RSocket server.

## 6. Metadata dạng POJO hoặc JSON

Metadata không bắt buộc phải là chuỗi. Ứng dụng có thể gửi một object có cấu trúc, miễn là cả hai phía thống nhất MIME type và có encoder/decoder phù hợp.

Ví dụ một metadata object:

```java
public record ClientContext(String appVersion, String region) {
}
```

Phía gửi có thể gọi:

```java
.metadata(
    new ClientContext("2.4.0", "ap-southeast-1"),
    MimeTypeUtils.parseMimeType("application/vnd.acme.client-context+json"))
```

Khi dùng JSON, cấu hình `RSocketStrategies` với `Jackson2JsonEncoder` ở phía gửi và `Jackson2JsonDecoder` ở phía nhận. Phía responder đăng ký MIME type đó với kiểu đích:

```java
registry.metadataToExtract(
        CLIENT_CONTEXT_MIME, ClientContext.class, "clientContext");
```

Sau đó handler có thể nhận object qua `@Header("clientContext")`. Tên header là key do ứng dụng đăng ký trong extractor. Không nên mặc định rằng Spring sẽ giải mã một MIME type tùy chỉnh nếu chưa có decoder và mapping tương ứng.

Với metadata JSON chứa nhiều trường, cũng có thể đăng ký một mapper để đưa các trường đã giải mã vào output map. Cách này hữu ích khi muốn ánh xạ các trường riêng lẻ thành header, nhưng cần đặt quy ước tên rõ ràng và tránh ghi đè key đã có.

## 7. Nhiều entry cùng MIME type và thứ tự

Theo Composite Metadata extension, cùng một MIME type có thể xuất hiện ở nhiều entry và thứ tự entry được bảo toàn. Điều này hữu ích khi giao thức ứng dụng định nghĩa một danh sách metadata cùng loại.

Tuy nhiên, cần phân biệt khả năng của wire protocol với mô hình dữ liệu ở tầng Spring. `MetadataExtractor` trả về các cặp name-value trong một `Map`; nếu nhiều entry được ánh xạ vào cùng một key, ứng dụng không nên mặc định rằng chúng tự động trở thành một danh sách. Hãy định nghĩa rõ cách gom giá trị bằng mapper tùy chỉnh hoặc dùng các key khác nhau. Nếu thứ tự có ý nghĩa nghiệp vụ, hãy kiểm thử hành vi giải mã và ánh xạ thực tế.

Không nên dùng nhiều entry cùng MIME type để gửi một danh sách lớn khi phần data hoặc một cấu trúc metadata duy nhất phù hợp hơn. Metadata nên giữ vai trò ngữ cảnh nhỏ, có thể xử lý trước hoặc độc lập với phần data.

## 8. Khi nào nên dùng Composite Metadata?

Các tình huống phù hợp:

- **Routing**: chọn handler hoặc endpoint logic thông qua route.
- **Authentication**: truyền thông tin xác thực theo extension hoặc cơ chế bảo mật đã thống nhất.
- **Tenant context**: xác định tenant để áp dụng phạm vi dữ liệu và chính sách.
- **Tracing**: truyền trace ID hoặc tracing context để nối các span giữa nhiều service.
- **Versioning/capability**: thông báo phiên bản giao thức hoặc khả năng mà request yêu cầu.
- **Content hints**: truyền một số chỉ dẫn xử lý nhỏ không thuộc dữ liệu nghiệp vụ chính.

Nên giữ phần data cho nội dung mà handler cần xử lý như một thông điệp nghiệp vụ. Chỉ đưa thông tin vào metadata khi nó thực sự là ngữ cảnh hoặc chỉ dẫn xử lý.

## 9. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Chỉ gửi được một loại metadata | Connection đang dùng metadata MIME type đơn lẻ | Dùng Composite Metadata ở cả hai phía |
| Gọi `metadata()` gây `IllegalArgumentException` | `RSocketRequester` không dùng Composite Metadata | Kiểm tra `metadataMimeType` của connection |
| Handler không nhận được header tùy chỉnh | Chưa đăng ký MIME type với `MetadataExtractor` | Thêm `metadataToExtract` cho MIME type đó |
| Lỗi encode/decode | Thiếu encoder/decoder hoặc MIME type không khớp | Cấu hình codec tương ứng ở cả hai phía |
| Route không tìm thấy handler | Route không khớp `@MessageMapping` hoặc route matcher | Kiểm tra route, separator và cấu hình route matcher |
| Giá trị metadata bị hiểu sai | MIME type mô tả sai định dạng bytes | Thống nhất MIME type và encoding thực tế |
| Metadata quá lớn | Đưa dữ liệu nghiệp vụ vào metadata | Chuyển dữ liệu lớn sang phần data |
| Nhiều entry bị mất khi ánh xạ | Nhiều entry cùng ghi vào một key trong map | Dùng mapper hoặc cấu trúc collection có chủ đích |

Một số lưu ý khi vận hành:

1. Định nghĩa MIME type có version, ví dụ `application/vnd.acme.trace-id.v1`, để có thể tiến hóa schema mà không làm thay đổi ngầm cách giải mã cũ.
2. Tránh dùng tên MIME type quá chung như `text/plain` cho nhiều ý nghĩa khác nhau nếu responder cần phân biệt từng loại metadata.
3. Kiểm tra dữ liệu metadata đầu vào như dữ liệu không tin cậy. Tenant ID hoặc trace ID không tự chứng minh danh tính hay quyền truy cập.
4. Không dùng tenant metadata làm cơ chế phân quyền duy nhất. Phải xác thực principal và kiểm tra principal đó có quyền truy cập tenant được yêu cầu.
5. Không ghi access token, credential hoặc metadata nhạy cảm vào log.
6. Giữ metadata nhỏ để giảm chi phí mã hóa, truyền tải và giải mã.
7. Kiểm thử trường hợp thiếu metadata bắt buộc, MIME type không được hỗ trợ, giá trị sai định dạng và request không được phép.

## 10. Checklist kiểm tra

- [ ] Connection khai báo `message/x.rsocket.composite-metadata.v0` nếu cần nhiều entry.
- [ ] Mỗi entry có MIME type riêng và nội dung được encode đúng định dạng.
- [ ] Client và server thống nhất MIME type, schema và version.
- [ ] Các metadata tùy chỉnh đã được đăng ký trong `MetadataExtractor`.
- [ ] Handler truy cập đúng key thông qua `@Header` hoặc `@Headers`.
- [ ] Route được giải mã và khớp với `@MessageMapping`.
- [ ] Metadata lặp được xử lý theo quy tắc rõ ràng, không vô tình ghi đè.
- [ ] Metadata không thay thế phần data và không mang dữ liệu lớn không cần thiết.
- [ ] Quyền truy cập được xác minh độc lập với các giá trị metadata do client gửi.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [RSocket — Composite Metadata Extension](https://github.com/rsocket/rsocket/blob/master/Extensions/CompositeMetadata.md)
- [RSocket — Routing Metadata Extension](https://github.com/rsocket/rsocket/blob/master/Extensions/Routing.md)
- [Spring Framework 6.1 — RSocketRequester.MetadataSpec](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.MetadataSpec.html)
- [Spring Framework 6.1 — RSocketStrategies.Builder](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.Builder.html)
- [Spring Framework 6.1 — MetadataExtractorRegistry](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/messaging/rsocket/MetadataExtractorRegistry.html)
