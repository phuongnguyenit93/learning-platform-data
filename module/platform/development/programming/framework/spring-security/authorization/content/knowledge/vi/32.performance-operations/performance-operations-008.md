# Rà soát quyền tích lũy, tài khoản quản trị và chính sách hết hạn

## 1. Vì sao phải rà soát authorization khi hệ thống đang vận hành?

Quyền truy cập không đứng yên sau lúc người dùng đăng nhập hoặc sau lần triển khai đầu tiên. Qua nhiều lần chuyển bộ phận, tham gia dự án, được cấp quyền tạm thời, nhận vai trò kế thừa và dùng tài khoản quản trị để xử lý sự cố, một danh tính có thể tích lũy nhiều quyền hơn nhu cầu hiện tại. Các quyền từng hợp lệ cũng có thể hết thời hạn nhưng vẫn xuất hiện trong session, token, cache hoặc một nguồn cấp quyền khác.

Rà soát authorization là hoạt động **xác minh quyền thực sự đang có hiệu lực**, đối chiếu với nhu cầu công việc và chính sách hiện hành, đưa ra quyết định giữ/giảm/thu hồi, rồi kiểm chứng quyền đã đổi trên đường request thực tế. Đối với Spring Security, không thể coi việc nhìn thấy `ROLE_ADMIN` hay `REPORT_EXPORT` trong `Authentication.getAuthorities()` là toàn bộ câu trả lời. Hệ thống còn có thể dùng role hierarchy, group, quyền trực tiếp theo đối tượng, tenant, ACL, giới hạn thời gian và các điều kiện nghiệp vụ.

Ba mục tiêu vận hành của bài này:

1. **Quyền tích lũy (privilege accumulation):** phát hiện quyền thừa, quyền trùng nguồn, quyền không còn lý do tồn tại và các đường kế thừa quyền bị bỏ quên.
2. **Tài khoản đặc quyền:** kiểm tra ai có khả năng vận hành nhạy cảm, khi nào sử dụng, được bảo vệ ra sao, và có thể thu hồi quyền quản trị mà không gây gián đoạn ngoài ý muốn hay không.
3. **Chính sách hết hạn:** kiểm tra grant, ngoại lệ, quyền tạm và chính sách có ngày hiệu lực/hết hiệu lực; bảo đảm quyền hết hạn thật sự bị từ chối khi gọi API, bất kể đã có job dọn dữ liệu hay chưa.

Bài tập trung vào **authorization của Spring Security trong vận hành**. Authentication xác minh danh tính, còn authorization quyết định danh tính ấy được làm gì, với đối tượng nào, trong ngữ cảnh và thời gian nào. Chỉ thành công đăng nhập hoặc có token hợp lệ không đồng nghĩa có quyền thực hiện tác vụ.

## 2. Các khái niệm phải tách riêng

| Khái niệm | Ý nghĩa | Rủi ro khi hiểu sai |
| --- | --- | --- |
| Principal | Danh tính người, dịch vụ, job hoặc tài khoản quản trị đang hành động | Gộp tài khoản dùng chung, không truy được người chịu trách nhiệm |
| Role | Nhóm quyền như `ROLE_ANALYST`, `ROLE_ADMIN` | Nghĩ rằng role được gán chỉ có quyền ghi rõ trên role đó |
| Authority | Chuỗi quyền mà Spring Security dùng để ra quyết định, ví dụ `REPORT_READ` | Xem authority trong session là quyền luôn còn hiệu lực theo thời gian |
| Role hierarchy | Quyền/vai trò kế thừa theo cấu hình | Thu hồi vai trò con nhưng quyền vẫn đến từ vai trò cha |
| Grant | Một lần cấp quyền, có nguồn, phạm vi, trạng thái, ngày hiệu lực, người duyệt | Chỉ nhìn quyền cuối cùng mà không biết nguồn để thu hồi |
| Effective permission | Quyền thực sự được phép sau khi áp dụng mọi điều kiện | Cộng tất cả quyền trực tiếp và kế thừa, bỏ qua deny, scope hoặc expiration |
| Scope | Đối tượng, tài nguyên, dự án, tenant hoặc môi trường được phép | Biến quyền theo tài liệu thành quyền toàn hệ thống |
| Privileged account | Danh tính có khả năng quản trị, truy cập dữ liệu nhạy cảm hoặc thay đổi bảo mật | Đánh giá như tài khoản người dùng thường |
| Time-bound grant | Quyền có `valid_from` và/hoặc `expires_at` | Không kiểm tra giờ hết hạn trên đường xử lý request |
| Review/attestation | Chủ tài nguyên hoặc người được ủy quyền xác nhận tính cần thiết của quyền | “Đã mở báo cáo” bị nhầm thành “đã rà soát/đã thu hồi” |

**Quyền tích lũy khác quyền hiệu lực.** Một người có thể có ba nguồn cấp `REPORT_READ`, nhưng chỉ một nguồn còn hiệu lực với báo cáo thuộc tenant A. Ngược lại, thu hồi một nguồn có thể **chưa** làm mất quyền nếu hai nguồn kia vẫn cho phép. Việc rà soát phải nhìn cả **đường cấp quyền** và **kết quả quyết định cuối cùng**.

Giới hạn của ví dụ: nếu hệ thống có cả `ALLOW` và `DENY`, thứ tự ưu tiên phải được thiết kế rõ. Nhiều ứng dụng dùng mô hình chỉ có allow và “không có allow ⇒ deny”; một số có explicit deny thắng allow; một số xử lý theo policy engine. Không được tự mặc định Spring Security sẽ tự hợp nhất các grant trong database theo một thứ tự ưu tiên mà ứng dụng chưa triển khai.

## 3. Từ quyền gán tới quyền thực sự có hiệu lực

Giả sử có quan hệ:

```text
alice
 ├── direct: REPORT_READ, scope=project-7
 ├── group: project-7-reviewers
 │    └── role: ROLE_ANALYST
 │         ├── REPORT_READ, scope=project-7
 │         └── REPORT_EXPORT, scope=project-7, expires_at=2026-05-01T00:00:00Z
 └── temporary grant: REPORT_EXPORT, scope=project-7, expires_at=2026-04-30T12:00:00Z
```

