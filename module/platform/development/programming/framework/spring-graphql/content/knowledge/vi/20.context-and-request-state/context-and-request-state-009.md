# Correlation ID

Correlation ID là mã định danh được gắn với một request để các thành phần trong hệ thống có thể liên kết log, lỗi và lời gọi service phát sinh từ cùng một luồng xử lý. Với GraphQL, một HTTP request có thể thực thi nhiều resolver và gọi nhiều backend. Nếu mỗi thành phần chỉ ghi log riêng mà không có mã chung, việc lần theo nguyên nhân một lỗi hoặc độ trễ sẽ khó khăn.

Trong Spring for GraphQL, có thể nhận hoặc tạo Correlation ID tại `WebGraphQlInterceptor`, đưa giá trị đó vào `GraphQLContext`, đọc nó trong resolver và truyền tiếp tới các service phía sau. Cách làm này giúp các log của cùng một GraphQL operation có chung một mã tham chiếu.

## 1. Correlation ID giải quyết vấn đề gì?

Giả sử client gửi query lấy đơn hàng cùng khách hàng và các dòng sản phẩm:

```graphql
query OrderDetail($id: ID!) {
    order(id: $id) {
        id
        status
        customer {
            name
        }
        items {
            quantity
            product {
                name
            }
        }
    }
}
```

Một operation có thể đi qua nhiều thành phần:

- HTTP server nhận request GraphQL.
- Resolver `Query.order` tải đơn hàng.
- Resolver `Order.customer` lấy khách hàng.
- Resolver `Order.items` tải các dòng hàng.
- Resolver `OrderItem.product` gọi catalog service.
- Các repository hoặc service khác truy cập database.

Nếu mỗi log chỉ chứa tên class hoặc message, sẽ khó xác định log nào thuộc cùng request, nhất là khi nhiều người dùng gọi API đồng thời. Correlation ID cung cấp một giá trị chung để lọc và nối các log này.

Ví dụ các log cùng một request:

```text
correlationId=7b2... operation=OrderDetail event=request_received
correlationId=7b2... field=Query.order event=resolver_started
correlationId=7b2... service=customer event=lookup_completed
correlationId=7b2... service=catalog event=timeout
correlationId=7b2... event=request_completed status=ERROR
```

Nhờ đó, người vận hành có thể tìm tất cả sự kiện có cùng `correlationId` và dựng lại đường đi của request.

## 2. Phân biệt Correlation ID, Request ID và Trace ID

Các hệ thống có thể dùng những tên này theo quy ước khác nhau. Nên thống nhất ý nghĩa trong dự án:

| Giá trị | Mục đích thường gặp | Phạm vi |
| --- | --- | --- |
| Request ID | Định danh một request cụ thể tại một service hoặc gateway | Một lần nhận request |
| Correlation ID | Liên kết nhiều log và hoạt động liên quan trong một luồng nghiệp vụ | Có thể đi qua nhiều service |
| Trace ID | Định danh distributed trace gồm nhiều span theo chuẩn tracing | Một distributed trace |
| Span ID | Định danh một đơn vị công việc bên trong trace | Một span |

Correlation ID có thể được tạo tại gateway và truyền qua nhiều service. Trace ID và Span ID thường do hệ thống tracing như Micrometer Tracing quản lý, với propagation theo chuẩn như W3C Trace Context (`traceparent`).

Không nên tự coi `X-Correlation-ID` là `traceparent` hoặc thay thế cơ chế distributed tracing bằng một UUID. Correlation ID hữu ích để tìm kiếm và đối chiếu log; tracing cung cấp quan hệ cha-con, thời gian và topology của các span. Hai cơ chế có thể cùng tồn tại.

## 3. Chọn nơi tạo hoặc tiếp nhận Correlation ID

Có hai tình huống phổ biến:

1. Request đến đã có Correlation ID từ API gateway hoặc service gọi trước đó. Ứng dụng xác thực định dạng và tiếp tục sử dụng giá trị đó.
2. Request không có ID hợp lệ. Ứng dụng tạo một ID mới, chẳng hạn UUID, rồi dùng xuyên suốt quá trình xử lý.

Ví dụ sử dụng HTTP header `X-Correlation-ID`:

```http
POST /graphql HTTP/1.1
Content-Type: application/json
X-Correlation-ID: 7b2d9a1f-4a9b-4d5c-9c7d-1f6a0d4e8b10
```

Tên header là quy ước của ứng dụng, không phải một phần bắt buộc của GraphQL. Có thể dùng tên khác, nhưng client, gateway, server và downstream service phải thống nhất.

