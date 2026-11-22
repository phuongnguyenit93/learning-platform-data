# Lưu bí mật trong cấu hình pipeline hoặc cấp toàn quyền cho runner

## 1. Vì sao đây là hai lỗi tư duy nguy hiểm?

Pipeline CI/CD thường cần truy cập source repository, package registry, container registry, cloud account, deployment environment và secret manager. Runner thực thi script do repository hoặc pipeline cung cấp. Nếu bí mật được đặt trực tiếp trong file cấu hình hoặc runner được cấp quyền quá rộng, một thay đổi nhỏ trong pipeline có thể trở thành đường truy cập tới nhiều hệ thống quan trọng.

Hai suy nghĩ sai thường gặp:

- “Pipeline là mã nội bộ nên có thể ghi token/password vào YAML hoặc script.”
- “Runner cần deploy nên cứ cấp quyền admin, quyền cloud rộng hoặc dùng một credential chung cho mọi job.”

Hai cách làm này biến pipeline thành nơi tập trung bí mật và quyền truy cập. Khi một pull request không đáng tin cậy, dependency bị xâm nhập, runner bị chiếm quyền hoặc log bị lộ, kẻ tấn công có thể lấy credential và dùng quyền đó vượt ra ngoài phạm vi một job.

Một thiết kế CI/CD an toàn phải coi pipeline và runner là một phần của ranh giới bảo mật. Secret cần được cấp đúng lúc, đúng job, đúng môi trường và trong thời gian ngắn nhất có thể. Runner chỉ nên có quyền cần thiết để thực hiện nhiệm vụ cụ thể.

## 2. Phân biệt cấu hình pipeline và bí mật

Không phải mọi giá trị cấu hình đều là secret. Cần phân loại trước khi chọn nơi lưu:

| Loại dữ liệu | Ví dụ | Cách quản lý |
|---|---|---|
| Cấu hình không nhạy cảm | Build mode, tên service, region công khai, timeout | Pipeline YAML, config file hoặc biến môi trường |
| Định danh tài nguyên | Registry host, cloud project ID, namespace | Cấu hình có kiểm soát, có thể công khai nội bộ |
| Thông tin xác thực | Password, API token, private key, client secret | Secret manager hoặc secret store của CI |
| Dữ liệu ký | Signing key, certificate private key | KMS/HSM hoặc signing service, quyền rất hạn chế |
| Dữ liệu nhạy cảm vận hành | Recovery code, credential khẩn cấp | Vault riêng, quy trình break-glass và audit |

Một URL có thể không phải secret nếu không chứa user/password hoặc token. Ngược lại, một biến có tên bình thường như DEPLOY_CONFIG có thể chứa private key hoặc credential. Phân loại dựa trên nội dung và khả năng lạm dụng, không chỉ dựa vào tên biến.

Không commit bí mật vào repository, kể cả repository private. Lịch sử Git, fork, clone, cache, artifact, log và bản backup có thể giữ lại giá trị đó lâu sau khi file bị xóa.

## 3. Vì sao hard-code secret trong pipeline là sai?

Ví dụ không an toàn:

~~~yaml
deploy:
  script:
    - cloud-cli login --token "token-thuc-te"
    - deploy --environment production
~~~

Giá trị token có thể bị lộ qua:

- Git history và pull request diff.
- Fork hoặc clone repository.
- Log khi command được in ra.
- Error message hoặc debug trace.
- Artifact, cache hoặc file tạm.
- Screenshot, support bundle hoặc bản sao workspace.
- Người có quyền đọc repository nhưng không cần quyền deploy.

Đổi token sau khi xóa khỏi file là cần thiết nhưng chưa đủ nếu token đã từng được commit. Phải coi credential đã lộ, thu hồi hoặc rotate, xác định phạm vi sử dụng và kiểm tra audit log. Một commit mới xóa secret không xóa giá trị khỏi lịch sử hoặc các bản clone.

## 4. Không dùng biến môi trường như một kho bí mật mặc định

Đưa secret vào environment variable thường tốt hơn hard-code trong script, nhưng không tự động làm secret an toàn. Biến môi trường có thể bị đọc bởi:

- Process con có cùng quyền.
- Debug command in toàn bộ environment.
- Crash dump hoặc diagnostic bundle.
- Test report hoặc script vô tình serialize cấu hình.
- Process khác cùng user trên runner dùng chung.
- Plugin/action có quyền đọc environment của job.

Environment variable là cơ chế truyền dữ liệu tới process, không phải secret manager. Nếu dùng, hãy giới hạn phạm vi job, không bật shell tracing, không dump environment, không truyền secret sang job không cần và dọn workspace sau khi thực thi.

Với secret cần bảo vệ cao, ưu tiên lấy trực tiếp từ secret manager trong job có quyền, dùng file descriptor hoặc file tạm với permission chặt nếu công cụ yêu cầu file. Xóa file tạm sau khi dùng và bảo đảm file không được đưa vào artifact/cache.

## 5. Masking log không bảo đảm secret không thể bị lộ

Nhiều CI platform hỗ trợ masked variables để thay giá trị đã đăng ký bằng ký hiệu che trong log. Đây là lớp giảm rò rỉ, không phải ranh giới bảo mật.

Masking có thể thất bại hoặc không áp dụng khi:

- Giá trị bị encode, chia nhỏ, biến đổi hoặc ghép chuỗi.
- Script ghi secret vào file rồi upload artifact.
- Tool tạo crash dump hoặc debug bundle.
- Secret xuất hiện trong exception hoặc output đã được format khác.
- Một process có quyền đọc secret gửi nó qua network.
- Giá trị chưa được đăng ký hoặc không thỏa điều kiện masking của nền tảng.

Không dựa vào masking để cho phép code không đáng tin cậy truy cập secret. Cách bảo vệ chính là không cấp secret cho job đó. Masking, redaction và log review là lớp phòng thủ bổ sung.

## 6. Secret có thể bị lộ qua artifact và cache

Một job có thể không in secret ra console nhưng vẫn vô tình đưa nó vào file:

- File cấu hình được render từ template có credential.
- Test report chứa request header.
- Debug archive chứa environment hoặc process dump.
- Docker build context copy file credential vào image layer.
- Cache lưu thư mục home hoặc workspace có credential.
- Package chứa file .env hoặc signing material.

Trước khi upload, xác định rõ danh sách file được phép publish. Dùng allowlist artifact thay vì archive toàn bộ workspace. Kiểm tra image layer, package manifest và cache path; không lưu thư mục chứa secret hoặc credential helper.

Nếu secret đã xuất hiện trong artifact, xóa artifact khỏi nơi phân phối theo quy trình, thu hồi credential và kiểm tra các bản replica/download nếu có. Xóa một file trên runner không làm artifact đã publish biến mất.

## 7. Lưu secret trong secret manager hoặc CI secret store

Secret manager tập trung giúp kiểm soát quyền đọc, rotation, audit và vòng đời credential. CI secret store có thể phù hợp với secret có phạm vi repository/environment nhỏ, nhưng cần hiểu rõ quyền truy cập của người sửa pipeline và job.

Một cách phân chia:

| Nhu cầu | Nơi lưu phù hợp |
|---|---|
| Credential build nội bộ theo project | Secret store của CI với scope hẹp |
| Credential production nhiều service dùng chung có kiểm soát | Secret manager trung tâm với policy theo workload identity |
| Private signing key | KMS/HSM hoặc signing service; hạn chế xuất key |
| Credential khẩn cấp | Vault/break-glass store, approval và audit |
| Secret của developer | Password manager cá nhân/tổ chức, không đưa vào pipeline |

Secret manager không tự làm hệ thống an toàn nếu mọi runner đều có quyền đọc mọi secret. Policy phải gắn với identity cụ thể, môi trường, service và operation.

## 8. Cấp secret theo job và environment

Không nên đưa toàn bộ secrets của repository vào mọi job. Job lint hoặc unit test thường không cần production credential. Job deploy staging chỉ cần quyền staging. Job publish package cần quyền ghi đúng package namespace.

Nguyên tắc:

- Cấp secret ở job/step cần dùng, không cấp ở cấp workflow nếu không cần.
- Tách secret theo môi trường development, staging và production.
- Không truyền secret production cho pull request từ fork hoặc branch không tin cậy.
- Giới hạn quyền đọc theo repository, branch, tag, environment và actor nếu nền tảng hỗ trợ.
- Dùng approval/environment protection trước khi cấp credential production.
- Không để job con hoặc action không liên quan thừa hưởng secret.

Một pipeline có thể có nhiều job nhưng chỉ một job release cần credential production. Tách job đó giúp thu hẹp blast radius nếu bước build hoặc test bị xâm nhập.

## 9. Ưu tiên credential ngắn hạn và workload identity

Credential dài hạn như personal access token hoặc access key tĩnh có thể tồn tại nhiều tháng. Nếu bị lộ, nó có thể tiếp tục được sử dụng cho tới khi bị phát hiện và thu hồi.

Khi nền tảng hỗ trợ, ưu tiên:

- OIDC federation giữa CI platform và cloud/secret manager.
- Workload identity gắn với repository, branch, workflow hoặc environment.
- Token có thời hạn ngắn và scope tối thiểu.
- Credential được cấp theo từng job và tự hết hạn.
- KMS/signing service nhận yêu cầu ký mà không xuất private key ra runner.

Ví dụ luồng OIDC:

~~~mermaid
sequenceDiagram
    participant CI as CI Job
    participant IdP as CI Identity Provider
    participant Cloud as Cloud STS
    participant API as Target API
    CI->>IdP: Request OIDC identity token
    IdP-->>CI: Short-lived signed token
    CI->>Cloud: Exchange token with trust policy
    Cloud-->>CI: Temporary scoped credentials
    CI->>API: Perform permitted deployment
    API-->>CI: Result
    Note over CI,Cloud: Temporary credentials expire automatically
~~~

Trust policy cần kiểm tra issuer, audience, subject và các claim phù hợp. Không chỉ xác minh token được ký bởi đúng issuer; cần giới hạn token nào được phép nhận role production. Ví dụ, chỉ workflow từ repository cụ thể, branch/tag được bảo vệ và environment đã được phê duyệt mới được assume role.

## 10. Không cấp quyền admin cho runner chỉ vì cần deploy

Runner là nơi thực thi code và script. Nếu runner có quyền administrator trên cloud account, cluster hoặc subscription, bất kỳ job nào chạy trên runner có thể trở thành đường truy cập tới toàn bộ tài nguyên đó.

Ví dụ quyền quá rộng:

- Một cloud access key có quyền Owner trên toàn account.
- Kubernetes cluster-admin dùng cho mọi namespace.
- Personal access token có quyền quản trị mọi repository.
- Registry credential có quyền xóa/publish mọi image.
- Runner có quyền truy cập production database dù chỉ cần deploy ứng dụng.

Thay vào đó, xác định operation cụ thể: cập nhật một deployment, push vào một repository, đọc một secret hoặc tạo một release. Cấp quyền tương ứng trên đúng resource và thời gian cần thiết.

## 11. Least privilege cho từng loại job

Least privilege (đặc quyền tối thiểu) nghĩa là identity chỉ có quyền cần để hoàn thành nhiệm vụ được giao.

| Job | Quyền nên có | Quyền không cần mặc định |
|---|---|---|
| Lint/unit test | Checkout source, đọc dependency cần thiết | Production deploy, cloud admin, signing key |
| Build/package | Đọc source/dependency, ghi artifact vào namespace của project | Xóa artifact khác, quản trị registry |
| Security scan | Đọc source và metadata cần scan | Deploy production, đọc secret runtime |
| Publish image | Push vào repository/image cụ thể | Xóa toàn registry hoặc sửa IAM |
| Deploy staging | Cập nhật workload trong staging namespace | Cluster-admin toàn cluster, production access |
| Deploy production | Quyền deploy hẹp sau approval, truy cập secret cần thiết | Owner toàn cloud account |
| Sign release | Gọi signing service theo policy | Export private key hoặc quản trị KMS |

