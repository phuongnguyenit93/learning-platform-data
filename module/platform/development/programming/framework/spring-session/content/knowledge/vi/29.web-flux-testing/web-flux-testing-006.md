# Đổi định danh, invalidate và khôi phục trạng thái ở yêu cầu tiếp theo

Trong ứng dụng Spring WebFlux dùng Spring Session, một phiên được truy cập qua API `WebSession`. Session ID được gửi qua cookie hoặc cơ chế resolver khác; dữ liệu phiên được lưu trong `ReactiveSessionRepository`, chẳng hạn Redis reactive. Để kiểm chứng đúng vòng đời phiên, test cần gửi nhiều HTTP request nối tiếp: tạo trạng thái, đổi session ID, đọc lại trạng thái bằng ID mới, invalidate phiên rồi xác minh request tiếp theo không còn nhìn thấy dữ liệu cũ.

Điểm quan trọng là mỗi request có một vòng đời riêng. Không giữ object `WebSession` của request trước rồi dùng lại trong request sau. Request tiếp theo phải gửi session ID qua cookie để `WebSessionManager` tải phiên từ repository. Đây là cách chứng minh dữ liệu đã được lưu và có thể khôi phục sau ranh giới request.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích cách WebFlux phân giải session ID và tải `WebSession`.
- Đổi session ID bằng `WebSession.changeSessionId()` và xác minh thuộc tính được giữ.
- Kiểm tra cookie được cập nhật sau khi ID thay đổi.
- Invalidate session và xác minh ID cũ không còn truy cập được dữ liệu.
- Phân biệt trạng thái được khôi phục từ repository với object session trong bộ nhớ của request.
- Dùng `WebTestClient` với full application context và repository thật để kiểm tra vòng đời.
- Kiểm thử lỗi cookie, repository, timeout và các request kế tiếp.

## 1. Các thành phần trong vòng đời WebFlux session

Spring WebFlux dùng `WebSession` thay cho `HttpSession`. Spring Session tích hợp vào WebFlux bằng các thành phần:

| Thành phần | Vai trò |
|---|---|
| `WebSession` | API reactive cho thuộc tính, ID, timeout, đổi ID và invalidate |
| `WebSessionManager` | Lấy session cho request hiện tại, tạo phiên mới khi cần và điều phối store/resolver |
| `WebSessionIdResolver` | Đọc session ID từ request và ghi hoặc xóa ID ở response |
| `WebSessionStore` | Hợp đồng store mà WebFlux dùng để tạo, truy xuất, cập nhật và xóa phiên |
| `SpringSessionWebSessionStore` | Adapter nối `WebSessionStore` với repository Spring Session |
| `ReactiveSessionRepository` | Hợp đồng reactive để tạo, tìm, lưu và xóa `Session` |
| Reactive backend | Nơi dữ liệu phiên được lưu; ví dụ reactive Redis hoặc repository reactive tùy chỉnh |

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant M as WebSessionManager
    participant I as WebSessionIdResolver
    participant W as WebSessionStore
    participant R as ReactiveSessionRepository
    participant D as Shared store
    participant H as WebFlux handler
    C->>M: Request kèm cookie session ID
    M->>I: Resolve ID
    I-->>M: ID hoặc không có ID
    M->>W: retrieveSession(ID)
    W->>R: findById(ID)
    R->>D: Đọc session
    D-->>R: Session data
    R-->>W: Session hoặc empty
    W-->>M: WebSession
    M->>H: Cung cấp WebSession
    H->>H: Đọc/ghi hoặc đổi ID
    H-->>M: Reactive chain hoàn tất
    M->>W: Lưu/xóa thay đổi
    W->>R: save/deleteById
    R->>D: Ghi thay đổi
    D-->>R: Hoàn tất
    M->>I: Cập nhật hoặc expire cookie
    I-->>C: Response
~~~