Vào ngày 2026-05-02 UTC, Alice vẫn có quyền đọc dự án 7 từ ít nhất hai nguồn nhưng **không còn quyền export** từ hai grant thời hạn đã kết thúc. Nếu một role cấp cha khác còn chứa `REPORT_EXPORT` không có hạn, export vẫn có thể được phép: đó là một phát hiện rà soát quyền tích lũy.

Một biểu thức đánh giá khái niệm:

```text
ALLOW(subject, action, resource, now, context)
    = authenticated(subject)
      AND functional_permission(subject, action)
      AND valid_grant_or_policy(subject, action, resource, now, context)
      AND resource_constraints_hold(resource, context)
      AND NOT explicit_deny_if_policy_uses_it
```

Trong đó:

- `functional_permission` là quyền chức năng được ứng dụng chấp nhận, chẳng hạn `REPORT_EXPORT`.
- `valid_grant_or_policy` có thể cần xét vai trò kế thừa, người chủ sở hữu, tenant, nhóm và grant trực tiếp; grant đã bị thu hồi/hết hạn không được tính.
- `resource_constraints_hold` kiểm tra trạng thái resource (đã khóa, đã xóa, chỉ cho xem nội bộ, thuộc tenant...).
- Với role hierarchy, kết quả phụ thuộc cấu hình hierarchy được áp dụng tại **nơi ra quyết định**. Không có lý do để mặc định mọi nơi trong ứng dụng đều sử dụng cùng một hierarchy nếu chưa được cấu hình thống nhất.

**Đặc điểm quan trọng của thời hạn:** quy ước đơn giản và dễ test là `valid_from <= now < expires_at`; đầu mốc **bao gồm**, cuối mốc **không bao gồm**. Nếu `expires_at` là null, hiểu “không có ngày hết hạn tự động” theo policy; vẫn cần review định kỳ. Nên lưu và tính bằng `Instant`/UTC; múi giờ của người duyệt chỉ dùng để hiển thị.

## 4. Bản đồ nguồn quyền: thứ cần thu thập trong một đợt review

Không thể kết luận “Alice hiện có quyền gì” chỉ bằng một bảng user-role. Hãy xây một **inventory có nguồn gốc và phạm vi**:

| Nhóm dữ liệu | Trường cần có | Câu hỏi rà soát |
| --- | --- | --- |
| Danh tính | principal ID ổn định, loại human/service/admin, trạng thái, owner, tenant | Tài khoản còn hoạt động và có người chịu trách nhiệm không? |
| Quyền gán trực tiếp | permission/role, resource/scope, người cấp, lý do, phiếu phê duyệt | Tại sao quyền này tồn tại? |
| Quyền kế thừa | group membership, role hierarchy, group lồng nhau, nguồn IdP/SCIM | Quyền đến theo những đường nào? |
| Quyền có hạn | `valid_from`, `expires_at`, trạng thái phê duyệt, ngoại lệ | Đã hết hạn, sắp hết hạn, hay gia hạn không đúng quy trình? |
| Quyền quản trị | admin scope, khả năng thay đổi IAM/policy, account break-glass | Có standing admin không cần thiết? |
| Tín hiệu sử dụng | last sign-in, last privileged action, last authorized use, môi trường | Quyền có thật sự cần cho công việc hiện tại? |
| Lịch sử quyết định | review date, reviewer, decision, evidence, next review, action ticket | Quyền đã được xác nhận và xử lý tới đâu? |
| Cơ chế thực thi | application role mapping, Spring method checks, cache, sessions, JWT claims | Đổi grant rồi API có từ chối ngay không? |

Nguồn thường nằm ở IdP/SSO, hệ thống HR, group directory, database ACL, cấu hình ứng dụng, token issuer, API gateway, job scheduler và audit log. Khi tổng hợp, giữ khóa ID ổn định, timestamp thống nhất, phiên bản chính sách, provenance và phạm vi tenant. Không đồng nhất “email giống nhau” với “cùng principal” nếu chưa xác nhận cách định danh.

**Không suy ra người ít đăng nhập là luôn có quyền thừa.** Một số tài khoản phục vụ ứng cứu khẩn cấp phải hiếm sử dụng. Với các tài khoản đó, ít hoạt động là dấu hiệu để kiểm tra cơ chế và người chịu trách nhiệm, không phải lý do xóa mù quáng.

## 5. Quy trình review định kỳ và theo sự kiện

Một chu kỳ vận hành có thể triển khai như sau:

1. **Chốt snapshot:** ghi mốc thời gian, nguồn và version policy; lấy đủ trực tiếp + kế thừa + phạm vi + thời hạn. Báo cáo thiếu dữ liệu phải đánh dấu “chưa xác minh”, không mặc định là an toàn.
2. **Tính quyền hiệu lực:** chuẩn hóa principal/action/resource/tenant, mở rộng role graph theo đúng cấu hình và áp dụng thời hạn/trạng thái tại mốc review. Giữ danh sách **mọi đường cấp** quyền để truy nguyên.
3. **Phân nhóm rủi ro:** ưu tiên account quản trị, khả năng thay đổi IAM, export hàng loạt, dữ liệu nhạy cảm, quyền ngoài tenant, grant không hạn, tài khoản rời tổ chức.
4. **Giao reviewer có thẩm quyền:** chủ tài nguyên xác nhận nhu cầu, owner kỹ thuật xác nhận khả năng vận hành, người cấp quyền/kiểm soát IAM xử lý thay đổi. Không để chính người thụ hưởng tự duyệt quyền đặc biệt của mình mà không có kiểm soát độc lập.
5. **Ra quyết định:** giữ nguyên có lý do, giảm scope, đặt expiry, thu hồi, chuyển sang JIT, hoặc cần thêm bằng chứng. Ghi quyết định trên từng grant hoặc nhóm grant có căn cứ; giữ phiếu thay đổi.
6. **Thực hiện thu hồi:** sửa nguồn canonical, đồng bộ IdP/app, xử lý cache, session/token khi cần, và kiểm tra quyền kế thừa còn đường thay thế hay không.
7. **Xác minh bằng hành vi:** một request đáng lẽ bị deny phải thật sự bị deny. Test cả truy cập dữ liệu lẫn ghi/mutation, không chỉ nhìn record `REVOKED` trong bảng.
8. **Đóng vòng review:** lưu người xác nhận, mốc hoàn thành, evidence, exception còn hiệu lực, kế hoạch rà soát lại và số tồn đọng.

