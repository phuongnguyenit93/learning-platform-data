# DTO, ánh xạ dữ liệu và nguy cơ làm mất lớp kiểm tra quyền

> **Module:** Spring Security - authorization  
> **Nhóm:** Kiểm tra sau phương thức  
> **Mục tiêu:** Hiểu ranh giới giữa entity, DTO, projection, mapper và method-security interceptor; biết chính xác object nào được kiểm tra bởi `@PostAuthorize`/`returnObject`; nhận ra tình huống mất metadata owner/tenant/ACL hoặc bảo mật của getter sau chuyển đổi dữ liệu; thiết kế luồng **authorize trước khi map/serialize/trả kết quả**, và kiểm thử chống IDOR/BOLA, lộ field nhạy cảm, bypass do proxy và side effect.

## 1. Bài toán: DTO chỉ chứa dữ liệu muốn trả về, còn quyền phụ thuộc dữ liệu không có trong DTO

Giả sử database có entity:

```java
public class Document {
    private Long id;
    private String title;
    private String content;
    private String ownerUserId;
    private String tenantId;
    private boolean confidential;
    // getters và business methods...
}
```

API không muốn để lộ `ownerUserId`, `tenantId` trong response JSON, nên mapper chỉ xuất:

```java
public record DocumentDto(Long id, String title, String content) {}
```

Một service ban đầu dùng `@PostAuthorize`:

```java
@PostAuthorize("returnObject.ownerUserId == authentication.name")
public Document readEntity(Long id) {
    return repository.findById(id).orElseThrow();
}
```

Sau refactor, lập trình viên chuyển return type sang DTO:

```java
@PostAuthorize("returnObject.ownerUserId == authentication.name")
public DocumentDto readDto(Long id) {
    Document entity = repository.findById(id).orElseThrow();
    return mapper.toDto(entity);
}
```

Vấn đề: **`returnObject` hiện là `DocumentDto`**, không còn là `Document`. Nó không có property `ownerUserId`. Biểu thức trên có thể phát sinh lỗi đánh giá SpEL vì property không tồn tại; không được giả định Spring âm thầm bỏ qua nó và tự cho phép. Cách “chữa nhanh” bằng việc xóa annotation hoặc chỉ thay bằng `isAuthenticated()` mới tạo lỗ hổng **IDOR/BOLA**, vì caller có thể đoán ID của tài liệu khác.

**Cốt lõi của chủ đề:** chuyển đổi entity → DTO không chỉ là quyết định presentation. Nếu authorization dựa vào thuộc tính của object trả về, **kiểu và nội dung return object là một phần hợp đồng bảo mật**. Bất kỳ thay đổi DTO, mapper, projection hay service boundary nào cũng cần review chính sách quyền tương ứng.

## 2. Thứ tự thực thi quyết định điều gì được nhìn thấy

```text
Request / caller
       |
       v
Spring service proxy
       |
       v
@PreAuthorize (nếu có)
       |
       +--- DENY: method body không chạy
       |
       v
Service method body
   1. Repository tải Document
   2. Mapper tạo DocumentDto
   3. Có thể log/cache/event/side effect
   4. Method trả DocumentDto
       |
       v
@PostAuthorize trên returnObject = DocumentDto
       |
       +--- DENY: không trả DTO bình thường cho caller
       |
       v
Controller / JSON serializer / GraphQL...
       |
       v
Client nhận kết quả
```

Một số nguyên tắc:
- `@PostAuthorize` kiểm tra **giá trị return của method thực sự được Spring AOP chặn**, không tự động quay lại entity gốc mà mapper đã bỏ.
- Mapper đã chạy **trước** `@PostAuthorize` nếu mapper ở trong method body.
- Hậu kiểm từ chối có thể ngăn return value tới caller, **nhưng không undo** việc mapper/log/cache/external service đã làm.
- Cùng object có thể đi qua nhiều chặng: JPA entity → projection → domain model → DTO → HTTP response. Chốt quyền ở đâu phải được định nghĩa rõ.
- Quyền đọc **cả document** và quyền xem **từng field** là hai quyết định khác nhau. `@PostAuthorize` owner-only không tự lọc dữ liệu nhạy cảm khỏi DTO được phép.

Với method ghi DB, dùng `@PostAuthorize` làm chốt sở hữu chính là nguy hiểm vì body đã thực hiện mutation. Mẫu đúng thường là **tải entity → kiểm tra policy → thay đổi hoặc map → trả kết quả**.

## 3. Spring Security đánh giá returnObject ra sao?

Bật method security:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {}
```

Trong Spring Security Servlet 6.5, `@PostAuthorize` được xử lý bởi `AuthorizationManagerAfterMethodInterceptor` và `PostAuthorizeAuthorizationManager`. Khi service method đã trả kết quả, biểu thức SpEL được đánh giá với `returnObject` chính là đối tượng trả về. Nếu không được phép, thường phát sinh `AccessDeniedException`; ở HTTP, exception handling phù hợp thường trả 403 cho actor đã xác thực.

Tài liệu chính thức minh họa:

```java
@PreAuthorize("hasAuthority('account:read')")
@PostAuthorize("returnObject.owner == authentication.name")
public Account readAccount(Long id) {
    return repository.findById(id).orElseThrow();
}
```

Ở đây `returnObject` là `Account`, nên `owner` phải được giải quyết trên kiểu Account hoặc accessor tương ứng. Nếu chuyển return type thành DTO, hãy **xác minh lại biểu thức và policy**. Việc thay đổi signature có thể thay đổi semantics hậu kiểm, ngay cả khi tên method, route và authentication không thay đổi.

**Không mặc định `@EnableMethodSecurity` đang bật:** Spring Boot Security starter không tự kích hoạt method security. Không mặc định một method có annotation sẽ được chặn nếu nó bị gọi qua `this.method()`, object tạo bằng `new` hoặc đường gọi không qua proxy phù hợp.

## 4. Khi mapper bỏ trường kiểm tra quyền: ba kết cục khác nhau

Giả sử code cũ:

```java
@PostAuthorize("returnObject.ownerId == authentication.name")
public DocumentEntity getDocument(long id) { ... }
```

Sau migration, mapper tạo:

```java
public record DocumentDto(long id, String title, String content) {}
```

Có ba hướng xử lý:

| Hướng xử lý | Kết quả | Đánh giá |
| --- | --- | --- |
| Giữ nguyên `@PostAuthorize` truy cập `ownerId` không tồn tại | Có thể lỗi SpEL tại hậu kiểm | Không phải success; phải sửa hợp đồng method/policy |
| Bỏ `@PostAuthorize` “để API chạy lại” | Endpoint có nguy cơ trả mọi document có ID hợp lệ | **Không an toàn** nếu thiếu chốt khác |
| Dùng `@PostAuthorize("isAuthenticated()")` | Chỉ kiểm tra đã login, bỏ ownership | **Không đủ** cho tài liệu private |
| Giữ metadata xác thực trong một return type có thể kiểm tra | Hậu kiểm có dữ liệu cần thiết | Có thể đúng nhưng phải kiểm soát serialization và dữ liệu gốc |
| Chuyển object-policy vào service **sau khi tải entity và trước khi map** | Không cần expose metadata nhạy cảm trong DTO | **Thường dễ kiểm chứng và an toàn nhất** |
| Dùng secured loader qua bean proxy rồi mới map | `@PostAuthorize` đánh giá entity/secured view trước mapper | Khả thi nếu bảo đảm mọi đường gọi qua loader có proxy |

**Lưu ý:** thiếu property trên DTO không được diễn giải là “Spring Security fail open”; rủi ro thực tế thường là **con người bỏ/chuyển sai checkpoint** hoặc **mapper làm mất dữ liệu cần cho biểu thức** rồi chọn cách sửa quá rộng. Test phải phát hiện thay đổi này trước khi triển khai.

## 5. Giải pháp ưu tiên: kiểm tra entity thật trước khi map sang DTO

Ví dụ service cho read-only:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentQueryService {
    private final DocumentRepository repository;
    private final DocumentPolicy policy;
    private final ActorResolver actors;
    private final DocumentMapper mapper;

    public DocumentQueryService(DocumentRepository repository,
                                DocumentPolicy policy,
                                ActorResolver actors,
                                DocumentMapper mapper) {
        this.repository = repository;
        this.policy = policy;
        this.actors = actors;
        this.mapper = mapper;
    }

    @PreAuthorize("hasAuthority('document:read')")
    @Transactional(readOnly = true)
    public DocumentDto getDocument(long id) {
        Actor actor = actors.requireAuthenticatedActor();

        Document document = repository
            .findByIdAndTenantId(id, actor.activeTenantId())
            .orElseThrow(DocumentNotFoundException::new);

        policy.requireCanRead(actor, document);

        // Chỉ chạy mapper SAU khi quyền trên entity được xác minh.
        return mapper.toDto(document);
    }
}
```

