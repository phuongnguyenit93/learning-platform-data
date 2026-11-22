# Scope secret theo service và environment

Một hệ thống API thường có nhiều service, nhiều môi trường và nhiều loại credential: database password, API key của nhà cung cấp, OAuth client secret, webhook signing secret, private signing key, certificate và credential kết nối message broker. Nếu tất cả service dùng chung một secret hoặc mọi môi trường cùng đọc một kho secret, một service bị xâm nhập có thể mở rộng sang nhiều hệ thống khác.

**Secret scope** là cách giới hạn secret theo workload, môi trường, mục đích và phạm vi dữ liệu cần truy cập. Một service chỉ nên đọc những secret cần cho chức năng của chính nó trong environment đang chạy. Development, staging và production cần có danh tính, policy và secret material tách biệt. Tên đường dẫn secret giúp tổ chức và tìm kiếm; quyền thực tế phải được thực thi bằng identity và access policy.

Ví dụ, `orders-api` ở production cần database credential chỉ đọc/ghi schema đơn hàng. Nếu cần xử lý thanh toán, nó gọi `payment-adapter` qua API nội bộ đã xác thực; chỉ adapter giữ credential của payment provider. `orders-api` không cần đọc secret của `billing-worker`, không cần credential production trong staging và không cần quyền quản trị secret store. Nếu hai service dùng chung một credential toàn quyền, việc thu hồi hoặc điều tra khi một service bị lộ sẽ khó hơn nhiều.

## 1. Vì sao cần scope secret?

Secret là credential hoặc key có thể cấp quyền truy cập vào tài nguyên. Phạm vi secret quá rộng làm tăng blast radius khi secret hoặc workload bị compromise.

Các tình huống rủi ro:

- Mọi microservice dùng chung một database user có quyền trên toàn bộ database.
- Secret của production được copy vào development để “dễ test”.
- Một Kubernetes service account có quyền đọc toàn bộ secret trong namespace hoặc cluster.
- CI pipeline có quyền đọc tất cả production secret dù chỉ cần deploy một service.
- Một API key của vendor được chia sẻ cho nhiều service; không thể xác định service nào đã sử dụng key.
- Một secret path có tên `prod/orders/db`, nhưng policy lại cho phép mọi workload đọc mọi path.
- Secret của service A bị lộ trong log, nhưng cùng credential đó cũng cho phép service B truy cập.
- Nhân viên hoặc job nền có quyền list/export toàn bộ secret dù chỉ cần đọc một secret cụ thể.

Scope tốt giúp:

1. Giới hạn tác động của một credential bị lộ.
2. Thu hồi hoặc rotate một service mà ít ảnh hưởng service khác.
3. Ngăn môi trường không đáng tin truy cập production.
4. Gắn audit event với đúng workload, environment và mục đích.
5. Tạo policy có thể kiểm thử tự động trong CI/CD.
6. Hỗ trợ phân tách trách nhiệm giữa developer, operator, security và service owner.

### 1.1. Scope không chỉ là tên secret

Đặt tên secret theo cấu trúc `prod/orders-api/database` là hữu ích, nhưng tên không tự tạo ra ranh giới bảo mật. Nếu mọi service đều có quyền `read secrets/*`, attacker có thể đọc secret của service khác bất kể path có được đặt rõ ràng đến đâu.

Một thiết kế scope cần kết hợp:

- **Workload identity:** xác định service/process đang yêu cầu secret.
- **Environment identity:** xác định workload thuộc dev, staging hay production.
- **Resource policy:** giới hạn chính xác secret hoặc nhóm secret mà identity được phép đọc.
- **Operation policy:** giới hạn read, write, rotate, delete, list hoặc administer.
- **Secret purpose:** phân biệt credential runtime, signing key, webhook secret và credential quản trị.
- **Audit:** ghi lại identity, secret reference, operation, kết quả và thời điểm.

### 1.2. Scope là least privilege áp dụng cho credential

Least privilege không chỉ áp dụng cho API endpoint hoặc database role. Nó cũng áp dụng cho secret store và KMS:

- Service chỉ đọc secret cần thiết để chạy.
- Producer chỉ có quyền lấy key dùng để ký hoặc mã hóa message của nó.
- Consumer chỉ có quyền giải mã dữ liệu mà nó cần.
- Runtime workload không có quyền tạo, xóa hoặc đổi policy secret.
- CI/CD không tự động nhận quyền đọc mọi secret chỉ vì nó có thể deploy.
- Developer không dùng credential production trong môi trường local.

## 2. Mô hình scope: service, environment và purpose

Một secret nên được gắn với ít nhất ba chiều:

| Chiều scope | Câu hỏi | Ví dụ |
|---|---|---|
| Service/workload | Ai cần secret? | `orders-api`, `billing-worker` |
| Environment | Workload đang chạy ở đâu? | `dev`, `staging`, `prod` |
| Purpose/resource | Secret dùng để truy cập hoặc làm gì? | Database runtime, payment API, webhook signing |

Có thể thêm chiều tenant, region, data classification hoặc deployment ring nếu kiến trúc yêu cầu. Không nên tạo quá nhiều chiều chỉ để đặt tên phức tạp; mỗi chiều cần gắn với policy có thể thực thi.

Ví dụ inventory:

| Secret | Service | Environment | Purpose | Quyền cần thiết |
|---|---|---|---|---|
| Orders DB runtime credential | `orders-api` | `prod` | Đọc/ghi bảng đơn hàng | Read secret; DB role giới hạn schema |
| Payment provider API key | `payment-adapter` | `prod` | Gọi API thanh toán | Read secret; quyền vendor tối thiểu |
| Webhook signing key | `webhook-dispatcher` | `prod` | Ký outbound webhook | Sign/use key; không export private key nếu KMS hỗ trợ |
| Test DB credential | `orders-api` | `staging` | Kiểm thử tích hợp | Chỉ truy cập staging database |
| Local development credential | Developer sandbox | `dev` | Chạy local | Dữ liệu giả, quyền giới hạn |

### 2.1. Một service, một runtime identity

Mỗi service nên có workload identity riêng cho từng environment. Ví dụ:

```text
orders-api / dev       -> identity: dev-orders-api
orders-api / staging  -> identity: staging-orders-api
orders-api / prod     -> identity: prod-orders-api

billing-worker / prod -> identity: prod-billing-worker
```

Không dùng một identity chung như `backend-service` cho mọi service. Nếu nhiều service dùng cùng identity, secret store không thể phân biệt service nào đang yêu cầu credential và việc thu hồi một service có thể ảnh hưởng tất cả.

Identity có thể được cấp bởi cloud workload identity, Kubernetes service account federation, SPIFFE/SPIRE, managed identity hoặc cơ chế tương đương. Điều quan trọng là credential của workload được cấp tự động, có thời hạn phù hợp và gắn với workload/environment đã xác minh.

### 2.2. Một environment, một trust boundary

Development và staging thường có nhiều người thử nghiệm, dữ liệu giả lập và quyền debug rộng hơn production. Vì vậy:

- Không cho dev/staging identity đọc production secret.
- Không dùng chung database password hoặc API key giữa dev và prod.
- Không đưa production secret vào test fixture, sample config hoặc CI artifact.
- Tách secret store, cloud account/project/subscription hoặc ít nhất policy boundary theo environment.
- Dùng dữ liệu đã giả danh/ẩn danh trong non-production; không copy nguyên dữ liệu production chỉ để test.
- Tách KMS key hoặc key hierarchy theo environment nếu threat model và nền tảng cho phép.

Chỉ thêm `environment=prod` vào tên secret là chưa đủ nếu workload dev vẫn có quyền đọc nó.

### 2.3. Purpose scope

Một service có thể cần nhiều secret nhưng không phải secret nào cũng nên được cấp cùng một quyền:

- Database runtime credential chỉ truy cập database của service.
- Migration credential chỉ dùng bởi job triển khai schema, không cấp cho API runtime.
- Vendor API key chỉ cho phép đúng API/product cần thiết.
- Signing key chỉ được dùng để ký; private key không cần export khỏi KMS/HSM.
- Webhook verification secret chỉ cần cho endpoint nhận webhook tương ứng.
- Monitoring credential chỉ được gửi metrics/logs, không truy cập dữ liệu nghiệp vụ.

Tách credential theo purpose giúp giảm quyền và làm rõ audit. Đừng gộp mọi credential của một service thành một file `.env` có quyền rộng cho toàn bộ process nếu các thành phần có vòng đời khác nhau.

## 3. Thiết kế secret naming và hierarchy

Tên secret nên giúp con người nhận diện service, environment và purpose mà không chứa giá trị bí mật.

Một convention có thể dùng:

```text
<environment>/<service>/<purpose>/<credential-name>

prod/orders-api/database/runtime
prod/orders-api/payment-provider/api-key
prod/webhook-dispatcher/signing/outbound
staging/orders-api/database/runtime
dev/orders-api/database/runtime
```

Hoặc dùng namespace/project riêng cho từng environment rồi đặt tên ngắn hơn:

```text
project: production
  secret: orders-api-database-runtime

project: staging
  secret: orders-api-database-runtime
```

Đây là quy ước tổ chức. Resource policy vẫn phải ràng buộc identity với secret cụ thể.

### 3.1. Tên secret không chứa secret value

Không đặt password, token, email cá nhân hoặc dữ liệu nhạy cảm trong:

- Secret name/path.
- Tag, label, description hoặc annotation.
- KMS encryption context nếu trường đó có thể xuất hiện trong audit/log và chưa được phân loại phù hợp.
- CI job name hoặc deployment metadata.

Tên nên ổn định và không phụ thuộc vào giá trị secret. Nếu API key thay đổi, resource name vẫn giữ nguyên; version của secret thay đổi.

### 3.2. Một secret cho một credential/purpose

Ưu tiên tách các credential có owner, quyền hoặc vòng đời khác nhau. Ví dụ database username/password có thể được lưu cùng một version để cập nhật nguyên tử nếu provider yêu cầu; nhưng database credential và payment API key nên là hai secret riêng.

Nếu gộp nhiều secret vào một JSON blob, mọi consumer có quyền đọc blob có thể nhận tất cả giá trị. Việc chỉ đọc một field sau khi parse không giới hạn quyền tại secret store. Chỉ nhóm các giá trị cùng purpose, cùng consumer và cùng vòng đời.

### 3.3. Secret version và alias

Secret store thường có version hoặc alias như `current`, `previous`, `active`. Cần định nghĩa semantics:

- Version ID bất biến để audit và rollback.
- Alias `current` trỏ tới version được phát hành cho runtime.
- Version cũ có thể được giữ tạm thời cho rotation overlap.
- Version bị thu hồi không được đọc lại chỉ vì alias cache chưa cập nhật.

Không dùng tên `latest` nếu nền tảng có thể thay đổi giá trị ngay giữa một lần deploy mà không có rollout có kiểm soát. Với workload cần tính tái lập, có thể pin version trong deployment rồi cập nhật version có chủ đích. Với credential cần rotation nhanh, có thể dùng alias động nhưng phải hỗ trợ refresh và kiểm soát cache.

## 4. Resource policy phải dựa trên workload identity

Secret manager cần biết chính xác principal đang yêu cầu thao tác. Một policy tốt xác định:

- Principal/workload identity.
- Environment hoặc trust domain.
- Resource secret cụ thể.
- Operation được phép.
- Điều kiện bổ sung như namespace, audience, network hoặc deployment identity nếu cần.

Ví dụ policy dạng khái niệm:

```yaml
principal: workload://prod/orders-api
environment: prod
allow:
  - action: secret.read
    resource: secret://prod/orders-api/database/runtime
deny:
  - action: secret.list
    resource: secret://prod/*
  - action: secret.read
    resource: secret://prod/billing-worker/*
  - action: secret.write
    resource: secret://prod/*
```

Đây là pseudocode, không phải schema của một cloud provider. Cần chuyển thành IAM/Vault policy đúng nền tảng và kiểm thử semantics deny/allow thực tế.

### 4.1. Không cấp wildcard theo service group quá rộng

Các policy kiểu:

```text
allow read secret://prod/*
allow read secret://*
allow all secrets in namespace
```

có thể biến một workload thành principal đọc được nhiều credential không liên quan. Ưu tiên resource ARN/path cụ thể hoặc nhóm nhỏ được quản lý bằng policy-as-code. Nếu cần wildcard cho nhiều instance của cùng service, giới hạn prefix đúng service/environment và kiểm tra không có secret khác nằm dưới prefix đó.

### 4.2. Tách read, list, write, rotate và administer

Không mặc định quyền đọc secret bao gồm quyền list hoặc quản trị. Một số secret store có permission riêng:

| Operation | Ý nghĩa | Principal thường cần |
|---|---|---|
| Read/Get | Đọc một secret version | Runtime service cần credential |
| List/Enumerate | Liệt kê tên secret | Operator/tool inventory được phê duyệt |
| Create/Update | Tạo secret hoặc version mới | Provisioning/rotation workflow |
| Delete/Disable | Vô hiệu hóa/xóa secret | Secret owner/operator theo quy trình |
| Set policy/Grant | Thay đổi quyền truy cập | Security/platform administrator |
| Rotate/Generate | Tạo credential/key mới | Rotation job hoặc KMS-authorized workload |
| Decrypt/Unwrap | Dùng KEK để mở DEK | Consumer được cấp quyền dữ liệu tương ứng |

Runtime service thường chỉ cần read hoặc use/sign/decrypt theo purpose. Nó không cần quyền list tất cả secret, tạo secret mới, đổi IAM policy hoặc xóa key.

### 4.3. Deny-by-default và kiểm tra identity context

Nếu không có policy khớp, từ chối. Không suy ra environment từ tên pod, request header hoặc biến do client có thể sửa. Environment phải đến từ identity provider/deployment trust boundary đáng tin cậy.

Nếu workload identity có claims như service account, namespace, audience hoặc environment, policy engine phải xác minh nguồn phát hành và ràng buộc audience. Không tin một header `X-Environment: prod` do ứng dụng tự gửi.

## 5. Tách biệt development, staging và production

Tách environment là một trong những ranh giới quan trọng nhất của secret management.

### 5.1. Mô hình tách biệt ưu tiên

Nếu nền tảng hỗ trợ, sử dụng cloud account/project/subscription hoặc vault riêng cho production và non-production. Có thể tách thêm theo domain rủi ro cao:

```text
Organization
  |
  +-- Non-production account
  |     +-- Dev secret store / dev KMS
  |     +-- Staging secret store / staging KMS
  |
  +-- Production account
        +-- Orders service secrets
        +-- Billing service secrets
        +-- Webhook service secrets
        +-- Production KMS/HSM
```

Mô hình này giúp giảm nguy cơ policy lỗi ở dev mở quyền tới production. Tuy nhiên, tách account/project không tự động đủ: cần tách identity, network, CI/CD role, audit và quyền quản trị.

### 5.2. Khi không thể tách account/project

Có thể dùng vault namespace, folder, secret path hoặc policy boundary riêng. Khi đó cần:

- Mỗi environment có workload identity riêng.
- Policy không cho dev/staging identity đọc path production.
- KMS key hoặc key policy phân biệt environment.
- Admin quyền production được kiểm soát chặt hơn.
- Có test cross-environment denial.
- Không để pipeline non-production có credential assume role production.

Một namespace chỉ là ranh giới bảo mật nếu secret manager thực thi authorization ở namespace đó và không có quyền quản trị rộng hơn vô tình phá ranh giới.

### 5.3. Không copy production secret sang non-production

Khi cần test tích hợp với vendor hoặc database, tạo credential riêng cho sandbox/test account của vendor. Nếu vendor không có sandbox, cân nhắc mock/stub hoặc test account với dữ liệu giả và quyền giới hạn. Không dùng production API key trong staging để kiểm tra nhanh.

