# Thiết lập RSocketStrategies dùng chung

## Mục tiêu

`RSocketStrategies` là tập hợp các chiến lược mà Spring dùng khi mã hóa, giải mã và định tuyến thông điệp RSocket. Thay vì cấu hình codec riêng cho từng requester và responder, ứng dụng có thể tạo một cấu hình tập trung rồi tái sử dụng ở cả hai phía.

Trong cùng một tiến trình Spring, cách làm phổ biến là khai báo `RSocketStrategies` thành một bean singleton. `RSocketRequester.Builder` dùng bean đó để tạo client; `RSocketMessageHandler` dùng cùng bean để xử lý các request đến server. Khi client và server nằm ở hai tiến trình khác nhau, mỗi tiến trình tạo bean riêng nhưng phải thống nhất định dạng dữ liệu, MIME type và metadata trên đường truyền.

## RSocketStrategies quản lý những gì?

`RSocketStrategies` gom các thành phần sau vào một cấu hình:

| Thành phần | Vai trò |
| --- | --- |
| `Encoder` | Chuyển object Java thành dữ liệu byte trong payload hoặc metadata. |
| `Decoder` | Chuyển dữ liệu byte nhận được thành object Java. |
| `RouteMatcher` | So khớp route trong metadata với các mẫu route khai báo trên handler. |
| `MetadataExtractor` | Đọc metadata của payload và chuyển các entry thành các giá trị có tên để handler truy cập. |
| `DataBufferFactory` | Cấp phát `DataBuffer` khi Spring tạo hoặc xử lý payload. |
| `ReactiveAdapterRegistry` | Hỗ trợ Spring làm việc với các kiểu reactive như `Mono`, `Flux` và những kiểu đã đăng ký adapter. |

Các thành phần này có quan hệ với nhau. Ví dụ, `DefaultMetadataExtractor` sử dụng danh sách decoder đã cấu hình để giải mã metadata. Vì vậy, chỉ thêm decoder cho data mà quên decoder cần thiết cho metadata có thể khiến phần data hoạt động nhưng phần metadata tùy chỉnh thất bại.

`RSocketStrategies.builder()` tạo builder với các thiết lập mặc định. `build()` tạo instance dùng trong ứng dụng. Nếu cần tạo một biến thể dựa trên cấu hình có sẵn, có thể gọi `strategies.mutate()` rồi build instance mới.

## Codec mặc định và codec cho object

Ở cấp Spring Framework, cấu hình mặc định có các codec cơ bản cho `String`, `byte[]`, `ByteBuffer` và `DataBuffer`. Những kiểu này phù hợp với payload đơn giản. Để gửi DTO hoặc record Java, cần đăng ký codec tương ứng với định dạng mà hai đầu kết nối cùng hỗ trợ.

Các codec JSON, CBOR và một số định dạng khác được cung cấp trong `spring-web`. Ví dụ ở Spring Framework 7 với Jackson 3:

```java
import org.springframework.http.codec.cbor.JacksonCborDecoder;
import org.springframework.http.codec.cbor.JacksonCborEncoder;
```

Với Spring Framework 6.x dùng Jackson 2, các lớp tương ứng có tên `Jackson2CborDecoder` và `Jackson2CborEncoder`. Tương tự, JSON dùng `JacksonJsonDecoder` và `JacksonJsonEncoder` ở Framework 7; ở Framework 6.x là `Jackson2JsonDecoder` và `Jackson2JsonEncoder`. Hãy dùng lớp codec tương ứng với phiên bản Spring và Jackson mà dự án đang quản lý.

Các dependency cần có phụ thuộc vào cách dựng ứng dụng:

- `spring-messaging` cung cấp `RSocketStrategies`, `RSocketRequester` và `RSocketMessageHandler`.
- `spring-web` cung cấp nhiều encoder, decoder và `PathPatternRouteMatcher`.
- Với Spring Boot, `spring-boot-starter-rsocket` là điểm bắt đầu thuận tiện vì starter cung cấp hạ tầng RSocket và các dependency codec được Boot hỗ trợ.

## Khai báo một bean dùng chung trong Spring Framework

Ví dụ sau dùng CBOR cho payload object và `PathPatternRouteMatcher` cho route. Đây là cấu hình Spring Framework 7; nếu dự án dùng Framework 6.x, thay tên codec theo ghi chú phiên bản ở trên.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.cbor.JacksonCborDecoder;
import org.springframework.http.codec.cbor.JacksonCborEncoder;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

