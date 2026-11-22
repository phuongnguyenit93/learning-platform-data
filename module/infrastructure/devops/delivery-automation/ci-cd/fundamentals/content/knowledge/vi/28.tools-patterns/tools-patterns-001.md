# Đặt GitHub Actions, GitLab CI và Jenkins vào cùng mô hình khái niệm

GitHub Actions, GitLab CI và Jenkins đều giúp tự động hóa quy trình từ thay đổi source code đến build, test, publish artifact và deploy. Tuy nhiên, mỗi công cụ dùng thuật ngữ, cấu trúc pipeline, cơ chế thực thi và mô hình quản trị khác nhau. Nếu chỉ học cú pháp YAML hoặc Jenkinsfile riêng lẻ, người học dễ nhầm một tính năng có tên giống nhau là có semantics giống nhau, hoặc khó chuyển một pipeline từ nền tảng này sang nền tảng khác.

Cách học bền vững hơn là đặt cả ba vào cùng một mô hình: **sự kiện nguồn → bộ điều phối → định nghĩa pipeline → đồ thị công việc → worker thực thi → artifact và bằng chứng → promotion/deployment**. Sau khi hiểu từng thành phần chịu trách nhiệm gì, ta mới ánh xạ nó sang GitHub Actions, GitLab CI và Jenkins.

Cả ba có thể thực hiện cùng một luồng CI/CD, nhưng không có phép ánh xạ một-một hoàn hảo. GitHub Actions tổ chức workflow, job và step; GitLab CI tổ chức pipeline, stage và job; Jenkins dùng controller, agent, pipeline, stage và step. Khác biệt về scheduler, runner lifetime, permission, cache, artifact, approval và plugin có thể ảnh hưởng trực tiếp đến tính đúng, bảo mật và chi phí vận hành.

## 1. Một mô hình chung cho mọi nền tảng CI/CD

Một pipeline có thể được phân tích thành bảy lớp:

1. **Source và event:** thay đổi nào kích hoạt quy trình, ví dụ push, pull request/merge request, tag, lịch hoặc thao tác thủ công.
2. **Control plane/orchestrator:** hệ thống nhận event, đọc định nghĩa pipeline, tạo run và quản lý trạng thái.
3. **Pipeline graph:** các job/task, điều kiện chạy, dependency, parallelism và thứ tự.
4. **Execution worker:** runner hoặc agent thực thi lệnh trên máy, container hay môi trường được cấp.
5. **Inputs và credentials:** source checkout, dependency, variables, secrets, identity và quyền truy cập.
6. **Outputs và side effects:** log, test report, artifact, cache, package publish, deployment và notification.
7. **Evidence và governance:** trạng thái kiểm tra, approval, audit trail, provenance, monitoring và release record.

~~~mermaid
flowchart TD
    A[Git event hoặc manual trigger] --> B[Control plane / Orchestrator]
    B --> C[Đọc pipeline definition và revision]
    C --> D[Schedule pipeline graph]
    D --> E[Runner / Agent thực thi jobs]
    E --> F[Build, test và quality checks]
    F --> G[Artifact, report và cache]
    G --> H[Publish / Promote / Deploy]
    H --> I[Post-deployment verification]
    I --> J[Evidence, audit và release record]
~~~

Mô hình này giúp đặt câu hỏi đúng khi thiết kế pipeline:

- Event đến từ đâu và có thể bị kích hoạt bởi actor nào?
- Định nghĩa pipeline được lấy từ commit/ref nào?
- Công việc nào có thể chạy song song?
- Worker có được cô lập và cấp quyền tối thiểu không?
- Output nào là artifact cần lưu, output nào chỉ là cache?
- Secret được cấp cho job nào và bằng identity nào?
- Ai có thể approve production?
- Làm thế nào biết artifact đang deploy chính là artifact đã test?

## 2. Thuật ngữ của ba nền tảng

| Khái niệm chung | GitHub Actions | GitLab CI | Jenkins |
|---|---|---|---|
| Định nghĩa pipeline | Workflow YAML | Pipeline YAML | Jenkinsfile |
| Sự kiện kích hoạt | Event và workflow trigger | Pipeline source, workflow/rules và trigger | SCM webhook, polling, timer hoặc trigger plugin |
| Lần chạy | Workflow run | Pipeline | Build/run của job hoặc Pipeline |
| Đơn vị lập lịch chính | Job | Job | Pipeline stage/branch và step được thực thi trên agent |
| Nhóm logic | Workflow/job/step | Pipeline/stage/job/script | Pipeline/stage/step |
| Worker | Runner | GitLab Runner | Agent/node |
| Điều phối | GitHub Actions service | GitLab instance | Jenkins controller |
| Tái sử dụng | Reusable workflow, composite action, action | include, component, extends, child pipeline | Shared Library, plugin và function |
| Artifact | Workflow artifact, package/container registry | Job artifact, package/container registry | Archived artifact hoặc artifact manager/plugin |
| Cache | Actions cache | GitLab cache | Thường qua plugin, workspace hoặc remote cache bên ngoài |
| Approval/deploy gate | Environment protection, reviewers và workflow logic | Manual job, protected environment và deployment approvals tùy cấu hình | input step, RBAC và plugin |
| Secret/identity | Secrets, GITHUB_TOKEN, OIDC | CI/CD variables, job token, ID token/OIDC | Credentials store, binding plugin và identity integration |

