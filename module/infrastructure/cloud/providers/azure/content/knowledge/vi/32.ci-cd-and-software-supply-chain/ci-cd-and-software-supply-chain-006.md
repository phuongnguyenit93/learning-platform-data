# Quét dependency, secret và image trong pipeline

## 1. Bối cảnh và mục tiêu

Một pipeline CI/CD có thể xây dựng và triển khai ứng dụng thành công nhưng vẫn đưa lỗ hổng vào môi trường chạy. Ví dụ, một API chạy trên Azure Kubernetes Service (AKS) có thể dùng thư viện npm chứa lỗ hổng đã công bố, vô tình đưa mật khẩu vào commit, hoặc đóng gói image từ bản hệ điều hành chưa được vá. Cả ba rủi ro này đều đi qua chuỗi cung ứng phần mềm: mã nguồn, gói phụ thuộc, bước build và artifact triển khai.

Trong hệ sinh thái Microsoft Azure, pipeline có thể chạy trên Azure Pipelines hoặc GitHub Actions, lưu container image tại Azure Container Registry (ACR), rồi triển khai lên AKS, Azure Container Apps hoặc App Service. Quét bảo mật trước khi phát hành là một **quality gate**: một tập điều kiện buộc pipeline dừng khi phát hiện rủi ro vượt ngưỡng.

Sau bài học, bạn có thể:

- Phân biệt quét **dependency** (thư viện, gói phần mềm), **secret** (thông tin xác thực bị lộ) và **image** (artifact container cùng các lớp phụ thuộc).
- Chọn vị trí quét phù hợp trong pull request, build, trước khi push lên ACR và sau khi triển khai.
- Viết một Azure Pipelines YAML mẫu có các bước quét và chặn phát hành khi phát hiện vấn đề nghiêm trọng.
- Đọc kết quả quét, xử lý lỗ hổng thật, ngoại lệ có kiểm soát và sự cố lộ secret.
- Hiểu giới hạn của từng scanner, vai trò của SBOM, khả năng giám sát sau phát hành và cách bảo vệ chính bản thân pipeline.

## 2. Ba đối tượng quét, ba kiểu rủi ro

| Đối tượng | Scanner tìm gì? | Đầu vào điển hình | Rủi ro khi bỏ sót |
| --- | --- | --- | --- |
| **Dependency / SCA** (Software Composition Analysis) | Lỗ hổng đã biết của dependency trực tiếp và bắc cầu, phiên bản không an toàn; đôi khi thêm rủi ro giấy phép | Manifest và lockfile, ví dụ package.json + package-lock.json, pom.xml, Gradle lockfile, SBOM | Một thư viện gây thực thi mã từ xa hoặc đọc trái phép dữ liệu |
| **Secret** | Token API, khóa riêng, mật khẩu, chuỗi kết nối hoặc thông tin xác thực có dạng đáng ngờ | File đang checkout, diff commit, lịch sử Git, cấu hình build | Kẻ tấn công sử dụng thông tin xác thực đã bị đưa vào repository hoặc artifact |
| **Container image** | Lỗ hổng trong package hệ điều hành, runtime, thư viện ứng dụng trong image; tùy scanner còn phát hiện secret và cấu hình nguy hiểm | OCI/Docker image đã build, image tar, image trong registry | Image có lỗ hổng dù mã ứng dụng hiện tại đã vượt qua kiểm thử |

Quét dependency và quét image có phần chồng lấn, nhưng không thể thay thế hoàn toàn cho nhau. Quét mã nguồn thường tập trung vào cây dependency và lockfile; quét image kiểm tra **những gì thực sự đã đóng gói**, bao gồm base image, package hệ điều hành và thư viện cài trong quá trình build. Quét secret cần thực hiện đủ sớm để tránh cấp quyền truy cập hoặc phát hành từ một commit chứa thông tin xác thực.

Sơ đồ luồng khuyến nghị:

