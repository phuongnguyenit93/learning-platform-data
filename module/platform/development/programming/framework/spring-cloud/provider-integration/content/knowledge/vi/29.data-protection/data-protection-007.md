# Xoay vòng khóa, thu hồi quyền và ứng phó khi lộ thông tin xác thực

Ứng dụng Spring Boot thường giữ hoặc sử dụng nhiều loại thông tin xác thực: workload identity, API key, OAuth client secret, refresh token, webhook secret, certificate, khóa ký và khóa mã hóa dữ liệu. Nếu một credential bị lộ, người khác có thể giả danh workload, đọc dữ liệu, ký request giả hoặc giải mã dữ liệu đã lưu. Việc xóa credential khỏi file cấu hình không làm credential cũ mất hiệu lực.

Quản lý an toàn cần ba năng lực liên kết với nhau:

- **Rotation:** thay credential/key hiện tại bằng phiên bản mới theo kế hoạch, có kiểm tra chuyển đổi và thời điểm thu hồi phiên bản cũ.
- **Revocation:** chặn credential, token, session hoặc quyền đã cấp khi không còn được phép sử dụng.
- **Incident response:** phát hiện, xác định phạm vi, cô lập, loại bỏ nguyên nhân, khôi phục và kiểm chứng sau khi credential bị lộ hoặc nghi bị lạm dụng.

Rotation định kỳ giảm thời gian tồn tại của credential, nhưng không thay thế xử lý khẩn cấp. Khi biết secret đã bị lộ, ưu tiên containment và revoke; không chờ đến lịch rotation tiếp theo. Với khóa mã hóa dữ liệu, revoke/disable quá sớm có thể khiến ứng dụng và backup không thể giải mã. Vì vậy phải phân biệt credential dùng để xác thực với KEK/DEK đang bảo vệ dữ liệu.

Bài thuộc chương **Bảo vệ dữ liệu** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng. Trọng tâm bài là lập inventory, xoay vòng identity và secret, thu hồi quyền, xử lý compromise, duy trì khả năng khôi phục và kiểm tra audit.

## 1. Mục tiêu học tập và tình huống xuyên suốt

Sau bài học, bạn có thể:

1. Phân biệt rotation, expiration, disable, revoke và destroy.
2. Lập inventory cho credential, certificate, signing key, KEK và DEK.
3. Thiết kế rotation không gián đoạn bằng key ID và overlap window.
4. Dùng workload identity thay cho long-lived access key khi nền tảng hỗ trợ.
5. Xoay API key, OAuth client secret, refresh token, webhook secret và TLS certificate.
6. Quản lý AWS IAM/STS/KMS, Azure Entra ID/Managed Identity/Key Vault và Google IAM/Workload Identity/KMS.
7. Thu hồi quyền và phiên đang hoạt động theo đúng phạm vi ảnh hưởng.
8. Xử lý credential bị lộ trong Git, CI/CD, log, container image hoặc máy developer.
9. Xây dựng playbook incident response có containment, recovery, evidence và post-incident review.
10. Kiểm thử rotation, revoke, rollback, key version và khả năng giải mã backup.

Tình huống: **document-service** chạy trên Kubernetes, lưu file hợp đồng ở object storage và mã hóa DEK bằng KMS. Service dùng workload identity để gọi storage, OAuth client credential để gọi một hệ thống đối tác, webhook secret để xác minh callback và certificate để bảo vệ kết nối nội bộ. Một access key cũ vô tình xuất hiện trong log CI; đội vận hành phải xác định quyền của key, chặn truy cập, xoay các credential liên quan và xác minh dữ liệu không bị truy cập trái phép.

~~~mermaid
flowchart TD
    A["Phát hiện credential có nguy cơ lộ"] --> B["Xác định loại, owner, scope và dependency"]
    B --> C["Đánh giá đang bị lạm dụng hay chỉ có nguy cơ"]
    C --> D["Contain: revoke / disable / deny / isolate"]
    D --> E["Tạo credential hoặc key mới"]
    E --> F["Cập nhật workload và xác minh"]
    F --> G["Thu hồi phiên bản cũ theo kế hoạch"]
    G --> H["Review log, access, data và downstream"]
    H --> I["Lưu evidence + cải tiến guardrail"]
~~~

**Không có một thao tác revoke chung cho mọi loại khóa.** Tắt IAM access key, revoke OAuth refresh token, disable KMS key version và xóa application share grant có semantics và blast radius khác nhau.

## 2. Phân biệt các thao tác trong vòng đời credential

| Thao tác | Ý nghĩa | Ví dụ | Tác động cần hiểu |
| --- | --- | --- | --- |
| Create | Tạo credential/key mới | Tạo client secret mới | Chưa có nghĩa workload đã dùng nó |
| Activate/enable | Cho phép credential/key được sử dụng | Enable access key hoặc KMS key version | Có thể mở quyền mới |
| Rotate | Chuyển sang credential/key mới | Thay secret phiên bản A bằng B | Cần phối hợp sender, receiver và consumer |
| Expire | Hết hạn theo thời gian | OAuth access token hết hạn | Credential cũ không còn hợp lệ theo policy |
| Disable | Tạm ngăn sử dụng | Disable IAM access key | Có thể bật lại nếu phù hợp; dữ liệu được mã hóa bằng key có thể bị ảnh hưởng |
| Revoke | Thu hồi quyền/ủy quyền | Revoke refresh token hoặc application grant | Có thể cần invalidation ở server hoặc policy |
| Delete | Xóa đối tượng credential/key | Xóa IAM access key cũ | Có thể mất khả năng khôi phục hoặc audit metadata |
| Destroy/purge | Hủy key material hoặc xóa vĩnh viễn | Purge key sau soft-delete window | Có thể khiến dữ liệu không thể giải mã |

### 2.1. Rotation không phải revoke

Rotation là quy trình chuyển đổi có kiểm soát. Ví dụ tạo webhook secret B, cấu hình receiver chấp nhận A và B, cập nhật sender dùng B, theo dõi traffic rồi loại bỏ A. Trong overlap window, cả hai secret còn hợp lệ.

