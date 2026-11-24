# Service account

## 1. Service account là gì?

**Service account** là danh tính không đại diện cho một người dùng tương tác, mà đại diện cho một ứng dụng, dịch vụ, workload, job tự động hoặc thành phần kỹ thuật cần truy cập tài nguyên. Ví dụ: dịch vụ thanh toán gọi API sổ cái, job sao lưu đọc object storage, ứng dụng gửi email qua nhà cung cấp hoặc workload trong Kubernetes gọi một dịch vụ nội bộ.

Service account cho phép hệ thống xác định **thành phần nào đang gọi**, kiểm tra credential của thành phần đó và áp dụng quyền đúng với nhiệm vụ. Nó thường được gọi là non-human identity, workload identity, machine identity hoặc service principal tùy nền tảng. Các tên này có thể khác nhau về mô hình triển khai, nhưng cùng nhấn mạnh rằng danh tính thuộc về workload và có vòng đời riêng.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, service account kết nối nguyên lý xác thực danh tính với credential, certificate, token, session, trust boundary và authorization. Một service account an toàn phải có owner chịu trách nhiệm, mục đích rõ, credential được bảo vệ, quyền tối thiểu, thời hạn và quy trình thu hồi. Việc tạo một tài khoản kỹ thuật rồi cấp quyền rộng vô thời hạn sẽ biến nó thành một điểm chiếm quyền có tác động lớn.

Sau bài học, người học có thể:

- Phân biệt service account, service principal, user account và workload identity.
- Xác định owner, mục đích và phạm vi tin cậy của danh tính dịch vụ.
- Chọn cơ chế xác thực phù hợp: managed identity, federation, certificate, private key hoặc secret.
- Thiết kế OAuth 2.0 client credentials và client authentication an toàn.
- Phân biệt xác thực service với quyền truy cập API và danh tính người dùng được ủy quyền.
- Bảo vệ secret, private key, certificate và access token.
- Quản lý provisioning, rotation, expiry, revocation và access review.
- Phát hiện credential bị lộ, service account mồ côi và hành vi bất thường.
- Kiểm thử token audience, scope, replay, impersonation và privilege escalation.

## 2. Service account khác user account thế nào?

User account đại diện cho một người. Người dùng thường đăng nhập qua giao diện, tương tác với MFA/passkey và nhận session để thực hiện hành động theo quyền của họ. Service account đại diện cho một thành phần phần mềm hoặc workload, thường xác thực tự động mà không có người nhập password mỗi lần.

| Đặc điểm | User account | Service account |
| --- | --- | --- |
| Chủ thể | Con người | Ứng dụng, service, job, workload hoặc thiết bị |
| Hoạt động | Tương tác, có thể qua browser/mobile | Tự động, thường qua API hoặc giao thức máy-máy |
| Credential thường gặp | Password, passkey, security key, MFA | Workload identity, certificate, private key, secret, token |
| Vòng đời | Joiner, mover, leaver của người dùng | Deploy, scale, rotate, migrate, retire workload |
| Owner | Chính người dùng và tổ chức | Team/service owner chịu trách nhiệm |
| Quyền | Theo vai trò, nhóm và ngữ cảnh người dùng | Theo nhiệm vụ cụ thể và resource cần truy cập |
| Giám sát | Đăng nhập, session, MFA và hành vi người dùng | Token issuance, workload, API call, key usage và deployment |
| Recovery | Khôi phục quyền kiểm soát của người dùng | Rotate/reissue credential hoặc khôi phục workload identity |

Không nên tạo một user account tên “service-admin” rồi dùng chung cho nhiều ứng dụng. Cách làm đó làm mờ chủ thể thật, khiến audit không biết service nào thực hiện hành động và tạo một credential có phạm vi ảnh hưởng lớn.

### 2.1. Service account không phải tài khoản dùng chung cho nhân viên

Một tài khoản kỹ thuật không nên được nhiều người đăng nhập tương tác bằng cùng password. Khi cần nhân viên vận hành một service, họ dùng user account cá nhân với quyền quản trị có kiểm soát; service dùng workload identity riêng để gọi API.

Nếu một người cần thực hiện thao tác thay mặt service, ghi nhận cả actor là người dùng và workload/client thực thi. Không biến service account thành cách né MFA hoặc chia sẻ danh tính.

### 2.2. Service account và service principal

Tên gọi phụ thuộc hệ sinh thái:
- Service account thường là tài khoản kỹ thuật trong directory hoặc nền tảng.
- Service principal thường là biểu diễn danh tính của một ứng dụng trong một tenant hoặc authorization system.
- Workload identity nhấn mạnh danh tính gắn với workload đang chạy.
- Machine identity có thể bao gồm service, thiết bị, certificate và các thực thể phi con người khác.

Không nên suy ra semantics chỉ từ tên. Cần biết issuer nào quản lý principal, credential nào chứng minh quyền kiểm soát và resource server nào tin danh tính đó.

## 3. Những trường hợp cần service account

