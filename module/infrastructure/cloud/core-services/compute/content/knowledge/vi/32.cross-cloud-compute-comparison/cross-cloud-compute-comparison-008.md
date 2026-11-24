# Thiết kế khả năng di chuyển workload và đánh giá mức phụ thuộc nhà cung cấp

Khi triển khai compute trên cloud, một workload có thể sử dụng máy ảo, container, Kubernetes, hàm serverless, database, object storage, queue và nhiều dịch vụ được quản lý. Mỗi dịch vụ giúp giảm công việc vận hành hoặc cải thiện hiệu năng, nhưng cũng có thể tạo ra phụ thuộc vào API, định dạng dữ liệu, mô hình quyền và cách vận hành riêng của nhà cung cấp.

**Khả năng di chuyển workload (workload portability)** là mức độ một ứng dụng có thể được chuyển sang môi trường khác với lượng thay đổi, thời gian gián đoạn và rủi ro chấp nhận được. **Mức phụ thuộc nhà cung cấp (vendor lock-in)** phản ánh chi phí và độ khó khi thay thế một dịch vụ hoặc chuyển workload sang nhà cung cấp khác.

Thiết kế tốt không nhất thiết phải làm mọi thành phần chạy giống hệt trên mọi cloud. Mục tiêu là hiểu rõ thành phần nào cần linh hoạt, thành phần nào có thể dùng dịch vụ chuyên biệt, và chuẩn bị được dữ liệu, cấu hình, kỹ năng cùng quy trình cần thiết cho phương án chuyển đổi đã chọn.

## 1. Hiểu đúng về portability và vendor lock-in

Portability không phải một thuộc tính bật/tắt. Một ứng dụng có thể dễ chuyển compute nhưng khó chuyển database; container image có thể chạy ở nhiều nơi nhưng pipeline triển khai, identity và network vẫn phụ thuộc nền tảng.

Có thể xem xét portability theo các lớp:

| Lớp | Nội dung cần chuyển | Câu hỏi đánh giá |
|---|---|---|
| Source và build | Mã nguồn, dependency, quy trình build | Có thể build lại từ source và tái tạo artifact không? |
| Runtime và compute | VM image, container, Kubernetes workload, function | Runtime đích có hỗ trợ kiến trúc và tính năng ứng dụng cần không? |
| Cấu hình và điều phối | IaC, deployment manifest, autoscaling, job scheduler | Cấu hình có tách phần chung và phần theo provider không? |
| Identity và security | Service account, IAM policy, secret, encryption key | Quyền có thể ánh xạ sang mô hình danh tính của môi trường đích không? |
| Network | VPC/VNet, subnet, routing, firewall, DNS, load balancer | Kết nối và chính sách mạng có thể tái tạo không? |
| Data | Database, object, volume, queue, backup | Dữ liệu có thể export/import, đồng bộ và kiểm chứng không? |
| Operations | Logging, metrics, tracing, alert, deployment | Đội ngũ có thể vận hành và xử lý sự cố bằng công cụ tương đương không? |
| Governance | Region, compliance, audit, quota, billing | Các yêu cầu pháp lý và tổ chức có được đáp ứng ở đích không? |

Vendor lock-in có thể xuất hiện ở nhiều mức:

- **Lock-in kỹ thuật:** ứng dụng gọi API độc quyền hoặc dùng tính năng chỉ có ở một dịch vụ.
- **Lock-in dữ liệu:** dữ liệu nằm trong định dạng, database hoặc storage khó export; dữ liệu lớn khiến việc chuyển tốn nhiều thời gian.
- **Lock-in vận hành:** đội ngũ phụ thuộc console, công cụ, quy trình và kỹ năng riêng của nhà cung cấp.
- **Lock-in hợp đồng và chi phí:** cam kết sử dụng, chiết khấu, phí egress hoặc chi phí thoát hợp đồng làm việc chuyển đổi đắt đỏ.
- **Lock-in về kiến trúc:** hệ thống được thiết kế quanh một dịch vụ managed có nhiều chức năng tích hợp, khiến việc thay thế cần thay đổi nhiều thành phần.

Một ứng dụng dùng container chưa chắc portable. Nếu container phụ thuộc một database API độc quyền, secret manager riêng, IAM policy riêng và queue có semantics đặc thù, phần compute chỉ là một phần nhỏ của bài toán di chuyển.

## 2. Đo mức phụ thuộc theo thành phần