Không nên chấp nhận nguyên văn mọi giá trị header do client gửi. Hãy giới hạn độ dài, ký tự hợp lệ và cách ghi log để tránh log injection hoặc dữ liệu quá lớn. Nếu giá trị không hợp lệ, có thể từ chối request theo chính sách bảo mật hoặc tạo ID mới. Ví dụ dưới đây chọn cách tạo ID mới khi header thiếu hoặc sai định dạng.

## 4. Tạo WebGraphQlInterceptor

`WebGraphQlInterceptor` là extension point của Spring for GraphQL để can thiệp vào request/response ở lớp web. Interceptor phù hợp để đọc HTTP header, tạo Correlation ID, đưa nó vào execution context và thêm lại vào response header.

```java
package com.example.graphql.config;

import java.util.UUID;
import java.util.regex.Pattern;

import org.springframework.core.annotation.Order;
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public class CorrelationIdInterceptor implements WebGraphQlInterceptor {

    public static final String HEADER_NAME = "X-Correlation-ID";
    public static final String CONTEXT_KEY = "correlationId";

    private static final Pattern VALID_ID =
        Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String correlationId = resolveCorrelationId(
            request.getHeaders().getFirst(HEADER_NAME));

        request.configureExecutionInput((input, builder) ->
            builder.graphQLContext(context ->
                context.put(CONTEXT_KEY, correlationId)
            ).build()
        );

        return chain.next(request)
            .doOnNext(response -> response.getResponseHeaders()
                .set(HEADER_NAME, correlationId));
    }

    private String resolveCorrelationId(String incoming) {
        if (incoming != null && VALID_ID.matcher(incoming).matches()) {
            return incoming;
        }
        return UUID.randomUUID().toString();
    }
}
```

Các bước chính:

1. Đọc header `X-Correlation-ID` từ `WebGraphQlRequest`.
2. Kiểm tra giá trị có chỉ chứa ký tự cho phép và có độ dài giới hạn.
3. Nếu thiếu hoặc không hợp lệ, tạo UUID mới.
4. Dùng `configureExecutionInput` để đưa ID vào `GraphQLContext`.
5. Sau khi chain xử lý xong, thêm cùng ID vào response header.

`@Component` giúp Spring đăng ký interceptor. `@Order` có thể dùng để xác định thứ tự khi ứng dụng có nhiều interceptor; chọn thứ tự phù hợp với các interceptor khác trong dự án.

## 5. Vì sao đưa Correlation ID vào GraphQLContext?

`GraphQLContext` là vùng context gắn với quá trình thực thi GraphQL. Nó phù hợp để chia sẻ dữ liệu request-level giữa các resolver mà không cần thêm một argument vào schema.

Trong ví dụ interceptor:

```java
request.configureExecutionInput((input, builder) ->
    builder.graphQLContext(context ->
        context.put("correlationId", correlationId)
    ).build()
);
```

Giá trị được lưu với key `correlationId`. Resolver, data fetcher hoặc thành phần thực thi có thể đọc giá trị đó trong cùng GraphQL execution.

Không nên thêm Correlation ID thành argument của từng field như `book(id: ID!, correlationId: String)`. Đây là metadata của request, không phải dữ liệu nghiệp vụ mà client cần điều khiển. Đưa nó vào context giúp giữ schema gọn và tránh lặp argument ở mọi field.

GraphQLContext cũng không phải nơi lưu trạng thái toàn cục. Mỗi request cần có context riêng; không lưu Correlation ID vào static field hoặc singleton mutable state vì các request đồng thời có thể ghi đè giá trị của nhau.

## 6. Đọc Correlation ID trong resolver bằng @ContextValue

Spring for GraphQL cung cấp `@ContextValue` để lấy giá trị từ GraphQL context trong handler method.

```java
package com.example.graphql.order;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.ContextValue;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class OrderQueryController {

    private static final Logger log =
        LoggerFactory.getLogger(OrderQueryController.class);

    private final OrderService orderService;

    public OrderQueryController(OrderService orderService) {
        this.orderService = orderService;
    }

    @QueryMapping
    public OrderView order(
            @Argument("id") String id,
            @ContextValue("correlationId") String correlationId) {

        log.info("Resolving order id={} correlationId={}", id, correlationId);
        return orderService.findById(id);
    }
}
```

`@ContextValue("correlationId")` lấy đúng key mà interceptor đã ghi vào context. Không cần thêm field vào SDL và client không thể tự thay đổi giá trị này thông qua GraphQL variables.

