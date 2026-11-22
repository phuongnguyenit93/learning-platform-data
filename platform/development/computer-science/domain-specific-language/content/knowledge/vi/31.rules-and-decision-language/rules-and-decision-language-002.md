# Độ ưu tiên luật trong DSL luật và quyết định

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích độ ưu tiên luật (rule priority) trong một DSL luật và phân biệt nó với thứ tự khai báo.
- Mô tả cách rule engine tạo activation, conflict set và agenda trước khi thực thi luật.
- Thiết kế cơ chế ưu tiên tĩnh hoặc động và xác định quy ước giá trị cao/thấp.
- Kết hợp priority với specificity, recency, thứ tự kích hoạt và các chiến lược phân giải xung đột khác.
- Tổ chức luật theo agenda group, activation group, ruleflow group hoặc phase.
- Hiểu ảnh hưởng của priority đến forward chaining, cập nhật fact, tác dụng phụ và thứ tự thực thi.
- Ngăn vòng lặp luật và kiểm soát việc một luật được kích hoạt lại.
- Thiết kế hành vi xác định khi nhiều luật cùng đủ điều kiện.
- Áp dụng priority trong decision table và các chính sách ra quyết định.
- Kiểm thử, ghi log, giải thích và quản lý phiên bản của cơ chế ưu tiên.

## 1. Độ ưu tiên luật là gì?

Trong một DSL luật (rule DSL), một tập luật có thể cùng thỏa điều kiện tại một thời điểm. Rule engine cần quyết định luật nào được thực thi trước, luật nào chờ và luật nào bị loại khỏi lượt xử lý. Độ ưu tiên luật (rule priority) là một trong những cơ chế giúp engine đưa ra quyết định đó.

Ví dụ, một hệ thống xử lý yêu cầu vay có các luật:

- Khách hàng có hồ sơ đầy đủ thì chuyển sang bước đánh giá.
- Khách hàng có dấu hiệu gian lận thì chặn yêu cầu.
- Khách hàng thuộc nhóm ưu tiên thì đưa vào hàng xử lý nhanh.

Một hồ sơ có thể đồng thời thỏa điều kiện “đầy đủ”, “có dấu hiệu gian lận” và “khách hàng ưu tiên”. Nếu engine chạy tất cả luật theo một thứ tự không được xác định, kết quả có thể không nhất quán. Cơ chế priority giúp quy định luật nào được xem xét trước hoặc luật nào có quyền thắng khi các luật xung đột.

Một khai báo DSL minh họa:

~~~text
rule "block_suspicious_request" {
    priority = 100
    when request.riskScore >= 90
    then reject(request)
}

rule "fast_track_vip" {
    priority = 50
    when customer.isVip
    then set request.queue = "FAST"
}

rule "validate_complete_profile" {
    priority = 10
    when request.profile.isComplete
    then set request.status = "READY_FOR_REVIEW"
}
~~~

Trong ví dụ này, giả sử engine quy định số priority lớn hơn được xét trước. Khi cả ba luật cùng đủ điều kiện, luật chặn yêu cầu được chọn trước.

Priority không tự động có nghĩa là luật có priority cao sẽ luôn thắng trong mọi trường hợp. Nó chỉ có tác dụng theo semantics mà DSL và engine đã công bố. Các luật có thể thuộc nhóm khác nhau, chạy ở phase khác nhau hoặc bị loại bởi activation group. Vì vậy, cần hiểu toàn bộ cơ chế điều phối trước khi thiết kế thứ tự luật.

## 2. Vòng đời thực thi luật

Để hiểu priority, trước hết cần hiểu cách rule engine xử lý luật.

Một vòng đời phổ biến:

~~~text
Tập luật + Fact hiện tại
          |
          v
     Pattern matching
          |
          v
  Các luật thỏa điều kiện
          |
          v
     Activations
          |
          v
  Conflict set / Agenda
          |
          v
  Chọn activation theo priority
          |
          v
     Thực thi luật
          |
          v
  Cập nhật / thêm / xóa fact
          |
          v
  Đánh giá lại các điều kiện
          |
          +------> Agenda mới
~~~

### 2.1. Fact

Fact là dữ liệu mà rule engine dùng để đánh giá điều kiện. Fact có thể là object, record, event hoặc dữ liệu miền nghiệp vụ.

Ví dụ:

~~~text
Request {
    id = "REQ-2048"
    amount = 25000000
    riskScore = 92
    status = "NEW"
}

Customer {
    id = "CUS-17"
    isVip = true
    profileComplete = true
}
~~~

### 2.2. Pattern matching

Engine so khớp điều kiện của từng luật với tập fact. Khi một bộ fact làm điều kiện luật đúng, engine có thể tạo một activation.

### 2.3. Activation

Activation là một cơ hội thực thi cụ thể của một luật với một tổ hợp fact và binding cụ thể. Một luật có thể tạo nhiều activation nếu nhiều bộ fact cùng khớp.

Ví dụ, luật tính phí có thể được kích hoạt một lần cho mỗi đơn hàng phù hợp.

### 2.4. Conflict set và agenda

Conflict set là tập activation đang đủ điều kiện nhưng chưa được thực thi. Agenda là cấu trúc engine dùng để quản lý và chọn activation tiếp theo. Một số engine dùng hai thuật ngữ gần như đồng nghĩa; một số engine phân biệt tập xung đột với hàng đợi ưu tiên.

### 2.5. Thực thi và tái đánh giá

Sau khi một activation chạy, luật có thể thay đổi fact. Thay đổi đó làm một số activation cũ không còn hợp lệ và có thể tạo activation mới. Engine phải cập nhật agenda theo semantics của mình.

Do đó, priority thường được áp dụng trên activation đang chờ tại một thời điểm, không chỉ đơn giản là sắp xếp danh sách rule một lần ở đầu chương trình.

## 3. Phân biệt priority với thứ tự khai báo

Thứ tự luật xuất hiện trong file DSL không nhất thiết là thứ tự thực thi.

Ví dụ:

~~~text
rule "rule_a" {
    priority = 5
    when conditionA
    then actionA()
}

rule "rule_b" {
    priority = 20
    when conditionB
    then actionB()
}
~~~

Nếu engine ưu tiên số lớn, rule_b được chọn trước dù được khai báo sau rule_a.

Một DSL có thể chọn thứ tự khai báo làm tie-breaker, nhưng cần phân biệt:
- Thứ tự khai báo là vị trí luật trong nguồn.
- Priority là thuộc tính điều phối được khai báo hoặc tính toán.
- Thứ tự activation là thời điểm các điều kiện trở thành đúng.
- Thứ tự thực thi là kết quả cuối cùng của conflict resolution.

Nếu DSL không quy định rõ, người dùng có thể nhầm rằng luật được viết trước sẽ chạy trước. Điều này đặc biệt nguy hiểm khi các action có tác dụng phụ hoặc cùng cập nhật một fact.

## 4. Priority tĩnh và thuộc tính salience

Nhiều rule engine cung cấp một thuộc tính số để thể hiện mức ưu tiên. Một số hệ thống gọi thuộc tính này là salience.

Ví dụ:

~~~text
rule "fraud_check" {
    salience = 100
    when transaction.riskScore > 80
    then flag(transaction)
}
~~~

Salience thường được đánh giá khi tạo activation hoặc khi engine xây agenda. Quy tắc cụ thể tùy engine.

### 4.1. Quy ước giá trị

Có hai quy ước phổ biến:

| Quy ước | Ý nghĩa |
|---|---|
| Số lớn hơn được ưu tiên | 100 đứng trước 50 |
| Số nhỏ hơn được ưu tiên | 1 đứng trước 10 |

Không có quy ước chung cho mọi DSL. Tài liệu ngôn ngữ phải nêu rõ chiều ưu tiên, giá trị mặc định và cách xử lý khi thiếu thuộc tính.

### 4.2. Giá trị mặc định

Nếu luật không khai báo priority, engine có thể:
- Dùng một giá trị mặc định như 0.
- Gán priority theo nhóm.
- Dùng thứ tự khai báo làm tie-breaker.
- Xếp luật vào một agenda group mặc định.

Cần công bố hành vi mặc định để luật cũ không thay đổi cách chạy khi bổ sung luật mới.

### 4.3. Miền giá trị

Nên quy định:
- Kiểu dữ liệu là integer hay decimal.
- Giới hạn nhỏ nhất và lớn nhất.
- Có chấp nhận số âm không.
- Cách xử lý overflow.
- Giá trị có thể là null hay không.

Với priority mang tính điều phối, một miền số hữu hạn thường dễ kiểm soát và giải thích hơn một biểu thức tùy ý.

### 4.4. Priority không phải mức độ quan trọng nghiệp vụ duy nhất

Một luật có priority 100 không nhất thiết quan trọng hơn mọi luật priority 50 trong mọi ngữ cảnh. Priority có thể chỉ áp dụng trong cùng một agenda. Quyền chặn giao dịch, quyền bảo mật hoặc quy tắc bắt buộc có thể được thực thi bằng phase hoặc policy riêng.

## 5. Xung đột luật và chiến lược phân giải

Xung đột xuất hiện khi nhiều activation cùng đủ điều kiện và engine cần chọn activation tiếp theo.

Ví dụ:

~~~text
rule "apply_standard_discount" {
    priority = 20
    when order.total >= 100000
    then set order.discount = 5
}

rule "apply_vip_discount" {
    priority = 30
    when customer.isVip and order.total >= 100000
    then set order.discount = 15
}
~~~

Nếu khách hàng VIP và đơn hàng đủ giá trị, cả hai luật đều được kích hoạt. Nếu cả hai cùng ghi order.discount, thứ tự thực thi có thể quyết định giá trị cuối cùng.

### 5.1. Priority

Engine chọn activation có priority cao hơn theo quy ước của DSL.

### 5.2. Specificity

Specificity là mức độ cụ thể của điều kiện. Một luật yêu cầu nhiều điều kiện hoặc ràng buộc hẹp hơn có thể được xem là cụ thể hơn.

Ví dụ:
- Luật A: khách hàng đang hoạt động.
- Luật B: khách hàng đang hoạt động, là VIP và có lịch sử thanh toán tốt.

Một engine có thể dùng specificity làm tie-breaker khi priority bằng nhau. Tuy nhiên, số lượng điều kiện nhiều hơn không phải lúc nào cũng có nghĩa là luật phù hợp hơn về nghiệp vụ. Specificity cần được định nghĩa chính xác, không nên suy ra bằng cảm tính.

### 5.3. Recency

Recency ưu tiên activation liên quan đến fact mới được thêm hoặc cập nhật gần đây. Cơ chế này có thể hữu ích trong hệ thống xử lý sự kiện, nhưng có thể làm thứ tự thực thi phụ thuộc thời điểm dữ liệu đến.

### 5.4. Activation age

Một chiến lược có thể ưu tiên activation đã chờ lâu hơn để tránh bị bỏ đói (starvation). Nếu chỉ chọn activation mới hoặc priority cao nhất, activation thấp hơn có thể không bao giờ được chạy.

### 5.5. Thứ tự khai báo

Nếu mọi tiêu chí trước đó bằng nhau, engine có thể dùng thứ tự khai báo hoặc một thứ tự ổn định theo rule ID.

### 5.6. Chiến lược ngẫu nhiên

Một số hệ thống có thể chọn ngẫu nhiên giữa activation tương đương để phân phối tải hoặc phục vụ thử nghiệm. Cách này không phù hợp nếu cần kết quả tái hiện được, trừ khi seed và semantics được ghi lại.

### 5.7. Kết hợp nhiều tiêu chí

Một engine có thể định nghĩa thứ tự so sánh dạng tuple:

~~~text
(priority descending,
 specificity descending,
 recency descending,
 activationSequence ascending)
~~~

Đây chỉ là một ví dụ. Engine khác có thể dùng thứ tự tiêu chí khác. Điểm quan trọng là quy tắc phải xác định, ổn định và được tài liệu hóa.

