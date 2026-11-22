# RequestAuthorizationContext và MethodInvocation làm ngữ cảnh quyết định

## 1. Vấn đề: một quyết định phân quyền cần biết **đang bảo vệ điều gì**

Trong Spring Security, một `AuthorizationManager<T>` nhận hai đầu vào:

- `Supplier<Authentication>`: cách lấy danh tính đang được xác thực, bao gồm các authority đã cấp.
- `T`: **ngữ cảnh của hành động cần được cho phép hoặc từ chối**.

`T` không phải kiểu cố định. Khi bảo vệ một HTTP request trong ứng dụng Servlet, Spring Security thường dùng `RequestAuthorizationContext`; khi bảo vệ một lần gọi service method qua Spring AOP, ngữ cảnh là `MethodInvocation`. Hai đối tượng mang những dữ liệu khác nhau, xuất hiện ở những thời điểm khác nhau và áp dụng cho những biên bảo vệ khác nhau.

Đề bài này tập trung vào việc đọc và sử dụng **đúng ngữ cảnh quyết định**, đặc biệt khi tự viết `AuthorizationManager`: tránh nhầm URL với tham số method, tránh tin dữ liệu do client tự khai, chọn vị trí bảo vệ phù hợp và kiểm thử được quyết định cấp quyền/từ chối.

Tình huống mẫu: ứng dụng có tài liệu `Document`. Người dùng được đọc tài liệu nếu có authority `document:read`, thuộc tenant hợp lệ và là chủ sở hữu theo database. Khi truy cập `GET /api/documents/7`, HTTP layer có đường dẫn và path variable `7`; khi service `readDocument(7L)` chạy, method layer có `MethodInvocation` với tham số `7L`. Cả hai cần policy đáng tin cậy để biết **tài liệu 7 thuộc ai**.

## 2. Hợp đồng AuthorizationManager<T>

Với Spring Security 6.4+ và 7.x, API hiện đại mô tả phương thức quyết định chính là `authorize(...)`:

```java
AuthorizationResult authorize(
    Supplier<Authentication> authentication,
    T object
);
```

Chữ ký ở trên là **rút gọn để đọc ý nghĩa**; tài liệu API của từng bản có thể thêm annotation nullability hoặc wildcards cho `Supplier`. Kiểu trả về thường là `AuthorizationDecision`, một triển khai của `AuthorizationResult`, mang trạng thái `isGranted()`. Những ứng dụng phiên bản cũ có thể gặp `check(...)` trả về `AuthorizationDecision`; hãy dùng chữ ký chính xác theo dependency thực tế thay vì sao chép ngược giữa các phiên bản.

Về ý nghĩa, kết quả có ba khả năng:

| Kết quả | Diễn giải |
| --- | --- |
| `new AuthorizationDecision(true)` | Quy tắc này cho phép hành động |
| `new AuthorizationDecision(false)` | Quy tắc này từ chối hành động |
| `null` | Abstain — manager không đưa ra quyết định |

**Không dùng `null` để biểu thị từ chối.** Cách xử lý abstain phụ thuộc thành phần gọi và cách tổng hợp manager; với policy quan trọng, nên trả về **từ chối rõ ràng** khi thiếu danh tính, tài nguyên hoặc dữ liệu tin cậy. `AuthorizationManager.verify(...)` có nhiệm vụ ném `AccessDeniedException` khi nhận quyết định từ chối.

Lý do dùng `Supplier<Authentication>` thay vì lấy authentication ngay lập tức là để hỗ trợ **lấy danh tính khi thực sự cần**. Ví dụ rule `permitAll` có thể không cần truy cập `Authentication`. Khi viết manager riêng, chỉ gọi `authentication.get()` nếu cần danh tính; tránh gọi lặp lại hoặc giả định kết quả luôn khác `null`.

Lưu ý tên gọi: `AuthenticationManager` phục vụ **xác thực** thông tin đăng nhập, còn `AuthorizationManager` phục vụ **phân quyền** hành động trên một đối tượng/ngữ cảnh. Hai vai trò khác nhau.

## 3. RequestAuthorizationContext: quyết định tại biên HTTP

Kiểu Java:

```java
org.springframework.security.web.access.intercept.RequestAuthorizationContext
```

Đây là ngữ cảnh Servlet cho quyết định request-based. Các API đáng chú ý:

- `getRequest()` trả `jakarta.servlet.http.HttpServletRequest`, gồm HTTP method, URL, headers, parameters và những request attributes.
- `getVariables()` trả `Map<String, String>` gồm các biến được **request matcher trích xuất**, chẳng hạn `documentId` từ pattern `/api/documents/{documentId}`.
- Constructor nhận `HttpServletRequest`, hoặc nhận request cùng map các biến đường dẫn — hữu ích khi unit test.

