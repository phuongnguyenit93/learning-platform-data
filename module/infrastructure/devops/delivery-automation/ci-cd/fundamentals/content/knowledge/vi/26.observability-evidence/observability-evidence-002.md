# Thu thập báo cáo kiểm thử, kết quả phân tích và thông tin triển khai

## Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích vai trò của bằng chứng trong việc quyết định một thay đổi có đủ điều kiện phát hành hay không.
- Phân biệt báo cáo kiểm thử, kết quả phân tích, telemetry vận hành và hồ sơ triển khai.
- Xác định dữ liệu cần thu thập từ từng job và từng giai đoạn của pipeline.
- Chọn định dạng báo cáo phù hợp và chuẩn hóa kết quả từ nhiều công cụ.
- Liên kết báo cáo với commit, workflow run, artifact digest, release và môi trường đích.
- Thiết kế quy trình tổng hợp bằng chứng từ các job chạy song song, kể cả khi một job thất bại hoặc không tạo được báo cáo.
- Bảo vệ tính toàn vẹn, nguồn gốc, khả năng truy cập và thời hạn lưu trữ của bằng chứng.
- Dùng evidence bundle để hỗ trợ quality gate, release approval, điều tra sự cố và audit.

## 1. Vì sao pipeline cần thu thập bằng chứng?

Một pipeline có thể kết thúc với trạng thái xanh, nhưng chỉ nhìn trạng thái tổng thể không đủ để hiểu điều gì đã được kiểm tra và artifact nào đã được tạo ra.

Ví dụ, một lần chạy có thể báo thành công dù:

- Một nhóm test bị bỏ qua do cấu hình sai.
- Báo cáo coverage không được tải lên.
- Công cụ phân tích bảo mật không chạy vì hết thời gian.
- Artifact được build từ commit khác với commit đã được kiểm thử.
- Deployment thành công ở một phần instance nhưng chưa hoàn tất rollout.
- Không có thông tin về cấu hình thực tế đã được áp dụng.

Bằng chứng giúp trả lời các câu hỏi cụ thể:

- Mã nguồn nào đã được kiểm thử?
- Những test suite nào đã chạy và kết quả ra sao?
- Có bao nhiêu test pass, fail, skipped hoặc error?
- Phân tích bảo mật và chất lượng đã kiểm tra phạm vi nào?
- Artifact nào được tạo từ lần build đó?
- Artifact có đúng là artifact đã được kiểm tra không?
- Ai hoặc workload nào đã triển khai?
- Deployment đã thay đổi môi trường nào, với cấu hình nào?
- Sau deploy, hệ thống có xác minh phiên bản và sức khỏe không?

Trong CI/CD, **evidence (bằng chứng)** là dữ liệu có cấu trúc hoặc tài liệu có thể kiểm tra, gắn với một đối tượng và một hoạt động cụ thể. Bằng chứng cần cho biết ai hoặc công cụ nào tạo ra nó, được tạo khi nào, áp dụng cho commit/artifact/environment nào và kết quả có ý nghĩa gì.

Bằng chứng không chỉ phục vụ dashboard. Nó là đầu vào của quality gate, quyết định phát hành, truy vết thay đổi, điều tra sự cố và chứng minh quy trình đã tuân thủ chính sách.

## 2. Phân biệt báo cáo, telemetry và hồ sơ triển khai

Các loại dữ liệu này thường được lưu gần nhau nhưng phục vụ mục đích khác nhau.

| Loại dữ liệu | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| Test report | Những kiểm thử nào đã chạy và kết quả ra sao? | JUnit XML, TRX, test summary |
| Coverage report | Mã nào được thực thi trong phạm vi kiểm thử? | JaCoCo XML, Cobertura, LCOV |
| Analysis report | Công cụ phát hiện vấn đề gì trong source, dependency hoặc image? | SARIF, SAST, DAST, dependency scan |
| Build evidence | Artifact được tạo như thế nào và từ đầu vào nào? | Build metadata, provenance, SBOM |
| Deployment record | Artifact và cấu hình nào được đưa đến môi trường nào? | Release manifest, deployment ID, config revision |
| Runtime telemetry | Hệ thống hoạt động thế nào sau deploy? | Metrics, logs, traces, alerts |
| Approval/audit record | Ai đã cho phép hoặc thực hiện hành động nào? | Approval event, audit log, change record |

**Báo cáo** thường mô tả kết quả của một lần thực thi có phạm vi xác định. **Telemetry** phản ánh trạng thái hoặc hành vi hệ thống theo thời gian. **Deployment record** mô tả một thay đổi đã được áp dụng lên môi trường.

