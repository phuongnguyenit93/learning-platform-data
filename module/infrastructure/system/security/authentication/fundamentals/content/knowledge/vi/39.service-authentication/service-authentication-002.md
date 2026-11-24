# Danh tính workload — Xác thực an toàn giữa các dịch vụ và tiến trình

Một dịch vụ xử lý đơn hàng cần gọi dịch vụ thanh toán. Dịch vụ thanh toán phải biết request đến từ workload nào, request có được phát ra từ môi trường triển khai đáng tin cậy không và workload đó được phép thực hiện hành động gì. Nếu hai dịch vụ dùng chung một API key cố định được chép vào biến môi trường, bất kỳ ai lấy được key đều có thể giả làm một trong hai dịch vụ. Khi key bị lộ, nhóm vận hành phải tìm mọi bản sao, thay key ở nhiều nơi và hy vọng không bỏ sót một worker cũ.

**Danh tính workload (workload identity)** là định danh được gán cho một ứng dụng, service, job, container, VM hoặc tiến trình đang chạy để các hệ thống khác có thể xác minh bên gọi là workload nào. Danh tính này có vòng đời, phạm vi và nguồn tin cậy; nó được cấp dựa trên bằng chứng về workload/môi trường chạy và thường được dùng để nhận credential ngắn hạn như certificate hoặc token. Workload identity giúp dịch vụ xác thực lẫn nhau mà không cần nhúng một bí mật dài hạn dùng chung vào từng ứng dụng.

Bài học thuộc chương **Service authentication** của học phần **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Nội dung kết nối danh tính workload với credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản. Người học sẽ biết mô hình hóa ranh giới tin cậy, phòng chống giả mạo service, replay và lạm dụng quyền giữa các dịch vụ; đồng thời thiết kế luồng xác thực workload an toàn, có thể xoay vòng và thu hồi.

## 1. Kết quả học tập

Sau bài này, người học có thể:

- Giải thích workload identity và phân biệt principal của con người với principal của máy/dịch vụ.
- Mô tả vòng đời danh tính cho service, container, VM, serverless function, batch job và CI/CD workload.
- Thiết kế định danh ổn định, duy nhất trong một trust domain và có thể ánh xạ tới môi trường triển khai.
- Giải thích cách workload chứng minh danh tính bằng attestation, managed identity, certificate hoặc token federation.
- Mô hình hóa xác thực service-to-service bằng mTLS và OAuth 2.0 client credentials/workload federation.
- Hiểu các khái niệm SPIFFE ID, trust domain, SVID và vai trò của SPIRE ở mức kiến trúc.
- Sử dụng credential ngắn hạn, audience hẹp và quyền tối thiểu thay cho secret tĩnh dùng chung.
- Phân biệt authentication, authorization và workload attestation.
- Phòng chống token theft, identity spoofing, confused deputy, metadata service abuse và trust configuration lỗi.
- Thiết kế rotation, revocation, audit và ứng phó khi workload hoặc môi trường triển khai bị compromise.
- Viết tiêu chí kiểm thử cho identity issuance, binding, token audience, mTLS, federation và deprovisioning.

## 2. Workload identity là gì?

Workload là phần mềm đang thực thi một nhiệm vụ: API service, background worker, container, Kubernetes pod, virtual machine, serverless function, scheduled job, build agent hoặc một tiến trình trên máy chủ. Workload identity là định danh đại diện cho workload đó khi nó tương tác với hệ thống khác.

Một workload identity có thể mô tả:

- **Workload nào:** tên service, application, job hoặc component.
- **Nằm trong phạm vi nào:** organization, tenant, environment, namespace, cluster hoặc cloud account.
- **Được triển khai bởi ai:** deployment controller, orchestrator, cloud platform hoặc pipeline có thẩm quyền.
- **Đang chạy ở đâu:** runtime/host/container context ở mức cần thiết để xác minh.
- **Được phép làm gì:** quyền được gán ở authorization layer, độc lập với việc chứng minh danh tính.
- **Sống bao lâu:** thời gian hoạt động, credential lifetime và quy tắc thu hồi.

Ví dụ, checkout service có thể được biểu diễn bằng một định danh có cấu trúc:

~~~text
spiffe://prod.example/ns/commerce/sa/checkout
~~~

Đây là một ví dụ SPIFFE ID minh họa. Phần trust domain xác định miền cấp danh tính; phần path biểu diễn workload theo quy ước của tổ chức. Tên cụ thể cần được thiết kế sao cho duy nhất trong miền tin cậy, ổn định qua lần restart nhưng vẫn phân biệt environment, namespace hoặc workload khi cần.

