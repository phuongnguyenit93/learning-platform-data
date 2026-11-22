# Bảo vệ subscription connection

GraphQL subscription thường giữ một kết nối trong thời gian dài để server liên tục gửi sự kiện cho client. Với WebSocket, nhiều subscription và cả query/mutation có thể dùng chung một connection. Vì vậy, bảo mật cần quản lý cả danh tính của connection, quyền trên từng operation và quyền nhận event trong suốt vòng đời stream.

Spring for GraphQL hỗ trợ xác thực tại thông điệp **connection_init** của giao thức GraphQL over WebSocket. Interceptor xác thực tích hợp có thể lấy bearer token từ payload, xác thực token và truyền **SecurityContext** sang các GraphQL operation tiếp theo trên cùng WebSocket session. Bài này tập trung vào cách bảo vệ connection, giới hạn quyền của subscription đang chạy và xử lý token hết hạn hoặc người dùng bị thu hồi quyền.

## 1. Vì sao subscription cần bảo vệ theo connection?

Một query HTTP thường kết thúc sau khi server trả response. WebSocket connection có vòng đời dài hơn: client mở kết nối, gửi thông điệp khởi tạo, sau đó có thể bắt đầu nhiều subscription. Mỗi subscription tiếp tục phát event cho đến khi client hủy, publisher hoàn tất, xảy ra lỗi hoặc connection đóng.

Ví dụ schema theo dõi trạng thái đơn hàng:

~~~graphql
type Query {
    order(id: ID!): Order
}

type Subscription {
    orderUpdates(orderId: ID!): OrderUpdate!
}

type Order {
    id: ID!
    status: String!
}

type OrderUpdate {
    orderId: ID!
    status: String!
    changedAt: String!
}
~~~

Một client có thể mở subscription cho đơn hàng order-42 và giữ connection trong nhiều phút. Nếu server chỉ xác thực khi mở HTTP handshake nhưng không gắn danh tính với các operation GraphQL sau đó, resolver có thể không biết ai đang yêu cầu dữ liệu. Nếu connection đã xác thực một lần nhưng quyền người dùng thay đổi trong lúc stream chạy, những event tiếp theo vẫn có nguy cơ được gửi tới người không còn quyền xem.

Cần phân biệt ba lớp:

- **Connection authentication:** xác định danh tính client khi thiết lập hoặc khởi tạo WebSocket session.
- **Operation authorization:** kiểm tra người dùng có quyền bắt đầu subscription hoặc gọi field cụ thể hay không.
- **Event authorization:** kiểm tra dữ liệu của từng event có còn được phép gửi tới subscriber trong suốt thời gian stream hay không, nếu nghiệp vụ yêu cầu thu hồi quyền tức thời.

## 2. Hai giai đoạn của GraphQL over WebSocket

GraphQL over WebSocket dùng giao thức graphql-ws với các thông điệp quản lý connection và operation. Spring for GraphQL hỗ trợ giao thức này thông qua GraphQlWebSocketHandler.

Vòng đời cơ bản:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant H as HTTP/WebSocket handshake
    participant S as Spring GraphQL
    participant A as Authentication
    participant R as Resolver/Publisher

    C->>H: HTTP Upgrade request
    H-->>C: 101 Switching Protocols
    C->>S: connection_init + payload
    S->>A: Extract and authenticate credentials
    A-->>S: Authenticated SecurityContext
    S-->>C: connection_ack
    C->>S: subscribe + GraphQL operation
    S->>R: Execute subscription resolver
    R-->>C: Event 1, Event 2, ...
    C->>S: complete / unsubscribe
    S->>R: Cancel publisher
    C->>H: Close WebSocket
~~~

Có hai thời điểm khác nhau:

1. **HTTP handshake:** trình duyệt yêu cầu nâng cấp HTTP thành WebSocket. Server có thể kiểm tra Origin, cookie session hoặc credential được gửi ở handshake.
2. **GraphQL connection initialization:** sau khi WebSocket mở, client gửi connection_init. Payload của thông điệp này có thể chứa bearer token. Server xác thực payload trước khi chấp nhận các GraphQL operation trên connection.