@Configuration
public class RSocketConfiguration {

    @Bean
    public RSocketStrategies rSocketStrategies() {
        return RSocketStrategies.builder()
                .encoders(encoders -> encoders.add(new JacksonCborEncoder()))
                .decoders(decoders -> decoders.add(new JacksonCborDecoder()))
                .routeMatcher(new PathPatternRouteMatcher())
                .build();
    }

    @Bean
    public RSocketMessageHandler rSocketMessageHandler(
            RSocketStrategies strategies) {
        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRSocketStrategies(strategies);
        return handler;
    }
}
```

`rSocketStrategies()` chỉ tạo cấu hình một lần trong application context. Spring inject cùng bean vào handler và vào các service cần tạo requester. Lệnh `setRSocketStrategies` cấu hình đồng bộ encoder, decoder, route matcher, metadata extractor và reactive adapter registry của `RSocketMessageHandler`.

Trong ứng dụng tự dựng server bằng Spring Framework, `RSocketMessageHandler` còn phải được gắn làm responder cho RSocket server, ví dụ:

```java
CloseableChannel server = RSocketServer.create(handler.responder())
        .bind(TcpServerTransport.create("localhost", 7000))
        .block();
```

Đoạn bind này cần các dependency transport RSocket phù hợp và cần được quản lý vòng đời khi ứng dụng dừng. Nếu dùng Spring Boot, server và `RSocketMessageHandler` thường đã được auto-configure; không tạo thêm handler thủ công nếu không có nhu cầu thay thế cấu hình mặc định.

## Dùng bean đó ở phía requester

`RSocketRequester.Builder.rsocketStrategies(...)` nhận instance đã tạo. Ví dụ client gửi mã SKU và nhận về một object:

```java
import org.springframework.http.MediaType;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;

public record InventoryItem(String sku, String status) { }

public class InventoryClient {

    private final RSocketRequester requester;

    public InventoryClient(RSocketStrategies strategies) {
        this.requester = RSocketRequester.builder()
                .rsocketStrategies(strategies)
                .dataMimeType(MediaType.parseMediaType("application/cbor"))
                .tcp("localhost", 7000);
    }

    public Mono<InventoryItem> findBySku(String sku) {
        return requester.route("inventory.find")
                .data(sku)
                .retrieveMono(InventoryItem.class);
    }
}
```

`dataMimeType` ở đây được đặt tường minh để ví dụ thể hiện rõ hợp đồng CBOR. Nếu bỏ qua thiết lập này, Spring suy ra MIME type data từ decoder được cấu hình đầu tiên. Khi có nhiều định dạng, hãy kiểm tra thứ tự codec và MIME type mà requester gửi trong frame `SETUP`.

Phía responder có thể nhận route tương ứng bằng handler annotation:

```java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class InventoryResponder {

    @MessageMapping("inventory.find")
    public Mono<InventoryItem> find(String sku) {
        return Mono.just(new InventoryItem(sku, "AVAILABLE"));
    }
}
```

Ví dụ minh họa cùng DTO để dễ theo dõi. Trong triển khai thực tế, requester và responder có thể nằm ở hai ứng dụng khác nhau; hai bên không chia sẻ object Java trong bộ nhớ mà phải thống nhất schema và cách serialize trên wire.

## Cấu hình khi dùng Spring Boot

Spring Boot auto-configure một bean `RSocketStrategies` cùng các codec cần thiết. Tài liệu Boot hiện hành mô tả thứ tự mặc định là CBOR với Jackson trước, sau đó JSON với Jackson. `spring-boot-starter-rsocket` cung cấp các dependency liên quan.

Khi dùng Boot, thường nên mở rộng builder auto-configured bằng `RSocketStrategiesCustomizer`. Ví dụ sau thay route matcher mà vẫn giữ các codec mặc định của Boot:

```java
import org.springframework.boot.rsocket.messaging.RSocketStrategiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

@Configuration
public class RSocketBootConfiguration {

