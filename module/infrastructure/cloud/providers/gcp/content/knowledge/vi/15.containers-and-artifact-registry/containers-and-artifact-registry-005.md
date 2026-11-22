# Remote repositories và virtual repositories

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt ba chế độ chính của **Google Cloud Artifact Registry**: **standard**, **remote** và **virtual repositories**; biết thêm chế độ **connector** khi thích hợp.
2. Giải thích cơ chế **remote proxy/cache** đối với container images và packages, bao gồm vấn đề upstream authentication, cache freshness, repository location và hạn chế mạng.
3. Thiết kế **virtual repository** gom nhiều upstream standard/remote theo **priority**, phân biệt tìm cùng package-version với chọn phiên bản mới nhất.
4. Giảm rủi ro **dependency confusion** bằng cách đặt private repository có ưu tiên cao và cấu hình client chỉ dùng virtual endpoint.
5. Thực hành với **gcloud Artifact Registry**, **Docker** và **Maven/Gradle** để tạo standard/remote/virtual repositories, kiểm thử download và quản lý access.
6. Vận hành an toàn trong **Cloud Build, GKE, Cloud Run** và pipeline Java: IAM/service agents, Secret Manager, cache, vulnerability scanning, cleanup policies, VPC Service Controls, giám sát và chi phí.

## 1. Bài toán: một pipeline cần cả dependency nội bộ lẫn công khai

Một công ty phát triển **Java/Spring Boot** trên GCP:

- Dùng các thư viện **com.company:order-core** do công ty tự phát hành.
- Dùng các thư viện công khai **org.slf4j:slf4j-api**, **com.fasterxml.jackson.core:jackson-databind** và những dependencies liên quan từ Maven Central.
- Build container bằng base image từ **Docker Hub**, sau đó push image tự xây vào Artifact Registry.
- Deploy image đến **Google Kubernetes Engine (GKE)**, **Cloud Run** hoặc VM trên **Compute Engine**.

Nếu Maven/Gradle, Docker, pip và npm truy cập nhiều nguồn trực tiếp, tổ chức gặp những vấn đề:

- Mỗi máy phát triển và runner có danh sách repository, credentials, proxy khác nhau.
- Upstream public có thể chậm, lỗi, giới hạn tốc độ hoặc tạm ngừng hoạt động.
- Package tên giống package nội bộ có thể xuất hiện trên public registry và bị client chọn nhầm (**dependency confusion**).
- Khó kiểm toán nguồn dependency và áp dụng quy tắc phân quyền, scan, retention tập trung.
- Download lặp lại từ Internet làm tăng độ trễ, phụ thuộc mạng và có thể tăng chi phí.

**Artifact Registry** giải quyết bài toán quản lý artifacts theo định dạng: Docker/OCI images, Maven packages, npm, Python và các định dạng được hỗ trợ. Ba chế độ repository có nhiệm vụ bổ sung nhau:

- **Standard:** nơi **publish/upload** artifact của doanh nghiệp.
- **Remote:** nơi **proxy và cache** artifact lấy từ nguồn upstream.
- **Virtual:** **một endpoint đọc** kết hợp nhiều repositories cùng định dạng theo các ưu tiên được quản trị.

Trong mô-đun **CLOUD_PROVIDERS_GCP**, bài này kết nối các kiến thức project, IAM, VPC, Compute Engine, GKE, Cloud Run, storage và CI/CD để thiết kế đường đi artifact có kiểm soát từ **dependency resolution → build → image → deploy → giám sát chi phí và độ tin cậy**.

## 2. Chọn đúng repository mode

### 2.1. So sánh tổng quát

| Chế độ | Artifact được lấy từ đâu? | Có lưu artifact trong repo? | Có upload/push trực tiếp? | Mục đích |
|---|---|---|---|---|
| **Standard** | CI/CD hoặc developer publish | **Có** | **Có**, nếu được cấp quyền | Artifacts nội bộ, phiên bản release |
| **Remote** | Một upstream public/private/standard theo khả năng hỗ trợ | **Có**, cache theo yêu cầu | **Không** (read-only) | Proxy/cache dependencies bên ngoài |
| **Virtual** | Một hoặc nhiều upstream standard/remote | **Không** | **Không** (read-only) | Endpoint duy nhất, áp priority giữa repositories |
| **Connector** (Preview, phạm vi hỗ trợ riêng) | Upstream được định nghĩa cho connector | **Không cache** | **Không**, theo mô hình proxy | Chuyển tiếp upstream khi không muốn cache |

Một repository có **một định dạng** (format), ví dụ Maven hoặc Docker. Một virtual Maven repository **không thể cùng lúc** tổng hợp Docker images; cần virtual Docker repository riêng.

### 2.2. Cấu trúc điển hình cho Java

~~~mermaid
flowchart LR
    DEV["Maven / Gradle<br/>Java developers và Cloud Build"] --> V["maven-all<br/>VIRTUAL"]
    V -->|"priority 100"| P["java-private<br/>STANDARD"]
    V -->|"priority 20"| R["maven-central-cache<br/>REMOTE"]
    R -->|"cache miss: HTTPS"| C["Maven Central<br/>UPSTREAM PUBLIC"]
    P --> J["Jar/POM nội bộ"]
~~~

**java-private** chứa thư viện do công ty xuất bản. **maven-central-cache** chỉ lấy dependency từ Maven Central và cache lại. **maven-all** là URL duy nhất mà build tool cần đọc; nó không giữ thêm một bản dữ liệu riêng.

### 2.3. Cấu trúc điển hình cho container

~~~mermaid
flowchart LR
    DO["Docker / GKE / Cloud Run pull"] --> V["docker-all<br/>VIRTUAL"]
    V -->|"priority 100"| S["images-private<br/>STANDARD"]
    V -->|"priority 10"| R["dockerhub-cache<br/>REMOTE"]
    R -->|"cache miss / metadata refresh"| HUB["Docker Hub"]
    CI["Cloud Build push image đã build"] --> S
~~~

Pipeline **push** vào **images-private**, không push vào **docker-all**. Client **pull** qua docker-all nếu cần một URL thống nhất. Đối với production deployment, có thể chọn trực tiếp image private theo digest hoặc dùng virtual endpoint theo chính sách tổ chức; cả hai vẫn cần IAM và kiểm soát provenance.

## 3. Remote repository hoạt động như thế nào?

### 3.1. Lần đầu tải: cache miss

~~~mermaid
sequenceDiagram
    participant CLI as Maven / Docker
    participant AR as Artifact Registry Remote
    participant UP as Upstream public/private
    CLI->>AR: GET package version / image digest
    AR->>AR: Kiểm tra cache
    alt Chưa có artifact
        AR->>UP: Tải artifact từ upstream
        UP-->>AR: Artifact + metadata
        AR->>AR: Cache bản đã tải
        AR-->>CLI: Trả artifact
    else Đã có bản phù hợp trong cache
        AR-->>CLI: Trả bản cached
    end
~~~

Remote repository hoạt động như một **read-only caching proxy**. Nó **không copy toàn bộ upstream ngay khi tạo**; chỉ những version được yêu cầu mới có thể được tải về cache.

### 3.2. Cache hit, upstream outage và artifact chưa từng tải

Khi một artifact/version đã được cache, một số request có thể tiếp tục lấy bản đã cache ngay cả khi upstream tạm không truy cập được. Nhưng:

- Artifact/version **chưa cache** vẫn có thể tải thất bại khi upstream outage.
- **Metadata, package indexes và mutable tags** có cơ chế làm mới, không thể coi cache luôn bất biến hay luôn mới nhất.
- Nếu upstream không có tên/version yêu cầu, remote không tự tạo ra version đó.
- Nếu repo bị xóa, cache cleanup hoặc request vượt quyền IAM, không có bảo đảm rằng artifact tiếp tục tải được.

**Remote cache giúp tăng tính sẵn sàng, không phải một bản sao offline hoàn chỉnh hoặc chiến lược backup.**

### 3.3. Các mốc làm mới metadata cần biết

Theo tài liệu remote repository hiện hành, những dạng index/metadata có **default update age** khác nhau:

| Định dạng | Thành phần metadata | Mốc mặc định |
|---|---|---|
| **Maven** | maven-metadata.xml | **5 phút** |
| **Maven** | archetype-catalog.xml | **1 giờ** |
| **npm** | Package manifest files | **5 phút** |
| **Python** | Package index files | **1 giờ** |
| **Docker** | List/Get tags cache | **1 giờ** |
| **Apt/Yum** (Preview) | Index files | **2 phút** |
| **Apt/Yum** (Preview) | Package files | **72 giờ** |

Đây là **giới hạn tuổi cập nhật cho các loại metadata/file được liệt kê**, không phải cam kết mọi artifact được kiểm tra lại đúng từng phút hay lời hứa một tag Docker mới luôn thấy ngay. Metadata refresh có thể khác cơ chế cache của artifact content. Với release quan trọng, **pin version và digest**, không chỉ dựa vào tag mutable như **latest**.

### 3.4. Địa điểm, upstream và những hạn chế mạng

Khi tạo remote repository, cần chọn **format, location, upstream source, encryption**. Các thiết lập này không thể tùy ý thay sau khi tạo; khi cần đổi upstream/location thường phải **tạo repo mới và chuyển client**.

