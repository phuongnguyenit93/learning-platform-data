# MetadataExtractor và ánh xạ metadata thành header

## Mục tiêu

Trong RSocket, metadata đi kèm payload có thể mang route, thông tin xác thực, tenant, trace hoặc ngữ cảnh của request. Spring Framework cung cấp **MetadataExtractor** để giải mã metadata thành các cặp tên–giá trị, sau đó đưa chúng vào **headers của Spring Message**. Nhờ vậy, handler có thể nhận dữ liệu bằng **@Header** hoặc đọc toàn bộ bằng **@Headers**, thay vì tự phân tích byte metadata trong từng phương thức.

Sau bài này, bạn có thể:

- Phân biệt data và metadata trong một RSocket payload.
- Giải thích vai trò của MetadataExtractor, DefaultMetadataExtractor và MetadataExtractorRegistry.
- Đăng ký MIME type cùng Decoder để Spring giải mã metadata tùy chỉnh.
- Ánh xạ một metadata object thành một header hoặc nhiều header.
- Gửi metadata bằng RSocketRequester và nhận metadata trong @MessageMapping.
- Nhận biết lỗi thường gặp và các giới hạn về bảo mật, kiểu dữ liệu.

## 1. Data, metadata và Spring Message headers

Một RSocket request có hai phần độc lập:

- **Data**: payload chính của nghiệp vụ, ví dụ OrderCommand, nội dung chat hoặc một đối tượng cần xử lý.
- **Metadata**: thông tin mô tả request, ví dụ route, token, tenantId, traceId hoặc phiên bản giao thức.

Metadata không phải HTTP header. Đây là phần riêng trong RSocket Payload. Mỗi metadata entry có thể có định dạng riêng, được nhận diện bằng MIME type. Khi dùng composite metadata, một payload có thể chứa nhiều entry với các MIME type khác nhau, chẳng hạn một entry cho routing và một entry cho request context.

Luồng xử lý ở phía nhận có thể hình dung như sau:

~~~text
RSocket Payload
├── Data: OrderCommand
└── Metadata (composite)
    ├── message/x.rsocket.routing.v0
    │   └── route = "orders.create"
    └── application/vnd.acme.request-context+json
        └── {"tenantId":"acme","traceId":"req-001"}
                    |
                    v
             MetadataExtractor
                    |
                    v
          Map<String, Object>
                    |
                    v
       Spring Message headers
                    |
          +---------+---------+
          |                   |
    @Header("tenantId")   @Headers Map
~~~

**MetadataExtractor** là strategy nhận RSocket Payload cùng MIME type của metadata, rồi trả về Map<String, Object>. Spring dùng các cặp tên–giá trị đó làm headers của Message được chuyển tới handler. Vì vậy, handler làm việc với kiểu Java đã giải mã thay vì byte metadata thô.

Cần phân biệt ba khái niệm:

| Thành phần | Trách nhiệm |
|---|---|
| MIME type | Cho biết định dạng của metadata entry, ví dụ JSON hoặc routing metadata |
| Decoder | Chuyển dữ liệu đã mã hóa thành đối tượng Java |
| MetadataExtractor | Chọn metadata cần đọc, dùng Decoder phù hợp và đặt kết quả vào Map theo tên header |

Metadata chỉ trở thành header ứng dụng khi extractor có thể nhận diện và giải mã entry đó. Việc gửi một MIME type tùy chỉnh từ client tự nó chưa đủ để tạo ra header ở server.

## 2. MetadataExtractor mặc định

Spring cung cấp **DefaultMetadataExtractor**, một implementation của MetadataExtractor và MetadataExtractorRegistry. Nó sử dụng các Decoder đã cấu hình để giải mã metadata.

Mặc định, extractor hỗ trợ routing metadata có MIME type:

~~~text
message/x.rsocket.routing.v0
~~~

Giá trị route được giải mã thành String và lưu dưới khóa **route**, tương ứng với **MetadataExtractor.ROUTE_KEY**. RSocketMessageHandler dùng route để tìm phương thức @MessageMapping phù hợp.

Ví dụ, client gửi route orders.create thì route được đưa vào quá trình chọn handler. Route này là thông tin định tuyến của RSocket; không nên nhầm nó với tenantId hoặc traceId của ứng dụng.