### 2.1. Workload identity khác hostname và service name

Hostname, DNS name, IP address, Kubernetes service name hoặc tên container giúp định tuyến và tìm dịch vụ. Chúng không tự chứng minh request đến từ workload được phép. Một attacker có thể giả header hostname, chạy container cùng tên hoặc chiếm IP đã từng được sử dụng.

Workload identity cần được xác minh bằng credential/chứng cứ do authority tin cậy cấp, ví dụ certificate có subject/SAN phù hợp, token có issuer/audience/subject hợp lệ hoặc managed identity được cloud platform chứng thực.

### 2.2. Workload identity khác API key

API key tĩnh thường là bearer secret: bên nào lấy được key có thể sử dụng key theo quyền gắn với nó. Workload identity hướng tới việc cấp credential theo danh tính và trạng thái workload, có thời hạn ngắn, có thể ràng buộc với khóa hoặc môi trường, đồng thời thu hồi qua authority tập trung.

API key vẫn có thể xuất hiện trong hệ thống legacy hoặc tích hợp bên ngoài. Nếu buộc phải dùng, cần key riêng theo workload, scope hẹp, lưu trong secret manager, rotation và owner rõ ràng. Không dùng một key chung cho mọi service.

## 3. Human identity và workload identity

Con người và workload đều là principal, nhưng cách chứng minh và vòng đời khác nhau:

| Thuộc tính | Human identity | Workload identity |
| --- | --- | --- |
| Chủ thể | Người dùng, nhân viên, quản trị viên | Service, pod, VM, job, function, agent |
| Bằng chứng | Password, passkey, MFA, certificate, identity proofing | Runtime attestation, managed identity, certificate, federated token |
| Tương tác | Có thể thực hiện challenge, consent hoặc recovery | Thường tự động, không có người nhập OTP mỗi lần |
| Vòng đời | Onboarding, đổi vai trò, nghỉ việc, recovery | Deploy, scale, restart, rotate, migrate, decommission |
| Credential | Có thể gắn với authenticator cá nhân | Thường được cấp tự động, ngắn hạn và ràng buộc workload |
| Authorization | Vai trò/nhóm/quyền của người dùng | Service role, audience, scope, resource policy |
| Recovery | Proofing, recovery code, hỗ trợ tài khoản | Re-attestation, redeploy, cấp identity mới hoặc thu hồi workload |

Không dùng tài khoản nhân viên hoặc mật khẩu của một kỹ sư làm danh tính lâu dài cho service. Khi nhân viên nghỉ việc, service cần tiếp tục hoạt động dưới workload identity do tổ chức quản lý; quyền sở hữu và quản trị workload phải được bàn giao riêng.

## 4. Vòng đời của workload identity

Một danh tính workload có thể đi qua các trạng thái:

~~~text
DEFINED -> ATTESTED -> ACTIVE -> ROTATING -> ACTIVE
                    \-> SUSPENDED
                    \-> REVOKED
                    \-> DECOMMISSIONED
~~~

### 4.1. Define

Tổ chức định nghĩa:

- Tên/ID duy nhất và trust domain.
- Owner/team chịu trách nhiệm.
- Environment, tenant, namespace hoặc cloud account.
- Mục đích nghiệp vụ và dependency cần gọi.
- Credential type, issuer và thời hạn.
- Quyền tối thiểu cần có.
- Quy trình deploy, rotate, revoke và decommission.

Danh tính nên được tạo qua quy trình có kiểm soát (IaC, deployment controller hoặc identity platform). Không cho workload tự chọn một principal tùy ý rồi yêu cầu authority cấp quyền rộng.

### 4.2. Attest

Identity authority cần có bằng chứng rằng workload đang chạy trong môi trường được phép và request cấp danh tính xuất phát từ workload đó. Bằng chứng có thể là:

- Kubernetes service account token hoặc pod metadata được xác minh qua API server có thẩm quyền.
- Cloud instance identity document hoặc managed identity assertion.
- VM/host attestation, node identity hoặc TPM-backed key khi threat model yêu cầu.
- CI/CD workload token có issuer và claims được kiểm tra.
- Runtime agent/attestor kiểm tra namespace, service account, image, node hoặc deployment policy.

Attestation không phải một header tự khai. Authority cần xác minh chữ ký, issuer, audience, freshness, subject và các thuộc tính môi trường cần thiết. Nếu attacker chiếm node/control plane hoặc workload runtime, attestation có thể bị ảnh hưởng; ranh giới tin cậy phải phản ánh điều đó.

### 4.3. Issue

Sau khi attestation và policy thành công, authority cấp identity credential, thường là:

- X.509 certificate ngắn hạn để dùng mTLS.
- JWT/SVID hoặc token federation có audience hẹp.
- Cloud access token từ managed identity endpoint.
- Credential tham chiếu tới khóa không xuất được trong HSM/TPM hoặc secure enclave nếu nền tảng hỗ trợ.

Không cấp secret vĩnh viễn nếu có thể cấp credential ngắn hạn. Credential cần gắn đúng workload principal và thời hạn phù hợp.

### 4.4. Use, rotate và revoke

Workload dùng credential để xác thực với service khác. Khi credential gần hết hạn, agent hoặc client lấy credential mới và chuyển đổi an toàn. Khi workload bị compromise, owner đổi, deployment bị xóa hoặc policy thay đổi, authority cần ngừng cấp mới và thu hồi credential hiện tại theo SLA.

### 4.5. Decommission

Khi service/job không còn tồn tại:

- Disable identity issuance cho workload đó.
- Revoke certificate/token/grant còn hiệu lực theo policy.
- Xóa role binding, trust mapping, secret và cấu hình không còn cần.
- Gỡ workload khỏi allowlist/attestation policy.
- Giữ audit/tombstone tối thiểu để credential cũ không được tái kích hoạt.
- Xác nhận resource server từ chối credential cũ.

Xóa deployment không tự động xóa API key đã sao chép vào CI/CD, secret store hoặc máy chủ khác. Cần inventory và cleanup theo vòng đời.

## 5. Kiến trúc cấp workload identity

Một kiến trúc điển hình gồm workload, runtime/orchestrator, attestation authority, identity issuer và resource server:

~~~mermaid
flowchart TD
    W[Workload starts] --> R[Runtime / orchestrator]
    W --> A[Identity agent or SDK]
    A -->|Attestation request| I[Identity authority]
    R -->|Signed runtime evidence| I
    I --> P{Policy and trust validation}
    P -->|Allowed| C[Issue short-lived credential]
    P -->|Denied| D[Reject issuance]
    C --> A
    A --> W
    W -->|mTLS or token| S[Target service]
    S --> V[Validate identity and credential]
    V --> Z[Authorization policy]
    Z -->|Allowed| X[Execute operation]
    Z -->|Denied| Y[Reject request]
~~~

### Các thành phần

- **Workload:** ứng dụng/tiến trình cần danh tính.
- **Runtime/orchestrator:** nền tảng triển khai và quản lý workload.
- **Attestor:** thành phần lấy/xác minh bằng chứng môi trường chạy.
- **Identity authority/issuer:** quyết định workload có được cấp identity không và phát credential.
- **Agent/SDK:** lấy credential, theo dõi thời hạn và cung cấp cho client.
- **Resource server:** xác minh credential, principal và request context.
- **Authorization engine:** kiểm tra principal được phép làm gì trên resource nào.
- **Audit/monitoring:** ghi issuance, validation, rotation, revoke và policy decision.

Không để client tự gửi tên service qua header rồi resource server tin đó là identity. Resource server phải xác minh credential hoặc assertion được cấp bởi authority đáng tin.

## 6. SPIFFE và SPIRE ở mức khái niệm

SPIFFE (Secure Production Identity Framework For Everyone) định nghĩa cách đặt tên và cung cấp identity cho workload trong các hệ thống phân tán. SPIRE là một implementation/runtime system có thể xác minh workload và cấp SPIFFE Verifiable Identity Document (SVID).

### 6.1. SPIFFE ID

SPIFFE ID là URI có dạng:

~~~text
spiffe://trust-domain/path
~~~

- **Trust domain:** miền chịu trách nhiệm cấp và quản lý identity.
- **Path:** cấu trúc định danh workload theo policy của tổ chức.

Ví dụ:

~~~text
spiffe://prod.example/ns/payments/sa/ledger
spiffe://staging.example/ns/payments/sa/ledger
~~~

Hai ID trên biểu diễn hai workload cùng tên logic nhưng ở hai trust domain khác nhau. Tách environment giúp tránh việc staging credential được chấp nhận trong production.

### 6.2. SVID

SPIFFE có hai dạng SVID thường gặp:

- **X.509-SVID:** certificate dùng trong TLS/mTLS để chứng minh workload identity.
- **JWT-SVID:** JWT mang SPIFFE ID, dùng trong các giao thức cần assertion dạng token.

X.509-SVID thường phù hợp khi service-to-service giao tiếp qua TLS. JWT-SVID có thể phù hợp cho một số API hoặc môi trường không dùng mTLS trực tiếp, nhưng cần audience, expiry và chống replay phù hợp. JWT-SVID là bearer token trừ khi có ràng buộc bổ sung; không được coi chữ ký JWT tự nó ngăn replay.

