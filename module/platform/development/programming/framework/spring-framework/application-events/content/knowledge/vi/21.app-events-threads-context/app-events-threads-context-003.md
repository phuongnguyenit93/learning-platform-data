# SecurityContext trong async listener của Spring Application Events

Trong Spring Security, danh tính người dùng đã xác thực thường được truy cập qua `SecurityContextHolder`. Một `@EventListener` đồng bộ của Spring Framework mặc định có thể đọc được Authentication của thread đang phát event. Nhưng khi thêm `@Async`, Spring gửi việc xử lý sang một executor khác. Với chiến lược mặc định `SecurityContextHolder.MODE_THREADLOCAL`, **SecurityContext không tự di chuyển sang worker thread**. Vì vậy listener bất đồng bộ có thể thấy `null` thay vì người dùng đã phát event.

Cách giải quyết đúng không phải là dựa vào tên thread hoặc bật kế thừa ThreadLocal toàn cục, mà là xác định nhu cầu quyền của công việc, sau đó **truyền SecurityContext theo từng tác vụ** nếu thật sự cần, ví dụ bằng `DelegatingSecurityContextAsyncTaskExecutor`. Lớp này bọc task, đưa context vào thread thực thi và dọn/khôi phục thread context theo cơ chế của Spring Security sau khi task hoàn thành.

Bài học giải thích cơ chế, hai cách thiết kế (truyền context và truyền actorId nghiệp vụ), cách cấu hình `@Async`, kiểm thử Java 17+ với JUnit 5, và những rủi ro về quyền, thread pool, transaction, reactive context, lỗi async và xử lý event lâu dài.

## 1. SecurityContext thực sự thuộc phạm vi nào?

Các đối tượng có vai trò khác nhau:

| Đối tượng | Nội dung | Điều không tự bảo đảm |
| --- | --- | --- |
| `Authentication` | Principal, trạng thái xác thực và authorities | Quyền hiện hành ở một thời điểm tương lai |
| `SecurityContext` | Container mang Authentication | Một immutable snapshot độc lập hoàn toàn |
| `SecurityContextHolder` | Cổng truy cập theo `SecurityContextHolderStrategy` | Context của mọi thread luôn giống nhau |
| `ApplicationEventPublisher` | Phát event đến listener của Spring | Truyền SecurityContext hoặc lưu event bền vững |
| `@Async` | Schedule method invocation qua executor | Sao chép SecurityContext, transaction, request scope hay MDC tự động |

Spring Security servlet/imperative thường dùng `MODE_THREADLOCAL`. Một thread request có thể chứa Authentication `alice`; thread trong pool của listener không mặc nhiên mang Authentication đó.

~~~text
Đồng bộ (mặc định):
  request-thread: SecurityContext(alice)
       |
       +-- publishEvent(DocumentApproved)
              |
              +-- @EventListener xử lý trên request-thread
                     -> SecurityContextHolder: alice

@Async với executor thường:
  request-thread: SecurityContext(alice)
       |
       +-- publishEvent(DocumentApproved)
              |
              +-- schedule task
       |
       +-- trả về / kết thúc request

  worker-thread: SecurityContext(thường trống)
       |
       +-- @Async @EventListener
              -> getAuthentication() có thể là null
~~~

Do đó, việc `event.actorId()` có giá trị `alice` không có nghĩa là `SecurityContextHolder` trên worker thread đã mang Authentication của alice. **Payload nghiệp vụ** và **security execution context** là hai thứ độc lập.

## 2. Vì sao thêm @Async có thể làm mất danh tính?

Một listener thông thường:

~~~java
@EventListener
public void onApproved(DocumentApproved event) {
    Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
    // Trong dispatch đồng bộ mặc định, thường đọc context của caller.
}
~~~

Phiên bản bất đồng bộ:

~~~java
@Async("backgroundExecutor")
@EventListener
public void onApproved(DocumentApproved event) {
    Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
    // Không giả định authentication của caller tồn tại ở worker thread.
}
~~~