Các MIME type khác cần được đăng ký rõ ràng. Ví dụ, nếu client gửi metadata dạng JSON với MIME type application/vnd.acme.request-context+json, server cần:

1. Có Decoder hỗ trợ JSON.
2. Đăng ký MIME type đó với kiểu Java đích.
3. Chỉ định tên header hoặc hàm ánh xạ kết quả vào nhiều header.

Nếu không đăng ký, metadata tùy chỉnh không tự xuất hiện dưới dạng các header ứng dụng mà handler mong đợi.

## 3. Hai cách ánh xạ metadata thành header

MetadataExtractorRegistry cung cấp các overload của **metadataToExtract**. Có hai cách dùng chính.

### 3.1. Đưa toàn bộ object vào một header

Khi metadata được giải mã thành một object, có thể gắn object đó dưới một tên:

~~~java
registry.metadataToExtract(
        CLIENT_CONTEXT_MIME,
        ClientContext.class,
        "clientContext");
~~~

Sau đó handler nhận object bằng:

~~~java
@MessageMapping("orders.create")
public Mono<String> create(
        @Header("clientContext") ClientContext context) {
    return Mono.just(context.tenantId());
}
~~~

Cách này phù hợp khi các trường thuộc cùng một khái niệm và handler muốn nhận một object có kiểu rõ ràng.

### 3.2. Tách một object thành nhiều header

Khi metadata chứa nhiều trường độc lập, overload nhận mapper cho phép đưa từng trường vào Map đầu ra:

~~~java
registry.metadataToExtract(
        CLIENT_CONTEXT_MIME,
        new ParameterizedTypeReference<Map<String, String>>() {},
        (context, headers) -> {
            String tenantId = context.get("tenantId");
            String traceId = context.get("traceId");

            if (tenantId != null) {
                headers.put("tenantId", tenantId);
            }
            if (traceId != null) {
                headers.put("traceId", traceId);
            }
        });
~~~

Ở đây, metadata JSON được giải mã thành Map<String, String>. Mapper chọn hai trường được phép sử dụng và ghi chúng vào Map header. Handler có thể nhận trực tiếp:

~~~java
@MessageMapping("orders.create")
public Mono<String> create(
        @Payload OrderCommand command,
        @Header("tenantId") String tenantId,
        @Header(name = "traceId", required = false) String traceId) {

    return Mono.just("accepted for tenant " + tenantId);
}
~~~

Dùng **ParameterizedTypeReference** khi kiểu đích có generic parameter như Map<String, String>. Nếu chỉ truyền Map.class, thông tin kiểu generic bị xóa do Java type erasure và Decoder không nhận được đầy đủ kiểu phần tử mong muốn.

Mapper cũng là nơi thích hợp để chuẩn hóa tên header, lọc trường không cần thiết và chuyển đổi kiểu. Không nên đưa toàn bộ khóa do client gửi vào header bằng putAll nếu ứng dụng chỉ cần một tập trường cố định; việc chọn rõ tenantId và traceId giúp tránh header ngoài dự kiến hoặc trùng tên với header nội bộ.

## 4. Cấu hình RSocketStrategies

RSocketStrategies tập hợp các thành phần dùng để encode và decode data, metadata, cũng như MetadataExtractor. Builder có **metadataExtractorRegistry** để đăng ký metadata tùy chỉnh mà vẫn giữ cấu hình mặc định, bao gồm khả năng xử lý route.

Ví dụ dưới đây dùng JSON metadata và ánh xạ hai trường thành hai header. Các lớp Jackson2JsonEncoder và Jackson2JsonDecoder thuộc Spring Web; ứng dụng cần có Jackson và các dependency RSocket tương ứng. Với Spring Boot, starter RSocket cung cấp hạ tầng codec cơ bản; có thể tùy chỉnh strategies theo nhu cầu ứng dụng.

### 4.1. Khai báo MIME type dùng chung

~~~java
import org.springframework.util.MimeType;

public final class RSocketMetadataTypes {

    public static final MimeType REQUEST_CONTEXT =
            MimeType.valueOf(
                    "application/vnd.acme.request-context+json");

