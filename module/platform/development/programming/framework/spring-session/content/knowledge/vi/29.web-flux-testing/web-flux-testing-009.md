# Lỗi, timeout, hủy chuỗi và tình trạng phiên đã được lưu hay chưa

Trong ứng dụng Spring WebFlux, thao tác với session và repository thường trả về Mono hoặc Flux. Kết quả chỉ xuất hiện khi publisher được subscribe và hoàn tất. Vì vậy, một request có thể thất bại trước khi session được lưu, bị timeout khi đang chờ Redis/JDBC, hoặc bị hủy khi client đóng kết nối. Các trường hợp này không đồng nghĩa với nhau và cũng không chứng minh cùng một trạng thái dữ liệu.

Khi kiểm thử, cần trả lời chính xác các câu hỏi: session chưa tồn tại hay repository không truy cập được? Publisher đã phát onComplete hay mới bắt đầu ghi? Timeout có gửi cancellation tới driver không? Client ngắt kết nối trước hay sau khi response commit? Nếu thao tác save bị timeout, dữ liệu đã được ghi ở server hay chưa? Một request retry có thể tạo session trùng hoặc ghi đè thuộc tính không?

Bài này hướng dẫn phân biệt lỗi, timeout và cancellation trong WebFlux; kiểm tra vòng đời WebSession và ReactiveSessionRepository; xác minh dữ liệu đã được lưu; xây dựng test bằng StepVerifier và WebTestClient; đồng thời xử lý trạng thái không chắc chắn khi thao tác ghi bị timeout hoặc bị hủy.

## 1. Session WebFlux đi qua những thành phần nào?

Trong WebFlux, session được biểu diễn bằng WebSession. Spring Session có thể cung cấp WebSessionManager/WebSessionStore tích hợp với ReactiveSessionRepository để lưu dữ liệu vào kho dùng chung như Redis. Ứng dụng thường lấy session qua ServerWebExchange hoặc tham số WebSession trong controller.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant W as WebFlux Handler
    participant M as WebSessionManager
    participant R as ReactiveSessionRepository
    participant S as Redis / Store

    C->>W: HTTP request + session cookie
    W->>M: getSession()
    M->>R: findById(id)
    R->>S: Read session
    S-->>R: Stored data
    R-->>M: WebSession
    M-->>W: WebSession
    W->>W: Update attributes
    W-->>M: Response commit
    M->>R: save(session)
    R->>S: Persist attributes + TTL
    S-->>R: Write acknowledged
    R-->>M: onComplete
    M-->>C: HTTP response + cookie
~~~

Các thành phần có trách nhiệm khác nhau:

- WebSession: API phiên mà handler/controller sử dụng; chứa ID, thời gian và attributes.
- WebSessionManager: tìm hoặc tạo session cho một exchange và quản lý vòng đời trong request.
- WebSessionStore: abstraction tạo, tìm và xóa WebSession.
- ReactiveSessionRepository: API reactive để tạo, tìm, lưu và xóa Session.
- Session repository implementation: chuyển đổi dữ liệu sang Redis, JDBC hoặc kho lưu trữ khác.
- Response commit: thời điểm WebFlux hoàn tất response; việc lưu session thường được phối hợp với giai đoạn này.

Trong WebFlux, không gọi block() để chờ repository. Việc đó chặn thread xử lý reactive pipeline và có thể gây nghẽn event loop.

## 2. Phân biệt các trạng thái thường bị nhầm

Một lỗi kiểm thử phổ biến là coi mọi trường hợp không có session là cùng một trạng thái. Cần phân biệt ít nhất các kết quả sau:

| Trạng thái | Publisher/API | Ý nghĩa |
|---|---|---|
| Session tồn tại | Mono phát Session | Có dữ liệu phiên hợp lệ |
| Session không tồn tại | Mono.empty() hoặc kết quả không có session theo API | ID không tìm thấy hoặc đã bị xóa/hết hạn |
| Repository lỗi | onError | Không thể xác định trạng thái do lỗi hạ tầng/dữ liệu |
| Timeout | TimeoutException hoặc lỗi timeout được ánh xạ | Không nhận kết quả trong giới hạn thời gian |
| Cancellation | SignalType.CANCEL | Subscriber không còn yêu cầu kết quả |
| Save hoàn tất | Mono<Void> phát onComplete | Repository xác nhận thao tác save đã hoàn tất theo contract |
| Save lỗi | onError | Repository báo thao tác lưu thất bại |
| Save outcome chưa rõ | Timeout/cancel sau khi ghi bắt đầu | Không biết chắc backend đã commit hay chưa |