Khi dùng `HttpSecurity.authorizeHttpRequests(...)`, Spring Security chọn rule matching, gọi `AuthorizationManager<RequestAuthorizationContext>` được cấu hình cho rule, rồi cho phép hoặc từ chối theo quyết định. Trong pipeline Servlet hiện đại, `AuthorizationFilter` đảm nhận bước thực thi authorization.

Ví dụ ý nghĩa dữ liệu:

```text
HTTP GET /api/documents/7?view=full
  |
  | requestMatcher: /api/documents/{documentId}
  v
RequestAuthorizationContext
  getRequest().getMethod()  -> "GET"
  getRequest().getRequestURI() -> "/api/documents/7"
  getVariables().get("documentId") -> "7"
  getRequest().getParameter("view") -> "full"
```

Đây chỉ là sơ đồ minh họa cho request đã match pattern tương ứng. `getVariables()` không phải bản đồ tùy ý của mọi query parameter hoặc mọi biến từ controller; nếu matcher không trích xuất biến thì map có thể trống. Nếu dùng prefix, servlet path, proxy hoặc cách cấu hình matcher khác, cần kiểm tra URL và các biến thực tế trong integration test.

**Ranh giới quan trọng:** path variable, header, query parameter và body đều là dữ liệu có thể do người gọi kiểm soát. Biến `documentId=7` chỉ nói người dùng yêu cầu **tài liệu 7**. Nó **không chứng minh** người dùng sở hữu hoặc có quyền đọc tài liệu đó.

### Đọc request để ra quyết định, nhưng không tin request là nguồn sự thật

Một quy tắc tốt có thể dùng request context để:

1. Kiểm tra hành động HTTP được phép, chẳng hạn chỉ `GET`.
2. Lấy identifier từ matcher và validate kiểu/range.
3. Lấy danh tính từ `Supplier<Authentication>` và kiểm tra authority.
4. Tra dữ liệu tài nguyên/tenant/ACL qua policy đã tin cậy.
5. Trả về quyết định boolean rõ ràng, ưu tiên từ chối nếu thiếu thông tin.

Đừng dùng `request.getParameter("role")` để cho client chọn role cần có; đừng coi `X-Tenant-Id` tự chứng minh quyền truy cập tenant. Nếu có tenant từ header, nó chỉ là **đầu vào yêu cầu chọn tenant**, phải đối chiếu membership đã được xác thực ở server.

## 4. Cài đặt một manager ở HTTP layer

Các đoạn tiếp theo là **thành phần cho ứng dụng Spring Boot dùng Spring Security 6.4+ hoặc 7.x trên Servlet**, không phải chương trình Java độc lập. Chúng giả định đã có các bean `DocumentPolicy`, `DocumentRepository` và entity `Document` của ứng dụng.

Đầu tiên, một bean policy chung kiểm tra quyền dựa trên danh tính và **dữ liệu thật**:

```java
import java.util.Optional;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class DocumentPolicy {
    private final DocumentRepository documents;
    private final TenantAccess tenantAccess;

    public DocumentPolicy(
            DocumentRepository documents, TenantAccess tenantAccess) {
        this.documents = documents;
        this.tenantAccess = tenantAccess;
    }

    public boolean canRead(Authentication auth, Long id) {
        if (auth == null || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken
                || id == null || id <= 0L) {
            return false;
        }

        boolean hasAuthority = auth.getAuthorities().stream()
            .anyMatch(a -> "document:read".equals(a.getAuthority()));
        if (!hasAuthority) {
            return false;
        }

        // TenantAccess là dịch vụ nghiệp vụ xác minh membership
        // từ nguồn đáng tin cậy, không chỉ từ header do client gửi.
        Optional<String> tenant = tenantAccess.authorizedTenant(auth);
        if (tenant.isEmpty()) {
            return false;
        }

        return documents.existsByIdAndTenantIdAndOwnerUsername(
            id, tenant.get(), auth.getName());
    }
}
```

Ở ví dụ này, `DocumentRepository` cần khai báo truy vấn derived `existsByIdAndTenantIdAndOwnerUsername(Long id, String tenantId, String ownerUsername)` hoặc cách truy vấn tương đương; `TenantAccess.authorizedTenant(...)` là hợp đồng ứng dụng do chúng ta phải triển khai. Policy chủ ý **chỉ cho owner đọc**. Nếu sản phẩm có chia sẻ theo ACL/nhóm, phần kiểm tra phải được mở rộng bằng nghiệp vụ và dữ liệu tin cậy, không tự nới quyền bằng cách nhận `owner` từ request.

