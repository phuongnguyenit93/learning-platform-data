# Đo thời gian chờ máy chạy và thời gian từng công việc

Thời gian một pipeline CI/CD mất từ lúc nhận thay đổi đến khi trả kết quả phụ thuộc vào nhiều thành phần. Job có thể nằm trong hàng đợi vì runner chưa có chỗ trống; runner có thể mất thêm thời gian để được cấp phát và khởi động; sau đó job mới checkout mã nguồn, tải dependency, build, chạy test và upload artifact. Nếu chỉ nhìn tổng thời gian pipeline, nhóm khó biết đang chờ máy chạy hay đang thực sự thực hiện công việc.

Đo thời gian chờ máy chạy và thời gian từng công việc giúp xác định chính xác nơi feedback bị chậm. **Thời gian chờ runner** cho biết job phải đợi bao lâu trước khi có máy thực thi; **thời gian khởi tạo runner** cho biết máy cần bao lâu để sẵn sàng; **thời gian thực thi job** cho biết bản thân công việc mất bao lâu; còn **thời gian phản hồi đầu-cuối** cho biết nhà phát triển phải đợi bao lâu để nhận kết quả cần thiết.

Bài học này hướng dẫn cách định nghĩa các khoảng thời gian, thu thập timestamp, tính duration, phân tích theo job và runner pool, xây dashboard, đọc percentile và tìm nút thắt. Mục tiêu là biến cảm giác “pipeline chậm” thành dữ liệu có thể hành động: biết job nào chờ lâu, bước nào chạy lâu, nhóm runner nào thiếu năng lực và thay đổi nào thực sự cải thiện thời gian phản hồi.

## 1. Phân rã thời gian thay vì chỉ đo tổng pipeline

Một pipeline thường gồm nhiều job liên kết bằng dependency. Một số job chạy song song, một số chỉ bắt đầu khi job trước hoàn tất. Mỗi job lại đi qua các giai đoạn như chờ runner, khởi tạo máy, setup và thực thi các step.

Nếu chỉ đo từ lúc trigger đến lúc pipeline kết thúc, ta biết tổng thời gian nhưng không biết phần nào tạo ra độ trễ. Cần tách ít nhất các khoảng sau:

| Khoảng thời gian | Điểm bắt đầu | Điểm kết thúc | Ý nghĩa |
|---|---|---|---|
| Dependency wait | Job được tạo hoặc workflow bắt đầu | Job đủ điều kiện chạy sau khi dependency hoàn tất | Thời gian chờ job upstream |
| Runner queue time | Job đủ điều kiện chạy | Runner được scheduler gán | Thời gian chờ năng lực thực thi |
| Runner provisioning time | Runner được gán/yêu cầu cấp phát | Runner sẵn sàng nhận job | Thời gian tạo VM/container hoặc khởi động máy |
| Job startup time | Runner sẵn sàng | Lệnh job đầu tiên bắt đầu | Checkout/bootstrap hoặc setup ban đầu |
| Job execution time | Job bắt đầu | Job kết thúc | Thời gian thực thi job, gồm các step và overhead trong job |
| Step duration | Một step bắt đầu | Step kết thúc | Thời gian của từng command hoặc nhóm thao tác |
| End-to-end feedback time | Sự kiện kích hoạt pipeline | Kết quả cần thiết được công bố | Thời gian nhà phát triển phải đợi feedback |

Điểm quan trọng là **queue time và provisioning time là hai việc khác nhau**. Job có thể được scheduler chọn ngay nhưng máy mới cần 40 giây để khởi tạo. Ngược lại, runner có thể luôn sẵn sàng nhưng job phải xếp hàng 5 phút vì toàn bộ máy đang bận.

Một số nền tảng chỉ cung cấp hai mốc queued và started. Trong trường hợp đó, khoảng queued đến started có thể gộp cả queue, provisioning và startup. Hãy đặt tên là **wait_to_start** hoặc **queue_plus_startup**, không gọi nó là queue thuần nếu chưa có timestamp để tách các giai đoạn.

~~~mermaid
flowchart LR
    A["Workflow triggered"] --> B["Job eligible"]
    B --> C["Runner queue"]
    C --> D["Runner assigned"]
    D --> E["Runner provisioning"]
    E --> F["Runner ready"]
    F --> G["Job startup"]
    G --> H["Job execution"]
    H --> I["Job completed"]
    I --> J["Feedback published"]
~~~

## 2. Định nghĩa timestamp chuẩn

Đo duration chính xác bắt đầu từ việc thống nhất ý nghĩa của từng timestamp. Tên trường có thể khác nhau giữa GitHub Actions, GitLab CI, Jenkins hoặc hệ thống CI nội bộ, nhưng khái niệm nên nhất quán.

Một event model tham khảo:

| Timestamp | Ý nghĩa |
|---|---|
| workflow_triggered_at | Sự kiện Git hoặc thao tác thủ công kích hoạt workflow |
| job_created_at | Hệ thống tạo job |
| job_eligible_at | Tất cả điều kiện dependency đã đạt, scheduler có thể xếp job vào hàng đợi |
| runner_requested_at | Yêu cầu runner được gửi |
| runner_assigned_at | Scheduler chọn hoặc gán runner |
| runner_ready_at | Runner hoàn tất provisioning và sẵn sàng thực thi |
| job_started_at | Lệnh thực thi job bắt đầu |
| step_started_at | Một step bắt đầu |
| step_completed_at | Một step kết thúc |
| job_completed_at | Job kết thúc, bất kể thành công hay thất bại |
| feedback_published_at | Kết quả được hiển thị hoặc gửi đến nơi nhà phát triển nhận feedback |

Không phải nền tảng nào cũng phát ra tất cả event này. Có thể bổ sung instrumentation ở runner controller, plugin hoặc wrapper của pipeline để thu thập phần còn thiếu.

### 2.1. Chọn đúng mốc bắt đầu của queue

Với job có dependency, job có thể được tạo từ đầu workflow nhưng chưa được phép chạy vì job upstream chưa xong. Khoảng chờ đó là **dependency wait**, không phải thời gian chờ runner.

Ví dụ: integration test chỉ được chạy sau khi build hoàn tất. Nếu build mất 4 phút, integration job chưa đủ điều kiện để scheduler cấp runner trong khoảng đó. Ghi toàn bộ 4 phút thành queue time sẽ khiến nhóm tưởng runner pool thiếu máy dù thực tế job đang chờ dependency.

Để đo queue thuần, dùng **job_eligible_at** làm mốc bắt đầu nếu hệ thống cung cấp. Nếu không có mốc này, cần ghi rõ metric đang bao gồm dependency wait.

### 2.2. Đo duration bằng đồng hồ phù hợp

Timestamp phục vụ tương quan giữa nhiều hệ thống nên được lưu ở UTC và đồng bộ thời gian giữa controller, runner và service. Khi đo một khoảng duration bên trong cùng process hoặc cùng máy, nên ưu tiên monotonic clock vì đồng hồ lịch có thể bị điều chỉnh trong lúc job chạy.

Không lấy timestamp từ log của hai máy chưa đồng bộ rồi trừ trực tiếp mà không tính đến clock skew. Một kết quả âm hoặc bất thường thường là dấu hiệu event đến sai thứ tự, clock lệch hoặc dữ liệu thiếu.

## 3. Công thức tính các khoảng thời gian

Khi đã có timestamp chuẩn, các duration được tính như sau:

\[
T_{\text{dependency}} =
t_{\text{eligible}} - t_{\text{created}}
\]

\[
T_{\text{queue}} =
t_{\text{runner-assigned}} - t_{\text{eligible}}
\]

\[
T_{\text{provision}} =
t_{\text{runner-ready}} - t_{\text{runner-assigned}}
\]

\[
T_{\text{startup}} =
t_{\text{job-started}} - t_{\text{runner-ready}}
\]

\[
T_{\text{job}} =
t_{\text{job-completed}} - t_{\text{job-started}}
\]

\[
T_{\text{feedback}} =
t_{\text{feedback-published}} - t_{\text{workflow-triggered}}
\]

Nếu chỉ có timestamp queued và started, có thể tính:

\[
T_{\text{wait-to-start}} =
t_{\text{started}} - t_{\text{queued}}
\]

Nhưng cần ghi chú metric này gộp các giai đoạn mà nền tảng không tách được.

### 3.1. Ví dụ tính duration

Giả sử một workflow có ba job:

- lint và unit-test đủ điều kiện chạy ngay khi workflow bắt đầu.
- integration-test chỉ đủ điều kiện sau khi unit-test hoàn tất.
- Các runner được cấp phát theo thời điểm khác nhau.

| Job | Eligible | Runner assigned | Runner ready | Job started | Job completed |
|---|---:|---:|---:|---:|---:|
| lint | 09:00:00 | 09:00:20 | 09:00:25 | 09:00:25 | 09:00:55 |
| unit-test | 09:00:00 | 09:00:50 | 09:01:00 | 09:01:00 | 09:03:00 |
| integration-test | 09:03:00 | 09:03:10 | 09:03:20 | 09:03:20 | 09:07:20 |

Từ dữ liệu trên:

| Job | Queue | Provisioning | Startup | Execution |
|---|---:|---:|---:|---:|
| lint | 20 giây | 5 giây | 0 giây | 30 giây |
| unit-test | 50 giây | 10 giây | 0 giây | 120 giây |
| integration-test | 10 giây | 10 giây | 0 giây | 240 giây |

Integration test có dependency wait 180 giây tính từ lúc workflow bắt đầu đến khi unit-test hoàn tất. Queue time của nó chỉ là 10 giây tính từ lúc đủ điều kiện đến khi runner được gán.

Nếu workflow được kích hoạt lúc 09:00 và kết quả cuối cùng được công bố lúc 09:07:20, end-to-end feedback time là 7 phút 20 giây. Không được cộng tổng queue và duration của cả ba job để suy ra thời gian pipeline, vì lint và unit-test chạy song song. Thời gian đầu-cuối phụ thuộc đường găng (critical path) của đồ thị job và các khoảng chờ liên quan.

## 4. Phân biệt thời gian job, step và pipeline