Nếu dùng bearer token trong connection_init, HTTP handshake có thể chưa mang danh tính người dùng. Vì vậy, phải cấu hình interceptor xác thực connection và không cho phép operation chạy trước khi khởi tạo được chấp nhận.

## 3. Bật WebSocket endpoint trong Spring Boot

Spring Boot không tự bật GraphQL WebSocket endpoint trong mọi cấu hình. Có thể khai báo path riêng bằng spring.graphql.websocket.path:

~~~yaml
spring:
  graphql:
    websocket:
      path: /graphql-ws
      connection-init-timeout: 10s
      keep-alive: 30s
~~~

Ý nghĩa:

| Thuộc tính | Mục đích |
| --- | --- |
| spring.graphql.websocket.path | Bật endpoint GraphQL WebSocket tại path được chỉ định |
| spring.graphql.websocket.connection-init-timeout | Thời gian tối đa chờ thông điệp connection_init đầu tiên; mặc định là 60s |
| spring.graphql.websocket.keep-alive | Khoảng thời gian idle tối đa trước khi server gửi ping keep-alive |

Dùng path riêng như /graphql-ws giúp phân biệt handshake WebSocket với HTTP GraphQL endpoint /graphql. Điều này đặc biệt hữu ích khi cấu hình Spring Security: HTTP request và WebSocket handshake có thể cần quy tắc khác nhau.

Keep-alive chỉ kiểm tra kết nối còn hoạt động theo cơ chế ping/pong. Nó không xác minh token còn hiệu lực, không gia hạn phiên đăng nhập và không thay thế authorization.

## 4. Gửi bearer token trong connection_init

Với ứng dụng chạy trong browser, API WebSocket chuẩn không cho phép JavaScript tùy ý thêm header Authorization vào handshake như khi dùng fetch. Giao thức GraphQL over WebSocket cung cấp payload connection_init để client gửi metadata khởi tạo, thường dùng cho thông tin xác thực.

Ví dụ thông điệp:

~~~json
{
  "type": "connection_init",
  "payload": {
    "Authorization": "Bearer eyJhbGciOi..."
  }
}
~~~

Server phản hồi connection_ack khi khởi tạo được chấp nhận. Sau đó client mới gửi operation subscribe.

Với thư viện JavaScript graphql-ws, có thể cấu hình connectionParams:

~~~javascript
import { createClient } from "graphql-ws";

const client = createClient({
  url: "wss://api.example.com/graphql-ws",
  connectionParams: async () => {
    const accessToken = await getAccessToken();

    return {
      Authorization: "Bearer " + accessToken
    };
  }
});
~~~

connectionParams được dùng để tạo payload của connection_init. Nếu client reconnect, callback có thể lấy access token mới cho connection mới. Không đưa token vào query string vì URL thường xuất hiện trong access log, browser history, proxy log và hệ thống giám sát.

Luôn dùng wss:// ở môi trường production để mã hóa token và dữ liệu subscription trên đường truyền.

## 5. AuthenticationWebSocketInterceptor tích hợp sẵn

Spring for GraphQL cung cấp hai class có tên AuthenticationWebSocketInterceptor:

- org.springframework.graphql.server.webmvc.AuthenticationWebSocketInterceptor cho Spring MVC.
- org.springframework.graphql.server.webflux.AuthenticationWebSocketInterceptor cho Spring WebFlux.

Cả hai mở rộng AbstractAuthenticationWebSocketInterceptor. Chúng lấy thông tin xác thực từ payload connection_init, gọi authentication manager, lưu authentication vào WebSocket session attributes và truyền SecurityContext sang các request GraphQL tiếp theo trên connection.

BearerTokenAuthenticationExtractor là extractor tích hợp để lấy bearer token. Constructor mặc định dùng key Authorization trong payload:

~~~java
new BearerTokenAuthenticationExtractor()
~~~

Đây là cách phù hợp khi client gửi Authorization: Bearer ... trong connection_init. Nếu ứng dụng dùng cấu trúc payload khác, có thể triển khai AuthenticationExtractor riêng.

## 6. Đăng ký interceptor cho Spring MVC

