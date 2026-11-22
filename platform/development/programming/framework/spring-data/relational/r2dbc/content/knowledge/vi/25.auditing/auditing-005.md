# Lấy danh tính từ ngữ cảnh bảo mật phản ứng

Trong Spring Data Relational R2DBC, auditing có thể tự động ghi nhận người tạo và người sửa một entity thông qua `@CreatedBy` và `@LastModifiedBy`. Với ứng dụng Spring WebFlux và Spring Security reactive, danh tính hiện tại cần được lấy từ `ReactiveSecurityContextHolder`, vì security context được truyền theo Reactor Context của subscription thay vì dựa vào `ThreadLocal` như mô hình imperative truyền thống.

Spring Data cung cấp `ReactiveAuditorAware<T>` để trả về auditor hiện tại dưới dạng `Mono<T>`. Khi auditing xử lý entity, implementation này đọc `Authentication` từ reactive security context, xác định principal phù hợp rồi phát ra định danh cần lưu. Nếu không có security context hoặc request chưa được xác thực, publisher có thể hoàn tất rỗng; ứng dụng cần quyết định rõ trường audit có được phép để trống hay phải dùng một danh tính hệ thống trong workflow nền.

## 1. Auditing và danh tính người thực hiện

Auditing ghi lại metadata về vòng đời của một entity. Các annotation thường dùng gồm:

| Annotation | Ý nghĩa |
|---|---|
| `@CreatedBy` | Người hoặc tác nhân tạo entity |
| `@LastModifiedBy` | Người hoặc tác nhân sửa entity gần nhất |
| `@CreatedDate` | Thời điểm entity được tạo |
| `@LastModifiedDate` | Thời điểm entity được sửa gần nhất |

Ví dụ một bản ghi khách hàng có các trường audit:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;

    private String email;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String lastModifiedBy;

    @CreatedDate
    private Instant createdDate;

    @LastModifiedDate
    private Instant lastModifiedDate;
}
```

Khi entity được tạo hoặc cập nhật qua cơ chế Spring Data auditing, framework lấy auditor từ `ReactiveAuditorAware` và gán vào các trường tương ứng. Thời điểm được cung cấp qua date-time provider của auditing.

Auditing entity không tự tạo một lịch sử bất biến cho mọi thay đổi. `@CreatedBy` và `@LastModifiedBy` chỉ lưu người tạo và người sửa gần nhất trên bản ghi hiện tại. Nếu cần lưu đầy đủ từng lần thay đổi, giá trị cũ/mới, lý do và actor của từng sự kiện, hãy thiết kế audit log hoặc event history riêng.

## 2. Vì sao phải dùng ReactiveSecurityContextHolder?

Trong Spring Security reactive, `SecurityContext` được lưu trong Reactor Context gắn với subscription. Một request có thể đi qua nhiều thread khi pipeline chuyển scheduler; do đó không thể dựa vào việc một `ThreadLocal` luôn chứa đúng người dùng.

API phù hợp để lấy security context trong reactive pipeline là:

```java
ReactiveSecurityContextHolder.getContext()
```

API này trả về `Mono<SecurityContext>`. Khi subscription đang chạy trong ngữ cảnh đã được Spring Security thiết lập, publisher có thể phát `SecurityContext` tương ứng. Nếu không có context, publisher thường hoàn tất rỗng.

Không dùng cách imperative sau trong code reactive:

```java
SecurityContext context = SecurityContextHolder.getContext();
Authentication authentication = context.getAuthentication();
```

`SecurityContextHolder` thông thường dựa trên chiến lược lưu trữ imperative/ThreadLocal. Trong WebFlux, code có thể chạy trên thread khác nhau và không bảo đảm đọc được context đúng. `ReactiveSecurityContextHolder` được thiết kế để đọc context theo subscription.

### 2.1. Reactor Context không phải ThreadLocal

Reactor Context gắn với subscriber và được truyền qua các toán tử reactive. Ví dụ:

```text
WebFlux Security WebFilter
          |
          v
Tạo SecurityContext trong Reactor Context
          |
          v
Controller trả Mono / Flux
          |
          v
Service và Repository compose publisher
          |
          v
ReactiveAuditorAware đọc context
          |
          v
