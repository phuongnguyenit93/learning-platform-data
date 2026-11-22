# Triển khai ACL có kế thừa và thu hồi quyền chia sẻ

## 1. Mục tiêu của bài thực hành

Access Control List (ACL) cho phép gán quyền đến **một đối tượng cụ thể**, chẳng hạn thư mục, tài liệu hoặc bản ghi. Khi một tài liệu nằm trong thư mục, ứng dụng có thể cho tài liệu **kế thừa** quyền đọc từ thư mục cha. Khi người sở hữu thu hồi một quyền chia sẻ, hệ thống phải lập tức đưa ra quyết định mới mà không làm lộ tài liệu qua cache, API danh sách hay đường dẫn truy cập khác.

Bài thực hành này sử dụng Spring Security ACL trong hệ thống quản lý tài liệu để triển khai đầy đủ ba thao tác:

1. **Cấp quyền:** thêm ACE (Access Control Entry) cho user hoặc authority vào ACL của thư mục/tài liệu.
2. **Kế thừa quyền:** liên kết ACL con với ACL cha và chủ động bật hoặc tắt thừa kế.
3. **Thu hồi quyền:** xóa ACE trực tiếp, thu hồi quyền ở ACL cha, hoặc đặt ngoại lệ DENY/ngắt thừa kế ở tài liệu con theo đúng phạm vi yêu cầu.

Sau bài học, bạn cần phân biệt được **xóa bản ghi grant** với **chặn quyền hiệu lực**; thiết lập các bean ACL/JDBC; viết service quản lý ACL với kiểm tra quyền thao tác; đánh giá quyền bằng `hasPermission`; kiểm thử các ca có quyền trực tiếp, quyền kế thừa, thu hồi và dữ liệu khác tenant.

Đây là bài **Spring Security - authorization / Thực hành tích hợp**. Mã Spring bên dưới là các thành phần đưa vào một ứng dụng Spring Boot 3.x/Spring Security 6.x có database, không phải một chương trình Java SE độc lập. Một chương trình Java 17 độc lập mô phỏng thừa kế/thu hồi sẽ được cung cấp ở mục 9 để thực hành quy tắc trước khi chạy integration test.

## 2. Thành phần của Spring Security ACL

| Thành phần | Vai trò |
|---|---|
| `ObjectIdentity` | Định danh duy nhất một domain object: kiểu đối tượng + ID. |
| `Acl` | ACL của một object, có thể chứa nhiều ACE, owner, parent ACL và cờ kế thừa. |
| `AccessControlEntry` (ACE) | Một rule gồm SID, permission mask, `granting=true/false` và thông tin audit. |
| `Sid` | Danh tính nhận quyền: `PrincipalSid` cho user hoặc `GrantedAuthoritySid` cho authority. |
| `Permission` | Bit mask cho thao tác. `BasePermission` gồm READ, WRITE, CREATE, DELETE, ADMINISTRATION. |
| `MutableAcl` | Cho phép `insertAce`, `deleteAce`, `setParent`, `setEntriesInheriting`. |
| `MutableAclService` | `createAcl`, `readAclById`, `updateAcl`, `deleteAcl` để lưu/đọc ACL. |
| `JdbcMutableAclService` | Cài đặt JDBC lưu ACL vào bốn bảng chuyên dụng; cần cấu hình theo DBMS. |
| `AclPermissionEvaluator` | Nối ACL với biểu thức method security như `hasPermission(...)`. |
| `LookupStrategy` và `AclCache` | Tải ACL, kể cả cây cha, và cache để hạn chế query lặp. |

Bốn bảng nền tảng là `acl_sid` (danh tính), `acl_class` (kiểu domain), `acl_object_identity` (mỗi instance, parent, owner, cờ inheritance) và `acl_entry` (ACE theo thứ tự với mask, SID, granting). Spring Security ACL **không tự tạo ACL khi repository tạo một entity**: ứng dụng phải chủ động khởi tạo và đồng bộ vòng đời ACL với vòng đời tài nguyên.

ACL object owner không đương nhiên nhận READ/WRITE trên mọi object: owner của ACL là metadata phục vụ quản trị ACL theo `AclAuthorizationStrategy`; quyền dữ liệu phải được biểu diễn/kiểm tra đúng policy của ứng dụng. Cũng không đồng nhất ACL owner, domain owner và tenant administrator khi ba khái niệm có thể khác nhau.

**Chính sách ngoài ACL vẫn phải có:** principal đã xác thực, membership active của tenant chứa tài nguyên, đối tượng đang tồn tại, không bị xóa, hành động hợp lệ và người thực hiện có quyền cấp/thu hồi chia sẻ. `AclPermissionEvaluator` không tự biết quy tắc tenant của sản phẩm.

## 3. Thiết kế bài toán và dữ liệu mẫu

Giả sử ứng dụng có hai tenant độc lập A và B. Một user có thể thuộc nhiều tenant với vai trò khác nhau; mọi tài nguyên mang `tenant_id`. Dùng **ID Long duy nhất trên toàn hệ thống** cho Folder/Document trong ví dụ để tránh va chạm `ObjectIdentity`; nếu ID chỉ duy nhất trong từng tenant, phải thiết kế object identity tương thích JDBC và bao gồm phạm vi tenant hoặc dùng một khóa toàn cục. Không sử dụng ID tên gọi ở bảng dưới như khóa database thực.

### 3.1. Cây tài nguyên

~~~text
Tenant A
└── Folder F10 "Dự án Aurora"       [ACL cha, owner alice]
    ├── Document D101 "Thiết kế"     [ACL con, kế thừa=true]
    └── Document D102 "Kế hoạch"     [ACL con, kế thừa=true]

Tenant B
└── Folder F20 "Nhân sự"            [ACL riêng, owner diana]
    └── Document D201 "Hợp đồng"     [ACL con riêng của B]
