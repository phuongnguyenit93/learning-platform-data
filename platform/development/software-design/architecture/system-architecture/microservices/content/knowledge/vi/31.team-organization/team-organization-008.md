# Đo tải nhận thức và tránh phân rã vượt năng lực tổ chức trong Microservices

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Tổ chức nhóm.
>
> **Thông điệp:** Kiến trúc microservices không chỉ chia mã nguồn thành những tiến trình nhỏ. Nó phân phối **kiến thức, quyền quyết định, giao tiếp, triển khai, bảo mật, vận hành và trách nhiệm** sang nhiều ranh giới. Nếu số lượng ranh giới vượt khả năng hiểu và quản lý của đội ngũ, doanh nghiệp có thể có nhiều service “độc lập” về mặt kỹ thuật nhưng lại trở nên phụ thuộc, khó thay đổi và dễ xảy ra sự cố hơn. **Tải nhận thức (cognitive load)** là một góc nhìn để đánh giá giới hạn đó, kết hợp với bằng chứng kỹ thuật và thực tế vận hành.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích **cognitive load**, phân biệt tải do độ phức tạp nghiệp vụ với tải có thể giảm bằng tổ chức công việc, công cụ và thiết kế kiến trúc.
2. Nhận diện chi phí cố định của mỗi microservice: repository, pipeline, runtime, cấu hình, API/event contract, dữ liệu, IAM, observability, on-call và incident handling.
3. Đánh giá xem một nhóm có đủ **năng lực sở hữu trọn vòng đời** service hay đang lệ thuộc quá nhiều vào những nhóm khác.
4. Phân tích cách số lượng service, số lượng công nghệ, thay đổi giao diện và số điểm handoff tạo thêm công việc phối hợp.
5. Thiết kế thước đo kết hợp phỏng vấn, khảo sát ngắn, telemetry kỹ thuật, dữ liệu triển khai và vận hành mà không biến “tải nhận thức” thành một chỉ tiêu cứng áp đặt lên cá nhân.
6. Áp dụng các ý tưởng từ **Team Topologies**: stream-aligned team, platform team, enabling team, complicated-subsystem team và ba cách tương tác thường gặp.
7. Chọn ranh giới microservice theo **bounded context, data ownership, nhịp thay đổi, mức tự chủ và khả năng vận hành** thay vì chia theo tên class hoặc số dòng code.
8. Xác định khi nào **modular monolith**, module trong cùng repository hoặc một service lớn hơn là lựa chọn hợp lý.
9. Xây dựng tiêu chí “đã sẵn sàng tách” và quy trình ADR trước khi thêm deployment boundary mới.
10. Lập kế hoạch giảm độ phức tạp: hợp nhất service, chuẩn hóa nền tảng, giảm synchronous dependencies, làm rõ ownership, loại bỏ công việc thủ công và cải thiện on-call.
11. Đánh giá tác động của thay đổi tổ chức tới lead time, incidents, chất lượng trải nghiệm người dùng và chi phí hạ tầng.

Các con số trong bài là **ví dụ minh họa để thảo luận**, không phải định mức bắt buộc về “số service tối đa trên mỗi kỹ sư”. Ngưỡng phù hợp phụ thuộc sản phẩm, quy mô, năng lực nền tảng, yêu cầu tuân thủ, mức tự động hóa, mức rủi ro và kỹ năng đội ngũ.

## 2. Tình huống mở đầu: nhiều service hơn nhưng giao hàng chậm hơn

Một công ty có 12 kỹ sư backend. Khi ban đầu, hệ thống có ba deployables: Web API, Background Worker và Analytics Pipeline. Đội muốn triển khai nhanh hơn nên chia Web API thành 25 microservices.

Sau sáu tháng:

- Một tính năng checkout nhỏ cần sửa ở 6 repositories và phối hợp 4 nhóm.
- Mỗi service có pipeline, config, secrets, health checks, dashboards và quyền cloud riêng.
- Một nhóm hai kỹ sư phải trực on-call cho 8 service, kể cả service họ hiếm khi đụng tới.
- Một lỗi đổi enum ở một event làm 4 consumers đọc sai dữ liệu.
- Họp điều phối release tăng; người mới mất nhiều tuần để nắm luồng đặt hàng.
- Số lần deploy riêng lẻ tăng nhưng **thời gian đưa một tính năng có giá trị đến khách hàng** lại tăng.
- Database và IAM vẫn dùng chung, nên phần lớn service không thể thay đổi độc lập thực sự.

Từ góc nhìn sơ đồ, kiến trúc có thể trông “rất microservices”. Từ góc nhìn tổ chức, nó đang có dấu hiệu **over-fragmentation**: nhiều ranh giới deploy/ownership nhưng không đủ khả năng tự chủ, chất lượng contract và năng lực vận hành.

**Câu hỏi quan trọng không phải “bao nhiêu service là quá nhiều?” mà là:**

> Có thể giải thích, thay đổi, thử nghiệm, triển khai, quan sát và khôi phục từng ranh giới trong thời gian hợp lý, với đội ngũ hiện có, mà không thường xuyên cần người ngoài đến cứu hay không?

## 3. Tải nhận thức là gì?

**Tải nhận thức** là mức năng lực tư duy và chú ý mà một cá nhân hoặc nhóm phải sử dụng để hiểu, ra quyết định và thực hiện công việc. Trong phát triển hệ thống, nó không chỉ là số dòng code cần đọc, mà còn là số lượng khái niệm, ranh giới, quy tắc và ngoại lệ phải giữ trong đầu.

Một khung diễn giải hữu ích gồm:

### 3.1. Tải nội tại (intrinsic load)

Độ phức tạp vốn có của bài toán:

- Quy tắc định giá, tax, refund.
- Phân quyền đa tenant.
- Invariants của đơn hàng và thanh toán.
- Consistency giữa tồn kho, đơn và giao dịch.
- Quy định bảo mật hoặc phục hồi dữ liệu.

Không thể xóa sạch tải nội tại mà không thay đổi phạm vi nghiệp vụ. Có thể **phân ranh giới và mô hình hóa** để từng nhóm chỉ cần hiểu một phần có ý nghĩa.

### 3.2. Tải ngoại lai (extraneous load)

Độ phức tạp do cách tổ chức công việc hoặc triển khai tạo ra:

- Hơn mười kiểu pipeline khác nhau.
- Triển khai phải copy thủ công cấu hình giữa nhiều môi trường.
- Không có dashboard chung hoặc chuẩn trace/log.
- Muốn đổi một field phải nhắn nhiều nhóm để đồng bộ release.
- Mỗi service có ngôn ngữ, framework hoặc cloud SDK riêng mà không có lý do rõ.
- Runbook thiếu, người mới phải hỏi trực tiếp một cá nhân mới biết cách xử lý.

Đây là phần có thể **giảm mạnh** bằng golden path, platform tooling, automation, documentation và thiết kế lại ranh giới.

### 3.3. Tải dành cho việc học, xây mô hình (germane load)

Năng lực dành để hiểu nghiệp vụ, xây mental model và học kỹ năng thực sự giúp giải quyết vấn đề.

Ví dụ: học về event ordering và state machine cho đơn hàng có giá trị. Nhưng nếu kỹ sư đã mất hết thời gian xử lý token của 15 CI jobs, họ không còn nhiều khả năng tập trung cho mô hình nghiệp vụ.

Khung ba loại tải mang tính hỗ trợ suy nghĩ; **không phải phép đo y khoa hoặc công thức đã được xác định chính xác cho một nhóm phần mềm**. Khi sử dụng trong tổ chức, ưu tiên các biểu hiện và kinh nghiệm thực tế thay vì gán điểm tâm lý cá nhân.

## 4. Vì sao microservices có chi phí cố định theo mỗi ranh giới?

Một microservice mới không chỉ thêm một controller và một Docker image. Nó thường kéo theo:

| Thành phần | Công việc mới hoặc cần duy trì |
| --- | --- |
| Code/repository | Dependency management, review, versioning, branching |
| Build/CI | Compile, test, security scan, artifact release |
| Deploy/CD | Environments, manifests, rollout, rollback, approvals |
| Runtime | CPU/memory, scaling, placement, probes, shutdown |
| Service discovery | DNS, endpoint, ingress/mesh, routing policy |
| Network security | TLS/mTLS, IAM, secrets, network policies |
| API/event contracts | Schema, version, compatibility, deprecation |
| Data | Database ownership, schema migration, backup/restore |
| Observability | Logs, metrics, tracing, dashboards, alerting |
| Resilience | Timeout, retries, idempotency, backpressure, circuit breaker |
| Operations | On-call, incident, runbook, SLO, postmortem |
| Governance | Data classification, audit, access reviews, compliance |
| Coordination | Ownership, handoffs, dependency change requests |
| Documentation | Purpose, boundaries, architecture decisions, onboarding |

Nếu công nghệ nền tảng tự động hóa tốt, chi phí thêm một service có thể thấp hơn rất nhiều. Nếu không, cùng một service đơn giản có thể sinh lượng công việc lặp lớn hơn phần logic nghiệp vụ.

### 4.1. Chi phí không tăng tuyến tính trong mọi trường hợp

Giả sử có \(N\) service. Một sơ đồ kết nối tối đa giữa mọi cặp có thể chứa:

\[
E_{\max}=\frac{N(N-1)}{2}
\]

cặp service không hướng, hoặc nhiều hơn khi xét hướng. **Hệ thống thật thường có đồ thị thưa**, nên không được dùng \(N(N-1)/2\) làm dự báo số phụ thuộc thực tế.

Tuy nhiên, chi phí phối hợp tăng theo **số cạnh phụ thuộc có nghĩa**, tần suất thay đổi contract, độ sâu call chain và số nhóm phải tham gia thay đổi, chứ không chỉ theo \(N\).

### 4.2. Service “nhỏ” về code có thể “lớn” về vận hành

Một service 300 dòng thực hiện gửi email có thể cần:

- Secret và quotas của provider.
- Retry/backoff, DLQ, idempotency.
- Xử lý dữ liệu cá nhân và consent.
- Bounce/complaint webhooks.
- Observability và escalation.
- Security review và credential rotation.

Giảm số dòng code không đồng nghĩa giảm số khái niệm cần hiểu.

## 5. Kích thước service khác độ phức tạp vận hành

Không tồn tại quy tắc đúng cho mọi hệ thống như “một service phải dưới 1.000 LOC”, “mỗi nhóm tối đa 5 service” hoặc “mỗi bounded context đúng một repository”.

Các biến đáng xem hơn:

- Service có **lý do nghiệp vụ và trách nhiệm thống nhất** không?
- Các thay đổi trong service có thường xuyên đi cùng nhau không?
- Service có thể triển khai mà không bắt buộc đồng thời đổi 5 services khác không?
- Team có thể xử lý incident của service mà không cần đội khác giải thích toàn bộ hoạt động không?
- Service có sở hữu dữ liệu/contract rõ và kiểm soát invariants không?
- Service có performance/scale/security requirements thực sự khác phần còn lại không?
- Tổng chi phí vận hành boundary có được bù bằng **tự chủ, cách ly lỗi, tốc độ thay đổi hoặc lợi ích kinh doanh** không?