Quyền cần được kiểm tra cả ở cloud IAM, Kubernetes RBAC, registry ACL, repository token, secret manager và hệ điều hành runner. Thu hẹp một lớp nhưng để lớp khác toàn quyền vẫn không đạt least privilege.

## 12. Runner có quyền quản trị host là một ranh giới bảo mật

Một runner có thể chạy shell, container, build tool và script từ repository. Nếu job có quyền root/administrator trên host, nó có thể:

- Đọc file và credential của job khác nếu workspace hoặc process dùng chung.
- Thay đổi runner agent hoặc cấu hình để chiếm các job sau.
- Đọc Docker socket hoặc container runtime.
- Cài persistence, binary độc hại hoặc SSH key.
- Truy cập metadata service hoặc network nội bộ.
- Lấy token của host/runner manager nếu được lưu trên máy.

Vì vậy, không dùng runner đặc quyền cao làm pool chung cho mã không tin cậy. Runner cho pull request từ fork cần môi trường cô lập, ephemeral và không có secret hoặc quyền production.

## 13. Ephemeral runner và isolation

Ephemeral runner được tạo cho một job hoặc một workload ngắn hạn rồi hủy. Nó giảm rủi ro dữ liệu còn sót lại giữa các job và hạn chế persistence trên máy dùng chung.

Tuy nhiên, ephemeral không tự động đồng nghĩa an toàn. Cần:

- Tạo runner từ image đã kiểm soát và có thể tái tạo.
- Dùng identity riêng cho từng runner/job hoặc nhóm tin cậy.
- Không mount host path, Docker socket hoặc credential không cần thiết.
- Hạn chế network egress theo dependency cần dùng.
- Không tái sử dụng workspace chứa dữ liệu nhạy cảm.
- Hủy instance và revoke identity sau job.
- Giữ log/evidence cần thiết bên ngoài runner trước khi terminate.
- Theo dõi orphan runner và cleanup failure.

Container runner vẫn chia sẻ kernel với host. Với workload không tin cậy hoặc cần quyền cao, cân nhắc VM isolation hoặc cơ chế sandbox mạnh hơn. Chọn mức cô lập theo threat model và loại mã được thực thi.

## 14. Không chạy mã từ fork/untrusted PR trên runner có secret

Pull request từ fork có thể thay đổi workflow, script build, test hoặc dependency. Nếu workflow cấp secret production cho job đó, contributor có thể sửa script để đọc và gửi secret ra ngoài.

Quy tắc an toàn:

- Không cấp secret cho job chạy mã từ fork không tin cậy.
- Không dùng runner persistent có quyền truy cập mạng nội bộ cho untrusted PR.
- Tách pool untrusted và trusted bằng identity, network và filesystem.
- Kiểm tra cẩn thận event trigger và quyền token mặc định.
- Chỉ chạy bước cần quyền cao sau khi thay đổi đã qua review và branch/environment policy.
- Không để artifact/cache do untrusted job tạo được tin cậy tự động trong release job.

Ngay cả khi nền tảng che secret trong log, script độc hại vẫn có thể gửi secret qua network. Không cấp secret là biện pháp quyết định.

## 15. Hạn chế quyền của CI token

Token do CI platform cấp cho workflow cũng là credential. Không nên để token mặc định có quyền ghi mọi repository hoặc quản trị toàn bộ project nếu job chỉ cần checkout source.

Các nguyên tắc:

- Mặc định quyền read-only nếu workflow chỉ đọc.
- Cấp write permission riêng cho job cần publish hoặc tạo release.
- Giới hạn token theo repository/project và thời gian sống.
- Không dùng personal access token cá nhân làm credential chung cho automation.
- Không chia sẻ token giữa developer, runner và service account.
- Xoay vòng và thu hồi token khi owner thay đổi hoặc nghi ngờ bị lộ.
- Audit các thao tác được thực hiện bằng bot identity.

Token scope cần xét cả quyền API và phạm vi tài nguyên. Một token chỉ có quyền package write nhưng áp dụng cho toàn tổ chức vẫn rộng hơn token chỉ ghi một package namespace.

## 16. Không để secret đi qua cache, Docker build context và image layer

Các đường rò rỉ thường bị bỏ qua:

- Cache dependency chứa file cấu hình có credential.
- Docker build context bao gồm file .env hoặc thư mục home.
- Build argument chứa secret và được lưu trong image history hoặc build metadata.
- Image layer tạo ở bước trước vẫn giữ file secret dù bước sau đã xóa.
- Artifact được tạo từ workspace chứa credential.

Với Docker/BuildKit, dùng secret mount của build tool khi cần secret trong quá trình build, không truyền secret như build argument thông thường. Giới hạn build context bằng ignore file và chỉ copy những file cần thiết. Không đóng gói file credential vào final image.

Ví dụ nguyên tắc:

~~~dockerfile
# Không truyền token bằng ARG hoặc ENV.
# Dùng secret mount do builder hỗ trợ ở lệnh cần xác thực.
RUN --mount=type=secret,id=package_token \
    ./download-private-dependency.sh
~~~

Đoạn trên minh họa BuildKit secret mount; cú pháp và quyền truy cập phụ thuộc builder. Script cần đọc secret từ mount path, không in ra log và không copy vào layer kết quả.

## 17. Pipeline injection và workflow không đáng tin

Pipeline-as-code có thể bị lợi dụng nếu workflow chèn dữ liệu do người dùng kiểm soát trực tiếp vào shell command. Ví dụ branch name, pull request title hoặc input không được kiểm tra có thể chứa ký tự làm thay đổi lệnh.

Các nguyên tắc:

- Không nội suy trực tiếp dữ liệu không tin cậy vào shell script.
- Đưa giá trị qua input/argument được quote đúng và validate theo allowlist.
- Dùng script file riêng thay vì tạo shell command động phức tạp.
- Hạn chế quyền token của workflow.
- Không dùng privileged runner cho workflow nhận input từ fork.
- Review thay đổi workflow và shared action như code nhạy cảm.
- Pin action/plugin bên thứ ba theo version hoặc immutable commit khi phù hợp.

Một job không có secret vẫn có thể gây hại nếu runner có quyền truy cập network nội bộ hoặc token host. Vì vậy, kiểm soát input và quyền runner cần được áp dụng cùng nhau.

## 18. Secret rotation và xử lý khi nghi ngờ bị lộ

Khi phát hiện secret xuất hiện trong commit, log hoặc artifact, cần coi credential đó đã bị lộ cho tới khi chứng minh được phạm vi khác.

Quy trình xử lý:

1. Xác định loại secret, owner, scope và hệ thống chấp nhận credential.
2. Thu hồi hoặc rotate credential theo mức độ khẩn cấp.
3. Kiểm tra audit log để tìm hoạt động bất thường kể từ thời điểm có thể bị lộ.
4. Xác định nơi giá trị xuất hiện: Git history, artifact, cache, log, runner disk hoặc backup.
5. Xóa/thu hồi bản phân phối theo retention và incident policy; hiểu rằng bản clone có thể còn tồn tại.
6. Cập nhật secret manager và consumer cần credential mới.
7. Xác minh workflow không còn đọc credential cũ.
8. Bổ sung secret scanning và test redaction để ngăn tái diễn.

Không chỉ xóa dòng secret khỏi YAML rồi coi sự cố đã giải quyết. Git history có thể còn giá trị cũ; force-push rewrite history có thể giảm khả năng truy cập trong một số trường hợp nhưng không thay thế việc revoke credential.

## 19. Phân tách quyền build, publish, deploy và sign

Một pipeline duy nhất có thể chứa nhiều giai đoạn với yêu cầu quyền khác nhau. Nếu toàn workflow nhận quyền production từ đầu, mọi bước trước deploy đều có thể làm lộ quyền đó.

Thiết kế tốt hơn là tách identity:

| Giai đoạn | Identity | Quyền |
|---|---|---|
| Build/test | Build identity | Đọc source/dependency, tạo output tạm |
| Publish artifact | Publisher identity | Ghi artifact vào namespace cụ thể |
| Sign | Signing identity | Yêu cầu ký artifact theo policy |
| Deploy staging | Staging deploy identity | Cập nhật staging |
| Deploy production | Production deploy identity | Cập nhật workload production đã chỉ định |

