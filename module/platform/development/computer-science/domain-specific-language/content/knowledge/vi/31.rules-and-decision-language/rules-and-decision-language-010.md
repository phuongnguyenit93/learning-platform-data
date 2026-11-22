# Kiểm thử tập luật trong DSL

Trong một hệ thống sử dụng ngôn ngữ đặc tả miền (Domain-Specific Language, DSL) để mô tả chính sách, điều kiện và quyết định, một tập luật (*rule set*) thường quyết định cách hệ thống phản ứng với dữ liệu đầu vào. Ví dụ, tập luật có thể xác định khách hàng có đủ điều kiện vay hay không, đơn hàng được miễn phí vận chuyển khi nào, giao dịch nào cần kiểm tra bổ sung hoặc yêu cầu nào được chuyển đến bước phê duyệt.

Một rule riêng lẻ có thể trông đơn giản, nhưng nhiều rule cùng hoạt động có thể tạo ra tương tác phức tạp. Hai rule có thể cùng khớp một đầu vào, rule có thể che khuất rule khác do độ ưu tiên, một điều kiện biên có thể bị xử lý sai, hoặc thứ tự đánh giá có thể làm thay đổi kết quả. Vì vậy, kiểm thử từng biểu thức riêng lẻ chưa đủ để chứng minh cả tập luật hoạt động đúng.

**Kiểm thử tập luật** là quá trình xác minh rằng các rule, điều kiện, hành động, thứ tự ưu tiên và chính sách kết hợp tạo ra quyết định đúng với những đầu vào và trạng thái đã xác định. Công việc này bao gồm kiểm thử từng rule, kiểm thử tương tác giữa rule, kiểm thử toàn bộ quyết định, kiểm thử hồi quy khi rule thay đổi và kiểm thử các thuộc tính mà tập luật phải luôn giữ.

Mục tiêu là biến yêu cầu nghiệp vụ thành những trường hợp có thể chạy lại, có kết quả mong đợi và có bằng chứng. Một bộ kiểm thử tốt giúp phát hiện lỗi trước khi triển khai, giải thích vì sao một quyết định được tạo ra và giảm nguy cơ một thay đổi nhỏ làm ảnh hưởng đến những tình huống vốn đang hoạt động đúng.

## 1. Vì sao cần kiểm thử tập luật?

### 1.1. Rule thường tương tác với nhau

Giả sử hệ thống có ba rule:

~~~text
rule PremiumCustomer {
    when customer.tier == PREMIUM
    then discount = 0.15
}

rule LargeOrder {
    when order.total >= 1000000 VND
    then discount = 0.10
}

rule NewCustomer {
    when customer.isNew
    then discount = 0.05
}
~~~

Một đơn hàng có thể thỏa mãn cả ba điều kiện. Nếu hệ thống cộng các mức giảm, chọn mức cao nhất hoặc chỉ áp dụng rule ưu tiên cao nhất, kết quả sẽ khác nhau. Kiểm thử từng rule riêng lẻ không phát hiện được sai khác trong chính sách kết hợp.

### 1.2. Quy tắc nghiệp vụ thường có nhiều trường hợp biên

Điều kiện như age >= 18 hoặc amount > 100000 có thể xử lý sai tại giá trị đúng bằng ngưỡng. Các lỗi off-by-one, làm tròn, timezone và null thường chỉ xuất hiện ở những trường hợp biên.

### 1.3. Thay đổi rule có thể gây hồi quy

Thêm một rule mới có thể làm một quyết định trước đây đổi kết quả. Sửa một điều kiện có thể khiến nhiều rule cùng khớp hoặc không còn rule nào khớp. Bộ kiểm thử hồi quy giữ lại những trường hợp quan trọng để phát hiện thay đổi ngoài dự kiến.

### 1.4. Quyết định cần giải thích được

Trong nhiều miền, người vận hành cần biết rule nào đã khớp, rule nào bị bỏ qua và vì sao kết quả được chọn. Kiểm thử có trace giúp xác nhận không chỉ kết quả cuối cùng mà cả đường đi dẫn đến quyết định.

### 1.5. Tác động có thể lớn hơn lỗi kỹ thuật

Một lỗi trong tập luật có thể làm:

- Tính sai phí hoặc giá.
- Chấp nhận giao dịch không đủ điều kiện.
- Từ chối khách hàng hợp lệ.
- Bỏ qua kiểm tra rủi ro.
- Gửi yêu cầu đến sai luồng phê duyệt.
- Thực hiện hành động bên ngoài nhiều lần.

Vì vậy, phạm vi kiểm thử cần dựa trên mức độ ảnh hưởng của quyết định, không chỉ dựa trên độ phức tạp của mã DSL.

## 2. Mục tiêu và phạm vi kiểm thử

### 2.1. Kiểm tra tính đúng đắn của từng rule

Với mỗi rule, xác nhận:

- Điều kiện đúng tạo ra hành động mong đợi.
- Điều kiện sai không kích hoạt hành động.
- Các giá trị biên được xử lý chính xác.
- Kiểu dữ liệu và giá trị thiếu được xử lý theo hợp đồng.
- Hành động tạo đúng kết quả hoặc side effect được quy định.

### 2.2. Kiểm tra tương tác giữa các rule

Kiểm tra những tình huống:

- Không có rule nào khớp.
- Chỉ một rule khớp.
- Nhiều rule cùng khớp.
- Hai rule đưa ra hành động mâu thuẫn.
- Rule có độ ưu tiên khác nhau cùng khớp.
- Một rule thay đổi trạng thái khiến rule khác có thể khớp.

### 2.3. Kiểm tra kết quả quyết định

Một tập luật có thể trả về:

- Một kết quả duy nhất.
- Một danh sách kết quả.
- Một quyết định cùng lý do.
- Một trạng thái cần chuyển tiếp.
- Một tập hành động cần thực thi.
- Một lỗi hoặc trạng thái không xác định.

Test cần xác nhận đúng kiểu kết quả, nội dung và cardinality.

### 2.4. Kiểm tra các bất biến

Bất biến (*invariant*) là điều kiện phải luôn đúng, bất kể đầu vào cụ thể. Ví dụ:

- Mức giảm giá không âm và không vượt 100%.
- Một giao dịch không được vừa APPROVED vừa REJECTED.
- Mỗi yêu cầu chỉ có một quyết định cuối cùng.
- Rule bị vô hiệu hóa không được kích hoạt.
- Một hành động thanh toán không được thực hiện hai lần cho cùng một idempotency key.

### 2.5. Kiểm tra khả năng vận hành

Ngoài kết quả, cần xem xét:

- Thời gian đánh giá.
- Số rule được xét.
- Bộ nhớ và số lần truy cập dữ liệu.
- Hành vi khi dependency lỗi.
- Khả năng hủy hoặc timeout.
- Chất lượng diagnostics và decision trace.

## 3. Mô hình hóa tập luật trước khi viết test

### 3.1. Xác định đầu vào và đầu ra