Nếu phải debug một sự cố production, truy cập qua quy trình break-glass có thời hạn, audit và phê duyệt; không export secret production về laptop hoặc chat.

### 5.4. Môi trường preview và ephemeral

Pull request preview, ephemeral namespace hoặc test branch không nên được cấp quyền production. Cấp secret tạm thời từ non-production vault, giới hạn TTL và thu hồi khi môi trường bị xóa. Không để tên branch hoặc PR tự quyết định identity có quyền cao.

## 6. Ví dụ ma trận quyền theo service/environment

Một ma trận quyền giúp phát hiện chia sẻ credential không cần thiết:

| Workload identity | Orders DB prod | Billing DB prod | Payment API prod | Staging secrets |
|---|---:|---:|---:|---:|
| `prod-orders-api` | Read | Deny | Deny | Deny |
| `prod-payment-adapter` | Deny | Deny | Read/use | Deny |
| `prod-billing-worker` | Deny | Read | Deny | Deny |
| `staging-orders-api` | Deny | Deny | Deny | Chỉ staging orders |
| `dev-orders-api` | Deny | Deny | Deny | Chỉ dev orders |
| `prod-deploy-orders` | Không đọc runtime value | Không đọc | Không đọc | Deny |

Nếu `orders-api` cần gọi payment adapter, ưu tiên gọi API nội bộ đã xác thực thay vì cấp payment provider key trực tiếp cho orders-api. Credential nên nằm ở service sở hữu tích hợp đó.

### 6.1. Secret scope và database privilege là hai lớp

Secret store giới hạn ai lấy được database password; database role giới hạn password đó làm được gì. Cần cả hai:

- `orders-api` chỉ đọc secret `orders-db-runtime`.
- Credential đó chỉ kết nối được database/schema của orders.
- Runtime role không có quyền tạo user, thay đổi schema hoặc đọc bảng billing.
- Migration job dùng credential riêng có quyền DDL và chỉ chạy trong pipeline được kiểm soát.

Nếu secret scope đúng nhưng database user có quyền superuser, blast radius vẫn rất lớn. Nếu database role giới hạn nhưng mọi service có thể lấy password đó, vẫn có thể bị lạm dụng.

## 7. Runtime identity và cách lấy secret

Secret cần được cấp cho workload sau khi workload đã được xác thực. Tránh phát một master secret tĩnh cho mọi process.

### 7.1. Workload identity thay cho credential bootstrap tĩnh

Các lựa chọn:

- Cloud managed identity hoặc workload identity federation.
- Kubernetes service account token được federation tới cloud IAM.
- SPIFFE/SPIRE workload identity.
- Short-lived client certificate hoặc OAuth client credential có thời hạn.
- Agent/sidecar được xác thực bằng workload identity để lấy secret.

Mục tiêu là workload có thể chứng minh danh tính mà không cần giữ một secret bootstrap dài hạn trong image hoặc manifest.

### 7.2. Runtime retrieval

Một luồng tham khảo:

1. Workload khởi động bằng identity được nền tảng cấp.
2. Workload yêu cầu secret manager qua TLS/mTLS.
3. Secret manager xác minh identity, environment và resource policy.
4. Workload chỉ nhận secret được phép.
5. Secret được giữ trong memory hoặc mount an toàn trong phạm vi cần thiết.
6. Workload refresh version theo rotation policy và xóa reference/cache cũ khi không còn dùng.

Không đưa secret vào URL hoặc query string. Không log response của secret manager. Không ghi secret vào exception message, startup banner hoặc actuator/debug endpoint.

### 7.3. Environment variable, file mount hay SDK?

| Cách cấp | Ưu điểm | Rủi ro/cần kiểm soát |
|---|---|---|
| Environment variable | Dễ tích hợp với nhiều runtime | Có thể xuất hiện trong process inspection, crash dump, diagnostic bundle hoặc child process |
| File mount/CSI/sidecar | Có thể kiểm soát permission và cập nhật file | Cần bảo vệ filesystem, symlink/path, quyền đọc và reload khi version đổi |
| Secret manager SDK | Có thể lấy theo identity, version và audit | Tạo dependency runtime; cần timeout, cache TTL và failure policy |
| KMS/HSM operation | Key có thể không rời phần cứng/dịch vụ | Cần phân quyền operation và quản lý availability/latency |

Không có cách truyền secret nào an toàn tuyệt đối trong mọi môi trường. Chọn theo threat model, giới hạn process access, không để secret đi vào log/dump và có cơ chế refresh. Nếu dùng environment variable, tránh in toàn bộ environment khi startup hoặc khi debug.

### 7.4. Cache secret có giới hạn

Gọi secret manager ở mỗi request có thể tăng latency và phụ thuộc mạng. Cache secret trong process có thể hợp lý, nhưng cần:

- TTL phù hợp với độ nhạy và thời gian rotation.
- Cơ chế refresh trước khi hết hạn.
- Không cache vô thời hạn hoặc ghi ra disk tùy tiện.
- Xóa/đổi reference khi secret bị revoke.
- Theo dõi version đang được sử dụng.
- Có policy rõ khi secret manager tạm thời không truy cập được.

