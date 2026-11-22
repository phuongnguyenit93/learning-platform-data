# Phân biệt chỉ số của pipeline với kết quả giao phần mềm

## Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt chỉ số đo hiệu quả và độ tin cậy của pipeline với chỉ số đo kết quả giao phần mềm.
- Xác định các tầng đo lường từ CI job, pipeline run, luồng phát hành, dịch vụ production đến khách hàng và mục tiêu kinh doanh.
- Chọn chỉ số phù hợp cho thời gian chờ, thời gian thực thi, tỷ lệ lỗi, tốc độ phát hành, độ ổn định và giá trị người dùng nhận được.
- Hiểu mối liên hệ và giới hạn diễn giải của các chỉ số DORA, flow metrics, SLO và product metrics.
- Thiết kế dashboard có ngữ cảnh, phân đoạn và liên kết được pipeline run với release, deployment và kết quả vận hành.
- Tránh tối ưu một chỉ số cục bộ gây suy giảm chất lượng hoặc kết quả giao phần mềm.
- Thiết lập baseline, mục tiêu cải tiến và vòng phản hồi dựa trên bằng chứng.
- Dùng số liệu để xác định bottleneck và thử nghiệm cải tiến thay vì tạo áp lực báo cáo hoặc xếp hạng cá nhân.

## 1. Vì sao cần phân biệt hai nhóm chỉ số?

CI/CD thường cung cấp rất nhiều số liệu: thời gian build, thời gian chờ runner, tỷ lệ job thành công, thời gian chạy test, số lần deploy và tỷ lệ rollback. Những số liệu này hữu ích để hiểu pipeline hoạt động ra sao, nhưng chúng không tự chứng minh phần mềm được giao có tạo ra giá trị hay không.

Ví dụ:

- Pipeline hoàn tất trong 4 phút nhưng release phải chờ phê duyệt thủ công 5 ngày.
- Tỷ lệ build thành công đạt 99% nhưng sau deploy tỷ lệ lỗi của người dùng tăng.
- Team tăng số lần deploy mỗi ngày nhưng phải rollback thường xuyên.
- Unit test chạy nhanh và pass nhưng lỗi tích hợp chỉ xuất hiện ở production.
- Runner utilization rất cao nhưng thời gian từ lúc yêu cầu được chấp nhận đến khi khách hàng nhận được tính năng không giảm.

Các tình huống này cho thấy cần phân biệt:

**Pipeline metrics** đo hiệu quả, năng lực và độ tin cậy của hệ thống CI/CD: pipeline có khởi chạy đúng không, job chờ bao lâu, build/test mất bao lâu, runner có đủ capacity không, workflow có thường xuyên thất bại không.

**Software delivery outcomes** đo kết quả của toàn bộ quá trình đưa thay đổi đến môi trường sử dụng và tác động của thay đổi đó: thay đổi được đưa đến production nhanh đến đâu, release có gây sự cố không, dịch vụ có đáp ứng SLO không, người dùng có nhận được cải thiện không.

Pipeline là một phần của hệ thống giao phần mềm. Cải thiện pipeline có thể góp phần cải thiện delivery, nhưng hai nhóm chỉ số không thể thay thế cho nhau.

## 2. Bốn tầng đo lường cần phân biệt

Có thể tổ chức hệ thống đo lường thành bốn tầng. Mỗi tầng trả lời một loại câu hỏi và cần được liên kết bằng các định danh chung.

| Tầng | Đối tượng đo | Câu hỏi chính | Ví dụ |
|---|---|---|---|
| 1. Pipeline execution | Job, workflow, runner | CI/CD chạy nhanh và ổn định không? | Queue time, job duration, pipeline success rate |
| 2. Delivery flow | Thay đổi, release, deployment | Thay đổi đi từ yêu cầu đến production thế nào? | Lead time, deployment frequency, throughput, WIP |
| 3. Service/operational outcome | Dịch vụ sau triển khai | Thay đổi có giữ dịch vụ ổn định không? | SLO, error rate, latency, change failure rate |
| 4. Customer/business outcome | Người dùng và mục tiêu sản phẩm | Phần mềm có tạo ra giá trị mong muốn không? | Adoption, task completion, conversion, customer satisfaction |

~~~mermaid
flowchart TD
    A["Pipeline execution metrics"] --> B["Delivery flow metrics"]
    B --> C["Service and operational outcomes"]
    C --> D["Customer and business outcomes"]
    A -. "Năng lực hỗ trợ" .-> C
    B -. "Release impact" .-> C
    C -. "Trải nghiệm thực tế" .-> D
~~~

Các tầng có quan hệ nhưng không phải quan hệ nhân quả tự động. Ví dụ giảm pipeline duration có thể rút ngắn một phần lead time, nhưng nếu thời gian chờ review hoặc approval không đổi thì lead time tổng thể có thể gần như không thay đổi.

Tương tự, tăng deployment frequency không đảm bảo customer outcome tốt hơn nếu các release không giải quyết đúng nhu cầu hoặc làm tăng lỗi.

## 3. Pipeline metrics đo điều gì?

