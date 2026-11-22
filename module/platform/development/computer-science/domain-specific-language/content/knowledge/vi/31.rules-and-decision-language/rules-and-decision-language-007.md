# Mô phỏng kịch bản

## 1. Mô phỏng kịch bản trong DSL luật và quyết định

Một ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL) cho luật và quyết định thường mô tả điều kiện, sự kiện, trạng thái, hành động và kết quả của một quy trình nghiệp vụ. Khi một quyết định có nhiều đầu vào hoặc nhiều nhánh luật, người thiết kế cần hiểu điều gì sẽ xảy ra trong các tình huống khác nhau trước khi áp dụng luật vào hệ thống thật.

**Mô phỏng kịch bản (scenario simulation)** là quá trình chạy một mô hình luật hoặc quyết định trên các bộ giả định đầu vào, trạng thái ban đầu và chuỗi sự kiện được kiểm soát để quan sát kết quả có thể xảy ra. Mô phỏng giúp trả lời các câu hỏi như:

- Nếu một biến đầu vào thay đổi thì quyết định có đổi không?
- Nếu nhiều luật cùng phù hợp thì luật nào được kích hoạt?
- Nếu sự kiện đến theo thứ tự khác nhau thì trạng thái cuối có khác không?
- Nếu nhu cầu tăng, hệ thống có vượt giới hạn tài nguyên không?
- Nếu một điều kiện rủi ro xuất hiện, quy trình sẽ đi theo nhánh nào?
- Nếu chính sách mới được triển khai, kết quả khác chính sách hiện tại ở đâu?

Ví dụ một DSL xét duyệt đơn hàng:

~~~text
decision "order-review" {
    input amount: Decimal
    input customer_risk: RiskLevel
    input verified: Boolean

    rule "manual-review" when
        amount > 5000 or customer_risk == HIGH
    then
        outcome MANUAL_REVIEW

    rule "auto-approve" when
        verified and amount <= 5000 and customer_risk == LOW
    then
        outcome APPROVE

    otherwise
        outcome REJECT
}
~~~

Người thiết kế có thể mô phỏng nhiều bộ dữ liệu: đơn hàng nhỏ của khách hàng rủi ro thấp, đơn hàng lớn đã xác minh, hoặc đơn hàng có thông tin chưa đầy đủ. Kết quả mô phỏng cho thấy outcome nào được chọn và những rule nào đã được đánh giá.

Mô phỏng kịch bản không phải là thực thi nghiệp vụ thật. Nó dùng mô hình và dữ liệu giả định hoặc bản sao được kiểm soát để khám phá hành vi, so sánh phương án và đánh giá rủi ro trước khi quyết định được đưa vào production.

## 2. Phân biệt mô phỏng, kiểm thử và thực thi

Ba hoạt động này có liên quan nhưng mục tiêu khác nhau.

| Hoạt động | Mục tiêu | Đầu vào | Kết quả |
|---|---|---|---|
| Thực thi | Áp dụng luật để xử lý công việc thật | Dữ liệu và trạng thái thực | Quyết định hoặc side effect thật |
| Kiểm thử | Xác nhận hành vi đáp ứng kỳ vọng đã định | Fixture và assertion | Pass/fail, lỗi hoặc coverage |
| Mô phỏng | Khám phá hành vi dưới các giả định và biến thiên | Scenario, giả định, dữ liệu mẫu hoặc phân phối | Kết quả, trace, thống kê và so sánh |

### 2.1. Thực thi thật

Một decision engine có thể nhận yêu cầu xét duyệt và cập nhật trạng thái đơn hàng. Nếu hành động gửi thanh toán hoặc từ chối giao dịch được thực hiện, đó là side effect thật.

### 2.2. Kiểm thử luật

Một test case có thể khẳng định rằng amount lớn hơn ngưỡng sẽ cho kết quả MANUAL_REVIEW. Test có expected result cụ thể và thất bại nếu kết quả khác.

### 2.3. Mô phỏng

Một scenario có thể thay đổi amount từ 1.000 đến 10.000, thay đổi risk level và quan sát ranh giới mà outcome chuyển từ APPROVE sang MANUAL_REVIEW. Mô phỏng có thể chạy nhiều biến thể mà không cần khẳng định trước một kết quả duy nhất.

### 2.4. Có thể dùng chung engine

Test runner và simulator có thể dùng cùng rule evaluator để bảo đảm cùng semantics. Tuy nhiên, simulator cần lớp quản lý scenario, giả định, lặp, random seed, thống kê và so sánh kết quả.

### 2.5. Không mô phỏng bằng cách gọi hệ thống production

Nếu simulation mode vẫn gọi API thật, gửi email hoặc cập nhật database, nó có thể gây side effect ngoài ý muốn. Cần tách effect adapter, dùng fake service hoặc sandbox và từ chối hành động không được phép trong simulation.

## 3. Mô hình khái niệm của một scenario

Một scenario thường bao gồm các thành phần:

- **Scenario identity:** tên và định danh.
- **Initial state:** trạng thái ban đầu của mô hình.
- **Inputs:** giá trị đầu vào.
- **Assumptions:** các giả định được dùng trong lần chạy.
- **Events:** sự kiện và thứ tự xảy ra.
- **Parameters:** biến được thay đổi giữa các lần chạy.
- **Ruleset version:** phiên bản luật được mô phỏng.
- **Environment profile:** cấu hình hoặc môi trường giả lập.
- **Execution policy:** cách xử lý xung đột, thứ tự và thời gian.
- **Expected invariants:** các điều kiện phải luôn giữ đúng.
- **Observations:** kết quả, trace và số liệu được thu thập.

Ví dụ một scenario dạng khai báo:

~~~text
scenario "high-value-order" {
    ruleset = "order-review@3.2"

    initial {
        customer.risk = LOW
        customer.verified = true
        order.amount = 7200
        order.status = NEW
    }

    run decision "order-review"

    observe outcome
    observe matched_rules
    observe state_changes
}
~~~