Ví dụ:

- **Service-to-service API:** order-service gọi inventory-service để giữ hàng.
- **Scheduled job:** job đối soát hằng đêm đọc dữ liệu giao dịch và ghi báo cáo.
- **CI/CD workload:** pipeline triển khai ứng dụng cần quyền cập nhật một cluster hoặc cloud resource.
- **Backup agent:** tiến trình sao lưu cần đọc dữ liệu nguồn và ghi vào kho backup.
- **Monitoring/observability:** agent gửi metrics hoặc logs tới hệ thống giám sát.
- **Integration:** connector đồng bộ khách hàng với SaaS bên ngoài.
- **Device/workload management:** agent thiết bị lấy cấu hình và gửi trạng thái.

Mỗi service account nên đại diện cho một workload hoặc một ranh giới quyền rõ. Nếu hai job có mục đích và quyền khác nhau, nên dùng hai danh tính riêng để một credential bị lộ không mở quyền cho cả hai.

### 3.1. Một workload có thể cần nhiều danh tính

Một ứng dụng có thể gọi nhiều hệ thống: đọc queue, ghi database và truy cập secret manager. Không nhất thiết dùng một service account có tất cả quyền. Có thể cấp identity riêng theo workload hoặc tách credential/role theo nhiệm vụ, tùy khả năng nền tảng.

Nguyên tắc là giới hạn blast radius. Nếu một thành phần chỉ cần đọc queue, credential của nó không nên cho phép xóa database hoặc tạo administrator khác.

## 4. Thiết kế danh tính và ownership

Trước khi tạo service account, xác định:

- Tên kỹ thuật ổn định và duy nhất.
- Owner là team hoặc cá nhân chịu trách nhiệm vận hành.
- Service/application/workload sử dụng danh tính.
- Môi trường: development, staging, production.
- Tenant, namespace hoặc trust domain.
- Mục đích và tài nguyên cần truy cập.
- API, scope, role và giới hạn hành động.
- Credential type, nơi lưu key và cách rotate.
- Ngày tạo, thời hạn, lần sử dụng gần nhất và review date.
- Quy trình incident, revoke và retirement.

Một record khái niệm:

~~~yaml
service_identity:
  id: svc-order-worker-prod
  owner_team: commerce-platform
  workload: order-worker
  environment: production
  purpose: consume-order-events
  issuer: https://identity.example.test
  allowed_audience:
    - inventory-api
  allowed_scopes:
    - stock:reserve
  credential_method: workload-federation
  review_at: 2027-02-01
  status: active
~~~

Đây là ví dụ minh họa, không phải schema chuẩn. Không lưu secret hoặc private key trong metadata inventory. Record cần tham chiếu tới secret manager, certificate inventory hoặc workload identity configuration được bảo vệ.

### 4.1. Owner không phải credential holder

Owner chịu trách nhiệm về mục đích, quyền, rotation và retirement. Owner không nhất thiết biết hoặc có thể đọc private key/secret. Nên tách quyền quản trị metadata khỏi quyền lấy credential, và hạn chế người có thể cấp thêm quyền cho chính service account.

Nếu owner rời team, phải có quy trình chuyển giao ownership. Service account không có owner là dấu hiệu cần review và có thể phải suspend cho tới khi xác định được trách nhiệm.

### 4.2. Môi trường phải được tách biệt

Không dùng cùng credential cho development và production. Credential test có thể bị chia sẻ rộng hoặc xuất hiện trong log; nếu cùng key với production, sự cố ở môi trường thấp có thể dẫn tới xâm nhập hệ thống thật.

Dùng principal, audience, scope và key riêng cho từng môi trường. Không cho token staging được resource server production chấp nhận.

## 5. Chọn cơ chế xác thực cho service account

Ưu tiên cơ chế có thể cấp credential ngắn hạn, gắn với workload và có khả năng thu hồi. Lựa chọn phụ thuộc nền tảng, trust boundary và giao thức của resource server.

| Cơ chế | Cách chứng minh | Ưu điểm | Rủi ro/điểm cần xét |
| --- | --- | --- | --- |
| **Managed identity** | Nền tảng cloud cấp danh tính cho workload | Giảm secret tĩnh và tự động hóa vòng đời | Phụ thuộc nền tảng; cần giới hạn role và endpoint metadata |
| **Workload identity federation** | Workload chứng minh danh tính với issuer tin cậy rồi đổi lấy token | Không cần lưu client secret dài hạn | Cần ràng buộc issuer, subject, audience và claims chặt |
| **X.509 client certificate / mTLS** | Workload chứng minh giữ private key tương ứng certificate | Xác thực client ở tầng TLS, hỗ trợ certificate-bound access | Quản lý CA, expiry, rotation, revocation và key storage |
| **private_key_jwt** | Client ký JWT assertion bằng private key để xác thực với token endpoint | Không gửi shared secret trong request | Cần bảo vệ private key, audience, jti và thời hạn assertion |
| **Client secret** | Client gửi secret đã đăng ký tới authorization server | Dễ tích hợp với hệ thống cũ | Secret có thể bị sao chép, rò rỉ và khó xác định bản sao |
| **HMAC request signing** | Client và server chia sẻ key để ký request | Có thể bảo vệ integrity/freshness ở tầng request | Shared secret ở hai phía; cần canonicalization và replay protection |
| **API key** | Client gửi key để được nhận diện/ủy quyền theo cấu hình | Đơn giản cho một số API | Thường là bearer secret; cần scope, expiry, rotation và giới hạn |

