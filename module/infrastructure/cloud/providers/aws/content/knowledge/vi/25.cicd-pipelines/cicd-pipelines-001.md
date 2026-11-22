# Thiết kế pipeline build, test, release và rollback

Một nhóm phát triển có thể hoàn thành tính năng trong vài giờ, nhưng đưa thay đổi đó lên production cần nhiều bước: lấy source code, build artifact, chạy tests, quét lỗ hổng, đóng gói container, triển khai lên môi trường kiểm thử, chờ approval và phát hành có kiểm soát. Nếu mỗi lần release phải làm thủ công, quy trình dễ bỏ sót bước, khó lặp lại và khó biết chính xác phiên bản nào đang chạy.

**CI/CD (Continuous Integration / Continuous Delivery hoặc Deployment)** tự động hóa đường đi từ source code đến môi trường chạy. Trên AWS, một pipeline thường kết hợp **AWS CodePipeline** để điều phối stages/actions, **AWS CodeBuild** để build/test, **Amazon ECR** để lưu container images, **Amazon S3** làm artifact store, và **AWS CodeDeploy/CloudFormation/ECS/Lambda/EKS** để triển khai. Pipeline cũng cần IAM roles, KMS encryption, approvals, monitoring và rollback.

Bài học thuộc chương **CI/CD trên AWS** của mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung kết nối quy trình release với Region/AZ, IAM, VPC, compute, storage, database, integration và serverless; mục tiêu là tạo pipeline an toàn, quan sát được, có thể phục hồi và kiểm soát chi phí.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt Continuous Integration, Continuous Delivery và Continuous Deployment.
2. Thiết kế pipeline theo stages từ source, build, test, security scan, artifact, deploy đến verify.
3. Chọn AWS CodePipeline, CodeBuild, CodeDeploy, ECR, S3, CodeArtifact và CloudFormation theo nhiệm vụ.
4. Thiết kế artifact bất biến, versioning, image digest và promotion qua môi trường.
5. Cấu hình buildspec, test reports, caching và build environment.
6. Dùng IAM roles, AWS CodeConnections, OIDC federation và cross-account roles thay access keys dài hạn.
7. Triển khai ứng dụng lên ECS, EKS, Lambda và hạ tầng bằng CloudFormation/CDK/SAM.
8. Chọn rolling, blue/green, canary hoặc linear deployment theo yêu cầu availability.
9. Thiết lập manual approval, automated gates, CloudWatch alarms và rollback.
10. Theo dõi pipeline executions, logs, deployment events, audit trail và chi phí.
11. Xử lý build failure, test failure, deployment failure, rollback failure và artifact mismatch.

## 2. CI, Continuous Delivery và Continuous Deployment

Ba khái niệm liên quan nhưng khác nhau:

| Khái niệm | Ý nghĩa | Điểm quyết định |
|---|---|---|
| **Continuous Integration (CI)** | Mỗi thay đổi được tích hợp thường xuyên, build và test tự động | Tự động xác minh chất lượng source |
| **Continuous Delivery** | Artifact luôn ở trạng thái có thể phát hành sau các kiểm tra; production release có thể cần approval | Con người/quy trình quyết định thời điểm production |
| **Continuous Deployment** | Thay đổi vượt qua toàn bộ gates được tự động đưa vào production | Không cần approval thủ công cho từng release |

Continuous Deployment không có nghĩa deploy bất kỳ commit nào ngay lập tức. Nó chỉ phù hợp khi tests, security gates, rollout controls, monitoring và rollback đủ tin cậy. Với hệ thống tài chính hoặc workload có change management bắt buộc, Continuous Delivery với approval vẫn có thể là lựa chọn phù hợp.

### 2.1. Pipeline là một đồ thị các bước có điều kiện

Pipeline có thể chạy tuần tự hoặc song song. Ví dụ, unit tests, dependency scan và IaC scan có thể chạy song song sau khi source được checkout; deployment chỉ bắt đầu khi các gates bắt buộc đều pass.

~~~mermaid
flowchart TD
    SRC["Git commit / Pull request"] --> SOURCE["Source stage"]
    SOURCE --> BUILD["Build & package"]
    BUILD --> PARALLEL{"Quality gates"}
    PARALLEL --> UNIT["Unit / integration tests"]
    PARALLEL --> SAST["SAST / dependency scan"]
    PARALLEL --> IAC["IaC / container scan"]
    UNIT --> GATE["All required checks pass"]
    SAST --> GATE
    IAC --> GATE
    GATE --> ART["Publish immutable artifact"]
    ART --> TEST["Deploy test / staging"]
    TEST --> VERIFY["Smoke / contract / acceptance tests"]
    VERIFY --> APPROVE{"Production approval"}
    APPROVE -->|"Approved"| PROD["Production deployment"]
    APPROVE -->|"Rejected"| STOP["Stop / discard release"]
    PROD --> OBS["Observe health & metrics"]
    OBS --> RESULT{"Healthy?"}
    RESULT -->|"Yes"| DONE["Release complete"]
    RESULT -->|"No"| ROLLBACK["Rollback / traffic shift back"]
~~~

### 2.2. Pipeline phải có đầu vào và đầu ra rõ ràng

| Đầu vào | Xử lý | Đầu ra |
|---|---|---|
| Git commit/tag | Checkout source, kiểm tra branch/tag | Source revision bất biến |
| Maven/Gradle project | Compile, unit test, package | JAR/WAR |
| Dockerfile | Build image, scan, tag | Container image digest |
| CloudFormation/CDK/SAM template | Validate, lint, policy scan, change set | IaC artifact/change set |
| Release metadata | Gắn version, commit SHA, build ID | Deployment manifest/SBOM |

Một release phải truy ngược được: **source commit → build execution → test reports → artifact digest → deployment execution → runtime version**.

## 3. Kiến trúc CI/CD phổ biến trên AWS

Một pipeline native AWS thường sử dụng:

| Dịch vụ | Vai trò chính |
|---|---|
| **AWS CodePipeline** | Điều phối stages, actions, artifacts, approvals và triggers |
| **AWS CodeBuild** | Build, unit/integration tests, package, lint và scan |
| **AWS CodeConnections** | Kết nối source providers như GitHub/GitLab/Bitbucket theo hỗ trợ |
| **Amazon S3** | Artifact store cho CodePipeline và build outputs |
| **AWS KMS** | Mã hóa artifact store và các tài nguyên hỗ trợ encryption |
| **Amazon ECR** | Lưu container images, image scanning và lifecycle |
| **AWS CodeDeploy** | Deployment orchestration cho EC2/on-premises, ECS blue/green và Lambda |
| **AWS CloudFormation** | Provision/update hạ tầng và change sets |
| **AWS CodeArtifact** | Lưu package dependencies nội bộ như Maven/npm/PyPI |
| **Amazon CloudWatch** | Logs, metrics, alarms và deployment health signals |
| **AWS CloudTrail** | Audit các API calls/control-plane events theo cấu hình |

~~~mermaid
flowchart LR
    GIT["Git provider"] --> CP["CodePipeline"]
    CP --> CB["CodeBuild<br/>Build / Test / Scan"]
    CB --> ART["S3 artifact store"]
    CB --> ECR["Amazon ECR<br/>Image digest"]
    ART --> TEST["Test / Staging deploy"]
    ECR --> TEST
    TEST --> GATE["Approval / quality gate"]
    GATE --> PROD["Production deploy"]
    PROD --> CD["CodeDeploy / ECS / Lambda / EKS"]
    PROD --> CFN["CloudFormation / CDK"]
    CD --> CW["CloudWatch alarms"]
    CFN --> CW
    CP --> CT["CloudTrail audit"]
~~~

Không bắt buộc mọi dự án phải dùng tất cả dịch vụ. Ví dụ, ứng dụng Java chạy ECS có thể dùng CodePipeline + CodeBuild + ECR + ECS deploy action; ứng dụng Lambda có thể dùng CodeBuild + SAM/CloudFormation + Lambda deployment preferences/CodeDeploy; nhóm GitOps EKS có thể dùng pipeline cập nhật manifest/Helm chart trong Git repository triển khai.

## 4. Chọn mô hình pipeline và công cụ

### 4.1. CodePipeline hay GitHub Actions?

CodePipeline phù hợp khi tổ chức muốn điều phối deployment native AWS, tích hợp IAM/CloudFormation/ECS/CodeDeploy và quản lý artifacts trong AWS. GitHub Actions phù hợp khi source, pull requests và workflow engineering tập trung ở GitHub; có thể assume AWS role qua OIDC để deploy.

| Tiêu chí | AWS CodePipeline | GitHub Actions |
|---|---|---|
| Orchestration | Stages/actions, execution modes, approvals | Workflows/jobs/steps |
| Source integration | CodeConnections, S3, CodeCommit theo hỗ trợ hiện hành | GitHub native |
| AWS identity | Pipeline/service/action roles | OIDC assume role hoặc credentials provider |
| Artifact storage | S3 artifact store | Workflow artifacts, ECR/S3 hoặc package registries |
| AWS deployment | Native actions và integrations | AWS CLI/CDK/SAM/SDK và actions |
| Approval | Manual approval action | Environment protection rules/reviewers |
| Best fit | AWS-centric release orchestration | GitHub-centric CI/CD và đa cloud |

Hai lựa chọn có thể kết hợp, nhưng tránh tạo hai pipeline cùng deploy một stack hoặc cùng cập nhật một service mà không có locking/ownership rõ ràng.

### 4.2. CodePipeline V1 và V2

CodePipeline có các pipeline types với khả năng và pricing khác nhau. V2 hỗ trợ thêm các trigger/filter và execution modes như queued, superseded hoặc parallel theo cấu hình; V1 có giới hạn tính năng khác. Chọn pipeline type theo yêu cầu concurrency, triggers và pricing hiện hành. Không giả định đổi type chỉ là metadata update không ảnh hưởng behavior.

