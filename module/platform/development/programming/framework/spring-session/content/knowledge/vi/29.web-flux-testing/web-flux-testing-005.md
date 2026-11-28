# Kiểm tra phiên chỉ được phát hành khi đã bắt đầu

Trong Spring WebFlux, việc lấy một `WebSession` không đồng nghĩa phiên mới đã được lưu hoặc session cookie đã được gửi về browser. WebFlux hỗ trợ tạo session theo nhu cầu: request có thể yêu cầu `exchange.getSession()` để đọc hoặc kiểm tra trạng thái, nhưng nếu không bắt đầu phiên và không thêm attribute, session mới có thể không cần được phát hành. Khi phiên được bắt đầu bằng `start()` hoặc được sử dụng theo cách làm nó chuyển sang trạng thái started, WebSession manager mới lưu phiên ở thời điểm response commit và phát session ID cookie theo cấu hình.

Đây là hành vi quan trọng để tránh tạo session không cần thiết cho các request chỉ đọc, endpoint public hoặc các API không cần trạng thái. Nếu test chỉ kiểm tra HTTP status mà không kiểm tra `Set-Cookie`, ứng dụng có thể vô tình phát hành session cho mọi request. Ngược lại, nếu test chỉ dùng `MockWebSession` hoặc mock repository, nó có thể không phát hiện cookie được gửi quá sớm hoặc session không được lưu sau khi đã bắt đầu.

Trong `SPRING_SESSION`, WebFlux dùng `WebSession` và reactive session repository, khác với Servlet `HttpSession`. Bài học này trình bày vòng đời lazy của `WebSession`, điều kiện bắt đầu, thời điểm lưu/phát cookie, cách kiểm tra bằng `WebTestClient`, và cách phân biệt kiểm thử session lifecycle với kiểm thử repository Redis/JDBC.

## 1. `WebSession` được tạo theo nhu cầu

Trong WebFlux, controller hoặc handler có thể lấy session từ `ServerWebExchange`:

```java
exchange.getSession()
```

Phương thức này trả về `Mono<WebSession>`. Vì đây là reactive publisher, session chỉ được resolve khi luồng được subscribe. Nếu request mang session ID cookie hợp lệ, WebSession manager tìm phiên hiện có qua session store. Nếu không có cookie hoặc session không còn hợp lệ, manager có thể tạo một WebSession mới trong bộ nhớ cho request hiện tại.

Một WebSession mới có thể vẫn ở trạng thái chưa bắt đầu. Việc tạo object trong bộ nhớ chỉ giúp request có một nơi tạm thời để đọc/ghi attributes. Nó chưa nhất thiết tạo bản ghi Redis/JDBC và chưa nhất thiết yêu cầu browser giữ một cookie mới.

Phân biệt các thao tác:

| Thao tác | Ý nghĩa | Có nhất thiết phát cookie cho session mới? |
|---|---|---:|
| Gọi `exchange.getSession()` | Lấy hoặc tạo WebSession cho exchange | Không |
| Đọc `session.getAttribute(...)` | Đọc một attribute | Không |
| Kiểm tra `session.isStarted()` | Xem trạng thái started | Không |
| Gọi `session.start()` | Bắt đầu phiên một cách tường minh | Có thể được lưu và phát cookie khi response commit |
| Thêm attribute vào `session.getAttributes()` | Bắt đầu phiên theo semantics của WebSession implementation | Có thể được lưu và phát cookie khi response commit |
| Gọi `session.invalidate()` | Hủy phiên hiện tại | Có thể làm cookie bị hết hạn/xóa ở response |

Với một session mới, chỉ lấy session để kiểm tra không nên làm phát hành session ID. Hành vi cụ thể của một WebSession implementation cần được xác minh qua contract và integration test; `start()` là cách tường minh để biểu đạt rằng ứng dụng thực sự cần một session.

## 2. Vòng đời: lấy, bắt đầu, lưu và phát session ID

Một luồng thông thường trong WebFlux:

1. Request tới WebFlux handler với hoặc không có session cookie.
2. `WebSessionManager` resolve session từ `ServerWebExchange`.
3. Nếu cần, manager tạo một WebSession mới nhưng chưa bắt đầu.
4. Controller/handler đọc attributes hoặc quyết định có cần session state hay không.
5. Khi ứng dụng gọi `start()` hoặc thêm attribute, session chuyển sang trạng thái started.
6. Request handler hoàn tất và response đi tới giai đoạn commit.
7. WebSession manager gọi lưu session thông qua WebSessionStore/repository nếu session cần được lưu.
8. Session ID resolver thêm `Set-Cookie` vào response để browser gửi lại ID ở request sau.