Tiếp theo, manager cho HTTP request. Chúng ta dùng **lambda** để tránh phụ thuộc vào cách trình bày wildcard của chữ ký `authorize` giữa các phiên bản, nhưng vẫn triển khai `AuthorizationManager<RequestAuthorizationContext>`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
public class DocumentHttpAuthorizationConfig {
    @Bean
    AuthorizationManager<RequestAuthorizationContext> documentRequestManager(
            DocumentPolicy policy) {
        return (authentication, context) -> {
            String rawId = context.getVariables().get("documentId");
            Long id = parsePositiveId(rawId);
            if (id == null) {
                return new AuthorizationDecision(false);
            }

            Authentication actor = authentication.get();
            return new AuthorizationDecision(policy.canRead(actor, id));
        };
    }

    private static Long parsePositiveId(String raw) {
        if (raw == null || !raw.matches("[1-9][0-9]{0,17}")) {
            return null;
        }
        try {
            return Long.valueOf(raw);
        } catch (NumberFormatException ex) {
            return null;
        }
    }
}
```

Ở đây `context.getVariables().get("documentId")` có nguồn từ route matcher. `parsePositiveId` minh họa input contract giới hạn ID dương dạng số thập phân, tối đa 18 chữ số; dự án dùng UUID hoặc ID dạng khác phải thay bằng parser/validator tương ứng. Input lỗi trả `false` thay vì gây exception không cần thiết hoặc "mặc định cho phép".

Đăng ký manager vào một đường dẫn cụ thể:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
public class ApiSecurityConfig {
    @Bean
    SecurityFilterChain api(
            HttpSecurity http,
            AuthorizationManager<RequestAuthorizationContext> documentRequestManager
    ) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/documents/{documentId}")
                .access(documentRequestManager)
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

Trong ứng dụng thật, cần ghép cấu hình này với cơ chế xác thực API, CSRF/CORS, exception handling và các endpoint khác theo yêu cầu sản phẩm. Vì mẫu dùng `anyRequest().denyAll()`, những route khác sẽ bị từ chối nếu không có chain/rule phù hợp. `RequestAuthorizationContext.getVariables()` cần kiểm chứng ở **matcher được cấu hình thật**: thay đổi matcher, servlet mapping hoặc phiên bản có thể ảnh hưởng cách trích xuất biến.

**Vị trí đặt rule:** `authorizeHttpRequests` xét các request matcher theo thứ tự khai báo; rule khớp đầu tiên được áp dụng. Vì thế, hãy đặt pattern cụ thể trước wildcard tổng quát, có quy tắc fallback `denyAll`/yêu cầu xác thực phù hợp và test các path biến thể (ký tự mã hóa, dấu slash, hậu tố, phân biệt method).

## 5. MethodInvocation: quyết định tại biên gọi phương thức

Kiểu Java:

```java
org.aopalliance.intercept.MethodInvocation
```

`MethodInvocation` đại diện cho **một lần gọi phương thức Java đang được Spring AOP intercept**. Nó không phải `HttpServletRequest` và có thể tồn tại dù phương thức được gọi từ scheduled job, message listener, batch, test hay một service khác.

Các thành phần thường dùng:

| API | Ý nghĩa và cách dùng |
| --- | --- |
| `getMethod()` | Đọc `Method` phản ánh phương thức được gọi: tên, kiểu tham số, annotation tùy cách proxy |
| `getArguments()` | Truy cập mảng đối số runtime theo thứ tự khai báo |
| `getThis()` | Đối tượng target nơi lời gọi được thực thi, không phải thông tin caller HTTP |
| `proceed()` | Phương thức của `MethodInvocation` cho interceptor gọi tiếp; **không tự gọi trong AuthorizationManager** |
| `getStaticPart()` | Thông tin tĩnh về điểm gọi, thường không cần cho policy đơn giản |

Một `AuthorizationManager<MethodInvocation>` thông thường **chỉ đọc** tên method và arguments, lấy `Authentication`, kiểm tra policy rồi trả quyết định. Việc tiến hành hoặc chặn gọi do `AuthorizationManagerBeforeMethodInterceptor` thực hiện; business method không chạy nếu manager từ chối.

Ví dụ:

```text
Controller / message listener / service khác
     -> DocumentService.readDocument(7L)
         |
         v
     Spring AOP proxy
         |
         v
     MethodInvocation
       getMethod().getName() -> "readDocument"
       getArguments()[0] -> Long(7)
       getThis() -> DocumentService target
         |
         v
     AuthorizationManager<MethodInvocation>
         |
         +-- DENY -> chặn trước method
         |
         +-- GRANT -> gọi method thực
