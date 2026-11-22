# Đối tượng không tồn tại, thiếu quyền và chính sách trả lỗi với PermissionEvaluator

## 1. Bài toán: “không tồn tại” khác “không có quyền”

Khi người dùng gọi `GET /api/documents/42`, hệ thống có thể gặp ba tình huống rất khác nhau:

1. Tài liệu 42 **không tồn tại** trong hệ thống hoặc đã bị xóa.
2. Tài liệu 42 **có tồn tại**, nhưng người gọi không thuộc tenant, không sở hữu hoặc không được chia sẻ tài liệu.
3. Tài liệu 42 tồn tại và người gọi **được phép** đọc nó.

Ở tầng nghiệp vụ, ta muốn nhận diện đúng từng tình huống. Nhưng ở tầng API, không phải ứng dụng nào cũng nên nói cho người dùng biết đối tượng bị cấm có thật hay không. Một câu trả lời khác nhau giữa `403 Forbidden` và `404 Not Found` có thể giúp người ngoài dò danh sách ID, dự án, tài khoản hoặc hồ sơ bí mật.

Spring Security cung cấp `PermissionEvaluator` làm điểm mở rộng để trả lời câu hỏi: **người dùng này có quyền cụ thể trên đối tượng/ID này không?** Nó **trả về boolean**, không quyết định trực tiếp mã HTTP. Chính sách phản hồi `401`, `403`, `404` hay `5xx` nằm ở những tầng khác của ứng dụng và cần được thiết kế có chủ đích.

Mục tiêu bài học:

- Hiểu chính xác hai overload của `PermissionEvaluator.hasPermission(...)`.
- Phân biệt “đối tượng không tồn tại”, “không có quyền”, “chưa xác thực” và “lỗi hạ tầng”.
- Biết lúc nào trả `false` an toàn, lúc nào phải phát sinh exception.
- Chọn chính sách `403` hoặc `404` không làm lộ sự tồn tại tài nguyên.
- Cài đặt ví dụ Spring Security và lựa chọn thay thế bằng query giới hạn theo principal/tenant.
- Kiểm thử hành vi bằng MockMvc, method security, database và các kịch bản dò ID.

## 2. Hai overload của PermissionEvaluator

Interface `org.springframework.security.access.PermissionEvaluator` định nghĩa hai cách kiểm tra:

```java
boolean hasPermission(
    Authentication authentication,
    Object targetDomainObject,
    Object permission
);

boolean hasPermission(
    Authentication authentication,
    Serializable targetId,
    String targetType,
    Object permission
);
```

### Dạng nhận domain object

`hasPermission(authentication, targetDomainObject, permission)` được dùng khi lời gọi đã có **đối tượng**. Ví dụ:

```java
@PreAuthorize("hasPermission(#document, 'read')")
public void process(Document document) {
    // ...
}
```

`#document` là tham số của phương thức. Nếu nó đến từ body do client gửi, các trường `ownerId`, `tenantId` trong object có thể bị giả mạo; đừng cho phép chỉ vì client tự ghi owner trùng tên mình. Với entity được tải từ database, cần tính đến việc nó đã được tải trong phạm vi bảo vệ nào và có bị thay đổi trong thời gian kiểm tra không.

Theo Javadoc, `targetDomainObject` **có thể bằng null**; implementation được khuyến nghị trả `false` khi target null. Nếu business method cần phân biệt “null” với “không có quyền”, việc đó nên được xử lý riêng ở lớp dữ liệu/lỗi thay vì cho evaluator ném lỗi `NullPointerException`.

### Dạng nhận ID và loại tài nguyên

`hasPermission(authentication, targetId, targetType, permission)` được dùng khi phương thức chỉ có ID:

```java
@PreAuthorize("hasPermission(#documentId, 'Document', 'read')")
public Document readDocument(Long documentId) {
    // ...
}
```

Ở đây Spring Security truyền `documentId` như một `Serializable`, chuỗi literal `"Document"` làm `targetType` và `"read"` làm `permission`. **`targetType` không tự tạo hoặc truy xuất entity**; code evaluator phải quyết định cách ánh xạ giá trị này tới repository thích hợp. Không dùng `Class.forName(targetType)` hoặc truy vấn tên table động từ chuỗi không tin cậy.

Cả hai overload đều trả:

- `true`: permission được cấp cho caller trên target đang xét.
- `false`: không cấp permission — có thể do không tồn tại, thiếu quyền, target sai, ID không hợp lệ hoặc policy fail-closed.
- Không có giá trị thứ ba “not found” trong hợp đồng boolean.

**Quan trọng:** `false` không mang mã HTTP. Khi dùng trong `@PreAuthorize`, kết quả `false` làm method security **từ chối lời gọi trước khi thân phương thức chạy**. Trên đường HTTP, kết quả thường được chuyển thành `403` cho người dùng đã xác thực, không phải tự động `404`.

## 3. Bảng trạng thái: nội bộ khác phản hồi ra ngoài