**Snippet tích hợp, không phải chương trình `javac` độc lập:** `DocumentRepository`, `DocumentPolicy`, `ActorResolver`, `Document`, `DocumentMapper`, `DocumentDto`, `Actor` và exception phải được ứng dụng định nghĩa. `@Transactional(readOnly=true)` không tự enforce security, mà giúp quản lý transaction/persistence context theo thiết kế.

Trình tự:
1. `@PreAuthorize` kiểm tra quyền chức năng.
2. `ActorResolver` lấy canonical user ID, tenant từ Authentication/membership tin cậy.
3. Repository hạn chế query theo tenant đã xác minh.
4. `policy.requireCanRead` kiểm tra owner/ACL/delegation/state trên entity thật.
5. **Chỉ sau ALLOW**, mapper tạo response DTO với đúng các fields được phép.
6. Framework mới serialize DTO ra HTTP response.

Mẫu này giữ owner/tenant khỏi DTO công khai mà **không làm mất thông tin cần cho authorization**. Nó cũng tránh việc map nội dung nhạy cảm và log DTO trước khi có quyết định owner.

Một nhược điểm cần quản lý: khi đọc object rồi quyết định trong service, đó không còn là `@PostAuthorize` trên DTO. Đây **không phải mất bảo mật**, miễn policy thực sự chạy trên mọi đường gọi và transaction/proxy boundaries đúng. Chọn nơi enforce theo quyền dữ liệu và kiến trúc, không ép mọi trường hợp phải giữ annotation.

## 6. Phương án vẫn dùng @PostAuthorize: return type có metadata tin cậy

Trong một số dự án muốn giữ hậu kiểm declarative, có thể thiết kế return type chứa metadata dùng nội bộ cho authorization:

```java
import com.fasterxml.jackson.annotation.JsonIgnore;

public record SecuredDocumentView(
    long id,
    String title,
    String content,
    @JsonIgnore String ownerUserId,
    @JsonIgnore String tenantId
) {}
```

Service:

```java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize(
    "returnObject != null and "
    + "@documentAccess.canRead(authentication, returnObject)"
)
public SecuredDocumentView read(long id) {
    Document document = repository.findById(id).orElseThrow();
    return mapper.toSecuredView(document);
}
```

Bean policy:

```java
@Component("documentAccess")
public class DocumentAccess {
    private final ActorResolver actorResolver;

    public DocumentAccess(ActorResolver actorResolver) {
        this.actorResolver = actorResolver;
    }

    public boolean canRead(Authentication auth,
                           SecuredDocumentView dto) {
        if (auth == null || dto == null || !auth.isAuthenticated()) {
            return false;
        }
        Actor actor = actorResolver.requireActor(auth);
        if (!actor.activeTenantId().equals(dto.tenantId())) {
            return false;
        }
        return actor.id().equals(dto.ownerUserId());
    }
}
```

Đây là **ba snippet tích hợp** cần Spring Security, Jackson và types dự án. `@JsonIgnore` là annotation serialization của Jackson; nó có thể giấu property khỏi JSON trong cấu hình tương ứng, **nhưng không phải security boundary phổ quát**. DTO vẫn giữ ownerUserId/tenantId trong memory và các serializer/loggers khác có thể hành xử khác. Phải test chính xác JSON cuối cùng.

Điều kiện để cách này an toàn:
- `mapper.toSecuredView` phải gán owner/tenant **từ entity tin cậy**, không từ HTTP request body.
- Method phải trả chính `SecuredDocumentView` qua proxy có `@PostAuthorize`.
- Bean `documentAccess` phải xác minh tenant, ACL/state theo policy thật.
- DTO không được log/cache/serialize trước khi hậu kiểm.
- JSON phải không phát tán owner/tenant nếu đây là thông tin không nên xuất.
- Đổi mapper hoặc DTO field name phải có regression test.

**Khi không cần hậu kiểm trên DTO, giải pháp kiểm tra trước map thường dễ audit hơn.**

## 7. Hậu kiểm entity ở service riêng, sau đó mới map: tách bean đúng ranh giới

Một kiến trúc khác:

```java
@Service
public class SecuredDocumentLoader {
    private final DocumentRepository repository;

    @PreAuthorize("hasAuthority('document:read')")
    @PostAuthorize(
        "returnObject != null and "
        + "@documentPolicy.canRead(authentication, returnObject)"
    )
    public Document load(long id) {
        return repository.findById(id)
            .orElseThrow(DocumentNotFoundException::new);
    }
}
```

Facade DTO:

```java
@Service
public class DocumentFacade {
    private final SecuredDocumentLoader loader;
    private final DocumentMapper mapper;

    public DocumentFacade(SecuredDocumentLoader loader,
                          DocumentMapper mapper) {
        this.loader = loader;
        this.mapper = mapper;
    }

    public DocumentDto read(long id) {
        Document authorized = loader.load(id); // Qua bean proxy.
        return mapper.toDto(authorized);
    }
}
```

**Đây là snippets kiến trúc**, không phải file Java hoàn chỉnh (cần constructor/DI cho loader, domain types, imports, transaction semantics). Mục đích:
- `SecuredDocumentLoader.load` trả `Document`, để `@PostAuthorize` nhìn thấy owner/tenant thật.
- Lời gọi `loader.load` đi qua Spring bean proxy; nếu DENY, facade không nhận entity để map.
- DTO công khai không cần giữ metadata owner.

**Ranh giới cần bảo đảm:**
- Không tự gọi `this.load(...)` trong cùng class, vì self-invocation có thể bypass Spring AOP.
- Không tạo loader bằng `new`; inject bean thật.
- Không có controller/mapper khác gọi thẳng repository để bỏ qua loader.
- Chỉ expose các trường DTO được phép; hậu kiểm object-level không phải field sanitizer.
- Với JPA lazy relation, mapping sau load có thể cần transaction còn sống; nếu không, hãy trả **secured view đã materialize** và kiểm tra theo policy trước khi map sang public DTO.
- Nếu bean loader trả managed entity và caller có thể mutate, cần giữ contract read-only và tránh cho caller lấy entity rồi ghi ngoài policy.

