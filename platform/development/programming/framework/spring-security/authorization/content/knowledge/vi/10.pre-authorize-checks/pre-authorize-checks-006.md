# Kiểm tra thuộc tính của đối tượng đầu vào

> **Module:** Spring Security - authorization  
> **Nhóm kiến thức:** Kiểm tra trước phương thức  
> **Mục tiêu:** Dùng `@PreAuthorize` để đọc thuộc tính của tham số method (DTO, command, object, collection) và kiểm tra quyền **trước khi chạy method body**; hiểu tên biến `#command`, `@P`, `-parameters`, SpEL, quyền trên input do client điều khiển; thiết kế policy dựa trên Authentication và dữ liệu server tin cậy, chống IDOR/BOLA/over-posting/TOCTOU; biết test trường hợp sai quyền, thiếu trường, input giả mạo và side effect.

## 1. Bài toán: thuộc tính của input không đồng nghĩa sự thật về đối tượng

Một service có method:

```java
public void renameDocument(RenameDocumentCommand command) {
    // Thực hiện đổi tên tài liệu...
}
```

Request có thể chứa:

```json
{
  "documentId": 42,
  "claimedOwnerId": "alice",
  "tenantId": "org-a",
  "newTitle": "Kế hoạch tháng tới"
}
```

Với Spring Method Security, ta có thể viết:

```java
@PreAuthorize("hasAuthority('document:rename') and #command != null")
public void renameDocument(RenameDocumentCommand command) {
    // ...
}
```

Spring kiểm tra `@PreAuthorize` trước khi chạy body, có thể đọc object `command` và các property của nó. Nhưng **không được** lập luận “`command.claimedOwnerId == authentication.name` nên người dùng chắc chắn là owner tài liệu số 42”: `claimedOwnerId` là **dữ liệu client tự khai**. Alice có thể gửi `documentId=42` của Bob và `claimedOwnerId=alice`.

Hai câu hỏi khác nhau:

1. **Input có thuộc một nhóm yêu cầu mà actor được phép thực hiện không?** Ví dụ action “đổi tên” cần `document:rename`; format xuất file CSV cần `report:export`.
2. **Dữ liệu thực trong hệ thống có cho phép actor làm vậy trên resource này không?** Phải tải document từ nguồn tin cậy và xét tenant, owner, ACL, trạng thái, v.v.

Bài này tập trung vào **kiểm tra trước phương thức (pre-invocation)** và cách dùng thuộc tính input một cách có giới hạn, không nhầm validation với authorization.

## 2. @PreAuthorize hoạt động ở điểm nào?

Ví dụ:

```java
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize(
    "hasAuthority('document:rename') and "
    + "#command != null and #command.documentId != null"
)
public void renameDocument(RenameDocumentCommand command) {
    // Body chỉ chạy khi pre-check được cho phép.
}
```

Luồng trong Spring Security Servlet 6.5:

```text
Controller / another Spring bean
            |
            v
Spring AOP proxy (method-security interception)
            |
            v
AuthorizationManagerBeforeMethodInterceptor
            |
            v
PreAuthorizeAuthorizationManager
            |
            v
MethodSecurityExpressionHandler
  - Authentication hiện hành
  - MethodInvocation và tham số
  - biểu thức SpEL trong @PreAuthorize
            |
            +--- DENY -> không chạy method body
            |
            +--- ALLOW -> chạy method body
                              |
                              v
                       Domain policy / DB
```

`@EnableMethodSecurity` cần được bật:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {}
```

**Điều kiện:** bean phải được Spring quản lý và invocation cần đi qua proxy/advisor. Annotation không tự bảo vệ lời gọi `this.method()` trong cùng target object theo cấu hình Spring AOP proxy thông thường. Cũng không tự bảo vệ object được tạo bằng `new` ngoài container.

`@PreAuthorize` bị từ chối khi interceptor chạy **trước** method body; đối với lệnh write đây là điểm thích hợp hơn `@PostAuthorize`. Nhưng nếu pre-check chỉ so sánh hai dữ liệu giả mạo từ client thì vẫn là kiểm tra **sai chính sách**, dù chạy đúng thời điểm.

## 3. Truy cập property bằng SpEL

Spring Security hỗ trợ các biểu thức tham chiếu tham số trong method:

```java
@PreAuthorize("#command.documentId != null")
public void renameDocument(RenameDocumentCommand command) {
    // ...
}
```

`#command` là tham số có tên `command`; `.documentId` là property SpEL, thường được truy cập thông qua getter `getDocumentId()` hoặc cơ chế property access của kiểu dữ liệu. Với DTO JavaBean:

```java
public final class RenameDocumentCommand {
    private final Long documentId;
    private final String newTitle;

    public RenameDocumentCommand(Long documentId, String newTitle) {
        this.documentId = documentId;
        this.newTitle = newTitle;
    }

    public Long getDocumentId() {
        return documentId;
    }

    public String getNewTitle() {
        return newTitle;
    }
}
```

Cách gọi trong annotation:

```java
@PreAuthorize(
    "hasAuthority('document:rename') and "
    + "#command != null and #command.documentId != null"
)
public void renameDocument(RenameDocumentCommand command) {
    // ...
}
```

Cần hiểu:
- `#command` khác `authentication` và `principal`. Nó là input của lời gọi.
- Property `documentId` phải tồn tại với tên và kiểu phù hợp; tên field Java chưa chắc bằng tên property nếu getter custom.
- SpEL có thể gọi method/property getter. Tránh getter có side effect, I/O hoặc dữ liệu mutable không ổn định trong một security expression.
- Nếu object null, biểu thức truy cập property trực tiếp có thể phát sinh lỗi. Viết null guard rõ và dựa vào phép `and` ngắn mạch.
- Null guard không có nghĩa quyền đã được xác minh; nó chỉ tránh biểu thức truy cập vào object không tồn tại.

Ví dụ nhiều cấp:

```java
@PreAuthorize(
    "#command != null and #command.options != null and "
    + "#command.options.format == 'CSV'"
)
public void export(ExportCommand command) {
    // ...
}
```

`options` và `format` cũng chỉ là các thuộc tính input. Cần xác định method body thực thi đúng format đã kiểm tra; nếu controller có alias/implicit default hoặc business command đổi mode sau pre-check, security rule có thể lệch hành vi thực.

## 4. Spring lấy tên #command từ đâu?

Một lỗi rất phổ biến là biểu thức `#command.documentId` không resolve tên tham số tại runtime. Spring Security sử dụng `DefaultSecurityParameterNameDiscoverer` để tìm tên tham số.

Các cách hỗ trợ gồm:

### A. Compile với -parameters

```bash
javac -parameters RenameDocumentService.java
```

Với Maven/Gradle, bật Java compiler option `-parameters` trên đúng module build. Spring Framework 6.1 đã bỏ cách suy tên tham số từ LocalVariableTable trước đây; do đó với code method security tham chiếu `#id`, `#command` theo tên Java, **đặc biệt quan trọng phải có `-parameters`**.

