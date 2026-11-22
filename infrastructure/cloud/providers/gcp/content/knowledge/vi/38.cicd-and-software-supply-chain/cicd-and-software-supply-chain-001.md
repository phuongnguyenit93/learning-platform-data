# Thiết kế pipeline ứng dụng và hạ tầng trên GCP

## 1. Mục tiêu của một pipeline CI/CD

Một pipeline CI/CD biến thay đổi trong Git thành phiên bản phần mềm hoặc hạ tầng có thể kiểm tra, truy vết, triển khai lặp lại và khôi phục khi có sự cố. Pipeline cần trả lời được các câu hỏi: mã nguồn nào đã tạo ra artifact, những kiểm tra nào đã chạy, ai hoặc hệ thống nào được phép triển khai, artifact nào đang chạy ở từng môi trường và làm thế nào quay về phiên bản an toàn.

Trong Google Cloud, một kiến trúc phổ biến kết hợp:

- **Cloud Build** để tự động build, chạy test, phân tích mã nguồn và đóng gói artifact.
- **Artifact Registry** để lưu container image và package.
- **Artifact Analysis** để quét lỗ hổng và quản lý metadata bảo mật của artifact.
- **Cloud Deploy** để quản lý release, target, promotion, approval và rollout cho workload được hỗ trợ như GKE và Cloud Run.
- **Terraform** để mô tả và triển khai hạ tầng bằng Infrastructure as Code (IaC).
- **IAM, Workload Identity Federation và Secret Manager** để giới hạn quyền và bảo vệ thông tin xác thực.
- **Cloud Monitoring, Cloud Logging và Cloud Trace** để theo dõi kết quả triển khai và tác động lên dịch vụ.

Các thành phần này không bắt buộc phải được dùng cùng nhau trong mọi tổ chức. Cloud Build có thể tích hợp với hệ thống CI khác; Cloud Deploy có thể nhận release từ một CI system bất kỳ có thể gọi API hoặc CLI; Terraform có thể chạy trong Cloud Build hoặc một nền tảng IaC chuyên dụng. Hãy chọn công cụ theo môi trường hiện có, nhưng giữ nguyên các nguyên tắc về kiểm soát nguồn, artifact, quyền và khả năng truy vết.

## 2. Thiết kế tổng thể: hai luồng liên kết nhưng có quyền riêng

Pipeline ứng dụng và pipeline hạ tầng có chung kho mã nguồn, quy trình review và tiêu chuẩn bảo mật, nhưng thực hiện các loại thay đổi khác nhau. Một pipeline build ứng dụng tạo artifact có thể chạy; pipeline hạ tầng thay đổi project, IAM, VPC, cluster, database hoặc cấu hình nền tảng. Quyền tạo image không nên mặc nhiên bao gồm quyền thay đổi IAM hoặc xóa tài nguyên production.

~~~mermaid
flowchart TB
    A[Git repository: application + deployment config] --> B[Pull request checks]
    B --> C{Review và policy checks đạt?}
    C -- Không --> X[Chặn merge]
    C -- Có --> D[Merge vào protected branch]
    D --> E[Cloud Build CI]
    E --> F[Build, unit/integration tests, scan]
    F --> G[Artifact Registry: image theo digest]
    G --> H[Provenance và attestations]
    H --> I[Cloud Deploy release]
    I --> J[Development / Staging]
    J --> K[Smoke test và verification]
    K --> L[Approval / promotion]
    L --> M[Production rollout]
    M --> N[Cloud Monitoring: SLO và alerts]
    N --> O{Có regression?}
    O -- Có --> P[Rollback hoặc mitigation]
    O -- Không --> Q[Theo dõi release]

    A --> R[Terraform / IaC pipeline]
    R --> S[Format, validate, policy, plan]
    S --> T[Review plan và approval]
    T --> U[Apply đúng saved plan]
    U --> V[Cloud resources và Terraform state]
    V --> N
~~~

Luồng ứng dụng thường đi qua build, test, scan, publish artifact, tạo release, triển khai staging, xác minh và promotion. Luồng IaC đi qua kiểm tra cấu hình, tạo execution plan, review thay đổi, approval và apply. Hai luồng có thể được kích hoạt bởi cùng một pull request, nhưng phải dùng danh tính triển khai và phạm vi quyền phù hợp.

### 2.1. Phân chia trách nhiệm của các thành phần

| Thành phần | Trách nhiệm | Kết quả cần lưu |
|---|---|---|
| Git repository | Lưu source code, Dockerfile, manifest, pipeline config và Terraform | Commit SHA, review, approval |
| Cloud Build | Thực thi CI theo cấu hình có thể tái lập | Build ID, log, test result, image digest |
| Artifact Registry | Lưu artifact được version hóa | Image/package digest, tag và metadata |
| Artifact Analysis | Phân tích lỗ hổng và metadata bảo mật của artifact | Vulnerability occurrences, scan metadata |
| Cloud Build provenance | Ghi nhận nguồn và quy trình tạo artifact | Provenance có thể xác minh |
| Binary Authorization | Áp dụng chính sách tin cậy tại thời điểm deploy trên runtime được hỗ trợ | Quyết định cho phép hoặc từ chối artifact |
| Cloud Deploy | Quản lý release, target và rollout | Release, rollout, approval, verification |
| Terraform | Quản lý hạ tầng bằng cấu hình khai báo | Saved plan, state và lịch sử thay đổi |
| Cloud Monitoring / Logging | Theo dõi hệ thống sau phát hành | Metric, log, trace và alert |

