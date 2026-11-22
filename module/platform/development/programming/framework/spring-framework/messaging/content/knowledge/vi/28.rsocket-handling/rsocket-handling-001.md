# RSocketMessageHandler và bộ xử lý dựa trên annotation

## 1. Vai trò của RSocketMessageHandler

Trong Spring Framework, RSocketMessageHandler là bộ điều phối các request đi vào một RSocket responder theo mô hình xử lý message của Spring. Nó kết nối giao thức RSocket với các phương thức handler được khai báo bằng annotation:

1. Nhận request hoặc sự kiện kết nối từ RSocket.
2. Đọc route và metadata từ payload.
3. Tìm phương thức phù hợp dựa trên @MessageMapping hoặc @ConnectMapping.
4. Giải mã payload thành kiểu tham số Java, chuyển metadata thành các giá trị có thể inject.
5. Gọi phương thức handler và mã hóa giá trị trả về thành response hoặc stream.

RSocketMessageHandler không tự mở cổng TCP/WebSocket. Phương thức responder() tạo một SocketAcceptor để gắn vào RSocketServer hoặc vào một RSocketRequester ở phía client. Vì vậy cần phân biệt ba trách nhiệm:

- RSocketServer và transport chịu trách nhiệm lắng nghe, chấp nhận kết nối.
- RSocketMessageHandler chịu trách nhiệm tìm và gọi phương thức xử lý message.
- RSocketRequester chịu trách nhiệm gửi request và đọc response ở phía requester.

RSocket có tính hai chiều. Sau khi kết nối được thiết lập, cả hai đầu đều có thể vừa gửi request vừa làm responder; khái niệm client/server chỉ mô tả vai trò khi bắt đầu kết nối.

## 2. Route và annotation handler

### @Controller

RSocketMessageHandler được khai báo thành Spring bean ở phía server sẽ mặc định phát hiện các bean @Controller có phương thức @MessageMapping hoặc @ConnectMapping. Đây là cơ chế đăng ký handler; chỉ viết một lớp có annotation nhưng không đưa lớp đó vào Spring ApplicationContext thì chưa đủ để handler phát hiện nó.

Nếu ứng dụng có nhiều loại responder, ví dụ server và nhiều client responder trong cùng ApplicationContext, có thể thay đổi điều kiện phát hiện handler bằng handlerPredicate. Việc này giúp tránh một lớp handler bị đăng ký nhầm vào responder không mong muốn.

### @MessageMapping

@MessageMapping ánh xạ route trong metadata của request tới phương thức xử lý một request RSocket. Annotation có thể đặt ở cấp lớp để khai báo tiền tố chung và ở cấp phương thức để khai báo phần route cụ thể.

Ví dụ:

~~~java
@Controller
@MessageMapping("catalog")
public class CatalogRSocketController {

    @MessageMapping("products.{sku}")
    public Mono<Product> find(
            @DestinationVariable("sku") String sku) {
        // Xử lý request tìm sản phẩm.
        return Mono.empty();
    }
}
~~~

Với cấu hình route matcher mặc định dùng dấu chấm làm dấu phân cách, route đầy đủ của phương thức trên có dạng catalog.products.{sku}. Request có route catalog.products.A-101 sẽ truyền giá trị A-101 vào tham số sku.

Route RSocket nằm trong metadata, không phải URL HTTP. Không nên áp dụng máy móc quy tắc định tuyến URL, URL decoding hay cấu hình HTTP của Spring MVC/WebFlux cho route RSocket.

Các tham số thường dùng trong phương thức @MessageMapping:

| Tham số | Ý nghĩa |
| --- | --- |
| @Payload | Payload của request; Spring giải mã thành kiểu tham số. Có thể là một đối tượng hoặc kiểu reactive như Mono/Flux. |
| @DestinationVariable | Giá trị được trích từ biến trong route pattern. |
| RSocketRequester | Requester gắn với kết nối hiện tại, dùng khi responder cần gửi request ngược lại đầu bên kia. |
| @Header | Một giá trị metadata đã được MetadataExtractor đăng ký. |
| @Headers Map<String, Object> | Các metadata đã được trích xuất và chuyển thành header. |

