# Xung đột giữa các luật

## 1. Xung đột giữa các luật là gì?

Trong DSL luật và quyết định (*rule and decision DSL*), một chương trình thường gồm nhiều luật mô tả điều kiện và hành động. Khi dữ liệu thay đổi, nhiều luật có thể đồng thời thỏa điều kiện. Rule engine phải quyết định luật nào được thực thi trước, luật nào được hoãn, luật nào bị loại khỏi lượt xử lý và khi nào quá trình đánh giá kết thúc.

**Xung đột giữa các luật (*rule conflict*)** là tình huống có từ hai luật trở lên cùng đủ điều kiện được xem xét hoặc cùng muốn tác động lên một trạng thái, nhưng engine cần áp dụng chính sách để lựa chọn, sắp xếp hoặc phối hợp chúng.

Ví dụ:

~~~text
rule "premium-discount" {
    when customer.tier == "PREMIUM"
    then order.discount = 20
}

rule "campaign-discount" {
    when order.campaign == "SUMMER"
    then order.discount = 15
}
~~~

Nếu khách hàng thuộc tier PREMIUM và đơn hàng tham gia chiến dịch SUMMER, cả hai luật đều có thể được kích hoạt. Cả hai cùng ghi vào order.discount nhưng đưa ra giá trị khác nhau. Engine cần có quy tắc xác định kết quả: ưu tiên một luật, kết hợp hai mức giảm theo công thức, từ chối trường hợp xung đột hoặc chuyển sang một luật quyết định tổng hợp.

Xung đột không nhất thiết là lỗi. Nhiều hệ thống được thiết kế để có nhiều luật cùng match. Vấn đề nằm ở việc engine có chính sách xử lý rõ ràng, có thể giải thích và cho kết quả phù hợp với semantics của miền hay không.

## 2. Phân biệt match, activation, firing và conflict

Các khái niệm sau thường xuất hiện trong rule engine:

- **Match:** một tập dữ liệu hoặc sự kiện thỏa pattern và điều kiện của luật.
- **Activation:** một cơ hội thực thi luật được tạo ra từ một match cụ thể.
- **Conflict set:** tập các activation đang chờ được xử lý.
- **Agenda:** cấu trúc quản lý thứ tự và trạng thái của các activation.
- **Firing:** hành động thực thi phần then/action của một luật.
- **Conflict resolution:** chính sách chọn activation tiếp theo trong conflict set.

Ví dụ có ba luật:

~~~text
rule "check-age" {
    when customer.age >= 18
    then customer.adult = true
}

rule "verify-email" {
    when customer.emailVerified == true
    then customer.verified = true
}

rule "enable-account" {
    when customer.adult == true and customer.verified == true
    then customer.enabled = true
}
~~~

Nếu tuổi và email đã thỏa hai luật đầu, engine có thể tạo hai activation. Khi một luật fire và cập nhật trạng thái, luật thứ ba có thể trở thành eligible. Conflict set có thể thay đổi sau mỗi lần firing.

Một rule có thể match nhưng chưa được fire vì:
- Activation có priority thấp hơn.
- Một activation khác được chọn trước.
- Activation bị loại do group hoặc agenda policy.
- Điều kiện không còn đúng sau khi dữ liệu thay đổi.
- Luật đã fire cho cùng một bộ dữ liệu và engine áp dụng cơ chế ngăn lặp.
- Execution bị dừng hoặc hủy.

Vì vậy, không nên xem số luật match là số luật đã thực thi.

## 3. Các loại xung đột

### 3.1. Xung đột lựa chọn (agenda conflict)

Nhiều activation cùng chờ xử lý. Engine cần chọn activation tiếp theo theo priority, recency, salience, thứ tự hoặc một chiến lược khác.

Ví dụ hai luật cùng match nhưng chỉ một luật được fire trước. Đây là xung đột về thứ tự xử lý, ngay cả khi action của chúng không ghi cùng một dữ liệu.

### 3.2. Xung đột cập nhật (write conflict)

Nhiều luật cập nhật cùng một key hoặc cùng một object field.

~~~text
rule "set-high-risk" {
    when transaction.amount > 100000
    then transaction.risk = "HIGH"
}

rule "set-low-risk-for-member" {
    when customer.member == true
    then transaction.risk = "LOW"
}
~~~

Nếu cả hai điều kiện đúng, giá trị cuối cùng có thể phụ thuộc thứ tự fire. Đây là dấu hiệu cần quy định precedence hoặc thay đổi mô hình quyết định để chỉ có một nơi sở hữu kết quả risk.

### 3.3. Xung đột side effect

Hai luật có thể gọi các hành động ngoài hệ thống không tương thích, chẳng hạn:
- Một luật phê duyệt thanh toán, luật khác hủy giao dịch.
- Một luật gửi email chấp thuận, luật khác gửi email từ chối.
- Một luật tạo reservation, luật khác giải phóng reservation.

Side effect khó đảo ngược hơn cập nhật dữ liệu trong bộ nhớ. Vì vậy, không nên để thứ tự fire ngẫu nhiên quyết định hành động bên ngoài.

### 3.4. Xung đột kết quả quyết định

Nhiều luật cùng đưa ra các quyết định nghiệp vụ khác nhau nhưng không trực tiếp ghi cùng một field. Ví dụ một luật trả về ALLOW, luật khác trả về DENY. Engine cần có policy tổng hợp như deny-overrides, permit-overrides hoặc một bảng quyết định có thứ tự.

### 3.5. Xung đột dữ liệu và fact