Với custom upstream URL, **HTTPS là bắt buộc**. Remote repository **không hỗ trợ upstream chỉ có IP private trong on-premises hoặc VPC**, không truy cập được từ Internet. Nếu muốn mirror repository Nexus nội bộ, cần đánh giá upstream endpoint HTTPS có thể truy cập và cơ chế xác thực, hoặc lựa chọn kiến trúc phù hợp khác.

Nếu remote repository thuộc **VPC Service Controls perimeter**, truy cập upstream bên ngoài perimeter **bị chặn theo mặc định**. Cần cấu hình ngoại lệ/egress được Artifact Registry hỗ trợ và review bảo mật, không mặc định VPC peering hay Cloud NAT giải quyết yêu cầu này.

### 3.5. Public và private upstream authentication

Một số upstream như Docker Hub áp dụng rate limits và có thể cho phép authentication. Khi dùng remote:

1. Client Docker/Maven **xác thực với Artifact Registry** bằng Google identity.
2. Artifact Registry **xác thực với upstream** bằng credentials riêng nếu cần.
3. Credentials upstream nên được lưu trong **Secret Manager** dưới dạng secret version.
4. **Artifact Registry service agent** cần quyền đọc secret đúng phạm vi; chỉ cấp quyền secretAccessor cho secret cần thiết.

**Không nhầm hai lớp credentials:** gcloud Docker credential helper xác thực client tới **REGION-docker.pkg.dev**; upstream Docker Hub username/token là credentials mà **Artifact Registry dùng để kéo artifact từ Docker Hub**.

## 4. Virtual repository: một endpoint, nhiều upstream và priority

### 4.1. Virtual không lưu artifact

Virtual repository là **tập hợp logic** dùng để định tuyến các request **đọc artifact** đến những standard/remote upstream phù hợp.

- Client dùng **một URL virtual** để tải container image hoặc package.
- Virtual có **upstream policy list** chứa repository resource name và priority.
- Artifacts vật lý nằm trong **standard repository** hoặc **cache của remote repository**.
- Lệnh liệt kê images trực tiếp ở virtual và giao diện Console có thể hiển thị **repo trống**, vì virtual **không giữ bản sao artifact**.
- Không upload image/JAR vào virtual, cũng không kỳ vọng chạy cleanup cache trên chính virtual để giải phóng dung lượng.

### 4.2. Priority: **số lớn ưu tiên cao**, khác nhiều hệ thống

Giả sử:

| Upstream | Chế độ | Priority | Có com.company:order-core:1.4.0? |
|---|---|---:|---|
| java-private | Standard | **100** | Có |
| maven-central-cache | Remote | **20** | Có thể có |
| java-legacy | Standard | **10** | Có |

Nếu client yêu cầu **đúng com.company:order-core:1.4.0**, virtual ưu tiên **java-private**. Nếu package/version đó không có trong java-private nhưng có trong maven-central-cache, hệ thống có thể dùng remote theo chính sách.

**Nguyên tắc cần nhớ:**

- **100** ưu tiên cao hơn **20**, không phải ngược lại.
- **Cùng priority:** nếu artifact có ở nhiều upstream đồng hạng, Artifact Registry **có thể trả từ bất kỳ upstream nào trong nhóm đó**. Không thiết kế provenance dựa vào thứ tự khai báo array.
- **Priority chỉ có ý nghĩa khi phân giải được artifact/version tương ứng.** Nếu client chỉ hỏi tên package và để resolver chọn **latest**, kết quả có thể nghiêng về version cao nhất bất kể ưu tiên.

### 4.3. Version pinning quan trọng ngang priority

Giả sử private có **order-core:1.2.0**, nhưng một nguồn public có package trùng tên **order-core:99.0.0**. Nếu client yêu cầu phiên bản “mới nhất” không pin, một resolver có thể chọn version mới hơn ở public.

Do đó cần:

- **Pin version** cho Maven/Gradle, npm, Python và Go theo chiến lược phù hợp.
- Với container image production, ưu tiên **image digest** thay vì tag mutable.
- Với Python, dùng lock file hoặc fully-pinned requirements, kết hợp **hash verification** khi được hỗ trợ.
- Chỉ cấu hình một **virtual endpoint** để resolver không vượt ra trực tiếp các nguồn công khai do client tự tìm.
- Tách **private package names/scopes** và review dependency supply-chain changes.

### 4.4. Rủi ro dependency confusion

**Dependency confusion** xảy ra khi attacker đăng một package public có tên giống package private và cố làm client tải nhầm.

Ví dụ không an toàn:

~~~text
pip index-url       → Private repository
pip extra-index-url → PyPI public

Client so sánh các candidate từ cả hai,
chọn version mới nhất, không bảo đảm ưu tiên private.
~~~

Kiến trúc tốt hơn:

~~~text
pip index-url → Artifact Registry virtual Python
  priority 100: python-private (standard)
  priority 20:  pypi-cache (remote)

Không cấu hình extra-index-url public song song.
~~~

Đây là **biện pháp giảm rủi ro**, không phải bảo đảm tuyệt đối không có package độc hại. Cần thêm dependency review, version/hash pinning, scanning, provenance và IAM.

### 4.5. Quy tắc location/format/permission

- **Upstream cùng format** với virtual repository.
- **Upstream cùng location** (region hoặc multi-region tương ứng) với virtual repository; project có thể khác.
- Virtual sử dụng **Artifact Registry Service Agent** để truy cập upstream; service agent phải được cấp quyền đọc cần thiết, đặc biệt khi upstream thuộc project khác.
- Nguồn ưu tiên cao nhưng không cho service agent đọc **không tương đương tự động fallback an toàn**. Lỗi IAM ở upstream phải được xử lý như sự cố cấu hình, không trông đợi hệ thống bỏ qua một nguồn riêng tư.
- Apt/Yum virtual hỗ trợ ở **Private Preview** và upstream phải là **standard Artifact Registry** theo giới hạn hiện hành.

## 5. Hỗ trợ định dạng và loại upstream

| Format | Remote repository | Virtual repository | Ví dụ upstream hoặc use case |
|---|---|---|---|
| **Docker / OCI** | Có | Có | Docker Hub, GHCR, standard Docker repo |
| **Maven** | Có | Có | Maven Central, standard Maven nội bộ |
| **npm** | Có | Có | npmjs.org, npm private nội bộ |
| **Python** | Có | Có | PyPI, private wheels |
| **Go** | Có theo preset public được hỗ trợ | Có | proxy.golang.org và Go modules |
| **Apt** | **Preview** | **Private Preview** | Debian/Ubuntu preset; virtual upstream standard |
| **Yum** | **Preview** | **Private Preview** | Rocky/EPEL/CentOS preset; virtual upstream standard |
| **Ruby/Conda/Kubeflow templates/generic** | Không mặc định theo danh sách remote/virtual nói trên | Không mặc định theo danh sách trên | Thường dùng standard theo tính năng hiện có |

Các định dạng được Artifact Registry hỗ trợ **ở cấp standard** không mặc nhiên hỗ trợ **remote và virtual modes**. Cần kiểm tra **Supported formats** và **Remote/Virtual overview** tại thời điểm triển khai; các tính năng Preview có điều kiện truy cập và thay đổi nhanh.

### Remote upstream có thể là gì?

| Format | Preset phổ biến | Custom upstream | Artifact Registry standard upstream |
|---|---|---|---|
| Docker | **DOCKER-HUB** | HTTPS registry, GHCR, public.ecr.aws... | Hỗ trợ |
| Maven | **MAVEN-CENTRAL** | HTTPS Maven repository | Hỗ trợ |
| npm | **NPMJS** | HTTPS registry hoặc private upstream | Hỗ trợ |
| Python | **PYPI** | HTTPS Python package repository | Hỗ trợ |
| Go | proxy.golang.org | Theo preset hỗ trợ; không giả định custom Go | Kiểm tra giới hạn format |
| Apt/Yum | Các base upstream được liệt kê trong Preview | Có quy tắc preset riêng, không tùy ý URL như Maven | Theo điều kiện Preview |

Với remote upstream là **Artifact Registry standard** thuộc project khác, cần cấp quyền cho service agent của **remote project**, không chỉ service account build của client. Đây là **một lần xác thực giữa repository services**, tách khỏi quyền read của người dùng vào remote endpoint.

## 6. Kiến trúc triển khai và mô hình phân quyền

### 6.1. Mô hình một project cho lab

| Resource | Type | Format | Purpose |
|---|---|---|---|
| **java-private** | Standard | Maven | Java packages do tổ chức publish |
| **maven-central-cache** | Remote | Maven | Proxy Maven Central |
| **maven-all** | Virtual | Maven | Dependency downloads qua một endpoint |
| **images-private** | Standard | Docker | Images do Cloud Build phát hành |
| **dockerhub-cache** | Remote | Docker | Proxy/cache base images Docker Hub |
| **docker-all** | Virtual | Docker | Pull images qua một endpoint |

Project minh họa là **shop-dev-001**, location **asia-southeast1**. Tất cả tên/ID trong bài là ví dụ chưa tạo, chỉ chạy trên môi trường thực hành được phép và có ngân sách/quota phù hợp.

### 6.2. Mô hình nhiều project

~~~mermaid
flowchart TB
    APP["Project app-ci<br/>Cloud Build"] --> V["Project platform-registry<br/>maven-all virtual"]
    V --> I["Project java-team<br/>java-private standard"]
    V --> P["Project platform-registry<br/>maven-central-cache remote"]
    P --> C["Maven Central"]
    SA["Artifact Registry service agent<br/>của virtual project"] -->|"read upstream"| I
    SA -->|"read upstream"| P