Một service lớn nhưng cohesive, có test tốt và một owner rõ, có thể dễ bảo trì hơn 12 services nhỏ chồng chéo trách nhiệm.

## 6. Tín hiệu định tính của tải nhận thức

Một nhóm có thể tự đánh giá qua câu hỏi:

1. “Tôi có thể giải thích luồng request chính từ đầu đến cuối mà không phải hỏi ba nhóm khác không?”
2. “Khi incident xảy ra, nhóm có dashboard và runbook đủ để bắt đầu khoanh vùng không?”
3. “Một thay đổi trong domain của nhóm có thể được deploy tự chủ phần lớn thời gian không?”
4. “Tôi biết service nào là source of truth cho những dữ liệu mình sử dụng không?”
5. “Tôi có hiểu lý do tồn tại của từng service mình đang on-call không?”
6. “Có bao nhiêu công nghệ/framework trong phạm vi sở hữu mà nhóm phải cập nhật liên tục?”
7. “Tôi có thể thử nghiệm một thay đổi quan trọng trên laptop/CI mà không dựng cả platform không?”
8. “Có hoạt động lặp lại nào tiêu tốn nhiều giờ nhưng không tạo giá trị cho khách hàng không?”
9. “Chúng tôi có đủ thời gian cho refactor, học domain và cải thiện reliability không?”
10. “Có điểm nào chỉ một người biết cách sửa hoặc triển khai không?”

Không nên dùng kết quả khảo sát để xếp hạng “ai có năng lực tư duy thấp”. Mục đích là phát hiện **gánh nặng hệ thống và tổ chức có thể cải thiện**, với tâm lý an toàn và quyền phản hồi thực chất.

### 6.1. Khảo sát 5 mức đơn giản

Ví dụ mỗi người tự đánh giá mức đồng ý từ 1 đến 5:

| Mệnh đề | 1 | 5 |
| --- | --- | --- |
| Tôi có thể thay đổi phần lớn nghiệp vụ mình sở hữu mà không cần nhiều handoff | Rất không đồng ý | Rất đồng ý |
| Công cụ build/deploy/observe cho phép tôi tập trung vào domain | Rất không đồng ý | Rất đồng ý |
| Tôi biết cách xác định nguyên nhân của các sự cố phổ biến | Rất không đồng ý | Rất đồng ý |
| Số công nghệ và service trong phạm vi của tôi dễ kiểm soát | Rất không đồng ý | Rất đồng ý |
| Tôi có đủ thời gian để cải thiện kỹ thuật thay vì chỉ xử lý khẩn cấp | Rất không đồng ý | Rất đồng ý |

Thêm câu hỏi mở: “Điều nào đang làm bạn đổi ngữ cảnh nhiều nhất?” và “Một thay đổi hệ thống có thể giảm tải ngay trong tháng tới là gì?”.

Đọc kết quả theo xu hướng qua các kỳ, kết hợp phỏng vấn. Không diễn giải chênh lệch nhỏ thành “sự thật khách quan”, nhất là với mẫu rất ít người.

## 7. Tín hiệu định lượng hỗ trợ đo tải tổ chức

Một số tín hiệu quan sát được:

| Nhóm tín hiệu | Ví dụ | Diễn giải cẩn trọng |
| --- | --- | --- |
| Ownership | Số service/runtime môi trường phải sở hữu | Số lượng lớn chỉ là dấu hiệu, không là lỗi tự thân |
| Handoffs | Số nhóm cần phối hợp để đưa tính năng ra production | Handoff nhiều có thể cho thấy boundary chưa đúng |
| Change coupling | Tỷ lệ changesets đụng nhiều service | Có thể vì shared release hay feature lớn |
| Lead time | Thời gian từ code tới deploy/useful outcome | Ảnh hưởng cả quy trình và test, không chỉ kiến trúc |
| Deployment | Tần suất deploy, rollback, release coordination | Deploy nhiều không đồng nghĩa deliver value nhanh |
| Reliability | Incident count/severity, recovery time, SLO burn | Cần normalize theo risk và traffic |
| On-call | Pages có hành động, pages nhiễu, ngoài giờ, toil | Page nhiều thường làm giảm thời gian cải tiến |
| Developer experience | Thời gian setup, local test, tìm owner/runbook | Phát hiện extraneous load |
| Dependency | Số edges/hops, synchronous chains, fan-out | Deep chains có thể tạo coupling và latency |
| Contract churn | Breaking changes, consumer failures | Phản ánh chất lượng ranh giới và governance |
| Operational toil | Giờ xử lý thủ công, cập nhật cert/config | Thường có thể tự động hóa |
| Knowledge spread | Bus factor, người duy nhất hiểu hệ thống | Dấu hiệu rủi ro ownership |
| Work in progress | Số việc active/person/team, blocked time | Quá nhiều WIP tăng chuyển ngữ cảnh |

Cần tránh lạm dụng metrics để **đánh giá cá nhân, thưởng phạt hoặc ép con số**. Theo dõi thay đổi của **hệ thống và nhóm**, giải thích bằng ngữ cảnh, bảo vệ quyền riêng tư và không biến chỉ số thành mục tiêu tự thân.

### 7.1. Đo tỷ lệ thay đổi đa service

Giả sử trong 60 tính năng gần đây, 42 cần sửa từ 3 service trở lên:

\[
CrossServiceChangeRate = \frac{42}{60}=70\%
\]

Đây là tín hiệu nên nghiên cứu. Nhưng không kết luận ngay “70% là sai”. Một sản phẩm có quy trình nhiều domain có thể cần thay đổi phối hợp hợp lệ. Cần phân biệt:

- Thay đổi business workflow liên domain thực sự.
- Thay đổi cùng field/enum vì duplicated logic.
- Thay đổi do shared library/config không ổn định.
- Thay đổi deployment đồng loạt dù runtime contract tương thích.

### 7.2. Đo thời gian blocked bởi nhóm khác

Với một tập công việc, ghi thời gian chờ ownership clarification, contract approval, shared environment hoặc release coordination. Nếu “coding time” là 2 ngày nhưng “waiting/handoff” là 12 ngày, tối ưu tốc độ CI thêm 5 phút không giải quyết bottleneck chính.

### 7.3. Đo toil on-call

Theo dõi giờ xử lý alerts/incident lặp lại, tỷ lệ page không có hành động, số lần phải can thiệp thủ công và mức ảnh hưởng tới roadmap. Nên ghi reason và khả năng tự động hóa, không chỉ tổng số alerts.

## 8. Đo tải nhận thức là một quá trình, không phải một số duy nhất

Một thang điểm có thể hỗ trợ workshop nhưng không được coi là phép đo chuẩn khoa học. Ví dụ **đánh giá rủi ro tổ chức** theo năm chiều:

| Chiều | 0 — Thấp | 2 — Vừa | 4 — Cao |
| --- | --- | --- | --- |
| **Domain breadth** | Một miền nghiệp vụ nhất quán | Vài domain liên quan | Nhiều domain không liên quan |
| **Operational surface** | Runbooks/observability thống nhất | Một số service đặc thù | Nhiều hệ/stack/alerts không chuẩn |
| **Coordination** | Thay đổi phần lớn tự chủ | Handoffs định kỳ | Mỗi release cần nhiều nhóm |
| **Change coupling** | Contracts ổn định, deploy độc lập | Đôi khi phối hợp | Thường phải deploy đồng loạt |
| **Uncertainty** | Ownership/docs rõ | Một số mảng mơ hồ | Không rõ SoR/owner/incident path |

Điểm 1 và 3 mô tả trạng thái trung gian. Tổng 0–20 chỉ dùng cho **thảo luận nội bộ và theo dõi tiến triển của cùng nhóm**; không so sánh máy móc giữa teams hoặc gắn với đánh giá nhân sự.

### 8.1. Cách sử dụng scorecard đúng

1. Cho các thành viên đánh giá độc lập, không yêu cầu đồng thuận ngay.
2. Thảo luận các điểm chênh lệch để hiểu góc nhìn.
3. Thu thập ví dụ cụ thể: PR chờ 8 ngày, runbook thiếu, 12 on-call pages vô ích.
4. Chọn một hoặc hai cải tiến có thể kiểm chứng.
5. Đặt metric dẫn dắt và metric kết quả; ví dụ giảm manual deploy steps và giảm blocked time.
6. Lặp lại sau một khoảng thời gian đủ để thấy xu hướng.

**Không:** áp lệnh “phải đạt dưới 8 điểm quý này” khiến mọi người giấu vấn đề.

## 9. Không thể tính công suất tổ chức từ số người đơn thuần

Nói “nhóm có 8 kỹ sư nên đủ sức quản 8 service” là một phép suy luận thiếu căn cứ.

Năng lực thực tế phụ thuộc:

- Mức kinh nghiệm với domain, stack và production.
- Sự trưởng thành của platform CI/CD/observability.
- Hỗ trợ từ security, DBA, networking và SRE.
- Mức độ ổn định của sản phẩm hay thay đổi liên tục.
- On-call và compliance requirements.
- Số múi giờ, thời gian đồng bộ và turnover.
- Workload support, incident frequency và roadmap.
- Chất lượng automated tests, contract tests và local dev.

Một nhóm bốn người với golden path tốt và ba service liên quan có thể tự chủ cao hơn nhóm mười người phải duy trì mười lăm stacks không thống nhất.

### 9.1. Capacity phải tính phần công việc không phải feature

Giả sử một nhóm có 6 kỹ sư, mỗi người 40 giờ/tuần về mặt lịch làm việc, tổng lý thuyết 240 giờ. Nhưng thời gian thực còn dùng cho:

- On-call và incident response.
- Meetings/coordination.
- Code reviews và hỗ trợ đồng nghiệp.
- Security updates và dependencies.
- CI flaky tests, infra upgrades, cost controls.
- Học domain và onboarding.
- Nghỉ phép/đào tạo.

Không lấy 240 giờ làm năng lực giao tính năng chắc chắn. Cũng không dùng 100% utilization làm mục tiêu, vì nó loại bỏ khả năng đối phó sự cố và thay đổi ưu tiên.

## 10. Một mô hình chi phí ranh giới minh họa

Có thể nghĩ về tổng tải công việc đội sở hữu:

\[
L_{\mathrm{team}} \approx L_{\mathrm{domain}}
+ \sum_{i=1}^{N}L_{\mathrm{service\ overhead},i}
+ \sum_{e \in E}L_{\mathrm{coordination},e}
+ L_{\mathrm{oncall}}+L_{\mathrm{change\ uncertainty}}
\]

Đây là **mô hình ý tưởng**, không phải định luật đo được. Nó nhấn mạnh rằng:

- Chi phí domain có thể giữ nguyên khi phân mảnh.
- Mỗi deployable thêm một số thao tác và trách nhiệm lặp.
- Mỗi contract/handoff thêm chi phí phối hợp.
- Độ không chắc chắn tăng nếu ownership mơ hồ.
- On-call và nền tảng có thể giảm hoặc tăng theo architecture.

### 10.1. Ví dụ cụ thể

Một nhóm có thể quản tốt 4 service với:

- Một chuẩn build/deploy.
- Log/trace/metric thống nhất.
- Một domain tương đối rõ.
- Ít sự cố.
- Tự phục vụ DB/IAM theo golden path.
- Runbook và ownership rõ.

Cũng nhóm đó có thể khó quản 4 service khác nếu:

- Mỗi service dùng runtime khác.
- Có 20 external dependencies.
- Phải gọi đội khác để deploy.
- Không có local test environment.
- Secrets được rotate thủ công.
- Một thay đổi cần nhiều simultaneous releases.

**Vấn đề là tải đa chiều, không phải đếm service thuần túy.**

## 11. Conway's Law và cấu trúc tổ chức

**Conway's Law** thường được diễn giải: cấu trúc hệ thống có xu hướng phản ánh cấu trúc giao tiếp của tổ chức thiết kế nó.

Nếu backend, database, QA, security và deployment là những silos riêng phải handoff liên tục, kiến trúc có thể có những ranh giới kỹ thuật tương ứng, nhưng không có team đủ quyền sở hữu outcome end-to-end.

Ví dụ:

~~~text
Backend Team → viết code
DBA Team     → tự tay tạo migration
QA Team      → chạy test thủ công
Ops Team     → triển khai mỗi tuần
Security     → cấp quyền theo ticket
~~~

Một microservice với năm handoffs như vậy khó phát huy lợi ích triển khai độc lập.

### 11.1. Inverse Conway Maneuver

Khi muốn kiến trúc theo các **luồng giá trị / bounded contexts**, tổ chức có thể chủ động hình thành các nhóm có quyền và trách nhiệm tương ứng:

~~~text
Checkout Team
  ├─ hiểu domain checkout
  ├─ sở hữu APIs/data contracts
  ├─ viết test và deploy
  ├─ quan sát SLO
  └─ tham gia incident/on-call

Platform Team
  └─ cung cấp công cụ tự phục vụ cho nhiều nhóm
~~~

Nhưng chuyển cơ cấu tổ chức chỉ để “vẽ cho giống microservices” có thể thất bại nếu nhóm chưa đủ kỹ năng, quyền hoặc nguồn lực.

### 11.2. Phản Conway: không chia team theo mỗi class/service

Một số doanh nghiệp chia nhỏ team theo một endpoint hoặc một microservice, khiến một workflow cần hợp tác giữa quá nhiều nhóm. Cấu trúc đó có thể làm chi phí coordination lớn hơn lợi ích song song hóa.

**Ưu tiên ownership quanh luồng giá trị và domain cohesive**, không lấy số service làm điều kiện tạo team.

## 12. Team Topologies: bốn loại đội hữu ích

Khung Team Topologies gợi ý bốn hình thái tổ chức để tối ưu flow of change và giảm tải:

### 12.1. Stream-aligned team

Một nhóm chịu trách nhiệm liên tục cho **luồng giá trị** hoặc product/domain scope: Checkout, Seller Onboarding, Fulfillment.

Đặc điểm:

- Hiểu nghiệp vụ và trải nghiệm người dùng.
- Thực hiện thay đổi end-to-end trong phạm vi sở hữu.
- Chịu trách nhiệm quality, SLO và vận hành.
- Tối thiểu hóa handoff và phối hợp liên nhóm không cần thiết.

Một stream-aligned team có thể sở hữu **một service, nhiều service hoặc một phần modular monolith**. Không mặc định số lượng deployable bằng số lượng team.

### 12.2. Platform team

Cung cấp các năng lực dùng chung như một **sản phẩm nội bộ**, ví dụ:

- Golden path build/deploy.
- Provisioning service/database.
- IAM, secrets, mTLS, observability.
- Logging/tracing/metrics dashboards.
- Standard runtime, service templates.
- Backups và self-service infrastructure.

Mục tiêu là giảm extraneous load của các stream-aligned teams. **Platform không nên biến thành ticket gate** mà mọi service phải chờ để thay một biến môi trường.

### 12.3. Enabling team

Một nhóm chuyên gia hỗ trợ nâng năng lực cho các nhóm khác: event-driven design, SRE practices, domain modeling, security, performance.

Enabling team thường tương tác **tạm thời**, huấn luyện và hỗ trợ thực hành để đội sản phẩm có thể tự chủ sau đó.

Không nên dùng enabling team như đội “làm hộ toàn bộ observability” vĩnh viễn; điều đó tạo thêm handoff và giảm ownership.

### 12.4. Complicated-subsystem team

Khi có một subsystem đòi hỏi kiến thức chuyên sâu, ví dụ:

- Thuật toán tối ưu routing rất phức tạp.
- Fraud detection model có yêu cầu nghiên cứu cao.
- Storage engine hoặc realtime pricing optimization.
- Một engine tính thuế đa quốc gia đặc biệt phức tạp.

Có thể giao cho nhóm chuyên gia riêng, cung cấp contract ổn định để stream-aligned teams không phải ôm hết tri thức đặc thù.

**Không dùng nhãn complicated-subsystem cho mọi thành phần chỉ vì nó “khó”.** Sự tách này có chi phí, nên cần chứng minh giảm cognitive load tổng thể.

## 13. Ba cách tương tác thường gặp giữa nhóm

### 13.1. Collaboration

Hai nhóm phối hợp sát trong một thời gian để khám phá thiết kế hoặc giải quyết vấn đề mới, ví dụ Checkout và Fraud cùng định nghĩa fraud decision contract.

Ưu điểm: học nhanh, giải quyết bất định. Chi phí: nhiều giao tiếp. Nên có mục tiêu và thời gian, không để trạng thái collaboration liên tục cho mọi release.

### 13.2. X-as-a-Service

Một nhóm cung cấp năng lực với API, documentation, SLO và self-service rõ để nhóm khác sử dụng mà không cần làm việc sát hàng ngày.

Ví dụ Platform cung cấp nút “tạo service mới có CI, logs và secret” hoặc Fraud cung cấp API đánh giá risk với contract rõ.

### 13.3. Facilitating

Enabling team hướng dẫn nhóm khác tiếp nhận kỹ thuật, ví dụ huấn luyện cách viết contract test hoặc xây runbook, rồi giảm dần sự phụ thuộc.

### 13.4. Chọn cách tương tác theo giai đoạn

Cùng hai nhóm có thể collaboration lúc thiết kế sản phẩm mới, sau đó chuyển sang X-as-a-Service khi contract ổn định. Không có một interaction mode cố định cho mọi thời điểm.

**Nguyên tắc:** giảm nhu cầu phối hợp liên tục bằng interface và ownership rõ, nhưng vẫn tạo không gian hợp tác khi domain còn chưa được hiểu.

## 14. Bounded context và ranh giới sở hữu

Một microservice nên bao một tập invariants và hành vi nghiệp vụ cohesive, không nhất thiết là một noun trong database.

Ví dụ trong thương mại điện tử:

~~~text
Checkout Flow
  ├─ Order Domain
  │    ├─ tạo/hủy đơn
  │    └─ quản lý trạng thái đơn
  ├─ Inventory Domain
  │    └─ reserve/release tồn kho
  ├─ Payment Domain
  │    └─ authorize/capture/refund
  └─ Fulfillment Domain
       └─ shipment/tracking
~~~

Các domain này có thể đáng tách khi:

- Ownership rõ, rules ổn định.
- Dữ liệu authoritative riêng.
- Có nhiều consumers và contracts tương đối ổn.
- Tần suất thay đổi hoặc nhu cầu scale khác nhau.
- Đội đủ năng lực triển khai/vận hành độc lập.

Ngược lại, chia Order thành `OrderValidatorService`, `OrderStatusService`, `OrderDiscountService` và `OrderPersistenceService` thường làm một lệnh tạo đơn phải đi qua nhiều RPC chỉ để thực hiện một invariant nội bộ.

### 14.1. Cohesion và coupling

Hai phép hỏi:

- **Cohesion:** những thành phần trong cùng một module/service có thường phải thay đổi cùng nhau vì một lý do nghiệp vụ không?
- **Coupling:** một thay đổi nhỏ ở A có buộc B, C, D cập nhật đồng thời không?

Mục tiêu không phải coupling bằng 0. Hệ thống giao tiếp để làm việc; cần **ổn định ranh giới và contract**, giảm coupled changes không cần thiết.

### 14.2. Không chia theo CRUD bảng

“Có bảng Product nên tạo ProductService”, “có bảng Price nên tạo PriceService” chưa đủ. Phải xem business rules, giá tại thời điểm bán, pricing promotions, ownership và consistency. Một domain được gọi là “Catalog” có thể vẫn chứa nhiều module nội bộ trước khi tách deployables.

## 15. Khi nào nên giữ modular monolith?

**Modular monolith** là một deployable có ranh giới module và ownership logic rõ ràng. Nó có thể cho phép:

- Giao tiếp nội bộ thông qua interface và dependency rules.
- Transaction nhất quán trong một database khi phù hợp.
- Test nhanh hơn so với nhiều RPC/contracts.
- Ít pipelines, secrets, service discovery và on-call surfaces.
- Tái cấu trúc domain khi nghiệp vụ còn thay đổi.
- Sau này trích xuất module thành service khi có nhu cầu thực.

~~~text
Monolith deployable
  ├─ Order Module
  ├─ Catalog Module
  ├─ Inventory Module
  ├─ Payment Integration Module
  └─ Notification Module
      ↓
 Modules giao tiếp qua public interfaces / events nội bộ
~~~

Nó không đồng nghĩa “mọi module gọi tùy ý vào bảng của nhau”. Nếu không enforce boundary, modular monolith có thể thành big ball of mud.

### 15.1. Khi modular monolith là lựa chọn khôn ngoan

- Sản phẩm đang tìm product-market fit hoặc domain chưa ổn định.
- Nhóm nhỏ, chưa có platform tự phục vụ.
- Tính năng thay đổi đồng thời nhiều module.
- Nhu cầu scale chưa khác nhau đáng kể.
- SLO/availability không yêu cầu cách ly deploy từng module.
- Chi phí microservices đang vượt lợi ích.

### 15.2. Khi nên tách một module

- Domain có ownership và contract đã đủ ổn định.
- Nhóm mới cần thay đổi/deploy phần đó tương đối độc lập.
- Workload có profile scale/isolation khác rõ.
- Một module gây lỗi ảnh hưởng hệ thống và cần cô lập failure.
- Data ownership và migration path đã xác định.
- Platform có CI/CD, observability, IAM, security, on-call phù hợp.
- Có business outcome đo được từ việc tách.

**Modular monolith không phải giai đoạn “lỗi thời”**. Nó có thể là kiến trúc mục tiêu bền vững cho một số hệ thống.

## 16. Service-per-team, team-per-service: không có luật cố định

Hai mô hình cực đoan thường gây vấn đề:

- **Một team phải sở hữu quá nhiều dịch vụ không liên quan**: tải hiểu domain và runtime quá lớn.
- **Một service có quá nhiều team đồng sở hữu không rõ quyền quyết định**: mỗi thay đổi phải điều phối và khó xác định owner khi incident.

Một mô hình thực dụng:

- Mỗi service/dataset có **primary owning team**.
- Nhóm sở hữu hiểu cả build, test, deploy, monitoring và incident.
- Có secondary support/escalation cho thành phần critical.
- Team có thể sở hữu nhiều service **nếu scope cohesive và vận hành trong khả năng**.
- Những nền tảng chung có team/platform owner riêng, cung cấp self-service contracts.
- Ownership có quy trình handoff khi tổ chức thay đổi.

Đừng áp “một service = một team” khi đội ngũ quá nhỏ; nó làm số nhóm hoặc vai trò ảo tăng lên mà không có người thực sự vận hành.

## 17. Vòng đời ownership: “you build it, you run it” trong thực tế

Một nhóm được coi là tự chủ khi có khả năng:

1. Hiểu business outcome và user SLO.
2. Thay code và test domain.
3. Xem dependency contract.
4. Triển khai, rollout/canary và rollback.
5. Theo dõi logs/metrics/traces.
6. Phân tích incident và thực hiện mitigation.
7. Quản lý data migrations/backup qua nền tảng được hỗ trợ.
8. Thực hiện security updates và secret rotation theo policy.
9. Lập kế hoạch capacity/cost.
10. Bàn giao tài liệu và kinh nghiệm cho thành viên mới.

Nhưng **tự chủ không có nghĩa mọi người phải là chuyên gia của mọi lớp**. Platform/SRE/Security có thể hỗ trợ bằng sản phẩm và hướng dẫn, còn trách nhiệm nghiệp vụ và hành vi service vẫn rõ ở owning team.

### 17.1. On-call là phép thử ownership

Nếu một nhóm deploy service nhưng không ai có quyền xem metrics hoặc logs khi lỗi, “sở hữu” chưa đầy đủ. Nếu một nhóm trực on-call cho service không hiểu logic nghiệp vụ và luôn phải gọi nhóm khác, ownership đang bị phân tách sai.

### 17.2. Ngăn bus factor thấp

Đảm bảo người thứ hai có thể:

- Triển khai.
- Khôi phục sự cố thường gặp.
- Sửa một thay đổi nghiệp vụ nhỏ.
- Truy cập runbook và dashboards.
- Nắm security boundary.

Không cần ai cũng thuộc toàn bộ hệ thống, nhưng các điểm sống còn không nên phụ thuộc độc nhất vào một cá nhân.

## 18. Độ hạt microservice và change coupling

Một service mới nên giảm hoặc ít nhất không tăng quá mức **số thay đổi phải phối hợp**.

Ví dụ:

~~~text
Trước khi tách:
  Order Module → Discount Module (cùng codebase/deployable)
  Thay đổi rule giảm giá: một PR, một bộ test, một rollout.

Sau khi tách:
  Order Service → Discount Service (HTTP)
  Thay đổi rule giảm giá: cập nhật client, schema, retry,
  dashboard, deployment, compatibility, nhiều on-call boundaries.
~~~

Nếu Discount là một domain độc lập, có đội chuyên trách, rất nhiều consumers và mô hình scale khác biệt, việc tách có thể có lợi. Nếu nó chỉ là helper nội bộ được gọi bởi Order, lợi ích có thể thấp hơn chi phí.

### 18.1. Đo coupling bằng dữ liệu thay đổi

Từ một khoảng thay đổi đủ lớn, xác định:

- Bao nhiêu user-facing features cần chỉnh cả A và B?
- Có cần deploy A/B cùng lúc để tránh lỗi?
- Có thường xuyên phải sửa event schema/enum hay dữ liệu dùng chung?
- Có thể dùng contract backward-compatible không?
- Có thể release riêng và quan sát kết quả không?

Nếu hai service thường xuyên thay đổi đồng thời vì cùng một business invariant, cân nhắc hợp nhất hoặc di chuyển responsibilities.

### 18.2. Tránh hiểu nhầm “có nhiều commit cùng ngày” là coupling

Hai nhóm có thể cùng deploy vào thứ năm vì quy trình release chung, dù code hoàn toàn độc lập. Phải tách **temporal correlation** khỏi **semantic change coupling**.

## 19. Sơ đồ phụ thuộc giúp thấy tải phối hợp

Ví dụ tổ chức A:

~~~text
Checkout Team
    ├──► Order API
    ├──► Payment API
    ├──► Inventory API
    └──► Customer API
~~~

Mỗi edge cần contract và owner. Nếu một checkout change phải sửa Payment và Inventory vì các API chưa ổn, tải phối hợp cao.

Một dependency graph nên gắn:

- Caller/callee, operation và criticality.
- Synchronous/asynchronous.
- Owner team.
- Contract version.
- Tỷ lệ thay đổi cùng nhau.
- SLO/latency budget.
- Số incident liên quan.
- Thời gian chờ approval/contract update.
- Có fallback hay không.

### 19.1. Đừng chỉ đếm số edges

Một edge Order→Payment stable, có API/contract test và tài liệu tốt, ít gây tải hơn 3 edges tới ba hệ thống legacy không có owner. Cần xem **độ bất định và chi phí thay đổi của edge**, không chỉ số lượng.

### 19.2. Độ sâu call chain và fault isolation

~~~text
Gateway → A → B → C → D → E
~~~

Đường đồng bộ sâu tăng xác suất timeout, phức tạp propagation và khó tìm root cause. Một microservice decomposition tốt không tự động cho phép fan-out tùy tiện; phải quản lý deadline, idempotency, trace và bounded contexts.

## 20. Đánh giá ranh giới mới bằng câu hỏi “việc gì trở nên dễ hơn?”

Trước khi tạo service mới, viết một ADR trả lời:

1. **Vấn đề hiện tại là gì?** Tốc độ thay đổi, ownership, scale, reliability hay security isolation?
2. **Nếu không tách thì sao?** Có thể sửa bằng module boundary, CI, config hoặc team ownership?
3. **Lợi ích cụ thể nào cần đo?** Giảm lead time, deploy failure, blast radius hoặc infrastructure cost?
4. **Ai chịu trách nhiệm service mới?** Domain, code, dữ liệu, on-call, SLO, security?
5. **Dữ liệu authoritative nằm ở đâu?** Cần migrate DB hay chỉ read projection?
6. **Consumers và contracts là gì?** Bao nhiêu service có thể bị ảnh hưởng?
7. **Giao tiếp đồng bộ hay bất đồng bộ?** Transaction, consistency, retry, ordering?
8. **Việc local test và CI trở nên dễ hay khó hơn?**
9. **Nền tảng có sẵn golden path không?** Provisioning, secrets, monitoring, release?
10. **Kế hoạch rollback/hợp nhất lại nếu sai?**
11. **Ai review sau 30/60/90 ngày?**
12. **Quy mô nhóm và kinh nghiệm có đủ cho vòng đời vận hành chưa?**

Nếu chỉ trả lời “cho đúng microservices best practice”, lý do chưa đủ.

## 21. Một bảng quyết định tách service

| Tiêu chí | Giữ module | Tách service có thể hợp lý |
| --- | --- | --- |
| Domain boundary | Chưa rõ, invariants thường thay đổi cùng nhau | Rõ và ổn định |
| Independent delivery | Thay đổi luôn đi cùng module khác | Thực sự cần và có thể release độc lập |
| Data ownership | Transaction/SoR gắn chặt | Có ownership/consistency rõ |
| Workload | Tương tự các module khác | Scale, latency hoặc isolation khác đáng kể |
| Organization | Cùng team nhỏ, thiếu ops support | Có owner đủ năng lực và platform |
| API/contract | Chưa ổn, thay schema liên tục | Contract đủ ổn và có tests |
| Reliability | Lỗi module chưa cần process isolation | Fault isolation mang lại lợi ích rõ |
| Security/compliance | Cùng trust boundary | Cần trust/permission boundary riêng |
| Deployment | Thêm boundary tạo nhiều handoffs | Tự động hóa đủ trưởng thành |
| Observability | Khó trace/test qua network | Metrics/traces/runbooks sẵn sàng |

Không có số “yes” tuyệt đối. Một yêu cầu pháp lý mạnh có thể làm quyết định tách hợp lý dù chi phí cao; một feature nhỏ có thể chọn module dù nhiều người thích microservices.

## 22. Ví dụ: ứng dụng thương mại điện tử 6 người

Giả định nhóm backend 6 người sở hữu:

- 1 Checkout API.
- 1 Catalog API.
- 1 Inventory API.
- 1 Payment Orchestrator.
- 1 Notification Worker.
- 1 Reporting Worker.

Các service dùng cùng Spring Boot runtime, PostgreSQL-managed service, Kafka và một platform CI/CD chuẩn.

### 22.1. Đánh giá ban đầu

- Domain: Checkout/Catalog/Inventory/Payment tương đối liên quan nhưng có nhiều invariants.
- Operations: 6 deployables, on-call, runbooks; có thể quản nếu incident ít và golden paths tốt.
- Dependencies: Payment external provider, Kafka, DB; cần hiểu failure modes.
- Change coupling: 20% checkout features sửa hơn một API.
- Developer experience: có template, tracing và CI khá tốt.

Với các giả định này, kiến trúc có thể chấp nhận. **Không kết luận chỉ từ số 6 service = 6 người.**

### 22.2. Đề xuất tách tiếp DiscountService, CouponService và PromotionRuleService

Cần hỏi:

- Ba thành phần có thực sự có owner/contract độc lập?
- Có cần scale khác Checkout không?
- Thay đổi chương trình khuyến mãi có làm cả ba thay đổi cùng lúc?
- Có một nguồn authoritative cho eligibility và pricing chưa?
- Nếu CouponService timeout giữa checkout, kết quả giao dịch ra sao?
- Ai trực on-call ba service mới?
- Có đủ bảo vệ khỏi double-discount và stale promotion data?

Nếu các rule cùng thay đổi trong một business decision, phương án **Pricing/Promotion module** trong một deployable có thể giảm nhiều RPC/contracts.

### 22.3. Khi tách vẫn có lợi

Nếu Promotion được nhiều sản phẩm dùng, có đội chuyên trách, cần chạy simulation/tối ưu riêng và scale độc lập, một service rõ domain có thể tạo giá trị. Tách “Promotion Domain” có thể tốt hơn chia thành nhiều CRUD services.

## 23. Ví dụ so sánh hai phương án kiến trúc

Một hệ thống onboarding khách hàng có năm bước: identity verification, consent, profile, welcome notification, CRM sync.

### Phương án A — Năm microservices

~~~text
Gateway
  → IdentityVerificationService
  → ConsentService
  → ProfileService
  → WelcomeEmailService
  → CRMSyncService
~~~

Có thể phù hợp nếu các domain có ownership khác nhau, compliance rất riêng và demand độc lập. Nhưng cần năm pipelines, contracts, data flows và on-call responsibilities.

### Phương án B — Một Onboarding Service với module boundaries

~~~text
Onboarding Service
  ├─ Verification module
  ├─ Consent module
  ├─ Profile module
  ├─ Notification adapter
  └─ CRM integration adapter
~~~

Có thể phù hợp với nhóm nhỏ và workflow thay đổi nhanh, giúp test end-to-end và transaction nội bộ dễ hơn.

### 23.1. Tiêu chí đánh giá bằng thử nghiệm

