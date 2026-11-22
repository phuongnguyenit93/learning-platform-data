# setupRoute, setupData và setupMetadata trong RSocketRequester

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của frame **SETUP** trong quá trình mở một kết nối RSocket.
- Phân biệt dữ liệu và metadata cấp kết nối với dữ liệu và metadata của từng request.
- Cấu hình route, data và metadata ban đầu bằng **RSocketRequester.Builder**.
- Nhận và xử lý các giá trị này ở phía server bằng **@ConnectMapping**.
- Chọn MIME type, encoder, decoder và metadata extractor phù hợp.

## 1. Ba phương thức nằm ở đâu?

**setupRoute**, **setupData** và **setupMetadata** là các phương thức của **RSocketRequester.Builder**, không phải các phương thức của một request đã được tạo. Builder được lấy bằng:

~~~java
RSocketRequester.Builder builder = RSocketRequester.builder();
~~~

Các phương thức này cấu hình payload của frame **SETUP** được gửi khi client thiết lập một kết nối RSocket. Sau khi cấu hình xong, builder tạo requester thông qua một transport như TCP hoặc WebSocket:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .setupRoute("client.connect")
    .tcp("localhost", 7000);
~~~

Frame SETUP là bước bắt tay ban đầu của một kết nối. Nó có thể chứa data và metadata tùy chọn, đồng thời khai báo MIME type dùng cho data và metadata trên kết nối đó. Server có thể nhận hoặc từ chối kết nối dựa trên thông tin này. Khi kết nối đã được thiết lập, hai phía mới trao đổi các request như Request-Response, Request-Stream, Channel hoặc Fire-and-Forget.

Một requester có thể dùng chung một kết nối cho nhiều request. Việc gọi **tcp** hoặc **websocket** tạo requester nhưng không nhất thiết mở kết nối ngay; kết nối thường được thiết lập khi request đầu tiên được thực hiện. Vì vậy, các giá trị **setup*** thuộc về lần thiết lập kết nối, không tự động được gửi lại trong từng request.

## 2. So sánh ba phương thức

| Phương thức | Phần của SETUP payload | Mục đích |
|---|---|---|
| **setupRoute(String route, Object... routeVars)** | Metadata định tuyến | Gắn một route với sự kiện mở kết nối để server chọn handler kết nối |
| **setupData(Object data)** | Data | Gửi một giá trị ban đầu, chẳng hạn thông tin giới thiệu client |
| **setupMetadata(Object value, MimeType mimeType)** | Một mục metadata có MIME type riêng | Gửi ngữ cảnh cấp kết nối như thông tin tenant, client hoặc xác thực |

Cả ba đều là tùy chọn. Nếu không gọi một phương thức, phần tương ứng sẽ không được thiết lập trong SETUP payload.

## 3. setupRoute: route cho sự kiện mở kết nối

Chữ ký:

~~~java
setupRoute(String route, Object... routeVars)
~~~

**setupRoute** thêm một route vào metadata của frame SETUP. Phía server có thể dùng route này để chọn phương thức **@ConnectMapping** xử lý kết nối mới.

Route có thể chứa placeholder. Các giá trị truyền trong **routeVars** được chuyển thành chuỗi bằng **toString()** rồi thay vào placeholder:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .setupRoute("client.connect.{clientId}", "client-42")
    .tcp("localhost", 7000);
~~~

Route được gửi ở trên là **client.connect.client-42**. Quy tắc định dạng giống với **RSocketRequester.route**. Nếu một route variable chứa dấu chấm (**.**), Spring thay dấu chấm đó bằng **%2E** để tránh bị hiểu nhầm là dấu phân cách route ở phía responder.

Cần phân biệt hai cách đặt route:

- **setupRoute** định tuyến sự kiện SETUP ở cấp kết nối; server thường xử lý bằng **@ConnectMapping**.
- **requester.route** định tuyến một request cụ thể; server thường xử lý bằng **@MessageMapping**.

Do đó, thiết lập route trong SETUP không có nghĩa là mọi request sau đó đều dùng route đó. Mỗi request vẫn cần khai báo route riêng nếu giao thức ứng dụng yêu cầu.

