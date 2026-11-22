# Phát hành và rollback

## 1. Phát hành và rollback trong DSL là gì?

Phát hành (release) là quá trình đưa một phiên bản DSL, compiler, runtime, plugin, artifact hoặc ứng dụng sử dụng DSL tới người dùng hay môi trường vận hành. Rollback là quá trình đưa hệ thống về một trạng thái phát hành trước đó hoặc khôi phục một phần thành phần khi phiên bản mới gây lỗi.

Trong một hệ sinh thái DSL (Domain-Specific Language), release thường gồm nhiều thành phần có version và vòng đời riêng:

- Language specification và language version.
- Compiler, parser, optimizer và code generator.
- Runtime, virtual machine và standard library.
- Artifact format, bytecode hoặc intermediate representation.
- Plugin API, language server và IDE extension.
- Query engine, workflow engine và connector.
- Schema, migration và configuration.
- Package, dependency và deployment bundle.

Một release có thể thay đổi cú pháp, semantics, API, artifact format hoặc cách thực thi. Vì vậy, phát hành DSL không chỉ là đóng gói binary. Cần bảo đảm source, compiler, runtime, artifact, schema và môi trường triển khai tương thích theo hợp đồng đã công bố.

Rollback cũng không đơn giản là cài lại binary cũ. Phiên bản mới có thể đã thay đổi database schema, ghi dữ liệu theo format mới, tạo workflow instance mới hoặc thực hiện side effect bên ngoài. Rollback an toàn cần xem xét toàn bộ trạng thái mà release đã tác động.

## 2. Mục tiêu của quy trình release

Một quy trình release tốt giúp:

1. Tạo artifact có danh tính và nguồn gốc xác định.
2. Xác nhận đúng source revision, compiler và dependency.
3. Kiểm tra compatibility giữa compiler, runtime và artifact.
4. Phát hành cùng tài liệu, migration và release notes.
5. Triển khai theo từng giai đoạn để giới hạn phạm vi ảnh hưởng.
6. Phát hiện sớm lỗi qua health check và telemetry.
7. Giữ khả năng quay lại phiên bản ổn định khi cần.
8. Bảo vệ dữ liệu và workflow đang chạy trong quá trình nâng cấp.
9. Ghi lại ai phát hành, artifact nào được triển khai và kết quả ra sao.
10. Tạo quy trình có thể lặp lại và kiểm chứng.

Release thành công không chỉ có nghĩa deployment command kết thúc với exit code bằng 0. Hệ thống phải hoạt động đúng theo mục tiêu, dữ liệu được bảo toàn và các thành phần liên quan ở trạng thái tương thích.

## 3. Phân biệt release, deployment và rollout

Ba khái niệm thường bị dùng lẫn:

| Khái niệm | Ý nghĩa |
|---|---|
| Release | Tạo và công bố một phiên bản có thể sử dụng |
| Deployment | Đưa artifact và cấu hình vào một môi trường |
| Rollout | Mở rộng việc sử dụng phiên bản mới theo từng nhóm hoặc tỷ lệ |
| Rollback | Quay lại phiên bản hoặc trạng thái vận hành trước đó |
| Roll forward | Sửa lỗi bằng một release mới hơn thay vì quay lại |

Một artifact có thể đã được release nhưng chưa deploy vào production. Một deployment có thể chỉ cập nhật một canary instance. Rollout có thể tiếp tục nhiều giờ sau khi release đã được công bố.

Tách các khái niệm giúp xác định chính xác điểm cần kiểm soát và bằng chứng cần lưu.

## 4. Release unit và compatibility boundary

Trước khi phát hành, cần xác định release unit gồm những thành phần nào:

- Compiler distribution.
- Runtime image hoặc package.
- Language server và plugin.
- Standard library.
- DSL source hoặc compiled artifact.
- Schema migration.
- Configuration và deployment manifest.
- Connector hoặc adapter.

Các thành phần không nhất thiết phải có cùng số version. Một project có thể dùng compiler 4.2, language version 3, artifact format 2 và runtime 5.0.

### 4.1. Compatibility matrix

Compatibility matrix quy định tổ hợp được hỗ trợ:

| Compiler | Language version | Artifact format | Runtime |
|---|---|---|---|
| 4.2 | 2, 3 | 2 | 4.8, 5.0 |
| 5.0 | 3, 4 | 3 | 5.0, 5.1 |