### 6.3. SPIRE và workload attestation

Ở mức kiến trúc, SPIRE có thể:

1. Xác thực node/agent đang đăng ký với server.
2. Nhận bằng chứng về workload từ runtime/plugin attestor.
3. Đối chiếu bằng chứng với registration entry và policy.
4. Cấp SVID cho workload được phép.
5. Làm mới identity/credential theo thời hạn.

Chi tiết attestor và cách triển khai phụ thuộc nền tảng. Các thuộc tính như namespace, service account, image digest, node identity hoặc process selectors cần được chọn theo threat model; không dùng một thuộc tính dễ giả mạo làm bằng chứng duy nhất.

## 7. Cloud managed identity và workload federation

Các cloud platform cung cấp cơ chế identity cho workload để ứng dụng lấy credential mà không phải nhúng access key dài hạn trong source/config. Tên và chi tiết triển khai khác nhau theo nhà cung cấp, nhưng nguyên lý chung là:

1. Workload chạy trong môi trường cloud hoặc môi trường ngoài đã được trust.
2. Workload chứng minh identity của runtime bằng metadata/credential/assertion có chữ ký.
3. Identity service kiểm tra issuer, subject, audience, tenant/account, condition và policy.
4. Workload nhận access token ngắn hạn hoặc credential tạm thời.
5. Resource server kiểm tra token và authorization.

### 7.1. Managed identity

Managed identity là danh tính do nền tảng quản lý cho VM, app service, function, container hoặc workload. Platform xử lý một phần việc cấp/rotate credential; ứng dụng lấy token qua endpoint/SDK được hỗ trợ.

Ưu điểm:

- Giảm nhu cầu lưu client secret/API key trong ứng dụng.
- Credential có thời hạn và được platform quản lý.
- Có thể gán role/policy trực tiếp cho workload identity.
- Có audit trail tại identity provider/resource platform.

Giới hạn:

- Cấu hình role quá rộng vẫn gây hậu quả lớn.
- Nếu attacker chiếm workload runtime, họ có thể gọi managed identity endpoint bằng quyền của workload.
- Metadata endpoint cần được bảo vệ khỏi SSRF và truy cập từ workload không được phép.
- Cần phân biệt identity theo environment/resource; không dùng một identity chung cho mọi service.

### 7.2. Workload identity federation

Federation cho phép một identity provider tin cậy token từ một issuer khác, ví dụ CI/CD platform hoặc Kubernetes cluster, rồi đổi assertion ngắn hạn lấy cloud access token. Trust policy cần ràng buộc:

- Issuer chính xác và TLS/JWKS trust phù hợp.
- Subject claim cụ thể (repository, workflow, namespace, service account hoặc workload identity).
- Audience đúng với token exchange endpoint.
- Tenant/account/project và environment phù hợp.
- Conditions về branch, deployment environment hoặc workload context khi cần.

Không tin toàn bộ token chỉ vì issuer là một nhà cung cấp quen thuộc. Nếu trust policy chấp nhận mọi repository, mọi branch hoặc mọi service account, attacker có thể chạy workload ở nơi khác và lấy credential production.

### 7.3. Ví dụ federation trong CI/CD

Một pipeline deploy production cần truy cập cloud registry và cluster:

1. CI platform phát OIDC assertion ngắn hạn cho job.
2. Cloud identity provider xác minh issuer, signature, audience, subject và điều kiện workflow.
3. Token exchange cấp access token ngắn hạn cho role deploy.
4. Role chỉ được phép cập nhật đúng cluster/namespace hoặc registry cần thiết.
5. Token hết hạn sau job; không lưu service account key dài hạn trong repository.

Nếu attacker sửa workflow, chiếm repository hoặc thay branch protection, trust policy có thể bị lợi dụng. Bảo vệ source control, workflow permissions, environment approval và deployment identity là một phần của workload authentication.

## 8. Service-to-service authentication bằng mTLS

mTLS là TLS trong đó cả client và server đều xác thực certificate của phía bên kia. Với workload identity, client certificate chứng minh workload gọi; server certificate chứng minh service đích.

### Luồng khái niệm

1. Workload A nhận X.509 certificate ngắn hạn từ identity authority.
2. Workload A mở TLS connection tới service B.
3. Service B trình server certificate; A kiểm tra trust chain, SAN/hostname và validity.
4. A trình client certificate; B xác minh chain, issuer, thời hạn và workload identity.
5. B ánh xạ identity sang principal và áp dụng authorization policy.
6. Hai bên bảo vệ traffic trong TLS session.

### 8.1. Xác minh đúng identity

