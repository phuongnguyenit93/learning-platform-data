# Chỉ số sử dụng

## 1. Chỉ số sử dụng trong quản trị vòng đời DSL

Một ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL) thường được phát triển và vận hành qua nhiều giai đoạn: thiết kế, thử nghiệm, phát hành, áp dụng, mở rộng, bảo trì và đôi khi ngừng hỗ trợ. Trong suốt vòng đời đó, nhóm phát triển cần biết ngôn ngữ đang được sử dụng như thế nào, tính năng nào có giá trị, phiên bản nào còn hoạt động, lỗi xuất hiện ở đâu và người dùng gặp trở ngại gì.

**Chỉ số sử dụng (usage metrics)** là các đại lượng được thu thập và tổng hợp để mô tả mức độ áp dụng, cách sử dụng và kết quả sử dụng DSL theo thời gian. Chúng có thể phản ánh số workspace, project, file, compile job, workflow execution, feature adoption, syntax deprecated, error rate hoặc mức độ hoàn tất một quy trình.

Ví dụ, một nhóm phát triển DSL có thể muốn trả lời:

- Có bao nhiêu project đang dùng DSL trong tháng này?
- Bao nhiêu project đã nâng lên language version mới?
- Những feature nào được sử dụng thường xuyên?
- Có bao nhiêu source còn dùng syntax deprecated?
- Parser error hoặc type error tăng sau release nào?
- Runtime execution có ổn định và đáp ứng latency mục tiêu không?
- Người dùng thường dừng ở bước nào trong quá trình tạo hoặc triển khai DSL?
- Một tính năng mới có được áp dụng sau khi phát hành không?

Chỉ số giúp đưa ra quyết định dựa trên bằng chứng. Tuy nhiên, số liệu chỉ có ý nghĩa khi định nghĩa rõ đối tượng đo, đơn vị, thời gian, nguồn dữ liệu và giới hạn diễn giải.

## 2. Mục tiêu của việc đo lường

Không nên thu thập mọi event chỉ vì có thể đo. Mỗi metric cần gắn với một câu hỏi quản trị hoặc quyết định cụ thể.

### 2.1. Đo adoption

Xác định DSL đã được áp dụng tới đâu trong các team, project, tenant hoặc môi trường.

### 2.2. Đo feature usage

Tìm feature được sử dụng nhiều, ít hoặc chưa được khám phá để ưu tiên cải tiến documentation, UX và roadmap.

### 2.3. Đo version adoption

Biết project đang dùng language version, compiler version hoặc runtime version nào để lập kế hoạch deprecation và migration.

### 2.4. Đo quality

Theo dõi compile failure, diagnostic, runtime error, migration failure và các vấn đề làm người dùng không hoàn thành công việc.

### 2.5. Đo reliability và performance

Đánh giá compiler service, language server và runtime về latency, throughput, availability, resource usage và error rate.

### 2.6. Đo lifecycle health

Phát hiện feature cũ không còn được dùng, dependency sắp hết hỗ trợ hoặc syntax deprecated vẫn còn phổ biến.

### 2.7. Hỗ trợ quyết định đầu tư

Kết hợp usage với chi phí bảo trì để quyết định giữ, cải tiến, thay thế hoặc loại bỏ một feature.

### 2.8. Đo lường không phải giám sát cá nhân

Mục tiêu thường là hiểu adoption và sức khỏe của sản phẩm. Không nên biến usage metrics thành công cụ theo dõi năng suất cá nhân hoặc xếp hạng người dùng.

## 3. Phân biệt metric, event, log và trace

Các loại dữ liệu quan sát có vai trò khác nhau.

### 3.1. Event

Event ghi nhận một việc xảy ra tại một thời điểm, ví dụ project_created, compile_completed, feature_used hoặc migration_started. Event thường có timestamp và một số thuộc tính.

### 3.2. Metric

Metric là số liệu được tổng hợp theo thời gian hoặc chiều phân loại, ví dụ số compile mỗi giờ, tỷ lệ compile thành công hoặc p95 latency.

### 3.3. Log

Log ghi chi tiết một sự kiện hoặc lỗi để điều tra. Log có thể chứa message và context, nhưng cần tránh dữ liệu nhạy cảm.

