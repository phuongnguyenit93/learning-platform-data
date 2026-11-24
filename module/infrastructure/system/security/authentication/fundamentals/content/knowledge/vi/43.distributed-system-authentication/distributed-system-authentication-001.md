# Distributed identity (Danh tính trong hệ thống phân tán)

> **Chương:** Authentication trong distributed system  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Trọng tâm:** Mô hình hóa danh tính người dùng, workload và dịch vụ khi request đi qua nhiều thành phần, trust domain hoặc tổ chức; thiết kế cách xác minh, liên kết, truyền và thu hồi identity context; bảo đảm subject, actor, issuer, audience, tenant và quyền không bị nhầm lẫn trong hệ thống phân tán.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích distributed identity và phân biệt identity, authentication, federation, delegation và authorization.
2. Mô hình hóa principal cho người dùng, workload, service account, client và hệ thống bên ngoài.
3. Thiết kế trust domain, issuer, subject identifier và quy tắc liên kết danh tính ổn định.
4. Phân tích cách identity context đi qua gateway, service mesh, API và message broker.
5. Chọn cơ chế truyền danh tính phù hợp: access token, token exchange, mTLS, workload identity hoặc signed assertion.
6. Xác minh issuer, audience, subject, actor, tenant, scope, thời hạn và token profile.
7. Ngăn confused deputy, identity spoofing, cross-tenant access và privilege escalation khi delegation.
8. Quản lý identity lifecycle, provisioning, deprovisioning, credential rotation và revocation trên nhiều service.
9. Đánh giá consistency, cache, event propagation, clock skew và failure mode của identity state.
10. Xây dựng test matrix cho federation, propagation, revocation, tenant isolation và sự cố phân tán.

## 1. Distributed identity là gì?

**Distributed identity (danh tính trong hệ thống phân tán)** là cách biểu diễn, xác minh và sử dụng danh tính của một chủ thể khi request hoặc hoạt động đi qua nhiều service, ứng dụng, nền tảng và trust domain.

Trong một ứng dụng đơn giản, một server có thể vừa xác thực người dùng vừa kiểm tra quyền trong cùng một tiến trình. Trong hệ thống phân tán, request có thể đi qua:

- Browser hoặc mobile application.
- Identity Provider (IdP) và Authorization Server.
- API Gateway hoặc edge proxy.
- Backend service và service mesh.
- Message broker, worker và scheduled job.
- Database hoặc resource server.
- Hệ thống đối tác thuộc tổ chức khác.

Mỗi thành phần có thể có cách biểu diễn principal riêng, cache trạng thái riêng và thời điểm nhận thông tin khác nhau. Nếu không có mô hình identity thống nhất, một service có thể hiểu user ID là danh tính đã xác minh trong khi service khác coi đó chỉ là dữ liệu do caller khai báo.

### Ví dụ

Một học viên đăng nhập vào Learning Portal bằng IdP của trường. Portal gọi Enrollment Service để ghi danh khóa học. Enrollment Service lại gọi Billing Service để kiểm tra nghĩa vụ thanh toán.

Trong chuỗi này cần phân biệt:

- Học viên là subject của nghiệp vụ.
- Learning Portal là workload thực hiện request.
- IdP là issuer xác thực người dùng.
- Enrollment Service là service nhận request.
- Billing Service là downstream resource server.
- Tenant của trường xác định phạm vi dữ liệu và policy.

Billing Service cần biết request đến từ Enrollment Service có danh tính hợp lệ, đồng thời biết request đang thay mặt học viên nào và có được phép truy vấn khoản phí thuộc tenant tương ứng hay không.

### Identity không chỉ là username

Username, email hoặc tên hiển thị có thể thay đổi, trùng lặp hoặc được tái sử dụng. Một identity model cần identifier ổn định trong đúng namespace, cùng issuer/trust domain và quy tắc liên kết rõ ràng.

## 2. Phân biệt identity, authentication, federation, delegation và authorization

Các khái niệm liên quan nhưng không thể thay thế nhau:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Identity** | Chủ thể nào đang được biểu diễn? | User ID, workload ID, service principal. |
| **Authentication** | Bằng chứng nào xác minh chủ thể? | Password, passkey, certificate, signed token. |
| **Federation** | Vì sao hệ thống này tin danh tính do hệ thống khác xác minh? | RP tin assertion/token từ IdP đối tác. |
| **Identity linking** | Hai định danh ở các hệ thống có thuộc cùng một chủ thể không? | Tài khoản trường học được liên kết với tài khoản Learning Platform. |
| **Delegation** | Một actor được phép hành động thay mặt subject nào? | Learning API gọi Enrollment API thay mặt học viên. |
| **Authorization** | Principal được làm gì trên resource nào? | Chỉ đọc enrollment thuộc tenant đã cấp. |
| **Provisioning** | Identity và quyền được tạo, cập nhật hoặc thu hồi ra sao? | Đồng bộ thành viên từ directory/HR. |