Ví dụ Maven Compiler Plugin:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

Đây là đoạn trong `pom.xml`, cần đặt trong `build/plugins` theo cấu trúc dự án và kiểm tra version compiler plugin; chỉ là phần cấu hình, không phải file Maven hoàn chỉnh.

Với Gradle Groovy DSL có thể dùng:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
```

Nhiều Spring Boot build đã cấu hình parameter metadata, nhưng **hãy kiểm tra output build thực tế**, không suy đoán từ tên framework.

### B. Đặt tên bằng @P

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize(
    "hasAuthority('document:rename') and "
    + "@documentPolicy.mayRequestRename(authentication, #command)"
)
public void renameDocument(
        @P("command") RenameDocumentCommand input) {
    // ...
}
```

`@P("command")` gắn một tên dùng được trong SpEL dù tên biến Java là `input`. Hữu ích với interface/service contract được compile riêng hoặc khi không kiểm soát compiler flags.

### C. Spring Data @Param

`DefaultSecurityParameterNameDiscoverer` cũng hỗ trợ `org.springframework.data.repository.query.Param` trong những cấu hình có dependency tương ứng. Tuy nhiên, không thêm Spring Data chỉ để đặt tên một tham số security; `@P` hoặc `-parameters` thường đơn giản hơn.

### D. Tên theo vị trí

Spring `MethodBasedEvaluationContext` thường cung cấp aliases theo vị trí như `#p0`, `#a0`, `#p1`. Chúng giúp minh họa cách truy cập arguments, nhưng tên có ý nghĩa như `#command` dễ đọc/review hơn và ít nhầm hơn khi thay đổi thứ tự tham số. Khi nhiều overload/interfaces, thêm test phương thức thực sự được gọi.

**Lỗi dễ chẩn đoán nhầm:** biểu thức không tìm được `#command` có thể báo SpEL error hoặc cho kết quả deny, không có nghĩa người dùng thiếu authority. Kiểm tra parameter metadata, tên property và build trước khi sửa policy.

## 5. @PreAuthorize có những biến nào ngoài tham số?

Các biểu thức thường dùng:

| Biểu thức | Ý nghĩa | Điều cần nhớ |
| --- | --- | --- |
| `authentication` | `Authentication` của lời gọi | Có thể chứa principal, authorities, details |
| `principal` | `Authentication#getPrincipal()` | Kiểu principal có thể khác theo cơ chế login/JWT |
| `authentication.name` | Tên người dùng theo Authentication | Không luôn bằng ID trong DB |
| `hasAuthority('x')` | Kiểm tra authority cụ thể | Chính sách role hierarchy/prefix tùy manager config |
| `hasRole('ADMIN')` | Kiểm tra role theo prefix mặc định `ROLE_` | Không nhầm với owner của resource |
| `#command` | Argument được đặt tên của method | Dữ liệu caller có thể kiểm soát |
| `#command.documentId` | Property của argument | ID chưa chứng minh có quyền trên object |
| `@documentPolicy` | Spring bean gọi từ SpEL | Nên gom logic domain phức tạp vào Java |
| `hasPermission(...)` | Kiểm tra permission qua `PermissionEvaluator` thích hợp | Cần cấu hình evaluator/policy thực, không tự có ACL chỉ vì bật Spring Security |

Tùy context/version còn có các expression root methods/variables khác. Không dựa vào tên biến từ ví dụ của một version khác nếu chưa kiểm tra compilation và test.

Ví dụ:

```java
@PreAuthorize(
    "hasAuthority('report:read') and "
    + "@reportPolicy.canRead(authentication, #query.reportId)"
)
public ReportView getReport(ReportQuery query) {
    // ...
}
```

Bean có thể lấy actor tin cậy từ Authentication và đọc resource từ server. Tuy nhiên, **lần đọc DB trong pre-expression** rồi body đọc/update sau đó cần quản lý nhất quán để tránh TOCTOU. Thường giữ pre-expression cho gate quyền chung và kiểm tra đầy đủ trong transaction ở use case.

## 6. Validation và authorization có hai nhiệm vụ

Ví dụ nhận một DTO:

```java
public record CreateInvoiceCommand(
    Long projectId,
    java.math.BigDecimal amount,
    String currency,
    String requestedBy
) {}
```

Có thể có validation:
- `projectId` không null và dương.
- `amount` dương và đúng precision.
- `currency` thuộc danh sách hỗ trợ.
- `requestedBy` phù hợp định dạng ký tự.

Nhưng validation không xác nhận actor:
- Có được tạo hóa đơn cho `projectId` không?
- Có là thành viên của tenant chứa project không?
- Có hạn mức để tạo invoice với `amount` không?
- Có quyền chọn `requestedBy` khác chính mình không?
- Resource còn ở trạng thái được phép tạo invoice không?

**Không đưa các điều kiện client-controllable thành bằng chứng quyền.** Ví dụ `requestedBy == authentication.name` chỉ chứng minh caller nhập tên mình, không chứng minh dữ liệu invoice gắn với actor được xác nhận đúng. Server nên tự đặt `createdBy` từ principal/actor đã xác thực, không nhận trực tiếp từ JSON nếu đây là trường security-sensitive.

Một phương thức có thể đồng thời có `@Valid` và `@PreAuthorize`, nhưng **không được mặc định thứ tự validation và security advisor** luôn đúng theo mọi cấu hình Spring/Bean Validation. Khi input có thể null/malformed, security expression nên tự xử lý null và service vẫn validate trong boundary phù hợp.

## 7. Khi nào dùng thuộc tính input trực tiếp là hợp lý?

Dùng input property trong pre-check có thể hữu ích khi thuộc tính đó thực sự là **tiêu chí phân loại yêu cầu**, không phải bằng chứng actor sở hữu tài nguyên.

Ví dụ hệ thống export có hai capability:
- `report:export:summary` cho báo cáo tổng hợp.
- `report:export:raw` cho raw data nhạy cảm.

```java
@PreAuthorize(
    "#request != null and "
    + "((#request.mode == 'SUMMARY' "
    + "and hasAuthority('report:export:summary')) "
    + "or (#request.mode == 'RAW' "
    + "and hasAuthority('report:export:raw')))"
)
public ExportResult exportReport(ExportRequest request) {
    // ...
}
```

Điều kiện trên có thể đúng nếu:
1. `mode` là enum/string được parse và validate nhất quán;
2. body thực sự chỉ làm điều được phép theo `mode`;
3. không có default/alias/header khác làm body xuất RAW trong khi expression nghĩ SUMMARY;
4. policy trên tenant/report thật vẫn được kiểm tra;
5. người chỉ có summary không thể lấy raw data bằng cách sửa các field khác.

Nếu mode policy phức tạp, ưu tiên:

```java
@PreAuthorize("@exportPolicy.mayExport(authentication, #request)")
public ExportResult exportReport(ExportRequest request) {
    // ...
}
```