Artifact cần được liên kết với digest, source revision và build provenance. Job deploy nên nhận artifact đã được kiểm tra thay vì build lại từ source trong môi trường có quyền production.

## 20. Ví dụ pipeline an toàn hơn

Đây là pseudocode thể hiện cách tách quyền:

~~~yaml
jobs:
  test:
    permissions:
      repository: read
    secrets: []
    steps:
      - checkout
      - run-unit-tests

  publish:
    needs: [test]
    permissions:
      repository: read
      artifact: write
    steps:
      - build-package
      - publish-artifact

  deploy-staging:
    needs: [publish]
    environment: staging
    identity: staging-deployer
    steps:
      - download-artifact-by-digest
      - deploy-staging
      - verify-staging

  deploy-production:
    needs: [deploy-staging]
    environment: production
    approval: required
    identity: production-deployer
    steps:
      - verify-approved-artifact
      - request-short-lived-credentials
      - deploy-production
      - verify-production
~~~

Đây là cấu hình khái niệm, không phải cú pháp trực tiếp của một CI platform. Hệ thống thật cần ánh xạ permission, secret scope, environment protection và OIDC trust policy theo semantics của nền tảng. Điểm cốt lõi là job test không có secret production và chỉ job deploy production được nhận identity tương ứng sau khi đạt gate.

## 21. Ví dụ Kubernetes RBAC cho deploy namespace-scoped

Không nên cấp cluster-admin cho mọi runner chỉ để cập nhật một Deployment. Có thể tạo ServiceAccount và Role chỉ cho phép thao tác cần thiết trong namespace đích.

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: ci-deployer
  namespace: staging
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: deployment-updater
  namespace: staging
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "watch", "patch", "update"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: ci-deployer-binding
  namespace: staging
subjects:
  - kind: ServiceAccount
    name: ci-deployer
    namespace: staging
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: deployment-updater
~~~

Đây là ví dụ minh họa. Cần kiểm tra các resource/verb thực tế mà công cụ deploy yêu cầu; Helm, rollout controller hoặc thao tác ConfigMap/Secret có thể cần quyền bổ sung. Không thêm quyền xóa, tạo secret hoặc truy cập namespace khác nếu không có lý do. Production nên dùng identity và namespace policy riêng.

## 22. Kiểm tra quyền hiệu lực, không chỉ quyền khai báo

Một file YAML có thể khai báo permission hẹp nhưng job vẫn thừa hưởng quyền từ runner host, cloud metadata service, mounted credential hoặc service account mặc định.

Hãy kiểm tra:

- Token của workflow thực tế có scope nào?
- Runner process chạy dưới user nào và có quyền sudo/admin không?
- Container có mount Docker socket, host filesystem hoặc kubeconfig nào?
- Instance có thể truy cập cloud metadata endpoint không?
- Network egress có thể tới database/production subnet không?
- ServiceAccount mặc định có quyền rộng hơn mong đợi không?
- Credential có được cache ở home directory hoặc workspace không?
- Job trước có thể để lại process/file ảnh hưởng job sau không?

Thực hiện kiểm tra quyền bằng identity của job trên môi trường thử nghiệm. So sánh hành động được phép và bị từ chối với policy mong đợi. Một policy chỉ có giá trị khi quyền hiệu lực tại runtime đúng như thiết kế.

