# Tối ưu số lượng dịch vụ thay vì khả năng thay đổi và giá trị sản phẩm

Một hệ thống microservices trưởng thành không được đánh giá bằng số lượng service, số repository hay số container đang chạy. Những con số đó chỉ mô tả cách triển khai. Giá trị kiến trúc nằm ở việc tổ chức có thể **thay đổi sản phẩm an toàn, nhanh và có kiểm soát**, đưa kết quả tới người dùng, học từ dữ liệu thực tế và vận hành hệ thống với chi phí hợp lý hay không.

Khi tổ chức đặt mục tiêu “tách thêm microservice” hoặc “tăng số service độc lập”, nhóm kỹ thuật dễ tối ưu một chỉ số có thể đếm thay vì mục tiêu thật. Một capability có thể bị chia thành nhiều service nhỏ, nhưng mọi thay đổi vẫn phải sửa nhiều nơi, deploy theo một lịch chung, chờ nhiều nhóm review và điều tra incident qua nhiều boundary. Ngược lại, một modular monolith có module boundary tốt đôi khi cho phép một nhóm phát hành tính năng nhanh hơn và an toàn hơn một hệ thống phân tán gồm hàng chục service.

Bài học này phân tích cách đánh giá kiến trúc theo **khả năng thay đổi và giá trị sản phẩm**, cách lựa chọn mức phân tán phù hợp, cách đo kết quả delivery/reliability, và cách tiến hóa kiến trúc dựa trên bằng chứng. Mục tiêu không phải giảm hay tăng số service theo một công thức, mà là chọn cấu trúc giúp tổ chức tạo ra kết quả tốt nhất trong điều kiện nhân lực, domain, rủi ro và vận hành thực tế.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vì sao số lượng microservice không phải chỉ số trực tiếp của chất lượng kiến trúc.
- Phân biệt output kỹ thuật (service, repository, deployment) với outcome sản phẩm (conversion, task completion, correctness, satisfaction).
- Đánh giá khả năng thay đổi qua lead time, deployment independence, change failure rate, recovery time và coordination cost.
- Phân tích trade-off giữa modular monolith, service-oriented architecture và microservices.
- Nhận diện dấu hiệu kiến trúc bị tối ưu theo số lượng service thay vì nhu cầu sản phẩm.
- Xác định bounded context, ownership, data boundary và contract theo hành vi nghiệp vụ.
- Thiết kế chỉ số cân bằng delivery, reliability, user experience, security và cost.
- Dùng thử nghiệm sản phẩm, telemetry và phản hồi người dùng để kiểm chứng quyết định kiến trúc.
- Lập lộ trình tiến hóa từ monolith hoặc distributed monolith sang cấu trúc phù hợp hơn.
- Tránh các thay đổi kiến trúc lớn chỉ dựa trên xu hướng, vanity metrics hoặc sơ đồ tổ chức.

## 2. Output kỹ thuật và outcome sản phẩm

**Output** là thứ nhóm tạo ra hoặc triển khai. **Outcome** là thay đổi có ý nghĩa xảy ra với người dùng hoặc doanh nghiệp.

| Output kỹ thuật | Outcome cần quan tâm |
|---|---|
| Tạo thêm 5 microservices | Người dùng hoàn thành hành trình nhanh và ít lỗi hơn |
| Tách một database | Thay đổi dữ liệu có owner rõ, giảm sự cố và rủi ro migration |
| Tạo thêm một API gateway | Người dùng có truy cập ổn định, an toàn và đúng quyền |
| Viết một platform SDK | Developer tự phục vụ tốt hơn, giảm thời gian onboarding |
| Chuyển sang event-driven | Workflow chịu được dependency outage và cập nhật đúng |
| Tăng deployment frequency | Tính năng có giá trị đến người dùng sớm hơn, không tăng lỗi |
| Tạo nhiều dashboard | Nhóm phát hiện và xử lý tác động nhanh hơn |
| Tăng số team chuyên trách | Quyết định rõ hơn, giảm thời gian chờ và ownership gap |

Số lượng service có thể hữu ích như một dữ liệu inventory, nhưng không trả lời được liệu tổ chức có đang thay đổi tốt hơn hay không. Một service mới chỉ tạo ra giá trị khi nó giải quyết một nhu cầu thực: ownership độc lập, scale khác biệt, failure isolation, security boundary hoặc tốc độ thay đổi.

### 2.1. Ví dụ về hai kiến trúc

**Kiến trúc A:** 40 microservices, 12 team. Một thay đổi checkout cần 6 team, 4 contract reviews và 3 lịch deploy. Thời gian từ yêu cầu tới production là 3 tuần. Incident thường mất nhiều thời gian xác định owner.

**Kiến trúc B:** 8 service theo bounded context, một số module vẫn nằm trong modular monolith. Checkout team có thể triển khai phần lớn thay đổi trong 2 ngày, với contract test và canary. SLO và business outcome được đo đầu-cuối.

Kiến trúc B có ít service hơn nhưng có thể tạo ra giá trị tốt hơn. Ngược lại, nếu một service trong B cần scale gấp 20 lần các module khác hoặc có security boundary riêng, tách nó có thể là quyết định đúng. Không thể kết luận chỉ từ số lượng.

## 3. Khả năng thay đổi là một thuộc tính của cả hệ thống

Một team có thể sửa code rất nhanh nhưng vẫn mất nhiều ngày để release do phải chờ consumer, database migration, platform ticket hoặc approval. Vì vậy, khả năng thay đổi cần nhìn xuyên suốt:

~~~text
Nhu cầu / giả thuyết sản phẩm
          |
          v
Thiết kế và quyết định
          |
          v
Code + test + contract
          |
          v
Build + security checks
          |
          v
Deploy + rollout
          |
          v
Quan sát user outcome
          |
          v
Học hỏi / điều chỉnh
~~~

Một kiến trúc hỗ trợ thay đổi khi:

- Phần lớn thay đổi có thể nằm trong một bounded context hoặc một nhóm owner.
- Contract ổn định và consumer không cần deploy cùng lúc cho thay đổi tương thích.
- Data ownership rõ, migration có thể tiến hành theo từng giai đoạn.
- Có test tự động cho boundary và invariant quan trọng.
- Team có quyền deploy, rollback và quan sát service của mình trong guardrails.
- Failure behavior được xác định, không tạo một chuỗi retry hoặc network call không kiểm soát.
- Nhóm có thể thử nghiệm với cohort nhỏ, đo tác động và dừng thay đổi khi cần.

**Deployment độc lập không có nghĩa không cần phối hợp.** Các thay đổi về business contract, dữ liệu dùng chung, security hoặc nghĩa vụ pháp lý vẫn cần review. Mục tiêu là giảm những lần đồng bộ bắt buộc không tạo thêm giá trị.

## 4. Vì sao số lượng service trở thành vanity metric?

Một chỉ số trở thành vanity metric khi nó dễ trình bày nhưng không phản ánh kết quả mà tổ chức cần đạt.

Các ví dụ:

- “Tăng từ 20 lên 50 services” không chứng minh lead time giảm.
- “Mỗi team có 10 microservices” không chứng minh ownership rõ.
- “100% service dùng Kubernetes” không chứng minh sản phẩm đáng tin hơn.
- “Mọi service đều có API riêng” không chứng minh contract có thể thay đổi độc lập.
- “Tất cả module đã tách repository” không chứng minh deployment boundary hợp lý.

Khi số service được dùng làm KPI, tổ chức có thể vô tình khuyến khích:

1. Tách một module nhỏ thành service dù không có nhu cầu vận hành độc lập.
2. Tạo API chỉ để truy cập một bảng database.
3. Chia controller, business logic và repository thành các process riêng.
4. Tạo team và on-call mới trước khi có đủ workload.
5. Đẩy complexity sang platform, CI/CD, observability và incident response.
6. Đo thành công bằng sơ đồ kiến trúc đẹp thay vì kết quả người dùng.

Một mục tiêu kiến trúc tốt cần mô tả vấn đề sản phẩm hoặc vận hành cần giải quyết, không đặt số lượng service như kết quả cuối.

## 5. Bắt đầu từ giá trị sản phẩm

Trước khi tách service hoặc thay đổi kiến trúc, hãy xác định hành trình người dùng và outcome mong muốn.

Ví dụ checkout:

- Người mua có thể hoàn tất đơn trong thời gian hợp lý.
- Giá, thuế và phí hiển thị đúng.
- Payment không bị charge trùng.
- Inventory không bị oversell.
- Trạng thái đơn rõ ràng kể cả khi dependency timeout.
- Người dùng nhận thông báo đúng và có thể tra cứu đơn.
- Khi một phần degraded, phần còn lại có behavior an toàn.

Những outcome này giúp định hướng kiến trúc. Nếu vấn đề là payment timeout làm người dùng không biết đã bị trừ tiền hay chưa, tạo thêm một API service không tự giải quyết. Cần idempotency, unknown-outcome handling, reconciliation, telemetry và trải nghiệm Pending rõ ràng.

### 5.1. North Star metric và guardrail metrics

Một sản phẩm có thể chọn một North Star metric phản ánh giá trị cốt lõi, nhưng phải có các guardrails để tránh tối ưu một chiều.

Ví dụ:

| Metric | Mục đích |
|---|---|
| Completed checkout per eligible user | Đo kết quả hành trình chính |
| Payment duplicate rate | Bảo vệ tính đúng của giao dịch |
| Checkout p95 latency | Bảo vệ trải nghiệm tốc độ |
| Inventory oversell incidents | Bảo vệ cam kết tồn kho |
| Refund/support contact rate | Phát hiện tác động sau giao dịch |
| Service availability/SLO | Bảo vệ khả năng phục vụ |
| Cost per completed order | Theo dõi hiệu quả vận hành |
| Change failure rate | Theo dõi rủi ro delivery |

Không dùng một North Star metric để che các lỗi nghiêm trọng. Tăng conversion bằng cách giảm bước xác nhận có thể làm tăng charge sai; vì vậy correctness và safety phải là guardrail cứng.

## 6. Kiến trúc cần hỗ trợ vòng học hỏi sản phẩm

Một nhóm cần có khả năng đưa giả thuyết ra production trong phạm vi nhỏ, quan sát outcome và điều chỉnh.

~~~text
Giả thuyết:
  "Rút gọn bước xác nhận địa chỉ sẽ tăng checkout completion"

        |
        v
Thiết kế thay đổi trong Checkout boundary
        |
        v
Feature flag / experiment cohort
        |
        v
Canary hoặc A/B test có kiểm soát
        |
        v
Đo conversion + latency + correctness + support
        |
        v
Quyết định: giữ / điều chỉnh / rollback
~~~

Nếu một thay đổi nhỏ phải chờ 5 team triển khai đồng thời, tổ chức mất khả năng thử nghiệm nhanh. Nếu tách quá nhiều service nhưng mỗi service có pipeline và release overhead riêng, thử nghiệm cũng có thể chậm hơn.

Kiến trúc tốt cho product discovery giúp:

- Thay đổi behavior trong phạm vi nhỏ.
- Giữ compatibility với phần còn lại.
- Tách thử nghiệm khỏi rollout toàn bộ người dùng.
- Có telemetry để đo kết quả.
- Rollback nhanh và có thể khôi phục dữ liệu.
- Ghi lại version/config để hiểu cohort đã trải nghiệm điều gì.

## 7. Chọn ranh giới theo khả năng thay đổi và bounded context

Bounded context là phạm vi trong đó mô hình và ngôn ngữ nghiệp vụ có ý nghĩa nhất quán. Đây thường là điểm xuất phát tốt để xác định ownership.

Ví dụ:

| Bounded context | Thay đổi thường gặp |
|---|---|
| Catalog | Thuộc tính, phân loại, trạng thái xuất bản |
| Pricing | Quote, promotion, tax/fee policy |
| Cart | Lựa chọn tạm thời, merge cart |
| Order | Lifecycle đơn, item snapshot, cancel/confirm |
| Payment | Authorization, capture, refund, ledger |
| Inventory | Reservation, allocation, stock |
| Shipping | Shipment, carrier, tracking |
| Notification | Consent, template, delivery status |

Không cần tạo một service cho mỗi context ngay lập tức. Có thể bắt đầu bằng module trong cùng deployable nếu domain còn thay đổi hoặc team chưa cần scale/release riêng.

Một context xứng đáng có service riêng khi có lý do như:

- Thay đổi độc lập và thường xuyên.
- Scale profile khác biệt.
- Failure isolation quan trọng.
- Security/data access boundary riêng.
- Owner và năng lực vận hành đủ.
- Contract đủ ổn định.
- Lợi ích độc lập lớn hơn distributed systems overhead.

## 8. Modular monolith, service-oriented và microservices

Ba lựa chọn không phải cuộc thi trưởng thành. Chúng là các cấu trúc có trade-off khác nhau.

| Tiêu chí | Modular monolith | Service-oriented architecture | Microservices |
|---|---|---|---|
| Deployment | Một hoặc ít deployables | Một số service lớn | Nhiều service nhỏ theo capability |
| Module boundary | Nội bộ, có thể được enforce | Giữa các service | Giữa các service độc lập |
| Network overhead | Thấp trong nội bộ | Có | Có, thường nhiều hơn |
| Transaction | Dễ giữ trong một DB boundary | Phân tán theo service | Phân tán theo service |
| Scaling | Thường theo deployable | Theo service | Theo service |
| Operational complexity | Thấp hơn | Trung bình | Cao hơn |
| Release independence | Theo module/deployable | Một phần | Có thể cao nếu contract tốt |
| Team ownership | Một/vài team | Theo subsystem | Theo capability/domain |
| Phù hợp khi | Domain còn ổn định/chưa cần phân tán | Có vài subsystem độc lập | Nhiều capability cần độc lập thực sự |

Một modular monolith có thể có module boundary nghiêm ngặt, architecture tests và data ownership rõ. Nó có thể là bước tiến tốt hơn một tập hợp microservices không có contract.