Các sự kiện cần kích hoạt review ngoài lịch: nhân sự nghỉ/đổi vai trò; hoàn tất dự án; grant tạm hết hạn; thay đổi role hierarchy; cấp quyền admin; rotation secret; sự cố; nâng cấp policy engine; đổi cách mapping claims từ IdP; phát hiện quyền vượt tenant.

**Thực tế hiệu quả:** khối lượng quyền lớn nên phân tầng tần suất theo mức độ nhạy cảm. Ví dụ quyền admin được xét thường xuyên hơn quyền đọc nội bộ; con số chu kỳ cụ thể phải theo chuẩn nội bộ và yêu cầu pháp lý của tổ chức, không có một tần suất mặc định do Spring Security áp đặt.

## 6. Rà soát tài khoản quản trị và đặc quyền

Đặc quyền là khả năng thực hiện hành động có hậu quả lớn: sửa policy, quản lý user/role, truy cập audit, xem bí mật, cấu hình production, export dữ liệu diện rộng, chạy migration hoặc vô hiệu hóa kiểm soát. Một role có tên “admin” không đủ để định nghĩa rủi ro; phải liệt kê **quyền thực tế**.

### 6.1. Những loại tài khoản cần tách

- **Human admin:** một người dùng danh tính riêng cho công việc quản trị, có trách nhiệm và dấu vết truy cập rõ ràng.
- **Service account:** ứng dụng/job dùng identity kỹ thuật; cần owner, giới hạn API/scope, quản lý credential và thời hạn/rotation.
- **Break-glass account:** dùng khi quy trình đăng nhập/quản trị thường bị gián đoạn; cần mục đích rõ, khả năng khôi phục, kiểm soát truy cập chặt, lưu audit và kiểm tra định kỳ.
- **Delegated admin:** quản trị một tenant, dự án hoặc nhóm cụ thể; không đồng nghĩa global superuser.

Đối với mỗi account, kiểm tra ít nhất: chủ sở hữu, mục đích, môi trường, quyền thực, lần sử dụng có chủ đích gần nhất, cơ chế MFA/step-up nơi áp dụng, đường cấp quyền, thời gian hết hạn, phương án thu hồi, log hoạt động và khả năng phân tách trách nhiệm.

### 6.2. Standing privilege và cấp quyền đúng lúc

`Standing admin` là quyền quản trị có sẵn lâu dài. `Just-in-time (JIT) access` là cấp tạm quyền theo yêu cầu đã phê duyệt, gắn phạm vi/mục đích/thời hạn. JIT giảm thời gian danh tính nắm quyền nhạy cảm nhưng **không tự bảo đảm** an toàn nếu cấp scope quá rộng, không thu hồi sau expiry, không ghi lại hành động, hoặc có một đường role khác luôn cho quyền đó.

Một quy trình JIT hợp lý:

```text
Người yêu cầu → lý do/ticket → đánh giá scope và approver
             → cấp grant có valid_from/expires_at rõ ràng
             → kiểm tra lại ở thời điểm mỗi thao tác nhạy cảm
             → expiry/revoke → invalidate cache/token nếu cần
             → kiểm thử DENY + rà soát audit
```

Break-glass có thể dùng quy trình khác để phục vụ sự cố khi hệ thống duyệt chính bị mất, nhưng việc sử dụng vẫn cần được ghi, cảnh báo, điều tra sau sự cố và kiểm thử khôi phục. Đừng dùng một tài khoản admin dùng chung thường xuyên rồi gọi đó là break-glass.

### 6.3. Separation of duties

Một danh tính có cả quyền `CREATE_PAYMENT` lẫn `APPROVE_PAYMENT` có thể vượt nguyên tắc tách nhiệm vụ, dù mỗi grant riêng lẻ đều do người khác phê duyệt. Review cần kiểm tra **tổ hợp quyền xung đột**, không chỉ kiểm tra từng role. Tương tự, quyền quản lý policy cộng quyền xóa audit là một tổ hợp có rủi ro cao.

Bộ tiêu chí rà soát có thể là: không có tài khoản không owner; không có admin ngoài scope đã phê duyệt; không có grant quản trị không expiry trừ ngoại lệ đã ghi rõ; không có tổ hợp quyền xung đột chưa được xử lý; mọi use của break-glass được ghi nhận và xem xét.

## 7. Hết hạn quyền: trạng thái lưu trữ khác trạng thái hiệu lực

Các trạng thái cần phân biệt:

| Trạng thái bản ghi | Có hiệu lực tại thời điểm yêu cầu? |
| --- | --- |
| `PENDING`, chưa được duyệt | Không |
| `APPROVED`, chưa đến `valid_from` | Không |
| `APPROVED`, đang trong [`valid_from`, `expires_at`) | Có **nếu** scope và các điều kiện khác cũng đúng |
| `APPROVED`, đã đến `expires_at` | Không |
| `REVOKED` dù còn thời hạn | Không |
| `APPROVED`, `expires_at = NULL` | Không tự hết hạn, nhưng vẫn chịu policy, review và revocation |

**Lỗi phổ biến:** chạy job mỗi đêm cập nhật `status = EXPIRED` rồi trong giờ hành chính chỉ kiểm tra `status = APPROVED`. Một grant hết hạn lúc 09:15 có thể tiếp tục dùng tới lần job tiếp theo. Job có ích cho dọn dữ liệu/báo cáo, còn **đường request phải kiểm tra thời gian hiện tại**.

