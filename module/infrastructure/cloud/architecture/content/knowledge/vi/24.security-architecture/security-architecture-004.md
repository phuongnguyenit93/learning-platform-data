# Định danh workload và truy cập ngắn hạn không dùng khóa tĩnh

## 1. Vì sao workload cần danh tính riêng?

Một ứng dụng cloud không chỉ có người dùng đăng nhập. Các thành phần như Booking API, worker gửi thông báo, job sao lưu, pipeline triển khai, function xử lý ảnh và service đọc dữ liệu đều cần gọi API, đọc secret, ghi database hoặc truy cập object storage. Mỗi thành phần đó là một **workload** và cần một danh tính có thể xác minh.

Trong nhiều hệ thống cũ, workload được cấp API key, access key/secret key hoặc mật khẩu dùng chung, lưu trong file cấu hình, biến môi trường, image hay secret manager. Cách này dễ bắt đầu nhưng tạo gánh nặng: khóa có thể tồn tại lâu, bị sao chép qua log hoặc image, khó biết ai đang dùng, khó thu hồi có chọn lọc và thường cấp quyền rộng để tránh lỗi vận hành.

**Workload identity** là danh tính được gắn với một ứng dụng, service, job hoặc thành phần chạy cụ thể. Hệ thống xác thực danh tính đó dựa trên môi trường chạy hoặc một cơ chế tin cậy, rồi cấp quyền truy cập phù hợp. Thay vì mang một bí mật dài hạn tới mọi nơi, workload có thể nhận **credential ngắn hạn** sau khi chứng minh danh tính.

Mô hình này thường kết hợp:

- Danh tính workload được quản lý bởi cloud platform, orchestrator hoặc identity provider.
- Federation để trao đổi token/danh tính giữa các miền tin cậy.
- Security Token Service (STS) hoặc cơ chế tương đương để phát credential có thời hạn.
- IAM policy cấp quyền tối thiểu cho đúng tài nguyên và hành động.
- TLS/mTLS để bảo vệ và xác thực kết nối.
- Audit, rotation, expiration và revocation để quản lý vòng đời.

Trong module **CLOUD_ARCHITECTURE**, thiết kế identity là nền tảng bảo mật cho compute, mạng, dữ liệu và mô hình triển khai. Cần cân bằng **bảo mật, độ tin cậy, khả năng mở rộng, chi phí và vận hành** theo tư duy Well-Architected.

Ví dụ xuyên suốt: Booking API chạy trên Kubernetes cần đọc thông tin cấu hình từ secret manager, ghi booking vào database và tải hóa đơn lên object storage. Worker gửi email chỉ cần đọc event và gọi dịch vụ email. Pipeline CI/CD cần triển khai vào production. Mỗi workload cần danh tính và quyền khác nhau; không nên dùng chung một access key quản trị cho cả ba.

## 2. Phân biệt các loại identity

Các danh tính tham gia một hệ thống thường có mục đích khác nhau:

| Loại identity | Đại diện cho ai/cái gì? | Ví dụ |
| --- | --- | --- |
| Human identity | Người dùng hoặc nhân viên | Nhân viên vận hành đăng nhập qua SSO |
| Customer identity | Khách hàng sử dụng sản phẩm | Khách đặt chỗ bằng tài khoản |
| Workload identity | Ứng dụng, service, job hoặc process | booking-api, invoice-worker |
| Device identity | Thiết bị hoặc phần cứng | Máy POS, edge gateway |
| External partner identity | Hệ thống đối tác | Payment provider gọi webhook hoặc API |
| Federated identity | Danh tính được xác minh ở miền khác và được tin cậy theo điều kiện | CI runner nhận token OIDC từ identity provider |

Không dùng user identity làm danh tính service chỉ vì cả hai đều có token. User token thường mang ngữ cảnh người dùng, audience và quyền theo hành động người dùng; workload credential đại diện cho process và cần policy theo tài nguyên mà service phải truy cập.

### 2.1. Authentication và authorization

- **Authentication (xác thực):** xác định chủ thể là ai và bằng chứng danh tính có hợp lệ không.
- **Authorization (ủy quyền):** chủ thể đã xác thực được phép thực hiện hành động nào trên tài nguyên nào, trong điều kiện nào.

Có workload identity hợp lệ không có nghĩa workload được phép đọc mọi bucket hoặc database. Danh tính chỉ là đầu vào để policy engine đánh giá quyền. Quyền phải được cấp theo resource, action, condition, environment và thời hạn cần thiết.

### 2.2. Một workload có thể có nhiều danh tính theo vai trò