Trước khi tạo test, cần mô tả hợp đồng của decision:

~~~text
DecisionInput:
    customer: Customer
    order: Order
    evaluationTime: Instant

DecisionOutput:
    discount: Money
    shipping: ShippingDecision
    reasons: List<DecisionReason>
~~~

Hợp đồng này làm rõ dữ liệu nào ảnh hưởng đến quyết định và kết quả nào cần xác minh.

### 3.2. Lập danh sách rule

Mỗi rule nên có định danh ổn định, mục đích, điều kiện, hành động, trạng thái bật/tắt, priority và nhóm nghiệp vụ.

| Thuộc tính | Ý nghĩa |
|---|---|
| Rule ID | Định danh ổn định để trace và test |
| Name | Tên dễ đọc |
| Condition | Điều kiện kích hoạt |
| Action | Hành động hoặc kết quả |
| Priority | Độ ưu tiên nếu engine sử dụng |
| Activation | Trạng thái enabled/disabled |
| Group | Nhóm hoặc phase đánh giá |
| Owner | Người chịu trách nhiệm nghiệp vụ |

### 3.3. Xác định semantics của engine

Trước khi viết expected result, phải biết engine thực thi tập luật theo mô hình nào:

- First match: dừng ở rule đầu tiên khớp.
- All match: chạy mọi rule khớp.
- Priority: chọn hoặc sắp xếp theo độ ưu tiên.
- Agenda: đưa rule khớp vào lịch thực thi.
- Sequential: chạy theo thứ tự khai báo hoặc thứ tự cấu hình.
- Stateful: hành động có thể thay đổi trạng thái để kích hoạt lần đánh giá tiếp theo.

Không được suy đoán semantics từ tên framework. Nó cần được định nghĩa trong hợp đồng của DSL và runtime.

### 3.4. Xác định điều kiện dừng

Với engine có vòng lặp đánh giá, cần xác định khi nào quá trình kết thúc:

- Không còn rule nào khớp.
- Đã chọn được một quyết định cuối.
- Đạt giới hạn số vòng.
- Gặp trạng thái terminal.
- Có lỗi không thể phục hồi.

Test cần xác nhận engine không chạy vô hạn và không thực hiện hành động lặp ngoài ý muốn.

### 3.5. Phân loại mức độ rủi ro

Có thể phân loại rule theo tác động:

- Thấp: hiển thị nhãn hoặc gợi ý.
- Trung bình: tính phí, phân nhóm hoặc điều hướng.
- Cao: cấp quyền, phê duyệt, từ chối hoặc thay đổi dữ liệu quan trọng.
- Rất cao: thanh toán, giao dịch tài chính hoặc quyết định có yêu cầu kiểm soát nghiêm ngặt.

Rule có tác động cao cần test sâu hơn, review độc lập và bằng chứng rõ ràng.

## 4. Các cấp độ kiểm thử

### 4.1. Unit test cho rule

Kiểm tra một rule với đầu vào cụ thể, xác nhận điều kiện và hành động.

### 4.2. Component test cho nhóm rule

Chạy một nhóm rule có chung mục tiêu, ví dụ nhóm tính phí hoặc nhóm kiểm tra điều kiện tín dụng. Test tập trung vào tương tác trong phạm vi nhóm.

### 4.3. Integration test

Chạy tập luật cùng schema, function provider, connector và runtime thật hoặc môi trường tích hợp gần thực tế. Mục tiêu là xác nhận ranh giới giữa DSL và các dịch vụ hoạt động đúng.

### 4.4. Decision test đầu-cuối

Đưa một request đại diện vào đúng entry point mà ứng dụng sử dụng, rồi kiểm tra quyết định cuối, trace và side effect.

### 4.5. Regression test

Chạy lại các trường hợp đã được xác nhận khi rule, schema, engine hoặc plugin thay đổi.

### 4.6. Performance test

Đo thời gian và tài nguyên với số lượng rule, dữ liệu và tần suất đánh giá gần thực tế.

### 4.7. Acceptance test

Domain expert hoặc người sở hữu chính sách xác nhận các trường hợp nghiệp vụ quan trọng. Acceptance test nên dùng ngôn ngữ gần với ví dụ nghiệp vụ, nhưng vẫn có dữ liệu và kết quả xác định.

## 5. Test case và expected result

### 5.1. Cấu trúc một test case

Một test case cho tập luật có thể gồm:

- ID.
- Mục tiêu.
- Rule hoặc nhóm rule liên quan.
- Input fixture.
- Trạng thái và cấu hình engine.
- Expected decision.
- Expected fired rules.
- Expected side effects.
- Expected trace hoặc diagnostics.

Ví dụ:

| Trường | Giá trị |
|---|---|
| Test ID | DISC-001 |
| Mục tiêu | Khách hàng Premium được giảm giá |
| Input | tier=PREMIUM, order.total=200000 VND |
| Expected | discount=15% |
| Fired rules | PremiumCustomer |
| Side effect | Không có |

### 5.2. Expected result cần cụ thể

Không nên ghi “kết quả đúng” hoặc “rule chạy thành công”. Hãy chỉ rõ:

~~~text
expected.discount = Money(30000, VND)
expected.decision = APPROVED
expected.firedRuleIds = ["premium-discount"]
expected.auditEventCount = 1
~~~

Nếu thứ tự fired rule không phải một phần của hợp đồng, nên so sánh tập ID thay vì danh sách có thứ tự.

### 5.3. Test cả kết quả và đường đi

Hai engine có thể trả cùng decision nhưng thực thi rule khác nhau. Nếu thứ tự hoặc trace là một phần semantics, cần xác nhận fired rules, skipped rules và lý do.

### 5.4. Negative test

Negative test xác nhận điều không được phép xảy ra:

- Rule không khớp không tạo hành động.
- Người dùng không đủ quyền không được approve.
- Rule disabled không được chạy.
- Giao dịch bị từ chối không gửi lệnh capture.
- Đầu vào sai kiểu không tạo quyết định giả định.

## 6. Decision table

### 6.1. Decision table là gì?

Decision table biểu diễn tổ hợp điều kiện và kết quả trong một bảng. Nó hữu ích khi một quyết định phụ thuộc vào nhiều thuộc tính.

Giả sử miễn phí vận chuyển khi khách hàng Premium hoặc đơn hàng đạt ngưỡng:

| Customer Premium? | Order >= 1.000.000 VND? | Free shipping? |
|---|---|---|
| No | No | No |
| No | Yes | Yes |
| Yes | No | Yes |
| Yes | Yes | Yes |

Bảng này cho thấy đủ bốn tổ hợp của hai điều kiện Boolean.

### 6.2. Từ bảng sang test

Mỗi dòng có thể trở thành một test case. Dữ liệu cụ thể cần chọn sao cho các điều kiện khác không vô tình ảnh hưởng kết quả.

### 6.3. Điều kiện nhiều giá trị

