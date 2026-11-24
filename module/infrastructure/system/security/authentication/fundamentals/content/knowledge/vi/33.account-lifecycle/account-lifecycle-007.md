# Credential cleanup — Thu hồi và dọn dẹp credential theo vòng đời tài khoản

Một nhân viên rời công ty. Bộ phận IT đã vô hiệu hóa tài khoản đăng nhập chính, nhưng người đó vẫn có thể truy cập hệ thống bằng một API key cũ, refresh token chưa bị thu hồi, chứng chỉ client còn hiệu lực hoặc passkey được đăng ký trên thiết bị cá nhân. Một tài khoản bị xóa khỏi giao diện không đồng nghĩa mọi đường truy cập đã biến mất. **Credential cleanup** là quá trình tìm, vô hiệu hóa, thu hồi và xử lý dữ liệu credential cùng các phiên/token liên quan khi chúng không còn được phép sử dụng.

Credential cleanup là một phần quan trọng của account lifecycle: tạo tài khoản, đăng ký credential, sử dụng, thay đổi, thu hồi, hết hạn, lưu giữ bằng chứng và xóa dữ liệu theo chính sách. Mục tiêu là bảo đảm mọi credential đều có chủ sở hữu, mục đích, phạm vi, thời hạn và quy trình kết thúc rõ ràng. Dọn dẹp không chỉ là xóa một bản ghi; hệ thống phải ngăn credential tiếp tục được chấp nhận ở mọi điểm xác thực và mọi bản sao có liên quan.

Bài học thuộc chương **Account lifecycle** của học phần **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Nội dung kết nối credential cleanup với mật khẩu, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản. Người học sẽ biết mô hình hóa ranh giới tin cậy, phòng chống credential tồn đọng, replay và lạm dụng quyền sau khi tài khoản thay đổi trạng thái.

## 1. Kết quả học tập

Sau bài này, người học có thể:

- Giải thích credential cleanup và phân biệt revoke, disable, expire, unlink, delete và destroy.
- Lập inventory cho mật khẩu, passkey, security key, OTP seed, recovery code, certificate, API key, access token, refresh token và session.
- Xác định chủ sở hữu, mục đích, phạm vi, nơi lưu và điểm kiểm tra của từng credential.
- Thiết kế quy trình cleanup cho offboarding, account deletion, credential compromise, rotation và tenant removal.
- Thu hồi session/token và xử lý độ trễ giữa các dịch vụ, cache, replica và resource server.
- Phát hiện orphaned credential, credential không rõ chủ, key không được quản lý và credential nằm ngoài hệ thống inventory.
- Bảo toàn audit evidence và tuân thủ retention/privacy khi xóa dữ liệu.
- Xử lý race condition, retry, idempotency và lỗi một phần trong quy trình cleanup phân tán.
- Thiết kế thông báo, recovery và kiểm soát ngăn người dùng/attacker tái tạo quyền trái phép.
- Viết tiêu chí kiểm thử để chứng minh credential đã bị thu hồi không còn được chấp nhận ở mọi điểm truy cập.

## 2. Credential cleanup là gì?

Credential là dữ liệu hoặc vật mang bí mật/khóa dùng để chứng minh quyền kiểm soát danh tính hoặc client. Tùy hệ thống, credential có thể là:

- Mật khẩu hoặc password verifier phía server.
- Passkey, public-key credential và private key tương ứng trên authenticator.
- Security key, smart card hoặc chứng chỉ client.
- TOTP seed, recovery code hoặc mã dự phòng.
- API key, client secret, workload identity hoặc khóa ký.
- Refresh token, access token và session cookie/identifier.

Credential cleanup là tập hợp hoạt động đưa credential ra khỏi trạng thái có thể sử dụng khi nó hết hạn, bị thu hồi, không còn cần thiết hoặc không còn thuộc về principal/tenant được phép. Quy trình cần xác định credential nào bị ảnh hưởng, điểm xác thực nào phải từ chối, dữ liệu nào được xóa và bằng chứng nào cần giữ.

### 2.1. Cleanup không chỉ là xóa dữ liệu

Một credential có thể đã được sao chép ra khỏi hệ thống gốc. Xóa bản ghi trong database không làm mất bản sao trong thiết bị, secret manager, CI/CD variable, backup hoặc máy chủ khác. Do đó, cleanup cần kết hợp:

1. Chặn credential ở nơi xác thực/ủy quyền.
2. Thu hồi hoặc vô hiệu hóa bản sao được quản lý.
3. Xóa dữ liệu không còn cần giữ theo retention policy.
4. Kiểm tra các phiên, token và quyền được tạo ra từ credential đó.
5. Ghi audit để chứng minh ai yêu cầu, hệ thống đã xử lý và điểm nào còn pending.

### 2.2. Cleanup là một quy trình vòng đời

Credential có thể đi qua các trạng thái:

~~~text
REQUESTED -> ACTIVE -> ROTATION_PENDING -> ACTIVE
                 \-> REVOKED
                 \-> EXPIRED
                 \-> DISABLED
                 \-> DESTROYED
