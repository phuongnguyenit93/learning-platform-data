# Chuẩn hóa template, baseline bảo mật và ngoại lệ có thời hạn

Trong quản trị tài nguyên compute, mỗi nhóm có thể tự tạo máy ảo, cụm container, workload Kubernetes hoặc hàm serverless theo cách riêng. Nếu mỗi lần triển khai dùng một bộ cấu hình khác nhau, tổ chức khó kiểm soát quyền truy cập, image, mạng, mã hóa, logging và chi phí. Các tài nguyên thiếu nhãn hoặc thiếu owner cũng làm cho việc điều tra sự cố và thu hồi tài nguyên trở nên chậm.

**Template compute** là mẫu cấu hình đã chuẩn hóa để tạo workload theo một mục đích cụ thể. **Security baseline** là tập yêu cầu bảo mật tối thiểu phải được đáp ứng. **Ngoại lệ có thời hạn** là sự cho phép có phạm vi rõ ràng để tạm thời không đáp ứng một kiểm soát, kèm người chịu trách nhiệm, biện pháp bù đắp và ngày hết hạn.

Ba cơ chế này bổ trợ nhau: template giúp triển khai nhất quán, baseline xác định điều kiện an toàn, còn ngoại lệ cho phép xử lý nhu cầu đặc biệt mà vẫn duy trì khả năng kiểm soát và truy vết.

## 1. Mục tiêu và phạm vi chuẩn hóa

Chuẩn hóa không có nghĩa mọi workload phải dùng cùng một kích thước máy hoặc cùng một cấu hình mạng. Template cần cung cấp phần mặc định chung và các lựa chọn được phê duyệt cho từng loại workload.

Mục tiêu quản trị gồm:

- Tạo tài nguyên có owner, môi trường, ứng dụng và mục đích rõ ràng.
- Áp dụng cấu hình bảo mật tối thiểu ngay từ lúc tạo tài nguyên.
- Giảm thay đổi thủ công và drift giữa các môi trường.
- Làm cho cấu hình có thể kiểm tra tự động trong pipeline và khi tài nguyên đang chạy.
- Cho phép nhóm phát triển chọn profile CPU, memory, GPU, storage và network phù hợp.
- Ghi nhận ngoại lệ, người phê duyệt, rủi ro và thời hạn khắc phục.
- Thu hồi hoặc điều chỉnh quyền và tài nguyên khi workload kết thúc.

Phạm vi template nên bao phủ các mô hình compute mà tổ chức đang sử dụng: VM, container/Kubernetes, batch job và serverless function. Các yêu cầu chung như owner, tagging, logging, identity và mã hóa có thể được chuẩn hóa; phần cấu hình riêng cho từng runtime nên nằm trong profile tương ứng.

## 2. Cấu trúc của một template compute

Một template có thể chia thành các nhóm thông tin sau:

| Nhóm | Nội dung | Mục đích |
|---|---|---|
| Metadata | Tên workload, owner, team, application, environment, cost center | Xác định trách nhiệm và phân bổ chi phí |
| Runtime | VM image, container image, function runtime, architecture | Giới hạn runtime và artifact được phép |
| Resources | CPU, memory, GPU, storage, timeout, concurrency | Tránh thiếu hoặc cấp phát quá mức |
| Network | Subnet, ingress/egress, security group, service exposure | Giới hạn đường truy cập |
| Identity | Runtime role, service account, quyền truy cập dịch vụ | Áp dụng least privilege |
| Data protection | Encryption, secret reference, backup, retention | Bảo vệ dữ liệu và khả năng khôi phục |
| Observability | Audit log, application log, metrics, health check | Điều tra và vận hành |
| Lifecycle | Expiry, patch policy, maintenance window, shutdown | Quản lý vòng đời tài nguyên |
| Governance | Baseline version, policy profile, exception reference | Chứng minh cấu hình đã qua kiểm soát |