Đây là các trích đoạn bên trong Spring-managed bean; cần import và bean `backgroundExecutor`. `@EnableAsync` cần được bật. Spring xử lý `@Async` bằng proxy/interceptor trong mode mặc định, nên direct self-invocation `this.onApproved(...)` không phải phép kiểm thử hợp lệ cho async execution.

Khi dispatch event thông qua `SimpleApplicationEventMulticaster` mặc định, lời gọi đến async proxy thường xảy ra ngay trên thread phát event; proxy gửi task sang executor, và executor được bọc có thể capture context trên thread này. Nếu ứng dụng **cũng cấu hình multicaster chạy trên executor khác**, thread submit có thể không còn là request thread. Vì vậy phải xác định chính xác **thread nào submit task**, không chỉ nơi gọi `publishEvent`.

### Lỗi điển hình

- `getAuthentication()` trả `null`, gọi `getName()` trực tiếp gây `NullPointerException`.
- Listener gọi một method được bảo vệ và bị từ chối vì SecurityContext của worker thiếu user/authorities.
- Task kế tiếp thừa hưởng principal của task trước nếu code tự đặt context nhưng không dọn.
- Unit test gọi trực tiếp method listener pass, còn integration test publish event thật và chạy executor thì fail.
- Người phát event đã logout hoặc quyền thay đổi, nhưng task đang giữ thông tin từ thời điểm submit; phải xét chính sách authorization riêng.

## 3. DelegatingSecurityContextAsyncTaskExecutor truyền context theo từng task

Spring Security cung cấp lớp `org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor`. Nó triển khai `AsyncTaskExecutor`, bọc `Runnable` hoặc `Callable` để thiết lập SecurityContext cho thời gian thực thi trên worker.

~~~text
submitter thread:
  SecurityContextHolder = alice
            |
            v
  DelegatingSecurityContextAsyncTaskExecutor.submit(task)
            |
            +-- lấy context của thread submit
            +-- wrap task với security context
            v
pool worker:
  cài đặt context được capture -> listener thấy alice
  try { xử lý event; }
  finally { dọn/khôi phục context trước đó; }
~~~

Trong constructor một tham số, context được lấy **khi task được submit**, không phải chụp một lần cho cả đời bean. Constructor hai tham số nhận một `SecurityContext` cố định: mọi task có thể chạy dưới danh tính cố định đó. Chỉ dùng trường hợp cố định khi nghiệp vụ thực sự yêu cầu một service identity được cấp quyền có chủ đích; không lấy context của admin lúc khởi động rồi vô tình áp dụng cho mọi user.

Cấu hình cho ứng dụng Spring MVC/imperative:

~~~java
@Configuration
@EnableAsync
class AsyncSecurityConfiguration {

    @Bean("notificationsPool")
    ThreadPoolTaskExecutor notificationsPool() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(100);
        pool.setThreadNamePrefix("notifications-");
        return pool;
    }

    @Bean("secureNotifications")
    AsyncTaskExecutor secureNotifications(
            @Qualifier("notificationsPool")
            ThreadPoolTaskExecutor delegate) {
        return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
    }
}
~~~

Đây là **trích đoạn** cấu hình; cần import `@Configuration`, `@EnableAsync`, `@Bean`, `@Qualifier`, `ThreadPoolTaskExecutor`, `AsyncTaskExecutor` và `DelegatingSecurityContextAsyncTaskExecutor`.

Bước quyết định ở listener là chọn **đúng executor**:

~~~java
@Component
class NotificationListener {

    @Async("secureNotifications")
    @EventListener
    public void onApproved(DocumentApproved event) {
        Authentication auth = SecurityContextHolder.getContext()
            .getAuthentication();

        if (auth == null) {
            // Xử lý không có principal theo hợp đồng nghiệp vụ.
            return;
        }

        notificationService.sendFor(event.documentId(), auth.getName());
    }
}
~~~

Đây là trích đoạn, yêu cầu `DocumentApproved`, `notificationService` và các imports tương ứng. **Không chỉ kiểm tra `auth.isAuthenticated()` rồi cho rằng luôn là user thật**: tùy cấu hình, AnonymousAuthenticationToken vẫn có thể được đánh dấu authenticated. Nếu quyền quan trọng, dùng authorization policy chính thức của hệ thống và phân biệt anonymous authentication.