Bảng trên chỉ là ví dụ. Matrix thực tế cần nêu rõ minor/patch range, platform, ABI và capability nếu chúng ảnh hưởng compatibility.

### 4.2. Compatibility check

Pipeline cần xác minh manifest của project với matrix. Nếu compiler tạo artifact format mà runtime đích không hỗ trợ, release phải bị chặn trước deployment.

Không nên suy luận compatibility từ số version hoặc giả định rằng runtime mới luôn hỗ trợ mọi artifact cũ.

## 5. Versioning và release channel

Một dự án DSL có thể sử dụng Semantic Versioning hoặc chính sách version riêng.

Với SemVer:

- MAJOR biểu thị thay đổi không tương thích.
- MINOR bổ sung tính năng tương thích ngược.
- PATCH sửa lỗi tương thích.

Release channel có thể gồm:

- Development snapshot.
- Alpha hoặc preview.
- Beta.
- Release candidate (RC).
- Stable hoặc general availability.
- Long-term support (LTS).

Mỗi channel cần nêu mục đích, mức ổn định, support window và cách nâng cấp.

### 5.1. Language version độc lập với compiler version

Compiler mới có thể hỗ trợ nhiều language version. Source nên khai báo language version để semantics không âm thầm thay đổi khi compiler được nâng cấp.

Ví dụ:

~~~yaml
project:
  compiler: 5.0.2
  languageVersion: 3
  artifactFormat: 3
  runtime: 5.1.0
~~~

### 5.2. Release notes

Release notes nên mô tả:

- Tính năng mới.
- Bug fix.
- Semantic changes.
- Deprecated và removed API.
- Compatibility changes.
- Security fixes.
- Migration instructions.
- Known issues.
- Runtime và platform support.

Một thay đổi behavior có thể ảnh hưởng chương trình cũ dù source vẫn compile. Vì vậy, release notes phải nêu thay đổi semantics chứ không chỉ liệt kê API mới.

## 6. Release pipeline

Một pipeline release điển hình:

~~~mermaid
flowchart TD
    A["Source revision"] --> B["Build and resolve dependencies"]
    B --> C["Unit and conformance tests"]
    C --> D["Compatibility and security checks"]
    D --> E["Package immutable artifacts"]
    E --> F["Sign and record provenance"]
    F --> G["Deploy to staging"]
    G --> H["Integration and acceptance tests"]
    H --> I["Promote artifact to production"]
    I --> J["Observe rollout"]
    J --> K["Complete or rollback"]
~~~

Các bước quan trọng:

1. Chọn source revision đã được review.
2. Build với toolchain và dependency được pin.
3. Chạy unit, integration và conformance tests.
4. Kiểm tra compatibility matrix.
5. Quét dependency và artifact theo policy.
6. Tạo package và checksum.
7. Ký artifact hoặc tạo attestation khi cần.
8. Lưu manifest và provenance.
9. Triển khai staging.
10. Kiểm tra health, behavior và migration.
11. Promote artifact đã kiểm chứng tới production.
12. Theo dõi rollout và ghi kết quả.

### 6.1. Build một lần, promote cùng artifact

Nên build artifact một lần từ source revision đã xác định rồi promote chính artifact đó qua staging và production. Nếu build lại ở mỗi môi trường, dependency resolution, timestamp hoặc toolchain có thể làm nội dung khác nhau.

Configuration riêng của môi trường được inject qua deployment configuration hoặc secret manager, không cần rebuild application artifact.

### 6.2. Immutable artifact

Sau khi phát hành, artifact nên được coi là immutable. Không sửa nội dung tại chỗ dưới cùng version hoặc tag. Nếu cần thay đổi, tạo artifact mới với identity mới.

Điều này giúp biết chính xác binary nào đang chạy và hỗ trợ rollback.

## 7. Release manifest và provenance

Release manifest ghi lại thành phần của một release:

~~~yaml
release:
  name: dsl-platform
  version: 5.0.2
  sourceRevision: 7f3a91c
  languageVersion: 3
  compilerVersion: 5.0.2
  runtimeVersion: 5.1.0
  artifactFormat: 3
  artifacts:
    - name: compiler
      digest: sha256:...
    - name: runtime
      digest: sha256:...
    - name: standard-library
      digest: sha256:...
~~~

Manifest giúp deployment xác minh đúng tổ hợp và hỗ trợ audit. Provenance bổ sung thông tin về source, builder, toolchain, dependency và quy trình tạo artifact.

