# Đồng bộ quyền từ nguồn danh tính mà vẫn giữ quyền nghiệp vụ nhất quán

## 1. Bài toán: nguồn danh tính thay đổi, quyền nghiệp vụ vẫn phải đúng

Trong nhiều ứng dụng Spring Security, người dùng đăng nhập qua một **nguồn danh tính tập trung** (Identity Provider, IdP) như hệ thống SSO/OIDC của tổ chức. IdP có thể quản lý tài khoản còn hoạt động hay đã bị khóa, danh sách nhóm tổ chức, phòng ban và một số thuộc tính nhân sự. Trong khi đó, ứng dụng tự quản lý quyền nghiệp vụ: ai được phê duyệt hóa đơn, xem báo cáo của tenant nào, khóa đơn hàng, xuất dữ liệu hoặc phê duyệt một hạn mức cụ thể.

Vấn đề phát sinh khi một trong hai nguồn thay đổi:

- Nhân viên chuyển phòng ban, IdP bỏ nhóm **finance**; ứng dụng vẫn còn bản ghi cũ cho phép phê duyệt.
- Tài khoản bị vô hiệu hóa trên IdP, nhưng token JWT hoặc cache quyền cũ vẫn còn hiệu lực.
- Hệ thống đồng bộ nhóm từ IdP bằng cách ghi đè toàn bộ vai trò trong cơ sở dữ liệu ứng dụng, làm mất quyền nghiệp vụ do quản trị viên từng cấp có chủ đích.
- Một sự kiện thu hồi quyền đến trước, sự kiện cũ đến muộn lại ghi đè trạng thái mới và **khôi phục quyền không đúng**.
- Người dùng thuộc tenant A được đồng bộ nhầm sang tenant B vì ghép danh tính bằng email hoặc tên đăng nhập không ổn định.

Mục tiêu không phải “chép mọi role từ IdP sang ứng dụng”. Mục tiêu là **xác định dữ liệu nào do hệ thống nào có thẩm quyền**, tiếp nhận thay đổi đúng thứ tự, và tính quyền **hiệu lực** của mỗi yêu cầu từ các điều kiện hiện hành.

Sau bài học, bạn có thể thiết kế ranh giới IdP–ứng dụng, xử lý đồng bộ có tính lặp lại an toàn (idempotency), sự kiện sai thứ tự, vô hiệu hóa tài khoản, đối soát định kỳ, cache/token cũ và kiểm thử Spring Security mà không đánh mất quyền do nghiệp vụ quản lý.

## 2. Mô hình nhất quán: hai nguồn thẩm quyền, một quyết định cuối

Hãy xét nghiệp vụ phê duyệt hóa đơn. Một nhân viên chỉ được duyệt khi:

1. Danh tính đã được xác thực từ đúng issuer và subject.
2. Trạng thái tài khoản theo IdP đang **active** và dữ liệu trạng thái đủ mới theo chính sách.
3. Người dùng đang thuộc nhóm tổ chức **finance** theo quy tắc ánh xạ đã duyệt.
4. Ứng dụng vẫn có **quyền nghiệp vụ invoice:approve** do người có thẩm quyền trong ứng dụng cấp.
5. Người dùng thuộc đúng tenant của hóa đơn.
6. Hóa đơn ở trạng thái phù hợp (ví dụ PENDING), hạn mức và các điều kiện nghiệp vụ được thỏa.
7. Nếu tài khoản từng bị vô hiệu hóa hoặc nhóm quyền nhạy cảm từng bị thu hồi, có bước **duyệt lại quyền cũ** trước khi khôi phục hoạt động.

Có thể biểu diễn quyết định:

~~~text
allowed =
    authenticated_identity_is_valid
 AND idp_account_is_active
 AND idp_group_gate_is_satisfied
 AND local_business_grant_is_active
 AND tenant_and_resource_scope_match
 AND business_preconditions_are_satisfied
 AND no_reapproval_or_security_hold_is_pending
~~~

Các phép AND là minh họa cho **một quyền nhạy cảm**. Với các chức năng khác, chính sách có thể khác; chẳng hạn quyền xem công khai không cần local grant. Nhưng mỗi quyền phải có công thức rõ ràng và mặc định **từ chối khi thiếu điều kiện bắt buộc**.

### 2.1. Phân định ai sở hữu dữ liệu nào

| Dữ liệu | Nguồn thẩm quyền đề xuất | Cách sử dụng |
| --- | --- | --- |
| Issuer, subject, trạng thái tài khoản | IdP / hệ thống vòng đời danh tính | Liên kết người dùng và chặn tài khoản bị vô hiệu |
| Nhóm tổ chức, phòng ban, quan hệ nhân sự | IdP nếu tổ chức giao quyền quản lý | Điều kiện đủ hoặc điều kiện cần cho một số nhóm quyền |
| Danh tính ứng dụng/tenant membership | Hệ thống theo hợp đồng dữ liệu | Quy định người dùng thuộc những tenant nào |
| Quyền invoice:approve, report:export, ACL, hạn mức | Hệ thống nghiệp vụ | Quyết định thao tác trên dữ liệu và hạn mức |
| Chủ sở hữu hóa đơn, trạng thái PENDING, tenant của hóa đơn | Cơ sở dữ liệu nghiệp vụ | Ràng buộc ở đúng tài nguyên |
| Mã hóa quyền từ IdP group sang capability | Cấu hình được review/kiểm thử | Bảng ánh xạ có phiên bản, không tự suy luận tên nhóm |
| Audit ai cấp/sửa/thu hồi local grant | Hệ thống nghiệp vụ | Điều tra và chứng minh nguồn gốc quyết định quyền |

**Nguyên tắc sở hữu:** Sự kiện IdP có thể cập nhật trạng thái tài khoản, nhóm tổ chức và những thuộc tính do IdP làm chủ; nó **không được ghi đè tùy tiện** quyền invoice:approve do ứng dụng làm chủ. Ngược lại, một local grant không được phép biến tài khoản đã bị IdP vô hiệu hóa thành tài khoản có quyền.

Nếu một quyền thực sự **do IdP làm chủ** theo hợp đồng (ví dụ group chính là nguồn duy nhất cho quyền đọc intranet), có thể đồng bộ quyền ấy trực tiếp. Điều quan trọng là phân biệt rõ quyền **IdP-owned** và **business-owned**, tránh hai bên cùng ghi một cột roles rồi liên tục ghi đè nhau.

### 2.2. Identity group không đồng nghĩa business permission

Group **finance** có thể chỉ cho biết người dùng thuộc bộ phận tài chính. Nó không nhất thiết cho phép phê duyệt **mọi** hóa đơn hoặc mọi tenant. Bảng ánh xạ có thể định nghĩa:

| IdP group | Tác dụng ở ứng dụng | Quyền cần thêm |
| --- | --- | --- |
| employees | Có thể sử dụng các chức năng nhân viên cơ bản | report:read khi chức năng yêu cầu |
| finance | Đủ điều kiện được xem xét cấp quyền hóa đơn | local grant invoice:approve + hạn mức |
| finance-auditors | Đủ điều kiện đọc log tài chính | audit:read + scope phù hợp |
| suspended | Khóa quyền nhạy cảm nếu chính sách sử dụng group này | Không cho local grant vượt qua trạng thái khóa |

