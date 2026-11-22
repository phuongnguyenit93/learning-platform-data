# Phân biệt MIME type của data và metadata trong RSocket

RSocket chia một `Payload` thành hai phần độc lập: **data** và **metadata**. Cả hai đều là dữ liệu nhị phân (`ByteBuf`/buffer), nhưng phục vụ hai mục đích khác nhau và có thể được mã hóa theo hai định dạng khác nhau. MIME type cho biết bên nhận phải diễn giải các byte đó theo định dạng nào.

Điểm cần nhớ: `dataMimeType` mô tả phần data; `metadataMimeType` mô tả cách đóng gói phần metadata. Nếu dùng Composite Metadata, từng mục metadata bên trong còn có MIME type riêng.

## 1. Data và metadata khác nhau ở đâu?

| Tiêu chí | Data | Metadata |
| --- | --- | --- |
| Vai trò | Nội dung nghiệp vụ chính của message: đối tượng yêu cầu, dữ liệu trả về, sự kiện... | Thông tin mô tả hoặc điều khiển message: route, xác thực, tenant, tracing, correlation id... |
| Vị trí trong Payload | Vùng data | Vùng metadata riêng |
| MIME type cấp kết nối | `dataMimeType` trong `SETUP` | `metadataMimeType` trong `SETUP` |
| Ví dụ định dạng | `application/json`, `application/cbor`, `application/octet-stream`, `text/plain` | `message/x.rsocket.composite-metadata.v0` hoặc một định dạng metadata đơn như `application/vnd.acme.metadata+json` |
| Cách gửi bằng Spring | `.data(value)` | `.route(...)` và `.metadata(value, entryMimeType)` |

Ví dụ: khi tìm một đơn hàng, `OrderQuery` là data; route `orders.find` và thông tin tenant là metadata. Phần data trả lời câu hỏi “đang gửi nội dung gì?”, metadata trả lời “nội dung này thuộc request nào, cần được định tuyến hoặc xử lý trong ngữ cảnh nào?”.

```text
SETUP (một lần cho connection)
├── data MIME type: application/json
└── metadata MIME type: message/x.rsocket.composite-metadata.v0

REQUEST_RESPONSE / REQUEST_STREAM / REQUEST_CHANNEL / REQUEST_FNF
└── Payload
    ├── Metadata
    │   ├── route: message/x.rsocket.routing.v0
    │   ├── authentication: message/x.rsocket.authentication.bearer.v0
    │   └── tenant: application/vnd.acme.tenant+json
    └── Data: các byte JSON của đối tượng nghiệp vụ
```

Trong frame có cả data và metadata, phần metadata được đặt trước data và có trường độ dài riêng. API Java `io.rsocket.Payload` cũng cho phép truy cập riêng `data()` và `metadata()`. Metadata có thể vắng mặt; data cũng có thể rỗng tùy loại frame và request.

## 2. MIME type được khai báo ở đâu?

Khi thiết lập kết nối, bên khởi tạo gửi frame `SETUP`. Frame này khai báo riêng định dạng của data và metadata. Hai MIME type này là cấu hình cấp connection và áp dụng cho các message trên connection đó; chúng không phải lựa chọn MIME type độc lập cho từng request.

- `dataMimeType`: định dạng của vùng data. Ví dụ `application/json` có nghĩa hai bên thống nhất diễn giải data như JSON.
- `metadataMimeType`: định dạng bao ngoài của vùng metadata. Nếu dùng Composite Metadata, giá trị là `message/x.rsocket.composite-metadata.v0`.

RSocket gọi các giá trị này là MIME type, nhưng tầng giao thức không tự phân tích JSON, CBOR hay schema ứng dụng. Nó chuyển tiếp byte và thông tin định dạng; ứng dụng hoặc framework phải có encoder/decoder phù hợp. Hai đầu kết nối cần thống nhất MIME type và hỗ trợ cách mã hóa tương ứng.

Vì data MIME type được khai báo ở cấp connection, không nên giả định có thể gửi JSON ở request này rồi gửi CBOR ở request khác trên cùng connection chỉ bằng cách thay một tham số của `.data()`. Nếu cần nhiều kiểu nội dung, hãy thống nhất một định dạng chung hoặc dùng một envelope có discriminator; trường hợp cần MIME type khác nhau ở cấp connection thì tạo connection riêng.

## 3. Hiểu đúng hai lớp MIME type của metadata

Đây là phần dễ nhầm nhất. Khi dùng Composite Metadata có hai lớp:

1. **MIME type của metadata container**: khai báo trong `SETUP` bằng `metadataMimeType`. Với Composite Metadata, dùng `message/x.rsocket.composite-metadata.v0`.
2. **MIME type của từng metadata entry**: nằm bên trong container. Mỗi entry có loại và nội dung riêng, nên một Payload có thể mang nhiều entry với các định dạng khác nhau.

Ví dụ các entry thường gặp:

| Entry | MIME type | Ý nghĩa |
| --- | --- | --- |
| Routing | `message/x.rsocket.routing.v0` | Tên route để chọn handler |
| Bearer authentication | `message/x.rsocket.authentication.bearer.v0` | Thông tin xác thực dạng bearer token |
| Metadata của ứng dụng | `application/vnd.acme.tenant+json` | Dữ liệu tenant do ứng dụng định nghĩa, mã hóa JSON |
| Tracing | MIME type tracing theo extension hoặc quy ước của hệ thống | Trace context phục vụ quan sát request |

Trong Spring, `RSocketRequester.Builder.metadataMimeType(...)` đặt MIME type của container. Còn `RequestSpec.metadata(value, mimeType)` đặt MIME type cho **một entry** mà request gửi thêm. Hai tham số này không thay thế cho nhau.

Composite Metadata hữu ích khi một request cần đồng thời route, authentication và tracing. Nếu chọn một MIME type metadata đơn, toàn bộ vùng metadata được hiểu theo định dạng đó; không còn cơ chế container để tự phân loại nhiều entry độc lập. Với cấu hình metadata không phải Composite Metadata, Spring cũng giả định route (nếu có) được mã hóa theo MIME type metadata đã cấu hình.

## 4. Cấu hình trong Spring Framework

Spring cung cấp `RSocketRequester` để tạo request ở mức object, và `RSocketStrategies` để chọn encoder/decoder cho data và metadata.

- Các codec cơ bản từ `spring-core` hỗ trợ `String`, `byte[]` và `ByteBuffer`.
- Thêm `spring-web` để dùng các codec như Jackson JSON/CBOR hoặc Protobuf.
- Nếu không chỉ định `dataMimeType`, Spring suy ra giá trị mặc định từ decoder được cấu hình đầu tiên (ưu tiên decoder non-default nếu có). Vì vậy, khi tích hợp nhiều ngôn ngữ hoặc nhiều ứng dụng, nên cấu hình tường minh để tránh phụ thuộc thứ tự codec.
- `metadataMimeType` mặc định của `RSocketRequester.Builder` là Composite Metadata. Thông thường không cần đổi giá trị này.

### 4.1. Cấu hình client dùng JSON cho data và Composite Metadata

Đoạn mã sau minh họa API Spring Framework 6.2 với Jackson 2. Các class encoder/decoder cần `spring-web` và dependency Jackson tương ứng.

```java
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.util.MimeType;

MimeType json = MimeType.valueOf("application/json");
MimeType composite = MimeType.valueOf(
        "message/x.rsocket.composite-metadata.v0");

RSocketStrategies strategies = RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
        .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
        .build();

RSocketRequester requester = RSocketRequester.builder()
        .dataMimeType(json)
        .metadataMimeType(composite)
        .rsocketStrategies(strategies)
        .tcp("localhost", 7000);
```

Ở đây, `application/json` áp dụng cho data trên connection; `message/x.rsocket.composite-metadata.v0` áp dụng cho container metadata. Các codec chịu trách nhiệm chuyển object thành byte và ngược lại. Chỉ khai báo MIME type mà không đăng ký codec tương ứng sẽ không tự tạo ra khả năng serialize/deserialize.

Với Spring Framework 7 và Jackson 3, dùng `JacksonJsonEncoder` và `JacksonJsonDecoder` thay cho các class `Jackson2...` trong ví dụ. Luôn chọn class theo phiên bản Spring và Jackson thực tế của dự án.

### 4.2. Gửi data và metadata trong cùng một request

```java
import org.springframework.util.MimeType;

MimeType tenantMime = MimeType.valueOf(
        "application/vnd.acme.tenant+json");

Mono<OrderView> response = requester.route("orders.find")
        .metadata(new TenantContext("tenant-42"), tenantMime)
        .data(new OrderQuery("ORD-42"))
        .retrieveMono(OrderView.class);
```

Đây là đoạn mã minh họa, giả định ứng dụng đã khai báo `TenantContext`, `OrderQuery`, `OrderView` và đã cấu hình codec JSON. `route("orders.find")` tạo routing metadata; `.metadata(...)` thêm một entry tenant có MIME type riêng; `.data(...)` gửi đối tượng nghiệp vụ theo `dataMimeType` của connection.

### 4.3. Giải mã metadata tùy chỉnh ở phía nhận

`RSocketMessageHandler` hỗ trợ Composite Metadata và routing metadata mặc định. Metadata routing được giải mã thành giá trị có key `route`. Với MIME type tùy chỉnh, cần có decoder và đăng ký cách trích xuất qua `MetadataExtractorRegistry`.

```java
MimeType tenantMime = MimeType.valueOf(
        "application/vnd.acme.tenant+json");

RSocketStrategies strategies = RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
        .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
        .metadataExtractorRegistry(registry ->
                registry.metadataToExtract(
                        tenantMime, TenantContext.class, "tenant"))
        .build();
```

Khi cấu hình `RSocketMessageHandler`, truyền `RSocketStrategies` này vào handler để decoder và metadata extractor được sử dụng ở phía responder. Sau đó handler có thể nhận giá trị đã trích xuất như header:

```java
@MessageMapping("orders.find")
Mono<OrderView> find(
        @Payload OrderQuery query,
        @Header("tenant") TenantContext tenant) {
    // Xử lý query trong ngữ cảnh tenant đã được xác thực.
    return orderService.find(query, tenant);
}
```