Revoke là chặn quyền của credential bị nghi compromise. Nếu secret A đã bị lộ, giữ A hoạt động chỉ để chờ lịch chuyển đổi có thể cho attacker thêm thời gian. Incident response có thể yêu cầu revoke A ngay và chấp nhận một khoảng gián đoạn có kiểm soát.

### 2.2. Expiration không thay thế revocation

Một access token có exp sau 15 phút sẽ tự hết hạn, nhưng attacker có thể dùng token trong 15 phút đó. Nếu token bị lộ, cần cơ chế revoke/introspection/denylist hoặc thu hồi session phù hợp. Với JWT self-contained, resource server có thể không biết token đã bị thu hồi nếu không có state/check bổ sung.

### 2.3. Disable và destroy key mã hóa cần thận trọng

Disable KMS key có thể khiến mọi ứng dụng cần decrypt dữ liệu bằng key đó thất bại. Destroy key material có thể khiến ciphertext, snapshot và backup không thể khôi phục vĩnh viễn. Không xử lý KMS key như một API key có thể xóa ngay sau khi deploy key mới.

### 2.4. Credential rotation và key rotation khác nhau

- Credential rotation thay bí mật hoặc danh tính dùng để xác thực.
- Signing-key rotation thay key ký request/token/certificate.
- KEK rotation thay khóa bảo vệ DEK.
- DEK rotation thay khóa mã hóa payload.
- Database password rotation thay credential kết nối database.
- Certificate rotation thay certificate và có thể cả private key/trust chain.

Mỗi loại cần inventory, dependency, test và kế hoạch rollback riêng.

## 3. Inventory và phân loại credential

Không thể xoay hoặc thu hồi an toàn nếu không biết credential nằm ở đâu và đang được ai sử dụng.

### 3.1. Credential inventory

Mỗi record nên có các trường:

| Thuộc tính | Ví dụ |
| --- | --- |
| Credential ID | payment-api-prod-v3 |
| Type | OAuth client secret |
| Owner | Payment Integration team |
| Consumer | document-service |
| Environment | Production |
| Provider/resource | Entra application / partner API |
| Scope | invoice.write |
| Created at | Thời điểm phát hành |
| Last rotated at | Thời điểm xoay gần nhất |
| Expiry | Thời điểm hết hạn |
| Secret location | Secret Manager/Key Vault/Secret Manager |
| Version/key ID | Resource/version identifier |
| Rotation method | Manual, automated, provider-managed |
| Revocation method | Revoke credential, disable key, policy deny |
| Dependencies | API gateway, worker, batch job |
| Audit | Log và owner chịu trách nhiệm |

Không ghi raw secret hoặc private key vào inventory. Ghi reference tới secret manager và version.

### 3.2. Phân loại theo khả năng ảnh hưởng

| Loại | Ví dụ | Câu hỏi cần đánh giá |
| --- | --- | --- |
| Workload identity | IAM role, managed identity, service account | Có thể giới hạn principal/resource/action đến đâu? |
| Static API credential | API key, database password | Có thể thay bằng short-lived identity không? |
| OAuth credential | Client secret, refresh token | Token nào đã được cấp và audience nào bị ảnh hưởng? |
| Webhook signing secret | HMAC secret | Sender và receiver có hỗ trợ overlap không? |
| Asymmetric signing key | RSA/ECDSA private key | Public key/certificate đã phân phối ở đâu? |
| TLS certificate | Service certificate, CA | Consumer nào tin cậy certificate/issuer? |
| Data encryption key | DEK/KEK | Ciphertext, envelope và backup nào phụ thuộc key? |
| Session credential | Cookie, session ID | Cần invalidate session store hoặc signing key nào? |

### 3.3. Owner và dependency graph

Một secret có thể được dùng bởi nhiều service, job hoặc môi trường. Trước khi rotate cần biết:

- Producer tạo credential.
- Consumer sử dụng credential.
- Secret manager phát hành version.
- Runtime tải secret lúc startup hay refresh định kỳ.
- Connection pool/cache giữ credential cũ bao lâu.
- Downstream có hỗ trợ hai credential đồng thời hay không.
- Log/audit cho biết credential version nào được dùng.
- Rollback có thể quay lại version cũ hay version cũ phải bị revoke ngay.

Với credential compromise, graph này giúp khoanh vùng blast radius và tìm credential phụ thuộc có thể bị lộ theo.

### 3.4. Ưu tiên loại bỏ long-lived secrets

Ưu tiên:

1. Workload identity hoặc federated identity.
2. Short-lived access token/temporary credentials.
3. Secret manager cấp phát và version hóa secret.
4. Static key có TTL, scope hẹp, rotation và audit nếu không có lựa chọn khác.

Không đưa credential cloud dài hạn vào source code, Docker image, Helm values công khai, Terraform state không được bảo vệ, CI variable không giới hạn hoặc file .env được commit.

## 4. Quy trình rotation không gián đoạn

### 4.1. Mô hình overlap

Một quy trình thông dụng:

~~~mermaid
sequenceDiagram
    participant Admin as Operator
    participant SM as Secret Manager
    participant App as Spring Boot
    participant Provider as External Provider
    Admin->>SM: Create secret version B
    SM-->>App: Publish reference/version B
    App->>Provider: Authenticate using B
    Provider-->>App: Success
    App->>Provider: Continue accepting A during overlap
    Admin->>Provider: Retire/revoke credential A
    Provider-->>App: A no longer valid
    App->>Provider: Verify B still works
~~~

Trình tự:

1. Xác định owner, consumers, expiry, scope và cách revoke.
2. Kiểm tra provider có hỗ trợ nhiều credential active hay không.
3. Tạo version mới B.
4. Phân phối B qua secret manager hoặc workload identity.
5. Cập nhật một instance/canary trước.
6. Xác minh request mới dùng B thành công.
7. Chuyển toàn bộ workload và job sang B.
8. Theo dõi lỗi xác thực, traffic còn dùng A và downstream.
9. Thu hồi A khi hết overlap window.
10. Xác minh A bị từ chối và B tiếp tục hoạt động.
11. Cập nhật inventory, audit và thời điểm rotation.

