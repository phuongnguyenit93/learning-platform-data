# Xác định đầu vào, đầu ra và điều kiện qua từng giai đoạn

Một luồng giao phần mềm đáng tin cậy cần trả lời được ba câu hỏi ở mỗi giai đoạn: **giai đoạn này nhận dữ liệu gì, tạo ra bằng chứng hoặc sản phẩm gì, và dựa vào điều kiện nào để được chuyển tiếp?** Nếu ba câu hỏi đó không có câu trả lời rõ ràng, pipeline dễ trở thành một chuỗi lệnh chạy tự động nhưng khó kiểm soát: có thể triển khai nhầm phiên bản, bỏ sót kiểm thử, phát hành artifact chưa được kiểm tra hoặc không biết phải quay lui về đâu khi có sự cố.

Trong CI/CD, mỗi giai đoạn nên được thiết kế như một hợp đồng có thể kiểm chứng. Hợp đồng này giúp pipeline chạy nhất quán, người duyệt hiểu mình đang phê duyệt điều gì và nhóm vận hành lần theo được đường đi từ thay đổi Git đến phiên bản đang chạy.

## 1. Mô hình hợp đồng cho một giai đoạn

Một giai đoạn trong luồng giao phần mềm nên khai báo tối thiểu năm thành phần:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Đầu vào (inputs) | Giai đoạn cần những dữ liệu nào? | commit SHA, cấu hình build, phiên bản công cụ, artifact digest |
| Xử lý (actions) | Giai đoạn thực hiện việc gì? | lint, chạy test, đóng gói, triển khai |
| Đầu ra (outputs) | Giai đoạn tạo ra sản phẩm hoặc kết quả nào? | báo cáo test, image container, deployment revision |
| Điều kiện qua (gate) | Bằng chứng nào chứng minh có thể đi tiếp? | tất cả kiểm tra bắt buộc thành công, artifact đã được quét |
| Khi thất bại | Dừng, thử lại hay chuyển về bước nào? | chặn merge, giữ log, rollback deployment |

Đầu vào phải có nguồn gốc xác định. Đầu ra phải có tên, phiên bản hoặc định danh đủ rõ để giai đoạn tiếp theo sử dụng. Điều kiện qua phải kiểm tra được bằng máy hoặc được một người có thẩm quyền xác nhận theo quy trình. Tránh các điều kiện mơ hồ như “build có vẻ ổn” hay “kiểm thử tương đối đầy đủ”.

Có thể biểu diễn hợp đồng bằng cấu trúc khái niệm sau. Đây là ví dụ mô tả thiết kế, không phải cú pháp cấu hình của một nền tảng CI/CD cụ thể:

```yaml
stage: test
inputs:
  - source_commit
  - dependency_lockfiles
  - test_configuration
outputs:
  - test_report
  - coverage_report
  - test_status
pass_when:
  - required_tests_pass
  - coverage_meets_policy
on_failure:
  - stop_pipeline
  - retain_reports_and_logs
```

Một gate chỉ có ý nghĩa khi nó kiểm tra đúng đầu ra của giai đoạn trước. Ví dụ, bước triển khai phải nhận artifact đã được build và kiểm tra; không nên tự build lại từ một nhánh có thể đã thay đổi.

## 2. Luồng đầu vào, đầu ra và gate theo từng giai đoạn

Một luồng phổ biến đi từ sự kiện Git, xác minh mã nguồn, kiểm tra chất lượng, build, lưu artifact, triển khai lên môi trường, phê duyệt phát hành đến xác minh sau triển khai. Tên và số lượng stage có thể khác nhau theo dự án, nhưng hợp đồng của từng stage vẫn cần rõ ràng.

### 2.1. Tiếp nhận sự kiện Git

**Mục đích:** xác định thay đổi nào cần chạy pipeline và vì sao pipeline được khởi động.