### 4.3. Một pipeline lớn hay nhiều pipeline nhỏ?

Tách pipeline khi:

- Service có owner, release cadence hoặc rollback boundary riêng.
- Artifact/deployment targets khác nhau.
- Cần giới hạn IAM permissions theo service.
- Một pipeline dài gây queueing hoặc blast radius lớn.

Giữ một pipeline khi các components phải phát hành đồng bộ và có dependency/version contract rõ. Với monorepo, có thể dùng path filters để chỉ build/deploy services bị ảnh hưởng, nhưng phải kiểm soát shared libraries và dependency graph.

## 5. Source stage và quản lý phiên bản

Source stage quyết định code nào được đưa vào pipeline. Trigger có thể là commit, tag, pull request hoặc lịch chạy; cần tách validation workflows khỏi production release workflows.

### 5.1. Branch và tag strategy

Một mô hình đơn giản:

| Event | Pipeline behavior |
|---|---|
| Pull request | Build, unit tests, static analysis, IaC validation; không deploy production |
| Merge vào main | Build artifact và deploy integration/staging |
| Release tag vX.Y.Z | Tạo release candidate/production pipeline |
| Hotfix branch/tag | Pipeline có kiểm soát, approval và audit riêng |

Branch protection yêu cầu review, status checks và signed commits/tags nếu policy tổ chức cần. Không để pipeline production tự chạy từ branch bất kỳ.

### 5.2. CodeConnections cho GitHub

CodePipeline có thể kết nối repository thông qua **AWS CodeConnections** (tên cũ trong tài liệu/console có thể là CodeStar Connections). Connection cần được tạo/ủy quyền với source provider; pipeline role cần quyền sử dụng connection ARN. Không nhúng Git personal access token vào buildspec hoặc source repository.

### 5.3. Commit SHA và source revision

Mỗi build nên lưu:

- Repository và commit SHA.
- Branch/tag và pull request ID nếu có.
- Pipeline execution ID và CodeBuild build ID.
- Build timestamp và toolchain versions.
- Release version và artifact digest.

Tag latest không đủ để chứng minh artifact đang chạy là artifact nào. Dùng commit SHA/version tag bất biến và image digest.

### 5.4. Source archive và reproducibility

Build nên chạy trên source snapshot cụ thể. Không clone một branch mutable lần thứ hai giữa các stages rồi vô tình build code mới hơn source artifact ban đầu. Nếu build phụ thuộc submodules, Git LFS hoặc generated files, ghi rõ version và đảm bảo chúng được checkout reproducibly.

## 6. Build stage với AWS CodeBuild

CodeBuild chạy build commands trong môi trường được quản lý hoặc custom container image. Build project xác định source, environment image, compute, service role, environment variables, cache, artifacts và logs.

### 6.1. Buildspec

Buildspec là file YAML mô tả các phases như install, pre_build, build, post_build, artifacts, reports và cache. Có thể đặt buildspec.yml ở root hoặc chỉ định path khác trong project.

Ví dụ Java Maven:

~~~yaml
version: 0.2

env:
  variables:
    MAVEN_OPTS: "-Dmaven.repo.local=.m2/repository"

phases:
  install:
    runtime-versions:
      java: corretto21
    commands:
      - java -version
      - mvn -version
  pre_build:
    commands:
      - echo "Validating source revision"
      - test -f pom.xml
  build:
    commands:
      - mvn -B clean verify
  post_build:
    commands:
      - echo "Build completed"

reports:
  junit-reports:
    files:
      - "**/surefire-reports/TEST-*.xml"
      - "**/failsafe-reports/TEST-*.xml"
    base-directory: target
    file-format: JUNITXML

artifacts:
  files:
    - target/*.jar
  discard-paths: yes

cache:
  paths:
    - ".m2/repository/**/*"
~~~

Đây là ví dụ buildspec cho Maven; kiểm tra runtime image và version CodeBuild hỗ trợ trước khi chọn corretto21. Nếu dự án dùng Gradle, thay commands và cache theo Gradle wrapper/cache. Không dùng clean verify nếu build lifecycle của dự án có side effects ngoài dự kiến.

### 6.2. Các phases

| Phase | Công việc | Ví dụ |
|---|---|---|
| install | Cài toolchain/runtime | JDK, Maven, Docker CLI |
| pre_build | Xác thực môi trường, đăng nhập registry, chuẩn bị config | ECR login, version metadata |
| build | Compile, test, package, container build | mvn verify, docker build |
| post_build | Publish, tạo metadata, báo trạng thái | Push image, write manifest |

### 6.3. Exit code phải phản ánh kết quả thật

Nếu test hoặc scan thất bại, build command cần trả exit code non-zero để CodeBuild/CodePipeline đánh dấu action failed. Tránh viết shell scripts luôn exit 0 hoặc dùng || true cho security/test commands bắt buộc.

### 6.4. Test reports

CodeBuild có thể thu thập test reports để hiển thị kết quả và lưu báo cáo. Nên phân biệt:

- Unit tests chạy nhanh, không phụ thuộc AWS thật.
- Integration tests với LocalStack hoặc test account/resources riêng.
- Contract tests kiểm tra tương thích giữa services.
- End-to-end tests kiểm tra luồng nghiệp vụ quan trọng.
- Performance/load tests chạy có kiểm soát, không chạy mọi commit nếu chi phí lớn.

## 7. Quality gates và security checks

Pipeline chỉ có giá trị khi các gates phản ánh rủi ro thực. Không dồn tất cả vào một lệnh build mà không lưu kết quả và không biết lỗi ở đâu.

### 7.1. Bộ kiểm tra đề xuất

| Gate | Ví dụ công cụ/kiểm tra | Điều kiện pass |
|---|---|---|
| Compile | Maven/Gradle | Không compile errors |
| Unit test | JUnit, Mockito | Tất cả tests critical pass |
| Static analysis | SonarQube, Checkstyle, SpotBugs | Không vượt quality threshold |
| Dependency scan | OWASP Dependency-Check, SCA service | Không có critical/high unresolved theo policy |
| Secret scan | Git/provider scanning, gitleaks | Không phát hiện secret hợp lệ |
| IaC scan | cfn-lint, cfn-guard, policy scanners | Template hợp lệ và tuân policy |
| Container scan | ECR image scanning hoặc scanner được duyệt | Vulnerability policy pass |
| SBOM | Syft/CycloneDX/Maven plugin | SBOM được tạo và gắn với artifact |
| License check | Dependency/license policy | Dependency license được phê duyệt |
| Integration tests | Test environment | Contract/API checks pass |

### 7.2. Scan findings cần có exception process

Một CVE có thể không khai thác được trong ứng dụng hoặc chưa có bản vá. Không nên tắt scan toàn bộ khi một finding gây fail. Tạo exception có owner, rationale, expiry date, compensating controls và ticket remediation; pipeline chỉ bypass finding đã được phê duyệt theo policy.

### 7.3. IaC validation

Trước deploy CloudFormation/CDK/SAM:

- Parse/validate template.
- Lint resource properties và intrinsic functions.
- Check IAM wildcard/public exposure/encryption requirements.
- Tạo change set và review replacement/removals.
- Kiểm tra CloudFormation Guard/policy-as-code nếu tổ chức dùng.

Template hợp lệ về syntax không đồng nghĩa kiến trúc an toàn. Change set review và policy checks bổ sung cho nhau.

### 7.4. Không để secrets trong build logs

Secrets cần lấy từ Secrets Manager/Parameter Store hoặc CodeBuild environment variables kiểu secret với quyền tối thiểu. Không echo environment, không bật shell tracing cho lệnh chứa secret và không truyền secret qua command-line arguments dễ bị log. Masking logs không phải bảo đảm tuyệt đối; tránh để secret xuất hiện ngay từ đầu.

## 8. Build và push container image lên Amazon ECR

Với ứng dụng Spring Boot chạy ECS/EKS, pipeline thường build JAR, tạo container image, scan image và push vào Amazon ECR.

### 8.1. Dockerfile tối thiểu

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/orders-api.jar app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Đây là ví dụ minh họa. Production image nên pin base image bằng digest, chạy non-root, chỉ copy runtime artifacts, áp dụng multi-stage build khi cần và cập nhật base image theo security policy. Không đưa AWS credentials hoặc application secrets vào image layers.

### 8.2. Buildspec push image theo commit SHA

Ví dụ Linux CodeBuild project đã bật privileged mode nếu dùng Docker daemon, có ECR repository URI trong cấu hình project:

~~~yaml
version: 0.2

env:
  variables:
    ECR_REPOSITORY_URI: "444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api"

phases:
  pre_build:
    commands:
      - ECR_REGISTRY="$(echo "$ECR_REPOSITORY_URI" | cut -d/ -f1)"
      - aws ecr get-login-password --region "$AWS_DEFAULT_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"
      - COMMIT_SHA="$(echo "$CODEBUILD_RESOLVED_SOURCE_VERSION" | cut -c 1-12)"
      - IMAGE_TAG="$COMMIT_SHA"
  build:
    commands:
      - mvn -B clean verify
      - docker build -t "$ECR_REPOSITORY_URI:$IMAGE_TAG" .
  post_build:
    commands:
      - docker push "$ECR_REPOSITORY_URI:$IMAGE_TAG"
      - printf '{"imageUri":"%s","imageTag":"%s","commit":"%s"}\n' "$ECR_REPOSITORY_URI" "$IMAGE_TAG" "$CODEBUILD_RESOLVED_SOURCE_VERSION" > image-detail.json

artifacts:
  files:
    - image-detail.json
~~~

Đây là ví dụ để giải thích flow; cần đặt ECR_REPOSITORY_URI và AWS_DEFAULT_REGION đúng trong project/environment, bảo đảm source có Dockerfile và JAR ở đúng path. Với source trigger không phải Git commit, CODEBUILD_RESOLVED_SOURCE_VERSION có thể có semantics khác; validate giá trị trước khi dùng làm tag.

