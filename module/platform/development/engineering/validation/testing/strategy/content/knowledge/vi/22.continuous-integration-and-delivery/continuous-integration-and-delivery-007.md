# Quản lý artifact, log, báo cáo và truy vết phiên bản

Trong chiến lược kiểm thử `VALIDATION_TESTING_STRATEGY`, pipeline CI/CD không chỉ có nhiệm vụ build và chạy test. Mỗi lần pipeline thực thi còn tạo ra nhiều bằng chứng: artifact được đóng gói, log của từng bước, báo cáo kiểm thử, kết quả phân tích chất lượng và thông tin về phiên bản được triển khai. Nếu các bằng chứng này không được quản lý nhất quán, nhóm khó xác định chính xác phần mềm nào đã được kiểm tra, artifact nào đã đưa lên môi trường, test nào đã chạy và nguyên nhân của một lỗi sau phát hành.

**Quản lý artifact, log, báo cáo và truy vết phiên bản** là việc xác định, lưu trữ, bảo vệ, liên kết và duy trì các đầu ra của quá trình phát triển và phát hành. Mục tiêu là tạo một chuỗi bằng chứng có thể kiểm tra từ mã nguồn đến build, artifact, test run, release và deployment. Khi có lỗi, nhóm có thể truy ngược từ hệ thống đang chạy về đúng artifact, commit, cấu hình và kết quả kiểm thử đã tạo ra nó.

Một quy trình tốt giúp trả lời được các câu hỏi: artifact này được tạo từ commit nào; dùng toolchain và dependency phiên bản nào; test nào đã chạy trên nó; kết quả có đạt cổng chất lượng không; artifact có bị thay đổi sau khi kiểm thử không; phiên bản nào đang chạy ở môi trường nào; và ai đã phê duyệt việc phát hành. Các câu trả lời cần dựa trên định danh và bằng chứng lưu được, không phụ thuộc vào trí nhớ hoặc tên file do con người đặt.

## 1. Các khái niệm cần phân biệt

Trong CI/CD, một số khái niệm thường bị dùng lẫn nhau nhưng đại diện cho những đối tượng khác nhau.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Source revision | Trạng thái mã nguồn tại một revision xác định | Git commit SHA |
| Build | Một lần thực thi quy trình tạo đầu ra từ source và toolchain | CI run số 1842 |
| Artifact | Đầu ra có thể lưu trữ hoặc triển khai được tạo từ build | JAR, container image, frontend bundle |
| Test run | Một lần thực thi một tập test trên artifact hoặc revision trong môi trường cụ thể | Core regression run trên staging |
| Report | Bản ghi kết quả của test hoặc hoạt động kiểm tra | JUnit XML, coverage report, scan report |
| Release | Phiên bản được phê duyệt để đưa vào sử dụng, cùng metadata và cấu hình liên quan | Release 3.8.2 |
| Deployment | Việc đưa một artifact/release vào một môi trường hoặc vùng cụ thể | Deploy digest X lên staging |
| Provenance | Thông tin nguồn gốc và quá trình tạo artifact | Commit, workflow, runner, dependency, digest |

Một commit có thể tạo nhiều build; một build có thể tạo nhiều artifact; một artifact có thể được kiểm thử nhiều lần trên các môi trường khác nhau; một release có thể được triển khai ở nhiều vùng hoặc theo nhiều giai đoạn. Cần lưu mối quan hệ này thay vì giả định một version string duy nhất mô tả mọi thứ.

### Chuỗi bằng chứng tổng quát

~~~text
Requirement / Change / Issue
          |
          v
Pull Request / Git Commit
          |
          v
CI Build + Toolchain + Dependencies
          |
          +------> Build Logs
          |
          v
Artifact + Digest + Provenance
          |
          +------> Test Runs + Reports
          |
          v
Quality Gate / Release Approval
          |
          v
Release Record / Deployment Record
          |
          v
Environment + Running Version + Runtime Logs
          |
          v
Incident / Feedback / Follow-up Change
~~~

Chuỗi này cần có định danh liên kết giữa các bước. Nếu mỗi công cụ lưu dữ liệu riêng mà không có khóa chung, việc điều tra sẽ tốn thời gian và dễ nhầm phiên bản.

## 2. Quản lý artifact trong CI/CD

Artifact là đầu ra của quá trình build hoặc đóng gói. Tùy loại sản phẩm, artifact có thể là thư viện, package, executable, container image, static website bundle, mobile package, firmware, tài liệu phát hành hoặc bộ manifest triển khai.

### Xác định artifact cần lưu

Không chỉ lưu file cuối cùng mà người dùng tải xuống. Các artifact hỗ trợ kiểm thử và vận hành cũng có giá trị:

- Package hoặc binary được triển khai.
- Container image và các lớp phụ thuộc.
- Frontend bundle, source map được bảo vệ và file tĩnh.
- Helm chart, deployment manifest hoặc gói Infrastructure as Code đã được kiểm tra.
- Schema, migration script và API specification.
- Software Bill of Materials (SBOM) mô tả thành phần phần mềm.
- Test data fixture, test harness hoặc simulator đã version hóa khi cần tái lập.
- Tài liệu release, checksum, chữ ký và provenance attestation.

Chỉ lưu những đầu ra có mục đích và chính sách rõ ràng. Không đưa secret, file tạm, dữ liệu production hoặc dump chứa thông tin cá nhân vào kho artifact chỉ vì pipeline có thể upload mọi thứ.

### Định danh artifact duy nhất

Artifact cần có định danh không mơ hồ. Có thể dùng tên package, version, build ID và digest. Với container, digest như SHA-256 định danh nội dung image; tag chỉ là nhãn có thể được cập nhật để trỏ sang digest khác.