Auditing gán createdBy / lastModifiedBy
```

Việc chuyển thread bằng `publishOn` hoặc `subscribeOn` không tự làm mất Reactor Context khi dùng các operator Reactor theo đúng cách. Tuy nhiên, tạo subscription độc lập bằng `subscribe()` hoặc chuyển sang API imperative không giữ context có thể làm mất ngữ cảnh request. Vì vậy, hãy compose publisher xuyên suốt thay vì tự subscribe trong repository/service.

## 3. ReactiveAuditorAware là gì?

Spring Data Commons cung cấp interface `ReactiveAuditorAware<T>` để xác định auditor hiện tại theo mô hình reactive. Phương thức chính trả về `Mono<T>`:

```java
public interface ReactiveAuditorAware<T> {
    Mono<T> getCurrentAuditor();
}
```

Kiểu `T` phải phù hợp với kiểu dữ liệu các trường được đánh dấu `@CreatedBy` và `@LastModifiedBy`. Ví dụ:

- `ReactiveAuditorAware<String>` nếu lưu username hoặc subject.
- `ReactiveAuditorAware<Long>` nếu lưu khóa người dùng nội bộ.
- `ReactiveAuditorAware<UUID>` nếu hệ thống dùng UUID làm định danh actor.

Khác với `AuditorAware<T>` đồng bộ trả `Optional<T>`, `ReactiveAuditorAware<T>` trả `Mono<T>` để việc lấy danh tính có thể tham gia reactive pipeline.

## 4. Lấy username từ Authentication

Trong trường hợp phổ biến, `Authentication.getName()` cung cấp tên định danh của principal. Có thể triển khai auditor như sau:

```java
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("auditorProvider")
public class SecurityAuditorAware implements ReactiveAuditorAware<String> {

    @Override
    public Mono<String> getCurrentAuditor() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .filter(authentication ->
                !(authentication instanceof AnonymousAuthenticationToken))
            .map(Authentication::getName)
            .filter(name -> !name.isBlank());
    }
}
```

Các bước xử lý:

1. `getContext()` lấy `Mono<SecurityContext>` từ Reactor Context.
2. `map(SecurityContext::getAuthentication)` lấy đối tượng `Authentication`.
3. `filter(Authentication::isAuthenticated)` chỉ giữ authentication đã được xác thực.
4. Loại `AnonymousAuthenticationToken`, vì anonymous authentication có thể báo `isAuthenticated() == true` nhưng không đại diện cho người dùng đã đăng nhập.
5. `map(Authentication::getName)` lấy định danh principal.
6. Loại tên rỗng để tránh lưu giá trị không hữu ích.

Nếu không có context, authentication chưa xác thực hoặc là anonymous, publisher hoàn tất rỗng. Auditor không tự ý gán một người dùng giả.

### 4.1. Vì sao cần loại AnonymousAuthenticationToken?

Trong một số cấu hình Spring Security, request chưa đăng nhập vẫn có thể có `Authentication` đại diện anonymous. Token này được dùng để biểu diễn một principal ẩn danh và có thể được đánh dấu authenticated theo semantics nội bộ của Spring Security.

Chỉ kiểm tra `isAuthenticated()` vì vậy chưa đủ. Nếu lưu tên principal anonymous vào `createdBy`, dữ liệu audit có thể ghi một giá trị kỹ thuật như `anonymousUser` thay vì người thực hiện thật. Hãy loại anonymous token hoặc áp dụng quy tắc actor riêng theo nghiệp vụ.

### 4.2. Không dùng principal.toString() làm định danh

Không nên:

```java
.map(authentication -> authentication.getPrincipal().toString())
```

`toString()` có thể chứa nhiều thông tin hơn tên định danh, phụ thuộc implementation của principal và có nguy cơ đưa dữ liệu cá nhân hoặc chi tiết xác thực vào cột audit. Dùng `Authentication.getName()` hoặc trích một thuộc tính ID rõ ràng từ principal đã được định nghĩa.

## 5. Lưu user ID nội bộ thay vì username

Username có thể thay đổi theo thời gian. Nếu hệ thống có khóa người dùng nội bộ ổn định, lưu user ID thường thuận tiện hơn cho việc liên kết dữ liệu và xử lý đổi tên.

Giả sử ứng dụng dùng custom principal:

```java
public record AppPrincipal(Long userId, String username) {
}
```

Một `Authentication` tùy chỉnh có thể đặt `AppPrincipal` làm principal. Auditor lấy `userId`:

```java
@Component("auditorProvider")
public class UserIdAuditorAware implements ReactiveAuditorAware<Long> {