### 3.4. Trace

Trace nối nhiều operation thành một luồng, ví dụ request từ editor đi qua language server, compiler service và artifact store.

### 3.5. Relationship

Event có thể là nguồn để tính metric; log và trace giúp giải thích nguyên nhân khi metric thay đổi. Không nên dùng metric có cardinality cao để thay thế log hoặc trace.

## 4. Các nhóm usage metrics

Một hệ thống quản trị DSL có thể chia chỉ số thành các nhóm.

| Nhóm | Câu hỏi chính | Ví dụ |
|---|---|---|
| Adoption | Ai đang sử dụng? | Active projects, active workspaces |
| Activity | Sử dụng thường xuyên đến đâu? | Compile count, execution count |
| Feature | Dùng khả năng nào? | Feature adoption, syntax frequency |
| Version | Đang dùng phiên bản nào? | Version distribution |
| Quality | Có gặp trở ngại không? | Compile success rate, diagnostics |
| Performance | Hệ thống nhanh và ổn định không? | Latency, throughput, memory |
| Lifecycle | Feature nào cần bảo trì hoặc loại bỏ? | Deprecated usage, migration progress |
| Outcome | Công việc có hoàn thành không? | Workflow completion, task success |

Các nhóm có thể liên hệ với nhau. Ví dụ adoption tăng nhưng compile success giảm có thể cho thấy onboarding hoặc documentation chưa theo kịp lượng người dùng mới.

## 5. Adoption metrics

Adoption đo mức độ DSL được đưa vào sử dụng trong tổ chức hoặc sản phẩm.

### 5.1. Registered projects

Số project đã đăng ký DSL. Đây là chỉ số quy mô tiềm năng, nhưng project được tạo chưa chắc đang hoạt động.

### 5.2. Active projects

Số project có hoạt động được định nghĩa trong một khoảng thời gian, chẳng hạn ít nhất một compile thành công hoặc một workflow execution.

### 5.3. Active workspaces

Số workspace có người mở hoặc chỉnh sửa DSL. Cần định nghĩa rõ activity để không tính một workspace chỉ mở nền là active.

### 5.4. Active users

Có thể đo người dùng hoạt động theo ngày, tuần hoặc tháng nếu việc đo phù hợp chính sách privacy. Nên ưu tiên aggregate theo team hoặc tenant khi không cần định danh cá nhân.

### 5.5. Adoption rate

Tỷ lệ project sử dụng DSL trong tập project đủ điều kiện:

\[
Adoption\ Rate =
\frac{Active\ DSL\ Projects}{Eligible\ Projects}
\times 100\%
\]

Mẫu số cần được định nghĩa. Nếu chỉ tính project đã được cấp quyền dùng DSL, metric khác với tỷ lệ trên toàn tổ chức.

### 5.6. New adoption

Số project bắt đầu dùng DSL lần đầu trong một kỳ. Cần phân biệt project mới tạo và project cũ bắt đầu áp dụng.

### 5.7. Retention

Retention đo tỷ lệ project tiếp tục sử dụng sau một khoảng thời gian kể từ lần đầu áp dụng. Có thể dùng cohort theo tháng bắt đầu.

### 5.8. Churn

Churn đo project ngừng hoạt động hoặc rời khỏi DSL. Cần phân biệt ngừng tạm thời, archive, migration sang giải pháp khác và project đã hoàn tất vòng đời.

## 6. Activity metrics

Activity metrics mô tả cường độ sử dụng theo thời gian.

### 6.1. Compile count

>Số lần compiler được gọi. Nên tách interactive compile, CI compile, batch compile và compile do automation.

### 6.2. Execution count

>Số lần DSL runtime thực thi workflow, rule set hoặc configuration.

### 6.3. Source changes

>Số lần lưu hoặc thay đổi source có thể cho biết mức độ chỉnh sửa, nhưng không phải thước đo trực tiếp của năng suất.

### 6.4. Build frequency

>Tần suất build project dùng DSL. Có thể phản ánh hoạt động phát triển hoặc CI.

### 6.5. Session duration

>Thời gian một phiên editor hoặc language server hoạt động. Cần tránh suy diễn rằng phiên dài luôn có nghĩa người dùng thành công.