Bảng này là bản đồ khái niệm, không có nghĩa các tính năng hoàn toàn tương đương. Ví dụ, GitHub Actions step có thể gọi một action đóng gói hoặc chạy shell; GitLab CI job thường chứa script nhiều lệnh; Jenkins step là lệnh trong Pipeline DSL. Khi chuyển đổi, cần so sánh semantics thay vì chỉ thay tên trường.

## 3. Source event và trigger

Pipeline bắt đầu khi một sự kiện xảy ra hoặc một người yêu cầu chạy. Event quyết định context của pipeline: commit, branch/ref, actor, loại thay đổi và quyền có thể được cấp.

### 3.1. GitHub Actions

Workflow nằm trong thư mục .github/workflows. Khối on khai báo các event như push, pull_request, workflow_dispatch hoặc schedule.

~~~yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Verify
        run: ./gradlew check
~~~

Cần chú ý event và actor context. Workflow chạy trên pull request có thể có quyền khác workflow chạy sau khi merge. Với pull request từ fork, secret và token permissions thường bị hạn chế theo chính sách nền tảng. Không nên giả định mọi event đều có cùng quyền hoặc cùng source revision.

### 3.2. GitLab CI

GitLab dùng pipeline source và các điều kiện như workflow rules, job rules, branch/tag, merge request event, schedule, web hoặc trigger token. Job có thể được loại khỏi pipeline bằng rules.

~~~yaml
workflow:
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
    - when: never

verify:
  stage: test
  image: gradle:8.10-jdk21
  script:
    - ./gradlew --no-daemon check
~~~

Cần hiểu sự khác nhau giữa workflow rules quyết định pipeline có được tạo hay không và job rules quyết định job nào xuất hiện trong pipeline. Một cấu hình rules thiếu trường hợp có thể khiến pipeline không chạy, hoặc tạo cả branch pipeline và merge request pipeline cho cùng thay đổi.

### 3.3. Jenkins

Jenkins có thể nhận webhook từ SCM, polling repository, timer hoặc trigger do plugin cung cấp. Pipeline as Code khai báo trigger trong Jenkinsfile hoặc cấu hình job/multibranch project.

~~~groovy
pipeline {
    agent any

    triggers {
        pollSCM('H/5 * * * *')
    }

    stages {
        stage('Verify') {
            steps {
                sh './gradlew --no-daemon check'
            }
        }
    }
}
~~~

Ví dụ dùng polling để minh họa trigger; webhook thường giảm độ trễ và tải polling nếu SCM/Jenkins được cấu hình đúng. Multibranch Pipeline có thể phát hiện branch và pull request theo SCM integration/plugin. Trigger thực tế phụ thuộc plugin và cấu hình controller.

### 3.4. Câu hỏi chung khi thiết kế trigger

- Pipeline chạy cho push, PR/MR, tag, schedule hay thao tác thủ công?
- Có chạy hai pipeline cho cùng một thay đổi không?
- Pipeline từ fork có được truy cập secret hoặc cache nhạy cảm không?
- Pipeline nào có quyền publish và deploy?
- Có điều kiện để bỏ qua tài liệu hoặc thay đổi không liên quan không?
- Tag release có được bảo vệ và xác minh nguồn tạo không?

## 4. Pipeline definition và version control

Cả ba nền tảng đều hỗ trợ quản lý định nghĩa pipeline dưới dạng mã, nhưng cách lưu và áp dụng có khác biệt.

- GitHub Actions: mỗi workflow là một file YAML trong .github/workflows; có thể gọi reusable workflow hoặc action.
- GitLab CI: pipeline thường bắt đầu từ .gitlab-ci.yml và có thể include file, component hoặc pipeline con.
- Jenkins: Jenkinsfile thường nằm trong repository; Shared Library cung cấp logic dùng chung. Một số cấu hình job và plugin vẫn nằm ở controller nên cần quản lý riêng.

Pipeline as Code mang lại diff, review, history và khả năng khôi phục. Tuy nhiên, không phải toàn bộ hành vi CI/CD đều nằm trong file pipeline. Repository settings, branch protection, runner group, Jenkins plugin, credential binding, service connection, environment approval và quyền tổ chức có thể nằm ngoài source.