Ba cấp độ này trả lời ba câu hỏi khác nhau:

- **Pipeline duration:** nhà phát triển chờ bao lâu từ lúc trigger đến kết quả.
- **Job duration:** một job cụ thể chạy mất bao lâu sau khi bắt đầu.
- **Step duration:** một thao tác cụ thể trong job mất bao lâu.

Ví dụ, job build-and-test chạy 12 phút 40 giây. Trong đó:

| Step | Duration |
|---|---:|
| Checkout | 20 giây |
| Restore dependency cache | 15 giây |
| Resolve dependencies | 70 giây |
| Compile | 90 giây |
| Unit tests | 420 giây |
| Package artifact | 45 giây |
| Upload artifact | 60 giây |
| Các bước setup/teardown khác | 40 giây |

Tổng duration các step được liệt kê là 760 giây (12 phút 40 giây), bằng job duration trong ví dụ. Trong thực tế, tổng step duration có thể lệch so với job duration do setup/teardown, thời gian nền tảng, bước chồng lấn hoặc timestamp không cùng quy ước. Hãy kiểm tra cách nền tảng tính thời gian và những khoảng không được ghi thành step.

Trong pipeline có nhiều job song song, tổng duration của tất cả job có thể lớn hơn rất nhiều so với pipeline duration. Đó là bình thường: tổng job duration đo lượng công việc tiêu thụ, còn pipeline duration đo thời gian lịch thực tế đến khi có kết quả.

### 4.1. Critical path

Critical path là chuỗi job và dependency quyết định thời điểm pipeline có thể hoàn tất. Tăng tốc một job không nằm trên critical path có thể không làm giảm thời gian feedback cuối.

Ví dụ:

~~~mermaid
flowchart TD
    A["Trigger"] --> B["Lint 30s"]
    A --> C["Unit test 120s"]
    B --> D["Package"]
    C --> D
    D --> E["Integration test 240s"]
    E --> F["Publish result"]
~~~

Trong ví dụ, lint hoàn tất trước unit test. Nếu package cần cả lint và unit test, nó phải chờ nhánh unit test. Tối ưu lint từ 30 giây xuống 10 giây không thay đổi critical path nếu unit test vẫn mất 120 giây. Tối ưu unit test có thể giảm thời gian đầu-cuối trực tiếp hơn.

### 4.2. First feedback và final feedback

Nhà phát triển có thể nhận kết quả lint sau 30 giây, nhưng phải đợi integration test thêm vài phút. Nên đo cả:

- **time_to_first_feedback:** thời gian đến kết quả đầu tiên có ích.
- **time_to_required_checks:** thời gian đến khi tất cả check bắt buộc hoàn tất.
- **time_to_pipeline_completion:** thời gian đến khi workflow kết thúc hoàn toàn.

Các mốc này giúp đánh giá liệu pipeline có trả lỗi sớm hay bắt nhà phát triển chờ tất cả công việc mới biết lỗi đơn giản.

## 5. Thu thập dữ liệu thời gian từ pipeline

Để phân tích được, mỗi lần chạy cần tạo event có định danh và timestamp nhất quán.

Một event có thể chứa:

~~~json
{
  "workflow_run_id": "run-84721",
  "job_id": "job-compile-02",
  "job_name": "unit-test",
  "stage": "test",
  "repository": "orders-service",
  "commit_sha": "a91c...72ef",
  "runner_pool": "linux-large",
  "runner_image": "ubuntu-22.04-v17",
  "job_eligible_at": "2026-11-18T09:00:00Z",
  "runner_assigned_at": "2026-11-18T09:00:50Z",
  "runner_ready_at": "2026-11-18T09:01:00Z",
  "job_started_at": "2026-11-18T09:01:00Z",
  "job_completed_at": "2026-11-18T09:03:00Z",
  "result": "success"
}
~~~

Đây là event schema minh họa. Tên field có thể được điều chỉnh theo CI provider hoặc hệ thống telemetry nội bộ.

### 5.1. Những metadata nên lưu

Để phân tích có ý nghĩa, nên gắn duration với:

- Workflow name và run ID.
- Job name, job ID và stage.
- Repository, branch, commit SHA và loại trigger.
- Runner pool, loại máy, CPU/memory class và image version.
- Hệ điều hành, architecture và toolchain.
- Kết quả job: success, failure, cancelled hoặc skipped.
- Cache hit/miss và artifact size nếu có.
- Thời điểm bắt đầu/kết thúc và retry attempt.

Không đưa run ID, commit SHA hoặc user ID thành label trên mọi time series nếu hệ thống metrics có chi phí cardinality cao. Hãy lưu chúng trong event/log hoặc trace; metric chỉ nên dùng các label có tập giá trị giới hạn như job_name, stage, runner_pool, os và result.

### 5.2. Đảm bảo event không bị mất

Cần ghi nhận cả job thành công lẫn thất bại, bị hủy và bị timeout. Nếu chỉ lưu job hoàn tất bình thường, dashboard sẽ bỏ qua những job bị treo hoặc runner bị mất.

Có thể dùng event hook của CI provider, runner telemetry, plugin hoặc wrapper để gửi event khi:

- Job được tạo và đủ điều kiện chạy.
- Runner được gán và sẵn sàng.
- Job bắt đầu và kết thúc.
- Step bắt đầu và kết thúc.
- Job bị hủy hoặc hết thời gian.
- Feedback được công bố.

Nếu một event bị thiếu, ghi rõ dữ liệu không đầy đủ thay vì gán duration bằng 0. Cần theo dõi tỷ lệ event bị thiếu như một chỉ số chất lượng của hệ thống đo lường.

## 6. Đo thời gian chờ runner

Queue time cao thường có nghĩa job đủ điều kiện chạy nhưng chưa có runner phù hợp hoặc chưa được scheduler cấp phát.

Các nguyên nhân phổ biến:

- Không đủ runner cho số job đồng thời.
- Nhiều pipeline cùng khởi chạy sau một đợt push hoặc merge.
- Runner pool bị giới hạn theo repository, team hoặc environment.
- Job yêu cầu label hiếm, OS hoặc architecture chuyên biệt.
- Runner autoscaling khởi tạo chậm hoặc đạt giới hạn capacity.
- Một số job dài chiếm toàn bộ runner persistent.
- Concurrency limit hoặc quota của nền tảng bị chạm.
- Job ưu tiên thấp phải chờ job ưu tiên cao.

### 6.1. Phân tích queue theo runner pool

Không nên chỉ xem queue time trung bình toàn tổ chức. Hãy phân tách theo runner pool, loại máy, repository, job class và thời gian trong ngày.

Ví dụ:

| Runner pool | p50 queue | p95 queue | Job count | Nhận định |
|---|---:|---:|---:|---|
| linux-small | 8 giây | 35 giây | 4.200 | Năng lực tương đối ổn định |
| linux-large | 25 giây | 210 giây | 1.100 | Có thể thiếu máy lớn vào giờ cao điểm |
| windows | 40 giây | 300 giây | 420 | Cần kiểm tra capacity và startup |
| macos | 75 giây | 480 giây | 160 | Pool nhỏ, nhu cầu tập trung |

Số liệu trên chỉ là ví dụ minh họa. p95 cao trong pool có ít job có thể biến động mạnh; luôn xem sample count và xu hướng nhiều ngày.

### 6.2. Queue time khác provisioning time

Nếu queue time thấp nhưng thời gian từ runner assigned đến runner ready cao, tăng số runner luôn bật có thể hữu ích hơn tăng quota queue. Nếu cả queue và provisioning đều cao, cần kiểm tra cả capacity lẫn autoscaler.

Với runner ephemeral, provisioning có thể gồm cấp VM, tải image, cài agent, lấy credential và kết nối controller. Với runner warm pool, máy đã sẵn sàng trước nên provisioning time cho job có thể rất nhỏ, nhưng vẫn có chi phí duy trì pool.

### 6.3. Job chờ do dependency không phải runner thiếu máy

Nếu job chưa đủ điều kiện vì needs hoặc dependency chưa hoàn tất, nó không nên được tính vào queue. Cần phân tích dependency wait riêng để biết pipeline đang bị chậm do cấu trúc DAG hay do capacity runner.

## 7. Đo thời gian thực thi từng job và step

Job duration giúp xác định công việc nào đang tiêu thụ nhiều thời gian sau khi runner sẵn sàng.

Nên theo dõi:

- Duration của từng job qua nhiều lần chạy.
- Duration của từng step trong job.
- p50, p90, p95 và max thay vì chỉ average.
- Tỷ lệ job thất bại, retry và timeout.
- Duration theo runner image và loại máy.
- Duration theo cache hit/miss.
- Artifact download/upload time.
- Thời gian checkout và resolve dependency.

### 7.1. So sánh cùng một loại job

Không so sánh trực tiếp job integration-test với lint rồi kết luận job nào bất thường. Hãy so sánh cùng job name, cùng loại runner và cùng workload qua các lần chạy.

Khi job duration tăng, kiểm tra:

- Commit có thêm test hoặc workload không?
- Dependency có thay đổi?
- Cache có bị miss hoặc bị invalidation?
- Runner có bị CPU throttling hoặc memory pressure?
- Có bước tải artifact hoặc package chậm?
- Số lượng test, shard hoặc matrix có thay đổi?
- Job có bị retry nội bộ mà không hiển thị thành job riêng?

### 7.2. Step duration để tìm nguyên nhân cụ thể

Job duration chỉ ra job chậm; step duration chỉ ra bước chậm. Ví dụ, build job tăng từ 4 lên 9 phút. Nếu checkout vẫn 15 giây, compile tăng 20 giây nhưng dependency resolution tăng từ 30 giây lên 4 phút, nhóm nên điều tra package repository, lockfile, cache hoặc network.

Nên đặt tên step rõ ràng và ổn định. Nếu mỗi commit đổi tên step, việc so sánh lịch sử sẽ khó hơn. Với các command dài, có thể tạo sub-step hoặc instrumentation để đo riêng phần tải dependency, compile, test và upload.

### 7.3. Matrix jobs

Một job matrix tạo nhiều execution tương ứng với OS, runtime hoặc version. Cần lưu dimension của matrix nhưng giới hạn số label. Khi phân tích, xem:

- Job nào trong matrix chậm nhất?
- Runner pool nào có queue cao?
- Có một OS/version luôn chậm hơn?
- Có thể dùng fail-fast cho trường hợp phù hợp không?
- Có đang chạy tổ hợp không cần thiết trên mọi pull request?

Không nên chỉ nhìn duration của job matrix đại diện nếu các instance có thời gian khác nhau đáng kể.

## 8. Phân tích end-to-end feedback và critical path

Thời gian pipeline đầu-cuối không bằng tổng duration của tất cả job. Với các job song song, phần lớn công việc có thể diễn ra đồng thời. Để hiểu feedback chậm, cần xem đồ thị dependency và critical path.

Một cách phân tích:

1. Xác định mốc workflow trigger.
2. Xác định thời điểm từng job đủ điều kiện chạy.
3. Tính dependency wait và queue/provisioning riêng.
4. Tính duration của từng job và step.
5. Xác định chuỗi dependency kết thúc muộn nhất.
6. Đối chiếu với thời điểm required checks và feedback được công bố.

### 8.1. Job chạy lâu nhất chưa chắc là nút thắt

Một job mất 10 phút nhưng chạy song song với nhánh khác cũng mất 10 phút có thể nằm trên critical path. Một job mất 8 phút nhưng không chặn kết quả bắt buộc có thể không ảnh hưởng thời gian feedback của pull request.

Hãy xác định job nào đang giữ dependency phía sau. Tối ưu job trên critical path thường có tác động lớn hơn tối ưu job không chặn kết quả.

### 8.2. Tối ưu first feedback

Có thể sắp xếp các kiểm tra nhanh và có khả năng phát hiện lỗi cao chạy sớm:

- Syntax, formatting và lint.
- Unit test nhanh.
- Kiểm tra cấu hình và schema.
- Build compile.
- Integration test và kiểm tra tốn tài nguyên.

Cách sắp xếp cần dựa trên dependency và độ tin cậy. Không được bỏ qua required check chỉ để làm kết quả đầu tiên xuất hiện sớm. Mục tiêu là phát hiện lỗi đơn giản sớm và vẫn giữ đầy đủ gate trước merge/release.

## 9. Metrics và percentile cho thời gian pipeline

Thời gian thường có phân phối lệch: phần lớn job chạy nhanh nhưng một số job phải chờ lâu hoặc gặp cache miss. Average dễ bị ảnh hưởng bởi outlier và không phản ánh trải nghiệm của phần lớn lần chạy.

Nên theo dõi:

- **p50:** thời gian điển hình của một nửa số job.
- **p90:** 90% job hoàn tất trong khoảng này.
- **p95:** hữu ích để phát hiện trải nghiệm chậm ở đuôi.
- **p99:** cho thấy những lần chạy rất chậm nhưng cần đủ mẫu.
- **Max:** dùng để tìm sự cố cực đoan, không dùng riêng làm mục tiêu.
- **Count:** số lần chạy được dùng để tính percentile.

### 9.1. Histogram cho queue time

Nếu hệ thống instrumentation phát histogram ci_job_queue_duration_seconds, có thể truy vấn p95 theo runner pool:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, runner_pool) (
    rate(ci_job_queue_duration_seconds_bucket[1h])
  )
)
~~~

Đây là metric minh họa; cần tạo histogram và label tương ứng trong hệ thống đo lường. Nếu muốn xem p95 theo job:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, job_name) (
    rate(ci_job_queue_duration_seconds_bucket[1h])
  )
)
~~~

### 9.2. Histogram cho job duration

~~~promql
histogram_quantile(
  0.95,
  sum by (le, job_name) (
    rate(ci_job_duration_seconds_bucket[1h])
  )
)
~~~

Có thể xây metric tương tự cho runner provisioning, step duration và end-to-end feedback. Chọn bucket phù hợp với quy mô thời gian thực tế: queue có thể tính bằng giây, còn integration test có thể kéo dài hàng chục phút.

### 9.3. Không gộp các nhóm khác bản chất

Một histogram tổng hợp tất cả job có thể gây hiểu lầm. Job lint 5 giây và integration test 15 phút có phân phối rất khác. Hãy phân nhóm theo job class hoặc stage, nhưng giữ label có cardinality thấp và ổn định.

Khi xem p95, luôn hiển thị sample count. p95 từ 20 mẫu không đáng tin như p95 từ hàng nghìn mẫu. Với nhóm ít chạy, có thể xem raw run hoặc cửa sổ thời gian dài hơn.

## 10. Dashboard theo dõi thời gian chờ và thời gian job

Một dashboard hữu ích cần trả lời nhanh:

- Job đang chờ runner bao lâu?
- Pool nào có queue time tăng?
- Runner provisioning có chậm không?
- Job hoặc step nào chiếm nhiều thời gian?
- Pipeline đầu-cuối đang bị critical path nào chi phối?
- Thời gian feedback thay đổi thế nào theo ngày/tuần?
- Tỷ lệ job fail, timeout, retry có tăng cùng thời gian chạy không?

Một bố cục dashboard tham khảo:

| Panel | Nội dung | Phân nhóm |
|---|---|---|
| Queue time | p50/p95 queue duration | Runner pool, job class |
| Provisioning | p50/p95 runner startup | Runner image, machine type |
| Job duration | p50/p95 duration | Job name, stage |
| Step duration | Top step chậm nhất | Job name, step |
| Feedback time | Trigger đến first/required feedback | Workflow, branch type |
| Queue depth | Số job đủ điều kiện đang chờ | Runner pool |
| Runner capacity | Busy/idle/starting/available | Pool, machine type |
| Reliability | Fail, timeout, retry rate | Job class, runner pool |
| Data quality | Tỷ lệ event thiếu hoặc duration bất thường | Provider, runner image |

### 10.1. Release và change marker

Khi runner image, concurrency limit, cache policy hoặc workflow được thay đổi, hãy ghi marker vào dashboard. Điều này giúp so sánh trước và sau thay đổi và biết liệu queue/job duration cải thiện có trùng với một thay đổi cụ thể hay không.

### 10.2. Bảo vệ dữ liệu và cardinality

Không dùng email, username, commit SHA hoặc run ID làm label trên mọi metric time series. Các trường đó phù hợp với log/event để drill down. Metrics nên dùng các dimension có tập giá trị giới hạn như repository group, workflow, job name, runner pool, OS và result.

Dashboard chứa tên repository hoặc thông tin pipeline nội bộ cần quyền truy cập phù hợp. Không đưa secret hoặc command line có token vào log chỉ để tăng khả năng chẩn đoán.

## 11. Đọc dữ liệu để tìm nút thắt

Kết hợp queue, provisioning, job và step duration giúp xác định nhóm nguyên nhân.

| Mẫu quan sát | Khả năng | Hướng kiểm tra |
|---|---|---|
| Queue p95 tăng, job duration ổn định | Thiếu runner hoặc scheduler bị giới hạn | Capacity, concurrency, quota và label |
| Queue thấp, provisioning cao | Autoscaler hoặc runner startup chậm | Warm pool, image pull, bootstrap và cloud API |
| Queue và provisioning thấp, job duration tăng | Công việc bên trong job chậm | Step timings, CPU/memory, dependency và cache |
| Một step tăng đột ngột | Bottleneck cục bộ | Log, network, artifact, test hoặc command |
| Pipeline duration cao nhưng job duration riêng lẻ bình thường | Dependency wait hoặc critical path | DAG, needs và thứ tự stage |
| p50 ổn định nhưng p95/p99 tăng | Outlier, pool không đồng đều hoặc burst traffic | Phân nhóm runner, thời điểm và job class |
| Job duration thấp nhưng feedback time cao | Feedback publishing hoặc gate phía sau chậm | Required checks, report upload và notification |
| Queue tăng theo giờ cao điểm | Capacity không theo kịp nhu cầu | Autoscaling, lịch chạy và concurrency |
| Một runner image luôn chậm | Image hoặc toolchain có vấn đề | Startup scripts, image size, package install |
| Thời gian giảm nhưng failure rate tăng | Có thể đã bỏ bước hoặc timeout quá gắt | So sánh gate, retry và kết quả chất lượng |

Không nên tối ưu dựa trên một lần chạy bất thường. Hãy kiểm tra xu hướng, sample count, thay đổi đồng thời và độ ổn định của hệ thống đo lường.

## 12. Dùng số đo để cải thiện thời gian phản hồi

Sau khi tìm được nút thắt, chọn hành động đúng với khoảng thời gian đang chiếm ưu thế.

### 12.1. Khi queue time cao

- Tăng hoặc autoscale runner pool theo nhu cầu thực tế.
- Tạo warm pool cho loại máy khởi tạo lâu.
- Phân tách pool theo workload và trust level.
- Điều chỉnh concurrency limit hoặc quota nếu có cơ sở.
- Tránh yêu cầu label/machine type quá đặc thù nếu không cần.
- Dùng runner lớn hơn khi job nhỏ bị xếp hàng vì thiếu máy phù hợp, nhưng đo chi phí và throughput.
- Phân bổ job theo mức ưu tiên hợp lý.

Tăng số runner không phải lúc nào cũng giải quyết được queue. Nếu bottleneck là quota cloud, registry hoặc database test dùng chung, thêm runner có thể làm dependency quá tải hơn.

### 12.2. Khi provisioning time cao

- Tạo runner image đã cài sẵn toolchain cần thiết.
- Giảm thao tác tải package trong startup script.
- Dùng image cache hoặc warm runner khi phù hợp.
- Đo riêng thời gian VM creation, image pull, bootstrap và agent registration.
- Kiểm tra cloud API, network và registry trong giai đoạn khởi tạo.
- Loại bỏ bước cài đặt trùng lặp ở cả image và job.

### 12.3. Khi job/step duration cao

- Dùng cache dependency đúng key và có kiểm soát invalidation.
- Chạy song song các test độc lập.
- Chia test suite thành shard cân bằng.
- Giảm việc tải lại artifact hoặc dependency không cần thiết.
- Tránh build lại cùng một artifact ở các stage chỉ để đổi cấu hình môi trường.
- Tối ưu bước có thời gian lớn trên critical path.
- Dùng incremental build khi công cụ hỗ trợ và có thể bảo đảm tính đúng đắn.
- Giảm dữ liệu hoặc scope của test nhanh trên pull request, đồng thời giữ gate đầy đủ cho release.