~~~

Thông tin membership:

| User | Tenant | Role nghiệp vụ | Ý nghĩa |
|---|---|---|---|
| alice | A | OWNER/EDITOR | Có quyền chia sẻ folder F10 theo chính sách mẫu. |
| bob | A | VIEWER | Được chia sẻ READ ở F10, vì vậy có thể đọc D101/D102 qua inheritance. |
| carol | A | EDITOR | Được cấp WRITE trực tiếp ở D101; không tự có quyền SHARE nếu policy không cho phép. |
| diana | B | ADMIN | Không được đọc F10/D101 chỉ vì là ADMIN tenant B. |

ACL ban đầu:

| Object | ACE trực tiếp | Parent ACL | entriesInheriting |
|---|---|---|---|
| F10 | (bob, READ, ALLOW) | none | false/không áp dụng |
| D101 | (carol, WRITE, ALLOW) | F10 | true |
| D102 | none | F10 | true |
| F20 | (diana, READ, ALLOW) | none | false/không áp dụng |
| D201 | none | F20 | true |

**Kỳ vọng ban đầu:** Bob đọc được cả D101 và D102 do ACE READ trên F10. Carol sửa được D101 vì ACE WRITE trực tiếp; không mặc nhiên sửa D102. Diana không được truy cập tài nguyên A vì tenant boundary chặn trước khi kiểm ACL. WRITE/READ là hai mask khác nhau: không suy WRITE ngầm bao gồm READ nếu không định nghĩa một permission strategy rõ ràng.

### 3.2. Hợp đồng về thu hồi

Từ “thu hồi quyền chia sẻ” có thể có nhiều ý nghĩa, phải xác định trước thao tác:

- **Thu hồi grant trực tiếp ở D101:** xóa ACE của recipient trên D101. Nếu recipient còn READ qua F10, việc xóa ACE **không làm mất** READ hiệu lực.
- **Thu hồi grant tại F10:** xóa ACE trên F10; quyền kế thừa xuống D101 và D102 biến mất nếu không có grant khác.
- **Chặn riêng Bob trên D101 nhưng giữ Bob ở F10:** tạo ACE `DENY READ` trực tiếp tại D101 cho SID Bob theo policy và thứ tự ACE đã xác minh; D102 vẫn đọc được.
- **Ngắt toàn bộ kế thừa trên D101:** `setEntriesInheriting(false)`; mọi ACE chỉ có ở ancestor sẽ không còn được áp dụng cho D101. Các ACE trực tiếp tại D101 vẫn tồn tại.
- **Thu hồi membership của Bob khỏi tenant A:** dù còn ACE, policy tenant bên ngoài ACL phải từ chối. Dữ liệu grant tồn dư có thể phải được dọn theo lifecycle.

Không đồng nhất ba thao tác “xóa ACE”, “deny ở con” và “setEntriesInheriting(false)”: tác động đến các user và quyền khác nhau.

## 4. Quy tắc kế thừa và thứ tự đánh giá

Một ACL con chỉ nhận ACE từ parent khi **cả hai** điều kiện tồn tại:

1. ACL con có parent: `getParentAcl() != null`.
2. ACL con bật kế thừa: `isEntriesInheriting() == true`.

Chỉ liên kết cha–con chưa đủ để truyền quyền. Parent có thể tiếp tục trỏ lên grandparent; không được tạo chu kỳ trong cây ACL.

Với `DefaultPermissionGrantingStrategy` của Spring Security, engine xem các permission được yêu cầu và các SID theo thứ tự cung cấp, tìm ACE khớp trên ACL hiện tại; khi không tìm được ACE khớp ở ACL hiện tại mới tìm lên parent (nếu bật kế thừa). Khi tìm thấy một ACE DENY phù hợp, quyết định phụ thuộc danh sách permission/SID và cách strategy xử lý; trong bài thực hành, kiểm tra **một permission và một PrincipalSid** để hành vi dễ xác minh. Với nhiều role/group SIDs hoặc permission masks kết hợp, cần test semantics engine thật, không giản lược thành “DENY luôn thắng mọi ALLOW của mọi SID”.

| Trạng thái | D101/Bob READ | D102/Bob READ | Lý do |
|---|---|---|---|
| F10 có ALLOW READ Bob, cả hai con inherit | ALLOW | ALLOW | Kế thừa từ F10. |
| D101 có ACE trực tiếp DENY READ Bob | DENY | ALLOW | Rule riêng của D101 chặn trước inheritance khi SID/permission khớp. |
| Xóa DENY ở D101, parent vẫn grant | ALLOW | ALLOW | Grant của cha xuất hiện trở lại. |
| D101 tắt inheritance, không có READ trực tiếp | DENY | ALLOW | Con D101 không nhận ACE của F10. |
| D101 bật lại inheritance, xóa grant Bob tại F10 | DENY | DENY | Không còn nguồn READ từ cha. |
| F10 bị thu hồi nhưng D101 có ALLOW READ trực tiếp | ALLOW | DENY | Grant trực tiếp của con sống độc lập. |

Đây là **ma trận hành vi đơn SID/READ của chính sách mẫu**. Nếu ứng dụng sử dụng role SID chung, custom permission masks, ACE ordering phức tạp hoặc parent hierarchy nhiều tầng, bổ sung test tương ứng. Đặc biệt, xóa một ACE local có thể làm **tăng quyền hiệu lực** vì trước đó ACE local là DENY đang che một ALLOW inherited — đây là lỗi thường bị bỏ sót.

## 5. Chuẩn bị ứng dụng Spring Boot và database

### 5.1. Dependency

Trong ứng dụng Spring Boot 3.x/Spring Security 6.x, bổ sung Spring Security ACL và JDBC (nếu chưa có). Dùng BOM/dependency management để giữ mọi thư viện Spring Security tương thích phiên bản:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    implementation("org.springframework.security:spring-security-acl")
    // JDBC driver tương ứng DBMS, ví dụ PostgreSQL, do ứng dụng cấu hình
}
~~~

