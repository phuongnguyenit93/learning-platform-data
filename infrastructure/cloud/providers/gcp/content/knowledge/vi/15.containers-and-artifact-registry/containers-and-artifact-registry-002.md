# Artifact Registry repositories và định dạng artifact trên Google Cloud

> **Chương:** Container và Artifact Registry  
> **Mô-đun:** **CLOUD_PROVIDERS_GCP** — Khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

Một nhóm phát triển Java có thể tạo ra **container image** để chạy trên GKE hoặc Cloud Run, **JAR** để các dự án Maven/Gradle khác sử dụng, và một gói cấu hình để phát hành cùng ứng dụng. Những artifact này không nên chỉ nằm trên laptop của lập trình viên hay ở một thư mục chung thiếu phiên bản, quyền và khả năng truy vết.

**Artifact Registry** là dịch vụ Google Cloud để quản lý **artifact đã đóng gói**: container images, language packages, OS packages và những tệp/gói phiên bản khác. Artifact Registry giúp tổ chức quản lý nơi lưu trữ, định dạng, định danh/version, phân quyền đọc/ghi, nguồn dependency, quét lỗ hổng và chính sách dọn dẹp. Bài này tập trung vào **repository và artifact formats**, sau đó nối chúng vào quy trình build, deploy và bảo mật của module **CLOUD_PROVIDERS_GCP**.

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **repository, package, version, tag, digest, artifact file** và **image manifest**.
2. Chọn đúng **định dạng repository** cho Docker/OCI, Maven, npm, Python, Go, Debian Apt, RPM Yum/DNF, Generic và các loại artifact được hỗ trợ.
3. So sánh **standard, remote, virtual** repositories và giải thích trường hợp connector (Preview).
4. Thiết kế tên, location, project, quyền IAM, encryption, retention và cleanup policy theo môi trường.
5. Tạo một **Docker standard repository**, xác thực Docker, tag/push/pull image và đọc metadata bằng gcloud.
6. Cấu hình cách tiếp cận Maven/Gradle, Python, npm và Generic artifacts mà không nhúng credential dài hạn vào mã nguồn.
7. Phân biệt **mutable tags** với **digest bất biến**, xây dựng pipeline phát hành có thể tái tạo và rollback.
8. Phân tích phụ thuộc remote/upstream, nguy cơ **dependency confusion**, lỗ hổng phần mềm, truy cập cross-project và chi phí.
9. Xử lý lỗi 401/403, tag không tìm thấy, sai location, quota, upstream outage và cleanup xóa nhầm phiên bản.

## 1. Artifact Registry giải quyết vấn đề gì?

Một artifact là **đầu ra có thể phân phối của quy trình xây dựng hoặc đóng gói**, ví dụ:

- Image **checkout-api** gồm Java runtime, JAR và cấu hình mặc định.
- Package **com.example:payment-common:1.8.0** dùng trong Maven hoặc Gradle.
- Package npm **@commerce/ui-kit@2.2.0** của đội frontend.
- Python wheel **risk_scoring-1.3.0-py3-none-any.whl**.
- Go module **example.com/team/ledger**.
- Debian **.deb**, RPM **.rpm** hoặc pipeline template.
- Gói Generic gồm file ZIP, YAML hoặc binary được đánh version.

Một artifact được quản lý đúng cách phải có:

| Câu hỏi | Thành phần trả lời |
|---|---|
| Lưu ở đâu? | Project, location, repository, format |
| Đây là phần mềm gì? | Package/image name |
| Phiên bản chính xác nào? | Version hoặc immutable image digest |
| Ai tạo và từ commit nào? | CI/CD, build provenance, metadata |
| Ai được đọc/ghi/xóa? | IAM roles của repository/project |
| Có vấn đề bảo mật không? | Vulnerability analysis, SBOM, policy |
| Khi nào hết hạn giữ? | Retention và cleanup policies |
| Workload nào đang dùng nó? | Deployment manifests, Cloud Run revisions, GKE workloads, VM startup |

**Artifact Registry là kho phân phối artifact, không phải CI server và không phải orchestrator.** Nó không tự build Docker image hay triển khai service; Cloud Build/GitHub Actions/Jenkins xây artifact, còn Cloud Run/GKE/Compute Engine lấy artifact để chạy. Cần kết hợp các dịch vụ này để tạo pipeline phát hành.

~~~mermaid
flowchart LR
    GIT["Git source"] --> CI["CI: build + test"]
    CI --> SCAN["Kiểm tra dependency / image"]
    SCAN --> AR["Artifact Registry repository"]
    AR --> RUN["Cloud Run"]
    AR --> GKE["GKE"]
    AR --> VM["Compute Engine"]
    AR --> MVN["Maven/Gradle consumers"]
    LOG["Provenance, SBOM, logs"] -. "Gắn với artifact" .-> AR
~~~

### 1.1. Repository không phải một thư mục Cloud Storage tự quản lý

Artifact Registry có API và giao thức registry/package manager riêng. Một Docker client dùng Docker Registry API, Maven tìm tọa độ **groupId/artifactId/version**, npm truy vấn package metadata, trong khi Generic artifact dùng các thao tác dành cho package/version/file.

Không nên tạo một Cloud Storage bucket rồi khẳng định bucket đó là Artifact Registry repository. Cloud Storage phù hợp cho object/datasets/backups; Artifact Registry thêm **định dạng package, version, IAM, tooling và quản trị artifacts**.

## 2. Mô hình dữ liệu: repository, package, version, tag và file

~~~mermaid
flowchart TD
    P["Project: commerce-build"] --> L["Location: asia-southeast1"]
    L --> R["Repository: checkout-images\nFormat: Docker; mode: Standard"]
    R --> PKG["Package/image: checkout-api"]
    PKG --> V1["Version: sha256:AAA..."]
    PKG --> V2["Version: sha256:BBB..."]
    V1 --> T1["Tag: 1.2.0"]
    V2 --> T2["Tag: 1.3.0"]
    V2 --> T3["Tag: stable"]
    V2 --> B["Manifest/layers/metadata"]
~~~

Mối quan hệ tổng quát:

- **Project**: ranh giới quản trị, billing và IAM.
- **Location**: region hoặc multi-region hỗ trợ, ảnh hưởng vị trí lưu, latency và lưu lượng.
- **Repository**: kho với **một artifact format** và một repository mode; có IAM, cleanup, encryption.
- **Package**: tên logical của artifact, chẳng hạn tên image hoặc module.
- **Version**: một bản nội dung cụ thể được đóng gói hoặc phát hành.
- **Tag**: tên tham chiếu thuận tiện cho một version ở các định dạng có hỗ trợ tags.
- **File/manifest/blob**: nội dung vật lý và metadata thuộc version.

Không phải mọi format dùng tag như Docker. Với Maven, version chủ yếu là chuỗi như **1.8.0**; với Generic, version là định danh rõ ràng của package; với Docker, version thực tế có thể được tham chiếu bằng **digest sha256**.

### 2.1. Repository name và fully qualified path

Đối với Docker/OCI, quy tắc đường dẫn phổ biến:

~~~text
LOCATION-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE:TAG
LOCATION-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE@sha256:DIGEST

Ví dụ:
asia-southeast1-docker.pkg.dev/commerce-build/checkout-images/checkout-api:1.3.0
~~~

Phân biệt:

| Thành phần | Giá trị ví dụ | Lưu ý |
|---|---|---|
| LOCATION | asia-southeast1 | Phải tồn tại và hỗ trợ định dạng |
| PROJECT_ID | commerce-build | Project chứa repository, không nhất thiết project triển khai |
| REPOSITORY | checkout-images | Tên duy nhất trong project + location |
| IMAGE | checkout-api | Có thể chứa đường dẫn con |
| TAG | 1.3.0 | Mặc định có thể thay đổi nếu không bật immutable tags |
| DIGEST | sha256:... | Định danh nội dung image manifest |

**Không nhầm project triển khai với project lưu repository.** Một Cloud Run service ở project **commerce-prod** có thể dùng image từ repository ở **commerce-build** nếu quyền đọc cross-project đã được cấp chính xác.

### 2.2. Container image khác container đang chạy

- **Image**: dữ liệu đóng gói các layer, filesystem và metadata.
- **Container instance**: tiến trình được runtime khởi chạy từ image.
- **Repository**: nơi lưu image.
- **Deployment**: khai báo image nào được chạy, tài nguyên, biến môi trường, secret, network và autoscaling.

Sửa code Java nhưng không build/push phiên bản mới thì Artifact Registry không tự cập nhật image. Push image mới cũng **không mặc nhiên** thay đổi tất cả revision hoặc Pod đang chạy; cần quy trình deployment cụ thể.

## 3. Artifact formats được hỗ trợ

Một repository standard thường chọn **một** format khi tạo. Artifact Registry hỗ trợ các nhóm sau, nhưng khả năng của từng format và giai đoạn sản phẩm có thể khác nhau.

| Format | Artifact/manager | Sử dụng điển hình |
|---|---|---|
| **Docker** | Docker/OCI images, Helm charts đóng gói OCI | Cloud Run, GKE, VM chạy container |
| **Maven** | JAR, POM, Java libraries; Maven/Gradle | Thư viện Java nội bộ |
| **npm** | Node.js packages | Frontend/component libraries |
| **Python** | Python wheels và source distributions | Python services, tooling, ML dependencies |
| **Go** | Go modules | Dịch vụ/backend Go |
| **Apt** | Debian packages (.deb), apt | Phân phối OS packages cho Debian/Ubuntu theo hỗ trợ |
| **Yum** | RPM packages (.rpm), yum/dnf | RHEL-compatible Linux |
| **GooGet** | Windows GooGet packages | Phân phối một số gói Windows |
| **Kubeflow Pipelines (KFP)** | Pipeline templates | Tái sử dụng workflow ML/Vertex AI |
| **Generic** | Tệp bất kỳ với package và version | ZIP, binary, config/artifact không có package manager riêng |
| **Ruby (Preview)** | Ruby gems / Bundler | Thư viện Ruby |
| **Conda (Preview)** | Conda packages | Dependencies môi trường Python/data science |

