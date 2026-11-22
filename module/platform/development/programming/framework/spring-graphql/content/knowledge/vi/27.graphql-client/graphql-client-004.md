# RSocketGraphQlClient trong Spring for GraphQL

`RSocketGraphQlClient` là client của Spring for GraphQL dùng RSocket để gửi GraphQL operation đến server. Nó triển khai hợp đồng chung `GraphQlClient`, vì vậy cách tạo query, truyền variables, đọc response và xử lý subscription gần như giống các client HTTP hoặc WebSocket. Phần khác biệt nằm ở cách thiết lập kết nối RSocket, route, metadata và vòng đời session.

RSocket là transport hướng kết nối và hỗ trợ multiplexing. Một `RSocketGraphQlClient` duy trì một session dùng chung cho nhiều request; session được thiết lập tự động khi request đầu tiên được gửi hoặc có thể khởi động tường minh bằng `start()`. Khi kết nối bị mất, client thử thiết lập lại ở request tiếp theo hoặc khi gọi `start()` lần nữa. Vì vậy, ứng dụng thường nên dùng một client instance cho mỗi GraphQL server thay vì tạo client mới cho từng query.

## 1. RSocketGraphQlClient là gì?

Spring for GraphQL định nghĩa `GraphQlClient` như API chung để thực hiện GraphQL request, không phụ thuộc transport. Các implementation chính gồm:

| Client | Transport | Đặc điểm |
| --- | --- | --- |
| `HttpSyncGraphQlClient` | HTTP qua `RestClient` | Blocking API |
| `HttpGraphQlClient` | HTTP qua `WebClient` | Reactive, non-blocking |
| `WebSocketGraphQlClient` | WebSocket | Session lâu dài, hỗ trợ streaming |
| `RSocketGraphQlClient` | RSocket qua TCP hoặc WebSocket | Session lâu dài, multiplexing và streaming |

`RSocketGraphQlClient` sử dụng `RSocketRequester` của Spring Messaging ở tầng dưới. Client đóng gói GraphQL request thành payload RSocket và gửi đến route mà server cấu hình cho GraphQL handler.

RSocket có thể chạy trên TCP hoặc WebSocket. Transport hai phía phải tương thích: client TCP cần kết nối đến RSocket server TCP; client WebSocket cần endpoint WebSocket được cấu hình để nhận RSocket.

## 2. Khi nào nên dùng RSocket?

RSocket phù hợp khi ứng dụng cần giao tiếp giữa các service hoặc client với server qua một session lâu dài, đặc biệt khi có nhiều request đồng thời hoặc cần streaming.

Một số trường hợp thường gặp:

- Backend service gọi GraphQL service khác với nhiều operation trên cùng một kết nối.
- Ứng dụng cần subscription để nhận dữ liệu thay đổi liên tục.
- Hệ thống nội bộ đã dùng RSocket cho request-response hoặc request-stream.
- Muốn dùng cùng API `GraphQlClient` nhưng chọn transport RSocket.
- Cần multiplex nhiều GraphQL request trên một session.

RSocket không tự làm query GraphQL nhanh hơn. Hiệu năng phụ thuộc payload, độ trễ mạng, server, database, cách multiplex và số request đồng thời. Nếu ứng dụng chỉ cần gọi GraphQL đơn giản qua HTTP và không cần session hoặc streaming, `HttpGraphQlClient` có thể phù hợp hơn.

## 3. Thêm dependency và cấu hình RSocket server

Với Spring Boot, ứng dụng server cần GraphQL starter và RSocket starter:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-rsocket")
}
~~~

RSocket starter cung cấp transport TCP hoặc WebSocket. Ví dụ cấu hình server dùng TCP port `7000` và route `graphql`:

~~~yaml
spring:
  rsocket:
    server:
      port: 7000
  graphql:
    rsocket:
      mapping: graphql
~~~

`spring.graphql.rsocket.mapping` xác định route mà GraphQL handler nhận. Client cũng phải gửi đúng route này. Khi cấu hình RSocket server và GraphQL mapping, Spring Boot đăng ký GraphQL handler trên RSocket transport.