Với servlet stack, đăng ký interceptor WebMVC dưới dạng bean. Ví dụ dưới đây giả định ứng dụng đã có JwtDecoder được cấu hình bằng issuer URI và sử dụng JWT bearer token:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/issuer
~~~

Cấu hình interceptor:

~~~java
package com.example.graphql.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.WebSocketGraphQlInterceptor;
import org.springframework.graphql.server.support.BearerTokenAuthenticationExtractor;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.jwt.JwtDecoder;

@Configuration
public class GraphQlWebSocketSecurityConfiguration {

    @Bean
    AuthenticationManager webSocketAuthenticationManager(JwtDecoder jwtDecoder) {
        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(jwtDecoder);

        return new ProviderManager(provider);
    }

    @Bean
    WebSocketGraphQlInterceptor webSocketAuthenticationInterceptor(
            AuthenticationManager webSocketAuthenticationManager) {

        return new org.springframework.graphql.server.webmvc.AuthenticationWebSocketInterceptor(
            new BearerTokenAuthenticationExtractor(),
            webSocketAuthenticationManager
        );
    }
}
~~~

JwtAuthenticationProvider xác minh bearer token bằng JwtDecoder và tạo Authentication đã xác thực. Trong hệ thống dùng custom claim hoặc authority converter riêng, cấu hình cùng converter cho provider này để authority trong WebSocket session nhất quán với HTTP resource server.

Không đăng ký đồng thời interceptor WebMVC và WebFlux. Chọn đúng class theo application stack. Bean WebSocketGraphQlInterceptor được Spring Boot sử dụng trong interception chain của GraphQL WebSocket endpoint.

## 7. Đăng ký interceptor cho Spring WebFlux

Với WebFlux, constructor nhận ReactiveAuthenticationManager thay cho AuthenticationManager. Ví dụ:

~~~java
package com.example.graphql.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.WebSocketGraphQlInterceptor;
import org.springframework.graphql.server.support.BearerTokenAuthenticationExtractor;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtReactiveAuthenticationManager;

@Configuration
public class GraphQlWebSocketSecurityConfiguration {

    @Bean
    ReactiveAuthenticationManager webSocketAuthenticationManager(
            ReactiveJwtDecoder jwtDecoder) {
        return new JwtReactiveAuthenticationManager(jwtDecoder);
    }

    @Bean
    WebSocketGraphQlInterceptor webSocketAuthenticationInterceptor(
            ReactiveAuthenticationManager webSocketAuthenticationManager) {

        return new org.springframework.graphql.server.webflux.AuthenticationWebSocketInterceptor(
            new BearerTokenAuthenticationExtractor(),
            webSocketAuthenticationManager
        );
    }
}
~~~

JwtReactiveAuthenticationManager xác thực token theo reactive flow. Cần dùng ReactiveJwtDecoder và issuer/JWK configuration tương ứng. Không trộn authentication manager đồng bộ của Servlet với WebFlux interceptor.

## 8. Bảo vệ HTTP handshake và connection_init

Nếu dùng bearer token trong connection_init, có thể cho phép HTTP handshake tới path WebSocket đi qua filter chain rồi để interceptor xác thực payload. Nên dùng path riêng để không vô tình mở HTTP GraphQL endpoint:

~~~java
import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/graphql-ws").permitAll()
            .requestMatchers("/graphql").authenticated()
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
        .build();
}
~~~

permitAll() ở đây chỉ cho phép request nâng cấp WebSocket đi tới handler. Nó không cấp danh tính và không thay thế xác thực trong connection_init. Interceptor phải từ chối payload thiếu hoặc token không hợp lệ; client chỉ gửi subscription sau khi server chấp nhận connection initialization.

Nếu dùng cookie/session authentication, hãy xác thực ngay ở HTTP handshake và yêu cầu session hợp lệ cho endpoint WebSocket. Không áp dụng cấu hình permitAll() của ví dụ bearer payload cho mô hình cookie mà không thiết kế lại ranh giới bảo mật.

Giữ CSRF protection phù hợp với cơ chế cookie/session ở HTTP endpoint. CSRF filter và CORS không thay thế kiểm tra Origin của WebSocket handshake.

