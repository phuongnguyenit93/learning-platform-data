# Xác định đầu vào gồm artifact, cấu hình và môi trường đích

Triển khai tự động chỉ đáng tin cậy khi pipeline biết chính xác **sản phẩm nào sẽ được đưa lên, cấu hình nào sẽ đi cùng sản phẩm và tài nguyên nào sẽ nhận phiên bản đó**. Nếu một trong ba đầu vào bị mơ hồ, pipeline có thể triển khai nhầm image, dùng cấu hình của môi trường khác hoặc gửi thay đổi đến sai cluster.

Một yêu cầu triển khai cần được mô tả bằng các đầu vào có định danh và có thể kiểm chứng. Artifact nên được tham chiếu bằng digest hoặc phiên bản bất biến; cấu hình cần có phiên bản, phạm vi và schema; môi trường đích cần được xác định bằng tài khoản, region, cluster, namespace hoặc tài nguyên tương ứng. Secret được tham chiếu qua hệ thống quản lý bí mật và cấp theo danh tính workload, không đưa giá trị bí mật vào gói cấu hình triển khai.

## 1. Ba nhóm đầu vào của một lần triển khai

Một lần triển khai thường có ba nhóm đầu vào chính:

| Nhóm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Artifact | Sản phẩm chính xác nào sẽ chạy? | Container image digest, package version, binary checksum |
| Configuration | Sản phẩm sẽ chạy với thiết lập nào? | Config bundle version, Helm values, feature flags |
| Target environment | Sản phẩm được triển khai ở đâu? | Environment, cloud account, region, cluster, namespace |

Ba nhóm này liên quan chặt chẽ nhưng có vòng đời khác nhau. Artifact được tạo trong quá trình build và nên giữ nguyên khi promote qua các môi trường. Cấu hình thường thay đổi theo môi trường và cần được quản lý phiên bản riêng. Target xác định nơi triển khai và quyền mà pipeline cần có.

Ngoài ba nhóm chính, một yêu cầu triển khai thường mang theo metadata và bằng chứng:

- Commit SHA của mã nguồn.
- Pipeline run ID và build ID.
- Artifact digest và provenance.
- Phiên bản cấu hình và checksum.
- Deployment strategy và rollout parameters.
- Người hoặc workflow khởi tạo.
- Approval record nếu môi trường yêu cầu phê duyệt.

Các metadata này giúp xác định lần triển khai đã dùng đầu vào nào và hỗ trợ điều tra hoặc quay lui sau này.

## 2. Xác định artifact bất biến

Artifact là sản phẩm được tạo ra từ quá trình build: container image, JAR, WAR, package, binary, static bundle hoặc gói triển khai. Pipeline cần xác định chính xác artifact sẽ được triển khai, không chỉ xác định tên dễ đọc của nó.

Một tham chiếu artifact nên chứa:

- Repository hoặc package registry.
- Tên sản phẩm.
- Phiên bản hoặc tag để con người tra cứu.
- Digest hoặc checksum để định danh nội dung.
- Nền tảng/kiến trúc nếu artifact có nhiều biến thể.
- Nguồn mã: repository và commit SHA.
- Build run ID và provenance nếu có.

Ví dụ:

~~~yaml
artifact:
  type: container
  repository: registry.example.com/payments/api
  version: "2.8.1"
  digest: "sha256:0123456789abcdef..."
  platform: linux/amd64
  source:
    repository: example/payments
    commit: "a1b2c3d4"
  build:
    runId: "8421"
~~~

Digest trong ví dụ là giá trị minh họa. Khi triển khai thật, pipeline phải lấy digest đã được registry hoặc build system trả về và xác minh có thể tải artifact theo digest đó.

### 2.1. Vì sao tag chưa đủ?

Tag như **latest**, **stable** hoặc **2.8.1** dễ đọc nhưng có thể được di chuyển để trỏ sang nội dung khác. Nếu hai lần triển khai dùng cùng tag ở hai thời điểm khác nhau, chúng có thể nhận hai artifact khác nhau.

Với container image, tham chiếu dạng digest giúp xác định nội dung:

~~~text
registry.example.com/payments/api@sha256:...
~~~

Với package hoặc file binary, có thể dùng version bất biến kết hợp checksum được lưu trong manifest phát hành. Không nên giả định tên file hoặc version string tự nó chứng minh nội dung chưa bị thay đổi.