Schema và annotated controller vẫn được cấu hình như các transport khác. Ví dụ:

~~~graphql
type Query {
    product(id: ID!): Product
}

type Product {
    id: ID!
    name: String!
    price: Float!
}
~~~

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @QueryMapping
    public Product product(@Argument("id") String id) {
        return productService.findById(id);
    }
}
~~~

Transport RSocket chỉ thay đổi cách request đi đến server. Schema, resolver, DataLoader, validation và exception handling vẫn hoạt động theo cơ chế Spring for GraphQL thông thường.

## 4. Tạo client qua TCP

Cách tạo trực tiếp bằng builder:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.client.RSocketGraphQlClient;

@Configuration(proxyBeanMethods = false)
public class ProductClientConfiguration {

    @Bean
    public RSocketGraphQlClient productGraphQlClient() {
        return RSocketGraphQlClient.builder()
                .tcp("localhost", 7000)
                .route("graphql")
                .build();
    }
}
~~~

Các bước chính:

1. `RSocketGraphQlClient.builder()` tạo builder mới dựa trên `RSocketRequester.Builder` đã được tùy chỉnh cho GraphQL.
2. `tcp(host, port)` chọn TCP transport và địa chỉ RSocket server.
3. `route("graphql")` đặt route metadata để server chuyển request đến GraphQL handler.
4. `build()` tạo client instance.

Builder mặc định đặt data MIME type là `application/graphql+json` và đăng ký JSON codecs cần thiết. Thông thường không cần tự cấu hình MIME type nếu server dùng cấu hình mặc định của Spring for GraphQL.

## 5. Kết nối qua WebSocket transport

Nếu server mở RSocket qua WebSocket, client có thể cấu hình URI:

~~~java
import java.net.URI;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.client.RSocketGraphQlClient;

@Configuration(proxyBeanMethods = false)
public class ProductClientConfiguration {

    @Bean
    public RSocketGraphQlClient productGraphQlClient() {
        return RSocketGraphQlClient.builder()
                .webSocket(URI.create("ws://localhost:8080/rsocket"))
                .route("graphql")
                .build();
    }
}
~~~

Với môi trường production có TLS, dùng URI `wss://...` và cấu hình chứng thư/SSL phù hợp ở transport. Đường dẫn `/rsocket` trong ví dụ là WebSocket mapping của RSocket server; nó khác route GraphQL `graphql` được gửi trong RSocket metadata.

Có thể tạo transport tường minh rồi truyền vào builder:

~~~java
import java.net.URI;

import io.rsocket.transport.netty.client.WebsocketClientTransport;
import org.springframework.graphql.client.RSocketGraphQlClient;

URI uri = URI.create("ws://localhost:8080/rsocket");
RSocketGraphQlClient client = RSocketGraphQlClient.builder()
        .clientTransport(WebsocketClientTransport.create(uri))
        .route("graphql")
        .build();
~~~

`clientTransport(...)` hữu ích khi cần cung cấp một `ClientTransport` đã được cấu hình riêng. Nếu chỉ cần TCP hoặc WebSocket tiêu chuẩn, `tcp(...)` và `webSocket(...)` ngắn gọn hơn.

## 6. Sử dụng RSocketGraphQlClient được Spring Boot auto-configure

Khi ứng dụng có Spring Boot RSocket và GraphQL auto-configuration phù hợp, Boot cung cấp bean `RSocketGraphQlClient.Builder<?>`. Có thể inject builder vào component rồi tạo client:

~~~java
import org.springframework.graphql.client.RSocketGraphQlClient;
import org.springframework.stereotype.Component;

@Component
public class ProductGraphQlGateway {

    private final RSocketGraphQlClient client;

    public ProductGraphQlGateway(RSocketGraphQlClient.Builder<?> builder) {
        this.client = builder
                .tcp("catalog.internal", 7000)
                .route("graphql")
                .build();
    }
}
~~~