Và bean `exportPolicy` phải kiểm tra capability theo **effective mode** cùng với actor/resource. Đừng viết một SpEL dài nhiều nhánh khiến reviewer bỏ sót.

## 8. Mẫu nguy hiểm: tin ownerId trong DTO

**Không an toàn:**

```java
@PreAuthorize(
    "hasAuthority('document:write') and "
    + "#command.claimedOwnerId == authentication.name"
)
public void rename(RenameDocumentCommand command) {
    repository.renameById(command.getDocumentId(),
        command.getNewTitle());
}
```

Một client là Bob có thể gửi:

```json
{
  "documentId": 42,
  "claimedOwnerId": "bob",
  "newTitle": "Đã thay đổi"
}
```

Nếu document 42 thực sự thuộc Alice, biểu thức `#command.claimedOwnerId == authentication.name` vẫn true cho Bob; body update theo ID và bỏ qua owner thật. Đây là **IDOR/BOLA** dù `@PreAuthorize` có chạy trước body.

Một anti-pattern tương tự:

```java
@PreAuthorize("#command.tenantId == principal.tenantId")
```

Nếu `command.tenantId` do client nhập, điều kiện chỉ chứng minh client chọn tenant đang active; **không chứng minh documentId ở tenant ấy**. Phải tra document tenant ở DB và xác minh permission theo resource thật.

**Quy tắc:** mọi field mang nghĩa ownership, tenant membership, clearance, approval status hoặc giá trị tài chính phải được đối chiếu nguồn tin cậy. Nếu client có quyền gửi chúng như yêu cầu nghiệp vụ, vẫn không được tự coi chúng là sự thật đã xác thực.

## 9. Mass assignment/over-posting làm thay đổi input thế nào?

Một DTO nhận quá nhiều field:

```java
public class UpdateUserRequest {
    private String displayName;
    private String email;
    private boolean admin;
    private String tenantId;
    private String ownerId;
    // getters/setters
}
```

Nếu controller bind JSON vào object trên rồi service copy trực tiếp vào entity bằng mapper không hạn chế, user có thể đặt `admin=true` hoặc sửa `tenantId`. Một pre-check `hasRole('USER')` không cứu được lỗi over-posting.

Thiết kế tốt hơn:
- DTO cho phép sửa profile chỉ có những field được phép: `displayName`, `locale`, v.v.
- Tách command `ChangeRoleCommand` với authority mạnh và policy chuyên trách.
- Các trường `createdBy`, `tenantId`, `approvedBy` do server quyết định hoặc kiểm tra membership.
- Mapper chỉ copy field allowlist, không bind toàn bộ entity trực tiếp từ request.
- Domain entity không cho caller tùy tiện thay owner/role/status qua setter chung.
- Test JSON chứa field trái phép, đảm bảo DB không đổi và response phù hợp.

Một `@PreAuthorize("#request.admin == false")` chỉ kiểm tra giá trị input ở một điểm; nếu có endpoint hoặc cách bind khác cho phép admin flag, hệ thống vẫn rủi ro. Cần thiết kế DTO và invariant trên entity.

## 10. Authentication.name không phải luôn là owner ID

`authentication.name` có thể là:
- username nội bộ;
- email;
- OIDC subject;
- opaque user ID;
- tên service account.

Còn DB có thể dùng UUID `ownerId` khác username. So sánh:

```java
@PreAuthorize("#command.ownerId == authentication.name")
```

có thể vừa sai chính sách vừa sai kiểu identity.

Nên định nghĩa server-side actor:

```java
public record Actor(
    java.util.UUID userId,
    java.util.UUID activeTenantId,
    java.util.Set<String> authorities
) {}
```

`Actor` phải được xây từ Authentication đã xác thực và membership/tenant context đã kiểm chứng; không lấy `userId` hay `activeTenantId` từ body chưa tin cậy.

Một policy đọc resource có thể nhận:

```java
boolean canRead(Actor actor, Document document);
```

Tránh gọi bean policy với `authentication.name` rồi đoán đó luôn là UUID của owner. Khi chuyển OAuth2 provider, semantics của principal có thể thay đổi, khiến rule sai.

## 11. Đặt chính sách ở bean Java thay vì SpEL dài

Một interface rõ ràng:

```java
public interface DocumentAccessPolicy {
    boolean canRename(Actor actor, Document document);
}
```

Ý tưởng tích hợp:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentCommandService {

    private final ActorResolver actorResolver;
    private final DocumentRepository repository;
    private final DocumentAccessPolicy policy;

    public DocumentCommandService(ActorResolver actorResolver,
                                  DocumentRepository repository,
                                  DocumentAccessPolicy policy) {
        this.actorResolver = actorResolver;
        this.repository = repository;
        this.policy = policy;
    }

    @PreAuthorize(
        "hasAuthority('document:rename') and #command != null"
    )
    @Transactional
    public void rename(RenameDocumentCommand command) {
        Actor actor = actorResolver.requireAuthenticatedActor();

        Document document = repository.findForUpdateInTenant(
            command.getDocumentId(), actor.activeTenantId()
        ).orElseThrow(DocumentNotFoundException::new);

        if (!policy.canRename(actor, document)) {
            throw new org.springframework.security.access.AccessDeniedException(
                "Rename denied"
            );
        }

        document.rename(command.getNewTitle());
    }
}
```

**Đây là snippet tích hợp**, không phải file JDK-alone. Những type `ActorResolver`, `Document`, `DocumentRepository`, `DocumentAccessPolicy`, `RenameDocumentCommand`, exception và method `findForUpdateInTenant` là contract của ứng dụng. Import, transaction manager, repository implementation, validation và authentication cần được bổ sung trong dự án thật.

Luồng:
- `@PreAuthorize` kiểm tra quyền chức năng trước body.
- Actor lấy từ server-side Authentication.
- Entity được tải theo tenant đã kiểm chứng, không theo `command.tenantId`.
- Policy kiểm tra owner/ACL/delegation/state.
- Chỉ sau ALLOW mới sửa entity trong transaction.

Nếu có permission “tenant admin sửa mọi document cùng tenant”, đưa nó vào `policy.canRename` **có ràng buộc tenant**, không bypass `if (isAdmin) return true` ở đầu mọi kiểm tra.

## 12. Sử dụng @documentAccess trong @PreAuthorize

Có thể đặt logic ở Spring bean:

```java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentAccess")
public class DocumentAccessExpression {

    private final DocumentRepository repository;
    private final ActorResolver actors;

    public DocumentAccessExpression(DocumentRepository repository,
                                    ActorResolver actors) {
        this.repository = repository;
        this.actors = actors;
    }