### 8.3. IAM permissions cho CodeBuild

CodeBuild service role thường cần quyền:

- ECR authorization token theo scope mà AWS yêu cầu.
- ECR upload layer/image actions trên đúng repository.
- Ghi build logs vào CloudWatch Logs.
- Đọc package dependencies từ CodeArtifact nếu sử dụng.
- Đọc parameters/secrets cần cho build, chỉ khi thật sự cần.
- Ghi artifacts vào S3 artifact store theo pipeline configuration.

Không cấp ECR full access hoặc AdministratorAccess chỉ để push image. Tách quyền build/push khỏi quyền deploy production khi pipeline architecture cho phép.

### 8.4. Image tag và digest

Tag commit SHA giúp truy vết source; **image digest** là định danh nội dung bất biến của image manifest. Khi deploy production, ưu tiên image URI có digest, ví dụ:

~~~text
444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api@sha256:...
~~~

Tag có thể bị overwrite nếu ECR repository không bật tag immutability. Bật immutable tags cho release repositories và lưu digest trong release manifest. Không dùng latest làm nguồn xác định release.

### 8.5. Scan image và promotion

ECR image scanning có thể phát hiện vulnerabilities theo chế độ scan/configuration đang bật. Pipeline nên đợi kết quả scan và áp dụng threshold policy trước deploy. Nếu promotion qua account/Region, có thể dùng ECR replication hoặc copy image có kiểm soát; sau copy, xác minh digest và provenance ở destination repository.

## 9. Artifact store, CodeArtifact và tính bất biến

CodePipeline lưu intermediate artifacts trong S3 artifact bucket. Artifact store phải được thiết kế như một thành phần production:

- Bật encryption bằng SSE-KMS theo policy.
- Block public access, bucket policy giới hạn pipeline roles.
- Versioning/lifecycle phù hợp với retention và audit requirements.
- Không dùng bucket chung không kiểm soát giữa nhiều tổ chức/ứng dụng.
- Xác định cross-Region artifact stores khi pipeline có actions ở Region khác.
- Cấu hình KMS key policies cho pipeline role, action roles và account đích.

### 9.1. Pipeline artifacts khác application artifacts

Pipeline artifact là file trao đổi giữa actions/stages, ví dụ source archive, test report, template hoặc deployment manifest. Application artifact là JAR/WAR/container image được release. Không nên coi file ZIP intermediate trong S3 là nguồn duy nhất để xác định runtime image nếu deployment thực tế dùng ECR digest.

### 9.2. Release manifest

Một manifest có thể ghi:

~~~json
{
  "service": "orders-api",
  "version": "1.8.0",
  "sourceCommit": "0123456789abcdef",
  "buildId": "orders-build:1042",
  "imageUri": "444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api@sha256:REPLACE_WITH_DIGEST",
  "sbom": "artifacts/orders-api-1.8.0.cdx.json",
  "createdAt": "2026-11-20T04:00:00Z"
}
~~~

Manifest trên là ví dụ; thay digest bằng giá trị thực từ image push. Không ghi secrets, environment-specific credentials hoặc secret values vào manifest. Có thể bổ sung signature, provenance attestation và deployment config version.

### 9.3. CodeArtifact cho dependencies nội bộ

AWS CodeArtifact có thể lưu Maven, npm, Python và package formats được hỗ trợ. Dùng repository nội bộ để:

- Cache/proxy dependencies từ public repositories.
- Phân phối shared libraries và internal SDKs.
- Kiểm soát package versions, upstream sources và access policies.
- Giảm rủi ro dependency confusion bằng namespace/source policy.

Build role cần quyền authenticate/read package repositories; publish role cần quyền write/publish. Không để mọi build jobs có quyền overwrite package release versions.

### 9.4. Reproducible builds và dependency pinning

- Dùng Maven Wrapper/Gradle Wrapper và pin plugin versions.
- Pin container base image bằng digest.
- Không dùng dependency version động như LATEST hoặc SNAPSHOT cho release production nếu không có kiểm soát.
- Lưu SBOM, build metadata và checksums.
- Cache chỉ là optimization; cache miss không được làm build thay đổi kết quả.
- Tách build-time credentials khỏi runtime credentials.

## 10. Cấu trúc CodePipeline và action artifacts

Một CodePipeline thường có các stages, mỗi stage có một hoặc nhiều actions. Actions có thể tiêu thụ artifact từ action trước và tạo output artifact cho stage tiếp theo.

### 10.1. Pipeline stages mẫu

| Stage | Action provider | Input | Output / gate |
|---|---|---|---|
| Source | CodeConnections | Git commit | SourceArtifact |
| Build | CodeBuild | SourceArtifact | AppArtifact, test reports |
| Security | CodeBuild/approved scanner | AppArtifact | Scan reports, pass/fail |
| Image | CodeBuild | AppArtifact | ECR image digest + manifest |
| Deploy test | ECS/CloudFormation/CodeDeploy | Manifest/template | Test environment |
| Verify | CodeBuild | Test endpoint/config | Smoke test result |
| Approval | Manual approval | Release summary | Approved/rejected |
| Deploy prod | ECS/CodeDeploy/CloudFormation | Same digest/template | Production deployment |
| Observe | CloudWatch/CodeBuild | Runtime metrics | Release accepted/rollback |

### 10.2. Artifact names và namespace

Đặt tên artifact rõ nghĩa, ví dụ SourceArtifact, BuildArtifact, ImageManifest, IaCTemplate. Không ghi đè artifact giữa parallel executions bằng S3 key tự đặt dùng chung; dùng execution-specific paths và giữ liên kết đến execution ID.

### 10.3. Manual approval action

Manual approval hữu ích trước production hoặc thay đổi có rủi ro cao. Approval notification có thể gửi SNS topic; approver cần xem release summary, change set, test results, artifact digest, risk/rollback plan và target environment. Approval không thay kiểm tra tự động; nó là decision gate có audit.

### 10.4. Execution mode và concurrent releases

CodePipeline V2 có execution modes như SUPERSEDED, QUEUED và PARALLEL. Chọn mode theo cách release cần được xử lý:

- **SUPERSEDED:** execution mới có thể thay thế execution cũ đang chờ/đang chạy ở các điều kiện được hỗ trợ.
- **QUEUED:** executions được xử lý theo hàng đợi để tránh chạy đồng thời trên cùng target.
- **PARALLEL:** nhiều executions có thể chạy song song; chỉ dùng khi deployments không tranh chấp target/state.

Nếu nhiều release cùng cập nhật một ECS service, CloudFormation stack hoặc database schema, parallel deployments có thể gây race conditions. Dùng queued/superseded phù hợp hoặc deployment lock/serialization ở cấp hệ thống.

## 11. IAM roles và bảo mật pipeline

Pipeline có nhiều principals. Không dùng một role có toàn quyền cho mọi stage.

~~~mermaid
flowchart TD
    DEV["Developer / Git provider"] --> CONN["CodeConnections"]
    CONN --> CP["CodePipeline service role"]
    CP --> CB["CodeBuild service role"]
    CP --> DEPLOY["Deployment action role"]
    DEPLOY --> CFN["CloudFormation service role"]
    CFN --> RES["AWS resources"]
    CB --> ECR["ECR repository"]
    CB --> S3["Artifact bucket"]
    CP --> KMS["KMS key"]
    DEPLOY --> TARGET["Cross-account target role"]
~~~

### 11.1. Tách các vai trò

| Role | Quyền điển hình |
|---|---|
| CodePipeline service role | Đọc source connection, gọi action providers, đọc/ghi artifacts, dùng KMS |
| CodeBuild service role | Logs, artifact access, dependency read, ECR push và test resources cần thiết |
| CloudFormation service role | Tạo/update resources theo template |
| CodeDeploy service role | Điều phối deployment vào compute target |
| Cross-account deploy role | Nhận deployment từ pipeline account, thao tác trong target account |
| Application runtime role | Quyền nghiệp vụ khi ứng dụng chạy |

### 11.2. Least privilege và iam:PassRole

CodePipeline/CodeBuild/CloudFormation có thể cần iam:PassRole để gắn role vào resource hoặc service. Scope theo role ARN cụ thể và điều kiện service khi hỗ trợ. Không cấp iam:PassRole trên wildcard nếu pipeline chỉ triển khai một workload.

### 11.3. Cross-account deployment

Mô hình nhiều account thường có pipeline account riêng và target accounts cho dev/staging/prod:

1. Pipeline role ở account nguồn có quyền assume target deployment role.
2. Target role trust policy chỉ cho phép source role cụ thể.
3. Target role có quyền triển khai stack/service ở account đích.
4. CloudFormation service role ở target account tạo resource theo least privilege.
5. Artifact bucket/KMS key policy cho phép actions cross-account cần thiết.

Không chia sẻ access keys giữa accounts. Dùng STS AssumeRole temporary credentials và audit assumed-role sessions.

### 11.4. Artifact encryption cross-account

Với CodePipeline cross-account, target account cần đọc artifacts và decrypt KMS key phù hợp. Kiểm tra cả:

- S3 bucket policy cho principal/account đích.
- KMS key policy/grants cho encrypt/decrypt/generate data key.
- Pipeline role và target action role permissions.
- Artifact store của Region nơi action chạy.

S3 object có SSE-KMS nhưng KMS key policy không cho account đích decrypt sẽ làm action fail dù bucket policy đã Allow.

### 11.5. Source connection và GitHub OIDC

CodeConnections và GitHub Actions OIDC là hai cơ chế kết nối/ủy quyền khác nhau. Với GitHub Actions, AWS role trust policy có thể giới hạn repository, branch hoặc environment qua token claims. Không cho phép mọi repository trong organization assume production role.

