# ReactiveRedisIndexedSessionRepository và khả năng hỗ trợ theo phiên bản

Spring Session hỗ trợ lưu `WebSession` của Spring WebFlux trong Redis theo mô hình reactive. Ở cấu hình cơ bản, ứng dụng khôi phục phiên bằng session ID do client gửi trong cookie hoặc header. Khi cần tìm các phiên theo principal, ví dụ liệt kê phiên đăng nhập của một người dùng, thu hồi mọi phiên hoặc giới hạn phiên đồng thời trên nhiều instance, ứng dụng cần repository có chỉ mục.

`ReactiveRedisIndexedSessionRepository` là implementation Redis reactive có khả năng tra cứu theo index. Điểm quan trọng về phiên bản là implementation này cùng interface `ReactiveFindByIndexNameSessionRepository` và annotation `@EnableRedisIndexedWebSession` được bổ sung từ Spring Session **3.3.0**. Ứng dụng dùng Spring Session 3.2.x hoặc cũ hơn vẫn có thể dùng reactive Redis session cơ bản, nhưng không có các API indexed reactive này. Vì vậy, cần kiểm tra phiên bản thư viện và dòng Spring Boot trước khi viết code dựa trên repository indexed.

## 1. Repository reactive cơ bản và repository indexed khác nhau thế nào?

`ReactiveRedisSessionRepository` là repository reactive cơ bản. Nó lưu dữ liệu session trong Redis và tìm phiên bằng session ID. Annotation WebFlux tương ứng là `@EnableRedisWebSession`. API này đã có trước Spring Session 3.3; `@EnableRedisWebSession` được giới thiệu từ 2.0.0 và `ReactiveRedisSessionRepository` từ 2.2.0.

`ReactiveRedisIndexedSessionRepository` bổ sung cấu trúc index cho các phiên. Ngoài `ReactiveSessionRepository`, nó triển khai `ReactiveFindByIndexNameSessionRepository`, cho phép tìm phiên theo cặp index name/index value. Index phổ biến nhất là principal name. Annotation WebFlux tương ứng là `@EnableRedisIndexedWebSession`.

| Khả năng | Reactive Redis cơ bản | Reactive Redis indexed |
|---|---|---|
| Lưu và khôi phục `WebSession` | Có | Có |
| Tìm phiên theo session ID | Có | Có |
| Xóa phiên theo session ID | Có | Có |
| Tìm phiên theo principal | Không cung cấp reactive principal index | Có, qua `ReactiveFindByIndexNameSessionRepository` |
| Quản lý danh sách phiên của một người dùng | Cần cơ chế riêng | Có thể truy vấn từ index |
| Hỗ trợ reactive concurrent session control của Spring Security | Không có index cần thiết | Có thể tích hợp `SpringSessionBackedReactiveSessionRegistry` |
| Cấu hình WebFlux | `@EnableRedisWebSession` | `@EnableRedisIndexedWebSession` |

Hai repository đều dùng Redis và API WebSession reactive. Khác biệt cốt lõi là indexed repository duy trì thêm dữ liệu ánh xạ từ thuộc tính index đến các session ID. Điều này tạo khả năng truy vấn mới nhưng cũng làm tăng dữ liệu và thao tác cần vận hành.

## 2. Ranh giới phiên bản: tính năng indexed reactive bắt đầu từ 3.3.0

Không được nhầm `RedisIndexedSessionRepository` với `ReactiveRedisIndexedSessionRepository`:

- `RedisIndexedSessionRepository` dùng Spring Data Redis API đồng bộ và phục vụ tích hợp Servlet/`HttpSession`.
- `ReactiveRedisIndexedSessionRepository` dùng `ReactiveRedisOperations` và phục vụ WebFlux/`WebSession`.
- `@EnableRedisIndexedHttpSession` cấu hình repository indexed cho Servlet.
- `@EnableRedisIndexedWebSession` cấu hình repository indexed reactive cho WebFlux.

Mốc hỗ trợ chính:

| Phiên bản Spring Session | Reactive Redis có sẵn | Reactive Redis indexed |
|---|---|---|
| Trước 2.2 | Có cấu hình WebFlux Redis từ các phiên bản trước; kiểm tra repository cụ thể theo API version | Chưa có `ReactiveRedisIndexedSessionRepository` |
| 2.2.x đến 3.2.x | `ReactiveRedisSessionRepository` và `@EnableRedisWebSession` | Chưa có `ReactiveRedisIndexedSessionRepository`, `ReactiveFindByIndexNameSessionRepository` hoặc `@EnableRedisIndexedWebSession` |
| 3.3.0 trở lên | Có | Có; các API indexed reactive được giới thiệu từ 3.3 |