    public boolean mayRename(Authentication authentication,
                             RenameDocumentCommand command) {
        if (authentication == null || command == null
                || command.getDocumentId() == null) {
            return false;
        }

        Actor actor = actors.requireActor(authentication);
        return repository.findByIdAndTenantId(
                command.getDocumentId(), actor.activeTenantId()
            )
            .filter(doc -> doc.canBeRenamedBy(actor))
            .isPresent();
    }
}
```

Gọi từ service:

```java
@PreAuthorize(
    "hasAuthority('document:rename') and "
    + "@documentAccess.mayRename(authentication, #command)"
)
public void rename(RenameDocumentCommand command) {
    // ...
}
```

**Lưu ý kỹ thuật quan trọng:** `doc.canBeRenamedBy(actor)` và `requireActor` ở đây là domain contract **do app định nghĩa**. Pre-expression tải document trước body nhưng body sau đó có thể query lại. Đối với command có side effect, vẫn cần kiểm tra policy trên entity/trạng thái được dùng để ghi **trong cùng transaction hoặc conditional update**. Việc đặt DB query trong authorization bean phải có giới hạn hiệu năng, xử lý exception fail-closed và không nhầm “không có record” với “được phép”.

Nếu policy chỉ cần authority chung và DTO mode rõ nghĩa, có thể không cần DB lookup trong SpEL. Nếu cần owner/tenant, cân nhắc đặt check trong service khi đã tải object để tránh duplicate reads và TOCTOU.

## 13. Thuộc tính đầu vào đa cấp, collection, Map và enum

Các dạng thường gặp:

```java
// 1. DTO JavaBean: #request.options.format
@PreAuthorize(
    "#request != null and #request.options != null and "
    + "#request.options.format == 'CSV'"
)
public void export(ExportRequest request) { }

// 2. List IDs: chỉ kiểm tra số lượng, CHƯA kiểm tra quyền từng ID.
@PreAuthorize(
    "hasAuthority('document:bulk:read') and "
    + "#ids != null and #ids.size() <= 100"
)
public void readMany(java.util.List<Long> ids) { }

// 3. Map thuộc tính: cú pháp Map access tùy cấu trúc.
@PreAuthorize(
    "#attributes != null and #attributes['visibility'] == 'PUBLIC'"
)
public void changeVisibility(java.util.Map<String, String> attributes) { }
```

Đây là **các snippet tách rời**, không phải một class biên dịch standalone. Chúng cho thấy SpEL có thể xét property/collection/map. Nhưng:
- `ids.size() <= 100` chỉ là giới hạn batch, không chứng minh quyền trên **từng ID**.
- `attributes['visibility'] == 'PUBLIC'` đọc giá trị caller gửi; không chứng minh object được phép publish.
- Enum/property string phải dùng cùng parser/validation với body để tránh bất đồng.
- List/map có thể mutable; caller ngoài service có thể giữ reference và đổi data nếu asynchronous/concurrent.
- Tránh chạy method getter tùy ý/side effect ngay trong security expression.

### Với enum

Giả sử `ExportMode` là enum có `SUMMARY` và `RAW`; trong SpEL có thể tham chiếu class qua `T(com.example.ExportMode).RAW`:

```java
@PreAuthorize(
    "hasAuthority('report:export:raw') and "
    + "#request.mode == T(com.example.ExportMode).RAW"
)
public void exportRaw(ExportRequest request) { }
```

Cần thay package/type bằng class thật trong dự án và kiểm tra parsing ở controller. Việc caller chọn RAW không cho phép bỏ qua resource policy trên report.

## 14. @PreFilter không phải @PreAuthorize

`@PreFilter` là một interceptor khác, được dùng để **lọc tập phần tử đầu vào** trước khi method body chạy, không đơn thuần quyết định ALLOW/DENY toàn method.

Ví dụ theo tài liệu Spring Security:

```java
@PreFilter("filterObject.owner == authentication.name")
public void updateAccounts(
        java.util.Collection<Account> accounts) {
    // Collection truyền vào đã được lọc theo filter expression.
}
```

`filterObject` là phần tử đang được duyệt, không phải toàn `accounts`. Với Map, có thể dùng `filterObject.value` tùy cấu trúc.

**Cảnh báo cho command nhạy cảm:**
- Nếu caller gửi Account DTO với `owner` tự khai, lọc dựa trên trường ấy có thể không chứng minh ownership trong DB.
- Một bulk operation có thể yêu cầu **all-or-nothing**; silently bỏ các phần tử không có quyền và cập nhật phần còn lại có thể trái contract.
- Với danh sách lớn, lọc trong memory gây tốn chi phí; nên kiểm tra tập ID theo tenant/ACL tại data layer.
- Việc prefilter thay đổi tập phần tử thấy trong method; hãy test mutation/return contract theo collection type.
- Không dùng `@PreFilter` như giải pháp mặc định cho mọi BOLA.

Một bulk command an toàn hơn có thể truy vấn tất cả entities theo ID và tenant, xác minh **đủ số lượng**, kiểm tra quyền từng entity và cập nhật trong một transaction. Nếu thiếu một ID, toàn operation DENY/CONFLICT theo hợp đồng.

## 15. @PostAuthorize cũng đọc object nhưng khác thời điểm

Ví dụ:

```java
@PostAuthorize(
    "returnObject.ownerId == authentication.name"
)
public DocumentView readDocument(long id) {
    return repository.getView(id);
}
```

`returnObject` là kết quả **sau** method. Khác với:

```java
@PreAuthorize("#command.documentId != null")
public void rename(RenameDocumentCommand command) { }
```

Trong pre-check, bạn có input mà **chưa có returnObject**; trong post-check, body đã chạy. Spring Security docs không khuyến khích dùng `@PostAuthorize` làm rào chắn chính cho các class ghi DB vì side effect có thể đã xảy ra.

Ví dụ sai:

```java
@PostAuthorize("denyAll()")
public void approveTransfer(ApproveTransferCommand command) {
    paymentGateway.sendMoney(command.getTransferId());
}
```

Method có thể đã gửi tiền trước khi bị DENY. Transaction rollback của DB không nhất thiết hủy được external side effect. Với write cần authorization trước thay đổi, kiểm tra chính sách trên state thật và quản lý concurrency.

## 16. TOCTOU: pre-check đúng tại T1 chưa chắc đúng tại T2

Tình huống:

```text
T1  @PreAuthorize:
    @documentAccess.mayRename(actor, command.docId) == true
         |
         | Một transaction khác chuyển owner/khóa tài liệu.
         v
T2  Method body:
    repository.renameById(command.docId, command.newTitle)
         |
         v
    Quyền đã hết hiệu lực hoặc state không hợp lệ.
```

Đây là **time-of-check/time-of-use**. `@PreAuthorize` không tự bảo đảm snapshot database hoặc lock được giữ tới lúc update.

Cách giảm rủi ro:
1. Đặt check cuối cùng sát operation trong transaction.
2. Load object đúng tenant và khóa/đọc version khi phù hợp.
3. Áp optimistic locking `@Version` hoặc update có điều kiện.
4. Không dùng một input property không có nguồn tin cậy làm bằng chứng owner.
5. Đừng tạo side effect external trước khi đủ quyền và commit policy.
6. Xử lý affected rows = 0 như conflict/deny/not-found, không success.

Ví dụ conditional update cho owner-only:

```sql
UPDATE documents
SET title = :new_title,
    version = version + 1
