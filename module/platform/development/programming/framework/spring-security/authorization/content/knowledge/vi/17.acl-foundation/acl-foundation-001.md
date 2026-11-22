# Khi nào cần ACL thay cho role hoặc cờ sở hữu đơn giản

## 1. Vấn đề thực tế: quyền trên **hành động** khác quyền trên **từng đối tượng**

Một ứng dụng Spring Security thường bắt đầu với các role như `USER`, `EDITOR`, `ADMIN` hoặc authority như `document:read`. Sau đó bổ sung trường `ownerId` trên đối tượng để người tạo được sửa dữ liệu của mình. Hai cơ chế này giải quyết rất nhiều nghiệp vụ, nhưng bắt đầu thiếu khi **quyền truy cập khác nhau ở từng bản ghi và có thể được chia sẻ/thu hồi độc lập**.

Ví dụ: An tạo tài liệu số 42. An muốn cho Bình xem tài liệu nhưng không sửa; cho Chi chỉnh sửa trong một tuần; một nhóm kiểm toán được đọc; riêng tài liệu số 57 vẫn chỉ An được xem. Nếu chỉ có role `EDITOR` hoặc điều kiện `document.ownerId == currentUserId`, hệ thống khó biểu diễn các quyền đó mà không tạo hàng loạt role đặc biệt hoặc nhồi danh sách người được chia sẻ vào logic rải rác.

**ACL – Access Control List** – là một cách lưu quy tắc truy cập gắn với **từng tài nguyên cụ thể**. Một ACL thường chứa các **ACE – Access Control Entry**, mỗi entry chỉ rõ chủ thể nào được hoặc bị từ chối quyền nào trên đối tượng nào.

Mục tiêu của bài này không phải “dùng ACL mọi nơi”. Mục tiêu là biết **khi nào RBAC hoặc kiểm tra owner đã đủ, khi nào chỉ cần bảng chia sẻ đơn giản, và khi nào độ phức tạp của ACL thực sự đáng giá**.

## 2. Bốn khái niệm không nên đánh đồng

| Cơ chế | Câu hỏi chính | Dữ liệu chính | Ví dụ | Mạnh ở đâu? |
|---|---|---|---|---|
| **RBAC** (Role-Based Access Control) | Người dùng có được thực hiện **loại hành động** này không? | Role → authority | `ROLE_EDITOR` có quyền tạo tài liệu | Quyền tương đối ổn định theo chức trách |
| **Owner check** | Người dùng có phải chủ thể được phép với **bản ghi này** không? | `resource.owner_id` | Chỉ chủ sở hữu sửa bản nháp | Quy tắc một chủ sở hữu, đơn giản |
| **ACL** | **Chủ thể nào** có **quyền gì** trên **đối tượng nào**? | Object identity + subject + permission + grant/deny | Bình READ tài liệu 42; Chi WRITE tài liệu 42 | Ngoại lệ theo đối tượng, chia sẻ/thu hồi linh hoạt |
| **ABAC/policy theo thuộc tính** | Điều kiện nào của actor, object, môi trường cho phép hành động? | Thuộc tính, quan hệ, quy tắc | Chỉ sửa trước hạn chót, từ mạng nội bộ, trong tenant | Quy tắc động và phụ thuộc ngữ cảnh |

ACL và RBAC không loại trừ nhau. Một cấu hình hay gặp là:

1. **RBAC** xác định actor có quyền sử dụng chức năng `document:read` hay `document:share`.
2. **Tenant boundary** giới hạn actor được hoạt động trong tổ chức nào.
3. **Owner/ACL** quyết định actor có quyền trên *đúng tài liệu* nào.
4. **Business policy** kiểm tra trạng thái tài liệu, thời gian hiệu lực, khóa phê duyệt hoặc các điều kiện đặc thù.

Công thức khái niệm, không phải biểu thức bắt buộc cho mọi hệ thống:

~~~text
ALLOW = authenticated
    AND action_authority
    AND tenant_scope_matches
    AND object_permission
    AND business_constraints
~~~

Một authority chung **không thay** permission trên object. Ngược lại, một ACE cho phép đọc tài liệu **không nhất thiết** cho quyền gọi mọi API hoặc vượt quy tắc tenant.

## 3. Khi nào role là đủ?

Giữ RBAC nếu quyền chủ yếu gắn với chức năng hoặc phạm vi ổn định, **không phụ thuộc từng bản ghi**.

Ví dụ:
- `SUPPORT_AGENT` được dùng màn hình hỗ trợ; `FINANCE_ADMIN` được cấu hình phí.
- Người quản trị của tenant được xem bảng quản trị của tenant, theo quy tắc tổ chức đã xác nhận.
- Chỉ `REPORT_VIEWER` có quyền mở trang thống kê tổng hợp; không có cơ chế từng người chọn cấp quyền từng báo cáo.
- Quyền chủ yếu do quản trị viên cấp theo công việc, không thay đổi mỗi khi tạo một đối tượng.

Ví dụ Spring Security:

~~~java
@PreAuthorize("hasAuthority('report:read')")
public ReportSummary getSummary() {
    return reportService.computeSummary();
}
~~~

Đây là **đoạn tích hợp Spring**: cần bật method security, có service và bean phù hợp; không phải file Java độc lập. Quy tắc phù hợp nếu **một summary toàn cục đúng phạm vi actor** được cho phép bởi authority đó.

Nếu `getSummary()` trả dữ liệu riêng của từng tenant, vẫn cần lọc/giới hạn tenant tin cậy. Role có thể là **cổng vào chức năng**, không nhất thiết là bảo vệ đầy đủ cho dữ liệu.

**Dấu hiệu không cần ACL:** số quyền ít, không có ngoại lệ theo từng document, không có nút Share, không có delegate per-object, và các câu hỏi quyền có thể trả lời bằng role + tenant scope.

## 4. Khi nào cờ owner đơn giản là đủ?

Giữ kiểm tra ownership khi đặc tả thực sự là “chỉ tác giả/chủ sở hữu được đọc hoặc sửa”, đôi khi bổ sung một quyền admin rõ ràng. Mô hình thường chỉ cần:

~~~text
DOCUMENT(id, tenant_id, owner_user_id, title, ...)
~~~

Ví dụ service đọc một bản ghi có owner check:

~~~java
@Transactional(readOnly = true)
public DocumentView read(long id) {
    Actor actor = actorResolver.requireVerifiedActor();
    Document doc = repository
            .findByIdAndTenantId(id, actor.tenantId())
            .orElseThrow(ResourceNotFoundException::new);

    if (!actor.userId().equals(doc.getOwnerUserId())) {
        throw new AccessDeniedException("Document access denied");
    }
    return mapper.toView(doc);
}
~~~

Đây là **mã tích hợp minh họa**: các kiểu `Actor`, `Document`, repository, mapper và exception thuộc project. Scope tenant được lấy từ danh tính đã xác minh; không tin `tenantId` do client tự truyền. Chính sách owner-only là giả định của ví dụ, **không** phải mặc định mọi chủ sở hữu đều có mọi quyền.

Kiểm tra owner rất hợp lý cho:
- Hồ sơ cá nhân không chia sẻ.
- Bản nháp riêng tư chỉ người tạo được sửa.
- Một số tài nguyên nội bộ mà người tạo là người duy nhất có quyền thay đổi.
- API self-service vốn không có nhu cầu user-to-user delegation.

Ưu điểm: schema đơn giản, query/filter dễ tối ưu, dễ hiểu khi test, dễ audit ai sở hữu đối tượng. Không cần ACL nếu yêu cầu không đòi hỏi quyền ngoại lệ.

**Cờ `isOwner` do client gửi không phải bằng chứng sở hữu.** Ownership phải được xác định từ dữ liệu tin cậy của server; chỉ so sánh actor ID đã xác thực với owner ID lưu trong database.

## 5. Dấu hiệu ACL bắt đầu có giá trị

ACL thường đáng cân nhắc khi **đồng thời** có nhiều trong các dấu hiệu sau:

1. **Chia sẻ theo từng tài liệu:** An cho Bình xem tài liệu 42, nhưng không cho xem tài liệu 43.
2. **Nhiều mức quyền trên cùng bản ghi:** Bình READ, Chi WRITE, Dũng chỉ COMMENT, An ADMINISTER.
3. **Nhiều đối tượng được cấp quyền:** user, nhóm, tổ chức con hoặc authority cần có ACE riêng.
4. **Ủy quyền và thu hồi độc lập:** chủ tài liệu cấp quyền cho người khác rồi rút lại mà không đổi role toàn hệ thống.
5. **Nhiều nguồn quyền:** owner, người được mời, nhóm dự án, người duyệt, cộng tác viên; cần một nơi giải thích ai được làm gì.
6. **Quyền kế thừa:** các tài liệu nằm trong folder/project có thể kế thừa chính sách từ parent, nhưng có khả năng override hoặc ngăn kế thừa theo thiết kế.
7. **Yêu cầu giải thích/audit:** phải trả lời “ai đã cấp quyền đọc tài liệu này, khi nào, quyền gì, được thu hồi chưa?”.
8. **Quy tắc owner-only khiến code sinh nhiều nhánh ngoại lệ:** `owner OR sharedUser OR teamMember OR reviewer OR delegatedAdmin ...` xuất hiện ở nhiều service/query.

Một tình huống tiêu biểu là ứng dụng quản lý tài liệu hợp tác. Role `MEMBER` chỉ cho biết người dùng là thành viên ứng dụng. ACL gắn với từng document/folder mới quyết định thành viên ấy được READ, WRITE hay MANAGE ở đâu.

**Không phải cứ có một ngoại lệ là phải triển khai ACL framework.** Nếu chỉ chia sẻ một loại dữ liệu với một quyền đọc, bảng `document_share(document_id, user_id)` và query kiểm tra quan hệ có thể dễ vận hành hơn. ACL đáng giá khi số chiều quyền, loại subject, inheritance và nhu cầu quản trị tăng rõ rệt.

## 6. Bảng quyết định: chọn mức đơn giản nhất đáp ứng yêu cầu

| Tình huống | Lựa chọn thường phù hợp | Vì sao? |
|---|---|---|
| Chỉ người có role `ADMIN` được đổi cấu hình chung | RBAC | Không có quyền gắn theo bản ghi |
| Mỗi người sửa duy nhất profile của mình | Owner check | Quan hệ 1 user ↔ 1 resource rõ ràng |
| Mỗi document có owner, không chia sẻ | Owner + tenant scope | Ít trường hợp ngoại lệ |
| Chia sẻ read-only cho đúng một user, ít hành động | Bảng quan hệ share đơn giản | ACL framework có thể quá nặng |
| Document có READ/WRITE/COMMENT/SHARE cho nhiều người | ACL | Nhiều permission × subject × object |
| Project/folder có kế thừa quyền xuống nhiều resource | ACL có inheritance hoặc policy quan hệ phù hợp | Quan hệ parent-child và ngoại lệ quan trọng |
| Tài nguyên thuộc hàng trăm nhóm động, có quan hệ lồng nhau | ACL/relationship-based authorization, tùy thiết kế | Cần mô hình hóa subject/group và khả năng truy vấn |
| “Chỉ xem trong giờ hành chính từ thiết bị compliant” | ABAC hoặc policy engine | Phụ thuộc thuộc tính môi trường, không chỉ danh sách |
| User trong tenant A không bao giờ xem dữ liệu tenant B | Tenant scoping bắt buộc, có thể cộng ACL | ACL không thay ranh giới tenant |
| Hàng triệu record, permission chỉ theo owner và tenant | Scoped query/owner; tránh ACL không cần thiết | Mô hình gọn, truy vấn hiệu quả |
| Nhiều đối tượng có share link public với expiry | Chính sách share token/capability có vòng đời riêng; có thể kết hợp ACL | URL/token thời hạn không tự là ACE cơ bản |
| Hệ thống cần chính sách dựa trên quan hệ tổ chức phức tạp và suy diễn xuyên resource | RBAC + ACL hoặc ReBAC/policy engine | Một bảng ACL phẳng có thể khó biểu diễn quan hệ |

