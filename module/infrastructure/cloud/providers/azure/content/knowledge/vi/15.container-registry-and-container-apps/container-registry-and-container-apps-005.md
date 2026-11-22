# Phân phối image đa region và giới hạn truy cập Registry

Khi một hệ thống triển khai container ở nhiều Azure region, mỗi khu vực cần lấy đúng **container image** để khởi động hoặc cập nhật ứng dụng. Nếu registry chỉ đặt tại một region, việc pull image qua khoảng cách xa có thể tăng độ trễ và tạo phụ thuộc vào khu vực đó. Nếu registry lại được mở rộng quyền hoặc public network thiếu kiểm soát, một danh tính hoặc mạng không đáng tin có thể đọc image nội bộ, đẩy mã độc hoặc thay đổi tag đang dùng trong production.

**Azure Container Registry (ACR)** là dịch vụ quản lý kho lưu trữ container images và các artifact theo chuẩn OCI. Với **geo-replication** trên SKU được hỗ trợ, một registry có thể có bản sao ở nhiều region nhưng vẫn sử dụng **một tên registry và một login server**. Song song với phân phối image, cần thiết kế **Microsoft Entra ID/managed identity, quyền pull/push, mạng private, DNS, logging và quy trình phát hành theo digest** để bảo vệ chuỗi cung ứng phần mềm.

Bài thuộc chương **Container Registry và Container Apps** của module **CLOUD_PROVIDERS_AZURE**. Module học Microsoft Azure từ subscription, resource group, Entra ID tới mạng ảo, compute, lưu trữ, dữ liệu; đồng thời triển khai, giám sát, bảo vệ và kiểm soát chi phí ứng dụng. Bài này kết hợp **container delivery**, **mạng đa region**, **quyền truy cập registry** và **vận hành dự phòng**.

Sau khi học, bạn có thể:

- Giải thích repository, tag, digest, manifest và vai trò của ACR trong CI/CD.
- Thiết kế ACR **Premium geo-replication** để phục vụ workload nhiều region.
- Phân biệt image replication với triển khai ứng dụng, sao chép dữ liệu và disaster recovery.
- Chọn cách cấp quyền pull/push theo nguyên tắc **least privilege**, bao gồm RBAC và mô hình repository-level được hỗ trợ.
- Giới hạn đường mạng bằng **public firewall rules**, **Private Endpoint** và Private DNS.
- Triển khai image tới **Azure Container Apps** hoặc AKS với managed identity khi phù hợp.
- Xác minh replica, kiểm thử kéo image từ từng region và chẩn đoán lỗi 401/403/DNS/timeout.
- Lập runbook phát hành, khôi phục, xoay vòng credential và kiểm soát chi phí.

## 1. ACR lưu trữ những thành phần nào?

Container image được đóng gói thành các lớp dữ liệu và metadata mô tả cách container khởi động. Trong ACR, các thành phần chính:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Registry** | Kho lưu trữ được quản lý với login server riêng | acmeprod.azurecr.io |
| **Repository** | Tập image có cùng tên logic | orders/api |
| **Tag** | Nhãn dễ đọc trỏ tới một manifest | 1.8.4, release-20261120 |
| **Digest** | Định danh nội dung manifest theo hash | sha256:... |
| **Manifest** | Mô tả các layer, cấu hình và đôi khi index nhiều kiến trúc | OCI image manifest |
| **Artifact** | Đối tượng theo chuẩn được registry hỗ trợ | Container image, OCI artifact theo tính năng |

Một image được tham chiếu bằng tag:

~~~text
acmeprod.azurecr.io/orders/api:1.8.4
~~~~~~~~~~~~~~~~~~~ ~~~~~~~~~~ ~~~~~
     registry       repository  tag
~~~

Hoặc tham chiếu theo digest:

~~~text
acmeprod.azurecr.io/orders/api@sha256:<MANIFEST_DIGEST>
~~~

Tên trên là minh họa. **Tag có thể thay đổi** nếu registry cho phép ghi đè, còn **digest** xác định manifest cụ thể. Với rollout production, việc ghi rõ digest giúp các region triển khai **cùng một artifact** thay vì phụ thuộc tag có thể bị di chuyển giữa hai lần pull.

### Vì sao không dùng :latest làm định danh phát hành?

Giả sử pipeline A đẩy **orders/api:latest** lúc 10:00, rồi pipeline B đẩy cùng tag lúc 10:03. Container tại region A pull lúc 10:01 và region B pull lúc 10:04 có thể chạy hai phiên bản khác nhau. Với geo-replication bất đồng bộ, hành vi còn chịu ảnh hưởng thời điểm manifest/layer được sao chép tới mỗi replica.

Hãy dùng **tag bất biến theo release** (ví dụ phiên bản hoặc commit SHA), kiểm tra digest và pin digest khi yêu cầu tính lặp lại cao. Nếu có cơ chế khóa thao tác ghi trên tag/repository, dùng thêm để giảm ghi đè vô ý.

## 2. Vì sao cần image distribution đa region?

Một hệ thống SaaS có API ở Southeast Asia và East Asia. Bình thường người dùng được đưa tới region gần hoặc còn đủ khỏe. Mỗi region có thể scale-out container khi traffic tăng:

~~~text
                      CI/CD pipeline
                            |
                      Build + Scan
                            |
                     Push 1 image
                            |
                 Azure Container Registry
                 cùng tên login server
                    /             \
             Replica A         Replica B
           Southeast Asia       East Asia
                 |                 |
             Image pull         Image pull
                 |                 |
        Container Apps/AKS    Container Apps/AKS
            Region A             Region B
~~~

Nếu chỉ lưu image ở một region, workload B có thể phụ thuộc vào kết nối mạng tới nơi đặt registry để pull khi tạo pod/replica mới. Nếu region chính hoặc đường kết nối lỗi, việc **scale-out, restart, node replacement hoặc rollout** có thể gặp khó khăn.

**Geo-replication** giúp image có mặt gần workload hơn và giảm phụ thuộc vào một vị trí lưu trữ. Nhưng nó không thay đổi code của ứng dụng, không tự cấp quyền registry và **không nhân bản dữ liệu database**. Một kiến trúc chịu lỗi region phải chuẩn bị cả compute, ingress, database, secrets, network và các phụ thuộc khác.

### Phân phối image khác failover ứng dụng

| Thành phần | Ai chịu trách nhiệm? |
|---|---|
| Image và manifest hiện diện ở nhiều vùng | ACR geo-replication |
| Container đang chạy tại A/B | Container Apps, AKS hoặc nền tảng compute |
| Traffic người dùng chuyển A → B | Azure Front Door, Traffic Manager hoặc giải pháp ingress phù hợp |
| Dữ liệu ứng dụng được phục hồi | Database/storage replication, backup và runbook DR |
| Workload có quyền pull | Managed identity/RBAC, token hoặc cơ chế auth được hỗ trợ |
| Workload có đường mạng tới ACR | VNet, routing, DNS, Private Endpoint/firewall |

Một image đã được replicate **không đảm bảo** ứng dụng ở region B có thể phục vụ nghiệp vụ nếu database B chưa sẵn sàng.

## 3. Chọn SKU Registry và kiến trúc sao chép

ACR có các tier như **Basic, Standard, Premium**, khác nhau về công suất, giới hạn và tính năng. **Geo-replication là tính năng của ACR Premium** theo mô hình dịch vụ được hỗ trợ. Không kỳ vọng một Basic hoặc Standard registry tự nhân bản ở nhiều region chỉ vì workload dùng nhiều cluster.

| Tiêu chí | Basic/Standard | Premium |
|---|---|---|
| Registry riêng để lưu OCI/container images | Có | Có |
| Pull/push bằng danh tính được hỗ trợ | Có | Có |
| Geo-replication nhiều region | Không | Có |
| Private Link/Private Endpoint cho ACR | Không ở các tier thông thường | Có |
| Một số network firewall/enterprise features | Hạn chế theo SKU | Đầy đủ hơn theo khả năng hiện hành |
| Chi phí | Thấp hơn cho nhu cầu cơ bản | Cao hơn, thêm chi phí replicas và các dịch vụ liên quan |

**SKU hỗ trợ tính năng không có nghĩa feature hoạt động trong mọi region hoặc mọi cấu hình.** Trước khi chọn, xác nhận quota, supported regions, tính năng networking, private endpoints, giá và chính sách Azure Policy trong subscription.