## 9. Authentication được truyền tới các subscription như thế nào?

Sau khi connection_init được xác thực, AuthenticationWebSocketInterceptor lưu authentication vào thuộc tính của WebSocket session. Với mỗi GraphQL request tiếp theo trên session, interceptor khôi phục và truyền SecurityContext vào Reactor context để resolver và service có thể dùng.

Ví dụ resolver nhận principal:

~~~java
import java.security.Principal;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class OrderSubscriptionController {

    private final OrderService orderService;

    public OrderSubscriptionController(OrderService orderService) {
        this.orderService = orderService;
    }

    @SubscriptionMapping
    public Flux<OrderUpdate> orderUpdates(
            @Argument("orderId") String orderId,
            Principal principal) {

        return orderService.updatesVisibleTo(
            orderId,
            principal.getName()
        );
    }
}
~~~

Principal đại diện người dùng đã được xác thực trên connection. Resolver không cần nhận userId từ client rồi tin giá trị đó để quyết định ai được xem stream.

Tất cả operation trên cùng một WebSocket session dùng chung danh tính connection. Vì vậy, không dùng chung một WebSocket client instance cho nhiều người dùng đăng nhập khác nhau. Khi đổi tài khoản, hãy dừng connection cũ và tạo connection mới với credential của người dùng mới.

## 10. Authorization khi bắt đầu và trong lúc stream chạy

@PreAuthorize hoặc kiểm tra quyền trong service có thể bảo vệ việc bắt đầu subscription:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Flux<OrderUpdate> updatesVisibleTo(String orderId, String username) {
    return orderRepository.findUpdatesVisibleTo(orderId, username);
}
~~~

Tuy nhiên, subscription resolver thường được gọi một lần khi client bắt đầu operation. Nếu quyền của người dùng bị thu hồi sau đó, annotation method security không tự chạy lại cho từng event được phát ra.

Nếu chính sách yêu cầu quyền phải được kiểm tra liên tục, cần lọc hoặc xác minh ở luồng event:

~~~java
@SubscriptionMapping
public Flux<OrderUpdate> orderUpdates(
        @Argument("orderId") String orderId,
        Principal principal) {

    return orderService.updatesFor(orderId)
        .filterWhen(update ->
            authorizationService.canReadUpdate(principal.getName(), update)
        );
}
~~~

Cách khác là tạo publisher chỉ phát các event thuộc phạm vi tenant/owner của principal, hoặc hủy stream khi tài khoản bị khóa hay quyền bị thu hồi. Chọn chiến lược theo độ nhạy dữ liệu và yêu cầu thời gian thu hồi quyền.

Không giả định kiểm tra quyền một lần lúc mở connection sẽ bảo vệ mọi event mãi mãi. Một connection dài hạn có thể tồn tại lâu hơn access token, phiên đăng nhập hoặc quyền truy cập ban đầu.

## 11. Token hết hạn và làm mới credential

Thông điệp connection_init chỉ được gửi ở đầu WebSocket session. Built-in authentication interceptor xác thực token lúc khởi tạo và truyền SecurityContext đã xác thực tới các request tiếp theo.

Điều này dẫn đến một số điểm cần thiết kế:

- Token hết hạn sau khi connection đã được xác thực không tự động khiến mọi subscription đang chạy dừng ngay lập tức.
- Làm mới access token ở client không tự gửi lại connection_init trên session đang mở.
- Một connection mới có thể dùng token mới trong connection_init.
- Nếu cần thu hồi quyền ngay lập tức, phải có cơ chế kiểm tra lại quyền, thu hồi session hoặc kết thúc publisher.

Một chiến lược phổ biến là dùng access token ngắn hạn, theo dõi thời điểm hết hạn và chủ động đóng/reconnect WebSocket bằng token mới. Với hệ thống yêu cầu thu hồi tức thời, kết hợp thêm session registry hoặc event thu hồi quyền để server có thể đóng connection hay cancel subscription của người dùng.

Không nên xem PING/PONG keep-alive là cơ chế refresh token. Ping chỉ giúp phát hiện connection còn hoạt động.