Sơ đồ mô tả ranh giới trách nhiệm. Thời điểm tạo cookie, lưu session và xóa cookie phụ thuộc trạng thái của `WebSession`, resolver và repository. Handler nên trả về `Mono`/`Flux` để WebFlux theo dõi toàn bộ thao tác.

## 2. WebSession được tạo và khôi phục như thế nào?

Một handler gọi `exchange.getSession()` để lấy `Mono<WebSession>`. Nếu request có cookie hợp lệ và repository tìm thấy phiên, manager trả về phiên đó. Nếu không có ID hoặc ID không còn hợp lệ, manager có thể tạo phiên mới khi handler yêu cầu session.

Ví dụ đọc thuộc tính:

~~~java
@GetMapping("/session/state")
Mono<String> readState(ServerWebExchange exchange) {
    return exchange.getSession()
            .map(session -> {
                String state = session.getAttribute("workflowState");
                return state == null ? "EMPTY" : state;
            });
}
~~~

`getSession()` luôn cung cấp một `WebSession`, vì vậy request không có cookie có thể tạo phiên mới. Điều này phù hợp với handler muốn bắt đầu phiên mới, nhưng test “không tìm thấy session cũ” cần kiểm tra thuộc tính hoặc trạng thái phiên thay vì giả định không có object session.

Không gọi `block()` trong handler để lấy session đồng bộ. Không gọi `subscribe()` thủ công để lưu thuộc tính rồi trả response trước khi công việc hoàn tất. Hãy nối thao tác vào reactive chain và trả publisher cho framework.

## 3. Đổi session ID bằng changeSessionId()

`WebSession.changeSessionId()` trả về `Mono<Void>`. Khi hoàn tất, session đang được request sử dụng có ID mới. Các thuộc tính của phiên tiếp tục thuộc cùng phiên logic; thao tác này không có nghĩa tạo một phiên rỗng rồi bỏ dữ liệu cũ.

Đổi ID thường cần trong các tình huống:

- Sau khi người dùng xác thực thành công.
- Khi nâng quyền hoặc chuyển sang một ngữ cảnh bảo mật khác.
- Khi ứng dụng cần giảm nguy cơ session fixation.
- Khi quy trình bảo mật yêu cầu thay credential định danh phiên.

Ví dụ handler:

~~~java
@PostMapping("/session/rotate")
Mono<String> rotateSessionId(ServerWebExchange exchange) {
    return exchange.getSession()
            .flatMap(session ->
                    session.changeSessionId()
                            .then(Mono.fromSupplier(session::getId)));
}
~~~

`then(Mono.fromSupplier(...))` bảo đảm chỉ đọc ID sau khi thao tác đổi ID hoàn tất. Nếu gọi `session.getId()` trước khi publisher chạy, test hoặc handler có thể ghi nhận ID cũ.

Việc phát cookie ID mới do `WebSessionManager` và `WebSessionIdResolver` điều phối trong vòng đời response. Không tự đặt cookie bằng tay trong handler; làm vậy dễ tạo sai khác giữa ID trong repository và ID trình duyệt gửi.

## 4. Đổi ID phải giữ trạng thái phiên

Giả sử phiên đang có:

~~~text
Session ID: old-id
workflowState = "PAYMENT_PENDING"
cartReference = "cart-42"
~~~

Sau `changeSessionId()`, kết quả mong đợi:

~~~text
Session ID: new-id
workflowState = "PAYMENT_PENDING"
cartReference = "cart-42"
~~~

ID thay đổi nhưng trạng thái ứng dụng của cùng phiên được bảo toàn. Repository và store có trách nhiệm lưu phiên với ID mới theo semantics implementation; resolver phát ID mới cho client.

Test cần kiểm tra cả hai điều:

1. Cookie ở response đổi ID.
2. Request kế tiếp gửi cookie mới đọc lại được các thuộc tính trước đó.

Chỉ kiểm tra giá trị ID khác nhau là chưa đủ. Nếu thuộc tính bị mất trong quá trình đổi ID, thao tác xoay ID không đáp ứng mục đích giữ phiên đăng nhập hoặc workflow.