Pipeline metrics giúp platform team và development team hiểu năng lực của hệ thống tự động hóa.

### 3.1. Thời gian chờ (queue time)

Queue time là thời gian từ lúc job sẵn sàng chạy đến lúc được cấp runner và bắt đầu thực thi.

Nó có thể tăng do:

- Thiếu runner hoặc concurrency quota.
- Nhiều pipeline run cùng lúc.
- Runner label không phù hợp.
- Concurrency group đang serialize job.
- Approval hoặc dependency chưa hoàn tất.
- Cloud capacity hoặc rate limit.

Cần phân biệt queue time với thời gian job thực thi. Nếu một job mất 2 phút để chạy nhưng chờ 15 phút để có runner, tối ưu script build sẽ không giải quyết bottleneck chính.

### 3.2. Job duration và pipeline duration

- Job duration đo thời gian thực thi của một job.
- Pipeline duration đo khoảng thời gian từ trigger hoặc start đến khi pipeline đạt trạng thái cuối.
- Critical path duration đo thời gian của chuỗi dependency dài nhất trong DAG.

Pipeline duration cần được định nghĩa nhất quán. Một số hệ thống tính từ lúc event đến khi run được tạo; hệ thống khác chỉ tính từ lúc runner bắt đầu. Khi so sánh, cần ghi rõ điểm bắt đầu và điểm kết thúc.

### 3.3. Tỷ lệ thành công của pipeline

Có thể tính tỷ lệ run thành công trên tổng số run được đánh giá trong một khoảng thời gian:

\[
Success\ Rate =
\frac{Successful\ Runs}{Eligible\ Runs}\times 100\%
\]

Cần quy định cách xử lý:

- Run bị hủy do commit mới thay thế.
- Run bị hủy thủ công.
- Run bị skip theo policy.
- Run thất bại do source/test.
- Run thất bại do runner, registry hoặc dịch vụ ngoài.
- Run retry và nhiều attempt.

Nếu tính mọi trạng thái cancelled như failure, tỷ lệ có thể phản ánh sai chất lượng pipeline. Nếu loại mọi run bị hủy mà không ghi lý do, team có thể che giấu vấn đề bằng cách hủy run lỗi.

### 3.4. Flaky test rate

Flaky test là test có kết quả không ổn định dù source và điều kiện thực thi tương đương. Chỉ số có thể theo dõi:

- Tỷ lệ test fail rồi pass khi retry.
- Số test flaky đã xác nhận.
- Tỷ lệ run bị ảnh hưởng bởi flaky test.
- Thời gian pipeline lãng phí cho retry.
- Số lần quarantine hoặc disable test.

Không nên coi retry pass là test pass bình thường mà bỏ qua lần fail đầu. Lần fail là bằng chứng về độ tin cậy của test suite và cần được phân loại.

### 3.5. Runner và tài nguyên

Các chỉ số thường dùng:

- Runner utilization.
- CPU, memory và disk pressure.
- Queue depth.
- Số job đồng thời.
- Tỷ lệ runner bị mất kết nối.
- Thời gian provisioning runner.
- Cache hit rate.
- Artifact upload/download duration.

Runner utilization cao không tự động là tốt. Nếu luôn gần 100%, các pipeline mới có thể phải chờ lâu và release khẩn cấp thiếu capacity. Nếu utilization thấp nhưng queue time cao, bottleneck có thể nằm ở quota, label hoặc concurrency policy.

## 4. Delivery flow metrics đo điều gì?

Delivery flow metrics quan sát cách một thay đổi đi qua hệ thống từ lúc được chấp nhận đến khi được phát hành.

### 4.1. Lead time for changes

Lead time for changes thường đo khoảng thời gian từ khi thay đổi được commit hoặc tích hợp vào nhánh chính đến khi thay đổi đó được triển khai thành công vào production. Cần định nghĩa điểm bắt đầu nhất quán theo mô hình phát triển của tổ chức.

Lead time có thể bị ảnh hưởng bởi:

- Thời gian review.
- Thời gian chờ CI.
- Thời gian sửa lỗi pipeline.
- Thời gian chờ security hoặc product approval.
- Batch release hoặc change window.
- Thời gian deploy và verify.
- Các bước thủ công hoặc dependency giữa team.

Không nên nhầm lead time với pipeline duration. Pipeline có thể chạy 10 phút, nhưng thay đổi phải chờ review 2 ngày và đợi release window thêm 3 ngày.

Có thể đo thêm thời gian từng chặng để tìm bottleneck:

- Commit to PR review.
- PR open to merge.
- Merge to artifact.
- Artifact to deployment.
- Deployment start to verified release.

### 4.2. Deployment frequency

Deployment frequency đo tần suất triển khai thay đổi lên production trong một khoảng thời gian.

Cần định nghĩa deployment là gì:

- Một lần deploy một service?
- Một lần release một sản phẩm?
- Một lần thay đổi production environment?
- Một lần triển khai thành công sau khi verification đạt?