### Geo-replication hoạt động như thế nào?

- Bạn tạo **một ACR Premium** ở region chính và thêm các **replication resources** ở những region được hỗ trợ.
- Image/manifest và dữ liệu registry được dịch vụ **sao chép bất đồng bộ** giữa các vùng theo cơ chế hỗ trợ.
- Client dùng **cùng login server**, ví dụ **acmeprod.azurecr.io**, thay vì tạo tên registry riêng cho mỗi replica.
- Dịch vụ có cơ chế định tuyến truy cập đến replica phù hợp dựa trên vị trí và khả năng phục vụ. Khi dùng Private Link hoặc chính sách mạng đặc thù, cần kiểm tra đường đi và DNS riêng.
- Các bản sao phục vụ pull tại những vùng đã sẵn sàng. Có thể cần thời gian để artifact vừa push xuất hiện ở tất cả replica.

ACR geo-replication có mô hình **active-active** ở cấp registry: một registry có nhiều replica phục vụ các thao tác theo khả năng dịch vụ. Điều này **không** phải cam kết đồng bộ tức thời giữa mọi vùng. Nếu nhiều pipeline cùng push/ghi đè một tag ở các vị trí khác nhau, có nguy cơ xung đột hoặc kết quả không như mong muốn. Dùng **một nguồn phát hành được kiểm soát**, tag bất biến và digest để tránh tranh chấp.

## 4. Chọn region sao chép

Việc chọn region phụ không đơn giản là chọn nơi cách xa region chính nhất:

1. **Workload locality:** container chạy ở đâu thì nên có khả năng pull image trong vùng hoặc vùng gần đó.
2. **Data residency/compliance:** image có thể chứa binary nội bộ, cấu hình nhúng hoặc các thành phần thuộc diện quản lý dữ liệu; xác nhận vùng được phép.
3. **Resiliency:** tránh phụ thuộc vào một vùng lỗi; cân nhắc khả năng ứng phó sự cố region.
4. **Khả dụng của SKU/feature:** ACR Premium, replica, networking và Private Link có được hỗ trợ ở vùng đó không?
5. **Mạng triển khai:** VM, AKS, Container Apps, build runners, private DNS, egress và proxy có kết nối được không?
6. **Chi phí:** replica Premium, traffic, private endpoints, logging và các chi phí liên quan.
7. **Vận hành:** ai có quyền cấu hình replica, cách đo tình trạng và điều kiện rollback?

Ví dụ hai region **southeastasia** và **eastasia** chỉ để minh họa cách thiết kế. Hãy kiểm tra chúng có thỏa điều kiện dịch vụ và chính sách tổ chức tại thời điểm triển khai, không xem đây là một cặp region dự phòng được bảo đảm cho mọi workload.

### Khi nào không cần geo-replication?

- Ứng dụng chỉ chạy trong một region, yêu cầu pull nhỏ, không có mục tiêu DR đa region.
- Ngân sách hạn chế và đã có chiến lược build/re-push hoặc registry dự phòng được kiểm chứng đáp ứng RTO.
- Các artifact lớn ít thay đổi; thời gian pull và rủi ro vùng đã được đánh giá là chấp nhận được.

Không nhất thiết mọi nhóm phát triển phải mua Premium. Đặt mục tiêu **availability, latency, recovery time và tổng chi phí**, rồi chọn giải pháp tương ứng.

## 5. Quản lý release bằng tag, digest và manifest

Một pipeline phát hành đáng tin cậy cần phân biệt:

~~~text
Source commit 6f2a...
      |
      v
CI: test + build + scan
      |
      v
Image: orders/api:1.8.4
      |
      v
Digest: sha256:<HASH>
      |
      +----> Region A: deploy chính digest
      |
      +----> Region B: deploy chính digest
~~~

**Tag** là điểm tham chiếu dễ đọc; **digest** là định danh nội dung. Một image multi-platform có thể có **OCI image index/manifest list** trỏ tới các manifest cho **linux/amd64** và **linux/arm64**. Nếu target cluster có node CPU architecture khác nhau, xác nhận image hỗ trợ platform cần thiết; geo-replication **không tự biến một image amd64 thành arm64**.

### Quy trình promotion đề xuất

1. Build image **một lần** từ commit đã xác định.
2. Chạy unit/integration tests và kiểm tra bảo mật theo pipeline.
3. Push image với **tag release duy nhất**, không tái sử dụng tag để ghi đè artifact khác.
4. Lấy/ghi **manifest digest** từ registry.
5. Chờ ACR replication đạt điều kiện sẵn sàng; kiểm tra pull thật từ các mạng/vùng mục tiêu.
6. Deploy staging bằng tag cố định hoặc digest; chạy smoke tests.
7. Promote sang production **cùng digest**, không rebuild riêng cho từng region.
8. Ghi lại commit, digest, registry, thời gian, người phê duyệt và từng vùng đã rollout.

Khi rollback, trỏ workload về **digest của bản tốt trước đó**; bảo đảm manifest/layers bản cũ chưa bị xóa theo retention policy và vẫn khả dụng ở các vùng cần phục vụ.

### Chống ghi đè tag

ACR hỗ trợ các cơ chế quản lý thuộc tính repository/image và quyền ghi theo khả năng dịch vụ. Ví dụ, sau khi release đã duyệt, có thể áp dụng policy hoặc thuộc tính **write-enabled=false** trên tag/manifest khi phù hợp. Tuy nhiên thao tác khóa phải được hiểu đúng phạm vi: không đồng nghĩa mọi principal đều mất khả năng tạo tag khác hoặc sửa repository theo mọi API.

Ưu tiên **immutable release naming + quyền push hẹp + audit**. Không dựa vào duy nhất một nút "khóa tag" để bảo vệ chuỗi cung ứng.

## 6. Mô hình truy cập Registry: danh tính, quyền và mạng

ACR có hai nhóm kiểm soát độc lập nhưng bổ sung cho nhau:

- **Authentication + authorization:** ai được login, pull, push, thay đổi repository, xóa artifact hoặc quản trị registry?
- **Network access:** client từ đâu có thể kết nối tới **login server và data endpoints** của registry?

~~~text
             Identity / Credentials
           Entra ID, managed identity,
           workload federation, token
                      |
                      v
       Authorization: pull/push/admin
                      |
                      v
       Network: public firewall rule
          hoặc Private Endpoint
                      |
                      v
             Azure Container Registry
                      |
                      v
           Manifest + layers / artifacts
~~~

**Có quyền AcrPull nhưng không có đường mạng thì vẫn pull thất bại. Có đường Private Endpoint nhưng không có quyền đọc repository thì vẫn bị từ chối.** Khi chẩn đoán, phải tách hai lớp này.

### Nhóm chủ thể thường gặp

| Chủ thể | Hành động cần thiết | Quyền thiết kế |
|---|---|---|
| CI build pipeline | Push release image | Chỉ repository/phạm vi được giao |
| Container Apps/AKS workload | Pull image khi tạo replica | Chỉ pull các repository cần dùng |
| Nhóm bảo mật | Xem log, scan, xử lý image policy | Read/scan theo sản phẩm hỗ trợ |
| Registry administrator | Cấu hình SKU, replicas, Private Endpoint, policies | Management plane có kiểm soát, audit |
| Nhà cung cấp/đối tác | Pull một nhóm image theo hợp đồng | Token hoặc role repository-scoped, thời hạn/quy trình thu hồi |

Không cấp quyền **push** cho workload chỉ cần chạy image. Một container nếu bị xâm nhập mà còn có quyền push có thể ảnh hưởng đến các deployment khác.

## 7. Microsoft Entra ID, RBAC và repository-scoped authorization

### RBAC ở cấp registry

Với registry sử dụng chế độ **Azure RBAC Registry Permissions** thông thường, các vai trò như **AcrPull** và **AcrPush** thường được dùng để cấp quyền data plane tại phạm vi registry:

- **AcrPull:** phục vụ yêu cầu pull/list metadata theo khả năng vai trò.
- **AcrPush:** phục vụ push và những thao tác ghi liên quan trong phạm vi được cấp.
- Một số vai trò khác xử lý xóa, quản trị và các kịch bản cụ thể.

Vai trò **Contributor/Owner** trên tài nguyên Azure (management plane) không tự động là một thiết kế **least privilege** cho nội dung registry. Ngược lại, người chỉ có quyền pull không cần quyền sửa network firewall, replicas hoặc SKU.