Không tự động coi một group có tên **admin** từ claim chưa kiểm chứng là ROLE_ADMIN của ứng dụng. Bảng ánh xạ phải dùng **allowlist**, tên chuẩn hóa, issuer được tin cậy và test các tình huống group lạ, group bị xóa, trùng tên và khác tenant.

## 3. Nhận dạng người dùng bền vững: issuer + subject + tenant

Trong OIDC/JWT, claim **sub** là định danh chủ thể do issuer cấp; cùng một sub ở hai issuer khác nhau không chắc là cùng người dùng. Vì vậy khóa liên kết danh tính nên xét ít nhất **(issuer, sub)**; còn quyền theo tenant phải gắn với một tenant rõ ràng được xác minh từ dữ liệu ứng dụng.

~~~text
IdP A: iss=https://idp-a.example/realms/main, sub=abc123
IdP B: iss=https://idp-b.example/realms/main, sub=abc123
         │                                      │
         └── hai danh tính khác nhau ───────────┘

Local business grant:
(issuer, subject, tenant, capability, scope, status, approvedBy, version)
~~~

**Email không nên là khóa chính** để cấp/thu hồi quyền: email có thể đổi, được tái sử dụng hoặc trùng ở các nguồn chưa chuẩn hóa. Username và display name cũng có thể thay đổi. Nếu ứng dụng phải liên kết tài khoản từ nhiều IdP, cần quy trình **account linking được xác minh**, không tự nối chỉ vì hai email giống nhau.

**Tenant không được lấy tin tưởng trực tiếp từ request** như một bằng chứng quyền. Khi phê duyệt hóa đơn, backend tra hóa đơn để biết tenant thực, sau đó kiểm tra người dùng có quyền trong tenant ấy. Nếu hệ thống dùng tenant context từ token hoặc header, vẫn phải kiểm tra quan hệ thành viên và ranh giới nguồn phát hành.

Với cùng một nhân viên có hai tenant, local grant ở tenant A **không tự áp dụng** cho tenant B; cache key và unique constraint phải bao gồm mọi chiều liên quan, tránh rò rỉ quyền chéo tenant.

## 4. Các con đường đồng bộ và vai trò của chúng

~~~text
                    Identity Provider
          ┌────────────┼───────────────┐
          │            │               │
      SCIM / API    Webhook/event     JWT/OIDC login
          │            │               │
          └───────► Ingestion         Xác thực request
                     │                  │
           Xác minh nguồn/sơ đồ         │
                     │                  │
           Inbox + kiểm tra phiên bản    │
                     │                  │
         Cập nhật projection IdP         │
                     │                  │
          Outbox invalidate cache        │
                     │                  │
               Policy Service ◄─────────┘
                     │
             Business grants + ACL
                     │
              Allow / Deny
                     │
           Audit + metrics + trace
~~~

**SCIM 2.0** (RFC 7644) là giao thức provisioning cho Users/Groups, có thao tác POST/GET/PUT/PATCH/DELETE và hỗ trợ versioning qua ETag/meta.version. SCIM không tự biến dữ liệu nhận được thành quyền nghiệp vụ chính xác; ứng dụng vẫn phải ánh xạ nguồn thẩm quyền và hợp nhất đúng. ETag thường là **giá trị opaque dùng cho kiểm soát đồng thời**, không được giả định là số nguyên tăng dần để so sánh lớn/nhỏ.

**Webhook/event** cho phép thay đổi lan truyền nhanh nhưng có thể trùng, sai thứ tự hoặc tạm thời không đến. Muốn so thứ tự cần **revision/sequence tăng đơn điệu theo đúng thực thể** hoặc cơ chế so sánh phiên bản được nguồn bảo đảm; timestamp đơn thuần dễ sai vì đồng hồ và retry.

**Đồng bộ khi đăng nhập** có thể cập nhật nhóm từ claims đã được xác thực nhưng không đảm bảo các thay đổi đến ngay khi người dùng vẫn giữ phiên cũ. Không nên coi “đợi người dùng đăng nhập lại” là biện pháp thu hồi quyền đủ mạnh cho thao tác rủi ro cao.

**Đối soát định kỳ (reconciliation)** đọc trạng thái danh tính hiện hành, so sánh với projection đã lưu và sửa thiếu/sai; nó bù cho sự kiện bị mất. Nhưng việc IdP trả lỗi, dữ liệu phân trang chưa đầy đủ hoặc snapshot tạm thời thiếu **không phải lệnh xóa toàn bộ tài khoản vắng mặt**.

## 5. Quy trình tiếp nhận một thay đổi danh tính

### 5.1. Hợp đồng sự kiện

Một sự kiện lý tưởng chứa:

~~~json
{
  "eventId": "evt-000245",
  "source": "trusted-directory",
  "issuer": "https://idp.example/realms/main",
  "subject": "user-123",
  "revision": 245,
  "type": "IDENTITY_SNAPSHOT",
  "active": true,
  "groups": ["finance", "employees"]
}
~~~

Đây là **một ví dụ hợp đồng nội bộ**, không phải payload SCIM chuẩn. Trường revision chỉ nên dùng để so sánh khi adapter đã xác minh nó thực sự tăng **trong cùng phạm vi issuer + subject**. Nếu nhà cung cấp không bảo đảm thứ tự, có thể dùng queue partition theo subject, kiểm tra ETag với API, hoặc tải trạng thái mới nhất rồi đối soát, thay vì tự suy đoán theo thời gian nhận.

Sự kiện dạng **snapshot đầy đủ** phải có semantics rõ về các trường bắt buộc. Với **partial update/PATCH**, một trường groups *vắng mặt* có nghĩa là **không cập nhật trường ấy**, không phải “xóa tất cả nhóm”. Một lệnh remove groups được xác thực mới mang nghĩa thu hồi. Nhầm hai trường hợp này sẽ làm mất quyền hàng loạt.

### 5.2. Xử lý theo từng bước

1. **Xác minh nguồn:** kênh HTTPS/mTLS hoặc chữ ký webhook, issuer được phép, token máy gọi, giới hạn schema và chống replay. Không chấp nhận JSON do khách hàng thường gửi như sự kiện IdP.
2. **Chuẩn hóa khóa:** xác định issuer + sub và tenant mapping dựa trên quy tắc đã xác minh; không nối bằng email.
3. **Ghi inbox/eventId:** nhận diện sự kiện trùng, trạng thái xử lý và liên kết audit.
4. **Kiểm tra thứ tự:** bỏ qua bản ghi đã cũ khi có revision có thứ tự xác định; không cho sự kiện cũ ghi đè trạng thái mới.
5. **Cập nhật projection của IdP:** active, groups, phiên bản đã áp dụng; chỉ trong các trường IdP làm chủ.
6. **Áp điều kiện thu hồi:** khi active=false hoặc nhóm điều kiện rủi ro cao bị loại bỏ, quyết định quyền hiệu lực phải chuyển sang deny. Có thể đánh dấu **local grants cần review** trước khi kích hoạt lại.
7. **Commit giao dịch** và tạo outbox event để xóa cache hoặc phát thông báo đến các node. Chỉ ACK sự kiện sau khi lưu bền vững.
8. **Đối soát** theo lịch để chữa missed event, ghi nhận drift và các trường hợp bất thường.

