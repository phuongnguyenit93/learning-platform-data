# Quản lý artifact, package và container image

Trong quy trình CI/CD, hoàn thành bước biên dịch chưa có nghĩa là ứng dụng đã sẵn sàng triển khai. Đội phát triển còn phải lưu trữ kết quả build ở nơi đáng tin cậy, xác định chính xác phiên bản, kiểm tra nguồn gốc, cấp quyền cho hệ thống tiêu thụ và quyết định khi nào có thể xóa dữ liệu cũ. Những kết quả đó thường xuất hiện dưới ba hình thức: **pipeline artifact**, **package** và **container image**.

Bài học thuộc chương **CI/CD và chuỗi cung ứng phần mềm** của lộ trình Microsoft Azure. Kiến thức ở đây áp dụng cho ứng dụng chạy trên Azure Kubernetes Service (AKS), Azure Container Apps, App Service, máy ảo hoặc các hệ thống tiêu thụ thư viện nội bộ. Trọng tâm là quản lý toàn bộ vòng đời của sản phẩm build, từ commit đến môi trường production, với Azure Pipelines, Azure Artifacts và Azure Container Registry (ACR).

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt pipeline artifact, package và container image theo định dạng, mục đích sử dụng và nơi lưu trữ.
2. Thiết kế quy tắc đặt phiên bản, gắn commit, lưu digest và phát hành một lần để triển khai ở nhiều môi trường.
3. Sử dụng Azure Pipelines để xuất bản artifact, Azure Artifacts để phân phối package và ACR để phân phối image.
4. Áp dụng quyền truy cập tối thiểu, kiểm tra lỗ hổng, SBOM, chữ ký và chính sách phê duyệt trước triển khai.
5. Vận hành quy trình promotion, rollback, retention và xử lý sự cố thường gặp.

## 2. Ba loại sản phẩm build cần quản lý

| Loại | Nội dung điển hình | Đích tiêu thụ | Nơi lưu thường dùng | Cách định danh |
| --- | --- | --- | --- | --- |
| **Pipeline artifact** | File JAR, thư mục build, báo cáo kiểm thử, manifest triển khai, file cấu hình đã sinh | Stage tiếp theo trong cùng hoặc giữa các pipeline | Azure Pipelines / Azure DevOps | Pipeline run, tên artifact, thông tin commit |
| **Package** | Thư viện NuGet, npm, Maven, Python, Universal Package | Ứng dụng khác, công cụ quản lý dependency, nhóm phát triển | Azure Artifacts feed | Tên package + phiên bản |
| **Container image** | Manifest OCI, các lớp filesystem, cấu hình khởi chạy | AKS, Container Apps, App Service, máy chủ container | Azure Container Registry | Registry + repository + tag hoặc digest |

**Pipeline artifact** là kết quả của một lần chạy pipeline. Ví dụ, job build Java tạo file JAR và job triển khai tải lại chính file đó. Artifact gắn với một run cụ thể, thuận tiện để chuyển dữ liệu giữa các stage hoặc phục vụ điều tra sự cố. Azure Pipelines hiện có cơ chế **Pipeline Artifacts** và cơ chế **Build Artifacts** cũ; khi dùng Azure DevOps Services, Pipeline Artifacts thường là lựa chọn phù hợp cho luồng mới.

**Package** là đơn vị có danh tính và phiên bản để nhiều dự án sử dụng lại. Ví dụ, nhóm nền tảng phát hành thư viện Maven tên **com.example:telemetry-core:2.3.1** vào một Azure Artifacts feed. Dự án tiêu thụ khai báo dependency đến phiên bản đó mà không cần biết pipeline nào đã build thư viện. Azure Artifacts hỗ trợ nhiều hệ sinh thái package và **Universal Packages** dành cho nội dung không thuộc một định dạng package chuyên biệt.

**Container image** đóng gói ứng dụng cùng những thành phần runtime cần thiết theo định dạng OCI/Docker. ACR lưu repository, image manifest và các layer. Ví dụ, một ứng dụng có địa chỉ **acrdemo.azurecr.io/orders/api:1.4.0**. Tag thuận tiện cho con người, trong khi digest **sha256** xác định nội dung manifest cụ thể.

Một pipeline có thể tạo cả ba loại. Chẳng hạn:

- Lưu JAR và kết quả kiểm thử làm pipeline artifacts để các stage khác tải xuống.
- Xuất bản thư viện dùng chung thành Maven package trong Azure Artifacts.
- Đóng gói dịch vụ API thành container image và đẩy lên ACR để triển khai.

Không nên đặt mọi kết quả vào một registry chỉ vì chúng đều được gọi chung là “artifact”. Hãy chọn nơi lưu theo **cách sản phẩm được tiêu thụ** và chính sách truy cập, lưu trữ, phát hành của nó.

## 3. Kiến trúc quản lý trên Azure

~~~mermaid
flowchart TD
    A["Git commit / pull request"] --> B["CI: build, test, phân tích"]
    B --> C["Sinh SBOM, metadata, bằng chứng"]
    C --> D["Cổng kiểm tra chất lượng và bảo mật"]
    D --> E["PublishPipelineArtifact"]
    D --> F["Azure Artifacts feed"]
    D --> G["Azure Container Registry"]
    E --> H["Stage triển khai dùng file build"]
    F --> I["Ứng dụng khác lấy dependency"]
    G --> J["Staging tham chiếu image digest"]
    J --> K["Phê duyệt / kiểm tra"]
    K --> L["Production dùng cùng image digest"]
~~~

Các thành phần cần nhận diện:

| Thành phần | Trách nhiệm |
| --- | --- |
| **Azure Repos hoặc GitHub** | Quản lý nguồn, pull request, nhánh, commit và chính sách kiểm tra thay đổi |
| **Azure Pipelines hoặc GitHub Actions** | Chạy build, test, đóng gói, quét, ký, xuất bản và triển khai |
| **Azure Artifacts** | Quản lý feed package, quyền đọc/ghi, phiên bản, upstream sources và feed views |
| **Azure Container Registry** | Quản lý repository, image manifest, layer, tag, digest, quyền push/pull và một số tác vụ registry |
| **Microsoft Entra ID** | Danh tính cho người dùng, service principal, workload identity và managed identity |
| **Azure RBAC / quyền feed** | Giới hạn ai được đọc, xuất bản, quản trị và triển khai artifact |
| **AKS, Container Apps, App Service** | Kéo và chạy image hoặc tiếp nhận sản phẩm build theo cơ chế triển khai tương ứng |

Azure DevOps organization/project, Azure subscription và ACR là các đối tượng quản trị khác nhau. Có quyền sửa pipeline **không tự động** đồng nghĩa có quyền push image vào ACR; có quyền push ACR cũng không đồng nghĩa có quyền quản lý feed Azure Artifacts.

## 4. Thiết kế định danh, phiên bản và tính bất biến

### 4.1. Gắn sản phẩm build với nguồn gốc

Mỗi lần phát hành nên truy vết được tối thiểu:

- Repository, commit SHA và nhánh/tag nguồn.
- Pipeline run ID, thời điểm build, bộ công cụ và môi trường build.
- Tên package, phiên bản hoặc tên repository image, tag, digest.
- Kết quả test, quét bảo mật, SBOM, chữ ký hoặc attestation (nếu áp dụng).
- Môi trường đã triển khai và người hoặc quy tắc đã phê duyệt.

**Ví dụ ánh xạ một bản phát hành:**

| Trường | Giá trị minh họa |
| --- | --- |
| Source | Repository orders-api; commit 8f73c1a… |
| CI run | Azure Pipelines run 4281 |
| Pipeline artifact | orders-api-jar của run 4281 |
| Maven package dùng chung | com.example:orders-client:1.4.0 |
| Container image tag | orders/api:1.4.0 và orders/api:8f73c1a |
| Container image digest | sha256:… (giá trị trả về từ registry sau push) |
| Môi trường | staging → production, tham chiếu cùng digest |

Đây là **bảng ánh xạ** giữa các hệ thống, không hàm ý rằng JAR, Maven package và image có cùng nội dung nhị phân. Mỗi loại có thông tin toàn vẹn riêng; muốn chứng minh sự tương ứng cần thêm metadata/provenance từ pipeline.

### 4.2. Phiên bản package

Với thư viện được người khác sử dụng, áp dụng quy tắc phiên bản của hệ sinh thái, thường là **Semantic Versioning**:

- **MAJOR** khi có thay đổi API không tương thích.
- **MINOR** khi bổ sung tính năng tương thích ngược.
- **PATCH** khi sửa lỗi tương thích ngược.

Ví dụ: **2.5.0** hoặc bản tiền phát hành **2.6.0-rc.1**. Phải xem quy ước phiên bản cụ thể của npm, NuGet, Maven hoặc Python vì các công cụ có quy tắc khác nhau đối với version, prerelease và build metadata.

Trong Azure Artifacts, phiên bản package đã xuất bản thường được xem là **bất biến**: không lập kế hoạch ghi đè cùng một tên và version khi nội dung thay đổi. Nếu bản **2.5.0** lỗi, hãy phát hành bản sửa **2.5.1** hoặc ngừng cho sử dụng bản lỗi theo quy trình; không build lại rồi gắn lại nhãn **2.5.0**.

### 4.3. Tag và digest của container image

Một image có thể có nhiều tag: **1.4.0**, **commit-8f73c1a**, **build-4281**. Tag là một tên tham chiếu có thể bị chuyển sang manifest khác, tùy chính sách registry; vì thế **tag không phải bằng chứng bất biến của nội dung**.

Digest tham chiếu nội dung manifest hoặc OCI index. Ví dụ minh họa:

~~~text
acrdemo.azurecr.io/orders/api:1.4.0
acrdemo.azurecr.io/orders/api@sha256:<digest-64-ky-tu-hex>
~~~

Dòng thứ hai dùng chỗ giữ chỗ để diễn giải cấu trúc; khi vận hành phải thay bằng digest thật do registry trả về. Với image đa kiến trúc **linux/amd64** và **linux/arm64**, digest của OCI index có thể khác digest manifest của từng kiến trúc. Cần ghi đúng digest được hệ thống triển khai dùng để xác định image.

Quy tắc thực hành:

1. Build và push một lần trong CI, sau khi kiểm tra.
2. Ghi lại digest thực tế ngay sau push, liên kết với commit và run ID.
3. Triển khai staging và production bằng **cùng digest**; promotion là chuyển quyền sử dụng sản phẩm đã kiểm chứng.
4. Dùng tag cho tìm kiếm, hiển thị phiên bản và quản trị nếu hữu ích; luôn lưu digest trong hồ sơ phát hành.
5. Muốn rollback, chọn digest đã được kiểm chứng trước đó.

**Không tái build riêng cho production** chỉ để đổi tên môi trường. Cùng mã nguồn có thể tạo nhị phân khác vì dependency, base image, timestamp hoặc toolchain đã thay đổi. Build một lần rồi promotion chính sản phẩm đó sẽ giảm rủi ro lệch giữa staging và production.

