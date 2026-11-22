# Cloud Asset Inventory và kiểm kê cấu hình trên Google Cloud

> **Chương:** Quản trị tổ chức  
> **Mô-đun:** **CLOUD_PROVIDERS_GCP** — Khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

Khi một tổ chức có hàng trăm project và hàng nghìn tài nguyên, nhóm nền tảng cần biết **đang có những gì, chúng nằm ở đâu, ai quản lý, quyền IAM nào đang được gán và cấu hình nào vừa thay đổi**. Màn hình quản lý của từng dịch vụ chỉ cho biết một phần tình trạng hạ tầng.

**Cloud Asset Inventory (CAI)** là dịch vụ Google Cloud giúp tìm kiếm, liệt kê, phân tích, xuất và theo dõi metadata tài nguyên và chính sách được hỗ trợ ở phạm vi project, folder hoặc organization. CAI cung cấp nguyên liệu quan trọng cho kiểm kê cấu hình, quản trị IAM, kiểm toán, phát hiện drift và quản lý vòng đời.

Điểm cần hiểu từ đầu: **CAI quan sát metadata, không tự bảo đảm tất cả tài nguyên đều an toàn, không thay thế bản sao lưu dữ liệu và không phải cơ sở dữ liệu cập nhật tức thì cho mọi thay đổi**.

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích asset, asset type, content type, scope, snapshot và thay đổi metadata.
2. Phân biệt **SearchAllResources**, **SearchAllIamPolicies**, **ListAssets**, **ExportAssets**, **GetAssetHistory** và feed.
3. Sử dụng lệnh gcloud chỉ đọc để kiểm kê tài nguyên, location, labels và IAM bindings trong phạm vi được cấp quyền.
4. Thiết kế bộ quy tắc kiểm kê theo owner, environment, location, loại tài nguyên, IAM và vòng đời.
5. Mô tả cách xuất snapshot sang Cloud Storage/BigQuery và dùng Pub/Sub để quan sát thay đổi.
6. Hiểu giới hạn lịch sử, độ nhất quán, độ đầy đủ dữ liệu, quyền truy cập và tác động chi phí.
7. Phân tích một tình huống kiểm toán nhiều project có liên hệ tới Compute Engine, GKE, Cloud Run, VPC và lưu trữ.

## 1. Asset và mục tiêu của kiểm kê cấu hình

Một **asset** là đối tượng hoặc dữ liệu quản trị mà Cloud Asset Inventory hỗ trợ. Ví dụ:

- Compute Engine VM, disk, VPC network hoặc subnet.
- Cloud Storage bucket.
- GKE cluster, node pool; Cloud Run service.
- Một số tài nguyên Cloud SQL, BigQuery hoặc dịch vụ khác theo danh mục được hỗ trợ.
- IAM allow policy, Organization Policy, Access Context Manager policy.
- Một số OS inventory metadata và quan hệ tài nguyên theo khả năng của sản phẩm.

Mỗi asset có **loại** như **compute.googleapis.com/Instance** hoặc **storage.googleapis.com/Bucket**, **tên tài nguyên đầy đủ**, scope và những thuộc tính khác phù hợp với content type. Cấu trúc metadata giữa hai dịch vụ có thể khác nhau.

Ví dụ lược giản:

~~~yaml
# Chỉ minh họa khái niệm; không phải JSON/YAML trả về nguyên vẹn từ API.
name: //compute.googleapis.com/projects/shop-prod/zones/us-central1-a/instances/123456789
assetType: compute.googleapis.com/Instance
location: us-central1-a
labels:
  environment: production
  team: payments
  application: checkout
~~~

Tên đầy đủ của một asset không đồng nhất với tên VM hiển thị; project ID, project number và resource ID cũng có vai trò khác nhau. Muốn đối chiếu dữ liệu giữa các hệ thống, cần giữ **định danh gốc** và cách chuẩn hóa của từng nguồn.

### 1.1. Vì sao cần kiểm kê định kỳ?

Hạ tầng có thể thay đổi từ nhiều nguồn: Terraform, pipeline CI/CD, Console, CLI, cơ chế autoscaling và thao tác trực tiếp của người vận hành. Tài nguyên có thể được tạo, đổi quyền, thay location khi tái tạo, đổi label hoặc bị xóa. Một bảng tính thủ công nhanh chóng cũ đi.

Một vòng kiểm kê tốt giúp trả lời:

| Câu hỏi quản trị | Dữ liệu cần dùng | Hành động có thể phát sinh |
|---|---|---|
| Tài nguyên nào không có chủ sở hữu? | Asset type, project, labels/tags | Xác định owner, sửa metadata qua IaC |
| VM hoặc database nào nằm ngoài vùng được phê duyệt? | Location, cấu hình resource | Rà soát yêu cầu lưu trú dữ liệu và phương án di chuyển |
| Ai được gán role nhạy cảm? | IAM allow policy, principal, role, scope | Kiểm tra quyền tối thiểu và phê duyệt ngoại lệ |
| Có tài nguyên thử nghiệm bỏ quên? | Labels, create/update time, project | Kiểm tra phụ thuộc, chi phí, sau đó mới dọn dẹp |
| Tài nguyên nào mới xuất hiện kể từ hôm qua? | Hai snapshot hoặc feed | Đối chiếu PR và audit log |
| Có thay đổi cấu hình ngoài pipeline? | Asset snapshot, feed, IaC state, audit logs | Điều tra drift và cập nhật nguồn chuẩn |

CAI là **nguồn dữ liệu quan sát**. Nó không tự trả lời “ai là owner” nếu tổ chức chưa thống nhất metadata owner và không có dữ liệu điền vào.

## 2. Liên hệ với resource hierarchy

Google Cloud tổ chức tài nguyên thành organization, folder và project. CAI cho phép làm việc với scope phù hợp với quyền và phương thức API.