Nguyên tắc quan trọng là **build một lần, promote cùng artifact**. Artifact đã được kiểm thử ở staging phải là artifact được triển khai lên production. Nếu build lại từ cùng source khi lên production, toolchain, dependency hoặc thời điểm build có thể tạo ra sản phẩm khác.

### 2.2. Kiểm tra nguồn gốc và tính toàn vẹn

Trước khi triển khai, pipeline nên xác minh:

- Artifact tồn tại trong registry được cho phép.
- Digest khớp với giá trị đã được ghi nhận sau build.
- Chữ ký hoặc provenance hợp lệ nếu chính sách yêu cầu.
- Artifact được tạo từ repository, commit và workflow được tin cậy.
- Kết quả scan và quality gate gắn với đúng digest.
- Artifact tương thích với runtime, kiến trúc và nền tảng đích.

Không nên triển khai artifact chỉ vì nó có tên đúng. Một image có thể bị thay thế, lấy từ registry không đáng tin hoặc không phải sản phẩm đã qua kiểm thử.

## 3. Xác định cấu hình đi kèm artifact

Cấu hình điều khiển cách ứng dụng hoạt động trong một môi trường. Ví dụ:

- Endpoint của dịch vụ phụ thuộc.
- Tên database hoặc schema.
- Số worker, timeout và giới hạn kết nối.
- Log level và sampling.
- Feature flag.
- Tên queue, topic hoặc bucket.
- Resource request/limit.
- Ingress, route và policy mạng.

Cấu hình nên được quản lý tách khỏi artifact để cùng một image có thể chạy ở nhiều môi trường. Tuy nhiên, cấu hình phải có định danh rõ ràng để biết phiên bản nào được sử dụng cùng artifact nào.

Ví dụ một tham chiếu cấu hình:

~~~yaml
configuration:
  name: payments-api
  environment: staging
  version: "2026.11.18.3"
  source:
    repository: example/platform-config
    commit: "d4e5f6a7"
  checksum: "sha256:abcdef0123456789..."
~~~

Không nên chỉ truyền tên nhánh như **main** làm phiên bản cấu hình. Nội dung nhánh có thể thay đổi; hãy chốt commit, tag bất biến hoặc version của config bundle để có thể tái hiện lần triển khai.

### 3.1. Tách cấu hình chung và cấu hình theo môi trường

Có thể chia cấu hình thành các lớp:

| Lớp | Ví dụ | Cách quản lý |
|---|---|---|
| Default | Log format, tên metric, giá trị mặc định an toàn | Cùng mã ứng dụng hoặc config chung |
| Service-level | Worker count, retry policy, timeout | Config repository hoặc config bundle |
| Environment-specific | Endpoint staging, region, replica count | Cấu hình riêng cho môi trường |
| Runtime override | Feature flag, tham số vận hành có kiểm soát | Config service hoặc control plane |
| Secret reference | Tên secret, version hoặc resource ID | Secret manager và identity policy |

Cấu hình theo môi trường cần được review và có lịch sử thay đổi. Tránh để một người sửa trực tiếp giá trị trong giao diện production mà không có dấu vết hoặc quy trình kiểm soát.

### 3.2. Xác minh schema và giá trị cấu hình

Cấu hình phải phù hợp với phiên bản ứng dụng. Ví dụ, phiên bản mới có thể yêu cầu thêm trường cấu hình hoặc đổi tên một property. Nếu deploy artifact mới với config cũ, ứng dụng có thể không khởi động hoặc hoạt động sai.

Nên xác minh:

- Cấu hình đúng định dạng và schema.
- Có đủ trường bắt buộc.
- Kiểu dữ liệu và miền giá trị hợp lệ.
- Endpoint thuộc môi trường dự kiến.
- Feature flag không bật nhầm tính năng chưa sẵn sàng.
- Phiên bản config tương thích với phiên bản artifact.
- Không chứa secret dạng plaintext.
- Checksum hoặc version khớp với config đã được phê duyệt.

Có thể thêm trường schemaVersion hoặc minApplicationVersion để mô tả tương thích. Nếu thay đổi cấu hình có thể phá vỡ tương thích ngược, cần triển khai theo thứ tự phù hợp hoặc dùng config version riêng cho từng release.

## 4. Phân biệt cấu hình và secret

Một cấu hình triển khai có thể cần thông tin xác định nơi lấy secret, nhưng không nên chứa giá trị bí mật.

Ví dụ tham chiếu an toàn hơn:

~~~yaml
secretReferences:
  - name: DATABASE_PASSWORD
    provider: aws-secrets-manager
    resource: app/staging/payments/database
    version: current
  - name: PAYMENT_API_TOKEN
    provider: vault
    resource: kv/data/staging/payments/provider
    version: "7"
~~~

Các tên resource và version trong ví dụ chỉ minh họa. Workload identity hoặc job identity cần có quyền đọc đúng secret tương ứng. Alias như current có thể trỏ sang version mới sau khi rotation; nếu cần tái hiện chính xác lần triển khai, hãy ghi lại version thực tế đã được secret manager phân giải. Nếu pipeline cần secret để thực hiện thao tác deploy, nó chỉ nên lấy secret ở job có quyền và trong thời gian cần thiết.

Không đưa password, token, private key hoặc connection string có credential vào config repository, artifact, Helm values công khai hoặc manifest được lưu trong Git. Không truyền secret trong command line hoặc ghi vào log. Cấu hình chỉ nên chứa reference; secret manager chịu trách nhiệm xác thực, phân quyền và cấp giá trị.

## 5. Xác định môi trường đích một cách tường minh

Tên như **staging** hoặc **production** hữu ích cho con người nhưng có thể chưa đủ để định danh tài nguyên thực tế. Một môi trường có thể gồm nhiều cloud account, subscription, project, region, cluster và namespace.

Một target deployment nên xác định:

- Environment name: dev, test, staging hoặc production.
- Cloud account, subscription hoặc project ID.
- Region hoặc zone.
- Cluster hoặc deployment platform.
- Namespace, application hoặc resource group.
- Service name và deployment slot nếu có.
- Identity/role được phép triển khai.
- Chính sách approval, concurrency và rollout.

Ví dụ:

~~~yaml
target:
  environment: staging
  cloud:
    provider: aws
    account: "111122223333"
    region: ap-southeast-1
  kubernetes:
    cluster: app-staging
    namespace: payments
  service: payments-api
~~~

Không nên suy ra target chỉ từ tên branch hoặc một biến tự do do người khởi chạy nhập. Một branch tên **release** không tự động có quyền triển khai production. Target cần được ánh xạ qua allowlist hoặc cấu hình môi trường được quản lý, rồi xác minh bằng danh tính và quyền truy cập.

### 5.1. Tách target khỏi credential

Target cho biết pipeline sẽ thao tác ở đâu; credential xác định pipeline có quyền thao tác hay không. Hai việc này cần được kiểm tra độc lập.

Ví dụ, cấu hình target có thể trỏ đến cluster production nhưng job vẫn phải bị từ chối nếu identity chỉ có quyền staging. Không cho phép người khởi chạy tự nhập một account ID hoặc cluster tùy ý rồi dùng credential có quyền rộng để triển khai đến đó.

Tốt nhất, mỗi environment có role hoặc service account riêng, với quyền chỉ giới hạn ở tài nguyên cần thiết. Production nên có approval và policy riêng nếu tổ chức yêu cầu.

## 6. Tạo một deployment descriptor thống nhất

Khi artifact, config và target được quản lý ở nhiều nơi, có thể tạo một deployment descriptor để liên kết chúng thành một yêu cầu triển khai cụ thể.

Ví dụ:

~~~yaml
apiVersion: delivery.example/v1
kind: DeploymentRequest
metadata:
  service: payments-api
  releaseId: payments-2.8.1
  requestedBy: release-workflow

artifact:
  repository: registry.example.com/payments/api
  digest: sha256:0123456789abcdef...
  sourceCommit: a1b2c3d4

configuration:
  bundle: payments-api
  version: "2026.11.18.3"
  checksum: sha256:abcdef0123456789...

target:
  environment: staging
  account: staging-account
  region: ap-southeast-1
  cluster: app-staging
  namespace: payments

deployment:
  strategy: rolling
  timeout: 15m
  expectedReplicas: 3

secretReferences:
  - provider: aws-secrets-manager
    resource: app/staging/payments/database
~~~

Descriptor là ví dụ mô hình, không phải schema chuẩn của Kubernetes hay một công cụ CI cụ thể. Trong hệ thống thực tế, cần định nghĩa schema, version, validation và quyền sửa descriptor.