- **Đầu vào:** sự kiện push, pull request, tạo tag, yêu cầu chạy thủ công hoặc lịch chạy; repository; nhánh hoặc tag; commit SHA; người hoặc hệ thống khởi tạo; các tham số được cho phép.
- **Đầu ra:** một lần chạy pipeline có mã định danh; loại sự kiện; commit SHA mục tiêu; thời điểm và danh tính tác nhân khởi chạy.
- **Gate:** sự kiện thuộc phạm vi được phép; nhánh/tag đáp ứng chính sách; tham số đầu vào hợp lệ; pipeline có thể xác định chính xác commit cần xử lý.
- **Khi thất bại:** từ chối yêu cầu không hợp lệ và ghi lý do. Với các lần push liên tiếp, có thể hủy lần chạy cũ đã lỗi thời nếu chính sách dự án cho phép.

Không nên dùng tên nhánh làm định danh duy nhất cho phiên bản mã nguồn, vì nội dung nhánh có thể thay đổi theo thời gian. Hãy ghi lại commit SHA ngay từ đầu. Pipeline chạy cho pull request từ fork cũng cần được xem là nguồn chưa tin cậy: không cấp bí mật triển khai hoặc quyền ghi vào registry cho mã chưa được tin cậy.

### 2.2. Lấy và xác minh mã nguồn

**Mục đích:** bảo đảm mọi bước sau làm việc trên cùng một snapshot mã nguồn.

- **Đầu vào:** repository, commit SHA, cấu hình checkout, submodule và lockfile nếu dự án sử dụng.
- **Đầu ra:** workspace mã nguồn đã checkout; commit SHA thực tế; thông tin phiên bản công cụ và dependency đầu vào.
- **Gate:** checkout thành công đúng commit được yêu cầu; submodule được lấy đúng revision; dependency được xác định theo lockfile; trạng thái workspace phù hợp với cách build của dự án.
- **Khi thất bại:** dừng pipeline và lưu thông tin lỗi checkout hoặc dependency resolution.

Nếu pipeline cho phép build từ tag phát hành, cần xác minh tag trỏ đến commit nào và tag có đáp ứng chính sách bảo vệ hoặc ký số của dự án hay không. Không nên âm thầm chuyển sang build commit mới nhất của nhánh khi commit ban đầu không còn truy cập được.

### 2.3. Kiểm tra chất lượng và bảo mật mã nguồn

**Mục đích:** phát hiện lỗi sớm trước khi tiêu tốn tài nguyên build và triển khai.

- **Đầu vào:** snapshot mã nguồn; cấu hình lint và static analysis; bộ test; chính sách coverage; quy tắc quét secret, dependency và lỗ hổng.
- **Đầu ra:** kết quả lint; báo cáo phân tích tĩnh; kết quả unit test và các test cần thiết khác; báo cáo coverage; kết quả quét secret và dependency.
- **Gate:** tất cả kiểm tra bắt buộc thành công; không có secret bị phát hiện; không có lỗ hổng vượt ngưỡng chính sách; coverage đáp ứng ngưỡng nếu dự án đặt ra; báo cáo được lưu để truy vết.
- **Khi thất bại:** chặn merge hoặc chặn stage tiếp theo; hiển thị lỗi và báo cáo đủ để người phát triển sửa.

Không phải dự án nào cũng cần mọi loại kiểm tra ở mọi lần chạy. Hãy xác định rõ kiểm tra nào bắt buộc cho pull request, kiểm tra nào chạy định kỳ và kiểm tra nào bắt buộc trước phát hành. Nếu một kiểm tra bị bỏ qua do cấu hình sai hoặc thiếu công cụ, pipeline cần thể hiện trạng thái “không thực hiện” thay vì coi đó là thành công.

Các test thường được chia thành nhiều lớp:

| Lớp kiểm thử | Điều được xác minh | Vị trí thường gặp |
|---|---|---|
| Unit test | Hành vi của đơn vị mã nhỏ | Mỗi pull request |
| Integration test | Tương tác giữa module hoặc dịch vụ | Pull request hoặc sau build |
| Contract test | Tương thích giữa các bên giao tiếp | Trước khi tích hợp/phát hành |
| End-to-end test | Luồng nghiệp vụ qua hệ thống | Môi trường test hoặc staging |
| Smoke test | Các chức năng và endpoint thiết yếu còn hoạt động | Ngay sau triển khai |

Kết quả test cần gắn với commit SHA và lần chạy pipeline. Một dấu tích “test passed” không có mã tham chiếu đến báo cáo cụ thể sẽ khó dùng khi điều tra sự cố.