~~~

Nếu upstream repositories ở **project khác**, cấp cho service agent của project sở hữu virtual repo quyền như **roles/artifactregistry.reader** trên upstream (hoặc role tùy biến hẹp theo permission **artifactregistry.repositories.readViaVirtualRepository**). **Không cấp cho toàn bộ người đọc virtual quyền trực tiếp ở project chứa packages private** nếu mục tiêu chỉ là download qua endpoint tập trung.

### 6.3. Các principal khác nhau, quyền khác nhau

| Principal | Nơi cấp | Quyền gợi ý | Tránh |
|---|---|---|---|
| Java developer / build runner | Maven virtual | **roles/artifactregistry.reader** | Writer trên virtual, Admin toàn project |
| Docker runtime/GKE node/Cloud Run deploy identity | Docker virtual hoặc image source | Reader tương ứng | Container registry credential key hardcoded |
| Maven publisher | **java-private standard** | **roles/artifactregistry.writer** | Publish vào virtual hoặc remote |
| Cloud Build image publisher | **images-private standard** | Writer | Admin chỉ để push image |
| Artifact Registry service agent của virtual | Upstream repos | Reader hoặc quyền readViaVirtualRepository phù hợp | Cấp Editor/Owner toàn project |
| Remote service agent | Upstream private registry/Secret Manager | Quyền upstream cần thiết và **secretAccessor** đúng secret | Lưu upstream token trong source |
| Platform registry admin | Repository/project cần quản trị | Artifact Registry Admin | Dùng Admin trong build/runtime không cần thiết |

Với **GKE** hoặc **Cloud Run**, hãy xác định **identity thực tế thực hiện image pull** theo sản phẩm/triển khai, thay vì mặc nhiên cấp quyền Reader cho Java service account của ứng dụng. Một image được pull lúc deploy thường do các service agents hoặc identities khác với identity chạy code Java.

## 7. Điều kiện trước khi thực hành

Cần có:

1. Project **shop-dev-001** với **billing** và **Artifact Registry API** được bật.
2. Gcloud CLI mới, đăng nhập principal được quyền quản trị repositories cho lab.
3. Biết location hợp lệ cho định dạng sản phẩm; kiểm tra bằng **gcloud artifacts locations list**.
4. Quyền quản trị repo (**roles/artifactregistry.admin**) tại project thực hành; về production dùng IAM least privilege.
5. Maven/Gradle hoặc Docker client để kiểm thử, cùng plugin/credential helper phù hợp.
6. Nếu upstream yêu cầu authentication, có **Secret Manager API, secret version và Service Agent IAM**.
7. Đã xem tổ chức có dùng **VPC Service Controls**, CMEK, scanning hoặc policies bắt buộc hay không.

~~~bash
# Lệnh chỉ đọc hoặc bật API theo quyền được giao.
gcloud config get-value project
gcloud artifacts locations list
gcloud artifacts repositories list \
  --project=shop-dev-001 \
  --location=asia-southeast1

# Thao tác quản trị có tác động, chỉ chạy khi được phép.
gcloud services enable artifactregistry.googleapis.com \
  --project=shop-dev-001
~~~

**Không áp dụng lab trực tiếp lên production.** Việc tạo repository, cache artifacts, cấp IAM, scan hoặc tải packages có thể phát sinh chi phí và tạo resources cần dọn theo kế hoạch.

## 8. Thực hành A — Maven standard + remote + virtual

**Mục tiêu:** Java build chỉ đọc dependencies qua **maven-all**, trong đó private Maven có ưu tiên cao hơn Maven Central proxy.

### 8.1. Tạo standard Maven repository

~~~bash
gcloud artifacts repositories create java-private \
  --project=shop-dev-001 \
  --repository-format=maven \
  --mode=standard-repository \
  --location=asia-southeast1 \
  --description="Private Java packages"
~~~

Repo **java-private** là đích xuất bản các JAR/POM công ty. Nó không tự có **com.company:order-core** cho tới khi publisher dùng Maven/Gradle triển khai package.

### 8.2. Tạo remote Maven Central

~~~bash
gcloud artifacts repositories create maven-central-cache \
  --project=shop-dev-001 \
  --repository-format=maven \
  --mode=remote-repository \
  --remote-mvn-repo=MAVEN-CENTRAL \
  --location=asia-southeast1 \
  --description="Cached dependencies from Maven Central"
~~~

Đây là remote **read-only**. Tài khoản build sẽ xác thực với **Artifact Registry** khi đọc. Maven Central public không nhất thiết cần username/password, nhưng nếu upstream yêu cầu authentication thì phải bổ sung secret theo phần sau.

### 8.3. Xác minh upstream đã tạo

~~~bash
gcloud artifacts repositories describe java-private \
  --project=shop-dev-001 --location=asia-southeast1

gcloud artifacts repositories describe maven-central-cache \
  --project=shop-dev-001 --location=asia-southeast1
~~~

Xác nhận **format=MAVEN**, **mode=STANDARD_REPOSITORY/REMOTE_REPOSITORY**, đúng location và **remoteRepositoryConfig** trỏ Maven Central.

### 8.4. Định nghĩa upstream policy JSON

Trong thư mục CLI bạn quản lý, tạo file **maven-upstreams.json**:

~~~json
[
  {
    "id": "internal",
    "repository": "projects/shop-dev-001/locations/asia-southeast1/repositories/java-private",
    "priority": 100
  },
  {
    "id": "public-maven-central",
    "repository": "projects/shop-dev-001/locations/asia-southeast1/repositories/maven-central-cache",
    "priority": 20
  }
]
~~~

Đây là **JSON input cho lệnh gcloud**, không phải Terraform hoặc Kubernetes manifest:

- **id** là định danh duy nhất của một upstream policy entry.
- **repository** phải là resource path đầy đủ của repo cùng **format/location**.
- **priority** là số nguyên; **100 > 20**, nên private được ưu tiên nếu hai repo có đúng artifact/version được yêu cầu.

Lưu file policy trong source control **không chứa secrets** để review thay đổi ưu tiên, thêm/bớt upstream theo quy trình IaC. Không đưa password/token trực tiếp vào JSON.

### 8.5. Tạo virtual Maven repository

~~~bash
gcloud artifacts repositories create maven-all \
  --project=shop-dev-001 \
  --repository-format=maven \
  --mode=virtual-repository \
  --location=asia-southeast1 \
  --description="Maven dependencies via private-first routing" \
  --upstream-policy-file=maven-upstreams.json

gcloud artifacts repositories describe maven-all \
  --project=shop-dev-001 \
  --location=asia-southeast1
~~~

Đọc **virtualRepositoryConfig.upstreamPolicies** để xác nhận hai resource paths và priority. Virtual repo không chứa bản sao packages; việc list packages ở virtual có thể trống.

### 8.6. Cấu hình Maven client chỉ đọc qua maven-all

Artifact Registry hỗ trợ **Maven wagon credential helper**. Trước tiên xem cấu hình chính thức do CLI sinh:

~~~bash
gcloud artifacts print-settings mvn \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --repository=maven-all
~~~

Ví dụ đoạn đặt trong **pom.xml** của dự án Java:

~~~xml
<repositories>
  <repository>
    <id>central</id>
    <name>Company Maven virtual repository</name>
    <url>artifactregistry://asia-southeast1-maven.pkg.dev/shop-dev-001/maven-all</url>
    <releases><enabled>true</enabled></releases>
    <snapshots><enabled>true</enabled></snapshots>
  </repository>
</repositories>
<build>
  <extensions>
    <extension>
      <groupId>com.google.cloud.artifactregistry</groupId>
      <artifactId>artifactregistry-maven-wagon</artifactId>
      <version>2.2.5</version>
    </extension>
  </extensions>
</build>
~~~

Đây là **các đoạn thuộc pom.xml hoàn chỉnh**, không phải một file XML độc lập vì có nhiều root elements. Phiên bản plugin minh họa theo tài liệu hiện hành; trong dự án thật lấy cấu hình từ **gcloud artifacts print-settings mvn** và khóa version theo quy trình của tổ chức.

**Vì sao id=central?** Maven Super POM mặc định có Maven Central. Khi muốn ghi đè repository Central bằng endpoint nội bộ, sử dụng id phù hợp và xem **effective POM/settings**. Cần kiểm tra cả **pluginRepositories**, Maven profiles và CI init settings để bảo đảm build không còn một đường trực tiếp khác đến Maven Central.

### 8.7. Kiểm thử Maven resolution

Giả sử pom.xml có dependency cố định:

~~~xml
<dependency>
  <groupId>org.slf4j</groupId>
  <artifactId>slf4j-api</artifactId>
  <version>2.0.16</version>
</dependency>
~~~

Trên môi trường đã có Maven và ADC authentication phù hợp:

~~~bash
mvn -U dependency:tree
~~~

Theo dõi log Maven: artifacts được tải qua **asia-southeast1-maven.pkg.dev/.../maven-all**, không lén tải một bản khác trực tiếp từ repo.maven.apache.org. Cần bảo đảm runner có **roles/artifactregistry.reader** và các token ADC hợp lệ.

### 8.8. Kiểm thử private-first