Đây là một mẫu tốt khi thực sự muốn **hậu kiểm entity** trong method security, nhưng không nhất thiết tối ưu hơn policy trong service. Điều kiện đầu tiên là **không có đường bypass**.

## 8. @PostAuthorize kiểm tra cái gì nếu service trả Optional, List hoặc Page?

Không phải mọi return type đều có cùng semantics:

| Return type | `returnObject` thực chất | Rủi ro |
| --- | --- | --- |
| `Document` | Một entity | Owner/tenant có thể lazy-loaded, metadata từ DB |
| `DocumentDto` | DTO sau mapper | Metadata cần check có thể đã bị bỏ |
| `Optional<Document>` | Có thể là wrapper hoặc result được handler đặc thù xử lý tùy version | Không đoán được `returnObject.ownerId` sẽ resolve đúng |
| `List<DocumentDto>` | Một collection | `returnObject.ownerId` không phải property của từng phần tử |
| `Page<DocumentDto>` | Page chứa items/metadata | Không dùng `@PostFilter` như thuốc chữa pagination nếu nguồn không scoped |
| `Stream<Document>` | Có thể lazy/deferred | Việc load/serialize có thể xảy ra sau boundary dự kiến |
| `ResponseEntity<DocumentDto>` | Wrapper HTTP và body | Biểu thức cần hiểu wrapper, không mặc định là body |
| `byte[]` / file stream | Payload/stream đã hình thành hoặc đang stream | Ownership không có trong return value |

**Không xây policy bằng giả định về shape không được test.** Trong nhiều trường hợp, policy nên kiểm tra object trước khi mapper làm mất metadata, rồi trả đúng contract API.

Đối với list:
- `@PostAuthorize` quyết định một lần trên returnObject toàn list, không tự xét từng item như object đơn.
- `@PostFilter("filterObject.ownerId == authentication.name")` xét từng item với các collection/array/Map/Stream hỗ trợ.
- Nhưng post-filter sau DB read có thể đắt, sai count/pagination và gây rủi ro dữ liệu đã được đưa vào memory/log/cache.
- Với list và export lớn, **truy vấn theo tenant, actor và ACL ngay ở DB** thường tốt hơn.

## 9. @PostFilter khi DTO không còn ownerId

Ví dụ ban đầu:

```java
@PostFilter("filterObject.ownerId == authentication.name")
public List<DocumentEntity> listDocuments() {
    return repository.findAll();
}
```

Sau khi chuyển sang:

```java
@PostFilter("filterObject.ownerId == authentication.name")
public List<DocumentDto> listDocuments() {
    return repository.findAll().stream()
        .map(mapper::toDto)
        .toList();
}
```

Lỗi tương tự: `filterObject` hiện là `DocumentDto`; nếu DTO không có ownerId, biểu thức không còn hợp lệ. Đừng bỏ filter để “hết lỗi” và trả toàn bộ danh sách.

Các cách tốt hơn:
1. Query chỉ lấy tài liệu actor có quyền, với tenant/ACL scoping trong DB, rồi map.
2. Lọc collection các **entity/secured view** theo policy **trước khi map** (chỉ phù hợp tập nhỏ và khi hiệu năng chấp nhận).
3. Dùng một bean policy `@docPolicy.canRead(authentication, filterObject)` nếu mỗi DTO còn đủ metadata tin cậy, nhưng vẫn cân nhắc hiệu năng.
4. Dùng service guarded loader/facade có test toàn luồng.

**Đừng nhầm `@PostFilter` với `@PreFilter`**: một cái lọc output sau method, một cái lọc input collection trước body. Cả hai không tự biết owner thật nếu phần tử là DTO do caller tự khai.

## 10. Tái cấu trúc DTO có thể làm mất lớp security của getter

Giả sử domain object có method:

```java
public class AccountView {
    private final String email;

    @PreAuthorize("hasAuthority('account:email:read')")
    public String getEmail() {
        return email;
    }
}
```

Lập trình viên tạo DTO:

```java
public record AccountDto(long id, String email) {}
```

Nếu mapper gọi `entity.getEmail()` từ đường không đi qua advice, hoặc sử dụng field access trong mapping, rồi điền email vào DTO, **annotation trên getter của entity không tự chuyển sang accessor của DTO**. Jackson serialize `AccountDto.email()` bình thường; nó không tự nhìn lại annotation của `AccountView.getEmail()`.

Cần phân biệt:
- `@PostAuthorize` trên method trả entity/DTO là chốt **toàn kết quả**.
- Method-security annotation trên getter là chốt **lời gọi getter cụ thể**, chỉ có hiệu lực khi đúng proxy/advice được thực thi.
- DTO thường là plain record/bean không có security proxy mặc định.
- Mapper (MapStruct, ModelMapper, manual mapping, reflection...) không tự đảm bảo gọi đúng authorization checkpoint trừ khi bạn thiết kế và kiểm thử như vậy.

**Anti-pattern:** tin rằng một @PreAuthorize trên entity getter hoặc repository method sẽ “theo dữ liệu” qua mọi DTO, JSON, cache. Security annotations bảo vệ **method invocations** theo các điều kiện runtime, không phải nhãn taint bất biến đi theo từng byte dữ liệu.

## 11. @AuthorizeReturnObject khác @PostAuthorize

Spring Security 6.5 có `@AuthorizeReturnObject` để proxy return object và áp method-security annotations cho các method trên object đó. Ví dụ official architecture cho phép bảo vệ getter của return object:

```java
public class User {
    private String email;

    @PreAuthorize("hasAuthority('user:email:read')")
    public String getEmail() {
        return email;
    }
}
```

Một bean trả User có thể dùng:

```java
@AuthorizeReturnObject
public User findUser(long id) {
    return repository.loadUser(id);
}
```

Hai ý tưởng **không tương đương**:
- `@PostAuthorize("...returnObject...")`: một hậu kiểm sau method, có thể DENY toàn return value.
- `@AuthorizeReturnObject`: cố gắng proxy object trả về để bảo vệ lời gọi các methods/getters của object theo annotations trên các methods đó.

Nếu bạn chuyển từ `User` sang `UserDto` không có protected getter hoặc mapper copy email vào plain DTO, **không được giả định proxy của entity hoặc annotations cũ vẫn bảo vệ serialization của DTO**.

Với `@AuthorizeReturnObject`, cần đối chiếu version, proxyable types, final/record constraints, nested return types, AOT runtime hints và JSON serialization; docs Spring Security lưu ý khả năng framework cố proxy cả value types như `String`/`Integer` khi áp annotation quá rộng ở class level. Không gắn `@AuthorizeReturnObject` bừa bãi cho mọi DTO rồi nghĩ đã bảo mật field-level.

Đối với API nhạy cảm, thường dễ audit hơn khi **service kiểm tra policy và tạo DTO chỉ gồm các field được phép** trước khi serializer thấy nó.

## 12. Serialize ra JSON không phải bước phân quyền

Một DTO:

```java
public record UserProfileDto(
    String name,
    String email,
    String phone,
    String nationalId
) {}
```

Có thể actor được quyền xem profile cơ bản nhưng **không** được xem nationalId hoặc phone. Một `@PostAuthorize` owner-only cho phép **toàn bộ DTO**, không tự cắt các fields không được phép.

Nên tách:
- **Object-level authorization:** actor có quyền xem User 42 không?
- **Field-level authorization:** actor có quyền xem email, phone, national ID của User 42 không?
- **Serialization allowlist:** JSON chỉ xuất fields đã được policy cho phép.
- **Response shaping:** role/relationship khác nhau có thể cần DTO khác nhau.

Ví dụ:

```java
public record PublicProfileDto(String displayName) {}

public record OwnProfileDto(
    String displayName,
    String email,
    String phone
) {}
```

Sau khi service policy xác định relationship và authority đáng tin, mapper chọn DTO phù hợp. Không nhận `?includeSensitive=true` từ client rồi tự cho tất cả fields; query flag chỉ biểu thị **ý định**, phải có quyền tương ứng.

**@JsonIgnore, @JsonView và Jackson filters có thể giúp serialize đúng shape**, nhưng chúng không thay thế source-of-truth authorization. Phải test JSON và cả export/GraphQL endpoints vì một DTO có thể được serialize qua nhiều cơ chế.

## 13. Một phương án DTO tối thiểu và chính sách tối thiểu

Thiết kế đáp ứng nguyên tắc giảm dữ liệu:

```text
Document entity:
    id, ownerId, tenantId, title, content, secretMetadata, status

DocumentPolicy:
    canRead(actor, document)
    canReadSecretMetadata(actor, document)

Public DocumentDto:
    id, title, permittedContent
```

Mẫu service:

```java
@PreAuthorize("hasAuthority('document:read')")
@Transactional(readOnly = true)
public DocumentDto read(long documentId) {
    Actor actor = actorResolver.requireAuthenticatedActor();
    Document doc = documents.findByIdInTenant(
        documentId, actor.activeTenantId()
    ).orElseThrow(DocumentNotFoundException::new);

    policy.requireCanRead(actor, doc);

    return new DocumentDto(
        doc.getId(),
        doc.getTitle(),
        policy.canReadContent(actor, doc)
            ? doc.getContent() : null
    );
}
```

**Snippet tích hợp:** `Actor`, `Document`, repo và policy là domain contract. Nếu content không được đọc, tốt hơn có thể dùng DTO khác hoặc omit property thay vì trả `null`; việc chọn shape phải theo API contract.

Một test cần kiểm tra **field không có quyền không xuất trong JSON**, không chỉ kiểm tra status 200. Ngay cả tài liệu owner có thể chứa dữ liệu sensitive thuộc người khác, do đó “owner allowed” không đồng nghĩa “show every DB column”.

## 14. MapStruct, manual mapper và mapping libraries không phải authorizer

MapStruct là công cụ tạo mã ánh xạ; các mapper khác có thể dựa trên reflection/convention. Chúng không tự biến một phép copy field thành quyết định authorization.

Ví dụ mapping giả định:

```java
@Mapper(componentModel = "spring")
public interface DocumentMapper {
    DocumentDto toDto(Document entity);
}
```

Annotation trên chỉ yêu cầu tạo mapper Spring bean khi dùng MapStruct đúng dependency/annotation processor. Nó **không** nói “chỉ map khi principal có quyền”.

Các lỗi khi review mapper:
- Một target field được map từ property khác với field post-check kỳ vọng.
- Không map `tenantId`/`ownerId` rồi security expression không còn dữ liệu.
- Map nhầm `source.userId` thành owner dù owner thật ở relation khác.
- Mapping child entity collections chứa confidential information.
- Mapping trực tiếp lazy relation gây SQL ngoài transaction.
- Mapper gọi một getter được bảo vệ nhưng invocation **không qua proxy** nên method-security annotation không chạy.
- Một map function được gọi ở endpoint khác trước khi policy guard.
- DTO mặc định có nhiều field hơn contract và Jackson serialize hết.
- Update mapper vô tình cho phép client thay `ownerId`/`role` khi DTO dùng cho input.

**Cách phòng:** coi mapper là code biến đổi dữ liệu, không phải authority check. Đặt policy ở service/repository boundary, và test mappings/dữ liệu JSON sau khi kiểm tra quyền.

## 15. JPA projection và native query làm thay đổi thông tin hậu kiểm

Một Spring Data repository có thể trả projection:

```java
public interface DocumentSummaryProjection {
    Long getId();
    String getTitle();
}
```

Service:

```java
@PostAuthorize(
    "returnObject.ownerId == authentication.name"
)
public DocumentSummaryProjection getSummary(long id) {
    return repository.findSummaryById(id).orElseThrow();
}
```

Nếu projection không có ownerId, post-check không còn input cần thiết. Không nên truy cập property không có trong projection rồi “bỏ rule”. Có thể:
- Trả projection nội bộ chứa ownerId/tenantId để policy kiểm tra, rồi map sang public DTO sau authorize;
- Tách query thành `findReadableSummaryById(id, actorId, tenantId)` có scope ngay tại DB;
- Tải entity tối thiểu gồm metadata policy, chạy guard rồi map;
- Sử dụng owner/ACL policy bean tra đúng resource với chi phí DB rõ ràng.

**Open projections / nested projections** có thể có SpEL/lazy access; không nên giả định chúng giống entity đầy đủ hoặc một DTO đã materialize. Cần test runtime với DB và mapping thật.

Một projection tối ưu query chỉ gồm `id,title` có thể rất tốt cho hiệu năng, **miễn truy vấn đã scope quyền**, không cần owner property để post-check.

## 16. Query scoping thường tốt hơn sửa DTO để giữ ownerId

Thay vì tải theo ID rồi kiểm tra hậu kỳ:

```sql
SELECT *
FROM documents
WHERE id = :document_id;
```

Có thể đưa tenant/owner/ACL vào truy vấn:

```sql
SELECT d.id, d.title, d.content
FROM documents d
WHERE d.id = :document_id
  AND d.tenant_id = :authorized_tenant
  AND (
    d.owner_id = :actor_id
    OR EXISTS (
      SELECT 1
      FROM document_grants g
      WHERE g.document_id = d.id
        AND g.user_id = :actor_id
        AND g.permission = 'READ'
    )
  );
```

Các tham số `authorized_tenant` và `actor_id` phải lấy từ Authentication/membership **đã xác thực**, không từ JSON/body/query tự khai. Nếu actor có quyền đọc toàn tenant, bổ sung nhánh riêng có điều kiện rõ theo policy; không dùng một `ROLE_ADMIN` global để bỏ tenant.

Ưu điểm:
- Không trả entity ngoài scope lên service theo đường query này.
- DTO có thể tối thiểu (không cần giữ ownerId để post-check).
- Dễ paging, sorting và counting phù hợp quyền.
- Giảm nguy cơ log/cache data sai actor.
- Bớt query lặp nếu post-authorizer ban đầu phải tra ACL lần nữa.

Đây là **authorization được thực thi tại data access scope**, cần review SQL/ORM để tránh thiếu điều kiện khi query khác. Có thể kết hợp một domain policy phía service nếu cần defense in depth.

## 17. Pagination: list DTO + hậu lọc thường sai kết quả