Đây là cú pháp minh họa. Một DSL thực tế cần xác định rõ phạm vi biến, kiểu dữ liệu, cách nạp ruleset và cách ghi nhận kết quả.

## 4. Các loại mô phỏng kịch bản

Không phải scenario nào cũng có cùng cách sinh đầu vào hoặc cùng mô hình thời gian.

### 4.1. Deterministic scenario

Mỗi lần chạy dùng cùng đầu vào, trạng thái và luật thì kết quả quan sát được phải giống nhau. Loại này phù hợp để khám phá nhánh luật, kiểm tra ranh giới và so sánh phiên bản.

### 4.2. What-if simulation

Thay đổi một hoặc nhiều giả định để xem kết quả thay đổi thế nào. Ví dụ tăng ngưỡng xét duyệt, thay tỷ lệ phí hoặc đổi một điều kiện eligibility.

### 4.3. Parameter sweep

Chạy một dải giá trị cho một hoặc nhiều tham số. Ví dụ amount từ 0 đến 20.000 với bước 500 để tìm vùng chuyển outcome.

### 4.4. Scenario matrix

Kết hợp các nhóm điều kiện rời rạc, ví dụ risk level LOW/MEDIUM/HIGH, verified true/false và amount SMALL/LARGE. Ma trận cho biết kết quả ở từng tổ hợp.

### 4.5. Discrete-event simulation

Mô phỏng hệ thống bằng cách xử lý sự kiện tại các thời điểm rời rạc. Thời gian mô phỏng nhảy từ event này sang event tiếp theo thay vì cập nhật mọi đơn vị thời gian.

### 4.6. Time-stepped simulation

Mô hình cập nhật theo bước thời gian cố định, ví dụ mỗi phút hoặc mỗi ngày. Phù hợp khi trạng thái cần được tính lại theo chu kỳ.

### 4.7. Monte Carlo simulation

Sinh nhiều lần chạy với đầu vào ngẫu nhiên theo phân phối đã khai báo để ước lượng phân bố kết quả, xác suất và rủi ro.

### 4.8. Agent-based simulation

Mô phỏng nhiều agent có trạng thái và hành vi riêng, tương tác qua sự kiện hoặc môi trường chung. Có thể dùng cho mô hình khách hàng, thị trường, thiết bị hoặc thành phần phân tán.

### 4.9. Hybrid simulation

Kết hợp nhiều cách mô phỏng, chẳng hạn sự kiện rời rạc cho workflow và Monte Carlo cho nhu cầu đầu vào.

## 5. Mô tả scenario bằng DSL

Một DSL mô phỏng nên giúp người dùng mô tả giả định và quan sát bằng ngôn ngữ của miền.

### 5.1. Khai báo scenario

~~~text
scenario "holiday-traffic" {
    description = "Mô phỏng tải trong kỳ nghỉ"
    duration = 24h
    time_step = 1m
}
~~~

Scenario có thể khai báo thời gian chạy, phạm vi và mô tả để người khác hiểu mục đích.

### 5.2. Khai báo inputs

~~~text
inputs {
    arrival_rate = 120 per_minute
    average_order_value = 850
    available_workers = 12
}
~~~

Input cần có kiểu, đơn vị và miền giá trị hợp lệ. Đơn vị rõ ràng giúp tránh so sánh hoặc cộng các đại lượng không tương thích.

### 5.3. Khai báo assumptions

~~~text
assumptions {
    payment_provider_available = true
    network_latency = 80ms
    retry_policy = "standard"
}
~~~

Giả định là điều kiện được cố định trong scenario. Kết quả chỉ có ý nghĩa trong phạm vi giả định đó.

### 5.4. Gắn ruleset

~~~text
ruleset "credit-policy" version "2026.3"
~~~

Việc pin ruleset giúp kết quả có thể được tái lập. Nếu dùng alias latest, cần lưu version thực tế được resolve.

### 5.5. Khai báo events

~~~text
events {
    at 0s: customer_arrives(count = 20)
    at 5m: provider_latency_changes(to = 300ms)
    at 10m: worker_pool_changes(to = 6)
}
~~~

Event có timestamp hoặc điều kiện kích hoạt. DSL cần quy định cách xử lý hai event cùng thời điểm.

### 5.6. Khai báo observations

~~~text
observe {
    decision.outcome
    rule.activation_count
    queue.length
    service.completed_requests
    service.error_rate
}
~~~

Observation chỉ định các đại lượng cần thu thập. Nếu ghi quá nhiều dữ liệu, simulation có thể tốn bộ nhớ và làm kết quả khó đọc.

## 6. Initial state và state transition

Mô phỏng thường bắt đầu từ một trạng thái ban đầu rồi áp dụng luật hoặc sự kiện để chuyển sang trạng thái tiếp theo.

### 6.1. State

State là tập giá trị mô tả mô hình tại một thời điểm. Ví dụ:

~~~text
account {
    balance = 1000
    status = ACTIVE
    failed_attempts = 0
}
~~~

### 6.2. Transition

Transition là thay đổi trạng thái do event hoặc rule gây ra:

~~~text
on withdrawal(amount) {
    if account.balance >= amount {
        account.balance = account.balance - amount
    } else {
        account.status = REVIEW
    }
}
~~~

### 6.3. State snapshot

Snapshot lưu trạng thái tại một mốc để so sánh hoặc khôi phục simulation. Snapshot nên có model version và scenario run ID để không bị nhầm giữa các lần chạy.

### 6.4. State isolation

Mỗi scenario run cần trạng thái riêng. Nếu nhiều run dùng chung mutable state, kết quả có thể phụ thuộc thứ tự chạy và làm nhiễm dữ liệu giữa các scenario.

### 6.5. Reset

Sau mỗi lần chạy, simulator cần khôi phục initial state hoặc tạo instance mới. Reset phải bao gồm cả queue, timer, random generator, counter và state của agent.

## 7. Rule evaluation trong mô phỏng quyết định

