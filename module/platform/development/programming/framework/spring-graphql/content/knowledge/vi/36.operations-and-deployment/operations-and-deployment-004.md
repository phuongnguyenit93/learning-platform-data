# Cấu hình timeout

Một GraphQL request có thể gọi nhiều resolver, truy vấn database, gọi dịch vụ HTTP khác hoặc chờ một nguồn dữ liệu bất đồng bộ. Nếu một dependency bị chậm, request có thể giữ tài nguyên lâu hơn dự kiến và làm các request khác phải chờ.

Timeout đặt giới hạn thời gian cho từng công đoạn. Trong Spring for GraphQL, có thể cấu hình timeout ở nhiều tầng: request GraphQL, HTTP transport, xử lý async của Spring MVC, SSE/WebSocket, WebClient và database. Mỗi timeout bảo vệ một phần khác nhau của hệ thống; không có một giá trị duy nhất tự động dừng mọi công việc.

Spring Boot không cung cấp một thuộc tính chung spring.graphql.timeout để tự giới hạn mọi GraphQL operation. Với web transports, cách tích hợp trực tiếp là đăng ký TimeoutWebGraphQlInterceptor; các thuộc tính khác chỉ áp dụng cho đúng transport hoặc dependency mà chúng quản lý.

## Phân biệt các loại timeout

Trước khi cấu hình, cần xác định chính xác điều gì đang chờ:

| Loại timeout | Giới hạn điều gì? | Ví dụ |
| --- | --- | --- |
| GraphQL request timeout | Thời gian từ lúc nhận request đến khi GraphQL response sẵn sàng | Một query cần nhiều resolver |
| MVC async timeout | Thời gian xử lý một Servlet request đang ở chế độ async | Resolver trả CompletableFuture chưa hoàn tất |
| HTTP server/proxy timeout | Thời gian kết nối, đọc request hoặc chờ response ở server/gateway | Reverse proxy chờ backend |
| WebClient connect timeout | Thời gian thiết lập kết nối tới dịch vụ HTTP khác | Kết nối TCP/TLS tới Author API |
| WebClient response/read timeout | Thời gian chờ dữ liệu phản hồi từ dịch vụ khác | Dịch vụ tìm kiếm không trả response |
| Database query/statement timeout | Thời gian một câu SQL được phép chạy | Query tìm kiếm sách bị chậm |
| Transaction timeout | Thời gian transaction được phép tồn tại theo transaction manager | Một use case ghi dữ liệu |
| WebSocket connection-init timeout | Thời gian client phải gửi thông điệp CONNECTION_INIT sau khi mở socket | Client mở socket nhưng không xác thực |
| SSE response-start timeout | Thời gian chờ tạo response để bắt đầu stream SSE | Subscription không thể thiết lập stream |
| Subscription/event timeout | Thời gian chờ event hoặc giới hạn thời gian sống của một stream | Nguồn event ngừng phát dữ liệu |

Không nên dùng spring.mvc.async.request-timeout để thay thế timeout của GraphQL hoặc dùng WebSocket keep-alive như một giới hạn thời gian chạy query. Cần chọn đúng tầng dựa trên tài nguyên đang bị giữ.

## Timeout cho GraphQL request với TimeoutWebGraphQlInterceptor

Spring for GraphQL cung cấp TimeoutWebGraphQlInterceptor để giới hạn thời gian xử lý request qua các web transport. Khi hết thời gian, interceptor kết thúc request với HTTP status mặc định là 408 Request Timeout và gửi tín hiệu cancel ngược lên chuỗi xử lý. Các reactive data fetcher có thể nhận tín hiệu hủy và dừng công việc đang chạy.

Lớp này có từ Spring for GraphQL 1.4.0. Trong ứng dụng Spring Boot, chỉ cần đăng ký interceptor thành bean:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.TimeoutWebGraphQlInterceptor;

@Configuration(proxyBeanMethods = false)
public class GraphQlTimeoutConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor timeoutWebGraphQlInterceptor() {
        return new TimeoutWebGraphQlInterceptor(
                Duration.ofSeconds(5));
    }
}
~~~

Trong ví dụ, một request GraphQL có tối đa 5 giây để tạo response. Giá trị này chỉ là ví dụ; hãy chọn theo SLA, độ trễ dependency và loại operation của ứng dụng.

Có thể chỉ định HTTP status khác nếu ứng dụng có quy ước riêng:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.TimeoutWebGraphQlInterceptor;
import org.springframework.http.HttpStatus;