Trước khi chọn chiến lược, lập danh mục các dịch vụ mà workload sử dụng. Với mỗi thành phần, ghi lại chức năng, giao diện, dữ liệu, mức độ quan trọng và phương án thay thế.

Ví dụ:

| Thành phần | Dịch vụ hiện tại | Phụ thuộc cần nhận diện | Khả năng thay thế |
|---|---|---|---|
| Compute | VM hoặc container service | Instance metadata, startup script, runtime | VM image, OCI container, Kubernetes |
| Orchestration | Managed Kubernetes | CNI, CSI, ingress, load balancer, admission policy | Kubernetes API chung cộng adapter theo nền tảng |
| Database | Managed relational database | Engine version, extension, stored procedure, replication | Cùng engine ở provider khác hoặc database tương thích |
| Object storage | Managed object store | API, event notification, lifecycle, ACL, versioning | S3-compatible API hoặc adapter storage |
| Queue | Managed queue | Visibility timeout, ordering, retry, DLQ, delivery semantics | Queue tương đương và lớp tích hợp |
| Identity | IAM/workload identity | Policy language, role assumption, token exchange | OIDC federation và ánh xạ role |
| Observability | Logging/monitoring service | Query language, alert rule, dashboard | OpenTelemetry, Prometheus và log format chuẩn |
| Network | VPC/VNet và managed LB | Routing, private endpoint, firewall, DNS | IaC module và thiết kế mạng độc lập |

Có thể chấm mức phụ thuộc cho từng thành phần theo thang nội bộ từ 1 đến 5:

- **1 – Thấp:** giao diện mở, dữ liệu dễ export, có nhiều lựa chọn thay thế và đã thử chuyển.
- **2 – Hạn chế:** có vài cấu hình riêng nhưng adapter và tài liệu chuyển đổi đã tồn tại.
- **3 – Trung bình:** cần thay đổi đáng kể ở cấu hình, dữ liệu hoặc vận hành.
- **4 – Cao:** phụ thuộc API, semantics hoặc dữ liệu riêng; chưa có phương án thay thế đã kiểm thử.
- **5 – Rất cao:** dịch vụ là nền tảng cốt lõi, chuyển đổi cần tái kiến trúc hoặc thời gian gián đoạn lớn.

Điểm số chỉ giúp ưu tiên thảo luận. Cần ghi rõ bằng chứng, chẳng hạn số ngày chuyển dữ liệu, lượng code provider-specific, số thao tác thủ công, RTO/RPO có thể đạt và chi phí egress ước tính. Không nên cộng điểm các thành phần thành một con số duy nhất rồi coi đó là đánh giá chính xác của toàn hệ thống.

## 3. Lựa chọn chiến lược portability

Có nhiều mức thiết kế, từ dùng dịch vụ chuyên biệt đến xây dựng một nền tảng chạy ở nhiều cloud.

| Chiến lược | Cách làm | Lợi ích | Đánh đổi |
|---|---|---|---|
| Provider-native | Dùng sâu dịch vụ của một cloud | Tận dụng tính năng, hiệu năng và tích hợp; giảm công vận hành | Chi phí chuyển đổi có thể cao |
| Portable compute | Chuẩn hóa image, runtime và deployment | Chuyển VM/container dễ hơn | Data, identity, network và operations vẫn có thể khóa |
| Portable platform | Dùng Kubernetes, IaC và giao diện quan sát chuẩn | Giảm phụ thuộc ở lớp compute/orchestration | Cần đội ngũ vận hành platform và quản lý khác biệt giữa cloud |
| Hybrid | Chạy một phần tại cloud, một phần tại chỗ hoặc edge | Đặt workload gần dữ liệu, đáp ứng yêu cầu locality | Tăng độ phức tạp kết nối, identity và đồng bộ |
| Multi-cloud active | Cùng workload phục vụ trên nhiều cloud | Có thể tăng khả năng dự phòng hoặc đáp ứng yêu cầu địa lý | Tốn chi phí, nhân đôi vận hành và đồng bộ dữ liệu |
| Exit-ready | Dùng dịch vụ chuyên biệt nhưng có export, backup và kế hoạch thay thế | Giữ lợi ích managed service, vẫn có đường thoát thực tế | Cần đầu tư kiểm thử và duy trì runbook |