Mono.empty() không phải là lỗi repository. onError cũng không có nghĩa session không tồn tại. Nếu code chuyển lỗi Redis thành Mono.empty(), ứng dụng có thể nhầm outage với một người dùng chưa đăng nhập.

Ví dụ phân nhánh rõ:

~~~java
return repository.findById(sessionId)
    .switchIfEmpty(Mono.error(
        new SessionNotFoundException()
    ))
    .onErrorMap(
        RedisConnectionFailureException.class,
        error -> new SessionStoreUnavailableException(error)
    );
~~~

Đây là ví dụ minh họa; loại exception cụ thể phụ thuộc driver và repository. Không bắt mọi lỗi thành SessionNotFoundException. Chỉ ánh xạ lỗi đã xác định, giữ nguyên nguyên nhân và để lỗi không mong đợi được xử lý ở tầng phù hợp.

## 3. Vòng đời WebSession và thời điểm lưu

WebSession thường được tạo khi ứng dụng yêu cầu session mới. Việc chỉ gọi getSession() không nhất thiết có nghĩa một session đã được lưu ngay lập tức. Session có thể được tạo lười và chỉ được xem là đã bắt đầu khi ứng dụng thêm thuộc tính hoặc gọi start().

Ví dụ handler cập nhật session:

~~~java
@GetMapping("/cart/visit")
Mono<String> visit(WebSession session) {
    session.getAttributes().put("cart.visited", true);
    return Mono.just("ok");
}
~~~

Trong cấu hình Spring Session WebFlux thông thường, WebSessionManager phối hợp việc lưu session với response commit. Khi session được thay đổi và đã bắt đầu, session được lưu theo chính sách tích hợp. Ứng dụng không nên mặc định rằng mọi lần gọi getSession() đều tạo một bản ghi bền vững.

Nếu cần kiểm soát tường minh ở một luồng đặc biệt, WebSession có API save() trả về Mono<Void>. Hãy compose publisher này vào luồng xử lý thay vì gọi block():

~~~java
return exchange.getSession()
    .flatMap(session -> {
        session.getAttributes().put("workflow.step", "confirmed");
        return session.save().thenReturn("saved");
    });
~~~

Không gọi save() tùy tiện ở mọi controller. Cần hiểu session manager đã lưu ở response commit hay chưa, và tránh tạo hai luồng save cạnh tranh cho cùng một session. API và hành vi chi tiết cần đối chiếu phiên bản Spring Framework/Spring Session của dự án.

## 4. Khi nào có thể nói session đã được lưu?

Trong reactive API, lời gọi repository.save(session) chỉ tạo publisher. Nó chưa chứng minh dữ liệu đã được ghi. Việc thực thi bắt đầu khi publisher được subscribe.

Với ReactiveSessionRepository, thao tác save thường có dạng Mono<Void>:

~~~java
Mono<Void> save = repository.save(session);
~~~

Ở thời điểm khai báo biến, chưa thể kết luận repository đã nhận lệnh. Chỉ khi publisher được subscribe và phát onComplete thì thao tác mới hoàn tất theo contract của repository.

Các mốc cần phân biệt:

1. Ứng dụng thay đổi WebSession attributes.
2. Session manager quyết định cần lưu.
3. Publisher save được tạo.
4. Publisher được subscribe.
5. Lệnh được gửi tới storage.
6. Storage xác nhận ghi.
7. Publisher phát onComplete.
8. Response được commit hoặc hoàn tất theo thứ tự tích hợp.

Tùy implementation, một số bước có thể nằm trong cùng một publisher hoặc transaction. Test cần xác minh điểm quan sát thực tế, không chỉ kiểm tra code đã gọi save().

Nếu response đã trả 200 nhưng repository chưa ghi xong, request sau có thể không tìm thấy session. Vì vậy, tích hợp cần bảo đảm save được compose vào response lifecycle và lỗi save không bị bỏ qua.

## 5. onComplete, onError và cancel trong Reactor

Reactor phân biệt ba kết thúc quan trọng:

- onComplete: publisher hoàn tất bình thường.
- onError: publisher kết thúc bằng lỗi.
- cancel: subscriber hủy subscription; đây là tín hiệu điều khiển ngược upstream, không phải một terminal signal giống onComplete/onError.

Có thể quan sát bằng doFinally:

~~~java
Mono<Void> save = repository.save(session)
    .doFinally(signal -> {
        switch (signal) {
            case ON_COMPLETE -> metrics.recordSaveCompleted();
            case ON_ERROR -> metrics.recordSaveFailed();
            case CANCEL -> metrics.recordSaveCancelled();
            default -> metrics.recordOtherSignal();
        }
    });
~~~

Không ghi session ID hoặc cookie vào log/metric. Dùng loại thao tác, repository, application version và kết quả làm nhãn có cardinality thấp.