### 6.6. Successful workflow count

>Số workflow hoàn tất theo trạng thái nghiệp vụ được định nghĩa, không chỉ số lần runtime được gọi.

### 6.7. Activity distribution

>Phân tích theo giờ, ngày, team, environment hoặc operation có thể giúp lập capacity plan. Không thu dimension chi tiết hơn nhu cầu.

## 7. Feature usage metrics

Feature usage cho biết người dùng sử dụng khả năng cụ thể nào của DSL.

### 7.1. Feature adoption

>Tỷ lệ project đang sử dụng một feature trong nhóm project có thể sử dụng feature đó.

### 7.2. Feature invocation

>Số lần một operation hoặc construct được thực thi. Cần phân biệt source declaration với runtime invocation.

### 7.3. Syntax frequency

>Có thể đo số lần xuất hiện của một syntax construct trong source, chẳng hạn retry block, pattern match hoặc typed duration. Thường nên aggregate theo project và version thay vì lưu raw source.

### 7.4. Feature depth

>Một feature có thể được dùng ở mức cơ bản hoặc nâng cao. Có thể đo các capability cụ thể, nhưng định nghĩa phải rõ và không tạo quá nhiều metric.

### 7.5. Feature discovery

>Đo số người mở documentation, completion hoặc sample liên quan có thể giúp hiểu khả năng được khám phá. Lượt xem tài liệu không chứng minh feature đã được áp dụng.

### 7.6. Feature outcome

>Đo kết quả sau khi sử dụng feature, ví dụ tỷ lệ workflow thành công khi dùng retry policy. Cần tránh kết luận nhân quả nếu nhóm dùng feature có workload khác nhóm không dùng.

### 7.7. Low-usage feature

>Feature ít dùng có thể không cần thiết, khó tìm, khó hiểu, chỉ dành cho use case hiếm hoặc mới phát hành. Cần kết hợp dữ liệu và phản hồi trước khi loại bỏ.

## 8. Version adoption và migration metrics

Trong quản trị vòng đời, biết source đang dùng version nào là điều kiện để nâng cấp an toàn.

### 8.1. Version distribution

>Tỷ lệ project theo language version, compiler version và runtime version. Không nên gộp ba loại version thành một metric.

### 8.2. Upgrade rate

>Tỷ lệ project chuyển từ version cũ sang version mới trong một khoảng thời gian.

### 8.3. Time to upgrade

>Thời gian từ khi version mới được phát hành đến khi project nâng cấp.

### 8.4. Deprecated syntax usage

>Số project hoặc source unit còn dùng construct đã deprecated. Nên đo theo construct ID và language version.

### 8.5. Migration completion

>Tỷ lệ project đã hoàn thành migration trên tổng số project cần migration.

### 8.6. Migration failure rate

>Tỷ lệ migration job thất bại hoặc cần manual intervention. Phân loại theo rule, source construct và version để tìm nguyên nhân.

### 8.7. Compatibility mode usage

>Số project vẫn bật compatibility flag. Metric này giúp biết liệu có thể gỡ flag hay cần kéo dài support window.

### 8.8. Unsupported version

>Số compile hoặc runtime request dùng version đã hết hỗ trợ. Cần phân biệt lỗi do source và request từ tool cũ.

## 9. Quality metrics

Quality metrics phản ánh trải nghiệm và độ tin cậy của source DSL.

### 9.1. Compile success rate

\[
Compile\ Success\ Rate =
\frac{Successful\ Compiles}{All\ Eligible\ Compile\ Attempts}
\times 100\%
\]

Cần quy định có tính compile bị cancel, timeout hoặc syntax error vào mẫu số hay không.

### 9.2. Diagnostic rate

>Số diagnostic trên mỗi compile hoặc trên mỗi source unit. Cần tách warning, error và informational message.

### 9.3. First-pass success

>Tỷ lệ source compile thành công ngay lần đầu trong một workflow authoring hoặc onboarding. Cần định nghĩa cửa sổ và session boundary.

### 9.4. Runtime success rate

>Tỷ lệ execution hoàn tất thành công trên tổng execution đủ điều kiện.

### 9.5. Error category distribution