```mermaid
sequenceDiagram
    participant B as Browser
    participant W as WebFlux handler
    participant M as WebSessionManager
    participant R as Reactive session repository
    B->>W: Request không có session cookie
    W->>M: exchange.getSession()
    M-->>W: WebSession mới, chưa started
    W->>W: Đọc trạng thái, không thêm attribute
    W-->>B: Response không phát session cookie
    Note over B,R: Request khác bắt đầu session
    B->>W: POST /session/start
    W->>M: exchange.getSession()
    M-->>W: WebSession mới
    W->>W: session.start(); set attribute
    W-->>M: Handler hoàn tất
    M->>R: Lưu session khi response commit
    R-->>M: Save hoàn tất
    M-->>B: Response + Set-Cookie session ID
```

Điểm phát hành cookie thường gắn với response commit, không phải thời điểm `getSession()` trả về object. Vì vậy, test phải đợi response hoàn tất trước khi đọc `Set-Cookie` hoặc truy vấn repository.

## 3. `start()` và việc thêm attribute

`WebSession` có các phương thức lifecycle như `isStarted()`, `start()`, `save()`, `invalidate()` và `changeSessionId()`. Với session mới, `start()` là cách tường minh để yêu cầu phiên được lưu. Việc thêm attribute vào map attributes cũng là một dấu hiệu sử dụng session và có thể làm session được bắt đầu theo implementation chuẩn.

Ví dụ handler chỉ kiểm tra session, không bắt đầu:

```java
@RestController
@RequestMapping("/test/session")
public class SessionTestController {

    @GetMapping("/inspect")
    public Mono<Map<String, Object>> inspect(ServerWebExchange exchange) {
        return exchange.getSession().map(session -> Map.of(
                "started", session.isStarted(),
                "hasMarker", session.getAttributes().containsKey("marker")));
    }
}
```

Khi request không có cookie, endpoint lấy WebSession mới để kiểm tra. Nó không gọi `start()` và không thêm attribute, do đó session mới không cần được phát hành.

Ví dụ handler bắt đầu session một cách tường minh:

```java
@PostMapping("/start")
public Mono<Map<String, Object>> start(ServerWebExchange exchange) {
    return exchange.getSession().map(session -> {
        session.start();
        session.getAttributes().put("marker", "created");
        return Map.of("started", session.isStarted());
    });
}
```

Nếu mục đích của endpoint là lưu trạng thái vào session, việc bắt đầu session và thêm attribute phải nằm trong reactive pipeline được trả về. Không gọi `subscribe()` thủ công bên trong controller rồi trả response ngay; làm vậy có thể khiến thao tác ghi chạy sau response commit hoặc không được quản lý theo request lifecycle.

### 3.1. Thêm attribute có thể tự bắt đầu phiên

Với WebSession implementation chuẩn, thêm attribute là một cách bắt đầu session. Vì vậy, nếu controller làm như sau:

```java
return exchange.getSession().map(session -> {
    session.getAttributes().put("cartId", cartId);
    return "saved";
});
```

thì session mới có thể được lưu và phát cookie khi response commit. Nếu chỉ đọc attribute hoặc gọi `getSession()` rồi không thay đổi state, session mới vẫn có thể chưa started.

Trong code nghiệp vụ, nên làm rõ ý định: nếu endpoint thực sự cần state, đặt attribute hoặc gọi `start()`; nếu chỉ cần xem trạng thái session hiện tại, không thêm dữ liệu mặc định vô nghĩa chỉ để lấy session ID.

### 3.2. Không nhầm `start()` với lưu tức thì

`start()` đánh dấu session đã bắt đầu. Việc lưu repository và cập nhật response cookie thường được điều phối bởi WebSession manager ở giai đoạn commit. Nếu ứng dụng gọi `start()` nhưng response bị hủy hoặc pipeline kết thúc bằng lỗi trước commit, không nên mặc định rằng session đã được lưu thành công và cookie đã tới browser.

`save()` là thao tác reactive riêng để lưu session theo API; nếu gọi trực tiếp, phải compose `Mono<Void>` vào luồng và xử lý lỗi. Trong ứng dụng WebFlux thông thường, để WebSession manager quản lý save ở response lifecycle giúp giữ thứ tự nhất quán giữa lưu session và ghi response.

## 4. Session cookie chỉ được phát khi cần