Sau khi publisher đã phát hành một phiên bản thử nghiệm của **com.company:order-core:1.4.0** vào **java-private**, kiểm tra:

1. Yêu cầu **đúng version 1.4.0** qua Maven virtual.
2. Ghi nhận nó được phục vụ từ upstream private theo chính sách.
3. Thử package không có trong private nhưng có trên Maven Central: remote được dùng.
4. Với dependency không tồn tại ở cả hai nguồn, phải thất bại.
5. Kiểm tra entitlement: một caller không có quyền Reader trên virtual phải bị từ chối.

**Không tự upload artifact thử nghiệm vào Maven Central** để mô phỏng attack; dùng repository lab có dữ liệu kiểm soát nếu muốn kiểm tra trùng package/version an toàn.

## 9. Thực hành B — Docker Hub remote và Docker virtual

**Mục tiêu:** một pipeline sử dụng base images từ Docker Hub và image tự phát hành trong **images-private**, nhưng runtime có thể pull qua một endpoint **docker-all**.

### 9.1. Tạo Docker standard repository

~~~bash
gcloud artifacts repositories create images-private \
  --project=shop-dev-001 \
  --repository-format=docker \
  --mode=standard-repository \
  --location=asia-southeast1 \
  --description="Private container images"
~~~

Đây là repository để publisher **push**. Với image Java API:

~~~text
asia-southeast1-docker.pkg.dev/shop-dev-001/images-private/orders-api:1.0.0
~~~

Tag là một tên tham chiếu dễ đọc; image content thực còn có **sha256 digest**. Khi phát hành production, ghi nhận digest để có khả năng tái tạo deployment chính xác.

### 9.2. Tạo remote Docker Hub

~~~bash
gcloud artifacts repositories create dockerhub-cache \
  --project=shop-dev-001 \
  --repository-format=docker \
  --mode=remote-repository \
  --remote-docker-repo=DOCKER-HUB \
  --location=asia-southeast1 \
  --description="Docker Hub proxy and cache"
~~~

Lệnh trên minh họa public upstream. Nếu cần xác thực Docker Hub để tránh giới hạn anonymous pull hoặc truy cập repository private, dùng **--remote-username** và **--remote-password-secret-version** với secret trong Secret Manager; **không đưa password plaintext vào lệnh hoặc source**.

### 9.3. Tạo Docker virtual theo priority

File **docker-upstreams.json**:

~~~json
[
  {
    "id": "company-images",
    "repository": "projects/shop-dev-001/locations/asia-southeast1/repositories/images-private",
    "priority": 100
  },
  {
    "id": "docker-hub",
    "repository": "projects/shop-dev-001/locations/asia-southeast1/repositories/dockerhub-cache",
    "priority": 10
  }
]
~~~

~~~bash
gcloud artifacts repositories create docker-all \
  --project=shop-dev-001 \
  --repository-format=docker \
  --mode=virtual-repository \
  --location=asia-southeast1 \
  --description="Private-first Docker image pulls" \
  --upstream-policy-file=docker-upstreams.json

gcloud artifacts repositories describe docker-all \
  --project=shop-dev-001 \
  --location=asia-southeast1
~~~

### 9.4. Đăng nhập Docker đến Artifact Registry

~~~bash
gcloud auth list
gcloud auth configure-docker asia-southeast1-docker.pkg.dev
~~~

Lệnh **configure-docker** ghi cấu hình credential helper cho Docker client hiện tại. Với Linux chạy Docker qua **sudo**, user/root có thể đọc các file cấu hình Docker khác nhau; đảm bảo người thực thi Docker và credential helper dùng đúng identity.

**Không nhầm:** bước này chỉ xác thực **Docker client → Artifact Registry**. Docker Hub upstream authentication, nếu cần, được quản lý riêng bởi remote repo.

### 9.5. Pull base image qua remote và virtual

~~~bash
# Pull trực tiếp qua remote để làm nóng cache
docker pull \
  asia-southeast1-docker.pkg.dev/shop-dev-001/dockerhub-cache/busybox:1.36

# Pull qua virtual: chọn upstream theo policy
docker pull \
  asia-southeast1-docker.pkg.dev/shop-dev-001/docker-all/busybox:1.36
~~~

Vì **images-private** chưa có package **busybox:1.36**, virtual có thể lấy từ **dockerhub-cache**, remote tải từ Docker Hub nếu chưa cache. Khi đã cache, remote có thể phục vụ mà không tải lại blob cho mỗi request.

**Thay image tag bằng version/digest được tổ chức phê duyệt.** Nếu tag upstream thay đổi, cache metadata và content có thể khiến kết quả khác vào những thời điểm khác nhau; không dùng **latest** làm khóa phát hành không đổi.

### 9.6. Push image nội bộ vào standard

Giả sử bạn đã build image **orders-api:1.0.0** từ source đáng tin cậy:

~~~bash
docker tag orders-api:1.0.0 \
  asia-southeast1-docker.pkg.dev/shop-dev-001/images-private/orders-api:1.0.0

docker push \
  asia-southeast1-docker.pkg.dev/shop-dev-001/images-private/orders-api:1.0.0
~~~

Thao tác này yêu cầu **roles/artifactregistry.writer** hoặc quyền phù hợp trên **images-private**. Không thể đổi đích push thành **docker-all** hoặc **dockerhub-cache**, vì hai loại repo đó là **read-only**.

Sau đó thử:

~~~bash
docker pull \
  asia-southeast1-docker.pkg.dev/shop-dev-001/docker-all/orders-api:1.0.0
~~~

Virtual sẽ tìm image trong standard private theo priority nếu có. Đối với môi trường production, tốt nhất ghi lại **digest của image đã build và kiểm chứng** trước khi deploy; việc pull lại một tag không bảo đảm không có thay đổi trong quá trình build/release.

### 9.7. Kiểm tra gói trong remote và virtual

~~~bash
gcloud artifacts packages list \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --repository=dockerhub-cache

gcloud artifacts docker images list \
  asia-southeast1-docker.pkg.dev/shop-dev-001/images-private
~~~

**Không dùng kết quả list của virtual để kết luận repository trống:** virtual không có storage riêng nên **gcloud artifacts docker images list** hoặc UI có thể không hiện images của upstream. Kiểm tra standard và remote repositories, rồi thực hiện **pull thực tế qua virtual endpoint** để xác nhận routing.

### 9.8. Deployment container dùng đúng identity

Khi GKE hoặc Cloud Run dùng image trong Artifact Registry, cần kiểm tra:

- **Identity thực hiện image pull** của sản phẩm có quyền đọc repository.
- Image URL và **location** đúng; repo **docker-all** chỉ là endpoint virtual, không phải backend service.
- Cloud Run service account chạy ứng dụng có quyền dữ liệu runtime (ví dụ Cloud Storage/Cloud SQL), **khác** các quyền deployment/image pull.
- Nếu image private bị xoá hoặc repo đổi permission, các lần **scale out, rollout, restart** có thể thất bại dù container hiện tại vẫn đang chạy.
- Chỉ cho production pull images đã kiểm soát bằng **digest**, attestation/provenance hoặc cơ chế Binary Authorization nếu tổ chức áp dụng.

## 10. Thực hành C — Cấu hình Python, npm và Go theo cùng nguyên tắc

Bài chính sử dụng Maven và Docker, nhưng virtual repository đặc biệt hữu ích với **Python pip** vì cơ chế phân giải nhiều indexes.

### 10.1. Python: một index-url duy nhất

Giả sử tổ chức có:

- **python-private** (standard).
- **pypi-cache** (remote, upstream PyPI).
- **python-all** (virtual, private priority 100, remote priority 20).

File **pip.conf** minh họa:

~~~ini
[global]
index-url = https://asia-southeast1-python.pkg.dev/shop-dev-001/python-all/simple/
~~~

Điều quan trọng là **không thêm extra-index-url=https://pypi.org/simple** nếu mục tiêu là kiểm soát thứ tự upstream tại Artifact Registry. Khi có nhiều indexes, **pip không bảo đảm ưu tiên private** và có thể chọn phiên bản cao hơn từ public.

Đối với workstation, Google Cloud khuyến nghị **keyrings.google-artifactregistry-auth** để làm mới credentials; với automation có thể dùng **access token ngắn hạn** hoặc cơ chế xác thực tương thích. Tránh nhúng access token vào pip.conf được commit vào source.

~~~bash
# Kiểm thử sau khi đã cấu hình Python credential helper và IAM.
python -m pip index versions requests
python -m pip install "requests==2.32.3"
~~~

Các lệnh trên chỉ là kiểm thử với package công khai phổ biến; phiên bản được đưa ra là **ví dụ** chứ không phải khuyến nghị chọn phiên bản mới nhất/an toàn nhất. Trong production, dựa vào lockfile, vulnerability review và version đã kiểm thử.

### 10.2. npm: một registry endpoint và lockfile

Ví dụ cấu hình **.npmrc** cho virtual npm:

~~~ini
registry=https://asia-southeast1-npm.pkg.dev/shop-dev-001/npm-all/
always-auth=true
~~~

Cần cấu hình npm authentication phù hợp theo hướng dẫn **gcloud artifacts print-settings npm**, không commit npm auth token vào repository. Với package nội bộ, ưu tiên **scoped package names** như **@company/order-client** và lockfile.

