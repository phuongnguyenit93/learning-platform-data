# Partner offboarding: chấm dứt quyền truy cập của đối tác trong IAM

## 1. Partner offboarding là gì?

**Partner offboarding** là quy trình **kết thúc hoặc thu hẹp có kiểm soát quan hệ truy cập giữa một tổ chức và đối tác bên ngoài**, đồng thời thu hồi những danh tính, quyền, phiên, credential và tích hợp không còn cơ sở hợp lệ. Đối tác có thể là đại lý, doanh nghiệp cùng triển khai dịch vụ, nhà phân phối, công ty tư vấn, nhà cung cấp hoặc một tổ chức cùng vận hành nền tảng B2B.

Khác với thao tác xóa một tài khoản, partner offboarding phải trả lời đồng thời:

1. **Quan hệ nào kết thúc?** Một hợp đồng, dự án, tenant, dịch vụ hay toàn bộ đối tác?
2. **Chủ thể nào bị ảnh hưởng?** Người dùng bên ngoài, guest account, nhóm, service account, OAuth client, workload federation hoặc tài khoản kỹ thuật?
3. **Quyền nào phải mất hiệu lực?** Role, membership, API scope, access grant, chia sẻ tài liệu, đặc quyền PAM, quyền mạng và ACL trực tiếp?
4. **Khi nào phải ngừng truy cập?** Ngay khi nhận sự kiện rủi ro, tại thời điểm hợp đồng hết hiệu lực hay sau một bước chuyển giao được phê duyệt?
5. **Xác minh bằng cách nào?** Hệ thống đích đã thực sự chặn các request cũ và mới hay chỉ có một phiếu yêu cầu đang chờ?
6. **Điều gì được giữ lại?** Dữ liệu, log, bằng chứng, bản sao lưu hoặc hồ sơ hợp đồng theo nghĩa vụ pháp lý và chính sách lưu giữ?

Ví dụ: Công ty A cho đối tác B truy cập hệ thống đơn hàng để phân phối sản phẩm. B có 20 nhân viên đăng nhập SSO, ba guest account hỗ trợ, hai API clients đồng bộ đơn hàng và một tài khoản kỹ thuật bảo trì. Khi hợp đồng A–B kết thúc, **khóa 20 nhân viên ở IdP B vẫn chưa đủ**. A phải ngăn đăng nhập mới, vô hiệu hóa những grants phụ thuộc hợp đồng, xử lý phiên/token còn hoạt động, tắt tích hợp máy, gỡ quyền trên ứng dụng đích và kiểm chứng rằng B không còn đọc hoặc sửa dữ liệu của A ngoài những phạm vi còn được phê duyệt riêng.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, đây là tình huống **Leaver** ở cấp tổ chức của mô hình **Joiner–Mover–Leaver (JML)**. Nó liên quan chặt với **IdP, SSO, SCIM, RBAC/ABAC, service account, PAM, kiểm toán** và mục tiêu giảm **quyền truy cập tồn dư**.

### Kết quả học tập

Người học có thể:

- Phân biệt offboarding một principal với offboarding một quan hệ hợp tác;
- Lập danh sách chủ thể, tài nguyên và quyền chịu ảnh hưởng;
- Thiết kế cơ chế ngăn cấp quyền mới trước khi xử lý quyền cũ;
- Thu hồi user, workload, session, token, quyền ứng dụng và cấu hình federation đúng thứ tự;
- Xử lý trường hợp một đối tác có nhiều hợp đồng hoặc nhiều tenant;
- Đối soát và ghi bằng chứng hoàn tất, kể cả ngoại lệ kỹ thuật/pháp lý;
- Thiết kế runbook, KPI và bài kiểm thử phòng chống tái kích hoạt quyền.

## 2. Không đồng nhất offboarding người dùng với offboarding đối tác

Một partner có thể đang hoạt động theo nhiều quan hệ cùng lúc. Việc nghỉ việc của một nhân viên B không đồng nghĩa toàn bộ B phải bị khóa. Ngược lại, chấm dứt hoàn toàn quan hệ A–B có thể yêu cầu thu hồi rất nhiều danh tính ngoài danh sách nhân viên.

| Cấp offboarding | Sự kiện minh họa | Phạm vi thu hồi | Phạm vi cần giữ |
|---|---|---|---|
| Một **grant** | U không còn cần đọc dự án P42 | Quyền đọc P42 của U | Quyền hợp lệ khác của U |
| Một **membership** | U rời tenant-B | Mọi grants phụ thuộc membership tenant-B | Membership hợp lệ ở tenant khác nếu có |
| Một **principal** | Kỹ sư B nghỉ việc | Guest, sessions và grants của cá nhân đó | Các nhân viên B khác |
| Một **workload** | API tích hợp W ngừng hoạt động | Client W, credential, scopes và webhook liên quan | Client B khác vẫn được phép |
| Một **relationship/hợp đồng** | Hợp đồng phân phối P42 hết hạn | Mọi grants phụ thuộc hợp đồng P42 | Hợp đồng hỗ trợ P51 còn hợp lệ |
| Một **partner tổ chức** | A chấm dứt hợp tác với B hoàn toàn | Tất cả quan hệ, user/workload và trust chỉ phục vụ B | Quyền của partner C độc lập |

**Nguyên tắc:** Thu hồi theo **nguồn tạo quyền** (provenance) và **phạm vi quan hệ**, không theo một danh sách email được đoán từ domain. Một IdP hoặc một email domain có thể phục vụ nhiều đối tác, công ty con hoặc quan hệ khác nhau. Nếu cấu hình tin cậy được dùng chung, không được xóa nó một cách mù quáng khiến các quan hệ đang hợp lệ bị ảnh hưởng.

### Ba trạng thái cần theo dõi độc lập

- **Partner/relationship state:** quan hệ tổ chức, hợp đồng hoặc dự án đang active, suspended hay terminated?
- **Principal state:** user/guest/workload đang active, suspended hay revoked?
- **Entitlement/session state:** những grants, role, token và phiên nào thực sự còn quyền?

Một principal có thể active vì vẫn dùng một hợp đồng khác, nhưng **grant phát sinh từ hợp đồng đã kết thúc phải bị DENY**. Một token còn hạn không làm hợp đồng hoặc grant trở nên hợp lệ trở lại.

## 3. Những sự kiện kích hoạt partner offboarding

### 3.1. Offboarding theo kế hoạch

| Trigger | Nguồn tín hiệu | Cách xử lý |
|---|---|---|
| Hợp đồng hết hạn, không gia hạn | Contract/procurement | Chốt ngày ngắt truy cập, phạm vi, chủ tài nguyên, bàn giao |
| Dự án hoàn tất sớm | Sponsor/project owner | Thu hồi quyền dự án, giữ hợp đồng khác nếu có |
| Đối tác đổi sang nhà cung cấp mới | Business owner/vendor management | Lập phương án chuyển tiếp, gỡ quyền cũ theo cutover |
| Chuyển mô hình hợp tác | Partner manager, pháp chế | Rà soát lại quan hệ, grants, IdP trust và owner |
| Ngừng một API integration | API owner/technical owner | Disable client và credential riêng, kiểm chứng API |
| Tái cơ cấu hoặc đổi tenant | Quản trị đối tác, IAM | Xác minh tổ chức mới, migrate có kiểm soát, không tự cộng dồn quyền |

### 3.2. Offboarding khẩn cấp

Có thể cần khóa ngay khi phát hiện đối tác bị xâm nhập, key bị lộ, vi phạm điều kiện truy cập, rủi ro dữ liệu nghiêm trọng hoặc quan hệ bị đình chỉ. Với tình huống này, **thứ tự ưu tiên chuyển sang containment**: từ chối request mới, chặn đặc quyền và credential nhạy cảm, xử lý phiên đang mở, sau đó điều tra phạm vi và hoàn thiện đối soát. Không chờ đủ mọi thủ tục bàn giao dữ liệu trước khi ngăn một truy cập đang gây nguy hiểm.

### 3.3. Sự kiện đầu vào phải đáng tin