    @Bean
    @Order(0)
    public RSocketStrategiesCustomizer routeMatcherCustomizer() {
        return builder -> builder.routeMatcher(new PathPatternRouteMatcher());
    }
}
```

`RSocketStrategiesCustomizer` nhận `RSocketStrategies.Builder`, vì vậy có thể thêm encoder, decoder, route matcher hoặc metadata extractor trước khi Boot build bean cuối cùng. Nếu có nhiều customizer, `@Order` ảnh hưởng đến thứ tự áp dụng; thứ tự codec có thể ảnh hưởng đến việc chọn codec phù hợp.

Boot cũng auto-configure `RSocketMessageHandler` cho server và `RSocketRequester.Builder` cho client. Builder này là prototype bean: mỗi injection point nhận một instance mới vì builder có trạng thái. Hãy tránh dùng một builder đã cấu hình cho nhiều requester có setup khác nhau. Có thể inject builder vào service rồi áp dụng strategies phù hợp trước khi gọi `tcp(...)` hoặc `websocket(...)`.

Không nên vừa tự khai báo một bean `RSocketStrategies`/`RSocketMessageHandler` vừa giữ nguyên cấu hình auto-configuration mà không kiểm tra điều kiện back-off và thứ tự bean. Chọn một điểm mở rộng rõ ràng: dùng `RSocketStrategiesCustomizer` khi chỉ cần bổ sung cấu hình cho Boot, hoặc tự quản lý bean khi chủ động thay thế hạ tầng.

## Route matcher và quy tắc route

`RouteMatcher` quyết định route nhận được có khớp với route pattern trên handler hay không. Mặc định, Spring dùng `SimpleRouteMatcher` dựa trên `AntPathMatcher` với dấu chấm (`.`) làm ký tự phân cấp. `PathPatternRouteMatcher` từ `spring-web` là lựa chọn hiệu quả hơn khi cần route pattern phức tạp.

RSocket route là tên route phân cấp, không phải URL HTTP. Ví dụ `inventory.find` và `inventory.{action}` là route hợp lệ theo quy ước dấu chấm. Không nên tự áp dụng suy nghĩ về URL path, URL encoding hoặc dấu gạch chéo của HTTP vào route RSocket.

Điểm quan trọng là requester chỉ gửi route trong metadata; responder mới dùng `RouteMatcher` để đối chiếu route đó với các phương thức `@MessageMapping`. Nếu route không đến được handler, kiểm tra chính tả route, quy tắc pattern và route matcher trên responder.

## Metadata tùy chỉnh

RSocket payload có hai phần độc lập: data và metadata. Metadata thường chứa route, thông tin xác thực, trace context hoặc thông tin điều khiển. Metadata mặc định thường dùng composite metadata, cho phép một payload mang nhiều entry với MIME type riêng.

`DefaultMetadataExtractor` có sẵn khả năng đọc routing metadata. Khi cần giải mã một metadata entry khác, đăng ký MIME type, kiểu Java và tên header bằng `metadataExtractorRegistry`. Ví dụ dưới đây là phần cấu hình bổ sung cho một `TraceContext` được mã hóa CBOR; decoder CBOR phải có trong strategies:

```java
.metadataExtractorRegistry(registry -> registry.metadataToExtract(
        MediaType.parseMediaType("application/cbor"),
        TraceContext.class,
        "traceContext"))