Cloud Build là dịch vụ thực thi build. Cloud Deploy quản lý việc đưa một release qua các target. Artifact Registry lưu artifact. Các thành phần có thể tích hợp nhưng không thay thế trách nhiệm của nhau.

## 3. Quản lý source code và điều kiện kích hoạt

### 3.1. Chuẩn hóa repository

Đưa những thành phần có ảnh hưởng đến khả năng triển khai vào version control:

- Source code và test.
- Dockerfile hoặc buildpack configuration.
- Cloud Build configuration như `cloudbuild.yaml`.
- Skaffold và manifest cho workload dùng Cloud Deploy.
- Cloud Deploy delivery pipeline và target definitions.
- Terraform modules, environment configuration và policy.
- Script migration database, smoke test và release notes.
- Tài liệu vận hành, SLO và hướng dẫn rollback.

Tách môi trường bằng folder hoặc repository theo quy mô tổ chức. Một cấu trúc tham khảo:

~~~text
repository/
  app/
    src/
    test/
    Dockerfile
  deploy/
    skaffold.yaml
    clouddeploy.yaml
    manifests/
  infra/
    modules/
    environments/
      dev/
      staging/
      prod/
  ci/
    cloudbuild.yaml
    scripts/
  policies/
  docs/
~~~

Không bắt buộc phải chia thành nhiều repository. Điều quan trọng là review có thể nhận biết thay đổi nào tác động đến ứng dụng, pipeline hay hạ tầng và người phê duyệt có đủ chuyên môn cho phạm vi đó.

### 3.2. Pull request và protected branch

Một pipeline an toàn nên có ít nhất hai nhóm trigger:

1. **Pull request trigger:** chạy kiểm tra nhanh như format, unit test, static analysis, secret scanning, dependency review, Terraform validate và plan trong phạm vi được phép. Trigger này không nên có quyền deploy production hoặc đọc secret production.
2. **Protected branch trigger:** chạy build phát hành sau khi pull request được review và merge. Trigger dùng service account riêng, tạo artifact có thể truy vết và có thể khởi tạo release.

Cloud Build hỗ trợ trigger theo sự kiện repository như push hoặc pull request, và có thể giới hạn theo branch hoặc điều kiện thay đổi. Cần kết nối repository với Cloud Build trước khi tạo trigger.

Không để pull request từ fork hoặc mã nguồn chưa tin cậy chạy trong một build có quyền cao. Người có quyền ghi vào repository gắn với trigger có thể ảnh hưởng mã nguồn được build; pull request trigger cũng có thể thực thi nội dung do người gửi PR cung cấp. Vì vậy, phân tách quyền, kiểm soát event type và review build configuration là một phần của bảo mật pipeline.

### 3.3. Trigger theo thay đổi

Với monorepo, không nhất thiết build tất cả dịch vụ sau mọi commit. Có thể dùng path filters hoặc logic xác định thư mục bị thay đổi để chạy đúng nhóm test. Tuy nhiên, thay đổi ở thư viện dùng chung, pipeline config, base image hoặc Terraform module có thể ảnh hưởng nhiều dịch vụ; cần khai báo dependency để trigger không bỏ sót.

Ví dụ ma trận trigger:

| Sự kiện | Kiểm tra hoặc hành động |
|---|---|
| Pull request thay đổi `app/` | Build ứng dụng, unit test, static analysis |
| Pull request thay đổi `infra/` | Terraform fmt, validate, policy check, plan |
| Pull request thay đổi `deploy/` | Validate manifest, Skaffold và Cloud Deploy config |
| Merge vào `main` | Build artifact phát hành, scan, provenance |
| Tạo release tag đã bảo vệ | Tạo release từ artifact đã build và kiểm chứng |
| Lịch chạy định kỳ | Drift detection, dependency scan, kiểm tra policy |

## 4. Thiết kế CI với Cloud Build

### 4.1. Các bước của CI

Một chuỗi CI thường gồm:

1. Checkout đúng commit và xác nhận commit SHA.
2. Khôi phục dependency từ repository được tin cậy.
3. Kiểm tra format, lint và static analysis.
4. Chạy unit test.
5. Chạy integration test trong môi trường phù hợp.
6. Phân tích dependency, license, secret và lỗ hổng.
7. Build artifact từ source đã kiểm tra.
8. Đẩy artifact vào Artifact Registry.
9. Ghi lại image digest, build ID, test result và provenance.
10. Chỉ phát tín hiệu cho CD khi toàn bộ gate bắt buộc đã đạt.

Cloud Build thực thi các bước trong build configuration. Mỗi build step chạy trong container riêng; build config có thể chỉ định công cụ như Maven, Gradle, Docker, Bazel hoặc builder tự quản lý. Dùng build script trong repository giúp quy trình nhất quán và có thể review.

### 4.2. Ví dụ Cloud Build configuration

Ví dụ dưới đây minh họa một ứng dụng Java dùng Maven và Docker. Hãy thay project, region, repository và image theo môi trường thật. Trong production, pin builder image theo digest và quản lý phiên bản toolchain rõ ràng.