~~~mermaid
flowchart TD
    O["Organization"]
    F1["Folder: commerce"]
    F2["Folder: analytics"]
    P1["Project: shop-dev"]
    P2["Project: shop-prod"]
    P3["Project: data-prod"]
    R1["VM / VPC"]
    R2["GKE / Cloud Run / Cloud SQL"]
    R3["BigQuery"]
    O --> F1
    O --> F2
    F1 --> P1
    F1 --> P2
    F2 --> P3
    P1 --> R1
    P2 --> R2
    P3 --> R3
    CAI["Cloud Asset Inventory"] -. "Search/List trong scope được cấp quyền" .-> O
    CAI -. "Hoặc chọn folder/project" .-> P2
~~~

- **Organization:** phạm vi rộng cho kiểm kê tập trung, đòi hỏi quyền ở cấp tương ứng.
- **Folder:** hỗ trợ phân loại đơn vị quản trị, nhiều thao tác CAI cho phép dùng folder làm scope.
- **Project:** phạm vi dễ bắt đầu khi học và khi chỉ được phép quan sát một sản phẩm/môi trường.

**Không mặc định một truy vấn organization luôn thấy toàn bộ dữ liệu**: loại API, quyền tại scope, loại asset được hỗ trợ, bộ lọc, phân trang và độ mới của index đều ảnh hưởng kết quả. Nếu một công cụ chỉ trả 100 tài nguyên, cần kiểm tra giới hạn/pagination trước khi tuyên bố organization có đúng 100 tài nguyên.

### 2.1. Các sản phẩm liên quan, không thay thế nhau

| Sản phẩm/cơ chế | Giá trị chính | Giới hạn khi dùng để kiểm kê |
|---|---|---|
| **Cloud Asset Inventory** | Danh mục metadata, policy, snapshot, tìm kiếm, feed | Không bao gồm mọi loại runtime/data event |
| **Cloud Audit Logs** | Sự kiện API, hành động và chủ thể theo loại log | Không phải snapshot đầy đủ trạng thái hiện tại |
| **Cloud Monitoring** | Metric, cảnh báo, uptime/SLO | Không mô tả đầy đủ chủ sở hữu và policy |
| **Security Command Center** | Findings, lỗ hổng, sai cấu hình tùy tier | Không thay cho toàn bộ inventory phục vụ vận hành |
| **Cloud Billing** | Chi phí theo project/service/SKU | Không chỉ ra mọi cấu hình bảo mật |
| **Terraform/IaC state** | Các tài nguyên do mã nguồn quản lý | Không thấy toàn bộ tài nguyên tạo ngoài state |
| **Organization Policy và IAM** | Thực thi quyền và ràng buộc | Không phải bảng tổng hợp mọi tài nguyên |

Để trả lời “ai tạo VM?”, đối chiếu audit log. Để trả lời “VM có lỗ hổng OS?”, cần giải pháp vulnerability/OS inventory tương ứng. Để trả lời “VM đang tồn tại ở đâu và có nhãn nào?”, CAI là điểm khởi đầu phù hợp.

## 3. Content type và asset type

Một **asset type** mô tả loại đối tượng, chẳng hạn **compute.googleapis.com/Instance**. **Content type** cho biết lớp nội dung cần lấy.

| Content type | Nội dung | Ví dụ ứng dụng |
|---|---|---|
| **RESOURCE** | Metadata cấu hình tài nguyên | Danh mục VM, bucket, cluster và location |
| **IAM_POLICY** | IAM allow policy trên resource được hỗ trợ | Tìm principal/role gán cho resource |
| **ORG_POLICY** | Organization Policy được hỗ trợ | Rà soát quy tắc vị trí, ràng buộc quản trị |
| **ACCESS_POLICY** | Access Context Manager metadata được hỗ trợ | Kiểm tra một phần chính sách truy cập |
| **OS_INVENTORY** | Thông tin OS inventory khi có tích hợp | Hỗ trợ kiểm kê OS metadata |
| **RELATIONSHIP** | Quan hệ giữa asset types được hỗ trợ | Tìm liên hệ hạ tầng phù hợp |