Không có một lựa chọn duy nhất cho mọi service. Nếu nền tảng hỗ trợ managed identity hoặc federation với token ngắn hạn, thường nên cân nhắc trước khi tạo secret tĩnh. Nếu hệ thống cần certificate hoặc mTLS, phải có PKI và quy trình vòng đời certificate tương ứng.

### 5.1. Password cho service account

Password tương tác thường không phải lựa chọn tốt cho workload tự động. Nó dễ bị đưa vào file cấu hình, script, biến môi trường, image hoặc log. Nếu hệ thống cũ bắt buộc dùng password:
- Sinh password ngẫu nhiên đủ mạnh, riêng cho từng principal.
- Không dùng password mặc định hoặc chia sẻ.
- Lưu trong secret manager, giới hạn quyền đọc.
- Không nhúng vào source code, container image hoặc repository.
- Có rotation và expiry rõ.
- Không cho đăng nhập tương tác nếu nền tảng hỗ trợ tắt.
- Giám sát việc sử dụng ngoài workload dự kiến.

Không dùng ngày tạo, tên service, hostname hoặc mã nhân viên làm password.

## 6. OAuth 2.0 Client Credentials

OAuth 2.0 Client Credentials Grant phù hợp cho confidential client truy cập tài nguyên dưới danh tính của chính client, không đại diện cho người dùng cuối. Client xác thực với authorization server, yêu cầu access token và dùng token gọi resource server.

~~~mermaid
sequenceDiagram
    participant W as Workload / Client
    participant AS as Authorization Server
    participant RS as Resource Server
    W->>AS: Token request + client authentication
    AS->>AS: Xác minh client và policy
    AS-->>W: Access token có audience/scope
    W->>RS: API request + access token
    RS->>RS: Xác minh token và authorization
    RS-->>W: Resource response
~~~

Quy trình khái quát:

1. Workload được gán client ID và phương thức client authentication.
2. Workload gửi token request tới token endpoint.
3. Authorization server xác minh client credential.
4. Server kiểm tra client được phép yêu cầu audience và scope nào.
5. Authorization server phát access token có thời hạn và quyền giới hạn.
6. Workload gửi token tới resource server.
7. Resource server xác minh token và quyết định quyền trên resource/action.

Client Credentials không phải luồng đăng nhập người dùng. Token đại diện cho client/service. Nếu cần hành động thay mặt người dùng, phải dùng flow delegated phù hợp và giữ rõ actor/delegation context; không giả mạo service token thành user token.

### 6.1. Client authentication khác access token

Client secret, private_key_jwt hoặc mTLS có thể dùng để xác thực client với token endpoint. Access token được cấp sau đó dùng để truy cập resource server. Hai loại credential có audience, mục đích và vòng đời khác nhau.

Không gửi client secret tới resource server để thay access token. Không dùng access token làm client secret để xin token khác trừ khi một profile cụ thể định nghĩa điều đó.

### 6.2. Token phải có audience và scope phù hợp

Một access token cần được phát hành cho resource server hoặc audience dự kiến. Scope nên phản ánh quyền tối thiểu cần thiết. Resource server phải kiểm tra issuer, audience, thời hạn, token type/profile và quyền; không chỉ kiểm tra chữ ký rồi cho phép mọi API.

Ví dụ, order-worker chỉ cần gọi inventory API để reserve stock. Token của nó không nên được chấp nhận bởi payroll API hoặc admin API. Nếu hệ thống dùng JWT, audience và claim phải được kiểm tra theo profile. Nếu dùng opaque token, resource server có thể introspect trạng thái với authorization server.

### 6.3. Không phát hành token quá rộng hoặc quá lâu

Access token nên có thời hạn phù hợp với rủi ro và khả năng refresh/lấy lại token. Token sống lâu làm tăng thời gian attacker có thể sử dụng nếu bị lộ. Client Credentials thường có thể xin token mới bằng client authentication khi cần; không mặc định cấp refresh token nếu không có nhu cầu và policy rõ.

Token không nên chứa secret hoặc dữ liệu cá nhân không cần thiết. Tránh đưa toàn bộ cấu hình nội bộ vào claim.

## 7. private_key_jwt

Với private_key_jwt, client tạo JWT assertion và ký bằng private key đã đăng ký với authorization server. Assertion được gửi trong token request để xác thực client.

