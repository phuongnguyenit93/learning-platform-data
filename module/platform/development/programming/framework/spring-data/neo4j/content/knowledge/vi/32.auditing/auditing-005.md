# Kích hoạt @EnableReactiveNeo4jAuditing và ReactiveAuditorAware

Spring Data Neo4j (SDN) hỗ trợ auditing để tự động ghi nhận ai đã tạo hoặc sửa entity và thời điểm thao tác diễn ra. Trong ứng dụng reactive, auditing cần được kích hoạt bằng `@EnableReactiveNeo4jAuditing`; thông tin người thực hiện được cung cấp qua `ReactiveAuditorAware<T>`. Interface này trả về `Mono<T>`, cho phép SDN lấy auditor từ reactive context mà không chặn thread.

Auditing giúp entity có metadata về nguồn gốc và lần cập nhật gần nhất. Ví dụ, một node `Person` có thể lưu `createdBy`, `createdDate`, `lastModifiedBy` và `lastModifiedDate`. Các giá trị được điền khi entity đi qua reactive persistence của SDN. Cơ chế này phù hợp để theo dõi metadata hiện tại của entity; nếu cần lịch sử mọi thay đổi, ứng dụng vẫn cần một audit log hoặc event store riêng.

## 1. Auditing ghi nhận những thông tin nào?

Spring Data cung cấp bốn annotation chính:

| Annotation | Ý nghĩa | Thời điểm cập nhật |
|---|---|---|
| `@CreatedBy` | Principal tạo entity | Khi entity được tạo |
| `@CreatedDate` | Thời điểm tạo entity | Khi entity được tạo |
| `@LastModifiedBy` | Principal sửa entity gần nhất | Khi tạo hoặc cập nhật tùy cấu hình |
| `@LastModifiedDate` | Thời điểm sửa entity gần nhất | Khi tạo hoặc cập nhật tùy cấu hình |

Các annotation nằm trong package `org.springframework.data.annotation`. Có thể dùng riêng từng annotation tùy nhu cầu. Nếu ứng dụng chỉ cần thời gian tạo và sửa, không cần triển khai `AuditorAware` hoặc `ReactiveAuditorAware`; hai interface này chỉ cần khi muốn điền principal cho `@CreatedBy` hoặc `@LastModifiedBy`.

Auditing metadata thường là các property scalar như username, user ID và `Instant`. Generic type của auditor phải tương thích với kiểu của property được đánh dấu `@CreatedBy` và `@LastModifiedBy`. Dùng một định danh ổn định như user ID hoặc username thường đơn giản hơn việc lưu trực tiếp đối tượng `Authentication`.

## 2. Kích hoạt reactive auditing

Đặt `@EnableReactiveNeo4jAuditing` trên một lớp cấu hình được Spring scan:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.config.EnableReactiveNeo4jAuditing;

@Configuration
@EnableReactiveNeo4jAuditing
public class Neo4jReactiveAuditingConfiguration {
}
~~~

Annotation thuộc package `org.springframework.data.neo4j.config` và được cung cấp từ Spring Data Neo4j 6.0. Nó đăng ký hạ tầng auditing dùng reactive infrastructure cho entity SDN.

Khi cần ghi nhận người tạo hoặc người sửa, hãy khai báo thêm bean `ReactiveAuditorAware<T>` và trỏ tới bean đó bằng thuộc tính `auditorAwareRef`. Ví dụ:

~~~java
@Configuration
@EnableReactiveNeo4jAuditing(
    auditorAwareRef = "reactiveAuditorAware"
)
public class Neo4jReactiveAuditingConfiguration {
}
~~~

Tên `reactiveAuditorAware` phải trùng tên bean được đăng ký trong application context. Nếu chỉ cần date metadata, có thể bật auditing mà không cần cung cấp auditor bean.

Không dùng `@EnableNeo4jAuditing` cho reactive persistence path. Annotation đó bật auditing imperative và sử dụng `AuditorAware<T>` trả về `Optional<T>`. Với reactive repository, hãy dùng `@EnableReactiveNeo4jAuditing` cùng `ReactiveAuditorAware<T>`.

## 3. Khai báo auditing metadata trên entity

Ví dụ một entity `Person` lưu thông tin người tạo, người sửa và thời gian:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdDate;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedDate;

    protected Person() {
    }

    public Person(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public Instant getCreatedDate() {
        return createdDate;
    }

    public String getLastModifiedBy() {
        return lastModifiedBy;
    }

    public Instant getLastModifiedDate() {
        return lastModifiedDate;
    }

    public void rename(String name) {
        this.name = name;
    }
}
~~~

