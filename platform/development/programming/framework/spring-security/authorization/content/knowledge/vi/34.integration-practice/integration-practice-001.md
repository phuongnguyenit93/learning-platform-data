# Dựng ma trận quyền cho ứng dụng quản lý tài liệu nhiều người dùng

## Mục tiêu học tập và bài toán thực hành

Một ứng dụng quản lý tài liệu có nhiều người dùng không thể chỉ kiểm tra `authenticated()` hoặc một vai trò toàn cục rồi cho mở mọi tài liệu. Quyết định còn phụ thuộc **tenant, chủ sở hữu, người được chia sẻ, loại tài liệu, trạng thái và thao tác**. Bài thực hành này xây dựng một **ma trận quyền có thể kiểm thử**, rồi ánh xạ nó vào Spring Security và truy vấn dữ liệu.

Sau bài, người học có thể: xác định subject/resource/action/context; lập bảng PERMIT/DENY cho mỗi quan hệ với tài liệu; thiết lập thứ tự điều kiện deny; viết chương trình Java 17 chạy độc lập tính quyền; phác thảo cấu hình Spring Security 6.x; thiết kế test HTTP, database, chia sẻ/revoke và phân trang; đánh giá các lỗi IDOR, vượt tenant, quyền thừa và rò rỉ dữ liệu.

**Các role và policy sau đây là quy tắc minh họa của một ứng dụng giả định**, không phải chức năng tự có của Spring Security. Với hệ thống thật, phải chốt chúng với chủ sở hữu nghiệp vụ trước khi viết code.

## 1. Thiết kế miền nghiệp vụ “Document Hub”

Ứng dụng phục vụ nhiều tổ chức (multi-tenant). Người dùng phải có membership hợp lệ mới truy cập tài liệu của tenant đó. Tài liệu có một owner, có thể chia sẻ thêm quyền VIEWER/EDITOR cho thành viên cùng tenant. Một tenant có ADMIN quản trị; các thành viên MEMBER có thể tạo tài liệu.

| Thành phần | Trường dữ liệu | Ý nghĩa bảo mật |
| --- | --- | --- |
| Principal | `userId`, trạng thái xác thực, membership, role theo tenant | Danh tính phải được server kiểm chứng |
| Document | `id`, `tenantId`, `ownerId`, `visibility`, `classification`, `status` | Nguồn sự thật về quan hệ và trạng thái tài liệu |
| ACL | `documentId`, `granteeId`, `grant`, `expiresAt`, `revokedAt` | Quyền bổ sung theo từng tài liệu |
| Action | `READ`, `DOWNLOAD`, `EDIT`, `DELETE`, `SHARE`, `RESTORE` | Mỗi hành động có quyền riêng, không gom thành “có thể mở” |
| Context | Tenant đang xác thực, thời gian, MFA/policy version nếu có | Dùng khi policy thực tế yêu cầu |

Hai tầng role/quyền không được nhầm:

- **TENANT_ADMIN**: role quản trị **trong một tenant**. Ở ví dụ này, admin xem và quản lý tài liệu ACTIVE của tenant, kể cả không phải owner; admin **không** vượt tenant.
- **MEMBER**: thành viên tenant, có thể tạo tài liệu; với từng tài liệu, mức quyền phụ thuộc quan hệ owner, ACL hoặc visibility.
- **Owner**: quan hệ `document.ownerId == user.id`, **không phải** `ROLE_OWNER` toàn cục. Alice có thể là owner của D101 nhưng là viewer của D102.
- **ACL EDITOR**: được READ/DOWNLOAD/EDIT tài liệu ACTIVE, **không** tự được DELETE hoặc SHARE.
- **ACL VIEWER**: được READ/DOWNLOAD, không được EDIT/DELETE/SHARE.

Dùng `hasRole("MEMBER")` để cho phép sửa bất kỳ documentId là sai: nó chỉ xác nhận membership/authority ở một mức, chưa chứng minh user là owner hoặc được ACL EDITOR.

### 1.1. Visibility, classification và status

Ví dụ chốt ba chiều độc lập:

1. `visibility = PRIVATE`: chỉ owner, người được cấp ACL hoặc admin **cùng tenant** được đọc.
2. `visibility = TEAM`: thành viên tenant được READ/DOWNLOAD nếu tài liệu có `classification = INTERNAL`. TEAM không cấp quyền EDIT/DELETE/SHARE cho mọi member.
3. `classification = CONFIDENTIAL`: chỉ cho `PRIVATE`. Cặp `CONFIDENTIAL + TEAM` không hợp lệ: validation phải từ chối khi tạo/sửa, policy đọc cũng từ chối an toàn nếu database chứa dữ liệu lỗi.
4. `status = ACTIVE`: áp dụng ma trận tác vụ thông thường.
5. `status = ARCHIVED`: user vốn có quyền đọc vẫn READ/DOWNLOAD; không ai được EDIT/DELETE/SHARE khi chưa restore. Chỉ TENANT_ADMIN cùng tenant được RESTORE. Owner không tự restore trong policy minh họa.