Các claim thường cần theo profile:
- **iss:** client identifier.
- **sub:** client identifier.
- **aud:** token endpoint hoặc audience được authorization server quy định.
- **iat:** thời điểm phát hành.
- **exp:** thời hạn ngắn.
- **jti:** định danh assertion duy nhất để chống replay.

Authorization server kiểm tra chữ ký bằng public key đã đăng ký, audience, thời hạn, issuer/subject và replay policy. Assertion cần được dùng một lần hoặc trong giới hạn profile; server có thể lưu jti đã dùng trong thời gian phù hợp.

Private key phải được bảo vệ trong HSM, KMS, keystore hoặc secret manager có kiểm soát. Không để private key nằm trong repository, image hoặc log. Khi rotate key, có thể đăng ký key mới trước, chuyển client, rồi thu hồi key cũ sau giai đoạn chuyển tiếp được kiểm soát.

Không nhầm private_key_jwt với access token JWT. Assertion dùng để xác thực client tại token endpoint; access token là kết quả authorization server phát hành để truy cập resource.

## 8. Mutual TLS và certificate-based service identity

**Mutual TLS (mTLS)** cho phép cả client và server xác thực certificate trong TLS handshake. Client chứng minh quyền kiểm soát private key tương ứng với certificate; server xác minh certificate chain và policy.

Các kiểm tra thường gồm:
- Certificate chain tới trust anchor được cấu hình.
- Validity period và trạng thái revoke theo PKI policy.
- Subject Alternative Name (SAN) hoặc định danh được profile quy định.
- Key Usage và Extended Key Usage phù hợp client authentication.
- Host/service identity và trust domain.
- Private key proof-of-possession trong handshake.
- Mapping certificate identity tới service principal và quyền.

Không chỉ dựa vào Common Name nếu profile dùng SAN. Certificate hợp lệ về chữ ký không tự cấp quyền gọi mọi API. Sau mTLS, resource server hoặc gateway vẫn phải map client identity, audience, scope và authorization.

### 8.1. Certificate-bound access token

Một số profile OAuth cho phép ràng buộc access token với certificate của client. Khi đó resource server kiểm tra token được trình bày cùng certificate tương ứng, giúp giảm khả năng một bearer token bị đánh cắp có thể dùng từ client khác.

Cơ chế này cần hỗ trợ đúng ở authorization server, client và resource server. Nếu token chỉ là bearer token thông thường, việc client sử dụng mTLS ở một kết nối khác không tự biến token thành certificate-bound.

### 8.2. Certificate lifecycle

Certificate có ngày hết hạn và có thể bị thu hồi. Cần:
- Theo dõi expiry và cấp mới trước khi hết hạn.
- Rotate private key khi cần theo policy.
- Bảo vệ CA, signing key và enrollment endpoint.
- Thu hồi certificate khi workload retire hoặc key compromise.
- Cập nhật trust bundle và xử lý CA rollover.
- Kiểm tra revocation/status theo khả năng PKI.
- Không dùng một certificate chung cho nhiều service nếu cần audit và blast radius riêng.

Certificate hết hạn đột ngột có thể làm ngừng production. Theo dõi ngày hết hạn, số ngày còn lại, lỗi handshake và trạng thái rotation.

## 9. Workload identity federation và managed identity

Workload identity federation cho phép workload chứng minh danh tính với một identity provider hoặc nền tảng tin cậy, sau đó đổi assertion lấy access token cho resource khác. Workload không cần giữ client secret dài hạn.

Ví dụ, một pod Kubernetes có projected service account token với audience và thời hạn xác định. Workload gửi token đó tới cloud identity provider; provider kiểm tra issuer, subject, audience và policy rồi cấp token truy cập cloud resource.

### 9.1. Ràng buộc federation

Cấu hình federation cần giới hạn:
- Issuer chính xác.
- Subject hoặc workload identity chính xác.
- Audience dự kiến.
- Namespace, service account, repository hoặc workload attributes theo nền tảng.
- Environment và trust domain.
- Thời hạn assertion.
- Resource và scope được phép nhận token.

Không tin mọi token từ cùng một issuer. Một issuer có thể phục vụ nhiều workload; policy phải ràng buộc subject/audience cụ thể để workload khác không đổi token thay.

### 9.2. Kubernetes service account

Kubernetes ServiceAccount là danh tính cho process trong cluster. Token service account có thể được projected và giới hạn audience/thời hạn; nên ưu tiên token ngắn hạn được cấp theo cơ chế hiện đại của cluster thay vì secret token tĩnh kéo dài.

Thực hành:
- Không tự động mount service account token vào pod nếu workload không cần.
- Tạo service account riêng cho workload.
- Dùng Role/RoleBinding hoặc ClusterRole/ClusterRoleBinding có phạm vi nhỏ.
- Hạn chế quyền tạo pod, impersonate service account và đọc secret.
- Giới hạn audience và thời hạn token.
- Không chia sẻ token giữa namespace hoặc môi trường.
- Cân nhắc workload identity federation để truy cập cloud resource mà không lưu cloud key dài hạn.

### 9.3. Managed identity