    @Override
    public Mono<Long> getCurrentAuditor() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .filter(authentication ->
                !(authentication instanceof AnonymousAuthenticationToken))
            .map(Authentication::getPrincipal)
            .filter(AppPrincipal.class::isInstance)
            .cast(AppPrincipal.class)
            .map(AppPrincipal::userId);
    }
}
```

Nếu principal không phải `AppPrincipal`, publisher hoàn tất rỗng. Đây là lựa chọn an toàn hơn việc ép kiểu không kiểm tra và gây `ClassCastException` cho một loại authentication khác.

Entity khi đó dùng kiểu tương ứng:

```java
@CreatedBy
private Long createdBy;

@LastModifiedBy
private Long lastModifiedBy;
```

Schema database cần có kiểu cột tương thích. Nếu có foreign key tới bảng user, hãy cân nhắc chính sách xóa/ẩn danh hóa user để dữ liệu lịch sử không bị mất.

## 6. Hỗ trợ các loại Authentication khác nhau

Spring Security có nhiều kiểu principal tùy cơ chế đăng nhập. Không nên giả định `getPrincipal()` luôn trả về `UserDetails`.

| Cơ chế xác thực | Dạng principal thường gặp | Định danh có thể dùng |
|---|---|---|
| Form login / username-password | `UserDetails` hoặc principal tùy chỉnh | Username hoặc user ID nội bộ |
| HTTP Basic | Principal theo cấu hình authentication provider | `Authentication.getName()` hoặc ID từ principal |
| OAuth2 Login | `OAuth2User` | `getName()` hoặc subject/provider ID đã ánh xạ |
| Resource Server JWT | `Jwt` trong `JwtAuthenticationToken` | Claim `sub` hoặc user ID đã ánh xạ |
| Opaque token | `OAuth2AuthenticatedPrincipal` | Name hoặc claim định danh đã được xác thực |
| Authentication tùy chỉnh | Kiểu principal do ứng dụng định nghĩa | Thuộc tính ID ổn định của ứng dụng |

Với `Authentication.getName()`, nhiều loại authentication chuẩn đã cung cấp tên phù hợp. Tuy nhiên, hệ thống cần định danh ổn định qua nhiều provider nên có thể ánh xạ principal về một ID nội bộ ngay ở tầng authentication.

### 6.1. JWT và subject

Với Resource Server JWT, `JwtAuthenticationToken` thường cung cấp tên dựa trên claim `sub`. Ví dụ auditor String có thể dùng:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .filter(Authentication::isAuthenticated)
    .filter(authentication ->
        !(authentication instanceof AnonymousAuthenticationToken))
    .map(Authentication::getName);
```

Không tự đọc claim từ một JWT chưa được xác minh. Auditor phải dựa trên `Authentication` đã được Spring Security xác thực, không lấy `sub` từ header hoặc payload do client gửi mà không qua validation chữ ký, issuer, audience và thời hạn.

Nếu `sub` là ID từ hệ thống identity provider, cần quyết định nó có đủ ổn định và duy nhất trong hệ thống ứng dụng hay không. Có thể cần ánh xạ cặp `(issuer, subject)` sang user ID nội bộ để tránh trùng subject giữa nhiều issuer.

### 6.2. OAuth2 Login và nhiều identity provider

Hai provider có thể trả về cùng một username cho hai người khác nhau. Nếu lưu username đơn lẻ, audit record có thể nhập nhằng. Hãy dùng ID nội bộ hoặc một định danh có namespace như provider/issuer cùng subject.

Không lưu access token, refresh token, ID token hoặc toàn bộ attributes của `OAuth2User` vào trường auditor. Chỉ lưu định danh actor đã được lựa chọn.

## 7. Cấu hình R2DBC auditing

Sau khi có implementation `ReactiveAuditorAware`, bật auditing cho Spring Data R2DBC:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.r2dbc.config.EnableR2dbcAuditing;

@Configuration
@EnableR2dbcAuditing(auditorAwareRef = "auditorProvider")
public class R2dbcAuditingConfiguration {
}
```

`auditorAwareRef` trỏ tới bean `ReactiveAuditorAware` đã khai báo. Trong ví dụ trước, bean có tên `auditorProvider` nhờ `@Component("auditorProvider")`.

Nếu ứng dụng chỉ có một bean auditor phù hợp, cấu hình có thể dùng auditor mặc định theo cách phiên bản Spring Data hỗ trợ. Khi có nhiều auditor provider, chỉ định tên bean rõ ràng để tránh framework chọn nhầm.

### 7.1. Bật cả date auditing

`@EnableR2dbcAuditing` cũng bật cơ chế gán ngày tạo và ngày sửa. Entity có thể khai báo:

```java
@CreatedDate
private Instant createdDate;