Bảng trên là **hướng ra quyết định**, không phải quy tắc cố định. Hãy đánh giá tính đúng đắn, độ đơn giản, quy mô và yêu cầu kiểm toán của use case thực tế.

## 7. Cây câu hỏi để chọn ACL hay không

~~~text
Quyền có phụ thuộc từng object ID?
 ├─ Không --> RBAC + scope tổ chức/tenant thường đủ
 └─ Có
     |
     +-- Có đúng một owner, không chia sẻ?
     |     ├─ Có --> owner check + query scope
     |     └─ Không
     |
     +-- Chỉ một quan hệ "được xem" đơn giản?
     |     ├─ Có --> cân nhắc bảng share đơn giản
     |     └─ Không
     |
     +-- Nhiều subject, nhiều permission, grant/revoke,
          quản trị/audit, inheritance?
             ├─ Có --> ACL đáng cân nhắc
             └─ Không --> giữ policy domain đơn giản
~~~

Trước khi đầu tư ACL, trả lời thêm:
- “Ai có quyền **grant/revoke** một quyền? Người nhận có được cấp tiếp không?”
- “Quyền của group được tính tại lúc grant hay lúc truy cập? Khi rời nhóm thì sao?”
- “Parent folder xóa/chuyển tenant thì child ACL thay đổi thế nào?”
- “Nếu không tìm thấy ACL hoặc ACL database lỗi, hệ thống làm gì?”
- “Có cần lọc hàng nghìn document trong list/pagination mà không bị N+1 query?”
- “Mức latency, cache invalidation và audit có chấp nhận được không?”

Nếu chưa có câu trả lời đáng tin cho các câu hỏi này, áp dụng ACL ngay có thể tăng bề mặt lỗi bảo mật hơn là giảm.

## 8. Ví dụ tiến hóa từ owner-only thành ACL

### Giai đoạn A: người tạo độc quyền

~~~text
document #42: owner=an, tenant=north
an READ, WRITE
binh DENY
chi DENY
~~~

Một cột `owner_user_id` và query scoped là đủ.

### Giai đoạn B: chia sẻ cho một người xem

~~~text
document #42: owner=an
share: (document=42, recipient=binh, permission=READ)
~~~

Nếu chỉ cần READ, có thể dùng bảng `document_share` với khóa duy nhất và logic điều kiện cố định. Đây chưa nhất thiết là thời điểm bắt buộc chuyển sang Spring Security ACL.

### Giai đoạn C: nhiều quyền, nhiều người, thu hồi

~~~text
document #42:
  owner an       READ + WRITE + MANAGE
  binh           READ
  chi            READ + WRITE
  team-review    READ + COMMENT

document #43:
  owner an       READ + WRITE + MANAGE
  binh           DENY
~~~

Role `MEMBER` của Bình không thể diễn đạt khác biệt giữa document 42 và 43. Owner check cũng không thể mô tả việc Chi được WRITE mà không phải owner. Đến đây ACL hoặc mô hình permission relation tương đương đáng giá.

### Giai đoạn D: folder và ngoại lệ

~~~text
folder /projects/north: team-review READ
  ├── #42: kế thừa team-review READ
  └── #43: không kế thừa vì chứa dữ liệu nhạy cảm
~~~

Lúc này cần xác định rõ inheritance, thứ tự grant/deny, đối tượng nào được override, và cách re-evaluate khi folder hoặc membership thay đổi. Không được mặc nhiên giả định “deny luôn thắng” hay “grant cuối cùng thắng”: kết quả phụ thuộc engine và policy mà ứng dụng chọn.

## 9. ACL có cấu trúc gì?

Mô hình chung:

~~~text
Subject (user/group/authority)
          |
          | ACE: permission + grant/deny
          v
Object Identity (type, object ID, tenant scope)
          |
          +-- ACL entries
          +-- optional parent ACL / inheritance
~~~

Các thành phần quan trọng:

- **Object identity:** xác định một bản ghi, thường gồm resource type và ID. Với multi-tenant nên bảo đảm định danh, query và policy luôn bao gồm tenant scope đáng tin.
- **SID – Security Identity:** người dùng hoặc authority/nhóm được cấp quyền. Trong Spring ACL có `PrincipalSid` và `GrantedAuthoritySid`.
- **Permission:** quyền như READ, WRITE, CREATE, DELETE, ADMINISTRATION. Có thể định nghĩa quyền khác nếu business cần; cần quy định nghĩa và hệ quả.
- **ACE – Access Control Entry:** một mục ghi SID được cho phép hoặc bị từ chối một permission trên object.
- **ACL:** tập ACE gắn với object; có thể có parent và quy tắc cho kế thừa.
- **Grant/revoke:** nghiệp vụ thêm, thay đổi hoặc loại bỏ ACE, cùng audit và điều kiện người được quyền chia sẻ.

Chính sách **nên mặc định không cấp quyền** khi không có ACE/owner/policy nào chứng minh quyền. Nhưng chi tiết xử lý “không có ACL”, “ACE deny” và “abstain” khác nhau giữa các engine; phải chọn cách fail-closed rõ ràng và test.

**Không nhầm ACL owner với owner domain:** trong Spring ACL, `Acl.getOwner()` đại diện SID sở hữu ACL theo nghĩa framework. Nó không tự chứng minh rằng người đó là `document.ownerUserId` của nghiệp vụ hay mặc nhiên có toàn quyền sửa nội dung. Chính sách owner và administrative rights phải được định nghĩa/kiểm thử.

## 10. Spring Security ACL cung cấp những gì?

Spring Security có module **`spring-security-acl`** riêng cho domain-object authorization. Tài liệu chính thức mô tả cơ chế này cho trường hợp phải xét “ai, ở đâu, đối tượng nào”, thay vì chỉ chặn một URL hay method theo role.