Ứng dụng cũng cần Spring MVC/Web starter khi triển khai REST controller và Spring Security test cho integration test. Spring Security 7 đưa một số **legacy Access API** như `AclEntryVoter` vào module `spring-security-access` riêng; ứng dụng chỉ dùng ACL/method security mới không nên thêm module legacy trừ khi thực sự phụ thuộc API đó.

### 5.2. Tạo schema ACL

Tạo bốn bảng ACL theo schema JDBC chính thức của **đúng phiên bản và DBMS**. Quan hệ khái quát:

~~~text
acl_class 1 ── * acl_object_identity * ── 1 acl_sid (owner)
                         │
                         │ parent_object (self reference)
                         ▼
                  acl_object_identity
                         │ 1
                         │
                         * acl_entry * ── 1 acl_sid (recipient)
~~~

Các trường đặc trưng của `acl_object_identity`: `object_id_class`, `object_id_identity`, `parent_object`, `owner_sid`, `entries_inheriting`. `acl_entry` thường có `acl_object_identity`, `ace_order`, `sid`, `mask`, `granting`, `audit_success`, `audit_failure`.

Không tự sao chép SQL HSQLDB mặc định vào PostgreSQL mà không kiểm tra sequence/identity: tài liệu API `JdbcMutableAclService` nêu các câu truy vấn identity mặc định hướng đến HSQLDB và có thể cần cấu hình `sidIdentityQuery`/`classIdentityQuery` hoặc các truy vấn khác cho database dùng thực tế. Nên dùng migration Flyway/Liquibase, khóa ngoại, uniqueness cho object class/id và chỉ mục theo parent/ACE SID. Tạo schema trong migration, không để runtime tự “best effort” sửa bảng ở production.

**Ràng buộc tenant:** bảng ACL mặc định không tự có `tenant_id`. Domain Folder/Document phải chứa tenantId; service tạo parent ACL phải xác minh parent/child cùng tenant và principal có membership hợp lệ. Không cho client gửi tùy ý class/id hay parent object để nối ACL xuyên tenant. Việc trùng ID Long giữa nhiều tenant cần thiết kế identity chính xác và kiểm thử.

### 5.3. Cấu hình bean tối thiểu

Ví dụ sau minh họa bean cấu hình theo mẫu tài liệu Spring Security ACL. Các import chuẩn Spring/Spring Security được lược bỏ cho gọn; đây là **snippet đặt trong class @Configuration** có dependency tương ứng:

~~~java
@EnableMethodSecurity
@Configuration
class AclConfiguration {
    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclPermissionEvaluator evaluator) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    AclPermissionEvaluator aclPermissionEvaluator(AclService service) {
        return new AclPermissionEvaluator(service);
    }

    @Bean
    JdbcMutableAclService aclService(
            DataSource dataSource, LookupStrategy strategy, AclCache cache) {
        return new JdbcMutableAclService(dataSource, strategy, cache);
    }

    @Bean
    LookupStrategy lookupStrategy(
            DataSource source, AclCache cache,
            AclAuthorizationStrategy authStrategy,
            PermissionGrantingStrategy grantingStrategy) {
        return new BasicLookupStrategy(
                source, cache, authStrategy, grantingStrategy);
    }

    @Bean
    AclCache aclCache(PermissionGrantingStrategy grantingStrategy,
                      AclAuthorizationStrategy authStrategy) {
        return new SpringCacheBasedAclCache(
                new ConcurrentMapCache("aclCache"),
                grantingStrategy, authStrategy);
    }

    @Bean
    AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
                new SimpleGrantedAuthority("ROLE_ACL_ADMIN"));
    }

    @Bean
    PermissionGrantingStrategy grantingStrategy() {
        return new DefaultPermissionGrantingStrategy(
                new ConsoleAuditLogger());
    }
}
~~~

Trong ứng dụng thực, `ROLE_ACL_ADMIN` là lựa chọn riêng của ví dụ, không phải role mặc định của mọi tổ chức. Đọc quyền sửa ACL qua `AclAuthorizationStrategy` **không thay thế** kiểm tra share/tenant/owner của nghiệp vụ. `ConcurrentMapCache` minh họa cho môi trường phát triển; production nhiều instance cần chiến lược cache và invalidation liên node rõ ràng, đồng thời kiểm tra consistency sau mutation.

## 6. Tạo ACL cha và ACL con có inheritance

Nên khởi tạo ACL ngay sau khi tạo domain record trong transaction thích hợp. Dữ liệu parent phải được xác minh qua repository; không cho request cung cấp một `ObjectIdentity` trỏ sang tenant khác. Mẫu thao tác cốt lõi:

~~~java
// Code minh họa trong một service có MutableAclService aclService,
// Domain Folder, Document và @Transactional đã được cấu hình.
@Transactional
public void initializeAcls(long folderId, long documentId) {
    ObjectIdentity folderOid =
            new ObjectIdentityImpl(Folder.class, folderId);
    ObjectIdentity documentOid =
            new ObjectIdentityImpl(Document.class, documentId);

    MutableAcl parent = aclService.createAcl(folderOid);
    Sid bob = new PrincipalSid("bob");
    parent.insertAce(
            parent.getEntries().size(), BasePermission.READ, bob, true);
    parent = aclService.updateAcl(parent);

    MutableAcl child = aclService.createAcl(documentOid);
    child.setParent(parent);
    child.setEntriesInheriting(true);
    aclService.updateAcl(child);
}
~~~

