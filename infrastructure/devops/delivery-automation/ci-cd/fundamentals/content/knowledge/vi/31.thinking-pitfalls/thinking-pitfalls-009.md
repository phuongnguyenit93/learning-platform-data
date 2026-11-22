# Tối ưu thời gian pipeline mà bỏ qua thời gian chờ và độ tin cậy

## Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích vì sao giảm thời gian thực thi job chưa chắc làm thay đổi thời gian giao phần mềm.
- Phân biệt elapsed time, execution time, queue time, dependency wait, approval wait và thời gian chờ môi trường.
- Phân tích thời gian từ lúc thay đổi được tạo đến khi release được xác minh.
- Nhận diện các dạng chờ bị che khuất trong dashboard pipeline.
- Đánh giá độ tin cậy của pipeline, test suite, runner và các dịch vụ phụ thuộc.
- Dùng percentile, flow efficiency, critical path và Little’s Law để tìm bottleneck.
- Chọn cải tiến dựa trên baseline và guardrail, tránh giảm thời gian bằng cách bỏ kiểm thử hoặc hạ chất lượng.
- Thiết kế dashboard và quy trình cải tiến cân bằng tốc độ, độ tin cậy và kết quả giao phần mềm.

## 1. Sai lầm: chỉ nhìn thời gian job chạy

Một pipeline có thể được tối ưu từ 20 phút xuống 8 phút, nhưng developer vẫn phải chờ nhiều giờ hoặc nhiều ngày để thay đổi đến production. Nguyên nhân là thời gian thực thi job chỉ là một phần của toàn bộ thời gian giao phần mềm.

Ví dụ:

- Job build và test chỉ mất 8 phút, nhưng chờ runner 12 phút.
- Pull request chờ reviewer hai ngày.
- Sau khi merge, release chỉ được phép chạy trong một cửa sổ thay đổi vào tối thứ Sáu.
- Deployment hoàn tất nhưng phải chờ người vận hành xác nhận.
- Test flaky khiến pipeline phải retry nhiều lần.
- Môi trường integration test dùng chung đang bị chiếm bởi pipeline khác.
- Scanner hoặc registry bên ngoài không ổn định khiến các job phải chờ hoặc chạy lại.

Nếu dashboard chỉ hiển thị thời gian thực thi job, những khoảng chờ này có thể biến mất khỏi góc nhìn của đội ngũ. Kết quả là team tối ưu phần dễ đo nhưng không xử lý nguyên nhân khiến người dùng phải chờ lâu.

Cần phân biệt hai câu hỏi:

1. **Pipeline thực thi nhanh đến đâu?** Đây là câu hỏi về thời gian job, critical path, runner và công cụ.
2. **Thay đổi được giao đến người dùng nhanh và đáng tin cậy đến đâu?** Đây là câu hỏi về toàn bộ luồng từ commit, review, kiểm thử, phê duyệt, phát hành, triển khai đến xác minh.

Tối ưu thời gian pipeline là mục tiêu hợp lý. Sai lầm xuất hiện khi coi đó là đại diện cho tốc độ giao phần mềm và bỏ qua thời gian chờ cũng như độ tin cậy.

## 2. Phân rã thời gian từ đầu đến cuối

Để hiểu một thay đổi mất bao lâu, cần xác định rõ điểm bắt đầu và điểm kết thúc rồi chia khoảng thời gian thành các giai đoạn.

Một mô hình tham khảo:

~~~text
Change created
    |
    v
Review wait
    |
    v
Review and revision
    |
    v
CI queue wait
    |
    v
Build / test / scan execution
    |
    v
Dependency or environment wait
    |
    v
Approval / release wait
    |
    v
Deployment execution
    |
    v
Post-deploy observation and verification
    |
    v
Verified release
~~~

Có thể phân rã tổng thời gian như sau:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Review wait | Thời gian chờ người review | PR chờ reviewer |
| Review/rework | Thời gian trao đổi và sửa đổi | Review comment, cập nhật code |
| CI queue wait | Job đã sẵn sàng nhưng chưa có runner | Runner pool đầy |
| CI execution | Thời gian build, test, scan thực thi | Compile, unit test |
| Dependency wait | Chờ job hoặc workflow khác | Chờ artifact, upstream pipeline |
| Environment wait | Chờ môi trường hoặc dữ liệu test | Staging đang bị chiếm |
| Approval wait | Chờ quyết định hoặc phê duyệt | Production approval |
| Release wait | Chờ lịch phát hành hoặc batch release | Chỉ deploy theo change window |
| Deployment execution | Thời gian áp dụng thay đổi | Rollout, migration |
| Verification | Chờ và thực hiện kiểm tra sau deploy | Smoke test, canary analysis |