doOnSuccess trên Mono<Void> có thể được gọi khi hoàn tất thành công với giá trị null; điều này không giống một session value. Với thao tác save, doOnSuccess chỉ nên được hiểu là publisher đã hoàn tất bình thường, không phải đã trả một đối tượng Session.

## 6. Cancellation không phải rollback

Khi client đóng kết nối hoặc upstream timeout, Reactor có thể gửi cancellation tới publisher upstream. Driver reactive có thể cố gắng hủy truy vấn hoặc lệnh đang chờ. Tuy nhiên, cancellation không bảo đảm thao tác ghi ở storage đã được rollback.

Ví dụ:

~~~text
Application gửi lệnh SET/UPDATE
        |
        v
Redis/Database nhận lệnh
        |
        +---- storage đã commit ---- response ACK đang trên đường về
        |
        +---- client cancel / timeout
~~~

Khi client hủy, ứng dụng có thể không nhận được ACK dù backend đã ghi xong. Ngược lại, lệnh có thể chưa được xử lý. Từ góc nhìn ứng dụng, kết quả có thể không xác định.

Vì vậy:

- Không suy ra “cancel thì dữ liệu chắc chắn chưa lưu”.
- Không suy ra “publisher đã bắt đầu thì dữ liệu chắc chắn đã lưu”.
- Không retry mù một thao tác không idempotent.
- Nếu cần biết trạng thái cuối, đọc lại repository bằng một request/operation mới.
- Với thao tác nghiệp vụ, dùng idempotency key hoặc version để xử lý retry.

Cancellation thường chỉ có thể ngăn công việc còn có thể ngăn. Nó không thể đảo ngược một lệnh đã commit tại hệ thống bên ngoài.

## 7. Timeout của request và timeout của repository

Timeout có thể xảy ra ở nhiều tầng:

| Tầng | Ví dụ | Điều cần kiểm tra |
|---|---|---|
| Client | Browser/người gọi API ngắt chờ | Request có bị đóng hay retry không |
| Gateway/proxy | Request timeout | Proxy có đóng kết nối trước ứng dụng không |
| WebFlux pipeline | Mono.timeout(...) | Publisher nào bị cancel |
| Redis/database driver | Command/query timeout | Backend có thể đã thực thi lệnh chưa |
| Connection pool | Không lấy được connection | Có chờ pool quá lâu không |
| Application deadline | Hết thời gian xử lý tổng | Các thao tác con có nhận deadline không |

Đặt timeout tổng cho request và timeout riêng cho repository có thể hữu ích, nhưng cần tránh cấu hình mâu thuẫn. Repository timeout nên phù hợp với SLA và thời gian còn lại của request.

Ví dụ:

~~~java
Duration repositoryTimeout = Duration.ofSeconds(2);

return repository.findById(sessionId)
    .timeout(repositoryTimeout)
    .onErrorMap(
        TimeoutException.class,
        error -> new SessionStoreTimeoutException(error)
    );
~~~

Timeout chỉ giới hạn thời gian chờ của publisher ở tầng này. Nó không tự đặt TTL session, không thay maxInactiveInterval và không chứng minh thao tác storage bị rollback.

## 8. Đừng biến timeout thành session miss

Mẫu code nguy hiểm:

~~~java
return repository.findById(id)
    .timeout(Duration.ofSeconds(1))
    .onErrorResume(error -> Mono.empty());
~~~

Đoạn này chuyển mọi lỗi thành kết quả không có session. Khi Redis mất kết nối hoặc query timeout, ứng dụng có thể coi người dùng là anonymous và tiếp tục tạo session mới. Điều đó làm khó chẩn đoán và có thể tạo hành vi bảo mật không mong muốn.

Tách trường hợp:

~~~java
return repository.findById(id)
    .switchIfEmpty(Mono.defer(() -> handleMissingSession(id)))
    .onErrorMap(
        TimeoutException.class,
        SessionStoreTimeoutException::new
    );
~~~

Chỉ switchIfEmpty xử lý trường hợp repository thực sự không phát session. onErrorMap chuyển lỗi timeout sang exception nghiệp vụ/hạ tầng riêng. Tùy thiết kế, lỗi repository có thể được trả về 503 thay vì 401 hoặc 404.

Không trả session rỗng khi repository unavailable. Nếu không thể xác minh phiên, thao tác cần xác thực nên fail closed.

## 9. Retry: chỉ lặp lại khi semantics cho phép

Retry có thể giúp vượt qua lỗi mạng tạm thời, nhưng retry save không phải lúc nào cũng an toàn. Nếu request đầu đã commit nhưng ACK bị mất, lần retry có thể ghi lại snapshot cũ hoặc tạo hiệu ứng phụ lần hai.