### 8.1. Không có kiến trúc cuối cùng

Sản phẩm, tổ chức và workload thay đổi. Một modular monolith có thể tiến hóa thành vài service khi có nhu cầu; một hệ thống có quá nhiều service có thể hợp nhất một số thành phần. Kiến trúc nên được xem như một lựa chọn có thể điều chỉnh, không phải một lần quyết định bất biến.

## 9. Đánh giá bằng change scenarios

Một cách thực tế để kiểm tra kiến trúc là lấy các thay đổi gần đây và hỏi chúng đi qua bao nhiêu ranh giới.

Ví dụ thay đổi “thêm trạng thái giao hàng cho đơn”:

- Team nào phải sửa code?
- Có bao nhiêu repository?
- Có bao nhiêu contract?
- Có bao nhiêu database schema?
- Có bao nhiêu consumer?
- Có cần deploy đồng thời không?
- Cần bao nhiêu approval?
- Bao nhiêu ngày chờ?
- Có thể rollback riêng không?
- Có thể đo outcome sau rollout không?

Nếu một thay đổi thông thường liên tục chạm 8 service và 5 team, có thể ranh giới chưa phản ánh domain hoặc contract chưa đủ ổn định.

Không phải mọi cross-service change đều xấu. Một capability mới thực sự xuyên Order, Payment và Inventory cần phối hợp. Điều cần giảm là số boundary bị chạm bởi những thay đổi nội bộ đáng lẽ chỉ thuộc một owner.

## 10. Metrics đo khả năng thay đổi

Các metric delivery có thể giúp hiểu hệ thống làm việc:

| Metric | Ý nghĩa | Câu hỏi cần đặt |
|---|---|---|
| Lead time for change | Thời gian từ bắt đầu tới production | Chờ ở bước nào? |
| Deployment frequency | Tần suất triển khai | Deploy có giá trị hay chỉ chia nhỏ? |
| Change failure rate | Tỷ lệ thay đổi gây sự cố/rollback | Guardrails có đủ? |
| Time to restore service | Thời gian khôi phục sau incident | Rollback/mitigation có dễ? |
| Coordinated release rate | Tỷ lệ thay đổi cần nhiều service deploy chung | Contract có thiếu compatibility? |
| Handoff count | Số lần chuyển trách nhiệm | Có thể tự phục vụ không? |
| Wait time | Thời gian chờ review/approval/dependency | Bottleneck nằm ở đâu? |
| Rework rate | Công việc phải làm lại do thiếu thông tin/contract | Discovery và testing có vấn đề? |
| Time to identify owner | Thời gian tìm đúng responder | Ownership metadata có chính xác? |

Các chỉ số như lead time, deployment frequency, change failure rate và time to restore thường được dùng trong nhóm DORA metrics. Cần dùng theo xu hướng của team/service và kết hợp với outcome sản phẩm; không dùng để xếp hạng cá nhân hoặc so sánh máy móc những hệ thống có rủi ro khác nhau.

### 10.1. Phân rã lead time

Giả sử một feature mất 12 ngày:

~~~text
Thiết kế và code                3 ngày
Chờ contract review             2 ngày
Chờ consumer team               3 ngày
Chờ platform provisioning       2 ngày
Canary và quan sát              1 ngày
Điều chỉnh sau feedback         1 ngày
Tổng                           12 ngày
~~~

Nếu chỉ tối ưu code từ 3 ngày xuống 2 ngày, tổng lead time chỉ giảm một ngày. Cần xử lý các điểm chờ có thể loại bỏ bằng contract tests, self-service và release compatibility.

### 10.2. Deployment frequency không phải mục tiêu độc lập

Tăng deploy frequency có thể giúp giảm batch size và feedback delay. Nhưng deploy nhiều hơn mà không có user outcome, hoặc tăng incident rate, không phải cải thiện.

Hãy hỏi:

- Thay đổi có tạo giá trị hoặc giảm rủi ro không?
- Có thể deploy nhỏ và rollback không?
- SLO có giữ ổn định?
- Có đo được outcome?
- Có tạo thêm overhead vận hành không cần thiết?

## 11. Metrics đo giá trị sản phẩm

Architecture work cần liên kết với outcome cụ thể:

- Tỷ lệ người dùng hoàn thành nhiệm vụ.
- Thời gian hoàn thành một workflow.
- Tỷ lệ thao tác thành công lần đầu.
- Số lỗi cần support.
- Tỷ lệ giao dịch cần reconciliation.
- Tính chính xác dữ liệu và số vi phạm invariant.
- Mức độ hài lòng hoặc phản hồi khách hàng.
- Chi phí trên một đơn vị giá trị hoàn thành.

Ví dụ, thay vì báo “đã tách Payment thành 3 service”, hãy báo:

- Tỷ lệ payment timeout giảm.
- Duplicate charge không tăng.
- Thời gian đưa provider integration mới vào production giảm.
- Rollback payment adapter không cần deploy Order.
- Cost per successful payment không vượt ngưỡng.

Nếu không có outcome nào thay đổi, cần xem lại liệu việc tách service có thực sự giải quyết vấn đề.

## 12. Metrics reliability và correctness

Availability không đủ để mô tả chất lượng. Một API có thể trả HTTP 200 nhưng ghi sai giá hoặc tạo payment trùng.

Nên có nhiều lớp đo:

| Lớp | Ví dụ |
|---|---|
| Availability | Request hợp lệ được phục vụ |
| Latency | p50/p95/p99 của user journey |
| Correctness | Kết quả nghiệp vụ đúng, không duplicate |
| Freshness | Read model cập nhật trong ngưỡng |
| Durability | Giao dịch đã xác nhận không bị mất |
| Consistency | Các trạng thái liên quan không vi phạm invariant |
| Security | Không có truy cập trái phép hoặc secret exposure |
| Recoverability | Backup/restore và failover đã được kiểm chứng |

Với Payment, correctness có thể quan trọng hơn một số điểm phần trăm availability. Với Search, stale index vài giây có thể chấp nhận; với inventory reservation, oversell có thể không chấp nhận. SLO và guardrail phải phù hợp domain.

## 13. Chi phí vòng đời kiến trúc

Mỗi service mới tạo ra một phần chi phí thường xuyên:

- Repository/build/dependency management.
- Pipeline, artifact và deployment configuration.
- Runtime, network, DNS và certificates.
- Logs, metrics, traces, alert và dashboard.
- Secrets, IAM, vulnerability patching.
- Backup, recovery và disaster recovery.
- On-call, runbook và incident routing.
- API/event versioning và compatibility.
- Capacity, scaling và cost allocation.
- Onboarding và cognitive load.

Có thể dùng mô hình khái niệm:

~~~text
Total lifecycle cost =
  feature delivery cost
  + runtime/platform cost
  + coordination cost
  + reliability and incident cost
  + security/compliance cost
  + migration and compatibility cost
  + cognitive load
~~~

Tách service có thể giảm coupling code nhưng tăng network, observability và on-call cost. Hãy so sánh tổng chi phí theo vòng đời, không chỉ chi phí triển khai ban đầu.

### 13.1. Cost per outcome

