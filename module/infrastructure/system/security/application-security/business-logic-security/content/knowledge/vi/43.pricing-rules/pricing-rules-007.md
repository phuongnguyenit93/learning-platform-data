# Price calculation audit: kiểm chứng quá trình tính giá

## 1. Audit phép tính giá phải trả lời được những câu hỏi nào?

Trong chương **Pricing Rules**, *price calculation audit* là khả năng giải thích, tái dựng và kiểm chứng cách hệ thống đi từ dữ liệu đầu vào đến một số tiền được báo giá, phê duyệt hoặc thực thu.

Chỉ lưu `total = 54.83` không cho biết giá đó có đúng hay không. Một hồ sơ tính giá cần trả lời được:

- Giá sản phẩm lấy từ nguồn nào và có hiệu lực ở phiên bản nào?
- Ai được áp dụng khuyến mại, trên những dòng hàng nào?
- Phí và thuế được tính theo thứ tự nào?
- Đã làm tròn ở đâu, theo chế độ và đơn vị nào?
- Có điều chỉnh thủ công hay phê duyệt đặc biệt nào không?
- Quote nào đã được chấp nhận và gắn với lần thu tiền nào?
- Khi retry hoặc xử lý đồng thời, có phát sinh thêm nghĩa vụ tiền tệ không?

Trong bảo mật logic nghiệp vụ, một tổng tiền sai có thể xuất phát từ sửa giá trên request, dùng coupon ngoài quyền, đổi số lượng sau khi phê duyệt, áp dụng quy tắc cũ không hợp lệ hoặc thu nhiều lần. Audit cần giúp phân biệt những nguyên nhân đó, thay vì chỉ ghi “checkout thành công”.

Audit không tự tạo quyền và cũng không tự chứng minh phép tính đúng. Một bản ghi nói “đã cho phép giảm giá” chỉ là một lời khẳng định nếu không có căn cứ về dữ liệu, quy tắc và quyết định quyền. Cần kết hợp audit với business invariants, quyền theo đối tượng, state machine, transaction, idempotency và kiểm thử lạm dụng.

Bài này dùng tiền giả định **U**, đơn vị hạch toán **0,01 U** và các quy tắc giá minh họa. Các mức phí, thuế và điều kiện khuyến mại không đại diện cho yêu cầu pháp lý hoặc chính sách của một hệ thống thực tế.

## 2. Phân biệt log chẩn đoán, bằng chứng tính giá và giao dịch tiền

### 2.1. Ba lớp dữ liệu có mục đích khác nhau

| Lớp | Ví dụ | Mục đích |
|---|---|---|
| Log chẩn đoán | Thời gian xử lý, lỗi gọi dịch vụ, request ID | Tìm vấn đề vận hành |
| Bằng chứng tính giá | Snapshot đầu vào, rule version, từng bước và tổng | Giải thích giá và tái dựng kết quả |
| Giao dịch tiền | Lệnh thu, ledger, giao dịch provider, hoàn tiền | Chứng minh tác động tiền tệ thực tế |

Log có thể bị lấy mẫu, luân chuyển hoặc mất khi tiến trình dừng. Vì vậy, log thông thường không nên là nơi duy nhất giữ bằng chứng của một giá đã được chấp nhận.

Ngược lại, một hồ sơ tính giá không chứng minh rằng tiền đã được thu. Cần liên kết sang trạng thái và giao dịch thực tế, phân biệt quote được xem, quote được chấp nhận, khoản đã authorize, khoản đã capture và khoản đã hoàn theo mô hình sản phẩm.

### 2.2. Phân biệt calculation run với accepted snapshot

**Calculation run** là một lần thực hiện thuật toán tính giá. Có thể có nhiều run khi người dùng đổi giỏ hàng, nhập coupon hoặc yêu cầu báo giá lại.

**Accepted pricing snapshot** là nội dung giá bất biến mà một quyết định nghiệp vụ đã chấp nhận sử dụng. Snapshot đó cần được gắn với phiên bản đơn, danh tính có quyền xác nhận và lệnh tiền tương ứng.

Một calculation run lỗi hoặc bị từ chối không được hiển thị như giá đã được chấp thuận. Một snapshot đã chấp thuận cũng không được cập nhật tại chỗ để phản ánh lần tính mới.

Ví dụ:

~~~text
Order O1, version 4:
  Run R10 → quote Q10: 54,83 U.

Người dùng thay số lượng, order thành version 5:
  Run R11 → quote Q11: 72,10 U.
~~~

Lệnh thanh toán cho version 5 không được dùng Q10 chỉ vì nó rẻ hơn. Nếu sản phẩm cho phép giữ giá cũ trong một số điều kiện, điều đó phải được thể hiện bằng chính sách và quan hệ có hiệu lực riêng.

### 2.3. Correlation không phải authorization

`requestId`, `traceId` và `correlationId` giúp nối các sự kiện vận hành. Chúng không chứng minh actor có quyền xem đơn hoặc sử dụng quote.

Một người biết ID audit không được đọc mọi chi tiết tính giá. Định danh khó đoán cũng không thay thế kiểm tra tenant, quan hệ đối tượng và quyền hành động.

## 3. Những dữ liệu cần giữ để phép tính có thể tái dựng

### 3.1. Đầu vào phải có nguồn gốc rõ ràng