- Thời gian thêm một trường vào onboarding.
- Số repositories/PRs/handoffs.
- Độ khó local test.
- Khả năng isolate provider failure.
- Recovery time khi email provider unavailable.
- Số data ownership ambiguities.
- Tỷ lệ deploy thực sự độc lập.
- Chi phí CPU/DB/network/observability.

Không tự giả định phương án B luôn tốt; độ phức tạp nội tại của identity/consent có thể cần boundary độc lập.

## 24. Platform engineering giảm tải ngoại lai

Một platform team có thể cung cấp **golden path** — đường chuẩn để tạo và vận hành service với lựa chọn đã được kiểm chứng.

Ví dụ developer tạo service mới qua template:

~~~text
create-service order-pricing
    ↓
Repository + standard build
    ↓
CI tests + security scanning
    ↓
Deployment manifest + rollback strategy
    ↓
Secrets/workload identity
    ↓
OpenTelemetry/metrics/logs
    ↓
SLO dashboard + alert links
    ↓
Ownership + runbook template
~~~

Các công cụ và phiên bản cụ thể tùy hạ tầng. Quan trọng hơn tool là việc **nhóm sản phẩm có thể tự phục vụ với feedback nhanh và chính sách mặc định an toàn**.

### 24.1. Những năng lực nên chuẩn hóa

- CI/CD và artifact signing/scan.
- Secrets/IAM, access requests.
- Service discovery, ingress, TLS.
- Standard HTTP/gRPC client timeout, retry, tracing.
- Feature flags/config distribution.
- Data migrations và backup/restore practices.
- Error handling, structured logs, trace propagation.
- Dashboards và SLO templates.
- Contract/schema registries.
- Local development/test environments.

### 24.2. Đừng biến platform thành “siêu microservice central team”

Nếu mọi thay đổi config đều phải mở ticket và chờ platform, team product mất tự chủ. Platform-as-a-product cần:

- Tài liệu self-service.
- SLO cho các thao tác phát triển quan trọng.
- Roadmap và phản hồi từ người dùng nội bộ.
- “Paved road” mặc định nhưng có escape hatch được quản lý.
- Telemetry về adoption, setup time, failure rate và support burden.

### 24.3. Quy mô platform hợp lý

Một tổ chức 6 người không nhất thiết cần thành lập platform team độc lập 4 người. Có thể bắt đầu bằng **shared templates và một nhóm nhỏ kiêm nhiệm có ownership rõ**, rồi chuyên môn hóa khi nhu cầu lặp và bottleneck đã rõ.

## 25. Giảm đa dạng công nghệ không cần thiết

Một đội phải vận hành Java, Node.js, Python, Go, Ruby với nhiều Kafka clients, ba API gateways và bốn kiểu deploy có thể có cognitive load cao dù số service ít.

**Technology diversity** có lợi khi workload thực sự cần:

- Python cho ML workflow.
- Go cho network-intensive component.
- Java cho core business APIs nếu đội có chuyên môn.
- Đặc thù performance hoặc ecosystem.

Nhưng quyết định đổi stack vì “thú vị” có thể tạo:

- Nhiều security update streams.
- Khó chia on-call.
- Khó chuẩn hóa metrics/tracing.
- Nhiều dependency incompatibilities.
- Onboarding và developer tooling phức tạp.

Cần có technology radar/chính sách lựa chọn đơn giản: mặc định dùng stack quen thuộc, chấp nhận ngoại lệ có ADR và owner.

**Mục tiêu không phải cấm đổi mới**, mà là biết tổng chi phí sở hữu một công nghệ mới trong nhiều năm.

## 26. Chuẩn hóa observability để giảm thời gian tìm nguyên nhân

Khi mỗi service dùng log format, metric names và trace headers khác nhau, incident response buộc on-call mở nhiều dashboards và suy đoán luồng request.

Một bộ chuẩn tối thiểu:

- Service name, version, environment, region/AZ.
- Trace ID/correlation ID.
- Inbound request rate, errors, p95/p99.
- Outbound dependency attempts, timeouts, retries.
- Thread/connection pool saturation.
- DB/broker lag và event IDs ở nơi cần.
- SLO/error budget và runbooks.
- Deployment/config annotations.

Không đưa PII, access tokens hoặc high-cardinality request IDs vào metric labels. Có thể gắn vào logs/traces đã phân quyền khi cần.

### 26.1. Giảm số công cụ để chẩn đoán

Một gateway dashboard cho “user-facing symptom”, một service map cho dependencies, và link tới tracing/logs thường hữu ích hơn nhiều dashboards tùy hứng với ý nghĩa metric khác nhau.

### 26.2. SLO giúp ưu tiên thay vì page mọi CPU spike

Một service có CPU tăng nhưng không ảnh hưởng user SLI có thể không cần incident cùng mức với checkout unavailable. Hệ thống alert phải gắn với impact và khả năng hành động, giảm alert fatigue.

## 27. Tổ chức on-call bền vững

Một nhóm sở hữu nhiều service nhưng không có giờ xử lý incidents có thể nhanh chóng cạn thời gian cho feature và learning.

### 27.1. Các dấu hiệu quá tải

- Page vào giờ đêm xảy ra nhiều ngày liên tiếp.
- Nhiều alert không cần hành động nhưng vẫn đánh thức người trực.
- Một service không có runbook, phải gọi tác giả cũ.
- Incident chỉ khắc phục bằng restart mà không tìm nguyên nhân.
- Roadmap liên tục bị gián đoạn bởi support tickets.
- Sau postmortem không có capacity để làm corrective actions.
- Hầu hết thời gian chỉ chạy theo sự cố.

### 27.2. Cách giảm

1. Phân loại alerts theo actionability và user impact.
2. Loại bỏ hoặc chuyển các alert nhiễu sang dashboard/ticket.
3. Bổ sung runbook cho 5 failure modes thường gặp.
4. Đặt SLO và escalation paths rõ.
5. Tự động hóa remediation an toàn khi có bằng chứng.
6. Cải thiện retry/timeouts/circuit breakers.
7. Giảm số service chưa có owner hoặc hợp nhất nếu phù hợp.
8. Dành capacity để xử lý postmortem actions.

Không cố định số người tối thiểu của một vòng trực chung cho mọi tổ chức; cần xét timezone, mức criticality, chế độ hỗ trợ và mức incident thực.

## 28. Chi phí phối hợp khi thay đổi API hoặc event

Một service tiêu thụ bởi 8 clients có thể không quá tải nếu contract ổn định. Nhưng nếu producer đổi field/enum liên tục mà không có backward compatibility, mọi thay đổi gây nhiều PR và họp.

### 28.1. Contract ownership

- Producer xác định semantics và publish version.
- Consumer chỉ dùng fields cần thiết, không phụ thuộc implementation.
- Tests kiểm tra consumer/provider compatibility.
- Schema evolution có deprecation window.
- Breaking changes được thông báo và migration có owner.

### 28.2. Tổ chức boundary phù hợp

Nếu một tính năng phải thay đổi đồng thời cả producer và 5 consumers vì mọi service phụ thuộc DTO nội bộ, cần nghiên cứu:

- Có thể tạo read model stable hơn?
- Shared business logic có nên nằm chung domain/module?
- Producer đang phát quá nhiều implementation details?
- Có thể bổ sung optional field theo contract thay vì breaking change?
- Nhóm sở hữu API có được trao quyền quyết định hợp lý không?

### 28.3. Async không tự xóa cognitive load

Đổi HTTP calls thành events có thể giảm runtime coupling, nhưng thêm:

- Broker schemas.
- Duplicate/out-of-order handling.
- DLQ và replay.
- Eventual consistency.
- Debug correlation và data governance.
- Consumer lag/freshness SLO.

Nếu event-driven được áp dụng chỉ để “đỡ gọi nhau”, nhưng không có ownership và observability, tổng tải có thể còn cao hơn.

## 29. Data ownership rõ ràng làm giảm tải phối hợp

Ví dụ ba services đều cập nhật `customer.email` trong database chung. Khi thông tin sai, không biết ai có quyền sửa.

Giải pháp:

~~~text
Customer Service = authoritative email
    │
    ├── Customer API
    └── CustomerEmailChanged event
          ├── Notification projection
          └── Analytics projection
~~~

Điểm mấu chốt:

- Một authoritative writer theo business rule.
- Consumers có projection/freshness và quyền sử dụng rõ.
- Contract versioned.
- Có replay/reconciliation khi event miss.
- User-facing operation có trạng thái pending/degraded phù hợp.

**Tuy nhiên**, việc tách Customer thành 8 services nhỏ chỉ vì chia field theo bảng có thể tạo nhiều boundary không cần thiết. Ownership rõ nên được thiết kế ở **domain level**, trước khi quyết định deployable level.

## 30. Các chỉ dấu của phân rã vượt năng lực tổ chức

Một số dấu hiệu mạnh khi xuất hiện đồng thời:

1. Không ai có thể giải thích luồng chính mà không nhờ nhiều nhóm.
2. Một change nhỏ cần sửa hàng loạt services, APIs và pipeline configs.
3. Nhiều service không có primary owner rõ.
4. On-call bị kéo vào incident mà không có quyền deploy/debug.
5. Thời gian waiting/handoff vượt đáng kể thời gian làm việc trực tiếp.
6. Có nhiều repositories gần như chỉ chứa proxy/forwarding CRUD.
7. Mỗi service tự triển khai logging/tracing/security khác nhau.
8. Contract changes thường xuyên gây lỗi runtime.
9. Bản sao data và writers bị phân tán không có SoR.
10. Số lượng CI pipelines/flaky tests khiến PR không có feedback nhanh.
11. Chỉ một người hiểu một số service quan trọng.
12. Service deployments phải phối hợp theo release train dù tuyên bố độc lập.
13. Khôi phục incident mất thời gian chủ yếu để tìm đúng owner hoặc access.
14. Đội ngũ không có thời gian xử lý reliability debt.
15. Các nhóm phải duy trì nhiều thứ họ không còn thực sự phát triển.

Một dấu hiệu đơn lẻ chưa đủ kết luận. Ví dụ release train có thể do quy định tuân thủ; cần đánh giá chi phí và khả năng cải thiện theo bối cảnh.

## 31. Cách quyết định hợp nhất các microservices

Hợp nhất không phải thừa nhận thất bại. Một phần của kiến trúc tốt là **giảm ranh giới không còn đem lại lợi ích**.

### 31.1. Ứng viên hợp nhất

- Hai services luôn thay đổi cùng nhau.
- Không có consumer hoặc owner độc lập đáng kể.
- Cùng dữ liệu và cùng business invariants.
- Giao tiếp synchronous với nhau trên gần như mọi request.
- Hai deployments không có nhu cầu scale hoặc trust boundaries khác.
- Một service chỉ forward request hoặc bọc CRUD trivial.
- Khi incident, luôn phải debug cả hai như một thành phần.

### 31.2. Trường hợp chưa nên hợp nhất

- Một subsystem có security/isolation requirement khác.
- Workload có scale/latency khác lớn.
- Owner teams và business outcomes độc lập rõ.
- Dữ liệu có nghĩa vụ retention/sovereignty riêng.
- Failure isolation là yêu cầu đã được chứng minh.
- API phục vụ nhiều consumers có contract ổn định.
- Hợp nhất sẽ tạo domain coupling lớn hơn lợi ích.