Session ID cookie là dữ liệu định danh có tính chất bearer credential: ai sở hữu giá trị hợp lệ có thể được server nhận diện là cùng session, tùy authentication state và policy. Không nên phát cookie cho request không cần state vì nó:

- Tạo session records không cần thiết trong Redis/JDBC.
- Tăng số key và công việc expiration/cleanup.
- Làm browser bắt đầu gửi cookie trong các request tiếp theo.
- Có thể ảnh hưởng caching và làm response trở thành user-specific.
- Tăng bề mặt CSRF nếu cookie được gửi tự động.

Khi session chưa started, response cho request mới không cần `Set-Cookie` session ID. Khi session đã started và lưu thành công, response có thể phát cookie với các thuộc tính theo `WebSessionIdResolver`/cookie configuration.

Cookie name mặc định thường là `SESSION` trong cấu hình Spring Session WebFlux, nhưng cần kiểm tra cấu hình thực tế. Đừng hard-code tên cookie mặc định trong test nếu ứng dụng đã cấu hình tên khác.

Các thuộc tính bảo mật cần kiểm tra riêng:

- `Secure`: cookie chỉ được gửi qua HTTPS.
- `HttpOnly`: JavaScript không đọc trực tiếp cookie.
- `SameSite`: kiểm soát gửi cookie trong cross-site context.
- `Path` và `Domain`: giới hạn host/path nhận cookie.
- `Max-Age`/`Expires`: thời hạn cookie phía browser; không đồng nhất với TTL session repository.

Không dùng việc “không phát cookie khi chưa started” thay cho các thuộc tính cookie an toàn. Khi session được phát hành, cookie vẫn cần được bảo vệ theo threat model của ứng dụng.

## 5. Kiểm tra trạng thái session bằng WebTestClient

`WebTestClient` là công cụ chính để kiểm thử WebFlux endpoint theo kiểu reactive. Nó có thể gửi request, nhận response, kiểm tra status/header/cookie/body và chờ reactive exchange hoàn tất mà không cần tự subscribe trong controller.

Một test cho request chỉ resolve session:

```java
@SpringBootTest
@AutoConfigureWebTestClient
class WebSessionStartTest {

    @Autowired
    WebTestClient client;

    @Test
    void doesNotIssueCookieWhenSessionIsOnlyInspected() {
        EntityExchangeResult<byte[]> result = client.get()
                .uri("/test/session/inspect")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.started").isEqualTo(false)
                .jsonPath("$.hasMarker").isEqualTo(false)
                .returnResult();

        assertThat(result.getResponseHeaders()
                .getFirst(HttpHeaders.SET_COOKIE)).isNull();
    }
}
```

Test cần dùng client/request không mang cookie từ lần gọi trước. `WebTestClient` không nhất thiết giữ cookie jar tự động giữa các request độc lập, nhưng nếu dùng client có cookie store hoặc custom filter thì hãy tạo client mới/clear cookie để bảo đảm test đang xét một browser mới. Test trên giả định endpoint không phát cookie nào khác; nếu ứng dụng có CSRF/tracking cookie, hãy lọc danh sách `Set-Cookie` theo đúng session cookie name thay vì yêu cầu toàn bộ header vắng mặt.

Test phát hành cookie sau khi bắt đầu session:

```java
@Test
void issuesCookieAfterSessionIsStarted() {
    EntityExchangeResult<byte[]> result = client.post()
            .uri("/test/session/start")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .returnResult();

    String responseBody = new String(
            result.getResponseBody(), StandardCharsets.UTF_8);
    assertThat(responseBody).contains("\"started\":true");

    String setCookie = result.getResponseHeaders()
            .getFirst(HttpHeaders.SET_COOKIE);
    assertThat(setCookie).startsWith("SESSION=");
}
```

Đoạn test dùng `EntityExchangeResult` để kiểm tra body và header của cùng một response. Bổ sung import `StandardCharsets`, `HttpHeaders` và `EntityExchangeResult` trong test class. Cookie name `SESSION` phải khớp với `WebSessionIdResolver` của ứng dụng.

## 6. Ví dụ endpoint test tối thiểu

Một controller test-only có thể cung cấp ba endpoint:

```java
@RestController
@RequestMapping("/test/session")
class WebSessionProbeController {

    @GetMapping("/inspect")
    Mono<Map<String, Object>> inspect(ServerWebExchange exchange) {
        return exchange.getSession().map(session -> Map.of(
                "started", session.isStarted(),
                "hasMarker", session.getAttributes().containsKey("marker")));
    }

    @PostMapping("/start")
    Mono<Map<String, Object>> start(ServerWebExchange exchange) {
        return exchange.getSession().map(session -> {
            session.start();
            session.getAttributes().put("marker", "created");
            return Map.of("started", session.isStarted());
        });
    }

    @GetMapping("/marker")
    Mono<Map<String, Object>> marker(ServerWebExchange exchange) {
        return exchange.getSession().map(session -> {
            Object marker = session.getAttribute("marker");
            return Map.of("marker", marker == null ? "missing" : marker);
        });
    }
}
```

Đặt các endpoint này trong test configuration hoặc profile test; không nên để endpoint quản trị/test công khai trong production. Nếu POST bị Spring Security CSRF bảo vệ, test cần gửi CSRF token hoặc cấu hình test security có chủ đích. Không tắt security toàn cục chỉ để test cookie.

## 7. Xác minh session được lưu và đọc lại qua cookie

Kiểm tra `Set-Cookie` mới chứng minh server đã phát session ID. Để chứng minh repository thực sự lưu session, cần gửi cookie đó trong request tiếp theo và xác minh attribute được khôi phục.

Ví dụ lấy cookie từ response đầu:

```java
@Test
void readsStartedSessionOnNextRequest() {
    EntityExchangeResult<byte[]> result = client.post()
            .uri("/test/session/start")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .returnResult();

    String setCookie = result.getResponseHeaders()
            .getFirst(HttpHeaders.SET_COOKIE);
    assertThat(setCookie).isNotNull();
    assertThat(setCookie).startsWith("SESSION=");

    String cookiePair = setCookie.split(";", 2)[0];
    String sessionId = cookiePair.substring("SESSION=".length());

    client.get()
            .uri("/test/session/marker")
            .cookie("SESSION", sessionId)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.marker").isEqualTo("created");
}
```

Đây là ví dụ đơn giản cho cookie name `SESSION` và một `Set-Cookie` header. Với cookie custom, giá trị URL-encoded hoặc nhiều `Set-Cookie` headers, hãy chọn đúng cookie theo tên bằng `getResponseHeaders().get(HttpHeaders.SET_COOKIE)` và xử lý thuộc tính cookie cẩn thận. Không gửi toàn bộ `Set-Cookie` response header làm `Cookie` request header; chỉ gửi cặp name/value.

Nếu response có cookie nhưng request kế tiếp không đọc được marker, kiểm tra:

- Session đã được lưu trước khi response hoàn tất chưa.
- Cookie name/value được gửi lại chính xác chưa.
- `WebSessionIdResolver` có dùng cùng cookie name/encoding không.
- Reactive session repository có dùng đúng Redis namespace/JDBC tables không.
- Serializer có đọc được attributes không.
- Test có vô tình tạo client/request đi tới application context khác không.

## 8. Dùng Spring Session reactive repository thật

WebFlux dùng reactive session abstraction. `WebSessionManager` làm việc với `WebSessionStore`; Spring Session cung cấp tích hợp để lưu WebSession qua reactive session repository, ví dụ Redis. Với Redis, cấu hình thường dùng `@EnableRedisWebSession` và reactive Redis connection factory tương ứng. Với các phiên bản Spring Session hỗ trợ JDBC reactive hay custom reactive repository, phải xác minh repository cụ thể; không thay `ReactiveSessionRepository` bằng JDBC blocking repository trong event loop.

Ví dụ cấu hình Redis WebSession:

```java
@Configuration
@EnableRedisWebSession(
        redisNamespace = "portal:web-session",
        maxInactiveIntervalInSeconds = 1800)
class ReactiveSessionConfiguration {
}
```

Tên annotation/thuộc tính và auto-configuration phụ thuộc Spring Session version. Spring Session Redis reactive cần `ReactiveRedisConnectionFactory` tương thích. Không dùng cấu hình Servlet `@EnableRedisHttpSession` cho WebFlux; annotation đó cấu hình `HttpSession` trong Servlet stack.

Trong test, có thể dùng Redis Testcontainers để kiểm tra:

- Session chưa started không tạo record bền vững hoặc cookie.
- Session started được lưu sau response commit.
- Request tiếp theo với cookie đọc được attributes.
- Invalidate xóa session và làm cookie hết hạn theo resolver.
- Session timeout/TTL được đặt và hết hạn theo repository.
- Hai application instances dùng cùng namespace có thể đọc cùng session nếu đây là thiết kế mong muốn.