| Điều kiện trong hệ thống | Ý nghĩa nội bộ | HTTP thường cân nhắc | Ghi chú |
| --- | --- | --- | --- |
| Chưa có Authentication hợp lệ | Chưa xác thực | `401 Unauthorized` hoặc chuyển hướng đăng nhập | Phụ thuộc authentication entry point |
| Đã xác thực, thiếu quyền thao tác chung | Không đủ quyền | `403 Forbidden` | Có thể bị deny ở filter/method trước khi tra ID |
| ID hợp lệ, tài nguyên không tồn tại | Not found | `404 Not Found` | Không nói có quyền với thứ không tồn tại |
| ID hợp lệ, tài nguyên tồn tại nhưng không được xem | Forbidden | `403` **hoặc `404` che giấu** | Chọn theo yêu cầu chống rò rỉ sự tồn tại |
| Tài nguyên tồn tại, có quyền | Granted | `200 OK`, `204 No Content`, v.v. | Tùy endpoint |
| ID sai định dạng | Invalid request | `400 Bad Request` hoặc `404` theo routing/API | Đây là lỗi đầu vào, không phải kết quả PermissionEvaluator |
| Database lỗi, timeout, mất kết nối | Lỗi hạ tầng | `500`/`503` tùy tình huống | Không coi là 404 và không cho phép truy cập |

`401`, `403` và `404` là các mã giao thức HTTP, **không phải giá trị trả về của PermissionEvaluator**. Spring Security dùng `AuthenticationEntryPoint` cho nhiều tình huống chưa xác thực, `AccessDeniedHandler` cho tình huống đã xác thực nhưng thiếu quyền; `ExceptionTranslationFilter` là cầu nối exception bảo mật với HTTP response trong filter chain.

Đừng áp dụng một bảng cố định cho mọi giao thức: một service được gọi từ batch job, message listener hoặc scheduled task có thể nhận `AccessDeniedException` mà không tồn tại HTTP status. Đối với REST API, hãy thiết kế mapping HTTP tại biên ứng dụng và viết integration test với security configuration thực.

## 4. Chính sách 403 và chính sách 404 che giấu tồn tại

### Chính sách A: phân biệt “không tồn tại” với “không đủ quyền”

Phù hợp khi sự tồn tại của đối tượng **được phép công khai**. Ví dụ sản phẩm công khai, sự kiện công cộng, hoặc tài nguyên mà mọi người đã có quyền xem metadata.

```text
GET /public-documents/42
         |
         v
  Tra cứu document 42
      |       |
  không có   có
      |       |
     404     kiểm tra permission
                 |       |
                DENY    GRANT
                 |       |
                403     200
```

**Rủi ro:** hai status khác nhau có thể trở thành một “existence oracle”. Nếu ID 42 trả `403` còn 43 trả `404`, người ngoài suy ra 42 có thật, dù không đọc được nội dung. Trong môi trường đa tenant hoặc dữ liệu riêng tư, đó có thể là thông tin cần bảo vệ.

### Chính sách B: “không nhìn thấy” được xử lý như “không tồn tại”

Phù hợp cho hồ sơ riêng tư, dự án nội bộ, dữ liệu tenant khác hoặc đối tượng mà người gọi **không có quyền biết nó tồn tại**.

```text
GET /documents/42
        |
        v
  Tra trong phạm vi dữ liệu caller được đọc
        |
        +-- Có bản ghi nhìn thấy -> 200
        |
        +-- Không có bản ghi nhìn thấy -> 404
             (gồm thực sự không tồn tại và bị cấm)
```

Đây là kiểu **resource hiding**: cùng một thông điệp trung tính cho “ID không tồn tại” và “ID tồn tại nhưng ngoài phạm vi có quyền”. Không phải mọi `403` đều cần đổi thành `404`. Ví dụ người dùng không có authority cơ bản `document:read` có thể nhận `403` trước khi truy vấn, vì điều đó không tiết lộ sự tồn tại của một ID cụ thể.

**Nguyên tắc chọn:** công bố một chính sách nhất quán cho từng loại endpoint. Không để các service cùng lớp dữ liệu lúc trả `403`, lúc trả `404` tùy một nhánh tình cờ; không đổi mã trả về tùy từng Exception message.

## 5. PermissionEvaluator nên trả false thế nào?

Ví dụ sau chỉ minh họa **các class thành phần trong ứng dụng Spring Boot**, không chạy độc lập. Giả định dự án có repository `DocumentRepository`, entity `Document` và dịch vụ `TenantScopeService` với hợp đồng dữ liệu được ứng dụng triển khai.

Một evaluator cho read permission trên Document bằng ID:

```java
import java.io.Serializable;
import java.util.Optional;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class DocumentPermissionEvaluator implements PermissionEvaluator {

    private final DocumentRepository documents;
    private final TenantScopeService scopes;

    public DocumentPermissionEvaluator(
            DocumentRepository documents, TenantScopeService scopes) {
        this.documents = documents;
        this.scopes = scopes;
    }

    @Override
    public boolean hasPermission(
            Authentication auth, Object target, Object permission) {
        if (!(target instanceof Document document)) {
            return false; // gồm target null, sai loại
        }

        // Chỉ dùng ID từ đối tượng để tra policy tại nguồn tin cậy.
        // Không tin các trường owner/tenant được client tự gửi.
        return hasPermission(
            auth, document.getId(), "Document", permission);
    }

    @Override
    public boolean hasPermission(
            Authentication auth,
            Serializable targetId,
            String targetType,
            Object permission) {

        if (auth == null
                || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken
                || !(targetId instanceof Long id)
                || id <= 0
                || !"Document".equals(targetType)
                || !"read".equals(permission)) {
            return false;
        }

        boolean hasOperationPermission = auth.getAuthorities().stream()
            .anyMatch(a -> "document:read".equals(a.getAuthority()));
        if (!hasOperationPermission) {
            return false;
        }

        Optional<String> tenantId = scopes.authorizedTenantId(auth);
        if (tenantId.isEmpty()) {
            return false;
        }

        return documents.existsByIdAndTenantIdAndOwnerUsernameAndDeletedFalse(
            id, tenantId.get(), auth.getName());
    }
}
```

Với Spring Data JPA, ví dụ cần repository có phương thức derived query tương ứng và entity có thuộc tính `id`, `tenantId`, `ownerUsername`, `deleted`. `scopes.authorizedTenantId(auth)` **không phải API có sẵn của Spring Security**; đây là service nghiệp vụ do dự án tự viết để xác nhận tenant từ dữ liệu server, không chỉ đọc một header request.

Implementation kiểm tra:

1. Caller là người dùng có authentication hợp lệ, không phải anonymous.
2. ID là `Long` dương, `targetType`/`permission` thuộc tập cho phép.
3. Có authority `document:read`.
4. Có tenant đang được ủy quyền từ nguồn tin cậy.
5. Repository xác nhận bản ghi phù hợp **đồng thời** ID, tenant, owner và chưa xóa.

Khi bản ghi thật sự không tồn tại, thuộc tenant khác hoặc có owner khác, `existsBy...` đều trả `false`. Điều này tạo được một chính sách boolean **không công bố lý do** qua evaluator.

### Không được giấu lỗi database thành false tùy tiện

Nếu database ngắt kết nối, repository có thể ném `DataAccessException`. **Không** làm:

```java
try {
    return documents.existsByIdAndTenantIdAndOwnerUsernameAndDeletedFalse(
        id, tenantId, username);
} catch (Exception ignored) {
    return false; // KHÔNG NÊN: đánh đồng outage với "không tồn tại"
}
```

Cho phép bằng mặc định khi lỗi là sai nghiêm trọng; nhưng ép mọi lỗi thành `false` cũng che khuất outage, khiến vận hành và client hiểu nhầm rằng tài nguyên không tồn tại. Hãy để lỗi hạ tầng được xử lý bởi tầng quản lý lỗi phù hợp và trả mã 5xx an toàn. **Fail closed** nghĩa là không tiết lộ dữ liệu khi không thể xác minh quyền, không có nghĩa mọi exception đều phải trở thành HTTP 404.

### Nhận đối tượng từ client có vấn đề gì?

Nếu controller nhận `Document document` từ JSON rồi gọi `hasPermission(auth, document, "read")`, user có thể tự đặt `ownerUsername = "alice"` hoặc `tenantId`. Bản triển khai ở trên cố ý **không tin** những field này, mà dùng ID để tra lại quyền tại repository. Với một entity đã được load ở server, có thể dùng metadata tin cậy để tối ưu, nhưng vẫn phải quản lý ranh giới transaction và trạng thái entity.

Đừng bỏ qua rủi ro IDOR: người gọi gửi `documentId` hợp lệ **không chứng minh** có quyền trên document.

## 6. Nối PermissionEvaluator vào Method Security

Bật method authorization và đặt `PermissionEvaluator` vào `DefaultMethodSecurityExpressionHandler`. Với cấu hình Java hiện đại, có thể công bố bean handler bằng method `static` để được tạo sớm khi Spring Security thiết lập infrastructure:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator evaluator) {

        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }
}
```

Trong một ứng dụng, cần đảm bảo **chỉ cấu hình handler thích hợp** và kiểm tra nó có được sử dụng trong context. Với nhiều bean evaluator/handler, quy tắc resolution cần tường minh. `@EnableMethodSecurity` không phải luôn được bật chỉ bằng cách thêm dependency security.

Service:

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize("hasPermission(#documentId, 'Document', 'read')")
    public Document read(@P("documentId") Long documentId) {
        return documents.findById(documentId).orElseThrow();
    }
}
```

`@P("documentId")` cung cấp tên tham số rõ cho SpEL. Đoạn này minh họa cách gọi evaluator và có chủ ý **không phải giải pháp tối ưu cuối cùng**:

- Khi evaluator trả `false` vì **không tồn tại** hoặc **không có quyền**, method không chạy; với user đã xác thực, tầng HTTP thường trả **403**, không phân biệt nguyên nhân.
- Nếu evaluator trả `true` rồi dữ liệu/quyền thay đổi trước khi `findById` chạy, có thể gặp race (time-of-check/time-of-use).
- `existsBy...` rồi `findById` phát sinh hai truy vấn và truy vấn thứ hai thiếu ràng buộc tenant/owner. Trong hệ thống nhạy cảm, nên lấy dữ liệu bằng query có phạm vi quyền trong transaction phù hợp thay vì dựa vào check cũ.
- Nếu `DocumentRepository.findById` không thấy bản ghi, `orElseThrow()` không tham số ném `NoSuchElementException`. Mã HTTP nào được tạo từ exception này **không được suy đoán**; phải có cơ chế mapping rõ ràng.

**Ghi nhớ:** Không thể yêu cầu `PermissionEvaluator` vừa trả boolean để `@PreAuthorize` chặn trước method, vừa tự động trả `404` cho “not found” và `403` cho “forbidden”. Muốn phân biệt hai lý do, cần **một thiết kế phối hợp policy + lookup + error mapping**.

## 7. Hai cách xây dựng service theo chính sách lỗi

### Cách 1 — Che giấu tài nguyên ngoài phạm vi: truy vấn có điều kiện và 404

Đây thường là lựa chọn tốt cho tài nguyên nhạy cảm theo tenant/owner. Thay vì `findById(id)` rộng rồi tiết lộ một phần tồn tại, chỉ tra **những bản ghi người dùng được thấy**.