Trước khi retry, cần hỏi:

- Thao tác có idempotent không?
- Dữ liệu được ghi có định danh ổn định không?
- Có version hoặc compare-and-set không?
- Retry có thể ghi đè update mới hơn không?
- Có side effect ngoài repository không?
- Thời gian retry có nằm trong request deadline không?

Một ví dụ retry có giới hạn cho thao tác đọc idempotent:

~~~java
return repository.findById(id)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .filter(this::isTransientStoreFailure)
    );
~~~

Không áp dụng retry chung cho mọi exception. Không retry lỗi serialization, validation hoặc session invalidation như thể đó là lỗi mạng tạm thời.

Với save, hãy ưu tiên idempotent write theo session ID và version. Nếu repository chỉ ghi snapshot toàn bộ session, retry một snapshot cũ có thể ghi đè dữ liệu mới hơn. Cần xác định semantics trước khi bật retry.

## 10. TTL và timeout không phải một khái niệm

Session max idle interval và timeout của một publisher có mục đích khác nhau:

- Max inactive interval: thời gian không hoạt động tối đa của session.
- Repository TTL: thời gian storage giữ key/record theo chính sách session.
- Request timeout: giới hạn thời gian xử lý HTTP request.
- Repository operation timeout: giới hạn thời gian chờ một lệnh đọc/ghi.
- Client timeout: giới hạn thời gian client chờ response.

Không đặt session max idle interval bằng repository operation timeout. Cũng không dùng Mono.timeout để thay TTL của session.

Ví dụ session có idle interval 30 phút nhưng Redis GET timeout 2 giây. Nếu GET mất 3 giây, request có thể thất bại dù session còn hợp lệ. Ngược lại, GET có thể hoàn tất nhanh nhưng session đã hết hạn logic và phải bị từ chối.

Khi test expiration, dùng repository TTL hoặc clock/expiry mechanism của session. Khi test timeout, dùng publisher chậm hoặc backend chậm có kiểm soát.

## 11. Lỗi khi lưu session và phản hồi HTTP

Nếu repository save lỗi trong quá trình response commit, ứng dụng cần xử lý lỗi thay vì trả response thành công như thể session đã được lưu.

Các nguyên tắc:

- Không phát cookie mới trỏ tới session chưa lưu thành công.
- Không bỏ qua lỗi save bằng onErrorResume trả Mono.empty() nếu response cần session.
- Ánh xạ store unavailable/timeout sang lỗi phù hợp.
- Tránh trả stack trace, session ID hoặc nội dung thuộc tính trong response.
- Ghi metric lỗi save, timeout và cancel riêng.
- Xác định response có thể đã bắt đầu commit hay chưa.

Một khi response headers đã commit, ứng dụng không thể đổi status code hoặc header Set-Cookie đã gửi. Vì vậy, lỗi save xảy ra sau thời điểm commit có thể cần được xử lý ở log/metric và chiến lược phục hồi; không giả định có thể luôn trả 503.

Test cần kiểm tra cả thứ tự save và response commit. Một lỗi xảy ra trước commit có thể được ánh xạ thành HTTP 5xx; lỗi sau commit không thể sửa response đã gửi.

## 12. WebSession invalidation và thao tác xóa

WebSession.invalidate() trả về Mono<Void>. Phải subscribe/combine publisher này vào luồng; gọi method rồi bỏ qua publisher có thể khiến thao tác không được thực thi như mong đợi trong reactive API.

Ví dụ:

~~~java
return exchange.getSession()
    .flatMap(session ->
        session.invalidate()
            .then(Mono.just(ResponseEntity.noContent().build()))
    );
~~~

Đây là ví dụ về cách compose publisher. Trong ứng dụng thực tế, logout thường được tích hợp với Spring Security và WebSessionManager; không tự triển khai endpoint thay thế security logout nếu chưa xét CSRF, SecurityContext và cookie deletion.

Nếu invalidate bị timeout hoặc cancel, trạng thái xóa có thể không rõ. Đừng khẳng định session chắc chắn còn hoặc chắc chắn đã bị xóa. Khi cần xác nhận, thực hiện lookup mới bằng ID cũ sau khi repository hoạt động trở lại, đồng thời bảo đảm response không phát lại ID cũ.

Xóa cookie phía client và xóa session ở repository là hai hành động khác nhau. Cả hai cần được kiểm thử.

## 13. WebSession.save() và trạng thái lưu tường minh

WebSession có phương thức save() trả về Mono<Void>. Nó có thể được dùng để yêu cầu lưu session trong một luồng reactive đặc biệt. Publisher phải được compose vào chuỗi:

~~~java
Mono<Void> persist(WebSession session) {
    session.getAttributes().put("checkout.state", "ready");
    return session.save();
}
~~~

Cách gọi:

~~~java
return exchange.getSession()
    .flatMap(session -> persist(session))
    .thenReturn("ok");
~~~

Không dùng:

~~~java
exchange.getSession()
    .doOnNext(session -> session.save()); // Sai: publisher save bị bỏ qua
~~~

doOnNext chỉ thực hiện callback đồng bộ và không tự subscribe publisher trả về từ session.save(). Publisher save bị bỏ rơi, nên không có bảo đảm dữ liệu được ghi.

Hãy dùng flatMap, then hoặc compose phù hợp. Trong pipeline reactive, mọi I/O phải được nối vào publisher cuối cùng.

## 14. Đo lường và quan sát save lifecycle

Để chẩn đoán, cần metric phân biệt:

- Số lần repository createSession.
- Số lần findById hit/miss.
- Số lần save hoàn tất.
- Số lần save lỗi.
- Số lần timeout.
- Số lần cancellation.
- Độ trễ đọc/ghi.
- Số session hết hạn và bị xóa.
- Số lỗi serialization.
- Số lần response commit thất bại.

Không dùng session ID làm tag metric vì cardinality lớn và có thể làm lộ credential. Log chỉ nên ghi request correlation ID, operation name, repository type, error class và node/version.

Dùng doFinally để đo kết thúc publisher, nhưng không coi doFinally(CANCEL) là bằng chứng backend không ghi. Nếu cần xác định trạng thái dữ liệu, phải có read-after-write hoặc storage-side acknowledgement phù hợp.

## 15. Kiểm thử repository với StepVerifier

StepVerifier cho phép kiểm tra signal của publisher theo thời gian và thứ tự.

Với ReactiveSessionRepository, createSession trả về publisher. Hãy compose việc tạo, cập nhật, lưu và tải lại thành một chuỗi reactive:

~~~java
StepVerifier.create(
    repository.createSession()
        .flatMap(session -> {
            session.setAttribute("app.marker", "persisted");
            return repository.save(session).thenReturn(session);
        })
        .flatMap(session -> repository.findById(session.getId()))
)
.assertNext(stored ->
    assertThat(stored.getAttribute("app.marker"))
        .isEqualTo("persisted")
)
.verifyComplete();
~~~

Không dùng block() trong test nếu mục tiêu là kiểm tra reactive semantics. StepVerifier subscribe publisher và kiểm tra signal hoàn tất.

## 16. Kiểm thử lỗi và timeout có kiểm soát

Dùng fake repository hoặc publisher có thể điều khiển để tạo lỗi xác định:

~~~java
Mono<Session> delayedLookup =
        Mono.<Session>never()
            .timeout(Duration.ofMillis(100));

StepVerifier.create(delayedLookup)
    .expectError(TimeoutException.class)
    .verify();
~~~

Ví dụ này kiểm tra operator timeout, không chứng minh Redis/JDBC thực tế timeout đúng cách. Để kiểm tra driver, cần integration test với backend thật hoặc proxy test có thể gây delay/network fault.

Test lỗi storage:

~~~java
Mono<Session> failedLookup =
        Mono.error(new IllegalStateException("store unavailable"));

StepVerifier.create(failedLookup)
    .expectError(IllegalStateException.class)
    .verify();
~~~

Không dùng message chứa thông tin nhạy cảm. Trong test thật, kiểm tra exception type và mapping thay vì phụ thuộc chuỗi message của driver.

Nên kiểm thử riêng:
- Empty result cho ID không tồn tại.
- onError cho storage unavailable.
- Timeout cho publisher không hoàn tất.
- Serialization failure cho payload sai.
- Cancel khi subscriber ngừng chờ.
- Retry giới hạn cho transient error.

## 17. Kiểm thử cancellation và truyền cancellation upstream

Cancellation cần được kiểm tra bằng publisher có thể quan sát onCancel:

~~~java
AtomicBoolean cancelled = new AtomicBoolean();

Mono<Void> pendingSave = Mono.<Void>never()
    .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(pendingSave)
    .thenCancel()
    .verify();

assertThat(cancelled).isTrue();
~~~

Test này xác nhận cancellation được truyền tới publisher được kiểm tra. Nó không chứng minh storage chưa ghi dữ liệu. Để kiểm tra repository thật, cần kiểm tra driver có hủy command đang chờ hay không và xác minh trạng thái cuối trong storage.

Khi test request cancellation qua WebFlux, có thể hủy subscription của WebTestClient hoặc dùng server test có thể đóng connection. Cần quan sát:

- Handler publisher có nhận cancel không.
- Repository publisher có nhận cancel không.
- Response đã commit hay chưa.
- Cookie đã được gửi chưa.
- Storage cuối cùng có session hay không.