| Đầu vào | Nguồn quyết định có thẩm quyền | Bằng chứng nên giữ |
|---|---|---|
| Giá đơn vị | Danh mục giá hoặc offer do server kiểm chứng | Price ID, phiên bản, giá và loại tiền |
| Số lượng | Lệnh đã được kiểm tra trong ngữ cảnh đơn | Order version và số lượng đã chấp nhận |
| Điều kiện coupon | Dịch vụ hoặc quy tắc khuyến mại | Coupon reference, rule version, kết quả đủ điều kiện |
| Hạng khách hàng | Hồ sơ hoặc quyền lợi đã xác minh | Tham chiếu hoặc snapshot tối thiểu của quyền lợi |
| Phí giao hàng | Chính sách giao hàng hoặc báo giá được chấp nhận | Phương án, vùng hoặc dữ kiện tính phí cần thiết |
| Thuế suất minh họa | Chính sách thuế do server chọn | Nhóm áp dụng, phiên bản và cơ sở tính |
| Tỷ giá nếu có | Nguồn và snapshot tỷ giá được phép | Chiều cặp tiền, thời điểm dữ liệu và hiệu lực |
| Điều chỉnh thủ công | Quy trình có quyền riêng | Actor, lý do, phê duyệt và số tiền thay đổi |

Client có thể đề nghị SKU, số lượng, mã coupon hoặc địa chỉ giao hàng. Những đề nghị đó không tự tạo giá, quyền giảm hoặc mức phí được chấp nhận.

Không dùng `clientUnitPrice`, `isVip` hoặc `discountApproved` do request gửi làm căn cứ có thẩm quyền. Nếu lưu chúng để phân tích lạm dụng, cần đặt tên rõ là giá trị client đề nghị, không trộn với dữ liệu server đã xác minh.

### 3.2. Phiên bản mã chưa chắc đủ

Một tên như `pricing-v3` có thể không tái dựng được giá nếu cùng tên đó nhưng dữ liệu cấu hình đã thay đổi.

Tùy thiết kế, cần tham chiếu hoặc snapshot:

~~~text
pricingAlgorithmVersion
ruleSetVersion
catalogPriceVersion
promotionVersion
feePolicyVersion
taxPolicyVersion
roundingPolicyVersion
allocationPolicyVersion
featureConfigurationVersion
externalQuoteReference
~~~

Nếu quy tắc phụ thuộc giờ, vùng, phân khúc hoặc thử nghiệm sản phẩm, phải lưu ngữ cảnh quyết định cần thiết. Khi replay, không đọc lại hạng khách hàng hiện tại rồi coi nó đại diện cho thời điểm thanh toán trước đó.

Cũng cần định nghĩa mốc thời gian mà quy tắc có hiệu lực: lúc phát hành quote, lúc chấp nhận hay lúc thực hiện một bước khác. Một timestamp không có ý nghĩa nghiệp vụ rõ ràng chưa đủ.

### 3.3. Snapshot cần đủ dùng nhưng có giới hạn

Chỉ lưu ID tới một bản ghi có thể bị sửa sẽ làm mất khả năng tái dựng. Có thể dùng bản ghi bất biến, dữ liệu có lịch sử phiên bản hoặc snapshot tối thiểu đi kèm.

Không cần sao chép toàn bộ hồ sơ khách hàng. Nếu tính giá chỉ cần vùng giao hàng và nhóm quyền lợi, lưu các dữ kiện hoặc tham chiếu phù hợp, cùng bằng chứng xác minh. Tránh đưa địa chỉ đầy đủ, token truy cập hoặc dữ liệu thanh toán nhạy cảm vào trace chỉ để “có đủ thông tin”.

Một hash của dữ liệu không thay thế dữ liệu hoặc kho phiên bản cần thiết để replay. Hash chỉ giúp so sánh với một nội dung đã biết; nó không cho phép khôi phục nội dung bị mất.

## 4. Ví dụ đầy đủ: từ giá niêm yết đến tổng thanh toán

### 4.1. Chính sách minh họa

Giả sử các điều kiện được backend xác định:

~~~text
Dòng A: 2 đơn vị, giá 19,95 U mỗi đơn vị, đủ điều kiện giảm giá.
Dòng B: 1 đơn vị, giá 10,00 U, không thuộc nhóm khuyến mại.

Khuyến mại: giảm 10% trên tổng các dòng đủ điều kiện.
Thuế minh họa: 8% trên tổng giá hàng sau giảm.
Phí giao hàng: 5,00 U, không nằm trong cơ sở thuế của ví dụ.
Phí dịch vụ: 0,25 U, không nằm trong cơ sở thuế của ví dụ.

Giảm giá và thuế làm tròn HALF_UP về 0,01 U.
~~~

Đây là một nhóm thuế đơn giản, không có tài trợ hoặc đổi ngoại tệ. Sản phẩm có quy tắc khác phải lưu đúng thứ tự và cơ sở của nó.

### 4.2. Trace tính giá có ý nghĩa nghiệp vụ

| Bước | Phép tính | Giá trị trước làm tròn | Kết quả được dùng |
|---|---|---:|---:|
| Giá dòng A | `19.95 × 2` | `39.90` | `39.90` |
| Giá dòng B | `10.00 × 1` | `10.00` | `10.00` |
| Gross | `39.90 + 10.00` | `49.90` | `49.90` |
| Cơ sở khuyến mại | Chỉ dòng A đủ điều kiện | `39.90` | `39.90` |
| Discount | `39.90 × 0.10` | `3.990` | `3.99` |
| Net giá hàng | `49.90 - 3.99` | `45.91` | `45.91` |
| Tax | `45.91 × 0.08` | `3.6728` | `3.67` |
| Shipping | Giá phí đã xác nhận | `5.00` | `5.00` |
| Service fee | Chính sách phí cố định | `0.25` | `0.25` |
| Payable | `45.91 + 3.67 + 5.00 + 0.25` | `54.83` | `54.83` |