>Phân loại syntax, type, semantic, dependency, permission, timeout và runtime error để tìm điểm gây cản trở.

### 9.6. Recovery rate

>Tỷ lệ lỗi được khắc phục trong cùng session hoặc trong khoảng thời gian quy định. Đây là chỉ số trải nghiệm, không phải bằng chứng duy nhất về chất lượng compiler.

### 9.7. Regression rate

>Số lỗi mới được phát hiện sau một release hoặc tỷ lệ source trước đó thành công nhưng thất bại sau nâng cấp.

### 9.8. Support burden

>Số ticket, incident hoặc yêu cầu hỗ trợ liên quan đến DSL. Nên chuẩn hóa theo số project hoặc active user để tránh so sánh sai khi adoption tăng.

## 10. Performance và reliability metrics

Usage metrics nên đi cùng số liệu vận hành vì hoạt động tăng có thể làm hệ thống chịu tải khác.

### 10.1. Compile latency

>Đo thời gian compile theo percentile như p50, p90 và p95. Trung bình có thể che giấu tail latency.

### 10.2. Runtime latency

>Đo thời gian thực thi DSL theo workflow type hoặc operation class. Không dùng customer ID làm metric label.

### 10.3. Throughput

>Số compile hoặc execution hoàn tất trong một đơn vị thời gian.

### 10.4. Queue time

>Thời gian job chờ trước khi được xử lý. Queue time tăng có thể cho thấy capacity hoặc scheduling bottleneck.

### 10.5. Memory usage

>Theo dõi heap, RSS, allocation rate, peak memory và số job đồng thời. Phân loại theo workload size nếu cần.

### 10.6. CPU utilization

>CPU theo compiler phase hoặc runtime worker giúp nhận ra workload nặng, nhưng cần gắn với throughput để diễn giải.

### 10.7. Availability

>Tỷ lệ thời gian service compiler hoặc runtime có thể phục vụ request theo SLI đã định nghĩa.

### 10.8. Saturation

>Quan sát thread pool, queue, connection pool, memory headroom và rate limit để nhận ra service sắp quá tải.

## 11. Outcome metrics

Activity cao không tự động chứng minh DSL tạo ra giá trị. Cần đo kết quả công việc.

### 11.1. Workflow completion

>Tỷ lệ workflow đạt terminal state mong muốn.

### 11.2. Time to completion

>Thời gian từ lúc bắt đầu đến lúc hoàn thành một tác vụ nghiệp vụ. Cần tách thời gian chờ external dependency và thời gian xử lý DSL.

### 11.3. Automation coverage

>Tỷ lệ quy trình đủ điều kiện đã được mô hình hóa hoặc tự động hóa bằng DSL.

### 11.4. Manual intervention

>Số lần workflow cần con người can thiệp hoặc tỷ lệ execution chuyển sang manual review.

### 11.5. Rework rate

>Tỷ lệ quy trình phải chạy lại do cấu hình hoặc rule sai. Cần định nghĩa rõ nguyên nhân và loại trừ retry tự động hợp lệ.

### 11.6. Business outcome

>Tùy miền, có thể đo thời gian xử lý giảm, lỗi nghiệp vụ giảm hoặc độ nhất quán tăng. Chỉ sử dụng metric có định nghĩa và nguồn dữ liệu đáng tin cậy.

### 11.7. Attribution

>Nếu nhiều thay đổi cùng tác động outcome, không nên quy toàn bộ cải thiện cho DSL. Có thể dùng cohort, baseline hoặc controlled rollout để phân tích thận trọng.

## 12. Metric definition và data contract

Metric cần được định nghĩa thống nhất trước khi instrument.

### 12.1. Name

>Tên metric nên ngắn, có ý nghĩa và theo convention chung. Tránh nhiều metric tên khác nhau nhưng cùng đo một khái niệm.

### 12.2. Unit

>Ghi rõ count, bytes, milliseconds, ratio hoặc percentage. Không trộn đơn vị trong cùng một chuỗi dữ liệu.

### 12.3. Event boundary

>Xác định chính xác thời điểm bắt đầu và kết thúc. Ví dụ compile duration có bao gồm queue time không?

### 12.4. Denominator