Không phải mọi hệ thống đều có tất cả các giai đoạn. Điều quan trọng là ghi nhận được các khoảng chờ có ý nghĩa thay vì gộp chúng vào một con số pipeline duration.

Một công thức đơn giản:

\[
T_{end-to-end} =
T_{active} + T_{waiting}
\]

Trong đó:

- \(T_{active}\) là thời gian thực sự xử lý công việc.
- \(T_{waiting}\) là thời gian chờ người, runner, dependency, môi trường hoặc quyết định.

Đây là phép phân rã ở cấp luồng công việc. Nếu nhiều job chạy song song, không thể cộng toàn bộ execution time của từng job để ra wall-clock duration. Cần dùng critical path và thời điểm bắt đầu/kết thúc thực tế.

## 3. Phân biệt các loại thời gian chờ

### 3.1. Chờ sự kiện và khởi tạo workflow

Một commit có thể đã được push nhưng workflow chưa bắt đầu vì:

- Webhook đến chậm hoặc được xử lý theo batch.
- Hệ thống CI đang quá tải.
- Workflow bị giới hạn concurrency.
- Pipeline chờ một workflow upstream.
- Trigger filter không khớp hoặc sự kiện cần xử lý thủ công.

Nếu chỉ đo từ lúc runner bắt đầu, thời gian trước đó sẽ không xuất hiện.

Cần ghi timestamp cho event source, workflow creation và job readiness nếu nền tảng cung cấp.

### 3.2. Chờ runner

Job đã sẵn sàng nhưng chưa được cấp runner phù hợp.

Nguyên nhân thường gặp:

- Không đủ runner.
- Runner label hoặc architecture không phù hợp.
- Quota concurrency đã hết.
- Runner đang provision hoặc khởi động.
- Một nhóm job fan-out chiếm hết capacity.
- Priority của pipeline chưa phù hợp với nhu cầu.

Tăng số runner có thể giúp, nhưng cần xem queue theo runner class và loại workload. Một runner Linux có thể rảnh nhưng không chạy được job cần Windows hoặc thiết bị đặc thù.

### 3.3. Chờ dependency

Job có thể bị block bởi dependency dù runner đã sẵn sàng.

Ví dụ:

- Integration test chờ service dependency khởi động.
- Deploy chờ artifact được publish.
- Release chờ kết quả security scan.
- Downstream pipeline chờ upstream pipeline hoàn tất.
- Migration chờ một thay đổi schema trước đó.

Dependency wait cần được phân biệt với runner queue. Tăng runner không giúp nếu job chưa đủ điều kiện bắt đầu.

### 3.4. Chờ môi trường

Môi trường dùng chung thường trở thành điểm nghẽn:

- Staging đang được một nhóm khác sử dụng.
- Database test đang chạy migration.
- Namespace chưa được cleanup.
- Test account bị khóa hoặc đang được sử dụng.
- External sandbox đạt quota.
- Environment provisioning mất nhiều thời gian.

Có thể giảm thời gian chờ bằng môi trường ephemeral, dữ liệu test độc lập, namespace riêng hoặc queue có giới hạn. Tuy nhiên, cần giữ mức đại diện đủ tốt so với production.

### 3.5. Chờ approval và release window

Một pipeline có thể hoàn tất mọi kiểm tra nhưng chưa được phép deploy.

Ví dụ:

- Chờ product owner xác nhận.
- Chờ security exception.
- Chờ change manager.
- Chờ người trực production.
- Chờ khung giờ thay đổi.
- Chờ một nhóm release gom nhiều thay đổi.

Không nên tự động xóa approval chỉ để giảm lead time. Cần xác định approval nào thực sự kiểm soát rủi ro, approval nào lặp lại cùng một thông tin và approval nào có thể chuyển thành policy tự động.

### 3.6. Chờ xác minh sau triển khai

Một release không nên được coi là hoàn tất ngay khi lệnh deploy trả về thành công.

Có thể cần chờ:

- Readiness của toàn bộ instance.
- Traffic shift hoàn tất.
- Canary observation window.
- Smoke test.
- Error rate và latency ổn định.
- Queue backlog xử lý xong.
- Business transaction được xác minh.

Đây là thời gian chờ có chủ đích để giảm rủi ro. Không nên loại bỏ nó chỉ vì dashboard cho thấy pipeline lâu hơn.

## 4. Thời gian chờ và thời gian thực thi cần được đo riêng

Một dashboard hữu ích nên tách ít nhất:

| Chỉ số | Cách hiểu | Hành động khi tăng |
|---|---|---|
| Event-to-workflow delay | Từ sự kiện đến khi workflow được tạo | Kiểm tra webhook và CI control plane |
| Queue time | Job sẵn sàng đến khi runner bắt đầu | Kiểm tra capacity, labels và quota |
| Provisioning time | Thời gian tạo runner hoặc môi trường | Tối ưu image, autoscaling và provisioning |
| Job execution time | Thời gian job thực thi | Profile command, cache và workload |
| Dependency wait | Chờ job hoặc workflow phụ thuộc | Rà soát DAG và upstream bottleneck |
| Environment wait | Chờ môi trường hoặc tài nguyên test | Isolation, ephemeral environment, queue |
| Approval wait | Chờ người hoặc policy phê duyệt | Làm rõ owner, SLA và tự động hóa phù hợp |
| Deployment time | Thời gian rollout thực tế | Kiểm tra strategy, health và capacity |
| Verification time | Thời gian quan sát và xác minh | Kiểm tra test, telemetry và cửa sổ quan sát |

Cần thống nhất timestamp và định nghĩa. Ví dụ queue time nên bắt đầu khi job đã sẵn sàng, không phải từ lúc workflow được tạo nếu job còn chờ dependency.

Nếu dữ liệu thời gian không đầy đủ, hãy ghi nhận missing segment. Không tự gán khoảng thời gian không biết thành execution time hoặc waiting time.

## 5. Độ tin cậy là một phần của tốc độ

Một pipeline chạy nhanh nhưng thường xuyên cho kết quả sai hoặc không ổn định sẽ làm tổng thời gian giao phần mềm tăng lên.

Các dạng không đáng tin cậy:

- Test flaky.
- Runner mất kết nối.
- Dependency repository bị gián đoạn.
- Cache trả về dữ liệu không tương thích.
- External test service không ổn định.
- Scanner timeout.
- Artifact upload/download lỗi.
- Migration không idempotent.
- Deployment chỉ thành công một phần.
- Report bị thiếu hoặc thuộc run cũ.

Mỗi lần retry đều tiêu tốn thời gian và có thể làm người dùng mất niềm tin vào pipeline. Nếu team quen retry đến khi pass, một lỗi thực sự có thể bị che giấu.

Cần đo không chỉ lần chạy cuối mà cả lịch sử attempt:

- First-attempt success rate.
- Retry rate.
- Flaky test rate.
- Infrastructure failure rate.
- Tool/service availability.
- Artifact publication failure rate.
- Deployment success và partial deployment rate.
- False positive/false negative của quality gate nếu có cách xác định.

Tốc độ đáng tin cậy thường tốt hơn một lần chạy rất nhanh nhưng cần nhiều lần thử.

## 6. Retry có thể làm pipeline trông nhanh hơn hoặc tốt hơn một cách giả tạo

Giả sử một test suite có tỷ lệ pass 90% ở lần chạy đầu, nhưng pipeline tự retry tối đa ba lần và chỉ báo trạng thái cuối cùng. Nếu lần thứ hai pass, dashboard có thể ghi thành công.

Tuy nhiên, developer đã phải chờ thêm một lần chạy và độ tin cậy của test suite vẫn thấp.

Cần phân biệt:

- **First-attempt success:** tỷ lệ thành công ngay lần đầu.
- **Eventual success:** tỷ lệ cuối cùng đạt sau retry.
- **Retry rate:** tỷ lệ run hoặc job cần retry.
- **Retry recovery:** tỷ lệ retry thành công.
- **Flaky failure:** lỗi không tái hiện ổn định với cùng điều kiện.
- **Infrastructure failure:** lỗi do runner, network hoặc dịch vụ ngoài.
- **Product failure:** lỗi thực sự của code hoặc hành vi ứng dụng.

Retry hợp lý cho lỗi tạm thời có thể giúp hệ thống bền hơn. Retry không giới hạn hoặc retry mọi loại lỗi sẽ tăng thời gian, tải và che giấu nguyên nhân.

Nên có:

- Phân loại lỗi có thể retry.
- Giới hạn số lần retry.
- Exponential backoff và jitter khi phù hợp.
- Ghi nhận kết quả từng attempt.
- Cảnh báo khi retry rate vượt baseline.
- Owner xử lý flaky test hoặc dependency không ổn định.

## 7. Đừng giảm thời gian bằng cách bỏ kiểm thử

Một cách làm pipeline nhanh giả tạo là loại bỏ những bước lâu:

- Bỏ integration test.
- Bỏ security scan.
- Giảm số test case mà không phân tích rủi ro.
- Tắt test flaky thay vì sửa.
- Dùng cache không xác minh.
- Bỏ post-deploy verification.
- Bỏ quality gate khi pipeline chậm.
- Chỉ chạy test trên một module dù thay đổi ảnh hưởng nhiều module.

Những cách này có thể giảm job duration nhưng làm tăng defect escape, incident và thời gian recovery.

Thay vì bỏ kiểm tra, hãy tối ưu cách thực hiện:

- Chạy song song các test độc lập.
- Chạy test phù hợp theo phạm vi thay đổi nhưng giữ full suite ở lịch hoặc gate cần thiết.
- Chia test theo criticality và thời gian.
- Cải thiện test data và environment provisioning.
- Loại bỏ duplicate test có bằng chứng.
- Sửa flaky test.
- Tối ưu fixture và dependency startup.
- Dùng contract test để phát hiện lỗi giao tiếp sớm.
- Giữ smoke test và post-deploy verification cho luồng quan trọng.

Nếu cần thay đổi phạm vi kiểm thử, phải có risk assessment, owner và guardrail. Không được coi việc giảm số test là cải tiến chỉ vì pipeline ngắn hơn.

## 8. Critical path và job song song

Pipeline thường là DAG. Thời gian tổng thể chịu ảnh hưởng của critical path, không phải tổng duration của mọi job.

Ví dụ:

~~~mermaid
flowchart TD
    A["Checkout"] --> B["Lint"]
    A --> C["Unit tests"]
    A --> D["Dependency scan"]
    B --> E["Package"]
    C --> E
    D --> E
    E --> F["Integration tests"]
    F --> G["Approval"]
    G --> H["Deploy"]
    H --> I["Post-deploy verification"]
~~~

Lint, unit test và dependency scan có thể chạy song song. Nhưng nếu integration test chờ package thì không thể bỏ dependency đó.

Tối ưu critical path bằng cách:

- Tìm job có duration dài nhất trên đường găng.
- Giảm queue wait của các job trên critical path.
- Cân bằng test shards.
- Tránh tạo dependency giả.
- Cache dependency một cách an toàn.
- Provision môi trường trước khi job cần dùng.
- Chuẩn bị artifact và test data sớm.
- Đảm bảo runner capacity phù hợp.

Không nên tăng concurrency vô hạn. Quá nhiều job đồng thời có thể làm CPU, memory, disk, registry hoặc external API bị quá tải, khiến từng job chậm hơn và flaky hơn.

## 9. Little’s Law giúp hiểu hàng đợi và WIP

Little’s Law mô tả mối quan hệ giữa số lượng công việc trung bình trong hệ thống, throughput và thời gian trung bình:

\[
L = \lambda W
\]

Trong đó:

- \(L\): số công việc trung bình đang nằm trong hệ thống (WIP).
- \(\lambda\): throughput trung bình, số công việc hoàn tất trên một đơn vị thời gian.
- \(W\): thời gian trung bình một công việc ở trong hệ thống.

Ví dụ, nếu trung bình có 20 job đang chờ hoặc chạy và hệ thống hoàn tất 10 job mỗi giờ, thời gian trung bình trong hệ thống xấp xỉ 2 giờ theo mô hình ổn định.

Định luật này không nói rằng tăng WIP sẽ tự động tăng throughput. Nếu capacity cố định, thêm job vào hàng đợi thường làm thời gian chờ tăng. Khi hệ thống chưa ổn định hoặc throughput thay đổi mạnh, cần thận trọng khi áp dụng công thức.

Có thể dùng Little’s Law để đặt câu hỏi:

- WIP đang tăng vì job đến nhiều hơn hay vì job hoàn tất chậm?
- Throughput có bị giới hạn bởi runner hay approval?
- Queue dài có phải do fan-out quá lớn?
- Có thể giảm WIP bằng cách giới hạn số run hoặc chia nhỏ thay đổi không?

## 10. Percentile quan trọng hơn chỉ nhìn trung bình

Thời gian pipeline thường có phân phối lệch: nhiều run nhanh nhưng một số run rất chậm.

Nên theo dõi:

- p50: trải nghiệm điển hình.
- p90: nhóm run chậm hơn.
- p95: tail latency ở mức cao.
- p99: hữu ích khi volume đủ lớn và cần hiểu các trường hợp hiếm.
- Mean: hữu ích cho một số bài toán tổng tài nguyên nhưng dễ bị outlier chi phối.

Ví dụ:

| Chỉ số | Trước tối ưu | Sau tối ưu |
|---|---:|---:|
| Pipeline duration p50 | 12 phút | 8 phút |
| Pipeline duration p95 | 35 phút | 38 phút |
| Queue time p50 | 2 phút | 1 phút |
| Queue time p95 | 18 phút | 25 phút |
| First-attempt success | 96% | 88% |
| Retry rate | 7% | 19% |

Trung vị đã tốt hơn, nhưng p95 và reliability xấu đi. Có thể việc tăng fan-out khiến runner pool quá tải; một số job chạy nhanh hơn nhưng nhóm còn lại phải chờ lâu và retry nhiều.