Ví dụ, hai image cùng tag `orders:3.8.2` không chắc có nội dung giống nhau nếu tag bị ghi đè. Khi cần xác định chính xác image đã kiểm thử hoặc triển khai, lưu digest và tham chiếu digest trong deployment record.

Một artifact nên có metadata tối thiểu:

- Tên sản phẩm, module hoặc service.
- Artifact type và package coordinates nếu có.
- Version hoặc release candidate identifier.
- Build ID và source commit SHA.
- Thời điểm tạo và workflow/pipeline đã tạo.
- Digest/checksum và trạng thái xác minh tính toàn vẹn.
- Toolchain, dependency lockfile hoặc dependency inventory.
- Trạng thái quality gate và liên kết đến báo cáo liên quan.

### Artifact bất biến

Sau khi artifact đã được kiểm thử và phê duyệt, nội dung của nó cần được giữ nguyên. Nếu sửa file, build lại hoặc ghi đè cùng version, digest sẽ thay đổi và bằng chứng trước đó không còn mô tả đúng nội dung mới.

Nguyên tắc thực hành:

- Không ghi đè artifact đã phát hành hoặc đã được phê duyệt.
- Dùng version/build ID duy nhất cho mỗi lần tạo artifact.
- Lưu digest để xác minh file không bị thay đổi.
- Nếu cần sửa, tạo build/artifact mới và liên kết với revision mới hoặc build mới.
- Hạn chế quyền xóa, ghi đè và promote artifact.

Artifact bất biến giúp tránh tình huống một báo cáo test nói rằng version 3.8.2 đạt, nhưng file có cùng tên trong repository đã bị thay thế bằng binary khác.

### Build một lần, promote qua môi trường

Một cách làm đáng tin cậy là build artifact một lần từ source và toolchain đã xác định, sau đó promote cùng artifact qua các môi trường tích hợp, staging và production. Cấu hình môi trường được cung cấp riêng khi deploy.

Quy trình mẫu:

1. Checkout commit đã xác định.
2. Cài toolchain và dependency theo lockfile.
3. Build artifact.
4. Chạy kiểm tra và tạo báo cáo.
5. Tạo digest, metadata và provenance.
6. Lưu artifact vào repository.
7. Sau khi quality gate đạt, promote đúng digest sang môi trường tiếp theo.
8. Ghi deployment record xác nhận digest đang chạy.

Không nên build lại một artifact mới cho production chỉ vì cần đổi URL hoặc cấu hình. Nếu phải tạo artifact khác do yêu cầu kỹ thuật, cần chạy lại các kiểm tra phù hợp và ghi rõ mối quan hệ với artifact trước.

## 3. Kho lưu trữ artifact và chính sách vòng đời

Artifact repository hoặc container registry là nơi lưu trữ và phân phối đầu ra build. Kho cần hỗ trợ định danh, quyền truy cập, truy vấn metadata, kiểm tra tính toàn vẹn và chính sách retention.

### Tổ chức kho

Có thể phân vùng theo:

- Sản phẩm, tổ chức hoặc nhóm sở hữu.
- Loại package hoặc container registry.
- Nhánh phát triển, snapshot, release candidate và release chính thức.
- Môi trường hoặc kênh phân phối nếu quy trình yêu cầu.
- Mức độ tin cậy của nguồn tạo artifact.

Không nên dùng một thư mục chung không có quy ước tên hoặc metadata. Người dùng kho phải có thể tìm artifact theo version, commit, build ID hoặc digest.

### Quyền truy cập

Áp dụng nguyên tắc quyền tối thiểu:

- Pipeline build được quyền publish vào repository phù hợp.
- Pipeline deploy được quyền đọc artifact đã được phê duyệt.
- Người phát triển có quyền tải artifact cần thiết nhưng không mặc nhiên được ghi đè release.
- Quyền xóa hoặc thay đổi retention được giới hạn và có audit log.
- Credential của pipeline được lưu trong secret manager, có phạm vi và thời hạn phù hợp.

Với pipeline từ pull request không đáng tin cậy hoặc từ fork, cần cẩn trọng khi cấp quyền publish artifact, truy cập secret hoặc ký release. Một bước build có thể thực thi mã do contributor cung cấp; quyền cao cần được tách khỏi workflow đó.

### Retention và lưu trữ dài hạn

Không phải artifact nào cũng cần lưu mãi mãi. Chính sách retention có thể phân biệt:

- Artifact tạm từ nhánh feature.
- Snapshot từ build tích hợp.
- Release candidate.
- Artifact đã phát hành hoặc đang được triển khai.
- Artifact cần lưu vì yêu cầu kiểm toán, hợp đồng hoặc điều tra sự cố.

Trước khi xóa, cần xác định artifact có đang được release hoặc deployment nào tham chiếu không. Không xóa artifact vẫn đang chạy nếu tổ chức cần khả năng rollback hoặc tái triển khai. Với artifact quan trọng, cân nhắc backup, replication và kiểm tra khả năng khôi phục kho.

### Phân biệt artifact và cache

Cache dependency hoặc build cache giúp tăng tốc pipeline, nhưng không nhất thiết là bản lưu đáng tin cậy của artifact đã phát hành. Cache có thể bị xóa, hết hạn hoặc được tạo lại. Artifact release cần được lưu trong kho có kiểm soát và có digest, provenance, retention riêng.

## 4. Provenance, checksum, chữ ký và SBOM

Để tin cậy artifact, nhóm cần biết nó đến từ đâu, được tạo như thế nào và có bị thay đổi hay không.

### Provenance — nguồn gốc artifact

Provenance ghi nhận mối liên hệ giữa source, workflow, toolchain và artifact. Thông tin có thể gồm:

- Repository và commit SHA.
- Workflow hoặc pipeline definition và revision của workflow.
- Build runner hoặc môi trường thực thi.
- Phiên bản compiler, runtime, build tool và dependency.
- Tham số build quan trọng và thời điểm tạo.
- Artifact name, version, digest và nơi lưu.
- Danh tính workload hoặc pipeline đã thực hiện build.

Provenance hữu ích khi điều tra lỗi, xác minh artifact được tạo từ source đã review và đánh giá chuỗi cung ứng phần mềm. Với hệ thống yêu cầu assurance cao, có thể tạo attestation theo định dạng hoặc tiêu chuẩn phù hợp và xác minh trước khi deploy.

### Checksum và digest

Checksum là giá trị tính từ nội dung file để kiểm tra tính toàn vẹn. Khi tải artifact từ repository hoặc promote giữa môi trường, pipeline có thể tính lại digest và so sánh với giá trị đã lưu.

Digest chỉ xác nhận nội dung có khớp với giá trị tham chiếu hay không; nó không tự chứng minh ai đã tạo artifact hoặc artifact có an toàn. Cần kết hợp với provenance, quyền truy cập và chữ ký khi yêu cầu.

### Chữ ký artifact

Chữ ký số có thể xác minh artifact hoặc image được ký bởi danh tính đáng tin cậy và nội dung chưa bị thay đổi sau khi ký. Cần bảo vệ private signing key, giới hạn quyền ký và có quy trình xoay vòng/thu hồi khóa. Không nên cho mọi job build tùy ý dùng cùng một khóa phát hành có quyền cao.

Trước khi deploy, pipeline có thể xác minh:

- Digest artifact đúng với release record.
- Chữ ký hợp lệ và được tạo bởi identity được phép.
- Provenance trỏ đến repository, workflow và revision được phê duyệt.
- Các policy bắt buộc, ví dụ scan hoặc SBOM, đã có kết quả đạt.

### SBOM — danh mục thành phần phần mềm

SBOM liệt kê các thành phần và dependency có trong artifact, thường kèm tên, version, supplier, định danh package và license hoặc thông tin bảo mật khi có. SBOM hỗ trợ đánh giá tác động khi một dependency có lỗ hổng, kiểm tra license và quản lý chuỗi cung ứng.

SBOM cần gắn với đúng artifact digest. Nếu build thay đổi dependency, SBOM phải được tạo lại. Một SBOM chung cho cả repository có thể không phản ánh chính xác những thành phần thực sự được đóng gói trong từng image hoặc package.

## 5. Quản lý log của pipeline và ứng dụng

Log cung cấp dòng thời gian và ngữ cảnh của hoạt động build, test, deploy và vận hành. Cần phân biệt các loại log vì chúng có mục đích, quyền truy cập và thời gian lưu khác nhau.

### Build log

Build log ghi lại các bước checkout, cài dependency, compile, package, scan và upload artifact. Nó giúp xác định bước nào thất bại, tool nào được dùng và lỗi phát sinh trong điều kiện nào.

Build log nên thể hiện:

- Pipeline/run ID và job/step ID.
- Commit, branch hoặc pull request liên quan.
- Toolchain và phiên bản quan trọng.
- Thời điểm bắt đầu/kết thúc và exit status.
- Lệnh hoặc tác vụ đã chạy ở mức cần thiết để chẩn đoán.
- Liên kết đến artifact và report được tạo.

Tránh in toàn bộ môi trường hoặc command line nếu có thể chứa token, password, connection string hoặc secret.

### Test execution log

Test log ghi lại test suite, test case, fixture, môi trường và kết quả thực thi. Khi một test fail, log cần giúp xác định test nào, dữ liệu nào, bước nào và exception hoặc assertion nào dẫn đến thất bại.

Với test phân tán hoặc chạy song song, nên có test run ID, shard/worker ID và correlation ID. Nếu test gọi API hoặc message broker, lưu mã giao dịch và thông tin phản hồi đã được che dữ liệu nhạy cảm.

### Deployment log

Deployment log ghi lại artifact/digest, môi trường, vùng, cấu hình hoặc config version, thời điểm, người hoặc pipeline khởi tạo, kết quả rollout và bước xác minh sau deploy.

Log này đặc biệt quan trọng khi production có nhiều phiên bản cùng tồn tại trong canary hoặc rollout theo giai đoạn. Cần biết từng nhóm lưu lượng đang nhận artifact nào.

### Application log và audit log

Application log ghi sự kiện khi phần mềm chạy: lỗi, cảnh báo, trạng thái xử lý và thông tin chẩn đoán. Audit log ghi các hành động cần truy trách nhiệm, chẳng hạn ai thay đổi cấu hình, phê duyệt release hoặc truy cập dữ liệu nhạy cảm.

Audit log thường có yêu cầu bảo vệ tính toàn vẹn và quyền truy cập nghiêm ngặt hơn log chẩn đoán. Không nên xem hai loại là một và áp dụng cùng chính sách xóa hoặc sửa.

### Log có cấu trúc

Log có cấu trúc giúp truy vấn và liên kết dễ hơn. Một bản ghi minh họa:

~~~json
{
  "timestamp": "2026-11-16T09:15:30Z",
  "level": "ERROR",
  "service": "order-service",
  "environment": "staging",
  "release": "3.8.2",
  "buildId": "ci-1842",
  "commit": "7d91c4a",
  "testRunId": "core-regression-552",
  "correlationId": "checkout-2048",
  "event": "payment_confirmation_failed",
  "errorCode": "PAYMENT_TIMEOUT"
}
~~~