DSL luật và quyết định có thể dùng simulator để hiểu cách các rule tương tác.

### 7.1. Rule matching

Mỗi rule có điều kiện. Simulator ghi nhận rule nào được đánh giá, rule nào khớp và rule nào không khớp.

~~~text
rule "large-order" when amount > 5000
    then outcome REVIEW
~~~

### 7.2. Rule priority

Nếu nhiều rule cùng khớp, engine có thể dùng priority hoặc agenda strategy. Scenario nên quan sát cả thứ tự kích hoạt, không chỉ kết quả cuối.

### 7.3. First-match và all-match

- First-match: chọn rule đầu tiên theo thứ tự hoặc ưu tiên đã quy định.
- All-match: thực thi mọi rule thỏa điều kiện theo semantics của engine.

Simulator phải dùng đúng chính sách production. Nếu mô phỏng bằng semantics khác, kết quả không phản ánh hành vi thật.

### 7.4. Conflict resolution

Hai rule có thể đề xuất hành động xung đột. Engine cần quy định cách giải quyết: priority, specificity, salience, explicit ordering hoặc báo conflict.

### 7.5. Rule trace

Một trace có thể ghi:

- Rule ID.
- Điều kiện đã đánh giá.
- Kết quả true/false.
- Priority.
- Hành động được chọn.
- Trạng thái trước và sau.
- Thời điểm hoặc event kích hoạt.

Không nên ghi dữ liệu nhạy cảm vào trace nếu không cần thiết.

## 8. Luật có trạng thái và chuỗi sự kiện

Một quyết định đơn lẻ chỉ xem xét một snapshot đầu vào. Nhiều nghiệp vụ phụ thuộc lịch sử sự kiện.

### 8.1. Event sequence

~~~text
events {
    at 0m: application_submitted()
    at 2m: document_uploaded()
    at 5m: risk_score_received(score = 72)
    at 8m: reviewer_assigned()
}
~~~

Simulator xử lý các event theo thứ tự và cập nhật state.

### 8.2. Event ordering

Nếu hai event có cùng timestamp, cần quy định tie-break: sequence number, source priority hoặc thứ tự khai báo. Không nên để kết quả phụ thuộc vào thứ tự iteration ngẫu nhiên của collection.

### 8.3. Late event

Một event có thể đến trễ so với thời điểm logic của nó. Mô hình cần quy định có chấp nhận event muộn, replay từ snapshot hay bỏ qua.

### 8.4. Duplicate event

Event bị gửi lại có thể làm transition chạy hai lần. Dùng event ID hoặc idempotency key để nhận diện duplicate khi semantics yêu cầu.

### 8.5. Event sourcing

Trong event-sourced model, state được dựng từ chuỗi event. Simulator có thể replay event log để kiểm tra luật mới hoặc so sánh hành vi giữa hai phiên bản ruleset.

## 9. Mô phỏng thời gian

Thời gian là yếu tố quan trọng trong workflow, policy và quyết định có deadline.

### 9.1. Simulation clock

Simulator nên có clock riêng, tách khỏi wall-clock của máy chạy. Điều này cho phép chạy một ngày mô phỏng trong vài giây thực hoặc kiểm thử mốc thời gian trong quá khứ.

### 9.2. Discrete-event clock

Với discrete-event simulation, clock nhảy đến timestamp của event tiếp theo. Không cần xử lý mọi mili giây nếu giữa hai event không có trạng thái thay đổi.

### 9.3. Time step

Time-stepped model cập nhật theo khoảng cố định. Bước quá lớn có thể bỏ qua biến động nhanh; bước quá nhỏ làm tăng số lần tính toán.

### 9.4. Timer và deadline

Rule có thể kích hoạt khi quá hạn:

~~~text
rule "escalate-overdue" when
    case.status == OPEN and now >= case.deadline
then
    case.status = ESCALATED
~~~

### 9.5. Time zone và calendar

Nếu luật phụ thuộc ngày làm việc, ngày nghỉ hoặc múi giờ, scenario cần chỉ định calendar và timezone. Không nên dùng timezone mặc định của máy host.

### 9.6. Temporal boundary

Kiểm thử tại thời điểm ngay trước, đúng tại và ngay sau deadline giúp phát hiện lỗi toán tử lớn hơn/lớn hơn hoặc bằng, inclusive/exclusive interval và rounding.

## 10. What-if analysis

What-if analysis thay đổi giả định để xem tác động lên outcome hoặc chỉ số.

### 10.1. Thay đổi một biến

~~~text
what_if "approval-threshold" {
    vary decision.approval_limit from 1000 to 10000 step 500
    observe approval_rate
}
~~~

Kết quả có thể cho thấy approval rate thay đổi theo ngưỡng.

### 10.2. Thay đổi nhiều biến

Có thể thay đồng thời arrival rate và worker count để quan sát throughput. Tuy nhiên, khi nhiều biến thay đổi cùng lúc, khó xác định biến nào gây ra tác động.

### 10.3. Baseline

Baseline là scenario tham chiếu dùng để so sánh. Nên lưu baseline cùng ruleset version, assumptions và input dataset.

### 10.4. Delta

Delta là chênh lệch giữa scenario và baseline:

~~~text
delta approval_rate = scenario.approval_rate - baseline.approval_rate
~~~

### 10.5. Threshold discovery

Parameter sweep có thể tìm giá trị tại đó outcome đổi hoặc invariant bắt đầu thất bại. Ví dụ tìm số worker tối thiểu để queue không tăng vô hạn trong một tải giả định.

### 10.6. Causal caution

Nếu nhiều tham số thay đổi đồng thời, sự tương quan trong kết quả không tự chứng minh quan hệ nhân quả. Nên thay đổi từng yếu tố hoặc dùng thiết kế thí nghiệm có kiểm soát.

## 11. Scenario matrix và combinatorial testing

Một tập đầu vào có nhiều giá trị có thể tạo số lượng tổ hợp rất lớn.

### 11.1. Cartesian product