### 7.1. Checksum và signature

Checksum phát hiện nội dung artifact bị thay đổi. Signature giúp xác minh artifact đến từ publisher hoặc signing identity được tin cậy.

Checksum không tự chứng minh artifact an toàn; nó chỉ xác nhận nội dung khớp với digest đã biết. Signature cũng cần kiểm tra trust chain và key lifecycle.

### 7.2. SBOM

Software Bill of Materials liệt kê dependency trong artifact. SBOM hỗ trợ tìm package bị ảnh hưởng khi có security advisory và đánh giá rủi ro chuỗi cung ứng.

## 8. Release candidate và staging

Release candidate là bản build dự kiến phát hành nếu không còn lỗi chặn. Staging mô phỏng production đủ gần để kiểm tra integration và deployment.

Staging nên xác minh:

- Artifact load và startup thành công.
- Compiler/runtime compatibility.
- Schema migration.
- Plugin và connector integration.
- Authentication và authorization.
- Query và workflow behavior.
- Resource limits và performance.
- Backup và restore procedure.
- Monitoring, alert và rollback path.

Dữ liệu staging nên được kiểm soát và tránh sử dụng dữ liệu cá nhân production nếu không cần thiết.

### 8.1. Environment parity

Staging và production nên dùng cùng loại artifact, runtime family, configuration structure và deployment mechanism. Khác biệt về scale hoặc secret có thể được cấu hình, nhưng cần được ghi rõ.

### 8.2. Smoke test

Smoke test là nhóm kiểm tra ngắn sau deployment:

- Service health endpoint.
- Load compiler/runtime.
- Compile một DSL sample.
- Thực thi một query hoặc workflow an toàn.
- Kiểm tra kết nối dependency.
- Xác nhận version đang chạy.

Smoke test không thay thế integration hoặc acceptance tests.

## 9. Các chiến lược rollout

Không phải lúc nào cũng nên thay toàn bộ instance cùng lúc. Có thể chọn chiến lược rollout theo mức rủi ro và khả năng chịu gián đoạn.

### 9.1. Rolling deployment

Thay từng instance hoặc nhóm instance theo đợt:

~~~text
Version A: [A] [A] [A] [A]
Step 1:    [B] [A] [A] [A]
Step 2:    [B] [B] [A] [A]
Step 3:    [B] [B] [B] [A]
Complete:  [B] [B] [B] [B]
~~~

Ưu điểm:

- Không cần nhân đôi toàn bộ capacity.
- Có thể duy trì service trong quá trình nâng cấp.
- Dễ dừng rollout khi phát hiện lỗi.

Đánh đổi:

- Hai version có thể chạy đồng thời.
- Message và artifact phải tương thích giữa các version.
- Session hoặc workflow state cần được xử lý đúng.

### 9.2. Blue-green deployment

Blue-green duy trì hai môi trường:

- Blue: phiên bản đang phục vụ.
- Green: phiên bản mới đã được deploy và kiểm tra.

Sau khi green đạt điều kiện, traffic được chuyển sang green. Nếu có lỗi, traffic có thể chuyển lại blue.

Ưu điểm là chuyển traffic nhanh và rollback tương đối rõ. Đánh đổi là cần capacity cho hai môi trường và phải quản lý data/schema tương thích trong giai đoạn chuyển đổi.

### 9.3. Canary release

Canary đưa phiên bản mới tới một tỷ lệ traffic hoặc một nhóm người dùng nhỏ:

~~~text
Initial:  99% old / 1% new
Stage 2:  90% old / 10% new
Stage 3:  50% old / 50% new
Complete: 0% old / 100% new
~~~

Tỷ lệ là ví dụ. Canary cần traffic đại diện và metric đủ nhạy để phát hiện regression. Nếu nhóm canary chỉ có workload rất nhỏ hoặc khác biệt, kết quả không đại diện cho toàn hệ thống.

### 9.4. Feature flag

Feature flag cho phép bật tính năng mới theo tenant, user hoặc environment mà không cần deploy binary mới.

Flag cần:

- Owner.
- Default state.
- Scope.
- Expiry hoặc review date.
- Audit change.
- Rollback action.

Feature flag không thay thế versioning. Code mới vẫn được deploy, nhưng behavior chỉ được kích hoạt khi flag bật.

## 10. Release gate và tiêu chí tiếp tục rollout

Release gate là điều kiện cần đạt trước khi chuyển sang giai đoạn tiếp theo.