Một process có thể cần tương tác với nhiều hệ thống, nhưng không nên vì thế mà được một quyền tổng hợp quá rộng. Có thể dùng một workload identity cho vai trò runtime và các quyền cụ thể được giới hạn theo tài nguyên; hoặc tách process thành các workload riêng nếu chúng có mức tin cậy và quyền khác nhau.

Ví dụ API nhận request booking không cần quyền gửi email trực tiếp nếu notification worker xử lý tác vụ đó. Tách trách nhiệm làm giảm blast radius khi một thành phần bị khai thác.

## 3. Mô hình truy cập bằng khóa tĩnh và rủi ro

Một access key dài hạn thường gồm định danh và bí mật được workload sử dụng để ký request hoặc lấy token. Khi bí mật không thay đổi trong thời gian dài, nó có thể bị sao chép và tiếp tục dùng sau khi process gốc bị thay thế.

### 3.1. Những nơi khóa tĩnh dễ bị lộ

- Source code, repository, pull request và file cấu hình.
- Docker/container image hoặc layer build.
- Biến môi trường, crash dump, process inspection và debug output.
- Log, trace, command history và support bundle.
- Secret được chia sẻ giữa nhiều môi trường hoặc nhiều service.
- Máy developer, CI runner hoặc host không được quản lý tốt.
- Backup, artifact registry hoặc bản export cũ.

Secret manager giúp quản lý lưu trữ và quyền truy cập bí mật, nhưng **không tự biến khóa dài hạn thành credential ngắn hạn**. Nếu ứng dụng vẫn đọc một access key không hết hạn từ secret manager rồi dùng liên tục, rủi ro về vòng đời vẫn còn.

### 3.2. Rủi ro khi dùng chung một khóa

Nếu Booking API, worker và pipeline triển khai dùng cùng một khóa:

- Audit khó xác định process nào thực hiện hành động.
- Không thể thu hồi một workload mà không làm gián đoạn các workload khác.
- Quyền thường phải rộng để đáp ứng tất cả use case.
- Khóa phải được phân phối và đồng bộ trên nhiều nơi.
- Rotation cần phối hợp mọi client và có thể gây outage.
- Khó chứng minh credential đã bị xóa khỏi image, log hoặc backup cũ.

## 4. Mô hình mục tiêu: danh tính đáng tin cậy và credential ngắn hạn

Một luồng truy cập điển hình:

~~~mermaid
sequenceDiagram
    participant W as Workload
    participant P as Runtime Identity Provider
    participant STS as Token / STS Service
    participant IAM as IAM Policy Engine
    participant R as Protected Resource
    W->>P: Chứng minh workload identity
    P-->>W: Identity assertion / token
    W->>STS: Đổi assertion lấy credential ngắn hạn
    STS->>IAM: Đánh giá trust policy và quyền
    IAM-->>STS: Cho phép với scope phù hợp
    STS-->>W: Credential có expiration
    W->>R: Gọi API với credential
    R->>IAM: Xác minh token, scope và policy
    IAM-->>R: Allow / deny
    R-->>W: Kết quả
~~~

Tên và thứ tự bước thay đổi giữa nền tảng. Có hệ thống cấp token workload trực tiếp; có hệ thống dùng assertion từ môi trường chạy để đổi lấy cloud role session; có hệ thống dùng certificate hoặc SPIFFE SVID để xác thực service-to-service.

Điểm quan trọng:

1. Workload chứng minh danh tính qua một kênh được nền tảng tin cậy.
2. Trust policy kiểm tra issuer, subject, audience, môi trường và điều kiện khác.
3. Credential được cấp có thời hạn, phạm vi và quyền giới hạn.
4. Resource kiểm tra credential và authorization ở thời điểm truy cập.
5. Workload làm mới credential trước khi hết hạn và không ghi bí mật vào log.

## 5. Các cách cung cấp workload identity

### 5.1. Cloud-native workload identity

Cloud provider thường có cơ chế gắn role/service account/managed identity với compute resource như VM, container service, serverless function hoặc managed job. Runtime cung cấp endpoint hoặc SDK để process lấy credential tạm thời.

Ưu điểm:

- Danh tính gắn với tài nguyên chạy, giảm nhu cầu lưu access key.
- Cloud control plane quản lý việc cấp và hết hạn credential.
- IAM policy có thể giới hạn quyền theo service/role.
- Thuận tiện audit theo principal hoặc role session.

Điều cần kiểm tra:

- Process nào trên host/container có thể lấy identity?
- Có thể phân biệt workload trong cùng node không?
- Endpoint metadata có bị truy cập từ container không được phép không?
- Credential được cache/refresh trong SDK như thế nào?
- Khi instance/service bị terminate, credential cũ còn hiệu lực bao lâu?

Không cấp một instance role rộng cho mọi process chạy trên cùng máy nếu chúng có mức tin cậy khác nhau.