Tenant isolation là ranh giới chặn mạnh hơn ACL: ngay cả khi ACL của D101 vô tình có grantee ở tenant B, grantee đó vẫn bị từ chối. Mọi quyết định cần áp đủ ràng buộc đã thống nhất.

### 1.2. Quy tắc riêng khi CREATE

`CREATE` chưa có tài liệu để so owner/ACL, nên kiểm tra người đang xác thực có role MEMBER hoặc TENANT_ADMIN trong tenant đích. Server tự gán `ownerId` và `tenantId` dựa trên principal/membership, không cho client gửi `ownerId=alice` hay `tenantId=otherTenant` để tự nhận quyền. Một role MEMBER tại tenant A không được tạo dữ liệu ở tenant B.

## 2. Ma trận quyền chuẩn theo quan hệ với tài liệu

Ký hiệu **Y** = cho phép; **N** = từ chối. Bảng sau áp dụng khi tài liệu **ACTIVE**, tenant/identity hợp lệ, không có dữ liệu vi phạm classification/visibility.

| Quan hệ caller với tài liệu | READ | DOWNLOAD | EDIT | DELETE | SHARE | RESTORE |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| TENANT_ADMIN cùng tenant | Y | Y | Y | Y | Y | N |
| Owner cùng tenant | Y | Y | Y | Y | Y | N |
| ACL EDITOR cùng tenant | Y | Y | Y | N | N | N |
| ACL VIEWER cùng tenant | Y | Y | N | N | N | N |
| MEMBER không có ACL, tài liệu TEAM + INTERNAL | Y | Y | N | N | N | N |
| MEMBER không có ACL, tài liệu PRIVATE | N | N | N | N | N | N |
| User khác tenant | N | N | N | N | N | N |
| Anonymous/chưa xác thực | N | N | N | N | N | N |

Với tài liệu **ARCHIVED**, quy tắc là:

| Quan hệ trong tenant với ARCHIVED | READ | DOWNLOAD | EDIT | DELETE | SHARE | RESTORE |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| TENANT_ADMIN | Y | Y | N | N | N | Y |
| Owner | Y | Y | N | N | N | N |
| ACL EDITOR hoặc VIEWER | Y | Y | N | N | N | N |
| MEMBER thấy tài liệu TEAM + INTERNAL | Y | Y | N | N | N | N |
| MEMBER không có quyền đọc / khác tenant / anonymous | N | N | N | N | N | N |

**Ưu tiên quyết định** (deny trước permit): kiểm tra authentication và active tenant membership → tenant tài liệu phải khớp → dữ liệu/visibility/classification phải hợp lệ → kiểm tra status → xét admin/owner/ACL/TEAM theo từng action → action không biết hoặc thiếu thuộc tính được **DENY mặc định**.

Không được hiểu “đã có một grant” là bỏ qua các ràng buộc tenant, status hoặc classification. Một ACL EDITOR bị thu hồi hay hết hạn không còn giá trị, kể cả cache chưa kịp cập nhật. Phải định nghĩa rõ thời điểm hiệu lực ACL nếu sản phẩm có expiry.

## 3. Fixture nhiều người dùng để kiểm thử

Tạo hai tenant t-a và t-b; các actor:

| Actor | Tenant xác thực | Vai trò | Mục đích test |
| --- | --- | --- | --- |
| `alice` | t-a | MEMBER | Owner của D101, D105; VIEWER của D102; EDITOR của D104 |
| `bob` | t-a | MEMBER | Owner D102–D104 |
| `dave` | t-a | TENANT_ADMIN | Quyền admin giới hạn trong tenant |
| `erin` | t-a | MEMBER | Không có ACL, chỉ xem TEAM |
| `mallory` | t-b | MEMBER | Owner D201; thử request vượt tenant |
| anonymous | Không có membership xác thực | — | Chứng minh TEAM không phải tài liệu public Internet |

Tạo tài liệu:

| ID | Tenant | Owner | Visibility | Classification | Status | ACL riêng |
| --- | --- | --- | --- | --- | --- | --- |
| D101 | t-a | alice | PRIVATE | INTERNAL | ACTIVE | không có |
| D102 | t-a | bob | PRIVATE | CONFIDENTIAL | ACTIVE | alice = VIEWER |
| D103 | t-a | bob | TEAM | INTERNAL | ACTIVE | không có |
| D104 | t-a | bob | PRIVATE | INTERNAL | ACTIVE | alice = EDITOR |
| D105 | t-a | alice | PRIVATE | INTERNAL | ARCHIVED | không có |
| D201 | t-b | mallory | PRIVATE | INTERNAL | ACTIVE | không có |

**Ma trận kết quả cụ thể** cho fixture:

| Actor / tài liệu | READ | DOWNLOAD | EDIT | DELETE | SHARE | RESTORE | Lý do |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | --- |
| alice / D101 | Y | Y | Y | Y | Y | N | Owner, ACTIVE |
| alice / D102 | Y | Y | N | N | N | N | ACL VIEWER |
| alice / D103 | Y | Y | N | N | N | N | TEAM + INTERNAL |
| alice / D104 | Y | Y | Y | N | N | N | ACL EDITOR |
| alice / D105 | Y | Y | N | N | N | N | ARCHIVED |
| alice / D201 | N | N | N | N | N | N | Khác tenant |
| dave / D102 | Y | Y | Y | Y | Y | N | ADMIN cùng tenant, ACTIVE |
| dave / D105 | Y | Y | N | N | N | Y | Chỉ ADMIN được RESTORE |
| erin / D103 | Y | Y | N | N | N | N | TEAM, không có ACL |
| erin / D101 | N | N | N | N | N | N | PRIVATE |
| mallory / D201 | Y | Y | Y | Y | Y | N | Owner tenant B |
| mallory / D101 | N | N | N | N | N | N | Tenant B khác A |
| anonymous / D103 | N | N | N | N | N | N | Chưa đăng nhập |

Trong một dự án thật, ma trận phải được version-control cùng policy và test fixtures. Khi nghiệp vụ thêm quyền `APPROVE`, `PUBLISH`, `TRANSFER_OWNERSHIP` hay phân loại `SECRET`, tạo cột/điều kiện và test trước khi mở endpoint.

## 4. Chương trình Java 17 chạy độc lập mô phỏng ma trận

Chương trình này **không cần Spring**. Nó cho thấy cách nhận actor, document, action và trả kết quả mặc định từ chối. Đây là mô hình phục vụ học tập; dữ liệu gán trong `main` phải được thay bằng claims đã kiểm chứng, DB và ACL khi làm ứng dụng thật.

Lưu đúng tên file `DocumentMatrixDemo.java`:

```java
import java.util.Map;
import java.util.Objects;

public class DocumentMatrixDemo {
    enum Action { READ, DOWNLOAD, EDIT, DELETE, SHARE, RESTORE }
    enum Visibility { PRIVATE, TEAM }
    enum Classification { INTERNAL, CONFIDENTIAL }
    enum Status { ACTIVE, ARCHIVED }
    enum Grant { VIEWER, EDITOR }

    record Actor(String id, String tenant, boolean admin,
                 boolean authenticated) {}

    record Document(long id, String tenant, String owner,
                    Visibility visibility, Classification classification,
                    Status status, Map<String, Grant> acl) {}

    static boolean permitted(Actor actor, Document doc, Action action) {
        if (actor == null || doc == null || action == null
                || !actor.authenticated()
                || !Objects.equals(actor.tenant(), doc.tenant())) {
            return false;
        }

        if (doc.classification() == Classification.CONFIDENTIAL
                && doc.visibility() == Visibility.TEAM) {
            return false; // Không PERMIT khi dữ liệu chính sách không hợp lệ
        }

        boolean admin = actor.admin();
        boolean owner = actor.id().equals(doc.owner());
        Grant grant = doc.acl().get(actor.id());

        boolean readable = admin || owner || grant != null
                || (doc.visibility() == Visibility.TEAM
                    && doc.classification() == Classification.INTERNAL);

        if (doc.status() == Status.ARCHIVED) {
            return switch (action) {
                case READ, DOWNLOAD -> readable;
                case RESTORE -> admin;
                default -> false;
            };
        }

        if (doc.status() != Status.ACTIVE) return false;

        return switch (action) {
            case READ, DOWNLOAD -> readable;
            case EDIT -> admin || owner || grant == Grant.EDITOR;
            case DELETE, SHARE -> admin || owner;
            case RESTORE -> false;
        };
    }

    static void print(String label, Actor actor, Document doc) {
        System.out.print(label + ":");
        for (Action action : Action.values()) {
            System.out.print(" " + action + "="
                    + (permitted(actor, doc, action) ? "Y" : "N"));
        }
        System.out.println();
    }

    public static void main(String[] args) {
        Actor alice = new Actor("alice", "t-a", false, true);
        Actor dave = new Actor("dave", "t-a", true, true);
        Actor erin = new Actor("erin", "t-a", false, true);
        Actor mallory = new Actor("mallory", "t-b", false, true);
        Actor anonymous = new Actor("anonymous", "t-a", false, false);

        Document d101 = new Document(101, "t-a", "alice",
                Visibility.PRIVATE, Classification.INTERNAL,
                Status.ACTIVE, Map.of());
        Document d102 = new Document(102, "t-a", "bob",
                Visibility.PRIVATE, Classification.CONFIDENTIAL,
                Status.ACTIVE, Map.of("alice", Grant.VIEWER));
        Document d103 = new Document(103, "t-a", "bob",
                Visibility.TEAM, Classification.INTERNAL,
                Status.ACTIVE, Map.of());
        Document d104 = new Document(104, "t-a", "bob",
                Visibility.PRIVATE, Classification.INTERNAL,
                Status.ACTIVE, Map.of("alice", Grant.EDITOR));
        Document d105 = new Document(105, "t-a", "alice",
                Visibility.PRIVATE, Classification.INTERNAL,
                Status.ARCHIVED, Map.of());
        Document d201 = new Document(201, "t-b", "mallory",
                Visibility.PRIVATE, Classification.INTERNAL,
                Status.ACTIVE, Map.of());

        print("alice D101", alice, d101);
        print("alice D102", alice, d102);
        print("alice D103", alice, d103);
        print("alice D104", alice, d104);
        print("alice D105", alice, d105);
        print("alice D201", alice, d201);
        print("dave D105", dave, d105);
        print("erin D103", erin, d103);
        print("erin D101", erin, d101);
        print("mallory D201", mallory, d201);
        print("mallory D101", mallory, d101);
        print("anonymous D103", anonymous, d103);
    }
}
```