Không dùng một test thenCancel() với Mono.never() để kết luận toàn bộ request lifecycle của production đã được kiểm thử.

## 18. Kiểm thử WebFlux bằng WebTestClient

WebTestClient kiểm thử endpoint WebFlux và response. Một endpoint test có thể cập nhật session:

~~~java
@RestController
class SessionProbeController {

    @GetMapping("/test/session")
    Mono<String> createSession(WebSession session) {
        session.getAttributes().put("test.marker", "stored");
        return Mono.just("ok");
    }
}
~~~

Test:

~~~java
@SpringBootTest
@AutoConfigureWebTestClient
class WebSessionIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void createsSessionCookie() {
        client.get()
            .uri("/test/session")
            .exchange()
            .expectStatus().isOk()
            .expectCookie().exists("SESSION");
    }
}
~~~

Tên cookie SESSION chỉ là ví dụ; cần dùng tên CookieSerializer thực tế. Nếu endpoint không làm session started, có thể không phát cookie. Trong test, thêm thuộc tính để tạo thay đổi có ý nghĩa.

WebTestClient kiểm tra response và cookie nhưng không tự chứng minh repository đã lưu attributes. Cần thêm read-after-write bằng repository hoặc gọi endpoint thứ hai với cookie vừa nhận để xác minh session được khôi phục.

## 19. Kiểm tra dữ liệu đã lưu sau response

Một cách kiểm tra end-to-end là dùng cookie nhận từ response đầu tiên cho request thứ hai:

~~~java
EntityExchangeResult<String> first = client.get()
    .uri("/test/session")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class)
    .returnResult();

ResponseCookie cookie =
    first.getResponseCookies().getFirst("SESSION");

assertThat(cookie).isNotNull();

client.get()
    .uri("/test/session/read")
    .cookie("SESSION", cookie.getValue())
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class)
    .isEqualTo("stored");
~~~

Ví dụ giả định endpoint /test/session/read đọc test.marker từ WebSession. Không log hoặc in cookie value. Tên cookie cần khớp cấu hình thực tế.

Request thứ hai chứng minh session được khôi phục qua HTTP lifecycle. Nếu cần xác minh storage cụ thể, đọc bằng ReactiveSessionRepository hoặc API quản trị trong test context. Không truy vấn trực tiếp key nội bộ bằng cách hard-code cấu trúc Redis nếu repository abstraction có thể cung cấp cách kiểm tra.

## 20. Kiểm thử save lỗi trước và sau response commit

Cần tạo hai tình huống khác nhau:

**Save lỗi trước response commit**

- Handler thay đổi session.
- Repository save phát onError trước khi response commit hoàn tất.
- Xác nhận response không báo thành công nếu session là điều kiện của thao tác.
- Xác nhận không phát cookie mới trỏ tới session không lưu được.
- Xác nhận lỗi được ánh xạ và metric tăng.

**Save lỗi sau khi response đã commit**

- Response headers/body đã được gửi.
- Backend hoặc tác vụ cleanup báo lỗi sau đó.
- Không thể thay đổi status/header đã gửi.
- Ghi nhận lỗi, cảnh báo và xác minh trạng thái storage theo quy trình phục hồi.

Trong một số tích hợp, save session được compose vào response commit nên lỗi save có thể làm commit thất bại trước khi dữ liệu gửi tới client. Tuy nhiên, không khái quát điều đó cho mọi custom filter hoặc mọi side effect. Hãy kiểm thử với chính WebSessionManager, repository và response pipeline của ứng dụng.

## 21. Trạng thái không chắc chắn sau timeout của save

Đây là tình huống khó nhất:

1. Ứng dụng gửi save.
2. Redis/database nhận lệnh.
3. Storage có thể đã commit.
4. ACK bị trễ hoặc mất.
5. Mono.timeout phát lỗi và cancel upstream.
6. Ứng dụng không biết save đã hoàn tất ở backend hay chưa.

Không được báo “chưa lưu” chỉ dựa vào TimeoutException. Cũng không báo “đã lưu” vì lệnh đã được gửi.

Chiến lược xử lý:

- Ghi nhận outcome là unknown/indeterminate trong telemetry.
- Không phát cookie mới nếu integration không thể xác nhận commit.
- Thực hiện read-after-write bằng ID ổn định sau khi storage phục hồi.
- Nếu session được tạo mới và ID chưa phát ra, cân nhắc dọn bản ghi mồ côi khi có thể xác định an toàn.
- Dùng thao tác idempotent để retry.
- Dùng version để phát hiện ghi đè snapshot cũ.
- Đặt timeout và retry theo request deadline.
- Không lặp lại side effect nghiệp vụ cùng với session save.

