# Gọi bean chính sách từ biểu thức bằng @beanName trong Spring Security

Trong Spring Security **method security**, `@PreAuthorize` thường bắt đầu bằng một điều kiện ngắn như `hasRole('ADMIN')` hoặc `hasAuthority('DOCUMENT_READ')`. Nhưng nghiệp vụ thực tế thường phức tạp hơn: người dùng chỉ được đọc tài liệu **thuộc tenant hiện hành**, đơn hàng chưa khóa, có quan hệ sở hữu hoặc được chia sẻ, và quyền của họ **chưa bị thu hồi**. Viết toàn bộ logic đó trong một chuỗi SpEL dài sẽ khó kiểm thử, khó tái sử dụng và dễ dựa vào dữ liệu client không đáng tin.

Spring Security cho phép **gọi một Spring bean trực tiếp trong biểu thức bảo mật**:

~~~java
@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
public DocumentView read(long documentId) { /* ... */ }
~~~

Trong chuỗi SpEL này, **`@documentPolicy` là phép tham chiếu đến bean có tên `documentPolicy` trong Spring ApplicationContext**, **`.canRead(...)` là phương thức Java của bean**, còn `authentication` và `#documentId` là những giá trị Spring Security đưa vào môi trường đánh giá biểu thức. Nếu policy trả `true`, method được phép chạy; nếu trả `false`, pre-authorization từ chối trước khi thân method thực thi.

Bài học này thuộc nhóm **Kiểm tra trước phương thức**, sử dụng **Spring Boot 3 / Spring Security 6.x, Java 17+ và Servlet stack** để giải thích cơ chế `@beanName`, cách định nghĩa policy bean, lấy đúng principal/tham số, thiết kế policy fail-closed, xử lý nhiều tenant, thứ tự kiểm tra và kiểm thử. Các snippet Spring cần dependency và bean ứng dụng thật; cuối bài có một chương trình Java 17 độc lập để chứng minh logic chính sách và việc chặn trước body.

## 1. Cú pháp `@beanName` trong SpEL là gì?

Spring Expression Language (**SpEL**) hỗ trợ **bean reference** bằng ký hiệu `@` theo sau là tên bean. Trong `@PreAuthorize`, thường gặp:

~~~java
@PreAuthorize("@documentPolicy.canRead(authentication, #id)")
@PreAuthorize("hasAuthority('DOC_READ') and @documentPolicy.canRead(authentication, #id)")
@PreAuthorize("@approvalPolicy.mayApprove(authentication, #orderId)")
@PreAuthorize("@tenantPolicy.canAccess(authentication, #tenantId)")
~~~

Đây là **bốn ví dụ annotation riêng biệt**, không chồng bốn `@PreAuthorize` trên cùng method. `@beanName` không phải một Java annotation mới; nó nằm **bên trong chuỗi SpEL** được `MethodSecurityExpressionHandler` đánh giá. Dấu `@` ở đây là cú pháp tra bean, **khác** với dấu `@` mở đầu Java annotation `@Component` hoặc `@PreAuthorize`.

Tách biểu thức:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `@documentPolicy` | Bean tên `documentPolicy` được tìm từ ApplicationContext. | `@Component("documentPolicy")` hoặc `@Bean("documentPolicy")`. |
| `.canRead(...)` | Gọi public method phù hợp trên bean. | `boolean canRead(Authentication, long)`. |
| `authentication` | Biến/root property của ngữ cảnh Spring Security. | User principal và authorities. |
| `#id` | Biến **tham số method** được resolve theo tên. | `read(long id)`. |
| `#root` | Root object biểu thức method security. | Dùng với `@authz.decide(#root)` theo tài liệu chính thức. |
| `and` | Logic boolean SpEL; vế phải không cần đánh giá nếu vế trái false. | Giảm gọi DB policy khi thiếu authority. |
| `true`/`false` | Kết quả chấp nhận/từ chối của policy kiểu boolean. | `true` cho chạy; `false` deny. |

Ví dụ `@documentPolicy.canRead(authentication, #id)` **không tự gọi** `canRead` trên chính service có annotation, và **không tự gọi HTTP controller**. Spring lấy bean có tên tương ứng từ context rồi gọi method Java của bean. Bean policy cũng có thể được dùng từ những service khác hoặc test trực tiếp như mọi class Java thông thường.

Lợi ích của `@beanName`: biến quyết định phức tạp thành **phương thức Java có tên nghiệp vụ**, dễ unit test, có dependency injection tới repository/permission service, dễ log và giữ biểu thức ngắn. Đây cũng là một hướng được tài liệu Spring Security khuyến nghị thay cho việc subclass một custom expression root chỉ để thêm vài phép kiểm tra quyền.

## 2. Đường đi của một lời gọi trước khi thân method chạy

Phải hiểu chính xác **thời điểm** đánh giá để dùng policy đúng mục tiêu:

~~~text
HTTP controller / scheduler / listener / bean khác
    |
    v
Gọi Spring-managed service qua AOP proxy
    |
    v