## 6. Agenda và thứ tự chọn activation

Agenda là trung tâm của cơ chế điều phối luật.

### 6.1. Priority queue

Một cách triển khai là dùng priority queue. Mỗi activation được đưa vào với một khóa sắp xếp. Khi engine cần chạy luật tiếp theo, nó lấy activation đứng đầu.

Khóa có thể bao gồm:
- Rule priority.
- Group priority.
- Specificity.
- Recency.
- Sequence number.
- Rule identifier.

### 6.2. Cập nhật activation

Khi fact thay đổi, activation có thể:
- Được tạo mới.
- Bị hủy vì điều kiện không còn đúng.
- Được cập nhật binding.
- Được giữ lại nếu engine xác định nó vẫn hợp lệ.

Nếu priority là động, engine cần xác định có tính lại priority khi fact liên quan thay đổi hay không.

### 6.3. Activation bị stale

Một activation được tạo từ fact snapshot cũ có thể không còn phù hợp tại thời điểm chạy. Engine cần xác nhận activation vẫn hợp lệ trước khi thực thi hoặc dùng cơ chế version để phát hiện dữ liệu đã thay đổi.

### 6.4. Thực thi từng activation

Trong mô hình tuần tự, engine thường chọn một activation, chạy action, cập nhật working memory rồi đánh giá lại agenda. Điều này làm thứ tự priority có thể ảnh hưởng đến những activation tiếp theo.

### 6.5. Không nhầm agenda order với kết quả cuối

Ngay cả khi luật ưu tiên cao chạy trước, một luật chạy sau có thể cập nhật lại fact. Nếu không có cơ chế loại trừ hoặc kiểm soát ghi, giá trị cuối cùng vẫn có thể do luật sau quyết định.

## 7. Nhóm luật và phạm vi priority

Một hệ thống lớn thường có nhiều nhóm luật. Priority trong một nhóm không nhất thiết so sánh trực tiếp với priority ở nhóm khác.

### 7.1. Agenda group

Agenda group phân chia các activation theo nhóm công việc. Engine có thể chỉ tập trung một nhóm tại một thời điểm.

~~~text
rule "validate_request" {
    agendaGroup = "VALIDATION"
    priority = 50
    when request.status == "NEW"
    then validate(request)
}
~~~

Các nhóm có thể đại diện cho validation, eligibility, pricing hoặc notification.

### 7.2. Focus stack

Một số engine dùng focus stack để xác định agenda group đang được ưu tiên xử lý. Nhóm được focus có thể chạy cho đến khi rỗng hoặc đến khi engine chuyển focus.

Priority bên trong group và thứ tự focus giữa các group là hai cơ chế khác nhau.

### 7.3. Activation group

Activation group thường thể hiện lựa chọn loại trừ: khi một activation trong nhóm được thực thi, các activation khác trong cùng nhóm bị hủy.

Ví dụ, quyết định duyệt hoặc từ chối:

~~~text
rule "approve_request" {
    activationGroup = "REQUEST_DECISION"
    when request.isEligible
    then approve(request)
}

rule "reject_request" {
    activationGroup = "REQUEST_DECISION"
    when request.hasFatalIssue
    then reject(request)
}
~~~

Cơ chế này giúp tránh cả hai quyết định cùng được thực thi. Cần xác định activation group có hủy activation ngay khi một luật chạy hay chỉ hủy các activation đang chờ.

### 7.4. Ruleflow group

Ruleflow group liên kết luật với một bước hoặc node trong quy trình. Luật chỉ được kích hoạt khi flow đến đúng node hoặc group được mở.

### 7.5. Phase và stage

Một DSL có thể dùng phase rõ ràng:

~~~text
phase VALIDATE {
    rule "check_required_fields" { ... }
}

phase DECIDE {
    rule "approve_or_reject" { ... }
}

phase NOTIFY {
    rule "send_result" { ... }
}
~~~

Cách tổ chức theo phase giúp tránh phải dùng một con số priority rất lớn để mô phỏng toàn bộ trình tự nghiệp vụ.

### 7.6. Priority toàn cục và priority cục bộ

Cần xác định:
- Priority so sánh trong cùng group hay toàn engine?
- Group priority có cao hơn rule priority không?
- Một group đang inactive có thể có activation không?
- Khi đổi focus, activation cũ được giữ hay bị hủy?
- Có thể chuyển activation giữa các group không?

Không nên để người dùng suy đoán phạm vi từ tên thuộc tính.

## 8. Thực thi tuần tự, forward chaining và priority

Rule engine kiểu forward chaining liên tục áp dụng luật khi dữ liệu thay đổi.

### 8.1. Forward chaining

Luồng xử lý:

1. Nạp fact ban đầu.
2. Tìm các luật thỏa điều kiện.
3. Tạo activation.
4. Chọn activation theo agenda.
5. Thực thi action.
6. Cập nhật fact.
7. Tạo hoặc hủy activation.
8. Tiếp tục đến khi agenda rỗng hoặc đạt điều kiện dừng.

Priority tác động ở bước chọn activation.

### 8.2. Một luật có thể chạy nhiều lần

Nếu fact thay đổi làm điều kiện của luật đúng trở lại, luật có thể tạo activation mới. Vì vậy, “luật đã chạy” không nhất thiết có nghĩa “luật không bao giờ chạy lại”.

### 8.3. Refraction

Refraction là cơ chế ngăn cùng một luật chạy lặp lại với cùng một tổ hợp fact trong một chu kỳ hoặc trạng thái nhất định. Phạm vi và thời điểm reset refraction tùy engine.

### 8.4. Sequential mode

Một số engine có chế độ tuần tự: thứ tự luật hoặc rule agenda được xác định trước và engine không liên tục tạo lại activation theo cùng cách forward chaining. Priority có thể không được áp dụng giống chế độ reactive. Tài liệu DSL cần phân biệt các execution mode.

### 8.5. Stateless evaluation