Trong hệ thống production, một luật có thể retract hoặc update fact mà activation khác đang dựa vào. Activation cũ có thể không còn hợp lệ. Đây là xung đột về tính mới và tính nhất quán của dữ liệu.

### 3.6. Xung đột tài nguyên

Nhiều luật cùng yêu cầu một tài nguyên giới hạn, ví dụ hạn mức, quota, slot hoặc inventory. Cần arbitration dựa trên reservation, transaction hoặc thứ tự nghiệp vụ. Chỉ sắp xếp activation chưa đủ để bảo đảm không vượt quota khi có concurrency.

## 4. Conflict set và agenda

### 4.1. Conflict set

Conflict set là tập các activation hiện đủ điều kiện để fire. Một activation thường liên kết với:
- Rule ID và rule version.
- Match hoặc tuple fact.
- Salience/priority.
- Thời điểm được tạo.
- Agenda group hoặc activation group.
- Trạng thái của các fact liên quan.
- Metadata dùng cho conflict resolution.

Ví dụ:

~~~text
Conflict set
------------------------------------------------
Activation A: premium-discount, salience 20
Activation B: campaign-discount, salience 10
Activation C: audit-order, salience  5
~~~

Nếu engine dùng salience cao hơn trước, activation A sẽ được chọn đầu tiên. Tuy nhiên, policy đó chỉ quyết định thứ tự; nó không tự giải quyết việc hai luật cùng ghi discount nếu luật thứ hai vẫn tiếp tục fire.

### 4.2. Agenda

Agenda quản lý các activation đang chờ, đã bị hủy hoặc đã được xử lý. Một engine có thể dùng priority queue, ordered list hoặc cấu trúc chuyên biệt.

Agenda có thể hỗ trợ:
- Thêm activation mới.
- Xóa activation không còn hợp lệ.
- Sắp xếp theo conflict strategy.
- Tạm dừng hoặc kích hoạt group.
- Ngăn một activation lặp lại theo policy.
- Giải thích lý do một activation được chọn.

### 4.3. Vòng lặp thực thi

Một vòng forward-chaining khái niệm:

~~~text
Nạp facts và rules
       |
       v
Match rules với facts
       |
       v
Tạo conflict set
       |
       v
Chọn activation theo agenda
       |
       v
Fire rule action
       |
       v
Cập nhật / thêm / xóa facts
       |
       v
Tính lại các match bị ảnh hưởng
       |
       +------> còn activation? ------+
       |                              |
       +---------- có ----------------+
                      |
                      v
                 Chọn tiếp
                      |
                     không
                      v
                 Hoàn tất
~~~

Sau mỗi lần fire, conflict set có thể thay đổi. Một luật đã match trước đó có thể mất điều kiện, và luật khác có thể được kích hoạt bởi fact mới.

### 4.4. Agenda là cơ chế, policy là quy tắc

Agenda là nơi quản lý activation. Conflict resolution policy quy định cách sắp xếp hoặc chọn chúng. Không nên đồng nhất cấu trúc dữ liệu agenda với chính sách nghiệp vụ.

## 5. Salience và priority

### 5.1. Salience

Salience là một giá trị ưu tiên gắn với luật hoặc activation trong một số rule engine. Giá trị cao hơn thường được chọn trước, nhưng chiều ưu tiên cụ thể phải theo engine.

Ví dụ:

~~~text
rule "block-fraud" salience 100 {
    when transaction.fraudScore >= 90
    then transaction.status = "BLOCKED"
}

rule "apply-reward" salience 20 {
    when customer.rewardEligible
    then grantReward(customer)
}
~~~

Nếu cả hai activation cùng tồn tại và engine chọn salience cao trước, block-fraud được fire trước.

### 5.2. Priority cố định và priority động

Priority có thể:
- Cố định trong định nghĩa rule.
- Được cấu hình bên ngoài.
- Tính từ dữ liệu match.
- Tính từ business policy hoặc context.

Priority động linh hoạt nhưng có thể khó dự đoán. Nếu giá trị priority thay đổi khi fact thay đổi, engine cần xác định thời điểm tính lại và cách cập nhật agenda.

### 5.3. Không dùng priority để che giấu semantics

Nếu hai luật mâu thuẫn về cùng một quyết định, đặt priority chỉ giải quyết thứ tự. Nếu luật có priority thấp vẫn fire sau đó, nó có thể ghi đè kết quả của luật trước.

Có thể cần:
- Dùng activation group để chỉ một luật được chọn.
- Dùng điều kiện loại trừ lẫn nhau.
- Dùng một luật tổng hợp.
- Dừng hoặc hủy các activation còn lại sau quyết định.
- Thiết kế action không ghi đè kết quả đã chốt.

### 5.4. Priority và fairness

Nếu một luật luôn có priority cao, các luật ưu tiên thấp có thể bị trì hoãn vô thời hạn. Đây là starvation. Nếu hệ thống yêu cầu mọi activation hợp lệ cuối cùng đều được xử lý, cần chính sách fairness hoặc giới hạn ưu tiên liên tục.

## 6. Các chiến lược conflict resolution

Không có một chiến lược phù hợp cho mọi DSL. Các lựa chọn phổ biến:

| Chiến lược | Nguyên tắc | Trường hợp phù hợp |
|---|---|---|
| Salience/priority | Activation ưu tiên cao hơn chạy trước | Luật khẩn cấp hoặc policy có thứ tự |
| Recency | Ưu tiên activation liên quan đến fact mới cập nhật | Forward-chaining theo dữ liệu mới |
| Specificity | Ưu tiên luật có điều kiện cụ thể hơn | Luật ngoại lệ so với luật tổng quát |
| Rule order | Dùng thứ tự khai báo hoặc thứ tự cấu hình | Bộ luật nhỏ, thứ tự được đặc tả |
| Agenda group | Chỉ xử lý nhóm đang được kích hoạt | Phân pha hoặc phân miền |
| Activation group | Các luật trong nhóm loại trừ lẫn nhau | Chọn một kết quả trong nhóm quyết định |
| Custom comparator | So sánh theo policy miền | Quyết định có tiêu chí riêng |
| Random/tie-break | Chọn theo thứ tự phụ hoặc ngẫu nhiên | Chỉ khi semantics cho phép và có kiểm soát |

### 6.1. Salience ordering

Sắp xếp activation theo priority. Nếu bằng nhau, cần tie-break xác định như sequence number hoặc rule ID.

### 6.2. Recency

Ưu tiên activation có fact mới được cập nhật gần đây. Điều này có thể hữu ích trong hệ thống phản ứng với sự kiện, nhưng không phải lúc nào dữ liệu mới nhất cũng quan trọng nhất về nghiệp vụ.

### 6.3. Specificity

Luật có nhiều điều kiện hoặc pattern hẹp hơn có thể được xem là cụ thể hơn. Tuy nhiên, đếm số điều kiện không luôn đo được mức đặc hiệu thực sự. Hai predicate có độ phức tạp khác nhau có thể mang ý nghĩa khác nhau.

Nếu dùng specificity, cần định nghĩa chính xác cách đo và kiểm thử các trường hợp ranh giới.

### 6.4. Rule order

Một số engine sử dụng thứ tự khai báo hoặc thứ tự trong file làm tie-break. Cách này dễ hiểu với tập luật nhỏ, nhưng có thể làm thay đổi kết quả khi người dùng chỉ di chuyển rule trong file.

Nếu rule order mang ý nghĩa nghiệp vụ, nên thể hiện nó tường minh trong DSL hoặc decision table.

### 6.5. Custom conflict resolver

Một DSL có thể cung cấp strategy riêng:

~~~java
interface ConflictResolver {
    Activation selectNext(List<Activation> candidates);
}
~~~

Resolver có thể xét tenant, loại sự kiện, deadline, mức độ rủi ro hoặc các tiêu chí miền. Cần bảo đảm resolver xác định, có giới hạn thời gian và không tạo side effect.

### 6.6. Tie-breaking

Nếu hai activation có cùng mọi tiêu chí ưu tiên, cần quy định tie-break. Có thể dùng stable rule ID, activation sequence hoặc một thứ tự đã công bố. Không nên dựa vào iteration order không xác định của collection.

## 7. Mutual exclusion và activation groups

### 7.1. Điều kiện loại trừ lẫn nhau

Có thể thiết kế điều kiện để hai luật không thể cùng match:

~~~text
rule "approve" {
    when order.risk == "LOW"
    then decision = "APPROVE"
}

rule "reject" {
    when order.risk == "HIGH"
    then decision = "REJECT"
}
~~~

Nếu risk chỉ có một giá trị tại thời điểm đánh giá, hai điều kiện loại trừ lẫn nhau.

Tuy nhiên, nếu các điều kiện chồng lấn hoặc dữ liệu có thể thay đổi giữa các lần đánh giá, vẫn cần kiểm tra khả năng xung đột.

### 7.2. Activation group

Một số engine hỗ trợ activation group, còn gọi là ruleflow group kiểu XOR hoặc nhóm loại trừ. Khi một activation trong nhóm fire, các activation khác cùng nhóm có thể bị hủy.

Ví dụ:

~~~text
activation-group "payment-decision"

rule "approve-payment" {
    when payment.eligible
    then decision = "APPROVE"
}

rule "reject-payment" {
    when payment.blocked
    then decision = "REJECT"
}
~~~

Cú pháp chỉ mang tính minh họa. Hành vi chính xác phụ thuộc engine: nhóm có thể hủy các activation khác sau khi một luật fire, nhưng không nhất thiết ngăn mọi activation mới được tạo về sau.

### 7.3. Agenda group

Agenda group phân chia luật theo nhóm xử lý. Chỉ group đang được focus mới được xử lý trong một số engine.

Ví dụ các phase:
1. Validate input.
2. Calculate eligibility.
3. Determine decision.
4. Apply side effects.

Agenda group giúp tổ chức thứ tự xử lý theo giai đoạn, nhưng không thay thế validation và conflict policy bên trong từng group.

### 7.4. Ruleflow group

Ruleflow group thường liên kết việc thực thi rule với tiến trình hoặc workflow. Một flow có thể kích hoạt nhóm luật tương ứng tại từng node. Cần phân biệt:
- Agenda group: focus của agenda.
- Activation group: loại trừ activation.
- Ruleflow group: nhóm luật gắn với flow hoặc phase.

Tên gọi và semantics có thể khác giữa các engine.

## 8. No-loop, refraction và ngăn luật lặp

### 8.1. Rule tự kích hoạt lại

Một rule có thể thay đổi fact khiến chính nó match lần nữa:

~~~text
rule "normalize-status" {
    when order.status == "new"
    then order.status = "NEW"
}
~~~

Nếu engine coi cập nhật là thay đổi mới dù giá trị không đổi, rule có thể tạo activation lặp.

### 8.2. No-loop

Một số engine có thuộc tính no-loop để tránh luật tự kích hoạt lại do chính action của nó tạo ra. Đây là chính sách cụ thể của engine, không phải giải pháp chung cho mọi vòng lặp.