Nếu **npmrc** còn cấu hình scope khác trỏ thẳng tới npmjs.org, một số package vẫn bypass virtual endpoint. Hãy kiểm tra **npm config get registry**, per-scope mappings và **npm ci** trong môi trường CI sạch.

### 10.3. Go: GOPROXY và module versions

Với Go modules, virtual Go repository có thể làm nguồn tải theo các upstream hỗ trợ. Client cần cấu hình **GOPROXY** phù hợp với Artifact Registry, authentication và cách kiểm tra checksum/version.

Không coi **GOPROXY=proxy.golang.org,direct** là chính sách dùng virtual duy nhất; phần **direct** có thể cho phép truy cập nguồn ngoài kiểm soát khi proxy không đáp ứng. Với private modules, cần thiết kế **GOPRIVATE**, checksum policy và quyền module server đúng cách.

### 10.4. Không trộn các package formats

Maven, npm, pip, Go và Docker có URL, authentication mechanism và caching semantics khác nhau. Không dùng **docker-all** làm Maven repository hay ngược lại, dù cùng project/location. Khi ứng dụng hỗn hợp Java/Node/Python, tạo **virtual riêng cho từng format** cần sử dụng.

## 11. Điều chỉnh upstream policy khi thêm hoặc đổi nguồn

Một virtual repository có thể **thêm/bớt upstream hoặc chỉnh priority** sau khi được tạo.

Ví dụ tổ chức thêm một Maven standard repo **java-security-reviewed** chứa packages đã được phê duyệt:

~~~json
[
  {
    "id": "security-reviewed",
    "repository": "projects/shop-dev-001/locations/asia-southeast1/repositories/java-security-reviewed",
    "priority": 200
  },
  {
    "id": "internal",
    "repository": "projects/shop-dev-001/locations/asia-southeast1/repositories/java-private",
    "priority": 100
  },
  {
    "id": "public-maven-central",
    "repository": "projects/shop-dev-001/locations/asia-southeast1/repositories/maven-central-cache",
    "priority": 20
  }
]
~~~

Sau khi tạo **java-security-reviewed** thực sự, cấp quyền service agent và review ảnh hưởng, lưu file thành **maven-upstreams.json**, rồi chạy:

~~~bash
gcloud artifacts repositories update maven-all \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --upstream-policy-file=maven-upstreams.json

gcloud artifacts repositories describe maven-all \
  --project=shop-dev-001 \
  --location=asia-southeast1
~~~

**Lệnh update có tác động lên mọi client dùng virtual.** Nếu cùng package/version tồn tại ở nhiều upstream, việc đổi priority có thể thay đổi nguồn artifact được tải trong build mới. Cần:

1. Diff policy file cũ và mới.
2. Kiểm tra tên artifact/version có thể bị shadow.
3. Chạy build/test ở staging với **clean dependency caches** khi cần.
4. Xác minh checksum/digest của artifact tải về.
5. Triển khai có kiểm soát và chuẩn bị rollback bằng policy file cũ.

Nếu muốn xóa tất cả upstream, file chính sách có thể chứa **[]**, nhưng mọi client tải qua virtual sẽ không còn nơi tìm artifact. Không dùng thao tác này như cleanup routine.

## 12. IAM, service agents và Secret Manager

### 12.1. Hai đường đọc khác nhau

Một yêu cầu đọc virtual đi qua hai lớp quyền:

~~~text
Client (Maven/Docker)
  ├─ IAM quyền đọc tại virtual repository
  ↓
Artifact Registry virtual service
  ├─ Artifact Registry Service Agent có quyền đọc upstream
  ↓
Upstream standard/remote repository
  ↓
Artifact
~~~

Client cần quyền Reader tại **virtual**, còn **service agent** cần quyền truy cập upstream. Nếu chỉ cấp Reader cho client tại virtual nhưng service agent không thể truy cập một upstream khác project, request có thể bị lỗi dù client không sai.

### 12.2. Service agent có dạng nào?

Định dạng service agent của Artifact Registry:

~~~text
service-PROJECT_NUMBER@gcp-sa-artifactregistry.iam.gserviceaccount.com
~~~

**PROJECT_NUMBER** là số project, không phải project ID. Với virtual repo trong project **platform-registry-001** và upstream ở project **java-team-001**, grant tương ứng:

~~~bash
# Ví dụ lấy số project chứa virtual.
gcloud projects describe platform-registry-001 \
  --format="value(projectNumber)"

# Sau khi thay VIRTUAL_PROJECT_NUMBER bằng giá trị thật:
gcloud artifacts repositories add-iam-policy-binding java-private \
  --project=java-team-001 \
  --location=asia-southeast1 \
  --member="serviceAccount:service-VIRTUAL_PROJECT_NUMBER@gcp-sa-artifactregistry.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.reader"
~~~

Ví dụ trên cấp Reader trên **một upstream repository**. Nếu upstream rất nhiều, có thể cấp Reader ở project upstream, nhưng phạm vi rộng hơn; cân nhắc custom role với **artifactregistry.repositories.readViaVirtualRepository** theo tài liệu để giảm quyền.

### 12.3. Remote có upstream Artifact Registry standard khác project

Khi **remote repo** sử dụng một Artifact Registry standard repo ở project khác làm upstream, tài liệu remote mô tả việc cấp quyền cho **remote project's Artifact Registry service agent** trên upstream. Trong ví dụ role có thể là **roles/artifactregistry.serviceAgent** theo hướng dẫn của remote upstream, **khác** role/permission khuyến nghị cho virtual upstream.

**Không sao chép nguyên IAM binding virtual sang remote hoặc ngược lại** chỉ vì cả hai đều có chữ upstream. Kiểm tra hướng dẫn của đúng repository mode, principal và permission; ưu tiên quyền thấp nhất thực sự hoạt động.

### 12.4. Secret Manager cho private Docker Hub upstream

Giả sử doanh nghiệp có Docker Hub username **DOCKERHUB_USER** và access token lưu trong Secret Manager:

~~~text
projects/shop-dev-001/secrets/dockerhub-token/versions/1
~~~

Lệnh tạo remote có authentication:

~~~bash
gcloud artifacts repositories create dockerhub-auth-cache \
  --project=shop-dev-001 \
  --repository-format=docker \
  --mode=remote-repository \
  --remote-docker-repo=DOCKER-HUB \
  --remote-username=DOCKERHUB_USER \
  --remote-password-secret-version=projects/shop-dev-001/secrets/dockerhub-token/versions/1 \
  --location=asia-southeast1
~~~

**Không nhập token trực tiếp ở command line**; token phải tồn tại trước dưới dạng **secret version** và Artifact Registry service agent phải có quyền Secret Manager Secret Accessor trên secret phù hợp.

Lưu ý khi vận hành:

- Secret trong docs/code không được chứa password thật.
- Khi rotate Docker Hub token, có thể phải cập nhật cấu hình remote repo với **secret version mới** theo tính năng được hỗ trợ.
- Không dùng một token Docker Hub cá nhân có quyền rộng cho toàn bộ doanh nghiệp nếu có lựa chọn tài khoản/permission phù hợp hơn.
- Nếu Secret Manager IAM thiếu, repo có thể tạo nhưng fetch upstream thất bại tùy bước validation/config; kiểm tra service agent và Cloud Audit Logs.
- **Docker client không cần biết token Docker Hub** khi sử dụng Artifact Registry remote, chỉ cần Google Cloud identity có quyền đọc remote.

## 13. Security và software supply chain

### 13.1. Remote cache không làm artifact an toàn tự động

Một package độc hại đã nằm trên public registry vẫn có thể được remote repository tải về và cache. Cache giảm phụ thuộc mạng, **không thẩm định chữ ký, license hay logic phần mềm tự động**.

Áp dụng phòng thủ nhiều lớp:

| Lớp | Kiểm soát phù hợp |
|---|---|
| **Source selection** | Virtual private-first, chỉ cho phép upstream đã phê duyệt |
| **Version identity** | Pin package version, checksum/hash, Docker image digest |
| **Provenance** | Build attestations, signed artifacts/SBOM theo công cụ và phạm vi được hỗ trợ |
| **Vulnerability awareness** | Artifact Analysis, vulnerability scanning theo format và repository policy |
| **Deployment policy** | Binary Authorization cho GKE/Cloud Run nếu mô hình triển khai hỗ trợ |
| **Identity** | IAM Reader/Writer tối thiểu, Workload Identity Federation cho CI ngoài GCP |
| **Secrets** | Secret Manager, không hardcode registry token |
| **Governance** | Change review, cleanup retention, audit logs, dependency review |

### 13.2. Priority không ngăn artifact độc hại đã có trong private

Nếu **java-private** ưu tiên 100 nhưng publisher nội bộ bị chiếm quyền và push JAR sai, virtual vẫn chọn artifact ở nguồn **ưu tiên cao nhất**. Vì vậy:

- Bảo vệ quyền **Writer** lên standard repository.
- Tách **publisher identity** theo pipeline/team.
- Bật provenance/signature checks và scan theo nhu cầu.
- Dùng kiểm thử tương thích và phê duyệt release.
- Hạn chế quyền xóa/overwrite những phiên bản đã phát hành khi định dạng cho phép.

### 13.3. Docker tags và digests

~~~text
Image theo tag:
asia-southeast1-docker.pkg.dev/shop-dev-001/docker-all/orders-api:1.0.0

Image theo digest (minh họa, không phải digest thật):
asia-southeast1-docker.pkg.dev/shop-dev-001/docker-all/orders-api@sha256:<64-HEX-CHARS>
~~~