Một số rule set được đánh giá một lần trên input rồi trả kết quả. Trong chế độ này, priority có thể xác định thứ tự đánh giá hoặc chọn kết quả, nhưng không nhất thiết tồn tại agenda lâu dài.

## 9. Priority và cập nhật fact

Priority trở nên quan trọng khi các luật có thể thay đổi cùng một fact hoặc tạo fact mới.

Ví dụ:

~~~text
rule "mark_high_risk" {
    priority = 100
    when request.score >= 90
    then set request.decision = "BLOCK"
}

rule "mark_eligible" {
    priority = 20
    when request.profileComplete
    then set request.decision = "REVIEW"
}
~~~

Nếu cả hai điều kiện đúng, luật BLOCK chạy trước. Nhưng nếu luật REVIEW vẫn còn activation và chạy sau, nó có thể ghi đè decision thành REVIEW.

Do đó, chỉ đặt priority cao cho luật BLOCK có thể chưa đủ.

### 9.1. Guard trên trạng thái hiện tại

Có thể thêm điều kiện để luật thường không ghi đè quyết định đã chốt:

~~~text
rule "mark_eligible" {
    priority = 20
    when request.profileComplete
      and request.decision == null
    then set request.decision = "REVIEW"
}
~~~

### 9.2. Trạng thái terminal

Một số quyết định nên là trạng thái terminal:

~~~text
decisionState = oneOf("PENDING", "APPROVED", "REJECTED", "BLOCKED")
~~~

Khi đã chuyển sang BLOCKED, các luật khác không được phép quay lại PENDING hoặc APPROVED nếu không có một luồng override riêng.

### 9.3. Decision fact

Có thể tách kết quả quyết định thành fact riêng và dùng một luật commit cuối cùng. Các luật đánh giá chỉ tạo đề xuất (recommendation), còn một bước arbitration chọn quyết định hợp lệ.

~~~text
Recommendation {
    requestId
    outcome
    reason
    priority
}
~~~

Cách này giảm việc nhiều luật ghi trực tiếp cùng một field.

### 9.4. Update và retraction

Khi một luật cập nhật hoặc xóa fact, engine cần loại bỏ activation phụ thuộc fact cũ. Nếu không, luật có thể chạy trên dữ liệu đã lỗi thời.

### 9.5. Idempotent action

Nếu luật được phép chạy lại, action nên idempotent khi có thể. Ví dụ, “đặt trạng thái thành REVIEW” thường an toàn hơn “tăng số lần gửi thông báo” nếu engine có thể tạo activation lặp.

## 10. Priority động

Priority tĩnh được khai báo cố định trong rule. Priority động được tính từ context hoặc dữ liệu tại thời điểm kích hoạt.

Ví dụ minh họa:

~~~text
rule "urgent_case" {
    priority = 50 + request.urgencyLevel
    when request.isOpen
    then assignUrgentQueue(request)
}
~~~

### 10.1. Khi nào cần priority động?

- Mức khẩn cấp khác nhau giữa các yêu cầu.
- Hàng đợi cần điều chỉnh theo SLA.
- Một loại khách hàng có trọng số xử lý riêng.
- Tác vụ sắp hết hạn cần được đẩy lên trước.

### 10.2. Thời điểm tính priority

Cần xác định priority được tính:
- Khi compile rule.
- Khi match điều kiện.
- Khi tạo activation.
- Mỗi lần agenda chọn activation.
- Khi một fact phụ thuộc thay đổi.

Tính quá thường xuyên có thể gây chi phí và làm thứ tự thay đổi khó giải thích.

### 10.3. Snapshot của priority

Một cách dễ dự đoán là tính priority khi tạo activation và lưu giá trị đó trong activation. Nếu dữ liệu làm priority thay đổi, engine hủy activation cũ và tạo activation mới.

### 10.4. Giới hạn giá trị động

Priority động nên có miền giá trị được giới hạn. Không nên để input người dùng tự do cung cấp một con số rất lớn rồi vượt qua mọi luật hệ thống.

### 10.5. Tránh ưu tiên không công bằng

Nếu priority dựa trên dữ liệu thay đổi liên tục, một số activation có thể bị đẩy xuống mãi. Có thể kết hợp age-based promotion, deadline hoặc quota để giảm starvation.

## 11. Ngăn vòng lặp và kiểm soát việc kích hoạt lại

Một tập luật có thể tạo vòng lặp nếu action của luật làm điều kiện của chính nó hoặc luật khác luôn đúng.

Ví dụ:

~~~text
rule "increase_level" {
    when customer.level < 10
    then set customer.level = customer.level + 1
}

rule "normalize_level" {
    when customer.level > 0
    then set customer.level = customer.level - 1
}
~~~

Hai luật có thể kích hoạt lẫn nhau và khiến engine không bao giờ kết thúc.

### 11.1. No-loop

Một số engine hỗ trợ no-loop để ngăn luật kích hoạt lại chính nó do thay đổi mà chính luật đó tạo ra. No-loop không nhất thiết ngăn một luật khác kích hoạt lại luật này.

### 11.2. Lock-on-active

Một số engine hỗ trợ lock-on-active để ngăn tái kích hoạt trong khi agenda group đang active. Semantics cụ thể tùy engine và có thể ảnh hưởng các update hợp lệ.

### 11.3. Activation group

Nếu chỉ một luật trong nhóm được chạy, activation group có thể hủy các lựa chọn còn lại sau khi một activation thắng.

### 11.4. Fired marker

Có thể lưu marker cho biết một hành động đã được thực hiện với một fact version cụ thể:

~~~text
Processed {
    ruleId = "calculate_fee"
    factId = "ORDER-2048"
    factVersion = 7
}
~~~

Marker cần được invalidated hoặc thay đổi khi fact version mới xuất hiện nếu luật được phép chạy lại.

### 11.5. Điều kiện chuyển trạng thái

Thay vì chỉ kiểm tra dữ liệu, luật có thể yêu cầu trạng thái nguồn cụ thể:

~~~text
when request.status == "PENDING"
then transition request.status to "APPROVED"
~~~