### 11.6. Secrets trong CodeBuild

CodeBuild hỗ trợ lấy environment variable từ Parameter Store hoặc Secrets Manager theo cấu hình project/buildspec. Service role chỉ cần quyền đọc secret cụ thể. Không in secret, không lưu vào artifact, không đưa vào Docker build layer và không tái sử dụng build role làm runtime role.

## 12. Deploy hạ tầng bằng CloudFormation, CDK và SAM

Pipeline thường cần deploy cả application và infrastructure. Nên tách infrastructure deployment khỏi application rollout khi chúng có lifecycle/risk khác nhau, nhưng vẫn quản lý bằng cùng release metadata.

### 12.1. CloudFormation template validation

Một stage IaC có thể:

1. Kiểm tra YAML/JSON syntax.
2. Chạy cfn-lint hoặc validator tương ứng.
3. Chạy policy checks như CloudFormation Guard.
4. Package artifacts nếu template tham chiếu local assets.
5. Tạo CloudFormation change set.
6. Review resource actions/replacement và chờ approval.
7. Execute change set.
8. Chờ stack terminal status và verify outputs.

Không deploy trực tiếp template production nếu policy yêu cầu change set review. Change set preview không đảm bảo resource operation thành công; pipeline vẫn phải monitor events và rollback.

### 12.2. CloudFormation deploy action

CodePipeline có CloudFormation action providers hỗ trợ các operation như create/update stack, create/execute change set theo action configuration. Khi dùng change set:

- Một action tạo change set.
- Có thể chèn manual approval/review stage.
- Action tiếp theo execute change set đã tạo.
- Các role, capabilities, parameters và artifact paths phải khớp template.

Kiểm tra action provider/version/configuration đang dùng; tránh giả định mọi loại CloudFormation action tự động chờ manual approval hoặc tự rollback application data.

### 12.3. AWS CDK

AWS CDK cho phép định nghĩa hạ tầng bằng ngôn ngữ lập trình. Pipeline có thể chạy:

~~~bash
npm ci
npm test
npx cdk synth
npx cdk diff
npx cdk deploy OrdersProductionStack --require-approval broadening
~~~

Đây là ví dụ CLI; CDK app có thể dùng TypeScript, Python, Java, C# hoặc Go theo hỗ trợ. Với production, tách synth/diff khỏi deploy, lưu synthesized templates làm artifacts và review IAM/security changes. CDK bootstrap resources và deployment roles phải được cấu hình trước cho account/Region.

### 12.4. AWS SAM cho serverless

SAM build tạo deployment artifacts; package/deploy sử dụng CloudFormation để quản lý resources:

~~~bash
sam validate --lint
sam build
sam package --s3-bucket orders-sam-artifacts-prod --output-template-file packaged.yaml
aws cloudformation create-change-set \
  --stack-name orders-api-prod \
  --change-set-name release-2026-11-20 \
  --change-set-type UPDATE \
  --template-body file://packaged.yaml \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --region ap-southeast-1
~~~

Capabilities phụ thuộc template; không thêm CAPABILITY_NAMED_IAM hoặc CAPABILITY_AUTO_EXPAND một cách máy móc. SAM template có thể tạo Lambda, API Gateway, queues, policies và event source mappings; review toàn bộ expanded CloudFormation changes.

### 12.5. IaC state và drift

CloudFormation là nguồn desired state của stack. Không để pipeline và kỹ sư sửa cùng một resource theo hai cơ chế không đồng bộ. Nếu có emergency manual change, ghi nhận và reconcile template/drift trước release tiếp theo.

## 13. Deploy ứng dụng lên Amazon ECS

ECS deployment cần cập nhật task definition revision và ECS service. Pipeline thường:

1. Build JAR/container image.
2. Push image vào ECR và lấy image digest.
3. Render task definition mới với image URI/digest.
4. Deploy task definition revision tới ECS service.
5. Chờ service ổn định và health checks pass.
6. Chạy smoke tests và monitor metrics.

### 13.1. Rolling deployment

ECS rolling update thay thế tasks theo deployment configuration, ví dụ minimum healthy percent và maximum percent. Đây là lựa chọn đơn giản, phù hợp service stateless và backward-compatible. Cần cấu hình health checks, grace period, capacity và deployment circuit breaker.

ECS deployment circuit breaker có thể phát hiện deployment không đạt trạng thái ổn định; khi bật rollback, ECS có thể quay lại deployment trước đó. Đây là cơ chế của ECS service deployment, khác với CloudFormation stack rollback.

### 13.2. Blue/green deployment với CodeDeploy

ECS blue/green sử dụng hai target groups và listener routing qua load balancer:

- Blue là task set hiện tại.
- Green là task set mới.
- CodeDeploy tạo green task set, chờ test/traffic shifting và chuyển listener traffic theo deployment configuration.
- Nếu alarm hoặc validation thất bại, CodeDeploy có thể rollback traffic về blue theo cấu hình.

Ví dụ AppSpec ECS (fragment):

~~~yaml
version: 0.0
Resources:
  - TargetService:
      Type: AWS::ECS::Service
      Properties:
        TaskDefinition: <TASK_DEFINITION>
        LoadBalancerInfo:
          ContainerName: orders-api
          ContainerPort: 8080
~~~

AppSpec này chỉ là fragment; deployment thực tế cần task definition artifact, AppSpec artifact, ECS cluster/service, target groups, listener, CodeDeploy application/deployment group và service role. Cấu hình test listener và hooks khi cần.

### 13.3. Database migrations phải backward-compatible

Trong blue/green hoặc rolling deployment, phiên bản cũ và mới có thể chạy đồng thời. Schema migration nên theo mô hình expand/contract:

1. Add schema mới mà phiên bản cũ vẫn chạy được.
2. Deploy application hỗ trợ cả schema cũ/mới.
3. Migrate/backfill data và xác minh.
4. Chuyển traffic hoàn toàn sang phiên bản mới.
5. Chỉ loại bỏ schema cũ trong release sau khi không còn consumer cũ.

Rollback application không tự rollback destructive database migration. Dùng migration scripts có version, backup và compensation plan.

## 14. Deploy lên AWS Lambda

Lambda deployment cần quản lý code package/image, function configuration, versions và aliases. Không cập nhật production alias bằng một lệnh không kiểm soát nếu cần traffic shifting/rollback.

### 14.1. Version và alias

Lambda version là snapshot immutable của function code/configuration được publish. Alias là pointer có thể trỏ tới version và có thể cấu hình weighted routing giữa hai versions. Production integration nên gọi alias thay vì gọi **$LATEST** trực tiếp.

### 14.2. CodeDeploy traffic shifting

Lambda có thể dùng CodeDeploy để dịch traffic từ version cũ sang version mới theo:

- **Canary:** chuyển một phần nhỏ traffic trước, chờ khoảng thời gian, rồi chuyển phần còn lại.
- **Linear:** chuyển traffic theo các bước phần trăm đều nhau.
- **All-at-once:** chuyển toàn bộ traffic ngay.

Chọn deployment configuration theo latency, cold start, blast radius và khả năng quan sát. Có thể gắn CloudWatch alarms và pre/post traffic hooks để kiểm tra health.

### 14.3. SAM deployment preferences

Ví dụ:

~~~yaml
Resources:
  OrdersFunction:
    Type: AWS::Serverless::Function
    Properties:
      Handler: com.example.orders.Handler::handleRequest
      Runtime: java21
      CodeUri: target/orders-function.jar
      AutoPublishAlias: live
      DeploymentPreference:
        Type: Canary10Percent10Minutes
        Alarms:
          - !Ref OrdersApiErrorsAlarm
        Hooks:
          PreTraffic: !Ref PreTrafficValidation
          PostTraffic: !Ref PostTrafficValidation
~~~

Đây là fragment SAM; function, alarm và hook resources cần được định nghĩa đầy đủ. Deployment preference hỗ trợ CodeDeploy traffic shifting; chọn runtime/version được Lambda hỗ trợ và kiểm tra Java packaging model.

### 14.4. Rollback Lambda

Nếu alarm chuyển ALARM hoặc hook thất bại, CodeDeploy có thể dừng deployment và chuyển alias traffic về version trước theo deployment configuration. Kiểm tra cả function code, environment variables, IAM role, event source mappings, reserved concurrency và API integrations. Alias rollback không khôi phục dữ liệu hoặc side effects đã xảy ra trong thời gian canary.

## 15. Deploy lên Amazon EKS

EKS deployment có thể dùng CodePipeline/CodeBuild để build image, push ECR và cập nhật Kubernetes manifests/Helm chart. Một cách phổ biến là **GitOps**: pipeline cập nhật image digest trong GitOps repository, Argo CD/Flux đồng bộ desired state vào cluster.

### 15.1. Direct deploy và GitOps

| Cách | Luồng | Phù hợp khi |
|---|---|---|
| Direct deploy | CodeBuild assume deploy role, chạy Helm/kubectl | Team có pipeline đơn giản, quyền deploy được kiểm soát |
| GitOps | Pipeline commit manifest/chart; controller pull và reconcile | Cần audit desired state trong Git và continuous reconciliation |

GitOps không loại bỏ CI. CI vẫn build/test/scan artifact; CD controller triển khai desired state đã được phê duyệt.

### 15.2. Image digest và rollout

Manifest production nên pin image digest, không chỉ tag mutable:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: orders-api
          image: 444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api@sha256:REPLACE_WITH_DIGEST
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
~~~

Digest là placeholder; pipeline cần thay bằng digest đã build/scan. Readiness/liveness probes phải khớp endpoints và security configuration thực tế của ứng dụng.

### 15.3. Rollout status và rollback

Các lệnh thường dùng:

~~~bash
kubectl rollout status deployment/orders-api -n production --timeout=5m
kubectl rollout history deployment/orders-api -n production
kubectl rollout undo deployment/orders-api -n production
~~~