Builder auto-configured giúp ứng dụng tái sử dụng cấu hình chung của Spring Boot. Client instance nên được tạo một lần và giữ lại để dùng cho các request tiếp theo.

Nếu cần nhiều GraphQL server, tạo một client riêng cho từng server. Không dùng một builder đã cấu hình route/transport cho server A rồi giả định nó tự chuyển sang server B nếu không gọi `mutate()` hoặc tạo builder khác.

## 7. Gửi query và đọc kết quả

Sau khi tạo client, cách gửi request giống các implementation khác của `GraphQlClient`:

~~~java
import reactor.core.publisher.Mono;

public Mono<Product> findProduct(String id) {
    return client.document("""
            query ProductById($id: ID!) {
                product(id: $id) {
                    id
                    name
                    price
                }
            }
            """)
            .variable("id", id)
            .retrieve("product")
            .toEntity(Product.class);
}
~~~

`document(...)` nhận GraphQL operation. `variable(...)` truyền giá trị cho biến trong operation. `retrieve("product")` chọn đường dẫn tương đối với `data` trong response, sau đó `toEntity(Product.class)` chuyển giá trị thành Java object.

Có thể dùng nhiều variables:

~~~java
import java.util.List;
import reactor.core.publisher.Mono;

Mono<List<Product>> searchProducts(String keyword, int first) {
    return client.document("""
            query SearchProducts($keyword: String!, $first: Int!) {
                searchProducts(keyword: $keyword, first: $first) {
                    id
                    name
                    price
                }
            }
            """)
            .variable("keyword", keyword)
            .variable("first", first)
            .retrieve("searchProducts")
            .toEntityList(Product.class);
}
~~~

Các method không block. Chúng trả `Mono<T>` hoặc `Flux<T>`; caller quyết định cách compose và subscribe theo reactive model của ứng dụng.

## 8. Dùng execute khi cần kiểm tra toàn bộ GraphQL response

`retrieve(...)` là shortcut để lấy một field theo path. Khi cần xem `data`, `errors` hoặc nhiều field trong response, dùng `execute()`:

~~~java
import org.springframework.graphql.client.ClientGraphQlResponse;
import reactor.core.publisher.Mono;

public Mono<ClientGraphQlResponse> executeProductQuery(String id) {
    return client.document("""
            query ProductById($id: ID!) {
                product(id: $id) {
                    id
                    name
                    price
                }
            }
            """)
            .variable("id", id)
            .execute();
}
~~~

Caller có thể kiểm tra response:

~~~java
return executeProductQuery(id)
        .map(response -> {
            if (!response.isValid()) {
                // Request-level failure: the response may contain only errors.
                throw new IllegalStateException("GraphQL request was rejected");
            }

            var productField = response.field("product");
            if (productField.getValue() == null && !productField.getErrors().isEmpty()) {
                // The field failed during execution.
                throw new IllegalStateException("Product field could not be resolved");
            }

            return productField.toEntity(Product.class);
        });
~~~

Trong ứng dụng thực tế, nên giữ lại GraphQL errors hoặc chuyển chúng thành exception domain có thông tin phù hợp thay vì ném một `IllegalStateException` chung. `execute()` hữu ích khi cần phân biệt request failure, field-level error và giá trị null hợp lệ.

## 9. Hiểu FieldAccessException

Khi dùng `retrieve(path)`, Spring for GraphQL cần đọc field ở path đã chọn. Việc decode có thể phát sinh `FieldAccessException` nếu field không tồn tại hoặc field có giá trị null kèm GraphQL error.

~~~java
import org.springframework.graphql.client.FieldAccessException;
import reactor.core.publisher.Mono;

public Mono<Product> findProductOrFallback(String id) {
    return client.document("""
            query ProductById($id: ID!) {
                product(id: $id) { id name price }
            }
            """)
            .variable("id", id)
            .retrieve("product")
            .toEntity(Product.class)
            .onErrorResume(FieldAccessException.class, exception -> {
                var response = exception.getResponse();
                var field = exception.getField();
                // Inspect response errors and decide on a domain fallback.
                return Mono.empty();
            });
}
~~~