**Preview/pre-GA** có nghĩa là phạm vi hỗ trợ và điều kiện vận hành có thể hạn chế hoặc thay đổi; không coi mọi tính năng Preview có SLA, support và khả năng tương đương sản phẩm GA. Không mặc định tất cả formats hỗ trợ **remote** hoặc **virtual** repositories.

### 3.1. Docker repository cũng lưu Helm OCI charts

Artifact Registry có thể lưu **Helm chart đóng gói OCI** trong một repository định dạng **Docker**. Đây không phải repository kiểu Maven hay một format Helm riêng trong bảng format chính.

Ví dụ một Helm client có thể dùng registry hostname **LOCATION-docker.pkg.dev** sau khi được xác thực, thực hiện push/pull chart OCI với cú pháp Helm tương ứng. Một chart được lưu trong Artifact Registry **không tự động được triển khai vào GKE**; vẫn cần Helm upgrade/install hoặc hệ thống GitOps.

### 3.2. Generic không phải format mặc định của mọi package manager

**Generic artifacts** phù hợp khi bản build không tuân theo Docker/Maven/npm/Python/Go. Ví dụ zip có chứa file cấu hình, binary CLI nội bộ hoặc gói dữ liệu định dạng tùy chỉnh. Generic package/version bất biến theo cơ chế upload; không dùng nó như bucket cho phép ghi đè một file tên **latest.zip** tùy ý.

Nếu đã có ecosystem manager như Maven hoặc npm, nên dùng format chuyên dụng để nhận được cơ chế dependency resolution và metadata đúng chuẩn.

### 3.3. Phân biệt định dạng file với format của repository

Ví dụ một JAR có thể:

- Là một **Maven package** với tọa độ group/artifact/version.
- Là một file nằm trong **Generic artifact**.

Hai cách lưu có thể chứa cùng bytes, nhưng Maven/Gradle **không tự suy dependency metadata** nếu ta chỉ ném JAR vào Generic repository. Ngược lại, Docker repository không phải nơi dùng **pip install** trực tiếp.

## 4. Repository modes: standard, remote, virtual và connector

~~~mermaid
flowchart LR
    BUILD["Build pipeline"] -->|"Publish trực tiếp"| STANDARD["Standard\nprivate artifacts"]
    PUB["Public registries\nDocker Hub / Maven Central / PyPI"] --> REMOTE["Remote\nproxy + cache"]
    STANDARD --> VIRTUAL["Virtual\nsingle access point"]
    REMOTE --> VIRTUAL
    CLIENT["Build clients / runtimes"] --> VIRTUAL
    CLIENT2["Direct consumers"] --> STANDARD
    CLIENT3["Direct consumers"] --> REMOTE
~~~

| Mode | Bản chất | Có lưu/cache? | Dùng khi nào? |
|---|---|---|---|
| **Standard** | Repository gốc để publish/upload artifacts trực tiếp | Có | Phát hành image/JAR/package nội bộ |
| **Remote** | Proxy đến upstream, **cache artifacts** khi có request | Cache bản lấy từ upstream | Kiểm soát truy cập dependency ngoài, hạn chế tải lặp |
| **Virtual** | Endpoint tổng hợp nhiều upstream standard/remote repositories theo priority | Không phải kho publish trực tiếp | Client muốn một registry endpoint với thứ tự nguồn rõ |
| **Connector (Preview)** | Proxy upstream nhưng **không cache** | Không | Phải quan sát upstream trực tiếp hoặc không được phép lưu cache |

**Tính năng connector** đang ở giai đoạn Preview. Nó không phải một dạng standard repository và không nên coi tương đương remote (vì remote có caching).

### 4.1. Standard repository

Đặc điểm:

- Upload/push artifact vào repository mà đội sở hữu kiểm soát.
- Phân quyền **reader/writer/repository admin** trực tiếp.
- Chọn một format như docker, maven, python hoặc generic.
- Có thể bật **immutable Docker tags**, cleanup policies, CMEK và quét lỗ hổng tùy khả năng.
- Phù hợp sản phẩm do chính doanh nghiệp build hoặc artifacts được promote qua môi trường.

Ví dụ: pipeline checkout build image, push **checkout-api:1.3.0** vào standard Docker repository; Cloud Run lấy image từ đó để deploy.

### 4.2. Remote repository

Remote repository dùng một upstream được hỗ trợ, ví dụ:

- Docker Hub hoặc registry Docker bên ngoài.
- Maven Central.
- npmjs.
- Python Package Index (PyPI).
- Go public module proxy.
- Một số nguồn OS packages (Preview) hoặc custom/upstream private theo format hỗ trợ.

Khi client yêu cầu package version chưa có trong cache, Artifact Registry có thể tải từ upstream và cache lại. Lần sau dùng bản đã cache theo cơ chế sản phẩm. Upstream phải phù hợp điều kiện **public HTTPS/internet reachability**, quyền xác thực nếu cần và format supported. Không mặc định truy cập được registry chỉ nằm trong VPC private hay site on-premises không có public endpoint.

**Remote không bảo đảm upstream luôn khả dụng hoặc mọi package public đều an toàn.** Cần xét rate limit, license, dependency provenance, vulnerability/poisoning và version pinning. Nếu upstream thay đổi hoặc cache bị thiếu, build vẫn có thể thất bại.

### 4.3. Virtual repository

Virtual repository là **một địa chỉ truy cập cho nhiều upstream** gồm các standard và remote repositories cùng format được hỗ trợ. Có thể gán **priority** để điều khiển thứ tự tìm package. Ví dụ:

~~~text
Client Maven / Gradle
      |
      v
maven-unified (VIRTUAL)
      |
      +-- priority cao: maven-internal (STANDARD)
      |
      +-- priority thấp: maven-central-cache (REMOTE)
~~~

Khi cùng package/version xuất hiện ở cả internal và public source, cần chính sách ưu tiên tránh tải nhầm bản không được phê duyệt. Đối với format hỗ trợ virtual, đây là cách có thể giảm nguy cơ **dependency confusion** so với cấu hình manager tự quét các URL không có thứ tự rõ ràng.

**Virtual không phải điểm publish**. Pipeline phát hành phải ghi vào **standard repository**, còn consumers dùng virtual endpoint nếu chính sách cho phép.

### 4.4. Các mode không hỗ trợ giống nhau ở mọi format

Theo tài liệu hiện hành, virtual repository hỗ trợ **Docker, Go, Maven, npm, Python**; Apt/Yum ở **Private Preview** trong một số trường hợp. Remote có các upstream presets và custom sources khác nhau theo format. Không suy rằng GooGet, Generic hay Ruby Preview đều có đầy đủ các mode.

Khi thiết kế production, phải kiểm tra **supported formats for repository mode**, region và điều kiện tier. Một repository **không thể đơn giản chuyển Docker thành Maven** hoặc đổi mode chỉ bằng sửa tên: format/mode là quyết định cấu trúc ngay khi tạo.

## 5. Chọn location, project và naming convention

### 5.1. Location là lựa chọn kiến trúc

Artifact Registry cho phép tạo repositories ở **regional** và một số **multi-regional locations** được hỗ trợ. Các yếu tố quyết định:

- **Data residency:** artifact phải nằm ở quốc gia/vùng địa lý nào theo policy.
- **Latency/pull:** Cloud Run/GKE/Compute Engine chủ yếu chạy tại region nào.
- **Network transfer:** truy xuất image hoặc package qua vùng khác có thể phát sinh phí và tăng thời gian.
- **Khả năng phục hồi:** nếu hạ tầng cần chạy ở nhiều region, cần kế hoạch copy/replicate artifact thích hợp.
- **KMS:** nếu dùng CMEK, chọn key/location và quyền theo yêu cầu.
- **VPC Service Controls**, organization policy và giới hạn dịch vụ.

**Multi-region không đồng nghĩa tự có bản sao ở mọi region theo ý người dùng**. Cần xác minh location semantics và chiến lược dự phòng. Nếu artifact cần hiện diện độc lập ở hai vùng, hãy lập pipeline sao chép/promote và kiểm tra digest, thay vì giả định một URL Docker có thể dùng với mọi location prefix.

### 5.2. Phân tách project và repository theo quyền

Ví dụ doanh nghiệp có:

| Project | Repository | Format | Quyền/đặc điểm |
|---|---|---|---|
| commerce-build | checkout-images | Docker | CI writer, runtime prod reader |
| commerce-build | java-libs | Maven | Java build publisher, dev reader |
| platform-deps | maven-central-cache | Maven remote | Build consumers được kiểm soát |
| platform-deps | maven-unified | Maven virtual | Read endpoint cho build clients |
| tools-internal | scripts-bundles | Generic | Pipeline release nội bộ |
| commerce-prod | Không bắt buộc chứa repo | — | Chạy Cloud Run/GKE, pull cross-project |

Không nhất thiết phải tạo một repository riêng cho mỗi microservice; có thể dùng một repo cho nhóm image có chính sách giống nhau. Ngược lại, nếu hai nhóm có **khác biệt lớn về IAM/retention/CMEK**, tách repository thường làm giảm rủi ro.

### 5.3. Quy ước tên

Ví dụ đặt tên:

~~~text
Project: commerce-build
Location: asia-southeast1

Repository IDs:
- checkout-images
- java-shared-libs
- npm-internal
- python-internal
- generic-release-bundles

Docker image paths:
- checkout-api:1.3.0
- billing-worker:2026.11.19-commitsha
~~~

Ưu tiên tên dễ đọc, không đưa **credential, PII hoặc tên khách hàng nhạy cảm** vào repository description, image name hoặc tags. Metadata mô tả thường không được mã hóa theo cách bảo vệ secret, và có thể xuất hiện trong logs hoặc dashboard.

## 6. Preflight: quyền, API và môi trường CLI

Để làm các ví dụ gcloud/Docker bên dưới, cần:

1. Project được cấp quyền và có **Artifact Registry API** khả dụng.
2. Billing/quota phù hợp cho thao tác lưu trữ và truy xuất.
3. gcloud CLI, Docker client hoặc package manager được cài và đăng nhập đúng danh tính.
4. Repository location được hỗ trợ.
5. Quyền IAM đủ theo thao tác: **Reader** để pull, **Writer** để push, **Repository Administrator** để xóa artifacts và **Administrator** để tạo/quản lý repositories.
6. Không dùng production repository để thử tag/delete/cleanup khi chưa có review.
7. Phân biệt identity của **người dùng gcloud**, **Docker credential helper**, **CI service account** và **runtime service agent**.