```

Không dựa vào việc `getThis()` là một HTTP controller hoặc có thể lấy request từ nó. Khi cần chính sách áp dụng ở **mọi đường gọi** của service, `MethodInvocation` và method security có lợi thế hơn kiểm tra chỉ ở đường HTTP.

### Vì sao argument chưa phải bằng chứng phân quyền?

Ví dụ caller gọi `readDocument(7L)`. Đối số `7L` là yêu cầu đọc tài liệu; điều đó **không chứng minh** user được đọc. Nếu method nhận entity `Document` từ client qua deserialization, trường `ownerUsername` trong entity đó cũng không nên được coi là quyền thực. Luôn đọc các đặc tính owner/tenant/ACL từ nguồn do server kiểm soát, hoặc dùng truy vấn đã bị ràng buộc theo danh tính thật.

`MethodInvocation.getArguments()` là mảng `Object[]`: phải kiểm tra số lượng, kiểu, `null` và định dạng trước khi ép kiểu. Với overload hoặc signature đổi, kiểm tra theo chỉ số `args[0]` có thể sai; nên ghép với pointcut chặt chẽ, test signature và cân nhắc đặt tên method/annotation cụ thể.

## 6. Cài đặt manager tại method layer

Giả sử service thực của chúng ta là:

```java
package com.example.documents;

import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    public Document readDocument(Long documentId) {
        return documents.findById(documentId).orElseThrow();
    }
}
```

Đây là class service thành phần, cần entity/repository đã triển khai. Khi được gọi qua proxy, ta muốn **chặn trước** khi `readDocument` truy vấn.

Manager method:

```java
import org.aopalliance.intercept.MethodInvocation;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;

@Configuration
public class DocumentMethodManagerConfig {
    @Bean
    AuthorizationManager<MethodInvocation> documentMethodManager(
            DocumentPolicy policy) {
        return (authentication, invocation) -> {
            Object[] args = invocation.getArguments();
            if (args.length != 1 || !(args[0] instanceof Long id)) {
                return new AuthorizationDecision(false);
            }

            Authentication actor = authentication.get();
            return new AuthorizationDecision(policy.canRead(actor, id));
        };
    }
}
```

Manager không được để `null`/sai kiểu lọt qua như một kết quả "không quyết định". Việc kiểm tra bằng `instanceof Long id` hoạt động với signature `readDocument(Long documentId)`; nếu tham số là primitive `long` thì giá trị trong `Object[]` thường vẫn được boxing thành `Long`. Nếu service có nhiều tham số hoặc nhiều method cùng pointcut, cần xác định điều kiện từ signature đúng và viết test.

Đăng ký advisor **chỉ áp dụng cho đúng service method**:

```java
import org.aopalliance.intercept.MethodInvocation;
import org.springframework.aop.Advisor;
import org.springframework.aop.aspectj.AspectJExpressionPointcut;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Role;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeMethodInterceptor;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class DocumentMethodSecurityConfig {
    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    Advisor documentReadAdvisor(
            AuthorizationManager<MethodInvocation> documentMethodManager) {
        AspectJExpressionPointcut pointcut = new AspectJExpressionPointcut();
        pointcut.setExpression(
            "execution(* com.example.documents.DocumentService.readDocument(..))"
        );
        return new AuthorizationManagerBeforeMethodInterceptor(
            pointcut, documentMethodManager);
    }
}
```

Điều kiện tiên quyết: class đích đúng package, ứng dụng có Spring AOP, advisor được container đăng ký và lời gọi đi **qua proxy**. Nếu sử dụng Spring Boot starter tương ứng và `@EnableMethodSecurity`, cần đảm bảo không vô tình đăng ký hai policy mâu thuẫn cho cùng method. Method có `@PreAuthorize` sẵn cũng có thể chịu thêm advisor khác; nhiều kiểm tra có thể cùng áp dụng.

Chúng ta đã tách:

- **Manager**: quyết định boolean từ `Authentication + MethodInvocation`.
- **Pointcut**: chọn **những method** nào cần manager đó.
- **Before interceptor**: gọi manager **trước** method rồi chặn/cho đi tiếp.
- **Bean policy**: nơi kiểm tra quyền tài nguyên bằng dữ liệu thật.

Với nhu cầu thông thường, viết `@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")` trên service đơn giản hơn quản lý một custom advisor. Cách custom `AuthorizationManager<MethodInvocation>` hữu ích khi cần policy Java thống nhất cho nhiều method, custom pointcut hoặc thay đổi cơ chế interception ở tầng framework.