Nếu customer tier có STANDARD, GOLD và PREMIUM, còn order channel có ONLINE, STORE và PARTNER, số tổ hợp có thể tăng nhanh. Decision table giúp nhìn rõ các tổ hợp được hỗ trợ và những kết quả tương ứng.

### 6.4. Don't care

Một số điều kiện không ảnh hưởng kết quả trong một nhánh. Có thể biểu diễn chúng bằng dấu * hoặc “không quan trọng”, nhưng chỉ khi nghiệp vụ thực sự xác nhận điều đó.

### 6.5. Rule table và decision table

Rule table mô tả rule được cấu hình trong engine. Decision table mô tả quan hệ giữa điều kiện và kết quả mong đợi. Hai bảng có thể giống hình thức nhưng mục đích khác nhau: một là cấu hình thực thi, một là đặc tả hoặc oracle kiểm thử.

## 7. Kiểm thử điều kiện và giá trị biên

### 7.1. Boundary value analysis

Lỗi thường xuất hiện tại ranh giới giữa hai vùng điều kiện. Với rule:

~~~text
when order.total >= 1000000 VND
then freeShipping()
~~~

các test nên gồm:

- 999999 VND.
- 1000000 VND.
- 1000001 VND.

### 7.2. Kiểm tra cả hai phía ngưỡng

Nếu điều kiện dùng > thay vì >=, kết quả tại đúng ngưỡng sẽ thay đổi. Test biên giúp phát hiện lỗi ký hiệu so sánh.

### 7.3. Phân vùng tương đương

Chia miền đầu vào thành các lớp có hành vi dự kiến giống nhau. Ví dụ tuổi:

- Dưới 18.
- Từ 18 đến 64.
- Từ 65 trở lên.

Chọn ít nhất một đại diện cho mỗi lớp, sau đó bổ sung test biên tại 17, 18, 64 và 65.

### 7.4. Giá trị null và thiếu

Nếu trường có thể null hoặc không được cung cấp, cần test:

- Có giá trị hợp lệ.
- Giá trị null.
- Field không xuất hiện.
- Giá trị sai kiểu.
- Giá trị rỗng nếu khác null.

Null, missing và empty string không nên bị gộp nếu DSL phân biệt chúng.

### 7.5. Kiểu số và độ chính xác

Test các trường hợp:

- Số nguyên và số thập phân.
- Giá trị âm nếu được phép.
- Giá trị cực đại và cực tiểu.
- Làm tròn tại nửa đơn vị.
- Overflow.
- Đơn vị không tương thích.

### 7.6. Ngày giờ

Kiểm thử thời điểm ngay trước, đúng tại và ngay sau ngưỡng thời gian. Với timezone, daylight saving hoặc ngày cuối tháng, cần dùng dữ liệu cố định để kết quả có thể tái hiện.

### 7.7. Điều kiện kết hợp

Với điều kiện AND, OR và NOT, test từng nhánh và các tổ hợp quan trọng. Đừng chỉ kiểm tra trường hợp mọi điều kiện đều true.

## 8. Rule coverage và condition coverage

### 8.1. Rule coverage

Rule coverage đo tỷ lệ rule đã được kích hoạt ít nhất một lần trong bộ test:

\[
RuleCoverage = \frac{\text{Số rule được kích hoạt}}{\text{Tổng số rule}} \times 100\%
\]

Coverage cao cho biết nhiều rule đã được chạy, nhưng không chứng minh mọi nhánh điều kiện hoặc mọi tương tác đều đúng.

### 8.2. Condition coverage

Condition coverage kiểm tra từng điều kiện con đã nhận cả giá trị true và false hay chưa.

Ví dụ:

~~~text
customer.active and order.total >= 100000
~~~

Cần có test khiến customer.active true và false, đồng thời kiểm tra điều kiện ngưỡng ở cả hai phía.

### 8.3. Decision coverage

Decision coverage kiểm tra toàn bộ biểu thức quyết định đã cho kết quả true và false. Với biểu thức nhiều điều kiện, decision coverage không bảo đảm từng điều kiện độc lập đã được kiểm tra.

### 8.4. Modified Condition/Decision Coverage

MC/DC yêu cầu chứng minh mỗi điều kiện con có thể độc lập làm thay đổi kết quả quyết định trong khi các điều kiện khác được kiểm soát. Nó hữu ích cho logic có rủi ro cao nhưng cần thiết kế test cẩn thận.

### 8.5. Action coverage

Action coverage đo tỷ lệ hành động hoặc nhánh kết quả đã được thực hiện. Một rule có thể được kích hoạt nhưng hành động bên trong có nhiều nhánh; cần đo riêng nếu các nhánh đó quan trọng.

### 8.6. Coverage không phải chất lượng

Một test có thể chạy qua mọi rule nhưng không kiểm tra kết quả mong đợi. Coverage chỉ là tín hiệu về phạm vi thực thi; cần kết hợp assertion, mutation testing và review nghiệp vụ.

## 9. Pairwise và combinatorial testing

### 9.1. Bùng nổ tổ hợp

Giả sử quyết định phụ thuộc vào:

- Tier: 4 giá trị.
- Channel: 3 giá trị.
- Region: 5 giá trị.
- Payment status: 4 giá trị.
- Customer age group: 3 giá trị.

Kiểm tra toàn bộ tổ hợp cần \(4 \times 3 \times 5 \times 4 \times 3 = 720\) trường hợp.

### 9.2. Pairwise testing

Pairwise testing chọn tập test sao cho mọi cặp giá trị giữa hai yếu tố đều xuất hiện ít nhất một lần. Nó có thể giảm số test đáng kể khi lỗi thường do tương tác giữa hai yếu tố.

### 9.3. Giới hạn của pairwise

Pairwise không bảo đảm phát hiện lỗi chỉ xuất hiện khi ba hoặc nhiều yếu tố kết hợp. Với rule có điều kiện phụ thuộc sâu hoặc rủi ro cao, cần test tổ hợp bậc cao và test theo domain knowledge.

### 9.4. Constraint giữa các tham số

Một số tổ hợp không hợp lệ, ví dụ payment status REFUNDED không thể đi cùng trạng thái order chưa thanh toán. Test generator cần biết constraint để không tạo dữ liệu vô nghĩa.

### 9.5. Chọn mức độ phù hợp

Có thể dùng:

- Exhaustive testing cho miền nhỏ.
- Pairwise cho nhiều thuộc tính có tương tác vừa phải.
- 3-way hoặc higher-order testing cho nhóm rủi ro.
- Scenario-based testing cho luồng nghiệp vụ dài.

## 10. Kiểm thử xung đột và ưu tiên rule

### 10.1. Nhiều rule cùng khớp

Nếu engine hỗ trợ nhiều rule cùng khớp, cần test rõ:

- Rule nào được thực thi?
- Thứ tự ra sao?
- Có chạy tất cả action không?
- Có chọn một kết quả cuối không?
- Có phát hiện xung đột không?

### 10.2. Priority