### Chế độ repository permissions có ABAC

Azure ACR có mô hình **RBAC Registry + ABAC Repository Permissions** cho các registry/cấu hình được hỗ trợ. Mô hình này hỗ trợ phân quyền ở mức repository thông qua role và điều kiện thuộc tính, với các vai trò như **Container Registry Repository Reader**, **Repository Writer** và **Repository Contributor** theo danh mục hiện hành.

**Quan trọng:** Không giả định có thể dùng **AcrPull/AcrPush** theo cách cũ cho một registry được tạo ở chế độ ABAC repository permissions. Các role và cách gán được hỗ trợ khác nhau theo **role assignment permissions mode** của registry; trước khi áp dụng, hãy kiểm tra mode và tài liệu dịch vụ.

| Mục tiêu | Hướng chọn |
|---|---|
| Workload chỉ pull toàn registry trên mô hình RBAC thông thường | AcrPull ở phạm vi phù hợp |
| CI push toàn registry trên mô hình RBAC thông thường | AcrPush theo nhu cầu, hạn chế rộng quyền |
| Workload chỉ pull **orders/api** trên mô hình ABAC | Repository Reader + điều kiện repository được hỗ trợ |
| CI chỉ push **orders/api** trên mô hình ABAC | Repository Writer/Contributor theo hoạt động thực tế |
| Cần liệt kê catalog/repositories trong mô hình ABAC | Kiểm tra vai trò/quyền **Catalog Lister** khi cần |

Không tạo điều kiện ABAC tùy đoán rồi kết luận đã cô lập repository. Khi triển khai thực tế, xác minh bằng **danh tính có quyền** và **danh tính không có quyền**, thử pull cả repository được phép và repository bị cấm.

### Repository-scoped tokens và scope maps

ACR hỗ trợ **repository-scoped tokens** với **scope maps** trong các kịch bản được dịch vụ hỗ trợ. Đây là cơ chế credential riêng của ACR, **khác** với Microsoft Entra ID managed identity. Nó có thể giúp cấp quyền một đối tác vào repository nhất định, ví dụ:

~~~text
Scope map:
  repository: partner/sdk
  actions: content/read, metadata/read

Token:
  quyền từ scope map
  credential được quản lý, xoay vòng và thu hồi
~~~

Token có secret/password riêng, cần đưa vào secret store an toàn, giới hạn vòng đời và không gửi qua chat/repository. Với workload Azure có thể dùng Entra ID và managed identity, ưu tiên cách không cần quản lý mật khẩu thủ công.

## 8. Managed identity cho Container Apps và AKS

### Azure Container Apps

Container Apps có thể dùng **system-assigned** hoặc **user-assigned managed identity** để xác thực với ACR trong các cấu hình được hỗ trợ. Quy trình logic:

1. Tạo registry và repository cần dùng.
2. Bật identity cho Container App hoặc gắn identity đã cấp.
3. Gán quyền pull theo đúng mode của ACR.
4. Cấu hình Container App dùng registry và identity tương ứng.
5. Đảm bảo Container Apps environment có đường mạng/DNS đến ACR.
6. Deploy image/tag hoặc digest, kiểm tra revision mới đã pull thành công.

Trong Azure CLI, một mẫu cấu hình registry của Container App khi identity đã tồn tại và được cấp quyền phù hợp:

~~~bash
az containerapp registry set \
  --resource-group "<APP_RESOURCE_GROUP>" \
  --name "<CONTAINER_APP_NAME>" \
  --server "<ACR_NAME>.azurecr.io" \
  --identity system
~~~

Đây là ví dụ cho system-assigned identity. Với user-assigned identity, sử dụng ID phù hợp theo CLI và cấu hình Container Apps được hỗ trợ. Lệnh này **không tự bảo đảm** danh tính đã được gán data-plane role hay mạng private hoạt động.

### Azure Kubernetes Service (AKS)

Với AKS, identity dùng để **kéo image cho node/kubelet** không nhất thiết là managed identity mà ứng dụng pod dùng để gọi các dịch vụ khác. Hãy xác định đúng **kubelet identity/service principal** được sử dụng cho image pull.

Trên ACR RBAC thông thường, lệnh AKS **--attach-acr** có thể tự động hóa một phần việc gán quyền pull theo khả năng hỗ trợ. **Đối với ACR ABAC repository permissions mode, cách attach này có hạn chế/không hỗ trợ việc cấp quyền theo mode mới**; cần gán role repository reader thích hợp thủ công và kiểm tra role catalog nếu kịch bản yêu cầu.

Không gán **AcrPush** cho kubelet identity để "khắc phục" lỗi pull. Một pod sản xuất thông thường chỉ cần pull image.

### CI/CD nên dùng định danh ngắn hạn

Pipeline có thể dùng Microsoft Entra ID service principal với **workload identity federation/OIDC** khi provider và tổ chức hỗ trợ. Cách này giảm nhu cầu lưu client secret dài hạn trong CI.

Nên tách:

- **Identity CI:** có quyền push/release, không có quyền tùy ý sửa firewall/geo-replica.
- **Identity workload:** chỉ pull.
- **Identity quản trị:** có quyền tạo replicas, Private Endpoint, thay đổi policy qua quy trình duyệt.

## 9. Vì sao không bật ACR admin user?

ACR có tùy chọn **admin user** tạo username/password phạm vi rộng, hữu ích trong một số lab hoặc tích hợp legacy. Nhưng đây là credential có rủi ro cao: khó quy trách nhiệm theo workload và nếu lộ có thể ảnh hưởng nhiều repository.

Với production:

- **Tắt admin user** nếu không có yêu cầu đặc biệt đã được phê duyệt.
- Dùng Entra ID, managed identity hoặc credential scope hẹp.
- Không lưu registry password trong Dockerfile, Kubernetes manifest thuần hoặc CI log.
- Có quy trình thu hồi, rotation và giám sát hoạt động push/pull bất thường.

Lệnh kiểm tra management configuration:

~~~bash
az acr show \
  --name "<ACR_NAME>" \
  --query "{name:name,sku:sku.name,adminUserEnabled:adminUserEnabled}" \
  --output json
~~~

Để tắt admin user trên registry bạn được quyền thay đổi:

~~~bash
az acr update \
  --name "<ACR_NAME>" \
  --admin-enabled false
~~~

Không chạy lệnh thay đổi trên registry dùng chung khi chưa kiểm tra hệ thống cũ có đang phụ thuộc vào admin credentials hay không.

## 10. Giới hạn truy cập qua public network

ACR có **public login endpoint** theo mặc định ở nhiều cấu hình. Dù image private, một public endpoint có thể nhận kết nối từ Internet trước khi kiểm tra authentication. Registry public **không đồng nghĩa repository cho anonymous pull**; nhưng giới hạn network giúp giảm bề mặt tiếp xúc.

Với SKU và tính năng được hỗ trợ, các hướng kiểm soát gồm:

1. **Selected networks/IP allowlist:** chỉ chấp nhận kết nối public từ các egress IP đáng tin cậy.
2. **Private Endpoint + public access disabled:** chỉ cho đường private đã cấu hình.
3. **Trusted services/network bypass** khi thực sự cần và được dịch vụ hỗ trợ, với đánh giá rủi ro riêng.

### Firewall rule theo IP

Ví dụ một self-hosted build runner có public egress IP cố định được tổ chức quản lý. Bạn có thể thêm network rule cho IP/cidr thực tế theo tính năng hỗ trợ của ACR Premium:

~~~bash
az acr network-rule add \
  --name "<ACR_NAME>" \
  --ip-address "<APPROVED_PUBLIC_EGRESS_IP_OR_CIDR>"
~~~

Sau khi chuẩn bị tất cả nguồn hợp lệ, cấu hình deny-by-default:

~~~bash
az acr update \
  --name "<ACR_NAME>" \
  --default-action Deny
~~~

**Không chạy theo thứ tự này trên registry production nếu chưa có đường quản trị và build runner dự phòng.** Thay đổi firewall có thể khiến CI/CD, container scale-out hoặc người vận hành tự khóa quyền truy cập data plane. Phải xác nhận chức năng/SKU, các nguồn thực tế đi qua NAT/proxy và cách khôi phục cấu hình.