**Tag** có thể mutable theo policy; **digest** biểu diễn content-addressed artifact cụ thể. Với images từ remote Docker Hub, việc pin digest giảm rủi ro do upstream tag thay đổi. Vẫn cần xác nhận digest đến từ nguồn được phê duyệt và scan để tránh “pin một artifact độc hại” lâu dài.

### 13.4. SBOM, vulnerability scanning và Artifact Analysis

Artifact Registry có thể tích hợp **Artifact Analysis** để thu thập metadata và quét lỗ hổng cho các loại artifacts theo khả năng/điều kiện kích hoạt. Remote cached artifacts cũng có thể được phân tích nếu phạm vi scanning hỗ trợ.

**Không mặc định toàn bộ package Maven/npm/Python và mọi remote artifact đều được scan theo cùng lịch và cùng mức độ.** Kiểm tra format được hỗ trợ, chính sách scan, quyền, giá và kết quả thực tế. Một kết quả “không có finding” **không chứng minh không có lỗ hổng**.

### 13.5. Dependency license và data governance

Một remote cache có thể lưu third-party artifact trong project doanh nghiệp. Cần xem:

- License/compliance khi tái phân phối hoặc lưu bản cache.
- Data residency/location của repository.
- Retention, cleanup và dữ liệu nhạy cảm trong private packages.
- Những secret vô tình được build vào image/JAR hoặc metadata.
- Khả năng truy cập của teams qua virtual endpoint và IAM.

Chọn region gần runtimes có thể giảm latency và truyền dữ liệu, nhưng phải tuân thủ chính sách dữ liệu và khả năng hỗ trợ sản phẩm.

## 14. VPC Service Controls, networking và tính sẵn sàng

### 14.1. Artifact Registry remote đi ra upstream bằng đường nào?

Remote repo là dịch vụ quản lý của Google Cloud, không phải một VM trong VPC của bạn. Vì vậy:

- Việc tạo **Cloud NAT** cho VM build không tự bảo đảm remote service truy cập một upstream private.
- Upstream remote **phải có endpoint được Artifact Registry hỗ trợ và truy cập được**; private VPC-only endpoint không được hỗ trợ theo hạn chế remote.
- Nếu remote repo nằm trong **VPC SC perimeter**, cần cấu hình cho phép **egress tới external upstream** theo tài liệu Artifact Registry/VPC SC.

### 14.2. Cached artifact không bảo đảm offline vô điều kiện

Giả sử Maven Central outage:

| Tình huống | Hành vi kỳ vọng |
|---|---|
| Build dùng version đã cache, cache còn hiệu lực | Có thể tiếp tục tải |
| Build yêu cầu version chưa từng cache | Có thể thất bại |
| Package index/metadata cần refresh và upstream down | Có thể phát sinh lỗi hoặc dùng dữ liệu cached theo quy tắc |
| Artifact bị cleanup/delete | Không còn copy cached để phục vụ |
| Client thiếu IAM hoặc token hết hạn | Vẫn thất bại dù cache có dữ liệu |

Giải pháp vận hành:

1. **Pin dependencies** và kiểm thử build từ cache.
2. Đối với production critical artifacts, cân nhắc **publish/mirror bản đã kiểm duyệt vào standard repo** theo quy trình có quyền Writer và lưu giữ phù hợp, thay vì chỉ tin vào cache remote.
3. Theo dõi HTTP errors, repository request counts, upstream availability và quota.
4. Có rollback version/deployment đã biết tốt.

### 14.3. Cloud Build, GKE và Cloud Run

- **Cloud Build:** service account của build phải có Reader khi tải dependencies/base images và Writer khi push output lên standard. Nếu dùng **custom worker pool** hoặc restricted network, xem cấu hình kết nối và Artifact Registry endpoint.
- **GKE:** nodes hoặc principal theo cơ chế image pull cần Reader trên Docker repo tương ứng; không nhầm với Kubernetes ServiceAccount/RBAC dành cho API ứng dụng.
- **Cloud Run:** triển khai image từ repository được phép; kiểm tra quyền truy cập xuyên project, danh tính pull và runtime service account riêng.
- **Compute Engine:** VM build/pull phải có OAuth scopes/IAM phù hợp, hoặc credential helper/token theo môi trường; đừng dùng legacy service account keys khi có workload identity/ADC.

### 14.4. Không coi virtual là load balancer HTTP đa chức năng

Virtual không thực hiện arbitrary path rewriting, health checks hay network failover cho ứng dụng. Nó giải quyết **artifact lookup/routing** giữa repositories, không thay thế Application Load Balancer, Private Service Connect, CDN, Cloud NAT hay VPC peering.

## 15. Cleanup policies, version retention và chi phí

### 15.1. Phân biệt storage của từng mode

| Chế độ | Chi phí cần chú ý | Vấn đề dung lượng |
|---|---|---|
| **Standard** | Stored artifact bytes, read/write operations, network/analysis theo bảng giá | Artifacts phát hành có thể tích lũy lâu năm |
| **Remote** | Cache storage, egress/operations, scanning và upstream liên quan | Cache tăng theo những packages được yêu cầu |
| **Virtual** | Không lưu blob riêng; read requests/operations và dịch vụ upstream theo chính sách giá | Không có “virtual cache” để dọn như standard/remote |

Chi phí cụ thể phụ thuộc **region, egress path, kích thước artifact, số pulls, tần suất refresh, vulnerability scanning** và chính sách giá Artifact Registry đang áp dụng. Không nên tự giả định remote cache luôn tiết kiệm tiền hơn mọi phương án khác.

### 15.2. Cleanup policies

Artifact Registry có **cleanup policies** để xóa những versions không cần thiết theo điều kiện tuổi/tag hoặc giữ lại số lượng nhất định, với khả năng **dry-run** tùy cấu hình.

Nguyên tắc:

- Với **standard**, giữ lại các bản release/digest đang deploy hoặc cần rollback.
- Với **remote**, xóa cache không dùng có thể giảm dung lượng nhưng cũng có thể làm request sau phải fetch lại từ upstream.
- Với **virtual**, quản lý **upstream policies** chứ không chạy cleanup trên một kho artifact vật lý không tồn tại.
- Nếu cần artifact offline đáng tin cậy, tránh cleanup làm mất bản duy nhất đã được scan/approved.
- Đọc retention, immutable tags, constraints và dry-run results trước khi bật cleanup destructive.

### 15.3. Thu gom dữ liệu không dùng

Định kỳ:

1. Liệt kê repositories, format, mode, location, owners.
2. Kiểm tra số lượng/dung lượng packages và tần suất pull.
3. Xác định artifacts đang được deploy, pinned trong lockfiles hoặc cần phục hồi.
4. Review policies trước khi xóa; không xóa toàn repository đang phục vụ virtual endpoint.
5. Theo dõi tác động lên build latency, cache miss, lỗi upstream và chi phí sau cleanup.

## 16. Troubleshooting: repository có nhưng không tải được artifact

| Triệu chứng | Nguyên nhân hay gặp | Cách kiểm tra |
|---|---|---|
| **401 Unauthorized** khi Docker pull | Chưa cấu hình credential helper hoặc token hết hạn | gcloud auth list, configure-docker, Docker config, identity |
| **403 Forbidden** khi pull virtual | Client thiếu Reader ở virtual hoặc service agent thiếu quyền upstream | Virtual IAM, upstream IAM và service agent |
| **403** khi build push virtual | Virtual **read-only** | Push vào **standard** với role Writer |
| **403** khi Docker Hub remote fetch | Upstream token không hợp lệ hoặc thiếu Secret Manager permissions | Remote config, secret version, service agent, Docker Hub account |
| **404 Not Found** qua virtual | Package/version không có ở bất kỳ upstream đủ điều kiện | Version pin, upstream content, policy, location/format |
| **404** dù package có ở upstream private | Service agent không đọc được, policy sai resource name hoặc metadata chưa cập nhật | Upstream IAM, repository path và logs |
| Docker pull **429 Too Many Requests** | Upstream Docker Hub rate limit, nhiều cache misses | Cấu hình upstream authentication, monitor quota, cache policy |
| Build Java chọn bản public khác mong muốn | Maven vẫn dùng Central trực tiếp, version không pin hoặc priority sai | Effective POM/settings, priority, resolved dependency tree |
| pip chọn public package mới hơn private | Có **extra-index-url** public, chọn latest không pin | pip config, requirements/lockfile, virtual-only index |
| Maven tải plugin từ Internet | Chưa quản lý **pluginRepositories** hoặc Super POM/profile khác | effective settings/POM, build logs |
| Docker virtual hiển thị “trống” | Virtual không lưu blobs | Kiểm tra standard/remote và thử pull qua virtual |
| Cache trả tag/metadata cũ | Metadata update age, mutable Docker tags, client cache | Digest pin, cache freshness, retry sau interval |
| Remote không tới private Nexus | Upstream chỉ có private IP trong VPC/on-prem | Remote cần upstream HTTPS internet-accessible được hỗ trợ |
| Remote fetch lỗi trong VPC SC | Egress upstream ngoài perimeter bị chặn | VPC SC policies và Artifact Registry remote access exceptions |
| Chuyển region khiến virtual creation lỗi | Upstream khác location với virtual | Cùng format và location; tạo/migrate repo đúng nơi |
| Không thấy package sau cleanup | Cache/standard artifact bị xóa | Cleanup policy, audit logs, upstream availability |
| IAM đúng nhưng image deploy thất bại | Identity image pull khác runtime identity, quota hoặc image digest không tồn tại | GKE/Cloud Run deploy logs, image URL/digest, Reader role |