## 12. Origin validation và Cross-Site WebSocket Hijacking

Trình duyệt tự gửi cookie phù hợp khi tạo WebSocket handshake. Nếu ứng dụng dùng cookie session và chấp nhận WebSocket từ mọi Origin, một trang độc hại có thể khiến trình duyệt của người dùng đã đăng nhập mở connection tới server và thực hiện GraphQL operation bằng session của nạn nhân. Đây là Cross-Site WebSocket Hijacking (CSWSH).

Origin validation cần được cấu hình ở WebSocket handshake:

- Chỉ cho phép origin của frontend hợp lệ.
- Không dùng wildcard * khi connection dùng cookie hoặc credential của người dùng.
- Không coi CORS HTTP là cơ chế bảo vệ WebSocket.
- Dùng TLS wss://.
- Xác thực connection và authorization từng operation vẫn cần được thực hiện riêng.

Origin là tín hiệu kiểm soát nguồn khởi tạo từ browser, không phải danh tính. Client không phải trình duyệt có thể tự tạo header Origin, vì vậy không dùng Origin thay cho authentication.

### Lưu ý bản vá CVE-2026-41700

Spring for GraphQL đã công bố CVE-2026-41700 về Cross-Site WebSocket Hijacking. Ứng dụng bị ảnh hưởng khi bật WebSocket transport, dùng cookie-based session authentication và không có cấu hình kiểm tra Origin ở cấp WebSocket/Spring Security.

Các dải phiên bản OSS bị ảnh hưởng gồm:

- 1.0.0 đến 1.0.6.
- 1.3.0 đến 1.3.8.
- 1.4.0 đến 1.4.5.
- 2.0.0 đến 2.0.3.

Các phiên bản OSS đã vá gồm 1.4.6 và 2.0.4 trên các nhánh tương ứng. Hãy ưu tiên phiên bản đang được hỗ trợ và đã bao gồm bản vá. Các phiên bản cũ đã hết vòng đời có thể không còn bản vá OSS công khai.

Bản vá áp dụng chính sách same-origin mặc định cho GraphQL WebSocket handshake. Nếu ứng dụng thực sự cần cross-origin, chỉ cấu hình allow-list origin cụ thể. Không mở rộng cho mọi origin để xử lý lỗi kết nối. Tham khảo advisory chính thức trước khi triển khai hoặc nâng cấp.

## 13. Giới hạn connection và tài nguyên

WebSocket session có thể giữ nhiều subscription đồng thời. Một client có thể tiêu thụ CPU, memory, queue và connection tới broker nếu server không giới hạn.

Nên kiểm soát:

- Số WebSocket connection tối đa ở server, reverse proxy hoặc connector.
- Kích thước tối đa của WebSocket message buffer.
- Thời gian chờ connection_init.
- Số subscription đồng thời trên một session.
- Số connection hoặc subscription theo user/tenant.
- Tần suất gửi event, queue size và backpressure.
- Thời gian sống tối đa của connection nếu chính sách bảo mật yêu cầu reconnect định kỳ.

Spring GraphQL cho phép giới hạn maxSubscriptionsPerSession khi xây dựng GraphQlWebSocketHandler. Mặc định không có giới hạn; khi đạt ngưỡng đã cấu hình, session sẽ bị đóng. Kích thước message buffer và số connection tối đa thuộc cấu hình server/connector bên dưới, không phải chỉ một thuộc tính GraphQL.

Không để client gửi subscription với filter quá rộng hoặc tạo hàng nghìn stream không giới hạn. Kết hợp query cost/depth limit, rate limit, pagination và authorization theo tenant.

## 14. Theo dõi connection lifecycle và cancellation

WebSocketGraphQlInterceptor mở rộng WebGraphQlInterceptor và cung cấp callback cho lifecycle connection:

- handleConnectionInitialization(...): xử lý payload connection_init.
- handleCancelledSubscription(...): nhận thông báo client hủy một subscription.
- handleConnectionClosed(...): được gọi khi WebSocket session đóng.
- intercept(...): can thiệp vào từng GraphQL request trên connection.