@LastModifiedDate
private Instant lastModifiedDate;
```

Auditor provider và date-time provider là hai nguồn khác nhau:

- `ReactiveAuditorAware` cung cấp ai thực hiện.
- DateTimeProvider cung cấp thời điểm.

Nếu cần dùng clock tùy chỉnh cho test hoặc quy tắc thời gian riêng, cấu hình date-time provider theo API của phiên bản Spring Data đang dùng. Không lấy thời gian từ principal hoặc security context.

### 7.2. Auditing cần entity được lưu qua Spring Data

Auditing được áp dụng trong lifecycle callback của Spring Data. Nếu ứng dụng ghi SQL trực tiếp bằng một cách không đi qua entity auditing callback, các annotation trên entity không tự động được áp dụng cho câu SQL đó.

Ví dụ `DatabaseClient` thực hiện `INSERT` trực tiếp cần bind các cột audit mà ứng dụng muốn ghi:

```java
databaseClient.sql("""
        INSERT INTO customer(name, created_by, created_date)
        VALUES (:name, :createdBy, :createdDate)
        """)
    .bind("name", name)
    .bind("createdBy", auditorId)
    .bind("createdDate", Instant.now())
    .fetch()
    .rowsUpdated();
```

Không giả định `@CreatedBy` tự bổ sung giá trị cho SQL tùy chỉnh. Nếu cần auditor cho các thao tác SQL trực tiếp, hãy lấy danh tính qua một service/provider phù hợp và bind rõ ràng, hoặc dùng entity persistence path có auditing callback.

## 8. Gắn auditor vào entity khi INSERT và UPDATE

Một entity mẫu:

```java
@Table("document")
public class Document {

    @Id
    private Long id;

    private String title;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String lastModifiedBy;

    @CreatedDate
    private Instant createdDate;

    @LastModifiedDate
    private Instant lastModifiedDate;
}
```

Khi tạo mới:

```java
Mono<Document> createDocument(String title) {
    return documentRepository.save(new Document(title));
}
```

Auditing có thể gán `createdBy`, `lastModifiedBy`, `createdDate` và `lastModifiedDate` theo cấu hình `modifyOnCreate` và date provider.

Khi cập nhật:

```java
Mono<Document> renameDocument(Long id, String newTitle) {
    return documentRepository.findById(id)
        .switchIfEmpty(Mono.error(new DocumentNotFoundException(id)))
        .flatMap(document -> {
            document.setTitle(newTitle);
            return documentRepository.save(document);
        });
}
```

Auditing có thể cập nhật `lastModifiedBy` và `lastModifiedDate` theo auditor/time provider tại thời điểm save. `createdBy` và `createdDate` thường được giữ nguyên sau khi entity đã được tạo.

### 8.1. `modifyOnCreate`

Theo cấu hình auditing, `modifyOnCreate` quyết định các trường modified có được gán khi entity mới được tạo hay không. Khi bật, `@LastModifiedBy` và `@LastModifiedDate` có thể có cùng giá trị với trường created ở lần ghi đầu. Hành vi này có thể hữu ích để trường modified luôn có giá trị, nhưng hãy chọn theo quy ước schema và nghiệp vụ.

Ví dụ cấu hình tường minh:

```java
@EnableR2dbcAuditing(
    auditorAwareRef = "auditorProvider",
    modifyOnCreate = true
)
```

Nếu muốn `lastModifiedBy` chỉ có giá trị sau lần cập nhật đầu tiên, hãy cân nhắc cấu hình `modifyOnCreate = false` và kiểm thử trên phiên bản framework đang dùng.

## 9. Khi không có SecurityContext

Không phải mọi thao tác R2DBC đều phát sinh từ một HTTP request đã đăng nhập. Những trường hợp thường gặp:

- Job chạy theo lịch.
- Batch import/export.
- Message consumer.
- Migration hoặc tác vụ quản trị.
- Integration test không thiết lập security context.
- Request anonymous hoặc luồng public được phép ghi dữ liệu.

Trong các trường hợp này, `ReactiveSecurityContextHolder.getContext()` có thể hoàn tất rỗng. `ReactiveAuditorAware` cũng có thể trả `Mono.empty()`, khiến trường auditor không được gán bởi provider. Schema và nghiệp vụ cần quyết định trường đó có nullable hay không.

Không tự động gán `anonymousUser` hoặc `system` cho mọi trường hợp rỗng nếu chưa phân biệt nguyên nhân. Làm vậy có thể khiến thao tác của người dùng chưa đăng nhập bị ghi nhầm là job hệ thống.

### 9.1. Danh tính hệ thống cho background job

Nếu job cần một actor hệ thống, hãy thiết lập danh tính hệ thống một cách tường minh trong workflow do ứng dụng kiểm soát. Một cách là dùng một khóa Reactor Context riêng cho auditor hệ thống:

```java
public final class AuditActorContext {
    public static final String AUDIT_ACTOR_KEY = "audit.actor";