Một token hợp lệ không tự chứng minh mọi claim bên trong có ý nghĩa giống nhau ở mọi hệ thống. Resource server phải hiểu issuer, subject namespace, audience, actor và policy của mình.

### Authentication thành công không đồng nghĩa quyền được cấp

Người dùng có thể được IdP xác thực thành công nhưng không còn membership trong tenant. Service có thể có certificate hợp lệ nhưng không có quyền gọi endpoint refund. Federation chỉ thiết lập quan hệ tin cậy về bằng chứng và issuer; authorization vẫn do resource owner quyết định.

## 3. Các loại principal trong hệ thống phân tán

Một hệ thống thường có nhiều loại principal:

| Principal | Đại diện cho | Ví dụ định danh |
| --- | --- | --- |
| Human user | Người dùng cuối. | Subject ID do IdP phát hành. |
| Workload | Process, pod, VM hoặc service đang chạy. | SPIFFE ID hoặc cloud workload identity. |
| OAuth client | Ứng dụng đã đăng ký tại Authorization Server. | Client ID. |
| Service account | Danh tính máy được cấp trong một nền tảng. | Namespace/service-account pair. |
| Organization/tenant | Phạm vi tổ chức hoặc khách hàng. | Tenant ID trong namespace của platform. |
| External partner | Hệ thống hoặc tổ chức liên kết. | Partner principal được map từ issuer ngoài. |
| Device | Thiết bị có danh tính được quản lý. | Device certificate hoặc managed device ID. |

Không nên dùng cùng một trường generic principal ID mà bỏ qua loại principal và issuer. Giá trị user-123 từ IdP A không nhất thiết là cùng chủ thể với user-123 từ IdP B.

### Principal cần namespace

Một định danh an toàn về mặt ngữ nghĩa thường cần ít nhất:

- Loại principal.
- Issuer hoặc trust domain.
- Subject identifier.
- Environment hoặc tenant context khi cần.
- Trạng thái và thời điểm hiệu lực.

Ví dụ, cặp issuer + subject thường ổn định hơn email. Trong OIDC, subject được định nghĩa trong phạm vi issuer; không nên so sánh sub từ hai issuer khác nhau như thể chúng cùng namespace.

## 4. Mô hình trust domain và issuer

**Trust domain** là phạm vi mà trong đó một hệ thống xác định nguồn danh tính, issuer và policy tin cậy. Một tổ chức có thể có nhiều trust domain cho production, staging, đối tác hoặc môi trường có mức bảo đảm khác nhau.

~~~mermaid
flowchart TD
    U["Người dùng"] --> IDP["IdP của trường"]
    W["Workload identity provider"] --> AS["Authorization Server"]
    IDP --> AS
    AS --> T["Token / assertion"]
    T --> G["API Gateway"]
    G --> A["Enrollment API"]
    A --> B["Billing API"]
    P["Partner IdP"] --> F["Federation trust"]
    F --> AS
~~~

### Trust không được suy ra từ tên gọi

Một issuer chỉ được tin khi được cấu hình và quản lý rõ. Không tin issuer chỉ vì hostname có chứa tên thương hiệu hoặc certificate chain đi tới một public CA.

Trust configuration cần xác định:

- Issuer identifier chính xác.
- Metadata/JWKS hoặc signing key source.
- Audience/resource server được phép nhận token.
- Loại token/assertion và profile.
- Subject namespace và mapping rule.
- Thuộc tính được phép dùng cho authorization.
- Thời hạn, key rotation và cách thu hồi trust.

### Tách trust theo môi trường

Không nên để token staging được chấp nhận ở production chỉ vì cùng một CA hoặc issuer family. Tách issuer, audience, key và trust bundle theo environment giúp giảm nhầm lẫn và blast radius.

## 5. Định danh ổn định và identity linking

Identity linking liên kết hai tài khoản hoặc định danh đã được xác minh. Ví dụ, một học viên liên kết tài khoản IdP trường với tài khoản Learning Platform đã tồn tại.

### Nguyên tắc liên kết

- Dùng định danh ổn định có issuer rõ ràng, không chỉ email hoặc display name.
- Yêu cầu chứng minh quyền kiểm soát cả hai tài khoản theo policy.
- Không tự động merge chỉ vì email giống nhau.
- Ghi nhận ai khởi tạo, thời điểm, nguồn và phương thức xác minh.
- Có notification và quy trình unlink/recovery.
- Chống account takeover trong lúc link hoặc unlink.
- Xử lý trường hợp một external subject được link nhầm với nhiều local account.

### Vì sao email không đủ?

Email có thể thay đổi, được tái cấp cho người khác hoặc có quy tắc alias khác nhau giữa nhà cung cấp. Nếu hệ thống dùng email làm khóa identity vĩnh viễn, việc đổi email hoặc tái sử dụng địa chỉ có thể dẫn đến account takeover hoặc liên kết nhầm.

### Mô hình liên kết

Một bảng identity link có thể lưu:

~~~sql
CREATE TABLE external_identity_link (
    local_subject_id VARCHAR(200) NOT NULL,
    issuer VARCHAR(500) NOT NULL,
    external_subject VARCHAR(300) NOT NULL,
    linked_at TIMESTAMP NOT NULL,
    link_status VARCHAR(30) NOT NULL,
    PRIMARY KEY (issuer, external_subject),
    UNIQUE (local_subject_id, issuer)
);
~~~

Schema chỉ minh họa. Hệ thống thực tế cần chính sách cho nhiều external identity cùng issuer, tenant-scoped linking, audit, encryption, deletion và unique constraint phù hợp. Không lưu token hoặc credential trong bảng link.

## 6. Identity context và propagation qua nhiều service

Khi một request đi qua nhiều service, mỗi hop phải biết danh tính nào được giữ lại, danh tính nào được tạo mới và ai chịu trách nhiệm xác minh.

### Context tối thiểu

Tùy kiến trúc, context có thể chứa:

- Issuer.
- Subject/principal.
- Actor hoặc client đã thực hiện request.
- Audience/resource.
- Tenant.
- Scope/permission.
- Authentication context/assurance khi cần.
- Token ID hoặc correlation reference.
- Thời điểm phát hành và hết hạn.
- Delegation chain hoặc actor context.

Không truyền tất cả thông tin người dùng cho mọi service. Chỉ chia sẻ thuộc tính cần cho quyết định ở downstream và theo nguyên tắc data minimization.

### Luồng qua nhiều hop

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Học viên
    participant P as Learning Portal
    participant AS as Authorization Server
    participant E as Enrollment Service
    participant B as Billing Service
    U->>P: Request với phiên đã xác thực
    P->>AS: Yêu cầu token cho Enrollment API
    AS-->>P: Access token audience Enrollment
    P->>E: Request + access token
    E->>E: Xác minh issuer, audience, subject, actor
    E->>AS: Token exchange cho Billing API nếu cần
    AS-->>E: Token audience Billing, quyền hẹp
    E->>B: Request + token mới
    B->>B: Xác minh token và tenant/resource
    B-->>E: Kết quả
    E-->>P: Kết quả nghiệp vụ
~~~

### Không forward mọi token

Một token có audience Enrollment API không nên được gửi nguyên vẹn tới Billing API. Token exchange hoặc cơ chế delegation phù hợp tạo token mới cho đúng downstream audience và scope.

Nếu không cần user delegation, service có thể dùng workload identity riêng. Quyết định phụ thuộc việc downstream cần biết actor cuối hay chỉ cần biết service caller.

## 7. Subject, actor và delegation chain

Một trong những lỗi nghiêm trọng là nhầm service đang gọi với người dùng mà service đại diện.

- **Subject:** chủ thể mà quyền hoặc dữ liệu đang nói tới.
- **Actor:** principal thực hiện hành động.
- **Client/workload:** ứng dụng hoặc service gửi request.
- **Issuer:** bên phát hành bằng chứng.
- **Audience:** resource server dự định nhận token.

Ví dụ, một học viên yêu cầu xuất bảng điểm. Learning API là actor thực hiện request tới Transcript Service; học viên là subject. Transcript Service cần kiểm tra Learning API được phép thực hiện loại export này và học viên có quyền với hồ sơ đó.

### Delegation cần giới hạn

- Subject phải được xác minh từ token hoặc context tin cậy.
- Actor phải được xác thực độc lập.
- Audience phải là downstream API cụ thể.
- Scope không được rộng hơn quyền subject/actor được phép ủy quyền.
- Delegation không tự động truyền quyền admin của service.
- Chain cần giới hạn độ sâu và thời hạn.
- Resource server phải kiểm tra tenant và ownership.

### Confused deputy

Confused deputy xảy ra khi service có quyền rộng bị lừa sử dụng quyền của nó cho một caller không đủ quyền. Ví dụ, Reporting Service có quyền đọc mọi tenant nhưng nhận tenant ID tùy ý từ request. Nếu không ràng buộc tenant với token/policy, caller có thể yêu cầu service đọc dữ liệu tenant khác.

Biện pháp là kiểm tra actor, subject, tenant và resource ở server-side; không tin tenant ID hoặc role do client tự gửi.

## 8. Token như một phương tiện mang identity context

Access token có thể mang identity context và quyền truy cập. Token không phải identity gốc; nó là bằng chứng do issuer phát hành theo một profile và mục đích cụ thể.

### Các claim quan trọng

- iss: issuer.
- sub: subject trong namespace của issuer.
- aud: audience/resource server.
- exp, nbf, iat: giới hạn thời gian.
- client_id hoặc azp: client/application theo profile.
- scope hoặc permission: quyền được cấp.
- tenant/org claim: phạm vi tổ chức nếu issuer có thẩm quyền phát hành.
- act hoặc actor-related claim: thông tin delegation theo profile.
- jti: token identifier nếu được sử dụng.
- cnf: confirmation/binding claim trong một số sender-constrained token.

