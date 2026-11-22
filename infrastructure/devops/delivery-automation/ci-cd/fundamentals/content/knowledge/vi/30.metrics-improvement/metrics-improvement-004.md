# Đo thời gian phản hồi, độ ổn định kiểm thử và thời gian chờ

Một pipeline CI/CD có thể chạy thành công nhưng vẫn khiến nhóm phát triển mất nhiều thời gian. Pull request phải chờ runner; job kiểm thử chạy nhanh nhưng kết quả thường xuyên thất thường; pipeline báo lỗi sau hàng chục phút dù một kiểm tra đơn giản đã có thể phát hiện lỗi từ đầu. Nếu chỉ nhìn trạng thái xanh/đỏ hoặc thời gian tổng, nhóm khó biết cần cải thiện ở đâu.

Để cải thiện CI/CD, cần đo ít nhất ba khía cạnh:

- **Thời gian phản hồi:** từ khi có sự kiện kích hoạt đến khi người phát triển nhận được phản hồi có thể hành động, và thời gian đến kết quả cuối cùng.
- **Độ ổn định kiểm thử:** mức độ kết quả test có thể lặp lại trong cùng điều kiện, tỷ lệ lỗi chập chờn, retry và test bị bỏ qua.
- **Thời gian chờ:** thời gian pipeline/job không thực sự làm việc vì chờ runner, môi trường, dependency, approval hoặc tài nguyên dùng chung.

Đây là một phần của năng lực **DEVOPS_CI_CD_FUNDAMENTALS**: xây dựng tư duy CI/CD từ sự kiện Git, pipeline dưới dạng mã, build và kiểm thử tự động đến quản lý artifact, môi trường, quality gate và phát hành có truy vết. Đo lường giúp xác định nút thắt, ưu tiên cải tiến và kiểm tra xem thay đổi có thực sự làm luồng phát hành tốt hơn hay không.

## 1. Đo lường để đưa ra quyết định nào?

Metric chỉ hữu ích khi gắn với một câu hỏi vận hành hoặc cải tiến cụ thể:

| Câu hỏi | Chỉ số cần xem | Quyết định có thể đưa ra |
| --- | --- | --- |
| Người phát triển phải chờ bao lâu để biết PR có lỗi? | Time to first feedback | Đưa lint, compile và test nhanh lên đầu pipeline |
| Một pipeline mất bao lâu để hoàn tất? | End-to-end pipeline duration | Phân tích critical path, job chậm và dependency |
| Test có thường xuyên thất thường không? | First-pass pass rate, flaky failure, retry-rescue rate | Sửa test, fixture, môi trường hoặc test data |
| Job đang mất thời gian chờ ở đâu? | Queue wait, runner provisioning, approval wait, environment wait | Tăng năng lực runner, cải thiện lịch hoặc tự động hóa cấp môi trường |
| Release có nhanh hơn mà vẫn an toàn không? | Pipeline metrics kết hợp quality, failure và recovery metrics | Đánh giá trade-off và tiếp tục/đảo ngược cải tiến |

Không tối ưu một chỉ số riêng lẻ. Rút ngắn pipeline bằng cách bỏ test có thể làm thời gian xanh nhanh hơn nhưng tăng lỗi sau triển khai. Tăng retry có thể làm tỷ lệ pipeline xanh cao hơn nhưng che giấu test không ổn định. Cải tiến phải xem thời gian, độ tin cậy và chất lượng cùng lúc.

## 2. Phân biệt các mốc thời gian của pipeline

Một pipeline có nhiều khoảng thời gian khác nhau. Cần định nghĩa mốc bắt đầu và kết thúc trước khi tính metric.

| Khoảng thời gian | Bắt đầu | Kết thúc | Ý nghĩa |
| --- | --- | --- | --- |
| Trigger-to-first-feedback | Sự kiện push/PR được CI nhận | Kết quả đầu tiên có thể hành động được | Người phát triển chờ phản hồi ban đầu |
| Pipeline duration | Pipeline được tạo/kích hoạt | Pipeline kết thúc | Thời gian tường của toàn bộ pipeline |
| Job queue wait | Job đủ điều kiện chạy và được xếp hàng | Runner/executor nhận job | Chờ năng lực thực thi |
| Runner provisioning | Runner được cấp hoặc chọn | Executor sẵn sàng chạy lệnh | Thời gian khởi tạo môi trường chạy |
| Job execution | Lệnh/job bắt đầu | Job kết thúc | Thời gian thực thi thực tế, bao gồm setup trong job |
| Approval wait | Yêu cầu approval được tạo | Người có quyền quyết định | Thời gian chờ quyết định thủ công |
| Environment wait | Yêu cầu môi trường được gửi | Môi trường/lock được cấp | Chờ môi trường hoặc tài nguyên dùng chung |
| Pipeline completion feedback | Pipeline bắt đầu | Kết quả cuối cùng được công bố | Thời gian đến quyết định cuối |