### 4.4. Release manifest

Một file manifest độc lập giúp deployment biết chính xác cần dùng nội dung nào:

~~~yaml
release: "orders-api-1.4.0"
source:
  commit: "8f73c1a..."             # minh họa, thay bằng SHA đầy đủ
  pipelineRunId: 4281
artifacts:
  pipeline:
    name: "java-output"
    runId: 4281
  package:
    name: "com.example:orders-client"
    version: "1.4.0"
  container:
    registry: "acrdemo.azurecr.io"
    repository: "orders/api"
    tag: "1.4.0"
    digest: "<sha256-digest-thuc-te>"
checks:
  tests: "passed"
  vulnerabilityPolicy: "passed"
  sbom: "attached"
~~~

Manifest này chỉ là **mẫu cấu trúc** để triển khai trong hệ thống của bạn; nó không phải định dạng bắt buộc của Azure. Nếu triển khai tự động, pipeline cần sinh manifest từ giá trị thật, lưu cùng bằng chứng và ngăn thay đổi không qua kiểm soát.

## 5. Quản lý pipeline artifacts trong Azure Pipelines

### 5.1. Xuất bản và tải xuống

Giả sử một dự án Java Maven tạo file JAR cùng báo cáo kiểm thử. Sau bước **mvn clean verify**, pipeline có thể xuất bản thư mục **target**:

~~~yaml
steps:
  - task: Maven@4
    displayName: "Build và test ứng dụng Java"
    inputs:
      mavenPomFile: "pom.xml"
      goals: "clean verify"

  - task: PublishPipelineArtifact@1
    displayName: "Lưu kết quả build"
    inputs:
      targetPath: "$(Build.SourcesDirectory)/target"
      artifact: "java-output"
~~~

Một job hoặc stage tiếp theo có thể tải artifact đó:

~~~yaml
steps:
  - task: DownloadPipelineArtifact@2
    displayName: "Lấy kết quả build của run hiện tại"
    inputs:
      buildType: "current"
      artifactName: "java-output"
      targetPath: "$(Pipeline.Workspace)/java-output"

  - bash: |
      find "$(Pipeline.Workspace)/java-output" -type f
    displayName: "Kiểm tra file nhận được"
~~~

Đây là các trích đoạn YAML cho **Azure Pipelines trên Azure DevOps Services**. Với pipeline nhiều stage, cần bảo đảm stage sản xuất artifact chạy thành công trước stage tải artifact. Lệnh **find** chỉ kiểm tra hiện diện; trong môi trường thực tế nên xác minh tên file, checksum hoặc metadata cần thiết trước khi dùng.

### 5.2. Quy tắc lưu pipeline artifacts

**Chỉ đóng gói các file cần thiết.** Thư mục build thường chứa file tạm, cache và nhiều báo cáo không cần đưa sang stage triển khai. Nên tách rõ **deployable** (để triển khai) và **reports** (để điều tra). Không tải lên khóa riêng, token, mật khẩu, file môi trường chứa bí mật hoặc log chứa thông tin nhạy cảm.

**Gắn với run ID.** Một artifact tên **java-output** xuất hiện ở nhiều run; tên này đơn lẻ không xác định phiên bản. Khi một release cần tái hiện, lưu cả run ID và commit.

**Chọn retention theo nhu cầu.** Vòng đời pipeline artifacts phụ thuộc chính sách retention và vòng đời run của Azure DevOps. Đừng giả định sản phẩm build sẽ tồn tại mãi hoặc dùng pipeline artifact làm kho phát hành lâu dài cho khách hàng nội bộ. Nếu cần phân phối thư viện cho nhiều dự án, chuyển sang package feed; nếu cần chạy container, đẩy image lên registry.

**Không coi artifact là bằng chứng đã kiểm thử.** File chỉ được coi là đủ điều kiện phát hành khi có kết quả test và quality gate gắn với đúng commit/run, theo chính sách của nhóm.

## 6. Quản lý package bằng Azure Artifacts

### 6.1. Feed, package và views

**Feed** là không gian quản lý package và quyền truy cập. Feed có thể được quản lý trong phạm vi project hoặc organization tùy cách tạo. Một feed có thể chứa package thuộc nhiều định dạng được Azure Artifacts hỗ trợ; nhóm nên đặt tên rõ ràng theo sản phẩm, miền nghiệp vụ hoặc chính sách truy cập.

**Feed views** giúp kiểm soát mức sẵn sàng của package, thường gặp:

- **@Local**: package hiện có trong feed.
- **@Prerelease**: các phiên bản được phép thử nghiệm hoặc tích hợp sớm.
- **@Release**: phiên bản đã được chấp thuận sử dụng rộng rãi.

Khi promotion từ **@Local** sang **@Release**, cùng một package version được gắn thêm mức công bố phù hợp; **không cần biên dịch lại** thư viện. Trước khi cấu hình client, xác minh URL feed/view và quyền đọc theo loại package.

**Upstream sources** cho phép feed lấy và lưu cache package từ nguồn ngoài hoặc feed khác theo cấu hình. Điều này hỗ trợ việc sử dụng dependency ổn định hơn, nhưng cũng làm cần thiết việc quản trị nguồn tin cậy, kiểm tra giấy phép và ngăn package cùng tên từ nguồn không mong muốn.

### 6.2. Ví dụ phát hành npm package nội bộ

Giả sử nhóm phát triển package **@platform/date-utils**. Trong mã nguồn:

~~~json
{
  "name": "@platform/date-utils",
  "version": "1.3.0",
  "private": false,
  "main": "dist/index.js",
  "files": ["dist"]
}
~~~