Audit còn cần ghi vì sao B không được giảm, chẳng hạn mã quyết định `PRODUCT_NOT_IN_PROMOTION_SCOPE` gắn với phiên bản khuyến mại. Chỉ ghi tổng discount `3.99` sẽ khó phát hiện trường hợp backend chọn sai tập dòng.

Ở bước thuế:

~~~text
rawTax = 3,6728 U
settledTax = 3,67 U
roundingDelta = -0,0028 U
roundingPoint = GROUP_TAX_TOTAL
~~~

`roundingDelta` là dữ liệu giải thích phép tính, có thể nhỏ hơn đơn vị hạch toán. Không mặc nhiên ghi nó thành một bút toán tiền độc lập.

### 4.3. Giữ phân bổ để phục vụ hoàn và đối soát

Trong ví dụ, toàn bộ giảm giá thuộc A. Nếu thuế tổng `3.67` được phân bổ theo net bằng phương pháp phần dư lớn nhất:

| Dòng | Gross | Discount | Net | Tax được phân bổ |
|---|---:|---:|---:|---:|
| A | `39.90` | `3.99` | `35.91` | `2.87` |
| B | `10.00` | `0.00` | `10.00` | `0.80` |
| Tổng | `49.90` | `3.99` | `45.91` | `3.67` |

Phí giao hàng và phí dịch vụ có chính sách hoàn riêng. Không suy ra rằng hoàn dòng A thì tự động hoàn toàn bộ các khoản phí của đơn.

Hồ sơ giá phải giữ quy tắc và kết quả phân bổ nếu những phần đó sẽ quyết định quyền hoàn. Tính lại bằng giá danh mục hoặc cấu hình hiện tại có thể thay đổi quyền lợi của giao dịch gốc.


## 5. Thiết kế hồ sơ audit có cấu trúc

### 5.1. Dùng trường có nghĩa thay cho một chuỗi log

Một hồ sơ calculation có thể có cấu trúc rút gọn như sau:

~~~json
{
  "schemaVersion": "1",
  "eventType": "PRICE_CALCULATION_COMPLETED",
  "calculationRunId": "calc-101",
  "pricingSnapshotId": "price-snapshot-101",
  "inputSnapshotId": "pricing-facts-101",
  "tenantId": "tenant-1",
  "orderId": "order-1",
  "orderVersion": 4,
  "actorId": "actor-1",
  "currency": "U",
  "ruleSetVersion": "pricing-rules-v7",
  "phase": "CALCULATED",
  "steps": [
    {
      "sequence": 70,
      "stepId": "GROUP_TAX",
      "ruleId": "TAX_AFTER_ORDER_DISCOUNT",
      "ruleVersion": "tax-rule-v3",
      "inputs": {
        "taxBase": "45.91",
        "taxRate": "0.08"
      },
      "rawResult": "3.6728",
      "settledResult": "3.67",
      "quantum": "0.01",
      "roundingMode": "HALF_UP",
      "roundingPoint": "GROUP_TAX_TOTAL"
    }
  ],
  "totals": {
    "gross": "49.90",
    "discount": "3.99",
    "net": "45.91",
    "tax": "3.67",
    "shipping": "5.00",
    "serviceFee": "0.25",
    "payable": "54.83"
  }
}
~~~

Mảng `steps` trong ví dụ chỉ trình bày bước thuế. Hồ sơ thực tế cần giữ những bước và quyết định cần thiết để giải thích toàn bộ tổng, hoặc tham chiếu đến dữ liệu bất biến tương ứng.

Số tiền dùng chuỗi thập phân để tránh đi qua biểu diễn số thực nhị phân ngoài ý muốn. Có thể dùng số nguyên đơn vị nhỏ nhất cho tiền đã chốt, nhưng dữ liệu tính toán trung gian vẫn cần biểu diễn đủ chính xác.

`phase = CALCULATED` cho biết đây là kết quả tính, chưa chứng minh quote đã được chấp nhận hoặc đã có thu tiền. Khi chấp nhận và khi thu tiền, ghi những sự kiện hoặc bản ghi liên kết mới. Không sửa sự kiện tính giá cũ để biến lịch sử thành một trạng thái khác.

### 5.2. Ghi cả quyết định áp dụng và không áp dụng

Đối với khuyến mại, một trace hữu ích có thể ghi:

~~~text
ruleId: PROMO_10_PERCENT_ELIGIBLE_PRODUCTS
ruleVersion: promo-v12
eligibleLineIds: [A]
excludedLines:
  B → PRODUCT_NOT_IN_PROMOTION_SCOPE
eligibleBase: 39.90 U
rawDiscount: 3.990 U
settledDiscount: 3.99 U
eligibilityEvidenceReference: entitlement-check-51
~~~

Căn cứ quyền lợi cần xuất phát từ server hoặc nguồn đã xác minh. Lưu `eligible=true` do client gửi không tạo ra bằng chứng hợp lệ.

Mã lý do nên ổn định và có cấu trúc. Chuỗi tự do như “đã giảm vì hợp lệ” khó tìm kiếm, khó kiểm thử và dễ che mất điều kiện thật sự.

