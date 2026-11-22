# WebSocketGraphQlClient trong Spring for GraphQL

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của `WebSocketGraphQlClient` trong ứng dụng Spring for GraphQL.
- Phân biệt WebSocket client với `HttpGraphQlClient` và `RSocketGraphQlClient`.
- Tạo client bằng `WebSocketGraphQlClient.builder(...)` và một `WebSocketClient`.
- Dùng API fluent chung của `GraphQlClient` để gửi operation.
- Nhận subscription stream bằng `retrieveSubscription(...).toFlux(...)`.
- Hiểu cách một WebSocket connection phục vụ nhiều operation.
- Phân biệt handshake HTTP với thông điệp khởi tạo GraphQL WebSocket connection.
- Truyền authentication metadata và bảo vệ kết nối.
- Quản lý cancellation, reconnect và lỗi transport.
- Kiểm thử stream bằng Reactor `StepVerifier`.

## 1. WebSocketGraphQlClient là gì?

`WebSocketGraphQlClient` là GraphQL client dùng WebSocket transport. Client gửi GraphQL operation qua một kết nối WebSocket và nhận response trên chính kết nối đó.

WebSocket phù hợp với subscription vì kết nối có thể tồn tại lâu và server có thể gửi nhiều response theo thời gian. Client không cần mở một HTTP request mới cho mỗi event.

Ví dụ, một ứng dụng quản trị muốn theo dõi trạng thái đơn hàng:

~~~graphql
subscription WatchOrder($orderId: ID!) {
    orderStatusChanged(orderId: $orderId) {
        orderId
        status
        changedAt
    }
}
~~~

Sau khi đăng ký, server có thể gửi nhiều payload `orderStatusChanged` trong cùng subscription operation. Client chuyển các payload thành một reactive stream để cập nhật giao diện hoặc xử lý nghiệp vụ.

`WebSocketGraphQlClient` triển khai abstraction `GraphQlClient`, do đó cách xây dựng document, truyền variables, lấy field và chuyển đổi response gần giống các GraphQL client khác của Spring.

## 2. Khi nào dùng WebSocketGraphQlClient?

Spring for GraphQL có các client transport khác nhau. Chọn transport theo kiểu tương tác:

| Client | Transport | Trường hợp phù hợp |
| --- | --- | --- |
| `HttpGraphQlClient` | HTTP request/response | Query và Mutation thông thường |
| `WebSocketGraphQlClient` | WebSocket | Subscription và các tương tác cần kết nối lâu dài |
| `RSocketGraphQlClient` | RSocket | Hệ thống đã dùng RSocket và cần các interaction model của RSocket |

Với màn hình chỉ tải thông tin sách rồi hiển thị, HTTP thường đơn giản hơn. Với màn hình cần nhận trạng thái đơn hàng thay đổi liên tục, WebSocket là lựa chọn phù hợp.

Một ứng dụng có thể dùng nhiều client cùng lúc: HTTP cho Query/Mutation và WebSocket cho Subscription. Không cần chuyển toàn bộ request sang WebSocket chỉ vì hệ thống có một subscription.

## 3. Tạo WebSocketGraphQlClient

`WebSocketGraphQlClient` cần một URI WebSocket và một implementation của Spring `WebSocketClient`.

Ví dụ dùng Reactor Netty:

~~~java
import java.net.URI;

import org.springframework.graphql.client.WebSocketGraphQlClient;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

WebSocketGraphQlClient graphQlClient =
        WebSocketGraphQlClient.builder(
                URI.create("ws://localhost:8080/graphql"),
                new ReactorNettyWebSocketClient()
        ).build();
~~~

Các thành phần:

- `ws://` là WebSocket không mã hóa, thường chỉ dùng trong môi trường phát triển cục bộ.
- `wss://` là WebSocket qua TLS, nên dùng cho môi trường production.
- URI phải trỏ tới WebSocket endpoint mà server đã cấu hình.
- `ReactorNettyWebSocketClient` là một implementation WebSocket client dựa trên Reactor Netty.

Nếu ứng dụng dùng một implementation WebSocket khác, có thể truyền implementation đó vào builder miễn là nó đáp ứng interface `WebSocketClient`.

Không nhầm URI WebSocket với HTTP URL. Một số server dùng cùng path `/graphql` cho HTTP và WebSocket, nhưng scheme khác nhau: `http/https` cho HTTP và `ws/wss` cho WebSocket.