Rollback Deployment đưa Kubernetes về revision trước trong rollout history nếu revision còn tồn tại. Nó không rollback CloudFormation resources, database schema hoặc external messages. Với GitOps, nên revert desired state trong Git thay vì sửa cluster thủ công; controller có thể ghi đè thay đổi ngoài band.

### 15.4. Progressive delivery trên EKS

RollingUpdate là mặc định của Kubernetes Deployment. Canary/blue-green có thể triển khai qua service mesh, ingress controller hoặc progressive delivery controllers như Argo Rollouts/Flagger theo kiến trúc. Cần metrics analysis, automated promotion/abort và traffic routing rõ ràng; chỉ tăng replicas không tạo canary.

## 16. Chiến lược release và traffic shifting

Không có một deployment strategy phù hợp cho mọi ứng dụng. Chọn chiến lược theo availability, latency, state compatibility, capacity, cost và rollback time.

| Strategy | Cách hoạt động | Ưu điểm | Rủi ro/điều kiện |
|---|---|---|---|
| **In-place** | Cập nhật trực tiếp instances/tasks/functions | Đơn giản, ít tài nguyên tạm | Downtime/interruption có thể xảy ra |
| **Rolling** | Thay từng nhóm instances/tasks | Không cần full duplicate environment | Old/new versions chạy đồng thời |
| **Blue/green** | Tạo environment mới, chuyển traffic | Cutover/rollback nhanh qua traffic routing | Cần capacity gấp đôi và kiểm soát data compatibility |
| **Canary** | Chuyển một phần traffic, quan sát rồi tăng | Giới hạn blast radius | Cần metrics và sample traffic đủ lớn |
| **Linear** | Chuyển traffic theo các bước | Quan sát tiến triển theo từng bước | Thời gian release dài hơn |
| **All-at-once** | Chuyển toàn bộ traffic ngay | Nhanh, ít thời gian song song | Blast radius lớn nếu lỗi |

### 16.1. Blue/green không tự giải quyết database compatibility

Hai application versions có thể đồng thời kết nối cùng database. Schema phải tương thích ngược và migration không được xóa column/index mà version cũ vẫn dùng. Nếu migration không backward-compatible, traffic rollback có thể đưa application cũ trở lại nhưng database đã đổi khiến app lỗi.

### 16.2. Canary cần đủ traffic và thời gian

Nếu chỉ có 10 requests trong canary window, không thể kết luận error rate 0% chứng minh release an toàn. Chọn sample size/time window phù hợp với traffic, latency SLO và error budget. Theo dõi cả business metrics như order completion, payment failure, queue age và consumer lag.

### 16.3. Feature flags bổ sung cho deployment strategy

Deploy code và bật feature là hai quyết định có thể tách nhau. Feature flag giúp release code tắt tính năng mới, bật cho internal users/percentage cohorts, rồi mở rộng sau khi metrics ổn định. Flag cần owner, expiry và cleanup plan; flag lâu ngày có thể tạo nhiều nhánh logic khó kiểm thử.

## 17. Automated rollback và deployment health

Rollback phải được thiết kế trước release, không đợi có incident mới nghĩ cách quay lại.

### 17.1. Các tín hiệu rollback

| Signal | Ví dụ threshold | Hành động có thể cấu hình |
|---|---|---|
| Application errors | 5xx tăng vượt baseline/SLO | Abort canary, CodeDeploy rollback |
| Latency | p95/p99 vượt SLO liên tục | Dừng traffic shift |
| ECS health | Desired tasks không đạt healthy | ECS circuit breaker rollback |
| Lambda errors/throttles | Error/throttle rate tăng sau alias shift | CodeDeploy rollback alias |
| EKS rollout | Readiness probe fail, unavailable replicas | Pause/undo rollout hoặc Git revert |
| Business KPI | Payment/order completion giảm | Stop release, feature flag off, compensate |
| IaC stack | CloudFormation resource update failed | CloudFormation rollback theo operation |

Threshold phải dựa trên baseline và traffic; không sao chép một con số chung cho mọi service. Alarm quá nhạy gây rollback giả; alarm quá chậm làm blast radius tăng.

### 17.2. CloudWatch alarms và CodeDeploy

CodeDeploy deployment group có thể liên kết CloudWatch alarms. Khi alarm chuyển ALARM trong quá trình deployment, CodeDeploy có thể dừng/rollback deployment tùy cấu hình. Cần:

- Alarm có metrics và dimensions đúng service/version/target group.
- Alarm được deploy trước hoặc cùng dependency order với deployment group.
- Role và service integration có quyền theo dõi alarms.
- Alarm state/INSUFFICIENT_DATA behavior được hiểu rõ.
- Deployment group cấu hình auto rollback cho deployment failure/alarm khi cần.

### 17.3. ECS deployment circuit breaker

Với ECS rolling deployments, cấu hình deployment circuit breaker và rollback. ECS đánh giá deployment có đạt steady state không dựa trên task launch/health progression. Nó không thay application-level smoke tests hoặc business metrics; có thể deployment đạt healthy tasks nhưng request logic vẫn sai.

### 17.4. CloudFormation rollback

CloudFormation rollback bảo vệ stack update, không phải toàn bộ release. Nếu pipeline deploy app image và CloudFormation hạ tầng riêng:

- Stack update rollback có thể không rollback image/service deployment đã chạy ở action khác.
- CodeDeploy rollback có thể đổi traffic về app version trước nhưng không restore DB data.
- Cần pipeline orchestration để dừng các stage tiếp theo, ghi nhận trạng thái và gọi recovery action phù hợp.

### 17.5. Rollback và roll-forward

Rollback phù hợp khi phiên bản cũ còn tương thích với data/schema/configuration. Roll-forward hotfix phù hợp khi rollback không an toàn hoặc data migration đã irreversible. Quyết định phải dựa trên incident runbook, không chỉ dựa trên việc action nào dễ chạy hơn.

## 18. Multi-environment và cross-account release

Pipeline thường promote cùng một artifact qua dev → test → staging → production. **Build một lần, promote nhiều lần** giúp bảo đảm binary/image đã test chính là binary/image được deploy production.

### 18.1. Tách configuration khỏi artifact

Artifact không chứa:

- Production database passwords.
- AWS access keys/session tokens.
- Environment-specific secret values.
- Hard-coded account IDs, endpoints hoặc bucket names nếu chúng phải thay theo môi trường.

Runtime config được cấp qua environment variables, Parameter Store, Secrets Manager, task/pod/Lambda configuration và IAM roles.

### 18.2. Cross-account deployment model

~~~mermaid
flowchart TD
    SRC["Source repository"] --> PIPE["Pipeline account"]
    PIPE --> BUILD["Build once"]
    BUILD --> ART["Encrypted artifact / ECR image"]
    ART --> DEV["Dev account role"]
    DEV --> TEST["Integration tests"]
    TEST --> STAGE["Staging account role"]
    STAGE --> APPROVE["Approval"]
    APPROVE --> PROD["Production account role"]
    PROD --> VERIFY["Health / smoke / alarms"]
~~~

### 18.3. Cross-account roles

Mỗi target account có deploy role riêng. Trust policy giới hạn source pipeline role; permissions policy chỉ cho phép cập nhật stacks/services được phê duyệt. Pipeline account cần quyền assume role và artifact access; target role cần quyền đọc artifact/decrypt KMS key nếu action chạy trong target account.

Không để production deploy role có quyền thay đổi IAM trust policy tùy ý hoặc assume role sang các account khác không liên quan.

### 18.4. Cross-Region deployment

CodePipeline hỗ trợ artifact stores theo Region khi pipeline actions chạy ở nhiều Regions. Cần chỉ định artifact store cho từng Region và KMS key tương ứng. Cross-Region actions có thể phát sinh data transfer và encryption permissions; xác minh pipeline service role được quyền dùng keys ở các Regions.

Không chỉ đổi Region parameter rồi cho rằng resource đã được replicate. Với ECR, S3, KMS, database và secrets, phải cấu hình replication/backup/copy và verify destination resources.

### 18.5. Approval và separation of duties

Production approval nên do người/nhóm có trách nhiệm phát hành, khác với người tạo thay đổi khi policy yêu cầu. Approval summary nên hiển thị:

- Source commit, release version và artifact digest.
- Test/security scan results.
- IaC change set và replacement/deletion risks.
- Target account/Region/environment.
- Rollout strategy, alarm links và rollback plan.
- Ticket/change request và approver identity.

Approval không được dựa trên thông báo chung chung như “build xanh”. Người duyệt cần đủ thông tin để đánh giá đúng release.

## 19. Pipeline example: thiết kế CodePipeline cho ECS

Ví dụ logic pipeline cho một Spring Boot service:

~~~text
Source:
  Provider: CodeConnections
  Repository: orders-api
  Trigger: merge to main

Build:
  Provider: CodeBuild
  Commands: mvn clean verify
  Output: application JAR + test reports

Security:
  Provider: CodeBuild
  Checks: SCA + secret scan + IaC scan
  Gate: all required findings pass

Container:
  Provider: CodeBuild
  Commands: docker build + ECR push
  Output: image digest manifest

Deploy-Test:
  Provider: ECS deploy action
  Input: task definition + image digest

Verify-Test:
  Provider: CodeBuild
  Checks: smoke + API contract tests

Approval:
  Provider: Manual approval
  Evidence: reports + release manifest + rollback plan

Deploy-Prod:
  Provider: ECS rolling or CodeDeploy blue/green
  Input: same image digest used in test

Observe:
  Provider: CloudWatch alarms + smoke checks
  Result: accept release or rollback
~~~

Đây là blueprint, không phải file pipeline definition có thể deploy nguyên trạng. Tên action providers, artifact names, IAM role ARNs, task definition files và CodePipeline V1/V2 configuration phải được khai báo theo dự án.

### 19.1. Task definition template