Vì vậy, để tái tạo một pipeline, cần version hóa file pipeline và quản lý cả cấu hình control plane có ảnh hưởng đến quyền và hành vi thực thi.

### 4.1. Review pipeline như review code ứng dụng

Các thay đổi nhạy cảm cần review phù hợp:

- Thêm quyền write/admin hoặc quyền deploy.
- Thay runner/agent pool hoặc network boundary.
- Thay action, include, plugin hoặc Shared Library.
- Thay secret reference hoặc credential binding.
- Bỏ required checks, approval hoặc protected environment.
- Thay trigger khiến code từ nhánh/fork không tin cậy nhận quyền cao hơn.
- Thay registry, artifact retention hoặc deployment target.

## 5. Pipeline graph: job, stage, step và dependency

Một pipeline thường là đồ thị có hướng không chu trình (DAG) hoặc một chuỗi các giai đoạn có điều kiện. Các job độc lập có thể chạy song song; job phụ thuộc chỉ bắt đầu khi điều kiện dependency được thỏa mãn.

### 5.1. GitHub Actions: workflow → jobs → steps

- Workflow là file định nghĩa và là đơn vị được trigger.
- Job là đơn vị scheduler cấp runner.
- Các job thường có thể chạy song song nếu không khai báo dependency.
- needs tạo dependency giữa các job.
- Steps trong cùng job chạy tuần tự trên cùng job runner/workspace.
- Một step có thể chạy shell command hoặc dùng action.

~~~yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./gradlew assemble

  test:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./gradlew test

  package:
    needs: [build, test]
    runs-on: ubuntu-latest
    steps:
      - run: ./scripts/package.sh
~~~

Mỗi job có runner/workspace riêng theo mô hình thực thi của nền tảng. Nếu cần chuyển file giữa job, hãy dùng artifact hoặc registry thay vì giả định workspace được chia sẻ.

### 5.2. GitLab CI: pipeline → stages → jobs

- Pipeline chứa các job.
- Stage nhóm job theo pha logic.
- Các job trong cùng stage có thể chạy song song tùy runner capacity và dependency.
- Mặc định các stage được thực hiện theo thứ tự khai báo.
- needs có thể tạo DAG để job bắt đầu khi các dependency trực tiếp hoàn tất mà không phải chờ toàn bộ stage trước.
- script chứa các lệnh thực thi trong job.

~~~yaml
stages:
  - build
  - test
  - package

build:
  stage: build
  script:
    - ./gradlew assemble

unit_test:
  stage: test
  script:
    - ./gradlew test

package:
  stage: package
  needs:
    - build
    - unit_test
  script:
    - ./scripts/package.sh
~~~

GitLab job có thể khai báo artifacts để truyền file cho job sau và cache để tái sử dụng dữ liệu. Hai khái niệm này có semantics khác nhau; không dùng cache thay cho artifact cần được truyền chính xác giữa các bước.

### 5.3. Jenkins: Pipeline → stages → steps

Jenkins Declarative Pipeline có pipeline, agent, stages, stage và steps. Một stage có thể chứa steps tuần tự, parallel hoặc matrix tùy cấu trúc. Agent xác định nơi các bước chạy.

~~~groovy
pipeline {
    agent any

    stages {
        stage('Build') {
            steps {
                sh './gradlew assemble'
            }
        }

        stage('Test') {
            steps {
                sh './gradlew test'
            }
        }

        stage('Package') {
            steps {
                sh './scripts/package.sh'
            }
        }
    }
}
~~~

Jenkins không có cấu trúc job/step giống hệt GitHub Actions. Một Jenkins Pipeline có thể được xem là một lần chạy nhiều stage/step; Jenkins controller quản lý run và agent thực thi công việc. Freestyle job, Pipeline job, Multibranch Pipeline và plugin có thể làm mô hình cụ thể khác nhau.

### 5.4. Mapping không hoàn toàn một-một

| Mục tiêu | GitHub Actions | GitLab CI | Jenkins |
|---|---|---|---|
| Chạy một nhóm lệnh | Step với run | Job script | Pipeline step trong stage |
| Chạy các công việc độc lập song song | Jobs không phụ thuộc needs | Jobs trong stage hoặc DAG với needs | Parallel branches/stages |
| Chờ công việc khác | needs | stage order hoặc needs | Stage order, parallel/join hoặc logic Pipeline |
| Điều kiện bỏ qua | if | rules, only/except legacy | when, expression hoặc scripted logic |
| Ma trận version/OS | strategy.matrix | parallel:matrix | matrix directive hoặc plugin/logic phù hợp |
| Chia nhỏ luồng | Reusable workflow/action | include/component/child pipeline | Shared Library, downstream job |

