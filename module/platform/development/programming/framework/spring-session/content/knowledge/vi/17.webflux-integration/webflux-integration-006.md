# Tạo phiên, trạng thái started và thời điểm phát hành định danh

Trong Spring WebFlux, session được biểu diễn bằng WebSession và được truy cập theo kiểu reactive. Khi một request gọi exchange.getSession(), WebFlux cung cấp một WebSession hiện có hoặc tạo một đối tượng session mới. Việc có đối tượng WebSession trong request chưa có nghĩa dữ liệu đã được lưu vào repository hoặc session ID đã được gửi tới trình duyệt.

Điểm quan trọng là trạng thái started. Một session mới thường ở trạng thái chưa started. Khi ứng dụng gọi start() hoặc thêm thuộc tính vào session, session chuyển sang trạng thái cần được duy trì. WebSessionManager lưu session ở giai đoạn hoàn tất response và dùng WebSessionIdResolver để phát hành định danh qua cookie hoặc header. Vì vậy, thời điểm phát hành ID cho client gắn với quá trình commit response, không đơn giản là thời điểm gọi getSession().

Bài này giải thích vòng đời tạo WebSession, ý nghĩa của isStarted(), cách thay đổi thuộc tính, thời điểm lưu và phát session ID, cách đổi hoặc thu hồi ID, cùng cách kiểm thử hành vi này trong ứng dụng reactive nhiều instance.

## 1. WebSession trong WebFlux khác HttpSession như thế nào?

Ứng dụng Spring MVC trên Servlet sử dụng HttpSession và thường tích hợp Spring Session qua SessionRepositoryFilter. Ứng dụng WebFlux sử dụng WebSession và WebSessionManager. Hai abstraction có mục tiêu tương tự nhưng thuộc hai mô hình request khác nhau.

| Thành phần | Servlet / Spring MVC | WebFlux |
|---|---|---|
| Abstraction session | HttpSession | WebSession |
| Request | HttpServletRequest | ServerWebExchange |
| Repository | SessionRepository | ReactiveSessionRepository |
| Quản lý session trong request | SessionRepositoryFilter | WebSessionManager |
| Định danh client | HttpSessionIdResolver | WebSessionIdResolver |
| Truy cập session | request.getSession() | exchange.getSession() trả Mono<WebSession> |
| Mô hình xử lý | Servlet thread-per-request truyền thống | Reactive, không chặn event loop |

WebSession cung cấp các thao tác như:

- getId(): lấy định danh hiện tại của session.
- getAttributes(): truy cập map thuộc tính session.
- isStarted(): kiểm tra session đã được bắt đầu để duy trì hay chưa.
- start(): đánh dấu session cần được duy trì.
- isExpired(): kiểm tra session đã hết hạn hay chưa.
- save(): lưu session khi cần.
- invalidate(): vô hiệu hóa session.
- changeSessionId(): thay đổi định danh session.
- getCreationTime(), getLastAccessTime() và getMaxIdleTime(): đọc metadata vòng đời.
- setMaxIdleTime(Duration): đặt thời gian không hoạt động tối đa.

Các thao tác repository và một số thao tác vòng đời trả về Mono hoặc được thực hiện trong reactive pipeline. Không gọi block() trong event loop để chờ session, Redis hoặc repository hoàn tất. Hãy nối các thao tác bằng map, flatMap, then và các toán tử Reactor phù hợp.

## 2. Các thành phần tham gia tạo và lưu WebSession

Một luồng WebFlux có các thành phần chính:

| Thành phần | Trách nhiệm |
|---|---|
| ServerWebExchange | Đại diện request và response hiện tại; cung cấp getSession() |
| WebSessionManager | Tìm session theo định danh request hoặc tạo session mới |
| WebSessionIdResolver | Đọc ID từ request và ghi/xóa ID trong response |
| WebSessionStore | Tạo, tải và xóa WebSession |
| ReactiveSessionRepository | Lưu trữ session theo API reactive |
| Session implementation | Giữ ID, metadata, thuộc tính và trạng thái started |

Spring Session cung cấp tích hợp reactive để nối WebSession với ReactiveSessionRepository. Ví dụ với Redis, cấu hình WebFlux dùng @EnableRedisWebSession và repository reactive tương ứng. Ứng dụng không cần tự đọc cookie rồi tự viết lệnh Redis trong controller.