### 2.4. Build phần mềm

**Mục đích:** biến mã nguồn đã qua kiểm tra thành sản phẩm có thể đóng gói và phát hành.

- **Đầu vào:** commit SHA; build script; dependency đã khóa phiên bản; phiên bản compiler, runtime và công cụ; tham số build không nhạy cảm.
- **Đầu ra:** binary, package hoặc image; log build; metadata về commit, công cụ và dependency; checksum hoặc digest của sản phẩm.
- **Gate:** build hoàn tất; sản phẩm đầu ra tồn tại và đúng định dạng; metadata chỉ ra đúng commit; các kiểm tra cần thiết trên sản phẩm đã hoàn tất.
- **Khi thất bại:** dừng trước bước publish; lưu log và thông tin môi trường build.

Để tăng khả năng tái lập, nên pin phiên bản công cụ và dependency, sử dụng lockfile, kiểm soát biến môi trường và tránh phụ thuộc vào trạng thái không được khai báo của máy chạy pipeline. Nếu cùng một commit và cùng đầu vào mà tạo ra kết quả khác nhau, nhóm cần biết khác biệt đến từ toolchain, dependency, cấu hình hay dữ liệu bên ngoài.

Bí mật dùng khi triển khai thường không cần thiết trong bước build. Không truyền production secret qua tham số build, không ghi secret vào log hoặc metadata và không đóng gói secret vào artifact.

### 2.5. Kiểm tra, đóng gói và lưu artifact

**Mục đích:** tạo một phiên bản bất biến có thể được kiểm tra, lưu giữ và triển khai lặp lại.

- **Đầu vào:** sản phẩm build; checksum; metadata build; chính sách lưu trữ và quét artifact.
- **Đầu ra:** artifact trong kho package/container registry; digest hoặc phiên bản bất biến; báo cáo quét; SBOM hoặc provenance nếu quy trình yêu cầu.
- **Gate:** upload thành công; có thể tải lại artifact; digest sau khi lưu khớp với digest đã tính; artifact đáp ứng chính sách bảo mật và lưu trữ.
- **Khi thất bại:** không cho triển khai; giữ log và thông tin upload để xử lý.

Artifact cần được định danh bằng digest hoặc phiên bản bất biến. Tag dễ đọc như `latest` có thể hữu ích khi tra cứu, nhưng không đủ để chứng minh chính xác nội dung đã triển khai vì tag có thể bị di chuyển. Pipeline nên lưu cả tên artifact và digest thực tế.

Một nguyên tắc quan trọng là **build một lần, promote cùng artifact qua các môi trường**. Ví dụ, image đã được kiểm thử ở staging phải là image được triển khai lên production. Nếu production build lại từ source, kết quả có thể khác với sản phẩm đã được phê duyệt.

### 2.6. Triển khai lên môi trường tích hợp hoặc kiểm thử

**Mục đích:** xác minh artifact hoạt động với cấu hình và dịch vụ phụ thuộc trong môi trường gần với thực tế.

- **Đầu vào:** artifact digest đã được chấp nhận; cấu hình môi trường; tham chiếu đến secret được cấp cho môi trường; hạ tầng và dịch vụ phụ thuộc.
- **Đầu ra:** deployment revision; môi trường và thời điểm triển khai; trạng thái rollout; log triển khai; endpoint hoặc thông tin truy cập phục vụ kiểm thử.
- **Gate:** triển khai đúng digest; workload đạt trạng thái sẵn sàng; cấu hình hợp lệ; smoke test và các kiểm tra sau triển khai thành công.
- **Khi thất bại:** dừng promotion; thu thập log và trạng thái workload; khôi phục phiên bản trước nếu thay đổi đã ảnh hưởng môi trường dùng chung.

Cấu hình có thể khác giữa development, test, staging và production, nhưng artifact cần giữ nguyên. Secret nên được lấy từ secret manager hoặc cơ chế cấp phát của nền tảng tại thời điểm triển khai. Quyền truy cập nên giới hạn theo môi trường và công việc; job test không cần quyền ghi production.

### 2.7. Phê duyệt và triển khai production