### 5.2. Kubernetes service account và workload identity

Trong Kubernetes, ServiceAccount cung cấp identity cho pod. Token projected có thể có expiration và audience, rồi được dùng với federation để đổi lấy credential của cloud role. Cơ chế cụ thể phụ thuộc phiên bản cluster, issuer, cấu hình OIDC và cloud provider.

Một pod declaration minh họa:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: booking-api
  namespace: production
  annotations:
    identity.example/role: booking-runtime-role
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: booking-api
  namespace: production
spec:
  template:
    spec:
      serviceAccountName: booking-api
      automountServiceAccountToken: true
      containers:
        - name: api
          image: registry.example/booking-api:v4
~~~

Đây là ví dụ khái niệm, annotation và cách cấu hình không phải cú pháp chung của Kubernetes hoặc một cloud provider. Trong môi trường thật, cần dùng cấu hình chính thức của nền tảng và kiểm soát token projection, audience, issuer, RBAC và network.

ServiceAccount token có thể phục vụ Kubernetes API hoặc làm assertion cho federation; hai mục đích không nên bị nhầm. Không mount token vào container nếu workload không cần truy cập Kubernetes API hoặc identity federation.

### 5.3. Managed identity cho VM/serverless

Managed identity là danh tính được cloud platform quản lý gắn với resource. Ứng dụng xin token từ runtime identity endpoint hoặc SDK mà không lưu client secret. Có thể dùng system-assigned identity hoặc user-assigned identity tùy nền tảng.

Khi lựa chọn, cân nhắc:

- Vòng đời identity gắn với resource hay độc lập để tái sử dụng?
- Một identity có được gắn vào nhiều workload không?
- Quyền nào được cấp và cách giới hạn theo resource?
- Làm sao phân biệt log giữa các instance dùng cùng identity?
- Có thể xoay vòng hoặc thu hồi mà không thay cấu hình ứng dụng không?

### 5.4. Workload identity cho môi trường ngoài cloud

Workload chạy tại datacenter, edge hoặc CI runner có thể không có cloud-native metadata identity. Các lựa chọn gồm federation bằng OIDC, certificate-based identity, SPIFFE/SPIRE hoặc một broker identity được quản lý.

Không nên giải quyết bằng cách đặt access key cloud dài hạn trong mỗi VM. Hãy thiết lập trust relationship có issuer, subject, audience, environment và điều kiện ràng buộc cụ thể.

## 6. Federation và OpenID Connect

**Federation** cho phép một miền tin cậy chấp nhận bằng chứng danh tính do miền khác phát hành theo một trust policy. Workload có thể nhận token từ CI platform, Kubernetes cluster hoặc identity provider rồi đổi lấy quyền truy cập tài nguyên cloud mà không cần lưu client secret dài hạn.

**OpenID Connect (OIDC)** là lớp identity dựa trên OAuth 2.0, sử dụng ID Token để mô tả authentication event và cung cấp issuer/claims. Trong workload federation, nền tảng thường xác minh một signed token theo trust configuration; token được dùng làm assertion để nhận credential khác. Cần tuân theo flow chính thức của từng nền tảng.

### 6.1. Các claim cần kiểm tra

| Claim/thuộc tính | Ý nghĩa | Rủi ro nếu trust quá rộng |
| --- | --- | --- |
| iss (issuer) | Nơi phát hành token | Chấp nhận issuer giả hoặc issuer không thuộc tổ chức |
| sub (subject) | Danh tính chủ thể | Chấp nhận mọi repository, namespace hoặc service account |
| aud (audience) | Token dành cho đối tượng nhận nào | Token được phát cho service khác bị dùng lại |
| exp / nbf | Thời hạn hiệu lực | Token hết hạn hoặc chưa đến thời điểm vẫn được chấp nhận sai |
| signature/key | Bằng chứng token do issuer phát hành | Không xác minh chữ ký hoặc không xử lý key rotation |
| repository/environment | Context CI/CD nếu issuer cung cấp | Branch/fork/untrusted environment được nhận quyền production |
| namespace/service account | Context workload trong cluster | Pod không tin cậy giả mạo workload được cấp role |

Không chỉ kiểm tra issuer. Trust policy thường cần ràng buộc issuer + subject + audience và có thể thêm claim theo repository, branch, environment, namespace hoặc service account. Chọn claim đúng semantics và xác minh nó được issuer ký, không lấy từ header tùy ý.

### 6.2. Ví dụ luồng CI/CD federation