~~~

Đây là mô hình khái niệm. Trạng thái thực tế cần được định nghĩa cho từng loại credential. Ví dụ, passkey có thể bị unlink khỏi tài khoản nhưng private key vẫn nằm trong authenticator; certificate có thể bị revoke trong PKI nhưng bản sao file certificate vẫn tồn tại; access token JWT có thể còn chữ ký hợp lệ đến khi hết hạn nếu resource server không kiểm tra trạng thái thu hồi.

## 3. Phân biệt các thao tác cleanup

Các thuật ngữ dưới đây không đồng nghĩa và cần được thể hiện rõ trong API, trạng thái dữ liệu và audit:

| Thao tác | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Disable | Tạm ngăn sử dụng theo policy; có thể bật lại nếu được phép | Tạm khóa một credential đang điều tra |
| Revoke | Thu hồi hiệu lực/ủy quyền; hệ thống phải từ chối credential từ thời điểm có hiệu lực theo SLA | Revoke refresh token family hoặc certificate |
| Expire | Credential hết hạn theo thời gian/điều kiện đã định | Access token hết exp, chứng chỉ hết validity |
| Unlink | Gỡ liên kết credential/external identity khỏi principal | Gỡ passkey hoặc SSO identity khỏi tài khoản |
| Delete | Xóa bản ghi hoặc dữ liệu theo policy | Xóa bản ghi API key đã revoke sau retention |
| Destroy | Hủy vật liệu khóa/bí mật theo cách không thể khôi phục trong phạm vi kiểm soát | Destroy key encryption key hoặc secret đã hết vòng đời |
| Rotate | Thay credential cũ bằng credential mới, có giai đoạn chuyển tiếp | Thay API key hoặc signing certificate |

Disable có thể chỉ là trạng thái tạm thời; revoke là quyết định chấm dứt quyền sử dụng; delete là xử lý dữ liệu lưu trữ. Một quy trình an toàn có thể revoke trước, xác minh mọi điểm kiểm tra đã từ chối, sau đó mới xóa dữ liệu theo retention. Không xóa thông tin cần thiết để ngăn credential cũ được tạo lại hoặc để điều tra sự cố.

## 4. Inventory: biết credential nào đang tồn tại

Không thể dọn dẹp thứ hệ thống không biết. Mỗi ứng dụng cần một inventory có thể trả lời:

- Credential thuộc principal, service account hay workload nào?
- Credential được dùng cho mục đích và tài nguyên nào?
- Ai tạo, ai phê duyệt, ai quản lý và ai có quyền thu hồi?
- Nó được xác minh ở những endpoint/service nào?
- Bí mật/khóa nằm ở đâu: authenticator, KMS, HSM, secret manager, database hay CI/CD?
- Ngày tạo, lần sử dụng gần nhất, thời hạn và trạng thái hiện tại?
- Có bản sao, bản backup, replica hoặc phụ thuộc nào?
- Khi thu hồi, dịch vụ nào cần nhận event và xác nhận hoàn tất?

### 4.1. Credential inventory mẫu

| Trường | Mục đích |
| --- | --- |
| Credential ID | Định danh nội bộ không phải secret |
| Principal/owner | User, service account, workload hoặc tenant sở hữu |
| Credential type | Password, passkey, certificate, API key, token... |
| Purpose/audience | API, ứng dụng, tenant hoặc hành động được phép |
| Created/last-used | Phát hiện credential cũ hoặc không còn sử dụng |
| Expires/review date | Thời điểm hết hạn hoặc cần đánh giá |
| Status | Active, disabled, revoked, expired, pending cleanup |
| Storage reference | Tham chiếu tới secret manager/KMS/HSM, không lưu secret thô |
| Verifier/validation points | Dịch vụ có trách nhiệm kiểm tra credential |
| Revocation reference | CRL/OCSP, token family, denylist hoặc trạng thái server |
| Owner/reviewer | Người hoặc nhóm chịu trách nhiệm |

Inventory không được lưu password, private key, OTP seed hoặc token thô chỉ để tiện quản lý. Dùng ID/reference, metadata tối thiểu và kho bí mật chuyên dụng.

### 4.2. Orphaned credential

Orphaned credential là credential không còn chủ sở hữu hoặc không rõ ai chịu trách nhiệm, ví dụ API key do nhân viên cũ tạo, certificate không có service owner, passkey của tài khoản đã bị disable hoặc refresh token gắn với client đã ngừng hoạt động.

Quy trình xử lý:

1. Tìm nguồn tạo và lịch sử sử dụng.
2. Xác định dependency và tác động nếu revoke.
3. Gắn owner tạm thời cho việc điều tra; không mặc định credential được phép tiếp tục.
4. Chọn revoke/disable theo rủi ro; với credential có dấu hiệu compromise, ưu tiên chặn ngay theo incident policy.
5. Kiểm tra mọi validation point và theo dõi lỗi dịch vụ sau thu hồi.
6. Giữ audit/reference cần thiết rồi xóa bí mật theo retention.