Giả sử:

- Risk: LOW, MEDIUM, HIGH.
- Verified: true, false.
- Amount: SMALL, LARGE.
- Channel: WEB, MOBILE, BRANCH.

Toàn bộ tổ hợp là 3 × 2 × 2 × 3 = 36 scenario.

### 11.2. Full factorial

Full factorial chạy mọi tổ hợp. Cách này hữu ích khi số chiều nhỏ hoặc cần khám phá tương tác đầy đủ.

### 11.3. Pairwise testing

Pairwise chọn tập scenario sao cho mọi cặp giá trị giữa hai tham số xuất hiện ít nhất một lần. Nó giảm số lần chạy nhưng không bảo đảm phát hiện lỗi chỉ xuất hiện từ tương tác ba chiều trở lên.

### 11.4. Boundary value

Với ngưỡng amount > 5000, các giá trị 4999.99, 5000 và 5000.01 có ý nghĩa hơn nhiều giá trị ngẫu nhiên. Simulator nên hỗ trợ sinh giá trị quanh boundary.

### 11.5. Constraint-aware generation

Một số tổ hợp không hợp lệ, ví dụ payment_method = BANK_TRANSFER nhưng country không hỗ trợ. Scenario generator cần constraint để tránh tạo dữ liệu vô nghĩa.

### 11.6. Coverage

Có thể đo:

- Input value coverage.
- Rule coverage.
- Decision outcome coverage.
- Branch coverage.
- Pairwise combination coverage.
- State transition coverage.
- Event ordering coverage.

Coverage cao không chứng minh mô hình đúng, nhưng giúp nhận ra vùng chưa được khám phá.

## 12. Monte Carlo simulation

Monte Carlo dùng nhiều lần chạy với giá trị ngẫu nhiên được sinh theo phân phối xác định.

### 12.1. Khai báo phân phối

~~~text
random_inputs {
    arrival_rate ~ Poisson(mean = 100 per_minute)
    service_time ~ Normal(mean = 200ms, stddev = 40ms)
    failure_probability ~ Uniform(0.001, 0.02)
}
~~~

Các phân phối trong ví dụ là giả định. Cần kiểm tra dữ liệu thực tế và tính phù hợp của mô hình trước khi dùng kết quả để quyết định.

### 12.2. Số lần chạy

~~~text
monte_carlo "capacity-risk" {
    runs = 10000
    seed = 48291
    scenario = "peak-traffic"
}
~~~

Số lần chạy lớn hơn có thể giảm sai số lấy mẫu nhưng tăng thời gian và chi phí. Cần xem độ hội tụ thay vì chọn số lần chạy tùy ý.

### 12.3. Random seed

Seed cho phép tái tạo chuỗi số ngẫu nhiên của một implementation cụ thể. Để tái lập đầy đủ, cần lưu thuật toán PRNG, seed, phiên bản simulator, thứ tự lấy mẫu và cấu hình.

### 12.4. Output distribution

Thay vì một kết quả, Monte Carlo tạo phân bố:

- Trung bình.
- Median.
- Percentile.
- Variance và standard deviation.
- Xác suất vượt ngưỡng.
- Confidence interval.

### 12.5. Law of large numbers

Khi số lần chạy tăng, trung bình mẫu có xu hướng gần kỳ vọng của phân phối nếu các giả định thống kê phù hợp. Điều này không sửa được mô hình đầu vào sai hoặc thiếu biến quan trọng.

### 12.6. Correlated inputs

Không nên mặc định mọi biến độc lập. Ví dụ lượng đơn hàng và thời gian xử lý có thể tương quan. Nếu mô hình hóa sai tương quan, tail risk có thể bị đánh giá thấp.

### 12.7. Rare events

Sự kiện hiếm có thể không xuất hiện trong số lần chạy thông thường. Cần cân nhắc importance sampling, stress scenario hoặc phân tích worst-case khi phù hợp.

## 13. Sensitivity analysis

Sensitivity analysis đo mức độ kết quả thay đổi khi một hoặc nhiều tham số thay đổi.

### 13.1. One-at-a-time

Thay một tham số trong khi giữ các tham số khác cố định. Cách này dễ diễn giải nhưng có thể bỏ qua tương tác giữa biến.

### 13.2. Local sensitivity

Đo thay đổi đầu ra gần một điểm vận hành cụ thể. Có thể dùng sai phân hoặc đạo hàm nếu mô hình có tính liên tục.

### 13.3. Global sensitivity

Khảo sát toàn miền tham số để xác định biến nào đóng góp nhiều vào độ biến thiên đầu ra. Phương pháp có thể cần nhiều lần chạy.

### 13.4. Tornado chart

Tornado chart sắp xếp các biến theo mức ảnh hưởng từ lớn đến nhỏ. Nó giúp nhận ra biến nào đáng được đo lường hoặc kiểm soát tốt hơn.

### 13.5. Sensitivity và uncertainty

Sensitivity cho biết đầu ra nhạy với biến nào. Uncertainty mô tả mức độ chưa chắc chắn của biến hoặc mô hình. Hai khái niệm cần được trình bày riêng.

## 14. Constraint và invariant trong simulation

Scenario có thể khai báo điều kiện phải luôn đúng.

### 14.1. Invariant

Ví dụ:

~~~text
invariant "balance-never-negative" {
    always account.balance >= 0
}
~~~

Simulator kiểm tra invariant sau mỗi transition hoặc tại các checkpoint được định nghĩa.

### 14.2. Safety property

Safety property nói rằng một trạng thái xấu không bao giờ được xảy ra, ví dụ một giao dịch chưa xác thực không thể được đánh dấu SETTLED.

### 14.3. Liveness property

Liveness property nói rằng một tiến trình mong đợi cuối cùng sẽ xảy ra, ví dụ mọi request được chấp nhận cuối cùng sẽ hoàn tất hoặc bị từ chối rõ ràng.

### 14.4. Resource constraint