Một email tự nhận là “đối tác chấm dứt hợp đồng” có thể sai hoặc bị giả mạo. Workflow cần xác minh sự kiện qua hệ thống hợp đồng, sponsor, đầu mối đối tác đã đăng ký hoặc kênh được thẩm quyền xác nhận. Với khẩn cấp, chính sách có thể cho phép đội an ninh đình chỉ có thời hạn trước khi xác minh đầy đủ, nhưng phải có log, phạm vi và người chịu trách nhiệm.

Mỗi sự kiện cần có định danh quan hệ, nguồn, thời điểm hiệu lực, yêu cầu ưu tiên, người phê duyệt và correlation ID. Không dùng tên hiển thị hoặc email làm khóa duy nhất để truy tìm tất cả quyền.

## 4. Lập bản đồ phụ thuộc trước khi thu hồi

### 4.1. Danh sách các lớp truy cập cần tìm

| Lớp | Đối tượng cần liệt kê | Nguồn dữ liệu khả dĩ |
|---|---|---|
| Quan hệ B2B | Partner ID, contract, sponsor, project, tenant | Partner/contract registry |
| Con người | External user, guest, alias, group, membership | IAM, IdP, guest directory |
| Xác thực | OIDC issuer, SAML IdP trust, broker mapping | Federation configuration |
| Provisioning | SCIM client, mapping nhóm, JIT rule, invitation | Provisioning/IAM |
| Authorization | RBAC role, ABAC grant, delegated admin, app ACL | Policy/grant store và ứng dụng |
| Remote access | VPN/ZTNA, SSH, jump host, remote-support access | Network/PAM platform |
| Đặc quyền | PAM vault checkout, JIT elevation, privileged sessions | PAM/audit |
| Workload | OAuth client, API key, service account, mTLS certificate | AS, API gateway, IAM, secret inventory |
| Developer tooling | Repository, CI/CD, deployment role, artifact registry | Git/DevOps platform |
| Dữ liệu | Shared folder, external link, database role, BI dashboard | Data owner/SaaS |
| Tích hợp nền | Webhook, queue consumer, scheduled job, cloud trust | Integration/cloud platform |
| Phiên/token | App session, refresh token, access token, key material | IdP, AS, resource server |

**Quyền ứng dụng đích có thể không trùng quyền IAM trung tâm.** Một admin đã chia sẻ file trực tiếp cho nhân viên B hoặc tạo API key thủ công nhiều tháng trước; những quyền này phải được phát hiện qua inventory và reconciliation.

### 4.2. Mô hình phụ thuộc có thể truy vết

~~~mermaid
flowchart TD
    B["Partner B"] --> R1["Relationship CTR-P42"]
    B --> R2["Relationship CTR-P51"]
    R1 --> G1["Grant nhóm người dùng P42"]
    R1 --> C1["OAuth client W"]
    R1 --> A1["Chia sẻ dữ liệu / ACL"]
    G1 --> U1["Guest U"]
    G1 --> U2["Guest V"]
    U1 --> S1["Phiên ứng dụng / PAM"]
    C1 --> K1["Secret / certificate"]
    C1 --> Q1["API / webhook"]
    R2 --> G2["Grant dự án P51"]
    G2 --> U3["Guest X"]
~~~

Nếu chỉ CTR-P42 kết thúc, hệ thống phải tìm G1, C1, A1 và các phụ thuộc của chúng; **không tự xóa G2 hoặc tài khoản U3 ở CTR-P51**. Nếu toàn bộ B chấm dứt, phạm vi mở rộng tới cả R1 và R2.

### 4.3. Thiết kế khóa định danh và quyền

Nên có:

- Partner ID và relationship/contract ID ổn định;
- Local principal ID, loại human/workload và nguồn xác thực;
- Grant ID, role, tenant/project/resource/action, hạn, owner và relationship tạo ra quyền;
- Đường liên kết đến các hệ thống đích/credential;
- Trạng thái desired và actual tại thời điểm kiểm tra.

Với OIDC, liên kết user qua **cặp (issuer, subject)** đã được xác minh; với SAML, dùng định danh ổn định gắn issuer/IdP đã tin cậy. Với workload, dùng client/workload identity gắn authorization server và owner. Không coi email giống nhau là chứng cứ để thu hồi một người khác hoặc chuyển quyền sang người mới.

### 4.4. Inventory không đầy đủ thì sao?

Ghi rõ những hệ thống chưa có API xuất quyền, các nhóm chỉ được kiểm tra thủ công và quyền nào có thể còn chưa phát hiện. **Không đóng offboarding ở trạng thái verified nếu còn mục tiêu trọng yếu chưa được kiểm chứng**. Tùy rủi ro, có thể chặn truy cập ở lớp gateway/mạng làm biện pháp kiểm soát tạm thời, song vẫn cần xử lý từng quyền gốc và báo cáo ngoại lệ.

## 5. Trách nhiệm, phê duyệt và mốc kiểm soát

| Vai trò | Trách nhiệm chính trong offboarding |
|---|---|
| Business sponsor | Xác nhận quan hệ/công việc kết thúc, danh sách nhu cầu không còn, thời hạn cutover |
| Partner/vendor manager | Xác nhận hợp đồng, pháp nhân, đầu mối và thông báo đối tác |
| Resource owner | Phê duyệt phạm vi thu hồi và xử lý tài nguyên/dữ liệu do mình sở hữu |
| IAM / Identity governance | Xác định quyền liên quan, chặn cấp mới, revoke, lưu dấu vết và đối soát |
| Security / Incident response | Chỉ đạo containment, ưu tiên khẩn cấp, xử lý quyền đặc biệt và sự cố |
| App owner | Gỡ grants/ACL tại ứng dụng đích và cung cấp kết quả verified |
| API/platform/DevOps owner | Disable workload, client, key, CI/CD, cloud trust và webhook |
| Legal/privacy/data owner | Quyết định nghĩa vụ lưu/xóa/chuyển dữ liệu theo hợp đồng và quy định |
| Đầu mối B | Xác nhận danh sách chủ thể, hỗ trợ chuyển giao và thông báo thay đổi bên đối tác |

Một sponsor không thể thay resource owner tự duyệt mọi thao tác kỹ thuật; ngược lại IAM không nên tự quyết rằng dữ liệu phải xóa ngay khi hợp đồng kết thúc. Phân chia rõ quyết định kinh doanh, phân quyền và nghĩa vụ dữ liệu.

### 5.1. Pre-offboarding checklist

Trước ngày ngắt truy cập theo kế hoạch, phải có:

1. Phạm vi tổ chức/relationship và các hệ thống bị ảnh hưởng;
2. Danh sách owner, contact và người phê duyệt;
3. Ngày cutover được ghi rõ múi giờ, hạn xử lý và độ ưu tiên;
4. Inventory người dùng, group, client, secret, session, grants, chia sẻ và tài khoản máy;
5. Cơ chế chặn provisioning tái kích hoạt quyền;
6. Bản kế hoạch ứng dụng đích, điều kiện xác nhận và cách xử lý lỗi;
7. Kế hoạch bàn giao dữ liệu/sản phẩm, lưu trữ hồ sơ và ngoại lệ;
8. Cách kiểm chứng từ request thực tế, không chỉ từ status database.

### 5.2. Tránh xóa quá sớm các bằng chứng cần thiết

Xóa guest record hoặc xóa mapping IdP ngay từ đầu có thể làm mất mối liên hệ để tìm grants còn sót. Thông thường nên **đình chỉ truy cập và ghi inventory trước**, sau đó revoke quyền, đối soát, cuối cùng mới xem xét xóa/ẩn danh theo retention policy. Tình huống sự cố có thể cần cô lập nhanh hơn nhưng vẫn bảo vệ audit trail.

## 6. Bước 1: đóng nguồn cấp quyền mới

Đây là bước thường bị bỏ qua: IAM đã thu hồi grants cũ, nhưng **JIT login, SCIM sync, invitation hoặc một job provisioning đang chạy** lại tạo bản ghi hoặc quyền mới từ cấu hình quan hệ còn active.

### 6.1. Áp dụng trạng thái quan hệ

