# Thêm header vào response

Trong ứng dụng web, HTTP response header mang metadata đi kèm response body. Ví dụ, server có thể trả về correlation ID để client gửi kèm khi báo lỗi, thêm cookie sau khi đăng nhập, chỉ định chính sách cache hoặc cung cấp một mã phiên bản API. Với Spring for GraphQL, có thể thêm những header này bằng **WebGraphQlInterceptor** sau khi GraphQL engine xử lý operation.

GraphQL response body và HTTP response header là hai phần khác nhau. Body chứa dữ liệu trong data, lỗi trong errors và metadata GraphQL trong extensions. Header thuộc tầng HTTP transport. Nếu client cần đọc một giá trị như request ID từ HTTP response, hãy đặt nó vào response header; nếu giá trị là một phần hợp đồng dữ liệu GraphQL, hãy cân nhắc trả về trong field hoặc extensions.

## WebGraphQlInterceptor xử lý response ở đâu?

WebGraphQlInterceptor nằm trong chuỗi xử lý request của Spring for GraphQL. Interceptor nhận WebGraphQlRequest, có thể kiểm tra hoặc bổ sung thông tin trước khi gọi GraphQL engine, rồi nhận WebGraphQlResponse khi operation hoàn tất:

~~~text
HTTP request
    |
    v
WebGraphQlInterceptor
    |
    v
GraphQL engine và các resolver
    |
    v
WebGraphQlResponse
    |
    v
WebGraphQlInterceptor xử lý response
    |
    v
HTTP response headers và body
~~~

Phương thức intercept trả về Mono<WebGraphQlResponse>. Lời gọi chain.next(request) chuyển request sang interceptor tiếp theo và cuối cùng tới GraphQL engine. Khi publisher phát ra response, interceptor có thể thêm header vào response trước khi transport ghi HTTP response về client.

Spring for GraphQL cung cấp WebGraphQlResponse.getResponseHeaders() để truy cập HttpHeaders sẽ được ghi vào HTTP response. Theo mặc định, danh sách header này rỗng. Đây là API dành cho GraphQL over HTTP; nó không thêm header HTTP riêng cho từng operation WebSocket vì handshake HTTP đã hoàn tất trước khi các operation bắt đầu.

## Thêm một header cố định cho GraphQL HTTP response

Ví dụ sau thêm header X-GraphQL-Server vào mọi response đi qua interceptor:

~~~java
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class ResponseHeaderInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        return chain.next(request).doOnNext(response -> {
            response.getResponseHeaders()
                    .set("X-GraphQL-Server", "catalog-api");
        });
    }
}
~~~

Đoạn code thực hiện ba việc:

1. Nhận request và chuyển tiếp bằng chain.next(request).
2. Đợi GraphQL xử lý xong và phát ra WebGraphQlResponse.
3. Ghi header vào response.getResponseHeaders().

doOnNext phù hợp vì thao tác thêm header là side effect trên response object. Nếu muốn biến đổi và trả về một response khác, có thể dùng map rồi trả response sau khi cập nhật header:

~~~java
return chain.next(request).map(response -> {
    response.getResponseHeaders().set("X-GraphQL-Server", "catalog-api");
    return response;
});
~~~

Hai cách trên đều xử lý response trong reactive pipeline, không cần block() hoặc chờ đồng bộ GraphQL execution.

## Đăng ký interceptor trong Spring Boot

Khi dùng Spring Boot với GraphQL starter và HTTP transport, chỉ cần khai báo WebGraphQlInterceptor dưới dạng Spring bean. Có thể dùng @Component như ví dụ trước hoặc tạo bean bằng @Configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.WebGraphQlInterceptor;

@Configuration
public class GraphQlInterceptorConfiguration {

    @Bean
    WebGraphQlInterceptor responseHeaderInterceptor() {
        return (request, chain) ->
                chain.next(request).doOnNext(response ->
                        response.getResponseHeaders()
                                .set("X-GraphQL-Server", "catalog-api"));
    }
}
~~~

