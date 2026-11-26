# AuditorAware và giá trị người thao tác

## 1. Ai được ghi nhận là người tạo hoặc người sửa?

Một ghi chú được người dùng `u-42` tạo, sau đó người dùng `u-73` sửa nội dung. Ứng dụng muốn giữ người tạo là `user:u-42` và người sửa gần nhất là `user:u-73`. Khi tác vụ nhập dữ liệu chạy, người thao tác có thể là `system:catalog-import` thay vì một tài khoản đang đăng nhập qua trình duyệt.

Bài học thuộc chương **Auditing** của module **SPRING_DATA_COMMONS**. Trọng tâm là abstraction `AuditorAware<T>`, kiểu dữ liệu đại diện cho người thao tác và cách nối nó với hạ tầng auditing của module lưu trữ. Những quyết định này liên quan đến metadata entity và luồng CRUD; chúng không tự cung cấp xác thực, phân quyền hoặc lịch sử thay đổi đầy đủ.

Một hợp đồng auditor cần trả lời được bốn câu hỏi:

1. Người thao tác được định danh bằng giá trị ổn định nào?
2. Giá trị đó đến từ nguồn đã được ứng dụng tin cậy nào?
3. Không có người thao tác thì bỏ trống, dùng tác nhân hệ thống đã xác định hay từ chối thao tác?
4. Luồng ghi nào thực sự gọi hạ tầng auditing?

Không nên chỉ thêm một annotation rồi kỳ vọng bốn quyết định này đã được giải quyết.

## 2. Hợp đồng AuditorAware<T>

`org.springframework.data.domain.AuditorAware<T>` có phương thức trả về `Optional<T>`:

```java
import java.util.Optional;
import org.springframework.data.domain.AuditorAware;

public final class ImportJobAuditor implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        return Optional.of("system:catalog-import");
    }
}
```

`getCurrentAuditor()` cung cấp giá trị người thao tác hiện hành cho hạ tầng gọi nó. Đây là một SPI nhỏ, không phải phương thức lưu entity hoặc tạo người dùng. [API AuditorAware](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AuditorAware.html).

Provider cố định trong ví dụ phù hợp với một tiến trình hoặc cấu hình riêng dành cho tác vụ import đã được ứng dụng xác định. Không đăng ký nó làm nguồn chung cho mọi request người dùng chỉ vì nó luôn trả được một giá trị.

### Vai trò của generic T

Generic `T` phải phù hợp với kiểu property dùng để lưu auditor. Nếu provider trả `String`, các property `@CreatedBy` và `@LastModifiedBy` của thiết kế này dùng `String`. Nếu chọn một value object như `ActorId`, cần kiểm tra mapping và biểu diễn lưu trữ của kiểu đó.

Spring Data dùng `@CreatedBy` và `@LastModifiedBy` cho người tạo, người sửa; `@CreatedDate` và `@LastModifiedDate` cho thời điểm. Hạ tầng phải được bật theo module. Chỉ theo dõi thời gian thì không bắt buộc phải có nguồn auditor. [Spring Data Commons: Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html).

`AuditorAware` không cung cấp thời gian hiện tại; đó là trách nhiệm khác, chẳng hạn `DateTimeProvider`. Cũng không dùng kết quả auditor để thay thế kiểm tra quyền sửa entity.

## 3. Chọn giá trị người thao tác để lưu

### 3.1. Ưu tiên định danh ổn định

Tên hiển thị có thể thay đổi và hai người có thể trùng tên. Email cũng có thể được đổi hoặc dùng lại theo chính sách hệ thống. Nếu cần liên kết người thao tác lâu dài, hãy xác định một ID ổn định phù hợp với vòng đời tài khoản.

Trong bài, auditor được lưu dưới dạng chuỗi có quy ước:

```text
user:u-42
user:u-73
system:catalog-import
```

Tiền tố giúp phân biệt tác nhân người dùng và tác vụ hệ thống. Đây là hợp đồng của ứng dụng minh họa, không phải định dạng do Spring Data áp đặt.