Nếu mỗi service deploy độc lập, nên đo theo service hoặc nhóm dịch vụ có cùng lifecycle. Không cộng số lần deploy của nhiều service thành một con số mà không giữ ngữ cảnh.

Deployment frequency cao có thể giúp giảm batch size và tăng phản hồi nhanh. Tuy nhiên, nếu deploy nhiều lần nhưng không có người dùng nhận được thay đổi hoặc chất lượng giảm, tần suất cao không phải kết quả cuối cùng.

### 4.3. Throughput và flow efficiency

Throughput là số lượng thay đổi hoàn tất trong một đơn vị thời gian, ví dụ số work item hoặc change được triển khai mỗi tuần.

Flow efficiency có thể xem xét tỷ lệ thời gian công việc thực sự được xử lý so với tổng lead time. Phần còn lại thường là thời gian chờ review, chờ dependency, chờ môi trường hoặc chờ quyết định.

Ví dụ một thay đổi mất 10 ngày từ lúc bắt đầu đến production, nhưng chỉ có 12 giờ thực hiện code/test. Phần lớn lead time nằm ở waiting time. Tăng tốc build thêm 5 phút sẽ không giải quyết vấn đề chính.

### 4.4. Work in progress (WIP)

WIP là số thay đổi đang được xử lý nhưng chưa hoàn tất. WIP quá cao có thể làm:

- Tăng context switching.
- Kéo dài thời gian review.
- Tăng số nhánh cần rebase hoặc merge.
- Tăng nguy cơ conflict.
- Khó xác định thay đổi nào đang chặn release.
- Tăng số thay đổi đồng thời gây rủi ro production.

Giới hạn WIP và chia nhỏ batch thường giúp luồng giao phần mềm dễ dự đoán hơn.

## 5. Các chỉ số DORA và cách diễn giải

DORA nghiên cứu năng lực giao phần mềm và vận hành. Bộ chỉ số thường được nhắc đến gồm:

- Deployment frequency.
- Lead time for changes.
- Change failure rate.
- Failed deployment recovery time (trong nhiều tài liệu trước đây gọi là time to restore service).
- Deployment rework rate được bổ sung trong mô hình DORA gần đây.

Tên gọi và cách định nghĩa có thể thay đổi theo phiên bản báo cáo và mô hình đo lường. Cần ghi rõ phiên bản framework hoặc định nghĩa nội bộ đang dùng.

| Chỉ số | Ý nghĩa | Tầng đo |
|---|---|---|
| Deployment frequency | Tần suất deploy production | Delivery flow |
| Lead time for changes | Thời gian từ thay đổi đến production | Delivery flow |
| Change failure rate | Tỷ lệ deploy dẫn đến cần remediation hoặc gây suy giảm dịch vụ | Service/delivery outcome |
| Failed deployment recovery time | Thời gian khôi phục sau deploy thất bại | Service/operational outcome |
| Deployment rework rate | Tỷ lệ deploy ngoài kế hoạch nhằm sửa hoặc khắc phục vấn đề production | Delivery/service outcome |

Các chỉ số này không phải pipeline metrics thuần túy. Chúng phản ánh kết quả của toàn bộ delivery system, bao gồm con người, quy trình, kiến trúc, kiểm thử, vận hành và nền tảng.

### 5.1. Change failure rate

Một cách tính đơn giản:

\[
CFR =
\frac{Deployments\ causing\ failure}{Total\ production\ deployments}
\times 100\%
\]

Nhưng cần xác định thế nào là failure:

- Incident có ảnh hưởng người dùng.
- Rollback hoặc hotfix.
- SLO burn vượt ngưỡng.
- Degradation cần can thiệp.
- Deployment phải được sửa ngoài kế hoạch.

Nếu mỗi tổ chức định nghĩa khác nhau, không nên so sánh CFR trực tiếp giữa các team.

Cần liên kết incident hoặc remediation với deployment ID để biết thay đổi nào có liên quan. Không phải mọi incident xảy ra sau deploy đều do deploy gây ra; cần quy tắc attribution và review.

### 5.2. Failed deployment recovery time

Chỉ số này đo thời gian từ khi deployment gây thất bại hoặc suy giảm được xác định đến khi dịch vụ được khôi phục về trạng thái chấp nhận được.

Cần xác định mốc kết thúc:

- Traffic được chuyển về phiên bản cũ?
- Error rate trở lại dưới ngưỡng?
- SLO được phục hồi?
- Người dùng có thể hoàn thành luồng nghiệp vụ?
- Data integrity đã được xác minh?

Chỉ rollback command hoàn tất chưa chắc dịch vụ đã phục hồi. Nếu dữ liệu bị sai hoặc queue backlog chưa được xử lý, recovery vẫn chưa hoàn tất.

### 5.3. Deployment rework rate

Deployment rework rate phản ánh phần deploy ngoài kế hoạch được thực hiện để sửa vấn đề production, chẳng hạn hotfix hoặc corrective deployment.

Chỉ số này bổ sung góc nhìn về khối lượng phát hành phải quay lại sửa lỗi. Cần phân biệt rework với deployment theo kế hoạch như feature rollout hoặc scheduled maintenance.