~~~mermaid
flowchart TD
    A["Commit / pull request"] --> B["Secret scan: diff + working tree"]
    B --> C["Dependency scan: manifest, lockfile, SBOM"]
    C --> D{"Đạt quality gate?"}
    D -->|Không| X["Dừng pipeline, tạo phát hiện cần xử lý"]
    D -->|Có| E["Test, build ứng dụng"]
    E --> F["Build container image"]
    F --> G["Image scan: OS, thư viện, secret"]
    G --> H{"Đạt quality gate?"}
    H -->|Không| X
    H -->|Có| I["Push image lên ACR"]
    I --> J["Triển khai theo image digest"]
    J --> K["Giám sát và quét lại khi có CVE mới"]
~~~

Thứ tự thực tế có thể khác nhau theo công cụ và ngôn ngữ, nhưng hai nguyên tắc cần giữ là **quét sớm trên pull request** và **quét artifact cuối trước khi phát hành**. Đăng kết quả quét lên dashboard sau khi image đã triển khai là hữu ích cho giám sát, nhưng chưa đủ để chặn lỗ hổng ở thời điểm phát hành.

## 3. Quét dependency: kiểm tra toàn bộ cây thư viện

### 3.1 Dependency trực tiếp và bắc cầu

Giả sử ứng dụng Node.js khai báo package A, A lại phụ thuộc B. Nếu B có CVE, chỉ đọc package.json sẽ không phản ánh đầy đủ rủi ro. Lockfile (như package-lock.json) ghi phiên bản đã được giải quyết và giúp scanner tái tạo cây phụ thuộc. Với Java, ý tưởng tương tự áp dụng cho Maven/Gradle; nên dùng scanner hiểu dependency graph thực tế hoặc SBOM sinh từ bước build.

Quy trình quét:

1. Checkout đúng commit của pull request, giữ manifest và lockfile đồng bộ; tránh tự động cập nhật dependency một cách âm thầm trong lúc quét.
2. Chạy công cụ SCA để nhận tên package, phiên bản, mã CVE/GHSA/OSV, mức độ nghiêm trọng, đường dẫn phụ thuộc và bản sửa nếu có.
3. Xác định ứng dụng có thực sự dùng phiên bản bị ảnh hưởng hay không, phạm vi production hay development, và lỗ hổng có khả năng bị khai thác trong kiến trúc hiện tại hay không.
4. Nâng phiên bản trực tiếp, cập nhật dependency bắc cầu qua phiên bản cha hoặc bản vá có hỗ trợ; tạo lại lockfile và chạy kiểm thử.
5. Quét lại đúng artifact sẽ phát hành. Nếu cần ngoại lệ, ghi rõ mã lỗ hổng, bằng chứng, người phê duyệt và ngày hết hạn.

Ví dụ với dự án Node.js đã commit package-lock.json:

~~~bash
# Kiểm tra dependency bằng chính công cụ quản lý package.
npm audit --audit-level=high

# Quét secret độc lập để không bỏ sót vì bộ lọc severity dành cho CVE.
trivy fs --scanners secret --exit-code 1 .

# Quét lỗ hổng dependency ở ngưỡng HIGH/CRITICAL.
trivy fs --scanners vuln --severity HIGH,CRITICAL --exit-code 1 .
~~~

Mã thoát khác 0 giúp pipeline dừng khi phát hiện vấn đề ở ngưỡng cấu hình. Với Maven hoặc Gradle, có thể tích hợp công cụ SCA phù hợp như OWASP Dependency-Check hoặc một scanner dựa trên SBOM. Không nên mặc định mọi scanner chỉ cần nhìn manifest là luôn phân giải chính xác dependency bắc cầu; nếu thiếu lockfile, cần dùng kết quả dependency resolution hoặc SBOM của build.

**Điểm dễ nhầm:** severity là mức độ nghiêm trọng của lỗ hổng, chưa phải bằng chứng chắc chắn rằng ứng dụng bị khai thác. Tuy nhiên, việc chưa có exploit công khai cũng không chứng minh an toàn. Chính sách chặn nên kết hợp severity, môi trường chạy, khả năng bị ảnh hưởng, bản vá và yêu cầu an ninh của tổ chức.