## 5. Cleanup theo loại credential

### 5.1. Password

Password thường không được lưu dưới dạng plaintext mà dưới dạng password hash/verifier có salt và thuật toán phù hợp. Khi người dùng đổi hoặc reset mật khẩu:

- Cập nhật verifier mới bằng quy trình xác minh/recovery phù hợp.
- Vô hiệu hóa password cũ ngay sau khi thay đổi commit.
- Thu hồi hoặc đánh giá lại session/refresh token đã được tạo bằng credential cũ theo policy.
- Kiểm tra password reset token và recovery transaction đang chờ; vô hiệu hóa token cũ.
- Gửi thông báo bảo mật tới contact đã xác minh theo chính sách.
- Không ghi password mới/cũ vào log, event hoặc audit.

Nếu tài khoản bị xóa, xóa password verifier theo retention policy sau khi đã khóa principal và xử lý phiên/token. Không giữ password hash vô thời hạn chỉ vì có thể hữu ích cho phân tích; nếu cần chống tái sử dụng, dùng cơ chế history có giới hạn và bảo vệ phù hợp.

### 5.2. Passkey và security key

Passkey/WebAuthn thường dùng public-key credential: server lưu credential ID, public key và metadata; private key nằm trong authenticator/credential provider. Khi người dùng xóa passkey:

- Đánh dấu credential ID là revoked/unlinked trong server-side credential store.
- Không chấp nhận assertion từ credential đó trong các lần xác thực sau.
- Thu hồi session/token theo policy nếu thao tác xảy ra sau compromise hoặc recovery.
- Xóa metadata không cần thiết theo retention; giữ audit event tối thiểu.
- Cập nhật số lượng authenticator và kiểm tra không khóa người dùng khỏi recovery ngoài ý muốn.

Xóa bản ghi public key phía server không xóa private key trên thiết bị. Tuy nhiên, nếu server không còn tin credential ID, assertion tương ứng phải bị từ chối. Khi thiết bị bị mất, người dùng có thể cần gỡ credential khỏi tài khoản và đăng ký lại trên thiết bị mới sau khi xác minh quyền kiểm soát.

### 5.3. TOTP seed và recovery code

TOTP seed là bí mật dùng tạo mã theo thời gian. Khi người dùng reset MFA hoặc thiết bị bị mất:

- Revoke seed cũ ở server và ngừng chấp nhận mã từ seed đó.
- Xóa hoặc hủy bản mã hóa seed theo key management policy sau khi revoke.
- Thu hồi recovery code đã dùng hoặc bộ code cũ khi tạo bộ mới.
- Chỉ hiển thị recovery code mới một lần theo quy trình an toàn; không lưu plaintext sau khi cấp.
- Audit ai thực hiện reset và bằng chứng recovery đã dùng.

Không cho phép người dùng tự thêm TOTP seed mới chỉ bằng một phiên yếu đang có nguy cơ bị chiếm. Việc thay MFA là thao tác nhạy cảm và có thể cần step-up bằng authenticator hiện tại hoặc recovery có bảo đảm.

### 5.4. Certificate và smart card

Certificate có thể xác thực client, người dùng hoặc workload. Cleanup cần:

- Revoke certificate tại CA/PKI theo quy trình và lý do phù hợp.
- Cập nhật CRL/OCSP hoặc cơ chế trạng thái tương đương.
- Đảm bảo verifier kiểm tra chain, validity, key usage, EKU, name binding và trạng thái revoke.
- Thu hồi private key trong HSM/KMS/keystore nếu hệ thống quản lý được.
- Thay certificate ở các client/service phụ thuộc; theo dõi giai đoạn overlap nếu rotation.
- Xóa file certificate/key khỏi nơi lưu không còn cần, backup và pipeline theo retention.

Revoke certificate không tự hủy private key đã xuất ra ngoài HSM. Nếu private key có thể đã bị sao chép, phải coi là compromise và thay key ở mọi nơi sử dụng.

### 5.5. API key và client secret

API key/client secret thường là bearer credential. Khi revoke:

- Đặt trạng thái revoked tại hệ thống xác thực API/key registry.
- Từ chối key ở mọi gateway/service đang xác minh.
- Xác định các ứng dụng, job, pipeline và secret store chứa bản sao.
- Rotate sang key mới nếu dịch vụ còn cần hoạt động; hỗ trợ overlap có thời hạn và giới hạn.
- Cập nhật secret manager/CI/CD variables, deployment và cấu hình client.
- Thu hồi key cũ sau khi xác minh key mới hoạt động; nếu key bị lộ, không kéo dài overlap ngoài incident policy.
- Xóa secret cũ và kiểm tra log/repository/artifact có chứa bản sao.

Không chỉ xóa key trong dashboard nếu API gateway vẫn cache trạng thái hoặc microservice có bản copy không được cập nhật.

### 5.6. Access token và refresh token