State transition rõ ràng giúp hạn chế việc luật chạy lặp hoặc ghi đè.

### 11.6. Giới hạn số lần firing

Engine có thể có max firing count, max execution time hoặc giới hạn số lần kích hoạt. Đây là hàng rào bảo vệ khi rule set có lỗi, không thay thế việc thiết kế logic kết thúc đúng.

### 11.7. Monotonic rules

Một hệ thống có thể thiết kế luật theo hướng chỉ bổ sung kết luận hoặc tiến trạng thái theo một chiều. Nếu luật không liên tục rút lại kết quả cũ, nguy cơ vòng lặp và xung đột có thể giảm. Tuy nhiên, không phải mọi nghiệp vụ đều có thể mô hình hóa theo cách monotonic.

## 12. Priority trong decision table

Decision table biểu diễn các điều kiện và hành động theo hàng hoặc cột. Khi nhiều hàng cùng khớp, cần một hit policy hoặc cơ chế ưu tiên.

Ví dụ:

| Rule | Risk score | VIP | Kết quả | Priority |
|---|---:|---|---|---:|
| R1 | >= 90 | Any | BLOCK | 100 |
| R2 | >= 50 | Yes | MANUAL_REVIEW | 60 |
| R3 | < 50 | Yes | FAST_TRACK | 40 |
| R4 | < 70 | No | STANDARD_REVIEW | 10 |

Nếu một request có riskScore = 95 và VIP = true, cả R1 và R2 có thể khớp. Priority giúp R1 được chọn nếu policy quy định số lớn hơn thắng.

### 12.1. Hit policy FIRST

FIRST chọn hàng khớp đầu tiên theo thứ tự bảng. Thứ tự dòng trở thành một phần của semantics.

### 12.2. Hit policy UNIQUE

UNIQUE yêu cầu chỉ có một hàng khớp. Nếu nhiều hàng cùng khớp, engine báo lỗi hoặc conflict.

### 12.3. Hit policy ANY

ANY cho phép nhiều hàng khớp nếu tất cả tạo ra cùng một kết quả theo quy tắc so sánh của engine.

### 12.4. Hit policy PRIORITY

PRIORITY chọn kết quả có mức ưu tiên cao nhất theo thứ tự output hoặc thuộc tính được định nghĩa.

### 12.5. Hit policy COLLECT

COLLECT thu thập kết quả từ tất cả hàng khớp. Có thể kết hợp với aggregate như sum, min, max hoặc list.

### 12.6. Hit policy RULE ORDER

RULE ORDER trả kết quả theo thứ tự các hàng khớp trong bảng. Nó không nhất thiết giống FIRST vì FIRST chỉ chọn một kết quả.

### 12.7. Không nhầm hit policy với salience

Hit policy quyết định cách kết hợp kết quả của các hàng khớp trong decision table. Salience hoặc rule priority điều phối activation trong rule engine. Hai cơ chế có thể phối hợp nhưng không nên xem là một khái niệm.

## 13. Priority theo giai đoạn quyết định

Một quyết định nghiệp vụ thường có nhiều lớp:
1. Điều kiện loại trừ hoặc an toàn.
2. Kiểm tra hợp lệ.
3. Phân loại.
4. Tính điểm hoặc đề xuất.
5. Chọn kết quả.
6. Ghi nhận và thông báo.

Có thể mô hình hóa bằng phase:

~~~text
decision "loan_review" {
    phase "eligibility" {
        rule "reject_missing_identity" { ... }
        rule "block_fraud_signal" { ... }
    }

    phase "scoring" {
        rule "calculate_credit_score" { ... }
        rule "calculate_debt_ratio" { ... }
    }

    phase "decision" {
        rule "approve_low_risk" { ... }
        rule "manual_review_medium_risk" { ... }
    }

    phase "notification" {
        rule "notify_result" { ... }
    }
}
~~~

### 13.1. Vì sao phase hữu ích?

Phase thể hiện trình tự nghiệp vụ rõ hơn việc gán số priority rất lớn cho mọi luật. Các luật trong phase hiện tại có thể được giải quyết theo priority nội bộ, sau đó mới chuyển phase.

### 13.2. Luật chặn và luật thông thường

Luật chặn có thể tạo kết quả terminal hoặc chuyển sang phase kết thúc. Khi đó, các luật phân loại thông thường không còn quyền sửa quyết định.

### 13.3. Điều kiện chuyển phase

Cần xác định phase chuyển khi:
- Agenda của phase rỗng.
- Có luật tạo kết quả terminal.
- Một điều kiện flow được thỏa.
- Có lỗi hoặc timeout.

### 13.4. Không dùng priority để thay thế quy trình

Nếu nghiệp vụ yêu cầu “xác thực trước, định giá sau, thông báo cuối cùng”, phase hoặc workflow thường diễn đạt tốt hơn một danh sách priority toàn cục.

## 14. Thực thi đồng thời và priority

Priority queue tuần tự dễ giải thích vì mỗi lần chỉ có một activation được chọn. Nhưng hệ thống lớn có thể chạy nhiều activation đồng thời.

### 14.1. Priority trong single-thread engine

Trong mô hình một luồng, engine có thể chọn activation cao nhất, thực thi, cập nhật fact rồi chọn tiếp. Thứ tự tương đối khá rõ nếu conflict resolution xác định.

### 14.2. Priority trong parallel engine

Trong engine đa luồng, một nhóm activation có thể được phân phát cho nhiều worker. Priority có thể chỉ quyết định thứ tự đưa vào worker queue, không bảo đảm activation có priority cao hoàn tất trước.

### 14.3. Race condition

Hai luật có thể cùng đọc một fact rồi ghi giá trị khác nhau. Nếu chạy song song, kết quả có thể phụ thuộc thời điểm commit.

Cần:
- Transaction hoặc compare-and-set.
- Phân vùng fact theo instance.
- Lock hoặc actor khi cần tuần tự.
- Xác định luật nào có thể chạy song song.
- Tách action thuần khỏi tác dụng phụ.

### 14.4. Priority và fairness