Bốn bảng cốt lõi trong triển khai JDBC mặc định:

| Bảng | Vai trò |
|---|---|
| `ACL_SID` | Chủ thể quyền: principal hoặc granted authority |
| `ACL_CLASS` | Loại đối tượng domain cần bảo vệ |
| `ACL_OBJECT_IDENTITY` | Đối tượng cụ thể, chủ ACL, parent và cờ inheritance |
| `ACL_ENTRY` | ACE cho một object và SID, permission bit mask, grant/deny, audit flags |

Các interface/class liên quan:

- `Acl`, `AccessControlEntry`, `Permission`, `Sid`, `ObjectIdentity`.
- `AclService` để đọc ACL; `MutableAclService` để cập nhật.
- `JdbcMutableAclService` và `BasicLookupStrategy` để hỗ trợ lưu trữ/đọc hiệu quả theo JDBC.
- `AclPermissionEvaluator` để kết nối với expression `hasPermission(...)` trong method security.
- `BasePermission` cung cấp các quyền bitmask thường gặp. Ví dụ READ là bit 0, WRITE là bit 1, CREATE là bit 2, DELETE là bit 3 và ADMINISTRATION là bit 4.

**Bit mask không phải số lượng object.** Các bit đại diện **loại permission**, không phải từng document. Hệ thống vẫn có thể có hàng triệu object identity và ACE, dù biểu diễn permission bằng các bit trong một số nguyên.

Module ACL không tự động tạo/xóa ACE mỗi khi ứng dụng `save()` hoặc `delete()` một entity. Ứng dụng phải chủ động quản lý vòng đời ACL, đồng bộ với tạo/xóa tài nguyên, grant/revoke, chuyển owner và chuyển project; không được giả định `@EnableMethodSecurity` sẽ tự làm việc đó.

Spring Security 7.x vẫn có tài liệu về ACL, nhưng khi nâng version cần theo migration guide. Với hệ thống cũ dùng `AclEntryVoter`/after-invocation provider, tài liệu migration 7 khuyến nghị chuyển trọng tâm sang `AclPermissionEvaluator` thay vì giữ plugin dựa trên API voter cũ.

Nguồn chính thức:
- [Spring Security – Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html)
- [Spring Security 6.5 → 7 – ACL migration](https://docs.spring.io/spring-security/reference/6.5/migration-7/acl.html)

## 11. Mô hình permission: đừng phát minh quan hệ không được xác minh

Tùy ứng dụng, các permission có thể là:
- **READ**: đọc nội dung và metadata được cho phép.
- **WRITE**: sửa nội dung, nhưng chưa chắc được chia sẻ.
- **COMMENT**: thêm bình luận, chưa chắc được chỉnh sửa nội dung.
- **SHARE/MANAGE**: mời người dùng, thu hồi quyền.
- **DELETE**: xóa tài nguyên; thường cần guard mạnh.
- **ADMINISTRATION**: quản lý ACL hoặc policy; ý nghĩa khác nhau tùy domain.

Nếu một sản phẩm gọi quyền “Editor”, phải **quy định rõ** editor gồm WRITE+READ hay thêm COMMENT/SHARE/DELETE. Đừng suy luận `WRITE` mặc nhiên bao hàm `DELETE` hoặc `MANAGE`: trong ACL có thể cấp riêng.

Ví dụ bảng chính sách nghiệp vụ (không phải chính sách tích hợp sẵn của Spring ACL):

| Cấp truy cập | READ | COMMENT | WRITE | SHARE | DELETE |
|---|---|---|---|---|---|
| Viewer | Có | Không | Không | Không | Không |
| Commenter | Có | Có | Không | Không | Không |
| Editor | Có | Có | Có | Không | Không |
| Manager | Có | Có | Có | Có | Có |

Bảng là một cách ánh xạ **từ cấp business sang tập permission**, không phải vai trò cố định do Spring Security tạo ra. Với những tài liệu có rủi ro cao, DELETE và SHARE có thể còn đòi phê duyệt thứ hai hoặc MFA mới.

### ACE allow và deny

Một số ACL cho phép cả mục *grant* và *deny*. Không nên tự viết logic:

~~~java
// Sai về mặt thiết kế nếu engine có deny/inheritance:
return aclEntries.stream().anyMatch(AccessEntry::isGranting);
~~~

Điều kiện trên bỏ qua loại permission, subject, target, thứ tự ACE và deny. Khi dùng Spring ACL, hãy để API `Acl.isGranted(...)` hoặc `AclPermissionEvaluator` xử lý semantics thực tế; Javadoc khuyến cáo không duyệt trực tiếp `getEntries()` để đưa ra quyết định. Nếu tự xây engine, phải có đặc tả tường minh về precedence và inheritance.

## 12. Kết hợp role, owner, tenant và ACL: thứ tự an toàn

Một policy tiêu biểu cho document riêng:

~~~text
1. Xác minh authentication và actor.
2. Kiểm tra actor có quyền sử dụng chức năng tương ứng.
3. Xác minh tenant scope; không tin tenant từ client.
4. Truy vấn object theo ID và tenant đã xác minh.
5. Xác định quyền object:
      owner hoặc ACE hợp lệ hoặc quy tắc quản trị đã phê duyệt.
6. Kiểm tra business constraints: locked, archived, legal hold, ...
7. Chỉ sau đó mới đọc thông tin nhạy cảm/trả dữ liệu/ghi side effect.
~~~

**Các điều kiện bắt buộc phải AND với nhau.** Nếu policy là `tenantMatch AND (isOwner OR hasAce) AND actionAllowed`, đừng viết sai thành `tenantMatch OR isOwner OR hasAce`. Một user có ACE trên ID trùng nhưng khác tenant không được vượt ranh giới tenant.

Với một admin, cũng cần xác định admin của phạm vi nào: `TENANT_ADMIN` không đương nhiên là admin của toàn bộ tenant khác; một global superuser nếu có phải là capability được quản trị, audit và test riêng.

ACL **không thay authentication**, RBAC ở tầng chức năng, việc giới hạn dữ liệu theo tenant hoặc logic trạng thái nghiệp vụ. Nó là một phần trong phép quyết định, không phải lớp bảo vệ duy nhất.

## 13. Spring method security: sử dụng PermissionEvaluator

Khi đã cấu hình `AclService` và `AclPermissionEvaluator`, có thể dùng expression `hasPermission(...)` để kiểm tra quyền với object hoặc object ID/type.

Ví dụ minh họa:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentQueryService {
    @PreAuthorize(
        "isAuthenticated() and hasAuthority('document:read') " +
        "and hasPermission(#documentId, 'com.example.domain.Document', 'READ')"
    )
    @Transactional(readOnly = true)
    public DocumentView readDocument(Long documentId) {
        // Query phải thêm tenant scope và các điều kiện nghiệp vụ.
        return loadScopedDocument(documentId);
    }

    private DocumentView loadScopedDocument(Long documentId) {
        throw new UnsupportedOperationException("Domain implementation");
    }
}
~~~

Đây là **snippet tích hợp**, không phải bài chạy độc lập. Nó minh họa các điều kiện cần, không phải triển khai đầy đủ: `com.example.domain.Document` là tên class ví dụ, ID/type phải khớp ObjectIdentity thực tế; cần cấu hình expression handler để `hasPermission` dùng ACL evaluator, repository scoped, principal tin cậy, và xử lý exception hợp lệ. Mã `loadScopedDocument` chỉ là cấu trúc để diễn giải và phải được thay bằng logic domain.

Một cách cấu hình expression handler trên Spring Security hỗ trợ method security hiện đại:

~~~java
@Configuration
@EnableMethodSecurity
class SecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclPermissionEvaluator permissionEvaluator) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(permissionEvaluator);
        return handler;
    }

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(AclService aclService) {
        return new AclPermissionEvaluator(aclService);
    }
}
~~~