Ví dụ:

| Gate | Bằng chứng |
|---|---|
| Build | Artifact digest và source revision |
| Test | Unit, conformance và integration result |
| Compatibility | Matrix check pass |
| Security | Dependency scan và policy checks |
| Staging | Smoke và acceptance tests |
| Canary | Error rate, latency và saturation trong ngưỡng |
| Completion | Toàn bộ instance chạy đúng release identity |

### 10.1. Health metrics

Theo dõi:

- Request success/error rate.
- Latency p50/p95/p99.
- CPU, memory và GC.
- Queue depth và worker saturation.
- Database connection và query latency.
- Workflow failure/retry rate.
- Compile failure rate.
- Plugin crash hoặc language server error.
- Business metric quan trọng.

### 10.2. Abort condition

Trước rollout cần xác định điều kiện dừng:

- Error rate tăng vượt threshold.
- Latency hoặc resource usage vượt budget.
- Data integrity check thất bại.
- Workflow side effect bị lặp.
- Security policy không được áp dụng.
- Health check không ổn định.

Ngưỡng phải phù hợp baseline và mức rủi ro của dịch vụ. Không nên đợi sự cố lớn mới quyết định khi nào dừng rollout.

## 11. Database và schema migration khi release

Schema migration là một trong những nguyên nhân khiến rollback khó. Application version cũ có thể không đọc được schema đã bị thay đổi bởi version mới.

Các thay đổi schema:

- Thêm hoặc xóa field.
- Đổi type.
- Thêm constraint.
- Đổi index.
- Thay quan hệ.
- Đổi enum hoặc status.
- Chuyển đổi dữ liệu.

### 11.1. Expand-and-contract

Một quy trình phổ biến:

1. Expand: thêm field hoặc cấu trúc mới mà code cũ vẫn hoạt động.
2. Deploy code có thể đọc cả schema cũ và mới.
3. Migrate dữ liệu theo batch và có checkpoint.
4. Chuyển writer sang cấu trúc mới.
5. Xác minh không còn consumer dùng cấu trúc cũ.
6. Contract: xóa cấu trúc cũ trong release sau.

Ví dụ, đổi field customerName thành displayName có thể thực hiện qua giai đoạn thêm displayName, dual-read/dual-write có kiểm soát, backfill, chuyển consumer và cuối cùng loại customerName.

### 11.2. Backward-compatible migration

Migration tương thích ngược cho phép code cũ và mới cùng hoạt động trong giai đoạn rollout. Điều này đặc biệt quan trọng với rolling deployment.

### 11.3. Migration có tính phá hủy

Drop column, thay kiểu không tương thích hoặc xóa dữ liệu có thể không rollback được. Những thao tác này cần backup, xác minh, thời gian chờ và release riêng khi phù hợp.

### 11.4. Data migration checkpoint

Migration lớn nên ghi tiến độ, số record xử lý, lỗi và checkpoint để có thể tiếp tục sau interruption. Cần có idempotency hoặc cơ chế tránh chuyển đổi cùng record nhiều lần.

## 12. Rollback application và rollback data

Rollback application đưa binary hoặc configuration về version trước. Rollback data đưa database hoặc persistent state về trạng thái trước.

Hai hoạt động này không tương đương:

- Binary cũ có thể không hiểu schema mới.
- Database rollback có thể xóa dữ liệu được ghi sau deployment.
- Workflow state có thể đã chuyển qua nhiều bước.
- External side effect không thể tự động đảo ngược.

Trước release cần xác định rollback scope:

1. Chỉ rollback traffic hoặc application artifact?
2. Có cần rollback configuration không?
3. Schema có giữ ở trạng thái tương thích không?
4. Có cần restore backup không?
5. Có external action nào cần compensation?

### 12.1. Ưu tiên roll forward khi data không thể rollback an toàn

Nếu schema hoặc dữ liệu đã thay đổi không thể đảo ngược, sửa lỗi bằng một release mới hơn có thể an toàn hơn restore database cũ.

Roll forward cần có patch nhanh, test tập trung và khả năng triển khai có kiểm soát.

### 12.2. Restore từ backup

Restore database có thể làm mất dữ liệu phát sinh sau backup. Cần xác định recovery point objective (RPO), recovery time objective (RTO), log replay và cách xử lý giao dịch đang diễn ra.

Không nên coi backup là bằng chứng có thể phục hồi cho tới khi đã thử restore.