    private RSocketMetadataTypes() {
    }
}
~~~

Tên MIME type phải thống nhất giữa bên gửi và bên nhận. Dùng vendor-specific MIME type giúp phân biệt cấu trúc request context của ứng dụng với các metadata JSON khác.

### 4.2. Đăng ký Decoder và mapper

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketStrategies;

@Configuration
public class RSocketMetadataConfig {

    @Bean
    RSocketStrategies rSocketStrategies() {
        return RSocketStrategies.builder()
                .encoders(encoders ->
                        encoders.add(new Jackson2JsonEncoder()))
                .decoders(decoders ->
                        decoders.add(new Jackson2JsonDecoder()))
                .metadataExtractorRegistry(registry ->
                        registry.metadataToExtract(
                                RSocketMetadataTypes.REQUEST_CONTEXT,
                                new ParameterizedTypeReference<
                                        Map<String, String>>() {},
                                (context, headers) -> {
                                    String tenantId =
                                            context.get("tenantId");
                                    String traceId =
                                            context.get("traceId");

                                    if (tenantId != null) {
                                        headers.put("tenantId", tenantId);
                                    }
                                    if (traceId != null) {
                                        headers.put("traceId", traceId);
                                    }
                                }))
                .build();
    }
}
~~~

Trong ví dụ, Encoder phục vụ phía gửi metadata JSON; Decoder phục vụ phía nhận. Nếu ứng dụng chỉ nhận metadata ở một phía, chỉ cần cấu hình codec cần thiết ở phía đó. Khi dùng cùng một RSocketStrategies cho client và server trong một ứng dụng, cả hai phía có thể chia sẻ cùng cấu hình.

Phải bảo đảm RSocketMessageHandler ở phía nhận sử dụng strategies đã cấu hình. Khi tự tạo handler trong cấu hình Spring, thiết lập bằng:

~~~java
RSocketMessageHandler handler = new RSocketMessageHandler();
handler.setRSocketStrategies(rSocketStrategies);
~~~

Nếu framework hoặc Spring Boot đã tạo handler, hãy cấu hình đúng handler đang được dùng bởi server. Một bean RSocketStrategies không có tác dụng với handler nếu handler thực tế vẫn sử dụng strategies khác.

## 5. Gửi metadata từ RSocketRequester

RSocketRequester cung cấp API fluent để tạo request. Với composite metadata, gọi **metadata(value, mimeType)** để thêm một metadata entry; sau đó khai báo data và kiểu response.

~~~java
import java.util.Map;

import reactor.core.publisher.Mono;

import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester = RSocketRequester.builder()
        .rsocketStrategies(rSocketStrategies)
        .tcp("localhost", 7000);

Map<String, String> context = Map.of(
        "tenantId", "acme",
        "traceId", "req-001");

Mono<String> response = requester.route("orders.create")
        .metadata(context, RSocketMetadataTypes.REQUEST_CONTEXT)
        .data(new OrderCommand("SKU-01", 2))
        .retrieveMono(String.class);
~~~

Ví dụ giả định server đang lắng nghe TCP tại localhost:7000, requester đã được cấu hình Encoder tương ứng và OrderCommand là kiểu payload của ứng dụng. Lệnh trên tạo một request có route orders.create, metadata JSON chứa tenantId và traceId, cùng data là OrderCommand.

Đối tượng nhận có thể là một record Java:

~~~java
public record OrderCommand(String sku, int quantity) {
}
~~~

Handler minh họa:

~~~java
import reactor.core.publisher.Mono;

import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

@Controller
public class OrderRSocketController {

    @MessageMapping("orders.create")
    public Mono<String> create(
            @Payload OrderCommand command,
            @Header("tenantId") String tenantId,
            @Header(name = "traceId", required = false) String traceId) {

        return Mono.just(
                "accepted for tenant " + tenantId
                        + ", sku " + command.sku());
    }
}
~~~

Khi request đến đúng handler, các giá trị dự kiến là:

| Vị trí | Giá trị |
|---|---|
| route | orders.create |
| tenantId | acme |
| traceId | req-001 |
| command.sku() | SKU-01 |
| command.quantity() | 2 |