Không phải hệ thống nào cũng cần multi-cloud. Chạy đồng thời nhiều cloud có thể làm tăng số control plane, mô hình quyền, network, pipeline, chi phí nhân sự và nguy cơ cấu hình sai. Nếu yêu cầu chỉ là khả năng chuyển trong một khoảng thời gian xác định, kiến trúc exit-ready có thể hợp lý hơn.

Nên bắt đầu từ mục tiêu kinh doanh: cần chuyển vì chi phí, vùng dữ liệu, khả năng sẵn sàng, yêu cầu pháp lý, thay đổi hợp đồng hay giảm rủi ro gián đoạn dịch vụ? Mỗi mục tiêu dẫn đến mức portability khác nhau.

## 4. Chuẩn hóa lớp compute và runtime

### 4.1. Máy ảo

Với workload chạy trên VM, portability phụ thuộc vào định dạng image, kiến trúc CPU, firmware, driver, hệ điều hành, boot process và các dịch vụ metadata của provider.

Để dễ di chuyển:

- Dùng image build tự động từ source hoặc cấu hình khai báo, thay vì chỉnh sửa máy thủ công.
- Ghi lại phiên bản OS, package, kernel module, agent và driver.
- Tách cấu hình môi trường khỏi image; không nhúng credential hoặc endpoint cố định.
- Tránh phụ thuộc trực tiếp vào metadata API của một cloud; đặt sau một adapter hoặc cung cấp cấu hình tương đương.
- Kiểm tra image có thể import vào định dạng và nền tảng VM đích hay không.
- Dùng công cụ cấu hình như cloud-init hoặc configuration management với module theo hệ điều hành.
- Xác minh license, secure boot, CPU feature và thiết bị tăng tốc trước khi chuyển.

Image VM có thể chuyển được nhưng hiệu năng vẫn khác do loại CPU, NUMA topology, storage và network. Phải benchmark workload ở môi trường đích thay vì chỉ xác nhận máy khởi động thành công.

### 4.2. Container

Container đóng gói ứng dụng và dependency, giúp giảm khác biệt giữa môi trường build và runtime. OCI image format và container runtime phổ biến tạo nền tảng tốt cho khả năng di chuyển.

Các nguyên tắc nên áp dụng:

- Build image theo chuẩn OCI và ghim base image theo phiên bản hoặc digest.
- Hỗ trợ đúng kiến trúc CPU của node đích, ví dụ amd64 hoặc arm64.
- Đưa cấu hình, secret và dữ liệu ra ngoài image.
- Không giả định đường dẫn volume, network interface hoặc quyền root giống nhau ở mọi runtime.
- Dùng health check, graceful shutdown và log theo chuẩn ứng dụng.
- Kiểm tra kernel capability, seccomp, cgroup version, GPU runtime và storage driver tại đích.

Container portability chủ yếu giải quyết đóng gói và runtime. Nó không tự chuyển database, persistent volume, load balancer, secret, DNS hay IAM.

### 4.3. Kubernetes

Kubernetes API chuẩn hóa nhiều đối tượng như Pod, Deployment, Service, ConfigMap, Secret và Job. Tuy nhiên, cluster managed của mỗi provider có thể khác nhau ở CNI, CSI, ingress, load balancer, autoscaling, identity integration và policy.

Manifest minh họa:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-api
  template:
    metadata:
      labels:
        app: order-api
    spec:
      containers:
        - name: api
          image: registry.example.com/orders/order-api@sha256:IMAGE_DIGEST
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              memory: "1Gi"
          env:
            - name: APP_ENV
              value: production
~~~

Manifest trên dùng API Kubernetes phổ biến, nhưng để chạy trong production còn cần Service/Ingress hoặc Gateway API, policy mạng, identity, secret, storage và telemetry. Các trường tích hợp với provider nên được đặt trong overlay hoặc module riêng theo môi trường.

Một cấu trúc repository có thể chia phần chung và phần đặc thù:

~~~text
deploy/
  base/
    deployment.yaml
    service.yaml
    network-policy.yaml
  overlays/
    cloud-a/
      ingress.yaml
      workload-identity.yaml
      storage-class.yaml
    cloud-b/
      gateway.yaml
      workload-identity.yaml
      storage-class.yaml
~~~

Kustomize hoặc Helm có thể quản lý khác biệt cấu hình. Tránh tạo hai bộ manifest hoàn toàn tách rời nếu workload và chính sách chung có thể được tái sử dụng; ngược lại, không nên ép hai nền tảng có khác biệt thực chất vào một template quá nhiều điều kiện khó kiểm tra.