Một task definition template có thể giữ placeholder cho image:

~~~json
{
  "family": "orders-api",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::444455556666:role/orders-api-execution-role",
  "taskRoleArn": "arn:aws:iam::444455556666:role/orders-api-task-role",
  "containerDefinitions": [
    {
      "name": "orders-api",
      "image": "REPLACE_WITH_ECR_IMAGE_DIGEST",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8080,
          "protocol": "tcp"
        }
      ]
    }
  ]
}
~~~

Pipeline render image URI bằng digest đã build, lưu task definition artifact và deploy. Không ghi runtime secrets vào task definition artifact; dùng Secrets Manager references hoặc application runtime secret retrieval.

### 19.2. CodeBuild deploy verification

Sau khi deploy test, một CodeBuild action có thể chạy smoke tests:

~~~bash
set -euo pipefail

for attempt in $(seq 1 30); do
  status="$(curl --silent --output /dev/null --write-out '%{http_code}' "$APP_BASE_URL/actuator/health/readiness" || true)"
  if [ "$status" = "200" ]; then
    echo "Readiness check passed"
    exit 0
  fi
  sleep 10
done

echo "Application did not become ready"
exit 1
~~~

Đây là ví dụ shell; APP_BASE_URL phải đến từ environment config đã được kiểm soát. Trong production pipeline, giới hạn retry/timeouts và không dùng readiness endpoint làm kiểm thử nghiệp vụ duy nhất.

## 20. Observability và audit pipeline

Một pipeline xanh không đủ để chứng minh release khỏe. Theo dõi cả **pipeline execution**, **deployment**, **application runtime** và **business outcome**.

### 20.1. Pipeline metrics

| Metric | Câu hỏi |
|---|---|
| Pipeline success/failure rate | Release có thường xuyên thất bại? |
| Stage/action duration | Stage nào tạo bottleneck? |
| Build queue time | CodeBuild capacity/concurrency có đủ? |
| Test failure rate | Regression nào thường xuất hiện? |
| Deployment duration | Release mất bao lâu để phục vụ traffic? |
| Rollback frequency | Quality gates có bỏ sót lỗi? |
| Lead time / deployment frequency | Tốc độ delivery thay đổi ra sao? |
| Change failure rate / MTTR | Release gây incident và phục hồi mất bao lâu? |

### 20.2. CloudWatch Logs

CodeBuild build logs có thể gửi tới CloudWatch Logs hoặc S3 theo cấu hình. Giữ retention phù hợp, kiểm soát quyền đọc và redact sensitive output. Không ghi toàn bộ environment variables hoặc build commands chứa secrets.

### 20.3. CloudTrail

CloudTrail giúp audit các API actions như tạo pipeline, update project, assume role, update stack/service và thay đổi IAM. Bật trail/organization trail theo yêu cầu; data events và retention có thể ảnh hưởng chi phí.

### 20.4. Deployment dashboard

Dashboard release có thể hiển thị:

- Pipeline execution ID và commit SHA.
- Build ID, test reports, scan findings.
- Artifact version/image digest.
- Target account/Region/cluster/service/stack.
- Deployment strategy và current traffic percentage.
- Alarm state, error rate, latency và healthy targets.
- Rollback action và final stack/service state.

### 20.5. Notifications

Có thể gửi thông báo qua SNS, EventBridge rules, Chatbot/Chat integrations hoặc hệ thống incident management. Notification nên gồm link execution/logs, release ID, failed action, error summary và owner; không chứa credentials, secret values hoặc payload khách hàng.

## 21. GitHub Actions OIDC và pipeline identity

Nếu dùng GitHub Actions làm CI/CD, không cần lưu AWS access key dài hạn trong GitHub secrets. GitHub có thể cấp OIDC token để workflow assume một IAM role có trust policy giới hạn repository/ref/environment.

### 21.1. Trust policy giới hạn repository và branch

Ví dụ trust policy cho workflow của repository orders-api, chỉ cho phép branch main:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GitHubActionsMainOnly",
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::444455556666:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:example-org/orders-api:ref:refs/heads/main"
        }
      }
    }
  ]
}
~~~

Thay account ID, organization và repository bằng giá trị thực. Nếu dùng GitHub Environment, subject claim có format khác; trust policy phải khớp chính xác token claims mà workflow phát hành. Không dùng wildcard quá rộng cho mọi branch/repository.

### 21.2. Workflow assume role

Ví dụ workflow:

~~~yaml
name: Build and deploy

on:
  push:
    branches: [main]

permissions:
  contents: read
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::444455556666:role/orders-api-ci-role
          aws-region: ap-southeast-1
      - name: Verify identity
        run: aws sts get-caller-identity
      - name: Build
        run: mvn -B clean verify
~~~

Đây là workflow fragment. Trong production, pin third-party actions theo full commit SHA hoặc cơ chế supply-chain policy của tổ chức, giới hạn permissions, tách deploy job/environment và không cho untrusted pull request code chạy trong job có quyền production.

### 21.3. Pull request từ fork

Không cấp OIDC production role cho workflow chạy code từ fork/untrusted pull requests. Pull request job nên chỉ chạy tests/static analysis với permissions tối thiểu; deployment credentials chỉ cấp sau merge hoặc protected environment approval.

### 21.4. GitHub OIDC và CodeConnections khác nhau

CodeConnections cho CodePipeline quyền truy cập source provider để lấy source revisions. GitHub OIDC cho workflow GitHub Actions assume AWS role. Chúng không thay thế nhau và có trust boundaries riêng.

## 22. Supply chain security và release provenance

Một pipeline an toàn phải chứng minh artifact đến từ source đã review, build environment đáng tin cậy và dependencies được kiểm soát.

### 22.1. SBOM và provenance

SBOM liệt kê components/dependencies trong artifact. Provenance ghi nhận source revision, builder, build steps và artifact digest. Lưu chúng cùng release metadata và liên kết với deployment.

### 22.2. Artifact signing

Có thể ký container image hoặc package bằng công cụ phù hợp như Notation/Cosign và tích hợp AWS Signer theo use case. Runtime/deployment admission policy có thể yêu cầu signature từ trusted identity trước khi cho phép image chạy. Signing chỉ có giá trị khi verification policy được thực thi ở deployment boundary.

### 22.3. Pin actions, dependencies và build images

- Pin GitHub Actions theo commit SHA khi dùng GitHub workflow.
- Dùng CodeBuild managed image version cụ thể hoặc custom image đã kiểm soát.
- Pin Maven/Gradle plugins và dependency versions.
- Pin Docker base images bằng digest.
- Quản lý package sources/allowlists trong CodeArtifact.
- Scan artifacts và tạo SBOM trước release.

### 22.4. Build isolation

Build untrusted pull request không nên chạy trong environment có quyền publish production images hoặc assume production roles. Tách projects/roles hoặc tách build phases; hạn chế privileged Docker mode và network egress khi không cần.

### 22.5. Artifact promotion

Không build lại ở mỗi environment. Promote cùng artifact digest qua dev/staging/prod; chỉ thay deployment configuration, secret references và runtime role. Nếu phải copy image giữa accounts/Regions, verify digest và signature sau khi copy.

## 23. Chi phí và hiệu quả vận hành

CI/CD có thể giảm thao tác thủ công và lỗi release, nhưng pipeline execution, build minutes, artifact storage, image scanning, logs và temporary deployment capacity đều có chi phí.

| Thành phần | Yếu tố chi phí | Cách kiểm soát |
|---|---|---|
| CodePipeline | Pipeline type, active pipeline/execution pricing theo mô hình hiện hành | Chọn V1/V2 theo triggers/concurrency cần thiết |
| CodeBuild | Compute type, build duration, concurrency, reserved capacity | Cache dependencies, right-size compute, parallelize hợp lý |
| S3 artifact store | Storage, requests, replication, data transfer | Lifecycle policies, retention và artifact cleanup |
| KMS | Key usage/API requests theo pricing hiện hành | Dùng key strategy phù hợp, tránh tạo key không cần |
| ECR | Image storage, scan features, data transfer | Lifecycle rules, remove untagged/obsolete images có kiểm soát |
| CodeArtifact | Package storage/requests/data transfer | Retention/cleanup và dependency caching |
| CloudWatch | Logs ingestion/storage/metrics/alarms | Retention, log levels, metric cardinality |
| Cross-Region/account | Artifact copy, replication, KMS operations | Chọn Regions và promotion model phù hợp |
| Blue/green | Hai environments cùng chạy tạm thời | Ước lượng capacity và monitoring window |
| Test environments | ECS/EKS/RDS resources để test | Ephemeral environments, schedule shutdown và cleanup |

### 23.1. Tối ưu CodeBuild

- Cache Maven/Gradle dependencies nhưng vẫn pin versions.
- Dùng compute size phù hợp với compile/test workload.
- Chạy tests độc lập song song khi không tranh chấp resources.
- Tránh build lại cùng image ở nhiều stages.
- Dùng test selection/path filters trong monorepo có dependency graph rõ.
- Dọn ephemeral resources sau integration tests.

### 23.2. Tối ưu artifact và image retention

Giữ release artifacts theo retention policy phục vụ rollback/audit. Xóa untagged images và build intermediates theo lifecycle rules, nhưng không xóa digest đang được ECS/EKS/Lambda release hoặc rollback plan tham chiếu. Giữ đủ image versions cho rollback window và compliance.

### 23.3. Đo DORA-style delivery metrics

Theo dõi deployment frequency, lead time for changes, change failure rate và time to restore service. Dùng metrics để cải thiện bottlenecks, không dùng để ép team tăng release count bằng cách giảm tests hoặc bỏ approvals cần thiết.

