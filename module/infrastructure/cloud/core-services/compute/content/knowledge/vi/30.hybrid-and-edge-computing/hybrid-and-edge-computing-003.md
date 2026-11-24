# Đóng gói workload để triển khai nhất quán ở nhiều môi trường

Một workload compute có thể phải chạy ở data center, cloud region, chi nhánh và edge site. Các môi trường này thường khác nhau về CPU architecture, hệ điều hành, network, storage, quyền truy cập, kết nối Internet và cách quản lý thiết bị. Nếu mỗi nơi được cài đặt thủ công theo một cách riêng, cùng một phiên bản ứng dụng có thể hoạt động khác nhau, khó cập nhật và khó khôi phục khi xảy ra lỗi.

Đóng gói workload giúp biến ứng dụng cùng runtime dependency thành một artifact có thể kiểm tra, phân phối và triển khai lặp lại. Artifact cần được tách khỏi cấu hình riêng của môi trường; quy trình triển khai cần mô tả rõ tài nguyên, network, storage, secret, health check và chính sách cập nhật. Mục tiêu là **cùng một bản phát hành đã xác minh có thể được triển khai theo các cấu hình môi trường đã kiểm soát**, đồng thời vẫn đáp ứng giới hạn riêng của cloud, on-premises và edge.

## 1. Vì sao cần đóng gói nhất quán?

Trong mô hình hybrid và edge, ứng dụng thường được triển khai ở nhiều vị trí:

- Cloud region để xử lý tải tập trung, dữ liệu lớn hoặc dịch vụ dùng chung.
- Data center/on-premises để đáp ứng yêu cầu dữ liệu, tích hợp hệ thống cũ hoặc độ trễ nội bộ.
- Edge site gần thiết bị, dây chuyền, cửa hàng hoặc người dùng để xử lý tại chỗ.
- Thiết bị gateway hoặc máy công nghiệp có tài nguyên hạn chế và kết nối không ổn định.

Mỗi nơi có thể có quy trình cài đặt, phiên bản runtime, biến môi trường, certificate, port và storage khác nhau. Nếu package không chuẩn hóa, một lỗi phổ biến là “chạy được ở cloud nhưng không chạy ở edge” do thiếu thư viện, khác kiến trúc CPU, cấu hình sai hoặc phụ thuộc dịch vụ không có ở site.

Đóng gói nhất quán mang lại:

- **Tính tái lập:** cùng artifact và cấu hình tương đương tạo ra môi trường chạy có thể dự đoán.
- **Khả năng truy vết:** biết chính xác source commit, dependency, image digest và phiên bản cấu hình nào đã triển khai.
- **Phân phối có kiểm soát:** artifact được kiểm tra, ký và đưa qua registry hoặc kho phân phối.
- **Cập nhật và rollback:** có thể phát hành theo phiên bản, rollout theo nhóm site và quay lại artifact trước đó.
- **Giảm drift:** hạn chế khác biệt do cài đặt thủ công hoặc sửa trực tiếp trên máy.
- **Bảo mật:** tách secret khỏi package, kiểm soát nguồn artifact và quyền triển khai.

Đóng gói không đồng nghĩa mọi môi trường phải dùng cấu hình giống hệt nhau. Binary hoặc image có thể giống nhau, trong khi số replica, endpoint, storage class, network route, resource limit và chính sách bảo mật cần khác theo môi trường.

## 2. Phân biệt artifact, cấu hình và trạng thái runtime

Một triển khai nhất quán nên tách ba nhóm:

| Nhóm | Thành phần | Cách quản lý |
|---|---|---|
| Artifact | Container image, VM image, binary, package, model hoặc static asset | Version hóa, checksum, ký, lưu registry/artifact repository |
| Configuration | Endpoint, feature flag, resource sizing, port, logging, region/site profile | Quản lý theo môi trường, review và version hóa |
| Runtime state | Database, queue offset, file nghiệp vụ, cache, checkpoint và dữ liệu người dùng | Lưu ở storage/service có vòng đời phù hợp; backup/replication riêng |

Không đóng gói dữ liệu runtime hoặc secret production vào image. Nếu image chứa cấu hình môi trường cụ thể, cùng artifact sẽ khó chuyển giữa staging, cloud và edge. Nếu state chỉ nằm trong writable layer của container, việc thay container có thể làm mất dữ liệu.

Một nguyên tắc quan trọng là artifact nên bất biến sau khi build. Khi cần thay đổi endpoint, secret hoặc resource profile, triển khai cấu hình mới hoặc tham số runtime, không sửa trực tiếp nội dung image đã phát hành.

## 3. Chọn định dạng package theo workload

Không phải mọi workload đều nên đóng gói bằng cùng một định dạng. Lựa chọn phụ thuộc cách ứng dụng chạy, yêu cầu OS, phần cứng và năng lực nền tảng tại nơi triển khai.