## 7. So sánh hai context theo góc nhìn thiết kế

| Khía cạnh | `RequestAuthorizationContext` | `MethodInvocation` |
| --- | --- | --- |
| Cấp bảo vệ | HTTP Servlet request | Lời gọi Java method qua AOP |
| Lớp điều phối phổ biến | `AuthorizationFilter`, `authorizeHttpRequests` | `AuthorizationManagerBeforeMethodInterceptor` / method security |
| Đầu vào chính | `HttpServletRequest` + matcher path variables | `Method`, `Object[]` arguments, target |
| Kiểu manager | `AuthorizationManager<RequestAuthorizationContext>` | `AuthorizationManager<MethodInvocation>` |
| Dùng để làm gì tốt? | Phân quyền endpoint, HTTP method, path/route, coarse-grained access | Phân quyền thao tác nghiệp vụ và tài nguyên ở service, không phụ thuộc nguồn gọi |
| Cần chú ý | URL/headers/query params do client kiểm soát; matcher có thể không trích biến | Arguments có thể do caller/client kiểm soát; proxy self-invocation; overload |
| Có sẵn HTTP response/status? | Quyết định authorization là đầu vào để filter xử lý; không tự trả response | Không phụ thuộc HTTP, lỗi có thể xuất hiện trong batch/job |
| Có sẵn quyền sở hữu trong database? | **Không** | **Không** |
| Có thể tái sử dụng policy chung? | Có, bằng bean `DocumentPolicy` | Có, bằng cùng bean `DocumentPolicy` |

**Phân biệt cốt lõi:** context cung cấp "đây là request nào / method nào đang được gọi", chứ không bảo đảm "hành động này được phép" hoặc "dữ liệu trong input là sự thật". Authentication và policy trả lời phần còn lại.

## 8. Phân quyền theo nhiều lớp mà không vô tình nhân đôi logic

Trong ứng dụng thực, một hành động HTTP có thể đi qua cả hai lớp:

```text
GET /api/documents/7
  -> SecurityFilterChain:
       Authentication + RequestAuthorizationContext
       kiểm tra endpoint / authority
  -> Controller:
       parse path variable -> Long(7)
  -> Service proxy:
       Authentication + MethodInvocation(readDocument, [7L])
       kiểm tra quyền trên tài liệu 7
  -> Repository:
       truy vấn có điều kiện tenant/owner/ACL
  -> Response
```

Nếu cả HTTP manager và method manager cùng gọi policy đắt (ví dụ mỗi lần query DB), một request có thể phải kiểm tra trùng hai lần. Thiết kế thường hợp lý:

1. HTTP layer yêu cầu authentication, authority cho route, kiểm tra HTTP method và các điều kiện request hợp lệ.
2. Service layer kiểm tra quyền thao tác gắn với **tài nguyên thực** và có hiệu lực với các nguồn gọi ngoài HTTP.
3. Repository bảo đảm truy vấn/ghi bị ràng buộc bởi tenant/owner/ACL theo chính sách, đặc biệt cho cập nhật hoặc danh sách lớn.

Ví dụ cấu hình hai manager ở trên **cố ý dùng lại cùng policy** để thấy cấu trúc hai context; tùy nghiệp vụ, có thể bỏ truy vấn DB dư thừa ở HTTP layer và để method/repository chịu trách nhiệm quyền tài nguyên. Không bỏ method-level policy chỉ vì HTTP filter có vẻ đã kiểm tra, khi service còn được gọi từ job, listener hoặc entry point khác.

**Điểm quan trọng khi write:** kiểm tra trước khi cập nhật trạng thái; lưu ý TOCTOU nếu quyền thay đổi giữa kiểm tra và transaction. Đặt ràng buộc quyền trong câu truy vấn cập nhật/transaction khi cần. `@PostAuthorize` chạy sau method nên không phải công cụ tin cậy để ngăn tác dụng phụ đã xảy ra.

## 9. Kiểu dữ liệu, thời điểm, tính bất biến và logging

### Dữ liệu ở RequestAuthorizationContext

Ví dụ `request.getParameter("tenant")` hoặc `context.getVariables().get("documentId")` đều có nguồn từ request, cần validate và đối chiếu dữ liệu server. Không ghép trực tiếp giá trị đó thành SpEL, SQL hoặc path đến tài nguyên khác. Mỗi request có context riêng; không lưu context hoặc request vào singleton field dùng lại giữa các thread.

