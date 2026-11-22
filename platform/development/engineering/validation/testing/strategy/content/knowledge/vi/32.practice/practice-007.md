# Xây lịch phản hồi và điểm chặn chất lượng cho một pipeline

Một pipeline CI/CD có thể chạy rất nhiều kiểm thử nhưng vẫn làm chậm nhóm phát triển nếu mọi kiểm tra đều chờ nhau, hoặc cho phép lỗi nghiêm trọng đi qua nếu các điểm chặn không được thiết kế rõ. Bài thực hành này hướng dẫn xây dựng một lịch phản hồi theo từng giai đoạn và xác định quality gate tương ứng. Kết quả cần trả lời được ba câu hỏi: kiểm tra nào chạy khi nào, người phát triển nhận phản hồi trong bao lâu và điều kiện nào cho phép thay đổi đi tiếp.

Bạn sẽ thiết kế pipeline cho một dịch vụ có build, unit test, API/contract test, integration test, E2E và các kiểm tra bảo mật. Bạn cũng sẽ xác định cách xử lý test thất bại, flaky, blocked hoặc chưa có bằng chứng; cách phân bổ tài nguyên; và cách đo xem lịch mới có cải thiện tốc độ mà vẫn giữ mức bảo vệ cần thiết hay không.

## 1. Mục tiêu thực hành

Sau bài này, bạn có thể:

- Phân loại kiểm thử theo thời gian phản hồi, chi phí, phụ thuộc và mức rủi ro.
- Thiết kế lịch kiểm tra cho commit, pull request, tích hợp, phát hành và sau triển khai.
- Xác định quality gate cho từng giai đoạn với điều kiện đạt, chặn và cảnh báo.
- Tính ngân sách thời gian của pipeline, kể cả khi có job chạy song song.
- Quy định cách xử lý trạng thái fail, blocked, flaky, skipped và ngoại lệ.
- Gán owner cho từng stage, test suite và quyết định chuyển giai đoạn.
- Thiết kế báo cáo và metric để đánh giá hiệu quả sau khi áp dụng.
- Tạo một kế hoạch có thể triển khai và rà soát được.

Sản phẩm đầu ra là một bản lịch pipeline, ma trận quality gate, sơ đồ luồng, quy tắc xử lý lỗi và kế hoạch đo lường. Các con số trong ví dụ là giả định để luyện tập; khi áp dụng cho hệ thống thật, cần thay bằng dữ liệu của nhóm.

## 2. Bối cảnh bài tập

Giả sử bạn phụ trách chiến lược kiểm thử cho dịch vụ Order của một nền tảng thương mại điện tử. Dịch vụ nhận yêu cầu tạo đơn, kiểm tra tồn kho, tính phí, gọi nhà cung cấp thanh toán và phát sự kiện để các dịch vụ khác xử lý.

Nhóm hiện có pipeline với các đặc điểm:

- Mỗi ngày có nhiều commit và khoảng 20–30 pull request.
- Pipeline PR hiện mất khoảng 35–50 phút, nhưng phản hồi đầu tiên thường đến sau 15 phút.
- Unit test chạy nhanh nhưng một số test cần database hoặc clock giả lập.
- API và contract test cần dịch vụ phụ thuộc hoặc container tạm.
- Integration test dùng database và message broker.
- E2E thanh toán dùng sandbox bên thứ ba, đôi khi không ổn định.
- Security scan chạy sau phần lớn test nên phát hiện vấn đề khá muộn.
- Một số suite chạy song song nhưng tranh chấp runner và dữ liệu.
- Release dự kiến mỗi tuần; có thể cần hotfix khi xảy ra sự cố.

Các hành trình và rủi ro quan trọng:

| Mã | Hành trình/rủi ro | Hậu quả nếu lỗi |
|---|---|---|
| J-01 | Tạo đơn và xác nhận đơn | Người dùng không mua được hàng hoặc đơn sai trạng thái |
| J-02 | Thanh toán và nhận callback | Giao dịch trùng, mất xác nhận hoặc sai trạng thái thanh toán |
| J-03 | Cập nhật và giữ tồn kho | Bán vượt tồn hoặc giữ hàng không được giải phóng |
| R-01 | Truy cập đơn của tenant/người dùng khác | Lộ dữ liệu và vi phạm quyền truy cập |
| R-02 | Callback thanh toán được gửi lặp | Tạo giao dịch hoặc cập nhật đơn nhiều lần |
| R-03 | Tải cao điểm làm cạn kết nối | Tăng lỗi, timeout và backlog |
| R-04 | Migration làm sai dữ liệu đơn | Mất hoặc sai lịch sử giao dịch |

Không phải mọi test đều cần chạy ở mọi commit. Tuy nhiên, các rủi ro nghiêm trọng cần có kiểm soát phù hợp và không được biến mất chỉ vì muốn rút ngắn pipeline.

## 3. Bước 1 — Kiểm kê kiểm thử và dữ liệu hiện có

Trước khi thiết kế lịch mới, lập danh sách test suite và đặc tính của chúng. Thu thập thời gian chạy từ CI trong một khoảng đủ đại diện, thay vì ước lượng từ một lần chạy thuận lợi.

### 3.1. Bảng kiểm kê

Với mỗi suite, ghi:

- Tên và mục tiêu.
- Loại kiểm thử.
- Rủi ro hoặc yêu cầu được bảo vệ.
- Trigger hiện tại.
- Thời gian chạy p50/p90 hoặc khoảng thường gặp.
- Phụ thuộc và dữ liệu cần thiết.
- Khả năng chạy song song.
- Tỷ lệ fail, flaky, blocked và retry.
- Mức độ quan trọng đối với quyết định merge/release.
- Owner và cách chẩn đoán khi thất bại.

Ví dụ:

| Suite | Loại | Thời gian điển hình | Phụ thuộc | Mục tiêu chính |
|---|---|---:|---|---|
| Format/lint | Static check | 1 phút | Không | Quy ước và lỗi cơ bản |
| Compile/build | Build | 3 phút | Dependency cache | Artifact hợp lệ |
| Unit | Unit | 4 phút | Fixture cục bộ | Logic và quy tắc nghiệp vụ |
| Component/API | Component/API | 6 phút | Container hoặc stub | Hành vi module và API |
| Contract | Contract | 4 phút | Contract registry/provider state | Tương thích consumer/provider |
| Integration | Integration | 10 phút | Database, broker | Giao tiếp giữa thành phần |
| E2E smoke | E2E | 8 phút | Môi trường tích hợp | Hành trình quan trọng |
| Full regression | Regression | 25 phút | Môi trường đầy đủ | Hồi quy phạm vi rộng |
| Security scan | Security | 7 phút | Source/dependency/build | Lỗ hổng và cấu hình |
| Load test | Performance | 20+ phút | Môi trường riêng | Năng lực và SLO |

Thời gian trong bảng không nhất thiết cộng trực tiếp thành tổng pipeline. Nếu các job chạy song song, thời gian hoàn thành phụ thuộc vào critical path, tài nguyên và các phụ thuộc giữa job.

### 3.2. Phân loại theo phản hồi

Chia kiểm tra thành ba nhóm thực dụng:

- **Nhanh:** ít phụ thuộc, phản hồi trong vài phút, phù hợp chạy thường xuyên.
- **Trung bình:** cần môi trường hoặc dịch vụ tạm, phù hợp với PR hoặc sau merge.
- **Chậm/chuyên sâu:** E2E rộng, regression lớn, performance hoặc security chuyên sâu; chạy theo lịch, trước release hoặc khi rủi ro yêu cầu.

Đây là phân loại vận hành, không phải phân cấp giá trị. Một kiểm tra chậm có thể bảo vệ rủi ro nghiêm trọng và vẫn phải có lịch chạy đủ thường xuyên.

### 3.3. Xác định kiểm tra bắt buộc

Đánh dấu test bảo vệ:

- Yêu cầu bắt buộc hoặc nghĩa vụ tuân thủ.
- Rủi ro Critical/High.
- Hành trình tạo doanh thu hoặc thay đổi dữ liệu quan trọng.
- Ranh giới API, schema hoặc event contract.
- Migration và tính toàn vẹn dữ liệu.
- Các lỗi từng gây incident hoặc defect escape nghiêm trọng.

Những kiểm tra này cần được gắn với quality gate phù hợp. Không dùng thời gian chạy làm lý do duy nhất để loại bỏ chúng.

## 4. Bước 2 — Xác định mục tiêu thời gian phản hồi

Lịch kiểm tra cần có mục tiêu thời gian cho từng điểm kiểm soát. Mục tiêu nên phản ánh mức độ cần phản hồi và khả năng sửa lỗi của người phát triển.

Ví dụ mục tiêu cho bài tập:

| Điểm kiểm soát | Mục tiêu phản hồi | Ý nghĩa |
|---|---:|---|
| Commit/feedback đầu tiên | Trong 5 phút | Phát hiện lỗi cú pháp, build và unit sớm |
| Pull request required checks | Trong 15 phút p90 | Người review không phải chờ quá lâu |
| Sau merge/integration | Trong 30 phút p90 | Xác minh tương tác trên bản dựng tích hợp |
| Release candidate | Trong 60 phút hoặc cửa sổ đã đặt | Có đủ bằng chứng trước quyết định release |
| Sau triển khai | Smoke trong vài phút đầu | Xác nhận môi trường đích hoạt động |

Đây là mục tiêu giả định, không phải chuẩn chung. Hãy chọn ngưỡng dựa trên tần suất commit, thời gian chờ hiện tại, chi phí runner và hậu quả của việc phát hiện lỗi muộn.

### 4.1. Định nghĩa thời gian rõ ràng

Ví dụ, "PR feedback time" có thể được định nghĩa:

\[
\text{PR Feedback Time} =
\text{Thời điểm required checks hoàn tất}
-
\text{Thời điểm PR sẵn sàng kiểm tra}
\]

Phải xác định "sẵn sàng kiểm tra" là lúc mở PR, lúc bỏ draft hay lúc cập nhật commit cuối cùng. Cần thống nhất cách xử lý thời gian PR ở trạng thái draft, job bị hủy và thời gian chờ runner.

Theo dõi ít nhất:

- Thời gian chờ trong queue.
- Thời gian thực thi job.
- Thời gian tổng trên critical path.
- Thời gian từ lần chạy đầu đến kết quả đáng tin cậy.

Một job chạy 3 phút nhưng chờ runner 12 phút vẫn tạo phản hồi chậm 15 phút.

### 4.2. Chọn phân vị

Không chỉ đặt mục tiêu trung bình. Dùng median/p50 để hiểu trải nghiệm điển hình và p90/p95 để biết phần lớn trường hợp có được đáp ứng không. Với ít dữ liệu, cần nêu số mẫu và không diễn giải percentile như một cam kết chắc chắn.