File **.npmrc** của package trỏ đến feed nội bộ. URL ví dụ dưới đây cần thay bằng đường dẫn feed thực tế hiển thị trong phần **Connect to feed** của Azure Artifacts:

~~~ini
@platform:registry=https://pkgs.dev.azure.com/ORG/PROJECT/_packaging/FEED/npm/registry/
always-auth=true
~~~

Pipeline sử dụng task xác thực thay vì đưa token vào repository:

~~~yaml
steps:
  - task: NodeTool@0
    inputs:
      versionSpec: "24.x"

  - task: npmAuthenticate@0
    inputs:
      workingFile: "packages/date-utils/.npmrc"

  - bash: |
      cd packages/date-utils
      npm ci
      npm test
      npm run build
      npm publish
    displayName: "Kiểm tra và phát hành npm package"
~~~

**Điều kiện để chạy ví dụ:**

- Feed phải tồn tại; đường dẫn, tên scope và folder package phải đúng với dự án thực.
- Danh tính build service phải có quyền cần thiết để publish package vào feed; nếu feed ở project khác, cấp quyền rõ ràng.
- Script **build** phải tồn tại và tạo thư mục **dist**; lockfile cần được commit để **npm ci** có thể chạy.
- Version **1.3.0** chỉ được publish khi chưa có package cùng tên và version trong feed; mỗi lần phát hành mới phải tăng version.
- Đưa bước publish vào luồng release đáng tin cậy, ví dụ sau khi pull request được duyệt và chính sách bảo mật đạt yêu cầu; không publish từ mọi pull request không tin cậy.

Với NuGet, Maven hoặc Python, nguyên tắc tương tự: dùng tool của hệ sinh thái, feed URL chính xác và tác vụ xác thực phù hợp. Việc tạo package version phải tách với quyết định cho phép tiêu thụ version đó ở môi trường production.

### 6.3. Chính sách cho package

| Quyết định | Thực hành đề xuất | Lý do |
| --- | --- | --- |
| Đặt tên | Dùng namespace/scope rõ chủ sở hữu | Giảm nhầm lẫn giữa package nội bộ và công khai |
| Phân quyền | Reader cho ứng dụng tiêu thụ; publisher cho pipeline tin cậy | Giới hạn ai có thể thay đổi nguồn dependency |
| Phiên bản | Không ghi đè version đã phát hành | Hỗ trợ tái lập build và điều tra sự cố |
| Promotion | Chỉ nâng lên view phát hành sau khi đủ bằng chứng | Tách bước tạo package khỏi bước chấp thuận sử dụng |
| Nguồn ngoài | Cấu hình upstream có kiểm soát, pin dependency/lockfile | Giảm thay đổi bất ngờ hoặc dependency confusion |
| Retention | Giữ bản đang sử dụng, bản cần rollback và bằng chứng kiểm toán | Cân bằng chi phí với khả năng khôi phục |

## 7. Quản lý container image bằng Azure Container Registry

### 7.1. Registry, repository, tag và manifest

ACR là registry riêng tư để lưu image và artifact tương thích OCI. Cấu trúc địa chỉ thường gặp:

~~~text
<registry-login-server>/<repository>:<tag>
~~~

Ví dụ: **acrdemo.azurecr.io/orders/api:1.4.0**. Trong đó:

- **acrdemo.azurecr.io** là login server.
- **orders/api** là repository.
- **1.4.0** là tag của một manifest.
- **sha256:…** là digest của manifest hoặc index tương ứng.

Một image thường gồm nhiều layer có thể được dùng lại. Việc xóa tag không luôn đồng nghĩa xóa ngay toàn bộ dữ liệu layer, vì nhiều manifest có thể cùng tham chiếu layer đó. Khi dọn registry phải xét cả manifest, tag, dependency và chính sách giữ bản.

### 7.2. Chuẩn bị registry và push thử

Ví dụ giả định đã đăng nhập Azure CLI, có subscription phù hợp, quyền tạo ACR và resource group **rg-ci** đã tồn tại. Tên registry trên Azure phải hợp lệ và duy nhất toàn cục; **acrteamdemo12345** chỉ là tên minh họa.

~~~bash
ACR_NAME=acrteamdemo12345
RESOURCE_GROUP=rg-ci
REPOSITORY=orders/api
TAG=1.4.0

az acr create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACR_NAME" \
  --sku Basic

ACR_SERVER=$(az acr show \
  --name "$ACR_NAME" \
  --query loginServer -o tsv)

az acr login --name "$ACR_NAME"

docker build --pull -t "$ACR_SERVER/$REPOSITORY:$TAG" .
docker push "$ACR_SERVER/$REPOSITORY:$TAG"
~~~

**Dockerfile tối giản** cho ứng dụng Java đã đóng gói sẵn:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/app.jar /app/app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Ví dụ yêu cầu **target/app.jar** có thật, image nền hỗ trợ chạy bằng UID **10001** và ứng dụng lắng nghe cổng **8080**. Trong hệ thống thực tế, nên pin digest image nền, kiểm tra quyền ghi của ứng dụng, giảm số layer không cần thiết và kiểm tra image sau build. Bản JAR và dependency phải được build/test từ nguồn tin cậy trước khi tạo image.

Để xác định digest đã được registry lưu, có thể truy vấn metadata bằng Azure CLI (với quyền đọc registry):

~~~bash
az acr manifest show-metadata \
  --registry "$ACR_NAME" \
  --name "$REPOSITORY:$TAG" \
  --query digest -o tsv
~~~