Managed identity do nền tảng quản lý danh tính và credential cho workload. Ứng dụng lấy token từ cơ chế do nền tảng cung cấp, thay vì lưu client secret. Dù giảm secret sprawl, managed identity vẫn cần authorization tối thiểu và bảo vệ môi trường chạy.

Nếu attacker chiếm được workload hoặc quyền gọi metadata endpoint, họ có thể lấy token của identity gắn với workload. Cần bảo vệ SSRF, isolation, network controls, process privilege và scope của managed identity.

## 10. Secret, private key và token storage

Credential của service account thường tồn tại trong pipeline, container, host, secret manager và runtime. Mỗi bản sao là một điểm có thể bị lộ.

Nguyên tắc:
- Dùng secret manager hoặc KMS/HSM phù hợp.
- Cấp quyền lấy secret cho đúng workload, không cho mọi developer hoặc pod.
- Không commit secret vào Git hoặc cấu hình public.
- Không nhúng secret vào Docker image, package, build artifact hoặc log.
- Tránh truyền secret qua command line vì có thể xuất hiện trong process list/history.
- Giới hạn file permission và quyền đọc memory/process.
- Ưu tiên private key không xuất được nếu nền tảng hỗ trợ.
- Dùng token ngắn hạn thay secret tĩnh khi có thể.
- Mask secret trong log, tracing, crash dump và support tooling.
- Theo dõi truy cập secret manager và bất thường trong việc đọc credential.

Biến môi trường có thể thuận tiện nhưng thường dễ bị lộ qua dump, diagnostic hoặc cấu hình runtime. Nếu dùng, đánh giá quyền truy cập process/container và tránh in toàn bộ environment. Mount secret qua cơ chế quản lý có quyền phù hợp hoặc dùng API lấy credential trực tiếp theo nền tảng.

### 10.1. Không lưu secret trong source code

Các ví dụ sau là anti-pattern:
- Client secret viết thẳng trong file cấu hình được commit.
- Private key nằm trong repository cùng code.
- Password nằm trong script deploy hoặc command history.
- Token được in ra console để debug.
- Credential được copy vào ticket/chat.

Nếu secret đã bị commit hoặc log, xóa khỏi file hiện tại chưa đủ. Cần rotate/revoke credential, kiểm tra lịch sử Git/artifact/log và đánh giá phạm vi bị truy cập.

### 10.2. API key và bearer secret

API key thường là một giá trị bí mật được gửi theo request. Ai có key có thể sử dụng trong phạm vi key được cấp. Vì vậy cần scope, quota, expiry, rotation, monitoring và revoke. Không đặt API key trong URL query vì URL thường bị ghi vào access log, browser history và telemetry.

Nếu API key chỉ nhận diện client mà không có cơ chế ký request hoặc token scope chi tiết, nó không tự cung cấp freshness hay chống replay.

## 11. Rotation, overlap và revocation

Rotation thay credential cũ bằng credential mới để giảm rủi ro khi credential bị lộ hoặc theo chu kỳ quản trị. Một rotation tốt phải có thể triển khai mà không gây outage và không để hai credential cùng có quyền rộng vô thời hạn.

Một quy trình thường gồm:

1. Tạo key/secret/certificate mới.
2. Đăng ký public key hoặc credential mới ở authorization server/resource server.
3. Cập nhật workload lấy credential mới.
4. Kiểm tra token/API call bằng credential mới.
5. Theo dõi lỗi và xác nhận tất cả instance đã chuyển.
6. Thu hồi credential cũ.
7. Xác minh credential cũ không còn được chấp nhận.
8. Ghi audit và cập nhật inventory.

### 11.1. Overlap có giới hạn

Trong thời gian chuyển đổi, có thể cho phép key cũ và mới cùng tồn tại. Khoảng overlap cần ngắn, có ngày kết thúc và theo dõi usage. Nếu key cũ bị compromise, không nên giữ overlap chỉ để thuận tiện; revoke khẩn cấp và xử lý downtime theo incident plan.

### 11.2. Revocation

Khi workload retire, team đổi owner, credential bị lộ hoặc service không còn nhu cầu, cần:
- Disable principal hoặc credential.
- Revoke certificate/token/grant theo khả năng.
- Xóa role/group assignment.
- Thu hồi session hoặc token còn hiệu lực khi cần.
- Xóa secret khỏi runtime, vault reference và pipeline.
- Kiểm tra replica, cache và backup theo retention.
- Xác minh resource server từ chối credential cũ.
- Giữ audit tối thiểu cho điều tra.

Thu hồi client secret không tự động làm access token đã phát hành mất hiệu lực nếu resource server chỉ kiểm tra JWT cục bộ tới exp. Cần thiết kế access token lifetime, introspection, denylist hoặc revocation event khi cần thu hồi sớm.

## 12. Authorization và least privilege

Authentication trả lời service nào đang gọi. Authorization quyết định service đó được phép làm gì trên resource cụ thể.