### 3.2 SBOM hỗ trợ truy vết

SBOM (Software Bill of Materials) liệt kê thành phần và phiên bản có trong artifact. Nó giúp trả lời câu hỏi: “Trong những image đang chạy, image nào chứa package X khi CVE mới xuất hiện?”. Một ví dụ tạo SBOM dạng CycloneDX bằng Syft:

~~~bash
syft my-app:build-123 -o cyclonedx-json=sbom.json
~~~

SBOM là **danh mục thành phần**, bản thân nó không chứng minh phần mềm an toàn. Có thể dùng SBOM làm đầu vào cho scanner, lưu cạnh thông tin commit, build và image digest, đồng thời quét lại khi cơ sở dữ liệu lỗ hổng được cập nhật. Tùy yêu cầu, pipeline còn có thể kiểm tra giấy phép, tính toàn vẹn package, chữ ký artifact và nguồn gốc build; đây là các kiểm soát bổ sung, không thuộc phạm vi của CVE scan đơn thuần.

## 4. Quét secret: phát hiện sớm và xử lý như sự cố

Secret có thể nằm trong file .env, YAML, source code, notebook, test fixture, Docker build argument, log hoặc commit cũ. Một chuỗi có hình thức giống token có thể là false positive, còn một credential thực tế có thể không khớp mẫu nhận diện. Vì vậy, secret scanning hỗ trợ phát hiện chứ không bảo đảm tìm thấy 100% secret.

Ba lớp kiểm soát nên kết hợp:

1. **Trước khi đẩy mã:** dùng pre-commit hook và chức năng push protection của nền tảng lưu trữ mã nguồn nếu được hỗ trợ. Nhà phát triển được cảnh báo ngay khi credential xuất hiện.
2. **Trong pull request:** quét diff hoặc toàn bộ working tree; một scanner như Gitleaks có thể kiểm tra lịch sử Git khi checkout đủ commit. Trivy có thể quét nội dung file hiện hành với chế độ secret.
3. **Ngoài CI:** quét lại repository và artifact định kỳ. Secret đã tồn tại từ nhiều tháng trước có thể chưa được kiểm tra trong một pull request mới.

Ví dụ chạy Gitleaks CLI phiên bản hỗ trợ lệnh git, sau khi checkout đủ lịch sử:

~~~bash
gitleaks git --redact --exit-code 1 .
~~~

Cờ --redact nhằm tránh in giá trị nhạy cảm ra report. Khi chạy scanner thực tế, cần kiểm tra các option của **phiên bản đã ghim** và giới hạn quyền đọc log/artifact quét. Nếu runner chỉ checkout shallow history, chế độ quét Git có thể bỏ sót commit cũ; nếu chỉ quét working tree, scanner sẽ không tự tìm hết lịch sử đã bị xóa khỏi nhánh hiện tại.

Khi phát hiện một secret thật, trình tự xử lý là:

1. **Thu hồi hoặc rotate ngay** credential tại nguồn cấp phát; mặc định xem credential đã lộ là không còn đáng tin cậy.
2. Kiểm tra log truy cập và hoạt động bất thường trong thời gian credential có thể bị lộ; xử lý theo quy trình incident response.
3. Xóa giá trị khỏi mã nguồn, cấu hình và artifact; nếu cần sửa lịch sử Git, phối hợp với chủ repository vì viết lại lịch sử ảnh hưởng các clone và nhánh. Việc xóa commit **không thay thế** bước thu hồi credential.
4. Cấp lại quyền theo nguyên tắc tối thiểu, quét lại và chỉ cho pipeline tiếp tục khi đã khắc phục.

Với Azure, ưu tiên **managed identity** hoặc **workload identity federation/OIDC** cho tài nguyên hỗ trợ, thay vì đưa client secret lâu dài vào repository. Dùng Azure Key Vault để quản lý secret cần thiết, và Azure DevOps service connection hoặc cơ chế định danh phù hợp để pipeline được cấp quyền. Secret variables chỉ giảm nguy cơ hiển thị trong log ở một số trường hợp; chúng không tự giải quyết nguy cơ pipeline hoặc script độc hại lấy trộm credential.