Lưu kết quả digest này vào release manifest hoặc output của pipeline. Khi xác nhận nội dung image từ môi trường khác, hãy dùng digest, không chỉ so sánh tag.

### 7.3. Azure Pipelines build và push image

Ví dụ CI sau dùng service connection kiểu Docker Registry đã được cấu hình với quyền push ACR. Tên **sc-acr-push** phải được thay bằng service connection thật. Pipeline test ứng dụng trước khi push:

~~~yaml
trigger:
  - main

pool:
  vmImage: "ubuntu-latest"

steps:
  - task: Maven@4
    displayName: "Build và kiểm thử"
    inputs:
      mavenPomFile: "pom.xml"
      goals: "clean verify"

  - task: PublishPipelineArtifact@1
    displayName: "Lưu sản phẩm Java"
    inputs:
      targetPath: "$(Build.SourcesDirectory)/target"
      artifact: "java-output"

  - task: Docker@2
    displayName: "Build và push image lên ACR"
    inputs:
      containerRegistry: "sc-acr-push"
      repository: "orders/api"
      command: "buildAndPush"
      Dockerfile: "$(Build.SourcesDirectory)/Dockerfile"
      buildContext: "$(Build.SourcesDirectory)"
      tags: |
        $(Build.SourceVersion)
        $(Build.BuildId)
~~~

Hai tag ở đây phục vụ truy vết theo commit và run ID; **chưa thay thế digest**. Để vận hành production, bổ sung stage truy vấn digest từ ACR, ghi metadata, tạo SBOM, quét và xác minh image rồi mới cho phép triển khai. Stage lấy digest cần một cơ chế xác thực Azure/ACR được cấp quyền đọc phù hợp; không được giả định service connection Docker tự động cấp phiên Azure CLI cho mọi step.

**Lưu ý về phiên bản:** CI thường có thể chạy nhiều lần trên cùng commit. Tag theo commit vì vậy có thể bị ghi lại nếu cấu hình cho phép. Muốn bảo đảm một tham chiếu duy nhất cho từng lần build, dùng run ID hoặc cơ chế tag bất biến, sau đó luôn chốt digest cho release.

### 7.4. Triển khai theo digest

Trong AKS, Container Apps hoặc nền tảng container khác, image reference có thể chỉ rõ digest:

~~~text
acrdemo.azurecr.io/orders/api@sha256:<digest-thuc-te>
~~~

Ví dụ phần container trong Kubernetes Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: api
          image: "acrdemo.azurecr.io/orders/api@sha256:<digest-thuc-te>"
          ports:
            - containerPort: 8080
~~~

Đoạn YAML chỉ mô tả lựa chọn image; giá trị digest dạng chỗ giữ chỗ cần được thay trước khi áp dụng. Cụm AKS phải có khả năng kết nối ACR và **danh tính dùng để pull image** phải được cấp quyền đọc tương ứng. Nếu ứng dụng dùng Container Apps hoặc App Service, cấu hình registry access và managed identity trên chính tài nguyên đó.

**Promotion** là cập nhật cấu hình triển khai của môi trường tiếp theo sang cùng image digest đã vượt qua kiểm thử. Khi production có sự cố, rollback bằng manifest/digest của bản ổn định trước đó, đồng thời kiểm tra tương thích schema dữ liệu, migration và cấu hình runtime. Rollback image không tự động hoàn tác thay đổi cơ sở dữ liệu.

## 8. Bảo vệ chuỗi cung ứng phần mềm

Artifact là kết quả của một quá trình; bảo vệ registry riêng lẻ chưa đủ nếu dependency hoặc runner build đã bị chiếm quyền. Chính sách phải bao phủ cả **nguồn → build → publish → promotion → runtime**.

### 8.1. Danh tính và phân quyền tối thiểu

| Chủ thể | Quyền cần thiết | Tránh cấp quyền |
| --- | --- | --- |
| Pipeline CI tạo image | Push vào repository ACR được chỉ định, đọc metadata cần thiết | Chủ sở hữu toàn subscription nếu chỉ cần publish |
| AKS kubelet / workload runtime | Pull image từ repository đã cho phép | Quyền push hoặc xóa image |
| Pipeline publish package | Publish package vào feed đúng phạm vi | Quản trị mọi project/feed |
| Pipeline consume package | Đọc package và metadata | Quyền phát hành phiên bản mới |
| Release approver | Xem bằng chứng, phê duyệt môi trường | Credential registry dùng chung không kiểm soát |

Với cấu hình ACR dùng **RBAC theo registry**, các vai trò quen thuộc là **AcrPull** và **AcrPush**. Với ACR cấu hình **repository permissions bằng ABAC**, cách phân quyền và tên vai trò theo repository khác; cần chọn đúng chế độ quyền hiện tại của registry. Không mặc định một lệnh gán role áp dụng cho mọi registry.

Đối với Azure Artifacts, quản lý quyền feed theo các vai trò đọc, cộng tác và xuất bản tương ứng; danh tính build service của Azure DevOps cần được cấp đúng quyền, nhất là khi feed nằm ở project khác.

Ưu tiên:

- **Managed identity** cho dịch vụ Azure chạy dài hạn để pull image khi nền tảng hỗ trợ.
- **Workload identity federation / OIDC** cho job CI/CD để tránh lưu client secret dài hạn, với trust policy giới hạn repository, branch và môi trường.
- Service connection có phạm vi nhỏ; tách danh tính build/push khỏi danh tính deploy.
- Không bật tài khoản admin ACR làm phương thức mặc định; không đưa mật khẩu vào Dockerfile, tham số build công khai, source code hoặc pipeline artifact.
- Giới hạn mạng ACR khi có yêu cầu bảo mật; kiểm tra trước khả năng kết nối của hosted agents, self-hosted agents và runtime nếu bật firewall/private endpoint.