~~~text
constraint {
    active_workers <= 20
    queue_length <= 500
}
~~~

### 14.5. Violation report

Khi invariant thất bại, report nên chứa:

- Tên invariant.
- Scenario run ID.
- Event hoặc transition gây vi phạm.
- State trước và sau.
- Thời điểm mô phỏng.
- Trace liên quan.

Không chỉ báo “constraint failed” nếu người dùng cần tìm nguyên nhân.

## 15. Mô phỏng luật xung đột và độ ưu tiên

Trong DSL luật, nhiều rule có thể cùng thỏa mãn một trạng thái.

### 15.1. Overlap detection

Scenario generator có thể tìm đầu vào làm hai rule cùng khớp. Điều này giúp phát hiện overlap ngoài dự kiến.

### 15.2. Rule shadowing

Một rule có thể không bao giờ được kích hoạt vì rule ưu tiên cao hơn luôn bắt trước. Simulator có thể đo activation count và phát hiện rule bị shadow.

### 15.3. Conflict report

Khi hai rule đề xuất hành động không tương thích, simulator có thể báo conflict thay vì âm thầm chọn một kết quả nếu chính sách yêu cầu rõ ràng.

### 15.4. Salience và agenda

Nếu engine dùng salience hoặc agenda, simulator nên hiển thị thứ tự kích hoạt và lý do. Không chỉ hiển thị kết quả cuối cùng.

### 15.5. Termination

Một tập luật có thể kích hoạt lặp lại không dừng. Cần giới hạn số lần firing, phát hiện trạng thái lặp hoặc yêu cầu điều kiện dừng.

## 16. Mô phỏng workflow và hệ thống sự kiện

Với workflow DSL, scenario có thể mô phỏng luồng task và failure.

### 16.1. Task graph

Workflow được biểu diễn thành graph các task và dependency. Simulator có thể dùng scheduler giả lập để chạy task theo duration và resource constraint.

### 16.2. Failure injection

~~~text
faults {
    at 5m: fail service "payment-api"
    probability task "send-receipt" = 0.02
}
~~~

Fault injection giúp kiểm tra retry, timeout, fallback và compensation. Fault cần được bật rõ ràng trong scenario để không nhầm với cấu hình production.

### 16.3. Retry behavior

Quan sát số lần retry, backoff, thời gian hoàn tất và khả năng tạo side effect trùng lặp.

### 16.4. Queue và backpressure

Mô phỏng producer nhanh hơn consumer để quan sát queue depth, rejection, dropped event và latency.

### 16.5. Resource contention

Đặt giới hạn connection, worker hoặc quota để xem task nào phải chờ và thời gian chờ thay đổi thế nào.

### 16.6. Compensation

Với saga hoặc workflow nhiều bước, mô phỏng lỗi sau một side effect để xác nhận compensation được kích hoạt đúng và trạng thái cuối được ghi nhận.

## 17. Kết quả và cách trình bày

Một simulation run nên trả về kết quả có thể đọc và so sánh.

### 17.1. Summary

Summary có thể gồm:

- Scenario name.
- Run ID.
- Ruleset version.
- Input profile.
- Số lần chạy.
- Thời lượng mô phỏng.
- Outcome distribution.
- Số invariant vi phạm.
- Trạng thái hoàn tất.

### 17.2. Decision trace

Trace giải thích mỗi decision:

1. Input và state được đọc.
2. Rule được đánh giá.
3. Rule khớp hoặc không khớp.
4. Conflict resolution.
5. Outcome được chọn.
6. State transition hoặc action giả lập.

### 17.3. Timeline

Timeline thể hiện event, task và transition theo thời gian. Nó đặc biệt hữu ích khi thứ tự hoặc độ trễ ảnh hưởng outcome.

### 17.4. Table

Bảng scenario phù hợp để so sánh input và outcome:

| Scenario | Amount | Risk | Verified | Outcome |
|---|---:|---|---|---|
| A | 1200 | LOW | true | APPROVE |
| B | 7200 | LOW | true | MANUAL_REVIEW |
| C | 900 | HIGH | true | MANUAL_REVIEW |
| D | 900 | LOW | false | REJECT |

Đây là dữ liệu minh họa cho rule đã nêu, không phải kết quả từ một engine cụ thể.

### 17.5. Chart

Chart có thể biểu diễn:

- Outcome rate.
- Queue length theo thời gian.
- Latency percentile.
- Resource utilization.
- Số lần rule được kích hoạt.
- Độ nhạy của output theo input.

### 17.6. Uncertainty band

Với Monte Carlo, có thể hiển thị median cùng percentile hoặc confidence interval. Không nên chỉ hiển thị một đường trung bình nếu tail risk quan trọng.

## 18. So sánh nhiều kịch bản và phiên bản luật

So sánh là một trong những giá trị lớn của simulation.

### 18.1. Baseline và candidate

Baseline là chính sách đang dùng; candidate là chính sách đề xuất. Cả hai nên chạy trên cùng input set và giả định để so sánh công bằng.

### 18.2. Paired simulation

Trong mô phỏng ngẫu nhiên, dùng cùng random seed hoặc cùng các mẫu đầu vào cho hai phiên bản giúp giảm biến thiên do khác mẫu. Cần lưu ý engine có thể tiêu thụ số ngẫu nhiên theo thứ tự khác nhau khi logic thay đổi.

### 18.3. Outcome diff

Có thể phân loại:

- Outcome không đổi.
- Outcome đổi từ approve sang review.
- Outcome đổi từ reject sang approve.
- Một phiên bản không đưa ra quyết định.
- Invariant chỉ thất bại ở một phiên bản.

### 18.4. Rule diff

So sánh activation count và decision trace để xác định rule nào tạo ra khác biệt.

### 18.5. Impact analysis

Ước lượng số record hoặc tỷ lệ giao dịch bị ảnh hưởng bởi candidate. Với dữ liệu thật, cần dùng dữ liệu đã được phép và bảo vệ thông tin cá nhân.

### 18.6. Rollout scenario

