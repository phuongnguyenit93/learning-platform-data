# Routing metadata và quy ước tên route

> Phạm vi: dữ liệu RSocket trong Spring Framework, tập trung vào cách requester gửi route trong metadata, cách responder khớp route và cách đặt tên route ổn định.

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt route, data payload và metadata của một RSocket request.
- Giải thích MIME type `message/x.rsocket.routing.v0` và cấu trúc tag ở mức giao thức.
- Tạo request bằng `RSocketRequester.route(...)` và ánh xạ request bằng `@MessageMapping`.
- Chọn route matcher phù hợp, hiểu dấu chấm là ký tự phân cấp mặc định trong Spring RSocket.
- Đặt tên route nhất quán, có thể mở rộng và dễ quan sát trong log, metric, trace.

## 2. Route nằm ở đâu trong một RSocket message?

RSocket tách phần **data** và **metadata** trong payload. Data thường mang dữ liệu nghiệp vụ cần xử lý, còn metadata mang thông tin điều khiển hoặc mô tả request, chẳng hạn route, thông tin xác thực, tracing hay correlation id.

Ví dụ một request tìm sản phẩm có thể được hiểu như sau:

| Thành phần | Giá trị ví dụ | Vai trò |
| --- | --- | --- |
| Route metadata | `inventory.item.find.{sku}` với `sku = SKU-42` | Chọn handler sẽ nhận request |
| Data payload | `FindItemRequest` hoặc không có payload | Dữ liệu nghiệp vụ của request |
| Metadata khác | token, tenant, trace id | Ngữ cảnh bổ sung cho request |

Route là địa chỉ logic của handler trong ứng dụng. Route không phải URL HTTP, không chứa phần host, port hay transport. RSocket có thể chạy trên TCP hoặc WebSocket; cùng một route vẫn có thể được dùng qua các transport khác nhau.

Một kết nối RSocket bắt đầu bằng frame `SETUP`. Frame này khai báo MIME type dùng cho data và metadata trên kết nối. Khi requester bắt đầu một tương tác, route thường được gửi trong metadata của frame khởi tạo request: `REQUEST_RESPONSE`, `REQUEST_STREAM`, `REQUEST_CHANNEL` hoặc `REQUEST_FNF`. Với `REQUEST_CHANNEL`, route nằm ở phần khởi tạo stream; các payload tiếp theo thuộc cùng stream.

RSocket hỗ trợ bốn kiểu tương tác chính:

| Kiểu | Ý nghĩa | Ví dụ sử dụng |
| --- | --- | --- |
| Request-Response | Một request, một response | Tìm một sản phẩm |
| Request-Stream | Một request, nhiều response | Theo dõi giá hoặc trạng thái |
| Request-Channel | Hai phía trao đổi các stream | Đồng bộ dữ liệu hai chiều |
| Fire-and-Forget | Gửi một chiều, không chờ response nghiệp vụ | Gửi sự kiện telemetry |

Route xác định handler. Kiểu tương tác được xác định bởi frame RSocket và hình dạng input/output mà requester và handler sử dụng; chỉ đổi tên route không biến một request-response thành request-stream.

## 3. Routing metadata ở mức giao thức

RSocket định nghĩa Routing Metadata Extension với MIME type:

```text
message/x.rsocket.routing.v0
```

Extension hiện được đánh dấu là incubating ở phiên bản `0`. Điều này có nghĩa cấu trúc đã được mô tả để các implementation có thể tương tác, nhưng ứng dụng vẫn cần kiểm tra khả năng tương thích của thư viện và peer đang dùng.

Metadata routing chứa một hoặc nhiều tag. Mỗi tag gồm:

1. Một byte `Tag Length`: số byte của tag, là số nguyên unsigned 8-bit.
2. Phần `Tag`: chuỗi UTF-8 có đúng số byte đã khai báo.

Vì độ dài được biểu diễn bằng 8 bit, một tag có tối đa 255 byte UTF-8. Tag không kết thúc bằng byte NUL. Giới hạn tính theo byte sau khi mã hóa UTF-8, không phải số ký tự nhìn thấy.