Nếu context value là tùy chọn, có thể cấu hình cách xử lý khi key không tồn tại hoặc dùng kiểu nhận giá trị nullable phù hợp. Trong ứng dụng này interceptor luôn tạo ID trước khi thực thi, nên resolver có thể xem đây là giá trị bắt buộc. Dù vậy, hãy kiểm tra cấu hình nếu có nhiều entry point hoặc test không đi qua interceptor.

## 7. Đọc context trực tiếp qua DataFetchingEnvironment

Khi cần truy cập GraphQL Java API hoặc truyền context cho một thành phần phức tạp, có thể nhận `DataFetchingEnvironment`:

```java
import graphql.schema.DataFetchingEnvironment;

@QueryMapping
public OrderView order(
        @Argument("id") String id,
        DataFetchingEnvironment environment) {

    String correlationId = environment.getGraphQlContext()
        .get("correlationId");

    return orderService.findById(id);
}
```

`environment.getGraphQlContext()` cung cấp context của GraphQL execution. Cách này hữu ích khi method cần nhiều metadata khác như tenant, locale hoặc thông tin request đã được xác thực.

Nếu chỉ cần một giá trị, `@ContextValue` thường làm chữ ký method gọn và thể hiện dependency rõ hơn. Tránh đọc context tùy tiện ở mọi tầng; nên truyền ID như một tham số rõ ràng tới service hoặc component cần ghi log.

## 8. Truyền Correlation ID tới downstream service

Correlation ID chỉ hữu ích xuyên hệ thống khi các service phía sau cũng nhận và ghi lại nó. Khi resolver gọi một HTTP service khác bằng `WebClient`, có thể truyền ID trong header của lời gọi đó.

```java
package com.example.graphql.order;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class CustomerClient {

    private final WebClient webClient;

    public CustomerClient(WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<CustomerView> findCustomer(
            String customerId,
            String correlationId) {

        return webClient.get()
            .uri("/customers/{id}", customerId)
            .header("X-Correlation-ID", correlationId)
            .retrieve()
            .bodyToMono(CustomerView.class);
    }
}
```

Service trung gian có thể đọc header này, ghi log và truyền tiếp tới hệ thống kế tiếp. Mỗi service nên giữ cùng giá trị Correlation ID cho một luồng request nếu mục tiêu là liên kết log xuyên dịch vụ.

Nếu dùng `RestClient`, `RestTemplate`, messaging hoặc gRPC, cách gắn metadata sẽ khác nhau. Hãy xây dựng một quy ước propagation thống nhất và dùng interceptor/filter của client tương ứng để tránh quên header ở một số lời gọi.

Không gửi Correlation ID như một bằng chứng xác thực. Downstream service vẫn phải xác thực caller và kiểm tra quyền độc lập.

## 9. Correlation ID trong log và MDC

Có thể ghi Correlation ID như một structured logging field:

```java
log.info("Loading customer customerId={} correlationId={}",
    customerId, correlationId);
```

Hoặc đưa vào MDC để logging pattern tự thêm field:

```java
try (var ignored = org.slf4j.MDC.putCloseable(
        "correlationId", correlationId)) {
    log.info("Loading order id={}", orderId);
}
```

MDC thường gắn với thread. Với Spring WebFlux, Reactor và các resolver bất đồng bộ, công việc có thể chạy trên thread khác. Không nên giả định MDC được truyền tự động qua mọi async boundary. Đặt và xóa MDC thủ công quanh một đoạn đồng bộ không bảo đảm giá trị còn tồn tại trong callback chạy sau đó.

Với ứng dụng reactive, ưu tiên truyền Correlation ID tường minh hoặc sử dụng cơ chế context propagation tương thích với Reactor/Micrometer đã được cấu hình trong ứng dụng. Nếu dùng MDC bridge, hãy xác minh cả trường hợp đổi thread, lỗi và cancellation; tránh để giá trị của request trước rò sang request khác.

## 10. Kết hợp với Micrometer Tracing

Correlation ID và distributed tracing bổ sung cho nhau. Nếu ứng dụng đã dùng Micrometer Tracing, các span có thể chứa trace ID và span ID để thể hiện quan hệ giữa GraphQL server, resolver và downstream client khi instrumentation được cấu hình.

Một quy ước log có thể bao gồm:

```text
correlationId=7b2... traceId=4bf... spanId=91a... operation=OrderDetail
```

- `correlationId` giúp tìm log theo mã nghiệp vụ hoặc mã do gateway truyền.
- `traceId` liên kết các span trong một distributed trace.
- `spanId` xác định một bước cụ thể trong trace.