**Chú ý:** khai báo bean `secureNotifications` không tự làm mọi `@Async` sử dụng nó. Cần `@Async("secureNotifications")` hoặc thiết lập async default executor có chủ đích. Một tên bean sai có thể khiến task chạy executor khác hoặc lỗi lúc runtime.

## 4. Kiểm thử thực: plain executor so với security-delegating executor

Ví dụ dưới là một bộ test Spring Context chạy Java 17+, Spring Framework 6.2 và Spring Security 6.4. Nó cố ý dùng **hai thread pool tách biệt** để đối chiếu trường hợp không truyền và có truyền context. Không cần chạy HTTP server hoặc truy cập database, bởi trọng tâm là event dispatch, async proxy và thread-local security context.

Các trường hợp được kiểm chứng:

1. Thread phát event có user `alice`, plain executor không tự có user đó.
2. Wrapped executor nhận SecurityContext của `alice` khi submit.
3. Sau khi chuyển sang user `bob`, wrapped executor nhận `bob`.
4. Khi thread phát event clear context, task tiếp theo không bị dùng lại principal `bob`.

### 4.1. Gradle dependencies

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform('org.springframework:spring-framework-bom:6.2.9')
    testImplementation 'org.springframework:spring-context'
    testImplementation 'org.springframework:spring-aop'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.springframework.security:spring-security-core:6.4.3'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Nếu dự án dùng Spring Boot, nên ưu tiên bộ phiên bản Framework và Security mà Boot quản lý. Không trộn BOM không tương thích. Test sử dụng `spring-security-core` để thao tác với `SecurityContextHolder` và executor wrapper, không cần dựng security filter chain.

### 4.2. src/test/java/example/events/SecurityContextAsyncEventTest.java

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(SecurityContextAsyncEventTest.Config.class)
class SecurityContextAsyncEventTest {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired Listener observer;

    @BeforeEach
    void reset() {
        SecurityContextHolder.clearContext();
        observer.clear();
    }

    @AfterEach
    void cleanup() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void ordinaryPoolLosesCallerButSecuredPoolPropagates()
            throws Exception {
        login("alice");
        publisher.publishEvent(new PlainEvent("P-1"));
        publisher.publishEvent(new SecureEvent("S-1"));

        Seen plain = observer.takePlain();
        Seen secured = observer.takeSecured();

        assertEquals("P-1", plain.eventId());
        assertEquals("<none>", plain.user());
        assertTrue(plain.thread().startsWith("plain-"));

        assertEquals("S-1", secured.eventId());
        assertEquals("alice", secured.user());
        assertTrue(secured.thread().startsWith("secure-"));
    }

    @Test
    void contextDoesNotLeakToTheNextTask() throws Exception {
        login("bob");
        publisher.publishEvent(new SecureEvent("S-2"));
        assertEquals("bob", observer.takeSecured().user());

        SecurityContextHolder.clearContext();
        publisher.publishEvent(new SecureEvent("S-3"));
        Seen second = observer.takeSecured();

        assertEquals("S-3", second.eventId());
        assertEquals("<none>", second.user());
    }