Spring Session 3.3.0 GA công bố rõ `ReactiveRedisIndexedSessionRepository` là tính năng mới. Javadoc đánh dấu class, `ReactiveFindByIndexNameSessionRepository` và `@EnableRedisIndexedWebSession` là `Since: 3.3`. Các dòng tài liệu 3.4, 3.5 và 4.0 tiếp tục có các API này.

Spring Boot 3.3 đưa Spring Session 3.3.0 vào bộ dependency được quản lý. Vì thế, dự án dùng Boot 3.3 trở lên có thể tiếp cận tính năng theo dependency management của dòng Boot tương ứng. Dự án dùng Boot 3.2.x thường được quản lý với Spring Session 3.2.x và không thể biên dịch code tham chiếu các lớp indexed reactive 3.3.

Không nên chỉ ép riêng `spring-session-data-redis` lên 3.3.x trong dự án Boot cũ rồi bỏ qua tương thích của Spring Framework, Spring Data Redis và các module Spring Session khác. Ưu tiên nâng theo dòng Spring Boot tương thích và để BOM quản lý phiên bản. Nếu chưa thể nâng, tiếp tục dùng repository reactive cơ bản hoặc xây dựng cơ chế quản lý phiên riêng phù hợp với phiên bản đang chạy.

## 3. Dependency và điều kiện chạy

Ứng dụng cần stack WebFlux, Spring Data Redis reactive và module Spring Session Redis. Với Gradle dùng Spring Boot dependency management:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-data-redis-reactive")
    implementation("org.springframework.session:spring-session-data-redis")
}
```

Không ghi một phiên bản Spring Session tùy ý nếu dự án đã dùng Spring Boot BOM. Xác nhận phiên bản thực tế của `spring-session-core` và `spring-session-data-redis` giống nhau, đồng thời tương thích với Spring Data Redis đang được quản lý.

`@EnableRedisIndexedWebSession` cần một `ReactiveRedisConnectionFactory`. Khi dùng Spring Boot và reactive Redis starter, Boot thường có thể tạo connection factory từ cấu hình `spring.data.redis.*`. Nếu tự cấu hình, phải cung cấp đúng một factory reactive phù hợp với Redis deployment.

## 4. Bật ReactiveRedisIndexedSessionRepository

Trong ứng dụng WebFlux, cách cấu hình tường minh là dùng `@EnableRedisIndexedWebSession`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.server.EnableRedisIndexedWebSession;

@Configuration(proxyBeanMethods = false)
@EnableRedisIndexedWebSession(
        maxInactiveIntervalInSeconds = 1800,
        redisNamespace = "spring:session:portal"
)
public class ReactiveSessionConfiguration {
}
```

Annotation này đưa `WebSessionManager` vào application context và cấu hình nó dùng Reactive Redis indexed repository. Ví dụ đặt timeout không hoạt động 30 phút và namespace riêng để cô lập dữ liệu session của ứng dụng. Namespace phải giống nhau trên mọi instance cùng chia sẻ phiên.

Trong Spring Boot, cấu hình `@EnableRedisIndexedWebSession` là cách chọn rõ indexed reactive repository. Khi dùng annotation này, kiểm tra auto-configuration của Boot đã lùi lại và chỉ có một `WebSessionManager`/repository được dùng cho ứng dụng. Không đồng thời bật `@EnableRedisWebSession` và `@EnableRedisIndexedWebSession` trong cùng một WebFlux application.

Nếu chỉ cần repository cơ bản, `@EnableRedisWebSession` vẫn là lựa chọn hợp lệ. Việc đổi sang annotation indexed là quyết định về khả năng tra cứu và dữ liệu index, không phải yêu cầu bắt buộc của mọi ứng dụng WebFlux.

## 5. Các API mà repository indexed cung cấp

`ReactiveRedisIndexedSessionRepository` triển khai hai interface:

- `ReactiveSessionRepository<S>`: tạo, tìm, lưu và xóa session theo ID bằng `Mono`.
- `ReactiveFindByIndexNameSessionRepository<S>`: tìm một map session theo index name và index value bằng `Mono<Map<String, S>>`.