## 13. Rollback plan

Một rollback plan cần được chuẩn bị trước khi deployment:

- Trigger rollback.
- Version ổn định gần nhất.
- Artifact identity và digest.
- Lệnh hoặc quy trình chuyển traffic.
- Configuration tương thích.
- Schema compatibility.
- Cách xử lý session và workflow đang chạy.
- Data recovery hoặc compensation.
- Người chịu trách nhiệm và kênh phối hợp.
- Smoke test sau rollback.

### 13.1. Rollback decision

Không phải mọi lỗi đều cần rollback. Một lỗi nhỏ có thể được xử lý bằng feature flag hoặc config change. Lỗi gây data corruption, security breach hoặc ảnh hưởng diện rộng có thể yêu cầu dừng traffic và rollback ngay.

Quyết định cần dựa trên impact, khả năng khắc phục, reversibility và nguy cơ làm tình hình xấu hơn.

### 13.2. Rollback rehearsal

Thực hành rollback trong staging hoặc môi trường thử nghiệm để đo thời gian và phát hiện bước thiếu. Một runbook chưa từng thực hiện có thể chứa giả định sai.

## 14. Rollback trong rolling và blue-green deployment

### 14.1. Rolling rollback

Có thể thay các instance mới bằng image cũ theo từng đợt. Tuy nhiên, cần bảo đảm version cũ tương thích với database và message đã được version mới tạo ra.

### 14.2. Blue-green switchback

Nếu blue vẫn được giữ nguyên và schema tương thích, traffic có thể chuyển lại blue. Nhưng nếu green đã ghi data format mà blue không đọc được, switchback có thể gây lỗi.

### 14.3. Canary abort

Canary có thể dừng tăng traffic và chuyển nhóm thử nghiệm về version cũ. Cần xác định cách xử lý request hoặc workflow đã bắt đầu trên version mới.

## 15. Workflow và job đang chạy

Workflow DSL thường tạo instance kéo dài qua nhiều phút, ngày hoặc tháng. Khi release runtime hoặc workflow definition mới, cần xác định instance cũ tiếp tục theo semantics nào.

Các chiến lược:

- Pin instance vào definition version đã khởi chạy.
- Chỉ instance mới dùng definition mới.
- Migrate instance ở trạng thái an toàn.
- Dừng instance và chạy compensation.

### 15.1. Definition version

Mỗi workflow instance nên lưu definition version, artifact identity và runtime contract cần thiết. Điều này giúp replay và debugging đúng version.

### 15.2. In-flight compatibility

Runtime mới có thể cần hỗ trợ state format cũ. Nếu không, cần migration state hoặc giữ worker/runtime cũ cho instance cũ tới khi hoàn tất.

### 15.3. Side effects

Rollback binary không đảo ngược payment, email, shipment hoặc API call đã hoàn tất. Workflow cần idempotency, compensation và audit để xử lý các hành động đã xảy ra.

### 15.4. Pause và drain

Trước khi dừng worker cũ, có thể ngừng nhận task mới và cho task đang chạy hoàn tất trong deadline. Với task dài, cần checkpoint hoặc handoff an toàn.

## 16. Artifact, package và cache khi rollback

Artifact rollback cần xác định đúng:

- Compiler/runtime package.
- DSL bundle.
- Plugin.
- Dependency lockfile.
- Configuration snapshot.
- Schema hoặc migration version.

Registry nên giữ artifact immutable theo retention policy. Không nên ghi đè tag release cũ bằng nội dung mới.

Cache cũng cần được xem xét:

- Compiled plan cache.
- Query result cache.
- Schema metadata cache.
- Plugin cache.

Sau rollback, cache được tạo bởi version mới có thể không tương thích. Cần version cache key hoặc invalidate có kiểm soát.

## 17. Configuration và secret compatibility

Configuration có thể thay đổi tên key, default hoặc semantics giữa các release.

Ví dụ:

~~~yaml
runtime:
  executionTimeoutSeconds: 30
~~~

Nếu version mới đổi default thành 10 giây, behavior có thể thay đổi dù configuration không đổi.

Release cần:

- Version hóa schema configuration.
- Validate config trước rollout.
- Nêu rõ default changes.
- Hỗ trợ alias hoặc migration cho key deprecated.
- Giữ secret ngoài artifact và source control.
- Đảm bảo rollback version có thể đọc configuration hiện tại.

## 18. Release cho compiler, runtime và plugin