**Trigger-to-first-feedback** không nhất thiết là thời gian pipeline chạy xong. Nếu lint và compile có thể trả kết quả sau ba phút trong khi integration test mất hai mươi phút, phản hồi ban đầu có thể đến sớm hơn nhiều so với kết quả cuối cùng.

### 2.1. Thời gian tường và tổng thời gian job

Với các job chạy song song, tổng thời lượng của từng job cộng lại có thể lớn hơn thời gian thực tế người dùng chờ pipeline. Ví dụ, hai job mất 8 và 10 phút chạy song song; pipeline có thể chỉ mất khoảng 10 phút cộng thời gian điều phối.

Vì vậy cần phân biệt:

- **Wall-clock duration:** thời gian từ lúc pipeline bắt đầu đến lúc kết thúc.
- **Sum of job durations:** tổng thời lượng thực thi của tất cả job.
- **Critical path:** chuỗi job/dependency quyết định thời điểm pipeline có thể hoàn tất.

Muốn rút ngắn wall-clock duration, hãy tìm job hoặc dependency trên critical path. Tối ưu một job không nằm trên critical path có thể giảm chi phí runner nhưng không làm người phát triển nhận kết quả sớm hơn.

## 3. Đo thời gian phản hồi (pipeline responsiveness)

Thời gian phản hồi phản ánh tốc độ CI cung cấp thông tin sau một thay đổi. Có thể theo dõi hai chỉ số chính:

**Time to first actionable feedback**

\[
T_{first} = t_{first\_feedback} - t_{trigger}
\]

Phản hồi có thể hành động là kết quả giúp người phát triển quyết định sửa code, xem log hoặc tiếp tục chờ các kiểm tra còn lại. Ví dụ: lint fail, compile fail hoặc unit test nhanh đã có kết quả.

**End-to-end pipeline duration**

\[
T_{pipeline} = t_{completed} - t_{trigger}
\]

Chỉ số này đo thời gian từ trigger đến trạng thái cuối cùng, bao gồm cả queue, job execution, approval và các khoảng chờ nằm trong pipeline theo định nghĩa của hệ thống.

Không nên tính thời gian từ lúc runner bắt đầu chạy rồi gọi đó là pipeline response time, vì cách đo này bỏ qua thời gian người phát triển phải chờ runner.

### 3.1. Chọn mốc first feedback nhất quán

Định nghĩa rõ loại phản hồi nào được tính:

- Lint/static check có thể phát hiện lỗi nhanh.
- Compile/build validation.
- Unit test cốt lõi.
- Policy check hoặc secret scan.
- Kết quả tổng hợp đầu tiên của required checks.

Không tính một log “job started” là feedback; nó không cho biết thay đổi có hợp lệ hay không. Cũng không nên tính một job tùy chọn hoàn tất trước required check nhưng không cung cấp thông tin hữu ích.

Có thể đo riêng time-to-first-failure và time-to-first-success. Lỗi được phát hiện sớm giúp sửa nhanh; kết quả pass đầu tiên giúp biết có thể tiếp tục review hoặc merge theo policy.

### 3.2. Dùng percentile thay vì chỉ dùng trung bình

Thời gian pipeline thường có phân phối lệch: phần lớn chạy nhanh, một số lần bị queue dài hoặc runner lỗi kéo dài. Trung bình có thể che khuất trải nghiệm của phần lớn người dùng hoặc nhóm phải chịu các lần chậm nhất.

| Chỉ số | Cách diễn giải |
| --- | --- |
| p50 | Một nửa số lần chạy hoàn tất trong thời gian này hoặc nhanh hơn |
| p90 | 90% số lần chạy hoàn tất trong thời gian này hoặc nhanh hơn |
| p95 | 95% số lần chạy hoàn tất trong thời gian này hoặc nhanh hơn |
| Maximum | Trường hợp chậm nhất trong cửa sổ dữ liệu; nhạy với ngoại lệ |

Theo dõi p50 để hiểu trải nghiệm điển hình và p90/p95 để phát hiện nhóm pipeline có thời gian chờ hoặc thực thi kéo dài. Luôn hiển thị số mẫu và khoảng thời gian đo; p95 từ 10 lần chạy không ổn định như p95 từ hàng nghìn lần chạy.

## 4. Đo độ ổn định kiểm thử

Test ổn định khi cùng một phiên bản mã, cùng điều kiện và dữ liệu kiểm thử tương đương cho kết quả nhất quán. Một test thất bại rồi pass khi chạy lại mà không có thay đổi liên quan có thể là flaky test, nhưng cũng có thể do dependency hoặc hạ tầng không ổn định.