## 6. Service outcomes: phần mềm chạy tốt sau khi deploy không?

Một release thành công về kỹ thuật vẫn có thể làm dịch vụ hoạt động kém. Vì vậy cần đo kết quả ở runtime.

Các chỉ số thường gặp:

- Availability hoặc success rate.
- Error rate theo endpoint và version.
- Latency p50, p95, p99.
- Saturation của CPU, memory, connection pool.
- Queue lag và processing delay.
- Dependency availability.
- Restart/crash rate.
- SLO compliance và error budget consumption.
- Business transaction success rate.

SLI là chỉ số đo một khía cạnh dịch vụ mà người dùng quan tâm. SLO là mục tiêu cho SLI trong một cửa sổ thời gian. Ví dụ SLI có thể là tỷ lệ request API thành công, còn SLO đặt mục tiêu 99,9% trong 30 ngày.

Pipeline metrics cho biết job có chạy xong không. SLI/SLO cho biết dịch vụ có đáp ứng kỳ vọng vận hành sau deploy không.

Không nên dùng CPU utilization làm đại diện duy nhất cho sức khỏe dịch vụ. Một service có CPU thấp nhưng payment failure cao vẫn là một service có vấn đề. Cần kết hợp technical signals và business signals.

## 7. Customer và business outcomes

Tầng cuối cùng hỏi phần mềm có tạo ra kết quả mà người dùng hoặc doanh nghiệp mong muốn không.

Ví dụ:

- Tỷ lệ người dùng hoàn thành checkout.
- Tỷ lệ giao dịch thanh toán thành công.
- Thời gian hoàn thành một tác vụ.
- Tỷ lệ người dùng quay lại.
- Tỷ lệ onboarding thành công.
- Số yêu cầu hỗ trợ liên quan đến tính năng.
- Customer satisfaction hoặc NPS nếu tổ chức sử dụng.
- Tỷ lệ chuyển đổi hoặc doanh thu phù hợp với sản phẩm.

Các chỉ số này chịu ảnh hưởng của nhiều yếu tố ngoài kỹ thuật: nhu cầu thị trường, UX, giá, chiến dịch, mùa vụ và thay đổi hành vi người dùng. Không nên quy mọi biến động cho một release hoặc cho pipeline.

Cần gắn product metric với mục tiêu cụ thể của thay đổi. Ví dụ release tối ưu checkout nên theo dõi completion rate, payment success và latency, thay vì chỉ theo dõi số lần deploy.

## 8. Mối liên hệ giữa pipeline metrics và delivery outcomes

Pipeline metrics thường là chỉ số dẫn dắt (leading indicators) cho một phần năng lực delivery. Delivery và service outcomes thường là kết quả trễ hơn (lagging outcomes), nhưng không phải mọi chỉ số đều có thể phân loại tuyệt đối.

Ví dụ một chuỗi giả thuyết:

1. Giảm queue time giúp job bắt đầu sớm hơn.
2. Giảm pipeline duration giúp developer nhận feedback nhanh hơn.
3. Feedback nhanh có thể giảm thời gian sửa lỗi và chờ merge.
4. Thay đổi nhỏ hơn có thể được phát hành thường xuyên hơn.
5. Batch nhỏ hơn có thể giảm blast radius khi có lỗi.
6. Kết hợp test tốt và observability có thể giảm change failure rate.
7. Dịch vụ ổn định hơn có thể cải thiện trải nghiệm người dùng.

Mỗi mũi tên là một giả thuyết cần kiểm chứng. Nếu review time chiếm phần lớn lead time, giảm build duration không làm lead time thay đổi đáng kể. Nếu test suite thiếu integration coverage, tăng deployment frequency có thể làm change failure rate tăng.

~~~mermaid
flowchart TD
    A["Pipeline queue/duration"] --> B["Feedback speed"]
    B --> C["Delivery lead time and batch size"]
    C --> D["Deployment frequency"]
    D --> E["Change failure and recovery"]
    E --> F["Service reliability / SLO"]
    F --> G["Customer task success"]
    H["Review, policy, architecture, team capacity"] --> C
    I["Test quality and observability"] --> E
    J["Product design and user needs"] --> G
~~~

Đo lường cần giúp kiểm tra chuỗi giả thuyết, không chỉ chứng minh một chỉ số đang tăng hoặc giảm.

## 9. Ví dụ: pipeline nhanh hơn nhưng delivery không nhanh hơn

Một team cải tiến cache dependency và runner. Kết quả:

| Chỉ số | Trước | Sau |
|---|---:|---:|
| Pipeline duration trung vị | 18 phút | 8 phút |
| Queue time trung vị | 6 phút | 1 phút |
| PR review waiting | 2,5 ngày | 2,4 ngày |
| Lead time for changes | 4,2 ngày | 4,0 ngày |
| Deployment frequency | 3 lần/tuần | 3 lần/tuần |

Pipeline đã cải thiện rõ, nhưng lead time và deployment frequency gần như không đổi. Điều đó không có nghĩa tối ưu pipeline vô ích. Nó cho thấy bottleneck lớn hơn nằm ở review hoặc release process.

