# Chọn công cụ theo hệ sinh thái, quyền truy cập và năng lực vận hành

Một công cụ CI/CD có thể có rất nhiều tính năng nhưng vẫn không phù hợp với tổ chức đang sử dụng nó. Một nền tảng tích hợp chặt với Git provider có thể giúp nhóm nhỏ thiết lập pipeline nhanh, nhưng có thể không đáp ứng yêu cầu chạy build trong mạng riêng. Một hệ thống tự quản lý có thể linh hoạt và kiểm soát sâu, nhưng đòi hỏi đội ngũ có khả năng vá lỗi, nâng cấp, vận hành runner, bảo vệ secret và duy trì tính sẵn sàng.

Vì vậy, chọn công cụ CI/CD không nên bắt đầu bằng câu hỏi "công cụ nào có nhiều tính năng nhất?". Cần bắt đầu từ hệ sinh thái hiện tại, mô hình truy cập, ranh giới tin cậy, yêu cầu phát hành và năng lực vận hành mà tổ chức có thể duy trì lâu dài.

Bài viết xây dựng một cách đánh giá có hệ thống: xác định nhu cầu và ràng buộc, phân loại công cụ, kiểm tra khả năng tích hợp, thiết kế identity và quyền truy cập, đánh giá runner và bảo mật, tính tổng chi phí sở hữu, cân nhắc portability và lock-in, rồi kiểm chứng bằng một proof of concept có tiêu chí đo lường. Mục tiêu là chọn được nền tảng mà nhóm có thể vận hành an toàn, truy vết được và mở rộng theo nhu cầu thực tế.

## 1. Bắt đầu từ workflow và ràng buộc, không bắt đầu từ tên sản phẩm

Trước khi lập danh sách công cụ, hãy mô tả luồng phát hành cần hỗ trợ:

1. Git event kích hoạt pipeline.
2. Source được checkout và dependency được xác minh.
3. Build và test chạy trên runner phù hợp.
4. Artifact được tạo, định danh bằng version và digest.
5. Quality gate và security scan đánh giá kết quả.
6. Artifact được ký hoặc gắn provenance khi yêu cầu.
7. Artifact được publish vào registry.
8. Release được promote qua các environment.
9. Approval, deployment và post-deploy verification được thực hiện.
10. Kết quả được ghi nhận để audit, điều tra và rollback.

Từ workflow đó, xác định các ràng buộc:

- Source code nằm ở GitHub, GitLab, Bitbucket hay hệ thống Git tự quản lý?
- Có nhiều repository, nhiều project hoặc nhiều nhóm cùng dùng một nền tảng không?
- Runner có được phép chạy trên cloud public không?
- Build có cần truy cập mạng nội bộ, database test hoặc phần cứng riêng không?
- Secret và identity được quản lý ở đâu?
- Production deployment cần approval, segregation of duties hay change record không?
- Log, artifact, test report và audit record phải lưu bao lâu?
- Ai chịu trách nhiệm nâng cấp và xử lý sự cố của chính nền tảng CI/CD?
- Có yêu cầu về data residency, network isolation hoặc compliance không?

Không nên chọn công cụ trước rồi cố ép quy trình hiện tại vào mô hình của công cụ. Hãy phân biệt yêu cầu bắt buộc, yêu cầu quan trọng và tính năng tiện ích để tránh trả chi phí cho những khả năng không sử dụng.

## 2. Phân biệt công cụ, nền tảng và dịch vụ

Tên gọi "CI/CD tool" thường được dùng cho nhiều lớp khác nhau. Phân biệt các lớp giúp tránh so sánh những sản phẩm không cùng vai trò.

| Lớp | Vai trò | Ví dụ |
|---|---|---|
| Source control | Lưu mã nguồn, branch, pull/merge request và Git event | GitHub, GitLab, Bitbucket |
| CI orchestration | Lập lịch job, quản lý DAG, retry, artifact và pipeline status | GitHub Actions, GitLab CI, Jenkins, Buildkite |
| Runner/agent | Thực thi script, build và test | Hosted runner, self-hosted runner, Jenkins agent |
| Build system | Biên dịch và đóng gói phần mềm | Gradle, Maven, Bazel, Make |
| Artifact registry | Lưu package, container image và binary | GitHub Packages, GitLab Package Registry, Harbor, Artifactory |
| Security/quality | Scan source, dependency, image, IaC và quality gate | SAST/SCA/container scanner, SonarQube và các công cụ tương ứng |
| Deployment/GitOps | Promote và reconcile trạng thái mong muốn | Argo CD, Flux, Spinnaker hoặc deployment service |
| Observability | Thu thập log, metric, trace và deployment event | Prometheus, Grafana, OpenTelemetry và log platform |
| Identity/secrets | Cấp danh tính, quyền và secret cho job | OIDC federation, cloud IAM, Vault, secret manager |