~~~mermaid
sequenceDiagram
    participant CI as CI Runner
    participant OIDC as CI OIDC Provider
    participant STS as Cloud STS
    participant IAM as Cloud IAM
    participant PROD as Production API
    CI->>OIDC: Request job token
    OIDC-->>CI: Signed token (issuer, subject, audience, expiry)
    CI->>STS: Exchange token for role session
    STS->>IAM: Check trust conditions
    IAM-->>STS: Trust allowed
    STS-->>CI: Short-lived deployment credentials
    CI->>PROD: Deploy using scoped permissions
~~~

Trust policy nên xác định rõ repository, protected branch/tag hoặc deployment environment được phép triển khai production. Không cho mọi pull request từ fork nhận quyền ghi production chỉ vì token có issuer hợp lệ.

### 6.3. Audience và confused deputy

Audience giúp giới hạn token được dùng cho đúng relying party. Nếu nhiều hệ thống chấp nhận cùng một token mà không ràng buộc audience, token có thể bị dùng ở nhầm service. Cần thiết lập audience cụ thể và không chấp nhận wildcard nếu không có lý do được đánh giá.

Một workload trung gian có quyền rộng có thể vô tình thực hiện hành động thay cho caller không đủ quyền (confused deputy). Khi service nhận lệnh từ workload khác, phải xác minh cả danh tính caller, quyền của caller và quyền service được phép đại diện; không mặc định mọi request tới service đều được dùng toàn bộ quyền runtime của service.

## 7. STS và credential ngắn hạn

**Security Token Service (STS)** hoặc dịch vụ tương đương phát credential tạm thời cho principal đã được xác minh. Credential có thể gồm access token, access key/session secret/session token hoặc signed assertion tùy giao thức.

Một credential session thường có:

- Principal/role được đại diện.
- Permissions hoặc scope áp dụng.
- Audience/resource target nếu giao thức hỗ trợ.
- Issue time và expiration.
- Session tags/claims để audit hoặc điều kiện policy.
- Context về source identity hoặc role assumption.

### 7.1. Thời hạn ngắn không tự động đồng nghĩa quyền nhỏ

Token 5 phút vẫn nguy hiểm nếu cấp quyền quản trị toàn tài khoản. Phải kết hợp **short lifetime + least privilege + audience restriction + trust condition + audit**.

Thời hạn quá ngắn có thể làm workload lỗi liên tục khi STS hoặc identity provider tạm thời không sẵn sàng. Thời hạn quá dài làm cửa sổ lạm dụng sau khi token bị lộ lớn hơn. Chọn duration theo threat model, khả năng refresh, SLA của identity service và chính sách nền tảng.

### 7.2. Làm mới credential

Workload nên dùng SDK hoặc credential provider chain chính thức để tự refresh. Tránh tự viết logic ký/xác thực nếu thư viện nền tảng đã cung cấp cơ chế đã kiểm thử.

Một cách tiếp cận:

1. Lấy credential khi bắt đầu hoặc trước lần gọi tài nguyên đầu tiên.
2. Cache trong memory theo expiration, không ghi ra log/disk nếu không cần.
3. Refresh trước khi hết hạn một khoảng có jitter.
4. Nếu refresh lỗi tạm thời, dùng credential hiện tại chỉ tới expiration; retry có backoff.
5. Khi credential hết hạn và không thể refresh, từ chối truy cập an toàn và phát cảnh báo.

Không đợi tới đúng thời điểm expiration mới refresh: network latency và clock skew có thể làm request đầu tiên thất bại.

### 7.3. Clock skew và token validation

Token có nbf, iat và exp. Đồng hồ máy lệch có thể làm token bị coi là chưa hiệu lực hoặc đã hết hạn. Đồng bộ thời gian hệ thống, dùng tolerance theo chính sách của protocol và theo dõi clock drift. Không nới tolerance quá rộng để “sửa” lỗi đồng hồ vì điều đó kéo dài cửa sổ chấp nhận token.

## 8. Least privilege và permission boundary

Một workload identity chỉ nên có quyền cần thiết cho nhiệm vụ cụ thể:

| Workload | Quyền cần thiết minh họa | Quyền không nên có mặc định |
| --- | --- | --- |
| Booking API | Đọc secret DB runtime, truy cập bảng booking, ghi outbox | Quản trị IAM, xóa backup, triển khai cluster |
| Invoice worker | Đọc event hóa đơn, ghi object vào prefix hóa đơn của tenant | Đọc payment credential hoặc xóa toàn bucket |
| Notification worker | Đọc event cần gửi và gọi provider gửi thông báo | Ghi database booking, đọc mọi customer record |
| Search indexer | Đọc projection source, ghi search index | Cập nhật booking hoặc quản trị tài khoản |
| CI deploy role | Deploy artifact vào namespace/environment được phép | Đọc dữ liệu khách hàng hoặc quản trị billing |
| Backup job | Đọc dữ liệu nguồn và ghi backup repository | Xóa mọi bản backup hoặc sửa production data |