Khi migrate, hãy chuyển dependency graph và điều kiện trước; sau đó mới chuyển cú pháp. Nếu chỉ chuyển từng stage thành một job mà bỏ qua dependency hoặc artifact handoff, pipeline mới có thể chạy sai thứ tự hoặc mất file.

## 6. Worker: runner, GitLab Runner và Jenkins agent

Control plane quyết định công việc; worker thực thi lệnh. Tách hai vai trò này giúp hiểu isolation, capacity và quyền.

### 6.1. GitHub Actions runner

GitHub-hosted runner do nền tảng cung cấp và được gán cho job. Self-hosted runner do tổ chức quản lý, có thể tồn tại lâu dài hoặc được tạo theo kiểu ephemeral. Self-hosted runner có thể truy cập mạng nội bộ và tài nguyên nhạy cảm, vì vậy cần giới hạn repository/workflow được phép sử dụng, kiểm soát registration và dọn workspace.

### 6.2. GitLab Runner

GitLab Runner nhận job từ GitLab và thực thi bằng executor như Shell, Docker, Kubernetes hoặc các loại executor được hỗ trợ. Runner có thể được đăng ký ở scope instance, group hoặc project tùy cấu hình. Tags giúp job chọn runner phù hợp nhưng tag không tự tạo ranh giới bảo mật; cần kiểm soát ai có quyền chạy job trên runner đó.

### 6.3. Jenkins agent

Jenkins controller lập lịch và điều phối; agent/node chạy build steps. Agent có thể là máy cố định, container hoặc pod được tạo động qua plugin/cloud integration. Không nên chạy build workload nặng trên controller. Cần kiểm soát node labels, executor count, workspace cleanup, plugin và quyền agent kết nối controller.

### 6.4. Những điều cần so sánh

| Thuộc tính | GitHub Actions runner | GitLab Runner | Jenkins agent |
|---|---|---|---|
| Điều phối | Actions service | GitLab instance | Jenkins controller |
| Worker quản lý sẵn | GitHub-hosted runners | Tùy dịch vụ GitLab/runner deployment | Không phải mô hình hosted mặc định chung; phụ thuộc hạ tầng |
| Worker tự quản lý | Self-hosted runner | Self-managed runner | Agent/node |
| Cách chọn worker | runs-on và labels | tags, runner scope và executor | agent label, node selection |
| Isolation | Tùy hosted/self-hosted và job setup | Tùy executor và runner config | Tùy agent, container/VM và plugin |
| Vệ sinh workspace | Phụ thuộc loại runner | Phụ thuộc executor/config | Cần quản lý workspace cleanup |

Đừng coi việc đặt tên runner khác nhau là khác biệt cốt lõi. Hãy đánh giá nơi code chạy, worker có thể truy cập gì, job khác có thể đọc workspace/cache không và ai có thể đăng ký hoặc chọn worker.

## 7. Artifacts, cache và dữ liệu truyền giữa job

Một pipeline thường tạo ra nhiều loại dữ liệu. Cần phân biệt:

- **Artifact:** output cần giữ hoặc truyền đi, như JAR, container image, package, test report hoặc SBOM.
- **Cache:** dữ liệu có thể tái tạo để giảm thời gian, như dependency download hoặc build cache.
- **Workspace:** thư mục làm việc của một job/agent; không mặc định được chia sẻ giữa các worker.
- **Release record:** metadata liên kết source, artifact digest, approval, environment và deployment.

### 7.1. GitHub Actions

Artifact có thể được upload/download giữa các job hoặc lưu để xem lại theo retention. Cache action có key và restore key; cache không nên dùng làm nơi duy nhất lưu artifact phát hành.

### 7.2. GitLab CI

Job artifacts lưu file đầu ra và có thể được job sau tải theo dependency/needs/artifact rules. Cache phục vụ tái sử dụng giữa các lần chạy và có policy riêng. Artifact expiration/retention cần được cấu hình phù hợp với nhu cầu release và audit.

### 7.3. Jenkins

Jenkins có thể archive artifacts từ build hoặc dùng plugin/artifact repository như Nexus, Artifactory hay registry. Workspace không phải artifact store bền vững. Khi cần promote cùng một artifact giữa môi trường, nên publish vào repository bất biến và lưu digest/version.

### 7.4. Quy tắc chung

- Build một lần, promote cùng artifact qua các môi trường.
- Dùng digest hoặc checksum để định danh nội dung.
- Không rebuild ở mỗi environment nếu mục tiêu là kiểm thử và phát hành cùng một binary.
- Lưu test report, SBOM, provenance và metadata cần thiết.
- Cache miss không được làm pipeline sai; artifact release không được phụ thuộc cache còn tồn tại.
- Phân quyền push/pull/delete và retention theo mức độ quan trọng.