| Kiểu giá trị | Lợi ích | Điều cần thiết kế thêm |
| --- | --- | --- |
| `String` chứa actor ID | Đơn giản, dễ lưu và truy vấn | Quy ước namespace, độ dài, tính duy nhất |
| `UUID` hoặc kiểu ID riêng | Rõ kiểu, hạn chế truyền nhầm dữ liệu | Chuyển đổi và hỗ trợ của store |
| Domain `User` hoặc tham chiếu người dùng | Có liên kết theo mô hình domain | Mapping quan hệ, tải dữ liệu và xử lý khi tài khoản bị xóa |
| Đối tượng `Actor` gồm loại và ID | Biểu diễn người dùng, service, job rõ hơn | Schema và khả năng mapping kiểu phức hợp |

Không lưu nguyên `Authentication`, access token, credentials hoặc toàn bộ security principal vào audit field. Các đối tượng ấy chứa dữ liệu phục vụ phiên xác thực và thường không phải một hợp đồng lưu trữ ổn định.

### 3.2. Tenant và danh tính được ủy quyền

Nếu user ID chỉ duy nhất trong từng tenant, chuỗi `user:42` chưa đủ phân biệt hai tenant. Có thể chọn ID toàn cục hoặc một cấu trúc định danh gồm cả tenant theo hợp đồng ứng dụng.

Nếu người dùng yêu cầu một job chạy thay mình, có thể có hai câu hỏi khác nhau: ai yêu cầu và tiến trình nào thực hiện. Một cặp `createdBy`/`lastModifiedBy` chỉ lưu một giá trị ở mỗi trường; không tự giữ đủ cả hai vai trò. Khi cần, bổ sung metadata như `requestedBy`, `executedBy` hoặc một bản ghi sự kiện riêng.

## 4. Lấy auditor từ Spring Security

### 4.1. Đọc ngữ cảnh xác thực ở thời điểm được gọi

Trong luồng servlet thông thường, `SecurityContextHolder` chứa `SecurityContext`, từ đó lấy `Authentication` và principal. Chiến lược mặc định lưu context theo thread. [Spring Security: Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html).

Không chụp người dùng hiện hành trong constructor của một singleton `AuditorAware`. Constructor có thể chạy lúc khởi động, khi chưa có request, và singleton phục vụ nhiều người dùng khác nhau. Provider phải lấy danh tính của lần thực thi đang diễn ra mỗi khi được gọi.

### 4.2. Không coi mọi Authentication là người dùng thật

Ứng dụng có thể có `AnonymousAuthenticationToken` trong security context. Chỉ kiểm tra `isAuthenticated()` không đủ để diễn đạt chính sách “người dùng đã đăng nhập, không phải anonymous”. Spring Security cung cấp `AuthenticationTrustResolver` để nhận diện trạng thái anonymous. [Spring Security: Anonymous Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html).

Ngoài ra, principal có thể là `UserDetails`, JWT, OAuth2 principal hoặc một kiểu riêng. Ép mọi principal thành domain `User` có thể gây lỗi kiểu. Hãy viết adapter cho đúng cơ chế xác thực đang sử dụng.

## 5. Ví dụ đầy đủ: auditor là String từ principal riêng

Các ví dụ dùng Java 17 và các phiên bản Spring Data, Spring Security tương thích. Mỗi lớp hoặc record `public` được đặt ở tệp Java riêng khi thực hành.

### 5.1. Principal của ứng dụng

```java
import org.springframework.security.core.AuthenticatedPrincipal;

public record AppPrincipal(String userId) implements AuthenticatedPrincipal {

    public AppPrincipal {
        if (userId == null || userId.isBlank()) {
            throw new IllegalArgumentException("userId bắt buộc");
        }
    }

    @Override
    public String getName() {
        return userId;
    }
}
```

`AuthenticatedPrincipal` cho phép ứng dụng công bố một principal riêng qua giao diện chung. [API AuthenticatedPrincipal](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/AuthenticatedPrincipal.html).