### 8.2. Kiểm tra trước khi publish và deploy

Một release gate có thể yêu cầu:

1. Source đã qua review, pipeline dùng cấu hình được kiểm soát.
2. Unit test, integration test và build thành công.
3. Quét dependency, secret, image và license theo chính sách.
4. Sinh **Software Bill of Materials (SBOM)** mô tả thành phần/phụ thuộc của bản build.
5. Tạo provenance/attestation ghi ai build, từ nguồn nào, bằng quy trình nào, và liên kết với digest.
6. Ký sản phẩm hoặc attestation khi tổ chức áp dụng; **xác minh chữ ký, danh tính người ký và chính sách tin cậy** trước triển khai.
7. Phê duyệt promotion, sau đó triển khai bằng digest và lưu bằng chứng.

Các công cụ như **Syft** (SBOM), **Trivy** (quét), **Cosign** (ký/xác minh) hoặc giải pháp phù hợp có thể tham gia quy trình này; chúng **không tự nhiên chạy** chỉ vì bạn đã đẩy image lên ACR. Microsoft Defender for Cloud có các khả năng đánh giá lỗ hổng container tùy gói, cấu hình và phạm vi hỗ trợ; cần xác nhận tính năng thực tế trước khi đặt làm release gate.

Một SBOM hữu ích thường ghi package, version, dependency và thông tin liên hệ tới sản phẩm build. Tuy nhiên, **SBOM không phải chữ ký** và **kết quả quét “không có lỗi” không chứng minh image đáng tin tuyệt đối**. Cần kiểm soát nguồn build, công cụ, quyền và xác minh bằng chứng đồng thời.

### 8.3. Các tấn công và biện pháp đối ứng

| Rủi ro | Tình huống | Cách giảm thiểu |
| --- | --- | --- |
| **Dependency confusion** | Package nội bộ trùng tên với package từ registry công khai | Namespace rõ ràng, ràng buộc nguồn package, cấu hình upstream và quyền publish |
| **Tag substitution** | Tag production bị trỏ sang manifest khác | Deploy bằng digest, giới hạn quyền push và giám sát thay đổi |
| **Rò rỉ bí mật trong layer** | Token bị COPY hoặc ghi vào lệnh build rồi tồn tại trong lịch sử layer | Dùng cơ chế build secret an toàn; không chép secret vào image; quét secret |
| **Runner bị xâm nhập** | Job không tin cậy dùng credential publish | Tách quyền theo nhánh, OIDC có điều kiện, cô lập runner và kiểm tra PR |
| **Dependency bị nhiễm độc** | Thư viện tải từ nguồn bên ngoài chứa mã độc | Lockfile, pin version/hash khi hỗ trợ, quét và kiểm soát upstream |
| **Bằng chứng không gắn đúng image** | Ký tag hoặc kiểm tra một image nhưng triển khai image khác | Sinh, ký và xác minh bằng chứng liên kết với digest thực tế |
| **Xóa nhầm bản đang chạy** | Chính sách cleanup gỡ manifest chỉ còn được tham chiếu bằng digest | Kiểm kê các digest đang chạy, cần rollback và đang được giữ trước khi xóa |

## 9. Quy trình phát hành từ staging đến production

Thiết kế thực tế cho dịch vụ **orders-api**:

| Giai đoạn | Hoạt động | Điều kiện chuyển bước |
| --- | --- | --- |
| 1. Commit | Merge sau code review, CI lấy commit chính xác | Thỏa branch policy |
| 2. Build | Khôi phục dependency, test, tạo JAR và image | Test và build thành công |
| 3. Publish | Đẩy image lên ACR, lưu pipeline artifact và digest | Publish thành công, metadata đầy đủ |
| 4. Security gate | Quét image/dependency, kiểm tra SBOM và provenance | Đạt policy hoặc có ngoại lệ được duyệt, có thời hạn |
| 5. Staging | Deploy bằng digest, chạy smoke/integration test | Chỉ số và kiểm thử đạt |
| 6. Approval | Xem release manifest và kết quả staging | Được duyệt theo chính sách môi trường |
| 7. Production | Deploy chính digest staging đã kiểm tra | Health check, metric và error budget trong ngưỡng |
| 8. Theo dõi | Ghi deployment, cảnh báo, quyết định rollback nếu lỗi | Có đường khôi phục rõ ràng |

Khi cần phân phối cùng image cho nhiều registry, nên **sao chép/import image giữ nguyên nội dung** bằng công cụ registry phù hợp, kiểm tra digest ở đích và lưu ánh xạ nguồn/đích. Đừng mặc định cùng tag ở hai registry có cùng bytes. Việc ký và xác minh cũng phải gắn với manifest đang thực sự triển khai.

Với package, luồng tương tự là **build → publish version bất biến vào feed → kiểm thử từ feed → promote view → ứng dụng tiêu thụ nâng dependency có kiểm soát**. Với pipeline artifacts, luồng điển hình là **publish từ build job → download ở deploy job → kiểm tra tính khớp run/commit → triển khai**.

## 10. Retention, dọn dẹp, khả năng khôi phục và chi phí

### 10.1. Retention theo từng loại

**Pipeline artifacts:** xem chính sách giữ pipeline run, release được giữ lại và nhu cầu audit. Không xóa run chứa bằng chứng cần điều tra hoặc file cần khôi phục khi chưa có bản lưu thay thế.