Các trường cụ thể phụ thuộc nền tảng. Cần thống nhất tên và ý nghĩa để truy vấn qua nhiều service. Không đưa access token, mật khẩu, số thẻ đầy đủ hoặc thông tin cá nhân không cần thiết vào log.

## 6. Bảo vệ log và dữ liệu chẩn đoán

Log có thể chứa dữ liệu nhạy cảm hoặc thông tin nội bộ. Một hệ thống log tốt cần vừa đủ ngữ cảnh cho điều tra vừa bảo vệ người dùng và tổ chức.

### Giảm thiểu và che dữ liệu

- Không ghi secret, password, private key hoặc session token.
- Che hoặc loại bỏ dữ liệu cá nhân và dữ liệu thanh toán không cần thiết.
- Dùng ID tham chiếu thay cho payload đầy đủ khi có thể.
- Kiểm tra log từ cả ứng dụng, test runner, reverse proxy và công cụ bên thứ ba.
- Tránh đưa nội dung request/response đầy đủ vào log mặc định nếu payload có thể nhạy cảm.

### Quyền truy cập và audit

Phân quyền đọc log theo vai trò và mục đích. Log production có thể cần giới hạn hơn log test. Ghi nhận truy cập hoặc export log nếu chính sách yêu cầu. Không dùng log làm kho lưu dữ liệu nghiệp vụ thay thế database.

### Retention và xóa

Thời gian lưu phụ thuộc mục đích, quy định, hợp đồng, chi phí và khả năng điều tra. Log debug ngắn hạn có thể có retention khác audit log. Cần xác định quy trình xóa tự động, legal hold nếu có và cách bảo vệ backup.

### Log từ pipeline không đáng tin cậy

Build từ mã nguồn bên ngoài hoặc pull request không đáng tin cậy có thể ghi nội dung độc hại, tạo file lớn hoặc cố lấy secret. Pipeline cần giới hạn quyền, giới hạn dung lượng, kiểm soát cách render log và tránh thực thi artifact chưa được xác minh trong môi trường có credential nhạy cảm.

## 7. Quản lý báo cáo kiểm thử và chất lượng

Báo cáo kiểm thử biến kết quả thực thi thành bằng chứng có thể xem xét. Không nên chỉ lưu một dòng “Build passed” hoặc ảnh chụp màn hình màu xanh. Cần giữ dữ liệu đủ chi tiết để biết test nào đã chạy, test nào bỏ qua, lỗi nào còn mở và điều kiện nào được sử dụng.

### Các loại báo cáo phổ biến

| Loại báo cáo | Nội dung | Mục đích |
|---|---|---|
| Unit/integration test report | Test case, pass/fail/skip, thời gian, lỗi | Phát hiện lỗi chức năng và tích hợp |
| Coverage report | Dòng, nhánh hoặc điều kiện được thực thi | Tìm vùng code chưa được test; không tự chứng minh chất lượng test |
| Static analysis report | Code smell, lỗi tiềm ẩn, maintainability issue | Phát hiện vấn đề mã nguồn trước runtime |
| Security scan report | Dependency vulnerability, SAST, container/image scan | Đánh giá rủi ro bảo mật và chuỗi cung ứng |
| Contract/API report | Kết quả kiểm tra schema và tương thích | Xác nhận consumer/provider phù hợp hợp đồng |
| Performance report | Throughput, latency, error rate, resource use | Đánh giá hiệu năng và giới hạn tải |
| Accessibility/compatibility report | Kết quả theo browser, thiết bị hoặc tiêu chí tiếp cận | Đánh giá khả năng sử dụng trên môi trường mục tiêu |
| Deployment verification report | Health, smoke, version và rollout result | Xác nhận phiên bản hoạt động sau deploy |

### Định dạng báo cáo

Nhiều test framework có thể xuất JUnit XML hoặc định dạng tương đương để CI tổng hợp. Các công cụ coverage, security và performance thường có định dạng riêng. Nên lưu cả dữ liệu máy đọc được để tích hợp tự động và bản tóm tắt dễ đọc cho người review.

Khi test chạy theo shard hoặc nhiều worker, cần hợp nhất báo cáo đúng cách, tránh mất test hoặc đếm trùng. Báo cáo cuối nên nêu số test discovered, executed, passed, failed, skipped, quarantined và thời gian chạy. Nếu test không được thực thi do điều kiện pipeline, phải thể hiện rõ thay vì coi là pass.

### Báo cáo cần có ngữ cảnh

Một báo cáo hữu ích cần liên kết với:

- Test run ID, build ID và commit SHA.
- Artifact version/digest được kiểm tra.
- Environment ID hoặc manifest, cấu hình và service version.
- Phiên bản test runner, test suite và dữ liệu liên quan.
- Thời điểm bắt đầu/kết thúc và người hoặc pipeline thực hiện.
- Kết quả quality gate và ngoại lệ được phê duyệt.
- Liên kết log, trace, screenshot hoặc file đính kèm cần thiết.

Nếu báo cáo chỉ ghi tên suite và số lượng pass/fail, người điều tra có thể không biết nó áp dụng cho artifact nào hoặc môi trường nào.

### Tóm tắt kết quả cho quyết định phát hành

Báo cáo tóm tắt nên nêu:

1. Phiên bản và artifact đã kiểm tra.
2. Phạm vi suite đã chạy và suite chưa chạy.
3. Kết quả theo mức độ nghiêm trọng.
4. Lỗi còn mở, test flaky hoặc test bị quarantine.
5. Kết quả scan, coverage và non-functional check liên quan.
6. Rủi ro tồn dư, giới hạn môi trường và ngoại lệ.
7. Khuyến nghị hoặc quyết định theo đúng thẩm quyền.

Không dùng coverage percentage hoặc tổng số test pass làm kết luận duy nhất. Một bộ test có thể pass nhưng không bao phủ rủi ro quan trọng; coverage cao vẫn có thể thiếu assertion hữu ích.