Không chỉ kiểm tra certificate có chữ ký hợp lệ. Cần kiểm tra:

- Chain tới CA/trust bundle được cấu hình.
- Thời hạn notBefore/notAfter.
- Subject Alternative Name (SAN) hoặc URI SAN chứa workload identity theo policy.
- Key usage/extended key usage phù hợp client/server authentication.
- Certificate status/revocation theo khả năng của PKI.
- Trust domain và mapping tới principal được mong đợi.

Không dùng Common Name như định danh duy nhất nếu profile hiện đại yêu cầu SAN. Không chấp nhận certificate từ CA tin cậy rộng hơn dự kiến chỉ vì chain hợp lệ.

### 8.2. TLS termination và proxy

Nếu mTLS kết thúc ở service mesh sidecar hoặc gateway, backend có thể không trực tiếp thấy client certificate. Proxy phải truyền identity qua kênh nội bộ được bảo vệ, có xác thực proxy và không cho client ngoài tự đặt header identity. Cần xác định rõ proxy đang đại diện cho client nào và backend tin proxy dựa trên cơ chế gì.

### 8.3. Certificate rotation

Credential ngắn hạn giảm thời gian lộ key, nhưng rotation cần overlap hợp lý:

- Agent lấy certificate mới trước khi certificate cũ hết hạn.
- Client/server reload certificate mà không làm mất kết nối đang hoạt động ngoài policy.
- Trust bundle được phân phối và cập nhật an toàn.
- Certificate cũ bị từ chối sau expiry/revocation theo SLA.
- Private key không xuất khỏi nơi lưu được bảo vệ nếu nền tảng hỗ trợ.

## 9. Service-to-service authentication bằng token

OAuth 2.0 client credentials hoặc workload identity federation thường được dùng khi workload cần access token cho API.

### 9.1. Client credentials

Trong mô hình truyền thống, confidential client xác thực với authorization server bằng client secret hoặc private key và yêu cầu access token. Client secret tĩnh có thể bị sao chép; nên ưu tiên private-key authentication, mTLS hoặc federation nếu nền tảng hỗ trợ.

Token cần:

- Issuer được tin cậy.
- Audience là API/resource server cụ thể.
- Scope/permission tối thiểu.
- Expiry ngắn phù hợp.
- Client/subject identity rõ.
- Sender constraint khi threat model yêu cầu.

### 9.2. Audience và confused deputy

Audience giúp token chỉ được chấp nhận bởi resource server dự kiến. Nếu API A chấp nhận token dành cho API B, attacker có thể dùng một token hợp lệ ở sai nơi. Mỗi resource server cần kiểm tra audience của chính nó, không chỉ kiểm tra chữ ký.

Confused deputy xảy ra khi một service có quyền rộng bị thuyết phục thực hiện hành động thay cho caller không đủ quyền. Service phải phân biệt identity của caller và identity của chính workload; khi gọi downstream, cần quyết định rõ dùng workload authority hay delegated user authority, không trộn hai principal.

### 9.3. Delegated user context và workload context

Một backend có thể gọi API thay mặt người dùng hoặc bằng quyền riêng của service:

- **Workload identity:** “Đây là service báo cáo đang gọi.”
- **User/delegated identity:** “Service đang hành động thay mặt người dùng X.”

Khi cần cả hai, token/authorization context phải thể hiện rõ caller, subject và delegation. Không nâng quyền người dùng chỉ vì backend có quyền rộng; áp dụng policy theo cả user và workload.

## 10. Secretless authentication và credential ngắn hạn

Secretless không có nghĩa là không có credential. Nó có nghĩa ứng dụng không phải giữ một secret tĩnh dài hạn trong source code/config; runtime nhận credential tạm thời từ identity platform dựa trên bằng chứng đáng tin cậy.

### Lợi ích

- Giảm secret sprawl trong repository, container image, CI/CD và file cấu hình.
- Credential tự hết hạn, giảm cửa sổ lạm dụng khi bị lấy cắp.
- Centralized issuance, policy, audit và revocation.
- Có thể gắn identity với workload/environment thay vì chỉ một chuỗi API key.

### Giới hạn

- Runtime bị chiếm vẫn có thể sử dụng credential hiện tại.
- Identity authority hoặc trust policy bị cấu hình sai có thể cấp credential cho workload attacker.
- Token ngắn hạn không tự ngăn replay trong thời hạn còn hiệu lực.
- Availability của identity provider ảnh hưởng khả năng cấp/làm mới credential.
- Cần kiểm soát cache, clock skew, rotation và outage.