Khi contract/relationship hết hạn hoặc được đình chỉ, policy cần từ chối **mọi yêu cầu cấp grant mới phụ thuộc vào quan hệ đó**. Điều này có thể được thể hiện bằng trạng thái terminated/suspended hoặc cờ eligibility được policy hiểu rõ. Cần xác định liệu việc **chặn cấp mới** có xảy ra đồng thời với **chặn mọi truy cập hiện hữu** hay không; với offboarding khẩn cấp cần ưu tiên chặn sử dụng ngay.

Ví dụ logic:

~~~text
mayProvision(principal, grantRequest):
    if principal.identityStatus != "active": DENY
    relationship = findRelationship(grantRequest.relationshipId)
    if relationship.status != "active": DENY
    if now >= relationship.expiresAt: DENY
    if not approvedSponsorAndResourceOwner(grantRequest): DENY
    if not withinAllowedPartnerScope(principal, grantRequest): DENY
    ALLOW
~~~

Mã giả chỉ minh họa. Chính sách cần được thực thi ở **mọi đường tạo quyền có liên quan**, không chỉ màn hình mời guest: SCIM, JIT, script quản trị, API delegated administration, import CSV hoặc role assignment tự động.

### 6.2. Chặn vòng provisioning ngược

Một nguồn SCIM bên B có thể tiếp tục gửi user/group sang A trong lúc A đã đánh dấu relationship terminated. Nếu A chỉ xóa user nhưng chưa sửa policy/mapping, bản ghi có thể tái xuất hiện. Giải pháp:

- Đánh dấu nguồn provisioning và đối tượng liên kết ở trạng thái không còn đủ điều kiện;
- Dừng hoặc giới hạn mapping phụ thuộc relationship đã kết thúc;
- Xử lý idempotent sự kiện deactivate/remove group và dữ liệu đến trễ;
- Chống tác vụ add user hoặc add group tái kích hoạt grant đã revoked;
- Ghi nhận cả kết quả **refused provisioning** để phát hiện tích hợp chưa được dừng;
- Phối hợp với đối tác B đóng kết nối SCIM khi toàn bộ phạm vi dùng chung được phép kết thúc.

Một **SCIM client chung** có thể phục vụ nhiều đối tác hoặc hợp đồng; không thu hồi thiếu kiểm tra nếu sẽ làm hỏng luồng hợp lệ khác. Khi shared connector không thể ngừng hoàn toàn, dùng chính sách theo relationship và lọc phạm vi dữ liệu.

### 6.3. Delegated admin

Nếu B từng được quyền tự mời nhân sự hoặc quản lý nhóm trong tenant-B, phải chặn **delegated administration** tương ứng khi quan hệ không còn active. Chặn login user mà quên quyền của API quản trị hoặc một quản trị viên khác có thể cho phép B cấp lại tài khoản.

## 7. Bước 2: thu hồi danh tính con người và quyền tài nguyên

### 7.1. Human principal: guest, external user và federated user

Danh tính con người có thể biểu diễn bằng local guest trong IdP A, account trong ứng dụng SaaS hoặc local principal liên kết với IdP B qua OIDC/SAML. Offboarding cần tìm **mọi bản ghi tương ứng** và những grants phát sinh từ quan hệ đã kết thúc.

Thao tác thường gồm:

1. Vô hiệu hóa local guest/principal nếu không còn quyền hợp lệ nào khác;
2. Nếu principal còn quyền theo quan hệ khác, chỉ thu hồi membership/grants theo relationship đã kết thúc;
3. Gỡ các group/role/resource assignments phụ thuộc hợp đồng;
4. Thu hồi invitation chưa được chấp nhận và ngăn invitation cũ trở thành quyền mới;
5. Gỡ quyền delegated admin hoặc elevated roles;
6. Xử lý truy cập SaaS, kho mã, dự án, cơ sở dữ liệu, cloud console, VPN/ZTNA và các share trực tiếp;
7. Đối soát tất cả kết quả, bao gồm các hệ thống không liên thông IAM.

Không đồng nhất việc **disable user** với **delete account**. Disable giúp ngăn nhiều hình thức truy cập nhưng không luôn xử lý group, session, token hoặc chia sẻ trực tiếp; delete có thể ảnh hưởng lịch sử kiểm toán và không chứng minh quyền ở hệ thống khác đã bị thu hồi.

### 7.2. Gỡ quyền theo nguồn (grant provenance)

Giả sử nhân viên U của B có:

- grant đọc dự án P42 từ hợp đồng CTR-P42;
- grant bình luận P51 từ hợp đồng CTR-P51;
- một share tài liệu được chủ ứng dụng tạo thủ công.

Khi CTR-P42 kết thúc, IAM phải gỡ grant P42 và mọi quyền bổ sung phụ thuộc P42; grant P51 chỉ giữ nếu hợp đồng P51, sponsor và resource owner còn xác nhận. Share thủ công cần được phân loại: nếu phục vụ P42 thì thu hồi; nếu không rõ nguồn phải review, không tự bỏ qua.

### 7.3. Không quên phiên và token

**Phiên IdP**, **phiên ứng dụng**, **refresh token** và **access token** có vòng đời riêng:

| Đối tượng | Có thể vẫn hoạt động sau disable ở nguồn? | Biện pháp liên quan |
|---|---|---|
| IdP session của B | Phụ thuộc hành động tại IdP B | Nhờ B disable/terminate nếu có hỗ trợ |
| Session cookie của ứng dụng A | Có | Invalidate session, re-check entitlement |
| Refresh token | Có thể | Revoke/rotate/xóa tại nơi phát hành và ứng dụng |
| JWT access token tự chứa | Có thể đến expiry | TTL phù hợp, kiểm tra quyền động hoặc token denylist tùy kiến trúc |
| Reference token | Phụ thuộc introspection | Kiểm tra active và trạng thái grant |
| Session đặc quyền PAM | Có thể | Kết thúc phiên, revoke credential/checkout |

**Thu hồi quyền ngay** chỉ đạt được khi các điểm thực thi có cơ chế từ chối phù hợp. Nếu resource server chỉ xác minh chữ ký JWT đã phát hành mà không kiểm tra trạng thái hiện tại, token có thể tiếp tục dùng đến expiry. Không hứa zero residual window nếu kiến trúc chưa đáp ứng.

### 7.4. Truy cập đặc quyền và hạ tầng

Đối với quyền production hoặc quản trị hệ thống:

- Thu hồi JIT elevation, tài khoản đặc quyền, group administrator và grants quản trị cloud;
- Kết thúc phiên qua PAM/jump host/remote support nơi có hỗ trợ;
- Revoke SSH certificate/key hoặc quyền vào host, repository, CI/CD pipeline;
- Xử lý tài khoản chia sẻ/vault checkout theo chính sách, rotate credential khi bí mật đã được chia sẻ;
- Kiểm tra hiệu lực của quyền đã gỡ tại chính host/API/hệ thống đích;
- Ghi lại tình trạng đang có tác vụ bảo trì chưa hoàn tất để chuyển giao an toàn.

Với hệ thống cũ bắt buộc dùng tài khoản kỹ thuật chung, chỉ xóa một guest không đủ. Cần tìm người đã nhận credential, quyền trên host và trạng thái secret; ưu tiên chuyển sang mô hình identity riêng với PAM trong dài hạn.

## 8. Bước 3: thu hồi workload, service account và tích hợp

Một lỗi nghiêm trọng là hoàn tất offboarding con người nhưng vẫn để API client của B hoạt động. Workload thường **không có sự kiện nghỉ việc từ HR** và có thể chạy mỗi phút suốt nhiều năm.

### 8.1. Các nhóm workload thường gặp

| Workload / credential | Nơi tồn tại | Hành động Leaver |
|---|---|---|
| OAuth 2.0 client | Authorization server | Disable/delete registration theo policy, revoke grants và refresh token nếu có |
| API key | API gateway/ứng dụng | Revoke key, kiểm tra request bị từ chối |
| Service account | Cloud IAM, SaaS, OS | Disable identity/role assignments, quản lý token/key |
| mTLS client certificate | PKI/gateway/mTLS trust store | Revoke/distrust chứng thư hoặc mapping, tùy khả năng hệ thống |
| Workload federation trust | IAM/STS | Gỡ trust mapping hoặc audience/subject policy dành riêng B |
| CI/CD credential | DevOps/secret manager | Gỡ deploy permission, rotate secret, revoke token |
| Webhook subscription | App/integration broker | Disable endpoint/secret, kiểm tra không còn phát sự kiện |
| Data synchronization job | Scheduler, ETL/queue | Dừng job, xóa quyền đọc/ghi, xử lý dữ liệu đọng |
| Long-lived shared secret | Nhiều dịch vụ | Rotate nơi dùng chung; không làm gián đoạn đối tác hợp lệ khác |