### 31.3. Quy trình hợp nhất an toàn

1. Xác định business behavior và API/event contracts.
2. Chụp baseline: lead time, incidents, latency, cost.
3. Vẽ data ownership và migration plan.
4. Đưa logic vào một codebase/module có boundary rõ.
5. Giữ compatibility adapter hoặc endpoint trong giai đoạn chuyển đổi.
6. Di chuyển traffic/consumers từng bước, canary nếu phù hợp.
7. Reconcile dữ liệu; kiểm tra idempotency và event replay.
8. Thu hồi service runtime, secrets, queues, dashboards và IAM không còn cần.
9. Cập nhật ownership và runbooks.
10. Đo lợi ích sau 30/60/90 ngày.

**Không delete một service chỉ vì không còn traffic trong 24 giờ**: nó có thể chạy batch theo tháng hoặc chỉ được gọi trong fallback path. Kiểm tra inventory và owners.

## 32. Modularization là cách giảm coupling trước khi tách

Giả sử một monolith có các packages:

~~~text
com.shop.order
com.shop.payment
com.shop.inventory
com.shop.catalog
~~~

Có thể enforce dependency rules: Order gọi Payment qua public port, không import lớp persistence của Payment; mỗi module có domain contracts và tests.

Ví dụ ý tưởng Java:

~~~java
public interface PaymentAuthorizationPort {
    AuthorizationResult authorize(
            String orderId,
            Money amount,
            String idempotencyKey);
}
~~~

Trong modular monolith, adapter có thể gọi trực tiếp module nội bộ. Khi thực sự cần tách process, cùng port có thể được implement bằng HTTP/gRPC client với timeout, retries và observability.

**Điểm quan trọng:** interface giúp giảm coupling ở code level, nhưng không tự giải quyết data ownership hay transaction; ranh giới vẫn phải có rule và test.

### 32.1. Test architecture boundaries

Có thể viết tests kiểm tra import/module dependencies hoặc dùng công cụ hỗ trợ architecture tests. Ví dụ:

- Module Catalog không được truy cập bảng Order.
- Module Payment không import implementation của Order.
- Các API công khai có contract tests.
- Domain invariants được test trong module owner.

Những tests này giảm nguy cơ modular monolith thành một khối phụ thuộc vòng tròn.

## 33. Developer experience là chỉ báo của extraneous load

Một người mới muốn thêm field vào Invoice API nhưng phải:

1. Cài ba ngôn ngữ.
2. Xin sáu quyền cloud.
3. Clone mười hai repositories.
4. Tạo 25 secret local.
5. Dựng toàn bộ Kafka + DB + Redis + service mesh.
6. Chạy script không có tài liệu.
7. Đợi staging môi trường chung không bận.
8. Hỏi người cũ để deploy.

Đây là gánh nặng không nhất thiết đến từ nghiệp vụ Invoice.

### 33.1. Các cải tiến có giá trị cao

- Dev container hoặc môi trường phát triển chuẩn.
- Local fake/service virtualization cho dependencies.
- Testcontainers cho DB/broker boundary quan trọng.
- Template tạo service/dependency contract.
- One-command local component test.
- Standard profile/config và secret injection an toàn.
- Preview environment tự động khi cần.
- Contract tests chạy trong CI.
- Documentation “từ clone tới first successful request”.
- Ownership catalog và troubleshooting guide.

### 33.2. Đo thời gian để đạt năng lực làm việc

Một metric hữu ích có thể là “median thời gian từ lúc có quyền truy cập hợp lệ đến lúc chạy được một test end-to-end local trong domain mới”. Nó cần được thu thập có đồng ý và không dùng để chấm cá nhân. Mục tiêu là giảm friction hệ thống.

## 34. Governance nhẹ để tránh tách service vô tội vạ

Một quy trình tạo service mới có thể yêu cầu **ADR ngắn** và review chéo bởi domain owner + platform/security khi phù hợp:

| Câu hỏi | Nội dung cần có |
| --- | --- |
| Business purpose | User outcome hoặc domain responsibility |
| Ownership | Primary team, on-call, data owner |
| Boundary | API/events, dependencies, no shared DB writes |
| Independence | Vì sao cần deploy/scale/trust riêng |
| Lifecycle cost | CI, observability, IAM, SLO, runbook |
| Alternatives | Module/modular monolith, library, existing service |
| Risks | Data migration, consistency, retry, failure modes |
| Success metrics | Lead time, reliability, cost, cognitive-load outcomes |
| Revisit date | Khi nào đánh giá giả thuyết tách |

Không tạo review board xử lý mỗi thay đổi nhỏ theo cách làm tăng handoff không cần thiết. Có thể tự động cho các thay đổi theo golden path, và review sâu những ranh giới mới hoặc dữ liệu nhạy cảm.

### 34.1. Nguyên tắc “service tax”

Để đội ngũ nhận thức đầy đủ chi phí, ADR có thể liệt kê công việc bắt buộc cho mỗi service:

- Có owner/on-call.
- Có contract/version policy.
- Có SLI/SLO phù hợp.
- Có dashboard/log/traces.
- Có CI/CD, scan, rollback.
- Có secrets/IAM và backup/restore nếu lưu data.
- Có documented incident playbook.

Nếu một đề xuất không có năng lực thực hiện những nghĩa vụ tối thiểu, **chưa nên thêm deployable boundary** trừ khi có rủi ro bắt buộc phải tách và kế hoạch bổ sung năng lực.

## 35. Ví dụ ADR: có nên tách Promotion Service?

~~~markdown
# ADR: Tách Promotion Domain thành service độc lập?

## Context
Checkout và Catalog cùng dùng logic promotion. 60% thay đổi
promotion hiện phải chỉnh Order và Catalog. Nhóm Checkout
đang on-call cho nhiều tích hợp khác.

## Options
A. Giữ Promotion module bên trong Checkout.
B. Tạo Promotion module dùng chung trong modular monolith.
C. Tách Promotion Service với API/version/owner riêng.

## Decision factors
- Có owner cho promotion rules và pricing semantics?
- Các consumers có contract ổn định?
- Cần scale/rollout độc lập không?
- Có thể test eligibility theo dữ liệu và thời điểm chính xác?
- Số synchronous hops và latency budget có chấp nhận?
- Khi Promotion unavailable, checkout xử lý thế nào?
- Data freshness, caching, snapshot at checkout?

## Expected benefits
- Giảm coordinated changes, rút ngắn lead time.
- Làm rõ data owner và pricing rules.
- Cho phép kiểm thử/release rules độc lập.

## Costs
- Thêm runtime, monitoring, IAM, support và on-call.
- API/event schema, timeout, retry, idempotency.
- Data migration/caching và provider dependency.

## Decision
Chưa chọn chỉ dựa vào số dòng code.
Thử module boundary và contract trong một giai đoạn
đủ quan sát; chỉ tách runtime khi benefits vượt overhead.

## Validation
Đo cross-service changes, lead time, SLO và on-call toil.
~~~

Đây là một mẫu ADR để thảo luận; kết luận thực tế phải được chính nhóm có dữ liệu và quyền quyết định đưa ra.

## 36. Dashboard theo “flow of change” và vận hành

Một dashboard tổ chức-kỹ thuật có thể gồm:

### 36.1. Flow metrics

- Lead time cho **một thay đổi có giá trị hoàn chỉnh**.
- Number of handoffs và blocked time.
- Cross-service changes per feature.
- Waiting time for contract review/deploy.
- Deployment frequency cùng change failure rate.
- Thời gian khôi phục dịch vụ sau thay đổi lỗi.

### 36.2. Reliability metrics

- User-facing SLO burn.
- Incidents theo severity và affected journeys.
- Mean time to detect/mitigate/restore (với phân phối, không chỉ mean).
- Repeated incidents và postmortem corrective action completion.
- On-call pages, actionability và time spent.

### 36.3. Architecture metrics

- Services per owner team và missing owners.
- Runtime stacks/pipelines khác biệt.
- Synchronous dependency chain length ở critical journeys.
- Contract breaking changes.
- Databases có nhiều writers không kiểm soát.
- Services không có CI/readiness/SLO/runbook.
- Platform golden path adoption.

### 36.4. Developer experience

- Thời gian setup môi trường.
- Local test success rate và thời gian chạy.
- CI flakiness.
- Survey tải nhận thức và gánh nặng tools.
- Thời gian onboarding domain mới.
- Số manual repeatable tasks.

**Không tạo một “điểm chất lượng đội” bằng cách cộng tất cả metric** rồi xếp hạng nhân sự. Dashboard phục vụ quyết định cải tiến, không là bảng thi đua giữa những nhóm khác scope.

## 37. Phương pháp khảo sát tải nhận thức theo quý

Một buổi workshop 60–90 phút có thể làm:

1. **Chuẩn bị:** service inventory, owners, dashboard flow/SLO, incidents, recent change sample.
2. **Cá nhân trả lời 5 mệnh đề:** về hiểu domain, autonomy, tooling, on-call, uncertainty.
3. **Lập bản đồ chỗ phải chuyển ngữ cảnh:** từ một feature thực tế qua teams/repos/deploys.
4. **Xác định top 3 extraneous burdens:** ví dụ môi trường staging dùng chung, cloud permissions, nhiều pipelines khác nhau.
5. **Xếp loại:** có thể giải quyết bằng module boundary, platform automation, contract stabilization, documentation hay organizational change?
6. **Chọn một cải tiến trong 4 tuần:** có owner, scope và tiêu chí kiểm chứng.
7. **Đặt lịch xem lại:** so sánh dữ liệu trước/sau, lấy phản hồi định tính.

Không bắt buộc mọi người công khai câu trả lời cá nhân. Với nhóm nhỏ, kết quả tổng hợp vẫn có thể nhận diện người cụ thể; ưu tiên thảo luận trong môi trường tin cậy và không trích dẫn ngoài ngữ cảnh.

## 38. Cách giảm tải mà không tái kiến trúc toàn bộ

Nhiều cải tiến nhỏ có thể tạo tác động lớn hơn việc chia/gộp service ngay:

### 38.1. Chuẩn hóa contract

Dùng OpenAPI/protobuf/event schema và contract test, quy định compatibility/deprecation. Giảm số lần ping nhau để hỏi JSON field nghĩa gì.

### 38.2. Tập trung các thao tác lặp

Tạo reusable CI templates, dashboard/runbook templates, secrets rotation workflow, standardized deployment rollback. Giảm thời gian duy trì nhiều service.

### 38.3. Làm rõ data ownership

Một authoritative writer per business concept; consumers dùng API/event/projections, không tùy tiện sửa shared database.

### 38.4. Giảm số synchronous hops trên critical path

Hợp nhất những helper services quá nhỏ, hoặc chuyển một số tác vụ không cần kết quả ngay sang async flow có contract và SLO phù hợp.

### 38.5. Giảm context switching

Giới hạn work in progress, gom thay đổi cùng domain, có owner rõ, dành khung thời gian cho reliability improvement. Không kéo kỹ sư vào quá nhiều roadmap/incident channel.