### 6.1. Kiểm tra chỉ đọc

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
LOCATION="asia-southeast1"

gcloud auth list
gcloud config list
gcloud services list --enabled --project="$PROJECT_ID"

# Danh sách locations được Artifact Registry hỗ trợ.
gcloud artifacts locations list

# Liệt kê các repositories có thể xem trong project.
gcloud artifacts repositories list --project="$PROJECT_ID"

# Đọc metadata của repository đã tồn tại.
gcloud artifacts repositories describe "REPOSITORY_ID" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --format=yaml
~~~

Nếu người dùng thiếu quyền liệt kê repository, không tự suy rằng project không có repository. Một quyền chỉ cấp ở **repository** có thể đủ để truy cập đúng repo nhưng không cho phép liệt kê toàn project. Cần đối chiếu IAM và resource path, tránh “sửa” bằng cách cấp roles/owner.

## 7. Thực hành A — Tạo Docker standard repository

**Các lệnh trong phần này thay đổi tài nguyên Google Cloud và có thể phát sinh phí.** Chỉ chạy trong project học tập được phép; không tạo hoặc xóa repositories production để thử.

### 7.1. Chọn thông số lab

| Trường | Giá trị lab | Cần kiểm tra |
|---|---|---|
| Project | YOUR_PROJECT_ID | Có billing và quyền create repo |
| Location | asia-southeast1 | Được Artifact Registry hỗ trợ |
| Repository | app-images-lab | Chưa tồn tại trong project/location |
| Format | docker | Docker/OCI images |
| Mode | standard | CI có quyền push |
| Image name | checkout-api | Gồm đường dẫn optional |
| Tag | 1.0.0 | Version nhận diện build |
| Runtime | Cloud Run hoặc GKE ở project lab | Có quyền pull theo đúng identity |

### 7.2. Tạo repository

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
LOCATION="asia-southeast1"
REPOSITORY="app-images-lab"

# THAY ĐỔI — tạo standard Docker repository.
gcloud artifacts repositories create "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --repository-format=docker \
  --location="$LOCATION" \
  --description="Docker images for the training application"

# CHỈ ĐỌC — kiểm tra format, mode, location và encryption.
gcloud artifacts repositories describe "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --format=yaml
~~~

**Standard là mode mặc định** nếu không chọn remote/virtual. Nếu yêu cầu không thể thay đổi tags sau phát hành, cân nhắc cờ **--immutable-tags** khi tạo repository hoặc cập nhật cấu hình theo quyền và quy trình phù hợp. Trước khi bật, xem ảnh hưởng với pipeline hiện đang dùng tags lặp như **latest**, **staging**.

### 7.3. Chuẩn bị Docker client authentication

~~~bash
# CẬP NHẬT CẤU HÌNH CLIENT trên máy đang chạy Docker.
gcloud auth configure-docker "$LOCATION-docker.pkg.dev"
~~~

Lệnh cấu hình **Docker credential helper** cho hostname của Artifact Registry trong Docker config. Nó **không tự cấp IAM**. Người dùng phải có quyền push/pull tương ứng, ví dụ Writer cho push, Reader cho pull.

Docker thường tìm credentials ở **~/.docker/config.json** của user. Nếu dùng **sudo docker**, Docker có thể dùng config của root thay vì user; đây là nguyên nhân phổ biến của lỗi 401 ngay cả khi lệnh gcloud auth đã thành công.

Với automation, ưu tiên **Workload Identity Federation**, service account được đính kèm workload và token ngắn hạn. Không đưa JSON service account key hoặc Docker password dạng plain text vào Git.

### 7.4. Build và push image Java

Giả sử dự án Java đang có **Dockerfile** và đã build/test thành công. Ví dụ Dockerfile tối thiểu:

~~~dockerfile
# Ví dụ yêu cầu target/checkout-api.jar đã được tạo trước đó.
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/checkout-api.jar app.jar
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Lưu ý:

- Nên dùng **base image đã xác minh**, pin digest khi yêu cầu reproducibility.
- **USER không phải root** giúp giảm phạm vi tác động của lỗi ứng dụng.
- Tạo **.dockerignore** để không copy .git, credentials và tệp build không cần thiết.
- **EXPOSE** là metadata, không tự mở VPC firewall hoặc Cloud Run ingress.
- Trong production, CI cần chạy unit/integration tests, kiểm tra dependency và tạo provenance trước push.

Ví dụ lệnh:

~~~bash
# Giả định đang ở thư mục của một dự án Java với Dockerfile.
# mvn verify sẽ chạy các phase/test theo cấu hình của dự án.
mvn -B verify

IMAGE_BASE="$LOCATION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/checkout-api"
TAG="1.0.0"

# THAY ĐỔI trên Docker daemon local: build container image.
docker build -t "checkout-api:$TAG" .

# Tag image theo đường dẫn Artifact Registry.
docker tag "checkout-api:$TAG" "$IMAGE_BASE:$TAG"

# THAY ĐỔI trên Artifact Registry: upload image/layers.
docker push "$IMAGE_BASE:$TAG"
~~~

Không nên dùng **latest** làm identifier duy nhất của bản phát hành. Nếu lặp lại tag mà repository đang cho phép mutable tags, **latest** có thể trỏ sang digest khác mà người deploy không nhận ra. Một release nên có tag gắn với version/commit và lưu digest được trả về sau push.

### 7.5. Đọc lại image và digest

~~~bash
# CHỈ ĐỌC — danh sách image/package trong repo.
gcloud artifacts docker images list \
  "$LOCATION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY"

# CHỈ ĐỌC — xem các versions và tags của một image.
gcloud artifacts docker images list "$IMAGE_BASE" \
  --include-tags

# CHỈ ĐỌC/LOCAL DOWNLOAD — lấy đúng version để thử.
docker pull "$IMAGE_BASE:$TAG"
~~~

Một output có **DIGEST sha256:...** cho biết phiên bản nội dung cụ thể. Đối với deployment production yêu cầu reproducibility, cân nhắc **deploy bằng image@sha256:DIGEST** thay vì chỉ tag. Ví dụ:

~~~text
Tag có thể đổi (nếu repository không bật immutable tags):
asia-southeast1-docker.pkg.dev/commerce-build/checkout-images/checkout-api:stable

Tham chiếu nội dung cụ thể:
asia-southeast1-docker.pkg.dev/commerce-build/checkout-images/checkout-api@sha256:<FULL_DIGEST>
~~~

Không dùng chuỗi **sha256:<FULL_DIGEST>** nguyên văn làm image reference vì đây là placeholder. Digest phải lấy từ kết quả build/push/Artifact Registry của image thật.

### 7.6. Tag không giống digest

| Thuộc tính | Docker tag | Digest |
|---|---|---|
| Ví dụ | 1.3.0, stable | sha256:... |
| Định danh | Tên logical trỏ đến image version | Hash của image manifest |
| Có thể đổi điểm trỏ? | **Có**, nếu mutable | Digest không được đổi để chỉ content khác |
| Tiện cho con người? | Rất tiện | Dài, khó nhớ |
| Dùng để deploy chính xác? | Cần policy kiểm soát | Phù hợp hơn |
| Bảo đảm ứng dụng không lỗi? | Không | Không; vẫn cần scan/test/review |

**Immutable tags** là thiết lập **của Docker repository**. Khi bật, một tag không được trỏ lại sang digest khác và tagged images có những giới hạn xóa/đổi tag. Cần xây chiến lược cleanup và rollback tương thích: không push đè một tag đã tồn tại, hãy dùng release tag mới và digest đã kiểm chứng.

## 8. IAM cho repositories và pipeline phát hành

IAM quyết định ai được xem, tải xuống, upload hoặc xóa artifacts. Không nhầm khả năng **login gcloud** với quyền thực sự trên repository.

| Vai trò | Role ID | Quyền sử dụng điển hình |
|---|---|---|
| Artifact Registry Reader | **roles/artifactregistry.reader** | Xem metadata và pull/download |
| Artifact Registry Writer | **roles/artifactregistry.writer** | Đọc và publish/upload |
| Artifact Registry Repository Administrator | **roles/artifactregistry.repoAdmin** | Đọc, ghi và xóa artifacts |
| Artifact Registry Administrator | **roles/artifactregistry.admin** | Tạo/quản lý repositories và artifacts |

### 8.1. Cấp quyền ở repository hay project?

- **Repository-level IAM**: phù hợp khi checkout-ci chỉ được push vào **checkout-images**, không được sửa **java-libs**.
- **Project-level IAM**: phù hợp khi một service account thực sự cần quyền giống nhau với **mọi repository** trong project.
- **Cross-project IAM**: runtime ở project B pull từ repository ở project A; phải cấp role Reader trên **repository A** cho **principal thực sự thực hiện pull**.
- **Virtual repositories**: Reader có thể đọc các upstream qua virtual endpoint theo cơ chế của dịch vụ; cần xem phạm vi quyền được mở rộng.

Ví dụ nguyên tắc phân công:

~~~text
build/checkout-ci:
  Writer trên checkout-images
  Không có Admin project

deploy/production:
  Reader trên checkout-images
  Không có Writer

platform/registry-admin:
  Admin trên repository hoặc phạm vi được phê duyệt
  Có quyền chỉnh cleanup/CMEK/visibility phù hợp

developer:
  Reader repository cần dùng
  Writer chỉ ở repo dev nếu được cho phép
~~~

### 8.2. Ví dụ gcloud IAM binding (thay đổi thật)

~~~bash
# THAY ĐỔI IAM — chỉ thực hiện khi đúng principal và có approval.
READER_SERVICE_ACCOUNT="deployer@YOUR_RUNTIME_PROJECT.iam.gserviceaccount.com"

gcloud artifacts repositories add-iam-policy-binding "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --member="serviceAccount:$READER_SERVICE_ACCOUNT" \
  --role="roles/artifactregistry.reader"