Ví dụ class service **trong ứng dụng Spring**:

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class PrivateDocumentService {
    private final DocumentRepository documents;
    private final TenantScopeService scopes;

    public PrivateDocumentService(
            DocumentRepository documents, TenantScopeService scopes) {
        this.documents = documents;
        this.scopes = scopes;
    }

    @PreAuthorize("hasAuthority('document:read')")
    public Document readVisible(Long id, Authentication auth) {
        if (id == null || id <= 0) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Document not found");
        }

        // Scope từ thông tin đã được xác minh phía server.
        String tenantId = scopes.authorizedTenantId(auth)
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Document not found"));

        return documents.findByIdAndTenantIdAndOwnerUsernameAndDeletedFalse(
            id, tenantId, auth.getName()
        ).orElseThrow(() -> new ResponseStatusException(
            HttpStatus.NOT_FOUND, "Document not found"));
    }
}
```

Lớp này giả định `auth` là `Authentication` do framework/controller **đã cung cấp**, không phải object do client có thể truyền từ JSON. Ở ứng dụng thật nên lấy identity từ security context hoặc injection được kiểm soát, thay vì để các caller không tin cậy tự dựng `Authentication`. Lời gọi phải đi qua Spring proxy để `@PreAuthorize` được thực thi.

Dù document thật không có hay có nhưng owner/tenant khác, truy vấn trả rỗng và API có thể phản hồi `404 Not Found` cùng một message. Người dùng có authority `document:read` nhưng không sở hữu document **không biết document có thật không** chỉ nhờ mã HTTP.

Lưu ý:

- Người **thiếu authority `document:read`** có thể bị `@PreAuthorize` chặn với `403`. Điều đó vẫn có thể phù hợp nếu chính sách chỉ che giấu sự tồn tại theo từng ID sau khi vượt qua permission thao tác chung.
- Nếu cần **mọi user không được phép** đều nhìn thấy cùng `404`, hãy thiết kế explicit entry policy/handler cho đúng route; không đổi toàn bộ 403 của ứng dụng thành 404 một cách bừa bãi.
- Query theo owner chỉ minh họa chính sách **chủ sở hữu**; ACL, group, chia sẻ và role admin phải được đưa vào query/policy nếu nghiệp vụ thực sự cho phép.
- Đối với write, cập nhật bằng `UPDATE ... WHERE id = ? AND tenant_id = ? AND owner_id = ?` hoặc locking/transaction phù hợp; quyền có thể thay đổi giữa check và write.

### Cách 2 — Cố ý phân biệt 404 và 403 khi tồn tại là công khai

Nếu sản phẩm cho phép công bố sự tồn tại resource, code có thể kiểm tra tồn tại trước rồi kiểm tra permission:

```java
public Document readPublicMetadataVisible(Long id, Authentication actor) {
    Document doc = documents.findById(id)
        .orElseThrow(() -> new ResponseStatusException(
            HttpStatus.NOT_FOUND, "Document not found"));

    if (!documentPolicy.canRead(actor, doc.getId())) {
        throw new org.springframework.security.access.AccessDeniedException(
            "Forbidden");
    }
    return doc;
}
```

Đây là **một phương thức minh họa** dùng các bean/biến của ứng dụng. Chính sách này **công bố sự tồn tại**: resource có thật nhưng không đủ quyền dẫn đến AccessDeniedException thay vì 404. Chỉ áp dụng khi product và security review xác nhận được phép lộ thông tin đó. `AccessDeniedException` có thể trở thành 403 ở HTTP qua Spring Security hoặc xử lý ngoại lệ khác đã cấu hình.

Nếu repository phục vụ multi-tenant private data, **không** dùng pattern `findById` rộng như trên chỉ để biết 403 hay 404. Nó cho kẻ ngoài khả năng dò ID. Thay vào đó, quay lại **Cách 1**.

### Nên chọn cách nào?

| Tiêu chí | Cách 1: chỉ truy vấn bản ghi được phép thấy | Cách 2: tra tồn tại rồi kiểm tra quyền |
| --- | --- | --- |
| Có tiết lộ tài nguyên ngoài phạm vi? | Thông thường không, nếu phản hồi nhất quán | Có thể có qua 403 so với 404 |
| Truy vấn | Một query theo ID + tenant + owner/ACL | Thường lookup trước rồi check |
| Hợp cho dữ liệu đa tenant riêng tư | **Ưu tiên** | Không phù hợp nếu tồn tại phải bí mật |
| Hợp cho tài nguyên có metadata công khai | Có thể dùng nhưng hạn chế thông tin | Có thể phù hợp |
| Tương tác với `@PreAuthorize("hasPermission(...)")` | Thường chọn coarse permission + scoped query thay vì evaluator riêng | Cần policy/error flow tường minh, tránh annotation nuốt mất phân biệt |
| Cần kiểm thử bên nào? | Không tồn tại **và** không có quyền cùng phản hồi | 403 vs 404 khác nhau là chủ ý và được cho phép |

## 8. Chọn mã HTTP ở đúng tầng, không trong evaluator

### Spring Security xử lý AccessDeniedException thế nào?

Ở ứng dụng Servlet, `ExceptionTranslationFilter` xử lý những `AuthenticationException` và `AccessDeniedException` phát sinh trong đường filter chain:

- Chưa được xác thực/anonymous: có thể kích hoạt `AuthenticationEntryPoint` để đăng nhập, trả 401 hoặc redirect.
- Đã xác thực nhưng bị từ chối: `AccessDeniedHandler` thường xử lý tình huống 403.
- `PermissionEvaluator` **không** phải nơi gọi `HttpServletResponse.sendError(...)` hoặc tự đặt status; nó có thể được dùng từ service **không có HTTP request**.

Ví dụ cấu hình handler minh họa cho một REST API đã xác thực:

```java
@Bean
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.exceptionHandling(errors -> errors
        .accessDeniedHandler((request, response, denied) -> {
            response.sendError(403, "Forbidden");
        })
        .authenticationEntryPoint((request, response, authError) -> {
            response.sendError(401, "Authentication required");
        })
    );
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").authenticated()
        .anyRequest().denyAll()
    );
    return http.build();
}
```

Đoạn trên là **config fragment** cần imports và cơ chế xác thực của ứng dụng; trong hệ thống có resource server, Basic authentication hoặc login riêng, một AuthenticationEntryPoint thích hợp có thể cần header `WWW-Authenticate` hay flow redirect theo chuẩn. Vì vậy không copy ví dụ để thay thế cơ chế xác thực hiện có mà chưa kiểm thử.

Nếu API chọn chính sách che giấu tài nguyên, nên xử lý `404` ở lookup scoped/exception translation cụ thể của domain. Tránh global handler chuyển **mọi** `AccessDeniedException` thành 404: nó có thể che lỗi vận hành, đổi nghĩa endpoint công khai, làm hỏng xử lý 401/403 hoặc khiến phản hồi giữa các route thiếu nhất quán.

### ResponseStatusException, @ControllerAdvice và ProblemDetail

Ở Spring MVC, có thể dùng `ResponseStatusException(HttpStatus.NOT_FOUND, "...")` hoặc một exception nghiệp vụ rồi mapping qua `@RestControllerAdvice` / `@ExceptionHandler`. Nếu theo RFC 9457 Problem Details, response body có thể chứa `type`, `title`, `status`, `detail`, `instance`. Nội dung bên ngoài phải **trung tính** với tài nguyên bị che giấu.

Ví dụ response đồng nhất cho cả not found và unauthorized-on-resource:

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Document not found"
}
```

Body trên là **ví dụ payload do ứng dụng thiết kế**, không phải output mặc định bảo đảm của mọi Spring Boot version. Không đưa `ownerUsername`, `tenantId`, `actualStatus = FORBIDDEN` hoặc stack trace vào body khi mục tiêu là conceal existence.

### Đừng để HTTP status phụ thuộc vào ngoại lệ ngoài dự tính

Các lỗi cần mapping có chủ đích:

- `NoSuchElementException` / `EntityNotFoundException`: không mặc định được chuyển thành 404 nếu không có handler.
- `DataAccessException` / timeout: không được nuốt để trả `false` hoặc 404.
- `IllegalArgumentException` do parse ID sai: validate sớm; trả `400` hoặc routing 404 theo hợp đồng API.
- `AccessDeniedException` từ method security: thường 403 đối với authenticated caller; khi không có HTTP layer, nó là exception của lời gọi Java.

Viết test qua stack thật: `MockMvc`, `SecurityFilterChain`, controller, service proxy và repository. Không đánh giá correctness chỉ từ việc unit test gọi `PermissionEvaluator.hasPermission(...)`.

## 9. Lộ sự tồn tại qua các kênh khác dù đều trả 404