### 4.2. Overlap window

Overlap phải đủ dài để cập nhật tất cả consumer nhưng không kéo dài quá mức cần thiết. Cần xét:

- Chu kỳ deploy và restart.
- Autoscaling instance mới.
- Batch job chạy theo lịch.
- Worker/queue consumer chạy lâu.
- Cache secret và connection pool.
- Retry window của webhook/event.
- Client bên ngoài không thể deploy đồng thời.

Không giữ hai secret hoạt động vô thời hạn. Đặt deadline, alert và owner cho việc retire key cũ.

### 4.3. Khi nào không thể overlap?

Một số provider chỉ cho một key hoặc có một số lượng key giới hạn. Khi đó:

- Dùng maintenance window nếu cần.
- Chuẩn bị deploy/config trước thao tác cutover.
- Có rollback credential mới nếu chưa bị compromise.
- Với compromise, ưu tiên revoke ngay; chấp nhận downtime nếu cần để chặn attacker.
- Nếu provider cho phép tạo credential mới nhưng không thể có hai key cùng lúc, dùng cơ chế migration/bridge do provider hỗ trợ.

### 4.4. Rotation tự động và thủ công

Rotation tự động phù hợp khi provider hỗ trợ API và secret manager có thể phối hợp update consumer. Nhưng tự động hóa không loại bỏ nhu cầu kiểm tra:

- Secret mới được tạo đúng scope?
- Consumer thực sự đã tải version mới?
- Connection pool đã mở lại bằng credential mới?
- Credential cũ đã bị revoke?
- Có cảnh báo nếu rotation thất bại?
- Có thể phục hồi nếu secret mới không hoạt động?

Rotation thủ công cần checklist, change record, owner, thời gian và bằng chứng xác minh. Không dùng lịch nhắc đơn thuần làm bằng chứng credential đã được thay.

## 5. Xoay vòng API key, OAuth secret và session token

### 5.1. API key

API key là bearer credential. Thiết kế tốt nên có:

- Key ID công khai để tra cứu, không phải secret.
- Secret entropy cao được hiển thị một lần.
- Hash secret lưu ở database nếu chỉ cần xác minh.
- Scope/resource/action rõ ràng.
- Expiry và last-used timestamp.
- Quota/rate limit.
- Owner và trạng thái active/revoked.
- Audit khi tạo, rotate, dùng và revoke.

Khi rotate, tạo key mới, cập nhật consumer, xác minh key mới rồi revoke key cũ. Nếu key bị lộ, revoke ngay và điều tra các request đã dùng key đó.

### 5.2. OAuth client secret

Với client credentials flow:

1. Tạo client secret/certificate mới ở authorization server.
2. Lưu secret version vào secret manager.
3. Cập nhật Spring Boot client registration.
4. Xác minh token mới có đúng issuer, audience, scope và expiry.
5. Chuyển traffic sang credential mới.
6. Revoke client secret cũ.
7. Theo dõi token issuance và resource access.

Client secret mới chỉ ảnh hưởng việc xin token tiếp theo. Access token đã phát hành trước đó có thể tiếp tục hợp lệ tới exp nếu authorization server/resource server không có cơ chế revoke/introspection.

### 5.3. Refresh token

Refresh token có thể cấp access token mới nên cần bảo vệ chặt hơn access token:

- Revoke token hoặc token family khi phát hiện compromise.
- Dùng refresh-token rotation và reuse detection nếu authorization server hỗ trợ.
- Invalidate session theo user/client.
- Không chỉ xóa token ở browser/local storage rồi coi đã revoke.
- Xác minh server-side revocation và token family state.
- Xem xét access token đã được cấp từ refresh token bị lộ có còn hiệu lực không.

### 5.4. JWT signing key

Khi xoay key ký JWT:

1. Tạo key pair mới và publish public key/JWKS với key ID mới.
2. Verifier phải tin cả public key cũ và mới trong overlap.
3. Issuer chuyển sang ký token mới bằng private key mới.
4. Theo dõi verifier đã tải JWKS mới.
5. Chờ token cũ hết TTL hoặc thực hiện revoke theo cơ chế hỗ trợ.
6. Gỡ public key cũ sau khi không còn token hợp lệ phụ thuộc nó.

Không xóa public key cũ ngay khi issuer bắt đầu ký bằng key mới; access token cũ có thể còn hiệu lực. Nếu private signing key bị lộ, cần chuyển key ký ngay và đánh giá token đã phát hành trong thời gian compromise.

### 5.5. Webhook secret

Webhook HMAC thường cần current/previous secret:

- Header key ID xác định secret version.
- Receiver xác minh với key ID được phép.
- Sender chuyển sang secret mới.
- Giữ secret cũ trong overlap chỉ đủ cho retry window.
- Sau đó revoke secret cũ.
- Nếu secret bị lộ, không kéo dài overlap vì tiện lợi; phối hợp đổi key và chặn request giả.
- Event ID/inbox vẫn cần để chống replay; đổi secret không xóa duplicate risk.

## 6. Certificate và TLS private key rotation

### 6.1. Certificate lifecycle

Certificate có public certificate, private key, issuer/CA, SAN, validity period và chain. Expiry là cơ chế tự hết hạn, nhưng compromise private key cần revoke/replace sớm.

- Theo dõi ngày hết hạn và issuer.
- Kiểm tra SAN/hostname.
- Phân phối trust chain mới trước khi cutover nếu CA thay đổi.
- Deploy private key mới vào secret/certificate store.
- Reload application/proxy hoặc rolling restart theo khả năng.
- Xác minh handshake và mutual TLS từ các consumer thực tế.
- Thu hồi certificate cũ theo CA/PKI policy khi cần.

### 6.2. Không chỉ kiểm tra ngày hết hạn