SDN auditing sẽ điền các property được đánh dấu khi entity được lưu qua reactive repository hoặc reactive template. Không tự đặt `createdDate` hoặc `lastModifiedDate` trong service nếu muốn auditing quản lý nhất quán. Với domain model bất biến, hãy bảo đảm mapping model hỗ trợ việc tạo instance mới với các giá trị auditing được áp dụng.

## 4. Triển khai ReactiveAuditorAware<T>

`ReactiveAuditorAware<T>` thuộc package `org.springframework.data.domain`. Interface có một phương thức `getCurrentAuditor()` trả về `Mono<T>`:

~~~java
import org.springframework.data.domain.ReactiveAuditorAware;
import reactor.core.publisher.Mono;

public class CurrentUserAuditorAware
        implements ReactiveAuditorAware<String> {

    @Override
    public Mono<String> getCurrentAuditor() {
        return Mono.just("system");
    }
}
~~~

Ví dụ trên dùng một auditor cố định để minh họa hợp đồng interface. Trong ứng dụng thật, giá trị thường đến từ người dùng đã xác thực hoặc một định danh hệ thống của tác vụ nền. Generic `String` có nghĩa các property `@CreatedBy` và `@LastModifiedBy` trong entity cũng nên nhận giá trị kiểu `String`.

`Mono.just("system")` không phải cách triển khai phù hợp cho mọi request. Nếu dùng một giá trị cố định cho toàn ứng dụng, mọi entity sẽ có cùng auditor và mất thông tin người thực hiện. Hãy lấy principal từ ngữ cảnh xác thực của request hoặc một định danh hệ thống riêng cho tác vụ nền.

## 5. Lấy auditor từ Spring Security reactive context

Trong ứng dụng WebFlux dùng Spring Security reactive, thông tin xác thực được lưu trong Reactor Context. Dùng `ReactiveSecurityContextHolder` để lấy `Authentication`; không đọc `SecurityContextHolder` imperative hoặc `ThreadLocal` trong reactive flow.

~~~java
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

public class SecurityReactiveAuditorAware
        implements ReactiveAuditorAware<String> {

    @Override
    public Mono<String> getCurrentAuditor() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .filter(authentication ->
                !(authentication instanceof AnonymousAuthenticationToken))
            .flatMap(authentication ->
                Mono.justOrEmpty(authentication.getName()))
            .filter(name -> !name.isBlank());
    }
}
~~~

Luồng xử lý:

1. `ReactiveSecurityContextHolder.getContext()` lấy security context từ Reactor Context.
2. `map(SecurityContext::getAuthentication)` lấy principal đã xác thực.
3. `filter(Authentication::isAuthenticated)` loại authentication chưa được xác thực.
4. Bộ lọc `AnonymousAuthenticationToken` loại principal anonymous nếu ứng dụng bật anonymous authentication.
5. `getName()` lấy tên principal; `Mono.justOrEmpty` xử lý trường hợp không có tên.
6. `filter` cuối loại chuỗi rỗng.

Nếu không có security context hoặc không có principal hợp lệ, publisher kết thúc rỗng. Đây là tín hiệu auditor chưa xác định. Không tự biến anonymous thành người dùng đã đăng nhập.

## 6. Đăng ký auditor bean và bật annotation

Kết hợp auditor với cấu hình reactive auditing:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.data.neo4j.config.EnableReactiveNeo4jAuditing;

@Configuration
@EnableReactiveNeo4jAuditing(
    auditorAwareRef = "reactiveAuditorAware",
    modifyOnCreate = true
)
public class Neo4jReactiveAuditingConfiguration {

    @Bean
    ReactiveAuditorAware<String> reactiveAuditorAware() {
        return new SecurityReactiveAuditorAware();
    }
}
~~~

Tên bean mặc định được suy ra từ tên method `reactiveAuditorAware`; giá trị `auditorAwareRef` phải khớp chính xác. Có thể dùng `@Component` cho implementation thay vì `@Bean`, miễn là bean được phát hiện và tên tham chiếu chính xác.

Các thuộc tính đáng chú ý của `@EnableReactiveNeo4jAuditing`:

| Thuộc tính | Mặc định | Tác dụng |
|---|---:|---|
| `auditorAwareRef` | Chuỗi rỗng | Tên bean cung cấp auditor hiện tại |
| `modifyOnCreate` | `true` | Điền metadata sửa đổi ngay khi tạo entity |
| `setDates` | `true` | Bật cập nhật các property ngày tạo và ngày sửa |
| `dateTimeProviderRef` | Chuỗi rỗng | Tên bean `DateTimeProvider` tùy chỉnh nguồn thời gian |

Nếu muốn `lastModifiedBy` và `lastModifiedDate` có giá trị ngay từ lần tạo đầu tiên, giữ `modifyOnCreate = true`. Nếu chỉ muốn điền các trường modified sau lần cập nhật tiếp theo, đặt thuộc tính này thành `false`.

## 7. Phân biệt auditor và date time provider

Auditor trả lời câu hỏi “ai thực hiện thao tác?”. Date time provider trả lời câu hỏi “thời điểm hiện tại là khi nào?”. Đây là hai nguồn dữ liệu riêng:

- `ReactiveAuditorAware<T>` cung cấp giá trị cho `@CreatedBy` và `@LastModifiedBy`.
- `DateTimeProvider` cung cấp thời gian cho `@CreatedDate` và `@LastModifiedDate`.

Ứng dụng chỉ theo dõi thời gian có thể bật auditing mà không cần `ReactiveAuditorAware`. Nếu muốn kiểm soát clock để kiểm thử hoặc dùng một nguồn thời gian riêng, khai báo `DateTimeProvider` và chỉ định `dateTimeProviderRef`.

Ví dụ cấu hình provider dùng clock của Java:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;

@Configuration
public class AuditTimeConfiguration {

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditDateTimeProvider(Clock auditClock) {
        return () -> Optional.of(Instant.now(auditClock));
    }
}
~~~

Khi dùng provider này, thêm `dateTimeProviderRef = "auditDateTimeProvider"` vào `@EnableReactiveNeo4jAuditing`. `DateTimeProvider` là SPI cung cấp thời gian; nó không thay thế `ReactiveAuditorAware` và không lấy principal từ security context.

## 8. Xử lý khi không có auditor

`ReactiveAuditorAware` có thể trả về `Mono.empty()` khi không xác định được người thực hiện. Ví dụ:

- Request không có người dùng đăng nhập.
- Một tác vụ nền chạy theo lịch không gắn với user session.
- Security context không được truyền tới publisher đang lưu entity.
- Principal không đáp ứng điều kiện hợp lệ của ứng dụng.

Hãy xác định chính sách theo use case:

| Ngữ cảnh | Chính sách gợi ý |
|---|---|
| Request người dùng bắt buộc đăng nhập | Từ chối request ở tầng security/service nếu thiếu principal |
| Tác vụ nền có định danh rõ | Cung cấp auditor hệ thống như `batch-import` |
| Chỉ theo dõi ngày tạo/sửa | Không cần auditor bean |
| Principal có thể không xác định | Cho phép `Mono.empty()` và chấp nhận trường auditor không được điền |

Không dùng fallback `system` cho mọi trường hợp thiếu security context nếu việc đó che giấu lỗi cấu hình bảo mật. Nếu có tác vụ nền, hãy phân biệt rõ nó với request người dùng và cung cấp định danh hệ thống có chủ đích.

## 9. Reactive Context và giới hạn của ThreadLocal

Reactive pipeline không bảo đảm một tác vụ luôn chạy trên cùng thread. Vì vậy, không nên lấy auditor bằng `SecurityContextHolder.getContext()` trong một reactive service rồi giả định ThreadLocal luôn chứa đúng principal.

`ReactiveSecurityContextHolder` đọc thông tin được gắn vào Reactor Context. Để auditor hoạt động:

- Các thành phần bảo mật phải đưa authentication vào reactive context.
- Không tự tách publisher bằng `subscribe()` rồi mong context của caller được truyền sang publisher độc lập.
- Không gọi `block()` để lấy auditor đồng bộ.
- Giữ thao tác lưu entity trong cùng reactive pipeline để SDN có thể truy xuất context.
- Với tác vụ nền, chủ động xác định auditor hệ thống thay vì dựa vào security context của request.

Việc chuyển scheduler bằng `publishOn` hoặc `subscribeOn` không đồng nghĩa Reactor Context bị mất; context được truyền theo subscriber chain, không gắn trực tiếp với thread như ThreadLocal.