# CHỈ ĐỌC — xác minh ai được gán quyền tại repository.
gcloud artifacts repositories get-iam-policy "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION"
~~~

Cẩn trọng: trong một số triển khai Cloud Run hoặc GKE cross-project, **identity kéo image** là **service agent hoặc node service account**, có thể **khác runtime service account** của container. Cần tra tài liệu sản phẩm/đường deploy cụ thể và kiểm tra principal thực hiện pull; đừng cấp Reader cho mọi service account theo phỏng đoán.

### 8.3. Xác thực ở máy trạm, CI và runtime

| Môi trường | Hướng triển khai |
|---|---|
| Developer laptop | gcloud user login, Docker credential helper, Maven/Gradle credential helper |
| Cloud Build | Xác định đúng build service account và quyền Writer/Reader |
| GitHub Actions/Jenkins ngoài GCP | Workload Identity Federation và service account impersonation phù hợp |
| GKE | Identity kéo image theo node/cluster và quyền Reader; workload IAM riêng |
| Cloud Run | Đường deploy/image pull và quyền service agent theo project; runtime identity không tự đồng nhất |
| Compute Engine | VM service account, scopes/cấu hình lịch sử và quyền repo cần thiết |

Tránh phát hành qua CI bằng **service account key JSON có thời hạn dài** nếu có thể dùng danh tính ngắn hạn. Nếu key buộc phải dùng, phải đặt ngoài repo, kiểm soát Secret Manager, rotation và audit.

### 8.4. Quy tắc tách người xây và người triển khai

Build pipeline cần **Writer** và không nhất thiết cần **Repository Administrator**. Runtime chỉ cần **Reader**. Người có quyền **Delete** hoặc bật/tắt immutable tags/cleanup là nhóm quản trị registry. Phân tách này giúp giảm nguy cơ:

- Lộ token của runtime dẫn tới chèn image độc hại.
- Một CI job lỗi xóa toàn bộ release artifacts.
- Một developer vô tình ghi đè tag của production.
- Cleanup policy chưa thử xóa artifact còn đang được triển khai.

## 9. Maven/Gradle repository dành cho Java

Với module Java, Artifact Registry **Maven format** hữu ích để phát hành thư viện chung dưới tọa độ **groupId:artifactId:version**.

### 9.1. Mô hình package Java

~~~text
Project: commerce-build
Repository: java-shared-libs
Format: maven
Location: asia-southeast1

Package coordinates:
com.example.platform:payment-sdk:1.8.0

Maven repository endpoint:
artifactregistry://asia-southeast1-maven.pkg.dev/commerce-build/java-shared-libs
~~~

Một Maven package gồm POM metadata, JAR, có thể sources/javadoc và các file liên quan. Maven/Gradle dùng metadata để giải quyết dependencies/transitive dependencies; đừng dùng Generic repository nếu mục tiêu chính là **mvn dependency resolution**.

### 9.2. Tạo Maven repository

~~~bash
# THAY ĐỔI — tạo Maven standard repository.
gcloud artifacts repositories create "java-shared-libs" \
  --project="$PROJECT_ID" \
  --repository-format=maven \
  --location="$LOCATION" \
  --description="Java libraries for internal builds"

# CHỈ ĐỌC — in cấu hình Maven tương ứng với repo.
gcloud artifacts print-settings mvn \
  --project="$PROJECT_ID" \
  --repository="java-shared-libs" \
  --location="$LOCATION"

# CHỈ ĐỌC — in cấu hình Gradle tương ứng.
gcloud artifacts print-settings gradle \
  --project="$PROJECT_ID" \
  --repository="java-shared-libs" \
  --location="$LOCATION"
~~~

Kết quả **print-settings** hướng dẫn cách cấu hình Maven **distributionManagement/repositories** hoặc Gradle **publishing/repositories** và các credential helpers. Hãy dùng output từ CLI theo phiên bản được cài, thay vì chép nguyên mọi số phiên bản plugin cố định từ tutorial.

### 9.3. Maven và Gradle authentication

Artifact Registry hỗ trợ **Maven wagon** và **Gradle plugin** để lấy credentials theo Application Default Credentials (ADC)/gcloud khi phù hợp. Nguyên tắc:

- Developer đăng nhập bằng tài khoản cá nhân được cấp quyền Reader/Writer tương ứng.
- CI dùng service account có quyền rõ ràng, ưu tiên credentials ngắn hạn.
- Không đưa password/key JSON vào **pom.xml, settings.xml, build.gradle** rồi commit.
- Ghi rõ repository ID/location và package version policy.
- Release artifact nên được phát hành từ một build đã qua test và có provenance.

### 9.4. SNAPSHOT và RELEASE có nghĩa gì?

Maven **1.9.0-SNAPSHOT** là bản đang phát triển, có thể được build nhiều lần. Maven **1.9.0** thường là release. Khi tạo Maven repository, có thể cấu hình **version policy** tương ứng theo điều kiện sản phẩm; remote Maven repositories có giới hạn về snapshot/release policy.

Tổ chức cần:

- Tách release và snapshot nếu yêu cầu IAM/retention khác nhau.
- Không coi SNAPSHOT là artifact ổn định để deploy production.
- Tránh overwrite release version khi quy trình yêu cầu immutability.
- Dọn SNAPSHOT cũ theo cleanup policy đã thử và không làm mất dependency đang dùng.

### 9.5. Kotlin/Gradle không đổi format

Dự án Java/Kotlin xây bằng Gradle vẫn có thể publish **Maven-compatible artifacts** vào repository format **maven**. Format được chọn theo giao thức phân phối artifact, không nhất thiết theo ngôn ngữ của mã nguồn.

## 10. npm, Python, Go và Generic artifacts

### 10.1. npm repository

Node.js package có tên và version như **@commerce/ui-kit@2.2.0**. Có thể tạo standard npm repo:

~~~bash
gcloud artifacts repositories create "npm-internal" \
  --project="$PROJECT_ID" \
  --repository-format=npm \
  --location="$LOCATION"

# CHỈ ĐỌC — lấy hướng dẫn cấu hình .npmrc / scope.
gcloud artifacts print-settings npm \
  --project="$PROJECT_ID" \
  --repository="npm-internal" \
  --location="$LOCATION" \
  --scope="@commerce"
~~~

Sau khi cấu hình authentication và **package.json** đúng, có thể chạy **npm publish** vào repository được phép. Không đăng token thật trong **.npmrc** được commit lên Git. Tránh định nghĩa nhiều registry URLs tùy ý khiến dependency private bị lấy nhầm từ public registry.

### 10.2. Python repository

Python format phù hợp cho wheels và source distributions. Công cụ **pip**, **twine** và keyring backend có thể được cấu hình để install/upload.

~~~bash
gcloud artifacts repositories create "python-internal" \
  --project="$PROJECT_ID" \
  --repository-format=python \
  --location="$LOCATION"

# CHỈ ĐỌC — hướng dẫn index-url, twine và auth.
gcloud artifacts print-settings python \
  --project="$PROJECT_ID" \
  --repository="python-internal" \
  --location="$LOCATION"
~~~

Đối với pip, địa chỉ private simple index có dạng:

~~~text
https://LOCATION-python.pkg.dev/PROJECT_ID/REPOSITORY/simple/
~~~

Khi dùng **keyrings.google-artifactregistry-auth** và các helpers phù hợp, có thể tránh nhúng mật khẩu vào pip config. Theo khuyến nghị của Google, khi cần private + public dependencies, có thể dùng **virtual repository** thay vì đặt private index và PyPI song song trong **extra-index-url**, vì pip không bắt buộc ưu tiên private index; kẻ xấu có thể đăng public package trùng tên phiên bản cao hơn (**dependency confusion**).

### 10.3. Go repository

Go module có cấu trúc module path/version và dùng **GOPROXY**. Ví dụ:

~~~bash
gcloud artifacts repositories create "go-internal" \
  --project="$PROJECT_ID" \
  --repository-format=go \
  --location="$LOCATION"

# CHỈ ĐỌC — thông tin module repository.
gcloud artifacts repositories describe "go-internal" \
  --project="$PROJECT_ID" \
  --location="$LOCATION"
~~~

Để tiêu thụ private modules, cần cấu hình **GOPROXY**, credentials helper và **GONOSUMDB** phù hợp với module path private. Cẩn trọng với cấu hình **GOPROXY** có fallback tới public proxy: có thể gây lộ tên private module hoặc tải từ nguồn không dự định. Với tổ chức yêu cầu kiểm soát hoàn toàn, ưu tiên proxy/virtual endpoint và policy được phê duyệt.

### 10.4. Generic repository và upload file có version

~~~bash
gcloud artifacts repositories create "generic-bundles" \
  --project="$PROJECT_ID" \
  --repository-format=generic \
  --location="$LOCATION"

# THAY ĐỔI — chỉ dùng file đã xây và được duyệt.
gcloud artifacts generic upload \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --repository="generic-bundles" \
  --package="deploy-manifests" \
  --version="1.0.0" \
  --source="./deploy-manifests.zip"

# CHỈ ĐỌC — xác minh file trong repo.
gcloud artifacts files list \
  --project="$PROJECT_ID" \
  --repository="generic-bundles" \
  --location="$LOCATION"
~~~

Generic package/version có cơ chế **version bất biến**, không thể ghi đè một phiên bản đã tồn tại. Nếu cần bản mới, xuất bản với **version mới**. Không dùng Generic như nơi cập nhật file với cùng version liên tục.

### 10.5. Apt/Yum, GooGet, KFP, Ruby và Conda

- **Apt** dùng cho Debian packages, cần cấu hình apt source và xác thực package manager đúng hướng dẫn.
- **Yum/DNF** dùng cho RPM packages, cần cấu hình repository và chữ ký/nguồn package phù hợp.
- **GooGet** áp dụng cho một số Windows packages.
- **KFP** lưu Kubeflow pipeline templates, dùng trong workflow ML/Vertex AI phù hợp.
- **Ruby gems và Conda packages** đang có khả năng **Preview** theo tài liệu định dạng được hỗ trợ.