Một policy có thể xét:
- Service principal và issuer.
- Environment và tenant.
- Audience/resource server.
- Scope hoặc role.
- Resource ID và action.
- Network/device/workload posture khi phù hợp.
- Purpose và transaction context.
- Thời điểm và trạng thái account.

Ví dụ:
- billing-worker được publish event vào billing-events.
- report-job chỉ được đọc bảng tổng hợp.
- order-service chỉ được gọi inventory reserve API.
- backup-agent chỉ được đọc nguồn và ghi backup destination; không được xóa backup cũ nếu không có quyền riêng.

Không cấp quyền wildcard như admin hoặc full access để tránh phải cập nhật policy thường xuyên. Nếu cần quyền rộng trong một tác vụ đặc biệt, dùng role tạm thời, approval và audit.

### 12.1. Confused deputy

Confused deputy xảy ra khi một service có quyền rộng bị lợi dụng để thực hiện hành động thay cho caller không đủ quyền. Ví dụ API gateway nhận request từ user nhưng gọi downstream bằng service account đặc quyền mà không chuyển tiếp/kiểm tra user context, khiến người dùng truy cập dữ liệu ngoài quyền.

Giảm rủi ro:
- Phân biệt service identity và end-user identity.
- Kiểm tra authorization ở gateway và resource service.
- Truyền delegation context có xác thực khi cần.
- Giới hạn scope service token.
- Không dùng service credential để bỏ qua quyền của user.
- Ràng buộc resource/action với caller và transaction.

### 12.2. Client Credentials không phải On-Behalf-Of

Client Credentials thể hiện service tự truy cập tài nguyên dưới quyền của chính client. Nếu service cần gọi downstream thay mặt user, cần flow delegated/OBO hoặc token exchange phù hợp với nền tảng, giữ actor và subject rõ ràng. Không tự thêm claim user vào service token.

## 13. Service account trong môi trường phân tán

Một hệ thống microservices có nhiều service gọi lẫn nhau. Mỗi service nên xác thực riêng với service đích; không dùng một shared API key cho cả cluster.

~~~mermaid
flowchart LR
    A[order-service identity] -->|token audience inventory| B[inventory-api]
    A -->|token audience payment| C[payment-api]
    D[report-job identity] -->|read-only token| E[reporting-store]
    F[backup-agent identity] -->|backup scope| G[backup-storage]
    H[CI workload identity] -->|deploy scope| I[deployment API]
~~~

Một service có thể xin các token khác nhau cho từng audience/resource. Không phát một token audience chung có thể truy cập mọi API nếu không cần.

### 13.1. Network trust không thay authentication

Chỉ vì request đến từ private subnet, cluster hoặc IP allowlist không có nghĩa nó đến từ service hợp lệ. Network control là lớp bổ sung. Service vẫn cần chứng minh identity bằng token, certificate hoặc workload identity theo policy.

### 13.2. East-west traffic

Traffic giữa các service nội bộ có thể đi qua service mesh. mTLS trong mesh giúp xác thực workload và mã hóa kết nối, nhưng authorization policy vẫn cần xác định service nào được gọi method/path nào. Không mặc định mọi workload trong cùng cluster đều đáng tin.

## 14. Monitoring và service account inventory

Service account có thể hoạt động trong nhiều năm mà không ai nhớ nó thuộc ứng dụng nào. Inventory và telemetry giúp phát hiện danh tính mồ côi, quyền thừa hoặc credential bị lạm dụng.

Nên theo dõi:
- Service identity không có owner hoặc owner không còn hoạt động.
- Credential chưa rotate hoặc sắp hết hạn.
- Service account không được sử dụng trong thời gian dài.
- Token issuance bất thường hoặc scope thay đổi.
- API call từ workload, region hoặc environment lạ.
- Lỗi authentication tăng đột biến.
- Secret manager access ngoài lịch trình.
- Certificate chain/issuer không mong đợi.
- Principal có quyền admin hoặc wildcard.
- Workload đã retire nhưng identity vẫn active.

Không tự động xóa account chỉ vì ít sử dụng; job theo lịch có thể chạy hiếm. Owner cần xác nhận lịch và mục đích trước khi suspend/revoke.

### 14.1. Audit fields

Một audit event có thể ghi:
- Service principal ID và owner/team.
- Workload, environment, namespace hoặc trust domain.
- Issuer, client ID, key/certificate reference.
- Audience, scope và resource/action.
- Thời điểm cấp token và thời điểm request.
- Source workload/node/region theo policy.
- Authentication result và authorization decision.
- Correlation ID, reason code và response status.

Không log client secret, private key, full access token, refresh token hoặc credential material. Nếu cần liên kết event, dùng token ID hoặc keyed reference được bảo vệ.

## 15. Threat model cho service account