**Package trong Azure Artifacts:** giữ các version đang được ứng dụng sử dụng, bản stable được hỗ trợ và các phiên bản phục vụ rollback. Xác minh các quy tắc retention và cơ chế xóa/unlist theo loại package; promotion, quyền feed và upstream có thể ảnh hưởng tới khả năng xóa. Không xem chính sách tự dọn như bằng chứng rằng package không còn ai tiêu thụ.

**Image trong ACR:** lập danh sách digest đang chạy ở production/staging, digest có thể rollback và các bản được giữ vì compliance. Kiểm tra repository, manifest/tag và chính sách retention trước khi xóa. Các cơ chế dọn image **untagged** hoặc purge tự động cần được thử với tập dữ liệu nhỏ và tiêu chí loại trừ rõ ràng.

### 10.2. Chi phí và độ sẵn sàng

Chi phí thường đến từ dung lượng lưu trữ, truyền dữ liệu và tính năng của từng dịch vụ. ACR có các tier/tính năng khác nhau; nhu cầu private endpoint, khả năng mở rộng hoặc replication có thể tác động lựa chọn tier. Azure DevOps và Azure Artifacts có cách tính giới hạn/lưu trữ riêng, cần theo dõi theo cấu hình thực tế.

Các quyết định giúp kiểm soát vận hành:

- Giảm file không cần thiết trong pipeline artifacts và tối ưu layer image.
- Đặt chính sách retention theo phân loại môi trường và yêu cầu audit.
- Giữ đủ bản để rollback trước khi kích hoạt cleanup tự động.
- Kiểm kê dependency để tránh lưu mọi bản vô thời hạn.
- Đo dung lượng và lưu lượng thực tế; cân đối chiến lược sao chép/replication của registry với mục tiêu phục hồi sau sự cố.

**Khôi phục sau sự cố** cần nhiều hơn một tag: lưu release manifest, digest, lịch sử phê duyệt, cấu hình triển khai và bí quyết khôi phục database. Kiểm thử định kỳ khả năng pull image cũ và triển khai lại trên môi trường kiểm soát.

## 11. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| **401 Unauthorized** khi push/pull | Chưa login, token hết hạn, cấu hình xác thực sai | Xác minh danh tính và phương thức login của job/runtime |
| **403 Forbidden** khi publish/pull | Đã xác thực nhưng thiếu quyền trên feed, registry hoặc repository | Kiểm tra quyền publisher/reader, Azure RBAC hoặc ABAC đúng phạm vi |
| **ImagePullBackOff** trên AKS | Credential pull, mạng/DNS/private endpoint, sai tên image/tag/digest, kiến trúc không phù hợp | Xem sự kiện Pod, danh tính kubelet, ACR reachability và reference image |
| **Package version already exists** | Pipeline publish lại cùng version | Tăng version mới; thiết lập idempotency cho pipeline phát hành |
| **Manifest unknown / image not found** | Tag/digest không có, sai repository, digest đã xóa | Kiểm tra địa chỉ registry, tên repository, digest đã ghi và retention |
| **Local build chạy, image production lỗi** | Khác cấu hình runtime, thiếu file, sai architecture hoặc base image | Kiểm tra Dockerfile, image runtime, health check và logs bằng cùng digest |
| **Staging tốt nhưng production khác** | Production dùng tag đã thay đổi hoặc bị build lại | So sánh digest và release manifest; promotion cùng digest |
| **CI không kết nối ACR** | Firewall, private endpoint, DNS hoặc cấu hình agent | Kiểm tra đường mạng thực tế từ agent và cơ chế cấp quyền |
| **Không khôi phục được phiên bản cũ** | Retention xóa artifact, image hoặc migration không tương thích | Duy trì danh sách digest cần rollback và kịch bản rollback dữ liệu |

Quy trình kiểm tra theo thứ tự thường giúp tìm nguyên nhân nhanh: **địa chỉ artifact → phiên bản/digest → danh tính → quyền → mạng → policy → runtime**. Không khắc phục lỗi quyền bằng cách cấp Owner toàn subscription hoặc bật ACR admin account cho tất cả pipeline.

## 12. Bài thực hành: một image, hai môi trường

**Bối cảnh:** Nhóm có một dịch vụ Java tên **orders-api**, Azure DevOps project, ACR và hai môi trường **staging** và **production**. Mục tiêu là chứng minh hai môi trường có thể dùng **cùng một sản phẩm build**.

### Bước 1 — Chuẩn bị

Tạo hoặc chọn ACR, thiết lập service connection CI có quyền push, và cấu hình danh tính runtime có quyền pull. Xác định Dockerfile hợp lệ, cấu hình Maven để tạo **target/app.jar**. Nếu có feed package nội bộ, cấu hình quyền đọc cho build job và chốt phiên bản dependency bằng file cấu hình/lockfile thích hợp.

### Bước 2 — Build và xuất bản

Chạy pipeline phần 7.3 trên nhánh được cho phép. Xác minh job Maven thành công, artifact **java-output** xuất hiện trong run và repository **orders/api** trong ACR có các tag tương ứng. Ghi **run ID, commit SHA, image digest** thực tế. Chỉ chấp nhận release nếu các bước kiểm tra đã định nghĩa ở phần 8 đạt yêu cầu.

### Bước 3 — Triển khai staging

Tạo release manifest với digest đã thu được. Cấu hình staging dùng image theo digest và chạy kiểm tra: khởi động thành công, endpoint health trả kết quả mong đợi, gọi một luồng nghiệp vụ chính và xác minh các metric quan trọng.