Interface thứ hai có hằng số `PRINCIPAL_NAME_INDEX_NAME` và phương thức tiện ích `findByPrincipalName(principalName)`. Kết quả là publisher chứa map trong đó key là session ID và value là session tương ứng. Nếu không tìm thấy phiên, map trả về rỗng; publisher không cần phát `null`.

Ví dụ truy vấn phiên của principal:

```java
@Service
public class UserSessionsService {

    private final ReactiveRedisIndexedSessionRepository repository;

    public UserSessionsService(ReactiveRedisIndexedSessionRepository repository) {
        this.repository = repository;
    }

    public Mono<Map<String, ReactiveRedisIndexedSessionRepository.RedisSession>>
            findSessions(String principalName) {
        return repository.findByPrincipalName(principalName);
    }
}
```

Phương thức trả nguyên publisher để caller kết hợp với response hoặc service khác. Không gọi `block()` để lấy map trong WebFlux và không tự `subscribe()` trong controller. Giữ thao tác trong reactive chain để lỗi Redis, cancellation và context được xử lý theo request.

## 6. Thu hồi mọi phiên theo principal

Một ứng dụng có thể cần đăng xuất tất cả thiết bị sau khi người dùng đổi mật khẩu hoặc yêu cầu kết thúc các phiên đang hoạt động. Với indexed repository, có thể tìm các session ID theo principal rồi xóa từng phiên:

```java
public Mono<Void> revokeAll(String principalName) {
    return repository.findByPrincipalName(principalName)
            .flatMapMany(sessions -> Flux.fromIterable(sessions.keySet()))
            .flatMap(repository::deleteById)
            .then();
}
```

Đây là thao tác reactive: `findByPrincipalName` trả `Mono<Map<...>>`, `flatMapMany` biến các key thành luồng ID, `flatMap` gọi xóa cho từng ID và `then()` hoàn tất khi các thao tác xóa kết thúc. Nếu map rỗng, chuỗi hoàn tất mà không xóa gì.

Chỉ truyền principal đã được xác thực hoặc principal mà caller có quyền quản lý. Không nhận username tùy ý từ request rồi cho phép người dùng xóa phiên của tài khoản khác. Với chức năng quản trị, kiểm tra quyền quản trị và ghi audit riêng.

Kết quả tra cứu là tập phiên tại thời điểm index được đọc. Một đăng nhập mới có thể tạo phiên ngay sau đó; request đang chạy cũng có thể tiếp tục cho đến khi hoàn tất. Với yêu cầu thu hồi nghiêm ngặt, kết hợp xóa phiên với trạng thái tài khoản, session version hoặc marker thu hồi được kiểm tra ở các request tiếp theo. Index giúp tìm phiên, nhưng không tự tạo một transaction phân tán bao trùm mọi request.

## 7. Principal index được tạo như thế nào?

Repository indexed duy trì index bằng `IndexResolver`. Mặc định, Spring Session dùng `PrincipalNameIndexResolver` để tìm thông tin principal từ các thuộc tính session mà nó nhận diện được. Khi session được lưu, repository cập nhật các index tương ứng; khi xóa session, index được dọn theo vòng đời repository.

Điều này không có nghĩa mọi cơ chế xác thực tùy chỉnh đều tự động được nhận diện. Nếu ứng dụng lưu principal theo một cấu trúc riêng hoặc dùng authentication mechanism không tích hợp mặc định, nhóm phát triển phải bảo đảm resolver có thể lấy ra principal name ổn định. Interface `ReactiveFindByIndexNameSessionRepository` cũng nêu rõ trách nhiệm của ứng dụng trong việc bảo đảm index principal được điền.

Khi cần index tùy chỉnh, có thể cấu hình `IndexResolver` phù hợp thông qua cấu hình nâng cao của `RedisIndexedWebSessionConfiguration` hoặc `ReactiveSessionRepositoryCustomizer` theo API của phiên bản. Không tự thêm một thuộc tính tên `PRINCIPAL_NAME_INDEX_NAME` từ dữ liệu request chưa xác thực. Giá trị index phải xuất phát từ danh tính đã được xác thực và được chuẩn hóa thống nhất trên các instance.

Một index không phải cơ chế phân quyền. Việc tìm thấy session của principal chỉ cho biết session được gắn với giá trị index đó; ứng dụng vẫn phải kiểm tra quyền trước khi hiển thị thông tin hoặc thu hồi phiên.