Nếu server không cần phân loại kết nối theo route, có thể bỏ **setupRoute**. Một phương thức **@ConnectMapping** không khai báo pattern sẽ khớp với mọi payload SETUP và metadata push.

## 4. setupData: data ban đầu của kết nối

Chữ ký:

~~~java
setupData(Object data)
~~~

**setupData** đặt phần data trong SETUP payload. Giá trị được mã hóa theo **dataMimeType** đã cấu hình trên builder. Ví dụ:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.TEXT_PLAIN)
    .setupData("app=orders-ui;version=1")
    .tcp("localhost", 7000);
~~~

Ở đây, data ban đầu là một chuỗi văn bản. Phía server cần giải mã theo cùng MIME type và có thể nhận giá trị này như payload của **@ConnectMapping**.

Giá trị truyền vào có thể là một object cụ thể hoặc một producer tạo ra **một giá trị** có thể được chuyển đổi thành Reactive Streams Publisher thông qua **ReactiveAdapterRegistry**. Vì SETUP chỉ mang một payload ban đầu, hãy dùng một giá trị đơn hoặc một publisher đơn trị như **Mono**; không dùng **Flux** nhiều phần tử cho mục đích này.

Nếu không cấu hình **dataMimeType**, Spring suy ra MIME type từ decoder không mặc định đầu tiên đã đăng ký; nếu không có decoder không mặc định thì dùng decoder đầu tiên. Khi gửi object phức tạp như DTO hoặc JSON, client và server cần có encoder/decoder tương ứng trong **RSocketStrategies**. Chỉ đặt MIME type thành JSON không tự tạo ra encoder JSON.

Data MIME type được khai báo trong SETUP áp dụng cho data trên toàn bộ kết nối. Vì vậy, nếu chọn **text/plain** như ví dụ trên, data của các request gửi qua kết nối đó cũng cần tương thích với cấu hình này.

## 5. setupMetadata: metadata bổ sung của kết nối

Chữ ký:

~~~java
setupMetadata(Object value, MimeType mimeType)
~~~

**setupMetadata** thêm một mục metadata vào SETUP payload. Tham số thứ nhất là giá trị cần gửi; tham số thứ hai mô tả MIME type của chính mục metadata đó:

~~~java
MimeType tenantMimeType = MimeTypeUtils.TEXT_PLAIN;

RSocketRequester requester = RSocketRequester.builder()
    .setupMetadata("tenant=acme", tenantMimeType)
    .tcp("localhost", 7000);
~~~

Metadata có thể dùng để truyền thông tin gắn với toàn bộ kết nối, chẳng hạn client identifier, tenant context, thông tin xác thực hoặc dữ liệu khởi tạo phiên. Giá trị có thể là object cụ thể hoặc producer đơn trị có thể được thích nghi qua **ReactiveAdapterRegistry**. Encoder tương ứng phải hỗ trợ kiểu dữ liệu và MIME type đã chọn.

### Composite metadata và điều kiện kết hợp

Mặc định, **metadataMimeType** của RSocketRequester là:

~~~text
message/x.rsocket.composite-metadata.v0
~~~

Composite metadata cho phép một payload chứa nhiều mục metadata độc lập, mỗi mục có MIME type riêng. Route do **setupRoute** tạo ra cũng được mã hóa thành một mục routing metadata trong composite metadata.

Vì vậy, composite metadata phải được sử dụng khi:

- Gọi **setupMetadata** nhiều lần để thêm nhiều mục metadata.
- Kết hợp **setupMetadata** với **setupRoute**.

Nếu đặt **metadataMimeType** thành một MIME type đơn khác composite metadata, Spring giả định MIME type đó cũng là định dạng của route nếu route được cung cấp. Cấu hình như vậy không phù hợp để trộn route với nhiều mục metadata có định dạng riêng. Khi cần route cùng metadata bổ sung, hãy giữ composite metadata mặc định hoặc cấu hình rõ ràng MIME type composite ở cả hai phía.

MIME type của kết nối và MIME type của từng mục metadata có vai trò khác nhau:

- **metadataMimeType** xác định định dạng metadata tổng thể của kết nối.
- Tham số **mimeType** của **setupMetadata** xác định định dạng của một mục metadata cụ thể bên trong composite metadata.

## 6. Phía server nhận thông tin SETUP như thế nào?

Spring cung cấp **@ConnectMapping** để xử lý frame SETUP lúc bắt đầu kết nối và các thông báo metadata push tiếp theo. Annotation này hỗ trợ pattern route để chỉ nhận những kết nối có route phù hợp.

Các đối số của **@ConnectMapping** tương tự **@MessageMapping**, nhưng dữ liệu được lấy từ SETUP hoặc METADATA_PUSH:

- **@DestinationVariable** nhận biến được trích từ route.
- **@Payload** nhận data từ SETUP.
- **@Header** nhận metadata đã được **MetadataExtractor** giải mã và ánh xạ thành tên header.

Với metadata có MIME type tùy chỉnh, server cần có decoder phù hợp và đăng ký cách trích xuất metadata trong **RSocketStrategies**. Ví dụ, mục metadata dạng text/plain có thể được ánh xạ thành header **tenant-info**:

~~~java
@Bean
RSocketStrategies rsocketStrategies() {
    return RSocketStrategies.builder()
        .metadataExtractorRegistry(registry ->
            registry.metadataToExtract(
                MimeTypeUtils.TEXT_PLAIN,
                String.class,
                "tenant-info"))
        .build();
}
~~~

Đảm bảo **RSocketMessageHandler** phía server sử dụng **RSocketStrategies** này. Ví dụ handler:

~~~java
@Controller
class ClientConnectionController {

    @ConnectMapping("client.connect.{clientId}")
    Mono<Void> onConnect(
            @DestinationVariable String clientId,
            @Payload String setupData,
            @Header("tenant-info") String tenantInfo) {

        // Kiểm tra thông tin client và tenant trước khi chấp nhận kết nối.
        return Mono.empty();
    }
}
~~~

Pattern **client.connect.{clientId}** khớp với route do client gửi bằng **setupRoute**. **setupData** được nhận qua **@Payload**; mục metadata text/plain đã đăng ký được nhận qua header **tenant-info**.

Ở phía server, handler có thể trả về **void** hoặc **Mono<Void>**. Nếu xử lý SETUP kết thúc bằng lỗi, kết nối mới có thể bị từ chối. Không giữ quá trình xử lý kết nối chờ một request khác chạy qua chính kết nối đó; nếu cần khởi động request từ callback kết nối, hãy tách việc đó khỏi luồng xử lý SETUP.

## 7. Ví dụ kết hợp ở phía client

Ví dụ sau gửi một route, một data value và một mục metadata khi tạo requester:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

RSocketRequester requester = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.TEXT_PLAIN)
    .metadataMimeType(MimeTypeUtils.parseMimeType(
        "message/x.rsocket.composite-metadata.v0"))
    .setupRoute("client.connect.{clientId}", "client-42")
    .setupData("app=orders-ui;version=1")
    .setupMetadata("tenant=acme", MimeTypeUtils.TEXT_PLAIN)
    .tcp("localhost", 7000);
~~~

Khi kết nối được mở, SETUP payload chứa:

1. Route **client.connect.client-42** trong metadata định tuyến.
2. Data **app=orders-ui;version=1** được mã hóa bằng **text/plain**.
3. Mục metadata **tenant=acme** có MIME type **text/plain**, được đóng gói trong composite metadata.

Sau khi kết nối sẵn sàng, client tạo request thông thường bằng API cấp request:

~~~java
Mono<String> response = requester.route("orders.ping")
    .data("hello")
    .retrieveMono(String.class);
~~~

Trong ví dụ này, **orders.ping** và **hello** thuộc request riêng. Chúng không phải là route và data của frame SETUP.

## 8. Khi nào nên dùng từng phương thức?