Có thể mô phỏng rollout theo nhóm người dùng, tenant hoặc tỷ lệ traffic để đánh giá rủi ro chuyển đổi.

## 19. Reproducibility và provenance

Simulation result chỉ hữu ích lâu dài nếu có thể biết nó được tạo từ những điều kiện nào.

### 19.1. Run manifest

Một run manifest có thể ghi:

- Scenario definition version.
- Ruleset version hoặc digest.
- Simulator version.
- Input dataset ID hoặc digest.
- Assumptions.
- Random seed và PRNG.
- Timezone và simulation clock policy.
- Runtime/backend version.
- Configuration flags.

### 19.2. Immutable inputs

Nếu dataset hoặc ruleset thay đổi sau khi chạy, không nên dùng cùng tên version giả định. Dùng content digest hoặc immutable version ID.

### 19.3. Deterministic replay

Với mô phỏng xác định, cùng manifest và input phải tạo kết quả tương đương. Với mô phỏng ngẫu nhiên, cần ghi đủ seed và cách lấy mẫu.

### 19.4. External dependencies

Không gọi API production không kiểm soát trong simulation. Nếu cần dữ liệu ngoài, lưu snapshot hoặc dùng fixture có version để tái lập.

### 19.5. Result provenance

Mỗi chart hoặc report nên liên kết với run ID và manifest. Nếu người dùng thay đổi giả định, tạo run mới thay vì ghi đè kết quả cũ.

## 20. Kiểm soát side effect và dữ liệu

Simulation có thể dùng dữ liệu gần giống production và có logic giống production, vì vậy cần giới hạn tác động.

### 20.1. Effect isolation

Các thao tác gửi email, chuyển tiền, ghi database hoặc gọi API cần được thay bằng adapter giả hoặc sandbox.

### 20.2. Dry-run semantics

Một flag dry_run không đủ nếu code vẫn gọi dịch vụ ngoài. Runtime cần bảo đảm mọi effect được intercept hoặc từ chối theo policy.

### 20.3. Synthetic data

Dữ liệu tổng hợp giúp tránh đưa thông tin cá nhân vào môi trường mô phỏng. Generator nên giữ các đặc tính thống kê cần thiết mà không sao chép định danh thật.

### 20.4. Data minimization

Chỉ nạp các trường cần cho scenario. Không cần dùng toàn bộ customer record nếu luật chỉ cần risk band và trạng thái xác minh.

### 20.5. Access control

Scenario, input dataset, trace và report có thể chứa thông tin nhạy cảm. Cần quyền đọc, chạy, chia sẻ và export riêng.

### 20.6. Retention

Run output có thể tăng nhanh, đặc biệt với Monte Carlo. Đặt retention, archive và deletion policy phù hợp.

## 21. Performance và quản lý tài nguyên mô phỏng

Simulation có thể chạy hàng nghìn hoặc hàng triệu lần.

### 21.1. Parallel runs

Các scenario độc lập có thể chạy song song. Mỗi run phải có state, random stream và output riêng.

### 21.2. Deterministic parallelism

Nếu kết quả cần tái lập, random stream nên được chia theo run hoặc partition ổn định. Không dùng một generator mutable chung mà thứ tự lấy số phụ thuộc lịch thread.

### 21.3. Bounded concurrency

Giới hạn số run đồng thời để tránh hết memory, CPU hoặc quota.

### 21.4. Sampling

Với không gian đầu vào lớn, có thể dùng sampling thay vì chạy toàn bộ tổ hợp. Phải ghi phương pháp sampling để diễn giải đúng coverage và uncertainty.

### 21.5. Early stopping

Một số Monte Carlo run có thể dừng khi confidence interval đủ hẹp hoặc tiêu chí hội tụ đạt. Điều kiện dừng cần minh bạch và không được diễn giải kết quả như thể đã chạy số lần cố định.

### 21.6. Checkpoint

Run dài có thể lưu checkpoint để tiếp tục sau sự cố. Checkpoint phải bao gồm state, event queue, random generator state và run manifest phù hợp.

### 21.7. Cost budget

Có thể đặt giới hạn thời gian, số lần chạy, memory hoặc lượng event. Khi vượt giới hạn, simulator trả trạng thái incomplete hoặc budget_exceeded thay vì báo thành công với dữ liệu thiếu.

## 22. Triển khai mô phỏng bằng Java

Một simulator Java có thể tách scenario definition, engine và collector.

### 22.1. Scenario model

~~~java
import java.util.Map;

public record Scenario(
        String id,
        String rulesetVersion,
        Map<String, Object> inputs,
        long seed
) {
}
~~~

Map trong ví dụ đơn giản hóa dữ liệu. Một implementation có kiểu nên dùng schema hoặc value model rõ ràng thay vì để mọi giá trị là Object.

### 22.2. Simulation result

~~~java
import java.util.List;
import java.util.Map;

public record SimulationResult(
        String runId,
        String outcome,
        List<String> matchedRules,
        Map<String, Object> observations,
        List<String> violations
) {
}
~~~

Result nên giữ run ID và provenance để kết quả có thể được truy vết về scenario và ruleset.

### 22.3. Engine interface

~~~java
public interface SimulationEngine {
    SimulationResult run(Scenario scenario);
}
~~~

Engine có thể dùng cùng rule evaluator với production nhưng cần effect adapter riêng cho simulation.

### 22.4. Event queue

~~~java
import java.time.Duration;

public record SimulationEvent(
        Duration at,
        long sequence,
        String type,
        Object payload
) {
}
~~~

Comparator nên sắp xếp theo simulation time rồi sequence để có thứ tự ổn định khi nhiều event cùng thời điểm. Payload cần được kiểm tra kiểu và không chứa dữ liệu ngoài phạm vi.

### 22.5. Random generator

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

RandomGenerator random =
    RandomGeneratorFactory.of("L64X128MixRandom").create(48291L);
~~~