## 8. Quality gate và liên kết với artifact

Quality gate là điều kiện quyết định pipeline có được tiếp tục, promote hoặc phát hành hay không. Gate cần dựa trên tiêu chí đo được và gắn với artifact cụ thể.

Ví dụ điều kiện gate:

- Build thành công và artifact được tạo đúng định danh.
- Smoke và core regression đạt theo chính sách.
- Không có lỗi nghiêm trọng hoặc lỗ hổng bảo mật vượt ngưỡng cho phép.
- Dependency/license policy đạt.
- Artifact có digest, provenance và SBOM theo yêu cầu.
- Các báo cáo bắt buộc được tạo và lưu thành công.
- Người có thẩm quyền đã phê duyệt ngoại lệ nếu có.

Gate phải kiểm tra đúng artifact sẽ được promote. Nếu test chạy trên artifact A nhưng pipeline deploy artifact B được build lại, gate không chứng minh B đã được kiểm tra. Liên kết qua digest là cách mạnh để xác nhận cùng nội dung.

### Phân biệt lỗi gate và lỗi hệ thống báo cáo

Pipeline có thể fail vì test fail, hoặc vì không thể upload report dù test đã chạy xong. Hai trường hợp cần được phân biệt. Nếu report upload thất bại, nhóm mất bằng chứng và có thể không đủ điều kiện tiếp tục theo policy, dù test process trả mã 0. Cần lưu raw output tạm thời, retry upload có kiểm soát hoặc đánh dấu kết quả chưa đầy đủ; không tự gán trạng thái pass.

### Quản lý ngoại lệ

Nếu tổ chức cho phép waiver, phải ghi lý do, phạm vi, người phê duyệt, thời hạn và điều kiện đóng. Không nên sửa report gốc hoặc xóa kết quả fail để làm pipeline xanh. Ngoại lệ phải được liên kết với release và dễ truy vết.

## 9. Truy vết phiên bản từ source đến production

Version traceability là khả năng liên kết các đối tượng trong vòng đời phần mềm để xác định chính xác nội dung nào đã được tạo, kiểm tra, phê duyệt và triển khai.

### Các định danh nên liên kết

| Đối tượng | Định danh gợi ý | Liên kết cần có |
|---|---|---|
| Requirement/change | Requirement ID, issue ID | Commit/PR triển khai thay đổi |
| Source | Repository + commit SHA | Build ID tạo artifact |
| Pull request | PR number + merge commit | Review, approval và checks |
| Build | Pipeline run ID | Toolchain, logs, artifacts và reports |
| Artifact | Package version + digest | Provenance, SBOM và test run |
| Test run | Test run ID | Artifact digest, environment và report |
| Release | Release ID/tag | Artifact digest, approvals và notes |
| Deployment | Deployment ID | Release, environment, region và config version |
| Runtime | Service/version/instance metadata | Logs, metrics, traces và incident |
| Incident | Incident ID | Release/deployment và change liên quan |

Không nhất thiết dùng một ID duy nhất cho mọi hệ thống. Cần có các khóa liên kết ổn định và quy tắc truyền metadata giữa công cụ.

### Commit SHA và tag release

Commit SHA xác định revision source. Tag release như `v3.8.2` giúp con người nhận diện mốc phát hành, nhưng tag có thể bị di chuyển nếu repository không bảo vệ. Cần bảo vệ release tag hoặc lưu commit SHA trong release record.

Một version hiển thị cho người dùng có thể theo SemVer, nhưng build ID cần phân biệt từng lần tạo artifact. Ví dụ `3.8.2+build.1842` hoặc một ID pipeline riêng có thể giúp phân biệt candidate. Cần thống nhất quy ước của dự án và không nhầm version thương mại với định danh nội dung bất biến.

### Release manifest

Release manifest là bản ghi mô tả những gì thuộc một release. Nó có thể bao gồm:

- Release ID, version và thời điểm phát hành.
- Repository, commit SHA và pull request liên quan.
- Artifact names, versions và digests.
- SBOM và provenance references.
- Test run IDs và kết quả gate.
- Phiên bản dependency/runtime quan trọng.
- Config version hoặc config reference không chứa secret.
- Các migration, feature flag và service dependency liên quan.
- Người phê duyệt, ngoại lệ và release notes.

Manifest cần được tạo tự động hoặc kiểm soát bằng quy trình rõ ràng. Không nên duy trì thủ công một danh sách dễ lệch với artifact thực tế.

### Deployment record

Mỗi lần triển khai cần ghi artifact digest, release ID, môi trường, vùng, thời điểm, rollout strategy, config version, người hoặc pipeline khởi tạo, kết quả smoke/post-deployment verification và trạng thái rollout.

Với canary, có thể nhiều digest cùng hoạt động trong một môi trường ở các thời điểm hoặc nhóm lưu lượng khác nhau. Deployment record cần ghi tỷ lệ và khoảng thời gian nếu điều đó quan trọng cho việc điều tra.

## 10. Truy vết kết quả test đến đúng phiên bản

Một test report chỉ có giá trị khi biết nó kiểm tra điều gì và trên nội dung nào. Đặc biệt, test có thể chạy trên source tree, package đã build hoặc deployment đã chạy; cần phân biệt rõ.

### Gắn test run với artifact

Khi test chạy trên artifact, lưu digest artifact trong report metadata. Nếu test chạy trực tiếp trên source hoặc build directory, lưu commit và build ID. Không chỉ dùng tên branch vì branch có thể di chuyển theo commit mới.

### Gắn môi trường với test run