Spring Boot tự phát hiện bean WebGraphQlInterceptor và đăng ký với web transport. Nếu tự tạo WebGraphQlHandler hoặc tự cấu hình transport, cần thêm interceptor vào chain tương ứng. Khi ứng dụng có nhiều interceptor, hãy thiết kế thứ tự xử lý rõ ràng, đặc biệt khi một interceptor tạo dữ liệu trong GraphQLContext và interceptor khác đọc dữ liệu đó sau khi execution hoàn tất.

## Thêm header động từ GraphQLContext

Có trường hợp giá trị header chỉ được biết sau khi resolver chạy. Ví dụ, một mutation đăng nhập tạo cookie phiên hoặc một resolver tạo mã theo dõi nghiệp vụ. Controller có thể đặt giá trị vào GraphQLContext; interceptor đọc giá trị đó sau khi chain.next(request) hoàn tất rồi thêm header.

Controller lưu giá trị cần phát hành:

~~~java
import graphql.GraphQLContext;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class SessionController {

    private final SessionService sessionService;

    public SessionController(SessionService sessionService) {
        this.sessionService = sessionService;
    }

    @MutationMapping
    public LoginPayload login(
            @Argument LoginInput input,
            GraphQLContext context) {

        CreatedSession session = sessionService.login(input);
        context.put("sessionCookieValue", session.cookieValue());

        return new LoginPayload(session.userId(), session.expiresAt());
    }
}
~~~

Interceptor đọc giá trị sau khi GraphQL engine thực thi:

~~~java
import graphql.GraphQLContext;
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class SessionCookieInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        return chain.next(request).doOnNext(response -> {
            GraphQLContext context =
                    response.getExecutionInput().getGraphQLContext();
            String cookieValue = context.get("sessionCookieValue");

            if (cookieValue != null) {
                ResponseCookie cookie = ResponseCookie
                        .from("SESSION", cookieValue)
                        .httpOnly(true)
                        .secure(true)
                        .sameSite("Lax")
                        .path("/")
                        .build();

                response.getResponseHeaders()
                        .add(HttpHeaders.SET_COOKIE, cookie.toString());
            }
        });
    }
}
~~~

Ví dụ này minh họa cách chuyển một giá trị từ resolver sang interceptor qua GraphQLContext. Payload GraphQL chỉ trả userId và thời điểm hết hạn; giá trị cookie không được đưa vào response body. Trong ứng dụng thật, SessionService phải tạo và xác minh session theo chính sách xác thực của hệ thống.

GraphQLContext ở đây thuộc một execution. Không giữ giá trị cookie trong field của interceptor hoặc singleton service, vì nhiều request có thể chạy đồng thời. Nếu một operation có nhiều resolver cùng ghi một key, cần quy định rõ resolver nào sở hữu giá trị đó hoặc dùng một cấu trúc dữ liệu riêng theo từng field.

## Dùng ResponseCookie để tạo Set-Cookie

Khi thêm cookie, nên dùng ResponseCookie của Spring thay vì tự nối chuỗi header. Builder hỗ trợ các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| httpOnly | Ngăn JavaScript phía trình duyệt đọc cookie qua document.cookie |
| secure | Chỉ gửi cookie qua kết nối HTTPS |
| sameSite | Kiểm soát việc gửi cookie trong ngữ cảnh cross-site |
| path | Giới hạn đường dẫn mà cookie được gửi tới |
| domain | Giới hạn host/domain nhận cookie |
| maxAge | Thời gian cookie còn hiệu lực |

Ví dụ cookie phiên:

~~~java
import java.time.Duration;

import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;

ResponseCookie cookie = ResponseCookie.from("SESSION", sessionId)
        .httpOnly(true)
        .secure(true)
        .sameSite("Strict")
        .path("/")
        .maxAge(Duration.ofHours(8))
        .build();

response.getResponseHeaders().add(
        HttpHeaders.SET_COOKIE,
        cookie.toString());
~~~

Chọn SameSite phù hợp với cách frontend và backend được triển khai. Strict hạn chế gửi cookie trong điều hướng cross-site; Lax cho phép một số điều hướng cấp cao; None cho phép ngữ cảnh cross-site và yêu cầu Secure. Nếu dùng cookie xác thực, cần thiết kế thêm CSRF protection phù hợp. Không ghi token hoặc giá trị cookie vào log.

## Phân biệt add và set

getResponseHeaders() trả về HttpHeaders. Hai thao tác thường dùng là add và set:

| Phương thức | Hành vi | Khi dùng |
| --- | --- | --- |
| set(name, value) | Thay thế các giá trị hiện có của header bằng một giá trị | Header chỉ cần một giá trị như X-Request-Id |
| add(name, value) | Thêm một giá trị mới, giữ các giá trị đã có | Header cho phép nhiều giá trị hoặc nhiều Set-Cookie |

Ví dụ:

~~~java
HttpHeaders headers = response.getResponseHeaders();
headers.set("X-Request-Id", requestId);
headers.add(HttpHeaders.SET_COOKIE, firstCookie.toString());
headers.add(HttpHeaders.SET_COOKIE, secondCookie.toString());
~~~

Không gộp nhiều Set-Cookie thành một chuỗi phân tách bằng dấu phẩy. Mỗi cookie cần một header Set-Cookie riêng; dùng add để giữ các cookie độc lập.

Nếu nhiều interceptor cùng ghi một header, thứ tự chain có thể quyết định giá trị cuối cùng khi dùng set. Hãy thống nhất interceptor nào chịu trách nhiệm cho từng header, tránh ghi đè lẫn nhau hoặc tạo nhiều giá trị không mong muốn.

## Thêm correlation ID vào response header

Một ứng dụng thường cần trả correlation ID để client gửi khi báo lỗi. Có thể tạo ID ở interceptor trước khi gọi GraphQL engine, đặt nó vào GraphQLContext để resolver và log có thể đọc, sau đó trả lại cùng giá trị trong HTTP response header.

~~~java
import java.util.Map;
import java.util.UUID;

import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class RequestIdInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String requestId = UUID.randomUUID().toString();
        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(Map.of("requestId", requestId)).build());

        return chain.next(request).doOnNext(response ->
                response.getResponseHeaders().set("X-Request-Id", requestId));
    }
}
~~~

Resolver có thể đọc cùng request ID:

~~~java
import org.springframework.graphql.data.method.annotation.ContextValue;
import org.springframework.graphql.data.method.annotation.QueryMapping;

@QueryMapping
public String requestId(@ContextValue("requestId") String requestId) {
    return requestId;
}
~~~

Với ví dụ có nhiều interceptor cùng thêm dữ liệu vào GraphQLContext, cần kiểm tra cách chúng kết hợp context và thứ tự được đăng ký để không vô tình thay thế các key đã có. Có thể dùng một interceptor chuyên trách tạo request ID và cấu hình context một lần.

## Header response và GraphQL response extensions

GraphQL response body có thể chứa trường extensions:

~~~json
{
  "data": {
    "greeting": "Hello"
  },
  "extensions": {
    "requestId": "d6d5a5f1-7b2d-4a55-a2a5-8f4e8f1d0001"
  }
}
~~~

Đây là metadata nằm trong JSON body. Còn header:

~~~http
X-Request-Id: d6d5a5f1-7b2d-4a55-a2a5-8f4e8f1d0001
~~~

là metadata của HTTP response. Hãy chọn theo nhu cầu:

- Dùng HTTP header cho request ID, cache policy, cookie hoặc metadata transport.
- Dùng extensions cho metadata gắn với GraphQL execution mà client GraphQL cần đọc trong body.
- Dùng field trong schema nếu dữ liệu là một phần hợp đồng nghiệp vụ và cần được truy vấn có kiểu.

Không nên thêm dữ liệu nghiệp vụ vào header chỉ vì interceptor có thể ghi header. Header có giới hạn kích thước, không có kiểu dữ liệu GraphQL và không phù hợp với object hoặc danh sách phức tạp.

## WebSocket và RSocket có giới hạn khác HTTP

WebGraphQlInterceptor được dùng trong chuỗi xử lý HTTP và WebSocket. Tuy nhiên, WebGraphQlResponse.getResponseHeaders() được thiết kế để bổ sung header cho HTTP response. Với WebSocket, HTTP handshake đã hoàn tất trước khi client gửi GraphQL operation. Vì vậy, không thể dùng API này để gửi một HTTP response header mới cho từng query hoặc subscription trên kết nối đang mở.