Đặc biệt, đừng cung cấp credential ACR hay quyền triển khai cho một job chạy mã pull request không tin cậy từ fork. Bước login/push/triển khai nên chỉ được thực hiện trên nhánh được bảo vệ hoặc sau khi đã qua bước xét duyệt được cấu hình.

## 5. Quét container image: kiểm tra sản phẩm thực sự triển khai

Image chứa nhiều thành phần không hiện rõ trong repository: base image, runtime, package hệ điều hành, thư viện được cài khi docker build và các file COPY vào image. Image scanner so khớp các thành phần này với dữ liệu lỗ hổng. Một số công cụ còn kiểm tra secret, cấu hình Dockerfile hoặc IaC; muốn có chức năng đó phải bật scanner tương ứng, không nên suy từ kết quả vulnerability scan rằng tất cả cấu hình đều đã được kiểm tra.

Ví dụ:

~~~bash
# Build image từ Dockerfile hiện tại.
docker build -t sample-api:build-123 .

# Quét lỗ hổng trong image khả dụng trong Docker daemon.
trivy image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 \
  sample-api:build-123

# Quét secret nằm trong artifact; không áp bộ lọc severity của CVE.
trivy image --scanners secret --exit-code 1 \
  sample-api:build-123
~~~

Các câu hỏi cần trả lời khi xử lý phát hiện:

- Package bị ảnh hưởng nằm trong **base image**, package hệ điều hành hay thư viện ứng dụng?
- Bản vá đã có cho đúng bản phân phối và phiên bản package đang dùng chưa? Một distro có thể backport bản sửa mà vẫn giữ một phần số phiên bản cũ; nên dựa vào advisory của distro và cách scanner diễn giải chúng.
- Image có chứa công cụ hoặc thư viện không cần thiết không? Có thể chuyển sang multi-stage build và runtime image tối giản không?
- Đã build lại image từ base image mới và quét lại chưa? Việc sửa package.json nhưng vẫn triển khai image cũ không giải quyết vấn đề.

**Tag có thể thay đổi**, còn digest nhận diện nội dung của image. Sau khi scan và push, nên ghi nhận digest (ví dụ dạng registry.azurecr.io/sample-api@sha256:...) và triển khai đúng digest đã được kiểm tra. Không tự suy rằng cùng tag “latest” ở hai thời điểm là cùng artifact. Để tăng độ tin cậy, tổ chức có thể bổ sung image signing, provenance/attestation và chính sách admission trước khi cho phép image chạy.

ACR cung cấp registry để lưu image; còn báo cáo đánh giá lỗ hổng image trong hệ sinh thái Azure có thể tích hợp thông qua các tính năng phù hợp của Microsoft Defender for Cloud/Defender for Containers, tùy cấu hình và gói dịch vụ. **Quét và chặn trước khi push** trong CI vẫn cần thiết nếu mục tiêu là ngăn artifact không đạt chuẩn được phát hành: việc một dịch vụ báo cáo lỗ hổng sau đó không tự động tương đương với một quality gate.

## 6. Thiết kế quality gate theo thời điểm

| Thời điểm | Kiểm tra nên có | Hành động khi có vấn đề |
| --- | --- | --- |
| Commit/pull request | Secret scan trên diff và file; SCA trên manifest/lockfile; kiểm tra lockfile thay đổi | Từ chối merge khi có secret thật hoặc dependency vượt ngưỡng; phản hồi kết quả cho tác giả PR |
| Build trước khi phát hành | Test; SCA bổ sung từ SBOM; image scan sau khi build | Dừng trước bước cấp quyền registry/push nếu không đạt |
| Nhánh phát hành | Đối chiếu commit, artifact, báo cáo quét, chính sách ngoại lệ | Chỉ push/triển khai artifact đã qua gate trên nhánh được bảo vệ |
| Sau phát hành | Quét lại theo cơ sở dữ liệu CVE mới, giám sát workload, inventory theo digest | Tạo cảnh báo/ticket, ưu tiên vá và triển khai lại |