Mỗi loại artifact có release concern riêng:

### 18.1. Compiler

- Language version support.
- Source compatibility.
- Diagnostic changes.
- Artifact format.
- Reproducible build.
- Compiler regression corpus.

### 18.2. Runtime

- Artifact compatibility.
- ABI và standard library.
- Performance regression.
- Resource behavior.
- State persistence.
- Security policy.

### 18.3. Plugin và language server

- IDE compatibility.
- LSP capability.
- Plugin API version.
- Dependency và permission.
- Formatter stability.
- Diagnostic parity với compiler.

Có thể phát hành các thành phần theo nhịp khác nhau, nhưng compatibility matrix và release manifest phải cho biết tổ hợp nào được hỗ trợ.

## 19. Security và supply-chain trong release

Release pipeline có quyền truy cập source, signing key, package registry và deployment credential. Vì vậy, pipeline cũng là một phần của security boundary.

Kiểm soát nên gồm:

- Protected source branch và review.
- Dependency pinning và checksum.
- Isolated build runner.
- Secret manager cho credential.
- Artifact signing.
- Provenance và SBOM.
- Registry access control.
- Deployment identity có least privilege.
- Audit trail cho release action.

### 19.1. Signing key

Signing key cần được bảo vệ, giới hạn quyền sử dụng và có quy trình rotation/revocation. Không lưu private key trong source hoặc artifact.

### 19.2. Artifact verification

Runtime hoặc deployment system nên xác minh digest/signature theo policy trước khi load artifact. Nếu verification thất bại, không tiếp tục thực thi.

### 19.3. Rollback và vulnerability

Version cũ có thể chứa lỗ hổng bảo mật đã biết. Rollback về version đó cần được đánh giá theo rủi ro; đôi khi cần hotfix hoặc roll forward thay vì quay lại bản dễ bị khai thác.

## 20. Observability sau release

Sau deployment, cần biết version nào đang chạy và behavior có thay đổi không.

Telemetry hữu ích:

- Release ID và artifact digest.
- Compiler/runtime version.
- Language và artifact format version.
- Deployment environment.
- Error rate và exception type.
- Latency và throughput.
- Resource usage.
- Migration progress.
- Workflow state và retry.
- Business outcome.

### 20.1. Correlation

Log, trace và metric nên có release identity hoặc deployment revision để so sánh trước và sau rollout.

### 20.2. Business metrics

Một hệ thống có thể health check pass nhưng kết quả nghiệp vụ sai. Theo dõi metric như tỷ lệ đơn được xử lý, query result count hoặc workflow completion để phát hiện semantic regression.

### 20.3. Alert

Alert cần gắn với threshold và owner. Tránh tạo quá nhiều cảnh báo không hành động được. Release dashboard nên hiển thị version, rollout progress và abort condition.

## 21. Release runbook

Runbook mô tả các bước vận hành cụ thể:

~~~text
Release:
  1. Verify source revision and release manifest.
  2. Verify artifact digest and signature.
  3. Confirm compatibility matrix.
  4. Confirm backup and migration readiness.
  5. Deploy to staging.
  6. Run smoke and acceptance tests.
  7. Start canary rollout.
  8. Observe release metrics for the agreed window.
  9. Continue rollout if gates pass.
  10. Stop or rollback if abort condition is reached.
  11. Record final deployment identity and result.
~~~

Runbook cần ghi:

- Preconditions.
- Commands hoặc thao tác chính xác.
- Expected result.
- Timeout.
- Failure path.
- Rollback path.
- Owner và escalation contact.

## 22. Kiểm thử release và rollback

Release testing nên bao gồm:

- Build và package verification.
- Compatibility matrix.
- Conformance và regression tests.
- Security scan.
- Staging smoke test.
- Migration test.
- Deployment integration.
- Canary/health checks.
- Rollback rehearsal.

### 22.1. Rollback test

Một rollback test có thể:

1. Deploy version A.
2. Ghi lại artifact, schema và config state.
3. Deploy version B.
4. Tạo dữ liệu và workflow state bằng B.
5. Chuyển traffic về A.
6. Xác minh A đọc được state cần thiết.
7. Kiểm tra business invariant.
8. Đo thời gian phục hồi.

Nếu A không đọc được dữ liệu B đã ghi, cần thay đổi migration strategy hoặc chọn roll-forward recovery.

### 22.2. Fault injection