@Configuration(proxyBeanMethods = false)
public class GraphQlTimeoutConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor timeoutWebGraphQlInterceptor() {
        return new TimeoutWebGraphQlInterceptor(
                Duration.ofSeconds(5),
                HttpStatus.REQUEST_TIMEOUT);
    }
}
~~~

Hai đoạn cấu hình trên là hai lựa chọn thay thế; chỉ đăng ký một bean TimeoutWebGraphQlInterceptor. Với cấu hình thứ hai, status vẫn là 408; constructor nhận HttpStatus hữu ích khi cần đặt status theo quy ước HTTP của hệ thống.

### Timeout áp dụng tới đâu?

TimeoutWebGraphQlInterceptor giới hạn thời gian chờ response GraphQL được tạo ra. Nó không phải một công cụ giết thread và không thể bảo đảm mọi công việc blocking dừng ngay lập tức.

Khi timeout xảy ra:

- Reactive data fetcher như Mono hoặc Flux có thể nhận cancel signal và hủy upstream subscription.
- Một tác vụ HTTP reactive có thể dừng chờ nếu client hỗ trợ cancellation.
- Một câu JDBC/JPA blocking đang chạy có thể tiếp tục trên thread hoặc tại database nếu driver/database không hỗ trợ hủy tương ứng.
- Một CompletableFuture không tự động dừng công việc bên trong chỉ vì response GraphQL đã timeout.

Do đó, timeout request cần đi cùng timeout của WebClient, database và transaction. Nếu chỉ đóng response, công việc phía sau có thể tiếp tục chiếm connection, thread hoặc CPU.

### Giới hạn với subscription

Subscription trả về một stream thay vì một response hoàn chỉnh duy nhất. TimeoutWebGraphQlInterceptor chỉ áp dụng đến lúc response stream được thiết lập. Sau khi stream bắt đầu, interceptor không đặt giới hạn tổng thời gian sống của subscription.

Để quản lý stream, cần thêm chính sách riêng: giới hạn thời gian chờ event, giới hạn thời gian sống, đóng subscription khi client hủy, giới hạn số subscription trên mỗi session và keep-alive của transport. Các phần này được trình bày ở mục WebSocket và SSE.

## Timeout cho Spring MVC async request

Spring for GraphQL có thể thực thi request bất đồng bộ trên Spring MVC. Khi GraphQL engine trả về một CompletableFuture chưa hoàn tất, Spring MVC chuyển Servlet request sang async mode và giữ response mở để chờ kết quả.

Spring Boot cung cấp thuộc tính:

~~~yaml
spring:
  mvc:
    async:
      request-timeout: 6s
~~~

spring.mvc.async.request-timeout giới hạn thời gian xử lý Servlet async request. Nếu không cấu hình, timeout phụ thuộc Servlet container và cấu hình hiện hành.

Đây là giới hạn của tầng Spring MVC. Nó có thể kết thúc quá trình chờ async của HTTP response, nhưng không thay thế timeout chuyên biệt của GraphQL. Một GraphQL request hoàn tất đồng bộ ngay trong lần gọi GraphQL Java có thể không đi qua async processing của MVC; vì vậy không nên chỉ dựa vào thuộc tính này để bảo vệ mọi GraphQL operation.

Nếu dùng Spring MVC, có thể phối hợp thuộc tính MVC async timeout với bean TimeoutWebGraphQlInterceptor có thời gian ngắn hơn, chẳng hạn 5 giây. Khi đó GraphQL có cơ hội kết thúc request và trả lỗi timeout trước khi MVC async timeout xảy ra.

Không đặt MVC async timeout ngắn hơn GraphQL request timeout nếu muốn client nhận phản hồi timeout do GraphQL interceptor tạo ra. Nếu MVC đóng request trước, tầng transport có thể kết thúc response mà không còn cơ hội gửi kết quả theo chính sách GraphQL.

## Timeout cho WebFlux

WebFlux xử lý HTTP theo reactive pipeline và không sử dụng Servlet async request. Vì vậy, spring.mvc.async.request-timeout không áp dụng cho ứng dụng WebFlux.

Với WebFlux, dùng TimeoutWebGraphQlInterceptor để giới hạn thời gian xử lý GraphQL request. Ngoài ra, cần cấu hình timeout riêng cho các dependency reactive như WebClient và database client.