### 16.1. Chẩn đoán từng bước

1. **Repository:** kiểm tra **format, mode, project và location** bằng gcloud describe.
2. **Client identity:** xác định user/service account nào thật sự gửi request; xem token hết hạn hay không.
3. **Endpoint:** client đang dùng **virtual**, **remote**, **standard** hay public registry trực tiếp?
4. **Upstream policy:** nếu virtual, kiểm tra **resource path và priority**; có cùng format/location không?
5. **Service agent:** có được phép đọc upstream? Với private upstream external, Secret Manager credentials đúng không?
6. **Artifact version:** package và version có thực sự tồn tại ở upstream? Nếu chỉ hỏi latest, có pin version không?
7. **Upstream/cache:** remote đã cache artifact chưa, metadata còn mới không, upstream có rate-limit/outage không?
8. **Security perimeter:** IAM deny, VPC SC, org policy, CMEK hoặc license restriction?
9. **Log/metrics:** Artifact Registry request logs, audit logs, Cloud Build/GKE/Cloud Run errors và request counts.
10. **Rollback:** nếu vừa sửa priority, trả policy file cũ hoặc quay lại image/library version đã kiểm duyệt.

### 16.2. Một chuỗi lệnh chỉ đọc hữu ích

~~~bash
gcloud artifacts repositories list \
  --project=shop-dev-001 --location=asia-southeast1

gcloud artifacts repositories describe maven-all \
  --project=shop-dev-001 --location=asia-southeast1

gcloud artifacts repositories describe maven-central-cache \
  --project=shop-dev-001 --location=asia-southeast1

gcloud artifacts repositories get-iam-policy maven-all \
  --project=shop-dev-001 --location=asia-southeast1

gcloud artifacts packages list \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --repository=maven-central-cache
~~~

Khi debug lỗi permission, không mặc định repo upstream nằm cùng project. Xem resource path **projects/.../locations/.../repositories/...** trong virtual policy và grants ở project tương ứng.

## 17. Tình huống triển khai: nền tảng Java và container dùng chung

Doanh nghiệp **Hưng Thịnh** có 30 services:

- 15 Java/Spring Boot services dùng Maven và thư viện doanh nghiệp.
- 10 APIs chạy trên Cloud Run; 5 workers chạy trên GKE.
- Base images từ Docker Hub/registry công khai đã được phê duyệt.
- Package Java nội bộ publish bởi pipeline CI riêng, không được public.
- Bảo mật yêu cầu **tránh dependency confusion, kiểm soát IAM, scan và tiết kiệm traffic**.

### 17.1. Thiết kế đề xuất

~~~mermaid
flowchart LR
    BUILD["Java build / Cloud Build"] --> MAV["maven-all virtual"]
    MAV -->|"100"| JPR["java-private standard"]
    MAV -->|"20"| MRC["maven-central-cache remote"]
    MRC --> CENTRAL["Maven Central"]
    BASE["Docker build / deploy"] --> DOC["docker-all virtual"]
    DOC -->|"100"| IPR["images-private standard"]
    DOC -->|"10"| DRC["dockerhub-cache remote"]
    DRC --> HUB["Docker Hub"]
    BUILD -->|"publish JAR"| JPR
    BUILD -->|"push image"| IPR
    DOC --> RUNTIME["GKE / Cloud Run"]
~~~

### 17.2. Chính sách phân quyền

| Actor | Hành động được phép | Repository |
|---|---|---|
| Java build runner | Download dependencies | maven-all Reader |
| Internal Java publisher | Publish version đã được CI phê duyệt | java-private Writer |
| Container build publisher | Push image đã build và scan | images-private Writer |
| GKE/Cloud Run image-pull identities | Pull image | docker-all hoặc images-private Reader theo cách deploy |
| Artifact Registry service agent | Đọc upstream theo policy | java-private, maven-central-cache, images-private, dockerhub-cache |
| Platform admin | Quản lý modes/upstream policy | Repos có phạm vi quản trị |

Không cấp **Artifact Registry Admin** cho tất cả jobs chỉ vì chúng cùng dùng một virtual URL. Khi pipeline ngoài GCP truy cập, dùng **Workload Identity Federation** và gắn principal với repo role tối thiểu.

### 17.3. Mục tiêu phát hành

1. **Release reproducible:** Maven versions/lock và Docker digest được ghi vào build manifest.
2. **Private-first:** mọi Java build chỉ truy cập **maven-all**, không dùng public repo song song.
3. **Caching:** dependencies công khai được tải lần đầu qua remote và có cache dùng lại.
4. **No direct publishing to virtual:** các pipelines có Writer trên standard, chỉ Reader trên virtual.
5. **Security:** vulnerability review, image provenance, IAM/access logs và Secret Manager.
6. **Operations:** cleanup có dry-run, alert khi cache/upstream lỗi, rollback upstream policy.
7. **Cost:** theo dõi bytes cached, pulls, storage growth, network và scanning trong ngân sách.

### 17.4. Ma trận nghiệm thu

| Test | Kỳ vọng |
|---|---|
| Maven lấy JAR nội bộ version cố định | Chọn java-private theo policy |
| Maven lấy package Maven Central chưa cache | Remote fetch rồi cache |
| Build lại version đã cache khi upstream tạm lỗi | Có thể tiếp tục nếu cache hợp lệ |
| Package/version không tồn tại ở cả hai upstream | Báo lỗi, không âm thầm lấy từ nguồn thứ ba |
| pip có repo public extra-index-url | Bị phát hiện và sửa thành virtual-only |
| Docker pull base image đã phê duyệt | Thành công qua docker-all |
| Push image vào docker-all | Bị từ chối vì read-only |
| Push image vào images-private với Writer | Thành công |
| Client không có Reader trên virtual | Bị từ chối |
| Service agent bị thu hồi quyền upstream | Test phát hiện lỗi để sửa IAM, không tắt security |
| Update priority rồi rollback | Phục hồi policy cũ và version/digest kỳ vọng |
| Scan phát hiện lỗ hổng nghiêm trọng | Có quy trình ngăn promotion và thay dependency |
| Xóa cache cũ | Không làm hỏng release cần rollback hoặc dùng offline |

### 17.5. Khi nào KHÔNG nên dùng remote/virtual?

Nếu doanh nghiệp chỉ có **một repository private**, client luôn tải đúng version từ đó và không cần upstream aggregation, **standard repo** có thể đủ. Không cần tạo virtual chỉ để tăng số tầng cấu hình.

Nếu upstream private **chỉ nằm trong VPC/on-premises không có public endpoint**, remote repo không đáp ứng trực tiếp; cần thiết kế khác (đồng bộ packages vào standard theo pipeline, hoặc sản phẩm/proxy hỗ trợ đường đi yêu cầu).

Nếu bắt buộc phải kiểm tra **mọi request** trực tiếp với upstream và chính sách không cho cache, xem xét **connector mode (Preview)** theo format/tính năng được hỗ trợ, đồng thời đánh giá độ trễ, upstream availability và chi phí.

## 18. Bài tập thực hành

### Bài tập A — Phân loại standard, remote, virtual

Hãy chọn mode:

1. Pipeline cần **push** JAR **com.company:billing-core:2.0.1**.
2. Build cần package công khai từ Maven Central nhưng muốn có cache.
3. Mọi build Maven cần một URL chung cho private và public.
4. Security policy cấm caching artifact upstream và format được hỗ trợ bởi connector.
5. Image đã build cần trở thành artifact chính thức có thể rollback.

**Đáp án:** (1) Standard Maven; (2) Remote Maven; (3) Virtual Maven; (4) cân nhắc Connector Preview; (5) Standard Docker.

### Bài tập B — Đọc virtual priority

Một virtual repo có:

| Upstream | Priority | Có com.company:client:1.0.0? |
|---|---:|---|
| private | 100 | Có |
| central-cache | 20 | Có |
| legacy | 100 | Có |

**Câu hỏi:**

1. Nếu client yêu cầu chính xác **1.0.0**, guaranteed lấy từ private không?
2. Vì sao hai nguồn priority 100 là rủi ro?
3. Cách sửa nếu chỉ private được phép cung cấp package trên?

**Đáp án:** (1) Không bảo đảm, vì private và legacy đồng hạng; (2) hệ thống có thể trả từ một trong hai; (3) cấp priority khác nhau theo chính sách, xóa nguồn không được phép, pin version/digest và kiểm tra provenance.

### Bài tập C — Dependency confusion qua pip

Client có:

~~~ini
[global]
index-url = https://asia-southeast1-python.pkg.dev/shop-dev-001/python-private/simple/
extra-index-url = https://pypi.org/simple
~~~

**Câu hỏi:**

1. Có chắc pip chọn package private nếu tên trùng với public nhưng public có version mới hơn không?
2. Sửa cấu hình như thế nào để private có priority cao?
3. Những cơ chế nào bổ sung để không tự lấy nhầm mã độc?

**Đáp án:** (1) Không; pip chọn candidate theo version và quy tắc resolver, không bảo đảm private first; (2) dùng một **python-all virtual** kết hợp private standard priority cao và PyPI remote priority thấp, bỏ extra-index-url public; (3) pin/lock/hashes, scan, review dependency, IAM.