Giả sử:

~~~text
rule FraudBlock priority 100 {
    when riskScore >= 90
    then decision = REJECT
}

rule PreferredCustomer priority 20 {
    when customer.tier == PREMIUM
    then decision = APPROVE
}
~~~

Nếu cả hai rule khớp, test cần xác nhận semantics priority của engine. Không được giả định priority cao hơn luôn thắng nếu engine dùng agenda hoặc quy tắc tie-break khác.

### 10.3. Tie-break

Hai rule cùng priority có thể được xử lý theo:

- Thứ tự khai báo.
- Rule ID.
- Thứ tự đăng ký.
- Chính sách conflict resolver.
- Không xác định nếu đặc tả không quy định.

Nếu kết quả nghiệp vụ phụ thuộc tie-break, phải làm cho quy tắc đó tường minh và kiểm thử.

### 10.4. Xung đột hành động

Hai rule có thể đặt cùng một biến thành giá trị khác nhau hoặc tạo hai hành động đối lập. Cần kiểm tra:

- Conflict có được phát hiện?
- Có policy giải quyết?
- Có diagnostic?
- Có thể xảy ra trạng thái trung gian không hợp lệ?

### 10.5. Rule disabled

Test xác nhận rule disabled không tham gia đánh giá, kể cả khi điều kiện của nó đúng. Nếu trạng thái bật/tắt có thể thay đổi theo workspace hoặc môi trường, phải test từng cấu hình liên quan.

### 10.6. Rule group và salience

Nếu engine có nhóm, phase hoặc salience, test cần xác nhận rule chỉ chạy trong đúng nhóm và theo đúng thứ tự chuyển phase.

## 11. Kiểm thử thứ tự và tính độc lập

### 11.1. Order dependence

Một tập luật có thể cho kết quả khác nếu đổi thứ tự rule. Điều này có thể là semantics có chủ ý hoặc lỗi thiết kế.

### 11.2. Order independence

Nếu các rule được kỳ vọng độc lập, hoán đổi thứ tự khai báo không nên làm thay đổi kết quả cuối. Có thể viết test chạy cùng input trên nhiều permutation hợp lệ.

### 11.3. Commutativity

Hai rule độc lập có thể được kỳ vọng cho cùng trạng thái cuối dù thực thi theo thứ tự nào. Test có thể so sánh:

~~~text
evaluate([RuleA, RuleB], input)
evaluate([RuleB, RuleA], input)
~~~

Kết quả chỉ cần bằng nhau nếu hợp đồng của engine và rule set yêu cầu tính giao hoán.

### 11.4. Idempotency

Một rule hoặc tập luật idempotent khi áp dụng lặp lại không tạo thêm thay đổi sau lần đầu:

~~~text
applyRules(applyRules(state)) == applyRules(state)
~~~

Đặc tính này quan trọng với retry và hệ thống xử lý event. Không phải mọi rule set đều cần idempotent, nhưng side effect cần có chính sách rõ.

### 11.5. Termination

Với engine lặp đến khi không còn rule khớp, cần test rằng trạng thái tiến tới điểm dừng. Một rule liên tục kích hoạt lại chính nó có thể gây vòng lặp.

Có thể giới hạn số lần kích hoạt hoặc số vòng và kiểm tra engine trả lỗi rõ khi vượt giới hạn.

## 12. Test fixture và dữ liệu kiểm thử

### 12.1. Fixture

Fixture là dữ liệu đầu vào được chuẩn bị sẵn cho một test. Fixture tốt cần nhỏ, rõ và chỉ chứa những thuộc tính liên quan đến trường hợp đang kiểm tra.

~~~yaml
customer:
  id: C-101
  tier: PREMIUM
  isNew: false
order:
  id: O-501
  total:
    amount: 800000
    currency: VND
  status: PENDING
~~~

### 12.2. Builder

Test builder giúp tạo dữ liệu mặc định hợp lệ và chỉ thay đổi những trường cần thiết:

~~~java
Customer customer = customerBuilder()
    .tier(PREMIUM)
    .isNew(false)
    .build();
~~~

Builder giảm trùng lặp nhưng không nên che giấu dữ liệu quan trọng của test.

### 12.3. Dữ liệu tối thiểu

Chỉ tạo dữ liệu cần thiết để kiểm tra rule. Fixture quá lớn khiến test khó hiểu và dễ bị ảnh hưởng bởi thay đổi không liên quan.

### 12.4. Dữ liệu biên và dữ liệu thực tế

Kết hợp dữ liệu tổng hợp có chủ đích với dữ liệu đã ẩn danh hoặc dữ liệu mẫu đại diện. Dữ liệu thực tế có thể bộc lộ phân bố và tương tác khó đoán, nhưng cần bảo vệ thông tin nhạy cảm.

### 12.5. Tránh phụ thuộc dữ liệu môi trường

Không nên để test dùng trực tiếp database phát triển có dữ liệu thay đổi theo thời gian. Mỗi test cần có fixture hoặc snapshot được kiểm soát.

### 12.6. Deterministic clock và random

Nếu rule phụ thuộc ngày hiện tại, tuổi, thời hạn hoặc random score, hãy inject clock và random provider cố định. Test không nên thay đổi kết quả chỉ vì chạy vào ngày khác.

### 12.7. Test isolation

Một test không nên làm thay đổi dữ liệu khiến test khác thất bại. Dùng transaction rollback, database riêng, fixture reset hoặc fake service tùy loại side effect.

## 13. Kiểm thử hành động và side effect

### 13.1. Tách quyết định khỏi hành động

Một kiến trúc dễ kiểm thử thường tách:

1. Đánh giá rule để tạo decision.
2. Diễn giải decision thành command.
3. Thực thi command qua service.

Nhờ vậy, có thể kiểm tra logic quyết định mà không cần gửi email, thanh toán hoặc ghi dữ liệu thật.

### 13.2. Verify command

Test có thể xác nhận:

~~~text
expected.commands = [
    SendNotification(customerId, "APPROVED")
]
~~~

Sau đó một integration test riêng xác nhận command handler gọi đúng dịch vụ.

### 13.3. Exactly-once không tự nhiên tồn tại

Nếu engine retry sau timeout, side effect có thể được thực hiện hai lần. Test cần kiểm tra idempotency key, deduplication hoặc transaction/outbox pattern khi phù hợp.

### 13.4. Failure injection

Mô phỏng dịch vụ ngoài:

- Timeout.
- Connection refused.
- Response sai schema.
- Permission denied.
- Lỗi tạm thời.
- Lỗi vĩnh viễn.

Kiểm tra tập luật và command handler có trả trạng thái rõ ràng, retry đúng và không tạo quyết định sai.

### 13.5. Transaction boundary

Nếu một quyết định gồm nhiều cập nhật, test cần xác nhận khi một bước thất bại thì trạng thái được rollback, bù trừ hoặc đánh dấu cần xử lý tiếp theo theo đúng thiết kế.

## 14. Property-based testing