Không nên coi mọi lần retry thành công là bằng chứng chắc chắn test flaky. Cần phân loại nguyên nhân và giữ lại kết quả lần chạy đầu.

### 4.1. Các chỉ số test reliability

| Chỉ số | Công thức/định nghĩa | Điều cần chú ý |
| --- | --- | --- |
| First-pass pass rate | Số test pass ở lần chạy đầu / tổng test được thực thi lần đầu | Không tính test bị skip như pass |
| First-pass failure rate | Số test fail ở lần đầu / tổng test được thực thi lần đầu | Phân loại product failure, test defect và infrastructure failure |
| Retry-rescue rate | Số test fail lần đầu nhưng pass ở lần retry / số test có retry sau fail | Là tín hiệu nghi ngờ flakiness, không phải kết luận cuối cùng |
| Confirmed flaky-test rate | Số test ID có kết quả không nhất quán trong các lần chạy cùng điều kiện / số test ID được chạy lặp đủ điều kiện | Cần định nghĩa cửa sổ và điều kiện so sánh |
| Retry rate | Số test/job có retry / số test/job đủ điều kiện | Retry cao có thể che giấu độ bất ổn |
| Skip rate | Số test bị skip/disabled / tổng test dự kiến | Giúp phát hiện độ bao phủ bị giảm |

Ví dụ: trong một ngày có 1.000 test case chạy lần đầu; 970 pass, 30 fail. Giả sử cả 30 test fail đều được chạy lại và 18 test pass ở lần retry. First-pass pass rate là 97%; retry-rescue rate là 60% trong nhóm 30 test đã retry. Con số 60% cho thấy cần điều tra, không có nghĩa 60% toàn bộ test suite là flaky.

### 4.2. Phân biệt lỗi sản phẩm, lỗi test và lỗi hạ tầng

Một test fail có thể do:

- **Product defect:** ứng dụng trả kết quả sai hoặc hành vi không đáp ứng yêu cầu.
- **Test defect:** assertion sai, selector UI mong manh, dữ liệu fixture lỗi hoặc test phụ thuộc thứ tự.
- **Infrastructure failure:** runner mất kết nối, DNS lỗi, database test không sẵn sàng hoặc tài nguyên cạn.
- **External dependency:** sandbox/API bên ngoài chậm hoặc gián đoạn.
- **Flaky behavior:** race condition, timing, dữ liệu dùng chung hoặc trạng thái không xác định khiến cùng test lúc pass lúc fail.

Phân loại đúng giúp chọn biện pháp phù hợp. Tăng runner capacity không sửa được race condition trong test; viết lại assertion không giải quyết được database test thường xuyên hết connection.

### 4.3. Đo test stability theo test ID

Mỗi test nên có định danh ổn định qua các lần chạy. Báo cáo cần lưu:

- Test ID và suite/module.
- Commit SHA hoặc artifact version được kiểm thử.
- Môi trường, runner image và dependency version.
- Lần chạy đầu và các lần retry.
- Kết quả, thời lượng, failure category.
- Test bị skip/disabled và lý do.

Nếu tên test thay đổi liên tục, hệ thống khó nhận ra test nào thường xuyên flaky. Dùng test ID hoặc metadata ổn định để theo dõi lịch sử.

Không gộp kết quả test trên các commit, môi trường hoặc cấu hình khác nhau mà không phân nhóm. Một test có thể pass ở Linux nhưng fail ở Windows do khác biệt môi trường; đó là thông tin quan trọng cần giữ lại.

## 5. Đo thời gian chờ

Pipeline có thể chậm dù thời gian chạy lệnh ngắn. Các khoảng chờ thường gặp:

| Loại chờ | Ví dụ | Hướng cải thiện |
| --- | --- | --- |
| Runner queue wait | Job chờ runner rảnh | Điều chỉnh concurrency, autoscaling và phân bổ pool |
| Runner provisioning | Khởi tạo VM/container, cài toolchain | Dùng image đã chuẩn bị, runner ephemeral tối ưu |
| Environment wait | Chờ namespace, test environment hoặc lock | Tạo môi trường theo yêu cầu, cleanup và quản lý lease |
| Approval wait | Chờ người duyệt release | Risk-based approval, lịch trực và thông báo rõ |
| Dependency wait | Chờ upstream pipeline/artifact | Cache, version hóa và giảm phụ thuộc không cần thiết |
| Resource contention | Chờ database test, device farm hoặc license | Chia pool, quota và giới hạn concurrency |
| Manual handoff | Chờ thao tác copy artifact hoặc cập nhật biến | Tự động hóa handoff có kiểm soát |

### 5.1. Công thức cho các khoảng chờ

Ví dụ:

\[
T_{queue} = t_{runner\_assigned} - t_{job\_queued}
\]

\[
T_{provision} = t_{executor\_ready} - t_{runner\_assigned}
\]

\[
T_{approval} = t_{decision} - t_{approval\_requested}
\]

\[
T_{environment} = t_{lease\_acquired} - t_{environment\_requested}
\]

Các mốc phải được định nghĩa theo khả năng của CI platform. Một số nền tảng chỉ cung cấp thời điểm job queued và started, không cung cấp runner assigned hoặc executor ready. Khi đó, ghi rõ khoảng nào được đo trực tiếp và khoảng nào là ước lượng; không đặt tên metric khiến người đọc hiểu sai.

### 5.2. Chờ runner khác với job execution

Giả sử một job được xếp hàng lúc 09:00, runner nhận lúc 09:04, executor sẵn sàng lúc 09:05 và lệnh test kết thúc lúc 09:12:

- Queue wait: 4 phút.
- Runner provisioning: 1 phút.
- Execution: 7 phút.
- Thời gian từ queue đến kết thúc: 12 phút.

Nếu chỉ xem job duration là 7 phút, nhóm sẽ bỏ qua 5 phút người phát triển chờ trước khi test bắt đầu. Nếu pipeline có nhiều job song song, cần xem từng job trên timeline để xác định job nào nằm trên critical path.

## 6. Instrumentation: ghi nhận sự kiện và timestamp

Muốn đo chính xác, cần phát event tại các mốc quan trọng. Mỗi event nên có định danh pipeline/job và timestamp UTC.

Ví dụ event cho một job:

~~~json
{
  "event_id": "evt-job-1842-test-01",
  "event_type": "ci.job.started",
  "occurred_at": "2026-11-18T09:05:00Z",
  "pipeline_id": "pipeline-1842",
  "job_id": "integration-test",
  "repository": "commerce/orders-api",
  "commit_sha": "4f9a1c2d7b...",
  "runner_pool": "linux-medium",
  "environment": "ci-test",
  "attempt": 1
}
~~~

Các event hữu ích:

- pipeline.triggered
- pipeline.first_feedback
- pipeline.completed
- job.queued
- job.runner_assigned
- job.started
- job.completed
- test.case.started
- test.case.completed
- approval.requested
- approval.decided
- environment.requested
- environment.acquired

Đây là tên event minh họa. Trong hệ thống thật, định nghĩa schema, trường bắt buộc, event ID duy nhất, producer, timestamp và quy tắc xử lý event trùng lặp.

### 6.1. Đồng hồ và timestamp

Các hệ thống runner, CI controller và external service có thể lệch đồng hồ. Hãy đồng bộ thời gian bằng cơ chế chuẩn của hạ tầng và lưu timestamp theo UTC. Khi có thể, dùng monotonic clock để đo duration bên trong cùng một process; dùng wall-clock timestamp để liên kết event giữa các hệ thống.

Không tính duration âm hoặc ghép timestamp từ các máy không đồng bộ mà không cảnh báo. Nếu nền tảng cung cấp duration đã tính, hiểu rõ định nghĩa của nền tảng trước khi so sánh với metric tự tạo.

### 6.2. Giữ khóa liên kết nhất quán

Event nên mang các trường phù hợp:

- repository, commit SHA và branch/ref.
- pipeline ID, job ID và attempt number.
- test suite/test ID.
- runner pool và environment.
- event type, timestamp và result.
- release/deployment ID nếu job thuộc luồng phát hành.

Không đưa token, secret, nội dung payload nhạy cảm hoặc dữ liệu cá nhân vào metric/event. Dùng ID giả danh hoặc metadata đã được lọc khi cần điều tra.

## 7. Phân tích pipeline bằng timeline và critical path

Một dashboard chỉ hiển thị “pipeline mất 18 phút” chưa đủ để tìm nguyên nhân. Hãy xem timeline các job và dependency:

~~~mermaid
gantt
    title Ví dụ timeline pipeline
    dateFormat HH:mm
    axisFormat %H:%M
    section Trigger
    Trigger đến first feedback :a1, 09:00, 4m
    section Jobs
    Lint và compile :a2, 09:01, 3m
    Unit tests :a3, 09:04, 5m
    Integration tests :a4, 09:05, 7m
    section Release
    Approval wait :a5, 09:12, 5m
    Deploy và smoke :a6, 09:17, 4m
~~~

Timeline là ví dụ minh họa, không phải phép cộng thời lượng để suy ra chính xác pipeline wall-clock. Các job có thể chạy song song; approval có thể bắt đầu trước khi tất cả job kết thúc tùy thiết kế. Hãy lấy mốc thực tế từ event.

Để xác định critical path:

1. Xây dependency graph của job.
2. Ghi thời điểm queued, started và completed.
3. Tìm chuỗi dependency dài nhất quyết định pipeline hoàn tất.
4. Tách queue/provisioning khỏi execution trên chuỗi đó.
5. Ưu tiên cải thiện những bước vừa chậm vừa nằm trên critical path.

Job chậm nhưng chạy song song và hoàn tất trước khi critical path cần đến có thể không ảnh hưởng wall-clock. Tuy vậy, nó vẫn có thể tiêu tốn runner và làm tăng queue của pipeline khác.

## 8. Phân đoạn dữ liệu để tìm đúng nhóm bị ảnh hưởng

Không nên chỉ xem một con số trung bình cho toàn tổ chức. Hãy phân tích theo các chiều có ý nghĩa:

- Repository hoặc service.
- Loại sự kiện: pull request, push, tag, scheduled, manual.
- Branch class: feature, main, release.
- Runner pool hoặc executor type.
- Job class: lint, unit, integration, e2e, deploy.
- Môi trường hoặc region.
- Kích thước thay đổi hoặc loại pipeline nếu có dữ liệu phù hợp.

Ví dụ, p95 queue wait cao ở runner pool Linux có thể do thiếu concurrency; p95 execution cao riêng ở integration suite có thể do test hoặc dependency. Một nhóm test flaky trên Windows không nên bị che bởi kết quả tốt trên Linux.

Giữ cardinality hợp lý. Không đưa commit SHA, test run ID hoặc user ID vào metric label nếu tạo ra hàng nghìn hoặc hàng triệu chuỗi khác nhau. Dùng log/event store để truy vấn chi tiết; metrics nên dùng chiều có số lượng giá trị được kiểm soát.

## 9. Thiết kế dashboard và mục tiêu đo lường

Dashboard nên giúp trả lời ba câu hỏi: phản hồi nhanh đến đâu, kết quả test đáng tin đến đâu và thời gian chờ nằm ở đâu.

Một dashboard cơ bản có thể gồm:

| Nhóm | Panel | Cách hiển thị |
| --- | --- | --- |
| Response | Trigger-to-first-feedback | p50/p90/p95 theo repository |
| Response | End-to-end pipeline duration | p50/p90/p95 và số pipeline |
| Test stability | First-pass pass rate | Theo suite và branch class |
| Test stability | Retry-rescue / confirmed flaky rate | Top test ID cần điều tra |
| Test stability | Skip rate | Theo suite và lý do |
| Waiting | Queue wait | p50/p90/p95 theo runner pool |
| Waiting | Provisioning time | Theo executor/image |
| Waiting | Approval/environment wait | Theo stage và owner |
| Outcome | Pipeline success và change failure | Theo service/release window |

Đặt mục tiêu theo baseline thực tế, ví dụ p90 time-to-first-feedback, p95 queue wait hoặc first-pass pass rate. Không sao chép ngưỡng của tổ chức khác khi quy mô runner, test suite và sản phẩm khác nhau.

Một mục tiêu tốt cần có:

- Phạm vi đo và đối tượng áp dụng.
- Công thức, timestamp bắt đầu/kết thúc.
- Cửa sổ thời gian.
- Ngưỡng mục tiêu và ngưỡng cảnh báo.
- Owner chịu trách nhiệm.
- Guardrail để tránh đánh đổi chất lượng.

## 10. Ví dụ tính toán từ một pipeline

Giả sử một pipeline có các mốc:

| Sự kiện | Thời điểm |
| --- | --- |
| PR trigger được CI nhận | 09:00 |
| Lint/compile trả feedback đầu tiên | 09:04 |
| Integration job được xếp hàng | 09:05 |
| Runner được cấp | 09:09 |
| Executor sẵn sàng | 09:10 |
| Integration test kết thúc | 09:17 |
| Approval được yêu cầu | 09:17 |
| Approval được quyết định | 09:22 |
| Deploy và smoke hoàn tất | 09:28 |

Từ các mốc này:

- Time to first feedback = 4 phút.
- Queue wait của integration job = 4 phút.
- Provisioning time = 1 phút.
- Integration execution = 7 phút.
- Approval wait = 5 phút.
- End-to-end duration = 28 phút.

Nếu nhóm giảm integration execution từ 7 xuống 5 phút nhưng queue vẫn 4 phút và approval vẫn 5 phút, tổng thời gian chỉ giảm khoảng 2 phút nếu đó là critical path. Nếu queue wait giảm từ 4 xuống 1 phút, người dùng có thể nhận kết quả cuối sớm hơn mà không thay đổi test.

Nếu first-pass pass rate chỉ 92% và nhiều test pass khi retry, tối ưu tốc độ trước khi xử lý độ ổn định có thể làm pipeline xanh nhanh hơn nhưng không đáng tin hơn. Cần xem cả ba nhóm chỉ số.