Một nền tảng có thể tích hợp nhiều lớp, nhưng không nhất thiết thay thế tất cả. Ví dụ, GitHub Actions có thể điều phối workflow, trong khi Gradle build artifact và một registry riêng lưu image. Argo CD tập trung vào GitOps continuous delivery; nó thường được ghép với một CI system tạo và publish artifact.

Hãy đánh giá từng lớp theo nhu cầu. Nếu tổ chức đã có build system và registry phù hợp, không cần thay thế chúng chỉ để dùng một CI platform mới.

## 3. Xây dựng tiêu chí lựa chọn có thứ tự ưu tiên

Một danh sách tiêu chí tốt nên chia thành ba nhóm.

### Điều kiện bắt buộc

Nếu không đáp ứng, công cụ bị loại khỏi shortlist:

- Hỗ trợ Git provider và repository model hiện tại.
- Có mô hình runner đáp ứng network và security boundary.
- Có identity và access control phù hợp.
- Có thể lưu log, artifact và audit evidence theo chính sách.
- Hỗ trợ approval hoặc cơ chế kiểm soát production deployment cần thiết.
- Đáp ứng giới hạn về dữ liệu, vùng triển khai và compliance nếu có.

### Tiêu chí quan trọng

Các tiêu chí này có thể được chấm điểm:

- Dễ viết và tái sử dụng pipeline.
- Khả năng mở rộng runner và concurrency.
- Tích hợp registry, test, scan, ticket và observability.
- Quản lý secret và OIDC.
- Khả năng retry, cache, artifact và workflow dependency.
- Chất lượng UI, API, CLI và khả năng debug.
- Audit, retention và reporting.
- Khả năng di chuyển pipeline hoặc dữ liệu ra khỏi nền tảng.

### Tiện ích bổ sung

Ví dụ template có sẵn, marketplace, dashboard đẹp, plugin phong phú hoặc tính năng AI. Chúng có thể tăng năng suất, nhưng không nên bù cho thiếu sót về bảo mật, identity hoặc vận hành.

Mỗi tiêu chí nên có trọng số phản ánh mức quan trọng. Điều kiện bắt buộc là pass/fail; không nên để điểm cao ở UI bù cho việc không đáp ứng ranh giới bảo mật production.

## 4. Đánh giá hệ sinh thái Git và mức độ tích hợp

CI platform cần nhận đúng sự kiện từ source control và phản hồi trạng thái về đúng commit hoặc pull/merge request.

Kiểm tra:

- Webhook hoặc native integration có ổn định không?
- Hỗ trợ branch protection và required checks như thế nào?
- Có phân biệt event từ fork, branch nội bộ, tag và release không?
- Có hỗ trợ monorepo, path filter và nhiều repository không?
- Có thể chia sẻ workflow/template giữa các repository không?
- Có quản lý status, check run, commit SHA và rerun history rõ ràng không?
- Có API để lấy pipeline metadata và audit record không?
- Khi Git provider gián đoạn, pipeline đã chạy có tiếp tục được không?

Tích hợp sâu có thể giảm cấu hình và tăng trải nghiệm developer. Tuy nhiên, nó cũng có thể khiến workflow phụ thuộc vào event model, permission model hoặc expression language riêng của provider.

Nếu dùng nhiều Git provider, hãy thử nghiệm một pipeline đại diện trên từng hệ thống. Đừng giả định khái niệm branch protection, merge train, environment approval hoặc reusable pipeline có semantics giống nhau giữa các nền tảng.

## 5. Kiểm tra khả năng mô hình hóa pipeline

Một công cụ nên biểu diễn được quy trình dưới dạng mã hoặc cấu hình có thể review, version control và tái sử dụng.

Các khả năng cần đánh giá:

- Pipeline as Code và schema validation.
- DAG/job dependencies.
- Parallel jobs và matrix build.
- Conditional execution.
- Reusable workflow, template, shared library hoặc component.
- Retry và timeout theo step/job.
- Manual approval và protected environment.
- Artifact passing giữa job.
- Cache key và cache scope.
- Concurrency group hoặc resource lock.
- Cancel và graceful shutdown.
- Rerun failed job và lịch sử attempt.
- Dynamic pipeline generation nếu thực sự cần.

Không phải pipeline nào cũng cần dynamic graph hoặc plugin framework phức tạp. Một mô hình đơn giản, dễ đọc và dễ debug thường bền vững hơn cấu hình quá linh hoạt mà chỉ một vài người hiểu.

### Kiểm tra tính tái sử dụng

Một pipeline template tốt nên có interface rõ:

- Input có kiểu và giá trị mặc định hợp lý.
- Quyền cần thiết được khai báo rõ.
- Output có tên và định dạng ổn định.
- Version của template được quản lý.
- Breaking change có quy trình nâng cấp.
- Repository sử dụng template có thể pin version hoặc commit.