## 5. Quản lý phụ thuộc vào dịch vụ managed

Dịch vụ managed có thể giảm đáng kể công việc bảo trì database, queue, cache, workflow hoặc serverless. Đổi lại, ứng dụng có thể phụ thuộc vào API, semantics và tính năng riêng.

### 5.1. Database

Các yếu tố ảnh hưởng portability:

- Database engine và phiên bản.
- Extension, stored procedure, trigger và kiểu dữ liệu riêng.
- Collation, timezone, transaction isolation và behavior của sequence.
- Replication, CDC, backup format và khả năng point-in-time recovery.
- Giới hạn connection, query planner và hiệu năng của instance đích.
- Công cụ migration và khả năng đồng bộ thay đổi trong lúc chuyển.

Nếu dùng cùng engine ở hai cloud, việc di chuyển thường dễ hơn nhưng không tự động tương thích hoàn toàn. Phiên bản engine, extension, cấu hình, quyền và giới hạn managed service có thể khác nhau.

Nên lưu schema migration trong source control, kiểm thử trên engine/version đích, tránh phụ thuộc không cần thiết vào stored procedure riêng và định kỳ thử restore backup vào môi trường độc lập. Với database lớn, cần kế hoạch full copy kết hợp CDC hoặc replication để giảm downtime.

### 5.2. Object storage và file

Object storage thường có API và semantics riêng về bucket, key, ACL, lifecycle, versioning, encryption và event notification. S3-compatible không đồng nghĩa mọi tính năng của các dịch vụ tương thích đều giống nhau.

Để dễ chuyển:

- Dùng một interface ứng dụng cho thao tác object cơ bản như put, get, head và delete.
- Tách bucket name, endpoint, region và credential khỏi code.
- Lưu metadata nghiệp vụ trong định dạng độc lập; không dựa hoàn toàn vào object tag hoặc ACL riêng.
- Ghi nhận version, checksum, content type và encryption metadata.
- Dùng công cụ đồng bộ hỗ trợ kiểm tra checksum và resume.
- Đo throughput, request rate, egress và thời gian copy trên dữ liệu đại diện.

File system volume cần được đánh giá riêng. Snapshot hoặc disk image của provider có thể không import trực tiếp sang provider khác; cần export ở cấp file hoặc dùng giao thức chia sẻ chuẩn nếu phù hợp.

### 5.3. Queue và event

Queue có semantics quan trọng hơn tên API:

- At-most-once, at-least-once hoặc exactly-once trong phạm vi được định nghĩa.
- Thứ tự thông điệp toàn cục hay theo partition.
- Visibility timeout hoặc ack deadline.
- Retry, dead-letter queue và retention.
- Kích thước message, throughput và giới hạn concurrency.
- Cách xử lý duplicate, redelivery và poison message.

Thiết kế consumer idempotent, message có schema/version, correlation ID và khả năng phát lại. Nếu đổi queue provider, cần kiểm thử lại thứ tự, retry và delivery semantics; chỉ thay endpoint trong cấu hình là chưa đủ.

### 5.4. Serverless và workflow

Function serverless có thể dùng runtime chuẩn nhưng vẫn phụ thuộc trigger, event format, IAM, API gateway, timeout, concurrency, ephemeral storage và workflow service.

Nếu muốn giảm phụ thuộc:

- Giữ business logic trong thư viện hoặc package độc lập với handler.
- Viết adapter cho HTTP, queue, storage event và scheduler.
- Chuẩn hóa event schema và version.
- Tránh để logic nghiệp vụ gọi trực tiếp SDK của provider ở nhiều lớp.
- Ghi rõ timeout, retry và concurrency assumptions.
- Với workflow dài, xác định state machine có thể tái hiện ở nền tảng khác hay cần thiết kế lại.

Không nên cố xây một lớp trừu tượng chung cho mọi function service nếu các semantics khác nhau. Hãy giữ phần nghiệp vụ portable và cô lập phần tích hợp trong adapter có kiểm thử.

## 6. Tách code khỏi API và SDK riêng của provider

Một cách hữu ích là phân chia ứng dụng thành business core và adapter tích hợp.

~~~mermaid
flowchart LR
    A["HTTP / Queue / Scheduler"] --> B["Provider adapter"]
    B --> C["Application service"]
    C --> D["Business domain"]
    C --> E["Storage interface"]
    C --> F["Message interface"]
    E --> G["Provider storage adapter"]
    F --> H["Provider queue adapter"]
    G --> I["Managed storage"]
    H --> J["Managed queue"]