### 8.2. OAuth token không đồng nghĩa access control hoàn chỉnh

Giả sử client B được cấp OAuth access token với scope orders.status.write. Khi B hết hợp đồng, API A phải từ chối các thao tác mới **dù token còn thời hạn**, nếu chính sách yêu cầu thu hồi ngay và resource server có thể đánh giá trạng thái relationship. Một token đúng chữ ký, audience và scope vẫn không có lý do đọc/ghi dữ liệu khi hợp đồng bị terminated.

Tại resource server:

~~~text
authorizePartnerClient(token, resource, action):
    validateTokenAndClientBinding(token)
    client = lookupTrustedClient(token.clientId)
    if client.status != "active": DENY
    relationship = lookupRelationship(client.relationshipId)
    if relationship.status != "active": DENY
    if now >= relationship.expiresAt: DENY
    if resource.tenantId != client.tenantId: DENY
    if action not in client.approvedActions: DENY
    if not tokenAllowsAction(token, action): DENY
    ALLOW
~~~

Mã giả giả định resource server được cung cấp dữ liệu trạng thái đủ tin cậy. Trong thực tế cần xác minh issuer, chữ ký/introspection, audience, expiry, scope và cách liên kết client ID phù hợp với loại token/ủy quyền. **Không tin chuỗi clientId do request body tự khai**.

### 8.3. Rotation và thu hồi an toàn

Nếu B và C từng cùng dùng một credential (thiết kế cần tránh), thu hồi key chung có thể làm hỏng C. Cần xây dựng client/secret riêng theo partner, environment và mục đích. Trong lúc xử lý legacy shared secret:

1. Xác định mọi bên sử dụng và người chịu trách nhiệm;
2. Cấp credential thay thế cho các workload còn hợp lệ;
3. Chuyển các consumer đó sang credential mới qua quy trình có kiểm chứng;
4. Revoke secret cũ và kiểm tra B bị từ chối, C vẫn hoạt động;
5. Ghi ngoại lệ và kế hoạch loại bỏ cấu hình dùng chung.

Trong sự cố key bị lộ, có thể phải thu hồi lập tức và chấp nhận gián đoạn có kiểm soát. Việc thay thế secret là hành động kỹ thuật **khác với** việc xử lý nghĩa vụ dữ liệu/hợp đồng.

## 9. Bước 4: xử lý federation, SSO và SCIM

### 9.1. Trust kỹ thuật chỉ được gỡ khi đúng phạm vi

Trong B2B federation, A có thể tin cậy IdP của B qua **OIDC** hoặc **SAML**. Offboarding toàn bộ B có thể bao gồm ngắt cấu hình issuer/entityID, client registration, signing certificate trust, domain routing, account linking hoặc federation broker mapping.

Nhưng không nên coi **một issuer = một partner = một hợp đồng**. Một IdP chung có thể xác thực nhiều tổ chức; một partner có thể có nhiều hợp đồng hoặc IdP. Nếu chỉ CTR-P42 kết thúc nhưng CTR-P51 vẫn active, gỡ toàn bộ IdP trust B có thể làm gián đoạn P51. Cần:

- Xác định tham chiếu từ từng relationship đến trust profile;
- Vô hiệu hóa relationship/grants trước để chặn quyền cụ thể;
- Gỡ trust cấp partner chỉ khi không còn quan hệ hợp lệ phụ thuộc;
- Không xóa cấu hình shared broker/SCIM connector đang phục vụ bên khác;
- Kiểm thử đăng nhập/tài nguyên cho những quan hệ cần giữ.

### 9.2. SSO không phải deprovisioning

Một người B đăng nhập qua IdP B bằng OIDC/SAML. A nhận và xác minh bằng chứng danh tính; sau đó cấp phiên ứng dụng của A. **Khóa IdP B không tự xóa guest A hoặc thu hồi mọi phiên A.** Ngược lại, A vô hiệu hóa local membership có thể chặn quyền tài nguyên trong khi B vẫn đăng nhập được vào IdP của mình, điều đó là bình thường.

Đặc biệt, **OIDC ID token dành cho xác thực của ứng dụng**, không phải bearer access token dùng chung cho API. Việc revoke OAuth access token, refresh token hoặc session cần áp dụng đúng công cụ/issuer/resource server. SAML Single Logout và các chuẩn logout khác có giới hạn hỗ trợ theo sản phẩm; không mặc định logout xuyên toàn bộ hệ thống nếu chưa kiểm thử.

### 9.3. Đóng provisioning trước khi xóa liên kết

Với SCIM và JIT provisioning, cần chặn tái tạo user/grant từ B sau offboarding. Có thể:

- Chuyển relationship sang trạng thái không đủ điều kiện provisioning;
- Đánh dấu user active=false/gỡ group tại những đích có hỗ trợ SCIM;
- Xử lý kết quả partial failure, retry và mapping trễ;
- Thu hồi provisioning credential riêng của B nếu không còn hợp đồng dùng chung;
- Vô hiệu hóa invitation/link cũ và policy JIT vốn tự tạo guest;
- Đối soát những principal được tạo sau thời điểm cutover.

### 9.4. Khả năng đảo chiều sau offboarding

Nếu B quay lại hợp tác sau sáu tháng, không tự kích hoạt lại tất cả grants cũ chỉ vì email/user trùng. Nên coi đó là **Joiner mới hoặc Mover được phê duyệt**, xác minh pháp nhân/hợp đồng, owner, IdP mapping, quyền, thời hạn và credential; chỉ phục hồi những gì đang có nhu cầu hợp lệ.

## 10. Bước 5: bàn giao dữ liệu và nghĩa vụ lưu trữ

Partner offboarding không chỉ là câu chuyện tài khoản. Quan hệ hợp tác có thể liên quan tới tài liệu chia sẻ, đơn hàng đang xử lý, báo cáo, dữ liệu cá nhân, bản sao lưu, khóa mã hóa, webhook payload hoặc máy chủ chứa dữ liệu của hai bên.

### 10.1. Bốn hành động khác nhau

| Hành động | Ý nghĩa | Ví dụ |
|---|---|---|
| **Revoke access** | Ngăn đối tác tiếp tục dùng dữ liệu/hệ thống | Gỡ quyền đọc dữ liệu tenant-B |
| **Transfer/return** | Bàn giao dữ liệu hoặc tài sản theo thỏa thuận | Xuất kết quả dự án có kiểm soát cho owner A |
| **Retain** | Giữ dữ liệu/bằng chứng theo thời hạn được phép hoặc bắt buộc | Audit log, hồ sơ giao dịch, legal hold |
| **Delete/anonymize** | Xóa/ẩn danh dữ liệu khi có căn cứ và được phê duyệt | Dữ liệu sao chép không còn mục đích xử lý |

Không suy rằng **revoke account = delete data** hoặc **delete account = revoke mọi data share**. Một liên kết chia sẻ bên ngoài có thể vẫn tồn tại; dữ liệu trong bản sao lưu có quy trình và retention riêng. Nghĩa vụ giữ/xóa/hoàn trả phải được xác định bởi legal/privacy/data owner theo hợp đồng, chính sách và pháp luật có liên quan.

### 10.2. Checklist chuyển giao dữ liệu

- Xác định owner và mục đích của các tập dữ liệu do B tạo, nhận hoặc xử lý;
- Phân loại dữ liệu, phạm vi xuất/chuyển và người phê duyệt;
- Chặn các kênh đồng bộ tiếp tục truyền dữ liệu sau cutover;
- Đối soát những file share, external link, backup và data export tồn tại;
- Bảo toàn chứng cứ giao nhận, xác nhận xóa hoặc giữ lại theo chính sách;
- Không xóa các tài nguyên A cần tiếp tục vận hành chỉ vì B từng quản lý chúng;
- Hạn chế truy cập dữ liệu trong giai đoạn chuyển tiếp, nếu có, bằng grants mới được phê duyệt có thời hạn.