Có thể thử lỗi network, worker crash, migration interruption hoặc dependency unavailable trong môi trường thử nghiệm để xác nhận deployment và recovery behavior.

### 22.3. Restore test

Thử restore backup và replay log. Xác nhận dữ liệu, schema, artifact reference và workflow state có thể được phục hồi theo RPO/RTO đã đặt.

## 23. Release decision và go/no-go

Trước khi rollout rộng, nhóm có thể tổ chức go/no-go dựa trên:

- Test gates.
- Compatibility.
- Security findings.
- Migration readiness.
- Capacity.
- Rollback readiness.
- Known issues.
- Owner và support coverage.

Go/no-go không nên chỉ dựa trên cảm nhận. Cần chỉ ra evidence và các rủi ro đã chấp nhận.

Nếu một gate không đạt, quyết định có thể là:

- Dừng release.
- Phát hành với feature flag tắt.
- Giới hạn rollout cho một nhóm.
- Sửa và tạo release candidate mới.
- Chấp nhận rủi ro có điều kiện với owner và expiry.

## 24. Release record và audit

Sau release, lưu:

- Release version.
- Source revision.
- Artifact digest.
- Compiler/runtime versions.
- Dependency lockfile identity.
- SBOM/provenance reference.
- Test result.
- Migration version.
- Deployment target.
- Rollout timeline.
- Operator/approval identity theo policy.
- Incident hoặc rollback record nếu có.

Release record giúp điều tra lỗi, tái lập build và biết artifact nào cần thu hồi nếu phát hiện vulnerability.

## 25. Những lỗi thường gặp

### Rebuild artifact ở mỗi môi trường

Staging và production có thể chạy nội dung khác nhau. Build một lần và promote cùng artifact.

### Dùng tag mutable

Tag release bị ghi đè khiến không biết binary nào thực sự được triển khai. Dùng immutable artifact identity và digest.

### Chỉ rollback application

Schema hoặc data đã thay đổi khiến version cũ không hoạt động. Lập kế hoạch tương thích schema và workflow trước release.

### Không kiểm tra workflow đang chạy

Instance cũ có thể gặp runtime mới hoặc state format không tương thích. Version hóa definition và kiểm thử in-flight execution.

### Không có abort condition

Rollout tiếp tục dù error rate hoặc latency tăng. Định nghĩa threshold trước khi bắt đầu.

### Xem health check là đủ

Service trả lời HTTP 200 nhưng business result sai. Theo dõi semantic và business metrics.

### Rollback không được diễn tập

Runbook có thể thiếu bước hoặc cần quyền không sẵn có. Thực hành trong môi trường thử nghiệm.

### Restore backup mà không tính dữ liệu mới

Restore có thể xóa giao dịch hợp lệ sau backup. Đánh giá RPO, log replay và compensation.

### Rollback về bản dễ bị tấn công

Version cũ có vulnerability đã biết. Đánh giá security risk và cân nhắc roll forward.

### Thiếu release identity

Không thể liên kết incident với artifact cụ thể. Gắn release ID và digest vào telemetry.

## 26. Quy trình phát hành và rollback

Một quy trình tổng thể:

1. **Xác định release scope.** Compiler, runtime, language, artifact, schema và plugin nào thay đổi?
2. **Chốt version và support matrix.** Xác định các tổ hợp tương thích.
3. **Build immutable artifact.** Pin source, toolchain và dependency.
4. **Chạy release tests.** Conformance, regression, security và compatibility.
5. **Tạo manifest và provenance.** Ghi digest, version và nguồn build.
6. **Triển khai staging.** Kiểm tra integration và migration.
7. **Chuẩn bị rollback.** Xác định artifact cũ, schema strategy và recovery path.
8. **Bắt đầu rollout.** Canary, rolling hoặc blue-green theo rủi ro.
9. **Theo dõi gates.** Health, business, latency và resource metrics.
10. **Tiếp tục hoặc dừng.** Đáp ứng abort condition thì ngừng rollout.
11. **Rollback hoặc roll forward.** Chọn phương án không làm mất dữ liệu hoặc tăng rủi ro.
12. **Xác minh trạng thái cuối.** Smoke test, business invariant và version identity.
13. **Ghi release record.** Lưu kết quả, incident và action item.

## 27. Ví dụ end-to-end: phát hành compiler và runtime mới

Giả sử hệ thống đang dùng compiler 4.2, runtime 5.0, language version 3 và artifact format 2. Release mới gồm compiler 5.0, runtime 5.1 và artifact format 3.