Callback handleCancelledSubscription được gọi khi client gửi complete; publisher nền của subscription được hủy tự động. Callback có thể dùng để ghi nhận audit hoặc dọn dẹp tài nguyên bổ sung. handleConnectionClosed phù hợp để giải phóng trạng thái gắn với session.

Trong một interceptor chain chỉ có thể có tối đa một WebSocketGraphQlInterceptor. Nếu cần vừa xác thực vừa theo dõi lifecycle, có thể kết hợp logic vào một interceptor hoặc dùng các WebGraphQlInterceptor thông thường cho các tác vụ không cần callback riêng của WebSocket.

Không ghi token nguyên văn, toàn bộ connection_init payload hoặc cookie vào log. Có thể ghi session ID, user ID đã chuẩn hóa, số subscription đang hoạt động, thời điểm mở/đóng và lý do kết thúc theo chính sách audit.

## 15. Phân biệt WebSocket, SSE và RSocket

Không phải mọi GraphQL subscription đều có cùng cơ chế xác thực connection:

| Transport | Cách xác thực thường dùng | Phạm vi |
| --- | --- | --- |
| WebSocket | HTTP handshake/session hoặc token trong connection_init | Một danh tính gắn với WebSocket session, dùng chung cho nhiều operation |
| SSE | HTTP security filter chain và credential của request mở stream | Mỗi stream là một HTTP request riêng |
| RSocket | Authentication qua RSocket setup/metadata và RSocket security | RSocket connection/session và request theo cấu hình |

SSE không dùng connection_init; hãy bảo vệ HTTP request tạo stream bằng Spring Security. RSocket không dùng giao thức GraphQL WebSocket nên AuthenticationWebSocketInterceptor không áp dụng cho RSocket. Chọn interceptor và security mechanism theo đúng transport đang chạy.

## 16. Kiểm thử bảo mật subscription connection

Kiểm thử cần xác minh cả xác thực ban đầu, quyền trên operation và hành vi của stream dài hạn.

Có thể dùng WebSocketGraphQlTester để kiểm thử với WebSocket server thật hoặc test environment hỗ trợ WebSocket:

~~~java
import java.util.Map;

import org.springframework.graphql.client.WebSocketGraphQlClientInterceptor;
import org.springframework.graphql.test.tester.WebSocketGraphQlTester;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;
import reactor.core.publisher.Mono;

WebSocketGraphQlTester tester =
    WebSocketGraphQlTester.builder(
            "ws://localhost:8080/graphql-ws",
            new ReactorNettyWebSocketClient()
        )
        .interceptor(new WebSocketGraphQlClientInterceptor() {
            @Override
            public Mono<Object> connectionInitPayload() {
                return Mono.just(Map.of(
                    "Authorization", "Bearer " + accessToken
                ));
            }

            @Override
            public Mono<Void> handleConnectionAck(Map<String, Object> payload) {
                return Mono.empty();
            }
        })
        .build();
~~~

Ví dụ giả định accessToken là JWT test hợp lệ và server đã đăng ký AuthenticationWebSocketInterceptor tương ứng. Trong test thực tế, không hardcode token production; dùng token test hoặc test identity provider.

Các tình huống nên có:

1. Token hợp lệ: connection được acknowledge và subscription nhận event.
2. Thiếu token: connection initialization bị từ chối, không có operation nào chạy.
3. Token sai chữ ký hoặc hết hạn: không nhận connection_ack thành công.
4. Người dùng thiếu scope: connection có thể được xác thực nhưng operation bị từ chối.
5. Người dùng mất quyền trong lúc stream chạy: event tiếp theo bị lọc hoặc subscription bị kết thúc theo chính sách.
6. Client gửi complete: publisher được cancel và resource riêng được dọn dẹp.
7. WebSocket handshake từ Origin không được phép: server từ chối handshake.
8. Một session đạt giới hạn subscription: server đóng session hoặc từ chối theo cấu hình.
9. Hai người dùng khác nhau: không chia sẻ connection hoặc SecurityContext.
10. Token được refresh: client reconnect và gửi token mới trong connection initialization.