- Refresh token cần revoke theo token/family/grant và client; rotation reuse có thể yêu cầu revoke toàn bộ family.
- Opaque access token có thể bị từ chối ngay qua introspection hoặc trạng thái server-side nếu hạ tầng hỗ trợ.
- JWT access token tự xác minh có thể tiếp tục hợp lệ đến exp nếu resource server không kiểm tra trạng thái revoke. Dùng TTL ngắn, denylist/reference token, introspection hoặc sender-constrained token theo threat model.
- Thu hồi token không nhất thiết thu hồi session gốc; cần xử lý cả hai theo policy.
- Logout/disable principal cần xác định refresh grant, token family, device session và access token đang còn hiệu lực.

### 5.7. Session cookie và session record

Khi logout, account disable hoặc incident:

- Revoke session record phía server và cập nhật trạng thái phiên.
- Gửi cookie hết hạn với đúng tên, Domain và Path; xóa cookie phía browser.
- Thu hồi session liên quan ở các node/region và cache.
- Rotate session ID khi đăng nhập lại hoặc thay đổi mức xác thực.
- Xem xét SSO logout nếu có phiên ở IdP/RP khác; phạm vi logout cần được mô tả rõ.
- Xóa dữ liệu client-side liên quan theo policy, nhưng không coi xóa browser storage là server revoke.

## 6. Sự kiện kích hoạt credential cleanup

| Sự kiện | Phạm vi cleanup thường cần |
| --- | --- |
| Nhân viên nghỉ việc | Disable principal/membership, revoke sessions, refresh tokens, API keys/certificates do nhân viên sở hữu hoặc quản lý |
| Người dùng xóa tài khoản | Ngừng đăng nhập, thu hồi credential và phiên, xử lý liên kết danh tính/dữ liệu theo retention |
| Mất thiết bị | Gỡ passkey/device credential bị mất, revoke session/token trên thiết bị, kiểm tra recovery |
| Password/MFA bị compromise | Revoke credential cũ, reset/re-enroll, thu hồi phiên/token liên quan và điều tra |
| API key bị lộ | Revoke key, rotate, cập nhật secret stores/deployments và kiểm tra log |
| Certificate hết hạn/thu hồi | Cập nhật PKI status, thay certificate và kiểm tra verifier/cache |
| Tenant bị đóng | Thu hồi membership, tenant-scoped credential, integration và token liên quan |
| Dịch vụ ngừng hoạt động | Thu hồi workload identity, certificate, API key và secret không còn cần |
| IdP/federation connection bị gỡ | Ngừng tin issuer/connection, xử lý external identity mapping và session phát sinh |
| Phát hiện credential không rõ chủ | Điều tra dependency, assign owner và revoke theo rủi ro |

### 6.1. Offboarding nhân viên

Offboarding thường cần phối hợp HR, IAM, ứng dụng, cloud, endpoint management và chủ sở hữu dữ liệu:

1. Nhận sự kiện nghỉ việc từ nguồn có thẩm quyền và xác minh thời điểm hiệu lực.
2. Disable principal/SSO access theo lịch và policy.
3. Revoke session, refresh token, API key, personal access token, certificate và credential do nhân viên quản lý.
4. Xóa quyền tenant/group/role, service ownership và delegated access không còn hợp lệ.
5. Chuyển quyền sở hữu tài nguyên cần bàn giao; không chuyển credential bí mật của cá nhân sang người khác.
6. Thu hồi thiết bị/quyền truy cập endpoint theo quy trình quản lý thiết bị.
7. Kiểm tra job, webhook, CI/CD, automation và secret mà nhân viên từng tạo.
8. Ghi audit và xác nhận các hệ thống downstream đã hoàn tất.

Disable tài khoản trong directory không tự động tìm thấy API key nằm trong repository hoặc certificate được cài trên một máy chủ. Cần inventory và quy trình xác nhận ở từng hệ thống.

### 6.2. Account deletion

Xóa tài khoản có thể gồm nhiều quyết định khác nhau: chấm dứt đăng nhập, gỡ external identity, xóa profile, xóa dữ liệu nghiệp vụ, giữ dữ liệu theo nghĩa vụ pháp lý và xóa bản sao/backup theo chu kỳ. Hãy tách:

- Ngay lập tức chặn đăng nhập và revoke credential/session.
- Xóa hoặc ẩn danh dữ liệu sản phẩm theo yêu cầu và retention.
- Giữ audit evidence tối thiểu để chứng minh thao tác, ngăn gian lận hoặc đáp ứng nghĩa vụ hợp lệ.
- Xử lý dữ liệu tại processor/vendor và backup theo lịch đã công bố.
- Ngăn credential cũ hoặc external subject bị tái liên kết trái phép.

Không giữ toàn bộ dữ liệu cá nhân vô thời hạn dưới lý do “audit”. Cũng không xóa ngay mọi dấu vết nếu hệ thống cần giữ tombstone tối thiểu để ngăn tái sử dụng credential đã bị revoke.

## 7. Quy trình cleanup an toàn

Một quy trình có thể triển khai theo các bước:

1. **Trigger:** nhận yêu cầu từ account lifecycle, security incident, HR/SCIM, admin hoặc chính người dùng.
2. **Authorize request:** xác minh actor, quyền, phạm vi, lý do và thời điểm hiệu lực.
3. **Resolve scope:** tìm principal, tenant, credential, session, token, client và dependency liên quan.
4. **Freeze/disable:** ngăn tạo credential mới hoặc thay đổi liên quan trong khi cleanup nếu cần.
5. **Revoke at source:** thu hồi tại authority phát hành/quản lý credential.
6. **Propagate:** gửi event tới gateway, API, resource server, cache, replica và provider phụ thuộc.
7. **Verify denial:** thử xác thực bằng credential cũ tại mọi validation point quan trọng.
8. **Clean stored copies:** xóa secret/config/artifact không còn cần theo retention và key policy.
9. **Preserve audit:** ghi kết quả, lỗi, thời gian, actor và phần việc còn pending.
10. **Close/monitor:** chỉ đóng case khi các điểm bắt buộc đã xác nhận; tiếp tục giám sát phần không thể thu hồi tức thời.

~~~mermaid
flowchart TD
    A[Cleanup trigger] --> B[Authorize and scope]
    B --> C[Inventory credentials and dependencies]
    C --> D[Freeze new use / disable]
    D --> E[Revoke at issuing authority]
    E --> F[Propagate to validators, caches and replicas]
    F --> G{All critical validators deny old credential?}
    G -->|No| H[Retry / isolate / incident escalation]
    H --> F
    G -->|Yes| I[Delete copies per retention policy]
    I --> J[Preserve audit evidence]
    J --> K[Close and monitor]
~~~

### 7.1. Thứ tự ưu tiên khi compromise

Khi credential đang bị khai thác, ưu tiên ngăn sử dụng trước khi dọn dữ liệu:

- Revoke credential tại nguồn có thẩm quyền.
- Chặn session/token và quyền liên quan theo phạm vi.
- Cô lập client/service bị compromise nếu cần.
- Sau khi kiểm soát truy cập, điều tra bản sao và xóa secret bị lộ khỏi nơi lưu.

Không trì hoãn revoke chỉ để hoàn tất inventory hoàn hảo. Có thể thực hiện containment trước, sau đó mở rộng truy tìm dependency và xác nhận tác động.

### 7.2. Thứ tự ưu tiên khi offboarding có lịch

Với offboarding đã được lên lịch, cần phối hợp thời điểm hiệu lực và handover. Có thể chuẩn bị inventory, xác định dependency và staged rotation trước thời điểm rời tổ chức. Đến thời điểm hiệu lực, disable/revoke theo kế hoạch và xác nhận hệ thống downstream. Không thu hồi sớm đến mức làm gián đoạn công việc bàn giao nếu chưa được policy cho phép; cũng không để credential tiếp tục hoạt động sau thời điểm quyền kết thúc.

## 8. Thu hồi trong hệ thống phân tán

Credential có thể được kiểm tra ở nhiều nơi: API gateway, microservice, CDN, region, cache, offline verifier và bên thứ ba. Một lệnh revoke tại database trung tâm không đảm bảo mọi node lập tức biết trạng thái mới.

### 8.1. Revocation propagation

- Phát sự kiện revoke có event ID, credential reference, principal, scope, effective time và reason code.
- Xác thực producer/consumer và bảo vệ channel.
- Consumer cập nhật local registry/cache và xác nhận version đã áp dụng.
- Dùng retry, dead-letter queue và reconciliation để phát hiện consumer bỏ lỡ event.
- Có TTL cache phù hợp với SLA revoke; với credential rủi ro cao, kiểm tra trạng thái trực tuyến hoặc denylist.
- Theo dõi thời gian từ revoke commit tới khi mọi validator quan trọng từ chối.

### 8.2. Cache và replica

Cache có thể tiếp tục giữ trạng thái active sau khi primary đã revoke. Replica có độ trễ có thể trả trạng thái cũ. Cần:

- Invalidate cache theo event và có TTL giới hạn.
- Dùng version/revocation epoch để phát hiện dữ liệu stale.
- Với thao tác đặc quyền, fail closed khi không xác minh được trạng thái credential.
- Tránh cache positive validation lâu hơn thời gian chấp nhận được.
- Kiểm thử partition, consumer outage và recovery/replay event.

### 8.3. JWT và giới hạn revoke

JWT access token được xác minh cục bộ bằng chữ ký có thể không cần gọi authorization server ở mỗi request. Vì vậy, revoke tại issuer không tự làm chữ ký JWT sai. Các cách giảm cửa sổ:

- Access token TTL ngắn.
- Opaque/reference token và introspection.
- Denylist theo jti/session hoặc principal revocation epoch.
- Sender-constrained token như DPoP/mTLS khi phù hợp.
- Kiểm tra session/principal status cho thao tác nhạy cảm.

Không tuyên bố “đã revoke ngay lập tức” nếu resource server vẫn chấp nhận JWT cũ tới exp. Hãy định nghĩa SLA và kiểm chứng ở các resource server thực tế.

