# dataMimeType, metadataMimeType và thương lượng dữ liệu

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt phần Data và Metadata trong một RSocket payload.
- Giải thích vai trò của `dataMimeType` và `metadataMimeType`.
- Hiểu hai MIME type được khai báo ở đâu, có phạm vi áp dụng thế nào và Spring chọn giá trị mặc định ra sao.
- Cấu hình Encoder, Decoder và `RSocketStrategies` để hai đầu trao đổi dữ liệu cùng định dạng.
- Gửi metadata bổ sung, đăng ký giải mã metadata tùy chỉnh và nhận giá trị đó ở responder.

## 1. Data và Metadata là hai phần khác nhau của payload

Một RSocket payload có thể chứa hai phần độc lập:

| Phần | Dùng để làm gì? | Ví dụ |
|---|---|---|
| Data | Nội dung nghiệp vụ mà request hoặc response cần truyền | `OrderQuery`, `OrderView`, chuỗi, byte array |
| Metadata | Thông tin mô tả hoặc điều khiển cách xử lý message | route, tenant, token xác thực, tracing context |

Ví dụ khi gọi `orders.find`:

- Data có thể là `{"orderId":"ORD-100"}`.
- Metadata có thể chứa route `orders.find` và tenant `tenant-42`.

Data và Metadata có thể dùng các định dạng khác nhau. Vì vậy RSocket khai báo MIME type cho từng phần riêng biệt.

MIME type là nhãn mô tả định dạng hoặc cấu trúc dữ liệu, chẳng hạn:

- `application/json`: dữ liệu JSON.
- `application/cbor`: dữ liệu CBOR.
- `application/octet-stream`: dữ liệu nhị phân.
- `message/x.rsocket.composite-metadata.v0`: metadata dạng composite của RSocket.
- `message/x.rsocket.routing.v0`: metadata chứa route theo phần mở rộng Routing của RSocket.

RSocket protocol không tự chuyển JSON sang CBOR hay diễn giải cấu trúc nghiệp vụ. Việc mã hóa và giải mã thuộc về ứng dụng và các codec mà ứng dụng đăng ký.

## 2. dataMimeType: định dạng của phần Data

`dataMimeType` xác định MIME type dùng để mã hóa phần Data trên một kết nối RSocket.

Trong Spring, cấu hình này nằm trên `RSocketRequester.Builder`:

```java
RSocketRequester requester = RSocketRequester.builder()
        .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
        .tcp("localhost", 7000);
```

Khi đặt `application/json`, hai phía phải có Encoder và Decoder phù hợp để chuyển đổi giữa object Java và JSON bytes.

Điểm cần nhớ:

1. MIME type được gửi trong frame `SETUP` khi thiết lập kết nối.
2. MIME type này áp dụng cho Data của các request trên kết nối đó, không phải một lựa chọn riêng cho từng lần gọi `route(...)`.
3. MIME type không tự tạo ra codec. Nếu chọn JSON nhưng không có Encoder/Decoder JSON phù hợp, việc ghi hoặc đọc object sẽ thất bại.
4. Nếu không đặt rõ, Spring lấy MIME type từ Decoder không mặc định đầu tiên đã cấu hình; nếu không có thì lấy từ Decoder đầu tiên. Vì vậy giá trị mặc định phụ thuộc vào danh sách codec thực tế, không nên mặc định rằng mọi ứng dụng đều dùng JSON.

Nên đặt MIME type tường minh khi kết nối với hệ thống khác, đặc biệt khi hai bên dùng thư viện hoặc cấu hình codec khác nhau.

## 3. metadataMimeType: định dạng bao ngoài của phần Metadata

`metadataMimeType` xác định cách mã hóa phần Metadata của payload trên kết nối.

Spring Framework mặc định dùng:

`message/x.rsocket.composite-metadata.v0`

Đây là định dạng Composite Metadata. Nó cho phép một phần Metadata chứa nhiều entry độc lập; mỗi entry có MIME type và nội dung riêng. Cách này phù hợp khi một request cần đồng thời có route, thông tin xác thực, tenant hoặc tracing.