Một chính sách khởi đầu có thể là: **secret thật: chặn ngay**; **vulnerability HIGH/CRITICAL: chặn trước phát hành**; các mức thấp hơn được theo dõi theo thời hạn xử lý. Đây là ví dụ chính sách để học, không phải một ngưỡng cố định đúng cho mọi hệ thống. Đối với ứng dụng có dữ liệu nhạy cảm hoặc yêu cầu tuân thủ cao, quy tắc có thể nghiêm ngặt hơn. Ngược lại, phát hiện false positive hoặc chưa có bản sửa có thể đi qua luồng ngoại lệ do người có thẩm quyền xét duyệt.

Ngoại lệ không nên được tạo bằng cách tắt toàn bộ scan hoặc đặt exit-code bằng 0 ở nhánh phát hành. Mỗi ngoại lệ cần ghi được ít nhất: mã lỗ hổng, thành phần bị ảnh hưởng, lý do chấp nhận tạm thời, biện pháp bù trừ, người sở hữu và ngày rà soát/hết hạn. Việc scanner không truy cập được cơ sở dữ liệu hoặc không phân tích được artifact cũng phải được phân biệt với kết quả “không tìm thấy lỗ hổng”; trên đường phát hành nhạy cảm, lỗi scanner cần khiến gate thất bại hoặc chuyển sang quy trình xử lý đã được định nghĩa.

## 7. Thực hành: Azure Pipelines quét trước khi push lên ACR

### 7.1 Giả định và chuẩn bị

Ví dụ minh họa một API Node.js có Dockerfile và package-lock.json đã commit. Repository có script npm test. Pipeline chạy trên agent Ubuntu có Docker; ACR đã được tạo và có Azure DevOps Docker registry service connection được cấp quyền push. Tên service connection và registry bên dưới là **giá trị mẫu** cần thay bằng tài nguyên của bạn.

Để ví dụ dễ theo dõi, scanner Trivy được chạy dưới dạng container riêng, còn image ứng dụng được lưu thành tar trước khi đưa vào scanner. Cách này không buộc agent phải cài sẵn trivy CLI hoặc cho container scanner truy cập Docker socket. Ở môi trường thực tế, hãy chọn phiên bản scanner đã kiểm chứng, **ghim bằng digest image** hoặc cơ chế tin cậy tương đương, cập nhật định kỳ và kiểm soát quyền của agent.

Dockerfile minh họa (ứng dụng có file server.js):

~~~dockerfile
FROM node:22-bookworm-slim
WORKDIR /srv/app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY . .
USER node
CMD ["node", "server.js"]
~~~

File .dockerignore tối thiểu để tránh đưa thư mục node_modules từ agent (có thể chứa dev dependencies) hoặc file nhạy cảm vào image:

~~~dockerignore
node_modules
.git
.env
.env.*
*.pem
*.key
coverage
~~~

Trong dự án thật, ghim base image theo digest sau khi kiểm chứng và cập nhật digest định kỳ; mở rộng .dockerignore theo repo để tránh COPY file credential hoặc artifact không cần thiết vào image. Kiểm tra ứng dụng có thể chạy với quyền non-root và không yêu cầu ghi vào thư mục chỉ đọc.

### 7.2 YAML pipeline

~~~yaml
# azure-pipelines.yml — ví dụ dành cho repository có Dockerfile và npm test.
trigger:
  - main

# "pr" dùng với repository GitHub/Bitbucket theo hỗ trợ của Azure Pipelines.
# Với Azure Repos Git, cấu hình build validation trong Branch Policies.
pr:
  - main

pool:
  vmImage: ubuntu-latest

variables:
  trivyImage: 'aquasec/trivy:0.65.0' # Phiên bản minh họa; rà soát và ghim digest khi vận hành.
  localImage: 'sample-api:$(Build.BuildId)'
  acrLoginServer: 'exampleacr.azurecr.io'