**Mục đích:** kiểm soát thời điểm phát hành và xác nhận phiên bản đã được phép đưa đến người dùng.

- **Đầu vào:** artifact digest; kết quả test và scan; kết quả xác minh staging; ghi chú phát hành; kế hoạch triển khai; kế hoạch rollback; yêu cầu thay đổi hoặc phê duyệt nếu quy trình tổ chức cần.
- **Đầu ra:** quyết định phê duyệt có danh tính và thời điểm; deployment revision production; lịch sử rollout; liên kết đến artifact và lần chạy pipeline.
- **Gate:** tất cả kiểm tra bắt buộc đã đạt; người có thẩm quyền phê duyệt đúng phạm vi; cửa sổ phát hành và điều kiện vận hành phù hợp; kế hoạch khôi phục đã sẵn sàng.
- **Khi thất bại:** không bắt đầu rollout hoặc dừng rollout theo chính sách; lưu lại lý do từ chối và bằng chứng liên quan.

Phê duyệt thủ công cần có dấu vết: ai duyệt, duyệt phiên bản nào, vào lúc nào và dựa trên những bằng chứng nào. Một nút “Approve” không gắn với artifact digest cụ thể có thể dẫn đến việc duyệt một phiên bản nhưng triển khai một phiên bản khác.

Có thể triển khai theo từng phần như rolling update, canary hoặc blue-green. Với canary, gate cần xác định khoảng quan sát, tỷ lệ traffic và ngưỡng lỗi cho phép trước khi tăng phạm vi. Với thay đổi database, cần cân nhắc tương thích ngược: triển khai ứng dụng mới và schema mới theo các bước tương thích, tránh migration phá hủy dữ liệu trước khi có đường khôi phục an toàn.

### 2.8. Xác minh sau triển khai và kết thúc phát hành

**Mục đích:** xác nhận hệ thống thực sự hoạt động sau khi rollout, thay vì chỉ xác nhận lệnh triển khai trả về thành công.

- **Đầu vào:** deployment revision; endpoint và kịch bản smoke test; health check; metric, log và trace; ngưỡng SLI/SLO hoặc ngưỡng cảnh báo của dịch vụ.
- **Đầu ra:** kết quả smoke test hoặc synthetic test; trạng thái health; số liệu quan sát trong khoảng thời gian xác định; kết luận phát hành; liên kết đến dashboard và log.
- **Gate:** endpoint thiết yếu phản hồi đúng; tỷ lệ lỗi và latency nằm trong ngưỡng; không có cảnh báo nghiêm trọng mới; các luồng nghiệp vụ quan trọng hoạt động.
- **Khi thất bại:** dừng rollout, chuyển traffic về phiên bản ổn định hoặc kích hoạt quy trình rollback/roll-forward; thông báo cho người chịu trách nhiệm theo quy trình vận hành.

Cần phân biệt trạng thái “deploy thành công” với “dịch vụ đã được xác minh”. Lệnh deploy có thể hoàn tất trong khi ứng dụng vẫn lỗi do cấu hình, kết nối database, quyền truy cập hoặc dependency bên ngoài. Vì vậy, xác minh phải kiểm tra hành vi thực tế của dịch vụ.

## 3. Bảng kiểm soát tổng hợp

Bảng sau có thể dùng làm điểm khởi đầu khi thiết kế pipeline. Tên stage có thể thay đổi, nhưng mỗi hàng cần có chủ sở hữu và bằng chứng cụ thể.

| Giai đoạn | Đầu vào chính | Đầu ra/bằng chứng | Điều kiện qua tiêu biểu |
|---|---|---|---|
| Git event | Sự kiện, ref, commit SHA, actor | Pipeline run ID, nguồn kích hoạt | Sự kiện và ref hợp lệ |
| Checkout | Repository, commit SHA, lockfile | Source snapshot, commit thực tế | Đúng commit, dependency xác định |
| Quality | Source, test và scan policy | Test report, coverage, scan report | Kiểm tra bắt buộc đạt chính sách |
| Build | Source, toolchain, build config | Binary/package/image, build metadata | Build thành công, đúng nguồn |
| Artifact | Sản phẩm build, digest | Artifact đã lưu, digest, scan result | Tải lại được, digest khớp, đạt policy |
| Test environment | Artifact digest, config, secret reference | Deployment revision, smoke-test result | Workload sẵn sàng, test đạt |
| Production release | Artifact, evidence, approval | Production revision, approval record | Được duyệt, rollout đạt ngưỡng |
| Post-deploy | Revision, health check, telemetry | Verification report, release status | Dịch vụ khỏe trong khoảng quan sát |