    private static void login(String name) {
        Authentication auth = new UsernamePasswordAuthenticationToken(
            name, "not-a-password",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(auth);
        SecurityContextHolder.setContext(context);
    }

    record PlainEvent(String id) {}
    record SecureEvent(String id) {}
    record Seen(String eventId, String user, String thread) {}

    static class Listener {
        private final BlockingQueue<Seen> plain =
            new LinkedBlockingQueue<>();
        private final BlockingQueue<Seen> secured =
            new LinkedBlockingQueue<>();

        @Async("plainExecutor")
        @EventListener
        public void onPlain(PlainEvent event) {
            plain.offer(observe(event.id()));
        }

        @Async("secureExecutor")
        @EventListener
        public void onSecure(SecureEvent event) {
            secured.offer(observe(event.id()));
        }

        private Seen observe(String id) {
            Authentication auth = SecurityContextHolder.getContext()
                .getAuthentication();
            return new Seen(
                id,
                auth == null ? "<none>" : auth.getName(),
                Thread.currentThread().getName()
            );
        }

        Seen takePlain() throws InterruptedException {
            Seen result = plain.poll(5, TimeUnit.SECONDS);
            assertNotNull(result, "plain listener did not finish");
            return result;
        }

        Seen takeSecured() throws InterruptedException {
            Seen result = secured.poll(5, TimeUnit.SECONDS);
            assertNotNull(result, "secure listener did not finish");
            return result;
        }

        void clear() {
            plain.clear();
            secured.clear();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync(proxyTargetClass = true)
    static class Config {

        @Bean("plainExecutor")
        ThreadPoolTaskExecutor plainExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(10);
            pool.setThreadNamePrefix("plain-");
            return pool;
        }

        @Bean("securePool")
        ThreadPoolTaskExecutor securePool() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(10);
            pool.setThreadNamePrefix("secure-");
            return pool;
        }

        @Bean("secureExecutor")
        AsyncTaskExecutor secureExecutor(
                @Qualifier("securePool") ThreadPoolTaskExecutor pool) {
            return new DelegatingSecurityContextAsyncTaskExecutor(pool);
        }

        @Bean
        Listener listener() {
            return new Listener();
        }
    }
}
~~~

### 4.3. Chạy test và đọc kết quả

Tại project có Gradle wrapper:

~~~bash
./gradlew test --tests "example.events.SecurityContextAsyncEventTest"
~~~

Trên Windows PowerShell:

~~~powershell
./gradlew.bat test --tests "example.events.SecurityContextAsyncEventTest"
~~~

Kết quả nằm ở các assertion, không phải những dòng in stdout của Gradle:

| Tình huống | Executor | Principal trong listener mong đợi |
| --- | --- | --- |
| `PlainEvent("P-1")` sau khi login alice | Plain pool | `<none>` |
| `SecureEvent("S-1")` sau khi login alice | Delegating wrapper | `alice` |
| `SecureEvent("S-2")` sau khi login bob | Delegating wrapper | `bob` |
| `SecureEvent("S-3")` sau khi clearContext | Delegating wrapper | `<none>` |

**Vì sao test dùng BlockingQueue và timeout?** `@Async` làm công việc có thể hoàn thành sau khi publisher đã trả về. `poll(5, TimeUnit.SECONDS)` cho test đợi kết quả có giới hạn, thay vì dùng `Thread.sleep(...)` rồi hy vọng scheduler hoàn tất. Nếu task bị lỗi hoặc executor không hoạt động, assertion sẽ fail thay vì treo mãi.

**Vì sao tách hai pool?** Để tránh một executor vô tình áp dụng context propagation cho cả hai nhánh. Mỗi pool một worker trong ví dụ, qua đó có thể quan sát hành vi dọn/khôi phục SecurityContext giữa các task.

**Đừng áp dụng máy móc vào Spring WebFlux:** test ở đây giả định SecurityContextHolder thread-local của Spring Security imperative. Trong ứng dụng reactive, danh tính thông thường được lưu trong Reactor Context, cần cơ chế khác.

## 5. Chọn truyền context hay truyền dữ liệu actor trong event

Tùy yêu cầu nghiệp vụ mà cách xử lý khác nhau.

### Tác vụ cần chạy dưới danh tính người dùng

Ví dụ listener gọi một service có method security và cần đánh giá quyền dựa trên caller tại thời điểm submit. Chọn một executor được bọc, truyền context và kiểm thử chính sách authorization. Chú ý **quyền có thể thay đổi** sau khi task đã lên lịch. Với nghiệp vụ nhạy cảm hoặc chạy lâu, cần cân nhắc kiểm tra lại quyền tại thời điểm xử lý.

### Tác vụ chỉ cần biết ai đã thực hiện thao tác

Đối với email/audit đơn giản, thường chỉ cần lưu một định danh actor đã được xác minh trong payload:

~~~java
public record DocumentApproved(
    String documentId,
    String actorId,
    String correlationId
) {}
~~~

Đây là Java record độc lập. Application service lấy `actorId` từ nguồn Authentication đáng tin cậy tại thời điểm chấp nhận lệnh; không tin một `actorId` do client tùy ý khai báo là bằng chứng đã xác thực. Consumer dùng actor ID cho audit hoặc notification mapping, còn các thao tác cần authorization vẫn áp dụng security policy.

### Tác vụ chạy dài hoặc được giao qua broker

Đừng serialize `SecurityContext` hoặc credentials vào Kafka/RabbitMQ/outbox/HTTP. Hãy dùng event payload tối thiểu, schema version, correlation ID và service identity có quyền hạn thích hợp. Bởi `SecurityContext` là trạng thái runtime trong JVM, nó không tự tồn tại sau restart và không phải capability an toàn để đưa qua tiến trình khác.

| Nhu cầu | Thiết kế ưu tiên | Điều phải kiểm tra |
| --- | --- | --- |
| Caller-scoped async task ngắn | `DelegatingSecurityContextAsyncTaskExecutor` | Capture từ đúng submit thread; cleanup |
| Audit actor | Immutable actorId trong event | ActorId phải xuất phát từ Authentication đáng tin |
| Scheduled/long-running retry job | Service identity, xác thực/authorize khi chạy | Least privilege, quyền bị thu hồi, idempotency |
| Message xuyên service | Integration event độc lập | Không nhúng raw SecurityContext/tokens |
| Async listener không cần security | Không truyền context | Tránh truyền quyền không cần thiết |

## 6. Vì sao MODE_INHERITABLETHREADLOCAL thường không phù hợp?

Spring Security hỗ trợ `SecurityContextHolder.MODE_INHERITABLETHREADLOCAL` để thread mới có thể kế thừa context của thread tạo nó. Tuy nhiên, thread pool thường **tái sử dụng worker thread qua nhiều request**; context được kế thừa lúc tạo thread không phản ánh chính xác user tại thời điểm submit các task về sau. Đổi global strategy sang inheritable có thể tạo lỗi thiếu context hoặc rò rỉ danh tính.

Vì vậy, không bật `MODE_INHERITABLETHREADLOCAL` toàn cục chỉ để “sửa @Async”. Truyền context **theo task** và bảo đảm cleanup là cách phù hợp hơn.

Một đoạn code tự set context không dọn:

~~~java
// SAI nếu chạy trong thread pool:
SecurityContextHolder.setContext(captured);
process(event);
// Thiếu finally; worker có thể giữ context của task trước.
~~~

Trong trường hợp thực sự cần thao tác thủ công, dùng `try/finally` để khôi phục context trước đó/clear theo policy. Spring Security đã có `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextCallable` và các executor wrapper để tránh tự viết logic này.

### SecurityContext có thể mutable

Một wrapper capture SecurityContext không nhất thiết tạo deep copy bất biến. Nếu ứng dụng tiếp tục thay đổi Authentication hoặc context object đã capture, có thể sinh race/hành vi khó dự đoán. Không mutate context dùng chung sau submit; đối với mục đích audit, dùng immutable actor ID và correlation ID. Với tác vụ đặc biệt nhạy cảm, kiểm tra lại quyền khi thực thi thay vì tin rằng quyền từ lúc submit luôn còn hiệu lực.

## 7. SecurityContext không phải transaction, MDC hay Reactor Context

Ba loại context có ý nghĩa khác nhau:

1. **SecurityContext**: Authentication/authorities phục vụ xác thực và phân quyền.
2. **Transaction context**: tài nguyên giao dịch DB, commit/rollback, thường gắn thread trong JDBC.
3. **Logging/tracing context**: correlation ID, MDC, observation context, có thể được truyền qua Micrometer context propagation.

Một task async có thể đã được truyền SecurityContext nhưng **không tham gia transaction JDBC gốc**. Nếu event publish trong `@Transactional`, listener có thể chạy trước commit và đọc trạng thái DB cũ. Nếu business cần xử lý chỉ sau commit, cân nhắc `@TransactionalEventListener(phase = AFTER_COMMIT)` và sau đó thiết kế executor/propagation phù hợp; nếu không được mất event sau crash, cần outbox hoặc registry bền vững.

~~~text
publisher thread:
  [SecurityContext = alice] [DB TX-1]
     -> UPDATE data
     -> publish event
     -> COMMIT hoặc ROLLBACK

async listener worker:
  [SecurityContext = alice, nếu wrapper truyền]
  [DB TX-1 không tự được truyền]
     -> mở transaction khác nếu có thao tác DB riêng
~~~

Với listener `AFTER_COMMIT`, thời điểm task được submit có thể xảy ra trong callback transaction completion, không chính xác là thời điểm application gọi `publishEvent`. Nếu lúc đó SecurityContext đã bị dọn, wrapper không thể tái tạo Authentication cũ. Cần test luồng end-to-end, đặc biệt khi multicaster cũng dùng executor.

### Spring Framework ContextPropagatingTaskDecorator

Spring Framework có `ContextPropagatingTaskDecorator` phối hợp với Micrometer để truyền context phục vụ tracing/MDC. **Đừng kết luận SecurityContext cũng được truyền** trừ khi application thực sự tích hợp context accessors phù hợp và đã kiểm thử. Khi cần propagation cho Spring Security servlet/imperative, các `DelegatingSecurityContext*` wrapper là lựa chọn trực tiếp và minh bạch.

### Reactor/WebFlux SecurityContext

Trong Spring WebFlux, reactive security thường dùng `ReactiveSecurityContextHolder` dựa trên **Reactor subscriber Context**, không phải chỉ dựa vào thread-local `SecurityContextHolder`.

~~~java
// Trích đoạn reactive, cần một Reactor subscription có security context:
Mono<String> principalName =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
~~~

Đoạn này yêu cầu các import tương ứng. Nếu không có context thì `Mono` có thể không phát giá trị. Việc bọc executor imperative bằng `DelegatingSecurityContextAsyncTaskExecutor` **không tự bảo đảm** chuyển Reactor subscriber Context. Khi xử lý WebFlux/Reactive, giữ luồng trong Reactor chain, dùng `ReactiveSecurityContextHolder` và thiết kế riêng khi cắt sang thread/task/message bên ngoài.

## 8. Lỗi phổ biến và cách kiểm thử

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `@Async @EventListener` gọi ngay `getAuthentication().getName()` | Có thể NPE | Kiểm tra auth/null, dùng correct executor khi thật sự cần |
| Có bean executor bọc nhưng method `@Async` không chọn nó | Task vẫn chạy executor không truyền context | Dùng `@Async("secureExecutor")` hoặc cấu hình async default |
| Cố định privileged SecurityContext trên mọi task | Chạy dưới quyền sai | Dùng per-task capture hoặc service identity có chủ đích |
| Bật `MODE_INHERITABLETHREADLOCAL` cho pool | Context sai hoặc cũ trong reused threads | Bọc từng task và dọn trong finally |
| SetContext thủ công không clear | Rò rỉ danh tính sang job khác | `try/finally` hoặc DelegatingSecurityContext wrapper |
| Dùng actorId trong event như bằng chứng xác thực | Quyền giả mạo | Authorization dựa vào identity đã kiểm chứng |
| Cho rằng SecurityContext cũng kéo theo transaction | Đọc DB sai mốc, không tham gia TX gốc | Transaction phase/transaction mới, kiểm thử commit |
| Async listener ném lỗi rồi mong publisher thấy ngay | Exception không truyền như listener sync | AsyncUncaughtExceptionHandler, log, metrics, retry |
| Publish trước commit rồi dùng email/API như side effect | Có thể gửi khi DB rollback | Sau commit hoặc transactional outbox |
| Test assert ngay sau publish | Race condition | BlockingQueue/latch với timeout |

Các kiểm thử thêm cho production: user A và B gửi gần nhau; listener gặp exception; executor bị reject do queue đầy; context không có Authentication; caller logout; quyền bị thu hồi; custom multicaster dùng executor; service có `@PreAuthorize`; after-commit listener; WebFlux nếu có. Đặc biệt, đo `task submitted`, `task completed`, `task failed` và queue saturation để phát hiện task không chạy.

Với `@Async` method trả `void`, lỗi có thể được xử lý bởi `AsyncUncaughtExceptionHandler` hoặc log mặc định. Không suy ra rằng `publishEvent()` chờ được tất cả async listeners hoặc event chắc chắn được gửi. Nếu yêu cầu giao nhận bền vững, thiết kế retry/idempotency và outbox phù hợp thay vì xem SecurityContext propagation là một dạng message delivery.

## 9. Checklist áp dụng

- Đã xác định listener là `@Async`, thực sự được gọi qua Spring proxy và `@EnableAsync` hoạt động.
- Đã chọn executor dành cho listener; tên trong `@Async("...")` khớp với bean dùng propagation.
- Xác định thread **submit task** thực sự có SecurityContext không, đặc biệt với custom multicaster.
- Không giữ privileged context cố định ngoài chủ đích; áp dụng least privilege.
- Worker xử lý trường hợp Authentication vắng mặt và anonymous authentication.
- Không dùng `MODE_INHERITABLETHREADLOCAL` như giải pháp mặc định cho pool.
- Không serialize token, credentials hay SecurityContext vào domain/integration event.
- Không lầm SecurityContext với transaction hoặc Reactor Context.
- Có kiểm thử async thật với timeout, context cleanup giữa các task và error path.
- Có policy rõ ràng cho event sau commit, tác vụ lâu dài, retry và quyền bị thay đổi.

## 10. Câu hỏi tự kiểm tra

**Câu 1:** Vì sao `@EventListener` đồng bộ thấy user nhưng `@Async @EventListener` có thể thấy `null`?

Vì lời gọi bất đồng bộ thực thi ở thread khác, nơi `SecurityContextHolder` với MODE_THREADLOCAL mặc định không có context của caller.

**Câu 2:** Constructor một tham số của `DelegatingSecurityContextAsyncTaskExecutor` khác constructor với fixed context như thế nào?

Constructor một tham số capture SecurityContext từ thread submit theo từng task; constructor có fixed context dùng một context được chỉ định cho các task. Chọn tùy mục đích và phân quyền.

**Câu 3:** Nếu chỉ đưa `actorId` vào payload event, listener có SecurityContext không?

Không. Actor ID phục vụ dữ liệu nghiệp vụ/audit; nó không tự cài đặt Authentication đáng tin vào SecurityContextHolder.

**Câu 4:** Có nên chuyển sang MODE_INHERITABLETHREADLOCAL khi dùng pool không?

Không nên mặc định. Worker threads được tái sử dụng và có thể giữ context không đúng user; dùng wrapper per-task và cleanup.

**Câu 5:** SecurityContext propagation có làm task async cùng JDBC transaction với publisher không?

Không. Transaction và SecurityContext là hai boundary khác nhau. Cần transaction riêng hoặc xử lý after-commit/outbox tùy nghiệp vụ.

**Câu 6:** Spring WebFlux nên đọc SecurityContextHolder thread-local như ứng dụng servlet hay không?

Không mặc định. Reactive security thường nằm trong Reactor Context; dùng `ReactiveSecurityContextHolder` và giữ subscriber context trong pipeline.

**Ghi nhớ:** trong async application events, danh tính không tự theo sang thread pool. Nếu listener thật sự cần quyền của caller, truyền context đúng thời điểm bằng `DelegatingSecurityContextAsyncTaskExecutor`, giới hạn quyền, dọn context sau mỗi task và kiểm thử bằng executor thật. Với tác vụ audit hoặc lâu dài, truyền dữ liệu actor tối thiểu và authorization độc lập thường an toàn, bền vững hơn.

## Tài liệu tham khảo

- [Spring Security – Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html)
- [Spring Security – DelegatingSecurityContextAsyncTaskExecutor Javadoc](https://docs.spring.io/spring-security/site/docs/6.4.3/api/org/springframework/security/task/DelegatingSecurityContextAsyncTaskExecutor.html)
- [Spring Framework – Task Execution and @Async](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework – Asynchronous Application Event Listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework – Observability and Context Propagation](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Security – Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