Bước tiếp theo nên phân tích thời gian chờ review, số vòng sửa PR, reviewer capacity và quy tắc batch release. Tối ưu tiếp runner có thể đem lại lợi ích nhỏ hơn so với cải tiến luồng review.

## 10. Ví dụ: deployment frequency tăng nhưng outcome xấu đi

Một nhóm chuyển từ release hàng tuần sang deploy nhiều lần mỗi ngày. Pipeline duration giảm và deployment frequency tăng. Tuy nhiên:

- Change failure rate tăng.
- Hotfix và rollback nhiều hơn.
- Error budget bị tiêu thụ nhanh.
- Support ticket tăng.
- Tỷ lệ hoàn thành tác vụ của người dùng giảm.

Đây là dấu hiệu team đang tối ưu tốc độ phát hành mà chưa kiểm soát đủ chất lượng hoặc chưa chia nhỏ thay đổi đúng cách.

Cần xem xét:

- Test coverage và độ tin cậy của test.
- Batch size của mỗi release.
- Canary và post-deploy verification.
- Feature flag và khả năng giới hạn blast radius.
- Compatibility của schema và API.
- Alert và khả năng rollback/recovery.
- Mức độ sẵn sàng của người trực vận hành.

Mục tiêu không phải giảm deployment frequency trở lại bằng mọi giá. Cần tìm cách giữ feedback nhanh và tăng độ an toàn của từng thay đổi.

## 11. Thiết kế metric tree cho một mục tiêu cụ thể

Một metric tree nối mục tiêu cấp cao với những chỉ số có thể tác động.

Ví dụ mục tiêu: giảm thời gian đưa thay đổi có giá trị đến người dùng mà vẫn giữ độ tin cậy.

~~~mermaid
flowchart TD
    A["Mục tiêu: giao giá trị nhanh và an toàn"]
    A --> B["Flow"]
    A --> C["Quality and reliability"]
    A --> D["Customer outcome"]
    B --> E["Lead time"]
    B --> F["Deployment frequency"]
    B --> G["WIP / waiting time"]
    C --> H["Change failure rate"]
    C --> I["Recovery time"]
    C --> J["SLO / error budget"]
    D --> K["Task completion"]
    D --> L["User adoption"]
    D --> M["Support contacts"]
~~~

Từ metric tree, team chọn một hoặc hai bottleneck để cải thiện trong một chu kỳ. Không cần đặt mục tiêu cho mọi metric cùng lúc.

Ví dụ nếu lead time cao do review waiting, chỉ số dẫn dắt có thể là thời gian chờ review và số PR đang mở trên mỗi reviewer. Nếu change failure rate cao do migration, cần đo tỷ lệ migration failure, thời gian kiểm tra compatibility và số incident liên quan data change.

## 12. Định nghĩa metric trước khi tạo dashboard

Một metric cần có định nghĩa rõ để các nhóm không diễn giải khác nhau.

Mỗi metric nên ghi:

- Tên và mục đích.
- Đơn vị.
- Công thức.
- Đối tượng và phạm vi.
- Điểm bắt đầu/kết thúc nếu đo thời gian.
- Cửa sổ thời gian.
- Nguồn dữ liệu.
- Quy tắc loại trừ.
- Cách xử lý missing/duplicate data.
- Owner.
- Phân đoạn cần thiết.
- Giới hạn diễn giải.

Ví dụ định nghĩa pipeline duration:

| Thuộc tính | Định nghĩa mẫu |
|---|---|
| Name | Pipeline duration |
| Unit | Minutes |
| Start | Thời điểm workflow run được tạo |
| End | Thời điểm run đạt trạng thái cuối |
| Population | Các CI validation run của repository |
| Exclusions | Run test thủ công ngoài workflow chuẩn, nếu được ghi rõ |
| Aggregation | Median và p90 theo tuần |
| Segments | Repository, branch class, workflow type |
| Owner | Platform engineering |
| Caveat | Không bao gồm thời gian từ commit đến lúc event được nhận nếu hệ thống không cung cấp timestamp |

Cần định nghĩa rõ một pipeline retry là một run mới hay một attempt của cùng run. Nếu không, duration và success rate có thể bị tính hai lần.

## 13. Baseline, percentile và phân đoạn

Số trung bình có thể che giấu các trường hợp chậm bất thường. Nên xem median và percentile khi phân tích thời gian.

- Median (p50) mô tả trải nghiệm điển hình.
- p90/p95 cho biết nhóm run chậm hơn.
- p99 có thể hữu ích với pipeline có volume đủ lớn.
- Mean có thể hỗ trợ tính tổng tài nguyên nhưng nhạy với outlier.

Ví dụ pipeline duration p50 là 8 phút nhưng p95 là 45 phút. Tối ưu trung vị thêm 1 phút có thể ít quan trọng hơn xử lý nhóm run chậm do runner label hoặc integration environment.

Nên phân đoạn theo:

- Repository hoặc service.
- Loại workflow: PR, main, release, nightly.
- Ngôn ngữ/build tool.
- Runner class.
- Kích thước thay đổi hoặc nhóm test.
- Environment.
- Loại deployment strategy.

Không nên xếp hạng team bằng số liệu chưa chuẩn hóa. Một monolith lớn với integration test nhiều không thể so trực tiếp với một thư viện nhỏ chỉ chạy unit test.

## 14. Từ tương quan đến nguyên nhân

Nếu pipeline duration giảm cùng lúc với lead time, chưa chắc pipeline optimization là nguyên nhân duy nhất. Có thể số lượng thay đổi giảm, reviewer được bổ sung hoặc release process thay đổi.

Để đánh giá cải tiến:

1. Nêu giả thuyết cụ thể.
2. Xác định metric chính và metric bảo vệ (guardrail).
3. Ghi baseline trước thay đổi.
4. Triển khai cải tiến trong phạm vi phù hợp.
5. Theo dõi trong khoảng thời gian đủ đại diện.
6. Phân đoạn dữ liệu để giảm ảnh hưởng của khác biệt workload.
7. So sánh với baseline hoặc nhóm đối chứng nếu khả thi.
8. Ghi nhận yếu tố gây nhiễu và giới hạn kết luận.
9. Quyết định giữ, điều chỉnh hoặc hoàn tác cải tiến.

Ví dụ giả thuyết: tăng runner capacity sẽ giảm queue time. Metric chính là queue time p50/p95; guardrail là chi phí runner và utilization. Nếu queue time giảm nhưng chi phí tăng mạnh, cần đánh giá trade-off.

Một thử nghiệm khác: giới hạn WIP có thể giảm lead time. Metric chính là lead time; guardrail là throughput và số công việc bị trì hoãn. Cần xem nhiều chu kỳ để tránh kết luận từ một tuần ít thay đổi.

## 15. Tránh metric gaming và hành vi tối ưu sai

Khi metric trở thành mục tiêu thưởng/phạt, con người có thể tối ưu con số thay vì kết quả.

Ví dụ:

| Metric bị tối ưu sai | Hành vi có thể xuất hiện | Guardrail cần có |
|---|---|---|
| Pipeline duration | Bỏ test chậm hoặc chuyển test ra ngoài thống kê | Test scope, escaped defects, quality gate |
| Build success rate | Retry đến khi pass rồi chỉ báo lần cuối | First-attempt success và flaky test rate |
| Deployment frequency | Tạo nhiều deploy nhỏ không có giá trị | Change outcome, failure rate, user impact |
| Lead time | Chia hoặc đổi trạng thái ticket để rút ngắn số đo | Định nghĩa workflow và audit timestamp |
| Coverage | Viết assertion yếu chỉ để tăng phần trăm | Mutation test, defect escape và review |
| Incident count | Không ghi nhận incident nhỏ | SLO, support signal và blameless reporting |
| Runner utilization | Giữ runner luôn bận dù queue tăng | Queue time, cost và service priority |

Không dùng một metric đơn lẻ để đánh giá năng suất cá nhân. Metrics phù hợp để tìm vấn đề hệ thống và cải thiện luồng làm việc, không phải để suy luận ai làm việc chăm chỉ hay kém hiệu quả.

DORA cũng nhấn mạnh việc đánh giá năng lực ở cấp nhóm/dịch vụ và bối cảnh thay vì dùng số liệu để tạo bảng xếp hạng đơn giản.

## 16. Dashboard theo từng đối tượng sử dụng

Một dashboard tốt trả lời câu hỏi của người xem thay vì hiển thị mọi metric trên một màn hình.

### Platform engineering

Quan tâm:

- Queue time và runner capacity.
- Pipeline/job failure theo nguyên nhân.
- Cache effectiveness.
- Runner provisioning.
- Chi phí CI.
- Workflow version adoption.

### Development team

Quan tâm:

- PR feedback time.
- Build/test duration.
- Flaky test.
- Time to merge.
- Lead time.
- Change failure liên quan service.

### QA

Quan tâm:

- Test suite duration.
- Pass/fail/skipped/error.
- Flaky test rate.
- Defect escape.
- Coverage và test scope.
- Regression trend.

### Security

Quan tâm:

- Finding theo severity và age.
- Thời gian remediation.
- Scan coverage và freshness.
- Exception có expiry.
- Artifact provenance và policy compliance.

### Operations/SRE

Quan tâm:

- Deployment frequency.
- Change failure rate.
- Recovery time.
- SLO/error budget.
- Rollout health.
- Incident và rollback trend.

### Product/business

Quan tâm:

- Feature adoption.
- Task success.
- Customer feedback.
- Conversion hoặc business KPI.
- Tác động sau release.

Các dashboard có thể chia sẻ nguồn dữ liệu, nhưng cần góc nhìn phù hợp. Không nên yêu cầu product owner diễn giải runner CPU hoặc yêu cầu platform team chịu trách nhiệm trực tiếp về conversion rate.

## 17. Liên kết dữ liệu qua release và deployment identity