Mọi so sánh thời gian nên dùng `Clock` tiêm vào service hoặc dùng cùng nguồn thời gian tin cậy trong database, và có quy ước rõ khi đồng hồ khác nhau. Với `Instant`, test được mốc `now == expiresAt`, `now` trước 1 nanosecond và sau 1 nanosecond. Với DB có độ chính xác microsecond/millisecond, điều chỉnh dữ liệu test theo mức chính xác thực tế, tránh kỳ vọng nano khi cột DB không giữ nano.

**Token không đồng nghĩa grant:** JWT có `exp` còn hợp lệ không có nghĩa grant ở database chưa hết hạn. Nếu authority được đóng vào JWT, việc thu hồi grant có thể không phản ánh cho đến khi token hết hạn hoặc được refresh, trừ khi API có bước tra trạng thái/quyền động, cơ chế token revocation hoặc policy version phù hợp. Session authentication cũng có thể giữ danh sách `GrantedAuthority` nạp lúc login. Kế hoạch review cần ghi rõ SLA thu hồi và cách xử lý credential còn lưu hành.

## 8. Thiết kế dữ liệu quyền và câu truy vấn kiểm tra active grant

Một mô hình minh họa cho quyền theo tài nguyên:

```sql
CREATE TABLE authorization_grant (
    grant_id        BIGINT PRIMARY KEY,
    principal_id    VARCHAR(100) NOT NULL,
    permission_code VARCHAR(100) NOT NULL,
    tenant_id       VARCHAR(100) NOT NULL,
    resource_id     BIGINT NOT NULL,
    source_kind     VARCHAR(40) NOT NULL,
    source_ref      VARCHAR(100) NOT NULL,
    status          VARCHAR(30) NOT NULL,
    valid_from      TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at      TIMESTAMP WITH TIME ZONE NULL,
    granted_by      VARCHAR(100) NOT NULL,
    approved_by     VARCHAR(100),
    justification   VARCHAR(500),
    reviewed_at     TIMESTAMP WITH TIME ZONE NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL
);
```

Đây là **schema SQL minh họa cho hệ quản trị hỗ trợ `TIMESTAMP WITH TIME ZONE`** (chẳng hạn PostgreSQL), không phải DDL dùng nguyên xi với mọi database. Có thể thêm constraint `expires_at > valid_from` khi expiry khác null; status là tập giá trị hữu hạn; index theo `(principal_id, permission_code, tenant_id, resource_id, status)` và trường thời gian tùy đặc điểm truy vấn. Nên lưu grant append-only hoặc event lịch sử phục vụ audit; cập nhật trạng thái hiện tại không được làm mất bằng chứng ai đã cấp và thu hồi.

Câu truy vấn đánh giá **một grant đã được duyệt, đúng resource, đúng tenant và chưa hết hạn**:

```sql
SELECT EXISTS (
    SELECT 1
      FROM authorization_grant g
     WHERE g.principal_id = :principal_id
       AND g.permission_code = :permission_code
       AND g.tenant_id = :tenant_id
       AND g.resource_id = :resource_id
       AND g.status = 'APPROVED'
       AND g.valid_from <= :now
       AND (g.expires_at IS NULL OR g.expires_at > :now)
) AS allowed;
```

`:principal_id` và `:tenant_id` phải lấy từ identity/context đáng tin; `:resource_id` có thể đến từ request nhưng phải được giới hạn theo tenant và policy thực. Ký hiệu `:name` phù hợp named-parameter API như `NamedParameterJdbcTemplate`; với `JdbcTemplate` thông thường dùng `?`. Không nối giá trị input vào SQL.

**Quan trọng:** truy vấn này chỉ xét grant trực tiếp đã được materialize trong bảng. Nếu source có group, role hierarchy hoặc chính sách theo thuộc tính (ABAC), cần tính quyền đó ở bước phù hợp, bảo đảm một nguồn canonical, xử lý cycle, thời hạn và đối chiếu scope. Không quảng bá câu SQL trên thành thuật toán tổng quát cho mọi mô hình IAM.

Nếu cùng resource có hai grant allow từ hai nguồn, thu hồi một grant không bảo đảm deny; test phải kiểm tra hiệu lực cuối cùng. Nếu có explicit deny, bổ sung phép xét deny theo policy ưu tiên đã định nghĩa, không chỉ `EXISTS(ALLOW)`.

## 9. Java 17 chạy độc lập: nhận diện quyền tích lũy và hết hạn

Mô hình Java thuần dưới đây có đủ identity, permission, scope, nguồn cấp và mốc thời gian. Nó giúp kiểm chứng ba nguyên tắc: (1) quyền chỉ active khi nằm trong khoảng thời gian cho phép, (2) hai nguồn cấp trùng vẫn là hai grant riêng, (3) một grant quản trị JIT hết hạn đúng ở biên `expiresAt`. Đây là mô hình logic, **không thay thế việc kiểm tra Spring Security, database, session hay JWT**.

Tệp `PermissionReviewDemo.java`:

```java
import java.time.Instant;
import java.util.List;

public class PermissionReviewDemo {
    record Grant(
            String principal,
            String source,
            String permission,
            String scope,
            Instant validFrom,
            Instant expiresAt,
            boolean approved) {

        boolean activeAt(Instant now) {
            return approved
                    && !now.isBefore(validFrom)
                    && (expiresAt == null || now.isBefore(expiresAt));
        }

        boolean allows(
                String who, String action, String target, Instant now) {
            return activeAt(now)
                    && principal.equals(who)
                    && permission.equals(action)
                    && scope.equals(target);
        }
    }

    static boolean allowed(
            List<Grant> grants, String who, String action,
            String target, Instant now) {
        return grants.stream()
                .anyMatch(g -> g.allows(who, action, target, now));
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2026-01-01T00:00:00Z");
        Instant reviewAt = Instant.parse("2026-05-01T12:00:00Z");
        List<Grant> grants = List.of(
                new Grant("alice", "direct",
                        "REPORT_READ", "project-7",
                        start, null, true),
                new Grant("alice", "role:analyst",
                        "REPORT_READ", "project-7",
                        start, null, true),
                new Grant("alice", "temporary",
                        "REPORT_EXPORT", "project-7",
                        start,
                        Instant.parse("2026-05-01T00:00:00Z"),
                        true),
                new Grant("ops", "jit:incident-42",
                        "POLICY_EDIT", "production",
                        start, reviewAt, true));

        long readSources = grants.stream()
                .filter(g -> g.allows("alice",
                        "REPORT_READ", "project-7", reviewAt))
                .count();
        long expired = grants.stream()
                .filter(g -> g.expiresAt() != null
                        && !reviewAt.isBefore(g.expiresAt()))
                .count();

        System.out.println("alice.read=" + allowed(
                grants, "alice", "REPORT_READ", "project-7", reviewAt));
        System.out.println("alice.export=" + allowed(
                grants, "alice", "REPORT_EXPORT", "project-7", reviewAt));
        System.out.println("ops.edit=" + allowed(
                grants, "ops", "POLICY_EDIT", "production", reviewAt));
        System.out.println("alice.readSources=" + readSources);
        System.out.println("expiredGrants=" + expired);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac PermissionReviewDemo.java
java PermissionReviewDemo
```

Stdout chính xác:

```text
alice.read=true
alice.export=false
ops.edit=false
alice.readSources=2
expiredGrants=2
```

Tại `reviewAt = 2026-05-01T12:00:00Z`, quyền export đã hết hạn từ 00:00; quyền `POLICY_EDIT` vừa chạm expiry 12:00 nên cũng bị từ chối. Alice còn **hai nguồn** cấp cùng quyền đọc, vì vậy muốn bỏ quyền đọc phải xử lý cả hai nguồn. Hàm `allowed` cố ý xét một danh sách grant đã được đưa về cùng dạng; nó chưa triển khai group recursion, explicit deny, tenant ACL hay policy engine. Nếu hệ thống có các cơ chế ấy, tính “effective” theo policy thật rồi test tương đương.

## 10. Đưa kiểm tra expiry và scope vào Spring Security

Spring Security cung cấp `GrantedAuthority` trong `Authentication`; các authorization manager/method security sẽ dùng authority để kiểm tra quyền. Thực tế, một quyền có điều kiện đối tượng và thời gian thường cần **policy service** lấy thông tin hiện hành từ database hoặc policy engine ngay lúc yêu cầu. Không nên biến hàng nghìn quyền theo từng ID thành hàng nghìn chuỗi `GrantedAuthority` nạp toàn bộ vào session.

### 10.1. Cấu hình method security và đồng hồ

Ví dụ dưới đây dành cho Spring Boot 3.x, Spring Security 6 và ứng dụng servlet dùng JDBC. Các đoạn là thành phần của **một ứng dụng đã có DataSource, authentication và bảng `authorization_grant`**, không phải một tệp Java độc lập. Tài khoản ví dụ dùng `authentication.name` làm `principal_id`; trong production nên map sang principal subject/ID ổn định để tránh lỗi khi đổi username.

Tệp `AuthorizationConfiguration.java`:

```java
package com.example.authorization;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class AuthorizationConfiguration {
    @Bean
    Clock authorizationClock() {
        return Clock.systemUTC();
    }
}
```

`@EnableMethodSecurity` phải được bật để biểu thức `@PreAuthorize` hoạt động. `Clock` cho phép đổi sang `Clock.fixed(...)` trong kiểm thử biên thời gian mà không phải chỉnh đồng hồ hệ thống. Endpoint vẫn phải có HTTP security filter chain phù hợp (authentication, CSRF/bearer policy, v.v.); method security chỉ là một lớp của hệ thống.

### 10.2. Policy service kiểm tra grant sống

Ví dụ nhận `reportId` và tenant của người dùng từ một thành phần đáng tin (`TenantIdentity`). Ở đây đưa vào `tenantId` như một tham số được caller server xác định; không lấy tenant tự khai trong body từ client.

Tệp `ActiveGrantPolicy.java`:

```java
package com.example.authorization;

import java.sql.Timestamp;
import java.time.Clock;
import java.time.Instant;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("activeGrantPolicy")
public class ActiveGrantPolicy {
    private final JdbcTemplate jdbc;
    private final Clock clock;

    public ActiveGrantPolicy(JdbcTemplate jdbc, Clock clock) {
        this.jdbc = jdbc;
        this.clock = clock;
    }

    public boolean canReadReport(
            Authentication actor, long reportId, String trustedTenant) {
        if (actor == null || reportId <= 0
                || trustedTenant == null || trustedTenant.isBlank()) {
            return false;
        }

        Instant now = clock.instant();
        Integer count = jdbc.queryForObject("""
                SELECT COUNT(*)
                  FROM authorization_grant g
                 WHERE g.principal_id = ?
                   AND g.permission_code = 'REPORT_READ'
                   AND g.tenant_id = ?
                   AND g.resource_id = ?
                   AND g.status = 'APPROVED'
                   AND g.valid_from <= ?
                   AND (g.expires_at IS NULL OR g.expires_at > ?)
                """,
                Integer.class, actor.getName(), trustedTenant,
                reportId, Timestamp.from(now), Timestamp.from(now));
        return count != null && count > 0;
    }
}
```

Câu SQL không tin dữ liệu client cho principal/tenant; `trustedTenant` phải được lấy/kiểm tra ở server, không cho client chọn tự do. Với nhiều tenant, cần ràng buộc **cả resource thực** (`reports.tenant_id`) khớp `trustedTenant` ở lần đọc/ghi, tránh người dùng sửa ID xuyên tenant. Bảng `authorization_grant` chỉ là một nguồn minh họa; nếu role/group còn nguồn khác, policy phải đưa chúng vào cùng quyết định.

Để đơn giản, ví dụ tính grant trực tiếp từ database ở mỗi request, phù hợp minh họa độ đúng khi revoke. Ứng dụng lớn có thể cache kết quả nhưng phải xác định cache key chứa actor + tenant + action + resource + policy version/thời gian, TTL đủ nhỏ, và chiến lược invalidation khi revoke/expiry. Với quyền admin nguy cơ cao, có thể buộc kiểm tra quyền động chặt hơn.