### 8.1. Scope theo resource và action

Policy nên giới hạn theo:

- Action cụ thể: get/list/put/delete/execute, không dùng wildcard rộng mặc định.
- Resource cụ thể: database/table/bucket/topic/secret/cluster.
- Environment: development, staging, production.
- Tenant hoặc namespace khi tài nguyên chia sẻ.
- Network/source condition hoặc device/workload posture nếu có hỗ trợ.
- Thời gian, session tag, MFA/human approval cho hành động đặc biệt.

Không dùng chuỗi tên role như bằng chứng bảo mật duy nhất. Trust policy và resource policy cần xác minh principal thực, resource, action và conditions.

### 8.2. Tách role theo chức năng

Nếu một service cần đọc secret và ghi object, nhưng không cần xóa object hoặc quản trị IAM, hãy cấp đúng các quyền đó. Nếu một job triển khai cần thay đổi production compute, không cấp cho nó quyền đọc dữ liệu production. Tách role giúp giới hạn tác động khi pipeline hoặc process bị xâm nhập.

## 9. Workload identity và mTLS/service-to-service

Cloud IAM identity và mTLS giải quyết những lớp khác nhau:

- Cloud IAM/workload credential thường xác định principal khi gọi API quản lý tài nguyên cloud.
- mTLS xác thực cả client và server trong một kết nối TLS, thường dùng giữa service.
- Application authorization xác định service đã xác thực được gọi endpoint/hành động nghiệp vụ nào.

Có thể dùng chung một nguồn danh tính nhưng phải xác định mapping giữa workload principal, certificate identity và application role.

### 9.1. SPIFFE và SPIRE

SPIFFE định nghĩa cách biểu diễn danh tính workload bằng SPIFFE ID và SVID (SPIFFE Verifiable Identity Document). SVID có thể là X.509 certificate hoặc JWT theo mô hình sử dụng. SPIRE là một implementation cung cấp attestation và phát SVID cho workload.

Khái niệm này hữu ích trong môi trường nhiều cluster, nhiều cloud hoặc hybrid khi cần danh tính service-to-service độc lập với địa chỉ IP và hostname. Workload được attest theo node/workload selector rồi nhận SVID có thời hạn. Peer xác minh trust bundle/issuer và identity theo policy.

SPIFFE/SPIRE không thay thế toàn bộ IAM, API authorization hoặc secret management. Nó cung cấp lớp workload identity; từng service vẫn phải quyết định principal được phép thực hiện hành động gì.

### 9.2. Luồng mTLS

~~~mermaid
sequenceDiagram
    participant A as Service A
    participant B as Service B
    A->>B: TLS ClientHello
    B-->>A: Server certificate
    A->>B: Client certificate
    B->>B: Verify issuer, validity and identity
    A->>A: Verify server identity
    A->>B: Authorized API request
    B->>B: Map workload identity to application policy
    B-->>A: Response
~~~

Certificate hết hạn, trust bundle thay đổi hoặc workload identity bị thu hồi đều cần được xử lý. Rotation không nên làm gián đoạn kết nối hàng loạt; có thể triển khai overlap certificate/trust bundle trong khoảng thời gian được kiểm soát.

## 10. Identity propagation và quyền đại diện

Trong chuỗi service A → B → C, cần phân biệt:

- C gọi bằng danh tính riêng của C.
- C gọi thay mặt user hoặc workload A.
- C gọi thay mặt tenant đang được xác thực.

Nếu C dùng quyền runtime của mình mà không giữ ngữ cảnh caller, một service trung gian có thể trở thành confused deputy. Nếu truyền nguyên token của A qua mọi hop, token có thể có audience hoặc lifetime không phù hợp.

Các lựa chọn:

1. **Service identity:** mỗi service xác thực bằng danh tính riêng, kiểm tra quyền caller ở lớp API.
2. **Token exchange/delegation:** đổi token sang token mới với audience, scope và lifetime hẹp hơn.
3. **On-behalf-of pattern:** service đại diện cho user theo flow được identity provider hỗ trợ.
4. **Signed context:** truyền context có chữ ký hoặc bảo vệ integrity khi không thể chuyển token; receiver vẫn phải xác minh nguồn và scope.

Không forward access token qua mọi service theo thói quen. Chỉ gửi credential đến audience dự định và tránh đưa token vào log, query string hoặc message không được bảo vệ.

## 11. Thu hồi, rotation và xử lý credential bị lộ

Credential ngắn hạn giảm thời gian lạm dụng nhưng không thay thế quy trình phản ứng sự cố.

### 11.1. Các cách thu hồi