`FieldAccessException` cung cấp response và field gây lỗi để caller xem GraphQL errors, path và giá trị. Nếu field tồn tại nhưng không thể decode sang kiểu Java được yêu cầu, client có thể phát sinh `GraphQlClientException` thay vì `FieldAccessException`.

Không nên bắt `FieldAccessException` rồi mặc định trả `Mono.empty()` cho mọi trường hợp. Một field null hợp lệ, field bị resolver lỗi và response không có field là những trường hợp khác nhau; hãy xem lỗi và chính sách nghiệp vụ trước khi chọn fallback.

## 10. Dùng GraphQL document từ file

Không nhất thiết phải viết operation thành string trong Java. Có thể lưu document trong `src/main/resources/graphql-documents/`:

~~~graphql
query ProductById($id: ID!) {
    product(id: $id) {
        id
        name
        price
    }
}
~~~

Ví dụ file `src/main/resources/graphql-documents/productById.graphql`:

~~~java
public Mono<Product> findProduct(String id) {
    return client.documentName("productById")
            .variable("id", id)
            .retrieve("product")
            .toEntity(Product.class);
}
~~~

`documentName("productById")` tìm file `productById.graphql` trong classpath document source mặc định. Cách này tách operation khỏi Java code, thuận tiện cho syntax highlighting, GraphQL IDE plugin và review query riêng.

## 11. RSocketGraphQlClient hỗ trợ subscription

RSocket hỗ trợ streaming nên có thể dùng `RSocketGraphQlClient` để thực hiện GraphQL subscription. Ví dụ schema:

~~~graphql
type Subscription {
    stockPrice(symbol: String!): StockPrice!
}

type StockPrice {
    symbol: String!
    price: Float!
    updatedAt: String!
}
~~~

Client mở subscription:

~~~java
import reactor.core.publisher.Flux;

public Flux<StockPrice> stockPrices(String symbol) {
    return client.document("""
            subscription StockPriceUpdates($symbol: String!) {
                stockPrice(symbol: $symbol) {
                    symbol
                    price
                    updatedAt
                }
            }
            """)
            .variable("symbol", symbol)
            .retrieveSubscription("stockPrice")
            .toEntity(StockPrice.class);
}
~~~

`retrieveSubscription(...)` trả `Flux<T>` vì server có thể gửi nhiều kết quả theo thời gian. Nếu cần xem errors và metadata của từng event, dùng `executeSubscription()` để xử lý `ClientGraphQlResponse` thay vì chỉ decode một field.

Khi client hủy subscription bằng cách cancel `Flux`, transport gửi tín hiệu hoàn tất/hủy tương ứng đến server. Các toán tử như `take(n)`, `timeout(...)` hoặc việc cancel `Subscription` có thể kết thúc stream.

## 12. Vòng đời session: start, stop và reconnect

Khác với `HttpGraphQlClient`, RSocket client cần thiết lập session. Có hai cách:

**Kết nối tự động:** tạo client rồi gửi request. Session được mở khi request đầu tiên cần kết nối.

~~~java
Mono<Product> product = client.document("{ product(id: \"p-1\") { id name price } }")
        .retrieve("product")
        .toEntity(Product.class);
~~~

**Khởi động tường minh:** gọi `start()` khi ứng dụng sẵn sàng hoặc trước khi gửi request:

~~~java
Mono<Product> warmupAndFetch = client.start()
        .then(findProduct("p-1"));
~~~

`start()` trả `Mono<Void>` hoàn tất khi session đã được thiết lập. Nếu ứng dụng cần bảo đảm kết nối sẵn sàng trước khi nhận traffic, có thể đưa bước này vào lifecycle/startup orchestration và xử lý lỗi kết nối.

Khi ứng dụng dừng, gọi `stop()` để đóng session:

~~~java
client.stop().subscribe();
~~~