Không được tiếp tục dùng credential đã biết bị compromise chỉ vì cache còn giá trị. Emergency revocation cần cơ chế invalidate hoặc restart/reload workload theo incident plan.

## 8. Secret trong CI/CD và deployment

Build pipeline, deployment pipeline và runtime workload là các principal khác nhau. Không cấp quyền đọc production secret cho mọi job chỉ vì pipeline có quyền deploy.

### 8.1. Tách build identity và deploy identity

- **Build identity:** compile, test và tạo artifact; thường không cần production runtime secret.
- **Deploy identity:** cập nhật workload, image hoặc secret reference; không nhất thiết cần đọc plaintext secret.
- **Runtime identity:** service đang chạy và cần đọc/use secret của nó.
- **Rotation identity:** job chuyên biệt tạo version mới hoặc thay credential.
- **Break-glass identity:** quyền khẩn cấp có TTL, approval và audit.

Nếu pipeline cần cập nhật secret reference hoặc policy, cấp đúng operation đó. Tránh đưa secret production vào build argument, Docker layer, artifact, test report hoặc cache.

### 8.2. Không lưu secret plaintext trong IaC state

Infrastructure as Code có thể quản lý resource và policy, nhưng một số tool lưu giá trị secret trong state/plan dù field được đánh dấu sensitive. Mask output không có nghĩa dữ liệu không được lưu.

Thực hành:

- Tạo secret container/reference bằng IaC; nhập secret value qua secret manager hoặc quy trình được kiểm soát.
- Giới hạn quyền đọc state và mã hóa state backend.
- Không commit file `.tfvars`, manifest hoặc values file chứa secret.
- Không truyền secret qua command-line argument nếu có thể bị lưu trong process list/history.
- Không in secret trong CI output hoặc plan diff.
- Quản lý state backup/retention như dữ liệu nhạy cảm nếu có secret value bên trong.

### 8.3. Pull request và fork không tin cậy

Không expose production secret cho pipeline chạy trên fork hoặc code chưa review. Một workflow có thể bị sửa để in environment, gửi secret ra ngoài hoặc tạo artifact chứa credential. Cấp quyền theo trust level của branch, approval và environment protection.

### 8.4. Secret scanning

Chạy secret scanning trên repository, commit, container image, IaC, artifact và pipeline logs. Khi phát hiện secret đã commit, xóa khỏi history có thể giảm khả năng lộ tiếp nhưng không làm credential đã lộ trở nên an toàn; phải revoke/rotate và điều tra nơi đã được clone/cache.

## 9. Kubernetes và container

Kubernetes Secret object được base64 encode trong manifest/API representation; base64 không phải encryption. Cần cấu hình encryption at rest cho datastore, RBAC chặt và kiểm soát node/pod access.

### 9.1. ServiceAccount theo workload

Mỗi service nên có ServiceAccount riêng, không dùng default account chung nếu service cần quyền secret. Tắt auto-mount service account token nếu pod không cần gọi Kubernetes API. Nếu workload identity federation cần token để đổi lấy cloud identity, chỉ mount projected token với audience đúng, TTL phù hợp và volume dành riêng cho workload; không bật token mặc định cho mọi pod.