## 5. Invalidate có ý nghĩa gì?

`WebSession.invalidate()` trả về `Mono<Void>` và làm phiên hiện tại không còn hợp lệ. Spring Session yêu cầu store/repository xóa hoặc vô hiệu hóa dữ liệu phiên; resolver cũng được điều phối để expire session ID ở response.

Ví dụ:

~~~java
@PostMapping("/session/invalidate")
Mono<Void> invalidate(ServerWebExchange exchange) {
    return exchange.getSession()
            .flatMap(WebSession::invalidate);
}
~~~

Sau khi invalidate hoàn tất:

- Phiên cũ không được tiếp tục sử dụng như một phiên hợp lệ.
- Request tiếp theo mang ID cũ không được khôi phục thuộc tính cũ.
- Response có thể phát cookie hết hạn để trình duyệt ngừng gửi ID đó.
- Request tiếp theo có thể tạo session mới nếu handler gọi `getSession()`.

Cookie hết hạn và session bị xóa là hai việc khác nhau. Một client tự viết vẫn có thể gửi lại cookie cũ sau khi server đã phát lệnh expire. Do đó, server phải từ chối ID đã invalidate ngay cả khi client cố tình gửi lại.

## 6. Endpoint kiểm thử cho trạng thái và vòng đời

Để minh họa, tạo một controller nhỏ trong test fixture hoặc dùng endpoint nghiệp vụ tương đương. Không cần đưa endpoint debug này vào production.

~~~java
@RestController
@RequestMapping("/probe")
class WebSessionProbeController {

    @PostMapping("/state")
    Mono<String> writeState(
            ServerWebExchange exchange,
            @RequestBody String value) {
        return exchange.getSession()
                .map(session -> {
                    session.getAttributes().put("workflowState", value);
                    return "saved";
                });
    }

    @GetMapping("/state")
    Mono<String> readState(ServerWebExchange exchange) {
        return exchange.getSession()
                .map(session -> {
                    String value =
                            session.getAttribute("workflowState");
                    return value == null ? "EMPTY" : value;
                });
    }

    @PostMapping("/rotate")
    Mono<String> rotate(ServerWebExchange exchange) {
        return exchange.getSession()
                .flatMap(session -> session.changeSessionId()
                        .then(Mono.fromSupplier(session::getId)));
    }

    @PostMapping("/invalidate")
    Mono<ResponseEntity<Void>> invalidate(ServerWebExchange exchange) {
        return exchange.getSession()
                .flatMap(session -> session.invalidate()
                        .thenReturn(ResponseEntity.noContent().build()));
    }
}
~~~

Các handler trả publisher thay vì tự subscribe. Khi response hoàn tất, WebFlux/Spring Session quản lý việc lưu session theo vòng đời request. Trong test có Spring Security, endpoint POST phải đáp ứng authentication/CSRF policy của ứng dụng.

## 7. Dựng WebTestClient với application context đầy đủ

`WebTestClient` là client kiểm thử WebFlux. Để xác minh tích hợp Spring Session, hãy dùng cấu hình nạp đầy đủ application context và filter chain reactive.

Với Spring Boot:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class WebSessionLifecycleIntegrationTest {

    @Autowired
    WebTestClient client;
}
~~~

`RANDOM_PORT` khởi chạy server thực trong test, nhờ đó request đi qua pipeline WebFlux thực tế. Nếu dùng mock web environment, cần bảo đảm WebTestClient được bind vào application context và mọi thành phần WebFlux/Spring Session cần thiết đều được nạp.

Không chỉ tạo `WebTestClient.bindToController(...)` cho bài test cần xác minh repository và cookie resolver. Cách bind trực tiếp controller hữu ích cho test handler đơn vị, nhưng không tự nạp toàn bộ cấu hình session của ứng dụng.

Để kiểm thử persistence, cấu hình repository test phù hợp:

- Redis reactive test instance cho `ReactiveRedisSessionRepository` hoặc repository Redis reactive được dùng.
- Repository reactive in-memory cho kiểm thử wiring và vòng đời cơ bản trong một application context.
- Với nhu cầu chia sẻ giữa instance, hai application context phải dùng cùng backend.

Không dùng repository in-memory để kết luận session tồn tại qua restart hoặc có thể được instance khác đọc.

Lưu ý về JDBC: repository Spring Session JDBC tiêu chuẩn phục vụ mô hình Servlet và API lưu trữ blocking; nó không tự triển khai `ReactiveSessionRepository` để cắm trực tiếp vào WebFlux. Nếu ứng dụng WebFlux cần lưu phiên trong cơ sở dữ liệu quan hệ, cần một repository reactive phù hợp, thường dựa trên R2DBC hoặc một adapter được thiết kế rõ ràng. Không chạy JDBC blocking trực tiếp trên event loop.

## 8. Đọc session cookie từ response

Spring Session WebFlux thường dùng cookie session tên `SESSION` theo cấu hình mặc định, nhưng ứng dụng có thể đổi tên qua `WebSessionIdResolver`. Test phải đọc cookie theo đúng cấu hình thực tế.

Ví dụ lấy cookie:

~~~java
EntityExchangeResult<String> result = client.post()
        .uri("/probe/state")
        .bodyValue("PAYMENT_PENDING")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .returnResult();

ResponseCookie cookie =
        result.getResponseCookies().getFirst("SESSION");

assertThat(cookie).isNotNull();
String sessionId = cookie.getValue();
~~~

`getResponseCookies()` trả cookie đã được parse từ response. Nếu ứng dụng dùng tên cookie khác, thay `SESSION` bằng tên được resolver cấu hình. Không log giá trị session ID trong test report hoặc CI output; chỉ giữ nó trong biến cục bộ của test.

Request kế tiếp gửi lại cookie:

~~~java
client.get()
        .uri("/probe/state")
        .cookie("SESSION", sessionId)
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("PAYMENT_PENDING");
~~~

Đây là ranh giới request quan trọng: test chỉ gửi cookie ID, không giữ object `WebSession` từ request trước.

## 9. Test đầy đủ: ghi trạng thái, đổi ID và khôi phục ở request sau

Ví dụ dưới đây thể hiện một chuỗi request hoàn chỉnh. Có thể tách từng phần thành các test nhỏ hơn nếu muốn cô lập lỗi.

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class WebSessionLifecycleIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void rotatesIdAndRestoresStateOnNextRequest() {
        EntityExchangeResult<String> write = client.post()
                .uri("/probe/state")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("PAYMENT_PENDING")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .returnResult();

        ResponseCookie initialCookie =
                write.getResponseCookies().getFirst("SESSION");
        assertThat(initialCookie).isNotNull();
        String oldId = initialCookie.getValue();

        EntityExchangeResult<String> rotate = client.post()
                .uri("/probe/rotate")
                .cookie("SESSION", oldId)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .returnResult();

        String returnedId = rotate.getResponseBody();
        ResponseCookie rotatedCookie =
                rotate.getResponseCookies().getFirst("SESSION");

        assertThat(returnedId).isNotBlank().isNotEqualTo(oldId);
        assertThat(rotatedCookie).isNotNull();
        assertThat(rotatedCookie.getValue()).isEqualTo(returnedId);

        client.get()
                .uri("/probe/state")
                .cookie("SESSION", returnedId)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("PAYMENT_PENDING");
    }
}
~~~

Đây là mẫu minh họa; test cần dependency Spring Boot Test, WebFlux test support và AssertJ/JUnit theo stack của dự án. Nếu Spring Security bật CSRF, bổ sung cấu hình test reactive CSRF cho các request POST, chẳng hạn dùng `SecurityMockServerConfigurers.csrf()` theo phiên bản Spring Security tương ứng. Nếu endpoint cần đăng nhập, thêm principal test phù hợp.