Không đưa nguyên văn mọi giá trị client vào log không có giới hạn. Dữ liệu đó có thể quá dài, chứa ký tự điều khiển hoặc làm người đọc hiểu nhầm một nội dung do client viết là quyết định của server.

### 5.3. Duy trì quan hệ tham chiếu

Các liên kết quan trọng thường là:

~~~text
calculationRunId → inputSnapshotId + ruleSetVersion
pricingSnapshotId → calculationRunId + output bất biến
acceptanceId → pricingSnapshotId + actor + authority + approval
paymentIntentId → acceptanceId + expectedAmount + currency
providerTransactionId → paymentIntentId
ledgerTransactionId → paymentIntentId hoặc giao dịch tiền tương ứng
refundId → giao dịch gốc + phân bổ hoặc quyền hoàn gốc
~~~

Không phải mọi hệ thống cần đúng các bảng trên. Điều cần giữ là quan hệ đủ chặt để không ghép nhầm audit của đơn này với tiền của đơn khác.

Nếu dữ liệu ở nhiều dịch vụ, cần bảo vệ tính duy nhất và khả năng phát hiện liên kết thiếu. Một `correlationId` được truyền qua các log không tự thay thế các quan hệ nghiệp vụ có ràng buộc.

## 6. Java minh họa: tính một bước và trả lại bằng chứng

Đoạn mã sau minh họa cách một bước thuế trả lại cả số tiền và dữ liệu giải thích. Nó dùng mô hình quantum là lũy thừa của mười; ví dụ tiền U áp dụng scale hai.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Map;

record TrustedTaxFacts(
        String inputSnapshotId,
        String currency,
        BigDecimal taxableBase,
        BigDecimal taxRate) {}

record TaxRuleSpec(
        String ruleId,
        String version,
        int scale,
        RoundingMode roundingMode) {}

record CalculationStep(
        String stepId,
        String ruleId,
        String ruleVersion,
        String inputSnapshotId,
        Map<String, String> inputs,
        String rawResult,
        String settledResult,
        String quantum,
        String roundingMode,
        String roundingPoint) {}

record TaxComputation(
        BigDecimal amount,
        CalculationStep evidence) {}

TaxComputation calculateTax(
        TrustedTaxFacts facts,
        TaxRuleSpec rule) {

    // Facts và rule đã được server phân giải, kiểm tra và giới hạn.
    BigDecimal rawTax = facts.taxableBase().multiply(facts.taxRate());

    BigDecimal settledTax = rawTax.setScale(
            rule.scale(), rule.roundingMode());

    CalculationStep evidence = new CalculationStep(
            "GROUP_TAX",
            rule.ruleId(),
            rule.version(),
            facts.inputSnapshotId(),
            Map.of(
                    "currency", facts.currency(),
                    "taxBase", facts.taxableBase().toPlainString(),
                    "taxRate", facts.taxRate().toPlainString()),
            rawTax.toPlainString(),
            settledTax.toPlainString(),
            BigDecimal.ONE.movePointLeft(rule.scale()).toPlainString(),
            rule.roundingMode().name(),
            "GROUP_TAX_TOTAL");

    return new TaxComputation(settledTax, evidence);
}
~~~

Điều cần rút ra:

- Dữ liệu audit lấy từ cùng đầu vào và kết quả thực sự được dùng cho bước tính.
- Giá trị trước và sau làm tròn được phân biệt.
- Phiên bản rule và snapshot đầu vào được liên kết rõ.
- Tiền không bị chuyển qua `double` để ghi log.
- Bằng chứng là dữ liệu có cấu trúc, không chỉ là một thông điệp được ghép chuỗi.

Đây là phác thảo thành phần, chưa bao gồm xác thực, kiểm tra null, giới hạn dữ liệu, lưu trữ hoặc transaction. Tên `TrustedTaxFacts` chỉ mô tả hợp đồng; nó không tự biến object do client tạo thành dữ liệu đáng tin cậy. Tầng gọi phải thật sự phân giải dữ kiện từ nguồn có thẩm quyền.

Nếu quantum là `0.05`, phép `setScale` trong ví dụ không đủ. Engine phải dùng quy tắc quantum tương ứng và ghi đúng quy tắc đó trong evidence.

Một engine vừa tính sai vừa ghi lại đúng cách nó tính sai vẫn có trace nhất quán. Do đó, instrumentation không thay thế kiểm chứng độc lập về công thức, điều kiện áp dụng và nguồn đầu vào.

## 7. Lưu bằng chứng cùng quyết định nghiệp vụ

### 7.1. Các invariant tại lúc chấp nhận giá

Có thể đặt các điều kiện:

~~~text
Giá được chấp nhận tham chiếu một snapshot bất biến.
Snapshot khớp tenant, đơn hàng, phiên bản và loại tiền.
Actor có quyền xác nhận và có quyền tác động tiền tương ứng.
Phê duyệt khớp chính nội dung đang chấp nhận.
Điều kiện còn phải kiểm tra tại lúc chấp nhận được bảo vệ nhất quán.
Lệnh tiền dùng đúng số tiền và loại tiền của snapshot được chấp nhận.
Retry không tạo một lần chấp nhận hoặc thu tiền ngoài phạm vi.
Bằng chứng cốt lõi được lưu bền vững cùng quyết định.
~~~