| Nhu cầu | Nên dùng | Lý do |
|---|---|---|
| Chọn handler xử lý lúc client vừa kết nối | **setupRoute** | Route gắn với sự kiện SETUP và pattern của @ConnectMapping |
| Gửi một thông điệp giới thiệu client khi bắt tay | **setupData** | Data chỉ cần có ở cấp kết nối |
| Gửi tenant, client context hoặc thông tin xác thực ở cấp kết nối | **setupMetadata** | Metadata có MIME type riêng và có thể kết hợp nhiều mục bằng composite metadata |
| Gửi route, payload hoặc metadata thay đổi theo từng thao tác | **route**, **data**, **metadata** | Đây là các API cấp request, được áp dụng cho từng request |

Một giá trị phù hợp với SETUP thường là thông tin tương đối ổn định trong suốt vòng đời kết nối. Nếu token hoặc ngữ cảnh cần thay đổi theo từng request, hãy cân nhắc metadata cấp request hoặc thiết lập lại kết nối. Không xem một tenant ID do client gửi lên là bằng chứng xác thực; server vẫn phải kiểm tra danh tính và quyền truy cập. Nếu truyền thông tin nhạy cảm, cần bảo vệ transport phù hợp và tránh ghi giá trị bí mật vào log.

## 9. Lỗi thường gặp và cách xử lý

1. **Dùng setupRoute thay cho route ở mọi request.**  
   **setupRoute** chỉ khai báo route trong SETUP. Hãy gọi **requester.route(...)** cho từng request cần định tuyến.

2. **Mong setupData xuất hiện trong mọi request.**  
   **setupData** chỉ thuộc payload khởi tạo kết nối. Nếu một request cần payload riêng, dùng **data(...)** trên request spec.

3. **Kết hợp setupRoute và setupMetadata nhưng tắt composite metadata.**  
   Khi thêm metadata ngoài route, hãy dùng **message/x.rsocket.composite-metadata.v0**. Nếu không, route và các mục metadata riêng không thể được biểu diễn theo cách composite mà Spring mong đợi.

4. **Server không đọc được metadata tùy chỉnh.**  
   Kiểm tra MIME type, decoder và đăng ký trong **MetadataExtractorRegistry**. Một mục metadata được gửi đi không tự động trở thành một header có tên trong handler.

5. **Hai phía không thống nhất MIME type.**  
   Data MIME type và metadata MIME type được khai báo ở cấp kết nối. Client và server phải hỗ trợ cùng định dạng và codec tương ứng.

6. **Đưa Flux nhiều phần tử vào setupData hoặc setupMetadata.**  
   Hai phương thức này nhận một giá trị hoặc producer đơn trị. Dùng **Mono** nếu giá trị được tạo bất đồng bộ.

7. **Chờ request khác hoàn tất bên trong @ConnectMapping.**  
   **@ConnectMapping** xử lý SETUP trước khi các request thông thường có thể bắt đầu. Hãy hoàn tất xử lý kết nối nhanh chóng; nếu cần khởi chạy request, tách nó khỏi quá trình xử lý SETUP.

8. **Gửi token chỉ một lần nhưng kỳ vọng token tự được làm mới.**  
   Metadata trong SETUP được gửi cùng lần bắt tay kết nối. Nếu thông tin xác thực hết hạn hoặc thay đổi trong khi kết nối còn mở, cần có chiến lược làm mới, gửi metadata theo request hoặc thiết lập lại kết nối.

## 10. Checklist cấu hình

Trước khi chạy ứng dụng, kiểm tra:

- Các phương thức **setupRoute**, **setupData** và **setupMetadata** được gọi trên builder trước phương thức tạo requester như **tcp** hoặc **websocket**.
- Route client gửi khớp với pattern **@ConnectMapping** phía server.
- Data MIME type và metadata MIME type tương thích giữa hai phía.
- Nếu dùng **setupRoute** cùng **setupMetadata**, metadata tổng thể là composite.
- Encoder/decoder hỗ trợ các kiểu dữ liệu thực tế.
- Metadata MIME type tùy chỉnh đã được đăng ký trong **MetadataExtractorRegistry** nếu handler cần đọc nó qua **@Header**.
- Các giá trị đặt trong SETUP thực sự ổn định ở cấp kết nối; dữ liệu thay đổi theo request được gửi bằng API cấp request.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [RSocketRequester.Builder — Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html)
- [ConnectMapping — Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/annotation/ConnectMapping.html)
- [RSocketRequester — Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