steps:
  - checkout: self
    fetchDepth: 0

  # Quét secret trước khi chạy npm scripts và trước khi cấp quyền ACR.
  - bash: |
      set -euo pipefail
      docker run --rm \
        -v "$(Build.SourcesDirectory):/repo:ro" \
        "$(trivyImage)" fs \
        --scanners secret \
        --exit-code 1 \
        /repo
    displayName: 'Quét secret trong repository'

  # Áp ngưỡng HIGH/CRITICAL cho vulnerability scan độc lập.
  - bash: |
      set -euo pipefail
      docker run --rm \
        -v "$(Build.SourcesDirectory):/repo:ro" \
        "$(trivyImage)" fs \
        --scanners vuln \
        --severity HIGH,CRITICAL \
        --exit-code 1 \
        /repo
    displayName: 'Quét dependency trong repository'

  - task: UseNode@1
    inputs:
      version: '22.x'
    displayName: 'Chuẩn bị Node.js'

  - bash: |
      set -euo pipefail
      npm ci
      npm test
    displayName: 'Cài đúng lockfile và chạy test'

  - bash: |
      set -euo pipefail
      docker build -t "$(localImage)" .
    displayName: 'Build container image'

  # Quét image tar để kiểm tra cả base image và package trong artifact.
  - bash: |
      set -euo pipefail
      docker save "$(localImage)" -o "$(Agent.TempDirectory)/sample-api.tar"
      docker run --rm \
        -v "$(Agent.TempDirectory):/artifacts:ro" \
        "$(trivyImage)" image \
        --input /artifacts/sample-api.tar \
        --scanners vuln \
        --severity HIGH,CRITICAL \
        --exit-code 1
      docker run --rm \
        -v "$(Agent.TempDirectory):/artifacts:ro" \
        "$(trivyImage)" image \
        --input /artifacts/sample-api.tar \
        --scanners secret \
        --exit-code 1
    displayName: 'Quét image trước khi phát hành'

  # Chỉ nhánh main đã qua toàn bộ gate mới được đăng nhập registry.
  - task: Docker@2
    displayName: 'Đăng nhập ACR sau khi scan thành công'
    condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))
    inputs:
      command: login
      containerRegistry: 'acr-service-connection'

  - bash: |
      set -euo pipefail
      docker tag "$(localImage)" \
        "$(acrLoginServer)/sample-api:$(Build.SourceVersion)"
      docker push "$(acrLoginServer)/sample-api:$(Build.SourceVersion)"
    displayName: 'Push image đã kiểm tra lên ACR'
    condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))
~~~

**Cách hoạt động:**

1. Pull request chỉ chạy các bước quét, test và build. Điều kiện branch trên hai bước cuối không cho PR đăng nhập ACR hoặc push image.
2. Hai bước quét file chạy **secret** và **vuln** riêng để ngưỡng severity HIGH/CRITICAL chỉ áp vào lỗ hổng; phát hiện secret được đánh giá độc lập. Nếu cần đầy đủ kiểm tra lịch sử commit, thêm Gitleaks (phiên bản đã ghim) và giữ fetchDepth: 0. Trivy fs trên working tree không đồng nghĩa với lịch sử Git đã được quét đầy đủ.
3. Trivy image đọc đúng tar sinh từ docker save, kiểm tra các package thực sự nằm trong image. Scanner trả mã lỗi nếu phát hiện mức nghiêm trọng vượt ngưỡng hoặc gặp lỗi thực thi, làm dừng các bước tiếp theo theo điều kiện succeeded().
4. Trên main, pipeline chỉ đăng nhập và push sau khi các bước trên đã thành công. Service connection cần quyền tối thiểu trên ACR; không nhúng username/password vào YAML.
5. Mẫu mới **push theo tag commit**, giúp truy vết tốt hơn tag latest. Sau push, nên lấy và lưu image digest từ registry, đưa digest vào manifest triển khai AKS/Container Apps và lưu cùng SBOM cùng báo cáo scan.