| Định dạng | Nội dung | Môi trường phù hợp | Điểm cần chú ý |
|---|---|---|---|
| OCI container image | Filesystem, runtime dependency, metadata và entrypoint | Kubernetes, container runtime trên VM, edge gateway | Kiến trúc CPU, base image, volume, network và runtime compatibility |
| VM image | OS, package hệ thống, agent và cấu hình nền | Cloud VM, hypervisor on-prem, môi trường cần OS riêng | Image format, boot mode, driver, machine identity và dung lượng |
| Native package | Binary, thư viện và metadata cài đặt như DEB/RPM/MSI | Server/edge host cần tích hợp OS hoặc service manager | Dependency OS, package signing và quy trình nâng cấp |
| Binary bundle | Executable và thư viện đi kèm | Thiết bị edge hoặc hệ thống tối giản | ABI, libc, CPU architecture, certificate và thư viện hệ thống |
| Helm chart/Kubernetes manifest | Mô tả workload và tài nguyên Kubernetes | Kubernetes trên cloud, data center hoặc edge | Không chứa image runtime; cần cấu hình theo cluster và phiên bản API |
| Model/data artifact | Model ML, rule, schema hoặc dữ liệu tĩnh được version hóa | AI inference, analytics và edge processing | Kích thước, checksum, accelerator compatibility và vòng đời dữ liệu |

Một ứng dụng có thể cần nhiều artifact phối hợp. Ví dụ, container image chứa API, Helm chart mô tả Deployment/Service, cấu hình site cung cấp endpoint, còn secret được cấp từ secret manager. Các thành phần phải có version và quan hệ tương thích rõ ràng.

## 4. Container image làm đơn vị phân phối ứng dụng

OCI image là lựa chọn phổ biến khi workload cần chạy trên nhiều container runtime. Image chứa filesystem và metadata để runtime biết command, user, environment mặc định và entrypoint.

Để image có thể triển khai trên nhiều môi trường:

- Chọn base image được duy trì và có hỗ trợ kiến trúc CPU mục tiêu.
- Đóng gói runtime dependency cần thiết, không phụ thuộc package cài thủ công trên host.
- Dùng `ENTRYPOINT`/`CMD` rõ ràng và chạy process chính ở foreground.
- Không ghi secret, IP site hoặc hostname production vào image.
- Ghi log ra stdout/stderr hoặc cơ chế log được chuẩn hóa.
- Đưa dữ liệu bền vững ra volume hoặc dịch vụ lưu trữ bên ngoài container.
- Dùng non-root user và quyền tối thiểu khi ứng dụng hỗ trợ.
- Pin dependency/base image và lưu image theo digest đã xác minh.

Ví dụ Dockerfile cho một API:

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --chown=10001:10001 app.jar /app/app.jar
USER 10001:10001
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=70"
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Đây là ví dụ rút gọn. Production nên pin base image theo digest đã phê duyệt, kiểm tra CA certificates/timezone/native dependency và đặt JVM/resource profile theo container limit. `EXPOSE` chỉ là metadata của image, không tự mở firewall hoặc publish port trên host.

Build image một lần trong pipeline, quét và ký artifact, sau đó promote cùng digest qua các môi trường. Không build lại một image khác cho từng site chỉ để thay endpoint hoặc secret.

## 5. Multi-platform image và khác biệt CPU architecture

Cloud region và edge device có thể dùng CPU khác nhau, ví dụ `linux/amd64` và `linux/arm64`. Một image tag có thể tham chiếu manifest index chứa nhiều image con theo platform. Runtime chọn image con phù hợp với host nếu manifest có entry tương ứng.

Ví dụ build multi-platform bằng Buildx:

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t registry.example.com/plant/edge-agent:2.3.0 \
  --push .
```

Lệnh trên yêu cầu builder và registry hỗ trợ multi-platform. Cần kiểm tra:

- Base image có manifest cho tất cả kiến trúc cần chạy.
- Binary native, JNI, Python wheel, Node native addon hoặc driver có bản tương thích.
- CPU feature set tối thiểu của thiết bị edge.
- Build emulation có thể làm chậm và không thay thế benchmark trên hardware thật.
- Image index trỏ đúng digest cho từng platform.

Java bytecode hoặc mã nguồn đa nền tảng không bảo đảm toàn bộ package tương thích. JNI, OpenSSL provider, agent, GPU runtime và native dependency vẫn có thể phụ thuộc kiến trúc.

Nếu một thiết bị không hỗ trợ image platform mong muốn, hãy tạo artifact riêng theo kiến trúc nhưng duy trì cùng version release, test suite và provenance. Không dùng một tag duy nhất để che giấu các binary không tương đương mà không có manifest rõ ràng.

## 6. Đóng gói VM image cho workload cần hệ điều hành riêng

Một số workload cần VM image thay vì container, chẳng hạn appliance mạng, phần mềm legacy, agent cần kernel module hoặc workload có yêu cầu OS đặc thù. VM image có thể chứa OS baseline, runtime, monitoring agent và package hệ thống.

Để image có thể dùng ở nhiều môi trường:

- Chuẩn hóa OS version, kernel, boot mode và partition layout.
- Cài guest tools/agent phù hợp với hypervisor đích.
- Không đóng cứng IP, hostname, machine ID hoặc certificate riêng của một máy.
- Dùng cloud-init, Ignition hoặc cơ chế provisioning tương đương để cấu hình lúc boot nếu nền tảng hỗ trợ.
- Xử lý SSH host key, machine identity và agent identity khi clone.
- Giữ dữ liệu nghiệp vụ ngoài image; image nên có thể thay thế.
- Ghi nhận image version, package inventory, checksum và build provenance.

VM image có thể cần chuyển đổi format hoặc điều chỉnh driver giữa hypervisor. Một image boot được ở cloud không tự động tương thích với hypervisor on-prem hoặc thiết bị edge. Cần test boot, network, storage, clock, console và recovery trên từng loại nền tảng.

## 7. Native package và system service cho edge host

Một edge device có thể không chạy Kubernetes hoặc container runtime. Trong trường hợp đó, package DEB/RPM/MSI hoặc binary bundle cùng service manager có thể phù hợp hơn.

Ví dụ systemd unit cho một agent chạy nền:

```ini
[Unit]
Description=Edge telemetry agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=edge-agent
Group=edge-agent
ExecStart=/opt/edge-agent/bin/agent --config /etc/edge-agent/config.yaml
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/edge-agent /var/log/edge-agent