Đây là các giá trị được bind vào tham số handler, không phải stdout của một chương trình độc lập. Các đoạn code là thành phần của ứng dụng Spring có RSocket server/client và dependency tương ứng.

## 6. Đọc toàn bộ metadata bằng @Headers

Nếu handler cần nhiều metadata đã được đăng ký, có thể nhận tất cả dưới dạng Map:

~~~java
@MessageMapping("orders.inspect")
public Mono<String> inspect(
        @Headers Map<String, Object> headers) {

    Object tenantId = headers.get("tenantId");
    Object traceId = headers.get("traceId");

    return Mono.just(
            "tenant=" + tenantId + ", trace=" + traceId);
}
~~~

**@Header** phù hợp khi handler biết chính xác các giá trị cần dùng. **@Headers** phù hợp với logging, audit hoặc logic dùng chung cần xem tập header đã được trích xuất. Map này chứa headers của Spring Message, không phải bản sao byte metadata ban đầu.

Nếu một header có thể vắng mặt, đặt required=false trong @Header hoặc xử lý kiểu dữ liệu nullable phù hợp. Mặc định, @Header yêu cầu header phải tồn tại; thiếu header bắt buộc có thể làm việc bind tham số thất bại trước khi phần thân handler chạy.

## 7. Metadata ở cấp request và cấp connection

Metadata thường gắn với từng request, chẳng hạn route, tenant hoặc trace id. RSocket cũng có metadata trong SETUP frame khi thiết lập kết nối. Spring hỗ trợ xử lý sự kiện cấp kết nối bằng **@ConnectMapping**; phương thức này có thể đọc data và metadata từ SETUP, cũng như metadata push qua METADATA_PUSH.

Nên chọn đúng phạm vi:

- Dữ liệu chỉ có ý nghĩa với một request, như traceId hoặc request version, nên gửi cùng request.
- Dữ liệu mô tả kết nối, như thông tin khởi tạo client, có thể nằm trong SETUP và được xử lý bằng @ConnectMapping.
- Metadata push là thông báo cấp kết nối, không phải header của một request nghiệp vụ cụ thể.

Không nên lưu trạng thái request riêng lẻ vào metadata SETUP nếu giá trị đó thay đổi theo từng request. Ngược lại, không cần lặp lại dữ liệu ổn định của kết nối ở mọi request nếu giao thức và chính sách bảo mật cho phép xử lý ở cấp kết nối.

## 8. Khi nào cần tự viết MetadataExtractor?

Phần lớn ứng dụng chỉ cần **DefaultMetadataExtractor** cùng **metadataExtractorRegistry**. Cách này giữ sẵn logic routing của Spring và bổ sung các quy tắc giải mã cần thiết.

Chỉ cân nhắc triển khai trực tiếp MetadataExtractor khi định dạng metadata đặc biệt không thể mô tả bằng các đăng ký có sẵn, chẳng hạn một cấu trúc nhị phân riêng hoặc quy tắc giải mã phụ thuộc nhiều entry. Implementation phải đọc Payload metadata, xác định MIME type, giải mã đúng định dạng và trả về Map<String, Object>.

Khi thay extractor mặc định bằng implementation riêng, cần bảo toàn việc trích xuất route nếu server vẫn dùng routing metadata chuẩn. Nếu không, handler có thể không tìm được route dù client đã gửi đúng route. Trong đa số trường hợp, mở rộng bằng metadataExtractorRegistry đơn giản và ít rủi ro hơn.

## 9. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| @Header không nhận được tenantId | Chưa đăng ký MIME type hoặc mapper không ghi khóa tenantId | Kiểm tra metadataExtractorRegistry và tên khóa trong mapper |
| Decode JSON thất bại | Chưa có JSON Decoder hoặc MIME type không khớp | Kiểm tra Decoder, MIME type client gửi và MIME type đã đăng ký |
| Map giải mã thành kiểu không mong muốn | Dùng Map.class và mất thông tin generic | Dùng ParameterizedTypeReference<Map<String, String>> |
| Không tìm thấy @MessageMapping | Routing metadata không hợp lệ hoặc extractor tùy chỉnh làm mất route | Kiểm tra route, routing MIME type và MetadataExtractor.ROUTE_KEY |
| Header bắt buộc bị thiếu | Client không gửi trường hoặc mapper bỏ qua trường đó | Kiểm tra dữ liệu gửi, mapper và required của @Header |
| Header có giá trị sai | Hai metadata entry cùng ghi một khóa hoặc mapper ghi đè giá trị | Dùng tên header riêng, quy định rõ trường nào được phép ghi |