API RandomGenerator có từ Java 17. Để tái lập qua môi trường, cần pin thuật toán cụ thể và phiên bản runtime; chỉ lưu seed là chưa đủ nếu implementation thay đổi.

### 22.6. Isolated state

~~~java
final class SimulationContext {
    private final String runId;
    private final java.util.Map<String, Object> state;
    private final RandomGenerator random;

    SimulationContext(
            String runId,
            java.util.Map<String, Object> initialState,
            RandomGenerator random
    ) {
        this.runId = runId;
        this.state = new java.util.HashMap<>(initialState);
        this.random = random;
    }

    String runId() {
        return runId;
    }

    java.util.Map<String, Object> state() {
        return state;
    }

    RandomGenerator random() {
        return random;
    }
}
~~~

Đây là ví dụ minh họa. State có thể cần deep copy hoặc immutable value; HashMap copy nông không cô lập các object mutable lồng bên trong.

### 22.7. Effect adapter

~~~java
public interface PaymentGateway {
    PaymentResult authorize(PaymentRequest request);
}

final class SimulatedPaymentGateway implements PaymentGateway {
    @Override
    public PaymentResult authorize(PaymentRequest request) {
        return PaymentResult.approved("SIMULATED");
    }
}
~~~

Simulator inject adapter giả để không thực hiện thanh toán thật. Trong production, adapter thật được cấu hình riêng và không được vô tình nạp vào simulation profile.

## 23. Tích hợp simulation với DSL editor và workbench

Một workbench có thể cho phép người dùng khai báo, chạy và khám phá scenario ngay cạnh source.

### 23.1. Scenario editor

Editor có thể hỗ trợ completion cho input, event, assumption, rule version và observation.

### 23.2. Validation

Language server kiểm tra kiểu, đơn vị, tên biến và reference. Ví dụ amount cần Decimal, duration cần đơn vị thời gian và ruleset version phải tồn tại.

### 23.3. Run command

Một command có thể chạy scenario đang mở hoặc tập scenario được chọn. Cần hiển thị rõ profile là simulation và môi trường không có side effect production.

### 23.4. Result viewer

Workbench có thể hiển thị decision trace, event timeline, chart, table và invariant violations.

### 23.5. Source navigation

Chọn rule trong trace có thể mở đoạn DSL tương ứng. Chọn event có thể mở khai báo event hoặc input tạo ra nó.

### 23.6. Scenario versioning

Scenario là artifact có thể review và quản lý bằng Git. Nên lưu assumptions, ruleset version và dataset reference để người khác tái chạy.

## 24. Kiểm thử và xác nhận simulator

Simulator cũng là phần mềm cần được kiểm thử.

### 24.1. Semantic equivalence

Với cùng input xác định, simulation evaluator cần cho kết quả phù hợp với production evaluator khi không có effect bên ngoài. Có thể dùng test chung cho rule semantics.

### 24.2. Determinism test

Chạy lại cùng scenario manifest và xác nhận output giống nhau trong phạm vi bảo đảm. Nếu có floating-point hoặc nondeterministic concurrency, xác định tolerance và điều kiện so sánh.

### 24.3. Event ordering test

Cho nhiều event cùng timestamp và xác nhận tie-break policy.

### 24.4. Isolation test

Chạy nhiều scenario song song và xác nhận state, event queue và random stream không bị chia sẻ ngoài ý muốn.

### 24.5. Side-effect test

Thay adapter production bằng adapter có thể phát hiện lời gọi ngoài. Xác nhận simulation không gửi request hoặc ghi dữ liệu thật.

### 24.6. Boundary test

Kiểm tra ngưỡng, deadline, số lần retry, quota và giới hạn tài nguyên.

### 24.7. Statistical validation

Với Monte Carlo, kiểm tra generator có đặc tính dự kiến, số lần chạy đủ cho độ chính xác mong muốn và kết quả không nhạy bất thường với seed.

### 24.8. Model validation

So sánh mô hình với dữ liệu quan sát hoặc chuyên gia miền. Một simulator có thể chạy đúng code nhưng vẫn đưa ra dự đoán sai nếu assumptions không phản ánh thực tế.

## 25. Diễn giải kết quả và giới hạn

Simulation output không phải lời tiên tri. Nó là kết quả của mô hình, dữ liệu và giả định đã chọn.

### 25.1. Model risk

Mô hình có thể bỏ sót biến quan trọng, giả định sai quan hệ hoặc mô tả đơn giản hóa hành vi thực tế.

### 25.2. Input uncertainty

Đầu vào có thể không chính xác hoặc phân phối không ổn định. Cần trình bày nguồn dữ liệu và mức độ tin cậy.

### 25.3. Parameter uncertainty

Các tham số như arrival rate hoặc failure probability có thể chỉ là ước lượng. Nên chạy sensitivity analysis và nhiều giả định hợp lý.

### 25.4. Structural uncertainty

Có thể tồn tại nhiều cách mô hình hóa cùng một quy trình. Kết quả nhạy với cấu trúc mô hình cần được nêu rõ.

### 25.5. Correlation và causality

Tương quan giữa hai biến trong dữ liệu không tự chứng minh một biến gây ra biến kia. Scenario can thiệp vào một biến cần mô hình nhân quả hoặc giả định được giải thích.

### 25.6. Không ngoại suy tùy tiện

Kết quả trong phạm vi tải 100 đến 200 request/phút không tự bảo đảm hành vi ở 10.000 request/phút. Cần kiểm chứng mô hình ở phạm vi dự kiến.

### 25.7. Decision support

Simulation hỗ trợ người ra quyết định bằng evidence và trade-off. Quyết định cuối vẫn cần xét chính sách, pháp lý, đạo đức và yếu tố không có trong mô hình.

## 26. Những sai lầm thường gặp

### 26.1. Nhầm simulation với production dry-run

Một chế độ chỉ đặt tên dry-run nhưng vẫn gọi API thật có thể gây side effect. Cần intercept hoặc từ chối effect ở runtime.

### 26.2. Không pin ruleset version