## 11. Cải thiện thời gian phản hồi

Khi time-to-first-feedback cao:

- Đưa lint, formatting, compile và unit test nhanh lên đầu pipeline.
- Chạy các kiểm tra độc lập song song.
- Chỉ chạy test theo phạm vi thay đổi khi dependency graph đủ tin cậy.
- Dùng dependency cache có key và invalidation đúng.
- Tránh tải toolchain hoặc container image lặp lại trong mỗi job.
- Trả kết quả sớm khi một required check chắc chắn fail.
- Giữ các test chậm ở stage sau nhưng vẫn bắt buộc trước release nếu policy yêu cầu.

Không nên chạy một test suite không ổn định ở đầu pipeline chỉ để có feedback nhanh. Kết quả false positive làm người phát triển mất niềm tin vào CI và tạo thêm thời gian điều tra.

Khi end-to-end duration cao nhưng first feedback thấp, nhóm có thể giữ pipeline feedback nhanh và tối ưu critical path ở stage sau. Đừng chỉ nhìn tổng thời gian rồi chuyển mọi test sang chạy tuần tự.

## 12. Cải thiện độ ổn định kiểm thử

Khi retry-rescue rate hoặc confirmed flaky rate cao, điều tra theo nhóm nguyên nhân:

**Test phụ thuộc thời gian**

- Dùng clock giả lập hoặc fixed clock cho logic thời gian.
- Tránh chờ bằng sleep cố định; chờ điều kiện có timeout.
- Kiểm tra timezone và locale của runner.

**Test chia sẻ trạng thái**

- Tạo dữ liệu riêng cho từng test/run.
- Dọn dữ liệu bằng fixture có phạm vi rõ.
- Không phụ thuộc thứ tự test hoặc tài nguyên dùng chung.
- Cô lập account, tenant, database schema và queue khi cần.

**Race condition và concurrency**

- Chờ trạng thái thực sự hoàn tất.
- Dùng synchronization thay vì giả định thời gian.
- Kiểm tra resource contention và giới hạn song song.

**Môi trường và dependency**

- Pin version của browser, driver, container và toolchain.
- Health-check dependency trước khi chạy suite.
- Thu log, trace và runner metadata khi fail.
- Dùng sandbox/mock cho dependency ngoài không ổn định nếu phù hợp.

Retry nên được giữ như một cơ chế phục hồi có giới hạn hoặc công cụ chẩn đoán. Không tự động biến một lần retry pass thành pass sạch mà xóa kết quả fail đầu tiên. Báo cáo cần giữ cả attempt đầu, retry và phân loại nguyên nhân.

## 13. Giảm thời gian chờ theo đúng nguyên nhân

### 13.1. Queue wait cao

- Đo queue theo runner pool, thời điểm và job class.
- Tăng concurrency hoặc autoscaling khi nhu cầu ổn định chứng minh thiếu năng lực.
- Tách pool cho workload nặng hoặc nhạy cảm.
- Hạn chế job không cần thiết và pipeline trùng lặp.
- Kiểm soát giới hạn concurrency để tránh bão hòa hạ tầng.

### 13.2. Provisioning time cao

- Dùng runner image có sẵn toolchain thường dùng.
- Giảm bước cài đặt runtime ở mỗi job.
- Dùng image theo digest và cập nhật có kiểm soát.
- Tối ưu khởi động container/VM.
- Thu thập thời gian bootstrap riêng để biết bước nào chậm.

### 13.3. Approval wait cao

- Xác định approval nào bắt buộc theo rủi ro.
- Dùng environment protection và approver group rõ ràng.
- Gửi thông báo có context và deadline.
- Có lịch trực hoặc người thay thế.
- Tự động hóa kiểm tra có thể xác minh bằng policy, giữ approval con người cho quyết định cần trách nhiệm.

Không loại bỏ approval chỉ để giảm metric nếu thay đổi vẫn cần kiểm soát rủi ro production.

### 13.4. Environment wait cao

- Dùng ephemeral environment cho PR nếu phù hợp.
- Tự động cấp và thu hồi namespace/test environment.
- Quản lý lock/lease có timeout và cleanup.
- Tách môi trường cho test song song.
- Giảm phụ thuộc vào một môi trường tích hợp dùng chung.

### 13.5. Dependency wait cao

- Publish artifact sớm sau khi upstream build thành công.
- Pin version và digest để consumer tải đúng nội dung.
- Cache artifact/dependency an toàn.
- Chỉ trigger consumer bị ảnh hưởng.
- Tránh release train toàn hệ thống nếu hợp đồng cho phép phát hành độc lập.

## 14. Không để metric tạo hành vi sai