WHERE id = :document_id
  AND tenant_id = :trusted_tenant_id
  AND owner_id = :authenticated_actor_id
  AND status = 'DRAFT'
  AND version = :expected_version;
```

Điều kiện phải lấy `trusted_tenant_id` và `authenticated_actor_id` từ server context, **không** từ các property caller tự khai. SQL minh họa không thay thế ACL/delegation nếu business cho phép người khác owner chỉnh sửa.

## 17. Lỗi null, typing và biểu thức quá thông minh

Một biểu thức kém bền:

```java
@PreAuthorize(
    "#request.options.format.toUpperCase() == 'CSV'"
)
```

Nếu `request`, `options` hoặc `format` null, có thể lỗi SpEL/runtime. Nếu getter có I/O hoặc throw exception, pre-check cũng có thể lỗi trước body.

Cách rõ hơn:

```java
@PreAuthorize(
    "#request != null and #request.options != null and "
    + "#request.options.format != null and "
    + "#request.options.format.equalsIgnoreCase('CSV')"
)
```

Dù vậy, **input validation** vẫn phải quyết định có chấp nhận case-insensitive CSV, có giá trị khác hoặc blank hay không. Việc SpEL dùng case-insensitive trong khi controller định nghĩa enum case-sensitive có thể tạo hai cách diễn giải.

Một số lỗi thường gặp:
- `#request` sai tên do thiếu `-parameters`.
- `#request.owner` sai JavaBean property.
- `#request.amount` là `String`, lại so sánh như số.
- `authentication.name` là email trong khi ownerId là UUID.
- `#request.tags.contains(...)` gọi trên list null.
- `#request.items.size()` không kiểm tra quyền từng item.
- Một method overloaded có tham số khác kiểu, annotation sao chép không hợp lệ.
- Expression bean `@policy` không tồn tại hoặc method không public/inaccessible theo config.
- Exception ở bean policy bị catch thành `true` hoặc bypass; phải fail closed.

Khi logic rẽ nhánh phức tạp, chuyển vào Java `@Component("policy")` để unit-test và quản lý xử lý null/exception rõ ràng.

## 18. Role hierarchy và input property là hai vấn đề riêng

Role hierarchy có thể định nghĩa:

```text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_USER
```

Một actor có ROLE_ADMIN khi manager đã wire hierarchy có thể vượt `hasRole('USER')`. Nhưng:

```java
@PreAuthorize(
    "hasRole('USER') and #command.ownerId == authentication.name"
)
```

vẫn không an toàn nếu `ownerId` do client gửi. Kế thừa role chỉ làm thay đổi tập authority reachable; nó **không xác minh dữ liệu thực của object**.

Với hệ thống multi-tenant, không để ROLE_ADMIN ở tenant A tự có quyền lên object tenant B. Tạo capability tenant-wide rõ ràng nếu được business phê duyệt, nhưng domain policy vẫn phải xét resource tenant và state.

## 19. Đường HTTP không phải đường duy nhất gọi service

`@PreAuthorize` nằm trên service có lợi vì cùng use case có thể được gọi từ:
- REST controller;
- GraphQL resolver;
- message listener;
- background job/scheduler;
- admin console;
- Spring service khác.

Tuy nhiên, mọi lời gọi phải đi qua Spring proxy/advisor (hoặc cấu hình AspectJ thích hợp). `this.rename(command)` trong cùng class có thể bỏ qua method-security interceptor theo proxy AOP. Object tạo bằng `new` cũng không tự được bảo vệ.

Với các entry point khác nhau, actor context phải đáng tin. Một job không có HTTP principal không có nghĩa được bypass policy; có thể dùng service identity/permission scope phù hợp. Nếu business command có thể bị gọi ngoài method-security boundary, service/domain guard là lớp an toàn bắt buộc.

`@PreAuthorize` trên controller cũng là một cách, nhưng nếu controller khác, job hoặc message handler gọi thẳng service, rule ở controller có thể không áp dụng. Chọn **boundary** chính ở use case và test mọi entry point.

## 20. Java 17+ chạy độc lập: input tự khai và object trong database

Ví dụ sau là **Java thuần mô phỏng** pre-authorization và resource policy; không dùng Spring Security. Mục tiêu là thấy vì sao so thuộc tính `claimedOwner` từ request là sai, còn tải object thật và kiểm tra trusted tenant/owner/permission đưa ra quyết định khác.

Lưu file `InputPropertyAuthorizationDemo.java`:

```java
import java.util.Map;
import java.util.Set;

public class InputPropertyAuthorizationDemo {

    record Actor(String id, String tenant, Set<String> permissions) {}
    record Command(long documentId, String claimedOwner,
                   String claimedTenant, String newTitle) {}
    record Document(long id, String tenant, String owner,
                    boolean locked) {}

    static boolean naivePreCheck(Actor actor, Command command) {
        return actor.permissions().contains("doc:write")
            && actor.id().equals(command.claimedOwner())
            && actor.tenant().equals(command.claimedTenant());
    }

    static String safeDecision(
            Actor actor, Command command, Map<Long, Document> database) {
        if (!actor.permissions().contains("doc:write")) {
            return "DENY permission";
        }
        if (command == null || command.newTitle() == null
                || command.newTitle().isBlank()) {
            return "DENY input";
        }

        Document real = database.get(command.documentId());
        if (real == null) {
            return "DENY not-found";
        }
        if (!actor.tenant().equals(real.tenant())) {
            return "DENY tenant";
        }
        if (real.locked()) {
            return "DENY locked";
        }

        boolean owner = actor.id().equals(real.owner());
        boolean tenantGrant =
            actor.permissions().contains("doc:write:tenant");
        if (!owner && !tenantGrant) {
            return "DENY owner";
        }
        return "ALLOW";
    }

    public static void main(String[] args) {
        Map<Long, Document> db = Map.of(
            42L, new Document(42, "A", "alice", false),
            43L, new Document(43, "A", "alice", true),
            99L, new Document(99, "B", "carol", false)
        );

        Actor alice = new Actor(
            "alice", "A", Set.of("doc:write"));
        Actor bob = new Actor(
            "bob", "A", Set.of("doc:write"));
        Actor manager = new Actor(
            "manager", "A", Set.of(
                "doc:write", "doc:write:tenant"));
        Actor reader = new Actor(
            "reader", "A", Set.of("doc:read"));

        Command forgedOwner = new Command(
            42, "bob", "A", "Tiêu đề bị giả mạo");
        Command wrongClaim = new Command(
            42, "bob", "A", "Tiêu đề hợp lệ");
        Command otherTenant = new Command(
            99, "bob", "A", "Khác tenant");
        Command locked = new Command(
            43, "manager", "A", "Không được sửa");
        Command missing = new Command(
            777, "manager", "A", "Không tồn tại");
        Command blank = new Command(
            42, "manager", "A", "");

        System.out.println("Forged owner naive: "
            + naivePreCheck(bob, forgedOwner));
        System.out.println("Forged owner safe: "
            + safeDecision(bob, forgedOwner, db));
        System.out.println("Owner claim mismatch naive: "
            + naivePreCheck(alice, wrongClaim));
        System.out.println("Owner claim mismatch safe: "
            + safeDecision(alice, wrongClaim, db));
        System.out.println("Cross-tenant safe: "
            + safeDecision(bob, otherTenant, db));
        System.out.println("Tenant grant safe: "
            + safeDecision(manager, forgedOwner, db));
        System.out.println("Locked safe: "
            + safeDecision(manager, locked, db));
        System.out.println("Read-only safe: "
            + safeDecision(reader, forgedOwner, db));
        System.out.println("Missing document safe: "
            + safeDecision(manager, missing, db));
        System.out.println("Blank title safe: "
            + safeDecision(manager, blank, db));
    }
}
```