Mỗi trường cần có kiểu dữ liệu, giá trị hợp lệ, mặc định và quy tắc bắt buộc. Ví dụ, owner phải là nhóm hoặc định danh có thể liên hệ; environment chỉ nhận các giá trị đã thống nhất; image phải đến từ registry được chấp thuận.

Một template tốt cũng ghi rõ trường nào người dùng được phép thay đổi. Người dùng có thể chọn số CPU trong một khoảng đã duyệt, nhưng không tự ý tắt audit log hoặc cấp quyền quản trị rộng cho workload.

## 3. Thiết kế template theo loại workload

### 3.1. Template máy ảo

Template VM nên chuẩn hóa:

- Image nền đã được vá và kiểm tra, ưu tiên image được quản lý tập trung.
- Kiến trúc CPU, loại máy và profile tài nguyên.
- Boot volume mã hóa, dung lượng và loại storage được phép.
- Subnet, firewall/security group và quy tắc không công khai trực tiếp khi không cần.
- Instance identity hoặc managed identity thay cho access key tĩnh.
- Secure boot, TPM hoặc các tính năng bảo vệ nền tảng nếu loại máy hỗ trợ.
- Agent quản lý bản vá, endpoint protection và log forwarding.
- Quy tắc backup, lịch bảo trì, shutdown và thời hạn tồn tại.

Không nên nhúng mật khẩu quản trị vào image hoặc user data. Cần quản lý tài khoản khởi tạo, SSH key/certificate và quyền truy cập thông qua danh tính tập trung. Nếu VM có public endpoint, template cần yêu cầu lý do và giới hạn nguồn truy cập.

### 3.2. Template container và Kubernetes

Template container nên quy định:

- Image đến từ registry được duyệt và được ghim bằng digest.
- Chạy non-root khi ứng dụng hỗ trợ; hạn chế Linux capabilities.
- Filesystem read-only nếu không cần ghi; vùng ghi tạm được khai báo rõ.
- Seccomp profile và security context phù hợp.
- Requests/limits CPU, memory và ephemeral storage.
- Service account riêng cho workload, không dùng quyền mặc định quá rộng.
- Network policy, ingress và egress theo nhu cầu.
- Secret được mount hoặc lấy từ secret manager; không ghi trong image hay manifest công khai.
- Liveness/readiness probe, graceful shutdown và log chuẩn.

Template cũng cần quy định namespace, quota, Pod Security hoặc admission policy, storage class và cách tiếp xúc dịch vụ. Một workload cần quyền đặc biệt như host networking, privileged container hoặc mount host path phải đi qua quy trình ngoại lệ phù hợp.

### 3.3. Template serverless và batch

Với function serverless, template nên có runtime được hỗ trợ, phiên bản dependency, memory, timeout, concurrency, trigger, execution role, logging và network configuration. Quyền của function chỉ nên cho phép thao tác trên tài nguyên mà chức năng thực sự cần.

Với batch job, bổ sung CPU, memory, GPU, thời gian tối đa, retry, queue, vùng dữ liệu đầu vào/đầu ra và chính sách lưu kết quả. Job cần có owner, batch ID hoặc correlation ID để theo dõi.

Không nên dùng một template chung quá rộng khiến các trường quan trọng trở thành tùy chọn. Nên có profile theo loại workload, nhưng vẫn kế thừa baseline và metadata chung.

## 4. Security baseline cho compute

Baseline là mức bảo vệ tối thiểu áp dụng cho tài nguyên trong phạm vi quản trị. Tổ chức có thể có baseline chung và các profile tăng cường cho dữ liệu nhạy cảm, môi trường production hoặc workload có yêu cầu tuân thủ cao.

### 4.1. Danh tính và quyền

- Mỗi workload dùng identity riêng hoặc identity theo nhóm chức năng có ranh giới rõ ràng.
- Cấp quyền tối thiểu theo tài nguyên và hành động cần thiết.
- Ưu tiên managed identity, instance profile hoặc workload identity federation.
- Không dùng tài khoản cá nhân hay khóa truy cập dài hạn làm danh tính runtime.
- Rà soát quyền định kỳ và thu hồi quyền khi workload hoặc owner kết thúc.
- Tách quyền deploy khỏi quyền runtime; người triển khai không tự động có toàn quyền dữ liệu production.