[Install]
WantedBy=multi-user.target
```

Ví dụ cần điều chỉnh theo distribution và quyền thực tế. `network-online.target` không bảo đảm Internet hoặc dịch vụ cloud đã truy cập được; ứng dụng vẫn cần retry có backoff. `Restart=on-failure` không thay thế health monitoring hoặc cơ chế cập nhật an toàn.

Package nên có script cài đặt/uninstall tối giản, không xóa dữ liệu nghiệp vụ khi upgrade, xác minh chữ ký và quản lý dependency rõ ràng. Tránh để script post-install tự tải binary không kiểm tra từ Internet.

## 8. Tách cấu hình môi trường khỏi artifact

Cùng một image có thể cần cấu hình khác nhau ở cloud, on-prem và edge. Ví dụ:

| Thuộc tính | Cloud | On-premises | Edge site |
|---|---|---|---|
| API endpoint | Internal load balancer/service DNS | DNS nội bộ hoặc service VIP | Gateway/site-local endpoint hoặc cloud endpoint qua tunnel |
| Resource profile | Nhiều vCPU/RAM, autoscaling | Capacity cố định theo cluster | CPU/RAM hạn chế, giới hạn nhiệt/điện |
| Storage | Managed database/object storage | SAN/NAS/database nội bộ | Local buffer/cache, đồng bộ về trung tâm |
| Network | VPC/VNet, private endpoint | VLAN, firewall, proxy | WAN không ổn định, NAT, private APN hoặc tunnel |
| Identity | Cloud IAM/workload identity | Directory hoặc PKI nội bộ | Device identity/certificate riêng từng thiết bị |
| Update channel | CI/CD và rollout theo region | Change window nội bộ | Fleet rollout theo site, có thể trì hoãn khi offline |

Cấu hình nên có schema, default an toàn, validation và version. Ví dụ file cấu hình không nhạy cảm:

```yaml
service:
  name: edge-telemetry
  logLevel: INFO
  requestTimeout: 5s

runtime:
  maxWorkers: 4
  queueCapacity: 500

storage:
  localBufferPath: /var/lib/edge-agent/buffer
  maxBufferBytes: 1073741824

connectivity:
  upstream: https://telemetry.example.internal
  retry:
    initialDelay: 2s
    maxDelay: 2m
```

File trên chỉ minh họa cấu hình không bí mật. Endpoint và worker count là giá trị theo site; credential, private key và token phải được cấp riêng. Ứng dụng nên validate cấu hình trước khi nhận traffic và báo lỗi rõ nếu thiếu trường bắt buộc.

## 9. Configuration profile và schema version

Khi có nhiều site, không nên sao chép rồi sửa thủ công một file cấu hình lớn cho từng nơi. Có thể chia thành:

- **Base profile:** giá trị chung và mặc định an toàn.
- **Environment profile:** thông số cho cloud, staging, on-prem hoặc edge.
- **Site profile:** endpoint, timezone, device mapping và resource cap riêng từng site.
- **Secret reference:** tên/ID secret trong secret manager hoặc device keystore, không chứa secret trực tiếp.

Mỗi profile nên có schema version và quy tắc tương thích. Khi thêm trường mới, ưu tiên default có ý nghĩa để phiên bản cũ không bị hỏng. Khi xóa hoặc đổi ý nghĩa trường, cần lộ trình migration và kiểm tra mọi site đang dùng phiên bản nào.

Ví dụ layout repository:

```text
deployment/
  base/
    app-config.yaml
    resource-defaults.yaml
  environments/
    cloud-prod.yaml
    datacenter-prod.yaml
    edge-default.yaml
  sites/
    plant-001.yaml
    store-014.yaml
  schemas/
    app-config-v2.schema.json
  manifests/
    deployment.yaml
    service.yaml