### 14.1. Khái niệm

Property-based testing tạo nhiều đầu vào từ generator rồi kiểm tra một thuộc tính phải luôn đúng, thay vì chỉ chạy một số ví dụ cố định.

Ví dụ, với rule tính giảm giá:

~~~text
forAll validOrder:
    0 <= discount(order) <= order.total
~~~

### 14.2. Generator có constraint

Generator cần tạo dữ liệu hợp lệ theo schema và constraint miền. Nếu tạo input vô nghĩa, test có thể chỉ phát hiện lỗi validation thay vì kiểm tra rule.

### 14.3. Shrinking

Khi tìm được input làm property thất bại, framework có thể thu nhỏ input để tìm trường hợp tối giản. Điều này giúp hiểu nguyên nhân và biến lỗi thành regression test.

### 14.4. Property về bất biến

Một số property hữu ích:

- Discount không âm.
- Total sau giảm không lớn hơn total trước giảm.
- Decision không chứa hai trạng thái cuối đối nghịch.
- Rule disabled không xuất hiện trong fired rule set.
- Mọi decision cuối đều có reason code.
- Một input giống nhau trong cùng context cho cùng decision nếu tập luật deterministic.

### 14.5. Property cần giới hạn

Không nên giả định tính chất toán học nếu nghiệp vụ không yêu cầu. Ví dụ, tổng giảm giá có thể không giao hoán nếu có cap hoặc thứ tự áp dụng. Property phải xuất phát từ hợp đồng nghiệp vụ.

## 15. Metamorphic testing

### 15.1. Khi không có oracle đầy đủ

Với một số rule phức tạp, khó biết kết quả đúng cho mọi input. Metamorphic testing kiểm tra quan hệ giữa kết quả của các input có liên hệ.

### 15.2. Ví dụ về ngưỡng

Nếu chỉ tăng order.total và mọi điều kiện khác giữ nguyên, một rule miễn phí vận chuyển theo ngưỡng không nên chuyển từ true sang false:

~~~text
total2 >= total1
eligible(total1) == true
=> eligible(total2) == true
~~~

Property này chỉ đúng nếu không có điều kiện khác phụ thuộc vào total theo hướng ngược lại.

### 15.3. Ví dụ về thêm dữ liệu không liên quan

Nếu query hoặc rule chỉ xét customerId cụ thể, thêm một Customer khác không nên làm thay đổi quyết định cho customer đó.

### 15.4. Ví dụ về thứ tự

Nếu thứ tự input collection không có ý nghĩa, hoán vị collection không nên thay đổi decision. Nếu order có ý nghĩa, property này không áp dụng.

### 15.5. Metamorphic relation phải có căn cứ

Quan hệ biến đổi cần được domain expert xác nhận. Nếu tự đặt một quan hệ sai, test có thể báo lỗi giả hoặc bỏ qua lỗi thật.

## 16. Golden test và snapshot test

### 16.1. Golden test

Golden test lưu kết quả mong đợi đã được xác nhận cho một input cụ thể. Khi chạy lại, hệ thống so sánh output mới với golden file.

Ví dụ:

~~~text
input: premium-customer-large-order.yml
expected: premium-large-order-decision.json
~~~

### 16.2. Snapshot của decision trace

Có thể lưu:

- Fired rule IDs.
- Thứ tự đánh giá nếu có ý nghĩa.
- Decision result.
- Reason codes.
- Commands.
- Diagnostics.

### 16.3. Cập nhật golden

Không nên tự động chấp nhận golden mới chỉ vì test báo khác. Người có trách nhiệm cần xem xét thay đổi và xác nhận đó là thay đổi nghiệp vụ mong muốn.

### 16.4. Snapshot quá chi tiết

Snapshot chứa timestamp, generated ID hoặc dữ liệu không ổn định có thể gây nhiễu. Chuẩn hóa những trường không thuộc hợp đồng so sánh, nhưng không loại bỏ thông tin có ý nghĩa.

## 17. Regression testing khi thay đổi tập luật

### 17.1. Giữ lại trường hợp quan trọng

Mỗi lỗi production hoặc thay đổi chính sách đáng kể nên bổ sung test hồi quy. Test cần mô tả input đã gây lỗi và expected behavior sau khi sửa.

### 17.2. Phân loại regression suite

Có thể chia:

- Smoke: một số quyết định quan trọng, chạy nhanh.
- Core: các rule và decision phổ biến.
- Boundary: các ngưỡng và trường hợp biên.
- Interaction: xung đột và kết hợp rule.
- Full: toàn bộ test và dữ liệu đại diện.

### 17.3. Impact analysis

Khi một rule hoặc schema thay đổi, xác định:

- Rule nào phụ thuộc vào field được sửa?
- Query hoặc function nào thay đổi?
- Test nào liên quan?
- Decision nào có thể bị ảnh hưởng?

Dependency graph hoặc rule reference index có thể giúp chọn tập test phù hợp.

### 17.4. Baseline comparison

Chạy cùng bộ input trên phiên bản hiện tại và phiên bản mới, sau đó so sánh:

- Decision result.
- Fired rule set.
- Reason codes.
- Side effects.
- Diagnostics.

Khác biệt không tự động là lỗi; cần phân loại là thay đổi dự kiến hay ngoài dự kiến.

### 17.5. Regression do engine hoặc plugin

Không chỉ sửa rule mới gây hồi quy. Nâng compiler, runtime, function provider hoặc plugin cũng có thể thay semantics. Bộ regression cần chạy khi những dependency này thay đổi.

## 18. Simulation và what-if testing

### 18.1. Simulation

Simulation chạy tập luật trên dữ liệu mẫu hoặc dữ liệu lịch sử mà không thực hiện side effect production. Nó giúp quan sát phân bố quyết định và rule nào được kích hoạt.

### 18.2. What-if

What-if testing so sánh kết quả hiện tại với một bộ rule thay đổi:

~~~text
Baseline rules: discount threshold = 1,000,000 VND
Candidate rules: discount threshold = 750,000 VND
~~~

Chạy cùng tập dữ liệu để xác định bao nhiêu trường hợp đổi quyết định.

### 18.3. Shadow evaluation

Có thể đánh giá phiên bản rule mới song song với phiên bản đang phục vụ, nhưng chỉ dùng kết quả mới để quan sát. Không thực hiện side effect từ shadow evaluation.

### 18.4. Historical replay

Replay dữ liệu lịch sử giúp phát hiện tác động của thay đổi trên workload thực tế. Cần lưu đủ input, context, schema và dependency version để kết quả có thể tái hiện.

### 18.5. Phân tích chênh lệch

Báo cáo simulation nên nhóm:

- Quyết định không đổi.
- Quyết định đổi từ A sang B.
- Rule mới được kích hoạt.
- Rule cũ không còn kích hoạt.
- Trường hợp lỗi hoặc không xác định.

### 18.6. Giới hạn dữ liệu lịch sử