### 12.4. Khi dependency wait hoặc critical path cao

- Kiểm tra job dependency có thật sự cần thiết không.
- Cho phép lint/unit test độc lập chạy sớm.
- Tách job chuẩn bị artifact khỏi test không phụ thuộc artifact nếu phù hợp.
- Tránh chuỗi dependency tuần tự không cần thiết.
- Chỉ gom các bước vào một job khi chi phí startup lớn hơn lợi ích chạy song song.
- Không tạo quá nhiều job nhỏ nếu mỗi job đều phải cấp runner và checkout lại.

Song song hóa có overhead. Chia một job 2 phút thành 20 job nhỏ có thể tăng queue và provisioning nhiều hơn thời gian tiết kiệm được. Cần đo trước và sau trên cùng workload.

## 13. Đặt mục tiêu và đánh giá thay đổi

Không có một ngưỡng queue time hoặc job duration phù hợp cho mọi tổ chức. Mục tiêu nên dựa trên trải nghiệm nhà phát triển, loại workflow, số lượng job và mức độ quan trọng của feedback.

Có thể đặt SLI/SLO nội bộ, ví dụ:

- p95 queue time của runner pool dưới một ngưỡng đã thống nhất.
- p95 thời gian đến first feedback của pull request dưới mục tiêu.
- p95 job duration của nhóm unit test không tăng quá mức cho phép.
- Tỷ lệ job thiếu telemetry dưới ngưỡng nhỏ.
- Tỷ lệ retry hoặc timeout không tăng sau tối ưu.

Ví dụ policy minh họa:

~~~yaml
pipeline_timing:
  measurements:
    - dependency_wait
    - runner_queue
    - runner_provisioning
    - job_duration
    - step_duration
    - time_to_first_feedback
    - time_to_required_checks

  reporting:
    percentiles:
      - p50
      - p90
      - p95
    include_sample_count: true
    group_by:
      - workflow
      - job_name
      - runner_pool
      - result

  objectives:
    pull_request:
      queue_p95_seconds: 60
      first_feedback_p95_seconds: 180
    data_quality:
      missing_timestamps: 0
      negative_durations: 0
~~~

Các con số trong ví dụ chỉ để minh họa cách biểu diễn mục tiêu, không phải chuẩn chung. Hãy đặt mục tiêu từ baseline, kỳ vọng của nhóm và năng lực nền tảng. Đừng tối ưu duration bằng cách bỏ required check hoặc giảm độ bao phủ test mà không đánh giá rủi ro.

### 13.1. So sánh trước và sau tối ưu

Khi đánh giá một thay đổi:

1. Chọn workflow và job đại diện.
2. Thu thập baseline đủ số lần chạy.
3. Giữ nguyên hoặc ghi lại workload, runner type và thời gian trong ngày.
4. Thay đổi một nhóm yếu tố tại một thời điểm nếu có thể.
5. So sánh p50/p95, sample count, queue, provisioning, job và feedback time.
6. Kiểm tra failure rate, retry rate và chất lượng gate.
7. Ghi kết quả và quyết định giữ, điều chỉnh hoặc revert thay đổi.

Một tối ưu tốt làm giảm thời gian chờ hoặc thực thi mà không làm tăng lỗi, giảm chất lượng kiểm tra hay tạo áp lực quá mức lên dependency.

## 14. Troubleshooting dữ liệu thời gian bất thường

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Queue duration âm | Clock skew hoặc timestamp sai thứ tự | Đồng bộ clock, kiểm tra event source |
| Job duration bằng 0 | Thiếu timestamp, làm tròn hoặc job bị skip | Kiểm tra result và event completeness |
| Queue time đột ngột bằng 0 cho mọi job | Metric instrumentation ngừng phát event | Kiểm tra exporter và pipeline telemetry |
| Job duration tăng nhưng step duration không đổi | Startup/teardown hoặc khoảng trống trong job | Đo checkout, setup, artifact và cleanup |
| p95 tăng nhưng average ổn định | Một nhóm job/runner bị chậm | Phân tách pool, job name và thời điểm |
| Tổng job duration lớn hơn pipeline duration | Nhiều job chạy song song | Kiểm tra DAG và critical path |
| Feedback time lớn hơn thời điểm job cuối hoàn tất | Report upload, check publishing hoặc notification chậm | Đo thời gian publish riêng |
| Một runner pool có queue cao dù idle máy | Label mismatch hoặc scheduler không chọn runner | Kiểm tra labels, eligibility và policy |
| Job bắt đầu trễ dù runner ready | Agent registration, workspace hoặc setup | Đo startup gap |
| Duration biến động mạnh giữa các lần chạy | Workload, cache, runner contention hoặc test data | Phân nhóm cache hit, machine type và workload |