AuthorizationManagerBeforeMethodInterceptor
  (kiểm tra @PreAuthorize)
    |
    +-- SpEL: hasAuthority('DOC_READ')
    |        AND
    |        @documentPolicy.canRead(authentication, #id)
    |                     |
    |                     +-- bean từ ApplicationContext
    |                     +-- kiểm tra owner/tenant/status từ DB
    |
    +-- FALSE -> AccessDeniedException
    |            METHOD BODY CHƯA CHẠY
    |
    +-- TRUE  -> vào service method body
                    |
                    v
             DB/query hoặc mutation
~~~

Với `@EnableMethodSecurity`, Spring Security đăng ký interceptor cho `@PreAuthorize`. Interceptor cung cấp ngữ cảnh biểu thức, đánh giá điều kiện **trước lời gọi method**, và không đi vào body nếu quyết định từ chối. Một policy bean có thể thực hiện query để quyết định, nhưng việc query đó thuộc **giai đoạn authorization**, không phải method body đang được bảo vệ.

Nếu policy `canRead` trả false, method không chạy. Nếu bean không tồn tại, biểu thức sai cú pháp, không tìm được tên tham số hoặc policy ném exception, **không đồng nghĩa một phép từ chối quyền sạch**: runtime có thể gặp lỗi SpEL/bean/service và trả 5xx hoặc được exception handler chuyển đổi theo thiết kế. Vì vậy cần test cả **false hợp lệ** và **lỗi kỹ thuật**; tránh dùng catch-all trả true khi database lỗi.

**Chỉ gọi qua Spring AOP proxy mới có method-security check.** `new DocumentService(...)` hoặc gọi `this.read(...)` trong cùng bean có thể bypass interceptor theo chế độ proxy mặc định. Đừng kết luận an toàn chỉ vì source code có `@PreAuthorize`.

## 3. Cấu hình đầy đủ tối thiểu: bật method security

Bật trong một class cấu hình của Spring Boot:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Spring Boot Starter Security **không tự bật method security**. Với Spring Security 6.x, `@EnableMethodSecurity` bật `@PreAuthorize` theo mặc định (trừ khi cấu hình tắt pre/post). HTTP SecurityFilterChain và method security là hai ranh giới khác nhau. Có thể có API qua HTTP yêu cầu `authenticated()`, nhưng ngay cả sau khi vượt HTTP filter, service vẫn từ chối vì `@PreAuthorize` không thỏa domain policy.

Ví dụ dependencies Gradle Groovy:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây **chỉ là phần dependencies**, không phải `build.gradle` hoàn chỉnh; dùng phiên bản Spring Security do Spring Boot BOM quản lý. Không dùng `WebSecurityConfigurerAdapter` hoặc `@EnableGlobalMethodSecurity` của thế hệ cũ để bắt đầu dự án Boot 3 mới.

Ví dụ cấu hình request-level để thấy hai lớp:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/documents/**").authenticated()
        .anyRequest().denyAll()
    );
    return http.build();
}
~~~

Đây là **trích đoạn bean Spring**, cần imports, authentication config và URL controller thực. `.authenticated()` chỉ yêu cầu caller xác thực ở HTTP; việc caller có quyền trên **Document 10** vẫn được policy bean ở method kiểm tra. Cũng có thể đặt authority chung tại HTTP như `hasAuthority('DOC_READ')`, nhưng bảo vệ service sẽ vẫn cần nếu có entry point không qua HTTP.

## 4. Khai báo một bean chính sách tên rõ ràng

Có hai cách đặt tên bean thông dụng.

### Cách A: @Component với tên tường minh

~~~java
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    public boolean canRead(/* Authentication auth, long id */) {
        // Thực hiện kiểm tra an toàn bằng Java.
        return false;
    }
}
~~~

Đây là **minh họa cách khai báo tên**, chữ ký chứa comment để tránh gắn vào business code. Trong implementation thực tế phải có đủ tham số và logic. `@Component("documentPolicy")` giúp tên bean không phụ thuộc việc class tên `DocumentPolicy` có đổi hay không.

### Cách B: @Bean với tên tường minh

~~~java
@Configuration
class PolicyBeans {

    @Bean("documentPolicy")
    DocumentPolicy documentPolicy(DocumentRepository repository) {
        return new DocumentPolicy(repository);
    }
}
~~~

Đây là **phương án thay thế**, không tạo đồng thời với `@Component("documentPolicy")` trong cùng context nếu không có chủ đích và quy tắc override. Khi dùng cách B, constructor `DocumentPolicy(DocumentRepository)` và các dependencies phải được định nghĩa phù hợp. Cả hai cách tạo bean đều cho phép biểu thức `@documentPolicy.canRead(...)`.

Nếu chỉ ghi `@Component` (không tên), Spring thường suy tên bean từ tên class theo quy tắc decapitalize, ví dụ `documentPolicy`. Nhưng không nên dựa vào suy luận khi refactor, đặc biệt với acronym, nested bean, custom bean naming strategy hoặc nhiều context. Với security expression, **đặt tên tường minh dễ bảo trì hơn**.

Tên bean là **case-sensitive trong thực hành tham chiếu**. `@DocumentPolicy`, `@documentpolicy`, `@documentPolicy` không nên coi là cùng một bean. Nếu bean nằm ngoài phạm vi component scan hoặc thuộc context khác, SpEL không tìm được nó. Lỗi này không phải chuyện “admin thiếu role”, mà là lỗi cấu hình bean.

## 5. Ví dụ policy bean đọc dữ liệu server và kiểm tra đa tenant

Xét ứng dụng có những tài liệu thuộc các cửa hàng khác nhau. Người gọi có thể đọc document nếu **đã xác thực**, có `DOC_READ`, document tồn tại, người đó là **thành viên còn hiệu lực của tenant**, và là **owner hoặc có quyền đọc nhóm**. Thiết kế như vậy cho thấy tại sao chỉ xét role là không đủ.

Một cách biểu diễn trong Spring Boot:

~~~java
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    private final DocumentRepository documents;
    private final TenantMembershipService memberships;

    public DocumentPolicy(DocumentRepository documents,
                          TenantMembershipService memberships) {
        this.documents = documents;
        this.memberships = memberships;
    }

    public boolean canRead(Authentication authentication, long documentId) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        boolean hasRead = authentication.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("DOC_READ"));
        if (!hasRead) {
            return false;
        }

        Document doc = documents.findById(documentId).orElse(null);
        if (doc == null) {
            return false;
        }

        String actor = authentication.getName();
        boolean tenantAllowed =
            memberships.isActiveMember(actor, doc.getTenantId());
        if (!tenantAllowed) {
            return false;
        }

        boolean owner = actor.equals(doc.getOwnerUsername());
        boolean teamRead = authentication.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("DOC_READ_TEAM"));
        return owner || teamRead;
    }
}
~~~

Đây là **mã trong ứng dụng Spring có dependencies do project cung cấp**: `DocumentRepository`, `TenantMembershipService`, `Document` với `getTenantId()`/`getOwnerUsername()` và cách xác thực tên principal cần tồn tại thật. `DocumentRepository.findById` trả `Optional<Document>` theo hợp đồng minh họa. Chưa có lớp thực thi repository/database nên không thể chạy độc lập bằng JDK.