Không đặt credential ngắn hạn vào log hoặc truyền qua nhiều service không cần thiết. Cũng không tạo một bootstrap secret dài hạn để lấy credential ngắn hạn nếu có thể dùng node attestation, managed identity hoặc federation an toàn hơn.

## 11. Authorization: identity không đồng nghĩa quyền

Authentication trả lời “workload nào đang gọi?” Authorization trả lời “workload đó được phép làm gì trên resource này?”. Attestation trả lời “bằng chứng về môi trường chạy có đáp ứng điều kiện cấp identity không?”.

Ví dụ:

- Identity: checkout service trong production namespace.
- Authentication: certificate/token chứng minh workload sở hữu identity đó.
- Authorization: checkout được phép gọi payment authorization endpoint với scope cụ thể.
- Attestation: workload chạy trong namespace/image/node đáp ứng policy được phê duyệt.

Không cấp quyền admin chỉ vì workload có identity hợp lệ. Áp dụng least privilege, resource-specific scope, environment separation và policy theo hành động. Đánh giá quyền định kỳ khi service thay đổi nhiệm vụ hoặc dependency.

### 11.1. Principal mapping

Resource server nên ánh xạ identity từ claim/SAN đã xác minh sang principal nội bộ. Không dùng display name, DNS alias hoặc header tùy ý làm principal. Mapping cần có namespace/trust domain để tránh hai workload cùng tên ở hai tổ chức bị coi là một.

### 11.2. Tenant isolation

Với SaaS multi-tenant, workload identity cần phân biệt service của platform với service do tenant quản lý. Token phải ràng buộc tenant/audience và authorization phải kiểm tra tenant context. Không để service identity toàn cục vô tình có quyền đọc dữ liệu của mọi tenant.

## 12. Các kiểu tấn công và biện pháp phòng chống

| Mối đe dọa | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| Static secret theft | API key/client secret bị lấy từ repo, image hoặc env | Managed identity/federation, secret manager, scan, rotation |
| Workload impersonation | Attacker giả service name/namespace/header | Credential có chữ ký, attestation, principal mapping |
| Token theft/replay | Token bị sao chép và dùng lại | TTL ngắn, audience, sender constraint, replay detection, revoke |
| Metadata SSRF | Workload bị dụ gọi cloud metadata endpoint và lấy credential | Metadata protection, egress controls, IMDS hardening, workload isolation |
| Overbroad federation | Trust policy chấp nhận quá nhiều issuer/subject/branch | Exact issuer/subject/audience, conditions, review và audit |
| Confused deputy | Service dùng quyền riêng rộng thay cho caller không đủ quyền | Caller/subject separation, delegation policy, least privilege |
| Trust bundle compromise | CA/root hoặc JWKS trust bị thay | Protected distribution, pinning/policy, rotation, audit |
| Node/control-plane compromise | Attacker tạo workload hoặc lấy attestation context | Harden orchestrator, admission control, node identity, segmentation |
| Credential leakage in logs | Token/certificate/private key bị ghi vào telemetry | Redaction, secret scanning, access control, retention |
| Stale identity after decommission | Workload bị xóa nhưng token/key vẫn active | Identity inventory, revoke, short TTL, validator confirmation |
| Cross-environment confusion | Staging credential được chấp nhận ở production | Trust domain/audience/environment separation |
| Supply-chain compromise | Image hoặc build pipeline bị thay | Image signing/verification, provenance, protected CI/CD, attestation |

### 12.1. Metadata service abuse

Một số cloud platform cung cấp credential tạm thời qua metadata/identity endpoint. Nếu ứng dụng có SSRF hoặc attacker kiểm soát request routing, họ có thể tìm cách truy cập endpoint đó từ workload. Biện pháp gồm:

- Dùng cơ chế metadata session/token bắt buộc nếu nền tảng hỗ trợ.
- Chặn SSRF tới link-local/metadata address và kiểm soát redirect/DNS resolution.
- Giới hạn egress và chỉ cho workload được phép gọi endpoint.
- Không để proxy forward metadata response tới client bên ngoài.
- Giới hạn role của workload và theo dõi request bất thường.

Chỉ chặn địa chỉ metadata ở một lớp không đủ nếu ứng dụng có proxy hoặc đường mạng khác; cần defense in depth.

### 12.2. Supply chain và image identity

Nếu identity issuance dựa trên image name hoặc tag dễ thay đổi, attacker có thể đẩy image độc hại cùng tag để được cấp identity production. Dùng image digest, signature/provenance và policy deployment; kiểm soát ai được sửa pipeline, registry và admission rule. Attestation cần chứng minh nguồn gốc triển khai phù hợp, không chỉ tên container.

## 13. Rotation, revocation và incident response