Một coupon có giới hạn số lượt không thể chỉ kiểm tra khi tạo quote rồi tiêu thụ tùy ý sau đó. Nếu chính sách yêu cầu giữ lượt hoặc ngân sách, trạng thái giữ và tiêu thụ đó phải tham gia cơ chế đồng thời phù hợp.

Tương tự, kiểm tra quyền chi tiền trước transaction có thể không đủ nếu quyền được thu hồi trong khi request chờ. Các luồng thay đổi quyền và chấp nhận lệnh cần cùng tuân theo quy tắc hiệu lực đã định nghĩa.

### 7.2. Trình tự cục bộ tham khảo

~~~text
BEGIN
  Nhận quyền xử lý khóa idempotency trong đúng phạm vi.
  Nếu lệnh đã hoàn tất, kiểm tra quyền đọc rồi trả kết quả cũ.

  Khóa đơn, quote và dữ liệu quyền cần thiết theo thứ tự thống nhất.
  Kiểm tra tenant, order version, trạng thái, hiệu lực và quyền.
  Kiểm tra hoặc tiêu thụ phê duyệt, lượt khuyến mại, hạn mức cần thiết.

  Lưu quyết định chấp nhận tham chiếu pricing snapshot bất biến.
  Tạo payment intent chứa expectedAmount, currency và snapshot reference.
  Ghi bằng chứng audit cốt lõi của quyết định.
  Chuyển trạng thái đơn theo state machine.
  Ghi outbox nếu cần thực hiện bước bên ngoài.
  Lưu kết quả idempotency.
COMMIT
~~~

Ví dụ này tạo ý định thanh toán; nó chưa khẳng định tiền bên ngoài đã được thu. Nếu luồng chỉ chuyển tiền nội bộ trong cùng cơ sở dữ liệu, các cập nhật số dư và ledger tương ứng có thể tham gia cùng transaction cục bộ.

Không đặt lời gọi HTTP tới gateway vào trong hàm transaction rồi coi mọi tác động bên ngoài có thể rollback cùng cơ sở dữ liệu.

### 7.3. Nếu hệ thống audit gặp lỗi

Nên tách:

- **Bằng chứng cốt lõi:** dữ liệu cần để chứng minh giá và quyết định tiền tệ. Trong mô hình của bài, không chấp nhận quyết định mới nếu không thể lưu bền vững phần này.
- **Bản xuất sang hệ thống tìm kiếm hoặc dashboard:** có thể gửi bất đồng bộ qua outbox, với retry và đối soát.
- **Telemetry chẩn đoán:** phục vụ vận hành, có thể có cơ chế giảm tải riêng.

Nếu bằng chứng cốt lõi ghi lỗi trước commit, transaction phải không để lại quyết định tiền tệ một phần.

Nếu đã commit nhưng hệ thống tìm kiếm audit chưa nhận sự kiện, cần retry xuất dữ liệu. Không tạo lại payment intent hoặc thu tiền thêm để “khôi phục audit”.

Outbox hỗ trợ lưu bền vững ý định phát sự kiện. Bên nhận vẫn cần chống trùng theo định danh sự kiện hoặc nghiệp vụ và phát hiện bản ghi thiếu. Trạng thái index tìm kiếm không nên trở thành nguồn quyết định giá có thẩm quyền.

## 8. Replay, kiểm chứng chính sách và đối soát tiền là ba phép kiểm tra khác nhau

### 8.1. Replay lịch sử

Replay lấy snapshot đầu vào và phiên bản quy tắc lịch sử để tính lại kết quả. Mục tiêu là trả lời: “với những dữ kiện đã ghi, engine có tái tạo cùng đầu ra không?”

Một luồng tham khảo:

~~~text
Đọc snapshot và xác minh quan hệ, tính toàn vẹn cần thiết.
Nạp đúng phiên bản thuật toán và cấu hình.
Dùng thời gian hiệu lực, tỷ giá và quyền lợi đã được ghi nhận.
Chạy engine thuần tính toán.
So sánh từng thành phần, tổng và phân bổ.
Lưu kết quả kiểm chứng dưới một định danh mới.
~~~

Replay không được gọi capture, redeem coupon hoặc hoàn tiền thật. Nó cũng không nên phụ thuộc vào thời gian hiện tại, giá danh mục hiện tại hoặc cấu hình thử nghiệm hiện tại.

Nếu phiên bản mã cũ không còn sẵn, việc chỉ giữ một tên version không đủ để replay. Cần chính sách lưu trữ artifact hoặc cách tái dựng phù hợp với yêu cầu lịch sử của sản phẩm.

### 8.2. Kiểm chứng tính hợp lệ của quyết định

Replay ra cùng `54.83` chưa chứng minh giá hợp lệ nếu đầu vào đã dùng sai giá hoặc giảm giá cho người không đủ điều kiện.

Cần kiểm tra thêm:

- Price reference thực sự thuộc đúng sản phẩm và thời điểm hiệu lực.
- Coupon được phép trên các dòng và chủ thể đó.
- Dữ kiện khách hàng xuất phát từ nguồn đã xác minh.
- Phê duyệt hoặc override đúng quyền và đúng nội dung.
- Điều kiện đồng thời, ngân sách hoặc lượt dùng đã được bảo vệ khi chấp nhận.

Một boolean `eligible=true` không đủ thay cho bằng chứng về nguồn và quyết định. Với các điều kiện phụ thuộc lịch sử dùng quyền lợi, có thể cần sự kiện hoặc bản ghi giao dịch liên quan để kiểm chứng.