## 23. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Commit token/password vào YAML | Secret tồn tại trong Git history và bản clone | Secret manager, revoke/rotate nếu đã lộ |
| Cho rằng repository private là đủ an toàn | Người có quyền đọc repo có thể thấy secret | Tách quyền đọc code và quyền dùng secret |
| Dựa vào masked log | Secret có thể lộ qua biến đổi, artifact hoặc network | Không cấp secret cho job không tin cậy |
| Đưa mọi secret vào environment của toàn workflow | Mọi job có thể đọc secret không cần thiết | Scope theo job/environment |
| Dùng PAT cá nhân cho automation | Quyền và vòng đời gắn với tài khoản người dùng | Bot/workload identity với scope hẹp |
| Cấp cloud Owner hoặc cluster-admin cho runner | Một job bị chiếm quyền có thể kiểm soát nhiều tài nguyên | Least privilege theo resource/operation |
| Dùng persistent runner cho fork PR | Persistence và truy cập chéo job | Pool untrusted ephemeral và cô lập |
| Chia sẻ runner giữa trusted/untrusted job | Rò rỉ workspace, process và credential | Tách trust boundary và host identity |
| Lưu secret trong cache/artifact/image layer | Credential tồn tại ngoài job | Allowlist output, secret mount và scan |
| Chỉ xóa secret khỏi commit mới | Git history và bản phân phối vẫn có giá trị cũ | Revoke/rotate, audit và xử lý artifact/log |
| Dùng cùng identity cho build và deploy | Job build/test có quyền production | Tách identity theo stage |
| Cho rằng container đồng nghĩa isolation tuyệt đối | Host kernel/socket/network vẫn có thể bị truy cập | VM/sandbox và hạn chế quyền host |

## 24. Checklist trước khi cho pipeline truy cập secret hoặc quyền deploy

Trước khi bật một credential hoặc runner pool, hãy kiểm tra:

- [ ] Dữ liệu đã được phân loại: cấu hình thường hay secret.
- [ ] Không có secret hard-code trong source, YAML, Dockerfile, script hoặc test fixture.
- [ ] Secret được lưu trong CI secret store/secret manager phù hợp.
- [ ] Secret chỉ được cấp cho job, branch, environment và actor cần dùng.
- [ ] Pull request từ fork/untrusted không nhận secret hoặc runner có quyền cao.
- [ ] Credential ngắn hạn/OIDC được ưu tiên khi nền tảng hỗ trợ.
- [ ] Token có scope tối thiểu và thời hạn phù hợp.
- [ ] Runner không có admin/cluster-wide/cloud-wide permission mặc định.
- [ ] Runner pool trusted và untrusted được tách biệt.
- [ ] Không mount host socket, credential hoặc filesystem không cần thiết.
- [ ] Network egress và metadata access được giới hạn theo nhu cầu.
- [ ] Artifact, cache, build context và image layer không chứa secret.
- [ ] Log masking/redaction và access control đã được kiểm tra.
- [ ] Rotation/revocation và audit procedure đã sẵn sàng.
- [ ] Quyền hiệu lực được kiểm chứng bằng identity thực của job.
- [ ] Build, publish, sign và deploy dùng identity tách biệt khi cần.

## 25. Nguyên tắc thực hành cốt lõi

1. Pipeline YAML là cấu hình có thể được review và lưu trong Git; secret không thuộc nội dung repository.
2. Masking chỉ giảm rò rỉ qua log, không bảo vệ secret khỏi code được phép đọc nó.
3. Cấp secret theo job/environment và không cấp cho workflow từ nguồn không tin cậy.
4. Ưu tiên workload identity, OIDC và credential ngắn hạn thay cho key tĩnh.
5. Áp dụng least privilege cho token, cloud IAM, Kubernetes RBAC, registry và secret manager.
6. Coi runner là ranh giới bảo mật vì nó thực thi script và có thể truy cập tài nguyên host.
7. Tách runner trusted/untrusted; dùng ephemeral isolation và hạn chế network/host access.
8. Kiểm soát artifact, cache, Docker build context và image layer để tránh lưu secret ngoài ý muốn.
9. Khi secret nghi bị lộ, revoke/rotate và kiểm tra audit; xóa file không đủ.
10. Tách quyền build, publish, sign và deploy; xác minh quyền runtime thay vì chỉ đọc YAML.

Lưu bí mật trong cấu hình pipeline và cấp toàn quyền cho runner đều xuất phát từ việc coi CI/CD như một công cụ tự động hóa thuần túy. Trên thực tế, pipeline thực thi mã và mang identity có thể chạm tới tài nguyên quan trọng. Khi secret được cấp đúng phạm vi, credential có thời hạn ngắn, runner được cô lập và quyền được giới hạn theo nhiệm vụ, tốc độ tự động hóa vẫn được duy trì mà rủi ro từ một job bị xâm nhập được thu hẹp đáng kể.