Nếu cần body JSON để ra quyết định, tránh ép authorization filter đọc và consume request body sớm: filter có thể chạy trước controller và message converter, xử lý body theo cách không phù hợp có thể ảnh hưởng downstream. Quy tắc gắn với nội dung đã parse/validate thường hợp lý hơn ở service method với DTO rõ ràng và policy Java.

### Dữ liệu ở MethodInvocation

`invocation.getMethod()` có thể phản ánh method khai báo trên interface khi dùng JDK proxy; khi cần annotation/generic type từ implementation, phải chọn cơ chế resolution phù hợp và kiểm thử cả interface proxy lẫn class proxy. Đừng dùng `getMethod().getName()` duy nhất làm định danh security rule khi có overload hoặc nhiều service dùng chung tên method.

`invocation.getArguments()` cho thấy argument **tại thời điểm interceptor**. Nó không biến giá trị thành đáng tin chỉ vì đã đi qua controller. Không để manager tự `proceed()` hoặc sửa argument để "chuyển hướng" điều kiện; nhiệm vụ của manager là quyết định, không là chạy business code.

### Authentication và thread

`authentication.get()` không phải đọc raw header từ request; nó nhận đối tượng auth đã được Spring Security thiết lập. Mặc dù vậy, không mọi đối tượng `Authentication` đều là người dùng đăng nhập thật; anonymous authentication có thể báo `isAuthenticated() == true`. Policy ví dụ từ chối `AnonymousAuthenticationToken` và yêu cầu authority rõ ràng. Với OAuth2/JWT hoặc pre-auth, xác minh cách hệ thống map principal, scope, tenant và authority.

Đối với `@Async`, executor và thread khác, `SecurityContext` có thể không tự được truyền; method-level manager cần test trong thread thật. Đừng chuyển context request sang luồng khác bằng cách giữ request object trong singleton.

### Ghi log, audit và dữ liệu nhạy cảm

Có thể ghi tên endpoint hoặc tên operation cùng kết quả `GRANT/DENY`, thời gian và correlation ID phù hợp. Không log toàn bộ `Authentication`, token, session, URL có secret, tham số cá nhân, hay dump toàn bộ `MethodInvocation.getArguments()`. Kết quả từ chối của manager không tự cung cấp lý do cho client; audit nên phân biệt "thiếu quyền" với "không tìm thấy tài nguyên" theo chính sách không tiết lộ thông tin.

## 10. Ví dụ Java 17 chạy độc lập để hiểu hai kiểu context

Ví dụ sau **mô phỏng** web context và method context bằng Java record; nó không dùng Spring Security/AOP và không thay thế integration test. Mục đích là thấy dù context khác nhau, cả hai vẫn có thể gửi **ID tài nguyên** tới cùng một policy đáng tin cậy.

Lưu file `AuthorizationContextDemo.java`:

```java
import java.util.Set;

public class AuthorizationContextDemo {
    record Actor(String name, String tenant, Set<String> authorities) {}
    record Document(long id, String tenant, String owner) {}
    record WebContext(String httpMethod, String idFromPath) {}
    record MethodContext(String name, Object[] arguments) {}

    static boolean policy(Actor actor, Document document) {
        return actor != null
            && actor.authorities().contains("document:read")
            && actor.tenant().equals(document.tenant())
            && actor.name().equals(document.owner());
    }

    static boolean webAllowed(
            Actor actor, WebContext context, Document document) {
        if (!"GET".equals(context.httpMethod())) {
            return false;
        }

        long requestedId;
        try {
            requestedId = Long.parseLong(context.idFromPath());
        } catch (NumberFormatException ex) {
            return false;
        }

        return requestedId > 0
            && requestedId == document.id()
            && policy(actor, document);
    }

    static boolean methodAllowed(
            Actor actor, MethodContext context, Document document) {
        Object[] args = context.arguments();
        if (!"readDocument".equals(context.name())
                || args.length != 1
                || !(args[0] instanceof Long id)) {
            return false;
        }
        return id == document.id() && policy(actor, document);
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
            "alice", "tenant-a", Set.of("document:read"));
        Actor bob = new Actor(
            "bob", "tenant-a", Set.of("document:read"));
        Document aliceDoc = new Document(7, "tenant-a", "alice");

        WebContext getSeven = new WebContext("GET", "7");
        MethodContext readSeven =
            new MethodContext("readDocument", new Object[] {7L});

        System.out.println("Alice web: "
            + webAllowed(alice, getSeven, aliceDoc));
        System.out.println("Bob web: "
            + webAllowed(bob, getSeven, aliceDoc));
        System.out.println("Alice service: "
            + methodAllowed(alice, readSeven, aliceDoc));
        System.out.println("Bob service: "
            + methodAllowed(bob, readSeven, aliceDoc));
        System.out.println("Invalid path ID: "
            + webAllowed(alice, new WebContext("GET", "abc"), aliceDoc));
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac AuthorizationContextDemo.java
java AuthorizationContextDemo
```