Certificate có thể còn hạn nhưng private key đã bị lộ. Khi compromise:

1. Tạo key pair mới; không tái sử dụng private key cũ.
2. Phát hành certificate mới.
3. Cập nhật server/client identity.
4. Cập nhật trust/revocation nếu có.
5. Thu hồi certificate cũ tại CA hoặc policy tương ứng.
6. Kiểm tra connection log và các client còn dùng certificate cũ.

CRL/OCSP và client revocation checking có khác biệt theo TLS stack. Không giả định mọi client kiểm tra revocation giống nhau; kiểm thử hành vi thực tế.

## 7. Quản lý AWS credentials và KMS

### 7.1. IAM access key và STS

Ưu tiên IAM role và temporary credentials cho EC2, ECS, EKS, Lambda hoặc workload federation. Static IAM user access key nên được giảm tối đa.

Nếu buộc phải rotate access key:

1. Tạo access key mới khi quota cho phép.
2. Cập nhật secret store và consumer.
3. Kiểm tra CloudTrail cho thấy request sử dụng key mới.
4. Deactivate key cũ.
5. Theo dõi lỗi trong thời gian rollback cho phép.
6. Delete key cũ sau khi xác minh không còn consumer.

Nếu key bị lộ, deactivate ngay, điều tra CloudTrail, IAM activity và tài nguyên có thể truy cập. Không chỉ xóa key khỏi source repository.

Temporary STS credentials có thời hạn và quyền bị giới hạn bởi role session/policy. Nếu nghi session đang bị lạm dụng, cần xem xét revoke active sessions hoặc policy deny theo hướng dẫn AWS; thao tác này có thể ảnh hưởng nhiều session của role.

### 7.2. AWS Secrets Manager

Secrets Manager lưu secret và hỗ trợ version stage như AWSCURRENT, AWSPREVIOUS và AWSPENDING trong rotation workflow.

- Tạo secret version mới.
- Thử credential mới với hệ thống đích.
- Chuyển stage current khi xác minh thành công.
- Consumer refresh secret theo cache policy.
- Thu hồi credential cũ ở hệ thống đích.
- Giữ version cũ chỉ theo retention và rollback policy.

Rotation Lambda/automation phải idempotent. Nếu workflow chạy lại sau timeout, không tạo thêm credential không kiểm soát hoặc xóa credential đang dùng.

### 7.3. AWS KMS key rotation

Cần phân biệt:

- Automatic rotation cho symmetric customer managed KMS key: KMS tạo key material mới nhưng giữ khả năng decrypt ciphertext cũ bằng key material version tương ứng.
- Manual rotation bằng cách tạo KMS key mới: key ARN/ID khác; ứng dụng và resource phải chuyển sang key mới.
- Re-encrypt/rewrap: cần thực hiện riêng nếu muốn dữ liệu/DEK chuyển sang key mới.
- Disable key: thao tác này có thể làm decrypt thất bại cho mọi dữ liệu phụ thuộc key.

Automatic rotation không làm key ARN đổi và không đồng nghĩa re-encryption toàn bộ dữ liệu. Lưu key reference và giữ key cũ trong suốt vòng đời ciphertext/backup.

### 7.4. Khi IAM key bị lộ

Containment có thể gồm:

- Deactivate access key hoặc revoke session theo mức độ.
- Thêm deny policy cho resource/action bị ảnh hưởng nếu cần.
- Xoay downstream credential mà principal có thể đọc.
- Kiểm tra CloudTrail, S3 data events nếu đã bật, KMS events, IAM changes và resource policy.
- Tìm key trong CI logs, artifact, container image, Git history và developer machine.
- Kiểm tra tạo user/role/policy, access key, bucket policy hoặc KMS grant bất thường.

Không giả định CloudTrail đã bật mọi data event; kiểm tra cấu hình log thực tế và các khoảng trống quan sát.

## 8. Quản lý Azure credentials và Key Vault

### 8.1. Microsoft Entra application credential

Với service principal/app registration:

- Ưu tiên managed identity cho workload Azure khi có thể.
- Nếu dùng client secret, tạo secret mới và cập nhật consumer trước khi xóa secret cũ nếu không có compromise.
- Cân nhắc certificate credential hoặc federated identity credential thay client secret.
- Giới hạn API permission, app role, tenant và resource.
- Theo dõi sign-in logs/service principal sign-in logs.
- Xóa credential cũ sau khi xác minh consumer đã chuyển.

Client secret có expiration date; đặt alert trước ngày hết hạn. Không đặt secret quá dài chỉ để giảm công vận hành.

### 8.2. Managed identity

Managed identity không yêu cầu ứng dụng giữ client secret. Nền tảng cấp token ngắn hạn cho workload. Khi cần thu hồi:

- Gỡ role assignment/RBAC hoặc app role không còn cần.
- Disable/delete identity khi workload không còn tồn tại.
- Thu hồi quyền ở resource scope phù hợp.
- Xác minh token/session đã cấp và thời gian hiệu lực còn lại theo cơ chế Entra/resource.
- Kiểm tra các workload khác đang dùng cùng identity.

Không chia sẻ một managed identity quá rộng cho nhiều service chỉ vì thuận tiện. Tách identity giúp giảm blast radius.

### 8.3. Azure Key Vault key và secret versions

Key Vault hỗ trợ version hóa key/secret. Rotation cần phối hợp consumer:

- Tạo version mới hoặc rotation policy.
- Consumer đọc đúng version/current version theo thiết kế.
- Kiểm tra key operation hoặc secret retrieval thành công.
- Giữ version cũ nếu ciphertext, certificate hoặc ứng dụng còn phụ thuộc.
- Thu hồi quyền của principal cũ khi cần.
- Dùng soft-delete và purge protection theo policy để giảm nguy cơ xóa nhầm.

Key Vault key rotation không tự động re-encrypt mọi payload do ứng dụng tự mã hóa. Nếu KEK bảo vệ DEK, có thể rewrap DEK sang version mới; nếu cần đổi DEK thì phải re-encrypt payload.