Extension cho phép nhiều tag trong một metadata payload. Responder có thể dùng một tag, nhiều tag hoặc bỏ qua tag tùy theo logic ứng dụng. Các ví dụ hợp lệ ở mức giao thức có thể là `/person/1`, `person.1`, `ios-client` hoặc `android-client`; giao thức không bắt buộc một quy ước đặt tên duy nhất.

Trong Spring, `RSocketRequester.route(...)` cung cấp API cấp ứng dụng để tạo route cho request. API này nhận một chuỗi route và các biến route tùy chọn. Khi kết nối dùng composite metadata, Spring mã hóa route bằng MIME type routing ở trên.

## 4. Composite metadata và Spring Framework

Composite metadata cho phép một payload metadata chứa nhiều entry độc lập, mỗi entry có MIME type riêng. Nhờ vậy, cùng một request có thể mang route, token xác thực và metadata tracing mà không cần trộn chúng thành một chuỗi không có cấu trúc.

Spring Framework hỗ trợ composite metadata làm mặc định cho `RSocketRequester.Builder`. `RSocketMessageHandler` hỗ trợ composite metadata và routing metadata. Vì vậy, trong cấu hình Spring thông thường, ứng dụng có thể gửi route và các metadata entry khác trong cùng request.

Ví dụ thêm metadata xác thực khi gửi request:

```java
String token = obtainAccessToken();
MimeType authMimeType = MimeType.valueOf(
        "message/x.rsocket.authentication.bearer.v0");

Mono<Item> item = requester.route("inventory.item.find.{sku}", "SKU-42")
        .metadata(token, authMimeType)
        .retrieveMono(Item.class);
```

Đoạn code trên giả định encoder và cấu hình metadata tương ứng đã được đăng ký trong `RSocketStrategies`. MIME type của metadata phải được hai phía hiểu giống nhau. Không gửi token bí mật trong route vì route thường xuất hiện trong log, trace hoặc metric.

`DefaultMetadataExtractor` có hỗ trợ sẵn routing metadata. Nó giải mã route thành `String` và đặt giá trị dưới key `route` trong map metadata. Các MIME type khác cần decoder tương ứng và đăng ký với extractor, ví dụ:

```java
DefaultMetadataExtractor extractor =
        new DefaultMetadataExtractor(metadataDecoders);

extractor.metadataToExtract(fooMimeType, Foo.class, "foo");
```

Sau khi được trích xuất, metadata có thể được truy cập như header trong annotated handler, chẳng hạn bằng `@Header` hoặc `@Headers Map<String, Object>`. Việc đăng ký decoder chỉ giải quyết giải mã; ứng dụng vẫn phải kiểm tra giá trị và áp dụng chính sách bảo mật phù hợp.

## 5. Gửi và nhận route bằng Spring

### 5.1. Gửi request với RSocketRequester

`RSocketRequester` là API fluent để tạo request, gắn route, data và metadata, rồi khai báo kiểu response mong đợi. Ví dụ:

```java
Mono<Item> item = requester
        .route("inventory.item.find.{sku}", "SKU-42")
        .retrieveMono(Item.class);
```

`route(...)` bắt đầu một request với route đích. `retrieveMono(...)` khai báo rằng caller mong đợi một giá trị kiểu `Item`. Nếu cần gửi data, thêm `.data(requestObject)` trước `retrieveMono(...)`. Nếu mong đợi nhiều giá trị, dùng `retrieveFlux(...)`.

Route có thể là template với placeholder. Các biến truyền vào `route(...)` được format bằng `toString()` rồi thay vào placeholder. Nếu giá trị của một biến chứa dấu chấm `.`, Spring thay dấu chấm đó bằng `%2E` để nó không bị hiểu nhầm là dấu phân cách route. Hãy truyền giá trị gốc và để `RSocketRequester` xử lý việc escape; tránh tự encode trước rồi vô tình encode hai lần.

### 5.2. Ánh xạ route bằng @MessageMapping

Responder có thể khai báo handler bằng `@MessageMapping`. Ví dụ sau dùng Java 17 record và Reactor `Mono`: 