Chỉ báo cáo p50 sẽ che giấu vấn đề này. Cần xem phân phối, số lượng mẫu và segment theo runner class, repository, workflow type và giờ cao điểm.

## 11. Flow efficiency: thời gian thực sự tạo giá trị so với thời gian chờ

Flow efficiency là một cách nhìn tỷ lệ thời gian active so với tổng elapsed time.

Một định nghĩa đơn giản:

\[
Flow\ Efficiency =
\frac{Active\ Time}{Total\ Elapsed\ Time}
\times 100\%
\]

Ví dụ một thay đổi mất 5 ngày từ lúc bắt đầu đến khi verified production:

- 4 giờ viết code và test.
- 2 giờ review thực sự.
- 1 giờ xử lý CI.
- Phần còn lại là chờ review, approval, release window và môi trường.

Flow efficiency theo định nghĩa này khá thấp. Điều đó không tự chứng minh các khoảng chờ đều lãng phí: có thể một số là chờ phê duyệt có chủ đích hoặc cửa sổ quan sát an toàn. Cần phân loại waiting time thành:

- Chờ cần thiết để giảm rủi ro.
- Chờ do thiếu capacity.
- Chờ do phụ thuộc.
- Chờ do không rõ owner.
- Chờ do batch hoặc lịch phát hành.
- Chờ do lỗi và retry.

Mục tiêu không phải xóa mọi thời gian chờ. Mục tiêu là giảm chờ không tạo giá trị trong khi vẫn giữ các kiểm soát cần thiết.

## 12. Tối ưu approval mà không bỏ kiểm soát

Approval wait thường chiếm phần đáng kể của lead time. Tuy nhiên, tự động bỏ approval có thể làm tăng rủi ro.

Hãy phân loại:

- Approval bắt buộc theo policy hoặc phân tách nhiệm vụ.
- Approval dựa trên rủi ro của thay đổi.
- Approval lặp lại cùng một kiểm tra đã được tự động hóa.
- Approval chỉ mang tính thông báo.
- Approval bị chậm vì không có owner hoặc lịch trực.

Các cách cải thiện:

- Xác định owner và người thay thế.
- Đặt SLA phản hồi cho approval.
- Gửi request kèm evidence bundle và risk summary.
- Tự động phê duyệt các trường hợp low-risk đã đáp ứng policy.
- Chỉ yêu cầu human approval ở bước có quyết định thực sự.
- Dùng protected environment và policy-based approval.
- Ghi nhận lý do từ chối hoặc chờ.

Không nên biến approval thành nút bấm hình thức. Nếu người phê duyệt không có thông tin hoặc không có quyền kiểm tra bằng chứng, quy trình chỉ thêm thời gian mà không tăng an toàn.

## 13. Tối ưu môi trường và dependency

Môi trường test hoặc staging dùng chung có thể làm pipeline chậm và không ổn định.

Các giải pháp:

- Tạo ephemeral environment theo pull request hoặc run ID.
- Dùng database/schema riêng.
- Seed dữ liệu xác định và có thể tái lập.
- Dùng container cho dependency test.
- Cache image và package có kiểm soát.
- Health check readiness trước khi test.
- Cleanup theo owner và TTL.
- Dùng contract test khi không cần dựng toàn bộ hệ thống.
- Giới hạn concurrency theo quota của sandbox bên ngoài.

Không phải môi trường nào cũng nên ephemeral hoàn toàn. Test performance hoặc production-like integration có thể cần môi trường dùng chung được quản lý. Khi đó cần queue, lịch dùng, isolation và telemetry về thời gian chờ.

Cũng cần đảm bảo môi trường test đủ tương đồng với production ở các đặc điểm ảnh hưởng kết quả. Một môi trường quá khác có thể chạy nhanh nhưng không phát hiện lỗi thật.

## 14. Tối ưu cache và dependency mà không đánh đổi tính đúng

Cache có thể giảm thời gian tải dependency và build, nhưng cache sai hoặc không an toàn làm kết quả không đáng tin.

Cần:

- Cache key dựa trên lockfile, toolchain, OS và cấu hình liên quan.
- Không dùng cache như nguồn chuẩn của artifact.
- Xác minh dependency checksum hoặc signature khi phù hợp.
- Phân vùng cache theo trust boundary.
- Tránh job không tin cậy ghi cache dùng bởi job phát hành tin cậy.
- Có cách invalidate và rebuild sạch.
- Đo cache hit rate cùng tỷ lệ lỗi hoặc cache corruption.

Nếu build chỉ nhanh khi dùng cache nhưng không thể tái lập từ trạng thái sạch, pipeline đang phụ thuộc vào một trạng thái ẩn. Nên có clean build định kỳ hoặc ở release quan trọng để kiểm tra.

## 15. Reliability metrics cần đi cùng speed metrics