Một metric hữu ích có thể là cost per completed order hoặc cost per successful payment. Nhưng phải hiểu thành phần chi phí:

- Compute/database/storage.
- Broker và network.
- Observability.
- Support/on-call.
- Provider fees.
- Incident/recovery.
- Engineering time cho maintenance.

Đừng tối ưu chi phí bằng cách giảm redundancy hoặc observability đến mức SLO bị vi phạm. Chi phí thấp hơn nhưng thiệt hại user cao hơn không phải tối ưu.

## 14. Architecture decision record nên bắt đầu từ vấn đề

Một ADR không nên chỉ ghi “chúng ta chuyển sang microservices”. Nó nên nêu:

~~~markdown
# ADR: Tách Inventory khỏi Commerce Application

## Context
- Stock reservation cần scale khác checkout.
- Các thay đổi allocation thường do nhóm Inventory thực hiện.
- Hiện tại thay đổi Inventory buộc deploy toàn ứng dụng.

## Problem
- Lead time của thay đổi Inventory cao.
- Một lỗi indexing làm ảnh hưởng API checkout.

## Options
- Giữ module trong modular monolith.
- Tách deployment nhưng dùng cùng database.
- Tách Inventory Service và data ownership.

## Decision
- Chọn phương án...
- Phạm vi và lý do...

## Consequences
- Contract, consistency, SLO, cost và on-call mới.
- Migration/rollback strategy.
- Tiêu chí kiểm chứng sau 90 ngày.
~~~

ADR giúp phân biệt mục tiêu và phương án. Nó cũng cho phép tổ chức xem lại quyết định khi giả định ban đầu thay đổi.

## 15. Thực hiện kiến trúc theo giả thuyết có thể kiểm chứng

Một quyết định tách service có thể được viết như một giả thuyết:

> Nếu tách Inventory thành một capability có owner và data boundary riêng, team Inventory sẽ phát hành thay đổi reservation độc lập, giảm lead time từ 10 ngày xuống 4 ngày mà không làm tăng oversell, incident hoặc cost vượt ngưỡng.

Từ giả thuyết này, xác định:

- Baseline hiện tại.
- Scope và consumer bị ảnh hưởng.
- Metric delivery.
- Metric correctness/reliability.
- Cost guardrails.
- Thời gian đánh giá.
- Điều kiện rollback hoặc dừng mở rộng.
- Owner chịu trách nhiệm.

Nếu sau thời gian thử nghiệm, lead time không giảm vì vẫn phải deploy Checkout và Order cùng lúc, có thể ranh giới contract chưa đúng hoặc việc tách không mang lại giá trị.

## 16. Experiment và canary cho thay đổi kiến trúc

Một thay đổi kiến trúc không phải lúc nào cũng có thể A/B test như UI, nhưng vẫn có thể rollout theo từng giai đoạn:

~~~text
Phase 0: Shadow/read-only validation
Phase 1: Internal users / synthetic traffic
Phase 2: Small cohort or one region
Phase 3: Expand traffic if guardrails pass
Phase 4: Full adoption
Phase 5: Remove old path after migration window
~~~

Theo dõi:

- User outcome.
- Error/latency.
- Data divergence.
- Queue lag.
- Cost/capacity.
- Rollback success.
- Dependency errors.
- Team coordination overhead.

Một canary cần có stop condition. Ví dụ nếu payment duplicate count tăng dù conversion tốt hơn, phải dừng rollout. Không chờ đủ thời gian experiment nếu guardrail quan trọng đã bị vi phạm.

## 17. Feature flags và kiến trúc có thể tiến hóa

Feature flag có thể giúp thay implementation theo từng cohort mà không cần deploy lại, nhưng flag cũng tạo nợ:

- Owner và mục đích rõ.
- Giá trị mặc định an toàn.
- Audit và quyền thay đổi.
- Cách xử lý khi flag service unavailable.
- Ngày review/expire.
- Xóa flag sau khi migration hoàn tất.
- Không dùng flag thay cho authorization/security control.

Ví dụ chuyển từ LegacyOrderAdapter sang OrderService:

~~~text
Order request
    |
    v
Feature routing
    +-- cohort A --> Legacy path
    +-- cohort B --> New Order Service
~~~

Cần đảm bảo một request không bị ghi vào cả hai path ngoài ý muốn. Nếu có shadow comparison, path phụ nên read-only hoặc không tạo side effect.

## 18. Khi modular monolith tạo giá trị tốt hơn

Modular monolith có thể là lựa chọn tốt khi:

- Một team hoặc vài team gần nhau sở hữu domain.
- Domain boundary chưa ổn định.
- Nhiều thao tác cần transaction nội bộ.
- Các module có cùng scale và release cadence.
- Hệ thống chưa có năng lực vận hành nhiều service.
- Team đang mất nhiều thời gian quản lý pipeline và dependency.
- Lợi ích deploy độc lập chưa được chứng minh.

Một cấu trúc module có thể:

~~~text
commerce-app
  catalog/
    api/
    application/
    domain/
    infrastructure/
  order/
    api/
    application/
    domain/
    infrastructure/
  payment/
    api/
    application/
    domain/
    infrastructure/
~~~

Có thể enforce dependency bằng Java modules, Gradle modules hoặc ArchUnit. Mỗi module nên có API nội bộ rõ và không truy cập repository/private entity của module khác.

### 18.1. Modular monolith không phải “để mọi thứ chung một đống”

Nếu mọi module cùng ghi bảng, import class tùy ý và phụ thuộc vòng, monolith vẫn khó thay đổi. Cần module boundary, data ownership và contract nội bộ. Có thể giữ một deployable nhưng vẫn tổ chức theo capability.

## 19. Khi microservices tạo giá trị tốt hơn

Tách service có thể hợp lý khi:

- Một capability cần scale độc lập đáng kể.
- Một team cần release thường xuyên mà không chờ domain khác.
- Có security/compliance boundary riêng.
- Failure isolation giúp giảm blast radius.
- Workload hoặc runtime khác biệt.
- Dữ liệu và invariant có thể sở hữu riêng.
- Contract ổn định và consumer có thể nâng độc lập.
- Tổ chức có năng lực CI/CD, observability, on-call và recovery.

Một quyết định tốt có thể là tách Inventory vì concurrency và allocation có yêu cầu khác Checkout; không phải vì Inventory có một bảng riêng.

### 19.1. Chi phí phải được chấp nhận có ý thức

Khi tách, phải bổ sung:

- Network timeout/deadline.
- Retry/idempotency.
- Authentication/authorization.
- API/event versioning.
- Data consistency/reconciliation.
- SLO/dependency budgets.
- Deployment, rollback và migration.
- Dashboard, alert, runbook và on-call.
- Backup/restore và incident response.

Nếu chưa sẵn sàng cho các yêu cầu này, tách runtime có thể làm hệ thống kém tin cậy hơn.

## 20. Anti-pattern: tách service để làm đẹp sơ đồ

Dấu hiệu:

- Proposal chỉ nêu “đưa theo microservices best practice”.
- Không có vấn đề sản phẩm hoặc vận hành cụ thể.
- Không có baseline lead time/SLO/cost.
- Không có owner mới hoặc on-call.
- Không có data ownership và contract.
- Chỉ đổi repository và deployment unit.
- Mọi service vẫn phải release đồng thời.
- Không có tiêu chí đánh giá sau triển khai.

Cách sửa: viết problem statement, giả thuyết, baseline, trade-off, owner và success metrics trước khi thực hiện. Nếu chưa xác định được outcome, có thể chưa cần thay đổi kiến trúc.

## 21. Anti-pattern: tối ưu deployment frequency bằng cách chia nhỏ giả tạo

Một tổ chức có thể tăng số deployment bằng cách tách một thay đổi thành nhiều service deploy nhưng user outcome không đổi. Điều này có thể làm metric đẹp hơn trong khi:

- Số pipeline tăng.
- Số lần rollout và alert tăng.
- Coordination cost tăng.
- Rollback phức tạp.
- Consumer version skew nhiều hơn.

Deployment frequency nên được đọc cùng lead time, change failure rate, restore time, user outcome và cost. Tần suất cao chỉ có ý nghĩa khi thay đổi nhỏ, an toàn và có feedback tốt.

## 22. Anti-pattern: giảm lead time bằng cách bỏ review

Nếu chờ review lâu, phản ứng sai là bỏ mọi review. Cần phân biệt:

- Review có giá trị: security, data loss, breaking contract, financial correctness.
- Review có thể tự động: formatting, static analysis, schema compatibility, policy checks.
- Review do thiếu owner: cần catalog/escalation rõ.
- Review do quá nhiều approval: cần delegated authority trong guardrails.

Mục tiêu là **giảm thời gian chờ mà vẫn giữ kiểm soát cần thiết**, không đánh đổi correctness để làm nhanh.

## 23. Anti-pattern: tách database nhưng không tách ownership

Tách mỗi service có database riêng trên sơ đồ nhưng mọi service vẫn đọc/ghi schema của nhau không tạo data independence. Cần:

- Logical owner rõ.
- Quyền ghi chỉ thuộc owner.
- Consumer qua API/event/read model.
- Migration theo contract.
- Reconciliation cho dữ liệu sao chép.
- Backup/retention theo trách nhiệm.

Database per service là một nguyên tắc về ownership và coupling, không nhất thiết là một server vật lý riêng cho mỗi service.

## 24. Anti-pattern: platform hóa mọi thứ

Platform có thể cung cấp runtime, CI/CD, observability, secrets và policy engine. Nhưng nếu mọi business rule được đưa vào shared platform library, platform trở thành bottleneck và domain ownership mờ.

Ví dụ discount policy, refund eligibility và inventory allocation không nên nằm trong một common starter chỉ vì nhiều service cần chúng. Platform nên cung cấp mechanism; domain team sở hữu policy và semantics.

## 25. Anti-pattern: chỉ đo số liệu hạ tầng

CPU, memory, pod count, request count và deployment count là tín hiệu kỹ thuật. Chúng không tự chứng minh sản phẩm tốt.

Cần liên kết:

~~~text
Infrastructure signals
  CPU, memory, queue, DB, network
             |
             v
Service behavior
  errors, latency, saturation
             |
             v
User journey
  success, correctness, completion time
             |
             v
Product/business outcome
  conversion, retention, support, cost/value
~~~

Một cluster khỏe nhưng payment status sai vẫn là thất bại. Một API latency tốt nhưng người dùng phải gọi support để xác nhận đơn cũng là vấn đề sản phẩm.

## 26. Product team và architecture cùng ra quyết định

Kiến trúc không nên chỉ là quyết định của một nhóm platform hoặc architect. Product, domain owner, engineering và reliability cần cùng xác định:

- User problem cần giải quyết.
- Hành vi nào phải thay đổi.
- Mức rủi ro chấp nhận được.
- Data correctness và compliance constraints.
- Release/rollout strategy.
- Outcome và guardrails cần đo.
- Chi phí vận hành dài hạn.
- Những giả định có thể kiểm chứng.

Product không nhất thiết quyết định database engine hay broker partition strategy; kỹ thuật không nên tự quyết giảm một bước xác nhận thanh toán mà không hiểu tác động conversion/fraud. Cần đúng người quyết định đúng phần.

## 27. Team topology ảnh hưởng trực tiếp khả năng thay đổi

Nếu một thay đổi cần nhiều team vì mỗi team sở hữu một layer kỹ thuật, lead time sẽ tăng. Tổ chức theo stream-aligned/domain teams giúp nhóm sở hữu luồng giá trị gần người dùng hơn.

Ví dụ:

- Checkout Team sở hữu orchestration và user journey.
- Payment Team sở hữu payment lifecycle và ledger.
- Inventory Team sở hữu reservation/stock.
- Platform Team cung cấp runtime, deployment, observability và self-service.
- SRE/Security hỗ trợ chuyên môn và guardrails.

Không cần một team cho mỗi service. Một team có thể sở hữu nhiều service liên quan nếu cognitive load và on-call vẫn bền vững. Mục tiêu là giảm phụ thuộc bắt buộc, không tối đa hóa số team.

## 28. Ownership phải đi cùng authority và tooling

Một team không thể chịu trách nhiệm lead time/reliability nếu không thể:

- Xem logs, traces, metrics và deployment history.
- Triển khai/rollback trong policy.
- Quản lý schema migration của domain.
- Cấu hình timeout/feature flag/rate limit theo guardrails.
- Kiểm tra backup/restore và data correctness.
- Nhận alert và escalation.
- Đọc chi phí và capacity.
- Thay đổi contract của service mình.

Nếu mọi thao tác đều cần ticket trung tâm, việc tách service không đem lại autonomy. Platform nên cung cấp self-service và guardrails để owner hành động an toàn.

## 29. DORA metrics: dùng như tín hiệu, không phải bảng xếp hạng

Bốn metric thường được nhắc đến:

- **Deployment frequency:** mức độ thường xuyên đưa thay đổi vào production.
- **Lead time for changes:** thời gian từ commit/đưa thay đổi vào quy trình đến production theo định nghĩa đã chọn.
- **Change failure rate:** tỷ lệ deploy gây degradation cần remediation/rollback.
- **Time to restore service:** thời gian khôi phục sau incident do thay đổi hoặc sự cố.

Cần thống nhất định nghĩa, phạm vi và nguồn dữ liệu trước khi so sánh. Một team deploy hàng trăm lần vì mỗi config change nhỏ là không tự động tốt hơn team deploy ít hơn cho một hệ thống batch quan trọng.

Không dùng các metric này để ép cá nhân tăng số deploy hoặc che incident. Dùng chúng để tìm constraint của hệ thống làm việc và xem các thay đổi kiến trúc có cải thiện delivery/reliability không.

## 30. Error budget và lựa chọn đầu tư

SLO và error budget giúp product/engineering quyết định giữa feature delivery và reliability work.

Ví dụ một API có SLO 99,9% trong cửa sổ 30 ngày. Nếu error budget bị tiêu nhanh, nhóm có thể:

- Tạm dừng rollout rủi ro.
- Ưu tiên sửa lỗi lặp lại.
- Tăng capacity hoặc cải thiện dependency behavior.
- Bổ sung retry/timeout đúng semantics.
- Cải thiện observability và recovery.
- Chấp nhận một degraded mode có kiểm soát.

Không dùng error budget cho lỗi correctness nghiêm trọng như charge trùng hoặc mất dữ liệu theo cách “đã nằm trong 0,1%”. Một số invariant cần guardrail tuyệt đối hoặc quy trình riêng.

## 31. Đo coordination cost của một thay đổi

Một template ghi nhận change:

~~~markdown
# Change Coordination Record

## Thay đổi
- Capability:
- User outcome:
- Owner team:

## Phạm vi
- Services/repositories:
- Data schemas:
- API/event contracts:
- Teams required:
- Teams consulted/informed:

## Thời gian
- Start:
- Code complete:
- Review complete:
- Dependency ready:
- Production:
- Total wait time:
- Total execution time:

## Release
- Coordinated deploys:
- Compatibility checks:
- Rollback plan:

## Kết quả
- User metric:
- Reliability guardrails:
- Cost:
- Follow-up:
~~~

Dữ liệu này có thể dùng để tìm các thay đổi thường xuyên bị chờ. Không cần ghi thủ công cho mọi ticket nếu hệ thống delivery đã thu được timestamps; template hữu ích cho các thay đổi xuyên nhiều nhóm.

## 32. Architecture fitness functions

Fitness function là phép kiểm tra tự động hoặc định kỳ giúp xác nhận một thuộc tính kiến trúc còn được giữ.

Ví dụ:

- Không service nào truy cập trực tiếp schema của domain khác.
- Mọi production service có owner, SLO, dashboard và runbook.
- API breaking change phải có compatibility report.
- Deployable có thể rollback trong thời gian mục tiêu.
- Không có dependency vòng giữa domain modules.
- Service mới phải khai báo data classification và backup policy.
- Critical user journey có synthetic check.
- Consumer xử lý duplicate event theo contract.
- Platform template có support window và version pinning.

Fitness function không nhất thiết là test code. Có thể là policy check, dashboard, review định kỳ hoặc game day. Quan trọng là đo một thuộc tính có liên quan đến outcome.

## 33. Evolutionary architecture: thay đổi từng bước

Không cần thiết kế lại toàn bộ hệ thống một lần. Một lộ trình tiến hóa:

1. Inventory capability, service, data và owner hiện tại.
2. Xác định user journey và pain point có bằng chứng.
3. Chọn một boundary có tác động rõ.
4. Viết giả thuyết và baseline.
5. Thiết kế contract và data ownership.
6. Thử thay đổi trong scope nhỏ.
7. Canary hoặc chuyển cohort.
8. Đo outcome, reliability và coordination cost.
9. Điều chỉnh hoặc rollback nếu guardrail fail.
10. Mở rộng khi bằng chứng đủ tốt.
11. Xóa đường cũ sau migration window.
12. Cập nhật catalog, runbook và architecture decision.

Cách này giảm rủi ro big-bang migration và giúp tổ chức học từ từng thay đổi.

## 34. Refactor khi đã có quá nhiều service nhỏ

Giả sử một checkout workflow gồm 18 service, phần lớn chỉ đọc/ghi một bảng. Các team phải phối hợp nhiều lần cho một thay đổi.

Một hướng tiếp cận:

**Bước 1 — Phân loại service.** Xác định capability, data owner, consumer, workload, SLO và tần suất thay đổi.

**Bước 2 — Tìm nhóm thay đổi cùng nhau.** Dùng commit/deploy history và change scenarios để tìm service thường được sửa/deploy cùng.

**Bước 3 — Xác định invariant và transaction.** Những bảng nào phải thay đổi nguyên tử? Những state transition nào thuộc cùng domain?

**Bước 4 — Chọn target boundary.** Có thể hợp nhất các CRUD service thành module hoặc service theo domain.

**Bước 5 — Thiết kế contract và ownership.** Chặn direct writes, công bố API/event và migration plan.

**Bước 6 — Chuyển traffic từng phần.** Dùng strangler routing hoặc adapter có kiểm soát.

**Bước 7 — Đối chiếu dữ liệu.** Kiểm tra record, totals, status transitions và business invariants.

**Bước 8 — Hợp nhất vận hành.** Cập nhật deployment, dashboard, alert, on-call và cost allocation.

**Bước 9 — Tắt service cũ.** Chỉ khi không còn consumer và có bằng chứng recovery/rollback.

Không cần giữ service chỉ vì đã đầu tư nhiều tháng. Chi phí sunk cost không phải lý do để duy trì một ranh giới gây overhead liên tục.

## 35. Refactor monolith khi cần độc lập thật sự

Nếu một phần monolith có nhu cầu scale/release riêng:

1. Tạo module boundary bên trong monolith trước.
2. Di chuyển domain model và persistence ownership vào module.
3. Thay truy cập trực tiếp bằng interface/contract nội bộ.
4. Bổ sung test cho invariant và module dependency.
5. Đo workload và release constraints.
6. Chọn phần tách có lợi ích rõ.
7. Tạo API/event contract.
8. Tách database ownership và migration.
9. Triển khai service mới song song theo strangler pattern.
10. Canary và so sánh behavior.
11. Chuyển quyền ghi/traffic.
12. Gỡ module cũ khi an toàn.

Không tách tất cả module chỉ vì đã có package. Một phần có thể ở lại monolith lâu dài nếu đó là lựa chọn kinh tế và vận hành tốt.

## 36. Sử dụng strangler pattern có kiểm soát

~~~text
                 API Gateway / Router
                         |
                 Routing decision
                   /          \
                  v            v
            Legacy module   New service
                  |             |
                  +---- data ---+
                    migration
~~~

Các điều kiện:

- Một nguồn authoritative cho writes tại mỗi giai đoạn.
- Routing nhất quán theo key/cohort.
- Không dual-write tùy tiện.
- Có idempotency, outbox và reconciliation nếu cần đồng bộ.
- Có telemetry so sánh kết quả.
- Có stop condition và rollback.
- Có thời hạn kết thúc legacy path.

Một feature flag không tự giải quyết data divergence. Nếu hai path cùng nhận write, phải có thiết kế consistency rõ.

## 37. Khi nào không nên tối ưu thêm service?

Không tách service nếu lý do chỉ là:

- Một bảng mới xuất hiện.
- Một class dài hoặc nhiều method.
- Muốn dùng một framework khác cho một hàm nhỏ.
- Muốn sơ đồ có nhiều hộp hơn.
- Một team cần thêm repository để thể hiện ownership.
- Có thể tái sử dụng một function ở nhiều nơi nhưng semantics chưa rõ.
- Một endpoint có lượng code nhỏ.
- “Microservices là best practice” mà chưa có pain point.

Cân nhắc giữ module nội bộ, tạo library kỹ thuật nhỏ hoặc dùng domain API hiện có. Nếu thay đổi không cần boundary vận hành độc lập, tạo thêm service có thể tăng chi phí nhiều hơn lợi ích.