Ở đây `Folder` và `Document` là domain class có thật của ứng dụng; tên type truyền vào `ObjectIdentityImpl` phải **nhất quán** với type được dùng trong permission evaluator. Tạo một ACL trùng object identity có thể gây `AlreadyExistsException`; tạo parent/child theo thứ tự, không tạo lại vô điều kiện ở mỗi request.

**Hành vi kỳ vọng sau khi commit:** nếu Bob đã được xác minh là member tenant của Folder, `hasPermission(documentId, DocumentType, READ)` có thể cho ALLOW ở document con qua parent F10 dù document chưa có ACE READ trực tiếp. Khi permission evaluator được gọi từ method security, kiểm tra cả điều kiện tenant/membership bằng policy bên ngoài ACL.

### 6.1. Xác minh kết quả từ ACL API

Đọc bằng `AclService.readAclById(documentOid)` rồi kiểm tra `getParentAcl()`, `isEntriesInheriting()` và quyền hiệu lực. Trong một bài test dùng một SID đã được load đầy đủ:

~~~java
Acl child = aclService.readAclById(
        new ObjectIdentityImpl(Document.class, documentId));
Sid bob = new PrincipalSid("bob");
boolean allowed = child.isGranted(
        List.of(BasePermission.READ), List.of(bob), false);
~~~

Ví dụ này giả định parent đã lưu, cache/lookup tải đủ thông tin SID và sử dụng strategy mặc định. Khi không có ACE khớp, `Acl.isGranted` có thể ném `NotFoundException`; nếu thông tin SID chưa được load đầy đủ có thể ném `UnloadedSidException`. Ở đường quyết định bảo mật thực tế, những tình huống không chứng minh được ALLOW phải được xử lý **fail closed**. Không viết handler bắt mọi exception rồi trả true.

### 6.2. Dùng hasPermission ở method security

Snippet tích hợp trong service có `@EnableMethodSecurity` và evaluator cấu hình như trên:

~~~java
@PreAuthorize(
    "@tenantPolicy.isActiveMember(authentication, #tenantId) and " +
    "hasPermission(#documentId, 'com.example.domain.Document', 'READ')")
public DocumentDto getDocument(long tenantId, long documentId) {
    Document doc = documentRepository
            .findByIdAndTenantId(documentId, tenantId)
            .orElseThrow(DocumentNotFoundException::new);
    return mapper.toDto(doc);
}
~~~

Đây là fragment minh họa trong service; `tenantPolicy`, repository, DTO, exception và class FQCN phải được tạo đúng ứng dụng. Lời gọi hasPermission có thể diễn ra trước khi vào thân method nên cần xác nhận đối tượng tồn tại/tenant thật và không để client giả mạo domain type. Với dữ liệu nhạy cảm, cân nhắc đặt một policy service tập trung nhận object đã tra theo tenant để không phát sinh nhiều query hoặc lộ thông tin qua lỗi.

Nhớ rằng `hasPermission(#documentId, 'com.example.domain.Document', 'READ')` dùng type string; nó phải khớp với identity lưu trong ACL (ví dụ `Document.class` ở package thực). Tùy phiên bản, permission string phải được mapping đúng qua PermissionFactory/evaluator. Không giả định một chuỗi type khác nhau vẫn trỏ cùng ACL.

## 7. Cấp và thu hồi chia sẻ trực tiếp

### 7.1. Cấp ACE READ ở đúng đối tượng

Từ service đã xác minh actor có quyền SHARE, recipient là member cùng tenant và đối tượng tồn tại:

~~~java
@Transactional
public void grantReadOnDocument(long documentId, String recipient) {
    ObjectIdentity oid = new ObjectIdentityImpl(
            Document.class, documentId);
    MutableAcl acl = (MutableAcl) aclService.readAclById(oid);
    Sid sid = new PrincipalSid(recipient);

    // Kiểm tra trùng ACE theo (Sid, permission, granting) trước khi insert.
    acl.insertAce(acl.getEntries().size(),
            BasePermission.READ, sid, true);
    aclService.updateAcl(acl);
}
~~~

Đây là logic cốt lõi, **không phải service production độc lập**: phải kiểm tra actor, tenant, document state, recipient và idempotency trước khi gọi. Một ACL có nhiều ACE trùng hoặc mâu thuẫn cùng SID/permission khiến thứ tự ACE quyết định hành vi và gây khó kiểm toán. Tốt nhất thiết kế invariant cho phép chỉ một rule trực tiếp cho mỗi SID + permission trên một object, hoặc quy định rõ cách giải quyết conflict.

### 7.2. Thu hồi ACE trực tiếp bằng deleteAce

Không nên xóa “ACE ở index 0” theo phỏng đoán. Index của danh sách `getEntries()` có thể đổi sau mỗi lần cấp/thu hồi. Tìm đúng SID, permission và mask ở **ACL được chọn**, rồi xóa từ index lớn xuống nhỏ để không làm dịch index chưa xử lý:

~~~java
@Transactional
public boolean revokeDirectRead(long documentId, String recipient) {
    ObjectIdentity oid = new ObjectIdentityImpl(
            Document.class, documentId);
    MutableAcl acl = (MutableAcl) aclService.readAclById(oid);
    Sid recipientSid = new PrincipalSid(recipient);
    boolean changed = false;

    for (int i = acl.getEntries().size() - 1; i >= 0; i--) {
        AccessControlEntry ace = acl.getEntries().get(i);
        if (ace.getSid().equals(recipientSid)
                && ace.getPermission().getMask()
                    == BasePermission.READ.getMask()
                && ace.isGranting()) {
            acl.deleteAce(i);
            changed = true;
        }
    }
    if (changed) {
        aclService.updateAcl(acl);
    }
    return changed;
}
~~~