Không chỉ kiểm tra response body của `/probe/rotate`. Bước GET cuối cùng mới chứng minh thuộc tính cũ được khôi phục từ repository bằng session ID mới.

## 10. Kiểm tra ID cũ không còn khôi phục phiên

Sau khi đổi ID, client không nên tiếp tục dùng ID cũ. Test có thể gửi request với cookie cũ và xác minh dữ liệu không còn truy cập được:

~~~java
client.get()
        .uri("/probe/state")
        .cookie("SESSION", oldId)
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("EMPTY");
~~~

Handler gọi `getSession()` nên request với ID không còn hợp lệ có thể nhận một session mới và trả `EMPTY`. Response có thể phát cookie mới cho session mới này; test không nên nhầm cookie mới đó với phiên cũ.

Tùy repository và semantics của implementation, ID cũ có thể bị xóa ngay khi đổi ID hoặc không còn được ánh xạ tới phiên mới. Điều cần kiểm chứng ở tầng ứng dụng là ID cũ không đọc được dữ liệu của phiên đã xoay. Tránh assert trực tiếp tên key Redis nội bộ nếu không cần.

## 11. Test invalidate và request kế tiếp

Sau khi đã có ID mới, gửi request invalidate:

~~~java
client.post()
        .uri("/probe/invalidate")
        .cookie("SESSION", newId)
        .exchange()
        .expectStatus().isNoContent();
~~~

Endpoint ví dụ trả `204 No Content` một cách tường minh qua `ResponseEntity.noContent()`. Khi test endpoint khác, hãy khớp status expectation với HTTP contract thực tế.

Tiếp theo gửi lại cookie cũ:

~~~java
client.get()
        .uri("/probe/state")
        .cookie("SESSION", newId)
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("EMPTY");
~~~

Kết quả `EMPTY` chứng minh phiên đã invalidate không được khôi phục. Vì `getSession()` có thể tạo session mới, test đang xác minh dữ liệu cũ không còn, không phải khẳng định server không tạo object session mới.

Nếu muốn xác minh response expire cookie, kiểm tra cookie response có `Max-Age=0` hoặc expiration date trong quá khứ theo cách serializer phát. Cookie attribute cụ thể có thể khác giữa resolver và phiên bản; ưu tiên kiểm tra ý nghĩa hết hạn thay vì so sánh toàn bộ header theo chuỗi cứng.

## 12. Khôi phục trạng thái sau request tiếp theo có nghĩa gì?

Có hai trường hợp cần phân biệt:

**Sau khi đổi ID:** đây vẫn là cùng một phiên logic. Thuộc tính như `workflowState` phải được giữ lại và request tiếp theo dùng ID mới phải đọc được giá trị đã lưu.

**Sau khi invalidate:** phiên cũ đã bị vô hiệu hóa. Request tiếp theo có thể tạo phiên mới, nhưng dữ liệu của phiên cũ không được tự khôi phục. Nếu nghiệp vụ cần khôi phục một workflow sau logout hoặc sau khi session hết hạn, phải tải trạng thái từ nguồn nghiệp vụ có thẩm quyền, chẳng hạn database theo `workflowId`, sau khi xác minh quyền truy cập.

Không dùng session repository như kho lưu trữ bền vững cho nghiệp vụ dài hạn. Session có thể hết hạn, bị invalidate, bị xóa hoặc mất theo chính sách vận hành. Một workflow cần tồn tại qua logout, restart hoặc nhiều ngày nên có bản ghi nghiệp vụ riêng.

## 13. Tùy chỉnh WebSessionIdResolver và cookie

`WebSessionIdResolver` quyết định session ID được đọc từ đâu và được phát/xóa thế nào. Với cookie resolver, có thể tùy chỉnh tên cookie và thuộc tính:

~~~java
@Bean
WebSessionIdResolver webSessionIdResolver() {
    CookieWebSessionIdResolver resolver =
            new CookieWebSessionIdResolver();
    resolver.setCookieName("APPSESSION");
    resolver.addCookieInitializer(cookie -> cookie
            .path("/")
            .httpOnly(true)
            .secure(true)
            .sameSite("Lax"));
    return resolver;
}
~~~

Test phải dùng `APPSESSION` thay vì `SESSION`. Cũng cần kiểm tra:

- Cookie ID mới được phát sau `changeSessionId()`.
- Cookie được expire sau `invalidate()`.
- `Path`, `Domain`, `Secure`, `HttpOnly` và `SameSite` đúng với môi trường.
- Reverse proxy TLS termination được cấu hình forwarded headers đúng để cookie `Secure` không bị phát sai.

Không tự đặt cookie session trong handler sau khi gọi `changeSessionId()`. Resolver là nơi chịu trách nhiệm đồng bộ ID với giao thức HTTP.

## 14. Reactive repository và ranh giới lưu dữ liệu

`WebSession` được lưu qua repository reactive. Các thao tác `createSession`, `findById`, `save` và `deleteById` trả về publisher. Test qua HTTP giúp xác minh lifecycle của framework đã subscribe và hoàn tất các thao tác cần thiết trước khi response kết thúc theo semantics của tích hợp.

Không viết test chỉ gọi:

~~~java
repository.save(session).subscribe();
~~~

rồi lập tức đọc lại dữ liệu. Cách này tạo một side effect tách rời, test có thể chạy trước khi lệnh lưu hoàn tất và lỗi có thể không được quan sát.

Nếu cần test repository riêng, nối thao tác bằng `StepVerifier`:

~~~java
StepVerifier.create(repository.save(session))
        .verifyComplete();

StepVerifier.create(repository.findById(session.getId()))
        .assertNext(saved -> assertThat(saved.getId())
                .isEqualTo(session.getId()))
        .verifyComplete();
~~~

Đây là test repository-level; nó không thay thế test HTTP qua `WebSessionManager`, resolver và store. Cả hai lớp kiểm thử có mục tiêu khác nhau.

## 15. Kiểm thử lỗi và tình huống biên

Ngoài luồng thành công, nên có các trường hợp:

| Tình huống | Kết quả mong đợi |
|---|---|
| Request đầu không có cookie | Tạo phiên mới khi handler cần session |
| Cookie chứa ID không tồn tại | Không khôi phục thuộc tính từ một phiên khác |
| Đổi ID thành công | ID mới khác ID cũ; thuộc tính được giữ |
| Gửi lại ID cũ sau rotate | Không truy cập được dữ liệu phiên mới |
| Invalidate thành công | ID cũ không còn truy cập được session |
| Gửi lại cookie sau invalidate | Nhận session mới hoặc trạng thái rỗng theo handler; không thấy dữ liệu cũ |
| Repository lỗi khi lưu | Request thể hiện lỗi theo error handling; không báo thành công giả |
| Redis timeout khi đọc | Lỗi store được phân biệt với “không tìm thấy session” |
| Session hết inactivity timeout | Request sau không khôi phục phiên đã hết hạn |
| Hai instance dùng cùng repository | Instance B đọc được trạng thái đã lưu từ request ở instance A |

Test ID không tồn tại nên kiểm tra qua handler không tự tin cậy giá trị ID. Không phản chiếu ID hoặc thuộc tính nhạy cảm vào response ngoài mục đích test.

## 16. Kiểm thử với Spring Security

Spring Security có thể thay đổi session ID sau xác thực để chống session fixation. Với WebFlux, security filter chain reactive và session authentication repository có thể tham gia vào việc lưu SecurityContext.

Khi test login:

1. Gửi request đăng nhập qua security filter chain thật.
2. Lấy cookie session mới từ response.
3. Xác minh session ID đã thay đổi theo chính sách fixation protection.
4. Gửi request bảo vệ bằng cookie mới.
5. Xác minh principal và quyền được khôi phục.
6. Logout, xác minh session bị invalidate và request tiếp theo không còn authentication.