### 38.6. Dọn service bỏ hoang

Service không rõ owner, không còn consumer hoặc chỉ làm proxy trivial nên được đánh giá để retire/hợp nhất sau khi kiểm tra cold paths và batch dependencies.

### 38.7. Bổ sung tài liệu kiến trúc sống

Service catalog, data flow, runbook, ADR, ownership, incident links cập nhật theo PR/deploy. Tài liệu giảm phụ thuộc vào một cá nhân “nhớ hết mọi thứ”.

## 39. Kế hoạch cải tiến 90 ngày — ví dụ

### Ngày 1–15: lập đường cơ sở

- Inventory services, owners, repos, on-call schedules.
- Map critical journeys và cross-service dependencies.
- Thu thập PRs/features gần đây để tính cross-service change rate.
- Ghi SLO, incidents, on-call toil và setup/deploy friction.
- Khảo sát ngắn về cognitive load.
- Không thay đổi structure lớn khi chưa hiểu root causes.

### Ngày 16–30: chọn bottleneck

Giả sử thấy:

- 10 services không có runbook.
- 5 pipelines làm deployment khác nhau.
- 60% checkout features cần chỉnh hai modules chỉ vì shared DTO.
- Một team luôn là bottleneck cấp quyền test environment.

Chọn một cải tiến từ **platform** (chuẩn CI + observability) và một cải tiến từ **boundary** (ổn định DTO contract hoặc hợp nhất helper).

### Ngày 31–60: triển khai có giới hạn

- Pilot golden path cho 2–3 services.
- Tự động hóa local environment/test setup.
- Viết ownership/runbook cho critical services.
- Thử contract tests cho hai interfaces gây lỗi thường xuyên.
- Hợp nhất/đưa một microservice helper vào module nếu có ADR và rollback.
- Huấn luyện team bằng enabling interaction để chủ động về sau.

### Ngày 61–90: kiểm chứng

- Đo blocked time, lead time và cross-service changes.
- So sánh on-call pages/incident mitigation.
- Phỏng vấn developers về cognitive load.
- Xem dữ liệu đã đủ để quyết định thêm/bớt deployable boundary chưa.
- Mở rộng giải pháp có bằng chứng; bỏ ý tưởng không hiệu quả.

**Không hứa trước % cải thiện** khi chưa có baseline. Có thể đặt outcome rõ như “giảm giờ thao tác deploy thủ công” và kiểm chứng thực tế.

## 40. Tình huống: một nhóm 4 người sở hữu 18 microservices

Giả định nhóm có 4 kỹ sư, 18 services, 5 ngôn ngữ/runtime, 4 DB engines, không có platform hỗ trợ và on-call 24/7.

### 40.1. Quan sát

- Nhiều stack có cập nhật bảo mật riêng.
- Một incident liên quan bốn hệ thống, khó tìm owner.
- PR thường chờ người có chuyên môn ngôn ngữ tương ứng.
- Kỹ sư ít thời gian cải thiện domain.
- Local test phải dựng rất nhiều dependencies.

Có **rủi ro tải nhận thức cao**, nhưng chưa được kết luận bằng ngưỡng 18/4. Cần xem service usage, criticality, CI automation, incidents và skill distribution.

### 40.2. Các lựa chọn

1. **Giảm bề mặt:** gộp helper services không mang boundary có giá trị, retire services không dùng.
2. **Chuẩn hóa stack:** ưu tiên runtime/team skills chính, giữ ngoại lệ có lý do.
3. **Platform support:** templates, secrets, deployment, observability.
4. **Sắp xếp ownership:** nhóm domain rõ, người hỗ trợ được đào tạo.
5. **Giảm synchronous coupling:** contract stable, bản sao dữ liệu hoặc async khi phù hợp.
6. **Thay đổi roadmap:** dành capacity xóa reliability/deployment debt.
7. **Bổ sung nhân sự/chuyên gia:** khi workload/độ phức tạp domain thật sự yêu cầu, không chỉ vì muốn tăng service count.

### 40.3. Điều không nên làm

Tạo thêm ba services “để chia nhỏ 18 services” mà không có owner mới, không giảm công việc và không loại bỏ dependency. Số deployables tăng nhưng giới hạn tổ chức vẫn giữ nguyên.

## 41. Tình huống: platform quá tập trung

Một tổ chức có 8 stream teams và một platform team nhỏ. Mọi việc — tạo DB, đổi env var, triển khai canary, xem logs — đều phải mở ticket cho platform. Mỗi PR chờ vài ngày.

### 41.1. Nhận định

Platform vốn được tạo để giảm tải, nhưng cách cung cấp thành **queue tập trung** làm tăng handoff và cognitive load ở cả hai phía.

### 41.2. Biện pháp

- Chuyển các thao tác thường xuyên thành self-service APIs/UI/CLI theo policy.
- GitOps/Pull Request templates và approval tự động cho trường hợp an toàn.
- RBAC scoped, audit trail và quotas.
- Dashboard tài liệu rõ, mặc định chuẩn.
- Đo platform request lead time, failure rate và satisfaction.
- Dành thời gian platform xử lý nhu cầu có độ phức tạp cao thay vì lặp tasks cơ bản.

### 41.3. Trade-off

Self-service cần guardrails để tránh cấp quyền quá rộng, cloud cost vượt budget hoặc làm mất data. Giảm handoff **không được đổi lấy thiếu kiểm soát bảo mật**.

## 42. Tình huống: “mỗi domain một team” nhưng một feature vẫn cần 7 nhóm

Một checkout feature liên quan:

- Identity.
- Customer.
- Catalog.
- Pricing.
- Inventory.
- Order.
- Payment.

Đây có thể là quy trình nghiệp vụ thật sự liên domain, không thể tránh bằng cách sáp nhập tất cả vào một service. Nhưng có thể giảm coordination bằng:

- **Stable APIs và event contracts**.
- Ownership của workflow/orchestration.
- Backward-compatible schema changes.
- Consumer/provider contract tests.
- Tích hợp trong staging/test environments tự động.
- Versioned business events và idempotency.
- Một roadmap/architecture collaboration có thời hạn cho feature mới.

**Không có mục tiêu “mọi feature chỉ đổi một service” bằng mọi giá.** Một số business change vốn cần phối hợp. Điều cần giảm là **phối hợp phát sinh từ kiến trúc kém**, không phủ nhận domain boundaries thật.

## 43. Quan hệ giữa reliability và tải nhận thức

Microservices tăng số thành phần có thể lỗi độc lập. Khi một request đi qua nhiều services, on-call phải hiểu:

- Timeout và deadline budgets.
- Retry amplification.
- Circuit breaker state.
- Bulkhead/concurrency limits.
- Eventual consistency và duplicate events.
- DB failover và schema migrations.
- Network/TLS/IAM errors.
- Container scheduling/scaling.
- User-facing SLO và business correctness.

Nếu số lớp lỗi tăng nhưng telemetry/runbooks không phát triển tương ứng, team có thể mất thời gian chủ yếu trong điều tra.

### 43.1. Thiết kế giảm tải khi incident

- Trace context xuyên service.
- Service dependency graph có owner.
- Alert grouping theo root dependency/impact.
- Correlation giữa deployment và regression.
- Playbook cho top failure modes.
- Safe rollout/rollback.
- Bounded retries/idempotency.
- Consistent logs/errors.

### 43.2. Không dùng “một đội SRE sẽ lo” làm lối thoát

SRE/Platform có thể giúp infrastructure và reliability engineering, nhưng không thể thay hoàn toàn hiểu biết domain. Nếu chỉ SRE trực, còn service owners không bao giờ tham gia incident, chất lượng runbooks/ownership thường suy yếu.

Một mô hình hợp tác phải xác định trách nhiệm, escalation và quyền hành động.

## 44. Kiểm thử năng lực tổ chức bằng một feature thật

Chọn một thay đổi tương đối nhỏ nhưng có giá trị, ví dụ “hỗ trợ coupon mới cho checkout”.

Đo:

1. Từ lúc team hiểu yêu cầu đến lúc có thiết kế.
2. Số domain/service boundaries cần thay.
3. Số PRs/repos.
4. Số lần review/chờ group khác.
5. Số môi trường/contract dependencies để test.
6. Số lần deploy và release coordination.
7. Độ dễ rollback.
8. Error/latency SLI sau deploy.
9. Có tạo docs/runbooks/debt mới không?
10. Phản hồi nhóm về các bước khó hiểu.

Sau đó thử phương án cải tiến nhỏ nhất, ví dụ promotion module contract ổn định hoặc self-service deployment, và đo lại trên thay đổi tương tự. Đây là cách nối **cognitive load** với **flow** và **business outcome** mà không giả tạo một phép đo tâm lý chính xác.

## 45. Checklist trước khi tách microservice mới

### Business và architecture

- [ ] Có bounded context và responsibility thống nhất.
- [ ] Lợi ích từ deploy/scale/fault/security isolation rõ ràng.
- [ ] Đã so sánh với module/modular monolith và phương án cải tiến ít phân mảnh hơn.
- [ ] Không tách chỉ vì có bảng mới hoặc code lớn.
- [ ] Contract với consumers được xác định và có compatibility plan.
- [ ] Data SoR/write ownership rõ; không thêm writers chồng chéo.
- [ ] Chấp nhận được latency, consistency và failure modes khi tăng network hops.

### Tổ chức

- [ ] Có primary owner team chịu trách nhiệm lifecycle.
- [ ] Có kỹ năng code, test, deploy, observe và incident trong hoặc gần team.
- [ ] On-call/escalation và backup coverage phù hợp rủi ro.
- [ ] Service không biến mọi thay đổi thành handoff giữa nhiều nhóm.
- [ ] Platform có golden path hoặc có kế hoạch vận hành tối thiểu đủ chắc.
- [ ] Có capacity cho security patches, cost và data retention.
- [ ] Có ADR ghi giả thuyết lợi ích, chi phí và ngày xem lại.

### Kỹ thuật và vận hành

- [ ] CI/CD, automated tests, deploy/rollback có thể chạy độc lập.
- [ ] SLO, dashboards, structured logs, trace propagation và alerting.
- [ ] Readiness/liveness, graceful shutdown, timeouts, retries, idempotency.
- [ ] IAM/secrets, network policy, dependency patching.
- [ ] DB migration/backup/restore và event/contract versioning nếu có data.
- [ ] Local/CI component tests không phụ thuộc toàn hệ thống sống.
- [ ] Có runbook cho các lỗi phổ biến và service catalog/ownership.

### Cách đo hiệu quả

- [ ] Baseline lead time, blocked time, change coupling, incidents.
- [ ] Xác định outcome mong muốn và dữ liệu kiểm chứng.
- [ ] Đã tính chi phí deployables, on-call và hạ tầng bổ sung.
- [ ] Có review 30/60/90 ngày.
- [ ] Sẵn sàng gộp lại hoặc thay kiến trúc nếu giả thuyết tách không đúng.

## 46. Checklist giảm tải ở hệ thống đã phân mảnh