Với một thao tác chỉ lưu thuộc tính session, đọc lại ID có thể giúp xác định trạng thái cuối. Nhưng nếu save bao gồm nhiều key hoặc transaction, cần xác minh toàn bộ bất biến chứ không chỉ key chính.

## 22. Không dùng onErrorResume để giả vờ lưu thành công

Mẫu nguy hiểm:

~~~java
return repository.save(session)
    .onErrorResume(error -> Mono.empty())
    .thenReturn("ok");
~~~

Mẫu này biến lỗi lưu thành hoàn tất bình thường. Handler có thể trả 200 trong khi session không được lưu. Request sau đó nhận cookie nhưng repository không tìm thấy dữ liệu.

Nếu muốn trả lỗi có ý nghĩa:

~~~java
return repository.save(session)
    .timeout(Duration.ofSeconds(2))
    .thenReturn("saved")
    .onErrorMap(
        error -> new SessionPersistenceException(error)
    );
~~~

Đừng dùng mapping tổng quát nếu cần giữ phân biệt timeout, serialization, authentication và connection failure. Tốt hơn là tạo exception hierarchy hoặc dùng error code nội bộ để phân loại.

Chỉ dùng fallback nếu fallback thực sự đáp ứng contract. Ví dụ, endpoint công khai không cần session có thể tiếp tục khi không tạo session; nhưng endpoint yêu cầu lưu trạng thái đăng nhập không được âm thầm bỏ qua repository failure.

## 23. Kiểm thử expiration và last access

Session idle expiration khác request timeout. Kiểm thử expiration cần xác nhận repository từ chối session sau max idle interval và storage TTL được cập nhật theo hoạt động.

Các trường hợp:

- Tạo session với idle timeout ngắn.
- Lưu session và xác nhận TTL được đặt.
- Đọc session và cập nhật last access theo chính sách.
- Xác nhận TTL được refresh khi có hoạt động được tính.
- Không refresh TTL khi request chỉ tạo publisher nhưng không subscribe.
- Xác nhận session hết hạn bị từ chối dù key còn tồn tại vật lý.
- Xác nhận timeout của repository không làm session bị coi là expired.

Nếu repository hỗ trợ clock injection, dùng Clock giả lập để kiểm soát thời gian. Nếu không, dùng TTL test ngắn với backend thật và polling có giới hạn thay vì sleep dài cố định.

## 24. Kiểm thử nhiều request và nhiều instance

Trong hệ thống nhiều node, hai request có thể cập nhật cùng session. Reactive không tự giải quyết lost update.

Một kịch bản:

~~~mermaid
sequenceDiagram
    participant A as Request A / Node 1
    participant R as Shared Repository
    participant B as Request B / Node 2
    A->>R: Read snapshot S1
    B->>R: Read snapshot S1
    A->>A: Update attribute A
    B->>B: Update attribute B
    A->>R: Save snapshot S2
    B->>R: Save snapshot S3
    Note over R: Snapshot ghi sau có thể ghi đè dữ liệu trước
~~~

Test cần điều khiển thứ tự đọc/ghi bằng latch hoặc publisher có thể điều khiển. Không dựa vào timing ngẫu nhiên.

Xác nhận:
- Node A tạo session, node B đọc được.
- Node B cập nhật, node A tải lại thấy dữ liệu sau commit.
- Hai request cùng sửa một thuộc tính có hành vi đúng chính sách.
- Timeout ở node A không làm node B kết luận sai trạng thái.
- Logout/invalidate ở một node có hiệu lực trên node khác.
- Redis/JDBC outage được phân biệt với session miss.
- Serializer, namespace và TTL giống nhau giữa node.

## 25. Testcontainers và lỗi storage thật

Fake repository hữu ích cho kiểm tra signal nhưng không mô phỏng mọi lỗi của Redis/JDBC. Nên có integration test dùng backend thật, chẳng hạn Redis Testcontainers hoặc database container tương ứng.

Các kịch bản fault injection:

- Tạm dừng container.
- Chặn kết nối hoặc làm tăng latency.
- Đóng connection pool.
- Gửi payload không deserialize được.
- Làm storage trả lỗi khi save.
- Ngắt mạng sau khi request đã gửi lệnh write.
- Khôi phục storage và kiểm tra session tồn tại hay không.

Không dùng Mono.delay thay cho mọi bài test Redis timeout. Publisher chậm kiểm tra operator; Testcontainers/fault injection kiểm tra driver, connection pool và backend.

## 26. Ánh xạ lỗi ra HTTP

Tùy loại lỗi và endpoint, có thể chọn status khác nhau:

| Trường hợp | Hành vi HTTP thường cân nhắc |
|---|---|
| Session không tồn tại/hết hạn | 401 hoặc chuyển tới login theo ứng dụng |
| Người dùng không đủ quyền | 403 |
| Repository unavailable | 503 Service Unavailable |
| Repository timeout | 503 hoặc lỗi gateway phù hợp |
| Payload session hỏng | 5xx, cảnh báo và chính sách thu hồi an toàn |
| Client cancel | Không có response hữu ích để gửi nếu connection đã đóng |
| Request validation sai | 400/422 tùy API |

Không trả 401 cho Redis outage như thể người dùng đã đăng xuất. Điều đó gây logout giả và che giấu lỗi hạ tầng. Không trả 200 khi session save thất bại.

Trong WebFlux có thể dùng @RestControllerAdvice hoặc error handler tập trung để ánh xạ exception. Không đưa exception message, session ID hoặc nội dung attributes vào response.

## 27. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Request sau không thấy session | Save publisher bị bỏ rơi hoặc response commit không đợi save | Compose save vào pipeline và test read-after-write |
| Timeout bị coi là session miss | onErrorResume chuyển mọi lỗi thành empty | Phân biệt empty và onError |
| Client đóng kết nối nhưng session vẫn tồn tại | Storage đã commit trước cancellation | Xác minh trạng thái cuối; cancellation không phải rollback |
| Retry tạo trạng thái không nhất quán | Write không idempotent hoặc snapshot cũ | Version/CAS và retry có điều kiện |
| Handler trả 200 nhưng session mất | Nuốt lỗi save rồi trả success | Để lỗi đi tới error handler |
| Test cancellation pass nhưng storage vẫn ghi | Test chỉ kiểm tra publisher cancel | Thêm integration test với backend thật |
| Session hết hạn dù request timeout dài | TTL/maxIdleTime quá ngắn hoặc không refresh | Kiểm tra last access và repository TTL |
| Redis outage bị trả 401 | Store error bị đổi thành empty | Ánh xạ store unavailable riêng |
| Logout không hoàn tất | Publisher invalidate không được compose | Dùng flatMap/then và test repository |
| WebFlux bị nghẽn | Gọi block() hoặc dùng driver blocking trên event loop | Dùng reactive driver, không block |
| Response cookie phát nhưng lookup miss | Cookie được phát trước khi save hoàn tất hoặc cấu hình node lệch | Kiểm tra commit order và cookie/repository config |

## 28. Checklist kiểm thử trước phát hành

- Phân biệt session miss, expiry, storage error và timeout.
- Không chuyển lỗi repository thành Mono.empty().
- Mọi publisher save/invalidate đều được compose vào pipeline.
- Xác nhận save phát onComplete trước khi coi thao tác thành công.
- Kiểm tra cancellation được truyền tới upstream.
- Không coi cancellation là rollback.
- Có test cho save timeout với trạng thái backend không chắc chắn.
- Có read-after-write để xác minh session đã lưu.
- Không phát session cookie mới khi save thất bại trước response commit.
- Kiểm tra WebSession lifecycle qua WebTestClient.
- Kiểm tra ReactiveSessionRepository bằng StepVerifier.
- Có test TTL và last-access riêng với request timeout.
- Retry chỉ áp dụng cho lỗi transient và thao tác idempotent.
- Không gọi block() trong reactive pipeline.
- Có test storage thật bằng Testcontainers/fault injection.
- Có test nhiều node và request đồng thời.
- Lỗi Redis/JDBC được ánh xạ thành 503 phù hợp thay vì logout giả.
- Log/metric không chứa session ID, cookie hoặc thuộc tính nhạy cảm.
- Test report không in credential khi assertion thất bại.

Trong WebFlux, trạng thái lưu session chỉ được xác nhận khi publisher lưu hoàn tất theo contract; việc tạo publisher hoặc gửi lệnh chưa đủ. Timeout và cancellation có thể xảy ra sau khi backend đã nhận hoặc thậm chí commit lệnh, nên kết quả ghi có thể không xác định. Hãy tách session miss khỏi lỗi storage, compose mọi thao tác save/invalidate vào reactive chain, kiểm thử bằng StepVerifier và WebTestClient, rồi dùng repository thật để xác minh trạng thái sau timeout/cancel. Với thao tác ghi có thể retry, cần idempotency hoặc version để tránh ghi lặp và lost update.

## Tài liệu tham khảo

- [Spring Session — WebFlux Integration](https://docs.spring.io/spring-session/reference/web-session.html)
- [Spring Session — ReactiveSessionRepository API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/ReactiveSessionRepository.html)
- [Spring Framework — WebSession API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebSession.html)
- [Spring Framework — WebFlux Testing](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Reactor — Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)