Dùng StepVerifier để kiểm tra event và cancellation ở tầng publisher; dùng WebSocketGraphQlTester hoặc integration test transport để xác minh protocol, authentication handshake và cleanup thực tế. Test service Flux đơn lẻ không chứng minh WebSocket handler đã truyền đúng security context.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| WebSocket mở được nhưng subscribe bị từ chối | Không gửi connection_init hoặc payload thiếu token | Kiểm tra client connection parameters |
| HTTP query có authentication nhưng WebSocket subscription là anonymous | Token chỉ được gửi ở HTTP header, chưa truyền vào connection initialization | Dùng AuthenticationWebSocketInterceptor hoặc cookie/session handshake |
| Token hợp lệ nhưng authentication interceptor từ chối | AuthenticationManager không hỗ trợ loại bearer token extractor tạo ra | Cấu hình provider hỗ trợ BearerTokenAuthenticationToken |
| Principal không có trong resolver | SecurityContext không được truyền vào WebSocket request | Kiểm tra đúng interceptor MVC/WebFlux và bean registration |
| Người dùng đổi tài khoản nhưng vẫn nhận event cũ | WebSocket client dùng chung session đã xác thực bằng user trước | Đóng session và tạo connection mới |
| Token hết hạn nhưng subscription vẫn tiếp tục | Authentication được xác thực lúc connection init và context còn gắn với session | Reconnect, kiểm tra quyền trong stream hoặc chủ động thu hồi session |
| Cookie-auth WebSocket bị CSWSH | Origin không được giới hạn hoặc phiên bản có lỗ hổng | Nâng cấp bản vá và cấu hình allow-list Origin |
| Một client mở quá nhiều subscription | Không giới hạn subscription/connection | Đặt giới hạn theo session, user và hạ tầng |
| Cleanup không chạy khi client rời đi | Không xử lý cancellation hoặc connection-close lifecycle | Dùng publisher cleanup và callback lifecycle phù hợp |

## 18. Checklist triển khai

- GraphQL WebSocket endpoint đã được bật tại path riêng và chỉ mở cho transport cần dùng?
- Client gửi credential trong HTTP handshake hoặc connection_init theo một mô hình nhất quán?
- Interceptor đúng stack MVC/WebFlux đã được đăng ký?
- AuthenticationManager xác minh token, issuer, chữ ký và thời hạn?
- Operation chỉ được xử lý sau khi connection initialization được chấp nhận?
- Principal/SecurityContext được truyền tới resolver và service?
- Authorization được kiểm tra khi bắt đầu subscription và trong stream nếu cần thu hồi quyền tức thời?
- Token refresh hoặc user switch có chiến lược đóng/reconnect rõ ràng?
- WebSocket Origin chỉ cho phép frontend hợp lệ, đặc biệt khi dùng cookie/session?
- Spring for GraphQL đang ở phiên bản đã vá CVE-2026-41700?
- Số connection, message size và subscription đồng thời có giới hạn?
- Có audit cho connection mở/đóng, cancellation và lỗi xác thực mà không log token?
- Integration test bao phủ token hợp lệ, token sai, thiếu quyền, Origin không hợp lệ và cancellation?

Bảo vệ subscription connection cần quản lý cả danh tính của WebSocket session lẫn quyền truy cập dữ liệu trong suốt vòng đời stream. Spring for GraphQL cung cấp AuthenticationWebSocketInterceptor để xác thực token trong connection_init và truyền SecurityContext tới các operation tiếp theo. Ứng dụng vẫn phải kiểm tra authorization, xử lý token hết hạn/thu hồi quyền, giới hạn tài nguyên và bảo vệ Origin của handshake. Kết hợp những lớp này giúp subscription an toàn ngay cả khi connection tồn tại lâu và mang nhiều operation đồng thời.

## Tài liệu tham khảo

- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — WebSocket Authentication API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/server/support/AbstractAuthenticationWebSocketInterceptor.html)
- [Spring for GraphQL — WebSocket Client](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Security Advisory — CVE-2026-41700](https://spring.io/security/cve-2026-41700)
- [Spring for GraphQL Examples — WebSocket Authentication](https://github.com/spring-projects/spring-graphql-examples)

