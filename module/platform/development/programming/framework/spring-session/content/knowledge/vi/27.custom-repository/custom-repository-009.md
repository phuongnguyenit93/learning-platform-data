# ReactiveSessionRepository và tuân thủ chuỗi xử lý không chặn

Spring Session có thể quản lý phiên trong ứng dụng Spring WebFlux thông qua ReactiveSessionRepository. Repository này tạo, tải, lưu và xóa Session bằng các kiểu dữ liệu reactive của Reactor, chủ yếu là Mono. Mỗi thao tác lưu trữ được biểu diễn thành một publisher để WebFlux ghép nó vào chuỗi xử lý request mà không phải chờ đồng bộ trên thread đang xử lý sự kiện.

Điểm cốt lõi của lập trình reactive là giữ toàn bộ đường đi I/O ở dạng không chặn. Việc đổi kiểu trả về từ Session sang Mono<Session> chưa đủ. Nếu bên trong publisher vẫn gọi JDBC đồng bộ, Thread.sleep(), block() hoặc một HTTP client blocking, event-loop vẫn bị giữ lại. Một chuỗi reactive đúng phải bắt đầu từ nguồn dữ liệu có API reactive, nối các bước bằng operator và để framework subscribe ở ranh giới phù hợp.

Trong ứng dụng WebFlux, Spring Session tích hợp với WebSession của Spring Framework. Thông thường, controller nên làm việc với WebSession qua ServerWebExchange hoặc tham số được framework hỗ trợ; WebSessionManager và WebSessionStore phối hợp với ReactiveSessionRepository để quản lý vòng đời. Chỉ gọi ReactiveSessionRepository trực tiếp khi cần thao tác repository ở tầng service, xây dựng implementation riêng hoặc xử lý một workflow đặc biệt.

## 1. ReactiveSessionRepository là gì?

ReactiveSessionRepository là hợp đồng lưu trữ Session theo cách reactive và không chặn. Nó nằm trong package org.springframework.session và dùng generic S extends Session để giữ kiểu Session do implementation tạo ra.

Bốn thao tác chính:

| Phương thức | Kiểu trả về | Ý nghĩa |
|---|---|---|
| createSession() | Mono<S> | Tạo một Session có thể được repository lưu |
| findById(String id) | Mono<S> | Tìm session theo ID; không có kết quả thì publisher hoàn tất rỗng |
| save(S session) | Mono<Void> | Lưu session và phát tín hiệu hoàn tất khi thao tác kết thúc |
| deleteById(String id) | Mono<Void> | Xóa session; nếu không tìm thấy thì có thể hoàn tất mà không làm gì |

Mẫu chữ ký rút gọn:

~~~java
public interface ReactiveSessionRepository<S extends Session> {
    Mono<S> createSession();
    Mono<S> findById(String id);
    Mono<Void> save(S session);
    Mono<Void> deleteById(String id);
}
~~~

Mono biểu diễn không hoặc một giá trị. Với save và delete, Mono<Void> biểu diễn việc hoàn tất hoặc lỗi, không phát ra một đối tượng kết quả. Không dùng block() để lấy giá trị từ Mono trong request WebFlux.

Repository có thể tối ưu cách lưu bằng cách theo dõi những thuộc tính thay đổi. Vì vậy, Session nên được tạo bằng createSession() hoặc tải bằng findById() từ chính repository đó. Không tự dựng một implementation Session tùy ý rồi truyền cho repository khác lưu.

## 2. Reactive khác với API đồng bộ ở đâu?

Với SessionRepository đồng bộ, lời gọi findById() trả về Session ngay khi dữ liệu đã được tải hoặc thread đã chờ I/O xong. Với ReactiveSessionRepository, findById() trả về Mono<S>; dữ liệu có thể được phát sau đó khi thao tác I/O hoàn tất.

Luồng đồng bộ:

    Request thread
        |
        v
    findById(id) -------- chờ Redis/DB
        |
        v
    Session
        |
        v
    Xử lý tiếp

Luồng reactive:

    Request
        |
        v
    findById(id) tạo Mono
        |
        v
    Ghép operator vào pipeline
        |
        v
    Driver reactive thực hiện I/O
        |
        v
    Phát Session hoặc hoàn tất rỗng
        |
        v
    Pipeline tiếp tục

Reactive không có nghĩa là mọi thao tác chạy song song. Mono chỉ mô tả một kết quả bất đồng bộ. Các operator như map, flatMap, then và switchIfEmpty xác định thứ tự và cách chuyển tiếp tín hiệu. Một chuỗi reactive có thể tuần tự hóa các thao tác phụ thuộc nhau mà không giữ thread chờ.

## 3. WebSession là lớp tích hợp ưu tiên trong WebFlux

Spring WebFlux dùng WebSession, không dùng Servlet HttpSession làm abstraction phiên của request reactive. Spring Session cung cấp WebSession integration để thay implementation mặc định bằng một phiên được lưu qua ReactiveSessionRepository.