### 8.3. Đối soát số tiền thực tế

Đối soát liên kết:

~~~text
Accepted pricing snapshot
    → payment intent kỳ vọng
    → authorize/capture hoặc chuyển tiền thực tế
    → ledger
    → hoàn và điều chỉnh liên quan
~~~

Trong mô hình thu toàn phần của ví dụ, expected gross charge là `54.83 U`. Callback hợp lệ về chữ ký nhưng thông báo số tiền thấp hơn không được làm đơn tự động chuyển sang trạng thái đã thanh toán đủ.

Cần so sánh đúng loại đại lượng. Tiền provider trả ròng sau phí có thể khác gross đã thu; đó không tự động là lỗi tính giá. Gross charge, phí provider, khoản quyết toán ròng và quyền được hưởng của từng bên phải được đặt tên và đối soát theo mô hình riêng.

Với nhiều lần capture hoặc nhiều loại tiền, cần kiểm tra theo lịch thu và loại tiền tương ứng. Không cộng trực tiếp các đơn vị tiền khác nhau để tuyên bố đã đủ tiền.

Khi phát hiện sai lệch, ghi một finding hoặc nghiệp vụ điều chỉnh có tham chiếu. Không sửa snapshot gốc để nó trùng với số đã thu rồi làm mất dấu lỗi.


## 9. Điều chỉnh thủ công và thay đổi quy tắc cũng phải được audit

### 9.1. Không chỉ audit lần checkout

Một phép tính có thể đúng theo cấu hình nhưng cấu hình đã bị thay đổi trái quyền. Vì vậy, cần theo dõi cả nguồn tạo ra quy tắc:

~~~text
Ai tạo hoặc sửa bảng giá.
Ai thay điều kiện khuyến mại.
Thời điểm và phạm vi có hiệu lực.
Phiên bản trước và sau.
Lý do và phê duyệt nếu quy trình yêu cầu.
Artifact hoặc nội dung quy tắc được phát hành.
~~~

Quyền chỉnh giá, quyền phát hành quy tắc, quyền phê duyệt và quyền thu tiền không nên được suy ra từ một chuỗi `role=ADMIN` do client truyền.

Nếu sản phẩm yêu cầu tách người tạo và người phê duyệt, backend phải kiểm tra hai danh tính và ràng buộc phê duyệt với đúng nội dung, phiên bản, phạm vi và thời gian hiệu lực.

### 9.2. Override phải là một nghiệp vụ có tên

Không dùng endpoint kiểu “sửa total thành bất kỳ số nào” mà không giải thích thành phần thay đổi.

Trong ví dụ ở mục 4, có thể có một nghiệp vụ miễn phí giao hàng:

~~~text
Snapshot cũ:
  shipping = 5,00 U
  payable = 54,83 U

Override được phép: WAIVE_SHIPPING.
Snapshot mới:
  shipping = 0,00 U
  payable = 49,83 U
~~~

Do phí giao hàng không nằm trong cơ sở thuế của mô hình minh họa, thuế vẫn là `3.67 U`. Sản phẩm có thuế trên phí giao hàng phải tính và ghi bằng chứng theo quy tắc khác.

Bản ghi override cần có:

~~~text
overrideId
originalPricingSnapshotId
replacementPricingSnapshotId
operationType
requestedBy
approvedBy nếu cần
reasonCode
authorityReference
changedComponents
beforeAmount
afterAmount
effectiveAt
~~~

Không ghi đè snapshot cũ. Nếu đơn đã được thanh toán, việc miễn phí có thể cần một nghiệp vụ hoàn hoặc điều chỉnh tiền riêng; chỉ tạo snapshot mới không tự trả lại tiền.

Retry nghiệp vụ miễn phí phải tham chiếu cùng override hoặc cùng ý định hợp lệ. Không thực hiện phép “trừ thêm 5” mỗi lần nhận request.

### 9.3. Chính sách mới không sửa lịch sử

Một giá mới có thể được áp dụng cho quote mới. Giao dịch đã chấp nhận phải tuân theo cam kết lịch sử và quy trình thay đổi tương ứng.

Không đổi tên version cũ rồi thay nội dung bên trong. Phiên bản cần xác định được nội dung bất biến hoặc lịch sử đủ tin cậy để phân biệt các lần phát hành.

Nếu quy tắc cũ được phát hiện sai, ghi phát hiện, phạm vi ảnh hưởng và các nghiệp vụ sửa sai có quyền. Giữ mối liên hệ với bằng chứng gốc để có thể giải thích cả quyết định ban đầu lẫn cách khắc phục.

## 10. Bảo vệ bằng chứng audit

### 10.1. Append-only cần đi cùng kiểm soát truy cập

Có thể thiết kế hồ sơ audit theo cách chỉ thêm sự kiện hoặc bản ghi mới. Việc sửa sai được thể hiện bằng sự kiện đính chính hoặc supersede có tham chiếu, không xóa giá trị cũ.

Tuy nhiên, gọi một bảng là `audit_log` không khiến nó bất biến. Cần kiểm soát:

- Danh tính nào được ghi từng loại sự kiện.
- Có thể sửa hoặc xóa dữ liệu đã chấp nhận hay không.
- Ai được đọc, export hoặc replay dữ liệu theo tenant.
- Thao tác quản trị nào cũng cần dấu vết riêng.
- Bản sao, lưu trữ dài hạn và kiểm tra tính toàn vẹn được thực hiện thế nào.