Dữ liệu lịch sử có thể không đại diện tương lai và có thể chứa dữ liệu nhạy cảm. Cần ẩn danh, giới hạn truy cập và ghi nhận thời điểm dữ liệu.

## 19. Kiểm thử decision trace và explainability

### 19.1. Decision trace

Trace ghi lại quá trình engine đánh giá:

~~~text
Decision: ORDER-501
  Rule premium-customer: MATCH
  Rule large-order: NO_MATCH
  Rule fraud-review: MATCH
  Resolver: PRIORITY
  Selected decision: MANUAL_REVIEW
~~~

### 19.2. Test fired rule

Xác nhận đúng rule được kích hoạt. Với engine có nhiều phase, cần kiểm tra fired set theo phase.

### 19.3. Test skipped reason

Nếu hệ thống giải thích được vì sao rule không chạy, test có thể xác nhận:

- Điều kiện false.
- Rule disabled.
- Thiếu quyền.
- Không thuộc group đang chạy.
- Bị loại bởi conflict policy.

### 19.4. Reason code ổn định

Reason code nên ổn định qua các bản dịch message. Test nên ưu tiên code và dữ liệu có cấu trúc hơn là so sánh toàn bộ câu văn nếu wording có thể thay đổi.

### 19.5. Không lộ dữ liệu nhạy cảm

Trace có thể chứa input hoặc giá trị trung gian. Test cần xác nhận secret, thông tin cá nhân và dữ liệu bị hạn chế được mask theo policy.

## 20. Kiểm thử trạng thái và rule engine có bộ nhớ

### 20.1. Stateless và stateful

Stateless engine đánh giá mỗi request từ input và context. Stateful engine có thể giữ fact, state hoặc event giữa các lần đánh giá.

### 20.2. Kiểm thử chuỗi sự kiện

Với stateful rule engine, test cần xác định thứ tự event:

~~~text
OrderCreated
PaymentAuthorized
PaymentCaptured
OrderShipped
~~~

Quyết định có thể phụ thuộc vào event đã xảy ra trước đó.

### 20.3. Duplicate event

Gửi cùng event hai lần để kiểm tra deduplication và idempotency. Một event trùng không nên tạo side effect thứ hai nếu contract yêu cầu xử lý đúng một lần theo event ID.

### 20.4. Out-of-order event

Gửi event sai thứ tự để xác nhận engine:

- Từ chối.
- Đưa vào hàng chờ.
- Chuyển sang trạng thái cần xử lý.
- Hoặc chấp nhận theo semantics được quy định.

### 20.5. Reset state

Mỗi test cần có cách tạo state ban đầu xác định. Nếu state dùng chung giữa test, kết quả có thể phụ thuộc thứ tự chạy.

### 20.6. Time-based rule

Rule dựa trên timeout, thời hạn hoặc lịch cần test với clock giả lập và các thời điểm chính xác. Không nên dùng sleep thật để chờ thời gian trong unit test nếu có thể inject clock.

## 21. Kiểm thử tính đúng đắn của dữ liệu và schema

### 21.1. Input validation

Kiểm tra đầu vào thiếu field, sai kiểu, ngoài miền giá trị và vi phạm constraint. Không nên để rule tự diễn giải dữ liệu lỗi theo cách ngầm định.

### 21.2. Schema version

Nếu tập luật chạy trên nhiều schema version, cần test mapping hoặc validation cho từng phiên bản được hỗ trợ.

### 21.3. Null semantics

Kiểm tra Boolean ba trạng thái nếu engine hỗ trợ UNKNOWN. Đặc biệt chú ý điều kiện AND, OR và NOT khi một field null.

### 21.4. Reference integrity

Rule tham chiếu đến function, enum hoặc field không tồn tại cần bị phát hiện trước khi chạy hoặc trả diagnostic runtime có cấu trúc.

### 21.5. Unit và currency

Với Money, Distance hoặc Duration, test phép so sánh và tính toán giữa đơn vị tương thích và không tương thích.

### 21.6. Timezone và locale

Nếu rule phụ thuộc ngôn ngữ, locale hoặc timezone, context cần được cố định trong test. Một ngày theo UTC có thể khác ngày địa phương.

## 22. Kiểm thử hiệu năng và khả năng mở rộng

### 22.1. Số lượng rule

Chạy benchmark với:

- Tập luật nhỏ.
- Tập luật trung bình.
- Tập luật lớn.
- Nhiều rule cùng khớp.
- Hầu hết rule không khớp.

### 22.2. Kích thước dữ liệu

Thay đổi số lượng fact, record hoặc event để đo thời gian đánh giá và bộ nhớ.

### 22.3. Throughput và latency

Đo:

- Số quyết định mỗi giây.
- P50, P95 và P99 latency.
- Thời gian parse hoặc compile rule.
- Thời gian evaluate.
- Thời gian gọi function provider.

### 22.4. Cold start và warm execution

Đo riêng lần chạy đầu sau khi nạp rule và những lần chạy tiếp theo. Cache, JIT và index có thể làm hai loại latency khác nhau.

### 22.5. Contention

Nếu nhiều request dùng chung rule engine hoặc cache, test đồng thời để phát hiện race condition, lock contention và rò rỉ trạng thái giữa request.

### 22.6. Performance regression

Giữ benchmark baseline và so sánh khi số rule, compiler hoặc runtime thay đổi. Chỉ đặt ngưỡng cảnh báo khi môi trường đo đủ ổn định.

## 23. Kiểm thử bảo mật cho tập luật

### 23.1. Authorization rule

Test cả trường hợp có quyền và không có quyền. Không chỉ kiểm tra decision result mà còn xác nhận hành động bị chặn không được thực thi.

### 23.2. Bypass và precedence

Kiểm tra không có rule ưu tiên thấp nào vô tình ghi đè quyết định từ rule bảo mật hoặc compliance.

### 23.3. Input độc hại

Thử chuỗi quá dài, biểu thức lồng sâu, giá trị không hợp lệ và payload bất thường để xác nhận parser và engine có giới hạn tài nguyên.

### 23.4. Function provider

Nếu rule gọi function plugin, kiểm tra quyền và dữ liệu mà function được phép truy cập. Không để DSL gọi method tùy ý trên host object.

### 23.5. Audit

Quyết định nhạy cảm có thể cần audit event. Test xác nhận actor, timestamp, rule version, decision ID và reason code được ghi đúng.

### 23.6. Không dùng production side effect trong test

Test bảo mật phải chạy trên môi trường giả lập hoặc sandbox. Không dùng tài khoản thật để tạo giao dịch hoặc gửi thông báo ngoài ý muốn.

## 24. Test harness cho DSL luật

### 24.1. Vai trò

Test harness là bộ công cụ giúp nạp rule set, chuẩn bị context, chạy test case, thu decision trace và so sánh kết quả.

### 24.2. Thành phần

Một harness có thể gồm:

- Rule loader.
- Test data builder.
- Clock và random provider giả lập.
- Fake function providers.
- Decision runner.
- Trace collector.
- Assertion library.
- Report generator.