Nếu test chỉ cần kiểm tra WebSession lifecycle, có thể dùng in-memory/mock store. Nhưng phải có ít nhất một integration test với repository thực để xác minh behavior persistence và serialization.

## 9. Kiểm tra repository trực tiếp bằng StepVerifier

Reactive repository trả về `Mono`/`Flux`; unit test không nên gọi `.block()` trong reactive pipeline của ứng dụng. Trong test, có thể dùng `StepVerifier` để xác minh publisher hoàn tất và trả kết quả.

Ví dụ khái quát với `ReactiveSessionRepository`; compose việc tạo, lưu và đọc thành một publisher rồi dùng một `StepVerifier`:

```java
StepVerifier.create(repository.createSession()
        .flatMap(session -> {
            session.setAttribute("test.marker", "ready");
            return repository.save(session)
                    .then(repository.findById(session.getId()));
        }))
    .assertNext(loaded -> assertThat(
            loaded.getAttribute("test.marker")).isEqualTo("ready"))
    .verifyComplete();
```

Tên kiểu generic và API repository cần khớp phiên bản Spring Session. Test repository trực tiếp không kiểm tra WebSession manager có phát cookie hay không; đó là trách nhiệm của HTTP integration test.

## 10. Test không phát cookie khi chỉ resolve session

Để test đúng điều kiện “chỉ phát hành khi đã bắt đầu”, hãy dùng request mới không có session cookie và endpoint chỉ resolve session:

```java
@Test
void lookupAloneDoesNotCreateSessionCookie() {
    client.get()
            .uri("/test/session/inspect")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().doesNotExist(HttpHeaders.SET_COOKIE);
}
```

Có thể kiểm tra body xác nhận `started=false`. Nhưng assertion header mới trực tiếp chứng minh response không phát session cookie. Nếu ứng dụng có cookie khác như CSRF cookie hoặc tracking cookie, không nên khẳng định toàn bộ `Set-Cookie` header vắng mặt; hãy kiểm tra chính xác session cookie name bằng `expectCookie().doesNotExist("SESSION")` hoặc lọc `Set-Cookie` theo tên.

Test cần dùng một browser context sạch. Nếu request mang cookie của một session đã tồn tại, server có thể nhận diện session cũ và response behavior khác với một session mới chưa started. Không trộn test “session mới chưa started” với test “đọc session hiện có”.

## 11. Test phát cookie sau `start()`

Để xác minh session chỉ được phát sau khi bắt đầu, test nên so sánh hai response độc lập:

| Trường hợp | Endpoint | Kết quả cần kiểm tra |
|---|---|---|
| Resolve nhưng không bắt đầu | `GET /test/session/inspect` | `started=false`, không có session cookie mới |
| Bắt đầu tường minh | `POST /test/session/start` | `started=true`, response có session cookie |
| Thêm attribute | Endpoint ghi marker vào attributes | Session được lưu và cookie được phát |
| Đọc lại bằng cookie | `GET /test/session/marker` với cookie từ response trước | Marker được khôi phục |
| Invalidate | Endpoint hủy session | Session không còn được khôi phục; cookie được hết hạn theo resolver |

Ví dụ kiểm tra cookie theo tên:

```java
client.post()
        .uri("/test/session/start")
        .exchange()
        .expectStatus().isOk()
        .expectCookie().exists("SESSION");
```

Nếu test cần kiểm tra cookie flags, có thể dùng cookie assertions tương ứng hoặc đọc `Set-Cookie` header và xác minh `HttpOnly`, `Secure`, `SameSite`, `Path` và `Max-Age`. Các thuộc tính mong đợi phải lấy từ cấu hình ứng dụng, không áp đặt một giá trị giống nhau cho mọi deployment.

## 12. Kiểm tra `save()` và response commit

WebFlux là reactive, vì vậy việc gọi method không có nghĩa thao tác đã chạy xong. `WebSession.save()` trả về `Mono<Void>`. Nếu ứng dụng gọi trực tiếp, phải compose publisher đó:

```java
return exchange.getSession()
        .flatMap(session -> {
            session.start();
            session.getAttributes().put("marker", "value");
            return session.save();
        })
        .then(ServerResponse.ok().build());
```

Trong phần lớn controller, không cần tự gọi `save()` vì WebSession manager tự lưu khi response commit. Ví dụ trên chỉ minh họa rằng nếu gọi `save()` tường minh thì phải nối nó vào reactive chain. Không gọi `session.save().subscribe()` rồi tiếp tục trả response; điều đó tách thao tác lưu khỏi request lifecycle và có thể làm response phát cookie không đồng bộ với persistence.