Biên dịch và chạy:

```bash
javac DocumentMatrixDemo.java
java DocumentMatrixDemo
```

Stdout chính xác:

```text
alice D101: READ=Y DOWNLOAD=Y EDIT=Y DELETE=Y SHARE=Y RESTORE=N
alice D102: READ=Y DOWNLOAD=Y EDIT=N DELETE=N SHARE=N RESTORE=N
alice D103: READ=Y DOWNLOAD=Y EDIT=N DELETE=N SHARE=N RESTORE=N
alice D104: READ=Y DOWNLOAD=Y EDIT=Y DELETE=N SHARE=N RESTORE=N
alice D105: READ=Y DOWNLOAD=Y EDIT=N DELETE=N SHARE=N RESTORE=N
alice D201: READ=N DOWNLOAD=N EDIT=N DELETE=N SHARE=N RESTORE=N
dave D105: READ=Y DOWNLOAD=Y EDIT=N DELETE=N SHARE=N RESTORE=Y
erin D103: READ=Y DOWNLOAD=Y EDIT=N DELETE=N SHARE=N RESTORE=N
erin D101: READ=N DOWNLOAD=N EDIT=N DELETE=N SHARE=N RESTORE=N
mallory D201: READ=Y DOWNLOAD=Y EDIT=Y DELETE=Y SHARE=Y RESTORE=N
mallory D101: READ=N DOWNLOAD=N EDIT=N DELETE=N SHARE=N RESTORE=N
anonymous D103: READ=N DOWNLOAD=N EDIT=N DELETE=N SHARE=N RESTORE=N
```

**Cách đọc:** D104 cho Alice EDIT=Y vì ACL EDITOR, nhưng SHARE=N và DELETE=N. D105 vẫn READ=Y đối với owner, nhưng bị chặn EDIT vì ARCHIVED. D201 bị chặn với Alice dù ID được đoán đúng; không dựa vào việc client “biết ID” để mở quyền. Chương trình thuần không xác minh nguồn dữ liệu: production phải chặn null ACL, account disabled, grant revoked/expired và mọi trạng thái không nhận diện trước khi cấp quyền.

## 5. Tích hợp chính sách với Spring Security

### 5.1. Giới hạn request trước khi kiểm quyền trên từng tài liệu

Một cấu hình **minh họa cho Spring Boot 3.x, Spring Security 6.x, Servlet MVC**. Các đoạn sau là snippet tích hợp, không phải project Java đầy đủ; import/bean và endpoint cụ thể do ứng dụng cung cấp.