Không phải mọi token có mọi claim trên. Resource server phải tuân theo token contract và profile đã thống nhất.

### Kiểm tra token tại mỗi trust boundary

1. Xác minh chữ ký hoặc introspection qua issuer tin cậy.
2. Kiểm tra issuer chính xác.
3. Kiểm tra audience đúng API.
4. Kiểm tra thời hạn và clock skew.
5. Kiểm tra token type/profile.
6. Xác định subject và client/actor theo schema.
7. Kiểm tra scope/permission cho action.
8. Kiểm tra tenant và resource ownership.
9. Kiểm tra revocation hoặc sender binding nếu yêu cầu.
10. Tạo request principal bất biến cho phần xử lý tiếp theo.

Không decode JWT rồi tin claim mà chưa xác minh chữ ký và issuer. Không chấp nhận ID token như access token chỉ vì cả hai có định dạng JWT.

## 9. Federation giữa nhiều IdP và tổ chức

Federation cho phép một hệ thống tin cậy kết quả xác thực hoặc thuộc tính do một IdP khác phát hành theo thỏa thuận.

Ví dụ, Learning Platform chấp nhận login từ IdP của nhiều trường đại học. Mỗi IdP có issuer, subject namespace, signing keys và thuộc tính khác nhau.

### Federation trust cần xác định

- Issuer được chấp nhận.
- Metadata/signing key được phân phối và cập nhật thế nào.
- Audience và recipient.
- Subject mapping.
- Authentication context và assurance.
- Attribute release policy.
- Tenant mapping và membership source.
- Key rotation, incident response và trust termination.

### Không đồng nhất assertion giữa các IdP

Một claim role=student từ IdP A không nhất thiết có cùng ý nghĩa với role=student từ IdP B. Cần mapping theo issuer, tenant, attribute semantics và contract. Không tin thuộc tính tùy ý chỉ vì nó nằm trong assertion có chữ ký hợp lệ.

### OIDC và SAML

- OIDC thường dùng ID token cho authentication result tại client và access token cho resource API.
- SAML assertion mang subject, conditions, audience và attributes theo protocol.
- Cả hai cần xác minh issuer, signature, audience, time và transaction binding.
- State/nonce/InResponseTo và replay detection giúp gắn response với đúng flow.
- Federation không thay thế authorization nội bộ của resource owner.

## 10. Workload identity trong hệ thống phân tán

Workload identity biểu diễn process, pod, VM, job hoặc service account. Nó giúp service xác thực lẫn nhau mà không phụ thuộc IP động hoặc shared secret dài hạn.

Các nguồn có thể gồm:

- Kubernetes service account và projected identity token.
- Cloud workload identity hoặc managed identity.
- SPIFFE/SPIRE.
- Certificate do internal CA cấp.
- OAuth client registration kết hợp private_key_jwt hoặc mTLS.

### Định danh workload

Một workload identity có thể biểu diễn bằng URI SAN/SPIFFE ID hoặc subject do cloud identity provider phát hành. Cần ánh xạ identity tới service principal và policy rõ.

Không cấp cùng một workload identity cho tất cả pod chỉ vì chúng nằm trong một namespace. Nếu workload bị compromise, identity dùng chung làm tăng blast radius và khó quy trách nhiệm.

### Authentication và authorization

mTLS xác minh peer trên connection. Access token có thể mang audience/scope cho API. Policy engine hoặc resource server quyết định service được gọi action nào. Các lớp này bổ trợ nhau, không thay thế nhau.

## 11. Gateway, service mesh và identity propagation

Gateway và service mesh có thể xác minh identity ở một hop rồi truyền context tới downstream. Đây là trust boundary quan trọng.

### Gateway pattern

- Gateway xác minh token từ client.
- Gateway xác thực backend qua mTLS.
- Backend xác thực gateway ở hop nội bộ.
- Identity context được truyền qua token exchange hoặc metadata có integrity.
- Backend không tin header từ Internet hoặc request không đi qua gateway đã xác thực.

### Header forwarding

Các header như X-User, X-Principal hoặc X-Client-Cert có thể bị giả mạo nếu backend tin trực tiếp từ caller. Nếu sử dụng header:

- Proxy xóa header đầu vào cùng tên.
- Proxy tạo lại giá trị từ identity đã xác minh.
- Backend chỉ nhận traffic từ proxy được xác thực.
- Có integrity protection và quy ước version/schema.
- Backend không có đường bypass không được kiểm soát.

### Service mesh

Service mesh thường dùng mTLS để xác thực workload giữa sidecar/ambient proxy. Authorization policy có thể dựa trên service identity, namespace và service account. Tuy nhiên, mesh identity không tự chứng minh user subject hoặc delegation. Ứng dụng cần một cơ chế riêng để truyền user context khi nghiệp vụ yêu cầu.

## 12. Identity propagation qua message broker và event

Không phải mọi request đều đồng bộ. Một service có thể phát event vào Kafka, RabbitMQ hoặc queue; worker xử lý sau đó.