~~~

Business domain không nên biết credential được lấy từ dịch vụ nào hoặc object được lưu ở bucket cụ thể nào. Adapter chuyển giao diện nội bộ thành API của provider.

Ví dụ interface giả định:

~~~typescript
interface ObjectStore {
  put(key: string, body: Uint8Array, contentType: string): Promise<void>;
  get(key: string): Promise<Uint8Array>;
  delete(key: string): Promise<void>;
}

interface MessagePublisher {
  publish(topic: string, payload: Uint8Array, messageId: string): Promise<void>;
}
~~~

Mỗi cloud có implementation riêng. Business logic chỉ phụ thuộc interface, còn adapter chịu trách nhiệm chuyển request, error code, retry và authentication.

Lớp trừu tượng cần đủ nhỏ và bám vào nhu cầu thật của ứng dụng. Nếu interface cố bao phủ toàn bộ chức năng của nhiều dịch vụ, nó có thể trở thành mẫu số chung quá thấp, làm mất các khả năng quan trọng hoặc buộc ứng dụng triển khai lại những tính năng mà provider đã cung cấp tốt.

## 7. Infrastructure as Code và cấu hình đa môi trường

IaC giúp tái tạo compute, network, identity và storage từ source. Tuy nhiên, công cụ IaC không tự làm tài nguyên portable: Terraform có provider và resource riêng, còn module cloud-native thường chứa nhiều chi tiết đặc thù.

Nên tổ chức:

- **Module chung:** naming, tagging, policy baseline, cấu hình ứng dụng và thành phần thực sự giống nhau.
- **Module provider:** VPC/VNet, managed Kubernetes, load balancer, IAM, storage class, key management.
- **Environment configuration:** region, CIDR, instance family, quota, endpoint và secret reference.
- **State management:** remote state, lock, backup, quyền truy cập và quy trình chuyển state.
- **Drift detection:** so sánh hạ tầng thực tế với khai báo để phát hiện chỉnh sửa ngoài IaC.

Ví dụ cấu trúc:

~~~text
infra/
  modules/
    app-network-contract/
    app-runtime-contract/
  providers/
    cloud-a/
      network/
      compute/
      identity/
    cloud-b/
      network/
      compute/
      identity/
  environments/
    production-cloud-a/
    recovery-cloud-b/
~~~

Không nên giả định có thể dùng nguyên một state file Terraform cho hai provider hoặc chuyển state mà không kiểm tra resource mapping. Khi di chuyển, thường cần tạo hạ tầng đích bằng module phù hợp, import hoặc tái tạo tài nguyên, sau đó chuyển workload và dữ liệu theo kế hoạch.

## 8. Identity, secrets và bảo mật khi di chuyển

Mô hình IAM của các cloud khác nhau về principal, policy language, role assumption, resource hierarchy và điều kiện truy cập. Một policy có cùng mục tiêu nghiệp vụ có thể cần được biểu diễn khác nhau.

Để giữ khả năng chuyển đổi:

- Dùng OIDC hoặc workload federation khi có thể, tránh credential dài hạn gắn trong code.
- Xác định quyền theo hành động nghiệp vụ và tài nguyên cần truy cập.
- Quản lý secret qua interface ứng dụng và secret manager của từng môi trường.
- Lập danh mục encryption key, certificate, trust chain và quy trình rotate.
- Kiểm tra quyền service-to-service và quyền người vận hành sau khi chuyển.
- Không copy nguyên IAM policy từ provider cũ sang provider mới mà chưa rà soát principal và phạm vi resource.
- Lưu audit log theo định dạng và thời hạn phù hợp với yêu cầu tổ chức.

Key management là một ràng buộc di chuyển đáng kể. Dữ liệu mã hóa bằng key chỉ tồn tại trong KMS của cloud cũ không thể tự giải mã ở cloud mới. Cần giải mã và mã hóa lại bằng key đích theo quy trình được kiểm soát, hoặc thiết kế envelope encryption và quản lý key phù hợp với yêu cầu bảo mật.

## 9. Network và connectivity giữa các cloud

Mạng thường là phần bị đánh giá thiếu khi lập kế hoạch portability. Hai cloud có thể dùng cùng khái niệm VPC/VNet nhưng khác cách triển khai route, peering, private endpoint, firewall, DNS, load balancer và giới hạn địa chỉ.