## 38. Khi nào cần tách dù số service đã nhiều?

Cũng không nên dùng “đã quá nhiều service” để ngăn mọi thay đổi. Có thể cần tách một capability khi:

- Một domain có security boundary riêng.
- Workload có throughput hoặc latency profile khác biệt.
- Một subsystem cần scale độc lập.
- Một team cần release độc lập thường xuyên.
- Failure isolation có giá trị cao.
- Data owner và contract có thể được xác định.
- Team đủ năng lực vận hành.

Quyết định phải dựa trên outcome và trade-off, không phải mục tiêu giảm số lượng bằng mọi giá.

## 39. Case study: tách Inventory vì nhu cầu nghiệp vụ

**Bối cảnh:** Inventory logic nằm trong Commerce Application. Flash sale làm stock reservation contention tăng cao; deploy một thay đổi catalog thường ảnh hưởng checkout.

**Giả thuyết:** tách Inventory thành capability có owner và storage boundary riêng sẽ cải thiện throughput reservation và giảm blast radius mà không tăng oversell.

**Các quyết định cần có:**

- Inventory Team sở hữu stock, allocation và reservation.
- Order/Checkout gọi ReserveInventory với idempotency key.
- Reservation có trạng thái và expiry rõ.
- Event Reserved/Released được versioned.
- Order không ghi trực tiếp inventory table.
- Platform hỗ trợ runtime, broker, database và observability.
- SLO đo reservation success/latency và oversell guardrail.

**Đo sau rollout:**

- p95 reservation latency.
- reservation conflict rate.
- oversell incidents.
- checkout completion.
- lead time của Inventory changes.
- deploy independence.
- cost per reservation.
- time to recover khi Inventory degraded.

Nếu throughput cải thiện nhưng checkout completion giảm vì API network timeout, cần điều chỉnh contract/timeout/fallback. Không thể tuyên bố thành công chỉ vì service mới xử lý được nhiều request.

## 40. Case study: giữ Pricing trong modular monolith

**Bối cảnh:** Pricing và Checkout do cùng một team nhỏ sở hữu. Rule thay đổi liên tục, nhiều bước cần transaction với cart snapshot, traffic chưa lớn và không có nhu cầu scale riêng.

Một lựa chọn hợp lý là giữ Pricing module trong cùng deployable, nhưng:

- Module có domain model và API nội bộ.
- Checkout không truy cập private tables của Pricing.
- Contract nội bộ được test.
- Rule version và quote snapshot rõ.
- Có thể tách runtime sau nếu nhu cầu thay đổi.
- Không tạo thêm network dependency chỉ để gọi một function nội bộ.

Đây không phải “không hiện đại”. Nó là cách giữ khả năng thay đổi và giảm operational overhead trong bối cảnh hiện tại.

## 41. Case study: giảm số service nhưng tăng khả năng thay đổi

Một công ty có 30 service, trong đó 10 service chỉ là CRUD wrappers. Sau phân tích, họ gom chúng vào ba domain services và một modular monolith cho các capability còn lại.

Kết quả cần đánh giá không phải “giảm từ 30 xuống 12” mà là:

- Thời gian từ code complete đến production giảm.
- Một thay đổi order không còn cần 5 release.
- Transaction Order header/items được giữ nguyên.
- Owner và on-call rõ.
- Network calls giảm.
- SLO user journey không xấu đi.
- Cost runtime giảm hoặc được tái đầu tư vào reliability.
- Rollback và recovery dễ kiểm soát hơn.

Nếu số service giảm nhưng một deployable quá lớn khiến mọi thay đổi phải chờ nhau, mục tiêu chưa đạt. Số lượng chỉ là một trong nhiều dữ liệu.

## 42. Case study: tăng service nhưng giảm blast radius

Một Payment capability cần cô lập credential, compliance và scaling. Tổ chức tách Payment khỏi Commerce Application dù tổng số service tăng.

Thành công được đo bằng:

- Payment credential và data access có owner/permission riêng.
- Checkout không truy cập Payment ledger.
- Payment có SLO và on-call độc lập.
- Payment provider integration có thể rollout/rollback riêng.
- Unknown outcomes và reconciliation được xử lý tốt.
- Incident Payment không làm lộ hoặc ảnh hưởng database của Order.
- Chi phí vận hành tăng trong ngưỡng chấp nhận.

Tăng số service trong trường hợp này có thể tạo giá trị rõ. Bài học là không tối ưu số lượng theo chiều tăng hay giảm; tối ưu khả năng đáp ứng mục tiêu.

## 43. Product discovery và kiến trúc cùng học

Một quyết định kiến trúc thường dựa trên giả định về tải, hành vi và ranh giới. Product discovery giúp kiểm chứng giả định đó:

- Quan sát user journey và điểm drop-off.
- Phỏng vấn người dùng/nhóm support.
- Thử nghiệm flow mới với cohort nhỏ.
- Đo latency/correctness trong môi trường thực.
- Xem workload và access patterns.
- Phân tích support incidents và manual work.
- Cập nhật domain model khi hiểu biết mới xuất hiện.

Nếu nhu cầu sản phẩm thay đổi, ranh giới kiến trúc cũng có thể thay đổi. Không nên giữ service boundary chỉ vì nó được phê duyệt trong ADR nhiều năm trước.

## 44. Governance và guardrails không làm mất autonomy

Các guardrails chung có thể bảo vệ tổ chức:

- Identity/IAM và least privilege.
- Encryption, secrets và certificate handling.
- Artifact provenance/signing và dependency scanning.
- Data classification, retention và backup.
- API/event compatibility.
- SLO, incident response và audit.
- Network policy và resource quotas.

Guardrails nên tự động hóa khi có thể. Domain teams vẫn quyết định behavior nghiệp vụ trong phạm vi của mình. Platform không nên trở thành nơi duyệt mọi business change; product teams không nên bỏ qua security/compliance vì muốn deploy nhanh.

## 45. Tổ chức roadmap kiến trúc theo outcome

Một roadmap kiến trúc nên gắn với mục tiêu có thể đo:

| Mục tiêu | Initiative kiến trúc | Metric kết quả |
|---|---|---|
| Checkout completion thấp do dependency latency | Giảm critical-path calls, cải thiện timeout/fallback | Completion, p95 latency |
| Thay đổi Order mất nhiều ngày chờ consumer | Additive contract, consumer compatibility | Lead time, coordinated releases |
| Incident mất thời gian tìm owner | Service catalog, on-call routing, trace context | Time to identify owner |
| Payment duplicate risk | Idempotency ledger, reconciliation | Duplicate charge count |
| Database migration hay fail | Expand-contract, migration tests | Change failure rate |
| Platform ticket backlog cao | Self-service provisioning | Provision time, manual handoffs |
| Chi phí per order tăng | Capacity/caching/architecture review | Cost per completed order |

Roadmap cần có owner, effort, dependency, risk và review date. Không đưa mục “tách 10 service” nếu không gắn với vấn đề/outcome.

## 46. Một quy trình quyết định kiến trúc