Nếu DB lưu trạng thái IdP và event inbox ở hai nơi riêng, không được ACK trước khi cập nhật thành công rồi quên retry. Dùng giao dịch, unique constraint và transactional outbox phù hợp để làm chặt đường xử lý. Cache invalidation thường là tác vụ bất đồng bộ: phải đặt **mức trễ thu hồi chấp nhận được** theo độ nhạy quyền.

### 5.3. Chống sự kiện sai thứ tự và cập nhật trùng

Giả sử:

~~~text
revision 10: active=true,  groups=[finance]
revision 11: active=false, groups=[]
revision 9 : active=true,  groups=[finance]   ← đến muộn
revision 11: active=false, groups=[]          ← phát lại
~~~

Đúng: sau revision 11 tài khoản **vẫn bị khóa**; revision 9 và bản phát lại của 11 không được mở quyền. Không được dùng “last write wins theo thời gian nhận” vì sự kiện 9 đến muộn có thể ghi đè trạng thái mới nhất. Nếu hai nguồn khác nhau cập nhật cùng một phần dữ liệu mà không có một thứ tự chung, phải xác định **nguồn nào làm chủ** hoặc chặn và chuyển vào hàng xử lý xung đột, không chọn đại dữ liệu đến sau.

Tương tự, local grant có phiên bản/quy trình cấp quyền riêng. Sự kiện IdP đến mới **không mặc định sửa businessGrant.version**. Đây chính là cách tránh “sự kiện nhóm mới làm mất quyền nghiệp vụ do ứng dụng cấp”.

### 5.4. Xóa và vô hiệu hóa

Một sự kiện xóa tài khoản cần được thể hiện thành **trạng thái vô hiệu/tombstone có phiên bản**, tránh xóa hẳn bản ghi rồi cho một event cũ “tạo lại”. Có thể lưu audit và local grant theo chính sách lưu trữ dữ liệu, nhưng **effective access phải bị khóa**. Nếu IdP cấp lại tài khoản mới với subject mới, đó là danh tính khác; không tự nối grants của người cũ bằng email.

Khi tài khoản cũ hoạt động lại, hệ thống có thể cần **phê duyệt lại** các quyền nhạy cảm đã được cấp trước đây. Chính sách này phải được quyết định cùng bộ phận nghiệp vụ và an ninh, vì việc IdP kích hoạt lại tài khoản không có nghĩa tất cả hạn mức/ủy quyền cũ tự nhiên còn phù hợp.

## 6. Mô hình dữ liệu gợi ý cho hệ thống thật

Có thể tách tối thiểu ba bảng/khối:

~~~sql
-- Mã SQL minh họa cấu trúc logic; cần điều chỉnh kiểu dữ liệu theo DB.
CREATE TABLE identity_projection (
    issuer        VARCHAR(512) NOT NULL,
    subject_id    VARCHAR(255) NOT NULL,
    active        BOOLEAN NOT NULL,
    group_data    TEXT NOT NULL,
    source_version VARCHAR(255) NOT NULL,
    observed_at   TIMESTAMP NOT NULL,
    PRIMARY KEY (issuer, subject_id)
);

CREATE TABLE business_grant (
    grant_id      BIGINT PRIMARY KEY,
    issuer        VARCHAR(512) NOT NULL,
    subject_id    VARCHAR(255) NOT NULL,
    tenant_id     VARCHAR(100) NOT NULL,
    capability    VARCHAR(150) NOT NULL,
    grant_status  VARCHAR(30) NOT NULL,
    grant_version BIGINT NOT NULL,
    approved_by   VARCHAR(255) NOT NULL
);

CREATE TABLE identity_event_inbox (
    source_name VARCHAR(150) NOT NULL,
    event_id    VARCHAR(255) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (source_name, event_id)
);
~~~

**Đây không phải DDL production hoàn chỉnh:** còn cần các khóa ngoại hoặc identity mapping, index theo tenant/capability, unique constraint chống grant trùng, audit thời điểm cấp/thu hồi, dữ liệu phiên bản có loại phù hợp với IdP, chính sách xử lý xóa và mã hóa các trường nhạy cảm. Cột source_version có dạng String vì ETag có thể opaque; không dùng so sánh số nguyên trên giá trị opaque. Nếu nguồn có số revision thật sự tăng đơn điệu, có thể lưu kiểu BIGINT và điều kiện cập nhật phiên bản.

**Ownership tách biệt trong DB:** event handler chỉ ghi identity_projection và trạng thái cần review; API quản trị nghiệp vụ chỉ ghi business_grant; policy engine **đọc cả hai** để ra quyết định cuối. Việc cần review có thể nằm trong bảng business_grant hoặc bảng trạng thái bảo mật riêng với audit, nhưng không được bỏ qua khi re-enable.

**Audit:** ghi ai/cái gì/nguồn nào thay đổi, eventId/revision, tenant, quyết định allow/deny và correlation id; tránh ghi raw token, mật khẩu hoặc thông tin cá nhân không cần thiết vào log. Metric tags dùng các nhóm hữu hạn như eventType/result, không dùng email/sub/id làm nhãn vì cardinality cao.

## 7. Ví dụ Java 17 tự chạy: nhóm IdP là điều kiện cần, quyền nghiệp vụ là quyết định riêng

Fixture sau mô phỏng một nguồn cung cấp **snapshot đầy đủ** với revision **đã được bảo đảm tăng dần** cho mỗi khóa. Đây là ví dụ học tập trong **một luồng**, dùng Map và Set trong bộ nhớ. Nó chứng minh các nguyên tắc, không phải engine production có transaction, persistence hay thread safety.

Chính sách: để duyệt hóa đơn, người dùng phải đang active, thuộc nhóm finance, có local grant invoice:approve, đúng tenant, hóa đơn còn PENDING và không có yêu cầu phê duyệt lại. **Không một sự kiện IdP nào tự tạo local grant**.

### 7.1. Tệp Java hoàn chỉnh