### 8.3. Refraction

Refraction là cơ chế ngăn cùng một rule fire lặp lại trên cùng một tuple hoặc tập fact trong một chu kỳ, trừ khi điều kiện liên quan thay đổi theo semantics của engine.

Refraction giúp tránh lặp vô hạn nhưng cần xác định rõ:
- Identity của tuple.
- Khi nào một activation được coi là đã fire.
- Fact update nào làm activation được phép tạo lại.
- Khi nào reset lịch sử firing.

### 8.4. Lock-on-active

Một số engine có cơ chế như lock-on-active để tránh activation mới được tạo trong khi một agenda/ruleflow group đang active, theo quy tắc cụ thể của engine. Đây là công cụ kiểm soát vòng lặp và reactivation, cần hiểu semantics trước khi bật.

### 8.5. Idempotent action

Action idempotent có thể chạy nhiều lần mà kết quả cuối không thay đổi ngoài dự kiến. Ví dụ set trạng thái thành một giá trị cố định thường dễ kiểm soát hơn increment counter hoặc gửi email.

Với side effect, nên dùng idempotency key, transaction hoặc outbox để xử lý retry và firing lặp an toàn.

## 9. Xung đột giữa luật có thể thay đổi facts

Trong forward-chaining, action của luật có thể:
- Assert fact mới.
- Update fact hiện có.
- Retract fact.
- Thay đổi trạng thái object.
- Phát sự kiện cho luật khác.

Những thay đổi này làm conflict set cần được cập nhật.

### 9.1. Activation stale

Một activation được tạo từ fact ở trạng thái cũ có thể không còn hợp lệ sau khi một luật khác cập nhật fact. Engine cần kiểm tra lại hoặc invalidate activation đó.

Ví dụ, luật A kích hoạt vì order.status là PENDING. Luật B đổi status thành CANCELLED. Activation A không nên tiếp tục approve order dựa trên trạng thái PENDING cũ.

### 9.2. Truth maintenance

Truth maintenance system theo dõi fact nào được suy ra từ fact hoặc rule nào. Khi premise bị rút lại, derived fact có thể cần bị retract.

Nếu không có cơ chế này, rule engine có thể giữ lại kết luận không còn đúng sau khi dữ liệu nguồn thay đổi.

### 9.3. Dependency-aware re-evaluation

Engine có thể theo dõi dependency từ rule condition đến fact/property. Khi một fact thay đổi, chỉ các rule bị ảnh hưởng cần được đánh giá lại.

Điều này cải thiện hiệu năng và giúp xác định activation nào cần hủy.

### 9.4. Atomic updates

Nếu một action cập nhật nhiều field liên quan, các rule khác không nên nhìn thấy trạng thái trung gian không hợp lệ. Có thể dùng transaction hoặc commit theo batch để cập nhật facts nguyên tử.

## 10. Xung đột trong decision table

Decision table biểu diễn các điều kiện và kết quả dưới dạng hàng/cột. Xung đột xảy ra khi nhiều row cùng match một input.

Ví dụ:

| Rule | Customer tier | Amount | Decision |
|---|---|---:|---|
| R1 | PREMIUM | > 1000 | APPROVE |
| R2 | Any | > 5000 | MANUAL_REVIEW |
| R3 | BLOCKED | Any | REJECT |

Một khách hàng PREMIUM có amount 6000 có thể match R1 và R2. Nếu customer cũng BLOCKED thì R3 có thể match cùng lúc.

### 10.1. Hit policy

Decision table có thể định nghĩa hit policy để quy định cách xử lý nhiều row match. Một số loại phổ biến trong các mô hình quyết định:
- **Unique:** yêu cầu không quá một row match; nhiều hơn một là lỗi.
- **Any:** nhiều row có thể match nếu kết quả tương đương theo policy.
- **First:** chọn row đầu tiên theo thứ tự bảng.
- **Priority:** chọn kết quả có priority cao nhất theo thứ tự ưu tiên đã định nghĩa.
- **Rule order:** trả hoặc thực thi các kết quả theo thứ tự row.
- **Collect:** thu thập nhiều kết quả.
- **Output order:** thu thập kết quả theo thứ tự ưu tiên output.

Tên và semantics chính xác phụ thuộc tiêu chuẩn hoặc engine. Cần định nghĩa rõ hit policy của DSL thay vì chỉ dùng tên quen thuộc.

### 10.2. Unique và Any

Unique phát hiện thiết kế bảng có overlap ngoài ý muốn. Any cho phép nhiều row match nếu output tương đương. Đây là cách hữu ích khi muốn khai báo nhiều điều kiện khác nhau nhưng cùng một kết quả.

### 10.3. First và Priority

First phụ thuộc thứ tự row; Priority phụ thuộc thứ tự ưu tiên của output hoặc một ranking được định nghĩa. Chúng không giống nhau: row đầu tiên không nhất thiết có output ưu tiên cao nhất.

### 10.4. Collect

Collect dùng khi nhiều rule đóng góp vào một kết quả tập hợp, chẳng hạn danh sách lý do hoặc danh sách validation errors. Cần xác định thứ tự, loại trùng và cách xử lý phần tử xung đột.

### 10.5. Kiểm tra overlap

Có thể phân tích tĩnh decision table để tìm:
- Hai row có thể cùng match.
- Một vùng input không có row nào match.
- Hai row cùng match nhưng output khác.
- Một row bị row khác che khuất.
- Điều kiện không thể xảy ra.