Trước khi thay đổi boundary, có thể đi theo các bước:

1. Mô tả vấn đề sản phẩm/vận hành cụ thể.
2. Xác định user outcome và guardrails.
3. Thu baseline hiện tại.
4. Liệt kê các options: giữ nguyên, refactor module, hợp nhất, tách service, dùng platform capability.
5. Ước lượng lifecycle cost và coordination cost.
6. Xác định domain/data owner và contract.
7. Đánh giá failure modes, security và recovery.
8. Chọn thử nghiệm nhỏ nhất có thể kiểm chứng giả thuyết.
9. Đặt stop conditions và rollback.
10. Đo sau rollout.
11. Ghi ADR và cập nhật service catalog.
12. Mở rộng hoặc đảo quyết định theo bằng chứng.

Không phải mọi quyết định đều cần một quy trình nặng. Một refactor nhỏ có thể chỉ cần code review; một thay đổi database/payment boundary có thể cần ADR, migration rehearsal và cross-team review.

## 47. Bài tập tự luyện

### Bài A — Đánh giá KPI số lượng service

Ban lãnh đạo yêu cầu tăng số microservice từ 25 lên 60 trong một quý. Hãy viết problem statement, chỉ ra rủi ro vanity metric và đề xuất các outcome/guardrail thay thế.

### Bài B — Đo khả năng thay đổi

Một feature mất 14 ngày: 3 ngày code, 2 ngày review, 4 ngày chờ consumer, 3 ngày chờ deploy window và 2 ngày canary. Hãy tính thời gian thực thi/chờ, xác định bottleneck và đề xuất cách giảm lead time mà không bỏ kiểm soát.

### Bài C — Chọn modular monolith hay microservices

Một team 7 người sở hữu Catalog, Pricing và Cart. Các module thường thay đổi cùng nhau và có transaction chung. Hãy đề xuất cấu trúc hiện tại, điều kiện nào sẽ khiến bạn tách một capability trong tương lai.

### Bài D — Tách Inventory

Inventory cần scale riêng cho flash sale. Hãy thiết kế owner, API, data boundary, idempotency, reservation expiry, SLO và migration. Nêu outcome và guardrails để đánh giá thành công.

### Bài E — Đo giá trị Payment extraction

Payment được tách khỏi monolith nhưng duplicate charge không giảm và lead time không thay đổi. Hãy xác định giả thuyết nào sai, những dependency nào vẫn còn và phương án tiếp theo.

### Bài F — DORA metrics

Một team tăng deployment frequency gấp ba nhưng change failure rate cũng tăng gấp đôi. Hãy đề xuất cách đọc các metric cùng SLO và user outcome; nêu những hành động không nên thực hiện.

### Bài G — Cost per outcome

Một kiến trúc mới làm compute cost tăng 20% nhưng checkout completion tăng 8%, support tickets giảm 30%. Hãy đề xuất cách đánh giá kinh tế, guardrails và dữ liệu còn thiếu.

### Bài H — Architecture fitness function

Thiết kế năm kiểm tra tự động giúp bảo vệ data ownership, API compatibility, service ownership, SLO instrumentation và rollback readiness.

### Bài I — Strangler migration

Một legacy order module cần tách dần. Hãy lập rollout theo cohort, xác định authoritative write path, reconciliation, rollback và điều kiện xóa đường cũ.

### Bài J — Review một proposal

Một proposal ghi “mỗi database table sẽ thành một microservice để scale tốt hơn”. Hãy đặt các câu hỏi về workload, domain, ownership, transaction, contract, SLO, cost và chứng cứ trước khi quyết định.

### Bài K — Product experiment

Một team muốn rút ngắn checkout bằng cách bỏ bước xác nhận. Hãy thiết kế experiment, North Star metric, guardrails correctness/security, rollout và stop condition.

### Bài L — Hợp nhất service

Mười service nhỏ luôn deploy cùng nhau. Hãy phân tích liệu nên hợp nhất thành modular monolith hay một domain service lớn hơn, và metric nào chứng minh quyết định có lợi.

## 48. Checklist: kiến trúc đang tối ưu điều gì?

- [ ] Mục tiêu kiến trúc bắt đầu từ một vấn đề sản phẩm/vận hành có bằng chứng.
- [ ] Có outcome và guardrails đo được trước khi thay đổi.
- [ ] Số service không được dùng làm KPI thành công độc lập.
- [ ] Bounded context và data owner được xác định.
- [ ] Mỗi service mới có lý do về ownership, scale, security, release hoặc failure isolation.
- [ ] Contract và compatibility cho phép thay đổi độc lập khi phù hợp.
- [ ] Team có authority, telemetry, deployment và rollback capability.
- [ ] SLO đo cả availability, latency và correctness theo domain.
- [ ] Product outcome được liên kết với service behavior.
- [ ] Cost tính cả runtime, coordination, on-call và maintenance.
- [ ] Modular monolith được xem như một option hợp lệ.
- [ ] Có baseline lead time, wait time và coordinated releases.
- [ ] Rollout có canary/stop condition và rollback.
- [ ] Migration có data reconciliation và một nguồn ghi có thẩm quyền.
- [ ] ADR ghi lại giả định, options và consequences.
- [ ] Có fitness functions để bảo vệ boundary.
- [ ] Sau rollout có review dựa trên dữ liệu.
- [ ] Có thể hợp nhất hoặc tách lại khi giả định thay đổi.
- [ ] Không dùng metric delivery để tạo động cơ che lỗi hoặc deploy giả.
- [ ] Kiến trúc giúp nhóm học nhanh hơn và phục vụ người dùng tốt hơn.

## 49. Kết luận

Số lượng microservice là một thuộc tính triển khai, không phải mục tiêu sản phẩm. Một hệ thống có nhiều service chỉ tạo ra giá trị khi các boundary giúp tổ chức thay đổi độc lập, bảo vệ dữ liệu, giới hạn failure và đưa tính năng tới người dùng nhanh hơn. Nếu mỗi thay đổi vẫn cần nhiều nhóm, nhiều release đồng bộ và nhiều bước vận hành thủ công, số service tăng chỉ làm tăng bề mặt phức tạp.

Hãy đánh giá kiến trúc bằng **khả năng thay đổi an toàn, kết quả người dùng, độ tin cậy, chi phí vòng đời và năng lực học hỏi**. Dùng bounded context để định nghĩa ownership, contract để giảm coupling, platform để giảm toil, SLO để bảo vệ reliability và experiment để kiểm chứng giá trị. Modular monolith, service-oriented architecture và microservices đều có chỗ đứng; lựa chọn tốt là lựa chọn phù hợp với nhu cầu hiện tại và có đường tiến hóa khi nhu cầu đổi khác.

Một quyết định tách service thành công không phải vì sơ đồ có thêm một hộp. Nó thành công khi người dùng nhận giá trị tốt hơn, nhóm có thể thay đổi phần mình sở hữu với ít chờ đợi hơn, hệ thống giữ được correctness và reliability, và tổng chi phí vận hành vẫn nằm trong mức tổ chức có thể duy trì.