```java
@Configuration
@EnableMethodSecurity
class SecurityConfiguration {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/documents")
                    .hasAnyRole("MEMBER", "TENANT_ADMIN")
                .requestMatchers("/api/documents/**").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

`authenticated()` chỉ chặn anonymous; một thành viên tenant A vẫn có thể gửi GET `/api/documents/201` đến filter. **Kiểm tra quyền theo documentId phải tiếp tục tại service**. `hasAnyRole` giả định authority `ROLE_MEMBER`/`ROLE_TENANT_ADMIN`; nếu JWT converter khác, phải kiểm tra `GrantedAuthority` thực tế. `httpBasic` chỉ để minh họa authentication; ứng dụng dùng session/JWT cần cấu hình tương ứng. Nếu dùng session/cookie, yêu cầu thay đổi trạng thái phải qua CSRF; không tắt CSRF chỉ để phép thử POST/PUT thành công.

### 5.2. Policy service có chung một hợp đồng quyết định

Có thể dùng `@PreAuthorize` trên Spring-managed service; ví dụ:

```java
@Component("documentPolicy")
public class DocumentPolicy {
    private final DocumentAccessRepository access;
    private final TenantIdentity tenantIdentity;

    public DocumentPolicy(
            DocumentAccessRepository access,
            TenantIdentity tenantIdentity) {
        this.access = access;
        this.tenantIdentity = tenantIdentity;
    }

    public boolean permits(Authentication principal,
                           long documentId, String action) {
        if (principal == null || !principal.isAuthenticated()) return false;
        String tenant = tenantIdentity.verifiedTenant(principal);
        if (tenant == null || tenant.isBlank()) return false;

        // access phải dùng tenant, identity và DB/ACL đáng tin;
        // unknown action, missing doc, lỗi policy -> DENY.
        return access.isAllowed(tenant, principal.getName(), documentId, action);
    }
}
```

`TenantIdentity.verifiedTenant` phải xác thực membership trong tenant thực; một chuỗi tenant client gửi không được dùng thay. `DocumentAccessRepository.isAllowed` là interface của ứng dụng cần triển khai theo ma trận đã chốt. Với mô hình nhiều membership, cần truyền đúng role **gắn với tenant đang xét**; không dựa vào boolean admin toàn cục. Nếu client policy từ xa lỗi, không có kết quả PERMIT đáng tin thì không thực hiện thao tác.

Dịch vụ có method security:

```java
@Service
public class DocumentService {
    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize("@documentPolicy.permits(authentication, #id, 'READ')")
    @Transactional(readOnly = true)
    public DocumentDto read(@P("id") long id) {
        DocumentEntity doc = documents.findById(id)
                .orElseThrow(() ->
                        new ResponseStatusException(HttpStatus.NOT_FOUND));
        return DocumentDto.from(doc);
    }

    @PreAuthorize("@documentPolicy.permits(authentication, #id, 'EDIT')")
    @Transactional
    public void edit(@P("id") long id, UpdateDocument body) {
        // Sửa nội dung qua điều kiện tenant/owner/grant/status nhất quán
        // trong transaction; không ghi nếu status/ACL đã đổi.
    }