### 24.3. Ví dụ DSL test

~~~text
test "premium customer receives discount" {
    given {
        customer.tier = PREMIUM
        order.total = 200000 VND
    }

    when evaluate DiscountRules

    then {
        decision.discountRate == 0.15
        firedRules contains "premium-customer"
        commands isEmpty
    }
}
~~~

Đây là cú pháp minh họa. Test DSL nên dùng cùng parser và semantics được định nghĩa rõ; nếu không, test có thể kiểm tra một ngôn ngữ khác với rule source.

### 24.4. Parameterized tests

Một test có thể chạy trên nhiều bộ input:

~~~text
examples:
  - tier: STANDARD
    expectedRate: 0.00
  - tier: GOLD
    expectedRate: 0.10
  - tier: PREMIUM
    expectedRate: 0.15
~~~

Parameterized tests giúp bao phủ nhiều giá trị mà vẫn giữ một mô tả chung.

### 24.5. Test tags

Tag có thể nhóm test theo:

- Rule ID.
- Domain capability.
- Risk level.
- Regression issue.
- Environment.
- Runtime backend.

CI có thể chọn tập test theo tag nhưng vẫn cần chạy full suite theo lịch hoặc trước release quan trọng.

### 24.6. Report

Report nên hiển thị:

- Passed, failed và skipped.
- Rule coverage.
- Decision coverage nếu đo được.
- Các input gây lỗi.
- Expected và actual result.
- Trace liên quan.
- Phiên bản rule set và engine.

## 25. Tự động hóa kiểm thử trong CI/CD

### 25.1. Kiểm tra khi pull request

Pipeline có thể chạy:

1. Parse và validate rule source.
2. Type check.
3. Unit test cho rule thay đổi.
4. Regression suite cốt lõi.
5. Kiểm tra conflict và unreachable rule.
6. Sinh report coverage và decision diff.

### 25.2. Full suite

Full suite có thể chạy theo lịch, trước release hoặc khi schema/engine/plugin thay đổi.

### 25.3. Quality gate

Quality gate có thể yêu cầu:

- Không có test quan trọng thất bại.
- Không có lỗi parse hoặc type.
- Rule rủi ro cao có test tương ứng.
- Không giảm coverage dưới ngưỡng đã thống nhất.
- Không có thay đổi decision ngoài dự kiến.

Không nên dùng coverage đơn lẻ làm điều kiện duy nhất để cho phép phát hành.

### 25.4. Artifact test

CI nên lưu:

- Rule set version.
- Test report.
- Coverage data.
- Decision trace mẫu.
- Engine và plugin version.
- Hash của fixture và cấu hình.

Những artifact này giúp tái hiện kết quả sau này.

### 25.5. Environment parity

Test và production cần dùng semantics, schema và plugin version tương thích. Nếu môi trường khác nhau, report phải nêu rõ khác biệt.

## 26. Quản lý test khi rule thay đổi

### 26.1. Rule change review

Một thay đổi rule nên có:

- Mô tả nghiệp vụ.
- Input trước và sau.
- Decision dự kiến thay đổi.
- Test case mới hoặc cập nhật.
- Tác động đến rule liên quan.
- Người xác nhận.

### 26.2. Version hóa rule set

Mỗi bản phát hành rule set nên có version hoặc immutable revision. Decision trace cần tham chiếu đúng revision để có thể giải thích quyết định lịch sử.

### 26.3. Test ownership

Mỗi nhóm rule nên có owner chịu trách nhiệm duy trì test. Domain expert xác nhận semantics; developer duy trì harness và automation.

### 26.4. Deprecated rule

Khi rule bị đánh dấu deprecated, cần test rằng nó vẫn hoạt động trong giai đoạn chuyển tiếp nếu hợp đồng yêu cầu, và không còn được gọi sau khi gỡ bỏ.

### 26.5. Test data lifecycle

Fixture và historical sample cần được version hóa. Khi schema đổi, cần cập nhật hoặc migration fixture có kiểm soát.

## 27. Ví dụ tổng hợp: quyết định duyệt đơn hàng

Giả sử tập luật có các quy tắc:

~~~text
rule BlockedCustomer priority 100 {
    when customer.status == BLOCKED
    then decision = REJECT
}

rule HighRiskOrder priority 90 {
    when order.riskScore >= 80
    then decision = MANUAL_REVIEW
}

rule PremiumApproval priority 30 {
    when customer.tier == PREMIUM
      and order.total <= 5000000 VND
    then decision = APPROVE
}

rule StandardApproval priority 10 {
    when customer.status == ACTIVE
      and order.riskScore < 80
    then decision = APPROVE
}
~~~

Giả sử engine chọn quyết định theo rule khớp có priority cao nhất. Bộ test cần xác nhận rõ giả định đó.

### 27.1. Test cơ bản

| Case | Customer status | Tier | Risk score | Total | Expected |
|---|---|---|---:|---:|---|
| A | ACTIVE | STANDARD | 20 | 1000000 | APPROVE |
| B | ACTIVE | PREMIUM | 20 | 4000000 | APPROVE |
| C | BLOCKED | PREMIUM | 20 | 1000000 | REJECT |
| D | ACTIVE | PREMIUM | 90 | 1000000 | MANUAL_REVIEW |
| E | ACTIVE | STANDARD | 90 | 1000000 | MANUAL_REVIEW |

### 27.2. Test biên

Với riskScore >= 80:

- 79.99 phải không khớp HighRiskOrder.
- 80 phải khớp.
- 80.01 phải khớp.

Với total <= 5000000:

- 4999999 phải khớp PremiumApproval nếu các điều kiện khác đúng.
- 5000000 phải khớp.
- 5000001 không khớp.

### 27.3. Test xung đột

Case C đồng thời thỏa PremiumApproval và BlockedCustomer. Kết quả phải REJECT vì priority 100 cao hơn 30 theo giả định engine.

Case D thỏa HighRiskOrder và PremiumApproval. Kết quả phải MANUAL_REVIEW.

### 27.4. Test không có rule khớp

Đầu vào có status PENDING, tier STANDARD và riskScore 30 có thể không khớp rule nào. Engine cần trả trạng thái NO_DECISION hoặc kết quả mặc định đã được quy định, không tự suy ra APPROVE.

### 27.5. Test trace

Với case C, trace mong đợi có:

~~~text
BlockedCustomer: MATCH
HighRiskOrder: NO_MATCH
PremiumApproval: MATCH
Selected: BlockedCustomer
Decision: REJECT
~~~

### 27.6. Test side effect

Nếu REJECT tạo audit event nhưng không tạo payment command, test cần xác nhận chính xác số lượng và loại command. Không chỉ kiểm tra decision string.

### 27.7. Regression khi thay priority

Nếu priority của PremiumApproval được tăng lên 110, case C có thể đổi kết quả nếu cả hai rule khớp. Regression test phải phát hiện thay đổi này và yêu cầu xác nhận nghiệp vụ.