Một dashboard có thể tổng hợp cả ba loại, nhưng không nên coi ảnh chụp dashboard là bằng chứng duy nhất. Cần lưu dữ liệu gốc hoặc bản xuất có cấu trúc, cùng metadata để truy vết.

## 3. Mô hình bằng chứng: đối tượng, hoạt động, kết quả và nguồn tạo

Một bằng chứng hữu ích cần gắn với một đối tượng cụ thể và một hoạt động có thể xác định.

Có thể dùng mô hình khái niệm:

- **Subject:** đối tượng được kiểm tra hoặc thay đổi, ví dụ commit, artifact digest, image hoặc environment.
- **Activity:** hoạt động đã diễn ra, ví dụ unit test, SAST scan, build, signing hoặc deploy.
- **Producer:** người, runner, tool hoặc workload identity tạo kết quả.
- **Timestamp:** thời điểm bắt đầu/kết thúc hoặc thời điểm tạo báo cáo.
- **Context:** workflow revision, run ID, parameters, tool version và phạm vi kiểm tra.
- **Result:** pass/fail, findings, metrics, trạng thái triển khai hoặc kết quả xác minh.
- **Integrity reference:** checksum, signature hoặc ID của bản lưu để phát hiện thay đổi.

~~~mermaid
flowchart LR
    S["Subject: commit / artifact / environment"] --> A["Activity: test / scan / build / deploy"]
    P["Producer: tool / runner / identity"] --> A
    C["Context: run ID / tool version / config"] --> A
    A --> R["Result: report / findings / status"]
    R --> I["Integrity: digest / signature / storage ID"]
    I --> G["Quality gate / approval / audit"]
~~~

Ví dụ, một file test report có thể ghi 120 test pass. Nhưng nếu không biết report thuộc commit nào, run nào, test suite nào và được tạo bởi tool version nào, giá trị truy vết của nó rất hạn chế.

Cần tránh các báo cáo chỉ có tên file chung như test-results.xml rồi ghi đè qua nhiều run. Mỗi report phải có định danh hoặc vị trí lưu gắn với pipeline run và attempt cụ thể.

## 4. Thu thập báo cáo kiểm thử

Test report cho biết những kiểm thử nào đã chạy, kết quả và thông tin lỗi. Đây là nguồn bằng chứng quan trọng cho quality gate.

Các nhóm kiểm thử thường gặp:

- Unit test.
- Component test.
- Integration test.
- Contract test.
- API test.
- End-to-end test.
- Smoke test.
- Performance/load test.
- Compatibility test.
- Migration hoặc data validation test.

Một test report nên chứa hoặc liên kết đến:

- Tên project/module và test suite.
- Test case hoặc nhóm test.
- Tổng số test.
- Số pass, fail, skipped, aborted và error.
- Thời gian thực thi.
- Failure message và stack trace phù hợp.
- Commit SHA và pipeline run ID.
- Runtime, OS, browser hoặc môi trường test.
- Phiên bản test framework.
- Link đến log chi tiết hoặc artifact liên quan.

Một số định dạng phổ biến:

| Định dạng | Mục đích thường gặp | Lưu ý |
|---|---|---|
| JUnit XML | Báo cáo test từ nhiều framework | Được nhiều CI server hỗ trợ |
| TRX | Kết quả test trong hệ sinh thái Microsoft | Có thể chứa test result và diagnostic |
| NUnit XML | Kết quả từ NUnit | Cần parser hoặc publisher tương thích |
| Allure results/report | Tổng hợp kết quả và lịch sử test | Cần lưu cả raw result và report đã render |
| JSON tùy công cụ | Kết quả có cấu trúc của framework | Nên có schema/version rõ ràng |

Định dạng được hỗ trợ tùy công cụ CI và test framework. Nếu pipeline dùng nhiều framework, có thể giữ báo cáo gốc rồi chuyển sang một mô hình tổng hợp chung.

Không nên chỉ lưu số test pass trong log console. Log có thể bị cắt, thay đổi format hoặc khó truy vấn. Hãy xuất report thành file có cấu trúc và publish như pipeline artifact.

## 5. Thu thập coverage và chất lượng kiểm thử

Coverage report bổ sung thông tin về phần mã được thực thi khi chạy test. Các loại thường gặp:

- Line coverage.
- Statement coverage.
- Branch coverage.
- Function/method coverage.
- Module hoặc package coverage.

Định dạng có thể gồm JaCoCo XML, Cobertura XML hoặc LCOV. Một số nền tảng hỗ trợ định dạng riêng.

Coverage cần được gắn với:

- Commit SHA.
- Build/test run.
- Source revision.
- Module hoặc package.
- Tool version.
- Phạm vi file được đưa vào và loại trừ.