Giả sử:
- DB chứa 1.000 tài liệu.
- Alice chỉ có quyền xem 10 tài liệu.
- Repository trả 20 tài liệu đầu rồi service map sang DTO.
- `@PostFilter` loại 18 tài liệu không thuộc Alice.

API sẽ trả 2 item dù đáng ra có thể có thêm nhiều item thuộc Alice ở page tiếp theo. `totalElements` trong `Page` có thể không tương ứng với số item sau lọc. Nếu dùng `Page<DocumentDto>` và filter ngoài, behavior càng phải kiểm tra theo version/collection type.

**Mẫu nên dùng:** query theo scope quyền **trước khi áp LIMIT/OFFSET hoặc keyset pagination**, sau đó map từng record và trả metadata count được tính trong cùng scope. Nếu business phải cho phép đa nhánh ACL, câu SQL/query specification cần diễn đạt đầy đủ:
- cùng tenant;
- owner hoặc ACL grant hợp lệ;
- classification/state;
- audience/project relationship;
- permission READ;
- thứ tự và giới hạn page.

Một query đúng cho danh sách còn giúp ngăn lộ số lượng dữ liệu ngoài quyền qua counts/search suggestions.

## 18. Cache: đặt trước hay sau kiểm tra quyền?

Ví dụ nguy hiểm:

```java
@Cacheable(cacheNames = "documents", key = "#id")
@PostAuthorize(
    "@documentPolicy.canRead(authentication, returnObject)"
)
public DocumentDto read(long id) {
    return mapper.toDto(repository.findById(id).orElseThrow());
}
```

Tùy thứ tự `@Cacheable`, method-security advisors và cache key, object có thể được cache trước khi policy được áp, hoặc một cached DTO được chia cho actor khác. Nếu DTO chứa dữ liệu đã giải mã/chưa giảm field, rủi ro càng lớn.

**Không suy ra thứ tự AOP advisor** từ vị trí annotations trên source. Cần kiểm tra cấu hình runtime và test.

Chiến lược an toàn:
1. Cache raw document trong service/repository có ACL/tenant rules riêng và **luôn** authorize trên mỗi truy cập trước khi trả/map dữ liệu.
2. Hoặc cache theo key có actor/tenant/permission version và invalidation đầy đủ (khó hơn).
3. Không cache một “ALLOW” vĩnh viễn chỉ vì actor từng là owner.
4. Không đưa DTO đã filter cho actor A sang actor B nếu field visibility khác nhau.
5. Revalidate quyền khi role, owner, ACL, tenant membership thay đổi theo yêu cầu nghiệp vụ.
6. Audit/trace không ghi sensitive DTO trước khi authorization.

Cache là tối ưu hiệu năng, **không phải nơi tạo/chuyển quyền**.

## 19. @Transactional và mapper: đối chiếu thời điểm thật

Giả sử:

```java
@Transactional(readOnly = true)
@PostAuthorize(
    "@documentPolicy.canRead(authentication, returnObject)"
)
public DocumentDto read(long id) {
    Document doc = repository.findById(id).orElseThrow();
    return mapper.toDto(doc);
}
```

Nếu mapper gọi lazy properties, điều đó có thể thực thi SQL khi transaction đang mở (tùy proxy nesting). `@PostAuthorize` đánh giá DTO sau khi body trả; JPA lazy relation có thể còn hoặc đã mất persistence context tùy thứ tự advisors và transaction boundaries. `@PostAuthorize` đọc entity lazy owner trực tiếp còn dễ phát sinh `LazyInitializationException` khi interceptor sau method chạy ngoài session.

Điểm thực hành:
- Không dựa vào `Open Session in View` để che lỗi architecture.
- Materialize mọi property mà policy cần **trong transaction rõ ràng**.
- Tránh dùng lazy entity trực tiếp làm JSON response.
- Test khi OSIV disabled nếu production theo hướng này.
- Không cho mapper kích hoạt external service hoặc ghi dữ liệu trước kiểm tra owner.
- Với write, authorization trên entity thật **trước mutation**, dùng version/locking tránh TOCTOU.

Không có một thứ tự mặc định duy nhất nên được dùng làm bằng chứng “post-check chắc chắn xảy ra trong transaction của mọi dự án”. Cấu hình advisors và test quyết định.

## 20. @PostAuthorize không giải quyết bảo vệ side effect

Đoạn code nguy hiểm:

```java
@PostAuthorize(
    "@documentPolicy.canEdit(authentication, returnObject)"
)
public DocumentDto rename(long id, String title) {
    Document doc = repository.findById(id).orElseThrow();
    doc.rename(title);
    repository.save(doc);
    return mapper.toDto(doc);
}
```

Nếu policy từ chối ở hậu kiểm, database **có thể đã thay đổi**, message/email có thể đã được gửi, log/cache có thể đã ghi dữ liệu. Transaction rollback phụ thuộc boundary và advisor order, không thể coi là bảo đảm mặc định; external side effects còn không nhất thiết rollback.

Mẫu command đúng:

```java
@PreAuthorize("hasAuthority('document:rename')")
@Transactional
public DocumentDto rename(long id, String title) {
    Actor actor = actors.requireActor();
    Document doc = documents.findForUpdateInTenant(
        id, actor.activeTenantId()
    ).orElseThrow(DocumentNotFoundException::new);

    policy.requireCanRename(actor, doc);
    doc.rename(title);
    return mapper.toDto(doc);
}
```

Trong command:
1. Tải entity **theo tenant đã xác minh**.
2. Kiểm tra quyền trên entity trước mutation.
3. Quản lý version/lock hoặc SQL conditional update.
4. Chỉ map và trả DTO sau khi đủ quyền.
5. Không gửi external side effect cho tới khi consistency được kiểm soát (transactional outbox khi cần).

Đây là snippet domain tích hợp, các methods custom phải được triển khai. Đừng tạo quyền sửa từ `ownerId` do client tự khai.

## 21. Java 17 độc lập: mapper bỏ owner và hậu kiểm yếu làm lộ dữ liệu

Ví dụ sau là **Java thuần**, không dùng Spring Framework, Spring Security, JPA hoặc JSON serializer. Mục tiêu minh họa **cơ chế logic**: một DTO public không chứa owner/tenant; nếu mapper đã tạo DTO và chỉ còn kiểm tra permission chung, một actor có thể nhận dữ liệu người khác. Luồng an toàn xác minh quyền trên entity trước khi map.

Lưu file `DtoAuthorizationDemo.java`:

```java
import java.util.Map;
import java.util.Set;

public class DtoAuthorizationDemo {

    record Actor(String id, String tenant, Set<String> rights) {}
    record Document(long id, String owner, String tenant,
                    String title, boolean locked) {}
    record PublicDto(long id, String title) {}

    private static final Map<Long, Document> DB = Map.of(
        42L, new Document(42, "alice", "A", "Alice plan", false),
        43L, new Document(43, "bob", "A", "Bob plan", false),
        44L, new Document(44, "bob", "B", "Other tenant", false),
        45L, new Document(45, "alice", "A", "Locked", true)
    );

    private static int mapped = 0;

    static PublicDto toDto(Document doc) {
        mapped++;
        return new PublicDto(doc.id(), doc.title());
    }

    static String unsafeRead(Actor actor, long id) {
        Document doc = DB.get(id);
        if (doc == null) return "NOT_FOUND";

        // Chuyển sang DTO trước; owner/tenant không còn trong DTO.
        PublicDto result = toDto(doc);

        // Anti-pattern: bỏ kiểm tra owner vì DTO thiếu property.
        if (!actor.rights().contains("document:read")) {
            return "DENY capability";
        }
        return "ALLOW dto#" + result.id();
    }

    static String safeRead(Actor actor, long id) {
        if (!actor.rights().contains("document:read")) {
            return "DENY capability";
        }

        Document doc = DB.get(id);
        if (doc == null) return "NOT_FOUND";
        if (!actor.tenant().equals(doc.tenant())) {
            return "DENY tenant";
        }
        if (doc.locked()) return "DENY locked";

        boolean owner = actor.id().equals(doc.owner());
        boolean tenantGrant =
            actor.rights().contains("document:read:tenant");

        if (!owner && !tenantGrant) return "DENY owner";

        PublicDto dto = toDto(doc); // Chỉ map sau khi ALLOW.
        return "ALLOW dto#" + dto.id();
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
            "alice", "A", Set.of("document:read"));
        Actor bob = new Actor(
            "bob", "A", Set.of("document:read"));
        Actor manager = new Actor(
            "manager", "A", Set.of(
                "document:read", "document:read:tenant"));
        Actor guest = new Actor("guest", "A", Set.of());

        System.out.println("Unsafe Bob reads Alice: "
            + unsafeRead(bob, 42));
        System.out.println("Safe Bob reads Alice: "
            + safeRead(bob, 42));
        System.out.println("Safe Alice own: "
            + safeRead(alice, 42));
        System.out.println("Safe manager same tenant: "
            + safeRead(manager, 42));
        System.out.println("Safe Bob cross tenant: "
            + safeRead(bob, 44));
        System.out.println("Safe Alice locked: "
            + safeRead(alice, 45));
        System.out.println("Safe guest: "
            + safeRead(guest, 42));
        System.out.println("Safe missing: "
            + safeRead(alice, 999));
        System.out.println("DTO mappings performed: " + mapped);
    }
}
```

Chạy JDK 17 trở lên:

```bash
javac DtoAuthorizationDemo.java
java DtoAuthorizationDemo
```

Stdout **chính xác**:

```text
Unsafe Bob reads Alice: ALLOW dto#42
Safe Bob reads Alice: DENY owner
Safe Alice own: ALLOW dto#42
Safe manager same tenant: ALLOW dto#42
Safe Bob cross tenant: DENY tenant
Safe Alice locked: DENY locked
Safe guest: DENY capability
Safe missing: NOT_FOUND
DTO mappings performed: 3
```

Giải thích:
1. Bob có quyền đọc chung, nhưng không là owner Document 42. `unsafeRead` vẫn ALLOW vì **cố tình bỏ owner check sau khi DTO đã mất metadata**.
2. `safeRead` từ chối Bob trước khi tạo DTO.
3. Alice là owner đúng tenant nên ALLOW.
4. Manager có explicit `document:read:tenant` nên ALLOW trong cùng tenant; đây là capability **do mô hình chủ động cấp**, không phải quyền mặc định của manager/admin.
5. Bob không đọc document tenant B dù owner của document B cũng tên “bob”.
6. Tài liệu LOCKED bị DENY theo business contract demo.
7. Guest không có quyền đọc chức năng.
8. ID không tồn tại trả NOT_FOUND.
9. Có đúng **3 lần mapping**: một lần ở luồng không an toàn, hai lần ở hai trường hợp được ALLOW trong luồng an toàn. Những request safe bị DENY không map dữ liệu.

**Giới hạn:** đoạn code chỉ mô phỏng một bug do developer bỏ authorization, **không mô phỏng Spring Security tự fail-open khi SpEL thiếu property**. Java record/Map là data giả; không có Authentication, proxy, Jackson, DB, transaction hay ACL thật. Không sao chép `unsafeRead` vào production.

## 22. Unit test mapper không được thay thế unit test policy

Với DTO mapping, cần hai nhóm test riêng.

### A. Test mapper shape

```java
@Test
void mapsOnlyPublicFields() {
    Document entity = documentWithSensitiveFields();

    DocumentDto dto = mapper.toDto(entity);

    assertThat(dto.id()).isEqualTo(entity.getId());
    assertThat(dto.title()).isEqualTo(entity.getTitle());
    // Kiểm tra DTO không lộ secrets theo contract.
}
```

### B. Test policy trên entity

```java
@Test
void sameRoleButDifferentOwnerIsDenied() {
    Actor bob = actor("bob", "tenant-A", "document:read");
    Document aliceDoc = document(
        42L, "alice", "tenant-A", false);

    assertThat(policy.canRead(bob, aliceDoc)).isFalse();
}

@Test
void sameOwnerButDifferentTenantIsDenied() {
    Actor alice = actor("alice", "tenant-A", "document:read");
    Document doc = document(
        44L, "alice", "tenant-B", false);

    assertThat(policy.canRead(alice, doc)).isFalse();
}
```

Đây là các **snippet JUnit 5/AssertJ và domain fixtures**, không phải Java standalone. `documentWithSensitiveFields`, `actor`, `document` và `policy` phải do test project định nghĩa.

Test mapper pass **không** chứng minh service đã authorize trước khi gọi mapper. Test policy pass **không** chứng minh service thật sự gọi policy. Cần thêm integration tests.

## 23. Integration test kiểm tra thứ tự policy → mapper

Trong một Spring integration test có service được inject qua proxy, spy/stub policy và mapper có thể dùng để xác minh:

```java
@Test
@WithMockUser(authorities = {"document:read"})
void nonOwnerIsDeniedBeforeMapping() {
    // Repository fixture: Document 42 owner Alice, actor Bob.
    assertThatThrownBy(() -> service.read(42L))
        .isInstanceOf(AccessDeniedException.class);

    verify(mapper, never()).toDto(any());
}

@Test
@WithMockUser(authorities = {"document:read"})
void ownerIsMappedAfterAuthorization() {
    // Fixture: actor Alice, Document 42 thuộc Alice/tenant A.
    DocumentDto dto = service.read(42L);

    assertThat(dto.id()).isEqualTo(42L);
    verify(mapper).toDto(any(Document.class));
}
```

Đây là snippets, yêu cầu Spring Boot Test, JUnit 5, AssertJ/Mockito, actor resolver theo test principal, repository fixtures, bean service/proxy thật và exception setup phù hợp. Nếu integration test dùng `@PostAuthorize` trên return DTO thay vì guard trước mapper, test `verify(mapper, never())` **không thể pass**, vì mapper ở body đã chạy. Khi đó hãy test một cách đúng hợp đồng:
- Return bị DENY khi actor không đủ quyền object.
- Dữ liệu không được serialize/trả tới client.
- Log/cache/external side effects không xảy ra trước deny, hoặc đã được thiết kế kiểm soát.

**Đừng viết test để củng cố kỳ vọng sai về thời điểm Spring AOP hậu kiểm.**

## 24. Regression test khi DTO được đổi tên/xóa property