- Disable/revoke workload identity hoặc role trust.
- Thu hồi federated trust cho issuer/subject/environment.
- Giảm quyền hoặc deny principal ở policy/resource policy.
- Revoke certificate hoặc cập nhật trust bundle/CRL/OCSP theo khả năng hệ thống.
- Xóa workload/runner bị xâm nhập và dựng lại từ image/artifact sạch.
- Rotate secret downstream nếu credential bị lộ kéo theo secret khác.
- Chặn network path hoặc session theo incident response plan.

Không phải mọi token đã phát đều bị vô hiệu ngay khi policy thay đổi. Một số hệ thống kiểm tra policy mỗi request; số khác chấp nhận token cho tới expiration hoặc có propagation delay. Phải hiểu semantics của provider và chọn lifetime phù hợp.

### 11.2. Rotation có overlap

Với certificate hoặc secret vẫn cần rotation, dùng quy trình có giai đoạn:

1. Tạo credential mới và đăng ký trust.
2. Triển khai workload chấp nhận credential mới.
3. Chuyển traffic hoặc refresh session sang credential mới.
4. Xác minh không còn request dùng credential cũ.
5. Thu hồi credential cũ và ghi audit.

Credential ngắn hạn vẫn cần rotation của signing key, trust anchor, issuer key và client certificate theo lịch và quy trình sự cố. “Không có khóa tĩnh trong workload” không có nghĩa hệ thống không còn khóa mật mã dài hạn ở bất kỳ đâu; signing keys và trust roots phải được bảo vệ ở control plane.

## 12. Credential cache, refresh và availability

Credential ngắn hạn tạo phụ thuộc vào identity provider/STS. Nếu STS ngừng hoạt động, workload đã có credential còn hiệu lực có thể tiếp tục làm việc trong thời hạn đó, nhưng không thể refresh vô hạn.

Các nguyên tắc:

- Cache credential trong memory theo SDK/provider đã được kiểm thử.
- Refresh sớm với jitter để tránh nhiều instance cùng refresh một lúc.
- Dùng retry có exponential backoff và giới hạn tổng thời gian.
- Theo dõi token issuance latency, error rate và số credential sắp hết hạn.
- Không log credential hoặc token exchange request chứa assertion.
- Có capacity/HA phù hợp cho identity endpoint và STS.
- Không kéo dài credential lifetime tùy tiện khi STS lỗi; lựa chọn degraded mode theo rủi ro nghiệp vụ.

### 12.1. Credential provider chain

SDK có thể chọn credential từ nhiều nguồn (managed identity, workload federation, local development profile, environment variables...). Thứ tự provider rất quan trọng. Một biến môi trường cũ có thể vô tình khiến production dùng static key thay vì workload identity mong muốn.

Trong production:

- Chỉ bật provider source được phê duyệt.
- Fail startup nếu identity source sai hoặc không có trust phù hợp.
- Kiểm tra principal/role thực tế trong health diagnostics an toàn.
- Không fallback âm thầm sang static key khi federation lỗi.
- Môi trường local dùng profile/dev identity riêng, quyền thấp và thời hạn phù hợp.

## 13. Bảo mật token, assertion và metadata endpoint

Token/assertion là bearer credential hoặc bằng chứng để nhận credential khác. Ai lấy được token có thể sử dụng trong phạm vi audience, expiry và policy cho phép.

### 13.1. Những điểm cần bảo vệ

- Không ghi token vào application log, tracing span, exception hoặc crash report.
- Không chuyển token qua URL/query string.
- Không nhúng token vào image, source code hoặc build artifact.
- Giới hạn quyền đọc projected token file và mount vào đúng container.
- Bảo vệ identity metadata endpoint khỏi truy cập từ workload không được phép.
- Chặn SSRF tới metadata service bằng cấu hình network/runtime thích hợp.
- Giới hạn audience và expiration; xác minh issuer, subject và signature.
- Xử lý signing key rotation và JWKS cache đúng semantics.

### 13.2. SSRF và metadata service

Một số cloud VM cung cấp metadata endpoint để workload lấy thông tin instance/identity. Nếu ứng dụng có lỗi Server-Side Request Forgery (SSRF), kẻ tấn công có thể cố truy cập metadata endpoint để lấy token. Các lớp giảm thiểu có thể gồm yêu cầu token header/session ở metadata endpoint, giới hạn hop, firewall/host controls, proxy policy, egress restriction và vá lỗi SSRF ở ứng dụng.

Không dựa duy nhất vào một header bảo vệ metadata nếu runtime hoặc network cho phép process không tin cậy tiếp cận endpoint theo cách khác. Kiểm tra hướng dẫn chính thức của nền tảng và threat model của môi trường cụ thể.

## 14. Audit và khả năng truy vết