    @PreAuthorize("@documentPolicy.permits(authentication, #id, 'SHARE')")
    @Transactional
    public void share(@P("id") long id, ShareCommand command) {
        // Xác thực người nhận còn là member cùng tenant,
        // tài liệu vẫn ACTIVE, grant chỉ VIEWER/EDITOR;
        // ghi ACL và audit thành công/thất bại.
    }
}
```

Đây là **đoạn minh họa API**, cần triển khai các type `DocumentRepository`, `DocumentEntity`, `DocumentDto`, `UpdateDocument`, `ShareCommand`, `DocumentAccessRepository` và import tương ứng; `@P` dùng để đánh dấu tên tham số cho SpEL. Không hiểu các comment trong method EDIT/SHARE là implementation hoàn chỉnh. Cần test handler và truy vấn thật.

Cẩn thận với Spring AOP: `@PreAuthorize` hoạt động khi lời gọi đi qua proxy, không nên dựa vào `this.edit(...)` gọi nội bộ trong cùng bean. Controller, scheduled job, message listener và API khác phải có enforcement tại boundary phù hợp.

**TOCTOU:** method-level check chạy trước logic; giữa lúc kiểm ACL/status và lúc UPDATE, một request khác có thể revoke quyền hoặc archive tài liệu. Cần transaction/locking hoặc conditional UPDATE với predicate tenant + quyền + ACTIVE, kiểm tra số row cập nhật; không coi một lần check trước đó là quyền vĩnh viễn.

### 5.3. Chia sẻ và thu hồi là quyền độc lập

Một endpoint `POST /api/documents/{id}/share` phải kiểm đồng thời: caller có SHARE trên tài liệu ACTIVE; grantee là thành viên **cùng tenant**; grant chỉ là VIEWER/EDITOR; user được share không thể tự đổi owner/tenant, không tự cấp ADMIN; tránh trùng ACL và có audit. Quyền EDITOR **không** bao hàm SHARE trong policy này.

Khi revoke ACL, quyền đọc và tải xuống phải thay đổi; URL cũ, download link, share link, cache PERMIT, WebSocket/subscription và API export không được tiếp tục trả dữ liệu quá thời hạn hiệu lực. Cache key cần subject + tenant + resource + action + phiên bản ACL/policy và TTL/invalidation đúng mức nhạy cảm. Cache miss hoặc policy service không trả lời không có nghĩa PERMIT.

## 6. Ma trận quyền phải áp dụng cả lên danh sách và số lượng

Đừng chỉ bảo vệ `GET /api/documents/{id}` rồi trả toàn bộ metadata trong `GET /api/documents` hoặc kết quả search. Trong fixture trên:

| Caller | ID được phép thấy trong list | `totalElements` |
| --- | --- | ---: |
| alice/t-a | [101,102,103,104,105] | 5 |
| dave/t-a | [101,102,103,104,105] | 5 |
| erin/t-a | [103] | 1 |
| mallory/t-b | [201] | 1 |
| anonymous | Không truy cập API | Không trả số đếm |

Đối với query có phân trang, phải **lọc quyền trước `LIMIT/OFFSET`**, và `COUNT` phải có cùng predicate. Nếu database trả [101,102] rồi application lọc cho Erin, trang đầu có thể rỗng dù D103 được quyền; tổng không được tính trên tất cả tài liệu tenant.

Ví dụ SQL định hướng cho danh sách. Các tham số `verified_*` phải đến từ authentication/membership được server kiểm chứng; role admin phải được xác thực trong tenant tương ứng. Cập nhật điều kiện nếu ACL có hiệu lực thời gian hoặc trạng thái mới:

```sql
SELECT d.id, d.title, d.status
FROM documents d
WHERE d.tenant_id = :verified_tenant
  AND d.status IN ('ACTIVE', 'ARCHIVED')
  AND NOT (d.classification = 'CONFIDENTIAL'
           AND d.visibility = 'TEAM')
  AND (
       :is_tenant_admin = TRUE
       OR d.owner_id = :verified_actor
       OR EXISTS (
           SELECT 1 FROM document_acl a
           WHERE a.document_id = d.id
             AND a.tenant_id = d.tenant_id
             AND a.grantee_id = :verified_actor
             AND a.grant IN ('VIEWER', 'EDITOR')
             AND a.revoked_at IS NULL
       )
       OR (d.visibility = 'TEAM'
           AND d.classification = 'INTERNAL')
  )
ORDER BY d.id ASC
LIMIT :page_size OFFSET :offset;
```

`SELECT COUNT(*)` phải dùng đúng điều kiện tenant/status/classification/ACL/owner/TEAM ở trên mà bỏ ORDER BY/LIMIT/OFFSET. Không lấy total từ bảng gốc hoặc áp filter sau khi phân trang. Nếu app có multiple tenants per user hoặc `expiresAt`/soft-delete, cả query data và count cùng phải cập nhật. Kiểm tra response DTO không tiết lộ `content`, path tải file, ACL đầy đủ, tên tài liệu hoặc số đếm ngoài quyền.

Download, preview, file version, export, thumbnails cũng cần check quyền tại điểm cấp bytes. Một signed URL là credential riêng phải có scope/hạn sử dụng/thu hồi hợp đồng rõ; không phát URL vô hạn chỉ vì user từng được READ.

## 7. Thiết kế kiểm thử ma trận ở nhiều tầng

### 7.1. Ma trận test phải gồm cả ca dương và ca âm

| Test | Principal / Action | Expected | Điều cần bảo vệ |
| --- | --- | --- | --- |
| AUTH-01 | anonymous READ D103 | DENY | TEAM không public cho anonymous |
| TENANT-01 | alice/t-a READ D201 | DENY | Chặn IDOR vượt tenant |
| TENANT-02 | mallory/t-b SHARE D101 | DENY | Không cấp ACL ngoài tenant |
| OWNER-01 | alice EDIT D101 | PERMIT | Owner ACTIVE có quyền sửa |
| ACL-01 | alice READ D102 | PERMIT | VIEWER được đọc tài liệu CONFIDENTIAL đã share |
| ACL-02 | alice EDIT D102 | DENY | VIEWER không sửa |
| ACL-03 | alice EDIT D104 | PERMIT | EDITOR được sửa |
| ACL-04 | alice SHARE D104 | DENY | EDITOR không tự cấp quyền |
| TEAM-01 | erin READ D103 | PERMIT | TEAM + INTERNAL |
| TEAM-02 | erin READ D101 | DENY | PRIVATE chưa được share |
| ADMIN-01 | dave DELETE D102 | PERMIT | ADMIN trong tenant, ACTIVE |
| ARCH-01 | alice EDIT D105 | DENY | Owner không vượt trạng thái ARCHIVED |
| ARCH-02 | dave RESTORE D105 | PERMIT | Chỉ admin được restore |
| CLASS-01 | Tạo CONFIDENTIAL+TEAM | DENY/400 | Chặn visibility không hợp lệ |
| SHARE-01 | alice share D101 cho mallory | DENY | Grantee khác tenant |
| LIST-01 | erin GET list | [103], total=1 | Không lộ private trong list/count |
| REVOKE-01 | Alice READ D102 sau revoke VIEWER | DENY | Không dùng ACL cũ |
| DEFAULT-01 | Action null/không nhận diện | DENY | Fail closed |

Khi kiểm thử HTTP, authenticated nhưng thiếu quyền thường nhận **403**, anonymous thường là **401** trong một API cấu hình authentication entry point tương ứng. Một sản phẩm có thể trả **404** thay cho 403 để che sự tồn tại của tài liệu; phải thống nhất contract và không làm lộ sự khác biệt qua body. Với request bị từ chối, kiểm tra DB không bị sửa, ACL không bị tạo và không có bytes riêng tư trong response.

### 7.2. Kiểm thử tích hợp Spring Security + MockMvc

Ví dụ skeleton tích hợp Spring Boot 3.x/Security 6.x (cần import Spring/JUnit/Mockito, endpoints, bean tenant context, database fixture và application class):

```java
@SpringBootTest
@AutoConfigureMockMvc
@Sql("/fixtures/documents-matrix.sql")
class DocumentPermissionsIT {
    @Autowired MockMvc mvc;