`@Header("tenant")` chỉ hoạt động khi metadata entry đã được giải mã và ánh xạ thành key `tenant`. Nếu không đăng ký extractor, việc gửi entry không đồng nghĩa Spring tự động biến nó thành header.

## 5. Khi nào nên đặt thông tin vào data hoặc metadata?

- Đặt vào **data** khi đó là nội dung nghiệp vụ mà handler cần xử lý: command, query, DTO, event, kết quả trả về hoặc nội dung file.
- Đặt vào **metadata** khi đó là ngữ cảnh hoặc chỉ dẫn đi kèm message: route, token, tenant, trace id, correlation id, phiên bản giao thức hoặc thông tin điều khiển.
- Dùng **Composite Metadata** khi một request cần nhiều nhóm metadata độc lập, mỗi nhóm có thể dùng MIME type riêng.
- Dùng **một metadata document tùy chỉnh** khi hai đầu đã thống nhất một schema duy nhất và không cần ghép các entry độc lập. Khi đó cần decoder và logic trích xuất phù hợp.
- Giữ schema metadata ổn định, đặt tên MIME type tùy chỉnh rõ ràng và quản lý version khi cấu trúc thay đổi.

Không nên chuyển toàn bộ DTO nghiệp vụ sang metadata chỉ vì metadata hỗ trợ nhiều MIME type. Phần nội dung chính vẫn nên ở data để handler có một payload rõ ràng; metadata nên giữ vai trò bổ sung.

## 6. Lỗi thường gặp và cách kiểm tra

| Triệu chứng hoặc lỗi | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Lỗi giải mã JSON hoặc nhận sai kiểu object | Hai đầu khai báo data MIME type khác nhau, hoặc thiếu encoder/decoder JSON | Kiểm tra `dataMimeType` ở connection và codec JSON ở cả hai phía |
| Route không được tìm thấy | Metadata container không phải Composite Metadata như phía nhận mong đợi, hoặc routing entry sai định dạng | Kiểm tra `metadataMimeType` và entry `message/x.rsocket.routing.v0` |
| Metadata tùy chỉnh không xuất hiện trong `@Header` | Chưa đăng ký MIME type với `metadataExtractorRegistry`, hoặc chưa có decoder tương ứng | Đăng ký `metadataToExtract(mimeType, Target.class, "headerName")` và cấu hình decoder |
| Nhiều metadata entry không được giải mã | Đang dùng metadata MIME type đơn thay vì Composite Metadata | Dùng `message/x.rsocket.composite-metadata.v0` ở hai đầu |
| Client và server đọc cùng byte theo cách khác nhau | MIME type chỉ là nhãn; codec hoặc schema của hai phía không đồng nhất | Thống nhất MIME type, schema và phiên bản serializer |

Checklist khi debug:

1. Xác nhận `dataMimeType` và `metadataMimeType` của connection; phía server có thể đọc giá trị này từ thông tin `SETUP`.
2. Kiểm tra data MIME type có đúng với object gửi/nhận và encoder/decoder đã đăng ký hay chưa.
3. Nếu dùng Composite Metadata, xác nhận MIME type container là `message/x.rsocket.composite-metadata.v0` và từng entry có MIME type đúng.
4. Kiểm tra route có được gửi dưới dạng routing metadata; trong Spring, `.route(...)` đặt route vào metadata chứ không đặt vào data.
5. Với metadata tùy chỉnh, kiểm tra decoder, `metadataExtractorRegistry` và tên key được ánh xạ trước khi dùng `@Header`.
6. Khi cần quan sát tầng giao thức, kiểm tra riêng byte của `Payload.data()` và `Payload.metadata()`; đừng giải mã cả hai bằng cùng một codec nếu MIME type khác nhau.

Metadata có thể chứa token hoặc thông tin định danh. Hãy dùng transport bảo mật phù hợp (ví dụ TLS khi triển khai qua mạng không tin cậy), tránh ghi token nguyên văn vào log và áp dụng xác thực/ủy quyền ở phía nhận. Việc đặt token vào metadata không tự nó bảo vệ token.

## 7. Ghi nhớ

- `dataMimeType` = định dạng của nội dung data.
- `metadataMimeType` = định dạng của vùng metadata ở cấp connection.
- Với Composite Metadata, mỗi entry còn có MIME type riêng; đây là MIME type truyền vào `.metadata(value, mimeType)`.
- MIME type không thay thế encoder/decoder và không tự chuyển đổi dữ liệu.
- Spring mặc định dùng Composite Metadata và hỗ trợ routing; metadata tùy chỉnh cần decoder cùng cấu hình trích xuất.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework 6.2 API — RSocketRequester.Builder](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html)
- [Spring Framework 6.2 API — MetadataExtractorRegistry](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/rsocket/MetadataExtractorRegistry.html)
- [RSocket Protocol — Data and Metadata, SETUP](https://rsocket.io/about/protocol/)
- [RSocket Composite Metadata Extension](https://github.com/rsocket/rsocket/blob/master/Extensions/CompositeMetadata.md)