**Các điểm bảo mật cố ý:**

1. `authentication == null` và anonymous → **false**; không tự giả định caller là admin hoặc “hệ thống”.
2. Thiếu `DOC_READ` → **false**, trước khi cần query record.
3. Record không tồn tại → **false**, không trả chi tiết owner/tenant cho người không có quyền.
4. Membership tenant được tra từ **server-side verified source**, không tin mỗi header `X-Tenant-Id` do client tự gửi.
5. Owner hoặc team permission chỉ được dùng **sau** khi xác minh tenant. Có `DOC_READ_TEAM` ở tenant A không có nghĩa được đọc tài liệu tenant B.
6. Policy trả **boolean**, không thay đổi dữ liệu, không gửi email, không ghi nghiệp vụ; phù hợp giai đoạn authorization trước method.

Nếu muốn thiết kế chặt hơn, có thể kiểm tra tài liệu không ở trạng thái deleted/archived, quyền chia sẻ theo thời hạn hoặc phạm vi cụ thể. Không cho rằng `isAuthenticated()` một mình chứng minh người dùng đã được cấp quyền trên dữ liệu.

## 6. Sử dụng bean policy tại @PreAuthorize

Một service nhỏ có thể viết:

~~~java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize("@documentPolicy.canRead(authentication, #id)")
    public DocumentView read(@P("id") long documentId) {
        return documents.loadViewById(documentId);
    }
}
~~~

Đây là **mã Spring phụ thuộc `DocumentRepository` và `DocumentView` do project định nghĩa**. Chú ý `@P("id")` dùng để ánh xạ tên SpEL `#id` tới tham số Java `documentId`. Trong project cấu hình build `-parameters`, có thể dùng thẳng `#documentId` nếu tên tham số được giữ lại; ở đây `@P` cho thấy cách đặt tên tường minh.

Diễn giải:

~~~text
caller -> DocumentService Spring proxy
  |
  v