Nếu có nghĩa vụ lưu giữ phục vụ điều tra hoặc tranh chấp, việc xóa/ẩn danh có thể phải tạm hoãn theo quy trình được thẩm quyền phê duyệt. Tài khoản truy cập vẫn có thể bị khóa trong khi dữ liệu cần được giữ.

## 11. Kiểm chứng offboarding: từ requested đến verified

### 11.1. Trạng thái kỹ thuật và nghiệp vụ phải tách bạch

| Trạng thái ví dụ | Ý nghĩa | Có đủ để đóng yêu cầu? |
|---|---|---|
| Requested | Đã tạo yêu cầu thu hồi | Chưa |
| Authorized | Đã xác nhận đúng phạm vi và người duyệt | Chưa |
| Access blocked | Các điểm thực thi chính đang chặn truy cập mới | Chưa nếu còn mục tiêu chưa xử lý |
| Revocation applied | Hệ thống đích báo đã gỡ grant/credential | Chưa nếu chưa có kiểm chứng |
| Verification pending | Đang đối chiếu quyền dự kiến và thực tế | Chưa |
| Verified | Đã xác nhận các quyền thuộc phạm vi bị thu hồi, có bằng chứng | Có thể đóng nếu không còn nghĩa vụ khác |
| Exception open | Có ứng dụng/scope chưa xác minh hoặc không thu hồi được | Cần owner, biện pháp giảm rủi ro và theo dõi |

Một số tổ chức định nghĩa thêm trạng thái **contained**, nghĩa là truy cập nguy hiểm đã được chặn nhưng remediation chưa hoàn tất. Không được trình bày contained tương đương mọi quyền đã được xóa.

### 11.2. Đối soát desired state và actual state

**Desired state**: theo quyết định offboarding, relationship CTR-P42 terminated và không còn grants phụ thuộc nó.

**Actual state**: ứng dụng SaaS còn giữ share trực tiếp cho guest U; API client W đã disable nhưng refresh token hoặc endpoint phụ trợ chưa được kiểm tra.

Reconciliation cần tìm sai lệch:

~~~text
reconcileOffboarding(relationshipId):
    relationship = loadRelationship(relationshipId)
    expected = computeExpectedAccessAfterTermination(relationship)
    actual = queryTargetsForPrincipalsGrantsAndCredentials(relationshipId)

    differences = compare(expected, actual)
    for difference in differences:
        createRemediationTask(
            systemOwner=difference.owner,
            scope=difference.scope,
            risk=difference.risk
        )
    return verifyAgainAfterRemediation()
~~~

Đây là **mã giả**. Không phải mọi hệ thống có cùng API hoặc cùng mức nhìn thấy quyền. Khi không thể tự truy vấn, cần thu thập bằng chứng theo cách phù hợp: xuất ACL, kết quả chạy kiểm thử, xác nhận từ app owner hoặc nhật ký từ chối. Nêu rõ phần chưa kiểm chứng.

### 11.3. Kiểm thử âm tính và dương tính

Kiểm tra **đối tác bị thu hồi không còn quyền** nhưng cũng phải kiểm tra **đối tác khác còn quyền hợp lệ không bị ảnh hưởng**.

| Test | Kỳ vọng |
|---|---|
| User U của B đăng nhập mới sau cutover | Bị từ chối theo đúng phạm vi quan hệ bị offboard |
| User U dùng session cũ truy cập P42 | DENY tại backend khi grant P42 đã revoked |
| Token OAuth cũ của W gọi API P42 | DENY hoặc token không còn hiệu lực theo cơ chế triển khai |
| W xin token mới bằng client credential cũ | Bị từ chối nếu client đã bị disable |
| SCIM/JIT cố tạo lại guest của B | Không cấp quyền trái trạng thái relationship |
| Guest U truy cập P51 theo hợp đồng còn hợp lệ | ALLOW nếu scope P51 được giữ theo chính sách |
| User X của partner C dùng cổng chung | Vẫn được phép nếu C không nằm trong phạm vi offboard |
| Repo/CI/CD của B | Quyền triển khai hoặc đọc mã bị từ chối |
| Direct share và URL cũ của B | Không thể truy cập nội dung đã thu hồi |
| Một user A nội bộ vận hành hệ thống | Không bị thu hồi nhầm bởi quy tắc đối tác |

Đối với test bảo mật, chỉ dùng tài khoản/credential kiểm thử được phép và môi trường phù hợp. Không thử truy cập dữ liệu nhạy cảm của C ngoài quyền để xác minh; sử dụng fixture hoặc dữ liệu kiểm thử đại diện.

### 11.4. Bằng chứng đóng yêu cầu

Một hồ sơ offboarding nên trả lời được:

- Ai phê duyệt và thời điểm hiệu lực?
- Hệ thống/quan hệ nào nằm trong scope?
- Những principal, groups, clients và credentials nào đã xử lý?
- Các hệ thống đích đã trả kết quả gì, khi nào và bởi ai?
- Những request kiểm thử nào đã bị DENY?
- Những quyền hợp lệ ngoài phạm vi nào được kiểm tra vẫn ALLOW?
- Ngoại lệ chưa xử lý là gì, ai chịu trách nhiệm, kiểm soát tạm thời và hạn xử lý?
- Dữ liệu nào đã bàn giao/lưu/xóa theo phê duyệt?

Không cần ghi nội dung token bí mật vào log; lưu kết quả, ID tham chiếu và correlation ID đủ để truy vết.

## 12. State machine và trình tự thực hiện

~~~mermaid
stateDiagram-v2
    [*] --> Planned: Xác nhận sự kiện và phạm vi
    Planned --> Inventoried: Liệt kê người, máy, grants, trust, dữ liệu
    Inventoried --> Blocked: Khóa quyền và provisioning mới
    Blocked --> Revoking: Deprovision và thu hồi credential
    Revoking --> Verifying: Thu thập trạng thái hệ thống đích
    Verifying --> Remediating: Phát hiện sai lệch
    Remediating --> Verifying: Đã xử lý, đối soát lại
    Verifying --> Verified: Quyền thuộc phạm vi đã mất hiệu lực
    Verified --> Archived: Lưu bằng chứng, xử lý retention
    Archived --> [*]
~~~

Với sự cố khẩn cấp, bước **Blocked** có thể xảy ra trước khi inventory hoàn chỉnh; phần inventory, revoke và verification tiếp tục sau containment. State machine không phải giao thức bắt buộc, chỉ mô tả việc không nên chuyển thẳng từ request sang completed mà thiếu kiểm chứng.

### 12.1. Workflow nhiều hệ thống và lỗi từng phần

Offboarding có thể thành công ở IdP, thất bại ở SaaS và chưa nhận phản hồi từ API gateway. Thiết kế tốt phải:

1. Ghi trạng thái cho từng target, không chỉ một cờ success chung;
2. Retry có giới hạn và idempotent nơi phù hợp;
3. Không tái cấp quyền do event đến muộn hoặc retry sai;
4. Escalate khi lỗi liên quan quyền nhạy cảm;
5. Giữ giải pháp chặn tạm tại ingress/API nếu một target chậm xử lý;
6. Đối soát lại sau khi target phục hồi;
7. Thông báo sponsor về ngoại lệ chưa được xác minh.

### 12.2. Định danh và version của lệnh thu hồi

Vì nhiều sự kiện có thể chồng lên nhau, nên liên kết mỗi lệnh với partner ID, relationship ID, principal/grant ID, version và correlation ID. Nếu nhận một sự kiện cấp lại quyền cũ đến sau quyết định revoke, policy phải kiểm tra trạng thái mới nhất trước khi áp dụng.

Một nguyên tắc phổ biến là **không cho quyết định cũ ghi đè trạng thái bảo mật mới**. Cách thực thi có thể dùng optimistic concurrency, idempotency key hoặc event version theo khả năng nền tảng.

## 13. Emergency offboarding: cô lập khi có sự cố

### 13.1. Khi nào cần kích hoạt?