### 4.2. Image, phần mềm và chuỗi cung ứng

- Chỉ dùng image từ registry hoặc nguồn phát hành được phê duyệt.
- Ghim image bằng digest hoặc artifact checksum.
- Quét lỗ hổng và malware theo chính sách; chặn artifact vi phạm ngưỡng nghiêm trọng đã định.
- Duy trì SBOM hoặc metadata dependency khi yêu cầu.
- Ký artifact và xác minh chữ ký trước khi triển khai nếu nền tảng hỗ trợ.
- Có lịch vá OS, runtime, base image và thư viện.
- Xác định phiên bản runtime còn được hỗ trợ và thời hạn nâng cấp.

### 4.3. Mạng và bề mặt tấn công

- Mặc định đặt workload trong mạng riêng.
- Chỉ mở ingress từ nguồn và cổng cần thiết.
- Giới hạn egress tới dependency, endpoint và dịch vụ được phép.
- Dùng TLS cho kết nối; dùng mTLS khi yêu cầu xác thực hai chiều giữa dịch vụ.
- Bảo vệ metadata service của VM theo cơ chế của nền tảng.
- Tránh IP công khai cho workload nội bộ; nếu cần public exposure, phải có kiểm soát lớp ứng dụng và lớp mạng.
- Tách môi trường production, staging và development bằng ranh giới mạng và quyền phù hợp.

### 4.4. Dữ liệu và mã hóa

- Bật mã hóa cho volume, object và database theo yêu cầu phân loại dữ liệu.
- Quản lý encryption key bằng dịch vụ hoặc quy trình được phê duyệt.
- Không ghi secret vào image, source control, user data hoặc log.
- Có backup và kiểm tra khả năng restore theo RPO/RTO.
- Quy định retention và xóa dữ liệu tạm, snapshot và backup.
- Hạn chế truy cập dữ liệu theo owner, workload identity và môi trường.

### 4.5. Logging, giám sát và audit

- Gửi audit log quản trị tới nơi lưu tập trung có kiểm soát quyền.
- Thu thập log runtime và log ứng dụng theo schema có thể truy vấn.
- Gắn resource ID, workload, owner, environment và correlation ID.
- Theo dõi thay đổi cấu hình, quyền, network exposure và trạng thái patch.
- Cảnh báo khi baseline bị vi phạm hoặc resource không còn owner.
- Đồng bộ thời gian để hỗ trợ đối chiếu sự kiện.

### 4.6. Vòng đời và độ bền vận hành

- Xác định owner và ngày review cho mỗi workload.
- Áp dụng patch window và quy trình cập nhật.
- Đặt backup policy cho dữ liệu cần khôi phục.
- Giới hạn thời gian tồn tại cho môi trường thử nghiệm và tài nguyên tạm.
- Có health check, shutdown behavior và kế hoạch phục hồi.
- Dọn tài nguyên mồ côi, snapshot không còn cần và image cũ theo retention.

Baseline cần được viết thành các yêu cầu có thể kiểm chứng. Câu “bảo mật mạng tốt” không thể dùng làm policy. Yêu cầu như “không có ingress từ Internet trừ khi có exception còn hiệu lực” hoặc “mọi volume production phải bật encryption” có thể được kiểm tra tự động.

## 5. Template mẫu kế thừa baseline

Ví dụ YAML sau mô tả một hợp đồng cấu hình compute mang tính khái niệm. Đây không phải schema trực tiếp của một nhà cung cấp cloud; các trường cần được ánh xạ sang Terraform module, Helm chart, Kubernetes admission policy hoặc API triển khai của nền tảng đang dùng.

~~~yaml
apiVersion: platform.example/v1
kind: ComputeWorkload
metadata:
  name: order-api
  owner: team-commerce
  application: order-management
  environment: production
  costCenter: CC-042
  baseline: compute-secure-v3