Chỉ dùng cùng HTTP status chưa đủ. Nếu tài nguyên thật nhưng bị cấm và tài nguyên không tồn tại gây ra những tín hiệu khác nhau, người ngoài vẫn có thể dò ID.

Các kênh cần xem xét:

- **Response body:** khác `title`/`detail`/error code hoặc kích thước JSON.
- **Headers:** `ETag`, `Last-Modified`, `Content-Length`, thông tin tenant, cache key hoặc redirect khác biệt.
- **Timing:** nhánh tồn tại phải truy DB/ACL phức tạp còn nhánh không tồn tại trả ngay. Không phải lúc nào cũng cần thời gian tuyệt đối giống nhau, nhưng nên tránh sự khác biệt lớn và có thể lặp lại.
- **Rate limiting:** lỗi 403 và 404 bị tính vào hai bucket khác nhau làm lộ trạng thái; nên xem xét threat model.
- **List/count/search:** endpoint listing có thể để lộ ID hay số lượng tài nguyên mà endpoint detail cố che.
- **Log/trace hiển thị cho client:** correlation ID nên vô hại; không đưa lý do nội bộ vào public debug endpoint.
- **Cache/CDN:** public cache có thể phục vụ response dành cho principal khác; dùng cache scoping và HTTP caching headers phù hợp.

Không cần tuyên bố đã bảo vệ hoàn toàn chống enumeration chỉ vì cả hai nhánh trả `404`. Kiểm tra tổng thể endpoint, headers, body, query time và khả năng đo lặp lại trong điều kiện thực.

## 10. Ghi log và audit: giữ lý do bên trong, không lộ ra ngoài

Mặc dù API có thể trả cùng 404, hệ thống nội bộ vẫn cần biết tình huống để điều tra:

```text
Public: 404 "Document not found"
Internal event (không đưa ra ngoài):
  request_id: <correlation-id>
  actor: <safe identifier>
  resource_type: Document
  decision: DENY
  reason: CROSS_TENANT   (hoặc ABSENT, NO_ACL, SOFT_DELETED...)
```

Nội dung trên là **mẫu event minh họa**, không phải một cấu trúc Spring Security tự phát sinh. Thông tin audit cần tuân thủ quy tắc lưu trữ, quyền truy cập, retention và mức độ nhạy cảm; tránh log access token, session cookie, toàn bộ entity hoặc thông tin cá nhân không cần thiết.

Khi có sự cố database, ghi nhận `DEPENDENCY_ERROR` thay vì giả `ABSENT`. Internal metrics cần theo dõi 5xx, permission denial, unusual sequences of ID probing và audit của thao tác quản trị. Việc nêu lý do chi tiết ra client nên có whitelist và chỉ áp dụng khi đối tượng đã được phép biết nội dung đó.

## 11. Java 17 chạy độc lập: cùng trạng thái bên ngoài, khác lý do bên trong

Chương trình dưới đây mô phỏng một kho tài liệu và hai chính sách phản hồi. Nó là **Java thuần**, không có Spring Security, database hay HTTP server; mục đích là so sánh việc che giấu tồn tại (`404` cho cả missing và forbidden) với phản hồi chi tiết (`403` khi resource có thật nhưng không có quyền).

Lưu mã dưới tên `ResourceVisibilityDemo.java`:

```java
import java.util.Map;
import java.util.Set;

public class ResourceVisibilityDemo {

    record Actor(String name, String tenant, Set<String> authorities) {}
    record Document(long id, String tenant, String owner) {}

    enum Decision {
        ALLOW, MISSING, FORBIDDEN, UNAUTHENTICATED
    }

    static Decision decide(
            Actor actor, long id, Map<Long, Document> documents) {
        if (actor == null) {
            return Decision.UNAUTHENTICATED;
        }

        Document document = documents.get(id);
        if (document == null) {
            return Decision.MISSING;
        }

        boolean permitted = actor.authorities().contains("document:read")
            && actor.tenant().equals(document.tenant())
            && actor.name().equals(document.owner());

        return permitted ? Decision.ALLOW : Decision.FORBIDDEN;
    }

    static String concealedResponse(Decision decision) {
        return switch (decision) {
            case ALLOW -> "200 OK";
            case UNAUTHENTICATED -> "401 Unauthorized";
            case MISSING, FORBIDDEN -> "404 Not Found";
        };
    }

    static String explicitResponse(Decision decision) {
        return switch (decision) {
            case ALLOW -> "200 OK";
            case UNAUTHENTICATED -> "401 Unauthorized";
            case MISSING -> "404 Not Found";
            case FORBIDDEN -> "403 Forbidden";
        };
    }

    static void printCase(String label, Decision decision) {
        System.out.println(label + ": " + decision
            + " | conceal=" + concealedResponse(decision)
            + " | explicit=" + explicitResponse(decision));
    }

    public static void main(String[] args) {
        Map<Long, Document> documents = Map.of(
            42L, new Document(42L, "tenant-a", "alice"),
            77L, new Document(77L, "tenant-b", "carol")
        );

        Actor alice = new Actor("alice", "tenant-a",
            Set.of("document:read"));
        Actor bob = new Actor("bob", "tenant-a",
            Set.of("document:read"));

        printCase("Alice own", decide(alice, 42L, documents));
        printCase("Bob other owner", decide(bob, 42L, documents));
        printCase("Alice missing", decide(alice, 99L, documents));
        printCase("Alice other tenant", decide(alice, 77L, documents));
        printCase("Anonymous", decide(null, 42L, documents));
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac ResourceVisibilityDemo.java
java ResourceVisibilityDemo
```