Không phải asset type nào cũng dùng được với mọi API hoặc content type. **RELATIONSHIP** và những khả năng phân tích nâng cao có thể yêu cầu **Security Command Center Premium/Enterprise** hoặc điều kiện sản phẩm tương ứng. Danh sách hỗ trợ thay đổi; luôn tra [Supported asset types](https://docs.cloud.google.com/asset-inventory/docs/asset-types) trước khi xây automation.

### 3.1. Ba lớp metadata cần phân biệt

1. **Thông tin chuẩn hóa:** full resource name, asset type, scope, location, thời điểm tạo/cập nhật, labels nếu có.
2. **Payload riêng của dịch vụ:** các field chi tiết của Compute Engine, GKE, Cloud Run hoặc database.
3. **Policy/relationship:** IAM bindings, Organization Policy và các quan hệ được dịch vụ hỗ trợ.

Một rule đơn giản “VM không có owner label” có thể dùng metadata chuẩn hóa. Một rule “VM có bật cấu hình bảo vệ nhất định” có thể cần đọc payload RESOURCE và kiểm tra lại API Compute Engine.

### 3.2. CAI không phải bản sao dữ liệu

Kiểm kê một Cloud Storage bucket không đồng nghĩa CAI đang sao lưu toàn bộ object. Tương tự, kiểm kê một Cloud SQL instance không sao chép nội dung bảng dữ liệu. Muốn theo dõi object upload, truy cập dữ liệu hoặc bảo vệ dữ liệu, phải dùng cơ chế sự kiện, log và backup của dịch vụ phù hợp.

## 4. Chọn công cụ: Search, List, Export, History và Feed

~~~mermaid
flowchart LR
    R["Resource / policy metadata"] --> S["SearchAllResources / SearchAllIamPolicies"]
    R --> L["ListAssets"]
    R --> E["ExportAssets"]
    R --> H["GetAssetHistory"]
    R --> F["Feeds → Pub/Sub"]
    S --> Q1["Điều tra nhanh theo query"]
    L --> Q2["Snapshot trong scope"]
    E --> Q3["Báo cáo BigQuery / GCS"]
    H --> Q4["Lịch sử gần đây"]
    F --> Q5["Phản ứng thay đổi gần thời gian thực"]
~~~

| Thao tác | Nhu cầu chính | Khác biệt đáng chú ý |
|---|---|---|
| **SearchAllResources** | Tìm theo tên, loại, location, labels và các trường có hỗ trợ | Dùng ngôn ngữ search của CAI; không phải SQL |
| **SearchAllIamPolicies** | Tìm IAM allow bindings theo role/principal/condition | Chỉ phản ánh binding khớp query, không tính mọi effective permission |
| **ListAssets** | Lấy asset snapshot theo scope/content type | Phù hợp tạo tập inventory tại thời điểm đọc |
| **ExportAssets** | Đưa asset snapshot vào Cloud Storage hoặc BigQuery | Phù hợp kiểm toán và phân tích quy mô lớn |
| **GetAssetHistory** | Xem tạo/sửa/xóa trong cửa sổ lịch sử | Bị giới hạn thời gian và phạm vi |
| **Feeds** | Gửi thông báo thay đổi metadata được hỗ trợ tới Pub/Sub | Cần consumer xử lý retry/lặp, xác thực kết quả |
| **QueryAssets** | Phân tích asset trực tiếp bằng cú pháp SQL tương thích BigQuery | Có điều kiện về tier/tính năng và quyền |

**Mấu chốt về độ mới:** CAI có **eventual consistency** với dữ liệu hiện tại và **best-effort consistency** với dữ liệu lịch sử. Một resource vừa tạo có thể chưa xuất hiện ngay trong kết quả tìm kiếm; snapshot không phải bằng chứng duy nhất để ra quyết định xóa hoặc khẩn cấp thu hồi quyền.

## 5. SearchAllResources: tìm tài nguyên theo điều kiện

### 5.1. Lệnh gcloud chỉ đọc

Yêu cầu đã cài gcloud CLI, đăng nhập, Cloud Asset Inventory API khả dụng, principal có quyền **cloudasset.assets.searchAllResources** trên scope và có cấu hình quota project/Service Usage cần thiết.

~~~bash
PROJECT_ID="shop-dev"

# Xem tài nguyên có thể tìm kiếm trong project.
gcloud asset search-all-resources \
  --scope="projects/$PROJECT_ID" \
  --format="table(name,assetType,location)"

# Chỉ xem Compute Engine instances.
gcloud asset search-all-resources \
  --scope="projects/$PROJECT_ID" \
  --asset-types="compute.googleapis.com/Instance" \
  --format="table(name,assetType,location,labels)"

# Tìm tên asset có từ checkout.
gcloud asset search-all-resources \
  --scope="projects/$PROJECT_ID" \
  --query="name:checkout" \
  --format="table(name,assetType,location)"
~~~

Các lệnh trên **không tạo hoặc sửa tài nguyên**. Nếu không có kết quả, kiểm tra lại quyền, scope, kiểu asset, cấu trúc query và độ trễ index trước khi kết luận.

### 5.2. Query theo location và labels

~~~bash
# Ví dụ tìm tài nguyên tại location có chứa cụm us-central1.
gcloud asset search-all-resources \
  --scope="projects/$PROJECT_ID" \
  --query="location:us-central1" \
  --format="table(name,assetType,location)"

# Ví dụ tìm metadata labels có chứa production.
gcloud asset search-all-resources \
  --scope="projects/$PROJECT_ID" \
  --query="labels:production" \
  --format="table(name,assetType,labels)"
~~~

Cú pháp **labels:production** thực hiện tìm kiếm theo chỉ mục; không phải một kiểm tra SQL chính xác **environment = production**. Khi dùng kết quả để áp chính sách, phải kiểm tra cặp key/value theo schema hoặc query field cụ thể mà CAI hỗ trợ. Tránh coi một kết quả tìm theo từ khóa là kiểm chứng compliance tuyệt đối.

### 5.3. Search trong organization hoặc folder

~~~bash
ORG_ID="123456789012"
FOLDER_ID="234567890123"

# Chỉ người được cấp quyền trên organization mới có thể xem đúng scope.
gcloud asset search-all-resources \
  --scope="organizations/$ORG_ID" \
  --asset-types="compute.googleapis.com/Instance" \
  --format="table(name,assetType,location)"

gcloud asset search-all-resources \
  --scope="folders/$FOLDER_ID" \
  --query="name:checkout"
~~~

Các ID trên là placeholder. Quyền xem ở project không mặc nhiên cho phép truy vấn toàn organization. Khi trích xuất ở scope lớn, dữ liệu topology và tên ứng dụng có thể nhạy cảm; cần giới hạn người nhận và thời gian lưu.

### 5.4. Search query khác gcloud filter

**--query** được dịch vụ Cloud Asset Inventory đánh giá với các toán tử/cú pháp riêng. **--filter**, khi dùng, là cơ chế lọc kết quả của gcloud. Hai biểu thức khác mục đích và cú pháp. Nếu muốn kết quả đầy đủ, phải tính tới **--limit**, phân trang và các asset types được hỗ trợ.

## 6. SearchAllIamPolicies: kiểm kê IAM allow bindings

IAM allow policy có các binding giữa principal, role và tài nguyên. **SearchAllIamPolicies** giúp tìm policy có:

- **roles/owner** hoặc vai trò quyền cao.
- Email người dùng, nhóm hoặc service account.
- Principal **allUsers**, **allAuthenticatedUsers**.
- Điều kiện IAM liên quan đến nhóm tài nguyên cần rà soát.

### 6.1. Ví dụ gcloud chỉ đọc

~~~bash
PROJECT_ID="shop-dev"

# Binding có roles/owner.
gcloud asset search-all-iam-policies \
  --scope="projects/$PROJECT_ID" \
  --query="policy:roles/owner" \
  --format="json"

# Binding của một service account cụ thể.
gcloud asset search-all-iam-policies \
  --scope="projects/$PROJECT_ID" \
  --query="policy:caller@shop-dev.iam.gserviceaccount.com" \
  --format="json"

# Các binding có allUsers.
gcloud asset search-all-iam-policies \
  --scope="projects/$PROJECT_ID" \
  --query="memberTypes:allUsers" \
  --format="json"
~~~

Kết quả tìm có thể chứa **chỉ các bindings khớp query**, không phải toàn bộ IAM policy của mỗi tài nguyên. Search cần quyền **cloudasset.assets.searchAllIamPolicies** trên scope.

### 6.2. Không nhầm binding được tìm thấy với quyền hiệu lực

| Câu hỏi | Search IAM policy cung cấp gì? | Điều còn phải xem |
|---|---|---|
| Role Owner được gán ở đâu? | Binding phù hợp với query | Scope thật, condition và chủ thể |
| User có quyền từ folder cha? | Có thể thấy binding trong scope bao quát | Kế thừa resource hierarchy, group membership |
| Principal có thể đọc bucket? | Có thể tìm policy liên quan | Role permissions, conditions, deny, policy khác |
| Service account có bị impersonate? | Một phần binding liên quan | Quyền service account Token Creator và chính sách khác |
| Tài nguyên có thật sự public? | Có thể thấy allUsers binding | Cấu hình sản phẩm và effective policies |
| API call có thành công? | Không xác định hoàn toàn | IAM thực tế, quota, API enabled, mạng, trạng thái dịch vụ |

Khi cần phân tích “**ai có thể truy cập tài nguyên nào**”, dùng **IAM Policy Analyzer**, đánh giá inheritance và các quy tắc deny/conditions; tìm allow binding chỉ là một bước. Với custom roles, việc phân tích quyền thành phần có thể cần thêm **iam.roles.get**.

**Không xóa binding bằng script chỉ dựa trên kết quả search.** Phải kiểm tra vai trò, người chịu trách nhiệm, ảnh hưởng production và quy trình phê duyệt.

## 7. ListAssets và lịch sử cấu hình 35 ngày

**ListAssets** liệt kê các asset trong một scope với content type cụ thể.

~~~bash
PROJECT_ID="shop-dev"

# Liệt kê metadata RESOURCE trong project.
gcloud asset list \
  --project="$PROJECT_ID" \
  --content-type=resource \
  --format="json"

# Giới hạn vào các VM được hỗ trợ.
gcloud asset list \
  --project="$PROJECT_ID" \
  --asset-types="compute.googleapis.com/Instance" \
  --content-type=resource \
  --format="json"
~~~

Lưu ý nếu không chọn content type, API có thể chỉ trả thông tin cơ bản như tên và loại asset. Với inventory lớn nên xuất snapshot hoặc xử lý dữ liệu có phân trang thay vì chép toàn bộ JSON lên terminal.

### 7.1. Truy vấn một snapshot time

~~~bash
# Chỉ ví dụ với ngày nằm trong khoảng lịch sử còn được hỗ trợ.
gcloud asset list \
  --project="shop-dev" \
  --content-type=resource \
  --asset-types="compute.googleapis.com/Instance" \
  --snapshot-time="2026-11-18T00:00:00Z" \
  --format="json"
~~~

Theo tài liệu, CAI cho phép truy xuất lịch sử tạo/sửa/xóa **tối đa 35 ngày**. Với asset không thay đổi trong khoảng này, hệ thống có thể trả trạng thái mới nhất. API **GetAssetHistory** chuyên biệt hỗ trợ lịch sử ở **organization và project**, không có phạm vi folder như các thao tác tìm kiếm/liệt kê khác.

**35 ngày không đủ cho lịch sử kiểm toán nhiều quý**. Nếu cần dữ liệu dài hạn, phải thiết kế **snapshot định kỳ, nhật ký thay đổi và retention** ngay từ đầu.

### 7.2. History và Audit Logs có vai trò khác nhau

- **Asset history:** trạng thái metadata và những thay đổi được CAI lưu.
- **Cloud Audit Logs:** hoạt động gọi API, actor và thời điểm theo loại log.
- **Git/IaC history:** thay đổi được review từ commit/PR nào.
- **Monitoring:** thay đổi có tác động tới traffic, latency, errors và SLO hay không.

Ví dụ CAI cho biết chính sách IAM đổi vào một ngày, nhưng để tìm **ai thực hiện và tại sao**, cần liên kết audit log và PR/ticket liên quan.

## 8. ExportAssets sang BigQuery hoặc Cloud Storage

**ExportAssets** tạo snapshot metadata ở một đích do người quản trị cấu hình. Phù hợp cho kiểm kê định kỳ, kiểm toán, dashboard và lưu giữ lâu hơn cửa sổ history của CAI.

~~~mermaid
flowchart TD
    CAI["Cloud Asset Inventory"] --> E["ExportAssets"]
    E --> GCS["Cloud Storage: snapshot có retention"]
    E --> BQ["BigQuery: bảng kiểm kê"]
    BQ --> CHECK["SQL: labels, location, owner, policy"]
    CHECK --> REPORT["Dashboard hoặc báo cáo ngoại lệ"]
    REPORT --> REVIEW["Owner xác minh và sửa qua IaC"]
~~~

### 8.1. Ví dụ xuất snapshot tới BigQuery

Lệnh sau **ghi dữ liệu BigQuery**, không thuộc phần thực hành chỉ đọc. Chỉ dùng khi đã được phép tạo bảng, cấu hình API và quyền ở scope nguồn cũng như dataset đích.

~~~bash
SOURCE_PROJECT="shop-dev"
BQ_PROJECT="inventory-admin"
BQ_DATASET="asset_inventory"
BQ_TABLE="snapshot_20261119"

gcloud asset export \
  --project="$SOURCE_PROJECT" \
  --content-type=resource \
  --asset-types="compute.googleapis.com/Instance,storage.googleapis.com/Bucket" \
  --bigquery-table="projects/$BQ_PROJECT/datasets/$BQ_DATASET/tables/$BQ_TABLE"
~~~

Khi xuất tới bảng đã tồn tại, kiểm tra **overwrite, append và partition** trước khi chạy. Cờ **--output-bigquery-force** có thể ghi đè dữ liệu ở trường hợp tương ứng, nên không đưa vào pipeline khi chưa kiểm soát đích.

Giới hạn theo tài liệu: không phải mọi field của asset đều được hỗ trợ trong export; một số trường thay đổi thường xuyên có thể bị xuất thành **null**; xuất theo từng asset type có hạn chế với các loại tài nguyên GKE khác nhau. Quy tắc kiểm kê phải xử lý **null = chưa xác định** khi thiếu dữ liệu, thay vì mặc định “pass” hoặc “fail”.

### 8.2. Asset export khác Cloud Billing export

| Cloud Asset Inventory export | Cloud Billing export |
|---|---|
| Metadata về tài nguyên, cấu hình và policy | Dữ liệu usage cost, service, SKU, credits |
| Cho biết tài nguyên nào tồn tại và cấu hình ra sao | Cho biết khoản gì đang phát sinh chi phí |
| Dễ tổ chức snapshot theo thời điểm | Theo cơ chế ghi nhận dữ liệu billing |
| Khóa chính thường dựa vào asset/resource name | Resource ID có thể thiếu trên một số dòng |
| Dùng cho configuration governance | Dùng cho FinOps/đối soát hóa đơn |

Muốn tìm các VM thiếu owner nhưng vẫn tốn tiền, có thể kết hợp hai nguồn sau khi chuẩn hóa identifier và thời gian. **Không join bằng tên gần giống** rồi coi kết quả chính xác; phạm vi resource identifiers của billing phụ thuộc dịch vụ và loại export.

### 8.3. Đặt lịch snapshot đúng cách

1. Cố định **scope, asset types, content type** và timestamp thu thập.
2. Xuất vào bucket/dataset được bảo vệ, có retention và owner.
3. Ghi trạng thái job, số record, schema và lỗi quyền nếu có.
4. So sánh snapshot mới với snapshot cũ theo ID ổn định.
5. Phân loại **created / updated / deleted / unknown**.
6. Xác minh thay đổi quan trọng bằng API đích và audit logs.
7. Tạo ticket/PR cho owner; kiểm tra lại sau khi sửa.

Nếu số asset từ 500 xuống 450, không vội kết luận có 50 tài nguyên bị xóa. Trước hết cần kiểm tra **lỗi job, bộ lọc, quyền, schema và độ trễ đồng bộ**.

## 9. QueryAssets bằng SQL và điều kiện sử dụng

Google Cloud hỗ trợ truy vấn tài sản trực tiếp bằng **SQL tương thích BigQuery** trong Asset Inventory. Theo tài liệu hiện hành, khả năng này yêu cầu quyền/tier phù hợp, chẳng hạn **Security Command Center Premium/Enterprise hoặc Gemini Cloud Assist**. Không phải mọi project đều có tab hoặc API QueryAssets.

Ví dụ minh họa:

~~~sql
-- Ví dụ chạy trong tính năng Asset query khi được cấp quyền.
SELECT
  name,
  resource.location
FROM
  compute_googleapis_com_Instance
WHERE
  resource.location LIKE '%asia%'
~~~

Tên bảng QueryAssets được chuyển từ **compute.googleapis.com/Instance** thành **compute_googleapis_com_Instance**. Không áp dụng nguyên xi câu SQL này cho bảng BigQuery do ExportAssets tạo ra khi chưa đọc schema đích: hai phương thức có thể khác cấu trúc bảng.

Nếu không có quyền QueryAssets trực tiếp, có thể xuất snapshot sang BigQuery và truy vấn bảng xuất với quyền được phép. Cần kiểm tra phí lưu trữ và truy vấn, đặc biệt với inventory lớn.

## 10. Feed và Pub/Sub: phát hiện thay đổi metadata

Snapshot hàng ngày có thể bỏ lỡ một thay đổi IAM được tạo rồi xóa trong cùng ngày. **Cloud Asset Inventory feeds** cho phép nhận thông báo khi metadata resource hoặc policy được hỗ trợ thay đổi, với **Pub/Sub** là kênh truyền.

~~~mermaid
sequenceDiagram
    participant A as Admin / Terraform / CI
    participant GCP as Google Cloud resource
    participant CAI as Cloud Asset Inventory feed
    participant PS as Pub/Sub topic
    participant W as Cloud Run checker
    A->>GCP: Tạo/sửa tài nguyên hoặc policy
    GCP-->>CAI: Thay đổi metadata được hỗ trợ
    CAI-->>PS: Welcome message hoặc TemporalAsset event
    PS-->>W: Gửi notification
    W->>W: Kiểm tra event, idempotency, rule
    W-->>A: Alert hoặc ticket để xác minh
~~~

### 10.1. Cấu hình feed có gì?

- **Scope:** project, folder hoặc organization.
- **Asset types/names:** các loại/định danh cần theo dõi.
- **Content type:** resource, IAM_POLICY hoặc loại tương ứng có hỗ trợ.
- **Điều kiện CEL:** lọc loại thay đổi trong những trường hợp được hỗ trợ.
- **Pub/Sub topic:** đích nhận thông báo.
- **Quyền service agent:** cho phép feed publish và các thao tác quản trị liên quan.

Theo tài liệu Google Cloud, thông báo **đầu tiên** sau khi tạo feed có thể là **welcome message dạng chuỗi**, các thông báo tiếp theo ở dạng **TemporalAsset**. Consumer cần phân biệt hai loại để không tạo cảnh báo giả.

### 10.2. Ví dụ tạo feed trong môi trường thử nghiệm

~~~bash
# Lệnh làm thay đổi tài nguyên thật; chỉ chạy ở project được phép.
gcloud asset feeds create inventory-vm-changes \
  --project="shop-dev" \
  --pubsub-topic="projects/monitoring-dev/topics/asset-changes" \
  --asset-types="compute.googleapis.com/Instance" \
  --content-type=resource
~~~

Phải chuẩn bị Pub/Sub topic, quyền publish của service agent và quota. Việc **tạo/cập nhật/xóa feed có thể mất tới khoảng 10 phút mới có hiệu lực**. Nếu không có event ngay lập tức, chưa đủ cơ sở để kết luận feed lỗi.

**Giới hạn:** feed quan sát thay đổi metadata asset được hỗ trợ. Ví dụ upload một object mới vào Cloud Storage bucket không đồng nghĩa metadata **bucket** thay đổi, nên không nên dùng bucket feed như công cụ giám sát mọi lần upload.

### 10.3. Thiết kế consumer an toàn

- Phân biệt welcome message và TemporalAsset.
- Trích asset name, asset type và thời điểm thay đổi.
- Xử lý **message lặp** theo event key/fingerprint có kiểm chứng.
- Giới hạn retry, dùng dead-letter khi phù hợp và giám sát backlog.
- Nếu sắp có hành động quan trọng, kiểm tra trạng thái bằng API đích vì index có thể trễ.
- Chỉ tạo cảnh báo/ticket có owner; không mặc định rollback mọi thay đổi IAM.
- Không ghi dư thừa metadata nhạy cảm vào log.

Một thay đổi IAM có thể là phần hợp lệ của quá trình phát hành hoặc incident response. Do đó, hành động tự động cần dựa trên **nguồn chuẩn IaC và policy đã được phê duyệt**, không chỉ trên việc nhận một event.

## 11. Quy tắc kiểm kê và phát hiện configuration drift

**Configuration drift** là sự khác biệt giữa **trạng thái mong muốn** trong IaC/chính sách và **trạng thái quan sát** từ tài nguyên thật.

~~~mermaid
flowchart LR
    D["Desired: Terraform / policy / exceptions"] --> COMP["So sánh"]
    A["Observed: CAI snapshot + feed"] --> COMP
    LOG["Audit logs / PR / owner"] --> COMP
    COMP --> OK["Hợp lệ"]
    COMP --> DRIFT["Drift / violation / unknown"]
    DRIFT --> REVIEW["Owner review"]
    REVIEW --> FIX["Sửa qua IaC/API được phê duyệt"]
    FIX --> A
~~~

Cần tránh xem những field **được dịch vụ tự quản hoặc thay đổi liên tục** là drift nguy hiểm. Số node GKE tăng vì autoscaling có thể là hành vi mong muốn; việc đánh giá cần bối cảnh workload.

### 11.1. Quy tắc mẫu

| Rule | Dữ liệu kiểm kê | Kết quả khi sai lệch |
|---|---|---|
| Production phải có owner/team | Asset labels và project mapping | Yêu cầu bổ sung metadata sau khi xác nhận owner |
| Database ở vùng được phê duyệt | Resource location và quy định tổ chức | Rà soát cư trú dữ liệu, phương án di chuyển |
| Binding roles/owner phải có lý do | IAM allow bindings, exception registry | Tạo ticket rà soát |
| VM có IP công khai phải được phê duyệt | Compute Engine metadata, network policy | Kiểm tra ingress/firewall, không xóa IP ngay |
| Resource thử nghiệm quá hạn | lifecycle/expires_on labels | Xác nhận phụ thuộc, dữ liệu và chủ sở hữu |
| Production có backup/HA phù hợp | Service-specific RESOURCE và API đích | Kiểm tra RTO/RPO và cấu hình thực |
| IAM hoặc location đổi ngoài pipeline | Feed, snapshot, audit logs, PR | Điều tra drift, ghi nhận remediation |

Ví dụ hợp đồng kiểm kê nội bộ:

~~~yaml
# Định nghĩa mẫu, không phải cấu hình API Cloud Asset Inventory.
controls:
  - id: required-owner
    applies_to: supported_production_resources
    required_labels: [team, application, environment]
    action: report_to_owner

  - id: restricted-location
    applies_to: regulated_data_resources
    allowed_regions: [approved-region-1, approved-region-2]
    exception_requires: [ticket, approver, expires_on]

  - id: excessive-iam
    scope: organization
    review_roles: [roles/owner]
    action: manual_review

  - id: resource-expiry
    scope: development
    requires: [lifecycle, expires_on]
    action: check_dependencies_before_cleanup
~~~

Các tên **approved-region-1/2** là placeholder, không phải tên region thật. Rule production phải được gắn tới cấu hình source phù hợp; chỉ dựa vào tên project chứa “prod” có thể sai nếu hệ thống chưa chuẩn hóa.

### 11.2. Ba trạng thái kết quả

Mỗi kiểm tra nên trả ít nhất:

- **PASS:** có đủ dữ liệu và đúng chính sách.
- **FAIL:** có đủ dữ liệu, vi phạm điều kiện.
- **UNKNOWN:** thiếu metadata, thiếu quyền, asset type chưa hỗ trợ hoặc lỗi đọc dữ liệu.

**UNKNOWN không được tính như PASS.** Nếu 20% project không thu thập được do lỗi IAM, báo cáo “100% compliant” trên 80% còn lại là dễ gây hiểu nhầm.

### 11.3. Chỉ số quản trị nên đo

1. **Coverage:** tỷ lệ project/scope thu thập thành công.
2. **Completeness:** tỷ lệ resource hỗ trợ labels có đủ owner/team/environment.
3. **Compliance:** tỷ lệ đã xác minh PASS; tách UNKNOWN.
4. **Detection latency:** thời gian từ thay đổi đến lúc cảnh báo.
5. **Remediation latency:** thời gian tới khi được xác minh đã sửa.
6. **Recurring drift:** số lỗi lặp lại sau sửa.
7. **Export integrity:** tỷ lệ job snapshot thành công và độ ổn định của số bản ghi.

Các phép đo cần tách trường hợp asset type **không hỗ trợ trường đang kiểm tra** khỏi trường hợp tài nguyên **thực sự thiếu cấu hình**.

## 12. IAM, bảo vệ inventory và trách nhiệm chi phí

Dữ liệu CAI có thể chứa topology mạng, danh tính IAM, tên dịch vụ, quan hệ project và thông tin quản trị nhạy cảm. Quyền đọc inventory cần được kiểm soát.

| Thao tác | Quyền tiêu biểu | Ghi chú |
|---|---|---|
| Search tài nguyên | **cloudasset.assets.searchAllResources** | Cấp ở scope được phép |
| Search IAM | **cloudasset.assets.searchAllIamPolicies** | Kết quả là allow bindings khớp query |
| List resource | **cloudasset.assets.listResource** hoặc quyền list chi tiết | Có thể giới hạn asset type |
| IAM analysis | **cloudasset.assets.analyzeIamPolicy** cùng các quyền liên quan | Có thể cần iam.roles.get và thông tin nhóm |
| QueryAssets SQL | **cloudasset.assets.queryResource** hoặc quyền content type tương ứng | Phụ thuộc tier |
| Export và feed | Quyền CAI phù hợp và quyền đích Cloud Storage/BigQuery/Pub/Sub | Tính cả quyền service agent |

Theo tài liệu CAI, các lời gọi API còn cần quyền như **serviceusage.services.use** trên project phù hợp. Một vai trò **roles/cloudasset.viewer** có thể hữu ích nhưng không bảo đảm đáp ứng mọi hành động. Không cấp Owner cho một pipeline kiểm kê chỉ để lệnh chạy được.

**Thực hành bảo vệ dữ liệu:**

- Đặt bucket/dataset inventory trong project quản trị với IAM tối thiểu.
- Hạn chế ai có thể tải toàn bộ báo cáo IAM/topology.
- Áp dụng retention và vị trí lưu phù hợp.
- Phân biệt người đọc report với service account thu thập.
- Theo dõi chi phí BigQuery storage/query, Cloud Storage, Pub/Sub và Cloud Run consumer.
- Không công khai snapshot hoặc gửi nguyên policy nhạy cảm vào ticket không kiểm soát.

## 13. Thực hành chỉ đọc trong project học tập

Bài thực hành này **không tạo/sửa tài nguyên**, chỉ cần project đã được cấp quyền và gcloud CLI.

### 13.1. Xác minh danh tính

~~~bash
gcloud auth list
gcloud config list

PROJECT_ID="my-training-project"
gcloud projects describe "$PROJECT_ID" \
  --format="table(projectId,name,projectNumber)"
~~~

### 13.2. Lấy mẫu inventory

~~~bash
gcloud asset search-all-resources \
  --scope="projects/$PROJECT_ID" \
  --format="table(name,assetType,location)" \
  --limit=100
~~~

Lưu ý **--limit=100** chỉ lấy mẫu tối đa 100 kết quả, không phải toàn bộ project nếu project có nhiều hơn 100 asset. Muốn kiểm kê đầy đủ phải thu thập toàn bộ trang hoặc export.

### 13.3. Kiểm tra VM và labels

~~~bash
gcloud asset search-all-resources \
  --scope="projects/$PROJECT_ID" \
  --asset-types="compute.googleapis.com/Instance" \
  --format="table(name,location,labels)"
~~~

Ghi bảng kết quả:

| Full resource name | Project | Zone/location | Environment | Owner/team | Ghi chú |
|---|---|---|---|---|---|
| … | … | … | … | … | … |

Nếu không có VM trong scope, ghi “**không thấy VM phù hợp ở phạm vi được phép tìm kiếm**”. Không suy ra không có VM trong organization.

### 13.4. Kiểm tra IAM nhạy cảm

~~~bash
gcloud asset search-all-iam-policies \
  --scope="projects/$PROJECT_ID" \
  --query="policy:roles/owner" \
  --format="json" \
  --limit=20
~~~

Chỉ ghi nhận tài nguyên, principal, role và condition nếu có; không sửa IAM trong bài thực hành này. Nếu thấy Owner binding, viết ra câu hỏi cần xác minh với owner.

### 13.5. Tổng hợp kết quả và kiến nghị

Mẫu báo cáo ngắn:

~~~text
Inventory scope:
Collection time (UTC):
Asset types queried:
Total records returned:
Was result limited/paginated:
Projects covered:
Missing owner/team labels:
Suspicious IAM bindings:
Resources outside approved locations:
UNKNOWN due to missing data/permissions:
Proposed owner and next action:
~~~

Báo cáo có giá trị khi **scope, thời gian và giới hạn** rõ ràng. Người đọc cần biết một kết quả “0 vi phạm” là do đã kiểm tra toàn bộ phạm vi hay do dữ liệu không đầy đủ.

## 14. Case study: kiểm kê production trước kỳ kiểm toán

**Bối cảnh giả định:** doanh nghiệp có 60 project trong ba folder **commerce**, **data** và **shared-platform**. Ứng dụng thanh toán chạy Cloud Run, GKE, Cloud SQL, Cloud Storage và một số VM Compute Engine. Nhóm bảo mật cần báo cáo:

- Mọi production resource có chủ sở hữu rõ ràng.
- Không có role Owner hoặc public binding ngoài trường hợp được duyệt.
- Workload dữ liệu nhạy cảm nằm trong vùng được cho phép.
- Có bằng chứng thay đổi IAM và cấu hình quan trọng.
- Tài nguyên dev tạm thời quá hạn được rà soát.

### 14.1. Thiết kế kiểm kê

~~~mermaid
flowchart TD
    O["Organization scope"] --> SEARCH["Search resources + IAM bindings"]
    SEARCH --> SNAP["Export snapshot GCS / BigQuery"]
    FEED["Feeds thay đổi"] --> PUB["Pub/Sub"]
    PUB --> CHECK["Cloud Run rule checker"]
    SNAP --> RULES["Kiểm tra label/location/IAM"]
    CHECK --> TICKET["Ticket và cảnh báo có owner"]
    RULES --> TICKET
    LOG["Audit Logs + IaC + exceptions"] --> TICKET
    TICKET --> VERIFY["Xác minh trực tiếp + sửa qua PR"]
~~~

**Ngày đầu:** cấp quyền đọc phạm vi phù hợp, kiểm kê resources/policies, xuất snapshot và phân loại asset theo project/loại dịch vụ.

**Hàng ngày:** tiêu thụ feed về thay đổi IAM/tài nguyên hỗ trợ, tạo alert khi có binding nhạy cảm hoặc resource mới thiếu owner; xác minh bằng trạng thái hiện tại trước khi hành động.

**Hàng tuần:** so sánh snapshot, kiểm tra IAM/vị trí/metadata, liên hệ owners để xử lý trường hợp sai lệch và quản lý exception.

**Trước kỳ kiểm toán:** lưu scope, timestamp, asset types, kết quả PASS/FAIL/UNKNOWN, bằng chứng audit logs, PR, ticket và trạng thái khắc phục.

### 14.2. Ba tình huống cần suy luận

**A — Không thấy VM vừa tạo.** Cần kiểm tra eventual consistency, quyền/scope và Compute Engine API. Không kết luận VM không tồn tại chỉ từ một lần tìm.

**B — Tìm thấy roles/owner ở folder cha.** Cần đánh giá kế thừa xuống project và quyền hiệu lực. Chỉ đọc binding trực tiếp tại project có thể bỏ sót.

**C — Số asset giảm 20 so với hôm qua.** Trước khi ghi nhận 20 tài nguyên bị xóa, phải so độ đầy đủ snapshot, quyền scanner, schema và bộ lọc.

### 14.3. Bước cải tiến bền vững

Các lỗi lặp lại nên được khắc phục từ **template Terraform, pipeline, IAM policy, Organization Policy và quy ước metadata** thay vì sửa tay từng tài nguyên. CAI cung cấp tín hiệu phát hiện và kiểm chứng; nguồn chuẩn quản trị phải được duy trì bởi nhóm sở hữu hệ thống.

## 15. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “CAI phản ánh mọi thứ ngay lập tức.” | Dữ liệu hiện tại có eventual consistency. |
| “CAI history lưu vô hạn.” | Chỉ truy xuất được khoảng 35 ngày theo khả năng API; cần snapshot dài hạn riêng. |
| “Search trả 0 nghĩa là không có tài nguyên.” | Có thể sai scope, thiếu quyền, lọc/giới hạn hoặc chưa index. |
| “CAI sao lưu toàn bộ data trong bucket/database.” | CAI kiểm kê metadata được hỗ trợ, không thay thế backup. |
| “Search IAM là effective IAM analyzer hoàn chỉnh.” | Còn inheritance, groups, conditions, deny và các ràng buộc khác. |
| “Tăng số asset là chi phí sẽ tăng cùng tỷ lệ.” | Chi phí phụ thuộc SKU, mức sử dụng, duration, storage, network và discounts. |
| “Feed theo dõi mọi object event trong bucket.” | Feed gắn với metadata asset được hỗ trợ, không phải mọi thao tác dữ liệu. |
| “Asset count giảm chứng minh asset bị xóa.” | Phải kiểm tra dữ liệu, quyền, schema, filters và API đích. |
| “Mọi loại resource có labels và payload giống nhau.” | Schema và khả năng CAI khác theo asset type. |
| “QueryAssets SQL sẵn có ở mọi project.” | Phụ thuộc tier/tính năng và quyền. |
| “Có một báo cáo CAI là hoàn thành kiểm toán.” | Cần bằng chứng, ngoại lệ, audit log, owner và kiểm tra hiệu lực. |
| “Phát hiện drift là phải tự rollback ngay.” | Nhiều thay đổi hợp lệ; cần xác minh nguồn chuẩn và tác động. |

## 16. Tài liệu tham khảo chính thức

- [Cloud Asset Inventory overview](https://docs.cloud.google.com/asset-inventory/docs/asset-inventory-overview)
- [Supported asset types](https://docs.cloud.google.com/asset-inventory/docs/asset-types)
- [Roles and permissions](https://docs.cloud.google.com/asset-inventory/docs/roles-permissions)
- [Search resources — gcloud reference](https://docs.cloud.google.com/sdk/gcloud/reference/asset/search-all-resources)
- [Search IAM allow policies — gcloud reference](https://docs.cloud.google.com/sdk/gcloud/reference/asset/search-all-iam-policies)
- [List assets — gcloud reference](https://docs.cloud.google.com/sdk/gcloud/reference/asset/list)
- [Get asset histories](https://docs.cloud.google.com/asset-inventory/docs/get-asset-history)
- [Export asset metadata to BigQuery](https://docs.cloud.google.com/asset-inventory/docs/export-bigquery)
- [Monitor asset changes with Pub/Sub](https://docs.cloud.google.com/asset-inventory/docs/monitor-asset-changes)
- [Query assets with SQL](https://docs.cloud.google.com/asset-inventory/docs/query-assets-with-sql)

Tính năng, asset type, thời gian lịch sử, quyền và cú pháp có thể thay đổi. Khi thiết kế production, xác minh với tài liệu và cấu hình hiện tại của Google Cloud organization.

---

**Kết nối với lộ trình CLOUD_PROVIDERS_GCP:** kiến thức về **organization, folder, project, IAM và VPC** giúp xác định phạm vi cần kiểm kê. Các bài về **Compute Engine, GKE, Cloud Run, lưu trữ và database** cung cấp những loại resource cần quan sát. **Cloud Asset Inventory**, kết hợp **audit logs, IaC, CI/CD, Billing, Monitoring và Security Command Center**, giúp biến quản trị hạ tầng thành một quy trình lặp lại: **thu thập trạng thái → xác định sai lệch → giao đúng chủ sở hữu → sửa đổi có kiểm soát → xác minh kết quả**.