Tạo tệp **IdentityPermissionSyncDemo.java**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class IdentityPermissionSyncDemo {

    public record Key(String issuer, String subject, String tenant) {
        public Key {
            Objects.requireNonNull(issuer, "issuer");
            Objects.requireNonNull(subject, "subject");
            Objects.requireNonNull(tenant, "tenant");
        }
    }

    // Snapshot đã được xác thực; revision tăng trong cùng một Key.
    public record DirectoryEvent(
            Key key, long revision, boolean active, Set<String> groups) {
        public DirectoryEvent {
            Objects.requireNonNull(key, "key");
            groups = Set.copyOf(groups);
        }
    }

    public record DirectoryState(
            long revision, boolean active, Set<String> groups) {}

    public record Invoice(String tenant, boolean pending) {}

    public static final class Engine {
        private final Map<Key, DirectoryState> directory = new HashMap<>();
        private final Map<Key, Set<String>> localGrants = new HashMap<>();
        private final Set<Key> reviewRequired = new HashSet<>();

        // Chỉ cập nhật projection của IdP và trạng thái rà soát.
        public void apply(DirectoryEvent event) {
            DirectoryState previous = directory.get(event.key());
            if (previous != null
                    && event.revision() <= previous.revision()) {
                return; // Bỏ bản cũ và bản phát lại.
            }

            boolean lostFinanceGroup = previous != null
                    && previous.groups().contains("finance")
                    && !event.groups().contains("finance");

            if (!event.active() || lostFinanceGroup) {
                reviewRequired.add(event.key());
            }

            directory.put(event.key(), new DirectoryState(
                    event.revision(), event.active(), event.groups()));
        }

        // Chỉ một quy trình/quản trị viên nghiệp vụ được phép gọi hàm này.
        public void grantLocally(Key key, String capability) {
            localGrants.computeIfAbsent(key, ignored -> new HashSet<>())
                    .add(capability);
        }

        // Giả lập bước người có thẩm quyền xét lại quyền cũ.
        public void approveReview(Key key) {
            DirectoryState current = directory.get(key);
            if (current == null || !current.active()
                    || !current.groups().contains("finance")) {
                throw new IllegalStateException(
                        "Identity is not eligible for approval");
            }
            reviewRequired.remove(key);
        }

        public boolean mayApprove(Key key, Invoice invoice) {
            if (key == null || invoice == null) {
                return false;
            }

            DirectoryState current = directory.get(key);
            return current != null
                    && current.active()
                    && current.groups().contains("finance")
                    && !reviewRequired.contains(key)
                    && key.tenant().equals(invoice.tenant())
                    && invoice.pending()
                    && localGrants.getOrDefault(key, Set.of())
                            .contains("invoice:approve");
        }

        public long lastRevision(Key key) {
            DirectoryState current = directory.get(key);
            return current == null ? -1L : current.revision();
        }
    }

    public static void main(String[] args) {
        Key alice = new Key("https://idp.example", "alice-sub", "tenant-a");
        Invoice pendingA = new Invoice("tenant-a", true);
        Engine engine = new Engine();

        engine.grantLocally(alice, "invoice:approve");
        engine.apply(new DirectoryEvent(alice, 10, true,
                Set.of("finance", "employees")));
        System.out.println("initial=" + engine.mayApprove(alice, pendingA));

        engine.apply(new DirectoryEvent(alice, 9, false, Set.of()));
        System.out.println("stale-event=" + engine.mayApprove(alice, pendingA));

        engine.apply(new DirectoryEvent(alice, 11, false, Set.of()));
        System.out.println("disabled=" + engine.mayApprove(alice, pendingA));

        engine.apply(new DirectoryEvent(alice, 12, true, Set.of("finance")));
        System.out.println("reactivated=" + engine.mayApprove(alice, pendingA));

        engine.approveReview(alice);
        System.out.println("reviewed=" + engine.mayApprove(alice, pendingA));

        engine.apply(new DirectoryEvent(alice, 13, true, Set.of("employees")));
        System.out.println("group-removed=" + engine.mayApprove(alice, pendingA));

        engine.apply(new DirectoryEvent(alice, 14, true, Set.of("finance")));
        System.out.println("group-restored=" + engine.mayApprove(alice, pendingA));

        engine.approveReview(alice);
        System.out.println("group-reviewed=" + engine.mayApprove(alice, pendingA));

        Invoice otherTenant = new Invoice("tenant-b", true);
        System.out.println("cross-tenant="
                + engine.mayApprove(alice, otherTenant));
    }
}
~~~

**Chạy trực tiếp với JDK 17+:**

~~~bash
javac IdentityPermissionSyncDemo.java
java IdentityPermissionSyncDemo
~~~

**Đầu ra chính xác của chương trình:**

~~~text
initial=true
stale-event=true
disabled=false
reactivated=false
reviewed=true
group-removed=false
group-restored=false
group-reviewed=true
cross-tenant=false
~~~

Giải thích:

1. Ban đầu đủ IdP group, local grant, tenant và trạng thái hóa đơn nên cho phép.
2. Event revision 9 đến sau revision 10 bị bỏ; không ghi đè.
3. Revision 11 vô hiệu hóa tài khoản, effective access lập tức bị từ chối trong projection.
4. Revision 12 mở lại tài khoản nhưng **reviewRequired** vẫn tồn tại; không tự khôi phục local grant.
5. Sau bước approveReview có chủ đích, quyền hoạt động lại.
6. Revision 13 bỏ finance nên bị chặn và đánh dấu review.
7. Revision 14 thêm lại finance vẫn bị chặn đến khi nghiệp vụ duyệt lại.
8. Local grant gắn tenant-a không cấp quyền lên tenant-b.

### 7.2. Giới hạn của mô hình trong bộ nhớ

Engine không tự xác minh event; giả định **chỉ được gọi sau khi adapter đã xác thực nguồn**. Nó không lưu dữ liệu ra DB, không khóa đồng thời và không bảo vệ khả năng nhiều node ghi cùng lúc. Trong production, điều kiện revision và cập nhật trạng thái phải **atomic** qua transaction/CAS, có unique constraint và outbox để invalidation. Hàm grantLocally trong ví dụ là API minh họa; khi thực tế phải được bảo vệ bằng một quy trình nghiệp vụ độc lập, có kiểm tra người cấp và audit.

Bài dùng quy tắc **bắt buộc duyệt lại sau khi bị vô hiệu hóa hoặc mất nhóm finance** cho quyền nhạy cảm. Đây là một lựa chọn chính sách cụ thể; sản phẩm khác có thể quy định tạm khóa cho đến khi giải quyết hoặc xóa grant, nhưng không nên tự động khôi phục quyền nhạy cảm sau thay đổi lớn mà không có quyết định đã thiết kế.

## 8. Kiểm thử JUnit 5: không chỉ kiểm tra đường được phép

Thêm JUnit Jupiter vào bộ test của dự án. Nếu dùng Gradle Spring Boot 3.x:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

test {
    useJUnitPlatform()
}
~~~

Đặt tệp **IdentityPermissionSyncDemoTest.java** cùng package với ví dụ (ví dụ demo không khai báo package nên dùng default package trong bài tập; dự án thật nên có package nhất quán):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Set;
import org.junit.jupiter.api.Test;

class IdentityPermissionSyncDemoTest {
    private static final IdentityPermissionSyncDemo.Key ALICE =
            new IdentityPermissionSyncDemo.Key(
                    "https://idp.example", "alice-sub", "tenant-a");
    private static final IdentityPermissionSyncDemo.Invoice INVOICE =
            new IdentityPermissionSyncDemo.Invoice("tenant-a", true);

    private IdentityPermissionSyncDemo.Engine ready() {
        var engine = new IdentityPermissionSyncDemo.Engine();
        engine.grantLocally(ALICE, "invoice:approve");
        engine.apply(new IdentityPermissionSyncDemo.DirectoryEvent(
                ALICE, 10, true, Set.of("finance")));
        return engine;
    }