Tránh template dùng quyền rộng, tự đọc secret toàn tổ chức hoặc thực hiện deploy production mà không có ranh giới rõ.

## 6. Hệ sinh thái tích hợp ngoài Git

CI/CD thường cần kết nối nhiều dịch vụ:

| Nhóm tích hợp | Câu hỏi cần kiểm tra |
|---|---|
| Cloud provider | Có OIDC federation, role assumption và region support không? |
| Container registry | Có push/pull, digest, signature và retention không? |
| Package registry | Có xác thực, version immutability và proxy/cache không? |
| Secret manager | Có short-lived credential và audit access không? |
| Security scanner | Có report format, policy gate và API không? |
| Test management | Có nhận test report và liên kết test với commit không? |
| Issue/change management | Có tạo release record và change evidence không? |
| Chat/notification | Có webhook, routing, retry và deduplication không? |
| Observability | Có gửi deployment event, trace context và metric không? |
| Artifact signing/provenance | Có tạo và xác minh attestation không? |

Ưu tiên integration chính thức hoặc giao thức mở, có tài liệu và cơ chế xác thực rõ. Với plugin cộng đồng, cần xem maintainer, release cadence, quyền plugin yêu cầu, nguồn phát hành và quy trình cập nhật.

Một integration có thể hoạt động về mặt kỹ thuật nhưng không an toàn nếu yêu cầu token quản trị toàn tổ chức hoặc chạy mã bên thứ ba trong cùng trust boundary với production secret.

## 7. Identity và quyền truy cập của người dùng

Nền tảng CI/CD thường chứa quyền đọc source, tạo artifact, truy cập secret và deploy production. Vì vậy, identity là tiêu chí lựa chọn trọng yếu.

Cần kiểm tra:

- SSO và MFA.
- SCIM hoặc quy trình provisioning/deprovisioning nếu cần.
- RBAC theo organization, project, repository, environment và resource.
- Nhóm và team mapping.
- Quyền quản trị được tách khỏi quyền chạy pipeline.
- Service account có owner và vòng đời.
- Audit log cho thay đổi permission.
- Quyền truy cập API và token scope.
- Quy trình thu hồi quyền khi nhân sự rời tổ chức.

Không dùng một token cá nhân của administrator làm credential chung cho mọi pipeline. Dùng service identity riêng theo workload, với quyền tối thiểu và khả năng thu hồi.

### Tách quyền author, approver và deployer

Một pipeline production nên xem xét separation of duties:

- Người sửa pipeline không nhất thiết tự phê duyệt thay đổi production.
- Job test không cần quyền deploy.
- Job deploy chỉ nhận quyền cần thiết cho environment đích.
- Người phê duyệt không thể âm thầm thay đổi artifact được phê duyệt.
- Audit record phải liên kết approver, commit và artifact digest.

Mô hình cụ thể phụ thuộc tổ chức, nhưng công cụ cần hỗ trợ thực thi policy chứ không chỉ ghi lại quy ước trên wiki.

## 8. OIDC và credential ngắn hạn

Nếu pipeline cần truy cập cloud hoặc dịch vụ ngoài, ưu tiên workload identity federation khi hệ thống hỗ trợ. OIDC cho phép job nhận token có claims xác định rồi đổi lấy credential ngắn hạn từ identity provider/cloud IAM.

Đánh giá:

- Có hỗ trợ OIDC token từ job không?
- Claims có thể ràng buộc theo repository, branch, tag, environment và workflow không?
- Có thể giới hạn audience và subject không?
- Có phân biệt job PR với job release không?
- Có audit việc assume role không?
- Có thể giới hạn quyền theo environment và resource không?

Ví dụ luồng:

~~~text
CI job
  |
  | OIDC token with repository/ref/environment claims
  v
Identity provider / cloud STS
  |
  | Validate issuer, audience, subject and policy
  v
Short-lived cloud credentials
  |
  v
Deploy only permitted resource
~~~

Không cấp quyền OIDC rộng cho toàn bộ workflow nếu chỉ một job deploy cần quyền đó. Ràng buộc trust policy theo repository và ref/environment cụ thể. Với fork PR hoặc mã không tin cậy, không cấp credential production.

Nếu phải dùng long-lived secret, cần secret manager, rotation, scope hẹp, audit và không để credential xuất hiện trong log hoặc artifact.

## 9. Runner topology và ranh giới mạng

Runner là nơi thực thi mã. Vì vậy, cách nền tảng cấp runner có thể quan trọng hơn số lượng tính năng trên giao diện.

Các mô hình thường gặp:

| Mô hình | Ưu điểm | Chi phí/rủi ro |
|---|---|---|
| Hosted runner | Ít vận hành host, mở rộng nhanh | Giới hạn image, network và quota; cần xem isolation và data location |
| Self-hosted persistent | Tùy biến sâu, tận dụng hạ tầng nội bộ | Rủi ro workspace residue, credential residue và patching |
| Ephemeral self-hosted | Runner mới cho mỗi job hoặc nhóm job | Cần orchestration và bootstrap tốt |
| Kubernetes-based runner | Tích hợp cluster, scale theo workload | Cần vận hành cluster, admission, quota và isolation |
| Hybrid | Kết hợp hosted và private runner | Phải quản lý routing, policy và trải nghiệm nhất quán |

Câu hỏi cần trả lời:

- Runner có thể chạy trong private subnet không?
- Có kiểm soát egress và ingress không?
- Có thể dùng ephemeral VM/container không?
- Workspace có được xóa sau job không?
- Runner có được tái sử dụng giữa repository tin cậy và không tin cậy không?
- Có giới hạn CPU, memory, disk và concurrency không?
- Có image pinning và patch cadence không?
- Có thể cập nhật runner mà không làm gián đoạn release?
- Có audit và metric về runner lifecycle không?

Không chạy mã PR không tin cậy trên persistent runner có quyền truy cập production network hoặc secret. Runner cần được phân nhóm theo trust level và workload.

## 10. Bảo vệ secret và dữ liệu pipeline

Công cụ cần hỗ trợ cách phân phối secret an toàn:

- Secret scope theo organization/project/repository/environment.
- Environment protection và approval.
- Masking/redaction trong log.
- Secret rotation và expiration.
- Audit ai đọc hoặc sử dụng secret.
- Short-lived credentials.
- Tách secret production khỏi PR workflow.
- Không đưa secret vào artifact, cache hoặc output.
- Có thể dùng external secret manager.

Masking log không phải ranh giới bảo mật tuyệt đối. Mã độc trong job có thể gửi secret ra network nếu job có quyền đọc secret. Cần kết hợp permission, network isolation, trust boundary và short-lived credential.

Dữ liệu khác cũng cần được bảo vệ: source code, test report, crash dump, build log, SBOM và artifact có thể chứa thông tin nội bộ. Kiểm tra quyền truy cập, retention, encryption và vị trí lưu trữ.

## 11. Governance, audit và compliance

Nếu pipeline tham gia phát hành production, cần có bằng chứng đáng tin cậy:

- Ai thay đổi pipeline?
- Ai kích hoạt release?
- Commit nào được build?
- Artifact digest nào được test và scan?
- Policy version nào được áp dụng?
- Ai phê duyệt environment?
- Credential/role nào được sử dụng?
- Artifact được publish ở đâu?
- Deployment bắt đầu và kết thúc lúc nào?
- Health check và rollback có kết quả gì?

Kiểm tra khả năng export audit log, API truy vấn, retention, immutability hoặc chống sửa đổi theo yêu cầu. Cần xác định log có thể bị administrator xóa hay không và cách lưu bản sao ra hệ thống audit độc lập.

Một nền tảng có dashboard tốt nhưng không cho truy xuất bằng chứng theo API có thể gây khó khăn khi cần kiểm toán hoặc liên kết với hệ thống quản trị thay đổi.

## 12. Artifact, provenance và khả năng truy vết

Công cụ nên giữ được mối liên hệ giữa source, build, test và release.

Một artifact release nên có:

- Repository và commit SHA.
- Build run ID.
- Dependency lockfile hoặc build input identity.
- Toolchain version.
- Artifact digest.
- Test report.
- Security scan result.
- SBOM nếu yêu cầu.
- Signature/provenance hoặc attestation.
- Release và deployment reference.

### Build một lần, promote nhiều môi trường

Nếu quy trình yêu cầu cùng một binary được xác minh qua staging rồi promote production, công cụ phải cho phép lưu artifact bất biến và dùng đúng digest qua các môi trường.

Không rebuild riêng cho production chỉ vì job deploy chạy lại, trừ khi quy trình chủ đích yêu cầu build mới. Nếu rebuild tạo digest khác, cần bộ bằng chứng tương ứng.

### Retention

Artifact retention ảnh hưởng khả năng rollback, audit và tái lập điều tra. Đánh giá:

- Thời hạn lưu theo loại artifact.
- Dung lượng và chi phí.
- Quyền xóa.
- Legal hold nếu cần.
- Replication/backup.
- Cách khôi phục artifact đã xóa nhầm.
- Khả năng export sang registry khác.

Không giữ tất cả artifact vô hạn. Hãy phân loại theo release, branch, PR, test output và evidence retention.

## 13. Bảo mật plugin, marketplace và extension

Plugin có thể tăng tốc tích hợp nhưng cũng mở rộng bề mặt tấn công.