Sơ đồ vòng đời:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant M as WebSessionManager
    participant R as WebSessionIdResolver
    participant S as WebSessionStore
    participant P as ReactiveSessionRepository
    C->>M: Request mang cookie/header nếu có
    M->>R: Đọc session ID
    R-->>M: ID hoặc không có ID
    M->>S: Tìm session hoặc tạo session mới
    S->>P: findById / createSession
    P-->>S: Session hoặc session mới
    S-->>M: WebSession
    M-->>C: Chuyển WebSession vào request pipeline
    Note over M,P: Trước khi response commit
    M->>P: Lưu session nếu started
    P-->>M: Hoàn tất lưu
    M->>R: Phát session ID
    R-->>C: Set-Cookie hoặc response header
~~~

Sơ đồ mô tả thứ tự khái niệm. Chi tiết implementation có thể khác theo phiên bản và repository, nhưng nguyên tắc cần nhớ là ID được gửi cho client khi session được lưu và resolver ghi định danh vào response.

## 3. getSession() tạo hoặc lấy session như thế nào?

Trong WebFlux, ServerWebExchange.getSession() trả về Mono<WebSession>. Khi subscribe vào pipeline, WebSessionManager tìm ID từ request thông qua resolver. Nếu ID hợp lệ và repository tìm thấy session, request sử dụng session đó. Nếu không có ID hoặc session không còn tồn tại, manager có thể tạo một WebSession mới cho request.

Ví dụ:

~~~java
@GetMapping("/session/status")
public Mono<Map<String, Object>> status(ServerWebExchange exchange) {
    return exchange.getSession()
            .map(session -> Map.of(
                    "started", session.isStarted(),
                    "hasLocale",
                    session.getAttributes().containsKey("app.locale")
            ));
}
~~~

Đoạn code này lấy một WebSession để kiểm tra trạng thái. Nếu request chưa có session, manager có thể tạo một đối tượng mới. Tuy nhiên, chỉ gọi getSession() không đồng nghĩa ứng dụng đã yêu cầu duy trì session mới. Nếu session mới vẫn chưa started và không có thuộc tính, manager có thể bỏ qua việc lưu nó và không phát session ID.

Với session đã tồn tại, session được tải từ repository và có trạng thái hoạt động. Khi request sử dụng session hiện có, metadata như thời điểm truy cập gần nhất có thể được cập nhật theo vòng đời repository.

Nếu endpoint không cần session, đừng gọi getSession() chỉ để lấy một ID hoặc ghi log. Việc tạo và tải session không cần thiết có thể gây I/O và làm tăng tải repository.

## 4. Trạng thái started có ý nghĩa gì?

Một WebSession mới thường được tạo ở trạng thái chưa started. Trạng thái này cho phép framework tạo một đối tượng session tạm trong request mà chưa phải lưu dữ liệu và phát định danh cho client.

Session chuyển sang started khi ứng dụng chủ động gọi start() hoặc thêm thuộc tính vào map session. Việc thêm thuộc tính biểu thị ứng dụng muốn duy trì trạng thái qua các request.

Ví dụ:

~~~java
@GetMapping("/session/start")
public Mono<Map<String, Object>> start(ServerWebExchange exchange) {
    return exchange.getSession()
            .map(session -> {
                session.start();

                return Map.of(
                        "started", session.isStarted(),
                        "hasPreference",
                        session.getAttributes().containsKey("app.preference")
                );
            });
}
~~~

Sau start(), session được đánh dấu cần duy trì. Khi response được hoàn tất, WebSessionManager sẽ lưu session và phát ID qua resolver nếu response chưa commit.

Có thể bắt đầu session bằng cách thêm thuộc tính:

~~~java
@GetMapping("/session/preference")
public Mono<String> savePreference(ServerWebExchange exchange) {
    return exchange.getSession()
            .map(session -> {
                session.getAttributes().put("app.locale", "vi-VN");
                return "Preference saved";
            });
}
~~~

Map thuộc tính của WebSession được quản lý để thay đổi thuộc tính có thể làm session chuyển sang started. Vì vậy, thêm thuộc tính thường là cách tự nhiên để bắt đầu session. Nếu chỉ cần tạo session rỗng theo một yêu cầu rõ ràng, gọi start() tường minh.

### Chưa started không có nghĩa là không có đối tượng

Cần phân biệt ba khái niệm:

- **Đối tượng session tồn tại trong pipeline:** exchange.getSession() đã trả WebSession.
- **Session started:** ứng dụng đã yêu cầu duy trì session, ví dụ bằng start() hoặc thêm thuộc tính.
- **Session đã lưu và ID đã được phát:** repository hoàn tất lưu và resolver ghi ID vào response.

Một session mới có thể tồn tại trong bộ nhớ của request nhưng chưa được lưu. Trạng thái started là tín hiệu về ý định duy trì, còn việc lưu và phát ID diễn ra sau đó trong vòng đời response.

## 5. Khi nào session ID thực sự được phát cho client?

Đây là điểm dễ hiểu nhầm nhất khi làm việc với WebFlux.

WebSessionManager thường đăng ký thao tác lưu session trước khi response được commit. Khi response bắt đầu commit, manager kiểm tra trạng thái session:

- Nếu session started và còn hợp lệ, manager lưu session qua WebSessionStore/repository, sau đó gọi WebSessionIdResolver để ghi ID vào response.
- Nếu session mới chưa started, manager không cần lưu session đó và không phát ID mới.
- Nếu session đã hết hạn hoặc bị vô hiệu hóa, manager xử lý xóa session và resolver có thể phát cookie hết hạn để client ngừng gửi ID cũ.

Với CookieWebSessionIdResolver, ID được phát trong header Set-Cookie. Với HeaderWebSessionIdResolver, ID được phát qua header HTTP đã cấu hình. Việc phát ID là một thao tác response, nên phải diễn ra trước khi response commit.

Có thể mô tả theo thời gian:

| Thời điểm | Điều xảy ra | Client đã nhận ID chưa? |
|---|---|---|
| T0 | Request tới, resolver đọc cookie/header | Chưa |
| T1 | getSession() tải hoặc tạo WebSession | Chưa |
| T2 | Ứng dụng gọi start() hoặc thêm thuộc tính | Chưa |
| T3 | Handler hoàn tất và response chuẩn bị commit | Chưa |
| T4 | Manager lưu session vào repository | Chưa |
| T5 | Resolver ghi Set-Cookie hoặc response header | ID được gắn vào response |
| T6 | Response được gửi tới client | Client nhận ID nếu response tới nơi |

getId() có thể trả về định danh nội bộ của WebSession trước khi response được gửi. Điều đó không có nghĩa client đã nhận ID hoặc session đã được lưu bền vững. Không trả session ID trong JSON, không ghi vào log và không tự tạo cookie thủ công từ giá trị getId().

Nếu repository lưu thất bại trước khi response commit, resolver không nên phát một ID trỏ tới session chưa lưu thành công. Lỗi lưu cần được xử lý như lỗi hạ tầng/repository và quan sát bằng log, metric phù hợp.

## 6. Ví dụ hoàn chỉnh: bắt đầu session khi người dùng chọn ngôn ngữ

Một endpoint có thể lưu lựa chọn ngôn ngữ trong WebSession:

~~~java
@RestController
public class PreferenceController {

    @PostMapping("/preferences/locale")
    public Mono<Map<String, Object>> setLocale(
            @RequestBody LocaleRequest request,
            ServerWebExchange exchange) {

        return exchange.getSession()
                .map(session -> {
                    session.getAttributes().put(
                            "app.locale",
                            request.locale()
                    );

                    return Map.of(
                            "saved", true,
                            "started", session.isStarted()
                    );
                });
    }

    public record LocaleRequest(String locale) {
    }
}
~~~

Khi client gửi request đầu tiên không có session ID:

1. WebSessionManager tạo WebSession mới.
2. Controller thêm app.locale.
3. Session chuyển sang started.
4. Khi response commit, manager lưu session.
5. Resolver thêm Set-Cookie vào response.
6. Client lưu cookie và gửi lại trong request sau.

Request kế tiếp có thể được định tuyến tới instance khác. Instance đó đọc cookie, tìm cùng session trong repository dùng chung và lấy lại app.locale.

Không cần gọi session.save() trực tiếp trong controller thông thường. WebSessionManager quản lý việc lưu trước response commit. Gọi save() thủ công chỉ nên làm khi có yêu cầu cụ thể và phải hiểu tương tác với response lifecycle; không dùng nó thay cho việc thiết kế reactive pipeline đúng.

## 7. Nếu chỉ đọc session thì có phát ID mới không?