Khi metric trở thành mục tiêu, nhóm có thể vô tình tối ưu con số thay vì kết quả:

- Bỏ test chậm để giảm pipeline duration.
- Chuyển test sang job tùy chọn để không tính vào pass rate.
- Retry nhiều lần đến khi xanh và chỉ báo cáo lần cuối.
- Tách pipeline thành nhiều phần để giảm thời gian hiển thị nhưng tăng tổng chi phí.
- Bỏ qua approval hoặc kiểm tra bảo mật để giảm wait.
- Đo từ lúc runner bắt đầu thay vì lúc trigger để loại queue wait khỏi báo cáo.

Các guardrail:

- Giữ số lượng test chạy, skip và disabled trong dashboard.
- Lưu first attempt và mọi retry.
- Đo cả wall-clock duration và thời gian chờ.
- Theo dõi failure sau deploy, rollback và incident cùng với tốc độ CI.
- Chỉ thay đổi định nghĩa metric qua review có version.
- Không xếp hạng cá nhân bằng thời gian pipeline hoặc số lần commit.

Mục tiêu là giảm thời gian phản hồi và chờ trong khi duy trì test coverage, độ tin cậy và chất lượng release.

## 15. Liên hệ với DORA và kết quả phát hành

Các chỉ số phản hồi, test stability và wait time chủ yếu giúp cải thiện luồng làm việc bên trong CI/CD. Chúng bổ sung cho các chỉ số delivery ở cấp dịch vụ/nhóm như:

- Lead time for changes: thời gian từ khi thay đổi được commit đến khi chạy trong production, theo định nghĩa đo được của tổ chức.
- Deployment frequency: tần suất triển khai.
- Change failure rate: tỷ lệ deployment gây suy giảm dịch vụ hoặc cần remediation theo định nghĩa đã thống nhất.
- Failed deployment recovery time: thời gian phục hồi sau deployment thất bại.

Không đồng nhất pipeline duration với lead time for changes. Pipeline có thể mất 20 phút nhưng code đã chờ review hai ngày; ngược lại, pipeline nhanh nhưng release phải chờ một cửa sổ triển khai dài.

Khi tối ưu CI/CD, xem cả delivery speed và delivery stability. Nếu pipeline nhanh hơn nhưng change failure rate tăng hoặc thời gian recovery dài hơn, thay đổi đó chưa chắc là cải tiến.

## 16. Vòng lặp cải tiến dựa trên dữ liệu

Một quy trình cải tiến thực tế:

1. **Định nghĩa:** thống nhất metric, công thức, timestamp và phạm vi.
2. **Đo baseline:** thu thập dữ liệu đủ dài để thấy ngày cao điểm, loại pipeline và biến động.
3. **Phân đoạn:** tìm repository, runner pool, test suite hoặc stage có vấn đề.
4. **Chọn nguyên nhân:** dùng timeline, logs và owner để xác định bottleneck.
5. **Đề xuất thay đổi:** chỉ thay một hoặc một nhóm nhỏ yếu tố có liên quan.
6. **Đánh giá guardrails:** kiểm tra test coverage, failure, security và release outcomes.
7. **So sánh:** so p50/p90/p95 và số mẫu trước/sau trên nhóm tương đương.
8. **Chuẩn hóa:** ghi lại cách làm hiệu quả và tiếp tục theo dõi drift.

Ví dụ, nếu p95 queue wait tăng sau khi thêm integration suite, hãy kiểm tra runner pool và concurrency trước khi giảm test. Nếu first-pass pass rate giảm cùng lúc runner image được cập nhật, so sánh test failure theo image version để xác định tác động.

Đừng thay đổi nhiều thành phần cùng lúc nếu chưa có baseline; khi metric thay đổi, nhóm sẽ khó biết nguyên nhân nào tạo ra kết quả.

## 17. Ví dụ metric definition cho dashboard

Một bộ định nghĩa có thể lưu trong repository để mọi nhóm hiểu giống nhau:

~~~yaml
metrics:
  pipeline_first_feedback_seconds:
    start_event: pipeline.triggered
    end_event: pipeline.first_actionable_feedback
    aggregation: p50_p90_p95
    dimensions:
      - repository
      - event_type
      - runner_pool

  pipeline_wall_clock_seconds:
    start_event: pipeline.triggered
    end_event: pipeline.completed
    aggregation: p50_p90_p95
    dimensions:
      - repository
      - branch_class

  job_queue_wait_seconds:
    start_event: job.queued
    end_event: job.runner_assigned
    aggregation: p50_p90_p95
    dimensions:
      - runner_pool
      - job_class

  test_first_pass_pass_rate:
    numerator: test_cases_passed_on_first_attempt
    denominator: test_cases_executed_on_first_attempt
    aggregation: ratio
    exclude:
      - skipped

  test_retry_rescue_rate:
    numerator: failed_tests_that_passed_on_retry
    denominator: failed_tests_retried
    aggregation: ratio

  approval_wait_seconds:
    start_event: approval.requested
    end_event: approval.decided
    aggregation: p50_p90_p95
    dimensions:
      - environment
      - approval_type