Việc `new AppPrincipal(...)` không tự xác thực một người dùng. Trong ứng dụng thực, lớp xác thực phải tạo hoặc ánh xạ principal sau khi kiểm tra danh tính. Không tạo principal từ ID tùy ý do request gửi lên rồi coi đó là bằng chứng người gọi sở hữu ID ấy.

### 5.2. Adapter từ Authentication sang audit ID

```java
import java.util.Optional;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;

public final class AuditorIds {
    private static final AuthenticationTrustResolver TRUST_RESOLVER =
            new AuthenticationTrustResolverImpl();

    private AuditorIds() {
    }

    public static Optional<String> from(Authentication authentication) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || TRUST_RESOLVER.isAnonymous(authentication)) {
            return Optional.empty();
        }

        if (!(authentication.getPrincipal() instanceof AppPrincipal principal)) {
            return Optional.empty();
        }

        return Optional.of("user:" + principal.userId());
    }
}
```

Ví dụ chỉ chấp nhận `AppPrincipal`. Nếu ứng dụng đang dùng JWT hoặc OAuth2 principal, cần thay phần ánh xạ bằng logic lấy subject và issuer theo hợp đồng của hệ thống; không thêm một phép cast không kiểm tra.

Adapter không tự tìm người dùng trong repository và không gọi dịch vụ từ xa. Khi ID đã có trong principal được xác thực, lấy trực tiếp giúp việc auditing ít phụ thuộc hơn vào các thao tác I/O khác.

`AuthenticationTrustResolverImpl` nhận diện anonymous dựa trên loại authentication tương ứng. Nếu ứng dụng dùng cơ chế riêng, phải kiểm tra cách nhận diện của cấu hình đó. [API AuthenticationTrustResolverImpl](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/authentication/AuthenticationTrustResolverImpl.html).

### 5.3. Provider đồng bộ

```java
import java.util.Optional;
import org.springframework.data.domain.AuditorAware;
import org.springframework.security.core.context.SecurityContextHolder;

public final class SecurityAuditorAware implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        return AuditorIds.from(SecurityContextHolder.getContext()
                .getAuthentication());
    }
}
```

Provider không giữ user ID trong field dùng chung. Hai request khác nhau sẽ được giải quyết dựa trên authentication hiện hành của mỗi lần gọi theo cơ chế quản lý context của ứng dụng.

Chính sách của ví dụ là trả `Optional.empty()` nếu không xác định được actor phù hợp. Đây là một lựa chọn cần được ứng dụng đánh giá, không phải cam kết rằng mọi thao tác ghi khi thiếu actor phải được chấp nhận.

## 6. Nối provider với auditing của MongoDB

### 6.1. Bật hạ tầng và chỉ rõ bean được chọn

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.mongodb.config.EnableMongoAuditing;

@Configuration(proxyBeanMethods = false)
@EnableMongoAuditing(
        auditorAwareRef = "securityAuditor",
        modifyOnCreate = true)
public class MongoAuditConfiguration {

    @Bean
    AuditorAware<String> securityAuditor() {
        return new SecurityAuditorAware();
    }
}
```

Ví dụ dành cho ứng dụng đã cấu hình Spring Data MongoDB đồng bộ. Cấu hình này đăng ký auditing, không thay thế kết nối database, mapping hoặc cơ chế xác thực.

Khi có nhiều implementation auditor, `auditorAwareRef` chỉ rõ bean được dùng thay vì trông chờ lựa chọn ngầm. MongoDB có cấu hình đồng bộ và reactive riêng. [Spring Data MongoDB: Auditing](https://docs.spring.io/spring-data/mongodb/reference/mongodb/auditing.html).

Không đăng ký thêm một instance cùng chức năng bằng cả `@Component` và `@Bean` nếu không có chủ đích. Trong ví dụ, `SecurityAuditorAware` không có `@Component`; cấu hình Java là nơi đăng ký duy nhất.

### 6.2. Entity có các audit fields phù hợp

```java
import java.time.Instant;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("notes")
public record Note(
        @Id String id,
        String content,
        @CreatedBy String createdBy,
        @LastModifiedBy String lastModifiedBy,
        @CreatedDate Instant createdAt,
        @LastModifiedDate Instant modifiedAt,
        @Version Long version) {

    public Note withContent(String nextContent) {
        return new Note(id, nextContent, createdBy, lastModifiedBy,
                createdAt, modifiedAt, version);
    }
}
```

`@CreatedBy` đánh dấu property đại diện người tạo entity; `@LastModifiedBy` đánh dấu người sửa gần nhất. [API CreatedBy](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/CreatedBy.html), [API LastModifiedBy](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/LastModifiedBy.html).

Các trường actor dùng `String`, khớp với `AuditorAware<String>`. Hai trường thời gian dùng `Instant` và có nguồn thời gian riêng của auditing.

```java
import org.springframework.data.repository.CrudRepository;