spec:
  runtime:
    type: container
    image: registry.example.com/orders/order-api@sha256:IMAGE_DIGEST
    architecture: amd64
  resources:
    cpuRequest: "500m"
    memoryRequest: "512Mi"
    memoryLimit: "1Gi"
  identity:
    serviceAccount: order-api-runtime
    permissionsProfile: order-api-minimal
  network:
    exposure: internal
    ingressProfile: internal-service
    egressProfile: approved-dependencies
  security:
    runAsNonRoot: true
    readOnlyRootFilesystem: true
    imageSignatureRequired: true
    encryptionRequired: true
  observability:
    auditEnabled: true
    logsEnabled: true
    metricsEnabled: true
  lifecycle:
    ownerReviewDays: 90
~~~

Template trên thể hiện các giá trị cần có và mối liên hệ giữa workload với baseline. Khi triển khai thật, cần kiểm tra schema, kiểu dữ liệu, giá trị enum và cách provider thực thi từng trường. Không được coi việc manifest chứa trường security là bằng chứng runtime đã áp dụng thành công; phải kiểm tra trạng thái thực tế sau deploy.

### 5.1. Giá trị mặc định và lựa chọn được phép

Template nên có:

- **Required fields:** owner, environment, image, runtime identity và profile tài nguyên.
- **Secure defaults:** private exposure, encryption, logging, non-root và image verification khi runtime hỗ trợ.
- **Allowed values:** danh sách region, instance family, runtime version, registry và storage class được duyệt.
- **Bounded values:** CPU, memory, timeout, concurrency và dung lượng tối đa.
- **Conditional requirements:** nếu exposure là public thì cần ingress profile, TLS và phê duyệt bổ sung.
- **Forbidden values:** wildcard admin permission, image không rõ nguồn hoặc secret dạng plaintext.

Không nên dùng giá trị mặc định che giấu thiếu thông tin quan trọng. Nếu owner không được khai báo, pipeline cần từ chối tạo tài nguyên thay vì tự gán một team chung không chịu trách nhiệm.

## 6. Chính sách baseline và cách thực thi

Baseline chỉ có hiệu lực khi được kiểm tra ở nhiều giai đoạn:

~~~mermaid
flowchart TD
    A["Developer chọn template"] --> B["Validate schema"]
    B --> C["Policy check trong CI/CD"]
    C --> D{"Đạt baseline?"}
    D -- "Không" --> E["Từ chối hoặc tạo yêu cầu exception"]
    D -- "Có" --> F["Deploy tài nguyên"]
    F --> G["Runtime / cloud config scan"]
    G --> H{"Drift hoặc vi phạm?"}
    H -- "Không" --> I["Theo dõi định kỳ"]
    H -- "Có" --> J["Remediate hoặc đánh giá exception"]
    J --> I
    I --> K["Review và tái chứng nhận"]
~~~

### 6.1. Kiểm tra trước triển khai

Pipeline có thể kiểm tra:

1. Schema template có hợp lệ không?
2. Owner, environment và cost center có tồn tại không?
3. Image có thuộc registry được duyệt và ghim digest không?
4. CPU/memory/timeout có nằm trong profile cho phép không?
5. Identity có dùng quyền quá rộng không?
6. Public exposure, privileged mode hoặc host access có bị cấm không?
7. Encryption, logging và backup có được bật theo phân loại dữ liệu không?
8. Exception reference có tồn tại và còn hiệu lực nếu workload cần miễn trừ?

Các lỗi baseline có thể chia thành blocking và warning. Ví dụ thiếu owner hoặc public database không có phê duyệt nên là blocking; nhãn mô tả chưa đầy đủ có thể là warning nếu chưa ảnh hưởng kiểm soát bắt buộc. Mức độ phải được quy định thống nhất.

### 6.2. Kiểm tra sau triển khai

Cấu hình thực tế có thể lệch khỏi template do thay đổi thủ công, thao tác console hoặc lỗi automation. Vì vậy cần kiểm tra định kỳ:

- So sánh desired configuration với actual configuration.
- Phát hiện security group mở rộng, role được thêm quyền hoặc encryption bị tắt.
- Kiểm tra image/runtime có còn được hỗ trợ và không vượt thời hạn vá.
- Xác nhận log và metric vẫn được gửi.
- Kiểm tra owner, expiry và exception reference.
- Tự động sửa các sai lệch an toàn, hoặc tạo ticket có owner và thời hạn cho sai lệch cần đánh giá.

Một số thay đổi có thể được tự động khôi phục, như bật lại logging nếu không ảnh hưởng workload. Thay đổi có khả năng gây gián đoạn cần quy trình change management hoặc đánh giá trước khi remediation.

## 7. Ngoại lệ có thời hạn là gì?

Ngoại lệ cho phép một workload tạm thời không đáp ứng một kiểm soát cụ thể. Ví dụ, một ứng dụng cũ chưa hỗ trợ TLS phiên bản mới hoặc một thiết bị đặc thù cần cổng mạng chưa có trong baseline.

Ngoại lệ không làm thay đổi baseline cho các workload khác. Nó chỉ áp dụng cho đối tượng, kiểm soát và khoảng thời gian đã được phê duyệt.

Một ngoại lệ hợp lệ cần có:

| Trường | Yêu cầu |
|---|---|
| Exception ID | Mã duy nhất để truy vết |
| Resource scope | Resource ID, workload hoặc nhóm cụ thể |
| Control reference | Baseline rule được xin miễn |
| Rationale | Lý do kỹ thuật/nghiệp vụ và vì sao chưa thể tuân thủ |
| Risk assessment | Tác động, khả năng khai thác và mức độ nhạy cảm |
| Compensating controls | Biện pháp bù đắp trong thời gian miễn trừ |
| Owner | Cá nhân/nhóm chịu trách nhiệm khắc phục |
| Approver | Người có thẩm quyền chấp thuận theo mức rủi ro |
| Start and expiry | Thời điểm bắt đầu và ngày hết hạn |
| Remediation plan | Hành động, mốc hoàn thành và bằng chứng |
| Review cadence | Tần suất kiểm tra trước ngày hết hạn |
| Status | Requested, approved, active, expired, revoked hoặc closed |

Không nên chấp nhận ngoại lệ chung cho toàn tài khoản, toàn tổ chức hoặc một wildcard resource nếu không có lý do đặc biệt và kiểm soát tương xứng. Phạm vi càng rộng, rủi ro càng khó giới hạn.

## 8. Quy trình yêu cầu, phê duyệt và hết hạn

Một quy trình điển hình:

1. **Tạo yêu cầu:** workload owner chọn control cụ thể và resource bị ảnh hưởng.
2. **Giải thích nhu cầu:** nêu nguyên nhân, thời gian cần miễn trừ và phương án thay thế đã xem xét.
3. **Đánh giá rủi ro:** security/platform owner xem xét dữ liệu, exposure, quyền và khả năng bị khai thác.
4. **Đề xuất bù đắp:** giới hạn network, tăng giám sát, giảm quyền hoặc cô lập workload.
5. **Phê duyệt:** người có thẩm quyền quyết định theo risk tier; người yêu cầu không tự phê duyệt ngoại lệ của mình.
6. **Đăng ký:** lưu exception ID, scope, approver, ngày hiệu lực và ngày hết hạn trong hệ thống quản trị.
7. **Theo dõi:** kiểm tra remediation plan và trạng thái rủi ro theo lịch.
8. **Hết hạn:** tự động thu hồi miễn trừ, chuyển về baseline hoặc chặn workload theo chính sách.
9. **Đóng:** lưu bằng chứng khắc phục và xác nhận kiểm soát đã đạt.

~~~mermaid
stateDiagram-v2
    [*] --> Requested
    Requested --> RiskReview
    RiskReview --> Rejected
    RiskReview --> Approved
    Approved --> Active
    Active --> RenewReview
    RenewReview --> Active: gia hạn được duyệt
    RenewReview --> Expired: không gia hạn
    Active --> Revoked: thu hồi sớm
    Active --> Closed: đã khắc phục
    Expired --> Remediating
    Revoked --> Remediating
    Remediating --> Closed
    Rejected --> [*]
    Closed --> [*]