## 10. Auditing chạy khi nào và áp dụng cho đường ghi nào?

Auditing được áp dụng trong quá trình SDN xử lý entity trước khi persistence hoàn tất. Khi dùng reactive repository hoặc reactive template, SDN gọi reactive auditing infrastructure và chờ publisher cung cấp auditor trước khi hoàn tất việc cập nhật metadata.

Một ví dụ repository:

~~~java
import org.springframework.data.neo4j.repository.ReactiveNeo4jRepository;

public interface PersonRepository
        extends ReactiveNeo4jRepository<Person, Long> {
}
~~~

Lưu entity qua repository:

~~~java
import reactor.core.publisher.Mono;

public Mono<Person> createPerson(Person person) {
    return personRepository.save(person);
}
~~~

Khi publisher hoàn tất, entity đã được lưu cùng các trường auditing tương ứng. Hãy tiêu thụ publisher theo cách reactive ở tầng gọi; không gọi `subscribe()` bên trong service để tự khởi chạy việc lưu.

Nếu dùng Cypher thô qua `Neo4jClient` để `CREATE` hoặc `SET` node trực tiếp, không giả định auditing metadata tự được điền. Raw Cypher không đi qua quy trình mapping entity nơi auditing được áp dụng. Khi cần metadata trong custom Cypher, hãy truyền và cập nhật các property đó rõ ràng hoặc dùng mapping-aware persistence API.

## 11. Auditing không phải lịch sử thay đổi đầy đủ

`@CreatedBy` và `@CreatedDate` lưu thông tin tạo ban đầu. `@LastModifiedBy` và `@LastModifiedDate` lưu lần sửa gần nhất. Các trường modified sẽ được cập nhật ở những lần lưu tiếp theo; chúng không giữ lại mọi giá trị trước đó.

Nếu nghiệp vụ cần biết mọi lần thay đổi, ví dụ ai đã đổi tên từ giá trị nào sang giá trị nào, hãy thiết kế lịch sử riêng:

- Tạo node audit/event cho từng thay đổi.
- Ghi event cùng transaction nếu cần bảo đảm thay đổi graph và event cùng commit.
- Dùng outbox nếu event phải được gửi đáng tin cậy sang hệ thống khác.
- Xác định retention, quyền đọc và bảo vệ dữ liệu audit.

Không dùng bốn trường auditing làm event log. Chúng chỉ cung cấp metadata hiện tại của entity.

## 12. Kiểm thử reactive auditing

Có thể kiểm thử `ReactiveAuditorAware` riêng bằng Reactor Test. Ví dụ kiểm thử trường hợp lấy auditor từ reactive security context:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContextImpl;
import reactor.test.StepVerifier;

class SecurityReactiveAuditorAwareTest {

    @Test
    void shouldReturnAuthenticatedPrincipal() {
        var authentication =
            UsernamePasswordAuthenticationToken.authenticated(
                "user-42", "n/a", java.util.List.of()
            );

        var securityContext = new SecurityContextImpl(authentication);
        var auditorAware = new SecurityReactiveAuditorAware();

        StepVerifier.create(
                auditorAware.getCurrentAuditor()
                    .contextWrite(
                        ReactiveSecurityContextHolder.withSecurityContext(
                            reactor.core.publisher.Mono.just(securityContext)
                        )
                    )
            )
            .expectNext("user-42")
            .verifyComplete();
    }
}
~~~

Đây là kiểm thử cho auditor provider; cần thêm integration test với reactive Neo4j repository để xác nhận các property `@CreatedBy`, `@LastModifiedBy`, `@CreatedDate` và `@LastModifiedDate` được lưu đúng.

Các trường hợp nên kiểm thử:

1. Tạo entity với principal đã xác thực: `createdBy` và `createdDate` được điền.
2. Cập nhật entity: `lastModifiedBy` và `lastModifiedDate` phản ánh lần sửa mới nhất.
3. Tạo entity khi `modifyOnCreate = false`: metadata modified không được điền lúc tạo.
4. Không có security context: `ReactiveAuditorAware` phát rỗng theo chính sách.
5. Anonymous authentication: không gán nhầm `anonymousUser` thành auditor thật.
6. Tác vụ nền: auditor hệ thống được sử dụng đúng nếu ứng dụng cấu hình chính sách đó.
7. Raw Cypher: xác nhận auditing không tự áp dụng nếu không qua entity mapping.