Để ngăn refactor làm mất security, tạo các test:
1. Actor có `document:read` nhưng không owner → DENY.
2. Actor đủ role, đúng owner, đúng tenant → ALLOW.
3. Actor trùng owner nhưng sai tenant → DENY.
4. ACL READ được cấp có hiệu lực; ACL WRITE không đồng nghĩa READ nếu policy không quy định.
5. Tài liệu LOCKED/ARCHIVED bị xử lý theo contract.
6. DTO output không chứa `ownerUserId`/`tenantId`/`secretMetadata` nếu không public.
7. Nếu dùng secured DTO và `@PostAuthorize`, biểu thức resolve đúng property trên **return type hiện hành**.
8. Khi đổi từ entity sang projection/DTO, test phải chạy với return type mới.
9. Khi thêm mapper khác cho GraphQL/export, test vẫn enforce policy.
10. Nếu query trả list/page, không có item hoặc count ngoài scope.
11. Method được gọi qua bean Spring AOP, không qua `new` hoặc `this.method`.
12. Khi DENY, controller chưa serialize JSON và không trả sensitive error details.

Chỉ một test “user đã login nhận HTTP 200” gần như không có giá trị chứng minh object authorization. Phải có negative cases với user đã được xác thực, đủ authority chức năng nhưng **không** có quyền resource.

## 25. MockMvc test cả status và payload JSON

Ví dụ:

```java
@Test
void ownerGetsSafeDto() throws Exception {
    mvc.perform(get("/api/documents/42")
            .with(user("alice").authorities(
                new SimpleGrantedAuthority("document:read")
            )))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.ownerUserId").doesNotExist())
        .andExpect(jsonPath("$.tenantId").doesNotExist());
}

@Test
void nonOwnerCannotReceiveDto() throws Exception {
    mvc.perform(get("/api/documents/42")
            .with(user("bob").authorities(
                new SimpleGrantedAuthority("document:read")
            )))
        .andExpect(status().isForbidden());
}
```

**Snippets MockMvc**, cần controller, route, fixtures, actor resolver, exception mapping, `spring-security-test` và matching imports. Nếu contract che sự tồn tại bằng 404, thay expectation nhưng vẫn cần kiểm chứng **không có dữ liệu private**. 404 khi route không tồn tại không chứng minh authorization.

Các tests nên bổ sung:
- JSON không chứa email, token, secret fields không được phép.
- Response Content-Type, HTTP status và error body không chứa owner thực.
- User có quyền object nhưng không có field-level permission chỉ nhận field cho phép.
- Guest không có quyền đọc không đi tới repository nếu pre-check có thể chặn.
- Nếu map đã thực thi trước post-check, test không có lộ dữ liệu vào logger/cache.
- Đường GraphQL và download/export trả cùng mức bảo vệ.

Một HTTP 403 trên POST/PATCH có thể do CSRF chứ không phải policy; với write tests phải gửi CSRF token hợp lệ khi security setup yêu cầu và kiểm chứng DB không đổi.

## 26. GraphQL và nested resolvers làm rủi ro ánh xạ tinh vi hơn

Trong REST, một service thường tạo DTO rồi Jackson serialize. Trong GraphQL:
- Query có thể chọn fields tùy ý trong schema.
- Resolver con có thể được gọi sau resolver cha.
- Một parent object được phép xem không đồng nghĩa field con được phép.
- DataLoader có thể batch/cache kết quả theo key thiếu actor/tenant.
- DTO/projection có thể được truyền từ resolver này sang resolver khác.

Ví dụ một resolver trả `DocumentDto` có `ownerId` bị bỏ, rồi child resolver `attachments` tải toàn bộ tệp bằng document ID mà không kiểm tra actor — đây là đường **BOLA** khác. Hậu kiểm trên parent object không tự chứng minh quyền cho attachment ở resolver con.

Giải pháp:
- Dùng domain policy ở application service mà mọi resolver gọi.
- Query/scoping theo actor + tenant cho mỗi resource cần bảo vệ.
- Không chia DataLoader cache giữa actors/tenants trừ khi key và invalidation đảm bảo cách ly.
- Có field-level policies cho dữ liệu nhạy cảm.
- Test GraphQL selections khác nhau với cùng document ID và actor thiếu quyền.

**Không dựa vào DTO shape như một authorization policy**, vì schema/resolver có thể mở thêm fields mà mapper ban đầu không tính tới.

## 27. Mối quan hệ với RoleHierarchy

Một hierarchy:

```text
ROLE_ADMIN > ROLE_EDITOR
ROLE_EDITOR > ROLE_VIEWER
```

cho phép actor ADMIN có thể vượt `hasRole('VIEWER')` nếu component đã được cấu hình sử dụng `RoleHierarchy`. Nhưng một DTO bỏ `ownerId` không tự được bảo vệ chỉ vì actor có role cao. Role là quyền chức năng; document ownership, tenant, ACL và classification là quyền trên resource.

Ví dụ quy tắc đầy đủ:

```text
ALLOW readDocument(id)
    = actor has document:read
      AND document tenant is authorized
      AND (
        document.ownerId == actor.userId
        OR ACL READ grant for actor
        OR explicit tenant-wide READ capability
      )
      AND document state permits read
```

Hierarchy có thể cấp `document:read` cho ROLE_VIEWER và `document:read:tenant` cho ROLE_ADMIN **nếu business phê duyệt**. Nhưng query/policy vẫn cần thấy entity gốc hoặc metadata chuẩn; DTO tối thiểu chỉ để response không phải nơi đáng tin để suy ra toàn bộ security invariants.

Không cố “sửa” việc mapper mất ownerId bằng cách nới role cho mọi user.

## 28. 403, 404, 500 khi security property biến mất

Ba tình huống:
- **403:** security expression hoặc policy đánh giá DENY, thường cho actor đã xác thực trong luồng HTTP.
- **404:** resource không tồn tại, hoặc ứng dụng chủ ý che sự tồn tại của resource không được phép.
- **500 hoặc lỗi đánh giá expression:** biểu thức hậu kiểm truy cập property không có trên DTO hoặc getter throw runtime exception, tùy exception handling.

Không đồng nhất 500 do expression lỗi với 403 do policy DENY, cũng không tự catch mọi lỗi SpEL rồi return ALLOW/`permitAll` để response “đẹp”. Khi mapper đổi type, test/build phải phát hiện lỗi trước production; khi lỗi policy/DB không rõ, thiết kế fail-closed và error handling không lộ secret.

Đối với anti-enumeration, cân nhắc cùng response cho “không tồn tại” và “không được phép” theo threat model; query scoped có thể hỗ trợ. Đừng lộ owner email, tenant ID hoặc tên người được chia sẻ trong error body.

## 29. Khi nào chọn giải pháp nào?

| Tình huống | Giải pháp phù hợp | Điều cần kiểm chứng |
| --- | --- | --- |
| Một entity read-only, owner chỉ biết sau query | `@PostAuthorize` trên entity/secured view có metadata | Proxy, đúng return type, source tin cậy, không side effect |
| REST trả public DTO không có owner metadata | Guard entity trong service trước mapper | Policy thực thi trước mapping/serialization |
| DTO cần giữ post-check | Internal secured DTO metadata + policy bean | Jackson output không lộ metadata, mapper lấy từ DB |
| Muốn giữ method annotation trên entity reader | Secured loader bean qua proxy, facade map sau ALLOW | Không self-invocation/direct repo bypass |
| List lớn / pagination | Repository query theo scope trước paging | Counts, owner/tenant/ACL chính xác |
| Field-level PII | Permission theo field + DTO allowlist | JSON/export/GraphQL không lộ field |
| Mapped JPA relation/lazy | Materialize fields trong transaction theo policy | Không lazy error, không SQL bất ngờ ngoài scope |
| Command write | Pre-check quyền chung + domain policy trước mutation | Transaction, locking, no side effect after DENY |
| Có @AuthorizeReturnObject | Test proxy và getter annotations trên object thật | Không giả định plain DTO có security advice |
| Cache DTO theo document ID | Authorize trên mỗi lần đọc, key/invalidation phù hợp | Không leak giữa user/tenant |
| Chuyển service từ entity sang projection | Regression test biểu thức và shape | Không bỏ security để chữa property error |