@Payload có thể được lược bỏ khi tham số là một kiểu đối tượng không thuộc nhóm tham số đặc biệt mà Spring đã hỗ trợ. Tuy vậy, ghi rõ @Payload thường giúp chữ ký handler dễ đọc hơn.

### @ConnectMapping

@ConnectMapping xử lý sự kiện ở cấp kết nối thay vì một request nghiệp vụ thông thường. Annotation này ánh xạ:

- Frame SETUP ban đầu khi kết nối RSocket được thiết lập.
- Các thông báo metadata push tiếp theo qua frame METADATA_PUSH.

@ConnectMapping có thể khai báo route pattern để chỉ nhận những kết nối có route metadata phù hợp. Nếu không khai báo pattern, phương thức khớp với mọi sự kiện setup và metadata push. Nó cũng có thể kết hợp với @MessageMapping ở cấp lớp để dùng chung route prefix.

Phương thức @ConnectMapping không trả dữ liệu. Kiểu trả về phải là void hoặc Mono<Void>. Ở phía server, nếu xử lý SETUP trả về lỗi thì kết nối mới có thể bị từ chối. Ở phía client, đây là callback và không quyết định việc thiết lập kết nối.

Một lưu ý quan trọng: không giữ việc xử lý SETUP lại để chờ một request mới gửi ngược qua RSocketRequester. Nếu cần chủ động gọi sang đầu bên kia ngay khi kết nối bắt đầu, hãy tách việc gửi request khỏi luồng xử lý kết nối và thực hiện bất đồng bộ.

## 3. Cardinality quyết định kiểu tương tác RSocket

RSocket hỗ trợ bốn kiểu tương tác:

- Request-Response: gửi một message và nhận một message.
- Request-Stream: gửi một message và nhận một luồng message.
- Request-Channel: hai bên trao đổi các luồng message.
- Fire-and-Forget: gửi một message một chiều, không chờ response.

Với @MessageMapping, Spring suy ra kiểu tương tác dựa trên số lượng phần tử đầu vào và đầu ra của chữ ký phương thức.

| Cardinality | Ý nghĩa trong chữ ký handler |
| --- | --- |
| 0 đầu vào | Không có tham số @Payload. |
| 1 đầu vào | Một giá trị cụ thể hoặc kiểu bất đồng bộ một phần tử như Mono<T>. |
| Many đầu vào | Kiểu bất đồng bộ nhiều phần tử như Flux<T>. |
| 0 đầu ra | void hoặc kiểu không phát giá trị như Mono<Void>. |
| 1 đầu ra | Một đối tượng cụ thể hoặc Mono<T>. |
| Many đầu ra | Kiểu nhiều phần tử như Flux<T>. |

Các tổ hợp được hỗ trợ:

| Cardinality đầu vào | Cardinality đầu ra | Kiểu tương tác |
| --- | --- | --- |
| 0 hoặc 1 | 0 | Fire-and-Forget, Request-Response |
| 0 hoặc 1 | 1 | Request-Response |
| 0 hoặc 1 | Many | Request-Stream |
| Many | 0, 1 hoặc Many | Request-Channel |

Ví dụ:

- Mono<Product> biểu thị kết quả đơn.
- Flux<Product> biểu thị một luồng kết quả.
- Mono<Void> biểu thị hoàn tất mà không phát giá trị.
- Flux<Command> ở đầu vào biểu thị handler nhận nhiều message trong một request-channel.

RSocket dùng Reactive Streams nên demand và back pressure có thể truyền qua ranh giới mạng. Khi xử lý Flux, hãy giữ xử lý ở dạng reactive nếu có thể; không gọi block() trong handler vì thao tác đó có thể chặn luồng xử lý và làm mất lợi ích của mô hình bất đồng bộ.

## 4. Cấu hình RSocketMessageHandler