Descriptor giúp gắn artifact digest, config version và target vào cùng một bản ghi. Nếu một trường thay đổi sau phê duyệt, yêu cầu triển khai cần được xác minh hoặc phê duyệt lại theo chính sách. Không nên duyệt một descriptor rồi âm thầm thay artifact hoặc target ngay trước khi deploy.

## 7. Kiểm tra đầu vào trước khi tạo thay đổi trên môi trường

Trước khi chạy lệnh triển khai có tác dụng phụ, pipeline nên thực hiện preflight validation. Mục tiêu là phát hiện sai đầu vào khi chưa thay đổi trạng thái của môi trường.

Một preflight thường kiểm tra:

| Nhóm | Kiểm tra |
|---|---|
| Artifact | Registry đúng, digest tồn tại, signature/provenance đạt, scan đạt |
| Source | Commit và pipeline run thuộc nguồn được phép |
| Configuration | Schema hợp lệ, đủ trường, đúng environment và checksum |
| Secret references | Resource tồn tại, identity có quyền đọc, version hợp lệ |
| Target | Account, region, cluster, namespace nằm trong allowlist |
| Compatibility | Artifact tương thích runtime, config và schema dữ liệu |
| Authorization | Job identity có đúng quyền; approval đã hoàn tất |
| Capacity | Tài nguyên đủ cho rollout hoặc quota còn đáp ứng |
| Concurrency | Không có deployment xung đột đang chạy trên cùng target |

Nếu preflight không xác minh được một điều kiện bắt buộc, pipeline cần dừng và nêu rõ trường nào không hợp lệ. Không tự thay bằng **latest**, config mặc định hoặc target mặc định để cố tiếp tục.

## 8. Kiểm tra tính tương thích giữa artifact, config và môi trường

Một artifact hợp lệ vẫn có thể không tương thích với cấu hình hoặc môi trường đích.

Các dạng không tương thích thường gặp:

- Artifact yêu cầu JDK mới hơn runtime của môi trường.
- Image chỉ hỗ trợ kiến trúc ARM nhưng cluster chỉ có node x64.
- Config chứa property đã bị loại bỏ trong phiên bản ứng dụng.
- Ứng dụng yêu cầu database schema mới nhưng migration chưa chạy.
- Config trỏ đến endpoint của staging trong khi target là production.
- Service cần quyền hoặc API version mà cluster chưa hỗ trợ.
- Replica count hoặc resource request vượt quota môi trường.

Có thể mô tả tương thích bằng metadata trong artifact và config:

~~~yaml
compatibility:
  applicationVersion: "2.8.x"
  configSchema: "4"
  runtime:
    java: "21"
  databaseSchema:
    minimum: "18"
    maximum: "20"
~~~

Thông tin này chỉ là ví dụ. Nên lấy metadata từ build manifest hoặc schema đã được kiểm soát, tránh nhập tay mỗi lần phát hành. Preflight cần so sánh yêu cầu với năng lực thực tế của target.

Với database migration, cần xem xét tương thích ngược. Một rollout an toàn có thể triển khai schema theo hướng expand, phát hành ứng dụng tương thích cả schema cũ và mới, rồi mới loại bỏ cấu trúc cũ trong một release sau.

## 9. Ví dụ: truyền đầu vào rõ ràng trong pipeline triển khai

Một workflow triển khai nên nhận artifact digest, config version và environment rõ ràng. Ví dụ GitHub Actions dưới đây minh họa một workflow được khởi chạy thủ công với môi trường đã khai báo:

~~~yaml
name: Deploy release

on:
  workflow_dispatch:
    inputs:
      artifact_digest:
        description: Immutable image digest
        required: true
        type: string
      config_version:
        description: Approved configuration version
        required: true
        type: string
      target_environment:
        description: Deployment environment
        required: true
        type: environment

permissions:
  contents: read

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - name: Validate deployment inputs
        env:
          ARTIFACT_DIGEST: ${{ inputs.artifact_digest }}
          CONFIG_VERSION: ${{ inputs.config_version }}
          TARGET_ENVIRONMENT: ${{ inputs.target_environment }}
        run: |
          [[ "$ARTIFACT_DIGEST" =~ ^sha256:[a-f0-9]{64}$ ]]
          [[ "$CONFIG_VERSION" =~ ^[A-Za-z0-9._-]+$ ]]
          [[ "$TARGET_ENVIRONMENT" == "staging" || "$TARGET_ENVIRONMENT" == "production" ]]

  deploy:
    needs: validate
    runs-on: ubuntu-latest
    environment: ${{ inputs.target_environment }}
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@v4

      - name: Deploy immutable release
        env:
          ARTIFACT_DIGEST: ${{ inputs.artifact_digest }}
          CONFIG_VERSION: ${{ inputs.config_version }}
          TARGET_ENVIRONMENT: ${{ inputs.target_environment }}
        run: |
          ./scripts/deploy.sh --artifact-digest "$ARTIFACT_DIGEST" --config-version "$CONFIG_VERSION" --environment "$TARGET_ENVIRONMENT"