~~~

Ngoại lệ phải có ngày hết hạn thực sự. Không dùng giá trị “không thời hạn” hoặc ngày rất xa để né quy trình review. Nếu cần tiếp tục, owner phải nộp yêu cầu gia hạn trước khi hết hạn, cung cấp bằng chứng tiến độ và đánh giá lại rủi ro.

## 9. Ví dụ hồ sơ ngoại lệ

Giả sử một workload tích hợp với thiết bị tại nhà máy chỉ hỗ trợ kết nối TCP tới cổng 8443 từ một dải IP đối tác. Baseline mạng mặc định chặn ingress từ ngoài vùng private. Nhóm vận hành chưa thể nâng cấp thiết bị đối tác trong 45 ngày.

Hồ sơ đề xuất:

~~~yaml
exception:
  id: EXC-2026-0142
  resource:
    workload: factory-gateway-07
    environment: production
  control:
    id: NET-INGRESS-PRIVATE-ONLY
    requestedDeviation: allow-partner-source
  rationale: legacy-partner-device-upgrade-window
  risk: medium
  compensatingControls:
    - sourceIpAllowlist
    - tlsRequired
    - dedicatedSecurityGroup
    - enhancedConnectionLogging
  owner: team-edge-operations
  approver: security-platform-lead
  startAt: "2026-11-22T00:00:00Z"
  expiresAt: "2027-01-06T00:00:00Z"
  remediation:
    action: upgrade-partner-device-and-remove-ingress-rule
    targetDate: "2026-12-20"
  status: approved
~~~

Đây là hồ sơ minh họa, không phải schema chuẩn của một sản phẩm quản trị. Khi áp dụng, cần xác minh approver có thẩm quyền, resource ID chính xác và dải IP đã được kiểm chứng.

Trong thời gian ngoại lệ:

- Chỉ cho phép đúng IP nguồn và cổng cần thiết.
- Bắt buộc TLS và xác minh chứng thư.
- Dùng security group riêng, không mở rộng rule cho workload khác.
- Ghi log kết nối và cảnh báo khi nguồn truy cập thay đổi.
- Review định kỳ xem thiết bị đối tác đã nâng cấp chưa.
- Đến ngày hết hạn, xóa rule và xác minh kết nối không còn được phép.

Nếu ngày hết hạn đến mà remediation chưa hoàn tất, ngoại lệ chuyển sang expired. Owner phải xin gia hạn và được đánh giá lại; hệ thống không tự kéo dài quyền.

## 10. Gia hạn, thu hồi và xử lý ngoại lệ quá hạn

Gia hạn là một quyết định mới, không phải thao tác cập nhật ngày hết hạn một cách tự động. Yêu cầu gia hạn cần trả lời:

- Lý do ban đầu còn tồn tại không?
- Owner đã hoàn thành những bước nào?
- Biện pháp bù đắp có còn hoạt động?
- Có thay đổi về dữ liệu, network hoặc threat model không?
- Có giải pháp thay thế mới khả thi hơn không?
- Thời gian gia hạn tối thiểu cần thiết là bao lâu?

Có thể thu hồi ngoại lệ trước hạn nếu workload đã khắc phục, rủi ro tăng cao, owner thay đổi, thiết bị bị xâm nhập hoặc điều kiện phê duyệt không còn đúng.

Khi ngoại lệ hết hạn:

1. Gửi cảnh báo trước ngày hết hạn cho owner và approver.
2. Tạo ticket remediation có deadline.
3. Đến hạn, tự động thu hồi quyền/route/config được miễn trừ nếu an toàn.
4. Nếu không thể tự động thu hồi mà không gây tác động lớn, chặn triển khai mới, cô lập workload hoặc chuyển sang trạng thái cần phê duyệt khẩn cấp theo runbook.
5. Ghi nhận trạng thái quá hạn và báo cáo lên nhóm quản trị.