`stop()` hủy các request đang chạy, đóng session và từ chối request mới trên client đó. Tài liệu API lưu ý việc dispose session được kích hoạt ngay; không nên coi `stop()` như một cơ chế chờ toàn bộ công việc nghiệp vụ hoàn tất.

Nếu session bị mất, `RSocketGraphQlClient` có thể kết nối lại ở request kế tiếp hoặc khi gọi `start()` lại. Điều đó không có nghĩa mọi request đang chạy được replay an toàn. Với mutation, cần thiết kế idempotency và retry policy cẩn thận để tránh ghi dữ liệu hai lần.

## 13. Dùng một client instance cho mỗi server

RSocket client là connection-oriented và multiplexed: một session có thể phục vụ nhiều GraphQL request đồng thời. Vì vậy, thông thường nên tạo một instance dùng chung cho mỗi server:

~~~java
import org.springframework.graphql.client.RSocketGraphQlClient;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ProductGraphQlGateway {

    private final RSocketGraphQlClient client;

    public ProductGraphQlGateway(RSocketGraphQlClient.Builder<?> builder) {
        this.client = builder
                .tcp("catalog.internal", 7000)
                .route("graphql")
                .build();
    }

    public Mono<Product> findById(String id) {
        return client.document("""
                query Product($id: ID!) {
                    product(id: $id) { id name price }
                }
                """)
                .variable("id", id)
                .retrieve("product")
                .toEntity(Product.class);
    }
}
~~~

Không tạo client mới bên trong mỗi method `findById`. Mỗi instance tạo session riêng, khiến ứng dụng mở nhiều kết nối không cần thiết và mất lợi ích multiplexing.

Nếu cần client với cấu hình khác từ client hiện có, dùng `mutate()` để tạo builder độc lập rồi build client mới. Lưu ý client mới là instance mới và sẽ tạo session riêng.

## 14. Cấu hình route, MIME type và RSocketRequester

`RSocketGraphQlClient.Builder` cung cấp các tùy chọn quan trọng:

| Method | Mục đích |
| --- | --- |
| `tcp(host, port)` | Chọn TCP transport |
| `webSocket(uri)` | Chọn WebSocket transport |
| `clientTransport(transport)` | Dùng `ClientTransport` đã cấu hình |
| `route(route)` | Đặt route metadata cho GraphQL handler |
| `dataMimeType(mimeType)` | Thay đổi MIME type của data payload |
| `rsocketRequester(consumer)` | Tùy chỉnh underlying `RSocketRequester.Builder` |
| `build()` | Tạo `RSocketGraphQlClient` |

Mặc định data MIME type là `application/graphql+json`. Có thể đổi sang `application/json` nếu server hoặc môi trường tích hợp yêu cầu, nhưng hai phía phải thống nhất định dạng payload.

`rsocketRequester(...)` dành cho cấu hình chuyên sâu của RSocket requester, ví dụ setup metadata, MIME type, codec hoặc transport option. Khi dùng authentication metadata, phải cấu hình cả client và server theo cùng cơ chế bảo mật; route GraphQL không thay thế authentication.

## 15. Authentication và bảo mật transport

RSocket là transport, không tự quyết định người dùng có quyền thực hiện GraphQL operation hay không. Ứng dụng cần cấu hình xác thực và authorization ở tầng RSocket/Spring Security hoặc cơ chế bảo mật phù hợp của hệ thống.

Một số nguyên tắc:

1. Dùng TLS khi truyền dữ liệu qua mạng không tin cậy; với WebSocket bảo mật, dùng `wss://`.
2. Truyền credential qua RSocket authentication metadata hoặc cơ chế bảo mật đã được cấu hình, không nhúng token vào GraphQL query string.
3. Xác thực ở server trước khi cho phép operation chạy.
4. Kiểm tra quyền ở resolver/service cho từng tài nguyên; một session lâu dài không có nghĩa quyền không thay đổi.
5. Có chính sách hết hạn hoặc refresh credential cho session sống lâu.
6. Không log access token, password hoặc metadata nhạy cảm.