## 8. Secrets và workload identity

Ba nền tảng có cách lưu secret khác nhau, nhưng nguyên tắc chung giống nhau: secret chỉ được cấp cho job cần dùng, trong khoảng thời gian cần thiết, với quyền tối thiểu.

### 8.1. GitHub Actions

Có thể dùng repository, environment hoặc organization secrets và GITHUB_TOKEN với permissions được giới hạn. OIDC cho phép workflow nhận token có claims rồi trao đổi với cloud identity provider để lấy credential ngắn hạn, nếu trust policy được cấu hình đúng.

Cần khai báo permissions rõ ràng cho workflow/job. Không cấp contents/packages/deploy write cho mọi job nếu chỉ một job publish cần quyền đó. Bảo vệ environment production bằng reviewer/branch policy phù hợp.

### 8.2. GitLab CI

GitLab hỗ trợ CI/CD variables với các thuộc tính như masked, protected, environment scope và file variable tùy cấu hình. CI_JOB_TOKEN có phạm vi và thời hạn riêng; ID tokens có thể dùng cho workload identity federation với dịch vụ bên ngoài.

Masked variable chỉ giúp che giá trị trong log theo quy tắc nền tảng; nó không ngăn code độc hại đọc và gửi secret ra ngoài. Job chạy code không tin cậy không nên được cấp secret production.

### 8.3. Jenkins

Jenkins thường lưu credential trong Credentials Store và cung cấp cho Pipeline qua credentials binding hoặc plugin phù hợp. Quyền đọc credential phụ thuộc folder/item scope, credential domain và authorization strategy. Cần kiểm soát ai có thể sửa Jenkinsfile/job và ai có thể chạy job với credential.

Credential masking không phải ranh giới chống mã độc. Một script có thể đọc environment variable hoặc truyền credential qua network. Không echo secret, không ghi vào workspace/artifact và giới hạn agent được phép nhận credential.

### 8.4. Bảng nguyên tắc chung

| Kiểm soát | Câu hỏi |
|---|---|
| Least privilege | Job chỉ có quyền cần thiết cho công việc của nó? |
| Secret scope | Secret giới hạn theo repository/project, environment hoặc folder? |
| Workload identity | Có thể dùng OIDC/federation thay credential dài hạn không? |
| Untrusted code | PR từ fork hoặc branch không bảo vệ có thể đọc secret không? |
| Log/artifact | Secret có thể lọt vào console, test report, cache hoặc artifact không? |
| Rotation | Credential có owner, expiry và quy trình rotate/revoke không? |

## 9. Environment, approval và promotion

Một environment biểu diễn nơi ứng dụng được triển khai như development, staging hoặc production. Environment có thể gắn với secret, URL, approval, protection rule và deployment history.

- GitHub Actions có environments, deployment history và protection rules như required reviewers hoặc branch restrictions tùy cấu hình.
- GitLab CI có environment/deployment records, protected environments và manual jobs/approval controls tùy phiên bản, tier và cấu hình.
- Jenkins có thể dùng input step, credentials/RBAC và plugin để tạo approval gate; semantics phụ thuộc cách tổ chức Jenkins.

Approval nên gắn với release candidate cụ thể: artifact digest, commit, environment và phạm vi. Không nên chỉ approve một nút chung rồi cho phép pipeline triển khai bất kỳ artifact nào sau đó.

### 9.1. Promotion khác rebuild

Một quy trình đáng tin cậy thường:

1. Build artifact từ commit xác định.
2. Test và scan artifact.
3. Publish artifact bất biến vào registry.
4. Deploy cùng digest lên staging.
5. Xác minh sau deploy.
6. Thu thập approval production.
7. Deploy đúng digest đã kiểm tra lên production.
8. Ghi deployment record và kết quả xác minh.

Nếu build lại cho production, output có thể khác artifact đã được test. Nếu có lý do bắt buộc rebuild, cần tạo release candidate mới và chạy lại các gate liên quan.

## 10. Tái sử dụng logic pipeline

Tái sử dụng giúp chuẩn hóa pipeline và giảm copy/paste, nhưng mỗi nền tảng có abstraction riêng.

### 10.1. GitHub Actions

- Action đóng gói một bước hoặc nhóm thao tác.
- Composite action gom nhiều step.
- Reusable workflow dùng workflow khác như một đơn vị có input/output và secrets contract.
- Workflow template giúp khởi tạo pipeline chuẩn.

Cần pin action theo version hoặc commit SHA theo policy; kiểm tra source và quyền của action. Reusable workflow có thể giảm duplication nhưng cũng tạo dependency supply chain cần quản lý.

### 10.2. GitLab CI