    @Test
    @WithMockUser(username = "erin", roles = "MEMBER")
    void teamIsReadableButPrivateIsForbidden() throws Exception {
        // TenantIdentity test phải ánh xạ erin -> t-a.
        mvc.perform(get("/api/documents/103"))
                .andExpect(status().isOk());
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", roles = "MEMBER")
    void viewerCannotEditAndEditorCannotShare() throws Exception {
        mvc.perform(put("/api/documents/102")
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"changed\"}"))
                .andExpect(status().isForbidden());

        mvc.perform(post("/api/documents/104/share")
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"granteeId\":\"erin\",\"grant\":\"VIEWER\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "mallory", roles = "MEMBER")
    void tenantBDoesNotReadTenantA() throws Exception {
        // TenantIdentity test phải ánh xạ mallory -> t-b.
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isForbidden());
        mvc.perform(get("/api/documents/101/download"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "erin", roles = "MEMBER")
    void listCountContainsOnlyPermittedDocuments() throws Exception {
        mvc.perform(get("/api/documents").param("size", "10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content.length()").value(1))
                .andExpect(jsonPath("$.content[0].id").value(103))
                .andExpect(jsonPath("$.totalElements").value(1));
    }
}
```

Các test trên **chỉ chạy được khi ứng dụng triển khai đủ** `DocumentPolicy`, endpoint/DTO, SQL fixture và `TenantIdentity` dành cho test. `@WithMockUser` chỉ tạo username/authority, **không tự có tenant claim**; không lấy tenant từ query/header tùy ý để “cho test xanh”. Test JWT/session riêng cần xác nhận membership và claims được xác thực đúng. Nếu app trả 404 để che ID, điều chỉnh expected status thống nhất với policy.

Với test sửa/xóa/cấp ACL, đọc lại DB sau request để chứng minh **không có side effect**. Nếu dùng `MockBean` trả kết quả repository đã lọc sẵn, bài test không phát hiện SQL/COUNT bỏ predicate bảo mật; cần integration test repository thật với fixture chứa các bản ghi trái quyền xen kẽ.

### 7.3. Test cập nhật quyền và điều kiện đồng thời

Nên có thêm các test:

- Revoke VIEWER của Alice tại D102 → request READ/DOWNLOAD sau revoke bị từ chối; list/count giảm tương ứng.
- Archive D104 khi Alice còn EDITOR → EDIT bị từ chối; READ tiếp tục theo chính sách ví dụ.
- Thay owner D101 trong một transaction → owner cũ mất DELETE/SHARE nếu không còn ACL; owner mới được quyền.
- Một request SHARE và một request revoke/chuyển tenant cùng lúc → chỉ quyết định thỏa điều kiện tại thời điểm ghi được commit.
- Truyền `tenantId=t-a` trong request Mallory đang ở tenant B → không làm tăng quyền; server xác minh membership.
- Dữ liệu lỗi `CONFIDENTIAL + TEAM`, action không nhận diện hoặc policy service timeout → DENY, không fallback cho phép.

## 8. Các lỗi thường gặp và hướng xử lý

| Lỗi | Hậu quả | Cách sửa/kiểm tra |
| --- | --- | --- |
| Gắn owner thành `ROLE_OWNER` toàn cục | Owner tài liệu này có thể sửa tài liệu khác | Owner là quan hệ với ID tài liệu, kiểm từng request |
| Dùng `authenticated()` thay policy object | Bất kỳ thành viên nào cũng đoán ID và đọc tài liệu | Service guard kết hợp tenant/owner/ACL |
| Cho ADMIN của tenant B xem tenant A | Lộ dữ liệu cross-tenant | Role gắn tenant, tenant gate trước mọi grant |
| EDITOR được SHARE do dùng chung permission | Leo thang quyền bằng cấp ACL | Action SHARE riêng, chỉ owner/admin ACTIVE |
| TEAM được xem là anonymous/public | Dữ liệu nội bộ lộ ra Internet | TEAM chỉ cho member tenant đã xác thực |
| Không kiểm classification khi đổi visibility | CONFIDENTIAL thành TEAM | Validate khi ghi và deny nếu dữ liệu hỏng |
| ARCHIVED vẫn cho chỉnh sửa | Vượt lifecycle | Kiểm state trước action |
| ACL revoke nhưng cache PERMIT còn dùng | Người bị thu hồi vẫn xem/download | TTL, invalidation, ACL version, test revoke |
| Lọc content sau `PageRequest` | Trang thiếu ID, total sai/rò rỉ | Predicate visibility trước paging, COUNT cùng scope |
| Chỉ ẩn nút Delete ở frontend | HTTP DELETE trực tiếp vẫn chạy | Enforcement tại API/service/database |
| Bỏ qua các đường export/preview | Lộ bytes qua endpoint phụ | Dùng cùng policy theo action/scope |
| Test mock bỏ security chain | Test xanh nhưng @PreAuthorize không chạy | HTTP integration với filter chain và proxy thật |
| Policy check trước, database đổi sau | TOCTOU, ghi sai quyền | Conditional UPDATE/locking/revalidate trong transaction |

## 9. Checklist bàn giao

Một ma trận quyền hoàn chỉnh cần trả lời được:

1. **Ai?** Identity, membership, role theo tenant được xác thực từ nguồn tin cậy.
2. **Tài liệu nào?** Tenant, owner, visibility, classification, status và ACL được đọc từ dữ liệu đáng tin; ID đoán được không tạo ra quyền.
3. **Thao tác gì?** READ/DOWNLOAD/EDIT/DELETE/SHARE/RESTORE/CREATE có định nghĩa riêng, quyền càng nhạy cảm càng rõ ràng.
4. **Điều kiện chặn nào?** Sai tenant, anonymous, metadata bất hợp lệ, ARCHIVED và grant revoked/expired đều được xử lý trước PERMIT.
5. **Ma trận kiểm thử đã phủ đủ chưa?** Có owner, VIEWER, EDITOR, ADMIN, nonmember, cross-tenant, TEAM, PRIVATE, CONFIDENTIAL, ARCHIVED, input hỏng.
6. **Đủ mọi bề mặt chưa?** Detail, list/count/search, download, preview, export, versions, background jobs, endpoint chia sẻ và thu hồi.
7. **An toàn khi ghi chưa?** Share trong tenant, conditional write/transaction/locking, audit, không side effect nếu 403/404.
8. **Có bằng chứng chạy thật chưa?** Unit policy + repository integration + HTTP filter/method security integration + đối chứng sau revoke.
9. **Có bảo trì không?** Khi thêm action hoặc loại tài liệu, cập nhật ma trận và test trước khi triển khai.

**Kết luận thực hành:** viết chính sách thành một bảng **“chủ thể – tenant – tài liệu – hành động – trạng thái – kết quả”** trước khi lập trình giúp phát hiện khoảng trống quyền sớm. Trong Spring Security, filter và annotation chỉ là những điểm thực thi; điều quyết định tính đúng đắn là policy nhất quán từ HTTP xuống database và được kiểm chứng bằng cả ca cho phép lẫn từ chối.

## Tài liệu tham khảo

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): bật `@EnableMethodSecurity`, dùng `@PreAuthorize` và interceptor.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `SecurityFilterChain`, matcher và request-level authorization.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager` và authorities.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege, validate authorization on each request.