    private AuditActorContext() {
    }
}
```

Auditor có thể ưu tiên actor được gắn bởi một workflow nội bộ, rồi mới đọc Spring Security context:

```java
@Component("auditorProvider")
public class ContextAwareAuditor implements ReactiveAuditorAware<String> {

    @Override
    public Mono<String> getCurrentAuditor() {
        return Mono.deferContextual(contextView -> {
            if (contextView.hasKey(AuditActorContext.AUDIT_ACTOR_KEY)) {
                return Mono.just(contextView.get(
                    AuditActorContext.AUDIT_ACTOR_KEY));
            }

            return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .filter(Authentication::isAuthenticated)
                .filter(authentication ->
                    !(authentication instanceof AnonymousAuthenticationToken))
                .map(Authentication::getName);
        });
    }
}
```

Job nội bộ có thể gắn actor khi tạo pipeline:

```java
public Mono<Void> runNightlyImport() {
    return importService.importData()
        .then()
        .contextWrite(context -> context.put(
            AuditActorContext.AUDIT_ACTOR_KEY,
            "system:nightly-import"
        ));
}
```

Khóa context này phải do code nội bộ kiểm soát. Không cho client HTTP gửi giá trị tùy ý để tự nhận mình là `system` hoặc một actor khác. Cần xác định rõ job nào được phép dùng actor hệ thống và tên actor phải ổn định, có thể truy vết.

Một lựa chọn đơn giản hơn là một auditor provider riêng cho background worker hoặc một `ReactiveAuditorAware` có fallback cố định. Chỉ dùng fallback khi ứng dụng đã bảo đảm luồng đó không thể là request người dùng chưa xác thực.

### 9.2. Public endpoint có quyền ghi dữ liệu

Nếu một endpoint public cho phép tạo dữ liệu mà không cần đăng nhập, hãy quyết định cách biểu diễn actor:

- `createdBy = null` nếu schema và nghiệp vụ cho phép không xác định người dùng.
- Một actor kỹ thuật như `anonymous:public-api` nếu cần phân biệt nguồn ghi.
- Một danh tính từ API key/client credential đã được xác thực nếu endpoint dùng machine-to-machine authentication.

Không coi `anonymousUser` là người dùng thật. Nếu cần kiểm toán ai gọi API, hãy lưu client/application identity riêng và phân biệt với end-user identity.

## 10. Context propagation qua Reactor pipeline

Reactive security context chỉ được đọc đúng khi thao tác auditing được thực thi trong subscription có context tương ứng. Hãy giữ publisher trong cùng pipeline:

```java
@Transactional
public Mono<Document> createDocument(Document document) {
    return documentRepository.save(document)
        .flatMap(saved -> auditEventRepository.save(
            AuditEvent.documentCreated(saved.getId())
        ).thenReturn(saved));
}
```

Khi WebFlux Security đã thiết lập context cho request và publisher được compose bình thường, auditing callback có thể đọc principal tương ứng.

Các hành vi có thể làm mất hoặc thay đổi context:

- Gọi `subscribe()` thủ công để tạo subscription độc lập.
- Chuyển sang callback imperative không giữ Reactor Context.
- Gọi một API blocking hoặc thread pool tùy chỉnh mà không có cơ chế context propagation phù hợp.
- Tạo công việc nền tách khỏi request rồi kỳ vọng nó vẫn mang danh tính request ban đầu.

`publishOn` và `subscribeOn` của Reactor thường giữ Reactor Context qua pipeline, nhưng không đồng nghĩa mọi `ThreadLocal` hoặc MDC tùy chỉnh tự động được truyền. Nếu cần log context, hãy cấu hình Micrometer Context Propagation/Tracing theo phiên bản Spring/Reactor hoặc đọc metadata từ Reactor Context ở đúng chỗ.

### 10.1. Không mang danh tính người dùng sang job chạy muộn một cách vô thức

Một request có thể tạo một công việc được xử lý vài phút sau. Nếu job đó giữ nguyên principal của request mà không có chính sách rõ ràng, audit có thể khiến người đọc hiểu nhầm người dùng trực tiếp thực hiện thao tác nền.

Hãy quyết định actor của job:

- Người dùng khởi tạo yêu cầu: lưu `requestedBy` trong bản ghi job.
- Worker thực hiện thay đổi: `lastModifiedBy` có thể là actor hệ thống/worker.
- Cần cả hai: lưu riêng `requestedBy` và `processedBy` hoặc ghi event audit riêng.

Không dựa vào việc Reactor Context tình cờ còn tồn tại để giữ danh tính cho một tác vụ được xếp hàng hoặc retry ở thời điểm khác.

## 11. Danh tính người dùng, tenant và actor hệ thống

Trong hệ thống multi-tenant, chỉ lưu username có thể chưa đủ để xác định ngữ cảnh. Có thể cần thêm các trường như:

```java
@CreatedBy
private Long createdBy;