~~~yaml
steps:
  - id: unit-and-integration-tests
    name: maven:3.9-eclipse-temurin-21
    entrypoint: mvn
    args:
      - -B
      - verify

  - id: build-container
    name: gcr.io/cloud-builders/docker
    args:
      - build
      - --pull
      - -t
      - ${_IMAGE_URI}:${SHORT_SHA}
      - .

images:
  - ${_IMAGE_URI}:${SHORT_SHA}

substitutions:
  _IMAGE_URI: asia-southeast1-docker.pkg.dev/PROJECT_ID/app-images/orders-api

options:
  logging: CLOUD_LOGGING_ONLY
  requestedVerifyOption: VERIFIED
~~~

`images` khai báo image Cloud Build cần push sau khi build. Tag chứa commit SHA giúp tra cứu thuận tiện, nhưng tag vẫn có thể được thay đổi nếu repository cho phép ghi đè. Khi promotion, hãy tham chiếu image bằng digest bất biến.

`requestedVerifyOption: VERIFIED` yêu cầu build provenance có thể xác minh theo cơ chế Cloud Build hỗ trợ. Kiểm tra cấu hình và điều kiện của dự án để chắc chắn build tạo được provenance mong muốn.

Ví dụ này chưa bao gồm đầy đủ các bước scan, ký, policy evaluation hoặc deploy. Hãy bổ sung các gate phù hợp với mức độ nhạy cảm của ứng dụng. Không đưa credential hoặc secret trực tiếp vào YAML.

### 4.3. Phân biệt CI nhanh và build phát hành

CI của pull request nên ưu tiên phản hồi nhanh và quyền tối thiểu. Build phát hành sau merge có thể chạy thêm integration test, scan đầy đủ, đóng gói, provenance và tạo release. Không nên dùng kết quả test của một commit khác để cấp phép phát hành.

Một release phải liên kết với đúng commit và đúng artifact digest đã kiểm tra. Nếu thay source sau khi test, cần build và kiểm tra lại. Nếu build lại cho từng môi trường, artifact ở staging có thể khác artifact ở production dù cùng tag; điều này làm yếu khả năng truy vết.

## 5. Artifact Registry và quản lý artifact bất biến

Artifact Registry là nơi lưu trữ container image và các package được tạo ra từ CI. Tổ chức repository theo ngôn ngữ, ứng dụng, môi trường hoặc ranh giới quyền truy cập tùy nhu cầu quản trị.

Các nguyên tắc nên áp dụng:

- Dùng repository riêng cho artifact production nếu cần tách quyền ghi và quyền đọc.
- Dùng tag có ý nghĩa như commit SHA hoặc release version để tra cứu.
- Promotion bằng digest SHA-256, tránh rebuild hoặc trỏ tag `latest` khi đưa artifact qua staging và production.
- Hạn chế ai có quyền push, delete hoặc thay đổi repository policy.
- Quản lý retention và cleanup để tránh xóa artifact còn cần cho rollback hoặc điều tra.
- Kiểm tra artifact nguồn bên ngoài và pin dependency/tool image vào phiên bản bất biến.
- Ghi lại quan hệ giữa commit, build ID, image digest, provenance và Cloud Deploy release.

Ví dụ một image được tham chiếu bằng digest:

~~~text
asia-southeast1-docker.pkg.dev/PROJECT_ID/app-images/orders-api@sha256:IMAGE_DIGEST
~~~

Tag hữu ích cho con người, digest hữu ích để xác định chính xác nội dung. Một image có thể có nhiều tag nhưng digest chỉ xác định một nội dung cụ thể. Khi tạo release, dùng digest của image đã qua kiểm thử và kiểm soát bảo mật.

## 6. Bảo vệ software supply chain

Pipeline không chỉ cần xác nhận mã nguồn build được. Nó còn phải chứng minh artifact đến từ nguồn đáng tin cậy và đi qua quy trình kiểm tra đã định.

### 6.1. Dependency và builder

- Khóa phiên bản dependency bằng lockfile hoặc dependency management phù hợp.
- Kiểm tra nguồn tải package và builder image.
- Không dùng tag mutable như `latest` cho base image hoặc builder trong pipeline production.
- Review thay đổi trong dependency lockfile.
- Giới hạn quyền ghi vào Artifact Registry.
- Dùng build environment tạm thời, cô lập giữa các build và kiểm soát tham số đầu vào.
- Không để build step có thể sửa script hoặc artifact của một build khác.

Cloud Build cung cấp môi trường build được quản lý và các tính năng bảo vệ build. Với workload cần truy cập mạng riêng, private pools cho phép tùy chỉnh môi trường build và kết nối với VPC. Private pools cũng là điều kiện cần trong một số kịch bản áp dụng VPC Service Controls cho build.

### 6.2. Vulnerability scanning và policy gate

Artifact Analysis có thể quét container image và package trong Artifact Registry. Kết quả có thể chứa thông tin về lỗ hổng, package độc hại, dependency và license tùy loại package và tính năng scanning được bật.

Một policy gate có thể phân loại kết quả:

| Kết quả scan | Hành động tham khảo |
|---|---|
| Không có finding vượt ngưỡng | Cho phép đi tiếp |
| Lỗ hổng Critical có bản vá và đang bị khai thác | Chặn release, yêu cầu xử lý |
| Lỗ hổng High | Chặn hoặc yêu cầu exception có thời hạn tùy chính sách |
| Finding chưa có bản vá | Đánh giá exploitability, exposure và phương án giảm thiểu; ghi nhận owner |
| Package không rõ nguồn hoặc bị đánh dấu độc hại | Chặn artifact và điều tra nguồn dependency |
| Kết quả scan không đầy đủ hoặc stale | Không mặc nhiên xem là sạch; thực hiện scan hoặc xác minh lại |