Ví dụ khái niệm:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: prod-orders
automountServiceAccountToken: false
```

Nếu dùng workload identity federation, cấu hình đúng annotation/label và trust policy của nền tảng. Không cho một ServiceAccount có thể assume identity của mọi service.

### 9.2. Namespace không phải ranh giới duy nhất

Namespace giúp tổ chức resource và có thể là một thành phần của policy, nhưng không thay thế RBAC, network policy, admission control, node isolation và cloud IAM. Một pod có thể đọc secret qua Kubernetes API nếu ServiceAccount được cấp quyền; container chạy cùng node cũng có thể bị ảnh hưởng bởi quyền node hoặc runtime.

Kiểm soát:

- RBAC chỉ cho service account get đúng Secret cần thiết; tránh wildcard `secrets` hoặc quyền list/watch toàn namespace nếu không cần.
- Giới hạn ai có thể create pod/deployment dùng ServiceAccount có quyền cao.
- Dùng Pod Security Standards/admission policy phù hợp.
- Bảo vệ node, kubelet, container runtime và etcd.
- Bật encryption at rest cho Kubernetes API datastore theo hướng dẫn cluster.
- Không mount toàn bộ secret namespace vào mọi pod.

### 9.3. CSI driver hoặc external secret operator

CSI driver/external secret operator có thể mount hoặc đồng bộ secret từ secret manager. Cần kiểm tra:

- Pod identity nào được dùng để fetch secret.
- Secret store resource mapping có giới hạn theo service/environment không.
- File permission/owner có tối thiểu không.
- Rotation có cập nhật file và ứng dụng có reload được không.
- Secret có bị đồng bộ thành Kubernetes Secret object hay không.
- Controller identity có quyền đọc quá rộng không.
- Log của controller có in secret value không.

Nếu operator đồng bộ tất cả secret vào namespace, quyền của operator và Kubernetes RBAC có thể trở thành điểm tập trung rủi ro. Giới hạn resource và service account theo nhu cầu.

## 10. Dynamic secret và credential có thời hạn

Secret tĩnh có thể tồn tại nhiều tháng hoặc nhiều năm nếu không có rotation. Dynamic secret được tạo theo yêu cầu, gắn với lease/TTL và có thể tự hết hạn hoặc thu hồi.

Ví dụ:

- Database credential được tạo riêng cho một service với TTL 1 giờ.
- Cloud access token được cấp qua workload identity và tự refresh.
- Certificate ngắn hạn được cấp cho workload.
- Credential vendor được cấp theo môi trường/sandbox và có expiry.

Ưu điểm:

- Giảm thời gian attacker có thể dùng credential bị lấy cắp.
- Giảm nhu cầu chia sẻ password tĩnh.
- Có thể gắn credential với workload/session cụ thể.
- Hỗ trợ audit và revoke theo lease.

### 10.1. Lease và renewal

Consumer cần xử lý:

- Lấy credential trước khi lease hiện tại hết hạn.
- Renew hoặc tạo credential mới theo policy.
- Cập nhật connection pool/client mà không làm gián đoạn request.
- Đóng kết nối dùng credential cũ khi đã chuyển đổi.
- Thu hồi lease khi service shutdown hoặc deploy kết thúc.
- Xử lý khi renewal thất bại hoặc KMS/secret manager tạm thời unavailable.

Với database connection pool, thay secret trong memory không tự đổi password của connection đã mở. Cần thiết kế cách tạo pool mới, drain pool cũ và tránh downtime. Nếu provider không hỗ trợ nhiều credential cùng lúc, rotation cần phối hợp thứ tự đổi credential và reconnect.

### 10.2. Dynamic không có nghĩa là không cần scope

Dynamic credential vẫn cần policy xác định workload nào được tạo credential cho database nào, role nào, TTL bao lâu và quota bao nhiêu. Một service có quyền tạo credential admin không giới hạn vẫn có blast radius lớn dù mỗi credential chỉ tồn tại một giờ.

## 11. Scope secret theo tenant và region

Một số hệ thống cần cách ly theo tenant hoặc region:

- Key mã hóa dữ liệu riêng theo tenant.
- Vendor credential riêng theo tenant contract.
- Secret theo region để đáp ứng data residency hoặc endpoint khác nhau.
- Signing key theo integration/partner.

Không mặc định mỗi tenant phải có một secret store riêng; chi phí vận hành có thể rất lớn. Hãy chọn key hierarchy và policy theo yêu cầu isolation, số tenant, khả năng KMS và blast radius chấp nhận được.

Nếu secret được chọn theo tenant, tenant context phải được xác minh từ principal/session hoặc routing trust boundary. Không lấy `tenantId` từ request body rồi cho phép chọn key bất kỳ.

## 12. Rotation khi scope theo service/environment

Rotation cần thực hiện độc lập theo service và environment để tránh thay một secret làm gián đoạn toàn hệ thống.

Một quy trình:

1. Tạo credential/key mới cho đúng service và environment.
2. Cấp quyền đọc/use cho workload identity tương ứng.
3. Cập nhật secret version/alias hoặc key reference.
4. Deploy/refresh consumer và xác minh kết nối mới.
5. Theo dõi request success, auth failure và version đang được dùng.
6. Thu hồi credential cũ sau overlap được xác định.
7. Xác minh service khác không dùng credential đó trước khi revoke.
8. Ghi audit và cập nhật inventory/owner.

### 12.1. Không rotate secret dùng chung nếu chưa biết consumer

Nếu nhiều service cùng dùng một API key, thay key có thể làm tất cả service lỗi hoặc buộc giữ key cũ lâu hơn. Trước khi tách, kiểm kê consumer và cấp credential riêng cho từng service. Khi chuyển xong, revoke key dùng chung.

### 12.2. Version overlap có giới hạn

Một số provider cho phép hai API key hoạt động đồng thời. Dùng overlap để chuyển consumer, nhưng đặt deadline. Không giữ key cũ vô thời hạn vì một client chưa được cập nhật. Theo dõi usage theo key ID/owner nếu provider hỗ trợ.

### 12.3. Emergency revoke

Nếu secret bị lộ:

- Thu hồi credential hoặc disable key ở hệ thống phát hành.
- Tạo credential mới với scope hẹp hơn nếu cần.
- Cập nhật đúng service/environment.
- Xóa secret khỏi cache/runtime theo khả năng.
- Kiểm tra audit log, source, CI, artifact, log và endpoint có thể đã lộ.
- Đánh giá request bất thường bằng credential bị lộ.
- Không chỉ xóa secret khỏi secret manager mà quên revoke ở vendor/database.

## 13. Secret sharing và tích hợp service-to-service

Nếu service A cần dữ liệu do service B sở hữu, ưu tiên gọi API của B bằng identity riêng thay vì chia sẻ database password hoặc vendor key của B.

Ví dụ:

```text
orders-api --(service identity / scoped token)--> payment-adapter
payment-adapter --(vendor API key)--> payment provider
```

Trong mô hình này:

- `orders-api` không đọc payment provider API key.
- `payment-adapter` sở hữu credential và chịu trách nhiệm rotate.
- `orders-api` chỉ có quyền gọi action nội bộ cần thiết.
- Payment adapter xác thực caller, authorization action và validate business request.

Nếu thực sự cần chia sẻ secret, hãy tạo secret riêng cho từng consumer hoặc dùng cơ chế cấp quyền decrypt/use theo consumer identity. Ghi rõ owner, consumer, expiry, rotation và revoke procedure.

## 14. Failure policy khi secret manager không khả dụng

Secret manager là dependency quan trọng. Cần thiết kế startup, cache, timeout và failure behavior:

- Nếu service chưa có credential hợp lệ, không khởi động ở trạng thái mở quyền hoặc dùng default password.
- Nếu secret manager outage nhưng cache còn secret chưa hết hạn và chưa bị revoke, có thể tiếp tục theo policy có giới hạn.
- Nếu secret đã hết hạn, bị revoke hoặc có incident compromise, không tiếp tục dùng cache cũ.
- Retry có exponential backoff/jitter; tránh mọi pod cùng retry tạo thundering herd.
- Có timeout, circuit breaker và alert.
- Không fallback sang secret của environment khác.
- Không ghi secret value vào log khi xử lý lỗi.

### 14.1. Fail closed hay bounded last-known-good?

Không có một policy chung cho mọi service. Với credential bị thu hồi hoặc nghi compromise, phải fail closed. Với outage ngắn của secret manager, một workload có thể tiếp tục dùng credential đã xác minh trước đó trong một khoảng bounded nếu policy cho phép, credential chưa hết hạn và không có tín hiệu revoke. Thời gian tối đa phải được định nghĩa và kiểm thử.

Không được tự động dùng secret production trong staging hoặc secret của service khác như fallback. Điều đó phá vỡ ranh giới scope và khiến sự cố khó điều tra.

## 15. Audit, inventory và ownership

Mỗi secret cần metadata quản trị:

- Secret ID/reference và purpose.
- Owner team/service.
- Environment và resource scope.
- Consumer/workload identity được phép.
- Upstream system/vendor/database.
- Created/rotated/expiry timestamps.
- Rotation policy và emergency contact/runbook.
- Data classification và retention.
- Version state và dependency list.

Không lưu secret value trong inventory. Inventory chỉ giữ reference, owner và metadata không nhạy cảm.

Audit event nên ghi:

- Principal/workload identity.
- Secret reference và version.
- Operation (read, create, rotate, revoke, delete, policy change).
- Allow/deny result, reason code, timestamp và request ID.
- Source workload/environment theo identity provider.

Không log plaintext value hoặc full secret response. Giới hạn quyền đọc audit log và bảo vệ log khỏi sửa đổi.

## 16. Phát hiện secret scope bị mở rộng

Theo dõi:

- Workload đọc secret ngoài inventory hoặc ngoài environment.
- Một service đột nhiên đọc nhiều secret hơn baseline.
- Dev/staging identity yêu cầu production secret.
- CI runner hoặc developer identity đọc runtime secret không thuộc job.
- Quyền list/watch hoặc wildcard policy được thêm mới.
- Secret không có owner, expiry hoặc rotation schedule.
- Secret value xuất hiện trong repository, artifact, log hoặc container layer.
- Một credential được dùng từ workload/network không mong đợi.

Alert nên tập trung vào hành vi bất thường và policy change có tác động lớn. Một request bị deny đơn lẻ có thể là lỗi cấu hình; việc một dev identity liên tục dò secret production hoặc một service đọc hàng trăm secret cần được điều tra.

## 17. Kiểm thử scope và isolation

Kiểm thử policy nên bao gồm cả trường hợp được phép và bị từ chối. Không chỉ xác nhận service của mình đọc được secret.

| Principal | Secret được yêu cầu | Kết quả mong đợi |
|---|---|---|
| `prod-orders-api` | `prod/orders-api/database/runtime` | Allow |
| `prod-orders-api` | `prod/billing-worker/database/runtime` | Deny |
| `prod-orders-api` | `staging/orders-api/database/runtime` | Deny |
| `staging-orders-api` | `prod/orders-api/database/runtime` | Deny |
| `dev-orders-api` | `prod/payment-adapter/vendor/api-key` | Deny |
| `prod-deploy-orders` | Read production runtime secret | Deny |
| `prod-orders-api` | Update/delete secret policy | Deny |
| `prod-orders-api` | List all production secrets | Deny nếu không có use case được phê duyệt |

### 17.1. Test identity spoofing

- Thử gửi header `X-Environment: prod` từ workload dev.
- Thử sửa namespace/service account claim nếu nền tảng cho phép trong test.
- Thử assume role production từ pipeline non-production.
- Thử dùng token workload với audience sai.
- Thử dùng service account của service khác.
- Xác minh secret manager từ chối request dù tên path có vẻ hợp lệ.

### 17.2. Test rotation và revocation

- Cấp version mới và xác minh đúng workload nhận được.
- Xác minh service khác không đọc được version mới.
- Revoke credential tại upstream và kiểm tra cache/runtime không tiếp tục sử dụng ngoài policy.
- Kiểm tra connection pool sau khi DB password đổi.
- Xác minh rollback không đưa credential đã compromise trở lại.
- Kiểm tra audit ghi đúng identity, version và operation.

### 17.3. Test rò rỉ

- Kiểm tra log startup, error log, tracing, crash dump và metrics.
- Quét source, container image, IaC state, CI artifacts và build cache.
- Xác minh secret không xuất hiện trong command history hoặc process arguments.
- Kiểm tra Kubernetes manifest/ConfigMap/annotation và rendered Helm output.
- Kiểm tra secret không được in khi secret manager timeout hoặc trả lỗi.

## 18. Ví dụ cấu hình policy theo environment

Ví dụ cấu hình khái niệm:

```yaml
environment: prod
service: orders-api
workloadIdentity: workload://prod/orders-api