private Long createdTenantId;

private String createdActorType;
```

`@CreatedBy` chỉ cung cấp auditor theo cấu hình. Tenant ID và actor type có thể cần được lấy từ một context provider khác hoặc gộp vào một kiểu auditor tùy chỉnh.

Ví dụ auditor dạng record:

```java
public record AuditActor(Long userId, Long tenantId, String actorType) {
}
```

```java
ReactiveAuditorAware<AuditActor> auditorAware = () ->
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(Authentication::isAuthenticated)
        .filter(authentication ->
            !(authentication instanceof AnonymousAuthenticationToken))
        .map(authentication -> (AppPrincipal) authentication.getPrincipal())
        .map(principal -> new AuditActor(
            principal.userId(),
            principal.tenantId(),
            "USER"
        ));
```

Đây là ví dụ cần custom principal đúng kiểu. Trong hệ thống thực tế, tránh cast trực tiếp nếu có nhiều loại Authentication; dùng kiểm tra kiểu và chính sách fallback phù hợp.

Auditing không thay thế authorization. `@CreatedBy` ghi lại actor, nhưng không tự kiểm tra người đó có quyền tạo hoặc sửa entity trong tenant hay không. Authorization phải được thực hiện riêng ở security/service layer và cần kiểm tra tenant scope trong truy vấn.

## 12. Bảo vệ dữ liệu trong principal và trường auditor

Principal có thể chứa nhiều thuộc tính như username, email, display name, tenant, roles hoặc claims. Chỉ chọn định danh tối thiểu cần lưu.

Không lưu những dữ liệu sau vào trường auditor:

- Password hoặc password hash.
- Access token, refresh token, ID token hoặc JWT nguyên bản.
- Session cookie hoặc API key.
- Toàn bộ `UserDetails`, `Jwt` hoặc OAuth2 attributes được serialize.
- Thông tin cá nhân không cần thiết cho mục đích audit.

Thường nên lưu user ID nội bộ hoặc subject ổn định. Nếu cần hiển thị tên người dùng trong giao diện audit, join sang bảng user hoặc service directory khi đọc thay vì sao chép toàn bộ hồ sơ vào mỗi entity.

Nếu user có thể bị xóa hoặc ẩn danh hóa, hãy chọn chiến lược phù hợp: giữ ID tham chiếu, chuyển sang actor tombstone, hoặc lưu một snapshot tối thiểu được phép. Không dùng cascade delete làm mất dấu vết audit nếu yêu cầu pháp lý/nghiệp vụ cần giữ lịch sử.

## 13. Auditing và SQL tùy chỉnh

Các annotation auditing được áp dụng qua lifecycle callback của Spring Data khi entity được insert/update bằng đường persistence có hỗ trợ auditing. Khi dùng `DatabaseClient` hoặc raw R2DBC SPI, câu SQL không tự chạy entity callback.

Ví dụ:

```java
databaseClient.sql("""
        UPDATE document
        SET title = :title,
            last_modified_by = :actor,
            last_modified_date = :modifiedAt
        WHERE id = :id
        """)
    .bind("title", title)
    .bind("actor", actor)
    .bind("modifiedAt", clock.instant())
    .bind("id", id)
    .fetch()
    .rowsUpdated();