Một bảng điều khiển chỉ có duration và deployment frequency dễ dẫn đến tối ưu sai. Cần bổ sung các chỉ số độ tin cậy.

| Nhóm | Metric gợi ý | Câu hỏi |
|---|---|---|
| Pipeline reliability | First-attempt success rate | Bao nhiêu run đạt ngay lần đầu? |
| Test reliability | Flaky test rate | Test có cho kết quả ổn định không? |
| Infrastructure | Runner failure rate | Runner có làm gián đoạn workflow không? |
| Dependency | External service failure rate | Registry/scanner/test service có ổn định không? |
| Artifact | Publish/verification failure rate | Artifact có được tạo và xác minh đúng không? |
| Deployment | Partial/failed deployment rate | Rollout có hoàn tất đúng trạng thái không? |
| Recovery | Retry/recovery duration | Mất bao lâu để trở lại trạng thái tốt? |
| Service | SLO, error rate, latency | Dịch vụ có ổn định sau release không? |
| Delivery | Change failure rate | Thay đổi có gây remediation không? |

Cần phân biệt lỗi do sản phẩm với lỗi hạ tầng. Nếu registry outage khiến build thất bại, đó vẫn là sự cố của delivery system dù không phải lỗi code. Việc phân loại giúp chọn đúng owner và biện pháp.

## 16. Cân bằng tốc độ và độ tin cậy bằng guardrail

Mỗi cải tiến nên có metric chính và guardrail.

Ví dụ:

| Cải tiến | Metric chính | Guardrail |
|---|---|---|
| Tăng runner capacity | Queue time p50/p95 | Cost, utilization, failure rate |
| Chạy test song song | Critical path duration | Flaky rate, resource saturation |
| Cache dependency | Build duration | Cache corruption, reproducibility |
| Giảm approval wait | Approval wait | Change failure, policy compliance |
| Tạo ephemeral environment | Environment wait | Cost, environment parity, cleanup failures |
| Chia test theo thay đổi | Feedback time | Defect escape, full-suite coverage |
| Tăng deployment frequency | Lead time | Change failure, SLO, recovery time |
| Rút ngắn canary window | Release duration | Detection delay, escaped incident |

Không nên kết luận cải tiến thành công chỉ vì metric chính giảm. Nếu queue time giảm nhưng runner cost tăng gấp nhiều lần và failure rate tăng, cần đánh giá lại.

Guardrail giúp phát hiện tác động phụ và ngăn team tối ưu một phần của hệ thống bằng cách chuyển chi phí sang phần khác.

## 17. Quy trình chẩn đoán pipeline chậm

Khi pipeline hoặc delivery flow chậm, hãy đi theo thứ tự:

1. **Xác định phạm vi:** một job, một workflow, một repository, một môi trường hay mọi dự án?
2. **Xác định điểm đo:** từ event đến workflow, job ready đến runner, hay commit đến verified production?
3. **Phân rã thời gian:** queue, execution, dependency, environment, approval, deployment và verification.
4. **Xem phân phối:** p50, p90/p95 và các outlier.
5. **Phân đoạn:** theo runner, workflow type, branch, service, giờ cao điểm và loại thay đổi.
6. **Kiểm tra reliability:** retry, flaky test, runner failure, external dependency và partial deployment.
7. **Tìm critical path:** xác định đoạn chi phối thời gian hoàn tất.
8. **Nêu giả thuyết:** chọn một nguyên nhân có bằng chứng.
9. **Thử nghiệm có guardrail:** thay đổi phạm vi nhỏ và đo lại.
10. **Chuẩn hóa hoặc hoàn tác:** giữ cải tiến chỉ khi tốc độ và độ tin cậy cùng đáp ứng mục tiêu.

~~~mermaid
flowchart TD
    A["Pipeline / delivery chậm"] --> B["Phân rã elapsed time"]
    B --> C{"Thời gian chờ chiếm ưu thế?"}
    C -- "Có" --> D["Queue / dependency / approval / environment"]
    C -- "Không" --> E["Execution / critical path"]
    D --> F["Kiểm tra reliability và owner"]
    E --> F
    F --> G["Xác định bottleneck có bằng chứng"]
    G --> H["Thử nghiệm cải tiến có guardrail"]
    H --> I{"Speed và reliability cùng đạt?"}
    I -- "Có" --> J["Chuẩn hóa cải tiến"]
    I -- "Không" --> K["Điều chỉnh hoặc hoàn tác"]
~~~

Nếu dữ liệu chưa đủ để phân biệt queue và execution, bước đầu tiên có thể là bổ sung timestamp và instrumentation thay vì tăng runner hoặc viết lại workflow.

## 18. Ví dụ: build nhanh nhưng pull request vẫn chậm

Một nhóm Java service có số liệu:

| Thành phần | Thời gian trung vị |
|---|---:|
| PR chờ reviewer đầu tiên | 9 giờ |
| Review và sửa đổi | 5 giờ |
| CI queue | 8 phút |
| Build/test/scan execution | 11 phút |
| Chờ môi trường integration | 2 giờ |
| Integration test execution | 18 phút |
| Chờ release approval | 1 ngày |
| Deploy và verification | 25 phút |

Nhóm quyết định tối ưu build từ 11 phút xuống 6 phút. Tổng elapsed time chỉ giảm 5 phút trong một luồng kéo dài nhiều ngày.

Các bottleneck lớn hơn là:

- PR chờ reviewer.
- Môi trường integration test dùng chung.
- Release approval.

Các thử nghiệm phù hợp hơn:

- Thiết lập reviewer rotation và thông báo PR quá hạn.
- Tạo environment theo run hoặc queue có owner.
- Gửi evidence bundle cho approver và xác định SLA.
- Tự động hóa approval low-risk theo policy đã được chấp thuận.

Sau khi giảm các khoảng chờ, mới đánh giá tiếp execution time và critical path.

## 19. Ví dụ: tối ưu song song làm reliability xấu đi

Một nhóm tăng matrix test từ 4 lên 24 job đồng thời để giảm thời gian. Pipeline p50 giảm từ 30 xuống 17 phút, nhưng:

- Runner CPU và disk thường xuyên quá tải.
- Database test bị nhiều job tranh chấp.
- p95 tăng từ 50 lên 75 phút.
- Flaky test rate tăng.
- Một số job timeout rồi retry.
- External sandbox bắt đầu trả rate limit.

Cải tiến này đã tăng mức đồng thời vượt capacity thực tế.

Cách xử lý:

1. Đo resource utilization theo runner và test environment.
2. Giới hạn max parallelism theo loại workload.
3. Chia test suite thành nhóm cân bằng.
4. Cấp database/schema riêng hoặc dùng environment isolation.
5. Giới hạn request đến sandbox.
6. Theo dõi p50, p95, first-attempt success và retry rate.
7. Tăng capacity có chọn lọc nếu có bằng chứng thiếu tài nguyên.
8. So sánh chi phí và lợi ích sau thay đổi.

Mục tiêu là tối ưu critical path trong capacity có thể duy trì, không phải tối đa hóa số job chạy cùng lúc.

## 20. Thiết kế dashboard cân bằng

Một dashboard nên có cả tốc độ, thời gian chờ và độ tin cậy.

Có thể chia thành các khu vực:

**Flow**

- Commit-to-verified-production lead time.
- PR review wait.
- Approval wait.
- Deployment frequency.
- WIP và throughput.

**Pipeline**

- Queue time p50/p95.
- Job execution duration.
- Critical path duration.
- Pipeline duration p50/p95.
- Runner provisioning time.

**Reliability**

- First-attempt success rate.
- Retry rate.
- Flaky test rate.
- Infrastructure failure rate.
- Artifact publish failure.
- Partial deployment rate.

**Service outcomes**

- Change failure rate.
- Recovery time.
- SLO/error budget.
- Error rate và latency sau deploy.

Mỗi biểu đồ cần:

- Định nghĩa metric.
- Khoảng thời gian.
- Số lượng mẫu.
- Segment theo repository/service/workflow.
- Owner.
- Link đến run hoặc release record.
- Ghi chú khi thay đổi cách tính.

Không nên gom mọi chỉ số thành một điểm số pipeline health duy nhất. Một điểm tổng hợp có thể che giấu trường hợp pipeline nhanh nhưng test không đáng tin hoặc dịch vụ production đang suy giảm.

## 21. Những anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách cải thiện |
|---|---|---|
| Chỉ đo job execution time | Bỏ qua queue và approval wait | Đo toàn bộ elapsed time theo segment |
| Dùng pipeline duration thay lead time | Không thấy review và release bottleneck | Theo dõi commit-to-verified-production |
| Tăng runner để xử lý mọi loại chờ | Không giải quyết dependency hoặc approval wait | Phân loại đúng queue và blocking reason |
| Retry đến khi pass | Che giấu flaky test và lỗi thật | First-attempt success, retry rate và failure classification |
| Bỏ integration/security test để nhanh hơn | Tăng defect escape và incident | Tối ưu test execution, không xóa gate tùy tiện |
| Tăng concurrency vô hạn | Quá tải runner và môi trường | Giới hạn theo capacity, đo p95 |
| Tối ưu p50 nhưng bỏ qua p95 | Nhóm run chậm vẫn bị ảnh hưởng | Theo dõi percentile và phân đoạn |
| Xóa approval không phân tích rủi ro | Giảm kiểm soát release | Tự động hóa low-risk theo policy |
| Coi rollback command là recovery hoàn tất | Dữ liệu và dịch vụ có thể chưa ổn định | Xác minh SLO, business flow và data integrity |
| Dùng cache không xác minh | Build không tái lập hoặc dùng dữ liệu sai | Cache key, integrity và clean build |
| Dashboard chỉ có số liệu xanh/đỏ | Không biết nguyên nhân và owner | Hiển thị queue, execution, retry và blocking reason |
| Tối ưu một metric đơn lẻ | Chuyển chi phí sang phần khác | Metric chính và guardrail |