Nếu cần gửi metadata cùng từng kết quả WebSocket, hãy dùng GraphQL response body, extensions hoặc thiết kế payload phù hợp với giao thức. Nếu cần metadata trong handshake, phải cấu hình ở tầng WebSocket handshake/interceptor trước khi kết nối được thiết lập.

RSocket dùng cơ chế interceptor riêng là RSocketQlInterceptor và không có HTTP response header. Không áp dụng ví dụ WebGraphQlResponse cho RSocket transport.

## CORS: cho phép trình duyệt đọc header tùy chỉnh

Server có thể trả header X-Request-Id nhưng JavaScript chạy ở origin khác không tự động được đọc mọi response header. Với cross-origin request, server cần khai báo header trong Access-Control-Expose-Headers hoặc cấu hình tương ứng của Spring Boot.

Ví dụ application.yml:

~~~yaml
spring:
  graphql:
    cors:
      allowed-origins: https://app.example.com
      allowed-methods: POST
      exposed-headers:
        - X-Request-Id
        - X-GraphQL-Server
~~~

Thuộc tính exposed-headers giúp trình duyệt cho phép script đọc các header được liệt kê. Nếu ứng dụng dùng cookie hoặc credentials trong cross-origin request, cần cấu hình allow-credentials và origin cụ thể phù hợp; không kết hợp credentials với wildcard origin. CORS chỉ điều khiển quyền truy cập từ trình duyệt, không phải cơ chế xác thực hoặc phân quyền API.

Client có thể đọc header sau khi request hoàn tất:

~~~javascript
const response = await fetch("/graphql", {
  method: "POST",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    query: "{ greeting }"
  })
});

const requestId = response.headers.get("X-Request-Id");
const body = await response.json();
~~~

Nếu header không được expose trong CORS, response vẫn có thể chứa header trên mạng nhưng JavaScript nhận null khi gọi headers.get.

## Bảo mật khi thêm response header

Response header có thể ảnh hưởng tới cách trình duyệt, proxy và cache xử lý dữ liệu. Hãy áp dụng các nguyên tắc:

- Không đưa access token, refresh token hoặc dữ liệu cá nhân vào custom header nếu không có yêu cầu rõ ràng.
- Không phản chiếu nguyên văn header do client gửi mà chưa kiểm tra định dạng và độ dài.
- Không cho phép dữ liệu không tin cậy chèn ký tự xuống dòng vào header value.
- Dùng ResponseCookie với HttpOnly, Secure và SameSite phù hợp khi phát hành cookie.
- Không ghi đè Content-Type, Content-Length, Transfer-Encoding hoặc các header transport do server quản lý nếu không có lý do đặc biệt.
- Tránh tự thêm các hop-by-hop header như Connection hoặc Transfer-Encoding; chúng thuộc tầng kết nối/proxy.
- Chỉ trả Cache-Control phù hợp với dữ liệu. Response chứa thông tin riêng tư thường cần chính sách no-store hoặc private theo yêu cầu ứng dụng.
- Đừng xem header là ranh giới bảo mật. Authorization vẫn phải được thực hiện trong Spring Security, service hoặc tầng domain.

Nếu một header là chính sách chung cho toàn bộ ứng dụng, chẳng hạn Strict-Transport-Security hoặc Content-Security-Policy, nên cân nhắc cấu hình tại Spring Security hoặc web server để áp dụng đồng nhất cho mọi endpoint. WebGraphQlInterceptor phù hợp với metadata gắn riêng GraphQL response.

## Kiểm thử response header

GraphQlTester hữu ích để kiểm tra dữ liệu GraphQL, nhưng khi cần xác minh HTTP response header, nên kiểm thử qua WebTestClient hoặc MockMvc. Ví dụ với WebTestClient:

~~~java
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("query", "{ greeting }"))
        .exchange()
        .expectStatus().isOk()
        .expectHeader().exists("X-Request-Id")
        .expectBody()
        .jsonPath("$.data.greeting").isEqualTo("Hello");
~~~