Stdout chính xác:

```text
Alice web: true
Bob web: false
Alice service: true
Bob service: false
Invalid path ID: false
```

Trong mã này, `WebContext` mang ID là `String` và phải parse. `MethodContext` mang đối số `Long` đã được tầng gọi truyền. **Dù kiểu dữ liệu khác, cả hai vẫn phải gọi `policy(...)`** để xác minh authority, tenant và owner. Mã không chạm đến framework; với ứng dụng thật, phải kiểm thử matcher/proxy và truy vấn dữ liệu.

## 11. Kiểm thử manager và đường tích hợp

Đừng chỉ test hàm `DocumentPolicy.canRead`. Bảo đảm **ngữ cảnh thực được đưa đến manager** và interceptor thực sự áp dụng.

### 11.1 Unit test web manager

Có thể tạo `MockHttpServletRequest` và `RequestAuthorizationContext` trực tiếp bằng:

```java
import java.util.Map;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

MockHttpServletRequest request =
    new MockHttpServletRequest("GET", "/api/documents/7");
RequestAuthorizationContext context =
    new RequestAuthorizationContext(
        request, Map.of("documentId", "7"));
```

Đây là đoạn **test fragment** cần `spring-test` và manager thật được khởi tạo/tiêm vào. Unit test với context tự tạo kiểm chứng logic parse/deny của manager, nhưng **không chứng minh matcher thực tế trích xuất biến**. Phải có MockMvc hoặc Servlet integration test đi qua `SecurityFilterChain`.

Các case tối thiểu: `documentId` thiếu, rỗng, sai định dạng, overflow, ID âm/0, authority thiếu, anonymous, tenant khác, owner khác và role hợp lệ. Một test quan trọng là `GET` được phép theo policy nhưng `POST` cùng path bị từ chối bởi rule HTTP method trong chain.

### 11.2 Unit test method manager

Dùng Mockito hoặc test double tạo một `MethodInvocation` có method signature tương ứng và `Object[]` chứa `Long`. Kiểm tra:

- `readDocument(7L)` với chủ sở hữu, tenant và authority hợp lệ → `isGranted() == true`.
- ID `null`, kiểu sai, số lượng argument sai → `false`.
- ID hợp lệ nhưng sai tenant/owner hoặc thiếu authority → `false`.
- `authentication.get()` trả `null` hoặc anonymous → `false`.

Tuy nhiên một manager tự chạy đúng **không đảm bảo** service có proxy và advisor được áp dụng. Trong integration test, lấy `DocumentService` từ Spring context rồi gọi public method; assert body/repository không chạy khi denied. Kiểm tra cả khi service được gọi từ controller, scheduler hoặc bean khác.

### 11.3 Test đường đi thực tế và dữ liệu

| Tình huống | Điều phải chứng minh |
| --- | --- |
| HTTP path đúng + user được phép | Matcher trích `documentId` và manager cho phép |
| HTTP path đúng + user không đủ quyền | Trả 401/403 theo cơ chế xác thực/entry point, không đọc tài liệu trái quyền |
| Path không khớp rule | Fallback bảo vệ/deny hoạt động |
| Lời gọi trực tiếp service từ bean khác | Method manager vẫn kiểm tra quyền |
| `this.readDocument(...)` trong cùng service | Có thể bypass Spring AOP proxy; phát hiện và sửa thiết kế |
| Concurrent tenant/owner change | Policy và transaction/query ngăn đọc/ghi trái quyền do race |
| HTTP manager và method manager cùng chạy | Không tạo truy vấn DB dư quá mức, không có nhánh cấp quyền mâu thuẫn |
| Async hoặc message processing | `Authentication`/SecurityContext có sẵn đúng cách hoặc deny an toàn |
| Invocation sai signature | Từ chối rõ, không `ClassCastException` hay silent allow |

Một số project có thể xử lý "không được xem hoặc không tồn tại" thành HTTP 404 để hạn chế rò rỉ sự tồn tại tài nguyên. Quyết định này thuộc thiết kế API/exception handling và phải thống nhất; `AuthorizationDecision(false)` không tự động đảm bảo status cụ thể trong mọi cấu hình.