### 27.1. Compatibility planning

- Compiler 5.0 tiếp tục hỗ trợ language version 3.
- Runtime 5.1 hỗ trợ artifact format 2 và 3.
- Runtime 5.0 chỉ hỗ trợ format 2.
- Workflow instance hiện tại đang chạy trên runtime 5.0.

### 27.2. Build và verify

1. Build compiler/runtime từ source revision đã review.
2. Chạy conformance suite cho language version 3.
3. Compile source corpus và kiểm tra diagnostics.
4. Tạo artifact format 3.
5. Xác minh runtime 5.1 load artifact mới.
6. Xác minh runtime 5.1 vẫn load artifact format 2.
7. Ký artifact và tạo release manifest.

### 27.3. Deployment

1. Deploy runtime 5.1 vào staging.
2. Chạy artifact format 2 và 3.
3. Kiểm tra workflow instance cũ.
4. Deploy canary cho một nhóm worker.
5. Theo dõi error, latency, queue và workflow completion.
6. Tăng rollout nếu gates đạt.

### 27.4. Rollback scenario

Giả sử canary phát hiện lỗi trong xử lý một instruction mới. Runtime 5.1 bị dừng rollout.

- Nếu chưa có artifact format 3 hoặc state mới được ghi, có thể đưa worker về runtime 5.0.
- Nếu runtime 5.1 đã ghi state không tương thích, cần giữ worker mới cho các instance đó hoặc chạy state migration.
- Nếu có side effect ngoài hệ thống, phải kiểm tra idempotency và compensation.
- Sau khi rollback, chạy smoke test bằng artifact format 2 và xác minh workflow completion.

### 27.5. Release record

Ghi release ID, digest, số worker đã nâng cấp, thời điểm dừng rollout, lỗi phát hiện, trạng thái workflow và quyết định khắc phục. Khi sửa xong, tạo release candidate mới và chạy lại gates liên quan.

## 28. Mẫu release checklist

~~~markdown
# Release checklist

## Identity
- [ ] Source revision is fixed.
- [ ] Compiler/runtime versions are recorded.
- [ ] Artifact digests are recorded.
- [ ] Compatibility matrix passes.

## Verification
- [ ] Unit and conformance tests pass.
- [ ] Integration and acceptance tests pass.
- [ ] Security and dependency checks pass.
- [ ] Performance baseline is within agreed limits.

## Data and state
- [ ] Schema migration is reviewed.
- [ ] Backup/restore path is known.
- [ ] In-flight workflows are covered.
- [ ] External side effects have recovery strategy.

## Deployment
- [ ] Staging smoke test passes.
- [ ] Rollout strategy and abort conditions are defined.
- [ ] Monitoring and owners are available.
- [ ] Rollback or roll-forward runbook is ready.

## Completion
- [ ] Business invariants are verified.
- [ ] Release record is saved.
- [ ] Known issues and follow-up actions are recorded.
~~~

Checklist hỗ trợ điều phối nhưng không thay thế các test và quyết định theo bối cảnh.

## 29. Kết luận

Phát hành và rollback là hai phần của cùng một quy trình quản lý thay đổi. Release cần tạo artifact có identity rõ ràng, xác minh compatibility, chạy test, triển khai có kiểm soát và theo dõi behavior thực tế. Rollback cần xem xét application, configuration, schema, dữ liệu, artifact, cache và workflow đang chạy.

Với DSL, rủi ro thường nằm ở ranh giới giữa language version, compiler, artifact format và runtime. Một phiên bản mới có thể compile source thành công nhưng không tương thích với runtime cũ; một migration có thể thay đổi schema khiến binary trước đó không còn hoạt động; một workflow có thể đã thực hiện side effect không thể đảo ngược. Vì vậy, compatibility matrix, immutable artifact, manifest, migration strategy và rollback rehearsal là những phần quan trọng của release design.

Hãy chuẩn bị abort condition và recovery path trước rollout, dùng canary hoặc rolling deployment khi phù hợp, theo dõi cả technical metrics lẫn business invariants, và ghi lại release identity cùng kết quả. Khi rollback data không an toàn, roll forward bằng bản sửa có kiểm chứng có thể là lựa chọn phù hợp hơn. Quy trình được diễn tập và có bằng chứng giúp phát hành DSL có kiểm soát, phục hồi nhanh và bảo vệ các chương trình đang vận hành.