| Mối đe dọa | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **Secret leakage** | Secret xuất hiện trong Git, image, log hoặc pipeline | Secret manager, scanning, rotation và revoke |
| **Overprivileged identity** | Service account có quyền rộng hơn nhiệm vụ | Least privilege, scope/resource restriction và review |
| **Shared credential** | Nhiều service dùng cùng key | Identity riêng theo workload và môi trường |
| **Workload impersonation** | Attacker giả mạo issuer/subject hoặc workload | Federation trust condition, mTLS và identity binding |
| **Token theft/replay** | Access token bị đánh cắp và dùng lại | Token ngắn hạn, sender constraint, TLS và replay controls |
| **SSRF to metadata endpoint** | Workload bị dụ gọi endpoint cấp managed identity token | SSRF defense, egress controls và scope nhỏ |
| **Confused deputy** | Service đặc quyền thực hiện thay caller không đủ quyền | Delegation context, downstream authorization và token exchange |
| **Stale identity** | Service đã retire nhưng account/credential còn active | Inventory, owner review và automated retirement |
| **Certificate expiry/compromise** | Cert hết hạn hoặc private key bị lộ | Expiry monitoring, rotation, revocation và HSM/KMS |
| **Federation misconfiguration** | Trust quá rộng cho issuer hoặc subject | Exact issuer/subject/audience allowlist |
| **CI/CD compromise** | Pipeline bị chiếm và lấy credential deploy | Short-lived federation, protected environment và approval |
| **Kubernetes token exposure** | Token service account bị mount rộng hoặc lưu lâu | Projected token, audience, TTL và automount controls |
| **Environment crossover** | Dev credential được dùng ở production | Principal/key/audience riêng theo environment |
| **Insider misuse** | Người vận hành lấy secret hoặc tự tăng quyền | Separation of duties, audit và privileged access management |

## 16. Ví dụ: order-service gọi inventory API

Giả sử order-service cần giữ hàng trong inventory khi nhận đơn mới. Service không đại diện cho người dùng cuối trong lời gọi nội bộ này; nó gọi API dưới danh tính workload của chính nó.

Flow:

1. Nền tảng cấp workload identity riêng cho order-service trong production.
2. Identity được gắn owner commerce-platform và mục đích reserve stock.
3. Workload lấy assertion ngắn hạn từ môi trường tin cậy hoặc dùng managed identity.
4. Order-service gửi token request tới authorization server, xác thực bằng federation hoặc client certificate.
5. Authorization server kiểm tra issuer, subject, audience và policy.
6. Server phát access token ngắn hạn chỉ dành cho inventory API với scope reserve.
7. Order-service gọi inventory API qua TLS/mTLS theo cấu hình.
8. Inventory API xác minh token, audience, expiry và scope.
9. API kiểm tra order/resource và giới hạn số lượng theo business policy.
10. Request được ghi audit theo service principal và correlation ID.
11. Khi order-service retire hoặc credential compromise, identity bị disable/revoke và token còn hiệu lực được xử lý theo revocation strategy.

~~~mermaid
sequenceDiagram
    participant O as order-service
    participant ID as Workload Identity Provider
    participant AS as Authorization Server
    participant INV as inventory-api
    O->>ID: Yêu cầu workload assertion
    ID-->>O: Assertion có issuer/subject/audience
    O->>AS: Token request + client proof
    AS->>AS: Verify federation/client authentication
    AS->>AS: Check audience và scope policy
    AS-->>O: Short-lived access token
    O->>INV: Reserve request + access token
    INV->>INV: Verify issuer, aud, exp, scope
    INV->>INV: Authorize order và stock operation
    INV-->>O: Reservation result
~~~

Nếu API cần thực hiện thao tác theo quyền của user đã đặt đơn, cần mang theo delegation context có xác thực và kiểm tra quyền user ở downstream. Token service của order-service không tự chứng minh user có quyền trên mọi đơn hàng.

## 17. Kiểm thử service authentication

| Test case | Kết quả mong đợi |
| --- | --- |
| Workload có identity hợp lệ | Lấy token theo audience/scope đã cấp |
| Client ID không tồn tại | Token endpoint từ chối |
| Client secret sai | Xác thực client thất bại, không phát token |
| private_key_jwt assertion sai chữ ký | Từ chối |
| Assertion hết hạn hoặc jti replay | Từ chối theo replay policy |
| Federation issuer đúng nhưng subject sai | Từ chối |
| Federation audience sai | Từ chối |
| Token audience là API khác | Resource server từ chối |
| Token hết hạn | Resource server từ chối |
| Scope thiếu quyền | API từ chối action |
| Certificate chain không tin cậy | TLS/client authentication thất bại |
| Certificate hết hạn/revoked | Từ chối theo PKI policy |
| Private key không khớp certificate | Proof-of-possession thất bại |
| Token bị dùng từ client khác khi certificate-bound | Từ chối binding |
| Credential dev gọi production | Từ chối environment/audience |
| Service account đã disabled | Không cấp token hoặc không chấp nhận credential |
| Secret rotation overlap | Key mới hoạt động; key cũ bị revoke đúng lịch |
| Secret manager không sẵn sàng | Fail theo policy, không dùng secret hardcode |
| Kubernetes token audience sai | Federation provider từ chối |
| Pod không cần token | Token không tự động mount |
| SSRF thử metadata endpoint | Không lấy được token ngoài policy |
| Service account không có owner | Inventory cảnh báo và yêu cầu xử lý |
| Confused deputy scenario | Downstream kiểm tra actor/subject và resource |
| Log inspection | Không có secret hoặc bearer token thô |