Các thành phần chính:

| Thành phần | Trách nhiệm |
|---|---|
| WebSession | API phiên mà handler/controller WebFlux sử dụng |
| WebSessionManager | Tìm hoặc tạo WebSession cho request |
| WebSessionStore | Chiến lược tải và lưu WebSession |
| SpringSessionWebSessionStore | Adapter nối WebSession với ReactiveSessionRepository |
| ReactiveSessionRepository | Lưu Session vào Redis hoặc repository reactive khác |

Trong request handler, có thể lấy phiên từ ServerWebExchange:

~~~java
@GetMapping("/preferences")
public Mono<String> getTheme(ServerWebExchange exchange) {
    return exchange.getSession()
            .map(session -> {
                Object theme = session.getAttributes().get("theme");
                return theme == null ? "light" : theme.toString();
            });
}
~~~

Cập nhật thuộc tính:

~~~java
@PostMapping("/preferences/theme")
public Mono<String> updateTheme(
        @RequestParam String theme,
        ServerWebExchange exchange) {

    return exchange.getSession()
            .map(session -> {
                session.getAttributes().put("theme", theme);
                return theme;
            });
}
~~~

WebSessionManager và WebSessionStore điều phối việc bắt đầu, thay đổi và lưu phiên theo vòng đời request. Controller không cần tự gọi một SessionRepository đồng bộ. Với luồng thông thường, hãy dùng WebSession và để Spring WebFlux quản lý persistence.

## 4. Cấu hình WebFlux với Spring Session Redis

Với Redis, Spring Session cung cấp ReactiveRedisSessionRepository và annotation EnableRedisWebSession để cấu hình WebSessionManager cùng repository reactive.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableRedisWebSession(
    maxInactiveIntervalInSeconds = 1800,
    redisNamespace = "catalog:prod:web-session"
)
public class SessionConfiguration {
}
~~~

Cấu hình này giả định ứng dụng đã có ReactiveRedisConnectionFactory tương thích, thường được cung cấp qua Spring Data Redis và Lettuce. Annotation EnableRedisWebSession thiết lập WebSession integration cho WebFlux và dùng Redis làm nơi lưu session.

Các thuộc tính thường cần quan tâm:

- maxInactiveIntervalInSeconds: thời gian không hoạt động tối đa của session, tính bằng giây.
- redisNamespace: tiền tố namespace cho key session.
- flushMode: thời điểm các thay đổi được ghi vào Redis.

Mặc định, ReactiveRedisSessionRepository lưu thay đổi khi save được gọi. FlushMode.IMMEDIATE yêu cầu ghi sớm nhất có thể khi session thay đổi. Chọn flush mode theo yêu cầu nhất quán và tải ghi; không coi IMMEDIATE là cách biến một driver blocking thành reactive.

Cần dùng cùng namespace và cấu hình tương thích trên mọi instance của cùng một ứng dụng. Mỗi môi trường nên có namespace riêng để tránh session dev, test và production dùng chung dữ liệu.

## 5. Cấu hình với EnableSpringWebSession và repository tự cung cấp

Nếu không dùng annotation Redis chuyên biệt, có thể bật EnableSpringWebSession và cung cấp đúng một bean ReactiveSessionRepository.

Ví dụ dùng ReactiveMapSessionRepository:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableSpringWebSession
public class WebSessionConfiguration {

    @Bean
    ReactiveSessionRepository<MapSession> reactiveSessionRepository() {
        return new ReactiveMapSessionRepository(new ConcurrentHashMap<>());
    }
}
~~~

Cấu hình này hữu ích cho test, demo hoặc ứng dụng đơn giản. ConcurrentHashMap nằm trong bộ nhớ của một JVM, không phải kho chia sẻ giữa nhiều instance. Nếu chạy nhiều node, mỗi node sẽ có vùng session riêng và client có thể mất phiên khi request được chuyển sang node khác.

EnableSpringWebSession yêu cầu một ReactiveSessionRepository trong ApplicationContext và tạo bean WebSessionManager. Annotation tổng quát này không tự cung cấp mọi cơ chế hết hạn hoặc cleanup; việc đó phụ thuộc repository cụ thể. Khi dùng repository tự viết, phải xác định rõ TTL, cleanup, event và giới hạn tài nguyên.

Không khai báo nhiều repository reactive không phân biệt trong cùng ApplicationContext rồi mong Spring tự chọn đúng một. Nếu có nhiều bean, cần cấu hình rõ bean được dùng và tránh tạo nhiều WebSessionManager cạnh tranh.

## 6. ReactiveSessionRepository trực tiếp: tạo và lưu phiên

Trong hầu hết handler WebFlux, WebSession integration là lựa chọn ưu tiên. Nhưng service có thể cần tạo một session riêng để thực hiện một workflow hoặc tích hợp với một thành phần khác.

Ví dụ tạo session và lưu trước khi trả ID:

~~~java
public class ReactiveWorkflowSessionService<S extends Session> {