```java
record Item(String sku, String name) {}

@Controller
class InventoryResponder {

    @MessageMapping("inventory.item.find.{sku}")
    Mono<Item> find(@DestinationVariable String sku) {
        return Mono.just(new Item(sku, "Demo item"));
    }
}
```

Khi client gửi route `inventory.item.find.SKU-42`, Spring có thể khớp mẫu `inventory.item.find.{sku}` và đưa phần biến vào tham số `sku` thông qua `@DestinationVariable`. Ví dụ này minh họa handler; ứng dụng thực tế cần đăng ký responder với `RSocketMessageHandler` và cung cấp các bean, codec, transport cần thiết.

Trong Spring RSocket, `@MessageMapping` hỗ trợ một hoặc nhiều route pattern. Các tham số thường gặp gồm:

- `@Payload`: data payload của request; có thể là object, `Mono` hoặc `Flux` tùy kiểu tương tác.
- `@DestinationVariable`: giá trị được trích từ placeholder trong route pattern.
- `@Header`: một metadata value đã được `MetadataExtractor` giải mã và đăng ký.
- `@Headers Map<String, Object>`: các metadata value đã được trích xuất.
- `RSocketRequester`: requester gắn với kết nối hiện tại để gửi request về đầu bên kia.

### 5.3. Chọn route matcher

Theo cấu hình mặc định, `RSocketMessageHandler` dùng `SimpleRouteMatcher`, dựa trên `AntPathMatcher`. Spring khuyến nghị dùng `PathPatternRouteMatcher` từ module `spring-web` để khớp route hiệu quả hơn.

Cấu hình minh họa:

```java
@Bean
RSocketMessageHandler rSocketMessageHandler() {
    RSocketMessageHandler handler = new RSocketMessageHandler();
    handler.routeMatcher(new PathPatternRouteMatcher());
    return handler;
}
```

Cả hai matcher được cấu hình mặc định với dấu chấm `.` làm separator. Vì vậy route có cấu trúc phân cấp như `inventory.item.find` phù hợp với mặc định của Spring. Route RSocket có thể phân cấp nhưng không phải URL path: Spring không tự thực hiện URL decoding như khi xử lý HTTP URL.

Nếu hệ thống chọn quy ước dùng dấu `/`, hãy xác định rõ route matcher và cách encode/decode ở cả hai phía. Đừng giả định rằng `/items/42` sẽ tự động có cùng ngữ nghĩa pattern với một HTTP endpoint.

### 5.4. @RSocketExchange và @ConnectMapping

`@RSocketExchange` là lựa chọn khác để khai báo RSocket service bằng Java interface. Method-level route phải là một route cụ thể; annotation ở cấp interface có thể khai báo prefix dùng chung. Điều này phù hợp khi muốn chia sẻ contract giữa requester proxy và responder.

`@ConnectMapping` dành cho sự kiện ở cấp kết nối: frame `SETUP` khi kết nối bắt đầu và metadata notification qua `METADATA_PUSH`. Nó không thay thế `@MessageMapping` cho từng request thông thường. `@ConnectMapping` không trả data và method phải có kiểu trả về `void` hoặc `Mono<Void>`.

## 6. Quy ước đặt tên route

RSocket không bắt buộc ứng dụng phải đặt route theo một mẫu duy nhất. Đây là quy ước của hệ thống, vì vậy cần thống nhất giữa requester, responder, tài liệu API, log và kiểm thử.

### 6.1. Mẫu đề xuất

Với Spring matcher mặc định, ưu tiên route phân cấp bằng dấu chấm:

```text
<domain>.<resource>.<action>
<domain>.<resource>.<action>.{variable}
```

Ví dụ:

| Route | Ý nghĩa |
| --- | --- |
| `inventory.item.find.{sku}` | Tìm một item theo SKU |
| `inventory.item.create` | Tạo item |
| `inventory.item.reserve` | Đặt trước item |
| `inventory.stock.watch.{warehouseId}` | Theo dõi tồn kho của một kho |
| `billing.invoice.get.{invoiceId}` | Lấy hóa đơn theo ID |
| `identity.session.revoke` | Thu hồi session |