Workload identity có giá trị khi log có thể trả lời: **workload nào, trong môi trường nào, dùng credential/role nào, truy cập tài nguyên gì, hành động nào được cho phép hoặc từ chối và theo phiên nào?**

Nên theo dõi:

| Nhóm | Trường/signal |
| --- | --- |
| Principal | Workload identity, role/service account, source identity |
| Federation | Issuer, subject, audience, token exchange result |
| Session | Session ID, issue/expiry time, session tags |
| Resource | ARN/resource ID/table/bucket/topic/endpoint |
| Action | API/action, allow/deny, policy decision |
| Source | Workload environment, cluster/namespace, region, source IP theo policy |
| Lifecycle | Credential issued/refreshed/expired/revoked, certificate rotated |
| Anomaly | Role assumption bất thường, audience lạ, geolocation/network bất thường, tần suất tăng |

Không log token hoặc private key để tăng khả năng debug. Audit trail cần chống sửa/xóa ngoài quyền, có retention và được chuyển khỏi failure domain của workload khi cần.

## 15. Phân quyền theo môi trường và chuỗi cung ứng phần mềm

Danh tính workload phải phân biệt development, staging và production. Một CI runner từ pull request không tin cậy không được dùng role của release production.

Các nguyên tắc:

- Tách trust relationship theo environment.
- Subject condition ràng buộc repository/branch/tag/workflow theo claim đáng tin của issuer.
- Production deployment dùng protected environment hoặc approval theo quy trình tổ chức.
- Build role chỉ ghi artifact vào registry; deploy role chỉ triển khai resource được giao.
- Runtime role không được sửa pipeline hoặc cấp quyền cho chính nó.
- Artifact phải truy nguyên được tới source commit và pipeline run.
- Tách role quản trị identity khỏi role chạy workload.

### 15.1. Không để workload tự nâng quyền

Nếu một workload có quyền sửa trust policy của chính role nó đang dùng hoặc tạo role mới, ranh giới least privilege bị phá vỡ. Quyền cấp identity, sửa IAM policy, tạo key và thay trust relationship nên được giữ ở control plane/admin role với quy trình review, audit và separation of duties.

## 16. Thiết kế kiến trúc tham khảo cho nền tảng đặt chỗ

~~~mermaid
flowchart TB
    subgraph Runtime["Workload runtime"]
      API["Booking API<br/>ServiceAccount: booking-api"]
      INV["Invoice Worker<br/>ServiceAccount: invoice-worker"]
      NOTI["Notification Worker<br/>ServiceAccount: notification-worker"]
    end
    IDP["Workload Identity Provider / OIDC"]
    STS["STS / Token Exchange"]
    IAM["IAM Policies"]
    DB[("Booking Database")]
    OBJ[("Invoice Object Storage")]
    MSG["Event Topic"]
    EMAIL["Email Provider"]
    API --> IDP
    INV --> IDP
    NOTI --> IDP
    IDP --> STS --> IAM
    API -->|"scoped DB access"| DB
    INV -->|"write invoice prefix"| OBJ
    NOTI -->|"read notification event"| MSG
    NOTI -->|"send message"| EMAIL
~~~

Policy minh họa:

| Workload | Principal/role | Resource | Quyền |
| --- | --- | --- | --- |
| Booking API | booking-runtime | Booking DB | Kết nối và thao tác bảng cần thiết |
| Booking API | booking-secret-reader | Secret booking DB | Đọc đúng secret runtime |
| Invoice Worker | invoice-writer | Bucket/prefix invoice | Ghi object theo tenant scope được xác minh |
| Notification Worker | notification-consumer | Topic notification | Consume event được giao |
| Notification Worker | email-sender | Email provider API | Gửi thông báo theo sender/domain cho phép |
| CI deploy job | production-deployer | Cluster/namespace production | Deploy version đã được phê duyệt |

Không cần một principal duy nhất cho mọi khả năng. Tách role theo chức năng giúp audit và thu hồi có phạm vi.

## 17. Bài thực hành: thay static access key bằng workload identity

**Bối cảnh:** Booking API và hai worker đang dùng một access key lưu trong secret manager. Key có quyền đọc nhiều bucket, ghi database và quản lý một số resource. Pipeline CI cũng dùng cùng key để deploy.

### Nhiệm vụ