public interface NoteRepository extends CrudRepository<Note, String> {
}
```

Một lần tạo và một lần cập nhật về mặt sử dụng repository:

```java
Note saved = repository.save(
        new Note(null, "Bản nháp", null, null, null, null, null));

Note updated = repository.save(saved.withContent("Nội dung đã sửa"));
```

Đoạn này giả định repository và security context đã được ứng dụng cung cấp. Nó không tự đổi danh tính giữa hai lần lưu.

Với auditing hoạt động đúng, actor `user:u-42` ở lần tạo có thể được ghi vào cả `createdBy` và `lastModifiedBy` khi `modifyOnCreate=true`. Nếu một lần cập nhật sau thực hiện bởi `user:u-73`, kỳ vọng người tạo vẫn là `user:u-42`, còn người sửa gần nhất là `user:u-73`.

Phải giữ entity trả về từ `save`, đặc biệt với record hoặc kiểu bất biến. Bỏ qua kết quả có thể làm mất ID, version hoặc metadata đã được hạ tầng điền khi tiếp tục xử lý.

### 6.3. Nhận biết entity mới và modifyOnCreate

`modifyOnCreate` quyết định có đánh dấu entity là đã sửa ngay lúc tạo hay không; cấu hình MongoDB cho phép đặt rõ thuộc tính này. [API EnableMongoAuditing](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/config/EnableMongoAuditing.html).

Việc chọn nhánh tạo hay sửa còn phụ thuộc cơ chế nhận biết entity mới của module. Nếu ứng dụng gán ID trước hoặc tùy biến trạng thái mới, cần kiểm tra cơ chế ấy. Không suy từ `createdBy` đang null rằng hạ tầng chắc chắn coi entity là mới.

Khi tạo instance mới để cập nhật, phải giữ audit fields không thuộc trách nhiệm thay đổi của ứng dụng. Dựng lại entity từ một DTO chỉ có ID và content, rồi để mọi trường audit cũ thành null, có thể làm mất thông tin trước đó tùy đường mapping và ghi.

## 7. Optional.empty() có nghĩa gì trong auditing?

`Optional.empty()` nói rằng provider không cung cấp một auditor hiện hành. Nó không có nghĩa “người dùng anonymous đã được phép sửa”, “hãy xóa actor cũ” hoặc “hãy tự chọn tài khoản hệ thống”.

Trong implementation auditing handler được dẫn, khi không có auditor, bước điền người thao tác được bỏ qua; phần xử lý ngày giờ có thể vẫn chạy độc lập. Nó không chủ động gán null để xóa các audit fields về người thao tác. [Mã nguồn AuditingHandlerSupport](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/auditing/AuditingHandlerSupport.java).

Điều này có một hệ quả thực tế: nếu `lastModifiedBy` cũ vẫn còn trên entity và một lần sửa không có auditor, ngày sửa có thể thay đổi trong khi người sửa vẫn giữ giá trị trước đó. Giá trị ấy không chứng minh người cũ vừa thực hiện lần sửa mới.

Ứng dụng cần chọn chính sách rõ:

| Trường hợp | Chính sách có thể chọn |
| --- | --- |
| Dữ liệu cho phép không biết người thao tác | Cho phép thiếu auditor và mô tả giới hạn metadata |
| Thao tác nghiệp vụ bắt buộc có actor | Từ chối trước khi ghi hoặc dùng provider có chính sách bắt buộc |
| Job hệ thống đã được định danh | Cung cấp actor hệ thống rõ ràng trong ngữ cảnh job |
| Principal không đúng kiểu kỳ vọng | Xem là không giải quyết được actor; chẩn đoán cấu hình thay vì giả một ID |

Nếu chọn provider bắt buộc, có thể bọc nguồn auditor như sau trong cấu hình thay thế:

```java
AuditorAware<String> requiredAuditor = () -> Optional.of(
        new SecurityAuditorAware().getCurrentAuditor()
                .orElseThrow(() -> new IllegalStateException(
                        "Thiếu người thao tác cho luồng ghi bắt buộc")));