Trong thực tế, giao diện thu hồi chia sẻ phải phân biệt *đang xóa grant nào*: recipient/user, resource, permission, grant issuer và version; kiểm tra quyền của **actor** trước khi chỉnh. Code mẫu chỉ xóa direct ACE READ ALLOW trên Document, không đụng parent. Nếu Bob vẫn được READ qua F10, sau khi xóa grant READ trực tiếp trên D101, Bob **vẫn đọc được** D101 do inheritance. Trả lời UI “đã thu hồi tất cả quyền” trong tình huống đó là sai.

Với `JdbcMutableAclService.updateAcl`, implementation có thể xóa và tạo lại các ACE trong database cho ACL mỗi lần update; cần tránh cập nhật cạnh tranh bị mất thay đổi, và dùng transaction/locking phù hợp. Không dùng chỉ số ACE cũ sau một update khác.

### 7.3. Thu hồi quyền ở parent và tác động đến descendants

Nếu chính sách “gỡ Bob khỏi toàn bộ thư mục F10”:
1. Xác nhận actor có quyền quản trị **Folder F10**, đúng tenant.
2. Tìm và xóa ACE READ ALLOW của Bob trong ACL **F10**.
3. Gọi `aclService.updateAcl(parentAcl)`.
4. Kiểm tra quyền hiệu lực của Bob trên F10, D101, D102 sau commit; những tài liệu có ACE READ trực tiếp khác có thể vẫn ALLOW.
5. Kiểm tra ACL cache của parent/descendants đã được invalidated hoặc tái tải đúng, nhất là khi có nhiều node ứng dụng.

Không xóa bản ghi `acl_object_identity` của F10 chỉ để thu hồi một share: `deleteAcl` dùng để xóa cả ACL object và có thể ảnh hưởng children, không phải API revoke một ACE. Khi xóa resource thật, xem xét riêng quy tắc cascade và trạng thái ACL descendants.

## 8. Chặn quyền kế thừa riêng tại con

### 8.1. Dùng ACE DENY cụ thể

Muốn Bob giữ READ trên F10/D102 nhưng **không đọc D101**, một cách là đặt local DENY cho SID Bob + READ tại D101:

~~~java
MutableAcl child = (MutableAcl) aclService.readAclById(
        new ObjectIdentityImpl(Document.class, documentId));
child.insertAce(0, BasePermission.READ,
        new PrincipalSid("bob"), false);
aclService.updateAcl(child);
~~~

Thứ tự ACE có thể làm thay đổi kết quả nếu cùng ACL có nhiều rule hoặc nếu user có nhiều SID; trước khi thêm DENY, kiểm tra và loại bỏ các ACE xung đột theo chính sách. Với một PrincipalSid và một READ mask như bài tập, DENY ở child có thể chặn ALLOW ở parent; với nhiều group SIDs, test thực tế trên `DefaultPermissionGrantingStrategy`/strategy đã cấu hình mới là kết luận cuối cùng.

**Thu hồi DENY** lại là việc xóa ACE `granting=false` trên D101. Khi xóa, nếu F10 còn ALLOW READ Bob và D101 kế thừa, Bob đọc D101 **trở lại**. Vì vậy, thao tác “unblock” phải được ghi audit riêng với thao tác “revoke grant”.

### 8.2. Dùng setEntriesInheriting(false)

Nếu D101 phải tách khỏi toàn bộ quyền cha, đặt:

~~~java
MutableAcl child = (MutableAcl) aclService.readAclById(
        new ObjectIdentityImpl(Document.class, documentId));
child.setEntriesInheriting(false);
aclService.updateAcl(child);
~~~

Cờ này tắt **mọi ACE thừa kế từ cha**, không chỉ Bob READ. Ví dụ Carol có WRITE tại D101 vẫn giữ được WRITE trực tiếp, nhưng quyền từ F10 của những user/role khác cũng mất. Không dùng cách này để thu hồi một user nếu hệ thống cần giữ các quyền inherited khác.

### 8.3. So sánh tác động

| Thao tác | D101 | D102 | Ai bị ảnh hưởng |
|---|---|---|---|
| Xóa direct READ ALLOW tại D101 | Có thể vẫn ALLOW do F10 | Không đổi | Recipient trên D101; inheritance còn tác dụng |
| Xóa READ ALLOW của Bob trên F10 | Mất inherited READ, trừ khi có direct grant | Mất inherited READ | Bob trên mọi descendant kế thừa |
| Đặt DENY READ Bob tại D101 | DENY với Bob theo policy test | Không đổi | Chỉ Bob/D101 |
| Tắt inheritance tại D101 | Không nhận ACE cha | Không đổi | Tất cả người nhận quyền từ parent đối với D101 |
| Xóa direct DENY Bob ở D101 | Có thể ALLOW trở lại qua F10 | Không đổi | Bob/D101 |

Không sử dụng “thu hồi quyền” như một nhãn chung cho các thao tác này trong API. API nên diễn đạt rõ *scope* (DIRECT_OBJECT / PARENT_TREE / OVERRIDE / INHERITANCE) và test tác động đúng phạm vi; tên enum ở đây chỉ là ví dụ thiết kế, không phải API Spring Security.

## 9. Chương trình Java 17 chạy độc lập: chứng minh semantics

Để luyện tập mà không cần Spring hay database, chương trình nhỏ sau mô hình hóa **một SID + một permission** trên mỗi nhánh ACL; local ALLOW/DENY ưu tiên trước parent; thiếu rule dẫn tới DENY. Đây là mô hình dạy cơ chế inheritance, **không sao chép thuật toán đầy đủ** của `DefaultPermissionGrantingStrategy` khi có nhiều SID, mask phức tạp và exception.

~~~java
import java.util.HashMap;
import java.util.Map;

public class AclInheritanceDemo {
    record Key(String user, String permission) {}

    static class Node {
        final String name;
        final Node parent;
        boolean entriesInheriting;
        final Map<Key, Boolean> local = new HashMap<>();

        Node(String name, Node parent, boolean entriesInheriting) {
            this.name = name;
            this.parent = parent;
            this.entriesInheriting = entriesInheriting;
        }