```

Layout chỉ là gợi ý. Site-specific config cần được quản lý quyền truy cập; không lưu private key hoặc password trong Git repository dù repository là private.

## 10. Đóng gói manifest triển khai

Container image mô tả ứng dụng, còn manifest triển khai mô tả cách chạy ứng dụng trong môi trường đích. Với Kubernetes, manifest có thể khai báo Deployment, DaemonSet, StatefulSet, Job, Service, volume, resource request/limit, security context và probe.

Ví dụ Deployment dùng image theo digest:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: edge-telemetry
spec:
  replicas: 2
  selector:
    matchLabels:
      app: edge-telemetry
  template:
    metadata:
      labels:
        app: edge-telemetry
    spec:
      containers:
        - name: agent
          image: registry.example.com/edge/telemetry@sha256:REPLACE_WITH_VERIFIED_DIGEST
          env:
            - name: CONFIG_PATH
              value: /etc/edge-agent/config.yaml
          resources:
            requests:
              cpu: 250m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 512Mi
          volumeMounts:
            - name: config
              mountPath: /etc/edge-agent
              readOnly: true
            - name: state
              mountPath: /var/lib/edge-agent
      volumes:
        - name: config
          configMap:
            name: edge-telemetry-config
        - name: state
          persistentVolumeClaim:
            claimName: edge-telemetry-state
```

Digest trong ví dụ là placeholder, phải được thay bằng digest thật đã xác minh. Manifest cần điều chỉnh theo cluster: ở edge site nhỏ có thể chỉ có một replica; storage class và PVC có thể khác; security context, service account, network policy và probe cần bổ sung theo ứng dụng.

Không đưa secret trực tiếp vào manifest hoặc ConfigMap. Dùng Secret, external secret provider hoặc device keystore theo khả năng nền tảng. ConfigMap thường phù hợp với cấu hình không nhạy cảm và có thể được mount/read-only.

## 11. Helm, Kustomize và cấu hình theo môi trường

Helm chart hoặc Kustomize có thể giúp tái sử dụng manifest và tạo overlay theo môi trường.

- **Helm:** template manifest bằng values; phù hợp khi cần package có version, dependency và tham số triển khai.
- **Kustomize:** patch/overlay lên base manifest mà không yêu cầu template engine; hữu ích cho cấu hình theo site/cluster.
- **Plain manifest:** phù hợp workload nhỏ hoặc môi trường có ít biến thể, miễn là version và review được kiểm soát.

Ví dụ Kustomize layout:

```text
k8s/
  base/
    deployment.yaml
    service.yaml
    kustomization.yaml
  overlays/
    cloud-prod/
      kustomization.yaml
      replicas-patch.yaml
    datacenter-prod/
      kustomization.yaml
      storage-patch.yaml
    edge-small/
      kustomization.yaml
      resources-patch.yaml
```

Overlay nên chỉ chứa khác biệt cần thiết. Nếu một site có manifest hoàn toàn khác vì đã fork quá nhiều, cần xem lại abstraction và chuẩn hóa platform capability. Không nên tạo một template khổng lồ với hàng trăm cờ điều kiện khiến khó hiểu cấu hình cuối cùng.

Trước khi triển khai, render manifest cuối và kiểm tra diff. Người vận hành cần nhìn thấy rõ image digest, replica, resource limit, volume, port, service account và policy thực sự được áp dụng.

## 12. Đóng gói dependency và dịch vụ phụ thuộc

Workload có thể phụ thuộc database, message broker, DNS, identity provider, object storage, API bên ngoài hoặc thiết bị tại site. Package ứng dụng không thể tự bảo đảm các dependency đó tồn tại.

Tạo một dependency manifest mô tả:

- Tên service và phiên bản giao thức/API cần dùng.
- DNS name, port và hướng kết nối.
- Cơ chế xác thực và certificate trust.
- Yêu cầu latency, throughput và timeout.
- Dependency bắt buộc so với dependency tùy chọn.
- Hành vi khi dependency offline: retry, buffer, degrade hoặc fail fast.
- Data schema/version và chính sách tương thích.

Với edge, cần phân biệt dependency local và cloud. Ví dụ, edge agent có thể ghi vào local queue khi WAN mất, sau đó đồng bộ lên cloud khi kết nối phục hồi. Không để ứng dụng block vô hạn chờ dịch vụ cloud nếu hoạt động tại chỗ phải tiếp tục.

## 13. Đóng gói dữ liệu và state riêng với application release

Image và manifest không nên là nơi lưu dữ liệu nghiệp vụ. Cần xác định state nằm ở đâu:

- Database managed hoặc database on-prem.
- Persistent volume có backup/replication.
- Object storage cho file lớn và artifact.
- Local disk/SSD cho cache, spool hoặc offline buffer có giới hạn.
- Message queue hoặc event log cho công việc chưa xử lý.
- Model store cho ML model có version và checksum.

Khi update workload, state phải có compatibility plan. Ví dụ, phiên bản mới thêm cột database nhưng phiên bản cũ vẫn đang chạy ở một số edge site offline. Dùng expand-and-contract: thêm schema tương thích trước, rollout ứng dụng, đợi fleet cập nhật đủ, rồi mới xóa field cũ ở một release sau.