Nếu hệ thống đã có W3C Trace Context, hãy để tracing instrumentation quản lý `traceparent` và propagation. Không tự tạo header `traceparent` theo định dạng tùy ý. Có thể giữ Correlation ID như một thuộc tính log bổ sung để người vận hành dễ đối chiếu với ticket, request từ client hoặc hệ thống cũ.

## 11. Correlation ID khi có nhiều resolver và DataLoader

Một GraphQL operation có thể gọi nhiều resolver song song hoặc theo các nhịp thực thi khác nhau. Vì vậy, Correlation ID nên thuộc về GraphQL execution context, không thuộc riêng một resolver.

Ví dụ `Query.order`, `Order.customer` và `Order.items` đều có thể đọc cùng `correlationId` từ context. Khi các resolver dùng DataLoader, batch loader cũng có thể nhận `BatchLoaderEnvironment` và truy cập context được truyền trong quá trình thực thi theo API phù hợp của Spring for GraphQL/GraphQL Java.

Không lưu Correlation ID vào field mutable của singleton service hoặc biến static. Những thành phần này được dùng đồng thời bởi nhiều request và có thể khiến log gắn nhầm ID.

Với DataLoader cache mặc định theo request, Correlation ID thường không cần đưa vào cache key nếu loader chỉ tồn tại trong request đó. Tuy nhiên, nếu một loader hoặc cache được dùng chung ngoài request scope, phải xem lại thiết kế để không trộn dữ liệu giữa người dùng/tenant. Correlation ID không thay thế tenant key hay authorization context.

## 12. Correlation ID với GraphQL errors

Một GraphQL response có thể chứa cả `data` và `errors`. Correlation ID nên được ghi ở log khi resolver hoặc exception handler xử lý lỗi, để client có thể cung cấp mã này khi báo sự cố.

Ví dụ client nhận response header:

```http
X-Correlation-ID: 7b2d9a1f-4a9b-4d5c-9c7d-1f6a0d4e8b10
```

Nếu response có lỗi, client gửi ID này cùng thông tin operation name và thời điểm xảy ra cho đội vận hành. Server có thể tìm log tương ứng mà không cần client gửi toàn bộ dữ liệu nhạy cảm.

Không nhất thiết phải lặp Correlation ID trong mọi `errors[].extensions`. Response header thường đủ cho HTTP client và tránh làm payload lỗi phức tạp. Nếu API có yêu cầu đặc biệt để client chỉ đọc body, có thể thêm extension qua error handler, nhưng cần thống nhất schema lỗi và tránh lộ thông tin nội bộ.

Interceptor ở ví dụ trên thêm header khi GraphQL handler trả về response, kể cả khi response có GraphQL errors. Nếu muốn mọi HTTP response đều có ID, bao gồm lỗi xảy ra trước khi GraphQL handler được gọi, hãy đặt Correlation ID ở HTTP filter hoặc gateway layer và cấu hình GraphQL interceptor đọc lại giá trị đó.

## 13. Bảo mật khi tiếp nhận Correlation ID

Correlation ID là dữ liệu đầu vào từ bên ngoài nếu client được phép gửi header. Cần xử lý nó như input không đáng tin cậy:

- Giới hạn độ dài và tập ký tự được chấp nhận.
- Không cho phép ký tự xuống dòng hoặc ký tự điều khiển có thể làm giả log entry.
- Không dùng Correlation ID làm token, session ID, API key hoặc căn cứ phân quyền.
- Không đưa email, số điện thoại, access token hoặc dữ liệu cá nhân vào ID.
- Không để client tùy ý tạo ID cực dài gây tăng dung lượng log hoặc cardinality.
- Nếu gateway là nguồn tin cậy, chỉ tin header đã được gateway chuẩn hóa và chặn client giả mạo theo kiến trúc mạng phù hợp.
- Không dùng Correlation ID làm label có cardinality cao trong metric; hãy dùng log hoặc trace để truy vấn từng request.

Nếu cần bảo đảm ID do hệ thống sinh ra, có thể bỏ qua header bên ngoài và luôn tạo UUID mới ở gateway hoặc ứng dụng. Nếu cần giữ ID xuyên hệ thống, cần xác định rõ ranh giới tin cậy và quy tắc xác thực định dạng.

## 14. Kiểm thử Correlation ID

Nên kiểm tra cả ba hành vi: tạo ID khi thiếu, giữ ID hợp lệ và truyền ID vào execution context/response header.

Với kiểm thử HTTP integration, có thể gửi request tới `/graphql` và xác minh response header:

```java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CorrelationIdHttpTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void echoesValidCorrelationId() {
        webTestClient.post()
            .uri("/graphql")
            .header("Content-Type", "application/json")
            .header("X-Correlation-ID", "test-request-42")
            .bodyValue(Map.of("query", "{ books { id } }"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                "X-Correlation-ID", "test-request-42");
    }
}
```

Đoạn test minh họa với `WebTestClient`; cần có GraphQL endpoint và schema `books` tương ứng trong test context. Có thể bổ sung kiểm tra mock service/resolver nhận đúng context value `test-request-42`.

Các trường hợp nên kiểm thử:

- Header không được gửi: server tạo ID và trả lại response header.
- Header hợp lệ: response giữ nguyên ID theo chính sách propagation.
- Header sai định dạng hoặc quá dài: server tạo ID mới hoặc trả lỗi theo chính sách đã chọn.
- GraphQL response có `errors`: Correlation ID vẫn có trong header.
- Nhiều request đồng thời: mỗi request có ID riêng và log không bị trộn.
- Downstream client: header được truyền đúng khi gọi service khác.
- Reactive flow: context và log vẫn đúng khi có chuyển thread hoặc async completion.

## 15. CORS và khả năng đọc response header từ browser

Nếu frontend chạy ở origin khác, browser có thể không cho JavaScript đọc mọi response header trừ khi server expose header đó qua CORS.

Ví dụ cấu hình CORS cần expose `X-Correlation-ID`:

```http
Access-Control-Expose-Headers: X-Correlation-ID
```

Nếu không expose, header vẫn có thể xuất hiện trong network inspector nhưng frontend không đọc được bằng Fetch API hoặc XMLHttpRequest. Hãy cấu hình CORS tại đúng lớp chịu trách nhiệm, chẳng hạn Spring Security, Web MVC/WebFlux hoặc API gateway; tránh khai báo nhiều chính sách CORS mâu thuẫn.

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Resolver không đọc được Correlation ID | Interceptor chưa đăng ký hoặc context key không khớp | Kiểm tra bean, thứ tự interceptor và tên key |
| Mọi request dùng chung một ID | Lưu ID trong static field hoặc singleton mutable state | Đưa giá trị vào context riêng của request |
| Downstream log thiếu ID | Không truyền header/metadata trong client call | Bổ sung propagation tại HTTP client hoặc messaging adapter |
| ID bị đổi ở giữa luồng | Mỗi service tự tạo ID mới thay vì tiếp tục ID đã nhận | Thống nhất quy tắc trust và propagation |
| MDC mất khi resolver async | MDC gắn với thread và không tự đi theo Reactor | Dùng context propagation hoặc truyền ID tường minh |
| Log có nhiều ID giả hoặc dữ liệu bất thường | Chấp nhận header không kiểm tra | Validate độ dài, ký tự và nguồn tin cậy |
| Browser không đọc được response header | Chưa expose header qua CORS | Thêm `Access-Control-Expose-Headers` |
| Metric tăng cardinality mạnh | Dùng ID riêng từng request làm metric label | Đưa ID vào log/trace thay vì label metric |

## 17. Checklist triển khai

- Đã thống nhất tên header và phạm vi Correlation ID giữa gateway, GraphQL server và downstream service?
- Interceptor có nhận ID hợp lệ hoặc tạo ID mới khi cần?
- Giá trị đầu vào đã được giới hạn độ dài và ký tự?
- ID đã được đưa vào `GraphQLContext` theo từng request?
- Resolver và batch loader đọc context đúng cách?
- Downstream HTTP/messaging client có truyền ID tiếp không?
- Logging không làm mất ID khi xử lý bất đồng bộ?
- Correlation ID được phân biệt với Trace ID và Span ID?
- GraphQL response có trả ID để client báo lỗi?
- Browser client có thể đọc header qua CORS khi cần?
- ID không được dùng làm cơ chế xác thực hoặc metric label có cardinality cao?
- Test đã bao phủ request đồng thời, lỗi và propagation?

Correlation ID giúp liên kết các sự kiện phát sinh từ cùng một GraphQL request qua resolver và các service phía sau. Trong Spring for GraphQL, `WebGraphQlInterceptor` có thể nhận hoặc tạo ID, lưu nó vào `GraphQLContext` và trả lại qua response header. Resolver đọc bằng `@ContextValue`, sau đó truyền ID tới downstream client và logging. Khi giữ phạm vi request rõ ràng, kiểm tra header đầu vào và kết hợp đúng với Micrometer Tracing, đội ngũ có thể lần theo lỗi và độ trễ xuyên hệ thống mà không biến Correlation ID thành dữ liệu xác thực hoặc trạng thái dùng chung.