Không đưa các lệnh apt/yum hoặc pip **không kiểm soát nguồn** vào startup script production. Cần pin version, xác thực repository, kiểm tra signature/checksum và dự phòng khi upstream không khả dụng.

## 11. Thực hành B — Remote và virtual repository cho dependencies

Đây là phần nâng cao. Muốn dùng remote/virtual, phải xác định rõ **upstream sources, location, format, IAM và quy tắc ưu tiên**. Các lệnh dưới đây có thể tạo tài nguyên thật, không chạy vào project production khi chưa được duyệt.

### 11.1. Remote repository lấy dependency từ Maven Central

Ví dụ nhóm Java muốn cache những package public từ Maven Central để tất cả build clients truy cập qua Artifact Registry.

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
LOCATION="asia-southeast1"

# THAY ĐỔI — tạo remote Maven repository, dùng preset upstream.
gcloud artifacts repositories create "maven-central-remote" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --repository-format=maven \
  --mode=remote-repository \
  --remote-mvn-repo=MAVEN-CENTRAL \
  --description="Cache of Maven Central packages"

# CHỈ ĐỌC — xác minh mode, format, remote config.
gcloud artifacts repositories describe "maven-central-remote" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --format=yaml
~~~

Đây không phải một Maven standard repository để build pipeline **publish JAR nội bộ** vào. Nó làm **proxy/cache upstream** theo chính sách. Nếu một package chưa có trong cache và Maven Central không khả dụng, fetch có thể thất bại. Cần kiểm tra dependency pinning và kế hoạch phục hồi build.

### 11.2. Remote Docker repository cho base images

Ví dụ một team muốn tải base images từ Docker Hub qua Artifact Registry, tránh client truy cập trực tiếp ra ngoài.

~~~bash
# THAY ĐỔI — tạo remote Docker repository.
gcloud artifacts repositories create "dockerhub-remote" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --repository-format=docker \
  --mode=remote-repository \
  --remote-docker-repo=DOCKER-HUB \
  --description="Docker Hub proxy cache"
~~~

Tùy policy và rate limits của Docker Hub, có thể cần **upstream credentials** lưu trong **Secret Manager**. Không truyền password/token raw vào shell command hoặc ghi trong tài liệu. Remote repositories cũng có giới hạn kết nối upstream private: những upstream không có public HTTPS endpoint hoặc chỉ nằm trong VPC/on-premises không mặc nhiên được proxy trực tiếp.

**Lưu ý:** khi dùng remote image, client cần tham chiếu đúng **remote repository path**, không phải trực tiếp **docker.io**. Nếu Dockerfile vẫn dùng **FROM docker.io/library/...** mà không có cơ chế rewrite/mirror tương ứng, bước build có thể tiếp tục truy cập Docker Hub trực tiếp, bỏ qua cache doanh nghiệp.

### 11.3. Virtual repository với upstream priorities

Giả sử cùng location/format có:

- **java-shared-libs** — standard Maven repository chứa packages nội bộ.
- **maven-central-remote** — remote Maven repository cache Maven Central.

Tạo virtual repository **maven-unified** là cách cung cấp một endpoint cho Gradle/Maven consumers.

~~~json
[
  {
    "id": "internal",
    "repository": "projects/YOUR_PROJECT_ID/locations/asia-southeast1/repositories/java-shared-libs",
    "priority": 100
  },
  {
    "id": "public-cache",
    "repository": "projects/YOUR_PROJECT_ID/locations/asia-southeast1/repositories/maven-central-remote",
    "priority": 50
  }
]
~~~

Lưu JSON này thành **upstream-policies.json** trong thư mục làm việc của quy trình triển khai khi đã được duyệt. Đây là tệp cấu hình **ví dụ trong bài học**, không phải yêu cầu người học tự thay đổi repo làm việc của module học.

~~~bash
# THAY ĐỔI — tạo virtual repository với JSON đã review.
gcloud artifacts repositories create "maven-unified" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --repository-format=maven \
  --mode=virtual-repository \
  --upstream-policy-file="upstream-policies.json" \
  --description="Unified Maven dependencies"

# CHỈ ĐỌC — xác minh upstream policies.
gcloud artifacts repositories describe "maven-unified" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --format=yaml
~~~

**Priority trong virtual repository: số LỚN hơn ưu tiên cao hơn.** Trong ví dụ **100** được tìm trước **50**. Đừng nhầm với **VPC firewall rule priority** nơi **số nhỏ hơn** ưu tiên cao hơn. Nếu hai upstream có cùng priority và cùng chứa package/version, server có thể chọn một trong hai.

**Điều kiện quan trọng:** upstream của virtual phải có **cùng format** và **cùng location** với virtual repository, nhưng có thể nằm ở project khác nếu IAM và chính sách cho phép. Virtual có thể dùng upstream standard, remote hoặc virtual theo điều kiện sản phẩm.

### 11.4. Phân biệt priority nguồn với lựa chọn version

Khi yêu cầu một **phiên bản cụ thể** có ở nhiều upstream, virtual có thể ưu tiên source có priority cao hơn. Nhưng khi package manager được phép chọn “latest/highest version” mà không pin version, kết quả có thể khác kỳ vọng: repository ưu tiên thấp hơn chứa phiên bản cao hơn vẫn có thể ảnh hưởng dependency resolution.

Vì vậy nên:

- Pin dependencies bằng lockfile, version và digest/hash theo ecosystem.
- Dùng một virtual endpoint nhất quán thay vì cấu hình nhiều public sources tùy tiện.
- Tạo quy ước tên package nội bộ để tránh trùng public package.
- Kiểm tra upstream priority, provenance, license và approved dependencies.
- Với Python, **không dùng extra-index-url** để trộn PyPI trực tiếp với private index khi yêu cầu ưu tiên nguồn private bảo đảm; pip không áp thứ tự ưu tiên theo URL như nhiều người tưởng.

## 12. Vòng đời artifact, immutability và release promotion

### 12.1. Mutable image tags có thể gây deployment không tái tạo được

Giả sử build A được push thành:

~~~text
checkout-api:stable -> sha256:AAA
~~~

Ngày sau build B ghi đè tag:

~~~text
checkout-api:stable -> sha256:BBB
~~~

Một deployment mới tham chiếu **stable** có thể lấy B, trong khi một Pod đang chạy hoặc một rollback cũ dùng A. Nếu đội vận hành chỉ lưu tag, có thể không tái tạo được chính xác bản build đã chạy.

Một chính sách phát hành tốt là:

1. CI build và test từ một **commit SHA** được biết.
2. Ghi image tags có version/commit rõ ràng.
3. Push vào standard repository được phép.
4. Lấy **digest sha256 đầy đủ** sau push.
5. Scan/attest theo policy.
6. Promote **chính digest đã được kiểm tra** tới staging/production.
7. Lưu artifact provenance và deployment revision để rollback.

### 12.2. Docker immutable tags

Repository có thể bật **immutable tags** để ngăn cập nhật tag sang image digest khác. Ví dụ:

~~~bash
# THAY ĐỔI — chỉ dùng khi thiết kế release đã sẵn sàng.
# Giai đoạn tạo repository:
gcloud artifacts repositories create "prod-images" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --repository-format=docker \
  --immutable-tags
~~~

Bật immutable tags có hậu quả về vòng đời:

- Không thể push tag cũ lên một digest mới.
- Không thể tùy ý gỡ tag khỏi image đã được gắn.
- Tagged images bị hạn chế xóa khi immutable tags được bật.
- Cleanup policies cần được thiết kế tương thích với các ràng buộc đó.

Không bật immutable tags trên repository đang dùng cách phát hành **latest overwrite** mà chưa cập nhật pipeline và phương án rollback. Tốt hơn là có versioned tags và dùng digest trong deployment.

### 12.3. Promotion khác rebuild

Giữa môi trường dev, staging và prod, nên promote **artifact đã kiểm chứng** (cùng content digest) thay vì build lại từ source rồi giả định bytes không đổi. Rebuild có thể thay đổi:

- Base image tag được giải tham chiếu ra digest khác.
- Dependency snapshot/public package mới.
- Build tool, timestamp và môi trường CI.
- Compiler/OS packages hoặc cấu hình build.

Reproducible builds là mục tiêu quan trọng, nhưng một cách đơn giản để tránh chênh lệch môi trường là **promote cùng digest**. Khi copy image giữa repositories/locations, phải kiểm tra digest/signer/provenance theo công cụ hỗ trợ; không tự cho rằng copy giữ nguyên tất cả manifest/metadata trong mọi trường hợp.

### 12.4. Artifact Registry không tự rollback Cloud Run/GKE

- **Cloud Run:** phát hành một revision mới dựa trên image đã chọn; rollback cần điều chỉnh traffic/revision theo công cụ Cloud Run.
- **GKE:** deployment manifest/Helm/GitOps xác định image; rollback cần cập nhật Deployment/StatefulSet phù hợp và kiểm tra readiness.
- **Compute Engine:** VM startup/container runtime phải được chỉ rõ tham chiếu image và cập nhật/khởi động phù hợp.

Nếu xóa digest còn được runtime kéo hoặc dùng để rollback, lần triển khai tiếp theo có thể thất bại. Điều này liên quan trực tiếp tới retention và cleanup policy.

## 13. Cleanup policies và retention

Artifact Registry có thể tự dọn các artifact versions không còn cần thiết theo **cleanup policies**. Tính năng này giúp giảm lưu trữ, nhưng xóa nhầm có thể làm pipeline build/deploy hoặc rollback không hoạt động.

### 13.1. Những kiểu policy thường gặp

| Kiểu policy | Mục đích | Rủi ro cần tránh |
|---|---|---|
| **Conditional delete** | Xóa versions khớp điều kiện như quá tuổi hoặc không còn tag | Xóa bản vẫn đang dùng hoặc artifact không hỗ trợ tags |
| **Conditional keep** | Bảo vệ versions khớp tag/version/package prefix | Bảo vệ nhầm tập quá rộng, làm chi phí tăng |
| **Keep most recent versions** | Giữ số phiên bản gần đây nhất theo package | Không đủ cho rollback phiên bản cũ hoặc release dài hạn |