### Những câu hỏi cần trả lời

- Event được phát bởi workload nào?
- Event đại diện cho actor/subject nào?
- Issuer nào xác minh danh tính?
- Consumer có được phép thực hiện hành động từ event không?
- Event có thể bị phát lại hoặc sửa đổi không?
- Identity context còn hiệu lực khi consumer xử lý sau vài phút/giờ không?

### Event envelope minh họa

~~~json
{
  "event_id": "evt-8f21",
  "event_type": "enrollment.requested",
  "issuer": "https://id.example.edu",
  "subject": "learner-204",
  "actor": "workload:learning-api",
  "tenant": "university-a",
  "issued_at": "2026-11-22T09:15:00Z",
  "correlation_id": "corr-72a1",
  "data": {
    "course_id": "course-18"
  }
}
~~~

Đây là envelope minh họa. Event không nên chứa bearer token, session cookie, password, OTP hoặc recovery secret. Consumer cần xác minh nguồn message qua broker ACL, signature hoặc transport identity theo kiến trúc; sau đó kiểm tra schema, event ID, tenant và quyền nghiệp vụ.

### Identity context trong event không phải credential vô hạn

Nếu event lưu subject và actor, đó là dữ liệu mô tả context tại thời điểm phát. Consumer phải quyết định policy dùng snapshot hay kiểm tra lại membership/account status tại thời điểm xử lý. Với thao tác nhạy cảm, có thể cần re-authorize hoặc xác minh trạng thái hiện tại.

## 13. Identity lifecycle và provisioning phân tán

Identity lifecycle bao gồm tạo, kích hoạt, cập nhật, đình chỉ, khôi phục và xóa danh tính cũng như quyền liên quan.

Trong hệ thống nhiều service, trạng thái có thể được đồng bộ qua provisioning protocol, event bus hoặc API.

### Vòng đời thường gặp

~~~mermaid
stateDiagram-v2
    [*] --> Pending
    Pending --> Active: Verify and provision
    Active --> Suspended: Security or lifecycle decision
    Suspended --> Active: Review and reinstate
    Active --> Deprovisioned: Membership or employment ends
    Suspended --> Deprovisioned: Approved removal
    Deprovisioned --> [*]
~~~

### SCIM và provisioning

SCIM có thể hỗ trợ đồng bộ user/group lifecycle giữa identity system và ứng dụng. Tuy nhiên, mỗi consumer cần xác minh nguồn provisioning và xử lý version/order của event. Không coi một request SCIM hợp lệ là quyền truy cập runtime cho mọi API.

### Deprovisioning

Khi user rời tổ chức:

- Thu hồi membership/role theo tenant.
- Vô hiệu hóa session và refresh token theo policy.
- Xử lý API key, passkey, device và external identity link.
- Đồng bộ tới RP và downstream service.
- Giữ audit và dữ liệu theo retention policy.
- Không xóa lịch sử nghiệp vụ nếu cần giữ theo quy định.
- Xác minh không còn account shadow hoặc service credential bị bỏ quên.

### Partial failure

Một service có thể nhận deprovision event trong khi service khác chưa nhận. Cần propagation SLA, retry, dead-letter queue, reconciliation và cơ chế deny nhanh cho thao tác nhạy cảm. Không giả định event bus đảm bảo mọi service cập nhật đồng thời.

## 14. Consistency, cache và revocation

Distributed identity có thể sai lệch tạm thời nếu token, membership hoặc account state được cache ở nhiều node.

### Các loại trạng thái

- Token validity và revocation.
- Account active/suspended/deprovisioned.
- Tenant membership và role.
- Workload identity và certificate status.
- Federation metadata và signing key.
- Delegation grant và consent.

### Cache trade-off

Cache giảm latency và dependency, nhưng làm chậm hiệu lực thay đổi. Cần định nghĩa:

- TTL theo loại dữ liệu và mức nhạy cảm.
- Event invalidation khi có thay đổi.
- Version hoặc epoch để nhận diện state mới.
- Fail-open/fail-closed khi identity provider không khả dụng.
- Reconciliation để phát hiện consumer bị lệch.
- Cơ chế deny khẩn cấp khi account hoặc workload bị compromise.

Không dùng một TTL chung cho mọi identity data. Membership có thể thay đổi ít thường xuyên hơn session revocation; certificate compromise cần containment nhanh hơn cache thông thường.

### Token đã phát hành

JWT access token có thể được xác minh offline tới exp nếu API không kiểm tra trạng thái online. Deprovisioning user hoặc revoke grant không tự động làm JWT đã phát hành mất hiệu lực ở mọi resource server.

Các lựa chọn:

- Access token TTL ngắn.
- Introspection hoặc online status check.
- Denylist theo jti/session reference.
- Subject/client version.
- Event-driven cache invalidation.
- Sender-constrained token.
- Revoke refresh token family để ngăn cấp token mới.

Phải mô tả rõ revocation SLA thực tế. Không tuyên bố revoke tức thời nếu API chỉ xác minh chữ ký cục bộ.