## 4. Cấu hình client dùng chung

Nên tạo client một lần và chia sẻ trong ứng dụng thay vì tạo một WebSocket client mới cho từng lần gọi subscription.

Có thể đăng ký client thành Spring bean:

~~~java
import java.net.URI;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.client.WebSocketGraphQlClient;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

@Configuration
class GraphQlClientConfiguration {

    @Bean
    WebSocketGraphQlClient webSocketGraphQlClient() {
        return WebSocketGraphQlClient.builder(
                URI.create("wss://api.example.com/graphql"),
                new ReactorNettyWebSocketClient()
        ).build();
    }
}
~~~

Sau đó inject client vào component cần nhận event:

~~~java
@Service
class OrderUpdatesClient {

    private final WebSocketGraphQlClient graphQlClient;

    OrderUpdatesClient(WebSocketGraphQlClient graphQlClient) {
        this.graphQlClient = graphQlClient;
    }
}
~~~

Một client được chia sẻ giúp quản lý connection và nhiều operation nhất quán. Tránh tạo một client mới trong mỗi lần người dùng mở màn hình nếu không có lý do về isolation hoặc cấu hình kết nối riêng.

Vòng đời client cần gắn với vòng đời ứng dụng. Khi ứng dụng dừng, cần để client và WebSocket transport được đóng theo lifecycle mà phiên bản Spring GraphQL đang dùng cung cấp. Không để connection tồn tại ngoài vòng đời component sở hữu nó.

## 5. API fluent chung của GraphQlClient

`WebSocketGraphQlClient` dùng API request của `GraphQlClient`. Một request thường được tạo bằng `document(...)`, sau đó thêm variables hoặc operation name.

Ví dụ Query:

~~~java
import reactor.core.publisher.Mono;