```

Đây là lựa chọn chính sách thay cho provider tùy chọn, không phải chỉ dẫn đăng ký cả hai bean rồi để hạ tầng tự chọn. Trong mã ứng dụng, có thể truyền delegate đã tạo vào wrapper thay vì tạo mới trong mỗi lần gọi.

Ném lỗi không thay thế cấu hình transaction. Nếu yêu cầu thao tác lớn phải rollback toàn bộ, cần kiểm tra ranh giới transaction và khả năng store của luồng ghi đó.

## 8. Người dùng, job và xử lý bất đồng bộ

### 8.1. Không lấy auditor từ audit field do client gửi

Một request có `createdBy="admin"` không phải nguồn bằng chứng về danh tính. DTO cập nhật nên chứa dữ liệu nghiệp vụ được phép thay đổi; actor được giải quyết từ ngữ cảnh đã được ứng dụng xác minh.

Không dùng ID đường dẫn, owner của entity hoặc người được gán công việc làm auditor chỉ vì các ID đó đang sẵn trong request. Người sở hữu dữ liệu và người thực hiện lần sửa là hai vai trò khác nhau.

### 8.2. Job nền cần actor tường minh

Một tác vụ định kỳ thường không có security context của request. Có thể dùng danh tính service hoặc job như `system:catalog-import`, nhưng chỉ trong luồng đã được thiết kế như vậy.

Không dùng `orElse("system")` ở mọi nơi để làm audit fields luôn có dữ liệu. Cách đó có thể che lỗi mất context của người dùng bằng cách biến mọi trường hợp không xác định thành một hành động hệ thống.

Trong một ứng dụng phục vụ cả HTTP và job, cần một chính sách nguồn actor thống nhất: ai được đặt actor của job, phạm vi tồn tại của nó, và cách kết thúc phạm vi ấy. Không giữ actor trong biến static mutable hoặc một field singleton rồi sửa trước mỗi job.

### 8.3. @Async và thread pool

Khi công việc chuyển sang thread khác, security context theo thread không mặc nhiên đi cùng. Spring Security có các abstraction như `DelegatingSecurityContextRunnable` và executor tương ứng để truyền context rồi dọn dẹp sau khi thực thi. [Spring Security: Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html).

Auditor cần phản ánh danh tính tại thời điểm auditing thực sự chạy. Với một job xếp hàng lâu, phải quyết định ghi người yêu cầu, service thực thi hay cả hai ở các metadata khác nhau.

Không chỉ đổi sang biến toàn cục hoặc mặc nhiên dựa vào kế thừa ThreadLocal để xử lý mọi thread pool. Context tồn dư của một tác vụ trên thread tái sử dụng có thể gắn nhầm actor cho tác vụ sau nếu vòng đời không được quản lý đúng.

## 9. ReactiveAuditorAware cho luồng reactive

`ReactiveAuditorAware<T>` trả `Mono<T>`; publisher rỗng biểu diễn trường hợp không biết auditor. Nó là SPI riêng, không phải `AuditorAware<Mono<T>>`. [API ReactiveAuditorAware](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/ReactiveAuditorAware.html).

Có thể dùng lại adapter `AuditorIds` nhưng đọc security context từ Reactor Context:

```java
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public final class ReactiveSecurityAuditorAware
        implements ReactiveAuditorAware<String> {

    @Override
    public Mono<String> getCurrentAuditor() {
        return ReactiveSecurityContextHolder.getContext()
                .flatMap(context -> Mono.justOrEmpty(
                        AuditorIds.from(context.getAuthentication())));
    }
}
```

`ReactiveSecurityContextHolder.getContext()` lấy security context từ Reactor Context. [API ReactiveSecurityContextHolder](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html).

Trong ứng dụng MongoDB reactive, đăng ký provider bằng cấu hình reactive tương ứng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.data.mongodb.config.EnableReactiveMongoAuditing;

@Configuration(proxyBeanMethods = false)
@EnableReactiveMongoAuditing(auditorAwareRef = "reactiveSecurityAuditor")
public class ReactiveMongoAuditConfiguration {

    @Bean
    ReactiveAuditorAware<String> reactiveSecurityAuditor() {
        return new ReactiveSecurityAuditorAware();
    }
}
```