Ngưỡng cụ thể phải dựa trên risk appetite và yêu cầu tổ chức. Scan không đảm bảo phát hiện mọi lỗ hổng; nó là một lớp kiểm soát trong nhiều lớp.

### 6.3. Provenance, SBOM và attestation

**Build provenance** ghi nhận dữ liệu có thể xác minh về quá trình tạo artifact, chẳng hạn digest của artifact, vị trí source, tham số build và thông tin thực thi. Cloud Build có thể tạo provenance theo chuẩn SLSA mà dịch vụ hỗ trợ. Dùng provenance để trả lời artifact nào được tạo từ source nào và bởi build nào.

**Software Bill of Materials (SBOM)** liệt kê các thành phần phần mềm có trong artifact. SBOM hỗ trợ phân tích ảnh hưởng khi một thư viện có lỗ hổng hoặc khi cần đánh giá nguồn gốc package.

**Attestation** là bằng chứng có thể xác minh rằng artifact đã đáp ứng một điều kiện, ví dụ được tạo bởi build pipeline đáng tin cậy hoặc đã qua một bước kiểm tra. Binary Authorization có thể dùng attestation và policy để kiểm tra artifact trước khi cho phép triển khai trên runtime được hỗ trợ như GKE và Cloud Run.

Chuỗi tin cậy minh họa:

~~~mermaid
flowchart LR
    A[Source commit đã review] --> B[Trusted Cloud Build]
    B --> C[Artifact Registry image digest]
    B --> D[Build provenance]
    C --> E[Artifact Analysis scan]
    D --> F[Attestation / verification]
    E --> F
    F --> G[Binary Authorization policy]
    G --> H[Runtime deployment]
~~~

Provenance chứng minh thông tin về build; scan cho biết kết quả phân tích tại thời điểm scan; attestation ghi nhận một tuyên bố có thể xác minh; Binary Authorization thực thi policy. Không thành phần riêng lẻ nào chứng minh ứng dụng hoàn toàn an toàn.

## 7. Quản lý danh tính, quyền và secret của pipeline

### 7.1. Tách service account theo trách nhiệm

Không dùng một service account có quyền Owner cho toàn bộ pipeline. Tách danh tính theo nhiệm vụ:

| Danh tính | Quyền cần thiết |
|---|---|
| PR validation build | Đọc source và chạy test; không có quyền deploy production hoặc đọc secret production |
| Release build | Push artifact vào repository được chỉ định, ghi build log và provenance cần thiết |
| Terraform plan | Đọc trạng thái và truy vấn tài nguyên cần thiết để tạo plan; không có quyền apply nếu quy trình cho phép tách |
| Terraform apply | Thay đổi đúng resource scope của environment đã phê duyệt |
| Cloud Deploy execution | Render và triển khai vào target được chỉ định |
| Runtime service account | Chỉ quyền mà ứng dụng cần khi đang chạy |

Service account dùng để build, service account dùng để deploy và service account của workload đang chạy là các danh tính khác nhau. Điều này giảm tác động nếu một build step hoặc một ứng dụng bị xâm nhập.

Cloud Build cho phép chọn user-managed service account cho trigger. Khi dùng trigger, service account được cấu hình trên trigger là danh tính được dùng cho build; trường service account trong build config không ghi đè danh tính trigger. Cấp role tối thiểu cho service account đó và kiểm tra ai có quyền sửa trigger hoặc source repository.

### 7.2. Workload Identity Federation

Nếu pipeline chạy ngoài Google Cloud, chẳng hạn GitHub Actions, GitLab SaaS, Azure DevOps hoặc HCP Terraform, ưu tiên **Workload Identity Federation (WIF)** để dùng OIDC/SAML token trao đổi lấy credential ngắn hạn. Cách này tránh phải lưu service account JSON key lâu dài trong CI secret.

Cấu hình WIF cần giới hạn trust bằng attribute mapping và attribute condition. Ví dụ với GitHub, có thể giới hạn theo organization, repository, branch hoặc workflow. Không chỉ kiểm tra issuer; cần kiểm tra token thực sự đến từ repository và ref được phép.

Một workflow có thể dùng `google-github-actions/auth` để tạo credential configuration file. Quyền `id-token: write` chỉ nên cấp cho job cần lấy OIDC token. Nếu dùng service account impersonation, service account cần được cấp quyền trên tài nguyên đích và provider phải cho phép principal phù hợp impersonate tài khoản đó.

### 7.3. Secret Manager

Không ghi API key, mật khẩu database, signing key hoặc token vào source, Dockerfile hay build config. Lưu secret trong Secret Manager và chỉ cấp quyền `secretAccessor` cho build step hoặc workload cần dùng.

Cloud Build hỗ trợ khai báo `availableSecrets` và `secretEnv` để đưa secret vào đúng step. Giới hạn step nào được nhận secret, tránh in biến môi trường ra log và xóa file tạm sau khi dùng. Nếu một secret bị lộ, thu hồi hoặc xoay vòng theo quy trình sự cố.

## 8. Continuous delivery với Cloud Deploy