- [ ] Inventory service và primary owner, đánh dấu orphan services.
- [ ] Đếm/quan sát những contracts thay đổi đồng thời thường xuyên.
- [ ] Xác định top incident paths và missing runbooks.
- [ ] Lấy feedback định tính về context switches, không chấm cá nhân.
- [ ] Đo CI/local-test friction và manual deployments.
- [ ] Xác định stack/tool đa dạng không có lợi ích được chứng minh.
- [ ] Tách business complexity khỏi overhead nền tảng có thể tự động hóa.
- [ ] Đề xuất hợp nhất những helper/proxy services quá nhỏ.
- [ ] Giữ data ownership và backward compatibility khi hợp nhất.
- [ ] Xem lại on-call coverage và review thời gian xử lý toil.
- [ ] Dùng platform self-service thay ticket handoff.
- [ ] Dành capacity cho reliability và domain learning.
- [ ] Đo kết quả theo SLO, lead time, coordination và phản hồi nhóm sau cải tiến.

## 47. Bài tập tự luyện

### Bài A — Nhiều service có phải luôn quá tải?

Hai nhóm cùng có 5 kỹ sư:

- Nhóm A sở hữu 10 services trong một domain, cùng runtime, CI golden path, contracts ổn định và on-call ít sự cố.
- Nhóm B sở hữu 4 services thuộc bốn domain khác nhau, ba runtimes, mỗi deploy phải chờ platform và incidents lặp lại.

**Câu hỏi:** nhóm nào có cognitive load cao hơn?

**Hướng giải:** không thể biết chỉ từ số service. Nhóm B có dấu hiệu extraneous load và context switching mạnh, nhưng cần khảo sát, incident/lead time/ownership data. Đánh giá tải đa chiều.

### Bài B — Có nên tách OrderStatusService?

Mọi request tạo/hủy đơn đều cần OrderStatusService; mỗi thay đổi state machine của Order phải sửa cả hai services và deploy phối hợp. Cả hai cùng một owning team.

**Hướng giải:** kiểm tra vì sao cần deploy boundary. Nếu chỉ là tách logic trạng thái, có thể hợp nhất thành module trong Order Service để bảo toàn invariants và giảm synchronous hops.

### Bài C — Platform trở thành điểm nghẽn

Mọi team phải chờ 5 ngày để tạo test database dù công việc an toàn và lặp lại.

**Hướng giải:** xây self-service provision workflow có policy, quotas, audit; giảm ticket handoff. Đo thời gian request-to-ready trước/sau, giữ guardrails bảo mật.

### Bài D — Không có SoR

ProfileService và CustomerService đều cập nhật `customer.email`. Support báo lúc đúng lúc sai.

**Hướng giải:** chọn authoritative owner cho email, xác định API/event contracts, thu hồi quyền ghi chồng chéo và có reconciliation. Đây là vấn đề ownership, không giải quyết bằng thêm SyncService.

### Bài E — Phải đổi bảy services cho một feature

Một thay đổi pricing nhỏ cần sửa cùng field ở nhiều consumers vì API truyền DTO nội bộ không versioned.

**Hướng giải:** xem lại bounded context, public contract, backward-compatible schema và materialized read models; không nhất thiết hợp nhất bảy business domains.

### Bài F — On-call quá tải

Nhóm 6 người nhận 80 alerts/tuần nhưng chỉ 10 alerts cần hành động; mọi người phải trực ngoài giờ thường xuyên.

**Hướng giải:** đo actionability, gộp/downgrade noisy alerts, SLO-based paging, runbooks, fix recurring causes. Không kết luận “cần thêm service để chia tải”.

### Bài G — Product-market fit chưa ổn

Startup 4 kỹ sư thay đổi workflow onboarding mỗi tuần, chưa có CI/CD platform. Đội muốn tạo 12 microservices theo mỗi màn hình.

**Hướng giải:** cân nhắc modular monolith với module boundaries, tests và domain contracts; chỉ tách khi có nhu cầu scale/ownership thực tế và năng lực ops.

### Bài H — Team Topologies

Một stream team thường xuyên không biết cấu hình OpenTelemetry, nên enabling team phải viết dashboards cho họ suốt 2 năm.

**Hướng giải:** facilitating nên có kế hoạch chuyển giao kỹ năng; platform có thể cung cấp golden dashboards, team phải hiểu SLO/trace để vận hành. Tránh phụ thuộc chuyên gia vĩnh viễn.

### Bài I — Tách subsystem phức tạp

Công ty có fraud engine đòi nghiên cứu ML/rules và tuning rất chuyên sâu; checkout developers không đủ năng lực hiểu chi tiết nhưng cần kết quả đánh giá risk.

**Hướng giải:** complicated-subsystem team với API/contract rõ có thể giảm tổng tải. Tách đủ ranh giới domain và trách nhiệm, không cần tạo nhiều service theo từng model class.

### Bài J — Đo thành công sau khi hợp nhất

Gộp ba proxy microservices vào một module của Checkout. Số deployables giảm, nhưng vẫn phải sửa 5 repos cho mỗi promotion change.

**Hướng giải:** giảm deployables chưa chắc giảm semantic coupling. Cần kiểm tra contract boundaries, data ownership, workflow và handoffs; đo blocked time và change coupling sau cải tiến.

### Bài K — Số lượng deploy tăng nhưng user impact chậm

Nhóm tăng deployment frequency từ 5 lên 30 deploys/tuần sau khi tách service, nhưng lead time từ yêu cầu đến giao một feature tăng từ 8 lên 18 ngày.

**Hướng giải:** xem deployment frequency **cùng** useful outcome lead time, handoffs, cross-service changes, CI/contract failures. Đừng kết luận tốc độ delivery tăng chỉ vì deploy count tăng.

### Bài L — Một đội vận hành tài nguyên chung

Nhiều microservices dùng chung database, IAM và broker, nhưng không ai muốn sở hữu schema migration cross-domain.

**Hướng giải:** làm rõ logical data owner, platform custody, permissions và change contracts. Nếu chưa thể tách dữ liệu, ghi shared dependency và quy trình migration có owner thay vì giả định tách process đã tạo isolation.

## 48. Câu hỏi gợi mở cho một buổi architecture review

1. Những kiến thức nào mỗi developer phải hiểu để giao một thay đổi thông thường?
2. Phần kiến thức đó bao nhiêu là nghiệp vụ cốt lõi, bao nhiêu là setup/tools/handoffs?
3. Một team có thể xác định SLO impact từ service của mình tới người dùng không?
4. Chúng ta có bao nhiêu service không có người thực sự hiểu và trực on-call?
5. Một deploy có thực sự độc lập hay vẫn phải phát hành đồng thời?
6. Có những edge nào chỉ tồn tại vì tách một function thành HTTP call?
7. Database, identity và network shared dependencies đã được biểu diễn trong architecture chưa?
8. Có một service mới nào chỉ mang lại thêm pipeline và monitoring mà không cải thiện flow/fault isolation?
9. Tại sao một nhân viên mới mất thời gian để thực hiện thay đổi đầu tiên?
10. Nếu bỏ một layer/service, điều gì trở nên đơn giản hơn và rủi ro nào tăng?
11. Platform có cung cấp self-service hay chủ yếu nhận tickets?
12. Các business decisions đang được sở hữu bởi bounded context nào?
13. Công việc giảm tải có nằm trong roadmap và được tính capacity không?
14. Khi nào chúng ta sẽ chủ động hợp nhất những boundaries không còn cần thiết?
15. Các số liệu nào sẽ làm ta thay đổi ý định về kiến trúc đã chọn?

## 49. Những hiểu lầm cần tránh

**“Microservices càng nhỏ càng chuẩn.”**  
Không có kích cỡ tối ưu độc lập với domain, runtime và organization. Một boundary mới luôn có chi phí.

**“Mỗi team chỉ nên sở hữu tối đa X services.”**  
Ngưỡng cố định không phản ánh độ phức tạp vận hành, kỹ năng và platform maturity.

**“Chia service sẽ chia tải nhận thức.”**  
Chỉ đúng khi quyền sở hữu, business boundaries và dependencies giúp mỗi team hiểu ít hơn mà không tăng coordination quá mức.

**“Một team chỉ chịu trách nhiệm code, platform lo mọi thứ khác.”**  
Nếu không rõ ownership của SLO, data và incident, tự chủ vẫn thấp.

**“Cognitive load có thể đo chính xác bằng số ticket/điểm survey.”**  
Các chỉ số chỉ là proxy. Cần phỏng vấn và quan sát hành vi, không chấm tâm lý cá nhân.

**“Service nhỏ nên incident nhỏ.”**  
Một helper service nằm trên critical path hoặc một shared database có thể gây outage toàn hệ thống.

**“Event-driven luôn giảm coupling.”**  
Giảm synchronous dependency nhưng tăng event schema, ordering, dedup và observability requirements.

**“Modular monolith là thất bại.”**  
Một deployable với module boundaries tốt có thể có ít overhead và delivery nhanh hơn microservices trong nhiều bối cảnh.

**“Platform team càng nhiều quyền càng tốt.”**  
Platform gate tập trung có thể trở thành queue, làm flow chậm. Tự phục vụ và guardrails quan trọng hơn quyền kiểm soát thủ công.

**“DORA metrics đánh giá năng suất cá nhân.”**  
Các chỉ số flow/reliability có ý nghĩa ở mức hệ thống/nhóm khi hiểu ngữ cảnh; lạm dụng để xếp hạng cá nhân gây méo hành vi.

**“Giảm service count là đủ.”**  
Nếu vẫn không rõ data ownership và boundaries, gộp deployables chỉ đổi hình thức coupling.

## 50. Tổng kết

**Tải nhận thức là giới hạn thực tế của kiến trúc**, không phải vấn đề riêng của từng kỹ sư. Khi thêm microservice, ta thêm khả năng triển khai/scale/cách ly độc lập **nếu** có boundary nghiệp vụ tốt, owner đủ năng lực và nền tảng hỗ trợ. Nếu các điều kiện đó thiếu, ta thường chỉ thêm network hops, contracts, pipelines, data consistency issues và gánh nặng on-call.

Để tránh phân rã vượt năng lực tổ chức:

1. **Đo thực tế:** khảo sát có tâm lý an toàn, change coupling, handoff/blocked time, on-call toil, SLO và developer experience.
2. **Thiết kế quanh domain:** bounded contexts, source of truth, owner và contracts; không chia theo CRUD/class.
3. **Giảm extraneous load:** platform golden paths, self-service, chuẩn hóa runtime/observability, test automation và runbooks.
4. **Giữ đúng mức phân rã:** modular monolith khi còn hợp lý; tách khi lợi ích deploy/scale/fault/security isolation có thể chứng minh; hợp nhất khi boundary không còn giá trị.
5. **Tái đánh giá liên tục:** dùng ADR, dữ liệu production, phản hồi đội ngũ và review sau thay đổi.

Một kiến trúc tốt là kiến trúc giúp **những nhóm hiện có hiểu đủ phần họ chịu trách nhiệm, đưa thay đổi có giá trị tới khách hàng an toàn, phục hồi sự cố có kiểm soát và còn năng lực học hỏi, cải thiện hệ thống** — không phải kiến trúc đạt số microservice lớn nhất.