Đây cũng là **mã tích hợp**, cần các import Spring Security/Spring Context và một `AclService` được cấu hình từ datasource. Đường đăng ký/cấu hình thay đổi tùy version và stack, nên kiểm tra tài liệu/version project. `@EnableMethodSecurity` không tự sinh các bảng ACL hoặc service.

Một vài lưu ý cần thiết:
- Method security dựa trên Spring AOP proxy: lời gọi nội bộ `this.readDocument(...)` có thể bỏ qua interceptor, tùy chế độ AOP; phải test qua bean Spring thực tế.
- `hasPermission` kiểm tra **đối tượng/ID và permission**, không thay thế lọc tenant trong repository.
- Với dữ liệu nhiều trường, có thể cần quyền khác nhau cho metadata, nội dung, file đính kèm; ACL tài liệu không tự cho phép mọi trường.
- Với write, đặt kiểm tra quyền **trước mutation**. Tránh chỉ dùng `@PostAuthorize` sau khi dữ liệu đã được ghi hoặc sự kiện đã phát.

## 14. Danh sách và phân trang: ACL có chi phí không nhỏ

Kiểm tra ACL cho **một** document tương đối dễ. Khó hơn là “liệt kê trang 20 document mà user được xem” từ một kho hàng triệu document.

Mẫu sai về kết quả:

~~~text
SELECT 20 documents bất kỳ
--> lọc từng document bằng ACL sau khi query
--> chỉ còn 3 document được phép
--> trả page size 3, total count sai/ngụ ý dữ liệu nhạy cảm
~~~

Mẫu này có thể dẫn tới:
- **N+1 ACL lookups**: mỗi document thêm một lần truy vấn để kiểm tra permission.
- Trang kết quả không đủ item, số trang và `totalElements` không đúng.
- Đọc document ngoài quyền vào memory/cache/log trước khi lọc.
- Rò rỉ thông tin qua count, sort, search facets, export hoặc thời gian phản hồi.
- CPU/DB pressure tăng mạnh khi số ACL và group membership lớn.

Chiến lược tốt hơn khi ACL nằm trong DB có thể là:
- **Query-first**: thêm điều kiện owner/tenant/permission vào truy vấn; bảo đảm countQuery và sorting nhất quán.
- **Read batch ACL** theo danh sách object identity/SID khi không thể đẩy toàn bộ predicate xuống DB; bù thêm dữ liệu để đủ page, nhưng phải tính lại semantics pagination và privacy.
- **Materialized authorized-view/permission index** hoặc cache kiểm soát invalidation cho bài toán lớn.
- Tách API detail và API list: list trả metadata đã scoped; detail vẫn **re-check authorization** trên object.
- Test với dữ liệu tập lớn, permission thay đổi, quyền nhóm và nhiều tenant.

Spring ACL có `LookupStrategy` tối ưu batch/caching, nhưng nó **không tự tạo ra SQL phân trang đã lọc đúng quyền** cho mọi repository và use case. Tránh cho rằng bật ACL là tự xử lý việc list và count.

## 15. Grant, revoke, share và audit có chi phí vòng đời

Nếu quyền được quản lý bởi ACL, cần một API/luồng quản trị riêng, không chỉ CRUD của document.

Các thao tác cần thiết:
- **Grant**: chủ thể có quyền chia sẻ tạo ACE phù hợp cho recipient, action và đúng resource.
- **Revoke**: xóa/đổi ACE và bảo đảm truy cập bị mất sau khi thay đổi có hiệu lực.
- **List grants**: hiển thị ai có quyền gì; không để người không có quyền MANAGE đọc danh sách nhạy cảm.
- **Transfer ownership**: cập nhật quyền owner-domain và ACL owner nếu hợp đồng đòi hỏi; không nhầm hai khái niệm.
- **Delete resource**: dọn ACL của object, các ACE và cache tương ứng theo lifecycle, tránh ACL mồ côi.
- **Remove user/group**: xử lý ACE, membership, SID, token/session và cache đúng semantics.
- **Inherit/uninherit**: kiểm soát tác động khi folder/project đổi parent hoặc từ chối kế thừa.
- **Audit**: ai cấp/thu hồi, lúc nào, quyền nào, object nào, kết quả ra sao.