```

Ở đây ứng dụng tự lấy actor và thời điểm rồi bind vào SQL. Nếu có nhiều chỗ dùng SQL tùy chỉnh, hãy gom logic lấy actor vào một abstraction chung để tránh mỗi repository tự đọc security context theo cách khác nhau.

Một lựa chọn khác là thực hiện update entity qua repository/template để auditing callback được kích hoạt, nếu thao tác và mapping phù hợp với use case.

## 14. Kiểm thử ReactiveAuditorAware

Kiểm thử auditor nên xác nhận các trường hợp có security context, anonymous và không có context.

### 14.1. Principal đã xác thực

Ví dụ unit test dùng `ReactiveSecurityContextHolder.withAuthentication`:

```java
@Test
void returnsAuthenticatedUserName() {
    Authentication authentication =
        UsernamePasswordAuthenticationToken.authenticated(
            "alice",
            "n/a",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );

    StepVerifier.create(
            auditorAware.getCurrentAuditor()
                .contextWrite(ReactiveSecurityContextHolder
                    .withAuthentication(authentication))
        )
        .expectNext("alice")
        .verifyComplete();
}
```

Publisher được test subscribe qua `StepVerifier`; `contextWrite` cung cấp security context cho subscription đó. Đây là cách kiểm tra ReactiveAuditorAware độc lập với HTTP filter chain.

### 14.2. Không có context

```java
@Test
void completesEmptyWhenNoSecurityContextExists() {
    StepVerifier.create(auditorAware.getCurrentAuditor())
        .verifyComplete();
}
```

Test xác nhận provider không tự tạo một username khi không có context.

### 14.3. Anonymous authentication

```java
@Test
void ignoresAnonymousAuthentication() {
    Authentication anonymous =
        new AnonymousAuthenticationToken(
            "key",
            "anonymousUser",
            List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS"))
        );

    StepVerifier.create(
            auditorAware.getCurrentAuditor()
                .contextWrite(ReactiveSecurityContextHolder
                    .withAuthentication(anonymous))
        )
        .verifyComplete();
}
```

Test này đảm bảo `isAuthenticated()` không làm anonymous principal bị ghi nhầm như người dùng đã đăng nhập.

### 14.4. Kiểm thử tích hợp auditing trên R2DBC

Unit test provider chưa chứng minh Spring Data đã gán trường vào entity. Cần integration test với database/driver phù hợp:

1. Thiết lập `ReactiveAuditorAware` và bật `@EnableR2dbcAuditing`.
2. Tạo publisher save entity trong security context có actor.
3. Subscribe và đợi save hoàn tất.
4. Đọc lại entity từ database.
5. Xác nhận `createdBy`, `lastModifiedBy` và các date field có giá trị mong đợi.
6. Cập nhật entity với một actor khác và xác nhận trường created giữ nguyên, trường modified thay đổi theo cấu hình.
7. Lặp lại với context rỗng, anonymous và background actor.

Ví dụ composition test:

```java
Mono<Document> saveAsAlice = documentRepository.save(document)
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(aliceAuth));

StepVerifier.create(saveAsAlice)
    .assertNext(saved -> assertEquals("alice", saved.getCreatedBy()))
    .verifyComplete();