Mono<Book> book = graphQlClient.document("""
        query FindBook($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
        .variable("id", "book-42")
        .retrieve("book")
        .toEntity(Book.class);
~~~

Ví dụ Mutation:

~~~java
Mono<Book> updatedBook = graphQlClient.document("""
        mutation RenameBook($id: ID!, $title: String!) {
            renameBook(id: $id, title: $title) {
                id
                title
            }
        }
        """)
        .variable("id", "book-42")
        .variable("title", "Spring GraphQL")
        .retrieve("renameBook")
        .toEntity(Book.class);
~~~

Các bước có ý nghĩa:

1. `document(...)` cung cấp GraphQL document.
2. `variable(...)` gán giá trị cho variable trong document.
3. `retrieve("book")` chọn field trong response cần lấy.
4. `toEntity(Book.class)` chuyển field value thành Java object.
5. Kết quả là `Mono<Book>` vì một Query/Mutation thông thường tạo một response.

API fluent này giúp chuyển đổi giữa HTTP và WebSocket transport dễ dàng hơn. Dù vậy, với Query/Mutation thông thường, HTTP thường là lựa chọn đơn giản và phù hợp hơn.

## 6. Gửi subscription và nhận Flux

Điểm khác biệt chính của WebSocket client là API nhận subscription stream.

SDL ví dụ:

~~~graphql
type OrderStatusChanged {
    orderId: ID!
    status: String!
    changedAt: String!
}

type Subscription {
    orderStatusChanged(orderId: ID!): OrderStatusChanged!
}
~~~

Java payload:

~~~java
import reactor.core.publisher.Flux;

public record OrderStatusChanged(
        String orderId,
        String status,
        String changedAt) {
}
~~~

Client tạo subscription:

~~~java
Flux<OrderStatusChanged> updates =
        graphQlClient.document("""
                subscription WatchOrder($orderId: ID!) {
                    orderStatusChanged(orderId: $orderId) {
                        orderId
                        status
                        changedAt
                    }
                }
                """)
                .variable("orderId", "order-42")
                .retrieveSubscription("orderStatusChanged")
                .toFlux(OrderStatusChanged.class);
~~~

`retrieveSubscription("orderStatusChanged")` chọn root subscription field. `toFlux(OrderStatusChanged.class)` chuyển mỗi payload của field thành một phần tử trong `Flux`.

Khác với `retrieve(...).toEntity(...)`, subscription không được chuyển thành một `Mono` duy nhất nếu client cần nhận nhiều event. `Flux` đại diện cho chuỗi kết quả theo thời gian.

## 7. Xử lý từng event từ subscription stream

Client có thể đăng ký xử lý event bằng Reactor:

~~~java
import reactor.core.Disposable;

Disposable subscription = updates.subscribe(
        event -> log.info(
                "Order status changed orderId={} status={}",
                event.orderId(),
                event.status()
        ),
        error -> log.error(
                "Order update stream failed",
                error
        ),
        () -> log.info("Order update stream completed")
);
~~~

Ba callback xử lý:

- `onNext`: nhận một event.
- `onError`: stream kết thúc do lỗi.
- `onComplete`: stream kết thúc bình thường.

Một stream subscription thường được giữ hoạt động trong khi người dùng đang theo dõi dữ liệu. Không giả định stream luôn hoàn tất sau event đầu tiên.

Nếu ứng dụng cần cập nhật state, hãy chuyển event thành một action hoặc cập nhật state store theo mô hình của ứng dụng. Tránh thực hiện công việc blocking lâu trong callback `onNext`, vì nó có thể làm chậm quá trình xử lý event.

## 8. Nhiều subscription trên một connection

WebSocket transport cho phép nhiều operation hoạt động đồng thời trên cùng connection. `WebSocketGraphQlClient` quản lý việc gửi operation và liên kết response với operation tương ứng.

Ví dụ một màn hình theo dõi hai đơn hàng:

~~~java
Flux<OrderStatusChanged> firstOrder =
        graphQlClient.document("""
                subscription {
                    orderStatusChanged(orderId: "order-42") {
                        orderId
                        status
                        changedAt
                    }
                }
                """)
                .retrieveSubscription("orderStatusChanged")
                .toFlux(OrderStatusChanged.class);

Flux<OrderStatusChanged> secondOrder =
        graphQlClient.document("""
                subscription {
                    orderStatusChanged(orderId: "order-99") {
                        orderId
                        status
                        changedAt
                    }
                }
                """)
                .retrieveSubscription("orderStatusChanged")
                .toFlux(OrderStatusChanged.class);
~~~

Hai stream có thể được subscribe độc lập:

~~~java
Disposable first = firstOrder.subscribe(this::handleOrderUpdate);
Disposable second = secondOrder.subscribe(this::handleOrderUpdate);
~~~

Mỗi operation có lifecycle riêng. Hủy `first` không nên làm hủy `second` nếu cả hai đang dùng chung client connection.

Việc multiplex giúp tránh mở một WebSocket connection cho mỗi subscription. Tuy nhiên, cần giới hạn số operation đồng thời và số subscription theo người dùng để tránh chiếm tài nguyên server.

## 9. WebSocket handshake và GraphQL connection initialization

WebSocket bắt đầu bằng HTTP upgrade handshake. Sau khi kết nối được nâng cấp, GraphQL WebSocket protocol có bước khởi tạo connection ở tầng ứng dụng.

Hai giai đoạn này khác nhau:

1. **Handshake:** browser/client và server thương lượng chuyển HTTP connection thành WebSocket. HTTP headers có thể được dùng cho authentication ở giai đoạn này.
2. **Connection initialization:** client gửi thông điệp khởi tạo theo GraphQL WebSocket protocol; payload có thể mang metadata xác thực hoặc context theo thỏa thuận giữa client và server.

Với GraphQL over WebSocket protocol phổ biến `graphql-transport-ws`, lifecycle gồm các message như `connection_init`, `connection_ack`, `subscribe`, `next`, `error` và `complete`.

Không nhầm header của HTTP handshake với payload `connection_init`. Server có thể kiểm tra chúng ở những điểm khác nhau. Cần thống nhất cơ chế xác thực giữa client và server.

## 10. Truyền authentication metadata

Một số hệ thống xác thực WebSocket bằng header trong handshake, ví dụ Bearer token. Có thể cấu hình header trên WebSocket transport hoặc builder theo API của implementation đang dùng.

Ví dụ minh họa cấu hình header:

~~~java
WebSocketGraphQlClient graphQlClient =
        WebSocketGraphQlClient.builder(
                URI.create("wss://api.example.com/graphql"),
                new ReactorNettyWebSocketClient()
        )
        .headers(headers -> headers.setBearerAuth(accessToken))
        .build();
~~~

Cấu hình header handshake chỉ phù hợp khi server xác thực ở giai đoạn HTTP upgrade. Nếu server yêu cầu token trong `connection_init` payload, client phải cấu hình payload theo API/protocol hỗ trợ của phiên bản đang dùng.

Các lưu ý:

- Không đặt token trong query string.
- Không log header `Authorization`.
- Dùng `wss://` để mã hóa dữ liệu trên mạng.
- Token hết hạn trong khi connection vẫn mở cần có chính sách refresh hoặc reconnect.
- Không giả định thay token trong một biến Java sẽ tự cập nhật connection đã mở.
- Server vẫn phải kiểm tra quyền cho từng operation và từng tài nguyên.

Đặc biệt với WebSocket connection tồn tại lâu, cần quyết định token được xác thực một lần khi handshake, khi connection initialization hay được kiểm tra lại trong quá trình hoạt động.

## 11. Client interceptor và metadata chung

Spring GraphQL client hỗ trợ interceptor để áp dụng logic chung cho các request, ví dụ:

- Ghi log operation name.
- Gắn correlation metadata.
- Chuẩn hóa xử lý lỗi.
- Đo thời gian request.
- Bổ sung header hoặc metadata theo cơ chế transport được hỗ trợ.

Có thể cấu hình interceptor trên builder của GraphQL client. Interceptor request/response ở GraphQL layer khác với cấu hình header của WebSocket handshake.

Không đưa access token, variables nhạy cảm hoặc toàn bộ GraphQL document vào log. Với subscription, cần phân biệt log lúc bắt đầu operation, từng event, lỗi stream và lúc operation kết thúc; một stream dài không nên tạo log payload quá lớn.

Nếu correlation ID cần đi cùng mọi event, hãy thống nhất nơi tạo và truyền metadata với server. Không dùng một giá trị mutable toàn cục để gán request ID cho nhiều subscription đồng thời.

## 12. Cancellation và đóng subscription

Khi người dùng rời màn hình hoặc không còn cần dữ liệu cập nhật, client cần hủy subscription.

Ví dụ:

~~~java
Disposable subscription = updates.subscribe(this::handleOrderUpdate);

// Khi không còn theo dõi đơn hàng:
subscription.dispose();
~~~

`dispose()` hủy subscription phía client. Với WebSocket GraphQL protocol, client gửi thông điệp kết thúc operation tương ứng và server có thể hủy publisher liên quan.

Hủy một operation không đồng nghĩa đóng toàn bộ WebSocket connection. Những operation khác trên cùng client có thể tiếp tục hoạt động.

Khi component UI bị dispose hoặc service ngừng hoạt động, lưu handle `Disposable` để hủy đúng lúc. Nếu tạo subscription mà không giữ handle, ứng dụng có thể tiếp tục nhận event sau khi màn hình đã đóng.

## 13. Reconnect và xử lý mất kết nối

WebSocket là kết nối lâu dài, vì vậy có thể gặp:

- Mạng client bị ngắt.
- Server restart hoặc deploy.
- Reverse proxy đóng kết nối idle.
- Token hết hạn.
- Keep-alive timeout.
- Connection bị từ chối hoặc đóng do giới hạn tài nguyên.

Khi connection mất, các subscription đang hoạt động có thể bị lỗi hoặc kết thúc. Ứng dụng cần quyết định có đăng ký lại hay không.

Một chiến lược reconnect nên xác định:

1. Điều kiện lỗi nào có thể retry.
2. Khoảng chờ giữa các lần thử, có exponential backoff và jitter.
3. Giới hạn số lần retry hoặc thời gian retry.
4. Cách refresh credential trước khi mở connection mới.
5. Cách tạo lại các subscription còn cần thiết.
6. Cách tránh xử lý trùng event sau reconnect.

Reconnect không đảm bảo nhận lại event đã phát trong thời gian mất kết nối. Nếu cần không bỏ lỡ sự kiện, payload nên có event ID hoặc sequence number và server cần hỗ trợ replay/resume từ một vị trí đã biết. WebSocket connection tự nó không phải message broker có lưu trữ bền vững.

## 14. Xử lý GraphQL error và transport error

Cần phân biệt lỗi GraphQL với lỗi kết nối:

| Loại lỗi | Ví dụ | Cách xử lý |
| --- | --- | --- |
| GraphQL error trong response | Người dùng không có quyền xem field | Đọc error details/code và xử lý theo API contract |
| Subscription operation error | Server từ chối hoặc kết thúc một operation | Hiển thị trạng thái lỗi cho subscription đó |
| Transport error | WebSocket disconnect, handshake thất bại | Retry/reconnect theo chính sách |
| Deserialization error | Payload không chuyển được thành DTO | Kiểm tra schema và kiểu Java |
| Application callback error | Consumer xử lý event ném exception | Cô lập lỗi consumer và theo dõi stream |

Khi dùng `retrieveSubscription`, nếu cần truy cập đầy đủ response và errors thay vì chỉ lấy một field, có thể dùng API thực thi subscription phù hợp của phiên bản Spring GraphQL. Đừng bỏ qua GraphQL errors chỉ vì WebSocket connection vẫn mở.

Không tự động retry mọi lỗi. Lỗi authorization hoặc validation thường không được giải quyết bằng cách kết nối lại liên tục. Chỉ retry các lỗi tạm thời và có giới hạn.

## 15. Backpressure và xử lý event chậm

Client có thể nhận event nhanh hơn tốc độ xử lý. Khi đó cần quyết định cách điều tiết:

- Xử lý nhanh trong callback và chuyển công việc nặng sang scheduler phù hợp.
- Dùng buffer có giới hạn nếu cần giữ một lượng event ngắn hạn.
- Dùng `onBackpressureBuffer` với giới hạn và chiến lược overflow rõ ràng khi phù hợp.
- Dùng `sample` hoặc `latest` nếu chỉ cần trạng thái mới nhất và nghiệp vụ cho phép bỏ event trung gian.
- Ngắt subscription nếu consumer không thể theo kịp trong giới hạn tài nguyên.

Ví dụ:

~~~java
updates
        .onBackpressureBuffer(
                100,
                dropped -> log.warn(
                        "Order event buffer overflow orderId={}",
                        dropped.orderId()
                )
        )
        .subscribe(this::handleOrderUpdate);
~~~

Buffer ở client chỉ xử lý áp lực trong pipeline client. Nó không tạo đảm bảo delivery bền vững và không thể khôi phục event mà server đã bỏ hoặc connection đã mất.

Nếu mọi event đều quan trọng, cần event ID, replay và nguồn dữ liệu có retention thay vì chỉ tăng kích thước buffer.

## 16. Lifecycle và tài nguyên của WebSocketGraphQlClient

Client WebSocket thường được dùng chung trong suốt vòng đời ứng dụng. Hãy quản lý các tài nguyên theo đúng phạm vi:

- **Client instance:** thường được tạo một lần và inject như Spring bean.
- **Connection:** được quản lý bởi client/transport theo lifecycle của nó.
- **Subscription operation:** mỗi operation có thể được hủy độc lập.
- **Event consumer:** cần được dừng khi component không còn sử dụng stream.

Không tạo client mới cho mỗi event hoặc mỗi lần gọi method. Cũng không đóng shared connection chỉ vì một màn hình hủy subscription của nó.

Khi ứng dụng shutdown, dừng các subscription do ứng dụng quản lý và cho client lifecycle hoàn tất để connection/transport được giải phóng. Nếu tạo client thủ công ngoài Spring context, cần tự quản lý lifecycle theo API của phiên bản thư viện.

## 17. Kiểm thử WebSocketGraphQlClient

Có thể kiểm thử luồng nhận event bằng Reactor `StepVerifier`.

Ví dụ với một publisher test được điều khiển:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import reactor.test.StepVerifier;

Flux<OrderStatusChanged> updates = graphQlClient.document("""
        subscription WatchOrder($orderId: ID!) {
            orderStatusChanged(orderId: $orderId) {
                orderId
                status
                changedAt
            }
        }
        """)
        .variable("orderId", "order-42")
        .retrieveSubscription("orderStatusChanged")
        .toFlux(OrderStatusChanged.class);

StepVerifier.create(updates)
        .assertNext(event -> {
            assertThat(event.orderId()).isEqualTo("order-42");
            assertThat(event.status()).isEqualTo("SHIPPED");
        })
        .thenCancel()
        .verify();
~~~

Đây là dạng kiểm thử cần một WebSocket GraphQL server test đang phát event tương ứng. Test cần đảm bảo server endpoint, subprotocol và client cùng tương thích.

Nên kiểm tra:

- Client kết nối được tới đúng `ws://` hoặc `wss://` endpoint.
- Subscription gửi đúng document và variables.
- Client nhận nhiều event theo đúng thứ tự mà server đảm bảo.
- Hai subscription trên cùng client nhận đúng event riêng.
- `dispose()` hủy đúng operation.
- Một operation bị hủy không làm dừng operation khác.
- Handshake hoặc connection initialization bị từ chối khi credential không hợp lệ.
- Connection loss kích hoạt đúng chính sách retry.
- GraphQL errors được phân biệt với transport errors.
- Consumer không tiếp tục chạy sau khi component đã dừng.

Với test cần kiểm soát publisher mà không mở socket, có thể kiểm thử riêng phần xử lý `Flux` của ứng dụng. Tuy nhiên, cần ít nhất một integration test qua WebSocket transport để xác minh kết nối, protocol và subscription lifecycle.

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không kết nối được | Dùng HTTP URI thay cho WebSocket URI hoặc sai path | Kiểm tra `ws://`/`wss://` và endpoint |
| Handshake bị từ chối | Header authentication thiếu hoặc không hợp lệ | Kiểm tra cơ chế auth của handshake |
| Server không nhận subscription | Client và server không thống nhất WebSocket subprotocol | Dùng protocol GraphQL WebSocket mà cả hai hỗ trợ |
| Subscription chỉ phát một event | Server publisher hoàn tất sau event đầu tiên | Kiểm tra event source phía server |
| Không thấy event cũ | Event source không hỗ trợ replay | Dùng snapshot Query hoặc broker có retention |
| Một subscription hủy làm mất stream khác | Đóng shared client connection thay vì dispose đúng operation | Hủy `Disposable` của operation |
| Connection mất nhưng không đăng ký lại | Chưa thiết kế reconnect và resubscribe | Thêm retry có backoff và khôi phục operation |
| Token hết hạn khi connection đang mở | Chỉ xác thực ở thời điểm handshake | Refresh credential và reconnect theo chính sách |
| Client xử lý event bị chậm | Callback blocking hoặc buffer không giới hạn | Tối ưu consumer và đặt giới hạn backpressure |
| Event bị xử lý trùng sau reconnect | Không có event ID hoặc idempotency | Dùng sequence/event ID và xử lý idempotent |
| Nhiều connection được tạo không cần thiết | Tạo client trong mỗi lần gọi | Chia sẻ client bean và quản lý operation riêng |

## 19. Quy trình tích hợp WebSocketGraphQlClient

Khi tích hợp WebSocket GraphQL client, hãy thực hiện theo trình tự:

1. **Xác nhận server endpoint.** Kiểm tra WebSocket path và subprotocol server hỗ trợ.
2. **Chọn transport client.** Cung cấp một `WebSocketClient` implementation phù hợp.
3. **Tạo client dùng chung.** Dùng `WebSocketGraphQlClient.builder(...)` và quản lý lifecycle.
4. **Thiết kế GraphQL document.** Đặt tên operation và khai báo variables.
5. **Tạo stream.** Dùng `retrieveSubscription(...).toFlux(...)` cho subscription.
6. **Xử lý event.** Giữ callback không blocking và phân biệt `onNext`, `onError`, `onComplete`.
7. **Bảo vệ kết nối.** Dùng TLS và cơ chế authentication phù hợp với handshake/connection initialization.
8. **Quản lý operation.** Lưu `Disposable` và hủy khi không còn nhu cầu.
9. **Thiết kế phục hồi.** Quy định reconnect, backoff, resubscribe và replay.
10. **Kiểm thử.** Dùng `StepVerifier` cùng integration test qua WebSocket endpoint.

## 20. Tổng kết

`WebSocketGraphQlClient` là GraphQL client của Spring for GraphQL dành cho WebSocket transport. Client được tạo bằng builder với URI WebSocket và một `WebSocketClient` implementation. Nó dùng API fluent chung của `GraphQlClient` để tạo document, truyền variables và đọc response; với subscription, `retrieveSubscription(...).toFlux(...)` chuyển các event thành reactive stream.

WebSocket phù hợp với luồng cập nhật lâu dài và có thể multiplex nhiều operation trên connection. Hãy quản lý client ở cấp ứng dụng, hủy từng subscription bằng `Disposable`, phân biệt handshake với connection initialization, bảo vệ authentication metadata và xây dựng chính sách reconnect có giới hạn. Khi mất kết nối, event có thể bị bỏ lỡ nếu server không hỗ trợ replay. Kết hợp `StepVerifier` với integration test qua WebSocket giúp xác minh cả việc nhận event lẫn lifecycle, cancellation và lỗi transport.