### Bài tập D — Remote cache khi upstream outage

Docker Hub tạm unavailable. Trong **dockerhub-cache**:

- Image **busybox:1.36** đã cache trước.
- Image **some-image:2.0.0** chưa cache.

**Câu hỏi:** Các pull có chắc đều thành công không? Tại sao cache không thay thế backup?

**Đáp án:** Không. Artifact đã cache có thể tiếp tục được phục vụ, còn artifact chưa cache có thể thất bại; việc cache bị xóa/expire, metadata cần refresh hoặc IAM lỗi vẫn ảnh hưởng. Với production critical versions, cân nhắc lưu/approve trong standard và pin digest.

### Bài tập E — Quyền service agent đa project

Virtual Maven ở project **platform-registry-001**, standard Maven ở **java-team-001**.

**Hỏi:**

1. Client Java build cần quyền Reader ở đâu?
2. Principal nào phải đọc upstream?
3. Vì sao chỉ cấp Reader tại virtual chưa đủ?
4. Permission/role nào giúp cấp quyền theo mức hẹp?

**Đáp án:** Build client Reader trên virtual; **Artifact Registry Service Agent của virtual project** có quyền đọc upstream. Có thể cấp roles/artifactregistry.reader trên upstream hoặc custom role chứa **artifactregistry.repositories.readViaVirtualRepository** theo hướng dẫn, tránh Editor/Owner rộng.

### Bài tập F — Review thay đổi priority

Nhóm cập nhật maven-all từ:

~~~text
java-private priority 100
maven-central-cache priority 20
~~~

thành:

~~~text
java-private priority 10
maven-central-cache priority 100
~~~

**Câu hỏi:** Nguy cơ gì xảy ra nếu hai nguồn cùng có package/version? Cần quy trình gì trước release?

**Đáp án:** Remote public có thể được ưu tiên hơn private, làm thay đổi nguồn package. Cần review thay đổi, kiểm thử clean build, so sánh checksum/artifact source, có policy rollback, triển khai staging trước.

### Bài tập G — Thiết kế hệ thống Java/GKE

Hãy thiết kế:

- Maven private libs do team Java publish.
- Maven Central packages chỉ đọc qua cache.
- Base image từ Docker Hub được kiểm soát.
- Image Java build xong được push về private Docker.
- GKE production chỉ pull images đã được phê duyệt.

**Đầu ra mong đợi:** sơ đồ repository modes, bảng IAM, cấu hình client URLs, policy JSON, cách pin dependencies/image digests, monitoring và cleanup. Chỉ rõ **phải push vào standard**, không push vào virtual/remote.

## 19. Checklist vận hành và runbook

### 19.1. Trước khi tạo repository

1. Xác định **format**: Docker, Maven, npm, Python, Go hoặc khác.
2. Liệt kê private packages và public upstream đã phê duyệt.
3. Chọn **location** và kiểm tra hỗ trợ/giá.
4. Đặt tên repo theo chức năng: **private**, **cache**, **all/virtual**.
5. Xác định caller identities, service agents và IAM tối thiểu.
6. Kiểm tra Secret Manager credentials nếu upstream cần auth.
7. Kiểm tra VPC SC/CMEK/org policies.
8. Xác định dữ liệu được cache, retention và nhu cầu scanning.

### 19.2. Trước khi đưa virtual vào CI/CD

1. Mọi upstream cùng format/location và đã tồn tại.
2. Virtual policy JSON có **priority khác nhau** nếu cần thứ tự quyết định.
3. Service agent đọc được upstream, kể cả cross-project.
4. Clients chỉ dùng virtual endpoint, không còn public registry phụ trong config.
5. Dependency versions và Docker images được pin theo chính sách.
6. Staging build thành công với cache nóng và lạnh.
7. Các lỗi 401/403/404 được phân loại trước rollout.
8. Có version của policy JSON để rollback.

### 19.3. Khi production build không tìm thấy package

~~~mermaid
flowchart TD
    E["Build / pull lỗi"] --> ID{"401/403?"}
    ID -->|Có| AUTH["Xác thực client, Reader/Writer,<br/>service agent, Secret Manager"]
    ID -->|Không| N{"404 / missing version?"}
    N -->|Có| SRC["Kiểm tra package/version thực,<br/>policy priority, upstream location"]
    N -->|Không| UP{"429/5xx/timeout?"}
    UP -->|Có| CACHE["Upstream rate limit/outage,<br/>VPC SC, remote cache, quota"]
    UP -->|Không| OTHER["Xem build client/proxy logs"]
    AUTH --> RETEST["Thử lại trên môi trường kiểm soát"]
    SRC --> RETEST
    CACHE --> RETEST
    OTHER --> RETEST
~~~

**Không xử lý bằng cách cấp Artifact Registry Admin cho mọi build runner** hoặc đưa tokens công khai vào source. Phải xác định lớp nào đang từ chối request.

### 19.4. Sau sự cố

- Ghi **package/version hoặc image digest**, URL endpoint, project/location và caller identity.
- Ghi **mã HTTP, giai đoạn resolve, upstream state và repository mode**.
- Nếu liên quan cache, xác định artifact đã được cache chưa, ai/đâu đã xóa.
- Nếu liên quan IAM, sửa role/service agent theo phạm vi nhỏ nhất.
- Nếu liên quan dependency confusion, khoanh vùng package có thể bị ảnh hưởng và kiểm tra build provenance.
- Cập nhật lockfile, upstream policy, runbook và cảnh báo cần thiết.

## 20. Tổng kết và tài liệu tham khảo

**Tám nguyên tắc chính:**

1. **Standard** dùng để **publish và lưu artifacts nội bộ**; **remote** dùng để **proxy/cache** upstream; **virtual** dùng làm **một endpoint đọc chung** và không lưu blob.
2. Remote chỉ cache **những artifact đã được yêu cầu**, không tải trước toàn bộ upstream; cache hỗ trợ độ tin cậy nhưng không thay thế mirror offline/backup.
3. Với virtual, **priority số lớn thắng**; cùng priority có thể chọn bất kỳ nguồn đồng hạng. **Pin version** vì priority không bảo đảm chọn đúng nguồn khi client hỏi phiên bản mới nhất.
4. **Giảm dependency confusion** bằng cách ưu tiên private standard và cấu hình package manager chỉ dùng virtual endpoint, không đồng thời hỏi PyPI/Maven Central/npm trực tiếp ngoài kiểm soát.
5. **Client Reader**, **publisher Writer** và **Artifact Registry service agent upstream Reader** là các vai trò khác nhau; private remote credentials thuộc Secret Manager.
6. Virtual upstream phải **cùng format/location**; remote custom upstream URL yêu cầu **HTTPS** và không hỗ trợ VPC-only/on-prem-only endpoint không có public access.
7. **VPC SC, scanning, provenance, pin digest, IAM, cleanup và monitoring** vẫn cần thiết; proxy/cache không tự làm packages an toàn.
8. Một kiến trúc tốt kết hợp hiệu năng, bảo mật, khả năng rollback và chi phí với workload Compute Engine, GKE, Cloud Run, Cloud Build và Java.

**Tài liệu Google Cloud chính thức:**

1. [Artifact Registry overview](https://docs.cloud.google.com/artifact-registry/docs/overview) — các mode repository và tích hợp hệ sinh thái GCP.
2. [Repository overview](https://docs.cloud.google.com/artifact-registry/docs/repositories) — standard, remote, connector, virtual.
3. [Remote repositories overview](https://docs.cloud.google.com/artifact-registry/docs/repositories/remote-overview) — cache, metadata freshness, upstream formats, hạn chế.
4. [Create remote repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/remote-repo) — gcloud remote flags, private upstream, Secret Manager.
5. [Virtual repositories overview](https://docs.cloud.google.com/artifact-registry/docs/repositories/virtual-overview) — priority, dependency confusion và giới hạn.
6. [Create virtual repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/virtual-repo) — upstream policy JSON, gcloud create/update, service agent IAM.
7. [Supported formats](https://docs.cloud.google.com/artifact-registry/docs/supported-formats) — các định dạng container, packages và pipeline.
8. [Create standard repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/create-repos) — publish private artifacts.
9. [Maven/Gradle authentication](https://docs.cloud.google.com/artifact-registry/docs/java/authentication) — credential helper và package resolver.
10. [Python authentication](https://docs.cloud.google.com/artifact-registry/docs/python/authentication) — pip index-url và tránh extra-index-url.
11. [Python package management](https://docs.cloud.google.com/artifact-registry/docs/python/manage-packages) — virtual priorities và dependency resolution.
12. [Quickstart: Docker Hub remote repository](https://docs.cloud.google.com/artifact-registry/docs/repositories/create-dockerhub-remote-repository) — cache image, Secret Manager và Docker authentication.
13. [Cleanup policies](https://docs.cloud.google.com/artifact-registry/docs/repositories/cleanup-policy) — quản lý versions/cache với retention.
14. [gcloud artifacts repositories create](https://docs.cloud.google.com/sdk/gcloud/reference/artifacts/repositories/create) — command flags và định dạng.
15. [Artifact Registry access control](https://docs.cloud.google.com/artifact-registry/docs/access-control) — Reader/Writer/Service Agent permissions.