Phân tích overlap giúp phát hiện xung đột trước runtime.

## 11. Chính sách tổng hợp quyết định

Không phải lúc nào chỉ chọn một luật. Một số miền cần tổng hợp nhiều kết quả.

### 11.1. Deny-overrides

Nếu bất kỳ luật nào đưa ra DENY, kết quả cuối là DENY. Các kết quả ALLOW khác không thể ghi đè.

Phù hợp với một số policy authorization hoặc kiểm soát an toàn.

### 11.2. Permit-overrides

Nếu có ít nhất một kết quả PERMIT, policy có thể trả PERMIT dù có kết quả DENY khác. Chỉ dùng khi semantics nghiệp vụ thực sự cho phép.

### 11.3. First-applicable

Chọn luật đầu tiên có điều kiện phù hợp theo thứ tự policy. Thứ tự phải được version và review vì thay đổi vị trí có thể đổi quyết định.

### 11.4. Consensus hoặc quorum

Một số hệ thống yêu cầu nhiều luật hoặc nhiều nguồn đánh giá đồng thuận. Ví dụ cần ít nhất hai trong ba policy module chấp thuận.

Cần quy định:
- Số phiếu cần thiết.
- Cách xử lý abstain.
- Cách xử lý timeout.
- Kết quả khi thiếu một evaluator.
- Cách ghi lại lý do từng vote.

### 11.5. Weighted score

Có thể cộng điểm hoặc trọng số từ nhiều rule để tạo score. Khi đó, conflict được chuyển thành bài toán tổng hợp. Cần xác định trọng số, ngưỡng, xử lý missing input và giải thích đóng góp của từng luật.

## 12. Phòng ngừa xung đột ngay từ thiết kế DSL

Tốt nhất là làm rõ semantics để xung đột không xuất hiện ngoài ý muốn.

Các cách phổ biến:

1. **Điều kiện loại trừ:** thiết kế predicate không overlap.
2. **Priority tường minh:** định nghĩa thứ tự ưu tiên có ý nghĩa nghiệp vụ.
3. **Decision table hit policy:** công bố cách xử lý nhiều row match.
4. **Rule group:** tách phase hoặc nhóm loại trừ.
5. **Single-writer principle:** chỉ một luật chịu trách nhiệm ghi một decision field.
6. **Centralized decision rule:** nhiều luật cung cấp facts, một luật tổng hợp kết quả.
7. **Explicit conflict result:** trả trạng thái CONFLICT thay vì chọn ngầm.
8. **Static overlap analysis:** phát hiện rule có thể cùng match trước khi deploy.

### 12.1. Single-writer principle

Nếu nhiều luật cùng ghi transaction.status, kết quả phụ thuộc thứ tự. Có thể thiết kế:
- Các luật đánh giá ghi recommendation riêng.
- Một luật quyết định cuối cùng đọc các recommendation.
- Một action duy nhất cập nhật transaction.status.

Ví dụ:

~~~text
rule "fraud-signal" {
    when transaction.fraudScore > 80
    then addRecommendation("BLOCK")
}

rule "credit-signal" {
    when customer.creditScore > 700
    then addRecommendation("ALLOW")
}

rule "final-decision" {
    when recommendations.available
    then transaction.decision = resolve(recommendations)
}
~~~

Cách này làm rõ nơi quyết định cuối cùng được tạo.

### 12.2. Explicit conflict state

Nếu hai kết quả không tương thích, DSL có thể biểu diễn:

~~~text
decision.status = "CONFLICT"
decision.reasons = ["RULE-A", "RULE-B"]
~~~

Ứng dụng có thể yêu cầu người dùng hoặc một policy chuyên biệt xử lý. Đây thường là lựa chọn an toàn hơn việc âm thầm chọn một kết quả không có căn cứ.

## 13. Ví dụ đầy đủ: xung đột trong xử lý đơn hàng

Giả sử hệ thống có các luật:

~~~text
rule "fraud-block" salience 100 {
    when order.fraudScore >= 90
    then order.decision = "REJECT"
}

rule "vip-approve" salience 50 {
    when customer.tier == "VIP" and order.amount < 5000
    then order.decision = "APPROVE"
}

rule "large-order-review" salience 40 {
    when order.amount >= 5000
    then order.decision = "MANUAL_REVIEW"
}
~~~

### 13.1. Input

~~~text
customer.tier = "VIP"
order.amount = 7000
order.fraudScore = 95
~~~

Các luật match:
- fraud-block vì fraudScore >= 90.
- large-order-review vì amount >= 5000.
- vip-approve không match vì amount không nhỏ hơn 5000.

Conflict set ban đầu:

~~~text
1. fraud-block          salience 100
2. large-order-review   salience 40
~~~

### 13.2. Nếu engine chỉ dùng priority

fraud-block được fire trước và đặt decision thành REJECT. Sau đó large-order-review vẫn có thể fire và ghi đè thành MANUAL_REVIEW nếu engine không hủy activation còn lại.

Do đó, priority một mình chưa chắc bảo đảm quyết định cuối cùng.

### 13.3. Nếu dùng activation group

Nếu hai luật quyết định thuộc cùng activation group, khi một luật fire, activation còn lại có thể bị hủy theo semantics của engine. Khi đó kết quả REJECT được giữ.

Tuy nhiên, phải bảo đảm activation group đúng phạm vi và không có activation mới xuất hiện sau đó làm thay đổi quyết định.

### 13.4. Nếu dùng central decision

Một cách khác là để các luật phát recommendation:

~~~text
fraud-block      -> BLOCK
large-order      -> REVIEW
vip-approve      -> ALLOW
~~~

Sau đó một resolver có policy:

~~~text
if any recommendation == BLOCK:
    decision = REJECT
else if any recommendation == REVIEW:
    decision = MANUAL_REVIEW
else if any recommendation == ALLOW:
    decision = APPROVE
else:
    decision = NO_DECISION
~~~

Kết quả được xác định bởi policy tổng hợp, không phụ thuộc thứ tự action ghi cùng field.

### 13.5. Explainability

Decision result nên ghi:
- Các luật đã match.
- Các luật đã fire.
- Các luật bị loại hoặc hủy.
- Priority và group.
- Recommendation của từng luật.
- Policy tổng hợp được áp dụng.
- Kết quả cuối và reason codes.

Người vận hành có thể giải thích tại sao order bị REJECT dù cũng có luật large-order-review match.

## 14. Determinism và reproducibility

Một rule engine có tính xác định nếu cùng input facts, cùng rule version, cùng configuration và cùng execution context tạo cùng chuỗi quyết định quan sát được.

Nguồn gây không xác định:
- Tie-break không ổn định.
- Collection iteration order.
- Timestamp hoặc random được dùng trong comparator.
- Concurrent firing.
- Side effect làm thay đổi dữ liệu ngoài.
- Remote data thay đổi giữa các lần đánh giá.
- Rule priority thay đổi theo mutable state mà không được version.

Để reproducibility:
- Quy định thứ tự và tie-break.
- Ghi rule version và input snapshot.
- Ghi conflict strategy.
- Cố định external data hoặc version.
- Tránh random trong conflict resolver.
- Lưu activation/firing trace.
- Gắn execution ID và configuration snapshot.

Nếu engine hỗ trợ parallel firing, cần xác định semantics khi hai action cập nhật cùng fact. Có thể dùng lock, optimistic concurrency, transaction hoặc thiết kế action không xung đột.

## 15. Termination, starvation và fairness

### 15.1. Termination

Rule engine cần điều kiện dừng rõ. Một rule có thể tạo fact khiến chính nó hoặc luật khác match lại, dẫn đến vòng lặp.

Ví dụ:

~~~text
rule "increase-level" {
    when account.level < 10
    then account.level = account.level + 1
}
~~~

Luật này có thể fire nhiều lần cho đến khi level đạt 10. Đây là lặp hữu hạn nếu giá trị tăng đúng và có giới hạn. Nếu action không thay đổi state hoặc thay đổi theo chu kỳ, engine có thể không kết thúc.

### 15.2. Starvation

Nếu activation priority thấp luôn bị activation mới có priority cao hơn đẩy xuống, nó có thể không bao giờ fire.

Có thể giảm starvation bằng:
- Aging: tăng effective priority theo thời gian chờ.
- Giới hạn số lần liên tiếp một group được chọn.
- Chia ngân sách xử lý theo group.
- Deadline hoặc timeout.
- Phát cảnh báo activation tồn đọng.

### 15.3. Fairness

Fairness bảo đảm activation đủ điều kiện có cơ hội được xử lý theo chính sách. Fairness có thể quan trọng trong hệ thống nhiều tenant hoặc nhiều loại event.

Cần cân bằng giữa ưu tiên nghiệp vụ và fairness. Không phải mọi hệ thống đều cần fair scheduling, nhưng nếu có yêu cầu thì phải kiểm thử.

### 15.4. Firing limit

Có thể giới hạn:
- Số activation fire trong một execution.
- Thời gian tối đa.
- Độ sâu chain.
- Số lần một rule được fire cho cùng tuple.
- Số fact được tạo.

Khi chạm giới hạn, engine cần trả trạng thái rõ như RULE_LIMIT_EXCEEDED thay vì coi execution hoàn tất bình thường.

## 16. Concurrency và transaction

Khi nhiều thread hoặc worker xử lý activation đồng thời, conflict resolution trở nên phức tạp hơn.

### 16.1. Parallel firing

Hai activation có thể được chạy song song nếu action độc lập. Nhưng nếu cả hai ghi cùng fact hoặc gọi service có side effect, kết quả có thể phụ thuộc race condition.

Engine cần:
- Phân tích dependency giữa action.
- Lock hoặc serialize khi cùng cập nhật tài nguyên.
- Dùng optimistic version check.
- Chạy transaction cho thay đổi facts.
- Kiểm tra conflict trước commit.
- Xác định cách retry khi transaction thất bại.

### 16.2. Read-write conflicts

Có thể phân loại:
- Read-read: thường có thể chạy song song.
- Read-write: kết quả đọc có thể stale.
- Write-write: cần arbitration hoặc merge.
- External side effects: cần idempotency và transaction boundary phù hợp.

### 16.3. Serializable execution

Nếu cần semantics như chạy tuần tự, engine có thể serialize các action xung đột. Không nhất thiết toàn bộ engine phải chạy đơn luồng; chỉ các activation có dependency mới cần tuần tự hóa.

### 16.4. Event sourcing và replay

Nếu engine lưu fact changes và rule firings thành event log, có thể replay để điều tra. Event cần có thứ tự xác định và chứa version của rules cùng conflict policy.

Replay phải phân biệt tính toán lại và phát lại side effect. Không được gửi lại email, charge payment hoặc tạo reservation chỉ vì replay log.

## 17. Diagnostics và giải thích conflict

Một engine tốt nên giải thích không chỉ kết quả mà cả cách nó chọn activation.

Một conflict report có thể chứa:

~~~json
{
  "executionId": "exec-42",
  "decision": "REJECT",
  "conflictSet": [
    {
      "ruleId": "fraud-block",
      "matched": true,
      "salience": 100,
      "fired": true
    },
    {
      "ruleId": "large-order-review",
      "matched": true,
      "salience": 40,
      "fired": false,
      "reason": "CANCELLED_BY_ACTIVATION_GROUP"
    }
  ],
  "resolutionStrategy": "SALience_AND_ACTIVATION_GROUP"
}
~~~

### 17.1. Match explanation

Cho biết điều kiện nào đúng hoặc sai. Có thể ghi predicate results mà không nhất thiết lưu mọi giá trị dữ liệu nhạy cảm.

### 17.2. Agenda explanation

Cho biết:
- Activation nào đang chờ.
- Thứ tự ưu tiên.
- Activation nào được chọn.
- Lý do tie-break.
- Activation nào bị hủy hoặc stale.

### 17.3. Firing explanation

Cho biết action nào đã chạy, fact nào thay đổi, action nào thất bại và rule nào được kích hoạt tiếp theo.

### 17.4. Conflict reason codes

Nên dùng reason code ổn định, ví dụ:
- PRIORITY_LOWER.
- CANCELLED_BY_GROUP.
- CONDITION_NO_LONGER_TRUE.
- ACTIVATION_STALE.
- DUPLICATE_ACTIVATION.
- RULE_DISABLED.
- AGENDA_GROUP_NOT_FOCUSED.
- FIRING_LIMIT_REACHED.

Message có thể thay đổi, nhưng code ổn định giúp dashboard và automation phân tích.

## 18. Kiểm thử xung đột giữa các luật

### 18.1. Multiple-match tests

Tạo input làm nhiều luật cùng match. Xác nhận conflict set chứa đúng activation và không bỏ sót rule.

### 18.2. Priority tests

Kiểm tra:
- Priority cao được chọn trước.
- Priority bằng nhau dùng tie-break đúng.
- Dynamic priority được tính lại theo policy.
- Priority thấp không bị starvation ngoài ý muốn.

### 18.3. Activation group tests

Xác nhận:
- Một activation fire sẽ hủy đúng các activation còn lại trong nhóm.
- Activation ngoài nhóm không bị ảnh hưởng.
- Activation mới sau đó tuân theo semantics đã định nghĩa.
- Group reset đúng giữa các execution.

### 18.4. Update/retract tests

Kiểm tra khi fact thay đổi:
- Activation stale bị hủy hoặc tính lại.
- Derived fact được retract khi premise không còn.
- Rule có thể được kích hoạt lại theo refraction policy.
- Không có kết quả dựa trên dữ liệu cũ.

### 18.5. Write conflict tests

Tạo hai luật cùng ghi một field. Xác nhận:
- Policy chọn kết quả đúng.
- Không phụ thuộc collection iteration order.
- Có diagnostic nếu conflict không được giải quyết.
- Side effect không chạy hai lần ngoài ý muốn.

### 18.6. Decision table hit policy tests

Kiểm tra Unique, Any, First, Priority, Rule Order và Collect theo semantics thực tế của DSL. Tạo cả input không match row nào và input match nhiều row.

### 18.7. Termination và fairness tests

Kiểm tra:
- Rule loop dừng theo giới hạn.
- Firing limit tạo trạng thái lỗi phù hợp.
- Activation ưu tiên thấp vẫn được xử lý nếu fairness được yêu cầu.
- Cancellation dừng execution đúng lúc.

### 18.8. Determinism tests

Chạy nhiều lần với cùng facts, rule version và context. So sánh:
- Firing sequence.
- Decision result.
- Fact changes.
- Reason codes.
- Side effect intents.

Nếu engine cho phép nondeterminism, cần test đúng phạm vi kết quả được cho phép.

## 19. Hiệu năng và khả năng mở rộng

Conflict resolution có thể tốn chi phí khi conflict set lớn hoặc nhiều rule cùng match.

Các điểm cần cân nhắc:
- Index fact types và thuộc tính dùng trong condition.
- Dùng incremental matching để tránh đánh giá lại toàn bộ rule.
- Giữ agenda structure phù hợp với comparator.
- Tránh comparator thực hiện I/O hoặc logic quá đắt.
- Giới hạn activation duplicates.
- Theo dõi số activation được tạo, hủy và fire.
- Đo thời gian match riêng với thời gian action.
- Phân vùng theo tenant hoặc rule group nếu semantics cho phép.
- Tránh lock toàn cục nếu chỉ một số facts xung đột.
- Giới hạn số firing và resource budget.

Các metric hữu ích:
- rule_matches_total.
- activations_created_total.
- activations_cancelled_total.
- rule_firings_total.
- conflict_set_size.
- agenda_wait_duration.
- rule_firing_duration.
- stale_activation_total.
- rule_loop_limit_hits.

Không nên dùng execution ID hoặc fact ID có cardinality cao làm metric label. Chi tiết theo từng execution phù hợp hơn với trace hoặc log có kiểm soát.

## 20. Bảo mật và an toàn nghiệp vụ

Xung đột luật có thể ảnh hưởng đến quyết định nhạy cảm như thanh toán, quyền truy cập, hạn mức và phê duyệt.