Khi test commit behavior, hãy chờ `.exchange()` hoàn tất trước khi kiểm tra cookie hoặc repository. Nếu save lỗi, response có thể kết thúc bằng lỗi thay vì phát cookie hợp lệ. Có thể thêm test datastore unavailable để xác minh ứng dụng không trả thành công giả khi session không lưu được, theo error policy của ứng dụng.

## 13. Phân biệt session mới, session hiện có và session invalid

Ba trạng thái cần test riêng:

1. **Không có cookie:** manager có thể tạo WebSession mới chưa started. Nếu không sử dụng state, không phát cookie.
2. **Cookie hợp lệ:** manager khôi phục session đã lưu. Session đã started; controller đọc attributes. Không nhất thiết phải phát một cookie mới nếu ID không đổi.
3. **Cookie hết hạn/không hợp lệ:** manager không khôi phục được session tương ứng và có thể tạo WebSession mới. Không được coi cookie cũ là xác thực hợp lệ.

Nếu endpoint chỉ đọc session, test với cookie hợp lệ có thể không phát `Set-Cookie` mới nhưng vẫn đọc được session hiện có. Điều đó khác với test request không có cookie và session mới chưa started.

Không kiểm tra “không có `Set-Cookie`” như bằng chứng duy nhất rằng server không tạo session object. Muốn xác minh lazy lifecycle, kết hợp body/state assertion, cookie assertion và repository assertion phù hợp.

## 14. Invalidate và cookie expiration

Khi gọi `session.invalidate()`, session bị đánh dấu invalid và repository cần xóa phiên. Session ID resolver có thể thêm cookie hết hạn vào response để browser ngừng gửi ID cũ.

Ví dụ endpoint:

```java
@PostMapping("/invalidate")
Mono<Void> invalidate(ServerWebExchange exchange) {
    return exchange.getSession()
            .flatMap(WebSession::invalidate);
}
```

API `invalidate()` trả `Mono<Void>` trong WebFlux. Hãy trả publisher này về framework để quá trình xóa session được hoàn tất trước khi response kết thúc.

Test nên xác minh:

- Request invalidate hoàn tất theo status mong đợi.
- Cookie session được xóa/hết hạn với `Max-Age=0` hoặc `Expires` trong quá khứ theo resolver.
- Request tiếp theo dùng cookie cũ không khôi phục được session đã xóa.
- Nếu request tiếp theo không bắt đầu session mới, nó không phát một session cookie mới.

Đừng yêu cầu cookie “không tồn tại” trong response logout; hành vi đúng thường là gửi cookie expiration để browser xóa cookie đã lưu.

## 15. Kiểm tra session timeout và TTL

Session timeout của repository và cookie lifetime là hai cấu hình liên quan nhưng khác nhau. WebSession có `maxIdleTime`/max inactive interval theo API/version; repository lưu TTL hoặc expiration tương ứng. Cookie có thể là session cookie không có `Max-Age`, hoặc persistent cookie có tuổi thọ cụ thể.

Test timeout nên:

1. Cấu hình idle timeout ngắn trong test profile.
2. Bắt đầu session và lưu marker.
3. Xác minh cookie được phát.
4. Chờ quá thời gian hết hạn hoặc điều khiển clock nếu implementation hỗ trợ.
5. Gửi request với cookie cũ.
6. Xác minh session không còn được khôi phục và attribute không còn.

Tránh `Thread.sleep` dài trong unit test. Có thể dùng clock controllable nếu repository hỗ trợ, hoặc integration test có timeout ngắn với polling giới hạn. Redis expiration có thể không được dọn đúng ngay tại mili-giây TTL bằng nhau; test nên có khoảng đệm và phân biệt TTL hết hạn với key cleanup/notification.

## 16. Kiểm tra WebSession trong WebFlux Security

Spring Security WebFlux có thể lưu `SecurityContext` trong `WebSession` tùy `ServerSecurityContextRepository` và session policy. Nếu ứng dụng dùng session-based login, một request đã xác thực có thể làm session started và response phát cookie. Nếu ứng dụng cấu hình stateless, việc có `WebSession` không đồng nghĩa SecurityContext được lưu trong đó.

Test security nên phân biệt:

- Anonymous request chỉ resolve WebSession nhưng không bắt đầu: không phát session cookie mới nếu không có thành phần khác khởi tạo session.
- Form/OIDC login thành công: security context được lưu và local session cookie được phát.
- Request tiếp theo với cookie: principal được khôi phục.
- Logout: context/session bị xóa và cookie được hết hạn.
- CSRF: POST được bảo vệ theo cấu hình reactive CSRF repository.