- include nạp cấu hình từ file/project/component khác.
- extends và YAML anchors giúp tái sử dụng job template.
- CI/CD components cung cấp cấu hình đóng gói theo interface.
- Child pipeline và multi-project pipeline chia luồng theo thành phần hoặc repository.

Cần hiểu merge/override semantics của include, extends và variables. Template dùng chung có thể thay đổi hành vi nhiều project; version và review là cần thiết.

### 10.3. Jenkins

- Shared Library cung cấp function, step và pipeline convention dùng chung.
- Plugin mở rộng SCM, credentials, agent, report và deployment integration.
- Folder/job template hoặc Job DSL có thể chuẩn hóa cấu hình.

Shared Library và plugin có thể thực thi code trên controller/agent với quyền lớn. Cần quản lý version, review, trusted/untrusted library và cập nhật plugin.

## 11. Quan sát, trạng thái và audit trail

Mỗi nền tảng cung cấp log và trạng thái riêng, nhưng release cần một chuỗi bằng chứng thống nhất:

- Actor/event đã kích hoạt pipeline.
- Repository, commit SHA, branch/ref và pipeline definition revision.
- Run ID, job ID, runner/agent identity.
- Test result, scan result và quality gate.
- Artifact coordinates, version, digest và provenance.
- Approval, approver, environment và thời điểm.
- Deployment ID, runtime digest và post-deploy result.
- Retry, cancellation, rollback và incident liên quan.

Pipeline log giải thích các lệnh trong job; audit log của nền tảng ghi thay đổi quản trị; cloud/registry audit log cho biết principal nào thực hiện API trên tài nguyên đích. Không nên dựa vào một console log để chứng minh toàn bộ chuỗi phát hành.

## 12. Cùng một luồng CI/CD trên ba công cụ

Giả sử service Java có luồng:

1. Push hoặc pull request.
2. Build và unit test.
3. Publish artifact khi merge vào main.
4. Deploy staging.
5. Smoke test.
6. Approval và deploy production.

### 12.1. GitHub Actions