Ví dụ ưu tiên tính dễ đọc và kiểm soát luồng gate. Trong pipeline thực tế, cần chọn version/digest scanner đang được hỗ trợ, kiểm tra kết nối tải vulnerability database, xuất báo cáo vào nơi chỉ người có quyền mới đọc được, giới hạn thời gian lưu artifact và cấu hình branch protection/reviewer. Nếu dùng Azure Repos, hãy thiết lập **Branch Policies → Build validation** cho pull request: chỉ khai báo phần pr trong YAML không tự tạo PR trigger cho Azure Repos Git.

### 7.3 Trường hợp pipeline chạy trên GitHub Actions

Cùng nguyên tắc có thể triển khai bằng GitHub Actions: job quét trên pull_request, job build/scan trên push main, rồi job phát hành cần có quyền phù hợp và phụ thuộc vào job quét. Với dependency thay đổi trong pull request, có thể bổ sung action Dependency Review của GitHub (khi repository và tính năng hỗ trợ):

~~~yaml
name: Review dependencies
on:
  pull_request:

permissions:
  contents: read

jobs:
  dependency-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/dependency-review-action@v4
        with:
          fail-on-severity: high
~~~

Ví dụ này chỉ bao phủ **dependency review trên PR**, chưa thay cho secret scan và image scan. Với workflow vận hành thật, hãy pin action bên thứ ba theo full commit SHA đã kiểm chứng, cấu hình quyền GITHUB_TOKEN tối thiểu, bảo vệ environment phát hành và dùng OIDC/workload identity federation cho đăng nhập Azure khi được hỗ trợ, tránh lưu khóa Azure dài hạn.

## 8. Đọc kết quả quét và khắc phục có phương pháp

Xét ba phát hiện trong cùng một lần chạy:

| Phát hiện | Diễn giải đúng | Hành động |
| --- | --- | --- |
| Thư viện bắc cầu có GHSA/CVE mức HIGH | Đường phụ thuộc có package thuộc dải phiên bản bị ảnh hưởng | Xác nhận lockfile và đường dẫn phụ thuộc; nâng gói cha/bản vá, test và scan lại |
| Chuỗi nghi là API token trong file cấu hình | Có khả năng thông tin xác thực đã vào Git, kể cả khi tác giả xóa ở commit mới | Xác nhận qua kênh an toàn, thu hồi/rotate token, điều tra và quét lại; không dán token vào ticket |
| Package hệ điều hành trong base image có CVE CRITICAL | Việc update ứng dụng có thể không thay đổi package đó | Đổi base image sang bản có vá hoặc rebuild từ bản phát hành đã sửa, rồi scan image mới |

Khi scan thất bại, không nên chỉ xem dòng tổng số CVE. Hãy xác định **artifact**, **package và phiên bản**, **nguồn advisory**, **fixed version**, **đường đưa vào**, và **ngữ cảnh thực tế** của thành phần bị ảnh hưởng. Với CVE không có bản vá, ghi nhận rủi ro, xem khả năng giảm bề mặt tấn công, gỡ thành phần và lên lịch cập nhật khi có bản sửa.

Một số kết quả dễ gây hiểu nhầm:

- **“0 vulnerabilities”** chỉ có nghĩa scanner không phát hiện lỗ hổng trong phạm vi và dữ liệu sẵn có ở lần quét đó. Kiểm tra log để chắc chắn database cập nhật thành công và manifest/image được đọc đúng.
- **Đã scan source** không suy ra image an toàn, vì package của base image không nhất thiết xuất hiện trong source.
- **Đã scan image** không chứng minh runtime configuration, secret từ Key Vault, quyền IAM/RBAC hoặc lưu lượng mạng an toàn.
- **Đã xóa secret khỏi commit mới** không có nghĩa credential cũ hết hiệu lực.
- **Có CVE nhưng không có bản sửa** không phải lý do mặc định bỏ qua tất cả CVE cùng mức severity.

Nếu cần lưu báo cáo để kiểm toán, hãy ưu tiên định dạng máy đọc được (như JSON/SARIF tùy scanner), loại bỏ giá trị bí mật, gắn báo cáo với commit và image digest, đặt quyền truy cập và thời hạn lưu phù hợp. Có thể phát hành SBOM và kết quả scan cạnh artifact, nhưng không nên đưa raw secret match vào một kho artifact công khai.