## 5. Bước 3 — Phân bổ kiểm tra theo giai đoạn

Thiết kế lịch sao cho mỗi stage có mục tiêu, trigger, tập kiểm tra, ngân sách thời gian, điều kiện chặn và owner.

### 5.1. Commit hoặc push

Mục tiêu: phát hiện lỗi gần thời điểm thay đổi nhất.

Chạy:

- Format và lint.
- Compile/build module bị ảnh hưởng.
- Unit test nhanh và các test cho logic thay đổi.
- Static analysis hoặc secret check nhanh.
- Kiểm tra cấu hình/schema cơ bản.

Ngân sách gợi ý: 3–5 phút cho feedback đầu tiên. Nếu suite unit vượt ngân sách, phân tích test chậm, fixture hoặc phụ thuộc; không xóa assertion quan trọng chỉ để đạt mục tiêu thời gian.

Gate:

- Build hoặc compile bắt buộc phải đạt.
- Lint rule chặn và unit test trọng yếu phải đạt.
- Secret hoặc lỗi nghiêm trọng theo chính sách phải chặn.
- Cảnh báo không chặn cần có owner hoặc quy tắc xử lý.

### 5.2. Pull request

Mục tiêu: đánh giá thay đổi trước khi hợp nhất.

Chạy:

- Unit suite của module liên quan.
- Component/API test.
- Contract test cho interface bị ảnh hưởng.
- Integration test chọn lọc với database/broker tạm.
- SAST và dependency scan theo chính sách.
- Regression chọn lọc theo dependency graph và rủi ro.

Ngân sách gợi ý: p90 không quá 15 phút cho required checks. Các suite rộng có thể tiếp tục chạy sau merge nếu không phải hard gate cho PR, nhưng cần xác định rủi ro còn lại và lý do.

Gate:

- Required checks hoàn tất và đạt.
- Không có defect Critical/High chưa được xử lý hoặc chấp nhận đúng thẩm quyền.
- Contract/API quan trọng không bị phá vỡ.
- Test bị skip, blocked hoặc quarantine phải hiển thị rõ.
- Review và phê duyệt theo chính sách nhánh hoàn tất.

### 5.3. Sau merge hoặc tích hợp

Mục tiêu: xác minh bản dựng và các thành phần hoạt động cùng nhau.

Chạy:

- Build artifact bất biến từ commit đã merge.
- Full integration test với database, broker và dịch vụ liên quan.
- System test cho các luồng quan trọng.
- E2E smoke cho tạo đơn, thanh toán và cập nhật trạng thái.
- Migration test trên dữ liệu đại diện khi có thay đổi schema.
- Một số kiểm tra resilience hoặc hiệu năng phù hợp.

Ngân sách gợi ý: p90 trong 30 phút. Có thể chia suite thành shard, nhưng cần tránh tranh chấp dữ liệu và môi trường.

Gate:

- Artifact có commit/version rõ ràng.
- Integration test trọng yếu đạt.
- Không có lỗi nghiêm trọng về tính toàn vẹn dữ liệu.
- E2E hành trình ưu tiên cao đạt hoặc có quyết định ngoại lệ hợp lệ.
- Log, metric và trace đủ để điều tra.

### 5.4. Release candidate

Mục tiêu: quyết định bản dựng có đủ bằng chứng để triển khai.

Chạy:

- Full regression suite phù hợp với phạm vi release.
- E2E cho các hành trình Critical.
- Security scan chuyên sâu hoặc kiểm thử bảo mật cần thiết.
- Performance/load test khi thay đổi ảnh hưởng năng lực.
- Migration rehearsal, backup/restore hoặc compatibility check.
- Kiểm tra cấu hình, secret, feature flag, runbook và alert.

Gate:

- Hard gate theo chính sách đạt.
- Rủi ro còn lại được owner đánh giá.
- Ngoại lệ có ID, approver, mitigation và thời hạn.
- Artifact đã kiểm thử là artifact được promote.
- Có kế hoạch rollout, dừng và phục hồi.

### 5.5. Sau triển khai

Mục tiêu: xác minh release trong môi trường đích.

Chạy:

- Health/readiness check.
- Smoke test an toàn cho API và hành trình chính.
- Kiểm tra migration và trạng thái dữ liệu.
- Theo dõi error rate, latency, saturation, queue và log.
- Synthetic transaction nếu được phép và không tạo giao dịch thật.

Gate:

- Health/readiness đạt.
- Metric nằm trong ngưỡng đã định trong cửa sổ quan sát.
- Không xuất hiện lỗi dữ liệu, bảo mật hoặc hành trình nghiêm trọng.
- Chỉ mở rộng canary khi người có quyền xác nhận điều kiện.

## 6. Lịch pipeline mẫu

Bảng dưới đây gom các quyết định vào một lịch có thể triển khai.