Hành vi phụ thuộc session hiện có hay mới và trạng thái started.

| Tình huống | Kết quả thường gặp |
|---|---|
| Request không có ID, getSession() tạo session mới nhưng không start và không thêm thuộc tính | Session mới có thể không được lưu; không phát ID mới |
| Request không có ID, gọi start() | Session được đánh dấu cần duy trì; được lưu và ID được phát trước commit |
| Request không có ID, thêm thuộc tính | Session started, được lưu và ID được phát |
| Request có ID hợp lệ, tải session hiện tại | Dùng session hiện tại; manager lưu theo chính sách repository và resolver duy trì định danh |
| Request có ID cũ không còn session | Có thể tạo session mới; chỉ phát ID nếu session mới được started |
| Session bị invalidate | Session bị xóa và response có thể hết hạn cookie/header ID |

Đối với session mới chưa started, việc chỉ gọi getSession() không nhất thiết tạo cookie mới. Điều này giúp tránh phát session cho mọi request công khai chỉ vì một controller hoặc filter gọi getSession() để kiểm tra.

Đối với session đã tồn tại, việc truy cập có thể làm mới thời điểm hoạt động hoặc TTL. Đây là một phần của idle timeout. Nếu muốn endpoint hoàn toàn không truy cập session, hãy tránh gọi exchange.getSession() và kiểm tra các filter/security repository có truy cập WebSession trước handler hay không.

## 8. Định danh session được lưu và giải quyết bằng resolver

WebSessionIdResolver tách cách vận chuyển session ID khỏi repository. Hai resolver thường gặp:

- CookieWebSessionIdResolver: đọc ID từ cookie và phát cookie trong response.
- HeaderWebSessionIdResolver: đọc ID từ một HTTP header và phát ID qua header response.

Với cookie, trình duyệt tự gửi cookie theo Domain, Path, Secure và SameSite. Cần cấu hình HttpOnly và Secure cho session cookie khi chạy HTTPS. Không đưa ID vào URL vì URL có thể xuất hiện trong lịch sử trình duyệt, proxy log, referrer và analytics.

Với header resolver, client phải tự lưu và gửi lại header. Cách này thường phù hợp với API client hoặc môi trường không dùng cookie jar. Tuy nhiên, header ID vẫn là bearer credential; phải bảo vệ qua TLS và không ghi giá trị vào log.

Resolver không lưu dữ liệu session. Nó chỉ nhận diện ID trong request và ghi/xóa ID trên response. Repository mới chịu trách nhiệm lưu trạng thái session.

### Ví dụ cấu hình Redis WebFlux

Với ứng dụng reactive dùng Redis, cấu hình có thể bật Spring Session WebFlux:

~~~java
@Configuration
@EnableRedisWebSession(maxInactiveIntervalInSeconds = 1800)
public class ReactiveSessionConfiguration {
}
~~~

Ứng dụng cần ReactiveRedisConnectionFactory và các dependency Spring Session Data Redis tương thích. Cấu hình cụ thể phụ thuộc phiên bản Spring Session và Spring Boot.

Trong một ứng dụng Spring Boot, auto-configuration có thể tạo các thành phần cần thiết từ starter và cấu hình Redis. Hãy dùng một cơ chế cấu hình session nhất quán, không đồng thời tự đăng ký WebSessionManager/repository trùng với auto-configuration.

## 9. Đổi session ID và phát ID mới

Sau khi người dùng đăng nhập hoặc thay đổi mức đặc quyền, ứng dụng có thể cần đổi session ID để giảm nguy cơ session fixation. WebSession cung cấp changeSessionId(), trả về Mono<Void>.

Ví dụ:

~~~java
public Mono<Void> rotateSessionId(ServerWebExchange exchange) {
    return exchange.getSession()
            .flatMap(WebSession::changeSessionId);
}
~~~

Sau khi ID được thay đổi, manager/resolver sẽ phát ID mới trong response khi response commit theo vòng đời session. Client cần dùng ID mới cho các request tiếp theo.

Nếu Spring Security đã cấu hình session fixation protection trong reactive security chain, hãy để cơ chế đó quản lý việc đổi ID. Không tự đổi ID thêm lần nữa nếu không có yêu cầu rõ ràng; kiểm thử để bảo đảm ID cũ không còn được chấp nhận theo chính sách repository.

Không gửi ID mới trong body để client tự tạo cookie. Hãy để WebSessionIdResolver quản lý kênh phát hành.