### 8.1. Release và target

Cloud Deploy quản lý việc đưa release qua chuỗi target đã khai báo. Một **release** đại diện cho nội dung được phát hành, bao gồm nguồn render và tham chiếu image. Một **rollout** là lần triển khai release vào một target cụ thể.

Ví dụ chuỗi môi trường:

- `dev`: kiểm tra tích hợp sớm.
- `staging`: môi trường gần production, chạy smoke test và acceptance test.
- `production`: target yêu cầu approval và có chiến lược rollout thận trọng.

Cloud Deploy sử dụng Skaffold để render và deploy manifest cho các target phù hợp. CI system tạo release bằng API hoặc CLI sau khi artifact đã được kiểm tra. Cloud Deploy lưu pipeline instance gắn với release; thay đổi cấu hình pipeline về sau không tự thay đổi định nghĩa của release đã tạo.

### 8.2. Ví dụ delivery pipeline và targets

Ví dụ dưới đây mô tả một pipeline cho GKE với staging và production. Thay project, region và cluster theo môi trường thật.

~~~yaml
apiVersion: deploy.cloud.google.com/v1
kind: DeliveryPipeline
metadata:
  name: orders-api
description: Release orders-api qua staging và production
serialPipeline:
  stages:
    - targetId: staging
    - targetId: production
---
apiVersion: deploy.cloud.google.com/v1
kind: Target
metadata:
  name: staging
gke:
  cluster: projects/PROJECT_ID/locations/asia-southeast1/clusters/staging
---
apiVersion: deploy.cloud.google.com/v1
kind: Target
metadata:
  name: production
requireApproval: true
gke:
  cluster: projects/PROJECT_ID/locations/asia-southeast1/clusters/production
~~~

Đây là skeleton minh họa; cần kiểm tra schema, quyền và cấu hình Skaffold tương ứng với phiên bản Cloud Deploy đang sử dụng. Target production yêu cầu approval trước khi rollout được tiếp tục.

### 8.3. Tạo release từ image đã kiểm tra

Sau khi build và scan thành công, CI có thể tạo release bằng digest của image. Ví dụ lệnh minh họa:

~~~bash
gcloud deploy releases create orders-api-${SHORT_SHA} \
  --delivery-pipeline=orders-api \
  --region=asia-southeast1 \
  --source=. \
  --images=app=asia-southeast1-docker.pkg.dev/PROJECT_ID/app-images/orders-api@sha256:IMAGE_DIGEST
~~~

Tên image `app` phải khớp với image alias trong Skaffold configuration. Source phải chứa cấu hình render/deploy mà release cần. Lưu release name, commit SHA và digest trong metadata của build để điều tra hoặc rollback.

### 8.4. Approval, verification và progressive rollout

Có thể yêu cầu approval ở target production. Người phê duyệt cần xem commit, image digest, test result, scan result, provenance, rollout plan và tác động dự kiến.

Sau deploy, Cloud Deploy có thể chạy verification task. Verification thường được thực hiện bằng container test do đội ngũ cung cấp; exit code 0 biểu thị thành công và non-zero biểu thị thất bại. Verification nên kiểm tra endpoint health, smoke test, kết nối phụ thuộc và hành vi quan trọng.

Với workload cần giảm rủi ro, dùng progressive rollout/canary khi target và runtime hỗ trợ. Chỉ tăng traffic hoặc số instance sau khi quan sát error rate, latency, saturation và business metric. Canary giúp phát hiện regression trên một phần lưu lượng; nó không thay thế test trước deploy.

### 8.5. Rollback

Khi release gây regression, rollback về release đã hoạt động tốt trước đó. Cloud Deploy hỗ trợ tạo rollout mới dựa trên release trước đó. Ví dụ:

~~~bash
gcloud deploy targets rollback production \
  --delivery-pipeline=orders-api \
  --region=asia-southeast1
~~~

Có thể chỉ định release cụ thể nếu cần. Rollback ứng dụng không tự động đảo ngược thay đổi database schema hoặc infrastructure. Thiết kế migration theo hướng backward-compatible, dùng expand-and-contract khi có thể và có kế hoạch xử lý dữ liệu riêng.

## 9. Pipeline cho hạ tầng với Terraform

### 9.1. Tách plan và apply

Thay đổi IAM, VPC, firewall, GKE, Cloud Run, Cloud SQL và Storage có thể ảnh hưởng nhiều workload. Pipeline hạ tầng cần có bước review rõ ràng:

1. Kiểm tra Terraform formatting và version constraints.
2. Chạy `terraform init` với provider lockfile đã review.
3. Chạy `terraform validate`.
4. Chạy policy checks và security scanning cho IaC.
5. Tạo saved plan bằng `terraform plan -out=tfplan`.
6. Xuất nội dung plan để người phụ trách review resource sẽ thêm, sửa hoặc xóa.
7. Yêu cầu approval theo môi trường và phạm vi rủi ro.
8. Chạy `terraform apply tfplan` với đúng saved plan đã được duyệt.
9. Kiểm tra tài nguyên sau apply và lưu kết quả cùng pipeline run.

Không tạo một plan, chờ approval, rồi tự động tạo một plan mới khác để apply mà không review lại. Plan mới có thể khác do state hoặc tài nguyên đã thay đổi.

### 9.2. Remote state và phân tách môi trường