### 8.4. Ứng phó credential Azure bị lộ

- Revoke/delete client secret hoặc certificate credential bị lộ.
- Xoay credential mới và cập nhật workload.
- Disable service principal hoặc managed identity nếu compromise nghiêm trọng và có thể chịu downtime.
- Gỡ RBAC role assignment rộng.
- Kiểm tra Entra sign-in logs, audit logs, Key Vault diagnostic logs và Azure Activity Log.
- Kiểm tra Key Vault access, secret versions, key operations và resource changes.
- Nếu Storage SAS bị lộ, xác định loại SAS và signing key/policy; không giả định mọi SAS revoke giống nhau.

## 9. Quản lý Google Cloud credentials và Cloud KMS

### 9.1. Service account key và Workload Identity

Ưu tiên Workload Identity Federation hoặc Workload Identity cho workload thay service account JSON key dài hạn.

Nếu buộc phải dùng service account key:

1. Tạo key mới theo policy.
2. Cập nhật consumer/secret store.
3. Xác minh workload sử dụng key mới.
4. Disable key cũ.
5. Kiểm tra lỗi và audit.
6. Delete key cũ sau khi xác minh.

Service account key có thể bị tải xuống và sao chép; xóa file khỏi container không revoke key đã phát hành. Phải disable/delete key ở IAM.

### 9.2. Disable service account khác disable key

- Disable một service account có thể làm gián đoạn mọi workload dùng identity đó.
- Disable một key cụ thể ảnh hưởng credential key đó.
- Gỡ IAM binding làm thay đổi quyền principal trên resource.
- Revoke token/session có semantics riêng và không phải mọi access token đều bị vô hiệu hóa tức thì.

Xác định phạm vi compromise trước khi chọn thao tác. Nếu private key JSON bị lộ, disable key đó sớm; nếu service account identity bị kiểm soát hoàn toàn, cần containment rộng hơn.

### 9.3. Cloud KMS key versions

Google Cloud KMS symmetric key có CryptoKey và các CryptoKeyVersion:

- Tạo version mới và chuyển primary version để encryption mới dùng version mới.
- Decrypt ciphertext cũ vẫn cần version cũ còn enabled.
- Disable version cũ chỉ sau khi không còn dữ liệu/backup phụ thuộc hoặc đã hoàn tất rewrap/re-encryption.
- Destroy version là hành động không thể đảo ngược sau khi hết destruction delay.
- Rotation schedule tạo version mới; không tự động re-encrypt mọi dữ liệu.

Cần lưu CryptoKey resource và version metadata theo format dữ liệu. Không xóa version cũ chỉ vì primary version đã thay đổi.

### 9.4. Kiểm tra compromise

Kiểm tra Cloud Audit Logs, service account key creation, IAM policy changes, KMS encrypt/decrypt operations, service account impersonation và workload identity federation. Xem xét project/folder/org scope để xác định quyền attacker có thể kế thừa.

## 10. Xây dựng rotation-aware configuration trong Spring Boot

### 10.1. Không đặt raw secret trong application.yml

Cấu hình chỉ nên giữ reference hoặc tên secret:

~~~yaml
app:
  integrations:
    payment:
      secret-reference: payment-provider/prod/webhook
      active-key-id: payment-2026-03
      previous-key-id: payment-2026-02
      previous-key-valid-until: 2026-12-01T00:00:00Z
~~~

Các giá trị trên là metadata tham khảo. Không đưa raw secret, private key, access token hoặc connection password vào file cấu hình được commit.

### 10.2. Tách secret retrieval khỏi nghiệp vụ

~~~java
import java.time.Instant;

public interface SecretVersionProvider {
    SecretValue get(String secretReference, String version);
}

public record SecretValue(
        String keyId,
        byte[] value,
        Instant createdAt,
        Instant expiresAt) {
}
~~~

Adapter có thể đọc từ AWS Secrets Manager, Azure Key Vault hoặc Google Secret Manager. Business service phụ thuộc interface, không phụ thuộc một cloud SDK cụ thể.

Trong production:

- Defensive copy byte array.
- Không trả secret qua toString/logging.
- Kiểm soát TTL cache và refresh.
- Hạn chế số principal có quyền đọc secret.
- Có timeout, retry có giới hạn và circuit breaker phù hợp.
- Không fallback sang hard-coded secret khi secret manager lỗi.
- Nếu không thể xác thực an toàn, fail closed.

### 10.3. Xác minh theo key ID

Khi sender gửi key ID, receiver chỉ chọn một trong các version đang được phép:

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.Map;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class RotatingHmacVerifier {
    private final Map<String, byte[]> acceptedKeys;

    public RotatingHmacVerifier(Map<String, byte[]> acceptedKeys) {
        Map<String, byte[]> copy = new HashMap<>();
        acceptedKeys.forEach((id, key) -> copy.put(id, key.clone()));
        this.acceptedKeys = Map.copyOf(copy);
    }

    public boolean verify(
            String keyId,
            byte[] message,
            byte[] suppliedMac) throws GeneralSecurityException {

        if (keyId == null || message == null) {
            return false;
        }

        byte[] secret = acceptedKeys.get(keyId);
        if (secret == null || suppliedMac == null || suppliedMac.length != 32) {
            return false;
        }

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        byte[] expected = mac.doFinal(message);
        return MessageDigest.isEqual(expected, suppliedMac);
    }
}
~~~

Đây là ví dụ minh họa. Map phải được tạo từ secret versions được phép theo thời gian, không chứa key đã revoke. Không thử mọi secret vô hạn hoặc chấp nhận key ID do client tự chọn mà không kiểm tra allowlist.

### 10.4. Refresh secret an toàn

Có thể dùng scheduled refresh, Spring Cloud refresh mechanism hoặc rolling deployment. Chọn theo loại credential:

- Với password database, cập nhật secret và connection pool có kế hoạch drain/recreate.
- Với OAuth client secret, refresh token cache hoặc client registration rồi xác minh token mới.
- Với webhook HMAC, receiver có thể chấp nhận hai key theo key ID trong overlap.
- Với TLS certificate, reload connector/proxy và xác minh handshake.
- Với KMS key reference, cập nhật config sau khi đã kiểm chứng decrypt path.