Trước khi cài plugin/action/extension, kiểm tra:

- Nguồn phát hành và danh tính publisher.
- Repository có được duy trì không?
- Version có thể pin bằng commit hoặc digest không?
- Plugin yêu cầu quyền nào?
- Nó chạy trong runner hay control plane?
- Có gửi dữ liệu ra ngoài không?
- Có cơ chế review và allowlist không?
- Có thể quét hoặc xác minh dependency của plugin không?
- Cách xử lý khi plugin bị compromise?

Tránh tham chiếu version mutable hoặc branch không được pin trong pipeline nhạy cảm. Cần có policy cho third-party action và plugin, đặc biệt khi chúng chạy trong job có quyền truy cập token hoặc secret.

## 14. Năng lực vận hành của tổ chức

Một công cụ mạnh có thể trở thành gánh nặng nếu tổ chức không có người vận hành nó.

Đánh giá năng lực hiện có:

- Có người quản trị nền tảng CI/CD không?
- Có người chịu trách nhiệm runner, image và patching không?
- Có quy trình backup/restore và disaster recovery không?
- Có khả năng theo dõi capacity, queue và lỗi control plane không?
- Có thể xử lý upgrade và breaking change không?
- Có quy trình incident và support escalation không?
- Có khả năng viết template, plugin và automation nội bộ không?
- Có tài liệu onboarding và hỗ trợ developer không?

### Hosted hay self-managed?

Hosted service giảm việc quản lý control plane, database, upgrade và availability. Tuy nhiên, tổ chức vẫn phải quản lý workflow, runner trust, identity, secret và policy.

Self-managed cho phép kiểm soát sâu hơn về network, data và extension, nhưng tổ chức phải tự chịu trách nhiệm cho patching, backup, monitoring, capacity, HA và incident response.

Không có lựa chọn tốt tuyệt đối. Chọn hosted nếu yêu cầu và policy cho phép, đội ngũ muốn tập trung vào sản phẩm và nhà cung cấp đáp ứng security boundary. Chọn self-managed khi có ràng buộc cụ thể và năng lực vận hành tương xứng.

## 15. Tính tổng chi phí sở hữu (TCO)

Giá license không phản ánh toàn bộ chi phí. TCO của CI/CD nên gồm:

| Thành phần | Ví dụ chi phí |
|---|---|
| Subscription/license | User, seat, concurrency, feature tier |
| Compute | Hosted minutes, VM, Kubernetes node, runner capacity |
| Storage | Artifact, cache, log, test report, registry |
| Network | Egress, cross-region traffic, private connectivity |
| Operations | Platform engineer, on-call, patching, upgrade |
| Security | Secret manager, scanning, signing, audit storage |
| Integration | Plugin, middleware, API maintenance |
| Migration | Chuyển pipeline, artifact, history và training |
| Downtime | Release chậm hoặc pipeline không khả dụng |
| Governance | Compliance evidence, audit và retention |

Cần dự báo theo workload thực tế:

- Số pipeline/ngày.
- Thời gian trung bình và p95 của job.
- Số job chạy song song cao điểm.
- Tỷ lệ cache hit.
- Artifact size và retention.
- Số repository và user.
- Mức tăng trưởng theo quý.
- Nhu cầu runner đặc biệt.

So sánh chi phí ở cùng một workload và cùng mức SLA. Một nền tảng rẻ theo phút build nhưng cần nhiều nhân lực tự vận hành có thể có TCO cao hơn dịch vụ hosted.

## 16. Khả năng mở rộng và hiệu năng

Kiểm tra cả control plane và execution plane:

- Queue latency.
- Thời gian cấp runner.
- Max concurrent jobs.
- Scale-up và scale-down time.
- Job startup overhead.
- Cache performance.
- Artifact upload/download throughput.
- API rate limits.
- Webhook delivery.
- Behavior khi một dependency hoặc region gặp sự cố.

Hãy thử nghiệm ở tải cao điểm dự kiến, không chỉ một pipeline đơn lẻ. Matrix build hoặc monorepo có thể tạo fan-out lớn. Nếu công cụ không có backpressure, queue và quota hợp lý, một đợt push có thể làm cạn runner hoặc rate limit của registry.

Cần xem cách nền tảng xử lý job bị hủy, runner mất kết nối và workflow retry để tránh tạo side effect trùng.

## 17. Portability và mức độ lock-in

Mọi CI platform đều có mức độ đặc thù. Mục tiêu không phải loại bỏ mọi lock-in mà là hiểu và chấp nhận phần phụ thuộc có chủ đích.

Các vùng dễ lock-in:

- YAML/expression syntax riêng.
- Reusable workflow hoặc shared library.
- Plugin/action marketplace.
- Secret store và environment model.
- Cache/artifact API.
- Runner registration.
- Approval và release environment.
- Audit/event API.
- Dashboard và reporting.
- Identity claims và permission model.