Ghi environment ID hoặc manifest gồm runtime, database, broker, browser, config version, feature flag và dữ liệu cần thiết. Nếu môi trường dùng dịch vụ bên ngoài không thể pin, ghi rõ endpoint/channel và thời điểm kiểm tra.

### Gắn test case với yêu cầu và rủi ro

Test ID có thể liên kết với requirement, issue hoặc risk ID. Khi một test fail, nhóm biết yêu cầu hoặc rủi ro nào bị ảnh hưởng. Khi một yêu cầu thay đổi, nhóm có thể tìm các test cần cập nhật hoặc chạy lại.

### Truy vết từ production incident

Khi có incident, cần tìm deployment record để biết digest đang chạy; từ digest tìm release manifest và provenance; từ manifest tìm commit, PR, build và test reports. Sau đó so sánh với phiên bản trước, cấu hình và dữ liệu runtime để xác định thay đổi có liên quan.

Chuỗi truy vết không tự chứng minh nguyên nhân. Nó giúp thu hẹp phạm vi và bảo đảm nhóm đang điều tra đúng phiên bản cùng bằng chứng.

## 11. Tổ chức pipeline để tạo và lưu bằng chứng

Một pipeline CI/CD có thể được tổ chức theo luồng sau:

~~~text
1. Checkout source + resolve commit
          |
2. Verify toolchain + lockfile
          |
3. Build artifact
          |
4. Run tests + scans
          |       +--> Test reports
          |       +--> Coverage / scan reports
          |       +--> Build and test logs
          v
5. Package metadata + digest + provenance + SBOM
          |
6. Upload artifact and reports to controlled storage
          |
7. Evaluate quality gates on the exact artifact
          |
8. Approve / promote the same artifact
          |
9. Deploy and write deployment record
          |
10. Post-deployment smoke + runtime verification
          |
11. Link runtime version and telemetry to release
~~~

Các bước có thể chạy song song nếu không phá vỡ quan hệ phụ thuộc. Ví dụ, static analysis và unit test có thể chạy song song sau khi source được checkout. Artifact chỉ được promote sau khi các kiểm tra bắt buộc và upload bằng chứng đạt.

### Quy tắc đặt tên và metadata

Đặt tên artifact và report sao cho dễ tìm nhưng không dựa vào tên tự do làm định danh duy nhất. Có thể kết hợp service, version, build ID và platform. Metadata nên lưu riêng hoặc trong manifest có schema rõ.

Ví dụ:

~~~text
service: order-service
release: 3.8.2
commit: 7d91c4a...
build_id: ci-1842
artifact: registry.example/order-service@sha256:...
test_run: core-regression-552
environment: staging-eu
config_version: staging-config-91
~~~

Các giá trị trên chỉ minh họa. Không đưa endpoint nội bộ nhạy cảm hoặc credential vào metadata công khai.

### Xử lý pipeline chạy song song

Khi nhiều job hoặc shard chạy song song:

- Mỗi job có job ID và liên kết với pipeline run ID.
- Artifact do từng job tạo cần tên hoặc metadata không xung đột.
- Report được hợp nhất theo test ID và shard, tránh đếm trùng.
- Chỉ tạo kết quả tổng hợp sau khi biết tất cả job bắt buộc đã hoàn tất.
- Nếu một shard bị mất hoặc bị hủy, report cần thể hiện thiếu dữ liệu.
- Upload phải bảo đảm report của build này không ghi đè report của build khác.

## 12. Ví dụ xuyên suốt: truy vết một bản phát hành dịch vụ Java

Giả sử nhóm phát triển `order-service` bằng Java, build bằng Gradle và đóng gói thành JAR cùng container image. Pipeline chạy unit, integration, contract, security scan và smoke test trên staging.

### Build và tạo artifact

Một pull request được merge thành commit `7d91c4a`. CI run `ci-1842` sử dụng JDK và Gradle version đã pin, cài dependency theo lockfile, build JAR và container image. Pipeline tạo digest cho image, tạo SBOM và provenance chứa commit, toolchain cùng workflow.

Artifact được upload vào registry với version `3.8.2-rc.1` và digest bất biến. Pipeline không ghi đè artifact nếu build lại. Nếu cần build mới, tạo build ID và digest mới.

### Chạy test và tạo báo cáo

Các suite chạy và lưu kết quả:

| Suite | Test run | Kết quả minh họa | Bằng chứng |
|---|---|---|---|
| Unit | unit-1842 | 1,240 passed | JUnit XML, coverage |
| Integration | integration-1842 | 186 passed, 2 failed | JUnit XML, test logs |
| Contract | contract-1842 | Passed | Contract report |
| Security scan | security-1842 | 0 critical, 1 medium | Scan report, SBOM |
| Smoke staging | smoke-1842 | Passed | Deployment verification report |

Hai integration test thất bại nên quality gate chưa đạt theo policy giả định. Pipeline giữ artifact và report để điều tra, nhưng không promote release candidate. Sau khi sửa lỗi, nhóm tạo commit/build mới, chạy lại các suite và lưu bằng chứng mới. Không sửa report cũ để làm kết quả trông như pass.

### Promote và triển khai

Sau khi gate đạt và được phê duyệt, cùng image digest được promote từ registry candidate sang release channel. Staging và production dùng cùng digest, còn cấu hình môi trường được cung cấp riêng. Deployment record ghi release ID, digest, config version, vùng triển khai và kết quả post-deployment smoke.

### Điều tra incident

Sau phát hành, một số đơn hàng bị treo ở trạng thái chờ xác nhận. Nhóm lấy mã đơn và correlation ID từ log, tìm trace liên quan, xác định instance đang chạy digest nào, rồi tra deployment record và release manifest. Từ manifest, nhóm tìm commit, PR, build, integration report và phiên bản Payment Adapter. Chuỗi bằng chứng cho thấy thay đổi timeout trong release mới có liên quan; nhóm có thể kiểm tra lại test tương ứng và bổ sung hồi quy.