>Với rate, xác định tập request đủ điều kiện. Loại bỏ cancelled hoặc invalid event phải được ghi trong định nghĩa.

### 12.5. Dimensions

>Dimension thường gồm service, operation, environment, language version, compiler version, outcome và error category.

### 12.6. Cardinality

>Giới hạn số giá trị dimension. User ID, project ID, file path hoặc request ID thường có cardinality cao và phù hợp hơn với log/trace có kiểm soát.

### 12.7. Ownership

>Mỗi metric quan trọng nên có owner, mục đích, nguồn, retention và dashboard hoặc alert sử dụng nó.

### 12.8. Schema version

>Event schema cũng cần versioning. Consumer phải xử lý field mới hoặc thay đổi tương thích theo contract.

## 13. Instrumentation và telemetry

Instrumentation là việc thêm khả năng phát event hoặc metric vào compiler, runtime và tooling.

### 13.1. Instrumentation points

>Các điểm thường hữu ích:

- Project hoặc workspace được mở.
- Source được parse hoặc compile.
- Compile thành công hoặc thất bại.
- Feature hoặc operation được sử dụng.
- Workflow bắt đầu, hoàn tất hoặc lỗi.
- Migration bắt đầu, hoàn tất hoặc cần can thiệp.
- Runtime hoặc compiler service gặp timeout.

### 13.2. Event schema

>Một event có thể chứa event name, timestamp, schema version, environment, language version, operation và outcome. Không cần gửi toàn bộ source.

### 13.3. Local và remote telemetry

>Telemetry có thể được tổng hợp tại máy rồi gửi aggregate, hoặc gửi event đã giảm dữ liệu. Lựa chọn phụ thuộc privacy, độ chính xác và yêu cầu vận hành.

### 13.4. Sampling

>Sampling giảm volume bằng cách chỉ giữ một phần event. Với error hoặc rare event, có thể áp dụng sampling riêng để không bỏ mất tín hiệu quan trọng.

### 13.5. Buffering

>Client có thể buffer event khi offline và gửi sau. Buffer cần giới hạn, retry policy và xử lý duplicate.

### 13.6. Delivery semantics

>Telemetry có thể được gửi at-least-once nên event có thể trùng. Dùng event ID hoặc aggregation window để deduplicate khi cần.

### 13.7. Instrumentation overhead

>Đo chi phí CPU, memory và latency do telemetry tạo ra. Instrumentation không nên làm thay đổi semantics hoặc gây chậm đáng kể cho compile path.

## 14. Privacy, security và data minimization

Usage metrics có thể phản ánh hành vi làm việc hoặc chứa metadata nhạy cảm. Cần xác định rõ dữ liệu nào được thu thập và vì sao.

### 14.1. Data minimization

>Chỉ thu thập field cần cho câu hỏi đo lường. Thường không cần gửi raw DSL source, literal value hoặc request payload.

### 14.2. Pseudonymous identifiers

>Nếu cần theo dõi cohort, dùng identifier giả danh hoặc aggregate theo tenant/team thay vì định danh cá nhân trực tiếp.

### 14.3. Sensitive content

>Không đưa secret, token, personal data, source literal hoặc payload nghiệp vụ vào metric label.

### 14.4. Access control

>Dashboard và raw event store cần quyền truy cập theo vai trò. Dữ liệu aggregate cũng có thể nhạy cảm khi tenant hoặc nhóm quá nhỏ.

### 14.5. Retention

>Đặt thời hạn lưu raw event, aggregate và trace. Raw data thường cần retention ngắn hơn số liệu tổng hợp.

### 14.6. Opt-in và policy

>Telemetry trong developer tool cần tuân chính sách tổ chức, consent hoặc opt-in khi phù hợp. Người dùng cần biết loại dữ liệu và mục đích sử dụng.

### 14.7. Regional processing

>Nếu event được gửi tới hệ thống analytics, xác định vùng lưu trữ và xử lý dữ liệu theo yêu cầu tổ chức.

## 15. Aggregation và cohort analysis

Aggregation biến event chi tiết thành chỉ số có thể dùng để quản trị.

### 15.1. Time window

>Chọn cửa sổ phút, giờ, ngày, tuần hoặc tháng tùy câu hỏi. Alert vận hành cần window ngắn; adoption trend thường cần window dài hơn.