### Giữ phần logic nghiệp vụ độc lập

Có thể giảm lock-in bằng cách:

- Đưa build/test/deploy logic vào script hoặc tool có thể chạy độc lập.
- Giữ pipeline file mỏng, chủ yếu điều phối.
- Dùng container image/toolchain được pin.
- Lưu artifact trong registry có thể export.
- Dùng format báo cáo phổ biến khi phù hợp.
- Tách policy khỏi logic triển khai nếu có thể.
- Version hóa reusable component.
- Ghi lại metadata và provenance ở định dạng có thể lưu trữ độc lập.

Không nên tạo abstraction quá mức để che mọi khác biệt giữa platform. Một lớp wrapper phức tạp có thể khó debug hơn việc chấp nhận một số cấu hình riêng của nền tảng.

## 18. So sánh một số mô hình công cụ phổ biến

Bảng sau mô tả xu hướng kiến trúc để định hướng đánh giá. Khả năng cụ thể phụ thuộc edition, phiên bản, cấu hình và chính sách tổ chức; cần xác minh trong proof of concept.

| Công cụ/mô hình | Điểm mạnh thường gặp | Điều cần cân nhắc |
|---|---|---|
| GitHub Actions | Tích hợp chặt với GitHub, workflow YAML, marketplace, hosted và self-hosted runners | Permission model, fork PR, runner isolation, quota và phụ thuộc hệ sinh thái GitHub |
| GitLab CI/CD | SCM, merge request, CI pipeline, registry và nhiều capability DevSecOps trong một nền tảng | Feature availability theo tier/edition, runner operations và mức độ phụ thuộc GitLab |
| Jenkins | Hệ plugin lớn, linh hoạt, self-managed và tích hợp nhiều hệ thống cũ | Quản trị controller/plugin, patching, credential security và maintenance |
| Buildkite | Mô hình control plane kết hợp agent do tổ chức vận hành, phù hợp khi cần kiểm soát execution environment | Cần quản lý agent fleet, queue, plugin và chi phí tổng thể |
| Tekton | Pipeline Kubernetes-native, task/pipeline CRD và khả năng tích hợp với cluster | Cần xây thêm trải nghiệm developer, secrets, artifact, governance và vận hành Kubernetes |
| Argo CD / Flux | GitOps continuous delivery, reconcile trạng thái Kubernetes từ Git | Không thay thế CI build/test; cần phối hợp với CI và quản lý promotion/approval |

### Đừng so sánh chỉ theo danh sách feature

Một tính năng "có" không nói lên mức phù hợp. Ví dụ, hai công cụ đều có self-hosted runner nhưng khác nhau về ephemeral lifecycle, isolation, network policy và cách cấp token. Hai công cụ đều có approval nhưng khác nhau về việc approval gắn với environment, artifact digest hay chỉ workflow run.

Hãy so sánh theo use case cụ thể và bằng chứng PoC.

## 19. Ma trận chấm điểm minh họa

Một scorecard có thể giúp nhiều nhóm cùng đánh giá nhất quán.

| Tiêu chí | Trọng số gợi ý | Câu hỏi |
|---|---:|---|
| Ecosystem/integration | 15% | Tích hợp với Git, registry, cloud và hệ thống hiện tại? |
| Identity/access/security | 20% | Có đáp ứng trust boundary, OIDC, RBAC, secret và audit? |
| Runner/network model | 15% | Có thực thi trong network và isolation yêu cầu? |
| Pipeline capability | 10% | Có mô hình hóa DAG, reuse, artifact, retry và approval? |
| Operations/support | 15% | Đội ngũ có thể vận hành và khôi phục? |
| Governance/evidence | 10% | Có truy vết, retention và audit export? |
| TCO/scalability | 10% | Chi phí và capacity phù hợp tăng trưởng? |
| Portability | 5% | Có thể di chuyển logic, artifact và evidence? |

Chấm mỗi tiêu chí theo thang 1-5:

- 1: Không đáp ứng hoặc cần workaround lớn.
- 2: Đáp ứng một phần, rủi ro đáng kể.
- 3: Đáp ứng yêu cầu hiện tại với một số giới hạn.
- 4: Đáp ứng tốt, có cách vận hành rõ.
- 5: Đáp ứng tốt và đã được kiểm chứng ở tải/mức kiểm soát cần thiết.

Điểm tổng có thể tính bằng tổng của trọng số nhân điểm chuẩn hóa. Nhưng tiêu chí bắt buộc vẫn phải pass riêng. Không chọn nền tảng có điểm tổng cao nếu nó thất bại ở điều kiện security hoặc network bắt buộc.

## 20. Thực hiện proof of concept có thể so sánh