    @Test
    void activeGroupAndLocalGrantAllow() {
        assertTrue(ready().mayApprove(ALICE, INVOICE));
    }

    @Test
    void localGrantWithoutIdentityIsDenied() {
        var engine = new IdentityPermissionSyncDemo.Engine();
        engine.grantLocally(ALICE, "invoice:approve");
        assertFalse(engine.mayApprove(ALICE, INVOICE));
    }

    @Test
    void groupWithoutBusinessGrantIsDenied() {
        var engine = new IdentityPermissionSyncDemo.Engine();
        engine.apply(new IdentityPermissionSyncDemo.DirectoryEvent(
                ALICE, 10, true, Set.of("finance")));
        assertFalse(engine.mayApprove(ALICE, INVOICE));
    }

    @Test
    void staleEventCannotUndoDisable() {
        var engine = ready();
        engine.apply(new IdentityPermissionSyncDemo.DirectoryEvent(
                ALICE, 11, false, Set.of()));
        engine.apply(new IdentityPermissionSyncDemo.DirectoryEvent(
                ALICE, 9, true, Set.of("finance")));
        assertFalse(engine.mayApprove(ALICE, INVOICE));
        assertEquals(11, engine.lastRevision(ALICE));
    }

    @Test
    void duplicateEventDoesNotChangeProjection() {
        var engine = ready();
        engine.apply(new IdentityPermissionSyncDemo.DirectoryEvent(
                ALICE, 10, false, Set.of()));
        assertTrue(engine.mayApprove(ALICE, INVOICE));
        assertEquals(10, engine.lastRevision(ALICE));
    }

    @Test
    void reactivationRequiresBusinessReview() {
        var engine = ready();
        engine.apply(new IdentityPermissionSyncDemo.DirectoryEvent(
                ALICE, 11, false, Set.of()));
        engine.apply(new IdentityPermissionSyncDemo.DirectoryEvent(
                ALICE, 12, true, Set.of("finance")));
        assertFalse(engine.mayApprove(ALICE, INVOICE));
        engine.approveReview(ALICE);
        assertTrue(engine.mayApprove(ALICE, INVOICE));
    }

    @Test
    void removedGroupCannotBeRestoredSilently() {
        var engine = ready();
        engine.apply(new IdentityPermissionSyncDemo.DirectoryEvent(
                ALICE, 11, true, Set.of("employees")));
        engine.apply(new IdentityPermissionSyncDemo.DirectoryEvent(
                ALICE, 12, true, Set.of("finance")));
        assertFalse(engine.mayApprove(ALICE, INVOICE));
    }

    @Test
    void differentTenantOrFinishedInvoiceIsDenied() {
        var engine = ready();
        assertFalse(engine.mayApprove(ALICE,
                new IdentityPermissionSyncDemo.Invoice("tenant-b", true)));
        assertFalse(engine.mayApprove(ALICE,
                new IdentityPermissionSyncDemo.Invoice("tenant-a", false)));
    }

    @Test
    void sameSubjectFromDifferentIssuerIsNotSameUser() {
        var engine = ready();
        var otherIssuer = new IdentityPermissionSyncDemo.Key(
                "https://another-idp.example", "alice-sub", "tenant-a");
        assertFalse(engine.mayApprove(otherIssuer, INVOICE));
    }

    @Test
    void inactiveIdentityCannotBeReviewed() {
        var engine = ready();
        engine.apply(new IdentityPermissionSyncDemo.DirectoryEvent(
                ALICE, 11, false, Set.of()));
        assertThrows(IllegalStateException.class,
                () -> engine.approveReview(ALICE));
    }
}
~~~

Bộ test gồm **10 trường hợp**: đủ quyền, thiếu IdP, thiếu local grant, event cũ, duplicate event, reactivation, mất nhóm, sai tenant/trạng thái, issuer khác và chặn duyệt lại khi inactive. Khi chạy trong dự án Gradle đã có JUnit Jupiter:

~~~bash
./gradlew test --tests IdentityPermissionSyncDemoTest
~~~

Trên Windows/PowerShell:

~~~powershell
.\gradlew.bat test --tests IdentityPermissionSyncDemoTest
~~~

**Kỳ vọng theo mã:** cả 10 test thành công. Đây là kết quả kỳ vọng từ fixture, không phải kết quả chạy Gradle đã được ghi nhận. Đối với hệ thống thật, cần bổ sung integration test với DB, message broker, cache, IdP giả lập và concurrency để kiểm tra giao dịch cùng hành vi nhiều node.

## 9. Áp dụng vào Spring Security: không chỉ ánh xạ JWT group thành role

### 9.1. Xác thực JWT và danh tính ổn định

Spring Security OAuth2 Resource Server hỗ trợ xác minh chữ ký JWT, thời hạn exp/nbf và issuer phù hợp cấu hình. Trong ứng dụng thật còn cần xác minh **audience (aud)** đúng API đang phục vụ và các điều kiện issuer/trust boundary theo hợp đồng.

Cấu hình minh họa **application.yml** cho một resource server:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example/realms/main
~~~

Với cấu hình mặc định, scope/scp thường được ánh xạ thành GrantedAuthority có tiền tố **SCOPE_**. Spring Security không mặc định hiểu mọi claim groups do các IdP khác nhau phát hành là quyền nghiệp vụ của ứng dụng. Khi cần dùng groups, cấu hình JwtAuthenticationConverter/GrantedAuthoritiesConverter tường minh và dùng allowlist; không tự biến toàn bộ giá trị nhóm thành quyền approve.

Một JWT đã được xác minh **không bảo đảm claims phản ánh sự thay đổi vừa xảy ra** trên IdP: người dùng vẫn có thể cầm token phát hành trước khi bị khóa hoặc bị thu hồi nhóm. Kiểm tra claim exp chưa đủ nếu chức năng yêu cầu hiệu lực thu hồi gần tức thời.

### 9.2. Chặn tại service bằng @PreAuthorize và policy nghiệp vụ

Trong Spring Security 6.x, cần bật method security:

~~~java
// Trích đoạn đặt trong một @Configuration của ứng dụng.
@Configuration
@EnableMethodSecurity
class AuthorizationConfiguration {}
~~~

Tạo một policy bean gọi cơ sở dữ liệu/permission service để tổng hợp trạng thái IdP projection, grant và tài nguyên. Đoạn sau **minh họa tích hợp**, không phải chương trình độc lập: các repository/interface domain cần được hiện thực theo dự án.

~~~java
@Component("invoiceAccess")
public class InvoiceAccessPolicy {
    private final InvoiceRepository invoices;
    private final IdentityProjectionRepository directory;
    private final BusinessGrantRepository grants;

    public InvoiceAccessPolicy(InvoiceRepository invoices,
                               IdentityProjectionRepository directory,
                               BusinessGrantRepository grants) {
        this.invoices = invoices;
        this.directory = directory;
        this.grants = grants;
    }