    private final ReactiveSessionRepository<S> sessions;

    public ReactiveWorkflowSessionService(ReactiveSessionRepository<S> sessions) {
        this.sessions = sessions;
    }

    public Mono<String> createSession(String workflowId) {
        return this.sessions.createSession()
                .flatMap(session -> {
                    session.setAttribute("workflow.id", workflowId);
                    session.setMaxInactiveInterval(Duration.ofMinutes(20));

                    return this.sessions.save(session)
                            .thenReturn(session.getId());
                });
    }
}
~~~

Chuỗi xử lý có thứ tự:

1. createSession() phát ra Session.
2. flatMap nhận Session và đặt các thuộc tính.
3. save(session) thực hiện persistence.
4. thenReturn chỉ phát session ID sau khi save hoàn tất.

Nếu save thất bại, Mono lỗi và session ID không được phát như một kết quả thành công. Đây là cách biểu diễn ranh giới lưu trước khi handoff cho worker hoặc publisher khác.

Không gọi subscribe() bên trong service để ép save chạy. Caller phải nhận Mono và ghép nó vào pipeline của mình.

## 7. Tải session và xử lý trường hợp không tồn tại

findById() trả về Mono<S>. Khi session không tồn tại hoặc đã hết hạn, publisher hoàn tất mà không phát Session. Trong Reactor, giá trị null không được phát như một phần tử Mono; hãy xử lý trường hợp rỗng bằng switchIfEmpty.

Ví dụ:

~~~java
public Mono<WorkflowState> loadWorkflow(String sessionId) {
    return this.sessions.findById(sessionId)
            .switchIfEmpty(Mono.error(
                    new SessionNotFoundException(sessionId)))
            .map(session -> new WorkflowState(
                    session.getId(),
                    session.getAttribute("workflow.id"),
                    session.getAttribute("workflow.status")
            ));
}
~~~

Không gọi block() để kiểm tra kết quả. Hãy để lỗi được truyền theo pipeline tới WebExceptionHandler, controller advice hoặc tầng xử lý lỗi tương ứng.

Nếu nghiệp vụ cho phép session không tồn tại, có thể dùng default value:

~~~java
return sessions.findById(sessionId)
        .map(session -> session.getAttribute("theme"))
        .defaultIfEmpty("light");
~~~

Không tự tạo session mới bằng ID cũ khi findById() rỗng. Session có thể đã bị logout, hết hạn hoặc bị thu hồi; việc tạo lại trạng thái xác thực từ ID cũ có thể phá vỡ chính sách bảo mật.

## 8. Cập nhật rồi lưu theo chuỗi reactive

Khi thao tác trực tiếp với repository, mọi bước cần thiết phải nằm trong cùng pipeline. Ví dụ:

~~~java
public Mono<Void> updateStatus(String sessionId, String status) {
    return sessions.findById(sessionId)
            .switchIfEmpty(Mono.error(
                    new SessionNotFoundException(sessionId)))
            .flatMap(session -> {
                session.setAttribute("workflow.status", status);
                return sessions.save(session);
            });
}
~~~

flatMap được dùng vì callback trả về Mono<Void>. Nếu dùng map, kết quả sẽ là Mono<Mono<Void>> và thao tác save bên trong không được tự động ghép vào pipeline ngoài.

Để trả về một giá trị sau khi lưu:

~~~java
public Mono<String> updateAndReturn(String sessionId, String status) {
    return sessions.findById(sessionId)
            .switchIfEmpty(Mono.error(
                    new SessionNotFoundException(sessionId)))
            .flatMap(session -> {
                session.setAttribute("workflow.status", status);
                return sessions.save(session)
                        .thenReturn(status);
            });
}
~~~

thenReturn bỏ qua giá trị phát ra từ publisher trước và phát status sau khi publisher trước hoàn tất. Đây là cách phổ biến để tuần tự hóa một thao tác ghi rồi đến kết quả hoặc thao tác kế tiếp.

## 9. Xóa session theo cách không chặn

deleteById() trả về Mono<Void>. Hãy trả publisher đó cho caller hoặc nối bước tiếp theo bằng then.

~~~java
public Mono<Void> revokeSession(String sessionId) {
    return sessions.deleteById(sessionId);
}
~~~

Nếu cần trả về response sau khi xóa:

~~~java
public Mono<ServerResponse> logout(String sessionId) {
    return sessions.deleteById(sessionId)
            .then(ServerResponse.noContent().build());
}
~~~

Không gọi deleteById(sessionId).block() trong controller. Cũng không giả định thao tác xóa hoàn tất ngay khi phương thức deleteById() trả về; phương thức trả về publisher mô tả thao tác, việc thực thi và hoàn tất diễn ra khi pipeline được subscribe.

Nếu cần thu hồi WebSession của request hiện tại, ưu tiên API WebSession.invalidate() và để WebSession integration xử lý repository cùng cookie. Dùng deleteById trực tiếp khi đã có session ID và service chịu trách nhiệm quản lý repository.