Mỗi segment nên có một vai trò rõ ràng. Prefix domain giúp tránh trùng tên khi một ứng dụng có nhiều nhóm chức năng; resource chỉ ra đối tượng nghiệp vụ; action mô tả thao tác.

### 6.2. Quy tắc thực hành

1. Dùng chữ thường và một bộ ký tự nhất quán, thường là chữ cái ASCII, chữ số và dấu chấm phân cấp. Quy ước đơn giản giúp giảm khác biệt giữa ngôn ngữ và hệ thống.
2. Chọn một cách viết cho resource, ví dụ dùng danh từ số ít `item`, `invoice`, `session`, rồi áp dụng đồng nhất.
3. Dùng động từ cụ thể cho action như `find`, `create`, `reserve`, `watch`, `revoke`. Tránh tên chung chung như `process`, `handle` hoặc `do` nếu không thể hiện được ý nghĩa nghiệp vụ.
4. Giữ route ổn định theo contract. Thay đổi cấu trúc nội bộ của class hoặc package không nên buộc client đổi route.
5. Đưa ID và giá trị biến vào placeholder, không ghép chúng vào tên route tĩnh. Ví dụ dùng `inventory.item.find.{sku}` thay vì tạo route riêng cho từng SKU.
6. Không trộn tùy tiện dấu chấm và dấu gạch chéo trong cùng một namespace. Chọn một convention và cấu hình matcher tương ứng.
7. Không đặt token, mật khẩu, dữ liệu cá nhân hoặc payload nghiệp vụ dài trong route. Dùng metadata riêng cho ngữ cảnh và data payload cho nội dung nghiệp vụ.
8. Chỉ đưa version vào route khi cần duy trì các contract không tương thích song song, ví dụ `billing.v2.invoice.get`. Không tăng version chỉ vì refactor nội bộ.
9. Giữ route có cardinality thấp và ổn định để log, metric và trace có thể nhóm theo route pattern. Không tạo route tĩnh mới cho từng user hoặc từng record.
10. Ghi rõ route, payload type, kiểu tương tác RSocket và metadata bổ sung trong tài liệu contract.

Đây là quy ước thiết kế được khuyến nghị, không phải yêu cầu bắt buộc của RSocket protocol. Điều bắt buộc là hai phía phải thống nhất route thực tế, format metadata và cách diễn giải route.

### 6.3. Route pattern và biến

Nên giữ phần cố định của route để biểu thị chức năng, còn phần thay đổi đặt trong placeholder:

```text
inventory.item.find.{sku}
inventory.warehouse.stock.{warehouseId}
billing.invoice.get.{invoiceId}
```

Với route `inventory.item.find.{sku}`, route pattern cho biết handler cần tìm item; giá trị `sku` chỉ là tham số định danh. Cách tách này giúp nhiều request đi qua cùng một handler pattern và giảm số lượng route cần quản lý.

Dấu chấm là separator mặc định trong Spring RSocket. Vì vậy, một biến route có dấu chấm cần được escape theo quy tắc của `RSocketRequester`. Nếu tự tạo payload routing ở mức thấp bằng RSocket Java, cần tự bảo đảm chuỗi tag và cách escape nhất quán với matcher của responder.

## 7. Ví dụ luồng request hoàn chỉnh

Giả sử service Inventory cung cấp thao tác tìm item. Client và server thống nhất contract:

- Route: `inventory.item.find.{sku}`
- Route variable: `sku`
- Request payload: không bắt buộc trong ví dụ này
- Response: một `Item`
- Interaction: Request-Response

Handler:

```java
record Item(String sku, String name) {}

@Controller
class InventoryResponder {

    @MessageMapping("inventory.item.find.{sku}")
    Mono<Item> find(@DestinationVariable String sku) {
        return Mono.just(new Item(sku, "Demo item"));
    }
}
```

Requester:

```java
Mono<Item> result = requester
        .route("inventory.item.find.{sku}", "SKU-42")
        .retrieveMono(Item.class);
```

Khi request được thực hiện, Spring tạo routing metadata cho route đã mở rộng. Responder giải mã metadata, trích xuất route, tìm mapping phù hợp, bind `SKU-42` vào `sku`, gọi handler và encode kết quả thành response payload. `Mono<Item>` biểu thị một response; nếu handler trả `Flux<Item>` thì contract sẽ là một stream response.