### Bước 4 — Promotion sang production

Sau khi staging qua kiểm tra và được duyệt, cập nhật production sang **đúng digest đó**. Ghi lại lịch sử triển khai. Truy vấn runtime để xác minh image thực tế; với Kubernetes, xem imageID/digest của Pod cùng trạng thái rollout để đối chiếu, vì chỉ đọc lại manifest cấu hình chưa đủ chứng minh Pod đã chạy đúng bản.

### Bước 5 — Diễn tập rollback

Giả lập health check không đạt. Đưa production về digest bản phát hành trước, quan sát trạng thái rollout và xác minh ứng dụng. Nếu release kèm migration dữ liệu, áp dụng kế hoạch khôi phục hoặc tương thích được thiết kế trước.

**Kết quả cần nộp của bài thực hành:**

- Bản ghi commit SHA, pipeline run ID và digest của hai bản image.
- Release manifest dùng cho staging/production.
- Bằng chứng staging và production đã chạy cùng digest trước khi rollback.
- Bản ghi kết quả rollback và đánh giá dữ liệu/secret có bị ảnh hưởng hay không.

## 13. Tình huống ra quyết định

**Tình huống A:** Một đội đang triển khai ứng dụng qua tag **latest**. Staging thông qua vào buổi sáng nhưng production tải lại tag vào buổi chiều và chạy mã khác. **Giải pháp:** gắn build với commit/run, chốt digest sau khi push, promotion digest đó qua các môi trường và giới hạn quyền ghi tag.

**Tình huống B:** Hai dịch vụ dùng chung thư viện, đội cung cấp muốn sửa bản **1.1.0** nhưng không tăng version. **Giải pháp:** giữ version bất biến, phát hành bản **1.1.1** hoặc phiên bản tương ứng với mức độ thay đổi, chạy kiểm thử tương thích và cho consumer chủ động nâng dependency.

**Tình huống C:** Một ACR tăng dung lượng nhanh; lịch dọn dẹp định xóa mọi image không còn tag. Một deployment cũ đang chạy bằng digest. **Giải pháp:** kiểm kê digest thực sự còn được tham chiếu và các bản rollback, thiết lập thời gian giữ bản, thử cleanup trên tập nhỏ, sau đó mới tự động hóa.

**Tình huống D:** Job GitHub Actions hoặc Azure Pipelines cần push image nhưng đang dùng mật khẩu ACR admin lưu trong biến chung. **Giải pháp:** tách danh tính CI, dùng OIDC/workload identity federation hoặc service connection phù hợp, cấp quyền push cần thiết theo chế độ RBAC/ABAC của ACR, bỏ credential dùng chung và kiểm tra lại audit.

## 14. Tự kiểm tra

**Câu 1.** Khi cần chia sẻ thư viện Java với nhiều service, nên ưu tiên pipeline artifact hay Maven package trong Azure Artifacts?  
**Đáp án:** Maven package vì có tên và version ổn định, công cụ dependency quản lý trực tiếp và feed hỗ trợ quyền, phân phối, promotion.

**Câu 2.** Vì sao không nên coi tag **1.4.0** là bằng chứng image staging và production giống nhau?  
**Đáp án:** Tag có thể bị chuyển sang manifest khác. Phải đối chiếu digest và bằng chứng của release.

**Câu 3.** Có nên build lại image để triển khai production sau khi staging đạt kiểm thử?  
**Đáp án:** Không. Nên promotion cùng digest đã kiểm chứng, đồng thời đối chiếu cấu hình và policy của production.

**Câu 4.** Azure Artifacts feed promotion và ACR image promotion có điểm chung gì?  
**Đáp án:** Cùng đưa một sản phẩm đã tạo và kiểm tra sang mức sử dụng cao hơn, dựa trên danh tính sản phẩm cố định. Package được xác định bằng tên/version; image production nên được xác định bằng digest.

**Câu 5.** SBOM có thay thế bước ký và xác minh provenance của image không?  
**Đáp án:** Không. SBOM liệt kê thành phần/phụ thuộc; chữ ký và provenance giúp kiểm tra tính toàn vẹn, danh tính và quá trình tạo sản phẩm. Các biện pháp bổ sung cho nhau.

## 15. Checklist áp dụng vào dự án

- [ ] Xác định đúng kho lưu cho pipeline artifact, package và container image.
- [ ] Mỗi sản phẩm phát hành truy vết được tới commit SHA và pipeline run.
- [ ] Package có version bất biến; image có digest được ghi vào release manifest.
- [ ] CI chỉ publish sau các bước build, test và kiểm tra bảo mật cần thiết.
- [ ] Phân quyền tách biệt cho publisher, consumer và deployer.
- [ ] Ưu tiên managed identity/OIDC và giữ secret khỏi source, image, artifact.
- [ ] Promotion chuyển đúng sản phẩm đã kiểm chứng sang môi trường tiếp theo.
- [ ] Có quan sát sau triển khai, kịch bản rollback và chính sách retention an toàn.
- [ ] Có bằng chứng kiểm tra SBOM/provenance/chữ ký nếu chính sách yêu cầu.

Quản lý artifact hiệu quả nghĩa là **biết chính xác sản phẩm nào đã được tạo, ai có quyền thay đổi hoặc sử dụng nó, sản phẩm đó đã được kiểm chứng ra sao và có thể khôi phục phiên bản nào khi sự cố xảy ra**. Với Azure, kết hợp Azure Pipelines, Azure Artifacts và ACR theo nguyên tắc đó tạo nền tảng vững chắc cho CI/CD và an toàn chuỗi cung ứng phần mềm.