## 9. Bảo vệ chính pipeline và duy trì khả năng phát hiện

Scanner là một dependency của pipeline. Một bước chạy công cụ quét từ image/tag không được kiểm chứng có thể trở thành điểm tấn công vào source hoặc credential của build. Vì vậy:

- Ghim phiên bản action, scanner và base image; xác thực nguồn phát hành, cập nhật có kiểm thử và tránh dùng tag trôi nổi như latest trong pipeline quan trọng.
- Phân tách job quét trên PR không tin cậy khỏi job có quyền push ACR hoặc deploy Azure. Chỉ cấp permission cần thiết cho từng job, service connection và runner.
- Không cho Docker build hoặc script trong pull request truy cập secret của production. Cẩn trọng với code chạy trong lifecycle scripts khi cài dependency.
- Quản lý cơ sở dữ liệu lỗ hổng: theo dõi thời điểm cập nhật, hạn chế fallback im lặng, và có quy trình xử lý khi scanner không kết nối mạng hoặc DB hết hạn.
- Theo dõi lỗ hổng **sau phát hành** vì CVE mới có thể xuất hiện sau ngày image được build; ánh xạ image digest đang chạy với SBOM để ưu tiên vá.
- Tạo đường xử lý ngoại lệ có người chịu trách nhiệm, hạn cuối và bằng chứng; rà soát định kỳ để tránh danh sách bỏ qua tăng mãi.

Trong Azure, giám sát bảo mật image/workload sau khi triển khai có thể kết hợp Defender for Cloud, Azure Monitor và các cơ chế vận hành khác tùy cấu hình. Chúng bổ sung khả năng phát hiện trong vòng đời ứng dụng, còn điểm quyết định có được **phát hành artifact** hay không phải được định nghĩa rõ ở CI/CD.

## 10. Bài tập áp dụng và tự kiểm tra

**Bài tập:** Một API có package-lock.json và Dockerfile sử dụng base image cũ. Khi mở pull request, pipeline phát hiện một dependency HIGH. Sau khi nâng dependency và merge, bước image scan phát hiện một CVE CRITICAL của package hệ điều hành. Đồng thời, secret scanner phát hiện chuỗi kết nối thật trong commit tuần trước.

Hãy đề xuất thứ tự xử lý và điều kiện được phép push ACR. Một lời giải hợp lý:

1. Thu hồi/rotate chuỗi kết nối ngay và kiểm tra hoạt động sử dụng credential; loại bỏ giá trị khỏi source, artifact, kiểm tra lịch sử theo quy trình.
2. Nâng dependency và cập nhật lockfile, chạy test, quét lại dependency của commit mới.
3. Cập nhật base image/bản vá hệ điều hành, build một image mới, quét lại image đó.
4. Chỉ mở gate sau khi secret được xử lý, không còn phát hiện vượt ngưỡng chưa được chấp nhận theo quy trình; push image đã quét và ghi nhận digest/SBOM.
5. Tiếp tục giám sát image đang triển khai vì CVE mới có thể được công bố bất kỳ lúc nào.

**Câu hỏi tự kiểm tra:**

1. Vì sao quét file manifest trước build không thể thay thế quét image sau build?
2. Khi nào cần checkout đầy đủ lịch sử Git để quét secret, và vì sao xóa secret khỏi commit mới chưa đủ?
3. Trong Azure Pipelines, làm thế nào bảo đảm PR không được dùng quyền push image lên ACR?
4. Vì sao cần lưu image digest và SBOM thay vì chỉ lưu tag latest?
5. Khi scanner bị lỗi tải vulnerability database, có thể kết luận build an toàn không?

**Kết quả cần đạt:** Bạn dựng được pipeline nhận diện đủ ba nhóm rủi ro, chặn trước khi push/triển khai, có cách xử lý secret khẩn cấp và gắn kết quả quét với đúng artifact. Đây là nền tảng để mở rộng sang ký image, provenance, admission policy và bảo vệ toàn bộ chuỗi cung ứng phần mềm trên Azure.