Ruleset thay đổi làm kết quả khó tái lập. Ghi version hoặc digest của luật trong run manifest.

### 26.3. Dùng dữ liệu đầu vào không đại diện

Scenario quá đơn giản hoặc dữ liệu thiên lệch làm kết quả không phản ánh vận hành. Chọn input theo mục tiêu và ghi rõ nguồn.

### 26.4. Không lưu giả định

Chỉ lưu output mà không lưu assumptions khiến người khác không hiểu kết quả dựa trên điều kiện nào.

### 26.5. Dùng random seed nhưng không pin PRNG

Cùng seed với thuật toán hoặc thứ tự lấy mẫu khác có thể tạo chuỗi khác. Lưu cả generator và cấu hình.

### 26.6. Không cô lập state giữa các run

Scenario có thể ảnh hưởng lẫn nhau qua mutable state, cache hoặc queue. Tạo context độc lập và reset đầy đủ.

### 26.7. Bỏ qua event ordering

Hai event cùng timestamp hoặc event đến trễ có thể làm kết quả khác nhau. Định nghĩa tie-break và late-event policy.

### 26.8. Chỉ nhìn kết quả cuối

Outcome không giải thích vì sao luật được chọn. Thu thập rule trace, state transition và event timeline.

### 26.9. Chạy Monte Carlo quá ít

Ước lượng từ ít mẫu có thể dao động mạnh, đặc biệt với sự kiện hiếm. Đánh giá confidence interval và hội tụ.

### 26.10. Giả định các biến độc lập

Biến đầu vào có thể tương quan. Mô hình hóa sai có thể đánh giá thấp tail risk.

### 26.11. Đọc chart mà không xem uncertainty

Đường trung bình có thể che giấu percentile xấu hoặc xác suất vượt ngưỡng. Trình bày phân phối khi rủi ro đuôi quan trọng.

### 26.12. Không xác nhận model với thực tế

Simulator có thể thực thi đúng nhưng mô hình sai. So sánh dự đoán với quan sát và cập nhật assumptions.

### 26.13. Dùng production secret hoặc dữ liệu cá nhân không cần thiết

Simulation nên dùng synthetic data hoặc snapshot đã được phép, giới hạn truy cập và retention.

### 26.14. Không đặt budget

Parameter sweep hoặc Monte Carlo có thể tạo hàng triệu run. Đặt giới hạn tài nguyên và báo trạng thái incomplete khi dừng sớm.

## 27. Quy trình xây dựng mô phỏng kịch bản

Một quy trình triển khai có thể gồm:

1. **Xác định câu hỏi.** Làm rõ cần khám phá quyết định, rủi ro, hiệu năng hay thay đổi chính sách.
2. **Chọn phạm vi mô hình.** Xác định ruleset, state, event và dependency cần mô phỏng.
3. **Xác định dữ liệu.** Chọn input, dataset, phân phối và mức ẩn danh.
4. **Ghi assumptions.** Định nghĩa điều kiện cố định, giới hạn và nguồn tham số.
5. **Thiết kế scenario DSL.** Khai báo initial state, inputs, events, faults và observations.
6. **Chọn simulation model.** Deterministic, discrete-event, time-stepped, Monte Carlo hoặc agent-based.
7. **Cô lập side effect.** Dùng adapter giả hoặc sandbox cho mọi thao tác bên ngoài.
8. **Pin version và seed.** Ghi ruleset, simulator, dataset, PRNG và configuration.
9. **Chạy baseline.** Tạo kết quả tham chiếu và lưu manifest.
10. **Chạy biến thể.** What-if, parameter sweep, scenario matrix hoặc random sampling.
11. **Thu thập trace và metrics.** Ghi outcome, rule activation, state change và invariant.
12. **So sánh và phân tích.** Tính delta, sensitivity, uncertainty và confidence interval.
13. **Xác nhận mô hình.** Đối chiếu với dữ liệu quan sát hoặc chuyên gia miền.
14. **Lưu và chia sẻ kết quả.** Gắn run ID, provenance, quyền truy cập và retention.
15. **Đưa ra quyết định có điều kiện.** Ghi rõ giới hạn mô hình và giả định cần theo dõi khi triển khai.

## 28. Câu hỏi tự kiểm tra

1. Mô phỏng kịch bản là gì và nó hỗ trợ DSL luật và quyết định như thế nào?
2. Phân biệt thực thi thật, kiểm thử luật và mô phỏng.
3. Một scenario cần những thành phần nào để có thể tái lập?
4. Phân biệt deterministic, what-if, discrete-event, time-stepped, Monte Carlo và agent-based simulation.
5. Vì sao compiler nên giữ ruleset semantics nhất quán giữa simulation và production?
6. Initial state, transition và snapshot có vai trò gì?
7. Event ordering, duplicate event và late event ảnh hưởng mô phỏng ra sao?
8. Simulation clock khác wall-clock như thế nào?
9. What-if analysis, parameter sweep và scenario matrix khác nhau ra sao?
10. Full factorial và pairwise testing có trade-off gì?
11. Monte Carlo dùng random seed và phân phối đầu vào để làm gì?
12. Vì sao cần xem xét tương quan giữa các biến đầu vào?
13. Sensitivity analysis cho biết điều gì và khác uncertainty analysis ra sao?
14. Invariant, safety property và liveness property khác nhau như thế nào?
15. Simulator có thể phát hiện rule overlap, conflict và shadowing ra sao?
16. Vì sao cần cô lập state và effect adapter giữa các scenario run?
17. Run manifest cần lưu những thông tin nào để hỗ trợ reproducibility?
18. Hãy mô tả cách so sánh ruleset hiện tại và candidate trên cùng một tập scenario.
19. Những chỉ số nào giúp đánh giá kết quả Monte Carlo và độ tin cậy của mô hình?
20. Hãy thiết kế một scenario mô phỏng tải workflow có retry, timeout, queue và lỗi dịch vụ; nêu assumptions, observations và invariant.