## 15. Tenant isolation và cross-domain mapping

Trong SaaS hoặc hệ thống nhiều tổ chức, cùng một người có thể có membership ở nhiều tenant. Một external identity có thể map tới local subject nhưng quyền và dữ liệu vẫn phải phân tách.

### Nguyên tắc

- Tenant là namespace/policy boundary, không chỉ là filter do client gửi.
- Token phải có tenant context được issuer tin cậy phát hành hoặc server xác định từ membership.
- API kiểm tra resource thuộc tenant được phép.
- Không dùng email domain để tự động cấp quyền tenant.
- Identity linking phải xác định tenant scope.
- Federation mapping không tự cấp membership.
- Admin của tenant A không được thay đổi identity/role ở tenant B nếu không có quyền cross-tenant riêng.
- Audit cần ghi tenant và principal context.

### Ví dụ

Một giảng viên có tài khoản tại hai trường. Subject của IdP có thể giống nhau hoặc khác nhau tùy hệ thống, nhưng Learning Platform cần biểu diễn membership riêng cho University A và University B. Quyền xem bảng điểm ở tenant A không tự mở quyền xem bảng điểm ở tenant B.

## 16. Threat model và lỗi phổ biến

| Rủi ro | Cách xảy ra | Biện pháp |
| --- | --- | --- |
| **Issuer confusion** | Token từ issuer không mong đợi được chấp nhận. | Allowlist issuer chính xác và trust configuration theo environment. |
| **Subject collision** | Cùng sub/email từ hai IdP bị coi là cùng user. | Namespace subject theo issuer và linking có xác minh. |
| **Audience confusion** | Token dành cho API A được dùng ở API B. | Audience validation tại mỗi resource server. |
| **Identity spoofing header** | Caller tự gửi X-User/X-Principal để mạo danh. | Header sanitization và authenticated proxy hop. |
| **Confused deputy** | Service có quyền rộng hành động thay caller thiếu quyền. | Actor/subject separation, delegation và resource authorization. |
| **Tenant confusion** | Tenant ID do client khai được tin trực tiếp. | Tenant mapping server-side và resource ownership checks. |
| **Privilege escalation** | Claim role/group từ issuer ngoài được map quá rộng. | Attribute mapping theo issuer và least privilege. |
| **Stale identity cache** | User đã bị suspend nhưng node vẫn dùng state cũ. | Versioning, invalidation, TTL và emergency deny. |
| **Token replay/theft** | Bearer token bị dùng lại từ nơi khác. | TTL, audience, revocation, mTLS/DPoP binding khi phù hợp. |
| **Delegation chain abuse** | Actor truyền tiếp quyền vượt quá phạm vi ban đầu. | Giới hạn scope, audience, depth và expiry. |
| **Event spoofing** | Consumer tin event không xác thực. | Broker ACL, producer identity, signature và schema validation. |
| **Out-of-order provisioning** | Event cũ ghi đè trạng thái mới. | Version monotonic, idempotency và reconciliation. |
| **Over-sharing attributes** | Identity context chứa dữ liệu cá nhân không cần thiết. | Data minimization, claim allowlist và privacy policy. |
| **Federation key compromise** | Signing key IdP bị lộ. | Key rotation, trust suspension, token/session response và incident runbook. |
| **Shadow identity** | Account hoặc credential còn tồn tại sau deprovisioning. | Inventory, periodic reconciliation và deprovision checks. |

## 17. Privacy và data minimization trong identity propagation

Identity context có thể chứa dữ liệu cá nhân như email, tên, nhóm, vai trò, tổ chức, thiết bị hoặc authentication history. Truyền toàn bộ dữ liệu tới mọi service làm tăng rủi ro và khó kiểm soát.

### Nguyên tắc

- Chỉ truyền claim cần cho downstream decision.
- Ưu tiên opaque subject reference thay vì email khi service không cần email.
- Dùng audience hẹp để token không bị chia sẻ rộng.
- Không đưa credential, OTP, session cookie hoặc private key vào event.
- Đặt retention cho identity logs và event.
- Pseudonymize identifier trong analytics khi phù hợp.
- Giới hạn quyền đọc audit và telemetry.
- Có quy trình xử lý access request, correction và deletion theo policy.

### Token không phải profile người dùng

Access token nên chứa context cần cho authorization, không phải bản sao toàn bộ user profile. Nếu service cần thêm dữ liệu, dùng API phù hợp với authorization riêng thay vì nhồi thêm claim nhạy cảm vào token.

## 18. Ví dụ thực tế: Learning Platform

Learning Platform phục vụ nhiều trường đại học và có các service Portal, Enrollment, Billing, Transcript và Notification.

### Đăng nhập và liên kết identity

1. Học viên đăng nhập qua IdP của trường.
2. Learning Portal xác minh issuer, signature, audience, nonce và thời hạn.
3. Portal liên kết external subject với local subject bằng quy trình đã xác minh.
4. Tenant membership được lấy từ nguồn provisioning tin cậy.
5. Portal tạo session và lưu authentication context phù hợp.