Ví dụ một request có thể có:

| Metadata entry | MIME type | Ý nghĩa |
|---|---|---|
| Route | `message/x.rsocket.routing.v0` | Chọn handler `orders.find` |
| Tenant | `text/plain` | Mã tenant |
| Authentication | `message/x.rsocket.authentication.bearer.v0` | Bearer token |

Vì vậy cần phân biệt hai khái niệm:

- `metadataMimeType`: định dạng bao ngoài của toàn bộ vùng Metadata trên kết nối.
- MIME type truyền vào `metadata(value, mimeType)`: định dạng của một entry riêng bên trong Composite Metadata.

Khi dùng Composite Metadata, Spring có thể kết hợp route với nhiều metadata entry khác nhau. Nếu đổi `metadataMimeType` sang một MIME type đơn khác, Spring xem MIME type đó là định dạng của route nếu request có route. Khi đó không còn cơ chế composite để ghép nhiều entry độc lập. Chỉ thay đổi mặc định này khi hệ thống đối tác yêu cầu một định dạng metadata đơn cụ thể và hai phía đã thống nhất cách giải mã.

## 4. Thương lượng MIME type diễn ra ở cấp kết nối

Trong RSocket, việc thống nhất định dạng Data và Metadata gắn với quá trình thiết lập kết nối:

1. Client mở transport như TCP hoặc WebSocket.
2. Client gửi frame `SETUP`. Frame này khai báo MIME type cho Data và Metadata, cùng các tham số thiết lập kết nối khác.
3. Server xử lý `SETUP`. Server có thể chấp nhận kết nối hoặc từ chối thiết lập nếu không thể làm việc với cấu hình được yêu cầu.
4. Sau khi kết nối được thiết lập, hai phía trao đổi request và response theo các MIME type đã khai báo.

Do đó, từ “thương lượng” ở đây nên được hiểu là hai phía thống nhất hợp đồng định dạng ở cấp kết nối. Đây không phải cơ chế HTTP content negotiation:

- Không có lựa chọn `Accept` mới cho từng request RSocket.
- RSocket không tự chọn codec tốt nhất dựa trên class Java.
- Một kết nối không tự đổi `dataMimeType` giữa các message.
- Hai phía phải có codec tương thích với MIME type đã thống nhất.

Nếu cần trao đổi nhiều định dạng Data khác nhau, hãy thiết kế hợp đồng rõ ràng: dùng các kết nối có cấu hình MIME type phù hợp hoặc dùng một envelope nghiệp vụ có trường nhận diện định dạng. Không nên kỳ vọng `dataMimeType` tự thay đổi theo từng message.

## 5. Encoder, Decoder và RSocketStrategies

MIME type chỉ mô tả định dạng. Encoder và Decoder mới thực hiện việc chuyển đổi dữ liệu:

- Encoder: object Java → DataBuffer/bytes để gửi đi.
- Decoder: DataBuffer/bytes → object Java khi nhận về.

Spring gom các thành phần này trong `RSocketStrategies`. `RSocketRequester.Builder` sử dụng strategies để mã hóa Data, Metadata và giải mã response.

Các codec cơ bản từ `spring-core` hỗ trợ `String`, `byte[]` và `ByteBuffer`. Khi cần JSON, CBOR hoặc Protobuf, hãy bổ sung codec tương ứng; các triển khai JSON/CBOR của Jackson nằm trong `spring-web`.

Ví dụ cấu hình JSON cho ứng dụng Spring Framework 6.1:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.util.MimeTypeUtils;

@Configuration
class RSocketClientConfiguration {

    @Bean
    RSocketStrategies rsocketStrategies() {
        return RSocketStrategies.builder()
                .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
                .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
                .build();
    }