Quyền xem audit có thể rộng hơn quyền người mua thông thường, nhưng vẫn phải là quyền được cấp rõ. Một trang hỗ trợ khách hàng không nên chỉ lọc dữ liệu trên giao diện rồi trả audit của mọi tenant xuống trình duyệt.

### 10.2. Hash giúp phát hiện thay đổi trong những điều kiện cụ thể

Một digest có thể giúp đối chiếu snapshot với nội dung đã biết. Khi dùng, cần quy định biểu diễn canonical:

~~~text
Phiên bản schema.
Tên và thứ tự trường theo quy tắc.
Biểu diễn tiền và loại tiền.
Thứ tự bước tính có ý nghĩa.
Quy tắc cho trường vắng mặt và trường null.
Phạm vi dữ liệu được bao phủ bởi digest.
~~~

Nếu dữ liệu `"1.0"` và `"1.00"` được coi là cùng giá trị, cần có quy tắc chuẩn hóa tương ứng trước khi tính digest. Nếu thứ tự mảng biểu diễn thứ tự áp dụng quy tắc, không được tùy tiện sắp xếp lại rồi làm mất ý nghĩa đó.

Một hash lưu ngay cạnh dữ liệu không tự ngăn người có quyền sửa cả hai. MAC, chữ ký hoặc lưu trữ tách quyền có thể tăng khả năng phát hiện và truy nguồn, tùy mô hình đe dọa và cách quản lý khóa.

Một hash chain cũng cần mốc tin cậy hoặc cơ chế kiểm chứng phù hợp; không nên coi nó tự chứng minh rằng lịch sử chưa từng bị viết lại.

Quan trọng hơn, tính toàn vẹn không chứng minh tính đúng đắn. Một bản ghi được ký vẫn có thể chứa giá sai nếu engine hoặc quy trình phê duyệt sai.

### 10.3. Giảm dữ liệu nhạy cảm và giới hạn đầu vào audit

Không ghi token, khóa bí mật hoặc dữ liệu thanh toán nhạy cảm không cần thiết vào calculation trace.

Thông tin định danh và điều kiện giá cũng có thể nhạy cảm. Nên phân tách các trường phục vụ tính toán với dữ liệu nhận dạng, áp dụng quyền truy cập và che dữ liệu phù hợp khi hiển thị hoặc export.

Hash thông tin cá nhân không mặc nhiên biến nó thành dữ liệu vô danh. Việc lưu trữ và quyền sử dụng vẫn cần được thiết kế theo dữ liệu thực tế.

Giới hạn kích thước, độ sâu và định dạng của các trường audit. Dùng dữ liệu có cấu trúc và phân biệt rõ trường do client đề nghị với quyết định do server đưa ra. Điều này giúp tránh log injection hoặc việc người đọc nhầm một nội dung client gửi thành sự kiện đã được hệ thống xác nhận.

## 11. Kiểm thử theo tình huống lạm dụng logic

Các ca dưới đây kiểm tra cả bằng chứng lẫn tác động tiền. Không chỉ assert rằng “có một dòng log”.

| Tình huống | Kết quả cần chứng minh |
|---|---|
| Tính đơn minh họa ở mục 4 | Gross `49.90`, discount `3.99`, net `45.91`, tax `3.67`, payable `54.83`; truy được nguồn và phiên bản |
| Client đổi đơn giá A thành một giá thấp hơn | Backend dùng giá có thẩm quyền; audit phân biệt đề nghị client nếu cần lưu |
| Client gửi `isVip=true` hoặc coupon ngoài quyền | Không tạo quyền giảm; giữ căn cứ từ nguồn xác minh |
| Dòng B bị đưa vào tập đủ điều kiện giảm | Kiểm thử phát hiện discount hoặc quyết định phạm vi sai |
| Chuyển làm tròn từ tổng nhóm vào từng dòng | Bộ dữ liệu sát nửa quantum phát hiện khác biệt và trace ghi đúng điểm |
| Thay số lượng sau khi quote đã được phê duyệt | Không thanh toán phiên bản mới bằng nội dung phê duyệt cũ ngoài chính sách |
| Actor lấy snapshot của người khác hoặc tenant khác | Bị từ chối; không đọc chi tiết hoặc tạo lệnh tiền trái quyền |
| Hai request cùng dùng một quote chỉ được thu một lần | Một tác động tiền tệ; audit tham chiếu cùng ý định hoặc kết quả theo chính sách |
| Cùng khóa idempotency nhưng đổi quote | Xung đột; không thay nội dung đã chấp nhận |
| Timeout sau commit rồi retry | Trả kết quả cũ; không tính hoặc thu tiền thêm |
| Ghi bằng chứng cốt lõi lỗi trước commit | Không để lại quyết định tiền tệ hoặc tiêu thụ quyền lợi một phần |
| Hệ thống tìm kiếm audit tạm ngừng | Bằng chứng gốc vẫn bền vững; outbox có thể được gửi lại mà không thu thêm |
| Một sự kiện export được giao hai lần | Consumer không tạo hai bản ghi nghiệp vụ khác nhau cho cùng sự kiện |
| Catalog hiện tại thay giá sau giao dịch | Replay lịch sử vẫn dùng đúng giá và cấu hình đã lưu |
| Không tìm được phiên bản rule lịch sử | Báo không thể kiểm chứng đầy đủ; không tự thay bằng rule hiện tại |
| Snapshot đầu vào bị sửa | Cơ chế kiểm chứng được thiết kế phát hiện sai lệch theo mốc tin cậy của nó |
| Người dùng chỉ có quyền xem đơn nhưng gọi override | Bị từ chối; không đổi giá hoặc miễn phí |
| Override miễn shipping `5.00` được phép | Snapshot mới là `49.83`; snapshot cũ và lý do vẫn tồn tại |
| Retry cùng override miễn phí | Không giảm thêm `5.00` lần nữa |
| Callback hợp lệ về nguồn nhưng sai amount hoặc currency | Không xác nhận đã thanh toán đủ; có trạng thái hoặc finding để xử lý |
| Provider trả số tiền quyết toán ròng khác gross charge | Đối soát đúng thành phần phí, không so nhầm hai đại lượng |
| Hoàn một phần sau khi policy giá đã đổi | Dùng quyền lợi và phân bổ gốc theo chính sách lịch sử |
| Replay một giao dịch | Không gọi thu, hoàn, redeem hoặc tạo tác động tiền thật |
| Client chèn chuỗi giả mạo sự kiện vào trường lý do | Không làm người đọc hoặc hệ thống hiểu đó là quyết định server |
| Người đọc audit không có quyền tenant | Không truy cập hoặc export được bằng ID đoán được |