Biên dịch và chạy JDK 17+:

```bash
javac InputPropertyAuthorizationDemo.java
java InputPropertyAuthorizationDemo
```

Stdout **chính xác**:

```text
Forged owner naive: true
Forged owner safe: DENY owner
Owner claim mismatch naive: false
Owner claim mismatch safe: ALLOW
Cross-tenant safe: DENY tenant
Tenant grant safe: ALLOW
Locked safe: DENY locked
Read-only safe: DENY permission
Missing document safe: DENY not-found
Blank title safe: DENY input
```

Diễn giải:
1. Bob có `doc:write`, tự khai `claimedOwner=bob` và tenant A nên **naive true**, dù document 42 thật thuộc Alice. Đây là false positive nguy hiểm.
2. Safe policy tra document 42 và từ chối Bob vì không phải owner và không có tenant grant.
3. Alice là owner thật, dù client claim sai là Bob; naïve false còn safe ALLOW. Điều này cho thấy client claim **không phải nguồn sự thật**.
4. Bob không được sửa document tenant B dù claim tenant A.
5. Manager có permission tenant-wide đã **chủ động được cấp** có thể sửa document cùng tenant, nhưng không tự bỏ qua state.
6. Document khóa vẫn DENY.
7. Reader chỉ có read không được write.
8. ID không tồn tại bị từ chối.
9. Title rỗng bị từ chối trước thao tác.

**Giới hạn demo:** `Map` là database giả, actor là test fixture, `safeDecision` không sử dụng Authentication/JPA/transaction/locking thật và hoàn toàn không sửa state. Không copy `naivePreCheck` vào production. Trong hệ thống thật, actor phải đến từ security context đáng tin và data query phải có tenant scope, transaction/conditional update phù hợp.

## 21. Unit test policy theo nhiều thuộc tính

Khi tách policy khỏi annotation, viết unit test trực tiếp:

```java
@Test
void editorCannotRenameDocumentOwnedByOtherUser() {
    Actor actor = actor("bob", "tenant-A", "document:rename");
    Document doc = document(42L, "tenant-A", "alice", "DRAFT");

    assertThat(policy.canRename(actor, doc)).isFalse();
}

@Test
void editorCannotRenameCrossTenantDocument() {
    Actor actor = actor("alice", "tenant-A", "document:rename");
    Document doc = document(99L, "tenant-B", "alice", "DRAFT");

    assertThat(policy.canRename(actor, doc)).isFalse();
}

@Test
void ownerCannotRenameLockedDocument() {
    Actor actor = actor("alice", "tenant-A", "document:rename");
    Document doc = document(43L, "tenant-A", "alice", "LOCKED");

    assertThat(policy.canRename(actor, doc)).isFalse();
}
```

`actor`, `document` và `policy` là **test fixture/domain API tự thiết kế**, không phải class sẵn có của Spring. Đây là snippets JUnit 5/AssertJ trong dự án đã có dependencies.

Độ bao phủ test cần ít nhất:
- Input null và property null.
- ID âm/rỗng/không tồn tại.
- Sai tenant, đúng owner và ngược lại.
- Đúng authority nhưng không owner.
- Owner nhưng thiếu authority.
- Role cao nhưng thiếu grant theo scope.
- Trạng thái LOCKED/ARCHIVED.
- Duplicate IDs, batch request và phần tử không được phép.
- Command field giả mạo `claimedOwnerId`/`tenantId`/`approvedBy`.
- Concurrency/version thay đổi trước khi update.

## 22. Integration test: @PreAuthorize có chạy trước body không?

Với Spring Test, gọi service bean qua proxy và dùng `@WithMockUser` hoặc request post processor:

```java
import org.junit.jupiter.api.Test;
import org.springframework.security.test.context.support.WithMockUser;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class DocumentCommandSecurityTest {

    private DocumentCommandService service; // Inject từ Spring context

    @Test
    @WithMockUser(authorities = {"document:read"})
    void readOnlyUserDeniedBeforeRename() {
        RenameDocumentCommand cmd =
            new RenameDocumentCommand(42L, "New title");

        assertThatThrownBy(() -> service.rename(cmd))
            .isInstanceOf(
                org.springframework.security.access.AccessDeniedException.class
            );
    }
}
```

Đây là **đoạn test minh họa**: trong dự án thật dùng `@SpringBootTest`/`@ContextConfiguration`, `@Autowired` cho bean service, fixtures, entity/transaction repositories. Không dùng `new DocumentCommandService(...)` nếu muốn kiểm tra interception.

Cần verify thêm `repository.save/rename` **không được gọi** khi pre-authorize DENY. Khi role đủ nhưng sai owner, nên xác minh policy trong service từ chối và DB không đổi.

**Dương tính giả:** Một test HTTP POST nhận 403 vì thiếu CSRF token không chứng minh `@PreAuthorize` hay ownership policy. Với MockMvc và CSRF enabled, cung cấp token hợp lệ cho request write rồi kiểm tra đúng checkpoint.

## 23. Test parameter names: đừng chỉ test method có một tham số

Ví dụ:

```java
@PreAuthorize(
    "hasAuthority('document:rename') and "
    + "#command != null and #command.documentId != null"
)
public void rename(String auditReason, RenameDocumentCommand command) {
    // ...
}
```

Nếu compile không có `-parameters`, `#command` có thể không được resolve; nếu dùng alias theo vị trí `#p0`, nó lại trỏ đến `auditReason`. Tác động có thể là deny không mong đợi hoặc cấu hình lỗi.

Test cần:
- Gọi qua Spring proxy với đúng build toolchain production.
- Bật `-parameters` hoặc dùng `@P("command")` tường minh.
- Test overload có nhiều tham số.
- Test interface method có @P khác implementation.
- Test dữ liệu null.
- Nếu app Kotlin, kiểm tra metadata/compiler và proxy final class theo version.
- Không fix lỗi parameter binding bằng cách đổi sang đọc raw request body trong SpEL.