**Ai có quyền chia sẻ?** Không mặc định user có `WRITE` được cấp `ADMINISTRATION` cho người khác. Quyền đọc/ghi, quyền quản lý ACL và quyền ủy quyền tiếp phải được định nghĩa riêng.

Dữ liệu quản trị quyền cần chống race/TOCTOU. Ví dụ một user có quyền SHARE ở thời điểm T1 nhưng bị thu hồi trước khi grant ở T2. Đặt kiểm tra gần mutation và chọn transaction/locking phù hợp với yêu cầu nhất quán. Nếu ACL nằm ở service khác, cần xác định cách xử lý eventual consistency và fail-closed khi hệ thống chưa kịp đồng bộ.

### Quyền có hạn dùng

“Tài liệu được chia sẻ cho Chi **trong 7 ngày**” là yêu cầu rất phổ biến, nhưng một ACE bitmask cơ bản của Spring ACL **không tự giải quyết toàn bộ thời hạn hết hiệu lực, invitation và revocation token**. Cần thêm mô hình expiry hoặc policy riêng, ví dụ bảng share có `expires_at` và kiểm tra ở thời điểm truy cập; nếu mở rộng ACL, phải thiết kế migration/schema/logic phù hợp.

Đừng cấp grant vĩnh viễn rồi chỉ ẩn nút Share sau 7 ngày ở UI: API vẫn có thể cho phép.

## 16. Group membership và kế thừa: điểm cần kiểm tra

Nếu quyền được cấp cho “team-review”:
- ACL engine cần biết actor thuộc team nào **tại thời điểm đánh giá**.
- Với Spring ACL, SID có thể đại diện principal hoặc granted authority. Nếu dùng authority nhóm, authentication hoặc resolver cần phản ánh đúng membership đáng tin.
- Khi user rời group, quyền thừa hưởng qua group phải mất theo contract. Một token chứa membership cũ hoặc cache stale có thể kéo dài quyền.
- Nếu nhóm lồng nhóm, phải quy định cách mở rộng quan hệ, cycle detection và chi phí truy vấn; không giả định module ACL mặc định tự suy luận mọi cây tổ chức.
- Với ACL parent inheritance, phân biệt kế thừa **permission của parent** và kế thừa **owner domain**; không tự đồng nhất.

Đối với tổ chức lớn với quan hệ nhóm/folder nhiều cấp, mô hình ReBAC hoặc policy engine có thể phù hợp hơn cách tạo ACE thủ công cho mọi object/user. Quan trọng là **bài toán quyền thực tế**, không phải tên framework.

## 17. Demo Java 17 độc lập: khi ACL tạo khác biệt

Chương trình sau mô phỏng owner + role tenant admin + ACL READ/WRITE trên **từng document**. Đây là Java thuần, không dùng Spring, không kết nối DB. Nó giúp thấy tại sao quyền của Bình trên document 42 không đồng nghĩa có quyền trên mọi tài liệu.

Tạo file `AclChoiceDemo.java`:

~~~java
import java.util.EnumSet;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public class AclChoiceDemo {

    enum Action { READ, WRITE }
    enum Role { USER, TENANT_ADMIN }

    record Actor(String userId, String tenantId, Set<Role> roles) { }
    record Document(long id, String tenantId, String ownerId) { }
    record ObjectKey(String tenantId, long id) { }

    static final class Policy {
        private final Map<ObjectKey, Map<String, EnumSet<Action>>> acl =
                new HashMap<>();

        void grant(Document document, String userId, Action action) {
            ObjectKey key = new ObjectKey(document.tenantId(), document.id());
            acl.computeIfAbsent(key, ignored -> new HashMap<>())
                    .computeIfAbsent(
                            userId, ignored -> EnumSet.noneOf(Action.class))
                    .add(action);
        }

        void revoke(Document document, String userId, Action action) {
            Map<String, EnumSet<Action>> entries =
                    acl.get(new ObjectKey(document.tenantId(), document.id()));
            if (entries == null) {
                return;
            }
            EnumSet<Action> rights = entries.get(userId);
            if (rights != null) {
                rights.remove(action);
                if (rights.isEmpty()) {
                    entries.remove(userId);
                }
            }
        }

        boolean allowed(Actor actor, Document document, Action action) {
            if (actor == null || document == null || action == null
                    || actor.userId() == null || actor.userId().isBlank()
                    || actor.tenantId() == null || actor.roles() == null
                    || document.id() <= 0
                    || !actor.tenantId().equals(document.tenantId())) {
                return false;
            }

            // Một admin chỉ có quyền trong tenant đã xác minh.
            if (actor.roles().contains(Role.TENANT_ADMIN)) {
                return true;
            }

            // Ví dụ này chủ ý cho owner quyền READ và WRITE.
            if (actor.userId().equals(document.ownerId())) {
                return true;
            }

            Map<String, EnumSet<Action>> entries =
                    acl.get(new ObjectKey(document.tenantId(), document.id()));
            if (entries == null) {
                return false;
            }
            EnumSet<Action> rights = entries.get(actor.userId());
            return rights != null && rights.contains(action);
        }
    }

    public static void main(String[] args) {
        Document document = new Document(42, "north", "an");
        Actor an = new Actor("an", "north", Set.of(Role.USER));
        Actor binh = new Actor("binh", "north", Set.of(Role.USER));
        Actor chi = new Actor("chi", "north", Set.of(Role.USER));
        Actor southAdmin = new Actor(
                "admin", "south", Set.of(Role.TENANT_ADMIN));

        Policy policy = new Policy();
        policy.grant(document, "binh", Action.READ);

        System.out.println("owner-write="
                + policy.allowed(an, document, Action.WRITE));
        System.out.println("shared-read="
                + policy.allowed(binh, document, Action.READ));
        System.out.println("shared-write="
                + policy.allowed(binh, document, Action.WRITE));
        System.out.println("not-shared-read="
                + policy.allowed(chi, document, Action.READ));
        System.out.println("cross-tenant-admin="
                + policy.allowed(southAdmin, document, Action.WRITE));

        policy.revoke(document, "binh", Action.READ);
        System.out.println("after-revoke-read="
                + policy.allowed(binh, document, Action.READ));
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac AclChoiceDemo.java
java AclChoiceDemo
~~~

Stdout:

~~~text
owner-write=true
shared-read=true
shared-write=false
not-shared-read=false
cross-tenant-admin=false
after-revoke-read=false
~~~

Giải thích:
1. An là owner nên được WRITE theo **policy của ví dụ**, không phải vì role USER.
2. Bình có ACE READ nên xem được tài liệu 42 nhưng không WRITE.
3. Chi cũng là USER, không có owner/ACE nên không được READ.
4. Một TENANT_ADMIN của tenant south không vượt được guard tenant north.
5. Sau revoke, Bình mất READ ngay trong map của demo.

**Giới hạn của demo:** actor được khởi tạo trực tiếp trong code; trong ứng dụng thật phải lấy actor/tenant/role từ nguồn xác thực. Map trong memory không có persistence, concurrency, audit, denial ACE, group membership, inheritance, expiry hoặc cơ chế thu hồi cache. Mã này chỉ nhằm minh họa **chênh lệch sức biểu đạt** của ACL so với role/owner, không phải ACL engine production.

## 18. Kiểm thử bảo mật khi quyết định dùng ACL

### 18.1. Ma trận bắt buộc

| Tình huống | Kết quả mong muốn |
|---|---|
| Owner được READ/WRITE theo policy đã công bố | ALLOW trong scope hợp lệ |
| Người không phải owner, không có ACE | DENY |
| Người có ACE READ nhưng yêu cầu WRITE | DENY |
| Người có ACE WRITE nhưng không có SHARE | Không được thay đổi ACL |
| Người đã bị revoke | DENY ngay sau hiệu lực thu hồi theo hợp đồng |
| User có role USER nhưng tài liệu không chia sẻ | DENY |
| User có role TENANT_ADMIN của tenant khác | DENY |
| User trong group có ACE READ | ALLOW nếu membership đã xác minh |
| User rời group | DENY nếu không có grant độc lập khác |
| Tài liệu không tồn tại trong tenant | Không cấp, không lộ dữ liệu |
| ACL không tồn tại/ACE thiếu | Không cấp theo default đã thiết kế |
| ACL service timeout | Không thực hiện thao tác; báo lỗi kỹ thuật |
| Có ACE deny và ACE grant khác | Kết quả theo precedence/inheritance đã kiểm thử |
| Parent ACL có READ, child tắt inheritance | Không tự kế thừa |
| Resource chuyển tenant/owner | Không giữ quyền cũ trái policy |
| Listing 1000 objects với một số được phép | Chỉ trả objects hợp lệ, count/pagination đúng |
| User đoán ID của tenant khác | Không đọc, ghi, log hoặc cache dữ liệu ngoài quyền |
| Batch export hoặc background job | Quyền được kiểm tra trên mọi resource và đúng identity |

### 18.2. Test API và data leakage

Không chỉ assert HTTP 403. Cần kiểm tra:
- Tài liệu bị từ chối **không bị update/delete**.
- Count, search suggestion, sort order, thumbnail, file download và attachment endpoint không rò rỉ tài liệu.
- Không xuất hiện metadata nhạy cảm trong error message hoặc log client.
- Cấu hình nhiều SecurityFilterChain/method security không bỏ qua ACL.
- Các đường gọi khác ngoài HTTP (message, scheduler, direct service) vẫn áp dụng resource policy tương ứng.
- Cache permission được invalidate khi revoke, membership hoặc parent ACL thay đổi.
- Query list và `countQuery` không vô tình bao gồm bản ghi ngoài quyền.

**Test hiệu năng:** đo số SQL query trên mỗi trang, latency p95/p99, số ACE load, hit rate cache, tốc độ grant/revoke và hành vi khi ACL database không khả dụng. Một policy đúng nhưng khiến mỗi page 20 document phát sinh 200 query có thể không vận hành bền vững.

## 19. Quy trình quyết định và triển khai từng bước

**Bước 1 — Viết bảng quyền nghiệp vụ.** Liệt kê subject (user/group/admin), resource (document/folder/project), action, điều kiện tenant và owner. Xác định ai cấp/thu hồi quyền.

**Bước 2 — Kiểm tra xem role + owner có đủ không.** Nếu quy tắc còn đơn giản, giữ như vậy. Tránh thiết kế ACL chỉ để “mở rộng tương lai” khi chưa có yêu cầu thật.

**Bước 3 — Thử mô hình share table nhỏ.** Nếu chỉ cần một quyền READ, bảng chia sẻ với khóa duy nhất và query scoped có thể giảm đáng kể phức tạp.

**Bước 4 — Chọn ACL khi số chiều tăng.** Đặt quy tắc cho quyền READ/WRITE/COMMENT/SHARE, nhiều SID, inheritance, grant/deny, audit và cơ chế revoke.

**Bước 5 — Thiết kế default deny và lifecycle.** Không có ACE không tự là public. Quy định rõ thao tác tạo/xóa object, grant/revoke, parent/membership change, outage, cache và TTL.

**Bước 6 — Chọn thư viện/engine phù hợp.** Với Spring Security ACL, kiểm tra tương thích version/ID type/schema, `AclService`, `AclPermissionEvaluator`, giới hạn policy cần mở rộng. Với quan hệ động rất phức tạp, cân nhắc engine khác thay vì ép mọi thứ vào ACE bitmask.

**Bước 7 — Thực thi ở ranh giới service và query.** Method security chặn hành động; repository scoped tenant và object policy bảo vệ từng dữ liệu. Đảm bảo Spring proxy không bị self-invocation bypass.

**Bước 8 — Tối ưu list/pagination và audit.** Ưu tiên query-first hoặc batch permission, tránh N+1. Định nghĩa cách tính total/count và cache invalidation.

**Bước 9 — Test revoke và lỗi hệ thống.** Đây là nơi phát hiện lỗi thực tế: user vẫn xem được sau revoke, admin tenant khác đọc được, service permission timeout nhưng vẫn cho qua, hoặc file download bỏ quên ACL.

**Bước 10 — Triển khai theo từng resource type.** Không cần chuyển mọi bảng trong hệ thống sang ACL cùng lúc. Theo dõi các loại object có nhu cầu chia sẻ rõ ràng, giữ RBAC/owner ở những nơi vẫn phù hợp.

## 20. Những sai lầm thường gặp

**Sai lầm 1: “Có role EDITOR là sửa mọi document.”** Role cho quyền chức năng, không chứng minh quyền đối tượng. **Sửa:** kiểm tra tenant và object-level permission.

**Sai lầm 2: “Cứ có ownerId thì không cần ACL.”** OwnerId không biểu diễn nhiều người với nhiều mức quyền. **Sửa:** thêm mô hình quan hệ/ACL khi có chia sẻ thực sự.

**Sai lầm 3: “Chỉ cần một share table đã phải dùng Spring ACL đầy đủ.”** Không đúng: một quan hệ READ duy nhất có thể đơn giản hơn. **Sửa:** chọn mức phức tạp tối thiểu.

**Sai lầm 4: “ACL tự bảo vệ mọi list và count.”** ACL object-level không tự giải bài toán pagination và search. **Sửa:** xây query được lọc theo quyền, batch/invalidation phù hợp.

**Sai lầm 5: “Không thấy ACL thì cho phép theo role.”** Có thể mở quyền không chủ đích. **Sửa:** policy fallback phải được thiết kế, mặc định không cấp với resource private.

**Sai lầm 6: “Owner của ACL luôn là owner business.”** Hai khái niệm khác nhau. **Sửa:** ánh xạ tường minh, kiểm thử transfer owner.

**Sai lầm 7: “WRITE bao hàm SHARE/DELETE.”** Không phải chân lý chung. **Sửa:** tách permission theo hành vi nghiệp vụ.

**Sai lầm 8: “Có quyền nhóm thì lưu một lần trong token mãi mãi.”** Membership có thể thay đổi. **Sửa:** xác định thời gian hiệu lực của token/cache và cơ chế thu hồi.

**Sai lầm 9: “ACL service lỗi thì bỏ qua cho ứng dụng hoạt động.”** Đây là fail-open. **Sửa:** không thực hiện thao tác khi chưa xác minh quyền.

**Sai lầm 10: “Kiểm tra ACL sau khi ghi xong cũng được.”** Có nguy cơ side effect không thể rollback. **Sửa:** guard trước mutation.

**Sai lầm 11: “Chỉ cần thêm @PreAuthorize là tất cả lời gọi được bảo vệ.”** Self-invocation hoặc service không đi qua proxy có thể bỏ qua method security. **Sửa:** tổ chức service boundary và test qua Spring bean thực tế.

**Sai lầm 12: “Bật spring-security-acl sẽ tự tạo ACE khi save entity.”** Framework không tự đồng bộ toàn bộ vòng đời ACL theo repository. **Sửa:** code transactional grant/revoke/create/delete và audit.

## 21. Checklist quyết định cuối cùng

- [ ] Quyền có thực sự khác nhau theo object ID, hay chỉ khác nhau theo chức năng?
- [ ] Có cần user-to-user/group sharing, nhiều permission và grant/revoke không?
- [ ] Owner-check hoặc share table một quyền có đáp ứng đủ không?
- [ ] Đã xác định rõ tenant scope, actor identity và resource identity đáng tin?
- [ ] Đã định nghĩa quyền READ/WRITE/COMMENT/SHARE/DELETE độc lập?
- [ ] Đã xác định ai được cấp quyền, cấp tiếp, thu hồi và chuyển owner?
- [ ] Có requirement về inheritance, explicit deny, expiry hoặc nhóm động không?
- [ ] Có default DENY khi ACL/permission không tồn tại hoặc không xác minh được?
- [ ] Có chiến lược bảo vệ list/search/count/export/download, không chỉ detail API?
- [ ] Có thiết kế database/index/batch read tránh N+1 ACL lookups?
- [ ] Có audit, cache invalidation, transaction và quy trình xử lý revoke?
- [ ] Có integration test Spring proxy, permission evaluator và các điểm vào ngoài HTTP?
- [ ] Có kiểm thử multi-tenant, permission stale, outage và side effect?
- [ ] Chi phí vận hành ACL có tương xứng lợi ích chia sẻ theo object?

**Kết luận:** Dùng **role** khi quyền đi theo chức năng; dùng **owner-check** khi mỗi bản ghi có một chủ thể được quyền theo quy tắc đơn giản; dùng **share table nhỏ** khi chỉ có một vài quan hệ dễ biểu diễn. Chọn **ACL** khi một tài nguyên cần nhiều subject, nhiều mức permission, cấp/thu hồi linh hoạt, có thể có inheritance và cần quản trị/audit quyền theo từng object. Trong mọi trường hợp, **tenant isolation, authentication, scope query và fail-closed** vẫn là các bảo vệ bắt buộc.

## Tài liệu tham khảo

- [Spring Security – Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): cấu trúc SID/ACL/ACE, permission, schema JDBC, `AclService` và `AclPermissionEvaluator`.
- [Spring Security 6.5 – ACLs](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html): đối chiếu behavior theo phiên bản 6.5.
- [Spring Security – Acl interface API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/Acl.html): `isGranted`, `getEntries` và semantics về parent/inheritance.
- [Spring Security – AclPermissionEvaluator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/AclPermissionEvaluator.html): kiểm tra permission theo đối tượng/ID.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, annotation và proxy interception.
- [Spring Security 6.5 → 7 ACL migration](https://docs.spring.io/spring-security/reference/6.5/migration-7/acl.html): ưu tiên `AclPermissionEvaluator` khi di chuyển khỏi voter API cũ.