## 28. Đọc và xử lý kết quả kiểm thử

### 28.1. Phân loại lỗi

Khi test thất bại, có thể phân loại:

- Sai expected result hoặc test data.
- Rule condition sai.
- Sai semantics của engine.
- Sai schema hoặc mapping.
- Sai thứ tự/priority.
- Function provider lỗi.
- Side effect hoặc transaction lỗi.
- Môi trường test không tương đương.

### 28.2. So sánh expected và actual

Report nên hiển thị khác biệt theo cấu trúc:

~~~text
Expected:
  decision: APPROVE
  firedRules: [PremiumApproval]

Actual:
  decision: MANUAL_REVIEW
  firedRules: [HighRiskOrder, PremiumApproval]
~~~

Sau đó trace giúp xác định resolver đã chọn rule nào và tại sao.

### 28.3. Không sửa expected chỉ để làm test xanh

Nếu output thay đổi, cần xác định đó là thay đổi nghiệp vụ có chủ đích hay regression. Chỉ cập nhật expected sau khi người có trách nhiệm xác nhận.

### 28.4. Lưu lại trường hợp lỗi

Một bug đã sửa nên trở thành regression case ổn định. Giữ input tối thiểu, rule version gây lỗi và kết quả mong đợi.

## 29. Những sai lầm thường gặp

### 29.1. Chỉ test từng rule

Rule có thể đúng riêng lẻ nhưng xung đột khi cùng khớp. Cần test tập rule và resolver.

### 29.2. Chỉ kiểm tra kết quả cuối

Kết quả cuối có thể đúng do hai lỗi triệt tiêu nhau. Với quyết định quan trọng, cần kiểm tra fired rules, trace và side effect.

### 29.3. Bỏ qua trường hợp không có rule khớp

Default behavior cần được kiểm thử. Không có rule khớp không nên tự động trở thành quyết định cho phép.

### 29.4. Không test boundary

Giá trị ngay trước, đúng tại và ngay sau ngưỡng là các trường hợp cần có.

### 29.5. Dùng dữ liệu không xác định

Clock, random, external API và dữ liệu mutable làm test chập chờn. Hãy inject dependency và cố định fixture.

### 29.6. Nhầm coverage với correctness

Chạy qua 100% rule không chứng minh expected behavior đúng. Cần assertion, property và test nghiệp vụ.

### 29.7. Bỏ qua thứ tự và priority

Nếu semantics phụ thuộc thứ tự, cần test tie-break và conflict. Nếu không phụ thuộc, có thể test order independence.

### 29.8. Test side effect bằng dịch vụ production

Điều này có thể tạo giao dịch hoặc thông báo thật. Dùng fake, sandbox hoặc test environment.

### 29.9. Không giữ regression suite

Nếu chỉ test thay đổi mới, một rule sửa hôm nay có thể làm hỏng tình huống cũ mà không bị phát hiện.

### 29.10. Không version hóa engine và rule set

Khi không biết test đã chạy với rule version và plugin version nào, kết quả khó tái hiện.

## 30. Quy trình xây dựng bộ kiểm thử tập luật

Một quy trình thực tế có thể gồm:

1. **Xác định decision contract:** đầu vào, đầu ra, context và error semantics.
2. **Lập inventory rule:** ID, condition, action, priority, group và owner.
3. **Mô tả engine semantics:** first match, all match, agenda, priority hoặc stateful.
4. **Lập decision table:** bao phủ các tổ hợp điều kiện quan trọng.
5. **Chọn test biên:** ngưỡng, null, missing, số học, ngày giờ và đơn vị.
6. **Phân tích tương tác:** nhiều rule cùng khớp, conflict, tie-break và thứ tự.
7. **Tạo fixture xác định:** dữ liệu nhỏ, clock cố định và dependency giả lập.
8. **Viết test theo cấp độ:** unit, component, integration, acceptance và end-to-end.
9. **Bổ sung property và metamorphic tests:** kiểm tra bất biến và quan hệ giữa input.
10. **Lưu golden và regression cases:** chỉ cập nhật sau khi thay đổi được xác nhận.
11. **Kiểm tra trace và side effect:** fired rules, reason, command và audit.
12. **Chạy simulation:** so sánh rule version mới với baseline trên dữ liệu đại diện.
13. **Đo coverage và performance:** dùng nhiều chỉ số, không dựa vào một con số.
14. **Tự động hóa CI/CD:** chạy test phù hợp khi rule, schema, engine hoặc plugin thay đổi.
15. **Version hóa kết quả:** lưu rule revision, engine version, fixture và report.
16. **Duy trì ownership:** xác định người xác nhận nghiệp vụ và người duy trì kỹ thuật.

## 31. Câu hỏi tự đánh giá

1. Vì sao kiểm thử từng rule riêng lẻ chưa đủ để xác nhận cả tập luật?
2. Decision table giúp chuyển yêu cầu nghiệp vụ thành test như thế nào?
3. Phân biệt rule coverage, condition coverage và decision coverage.
4. Boundary value analysis cần kiểm tra những giá trị nào quanh một ngưỡng?
5. Pairwise testing giảm số lượng tổ hợp ra sao và có giới hạn gì?
6. Cần kiểm thử gì khi nhiều rule cùng khớp?
7. Priority và tie-break ảnh hưởng quyết định như thế nào?
8. Khi nào có thể kiểm tra order independence?
9. Idempotency và termination có ý nghĩa gì với rule engine?
10. Property-based testing khác test ví dụ cố định ra sao?
11. Metamorphic testing hữu ích khi nào?
12. Vì sao decision trace cần được kiểm tra cùng kết quả cuối?
13. Làm thế nào test side effect mà không gọi dịch vụ production?
14. Simulation và shadow evaluation giúp đánh giá thay đổi rule ra sao?
15. Cần lưu những metadata nào để tái hiện một lần kiểm thử?

## Kết luận

Kiểm thử tập luật phải xác nhận cả rule riêng lẻ lẫn cách chúng phối hợp để tạo ra quyết định. Decision table, phân vùng tương đương, kiểm thử giá trị biên, rule coverage, condition coverage, pairwise, property-based và metamorphic testing giúp mở rộng phạm vi kiểm tra. Test xung đột, priority, thứ tự, idempotency và termination xác nhận semantics của engine khi nhiều rule cùng tham gia.

Một bộ kiểm thử đáng tin cậy cần fixture xác định, expected result cụ thể, trace có thể giải thích, kiểm soát side effect và regression suite được version hóa. Simulation và shadow evaluation giúp quan sát tác động của thay đổi trên dữ liệu đại diện trước khi triển khai. Khi kiểm thử được tích hợp vào CI/CD và có domain owner xác nhận, tập luật có thể thay đổi thường xuyên mà vẫn giữ được bằng chứng về tính đúng đắn, khả năng tái hiện và mức độ rủi ro của mỗi quyết định.