Workload credential thường ngắn hạn, nhưng identity và quyền có thể tồn tại lâu hơn. Khi có sự cố, cần thu hồi cả credential và binding/permission liên quan.

### Khi workload bị compromise

1. Xác định workload identity, trust domain, environment và credential family.
2. Ngăn workload tạo credential mới bằng cách suspend/revoke identity issuance.
3. Revoke certificate/token hiện tại và thu hồi session/grant liên quan.
4. Cô lập pod/VM/node hoặc pipeline bị ảnh hưởng.
5. Kiểm tra quyền workload đã dùng và các downstream resource bị truy cập.
6. Rotate key/secret nếu có dấu hiệu bị lộ.
7. Redeploy từ image/provenance đã xác minh hoặc tạo workload identity mới.
8. Khôi phục quyền tối thiểu, theo dõi hoạt động và ghi audit.

### Revocation propagation

Certificate, JWT và cloud access token có cơ chế thu hồi khác nhau. Certificate có thể dựa vào CRL/OCSP hoặc trust bundle; opaque token có thể introspect; JWT tự xác minh có thể còn hợp lệ tới expiry nếu resource server không kiểm tra revoke state. Cần xác định SLA cho từng validator và không tuyên bố thu hồi tức thời nếu chưa có cơ chế thực tế.

### Decommission và orphan cleanup

Khi service bị xóa, tìm API key, certificate, federation subject, role binding, cloud service account, secret, token grant, mesh registration và CI/CD variable liên quan. Thu hồi ở issuer, truyền tới validator, kiểm tra từ chối credential cũ rồi xóa bản sao theo retention. Giữ tombstone/reference tối thiểu để event cũ không tạo lại identity đã decommission.

## 14. Ví dụ luồng: checkout gọi payment service

Một kiến trúc thương mại điện tử có checkout service và payment service. Checkout cần gọi endpoint authorize của payment nhưng không được truy cập trực tiếp dữ liệu thẻ hoặc thao tác quản trị.

### Thiết kế

1. Checkout được khai báo identity trong production trust domain.
2. Runtime attestor xác minh pod/VM chạy trong namespace và service account được phê duyệt.
3. Identity issuer cấp X.509-SVID ngắn hạn hoặc access token có audience là payment API.
4. Checkout mở mTLS connection hoặc gửi token theo giao thức đã chọn.
5. Payment xác minh issuer/trust chain, workload identity, audience, expiry và scope.
6. Authorization policy chỉ cho checkout gọi endpoint authorize với các giới hạn nghiệp vụ đã định.
7. Payment ghi audit principal của caller và transaction reference; không ghi credential.
8. Credential tự rotate; nếu checkout bị compromise, authority revoke identity/certificate và payment từ chối theo SLA.

### Phân biệt caller và quyền service

Nếu checkout xử lý đơn hàng của user Alice, payment cần biết cả workload checkout và user/transaction context phù hợp. Không dùng quyền riêng của checkout để bỏ qua giới hạn của Alice. Có thể dùng delegated token hoặc transaction authorization riêng để giữ rõ hai principal.

## 15. Pseudocode: xác minh workload token

Ví dụ khái niệm cho resource server. Trong production, dùng thư viện OAuth/JWT hoặc SPIFFE/TLS đã được duy trì; không tự viết xác minh chữ ký:

~~~ts
async function authorizeWorkloadRequest(request) {
  const token = extractBearerToken(request);
  if (!token) return deny("MISSING_CREDENTIAL");

  const claims = await verifyTokenWithTrustedIssuer(token, {
    allowedIssuers: configuredWorkloadIssuers(),
    expectedAudience: "payment-api",
    allowedAlgorithms: configuredAlgorithms(),
    requireExpiry: true
  });
  if (!claims.valid) return deny("INVALID_TOKEN");

  const principal = mapVerifiedWorkloadIdentity({
    issuer: claims.iss,
    subject: claims.sub,
    trustDomain: claims.trust_domain
  });
  if (!principal) return deny("UNKNOWN_WORKLOAD");

  const policy = await authorizationPolicy.evaluate({
    principal,
    action: request.action,
    resource: request.resource,
    tenant: request.tenant
  });
  if (!policy.allowed) return deny("INSUFFICIENT_PERMISSION");

  return allow({ principalRef: principal.safeReference });
}
~~~

Đây là pseudocode, không phải API cụ thể. Cần xác minh signature, issuer, audience, expiry, not-before, key rotation/JWKS trust và claim semantics. Nếu token có sender constraint, phải xác minh DPoP/mTLS binding ở request thực tế. Không tin trust_domain hoặc subject do client gửi riêng ngoài token đã xác minh. Authorization phải kiểm tra tenant/resource/action và không suy ra quyền từ việc token hợp lệ.