Ví dụ: credential của nhà cung cấp B bị rò rỉ; B bị tấn công, khả năng đối phương dùng token hiện có; có hành vi truy cập chéo tenant; hợp đồng bị đình chỉ khẩn cấp do vi phạm bảo mật; phát hiện một tích hợp B bị khai thác để tải dữ liệu trái phép.

Quyền kích hoạt, liên hệ và phạm vi phải được quy định trong incident response plan. Không mặc định sponsor đơn lẻ có toàn quyền chỉnh policy an ninh hoặc xóa dữ liệu.

### 13.2. Thứ tự ưu tiên

1. **Containment:** khóa relationship/identity/grants hoặc chặn tại gateway/PAM/IdP theo phạm vi để ngừng truy cập mới và thao tác nguy hiểm.
2. **Credential response:** revoke/rotate token, key, cert, client registration và secret có nguy cơ lộ, xử lý các workload liên quan.
3. **Session control:** ngắt phiên đang hoạt động ở nơi có hỗ trợ, kiểm tra JWT hay session còn thời hạn.
4. **Preserve evidence:** lưu log và chứng cứ phục vụ điều tra; không làm mất dữ liệu cần thiết.
5. **Scope confirmation:** rà soát các đối tác và dịch vụ dùng chung trust/credential để tránh ảnh hưởng ngoài ý muốn.
6. **Remediation and verification:** gỡ quyền thực tế, kiểm tra access policy và tổng hợp các bất thường.
7. **Controlled recovery (nếu có):** chỉ tái cấp quyền qua phê duyệt mới, không phục hồi mọi quyền theo snapshot cũ.

### 13.3. Tình huống shared infrastructure

B và C cùng sử dụng một broker OIDC hoặc một API gateway. Khi khóa B, không nên tự dừng cả gateway nếu có thể áp dụng rule theo partner/client. Nếu có credential thực sự dùng chung và đã bị lộ, rủi ro có thể buộc phải chặn rộng hơn; cần có thông báo và phương án khôi phục đối với những đối tượng hợp lệ bị ảnh hưởng.

### 13.4. Đánh giá tác động

Các hạng mục thường cần theo dõi:

- Truy cập API bị từ chối sau khi chặn;
- Workload còn có thể lấy token mới hoặc sử dụng token cũ không;
- Có dữ liệu được tải/xuất ngay trước thời điểm chặn hay không;
- Thay đổi cấu hình, quyền hoặc secret nào phát sinh từ tài khoản bị ảnh hưởng;
- Khả năng phục hồi vận hành và trách nhiệm thông báo liên quan.

Giới hạn lưu dữ liệu và quyền truy cập nhật ký theo chính sách. Kết luận xảy ra xâm nhập phải dựa vào chứng cứ, không suy từ một đăng nhập thất bại.

## 14. Offboarding một phần và quá trình hợp tác lại

### 14.1. Một đối tác, nhiều hợp đồng

Một công ty có thể vừa bán hàng cho A vừa bảo trì ứng dụng của A. Hai quan hệ này có tài nguyên và owner khác nhau. Khi hợp đồng bảo trì kết thúc:

- Thu hồi grants của nhóm hỗ trợ, quyền CI/CD, PAM, API client hỗ trợ;
- Giữ các quyền phân phối hàng hóa nếu hợp đồng đó còn active và được duyệt;
- Kiểm tra shared principals đã mất đúng grants bảo trì nhưng vẫn hoạt động trong vai trò phân phối;
- Không xóa cấu hình federation cần cho quan hệ còn lại;
- Rà soát những quyền không có provenance rõ, tránh mặc định thuộc hợp đồng còn hiệu lực.

### 14.2. Mover, Leaver và Joiner có thể giao nhau

Trong chuyển đổi nhà cung cấp, nhóm mới có thể đang được onboard trước khi nhóm cũ offboard để tránh ngắt dịch vụ. Phải giới hạn cửa sổ overlap, phân định owner, dữ liệu, quyền phê duyệt và điều kiện cắt quyền cũ. **Không lấy nhu cầu chuyển tiếp làm lý do giữ admin vô thời hạn**.

Khi B quay lại làm việc sau một thời gian, dùng **quy trình xác minh và phê duyệt lại**, không tự khôi phục roles, OAuth scopes và credentials cũ chỉ vì tên doanh nghiệp hoặc email giống trước.

### 14.3. Ngoại lệ có thời hạn

Có thể một workload phải tiếp tục gửi dữ liệu hoàn tất đơn hàng sau hợp đồng chính. Ngoại lệ cần:

1. Chủ sở hữu kinh doanh và resource owner duyệt rõ;
2. Tách grant/relationship chuyển tiếp ra khỏi quan hệ đã đóng nếu cần;
3. Giới hạn action, dữ liệu, token, tenant và thời hạn ngắn;
4. Theo dõi và kiểm chứng riêng, có ngày chấm dứt;
5. Được phản ánh như ngoại lệ có kiểm soát, không gọi offboarding toàn bộ đã verified khi vẫn có quyền hợp lệ còn sử dụng.

## 15. Audit, access review và KPI cho offboarding

### 15.1. Audit event cần có

| Nhóm sự kiện | Thông tin truy vết |
|---|---|
| Offboarding requested | Partner, relationship, lý do, nguồn, người duyệt |
| Scope/inventory captured | Danh sách principal, grants, clients, resource owners |
| Relationship disabled | Trạng thái cũ/mới, policy version, timestamp |
| User/guest deactivated | Principal, hệ thống đích, outcome |
| Group/role/share removed | Entitlement trước/sau, tenant, resource |
| Client/key/cert revoked | ID tham chiếu, owner, phương thức, thời gian |
| Federation/SCIM changed | Trust/mapping cũ/mới, ảnh hưởng tới quan hệ khác |
| Session/token handled | Cách thu hồi, giới hạn và hiệu lực |
| Verification completed | Kết quả test DENY/ALLOW, target, correlation ID |
| Exception opened/closed | Owner, rủi ro, biện pháp tạm, hạn và kết quả |
| Data retention/disposal | Phê duyệt, loại dữ liệu, đối tượng quản lý |

Hồ sơ cần chống sửa trái phép, bảo vệ dữ liệu cá nhân và tuân thủ thời hạn lưu giữ. Không lưu credential có thể sử dụng được trong bằng chứng; lưu checksum/tham chiếu khi cần xác nhận công việc.

### 15.2. KPI phản ánh chất lượng

| KPI | Cách hiểu |
|---|---|
| Time to block new access | Từ sự kiện hợp lệ đến khi điểm kiểm soát chặn truy cập mới |
| Time to verified revoke | Từ sự kiện đến khi các target trong scope xác nhận thu hồi |
| Residual access count | Số principal/grant/client còn quyền sau cutover |
| Offboarding coverage | Tỷ lệ ứng dụng/credential trong inventory được kiểm chứng |
| Reprovision after revoke | Số tài khoản hoặc quyền bị tái tạo trái phép |
| Long-lived credential remaining | Số secret/key/client chưa revoke hoặc chưa đổi |
| Partial failures and exceptions | Số target lỗi hoặc chưa có bằng chứng verified |
| False-positive impact | Số principal/đối tác hợp lệ bị chặn nhầm |
| Late lifecycle signal | Thời gian trễ từ thay đổi ở partner đến khi IAM A nhận được |

Không có một SLA mặc định cho mọi hệ thống; đặt mức ưu tiên theo rủi ro, mức nhạy dữ liệu và nghĩa vụ hợp đồng. Một yêu cầu hoàn tất nhanh trên dashboard nhưng thiếu coverage ở cloud/API không phải kết quả tốt.

## 16. Case study: kết thúc hợp đồng phân phối nhưng giữ hợp đồng hỗ trợ

Công ty A vận hành nền tảng B2B cho hai đối tác B và C. B đang có **hợp đồng phân phối CTR-P42** và **hợp đồng hỗ trợ kỹ thuật CTR-P51**; C có hợp đồng riêng CTR-C. B sử dụng chung IdP OIDC cho nhân viên thuộc cả hai dự án. Một API client W của B đồng bộ đơn hàng P42; một service account T hỗ trợ kiểm tra log P51.