## 10. Invalidate session và hết hạn định danh

Đăng xuất hoặc thu hồi session cần xóa trạng thái phía repository và làm cho client ngừng gửi ID cũ. WebSession.invalidate() trả về Mono<Void>.

Ví dụ:

~~~java
public Mono<Void> invalidateSession(ServerWebExchange exchange) {
    return exchange.getSession()
            .flatMap(WebSession::invalidate);
}
~~~

Trong luồng Spring Security, nên cấu hình logout handler và security context repository đúng cách để Authentication bị xóa và WebSession bị invalidate theo chính sách. Không chỉ xóa cookie ở client; nếu repository vẫn giữ session, một bản sao cookie cũ có thể tiếp tục được sử dụng.

Khi session đã expired hoặc invalidated, resolver có thể phát lệnh hết hạn cookie hoặc xóa header ID trên response. Với cookie, lệnh hết hạn cần khớp tên, Domain và Path của cookie ban đầu. Nếu dùng header resolver, response cần loại bỏ định danh theo quy ước của resolver.

Nếu không có session hiện tại, không nên tự tạo session mới chỉ để invalidate. Hãy xử lý trạng thái request không có session và để security/logout flow kết thúc nhất quán.

## 11. Response commit và ứng dụng streaming

WebFlux có thể trả Flux hoặc streaming response như Server-Sent Events. Khi response bắt đầu commit hoặc body bắt đầu được gửi, headers thường không còn thay đổi được.

Điều này có ý nghĩa trực tiếp với session ID:

- Nếu session cần bắt đầu, hãy gọi start() hoặc thêm thuộc tính trước khi response được commit.
- Đừng chờ một callback nền chạy sau khi handler đã trả response rồi mới tạo session.
- Đừng thêm thuộc tính session sau khi streaming response đã flush headers.
- Nếu cần lưu trạng thái cho một stream dài, hãy xác định rõ session được bắt đầu trước khi stream được subscribe/commit.
- Không giả định có thể gửi một cookie mới giữa luồng response đã commit.

Ví dụ, nếu endpoint SSE cần giữ một subscription ID trong session, hãy ghi thuộc tính trước khi tạo Flux stream:

~~~java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Mono<ResponseEntity<Flux<ServerSentEvent<String>>>> events(
        ServerWebExchange exchange) {

    return exchange.getSession()
            .map(session -> {
                session.getAttributes().put(
                        "app.subscription",
                        "subscription-42"
                );

                Flux<ServerSentEvent<String>> stream =
                        eventService.stream()
                                .map(value -> ServerSentEvent.builder(value).build());

                return ResponseEntity.ok(stream);
            });
}
~~~

Ví dụ minh họa việc bắt đầu session trước khi response stream được gửi. Trong ứng dụng thực tế, không dùng giá trị subscription cố định; tạo mã tham chiếu an toàn và xác thực quyền truy cập. Nếu stream có thời lượng dài, session cookie chỉ được phát ở response ban đầu, không thể cập nhật tùy ý sau khi headers đã commit.

## 12. Không chặn event loop khi thao tác session

WebFlux được thiết kế để xử lý nhiều request bằng số lượng thread nhỏ và non-blocking I/O. Vì vậy, không dùng JDBC blocking hoặc gọi block() trong controller để chờ session.

Không nên:

~~~java
WebSession session = exchange.getSession().block();
~~~

Cách này chặn thread đang xử lý reactive request và có thể gây nghẽn event loop hoặc deadlock trong một số luồng.

Nên giữ pipeline reactive:

~~~java
public Mono<String> currentLocale(ServerWebExchange exchange) {
    return exchange.getSession()
            .map(session -> (String) session.getAttributes()
                    .getOrDefault("app.locale", "vi-VN"));
}
~~~

Spring Session WebFlux cần ReactiveSessionRepository. Với Redis, dùng reactive Redis integration. JDBC repository là API blocking dành cho mô hình Servlet; không đưa JdbcIndexedSessionRepository trực tiếp vào reactive event loop như thể nó là repository non-blocking đầy đủ. Nếu hệ thống bắt buộc phải gọi một dịch vụ blocking, cần cô lập công việc đó trên scheduler phù hợp và đánh giá độ trễ; việc chuyển scheduler không tự biến JDBC session repository thành tích hợp reactive đầy đủ.