Terraform state cần được lưu ở backend dùng chung, có kiểm soát quyền truy cập và backup. Google Cloud Storage backend là lựa chọn phổ biến cho Terraform trên GCP. Bật object versioning cho bucket state và giới hạn quyền đọc/ghi; state có thể chứa thông tin nhạy cảm ngay cả khi giá trị đã được đánh dấu sensitive trong Terraform.

Dùng state riêng cho dev, staging và production hoặc phân tách theo ranh giới quản trị phù hợp. Không để nhiều pipeline đồng thời apply cùng một state. Backend GCS hỗ trợ state locking để tránh hai tiến trình cùng ghi state; vẫn cần tổ chức pipeline để tránh chạy chồng và xử lý lock timeout có kiểm soát.

Ví dụ backend:

~~~hcl
terraform {
  backend "gcs" {
    bucket = "ORG_TERRAFORM_STATE"
    prefix = "orders-api/production"
  }
}
~~~

Tên bucket và prefix là ví dụ. Bucket state nên được tạo và bảo vệ trong một quy trình bootstrap riêng; không để pipeline đang tạo bucket state phụ thuộc vào chính state chưa tồn tại.

### 9.3. Saved plan và approval

Một file `tfplan` có thể chứa giá trị cấu hình nhạy cảm. Lưu nó như artifact nội bộ có kiểm soát truy cập và thời gian lưu ngắn. Chỉ apply plan từ đúng commit, workspace/state và pipeline run đã được review. Nếu state hoặc tài nguyên thay đổi làm plan hết hiệu lực, tạo plan mới và yêu cầu review lại.

Ví dụ các lệnh trong job:

~~~bash
terraform init -input=false
terraform fmt -check -recursive
terraform validate
terraform plan -input=false -out=tfplan
terraform show -no-color tfplan
# Sau approval, trong job apply được bảo vệ:
terraform apply -input=false tfplan
~~~

Đây là chuỗi lệnh minh họa. Cần tách job plan và apply theo cơ chế artifact/approval của CI system, đồng thời giữ đúng commit và state backend. Không đưa plan hoặc state vào repository.

### 9.4. Policy as code và drift detection

Policy as code có thể chặn các thay đổi như:

- Mở SSH/RDP cho toàn Internet.
- Tạo bucket dữ liệu không có public access prevention.
- Gán role Owner/Editor ở phạm vi không được phép.
- Tạo database public không có phê duyệt.
- Tạo tài nguyên ở region không được tổ chức chấp thuận.
- Tắt logging, encryption hoặc backup bắt buộc.

Chạy drift detection định kỳ để so sánh cấu hình thực tế với IaC. Khi phát hiện drift, xác định thay đổi là thao tác hợp lệ, sự cố hay cấu hình ngoài quy trình. Không tự động apply để xóa drift khi chưa hiểu tác động; có thể vô tình ghi đè thay đổi khẩn cấp hoặc thay đổi có chủ đích.

## 10. Bảo vệ pipeline và môi trường triển khai

### 10.1. Phân tách project và quyền

Một mô hình thường dùng là tách project quản lý CI/CD, project artifact và project runtime theo yêu cầu bảo mật. Không bắt buộc phải tạo project riêng cho mọi thành phần; hãy dùng ranh giới project/folder để tách blast radius, billing, quota và quyền.

Kiểm soát tối thiểu:

- Build service account chỉ push vào repository cần thiết.
- Deploy service account chỉ triển khai vào target được giao.
- Terraform apply identity chỉ thay đổi tài nguyên của environment tương ứng.
- Người tạo trigger không mặc nhiên được cấp quyền production.
- Chỉ nhóm platform/security được thay đổi pipeline config, service account hoặc policy nhạy cảm.
- Dùng approval độc lập cho production và thay đổi IAM/network/database có rủi ro cao.
- Audit log cho việc thay đổi trigger, IAM, pipeline, target và policy.

### 10.2. Bảo vệ build environment

Build config và builder image là một phần của software supply chain. Kẻ tấn công có thể sửa build script, thay dependency, lấy credential từ môi trường hoặc thay artifact được xuất bản.

Các biện pháp:

- Review thay đổi trong `cloudbuild.yaml`, Dockerfile, Skaffold và Terraform.
- Dùng builder image được kiểm soát, pin version/digest và rà soát nguồn.
- Dùng build worker tạm thời, hạn chế kết nối mạng và quyền truy cập ngoài nhu cầu.
- Với build cần private network, cân nhắc Cloud Build private pools.
- Tách PR build không tin cậy khỏi release build có secret và quyền deploy.
- Không truyền secret qua command-line argument hoặc log.
- Bật provenance và lưu build log theo chính sách retention.
- Giới hạn quyền sửa build trigger và service account của trigger.

### 10.3. Tách môi trường và cấu hình

Không dùng cùng một project, database hoặc secret cho dev, staging và production nếu điều đó làm mất khả năng cô lập. Cấu hình môi trường có thể được truyền qua substitutions hoặc environment-specific manifest, nhưng không nên dùng biến đầu vào tùy ý để thay đổi image digest hay service account production.

Một release nên giữ nguyên artifact qua các môi trường. Chỉ cấu hình runtime như hostname, replica count, secret reference và quota mới thay đổi theo target. Không build lại image khi promote từ staging sang production.

## 11. Database migration và thay đổi không thể rollback đơn giản