## 8. Tích hợp reactive concurrent session control

Spring Session 3.3 cũng bổ sung `SpringSessionBackedReactiveSessionRegistry`, một implementation của Spring Security `ReactiveSessionRegistry`. Registry này lấy thông tin phiên từ Spring Session thay vì giữ một registry cục bộ trong bộ nhớ, nhờ vậy có thể hỗ trợ giới hạn phiên đăng nhập đồng thời trong môi trường nhiều instance.

Ví dụ khai báo bean theo API Spring Session:

```java
@Bean
<S extends Session> SpringSessionBackedReactiveSessionRegistry<S> sessionRegistry(
        ReactiveSessionRepository<S> sessionRepository,
        ReactiveFindByIndexNameSessionRepository<S> indexedSessionRepository) {
    return new SpringSessionBackedReactiveSessionRegistry<>(
            sessionRepository, indexedSessionRepository);
}
```

Bean cần cả repository reactive và interface index reactive. Sau đó cấu hình Spring Security WebFlux dùng `ReactiveSessionRegistry` này cho concurrent session control theo DSL của phiên bản Spring Security trong dự án.

Giới hạn số phiên vẫn cần kiểm thử với đăng nhập đồng thời. Hai request đăng nhập gần như cùng lúc có thể quan sát trạng thái trước khi phiên còn lại được ghi; index và registry cung cấp khả năng tra cứu dùng chung nhưng không nên được hiểu là mọi quy tắc nghiệp vụ đã trở thành một thao tác nguyên tử duy nhất.

## 9. Redis lưu session và index ra sao?

Repository lưu dữ liệu phiên trong Redis Hash. Ngoài key chứa session, indexed repository duy trì các cấu trúc phụ để tìm session theo principal và theo dõi thời điểm hết hạn. Với namespace mặc định, các key minh họa có thể có dạng:

```text
spring:session:sessions:<session-id>
spring:session:sessions:index:PRINCIPAL_NAME_INDEX_NAME:<principal>
spring:session:sessions:<session-id>:idx
spring:session:sessions:expires:<session-id>
spring:session:sessions:expirations
```

Redis Set principal index chứa các session ID thuộc principal. Một key index phụ theo session giúp repository biết các index nào cần xóa khi session bị xóa hoặc thay đổi. Sorted set expiration theo dõi session ID và thời điểm dự kiến hết hạn để hỗ trợ cleanup.

Đây là cấu trúc nội bộ phục vụ giải thích và chẩn đoán, không phải schema công khai để ứng dụng tự ghi. Không dùng `DEL`, `SADD`, `SREM` hoặc `ZREM` thủ công để sửa index trong production. Thao tác trực tiếp có thể làm session data và index mất đồng bộ. Dùng API repository hoặc quy trình migration được kiểm thử.

## 10. Hết hạn, keyspace events và cleanup

Reactive indexed repository sử dụng Redis keyspace notifications để nhận biết key hết hạn hoặc bị xóa, từ đó dọn các key session liên quan và phát sự kiện vòng đời. Redis không bảo đảm mọi key hết hạn đều phát event đúng ngay thời điểm TTL chạm 0 nếu key không được truy cập. Vì vậy, repository còn theo dõi thời điểm hết hạn trong sorted set và chạy cleanup task nền để chạm các key có khả năng đã hết hạn.

Theo tài liệu Spring Session 3.3, cleanup mặc định kiểm tra tối đa 100 session hết hạn mỗi 60 giây. Có thể tùy chỉnh khoảng cleanup bằng `ReactiveSessionRepositoryCustomizer<ReactiveRedisIndexedSessionRepository>`:

```java
@Bean
ReactiveSessionRepositoryCustomizer<ReactiveRedisIndexedSessionRepository>
        reactiveSessionRepositoryCustomizer() {
    return repository -> repository.setCleanupInterval(Duration.ofSeconds(30));
}
```

Có thể gọi `disableCleanupTask()` nếu ứng dụng chủ động cung cấp cơ chế cleanup riêng. Chỉ tắt task mặc định khi đã có phương án thay thế được giám sát và kiểm thử; nếu không, key phụ và index có thể tồn tại lâu hơn dự kiến.

Spring Session mặc định thử cấu hình Redis keyspace notifications thông qua `ConfigureReactiveRedisAction`. Trên Redis được bảo vệ chặt, ứng dụng có thể không có quyền thay đổi cấu hình server. Khi đó, quản trị viên cần cấu hình `notify-keyspace-events` bên ngoài và ứng dụng có thể khai báo `ConfigureReactiveRedisAction.NO_OP` để tắt bước tự cấu hình:

```java
@Bean
ConfigureReactiveRedisAction configureReactiveRedisAction() {
    return ConfigureReactiveRedisAction.NO_OP;
}
```

Không thêm `NO_OP` rồi bỏ qua cấu hình Redis phía server. Nếu keyspace notifications không được bật đúng, event và cleanup liên quan có thể không hoạt động như mong đợi. Kiểm tra quyền Redis, cấu hình notification, listener và metric cleanup trong môi trường triển khai thật.

## 11. Sự kiện session và xử lý phụ trợ

Indexed repository hỗ trợ các sự kiện như `SessionCreatedEvent`, `SessionDeletedEvent` và `SessionExpiredEvent` theo cấu hình Redis keyspace/channel. Ứng dụng có thể dùng các sự kiện để cập nhật metric, dọn metadata phụ trợ hoặc kích hoạt công việc bảo mật.

Event là tín hiệu vòng đời, không phải nguồn sự thật duy nhất về quyền truy cập. Request phải được xác thực bằng repository và trạng thái session hiện tại; không chờ event hết hạn mới từ chối session. Redis listener có thể gián đoạn, event có thể đến trễ và tác vụ phụ có thể cần retry.

Handler nên idempotent và không ghi session ID, cookie hoặc thuộc tính nhạy cảm vào log. Nếu event kích hoạt gửi thông báo hoặc gọi dịch vụ bên ngoài, dùng khóa nghiệp vụ/outbox khi cần tránh tác dụng phụ lặp lại. Không thực hiện công việc blocking trên reactive event loop.

## 12. Phân biệt WebFlux indexed với Servlet indexed

Hai cấu hình có tên gần nhau nhưng thuộc hai stack khác nhau:

| Mục đích | WebFlux reactive | Servlet đồng bộ |
|---|---|---|
| Repository | `ReactiveRedisIndexedSessionRepository` | `RedisIndexedSessionRepository` |
| API cơ sở | `ReactiveSessionRepository` | `SessionRepository` |
| API index | `ReactiveFindByIndexNameSessionRepository` | `FindByIndexNameSessionRepository` |
| Annotation | `@EnableRedisIndexedWebSession` | `@EnableRedisIndexedHttpSession` |
| Session API | `WebSession` | `HttpSession` |
| Kiểu trả về | `Mono`/`Flux` | Giá trị đồng bộ |
| Redis operations | `ReactiveRedisOperations` | `RedisOperations` |

Không inject `RedisIndexedSessionRepository` đồng bộ vào WebFlux rồi gọi `block()` để giả lập reactive. Cũng không dùng `@EnableRedisIndexedHttpSession` trong ứng dụng WebFlux thuần. Chọn đúng repository và annotation theo application type.

## 13. Chuyển từ repository reactive cơ bản sang indexed

Đổi từ `@EnableRedisWebSession` sang `@EnableRedisIndexedWebSession` làm thay đổi cách repository duy trì index và event. Không nên triển khai bằng cách chỉ thay annotation rồi giả định tất cả session cũ lập tức có principal index.

Các phiên đã được tạo bởi repository cơ bản có thể còn dữ liệu session trong Redis, nhưng index principal chưa chắc đã tồn tại. Việc tra cứu theo principal có thể không trả đủ các phiên cũ cho đến khi chúng được lưu lại theo cơ chế indexed hoặc được xử lý bằng kế hoạch backfill phù hợp. Cần xác minh hành vi trên đúng phiên bản và dữ liệu thực tế.

Quy trình chuyển đổi nên gồm:

1. Kiểm tra serializer, namespace, timeout và cấu trúc key hiện tại.
2. Xác nhận classpath có Spring Session 3.3.0 trở lên và annotation/API indexed reactive.
3. Xác định cách xử lý các phiên cũ chưa có index: backfill có kiểm soát, chờ hết TTL hoặc kết thúc session cũ theo kế hoạch.
4. Triển khai cùng một repository type và namespace trên mọi instance phục vụ cùng ứng dụng.
5. Kiểm thử đọc session ID cũ, tìm principal, logout, expiration và cleanup.
6. Theo dõi số lượng session được index và chênh lệch giữa số phiên tồn tại với kết quả principal lookup.