PoC nên dùng cùng một workflow và cùng một workload trên các công cụ shortlist.

### Phạm vi PoC

Chọn một service đại diện có:

- Pull request validation.
- Build và unit test.
- Integration test cần service phụ.
- Container/package artifact.
- Security scan.
- Publish artifact.
- Staging deployment.
- Approval và production-like promotion.
- Post-deploy health check.
- Rerun và rollback thử nghiệm.

### Kịch bản cần thử

1. Pipeline bình thường từ commit tới artifact.
2. Hai commit push gần nhau và concurrency behavior.
3. Job runner bị dừng giữa chừng.
4. Dependency registry trả 429/503.
5. Fork PR hoặc untrusted code.
6. Secret access và OIDC role assumption.
7. Artifact bị hết hạn hoặc không tìm thấy.
8. Job deploy timeout sau khi gửi request.
9. Approval bị từ chối hoặc hết hạn.
10. Runner pool hết capacity.
11. Audit log và evidence export.
12. Restore hoặc migrate một pipeline mẫu.

### Đo lường

- Thời gian setup.
- Thời gian pipeline median/p95.
- Queue và runner startup latency.
- Tỷ lệ rerun và cách lưu attempt.
- Số thao tác thủ công.
- Mức độ khó debug.
- Khả năng phân quyền.
- Chi phí trên cùng workload.
- Thời gian phục hồi khi lỗi.
- Chất lượng audit/provenance.
- Công sức nâng cấp và bảo trì ước tính.

Không đánh giá PoC chỉ qua demo thành công. Cần thử failure path, permission boundary và vận hành thực tế.

## 21. Thiết kế kiến trúc tham chiếu theo quy mô

### Nhóm nhỏ, một Git provider

Một nền tảng CI hosted tích hợp với Git provider, hosted runner và registry managed có thể đủ. Nhóm cần chuẩn hóa reusable workflow, permission tối thiểu, secret scope và branch protection.

Không cần tự vận hành Kubernetes runner nếu workload chưa có yêu cầu đặc biệt.

### Tổ chức cần private network và kiểm soát runner

Có thể dùng CI control plane hosted hoặc self-managed cùng ephemeral runner trong private network. Runner được chia theo trust level và chỉ cấp route tới dependency cần thiết. Identity sử dụng OIDC hoặc workload identity; secret production chỉ được cấp trong protected deployment job.

### Tổ chức Kubernetes/GitOps

CI build, test, scan và publish image theo digest. Sau đó CI cập nhật manifest hoặc promotion record trong Git. Argo CD/Flux reconcile trạng thái cluster từ repository. Approval và policy kiểm soát thay đổi trước khi promotion tới production.

Trong mô hình này, CI và CD có thể là hai hệ thống riêng nhưng cần chung artifact identity, commit reference và audit trail.

### Tổ chức có nhiều nền tảng hoặc legacy

Có thể giữ một số pipeline cũ trong giai đoạn chuyển đổi. Chuẩn hóa build script, artifact format, identity, secret và evidence trước; sau đó di chuyển từng nhóm workflow. Đặt thời hạn cho hệ thống cũ và tránh duy trì hai nền tảng vô thời hạn nếu không có lý do rõ.

## 22. Lập kế hoạch migration và tránh gián đoạn

Migration CI/CD không chỉ là chuyển YAML. Cần chuyển:

- Pipeline definitions và reusable templates.
- Secret và service identity.
- Runner images, network access và certificates.
- Artifact, cache và retention policy.
- Required checks và branch protection.
- Environment approvals.
- Webhook và notification.
- Audit/evidence history.
- Release metadata và rollback reference.

### Chuyển đổi theo từng nhóm

Một cách tiếp cận an toàn:

1. Chọn repository ít rủi ro làm pilot.
2. Chạy song song pipeline cũ và mới ở chế độ không deploy.
3. So sánh artifact digest, test result và duration.
4. Kiểm tra permission và secret access.
5. Chuyển required check khi kết quả tương đương.
6. Chuyển publish/deploy sau khi xác minh approval và rollback.
7. Theo dõi một chu kỳ release.
8. Mở rộng theo nhóm repository.
9. Tắt pipeline cũ sau khi xác nhận không còn consumer.

Không để hai pipeline cùng publish một version hoặc deploy production nếu chưa có concurrency và idempotency rõ.

## 23. Các dấu hiệu lựa chọn sai công cụ

Một số dấu hiệu cho thấy quyết định cần được xem xét lại:

- Phần lớn pipeline phải dùng workaround không được hỗ trợ.
- Runner không thể đáp ứng network hoặc trust boundary.
- Mọi job phải dùng token quyền rộng.
- Không thể liên kết test/scan với artifact digest.
- Audit log không đủ cho điều tra hoặc compliance.
- Một vài cá nhân là người duy nhất hiểu hệ thống.
- Plugin quan trọng không còn được duy trì.
- Nâng cấp thường xuyên làm pipeline ngừng hoạt động.
- Chi phí tăng nhanh do concurrency, storage hoặc runner.
- Mỗi repository tự xây template khác nhau.
- Rerun dễ tạo release hoặc deployment trùng.
- Không có cách export artifact/evidence khi rời nền tảng.

Không phải dấu hiệu nào cũng buộc phải thay công cụ. Có thể giải quyết bằng thay đổi kiến trúc, policy hoặc cách vận hành. Nhưng cần có owner, kế hoạch và tiêu chí đánh giá lại.

## 24. Anti-pattern khi chọn công cụ

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Chọn theo mức độ phổ biến | Không phù hợp hệ sinh thái và ràng buộc | Bắt đầu từ workflow và điều kiện bắt buộc |
| Chọn vì nhiều feature | Tăng độ phức tạp và chi phí | Ưu tiên capability cần dùng |
| Chỉ so sánh license price | Bỏ sót runner, storage, egress và nhân lực | Tính TCO theo workload |
| Bỏ qua identity/secret | Pipeline có quyền vượt nhu cầu | Đánh giá trust boundary và OIDC/RBAC |
| Dùng persistent runner cho mọi loại job | Rủi ro residue và lateral movement | Phân trust level và ephemeral runner |
| Cài plugin tùy tiện | Mở rộng supply-chain attack surface | Pin, review và allowlist extension |
| Coi CI platform là toàn bộ CD | Bỏ sót promotion, GitOps và runtime verification | Phân lớp CI, deployment và observability |
| Tự vận hành mà không có owner | Patch và incident bị bỏ ngỏ | Xác định năng lực vận hành trước |
| Tạo abstraction che mọi platform | Khó debug và khó tận dụng capability | Giữ logic nghiệp vụ độc lập, điều phối rõ |
| Migration tất cả repository cùng lúc | Phạm vi lỗi lớn và rollback khó | Pilot rồi chuyển theo nhóm |
| Không kiểm thử failure path | Chỉ biết happy path | PoC với crash, retry, permission và recovery |
| Không có exit plan | Lock-in và chi phí di chuyển tăng | Lưu artifact, config và evidence có thể export |

## 25. Checklist lựa chọn công cụ CI/CD

### Hệ sinh thái và tích hợp

- [ ] Hỗ trợ Git provider, repository model và trigger hiện tại.
- [ ] Tích hợp registry, cloud, scanner, secret manager và observability.
- [ ] Có API/CLI và webhook đủ cho automation.
- [ ] Có cơ chế reusable pipeline/template có version.
- [ ] Hỗ trợ artifact digest và provenance.

### Identity và bảo mật

- [ ] SSO/MFA/RBAC đáp ứng tổ chức.
- [ ] Có service identity riêng và token scope hẹp.
- [ ] Có OIDC/workload identity nếu cần.
- [ ] Secret được scope theo project/environment.
- [ ] Có audit access và permission change.
- [ ] Runner được cô lập theo trust level.
- [ ] Untrusted PR không truy cập production secret/network.
- [ ] Plugin/action có thể pin và review.

### Vận hành và governance

- [ ] Hosted/self-managed phù hợp năng lực vận hành.
- [ ] Có runner scaling, queue và concurrency control.
- [ ] Có backup/restore, upgrade và support model.
- [ ] Có log, artifact, audit và retention policy.
- [ ] Có approval và separation of duties.
- [ ] Có metric về queue, duration, failure và capacity.
- [ ] Có runbook và owner cho platform.

### Chi phí và khả năng phát triển

- [ ] TCO được tính trên workload thực tế.
- [ ] Có headroom cho tăng trưởng và giờ cao điểm.
- [ ] Portability và lock-in đã được đánh giá.
- [ ] Có kế hoạch export artifact/config/evidence.
- [ ] PoC đã thử cả happy path và failure path.
- [ ] Có kế hoạch migration và exit strategy.

## Kết luận

Chọn công cụ CI/CD là quyết định về hệ sinh thái, quyền truy cập và năng lực vận hành trong nhiều năm. Hãy bắt đầu từ workflow và ràng buộc bắt buộc; đánh giá integration với Git, registry, cloud và hệ thống bảo mật; kiểm tra identity, runner isolation, secret, audit và provenance; sau đó tính TCO, scalability và mức lock-in. So sánh công cụ bằng cùng một PoC có failure path, đo thời gian, chi phí, khả năng debug và chất lượng evidence. Nền tảng phù hợp là nền tảng đáp ứng được ranh giới tin cậy và nhu cầu phát hành hiện tại, đồng thời đội ngũ có thể duy trì, khôi phục và phát triển nó một cách có kiểm soát.