Đây là cấu hình thay thế cho luồng reactive, không tự biến repository đồng bộ thành reactive. Không gọi `block()` để lấy auditor đồng bộ từ publisher trong lúc auditing reactive; giữ việc giải quyết danh tính trong pipeline đang thực thi.

Nếu muốn bắt buộc có actor ở provider reactive, chính sách có thể dùng `switchIfEmpty(Mono.error(...))`. Cần kiểm thử lỗi khi publisher được thực thi; chỉ tạo publisher chưa chứng minh provider đã được gọi.

## 10. Những giới hạn của audit fields về người thao tác

### 10.1. Không phải lịch sử thay đổi đầy đủ

`createdBy` và `lastModifiedBy` giữ thông tin đầu và gần nhất theo hợp đồng auditing. Nếu ba người cùng sửa qua ba thời điểm, một field người sửa cuối không lưu toàn bộ chuỗi sự kiện.

Nếu cần biết từng lần đổi trạng thái, giá trị trước/sau, người yêu cầu hoặc correlation ID, cần một thiết kế lịch sử riêng. Không coi hai annotation là cơ chế tự tạo mọi bản ghi lịch sử.

### 10.2. Không tự áp dụng cho mọi đường ghi

Raw driver, SQL trực tiếp hoặc update definition không mặc nhiên đi qua cùng checkpoint với lưu entity. Ví dụ, tài liệu Spring Data JDBC nêu modifying queries không gọi callback hoặc event; audit fields cần được cập nhật trong query nếu muốn thay đổi chúng. [Spring Data JDBC: Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html).

Không sửa `AuditorAware` mãi khi đường update chưa từng gọi auditing infrastructure. Trước hết xác định API ghi, module và checkpoint thực tế.

### 10.3. Cấu hình theo module