Ví dụ một resolver trả về Mono:

~~~java
import java.time.Duration;

import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Mono<BookView> slowBook() {
        return bookService.findBook()
                .timeout(Duration.ofSeconds(3));
    }
}
~~~

Mono.timeout giới hạn thời gian cho publisher của resolver. Nếu publisher không phát kết quả trong thời gian quy định, nó phát lỗi timeout và hủy upstream subscription. Lỗi này đi qua cơ chế xử lý exception của GraphQL; nếu muốn response có mã lỗi riêng, hãy ánh xạ timeout trong DataFetcherExceptionResolver hoặc exception handler.

Timeout của resolver không thay thế timeout toàn request. Một query có nhiều resolver song song; mỗi resolver có thể mất ít hơn 3 giây nhưng tổng request vẫn vượt deadline. Vì vậy nên kết hợp timeout từng dependency với timeout request.

## Timeout cho HTTP downstream bằng WebClient

GraphQL resolver thường gọi service khác để lấy dữ liệu. WebClient cần timeout kết nối và timeout phản hồi riêng.

Với Reactor Netty, có thể cấu hình CONNECT_TIMEOUT_MILLIS và responseTimeout:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Configuration(proxyBeanMethods = false)
public class DownstreamClientConfiguration {

    @Bean
    WebClient authorWebClient(WebClient.Builder builder) {
        HttpClient httpClient = HttpClient.create()
                .option(
                        ChannelOption.CONNECT_TIMEOUT_MILLIS,
                        500)
                .responseTimeout(Duration.ofSeconds(2));

        return builder
                .baseUrl("https://author.internal")
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
~~~

Trong ví dụ:

- Connect timeout 500 ms giới hạn thời gian thiết lập kết nối.
- Response timeout 2 giây giới hạn thời gian chờ phản hồi ở tầng HTTP client.
- Đây là timeout của kết nối tới Author service, không phải timeout toàn bộ GraphQL request.

Resolver có thể gọi client:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class AuthorClient {

    private final WebClient authorWebClient;

    public AuthorClient(WebClient authorWebClient) {
        this.authorWebClient = authorWebClient;
    }

    public Mono<AuthorView> findById(String id) {
        return authorWebClient.get()
                .uri("/authors/{id}", id)
                .retrieve()
                .bodyToMono(AuthorView.class);
    }
}
~~~

Nếu dùng Reactor Netty, responseTimeout là lựa chọn phù hợp để giới hạn chờ response ở tầng HTTP client. Có thể dùng ReadTimeoutHandler hoặc WriteTimeoutHandler khi cần timeout đọc/ghi ở cấp channel, nhưng hãy hiểu rõ phạm vi của từng handler và tránh cấu hình trùng lặp không cần thiết.

Với Reactor Netty, responseTimeout giới hạn khoảng thời gian chờ giữa các lần đọc dữ liệu response ở tầng network. Nó không nhất thiết giới hạn tổng thời gian từ lúc gửi request đến khi body hoàn tất nếu server liên tục gửi dữ liệu. Nếu cần deadline tuyệt đối cho toàn bộ publisher, dùng thêm Mono.timeout hoặc deadline ở tầng request.

Reactor cũng cung cấp toán tử timeout(Duration) trên Mono/Flux để giới hạn toàn bộ publisher:

~~~java
return authorWebClient.get()
        .uri("/authors/{id}", id)
        .retrieve()
        .bodyToMono(AuthorView.class)
        .timeout(Duration.ofSeconds(2));
~~~

Toán tử này giới hạn thời gian từ lúc publisher được subscribe đến khi có terminal signal. Các timeout chuyên biệt của HTTP client cho phép kiểm soát rõ hơn từng giai đoạn như connect và response; không nên dùng một timeout tổng để thay thế tất cả.

## Timeout cho database và transaction

Một GraphQL request có thể vượt deadline vì một câu SQL chậm hoặc chờ connection pool. Cần phân biệt:

- Connection acquisition timeout: thời gian chờ lấy connection từ pool.
- Statement/query timeout: thời gian database được phép thực thi câu lệnh.
- Transaction timeout: thời gian transaction được phép tồn tại theo transaction manager.
- GraphQL request timeout: thời gian chờ response GraphQL hoàn tất.

Ví dụ một request có deadline 5 giây nhưng truy vấn database được phép chạy tới 5 giây thì request không còn thời gian để xử lý mapping, gọi dependency khác và serialize response. Hãy đặt timeout database thấp hơn request deadline.

Với Spring JDBC, có thể đặt query timeout trên JdbcTemplate hoặc trên JdbcTemplate/JdbcClient được cấu hình riêng cho use case. Với JPA/Hibernate, dùng query timeout hint hoặc cấu hình tương ứng với provider và database. Kiểm tra driver có thực sự gửi cancel statement tới database hay chỉ ngừng chờ ở phía ứng dụng.

Transaction timeout có thể khai báo trên service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookCommandService {

    @Transactional(timeout = 3)
    public BookView publish(String bookId) {
        // Đọc, kiểm tra và cập nhật dữ liệu trong transaction.
        return publishBook(bookId);
    }
}
~~~

Giá trị timeout = 3 được tính bằng giây. Transaction timeout là giới hạn do transaction manager áp dụng cho transaction mới; khả năng truyền xuống JDBC/JPA statement phụ thuộc transaction manager, provider và driver. Không coi annotation này là bảo đảm mọi câu SQL đang chạy sẽ bị dừng chính xác sau 3 giây.

Đặt connection pool acquisition timeout, query timeout và transaction timeout theo chính sách database. Không giữ transaction mở trong lúc chờ gọi HTTP downstream nếu có thể tránh; transaction dài làm giữ connection và khóa lâu hơn.

## Timeout cho SSE

Spring for GraphQL hỗ trợ GraphQL qua Server-Sent Events (SSE). Với SSE, cần phân biệt thời gian tạo response ban đầu và thời gian sống của event stream.

Spring Boot cung cấp:

~~~yaml
spring:
  graphql:
    http:
      sse:
        timeout: 5s
        keep-alive: 15s
~~~

Ý nghĩa:

- spring.graphql.http.sse.timeout giới hạn thời gian handler chờ để tạo response bắt đầu stream SSE.
- spring.graphql.http.sse.keep-alive cấu hình khoảng thời gian gửi heartbeat khi không có event.

SSE timeout không phải giới hạn tổng thời gian subscription được phép tồn tại. Keep-alive cũng không phải timeout; heartbeat chỉ giúp kết nối đang rảnh không bị nhầm là đã chết bởi một số proxy hoặc client.

Ở mức handler, GraphQlSseHandler có constructor nhận timeout và keep-alive duration. Timeout ở đây giới hạn thời gian chờ ứng dụng tạo ServerResponse để bắt đầu stream; sau khi stream đã bắt đầu, nó không tự đặt giới hạn tổng thời gian sống của subscription.

Nếu ứng dụng tự tạo GraphQlSseHandler hoặc dùng functional endpoint, cấu hình trực tiếp:

~~~java
import java.time.Duration;

import org.springframework.graphql.server.WebGraphQlHandler;
import org.springframework.graphql.server.webflux.GraphQlSseHandler;

GraphQlSseHandler sseHandler = new GraphQlSseHandler(
        webGraphQlHandler,
        Duration.ofSeconds(5),
        Duration.ofSeconds(15));
~~~

Đoạn code minh họa constructor của WebFlux handler. Với Spring MVC, dùng class trong package org.springframework.graphql.server.webmvc. Nếu dùng Spring Boot auto-configuration, ưu tiên các thuộc tính spring.graphql.http.sse.*.

## Timeout và quản lý tài nguyên WebSocket

WebSocket connection có thể tồn tại lâu và mang nhiều operation hoặc subscription. Timeout của kết nối khác timeout của từng GraphQL operation.

Spring Boot hỗ trợ:

~~~yaml
spring:
  graphql:
    websocket:
      connection-init-timeout: 10s
      keep-alive: 20s
~~~

- connection-init-timeout là thời gian client phải gửi thông điệp CONNECTION_INIT sau khi WebSocket được thiết lập. Đây là timeout khởi tạo kết nối, không phải thời gian tối đa cho một GraphQL query.
- keep-alive là khoảng thời gian tối đa không hoạt động trước khi server gửi keep-alive ping. Đây là heartbeat, không phải operation timeout.

TimeoutWebGraphQlInterceptor cũng tham gia chuỗi interceptor của các request WebSocket. Với query/mutation trả về một response đơn, nó có thể giới hạn thời gian tạo response. Với subscription, timeout chỉ được áp dụng cho tới khi stream được thiết lập; thời gian phát event sau đó cần chính sách riêng.

WebSocket session có thể chứa nhiều subscription. Ngoài timeout, cần giới hạn số kết nối, kích thước message và số subscription đồng thời trên một session. GraphQlWebSocketHandler có tùy chọn maxSubscriptionsPerSession; mặc định không giới hạn số subscription trên session.

Khi client gửi thông điệp cancel hoặc đóng socket, ứng dụng nên hủy subscription và giải phóng tài nguyên upstream. Với publisher tự quản lý, bảo đảm cleanup được thực hiện trong doFinally, usingWhen hoặc cơ chế tương đương.

## Timeout cho subscription publisher

Với subscription, có thể áp dụng timeout cho từng khoảng chờ event hoặc cho toàn bộ stream tùy nghiệp vụ.

Ví dụ giới hạn khoảng thời gian không có event:

~~~java
import java.time.Duration;

import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class NotificationController {

    private final NotificationService notificationService;

    public NotificationController(
            NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @SubscriptionMapping
    public Flux<NotificationView> notifications() {
        return notificationService.events()
                .timeout(Duration.ofSeconds(60));
    }
}
~~~

Flux.timeout(Duration) phát timeout error nếu không có item trong khoảng thời gian đó. Đây là idle/event-gap timeout; một stream vẫn tiếp tục vô hạn nếu đều đặn phát event trong mỗi 60 giây.

Nếu cần giới hạn tổng thời gian sống của stream, dùng một deadline tuyệt đối hoặc kết hợp take(Duration) theo yêu cầu nghiệp vụ. Không nhầm hai chính sách:

| Chính sách | Hành vi |
| --- | --- |
| Event-gap timeout | Đóng stream nếu quá lâu không có event |
| Absolute lifetime | Đóng stream sau một khoảng thời gian tính từ lúc bắt đầu |
| WebSocket keep-alive | Gửi heartbeat để duy trì/kiểm tra kết nối |
| Client cancellation | Hủy stream khi client không còn quan tâm |

Nếu stream phát event thường xuyên, event-gap timeout không thể thay thế giới hạn lifetime. Ngược lại, absolute lifetime có thể đóng stream dù nguồn event vẫn đang hoạt động.

Reactor Flux.take(Duration) hoàn tất stream sau khoảng thời gian chỉ định; nó không phát TimeoutException như Flux.timeout(Duration). Chọn toán tử theo contract mong muốn: hoàn tất bình thường hay kết thúc bằng lỗi timeout.

## Timeout cho RSocket

TimeoutWebGraphQlInterceptor là WebGraphQlInterceptor nên chỉ áp dụng cho web transports như HTTP và WebSocket. GraphQL over RSocket đi qua RSocketQlInterceptor và RSocket request handling, vì vậy không nhận timeout chỉ bằng cách đăng ký bean TimeoutWebGraphQlInterceptor.

Với RSocket, cấu hình thời gian chờ ở RSocket requester/client hoặc transport tương ứng với interaction model đang dùng. Có thể bổ sung timeout cho Mono/Flux trong resolver khi cần giới hạn một dependency cụ thể. Không dùng các thuộc tính spring.graphql.websocket.* để điều khiển RSocket; đó là cấu hình dành cho WebSocket.

## Xây dựng timeout budget

Một request GraphQL có thể đi qua nhiều dependency. Timeout phải phối hợp theo một ngân sách chung để tránh mỗi tầng tự chờ quá lâu.

Ví dụ ngân sách minh họa cho query thông thường:

| Tầng | Timeout ví dụ | Mục đích |
| --- | --- | --- |
| Connection pool acquisition | 300 ms | Không chờ pool quá lâu |
| HTTP connect | 500 ms | Giới hạn thiết lập kết nối |
| HTTP downstream response | 1.5 s | Giới hạn chờ service khác |
| Database statement | 2 s | Giới hạn câu truy vấn |
| GraphQL request | 4 s | Giới hạn toàn bộ response |
| MVC async request | 5 s | Lớp bảo vệ ngoài GraphQL |
| Gateway/client deadline | 6 s | Chừa thời gian nhận timeout response |

Các giá trị này không phải mặc định của Spring. Chúng chỉ minh họa thứ tự ưu tiên: timeout dependency phải ngắn hơn deadline request; timeout của transport/gateway nên đủ dài để ứng dụng có thể trả kết quả hoặc lỗi.

Khi một request gọi nhiều dependency tuần tự, tổng thời gian chờ có thể cộng dồn. Nếu hai dependency chạy song song, thời gian thực tế phụ thuộc dependency chậm nhất và phần xử lý nối tiếp sau đó. Vì vậy không chỉ cộng các con số timeout; hãy đo luồng thực tế và dành phần ngân sách cho mapping, serialization và network response.

Nên truyền deadline còn lại giữa các tầng nếu ứng dụng có nhiều service nội bộ. Ví dụ, nếu request đã dùng 3 giây trong ngân sách 4 giây, downstream không nên bắt đầu một thao tác mới với timeout 4 giây.

## Timeout không thay thế giới hạn độ phức tạp query

Timeout chỉ giới hạn thời gian chờ. Một GraphQL document rất lớn hoặc query có fan-out cao vẫn có thể tiêu tốn CPU và bộ nhớ trước khi request chạm deadline. Vì vậy, hãy kết hợp timeout với các biện pháp giới hạn chi phí:

- Giới hạn query depth và complexity/cost theo chính sách ứng dụng.
- Bắt buộc pagination và giới hạn kích thước page.
- Dùng DataLoader hoặc batch resolver để tránh N+1.
- Giới hạn số request đồng thời và áp dụng rate limit theo client/user.
- Theo dõi operation name và query pattern gây ra p95/p99 cao.

Timeout là lớp bảo vệ cuối khi request vượt ngân sách; nó không thay thế việc thiết kế query và giới hạn tài nguyên đầu vào.

## Xử lý lỗi timeout

Timeout có thể xuất hiện ở nhiều tầng và cần được phân loại:

| Nguồn timeout | Cách biểu diễn thường gặp | Nơi xử lý |
| --- | --- | --- |
| GraphQL request timeout | HTTP 408 từ TimeoutWebGraphQlInterceptor | Web transport/client |
| Resolver publisher timeout | Timeout exception trong GraphQL execution | DataFetcherExceptionResolver hoặc @GraphQlExceptionHandler |
| WebClient timeout | WebClientRequestException, TimeoutException hoặc lỗi từ connector | Service/client adapter và GraphQL exception resolver |
| Database query timeout | Exception từ JDBC/JPA/provider | Repository/service và exception resolver |
| MVC async timeout | Servlet async request timeout | Spring MVC async handling |
| SSE/WebSocket handshake timeout | Transport đóng hoặc từ chối khởi tạo stream/kết nối | Transport handler/client |

Không nên trả chi tiết nội bộ như hostname, SQL, stack trace hoặc tên database cho GraphQL client. Hãy log nguyên nhân ở server với execution ID/correlation ID, sau đó trả lỗi công khai có mã ổn định và thông điệp phù hợp.

Ví dụ ánh xạ timeout từ resolver thành GraphQL error:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Controller;

import java.util.List;

@Controller
public class GraphQlTimeoutExceptionHandler {

    @GraphQlExceptionHandler
    public List<GraphQLError> handleTimeout(
            java.util.concurrent.TimeoutException exception,
            DataFetchingEnvironment environment) {

        GraphQLError error = GraphqlErrorBuilder.newError(environment)
                .message("Dịch vụ tạm thời phản hồi quá chậm.")
                .errorType(ErrorType.INTERNAL_ERROR)
                .extensions(java.util.Map.of(
                        "code", "DEPENDENCY_TIMEOUT"))
                .build();

        return List.of(error);
    }
}
~~~

TimeoutWebGraphQlInterceptor xử lý request timeout ở tầng transport và trả HTTP status theo cấu hình của interceptor. Exception handler ở trên chỉ dành cho timeout phát sinh bên trong resolver, chẳng hạn Mono.timeout hoặc lỗi timeout từ dependency. Hai trường hợp không đi qua cùng một đường xử lý.

Nếu dùng DataFetcherExceptionResolver, có thể ánh xạ exception theo cùng nguyên tắc thay vì đặt handler trong controller.

## Retry và mutation

Retry không phải cách khắc phục mặc định cho timeout. Nếu retry một thao tác đã chạy lâu, request có thể tiêu thụ thêm tài nguyên và vượt deadline.

Với query đọc dữ liệu, retry có thể phù hợp nếu lỗi tạm thời, thao tác idempotent và vẫn còn ngân sách thời gian. Với mutation, cần đặc biệt cẩn thận:

- Client có thể không biết mutation đã commit hay chưa khi connection timeout.
- Retry cùng mutation có thể tạo bản ghi trùng hoặc thực hiện side effect hai lần.
- Dùng idempotency key hoặc command ID nếu nghiệp vụ cần retry an toàn.
- Không retry khi deadline tổng đã hết.
- Giới hạn số lần retry và thêm backoff có jitter nếu phù hợp.

Timeout ở phía client không chứng minh server chưa thực hiện mutation. Thiết kế mutation nên có cách truy vấn trạng thái hoặc idempotency khi thao tác có side effect quan trọng.

## Kiểm thử timeout

Kiểm thử cần xác minh cả response và cancellation/cleanup. Một request timeout nhưng database query vẫn chạy nhiều phút vẫn là lỗi vận hành.

### Kiểm thử resolver publisher

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ResolverTimeoutTests {

    @Test
    void publisherTimesOut() {
        Mono<String> result = Mono.delay(Duration.ofSeconds(2))
                .map(ignored -> "done")
                .timeout(Duration.ofMillis(100));

        StepVerifier.create(result)
                .expectError(java.util.concurrent.TimeoutException.class)
                .verify();
    }
}
~~~

Test này kiểm tra timeout của Reactor publisher. Nó không thay thế integration test cho TimeoutWebGraphQlInterceptor.

### Kiểm thử GraphQL HTTP request timeout

Với ứng dụng Spring Boot, có thể dùng WebTestClient để gửi request đến endpoint và kiểm tra HTTP 408:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import java.util.Map;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GraphQlRequestTimeoutTests {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void slowQueryReturnsRequestTimeout() {
        webTestClient.post()
                .uri("/graphql")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("query", "{ slow }"))
                .exchange()
                .expectStatus()
                .isRequestTimeout();
    }
}
~~~

Test giả định ứng dụng có field query slow trả về một publisher mất nhiều thời gian hơn timeout được cấu hình. Nếu dùng Spring MVC, có thể dùng MockMvc hoặc HTTP client test tương ứng; điều quan trọng là request phải đi qua web interceptor chain.

Trong test Spring MVC, nếu muốn inject WebTestClient, cần bật cấu hình WebTestClient test support phù hợp với phiên bản Spring Boot đang dùng; nếu không, dùng MockMvc hoặc tạo WebTestClient từ server đang chạy.

### Các tình huống nên kiểm thử

- Query hoàn tất trước deadline vẫn trả kết quả thành công.
- Query vượt deadline trả HTTP 408 theo cấu hình.
- Resolver publisher nhận cancellation khi request bị timeout.
- WebClient connect timeout và response timeout được phân biệt.
- Database query timeout giải phóng hoặc trả connection theo đúng driver/provider.
- MVC async timeout không xảy ra trước GraphQL timeout.
- SSE response-start timeout không bị hiểu nhầm là subscription lifetime.
- WebSocket connection-init timeout chỉ áp dụng cho giai đoạn khởi tạo.
- Subscription event-gap timeout và absolute lifetime có hành vi khác nhau.
- Client cancellation đóng subscription và giải phóng upstream resource.
- Mutation timeout không gây side effect trùng khi client retry.

## Quan sát và vận hành

Để phát hiện timeout trước khi người dùng báo lỗi, nên theo dõi:

- Số request timeout theo operation name và transport.
- Thời gian thực thi GraphQL p50, p95, p99.
- Số timeout theo dependency: database, HTTP client, message broker.
- Số connection đang chờ trong pool và thời gian lấy connection.
- Số subscription đang mở, tuổi stream và số lần client cancel.
- Số timeout xảy ra trước và sau khi GraphQL response stream được thiết lập.
- Số lần retry và tỷ lệ retry thành công.

Ghi log timeout cùng execution ID/correlation ID, operation name, dependency và thời gian đã dùng. Không log toàn bộ variables nếu chúng chứa token, dữ liệu cá nhân hoặc thông tin nhạy cảm.

Đặt cảnh báo khi tỷ lệ timeout hoặc p99 tăng bất thường. Tăng timeout chỉ làm request chờ lâu hơn; nếu nguyên nhân là pool cạn, query không có index hoặc dependency quá tải, cần xử lý nguyên nhân gốc.

## Lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| GraphQL request chờ quá lâu | Chưa đăng ký TimeoutWebGraphQlInterceptor | Thêm interceptor bean |
| spring.mvc.async.request-timeout không tác dụng trên WebFlux | Đây là thuộc tính của Servlet MVC | Dùng GraphQL interceptor và timeout cho reactive dependency |
| MVC timeout xảy ra trước GraphQL timeout | MVC async timeout đặt ngắn hơn | Đặt MVC timeout dài hơn GraphQL request timeout |
| HTTP response timeout nhưng SQL vẫn chạy | JDBC/JPA call blocking không dừng theo cancel signal | Cấu hình statement/query timeout ở database layer |
| WebClient timeout nhưng GraphQL request vẫn mở | Chưa có timeout toàn request | Kết hợp WebClient timeout với GraphQL request timeout |
| Subscription tự đóng sau vài giây | Nhầm request timeout với stream lifetime | Hiểu giới hạn timeout đến lúc stream được thiết lập và cấu hình publisher riêng |
| SSE không bắt đầu được | Handler chờ response khởi tạo quá lâu | Kiểm tra spring.graphql.http.sse.timeout |
| SSE bị proxy đóng khi im lặng | Thiếu heartbeat hoặc keep-alive quá dài | Cấu hình spring.graphql.http.sse.keep-alive và proxy idle timeout |
| WebSocket bị đóng trước khi gửi operation | Client không gửi CONNECTION_INIT đúng hạn | Kiểm tra spring.graphql.websocket.connection-init-timeout |
| WebSocket vẫn giữ quá nhiều subscription | Chưa giới hạn subscription/session | Cấu hình maxSubscriptionsPerSession và quản lý cancellation |
| Retry mutation tạo dữ liệu trùng | Client retry sau timeout mà không có idempotency | Dùng idempotency key/command ID |
| Tăng timeout nhưng hệ thống vẫn chậm | Timeout che khuất query hoặc dependency chậm | Đo p95/p99, pool, query plan và downstream latency |

## Quy trình cấu hình timeout

Khi triển khai timeout cho một ứng dụng Spring for GraphQL:

1. **Đo thời gian thực tế.** Lấy p95/p99 của query, mutation và dependency quan trọng.
2. **Đặt request deadline.** Đăng ký TimeoutWebGraphQlInterceptor cho web transports.
3. **Đặt timeout transport phù hợp.** Với MVC, xem xét async timeout; với WebFlux, xem xét server/proxy timeout; với SSE/WebSocket, cấu hình handler properties tương ứng.
4. **Đặt timeout downstream.** Giới hạn connect/response của WebClient và query/statement/transaction của database.
5. **Để lại ngân sách xử lý response.** Dependency timeout phải ngắn hơn GraphQL request deadline.
6. **Xử lý cancellation.** Dùng reactive pipeline khi phù hợp và bảo đảm blocking work có timeout riêng.
7. **Quản lý subscription.** Phân biệt event-gap, absolute lifetime, keep-alive và client cancellation.
8. **Chuẩn hóa lỗi.** Phân biệt HTTP request timeout với GraphQL execution error từ resolver.
9. **Kiểm thử tích hợp.** Xác minh status, cancellation, cleanup và idempotency.
10. **Theo dõi sau triển khai.** Quan sát p95/p99, pool usage và timeout rate để điều chỉnh budget.

Cấu hình timeout hiệu quả cần một deadline cho toàn GraphQL request và các timeout nhỏ hơn cho dependency. TimeoutWebGraphQlInterceptor giới hạn thời gian tạo response cho web transports, trong khi MVC async, SSE, WebSocket, WebClient và database có các timeout riêng. Tín hiệu cancel giúp reactive work dừng, nhưng không bảo đảm một tác vụ blocking hoặc câu SQL đang chạy tự kết thúc. Với subscription, timeout request chỉ bảo vệ giai đoạn thiết lập stream; event-gap, lifetime và keep-alive phải được quản lý riêng. Hãy đo độ trễ thực tế, phối hợp timeout theo ngân sách, kiểm thử cancellation và theo dõi timeout rate sau triển khai.

## Tài liệu tham khảo

- [Spring for GraphQL - Request Execution and GraphQL Request Timeout](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL - Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL - TimeoutWebGraphQlInterceptor API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/server/TimeoutWebGraphQlInterceptor.html)
- [Spring Boot - Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties/)
- [Spring Framework - Asynchronous Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
- [Spring Framework - WebClient Timeouts](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html)
- [Reactor Netty - HTTP Client Timeout](https://projectreactor.io/docs/netty/release/reference/http-client.html#http-client-timeout)