Ví dụ cho thấy artifact, report, log và version metadata phải được liên kết ngay từ pipeline. Nếu chỉ lưu một file JAR và vài dòng console output, việc truy ngược incident sẽ khó và dễ dựa vào phỏng đoán.

## 13. Điều tra lỗi bằng log và báo cáo

Khi pipeline hoặc production có vấn đề, nên điều tra theo một trình tự có thể tái lập.

### Xác định định danh trước

Thu thập build ID, commit SHA, artifact digest, test run ID hoặc deployment ID. Không bắt đầu bằng việc tìm file theo tên chung như `latest-report.zip` nếu có nhiều build cùng ghi vào đó.

### Đọc summary rồi đi vào chi tiết

Xem trạng thái quality gate và tổng hợp report để biết suite hoặc step nào fail. Sau đó mở test case, stack trace, log liên quan và môi trường. Tránh đọc hàng nghìn dòng log mà chưa biết job hoặc thời điểm cần tập trung.

### Phân loại nguyên nhân

Một test fail có thể do:

- Lỗi sản phẩm.
- Lỗi test hoặc assertion không đúng.
- Dữ liệu hoặc fixture không hợp lệ.
- Môi trường hoặc dịch vụ phụ thuộc không sẵn sàng.
- Version toolchain/dependency thay đổi.
- Timeout, race condition hoặc tài nguyên thiếu.
- Report upload/aggregation bị lỗi.

Ghi nhận loại nguyên nhân và bằng chứng. Không tự động gán mọi lỗi test là lỗi sản phẩm, cũng không gán mọi lỗi môi trường để bỏ qua gate.

### Tái lập bằng đúng artifact và điều kiện

Nếu có thể, chạy lại cùng artifact digest, environment manifest và dữ liệu. Nếu phải build lại, ghi build ID mới và so sánh digest. Việc tái lập trên source mới nhất không chứng minh lỗi ở artifact cũ đã được hiểu.

### Lưu kết quả điều tra

Liên kết issue hoặc incident với report, log, trace, deployment và commit liên quan. Khi lỗi được sửa, thêm test hồi quy phù hợp và cập nhật tài liệu hoặc quy trình nếu nguyên nhân đến từ quản lý artifact, cấu hình hay pipeline.

## 14. Quản trị, retention và tính toàn vẹn bằng chứng

Artifact, log và report có thể là bằng chứng quan trọng cho vận hành, hợp đồng, kiểm toán và bảo mật. Cần có chính sách quản trị nhất quán.

### Chính sách retention

Xác định thời gian lưu theo loại dữ liệu:

- Artifact snapshot và build tạm.
- Release artifact và artifact đang chạy.
- Test report và quality gate evidence.
- Build/deployment logs.
- Runtime diagnostic logs.
- Audit logs và security scan reports.
- Provenance, SBOM và approval record.

Thời gian lưu cần cân bằng nhu cầu điều tra, yêu cầu pháp lý/hợp đồng, chi phí và quyền riêng tư. Artifact release có thể cần lưu lâu hơn build tạm; audit log có thể cần retention riêng và không được chỉnh sửa tùy tiện.

### Tính toàn vẹn và backup

Với bằng chứng quan trọng, dùng checksum, storage versioning, immutable storage hoặc cơ chế bảo vệ tương đương. Kiểm tra khả năng khôi phục repository và báo cáo. Nếu artifact mất nhưng deployment record vẫn còn, nhóm có thể không tái triển khai hoặc rollback được.

### Audit trail

Ghi nhận ai đã publish, promote, approve, deploy, xóa hoặc thay đổi retention. Audit trail cần có timestamp đáng tin cậy và được bảo vệ khỏi chỉnh sửa trái phép.

### Quyền riêng tư và bí mật

Báo cáo và log có thể chứa email, ID khách hàng, request payload hoặc thông tin môi trường. Giảm thiểu dữ liệu, che thông tin, giới hạn quyền và tuân thủ thời hạn lưu. Không dùng log làm nơi chia sẻ credential hoặc thông tin nhạy cảm.

## 15. Những sai lầm thường gặp

**Ghi đè artifact cùng version.** Báo cáo test cũ có thể trỏ đến tên file nhưng nội dung đã thay đổi. Dùng định danh bất biến, digest và version/build ID duy nhất.

**Build lại cho từng môi trường.** Artifact production có thể khác artifact đã kiểm thử. Ưu tiên build một lần, promote cùng digest và quản lý cấu hình riêng.

**Chỉ lưu console log.** Log có thể bị cắt, khó truy vấn và không đủ metadata. Lưu log có cấu trúc, report máy đọc được và summary gắn với build/test run.

**Báo cáo không gắn với artifact.** Không biết test chạy trên bản nào khiến kết quả khó dùng trong quyết định release. Gắn artifact digest hoặc source/build ID vào report.

**Chỉ lưu tổng số pass/fail.** Số tổng hợp không cho biết test nào skip, flaky, quarantine hoặc không chạy. Giữ kết quả chi tiết và trạng thái của từng test.

**Dùng tag động thay cho digest.** Tag có thể bị cập nhật và không xác định nội dung duy nhất. Lưu digest trong manifest và deployment record.

**Thiếu metadata môi trường.** Cùng artifact có thể cho kết quả khác do database, browser, config hoặc feature flag. Gắn environment manifest với test run.

**Không lưu report khi pipeline fail.** Nếu job kết thúc trước bước upload, nhóm mất bằng chứng. Dùng cơ chế luôn chạy bước thu thập report khi phù hợp và xử lý upload lỗi minh bạch.