| Stage | Trigger | Kiểm tra | Ngân sách mục tiêu | Gate | Owner chính |
|---|---|---|---:|---|---|
| Commit | Push/commit | Lint, compile, unit nhanh, secret check | 5 phút | Build và test trọng yếu đạt | Developer |
| PR | Mở/cập nhật PR | Unit module, API, contract, SAST, regression chọn lọc | 15 phút p90 | Required checks đạt, review xong | PR owner/QA |
| Integration | Merge | Build artifact, integration, system smoke, migration liên quan | 30 phút p90 | Test tích hợp trọng yếu đạt | Service team |
| Release candidate | Tạo RC | Full regression, E2E Critical, security/performance theo rủi ro | 60 phút hoặc lịch riêng | Release gates đạt, risk owner xác nhận | Release owner |
| Post-deploy | Deploy/canary | Readiness, smoke, synthetic, observability | 5–10 phút khởi đầu | Metric và hành trình trong ngưỡng | SRE/on-call |
| Scheduled | Hằng đêm/tuần | Full regression, compatibility, soak, scan sâu | Theo cửa sổ | Issue được tạo và phân loại | QA/platform |

Một số kiểm tra có thể chạy ở nhiều giai đoạn với mục đích khác nhau. Ví dụ, contract test ở PR xác minh thay đổi consumer; contract verification sau merge xác minh artifact tích hợp; kiểm tra sau deploy xác nhận cấu hình môi trường đích.

### 6.1. Kiểm tra định kỳ

Không phải suite chậm nào cũng phải chạy trên mọi PR. Xác định lịch cho:

- Full regression mỗi đêm hoặc theo nhịp release.
- Performance/soak test trong môi trường riêng.
- Compatibility test theo ma trận phiên bản.
- Security scan sâu theo lịch và khi có thay đổi rủi ro.
- Kiểm tra khôi phục backup và disaster recovery theo kế hoạch.

Kết quả định kỳ phải được liên kết với commit, artifact và phiên bản phù hợp. Nếu code thay đổi sau lần chạy, không dùng kết quả cũ như bằng chứng tự động cho release mới.

## 7. Bước 4 — Thiết kế quality gate

Quality gate là tập điều kiện quyết định pipeline được chuyển tiếp, bị chặn hoặc cần đánh giá. Mỗi gate cần có:

- Tên và mục tiêu.
- Phạm vi áp dụng.
- Điều kiện pass.
- Điều kiện fail/block.
- Ngưỡng cảnh báo.
- Nguồn bằng chứng.
- Owner.
- Cách xử lý ngoại lệ.
- Hành động khi gate không đạt.

### 7.1. Phân loại gate

| Loại | Ý nghĩa | Ví dụ |
|---|---|---|
| Hard gate | Không đạt thì dừng chuyển giai đoạn | Unit test bắt buộc fail; phát hiện secret; lỗi phân quyền nghiêm trọng |
| Conditional gate | Chỉ tiếp tục khi có mitigation và phê duyệt đúng thẩm quyền | Sandbox vendor tạm gián đoạn nhưng có bằng chứng thay thế và rollout giới hạn |
| Advisory gate | Cảnh báo cần theo dõi, không tự động chặn | Cảnh báo maintainability chưa vượt ngưỡng |
| Operational gate | Điều kiện trong lúc triển khai/vận hành | Error rate hoặc latency vượt ngưỡng thì dừng canary |

Không thay đổi hard gate thành advisory chỉ vì release đang trễ. Nếu muốn đổi chính sách, cần review và phê duyệt trước khi áp dụng.

### 7.2. Đặt ngưỡng có căn cứ

Ngưỡng có thể dựa trên:

- SLO hoặc SLA.
- Baseline và biến động lịch sử.
- Mức độ nghiêm trọng của rủi ro.
- Khả năng phát hiện và phục hồi.
- Chi phí của false positive và false negative.
- Nghĩa vụ pháp lý, hợp đồng hoặc chính sách.

Ví dụ, có thể đặt ngưỡng p95 latency, error rate hoặc test coverage theo dữ liệu của hệ thống. Không lấy một con số chung từ dự án khác mà không kiểm tra workload và môi trường.

### 7.3. Tránh gate quá rộng

Một gate "mọi test phải xanh" nghe có vẻ rõ nhưng có thể không đủ chính xác. Cần xác định:

- Test nào bắt buộc ở stage này?
- Test nào chỉ chạy định kỳ?
- Test nào được quarantine?
- Test nào có thể bỏ qua với phê duyệt?
- Kết quả nào thuộc build hiện tại?
- Khi thiếu dữ liệu hoặc hệ thống test không khả dụng thì xử lý ra sao?

Gate cần phản ánh chính sách thật, không phụ thuộc vào việc người vận hành nhớ các ngoại lệ ngầm.

## 8. Quy tắc xử lý trạng thái kiểm thử

Không nên gom mọi trạng thái thành pass/fail duy nhất. Quy định hành động cho từng trạng thái:

| Trạng thái | Ý nghĩa | Hành động gợi ý |
|---|---|---|
| Passed | Test chạy và đạt | Tiếp tục nếu các gate khác đạt |
| Failed | Test chạy và phát hiện sai lệch | Chặn theo mức độ; tạo defect và điều tra |
| Blocked | Không thể chạy do môi trường/dữ liệu/phụ thuộc | Không coi là pass; sửa nguyên nhân hoặc đánh giá ngoại lệ |
| Flaky | Kết quả không ổn định giữa các lần chạy tương đương | Ghi nhận, điều tra và theo dõi; không che bằng retry |
| Skipped | Không chạy theo cấu hình hoặc điều kiện | Xác định lý do, phạm vi thiếu và quyền cho phép |
| Quarantined | Tạm cách ly test đã xác nhận không đáng tin | Hiển thị khoảng trống, owner và hạn khắc phục |
| Cancelled | Bị hủy do thao tác hoặc điều phối | Xác định có cần chạy lại hay không |