Cách cấu hình phía server thường dùng là khai báo RSocketMessageHandler thành bean. Ví dụ dưới đây chọn PathPatternRouteMatcher:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

@Configuration
public class RSocketHandlerConfiguration {

    @Bean
    public RSocketMessageHandler rSocketMessageHandler() {
        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRouteMatcher(new PathPatternRouteMatcher());
        return handler;
    }
}
~~~

Mặc định, handler dùng SimpleRouteMatcher dựa trên AntPathMatcher. PathPatternRouteMatcher từ spring-web sử dụng route và pattern đã được parse, thường hiệu quả hơn khi có nhiều route cần so khớp. Cả hai matcher mặc định dùng dấu chấm làm dấu phân cách route. Route RSocket là chuỗi phân cấp của ứng dụng, không phải đường dẫn URL.

Sau khi lấy bean, có thể gắn responder vào RSocketServer:

~~~java
import io.rsocket.core.RSocketServer;
import io.rsocket.transport.netty.server.TcpServerTransport;
import org.springframework.context.ApplicationContext;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;

ApplicationContext context = /* ApplicationContext của ứng dụng */;
RSocketMessageHandler handler =
        context.getBean(RSocketMessageHandler.class);

var server = RSocketServer.create(handler.responder())
        .bind(TcpServerTransport.create("localhost", 7000))
        .block();
~~~

Đoạn bind trên minh họa cách kết nối adapter với RSocket Java API. Ứng dụng thực tế cần quản lý vòng đời của channel trả về và dispose channel khi dừng server. Nếu dùng Spring Boot, có thể để cấu hình server/transport do Boot quản lý; phần quan trọng ở đây là responder được cung cấp bởi RSocketMessageHandler.

## 5. Ví dụ controller xử lý nhiều kiểu request

Ví dụ sau dùng Java 17 record để biểu diễn payload. Controller có tiền tố route catalog và ba handler: request-response, request-stream và request-channel.

~~~java
import java.util.Map;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
@MessageMapping("catalog")
public class CatalogRSocketController {

    private final Map<String, Product> products = Map.of(
            "A-101", new Product("A-101", "Keyboard", 12),
            "B-205", new Product("B-205", "Mouse", 0)
    );

    // Request-Response: một route variable, một kết quả.
    @MessageMapping("products.{sku}")
    public Mono<Product> find(
            @DestinationVariable("sku") String sku) {
        return Mono.justOrEmpty(products.get(sku));
    }

    // Request-Stream: một payload, nhiều kết quả.
    @MessageMapping("products.available")
    public Flux<Product> available(
            @Payload AvailabilityFilter filter) {
        return Flux.fromIterable(products.values())
                .filter(product ->
                        product.stock() >= filter.minimumStock());
    }

    // Request-Channel: nhận một luồng lệnh và trả một luồng kết quả.
    @MessageMapping("stock.echo")
    public Flux<StockCommand> echo(
            @Payload Flux<StockCommand> commands) {
        return commands.doOnNext(System.out::println);
    }

    // Fire-and-Forget: nhận một payload và hoàn tất không phát dữ liệu.
    @MessageMapping("audit.record")
    public Mono<Void> record(@Payload AuditEvent event) {
        return Mono.fromRunnable(() ->
                System.out.println("audit=" + event.action()));
    }

    public record Product(String sku, String name, int stock) {
    }

    public record AvailabilityFilter(int minimumStock) {
    }

    public record StockCommand(String sku, int delta) {
    }

    public record AuditEvent(String action) {
    }
}
~~~

Các route đầy đủ được tạo từ tiền tố catalog và route ở cấp phương thức:

| Phương thức | Route | Kiểu tương tác |
| --- | --- | --- |
| find | catalog.products.{sku} | Request-Response |
| available | catalog.products.available | Request-Stream |
| echo | catalog.stock.echo | Request-Channel |
| record | catalog.audit.record | Fire-and-Forget |