Nếu worker luôn lấy activation priority cao nhất, activation thấp có thể bị starvation. Có thể dùng aging, quota, deadline hoặc weighted scheduling.

### 14.5. Priority không phải khóa bảo vệ

Priority không bảo đảm hai luật không cùng cập nhật một fact. Nếu cần loại trừ, dùng activation group, transaction, state transition hoặc cơ chế đồng bộ phù hợp.

### 14.6. Kết quả xác định

Nếu cần cùng input tạo cùng kết quả, phải kiểm soát cả:
- Thứ tự conflict resolution.
- Thứ tự commit.
- Cách xử lý fact update.
- Thứ tự event đến.
- Tính thuần của action.
- Retry và concurrency.

Chỉ có priority tĩnh là chưa đủ để bảo đảm deterministic execution trong hệ thống phân tán.

## 15. Ưu tiên theo SLA, deadline và tuổi chờ

Trong hệ thống xử lý hàng đợi, priority có thể phản ánh deadline hoặc thời gian chờ.

Ví dụ:

~~~text
priority = basePriority
         + urgencyBonus
         + deadlineBonus
         + waitingAgeBonus
~~~

### 15.1. Deadline-based priority

Yêu cầu gần hết hạn có thể được ưu tiên để đáp ứng SLA. Cần xác định deadline được tính theo timezone nào và cách xử lý khi deadline đã qua.

### 15.2. Aging

Aging tăng priority theo thời gian chờ. Điều này giúp activation có priority thấp không bị bỏ đói vô hạn.

### 15.3. Giới hạn bonus

Nếu bonus không có giới hạn, một request chờ rất lâu có thể vượt qua luật chặn hoặc luật bảo mật. Nên chia priority theo tier hoặc tách policy bắt buộc khỏi queue scheduling.

### 15.4. Ưu tiên không đồng nghĩa với cam kết thời gian

Priority chỉ ảnh hưởng thứ tự tương đối. Nó không bảo đảm một activation được chạy trước một thời điểm nhất định nếu tài nguyên thiếu hoặc worker gặp lỗi. SLA cần thêm capacity planning và monitoring.

## 16. Priority và độ tin cậy của tác dụng phụ

Action của luật có thể gửi email, tạo đơn hàng, thu tiền hoặc gọi dịch vụ ngoài. Thứ tự luật ảnh hưởng đến thời điểm tác dụng phụ xảy ra.

### 16.1. Tách đánh giá khỏi thực thi

Một cách thiết kế là luật chỉ tạo đề xuất hoặc command. Một bước riêng chọn kết quả rồi thực thi action.

~~~text
rule "suggest_approval" {
    when request.score >= 80
    then emit Recommendation("APPROVE", priority = 20)
}

rule "suggest_rejection" {
    when request.fraudFlag
    then emit Recommendation("REJECT", priority = 100)
}
~~~

Một decision resolver chọn recommendation hợp lệ, sau đó mới thực hiện tác dụng phụ.

### 16.2. Transaction boundary

Nếu nhiều action cần cập nhật cùng dữ liệu, dùng transaction để tránh commit một phần.

### 16.3. Outbox và idempotency

Với thông báo hoặc service call, có thể ghi command vào outbox trong cùng transaction với quyết định. Consumer xử lý command bằng idempotency key để retry an toàn.

### 16.4. Không dùng priority làm cơ chế rollback

Nếu luật priority thấp đã chạy và gửi email, việc một luật priority cao chạy sau không thể tự động thu hồi email. Cần thiết kế phase, decision arbitration hoặc action trì hoãn cho đến khi quyết định cuối cùng được chốt.

## 17. Debug và giải thích vì sao một luật được chạy trước

Một DSL luật cần khả năng giải thích thứ tự thực thi. Khi kết quả không như mong đợi, người vận hành cần biết activation nào đã cạnh tranh và tiêu chí nào quyết định.

### 17.1. Agenda trace

Một trace có thể ghi:

~~~text
10:00:00.010 Activation created: block_suspicious_request
10:00:00.012 Activation created: fast_track_vip
10:00:00.013 Activation created: validate_complete_profile
10:00:00.014 Selected: block_suspicious_request (priority=100)
10:00:00.018 Fired: block_suspicious_request
10:00:00.019 Cancelled: fast_track_vip (decision became terminal)
10:00:00.019 Cancelled: validate_complete_profile (decision became terminal)
~~~

### 17.2. Giải thích tiêu chí chọn

Debugger có thể hiển thị:
- Priority của activation.
- Group hiện tại.
- Các tiêu chí tie-break.
- Activation nào đứng trước.
- Activation nào bị hủy.
- Fact nào làm điều kiện thay đổi.

### 17.3. Audit record

Với quyết định quan trọng, nên ghi:
- Rule ID và version.
- Input hoặc fact version.
- Priority được dùng.
- Kết quả rule.
- Người hoặc service khởi tạo.
- Thời điểm và correlation ID.

Không nên log toàn bộ dữ liệu nhạy cảm nếu không cần.

### 17.4. Reproducibility

Để tái hiện quyết định, cần lưu phiên bản rule set, configuration, input snapshot và policy điều phối. Chỉ lưu tên luật cuối cùng có thể không đủ để giải thích kết quả.

## 18. Quản lý phiên bản và thay đổi priority

Thay đổi priority có thể làm thay đổi kết quả nghiệp vụ dù điều kiện và action của luật không đổi.

Ví dụ, tăng priority của luật VIP có thể khiến nó chạy trước luật giảm giá chung. Nếu hai luật ghi cùng field, giá trị cuối có thể thay đổi.

### 18.1. Priority là một phần semantics

Không nên coi priority chỉ là metadata trình bày. Trong nhiều hệ thống, nó ảnh hưởng trực tiếp đến hành vi chương trình.

### 18.2. Review thay đổi

Một thay đổi priority nên được review cùng:
- Luật bị ảnh hưởng.
- Các luật có điều kiện giao nhau.
- Fact được đọc và ghi.
- Activation group hoặc agenda group.
- Kết quả với dữ liệu đại diện.