        void grant(String user, String permission) {
            local.put(new Key(user, permission), true);
        }

        void deny(String user, String permission) {
            local.put(new Key(user, permission), false);
        }

        void revokeLocal(String user, String permission) {
            local.remove(new Key(user, permission));
        }

        boolean allowed(String user, String permission) {
            Boolean direct = local.get(new Key(user, permission));
            if (direct != null) {
                return direct;
            }
            return entriesInheriting && parent != null
                    && parent.allowed(user, permission);
        }
    }

    static void check(String label, Node node, String user,
                      String permission, boolean expected) {
        boolean actual = node.allowed(user, permission);
        if (actual != expected) {
            throw new AssertionError(label + " expected=" + expected
                    + " actual=" + actual);
        }
        System.out.println(label + ": " + (actual ? "ALLOW" : "DENY"));
    }

    public static void main(String[] args) {
        Node folder = new Node("F10", null, false);
        Node design = new Node("D101", folder, true);
        Node plan = new Node("D102", folder, true);

        folder.grant("bob", "READ");
        design.grant("carol", "WRITE");

        check("inherit design", design, "bob", "READ", true);
        check("inherit plan", plan, "bob", "READ", true);
        check("no inherited write", plan, "carol", "WRITE", false);

        design.deny("bob", "READ");
        check("local deny", design, "bob", "READ", false);
        check("sibling unaffected", plan, "bob", "READ", true);

        design.revokeLocal("bob", "READ");
        check("deny removed reveals parent", design, "bob", "READ", true);

        design.entriesInheriting = false;
        check("inheritance disabled", design, "bob", "READ", false);
        check("direct write retained", design, "carol", "WRITE", true);

        design.entriesInheriting = true;
        folder.revokeLocal("bob", "READ");
        check("parent grant revoked", plan, "bob", "READ", false);
        check("child after parent revoke", design, "bob", "READ", false);

        design.grant("bob", "READ");
        check("child direct grant", design, "bob", "READ", true);
        design.revokeLocal("bob", "READ");
        check("child direct revoked", design, "bob", "READ", false);
    }
}
~~~

Lưu dưới tên `AclInheritanceDemo.java` rồi biên dịch/chạy:

~~~bash
javac --release 17 AclInheritanceDemo.java
java AclInheritanceDemo
~~~

Stdout kỳ vọng:

~~~text
inherit design: ALLOW
inherit plan: ALLOW
no inherited write: DENY
local deny: DENY
sibling unaffected: ALLOW
deny removed reveals parent: ALLOW
inheritance disabled: DENY
direct write retained: ALLOW
parent grant revoked: DENY
child after parent revoke: DENY
child direct grant: ALLOW
child direct revoked: DENY
~~~

Giải thích: quyền READ ở folder đi xuống các child đang bật inheritance. Local DENY chặn quyền inherited, nhưng xóa DENY sẽ mở lại quyền nếu ancestor vẫn grant. Tắt inheritance chỉ bỏ quyền kế thừa, không xóa direct WRITE. Thu hồi parent grant chặn tất cả child nhận quyền từ parent; grant trực tiếp cho child vẫn có thể cấp lại quyền riêng. Chính vì các trạng thái này, test sau revoke **phải kiểm tra effective permission**, không chỉ assert rằng một dòng trong bảng `acl_entry` đã bị xóa.

## 10. API chia sẻ và ranh giới bảo mật

Giả sử controller có các endpoint:

~~~text
POST   /api/tenants/{tenantId}/folders/{folderId}/shares
DELETE /api/tenants/{tenantId}/folders/{folderId}/shares/{recipient}
POST   /api/tenants/{tenantId}/documents/{documentId}/shares
DELETE /api/tenants/{tenantId}/documents/{documentId}/shares/{recipient}
PATCH  /api/tenants/{tenantId}/documents/{documentId}/inheritance
GET    /api/tenants/{tenantId}/documents/{documentId}
~~~

Đây là **phác thảo API nghiệp vụ**, không phải endpoint do Spring Security ACL tự tạo. Từng request phải thực hiện:
1. Lấy actor từ principal đã xác thực; kiểm tra membership tenant đang active.
2. Load Folder/Document **theo tenantId và objectId** từ repository. Không chỉ `findById` rồi tin tenant do client khai.
3. Với SHARE/REVOKE/CHANGE_INHERITANCE, kiểm tra actor có quyền quản lý share (owner, admin đúng tenant hoặc policy riêng). Không cho recipient tự cấp quyền cho mình.
4. Kiểm tra recipient là member cùng tenant, permission có trong tập cho phép; nếu áp ACL cho một role SID thì role đó phải thuộc đúng tenant.
5. Với thay đổi parent ACL, kiểm tra cha/con cùng tenant, không tạo chu kỳ, không chuyển document sang folder không được phép.
6. Ghi domain mutation và ACL mutation trong transaction theo cấu hình; sau commit làm mới/invalidate cache, bảo đảm quyết định đọc kế tiếp phản ánh kết quả.
7. Ghi audit actor/tenant/resource/recipient/action/scope/before/after. Không ghi token hay dữ liệu nhạy cảm không cần thiết.

Trả về 403 nếu actor không có quyền SHARE, hoặc 404 cho tài nguyên không được tiết lộ theo API contract; chọn một hợp đồng nhất quán và test thực tế. Với DELETE share, nên xác định idempotency: xóa grant không tồn tại có thể trả 204/404 theo hợp đồng nhưng **không được xóa nhầm ACE khác**.

### 10.1. Cẩn trọng với PrincipalSid và GrantedAuthoritySid