Không giả định mọi cấu hình authentication đều tạo session. Ứng dụng stateless có thể không dùng session để lưu SecurityContext. Bài test phải phản ánh chính sách thực tế: stateful WebSession hay stateless token.

Với CSRF bật, request POST/DELETE trong test cần token hợp lệ. Giữ security filter chain để kiểm tra logout và session lifecycle trong điều kiện gần production; không tắt security chỉ để test dễ pass.

## 17. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| ID đổi nhưng thuộc tính mất | Test chỉ kiểm tra ID hoặc repository không lưu state đúng | Đọc thuộc tính bằng request kế tiếp với cookie mới |
| Cookie response vẫn chứa ID cũ | Resolver không được gọi đúng lifecycle hoặc test đọc nhầm header | Kiểm tra `WebSessionManager`, resolver và response cookies |
| ID cũ vẫn đọc được trạng thái | Logic đổi ID chưa hoàn tất hoặc test gửi nhầm cookie mới | So sánh ID rõ ràng và test old/new riêng |
| Invalidate nhưng dữ liệu còn truy cập được | Chưa chờ publisher hoàn tất hoặc repository không xóa phiên | Nối `invalidate()` vào reactive chain và kiểm tra request sau |
| Request sau luôn tạo session mới | Cookie name/path/domain không khớp hoặc ID không được gửi | Kiểm tra cookie thực tế và resolver |
| Test chỉ pass trong một context | Dùng repository in-memory cục bộ | Dùng shared Redis reactive store cho test nhiều instance |
| Test đọc trước khi ghi hoàn tất | Gọi `subscribe()` tách rời | Chờ response hoặc dùng `StepVerifier` |
| Session bị mất sau logout nhưng workflow cần tiếp tục | Dữ liệu dài hạn chỉ lưu trong session | Lưu workflow trong database và kiểm tra quyền khi khôi phục |
| Login đổi ID nhưng client vẫn dùng ID cũ | Client không cập nhật cookie response | Dùng cookie jar hoặc gửi cookie mới từ response |

## 18. Checklist kiểm thử vòng đời WebFlux session

- [ ] Dùng full WebFlux application context và `WebTestClient` phù hợp.
- [ ] Có repository reactive test phù hợp với mục tiêu.
- [ ] Request đầu tạo session và nhận cookie session ID.
- [ ] Ghi một thuộc tính để xác định trạng thái phiên.
- [ ] Gọi `changeSessionId()` và đợi publisher hoàn tất.
- [ ] Xác minh response phát ID mới khác ID cũ.
- [ ] Gửi request tiếp theo với cookie mới và đọc lại thuộc tính.
- [ ] Gửi request với ID cũ và xác minh không đọc được trạng thái phiên mới.
- [ ] Gọi `invalidate()` và đợi hoàn tất.
- [ ] Xác minh cookie hết hạn và ID cũ không khôi phục được dữ liệu.
- [ ] Phân biệt session mới sau invalidate với việc phục hồi session cũ.
- [ ] Giữ Spring Security/CSRF filter chain trong test bảo mật.
- [ ] Kiểm thử lỗi repository, timeout và nhiều instance khi cần.
- [ ] Không log session ID hoặc thuộc tính nhạy cảm.

`changeSessionId()` đổi định danh của cùng một WebSession và cần giữ các thuộc tính phiên; `invalidate()` làm phiên cũ mất hiệu lực. Cách kiểm chứng đáng tin cậy là dùng `WebTestClient` gửi request nối tiếp, lấy cookie từ response và gửi lại cookie đó ở request tiếp theo. Khi đổi ID, request mới phải khôi phục được trạng thái bằng ID mới; sau invalidate, request dùng ID cũ không được thấy dữ liệu cũ. Với workflow cần tồn tại lâu hơn session, hãy khôi phục từ kho nghiệp vụ riêng sau khi xác minh quyền.