Phương thức find không cần payload vì SKU đã nằm trong route. Phương thức available nhận một đối tượng AvailabilityFilter và phát nhiều Product. Phương thức echo nhận Flux<StockCommand>, vì vậy đây là luồng hai chiều. Phương thức record trả Mono<Void>; requester có thể dùng send() để gửi theo kiểu Fire-and-Forget.

## 6. Gửi request bằng RSocketRequester

RSocketRequester cung cấp API fluent để khai báo route, payload và kiểu kết quả mong đợi. Ví dụ:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

RSocketRequester requester =
        RSocketRequester.builder().tcp("localhost", 7000);

// Request-Response.
Mono<CatalogRSocketController.Product> product =
        requester.route("catalog.products.A-101")
                .retrieveMono(CatalogRSocketController.Product.class);

// Request-Stream.
Flux<CatalogRSocketController.Product> available =
        requester.route("catalog.products.available")
                .data(new CatalogRSocketController.AvailabilityFilter(1))
                .retrieveFlux(CatalogRSocketController.Product.class);

// Fire-and-Forget.
Mono<Void> sent =
        requester.route("catalog.audit.record")
                .data(new CatalogRSocketController.AuditEvent("PRODUCT_VIEWED"))
                .send();
~~~

Lệnh send() trả về Mono<Void> để báo việc gửi message đã hoàn tất. Nó không xác nhận rằng phương thức handler phía nhận đã xử lý xong message. Nếu cần kết quả xử lý, hãy dùng kiểu tương tác có response như Request-Response.

RSocketRequester cũng hỗ trợ Request-Channel. Khi gửi một Publisher nhiều phần tử, có thể khai báo kiểu phần tử để tránh phải suy luận kiểu dữ liệu cho từng phần tử:

~~~java
Flux<CatalogRSocketController.StockCommand> commands = Flux.just(
        new CatalogRSocketController.StockCommand("A-101", 2),
        new CatalogRSocketController.StockCommand("B-205", -1)
);

Flux<CatalogRSocketController.StockCommand> replies =
        requester.route("catalog.stock.echo")
                .data(commands, CatalogRSocketController.StockCommand.class)
                .retrieveFlux(CatalogRSocketController.StockCommand.class);
~~~

Các ví dụ requester và responder phải thống nhất route, kiểu payload, data MIME type và codec tương ứng.

## 7. RSocketStrategies, codec và metadata

RSocketStrategies gom các thành phần dùng chung cho requester và responder, gồm encoder, decoder, route matcher, MetadataExtractor và ReactiveAdapterRegistry. Có thể cấu hình chiến lược này một lần rồi dùng lại ở hai phía.

Ví dụ đăng ký JSON codec từ spring-web:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

@Configuration
public class RSocketStrategiesConfiguration {