Local edge buffer cần quota, retention và chính sách khi đầy. Có thể đặt giới hạn dung lượng, ưu tiên loại event, backpressure producer và cảnh báo khi đồng bộ chậm. Không để log hoặc cache lấp đầy disk làm thiết bị mất khả năng khởi động.

## 14. Secret, certificate và device identity

Hybrid/edge có nhiều identity khác nhau: workload identity trong cloud, service account trong cluster, machine identity của VM và device identity cho từng edge gateway.

Nguyên tắc:

- Không bake secret vào container image, VM image hoặc package.
- Cấp credential khi deploy/boot qua secret manager, workload identity, TPM hoặc secure keystore nếu có.
- Mỗi device/site có identity riêng; tránh dùng một private key chung cho toàn fleet.
- Certificate có thời hạn, quy trình rotate và thu hồi.
- Phân quyền theo site, workload và loại hành động.
- Có cơ chế bootstrap identity ban đầu và xử lý thiết bị bị mất/thu hồi.
- Log không ghi private key, token hoặc toàn bộ secret response.

Edge device có thể offline trong thời gian dài nên certificate rotation cần có grace period và quy trình đồng bộ. Không đặt credential vĩnh viễn trong image để tránh thiết bị clone dùng chung danh tính.

## 15. Đóng gói cho môi trường không có Internet hoặc kết nối gián đoạn

Edge site có thể bị giới hạn Internet, dùng private WAN hoặc mất kết nối trong nhiều giờ/ngày. Package cần hỗ trợ phân phối và vận hành trong điều kiện này.

Chuẩn bị:

- OCI image archive hoặc registry mirror nội bộ nếu site không truy cập registry trung tâm.
- Native package và dependency bundle đã ký nếu cài trực tiếp trên host.
- Manifest, chart và cấu hình đã render cho site.
- SBOM, chữ ký, checksum và metadata release.
- Model/data artifact cần thiết cùng checksum/version.
- Runbook cài đặt, kiểm tra, rollback và phục hồi offline.
- Danh sách dependency cần có tại site và phương án cache/local fallback.

Ví dụ xuất và nạp image archive:

```bash
docker save registry.example.com/edge/telemetry:2.3.0 -o telemetry-2.3.0.tar
sha256sum telemetry-2.3.0.tar > telemetry-2.3.0.tar.sha256

# Tai edge site sau khi xac minh checksum va chu ky
sha256sum -c telemetry-2.3.0.tar.sha256
docker load -i telemetry-2.3.0.tar
```

Checksum chỉ phát hiện thay đổi nếu file checksum đến từ nguồn tin cậy. Kẻ tấn công có thể thay cả archive lẫn checksum nếu kênh phân phối không được xác thực. Cần ký artifact hoặc manifest release bằng khóa được bảo vệ và xác minh chữ ký tại site.

Nếu dùng container runtime khác Docker, chọn công cụ export/import tương ứng với OCI image. Archive cần có metadata version và kiến trúc; registry mirror thường dễ quản lý hơn khi site có kết nối nội bộ ổn định.

## 16. Release bundle cho một site

Một release bundle có thể gom những thành phần cần thiết để triển khai offline hoặc theo một đợt:

```text
release-2.3.0/
  release-manifest.json
  images/
    telemetry-linux-amd64.oci.tar
    telemetry-linux-arm64.oci.tar
  deployment/
    rendered-manifest.yaml
    site-config.yaml
  packages/
    edge-agent_2.3.0_arm64.deb
  models/
    detector-v7.onnx
  security/
    sbom.spdx.json
    provenance.json
    release-signature.sig
    checksums.txt
  docs/
    install.md
    rollback.md
```

Bundle là ví dụ cấu trúc, không phải định dạng chuẩn bắt buộc. `release-manifest` nên liệt kê artifact, version, digest, platform, dependency và yêu cầu runtime. Không đưa secret vào bundle; secret được cấp riêng tại site.

Một bundle cần có manifest có chữ ký để thiết bị xác minh toàn bộ file. Sau khi import, nên ghi nhận release ID, digest đã cài, site ID, thời điểm, kết quả health check và người/automation thực hiện.

## 17. Supply chain: SBOM, provenance và chữ ký

Một package có thể chạy ở nhiều nơi nên cần bằng chứng về nguồn gốc và thành phần.

- **SBOM:** danh sách package, thư viện và phiên bản nằm trong artifact.
- **Provenance:** thông tin về source, builder, pipeline, tham số và quy trình tạo artifact.
- **Signature:** bằng chứng artifact được ký bởi publisher/key được tin cậy.
- **Digest/checksum:** định danh nội dung bất biến và phát hiện thay đổi.
- **Vulnerability scan:** kiểm tra thành phần có lỗ hổng đã biết.

Quy trình nên tạo SBOM/provenance tại build, ký artifact, lưu cùng release metadata và xác minh trước deploy. Với edge offline, public key hoặc trust root cần được provision an toàn từ trước và có quy trình cập nhật/thu hồi.