Khi thiết kế:

- Dùng IP plan tránh trùng CIDR giữa các cloud, site và môi trường on-premises.
- Tách public/private subnet và chỉ mở egress cần thiết.
- Chuẩn hóa DNS naming và cách service discovery.
- Dùng TLS/mTLS cho kết nối service-to-service.
- Ghi rõ latency và bandwidth yêu cầu giữa application, database, queue và object storage.
- Kiểm thử firewall, MTU, DNS resolution và route trong môi trường đích.
- Tính phí truyền dữ liệu liên vùng và liên cloud.

Nếu workload được chia giữa hai cloud trong thời gian chuyển đổi, cần xác định luồng nào đi qua WAN, dữ liệu nào được replicate và cách xử lý khi kết nối bị gián đoạn. Không nên để database có hai writer độc lập nếu chưa có cơ chế phân giải conflict và nhất quán được thiết kế rõ ràng.

## 10. Portability của dữ liệu và kế hoạch chuyển đổi

Dữ liệu thường là phần tốn thời gian và rủi ro nhất. Trước khi di chuyển, cần biết dung lượng, tốc độ thay đổi, định dạng, retention, yêu cầu mã hóa và mức downtime chấp nhận được.

Một quy trình database migration điển hình:

1. Tạo database đích với engine/version và cấu hình tương thích.
2. Chạy schema migration và kiểm tra extension.
3. Sao chép full snapshot hoặc backup.
4. Bật CDC/replication để chuyển các thay đổi phát sinh sau snapshot.
5. Đối chiếu row count, checksum, constraint và dữ liệu nghiệp vụ.
6. Dừng ghi ở nguồn trong cửa sổ cutover hoặc chuyển sang chế độ read-only.
7. Đồng bộ phần thay đổi cuối, chuyển connection endpoint và mở ghi ở đích.
8. Theo dõi lỗi và giữ nguồn trong trạng thái có thể khôi phục theo thời hạn đã định.

Với object storage, có thể copy theo batch và checksum, sau đó đồng bộ phần object thay đổi. Cần lưu metadata, version, ACL tương đương, retention và encryption. Queue có thể cần drain thông điệp cũ, chuyển producer trước hoặc dùng bridge consumer để tránh mất hoặc xử lý trùng.

### 10.1. RPO và RTO

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất tính theo thời gian.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ.

Nếu RPO là 5 phút, cơ chế replication phải giữ độ trễ và khả năng phục hồi trong giới hạn tương ứng. Nếu RTO là 30 phút, cần chuẩn bị sẵn hạ tầng, image, secret, DNS và quy trình cutover đủ nhanh. Chỉ có backup hàng ngày thường không đáp ứng RPO thấp.

### 10.2. Chi phí egress và thời gian copy

Ước lượng sơ bộ thời gian truyền dữ liệu:

\[
T \approx \frac{D \times 8}{B \times \eta}
\]

Trong đó:

- D là dung lượng dữ liệu tính bằng byte.
- B là băng thông truyền tải tính bằng bit/giây.
- \(\eta\) là hiệu suất sử dụng đường truyền, nhỏ hơn hoặc bằng 1.

Ví dụ, 10 TB dữ liệu truyền qua đường truyền 1 Gbit/s với hiệu suất 70% cần thời gian lý thuyết xấp xỉ 31,7 giờ, chưa tính thời gian kiểm tra, retry, giới hạn request và thời gian đồng bộ phần thay đổi. Vì vậy, cần benchmark thực tế và tính phí egress, request, thiết bị truyền dữ liệu hoặc đường truyền chuyên dụng nếu phù hợp.

## 11. Các chiến lược di chuyển workload

Có thể dùng mô hình 6R để phân loại hướng xử lý khi chuyển ứng dụng:

| Chiến lược | Ý nghĩa | Khi phù hợp |
|---|---|---|
| Rehost | Chuyển gần như nguyên trạng sang hạ tầng đích | Cần rời nền tảng nhanh, workload ít phụ thuộc |
| Replatform | Điều chỉnh runtime hoặc dịch vụ nền nhưng giữ phần lớn ứng dụng | Có thể thay database/cache/compute bằng dịch vụ tương đương |
| Refactor / Rearchitect | Thiết kế lại ứng dụng hoặc chia nhỏ thành phần | Lock-in cao hoặc cần tận dụng kiến trúc mới |
| Repurchase | Thay bằng sản phẩm/SaaS khác | Không cần tiếp tục tự vận hành phần mềm hiện tại |
| Retain | Giữ lại thành phần ở môi trường cũ | Chi phí chuyển lớn hoặc chưa có lựa chọn thay thế |
| Retire | Ngừng thành phần không còn cần thiết | Giảm phạm vi và chi phí migration |