Không nên để ngoại lệ hết hạn biến thành một cấu hình được chấp nhận vĩnh viễn. Báo cáo cần thể hiện số ngoại lệ active, sắp hết hạn, quá hạn, đã gia hạn và thời gian trung bình để khắc phục.

## 11. Liên kết template, baseline và exception

Template nên khai báo phiên bản baseline đang áp dụng. Nếu một workload cần ngoại lệ, template hoặc deployment record tham chiếu exception ID. Policy engine kiểm tra exception có đúng resource, control và thời hạn hay không.

Ví dụ logic kiểm tra:

~~~text
for each workload:
    validate_template_schema(workload)
    violations = evaluate_security_baseline(workload)

    for each violation:
        exception = find_active_exception(
            resource = workload.id,
            control = violation.control_id,
            now = current_time
        )

        if exception is valid and exception.scope_matches:
            require_compensating_controls(exception)
            record_accepted_deviation(exception.id)
        else:
            block_deployment(violation)
~~~

Đoạn giả mã minh họa nguyên tắc. Trong triển khai thật, policy engine cần xác minh chữ ký hoặc nguồn dữ liệu của exception registry, thời gian theo UTC, resource scope và quyền phê duyệt. Không nên chỉ kiểm tra xem có chuỗi exception ID trong annotation hay không.

Có thể chia kết quả policy thành:

- **Pass:** đáp ứng baseline.
- **Pass with approved exception:** có sai lệch nhưng exception còn hiệu lực và biện pháp bù đắp được kiểm tra.
- **Warn:** thiếu yếu tố khuyến nghị chưa phải kiểm soát bắt buộc.
- **Block:** vi phạm kiểm soát bắt buộc, exception không hợp lệ hoặc đã hết hạn.

## 12. Quản lý phiên bản template và baseline

Template và baseline cần được version hóa như mã nguồn:

- Lưu source trong repository được kiểm soát.
- Review thay đổi qua pull request hoặc quy trình phê duyệt.
- Gắn version và changelog.
- Kiểm thử schema và policy bằng ví dụ hợp lệ/không hợp lệ.
- Xác định workload nào chịu ảnh hưởng khi baseline thay đổi.
- Có thời gian chuyển tiếp cho thay đổi không tương thích.
- Xác định ngày ngừng hỗ trợ phiên bản template cũ.
- Lưu lịch sử deploy để truy lại template version tại thời điểm tạo tài nguyên.

Không nên âm thầm thay đổi template đang dùng trong production. Một baseline mới có thể làm workload cũ không còn hợp lệ; cần lập kế hoạch remediation theo mức rủi ro và thời hạn cụ thể.

Ví dụ versioning:

| Phiên bản | Thay đổi | Hành động |
|---|---|---|
| compute-secure-v1 | Baseline ban đầu | Duy trì cho workload cũ trong thời gian chuyển tiếp |
| compute-secure-v2 | Bắt buộc mã hóa volume và audit log | Đánh giá workload hiện hữu và lên lịch remediation |
| compute-secure-v3 | Ghim image digest và hạn chế quyền runtime | Cập nhật template, policy test và pipeline |

Nếu thay đổi là bản vá khẩn cấp cho kiểm soát nghiêm trọng, có thể rút ngắn thời gian chuyển tiếp theo quy trình ứng phó sự cố.

## 13. Ví dụ pipeline kiểm tra template

Một pipeline triển khai có thể thực hiện các bước:

~~~bash
# Kiểm tra cú pháp và cấu trúc IaC
terraform fmt -check
terraform validate

# Kiểm tra manifest Kubernetes
kubectl apply --dry-run=client -f deploy/base/

# Chạy policy test bằng công cụ policy-as-code của tổ chức
policy-check deploy/ --baseline compute-secure-v3

# Kiểm tra image và metadata phát hành
image-scan registry.example.com/orders/order-api@sha256:IMAGE_DIGEST
~~~