Stdout chính xác:

```text
Alice own: ALLOW | conceal=200 OK | explicit=200 OK
Bob other owner: FORBIDDEN | conceal=404 Not Found | explicit=403 Forbidden
Alice missing: MISSING | conceal=404 Not Found | explicit=404 Not Found
Alice other tenant: FORBIDDEN | conceal=404 Not Found | explicit=403 Forbidden
Anonymous: UNAUTHENTICATED | conceal=401 Unauthorized | explicit=401 Unauthorized
```

Ở ví dụ này, `Decision` là trạng thái **nội bộ** giàu thông tin; hai hàm `concealedResponse` và `explicitResponse` mô phỏng các hợp đồng HTTP **khác nhau**. Nếu thay bằng `PermissionEvaluator`, kết quả kiểm tra quyền sẽ là boolean; chỉ nhìn `false` không phân biệt được missing hay forbidden.

Hàm `decide` tra cứu toàn bộ `Map` trước khi kiểm tra owner/tenant để minh họa sự phân biệt. **Đừng sao chép thứ tự đó vào API dữ liệu riêng tư** nếu chính sách yêu cầu conceal existence: ưu tiên truy vấn scoped và không trả lý do nội bộ ra client.

## 12. Ma trận kiểm thử bắt buộc

### Test evaluator

| Case | Kết quả `hasPermission` kỳ vọng | Điều cần kiểm tra |
| --- | --- | --- |
| Tài liệu của user, cùng tenant, có authority | `true` | Repository scoped query đúng |
| Tài liệu không tồn tại | `false` | Không ném lỗi null |
| Tài liệu tồn tại nhưng tenant khác | `false` | Không lộ owner/tenant qua response |
| Cùng tenant nhưng owner khác, không có ACL | `false` | Không chỉ dựa vào role |
| Thiếu `document:read` | `false` | Không chạy query tốn kém nếu có thể short-circuit |
| `Authentication` null/anonymous | `false` | Không chấp nhận anonymous vì `isAuthenticated` riêng lẻ |
| ID null, âm, sai kiểu | `false` | Không ClassCastException ngoài dự tính |
| `targetType` lạ hoặc permission không được hỗ trợ | `false` | Không tự tin vào chuỗi type/action bất kỳ |
| DB outage/timeout | **Exception** để layer trên xử lý an toàn | Không nhầm outage thành “not found” |

### Test API có chủ đích che giấu

| Danh tính và ID | Nội bộ | HTTP kỳ vọng |
| --- | --- | --- |
| User hợp lệ, ID được xem | ALLOW | 200 |
| User hợp lệ, ID không tồn tại | ABSENT | 404 |
| User hợp lệ, ID bị cấm (owner khác) | DENY | 404, cùng body/header contract với case absent |
| User hợp lệ, ID tenant khác | DENY | 404, không lộ tenant |
| User chưa đăng nhập | UNAUTHENTICATED | 401 hoặc auth flow được thiết kế |
| Thiếu authority route-level | DENY | 403 theo chính sách bảo vệ route |
| Database lỗi | DEPENDENCY_ERROR | 5xx, không lộ stack trace |

Với chính sách **phân biệt** lỗi, hai case “không tồn tại” và “bị cấm” có thể kỳ vọng 404/403 khác nhau. Test phải mô tả vì sao điều đó được cho phép.

### Test tích hợp

- Dùng `MockMvc` đi qua `SecurityFilterChain` và controller, không chỉ unit test evaluator.
- Bật `@EnableMethodSecurity`, lấy service từ Spring context. Tự gọi `this.securedMethod()` hoặc dùng `new Service()` có thể bypass AOP proxy.
- Ghi rõ hành vi khi `@PreAuthorize("hasPermission(...)")` từ chối: method không chạy; với người đã xác thực, HTTP thường là `403`. Nếu API chủ đích cần `404` cho cả thiếu quyền tài nguyên, test luồng **scoped lookup** thay vì kỳ vọng evaluator tự chọn response.
- Test body, content-type, headers, cache behavior và không để thông tin tồn tại lộ qua response metadata.
- Test ID có định dạng hợp lệ nhưng không có thật, ID quá lớn, null, input Unicode/encoding, soft delete, concurrent delete, revoked access và thay đổi ACL/tenant.
- Nếu quyền thay đổi giữa lần evaluator query và lần service đọc/ghi, dùng transaction/locking/scoped query phù hợp để không trả dữ liệu trái quyền.
- Test `DataAccessException` thật để chắc chắn không biến sự cố thành false/404; bảo đảm không có data leak.
- Test lỗi từ tầng method security trong cả HTTP và non-HTTP caller; non-HTTP code phải xử lý exception phân quyền theo hợp đồng riêng.