@PreAuthorize expression
  @documentPolicy.canRead(authentication, #id)
  |
  +-- bean được tìm đúng tên "documentPolicy"
  +-- #id = documentId của invocation
  +-- authentication = principal/authorities của caller
  +-- trả false? -> DENY; không gọi read(...)
  +-- trả true?  -> gọi read(...)
                     |
                     v
                documents.loadViewById(documentId)
~~~

Nếu một người chỉ có `DOC_READ` và là owner trong tenant được phép → policy true, service được gọi. Nếu người đó thiếu quyền, dùng document ID của người khác hoặc tenant khác → false, body không chạy.

Một biến thể biểu thức ngắn và tận dụng **short-circuit**:

~~~java
@PreAuthorize(
    "hasAuthority('DOC_READ') and @documentPolicy.canRead(authentication, #id)")
public DocumentView read(@P("id") long documentId) {
    return documents.loadViewById(documentId);
}
~~~

Nếu không có `DOC_READ`, vế trái false và SpEL **không cần gọi** `@documentPolicy.canRead` để tra DB. Trong code policy ở mục trước vẫn nên kiểm tra authority: có thể có caller khác dùng bean trực tiếp, hoặc một rule khác gọi policy mà không có vế `hasAuthority`. Đừng dựa hoàn toàn vào cấu trúc biểu thức tại một method để bảo đảm policy luôn đúng ở mọi nơi.

### Tên tham số: #id khác @documentPolicy

- `@documentPolicy`: tra **bean Spring** theo tên.
- `#id`: tra **biến trong evaluation context**, ở đây là method argument.
- `authentication`: property/biến có sẵn do expression root cung cấp.
- `#root`: root object, thường dùng khi policy muốn xem nhiều thông tin method security cùng lúc.

Một lỗi phổ biến là viết `@documentPolicy.canRead(authentication, @id)`. Dấu `@id` nghĩa là tìm bean tên `id`, **không phải đọc tham số `id`**. Tương tự, viết `#documentPolicy.canRead(...)` không tìm Spring bean theo cơ chế trên; nó đòi một **variable** tên `documentPolicy` trong evaluation context, thường không tồn tại.

## 7. Passing Authentication: cái gì đáng tin, cái gì không?

Trong method security expression, `authentication` được cung cấp từ ngữ cảnh Spring Security hiện tại, gắn với execution/thread và security setup. Nó hữu ích để tránh policy bean tự gọi `SecurityContextHolder.getContext()` khắp nơi.

Ưu điểm của chữ ký:

~~~java
public boolean canRead(Authentication authentication, long documentId)
~~~

là **input thể hiện rõ** danh tính và tài nguyên đang kiểm tra, giúp unit test bằng mock/stub Authentication, giảm coupling tới thread-local trong domain policy. Tuy nhiên policy không nên trả true chỉ vì `authentication != null` hoặc `authentication.getName()` giống một chuỗi nào đó. Phải kiểm tra permission, membership, trạng thái và dữ liệu server.

`Authentication.getPrincipal()` có thể là `UserDetails`, `Jwt`, `OAuth2User` hoặc custom principal tùy cơ chế. Đừng ép `(AppUser) authentication.getPrincipal()` nếu không chắc runtime type. Với JWT, cần converter biến claims thành authorities hợp lệ, và nguồn tenant đã được validate/chấp nhận. Nếu `authentication.getName()` là ID không tương ứng username trong DB, policy phải dùng **định danh ổn định** (subject/userId) thay vì so sai chuỗi username.

Trường hợp anonymous: Spring Security có thể đặt `AnonymousAuthenticationToken` trong context, nên `authentication` **không nhất thiết null** đối với request chưa đăng nhập. Đừng sử dụng duy nhất `authentication.isAuthenticated()` để bảo đảm đây là một người dùng thực. Có thể dùng policy helper phù hợp `AuthenticationTrustResolver` nếu logic cần phân biệt anonymous, hoặc kiểm tra kiểu token và authorities đúng theo authentication mechanism.

**Bảo vệ chống spoofing:** HTTP client có thể giả header `X-User-Id`, gửi body `ownerUserName` hoặc đổi `tenantId`. Những giá trị đó không thay thế `Authentication` đã được server xác thực và cơ sở dữ liệu quyền tenant. Chính sách dựa trên `#owner` do client truyền có thể bị lách nếu không so với bản ghi thực.

## 8. Gọi một policy bean qua #root: tình huống nâng cao

Ngoài truyền `Authentication` và tham số riêng, tài liệu chính thức Spring Security 6.5 trình bày cách truyền **method security expression root** tới một bean:

~~~java
import org.springframework.security.access.expression.method.MethodSecurityExpressionOperations;
import org.springframework.stereotype.Component;

@Component("authz")
public class AuthorizationLogic {

    public boolean decide(MethodSecurityExpressionOperations operations) {
        return operations.hasAuthority("DOC_READ");
    }
}
~~~

Trong service:

~~~java
@PreAuthorize("@authz.decide(#root)")
public DocumentView readDocument(long id) {
    return repository.loadViewById(id);
}
~~~

Hai đoạn này là **mã cần Spring context và repository ứng dụng**, không phải một file Java độc lập. `#root` ở đây là **`MethodSecurityExpressionOperations`**, cho phép policy dùng những helper của expression root (như `hasAuthority`) mà không phải tự đi qua danh sách `GrantedAuthority`. Spring Security cũng mô tả khả năng policy trả `AuthorizationDecision`/kết quả giàu thông tin ở những API hỗ trợ tương ứng; chi tiết signature phải khớp version thực tế.

Một biến thể vẫn cho phép dùng cả root và method argument nếu muốn:

~~~java
@PreAuthorize("@documentAuthorization.mayRead(#root, #id)")
public DocumentView read(@P("id") long documentId) {
    return repository.loadViewById(documentId);
}
~~~

`documentAuthorization` phải là **bean có public method đúng signature**, ví dụ nhận `MethodSecurityExpressionOperations` và `long`. Đây là một phương án khác với `DocumentPolicy.canRead(Authentication,long)`; không trộn signature giữa hai cách rồi mong SpEL tự chuyển kiểu.

**Chọn cách nào?**

| Cách truyền | Ưu điểm | Lưu ý |
| --- | --- | --- |
| `@policy.canRead(authentication, #id)` | Dễ unit test với Authentication; hiển thị tài nguyên rõ. | Policy cần tự xác minh authority/trust và dùng domain repository. |
| `@authz.decide(#root)` | Sử dụng API `MethodSecurityExpressionOperations` và helper method security. | Policy phụ thuộc Spring Security expression interface hơn, cần test method context. |
| `hasAuthority('...') and @policy.canRead(authentication, #id)` | Short-circuit quyền chung rồi mới query domain. | Policy vẫn nên fail closed khi gọi ở nơi khác. |
| `@policy.canRead(#id)` | Ngắn nhất nếu policy tự lấy actor từ context. | Phụ thuộc thread-local/bean context ẩn; test phức tạp hơn. |

Không nhất thiết phải viết custom `MethodSecurityExpressionHandler` hoặc subclass expression root chỉ để thêm một hàm `canRead`. **Gọi bean chính sách từ SpEL thường đủ**; chỉ custom handler khi có nhu cầu framework-level thực sự và đã đọc contract API cho version đang chạy.

### Boolean, null và abstain

Với bean policy trả `boolean`, hãy trả **`false` cho mọi trường hợp không đủ dữ liệu/không đủ quyền**. Trong các extension API cao hơn, tài liệu Spring Security 6.5 có mô tả policy trả `Boolean` nullable để biểu thị **abstain** và có thể dùng loại `AuthorizationDecision`/kết quả để nêu lý do. **Đừng dùng `null` như một mã lỗi tùy tiện** khi policy lẽ ra phải deny; abstain có semantics khác và phụ thuộc cách manager/interceptor tổng hợp. Với nghiệp vụ cần fail closed, trả boolean rõ và test đủ.

## 9. Tái sử dụng policy ở nhiều phương thức

Một bean chính sách đúng trách nhiệm có thể được gọi trong nhiều service methods:

~~~java
@PreAuthorize("@documentPolicy.canRead(authentication, #id)")
public DocumentView read(@P("id") long documentId) {
    return repository.loadViewById(documentId);
}

@PreAuthorize("@documentPolicy.canApprove(authentication, #id)")
public void approve(@P("id") long documentId) {
    documentWriter.approveAfterStateValidation(documentId);
}

@PreAuthorize("hasAuthority('DOC_DOWNLOAD') and @documentPolicy.canRead(authentication, #id)")
public byte[] download(@P("id") long documentId) {
    return documentExporter.generateFile(documentId);
}
~~~

Đây là **ba snippet method đặt trong Spring service**, cần policy bean cung cấp đúng cả `canRead` và `canApprove`, `documentWriter`, `documentExporter` và repository ứng dụng. Một policy tốt nên dùng tên rõ `canRead`, `canApprove`, `mayDelete`, không gom tất cả vào một boolean `isAllowed` không biết action.

Một thao tác `approve` có thể cần:

- Có `DOC_APPROVE`, đã đăng nhập.
- Document thuộc tenant mà actor đang là thành viên có hiệu lực.
- Document ở trạng thái `PENDING`.
- Theo quy tắc **four-eyes**, người duyệt không được là người tạo document.
- Hạn mức, thời gian, feature flags và các ràng buộc doanh nghiệp phù hợp.

**Không suy rằng** `canRead` true đồng nghĩa `canApprove` true. Quyền xem và quyền thay đổi trạng thái tài nguyên là hai hành động khác nhau, phải có kiểm tra riêng.

Đối với method `approve`, `@PreAuthorize` là **lớp chặn trước body**, nhưng dữ liệu có thể thay đổi giữa lúc policy query và transaction ghi. Method phải tái xác minh các bất biến gần update (optimistic version check hoặc conditional SQL); điều kiện trạng thái/tenant không thể chỉ tồn tại trong policy pre-check.

## 10. Ví dụ policy bean dành cho approve có domain state

Ví dụ mở rộng class policy ở mục 5:

~~~java
public boolean canApprove(Authentication authentication, long documentId) {
    if (authentication == null
            || !authentication.isAuthenticated()
            || authentication instanceof AnonymousAuthenticationToken) {
        return false;
    }
    boolean hasPermission = authentication.getAuthorities().stream()
        .anyMatch(a -> a.getAuthority().equals("DOC_APPROVE"));
    if (!hasPermission) {
        return false;
    }

    Document doc = documents.findById(documentId).orElse(null);
    if (doc == null || !"PENDING".equals(doc.getStatus())) {
        return false;
    }

    String actor = authentication.getName();
    return memberships.isActiveMember(actor, doc.getTenantId())
            && !actor.equals(doc.getOwnerUsername());
}
~~~

Đây là **method Java được thêm vào `DocumentPolicy` đã định nghĩa**, không phải class/file độc lập. Nó chỉ ra logic **fail-closed, role/permission, tenant, state và separation of duties**. Khi document không tồn tại hoặc quyền không đủ, **không lộ chi tiết** về tenant hay người tạo ra ngoài.

Để vận hành đáng tin, cấu hình transaction isolation/locking tương ứng. Ví dụ trạng thái document chuyển từ PENDING sang CLOSED ngay sau policy check thì `approveAfterStateValidation` phải từ chối update. Nếu hệ thống có hành động ngoài DB (email, webhook), áp dụng outbox/idempotency và chỉ gửi sau khi transaction thực sự thành công; chỉ gắn `@PreAuthorize` không đảm bảo mọi side effect được rollback.

## 11. Bean name, lifecycle và dependency injection: lỗi hay gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| SpEL báo không tìm thấy bean `documentPolicy` | Class không được component scan, sai tên bean, hoặc bean ở context khác. | Kiểm tra `@Component("documentPolicy")`/`@Bean("documentPolicy")`, package scan và application context. |
| Bean tồn tại nhưng không gọi được `canRead` | Method không public, signature/type không phù hợp, hoặc tên method sai. | Dùng public method có signature rõ và unit test. |
| `#documentId` là null dù caller truyền số | Spring không khám phá được tên tham số. | Bật `-parameters` hoặc dùng `@P("id")` và biểu thức `#id`. |
| Policy trả false cho mọi người | Authority prefix khác, tenant membership không đúng hoặc principal name mapping sai. | Kiểm tra dữ liệu auth thực, test owner/tenant/permissions. |
| Service được gọi dù policy trả false | Method security chưa bật hoặc lời gọi không qua proxy. | `@EnableMethodSecurity`, inject bean, test self invocation. |
| Lỗi 500 thay vì 403 | Bean exception, lỗi DB/SpEL/type conversion, không phải boolean deny bình thường. | Phân biệt lỗi kỹ thuật với quyết định quyền; fail closed, xử lý exception có kiểm soát. |
| Query policy rất chậm | DB query mỗi invocation, N+1, thiếu index/tenant filter. | Tối ưu repository, query existence, index và đo latency. |
| Một user được đọc dữ liệu của tenant khác | Tenant lấy từ header giả hoặc policy chỉ so role/owner. | Kiểm chứng membership server-side, đưa tenant vào DB predicate. |
| Policy test pass nhưng HTTP vẫn 403 | HTTP filter, CSRF, authentication entry point hoặc chain khác chặn trước method. | Kiểm thử HTTP và method riêng để xác định lớp lỗi. |

Nếu bean có tên đặc biệt như dấu gạch nối, SpEL hỗ trợ cú pháp tham chiếu tên có dấu nháy theo ngữ pháp bean reference; tuy nhiên để dễ đọc và ít lỗi, **ưu tiên tên camelCase chữ/số bình thường** như `documentPolicy`.

**Không đặt toàn bộ chính sách trong static method hoặc singleton lưu state user hiện tại.** Bean `@Component` mặc định singleton, phục vụ đồng thời nhiều người dùng; không cất `currentUser`, `lastDocument` hoặc `Authentication` của request trong **field mutable của singleton**. Mỗi lời gọi cần dùng Authentication/ID được truyền vào, repository và các service có vòng đời phù hợp.

## 12. Độ tin cậy của chính sách: fail closed và dữ liệu server

Vì bean policy có thể đọc DB, gọi service và so nhiều điều kiện, phải thiết kế **quy tắc từ chối an toàn**:

1. **Không xác thực hoặc thiếu authority → false.**
2. **Resource không tồn tại/không được phép tiết lộ → false** hoặc trả lỗi có xử lý mà không lộ tài nguyên ngoài scope; response policy không nên tiết lộ owner/tenant cho caller không có quyền.
3. **Tenant membership không hợp lệ → false**, kể cả role toàn hệ thống trông có vẻ đủ.
4. **Không thể đọc dữ liệu quyền do sự cố → không cho phép**. Lỗi kỹ thuật có thể dẫn đến 5xx, nhưng tuyệt đối không dùng fallback ALLOW.
5. **Không dùng input client làm nguồn sự thật của ownership.** Document ID phải được resolve trên server.
6. **Không cấp quyền dựa vào URL một mình.** URL path trùng `/api/documents/**` chỉ xác định loại endpoint, không chứng minh caller được đọc document 42.
7. **Giảm dữ liệu nhạy cảm trong log**: log decision type/request correlation ID, không log JWT, cookie hoặc toàn bộ object PII.
8. **Tránh side effects trong policy**: trước khi thực thi method, policy nên đọc và ra quyết định, không gửi email, ghi dữ liệu hoặc thay trạng thái.
9. **Dùng permission names có ý nghĩa**: `DOC_READ`, `DOC_APPROVE`, `DOC_DOWNLOAD` thay cho một role tổng quát không mô tả action.
10. **Xem xét cạnh tranh thời gian**: policy pre-check cho phép ở thời điểm T1 nhưng record đổi tại T2; thao tác ghi phải recheck dưới transaction.

Một rủi ro thường thấy là “bỏ policy vì chỉ là endpoint đọc”. Nếu endpoint trả invoice, address, report hoặc file riêng tư, **đọc cũng là hành động cần authorization**. `@PreAuthorize` giúp chặn trước khi service load object; kết hợp query-scoped data access có thể tránh đọc record ngoài quyền ngay từ database.

## 13. Hiệu năng và quyền khi gọi policy từ SpEL

Mỗi lời gọi method qua proxy có thể **đánh giá biểu thức** và gọi bean policy. Nếu policy dùng `repository.findById`, một request liệt kê 1000 records và gọi `canRead` riêng cho từng record có thể tạo hàng nghìn DB queries. Cần cân nhắc:

- **Kiểm tra quyền chung ở method** trước, ví dụ `hasAuthority('DOC_READ')`, rồi query data **đã giới hạn tenant/owner** tại repository.
- Với một object ID, dùng query `existsByIdAndOwner...` hoặc query gắn tenant nếu đủ điều kiện để giảm dữ liệu lấy về. Đặt index phù hợp.
- Với list/page, **lọc trong DB** theo tenant, owner, sharing scope để pagination/total count chính xác; đừng gọi bean policy cho từng item nếu có cách truy vấn quyền trên server hiệu quả hơn.
- Cache decision chỉ khi hiểu quyền **có thể bị thu hồi**, membership/role/state thay đổi và key cache bao gồm actor, tenant, action, resource, version hoặc thời hạn phù hợp. Cache nhầm `canRead(documentId)` bỏ actor/tenant là lỗ hổng.
- Nếu policy gọi service bên ngoài, đặt timeout, circuit-breaker fail closed và tránh biến lỗi hệ thống thành ALLOW.
- Trong các điều kiện boolean, viết `hasAuthority(...) and @policy...` để tránh query khi chắc chắn thiếu quyền; nhưng policy bản thân vẫn phải kiểm tra đầy đủ khi tái sử dụng.
- Nếu phải so tenant + owner + trạng thái ngay trước ghi, để transaction/domain method kiểm soát **bất biến tại thời điểm update**, không chỉ cache pre-check.

Đánh đổi quan trọng: tách policy bean giúp logic dễ test, nhưng **không có phép màu tự tối ưu N+1 hoặc transactional consistency**. `@PreAuthorize` ở bên ngoài một method `@Transactional` có thể chạy ở một transaction boundary khác. Đo/kiểm tra cấu hình advice ordering nếu nghiệp vụ cần tính nhất quán cụ thể; thông thường nên giữ pre-check để chặn quyền chung và đặt invariant check khi ghi trong transaction.

## 14. Kiểm thử policy bean độc lập: test input → boolean

Điểm mạnh của `@beanName` là logic policy có thể được test mà không cần chạy nguyên HTTP server. Với `DocumentPolicy`, dùng mock/fake repository và membership service để tạo các tình huống:

| Actor / tài nguyên | Permission | Membership/owner | Kỳ vọng `canRead` |
| --- | --- | --- | --- |
| Alice đọc document chính mình thuộc tenant A | Có `DOC_READ` | Membership A còn hiệu lực, owner Alice | `true`. |
| Alice đọc document của Bob cùng tenant A | Có `DOC_READ` | Không có team read | `false`. |
| Manager tenant A đọc document Bob ở tenant A | `DOC_READ` + `DOC_READ_TEAM` | Membership A hợp lệ | `true`. |
| Manager tenant A đọc document ở tenant B | Có `DOC_READ_TEAM` | Không có membership B | `false`. |
| Guest đọc document công khai nhầm | Thiếu `DOC_READ` | Dù ID tồn tại | `false`. |
| Document ID không tồn tại | Có permission | Repository trả empty | `false`. |
| Anonymous/null Authentication | Không hợp lệ | Không xét document | `false`. |
| Permission bị thu hồi | Không còn `DOC_READ` | Owner vẫn Alice | `false`. |

Với `canApprove`, test thêm trạng thái `PENDING`, actor không phải người tạo (four-eyes), khác tenant, không có `DOC_APPROVE`, record bị đóng hoặc xóa.

**Unit test policy** nên xác minh **không có side effect**, decision không tiết lộ dữ liệu và query không chạy khi thiếu authority. Dùng mock repository để `verifyNoInteractions` ở ca thiếu quyền nếu thiết kế có short-circuit. Nhưng test policy thuần **không chứng minh annotation `@PreAuthorize` đã được Spring kích hoạt**; cần thêm method-security integration test.

## 15. Kiểm thử annotation thực: @WithMockUser và service proxy

Một integration test Spring Boot với `spring-security-test` có thể gọi bean service qua proxy:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class DocumentServiceSecurityIT {

    @Autowired DocumentService documents;

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void ownerCanReadDocument() {
        DocumentView view = documents.read(10L);
        assertNotNull(view);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void ownerCannotReadOtherTenant() {
        assertThrows(AccessDeniedException.class,
            () -> documents.read(12L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "OTHER_PERMISSION")
    void missingPermissionDenied() {
        assertThrows(AccessDeniedException.class,
            () -> documents.read(10L));
    }
}
~~~

Đây là **cấu trúc test framework**, cần DB fixtures hoặc mock repository/membership, các bean `DocumentView`/`DocumentService` thật, `@EnableMethodSecurity` và Spring Test context. Dữ liệu 10/12 là **ID ví dụ**, không tự tồn tại trong database. Nếu dùng `@WithMockUser`, security context sẽ có username và authority được chỉ định, nhưng tenant membership phải được cấu hình trong fixture để logic policy trả đúng.

Để chứng minh `@PreAuthorize` **thực sự ngăn body**, dùng spy/counter ở repository `loadViewById` hoặc ở service body: khi policy false, **không được gọi** method body. Nếu chỉ test `@documentPolicy.canRead(...)` trả false, bạn mới xác minh bean policy; chưa xác minh expression đã resolve đúng bean hoặc interceptor đã chạy.

Một test chẩn đoán sai bean name có thể intentionally dùng context test không đăng ký `documentPolicy`, khi đó invocation sẽ lỗi đánh giá SpEL. Đừng viết test kỳ vọng 403 từ cấu hình sai bean, vì đó không phải một policy decision false bình thường.

### Test cả đường HTTP → service

Bên cạnh direct service test, dùng `MockMvc` hoặc test với Servlet container thật để kiểm tra endpoint HTTP:

- Anonymous gọi API private: có thể 401 hoặc redirect tùy authentication entry point.
- Có `DOC_READ`, document cùng tenant/owner: policy cho phép, response đúng.
- Có `DOC_READ` nhưng khác owner/tenant: method security từ chối, response thường 403 nếu web exception handling phù hợp.
- Thiếu `DOC_READ`: HTTP filter hoặc method có thể chặn; xác minh **lớp nào** chặn nếu cần.
- Dùng ID không tồn tại: không trả thông tin owner/tenant ngoài phạm vi.
- Gọi service từ job hoặc message listener: method security vẫn chạy nếu qua proxy, nhưng worker cần identity/service context hợp lệ.

Một response HTTP 403 **không đủ** chứng minh bean SpEL làm việc: CSRF, HTTP `AuthorizationFilter` hoặc authentication filter có thể chặn trước controller. Vì vậy test **policy bean thuần → direct method proxy → HTTP integration** theo thứ tự sẽ định vị lỗi chính xác.

## 16. Java 17 độc lập: mô phỏng gọi policy trước method body

Chương trình dưới đây **không dùng thư viện Spring** và không giải quyết SpEL parsing/AOP thật. Nó mô phỏng đúng ý tưởng `@PreAuthorize("@documentPolicy.canRead(authentication, #id)")`: một method policy **được gọi trước thân service**, policy dùng actor/permissions và dữ liệu server, rồi chỉ thực thi body khi được phép. Một policy khác kiểm tra four-eyes cho approve.

Lưu đúng tên **`PolicyBeanDecisionDemo.java`**:

~~~java
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

public class PolicyBeanDecisionDemo {
    record Actor(String name, String tenant, Set<String> authorities) {}
    record Document(int id, String owner, String tenant, String state) {}

    static final class DocumentRepository {
        private final Map<Integer, Document> documents = Map.of(
                10, new Document(10, "alice", "shop-a", "PENDING"),
                11, new Document(11, "bob", "shop-a", "PENDING"),
                12, new Document(12, "alice", "shop-b", "PENDING"),
                13, new Document(13, "bob", "shop-a", "CLOSED"));

        Document find(int id) { return documents.get(id); }
    }

    static final class DocumentPolicy {
        private final DocumentRepository repository;
        DocumentPolicy(DocumentRepository repository) {
            this.repository = repository;
        }

        boolean canRead(Actor actor, int id) {
            if (actor == null || !actor.authorities().contains("DOC_READ")) {
                return false;
            }
            Document doc = repository.find(id);
            if (doc == null || !actor.tenant().equals(doc.tenant())) {
                return false;
            }
            return actor.name().equals(doc.owner())
                    || actor.authorities().contains("DOC_READ_TEAM");
        }

        boolean canApprove(Actor actor, int id) {
            if (actor == null || !actor.authorities().contains("DOC_APPROVE")) {
                return false;
            }
            Document doc = repository.find(id);
            return doc != null
                    && actor.tenant().equals(doc.tenant())
                    && doc.state().equals("PENDING")
                    && !actor.name().equals(doc.owner());
        }
    }

    static String readWithGuard(DocumentPolicy policy, Actor actor,
                                int id, AtomicInteger bodyRuns) {
        if (!policy.canRead(actor, id)) {
            throw new SecurityException("Access denied");
        }
        bodyRuns.incrementAndGet();
        return "document-" + id;
    }

    public static void main(String[] args) {
        DocumentPolicy policy = new DocumentPolicy(new DocumentRepository());
        Actor alice = new Actor("alice", "shop-a", Set.of("DOC_READ"));
        Actor manager = new Actor("manager", "shop-a",
                Set.of("DOC_READ", "DOC_READ_TEAM", "DOC_APPROVE"));
        Actor bob = new Actor("bob", "shop-a", Set.of("DOC_APPROVE"));
        Actor guest = new Actor("guest", "shop-a", Set.of());
        AtomicInteger bodyRuns = new AtomicInteger();

        System.out.println("Alice read own: " + policy.canRead(alice, 10));
        System.out.println("Alice read Bob: " + policy.canRead(alice, 11));
        System.out.println("Manager read Bob: " + policy.canRead(manager, 11));
        System.out.println("Manager cross tenant: " + policy.canRead(manager, 12));
        System.out.println("Guest read: " + policy.canRead(guest, 10));
        System.out.println("Missing document: " + policy.canRead(alice, 999));
        System.out.println("Null actor: " + policy.canRead(null, 10));
        System.out.println("Bob approve Alice: " + policy.canApprove(bob, 10));
        System.out.println("Bob approve own: " + policy.canApprove(bob, 11));
        System.out.println("Manager approve closed: " + policy.canApprove(manager, 13));

        boolean denied = false;
        try {
            readWithGuard(policy, alice, 11, bodyRuns);
        } catch (SecurityException ex) {
            denied = true;
        }
        System.out.println("Denied before method body: " + denied);
        System.out.println("Body runs after denial: " + bodyRuns.get());
        System.out.println("Allowed method result: "
                + readWithGuard(policy, alice, 10, bodyRuns));
        System.out.println("Body runs after allow: " + bodyRuns.get());
    }
}
~~~

Biên dịch/chạy bằng **JDK 17 trở lên**:

~~~bash
javac --release 17 PolicyBeanDecisionDemo.java
java PolicyBeanDecisionDemo
~~~

Kết quả chính xác (đã chạy với JDK 17 target):

~~~text
Alice read own: true
Alice read Bob: false
Manager read Bob: true
Manager cross tenant: false
Guest read: false
Missing document: false
Null actor: false
Bob approve Alice: true
Bob approve own: false
Manager approve closed: false
Denied before method body: true
Body runs after denial: 0
Allowed method result: document-10
Body runs after allow: 1
~~~

Những dòng quan trọng: `Manager cross tenant: false` chứng minh permission nhóm chưa đủ để vượt tenant; `Missing document: false` và `Null actor: false` là fail-closed; `Denied before method body: true` cùng `Body runs after denial: 0` minh họa pre-authorization chặn trước execution. `Bob approve own: false` thể hiện four-eyes, còn `Manager approve closed: false` phản ánh trạng thái resource.

**Đây là mô hình Java thuần**: `Actor`/ `Document` là record do demo định nghĩa, không phải Spring `Authentication`, `DocumentRepository` là in-memory map, `readWithGuard` không thực sự chạy AOP. Mục đích là test logic trước khi đưa nó vào `@Component("documentPolicy")` và `@PreAuthorize` thật.

## 17. Những lỗi thường gặp và cách giải quyết

1. **Viết `@beanName` bên ngoài chuỗi SpEL.** → Ký hiệu này dùng **trong** `@PreAuthorize("...")`, không phải một annotation Java tương ứng.
2. **Nhầm `#id` thành `@id`.** → `#id` là tham số; `@id` là bean reference khác.
3. **Không có bean tên đúng `documentPolicy`.** → Đặt tên tường minh, bảo đảm component scan/context.
4. **Policy method không public hoặc sai signature.** → Viết public Java method nhận đúng Authentication/ID và trả boolean rõ.
5. **`@EnableMethodSecurity` chưa bật.** → Bật cấu hình, test một ca thiếu quyền thực sự bị chặn.
6. **Service self-invocation hoặc dùng `new`.** → Gọi qua Spring proxy và có negative test body-not-run.
7. **Tên `#documentId` không resolve.** → Bật `-parameters` hoặc `@P("id")`, cập nhật expression.
8. **Policy chỉ so owner từ client DTO.** → Tra server DB theo ID rồi kiểm tra tenant và ownership.
9. **Policy cho phép khi không tìm thấy record hoặc DB lỗi.** → Fail closed; lỗi kỹ thuật không được tự ALLOW.
10. **Policy singleton lưu Authentication trong mutable field.** → Cấm trộn request identities; truyền context theo từng invocation.
11. **Role nhầm prefix.** → `hasRole('ADMIN')` thường cần `ROLE_ADMIN`, authority JWT có thể là `SCOPE_admin`.
12. **Một user có permission nhưng tenant khác vẫn được ALLOW.** → Kiểm tra membership server-side và tenant của resource thật.
13. **Gọi `canRead` 1000 lần cho một list 1000 items.** → Thiết kế scoped query/exists/index và batch policy.
14. **Cache quyết định thiếu actor/tenant/action.** → Có thể rò quyền giữa người dùng; cache key và invalidation phải đúng.
15. **Dùng `@PreAuthorize` như thay thế invariant trong transaction.** → Bổ sung conditional update/locking ở body.
16. **Đánh đồng lỗi SpEL 500 với quyền bị từ chối 403.** → Tách lỗi cấu hình/kỹ thuật khỏi boolean deny.
17. **Dùng policy bean để gửi email/ghi DB trước permission.** → Policy nên không có side effect; chỉ quyết định.
18. **Chỉ test HTTP 403, không test bean/method.** → Test từng lớp để tránh false positive do CSRF/HTTP filter chặn sớm.
19. **Tin `principal.tenantId` luôn có.** → Xác định auth mechanism và custom principal type thật, không cast mù.
20. **Coi quyền được chụp lúc submit job vẫn hợp lệ khi job chạy.** → Với async/background work, kiểm tra identity, thời hạn và domain permission tại execution time.

## 18. Checklist áp dụng cho một phương thức mới

Trước khi merge một `@PreAuthorize("@policy...")`, nên xác minh:

- [ ] Bean policy có tên tường minh và tồn tại đúng application context.
- [ ] `@EnableMethodSecurity` đã bật và method được gọi qua Spring AOP proxy.
- [ ] SpEL dùng đúng `@beanName`, `#argument`, `authentication` hoặc `#root`.
- [ ] Policy method nhận đúng kiểu dữ liệu và trả boolean **false** khi không thể xác nhận quyền.
- [ ] Dữ liệu owner/tenant/status đến từ server tin cậy, không từ client gửi tùy ý.
- [ ] Auth được kiểm tra chính xác, bao gồm anonymous, role/authority prefix và principal type.
- [ ] Policy không gây side effect; có timeout/fail-closed khi dependency lỗi.
- [ ] Tối ưu query nếu gọi trong vòng lặp hoặc danh sách nhiều phần tử; không cache sai actor/tenant.
- [ ] Việc ghi dữ liệu vẫn recheck invariants trong transaction khi state có thể đổi.
- [ ] Có test policy thuần cho ALLOW/DENY và tenant/owner/missing/anonymous.
- [ ] Có test service proxy chứng minh false chặn body; không chỉ test policy method trực tiếp.
- [ ] Có integration test HTTP→service và entry point không qua HTTP.
- [ ] Error handling không lộ tài liệu/tenant thuộc người khác.
- [ ] Có regression tests khi đổi bean name, method signature, parameter name, JWT converter hoặc Spring Security version.

**Kết luận:** `@beanName` trong `@PreAuthorize` là **cú pháp SpEL để gọi một Spring bean chính sách**, không phải cơ chế cấp quyền tự động. Nó giúp dời logic authorization từ biểu thức dài vào **Java có thể kiểm thử**, kết hợp `Authentication`, method arguments và dữ liệu server để ra quyết định **trước khi body chạy**. Chính sách an toàn phải fail closed, kiểm soát owner/tenant/trạng thái, không có side effect và được kiểm thử ở **ba lớp: policy bean, method AOP proxy và HTTP integration**.

### Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Method Security: Using a Custom Bean in SpEL](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — Method Security: Method Parameters và Expression Handling](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — PreAuthorize API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/prepost/PreAuthorize.html)
- [Spring Framework — SpEL Bean References](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/beanref.html)
- [Spring Framework — AOP Proxying and Self Invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