Không nên so sánh hai con số coverage nếu phạm vi source khác nhau. Ví dụ một run loại trừ integration module, run khác đưa module đó vào; phần trăm có thể thay đổi mà không phản ánh chất lượng test thực sự.

Coverage cao không đồng nghĩa test tốt. Một dòng code có thể được thực thi nhưng assertion không kiểm tra hành vi. Vì vậy coverage là một tín hiệu, cần được kết hợp với test result, mutation testing hoặc review theo nhu cầu.

Khi tổng hợp coverage từ nhiều module, cần tránh cộng trung bình phần trăm một cách sai lệch. Nên tổng hợp số dòng/nhánh được cover và tổng số dòng/nhánh có thể cover theo cùng quy tắc, rồi tính tỷ lệ trên tổng.

## 6. Thu thập kết quả phân tích mã nguồn và bảo mật

Pipeline có thể chạy nhiều công cụ phân tích:

- Static Application Security Testing (SAST).
- Software Composition Analysis (SCA) hoặc dependency scanning.
- Secret scanning.
- License compliance.
- IaC scanning.
- Container/image scanning.
- Dynamic Application Security Testing (DAST).
- API security testing.
- Code quality và maintainability analysis.

Một kết quả phân tích cần cho biết:

- Công cụ và phiên bản.
- Loại phân tích.
- Source, artifact hoặc image digest được quét.
- Commit SHA và phạm vi file.
- Thời điểm scan.
- Rule set, policy hoặc database vulnerability version nếu có.
- Finding ID, rule ID và vị trí.
- Severity, confidence hoặc risk rating.
- Trạng thái: new, existing, suppressed, accepted hoặc resolved.
- Tham chiếu đến exception/waiver nếu có.

SARIF (Static Analysis Results Interchange Format) là một định dạng trao đổi kết quả phân tích tĩnh được nhiều công cụ hỗ trợ. Nó có thể mang thông tin tool, rule, result và vị trí trong source. Tuy nhiên, không phải mọi scanner đều xuất SARIF hoặc hỗ trợ đầy đủ mọi trường.

Đối với dependency scan, nên lưu thêm dependency manifest/lockfile hoặc SBOM liên quan để biết chính xác thành phần nào được đánh giá. Với image scan, cần gắn kết quả với image digest thay vì chỉ dùng tag.

Một báo cáo scan cần phân biệt rõ:

- Không tìm thấy finding.
- Scan hoàn tất và có finding.
- Scan không chạy.
- Scan chạy nhưng lỗi.
- Scan bị giới hạn phạm vi.
- Scan kết quả cũ hoặc không còn phù hợp với artifact hiện tại.

Không được diễn giải trạng thái “không có báo cáo” thành “không có lỗ hổng”.

## 7. Thu thập thông tin build và nguồn gốc artifact

Sau khi test và analysis đạt, pipeline tạo artifact. Bằng chứng build cần giúp truy ngược artifact về nguồn và quá trình tạo.

Thông tin nên thu thập:

- Repository và source commit.
- Branch/tag hoặc release reference.
- Workflow definition revision.
- Pipeline run ID và attempt.
- Builder/runner identity.
- Build tool và phiên bản compiler.
- Dependency lockfile hoặc dependency graph.
- Build parameters và target platform.
- Thời điểm build.
- Artifact name, version và digest.
- SBOM và provenance nếu chính sách yêu cầu.
- Signature hoặc attestation nếu có.

Artifact nên được định danh bằng digest bất biến. Tag có thể thuận tiện cho con người, nhưng không đủ để chứng minh nội dung nếu tag có thể bị ghi đè.

Cần phân biệt hai loại file:

- **Deployable artifact:** JAR, package, binary, container image hoặc bundle được triển khai.
- **Evidence artifact:** test report, scan report, coverage, build log, SBOM, provenance và deployment record.

Không gộp bằng chứng vào artifact runtime theo cách làm thay đổi nội dung cần được triển khai. Có thể lưu cả hai trong cùng release record hoặc evidence bundle, nhưng phải phân biệt rõ digest và vai trò.

## 8. Thu thập thông tin triển khai

Deployment record cho biết một artifact cụ thể đã được đưa đến môi trường nào, bằng cấu hình và chiến lược nào.

Các trường nên có:

| Trường | Ý nghĩa |
|---|---|
| Release ID | Định danh phát hành xuyên các môi trường |
| Deployment ID | Định danh một lần triển khai |
| Artifact digest | Nội dung thực tế được triển khai |
| Source commit | Commit tạo ra artifact |
| Workflow/template revision | Logic pipeline đã thực hiện |
| Environment ID | Môi trường đích |
| Config revision/fingerprint | Cấu hình được resolve và áp dụng |
| Migration version | Schema/data migration liên quan |
| Strategy | Rolling, canary, blue-green hoặc recreate |
| Actor/workload identity | Ai hoặc workload nào thực hiện |
| Approval/change reference | Quyết định và change record liên quan |
| Start/end time | Khoảng thời gian triển khai |
| Result | Success, failed, partial, cancelled hoặc rolled back |
| Verification | Kết quả health, smoke test và runtime check |

Một deployment command trả về exit code 0 chưa đủ chứng minh hệ thống đang chạy đúng artifact. Cần xác minh trạng thái thực tế từ môi trường đích:

- Image digest hoặc package version đang chạy.
- Replica/instance đã đạt trạng thái mong muốn.
- Config revision đã được áp dụng.
- Routing hoặc traffic shift đã hoàn tất.
- Health và smoke test đạt.
- Rollout không còn instance cũ ngoài chủ đích.
- Release ID được ghi nhận trong telemetry.

Nếu deployment thất bại một phần, record phải thể hiện trạng thái partial và tài nguyên đã thay đổi. Không ép mọi kết quả thành success/fail nếu điều đó che giấu trạng thái thực tế.

## 9. Liên kết bằng chứng bằng các định danh ổn định

Khi test, scan, build và deploy chạy ở nhiều job hoặc hệ thống, cần một tập định danh giúp nối các bằng chứng.

Các định danh hữu ích:

- Repository ID hoặc URL chuẩn.
- Commit SHA.
- Workflow revision.
- Pipeline run ID và attempt number.
- Artifact digest.
- SBOM digest.
- Provenance/attestation ID.
- Release ID.
- Deployment ID.
- Environment ID.
- Config revision.
- Correlation ID hoặc trace ID cho hoạt động runtime.

Một chuỗi liên kết điển hình:

~~~text
Repository + Commit SHA
        |
        v
Workflow Revision + Run ID
        |
        +---- Test Reports
        |
        +---- Analysis Reports
        |
        v
Build Artifact Digest
        |
        +---- SBOM / Provenance / Signature
        |
        v
Release ID
        |
        v
Deployment ID + Environment ID + Config Revision
        |
        v
Post-deploy Verification + Runtime Evidence
~~~

Không nên chỉ liên kết bằng branch name hoặc version label. Branch có thể thay đổi và tag có thể bị ghi đè. Commit SHA, digest và ID của từng lần chạy là những định danh phù hợp hơn để truy vết.

Nếu nhiều pipeline cùng tạo artifact hoặc downstream pipeline triển khai artifact, cần truyền artifact digest và release ID qua input/output có cấu trúc, không dựa vào việc tự tìm tag mới nhất.

## 10. Tổng hợp bằng chứng từ các job chạy song song

Một pipeline có thể có nhiều job kiểm thử và phân tích chạy song song. Mỗi job tạo một hoặc nhiều report artifact.

Ví dụ:

~~~mermaid
flowchart TD
    A["Source commit"] --> B["Pipeline run"]
    B --> C["Unit tests"]
    B --> D["Integration tests"]
    B --> E["Coverage"]
    B --> F["SAST / dependency scan"]
    C --> G["Evidence collector"]
    D --> G
    E --> G
    F --> G
    G --> H["Normalize and validate"]
    H --> I["Quality gate"]
    I --> J["Build / release evidence bundle"]
~~~

Evidence collector cần biết report nào là bắt buộc. Nếu một job không tạo report, collector phải phân biệt nguyên nhân:

- Job chưa chạy vì dependency.
- Job bị skip theo policy.
- Job thất bại trước khi xuất report.
- Upload report thất bại.
- Report không hợp lệ hoặc schema không hỗ trợ.
- Report bị thiếu do cấu hình.

Đối với gate bắt buộc, thiếu bằng chứng cần được xử lý như trạng thái không đạt hoặc không thể đánh giá, theo policy. Không tự động bỏ qua report chỉ vì pipeline vẫn có thể tiếp tục.

Khi các job chạy trên runner khác nhau, không giả định file nằm trong cùng workspace. Mỗi job cần upload report bằng artifact storage của CI hoặc kho lưu trữ chung, sau đó collector tải về theo run ID và job ID.

## 11. Chuẩn hóa dữ liệu mà vẫn giữ báo cáo gốc

Nhiều công cụ dùng format, tên severity và cách tính khác nhau. Một hệ thống tổng hợp có thể tạo mô hình dữ liệu chuẩn để so sánh và áp dụng policy.

Ví dụ các trạng thái test chuẩn:

- passed
- failed
- skipped
- error
- cancelled
- not_run
- unavailable

Ví dụ severity chuẩn cho finding:

- critical
- high
- medium
- low
- info
- unknown

Cần có mapping được quản lý phiên bản từ định dạng của công cụ sang mô hình chung. Không nên ép mọi trường của công cụ vào một schema quá nhỏ làm mất dữ liệu quan trọng.

Nên lưu cả:

1. Báo cáo gốc do công cụ tạo.
2. Bản đã parse/normalize.
3. Metadata về parser và schema version.
4. Lỗi hoặc cảnh báo khi parse.
5. Link đến log chi tiết.

Nếu parser không hiểu một trường hoặc report version mới, cần ghi rõ phần dữ liệu không thể xử lý. Không âm thầm bỏ qua findings.

## 12. Kiểm tra tính đầy đủ và hợp lệ của báo cáo

Một file tồn tại không có nghĩa report hợp lệ.

Collector cần kiểm tra:

- File có tồn tại và không rỗng.
- Định dạng có parse được.
- Schema/version có được hỗ trợ.
- Report thuộc đúng repository, commit và run.
- Thời gian report phù hợp với lần chạy hiện tại.
- Tool name và tool version có mặt.
- Phạm vi test/scan đúng với policy.
- Artifact digest khớp với đối tượng cần đánh giá.
- Số liệu tổng hợp nhất quán với chi tiết.
- Không có report trùng hoặc bị ghi đè.

Ví dụ, report từ run trước có thể vẫn còn trong workspace nếu job tái sử dụng runner. Nếu collector chỉ tìm file theo tên, nó có thể vô tình đọc report cũ. Nên tạo workspace sạch hoặc dùng đường dẫn artifact gắn run ID và attempt.

Cần xác định rõ các trạng thái:

| Trạng thái | Ý nghĩa | Cách xử lý |
|---|---|---|
| Valid | Report hợp lệ và đúng context | Đưa vào tổng hợp |
| Missing | Không tìm thấy report bắt buộc | Chặn hoặc chuyển trạng thái không thể đánh giá |
| Invalid | File tồn tại nhưng parse/schema lỗi | Chặn theo policy và ghi nguyên nhân |
| Stale | Report thuộc commit/run/artifact cũ | Không dùng cho release hiện tại |
| Partial | Chỉ một phần scope được kiểm tra | Đánh giá theo policy, không coi là full pass |
| Unavailable | Tool hoặc dịch vụ không thể cung cấp kết quả | Fail closed hoặc exception có phê duyệt |
| Optional skipped | Bước không bắt buộc được skip hợp lệ | Ghi nhận lý do, không ảnh hưởng gate bắt buộc |

## 13. Quality gate phải đọc bằng chứng có ngữ nghĩa

Quality gate không nên chỉ kiểm tra một job có trạng thái success. Nó cần đọc kết quả và xác định kết quả có đáp ứng policy không.

Ví dụ:

- Tất cả test bắt buộc đã chạy và không có failure.
- Không có critical finding chưa được xử lý.
- Coverage không giảm dưới ngưỡng đã thống nhất.
- Dependency scan có dữ liệu mới đủ freshness.
- Artifact digest có provenance hợp lệ.
- Approval gắn với đúng release và environment.
- Deployment verification xác nhận đúng artifact đang chạy.

Một gate cần lưu:

- Policy ID và policy version.
- Input evidence IDs.
- Kết quả từng điều kiện.
- Kết quả cuối: pass, fail, blocked hoặc exception.
- Lý do và finding liên quan.
- Actor phê duyệt exception nếu có.
- Thời điểm đánh giá.

Không nên hard-code threshold trong nhiều job khác nhau. Có thể quản lý policy tập trung hoặc versioned configuration, sau đó ghi lại policy version đã được áp dụng.

Exception cần có phạm vi, lý do, owner và thời hạn. Một waiver cho finding không nên biến thành bỏ qua toàn bộ scanner ở các lần chạy sau.

## 14. Gắn bằng chứng với artifact và release

Một evidence bundle là tập hợp các report và metadata liên quan đến một artifact hoặc release.

Một cấu trúc logic có thể như sau:

~~~text
release-evidence/
├── manifest.json
├── source/
│   └── revision.json
├── tests/
│   ├── junit-unit.xml
│   ├── junit-integration.xml
│   └── coverage.xml
├── analysis/
│   ├── sast.sarif
│   ├── dependency-report.json
│   ├── image-scan.json
│   └── sbom.json
├── build/
│   ├── build-metadata.json
│   └── provenance.json
├── deployment/
│   ├── staging-deployment.json
│   └── production-deployment.json
└── verification/
    ├── smoke-test.json
    └── post-deploy-health.json