~~~

Ví dụ này chỉ minh họa cách truyền và kiểm tra input. Quyền id-token: write được dùng khi script xác thực với cloud bằng OIDC; nếu nền tảng dùng cơ chế workload identity khác, hãy cấp quyền tương ứng và tối thiểu. Script deploy cần tiếp tục xác minh digest tồn tại, config version được phê duyệt và environment ánh xạ đến đúng account/cluster. Điều kiện kiểm tra chuỗi không chứng minh artifact đáng tin cậy hoặc người khởi chạy có quyền production.

Trong workflow thực tế, cần cấu hình protection rule cho environment production, giới hạn ai được khởi chạy, và yêu cầu approval nếu chính sách cần. Các action dùng trong workflow cũng cần được pin và cập nhật theo quy trình bảo mật của tổ chức.

## 10. Không dùng dữ liệu đầu vào tùy ý làm lệnh hoặc đường dẫn

Một số input đến từ người khởi chạy, pull request, webhook hoặc hệ thống ngoài. Chúng cần được xem là dữ liệu không tin cậy cho đến khi xác minh.

Không ghép trực tiếp branch name, release note, environment name hoặc config path vào shell command. Thay vào đó:

- Kiểm tra giá trị theo allowlist và schema.
- Truyền dữ liệu qua environment variable hoặc tham số riêng.
- Không dùng eval hoặc dựng lệnh shell từ chuỗi tùy ý.
- Chuẩn hóa và xác minh đường dẫn để tránh path traversal.
- Tra cứu target từ danh mục môi trường được quản lý.
- Giới hạn kích thước và kiểu dữ liệu của input.
- Ghi nhận người khởi tạo và nguồn cung cấp input.

Đặc biệt, không để input tự chọn secret resource hoặc cloud role bất kỳ. Pipeline phải ánh xạ environment đã được cho phép sang identity và secret scope tương ứng.

## 11. Gắn phê duyệt với đúng bộ đầu vào

Approval chỉ có ý nghĩa khi người duyệt biết chính xác điều gì sẽ được triển khai. Nội dung phê duyệt nên hiển thị:

- Artifact name, version và digest.
- Commit SHA và build run ID.
- Config version và checksum.
- Target environment, account, region, cluster và namespace.
- Deployment strategy và phạm vi rollout.
- Kết quả test, scan và preflight.
- Người yêu cầu và thời điểm yêu cầu.

Nếu artifact digest, config version hoặc target thay đổi sau approval, cần đánh giá lại và yêu cầu phê duyệt mới khi chính sách quy định. Một approval chung cho release 2.8.1 không đủ nếu có nhiều image hoặc config bundle cùng tên nhưng nội dung khác nhau.

Có thể tạo fingerprint cho deployment descriptor bằng cách hash biểu diễn chuẩn hóa của các trường quan trọng. Fingerprint giúp đối chiếu bộ đầu vào đã duyệt với bộ đầu vào thực sự được deploy. Cần xác định rõ trường nào nằm trong fingerprint và chuẩn hóa dữ liệu trước khi hash.

## 12. Lưu đầu vào để truy vết và quay lui

Sau khi deploy, cần lưu lại deployment descriptor hoặc bản ghi tương đương cùng kết quả thực thi.

Thông tin tối thiểu:

- Artifact digest thực tế được triển khai.
- Config version và checksum.
- Target environment và resource identity.
- Deployment revision hoặc release ID.
- Pipeline run ID, commit SHA và build provenance.
- Approval record.
- Thời điểm bắt đầu/kết thúc và kết quả rollout.
- Kết quả health check và post-deploy verification.

Khi rollback, không nên chỉ chọn tag previous có thể đã thay đổi. Hãy dùng deployment record trước đó để khôi phục đúng artifact digest và config version đã chạy ổn định.