```

Đây là ví dụ minh họa. Tên field getter và cách tạo entity phụ thuộc model thực tế. Với integration test, đọc lại database để xác nhận giá trị đã được ghi, không chỉ kiểm tra object trong bộ nhớ.

## 15. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `SecurityContextHolder` imperative trong WebFlux | Có thể không lấy được principal đúng khi thread thay đổi | Dùng `ReactiveSecurityContextHolder` |
| Dùng `AuditorAware` đồng bộ thay `ReactiveAuditorAware` | Không tận dụng reactive context đúng cách | Triển khai `ReactiveAuditorAware<T>` |
| Chỉ kiểm tra `isAuthenticated()` | Anonymous token có thể bị coi là authenticated | Loại `AnonymousAuthenticationToken` hoặc xác định actor riêng |
| Lấy `principal.toString()` | Có thể lưu dữ liệu thừa hoặc nhạy cảm | Dùng `Authentication.getName()` hoặc ID rõ ràng |
| Ép principal sang một kiểu mà không kiểm tra | `ClassCastException` với OAuth2/JWT hoặc custom auth khác | Kiểm tra kiểu và xử lý các loại principal được hỗ trợ |
| Lưu username có thể thay đổi khi cần định danh lâu dài | Audit record khó liên kết sau khi đổi username | Lưu user ID/subject ổn định |
| Không bật `@EnableR2dbcAuditing` | Annotation auditing không được xử lý | Bật cấu hình và khai báo auditor provider |
| Bean name trong `auditorAwareRef` không khớp | Không tìm thấy provider hoặc chọn sai bean | Khai báo tên bean rõ ràng |
| Gọi `subscribe()` thủ công trong service | Mất Reactor Context và transaction propagation | Compose publisher và trả về caller |
| Dùng `DatabaseClient` rồi kỳ vọng annotation tự gán auditor | SQL tùy chỉnh bỏ qua entity auditing callback | Bind actor/date tường minh hoặc dùng entity persistence path |
| Gán `system` cho mọi context rỗng | Có thể ghi nhầm request anonymous thành job hệ thống | Phân biệt request, anonymous và background actor |
| Mang principal của request sang job chạy muộn | Audit thể hiện sai actor thực thi | Lưu requestedBy và processedBy riêng khi cần |
| Lưu token hoặc toàn bộ principal | Tạo dữ liệu nhạy cảm trong bảng audit | Chỉ lưu định danh tối thiểu |
| Cho rằng auditing kiểm tra quyền truy cập | Có thể ghi actor nhưng vẫn sửa dữ liệu trái quyền | Thực hiện authorization riêng |
| Không test với security context thật | Không phát hiện context propagation hoặc callback lỗi | Test provider và integration test R2DBC |

## 16. Quy trình triển khai auditing theo reactive security context

Khi triển khai danh tính người tạo/người sửa, có thể đi theo trình tự:

1. **Chọn định danh:** username, subject từ identity provider hay user ID nội bộ; ưu tiên định danh ổn định.
2. **Chọn kiểu auditor:** `String`, `Long`, `UUID` hoặc một kiểu domain phù hợp với entity.
3. **Triển khai ReactiveAuditorAware:** đọc `ReactiveSecurityContextHolder`, kiểm tra authentication và loại anonymous.
4. **Cấu hình auditing:** bật `@EnableR2dbcAuditing` và trỏ `auditorAwareRef` tới đúng bean.
5. **Đánh dấu entity:** dùng `@CreatedBy`, `@LastModifiedBy` và date annotations cần thiết.
6. **Quy định context rỗng:** xác định hành vi cho public request, scheduled job, worker và test.
7. **Thiết kế actor hệ thống:** dùng context nội bộ hoặc provider riêng, không gán fallback mù quáng.
8. **Giữ reactive context:** compose publisher xuyên suốt và không tự subscribe trong repository/service.
9. **Xử lý SQL tùy chỉnh:** bind audit fields rõ ràng nếu thao tác không đi qua auditing callback.
10. **Bảo vệ định danh:** không lưu token, password hoặc toàn bộ principal.
11. **Kiểm thử:** kiểm tra authenticated, anonymous, no-context, background actor, INSERT và UPDATE trên database thật.

## 17. Nguyên tắc cần nhớ

- Spring Data R2DBC dùng `ReactiveAuditorAware<T>` để lấy actor hiện tại theo mô hình reactive.
- Reactive security context nằm trong Reactor Context; dùng `ReactiveSecurityContextHolder.getContext()` thay cho `SecurityContextHolder` imperative.
- `getCurrentAuditor()` trả `Mono<T>` và có thể hoàn tất rỗng nếu không có principal phù hợp.
- Kiểm tra `Authentication.isAuthenticated()` và loại `AnonymousAuthenticationToken`.
- `Authentication.getName()` phù hợp cho nhiều cơ chế xác thực; user ID nội bộ thường ổn định hơn username.
- Không giả định mọi principal đều là `UserDetails`; OAuth2, JWT và custom authentication có thể dùng kiểu khác.
- Bật `@EnableR2dbcAuditing` và cấu hình đúng `auditorAwareRef`.
- Dùng `@CreatedBy`/`@LastModifiedBy` cho actor và date annotations cho thời điểm.
- Auditing callback áp dụng qua Spring Data entity persistence; SQL tùy chỉnh cần bind audit fields rõ ràng.
- Không tự gán `system` cho mọi trường hợp thiếu context; phân biệt anonymous request với background job.
- Với job nền, xác định riêng người yêu cầu và actor thực thi nếu cần.
- Không lưu password, token hoặc toàn bộ principal trong trường auditor.
- Auditing không thay thế authorization và không tự tạo lịch sử bất biến của mọi thay đổi.
- Kiểm thử context propagation và việc gán field trên database/driver thực tế.

Lấy danh tính từ ngữ cảnh bảo mật phản ứng giúp các trường `createdBy` và `lastModifiedBy` phản ánh đúng actor của subscription đang thực hiện thao tác R2DBC. `ReactiveAuditorAware` kết nối Spring Data auditing với `ReactiveSecurityContextHolder`, còn Reactor Context giữ danh tính xuyên suốt pipeline mà không phụ thuộc thread cố định. Khi chọn định danh ổn định, loại anonymous, xử lý rõ context rỗng và tách actor hệ thống khỏi người dùng, dữ liệu auditing sẽ nhất quán và có ý nghĩa trong cả request WebFlux lẫn các workflow nền.