Với các ca về tính toán, expected nên được xác định độc lập từ chính sách và dữ liệu nhỏ có thể kiểm tra chính xác. Không tạo expected bằng cách gọi lại chính engine đang được kiểm thử.

Với các ca đồng thời, cần điều khiển thời điểm các transaction gặp nhau bằng barrier hoặc cơ chế phù hợp. Sau khi cả hai kết thúc, đọc lại snapshot được chấp nhận, lệnh tiền, ngân sách đã dùng và ledger. Hai response có cùng số tiền chưa đủ chứng minh chỉ có một lần thu.

Với fault injection, phân biệt lỗi trước commit và lỗi sau commit. Bằng chứng từ chối có thể tồn tại, nhưng dữ liệu tiền và quyền lợi không được ở trạng thái dở dang ngoài state machine đã định nghĩa.

## 12. Vận hành và sử dụng kết quả audit

### 12.1. Theo dõi chất lượng bằng chứng

Một số tín hiệu hữu ích:

~~~text
Quyết định tiền tệ không có pricing snapshot hợp lệ.
Snapshot thiếu rule version hoặc input reference cần thiết.
Tổng tiền lệch với các thành phần.
Tổng phân bổ lệch với tổng đã chốt.
Replay không tái tạo được kết quả.
Lệnh tiền hoặc ledger không khớp giá đã chấp nhận.
Override thiếu quyền hoặc thiếu phê duyệt theo chính sách.
Outbox audit bị trễ hoặc thiếu liên kết.
Lỗi truy cập audit ngoài tenant.
~~~

Các chỉ số tổng hợp có thể dùng để phát hiện xu hướng, nhưng bằng chứng của quyết định tiền tệ đã chấp nhận không nên bị lấy mẫu mất chỉ vì cần giảm dung lượng telemetry.

Thời hạn lưu bằng chứng, phiên bản quy tắc và khả năng replay phải thống nhất với nhu cầu hoàn, tranh chấp và kiểm tra của sản phẩm. Không xóa dữ liệu đầu vào trong khi vẫn tuyên bố có thể tái dựng đầy đủ giao dịch.

### 12.2. Giữ quan hệ nhân quả thay vì chỉ sắp theo thời gian

Đồng hồ giữa các dịch vụ có thể lệch và sự kiện có thể đến không theo thứ tự. Nên dùng version đối tượng, sequence trong phạm vi phù hợp và các quan hệ tham chiếu để xác định sự kiện nào dựa trên sự kiện nào.

Một chuỗi bằng chứng có thể là:

~~~mermaid
flowchart LR
    F[Snapshot dữ kiện tin cậy] --> C[Calculation run]
    R[Phiên bản quy tắc] --> C
    C --> Q[Pricing snapshot bất biến]
    Q --> A[Quyết định chấp nhận]
    A --> P[Payment intent]
    P --> T[Giao dịch tiền và ledger]
    T --> U[Hoàn hoặc điều chỉnh]
    Q --> U
~~~

Mũi tên biểu diễn quan hệ nghiệp vụ, không chỉ là các dòng log tình cờ có cùng request ID.

### 12.3. Dùng finding để sửa quy tắc và kiểm thử

Khi tìm thấy sai lệch:

1. Xác định đang sai phép tính, dữ kiện đầu vào, quyền áp dụng hay đối soát tiền.
2. Giữ snapshot và bằng chứng gốc để giải thích quyết định lịch sử.
3. Ghi finding có tham chiếu đến các giao dịch chịu ảnh hưởng.
4. Thực hiện điều chỉnh bằng nghiệp vụ có quyền và chống trùng nếu cần.
5. Bổ sung một tình huống regression bằng dữ liệu tổng hợp, không chứa thông tin khách hàng thật.

Một báo cáo audit hữu ích có thể nói rõ: **giá nào được tính, bằng dữ kiện và quy tắc nào, ai được phép chấp nhận, số tiền nào đã thực sự được thu, và phần nào không khớp**. Khi các câu trả lời có quan hệ bền vững, hệ thống có thể phát hiện sửa giá, lạm dụng khuyến mại, bỏ qua phê duyệt và thực hiện trùng mà không phải suy đoán từ một tổng tiền hoặc vài dòng log rời rạc.