secrets:
  - name: database-runtime
    resource: secret://prod/orders-api/database/runtime
    operations: [read]
    purpose: connect-to-orders-database

  - name: event-signing
    resource: key://prod/orders-api/events/signing
    operations: [sign]
    purpose: sign-orders-events

denied:
  - secret://prod/billing-worker/*
  - secret://staging/*
  - secret://dev/*
  - secret://prod/orders-api/database/migration
```

Đây chỉ là mô tả policy, không phải cú pháp provider. Nếu policy engine có quy tắc deny-overrides/allow-overrides, cần xác minh semantics. Không dựa vào một dòng deny wildcard để thay thế resource allowlist và identity scoping.

### 18.1. Phân tách migration credential

Migration job có thể cần DDL quyền cao hơn runtime service:

```text
workload://prod/orders-api
  -> read secret: prod/orders-api/database/runtime
  -> database role: orders_runtime

workload://prod/orders-migration
  -> read secret: prod/orders-api/database/migration
  -> database role: orders_schema_migrator
```

Job migration chỉ chạy trong pipeline được kiểm soát, có approval và audit. Không để API runtime giữ credential có thể drop table hoặc tạo database user.

## 19. Checklist triển khai

- [ ] Mỗi service có workload identity riêng; không dùng một identity chung cho toàn backend.
- [ ] Mỗi environment có identity và secret boundary riêng.
- [ ] Production secret nằm trong account/project/vault hoặc policy boundary được bảo vệ riêng.
- [ ] Secret name thể hiện environment/service/purpose nhưng không chứa giá trị nhạy cảm.
- [ ] Resource policy ràng buộc identity với secret cụ thể; path naming không được coi là authorization.
- [ ] Runtime service chỉ có read/use/sign/decrypt cần thiết; không mặc định có list/write/delete/admin.
- [ ] Database runtime credential tách khỏi migration/admin credential.
- [ ] Vendor/API key được tách theo service và environment; không chia sẻ tùy tiện.
- [ ] CI build, deploy, runtime, rotation và break-glass identities được phân biệt.
- [ ] Không đưa secret plaintext vào Git, image, IaC state, artifact, ConfigMap hoặc log.
- [ ] Dùng workload identity/short-lived credential thay cho bootstrap secret tĩnh khi có thể.
- [ ] Cache có TTL và refresh/revoke behavior rõ ràng.
- [ ] Dynamic credential có lease renewal và connection pool transition.
- [ ] Kubernetes RBAC, ServiceAccount, CSI/operator và etcd encryption được cấu hình phù hợp.
- [ ] Có rotation schedule, overlap, emergency revoke và owner cho từng secret.
- [ ] Inventory có consumer, owner, purpose, environment, expiry và upstream dependency.
- [ ] Audit read/rotate/revoke/policy changes và cảnh báo truy cập cross-scope.
- [ ] Có test allow/deny giữa service, environment, operation và identity spoofing.
- [ ] Có kiểm tra secret leakage trong source, build, runtime logs và artifacts.

## 20. Nguyên tắc cần ghi nhớ

Scope secret cần gắn với workload identity, environment, resource và operation. Tên path như `prod/orders-api/database/runtime` giúp tổ chức nhưng không thay thế IAM/Vault policy. Mỗi service nên có identity riêng; dev, staging và production phải có credential và trust boundary riêng. Runtime workload chỉ nhận secret cần cho purpose của nó.

Tách secret theo service giúp thu hồi và điều tra độc lập. Tách theo environment ngăn non-production trở thành đường vào production. Tách theo purpose giúp runtime credential không có quyền migration/admin và service không giữ vendor key mà service khác sở hữu. Secret manager policy và quyền ở hệ thống đích (database, vendor API, KMS) đều phải áp dụng least privilege.

Ưu tiên workload identity và credential có thời hạn; giới hạn cache, rotation và emergency revoke. Kiểm soát CI/CD, Kubernetes, IaC state, log và artifact vì đây đều là nơi secret có thể bị lộ. Theo dõi inventory, audit và test các trường hợp cross-service/cross-environment denial thường xuyên.

Một phép kiểm tra thực tế là dùng identity của `staging-orders-api` yêu cầu secret production của `orders-api`, sau đó dùng identity `prod-orders-api` yêu cầu secret của `billing-worker`. Cả hai phải bị từ chối ở secret manager, kể cả khi caller biết chính xác tên secret. Nếu chỉ đổi tên path là vượt được policy, scope chưa được thực thi đúng.

## Tài liệu tham khảo

- OWASP Secrets Management Cheat Sheet — secret lifecycle, storage, access control và rotation.
- OWASP CI/CD Security Cheat Sheet — bảo vệ pipeline identity, credentials và artifacts.
- NIST SP 800-57 Part 1 — Recommendation for Key Management.
- NIST SP 800-53 Rev. 5 — AC (Access Control), IA (Identification and Authentication), SC (System and Communications Protection).
- SPIFFE/SPIRE specifications — workload identity và trust domain.
- Kubernetes documentation — Secrets, ServiceAccounts, RBAC và encryption at rest.
- HashiCorp Vault documentation — policies, namespaces, dynamic secrets và leases.
- Cloud provider IAM/workload identity documentation — resource-scoped permissions và short-lived credentials.