## 22. Checklist tối ưu thời gian pipeline an toàn

Trước khi triển khai một cải tiến, hãy xác nhận:

- [ ] Điểm bắt đầu và kết thúc của thời gian đo đã rõ.
- [ ] Queue time được tách khỏi job execution time.
- [ ] Có đo review, dependency, environment và approval wait phù hợp.
- [ ] Pipeline duration không bị dùng thay cho delivery lead time.
- [ ] Critical path đã được xác định.
- [ ] Có p50 và p90/p95, không chỉ mean.
- [ ] Có first-attempt success và retry rate.
- [ ] Flaky test được ghi nhận và có owner xử lý.
- [ ] Runner capacity và resource saturation được kiểm tra.
- [ ] Test scope và security gate không bị giảm tùy tiện.
- [ ] Môi trường test đủ ổn định và đại diện.
- [ ] Cache có key, integrity và clean-build strategy.
- [ ] Approval có owner, SLA và policy rõ.
- [ ] Post-deploy verification vẫn đáp ứng mục tiêu rủi ro.
- [ ] Có metric chính và guardrail cho cải tiến.
- [ ] Có baseline và thời gian đánh giá.
- [ ] Kết quả được phân đoạn theo workload và service.
- [ ] Có thể truy từ metric đến pipeline run, release và deployment.
- [ ] Cải tiến không làm tăng defect escape, change failure hoặc recovery time ngoài ngưỡng.

## 23. Bài tập tự đánh giá

Một nhóm báo cáo pipeline đã nhanh hơn sau đợt tối ưu:

- Pipeline duration p50 giảm từ 24 xuống 12 phút.
- Queue time p50 giảm từ 5 xuống 2 phút.
- Pipeline duration p95 tăng từ 42 lên 60 phút.
- First-attempt success giảm từ 97% xuống 89%.
- Retry rate tăng từ 4% lên 18%.
- Integration test thường chờ database dùng chung.
- PR review wait trung vị là 1,5 ngày.
- Production approval wait trung vị là 18 giờ.
- Change failure rate tăng từ 3% lên 9%.

Hãy phân tích:

1. Những chỉ số nào cho thấy pipeline đã nhanh hơn ở trường hợp điển hình?
2. Vì sao p95 và first-attempt success lại xấu đi?
3. Retry rate tăng có thể che giấu vấn đề gì?
4. Những khoảng chờ nào đang nằm ngoài pipeline execution?
5. Có nên tăng runner hoặc concurrency thêm không? Cần bằng chứng nào?
6. Làm thế nào giảm thời gian chờ database integration?
7. PR review và approval wait nên được xử lý ra sao mà vẫn giữ kiểm soát?
8. Những test hoặc quality gate nào tuyệt đối không nên bỏ chỉ để giảm duration?
9. Guardrail nào cần theo dõi nếu tiếp tục tối ưu?
10. Cần liên kết change failure với release và deployment ID thế nào?

Một phương án tốt sẽ giữ lại cải tiến có ích ở p50, điều tra nguyên nhân p95 và retry tăng, cô lập database test, cải thiện reviewer/approval flow và phân tích change failure trước khi tăng deployment frequency. Kết luận cần dựa trên số liệu của cả tốc độ lẫn độ tin cậy.

## Kết luận

Tối ưu thời gian thực thi pipeline chỉ giải quyết một phần của thời gian giao phần mềm. Queue, review, dependency, môi trường, approval và xác minh sau deploy có thể chiếm phần lớn elapsed time. Một pipeline nhanh nhưng flaky, phải retry nhiều hoặc bỏ qua kiểm tra cần thiết sẽ làm delivery kém tin cậy và có thể kéo dài thời gian khôi phục.

Hãy phân rã end-to-end elapsed time, đo riêng waiting và execution, xem critical path cùng percentile, theo dõi first-attempt success và retry. Chọn cải tiến dựa trên bottleneck có bằng chứng, giữ quality gate cần thiết và đặt guardrail cho change failure, SLO, chi phí và trải nghiệm người dùng. Mục tiêu là rút ngắn thời gian chờ không cần thiết trong khi duy trì một luồng phát hành có thể dự đoán và đáng tin cậy.