## 24. MockMvc: kết hợp HTTP và method security đúng cách

Ví dụ request:

```http
PATCH /api/documents/42
Content-Type: application/json

{"newTitle":"Title", "claimedOwnerId":"alice"}
```

Một test đúng cần:
- Actor xác thực với authority `document:rename`.
- CSRF token nếu session-based security bật.
- Entity trong DB có owner/tenant cụ thể.
- Gửi claimedOwnerId **khác** entity owner để thử over-posting.
- Kiểm tra status 403/404 tùy contract.
- Kiểm tra document trong DB không bị đổi.
- Kiểm tra service policy được gọi bằng resource owner thật, không chỉ DTO.

Ví dụ snippets:

```java
// Cần MockMvc, spring-security-test, fixture tài liệu 42,
// controller PATCH thật và cấu hình CSRF phù hợp.
mvc.perform(patch("/api/documents/42")
        .with(user("bob").authorities(
            new SimpleGrantedAuthority("document:rename")
        ))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"newTitle":"Forged","claimedOwnerId":"bob"}
            """))
   .andExpect(status().isForbidden());
```

Trong dự án thật imports tương ứng gồm `patch`, `user`, `csrf`, `status`, `MediaType` và `SimpleGrantedAuthority`. Nếu API JWT stateless và CSRF disable theo thiết kế, cách test sẽ khác; không dùng CSRF token giả để “sửa” authorization.

Cần test case ALLOW đối chứng với owner đúng quyền, sau đó mới có bằng chứng request DENY không phải do route không tồn tại hay authentication sai.

## 25. Property-based testing cho DTO authorization

Một bộ test cố định dễ bỏ sót biến thể:
- Nhiều giá trị query/case/whitespace trước khi bind DTO.
- Field ownerId/tenantId bị thiếu hoặc null.
- Map/list bị rỗng hoặc chứa ID khác tenant.
- Object nested null ở nhiều độ sâu.
- Mức tiền âm/quá lớn/precision vượt giới hạn.
- Enum mode không tồn tại hoặc đổi default.
- Payload có field thừa (mass assignment).
- DTO immutable hay mutable, có setter sau pre-check.
- Controller và service parse một format theo hai cách.
- Resource owner thay đổi giữa T1 pre-check và T2 write.

Có thể viết property tests:
1. Với mọi actor thiếu permission chức năng, command phải bị DENY.
2. Với mọi document ngoài tenant đã xác minh, command phải bị DENY bất kể client claim.
3. Với mọi document locked, command write phải bị DENY.
4. Với mọi command thiếu field bắt buộc, không được tạo side effect.
5. Với một capability RAW, user chỉ có SUMMARY không được kích hoạt RAW qua bất kỳ mode alias nào.
6. Đổi client claimedOwner/claimedTenant **không làm thay đổi quyết định** nếu server-side actor/resource không đổi.

**Bằng chứng mạnh nhất cho chống IDOR:** thay ID tới resource khác owner/tenant trong cùng endpoint, giữ các field còn lại do attacker tùy ý, và xác nhận **không lộ/không sửa resource**.

## 26. Lỗi security expression và cách chẩn đoán

Những nguyên nhân có thể khiến method không chạy:
- Thiếu `@EnableMethodSecurity` và annotation chưa có tác dụng.
- Bean được gọi không qua proxy.
- `#command` không tìm thấy do parameter metadata.
- Getter/property sai tên hoặc null.
- `@documentPolicy` bean sai name hoặc chưa có.
- Custom policy throw exception khi DB lỗi.
- Authentication không chứa authority cần thiết.
- Role hierarchy chưa được nối với expression handler.
- Owner/tenant policy thật từ chối đúng.
- Method-level annotation override class-level rule theo cách không dự kiến.
- Một `@PostAuthorize`/advisor khác từ chối sau body.
- Exception handler chuyển authorization exception sang response khác.

Không dùng một HTTP status 403 để suy ra ngay lỗi ở `#command`. Với test:
1. Ghi nhận direct authorities và actor identity (không log token).
2. Kiểm tra compiler `-parameters` hoặc `@P`.
3. Xác minh method qua Spring proxy.
4. Unit-test SpEL/policy bean bằng fixture.
5. Kiểm tra đã tải đúng resource owner/tenant.
6. Với write, assert DB và external side effects không đổi khi DENY.

Không đưa raw JWT, password, payment details hay nội dung nhạy cảm vào log; có thể audit actor ID, action, resource ID và reason code an toàn.

## 27. Khi nào không nên kiểm tra thuộc tính input trong annotation?

Một số trường hợp nên chuyển toàn bộ hoặc phần lớn logic sang domain service:
- Quyền phụ thuộc dữ liệu DB vừa thay đổi.
- Cần kiểm tra nhiều resource cùng transaction.
- Có owner, ACL, tenant inheritance, delegation, workflow phức tạp.
- Command cần locking/version và invariant nhất quán.
- Logic liên quan số tiền và hạn mức có thể thay đổi giữa request.
- Có policy “không được tự duyệt” cần so với creator thật.
- Cần trả decision reason/audit chi tiết.
- Cần sử dụng cùng logic ở HTTP, GraphQL, scheduler, message consumer.
- Biểu thức SpEL đã dài và khó kiểm thử.

Ví dụ đơn giản:

```java
@PreAuthorize("hasAuthority('payment:approve')")
@Transactional
public void approve(ApprovePaymentCommand command) {
    Actor actor = actors.requireAuthenticatedActor();
    Payment payment = payments.findForUpdateInTenant(
        command.getPaymentId(), actor.activeTenantId()
    ).orElseThrow(PaymentNotFoundException::new);

    policy.requireCanApprove(actor, payment);
    payment.approveBy(actor.id());
}
```

Snippet này cần domain contracts, không phải standalone Java. Nếu client gửi `approvedBy` hoặc `creatorId`, những field ấy không được xem là quyết định cuối cùng; policy dùng giá trị lưu trữ và principal tin cậy.

## 28. Bảng anti-pattern và cách sửa