### 10.3. Dùng @PreAuthorize tại service và bảo vệ data layer

Một service có thể gọi:

```java
package com.example.authorization;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ActiveGrantPolicy grants;
    private final ReportRepository reports;

    public ReportService(ActiveGrantPolicy grants,
                         ReportRepository reports) {
        this.grants = grants;
        this.reports = reports;
    }

    @PreAuthorize("""
            hasAuthority('REPORT_READ')
            and @activeGrantPolicy.canReadReport(
                authentication, #reportId, #trustedTenant)
            """)
    public ReportView readReport(long reportId, String trustedTenant) {
        return reports.loadForTenant(reportId, trustedTenant);
    }
}
```

Các kiểu `ReportRepository` và `ReportView` là thành phần domain của ứng dụng, **chưa được định nghĩa trong đoạn minh họa**, nên đây là code tích hợp/pseudocode type-level, không tự biên dịch như một chương trình hoàn chỉnh. Với build chưa giữ tên tham số, bật `-parameters` hoặc dùng `@P("reportId")`, `@P("trustedTenant")` để SpEL tra được đúng tham số.

**Hai cửa bắt buộc**: authority `REPORT_READ` ở lớp chức năng và grant còn hiệu lực đúng report/tenant ở policy service. `ReportRepository.loadForTenant` cũng phải query có `WHERE id = ? AND tenant_id = ?`, không load bằng ID rồi hy vọng controller đã kiểm tra. Nếu có mutation, cập nhật có điều kiện tenant/owner/trạng thái, transaction và recheck phù hợp để tránh TOCTOU.

**Không dùng `hasRole('ADMIN')` như đường tắt cho mọi tài nguyên.** Role admin có thể được phép vận hành hệ thống nhưng không nhất thiết được xem dữ liệu ngoài tenant hay vượt ràng buộc phân tách nhiệm vụ. Nếu có ngoại lệ quản trị, biểu diễn nó thành policy rõ ràng, có scope, approval, expiry và audit thay vì một điều kiện OR tùy tiện khắp code.

### 10.4. Role hierarchy và quyền gán gián tiếp

Spring Security hỗ trợ role hierarchy; chẳng hạn `ROLE_ADMIN > ROLE_ANALYST` có thể làm admin thừa hưởng quyền analyst ở những điểm authorization được cấu hình dùng hierarchy. Nhưng **quyền kế thừa không tự kéo theo giới hạn thời gian của grant database**. Nếu scope/expiry quan trọng, phải bảo đảm chính sách còn hạn cũng được kiểm tra tại đường service.

Rà soát cần lấy cấu hình hierarchy, phát hiện cycle/cấu hình bất thường, tính closure các role và ghi **đường nguồn** cho từng permission. Khi bỏ `ROLE_ANALYST` trực tiếp khỏi user, `ROLE_ADMIN` vẫn có thể đem lại cùng quyền. Khi sửa hierarchy, cần test hồi quy các endpoint liên quan vì phạm vi effective permissions thay đổi cùng lúc cho nhiều người.

Lưu ý mặc định: `hasRole("ADMIN")` thường so khớp authority có tiền tố `ROLE_ADMIN`; `hasAuthority("ROLE_ADMIN")` so trực tiếp chuỗi, còn `hasAuthority("REPORT_READ")` không tự thêm prefix. Kiểm tra cấu hình tiền tố/role hierarchy tại runtime thay vì suy ra từ tên bảng quyền.

## 11. Kiểm thử quyền hết hạn, thu hồi và quản trị

Test tốt phải có trạng thái hiện tại lẫn **thời gian** và **nguồn grant**. Chỉ assert một trường `status = REVOKED` sau khi gọi API thu hồi là chưa đủ; cần request thật chứng minh quyền đã biến mất.

### 11.1. Bảng tình huống

| Kịch bản | Kỳ vọng tối thiểu |
| --- | --- |
| Grant approved và trong hạn | Được phép nếu scope, tenant, authority và chính sách khác đều đúng |
| `now = valid_from` | Được phép ở biên bắt đầu |
| `now` ngay trước `expires_at` | Còn hiệu lực tới trước biên kết thúc |
| `now = expires_at` | Bị từ chối |
| `now` sau `expires_at` | Bị từ chối cả trước khi job đánh dấu expired |
| Status `REVOKED` nhưng chưa đến expiry | Bị từ chối ngay theo SLA đã công bố |
| Hai grant cùng permission, thu hồi một | Quyền vẫn có thể còn từ grant thứ hai; báo cáo phải giải thích đường còn lại |
| Bỏ role trực tiếp nhưng còn role cha | Quyền kế thừa vẫn có thể còn; phải xử lý hierarchy |
| Grant admin JIT hết hạn | Hành động admin mới bị từ chối; thao tác đang chạy xử lý theo contract transaction |
| Account bị disable/terminated | Không tạo được session mới và hành vi ở session/token cũ tuân thủ SLA thu hồi |
| Token JWT còn hạn nhưng grant đã revoke | Quyền nhạy cảm phải từ chối theo cơ chế refresh/recheck/revocation đã chọn |
| Chuyển tenant/đổi owner | Không truy cập được dữ liệu tenant cũ ngoài scope |
| Policy cache stale | Hết hạn/invalidation thật sự có hiệu lực, không cho phép quá TTL đã duyệt |
| Service account không owner hoặc credential quá hạn | Được đánh dấu và xử lý không bỏ sót |
| Lỗi database/policy service | Deny/fail closed cho đường nhạy cảm, audit lý do hạ tầng phù hợp |

Chủ động kiểm tra quyền **tại thời điểm truy cập**. Với quy trình dài (batch hoặc async), cần quyết định liệu quyền được chốt lúc nhận request, lúc thực thi hay cả hai. Đối với thao tác rủi ro cao, việc thu hồi trong lúc job đang chờ phải có tác động rõ ràng và được test.