## 9. Rotation và overlap an toàn

Rotation thay credential cũ bằng credential mới để giảm tác động của lộ bí mật, hết hạn hoặc thay đổi owner. Một quy trình rotation có thể gồm:

1. Tạo credential mới ở authority có thẩm quyền.
2. Lưu vào secret manager/KMS/HSM theo policy.
3. Phân phối tới client/service được phép.
4. Kiểm tra client mới đã hoạt động bằng credential mới.
5. Chuyển traffic/consumer sang credential mới.
6. Revoke credential cũ sau khi dependency được chuyển đổi.
7. Xác minh validator từ chối credential cũ.
8. Xóa bản sao cũ khỏi secret stores, CI/CD, config và artifact theo retention.

Overlap có thể cần để tránh downtime, nhưng phải có thời hạn, scope hẹp và audit. Nếu credential cũ bị compromise, không duy trì overlap chỉ vì thuận tiện; containment có thể yêu cầu revoke ngay và chấp nhận gián đoạn có kiểm soát.

### Zero-downtime rotation

Với service-to-service credential, có thể hỗ trợ hai key active trong một cửa sổ ngắn. Client triển khai key mới, kiểm tra request thành công, sau đó server revoke key cũ. Cần giới hạn số key đồng thời, xác định owner và tự động cảnh báo khi key cũ vẫn được dùng sau deadline.

## 10. Race condition, idempotency và partial failure

Cleanup thường là quy trình nhiều bước và có thể được yêu cầu lặp lại. Ví dụ, HR event đến hai lần, admin bấm revoke nhiều lần hoặc worker retry sau timeout.

### 10.1. Idempotency

Một lệnh cleanup nên có operation ID và idempotency key. Nếu chạy lại:

- Không tạo trạng thái mới mâu thuẫn.
- Không vô tình kích hoạt lại credential đã revoke.
- Không xóa audit evidence cần giữ.
- Trả kết quả đã xử lý hoặc trạng thái hiện tại.

### 10.2. Race giữa revoke và refresh

Một refresh request có thể đến cùng lúc với lệnh revoke:

- Nếu refresh commit trước revoke, token mới phải thuộc phạm vi cleanup hoặc bị revoke theo token family.
- Nếu revoke commit trước refresh, token endpoint phải từ chối.
- Không để refresh request dùng replica stale để phát token mới sau khi principal đã disable.
- Dùng transaction, version/epoch hoặc serialization theo principal/token family khi cần.

### 10.3. Partial failure

Nếu API key đã revoke tại gateway nhưng secret manager chưa xóa bản sao, quyền truy cập có thể đã bị chặn nhưng cleanup chưa hoàn tất. Trạng thái nên thể hiện từng bước:

~~~text
REQUESTED
REVOKED_AT_ISSUER
PROPAGATION_PENDING
VALIDATORS_CONFIRMED
COPIES_CLEANUP_PENDING
COMPLETED
FAILED_REQUIRES_REVIEW
~~~

Không gắn một cờ `completed=true` khi còn validator quan trọng chưa xác nhận. Có thể đóng containment phase nhưng vẫn giữ cleanup case mở cho phần còn lại.

## 11. Audit, retention và bằng chứng

Audit record nên ghi:

- Ai hoặc hệ thống nào yêu cầu cleanup.
- Principal, credential reference và phạm vi bị ảnh hưởng.
- Lý do: offboarding, user request, compromise, expiry, rotation...
- Thời điểm yêu cầu, thời điểm hiệu lực và từng bước hoàn tất.
- Service/validator đã nhận event và trạng thái xác nhận.
- Lỗi, retry, override và người phê duyệt ngoại lệ.
- Kết quả kiểm tra credential cũ bị từ chối.

Không ghi secret thô, private key, password hash nếu không cần, OTP, recovery code hoặc token có thể sử dụng. Audit evidence cũng là dữ liệu cần bảo vệ: giới hạn truy cập, integrity, retention và xóa theo policy. Có thể giữ credential ID/reference đã revoke hoặc tombstone tối thiểu để ngăn tái sử dụng mà không giữ bí mật cũ.

### 11.1. Tombstone và anti-resurrection

Nếu xóa hoàn toàn bản ghi credential, một event cũ hoặc replica stale có thể tạo lại credential như thể chưa từng bị revoke. Tombstone có thể giữ ID, trạng thái revoked, thời điểm và nguồn phát hành tối thiểu để:

- Từ chối credential cũ.
- Chặn event replay hoặc import dữ liệu cũ.
- Bảo đảm replica đồng bộ không hồi sinh trạng thái active.
- Hỗ trợ audit và điều tra theo retention.

Tombstone không nên chứa secret hoặc dữ liệu cá nhân dư thừa. Cần có thời hạn và quy trình purge khi hết mục đích lưu.

## 12. Quyền riêng tư và dữ liệu sau khi tài khoản đóng

Account deletion và credential cleanup phải tuân theo mục đích xử lý và nghĩa vụ lưu giữ:

- Xóa password verifier, recovery secret và token không còn cần sau khi revoke.
- Gỡ public-key credential mapping, nhưng giữ tombstone/reference tối thiểu nếu cần chống tái sử dụng.
- Xóa dữ liệu cá nhân trong profile theo chính sách; xử lý bản sao/backup theo lịch được công bố.
- Giữ audit evidence tối thiểu khi có căn cứ; tách khỏi dữ liệu sản phẩm và giới hạn truy cập.
- Yêu cầu processor/vendor xóa hoặc xác nhận xử lý dữ liệu theo hợp đồng và pháp luật áp dụng.
- Không giữ private key của người dùng hoặc bí mật đã revoke chỉ để thuận tiện khôi phục.

Nếu dữ liệu phải được giữ vì tranh chấp/nghĩa vụ pháp lý, đánh dấu legal hold, giới hạn mục đích và quyền truy cập; không tiếp tục cho phép credential dùng để đăng nhập.

## 13. Tình huống thực tế: nhân viên rời công ty

Một nhân viên có tài khoản SSO, passkey trên laptop cá nhân, certificate để truy cập VPN, API key dùng cho automation, refresh token của ứng dụng báo cáo và một số phiên trên điện thoại. Khi nhân viên rời công ty, IAM chỉ disable tài khoản directory.

### Những đường truy cập còn sót

- Passkey vẫn được lưu trong authenticator; nếu ứng dụng không disable principal hoặc gỡ mapping, credential có thể tiếp tục được chấp nhận.
- Certificate vẫn có thể xác thực VPN nếu PKI không revoke hoặc gateway không kiểm tra trạng thái.
- API key của automation có thể vẫn hoạt động dù owner đã rời công ty.
- Refresh token có thể tiếp tục xin access token mới.
- Session cookie còn hiệu lực tại các ứng dụng không nhận sự kiện disable.
- Secret đã được sao chép vào CI/CD variable hoặc file cấu hình.

### Quy trình xử lý

1. Nhận offboarding event có thời điểm hiệu lực từ HR/IAM.
2. Disable principal và tenant memberships tại nguồn.
3. Revoke SSO/local sessions, refresh token families và token grants.
4. Revoke certificate tại PKI và xác nhận VPN gateway từ chối.
5. Revoke API key; chuyển automation sang owner/workload identity mới nếu còn cần.
6. Gỡ passkey credential mapping khỏi principal và chặn mọi assertion từ credential đã gỡ.
7. Tìm secret copies trong secret manager, CI/CD, repository và deployment config; rotate các secret cần tiếp tục sử dụng.
8. Xác nhận từng validator và ghi audit; theo dõi event consumer bị lỗi.
9. Xử lý dữ liệu cá nhân/tài nguyên cần bàn giao theo policy, không chuyển credential cá nhân.

Kết quả đạt không phải là “tài khoản directory đã disable”, mà là mọi điểm truy cập trong phạm vi đã xác định từ chối credential cũ và quyền sở hữu tài nguyên đã được bàn giao.

## 14. Pseudocode: cleanup một credential

Ví dụ khái niệm cho credential registry. Hàm và trạng thái cần được điều chỉnh theo hệ thống thực tế:

~~~ts
async function revokeCredential(request) {
  const actor = await authorizeCleanupActor(request.actor, request.scope);
  if (!actor.allowed) return rejectRequest();

  const operation = await cleanupStore.getOrCreateIdempotently({
    idempotencyKey: request.idempotencyKey,
    credentialRef: request.credentialRef,
    reason: request.reason
  });

  if (operation.status === "COMPLETED") return operation.result;

  const credential = await credentialRegistry.find(request.credentialRef);
  if (!credential) return recordNotFoundOrAlreadyPurged(operation);

  await credentialRegistry.markRevocationPending(credential.id, operation.id);
  await issuingAuthority.revoke(credential);
  await revocationEvents.publish({
    eventId: operation.eventId,
    credentialRef: credential.safeReference,
    principalRef: credential.principalRef,
    effectiveAt: now(),
    reason: request.reason
  });

  const confirmations = await validatorRegistry.collectRevocationAcks(operation.id);
  if (!confirmations.allCriticalValidatorsDenied) {
    await cleanupStore.markPending(operation.id, confirmations);
    return { status: "PROPAGATION_PENDING" };
  }

  await credentialRegistry.markRevoked(credential.id, now());
  await auditStore.appendCleanupResult(operation.id, confirmations);
  return { status: "REVOKED_AND_VERIFIED" };
}
~~~

Đây là pseudocode minh họa. Trong thực tế, không giữ một transaction database mở trong khi gọi nhiều dịch vụ từ xa. Dùng state machine/outbox/saga hoặc workflow engine phù hợp; mỗi bước có timeout, retry, idempotency và compensation rõ. Nếu issuer revoke thành công nhưng event publish lỗi, operation phải ở trạng thái pending và có worker/reconciliation tiếp tục xử lý. Không đánh dấu completed chỉ vì một API trả HTTP 200.