## 13. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `@EnableNeo4jAuditing` trong reactive persistence path | Cấu hình dùng auditing imperative | Dùng `@EnableReactiveNeo4jAuditing` |
| Dùng `AuditorAware<T>` thay cho `ReactiveAuditorAware<T>` | Lấy auditor theo kiểu đồng bộ, không theo reactive context | Triển khai `ReactiveAuditorAware<T>` |
| Sai tên `auditorAwareRef` | Không tìm thấy bean cung cấp auditor | Đối chiếu với tên bean trong application context |
| Đọc `SecurityContextHolder` trong WebFlux | Có thể không lấy đúng principal do thread thay đổi | Dùng `ReactiveSecurityContextHolder` |
| Trả auditor cố định cho mọi request | Mọi bản ghi có cùng người thực hiện | Lấy principal hiện tại hoặc định danh system theo use case |
| Không xử lý `Mono.empty()` | Trường auditor có thể không được điền như mong đợi | Xác định chính sách thiếu principal |
| Dùng `block()` trong `getCurrentAuditor()` | Chặn reactive pipeline | Trả publisher từ nguồn xác thực |
| Kỳ vọng auditing tự chạy với raw Cypher | Metadata không được tự cập nhật qua entity mapping | Tự quản lý property hoặc dùng repository/template |
| Dùng `@LastModifiedBy` như lịch sử đầy đủ | Chỉ còn principal sửa gần nhất | Tạo audit log/event riêng |

## 14. Quy trình bật reactive auditing

1. Đảm bảo ứng dụng dùng reactive SDN repository hoặc reactive template.
2. Đánh dấu các property cần theo dõi bằng `@CreatedBy`, `@LastModifiedBy`, `@CreatedDate` và `@LastModifiedDate`.
3. Thêm `@EnableReactiveNeo4jAuditing` vào lớp cấu hình được Spring scan.
4. Nếu cần principal, tạo bean `ReactiveAuditorAware<T>` và đặt tên rõ ràng.
5. Khai báo `auditorAwareRef` trùng tên bean.
6. Lấy principal từ Reactor Context, thường qua `ReactiveSecurityContextHolder` trong WebFlux.
7. Quy định hành vi khi không có auditor và cách nhận diện tác vụ nền.
8. Dùng reactive repository/template để lưu entity và kiểm thử metadata sau khi publisher hoàn tất.
9. Dùng audit event riêng nếu cần lịch sử đầy đủ của mọi thay đổi.

## 15. Tự kiểm tra

1. `@EnableReactiveNeo4jAuditing` có vai trò gì trong ứng dụng SDN reactive?
2. `ReactiveAuditorAware<T>` khác `AuditorAware<T>` ở kiểu trả về và ngữ cảnh thực thi nào?
3. Khi nào ứng dụng không cần khai báo `ReactiveAuditorAware`?
4. Vì sao nên dùng `ReactiveSecurityContextHolder` thay cho `SecurityContextHolder` trong WebFlux?
5. `auditorAwareRef` phải khớp với thông tin nào trong Spring context?
6. `modifyOnCreate` ảnh hưởng ra sao đến `@LastModifiedBy` và `@LastModifiedDate`?
7. Điều gì xảy ra khi `getCurrentAuditor()` trả `Mono.empty()`?
8. Vì sao raw Cypher qua `Neo4jClient` không tự nhận auditing metadata?
9. Khi nào cần audit log riêng thay vì chỉ dùng `@LastModifiedBy`?

`@EnableReactiveNeo4jAuditing` kích hoạt hạ tầng auditing cho reactive SDN, còn `ReactiveAuditorAware<T>` cung cấp principal qua `Mono<T>`. Hãy lấy người thực hiện từ Reactor Context, cấu hình đúng bean reference và xác định rõ hành vi khi không có principal. Bốn trường auditing giúp biết ai tạo, ai sửa và thời điểm gần nhất; nếu cần lịch sử đầy đủ, hãy bổ sung event hoặc audit log riêng.

Tài liệu tham khảo:

- [Spring Data Neo4j – Auditing](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [EnableReactiveNeo4jAuditing API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/config/EnableReactiveNeo4jAuditing.html)
- [ReactiveAuditorAware API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/ReactiveAuditorAware.html)
- [Spring Data Commons – ReactiveAuditorAware](https://docs.spring.io/spring-data/commons/reference/auditing.html)