### 18.3. Versioning

Có thể version rule set hoặc decision model. Audit nên ghi phiên bản đã được dùng cho từng quyết định.

### 18.4. Migration

Khi đổi semantics priority, cần xem xét các rule set cũ. Ví dụ, trước đây số nhỏ hơn được ưu tiên nhưng version mới dùng số lớn hơn. Chuyển đổi phải có migration rõ, tránh đảo ngược thứ tự ngoài ý muốn.

### 18.5. Rollback

Nếu thay đổi priority gây kết quả sai, có thể rollback rule version hoặc config. Với workflow đang chạy, cần xác định instance tiếp tục dùng version cũ hay chuyển sang version mới.

## 19. Kiểm thử độ ưu tiên luật

Kiểm thử priority cần tập trung vào những trường hợp nhiều luật cùng đủ điều kiện và có thể xung đột.

### 19.1. Kiểm thử luật đơn

Xác nhận:
- Luật đủ điều kiện được kích hoạt.
- Luật không đủ điều kiện không tạo activation.
- Priority mặc định đúng.
- Priority âm hoặc ngoài miền bị xử lý đúng.

### 19.2. Kiểm thử hai luật cạnh tranh

Tạo input làm hai luật cùng match. Xác nhận luật có priority cao hơn được chọn theo quy ước.

### 19.3. Kiểm thử tie-break

Cho hai activation có cùng priority. Xác nhận tiêu chí tiếp theo như specificity, recency hoặc sequence number được áp dụng đúng.

### 19.4. Kiểm thử group

Xác nhận:
- Priority trong cùng agenda group.
- Thứ tự focus giữa group.
- Activation group hủy các activation còn lại.
- Ruleflow group chỉ chạy khi được kích hoạt.

### 19.5. Kiểm thử fact update

Luật đầu tiên thay đổi fact làm luật khác được kích hoạt hoặc hủy. Xác nhận agenda được cập nhật và activation stale không chạy.

### 19.6. Kiểm thử vòng lặp

Tạo tập luật có khả năng kích hoạt qua lại. Xác nhận no-loop, refraction, giới hạn firing hoặc state transition ngăn vòng lặp theo thiết kế.

### 19.7. Kiểm thử priority động

Thay đổi urgency, deadline hoặc fact liên quan. Xác nhận thời điểm tính lại priority đúng và giá trị được giới hạn.

### 19.8. Kiểm thử đồng thời

Cho nhiều activation cùng cập nhật một fact. Kiểm tra transaction, conflict detection, lock hoặc actor bảo vệ trạng thái.

### 19.9. Kiểm thử xác định

Chạy lại cùng input snapshot, rule version và config nhiều lần. Kết quả và trace cần giống nhau nếu DSL cam kết deterministic execution.

### 19.10. Kiểm thử hồi quy

Khi thay priority, chạy lại tập tình huống nghiệp vụ đại diện để phát hiện quyết định bị thay đổi ngoài dự kiến.

## 20. Những lỗi thiết kế thường gặp

### 20.1. Nghĩ rằng priority cao luôn thắng

Priority có thể chỉ áp dụng trong một agenda group hoặc một phase. Activation group và flow state có thể loại activation trước khi so sánh priority.

### 20.2. Không quy định chiều ưu tiên

Nếu người viết không biết 100 hay 1 được ưu tiên trước, lỗi cấu hình rất dễ xảy ra. Tài liệu DSL và validator phải công bố quy ước.

### 20.3. Dùng priority để mô tả toàn bộ quy trình

Một quy trình nhiều giai đoạn nên được mô tả bằng phase hoặc ruleflow. Dùng priority 10000, 9000, 8000 để giả lập workflow làm cấu hình khó hiểu.

### 20.4. Cho nhiều luật ghi cùng một field

Luật ưu tiên cao chạy trước nhưng luật thấp hơn ghi đè sau. Hãy dùng guard, terminal state, activation group hoặc decision resolver.

### 20.5. Không có tie-break xác định

Hai activation cùng priority có thể được chọn theo thứ tự nội bộ không ổn định. Cần một tiêu chí cuối cùng như sequence number hoặc rule ID.

### 20.6. Priority động không giới hạn

Input có thể làm priority tăng bất thường, vượt qua luật hệ thống hoặc gây starvation. Cần range và policy kiểm soát.

### 20.7. Dùng side effect trong điều kiện

Nếu điều kiện có thể gửi request hoặc thay đổi dữ liệu, việc engine đánh giá lại hay reorder predicate có thể gây tác dụng phụ lặp. Điều kiện nên thuần.

### 20.8. Không xử lý activation stale

Activation tạo từ fact cũ có thể chạy sau khi quyết định đã chốt. Cần kiểm tra version hoặc hủy activation khi fact thay đổi.

### 20.9. Bỏ qua concurrency

Priority không ngăn hai worker cùng ghi dữ liệu. Cần cơ chế transaction và đồng bộ riêng.

### 20.10. Không lưu trace

Khi kết quả bất ngờ, thiếu agenda trace và rule version khiến việc điều tra rất khó. Nên lưu đủ thông tin giải thích quyết định.

## 21. Quy trình thiết kế priority cho DSL luật

Một quy trình có thể thực hiện như sau:

1. Xác định execution model: forward chaining, sequential, stateless hay ruleflow.
2. Xác định khái niệm activation, conflict set và agenda.
3. Chọn quy ước priority, giá trị mặc định và miền giá trị.
4. Xác định phạm vi so sánh: toàn cục, theo agenda group hay theo phase.
5. Chọn tie-breaker và thứ tự ưu tiên giữa các tiêu chí.
6. Xác định cách xử lý priority động và thời điểm tính lại.
7. Phân nhóm luật bằng agenda group, activation group hoặc phase nếu cần.
8. Xác định luật nào được phép ghi cùng một fact.
9. Thiết kế guard, terminal state, refraction và giới hạn firing để ngăn vòng lặp.
10. Quy định hành vi khi chạy song song và khi có conflict cập nhật.
11. Thiết kế agenda trace, audit và versioning.
12. Kiểm thử các trường hợp nhiều luật cùng match, tie, stale activation và concurrency.
13. Đánh giá thay đổi priority bằng regression scenarios trước khi phát hành.