Nếu dữ liệu không đầy đủ, không thay giá trị thiếu bằng 0. Hãy ghi unknown, missing hoặc bỏ mẫu khỏi phép tính với một chỉ số riêng cho tỷ lệ dữ liệu thiếu. Nếu không, percentile sẽ trông tốt giả tạo.

## 15. Tình huống mẫu: xác định vì sao pull request phản hồi chậm

Một nhóm nhận thấy pull request thường mất khoảng 12 phút mới có đủ required checks, nhưng chưa rõ nguyên nhân.

1. Nhóm thêm event timestamp cho workflow trigger, job eligible, runner assigned, runner ready, job start và job completion.
2. Dashboard cho thấy p95 queue time của linux-large tăng lên 3 phút vào giờ cao điểm.
3. Provisioning time của pool này chỉ khoảng 12 giây, nên khởi tạo máy không phải nút thắt chính.
4. Job unit-test có execution duration p95 khoảng 6 phút, tăng từ 4 phút sau khi số test tăng.
5. Step breakdown cho thấy phần lớn thời gian nằm ở integration-style test bị chạy chung trong unit-test job.
6. Nhóm tách test nhanh và test cần database thành hai job, đồng thời giữ các required checks tương ứng.
7. Lint và unit test nhanh chạy song song, trả first feedback sớm; test cần database tiếp tục chạy và vẫn là gate bắt buộc.
8. Nhóm tăng capacity linux-large có kiểm soát trong giờ cao điểm, sau đó đo lại queue p95.
9. Sau một tuần, p95 queue giảm, first feedback ngắn hơn và required checks hoàn tất nhanh hơn. Failure rate và độ bao phủ test không suy giảm.
10. Nhóm ghi lại baseline, thay đổi runner pool, thay đổi DAG và kết quả đo để các nhóm khác có thể học theo.

Tình huống này cho thấy một con số tổng 12 phút không đủ để quyết định cần thêm runner hay tối ưu test. Chỉ khi tách queue, provisioning, execution và critical path, nhóm mới chọn đúng hành động.

## 16. Lộ trình thực hành

Có thể thực hành trên một workflow CI mẫu theo các bước:

1. **Liệt kê job và dependency:** vẽ DAG, xác định job chạy song song và job chặn kết quả.
2. **Chuẩn hóa timestamp:** ghi workflow trigger, job eligible, runner assignment, runner ready, job start và job completion.
3. **Tính các duration:** dependency wait, queue, provisioning, startup, job và end-to-end feedback.
4. **Đo step duration:** thêm tên step ổn định và ghi thời gian bắt đầu/kết thúc.
5. **Tạo dashboard:** hiển thị p50/p90/p95, sample count, queue depth và runner capacity.
6. **Phân nhóm:** xem theo runner pool, job name, stage, OS và result.
7. **Tìm critical path:** xác định chuỗi dependency quyết định required feedback.
8. **Tạo tình huống queue cao:** giới hạn runner trong môi trường thử nghiệm và quan sát queue duration.
9. **Tạo tình huống job chậm:** tăng workload hoặc tắt cache trong thử nghiệm để xem step duration thay đổi.
10. **Đề xuất tối ưu:** chọn capacity, provisioning, cache, parallelism hoặc DAG dựa trên bằng chứng.
11. **Đo trước/sau:** so sánh cùng loại workload, giữ sample count và failure rate.
12. **Kiểm tra chất lượng telemetry:** xác nhận không có duration âm, event thiếu hoặc label cardinality không kiểm soát.

### Tiêu chí hoàn thành

Người học có thể xem bài thực hành hoàn thành khi chứng minh được:

- Phân biệt dependency wait, runner queue, provisioning, startup, job duration và step duration.
- Chọn đúng mốc job_eligible_at để đo queue thuần khi job có dependency.
- Giải thích được giới hạn khi nền tảng chỉ cung cấp queued và started timestamp.
- Tính được duration từ timestamp và phát hiện clock skew.
- Phân biệt job duration với pipeline duration và critical path.
- Đo first feedback và thời gian đến required checks.
- Phân tích p50/p90/p95/p99 kèm sample count.
- Phân nhóm queue/job duration theo runner pool và job class.
- Xác định được nút thắt từ dashboard và step breakdown.
- Đề xuất tối ưu có số đo trước/sau và không làm suy giảm chất lượng gate.

## Kết luận

Để cải thiện tốc độ feedback CI/CD, cần đo riêng thời gian job chờ runner, thời gian runner khởi tạo, thời gian thực thi từng job và step, cùng thời gian đầu-cuối từ trigger đến kết quả. Timestamp phải có định nghĩa thống nhất; dependency wait không được nhầm thành queue; provisioning không được gộp vào queue nếu hệ thống có thể tách.

Dashboard nên hiển thị percentile, sample count, queue depth, runner capacity và duration theo job/step. Kết hợp với đồ thị dependency và critical path, nhóm có thể xác định nên tăng capacity, rút ngắn startup, tối ưu step hay thay đổi thứ tự chạy. Mọi cải thiện cần được so sánh trước/sau trên workload tương đương và giữ nguyên chất lượng kiểm tra. Khi đó, “pipeline chậm” trở thành một vấn đề có thể đo, giải thích và xử lý theo bằng chứng.