### 8.1. Retry có kiểm soát

Retry có thể giúp phân biệt lỗi tạm thời với lỗi ổn định, nhưng không nên biến lần retry thành pass không dấu vết. Lưu kết quả lần đầu, số lần retry và kết quả cuối. Nếu test bắt buộc chỉ pass sau retry, cần quy định đó có được chấp nhận hay không và theo dõi tỷ lệ flaky.

### 8.2. Quarantine

Khi quarantine:

- Ghi test ID và lý do.
- Ghi owner sửa và thời hạn.
- Xác định yêu cầu/rủi ro/hành trình bị ảnh hưởng.
- Chọn kiểm tra thay thế nếu có.
- Hiển thị trạng thái trên dashboard release.
- Chạy lại và gỡ quarantine khi có bằng chứng ổn định.

Không quarantine hàng loạt để làm pipeline xanh. Nếu nhiều test bị ảnh hưởng bởi môi trường chung, xử lý nguyên nhân ở môi trường.

### 8.3. Ngoại lệ có thời hạn

Một conditional gate cần exception ID, phạm vi, approver, mitigation, owner và ngày hết hạn. Pipeline phải kiểm tra ngoại lệ còn hiệu lực trước khi cho phép đi tiếp. Ngoại lệ không thay đổi kết quả test gốc.

## 9. Bước 5 — Tính critical path và phân bổ tài nguyên

Tổng thời gian pipeline không đơn giản là tổng thời gian từng test nếu có chạy song song.

### 9.1. Tính critical path

Giả sử:

- Lint và compile chạy song song, mất 1 và 3 phút.
- Unit test bắt đầu sau compile, mất 4 phút.
- API và contract test chạy song song sau unit, mất 6 và 4 phút.
- Integration test chạy sau API/contract, mất 10 phút.

Thời gian theo chuỗi phụ thuộc là:

\[
T = \max(1,3) + 4 + \max(6,4) + 10 = 23 \text{ phút}
\]

Nếu có job độc lập chạy song song với integration và hoàn tất trước khi gate tổng hợp, thời gian thực tế phụ thuộc vào nhánh lâu nhất. Cần dùng DAG để thấy critical path thay vì cộng tất cả job.

### 9.2. Kiểm soát tài nguyên

Chạy song song có thể làm thời gian giảm nhưng tăng tranh chấp. Theo dõi:

- CPU, RAM và throttling của runner.
- Database connection, lock và I/O.
- Browser worker và số phiên.
- Network, socket và quota API.
- Dữ liệu dùng chung và khả năng va chạm.
- Queue time và số job chờ.

Giới hạn concurrency theo tài nguyên thực. Dùng namespace, schema, tenant hoặc dataset riêng khi cần. Những test cố ý kiểm tra race condition có thể chia sẻ dữ liệu nhưng phải có thiết kế rõ.

### 9.3. Tối ưu đúng điểm nghẽn

Nếu queue time cao, tăng runner hoặc điều chỉnh lịch có thể hiệu quả. Nếu một test suite chiếm phần lớn critical path, tối ưu test đó. Nếu database bị bão hòa, chạy song song thêm job có thể làm pipeline chậm hơn. Luôn đo trước khi thay đổi.

## 10. Bước 6 — Vẽ pipeline và các điểm chặn

Sơ đồ dưới đây thể hiện một pipeline tham khảo. Các job độc lập có thể chạy song song; gate chỉ mở khi các điều kiện bắt buộc của stage đạt.

~~~mermaid
flowchart TD
    A["Commit / Push"]
    B["Lint + Secret scan"]
    C["Compile / Build"]
    D["Unit tests"]
    E{"Commit gate"}
    F["Pull request"]
    G["API + Component"]
    H["Contract tests"]
    I["SAST + Dependency scan"]
    J{"PR gate + review"}
    K["Merge"]
    L["Build immutable artifact"]
    M["Integration tests"]
    N["System / E2E smoke"]
    O{"Integration gate"}
    P["Release candidate"]
    Q["Regression + E2E Critical"]
    R["Security / Performance / Migration"]
    S{"Release Go/No-Go"}
    T["Deploy canary"]
    U["Readiness + Smoke + Metrics"]
    V{"Operational gate"}
    W["Mở rộng rollout"]
    X["Dừng rollout / Rollback / Incident"]
    A --> B
    A --> C --> D
    B --> E
    D --> E
    E -->|Pass| F
    E -->|Fail| X
    F --> G
    F --> H
    F --> I
    G --> J
    H --> J
    I --> J
    J -->|Pass| K --> L
    J -->|Fail| X
    L --> M
    L --> N
    M --> O
    N --> O
    O -->|Pass| P
    O -->|Fail| X
    P --> Q
    P --> R
    Q --> S
    R --> S
    S -->|Go| T --> U --> V
    S -->|No-Go| X
    V -->|Pass| W
    V -->|Fail| X
~~~

Sơ đồ là cơ sở thảo luận. Khi triển khai, cần thêm trigger cụ thể, điều kiện phụ thuộc, timeout, cancel policy, thông báo và liên kết artifact.

## 11. Bước 7 — Xây ma trận quality gate

Điền ma trận theo pipeline của nhóm. Ví dụ:

| Gate | Điều kiện đạt | Điều kiện chặn | Người xác nhận |
|---|---|---|---|
| Commit gate | Build, lint và unit trọng yếu đạt | Compile fail, secret, test Critical fail | Developer/CI |
| PR gate | Required checks đạt, review hoàn tất | Contract break, security High/Critical, test bắt buộc fail | PR owner/QA/Security |
| Integration gate | Artifact hợp lệ, integration và smoke đạt | Lỗi dữ liệu, giao tiếp hoặc hành trình trọng yếu | Service owner/QA |
| Release gate | Regression và kiểm tra bắt buộc đạt, risk review hoàn tất | Hard gate fail, rủi ro không được chấp nhận | Release decision owner |
| Operational gate | Readiness và metric trong ngưỡng | Error/latency/data integrity vượt ngưỡng | SRE/on-call |

### 11.1. Mẫu định nghĩa một gate

~~~yaml
gate:
  id: PR-QUALITY-GATE
  stage: pull-request
  scope:
    - order-service
  required_checks:
    - unit-critical
    - api-contract
    - sast
  blocking_conditions:
    - critical_test_failed
    - incompatible_contract
    - secret_detected
  advisory_conditions:
    - maintainability_warning
  exception_policy:
    requires_id: true
    requires_approver: true
    requires_expiry: true
  owner: service-team
~~~

Đây là cấu trúc minh họa, không phải schema dành cho một nền tảng CI cụ thể. Khi triển khai thật, cần chuyển thành cấu hình được công cụ hỗ trợ và review quyền bypass.

### 11.2. Kiểm tra gate có thể kiểm chứng

Với từng điều kiện, hãy trả lời:

- Dữ liệu lấy từ đâu?
- Điều kiện được tính như thế nào?
- Ai có quyền thay đổi ngưỡng?
- Khi thiếu dữ liệu thì gate xử lý ra sao?
- Có thể tái hiện quyết định từ log không?
- Có thể bypass không, và ai phê duyệt?
- Bằng chứng được lưu bao lâu?

Nếu câu trả lời mơ hồ, gate chưa sẵn sàng để đưa vào pipeline.

## 12. Bước 8 — Phân vai và quy trình xử lý khi gate không đạt

| Hoạt động | Developer | QA/Test owner | Security | SRE/Platform | Release owner |
|---|---|---|---|---|---|
| Sửa lỗi build/unit | A/R | C | I | C | I |
| Điều tra flaky test | R | A/R | I | C | I |
| Xử lý lỗ hổng | R | C | A | C | I |
| Sửa môi trường/runner | C | C | I | A/R | I |
| Đánh giá regression | R | A/R | C | C | I |
| Quyết định release | C | C | C | C | A |
| Dừng rollout | R | C | C | A/R | I |

Ma trận này cần được điều chỉnh theo chính sách. Mỗi hoạt động có một người chịu trách nhiệm cuối cùng rõ ràng.

### 12.1. Quy trình khi fail

1. Pipeline giữ nguyên kết quả gốc và dừng ở gate tương ứng.
2. Tạo hoặc cập nhật defect với test ID, run ID, commit và log.
3. Phân loại lỗi sản phẩm, test, dữ liệu, môi trường hay phụ thuộc.
4. Giao owner và mức ưu tiên.
5. Sửa nguyên nhân và chạy lại phạm vi cần thiết.
6. Xác minh gate được mở lại bằng bằng chứng mới.

### 12.2. Quy trình khi blocked

Không thể chạy test không có nghĩa test đạt. Owner môi trường hoặc phụ thuộc cần xử lý. Nếu release có lý do phải tiếp tục, cần đánh giá ngoại lệ theo chính sách, chỉ rõ phần bằng chứng còn thiếu và mitigation.

### 12.3. Quy trình khi có bất đồng

QA có thể khuyến nghị No-Go trong khi product muốn tiếp tục. Các bên cần xem lại hard gate, rủi ro, bằng chứng và thẩm quyền. Không dùng im lặng làm đồng ý. Decision owner ghi quyết định, điều kiện và người chịu trách nhiệm.

## 13. Bước 9 — Đo hiệu quả lịch mới

Sau khi triển khai lịch, so sánh với baseline bằng cùng định nghĩa.

### 13.1. Chỉ số chính

- PR feedback time p50/p90.
- Tổng thời gian critical path.
- Queue time và execution time.
- Tỷ lệ required checks hoàn tất trong mục tiêu.
- Thời gian từ fail đến khi có owner.

### 13.2. Chỉ số bảo vệ

- Defect escape sau merge/release.
- Risk coverage cho rủi ro High/Critical.
- Tỷ lệ test skip, blocked, flaky và quarantine.
- Tỷ lệ rollback/hotfix.
- Tỷ lệ hành trình quan trọng có bằng chứng đạt.
- Chi phí runner và thời gian bảo trì test.

### 13.3. So sánh trước và sau

Ví dụ minh họa:

| Chỉ số | Trước | Sau | Diễn giải |
|---|---:|---:|---|
| PR feedback p90 | 28 phút | 14 phút | Cải thiện tốc độ |
| Critical path | 42 phút | 26 phút | Giảm thời gian tổng |
| Flaky rate | 3,5% | 2,0% | Độ ổn định tốt hơn |
| Test skipped | 0,4% | 1,6% | Cần điều tra tăng skip |
| Defect escape/100 PR | 2,0 | 2,4 | Guardrail suy giảm |
| Risk coverage High/Critical | 98% | 92% | Không đủ căn cứ mở rộng |