Spring Security test support cho WebFlux có `SecurityMockServerConfigurers`, ví dụ `mockUser()` và `csrf()`. Các postprocessor này tạo security context cho test; chúng không chứng minh login protocol hoặc session repository persistence. Để kiểm tra session sau login, dùng flow integration thực tế và cookie từ response.

## 17. Test reactive đúng cách

Không gọi `.block()` hoặc `.subscribe()` trong controller/service reactive chỉ để làm test dễ hơn. Hãy trả `Mono`/`Flux` và để WebFlux subscribe ở đúng lifecycle. Trong unit test, dùng `StepVerifier`; trong HTTP test, dùng `WebTestClient`.

Ví dụ kiểm tra một publisher có phát trạng thái started:

```java
StepVerifier.create(sessionService.startAndMark())
        .assertNext(state -> assertThat(state.started()).isTrue())
        .verifyComplete();
```

Ví dụ này giả định service trả về một publisher chứa kết quả. Test thực tế nên tránh truy cập session qua static thread-local hoặc giữ `WebSession` sau khi request kết thúc. WebSession thuộc về request lifecycle; không dùng object đó trong background thread sau response commit.

### 17.1. Không chạy blocking Redis/JDBC trong event loop

Reactive session repository cần reactive I/O. Nếu dùng JDBC blocking repository trong WebFlux event loop, request có thể bị block và làm giảm throughput. Nếu datastore/driver không có reactive support, cần chạy blocking work trên scheduler phù hợp và đánh giá lại kiến trúc; không bọc blocking call vào `Mono.just(...)` rồi coi nó là non-blocking.

Unit test service reactive có thể dùng mock publisher; integration test phải xác minh repository implementation thực sự phù hợp với reactive runtime.

## 18. Phân biệt in-memory mock với repository thật

| Phương pháp | Xác minh được | Không tự xác minh được |
|---|---|---|
| Unit test `WebSession`/fake store | Logic quyết định start, attribute và invalidate | Cookie resolver, Redis/JDBC persistence thật |
| `MockServerWebExchange` | Handler đọc/ghi exchange/session theo test setup | HTTP response cookie lifecycle hoàn chỉnh nếu không dựng manager/store phù hợp |
| `WebTestClient` với application context | WebFlux handler, WebSession manager và response cookie trong cấu hình test | Redis durability/cluster behavior nếu store là in-memory |
| `WebTestClient` + Redis Testcontainers | Cookie, filter/web handler, reactive repository persistence | Mọi hành vi production cluster/failover nếu test chỉ có một Redis node |
| Multi-instance integration test | Session được chia sẻ giữa nodes theo cookie/repository config | IdP/Browser behavior thực tế nếu không có end-to-end browser test |

Một test dùng mock session store có thể kiểm tra `start()` được gọi nhưng không chứng minh Spring Session Redis phát cookie đúng. Một test `WebTestClient` với in-memory store có thể kiểm tra HTTP lifecycle nhưng không chứng minh serialization hoặc TTL của Redis.

## 19. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Request chỉ gọi `getSession()` nhưng vẫn phát cookie | Code khác thêm attribute hoặc gọi `start()`; filter/security component bắt đầu session | Tìm tất cả session mutations và xác định thành phần tạo state |
| Session đã start nhưng response không có cookie | Response bị lỗi/hủy trước commit, resolver không được cấu hình hoặc save thất bại | Kiểm tra reactive chain, response commit, resolver và repository logs |
| Cookie có nhưng request sau không thấy session | Repository không lưu, namespace sai, cookie không được gửi hoặc serializer lỗi | Kiểm tra Set-Cookie, request Cookie, repository và serializer |
| Test luôn thấy cookie dù endpoint không mutate | Client tái sử dụng cookie cũ hoặc fixture đã tạo session | Dùng request/browser context mới và xóa cookie trước test |
| Test không thấy cookie sau `start()` | Cookie name khác, response commit chưa hoàn tất hoặc session save error | Kiểm tra cookie configuration và chờ exchange hoàn tất |
| Attribute không được lưu | Code không set lại object theo SaveMode hoặc session chưa started | Thêm attribute tường minh và xác minh `isStarted()` |
| `Mono` test không chạy | Publisher chưa subscribe/compose vào response | Trả publisher về WebFlux hoặc dùng StepVerifier trong test |
| Gọi `subscribe()` trong controller gây flaky test | Side effect tách khỏi request lifecycle | Compose thao tác vào chain, không tự subscribe |
| Logout không xóa cookie | Invalidate publisher không được compose hoặc resolver không expire cookie | Trả `session.invalidate()` và kiểm tra response cookie expiration |
| Test timeout không ổn định | Dùng sleep ngắn hơn TTL/Redis cleanup delay | Dùng timeout ngắn có khoảng đệm, polling giới hạn hoặc clock test |
| WebFlux event loop bị block | Dùng JDBC/blocking repository trong reactive path | Dùng reactive repository hoặc cô lập blocking work đúng scheduler |