Quét lỗ hổng không chứng minh package an toàn tuyệt đối. Cần đánh giá mức độ nghiêm trọng, khả năng khai thác, package có thực sự được dùng hay không và bản vá có tương thích với thiết bị không. Nếu chưa thể vá ngay, ghi nhận ngoại lệ, phạm vi thiết bị và biện pháp giảm thiểu.

## 18. Quy trình build một lần, triển khai nhiều môi trường

Một pipeline tham khảo:

1. Checkout source tại commit xác định.
2. Resolve dependency từ repository được kiểm soát và dùng lockfile.
3. Chạy unit/integration test và static analysis.
4. Build artifact cho các target platform cần hỗ trợ.
5. Tạo container image/VM image/package theo quy trình chuẩn.
6. Tạo SBOM, provenance, checksum và ký artifact.
7. Quét lỗ hổng và kiểm tra policy trước khi promote.
8. Đẩy artifact vào registry hoặc kho phân phối.
9. Tạo/render cấu hình theo môi trường và validate schema.
10. Deploy vào test/staging hoặc edge pilot; xác minh health, data path và hiệu năng.
11. Promote cùng digest/release ID sang các môi trường tiếp theo.
12. Ghi nhận trạng thái từng site và theo dõi drift.

Không build lại chỉ để đổi tên môi trường. Nếu build lại, artifact có thể khác dù source giống nhau do dependency trôi nổi, timestamp hoặc base image thay đổi. Nếu cần artifact riêng cho kiến trúc, tạo chúng trong cùng release và liên kết bằng manifest/version chung.

## 19. Triển khai cấu hình bằng Infrastructure as Code

Artifact ứng dụng và hạ tầng cần được version hóa riêng nhưng liên kết qua release. Infrastructure as Code (IaC) mô tả network, compute, storage, IAM, load balancer và các tài nguyên nền tảng để có thể review và tái tạo.

Ví dụ cách tổ chức:

```text
platform/
  modules/
    network/
    compute/
    storage/
    identity/
  environments/
    cloud-prod/
    datacenter-prod/
    edge-fleet/
applications/
  telemetry/
    image-version.txt
    manifests/
    config-schema/
```

IaC cần quản lý state, quyền backend, secret và drift. Không lưu state file có secret trong repository công khai. Với edge device không có cloud control plane, có thể dùng configuration management/agent và manifest mong muốn được ký để đồng bộ cấu hình.

Không cố ép mọi môi trường vào một module IaC duy nhất nếu API và capability khác nhau đáng kể. Có thể tái sử dụng module/contract chung và tạo adapter theo platform, miễn là đầu ra và chính sách được kiểm tra nhất quán.

## 20. Triển khai theo site và quản lý fleet

Một edge fleet có thể gồm hàng chục tới hàng nghìn site. Cập nhật đồng thời toàn bộ fleet tạo blast radius lớn; nên triển khai theo nhóm và kiểm tra kết quả từng đợt.

Các nhóm rollout có thể gồm:

- Lab/test devices.
- Pilot site đại diện cho phần cứng và network khác nhau.
- Small canary cohort.
- Region/site wave.
- Toàn bộ fleet sau khi đạt tiêu chí.

Mỗi site cần báo về:

- Site/device identity và platform version.
- Desired release và actual release digest.
- Trạng thái tải artifact, cài đặt và khởi động.
- Health/readiness, resource usage và disk capacity.
- Thời điểm cập nhật và lỗi gần nhất.
- Trạng thái kết nối cloud/control plane.

Fleet manager cần xử lý site offline, update bị gián đoạn, device thay thế và version lệch. Không coi “lệnh rollout đã gửi” là “thiết bị đã cập nhật thành công”. Cần xác nhận actual state từ từng site hoặc đánh dấu rõ thiết bị chưa báo trạng thái.

## 21. Cập nhật an toàn: canary, rolling và blue-green

Các chiến lược triển khai có trade-off khác nhau:

| Chiến lược | Cách làm | Ưu điểm | Rủi ro/điều kiện |
|---|---|---|---|
| Rolling update | Thay từng nhóm instance/container | Dùng tài nguyên hiệu quả, triển khai dần | Cần tương thích phiên bản đồng thời và capacity dư |
| Canary | Cập nhật một tỷ lệ nhỏ site/replica trước | Giới hạn blast radius và quan sát sớm | Cần metric/feedback đáng tin cậy và tiêu chí promote |
| Blue-green | Duy trì hai môi trường, chuyển traffic sang bản mới | Có thể rollback nhanh bằng chuyển traffic | Tốn capacity tạm thời và cần quản lý data/schema |
| Staged offline update | Phân phối bundle tới site khi có kết nối/cửa sổ bảo trì | Phù hợp edge bị giới hạn kết nối | Site có thể chậm cập nhật; cần expiry và trạng thái desired/actual |

Trước khi cập nhật, kiểm tra compatibility của API, schema, message và dữ liệu. Trong hybrid, phiên bản mới ở cloud có thể giao tiếp với phiên bản cũ ở edge trong nhiều ngày; protocol cần tương thích ngược trong cửa sổ rollout.