| Anti-pattern | Vì sao nguy hiểm | Hướng đúng |
| --- | --- | --- |
| `#dto.ownerId == authentication.name` | ownerId có thể do client giả mạo | Tải owner thật từ DB |
| `#dto.tenantId == principal.tenantId` | Document ID có thể thuộc tenant khác | Query entity theo tenant đã xác minh |
| Chỉ `#ids.size() <= 100` cho bulk delete | Không kiểm tra quyền từng ID | Tải/scoped và authorize từng object |
| Chỉ `hasRole('ADMIN')` rồi update by ID | Bỏ qua tenant/owner/ACL/state | Domain policy có scope |
| `@PostAuthorize` trên write làm guard chính | Method có thể đã ghi dữ liệu | Pre-check + transactional guard |
| Getter DTO có side effect | Security expression không thuần túy | DTO immutable/thuần data |
| Dựa vào `authentication.name` là UUID | Identity format có thể khác | Actor resolver và ID chuẩn hóa |
| Không bật `-parameters` | `#command` không resolve | Compiler flag/`@P` và test |
| SpEL dùng nested property không null-check | Exception không mong đợi | Null guard, validation, bean policy |
| Catch lỗi policy rồi trả true | Fail-open | Fail-closed + proper exception handling |
| Over-posting role/admin/owner fields | Client tự sửa đặc quyền | DTO allowlist + domain invariant |
| Policy chỉ ở controller | Job/GraphQL có thể bypass | Use-case policy |
| Service tự gọi `this.securedMethod()` | Proxy advice có thể không chạy | Bảo vệ boundary và domain guard |
| Test 403 không có CSRF | Dương tính giả | Request hợp lệ và verify điểm DENY |
| Expression lớn nhiều nhánh | Khó review, bị lệch body | `@Component` policy Java testable |
| Check DB trong pre-expression rồi ghi sau lâu | TOCTOU | Check sát thời điểm dùng, version/lock |
| Chỉ test quyền thấp thiếu role | Không bắt IDOR/BOLA | Test actor đủ role nhưng sai owner/tenant |

## 29. Checklist trước khi merge một @PreAuthorize trên input object

1. Service method được Spring quản lý và được gọi qua proxy hay không?
2. `@EnableMethodSecurity` đã bật trong context thật chưa?
3. Annotation ở method, class/interface hay meta-annotation, có override không?
4. Tên biến `#command` có resolve bằng `-parameters`/`@P` không?
5. DTO JavaBean property names có đúng không?
6. Null/nested properties được xử lý an toàn chưa?
7. Điều kiện trên input là **yêu cầu chức năng** hay đang giả mạo bằng chứng quyền?
8. Authentication/principal có được xác thực và chuẩn hóa thành Actor ổn định chưa?
9. Owner/tenant/role từ payload có được tin sai là giá trị DB không?
10. Method body có dùng chính giá trị đã kiểm tra hay một alias/default khác?
11. Có collection/map/enum phức tạp cần policy bean không?
12. Quyền có áp dụng cho **mọi object** trong bulk request chưa?
13. Tenant được xác minh bằng membership thật chưa?
14. Có query resource scope và ACL/owner check đúng không?
15. Command thay đổi dữ liệu có kiểm tra ngay trước side effect không?
16. Có rủi ro TOCTOU, locking/version/conditional update không?
17. Một method được gọi qua HTTP và ngoài HTTP có dùng cùng policy không?
18. Có thử attacker giả mạo ownerId/tenantId/approvedBy trong DTO chưa?
19. Có test input null, malformed, nested null và method overload không?
20. Có test user đủ role nhưng khác tenant/owner không?
21. Có test owner đúng nhưng thiếu authority không?
22. Có kiểm tra state không đổi sau DENY không?
23. Test HTTP có loại trừ CSRF/404/405 như nguyên nhân giả không?
24. Error và logs có giữ bí mật dữ liệu resource không?
25. Chính sách có thể được giải thích và review bằng tên permission cụ thể không?

### Câu hỏi tự kiểm tra

**Câu 1.** `@PreAuthorize("#command.ownerId == authentication.name")` có đủ bảo vệ quyền sở hữu document không?  
→ **Không**, nếu `ownerId` do client gửi. Cần đối chiếu document owner thật và tenant scope.

**Câu 2.** Tham số Java tên `command` nhưng SpEL `#command` null trong Spring Framework 6.1+; cần kiểm tra gì?  
→ Compiler `-parameters`, `@P("command")`, interface/method signature và runtime argument binding.

**Câu 3.** Có thể dùng `#command.options.format` để quyết định quyền export RAW không?  
→ **Có thể**, nếu input được parse/validate nhất quán, body thực hiện đúng mode và report thật vẫn qua domain policy.

**Câu 4.** `@PreFilter("filterObject.owner == authentication.name")` có tương đương với DENY toàn bộ bulk operation khi có một account không được phép không?  
→ **Không**. Nó lọc phần tử; với all-or-nothing cần verify toàn tập.

**Câu 5.** `hasRole('ADMIN')` hoặc role hierarchy có xác nhận object thuộc tenant admin không?  
→ **Không**. Phải kiểm tra tenant/resource scope riêng.

**Câu 6.** Pre-check đã query DB thấy owner Alice, rồi owner đổi trước update. Có đảm bảo quyền vẫn đúng không?  
→ **Không**. Cần transaction, lock/version hoặc conditional update phù hợp.

**Câu 7.** `authentication.name` có luôn bằng `ownerId` dạng UUID trong DB không?  
→ **Không**. Cần chuẩn hóa identity từ principal tin cậy.

**Câu 8.** Nếu method có `@PreAuthorize` nhưng được gọi bởi `this.method()` trong cùng bean, có chắc advice chạy không?  
→ **Không** trong proxy-AOP thông dụng. Phải xác minh boundary và có domain guard bắt buộc.

**Câu 9.** Một test POST trả 403 khi không có CSRF token có chứng minh `@PreAuthorize` đã DENY không?  
→ **Không**. Phải phân biệt `CsrfFilter` và method security.

**Câu 10.** Đâu là test tốt nhất để phát hiện IDOR với DTO?  
→ Actor có authority hợp lệ nhưng gửi ID resource của người khác, giả mạo các field owner/tenant tùy ý, và verify không có data leak hay side effect.

## Kết luận

`@PreAuthorize` có thể dùng SpEL truy cập thuộc tính của đối tượng đầu vào qua `#command.property`, phân loại request và gọi policy bean **trước khi method body chạy**. Nhưng DTO, path ID, ownerId, tenantId, status hoặc vai trò do client tự gửi **không phải chứng cứ authorization**. Thiết kế an toàn kết hợp **authority chức năng từ Authentication tin cậy**, **thuộc tính input được validate đúng semantics**, **entity/tenant/owner/ACL từ server**, **policy kiểm tra ở điểm sử dụng dữ liệu**, và **test negative kể cả khi caller đủ role**. Khi logic phức tạp hoặc có write, đưa quyết định vào service/domain policy trong transaction thay vì chỉ dựa vào một SpEL ngắn.

## Tài liệu tham khảo chính thức

1. [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html) — `@PreAuthorize`, `MethodSecurityExpressionHandler`, method parameters, bean authorization, `@PreFilter` và `@PostAuthorize`.
2. [Spring Security 6.5 — Authorization Migrations](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/authorization.html) — yêu cầu compiler `-parameters` sau khi Spring Framework 6.1 bỏ LocalVariableTableParameterNameDiscoverer.
3. [Spring Security 6.5 — Method Security Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html) — `@WithMockUser` và test method interception.
4. [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html) — authority, role và policy.
5. [Spring Security 6.5 — Domain Object Security (ACL)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html) — quyền trên object và `PermissionEvaluator`.
6. [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html) — HTTP security và phạm vi riêng với method security.