`AuditorAware` thuộc Commons, nhưng enablement thuộc module. MongoDB dùng cấu hình Mongo auditing; JPA cần auditing cùng cơ chế listener phù hợp của JPA; các module khác có hướng dẫn riêng. [Spring Data JPA: Auditing](https://docs.spring.io/spring-data/jpa/reference/auditing.html).

Không sao chép `@EnableMongoAuditing` vào ứng dụng chỉ dùng JPA rồi mong provider sẽ tự được gọi. Cũng không mặc định kiểu auditor là domain `User` thì mọi store đều lưu được quan hệ ấy theo cùng cách.

## 11. Kiểm thử nguồn auditor và dữ liệu được ghi

### 11.1. Kiểm thử provider trong bộ nhớ

Bộ tình huống tối thiểu:

| Authentication | Kết quả của adapter trong bài |
| --- | --- |
| Không có authentication | `Optional.empty()` |
| Token chưa xác thực | `Optional.empty()` |
| Anonymous authentication | `Optional.empty()` |
| Token đã xác thực với `AppPrincipal("u-42")` | `Optional.of("user:u-42")` |
| Token đã xác thực nhưng principal khác kiểu | `Optional.empty()` theo chính sách hiện tại |

Một test JUnit Jupiter minh họa provider đồng bộ:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

public class SecurityAuditorAwareTest {
    private final SecurityAuditorAware auditor = new SecurityAuditorAware();

    @AfterEach
    void clearContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void usesStableIdFromAuthenticatedPrincipal() {
        var authentication = new UsernamePasswordAuthenticationToken(
                new AppPrincipal("u-42"), null,
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
        var context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);

        assertEquals(Optional.of("user:u-42"), auditor.getCurrentAuditor());
    }

    @Test
    void anonymousDoesNotBecomeAUserAuditor() {
        var authentication = new AnonymousAuthenticationToken(
                "test-key", "anonymousUser",
                List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS")));
        var context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);

        assertEquals(Optional.empty(), auditor.getCurrentAuditor());
    }

    @Test
    void missingAuthenticationHasNoAuditor() {
        SecurityContextHolder.clearContext();

        assertEquals(Optional.empty(), auditor.getCurrentAuditor());
    }
}
```

Các token được tạo trực tiếp trong test để giả lập ngữ cảnh. Đây không phải hướng dẫn cho endpoint tự gán một authentication đã xác thực từ dữ liệu người dùng chưa được kiểm tra.

Mỗi test thay bằng context mới và dọn context sau khi chạy để tránh danh tính của test trước ảnh hưởng test sau. Những đoạn kiểm thử trong bài là ví dụ để thực hành, không phải báo cáo đã chạy trong môi trường dự án.

### 11.2. Kiểm thử tích hợp với store

Test provider đúng chưa chứng minh auditing được bật. Trong ứng dụng demo đã có store, cần:

1. Tạo entity mới với actor `user:u-42`, lưu và đọc lại để kiểm tra người tạo và người sửa theo cấu hình `modifyOnCreate`.
2. Cập nhật entity bằng actor `user:u-73`, xác nhận người tạo được bảo toàn và người sửa thay đổi.
3. Thử thiếu actor theo chính sách đã chọn: provider tùy chọn hay provider bắt buộc.
4. Đặt đúng hai auditor bean trong cấu hình thử nghiệm, dùng `auditorAwareRef` để xác nhận bean được lựa chọn.
5. Thực hiện tác vụ nền và kiểm tra actor hệ thống không bị dùng nhầm cho request người dùng.
6. Với luồng reactive hoặc async, kiểm tra dữ liệu sau thực thi trong đúng ngữ cảnh thay vì chỉ gọi provider ngoài pipeline.

Nếu audit fields không đúng, kiểm tra lần lượt annotation, kiểu field, bean được chọn, enablement của store, trạng thái mới của entity, thời điểm chạy và API ghi. Không chỉ nhìn vào việc có tồn tại một bean `AuditorAware` trong container.

## 12. Các quyết định cần giữ nhất quán

| Quyết định | Ví dụ của bài |
| --- | --- |
| Kiểu lưu actor | `String` |
| ID người dùng | ID ổn định từ `AppPrincipal` đã được xác thực |
| Định dạng | `user:<id>` và actor hệ thống được quy định riêng |
| Anonymous | Không được coi là user auditor |
| Principal ngoài hợp đồng | Không tự ép kiểu hoặc đoán ID |
| Không xác định được auditor | Trả rỗng hoặc từ chối theo chính sách luồng ghi |
| Job | Actor hệ thống tường minh, đúng phạm vi job |
| Nhiều provider | Chọn rõ bằng cấu hình module |
| Reactive | `ReactiveAuditorAware` và Reactor Context |
| Lịch sử nhiều lần thay đổi | Thiết kế riêng ngoài cặp audit fields đầu/cuối |

Khi giải thích một giá trị `createdBy` hoặc `lastModifiedBy`, cần chỉ ra được nguồn danh tính, quy tắc ánh xạ, kiểu được lưu và đường ghi đã gọi auditing. Đó là cơ sở để `AuditorAware` cung cấp thông tin người thao tác có ý nghĩa trong hạ tầng Spring Data.