## 16. Tiêu chí chấp nhận và kiểm thử

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Workload được attestation hợp lệ | Issuer cấp identity credential ngắn hạn theo policy |
| Client tự gửi service name trong header | Resource server không coi header đó là identity |
| Token có chữ ký hợp lệ nhưng sai audience | Resource server từ chối |
| Token từ issuer không được tin cậy | Từ chối |
| Staging workload gọi production API | Bị từ chối do trust domain/audience/policy không khớp |
| Workload identity hợp lệ nhưng thiếu scope | Authentication thành công; authorization từ chối |
| Token hết hạn | Từ chối; workload lấy credential mới qua authority |
| Credential bị revoke | Validator từ chối trong SLA đã định nghĩa |
| Workload bị decommission | Không thể lấy credential mới; credential cũ bị từ chối |
| Federation subject quá rộng | Policy review phát hiện; chỉ subject/workflow đã phê duyệt được exchange |
| CI job từ branch không được phép | Không được cấp production role/token |
| Metadata endpoint bị SSRF | Network/runtime controls ngăn workload ngoài phạm vi lấy credential |
| Workload token bị replay từ client khác | Sender constraint hoặc risk/replay controls phát hiện/giảm thiểu theo thiết kế |
| mTLS certificate có SAN không đúng workload | Từ chối dù chain tới CA tin cậy |
| TLS terminate tại proxy | Backend chỉ tin identity assertion từ proxy đã xác thực |
| Trust bundle rotation | Credential hợp lệ tiếp tục hoạt động trong overlap được kiểm soát; CA cũ bị retire đúng lịch |
| Identity authority tạm outage | Workload hiện tại xử lý theo credential TTL/cache policy; không fallback sang secret tĩnh không kiểm soát |
| Attestation evidence stale hoặc replay | Issuer từ chối theo freshness/nonce/policy |
| Hai workload cùng display name nhưng khác trust domain | Được ánh xạ thành principal khác nhau |
| Workload gọi tenant khác | Authorization từ chối theo tenant boundary |
| Audit log được ghi | Có principal/action/resource/result; không có token/private key/secret |

### Chỉ số vận hành

Theo dõi số workload identity active/orphaned, tỷ lệ credential ngắn hạn, thời gian cấp identity, issuance/attestation failure, certificate expiry/revocation lag, token audience rejection, federation exchange theo issuer/subject, quyền service quá rộng, secret scan findings và thời gian decommission. Phân tích theo service/environment để phát hiện identity dùng chung bất thường.

## 17. Bài tập tự kiểm tra

Một nền tảng có ba workload: checkout, payment và reporting. Checkout gọi payment để authorize giao dịch; reporting chỉ được đọc dữ liệu tổng hợp. Cả ba chạy trên Kubernetes ở staging và production. CI/CD pipeline cũng cần credential để deploy.

Hãy:

1. Thiết kế workload ID cho từng service theo trust domain, namespace và service account.
2. Xác định bằng chứng attestation cần kiểm tra trước khi cấp credential.
3. Chọn khi nào dùng X.509-SVID/mTLS, khi nào dùng federated access token.
4. Định nghĩa issuer, audience, subject và scope cho payment/reporting API.
5. Giải thích cách tách staging khỏi production và giới hạn trust của CI/CD workflow.
6. Mô tả rủi ro metadata SSRF, token theft, confused deputy và image supply-chain compromise.
7. Thiết kế rotation/revocation khi checkout bị compromise.
8. Viết test case chứng minh token hợp lệ nhưng sai audience/tenant/scope vẫn bị từ chối.

**Gợi ý đánh giá:** lời giải tốt phải có principal riêng cho từng workload/environment, attestation từ nguồn tin cậy, credential ngắn hạn, audience hẹp, authorization least privilege, quy trình rotation/revoke và audit. Không dùng service name hoặc network location như bằng chứng danh tính độc lập.

---

**Ghi nhớ:** workload identity cho biết **dịch vụ/tiến trình nào đang gọi** dựa trên credential được cấp từ một authority và bằng chứng runtime đáng tin cậy. Hãy tạo principal riêng theo workload và environment, dùng attestation/federation/managed identity để cấp credential ngắn hạn, xác minh issuer–subject–audience và ràng buộc mTLS/DPoP khi cần. Authentication chỉ xác nhận workload; authorization vẫn phải giới hạn action, resource và tenant. Khi workload bị compromise hoặc decommission, ngừng issuance, revoke credential, truyền trạng thái tới mọi validator và xác minh credential cũ bị từ chối.