### 11.2. Dùng Clock cố định để test biên

Ví dụ JUnit 5 cho logic Java thuần, khi tạo dữ liệu theo bài demo:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class GrantExpiryTest {
    @Test
    void expiryIsExclusive() {
        Instant from = Instant.parse("2026-01-01T00:00:00Z");
        Instant until = Instant.parse("2026-05-01T12:00:00Z");
        PermissionReviewDemo.Grant grant =
                new PermissionReviewDemo.Grant(
                        "ops", "jit:incident-42",
                        "POLICY_EDIT", "production",
                        from, until, true);
        assertTrue(grant.activeAt(until.minusNanos(1)));
        assertFalse(grant.activeAt(until));
        assertFalse(grant.activeAt(until.plusNanos(1)));
    }
}
```

Đoạn này cần JUnit 5 trên test classpath và tệp `PermissionReviewDemo.java` cùng package (hoặc default package như bài chạy độc lập). `Instant` giữ độ chính xác nanosecond trong bộ nhớ; khi test tích hợp database, dùng độ chính xác mà cột và driver hỗ trợ. Với Spring, tiêm một bean `Clock.fixed(..., ZoneOffset.UTC)` cho test hoặc một `Clock` có thể thay đổi; tránh `Thread.sleep` để chờ expiry vì test dễ không ổn định.

### 11.3. Kiểm chứng qua Spring Security/HTTP

Các test tích hợp cần bật SecurityFilterChain và `@EnableMethodSecurity`, seed grant vào database test, gọi đúng endpoint với principal/authorities, rồi kiểm tra:

- Request approved, đúng scope, trong hạn ⇒ thành công và dữ liệu đúng tenant.
- Request cùng credential sau khi `status` chuyển `REVOKED` ⇒ bị từ chối; token hoặc session được xử lý theo thiết kế.
- Giữ nguyên `status='APPROVED'` nhưng đặt `expires_at` trong quá khứ ⇒ bị từ chối **mà không cần chạy job dọn grant**.
- Với tài khoản không có `REPORT_READ` nhưng grant DB còn, quyền chức năng phải chặn. Với account có `REPORT_READ` nhưng grant sai resource/tenant, policy object phải chặn.
- Nếu cập nhật quyền admin, assert trạng thái thay đổi không tạo side effect trái phép; kiểm tra audit đã ghi actor, action, resource, policy version, decision (không ghi secret/token).

Trong Spring MVC, `MockMvc` có thể dùng `@WithMockUser` hoặc `SecurityMockMvcRequestPostProcessors.user(...)` để đưa authority vào request. `@WithMockUser` tự nó không xác minh toàn bộ SSO/token issuance; nếu cần kiểm tra claims/refresh/revocation, viết thêm test tại authentication chain hoặc end-to-end dùng credential/token thật của môi trường test.

## 12. Chỉ số vận hành và bằng chứng review

Các chỉ số giúp đánh giá mức độ hoàn thành, nhưng không thay bằng chứng truy cập thực:

| Chỉ số | Cách tính/diễn giải |
| --- | --- |
| Grant đã quá hạn mà còn trạng thái active | Số bản ghi trong source chưa được dọn; lỗi nghiêm trọng hơn nếu API vẫn allow |
| Privileged accounts không owner | Số danh tính đặc quyền không có người chịu trách nhiệm |
| Standing admin | Số danh tính có admin dài hạn, phân theo môi trường/scope |
| Grant nhiều nguồn | Số cặp (principal, permission, scope) có từ hai đường active trở lên |
| Review overdue | Grant cần review nhưng quá ngày, phân loại high-risk trước |
| Revocation propagation lag | Thời gian từ quyết định thu hồi đến khi request thực sự bị deny |
| Token/cache exposure window | Thời gian quyền có thể còn tồn tại trong credential/cache sau revoke |
| Privileged action coverage | Tỷ lệ thao tác nhạy cảm có audit actor/action/target/time/decision đầy đủ |
| Exception inventory | Số ngoại lệ đang còn hiệu lực, reason/approver/expiry rõ ràng |

Ví dụ, nếu có 20 grant admin phải review và 16 grant đã được người có thẩm quyền xác nhận đúng hạn thì tỷ lệ hoàn thành là `16/20 = 80%`. Chỉ số này **không nói gì** về việc 4 grant còn lại có an toàn hay không; cần xem mức rủi ro và bằng chứng của chúng. Tránh dùng “không có lần dùng” làm bằng chứng quyền chắc chắn không cần thiết.

Một bản ghi audit cho quyết định review có thể chứa:

```json
{
  "reviewId": "RV-2026-0412",
  "principalId": "principal-123",
  "permission": "REPORT_EXPORT",
  "scope": "project-7",
  "grantSources": ["role:analyst", "temporary:ticket-42"],
  "evaluatedAt": "2026-05-02T09:00:00Z",
  "decision": "REVOKE",
  "reviewerId": "reviewer-55",
  "reason": "Project completed",
  "actionTicket": "IAM-482",
  "verification": "DENIED_ON_API"
}
```

Đây là **mẫu dữ liệu minh họa**, không phải định dạng chuẩn của Spring Security. Tách audit record khỏi access token, mật khẩu và dữ liệu nhạy cảm. Lưu đủ thông tin để truy ra nguồn grant và quyết định đã thực thi nhưng không ghi secret, refresh token hoặc toàn bộ hồ sơ cá nhân.

## 13. Thu hồi an toàn và xử lý rủi ro của phiên cũ

Quy trình revoke nên xét đủ bốn lớp:

1. **Source of truth:** IdP, user-group mapping, ACL hoặc database grant được thay đổi đúng nguồn. Một bản copy được sửa không bảo đảm các bản còn lại đồng bộ.
2. **Policy calculation:** role hierarchy/ABAC được tính lại; mất một grant nhưng còn grant khác có thể vẫn allow.
3. **Credentials và cache:** session, cached `Authentication`, JWT claims, token issuer, API gateway, distributed cache hoặc DataLoader có thể giữ thông tin cũ. Chọn invalidation, short-lived token, policy-version check hoặc lookup động theo SLA.
4. **Execution/evidence:** gọi endpoint hoặc chạy job với danh tính bị thu hồi; xác minh deny, dữ liệu không bị ghi và audit có bản ghi cần thiết.

Nếu cần thu hồi tức thời quyền phá hủy hoặc thay đổi chính sách, chỉ giảm TTL cache từ vài giờ xuống vài phút có thể chưa đáp ứng SLA. Dùng kiểm tra grant hiện hành hoặc version/revocation list ngay tại điểm hành động, cân nhắc đặc tính khả dụng khi hệ thống chính sách bị mất. Với hệ thống deny khi policy service lỗi (*fail closed*), phải có giám sát và quy trình khắc phục sự cố để tránh mở lại quyền bằng đường bypass.

Khi revoke một account quản trị, rà soát cả key, credential, session, API token, quyền IAM/cloud và automation chạy dưới danh tính đó. Nếu chuyển owner service account, cần gắn owner mới và kiểm chứng job còn hoạt động; không tự ý xóa account production không có phương án chuyển giao.

## 14. Các lỗi phổ biến cần nhận diện

- **Chỉ liệt kê role trực tiếp:** bỏ qua group, role cha, tenant/ACL và grant tạm; giải pháp là tính effective permissions có provenance.
- **Dùng danh sách authority trong login session làm sự thật vĩnh viễn:** authority có thể stale sau revoke; bổ sung refresh/recheck theo SLA.
- **Chạy cron dọn grant thay cho kiểm tra expiry tại request:** quyền hết hạn giữa hai lần job vẫn truy cập được; kiểm tra `now < expires_at` tại authorization.
- **Gia hạn quyền bằng cách đặt `expires_at = null` cho tiện:** tạo standing privilege không có ngày kết thúc; cần approval và chu kỳ review.
- **Thu hồi một grant nhưng bỏ sót grant khác:** cùng quyền còn đến từ role/direct/group; test lại quyết định cuối cùng.
- **Đặt ADMIN làm bypass toàn bộ domain policy:** admin xuyên tenant hoặc xem dữ liệu nhạy cảm trái nhu cầu; tách privileged action khỏi object/field access.
- **Tài khoản quản trị dùng chung:** audit không xác định cá nhân chịu trách nhiệm; dùng danh tính riêng, truy cập có kiểm soát, quy trình ứng cứu riêng.
- **Đồng nhất token expiry với grant expiry:** token còn hạn có thể chứa quyền đã bị thu hồi; cần cơ chế cập nhật/revoke có thể kiểm chứng.
- **So sánh ngày theo giờ local và bỏ qua timezone:** cấp quyền quá hạn sớm/muộn ở DST hoặc môi trường khác; lưu `Instant` và test mốc biên.
- **Review chỉ mang tính thủ tục:** reviewer xác nhận nhưng quyền không đổi hoặc request vẫn allow; bắt buộc evidence thực thi và kiểm tra sau đổi.
- **Deny chỉ trong UI:** nút quản trị bị ẩn nhưng API vẫn thao tác được; mọi enforcement phải ở backend/security layer.
- **Policy cache không phân biệt tenant hoặc user:** quyền của người này bị tái sử dụng cho người khác; khóa cache đầy đủ và invalidation thích hợp.
- **Xóa audit để giảm dung lượng:** không truy ra ai đã cấp/duyệt/sử dụng quyền; áp dụng retention, kiểm soát truy cập và tối giản dữ liệu một cách có chủ đích.

## 15. Bài tập vận hành và tiêu chí nghiệm thu

### Bài tập A — Truy vết quyền tích lũy

Với Alice có `REPORT_READ` từ grant trực tiếp và `ROLE_ANALYST`, hãy trả lời: (1) hiện có bao nhiêu **nguồn** cấp quyền đọc, (2) nếu thu hồi grant trực tiếp thì API còn cho phép không, (3) cần sửa nguồn nào để quyền đọc hoàn toàn biến mất, (4) có bị ảnh hưởng bởi role hierarchy hay không. Kết quả phải ghi đường nguồn, scope và thời điểm đánh giá, không chỉ cột `allowed=true/false`.

### Bài tập B — Quyền admin đúng hạn

Cấp `POLICY_EDIT` cho `ops` từ 08:00 tới 12:00 UTC ngày 01/05/2026. Kiểm thử 11:59:59 được phép, đúng 12:00 bị từ chối. Xác minh việc từ chối không phụ thuộc cron. Ghi evidence grant ID, người duyệt, ticket và một request bị deny sau expiry.

### Bài tập C — Thu hồi sau thay đổi công việc

Một account rời dự án vẫn có `REPORT_EXPORT` qua group. Hãy mô phỏng bỏ group rồi gọi API export: kết quả phải deny. Nếu token/session cũ còn quyền, nêu cách cập nhật và SLA cần đạt. Với account service, xác minh job liên quan sau khi giảm scope và cập nhật owner.

### Bài tập D — Review account quản trị

Tạo một danh sách gồm human admin, service account và break-glass. Với từng account, xác định owner, quyền nhạy cảm, last privileged use, thời hạn, điểm kiểm soát MFA/approval, logging, đường khôi phục và cách thu hồi. Ghi quyết định: giữ, giảm, JIT, revoke hoặc ngoại lệ có hạn.

**Tiêu chí hoàn thành:** báo cáo mô tả được quyền **hiệu lực** và mọi nguồn cấp; không bỏ qua role hierarchy/scope; tài khoản admin có owner, lý do và kiểm soát; grant hết hạn bị deny ngay ở đường API; revoke được xác minh qua request; thời gian đo bằng UTC và kiểm thử các biên; nhật ký review truy nguyên được ai quyết định và kết quả đã thực thi.

## Tài liệu tham khảo

- Spring Security — Authorization Architecture (`GrantedAuthority`, role hierarchy, `AuthorizationManager`): https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Method Security (`@EnableMethodSecurity`, `@PreAuthorize`): https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