## 10. Mono là mô tả công việc, không phải kết quả đã có

Một lỗi thường gặp là tạo Mono rồi cho rằng công việc đã chạy:

~~~java
Mono<String> sessionId = sessions.createSession()
        .map(Session::getId);
~~~

Ở đây sessionId là một publisher. Nó chưa phải String và không thể được dùng như ID ngay lập tức.

Cách đúng là ghép publisher vào luồng xử lý:

~~~java
return sessions.createSession()
        .flatMap(session -> sessions.save(session)
                .thenReturn(session.getId()));
~~~

WebFlux subscribe vào publisher trả về từ controller hoặc handler. Với service, caller sẽ tiếp tục ghép publisher. Không gọi subscribe() rời rạc chỉ để kích hoạt công việc, vì như vậy service tự tạo một luồng thực thi tách khỏi request và mất khả năng điều phối thứ tự, lỗi, cancellation và context.

## 11. Không dùng block(), subscribe() hoặc chờ đồng bộ trong event loop

Các thao tác sau thường làm hỏng lợi ích của reactive:

~~~java
// Không dùng trong request WebFlux
Session session = sessions.findById(id).block();
sessions.save(session).block();
~~~

block() giữ thread cho đến khi có kết quả. Trên event-loop thread, một thao tác như vậy có thể làm nhiều request khác cùng event loop bị chậm hoặc không được xử lý.

Cũng không nên gọi subscribe() trong service:

~~~java
// Không dùng để lưu session rồi trả response ngay
sessions.save(session).subscribe();
return Mono.just("saved");
~~~

Response có thể được trả về trước khi save hoàn tất. Lỗi persistence cũng không còn nằm trong pipeline của request.

Không dùng Thread.sleep(), Future.get(), CompletableFuture.join() hoặc I/O blocking khác trên event loop. Hãy dùng operator reactive tương ứng và trả publisher cho framework.

## 12. Tránh tạo publisher từ lời gọi blocking đã xảy ra

Đoạn mã sau vẫn blocking:

~~~java
return Mono.just(jdbcRepository.findById(id));
~~~

Lời gọi JDBC chạy trước khi Mono.just được tạo. Publisher không thể làm cho lời gọi đã xảy ra trở thành không chặn.

Nếu bắt buộc phải gọi API blocking cũ trong một giai đoạn chuyển tiếp, có thể cô lập nó trên boundedElastic:

~~~java
return Mono.fromCallable(() -> jdbcRepository.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là biện pháp tương thích, không phải repository reactive thực sự. Thread boundedElastic vẫn bị chiếm trong lúc JDBC chờ. Cần giới hạn concurrency, timeout và theo dõi hàng đợi. Với session trong WebFlux, nên chọn ReactiveSessionRepository có driver không chặn thay vì bọc JDBC blocking quanh mọi request.

## 13. JDBC SessionRepository không trở thành reactive chỉ nhờ bọc Mono

JdbcIndexedSessionRepository dùng JdbcOperations và triển khai SessionRepository đồng bộ. Nó không phải ReactiveSessionRepository. Không thể truyền bean này vào EnableSpringWebSession hoặc mong WebFlux tự biến các thao tác JDBC thành non-blocking.

Nếu ứng dụng cần reactive session store, hãy dùng implementation hỗ trợ ReactiveSessionRepository, chẳng hạn ReactiveRedisSessionRepository. ReactiveMapSessionRepository phù hợp cho test hoặc nơi cung cấp Map không chặn; ConcurrentHashMap chỉ chia sẻ trong một JVM.

Nếu hệ thống bắt buộc lưu session bằng JDBC, có thể tiếp tục dùng Servlet stack với SessionRepositoryFilter hoặc cô lập JDBC operations trên boundedElastic trong WebFlux như giải pháp chuyển tiếp. Hãy mô tả rõ giới hạn concurrency và chấp nhận rằng I/O JDBC vẫn blocking.

Không chạy JdbcTemplate, JPA EntityManager hoặc JDBC transaction trên event loop. Không đưa một blocking SessionRepository vào một adapter reactive giả chỉ để thỏa kiểu Mono.

## 14. Nguồn dữ liệu Redis reactive

ReactiveRedisSessionRepository sử dụng Spring Data ReactiveRedisOperations. Vì driver trả publisher, repository có thể ghép thao tác Redis vào Reactor pipeline mà không buộc event-loop thread chờ đồng bộ.

Cấu hình production thường cần:

- ReactiveRedisConnectionFactory, thường dùng Lettuce.
- Namespace riêng cho ứng dụng và môi trường.
- Serialization tương thích với các instance.
- Timeout và connection settings phù hợp.
- Chính sách TTL và cleanup.
- Giám sát latency, lỗi kết nối và dung lượng Redis.

Annotation EnableRedisWebSession có thể cấu hình repository và WebSessionManager. Nếu tự tạo ReactiveRedisSessionRepository, cần cấu hình ReactiveRedisTemplate cùng serialization context đúng kiểu dữ liệu mà session attributes sử dụng.

Không dùng RedisTemplate đồng bộ trong một reactive session service chỉ vì nó kết nối cùng Redis server. RedisTemplate và ReactiveRedisTemplate là hai API khác nhau; dùng nhầm template có thể đưa blocking I/O vào event loop.

## 15. FlushMode và thời điểm persistence

ReactiveRedisSessionRepository theo dõi những thay đổi của Session và có thể chỉ ghi các thuộc tính đã thay đổi. FlushMode quyết định thời điểm thay đổi được đẩy xuống Redis.

- ON_SAVE: mặc định ghi khi repository save được gọi.
- IMMEDIATE: ghi sớm nhất có thể khi thay đổi được thực hiện.

Tên enum và cách cấu hình cụ thể cần đối chiếu phiên bản Spring Session đang dùng. Với WebSession integration, framework quản lý vòng đời save. Với code gọi repository trực tiếp, hãy nối save() vào pipeline và chỉ phát kết quả handoff sau khi publisher hoàn tất.

IMMEDIATE có thể tăng số thao tác ghi và làm thay đổi latency. Nó không làm chuỗi nhiều thao tác trở thành transaction nguyên tử, cũng không thay thế xử lý lỗi hoặc kiểm soát cập nhật đồng thời.

## 16. Mono.defer và thời điểm tạo thao tác

Mono.defer trì hoãn việc tạo publisher con đến lúc subscription. Điều này hữu ích khi cần đọc context hoặc tạo thao tác theo từng subscription.

Ví dụ:

~~~java
public Mono<String> createForRequest(String workflowId) {
    return Mono.defer(() -> sessions.createSession())
            .flatMap(session -> {
                session.setAttribute("workflow.id", workflowId);
                return sessions.save(session)
                        .thenReturn(session.getId());
            });
}
~~~

Không phải mọi phương thức đều cần bọc trong defer. Nếu repository method đã trả publisher đúng cách, có thể gọi trực tiếp. Dùng defer khi việc tạo publisher có side effect đồng bộ, phụ thuộc dữ liệu tại thời điểm subscription hoặc cần bảo đảm mỗi subscription tạo một thao tác riêng.

Tránh đặt lệnh blocking trong defer với suy nghĩ rằng defer tự làm nó không chặn. Defer chỉ trì hoãn thời điểm gọi; nó không chuyển lệnh sang scheduler khác.

## 17. Xử lý lỗi theo tín hiệu reactive

Trong reactive pipeline, lỗi được truyền như một tín hiệu terminal. Hãy xử lý lỗi ở nơi có đủ thông tin nghiệp vụ.

Ví dụ ánh xạ lỗi repository:

~~~java
public Mono<String> saveWorkflow(MapSession session) {
    return sessions.save(session)
            .thenReturn(session.getId())
            .onErrorMap(error ->
                    new SessionPersistenceException(
                            "Cannot persist workflow session", error));
}
~~~

Các operator thường dùng:

| Operator | Công dụng |
|---|---|
| doOnError | Quan sát hoặc ghi log lỗi; không thay thế lỗi |
| onErrorMap | Chuyển loại exception |
| onErrorResume | Chuyển sang publisher thay thế khi có lỗi |
| retryWhen | Thử lại theo policy khi lỗi phù hợp |
| switchIfEmpty | Xử lý publisher hoàn tất rỗng |
| timeout | Giới hạn thời gian chờ publisher |

Không dùng onErrorResume để biến mọi lỗi lưu session thành kết quả thành công. Nếu session không được lưu, không trả session ID như thể đã persist. Chỉ retry lỗi tạm thời có thể thử lại an toàn; tránh retry lỗi schema, serialization hoặc lỗi xác thực Redis.

## 18. Retry và idempotency

Một thao tác save có thể đã đến Redis trước khi client nhận timeout. Nếu retry, ứng dụng cần hiểu liệu thao tác có thể lặp an toàn hay không.

Các nguyên tắc:

- Phân biệt lỗi trước khi gửi lệnh với timeout không rõ kết quả.
- Không retry vô hạn.
- Dùng backoff và jitter khi store tạm thời không sẵn sàng.
- Không tạo session mới mỗi lần retry nếu mục tiêu là lưu cùng một session.
- Dùng workflow ID hoặc idempotency key cho nghiệp vụ.
- Không dùng session ID làm idempotency key cho mọi loại command.
- Ghi metric số lần retry và tỷ lệ retry thành công.

Nếu publisher được subscribe lại, các thao tác đặt bên trong có thể chạy lại. Dùng Mono.defer và vị trí tạo Session có chủ đích để không vô tình tạo nhiều session mới trong mỗi lần retry.

## 19. Cancellation và client ngắt kết nối

WebFlux hỗ trợ cancellation khi subscriber không còn quan tâm đến kết quả, ví dụ client đóng kết nối hoặc timeout ở tầng trên hủy pipeline. Cancellation có thể được truyền xuống publisher và driver để dừng công việc nếu hỗ trợ.

Tuy nhiên, cancellation không phải rollback. Một lệnh Redis có thể đã được gửi và được thực thi trước khi cancellation tới. Vì vậy:

- Không dựa vào cancellation để đảo ngược save đã hoàn tất.
- Không publish công việc phụ trước khi save cần thiết hoàn tất.
- Dùng idempotency cho side effect có thể lặp.
- Xử lý trạng thái không rõ kết quả sau timeout.
- Tránh đặt side effect trong doOnNext nếu cần bảo đảm thứ tự hoàn tất.

Nếu cần lưu session rồi publish task, ghép chúng tuần tự:

~~~java
return sessions.save(session)
        .then(taskPublisher.publish(task))
        .thenReturn(session.getId());
~~~

Khi save lỗi, task publisher không được chạy. Khi client hủy request, pipeline có thể bị cancel; nếu công việc phải tiếp tục độc lập với client, hãy chuyển nó sang workflow/outbox bền vững thay vì gắn vòng đời job vào request.

## 20. flatMap, concatMap và giới hạn concurrency

flatMap cho phép các publisher con chạy chồng lấn. Điều này hữu ích khi xử lý nhiều session độc lập, nhưng không nên dùng để chạy song song các bước phụ thuộc thứ tự trên cùng một session.

Ví dụ xử lý batch:

~~~java
Flux<String> savedIds = Flux.fromIterable(workflowIds)
        .flatMap(id -> createAndSaveSession(id), 16);
~~~

Tham số 16 giới hạn số publisher con đang hoạt động đồng thời. Nếu thứ tự phải được giữ hoặc mỗi thao tác phụ thuộc kết quả trước, dùng concatMap:

~~~java
return Flux.fromIterable(workflowIds)
        .concatMap(this::createAndSaveSession);
~~~

Không để flatMap concurrency vô hạn khi batch lớn. Nó có thể tạo quá nhiều request tới Redis, chiếm connection pool và làm tăng bộ nhớ giữ các publisher đang chờ. Chọn mức concurrency dựa trên capacity của store và đo đạc thực tế.

## 21. Mutable Session và cập nhật đồng thời

Session là object có thể thay đổi. Reactive không làm object này trở thành immutable hoặc thread-safe. Không chia sẻ cùng một instance Session cho nhiều pipeline song song cùng sửa thuộc tính.

Ví dụ nguy hiểm:

~~~java
Mono<Void> first = updateCart(session);
Mono<Void> second = updatePreferences(session);

return Mono.when(first, second);
~~~

Nếu cả hai pipeline cùng sửa và save cùng Session, thứ tự ghi và trạng thái dirty có thể khó dự đoán. Hãy tuần tự hóa thay đổi hoặc thiết kế các thuộc tính độc lập với cơ chế versioning phù hợp.

ReactiveSessionRepository không tự cung cấp một hợp đồng compare-and-set chung cho mọi implementation. Nếu cần chống lost update, hãy dùng atomic operation, optimistic version hoặc kho dữ liệu nghiệp vụ có transaction. Không dùng session làm bộ đếm phân tán hoặc nguồn chuẩn cho số dư, đơn hàng và tồn kho.

## 22. Reactor Context và bảo mật reactive

Reactive pipeline có thể đổi thread giữa các operator. Không dựa vào ThreadLocal hoặc SecurityContextHolder kiểu imperative để truyền principal qua mọi bước.

Trong Spring Security WebFlux, dùng reactive security context và các API tích hợp của framework. Khi cần đọc principal trong service, ghép nó vào pipeline bằng ReactiveSecurityContextHolder hoặc nhận principal từ controller theo cách được hỗ trợ.

Không lưu session ID hoặc cookie vào Reactor Context nếu không cần. Context không phải kho bí mật và có thể được quan sát bởi operator hoặc logging code. Không log toàn bộ context.

Session authentication và repository lookup là hai việc riêng: tìm thấy Session không tự chứng minh người dùng có quyền truy cập workflow hoặc tenant. Luôn kiểm tra authorization ở tầng nghiệp vụ.

## 23. Tùy biến ReactiveSessionRepository

Khi cần repository riêng, implementation phải tuân thủ contract reactive và bảo đảm các thao tác I/O không chặn.

Một skeleton khái niệm:

~~~java
public final class CustomReactiveSessionRepository
        implements ReactiveSessionRepository<CustomSession> {

    @Override
    public Mono<CustomSession> createSession() {
        return Mono.fromSupplier(CustomSession::new);
    }

    @Override
    public Mono<CustomSession> findById(String id) {
        return reactiveStore.find(id);
    }

    @Override
    public Mono<Void> save(CustomSession session) {
        return reactiveStore.put(session.getId(), session);
    }

    @Override
    public Mono<Void> deleteById(String id) {
        return reactiveStore.delete(id);
    }
}
~~~

reactiveStore trong ví dụ đại diện cho một adapter có API reactive thực sự. Không thay nó bằng JDBC, Files API đồng bộ hoặc RedisTemplate blocking.

Một implementation production cần giải quyết thêm:

- ID đủ ngẫu nhiên và không dễ đoán.
- Serialization ổn định và kiểm soát kiểu thuộc tính.
- TTL và expiration.
- Giới hạn payload và số thuộc tính.
- Cập nhật delta nếu phù hợp.
- Hành vi khi findById không có kết quả.
- Delete idempotent theo contract.
- Lỗi kết nối và retry.
- Quan sát metrics và cleanup.
- Tính nhất quán khi nhiều instance cùng truy cập.

Session truyền vào save() nên là Session do chính repository tạo hoặc tải. Theo dõi thay đổi giúp giảm ghi dữ liệu và tránh ghi toàn bộ object không cần thiết.

## 24. Expiration và cleanup trong reactive repository

ReactiveSessionRepository chỉ định nghĩa API quản lý Session; không phải implementation nào cũng cung cấp cùng một cơ chế expiration và cleanup.

Reactive Redis repository có thể dùng TTL của Redis và logic repository để không trả session đã hết hạn. ReactiveMapSessionRepository không tự biến ConcurrentHashMap thành kho phân tán hoặc tự có cleanup production hoàn chỉnh. Với repository tự viết, phải xác định:

- TTL được lưu và cập nhật ở đâu.
- findById xử lý session hết hạn như thế nào.
- Cleanup chạy theo lịch hay theo truy cập.
- Cleanup có thể tranh chấp với save hoặc gia hạn không.
- Event expiration có được phát hay không.
- Dữ liệu phụ và index được dọn như thế nào.

EnableSpringWebSession không tự cấu hình mọi hạ tầng expiration cho một repository tùy ý. Đọc tài liệu implementation và kiểm thử TTL thực tế. Không dựa vào việc key bị xóa vật lý đúng thời điểm để quyết định authorization; repository phải từ chối session đã hết hạn theo logic của nó.

## 25. Phân biệt WebSession save lifecycle và save trực tiếp

Khi controller dùng WebSession, WebFlux cùng WebSessionManager quản lý vòng đời lưu phiên. Việc truy cập exchange.getSession() trả về Mono<WebSession>; khi thay đổi thuộc tính hoặc bắt đầu session, integration sẽ lưu theo lifecycle đã cấu hình.

Khi service gọi ReactiveSessionRepository trực tiếp, service chịu trách nhiệm ghép save() vào pipeline. Không nhầm hai mô hình:

| Tình huống | Cách làm |
|---|---|
| Controller cần lưu theme, locale hoặc trạng thái UI | Dùng WebSession |
| Controller cần logout session hiện tại | Dùng WebSession.invalidate() và Spring Security logout integration |
| Service cần tạo session riêng cho workflow | Dùng ReactiveSessionRepository.createSession() rồi save() |
| Worker cần tải session theo ID | Dùng findById() trong pipeline reactive |
| Ứng dụng cần tích hợp store riêng | Implement ReactiveSessionRepository và đăng ký WebSession integration |

Không cố gọi phương thức save() của repository trên WebSession. WebSession và Session là hai abstraction khác nhau; WebSessionStore là adapter quản lý việc chuyển đổi.

## 26. Kiểm thử bằng StepVerifier và WebTestClient

Kiểm thử reactive cần subscribe đúng cách và xác minh tín hiệu. Reactor cung cấp StepVerifier để kiểm tra Mono/Flux mà không cần block trong code ứng dụng.

Ví dụ kiểm tra service tạo session:

~~~java
StepVerifier.create(service.createSession("wf-100"))
        .expectNextMatches(id -> id != null && !id.isBlank())
        .verifyComplete();
~~~

Các trường hợp nên kiểm thử:

1. createSession phát ra một Session.
2. save hoàn tất trước khi service phát session ID.
3. findById phát Session khi tồn tại.
4. findById hoàn tất rỗng khi không có session.
5. switchIfEmpty chuyển trường hợp thiếu session thành lỗi nghiệp vụ.
6. deleteById hoàn tất khi session tồn tại hoặc không tồn tại.
7. save lỗi làm pipeline lỗi và không phát kết quả thành công.
8. retry chỉ áp dụng cho lỗi tạm thời đã chọn.
9. Cancellation không làm publish task chạy trước save.
10. Hai pipeline không sửa cùng mutable Session đồng thời.
11. TTL được kiểm thử trên Redis thật hoặc container tương thích.
12. WebSession được lưu và khôi phục qua WebTestClient.
13. Logout invalidate session và request sau không còn xác thực.
14. Nhiều instance cùng đọc được session từ Redis dùng chung.
15. Không có block(), Thread.sleep() hoặc JDBC blocking trên event-loop path.

Dùng mock repository để kiểm tra thứ tự operator; dùng Redis integration test để xác minh serialization, TTL và persistence. WebTestClient phù hợp để kiểm tra hành vi HTTP reactive và cookie/session lifecycle.

## 27. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Request WebFlux bị treo khi đọc session | Có block() hoặc driver blocking trên event loop | Tìm block, JDBC, RedisTemplate và client blocking |
| Session không được lưu | Mono save chưa được ghép hoặc publisher không được subscribe ở ranh giới framework | Kiểm tra return chain và flatMap/then |
| Response trả trước khi save xong | Gọi subscribe() rời rạc rồi trả Mono khác | Ghép save bằng then hoặc flatMap |
| findById không tìm thấy session vừa tạo | Save chưa hoàn tất, namespace khác hoặc TTL đã hết | Kiểm tra thứ tự, namespace và timeout |
| Mono<Mono<Void>> | Dùng map khi callback trả publisher | Dùng flatMap |
| Không xử lý session không tồn tại | Bỏ qua Mono.empty | Dùng switchIfEmpty/defaultIfEmpty |
| Redis lỗi làm toàn bộ request retry liên tục | retry policy quá rộng hoặc không giới hạn | Phân loại lỗi, backoff và retry limit |
| Tải tăng làm Redis quá tải | flatMap concurrency quá cao hoặc flush quá thường xuyên | Giới hạn concurrency, đo writes và latency |
| Session attributes bị mất cập nhật | Nhiều pipeline sửa cùng object hoặc lost update | Tuần tự hóa, versioning hoặc store atomic |
| JDBC chạy trong reactive controller | Dùng JdbcIndexedSessionRepository như reactive store | Chuyển sang reactive store hoặc cô lập blocking |
| Session không hết hạn trong repository tự viết | Chưa triển khai TTL/cleanup | Bổ sung expiration semantics và integration test |

Khi điều tra, theo dõi thời gian subscribe, thời gian hoàn tất, scheduler, lỗi driver và repository latency. Không ghi session ID hoặc cookie thô vào log.

## 28. Quy trình triển khai chuỗi không chặn

Trước khi đưa ReactiveSessionRepository vào production:

1. Xác nhận ứng dụng thực sự dùng Spring WebFlux và WebSession.
2. Chọn ReactiveSessionRepository có driver I/O không chặn.
3. Ưu tiên WebSession integration cho controller và handler.
4. Chỉ dùng repository trực tiếp khi cần service-level lifecycle rõ ràng.
5. Ghép create/find/save/delete bằng flatMap, map, then và switchIfEmpty phù hợp.
6. Không gọi block(), subscribe() rời rạc, Thread.sleep() hoặc Future.get() trên request path.
7. Không dùng JdbcIndexedSessionRepository hoặc RedisTemplate blocking trong event loop.
8. Nếu tạm thời phải gọi legacy blocking API, cô lập trên boundedElastic và giới hạn concurrency.
9. Cấu hình TTL, namespace, serializer và cleanup theo implementation.
10. Giới hạn flatMap concurrency khi xử lý batch.
11. Không chia sẻ mutable Session cho nhiều pipeline đồng thời.
12. Xử lý cancellation, timeout, retry và idempotency.
13. Kiểm thử bằng StepVerifier, WebTestClient và Redis integration test.
14. Đo repository latency, connection pool, Redis memory và lỗi persistence.
15. Kiểm thử nhiều instance để xác nhận mọi node dùng cùng store và namespace.

## Kết luận

ReactiveSessionRepository cung cấp createSession, findById, save và deleteById dưới dạng Mono để Spring Session có thể làm việc với WebFlux mà không chặn event loop. Trong ứng dụng web, nên dùng WebSession integration để WebSessionManager và WebSessionStore điều phối vòng đời; chỉ gọi repository trực tiếp khi service cần kiểm soát rõ thao tác lưu. Chuỗi xử lý phải ghép publisher bằng flatMap, then, switchIfEmpty và operator phù hợp, không gọi block hoặc subscribe rời rạc. Driver phải thực sự reactive: bọc JDBC blocking trong Mono không làm I/O trở thành non-blocking. Hãy cấu hình TTL và cleanup theo repository, giới hạn concurrency, tránh cập nhật đồng thời cùng mutable Session, và kiểm thử cancellation, lỗi, serialization cùng persistence trên Redis thật trước khi triển khai nhiều instance.

## Tài liệu tham khảo

- Spring Session API Documentation: https://docs.spring.io/spring-session/reference/api.html
- ReactiveSessionRepository Javadoc: https://docs.spring.io/spring-session/docs/current/api/org/springframework/session/ReactiveSessionRepository.html
- Spring Session WebSession Integration: https://docs.spring.io/spring-session/reference/web-session.html
- Spring Session Reactive Redis Repository: https://docs.spring.io/spring-session/reference/api.html
- Spring Framework WebFlux Reference: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Project Reactor Reference Guide: https://projectreactor.io/docs/core/release/reference/