1. Lập inventory các workload, môi trường, tài nguyên và hành động hiện tại.
2. Xác định nơi static key xuất hiện: secret store, config, image, CI, log hoặc developer machine.
3. Tách danh tính cho Booking API, Invoice Worker, Notification Worker và CI deployment.
4. Chọn cloud-native identity, Kubernetes federation, OIDC federation hoặc SPIFFE/mTLS theo runtime.
5. Thiết kế trust policy với issuer, subject, audience, environment và conditions cụ thể.
6. Viết IAM policy tối thiểu cho từng workload/resource/action.
7. Thiết lập credential duration, refresh, retry, clock sync và hành vi khi STS unavailable.
8. Thiết kế rotation/revocation và quy trình xử lý credential bị lộ.
9. Kiểm tra SSRF/metadata endpoint, token logging, service account mount và provider-chain fallback.
10. Xây audit dashboard và phát hiện assumption bất thường.
11. Thực hiện migration theo giai đoạn: cấp identity mới, deploy song song, xác minh principal, thu hồi static key, kiểm tra mọi đường truy cập.
12. Viết ADR ghi đánh đổi availability, security, performance, cost và operations.

### Mẫu ma trận trust

| Workload | Issuer/runtime | Subject được tin | Audience | Role/scope | Expiry |
| --- | --- | --- | --- | --- | --- |
| Booking API | Cluster OIDC issuer | Namespace production, ServiceAccount booking-api | Cloud STS | Booking runtime policy | Ngắn hạn theo platform |
| Invoice Worker | Cluster OIDC issuer | Namespace production, ServiceAccount invoice-worker | Cloud STS | Invoice object writer | Ngắn hạn theo platform |
| Notification Worker | Cluster OIDC issuer | Namespace production, ServiceAccount notification-worker | Cloud STS | Event consumer + email sender | Ngắn hạn theo platform |
| CI production deploy | CI OIDC issuer | Protected repository/environment | Cloud STS | Production deploy role | Chỉ trong job session |

Các giá trị ở bảng phải khớp claim thực tế do issuer phát và policy engine kiểm tra. Không sao chép subject mẫu sang production mà chưa xác minh format và semantics của provider.

### Tiêu chí hoàn thành

- Mỗi workload có identity riêng hoặc scope riêng đủ để phân biệt và cô lập.
- Static credential không còn là dependency runtime cho luồng đã migration.
- Trust policy ràng buộc issuer, subject, audience và environment.
- Quyền được cấp theo least privilege, resource và action cụ thể.
- Credential có expiration, tự refresh an toàn và không rò vào log.
- Revocation, signing key rotation và incident response có runbook.
- Không có fallback âm thầm về static key khi federation lỗi.
- CI untrusted context không thể lấy quyền deploy production.
- Audit truy vết được principal, role session, resource và action.

## 18. Checklist Well-Architected trước khi đưa workload identity vào production

- [ ] Đã phân biệt human, customer, workload, device và partner identity.
- [ ] Mỗi workload có danh tính riêng phù hợp với ranh giới tin cậy và nhiệm vụ.
- [ ] Authentication và authorization được thiết kế thành hai bước riêng.
- [ ] Trust policy kiểm tra issuer, subject, audience, expiry và claim cần thiết.
- [ ] Federation không chấp nhận wildcard hoặc untrusted repository/namespace.
- [ ] Credential có thời hạn phù hợp, được refresh trước expiration và không lưu/log tùy tiện.
- [ ] IAM policy tuân theo least privilege, giới hạn action/resource/condition.
- [ ] Không dùng một role quản trị rộng cho API, worker, CI và backup.
- [ ] Metadata endpoint, projected token, SSRF và token file được bảo vệ.
- [ ] SDK credential provider chain không fallback âm thầm sang static key ở production.
- [ ] mTLS/SPIFFE được dùng đúng lớp và có mapping tới application authorization.
- [ ] Identity propagation không gây confused deputy hoặc forward token sai audience.
- [ ] Có rotation/revocation cho credential, signing key, certificate và trust anchor.
- [ ] Hiểu rõ policy propagation và thời gian token cũ còn hiệu lực sau revoke.
- [ ] STS/identity provider có HA, quota, timeout, retry và monitoring phù hợp.
- [ ] Audit trail ghi principal/session/resource/action nhưng không lưu bí mật.
- [ ] CI/CD trust tách theo protected branch/environment và deployment approval.
- [ ] Đã kiểm thử credential expiration, STS outage, issuer key rotation và compromise response.
- [ ] ADR ghi rõ đánh đổi reliability, security, performance, cost và operations.

**Điểm cốt lõi:** workload cần một danh tính có thể xác minh, quyền tối thiểu và credential có vòng đời ngắn. Cloud-native identity, federation, STS, mTLS và SPIFFE giải quyết các lớp khác nhau nhưng có thể phối hợp thành một mô hình thống nhất. Khi trust policy ràng buộc đúng issuer/subject/audience, credential được refresh và thu hồi có kiểm soát, còn audit truy vết được từng workload, hệ thống giảm đáng kể rủi ro từ khóa tĩnh và giới hạn blast radius khi một process bị xâm nhập.