Một quy trình kiểm tra hữu ích:

1. Xác nhận client đang gửi đúng MIME type và đúng cấu trúc metadata.
2. Xác nhận client có Encoder và server có Decoder tương ứng.
3. Xác nhận server handler sử dụng RSocketStrategies có đăng ký metadataExtractorRegistry.
4. Xác nhận mapper ghi đúng tên header và đúng kiểu giá trị.
5. Tạm nhận @Headers Map<String, Object> để quan sát các header đã được trích xuất.
6. Kiểm tra riêng route để chắc rằng routing metadata vẫn được xử lý.

Metadata không giải mã được có thể phát sinh lỗi decode. Routing metadata không hợp lệ cũng có thể làm request thất bại trước khi handler được gọi. Không nên bắt lỗi rồi âm thầm bỏ qua metadata bắt buộc, vì như vậy có thể che giấu lỗi giao thức hoặc cấu hình giữa hai phía.

## 10. Lưu ý thiết kế và bảo mật

- **Metadata không thay thế payload**: chỉ đặt thông tin điều khiển hoặc ngữ cảnh nhỏ vào metadata. Đối tượng nghiệp vụ lớn vẫn nên nằm trong data.
- **MIME type là hợp đồng giao tiếp**: client và server phải thống nhất MIME type, cấu trúc JSON, tên trường và phiên bản schema.
- **Giới hạn trường được ánh xạ**: chỉ tạo những header mà handler thực sự cần. Tránh đưa nguyên Map do client gửi vào header nếu không có kiểm soát.
- **Tránh trùng tên**: không ghi đè các khóa dùng cho routing hoặc header nội bộ của framework. Đặt namespace rõ ràng cho header riêng của ứng dụng khi cần.
- **Không tin tenantId chỉ vì nó nằm trong metadata**: client có thể tự gửi giá trị này. Phân quyền tenant phải dựa trên danh tính đã được xác thực và kiểm tra ở server; metadata chỉ là dữ liệu đầu vào.
- **Không dùng traceId làm credential**: traceId phục vụ tương quan log và quan sát request, không chứng minh danh tính.
- **Kiểm soát kích thước**: metadata nên nhỏ và có giới hạn. Không gửi file, danh sách lớn hoặc payload nghiệp vụ qua metadata.
- **Giữ tương thích phiên bản**: khi thay cấu trúc metadata, cần phối hợp phiên bản MIME type hoặc schema để client cũ và server mới không hiểu khác nhau.

## 11. Ghi nhớ

MetadataExtractor là cầu nối giữa metadata của giao thức RSocket và headers của Spring Message. DefaultMetadataExtractor xử lý routing metadata chuẩn và dùng Decoder để giải mã các entry đã đăng ký. MetadataExtractorRegistry cho phép ánh xạ một object thành một header hoặc dùng mapper để tạo nhiều header. Sau khi cấu hình đúng RSocketStrategies ở phía nhận, handler có thể truy cập các giá trị qua @Header hoặc @Headers.

Khi debug, hãy lần lượt kiểm tra MIME type, Decoder, đăng ký metadataToExtract, mapper và RSocketStrategies đang được handler sử dụng. Nếu request không vào đúng handler, kiểm tra thêm routing metadata và giữ nguyên hành vi trích xuất route mặc định.

## Tài liệu tham khảo

- [RSocket — Spring Framework Reference](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [MetadataExtractor — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/rsocket/MetadataExtractor.html)
- [DefaultMetadataExtractor — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/rsocket/DefaultMetadataExtractor.html)
- [MetadataExtractorRegistry — Spring Framework 6.1.x API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/rsocket/MetadataExtractorRegistry.html)
- [RSocketStrategies.Builder — Spring Framework 6.1.x API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.Builder.html)
- [RSocketRequester — Spring Framework 6.1.x API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