## 20. Ma trận kiểm thử cần có

| Kịch bản | Input | Assertion chính |
|---|---|---|
| Request mới chỉ resolve session | Không có cookie, gọi `getSession()` | Session mới chưa started; không có session `Set-Cookie` |
| Đọc attribute không tồn tại | Không có cookie, chỉ `getAttribute` | Không bắt đầu phiên và không phát cookie |
| Explicit start | Không có cookie, gọi `start()` | `isStarted=true`; cookie được phát sau response commit |
| Thêm attribute | Không có cookie, `attributes.put` | Session started, lưu và phát cookie theo implementation |
| Cookie round-trip | Gửi lại cookie từ response start | Repository khôi phục attribute |
| Existing session read-only | Gửi cookie hợp lệ, chỉ đọc | Attribute tồn tại; không bắt buộc phát cookie mới nếu ID không đổi |
| Invalid cookie | Gửi ID không tồn tại/hết hạn | Không khôi phục session cũ; request xử lý như session mới |
| Invalidate | Cookie hợp lệ, gọi invalidate | Repository xóa session; response expire cookie |
| Save error | Datastore unavailable khi commit | Request không báo thành công giả; lỗi được xử lý theo policy |
| TTL expiration | Chờ quá idle timeout | Cookie cũ không khôi phục session đã hết hạn |
| Security login | Thực hiện login flow | SecurityContext lưu trong local WebSession và cookie được phát |
| Stateless endpoint | Security stateless, không mutate session | Không phát session cookie ngoài ý muốn |
| Hai instance | Start ở A, đọc cookie ở B | B khôi phục session nếu dùng chung reactive repository/namespace |

Test “existing session read-only” cần phân biệt việc không phát cookie mới với việc không có cookie. Browser đã gửi cookie trong request; response có thể không cần gửi lại `Set-Cookie` nếu session ID không thay đổi.

## 21. Quy trình kiểm thử thực tế

Khi kiểm tra WebFlux chỉ phát hành session sau khi bắt đầu:

1. Xác nhận ứng dụng đang dùng WebFlux `WebSession`, không phải Servlet `HttpSession`.
2. Dùng request mới không có session cookie để bắt đầu test.
3. Tạo endpoint/test handler chỉ gọi `exchange.getSession()` và đọc `isStarted()`.
4. Xác minh response không có session cookie theo đúng cookie name.
5. Tạo endpoint khác gọi `session.start()` hoặc thêm attribute.
6. Chờ response commit qua `WebTestClient.exchange()` rồi xác minh session cookie được phát.
7. Gửi lại đúng cookie trong request tiếp theo và xác minh attribute được khôi phục.
8. Lặp lại với reactive repository thật như Redis để kiểm tra persistence/serialization.
9. Test invalidate, cookie expiration, TTL và datastore save failure.
10. Nếu dùng Spring Security, kiểm tra login/logout/CSRF riêng; không suy ra security behavior từ một test session đơn giản.
11. Nếu chạy nhiều instance, tạo session ở node A và khôi phục ở node B bằng cùng cookie.
12. Theo dõi response headers và repository state để phân biệt lỗi start, save, cookie resolver và datastore.

`WebSession` trong WebFlux được thiết kế để tạo theo nhu cầu. Chỉ gọi `exchange.getSession()` để đọc hoặc kiểm tra trạng thái không nên tự phát hành session cookie cho một phiên mới chưa bắt đầu. Khi ứng dụng gọi `start()` hoặc thêm attribute, WebSession manager có thể lưu session ở response commit và gửi session ID về browser. Kiểm thử đúng cần quan sát cả `isStarted()`, `Set-Cookie`, cookie round-trip và repository state; dùng `WebTestClient` cho HTTP lifecycle, `StepVerifier` cho reactive publisher và Redis/JDBC integration test cho persistence thật.