## 22. Rollback và tương thích dữ liệu

Rollback package thường là triển khai lại artifact trước đó. Nhưng rollback ứng dụng không tự khôi phục database, message hoặc dữ liệu local đã thay đổi.

Thiết kế rollback cần:

- Lưu digest và release metadata của phiên bản trước.
- Giữ package/image cũ trong registry hoặc cache site theo retention.
- Kiểm tra schema/API có tương thích khi ứng dụng quay lại không.
- Dùng expand-and-contract cho database migration.
- Có checkpoint và backup cho local state cần bảo toàn.
- Ngăn hai phiên bản cùng ghi dữ liệu không tương thích.
- Xác định site nào có thể rollback tự động và site nào cần can thiệp.
- Kiểm tra artifact cũ vẫn được hỗ trợ bảo mật và không chứa lỗ hổng nghiêm trọng đã biết.

Với edge offline, rollback có thể phải thực hiện tại chỗ bằng bundle đã cache. Cần giữ ít nhất một bản release trước phù hợp với storage/schema hiện tại và xác minh checksum trước khi cài lại.

## 23. Drift và xác minh trạng thái thực tế

Configuration drift xảy ra khi môi trường thực tế khác với cấu hình mong muốn đã version hóa. Nguyên nhân có thể là sửa tay trên host, thay đổi ngoài pipeline, update không hoàn tất hoặc site dùng profile cũ.

Biện pháp:

- Lưu desired configuration và release ID trong source of truth.
- Agent/cluster controller định kỳ báo actual version và config hash.
- So sánh desired/actual và phân loại khác biệt được phép/không được phép.
- Hạn chế sửa trực tiếp production; thay đổi khẩn cấp phải được ghi nhận và đưa ngược vào source of truth.
- Cảnh báo site không cập nhật hoặc config schema quá cũ.
- Có quy trình reconcile an toàn, tránh tự động ghi đè dữ liệu local hoặc thay đổi gây downtime.

Không phải mọi khác biệt đều là drift xấu. Một số giá trị như device calibration, network route hoặc capacity thực tế có thể được quản lý riêng. Phải xác định field nào được phép thay đổi tại site và field nào cần tuân theo cấu hình trung tâm.

## 24. Ví dụ: cùng một telemetry workload trên cloud, data center và edge

Một workload thu thập telemetry từ máy công nghiệp. Ở edge, agent đọc dữ liệu từ thiết bị, lưu buffer cục bộ khi WAN gián đoạn và gửi lên cloud khi có kết nối. Ở data center, một service xử lý dữ liệu từ các hệ thống nội bộ. Trên cloud, worker phân tích và lưu dữ liệu dài hạn.

Thiết kế package:

| Thành phần | Cloud | Data center | Edge |
|---|---|---|---|
| Application artifact | Cùng release image, platform phù hợp | Cùng release image hoặc package tương thích | Image ARM64/AMD64 hoặc native package theo thiết bị |
| Runtime | Kubernetes/container service | Kubernetes hoặc container runtime on-prem | Lightweight Kubernetes, container runtime hoặc systemd |
| Config | Cloud endpoint, autoscaling và managed storage | Endpoint nội bộ, storage nội bộ | Site ID, device mapping, local buffer, WAN retry |
| Identity | Workload identity/service account | PKI/identity nội bộ | Device certificate riêng từng gateway |
| Data state | Database/object storage | Database hoặc message broker nội bộ | Local spool/cache có quota và sync cursor |
| Update | CI/CD rolling/canary | Change window và staged rollout | Signed bundle, site cohort và offline rollback |

Quy trình phát hành:

1. Build image đa kiến trúc cho cloud và edge target.
2. Tạo SBOM, provenance, signature và release manifest.
3. Kiểm thử trên hardware edge đại diện và cluster cloud.
4. Tạo cấu hình riêng theo site, chỉ chứa giá trị không nhạy cảm.
5. Cấp device identity và secret riêng ngoài image.
6. Deploy cloud/data center trước hoặc theo thứ tự dependency đã xác định.
7. Rollout một nhóm edge pilot, xác nhận actual digest và telemetry flow.
8. Mở rộng theo site wave; thiết bị offline sẽ nhận update khi kết nối lại theo policy.
9. Theo dõi version drift, buffer utilization, sync lag và lỗi thiết bị.

Trong ví dụ này, cùng một logic ứng dụng được phát hành theo một release ID nhưng cấu hình, tài nguyên và phương thức cài đặt khác nhau theo môi trường. Điều đó giúp giữ tính nhất quán của phần mềm mà vẫn thích ứng với giới hạn tại từng site.

## 25. Kiểm thử package trước khi triển khai rộng

Kiểm thử cần xác nhận artifact chạy được trên đúng nền tảng và cấu hình dự kiến:

1. **Artifact integrity:** digest, signature và provenance hợp lệ.
2. **Platform compatibility:** CPU architecture, OS, kernel, runtime và driver phù hợp.
3. **Configuration validation:** schema, default, secret reference và endpoint đúng.
4. **Dependency test:** DNS, port, certificate, identity và service contract hoạt động.
5. **Resource test:** CPU, memory, disk, network và accelerator trong giới hạn.
6. **Offline test:** workload tiếp tục hành vi được phép khi WAN/cloud mất kết nối.
7. **Recovery test:** process restart, node reboot, disk full và power interruption theo phạm vi an toàn.
8. **Update test:** upgrade, interrupted update và rollback trên thiết bị đại diện.
9. **Security test:** user privilege, secret handling, image scan và network policy.
10. **Observability test:** log, metric, event và trạng thái version được gửi hoặc lưu cục bộ.

Không chỉ kiểm thử trên máy developer. Edge hardware có thể khác CPU feature, storage speed, nhiệt độ, nguồn điện và network. Cần có test matrix đại diện cho các nhóm phần cứng được hỗ trợ.

## 26. Những lỗi thường gặp

- **Build image riêng cho từng môi trường:** các artifact dần khác nhau và khó truy vết. Build một lần, inject cấu hình theo môi trường.
- **Nhúng secret vào image hoặc bundle:** credential bị sao chép tới mọi site. Cấp secret/device identity riêng.
- **Giả định cùng image chạy trên mọi CPU:** native dependency có thể không tương thích. Build và test multi-platform.
- **Đóng gói cấu hình site vào image:** image khó promote và rollback. Tách base/environment/site profile.
- **Không pin image digest:** tag có thể trỏ tới nội dung khác. Deploy artifact theo digest đã xác minh.
- **Chỉ kiểm thử ở cloud:** bỏ qua offline mode, disk hạn chế và hardware edge. Test trên thiết bị đại diện.
- **Cập nhật toàn bộ fleet cùng lúc:** lỗi release ảnh hưởng mọi site. Dùng pilot, canary và wave rollout.
- **Không lưu package cũ tại edge:** site mất kết nối không thể rollback. Cache release trước và kiểm tra retention.
- **Rollback app mà không xét schema/state:** phiên bản cũ không đọc được dữ liệu mới. Dùng schema compatibility và checkpoint.
- **Không xác minh actual state:** lệnh triển khai thành công nhưng thiết bị chưa cập nhật. Thu desired/actual digest và health report.
- **Để local buffer không giới hạn:** disk đầy khiến workload ngừng hoạt động. Đặt quota, retention và backpressure.
- **Dùng một credential chung cho toàn fleet:** một thiết bị bị lộ có thể ảnh hưởng toàn bộ site. Dùng identity riêng và quy trình revoke.

## 27. Checklist đóng gói và triển khai đa môi trường

**Artifact và build**

- [ ] Artifact có version/release ID, digest và nguồn build truy vết được.
- [ ] Base image/runtime/dependency được pin và có quy trình cập nhật.
- [ ] Đã xác minh CPU architecture, OS, kernel, driver và native dependency.
- [ ] Có SBOM, provenance, signature và vulnerability scan theo policy.
- [ ] Artifact không chứa secret, IP hoặc cấu hình riêng của site.

**Cấu hình và manifest**

- [ ] Có base profile, environment profile và site profile rõ ràng.
- [ ] Cấu hình có schema version, validation và default an toàn.
- [ ] Manifest cuối đã render/review; resource, volume, port, identity và policy đúng.
- [ ] Secret/certificate được cấp riêng qua secret manager, PKI hoặc device keystore.
- [ ] Dependency và hành vi khi mất kết nối được mô tả.

**Phân phối và rollout**

- [ ] Registry/repository hoặc offline bundle có xác minh chữ ký/checksum.
- [ ] Có cache/mirror phù hợp cho site không có Internet.
- [ ] Rollout theo pilot/canary/site wave và có tiêu chí promote.
- [ ] Có rollback package, schema compatibility và retention tại edge.
- [ ] Theo dõi desired/actual release, config hash và site health.

**Vận hành**

- [ ] Local state, buffer, checkpoint và log có quota/retention.
- [ ] Đã test WAN outage, reboot, disk pressure, interrupted update và recovery.
- [ ] Có log/metric/tracing và cơ chế báo trạng thái khi site kết nối lại.
- [ ] Có quy trình rotate/revoke device identity và certificate.
- [ ] Có owner, runbook và lịch cập nhật bảo mật cho từng loại nền tảng.

Đóng gói workload để triển khai nhất quán ở nhiều môi trường đòi hỏi tách artifact bất biến khỏi cấu hình và state, chọn định dạng package phù hợp, kiểm soát supply chain và chuẩn hóa quy trình rollout. Với hybrid và edge, cần bổ sung hỗ trợ nhiều kiến trúc CPU, phân phối offline, identity riêng cho thiết bị, cấu hình theo site và khả năng cập nhật/rollback khi mạng gián đoạn. Khi các thành phần này được version hóa, xác minh và quan sát xuyên suốt, cùng một release có thể vận hành có kiểm soát trên cloud, data center và edge mà vẫn đáp ứng điều kiện riêng của từng môi trường.