Không refresh tất cả secret cùng lúc nếu có thể tạo một thay đổi diện rộng khó rollback.

### 10.5. Không giữ credential trong heap lâu hơn cần thiết

Java không bảo đảm xóa hoàn toàn mọi bản sao byte array do JVM/provider tạo. Tuy vậy có thể:

- Giới hạn thời gian giữ secret trong memory.
- Không serialize secret object.
- Tránh heap dump/core dump không kiểm soát.
- Bảo vệ process access và debug endpoint.
- Không đặt secret trong exception message.
- Dùng byte array và best-effort zeroization khi có thể.
- Không cache credential vô thời hạn.

## 11. Ứng phó khi lộ credential: playbook

### 11.1. Chuẩn bị trước incident

Chuẩn bị sẵn:

- Credential inventory và owner/on-call.
- Cách revoke theo từng provider và loại credential.
- Quyền break-glass có kiểm soát.
- Audit log và retention.
- Contact của provider/security team.
- Quy trình rotation khẩn cấp và rollback.
- Danh sách downstream dependency.
- Kịch bản kiểm thử backup/decrypt.
- Mẫu incident record và timeline.

Không chờ tới lúc compromise mới tìm cách disable access key hoặc xác định ai quản lý KMS key.

### 11.2. Detect và triage

Nguồn phát hiện có thể là:

- Secret scanning báo key trong Git.
- CI/CD log hoặc artifact chứa secret.
- Provider alert về access bất thường.
- Sign-in log từ IP/region lạ.
- API rate tăng bất thường.
- IAM role/key được dùng ngoài lịch.
- KMS decrypt hoặc secret retrieval tăng đột biến.
- Credential hết hạn hoặc bị revoke làm service lỗi.

Triage cần trả lời:

1. Credential loại gì và version/key ID nào?
2. Secret bị lộ ở đâu, từ khi nào và ai có thể truy cập?
3. Credential còn active không?
4. Scope, resource, tenant, region và action nào được cấp?
5. Có bằng chứng đã bị sử dụng không?
6. Có credential khác được đọc từ secret manager bằng credential này không?
7. Có dữ liệu bị đọc/export/thay đổi không?
8. Có phụ thuộc cần phối hợp để tránh mất dữ liệu hoặc downtime không?

Nếu chưa rõ mức độ, coi credential có khả năng compromise cho tới khi có bằng chứng đáng tin cậy.

### 11.3. Containment

Mục tiêu là chặn attacker sử dụng credential và giới hạn blast radius:

- Disable/revoke credential bị lộ.
- Revoke refresh token/session hoặc application grant liên quan.
- Deny principal ở resource policy nếu cần.
- Tạm dừng workload hoặc endpoint bị compromise.
- Rotate credential downstream mà attacker có thể đã đọc.
- Chặn network path hoặc IP nếu có căn cứ.
- Thu hồi quyền secret manager/KMS cho principal bị chiếm.
- Cô lập container/VM/pod có dấu hiệu bị kiểm soát.
- Giữ nguyên evidence và log cần điều tra.

**Không xóa ngay log, container image, VM hoặc Git history trước khi lưu evidence cần thiết.** Containment cần ưu tiên chặn truy cập; bảo toàn bằng chứng giúp xác định phạm vi và nghĩa vụ thông báo.

### 11.4. Eradication

Sau khi đã chặn:

- Xóa secret khỏi code/config/CI variables theo quy trình.
- Xóa hoặc thay artifact/image chứa credential.
- Vá nguồn rò rỉ: debug logging, permission rộng, secret mount, build output.
- Xóa persistence hoặc workload/identity do attacker tạo.
- Review IAM/RBAC/policy/grants và key access.
- Xoay các credential có thể bị lộ thứ cấp.
- Quét lại repository, branches, tags, forks, package, image registry và build cache.

Xóa secret khỏi Git history không làm secret cũ mất hiệu lực. Phải revoke trước; history rewrite chỉ là bước giảm lộ về sau và không thể thu hồi bản clone đã tải.

### 11.5. Recovery

- Tạo credential mới với scope tối thiểu.
- Phân phối qua secret manager hoặc workload identity.
- Deploy canary, kiểm tra authentication và business flow.
- Mở lại traffic theo từng phần.
- Xác minh không còn request bằng credential cũ.
- Khôi phục KMS/key permission theo change được duyệt.
- Kiểm tra decrypt/restore dữ liệu cũ trước khi disable key version.
- Theo dõi error rate, auth failure, audit và usage bất thường.

### 11.6. Lessons learned

Sau incident:

- Viết timeline và root cause.
- Ghi credential, resource, data và principal bị ảnh hưởng.
- Đánh giá liệu có cần thông báo khách hàng/cơ quan theo nghĩa vụ áp dụng.
- Cập nhật inventory và rotation deadline.
- Thêm secret scanning, least privilege, alert và test.
- Đánh giá thời gian phát hiện, containment và recovery.
- Không đưa secret hoặc dữ liệu nhạy cảm vào báo cáo sự cố.

## 12. Xử lý theo loại credential bị lộ