Triển khai ứng dụng thường đi cùng schema migration. Rollback container không đồng nghĩa rollback dữ liệu. Một migration xóa cột hoặc đổi kiểu dữ liệu có thể khiến phiên bản ứng dụng trước đó không còn hoạt động.

Dùng quy trình expand-and-contract:

1. **Expand:** thêm cột hoặc bảng mới theo cách tương thích ngược.
2. **Deploy code:** ứng dụng mới có thể đọc/ghi cấu trúc cũ và mới trong giai đoạn chuyển tiếp.
3. **Migrate data:** chuyển dữ liệu theo batch, có kiểm tra và checkpoint.
4. **Switch:** chuyển ứng dụng sang schema mới.
5. **Contract:** chỉ xóa cấu trúc cũ sau khi xác nhận không còn phiên bản nào phụ thuộc.

Với migration lớn, chạy như một job có kiểm soát, có lock hoặc cơ chế chống chạy trùng và có khả năng tiếp tục sau lỗi. Đặt backup/restore plan và kiểm tra thời gian phục hồi. Không gộp migration phá hủy dữ liệu vào rollout ứng dụng mà không có review riêng.

## 12. Vận hành release và quan sát sau triển khai

Một rollout thành công về mặt công cụ chưa chắc ứng dụng hoạt động tốt. Sau mỗi lần deploy, theo dõi:

- Tỷ lệ request thành công và lỗi theo phiên bản.
- p50, p95, p99 latency.
- CPU, memory, concurrency, queue depth và autoscaling.
- Error logs và exception mới.
- Database connection, query latency và migration status.
- Quota và rate limit của các GCP APIs.
- Business metric như tỷ lệ thanh toán thành công hoặc số job hoàn tất.
- SLO và error budget.

Dùng label hoặc resource metadata để gắn release ID, commit SHA và service version vào metric/log khi phù hợp. Tránh tạo metric label có cardinality cao như request ID hoặc user ID.

Nếu canary có error rate hoặc latency vượt ngưỡng, dừng promotion và đánh giá rollback. Khi rollback, ghi lại release cũ, release lỗi, metric gây quyết định và kết quả sau rollback. Nếu sự cố do hạ tầng hoặc database migration, rollback ứng dụng có thể chưa đủ; cần playbook tương ứng.

## 13. Tình huống thực hành: phát hành một Java API lên Cloud Run

Một nhóm phát triển dịch vụ Java tên `orders-api`. Source code nằm trong GitHub, image được lưu ở Artifact Registry và workload chạy trên Cloud Run. Hạ tầng Cloud Run, service account, IAM và database được quản lý bằng Terraform.

### Thiết kế pipeline

1. Developer mở pull request. Cloud Build chạy Maven verify, static analysis, secret scan và kiểm tra Terraform nếu thay đổi chạm vào `infra/`.
2. Reviewer kiểm tra code, dependency changes, Dockerfile và Terraform plan. Pull request build không có quyền deploy production hoặc đọc secret production.
3. Sau khi merge vào protected branch, release trigger chạy build từ commit đã duyệt. Cloud Build build image, chạy test, push image lên Artifact Registry và ghi nhận digest.
4. Artifact Analysis quét image/package. Build provenance được tạo; policy kiểm tra lỗ hổng và nguồn build.
5. CI tạo Cloud Deploy release tham chiếu image digest đã kiểm tra. Cloud Deploy triển khai vào staging.
6. Verification chạy smoke test: health endpoint, kết nối database, đọc Secret Manager và một luồng nghiệp vụ cơ bản.
7. Release được đề nghị promotion vào production. Người có quyền approval kiểm tra test, scan, provenance và rollout plan.
8. Cloud Deploy triển khai theo chiến lược phù hợp. Cloud Monitoring theo dõi error rate, latency và business metrics.
9. Nếu canary không đạt ngưỡng, dừng promotion và tạo rollout rollback về release đã hoạt động tốt. Nếu database schema đã thay đổi, dùng playbook migration riêng.
10. Thay đổi hạ tầng được thực hiện trong pipeline Terraform: plan, review, approval và apply bằng identity riêng. State lưu trong GCS backend có versioning và quyền hạn chế.

### Tiêu chí hoàn thành

- Có thể truy từ release về commit SHA, build ID và image digest.
- Image production chính là image đã qua staging và scan.
- Không có service account key dài hạn trong repository hoặc CI secret.
- Pull request không tin cậy không thể deploy hoặc đọc secret production.
- Terraform plan được review trước apply; state tách theo môi trường.
- Production promotion có approval và verification.
- Có dashboard, alert và playbook rollback.
- Database migration có kế hoạch tương thích và phục hồi.

## 14. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Build lại image cho từng môi trường | Artifact production khác artifact staging | Promote cùng digest |
| Dùng tag `latest` | Không xác định được chính xác image đang chạy | Dùng digest và tag gắn commit/release |
| Build trigger có quyền Owner | Mã nguồn PR có thể thực thi thao tác quá rộng | Dùng service account riêng, least privilege |
| Lưu service account key trong GitHub secret lâu dài | Rủi ro rò rỉ và khó xoay vòng | Dùng Workload Identity Federation |
| Không kiểm tra builder và dependency | Artifact có thể bị thay đổi từ nguồn không tin cậy | Pin version, review nguồn, scan và provenance |
| Terraform apply trực tiếp từ branch | Thay đổi production không có plan review | Saved plan, approval và apply đúng plan |
| Dùng chung Terraform state giữa môi trường | Blast radius lớn, dễ ghi nhầm môi trường | State riêng theo environment |
| Cho PR build đọc secret production | Mã nguồn chưa tin cậy có thể lấy secret | Tách PR validation và release build |
| Không có verification sau deploy | Rollout xanh nhưng ứng dụng lỗi | Smoke test, canary và SLO monitoring |
| Rollback ứng dụng nhưng bỏ qua database | Phiên bản cũ không tương thích schema mới | Expand-and-contract và migration playbook |