~~~yaml
name: Orders CI/CD

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build and test
        run: ./gradlew --no-daemon clean check build
      - name: Upload release artifact for main
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        uses: actions/upload-artifact@v4
        with:
          name: orders-jar
          path: app/build/libs/*.jar

  publish:
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    needs: verify
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: orders-jar
          path: dist/
      - name: Publish
        run: ./scripts/publish.sh dist/

  deploy_staging:
    needs: publish
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - name: Deploy
        run: ./scripts/deploy.sh staging

  deploy_production:
    needs: deploy_staging
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Deploy
        run: ./scripts/deploy.sh production
~~~

Đây là skeleton minh họa. Workflow thực tế cần upload/promote artifact giữa job thay vì giả định workspace được chia sẻ; publish job cần pin actions theo policy, xác minh digest và dùng identity phù hợp. Production environment nên có protection rules và approval theo yêu cầu.

### 12.2. GitLab CI

~~~yaml
stages:
  - verify
  - publish
  - staging
  - production

verify:
  stage: verify
  image: gradle:8.10-jdk21
  script:
    - ./gradlew --no-daemon clean check build
  artifacts:
    paths:
      - app/build/libs/*.jar
    expire_in: 7 days

publish:
  stage: publish
  image: gradle:8.10-jdk21
  rules:
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
  needs:
    - job: verify
      artifacts: true
  script:
    - ./scripts/publish.sh app/build/libs/

deploy_staging:
  stage: staging
  environment:
    name: staging
  script:
    - ./scripts/deploy.sh staging

deploy_production:
  stage: production
  environment:
    name: production
  when: manual
  script:
    - ./scripts/deploy.sh production
~~~

Skeleton này cần điều chỉnh rules và needs để bảo đảm các pipeline source khác nhau có dependency đúng; artifact release cần được publish vào registry bất biến và deploy theo digest. Manual job chỉ là một điểm dừng; quyền chạy job và protected environment cần được cấu hình riêng.

### 12.3. Jenkins Declarative Pipeline

~~~groovy
pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
    }

    stages {
        stage('Verify') {
            steps {
                checkout scm
                sh './gradlew --no-daemon clean check build'
                stash name: 'orders-jar', includes: 'app/build/libs/*.jar'
            }
        }

        stage('Publish') {
            when {
                branch 'main'
            }
            steps {
                unstash 'orders-jar'
                sh './scripts/publish.sh app/build/libs/'
            }
        }

        stage('Deploy Staging') {
            when {
                branch 'main'
            }
            steps {
                sh './scripts/deploy.sh staging'
            }
        }

        stage('Deploy Production') {
            when {
                branch 'main'
            }
            steps {
                input message: 'Approve production deployment?'
                sh './scripts/deploy.sh production'
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'build/reports/**', allowEmptyArchive: true
        }
    }
}
~~~

Skeleton này giả định Multibranch Pipeline và Declarative Pipeline được cấu hình phù hợp. Production approval cần RBAC, người phê duyệt và policy rõ ràng; input step không tự thay thế toàn bộ governance. Trong hệ thống thật, nên tách credential scope, pin toolchain, publish artifact bất biến và deploy đúng digest.

### 12.4. Điểm chung và khác biệt

| Bước | GitHub Actions | GitLab CI | Jenkins |
|---|---|---|---|
| Trigger PR/MR | pull_request | merge request pipeline/rules | SCM integration hoặc multibranch plugin |
| Build/test | Job và steps | Job trong stage | Stage và steps |
| Dependency | needs | stage/needs | Stage order hoặc Pipeline logic |
| Publish condition | if theo event/ref | rules | when/branch condition |
| Artifact handoff | upload/download artifact hoặc registry | job artifacts hoặc registry | archive/artifact repository |
| Staging | Environment và deployment job | environment job | stage/job và plugin/script |
| Production approval | Environment protection | manual/protected environment | input/RBAC/plugin |
| Worker | Runner | Runner | Agent |

## 13. Bảo mật pipeline: không chỉ là bảo vệ file YAML

Pipeline có thể đọc source, secret, artifact và truy cập production. Bề mặt tấn công gồm:

- Pipeline definition và reusable components.
- Action, include, plugin và Shared Library.
- Runner/agent image, workspace và network.
- Secret store, token, OIDC trust policy và credential binding.
- Artifact registry, cache và package repository.
- Environment approval và deployment permissions.
- Webhook, trigger token và service account.

### 13.1. Tách job theo mức quyền

Job build/test cho pull request thường chỉ cần đọc source và dependency. Job publish cần quyền ghi package. Job deploy staging/production cần identity và quyền riêng theo environment. Không nên cấp toàn bộ quyền cho mọi job chỉ để đơn giản hóa cấu hình.

### 13.2. Bảo vệ worker

- Dùng runner/agent ephemeral cho workload không tin cậy nếu phù hợp.
- Dọn workspace và credential sau job.
- Không cho PR từ fork chạy trên worker có quyền truy cập production network.
- Hạn chế runner tag/label và quyền đăng ký worker.
- Cập nhật image, runtime, plugin và action.
- Tách controller/control plane khỏi worker execution.

### 13.3. Supply chain của pipeline

Pin action, plugin, Shared Library và component theo version/revision được review. Xác minh artifact bằng digest/provenance. Theo dõi thay đổi pipeline và quyền. Một workflow file an toàn có thể vẫn gọi một action/plugin không an toàn; cần kiểm soát toàn bộ dependency của pipeline.

## 14. Các khác biệt vận hành cần hiểu trước khi chọn công cụ

| Chủ đề | GitHub Actions | GitLab CI | Jenkins |
|---|---|---|---|
| Mức tích hợp SCM | Tích hợp chặt với GitHub repository/event | Tích hợp chặt với GitLab project/MR | Kết nối SCM qua plugin/integration |
| Quản trị control plane | Dịch vụ GitHub | GitLab SaaS hoặc self-managed | Tổ chức vận hành Jenkins controller |
| Mở rộng execution | Hosted/self-hosted runners | GitLab Runner và executor | Agent/node, cloud/plugin |
| Mức tùy biến | Actions, reusable workflows và runner | YAML, components, runners và pipeline features | Rất rộng qua plugin và Shared Libraries |
| Bảo trì | Ít hơn với hosted; self-hosted cần quản lý | Runner và instance tùy mô hình | Controller, plugin, agent và backup |
| Portability | Workflow/action gắn hệ sinh thái GitHub | Pipeline syntax gắn GitLab | Jenkinsfile/Shared Library gắn Jenkins/plugin |
| Chi phí vận hành | Phụ thuộc plan, minutes và runner | Phụ thuộc tier, runner và hạ tầng | Hạ tầng, vận hành, plugin và nhân lực |

Không có công cụ tốt nhất trong mọi tổ chức. GitHub Actions thường thuận lợi khi source và governance nằm trên GitHub; GitLab CI phù hợp khi nhóm dùng GitLab làm nền tảng tích hợp source, issue và pipeline; Jenkins hữu ích trong môi trường cần tích hợp hệ thống đa dạng, plugin hoặc legacy pipeline phức tạp, nhưng tổ chức phải quản trị controller, plugin và agent.

Quyết định nên dựa trên repository platform, yêu cầu self-hosting, network boundary, compliance, runner capacity, kỹ năng đội ngũ, tích hợp hiện có và tổng chi phí sở hữu.

## 15. Chuyển pipeline từ nền tảng này sang nền tảng khác

Khi migration, đừng bắt đầu bằng việc chuyển YAML từng dòng. Hãy trích xuất hành vi mong muốn thành mô hình độc lập:

1. Liệt kê trigger và điều kiện tạo pipeline.
2. Vẽ DAG job/dependency và xác định parallelism.
3. Ghi runner/agent requirements, OS, toolchain và network.
4. Liệt kê inputs, secrets, identities và permissions theo job.
5. Xác định artifact/cache/workspace handoff.
6. Ghi approval, environment và deployment scope.
7. Xác định retry, timeout, cancellation và concurrency semantics.
8. Ghi report, audit event và release evidence.
9. Viết lại trên nền tảng đích bằng abstraction phù hợp.
10. Chạy song song hoặc đối chiếu output trong giai đoạn chuyển tiếp.

### 15.1. Những lỗi migration thường gặp

- GitHub job được chuyển thành GitLab stage nhưng dependency giữa các job bị thay đổi.
- Giả định workspace giữa các job được chia sẻ.
- GitLab cache bị dùng thay cho artifact cần truyền chính xác.
- Jenkins agent lâu dài giữ lại file/secret từ build trước.
- Approval được chuyển thành manual job nhưng ai cũng có quyền bấm.
- Trigger mới chạy pipeline hai lần cho cùng commit.
- Job rerun làm publish hoặc deploy lặp side effect.
- Secret được chuyển sang variable nhưng không giữ protected/environment scope.
- Plugin hoặc action được thay thế mà không kiểm tra semantics và quyền.

## 16. Cách chọn abstraction phù hợp

Một số nguyên tắc giúp pipeline dễ bảo trì:

- Dùng job cho một đơn vị công việc có input/output và quyền rõ.
- Dùng stage để diễn đạt pha logic; không tạo stage chỉ để đặt tên đẹp.
- Dùng DAG dependency để thể hiện quan hệ thực; tránh phụ thuộc thứ tự ngầm.
- Tách build/test khỏi publish/deploy.
- Tách logic dùng chung khỏi file pipeline bằng abstraction có version.
- Đặt policy và permissions gần job cần chúng.
- Dùng artifact registry cho output cần promote; cache cho dữ liệu tái tạo.
- Dùng environment/protected resource cho approval và deployment history.
- Dùng worker ephemeral hoặc workspace cleanup khi code không tin cậy.
- Ghi release record để liên kết commit, digest, approval và deployment.

## 17. Checklist đọc và đánh giá một pipeline

### Trigger và source

- [ ] Biết event nào tạo pipeline và event nào bị bỏ qua.
- [ ] Biết source revision/ref thực sự được checkout.
- [ ] PR/MR từ fork có quyền và secret phù hợp.
- [ ] Không tạo pipeline trùng ngoài ý muốn.

### Graph và execution

- [ ] Job, stage, step và dependency được hiểu rõ.
- [ ] Công việc độc lập chạy song song đúng cách.
- [ ] Artifact được truyền qua cơ chế bền vững, không dựa vào workspace ngầm.
- [ ] Runner/agent có capacity, isolation và cleanup phù hợp.

### Artifact, cache và security

- [ ] Artifact có version/digest và được promote nhất quán.
- [ ] Cache không thay thế artifact release.
- [ ] Secret chỉ cấp cho job cần dùng.
- [ ] Token/identity có quyền tối thiểu và thời hạn phù hợp.
- [ ] Action/plugin/include/Shared Library được kiểm soát nguồn và version.

### Environment và governance

- [ ] Staging/production được phân biệt rõ.
- [ ] Approval gắn với đúng artifact và environment.
- [ ] Quyền deploy production được giới hạn.
- [ ] Có audit, release record và post-deploy verification.
- [ ] Retry/cancel/rollback không tạo side effect ngoài ý muốn.

## 18. Kết luận mô hình

GitHub Actions, GitLab CI và Jenkins khác nhau về cách đặt tên, cấu hình và vận hành, nhưng cùng giải quyết một bài toán: nhận sự kiện, điều phối đồ thị công việc, cấp worker, quản lý input/credential, tạo output và kiểm soát phát hành.

Hãy hiểu control plane chịu trách nhiệm điều phối; runner/agent chịu trách nhiệm thực thi; pipeline graph thể hiện dependency; artifact là đầu ra cần định danh và promote; cache chỉ là tối ưu hóa; secret/identity quyết định quyền; environment/approval kiểm soát release; audit và observability cung cấp bằng chứng. Khi nắm mô hình này, bạn có thể đọc pipeline của cả ba công cụ, phát hiện khác biệt semantics, thiết kế pipeline có thể truy vết và chuyển đổi nền tảng mà không làm mất các kiểm soát quan trọng.