## 12. Lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai | Sửa thế nào |
| --- | --- | --- |
| Dùng `RequestAuthorizationContext` để lấy method arguments đã parse/validated của controller | Nó chỉ chứa Servlet request và matcher variables | Dùng `MethodInvocation` cho service parameters |
| Coi `context.getVariables()` luôn có mọi biến của controller | Map tùy matcher có thể trống hoặc không chứa key yêu cầu | Kiểm thử matcher; xử lý thiếu biến bằng deny |
| Tin `documentId`, `owner`, `tenant` từ path/header là bằng chứng sở hữu | Input do client kiểm soát | Query owner/tenant/ACL bằng danh tính server đã xác thực |
| Gọi `authentication.get()` rồi mặc định actor là user thật | Có thể thiếu auth/anonymous | Kiểm tra identity, authority và chính sách auth thực |
| Trả `null` khi user thiếu quyền | `null` là abstain, không đồng nghĩa deny | Trả `new AuthorizationDecision(false)` |
| Cho manager tự gọi `invocation.proceed()` | Trộn quyết định với thực thi business method | Chỉ trả kết quả; interceptor quyết định tiếp tục |
| Dùng `getArguments()[0]` mà không kiểm tra type/length | Dễ exception hoặc phân quyền nhầm khi đổi signature | Kiểm tra rõ kiểu, pointcut và test overload |
| Dùng tên method làm key policy duy nhất | Trùng tên/overload/interface proxy có thể sai | Dùng pointcut, signature, annotation và test |
| Chỉ bảo vệ URL, bỏ service dùng lại từ jobs | Đường gọi không qua HTTP filter thiếu check | Thêm method security/kiểm soát tại service |
| Chỉ bảo vệ method bằng annotation rồi gọi `this.method()` | Self-invocation có thể bypass proxy | Thiết kế public entry point qua Spring bean/proxy |
| Tách permission check khỏi query theo tenant | Có race hoặc query không giới hạn dữ liệu | Đặt điều kiện quyền đúng ở data access, cần thiết thì cùng transaction |
| Debug bằng cách dump toàn request và invocation | Rò rỉ token, headers, dữ liệu nhạy cảm | Log metadata tối thiểu, che thông tin riêng |

## 13. Checklist chọn đúng context

1. **Chính sách áp dụng ở đâu?** Endpoint HTTP dùng `RequestAuthorizationContext`, service operation dùng `MethodInvocation`.
2. **Trích đúng dữ liệu?** HTTP: method/path/matcher variables. Method: signature và arguments.
3. **Dữ liệu nào là không tin cậy?** Mọi path/header/query và arguments do caller/HTTP truyền có thể giả mạo.
4. **Đã lấy Authentication đúng cách?** Kiểm tra null/anonymous và authority được hệ thống cấp.
5. **Đã kiểm tra quyền trên tài nguyên thật?** Dùng policy server + tenant/owner/ACL ở database.
6. **Thiếu dữ liệu thì sao?** Trả explicit deny, không lẫn abstain với deny.
7. **Đã gắn manager vào đúng điểm thực thi?** Với HTTP: `.access(manager)` của matcher cụ thể. Với method: `Advisor` và pointcut cụ thể hoặc annotation thích hợp.
8. **Đã test matcher/proxy thật?** Unit test manager không thay thế integration test.
9. **Đã tính các đường gọi khác HTTP?** Scheduler, message listener, nội bộ service, async, self-invocation.
10. **Đã tránh double work và race?** Tận dụng HTTP coarse-grained check, method-level resource policy và data query có điều kiện.

**Kết luận học tập:** `RequestAuthorizationContext` trả lời "**request nào đang được yêu cầu?**"; `MethodInvocation` trả lời "**method nào với những arguments nào đang được gọi?**". Cả hai cùng với `Authentication` tạo thông tin đầu vào cho `AuthorizationManager`, còn sự thật về quyền truy cập tài nguyên phải được xác minh bằng **policy và dữ liệu tin cậy**.

## Tài liệu chính thức

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager`, `AuthorizationResult`, supplier và quyết định allow/deny/abstain.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `authorizeHttpRequests`, `requestMatchers`, `.access(...)` và path variables.
- [Spring Security API — RequestAuthorizationContext](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/intercept/RequestAuthorizationContext.html): `getRequest()` và `getVariables()`.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, custom `AuthorizationManager<MethodInvocation>` và `AuthorizationManagerBeforeMethodInterceptor`.
- [Spring Security API — AuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManager.html): chữ ký API phiên bản hiện hành và phương thức `authorize`.