Để gửi payload nghiệp vụ, thêm `.data(request)` ở requester và nhận payload tương ứng bằng `@Payload` ở handler. Không nên nhét object JSON vào route; route chỉ nên định tuyến đến handler.

## 8. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Không tìm thấy handler | Route client và `@MessageMapping` không khớp | So sánh route sau khi mở rộng biến với mapping pattern |
| Route bị tách sai segment | Dùng dấu chấm trong biến hoặc quy ước separator không thống nhất | Kiểm tra matcher và cách `RSocketRequester` escape biến |
| Metadata không giải mã được | MIME type hoặc format metadata không khớp | Kiểm tra `metadataMimeType` trong `SETUP` và cấu hình metadata extractor |
| Metadata tùy chỉnh không có trong handler | Chưa đăng ký decoder hoặc `metadataToExtract` | Kiểm tra `RSocketStrategies` và `MetadataExtractor` |
| Route hoạt động ở một client nhưng không ở client khác | Hai phía dùng convention hoặc metadata MIME type khác nhau | Kiểm tra contract route, MIME type và phiên bản thư viện |
| Dùng `METADATA_PUSH` nhưng mong đợi gọi handler request | Nhầm metadata cấp kết nối với metadata của request | Dùng `@ConnectMapping` cho metadata push; dùng `@MessageMapping` cho request |
| Metric tạo quá nhiều series | Gắn ID hoặc giá trị động vào tên route tĩnh | Dùng route pattern ổn định và ghi ID ở field riêng |

Quy trình debug thực tế:

1. Xác nhận kết nối đã hoàn tất `SETUP` và hai phía thống nhất data/metadata MIME type.
2. Xác định frame mở đầu request là `REQUEST_RESPONSE`, `REQUEST_STREAM`, `REQUEST_CHANNEL` hay `REQUEST_FNF`.
3. Kiểm tra metadata của frame mở đầu có routing entry với MIME type `message/x.rsocket.routing.v0` hay không.
4. Đọc route sau khi các biến đã được mở rộng; đối chiếu chính xác với `@MessageMapping` hoặc route khai báo trong `@RSocketExchange`.
5. Kiểm tra separator và route matcher ở responder.
6. Nếu có metadata khác, xác nhận MIME type, encoder, decoder và registration trong `MetadataExtractor`.
7. Kiểm tra log/trace mà không ghi token hoặc dữ liệu nhạy cảm.

## 9. Checklist khi thiết kế route

- [ ] Route có prefix domain hoặc namespace rõ ràng.
- [ ] Các segment dùng cùng một quy ước chữ thường và separator.
- [ ] Tên route mô tả resource và action cụ thể.
- [ ] Giá trị động được khai báo bằng placeholder và route variable.
- [ ] Requester và responder dùng cùng route pattern.
- [ ] Matcher của Spring được cấu hình với separator phù hợp.
- [ ] Metadata MIME type và composite metadata được hai phía hỗ trợ.
- [ ] Metadata tùy chỉnh đã có encoder, decoder và registration cần thiết.
- [ ] Route không chứa token hoặc payload nghiệp vụ.
- [ ] Có kiểm thử tích hợp cho route, biến route và kiểu tương tác tương ứng.

## 10. Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): RSocketRequester, annotated responders, route matcher, MetadataExtractor và RSocket Interface.
- [Spring Framework Javadoc — RSocketRequester](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html): hợp đồng `route(String, Object...)`, template variable và quy tắc escape dấu chấm.
- [RSocket Routing Metadata Extension](https://github.com/rsocket/rsocket/blob/master/Extensions/Routing.md): MIME type, tag encoding và giới hạn độ dài tag.
- [RSocket Protocol](https://github.com/rsocket/rsocket/blob/master/Protocol.md): SETUP, request frames, payload data và metadata.

Khi triển khai, hãy đối chiếu tài liệu theo đúng phiên bản Spring Framework và RSocket Java mà ứng dụng đang dùng; các ví dụ trên mô tả API Spring hiện hành và quy ước route ở cấp ứng dụng.