    @Bean
    RSocketRequester rsocketRequester(RSocketStrategies strategies) {
        return RSocketRequester.builder()
                .rsocketStrategies(strategies)
                .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
                .metadataMimeType(MimeTypeUtils.parseMimeType(
                        "message/x.rsocket.composite-metadata.v0"))
                .tcp("localhost", 7000);
    }
}
```

Đây là cấu hình bean dùng bên trong một ứng dụng Spring, không phải chương trình độc lập chạy chỉ bằng `javac`. Cần có các dependency Spring Messaging, Spring Web với Jackson và RSocket transport phù hợp. Phía responder cũng cần cấu hình Encoder/Decoder tương thích; nếu dùng cùng một ứng dụng, có thể tái sử dụng một bean `RSocketStrategies`.

Trong ví dụ, `dataMimeType` được đặt rõ là JSON. `metadataMimeType` được đặt rõ là Composite Metadata dù đây cũng là mặc định của Spring, để thể hiện hợp đồng kết nối. Việc tạo `RSocketRequester` chưa nhất thiết mở kết nối ngay; kết nối dùng chung được thiết lập khi có request thực sự.

## 6. Gửi Data và nhiều metadata entry trong một request

Giả sử client cần tìm đơn hàng theo mã và gửi thêm tenant:

```java
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;

record OrderQuery(String orderId) {}
record OrderView(String orderId, String status) {}

Mono<OrderView> result = requester.route("orders.find")
        .metadata("tenant-42", MimeTypeUtils.TEXT_PLAIN)
        .data(new OrderQuery("ORD-100"))
        .retrieveMono(OrderView.class);
```

Trong đoạn code:

- `route("orders.find")` tạo routing metadata để responder tìm đúng handler.
- `metadata("tenant-42", MimeTypeUtils.TEXT_PLAIN)` thêm một metadata entry có MIME type `text/plain`.
- `data(new OrderQuery(...))` gửi object nghiệp vụ. Với cấu hình ở phần trước, object này được mã hóa thành JSON.
- `retrieveMono(OrderView.class)` khai báo kiểu response mong đợi và trả về `Mono<OrderView>`.

Lời gọi này dùng được vì metadata mặc định là Composite Metadata. Giá trị tenant là một metadata entry riêng, không bị trộn vào object `OrderQuery`.

## 7. Giải mã metadata ở responder

Responder cần biết MIME type nào cần đọc và tên nào sẽ được gán cho giá trị đã giải mã. Spring cung cấp `MetadataExtractorRegistry` thông qua `RSocketStrategies.Builder`.

Ví dụ đăng ký metadata `text/plain` thành header `tenantId`:

```java
RSocketStrategies serverStrategies = RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
        .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
        .metadataExtractorRegistry(registry ->
                registry.metadataToExtract(
                        MimeTypeUtils.TEXT_PLAIN,
                        String.class,
                        "tenantId"))
        .build();

RSocketMessageHandler handler = new RSocketMessageHandler();
handler.setRSocketStrategies(serverStrategies);
```

Khi dùng chiến lược này cho responder, Spring vẫn có hỗ trợ route mặc định và đồng thời biết cách giải mã metadata tenant. Handler có thể nhận giá trị qua `@Header`:

```java
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import reactor.core.publisher.Mono;