Các điều kiện có thể dựa trên **tagState, tagPrefixes, versionNamePrefixes, packageNamePrefixes, olderThan/newerThan** theo tài liệu, tùy format. Với format không hỗ trợ tags, artifact có thể được xem như **untagged** trong cleanup semantics. Repository **immutable Docker tags** có ràng buộc riêng về tagged image deletion.

### 13.2. Quy trình an toàn khi tạo cleanup policy

~~~mermaid
flowchart TD
    REQ["Nhu cầu giảm phí/giữ release"] --> INVENT["Inventory image versions + consumers"]
    INVENT --> RULE["Thiết kế keep/delete policies"]
    RULE --> DRY["Dry run, kiểm tra audit/logs"]
    DRY --> REVIEW{"Owner & SRE chấp thuận?"}
    REVIEW -- "Chưa" --> RULE
    REVIEW -- "Có" --> APPLY["Apply cleanup"]
    APPLY --> VERIFY["Xác minh digest cần rollback vẫn tồn tại"]
    VERIFY --> COST["Quan sát storage và chi phí"]
~~~

Không xem xóa versions là thao tác tức thì. Theo tài liệu, cleanup jobs chạy định kỳ, thay đổi có thể mất **khoảng một ngày** để có hiệu lực. Chính sách dọn dẹp dành cho **standard repositories**, không áp trực tiếp lên virtual repository hoặc cả project.

**Đặc biệt lưu ý:** giữ “5 versions gần nhất” không bảo đảm một image production đang chạy từ sáu tháng trước còn được giữ. Phải có registry of deployed digests hoặc retention policy cho release được phê duyệt và khôi phục.

### 13.3. Ví dụ quy tắc minh họa

~~~json
[
  {
    "name": "delete-untagged-old",
    "action": {"type": "Delete"},
    "condition": {
      "tagState": "untagged",
      "olderThan": "30d"
    }
  },
  {
    "name": "keep-prod-tags",
    "action": {"type": "Keep"},
    "condition": {
      "tagState": "tagged",
      "tagPrefixes": ["prod-", "release-"]
    }
  }
]
~~~

Đây là **cấu hình ví dụ để phân tích**, không nên apply trước khi kiểm tra hỗ trợ format, logic tương tác giữa keep/delete và trạng thái tags thực. Người quản trị cần dùng **dry run** trước khi bật xóa, và bảo đảm có danh sách deployed digests/rollback requirements được bảo vệ.

### 13.4. Tại sao registry không tự là hệ thống backup?

Một repository có thể bị xóa do IAM lỗi, thao tác quản trị nhầm hoặc retention policy. Artifact Registry quản lý artifact distribution, không mặc nhiên cung cấp bản backup độc lập khỏi mọi thay đổi.

Nếu cần **disaster recovery**, cân nhắc:

- Giữ source và build recipes có thể tái tạo được.
- Có bản sao artifacts quan trọng ở location/repository khác theo chính sách.
- Lưu SBOM, signatures/provenance và manifest release.
- Diễn tập kéo image từ repository DR và deploy lại.
- Kiểm soát IAM Administrator/Repo Admin, deletion và cleanup policy.

Một artifact đã được ký/scan vẫn có thể mất availability nếu repository/region có sự cố. Cần phương án vận hành phù hợp RTO và yêu cầu compliance.

## 14. Bảo mật chuỗi cung ứng phần mềm

Artifact Registry là một mắt xích quan trọng trong **software supply chain**, nhưng việc push thành công không chứng minh artifact an toàn hoặc đáng tin.

### 14.1. Những rủi ro phổ biến

| Rủi ro | Ví dụ | Kiểm soát phù hợp |
|---|---|---|
| **Dependency confusion** | Public package trùng tên internal package được resolve trước | Virtual repository, ưu tiên upstream, version pinning |
| **Typosquatting** | Package tên gần giống thư viện hợp lệ | Allowlist, review deps, kiểm tra provenance |
| **Mutable tag** | stable được push đè bằng digest khác | Immutable tags, pin digest |
| **Image có lỗ hổng** | Base image chứa CVE nghiêm trọng | Quét lỗ hổng, base image updates, SLA remediation |
| **Secret trong image** | ENV/build layer chứa API key | Secret scanning, không COPY credentials |
| **Malicious build pipeline** | CI service account bị lộ có quyền Writer | WIF, quyền tối thiểu, signed provenance, branch protection |
| **Xóa artifact quan trọng** | Cleanup xóa release đang chạy | Dry run, keep policies, inventory deployed digests |
| **Upstream không đáng tin** | Remote tự tải phiên bản bị đầu độc | Pin versions, signatures/hashes, source policy |
| **IAM quá rộng** | Runtime service account có repoAdmin | Tách Reader/Writer/RepoAdmin/Admin |
| **Sai ranh giới vị trí** | Build ở region khác nơi dữ liệu được phép | Location policy, kiểm soát egress và repo replication |

### 14.2. Artifact Analysis và vulnerability scanning

Artifact Registry có thể tích hợp **Artifact Analysis** và cơ chế quét lỗ hổng được hỗ trợ cho container images. Có thể kiểm tra các bản image có dependency OS/language packages bị báo CVE, severity và thời điểm scan.

Nhưng cần phân biệt:

- **Scan result** là ảnh chụp đánh giá tại thời điểm, không phải chứng chỉ phần mềm không có lỗ hổng.
- Một CVE có thể được công bố sau khi image đã deploy; phải theo dõi lại và rebuild base image.
- Lỗ hổng ở package không đồng nghĩa có thể khai thác trong workload; cần xét reachability/exposure và risk appetite.
- Việc bật **Container Scanning API** có thể phát sinh chi phí quét; xem trạng thái dự án và thiết lập repo.
- Scan không phát hiện mọi vấn đề như business logic vulnerabilities, secret vô tình nhúng, sai IAM hoặc network policy.

### 14.3. SBOM, provenance, chữ ký và Binary Authorization

**SBOM (Software Bill of Materials)** là danh mục thành phần phần mềm trong artifact, giúp truy vấn tác động khi có CVE. **Build provenance** mô tả artifact được build từ source/commit, builder và workflow nào. OCI attachments có thể lưu metadata liên quan tới image như SBOM và scan outputs khi công cụ hỗ trợ.

Có thể dùng **Binary Authorization** và policy enforcement phù hợp trên GKE/Cloud Run hoặc môi trường hỗ trợ để chỉ triển khai image đã được phê duyệt. Không đồng nhất:

- Đã có image trong Artifact Registry.
- Đã qua vulnerability scan.
- Đã ký/chứng thực provenance.
- Đã được policy cho phép deploy.

Đó là **bốn điều kiện có thể tách biệt**. Pipeline production nên kết hợp các mức kiểm tra theo yêu cầu thay vì giả định Artifact Registry tự chặn mọi image nguy hiểm.

### 14.4. Mã hóa và quản trị khóa

Repository artifacts được mã hóa at rest theo cơ chế Google Cloud. Với nhu cầu cụ thể, có thể cấu hình **Cloud KMS Customer-Managed Encryption Key (CMEK)** khi tạo repository trong phạm vi/tính năng được hỗ trợ.

Trước khi dùng CMEK:

1. Kiểm tra location của KMS key và repository theo điều kiện sản phẩm.
2. Cấp quyền phù hợp cho Artifact Registry service agent sử dụng key.
3. Xác định chính sách rotate/disable/destroy key và tác động tới khả năng pull artifacts.
4. Bảo vệ quyền KMS Admin tách khỏi người vận hành CI.
5. Diễn tập tình huống mất quyền sử dụng key mà không cần phá hủy production artifacts.

**Không tùy tiện disable hoặc destroy KMS key** đang bảo vệ repository: dữ liệu có thể không truy cập được. Metadata repository như description/tags không phải chỗ lưu secret.

### 14.5. VPC Service Controls và truy cập riêng

Một số tổ chức dùng **VPC Service Controls**, private network egress và chính sách organization để giảm nguy cơ dữ liệu bị lấy ra ngoài. Tuy vậy, Artifact Registry là dịch vụ có API endpoint: client vẫn cần DNS, route/private Google access nếu cần, credentials và IAM. Việc repository đặt tại một region không mặc nhiên có nghĩa “chỉ mạng VPC đó được đọc”.

Với remote repository, kết nối tới upstream bên ngoài còn phải đáp ứng chính sách egress/upstream được sản phẩm hỗ trợ. Không áp dụng một tập firewall VPC cho VM rồi mặc định đã bảo vệ mọi đường lấy package qua Artifact Registry.

## 15. Quan sát hoạt động, audit và chi phí

### 15.1. Những tín hiệu nên theo dõi

| Nhóm | Chỉ số/dữ liệu | Ý nghĩa |
|---|---|---|
| Repository inventory | Repo format/mode/location, IAM, artifact versions | Kiểm kê tài sản và quyền |
| Build/deploy | Build ID, commit SHA, pushed digest, deployment revision | Truy vết release |
| Security | Vulnerability findings, SBOM, attestations | Phát hiện rủi ro |
| Availability | Pull/push failures, upstream timeouts, error responses | Khả năng cấp artifact cho CI/runtime |
| Storage | Bytes/versions, tagged vs untagged, cleanup results | Quản lý dung lượng |
| Cost | Storage, egress, scanning, build and KMS charges | FinOps |
| Audit | IAM changes, repository create/update/delete, cleanup changes | Điều tra và tuân thủ |
| Cross-project | Service agents/readers dùng repo của project khác | Least privilege |

**Cloud Audit Logs** giúp xác định ai tạo/xóa/chỉnh repository và quyền theo loại log/API được hỗ trợ. Registry activity cần được đọc theo cơ chế logging tương ứng; đừng mặc định mọi request pull đều xuất hiện trong một bảng duy nhất mà không kiểm tra Data Access logging và quyền xem logs.

### 15.2. Chi phí không chỉ là kích thước image

Artifact Registry có thể phát sinh phí từ:

- Dung lượng **artifacts và remote cached content** được lưu.
- Lưu lượng **network transfer/egress** theo location/đích và bảng giá.
- Số lượng requests hoặc hoạt động tương ứng theo mô hình giá đang áp dụng.
- **Vulnerability scanning** khi API/chức năng tính phí được bật.
- Cloud Build/GKE/Cloud Run, KMS, Pub/Sub, Cloud Logging hoặc dịch vụ ngoài Artifact Registry.
- CI retry, image layers lớn, cache invalidation và cross-region pull không tối ưu.

Không khẳng định cứ xóa tag là lập tức tiết kiệm toàn bộ dung lượng; image layers có thể còn được chia sẻ hoặc version còn được tham chiếu. Cần đọc số liệu billing/storage thực tế, đợi cleanup job chạy và đối chiếu hóa đơn theo **Service/SKU**, không tính chỉ từ số tag.

### 15.3. Tối ưu hợp lý

- Dùng multi-stage Docker builds, base image tối giản và **.dockerignore**.
- Pin dependencies và base image digests để build ổn định.
- Chọn region phù hợp với runtime/CI và yêu cầu cư trú dữ liệu.
- Dùng remote cache có chính sách để giảm tải lặp từ upstream.
- Dọn untagged/old versions có kiểm soát, giữ digests đang deploy hoặc cần rollback.
- Gắn owner/cost center qua labels/metadata theo khả năng repository.
- Review định kỳ số repositories không dùng, quyền Writer/RepoAdmin và phí scanning.

**Không đánh đổi bảo mật lấy tiết kiệm bằng cách tắt quét lỗ hổng hoặc xóa bản rollback** khi chưa có quyết định về risk và khôi phục.

## 16. Troubleshooting: lỗi thường gặp

### 16.1. Ma trận chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| **401 Unauthorized** khi Docker pull/push | Docker credential helper sai hostname, token hết hạn hoặc chưa login | docker config, gcloud auth list, location hostname |
| **403 Permission Denied** | Identity thiếu Reader/Writer hoặc policy chặn | Repository IAM, project/SA đúng, service agent |
| **Repository not found** | Sai project, location, repo ID hoặc không có quyền xem | gcloud artifacts repositories describe, đường dẫn image |
| **Unsupported format** | Push Docker vào repo Maven hoặc dùng npm registry URL sai | Describe repository format/mode |
| **Cannot push to virtual/remote** | Đang dùng endpoint chỉ dành pull/aggregation | Publish vào standard |
| **Push tag bị từ chối** | Immutable tags, tag đã tồn tại hoặc policy hạn chế | Describe immutable settings, version naming |
| **Maven dependency không resolve** | Wrong repository URL/credentials, snapshot/release policy hoặc version không tồn tại | print-settings mvn/gradle, artifact version, auth helper |
| **Python pip cài nhầm public package** | Config nhiều indexes, chọn version cao hơn | Kiểm tra pip config, dùng virtual endpoint và pin |
| **npm publish 403** | Scope, .npmrc, credentials hoặc Writer IAM | print-settings npm, package scope và token |
| **Remote pull lần đầu lỗi** | Upstream timeout, rate limit, credentials, URL không được hỗ trợ | Remote config, Secret Manager, upstream health |
| **Virtual trả nhầm package** | Priority/upstream trùng tên/version, không pin | Policy JSON, version lock, source logs |
| **GKE image pull failed** | Node SA thiếu reader, secret hoặc sai image path | Pod events, node/project IAM, image digest |
| **Cloud Run deploy image failed** | Cross-project pull thiếu service agent permission hoặc image không tồn tại | Cloud Run deploy errors, Artifact Registry IAM |
| **Quét CVE không thấy kết quả** | Scanning API/option chưa bật, asset chưa hỗ trợ hoặc scan chưa hoàn tất | Artifact Analysis config, scan status |
| **Cleanup chưa xóa ngay** | Chạy định kỳ/dry-run mode | Repo cleanup settings, đợi job/quan sát logs |
| **Cleanup xóa nhầm** | Điều kiện/tagState/keep rule sai | Incident response, tìm bản sao/restore/rebuild |
| **Storage charge không giảm** | Layers còn chia sẻ, versions khác vẫn giữ, billing trễ | Inventory versions, storage metrics, Billing |
| **CMEK repo không đọc được** | Key bị disable, IAM KMS sai hoặc location không phù hợp | KMS key status, service agent access |
| **Không tải được qua mạng riêng** | DNS, private access/VPC-SC, proxy hoặc perimeter policy | Kết nối API endpoint và logs tương ứng |

### 16.2. Quy trình điều tra không mở quyền bừa bãi

1. Xác nhận **operation**: create repo, list, push, pull, delete hay deploy.
2. Xác định **identity** thực tế: gcloud user, Docker helper, CI service account, GKE node SA hoặc Cloud Run service agent.
3. Xác nhận **project/location/repository/format/mode/image/version**.
4. Đọc chi tiết lỗi HTTP (401 khác 403), timestamps, logs và IAM policy.
5. Đối chiếu upstream khi là remote/virtual; kiểm tra priority/version.
6. Kiểm tra tag/digest và xem artifact version có thực sự tồn tại.
7. Thử lại bằng **identity và path đúng** trong project lab; không cấp Owner để “thử cho nhanh”.
8. Ghi nguyên nhân, cách khắc phục nhỏ nhất, tác động và bước tránh lặp.

### 16.3. Bộ lệnh chỉ đọc phục vụ điều tra

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
LOCATION="asia-southeast1"
REPOSITORY="app-images-lab"

gcloud auth list

gcloud artifacts repositories describe "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --format=yaml

gcloud artifacts repositories get-iam-policy "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION"

gcloud artifacts packages list \
  --project="$PROJECT_ID" \
  --repository="$REPOSITORY" \
  --location="$LOCATION"

gcloud artifacts docker images list \
  "$LOCATION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY" \
  --include-tags
~~~

Không chia sẻ Docker config hoặc access tokens nguyên văn khi gửi ticket: file credential helper có thể chứa endpoint/dữ liệu xác thực nhạy cảm. Chỉ cung cấp phần hostname và identity cần thiết đã che bớt.

## 17. Case study: phát hành checkout-api và Java library nội bộ

**Bối cảnh giả định:** một công ty bán hàng trực tuyến có các thành phần:

- **checkout-api** viết bằng Java, triển khai Cloud Run.
- **payments-worker** triển khai trên GKE.
- Thư viện Java **payment-sdk** dùng chung trong nhiều repository Git.
- Frontend **storefront-ui** sử dụng npm packages nội bộ.
- Các base images/dependencies public cần kiểm soát nguồn.

### 17.1. Thiết kế repositories

| Repository | Format/mode | Nguồn và consumer |
|---|---|---|
| **checkout-images** | Docker standard | Cloud Build push; Cloud Run/GKE pull |
| **java-shared-libs** | Maven standard | Java release pipeline publish |
| **maven-central-remote** | Maven remote | Proxy/cache Maven Central |
| **maven-unified** | Maven virtual | Maven/Gradle resolve internal trước public |
| **npm-internal** | npm standard | Frontend publish package nội bộ |
| **dockerhub-remote** | Docker remote | Controlled pull base images |
| **generic-bundles** | Generic standard | Bộ release manifests/CLI được đóng version |

Các repositories dùng location phù hợp với chính sách doanh nghiệp. Runtime production có thể nằm ở project khác, nên IAM được cấp **theo principal kéo image** với **Reader**, CI có **Writer**, security/platform team có quyền quản trị riêng.

### 17.2. Pipeline build và phát hành

~~~mermaid
flowchart TD
    COMMIT["Git commit + PR review"] --> TEST["Test Java / SAST / deps"]
    TEST --> BUILD["Build image + JAR"]
    BUILD --> PUSH["Push standard repositories"]
    PUSH --> DIG["Ghi immutable digest/version"]
    DIG --> SCAN["Vulnerability checks / SBOM / provenance"]
    SCAN --> APPROVE{"Release gate PASS?"}
    APPROVE -- "Không" --> FIX["Sửa và tạo version mới"]
    APPROVE -- "Có" --> STAGE["Deploy staging theo digest"]
    STAGE --> VERIFY["Integration tests và SLO"]
    VERIFY --> PROD["Promote cùng digest vào production"]
    PROD --> OBS["Monitor / audit / inventory deployed digests"]
    OBS --> CLEAN["Cleanup dry run và retention review"]
~~~

Một quy trình release có thể sử dụng Cloud Build để build và push, Artifact Analysis để quét và Cloud Deploy/GitOps/Cloud Run revisions để điều phối; chính sách deployment cuối cùng phụ thuộc nền tảng chạy ứng dụng.

### 17.3. Sự cố 1: lỗi image pull sau khi tách project

Sau khi tách production project, pipeline deploy Cloud Run thất bại vì **403** khi lấy image từ **commerce-build**. Nhóm ứng dụng cấp Reader cho runtime service account nhưng vẫn lỗi.

**Hướng điều tra:** xem **principal thực sự kéo image** trong đường deploy Cloud Run, có thể là service agent của project runtime thay vì runtime SA. Kiểm tra IAM repository nguồn, project/region/path/digest và organization policy. Không đặt repository thành public để xử lý tạm.

### 17.4. Sự cố 2: package nội bộ bị lấy nhầm từ public

Build Python cài package **internal-risk-utils** phiên bản cao hơn từ PyPI vì pip được cấu hình nhiều indexes, trong đó có cả private index và public PyPI. Dù private package có sẵn, pip có thể chọn bản public theo version.

**Hướng xử lý:** dùng virtual repository với private upstream priority phù hợp, chỉ cấu hình một approved index endpoint, pin dependencies, kiểm tra hashes/provenance và review tên packages nội bộ.

### 17.5. Sự cố 3: cleanup xóa release đang chạy

Một policy giữ 5 image versions gần nhất đã xóa digest của phiên bản đang chạy ở một nhóm GKE ít phát hành. Các Pod đang chạy chưa nhất thiết hỏng ngay, nhưng khi cần reschedule/rollback, image không còn để pull.

**Hướng xử lý:** duy trì danh sách deployed digests, retention policy cho production/rollback, dry run trước apply, tạo bản sao DR khi yêu cầu. Nếu không còn image, phải rebuild từ nguồn và đối chiếu provenance; không khẳng định có thể khôi phục chính xác một digest cũ khi môi trường build đã thay đổi.