Không chạy một số instance với repository cơ bản và một số instance với indexed trên cùng namespace trong rolling deployment nếu chưa có thiết kế tương thích. Node cơ bản không duy trì index; node indexed có thể thấy index thiếu hoặc cũ khi request đi qua node khác. Có thể dùng một namespace mới và chủ động yêu cầu đăng nhập lại nếu không cần giữ session cũ.

## 14. Kiểm tra phiên bản và repository thực tế

Khi gặp lỗi `ClassNotFoundException`, `NoClassDefFoundError` hoặc lỗi biên dịch với `ReactiveRedisIndexedSessionRepository`, kiểm tra phiên bản dependency trước khi thay code:

```bash
./gradlew dependencyInsight \
  --dependency spring-session-data-redis \
  --configuration runtimeClasspath
```

Với Maven:

```bash
mvn dependency:tree \
  -Dincludes=org.springframework.session:spring-session-data-redis
```

Các lệnh này giúp xác nhận phiên bản thực tế và dependency nào đưa nó vào. Nếu dự án dùng Spring Boot, kiểm tra BOM đang quản lý Spring Session ở dòng 3.2, 3.3, 3.4, 3.5 hoặc 4.0 tương ứng. Không chỉ xem phiên bản khai báo trong build file; dependency mediation có thể chọn một phiên bản khác.

Trong application context, xác nhận có `WebSessionManager` và repository reactive được chọn. Nếu nghiệp vụ cần index, xác nhận repository thực hiện `ReactiveFindByIndexNameSessionRepository`; chỉ có `ReactiveSessionRepository` là chưa đủ để gọi API principal lookup.

## 15. Kiểm thử repository indexed

Một bộ integration test cần chứng minh cả lưu phiên, index và hành vi khi nhiều instance:

| Ca kiểm thử | Cách thực hiện | Kết quả cần xác nhận |
|---|---|---|
| Tạo session | Tạo WebSession qua request WebFlux | Response phát session ID và repository lưu phiên |
| Khôi phục theo ID | Gửi lại cookie/header đến request sau | WebSession khôi phục đúng thuộc tính |
| Principal index | Tạo session với principal được nhận diện | `findByPrincipalName` trả session tương ứng |
| Principal khác | Tìm bằng principal không liên quan | Không trả session của người khác |
| Thu hồi principal | Tìm và xóa các session của principal | Các session ID đã xóa không còn khôi phục được |
| Index tùy chỉnh | Dùng authentication mechanism riêng | IndexResolver ánh xạ principal đúng |
| Hết hạn | Để session quá TTL | `findById` không trả phiên đã hết hạn; cleanup xử lý key phụ |
| Redis keyspace events | Bật notification trong Redis test | Event được phát theo cấu hình; handler chịu được retry |
| Cleanup task | Tạo session hết hạn và quan sát cleanup | Sorted-set entry/key phụ được xử lý theo chính sách |
| Concurrent session control | Đăng nhập cùng principal từ nhiều client | Reactive registry tra cứu được phiên giữa các instance |
| Nhiều instance | Tạo phiên ở A, tra cứu principal ở B | Index được chia sẻ và đọc được từ B |
| Chuyển phiên bản | Đọc dữ liệu được tạo bởi phiên bản trước | Tương thích serializer/index được xác nhận |

Ví dụ kiểm thử publisher tìm principal:

```java
StepVerifier.create(repository.findByPrincipalName("alice"))
        .assertNext(sessions ->
                assertThat(sessions).hasSize(1))
        .verifyComplete();
```

Test phải tạo một session thực sự có index cho `alice` trước khi truy vấn. Dùng Redis test tương thích với production và cấu hình keyspace notifications phù hợp. Mock repository không xác nhận index, TTL, event hoặc cleanup thực tế.