Kết quả cho thấy lịch mới nhanh hơn nhưng có dấu hiệu suy giảm bao phủ và lỗi lọt. Không nên tuyên bố thành công chỉ dựa vào thời gian. Cần tìm nguyên nhân test bị skip, phục hồi kiểm tra rủi ro cao và đo lại.

### 13.4. Điều kiện mở rộng

Chỉ mở rộng lịch mới khi:

- Chỉ số tốc độ đạt mục tiêu.
- Hard gate vẫn bảo vệ yêu cầu và rủi ro bắt buộc.
- Guardrail không vượt ngưỡng.
- Test skip/quarantine có owner và thời hạn.
- Tài nguyên pipeline ổn định.
- Có bằng chứng qua đủ số lần chạy và chu kỳ phù hợp.

## 14. Bài tập thực hành theo nhóm

Thực hiện bài tập trong một buổi workshop hoặc chia thành các phiên ngắn.

### Phần A — Kiểm kê

1. Liệt kê tối thiểu 8 test suite hiện có hoặc dự kiến.
2. Ghi thời gian p50/p90, phụ thuộc và owner.
3. Đánh dấu test bảo vệ rủi ro Critical/High.
4. Xác định test nào đang flaky, blocked hoặc bị skip.

Đầu ra: bảng inventory test suite.

### Phần B — Thiết kế lịch

1. Chọn trigger cho commit, PR, merge, release và post-deploy.
2. Phân bổ từng suite vào stage.
3. Xác định ngân sách phản hồi và critical path.
4. Chọn suite chạy song song và giới hạn concurrency.
5. Đặt lịch cho full regression, performance và security test chuyên sâu.

Đầu ra: bảng lịch pipeline.

### Phần C — Thiết kế quality gate

1. Viết điều kiện pass và block cho từng stage.
2. Phân biệt hard, conditional, advisory và operational gate.
3. Định nghĩa xử lý fail, blocked, flaky, skipped và quarantine.
4. Xác định quyền bypass, approver và hạn ngoại lệ.
5. Gán owner cho gate và hành động khi không đạt.

Đầu ra: ma trận gate và quy tắc xử lý trạng thái.

### Phần D — Kiểm tra tình huống

Xử lý các tình huống sau:

**Tình huống 1:** Unit test Critical thất bại trên PR. Developer cho rằng test sai do clock của máy CI.

- Gate nào chặn?
- Cần bằng chứng gì để phân loại lỗi test hay lỗi sản phẩm?
- Ai là owner điều tra?
- Điều kiện nào cho phép chạy lại?

**Tình huống 2:** Sandbox thanh toán bị gián đoạn trước release, contract test đạt nhưng E2E chưa chạy.

- E2E có phải hard gate không?
- Có kiểm tra thay thế nào?
- Ai có quyền chấp nhận rủi ro?
- Mitigation, giới hạn rollout và ngày hết hạn là gì?

**Tình huống 3:** Pipeline nhanh hơn 30% nhưng test skip tăng gấp ba.

- Có thể kết luận cải thiện không?
- Cần phân tích những nhóm test nào?
- Guardrail nào đã bị vi phạm?
- Điều kiện nào phải đạt trước khi mở rộng?

**Tình huống 4:** Sau deploy, error rate tăng vượt ngưỡng trong canary.

- Ai có quyền dừng?
- Ngưỡng và khoảng thời gian quan sát được xác định ở đâu?
- Rollback hay roll-forward?
- Cần lưu bằng chứng và thông báo cho ai?

Đầu ra: quyết định và lý do cho từng tình huống.

### Phần E — Kế hoạch đo lường

1. Chọn baseline ít nhất một chu kỳ đại diện.
2. Chốt định nghĩa PR feedback p90, defect escape và risk coverage.
3. Xác định chỉ số chính và guardrail.
4. Đặt thời gian thử nghiệm và số quan sát tối thiểu.
5. Xác định ai tổng hợp và ai quyết định giữ/mở rộng lịch mới.

Đầu ra: kế hoạch đánh giá trước/sau.

## 15. Mẫu tài liệu lịch phản hồi và quality gate

Có thể dùng mẫu sau làm điểm bắt đầu:

~~~text
PIPELINE: <service/repository>
VERSION: <policy version>
OWNER: <pipeline owner>

GOAL:
  - First feedback target:
  - PR required-check target:
  - Integration target:
  - Release readiness target:

STAGE:
  name:
  trigger:
  required_checks:
  scheduled_checks:
  time_budget:
  blocking_conditions:
  advisory_conditions:
  evidence_location:
  responsible:
  accountable:
  failure_action:
  exception_policy:

OBSERVABILITY:
  - queue_time
  - execution_time
  - critical_path
  - pass_fail_blocked_skipped
  - flaky_rate
  - defect_escape
  - risk_coverage

REVIEW:
  baseline_window:
  evaluation_window:
  guardrail_thresholds:
  review_owner:
  decision_date:
~~~

Mỗi stage nên có một bản ghi riêng. Không để trường owner hoặc điều kiện chặn trống ở các gate quan trọng.

## 16. Tiêu chí tự đánh giá kết quả

Đánh giá bản thiết kế theo các câu hỏi:

| Tiêu chí | Đạt khi |
|---|---|
| Phân tầng phản hồi | Kiểm tra nhanh chạy sớm; suite rộng có lịch và lý do rõ |
| Bao phủ rủi ro | Rủi ro Critical/High có test hoặc biện pháp phù hợp |
| Thời gian | Có ngân sách, định nghĩa và cách đo p50/p90 |
| Quality gate | Mỗi stage có pass/block/advisory rõ |
| Trạng thái test | Fail, blocked, flaky, skipped và quarantine được phân biệt |
| Tài nguyên | Concurrency và dữ liệu được quản lý |
| Ownership | Có Responsible và Accountable cho từng quyết định |
| Ngoại lệ | Có ID, approver, mitigation, owner và expiry |
| Truy vết | Kết quả gắn với commit, build, artifact và release |
| Đo hiệu quả | Có baseline, guardrail và tiêu chí mở rộng |

Nếu một tiêu chí chưa đạt, ghi rõ khoảng trống và hành động cần thực hiện. Không tự chấm đạt chỉ vì đã có một mục trong tài liệu.

## 17. Những lỗi thiết kế cần tránh

- **Đưa mọi test vào PR:** làm feedback chậm và tạo hàng đợi lớn.
- **Chỉ chạy test nhanh:** bỏ sót tích hợp, migration, E2E và rủi ro phi chức năng.
- **Không có lịch định kỳ:** suite chậm dễ bị quên hoặc chỉ chạy trước release.
- **Gate không có owner:** khi fail không ai chịu trách nhiệm xử lý.
- **Coi blocked là pass:** tạo khoảng trống bằng chứng không được thể hiện.
- **Retry cho đến khi xanh:** che flaky test và làm sai lệch tín hiệu.
- **Quarantine không thời hạn:** biến ngoại lệ tạm thành bỏ qua vĩnh viễn.
- **Chỉ đo thời gian trung bình:** bỏ qua queue time và phần đuôi chậm.
- **Chạy song song không giới hạn:** runner, database hoặc dữ liệu bị tranh chấp.
- **Gate dùng ngưỡng tùy tiện:** không phản ánh baseline hoặc rủi ro.
- **Artifact build lại sau khi test:** release có thể không phải artifact đã xác minh.
- **Không đo guardrail:** pipeline nhanh hơn nhưng chất lượng suy giảm.
- **Không có quyền dừng rollout:** phản ứng chậm khi metric sau deploy vượt ngưỡng.

## 18. Checklist hoàn tất bài thực hành

- [ ] Đã kiểm kê suite, thời gian, phụ thuộc, trạng thái và owner.
- [ ] Đã phân loại test nhanh, trung bình và chuyên sâu.
- [ ] Đã xác định yêu cầu, rủi ro và hành trình bắt buộc.
- [ ] Đã đặt mục tiêu phản hồi theo từng stage.
- [ ] Đã định nghĩa cách đo queue time, execution time và critical path.
- [ ] Đã phân bổ test cho commit, PR, integration, release và post-deploy.
- [ ] Đã lên lịch cho full regression và kiểm tra chuyên sâu.
- [ ] Đã xác định hard, conditional, advisory và operational gate.
- [ ] Mỗi gate có điều kiện pass, block, evidence và owner.
- [ ] Đã quy định cách xử lý fail, blocked, flaky, skipped và quarantine.
- [ ] Ngoại lệ có ID, approver, mitigation và expiry.
- [ ] Đã kiểm soát concurrency, runner và dữ liệu dùng chung.
- [ ] Đã có sơ đồ pipeline thể hiện dependency và critical path.
- [ ] Đã có RACI hoặc bảng ownership.
- [ ] Đã xác định quyền dừng, rollback và tiếp tục rollout.
- [ ] Đã chọn metric chính và guardrail.
- [ ] Đã có baseline, cửa sổ đo và tiêu chí mở rộng.
- [ ] Đã lưu mẫu lịch, gate và quyết định để nhóm sử dụng.

## 19. Kết quả bàn giao

Khi kết thúc bài thực hành, nhóm cần bàn giao tối thiểu:

1. **Inventory test suite:** tên, mục tiêu, thời gian, phụ thuộc, owner và mức rủi ro.
2. **Lịch phản hồi:** trigger, stage, suite, ngân sách và lịch định kỳ.
3. **Ma trận quality gate:** điều kiện đạt/chặn/cảnh báo, bằng chứng và quyền quyết định.
4. **Sơ đồ pipeline:** dependency, nhánh song song và critical path.
5. **Quy tắc xử lý trạng thái:** fail, blocked, flaky, skipped, quarantine và exception.
6. **Ma trận ownership:** người thực hiện, người chịu trách nhiệm và người phê duyệt.
7. **Kế hoạch đo lường:** baseline, metric, guardrail, thời gian và tiêu chí đánh giá.
8. **Danh sách hành động:** khoảng trống, owner và hạn hoàn tất.

Lịch phản hồi tốt đưa lỗi dễ phát hiện đến người phát triển sớm, giữ các kiểm tra sâu ở đúng điểm kiểm soát và làm rõ điều kiện để thay đổi đi tiếp. Quality gate tốt bảo vệ rủi ro quan trọng, thể hiện trung thực những gì chưa được kiểm chứng và chỉ cho phép ngoại lệ trong phạm vi có trách nhiệm. Khi lịch, gate, owner và metric được thiết kế cùng nhau, pipeline vừa hỗ trợ tốc độ phát triển vừa cung cấp bằng chứng đáng tin cậy cho quyết định chất lượng.