Nếu dùng `rsocketRequester(...)` để cấu hình setup metadata, hãy đối chiếu với cách server đọc metadata và Spring Security RSocket đang dùng. Không sao chép một MIME type authentication tùy ý nếu server chưa đăng ký decoder tương ứng.

## 16. Interceptor cho GraphQlClient

`RSocketGraphQlClient` kế thừa cấu hình interceptor chung của `GraphQlClient`. Với non-blocking client, dùng `GraphQlClientInterceptor` để quan sát hoặc biến đổi request/response:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.client.ClientGraphQlRequest;
import org.springframework.graphql.client.ClientGraphQlResponse;
import org.springframework.graphql.client.GraphQlClientInterceptor;
import reactor.core.publisher.Mono;

public class LoggingGraphQlClientInterceptor implements GraphQlClientInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(LoggingGraphQlClientInterceptor.class);

    @Override
    public Mono<ClientGraphQlResponse> intercept(
            ClientGraphQlRequest request,
            Chain chain
    ) {
        long started = System.nanoTime();

        return chain.next(request)
                .doOnNext(response -> {
                    long elapsed = System.nanoTime() - started;
                    log.debug("GraphQL client request completed in {} ns", elapsed);
                });
    }
}
~~~

Đăng ký interceptor qua builder:

~~~java
RSocketGraphQlClient client = RSocketGraphQlClient.builder()
        .tcp("localhost", 7000)
        .route("graphql")
        .interceptor(new LoggingGraphQlClientInterceptor())
        .build();
~~~

Interceptor phù hợp cho tracing, metrics hoặc thêm metadata ở cấp client request theo API hỗ trợ. Không ghi toàn bộ variables nếu chúng có thể chứa thông tin nhạy cảm.

## 17. Xử lý lỗi transport và GraphQL

Khi dùng RSocket, cần phân biệt hai lớp lỗi:

| Loại lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| GraphQL error | Validation error, resolver exception, field null kèm error | Đọc `ClientGraphQlResponse`, `errors`, `path` và `extensions` |
| RSocket transport error | Không kết nối được, session bị đóng, timeout hoặc disconnect | Kiểm tra endpoint, route, network, timeout và retry policy |
| Decode/binding error | Response field không chuyển được sang Java type | Kiểm tra selection set, DTO, scalar và codec |
| Subscription error | Server gửi subscription error hoặc stream kết thúc bất thường | Xử lý `SubscriptionErrorException` và lỗi transport trong Flux |

Với subscription, stream có thể kết thúc bằng `SubscriptionErrorException` khi server gửi thông điệp lỗi. Nếu session/connection bị mất, client có thể nhận `GraphQlTransportException`. Có thể dùng Reactor `retry` cho trường hợp phù hợp, nhưng cần phân biệt lỗi tạm thời với lỗi nghiệp vụ không nên retry.

Không retry mutation một cách mù quáng. Nếu response bị mất sau khi server đã commit mutation, gửi lại request có thể thực hiện hành động hai lần. Dùng idempotency key hoặc thiết kế mutation idempotent nếu cần retry.

## 18. Kiểm thử RSocketGraphQlClient

Kiểm thử integration nên có một RSocket server test với GraphQL mapping, sau đó tạo client trỏ đến port/route test. Nên kiểm tra:

1. Client kết nối được bằng TCP và route chính xác.
2. Query truyền variables và decode đúng DTO.
3. Mutation trả response đúng và không bị retry ngoài ý muốn.
4. `execute()` cho phép đọc GraphQL errors và partial data.
5. Subscription phát nhiều event và dừng khi Flux bị cancel.
6. Session được tái lập sau khi server restart hoặc connection bị đóng.
7. `stop()` đóng session và client từ chối request mới.
8. Authentication metadata được server xác thực và authorization được áp dụng.

Ví dụ kiểm tra logic request ở mức component (giả sử client đã được cấu hình và server test đang chạy):

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import reactor.test.StepVerifier;