## 15. Tiêu chí chấp nhận và kiểm thử

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Credential active được revoke | Issuer/registry ghi trạng thái revoke và mọi validator quan trọng từ chối |
| Credential đã revoke được gửi lại | Không được kích hoạt lại; thao tác lặp idempotent |
| User bị disable | Login mới bị từ chối; session/token hiện tại được xử lý theo SLA |
| Passkey bị gỡ | Assertion từ credential ID đã gỡ bị từ chối |
| TOTP seed bị reset | Mã sinh từ seed cũ không còn được chấp nhận |
| Recovery code cũ đã dùng hoặc bị thay | Code cũ bị từ chối và không thể replay |
| Certificate bị revoke | Gateway/validator kiểm tra trạng thái và từ chối theo SLA |
| API key bị rotate | Client mới hoạt động; key cũ bị từ chối sau thời điểm cutover |
| Refresh và revoke xảy ra đồng thời | Không phát hành token mới còn hiệu lực sau revoke commit |
| JWT cũ còn chữ ký hợp lệ | Resource server áp dụng TTL/denylist/introspection/revocation epoch theo SLA đã công bố |
| Một consumer bỏ lỡ revoke event | Reconciliation phát hiện và đồng bộ lại; credential không được coi cleanup hoàn tất |
| Cache giữ trạng thái active cũ | Cache invalidation/TTL/version khiến validator từ chối trong SLA |
| Secret còn trong CI/CD hoặc artifact | Inventory/scan phát hiện; rotate và xóa bản sao theo policy |
| Backup còn chứa dữ liệu credential | Dữ liệu không được dùng để xác thực; xử lý hết hạn backup/crypto-erasure theo policy |
| Orphaned credential không rõ owner | Tạo case điều tra, gán owner tạm và quyết định revoke theo rủi ro |
| Offboarding event bị gửi trùng | Idempotency ngăn side effect mâu thuẫn; audit ghi nhận lần xử lý |
| Account deletion đang legal hold | Credential bị revoke; dữ liệu giữ lại bị giới hạn mục đích và quyền truy cập |
| Validator không phản hồi | Operation ở pending/failed-review; không báo cleanup hoàn tất |
| Credential cũ được import từ replica | Tombstone/revocation epoch ngăn trạng thái active bị hồi sinh |
| Cleanup thành công | Audit ghi actor, reason, phạm vi, thời gian và xác nhận validator; không chứa secret |

### Chỉ số vận hành

Theo dõi số credential active/orphaned/expired, tỷ lệ credential có owner, thời gian từ trigger tới revoke, thời gian propagation tới validator cuối, số operation pending, tỷ lệ retry, số credential cũ bị từ chối trong kiểm thử, số secret tìm thấy trong CI/CD/artifact và tỷ lệ offboarding hoàn tất đúng SLA. Không lưu secret thô để đo các chỉ số này.

## 16. Bài tập tự kiểm tra

Một doanh nghiệp có nhân viên dùng SSO và passkey để vào SaaS, certificate để truy cập VPN, API key cho automation và refresh token cho ứng dụng báo cáo. Một nhân viên nghỉ việc vào cuối ngày; hai tuần sau, nhóm bảo mật phát hiện API key do nhân viên đó tạo xuất hiện trong một repository công khai.

Hãy:

1. Lập inventory credential, chủ sở hữu, mục đích, validator và nơi lưu bản sao.
2. Thiết kế offboarding cleanup tại thời điểm hiệu lực và chỉ rõ thứ tự disable/revoke/propagate/delete.
3. Mô tả cách thu hồi passkey, certificate, API key, refresh token và session.
4. Giải thích vì sao disable directory user không đủ và vì sao JWT có thể còn được chấp nhận sau revoke.
5. Thiết kế phản ứng incident khi API key bị lộ, bao gồm containment, rotation, secret scanning và audit.
6. Xử lý race giữa refresh token request và lệnh revoke.
7. Xác định dữ liệu cần giữ dưới dạng tombstone/audit và dữ liệu phải xóa theo retention.
8. Viết test case chứng minh credential cũ không thể truy cập sau cleanup ở mọi validator.

**Gợi ý đánh giá:** câu trả lời tốt phải phân biệt disable/revoke/delete/destroy, bao phủ credential và bản sao ở mọi hệ thống, có propagation/reconciliation, xử lý JWT/session, giữ audit tối thiểu và chứng minh bằng kiểm thử rằng credential cũ bị từ chối.

---

**Ghi nhớ:** credential cleanup bảo đảm credential hết vòng đời không còn được chấp nhận. Hãy inventory mọi credential và dependency; phân biệt **disable, revoke, expire, unlink, delete và destroy**; thu hồi tại issuer rồi lan truyền tới mọi validator/cache; kiểm tra session/token và bản sao trong secret store, CI/CD, backup; xử lý race/retry bằng idempotency; giữ audit/tombstone tối thiểu theo retention. Chỉ đóng cleanup khi các điểm xác thực quan trọng đã xác nhận từ chối credential cũ.