### 16.1. Bản đồ trước khi offboard

| Chủ thể | Nguồn danh tính | Quan hệ phát sinh quyền | Quyền thực tế |
|---|---|---|---|
| U, nhân viên kinh doanh B | OIDC IdP B + guest A | CTR-P42 | Đọc đơn P42 trong tenant-B |
| V, kỹ sư hỗ trợ B | OIDC IdP B + guest A | CTR-P51 | Đọc log P51 và JIT production qua PAM |
| W, API client B | OAuth client riêng của B | CTR-P42 | Cập nhật trạng thái đơn P42 |
| T, workload hỗ trợ | Service account/workload identity | CTR-P51 | Đọc telemetry/log P51 |
| X, nhân viên C | SAML IdP C + local user A | CTR-C | Đọc báo cáo tenant-C |

Ngày 30/11, hợp đồng CTR-P42 hết hạn. Hợp đồng P51 tiếp tục ba tháng và C không bị ảnh hưởng.

### 16.2. Kế hoạch cutover

| Thời điểm tương đối | Công việc | Owner |
|---|---|---|
| Trước cutover | Xác minh điều khoản, inventory toàn bộ grants P42, client W, file share | Sponsor, IAM, app owner |
| Trước cutover | Kiểm tra W có dùng chung với P51 không; chuẩn bị dữ liệu đơn hàng cần bàn giao | API/data owner |
| Tại cutover | Đặt CTR-P42 terminated, khóa JIT/SCIM provisioning theo P42 | IAM |
| Tại cutover | Gỡ U khỏi group P42, thu hồi share và các grants của P42 | IAM/app owner |
| Tại cutover | Disable W, revoke credential và quyền trên API P42 | API/platform owner |
| Sau cutover | Xử lý session/token P42, đối soát app và kiểm thử quyền | IAM/Security |
| Sau cutover | Xác nhận V và T vẫn truy cập P51 đúng phạm vi; X của C vẫn hoạt động | App owner |
| Khi hoàn thành | Lưu bằng chứng và xử lý dữ liệu P42 theo chính sách | Sponsor/Legal/Data owner |

### 16.3. Những kiểm thử quyết định

**Kiểm thử 1 — User U:** U vẫn có thể xác thực tại IdP B, nhưng local membership P42 đã mất quyền. Một request đọc order P42 phải bị **DENY**. Nếu U có quyền P51 hợp lệ khác, quyền đó được đánh giá độc lập.

**Kiểm thử 2 — Client W:** W sử dụng token OAuth còn hạn để gọi API cập nhật đơn P42. Vì relationship CTR-P42 đã terminated, resource server phải **DENY** nếu policy hỗ trợ kiểm tra trạng thái hiện tại. W cũng không thể xin token mới sau khi client registration bị disable.

**Kiểm thử 3 — Kỹ sư V:** V vẫn thuộc CTR-P51, có role đọc log đúng phạm vi. A không được khóa toàn bộ IdP B hoặc xóa guest V chỉ vì hợp đồng P42 hết hạn.

**Kiểm thử 4 — Đối tác C:** X đăng nhập bằng SAML IdP C và đọc dữ liệu tenant-C bình thường. Điều này xác nhận cấu hình dùng chung tại A không bị chặn nhầm.

**Kiểm thử 5 — Chia sẻ trực tiếp:** Một tài liệu P42 từng được nhân viên A chia sẻ thẳng cho U. Nếu IAM chỉ gỡ group P42, U có thể còn quyền qua ACL đó. Reconciliation phải phát hiện và app owner phải revoke direct share.

### 16.4. Khi B chấm dứt toàn bộ quan hệ sau ba tháng

Khi CTR-P51 cũng kết thúc, cần thực hiện offboarding đầy đủ cho V, T, PAM và liên kết federation B nếu không còn relationship nào dùng chung. Bắt đầu bằng trạng thái quan hệ, thu hồi grants, xử lý workload và session, gỡ trust thích hợp, sau đó kiểm chứng các ứng dụng và dữ liệu. Không dùng bằng chứng từ đợt CTR-P42 để khẳng định toàn bộ B đã được offboard.

### 16.5. Bài học từ case study

Một quy trình tốt không chỉ chứng minh **người hết quyền đã bị từ chối**, mà còn chứng minh **người và workload còn có quyền hợp lệ không bị ảnh hưởng**. Điều này đặc biệt quan trọng khi nhiều hợp đồng dùng chung IdP, network gateway hoặc ứng dụng đa tenant.

## 17. Runbook thực hành: offboard một quan hệ B2B

Runbook dưới đây mô tả trình tự thao tác và tiêu chí kiểm tra, không phải lệnh sản xuất có thể chạy trực tiếp. Tên trạng thái và endpoint cụ thể tùy hệ thống.

### Giai đoạn A — Xác nhận và lập phạm vi

1. Nhận yêu cầu termination với partner_id, relationship_id, effective_at, nguồn sự kiện và approver.
2. Kiểm tra sponsor, resource owner, vendor/partner manager đã xác nhận đúng phạm vi.
3. Xác định shared IdP/SCIM/credential và các hợp đồng còn tồn tại.
4. Xuất danh sách human, workload, grants, sessions và ứng dụng đích chịu ảnh hưởng.
5. Đánh dấu các mục thiếu owner và hệ thống không thể xác minh tự động.

**Điều kiện chuyển bước:** đã biết rõ sẽ chặn quyền gì, giữ quyền gì và ai chịu trách nhiệm nếu lỗi.

### Giai đoạn B — Chặn sử dụng và provisioning

1. Đặt relationship vào trạng thái terminated/suspended tại policy và grant store.
2. Kiểm tra API/backend từ chối hành động thuộc relationship bị chặn.
3. Vô hiệu hóa invitations, JIT, delegated admin và SCIM grants phụ thuộc relationship.
4. Chặn các phiên đặc quyền đang hoạt động nếu thuộc scope cần thu hồi.
5. Theo dõi dấu hiệu một job cũ đang cố tái tạo quyền.

**Điều kiện chuyển bước:** không có đường cấp quyền mới trái trạng thái và các điểm thực thi trọng yếu đang từ chối quyền.

### Giai đoạn C — Thu hồi theo từng hệ thống

1. Gỡ membership, group và grants theo hợp đồng.
2. Vô hiệu hóa local guest/user chỉ khi không còn quan hệ hợp lệ khác.
3. Hủy session/refresh token nơi có hỗ trợ, xử lý access token theo khả năng resource server.
4. Disable service account, API client, key/certificate, webhook và workload trust liên quan.
5. Gỡ share, ACL, repository, CI/CD, VPN/ZTNA, cloud grants, data-access permissions.
6. Gỡ IdP trust/SCIM connector chỉ khi không còn phụ thuộc hợp lệ.

**Điều kiện chuyển bước:** mọi target đã báo applied hoặc có ngoại lệ rõ ràng và biện pháp containment tạm.

### Giai đoạn D — Đối soát và đóng

1. So sánh desired/actual access cho từng principal/client/grant.
2. Chạy các ca test DENY trên tài nguyên bị thu hồi.
3. Chạy các ca test ALLOW trên quan hệ hợp lệ còn lại để phát hiện false positive.
4. Giao remediation cho owner của target chưa hoàn tất và kiểm tra lại.
5. Lưu audit event, thời điểm, approvals, kết quả và giới hạn xác minh.
6. Xác nhận quyết định dữ liệu: return/retain/delete theo thẩm quyền.
7. Đóng yêu cầu khi đạt điều kiện verified hoặc ghi rõ exceptions chưa hoàn tất.

**Điều kiện hoàn thành:** không còn quyền thuộc phạm vi bị thu hồi tại các điểm thực thi được kiểm chứng và mọi ngoại lệ được quản lý minh bạch.

### Mẫu kế hoạch offboarding minh họa