`new PrincipalSid("bob")` là danh tính user, trong khi `new GrantedAuthoritySid("ROLE_EDITOR")` là authority có thể áp dụng cho nhiều user. Chia sẻ qua group/role có thể khiến Bob tiếp tục có quyền ngay cả khi đã xóa ACE cá nhân. Khi thu hồi “mọi quyền Bob” phải đánh giá **toàn bộ SID hiện có của Bob**, không chỉ `PrincipalSid("bob")`. Với multi-tenant, tên authority cần scope tenant hoặc được kiểm tra membership trước khi xét ACL.

## 11. Kiểm thử tích hợp trên database thật

### 11.1. Seed và sequence

Dùng database kiểm thử riêng (có thể Testcontainers) với migration schema ACL đúng DBMS. Seed:
- tenant A/B, user Alice/Bob/Carol/Diana và membership.
- Folder F10/F20, Document D101/D102/D201.
- ACL F10 (Bob READ ALLOW), ACL D101 (parent F10, inherit=true, Carol WRITE ALLOW), ACL D102 (parent F10, inherit=true), ACL B riêng.
- Cơ chế authentication trong test tạo principal tương ứng; không lấy role/tenant từ HTTP body làm sự thật.

Mỗi test cần baseline sạch hoặc transaction rollback và cache được reset hợp lý; test revoke không nên phụ thuộc thứ tự chạy hoặc kết quả của test trước đó.

### 11.2. Ma trận bắt buộc

| Test | Trước thao tác | Thao tác | Expected sau thao tác |
|---|---|---|---|
| Inherit READ | Bob READ D101/D102 = ALLOW | Không đổi | Giữ ALLOW ở hai con. |
| Direct WRITE | Carol WRITE D101 = ALLOW | Không đổi | Carol không WRITE D102. |
| Deny ở con | Bob READ D101/D102 = ALLOW | Insert DENY Bob READ D101 | D101 DENY; D102 ALLOW. |
| Remove DENY | D101 DENY; F10 ALLOW | Delete local DENY D101 | D101 ALLOW trở lại. |
| Disable inheritance | F10 grant READ Bob | D101 setEntriesInheriting(false) | D101 DENY nếu không có direct READ; D102 ALLOW. |
| Reenable inheritance | D101 inherit=false | setEntriesInheriting(true) | D101 ALLOW nếu parent grant còn. |
| Revoke parent | F10 grant READ Bob | Delete Bob READ ALLOW F10 | D101/D102 DENY nếu không có direct READ khác. |
| Direct grant survives | F10 grant; D101 direct READ Bob | Revoke Bob ở F10 | D101 ALLOW; D102 DENY. |
| Cross tenant | Diana ADMIN B | READ/share D101 tenant A | DENY; ACL A không đổi. |
| Missing ACL/SID | Không có rule khớp | Read không hợp lệ | DENY/fail closed, không 500 làm lộ metadata. |
| Group SID | Bob thuộc authority được grant trên F10 | Xóa ACE cá nhân Bob | Vẫn có thể ALLOW qua group; theo policy. |
| Concurrent revoke | Có grant; hai thay đổi song song | Revoke + grant/update | Không ghi đè ngầm; trạng thái cuối hợp đồng rõ. |
| Cache stale | Bob đã đọc trước revoke | Revoke rồi đọc lại qua node khác | Quyền cập nhật theo cam kết nhất quán. |

Không dừng ở việc assert số lượng ACE. Với từng case, đọc ACL mới từ database, kiểm `hasPermission` bằng principal thực tế trong test, và gọi REST GET/UPDATE nếu có. **DENY phải đồng nghĩa response không lộ dữ liệu và mutation không có side effect.**

### 11.3. Ví dụ kiểm thử định hướng

Trong test class đã được cấu hình `MockMvc`, authentication, repository, ACL beans và seed, đoạn sau thể hiện đường đi cần test (không biên dịch độc lập):

~~~java
// 1. Cho Bob đọc D101 trước revoke.
mvc.perform(get("/api/tenants/A/documents/101")
        .with(user("bob").roles("VIEWER")))
    .andExpect(status().isOk());

// 2. Alice thu hồi quyền READ Bob tại folder F10.
mvc.perform(delete("/api/tenants/A/folders/10/shares/bob")
        .with(user("alice").roles("OWNER"))
        .with(csrf()))
    .andExpect(status().isNoContent());

// 3. Bob không còn quyền inherited READ D101 và D102
// nếu hai document không có grant READ trực tiếp khác.
mvc.perform(get("/api/tenants/A/documents/101")
        .with(user("bob").roles("VIEWER")))
    .andExpect(status().isForbidden());
~~~

Các status chỉ là contract giả định (application có thể chọn 404 cho object bị từ chối). Với ứng dụng dùng CSRF, cung cấp token hợp lệ để phân biệt lỗi CSRF với authorization; với API stateless Bearer, dùng cơ chế test authentication tương ứng. Test phải đảm bảo đọc lần hai thật sự đi qua policy và cache sau revoke, không chỉ đọc cùng object đã memoized trong một request.

### 11.4. Kiểm tra query và performance

Nếu list 100 document rồi gọi `hasPermission` từng item, có thể phát sinh N+1 ACL lookup. Khi cần đánh giá nhiều ID, cân nhắc `AclService.readAclsById(objectIdentities, sids)`, cơ chế batch/cache của ACL hoặc query danh sách đã lọc quyền trước pagination. Không lấy tất cả document rồi `@PostFilter` sau LIMIT vì phân trang/total có thể sai; cần thiết kế query projection quyền tương đương với ACL engine, nhất là khi có inheritance và ACE DENY.

## 12. Cache, transaction và đồng thời khi thu hồi

Thu hồi quyền thường tạo nguy cơ bảo mật lớn hơn cấp quyền vì **quyết định ALLOW cũ** có thể tồn tại trong cache.