### 15.2. Cohort

>Nhóm project theo thời điểm bắt đầu dùng DSL, version đầu tiên hoặc thời điểm migration. Cohort giúp so sánh retention và upgrade behavior.

### 15.3. Rolling window

>Rolling 7-day hoặc 30-day active giúp giảm ảnh hưởng của lịch làm việc và ngày nghỉ.

### 15.4. Distinct count

>Đếm project hoặc workspace duy nhất cần định nghĩa identity và xử lý rename, fork hoặc archive.

### 15.5. Percentile

>Latency nên được tổng hợp bằng percentile thay vì chỉ mean. Cần đủ sample size để percentile có ý nghĩa.

### 15.6. Normalize

>So sánh error count giữa project có quy mô rất khác nhau có thể gây hiểu nhầm. Có thể dùng error rate trên compile hoặc execution.

### 15.7. Small cohort

>Nhóm có ít project dễ bị nhận diện hoặc dao động mạnh. Có thể gộp nhóm hoặc ẩn số liệu dưới ngưỡng phù hợp.

## 16. Dashboard cho quản trị DSL

Dashboard nên trả lời một nhóm câu hỏi cụ thể, không gom mọi metric vào một màn hình.

### 16.1. Adoption dashboard

>Hiển thị active projects, adoption rate, new projects, retention và churn theo thời gian.

### 16.2. Feature dashboard

>Hiển thị feature adoption, frequency, version và mức sử dụng syntax deprecated.

### 16.3. Version dashboard

>Hiển thị distribution, upgrade progress, migration failure và số project còn ở version hết hỗ trợ.

### 16.4. Quality dashboard

>Hiển thị compile success, diagnostic rate, runtime success và nhóm lỗi phổ biến.

### 16.5. Reliability dashboard

>Hiển thị latency percentile, throughput, availability, memory, queue và saturation.

### 16.6. Outcome dashboard

>Hiển thị workflow completion, time to completion, manual intervention và rework.

### 16.7. Context

>Mỗi chart cần có timeframe, unit, denominator, filter và link tới định nghĩa metric. Không hiển thị percentage mà không nói mẫu số là gì.

## 17. SLI, SLO và alerting

Usage metrics có thể hỗ trợ vận hành bằng Service Level Indicator (SLI) và Service Level Objective (SLO).

### 17.1. SLI

>SLI là chỉ số đo một khía cạnh dịch vụ, ví dụ tỷ lệ compile request thành công hoặc p95 compile latency.

### 17.2. SLO

>SLO là mục tiêu nội bộ cho SLI trong một khoảng thời gian. Ví dụ 99.5% compile request đủ điều kiện hoàn tất trong thời hạn đã định.

### 17.3. Error budget

>Error budget là phần lỗi được phép theo SLO. Khi budget tiêu nhanh, nhóm có thể ưu tiên reliability trước khi phát hành feature mới.

### 17.4. Alert threshold

>Alert nên dựa trên ảnh hưởng và xu hướng, không chỉ một spike ngắn. Kết hợp absolute threshold, rate và duration.

### 17.5. Adoption alert

>Có thể cảnh báo khi usage deprecated không giảm trước sunset date hoặc migration progress chậm hơn kế hoạch.

### 17.6. Alert fatigue

>Quá nhiều alert không hành động được làm giảm hiệu quả. Mỗi alert cần owner, runbook và điều kiện clear.

## 18. Ví dụ instrumentation bằng Java

Ví dụ sau minh họa cách ghi nhận compile duration và outcome bằng một interface metrics nhỏ. Đây là mô hình khái niệm, không phụ thuộc một thư viện telemetry cụ thể.

### 18.1. Metric interface

~~~java
import java.time.Duration;

public interface DslMetrics {
    void compileCompleted(
            String languageVersion,
            String outcome,
            Duration duration
    );
}
~~~

### 18.2. Instrument compiler boundary

~~~java
import java.time.Duration;

public final class InstrumentedCompiler {
    private final Compiler compiler;
    private final DslMetrics metrics;

    public InstrumentedCompiler(Compiler compiler, DslMetrics metrics) {
        this.compiler = compiler;
        this.metrics = metrics;
    }