**Đưa secret vào log.** In toàn bộ biến môi trường hoặc request có thể làm lộ credential. Che dữ liệu và kiểm tra log ở nhiều lớp.

**Retention không có quy tắc.** Xóa artifact đang chạy hoặc lưu mọi log vô thời hạn đều gây rủi ro. Đặt retention theo loại dữ liệu và khả năng khôi phục.

**Truy vết chỉ đến commit, không đến deployment.** Commit không cho biết artifact nào được deploy hoặc cấu hình nào đang chạy. Ghi deployment record với digest, environment và config version.

## 16. Checklist quản lý artifact, log, report và version traceability

### Artifact

- [ ] Artifact có tên, version/build ID và digest duy nhất.
- [ ] Artifact sau kiểm thử không bị ghi đè hoặc thay đổi âm thầm.
- [ ] Build metadata/provenance liên kết source, toolchain và dependency.
- [ ] SBOM/chữ ký được tạo và xác minh khi policy yêu cầu.
- [ ] Artifact được lưu trong repository có phân quyền và retention.
- [ ] Cùng artifact được promote qua môi trường theo quy trình đã xác định.

### Logs

- [ ] Build, test, deployment, application và audit log được phân biệt.
- [ ] Log có pipeline/build/test/deployment ID và timestamp.
- [ ] Log có cấu trúc và correlation ID ở các luồng cần truy vết.
- [ ] Secret và dữ liệu nhạy cảm được loại bỏ hoặc che.
- [ ] Quyền đọc, export và thời gian lưu được kiểm soát.
- [ ] Log đủ ngữ cảnh để phân loại lỗi và tái lập điều kiện.

### Báo cáo

- [ ] Có report máy đọc được và summary dễ review.
- [ ] Report gắn với commit, build, artifact digest và environment.
- [ ] Test pass/fail/skip/flaky/quarantine được thể hiện đầy đủ.
- [ ] Report từ shard/worker được hợp nhất không mất hoặc đếm trùng.
- [ ] Coverage, security, performance và contract report được lưu khi áp dụng.
- [ ] Quality gate dựa trên artifact đúng và có hồ sơ ngoại lệ.

### Truy vết và quản trị

- [ ] Requirement/issue liên kết được với PR/commit và test.
- [ ] Commit liên kết được với build, artifact, report và release.
- [ ] Release liên kết được với deployment, environment và config version.
- [ ] Có thể truy ngược từ incident đến digest, commit và test evidence.
- [ ] Retention, backup, integrity và audit trail được xác định.
- [ ] Có chủ sở hữu cho repository, report pipeline và metadata schema.

## 17. Tự kiểm tra mức độ hiểu

**Tình huống 1:** CI báo build `3.8.2` pass, nhưng registry có hai image cùng tag với digest khác nhau. Nhóm không thể kết luận image đang deploy đã được kiểm thử chỉ từ tag. Cần xác định digest của artifact test và so sánh với digest trong deployment record.

**Tình huống 2:** Integration test fail nhưng pipeline chỉ lưu summary “1 failed”, không có JUnit XML hoặc log. Bằng chứng chưa đủ để điều tra. Cần cấu hình bước thu thập report luôn chạy khi phù hợp, lưu raw report và liên kết với test run ID.

**Tình huống 3:** Production có lỗi ở một số đơn hàng. Nhóm có order ID và timestamp nhưng không biết release nào xử lý. Cần dùng correlation ID, runtime metadata và deployment record để tìm digest đang chạy, sau đó truy ngược release manifest, commit và test reports.

**Tình huống 4:** Artifact đã được ký nhưng SBOM thuộc một build khác. Chữ ký chỉ xác nhận nội dung được ký, không chứng minh SBOM mô tả đúng artifact. Cần gắn SBOM với digest chính xác và xác minh trong pipeline.

**Tình huống 5:** Pipeline từ pull request bên ngoài có quyền publish release và đọc signing key. Đây là rủi ro chuỗi cung ứng. Cần giới hạn quyền của workflow không đáng tin cậy, tách bước ký/phát hành sang workflow được bảo vệ và dùng identity/credential có phạm vi tối thiểu.

**Tình huống 6:** Một artifact cũ đã bị xóa theo retention, nhưng release vẫn đang chạy và tổ chức cần rollback. Chính sách retention chưa tính đến vòng đời deployment. Cần bảo vệ artifact đang được tham chiếu hoặc lưu trữ release đủ lâu để đáp ứng rollback và kiểm toán.

Khi review một pipeline, hãy tự hỏi: **có thể xác định chính xác artifact nào được tạo và kiểm tra không, bằng chứng có gắn với đúng phiên bản và môi trường không, và từ một deployment hoặc incident có thể truy ngược về source cùng test report không?** Nếu thiếu một liên kết, cần bổ sung metadata hoặc record tại bước tạo ra nó.

## Kết luận

Quản lý artifact, log, báo cáo và truy vết phiên bản giúp CI/CD tạo ra bằng chứng đáng tin cậy cho toàn bộ vòng đời phần mềm. Artifact cần được định danh bất biến, lưu trong repository có kiểm soát và gắn với provenance, digest cùng SBOM khi phù hợp. Log cần có cấu trúc, ngữ cảnh và bảo vệ dữ liệu; report cần thể hiện chi tiết kết quả và gắn với đúng build, artifact và môi trường. Release manifest và deployment record kết nối source, test, approval và phiên bản đang chạy. Khi chuỗi bằng chứng được tạo tự động, lưu an toàn và có thể truy vấn, nhóm có thể điều tra nhanh hơn, phát hành có kiểm soát và chứng minh rõ điều gì đã được kiểm thử.