Cũng cần phân biệt rollback ứng dụng với rollback dữ liệu. Nếu release đã thực hiện database migration phá hủy tương thích ngược, việc đưa image cũ trở lại có thể không đủ để khôi phục dịch vụ. Kế hoạch rollback phải xem xét schema, dữ liệu và các thay đổi hạ tầng liên quan.

## 13. Điều tiết triển khai và bảo vệ target

Hai lần triển khai đồng thời đến cùng service có thể ghi đè trạng thái hoặc khiến rollout không nhất quán. Cần kiểm soát concurrency theo target hoặc service.

Các biện pháp:

- Dùng deployment lock hoặc concurrency group theo environment và service.
- Chỉ cho một release thay đổi cùng một target tại một thời điểm nếu nền tảng không hỗ trợ phối hợp an toàn.
- Hủy lần chạy cũ chỉ khi thao tác hủy được thiết kế an toàn.
- Dùng idempotent deployment operation để chạy lại không tạo tài nguyên trùng.
- Kiểm tra trạng thái hiện tại trước khi áp dụng thay đổi.
- Giới hạn quyền deploy theo target cụ thể.
- Có timeout và cơ chế dừng rollout khi health check không đạt.

Không nên dùng cùng một credential có quyền trên mọi cluster chỉ để đơn giản hóa pipeline. Tách identity theo môi trường giúp giảm phạm vi ảnh hưởng nếu job bị xâm nhập hoặc input bị thao túng.

## 14. Ví dụ xuyên suốt: triển khai một release lên staging

Giả sử nhóm phát hành dịch vụ payments-api phiên bản 2.8.1:

1. Build pipeline tạo image và ghi lại digest, commit SHA, build run ID và provenance.
2. Image được scan và kiểm thử. Artifact được lưu trong registry theo digest.
3. Config repository phát hành bundle staging phiên bản 2026.11.18.3, kèm checksum và commit cấu hình.
4. Release descriptor liên kết digest image, config version và target staging.
5. Preflight xác minh image, signature, scan result, config schema, secret references, cluster và quyền deploy.
6. Người có thẩm quyền phê duyệt descriptor nếu staging yêu cầu approval.
7. Pipeline triển khai đúng image digest và config version đã xác minh.
8. Rollout được theo dõi; smoke test và health check chạy trên deployment revision mới.
9. Pipeline lưu descriptor, kết quả triển khai và bằng chứng post-deploy.
10. Sau khi staging đạt yêu cầu, cùng image digest được promotion lên production với config và target production riêng.

Ở bước production, artifact không được build lại. Cấu hình production và secret reference thay đổi theo môi trường, còn artifact digest giữ nguyên. Nhờ vậy, nhóm có thể chứng minh sản phẩm đã kiểm thử ở staging chính là sản phẩm được phát hành.

## 15. Checklist xác định đầu vào triển khai

Trước khi chạy deployment, hãy kiểm tra:

- [ ] Artifact có repository, version và digest bất biến.
- [ ] Digest được lấy từ build/publish result và xác minh lại từ registry.
- [ ] Artifact có nguồn gốc, chữ ký hoặc provenance theo chính sách.
- [ ] Test và security scan gắn với đúng artifact digest.
- [ ] Cấu hình có version hoặc commit bất biến và checksum.
- [ ] Cấu hình đúng schema và tương thích với artifact.
- [ ] Cấu hình môi trường không chứa secret dạng plaintext.
- [ ] Secret chỉ được tham chiếu qua secret manager và có policy cấp quyền phù hợp.
- [ ] Target có environment, account/project, region, cluster và namespace rõ ràng.
- [ ] Target được ánh xạ từ allowlist hoặc environment registry được quản lý.
- [ ] Identity của job chỉ có quyền trên target cần triển khai.
- [ ] Input từ người dùng hoặc webhook được validate trước khi dùng.
- [ ] Approval gắn với đúng artifact, config và target.
- [ ] Có concurrency control và timeout cho deployment.
- [ ] Deployment record lưu đủ đầu vào và kết quả để truy vết.
- [ ] Có thể xác định artifact và config của phiên bản trước để rollback.

Triển khai tự động bắt đầu từ một hợp đồng đầu vào rõ ràng. Khi artifact được định danh bất biến, cấu hình có phiên bản và được kiểm tra tương thích, còn target được xác minh bằng danh tính và quyền phù hợp, pipeline có thể triển khai đúng sản phẩm đến đúng môi trường và giữ được bằng chứng cho từng lần phát hành.