    public CompilationResult compile(SourceFile source) {
        long started = System.nanoTime();
        String outcome = "success";
        try {
            return compiler.compile(source);
        } catch (RuntimeException error) {
            outcome = "failure";
            throw error;
        } finally {
            Duration elapsed =
                Duration.ofNanos(System.nanoTime() - started);
            metrics.compileCompleted(
                source.languageVersion(),
                outcome,
                elapsed
            );
        }
    }
}
~~~

Trong implementation thực tế, cần phân biệt syntax error, cancellation, timeout và internal failure. Không đưa source text hoặc exception message có thể chứa dữ liệu nhạy cảm vào metric label.

### 18.3. Counter và histogram

Một backend metrics có thể dùng counter cho compile count và histogram cho duration. Counter tăng theo event; histogram hỗ trợ phân tích phân bố latency.

### 18.4. Low-cardinality labels

Label phù hợp có thể là language version, compiler version, operation class và outcome. Project ID, file path hoặc user ID không nên dùng làm label metric mặc định.

### 18.5. Event aggregation

Nếu client offline, event có thể được buffer và gửi theo batch. Cần có giới hạn kích thước, retry và deduplication.

## 19. Ví dụ định nghĩa event cho DSL usage

Một event compile có thể được biểu diễn như sau:

~~~json
{
  "event": "dsl.compile.completed",
  "schemaVersion": 1,
  "timestamp": "2026-01-15T10:20:30Z",
  "languageVersion": "2",
  "compilerVersion": "4.1",
  "environment": "ci",
  "outcome": "success",
  "durationMs": 184
}
~~~

Đây là payload minh họa. Event production cần tuân schema registry hoặc data contract của hệ thống analytics.

### 19.1. Không gửi source

>Event không cần chứa toàn bộ DSL file. Nếu cần biết feature nào được dùng, có thể gửi feature ID đã được allowlist và aggregate.

### 19.2. Schema evolution

>Thêm field optional thường dễ tương thích hơn đổi type hoặc xóa field. Consumer cần xử lý event version theo contract.

### 19.3. Deduplication

>Thêm event ID hoặc idempotency key nếu transport có thể gửi lặp.

### 19.4. Timestamp semantics

>Phân biệt event time, processing time và ingestion time để tránh phân tích sai khi client offline rồi gửi event muộn.

## 20. Data quality và metric governance

Metric sai hoặc thiếu nhất quán có thể dẫn đến quyết định sai.

### 20.1. Missing events

>Client có thể tắt telemetry, offline hoặc bị crash trước khi gửi. Không diễn giải event count thấp là usage thấp nếu collection coverage chưa rõ.

### 20.2. Duplicate events

>Retry hoặc replay có thể tạo event trùng. Deduplicate theo event ID hoặc quy tắc aggregation.

### 20.3. Clock skew

>Đồng hồ client không đồng bộ có thể làm event order sai. Ghi cả event timestamp và ingestion timestamp.

### 20.4. Version drift

>Producer và consumer có thể dùng schema version khác nhau. Theo dõi unknown field, parse failure và compatibility.

### 20.5. Metric ownership

>Mỗi metric cần owner, định nghĩa, nguồn dữ liệu, unit, retention và mục đích.

### 20.6. Change review

>Thay đổi công thức hoặc denominator có thể làm trend đứt đoạn. Ghi metric definition version và chú thích trên dashboard.

### 20.7. Data lineage

>Biết metric được tính từ event nào, pipeline nào và transformation nào giúp audit và sửa sai.

## 21. Những sai lầm thường gặp

### 21.1. Đếm mọi request thành active usage

>Health check, retry và automation có thể làm activity tăng giả. Định nghĩa active event theo mục đích.

### 21.2. Dùng user count làm thước đo duy nhất

>Một user có thể sở hữu nhiều project; một project có nhiều contributor. Chọn unit phù hợp với câu hỏi.

### 21.3. Không định nghĩa denominator

>Hai dashboard có thể báo adoption rate khác nhau vì dùng tập project đủ điều kiện khác nhau.

### 21.4. Thu raw source để đo feature

>Raw source có thể chứa bí mật hoặc dữ liệu nghiệp vụ. Ưu tiên feature ID và aggregate.