    @Bean
    public RSocketStrategies rSocketStrategies() {
        return RSocketStrategies.builder()
                .encoders(encoders ->
                        encoders.add(new Jackson2JsonEncoder()))
                .decoders(decoders ->
                        decoders.add(new Jackson2JsonDecoder()))
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
~~~

Các codec JSON cần spring-web và Jackson trên classpath. Nếu dùng CBOR hoặc Protobuf, đăng ký encoder/decoder tương ứng. Mặc định, RSocketStrategies chỉ có các codec cơ bản cho String, byte[] và ByteBuffer; không nên giả định một DTO Java bất kỳ tự động được serialize nếu chưa có codec phù hợp.

RSocket khai báo MIME type của data và metadata trong frame SETUP. Hai phía phải thống nhất định dạng để giải mã đúng payload. Metadata có thể chứa route, thông tin xác thực, tracing hoặc dữ liệu ứng dụng khác. RSocketMessageHandler hỗ trợ composite metadata và routing metadata mặc định; DefaultMetadataExtractor giải mã route thành header route. Muốn đọc metadata bổ sung qua @Header hoặc @Headers, hãy đăng ký MIME type và decoder phù hợp với MetadataExtractor.

## 8. Responder ở phía client

Annotated responder không chỉ dùng cho server. Client cũng có thể nhận request từ server và xử lý bằng @MessageMapping hoặc @ConnectMapping. Cách đăng ký gọn là dùng factory method tĩnh:

~~~java
import io.rsocket.SocketAcceptor;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

RSocketStrategies strategies = RSocketStrategies.builder()
        .routeMatcher(new PathPatternRouteMatcher())
        .build();

SocketAcceptor clientResponder =
        RSocketMessageHandler.responder(strategies, new ClientResponder());

RSocketRequester requester = RSocketRequester.builder()
        .rsocketConnector(connector ->
                connector.acceptor(clientResponder))
        .tcp("localhost", 7000);
~~~

ClientResponder là một đối tượng có các phương thức được gắn @MessageMapping hoặc @ConnectMapping. Khi truyền trực tiếp đối tượng vào factory method, nó không bắt buộc phải có stereotype @Controller. Nếu cần phát hiện handler theo annotation tùy chỉnh hoặc cấu hình nhiều responder phức tạp hơn, có thể khai báo RSocketMessageHandler thành bean và điều chỉnh handlerPredicate.

Từ Spring Framework 6.1, RSocketMessageHandler cũng hỗ trợ @RSocketExchange. Đây là lựa chọn khác để khai báo contract RSocket bằng interface và dùng interface đó ở cả requester lẫn responder. @MessageMapping linh hoạt hơn khi cần nhiều route hoặc route pattern; @RSocketExchange yêu cầu route cụ thể cho từng phương thức.

## 9. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy handler | Lớp handler chưa là bean, thiếu @Controller ở chế độ phát hiện mặc định hoặc route không khớp. | Kiểm tra component scan, handlerPredicate và route sau khi ghép prefix cấp lớp với route cấp phương thức. |
| Biến route không được inject | Tên biến trong @DestinationVariable không trùng với biến trong pattern hoặc route gửi lên sai. | Đối chiếu @MessageMapping("products.{sku}") với @DestinationVariable("sku") và route thực tế. |
| Không giải mã được DTO | Thiếu decoder hoặc data MIME type giữa hai đầu không tương thích. | Cấu hình RSocketStrategies và codec ở cả requester lẫn responder. |
| Không đọc được metadata tùy chỉnh | MetadataExtractor chưa đăng ký MIME type hoặc decoder tương ứng. | Đăng ký metadata extractor và kiểm tra tên header được trích xuất. |
| Request-Stream không phát nhiều phần tử | Handler trả một đối tượng hoặc Mono thay vì Flux. | Dùng Flux<T> khi cần nhiều kết quả và đảm bảo requester gọi retrieveFlux(). |
| Request-Channel không hoạt động như mong đợi | Handler không nhận Publisher nhiều phần tử hoặc hai đầu không thống nhất kiểu dữ liệu. | Dùng Flux<T> ở đầu vào, chọn kiểu trả về phù hợp và khai báo element type khi gửi Publisher. |
| Kết nối bị từ chối khi SETUP | @ConnectMapping phía server phát ra lỗi. | Kiểm tra xác thực, kiểm tra dữ liệu setup và lỗi trong Mono<Void>. |
| Handler làm nghẽn luồng reactive | Gọi block() hoặc thực hiện I/O blocking trực tiếp trong phương thức xử lý. | Dùng API reactive; nếu buộc phải gọi tác vụ blocking, cô lập nó trên scheduler phù hợp. |

Khi debug, nên lần lượt kiểm tra route metadata, chữ ký handler, cardinality, MIME type, encoder/decoder và metadata extractor. Không nên chỉ nhìn vào tên phương thức Java vì route thực tế là kết quả kết hợp pattern cấp lớp, pattern cấp phương thức và route mà requester gửi đi.

## 10. Tài liệu tham khảo

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [RSocketMessageHandler — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/rsocket/annotation/support/RSocketMessageHandler.html)
- [MessageMapping — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/handler/annotation/MessageMapping.html)
- [ConnectMapping — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/rsocket/annotation/ConnectMapping.html)
- [PathPatternRouteMatcher — Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/util/pattern/PathPatternRouteMatcher.html)