    public boolean mayApprove(Authentication authentication, long invoiceId) {
        if (!(authentication instanceof JwtAuthenticationToken token)) {
            return false;
        }

        Jwt jwt = token.getToken();
        if (jwt.getIssuer() == null || jwt.getSubject() == null) {
            return false;
        }

        Invoice invoice = invoices.findById(invoiceId).orElse(null);
        if (invoice == null || !invoice.isPending()) {
            return false;
        }

        String issuer = jwt.getIssuer().toString();
        String subject = jwt.getSubject();
        String tenant = invoice.getTenantId(); // Lấy từ DB, không tin request.

        return directory.isActiveAndCurrent(issuer, subject)
                && directory.isInGroup(issuer, subject, "finance")
                && grants.hasActiveGrant(
                        issuer, subject, tenant, "invoice:approve")
                && grants.notPendingReapproval(issuer, subject, tenant);
    }
}

@Service
public class InvoiceService {
    @PreAuthorize("@invoiceAccess.mayApprove(authentication, #p0)")
    public void approve(long invoiceId) {
        // Cập nhật có điều kiện theo trạng thái/hạn mức trong giao dịch.
    }
}
~~~

**Import cần có** cho trích đoạn: Configuration, EnableMethodSecurity, Component, Service, PreAuthorize, Authentication, JwtAuthenticationToken, Jwt. Các repository và class Invoice thuộc ứng dụng nên không có triển khai trong đoạn này.

**Vì sao dùng #p0?** Đây là tham số thứ nhất của phương thức, tránh phụ thuộc vào việc project có bật compiler flag để giữ tên tham số Java hay không. Bean invoiceAccess phải là Spring-managed; phương thức bảo vệ phải được gọi qua Spring AOP proxy. Nếu code tự new InvoiceService() hoặc gọi nội bộ qua this., interceptor @PreAuthorize có thể bị bỏ qua.

**Kiểm tra ngay tại nghiệp vụ:** Tên tenant được tra từ hóa đơn thật, không lấy từ client. Nếu trạng thái hóa đơn có thể đổi giữa lúc kiểm tra và lúc cập nhật, dùng transaction, lock hoặc UPDATE ... WHERE status='PENDING' và xác minh số dòng cập nhật, tránh lỗi TOCTOU. Với thao tác nhạy cảm, quyền hiệu lực cần được kiểm tra theo dữ liệu đủ mới và chính sách nhất quán với giao dịch.

### 9.3. HTTP layer và token scope

Có thể dùng request rule để lọc bước đầu, sau đó để service policy ra quyết định tài nguyên:

~~~java
// Trích cấu hình SecurityFilterChain, không độc lập.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.POST, "/api/invoices/*/approve")
        .hasAuthority("SCOPE_invoices.approve")
    .anyRequest().denyAll()
).oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()));
~~~

Scope **SCOPE_invoices.approve** là quyền coarse-grained do token phát hành; **không thay thế** local business grant, tenant scope, account state và điều kiện hóa đơn trong method security. Với JWT cũ còn scope, policy service có thể vẫn từ chối dựa trên projection IdP đã cập nhật và quyền nghiệp vụ hiện hành.

Trong hệ thống không dùng JWT hoặc dùng session/OIDC login, Authentication có kiểu khác; cần adapter tương ứng lấy danh tính đáng tin cậy thay vì ép mọi request thành JwtAuthenticationToken. Không dựa trực tiếp vào authentication.getName() như một khóa toàn cục vì nhiều cấu hình JWT chỉ trả về sub mà thiếu issuer.

### 9.4. Mức độ nhất quán và cache quyền

Mỗi chức năng cần chính sách rõ về **độ trễ đồng bộ tối đa**:

| Loại thao tác | Hướng xử lý khi projection quá cũ hoặc IdP mất kết nối |
| --- | --- |
| Phê duyệt, chuyển tiền, nâng quyền, xuất dữ liệu nhạy cảm | Có thể yêu cầu kiểm tra trạng thái đủ mới hoặc từ chối cho đến khi xác minh; ưu tiên fail closed |
| Đọc dữ liệu không nhạy cảm, tác vụ ít rủi ro | Có thể cho phép stale theo TTL ngắn đã được phê duyệt, vẫn kiểm tra local grant và tenant |
| Tác vụ nền có service identity | Kiểm tra quyền của danh tính dịch vụ riêng, không mặc định mượn ROLE_ADMIN |
| Tài khoản đã bị vô hiệu hóa trong projection | Từ chối; không dùng cache allow cũ để ghi đè trạng thái bị khóa |

**Không có một TTL dùng cho mọi sản phẩm.** Mục tiêu thu hồi quyền cần cân bằng với availability và được xác định theo nguy cơ. Trong mọi trường hợp, không diễn giải lỗi IdP timeout thành “không tìm thấy cập nhật nên tiếp tục cấp quyền vô hạn”.

Cache quyết định **allow** cần khóa đủ issuer + sub + tenant + resource + action + phiên bản quyền/nhóm (và các điều kiện policy thực sự ảnh hưởng kết quả). Khi người dùng bị khóa hoặc quyền bị thu hồi, invalidate chính xác; nếu invalidation có độ trễ, TTL/safety gate phải giữ quyền rủi ro cao trong giới hạn được phê duyệt.

## 10. Đồng bộ và đối soát mà không ghi đè quyền nghiệp vụ

### 10.1. Ingestion và transaction

Ví dụ luồng **mang tính giả mã**, nhằm chỉ ra trách nhiệm giao dịch:

~~~text
receive(verified_event):
    validate_schema_and_trust(verified_event)
    key = (issuer, subject)
    begin transaction
        if inbox already contains (source, eventId):
            commit and acknowledge
        else:
            current = load IdP projection FOR UPDATE
            if event is a full snapshot with verifiable newer revision:
                update only IdP-owned fields
                if account was disabled or sensitive group removed:
                    mark local sensitive grants as requiring review
            store inbox eventId
            store outbox cache-invalidation message
    commit
    acknowledge only after commit
~~~

Nếu phiên bản nguồn là ETag opaque, không so “v2” lớn hơn “v1” theo chữ/số; dùng cách kiểm soát đồng thời mà nguồn hỗ trợ hoặc đọc snapshot hiện tại với một revision do adapter cung cấp. Nếu event chỉ chứa PATCH, phải ghép từng trường được thay đổi; không coi trường thiếu là giá trị rỗng.

Trong database, một điều kiện upsert hoặc compare-and-swap **atomic** giúp hai worker không cùng ghi đè sai thứ tự. Khi outbox phát không thành công, có thể retry mà không phát lệnh phân quyền sai, vì invalidation có idempotency và version.

### 10.2. Reconciliation không được trở thành “mass revoke”

Quy trình định kỳ nên:

1. Đọc danh sách identity/projection được phép đối soát theo issuer/tenant, xử lý đủ mọi trang dữ liệu.
2. Ghi nhận watermark hoặc phiên bản snapshot; xác nhận nguồn trả **đầy đủ và thành công**.
3. So sánh active, groups và liên kết danh tính; ghi drift theo từng khóa.
4. Sửa các thuộc tính **do IdP sở hữu**, không ghi đè local business grants.
5. Với xóa/khóa/tước nhóm, áp đúng chính sách deny/review, invalidation và audit.
6. Với sự kiện có conflict hoặc phiên bản không thể so sánh, chuyển sang đối soát riêng, không tự cấp quyền.
7. Báo kết quả và cảnh báo chênh lệch bất thường; ưu tiên thao tác có thể chạy lại nhiều lần mà không tác dụng phụ không mong muốn.