## 15. Checklist trước khi đưa pipeline vào production

### Source và CI

- [ ] Source, Dockerfile, build config, manifest và IaC được version control.
- [ ] Pull request có review bắt buộc và branch protection.
- [ ] Trigger theo branch/path được kiểm soát.
- [ ] PR build không có quyền production hoặc secret production.
- [ ] Unit, integration, static analysis và dependency checks chạy tự động.
- [ ] Builder image và dependency được pin, review và quản lý nguồn.

### Artifact và supply chain

- [ ] Artifact Registry repository có IAM và retention policy phù hợp.
- [ ] Artifact được tham chiếu bằng digest bất biến.
- [ ] Vulnerability scanning được bật cho loại artifact cần kiểm tra.
- [ ] Build provenance được tạo và có thể xác minh.
- [ ] SBOM/attestation được lưu khi chính sách yêu cầu.
- [ ] Binary Authorization hoặc deploy policy được áp dụng cho runtime phù hợp.

### Identity và secrets

- [ ] Build, deploy, Terraform apply và runtime dùng danh tính riêng.
- [ ] Service account chỉ có quyền cần thiết.
- [ ] External CI dùng Workload Identity Federation nếu hỗ trợ.
- [ ] Secret nằm trong Secret Manager và chỉ được cấp cho step cần dùng.
- [ ] Không ghi token, key hoặc secret vào log/artifact.

### CD và IaC

- [ ] Release liên kết với commit SHA và artifact digest.
- [ ] Staging verification chạy trước production.
- [ ] Production có approval và rollout strategy.
- [ ] Có phương án rollback và hiểu giới hạn của database migration.
- [ ] Terraform luôn tạo plan trước; plan được review và apply đúng bản đã duyệt.
- [ ] State remote có quyền hạn chế, versioning và locking.
- [ ] Có drift detection và policy checks.

### Vận hành

- [ ] Release ID/version xuất hiện trong telemetry.
- [ ] Dashboard theo dõi error rate, latency, saturation và business metrics.
- [ ] Có alert theo SLO và error budget.
- [ ] Có playbook dừng rollout, rollback và điều tra.
- [ ] Có quy trình thu hồi credential và xử lý artifact bị phát hiện lỗ hổng.

## 16. Câu hỏi tự kiểm tra

1. Vì sao cần tách pull request validation build khỏi release build có quyền deploy?
2. Cloud Build, Artifact Registry và Cloud Deploy đảm nhiệm những phần nào khác nhau?
3. Vì sao promotion từ staging sang production nên dùng cùng image digest?
4. Build provenance cho biết điều gì và không chứng minh được điều gì?
5. Workload Identity Federation giúp giảm rủi ro nào khi dùng GitHub Actions hoặc GitLab?
6. Vì sao Terraform cần saved plan và approval trước apply?
7. Nếu Terraform plan thay đổi sau khi đã được phê duyệt, pipeline nên làm gì?
8. Cloud Deploy verification và canary rollout hỗ trợ phát hiện regression như thế nào?
9. Vì sao rollback container có thể không khôi phục được database sau migration phá hủy?
10. Những quyền nào nên tách giữa build service account, deploy service account và runtime service account?

## Tài liệu tham khảo

- [Cloud Build overview](https://docs.cloud.google.com/build/docs/overview)
- [Create and manage Cloud Build triggers](https://docs.cloud.google.com/build/docs/automating-builds/create-manage-triggers)
- [Run builds with a user-managed service account](https://docs.cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts)
- [Safeguard builds](https://docs.cloud.google.com/software-supply-chain-security/docs/safeguard-builds)
- [Use secrets from Secret Manager in Cloud Build](https://docs.cloud.google.com/build/docs/securing-builds/use-secrets)
- [Generate and validate build provenance](https://docs.cloud.google.com/build/docs/securing-builds/generate-build-provenance)
- [Artifact Analysis package scanning](https://docs.cloud.google.com/artifact-analysis/docs/package-scanning-overview)
- [Software supply chain security overview](https://docs.cloud.google.com/software-supply-chain-security/docs/overview)
- [Configure Workload Identity Federation with deployment pipelines](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)
- [Cloud Deploy overview](https://docs.cloud.google.com/deploy/docs/overview)
- [Create Cloud Deploy delivery pipelines and targets](https://docs.cloud.google.com/deploy/docs/create-pipeline-targets)
- [Verify a Cloud Deploy deployment](https://docs.cloud.google.com/deploy/docs/verify-deployment)
- [Promote a release and manage approvals](https://docs.cloud.google.com/deploy/docs/promote-release)
- [Roll back a Cloud Deploy target](https://docs.cloud.google.com/deploy/docs/roll-back)
- [Terraform operations best practices](https://docs.cloud.google.com/docs/terraform/best-practices/operations)