## 24. Troubleshooting pipeline và deployment

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Source action không lấy được code | Connection chưa authorized, role thiếu UseConnection, webhook/trigger sai | Connection status, pipeline role, source revision |
| CodeBuild không checkout source | Source artifact/input mapping sai, quyền artifact bucket thiếu | Action configuration, S3/KMS, build logs |
| Maven/Gradle build fail | JDK/toolchain mismatch, dependency repository lỗi, test fail | Build image/runtime, wrapper version, logs/reports |
| CodeBuild không push ECR | Role thiếu ECR upload actions, Region/repository URI sai | Caller identity, repository policy, ECR auth |
| Docker build fail | Privileged mode thiếu, daemon không khả dụng, build context sai | Project environment, Dockerfile, build logs |
| Image scan fail | Vulnerability threshold hoặc scan chưa hoàn tất | ECR scan status, finding severity, exception policy |
| Pipeline artifact decrypt denied | S3 bucket/KMS key policy thiếu cross-account permissions | Artifact store, KMS key policy/grants |
| CloudFormation action fail | Capabilities, template, service role, change set hoặc quota | Stack events, change set status reason |
| ECS deployment không steady state | Task crash, image pull, health check, capacity hoặc networking | ECS service events, stopped task reason, target health |
| ECS blue/green fail | Target group/listener/AppSpec/task definition sai | CodeDeploy deployment events, ALB target health |
| Lambda deployment fail | Alias/version, hook, permission hoặc alarm | CodeDeploy deployment, Lambda logs, alias routing |
| EKS rollout stuck | Image pull, readiness probe, insufficient capacity, RBAC | kubectl describe/events/logs, rollout status |
| OIDC AssumeRole denied | Trust policy sub/aud không khớp, workflow permissions thiếu | Token claims, role trust policy, id-token permission |
| Secret bị lộ trong logs | Echo env, shell tracing, build command | Dừng job, rotate secret, xử lý incident và audit logs |
| Rollback không phục hồi app | Database migration/side effect không reversible | App/data recovery plan, forward fix, compensation |
| Pipeline artifact mismatch | Tag bị overwrite, artifact key collision, parallel executions | Release manifest, digest, action input/output mapping |

### 24.1. Source/connection failure

Kiểm tra connection state, repository authorization, branch filters, trigger configuration, IAM permission trên connection ARN và event delivery. Nếu pipeline không trigger, chạy manual execution để phân biệt source trigger với action configuration.

### 24.2. Build failure

Đọc CodeBuild phase status và log dòng lỗi đầu tiên có ý nghĩa. Xác minh runtime image, JDK/Maven/Gradle versions, dependency repositories, network egress, environment variables và cache. Thử build cùng commit trong môi trường tương đương trước khi thay buildspec production.

### 24.3. Deployment failure

Không chỉ xem CodePipeline stage đỏ. Mở provider cụ thể:

- CloudFormation: stack events và resource status reason.
- ECS: service events, stopped task reasons, target group health.
- CodeDeploy: deployment lifecycle events và hook logs.
- Lambda: function logs, version/alias configuration, concurrency.
- EKS: Pod events, image pull status, readiness/liveness probes và rollout history.

### 24.4. Rollback failure

Rollback có thể fail do database migration, deleted resources, service quotas, permissions hoặc custom hooks. Dừng executions mới, xác định deployment system sở hữu rollback (ECS, CodeDeploy, CloudFormation, Kubernetes) và chạy đúng recovery runbook. Không gọi đồng thời nhiều rollback mechanisms lên cùng target.

### 24.5. Pipeline artifact mismatch

Nếu staging chạy image digest A nhưng production chạy digest B:

1. So sánh release manifest và ECR digest.
2. Kiểm tra artifact input/output mapping giữa actions.
3. Kiểm tra tag có bị overwrite không.
4. Kiểm tra pipeline executions chạy song song và artifact key collisions.
5. Chỉ promote digest đã test; không build lại trong production stage.

## 25. Runbook phát hành production

### Giai đoạn A — Trước release

1. Xác nhận source commit/tag và code review.
2. Xác nhận pipeline đang chạy đúng branch/tag và target account/Region.
3. Build, unit tests, integration tests, security scans và IaC checks pass.
4. Tạo JAR/image, SBOM, provenance và release manifest.
5. Ghi image digest; không dựa vào latest tag.
6. Kiểm tra artifact encryption, IAM roles và deployment permissions.
7. Xác nhận backup/data migration/rollback plan.
8. Xác nhận CloudWatch alarms, dashboard và on-call owner.

### Giai đoạn B — Test/staging

1. Deploy cùng artifact digest lên test/staging.
2. Chạy smoke, contract, acceptance và security checks.
3. Xác nhận caller identity/runtime role và secrets/config đúng môi trường.
4. Chạy migration/compatibility checks.
5. Đo latency/error/business metrics và kiểm tra autoscaling.
6. Lưu test evidence và release notes.

### Giai đoạn C — Approval và production

1. Review release summary, artifact digest, change set, scan reports và risk.
2. Approver xác nhận target environment, deployment strategy và rollback plan.
3. Execute production deployment với role riêng.
4. Theo dõi traffic shift, healthy targets, alarms và business KPIs.
5. Chạy smoke tests sau deployment.
6. Nếu health pass trong monitoring window, đánh dấu release complete.

### Giai đoạn D — Rollback hoặc close

1. Nếu gate fail, dừng promotion và kích hoạt rollback mechanism tương ứng.
2. Xác nhận application traffic đã quay lại version ổn định.
3. Kiểm tra database/data side effects và chạy compensation/forward fix nếu cần.
4. Xác minh ECS/CodeDeploy/Lambda/EKS/CloudFormation state cuối cùng.
5. Lưu pipeline execution, deployment IDs, logs, alarms và decision record.
6. Tạo incident/postmortem và remediation tasks.

~~~mermaid
flowchart TD
    A["Source revision approved"] --> B["Build once + test + scan"]
    B --> C["Publish immutable artifact + SBOM"]
    C --> D["Deploy test / staging"]
    D --> E["Smoke / contract / acceptance"]
    E --> F{"Approval & gates pass?"}
    F -->|"No"| STOP["Stop release / fix"]
    F -->|"Yes"| G["Production rollout"]
    G --> H["Observe alarms, SLO and business KPIs"]
    H --> I{"Healthy during window?"}
    I -->|"Yes"| J["Release complete + audit"]
    I -->|"No"| K["Rollback / traffic shift / recovery"]
    K --> L["Verify service and data state"]
~~~

## 26. Bài tập tình huống

### Tình huống A — Build xanh nhưng production lỗi

Pipeline compile và unit tests pass, nhưng production trả 500 sau deploy. Integration tests chưa chạy và cấu hình production khác staging.

**Câu hỏi:** thiếu những gates nào?

**Gợi ý:** thêm integration/contract tests, smoke tests sau deploy, config validation và canary/alarms. So sánh runtime role, secrets, endpoints và database schema giữa staging/prod; không coi unit tests pass là bằng chứng release production-safe.

### Tình huống B — Image tag latest bị ghi đè

Hai pipeline executions chạy song song và cùng push tag latest. Staging test image của build A nhưng production deploy image build B.

**Câu hỏi:** bảo đảm promotion đúng artifact bằng cách nào?

**Gợi ý:** tag theo commit/build ID, bật ECR tag immutability, lưu image digest trong manifest và deploy digest. Serialize deployments nếu hai executions cập nhật cùng target.

### Tình huống C — CodeBuild không push được ECR

Build tests pass nhưng docker push trả AccessDeniedException. Team cấp AdministratorAccess cho CodeBuild role để unblock.

**Câu hỏi:** quyền tối thiểu cần xem là gì?

**Gợi ý:** kiểm tra ECR authorization token và upload layer/image actions trên repository, Region và repository policy. Cấp đúng quyền cho CodeBuild role; không cấp quyền production deployment nếu build chỉ cần push image.

### Tình huống D — Docker build thất bại trong CodeBuild

Buildspec gọi docker build nhưng lỗi không kết nối được Docker daemon.

**Câu hỏi:** cần xác minh cấu hình nào?

**Gợi ý:** project environment có Docker capability/privileged mode khi build daemon-based container hay không, compute image/architecture và build context. Cân nhắc builder khác nếu không muốn privileged mode.

### Tình huống E — GitHub workflow assume production role bị từ chối

Workflow chạy trên branch release/1.2 nhưng trust policy chỉ cho phép refs/heads/main.

**Câu hỏi:** có nên đổi sub condition thành wildcard mọi branch?

**Gợi ý:** không. Cập nhật trust policy có chủ đích cho protected release branch hoặc GitHub Environment claim, giới hạn repository/ref và giữ approval gate. Kiểm tra aud/sub token claims.

### Tình huống F — Cross-account artifact decrypt denied

Pipeline account ghi artifact vào S3 SSE-KMS. Target account assume deployment role nhưng action không decrypt được artifact.

**Câu hỏi:** cần kiểm tra cả hai lớp nào?

**Gợi ý:** S3 bucket policy và KMS key policy/grants, cùng permissions của pipeline/action roles. Role target phải được phép đọc object và decrypt đúng key; artifact store/Region phải khớp action.

### Tình huống G — ECS deployment rollback dù task healthy

Tasks mới healthy nhưng API error rate tăng vì application query schema mới không tương thích.

**Câu hỏi:** health check nào bị thiếu?

**Gợi ý:** smoke/contract tests và business metrics, không chỉ container health. Áp dụng expand/contract migration, canary traffic và CloudWatch alarms để phát hiện lỗi nghiệp vụ trước full rollout.

### Tình huống H — Lambda canary fail nhưng database đã đổi

CodeDeploy chuyển 10% traffic sang version mới; migration đổi schema không tương thích, alarm kích hoạt và alias quay về version cũ.

**Câu hỏi:** vì sao rollback vẫn có thể làm app cũ lỗi?

**Gợi ý:** alias rollback không đảo ngược DB migration. Dùng migration backward-compatible, backup và compensation; tách schema changes khỏi traffic switch.