Nên kiểm thử các tình huống:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Query thành công | Header tùy chỉnh xuất hiện trong HTTP response |
| Mutation trả GraphQL error | Interceptor vẫn thêm header nếu GraphQL engine trả response bình thường |
| Request validation thất bại | Xác định rõ interceptor có nhận được response để thêm header hay không |
| Nhiều interceptor cùng ghi một header | Không bị ghi đè ngoài ý muốn |
| Nhiều Set-Cookie | Mỗi cookie được gửi thành một giá trị header riêng |
| CORS cross-origin | Browser script đọc được header đã expose |
| WebSocket operation | Không kỳ vọng có HTTP response header cho từng message |
| Giá trị context không tồn tại | Interceptor không phát hành cookie/header có giá trị null |

Với cookie, kiểm tra cả thuộc tính HttpOnly, Secure, SameSite, Path và Max-Age trong header Set-Cookie. Không chỉ xác nhận cookie name xuất hiện.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Header không xuất hiện | Interceptor chưa được đăng ký hoặc response chưa đi qua chain | Kiểm tra WebGraphQlInterceptor bean và web transport |
| Header có trong server log nhưng browser không đọc được | Chưa cấu hình CORS exposed-headers | Thêm header vào spring.graphql.cors.exposed-headers |
| Header luôn null | Context key chưa được resolver thiết lập hoặc sai tên | Kiểm tra key và thứ tự xử lý |
| Cookie bị ghi đè | Dùng set cho nhiều Set-Cookie | Dùng add cho từng cookie |
| Header bị nhân đôi | Nhiều interceptor cùng add một giá trị | Chọn một nơi sở hữu header hoặc dùng set |
| WebSocket không có header mới | HTTP handshake đã hoàn tất trước operation | Dùng extensions hoặc payload cho metadata từng message |
| Response header chứa giá trị không hợp lệ | Dữ liệu đầu vào chưa được kiểm tra | Validate và giới hạn header value |
| Thay đổi response body không có tác dụng | Dùng getResponseHeaders cho dữ liệu JSON hoặc ngược lại | Chọn HTTP header, extensions hoặc field đúng mục đích |

## Nguyên tắc thiết kế interceptor response header

Khi thêm header cho Spring for GraphQL, hãy nhớ:

1. **Dùng WebGraphQlInterceptor.** Thêm header sau chain.next(request), khi đã có WebGraphQlResponse.
2. **Ghi vào getResponseHeaders().** Đây là HttpHeaders mà HTTP transport sẽ đưa vào response.
3. **Phân biệt body và header.** Dùng extensions hoặc field cho dữ liệu GraphQL; dùng header cho metadata HTTP.
4. **Chọn add hoặc set đúng mục đích.** Dùng add cho nhiều Set-Cookie và set cho header đơn trị.
5. **Đăng ký interceptor thành bean.** Spring Boot tự đăng ký WebGraphQlInterceptor bean với web transport.
6. **Dùng GraphQLContext cho giá trị động theo execution.** Không lưu giá trị request vào field singleton.
7. **Cấu hình CORS expose header.** Browser cần exposed-headers để JavaScript đọc header tùy chỉnh.
8. **Bảo vệ cookie và header.** Kiểm tra giá trị, dùng thuộc tính cookie an toàn và không phát lộ credential.
9. **Hiểu giới hạn transport.** Response header API dành cho HTTP, không thêm header cho từng WebSocket message hoặc RSocket response.
10. **Kiểm thử ở tầng HTTP.** Dùng WebTestClient hoặc MockMvc để xác minh header thực tế.

WebGraphQlInterceptor cho phép bổ sung HTTP response header sau khi GraphQL engine hoàn tất operation. Spring for GraphQL cung cấp WebGraphQlResponse.getResponseHeaders() để ghi metadata vào response; GraphQLContext có thể chuyển giá trị do resolver tạo tới interceptor; ResponseCookie hỗ trợ phát hành cookie có thuộc tính bảo mật. Khi phân biệt rõ HTTP header với GraphQL response body, cấu hình CORS đúng và tôn trọng giới hạn của WebSocket/RSocket, việc thêm header sẽ nhất quán và an toàn hơn.

## Tài liệu tham khảo

- [Spring for GraphQL - Server Transports và WebGraphQlInterceptor](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL - WebGraphQlResponse API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/server/WebGraphQlResponse.html)
- [Spring Boot - Spring for GraphQL và CORS](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring Boot - Application Properties: spring.graphql.cors](https://docs.spring.io/spring-boot/appendix/application-properties/)