@SpringBootTest
class ProductGraphQlClientTests {

    @Autowired
    ProductGraphQlGateway gateway;

    @Test
    void retrievesProductOverRSocket() {
        StepVerifier.create(gateway.findById("p-1"))
                .expectNextMatches(product ->
                        product.id().equals("p-1") && !product.name().isBlank()
                )
                .verifyComplete();
    }
}
~~~

Test trên giả định RSocket server và route `graphql` đã được khởi động trong test context, đồng thời dữ liệu fixture có sản phẩm `p-1`. Trong test tự khởi tạo server, cần quản lý port động và đóng server sau test để tránh xung đột port.

## 19. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không thiết lập được session | Sai host/port, transport hoặc server chưa chạy | Kiểm tra RSocket listener và cấu hình TCP/WebSocket |
| Server không nhận GraphQL request | Route client khác `spring.graphql.rsocket.mapping` | Đồng bộ route ở hai phía |
| Kết nối WebSocket thất bại | Dùng sai URI hoặc server không bật WebSocket transport | Kiểm tra scheme, path và WebSocket mapping |
| Payload không decode | Data MIME type hoặc codec không tương thích | Dùng mặc định `application/graphql+json` hoặc cấu hình hai phía đồng nhất |
| Mỗi request tạo kết nối mới | Tạo RSocketGraphQlClient trong từng method | Dùng một instance lâu dài cho mỗi server |
| Request đầu tiên có độ trễ kết nối | Session được thiết lập tự động khi gửi request đầu | Gọi `start()` trong startup nếu cần warm-up |
| Subscription không phát event | Server field không phải subscription stream hoặc transport không hỗ trợ streaming | Kiểm tra schema, resolver và RSocket server |
| Stream dừng sau disconnect | Session bị mất hoặc server đóng kết nối | Phân loại transport error và retry subscription có kiểm soát |
| Mutation bị thực hiện hai lần sau retry | Retry không idempotent | Dùng idempotency key hoặc không retry mutation tự động |
| Request bị từ chối dù kết nối thành công | Authentication/authorization metadata thiếu hoặc sai | Kiểm tra RSocket Security và chính sách server |

## 20. Quy trình triển khai RSocketGraphQlClient

Khi tích hợp GraphQL client qua RSocket:

1. Xác định server dùng RSocket TCP hay WebSocket.
2. Bật RSocket server và GraphQL route bằng Spring Boot hoặc cấu hình RSocket tương ứng.
3. Thêm dependency GraphQL và RSocket cần thiết.
4. Tạo `RSocketGraphQlClient` bằng builder, chọn transport và route khớp server.
5. Giữ một client instance cho mỗi server để dùng chung session và multiplex request.
6. Gửi query/mutation bằng `document`, `variable`, `retrieve` hoặc `execute`.
7. Dùng `retrieveSubscription` hoặc `executeSubscription` cho GraphQL subscription.
8. Chọn `start()` nếu cần kết nối sẵn trước request đầu tiên; gọi `stop()` khi quản lý vòng đời client kết thúc.
9. Cấu hình authentication, TLS, timeout và retry theo chính sách của hệ thống.
10. Kiểm thử query, lỗi GraphQL, lỗi transport, subscription, reconnect và cancellation.

`RSocketGraphQlClient` đem lại một client GraphQL reactive trên session RSocket lâu dài. Khi route, transport và vòng đời client được cấu hình đúng, ứng dụng có thể tái sử dụng cùng một session cho nhiều request và nhận stream subscription qua cùng API `GraphQlClient`.

## Tài liệu tham khảo

- [Spring for GraphQL — Client](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL — RSocketGraphQlClient API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/client/RSocketGraphQlClient.html)
- [Spring for GraphQL — RSocketGraphQlClient.Builder API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/client/RSocketGraphQlClient.Builder.html)
- [Spring Boot — Spring for GraphQL and RSocket](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring Framework — RSocketRequester](https://docs.spring.io/spring-framework/reference/rsocket.html)