### Tình huống I — EKS GitOps liên tục revert hotfix thủ công

Kỹ sư sửa image tag trực tiếp bằng kubectl nhưng Argo CD đưa manifest về version trong Git.

**Câu hỏi:** nên phát hành hotfix thế nào?

**Gợi ý:** cập nhật desired state trong GitOps repository, review/merge hotfix commit và để controller reconcile. Ghi nhận emergency manual change rồi đồng bộ Git để tránh drift.

### Tình huống J — CodePipeline chạy hai deployment cùng lúc

Hai commits liên tiếp khởi chạy parallel executions, cùng cập nhật một CloudFormation stack và ECS service.

**Câu hỏi:** chọn execution mode nào?

**Gợi ý:** QUEUED nếu cần xử lý tuần tự; SUPERSEDED nếu chỉ release mới nhất còn ý nghĩa và action semantics cho phép; PARALLEL chỉ khi targets độc lập. Cần deployment lock cho shared database/schema.

### Tình huống K — Security scan fail do CVE đã có exception

Pipeline chặn release vì dependency scan phát hiện CVE đã được security team chấp thuận tạm thời.

**Câu hỏi:** có nên tắt dependency scan?

**Gợi ý:** không. Dùng exception record có owner, rationale, expiry, compensating controls và ticket remediation. Gate chỉ bypass đúng finding/version đã duyệt.

### Tình huống L — Rollback CodeDeploy thành công nhưng pipeline vẫn xanh

CodeDeploy deployment rollback về version cũ, nhưng pipeline action không kiểm tra trạng thái cuối và stage sau vẫn chạy.

**Câu hỏi:** cần cải thiện orchestration ra sao?

**Gợi ý:** coi rollback là deployment failure, kiểm tra final deployment status, dừng promotion stages và phát thông báo incident. Pipeline phải xác nhận trạng thái runtime sau rollback.

### Tình huống M — Build job của pull request có thể đọc production secrets

Untrusted fork pull request chạy CodeBuild project dùng service role có GetSecretValue trên production secret.

**Câu hỏi:** giới hạn blast radius bằng cách nào?

**Gợi ý:** tách PR build role/project không có production permissions, tách deploy job sau merge/protected approval và giới hạn network egress. Không đưa untrusted code vào build environment có secret.

### Tình huống N — ECR lifecycle xóa image cần rollback

Repository lifecycle policy xóa images cũ sau vài ngày. Incident yêu cầu quay về digest của release trước nhưng image đã bị xóa.

**Câu hỏi:** cần thay đổi retention ra sao?

**Gợi ý:** giữ đủ release images theo rollback/compliance window, bảo vệ tags/digests đang được deploy và kiểm thử restore/copy. Lifecycle policy phải hiểu tag patterns và untagged image behavior.

### Tình huống O — Pipeline update CloudFormation thành công nhưng app không ready

CloudFormation stack UPDATE_COMPLETE nhưng ECS tasks không healthy do container startup failure.

**Câu hỏi:** vì sao stack status chưa đủ?

**Gợi ý:** IaC success chỉ chứng minh resource operations hoàn tất. Cần deployment stage, ECS service stabilization, target health, smoke tests và application metrics; pipeline không nên đánh dấu release complete khi runtime chưa healthy.

## 27. Checklist production

- [ ] Pipeline có source trigger/branch/tag strategy rõ ràng và pull request validation riêng.
- [ ] Mọi release truy ngược được source commit, build ID, test reports và deployment ID.
- [ ] Build environment, JDK/toolchain, dependencies và base images được pin.
- [ ] Unit, integration, contract và smoke tests phù hợp risk.
- [ ] Security gates gồm SAST/SCA/secret/IaC/container scan theo policy.
- [ ] Finding exceptions có owner, rationale, expiry và remediation.
- [ ] Buildspec trả exit code chính xác và xuất test reports.
- [ ] Docker build chỉ bật privileged mode khi cần và có isolation phù hợp.
- [ ] ECR tag immutability được bật cho release repository; production deploy dùng image digest.
- [ ] SBOM/provenance/release manifest được tạo và lưu cùng artifact.
- [ ] CodePipeline artifact store có S3/KMS encryption, bucket policy, retention và cross-Region stores.
- [ ] CodeArtifact repositories và package permissions được kiểm soát.
- [ ] CodePipeline, CodeBuild, CloudFormation, CodeDeploy và runtime roles được tách biệt.
- [ ] OIDC/CodeConnections trust được giới hạn repository, branch, environment và connection ARN.
- [ ] Không dùng access keys dài hạn trong pipeline, Docker image hoặc source.
- [ ] Cross-account deploy roles, artifact bucket policies và KMS key policies đã được kiểm tra.
- [ ] Production approval hiển thị digest, test results, change set, target account/Region và rollback plan.
- [ ] ECS deployment có health checks/circuit breaker hoặc CodeDeploy blue/green phù hợp.
- [ ] Lambda production dùng published versions/aliases và traffic shifting khi cần.
- [ ] EKS rollout có readiness/liveness, resource capacity và GitOps desired state nếu áp dụng.
- [ ] Database migration backward-compatible; rollback không phụ thuộc destructive reverse migration.
- [ ] CloudWatch alarms, deployment hooks, smoke tests và business KPIs được cấu hình.
- [ ] Pipeline execution mode tránh concurrent updates cùng target/state.
- [ ] Rollback mechanism được thử nghiệm cho đúng deployment provider.
- [ ] Application/data side effects có idempotency/compensation plan.
- [ ] Logs/notifications không chứa credentials, tokens, secret values hoặc customer payloads.
- [ ] CloudTrail, CloudWatch dashboards, retention và incident notifications có owner.
- [ ] ECR/S3/CodeArtifact/logs/test environments có lifecycle/retention policy.
- [ ] Rollback images/artifacts được giữ đủ lâu và có thể truy cập.
- [ ] Đã diễn tập pipeline failure, deployment failure, alarm rollback, cross-account access và recovery.

## 28. Ghi nhớ

**CI/CD là quy trình có thể truy vết từ source commit đến runtime release.** CodePipeline điều phối stages/actions; CodeBuild build và test; S3 lưu pipeline artifacts; ECR lưu container images; CodeDeploy/ECS/Lambda/EKS triển khai; CloudFormation/CDK/SAM quản lý hạ tầng; CloudWatch và CloudTrail cung cấp signals/audit.

Hãy **build một lần, promote cùng artifact bất biến** qua dev/staging/prod. Dùng commit SHA và image digest thay latest tag; lưu SBOM/provenance; tách pipeline, build, deployment, CloudFormation và runtime roles; dùng CodeConnections hoặc OIDC với trust policy giới hạn; mã hóa artifacts bằng KMS và không để secrets trong source, build logs hoặc image.

Chọn rolling, blue/green, canary hoặc linear theo availability và data compatibility. Rollback cần metrics, alarms, health checks và runbook riêng cho ECS, CodeDeploy, Lambda, EKS và CloudFormation. Nhớ rằng rollback traffic/code không tự khôi phục database data hoặc external side effects. Cuối cùng, kiểm soát execution concurrency, artifact retention, logs, build minutes và temporary capacity để pipeline vừa tin cậy vừa có chi phí hợp lý.

### Tài liệu AWS chính thức để đối chiếu

- [AWS CodePipeline User Guide](https://docs.aws.amazon.com/codepipeline/latest/userguide/welcome.html) — stages, actions, artifacts và execution.
- [CodePipeline pipeline types](https://docs.aws.amazon.com/codepipeline/latest/userguide/pipeline-types.html) — V1/V2 capabilities.
- [CodePipeline cross-Region actions](https://docs.aws.amazon.com/codepipeline/latest/userguide/actions-create-cross-region.html) — artifact stores và cross-Region actions.
- [AWS CodeBuild User Guide](https://docs.aws.amazon.com/codebuild/latest/userguide/welcome.html) — build projects, environments và reports.
- [Buildspec reference](https://docs.aws.amazon.com/codebuild/latest/userguide/build-spec-ref.html) — phases, artifacts, reports và cache.
- [CodeBuild environment variables](https://docs.aws.amazon.com/codebuild/latest/userguide/build-env-ref-env-vars.html) — source/build metadata.
- [Amazon ECR image scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning.html) — scan configuration và findings.
- [Amazon ECR image tag mutability](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-tag-mutability.html) — immutable tags.
- [AWS CodeDeploy User Guide](https://docs.aws.amazon.com/codedeploy/latest/userguide/welcome.html) — deployment groups, hooks và rollback.
- [ECS blue/green deployments with CodeDeploy](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-bluegreen.html) — target groups và traffic shifting.
- [ECS deployment circuit breaker](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-circuit-breaker.html) — detect failure và rollback.
- [Lambda traffic shifting with CodeDeploy](https://docs.aws.amazon.com/lambda/latest/dg/deploying-lambda.html) — canary/linear deployments.
- [AWS SAM gradual deployments](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/automating-updates-to-serverless-apps.html) — deployment preferences và alarms.
- [Amazon EKS application deployments](https://docs.aws.amazon.com/eks/latest/userguide/deploying.html) — Kubernetes deployment practices.
- [AWS IAM OIDC federation](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html) — web identity trust.
- [GitHub Actions OIDC in AWS](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html) — trust policy và role assumption.
- [AWS CodeConnections User Guide](https://docs.aws.amazon.com/dtconsole/latest/userguide/welcome-connections.html) — source provider connections.
- [AWS CodeArtifact User Guide](https://docs.aws.amazon.com/codeartifact/latest/ug/welcome.html) — package repositories.
- [CloudFormation change sets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets.html) — preview và execute infrastructure changes.
- [AWS Well-Architected DevOps guidance](https://docs.aws.amazon.com/wellarchitected/latest/devops-guidance/welcome.html) — release engineering, deployment safety và operations.