Để nối pipeline metrics với delivery outcome, cần định danh ổn định:

- Repository ID.
- Commit SHA.
- Pull request/change ID.
- Pipeline run ID và attempt.
- Artifact digest.
- Release ID.
- Deployment ID.
- Environment ID.
- Service/version label.
- Incident ID.
- Trace/correlation ID.

Ví dụ chuỗi dữ liệu:

~~~text
Commit SHA
   |
   v
Pull Request / Change ID
   |
   v
Pipeline Run ID
   |---- Queue time / Job duration
   |---- Test and scan results
   |
   v
Artifact digest
   |
   v
Release ID
   |
   v
Deployment ID + Environment
   |---- Deployment frequency
   |---- Verification result
   |
   v
Service telemetry / Incident
   |---- SLO / Change failure / Recovery
   |
   v
Customer or business metric
~~~

Không có liên kết này, team có thể biết một incident xảy ra nhưng không xác định được release nào liên quan; hoặc biết pipeline nhanh hơn nhưng không biết thay đổi nào thực sự đến production.

Nên gắn release ID/version vào log, metric và trace theo cách có kiểm soát cardinality. Tránh đưa commit SHA đầy đủ hoặc user ID làm label metric có cardinality quá cao; các định danh chi tiết có thể nằm trong trace/log hoặc release record.

## 18. Vòng lặp cải tiến dựa trên số liệu

Đo lường chỉ tạo giá trị khi dẫn đến hành động và kiểm tra kết quả.

Một vòng lặp thực tế:

1. **Observe:** thu thập metric và bằng chứng đáng tin.
2. **Diagnose:** phân tích bottleneck hoặc kết quả không đạt.
3. **Hypothesize:** nêu nguyên nhân có thể và cách cải thiện.
4. **Experiment:** thử thay đổi có phạm vi và guardrail.
5. **Evaluate:** so sánh với baseline và kiểm tra tác động phụ.
6. **Standardize:** giữ lại cải tiến hiệu quả, cập nhật pipeline hoặc policy.
7. **Review:** xem metric có còn phù hợp và có tạo hành vi sai lệch không.

~~~mermaid
flowchart TD
    A["Observe metrics and evidence"] --> B["Diagnose bottleneck"]
    B --> C["Form a testable hypothesis"]
    C --> D["Run a bounded experiment"]
    D --> E["Evaluate outcomes and guardrails"]
    E --> F{"Improvement sustained?"}
    F -- "Có" --> G["Standardize and document"]
    F -- "Không" --> H["Adjust or revert"]
    G --> I["Review metric definitions"]
    H --> I
    I --> A
~~~

Không nên tạo quá nhiều mục tiêu cải tiến cùng lúc. Chọn một bottleneck quan trọng, xác định owner và thời gian đánh giá, sau đó mới chuyển sang vấn đề tiếp theo.

## 19. Ví dụ cải tiến từ số liệu

Một tổ chức nhận thấy:

- Pipeline duration p50: 12 phút.
- Queue time p50: 4 phút.
- Lead time for changes: 3,5 ngày.
- Deployment frequency: 4 lần/tuần.
- Change failure rate: 8%.
- SLO đạt 99,95%.

Phân tích:

1. Queue time chiếm một phần đáng kể pipeline duration; cần kiểm tra runner capacity và concurrency policy.
2. Lead time 3,5 ngày lớn hơn nhiều pipeline duration; cần đo review waiting, approval và release batching.
3. Change failure rate 8% cần phân loại theo loại thay đổi, service và failure mode.
4. SLO đang đạt mục tiêu nhưng cần xem error budget và xu hướng theo release.
5. Deployment frequency không nên tăng trước khi hiểu nguyên nhân change failure.

Có thể chọn hai thử nghiệm riêng:

**Thử nghiệm A — Runner scheduling**

- Giả thuyết: tăng runner pool phù hợp và giới hạn fan-out sẽ giảm queue time.
- Metric chính: queue time p50/p95.
- Guardrail: chi phí runner, utilization và pipeline failure.
- Phạm vi: một nhóm repository đại diện.

**Thử nghiệm B — Giảm change failure**

- Giả thuyết: bổ sung integration test cho luồng có lỗi lặp lại và canary verification sẽ giảm failure.
- Metric chính: change failure rate.
- Guardrail: lead time, deployment frequency và test duration.
- Phạm vi: một service có incident trend rõ.

Sau mỗi thử nghiệm, cần kiểm tra số liệu đủ lớn và có đại diện trước khi áp dụng toàn tổ chức.