Nếu API IdP bị timeout giữa quá trình phân trang, phần danh sách thiếu không có nghĩa người dùng đã bị xóa. Một hệ thống reconciliation chỉ nên xử lý **deletion by absence** khi đã có **ảnh chụp toàn vẹn** hoặc tín hiệu xóa rõ ràng theo hợp đồng.

### 10.3. Ai được thay đổi bản đồ quyền?

Bảng ánh xạ IdP group → business eligibility phải có owner, version, quy trình review và test. Từ góc nhìn domain, không chấp nhận một thay đổi tên nhóm IdP làm hệ thống bất ngờ cấp **invoice:approve** cho toàn bộ nhóm. Bảng ánh xạ giống code phân quyền và cần cùng tiêu chuẩn kiểm thử, duyệt và triển khai.

Nếu tổ chức chia nhóm chính sách theo tenant, cần audit rõ rule nào đã áp dụng tại thời điểm quyết định. Khi hợp đồng mapping thay đổi, cân nhắc tăng policyVersion để invalidate cache và tránh trộn hai cách hiểu quyền.

## 11. Ma trận kiểm thử tích hợp để bảo đảm nhất quán

| Ca | Trạng thái IdP | Local grant | Tài nguyên/điều kiện | Kỳ vọng |
| --- | --- | --- | --- | --- |
| A1 | Active, finance | invoice:approve | Đúng tenant, PENDING | Allow |
| A2 | Active, finance | Không có invoice:approve | Đúng tenant | Deny |
| A3 | Active, không còn finance | invoice:approve | Đúng tenant | Deny |
| A4 | Disabled | invoice:approve còn lưu | Đúng tenant | Deny |
| A5 | Reactivated sau disabled | Grant cũ đang chờ review | Đúng tenant | Deny đến khi duyệt lại |
| A6 | Active, finance | invoice:approve | Tenant khác | Deny |
| A7 | Active, finance | invoice:approve | Hóa đơn đã hoàn tất | Deny |
| A8 | Revision mới khóa trước; revision cũ active đến muộn | Grant còn lưu | Đúng tenant | Deny, không rollback |
| A9 | Cùng eventId phát lại nhiều lần | Không thay đổi | Giữ nguyên | Idempotent |
| A10 | sub giống, issuer khác | Grant của issuer cũ | Đúng tenant | Deny |
| A11 | JWT còn hạn sau khi IdP khóa | Grant còn lưu | Quyền nhạy cảm | Deny theo projection hiện hành |
| A12 | Group finance bị thu hồi rồi thêm lại | Grant cũ cần review | Đúng tenant | Deny cho đến quyết định mới |
| A13 | SCIM PATCH thiếu trường groups | Giữ local grant | Đúng tenant | Không xóa groups vì trường vắng mặt |
| A14 | Reconciliation lỗi giữa chừng | Không rõ trạng thái đầy đủ | Nhiều account | Không mass-delete |
| A15 | Đã cấp lại quyền ở tenant A | Không có grant tenant B | Tài nguyên B | Deny |
| A16 | Hai đồng bộ viên áp revision khác nhau cùng lúc | Grant riêng | Đúng tenant | Revision mới nhất hợp lệ thắng |
| A17 | Cache allow chưa invalidated | Quyền đã bị thu hồi | Hành động nhạy cảm | Deny theo cơ chế freshness |
| A18 | IdP tạm thời không phản hồi | Local grant vẫn có | Phê duyệt rủi ro cao | Áp chính sách stale/fail closed đã phê duyệt |

**Phân tầng test:** JUnit đơn vị xác minh thuật toán hợp nhất như mục 8. Integration test với DB kiểm chứng transaction/unique version, test broker kiểm chứng duplicate/reorder/retry, Spring Security test kiểm chứng 401/403, và end-to-end test có IdP giả lập kiểm chứng JWT cũ sau khi khóa tài khoản.

Một bài test Spring chỉ dùng @WithMockUser(authorities="invoice:approve") **chưa chứng minh đồng bộ quyền đúng** vì nó tự cấp authority trong test. Cần fixture điều khiển riêng dữ liệu IdP projection, local grant, tenant/resource và phiên bản. Với endpoint HTTP dùng session/CSRF, test POST phải có CSRF token hợp lệ nếu mục tiêu là kiểm tra quyền thay vì kiểm tra CSRF.

Đối với concurrency, nên kiểm tra trường hợp hai consumer cùng nhận revision 21 và 22: kết quả cuối vẫn là 22. Nếu toàn hệ thống có cache đa node, kiểm tra một node cập nhật và node khác không thể tiếp tục dùng quyền đã thu hồi vượt quá freshness window.

## 12. Vận hành: theo dõi độ trễ và sai lệch dữ liệu

| Nhóm chỉ số | Gợi ý theo dõi |
| --- | --- |
| Event ingestion | Số sự kiện nhận/xử lý, duplicate, stale version, lỗi schema/chữ ký |
| Đồng bộ | Độ trễ từ IdP thay đổi đến projection cập nhật, backlog và tuổi sự kiện cũ nhất |
| Reconciliation | Số bản ghi drift, số sửa thành công, lần snapshot không đầy đủ |
| Quyền hiệu lực | Tỷ lệ allow/deny theo capability nhóm hữu hạn, deny vì inactive/group/local/tenant |
| Cache | Cache hit/miss, thời gian invalidation, version mismatch, thời gian dùng stale |
| Bảo mật | Số yêu cầu reapproval, thời gian revoke có hiệu lực, biến động quyền bất thường |
| Hạ tầng | Lỗi IdP API, timeout, retry, outbox chậm, DB contention và policy latency |

**Cảnh báo đáng chú ý:** một đợt đồng bộ làm thay đổi hàng loạt quyền invoice:approve, tỷ lệ deny đột biến sau một mapping release, inbox backlog lớn hoặc projection cũ quá ngưỡng cho quyền nhạy cảm.

Trong metrics không đặt **sub, email, tenantId, invoiceId, token, raw URL** làm tag có cardinality vô hạn. Thông tin truy vết chi tiết lưu ở audit/log đã được kiểm soát truy cập, liên kết bằng correlation id.

### 12.1. Khi IdP tạm ngừng hoạt động

Không thể bảo đảm nhất quán tuyệt đối giữa IdP và ứng dụng ở mọi thời điểm khi hai hệ thống tách biệt. Cần nói rõ **mô hình nhất quán**: event-driven eventual consistency, polling có SLA, kiểm tra trực tuyến với IdP ở thao tác rủi ro cao, hoặc deny nếu trạng thái quá cũ.

Đối với quyền phê duyệt tài chính, có thể không chấp nhận trạng thái stale hơn một ngưỡng ngắn được cấu hình. Đối với tác vụ đọc ít nhạy cảm, doanh nghiệp có thể chấp nhận stale bounded. Quyết định phải được thiết kế, đo đạc và test; không suy ra tự nhiên từ việc cache có TTL.