## 18. Checklist review

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Có owner và purpose rõ? | Team, workload và trách nhiệm được ghi nhận |
| Identity có riêng theo workload? | Không chia sẻ credential giữa service |
| Dev/staging/prod có tách? | Principal, key, audience và scope riêng |
| Có ưu tiên managed identity/federation? | Giảm secret tĩnh khi nền tảng hỗ trợ |
| Client authentication phù hợp? | private_key_jwt, mTLS hoặc secret được chọn theo risk |
| Token có audience/scope hẹp? | Resource server chỉ nhận token dành cho nó |
| Token có thời hạn phù hợp? | Short-lived và có revoke strategy |
| Secret/private key được bảo vệ? | Secret manager, KMS/HSM và least privilege |
| Certificate lifecycle có quản lý? | Expiry, rotation, CA trust và revocation |
| Workload federation có ràng buộc? | Issuer, subject, audience và environment chính xác |
| Kubernetes identity có giới hạn? | Projected token, TTL, audience, RBAC và automount |
| Authorization tách authentication? | Principal hợp lệ vẫn phải qua resource/action policy |
| Có chống confused deputy? | Delegation context và downstream authorization |
| Rotation có kiểm chứng? | Overlap giới hạn, revoke và test key cũ |
| Có inventory và access review? | Owner, last used, expiry và stale account |
| Có audit/alert? | Token issuance, scope, key use và API behavior |
| Retirement có revoke đầy đủ? | Principal, credential, grant, session và role được xử lý |
| Có negative tests? | Wrong issuer/audience/scope, replay, expiry và key mismatch |

### Tình huống tự kiểm tra

**Tình huống 1:** Hai microservice cùng chạy trong một cluster. Có thể dùng chung một service account để đơn giản hóa không?

**Trả lời:** Không nên nếu chúng có nhiệm vụ hoặc quyền khác nhau. Danh tính riêng giúp giới hạn blast radius và xác định chính xác service thực hiện request.

**Tình huống 2:** Một service có client secret hợp lệ. Có thể gọi mọi API trong hệ thống không?

**Trả lời:** Không. Secret chỉ xác thực client với authorization server. Token được cấp cần audience/scope phù hợp và resource server vẫn kiểm tra authorization.

**Tình huống 3:** Access token JWT có chữ ký hợp lệ nhưng audience là reporting API, trong khi request tới payroll API. Có chấp nhận không?

**Trả lời:** Không. Resource server phải kiểm tra audience của chính nó; chữ ký hợp lệ không có nghĩa token dành cho mọi API.

**Tình huống 4:** Service dùng mTLS. Có thể bỏ kiểm tra quyền ở API không?

**Trả lời:** Không. mTLS xác thực client ở tầng kết nối. API vẫn cần kiểm tra principal, resource, action và scope.

**Tình huống 5:** Một pod Kubernetes không cần gọi API ngoài cluster. Có nên tự động mount service account token vào pod không?

**Trả lời:** Không. Tắt automount nếu workload không cần token; giảm credential hiện diện trong runtime và nguy cơ bị lấy cắp.

**Tình huống 6:** Team đã xóa client secret khỏi repository sau khi phát hiện bị commit. Đã xử lý xong chưa?

**Trả lời:** Chưa. Cần rotate/revoke secret, kiểm tra lịch sử Git và artifact/log, xác định thời gian/phạm vi lộ và đánh giá token hoặc truy cập phát sinh.

**Tình huống 7:** Một service account không có request trong 90 ngày. Có nên xóa ngay không?

**Trả lời:** Không mặc nhiên. Có thể là job theo quý hoặc dự phòng. Kiểm tra owner, lịch chạy, mục đích và phụ thuộc trước khi suspend/retire.

## 19. Ghi nhớ

**Service account là danh tính dành cho ứng dụng, service hoặc workload để xác thực khi truy cập tài nguyên.** Nó cần owner, mục đích, phạm vi tin cậy và quyền riêng. Không dùng chung với nhân viên hoặc nhiều workload không liên quan; mỗi môi trường và nhiệm vụ cần identity phù hợp.

Ưu tiên managed identity, workload federation, certificate/mTLS hoặc private_key_jwt khi phù hợp để giảm secret tĩnh. Nếu buộc dùng secret/API key, lưu trong secret manager, giới hạn scope, rotate và revoke. OAuth Client Credentials xác thực client rồi cấp access token; resource server vẫn phải kiểm tra issuer, audience, expiry, scope và authorization. Inventory, audit, access review và quy trình retirement giúp ngăn service account mồ côi hoặc credential bị lạm dụng.