~~~yaml
offboarding_request:
  request_id: "OFF-2026-042"
  partner_id: "partner-B"
  relationship_id: "CTR-P42"
  trigger: "contract_expired"
  effective_at: "2026-11-30T17:00:00Z"
  approved_by: "resource-owner-A9"
  sponsor_id: "sponsor-A17"
  mode: "planned"
  keep_relationships:
    - "CTR-P51"
  affected_principals:
    - "external-user-U"
    - "oauth-client-W"
  operations:
    - "block_new_provisioning"
    - "revoke_scoped_grants"
    - "terminate_relevant_sessions"
    - "disable_scoped_workloads"
    - "verify_downstream_access"
  verification:
    require_negative_access_tests: true
    require_unaffected_relationship_tests: true
    require_target_reconciliation: true
~~~

Đây là bản ghi ví dụ, không phải schema của một sản phẩm IAM. Định danh và thời gian đều minh họa. Trong triển khai thực tế phải hỗ trợ kiểm soát phiên bản, audit, phân quyền xem kế hoạch và xử lý idempotent.

## 18. Các anti-pattern cần tránh

| Anti-pattern | Hậu quả | Biện pháp phù hợp |
|---|---|---|
| Chỉ disable user tại IdP B | Local grants, sessions, API clients còn dùng được | Offboard tại A và hệ thống đích |
| Chỉ xóa guest, không tìm grants | Share/ACL còn sót, khó truy vết | Inventory, revoke, verify trước xử lý xóa |
| Coi hợp đồng B kết thúc nghĩa là xóa tất cả issuer chung | Partner/relationship hợp lệ khác bị gián đoạn | Phân biệt partner, contract, trust reference |
| Quên service account và OAuth client | Workload tiếp tục gọi API sau hợp đồng | Quản lý workload như principal riêng |
| Thu hồi API key nhưng bỏ qua webhook/queue | Dữ liệu vẫn được phát hoặc job còn chạy | Inventory toàn bộ integration surface |
| Chỉ gỡ group trung tâm | Quyền cấp thủ công ở app đích vẫn tồn tại | Downstream reconciliation |
| Không chặn JIT/SCIM trước khi xóa user | Tài khoản hoặc role được tạo lại | Relationship-based provisioning guard |
| Tin token còn hạn là quyền hợp lệ | JWT cũ có thể tiếp tục truy cập | Re-check policy/introspection/TTL phù hợp |
| Không xử lý credential dùng chung | Revoke gây gián đoạn C hoặc để B giữ secret | Tách và rotate credential có kiểm soát |
| Xóa toàn bộ log ngay khi offboard | Không thể kiểm toán/sự cố | Retention và bảo vệ chứng cứ |
| Báo completed ngay khi ticket đóng | Chưa có bằng chứng thực thi thực tế | Phân biệt requested, applied và verified |
| Không kiểm thử ALLOW cho người còn quyền | Chặn nhầm partner/tenant khác | Regression test ở phạm vi không bị thu hồi |
| Chỉ dùng last login để quyết định | Bỏ qua quyền nhạy cảm không thường xuyên dùng | Review hợp đồng, grants và workload |
| Không có owner cho lỗi thu hồi | Ngoại lệ tồn tại vô thời hạn | Remediation có người nhận và SLA |
| Tự khôi phục toàn bộ role khi đối tác quay lại | Tái xuất quyền thừa cũ | Joiner/phê duyệt mới, least privilege |

## 19. Câu hỏi tự kiểm tra và tình huống

**Câu 1.** Hợp đồng P42 của B kết thúc nhưng P51 vẫn hiệu lực. IAM có nên khóa toàn bộ IdP B?

**Trả lời:** Không mặc định. Cần thu hồi grants/relationships phụ thuộc P42, giữ P51 được phê duyệt và chỉ gỡ IdP trust khi không còn quan hệ hợp lệ sử dụng nó.

**Câu 2.** IdP B đã disable U. Có thể xem U chắc chắn không còn truy cập được A?

**Trả lời:** Không. Phiên ứng dụng, access token, local guest, group, ACL và quyền ở hệ thống đích của A có thể vẫn tồn tại. Cần chặn và kiểm chứng ở đúng điểm thực thi.

**Câu 3.** IAM đã xóa guest nhưng app tài liệu vẫn chia sẻ file trực tiếp với email cũ. Đây là vấn đề gì?

**Trả lời:** Quyền ứng dụng đích chưa được thu hồi, tức residual access. Cần đối soát direct share/ACL, gỡ quyền, xác minh request bị từ chối và ghi bằng chứng.

**Câu 4.** Tại sao phải khóa đường tạo quyền mới trước khi hoàn tất xóa grants?

**Trả lời:** SCIM/JIT hoặc các job cũ có thể tái tạo account/group/grant vừa bị thu hồi. Policy phải kiểm tra relationship và ngăn cấp mới trái trạng thái.

**Câu 5.** API client W của B vẫn có JWT hợp lệ sau khi hợp đồng hết hiệu lực. Làm sao xử lý?

**Trả lời:** Disable client, thu hồi credential/grants, kết thúc các token/phiên nơi hỗ trợ; resource server cần từ chối request theo tình trạng relationship và entitlement. Nếu chỉ xác minh JWT offline, phải xác định giới hạn thu hồi tới expiry và biện pháp giảm rủi ro.

**Câu 6.** Vì sao không xóa ngay mọi dữ liệu B từng xử lý?

**Trả lời:** Dữ liệu có thể thuộc A, có nghĩa vụ bàn giao/lưu giữ hoặc phục vụ điều tra và kế toán. Revoke quyền truy cập khác với return, retain và delete; quyết định dữ liệu thuộc owner có thẩm quyền và chính sách liên quan.

**Câu 7.** Làm sao chứng minh offboarding đã hoàn tất?

**Trả lời:** Có inventory và phạm vi, chứng cứ revocation từ hệ thống đích, kết quả test DENY cho quyền bị thu hồi, kết quả test ALLOW cho đối tác còn hợp lệ và không còn ngoại lệ trọng yếu chưa xử lý.

**Câu 8.** B và C dùng cùng một gateway. Chặn B có nên dừng toàn bộ gateway?

**Trả lời:** Nên áp dụng chặn theo partner/client/grant nếu hạ tầng hỗ trợ, tránh ảnh hưởng C. Nếu credential chung bị lộ buộc phải chặn rộng, cần quản lý gián đoạn và khôi phục có kiểm chứng.

**Câu 9.** Một OAuth client B có owner là nhân viên đã nghỉ việc từ trước. Điều gì còn thiếu?

**Trả lời:** Quản lý workload lifecycle và ownership. Phải xác định technical/business owner mới, quyền liên quan, hạn và credential; khi tích hợp chấm dứt phải revoke client chứ không chỉ xử lý guest của nhân viên cũ.

**Câu 10.** B trở lại sau sáu tháng và sử dụng email/issuer cũ. Có thể khôi phục grants trước đây không?

**Trả lời:** Không tự động. Cần xác minh hợp đồng, sponsor, nguồn danh tính, thời hạn và phê duyệt mới; chỉ cấp quyền đáp ứng nhu cầu hiện tại, tránh privilege creep.

## 20. Tổng kết thực hành

Partner offboarding thành công cần đạt **hai mục tiêu đồng thời**:

1. **Ngừng quyền không còn hợp lệ:** không còn đường cấp quyền mới, session/token/credential và grants nằm trong phạm vi chấm dứt phải bị xử lý tại điểm thực thi.
2. **Bảo toàn quyền và dữ liệu hợp lệ:** không khóa nhầm hợp đồng/đối tác khác, không phá bằng chứng audit hoặc dữ liệu có nghĩa vụ giữ lại, không làm gián đoạn workload đang được phê duyệt ở quan hệ độc lập.

Quy trình có thể được ghi nhớ bằng chuỗi:

**Xác minh sự kiện → định phạm vi → lập inventory → chặn truy cập/cấp mới → thu hồi người và máy → xử lý federation/session/token → đối soát → xác nhận → lưu bằng chứng.**

Trong **Joiner–Mover–Leaver**, partner offboarding là hình thức Leaver có phạm vi rộng, kéo theo nhiều identity và relationship. Sự phối hợp giữa **IdP, SSO, SCIM, RBAC/ABAC, PAM, service account, sponsor, resource owner và audit** cho phép giảm quyền truy cập tồn dư một cách **có kiểm chứng**, thay vì chỉ đánh dấu một hợp đồng hoặc tài khoản là đã đóng.