### 12.2. Vòng đời đổi quyền nghiệp vụ

Hãy mô tả riêng quy trình tạo/cấp/thu hồi invoice:approve trong hệ thống nghiệp vụ: người đề nghị, người phê duyệt, tenant, hạn mức, lý do, effective time, expiry, audit trail. **Identity sync consumer không nên tự đóng vai quản trị viên nghiệp vụ.** Nếu dùng bảng business_grant, kiểm soát quyền sửa bảng và kiểm tra mọi luồng ghi, không chỉ endpoint HTTP.

## 13. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng email làm khóa đồng bộ | Gán nhầm quyền khi email đổi/tái sử dụng | Dùng issuer + subject, liên kết account đã xác minh |
| Copy IdP groups vào cùng cột roles nghiệp vụ | IdP sync ghi đè quyền cấp ở ứng dụng | Tách projection với business grants, policy hợp nhất |
| Tin group finance = invoice:approve | Mở rộng quyền vượt phạm vi | Dùng điều kiện đủ + local grant + tenant/resource check |
| Áp event theo thời gian nhận | Sự kiện cũ hồi sinh quyền đã thu hồi | Version/revision hoặc snapshot/ETag được kiểm chứng |
| Dùng SCIM ETag như số tăng dần | So sánh phiên bản không có nghĩa | Xem ETag như opaque; If-Match/snapshot sync đúng hợp đồng |
| PATCH thiếu groups bị hiểu thành [] | Thu hồi nhầm hàng loạt | Phân biệt partial update với snapshot đầy đủ |
| Xóa cứng projection ngay khi deprovision | Event cũ có thể tạo lại | Tombstone/version và kiểm soát lifecycle |
| Kích hoạt lại IdP tự khôi phục grant cũ | Quyền nhạy cảm không được review | Giữ deny/review gate đến khi được duyệt |
| JWT còn hạn bị coi là quyền mới nhất | Thu hồi quyền chậm | Fresh projection/introspection/revocation/TTL theo rủi ro |
| Cache key chỉ theo sub | Rò quyền khác issuer/tenant/resource | Key đầy đủ context, version và invalidation |
| Reconcile thiếu một trang coi là deleted | Khóa/mất quyền hàng loạt | Chỉ xử lý missing khi snapshot đầy đủ |
| Tắt IdP nghĩa là allow bằng cache vô hạn | Người bị khóa tiếp tục thao tác | Freshness policy và fail closed với quyền nhạy cảm |
| Chỉ test allow, không test deny | Bỏ sót quyền bị mở rộng | Ma trận positive/negative và trạng thái dữ liệu |
| Dựa vào @WithMockUser để kiểm tra provisioning | Test không chạm nguồn IdP/local grants | Test riêng pipeline, DB và token mapping |

## 14. Bài thực hành

**Bài 1 — Giữ quyền nghiệp vụ:** Thêm quyền report:export trong localGrants cho Alice. IdP thay đổi group employees nhưng không thay nhóm điều kiện export. Chứng minh không một sự kiện IdP nào tự xóa local grant; đồng thời xác định rõ khi nào report:export phải bị chặn bởi chính sách hiệu lực.

**Bài 2 — Đồng bộ sai thứ tự:** Gửi các event revision 30 active, 32 inactive, 31 active. Viết test xác nhận revision cuối là 32 và quyền bị từ chối. Thêm một eventId trùng để kiểm thử inbox idempotency.

**Bài 3 — Multi-tenant:** Alice có invoice:approve ở tenant A nhưng không ở B. Thêm bảng hóa đơn với tenantId lấy từ DB; chứng minh request truyền tenant=A không đủ cấp quyền nếu id tài nguyên thật thuộc B.

**Bài 4 — Đồng bộ sau deprovision:** Vô hiệu tài khoản, giữ local grant cho audit, bật lại tài khoản trên IdP. Triển khai reviewRequired và test chỉ quản trị viên nghiệp vụ mới được xóa trạng thái review sau bước duyệt, có audit log.

**Bài 5 — Token cũ:** Mô phỏng JWT phát trước khi IdP thu hồi finance. Test token vẫn vượt qua bước xác thực nhưng policy @PreAuthorize bị từ chối theo projection mới. Thử các mức TTL và xác định phạm vi độ trễ thu hồi chấp nhận được.

**Bài 6 — Reconciliation thiếu dữ liệu:** Mock API IdP trả trang 1 thành công, trang 2 lỗi. Chứng minh logic không suy luận tất cả identity ở trang 2 đã bị xóa. Sau khi khôi phục, chạy lại một lượt đầy đủ và ghi audit drift.

**Bài 7 — Đồng thời:** Hai worker xử lý revision 44 và 45 trên cùng Key. Dùng transaction/unique constraint/optimistic locking để chứng minh trạng thái cuối không thể quay lại 44.

## 15. Checklist nghiệm thu

- [ ] Có bảng ownership rõ: IdP làm chủ identity lifecycle/groups, nghiệp vụ làm chủ grants/ACL/hạn mức.
- [ ] Khóa danh tính dùng issuer + subject, scope tenant được xác minh.
- [ ] Quyền hiệu lực gồm active status, group gate, local grant và resource conditions phù hợp.
- [ ] Ingestion xác minh nguồn, hỗ trợ duplicate event và event sai thứ tự.
- [ ] Partial update không xóa trường vắng mặt; ETag được xử lý đúng semantics.
- [ ] Deprovision/tombstone không cho event cũ hồi sinh quyền.
- [ ] Kích hoạt lại sau thu hồi quyền nhạy cảm có chính sách review rõ.
- [ ] Reconciliation chỉ sửa dữ liệu IdP-owned và không xử lý thiếu snapshot như xóa.
- [ ] Cache/token cũ được xử lý theo freshness/thu hồi quyền đã định nghĩa.
- [ ] @EnableMethodSecurity và @PreAuthorize thực thi qua Spring-managed bean; policy lấy tenant từ dữ liệu tin cậy.
- [ ] Có test cả allow và deny cho inactive, local missing, group missing, cross-tenant, stale token, replay và concurrency.
- [ ] Audit và metrics đủ điều tra nhưng không lộ token hoặc thông tin nhạy cảm.

## 16. Tài liệu tham khảo

- Spring Security — OAuth2 Resource Server JWT, xác minh claims và JwtAuthenticationConverter: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — Method Security / @EnableMethodSecurity / @PreAuthorize: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- RFC 7643 — SCIM Core Schema: https://www.rfc-editor.org/rfc/rfc7643
- RFC 7644 — SCIM Protocol, PATCH và ETag: https://www.rfc-editor.org/rfc/rfc7644
- OpenID Connect Core 1.0 — Issuer, Subject, ID Token: https://openid.net/specs/openid-connect-core-1_0.html
- OAuth 2.0 Token Introspection (RFC 7662): https://www.rfc-editor.org/rfc/rfc7662
- OAuth 2.0 Token Revocation (RFC 7009): https://www.rfc-editor.org/rfc/rfc7009