~~~

Manifest có thể chứa:

- Release ID.
- Repository và commit SHA.
- Workflow revision và run ID.
- Artifact name/version/digest.
- Danh sách report cùng digest.
- Tool và schema version.
- Policy evaluation ID.
- Chữ ký hoặc attestation reference nếu được sử dụng.

Evidence bundle không nhất thiết là một file ZIP duy nhất. Có thể là một release record trong hệ thống quản lý phát hành, một tập artifact trong CI storage hoặc các object trong evidence store. Điều quan trọng là manifest liên kết chúng một cách ổn định và có thể kiểm tra.

Không sửa báo cáo gốc sau khi đã được dùng để quyết định release. Nếu cần thêm thông tin, tạo phiên bản mới và giữ liên kết đến bản trước.

## 15. Tính toàn vẹn và nguồn gốc của bằng chứng

Bằng chứng chỉ có giá trị khi có thể tin rằng nó thuộc đúng hoạt động và không bị thay đổi trái phép.

Các biện pháp:

- Lưu digest của từng report.
- Bảo vệ quyền ghi/xóa evidence store.
- Ghi producer identity và run context.
- Dùng immutable hoặc retention-locked storage cho bằng chứng quan trọng.
- Ký manifest hoặc attestation khi yêu cầu mức đảm bảo cao.
- Giữ audit log cho upload, download, replace và delete.
- Tách quyền tạo report khỏi quyền sửa policy hoặc approve release.
- Xác minh chữ ký và trust root trước khi dùng bằng chứng.

Checksum phát hiện nội dung thay đổi so với digest đã lưu, nhưng không chứng minh người tạo report là đáng tin. Chữ ký giúp xác minh chủ thể ký và tính toàn vẹn, nhưng vẫn cần tin cậy vào signer, builder và quy trình cấp key.

Không nên để job chạy mã không tin cậy tự tạo bằng chứng có thể được pipeline production coi là đáng tin. Cần kiểm soát identity và nguồn tạo.

## 16. Thu thập bằng chứng sau triển khai

Sau deploy, pipeline cần thu thập bằng chứng cho biết môi trường thực tế đã nhận đúng release và hoạt động theo yêu cầu.

Các kiểm tra thường gặp:

- Artifact digest đang chạy.
- Release ID hoặc version đang được expose.
- Config revision đã áp dụng.
- Số replica/instance healthy.
- Readiness và startup status.
- Smoke test hoặc critical user journey.
- Error rate và latency trong cửa sổ quan sát.
- Queue lag, restart count hoặc dependency failure.
- Kết quả traffic shift/canary nếu có.
- Kết quả rollback hoặc recovery nếu rollout không đạt.

Nên có một cửa sổ quan sát phù hợp với loại dịch vụ. Một health check thành công ngay sau deploy có thể chưa phát hiện lỗi chỉ xuất hiện khi có tải hoặc khi một background job chạy.

Nếu metric chưa đủ dữ liệu, kết quả nên là pending/insufficient evidence thay vì tự động pass. Cần xác định thời gian chờ tối đa và hành động khi không thể kết luận.

Deployment evidence nên lưu cả trạng thái mong muốn và trạng thái quan sát được. Ví dụ, pipeline yêu cầu image digest X nhưng cluster đang chạy digest Y; đây là drift cần được ghi nhận và xử lý.

## 17. Lưu trữ, retention và khả năng truy cập

Bằng chứng có giá trị khác nhau theo thời gian và mục đích.

Có thể phân loại:

- Raw logs và report tạm thời phục vụ debug.
- Test/scan report gắn với release.
- Artifact provenance và SBOM.
- Approval và deployment audit.
- Evidence phục vụ yêu cầu tuân thủ hoặc điều tra.

Retention policy cần xác định:

- Loại bằng chứng.
- Thời gian lưu.
- Nơi lưu.
- Người/role được đọc.
- Ai được xóa hoặc thay thế.
- Cách xử lý legal hold hoặc incident hold.
- Mức độ mã hóa và phân vùng dữ liệu.

Không nên lưu mọi log vô thời hạn. Điều đó làm tăng chi phí và rủi ro chứa thông tin nhạy cảm. Ngược lại, không nên xóa deployment evidence quá sớm nếu cần truy vết một phiên bản đang chạy.

Retention cần dựa trên nhu cầu vận hành, hợp đồng, pháp lý và chính sách của tổ chức. Không có một con số thời hạn phù hợp cho mọi loại report.

## 18. Bảo vệ dữ liệu nhạy cảm trong report

Test report, log và scan output đôi khi chứa:

- Email, số điện thoại hoặc dữ liệu khách hàng mẫu.
- Access token hoặc secret bị in ra.
- URL nội bộ và hostname.
- SQL statement hoặc request payload.
- Đường dẫn file và thông tin hệ thống.
- Chi tiết lỗ hổng chưa được công bố.

Cần:

- Dùng dữ liệu test giả lập hoặc đã ẩn danh.
- Mask secret trước khi ghi log.
- Không upload file environment hoặc credential vào evidence bundle.
- Phân quyền đọc report bảo mật và deployment.
- Mã hóa dữ liệu khi truyền và khi lưu.
- Có quy trình revoke/rotate secret nếu phát hiện lộ.
- Xác định thời hạn lưu đối với dữ liệu nhạy cảm.
- Kiểm tra nội dung report trước khi publish ra bên ngoài tổ chức.

Secret masking không bảo đảm mọi dạng dữ liệu đều được che. Tốt nhất là không đưa secret vào command output hoặc test fixture ngay từ đầu.

## 19. Ví dụ pipeline thu thập bằng chứng

YAML sau minh họa logic tổng quát:

~~~yaml
pipeline:
  context:
    source_commit: required
    run_id: required
    workflow_revision: required

  jobs:
    unit_tests:
      output:
        - junit-unit.xml

    integration_tests:
      output:
        - junit-integration.xml

    coverage:
      output:
        - coverage.xml

    security_analysis:
      output:
        - sast.sarif
        - dependency-report.json

    build:
      needs:
        - unit_tests
        - integration_tests
        - security_analysis
      output:
        - artifact_digest
        - build-metadata.json
        - provenance.json

    collect_evidence:
      needs:
        - unit_tests
        - integration_tests
        - coverage
        - security_analysis
        - build
      steps:
        - download_reports_by_run_id
        - validate_report_schema_and_context
        - normalize_results
        - calculate_report_digests
        - create_evidence_manifest
        - publish_evidence_bundle

    quality_gate:
      needs:
        - collect_evidence
      input:
        - evidence_manifest
        - policy_revision
      output:
        - gate_decision

    deploy:
      needs:
        - quality_gate
      condition: gate_decision == "pass"
      output:
        - deployment_record.json
        - post_deploy_verification.json
~~~

Trong thực tế, nếu build có thể chạy song song với test, DAG có thể cho phép điều đó. Điều kiện là artifact được tạo từ cùng source revision và quality gate chờ đủ bằng chứng bắt buộc trước khi cho phép deploy.

Collector không nên chỉ tải file có tên cố định. Cần truy vấn theo run ID, job ID và attempt, sau đó xác minh commit/artifact context.

## 20. Những trạng thái báo cáo cần phân biệt

Một pipeline cần phân biệt rõ kết quả của công cụ với kết quả tổng hợp.

Ví dụ:

| Report status | Gate interpretation |
|---|---|
| Completed, no findings | Có thể pass nếu đáp ứng policy |
| Completed, findings present | Đánh giá severity và policy |
| Failed | Không đạt hoặc cần điều tra |
| Skipped by approved policy | Ghi nhận ngoại lệ có phạm vi |
| Skipped unexpectedly | Blocked hoặc fail |
| Missing | Không thể đánh giá |
| Invalid schema | Không thể đánh giá |
| Stale | Không được dùng cho release hiện tại |
| Partial scope | Chỉ chấp nhận nếu policy cho phép |
| Tool unavailable | Blocked hoặc exception có phê duyệt |

Không được gom mọi trạng thái khác success thành một nhãn duy nhất nếu điều đó làm mất thông tin. Ví dụ test fail khác với scanner không khởi động; cả hai có thể chặn release nhưng cần cách xử lý khác nhau.

## 21. Những anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách cải thiện |
|---|---|---|
| Chỉ xem trạng thái pipeline xanh | Không biết test/scan nào thực sự chạy | Publish report có cấu trúc |
| Chỉ lưu log console | Khó parse và có thể bị cắt | Lưu report gốc và metadata |
| Report dùng tên file chung giữa nhiều run | Đọc nhầm kết quả cũ | Gắn path với run ID và attempt |
| Thiếu report vẫn coi là pass | Bỏ qua kiểm tra bắt buộc | Phân biệt missing/unavailable và fail gate |
| Chỉ lưu phần trăm coverage | Không biết phạm vi đo | Lưu raw coverage và source revision |
| Scan report không gắn artifact digest | Kết quả có thể thuộc image khác | Gắn digest và scan context |
| Dùng tag mutable để liên kết release | Truy vết không ổn định | Dùng commit SHA và artifact digest |
| Sửa report sau khi release | Mất lịch sử quyết định | Lưu phiên bản mới, giữ bản cũ |
| Dashboard là bằng chứng duy nhất | Không tái lập hoặc kiểm tra được | Lưu evidence record có cấu trúc |
| Lưu log vô thời hạn | Chi phí và rủi ro dữ liệu nhạy cảm | Retention theo loại evidence |
| Upload report chứa secret | Rò rỉ credential | Mask, kiểm tra và giới hạn quyền |
| Deployment command success được coi là deploy thành công | Có thể còn instance cũ hoặc rollout partial | Xác minh trạng thái thực tế |