## 22. Ví dụ tổng hợp: quyết định yêu cầu vay

Giả sử hệ thống đánh giá yêu cầu vay có các luật sau:

~~~text
decision "loan_application" {
    phase "screening" {
        rule "block_fraud" {
            priority = 100
            when application.fraudScore >= 90
            then set application.decision = "BLOCKED"
        }

        rule "reject_invalid_identity" {
            priority = 90
            when not application.identityVerified
            then set application.decision = "REJECTED"
        }
    }

    phase "assessment" {
        rule "vip_manual_review" {
            priority = 60
            when application.customer.isVip
              and application.creditScore < 650
            then emit Recommendation("MANUAL_REVIEW")
        }

        rule "approve_low_risk" {
            priority = 40
            when application.creditScore >= 750
              and application.debtRatio < 0.3
            then emit Recommendation("APPROVE")
        }

        rule "review_medium_risk" {
            priority = 20
            when application.creditScore >= 650
              and application.creditScore < 750
            then emit Recommendation("MANUAL_REVIEW")
        }
    }

    phase "resolve" {
        resolve recommendations
        commit application.decision
    }

    phase "notify" {
        rule "notify_final_decision" {
            when application.decision is not null
            then sendDecisionNotice(application)
        }
    }
}
~~~

### 22.1. Screening trước assessment

Nếu application có fraudScore >= 90, luật block_fraud được kích hoạt. Quy trình có thể kết thúc ở trạng thái BLOCKED hoặc chuyển thẳng đến phase notify tùy flow.

### 22.2. Priority trong cùng phase

Trong assessment, nếu nhiều recommendation cùng được tạo, priority có thể xác định đề xuất được chọn trước. Tuy nhiên, cần policy resolve rõ ràng: chọn một recommendation, kết hợp nhiều recommendation hay yêu cầu UNIQUE.

### 22.3. Tách recommendation và quyết định cuối

Các luật assessment không ghi trực tiếp application.decision. Chúng phát recommendation. Phase resolve chọn một kết quả và commit một lần, giảm nguy cơ luật sau ghi đè kết quả trước.

### 22.4. Notify sau khi quyết định chốt

Luật gửi thông báo chỉ chạy sau khi phase resolve đã commit decision. Điều này tránh gửi thông báo dựa trên một kết quả tạm thời.

### 22.5. Trace

Một trace có thể giải thích:
- Luật nào đã match.
- Priority từng activation.
- Phase đang chạy.
- Luật nào được chọn.
- Recommendation nào bị loại.
- Vì sao quyết định cuối cùng được commit.

## 23. Bài tập tự kiểm tra

### Bài 1: Quy ước priority

Một DSL quy định số lớn hơn được ưu tiên trước và priority mặc định bằng 0. Hãy xác định thứ tự của bốn luật có priority lần lượt là 10, 0, 50 và -5. Giải thích vì sao phải có tie-break khi hai luật cùng priority.

### Bài 2: Conflict set

Ba luật cùng match một fact. Hãy mô tả các bước từ pattern matching đến activation, conflict set, agenda và firing.

### Bài 3: Priority và specificity

Luật A có priority 20 với một điều kiện rộng. Luật B có priority 20 với ba điều kiện cụ thể. Hãy đề xuất semantics tie-break và nêu giới hạn của việc dùng số điều kiện để đo specificity.

### Bài 4: Ghi đè fact

Hai luật cùng cập nhật trường decision. Luật A có priority cao hơn nhưng luật B vẫn chạy sau và ghi đè. Hãy đề xuất ít nhất hai cách thiết kế để bảo vệ quyết định.

### Bài 5: Agenda group và activation group

Giải thích khác nhau giữa nhóm agenda dùng để điều phối giai đoạn xử lý và activation group dùng để loại trừ các activation cạnh tranh.

### Bài 6: Priority động

Một hàng đợi tính priority từ urgency và thời gian chờ. Hãy thiết kế công thức có giới hạn và giải thích cách tránh starvation hoặc để request không đáng tin tự nâng priority.

### Bài 7: Vòng lặp luật

Hai luật cập nhật qua lại cùng một fact. Hãy phân tích cách dùng no-loop, refraction, guard và terminal state. Nêu giới hạn của từng cơ chế.

### Bài 8: Decision table

Một decision table có nhiều hàng cùng match. Hãy so sánh FIRST, UNIQUE, PRIORITY và COLLECT, rồi chọn hit policy cho một trường hợp cụ thể.

### Bài 9: Thực thi song song

Hai activation cùng đọc và ghi một trạng thái. Hãy giải thích vì sao priority không ngăn race condition và đề xuất cơ chế đồng bộ phù hợp.

### Bài 10: Audit và regression

Khi thay priority của một luật từ 20 lên 80, hãy lập danh sách thông tin cần ghi trong audit và tình huống hồi quy cần chạy trước khi phát hành.

## Kết luận

Độ ưu tiên luật giúp rule engine lựa chọn activation khi nhiều luật cùng thỏa điều kiện. Để cơ chế này đáng tin cậy, DSL cần quy định rõ chiều priority, giá trị mặc định, phạm vi so sánh và tie-breaker. Priority phải được hiểu cùng agenda, activation group, agenda group, phase, fact update và execution mode. Khi nhiều luật có thể ghi cùng dữ liệu, cần guard, terminal state hoặc bước arbitration để tránh ghi đè. Với hệ thống có tác dụng phụ hoặc chạy song song, phải bổ sung transaction, idempotency và concurrency control; priority tự nó không bảo đảm loại trừ hay thứ tự hoàn tất. Agenda trace, versioning và kiểm thử các tình huống xung đột giúp người vận hành giải thích được vì sao một luật chạy trước và kiểm soát tác động khi chính sách ưu tiên thay đổi.