Với WebFlux HTTP lifecycle, dùng `WebTestClient` để tạo session, lấy cookie/header, gọi lại endpoint và kiểm tra logout. Với repository, dùng `StepVerifier` để xác nhận completion/error signal. Không gọi `block()` trong code ứng dụng chỉ để viết test; test có thể dùng công cụ đồng bộ ở biên test nếu cần nhưng phải giữ request path reactive.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không biên dịch được `ReactiveRedisIndexedSessionRepository` | Spring Session đang ở 3.2.x hoặc thấp hơn | Nâng theo dòng Boot tương thích lên Spring Session 3.3+ |
| Không tìm thấy `@EnableRedisIndexedWebSession` | Dùng sai phiên bản hoặc import nhầm package Servlet | Kiểm tra API 3.3+ và package `web.server` |
| Ứng dụng không có principal lookup | Đang dùng `ReactiveRedisSessionRepository` cơ bản | Cấu hình indexed repository và xác nhận interface bean |
| `findByPrincipalName` trả map rỗng | Principal chưa được index hoặc resolver không nhận diện authentication | Kiểm tra session attributes, `IndexResolver` và principal name |
| Chỉ một số session được tìm thấy | Session cũ được tạo trước khi bật index hoặc index chưa được backfill | Lập kế hoạch cho session cũ và kiểm tra index trong Redis |
| Redis event không tới listener | Keyspace notifications chưa bật hoặc quyền cấu hình Redis bị giới hạn | Cấu hình notification bên ngoài và dùng `ConfigureReactiveRedisAction.NO_OP` nếu phù hợp |
| Key phụ còn tồn tại lâu | Cleanup task bị tắt hoặc listener/Redis event gián đoạn | Kiểm tra cleanup interval, sorted set và metric |
| Một instance tìm thấy, instance khác không | Namespace, repository type hoặc Redis endpoint không đồng nhất | Đồng nhất cấu hình và kiểm thử xuyên instance |
| Concurrent session control không hoạt động | Chưa dùng `SpringSessionBackedReactiveSessionRegistry` hoặc index principal thiếu | Kiểm tra registry và cách populate principal index |
| Lỗi reactive/blocking | Dùng repository đồng bộ hoặc gọi `block()` trên event loop | Dùng Reactive Redis repository và giữ `Mono`/`Flux` trong pipeline |

## 17. Checklist triển khai

- [ ] Ứng dụng thực sự chạy WebFlux và dùng reactive Redis connection factory.
- [ ] Spring Session là 3.3.0 trở lên nếu cần indexed reactive API.
- [ ] Spring Boot, Spring Framework, Spring Data Redis và Spring Session được quản lý theo bộ phiên bản tương thích.
- [ ] Dùng `@EnableRedisIndexedWebSession`, không nhầm với annotation Servlet.
- [ ] Chỉ có một cấu hình WebSessionManager/repository được áp dụng.
- [ ] Principal index được populate từ danh tính đã xác thực.
- [ ] Namespace giống nhau trên các instance và tách biệt với ứng dụng khác.
- [ ] Redis keyspace notifications và cleanup task được cấu hình, giám sát.
- [ ] Session cũ khi chuyển từ repository cơ bản có kế hoạch backfill hoặc kết thúc rõ ràng.
- [ ] Kiểm thử tìm principal, thu hồi, hết hạn, event và concurrent session control bằng Redis thật.
- [ ] Không block event loop, không tự subscribe tách rời request và không log session ID.

## 18. Tài liệu phiên bản cần đối chiếu

- [Reactive Redis Indexed Configurations – Spring Session 3.3](https://docs.spring.io/spring-session/reference/3.3/configuration/reactive-redis-indexed.html)
- [ReactiveRedisIndexedSessionRepository – API 3.3](https://docs.spring.io/spring-session/docs/3.3.x/api/org/springframework/session/data/redis/ReactiveRedisIndexedSessionRepository.html)
- [ReactiveFindByIndexNameSessionRepository – API 3.3](https://docs.spring.io/spring-session/docs/3.3.x/api/org/springframework/session/ReactiveFindByIndexNameSessionRepository.html)
- [Spring Session 3.3 goes GA](https://spring.io/blog/2024/05/21/spring-session-3-3-goes-ga/)
- [Spring Boot 3.3 Spring Session documentation](https://docs.spring.io/spring-boot/3.3/reference/web/spring-session.html)

`ReactiveRedisIndexedSessionRepository` là lựa chọn dành cho ứng dụng WebFlux cần tra cứu phiên theo index, đặc biệt là principal. Tính năng này có từ Spring Session 3.3.0; các dự án ở dòng cũ hơn chỉ có reactive repository cơ bản và cần nâng cấp theo bộ phiên bản Spring tương thích trước khi dùng API indexed. Khi cấu hình đúng, index principal, Redis keyspace events và cleanup phối hợp để hỗ trợ quản lý phiên nhiều thiết bị và concurrent session control trên nhiều instance mà vẫn giữ toàn bộ thao tác trong mô hình reactive.