```

Handler có thể nhận giá trị đã trích xuất thông qua header tương ứng. Hai đầu cần thống nhất MIME type của entry và kiểu dữ liệu được giải mã. Nếu metadata sử dụng một định dạng khác, hãy đăng ký decoder hỗ trợ đúng MIME type đó; không giả định decoder của data sẽ tự động giải mã mọi metadata.

Khi cần thay toàn bộ cách trích xuất metadata, có thể dùng `metadataExtractor(...)` để cung cấp một `MetadataExtractor` riêng. Với trường hợp chỉ thêm một hoặc vài loại metadata, `metadataExtractorRegistry(...)` thường dễ bảo trì hơn vì giữ lại hành vi mặc định.

## Data MIME type và metadata MIME type

`dataMimeType` và `metadataMimeType` mô tả định dạng payload được thương lượng ở cấp kết nối trong frame `SETUP`:

- Data MIME type áp dụng cho phần data của các request trên kết nối. Giá trị mặc định được suy ra từ decoder đầu tiên trong strategies; requester có thể đặt rõ bằng `RSocketRequester.Builder.dataMimeType(...)`.
- Metadata MIME type mô tả cách đóng gói metadata. Mặc định là composite metadata, cho phép nhiều metadata entry với MIME type riêng.
- MIME type ở cấp kết nối không thay thế việc đăng ký encoder/decoder. Codec vẫn phải hỗ trợ kiểu object và MIME type thực tế của dữ liệu.
- Hai đầu kết nối phải tương thích. Một bên gửi CBOR trong khi bên kia chỉ có decoder JSON sẽ không thể giải mã payload object.

Chỉ thay MIME type khi hợp đồng giao tiếp yêu cầu. Nếu đổi định dạng, cập nhật đồng bộ requester, responder, codec và các hệ thống tiêu thụ khác.

## Thứ tự và cách tổ chức codec

Builder cung cấp hai nhóm phương thức:

- `encoder(...)` và `decoder(...)` thêm một hoặc nhiều codec vào danh sách.
- `encoders(Consumer<List<Encoder<?>>>)` và `decoders(Consumer<List<Decoder<?>>>)` cho phép thao tác trực tiếp với danh sách codec hiện có.

Thứ tự có ý nghĩa khi nhiều codec cùng có thể xử lý một kiểu hoặc MIME type. Đặt codec đặc thù trước codec tổng quát khi ứng dụng cần ưu tiên codec đó. Tránh đăng ký lặp cùng một codec hoặc thêm decoder không có encoder tương ứng khi ứng dụng cũng cần gửi kiểu dữ liệu đó.

Không tạo mới `RSocketStrategies` ở mỗi lần gọi request. Chiến lược thường là cấu hình dùng chung và ổn định trong suốt vòng đời ứng dụng. Nếu cần một cấu hình biến thể, dùng `mutate()` để sao chép cấu hình hiện tại, chỉnh sửa builder mới rồi `build()`.

## Kiểm tra và xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân nên kiểm tra |
| --- | --- |
| Không tìm được encoder cho DTO | Chưa đăng ký encoder cho kiểu dữ liệu hoặc MIME type; thiếu dependency codec; DTO không được codec hỗ trợ. |
| Không giải mã được payload | Decoder không tương ứng với định dạng bên gửi, MIME type khác nhau hoặc schema không tương thích. |
| Client chạy nhưng server báo lỗi decode | Client và responder đang dùng strategies khác nhau hoặc khác cấu hình MIME type. |
| `@MessageMapping` không được gọi | Route gửi lên sai, route pattern không khớp hoặc responder dùng route matcher khác dự kiến. |
| Metadata tùy chỉnh không xuất hiện trong handler | Chưa đăng ký metadata MIME type trong extractor, thiếu decoder phù hợp hoặc tên header không trùng với tên đã đăng ký. |
| Boot có codec trùng hoặc codec không được ưu tiên | Có nhiều `RSocketStrategiesCustomizer`; kiểm tra `@Order` và danh sách codec sau khi customizer chạy. |

Quy trình kiểm tra nên đi theo thứ tự:

1. Xác nhận classpath có `spring-messaging`, `spring-web` và dependency của codec cần dùng.
2. Kiểm tra danh sách encoder/decoder và thứ tự đăng ký trong `RSocketStrategies`.
3. Xác nhận requester gửi đúng data MIME type và metadata MIME type trong `SETUP`.
4. Kiểm tra route string ở requester có khớp với `@MessageMapping` và route matcher không.
5. Với metadata tùy chỉnh, xác nhận MIME type, decoder, kiểu Java và tên header đã đăng ký.
6. Kiểm tra cả hai đầu kết nối. Thay đổi codec ở một phía cần được phản ánh trong hợp đồng giao tiếp của phía còn lại.

## Lưu ý thiết kế

- Dùng một bean `RSocketStrategies` cho những requester và responder trong cùng application cần chung hợp đồng mã hóa và định tuyến.
- Với các ứng dụng ở hai tiến trình khác nhau, tạo cấu hình tương đương ở mỗi bên; không có singleton Java nào được chia sẻ qua mạng.
- Tách biệt cấu hình codec khỏi cấu hình transport. `RSocketStrategies` không quyết định host, port, TCP/WebSocket, TLS, keepalive hay session resumption; các thiết lập đó thuộc requester builder hoặc RSocket connector/server.
- Giữ nguyên composite metadata nếu ứng dụng cần nhiều loại metadata độc lập như route, authentication và tracing.
- Chỉ thêm codec khi có nhu cầu định dạng cụ thể. Codec dư thừa làm cấu hình khó hiểu và có thể ảnh hưởng đến thứ tự lựa chọn.
- Với Spring Boot, ưu tiên customizer khi chỉ cần mở rộng auto-configuration; tránh tạo cấu hình thứ hai trùng với bean Boot đã cung cấp.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Javadoc — RSocketStrategies](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.html)
- [Spring Framework Javadoc — RSocketRequester.Builder](https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html)
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [Spring Boot API — RSocketStrategiesCustomizer](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/rsocket/messaging/RSocketStrategiesCustomizer.html)