Các nguyên tắc:
- Không để luật priority thấp ghi đè quyết định bảo vệ quan trọng.
- Quy định deny/allow precedence một cách tường minh.
- Giới hạn ai có quyền thay đổi salience hoặc activation group.
- Audit mọi thay đổi policy có ảnh hưởng đến quyết định.
- Validate rule set trước khi publish.
- Không thực thi side effect trước khi quyết định được chốt.
- Dùng transaction hoặc outbox cho action ngoài hệ thống.
- Giới hạn thời gian và số lần firing.
- Không đưa dữ liệu nhạy cảm vào conflict explanation không được bảo vệ.
- Có cơ chế fail-safe cho policy quan trọng.

Một thay đổi nhỏ về priority có thể làm đổi kết quả của nhiều trường hợp. Do đó, rule priority và conflict policy cần được review và version như logic nghiệp vụ.

## 21. Kiến trúc conflict resolution trong rule engine

Một kiến trúc khái niệm:

~~~text
Facts / Events
      |
      v
Pattern Matcher
      |
      v
Activation Builder
      |
      v
Conflict Set
      |
      v
Agenda Manager
      |
      v
Conflict Resolver
      |
      v
Selected Activation
      |
      v
Rule Executor
      |
      v
Fact Store / Side-effect Boundary
      |
      +------> Update matcher and agenda
      |
      v
Execution Trace / Diagnostics
~~~

Các thành phần:
- **Pattern matcher:** tìm rule match với facts.
- **Activation builder:** tạo activation cho mỗi match hợp lệ.
- **Conflict set:** lưu các activation chờ.
- **Agenda manager:** quản lý group, focus và trạng thái activation.
- **Conflict resolver:** chọn activation theo strategy.
- **Rule executor:** thực thi action.
- **Fact store:** quản lý assert/update/retract.
- **Truth maintenance:** theo dõi derived facts.
- **Side-effect boundary:** quản lý transaction, outbox và idempotency.
- **Trace collector:** ghi match, selection, firing và cancellation.

Không nhất thiết mỗi thành phần là service riêng. Nhưng việc tách trách nhiệm giúp thay đổi conflict strategy mà không phải viết lại matcher hoặc action execution.

## 22. Ví dụ API conflict resolver

Một API khái niệm:

~~~java
interface ConflictResolver {
    ResolutionResult resolve(
        List<Activation> candidates,
        RuleExecutionContext context
    );
}

record ResolutionResult(
    Activation selected,
    String strategy,
    List<ConflictReason> reasons
) {}
~~~

Một comparator có thể xếp theo salience rồi activation sequence:

~~~java
Comparator<Activation> order =
    Comparator.comparingInt(Activation::salience)
        .reversed()
        .thenComparingLong(Activation::sequence);
~~~

Ví dụ chỉ minh họa comparator. Một triển khai thực tế cần:
- Xác định tie-break ổn định.
- Xử lý activation stale.
- Kiểm tra group/focus.
- Hỗ trợ cancellation.
- Không gọi side effect trong resolver.
- Ghi lại lý do lựa chọn.

Resolver nên là hàm thuần nếu có thể: cùng candidate set và context thì trả cùng kết quả. Điều này giúp test, replay và explainability đáng tin cậy.

## 23. Quy trình thiết kế conflict policy

Có thể áp dụng quy trình sau:

1. **Liệt kê rule outputs:** xác định luật nào đọc/ghi fact hoặc gọi side effect nào.
2. **Phân loại conflict:** agenda, write, side effect, decision hoặc resource conflict.
3. **Xác định semantics nghiệp vụ:** nhiều kết quả có được phép cùng tồn tại không?
4. **Chọn policy:** priority, specificity, group, hit policy, aggregation hoặc explicit conflict.
5. **Định nghĩa tie-break:** bảo đảm thứ tự xác định khi các tiêu chí bằng nhau.
6. **Xử lý activation lifecycle:** stale, duplicate, cancelled, refraction và reactivation.
7. **Quy định termination:** firing limit, timeout, loop detection và cancellation.
8. **Thiết kế transaction:** xử lý cập nhật facts và side effect nguyên tử hoặc an toàn khi retry.
9. **Thiết kế explanation:** lưu match, agenda decision, firing và reason codes.
10. **Kiểm thử overlap:** tạo input match nhiều luật và kiểm tra kết quả.
11. **Kiểm thử determinism:** chạy lại cùng snapshot và so sánh firing trace.
12. **Đo performance:** conflict set size, matching cost, agenda wait và firing duration.
13. **Version policy:** lưu rule version và conflict strategy cùng execution.
14. **Kiểm soát thay đổi:** review và audit các thay đổi priority, group hoặc hit policy.

Nếu xung đột là một phần chủ ý của mô hình, hãy thể hiện nó trong DSL hoặc decision table. Nếu xung đột là bất hợp lệ, hãy phát diagnostic trước khi triển khai thay vì chờ runtime chọn một luật ngẫu nhiên.

## 24. Kết luận

Xung đột giữa các luật xuất hiện khi nhiều activation cùng đủ điều kiện hoặc nhiều action có khả năng tác động lên cùng dữ liệu, quyết định hay tài nguyên. Rule engine cần phân biệt match với firing, quản lý conflict set và agenda, rồi áp dụng conflict resolution policy có semantics rõ ràng.

Priority, salience, recency, specificity, agenda group, activation group và decision table hit policy là những công cụ phổ biến, nhưng mỗi công cụ giải quyết một dạng vấn đề khác nhau. Một thiết kế tốt còn phải xử lý activation stale, rule loops, starvation, concurrency, transaction và side effects. Khi conflict policy được version, kiểm thử và giải thích bằng firing trace, kết quả DSL trở nên xác định, có thể tái lập và đáng tin cậy hơn.