## 20. Những anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách cải thiện |
|---|---|---|
| Coi pipeline duration là lead time | Bỏ qua review, approval và release wait | Đo từng chặng của delivery flow |
| Coi pipeline success là release success | Không thấy lỗi runtime hoặc tác động người dùng | Kết hợp deployment verification và SLO |
| Tăng deployment frequency bằng mọi giá | Change failure và rework tăng | Theo dõi cả speed và stability |
| Dùng một số trung bình duy nhất | Che giấu nhóm run chậm | Xem p50/p90/p95 và phân đoạn |
| So sánh các team khác workload | Kết luận thiếu công bằng | Chuẩn hóa scope và bối cảnh |
| Retry rồi bỏ qua first-attempt failure | Flaky test bị che giấu | Đo retry và flaky rate riêng |
| Đặt mục tiêu coverage tuyệt đối | Khuyến khích test yếu | Kết hợp risk-based test và defect escape |
| Đếm mọi deploy như nhau | Không phân biệt service và loại thay đổi | Định nghĩa deployment unit rõ |
| Gán mọi incident sau deploy cho release | Sai attribution | Liên kết deployment và review nguyên nhân |
| Dùng metric để xếp hạng cá nhân | Tạo hành vi gaming và giảm hợp tác | Dùng metrics để cải tiến hệ thống |
| Dashboard không có owner | Số liệu không dẫn đến hành động | Gắn metric với người và quyết định |
| Không có baseline | Không biết cải tiến có hiệu quả | Ghi baseline trước experiment |

## 21. Checklist thiết kế hệ thống đo lường

Trước khi dùng metrics để điều hành CI/CD, hãy xác nhận:

- [ ] Đã phân tầng pipeline execution, delivery flow, service outcome và customer/business outcome.
- [ ] Pipeline duration, queue time và job duration có định nghĩa riêng.
- [ ] Pipeline run, attempt, retry, cancelled và skipped được xử lý nhất quán.
- [ ] Lead time có điểm bắt đầu và kết thúc rõ.
- [ ] Deployment frequency có định nghĩa deployment unit.
- [ ] Change failure và recovery có attribution đến deployment.
- [ ] SLO/SLI phản ánh trải nghiệm dịch vụ quan trọng.
- [ ] Product metric gắn với mục tiêu cụ thể của thay đổi.
- [ ] Có metric chính và guardrail cho mỗi thử nghiệm cải tiến.
- [ ] Baseline và cửa sổ đo được ghi nhận.
- [ ] Dùng median/percentile khi phù hợp.
- [ ] Phân đoạn theo service, workflow, runner và loại thay đổi.
- [ ] Có release/deployment identity để nối pipeline với runtime.
- [ ] Metric có owner và người dùng ra quyết định.
- [ ] Missing data và thay đổi định nghĩa được ghi nhận.
- [ ] Không dùng một metric đơn lẻ để đánh giá cá nhân hoặc team.
- [ ] Có review định kỳ để phát hiện metric gaming.
- [ ] Kết quả cải tiến được đánh giá bằng outcome và guardrail.

## 22. Bài tập tự đánh giá

Một nhóm báo cáo trong tháng vừa qua:

- Pipeline duration giảm từ 20 xuống 9 phút.
- Pipeline success rate tăng từ 92% lên 98%.
- Deployment frequency tăng từ 2 lên 8 lần/tuần.
- Lead time for changes vẫn ở mức 4 ngày.
- Change failure rate tăng từ 4% lên 11%.
- Recovery time trung vị tăng từ 25 lên 50 phút.
- Tỷ lệ hoàn thành checkout của người dùng giảm 3%.
- Runner utilization tăng lên 95%.

Hãy phân tích:

1. Những chỉ số nào đo pipeline execution?
2. Những chỉ số nào phản ánh delivery flow?
3. Những chỉ số nào phản ánh service/customer outcome?
4. Vì sao pipeline tốt hơn nhưng lead time không đổi?
5. Deployment frequency tăng có thể liên quan thế nào đến change failure rate?
6. Recovery time tăng nói lên điều gì về khả năng vận hành?
7. Runner utilization 95% có thể tạo rủi ro gì?
8. Cần liên kết release ID, deployment ID và checkout metric ra sao để phân tích?
9. Nên chọn thử nghiệm cải tiến nào trước và guardrail nào cần theo dõi?
10. Cần thêm dữ liệu nào trước khi kết luận release là nguyên nhân làm checkout giảm?

Một câu trả lời tốt không cố tạo một điểm số tổng hợp duy nhất. Hãy phân loại chỉ số, tìm bottleneck, xác định giả thuyết có thể kiểm chứng và đề xuất một thử nghiệm có phạm vi rõ.

## Kết luận

Chỉ số pipeline cho biết hệ thống CI/CD thực thi công việc nhanh và ổn định đến đâu. Kết quả giao phần mềm cho biết thay đổi có đến production đúng cách, giữ dịch vụ đáng tin cậy và tạo ra giá trị cho người dùng hay không. Hai nhóm liên quan nhưng không thay thế nhau.

Hãy đo từ pipeline execution qua delivery flow đến service và customer outcomes; liên kết chúng bằng commit, artifact digest, release và deployment ID. Định nghĩa metric rõ ràng, xem percentile và bối cảnh, kết hợp chỉ số tốc độ với độ ổn định và kết quả người dùng. Dùng số liệu để tìm bottleneck, thử nghiệm cải tiến và kiểm tra guardrail, thay vì tối ưu một con số riêng lẻ hoặc dùng metrics để xếp hạng con người.