Một migration có thể kết hợp nhiều chiến lược. Ví dụ, stateless API được rehost bằng container, database được replatform sang engine tương thích, còn workflow phụ thuộc dịch vụ độc quyền được refactor sau. Không cần di chuyển mọi thành phần cùng lúc nếu có thể xác định ranh giới và dependency rõ ràng.

## 12. Ví dụ thực tế: chuẩn bị chuyển API từ cloud A sang cloud B

Giả sử một hệ thống thương mại điện tử có API chạy trên Kubernetes, database quan hệ managed, object storage lưu hóa đơn và queue xử lý đơn hàng.

### 12.1. Đánh giá ban đầu

Nhóm kiểm kê:

- API container dùng OCI image và Kubernetes Deployment.
- Ingress phụ thuộc load balancer controller của cloud A.
- Pod dùng workload identity để đọc bucket và gửi message.
- Database dùng engine quan hệ nhưng có một số extension.
- File hóa đơn lưu trong object storage, event notification kích hoạt xử lý.
- Dashboard và alert dùng monitoring service riêng của cloud A.

Kết quả: compute tương đối dễ chuyển; ingress, identity, event notification, database extension và observability cần công việc chuyển đổi riêng.

### 12.2. Chuẩn bị môi trường đích

Nhóm tạo VPC, cluster, node pool, ingress/gateway, identity, database và bucket ở cloud B bằng IaC. Deployment manifest chung được tái sử dụng; provider-specific ingress, storage và identity được cấu hình bằng overlay.

Pipeline build cùng image digest, chạy integration test với database đích và xác minh quyền workload. Hệ thống logging/metrics được cấu hình để nhận telemetry trước khi cutover.

### 12.3. Đồng bộ dữ liệu và chuyển traffic

Database đích nhận snapshot ban đầu rồi theo dõi CDC. Object storage được đồng bộ theo batch và checksum. Queue được cấu hình bridge hoặc drain theo thứ tự đã thiết kế.

Trước cutover, nhóm xác nhận replication lag trong giới hạn RPO, kiểm tra row count và checksum, chạy smoke test trên môi trường đích. Sau khi chuyển endpoint, theo dõi latency, error rate, queue age và nghiệp vụ tạo đơn.

### 12.4. Rollback và kết thúc

Nếu đích gặp lỗi trước khi ghi dữ liệu mới, có thể chuyển traffic về cloud A tương đối đơn giản. Nếu cloud B đã nhận ghi mới, quay lại cloud A cần đồng bộ ngược hoặc một quy trình phục hồi dữ liệu; đổi DNS đơn thuần có thể gây mất hoặc phân nhánh dữ liệu.

Giữ môi trường nguồn ở chế độ sẵn sàng theo thời hạn đã thống nhất. Chỉ ngừng nguồn sau khi xác minh dữ liệu, traffic, backup, monitoring và quy trình khôi phục tại đích.

## 13. Kiểm thử portability định kỳ

Portability chỉ có giá trị thực tế khi đã được kiểm thử. Tài liệu kiến trúc hoặc tuyên bố "dùng container nên portable" chưa đủ.

Một bài kiểm thử có thể thực hiện theo các bước:

1. Chọn một workload đại diện và định nghĩa mục tiêu chuyển, ví dụ chạy ở cloud B trong 4 giờ.
2. Build image từ source sạch và xác minh digest.
3. Triển khai bằng IaC và manifest chung ở môi trường đích.
4. Cấp identity và secret theo cơ chế đích.
5. Khôi phục snapshot dữ liệu thử nghiệm và kiểm tra schema.
6. Chạy integration test, load test và fault injection.
7. Kiểm tra backup/restore, log, metrics, alert và quyền truy cập.
8. Đo thời gian, lỗi thủ công, chi phí và phần code/config phải thay đổi.
9. Thực hiện cutover thử và rollback theo runbook.
10. Cập nhật dependency register, sơ đồ kiến trúc và ước lượng chi phí thoát.

Các tiêu chí cần đo:

- Thời gian dựng hạ tầng và triển khai.
- Thời gian copy và đồng bộ dữ liệu.
- Thời gian cutover và rollback.
- Số thay đổi trong source code, IaC và cấu hình.
- Tỷ lệ test thành công và sai khác hiệu năng.
- RPO/RTO thực tế.
- Chi phí egress, tài nguyên chạy song song và nhân lực.
- Số thao tác thủ công hoặc quyền đặc biệt cần hỗ trợ.

## 14. Đánh đổi giữa portability và lợi ích cloud-native

Thiết kế portable có thể làm giảm khả năng tận dụng tính năng chuyên biệt. Một lớp trừu tượng quá rộng có thể hạn chế transaction, analytics, autoscaling hoặc khả năng quan sát mà dịch vụ native cung cấp.

| Quyết định | Lợi ích | Chi phí/đánh đổi |
|---|---|---|
| Dùng managed database native | Backup, patching, HA và tích hợp tốt | Khác biệt engine/API có thể gây lock-in |
| Dùng database tự quản lý trên VM/Kubernetes | Kiểm soát engine và cấu hình | Đội ngũ chịu trách nhiệm backup, upgrade, HA và phục hồi |
| Dùng Kubernetes làm lớp compute chung | Manifest và API workload quen thuộc | Vẫn phải vận hành cluster và xử lý khác biệt provider |
| Dùng queue interface chung | Business logic ít phụ thuộc SDK | Có thể không biểu diễn hết ordering, transaction hoặc delivery semantics |
| Dùng OpenTelemetry | Chuẩn hóa traces/metrics/logs | Backend, query, alert và retention vẫn có khác biệt |
| Multi-cloud active-active | Có thể tăng khả năng chịu lỗi và locality | Đồng bộ dữ liệu, split-brain, chi phí và vận hành phức tạp |

Đừng tối ưu portability cho mọi thành phần bằng nhau. Ưu tiên các thành phần có giá trị di chuyển cao, vòng đời thay đổi thường xuyên hoặc rủi ro lock-in lớn. Với dịch vụ native đem lại lợi ích đáng kể, có thể chấp nhận lock-in có chủ đích nếu đã có export, backup, tài liệu và exit plan.

## 15. Checklist thiết kế và đánh giá

- [ ] Đã xác định lý do cần portability và môi trường đích có thể là gì.
- [ ] Đã lập danh mục compute, runtime, data, identity, network, storage và operations dependency.
- [ ] Đã phân loại mức lock-in và ghi bằng chứng, chi phí thay thế cho từng thành phần.
- [ ] Image, artifact, source và dependency có version/digest để tái tạo.
- [ ] Cấu hình môi trường và secret được tách khỏi image.
- [ ] Provider-specific API được cô lập trong adapter hoặc module riêng.
- [ ] IaC có module chung, module provider và quy trình quản lý state rõ ràng.
- [ ] Đã kiểm tra database engine, extension, schema, backup, CDC và khả năng export/import.
- [ ] Đã kiểm tra object, volume, queue semantics và event integration.
- [ ] Identity, encryption key, certificate và policy có phương án ánh xạ sang môi trường đích.
- [ ] Network, DNS, CIDR, firewall, private endpoint và phí truyền dữ liệu đã được đánh giá.
- [ ] Đã đặt mục tiêu RPO/RTO và xác định thứ tự cutover.
- [ ] Đã có runbook rollback, kể cả trường hợp đích đã nhận dữ liệu ghi mới.
- [ ] Đã thực hiện portability test trên môi trường đích đại diện.
- [ ] Đã đo thời gian, chi phí, thay đổi kỹ thuật và thao tác thủ công.
- [ ] Đã quyết định rõ phần nào cần portable, phần nào chấp nhận lock-in có chủ đích.

Thiết kế khả năng di chuyển workload bắt đầu bằng việc hiểu đầy đủ dependency, dữ liệu và quy trình vận hành, sau đó chuẩn hóa những lớp mang lại lợi ích thực tế như artifact, runtime, cấu hình, IaC và telemetry. Đánh giá vendor lock-in cần dựa trên bằng chứng về thời gian, chi phí, rủi ro và khả năng thay thế. Khi có mục tiêu RPO/RTO, phương án chuyển dữ liệu, kiểm thử ở môi trường đích và runbook rollback, tổ chức có thể tận dụng dịch vụ cloud-native mà vẫn duy trì quyền chủ động trước các thay đổi về nhà cung cấp.