Nếu pipeline chạy từ dịch vụ SaaS có IP egress động, việc allowlist một IP của laptop không giải quyết được. Cân nhắc self-hosted runner ở mạng được quản lý, Private Endpoint và mô hình CI phù hợp.

### Khi chọn allowlist theo IP cần biết gì?

- IP phải là **public egress IP** mà ACR nhìn thấy, không phải địa chỉ private 10.x của runner.
- Với NAT Gateway/firewall, traffic có thể dùng egress IP khác với IP VM.
- Quy tắc network không cấp quyền pull/push. Managed identity/RBAC vẫn cần.
- Việc ACR có geo-replication không đồng nghĩa bạn có thể bỏ quản trị network ở mọi region.
- "Allow trusted services" không phải một danh sách tùy ý do người dùng chọn; cần hiểu phạm vi bypass thực tế trước khi bật.

## 11. Private Endpoint và Private Link cho ACR

Với **Azure Private Link**, bạn tạo **Private Endpoint** trong một VNet/subnet để truy cập ACR qua địa chỉ IP private. Đây là lựa chọn phổ biến cho container workloads nội bộ và registry không muốn tiếp xúc qua public network.

~~~text
                   Azure Container Registry
                     Premium + replicas
                       /           \
             Region A replica    Region B replica
                     ^                 ^
                     |                 |
                 Private Link access / DNS
                     |                 |
           VNet A + Private EP   VNet B + Private EP
                     |                 |
                 AKS / ACA           AKS / ACA
                  Region A            Region B
~~~

Sơ đồ mô tả kiến trúc logic. Private Endpoint là **network interface trong subnet**, không phải một bản sao ACR và không tự tạo replica. Client vẫn cần xác thực hợp lệ với registry.

### Trình tự thiết kế an toàn

1. Xác nhận **ACR Premium**, region, feature support và mạng/container platform.
2. Xác định VNets/subnets nơi **AKS/Container Apps, build runners và công cụ quản trị** thực sự hoạt động.
3. Tạo Private Endpoint tới đúng registry theo quy trình mạng và quyền được phê duyệt.
4. Cấu hình Private DNS theo endpoint do Azure cung cấp; với ACR thường liên quan **privatelink.azurecr.io**.
5. Đảm bảo phân giải DNS và kết nối tới **registry login endpoint** **và data endpoints** dùng để pull layers.
6. Kiểm tra pull/push từ từng mạng nguồn đã được phê duyệt, bao gồm vùng dự phòng.
7. **Sau khi đường private hoạt động ổn định**, mới cân nhắc tắt public network access.
8. Lưu phương án rollback, kiểm tra DNS liên vùng và chạy DR drill.

### DNS là yếu tố dễ bị bỏ sót

ACR dùng endpoint đăng nhập và các **regional data endpoints** cho nội dung image. Với geo-replication, số endpoint cần phân giải có thể tăng theo vùng. Tên data endpoint có dạng liên quan đến:

~~~text
<REGISTRY_NAME>.azurecr.io
<REGISTRY_NAME>.<REGION>.data.azurecr.io
~~~

Khi dùng Private Link, DNS private records cho login server và các data endpoints theo cấu hình có thể được tạo/quản lý thông qua tích hợp Private DNS zone. Đừng tự suy diễn A record/IP tĩnh từ một ví dụ: hãy kiểm tra danh sách **DNS configuration** của Private Endpoint, Private DNS zone group và tài liệu ACR cho registry đa replica.

**Có thể login thành công nhưng pull layers vẫn timeout** nếu client chỉ phân giải đúng registry login server mà data endpoints không đi được. Đây là sự cố điển hình khi kết hợp geo-replication và Private Link.

### Multi-region networking và DNS

Nếu hai region có hai VNets không kết nối, mỗi nơi cần **đường private** phù hợp đến registry và hệ thống DNS tương ứng. Nếu dùng hub-spoke hoặc custom DNS resolver, xác minh private DNS zone được link/forward đúng, không chồng chéo record giữa các endpoint và không làm lệch truy cập khi một region gặp sự cố.

**Private Link không tự mã hóa lại image hoặc thay đổi quy tắc pull/push.** HTTPS/TLS vẫn được dùng cho kết nối theo dịch vụ; RBAC/identity vẫn là tầng bắt buộc.

## 12. Tắt public access phải có đường kiểm thử và rollback

Sau khi đã thiết lập Private Endpoint, bạn có thể xem xét cấu hình **publicNetworkAccess=Disabled**:

~~~bash
az acr update \
  --name "<ACR_NAME>" \
  --public-network-enabled false
~~~

**Đây là lệnh thay đổi chính sách có thể cắt đường truy cập registry. Không chạy chỉ để học nếu không có môi trường lab và quyền khôi phục.**

Khi tắt public access, xác nhận các đối tượng còn pull/push được:

- Container Apps environment/AKS kubelet trong region A.
- Workload dự phòng ở region B.
- CI runner cần push image mới.
- Công cụ kiểm tra bảo mật, scanner, webhook hoặc dịch vụ tích hợp theo khả năng hỗ trợ.
- Người vận hành có một đường kiểm tra và sửa cấu hình không phụ thuộc việc truy cập public data plane.

Một dịch vụ Azure được Microsoft vận hành **không mặc nhiên** truy cập được ACR private của bạn. Các tích hợp như ACR Tasks, cloud-hosted runners hoặc dịch vụ scanning có những điều kiện mạng/trusted-services/identity riêng. Cần kiểm thử từng tích hợp, không bật bypass rộng chỉ để xử lý nhanh một pipeline lỗi.

### Tình huống tự khóa CI

Trước thay đổi:

~~~text
Hosted CI Runner -- Internet --> ACR public endpoint --> Push thành công
~~~

Sau khi tắt public network:

~~~text
Hosted CI Runner -- Internet -X-> ACR
                                      ^
                                      |
                         Private Endpoint trong VNet
                                      ^
                                      |
                            Self-hosted Runner
~~~

Để CI tiếp tục push, có thể cần self-hosted runner trong mạng được phép hoặc giải pháp tích hợp khác **được dịch vụ hỗ trợ**. Thao tác tắt public network không tự di chuyển CI runner vào VNet.

## 13. Geo-replication và Private Endpoint kết hợp ra sao?

Đây là giao điểm quan trọng của bài học:

- **Geo-replication** làm dữ liệu registry có các replica khu vực.
- **Private Endpoint** cung cấp đường kết nối private từ VNet đến registry.
- **DNS** quyết định client tìm tới IP/endpoint nào.
- **Identity và roles** quyết định thao tác pull/push có được phép không.

Thực tế không nên diễn giải rằng **một Private Endpoint ở region A tự động đủ cho region B**. Dịch vụ có thể cần các endpoint và DNS records tương ứng với kiến trúc, nhất là khi hai workload dùng mạng riêng độc lập.

### Ma trận xác minh

| Kiểm thử | Region A | Region B |
|---|---|---|
| Registry login FQDN phân giải đúng đường mạng | Bắt buộc | Bắt buộc |
| Regional data endpoints truy cập được | Bắt buộc | Bắt buộc |
| Workload identity có quyền đọc repository | Bắt buộc | Bắt buộc |
| Kéo một image đã replicate thành công | Bắt buộc | Bắt buộc |
| Tạo instance/pod mới từ cùng digest | Bắt buộc | Bắt buộc |
| Pull khi region còn lại gặp sự cố | Diễn tập nếu được phê duyệt | Diễn tập nếu được phê duyệt |
| CI có đường push hợp lệ | Theo thiết kế | Theo thiết kế |

Chỉ khi kiểm thử **đường dữ liệu thực** mới có thể kết luận registry sẵn sàng cho nhu cầu failover. Một màn hình status replica xanh chưa đủ chứng minh network, IAM và runtime đều đúng.

## 14. Triển khai bằng Azure Portal

Các bước minh họa với registry Premium; giao diện có thể thay đổi theo phiên bản Portal:

1. Mở [Azure Portal](https://portal.azure.com), chọn subscription, resource group.
2. Tìm **Container registries**, tạo ACR hoặc mở registry Premium đã được giao.
3. Chọn **SKU Premium**, region chính và tên registry toàn cục duy nhất theo quy tắc ACR.
4. Đảm bảo **Admin user** ở trạng thái Disabled khi thiết kế cho production.
5. Vào **Replications / Geo-replications**, tạo replica tại region phụ được phê duyệt.
6. Kiểm tra provisioning/replication status và dung lượng.
7. Trong **Access control (IAM)**, cấp role pull/push đúng danh tính và **role assignment permissions mode**.
8. Trong **Networking**, cấu hình Private Endpoint hoặc public network rules theo thiết kế.
9. Với Private Endpoint, xác minh vùng DNS private, records login/data và client path.
10. Bật **Diagnostic settings** gửi logs/metrics tới nơi giám sát thích hợp.
11. Push/pull image mẫu bằng danh tính được cấp quyền, thử từ mỗi region.

**Đừng tắt public access ngay ở bước đầu** nếu CI runner, AKS hoặc Container Apps chưa được chuẩn bị đường private. Trình tự nên là **configure → test → restrict → retest**.

### Phạm vi quyền và các bước phê duyệt

Người có quyền sửa ACR Networking/Replications thường cần role quản trị tài nguyên phù hợp; người chỉ push image không nên được cấp luôn quyền đổi firewall. Dùng change management, Azure Policy, Activity Log và review thay đổi để ngăn sự cố do cấu hình sai.

## 15. Azure CLI: kiểm tra registry và tạo replica

Các lệnh mẫu dưới đây dành cho Azure CLI trong **Bash/Cloud Shell**. Đây là **nội dung học tập**, không phải hành động đã được thực hiện trên subscription của bạn. Chỉ chạy lệnh tạo/sửa khi có môi trường lab được phép và đã đánh giá chi phí Premium.

### Đăng nhập và chọn subscription

~~~bash
az login
az account list --output table
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --output table

RG="rg-acr-geo-lab"
LOCATION_A="southeastasia"
LOCATION_B="eastasia"
ACR="<GLOBALLY_UNIQUE_REGISTRY_NAME>"
~~~

**Bắt buộc thay** ACR bằng tên hợp lệ chưa được dùng; ACR name có quy tắc riêng, thường chỉ gồm chữ/số và có độ dài được dịch vụ hỗ trợ. Không lấy nguyên tên ví dụ cho production.

### Tạo resource group và ACR Premium

~~~bash
az group create \
  --name "$RG" \
  --location "$LOCATION_A" \
  --tags environment=learning purpose=acr-georeplication

az acr create \
  --resource-group "$RG" \
  --name "$ACR" \
  --location "$LOCATION_A" \
  --sku Premium \
  --admin-enabled false
~~~

Đây là registry Premium **có thể bắt đầu phát sinh chi phí** ngay khi tạo. Ví dụ chưa tự khóa network để tránh khiến người học mất quyền thao tác trong lab; **không phải cấu hình bảo mật đầy đủ cho production**.

### Tạo replica ở region thứ hai

~~~bash
az acr replication create \
  --resource-group "$RG" \
  --registry "$ACR" \
  --location "$LOCATION_B"
~~~

Kết quả cần được kiểm tra; việc gọi lệnh thành công không có nghĩa mọi image được replicate tức thời.

### Xem registry, replicas và network settings

~~~bash
az acr show \
  --name "$ACR" \
  --query "{name:name,sku:sku.name,loginServer:loginServer,adminUserEnabled:adminUserEnabled,publicNetworkAccess:publicNetworkAccess}" \
  --output json

az acr replication list \
  --resource-group "$RG" \
  --registry "$ACR" \
  --query "[].{name:name,region:location,provisioningState:provisioningState}" \
  --output table

az acr network-rule list \
  --name "$ACR" \
  --output json
~~~

Các lệnh **show/list** cho biết cấu hình, **không tự xác nhận một client ở mỗi region đã pull thành công**. Khi cần chứng minh khả năng sử dụng, phải kiểm thử từ mạng và identity thực tế.

### Nếu registry không hỗ trợ lệnh hoặc region

Kiểm tra phiên bản Azure CLI, hỗ trợ lệnh **az acr replication --help**, SKU, region và Azure Policy. Không tạo replica khác chỉ vì bị lỗi quyền hoặc quota; xử lý nguyên nhân trước.

## 16. Demo phân phối image: build một lần, push một lần

Giả sử nhóm phát triển đã có một project container với **Dockerfile** và đã kiểm thử image. Có thể build và push bằng Docker CLI trong **môi trường được phép truy cập ACR**:

~~~bash
REPO="orders/api"
TAG="1.8.4"
LOGIN_SERVER="$ACR.azurecr.io"

az acr login --name "$ACR"

docker build -t "$LOGIN_SERVER/$REPO:$TAG" .
docker push "$LOGIN_SERVER/$REPO:$TAG"
~~~

**Yêu cầu:** máy chạy lệnh đã có Docker engine, đủ quyền registry, đường mạng tới login/data endpoints và code/Dockerfile hợp lệ. Đăng nhập ACR bằng Entra ID khi có thể thay vì bật admin user.

Kiểm tra repository/image:

~~~bash
az acr repository list \
  --name "$ACR" \
  --output table

az acr repository show-tags \
  --name "$ACR" \
  --repository "$REPO" \
  --output table

az acr repository show \
  --name "$ACR" \
  --image "$REPO:$TAG" \
  --output json
~~~

Lưu manifest digest được trả về khi push hoặc qua metadata từ registry, rồi dùng đúng digest cho workload deployment theo platform hỗ trợ:

~~~text
<ACR_NAME>.azurecr.io/orders/api@sha256:<DIGEST>
~~~

**Không lấy một digest bất kỳ trong ví dụ** rồi coi đó là image thật. Digest cần xác minh từ registry của release đã được build, đặc biệt với image multi-platform.

### Kiểm thử replication ở từng region

1. Xác nhận registry có replica tại A/B và provisioning health phù hợp.
2. Dùng **runner/VM lab ở region A** có quyền pull và mạng đúng để kéo image theo digest.
3. Dùng **runner/VM lab ở region B** với cùng điều kiện để kéo **chính digest ấy**.
4. Kiểm tra tag/digest, nền tảng CPU và khởi động container hoặc triển khai workload thử nghiệm.
5. Nếu pull ở B chưa có manifest, xem trạng thái đồng bộ và chờ theo cơ chế bất đồng bộ; không tự push lại cùng tag ở B để "ép" đồng bộ.
6. Ghi lại thời điểm push, lúc replica sẵn sàng và latency pull để đánh giá nhu cầu vận hành.

Việc dùng máy thử ở hai vùng có thể phát sinh phí compute, disk, egress. Có thể thực hành **trên giấy** nếu không có sandbox; không yêu cầu tạo VM chỉ để làm bài.

### Khi cần test không có Docker daemon

Một số quy trình dùng **az acr import** từ nguồn registry được phép, hoặc **az acr build** để build phía dịch vụ. Tuy nhiên, các thao tác này có điều kiện mạng/quyền riêng, đặc biệt khi registry bị khóa Private Link. Không coi import/build trên dịch vụ cloud là cách vượt firewall mặc định của ACR.

## 17. Pin digest và rollout đa region

Một hệ thống có hai Container Apps environments hoặc hai AKS clusters. Sau khi image đã có mặt ở A/B:

~~~text
CI push orders/api:1.8.4 (digest D)
                   |
                   v
             ACR geo-replication
              /              \
         Replica A          Replica B
              |                 |
         Stage region A     Stage region B
              |                 |
         Smoke tests        Smoke tests
              \                 /
               \               /
               Production rollout
                cùng digest D
~~~

Với **Azure Container Apps**, revision có thể giữ phiên bản image/config và hỗ trợ điều khiển traffic theo khả năng platform. Với **AKS**, Deployment/Helm/GitOps có thể tham chiếu image digest. Phương thức rollout khác nhau nhưng nguyên tắc giống nhau: **một artifact đã xác minh, triển khai tuần tự hoặc theo canary**.

### Vì sao warm deployment cần thiết?

Trong sự cố region, một ứng dụng đã có replicas đang chạy tại B có thể tiếp tục phục vụ dù registry có trục trặc trong ngắn hạn. Nhưng khi B cần scale-out hoặc node được thay, hệ thống có thể phải pull image. Vì vậy:

- Dự phòng compute nên được kiểm thử với image hiện hành **trước** khi xảy ra sự cố.
- Đừng giả định mọi node đều có cached image đúng digest; cache có thể bị dọn.
- Đảm bảo registry/Private Endpoint/DNS tại B vẫn phục vụ trong kịch bản failover.
- Giữ artifact release trước đó đủ lâu để rollback.

Geo-replication cải thiện **khả năng phân phối artifact**, không cam kết RTO/RPO cho toàn ứng dụng.

## 18. Xác nhận quyền bằng hai danh tính đối chứng

Để chứng minh least privilege, không chỉ test bằng tài khoản Owner:

| Identity thử nghiệm | Thao tác | Kết quả mong đợi |
|---|---|---|
| CI writer của repository **orders/api** | Push image release tới orders/api | Được phép theo vai trò đã cấp |
| CI writer | Sửa ACR firewall hoặc tạo replica | Bị từ chối nếu không có quyền quản trị |
| Container workload reader | Pull orders/api | Thành công |
| Container workload reader | Push orders/api | Bị từ chối |
| Workload reader giới hạn repository | Pull repository khác không được cấp | Bị từ chối trong mô hình ABAC/scope phù hợp |
| Identity chưa cấp quyền | Pull private image | Bị từ chối |
| Identity có quyền nhưng ngoài mạng cho phép | Pull image | Không thành công vì network restriction |

Kết quả mong đợi phải đối chiếu với **registry mode** và **cấu hình thật**. Nếu chỉ dùng RBAC cấp AcrPull ở toàn registry, không kỳ vọng tự nhiên có repository isolation chỉ vì tên repository khác nhau.

### Đọc 401 và 403 sao cho đúng

- **401 Unauthorized:** có thể chưa authenticate, token sai/hết hạn hoặc registry yêu cầu login; cần kiểm tra auth challenge/credential.
- **403 Forbidden:** có thể auth hợp lệ nhưng thiếu quyền, hoặc bị chính sách/đường truy cập mạng từ chối tùy API/tình huống.
- **Timeout/DNS/connection refused:** thường nghiêng về mạng, DNS, firewall/Private Endpoint, proxy hoặc dịch vụ không reachable.
- **manifest unknown:** image/tag/digest không tồn tại, chưa kịp replicate hoặc tham chiếu sai.

Không suy luận chỉ từ một mã HTTP rằng nguyên nhân chắc chắn là RBAC. Xem thông báo chi tiết, identity đang dùng, điều kiện mạng và logs để phân biệt.

## 19. Chẩn đoán với Azure CLI, DNS và registry diagnostics

### Kiểm tra login/pull

Từ một máy có Docker hoặc công cụ registry phù hợp:

~~~bash
az acr login --name "<ACR_NAME>"

docker pull "<ACR_NAME>.azurecr.io/orders/api:1.8.4"
~~~

Lệnh **az acr login** thông thường sử dụng Docker CLI/daemon để lưu credential; có lựa chọn **--expose-token** trong các kịch bản không có Docker daemon, nhưng output chứa access token ngắn hạn cần bảo vệ. Không in token vào log hoặc chia sẻ dưới dạng ảnh chụp màn hình.

Kiểm tra DNS:

~~~bash
nslookup <ACR_NAME>.azurecr.io
~~~

Kiểm tra từ **đúng VNet/runner ở region A và B**, không chỉ từ máy laptop của người quản trị. Trong Private Link, kết quả mong đợi là DNS dẫn tới đường private theo thiết kế; việc thấy một public IP khi kỳ vọng private có thể cho thấy resolver/zone link không đúng.

### Công cụ health check

ACR CLI có công cụ **check-health** cho registry và môi trường, tùy tham số và phiên bản:

~~~bash
az acr check-health \
  --name "<ACR_NAME>" \
  --yes
~~~

Xem **az acr check-health --help** để xác nhận điều kiện, các kiểm tra local/Docker và tác động. Công cụ này hỗ trợ chẩn đoán nhưng **không thay** kiểm thử pull từ workload và network thật.

### Logs và giám sát

Trong ACR, cấu hình **Diagnostic settings** để gửi log và metric hỗ trợ tới Azure Monitor / Log Analytics theo chính sách tổ chức. Tùy kiểu logging, có thể có thông tin **login events**, **repository events**, authentication/operations và các metric của registry.

Cần phân biệt:

- **Management plane Activity Log:** tạo/xóa replica, sửa firewall, thay đổi SKU/IAM/policy.
- **Data plane registry events:** push/pull, thao tác repository và lỗi liên quan, tùy log category được hỗ trợ.
- **Workload platform logs:** Container Apps revision, AKS pod events (như ImagePullBackOff/ErrImagePull), CI pipeline logs.
- **Network/DNS logs:** firewall, DNS resolver, VNet và Private Endpoint khi được bật.

Tên bảng Log Analytics có thể thay đổi tùy **resource-specific** hay **AzureDiagnostics**, và theo tính năng dịch vụ. Không dùng một truy vấn KQL giả định bảng chắc chắn tồn tại; kiểm tra Diagnostic settings và schema workspace trước.

### Ví dụ quá trình điều tra ImagePullBackOff

1. Ghi exact image reference, tag/digest, cluster/region, timestamp.
2. Đọc lỗi pod/revision: **401, 403, manifest unknown, DNS timeout hay no matching manifest**?
3. Xác định kubelet/Container App identity và registry permissions mode.
4. Kiểm tra Private DNS/login/data endpoints từ workload subnet.
5. Xem replica status và kiểm thử pull cùng digest từ một client được cấp quyền trong region.
6. Kiểm tra pipeline vừa thay tag, xóa manifest hoặc chạy cleanup không.
7. Chỉ thay đổi một nguyên nhân cụ thể, rồi retry có kiểm soát.

Không lập tức bật ACR admin user hoặc mở public access toàn Internet để "chữa" ImagePullBackOff trên production.

## 20. Tình huống lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra/khắc phục |
|---|---|---|
| ACR Basic không có mục Replications | SKU không hỗ trợ geo-replication | Xem yêu cầu Premium, giá và migration plan |
| Replica tạo thành công nhưng image mới chưa pull được ở B | Replication bất đồng bộ, lag hoặc đường data endpoint | Kiểm tra replica health, đợi đồng bộ, thử cùng digest |
| Registry login được, pull layers timeout | DNS/Private Endpoint cho data endpoints thiếu | Kiểm tra regional data endpoints và private DNS records |
| Container Apps lỗi kéo image | Managed identity chưa được cấp quyền, registry config/port/network sai | Kiểm tra ACA identity, ACR role, VNet/DNS và revision logs |
| AKS ImagePullBackOff với ACR ABAC | Attach-acr kiểu cũ không cấp repository role phù hợp | Gán repo reader có điều kiện theo mode, kiểm tra kubelet identity |
| CI pipeline đẩy được trước khi tắt public, sau đó 403/timeout | Hosted runner không ở mạng private | Dùng đường CI được hỗ trợ, chuẩn bị private runner hoặc cấu hình thích hợp |
| Tag giống nhau nhưng A/B chạy binary khác | Tag đã bị ghi đè, release race hoặc image chưa thống nhất | Kiểm tra digest, khóa promotion và rollback |
| Pull trả **manifest unknown** | Repo/tag sai, artifact đã xóa hoặc chưa replicate | Xem repository metadata, tag history/retention, replica status |
| Pull trả **no matching manifest for linux/arm64** | Image không có manifest cho CPU architecture | Build multi-platform phù hợp; không đổ lỗi cho region |
| CI có AcrPush nhưng không thể đổi firewall | Data-plane role không bao gồm management plane | Cấp riêng quyền quản trị qua quy trình IAM |
| Runner có AcrPush mà push vẫn timeout | Không có đường mạng tới ACR | Kiểm tra DNS, firewall allowlist, Private Endpoint |
| Private Endpoint kết nối được từ A nhưng B không được | VNets/DNS/endpoint topology của B chưa được chuẩn bị | Kiểm tra zone links, resolver, data endpoints và routing |
| Người dùng ngoài tổ chức pull được image nội bộ | Quyền/token/public config rộng, credential lộ | Thu hồi token, kiểm tra audit, review permissions/network |
| Sau khi khóa mạng, scanner/automation ngừng hoạt động | Tích hợp không hỗ trợ private hoặc bypass chưa được thiết kế | Đánh giá tính năng, private runner hoặc đường truy cập chính thức |
| Chi phí ACR tăng sau thêm replica | Premium geo-replication, storage, transfer và monitoring | Kiểm tra Cost Management, nhu cầu từng replica |

**Nguyên tắc:** một lỗi pull có thể xuất phát từ **identity**, **network**, **image reference**, **replication timing** hoặc **runtime platform**. Không sửa đồng loạt nhiều lớp khiến nguyên nhân gốc khó xác định.

## 21. Xử lý tình huống ACR region gặp sự cố

Giả sử ứng dụng hoạt động ở hai region và ACR có replica A/B. Region A mất khả dụng khi CI vừa phát hành phiên bản mới.

### Tác động cần phân tích

- Các container đang chạy ở B có tiếp tục phục vụ không?
- B có đủ compute/database/network để nhận thêm traffic không?
- **Digest release mới nhất** đã replicate tới B chưa?
- Registry login/data endpoints, DNS private và identity của B có còn dùng được không?
- CI có nên tiếp tục push hay **đóng băng release** trong lúc dữ liệu registry chưa xác nhận nhất quán?
- Có cần rollback ứng dụng về digest đã được kiểm thử và hiện diện ở B không?

### Runbook gợi ý

1. **Đóng băng những thay đổi image không cấp bách** để tránh race với replication.
2. Kiểm tra registry/replica health, image digests và logs từ workload B.
3. Xác minh pull bản release đã biết tốt ở B; tránh tự push lại tag mutable bằng một pipeline khác.
4. Đánh giá điều kiện failover ứng dụng, database và ingress **độc lập với registry**.
5. Nếu image mới chưa an toàn/không sẵn sàng ở B, dùng digest ổn định đã được kiểm chứng.
6. Chuyển traffic qua cơ chế ứng dụng được thiết kế (ví dụ Front Door) theo runbook.
7. Giám sát scale-out, ImagePullBackOff, latency, HTTP errors và giao dịch nghiệp vụ.
8. Khi A phục hồi, xác minh replica đồng bộ, policy vẫn đúng và không có image bất thường trước khi mở lại pipeline.

Một **replica healthy** không đồng nghĩa ứng dụng đã đạt RTO: cần kiểm tra cả khả năng khởi chạy container, kết nối dữ liệu và xử lý request. **Geo-replication của ACR không thay cho backup/dự phòng database hoặc logic ứng dụng**.

## 22. Bảo vệ chuỗi cung ứng image

Network/identity là cần thiết nhưng chưa đủ. Một identity có quyền push bị lộ có thể đưa image độc hại vào registry private.

Các kiểm soát nên bổ sung:

- **Build provenance:** ghi source commit, pipeline/job ID, người duyệt, digest.
- **Dependency/image scanning:** dùng công cụ scanner hoặc Microsoft Defender for Cloud/Containers theo gói và tính năng hỗ trợ.
- **SBOM:** lưu danh mục thành phần phần mềm theo quy trình tổ chức.
- **Image signing/verification:** cân nhắc chữ ký OCI và policy xác minh ở pipeline/admission theo công cụ tương thích.
- **Tag immutability/promotion discipline:** không tái sử dụng tag production cho nội dung khác.
- **Principle of least privilege:** CI push đúng repo, workload chỉ pull; không dùng admin account.
- **Secret hygiene:** không bake access token, key hay mật khẩu vào image layer/Dockerfile.
- **Artifact retention:** giữ đủ các digest cần rollback, có chính sách cleanup tránh xóa bản đang chạy.
- **Audit + alerting:** cảnh báo push bất thường, thay đổi firewall/IAM, xóa repository và lỗi pull tăng.

**Registry không tự động chứng thực rằng một image an toàn** chỉ vì nó nằm trong ACR Premium. Một image vẫn cần được đánh giá từ source đến build, deploy và runtime.

## 23. Chi phí và các quyết định vận hành

Geo-replication và Private Link giúp nâng availability/security, nhưng tăng chi phí:

| Thành phần | Nhóm chi phí cần xem |
|---|---|
| **ACR Premium** | Giá theo tier/capacity và mức sử dụng được dịch vụ tính phí |
| **Geo replicas** | Chi phí duy trì mỗi khu vực sao chép theo giá hiện hành |
| **Registry storage** | Dung lượng layers/manifest/artifact và chính sách retention |
| **Data transfer** | Traffic pull/push qua mạng, đặc biệt liên vùng/Internet nếu áp dụng |
| **Private Endpoints** | Tài nguyên private link, lưu lượng theo mô hình tính phí |
| **Private DNS/Resolver** | Zone, query/forwarder và resolver theo mức sử dụng |
| **Compute/CI runners** | AKS/Container Apps, VM runner và network egress |
| **Diagnostic logs** | Ingestion, retention, analytics và alerting |
| **Security scanning** | Gói bảo mật hoặc công cụ scanning phù hợp |

Không phát biểu một mức giá cố định không kèm region, tier, số replicas và workload. Dùng **Azure Pricing Calculator** và **Cost Management** để ước tính, gán tags/environment owner và đặt budget alert. **Budget alert không tự dừng việc tính phí**.

Đối với build-heavy workload, hãy quan sát pull frequency, image size, số lớp trùng lặp, cache và chi phí dữ liệu. Tối ưu Dockerfile và giảm image size có thể giảm thời gian khởi động và chi phí truyền dữ liệu mà không cần tăng số replicas.

### Thời điểm dọn tài nguyên

Sau lab, registry Premium và replicas vẫn có thể tính phí ngay cả khi bạn không push image. Xóa registry hoặc resource group **chỉ khi chắc chắn không còn workload khác phụ thuộc** và đã lưu artifact cần giữ. Không xóa image/digest đang được production sử dụng chỉ để giải phóng vài GiB.

## 24. Bài thực hành an toàn: thiết kế và xác minh ACR đa region

Bài tập có hai mức: **thiết kế/read-only** không cần tạo tài nguyên mới, và **lab có tính phí** nếu bạn đã được cấp subscription riêng.

### Bối cảnh

Doanh nghiệp có hai vùng:

- **Region A:** Container Apps production chính và CI runner.
- **Region B:** Container Apps standby/active, có thể scale-out khi A lỗi.
- Image nghiệp vụ **orders/api:1.8.4** được build bởi một pipeline.
- Yêu cầu: workload chỉ pull image, CI chỉ push repository cần thiết; registry không cho phép truy cập public tùy tiện.
- Có chính sách phải giữ digest release trước cho rollback.

### Phần A — lập thiết kế

Điền bảng:

| Hạng mục | Thiết kế đề xuất | Điều cần chứng minh |
|---|---|---|
| SKU | ACR Premium | Tính năng geo-replication/private network được hỗ trợ |
| Replicas | A và B theo vùng được cho phép | Provisioning health + pull ở cả hai vùng |
| Image identity | Tag bất biến + pin digest | Hai vùng chạy cùng digest |
| CI identity | Managed/federated identity với quyền push hẹp | Push đúng repo, không quản trị network |
| Workload identity | Managed identity chỉ pull | Không thể push |
| Registry endpoint | Cùng login server | DNS/đường mạng hoạt động từ A/B |
| Private networking | Private Endpoint và DNS theo topology | Login và data endpoints đều reachable |
| Public access | Giới hạn hoặc tắt sau khi kiểm thử private | Không mất CI/scale-out |
| Observability | Registry/workload/network logs | Phân biệt 401, 403, timeout và replica lag |
| Recovery | Image digest cũ + runbook B | Pull/khởi động B khi A lỗi |

### Phần B — kiểm tra read-only trong Azure CLI

Với một registry được cấp quyền xem:

~~~bash
az login
az account set --subscription "<LAB_SUBSCRIPTION_ID>"

ACR="<EXISTING_LAB_ACR>"
RG="<LAB_RESOURCE_GROUP>"

az acr show \
  --name "$ACR" \
  --query "{name:name,sku:sku.name,loginServer:loginServer,publicNetworkAccess:publicNetworkAccess,adminEnabled:adminUserEnabled}" \
  --output json

az acr replication list \
  --registry "$ACR" \
  --resource-group "$RG" \
  --output table

az acr network-rule list \
  --name "$ACR" \
  --output json
~~~

Lệnh xem repository cần **data-plane quyền thích hợp** và đường mạng tới ACR:

~~~bash
az acr repository list \
  --name "$ACR" \
  --output table
~~~

Nếu bị 401/403 hoặc timeout, ghi lại loại lỗi và kiểm tra quyền/network thay vì bật admin user. Không cần cố tạo image hoặc VM để hoàn thành phần thiết kế.

### Phần C — lab tạo tài nguyên có tính phí (tùy chọn)

Nếu tổ chức cấp **subscription lab**, có budget và phê duyệt tạo Premium registry:

1. Chọn hai region được hỗ trợ; xác nhận chính sách dữ liệu và chi phí.
2. Tạo resource group riêng cho lab và ACR Premium với admin user disabled.
3. Tạo replica B; quan sát trạng thái bằng **az acr replication list**.
4. Push image thử có tag duy nhất từ runner đã được phép, ghi digest.
5. Kiểm tra pull đúng digest từ A và B bằng hai client lab có đường mạng/role hợp lệ.
6. Nếu thực hành Private Endpoint, tạo và kiểm tra DNS/Private Endpoint dưới hướng dẫn của nhóm mạng; chỉ tắt public access sau khi đường private hoạt động.
7. Thử một **identity chỉ pull** và xác nhận thao tác push bị từ chối.
8. Thực hiện diễn tập "CI offline", "replica lag" hoặc "network lỗi" ở mức mô phỏng, không phá registry chung.
9. Ghi kết quả và dọn tài nguyên **riêng của lab** sau khi chắc chắn không còn dữ liệu cần giữ.

**Không cố ý ngắt production registry, khóa firewall hoặc xóa replica để tạo sự cố thực nghiệm.** Mọi thử nghiệm failover thật cần runbook, quyền và thời điểm được phê duyệt.

### Bằng chứng cần nộp

| Hạng mục | Bằng chứng |
|---|---|
| Registry | SKU, region chính, login server, role assignment permissions mode |
| Replicas | Danh sách vùng, trạng thái, thời điểm kiểm tra |
| Image | Repository, tag, digest, target CPU architecture |
| Identity | Quyền pull/push của CI và workload, không ghi secret |
| Network | Public policy, Private Endpoint, DNS login/data endpoints |
| Test | Pull từ A/B, lỗi và cách khắc phục nếu thất bại |
| Security | Admin disabled, hạn chế public, quyền repo phù hợp |
| DR | Cách giữ release cũ, cách scale-out B và kiểm tra nghiệp vụ |
| Cost | Ước tính Premium/replica/private networking và kết quả cleanup |

## 25. Checklist trước khi đưa ACR đa region vào production

- [ ] Đã xác định lý do cần geo-replication theo workload/RTO và chọn SKU Premium phù hợp.
- [ ] Region A/B đáp ứng residency, service support và quota.
- [ ] Sử dụng một registry login server và hiểu replication bất đồng bộ.
- [ ] CI build một lần, push một lần, tag duy nhất và ghi digest.
- [ ] Cluster/Container Apps ở từng region có thể pull đúng digest và CPU architecture.
- [ ] Đã kiểm tra **role assignment permissions mode** của ACR; không trộn AcrPull với mô hình ABAC mà chưa xác minh.
- [ ] CI chỉ có quyền ghi repository cần thiết, workloads chỉ pull.
- [ ] Admin user bị tắt trừ khi có ngoại lệ được phê duyệt và kiểm soát.
- [ ] Private Endpoint/DNS phù hợp từng VNet; đã kiểm tra cả login/data endpoints.
- [ ] Không tắt public access trước khi xác minh CI/AKS/Container Apps có đường private hoặc allowlist hợp lệ.
- [ ] Có logging, audit, alert và quy trình xác định lỗi 401/403/DNS/replication.
- [ ] Image signing/scanning/SBOM và quản lý secret theo chính sách supply chain.
- [ ] Có bản release trước được giữ để rollback và đã kiểm thử scale-out B.
- [ ] Có runbook cho mất một region, đóng băng release, kiểm tra digest và phục hồi pipeline.
- [ ] Có budget/cost monitoring cho Premium, replicas, network và log retention.
- [ ] Đã kiểm tra đường cleanup trong lab mà không ảnh hưởng production.

## 26. Câu hỏi tự kiểm tra

1. Một ACR geo-replicated Premium sử dụng một login server hay mỗi region có login server khác nhau?
2. Geo-replication có đồng bộ image tức thời và có tự triển khai app sang Container Apps B không?
3. Vì sao nên lưu digest khi phát hành thay vì chỉ dùng tag **latest**?
4. Nếu ACR đã có replica B nhưng AKS B không có quyền pull, geo-replication có giải quyết được không?
5. Vai trò **AcrPull/AcrPush** khác cách cấp quyền repository-level ABAC ở đâu?
6. Vì sao CI writer không nên có quyền đổi firewall và geo-replication settings?
7. Repository-scoped token khác managed identity như thế nào? Trường hợp nào phù hợp với mỗi loại?
8. Tại sao Private Endpoint không tự cấp quyền đọc image?
9. Nếu login thành công nhưng pull layers timeout, nên kiểm tra những endpoint/DNS nào?
10. Với two-region ACR private, tại sao phải kiểm thử DNS và pull từ cả hai VNets?
11. Việc tắt public network access có thể làm hỏng hosted CI pipeline như thế nào?
12. Vì sao Container Apps/AKS production thường chỉ cần quyền pull?
13. Trường hợp nào làm xuất hiện **manifest unknown** dù replica đã được tạo?
14. Vì sao một image có digest hợp lệ vẫn không chạy trên ARM64 node?
15. Geo-replication có bảo đảm database RPO hoặc failover của Front Door không?
16. Những dữ liệu nào phải thu thập khi điều tra ImagePullBackOff?
17. Chi phí nào xuất hiện khi thêm geo replica và Private Endpoint?
18. Tại sao cần giữ image release cũ dù pipeline đã push release mới thành công?

## 27. Tài liệu tham khảo

- [Azure Container Registry overview](https://learn.microsoft.com/azure/container-registry/container-registry-intro) — registry, repositories và vai trò ACR.
- [Geo-replication in Azure Container Registry](https://learn.microsoft.com/azure/container-registry/container-registry-geo-replication) — Premium geo replicas và kiến trúc phân phối đa region.
- [Azure Container Registry service tiers](https://learn.microsoft.com/azure/container-registry/container-registry-skus) — Basic/Standard/Premium và giới hạn.
- [Authenticate with an Azure container registry](https://learn.microsoft.com/azure/container-registry/container-registry-authentication) — Entra ID, service principal, managed identity và credential.
- [Overview of permissions and roles in Azure Container Registry](https://learn.microsoft.com/azure/container-registry/container-registry-rbac-built-in-roles-overview) — quyền registry và repository theo mode.
- [Repository permissions using ABAC](https://learn.microsoft.com/azure/container-registry/container-registry-rbac-abac-repository-permissions) — điều kiện phân quyền theo repository.
- [Repository-scoped permissions](https://learn.microsoft.com/azure/container-registry/container-registry-repository-scoped-permissions) — tokens và scope maps.
- [Restrict access to an Azure container registry](https://learn.microsoft.com/azure/container-registry/container-registry-access-selected-networks) — public network firewall/IP rules.
- [Connect privately to an Azure container registry](https://learn.microsoft.com/azure/container-registry/container-registry-private-link) — Private Endpoint và DNS.
- [Managed identity image pull in Azure Container Apps](https://learn.microsoft.com/azure/container-apps/managed-identity-image-pull) — kết nối ACA–ACR bằng identity.
- [Authenticate from AKS to ACR](https://learn.microsoft.com/azure/aks/cluster-container-registry-integration) — kubelet identity và quyền pull.
- [Azure CLI: az acr](https://learn.microsoft.com/cli/azure/acr) — registry management, login và health.
- [Azure CLI: az acr replication](https://learn.microsoft.com/cli/azure/acr/replication) — tạo và liệt kê geo replicas.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — ước tính Premium/replication/networking theo vùng.

**Kết luận:** Phân phối image đa region an toàn phải giải quyết đồng thời **đúng artifact**, **đủ replica**, **đúng danh tính/quyền** và **đúng đường mạng**. ACR Premium geo-replication cung cấp nền tảng phân phối image nhiều region qua một registry, nhưng sao chép có độ trễ và không thay cơ chế triển khai/DR ứng dụng. Hãy dùng tag bất biến và digest, giới hạn quyền push/pull theo mode được hỗ trợ, kiểm thử Private Link/DNS từ từng region, giám sát lỗi thực tế và duy trì runbook rollback cùng kế hoạch chi phí.