### 21.5. Metric label có cardinality cao

>File path hoặc identifier tạo quá nhiều time series, tăng chi phí và làm dashboard chậm.

### 21.6. Coi correlation là causation

>Feature adoption và outcome tốt có thể cùng tăng do nhóm người dùng hoặc workload khác nhau. Cần phân tích thận trọng.

### 21.7. Chỉ đo adoption, không đo quality

>Usage tăng trong khi compile failure hoặc runtime error cũng tăng có thể là dấu hiệu rollout có vấn đề.

### 21.8. Không phân biệt source version và compiler version

>Không thể lập kế hoạch migration chính xác nếu hai loại version bị gộp.

### 21.9. Không tính telemetry overhead

>Instrumentation có thể làm chậm compile hoặc tăng memory. Đo chi phí và có sampling/buffering hợp lý.

### 21.10. Dashboard không có owner

>Metric không gắn với quyết định hoặc người chịu trách nhiệm thường trở thành số liệu không được sử dụng.

## 22. Quy trình xây dựng hệ thống usage metrics

1. **Xác định quyết định cần hỗ trợ.** Ví dụ ưu tiên feature, lên kế hoạch migration hoặc phát hiện reliability regression.
2. **Chọn đơn vị đo.** Project, workspace, compile, execution, feature hoặc workflow.
3. **Định nghĩa metric.** Nêu công thức, unit, denominator, timeframe và dimension.
4. **Thiết kế event contract.** Chọn event name, schema version, timestamp và field tối thiểu.
5. **Chọn instrumentation point.** Compiler, language server, runtime, migration tool hoặc platform.
6. **Áp dụng privacy.** Data minimization, pseudonymization, access control và retention.
7. **Thiết kế pipeline.** Buffer, transport, deduplication, aggregation và schema validation.
8. **Tạo dashboard.** Chia theo adoption, feature, version, quality, reliability và outcome.
9. **Đặt SLI/SLO khi phù hợp.** Xác định mục tiêu dịch vụ và alert có hành động.
10. **Kiểm tra data quality.** Theo dõi missing event, duplicate, clock skew và schema drift.
11. **Đánh giá overhead.** Đo CPU, memory, latency và network do telemetry tạo ra.
12. **Gán ownership.** Mỗi metric và alert có owner, runbook và lịch review.
13. **Diễn giải thận trọng.** Ghi rõ giới hạn, bias và những gì metric không thể kết luận.
14. **Điều chỉnh theo lifecycle.** Cập nhật metric khi DSL thêm feature, đổi version hoặc chuyển sang giai đoạn maintenance.

## 23. Câu hỏi tự kiểm tra

1. Chỉ số sử dụng có vai trò gì trong quản trị vòng đời DSL?
2. Phân biệt event, metric, log và trace.
3. Adoption rate cần định nghĩa numerator và denominator như thế nào?
4. Active project, retention và churn có thể được đo ra sao?
5. Feature adoption khác feature invocation và feature outcome như thế nào?
6. Version distribution và migration completion hỗ trợ quyết định deprecation ra sao?
7. Compile success rate cần xác định các loại attempt đủ điều kiện thế nào?
8. Performance metrics nào nên được theo dõi cho compiler và runtime?
9. Vì sao cần đo outcome bên cạnh activity?
10. Một metric definition nên có name, unit, event boundary và dimensions nào?
11. Instrumentation points nào phù hợp cho editor, compiler và runtime?
12. Sampling, buffering và deduplication giải quyết vấn đề gì?
13. Làm thế nào giảm privacy risk khi thu thập feature usage?
14. Cohort analysis giúp hiểu adoption và retention như thế nào?
15. Dashboard nên tách các nhóm metric nào?
16. SLI, SLO và error budget liên hệ ra sao với DSL service?
17. Vì sao metric labels có cardinality cao gây vấn đề?
18. Làm thế nào phát hiện schema drift hoặc telemetry bị thiếu?
19. Hãy thiết kế event schema cho một migration job, gồm trạng thái bắt đầu, hoàn tất và cần can thiệp.
20. Hãy đề xuất bộ metrics để quyết định khi nào có thể loại bỏ một syntax đã deprecated.