## 13. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ `hasPermission` trả false thì tự có 404 | Method security thường tạo access denied, không phải not found | Thiết kế response policy ở service/controller |
| Trả `true` nếu không tìm được document để tránh 403 | Fail-open, có thể đọc/ghi trái quyền | Missing phải từ chối; không bypass policy |
| Mọi lỗi database đều catch rồi return false | Outage bị hiểu thành 404/403, khó phát hiện | Fail closed và xử lý lỗi hạ tầng thành 5xx |
| Tự tạo `AccessDeniedException` ngay trong evaluator khi missing | Trộn boolean decision với error mapping; phá hợp đồng | Return false, dùng tầng cao hơn khi cần chính sách phân biệt |
| Tra `findById` rồi trả 403/404 khác nhau cho tài nguyên private | Lộ sự tồn tại ID cho người ngoài | Query scoped, trả 404 đồng nhất |
| Chỉ dùng `@PreAuthorize` rồi query `findById` rộng sau đó | Race/TOCTOU, query thứ hai có thể không còn được scope | Ràng buộc truy vấn thật theo quyền và transaction |
| Dùng owner/tenant do client gửi trong domain object | Người dùng giả mạo trường để được quyền | Xác minh bằng server/database |
| Trả về toàn bộ entity từ `@PostAuthorize` để chặn sau khi ghi | Side effect có thể đã commit trước khi deny | Kiểm tra quyền trước thao tác ghi |
| Đổi toàn bộ AccessDeniedException thành 404 | Mất ý nghĩa permission ở các endpoint khác | Mask có chọn lọc theo tài nguyên/policy |
| Body 404 nói “document exists but private” | Rò rỉ dù status là 404 | Dùng message và metadata trung tính |
| Cache shared response giữa hai user/tenant | Có thể lộ dữ liệu hoặc tín hiệu tồn tại | Partition cache theo principal/tenant và kiểm tra authorization |
| Chỉ kiểm tra HTTP status, bỏ qua audit/DB | Test không phát hiện side effect trái quyền | Assert DB, query, event, response, log |
| Log chi tiết lý do deny ra công khai | Lộ chủ sở hữu/tenant/token | Tách audit nội bộ và API error |

## 14. Checklist thiết kế

1. **Tài nguyên có được phép tiết lộ sự tồn tại không?** Nếu không, ưu tiên chính sách scoped lookup + 404 trung tính.
2. **PermissionEvaluator có đang trả boolean thuần không?** `false` phải có nghĩa không cấp quyền, không cố mang thông tin HTTP.
3. **Đã phân biệt thiếu xác thực, thiếu quyền và missing chưa?** `401` khác `403` và `404`.
4. **Đã định nghĩa đường xử lý database failure chưa?** Không return true, không dùng 404 che outage.
5. **Owner/tenant/ACL có đến từ nguồn đáng tin không?** Không tin ID, header, form, JSON hay entity do client gửi.
6. **Có query scoped và nhất quán transaction không?** Đặc biệt quan trọng khi cập nhật tài nguyên.
7. **Cấu hình `@EnableMethodSecurity` và handler đúng chưa?** Unit test evaluator không chứng minh annotation được thực thi.
8. **403/404 có nhất quán trong cùng nhóm tài nguyên không?** Bao gồm body, headers, cache và side channels.
9. **Có logging/audit nội bộ phù hợp không?** Giữ lý do riêng để điều tra, không để lộ ra client.
10. **Đã kiểm thử cả trường hợp bị cấm lẫn không tồn tại chưa?** So sánh chúng trực tiếp thay vì chỉ test happy path.

**Kết luận:** `PermissionEvaluator` trả lời "**người dùng này có quyền trên đối tượng/ID này không?**" bằng `true/false`. Nó **không** trả lời trực tiếp "**API nên trả 403 hay 404?**". Để tránh lộ sự tồn tại tài nguyên, hãy thiết kế error contract có chủ đích, ưu tiên truy vấn giới hạn theo quyền trên dữ liệu thật, fail closed khi kiểm tra quyền và xử lý lỗi hạ tầng riêng.

## Tài liệu tham khảo chính thức

- [Spring Security — PermissionEvaluator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionEvaluator.html): hai overload, kiểu trả boolean và khuyến nghị với target null.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `hasPermission`, `@EnableMethodSecurity`, `@PreAuthorize`, expression handler, từ chối trước method.
- [Spring Security — Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html): bộ lọc bảo mật, xử lý authentication/access denied theo request.
- [Spring Security — ExceptionTranslationFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html): chuyển `AccessDeniedException` / `AuthenticationException` thành xử lý phía HTTP.
- [Spring Framework — ResponseStatusException](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): tạo phản hồi lỗi có status rõ ràng ở Spring MVC.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): ý nghĩa 401, 403, 404 và khả năng dùng 404 để che giấu tài nguyên bị cấm.