### Ghi danh khóa học

1. Portal nhận request của học viên và xác định subject/tenant.
2. Portal gọi Enrollment API với token audience đúng service.
3. Enrollment API xác minh token, actor, subject, scope và tenant.
4. Enrollment API kiểm tra membership và trạng thái khóa học.
5. Nếu cần kiểm tra Billing, Enrollment đổi token hoặc dùng service identity theo policy.
6. Billing API kiểm tra quyền truy vấn khoản phí thuộc đúng tenant.
7. Kết quả được trả về; correlation ID liên kết audit qua các hop.

### Học viên rời trường

1. Directory/SCIM source phát deprovision event có version.
2. Identity service cập nhật membership và trạng thái theo policy.
3. Session/refresh token được revoke hoặc giới hạn.
4. Enrollment và Transcript nhận event; cache được invalidate.
5. Billing giữ dữ liệu giao dịch theo retention nhưng từ chối truy cập mới không còn quyền.
6. Reconciliation phát hiện service nào chưa nhận event.
7. Audit ghi actor, source, version và kết quả từng consumer.

### Một service bị compromise

Nếu Notification Worker bị compromise, workload identity của nó bị revoke. Các service khác từ chối kết nối/token của principal đó. Notification Worker không thể dùng identity này để đọc Transcript hoặc thực hiện Billing action vì authorization policy phân tách theo service/action/resource.

## 19. Kiểm thử distributed identity

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Issuer đúng | Dùng token từ issuer được cấu hình. | Token được xác minh theo profile. |
| Issuer giả | Dùng token ký bởi key ngoài trust set. | Resource server từ chối. |
| Subject collision | Dùng cùng sub từ hai issuer. | Hai identity được phân biệt theo issuer namespace. |
| Identity link trùng | Link external subject đã thuộc local account khác. | Bị từ chối hoặc yêu cầu quy trình merge có xác minh. |
| Email thay đổi | Đổi email nhưng giữ external subject. | Identity link không bị chuyển sang người khác. |
| Audience sai | Dùng token của API A ở API B. | API B từ chối. |
| Actor/subject mismatch | Actor service hợp lệ nhưng subject không được phép. | Authorization từ chối. |
| Confused deputy | Caller yêu cầu service có quyền rộng đọc tenant khác. | Tenant/resource policy từ chối. |
| Header spoofing | Gửi X-User/X-Principal giả tới gateway/backend. | Header bị xóa/ghi đè; principal không bị giả mạo. |
| Gateway bypass | Gọi backend trực tiếp bỏ qua gateway. | Network/authentication policy chặn nếu kiến trúc yêu cầu. |
| Federation attribute abuse | IdP gửi role/group ngoài mapping. | Claim không được nâng thành quyền nội bộ. |
| Token exchange audience | Đổi token cho downstream API được phép. | Token mới có audience và scope đúng. |
| Token exchange escalation | Yêu cầu scope vượt quyền subject/actor. | Authorization Server từ chối hoặc cấp quyền hẹp. |
| Delegation chain depth | Tạo chuỗi actor vượt giới hạn. | Request bị từ chối theo policy. |
| Workload identity mismatch | Pod/service account ngoài allowlist xin token. | Broker/AS không cấp token. |
| mTLS peer identity | Kết nối bằng workload certificate hợp lệ và không hợp lệ. | Chỉ principal được tin cậy hoàn tất handshake. |
| Event producer spoofing | Gửi event từ producer không được phép. | Consumer từ chối hoặc cách ly event. |
| Duplicate event | Gửi cùng event ID nhiều lần. | Consumer idempotent; side effect chỉ xảy ra một lần. |
| Out-of-order event | Gửi version cũ sau version mới. | State mới không bị ghi đè. |
| Deprovision propagation | Suspend user rồi gọi API ở nhiều node. | Quyền bị thu hồi trong SLA đã định nghĩa. |
| Stale cache | Giữ cache membership cũ trong test. | Invalidation/version/TTL đưa state về đúng trong SLA. |
| IdP outage | Ngắt IdP khi request mới đến. | Không tạo identity mới thiếu bằng chứng; hành vi với session hiện có theo policy. |
| Revocation outage | Làm introspection/status service không khả dụng. | Fail policy rõ theo risk; không âm thầm bỏ kiểm tra. |
| Multi-tenant access | User thuộc tenant A truy cập resource tenant B. | API từ chối nếu không có membership/quyền riêng. |
| Privacy review | Kiểm tra token/event/log. | Không có secret hoặc claim cá nhân không cần thiết. |
| Key rotation | Thay signing key hoặc federation metadata. | Key mới được chấp nhận đúng lúc; key cũ retire theo overlap policy. |

## 20. Checklist thiết kế distributed identity