Các lệnh policy-check và image-scan ở trên là tên lệnh minh họa; cần thay bằng công cụ thực tế của tổ chức. Dry-run client chỉ kiểm tra một phần cú pháp và không thay thế admission policy hoặc kiểm tra trên cluster đích.

Sau deploy, pipeline hoặc continuous compliance scanner cần kiểm tra cấu hình thực tế. Kết quả cần lưu build ID, commit, template version, baseline version, resource ID, policy result và exception ID nếu có.

## 14. Chỉ số quản trị và báo cáo

Các chỉ số có thể dùng để đánh giá hiệu quả chương trình:

| Chỉ số | Cách hiểu | Mục tiêu quản trị |
|---|---|---|
| Template adoption | Tỷ lệ workload mới dùng template được duyệt | Tăng tính nhất quán |
| Baseline compliance | Tỷ lệ resource đạt baseline | Giảm cấu hình yếu |
| Exception count | Số ngoại lệ active theo control/risk | Nhận diện điểm yếu hệ thống |
| Expired exception count | Số ngoại lệ đã hết hạn nhưng chưa đóng | Ngăn miễn trừ tồn tại lâu |
| Mean time to remediate | Thời gian trung bình từ phát hiện đến khắc phục | Cải thiện tốc độ xử lý |
| Drift rate | Tỷ lệ resource lệch cấu hình chuẩn | Đo hiệu quả kiểm soát sau deploy |
| Owner coverage | Tỷ lệ resource có owner hợp lệ | Tăng trách nhiệm vận hành |
| Unmanaged resource count | Tài nguyên không có template hoặc baseline reference | Giảm tài nguyên ngoài quản trị |

Không nên chỉ tối ưu tỷ lệ compliance bằng cách hạ baseline hoặc cấp exception hàng loạt. Cần xem cả mức rủi ro, chất lượng biện pháp bù đắp và tốc độ khắc phục.

## 15. Checklist chuẩn hóa và quản lý ngoại lệ

- [ ] Template có metadata owner, application, environment và cost center bắt buộc.
- [ ] Template có profile riêng cho VM, container/Kubernetes, serverless và batch.
- [ ] Runtime, image, architecture và resource profile nằm trong danh sách được duyệt.
- [ ] Identity dùng quyền tối thiểu và secret được quản lý an toàn.
- [ ] Network exposure mặc định hạn chế; ingress/egress có phạm vi rõ.
- [ ] Encryption, logging, backup và lifecycle được khai báo theo phân loại dữ liệu.
- [ ] Baseline được biểu diễn thành policy có thể kiểm tra tự động.
- [ ] Pipeline kiểm tra trước deploy và scanner kiểm tra drift sau deploy.
- [ ] Mọi sai lệch có exception ID, resource scope và control reference rõ ràng.
- [ ] Exception có rationale, risk assessment, compensating controls, owner và approver.
- [ ] Mỗi exception có ngày bắt đầu, ngày hết hạn và remediation plan.
- [ ] Gia hạn cần đánh giá và phê duyệt lại; không tự động kéo dài.
- [ ] Hết hạn có cảnh báo, thu hồi hoặc biện pháp xử lý theo runbook.
- [ ] Template và baseline có version, changelog, review và kế hoạch nâng cấp.
- [ ] Báo cáo thể hiện compliance, drift, ngoại lệ active/quá hạn và thời gian khắc phục.

Chuẩn hóa template giúp workload được tạo với cấu hình có thể dự đoán và truy vết. Security baseline chuyển yêu cầu bảo mật thành các điều kiện kiểm tra được ở cả trước và sau triển khai. Ngoại lệ có thời hạn xử lý nhu cầu đặc biệt bằng phạm vi giới hạn, người chịu trách nhiệm, biện pháp bù đắp và kế hoạch khắc phục. Khi ba cơ chế được quản lý cùng nhau, tổ chức có thể duy trì tính nhất quán của compute mà vẫn xử lý được khác biệt thực tế trong vận hành.