| Credential bị lộ | Containment ưu tiên | Recovery và xác minh |
| --- | --- | --- |
| AWS IAM access key | Deactivate key; review CloudTrail và IAM changes | Tạo/ưu tiên role-based identity, rotate downstream secret |
| AWS STS session | Revoke/deny session theo cơ chế AWS phù hợp; scope policy | Xác minh session cũ không còn truy cập và workload mới hoạt động |
| Azure client secret | Delete/revoke credential; kiểm tra sign-in logs | Tạo secret/certificate mới hoặc chuyển managed identity |
| Azure managed identity | Gỡ role assignment/disable identity theo blast radius | Cấp identity mới hoặc thu hẹp scope, kiểm tra Activity/Sign-in logs |
| GCP service account key | Disable/delete key cụ thể | Chuyển Workload Identity, kiểm tra Cloud Audit Logs |
| OAuth refresh token | Revoke token family/session | Cấp phiên mới, đánh giá access token đã phát hành |
| JWT signing private key | Chuyển sang key pair mới; đánh giá token đã ký | Publish JWKS mới, xử lý token cũ/denylist theo threat model |
| Webhook HMAC secret | Chuyển sender/receiver sang secret mới; từ chối key cũ nếu compromise | Xác minh signature, key ID và event inbox |
| TLS private key | Thay key pair/certificate và revoke cert cũ | Cập nhật trust/handshake, kiểm tra client còn dùng cert cũ |
| KMS KEK | Đánh giá data dependency; disable chỉ khi cần containment khẩn cấp | Rotate/rewrap DEK, kiểm tra backup và khả năng decrypt |
| DEK | Coi payload liên quan có thể bị lộ; tạo DEK mới và re-encrypt | Xác minh ciphertext mới, xử lý bản sao/backup theo policy |
| Signed URL/SAS | Revoke grant/key/policy/resource theo loại | Kiểm tra access log; nhớ rằng file đã tải không thể thu hồi từ recipient |

## 13. KMS compromise và khả năng khôi phục dữ liệu

### 13.1. KEK bị lộ không giống DEK bị lộ

Nếu KEK trong KMS bị lạm dụng qua quyền decrypt, attacker có thể unwrap nhiều DEK. Nếu raw KEK material bị compromise, phạm vi có thể còn rộng hơn. Nếu chỉ một DEK bị lộ, phạm vi có thể giới hạn theo object/tenant tùy cách tạo DEK.

Cần xác định:

- KMS operation nào đã xảy ra.
- Principal nào gọi Encrypt/Decrypt/GenerateDataKey/Wrap/Unwrap.
- Encryption context/AAD có được áp dụng đúng không.
- Các DEK/object nào phụ thuộc key.
- Ciphertext và wrapped DEK có bị copy ra ngoài không.

### 13.2. Rewrap và re-encrypt

- **Rewrap DEK:** unwrap DEK bằng KEK cũ rồi wrap lại bằng KEK mới. Payload ciphertext không đổi.
- **Re-encrypt payload:** giải mã bằng DEK cũ rồi mã hóa lại bằng DEK mới. Cần xử lý payload và metadata.
- **Rotate KMS key material:** thay version key material theo khả năng provider; không nhất thiết đổi key resource hoặc mã hóa lại dữ liệu cũ.

Nếu KEK chỉ cần thay vì chính sách rotation, rewrap có thể đủ. Nếu DEK bị lộ hoặc thuật toán/nonce bị sử dụng sai, rewrap không đủ; phải re-encrypt payload bằng DEK mới.

### 13.3. Disable/destroy có thể làm mất dữ liệu

Trước khi disable/destroy key:

- Kiểm kê object, database, backup, snapshot, replica và archive.
- Xác minh key version cần thiết cho decrypt.
- Thực hiện recovery test từ backup.
- Kiểm tra cross-region/cross-account dependency.
- Xác định retention/legal hold.
- Có phê duyệt và change record.
- Xác minh có thể phục hồi key/permission nếu thao tác disable.

Không destroy KMS key chỉ vì đã chuyển primary version hoặc ứng dụng hiện tại đã dùng key mới. Backup cũ có thể vẫn cần key cũ trong nhiều năm.

### 13.4. Khi nào cần chấp nhận downtime?

Nếu KEK bị compromise nghiêm trọng, tiếp tục cho decrypt có thể duy trì đường tấn công. Có thể cần disable key tạm thời và chấp nhận service ngừng đọc dữ liệu. Quyết định cần phối hợp security, service owner, data owner và incident commander, dựa trên blast radius và khả năng phục hồi.

## 14. Kiểm thử rotation, revocation và incident response

### 14.1. Rotation test

- Credential mới được tạo và đọc từ secret manager.
- Canary sử dụng credential mới thành công.
- Autoscaled instance mới không quay lại credential cũ.
- Connection pool được refresh/reconnect.
- Current/previous key overlap đúng thời hạn.
- Credential cũ bị revoke sau cutover.
- Request bằng credential cũ bị từ chối sau revoke.
- Rollback được kiểm tra trong môi trường test khi credential cũ chưa bị compromise.

### 14.2. Revocation test

- API key revoked không còn gọi được API.
- OAuth refresh token bị revoke không cấp access token mới.
- JWT key cũ không được dùng ký token mới; verifier xử lý token cũ theo policy.
- IAM access key bị deactivate không còn request mới thành công.
- Azure client secret cũ bị xóa/disable.
- GCP service account key bị disable.
- Webhook secret cũ bị từ chối sau overlap.
- KMS key version disable làm hành vi decrypt đúng như dự kiến và cảnh báo xuất hiện.

### 14.3. Recovery test

- Khôi phục secret version đúng từ secret manager.
- Khôi phục certificate chain và private key theo quy trình được phép.
- Giải mã envelope cũ bằng key version cũ.
- Restore backup ở môi trường riêng.
- Rewrap DEK và xác minh payload ciphertext không đổi.
- Re-encrypt payload và so sánh checksum plaintext.
- Kiểm tra outbox/inbox và event replay sau khi service khởi động lại.

### 14.4. Incident simulation

Mô phỏng credential xuất hiện trong CI log:

1. Tạo một test key riêng có scope hẹp.
2. Ghi nhận vị trí lộ giả lập.
3. Thực hiện deactivate/revoke theo runbook.
4. Kiểm tra request cũ bị từ chối.
5. Tạo credential mới và deploy canary.
6. Tìm mọi nơi secret được sao chép.
7. Xác minh audit evidence và timeline.
8. Đánh giá thời gian containment và recovery.

Không dùng production secret để diễn tập. Không gửi credential thật vào ticket hoặc chat để minh họa.

### 14.5. Metrics và cảnh báo

Theo dõi:

- Credential gần hết hạn.
- Thời gian từ lần rotation cuối.
- Credential cũ còn request sau cutover.
- Secret retrieval bất thường.
- Failed authentication tăng đột biến.
- IAM/RBAC change ngoài lịch.
- KMS decrypt/unwrap bất thường.
- Service account key/client secret mới được tạo.
- Refresh token reuse hoặc JWT validation failure.
- Rotation automation thất bại hoặc bị stuck ở trạng thái pending.

Alert nên có owner, severity, runbook và đường escalation. Không gửi raw secret hoặc token vào alert.

## 15. Bài tập thực hành tổng hợp

document-service chạy trên Kubernetes và dùng AWS S3/KMS, Azure Key Vault cho một integration, Google Cloud KMS trong môi trường analytics. Một webhook HMAC secret và một OAuth client secret xuất hiện trong CI log.

**Nhiệm vụ:**

1. Lập inventory các credential, key, certificate và principal của service.
2. Xác định quyền, consumer và blast radius của hai secret bị lộ.
3. Deactivate/revoke credential bị lộ và xác minh request mới bị từ chối.
4. Kiểm tra log/audit để tìm hoạt động bất thường trước thời điểm revoke.
5. Tạo webhook secret mới và hỗ trợ overlap có deadline.
6. Xoay OAuth client secret, đánh giá access token đã phát hành.
7. Chuyển workload sang managed identity/role/workload identity nếu có thể.
8. Xoay KEK trong môi trường test, rewrap DEK và kiểm tra decrypt backup.
9. Kiểm tra KMS key version cũ vẫn cần thiết cho object/archive nào.
10. Viết incident timeline, containment record, recovery evidence và post-incident action.
11. Tạo cảnh báo credential expiry và stale key usage.
12. Thực hiện simulation trong môi trường non-production.

**Câu hỏi tự đánh giá:**

- Rotation khác revoke như thế nào?
- Vì sao xóa secret khỏi Git không làm credential mất hiệu lực?
- Vì sao overlap window có lợi cho rotation nhưng nguy hiểm khi secret đã compromise?
- Access token đã cấp trước khi đổi OAuth client secret có tự hết hiệu lực ngay không?
- JWT signing key rotation cần giữ public key cũ trong bao lâu?
- Vì sao IAM role/managed identity an toàn hơn static access key?
- AWS KMS automatic rotation có tự re-encrypt object cũ không?
- Azure Key Vault key version mới có làm ciphertext cũ tự chuyển key không?
- GCP Cloud KMS primary version mới có cho phép disable version cũ ngay không?
- Vì sao disable KMS key có thể gây mất khả năng đọc backup?
- Khi service account key bị lộ, xóa JSON file có đủ không?
- Khi nào cần chấp nhận downtime để containment?
- Vì sao incident response phải giữ evidence trước khi xóa artifact?

**Đáp án định hướng:** rotation là chuyển phiên bản, revoke là chặn credential; Git history/clone vẫn giữ secret nên phải revoke trước; overlap giúp deploy nhưng tăng thời gian key cũ còn hợp lệ; access token cũ thường sống tới exp hoặc cơ chế revoke; verifier cần public key cũ đến khi token cũ hết hạn hoặc bị invalidated; workload identity loại bỏ static secret; KMS rotation không tự re-encrypt; Key Vault/GCP version mới không tự migrate ciphertext; disable key có thể chặn decrypt; xóa file local không revoke cloud key; downtime có thể cần nếu attacker còn quyền; evidence giúp xác định phạm vi và nghĩa vụ xử lý.

## 16. Tài liệu tham khảo chính thức

- [AWS IAM – Rotate access keys](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys-update.html): quy trình tạo key mới, cập nhật ứng dụng, deactivate và xóa key cũ.
- [AWS IAM – Revoke active IAM role sessions](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html): giới hạn và cách chặn session đã phát hành.
- [AWS Secrets Manager – Rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotating-secrets.html): version stages và rotation workflow.
- [AWS KMS – Rotate KMS keys](https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html): automatic/manual rotation và khả năng decrypt ciphertext cũ.
- [Microsoft Entra – Add and manage application credentials](https://learn.microsoft.com/en-us/entra/identity-platform/how-to-add-credentials): client secret, certificate credential và vòng đời credential.
- [Azure Key Vault – Configure key rotation](https://learn.microsoft.com/en-us/azure/key-vault/keys/how-to-configure-key-rotation): rotation policy và key versions.
- [Azure Key Vault – Soft-delete and purge protection](https://learn.microsoft.com/en-us/azure/key-vault/general/soft-delete-overview): bảo vệ key/secret khỏi xóa nhầm hoặc purge sớm.
- [Google Cloud IAM – Service account key rotation](https://cloud.google.com/iam/docs/key-rotation): tạo, cập nhật consumer, disable và xóa key.
- [Google Cloud IAM – Best practices for managing service account keys](https://cloud.google.com/iam/docs/best-practices-for-managing-service-account-keys): giảm key dài hạn và thay bằng workload identity.
- [Google Cloud KMS – Rotate a key](https://cloud.google.com/kms/docs/rotating-keys): primary CryptoKeyVersion và quy trình rotation.
- [OAuth 2.0 Token Revocation – RFC 7009](https://www.rfc-editor.org/rfc/rfc7009): token revocation endpoint và semantics.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): inventory, lifecycle, rotation, access và incident handling.
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html): key lifecycle, backup, rotation, compromise và destruction.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): bảo vệ audit evidence và tránh ghi credential vào log.

**Ghi nhớ:** rotation thay credential theo kế hoạch; revocation chặn credential đã mất niềm tin; incident response giới hạn thiệt hại và xác minh hệ thống phục hồi. Với Spring Boot tích hợp cloud, hãy ưu tiên workload identity, giữ inventory và audit, xoay secret có overlap khi an toàn, revoke ngay khi compromise, và chỉ disable/destroy khóa mã hóa sau khi đã xác minh toàn bộ dữ liệu cùng backup không còn phụ thuộc vào nó.