## 22. Checklist thu thập và quản lý bằng chứng

Trước khi đưa pipeline vào vận hành, hãy xác nhận:

- [ ] Có danh sách report bắt buộc theo loại pipeline và release.
- [ ] Mỗi report gắn với repository, commit, run ID và attempt.
- [ ] Test report có số liệu pass/fail/skipped/error và failure details.
- [ ] Coverage report có source revision và phạm vi đo.
- [ ] Analysis report có tool/version, scope, severity và finding ID.
- [ ] Scan report gắn với đúng source hoặc artifact digest.
- [ ] Build evidence có builder, workflow revision, parameters và artifact digest.
- [ ] Deployment record có release ID, environment, config revision và actor.
- [ ] Post-deploy evidence xác minh artifact và trạng thái thực tế.
- [ ] Job song song upload report riêng; collector tổng hợp theo run context.
- [ ] Report schema và context được validate trước quality gate.
- [ ] Missing, invalid, stale, partial và unavailable được phân biệt.
- [ ] Báo cáo gốc được giữ cùng bản normalized.
- [ ] Evidence manifest liên kết report bằng ID và digest.
- [ ] Quyền upload, đọc, sửa và xóa được phân tách.
- [ ] Retention và privacy policy được áp dụng.
- [ ] Có audit cho approval, exception và thay đổi evidence.
- [ ] Có thể truy vết từ production deployment về commit và test/scan evidence.

## 23. Bài tập tự đánh giá

Một pipeline của dịch vụ thanh toán có các job:

- Unit test chạy trên Java 21 và xuất JUnit XML.
- Integration test chạy trên container database và xuất JUnit XML.
- Coverage job xuất JaCoCo XML.
- SAST job xuất SARIF.
- Image scan job xuất JSON report.
- Build job tạo container image và push tag latest.
- Deploy job triển khai tag latest lên staging.
- Một collector chỉ tìm file report theo tên trong workspace của runner.

Một số lần chạy gần đây có các vấn đề:

- Report integration test đôi khi là file từ run trước.
- Image scan report không cho biết digest image đã quét.
- SAST job bị timeout nhưng pipeline vẫn pass.
- Staging có lúc chạy image khác với image được build trong cùng run.
- Deployment record chỉ lưu thời gian và trạng thái success.

Hãy đề xuất thiết kế mới:

1. Mỗi job cần publish những report và metadata nào?
2. Làm sao để collector lấy đúng report của run và attempt hiện tại?
3. Cần kiểm tra những trường nào trước khi normalize report?
4. Làm thế nào phân biệt scanner timeout với scan hoàn tất không có finding?
5. Image scan phải gắn với artifact digest nào?
6. Vì sao tag latest không đủ để xác định image đã deploy?
7. Deployment record cần bổ sung release, config và environment metadata gì?
8. Evidence bundle nên có manifest và digest ra sao?
9. Quyền đọc report bảo mật và retention nên được tổ chức thế nào?
10. Quality gate cần xử lý missing, stale và invalid report ra sao?

Một thiết kế tốt phải cho phép truy từ deployment ở staging về image digest, source commit, test report, scan result và policy decision đã cho phép release.

## Kết luận

Thu thập báo cáo kiểm thử, kết quả phân tích và thông tin triển khai giúp pipeline tạo ra bằng chứng có thể kiểm tra thay vì chỉ trả về một trạng thái xanh/đỏ. Mỗi report cần gắn với đúng commit, run, artifact hoặc môi trường; có nguồn tạo, thời điểm, phạm vi và định dạng hợp lệ.

Hãy publish report từ từng job, tổng hợp theo run context, chuẩn hóa mà vẫn giữ bản gốc, xác minh tính đầy đủ và liên kết bằng evidence manifest. Sau deploy, cần ghi nhận artifact digest, config revision, environment, actor và kết quả xác minh thực tế. Khi bằng chứng có integrity, retention và quyền truy cập phù hợp, đội ngũ có thể ra quyết định phát hành nhất quán, truy vết sự cố và chứng minh chính xác điều gì đã được kiểm tra và triển khai.