### 17.6. Kiểm tra sau triển khai

- Deployment của Cloud Run/GKE tham chiếu **digest** đã được phê duyệt.
- Image pull thành công bằng principal đúng ở cả staging và production.
- Java package có đúng Maven coordinates/version và consumers resolve được.
- Virtual dependency endpoint ưu tiên internal đúng theo policy.
- Vulnerability findings nằm trong mức chấp nhận đã phê duyệt.
- SBOM/provenance/CI logs giúp truy vết build.
- Cleanup không xóa digests đang chạy/rollback.
- Chi phí storage, scan, transfer và repo IAM được review theo chu kỳ.

## 18. Bài tập và câu hỏi tự kiểm tra

### 18.1. Chọn định dạng và repository mode

| Nhu cầu | Đáp án định hướng |
|---|---|
| Push container image Java lên Cloud Run | **Docker standard** |
| Publish thư viện Java để Maven resolve | **Maven standard** |
| Có một endpoint cho Maven nội bộ + Maven Central | **Maven virtual**, upstream standard và remote |
| Proxy/cache images từ Docker Hub | **Docker remote** |
| Lưu file ZIP bản phát hành, có package/version | **Generic standard** |
| Phân phối gói Debian OS | **Apt** format |
| Lưu Helm chart theo OCI | **Docker** format |
| Lưu Ruby gem hoặc Conda package | Format tương ứng, lưu ý **Preview** |
| Proxy upstream nhưng policy cấm cache | **Connector (Preview)** khi được hỗ trợ |
| Phân phối Python wheel cho pip | **Python** format |

### 18.2. Câu hỏi suy luận

1. Artifact Registry có tự build image khi code trên Git thay đổi không?
2. Một repository format Docker có thể được chuyển sang Maven bằng cách đổi description không?
3. **Remote repository** khác **virtual repository** ở đâu?
4. Với virtual upstream priority **100** và **50**, upstream nào được ưu tiên khi cùng version tồn tại?
5. Vì sao cấu hình pip **extra-index-url** không bảo đảm ưu tiên private package?
6. Tag **stable** có tự là bản build bất biến không?
7. Vì sao nên deploy image qua digest để rollback chính xác?
8. Một CI account cần push, có nhất thiết được cấp **roles/artifactregistry.admin** không?
9. Cross-project Cloud Run image pull fail 403, principal nào cần kiểm tra?
10. Cleanup policy chỉ giữ 5 versions mới nhất có đủ cho mọi rollback production không?
11. Generic artifact version có thể ghi đè bằng upload mới cùng version không?
12. Nếu bật vulnerability scanning, có bảo đảm không còn lỗi logic, secret hoặc IAM không?
13. Docker credential helper đã cấu hình thì người dùng thiếu Reader IAM có pull được không?
14. Nếu location của repository khác nơi chạy GKE, những tác động nào cần xem xét?
15. Vì sao xóa tag có thể chưa làm giảm ngay phí storage?

**Đáp án ngắn:** (1) Không; CI chịu trách nhiệm build. (2) Không. (3) Remote proxy/cache một upstream, virtual tập hợp nhiều upstream thành endpoint. (4) 100. (5) pip có thể chọn version mới nhất trên bất kỳ index. (6) Không nếu mutable. (7) Digest xác định nội dung manifest. (8) Không, Writer thường đủ. (9) Service agent/identity thực sự thực hiện pull. (10) Không. (11) Không. (12) Không. (13) Không. (14) Network/egress/latency/data residency/DR. (15) Còn layers, versions, cleanup job và độ trễ billing.

### 18.3. Bài thực hành đọc repository hiện có

Chỉ dùng repo được cấp quyền:

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
LOCATION="asia-southeast1"
REPOSITORY="YOUR_REPOSITORY"

# Chỉ đọc.
gcloud artifacts repositories describe "$REPOSITORY" \
  --project="$PROJECT_ID" --location="$LOCATION" \
  --format=yaml

gcloud artifacts packages list \
  --project="$PROJECT_ID" --location="$LOCATION" \
  --repository="$REPOSITORY"

gcloud artifacts repositories get-iam-policy "$REPOSITORY" \
  --project="$PROJECT_ID" --location="$LOCATION"
~~~

Viết báo cáo:

~~~text
PROJECT / LOCATION:
REPOSITORY / FORMAT / MODE:
UPSTREAMS VÀ PRIORITIES (NẾU CÓ):
IAM READER / WRITER / ADMIN:
NUMBER OF PACKAGES / VERSIONS:
IMAGE DIGEST ĐANG DEPLOY (NẾU LÀ DOCKER):
IMMUTABLE TAGS ENABLED?:
CLEANUP / RETENTION DRY RUN?:
VULNERABILITY SCANNING STATUS:
CMEK / ENCRYPTION POLICY:
DATA RESIDENCY / CROSS-REGION CONSUMERS:
ESTIMATED COST / OWNER:
RISK / RECOMMENDED ACTION:
~~~

Nếu không đủ quyền hoặc format/mode không hỗ trợ một lệnh, ghi rõ **NOT OBSERVED/UNKNOWN**, không đánh giá “PASS” khi chưa xác minh.

## 19. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “Artifact Registry chính là Docker Hub của Google.” | Hỗ trợ nhiều package formats và repository modes, không chỉ Docker. |
| “Một repo chứa được mọi định dạng.” | Repository chọn format cụ thể, không dùng lẫn Maven/npm/Docker tùy ý. |
| “Virtual là nơi push artifact.” | Virtual là access point tổng hợp; publish vào standard. |
| “Remote lưu bản gốc nội bộ.” | Remote là proxy/cache upstream; standard dùng để upload artifacts nội bộ. |
| “Connector và remote đều cache như nhau.” | Connector Preview proxy **không cache**. |
| “Artifact Registry tự build và deploy code.” | CI/CD và runtime thực hiện build/deploy. |
| “Image tag là content hash.” | Tag có thể mutable; digest là content-addressable identifier. |
| “Nếu immutable tag bật thì mọi artifact mãi tồn tại.” | Chỉ kiểm soát cách tag được dùng; còn lifecycle, retention và hành động admin. |
| “Có Reader trên runtime SA là luôn pull được cross-project.” | Phải kiểm tra principal thực sự kéo image, có thể là service agent/node SA. |
| “Một repo virtual priority cao hơn sẽ luôn chọn phiên bản cũ nội bộ.” | Version resolution của client còn ảnh hưởng; pin version/hashes. |
| “pip extra-index-url ưu tiên private theo thứ tự khai báo.” | Không; có rủi ro dependency confusion. |
| “Artifact Analysis scan đủ để cho phép production deploy.” | Còn test, provenance, policy, IAM và risk review. |
| “Generic là nơi ghi đè file cùng version.” | Generic versions bất biến; phát hành version mới. |
| “Cleanup dry run xóa artifact.” | Dry run dùng để quan sát trước khi bật xóa thật. |
| “Chỉ tag 1.0.0 tồn tại là đủ backup/rollback.” | Phải giữ digest, artifacts, pipeline/provenance và phương án DR. |
| “Xóa một tag sẽ giảm phí ngay bằng kích thước image.” | Layers có thể còn dùng; cleanup/billing có độ trễ. |
| “Repository ở asia-southeast1 bảo đảm mọi pull đều từ vùng đó miễn phí.” | Cần xem network transfer, destination và giá hiện hành. |
| “Có thể đặt token vào Dockerfile nếu image private.” | Secret có thể còn trong build layers; phải dùng secret management. |

## 20. Tài liệu Google Cloud tham khảo

Những tài liệu chính thức nên kiểm tra khi cập nhật bài học hoặc triển khai production:

- [Artifact Registry overview](https://docs.cloud.google.com/artifact-registry/docs/overview)
- [Repository overview](https://docs.cloud.google.com/artifact-registry/docs/repositories)
- [Supported formats](https://docs.cloud.google.com/artifact-registry/docs/supported-formats)
- [Create standard repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/create-repos)
- [Remote repositories overview](https://docs.cloud.google.com/artifact-registry/docs/repositories/remote-overview)
- [Create remote repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/remote-repo)
- [Virtual repositories overview](https://docs.cloud.google.com/artifact-registry/docs/repositories/virtual-overview)
- [Create virtual repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/virtual-repo)
- [Connector repositories overview (Preview)](https://docs.cloud.google.com/artifact-registry/docs/repositories/connector-overview)
- [Access control with IAM](https://docs.cloud.google.com/artifact-registry/docs/access-control)
- [Docker image push and pull](https://docs.cloud.google.com/artifact-registry/docs/docker/pushing-and-pulling)
- [Maven and Gradle authentication](https://docs.cloud.google.com/artifact-registry/docs/java/authentication)
- [Python package authentication](https://docs.cloud.google.com/artifact-registry/docs/python/authentication)
- [npm authentication](https://docs.cloud.google.com/artifact-registry/docs/nodejs/authentication)
- [Generic artifacts](https://docs.cloud.google.com/artifact-registry/docs/generic)
- [Configure cleanup policies](https://docs.cloud.google.com/artifact-registry/docs/repositories/cleanup-policy)
- [Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing)

Định dạng Preview, repository modes, cấu hình upstream, vulnerability scanning, IAM và giá có thể thay đổi theo thời điểm. Khi áp dụng thật, cần xác minh theo **format, mode, location, Google Cloud project, CLI version và quyền đang được cấp**.

---

**Kết nối với lộ trình CLOUD_PROVIDERS_GCP:** Artifact Registry là điểm nối giữa **source code/CI-CD** và những nền tảng chạy workload như **Compute Engine, GKE và Cloud Run**. Repository format/mode quyết định cách quản lý **Docker images, Java JARs và dependencies**, trong khi **project/IAM, VPC/network, Cloud KMS, Cloud Logging/Monitoring và Cloud Billing** quyết định an toàn và chi phí vận hành. Quy trình đáng tin cậy là **xác định nguồn → build/test → publish vào standard repository → xác minh version/digest, quét bảo mật → deploy bằng danh tính ít quyền nhất → giữ bản rollback → dọn artifacts theo chính sách đã kiểm thử**.