~~~

Đây là schema minh họa. Metric owner cần định nghĩa cách xử lý event thiếu, job bị cancel, pipeline retry, test flaky đã xác nhận, approval bị thu hồi và thời điểm pipeline được tạo lại. Nếu mẫu số bằng 0, metric ratio phải hiển thị không có dữ liệu thay vì tự coi là 100%.

## 18. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ đo pipeline duration | Không biết thời gian mất ở queue, execution hay approval | Đo từng khoảng và critical path |
| Đo từ runner start | Bỏ qua thời gian người phát triển chờ | Đo từ trigger/queue theo định nghĩa |
| Chỉ dùng average | Ngoại lệ kéo lệch hoặc che p95 | Theo dõi p50/p90/p95 và số mẫu |
| Coi retry pass là test ổn định | Che giấu lỗi chập chờn | Lưu first attempt và phân loại failure |
| Tính skipped là pass | Làm đẹp tỷ lệ mà giảm kiểm thử | Báo skip rate riêng |
| Gộp lỗi hạ tầng vào product failure | Sửa sai nguyên nhân | Phân loại test, product, infra và external dependency |
| Tối ưu job không nằm trên critical path | Không cải thiện thời gian người dùng chờ | Phân tích dependency graph và timeline |
| Tăng runner vô hạn | Tăng chi phí và bão hòa dependency | Dùng concurrency/capacity theo dữ liệu |
| Loại approval để giảm wait | Tăng rủi ro release | Risk-based approval và tự động hóa kiểm tra |
| Dùng retry vô hạn | Kéo dài pipeline và che lỗi | Retry hữu hạn, backoff và báo cáo rõ |
| Không giữ metric definition | Các nhóm đo khác nhau và không so sánh được | Version hóa schema và công thức |
| Chỉ nhìn tốc độ CI | Bỏ qua failure sau deploy | Kết hợp DORA và quality guardrails |

## 19. Checklist đo lường và cải tiến CI/CD

**Định nghĩa và thu thập**

- [ ] Có định nghĩa trigger, first feedback và pipeline completion.
- [ ] Đo wall-clock duration, job execution và các khoảng chờ riêng.
- [ ] Ghi event/timestamp UTC cùng pipeline ID, job ID và attempt.
- [ ] Phân biệt release, deployment, repository và runner pool.
- [ ] Có metric definition và owner rõ ràng.

**Độ ổn định kiểm thử**

- [ ] Báo first-pass pass/failure rate.
- [ ] Lưu mọi retry và kết quả lần đầu.
- [ ] Đo retry-rescue, confirmed flaky và skip rate.
- [ ] Phân loại product, test, infrastructure và external failures.
- [ ] Theo dõi lịch sử theo test ID và môi trường.

**Thời gian chờ và phản hồi**

- [ ] Theo dõi p50/p90/p95 và số lượng mẫu.
- [ ] Phân biệt queue, provisioning, approval, environment và dependency wait.
- [ ] Xác định critical path của pipeline.
- [ ] Phân đoạn theo repository, event type, runner pool và job class.
- [ ] Dashboard cho thấy nơi cần hành động và owner.

**Cải tiến có guardrail**

- [ ] Có baseline trước khi thay đổi.
- [ ] Ưu tiên bottleneck dựa trên dữ liệu.
- [ ] Không bỏ test hoặc approval chỉ để làm đẹp metric.
- [ ] Theo dõi coverage, release failure và recovery cùng tốc độ.
- [ ] So sánh trước/sau trên nhóm tương đương và lưu kết quả.

## Kết luận

Đo thời gian phản hồi, độ ổn định kiểm thử và thời gian chờ giúp nhóm hiểu CI/CD đang làm người phát triển mất thời gian ở đâu và kết quả kiểm thử có đáng tin hay không. Hãy đo từ thời điểm trigger, tách first feedback khỏi pipeline completion, phân tích queue/provisioning/approval riêng, và giữ kết quả lần chạy đầu cùng mọi retry để nhận diện test không ổn định.

Percentile, timeline và dependency graph giúp tìm bottleneck thực sự. Cải tiến nên bắt đầu từ baseline, nhắm vào nguyên nhân trên critical path và luôn có guardrail về test coverage, security, change failure và recovery. Khi metric có định nghĩa rõ, được phân đoạn đúng và không bị dùng để tạo hành vi chạy theo con số, nó trở thành công cụ cải tiến CI/CD bền vững.