@MessageMapping("orders.find")
Mono<OrderView> find(
        @Payload OrderQuery query,
        @Header("tenantId") String tenantId) {

    return Mono.just(new OrderView(query.orderId(), "ACCEPTED"));
}
```

Đây là phần minh họa handler; trong ứng dụng thật, kết quả thường đến từ service hoặc repository. Nếu metadata dùng MIME type tùy chỉnh, cần có Decoder hỗ trợ MIME type đó và đăng ký nó với `metadataToExtract(...)`. Chỉ gửi metadata từ client là chưa đủ để responder tự biết cách chuyển bytes thành giá trị Java.

## 8. Khi nào nên giữ mặc định và khi nào nên đổi?

| Tình huống | Cách cấu hình |
|---|---|
| Hai phía dùng JSON cho object nghiệp vụ | Đặt `dataMimeType(application/json)` và đăng ký Jackson JSON Encoder/Decoder ở cả hai phía |
| Cần route cùng token, tenant hoặc tracing | Giữ `message/x.rsocket.composite-metadata.v0` |
| Chỉ gửi `String` hoặc `byte[]` | Codec cơ bản có thể đủ; vẫn cần thống nhất MIME type |
| Đối tác bắt buộc dùng một metadata format đơn | Đặt `metadataMimeType` theo hợp đồng và cấu hình cách đọc route/metadata tương ứng |
| Metadata có kiểu dữ liệu riêng | Đăng ký Encoder khi gửi, Decoder và MetadataExtractor khi nhận |

Thông thường, hãy giữ Composite Metadata và chỉ đổi `dataMimeType` khi cần chọn định dạng Data cụ thể hoặc cần bảo đảm hợp đồng với hệ thống khác.

## 9. Lỗi thường gặp và cách kiểm tra

**Client gửi JSON nhưng responder không đọc được object**

- Kiểm tra `dataMimeType` ở frame `SETUP`.
- Kiểm tra cả hai phía đều có JSON Encoder/Decoder tương thích.
- Kiểm tra cấu hình có dùng đúng `RSocketStrategies` hay không.
- Không giả định rằng có Jackson trong classpath thì mọi `RSocketStrategies` đều tự đăng ký codec JSON.

**Route hoạt động nhưng metadata tùy chỉnh không xuất hiện trong handler**

- Kiểm tra kết nối có dùng Composite Metadata hay không.
- Kiểm tra MIME type của metadata entry khi gửi.
- Kiểm tra Decoder hỗ trợ đúng MIME type và kiểu đích.
- Đăng ký entry bằng `metadataExtractorRegistry(...)` và đọc đúng tên bằng `@Header("tenantId")`.

**Đã đặt metadataMimeType nhưng vẫn không gửi được nhiều metadata entry**

- Kiểm tra giá trị có còn là `message/x.rsocket.composite-metadata.v0` hay không.
- Một metadata format đơn không có cấu trúc entry độc lập như Composite Metadata.
- Nếu gọi `setupMetadata(...)` nhiều lần hoặc kết hợp `setupRoute(...)` với `setupMetadata(...)`, Composite Metadata phải được sử dụng.

**Hai ứng dụng dùng MIME type giống nhau nhưng vẫn không tương thích**

- MIME type giống nhau chưa bảo đảm hai codec có cùng cách biểu diễn dữ liệu.
- Kiểm tra schema, kiểu dữ liệu, cấu hình Jackson, phiên bản và quy tắc xử lý null/field.
- Kiểm tra cả chiều request và response; hai bên đều cần khả năng encode/decode tương ứng.

## 10. Quy trình cấu hình đề xuất

1. Xác định định dạng Data mà hai ứng dụng sẽ dùng, ví dụ JSON hoặc CBOR.
2. Đăng ký Encoder và Decoder tương ứng trong `RSocketStrategies` ở cả hai phía.
3. Đặt `dataMimeType` rõ ràng nếu cần hợp đồng ổn định hoặc kết nối liên ngôn ngữ.
4. Giữ Composite Metadata nếu cần route và nhiều metadata entry.
5. Đăng ký Decoder và MetadataExtractor cho từng metadata MIME type tùy chỉnh.
6. Kiểm thử request, response, route và metadata trên kết nối thật giữa hai đầu.

## Kết luận

`dataMimeType` mô tả cách mã hóa Data; `metadataMimeType` mô tả cách mã hóa vùng Metadata. Cả hai được khai báo ở cấp kết nối trong frame `SETUP`. Trong Spring, `RSocketStrategies` cung cấp Encoder/Decoder, còn `MetadataExtractor` giúp responder biến metadata thành các giá trị có thể truy cập qua header.

Hãy xem MIME type, codec và schema là một phần của hợp đồng giữa requester và responder. Khi cả hai phía thống nhất đủ ba yếu tố này, dữ liệu nghiệp vụ và metadata mới được trao đổi chính xác.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework 6.1 — RSocketRequester.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html)
- [Spring Framework 6.1 — RSocketStrategies.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.Builder.html)
- [RSocket Protocol — SETUP frame](https://github.com/rsocket/rsocket/blob/master/Protocol.md#setup-frame)