- [ ] Đã định nghĩa principal types: user, workload, client, tenant và partner.
- [ ] Subject được namespace theo issuer/trust domain.
- [ ] Không dùng email hoặc display name làm identity key duy nhất.
- [ ] Trust domain, issuer, audience và token profile được cấu hình rõ.
- [ ] Identity linking yêu cầu proof phù hợp và có audit.
- [ ] Tách subject, actor, client/workload và issuer.
- [ ] Delegation có audience, scope, expiry và chain depth giới hạn.
- [ ] Mỗi resource server xác minh token tại trust boundary của mình.
- [ ] Không forward bearer token tới downstream API sai audience.
- [ ] Gateway header được sanitize và chỉ tin từ proxy đã xác thực.
- [ ] Workload identity riêng theo service/environment khi cần.
- [ ] Event envelope không chứa credential hoặc token; producer được xác minh.
- [ ] Provisioning có version, idempotency, retry và reconciliation.
- [ ] Deprovisioning xử lý session, refresh token, membership, API key và external links.
- [ ] Cache có TTL/invalidation theo mức nhạy cảm.
- [ ] Revocation SLA và fail-open/fail-closed được định nghĩa.
- [ ] Tenant/resource authorization được kiểm tra server-side.
- [ ] Claim được tối thiểu hóa theo privacy policy.
- [ ] Audit correlation qua nhiều hop nhưng không log secret.
- [ ] Có runbook khi IdP, CA, signing key, broker hoặc workload identity bị compromise.
- [ ] Có test issuer/subject collision, audience, delegation, tenant isolation, event ordering và outage.

## 21. Tự kiểm tra

**Câu 1.** Distributed identity là gì?

**Đáp án:** Là cách biểu diễn, xác minh, liên kết và truyền danh tính qua nhiều service, ứng dụng, trust domain và tổ chức trong hệ thống phân tán.

**Câu 2.** Vì sao subject cần được namespace theo issuer?

**Đáp án:** Vì cùng một subject string từ hai IdP có thể đại diện cho hai người khác nhau. Issuer xác định namespace mà subject thuộc về.

**Câu 3.** Federation có tự cấp quyền nội bộ cho user không?

**Đáp án:** Không. Federation thiết lập trust về issuer và bằng chứng/thuộc tính; resource owner vẫn phải ánh xạ claim và quyết định authorization.

**Câu 4.** Vì sao không nên dùng email làm khóa identity duy nhất?

**Đáp án:** Email có thể đổi, tái sử dụng hoặc có alias. Dùng issuer + subject ổn định và identity-linking có xác minh giúp tránh liên kết nhầm.

**Câu 5.** Subject và actor khác nhau thế nào?

**Đáp án:** Subject là chủ thể mà request hoặc quyền đang đại diện; actor là principal thực hiện hành động. Service có thể là actor thay mặt một user subject.

**Câu 6.** Vì sao token cần audience?

**Đáp án:** Audience giới hạn resource server được phép nhận token, ngăn token dành cho API này bị dùng ở API khác.

**Câu 7.** Khi gateway terminate mTLS, backend có tự biết client gốc không?

**Đáp án:** Không. Backend xác thực gateway ở hop nội bộ. Client gốc chỉ được tin nếu gateway truyền identity đã xác minh qua cơ chế integrity-protected và backend chặn bypass.

**Câu 8.** Làm sao ngăn confused deputy trong service có quyền rộng?

**Đáp án:** Giữ actor/subject rõ, ràng buộc tenant/resource, giới hạn scope/audience và kiểm tra authorization theo caller thay vì dùng quyền service một cách mù quáng.

**Câu 9.** Vì sao deprovision event cần version và reconciliation?

**Đáp án:** Event có thể trùng hoặc tới sai thứ tự, consumer có thể lỗi hoặc offline. Version/idempotency ngăn state cũ ghi đè; reconciliation tìm service chưa đồng bộ.

**Câu 10.** Nếu JWT đã phát hành còn hạn nhưng user vừa bị deprovision, mọi API có tự từ chối ngay không?

**Đáp án:** Không nhất thiết. API chỉ xác minh chữ ký offline có thể tiếp tục chấp nhận tới exp. Cần TTL ngắn, introspection, denylist, version hoặc event invalidation và công bố revocation SLA.

## Ghi nhớ

**Distributed identity** là mô hình danh tính xuyên suốt nhiều service và trust domain. Hệ thống cần phân biệt user subject, workload/client actor, issuer, audience, tenant và delegation; không coi username/email hoặc một header do caller gửi là bằng chứng danh tính. Federation và identity linking cần namespace, trust configuration và quy trình xác minh rõ ràng.

Identity context phải được truyền tối thiểu, đúng audience và có integrity qua gateway, service mesh và message broker. Provisioning, deprovisioning, token revocation và cache cần version, retry, reconciliation cùng SLA thực tế. Mỗi resource server vẫn phải kiểm tra authorization theo action, resource và tenant. **Một danh tính chỉ có ý nghĩa khi issuer, subject, actor, trust boundary và quyền được hiểu nhất quán ở mọi nơi sử dụng nó.**