## 13. Bảo mật khi tạo và phát session ID

Session ID là bearer credential. Người có ID hợp lệ có thể sử dụng session tương ứng. Vì vậy:

- Chỉ bắt đầu session khi chức năng thực sự cần duy trì trạng thái.
- Dùng HTTPS và bật Secure cho cookie trong production.
- Bật HttpOnly để JavaScript không đọc session cookie.
- Chọn SameSite theo luồng điều hướng và SSO; vẫn duy trì CSRF protection phù hợp.
- Không ghi ID vào log, trace, URL hoặc metric label.
- Không trả ID trong JSON chỉ để debug.
- Đổi ID sau xác thực hoặc thay đổi đặc quyền theo chính sách session fixation.
- Invalidate session ở repository khi logout hoặc thu hồi.
- Không dùng session attribute do client gửi trực tiếp để xác định principal.
- Giới hạn dữ liệu lưu trong session và tránh lưu bí mật không cần thiết.

Không tự tạo session ID bằng UUID trong controller. Repository hoặc WebSessionStore chịu trách nhiệm tạo ID phù hợp và resolver chịu trách nhiệm phát ID. Tự quản lý ID sẽ làm tăng nguy cơ đoán được, trùng lặp, phát hành trước khi lưu hoặc không thu hồi đúng cách.

## 14. Kiểm thử trạng thái started và thời điểm phát ID

Kiểm thử cần xác minh không chỉ giá trị isStarted() mà còn response headers và khả năng dùng lại session trong request tiếp theo.

### Các ca kiểm thử cần có

| Ca kiểm thử | Hành động | Kết quả cần xác nhận |
|---|---|---|
| Không có cookie, chỉ gọi getSession() | Không start, không thêm thuộc tính | Không phát cookie ID mới nếu session mới vẫn chưa started |
| Không có cookie, gọi start() | Bắt đầu session rỗng | Session được lưu và response phát ID |
| Không có cookie, thêm thuộc tính | Đặt app.locale | Session started, được lưu và phát ID |
| Gửi cookie hợp lệ | Gọi getSession() | Tải lại session đã lưu |
| Request kế tiếp tới node khác | Dùng cùng cookie và repository chia sẻ | Đọc được thuộc tính đã lưu |
| Đổi ID | Gọi changeSessionId() | Response phát ID mới; ID cũ không còn dùng theo chính sách |
| Invalidate | Gọi invalidate() | Session bị xóa và resolver hết hạn định danh |
| Response streaming | Bắt đầu session trước commit | Cookie xuất hiện ở response ban đầu |
| Tạo session sau commit | Cố sửa session khi headers đã commit | Không dựa vào thao tác này để phát cookie; thiết kế phải tránh |
| Repository lỗi | Ngắt Redis trong test | Lỗi lưu được báo rõ, không phát ID trỏ tới session chưa lưu |

### Ví dụ WebTestClient kiểm tra cookie

~~~java
webTestClient.post()
        .uri("/preferences/locale")
        .bodyValue(new LocaleRequest("vi-VN"))
        .exchange()
        .expectStatus().isOk()
        .expectHeader().exists(HttpHeaders.SET_COOKIE);
~~~

Đây là ví dụ cho endpoint tạo thuộc tính session và dùng CookieWebSessionIdResolver. Nếu ứng dụng dùng HeaderWebSessionIdResolver, hãy kiểm tra response header tương ứng thay vì Set-Cookie.

Tiếp theo, lấy cookie từ response trong test và gửi lại ở request thứ hai. Xác nhận endpoint đọc được app.locale. Không ghi giá trị cookie ra console hoặc report test.

### Kiểm tra trường hợp chưa started

Tạo một endpoint test chỉ gọi exchange.getSession() và trả về isStarted() mà không gọi start() hoặc thêm thuộc tính. Gửi request không có cookie và xác nhận response không phát session cookie mới. Sau đó gọi endpoint tạo thuộc tính và xác nhận response có cookie.

Test này giúp phát hiện việc một filter hoặc controller vô tình bắt đầu session cho mọi request công khai.

## 15. Kiểm thử nhiều instance và repository thật

Một test với WebSession object giả không chứng minh dữ liệu được chia sẻ giữa các instance. Hãy dùng Redis test instance hoặc môi trường tương đương production:

1. Khởi động hai application context WebFlux dùng cùng ReactiveSessionRepository, namespace và resolver.
2. Gửi request tạo session tới instance A.
3. Nhận cookie từ response A.
4. Gửi request tiếp theo mang cookie đó tới instance B.
5. Xác nhận B đọc được thuộc tính session.
6. Đổi ID hoặc invalidate ở A.
7. Gửi lại cookie cũ tới B và xác nhận session không còn hợp lệ theo chính sách.
8. Ngắt repository trong test và xác nhận lỗi hạ tầng được phân biệt với session không tồn tại.

Cần kiểm tra cả cấu hình cookie và repository giữa các instance. Nếu namespace khác nhau, instance B sẽ không tìm thấy session dù cookie được gửi đúng. Nếu resolver khác tên cookie hoặc header, request có thể không mang định danh mà B mong đợi.

## 16. Lỗi thường gặp khi tạo session và phát ID

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| getSession() trả WebSession nhưng client không nhận cookie | Session mới chưa started | Gọi start() hoặc thêm thuộc tính nếu thực sự cần duy trì |
| Controller thấy isStarted() là false | Chưa gọi start và chưa thêm thuộc tính | Kiểm tra luồng tạo trạng thái |
| Có cookie nhưng request sau không đọc được session | Repository, namespace hoặc resolver không đồng nhất | So sánh cấu hình giữa instance |
| Cookie không xuất hiện trên response streaming | Response đã commit trước khi session started | Bắt đầu session trước khi stream commit |
| Session ID đổi nhưng client tiếp tục dùng ID cũ | Response đổi ID không tới client hoặc cookie scope không khớp | Kiểm tra Set-Cookie, Domain, Path và TLS |
| Request công khai tạo nhiều session | Filter/controller gọi getSession và thêm thuộc tính không cần thiết | Loại bỏ session access không cần thiết |
| WebFlux bị nghẽn khi truy cập session | Dùng API blocking hoặc gọi block() | Dùng ReactiveSessionRepository và pipeline non-blocking |
| Repository không khả dụng nhưng bị coi là anonymous | Exception bị nuốt và chuyển thành session trống | Phân biệt lỗi hạ tầng với session không tìm thấy |

Khi điều tra, kiểm tra theo thứ tự: request có ID hay không, resolver có đọc đúng ID không, repository có tìm thấy session không, session có started không, thao tác save có hoàn tất không và response có phát header trước commit không.

## 17. Checklist triển khai

Trước khi đưa WebFlux session vào production, xác nhận:

- Ứng dụng dùng WebSession và WebSessionManager, không dùng Servlet HttpSession filter trong luồng WebFlux.
- Repository là ReactiveSessionRepository phù hợp với kho dữ liệu.
- Không gọi block() trong reactive request pipeline.
- getSession() không bị nhầm với việc lưu session hoặc phát ID.
- Chỉ bắt đầu session khi cần duy trì trạng thái.
- Hiểu start() và thêm thuộc tính có thể chuyển session sang started.
- Session được lưu trước khi response commit.
- Resolver phát ID qua cookie hoặc header đã cấu hình.
- Cookie có Domain, Path, Secure, HttpOnly và SameSite phù hợp.
- Đã kiểm thử đổi ID, logout, expiration và response streaming.
- Mọi instance dùng cùng repository, namespace và resolver.
- Log, trace và metric không chứa session ID hoặc cookie.
- Có kiểm thử với repository thật và nhiều instance.

Trong WebFlux, việc tạo một WebSession và việc phát hành session ID là hai thời điểm khác nhau. getSession() cung cấp đối tượng session cho reactive pipeline; start() hoặc thêm thuộc tính thể hiện ứng dụng muốn duy trì session. Trước khi response commit, WebSessionManager lưu session đã started và WebSessionIdResolver phát ID vào response. Nắm rõ ranh giới này giúp tránh tạo session không cần thiết, tránh cookie bị thiếu trong response streaming và giữ vòng đời session nhất quán giữa các instance.

## Tài liệu tham khảo

- [Spring Session — WebFlux Integration](https://docs.spring.io/spring-session/reference/web-session.html)
- [Spring Session — ReactiveSessionRepository API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/ReactiveSessionRepository.html)
- [Spring Framework — WebSession API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebSession.html)
- [Spring Framework — WebSessionManager API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/session/WebSessionManager.html)
- [Spring Framework — WebSessionIdResolver API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/session/WebSessionIdResolver.html)