- **Cache ở ACL layer:** xác minh `AclCache` evict ACL bị sửa khi `updateAcl`, và đánh giá riêng các ACL con đã được load/cached khi thay parent. Không mặc nhiên kết luận sửa parent đã đồng bộ mọi child ở mọi node.
- **Cache ở service/UI:** mọi cache `canRead`/`canWrite` theo user + tenant + resource + permission cần invalidation, phiên bản policy hoặc TTL đủ chặt theo contract. Không cache kết quả ALLOW vô thời hạn.
- **Multiple instances:** `ConcurrentMapCache` chỉ nằm trong một JVM; production nhiều node cần cơ chế phát sự kiện invalidate hoặc cache chung và test revoke từ node A, read từ node B.
- **Transaction boundary:** `updateAcl` có thể xóa rồi insert lại ACE; dùng transaction để tránh state nửa chừng, và kiểm soát lost update khi hai actor sửa ACL cùng lúc (optimistic lock/domain version, lock theo object hoặc serialization).
- **TOCTOU:** quyền có thể bị revoke sau bước check nhưng trước mutation; với thao tác nhạy cảm, đánh giá quyền trong transaction/lock phù hợp hoặc recheck ngay tại điểm ghi theo threat model.
- **Audit:** ghi ai đã cấp/thu hồi, timestamp, tenant, SID, resource, direct hay inherited; truy vết cả việc bật/tắt inheritance và đổi parent.
- **Failure semantics:** khi ACL lookup thiếu, SID chưa load, cache hỏng hoặc database lỗi, không trả ALLOW. Thay vì bắt exception rồi cấp quyền dự phòng, fail closed và log lỗi đủ điều tra.

Một chính sách thu hồi “có hiệu lực ngay” cần định nghĩa **ngay sau commit ở mọi node** hay chỉ có độ trễ nhất định, rồi test tương ứng. Không hứa immediate consistency nếu cache phân tán chưa có cơ chế invalidation bảo đảm.

## 13. Những lỗi triển khai hay gặp

1. **Chỉ gọi setParent:** quên `setEntriesInheriting(true)` nên không có inherited permission.
2. **Xóa direct ACE rồi cho rằng đã revoke hết:** parent/group SID khác có thể vẫn grant.
3. **Dùng setEntriesInheriting(false) để revoke một user:** vô tình chặn mọi quyền inherited của user khác.
4. **Đặt DENY thiếu kiểm soát:** thứ tự ACE, nhiều SID và permission mask có thể khiến kết quả khác kỳ vọng.
5. **Coi ACL owner tự có toàn quyền dữ liệu:** ownership và permission phải theo đặc tả nghiệp vụ.
6. **Không tách tenant:** một SID hoặc ObjectIdentity trùng ID giữa tenants có thể gây truy cập chéo.
7. **Cho client chỉ định arbitrary object type/parent:** có thể tạo ACL cho đối tượng khác tenant, xuyên cây hoặc vòng lặp.
8. **Quên khởi tạo ACL:** domain record đã tạo nhưng readAclById báo thiếu, handler lại mặc nhiên allow.
9. **Tái sử dụng ACE index sau update:** xóa nhầm grant của user khác; phải tìm theo SID/mask và xử lý index thay đổi.
10. **Chỉ assert database row:** có cache/parent nên effective permission vẫn ALLOW.
11. **Bỏ quên group SID:** revoke PrincipalSid không xóa quyền còn do authority SID.
12. **Coi updateAcl là thao tác nhỏ không cần lock:** nhiều update có thể ghi đè nhau hoặc xóa/tạo lại ACE bất ngờ.
13. **Dùng @PostFilter cho list phân trang:** có thể trả trang thiếu item và lộ count, cần cân nhắc query/batch đúng semantics.
14. **Chỉ kiểm tra quyền ở controller:** service được gọi từ job/scheduler hoặc API khác vẫn có thể sửa dữ liệu; bảo vệ đúng ranh giới nghiệp vụ.

## 14. Checklist hoàn thành bài thực hành

Một triển khai ACL kế thừa và thu hồi đạt yêu cầu khi:

- Mỗi Folder/Document có object identity ổn định, đúng tenant, schema và parent ACL hợp lệ không có chu kỳ.
- Kế thừa chỉ hoạt động khi parent tồn tại và `entriesInheriting=true`, đúng expected của case multi-level.
- API cấp quyền chỉ do actor có quyền chia sẻ thực hiện; recipient/membership cùng tenant được xác minh.
- API thu hồi nói rõ scope: xóa direct grant, xóa parent grant, đặt override DENY hay tắt inheritance.
- Với mỗi thao tác, kiểm tra **quyền hiệu lực** của recipient trước và sau; trường hợp còn grant qua parent/group được giải thích chính xác.
- Có test negative cross-tenant, missing ACL, duplicate grant, concurrent update, cache stale và no-side-effect khi DENY.
- Dữ liệu ACL được cập nhật nhất quán trong transaction, cache/policy invalidation được xác minh ở mọi node liên quan.
- Không nhập nhằng `Permission`, `Role`, `Sid`, `Owner` và `Tenant membership`.

**Điểm cốt lõi:** trong ACL có kế thừa, quyền hiệu lực được tính từ ACL hiện tại **và có thể từ chuỗi ACL cha**, cộng với các chính sách tenant/role nằm ngoài ACL. Thu hồi một ACE chỉ có nghĩa là xóa một nguồn quyết định; để thực sự ngăn truy cập phải chứng minh rằng không còn đường ALLOW hợp lệ nào khác.

## 15. Tài liệu gốc

- Spring Security — Domain Object Security (ACLs): https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html
- Spring Security — `Acl` interface và inheritance: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/Acl.html
- Spring Security — `MutableAcl` interface: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/MutableAcl.html
- Spring Security — `JdbcMutableAclService`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/jdbc/JdbcMutableAclService.html
- Spring Security — `DefaultPermissionGrantingStrategy`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