Mục tiêu không phải “giữ `@PostAuthorize` ở mọi nơi”, mà là **không mất quyết định quyền** trong quá trình thay đổi data shape.

## 30. Checklist review DTO / mapper dưới góc nhìn bảo mật

1. Method trả entity, DTO, projection, collection, Page, Optional hay wrapper?
2. `returnObject` tại `@PostAuthorize` chính xác là kiểu gì?
3. Biểu thức post-check cần ownerId, tenantId, ACL, state từ đâu?
4. Mapper có làm mất/đổi các metadata ấy không?
5. Nếu property thiếu, code có bị lỗi hoặc developer đã nới policy để “fix” không?
6. DTO fields có đến từ entity thật hay client request được copy lại?
7. Source of truth của owner và tenant có đáng tin không?
8. Actor canonical ID/active tenant có được xác minh từ Authentication/membership không?
9. `@EnableMethodSecurity` và Spring bean proxy có thực sự hoạt động không?
10. Có self-invocation hoặc direct repository access bypass secured loader không?
11. `@PostAuthorize` nằm **trước hay sau mapper** trong flow runtime?
12. Mapper có chạy side effect, log hoặc cache DTO trước policy không?
13. Có JPA lazy relation hoặc transaction advisor order ảnh hưởng không?
14. DTO có chứa PII/secret fields ngoài permission actor không?
15. Có `@JsonIgnore` hoặc Jackson filter nhưng đường export khác lại serialize không?
16. Getter được gắn method-security annotation có được gọi qua proxy không?
17. Sau khi chuyển sang record DTO, getter annotations cũ có còn effect không?
18. Nếu dùng `@AuthorizeReturnObject`, return type có proxyable và AOT hints đúng không?
19. Với List/Page, policy có kiểm tra từng object trước pagination/count không?
20. Query đã giới hạn tenant/owner/ACL đúng chưa?
21. Đường GraphQL/download/export có dùng cùng policy không?
22. Cache key có phụ thuộc actor/tenant/rights hoặc có recheck mỗi lần đọc không?
23. Với write, quyền được kiểm tra trước mutation và side effect chưa?
24. Đã test actor đủ role nhưng khác owner/tenant DENY chưa?
25. Đã test DTO không lộ metadata/PII trong JSON chưa?
26. Đã test đổi mapper/return type không phá expression không?
27. Lỗi SpEL có fail-closed và không lộ dữ liệu không?
28. Logs có loại bỏ raw entity/DTO nhạy cảm không?
29. Owner/ACL/membership đổi có được invalidate cache/policy đúng không?
30. Review security được yêu cầu khi sửa mapping hoặc API projection không?

### Câu hỏi tự kiểm tra

**1.** Service trả `Document` có `ownerId`, sau refactor trả `DocumentDto` không có `ownerId`. `@PostAuthorize("returnObject.ownerId ...")` còn đúng không?  
→ **Không.** `returnObject` hiện là DTO; property có thể không resolve, cần thay đổi chốt quyền/return type và test, không xóa policy.

**2.** Thiếu field trên DTO có nghĩa Spring tự động bỏ qua `@PostAuthorize` và ALLOW không?  
→ **Không.** Có thể lỗi SpEL. Lỗ hổng thường xuất hiện khi guard bị xóa/nới quá rộng hoặc mapping làm mất chốt khác.

**3.** Cách đơn giản để public DTO không chứa ownerId nhưng vẫn kiểm tra owner?  
→ Tải entity thật, kiểm tra tenant/owner/ACL trong service, rồi **mới map DTO**.

**4.** Có thể dùng `@JsonIgnore` che ownerId trên secured DTO để post-check không?  
→ Có thể trong Jackson đúng cấu hình, nhưng `@JsonIgnore` không phải security boundary. Phải test serialization/other serializers và dùng owner metadata từ DB.

**5.** Entity getter có `@PreAuthorize`; mapper copy giá trị vào record DTO. Getter annotation còn tự bảo vệ DTO không?  
→ **Không mặc định.** Method security bảo vệ lời gọi qua proxy/advice, không tự di chuyển annotation sang record accessor.

**6.** `@AuthorizeReturnObject` có tương đương `@PostAuthorize` không?  
→ **Không.** Một cơ chế proxy methods trên return object, một cơ chế đánh giá toàn kết quả sau method.

**7.** `@PostFilter` dùng với danh sách 1 triệu record trước khi phân trang có tốt không?  
→ Thường không; dùng query scoped theo quyền trước paging, vì hậu lọc đắt và có thể làm sai count/page.

**8.** Hậu kiểm DENY có nghĩa mapper chưa chạy không?  
→ **Không.** Nếu mapper ở method body, nó chạy trước `@PostAuthorize`. Cần tránh mapper có side effect/caching nhạy cảm.

**9.** Actor là owner của document nhưng không được đọc PII field; object-level post-check ALLOW có tự giấu PII không?  
→ **Không.** Phải có field-level policy và DTO allowlist/serialization test.

**10.** Một test HTTP 403 khi actor thiếu quyền chức năng có chứng minh owner check không?  
→ **Không.** Phải dùng actor có quyền chung nhưng sai owner/tenant và xác minh điểm DENY thực.

## Kết luận

**DTO và mapper là bước chuyển đổi hình dạng dữ liệu, không phải thành phần quyết định quyền mặc định.** `@PostAuthorize` đánh giá `returnObject` thật sự của method; khi mapper chuyển entity sang DTO và bỏ `ownerId`, `tenantId` hoặc metadata ACL, biểu thức hậu kiểm có thể không còn hợp lệ. An toàn nhất trong nhiều use case là **authorization trên entity/secured view từ nguồn tin cậy trước khi map sang DTO công khai**, hoặc dùng secured loader thực sự qua proxy rồi mới map. Với dữ liệu nhạy cảm, list lớn, field-level PII và commands có side effect, cần query scoped, policy actor–resource, kiểm soát mapper/serializer và regression tests. **Không xóa/nới security rule chỉ vì DTO mới làm SpEL error.**

## Tài liệu tham khảo chính thức

1. [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html) — `@PostAuthorize`, `returnObject`, `@PostFilter`, `@AuthorizeReturnObject`, AOP và transaction.
2. [Spring Security 6.5 — Method Security Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html) — `@WithMockUser` và kiểm thử method-level permissions.
3. [Spring Security 6.5 — Domain Object Security (ACL)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html) — ACL/permission per object.
4. [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html) — HTTP security khác method checks.
5. [OWASP — Insecure Direct Object Reference Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html) — xác minh quyền truy cập object theo user, tránh IDOR/BOLA.
6. [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html) — boundaries, proxy và rollback semantics.