Không nên chỉ lưu kết quả cuối cùng của pipeline. Hãy lưu bằng chứng theo từng giai đoạn để khi một gate thất bại, nhóm biết chính xác đầu vào nào đã được dùng và điều kiện nào chưa đạt.

## 4. Giữ liên kết truy vết xuyên suốt pipeline

Một luồng phát hành có thể kiểm toán cần nối được các định danh sau:

```text
Git event
  -> repository + commit SHA
  -> pipeline run ID
  -> test / scan reports
  -> build metadata
  -> artifact name + immutable digest
  -> deployment revision + environment
  -> approval record
  -> post-deploy verification
  -> rollback hoặc release completion
```

Mỗi lần triển khai nên ghi lại tối thiểu: dịch vụ, môi trường, artifact digest, commit SHA, pipeline run ID, deployment revision, người hoặc hệ thống khởi tạo, thời điểm và kết quả xác minh. Khi có sự cố, thông tin này giúp trả lời nhanh: phiên bản nào đang chạy, nó được build từ commit nào, đã qua những kiểm tra nào và có thể quay về artifact ổn định nào.

Nếu nền tảng hỗ trợ provenance hoặc attestation, hãy gắn bằng chứng về nguồn mã, môi trường build và quy trình tạo artifact. SBOM giúp biết các thành phần phụ thuộc nằm trong sản phẩm. Những tài liệu này bổ sung cho nhau: SBOM mô tả thành phần, provenance mô tả nguồn gốc và quá trình tạo ra artifact.

## 5. Thiết kế gate an toàn và có thể vận hành

Một gate tốt cần đáp ứng các nguyên tắc sau:

1. **Có điều kiện cụ thể:** dùng kết quả test, scan, digest, health check hoặc phê duyệt có định danh; tránh điều kiện chỉ dựa vào nhận xét chủ quan.
2. **Có chính sách rõ ràng:** ghi ngưỡng lỗi, coverage, mức độ lỗ hổng, thời gian quan sát và người có quyền phê duyệt.
3. **Fail closed với kiểm tra bắt buộc:** nếu không lấy được kết quả của một kiểm tra bảo mật hoặc chất lượng bắt buộc, không coi việc thiếu dữ liệu là thành công.
4. **Có thể truy vết:** lưu log, báo cáo và định danh đầu vào/đầu ra; tránh chỉ lưu một trạng thái xanh/đỏ.
5. **Có quyền tối thiểu:** mỗi job chỉ nhận quyền cần thiết; tách quyền build, publish và deploy; bảo vệ secret và môi trường production.
6. **Có thể thử lại an toàn:** thao tác có tác dụng phụ cần được thiết kế idempotent hoặc có cơ chế nhận diện lần chạy để tránh tạo tài nguyên hay phát hành trùng.
7. **Có đường xử lý thất bại:** xác định khi nào retry, khi nào dừng, ai nhận thông báo và điều kiện nào kích hoạt rollback.

Đặc biệt, cần giới hạn nơi secret được sử dụng. Không đưa secret vào source, artifact, log, cache hoặc tham số dòng lệnh có thể bị ghi lại. Ưu tiên credential ngắn hạn hoặc cơ chế định danh workload nếu nền tảng hỗ trợ. Với pull request từ nguồn chưa tin cậy, không cấp quyền truy cập secret production hay quyền publish artifact phát hành.

## 6. Phân biệt retry, rollback và roll-forward

Ba hành động này giải quyết các loại lỗi khác nhau:

- **Retry:** chạy lại một thao tác thất bại do lỗi tạm thời, chẳng hạn registry timeout hoặc một dịch vụ kiểm thử tạm thời không sẵn sàng. Chỉ retry khi thao tác có thể lặp an toàn và có giới hạn số lần.
- **Rollback:** đưa dịch vụ về phiên bản đã biết là ổn định trước đó. Cần lưu artifact cũ, cấu hình tương ứng và cách chuyển traffic. Rollback ứng dụng không tự động đảo ngược thay đổi dữ liệu.
- **Roll-forward:** sửa lỗi bằng một phiên bản mới rồi triển khai tiếp. Cách này phù hợp khi rollback không an toàn, chẳng hạn schema hoặc dữ liệu đã thay đổi theo hướng không thể đảo ngược.

Trước khi phát hành, nhóm nên xác định điều kiện kích hoạt rollback: tỷ lệ lỗi vượt ngưỡng trong khoảng thời gian nào, health check nào thất bại, hoặc luồng nghiệp vụ nào bị ảnh hưởng. Quyết định cần dựa trên telemetry và tác động thực tế, không chỉ dựa vào trạng thái của job deploy.

## 7. Ví dụ xuyên suốt: từ pull request đến production

Giả sử nhóm phát triển một dịch vụ API và chuẩn bị phát hành commit `a1b2c3d`.

1. Một pull request được mở. Pipeline ghi nhận repository, pull request, commit SHA `a1b2c3d` và người khởi tạo.
2. Checkout xác minh workspace đúng commit. Lint, unit test, integration test và dependency scan chạy theo chính sách của dự án.
3. Khi các kiểm tra bắt buộc đạt, pipeline build image. Metadata build ghi lại commit, phiên bản toolchain và lần chạy pipeline.
4. Image được đẩy lên registry. Pipeline lưu digest, ví dụ `sha256:...`, rồi xác minh có thể tải image theo digest và kết quả scan đạt yêu cầu.
5. Cùng digest đó được triển khai lên môi trường staging. Smoke test, contract test và các kịch bản nghiệp vụ quan trọng chạy trên revision vừa triển khai.
6. Người có thẩm quyền xem báo cáo, ghi nhận phê duyệt gắn với digest và yêu cầu phát hành. Pipeline triển khai đúng digest đã được duyệt lên production.
7. Sau rollout, smoke test và telemetry được quan sát trong khoảng thời gian quy định. Nếu các ngưỡng đều đạt, release được đánh dấu hoàn tất. Nếu tỷ lệ lỗi vượt ngưỡng, pipeline dừng tăng traffic và thực hiện quy trình khôi phục đã định.

Trong ví dụ này, commit SHA cho biết mã nguồn, pipeline run ID cho biết lần xử lý, artifact digest cho biết chính xác sản phẩm, còn deployment revision cho biết phiên bản được đưa vào môi trường. Bốn định danh này phải liên kết được với nhau.

## 8. Checklist khi thiết kế hoặc rà soát pipeline

Trước khi đưa một pipeline vào sử dụng, hãy kiểm tra:

- [ ] Mỗi stage có đầu vào, đầu ra và điều kiện qua được mô tả.
- [ ] Commit SHA được ghi nhận và giữ xuyên suốt các bước.
- [ ] Các kiểm tra bắt buộc có báo cáo và chính sách ngưỡng rõ ràng.
- [ ] Build dùng toolchain và dependency có phiên bản xác định.
- [ ] Artifact có định danh bất biến và digest được lưu lại.
- [ ] Cùng một artifact được promote qua các môi trường.
- [ ] Secret được cấp theo đúng job và môi trường, với quyền tối thiểu.
- [ ] Production có cơ chế phê duyệt và lưu danh tính người duyệt.
- [ ] Sau triển khai có smoke test và kiểm tra telemetry.
- [ ] Có quy tắc retry, rollback hoặc roll-forward và biết ai chịu trách nhiệm.
- [ ] Có thể lần từ deployment đang chạy về artifact, pipeline run, báo cáo và commit nguồn.

Khi các hợp đồng này được thể hiện trong pipeline dưới dạng mã và được rà soát cùng với mã ứng dụng, CI/CD trở thành một quy trình giao phần mềm có thể lặp lại và kiểm chứng. Nhóm có thể biết mỗi thay đổi đã đi qua những bước nào, sản phẩm nào được tạo ra, vì sao nó được phép phát hành và cần làm gì khi một điều kiện không đạt.

