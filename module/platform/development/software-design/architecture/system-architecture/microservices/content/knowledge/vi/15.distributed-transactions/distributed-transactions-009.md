# Đối soát, sửa sai và xử lý thủ công khi tự động phục hồi thất bại

> **Chủ đề:** Software Design Architecture System Architecture Microservices  
> **Nhánh kiến thức:** Giao dịch phân tán  
> **Trọng tâm:** Thiết kế cách phát hiện và khôi phục những sai lệch nghiệp vụ khi một giao dịch trải qua nhiều dịch vụ, message, cơ sở dữ liệu hoặc đối tác; đặc biệt là lúc retry, compensation, saga hoặc cơ chế phục hồi tự động không thể đưa hệ thống về trạng thái đúng.

## 1. Bài toán cốt lõi: hệ thống phân tán không phải lúc nào cũng tự sửa xong

Giả sử khách hàng đặt một đơn hàng. Quy trình liên quan đến:

1. Ordering tạo đơn và ghi trạng thái ban đầu.
2. Inventory giữ hàng.
3. Payments thu tiền hoặc xác nhận thanh toán.
4. Fulfillment tạo vận đơn.
5. Notifications gửi xác nhận.

Mỗi dịch vụ có dữ liệu, giao dịch database và vòng đời xử lý riêng. Một sự cố xảy ra giữa các bước có thể để lại những trạng thái không đồng nhất:

- Payments đã thu tiền, Ordering vẫn báo “Chưa thanh toán”.
- Inventory đã giữ hàng, đơn bị hủy nhưng lệnh trả tồn không thành công.
- Đối tác vận chuyển đã tạo vận đơn nhưng phản hồi HTTP bị mất; Fulfillment gửi lại và có hai vận đơn.
- Sự kiện PaymentCaptured được phát hai lần; consumer chưa idempotent tạo hai yêu cầu xuất hàng.
- Saga phát lệnh hoàn tiền nhưng bên thanh toán chưa xác nhận, trong khi UI đã hiển thị “Đã hoàn tiền”.
- Một giao dịch đã qua thời điểm được phép hủy; hành động bù giờ không còn tương đương việc đảo ngược ban đầu.

Hệ thống cần retry, timeout, idempotency, outbox và saga để phục hồi thông thường. Nhưng không có cơ chế tự động nào có thể xử lý mọi loại thất bại. Có lỗi **mơ hồ về kết quả**, có lỗi **dữ liệu mâu thuẫn**, có lỗi cần **quyết định nghiệp vụ** hoặc **phê duyệt của người có trách nhiệm**.

Vì vậy, hệ thống production cần cả ba năng lực bổ sung cho nhau:

- **Đối soát (reconciliation):** so sánh những bằng chứng từ các nguồn có thẩm quyền để phát hiện thiếu, trùng, lệch tiền, lệch trạng thái, xử lý chưa kết thúc hoặc dữ liệu đến trễ.
- **Sửa sai (remediation/correction):** chọn và thực thi hành động được phép để đưa nghiệp vụ về trạng thái nhất quán/được chấp nhận, có thể bằng lệnh bù, điều chỉnh, tạo bổ sung hoặc điều tra.
- **Xử lý thủ công (manual intervention):** chuyển ca cho người vận hành/nghiệp vụ có quyền, kèm toàn bộ bối cảnh, bằng chứng, công cụ thao tác an toàn, phân quyền, audit và xác nhận kết quả.

Mục tiêu không phải làm cho mọi service có cùng một giá trị status ngay tức thì; mục tiêu là **không để tiền, quyền lợi, hàng hóa, chứng từ hoặc cam kết khách hàng rơi vào trạng thái không có ai chịu trách nhiệm**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt lỗi kỹ thuật có thể retry, lỗi nghiệp vụ cần bù, và trạng thái không rõ kết quả phải đối soát trước.
2. Giải thích vì sao saga compensation không tương đương rollback ACID toàn hệ thống.
3. Thiết kế bộ phát hiện sai lệch dựa trên source of truth, transaction IDs, trạng thái và bằng chứng bên ngoài.
4. Mô hình hóa một hồ sơ xử lý ngoại lệ có owner, SLA, quyết định, bằng chứng, lịch sử và trạng thái.
5. Thiết kế cơ chế sửa sai idempotent, an toàn trước message duplicate, callback trễ và operator race.
6. Xây dựng runbook/manual operation có kiểm soát quyền, phê duyệt theo rủi ro và audit trail.
7. Định nghĩa metric, SLO, cảnh báo và bài kiểm thử cho năng lực đối soát–phục hồi–xử lý thủ công.

## 2. Bối cảnh giao dịch phân tán

### 2.1. Vì sao “commit ở từng service” không đủ?

Trong một database transaction, nhiều thay đổi có thể commit hoặc rollback cùng nhau. Trong kiến trúc phân tán, mỗi dịch vụ thường có transaction cục bộ:

~~~text
[Ordering DB]    [Inventory DB]     [Payments DB]
 COMMIT order     COMMIT reserve     COMMIT capture
      |                |                  |
      +----------------+------------------+
              Không có rollback ACID
              tự động xuyên tất cả
~~~

Khi ba service cùng commit thành công, giao dịch nghiệp vụ có thể hoàn tất. Khi chỉ một hoặc hai service commit, hệ thống cần trạng thái trung gian, retry, bù trừ và/hoặc đối soát.

Các dịch vụ ngoài tổ chức càng khó: payment provider, hãng vận chuyển, hệ thống ngân hàng, email gateway, cơ quan cấp chứng từ... Có thể không cung cấp giao dịch chung, có rate limit, thay đổi API hoặc phản hồi không ổn định.

### 2.2. Saga và compensation

**Saga** chia một quy trình thành những transaction cục bộ, với các hành động bù được thiết kế theo nghiệp vụ.

Ví dụ:

~~~text
ReserveStock --> CapturePayment --> CreateShipment
    |                  |                 |
  releaseStock       refundPayment      cancelShipment
~~~

Nếu CreateShipment thất bại sau CapturePayment, hệ thống có thể thử hoàn tiền và trả hàng. Tuy nhiên:

- Hoàn tiền là **giao dịch mới**, không xóa lịch sử đã thu tiền.
- Đơn đã được vận chuyển thật có thể không thể “rollback” như một record.
- Lệnh compensation cũng có thể timeout hoặc thất bại.
- Chính sách refund, phí, tỷ giá, thời gian cut-off có thể làm compensation không tương đương hoàn toàn với hành động gốc.
- Một đối tác có thể không hỗ trợ hủy, hoặc phải xử lý bằng yêu cầu thủ công.

Saga giúp điều phối phục hồi, nhưng **không bảo đảm luôn tự phục hồi thành công**.

### 2.3. Trạng thái “không rõ kết quả”

Một caller gửi CapturePayment. Provider thực sự thu tiền, nhưng mạng mất kết nối trước khi trả response. Caller chỉ nhìn thấy timeout.

~~~text
Payments service --> Provider: capture 500.000 VND
                         |
                         +-- tiền được capture thành công
                         |
                    response bị mất
                         |
Payments service <-- timeout (không biết kết quả)
~~~

**Timeout không chứng minh thao tác chưa xảy ra.** Retry ngay bằng một idempotency key khác có thể thu tiền lần hai.

Cách xử lý hợp lý là tra cứu trạng thái theo merchant reference, provider transaction ID hoặc idempotency key đã dùng; nếu provider còn bất định, lưu trạng thái UNKNOWN/PENDING_RECONCILIATION và chờ webhook/statement/đối soát định kỳ. Chỉ phát lệnh mới khi có đủ bằng chứng và chính sách cho phép.

## 3. Các loại sai lệch cần phát hiện

| Loại | Ví dụ | Điều cần kiểm chứng |
| --- | --- | --- |
| **Missing event** | Payment đã được thu nhưng không có PaymentCaptured trong Ordering | Có bản ghi nguồn? Outbox/consumer tiến đến đâu? |
| **Duplicate processing** | Một order có hai vận đơn cho cùng lần gửi | Hai side effect thật hay hai callback của một lần? |
| **State divergence** | Ordering CANCELLED, Shipping IN_TRANSIT | Trạng thái nào là sự thật ở mỗi miền? Có thể bù không? |
| **Amount mismatch** | Payments capture 490.000, Order amount 500.000 | Thuế, coupon, phí, currency, rounding, partial capture? |
| **Orphaned resource** | Giữ kho tồn tại nhưng order không còn hiệu lực | Reservation còn hợp lệ, cần release hay expire? |
| **Stuck workflow** | Saga đang COMPENSATING hơn 24 giờ | Worker chết, callback trễ, lỗi provider hay dữ liệu bất hợp lệ? |
| **Unknown external outcome** | Gửi lệnh refund timeout | Refund đã tạo? Có transaction ID hay bank statement? |
| **Missed deadline** | Hết thời hạn giữ hàng, nhưng chưa hủy | Timer/job scheduler có chạy? Tác động đến tồn kho? |
| **Projection lag** | Báo cáo thanh toán kém nguồn một giờ | Read model chậm hay mất event? |
| **Cross-version conflict** | Callback cũ cập nhật lại trạng thái đã hoàn tất | Version/sequence và trạng thái chuyển tiếp có hợp lệ? |
| **Authorization mismatch** | Quyền đã thu hồi nhưng projection chưa cập nhật | Nguồn quyền hiện tại là gì? Có rủi ro truy cập? |
| **Partial business completion** | Khách đã thu tiền nhưng chưa được cấp dịch vụ | Cam kết phải cung cấp hay hoàn tiền? Ai quyết định? |

Sai lệch có thể là **lỗi thật** hoặc **khác biệt tạm thời hợp lệ** do eventual consistency. Bộ đối soát phải biết khoảng trễ được phép và không tự sửa những thứ đang đúng theo workflow.

## 4. Định nghĩa “đúng” trước khi tự động sửa

Một bộ đối soát không thể chỉ hỏi “hai cột status có bằng nhau không?”. Mỗi bounded context có định nghĩa và quyền sở hữu riêng.

Ví dụ:

- **Payments** là nguồn có thẩm quyền về giao dịch capture/refund đã được ghi nhận qua provider và ledger nội bộ.
- **Inventory** là nguồn có thẩm quyền về reservation, movement và available stock.
- **Ordering** là nguồn có thẩm quyền về vòng đời đơn và trạng thái chấp nhận/hủy nghiệp vụ.
- **Shipping** là nguồn có thẩm quyền về vận đơn, giao nhận và các sự kiện từ carrier.
- **Accounting/Ledger** có thể là nguồn có thẩm quyền về số dư hạch toán, không thể suy diễn tùy ý từ order status.

Một trạng thái ở Ordering có thể là **projection** được cập nhật từ Payments, không thể thay cho bằng chứng thanh toán tại provider.

### 4.1. Phân biệt source of truth và evidence source

Một nguồn có thẩm quyền cho một loại sự thật, nhưng để đối soát vẫn phải so sánh bằng chứng:

- Transaction log nội bộ.
- Provider API/webhook/báo cáo đối soát.
- Bank statement hoặc settlement file.
- Outbox/inbox event IDs.
- Workflow history.
- Audit log của operator.
- Customer-facing artifact như hóa đơn hoặc shipping label.

Sự khác nhau giữa nguồn nội bộ và nguồn ngoài không tự quyết định bên nào đúng. Đôi khi cần quy tắc precedence: ví dụ capture đã được provider xác nhận và sao kê settlement chứng minh tiền chuyển, nhưng bản ghi Payments nội bộ bị thiếu. Quy tắc này phải được domain owner và bộ phận liên quan phê duyệt.

### 4.2. Invariant có thể kiểm tra

Một số ví dụ, tùy nghiệp vụ:

1. Mỗi accepted order có một kết quả thanh toán cuối cùng được biết trong deadline đã cam kết, hoặc một hồ sơ ngoại lệ có owner.
2. Không có hai lần charge cho **cùng một ý định thanh toán**, trừ trường hợp nghiệp vụ hỗ trợ nhiều capture với ID riêng.
3. Một reservation đã hết hạn không tiếp tục làm giảm available inventory vô thời hạn.
4. Mọi refund đã hứa với khách phải có trạng thái tracking đến khi provider/ledger xác nhận.
5. Shipment chỉ được tạo theo điều kiện nghiệp vụ được phê duyệt.
6. Mọi điều chỉnh tiền có ledger entry và audit liên kết; không âm thầm sửa số dư hiện tại.

Invariant nên có **định danh và định nghĩa kiểm chứng**, không chỉ là phát biểu “mọi service phải đồng bộ”. Các trường hợp “partial capture”, “split shipment”, “partial refund” hoặc “backorder” có thể hợp lệ và phải được đưa vào quy tắc.

## 5. Khi nào retry, khi nào đối soát, khi nào xử lý thủ công?

### 5.1. Ba hướng xử lý khác nhau

**Retry**: thực hiện lại một thao tác có khả năng thành công sau lỗi tạm thời, an toàn trước trùng, còn trong deadline/retry budget.

**Reconciliation**: đọc bằng chứng và tính trạng thái cần có trước khi ra hành động. Thường cần khi kết quả trước đó **không rõ**, hoặc dữ liệu giữa các nguồn **mâu thuẫn**.

**Manual intervention**: cần con người quyết định hoặc thực thi vì tự động không đủ bằng chứng, quá rủi ro, vượt ngưỡng số lần thử, quá thời hạn hoặc thiếu capability bù an toàn.

| Tình huống | Đường ưu tiên | Lý do |
| --- | --- | --- |
| HTTP 503 trước khi command được chấp nhận; idempotency bảo vệ tốt | Retry có backoff | Lỗi tạm thời, đã biết cách chống trùng |
| Provider capture timeout, không rõ tiền đã thu hay chưa | Query status/đối soát | Retry mù có thể thu tiền lần hai |
| Compensating release stock lỗi do DB down 2 phút | Retry giới hạn, theo dõi | Có thể khôi phục tự động |
| Release stock thất bại liên tục do dữ liệu đã bị điều chỉnh thủ công | Mở exception case | Cần phán đoán nghiệp vụ |
| Refund được yêu cầu nhưng provider báo từ chối vĩnh viễn | Manual review | Có thể cần kênh hoàn khác hoặc liên hệ khách |
| Read model lệch nhưng event log đầy đủ và có thể replay | Rebuild/replay an toàn | Sửa projection, không tạo side effect thật |
| Đơn hàng đã giao và khách đã nhận, nhưng saga muốn cancel shipment | Manual resolution | Không thể đảo ngược vật lý bằng một API |
| Khoản tiền có thể liên quan gian lận | Escalate theo quy trình rủi ro | Không tự động chuyển tiền tùy tiện |

### 5.2. Ma trận quyết định

~~~text
Phát hiện bất thường
      |
      v
Có phải độ trễ tạm thời trong cửa sổ cho phép?
  | Có --> Ghi nhận và theo dõi, không sửa sớm
  | Không
  v
Có bằng chứng đủ để biết kết quả cuối?
  | Không --> Query provider/ledger/status
  |             |
  |             +-- Vẫn mơ hồ --> PENDING_RECONCILIATION
  |                                      |
  |                                deadline/owner
  v
Có phương án sửa tự động an toàn và idempotent?
  | Có --> Thực thi theo policy, xác minh kết quả
  |                         |
  |                         +-- lỗi kéo dài --> Manual case
  | Không
  v
Hồ sơ xử lý thủ công + phân quyền + SLA + audit
      |
      v
Quyết định --> Lệnh sửa được kiểm soát --> Đối soát lại
~~~

Không nên biến một state machine xử lý tiền thành “lỗi bất kỳ thì thử lại năm lần rồi đánh dấu thành công”. Mỗi nhánh phải gắn với bằng chứng và điều kiện kết thúc.

## 6. Đối soát chủ động và thụ động

### 6.1. Đối soát dựa trên sự kiện

Sau PaymentCaptured, một consumer cập nhật Order payment status và kiểm tra bất biến liên quan. Nếu phát hiện khác biệt (đơn không tồn tại, currency sai, version cũ), nó mở một exception case thay vì lặng lẽ bỏ qua.

Ưu điểm: phát hiện tương đối nhanh, có bối cảnh event. Hạn chế: khi event bị mất hoàn toàn, chỉ dựa trên consumer sẽ không phát hiện được.

### 6.2. Đối soát định kỳ

Một scheduled reconciliation job quét các giao dịch cần kiểm tra:

- Payment PENDING lâu hơn ngưỡng.
- Refund REQUESTED nhưng chưa có final result.
- Reservation hết hạn nhưng chưa RELEASED.
- Shipment creation không có provider reference.
- Saga không có bước tiến triển sau deadline.
- Order và Payment settlement mismatch.
- Event/outbox backlog quá tuổi cho phép.

Cần phân vùng, pagination, checkpoint và giới hạn tải để job đối soát không làm database sản xuất quá tải.

### 6.3. Đối soát theo yêu cầu

Một nhân viên hỗ trợ có thể yêu cầu “Kiểm tra lại thanh toán” cho một order cụ thể. Hành động này nên tạo một **reconciliation job có định danh**, đi qua auth, quota, audit, chống trùng và logic tương tự đối soát định kỳ.

Không nên cung cấp nút “Gọi lại webhook” cho mọi nhân viên như một shortcut: có thể làm trùng side effect nếu consumer không được thiết kế đúng.

### 6.4. Đối soát theo batch từ đối tác

Ngân hàng/payment provider có thể cung cấp settlement file cuối ngày. Có thể cần:

1. Nhận file an toàn, xác thực nguồn và checksum/signature.
2. Parse schema/version, currency, amount, fee và thời điểm.
3. Chuẩn hóa reference/transaction ID.
4. So sánh tập nội bộ với tập bên ngoài.
5. Ghi mismatch theo loại: missing internal, missing provider, amount mismatch, duplicate, late reversal, fee difference.
6. Tạo case và đề xuất action; tự động sửa chỉ với policy cho phép.
7. Lưu báo cáo, audit và checkpoint để chạy lại an toàn.

Với tiền, cần tính theo đơn vị tiền tệ và độ chính xác đã định nghĩa; không dùng floating point nhị phân để kết luận các khoản tiền bằng nhau.

## 7. Thiết kế dữ liệu cho bộ đối soát

### 7.1. Các định danh không thể thiếu

| Trường | Vai trò |
| --- | --- |
| businessOperationId | Định danh ý định nghiệp vụ xuyên nhiều bước |
| orderId / bookingId / paymentId | Định danh thực thể miền |
| providerReference | Khóa tra cứu ở hệ ngoài |
| idempotencyKey | Chống tạo lệnh có cùng ý định nhiều lần |
| eventId | Nhận biết cùng một sự kiện được giao lại |
| sagaId / workflowId | Nối các bước và compensation |
| attemptId | Phân biệt một lần thử thực thi |
| reconciliationCaseId | Định danh hồ sơ điều tra/sửa sai |
| correlationId / traceId | Kết nối log, trace và case |

Một đơn hàng có thể có nhiều payment attempts, partial captures và partial refunds. Không dùng orderId như khóa duy nhất để tuyên bố “đơn chỉ có thể có một giao dịch”. Cần định nghĩa identity theo **ý định và hành động thật**.

### 7.2. Mẫu dữ liệu một reconciliation case

~~~json
{
  "caseId": "rc-82017",
  "caseType": "PAYMENT_CAPTURE_UNKNOWN",
  "priority": "HIGH",
  "businessOperationId": "checkout-742",
  "entityRefs": {
    "orderId": "ord-742",
    "paymentId": "pay-391",
    "providerReference": "merchant-req-814"
  },
  "detectedAt": "2026-11-11T09:00:00Z",
  "lastCheckedAt": "2026-11-11T09:03:00Z",
  "status": "AWAITING_EVIDENCE",
  "assignedTeam": "payments-operations",
  "attemptCount": 3,
  "evidence": [
    {
      "source": "internal_payment",
      "finding": "CAPTURE_REQUEST_SENT"
    },
    {
      "source": "provider_status",
      "finding": "UNKNOWN"
    }
  ],
  "deadline": "2026-11-11T10:00:00Z",
  "proposedAction": "HOLD_AND_RECHECK",
  "resolution": null
}
~~~

Đây là model minh họa, không phải schema bắt buộc. Bằng chứng phải có quyền truy cập thích hợp; không lưu raw card data, secrets, mã OTP hoặc thông tin cá nhân không cần thiết.

### 7.3. Dữ liệu phải được chuẩn hóa đủ để so sánh

Đối soát tiền cần hiểu:

- Currency, amount minor units/decimal precision.
- Tỷ giá và effective time nếu có quy đổi.
- Phí, thuế, surcharge, partial payment và fee reversal.
- Kiểu transaction: authorization, capture, settlement, refund, chargeback.
- Provider transaction IDs và merchant reference.
- Event time, processing time và accounting date.
- Timezone, cut-off và business day.

Nếu một bên ghi 1.000.000 VND đã thu và bên kia ghi 995.000 VND chuyển ròng sau phí 5.000 VND, đó có thể là khác nhau hợp lệ về **ngữ nghĩa**. Bộ đối soát phải so sánh đúng loại giá trị.

### 7.4. So sánh theo version và thời điểm

Một Order projection cập nhật chậm 5 giây chưa chắc sai. Quy tắc có thể yêu cầu chờ hết một **settling window** rồi mới mở case. Với giao dịch tài chính, một số bằng chứng hoàn tất chỉ xuất hiện sau kỳ settlement; cần phân biệt trạng thái tức thời và trạng thái đã đối soát cuối ngày.

Đừng dùng timestamp giữa các service làm một đồng hồ tuyệt đối nếu clock skew và event delay chưa được kiểm soát. Ưu tiên version/sequence theo aggregate khi cần bảo vệ ordering.

## 8. Sửa sai là một giao dịch nghiệp vụ mới, không phải sửa bảng cho khớp

Có hai nhóm hành động sửa sai:

1. **Sửa trạng thái biểu diễn:** cập nhật read model, phát lại integration event bị mất, dựng lại projection, sửa metadata không mang side effect.
2. **Sửa tác dụng nghiệp vụ:** hoàn tiền, trả tồn, hủy vận đơn, cấp bù quyền lợi, phát hành chứng từ điều chỉnh, tạo ledger adjustment.

Nhóm thứ hai phải có hợp đồng command, permission, idempotency, evidence và audit. Không tự SQL UPDATE một trạng thái được phân phối nếu hành động đó làm giả lịch sử hoặc bỏ qua domain rules.

### 8.1. Ví dụ: thanh toán đã thành công, Order projection chưa cập nhật

Nếu provider và Payments ledger xác nhận capture hợp lệ, nhưng Ordering vẫn PENDING:

- Xác minh orderId, paymentId, amount và currency đúng.
- Xem event PaymentCaptured có được phát trong outbox không.
- Nếu event đã có nhưng projection chưa xử lý, có thể replay event vào consumer idempotent hoặc repair projection có kiểm soát.
- Nếu outbox thiếu do bug, dùng một **recovery command/event** do Payments owner phát sau khi xác nhận sự thật.
- Đối soát lại Order và Payments.
- Lưu audit, root cause và biện pháp ngăn lặp.

Không tự tạo thêm lệnh capture chỉ để “làm cho Ordering thấy thanh toán”.

### 8.2. Ví dụ: tồn kho bị giữ cho đơn đã hủy

Inventory là nguồn có thẩm quyền cho reservation. Reconciliation xác minh order đã CANCELLED và reservation vẫn ACTIVE vượt grace period:

- Kiểm tra reservation có được release/cancel trước đó chưa.
- Nếu release idempotent và còn hợp lệ, gửi ReleaseReservation với unique operationId.
- Nếu Inventory báo reservation đã CONSUMED do giao hàng, không cố force release; cần điều tra.
- Nếu release đã chạy nhưng projection chậm, chờ/repair projection.
- Xác nhận sau sửa, ghi case RESOLVED khi trạng thái nghiệp vụ thực sự hợp lệ.

### 8.3. Ví dụ: bên vận chuyển đã tạo vận đơn nhưng callback mất

Tạo lại vận đơn ngay có thể gây trùng. Trước hết query theo **merchant shipment request ID** hoặc provider reference. Nếu có, ghi nhận vận đơn đã tồn tại vào Fulfillment. Nếu provider trả “không tìm thấy” nhưng có độ trễ indexing, cần chờ trong cửa sổ xác định trước khi quyết định retry. Nếu không có API tra cứu tin cậy, chuyển case cho nhân viên vận hành/đối tác.

### 8.4. Khi điều chỉnh tiền, dùng bút toán

Trong một ledger có tính kiểm toán, không nên xóa/ghi đè entry đã phát sinh để làm cân số dư. Có thể cần bút toán điều chỉnh hoặc giao dịch bù có tham chiếu tới giao dịch gốc và lý do, theo nghiệp vụ/kế toán được phê duyệt.

Hệ thống phải phân biệt “UI status đã sửa” với “tiền thực tế đã được hoàn/ghi nhận”. Việc đóng case chỉ hợp lệ khi những điều kiện cuối được xác minh.

## 9. State machine cho việc phục hồi và xử lý thủ công

Một state machine tham khảo:

~~~text
DETECTED
   |
   v
VALIDATING_EVIDENCE
   |
   +--> WAITING_FOR_CONSISTENCY_WINDOW ----+
   |                                      |
   v                                      v
RECONCILING <----------------------------+
   |
   +--> NO_MISMATCH --> CLOSED_NO_ACTION
   |
   +--> AUTO_REMEDIATION_APPROVED
   |                  |
   |                  v
   |             REMEDIATING
   |               |      |
   |            success  unresolved / repeated failure
   |               |      |
   |               v      v
   |            VERIFYING  NEEDS_MANUAL_REVIEW
   |               |           |
   |               v           v
   |            RESOLVED   ASSIGNED / INVESTIGATING
   |                           |
   |                  decision + approval
   |                           |
   |                     MANUAL_ACTION
   |                           |
   +------------------------> VERIFYING
                                |
                          RESOLVED / ESCALATED
~~~

Các trạng thái có thể được tinh chỉnh, nhưng cần bảo đảm:

- Không đóng case khi thao tác đã **gửi** mà kết quả còn UNKNOWN.
- Không thực thi hai remediation trái chiều cùng lúc.
- Một case có owner và deadline khi chờ bằng chứng.
- Việc bỏ qua/no-action phải có lý do và bằng chứng.
- Trạng thái terminal có nghĩa rõ, không che unresolved side effect.
- Có lịch sử transition, người/automation thực hiện, thời gian và version.

### 9.1. Case lifecycle khác saga lifecycle

**Saga** theo dõi quy trình nghiệp vụ gốc. **Reconciliation case** theo dõi sự bất thường và quyết định khôi phục. Một saga có thể phát sinh nhiều case, và một case có thể liên quan đến nhiều service hoặc provider references.

Không nên tái sử dụng duy nhất trạng thái ERROR trên saga để chứa mọi thông tin điều tra; thiếu owner, evidence, approval và audit rất khó vận hành.

### 9.2. Deadline và aging

Case có thể được phân cấp:

- **Critical:** tiền/đặt hàng có ảnh hưởng tức thời, nghi vấn charge trùng, khóa tài khoản sai.
- **High:** đơn đã thu tiền nhưng chưa thực hiện, refund pending lâu.
- **Medium:** reservation mồ côi, shipment metadata lệch chưa gây tác động trực tiếp.
- **Low:** projection/dashboard chỉ trễ hiển thị và có thể rebuild.

Mức ưu tiên phụ thuộc giá trị tiền, số người bị ảnh hưởng, nghĩa vụ khách hàng, thời hạn provider và rủi ro pháp lý. SLA nên do nghiệp vụ/vận hành thống nhất; các mức trên chỉ để minh họa.

## 10. Thiết kế một bộ reconciliation chạy nền

### 10.1. Kiến trúc tổng quan

~~~text
  Domain Services / Provider APIs / Statements
        |             |             |
        +-------------+-------------+
                      |
              [Reconciliation Runner]
                   |          |
         discover anomalies   fetch evidence
                   |          |
                   +----+-----+
                        |
                 [Rules / Policy]
                        |
            +-----------+------------+
            |                        |
      Safe auto-fix             Needs decision
            |                        |
            v                        v
       [Command Bus]            [Case Store]
            |                        |
         Domain API               Ops Console
            |                        |
            +-----------+------------+
                        |
                 Verify / Audit
                        |
               Metrics + Alerts
~~~

Runner có thể do Payments, Inventory hoặc một team nghiệp vụ sở hữu, với hạ tầng scheduler/case platform dùng chung. Tránh tạo “global super-reconciliation service” có quyền đọc/ghi mọi database mà không có ranh giới bảo mật, ownership và hợp đồng rõ.

### 10.2. Discover: tìm các bản ghi đáng kiểm tra

Có thể truy vấn theo:

- status = PENDING và updated_at cũ hơn ngưỡng.
- saga đang WAITING/COMPENSATING quá thời hạn.
- reservation expires_at nhỏ hơn now nhưng chưa released.
- outbox entry chưa publish quá SLA.
- ledger entry có provider reference nhưng thiếu internal correlation.
- callback message ở DLQ hoặc consumer lag kéo dài.

Không quét toàn bộ bảng lớn mỗi phút. Dùng index theo trạng thái/thời gian, page/cursor, partition theo thời gian/tenant, watermark và rate limit.

### 10.3. Fetch evidence: lấy dữ liệu có thẩm quyền

Một case cần snapshot dữ liệu tại thời điểm điều tra cùng metadata nguồn và thời gian. Hạn chế query liên tục vào provider có quota. Cần timeout, retry có backoff và cache nếu bằng chứng bất biến hoặc có TTL được định nghĩa.

Bằng chứng có thể thay đổi (ví dụ pending refund chuyển sang succeeded). Lệnh sửa sai phải kiểm tra lại **precondition tại thời điểm thực thi**, không hành động mù theo snapshot cũ.

### 10.4. Evaluate: phân loại, không sửa tùy tiện

Một policy engine hoặc application logic có thể trả:

~~~json
{
  "caseId": "rc-82017",
  "classification": "CAPTURE_OUTCOME_UNKNOWN",
  "evidenceStatus": "INSUFFICIENT",
  "decision": "WAIT_AND_RECHECK",
  "nextCheckAt": "2026-11-11T09:15:00Z",
  "autoFixAllowed": false,
  "reasonCode": "PROVIDER_STATUS_NOT_FINAL"
}
~~~

Một số sai lệch chỉ có thể được quyết định bởi con người hoặc rule nghiệp vụ bổ sung. Không cố “AI tự ra quyết định chuyển tiền” trên bằng chứng không đủ.

### 10.5. Execute: gửi command qua owner

Lệnh sửa sai nên đi qua **domain API/command handler được ủy quyền**, không trực tiếp cập nhật bảng nguồn của một context khác.

~~~text
Reconciliation Worker -> Inventory.ReleaseReservation
  operationId = "release-reservation-..."
  expectedReservationState = ACTIVE
  expectedVersion = 7
  reason = "ORDER_CANCELLED_RECONCILIATION"
  caseId = rc-...
~~~

Domain handler kiểm tra state/version/idempotency, thực thi giao dịch và phát event/ledger entry phù hợp. Caller nhận kết quả thật hoặc trạng thái PENDING; nếu timeout thì tiếp tục đối soát, không kết luận đã sửa.

### 10.6. Verify: đối soát lại sau hành động

Một lỗi thường gặp: đóng case ngay khi API trả 202 hoặc message đã publish. Cần phân biệt:

- **Action accepted:** đã nhận yêu cầu sửa.
- **Action executed:** domain owner đã xác nhận thao tác.
- **External effect confirmed:** provider/ledger xác nhận khi cần.
- **All invariants satisfied:** dữ liệu ở những nguồn liên quan đã ở trạng thái hợp lệ.

Case chỉ được RESOLVED theo policy sau khi có bằng chứng đủ cho mức xác nhận cần thiết. Nếu projection còn lag, có thể đóng phần side effect và mở/tracking một vấn đề projection riêng, thay vì giữ một case “thanh toán lỗi” mãi.

## 11. At-least-once delivery và idempotency trong remediation

Các tiến trình đối soát thường chạy nền, có retry và có thể bị chạy trùng:

- Scheduler có hai replica cùng kích hoạt.
- Worker crash sau khi gửi command nhưng trước khi ghi trạng thái case.
- Message được redeliver.
- Operator nhấn lại vì trang không phản hồi.
- Runbook được thực thi hai lần trong ca trực khác nhau.

Do đó **manual và automatic repair đều phải idempotent ở ranh giới tác dụng phụ**.

### 11.1. Khóa idempotency theo ý định

Ví dụ “Release reservation R vì order O đã hủy” có thể dùng một operation key ổn định theo action + reservationId + cancellation eventId hoặc case quyết định. Retry giữ nguyên key. Nhưng nếu một reservation có hai lần giữ hàng hợp lệ trong các thời kỳ khác nhau, phải dùng version/attempt đúng để tránh nhầm.

### 11.2. CAS/optimistic locking

Lệnh sửa thường cần điều kiện:

~~~sql
UPDATE reservations
SET status = 'RELEASED', version = version + 1
WHERE reservation_id = :reservationId
  AND status = 'ACTIVE'
  AND version = :expectedVersion;
~~~

Nếu zero rows affected, không nhất thiết là lỗi: có thể reservation đã released, consumed hoặc version thay đổi. Handler phải đọc lại và quyết định **already done**, **conflict cần điều tra**, hay **precondition no longer valid**.

### 11.3. Deduplication trong inbox

Consumer event có thể dùng processed-event table với unique (consumer, eventId). Phải ghi nhận processed marker cùng thay đổi nghiệp vụ trong một transaction nếu cùng database. Không ack rồi mới commit thay đổi quan trọng.

### 11.4. Fencing token và lease

Nếu hai worker cùng xử lý một case, lease đơn thuần có thể hết hạn khi worker A bị pause; B nhận lại. A tỉnh dậy và ghi đè kết quả B.

Có thể dùng lease version/fencing token tăng dần. Mọi cập nhật case state phải kiểm tra token hiện hành. Với side effect ngoài database, vẫn phải có idempotency/precondition ở domain service hoặc provider.

### 11.5. Side effect ngoài hệ thống

Nếu provider hỗ trợ idempotency key, lưu cùng key qua retry. Nếu không, phải sử dụng transaction lookup và một state machine chặt chẽ để tránh tạo yêu cầu mới trong khi kết quả cũ chưa xác định. Không coi exactly-once ở broker là bảo đảm đúng một khoản tiền được xử lý.

## 12. Transactional outbox, inbox và dữ liệu lịch sử

### 12.1. Outbox

Một lỗi dual-write điển hình:

~~~text
1. COMMIT payment captured nội bộ
2. PUBLISH PaymentCaptured event
~~~

Nếu bước 1 thành công nhưng bước 2 thất bại, downstream không biết trạng thái mới. Có thể dùng transactional outbox:

~~~text
BEGIN;
  UPDATE payment SET status = CAPTURED;
  INSERT INTO outbox(eventId, type, payload);
COMMIT;

Outbox relay -> event broker -> consumers
~~~

Outbox relay có thể publish lại; consumer cần idempotency. Reconciliation phát hiện outbox tồn quá lâu hoặc payment captured nhưng projection chưa đồng bộ.

### 12.2. Inbox

Consumer dùng inbox/processed messages để ghi nhận message đã xử lý và tránh side effect trùng. Nhưng replay một event sau khi consumer code thay đổi có thể cần **rebuild projection** dưới identity consumer khác; không tự xóa dedup marker trong production rồi phát lại tất cả.

### 12.3. Event log và replay

Nếu lỗi chỉ ảnh hưởng read model, có thể rebuild từ event log/CDC khi:

- Lịch sử còn đủ retention.
- Event schema/version còn đọc được.
- Consumer xử lý duplicate/out-of-order phù hợp.
- Replay không vô tình phát lệnh thu tiền/giao hàng/email lại.
- Có watermark/đối soát completeness và kế hoạch cutover.

**Replay không phải công cụ sửa mọi lỗi.** Nếu sự kiện nguồn chưa từng được tạo, log không có thông tin để dựng lại. Nếu nguồn nghiệp vụ sai, replay có thể tái tạo sai sót.

## 13. Xử lý thủ công: một phần của kiến trúc, không phải phương án cuối cùng vô hình

Một hệ thống chỉ có nút “Retry failed job” rồi hy vọng người trực sẽ biết cần làm gì là chưa hoàn chỉnh. Manual intervention phải có **giao diện, quyền, state, bằng chứng và công cụ an toàn**.

### 13.1. Khi nào bắt buộc chuyển cho con người?

- Tự động đã vượt retry/deadline và không có next safe action.
- Kết quả từ provider vẫn UNKNOWN sau cửa sổ đối soát.
- Bằng chứng mâu thuẫn, không đủ để chọn hành động.
- Compensation có thể gây ảnh hưởng tài chính/vật lý lớn.
- Quy tắc nghiệp vụ thay đổi sau khi workflow bắt đầu.
- Có nghi vấn gian lận, vi phạm chính sách hoặc tranh chấp.
- Đối tác không có API để sửa, phải qua cổng hỗ trợ/hợp đồng.
- Điều chỉnh số dư/thuế/chứng từ cần phê duyệt.
- Case có nguy cơ ảnh hưởng hàng loạt người dùng.
- Một lệnh đã được operator khác thực hiện và cần đánh giá race.

### 13.2. Những thông tin phải có trong case

Một màn hình Operations Console nên cho thấy:

1. Case ID, loại bất thường, severity, SLA và owner.
2. Business operation, order/payment/reservation/shipment IDs.
3. Timeline các bước saga, retry, compensation và callback.
4. Evidence từ từng nguồn, trạng thái xác minh, độ mới và liên kết log có quyền.
5. Các bất biến đang vi phạm và ảnh hưởng khách hàng.
6. Phân loại có thể tự sửa hay bắt buộc phê duyệt.
7. Action được phép và precondition, rủi ro của từng action.
8. Người thao tác, người phê duyệt, reason code và audit trail.
9. Kết quả thực thi và bằng chứng đối soát sau sửa.
10. Đường escalation tới Payments/Inventory/Support/Compliance theo chủ sở hữu.

Không bắt nhân viên tự chắp nối log 20 service chỉ để biết vì sao một đơn lỗi, cũng không cấp quyền SQL toàn DB cho mọi ca trực.

### 13.3. Mẫu màn hình

~~~text
CASE rc-82017  | HIGH | AWAITING_EVIDENCE
Order: ord-742        Payment: pay-391
Customer impact: Có thể đã thu tiền, đơn chưa xác nhận
Deadline: 10:00     Owner: Payments Operations

Timeline:
09:00 Capture requested, key=cap-814
09:00 Provider HTTP timeout
09:01 Status query UNKNOWN
09:03 Provider webhook not yet received
09:05 Automated reconciliation pending

Evidence:
[Internal payment attempt] [Provider query] [Ledger] [Trace]

Allowed actions:
[Recheck status]  [Escalate provider]  [Request manual review]

Forbidden until verified:
[Capture again] [Mark refunded] [Close as success]
~~~

Hiển thị lý do một nút không được phép giúp người trực hiểu hệ thống, không tìm cách bypass bằng thao tác ngoài luồng.

### 13.4. Phê duyệt theo rủi ro

Không phải mọi case cần hai người duyệt. Nhưng với action có tiền, quyền hoặc hậu quả khó đảo ngược, có thể yêu cầu:

- Maker-checker/four-eyes approval.
- Role-based hoặc attribute-based access control.
- Transaction limit và kiểm tra ngân sách/hạn mức.
- Reason code và mô tả tác động.
- Separate duty: người đề nghị không tự phê duyệt khi chính sách cấm.
- Step-up authentication cho thao tác nhạy cảm.
- Chính sách thay người duyệt, hết hạn approval, và kiểm soát khi thay đổi dữ liệu giữa lúc duyệt và lúc thực thi.

Phê duyệt phải dựa trên **snapshot quyết định** nhưng lúc chạy cần kiểm tra lại trạng thái thực. Một action được duyệt lúc 09:10 có thể không còn hợp lệ lúc 09:30 vì webhook đã đến.

## 14. Một lệnh sửa thủ công an toàn nên có gì?

Ví dụ thao tác “Mark external refund confirmed” không nên chỉ là PATCH status=REFUNDED do operator nhập. Cần một domain operation có contract:

~~~http
POST /v1/refunds/ref-203/confirm-external-settlement
Authorization: Bearer <operator-token>
Idempotency-Key: manual-repair-rc-82017-v1
If-Match: "refund-version-11"
Content-Type: application/json

{
  "reconciliationCaseId": "rc-82017",
  "providerReference": "provider-ref-203",
  "settlementEvidenceId": "evidence-901",
  "reasonCode": "PROVIDER_CONFIRMED_OFFLINE",
  "approvalId": "approval-451"
}
~~~

Hệ thống xử lý:

1. Xác thực operator và scope.
2. Kiểm tra approval còn hiệu lực và đúng action/amount.
3. Kiểm tra evidence có nguồn tin cậy và không bị thay đổi ngoài quy trình.
4. Kiểm tra refund hiện hành, version và trạng thái hợp lệ.
5. Deduplicate idempotency key.
6. Ghi state/ledger/audit/outbox trong transaction phù hợp.
7. Trả actionId và trạng thái; nếu cần thêm xác nhận, giữ PENDING.
8. Chạy lại reconciliation, chỉ đóng case khi invariant đạt.

**Đừng** tự tạo fake provider transaction ID hoặc ghi đè ledger để hợp với kỳ vọng. Nếu dữ liệu bên ngoài không xác minh được, case phải giữ trạng thái chưa rõ/được escalation.

### 14.1. Mọi action có precondition

Một action hợp lệ thường cần:

- Source state thuộc tập cho phép.
- Operation chưa được thực hiện trước đó, hoặc đã thực hiện với cùng kết quả.
- Business deadline/cut-off chưa cấm thao tác.
- Approval phù hợp với current amount/currency và tenant.
- Không có case/action cạnh tranh đang giữ lock hợp lệ.
- Downstream capability có thể nhận lệnh và xác thực identity.
- Có kế hoạch xác minh và xử lý unknown outcome sau command.

### 14.2. Tương tác giữa auto-repair và operator

Khi case được operator claim, auto-repair không nhất thiết phải dừng mọi kiểm tra. Có thể tiếp tục **read-only reconciliation**, nhưng các action có side effect phải theo policy ownership/lease để không cùng lúc thực thi hai hướng.

Nếu provider webhook tới giữa khi nhân viên đang điều tra, case cần refresh evidence và invalidate action không còn phù hợp. Thao tác sửa phải thực hiện kiểm tra version tại domain owner.

## 15. Quy tắc xử lý giao dịch tài chính

Các ví dụ thanh toán cần mức nghiêm ngặt cao hơn tác vụ thông thường.

### 15.1. Phân biệt authorization, capture, settlement và refund

Không nên dùng một cột boolean paid thay cho mọi quá trình. Một payment có thể AUTHORIZED nhưng chưa CAPTURED, đã CAPTURED nhưng chưa SETTLED, hoặc có PARTIAL_REFUND/CHARGEBACK.

~~~text
REQUESTED
   |
AUTHORIZED
   |
CAPTURED
   |
SETTLEMENT_PENDING
   |
SETTLED

Từ CAPTURED/SETTLED có thể phát sinh:
  REFUND_REQUESTED -> REFUND_PENDING -> REFUNDED
                              |
                         REFUND_UNKNOWN / REFUND_FAILED
~~~

State machine thực phụ thuộc provider và sản phẩm. Reconciliation phải so sánh những trạng thái **cùng định nghĩa**, không yêu cầu “capture amount = settlement amount” nếu provider trừ phí và chuyển net settlement.

### 15.2. Bút toán điều chỉnh

Một ledger có tính kiểm toán cần ghi nhận dòng tiền/chuyển trạng thái bằng entry mới hoặc reversal/adjustment phù hợp, không xóa bằng chứng gốc. Khi cần sửa:

- Liên kết adjustment với giao dịch bị ảnh hưởng.
- Ghi lý do, bằng chứng, người quyết định và approval.
- Giữ tính cân bằng theo mô hình sổ.
- Kiểm tra amount/currency/rounding.
- Tránh ghi hai adjustment cùng lý do do retry.
- Đối soát lại với provider và báo cáo kế toán.

### 15.3. Tình huống charge trùng

Một khách có hai capture cùng merchant intent. Không tự hoàn tiền một capture chỉ dựa trên việc “có hai record” vì có thể business support split payment, multiple partial captures hoặc authorization khác nhau. Cần xác minh provider IDs, amounts, original intent và điều kiện kinh doanh. Nếu xác định duplicate thật, refund có thể là action phù hợp; cũng có thể cần kênh giải quyết riêng theo chính sách.

### 15.4. Không phản hồi “đã hoàn tiền” trước bằng chứng cuối

Có thể hiển thị “Yêu cầu hoàn tiền đã được ghi nhận” sau khi hệ thống nhận command. Trạng thái “Đã hoàn tiền” nên theo nguồn có thẩm quyền và nghĩa đã thống nhất. Khi provider vẫn pending, UI phải thể hiện pending/estimated timeline thay vì kết luận thành công.

## 16. Quy tắc xử lý tồn kho, giao nhận và quyền lợi phi tiền tệ

### 16.1. Inventory reservation

Reservation có thể ACTIVE, EXPIRED, RELEASED hoặc CONSUMED. Nếu workflow lỗi:

- ACTIVE + order CANCELLED: có thể cần release.
- CONSUMED + order CANCELLED: cần điều tra fulfillment, không force release.
- EXPIRED rồi callback confirm tới muộn: kiểm tra version và không hồi sinh reservation cũ.
- Partial shipment: chỉ điều chỉnh phần thật sự chưa thực hiện theo quy tắc.

### 16.2. Shipping

Nếu tạo shipment timeout, phải query provider theo request reference trước. Khi vận đơn đã có, cập nhật record nội bộ thay vì tạo lại. Nếu shipment đã giao, không thể gọi cancel như một rollback vật lý; có thể cần quy trình return/refund hoặc xử lý khiếu nại.

### 16.3. Cấp quyền/entitlement

Khách đã trả tiền nhưng chưa được cấp quyền truy cập:

- Xác minh payment thật.
- Kiểm tra entitlement có tồn tại hoặc đã cấp trùng không.
- Nếu thiếu, cấp quyền bằng command idempotent có tham chiếu payment.
- Nếu payment bị đảo/chargeback, xác định chính sách thu hồi quyền và grace period.
- Audit thời điểm user được cấp hoặc bị thu hồi quyền.

### 16.4. Thông báo

Email/SMS có thể được gửi trùng nếu hệ thống phát lại event. Việc không gửi được thường không yêu cầu rollback payment. Nhưng nếu một thông báo là nghĩa vụ pháp lý/contract, case phải theo dõi việc gửi hoặc kênh thay thế.

## 17. Tránh sửa sai sai do dữ liệu đến trễ

### 17.1. Race với webhook

Một refund đang UNKNOWN, reconciliation dự tính gửi refund mới. Ngay lúc đó webhook cho biết refund cũ SUCCEEDED. Nếu action được kích hoạt dựa trên snapshot đã cũ, có nguy cơ hoàn tiền hai lần.

Phải:

- Dùng idempotency key ổn định.
- Re-read status và version sát thời điểm thực thi.
- Kiểm tra provider transaction reference.
- Lock/serialize business action ở owner nếu cần.
- Không tạo operation mới nếu kết quả cũ còn unknown.
- Thiết lập event version/timestamp semantics để callback cũ không ghi đè state mới.

### 17.2. Out-of-order messages

Một consumer có thể nhận RefundSucceeded trước RefundRequested từ các kênh khác nhau, hoặc nhận event retry sau vài giờ. Phải xác định **thứ tự nghiệp vụ**, monotonic state transitions và cách xử lý orphan event. Không chỉ sort theo timestamp từ hai máy khác nhau.

### 17.3. Cửa sổ nhất quán

Một mismatch xuất hiện trong vài giây có thể do eventual consistency bình thường. Bộ phát hiện nên có:

- Grace period cho propagation/event lag.
- Watermark/sequence nếu đọc projection.
- “Observed twice” hoặc xác minh qua nguồn gốc trước khi sửa, khi phù hợp.
- SLA theo loại event và loại nghiệp vụ.
- Không kéo dài grace period đến mức che vi phạm quan trọng.

### 17.4. Phát hiện sự kiện mất thật

Nếu lag đã hết mà một business event vẫn thiếu, đối soát nguồn gốc và outbox/inbox có thể chỉ ra event không được phát, consumer DLQ hoặc mapping lỗi. Khi sửa cần giữ event identity/contract đủ để tránh consumer khác hiểu đó là một nghiệp vụ mới.

## 18. Dữ liệu và API của case cần bảo mật như dữ liệu nghiệp vụ

Một reconciliation case có thể chứa thông tin thanh toán, địa chỉ, chứng từ, lịch sử truy cập và các quyết định nhạy cảm.

Cần:

- Authorization theo team, role, tenant và mức độ nhạy cảm.
- Mặt nạ thông tin và truy cập tối thiểu (least privilege).
- Mã hóa phù hợp và kiểm soát nguồn chứng cứ.
- Retention riêng cho case/evidence theo nghĩa vụ pháp lý và chính sách tổ chức.
- Không đưa secret, raw payment card, password, private key vào case/log.
- Audit bất biến hoặc chống sửa đổi trái phép cho quyết định/action quan trọng.
- Phân biệt user identity và service identity trong mọi command.
- Quy trình break-glass có giới hạn, lý do và rà soát sau khi dùng.
- Rate limit và quyền re-drive/replay đặc biệt.
- Ngăn SSRF/path injection nếu công cụ operator cho phép tra cứu URI/file từ đối tác.

Một công cụ repair có quyền rộng có thể nguy hiểm hơn chính lỗi hệ thống ban đầu. Nên xây **domain-specific repair endpoints** chứ không cung cấp quyền UPDATE mọi bảng.

## 19. Observability và SLO cho phục hồi thực tế

### 19.1. Chỉ số phát hiện

- Số transaction stuck theo từng trạng thái và age.
- Số mismatch mới/phút theo category và source.
- Outbox backlog/oldest age, inbox pending, DLQ count.
- Provider unknown-outcome rate.
- Saga compensation failure rate.
- Tỷ lệ event/projection lag vượt ngưỡng.
- Độ trễ từ business action đến khi kết quả được xác minh.

### 19.2. Chỉ số giải quyết

- **Time to detect (TTD):** thời gian từ khi sai lệch xuất hiện đến khi được ghi nhận.
- **Time to reconcile:** thời gian thu thập đủ bằng chứng.
- **Time to resolve (TTR):** từ phát hiện đến kết quả nghiệp vụ đúng.
- Tỷ lệ case auto-resolved, manually resolved, escalated, reopened.
- Tỷ lệ case không có owner hoặc quá SLA.
- Số action thủ công không thành công hoặc tạo side effect không mong muốn.
- Tỷ lệ outcome UNKNOWN còn tồn.
- Số tiền/đơn/hàng hóa chịu ảnh hưởng, không chỉ số lượng case.
- Thời gian từ accepted correction đến provider confirmation.
- Reconciliation false-positive rate nếu đo được.

### 19.3. Metric theo mức ảnh hưởng

Một case thanh toán 100 triệu đồng có rủi ro khác một case notification trễ. Dashboard nên phân tầng theo:

- Giá trị tiền/hàng hóa hoặc số khách hàng bị ảnh hưởng.
- Loại nghiệp vụ, tenant/product/region.
- Mức ưu tiên/severity và deadline.
- Trạng thái unknown, action pending, unresolved.
- Kênh đối tác và nguyên nhân kỹ thuật.

Tránh metric label có cardinality rất cao như caseId hay orderId; ID nên vào trace/log/searchable case store, metric tổng hợp theo loại.

### 19.4. Ví dụ SLO

Đây là mục tiêu minh họa, không mặc định:

- 99,9% capture outcome được biết hoặc có case có owner trong 10 phút.
- Không có refund case ưu tiên cao quá 1 giờ mà chưa được tiếp nhận.
- 99% reservation hết hạn được release hoặc phát hiện bất thường trong 15 phút.
- 100% manual money adjustment có evidence, reason và audit.
- 99% outbox events được publish trong 30 giây bình thường.
- Mọi case RESOLVED phải vượt bước post-action verification theo policy.

Một hệ thống API 99,99% availability vẫn có thể có sự cố kinh doanh lớn nếu một khoản tiền bị treo không ai đối soát. Do đó SLO cần đo **kết quả nghiệp vụ**.

### 19.5. Tracing

~~~text
customer checkout request
  | correlationId=checkout-742
  v
OrderCreated --> ReserveStock --> CapturePayment
                                       |
                                  timeout / UNKNOWN
                                       |
                            ReconciliationCase rc-82017
                                       |
                            Provider status lookup
                                       |
                           Manual review / resolution
                                       |
                              Post-fix verification
~~~

Trace theo từng HTTP request có thể hết từ lâu khi manual case được giải quyết. Dùng correlation/business ID để nối log, event, workflow, case và action; không cần giữ một span sống hàng giờ.

## 20. Runbook xử lý một case thanh toán UNKNOWN

### Giai đoạn 1 — Tiếp nhận và cô lập rủi ro

1. Nhận case, kiểm tra severity và owner.
2. Xác định customer/order/payment/provider references.
3. Kiểm tra có request capture/refund mới đang chạy hay không.
4. Ngăn **gửi command trùng không an toàn** nếu chưa biết outcome cũ.
5. Đánh giá tác động khách hàng và các deadline đã cam kết.
6. Không công bố “đã thành công/đã hoàn tiền” khi chưa có bằng chứng.

### Giai đoạn 2 — Thu thập bằng chứng

1. Đọc payment attempt state, ledger entries và idempotency key.
2. Tra provider status theo merchant/provider reference.
3. Đọc webhook inbox, DLQ/outbox và delivery state.
4. Kiểm tra settlement file hoặc reporting channel có thẩm quyền nếu cần.
5. Chuẩn hóa amount, currency, transaction type và thời điểm.
6. Lưu evidence có nguồn và thời gian truy xuất.

### Giai đoạn 3 — Quyết định

| Kết quả | Hành động có thể phù hợp |
| --- | --- |
| Provider xác nhận capture SUCCEEDED, nội bộ PENDING | Repair internal state/event sau khi kiểm tra identity |
| Provider xác nhận FAILED/NOT_EXECUTED có độ tin cậy theo contract | Có thể retry cùng ý định với idempotency phù hợp |
| Provider vẫn UNKNOWN | Giữ pending, query lại theo lịch, escalate |
| Provider có hai captures ngoài ý định | Điều tra duplicate, quyết định refund/adjustment theo policy |
| Ledger và provider mâu thuẫn | Điều tra settlement, không tự tạo bút toán để làm đẹp UI |
| Giao dịch có nghi vấn gian lận | Chuyển bộ phận rủi ro theo quy trình |

### Giai đoạn 4 — Thực thi sửa

1. Tạo proposed action và kiểm tra role/approval.
2. Xác nhận version/precondition vẫn đúng.
3. Gọi domain-specific action với idempotency key ổn định.
4. Nhận actionId và theo dõi tới terminal result.
5. Nếu response timeout, không retry bằng operation mới; tra cứu outcome.
6. Ghi audit, reason, bằng chứng và liên kết provider/ledger.

### Giai đoạn 5 — Đối soát lại và đóng case

1. Đọc nguồn có thẩm quyền sau sửa.
2. Kiểm tra invariant order/payment/ledger.
3. Kiểm tra không tạo side effect trùng.
4. Cập nhật kết quả cho user/support theo chính sách.
5. Đóng case với resolution code và evidence.
6. Tạo issue về root cause nếu sự cố có tính hệ thống.

## 21. Ví dụ Java/Spring: job đối soát có trạng thái rõ

Đây là pseudo-code mô tả cấu trúc, không phải bộ mã chạy được độc lập. Trong production phải bổ sung transaction, repository, security, network client, metrics và kiểm thử.

### 21.1. Phân loại kết quả bằng kiểu dữ liệu

~~~java
sealed interface CaptureEvidence
        permits CaptureConfirmed, CaptureRejected, CaptureUnknown {}

record CaptureConfirmed(
        String providerTransactionId,
        BigDecimal amount,
        String currency) implements CaptureEvidence {}

record CaptureRejected(String providerCode)
        implements CaptureEvidence {}

record CaptureUnknown(String reason, Instant checkedAt)
        implements CaptureEvidence {}
~~~

Không coi exception là “rejected” nếu thật ra chỉ mất kết nối. Với amount, dùng cấu trúc tiền có currency và quy tắc precision chuẩn của miền.

### 21.2. Reconciler tra cứu trước khi quyết định

~~~java
public final class PaymentReconciler {
    private final PaymentRepository payments;
    private final ProviderGateway provider;
    private final ReconciliationCaseRepository cases;

    public void reconcile(String paymentId) {
        Payment payment = payments.load(paymentId);

        if (payment.isFinalAndVerified()) {
            cases.closeIfNoOpenAction(paymentId, "ALREADY_CONSISTENT");
            return;
        }

        CaptureEvidence evidence =
            provider.lookupCapture(payment.merchantReference());

        switch (evidence) {
            case CaptureConfirmed confirmed ->
                cases.recordProposedCorrection(
                    paymentId,
                    confirmed.providerTransactionId(),
                    "SYNC_CAPTURE_CONFIRMED");

            case CaptureRejected rejected ->
                cases.recordFinding(
                    paymentId,
                    "PROVIDER_REJECTED",
                    rejected.providerCode());

            case CaptureUnknown unknown ->
                cases.scheduleRecheckOrEscalate(
                    paymentId, unknown.reason());
        }
    }
}
~~~

Không phải mọi CaptureRejected đều cho phép tạo capture mới; cần biết business deadline và provider contract. Phần recordProposedCorrection **chưa ghi trạng thái payment thành công**: nó chỉ là dữ liệu để policy/handler quyết định và thực thi an toàn.

### 21.3. Domain command kiểm tra tiền điều kiện

~~~java
@Transactional
public RepairActionResult confirmCapture(
        ConfirmCaptureCommand cmd,
        OperatorIdentity operator) {

    security.requirePermission(operator, "payment.repair");
    approvalPolicy.validate(cmd.approvalId(), operator, cmd);

    Payment payment = payments.lockById(cmd.paymentId());

    // Một request được retry cần trả cùng kết quả logic.
    RepairActionResult existing =
        actions.findByIdempotencyKey(cmd.idempotencyKey());
    if (existing != null) return existing;

    payment.requireStateAllowedForCaptureRepair();
    payment.requireVersion(cmd.expectedVersion());
    evidenceVerifier.verifyProviderCapture(
        cmd.evidenceId(), payment);

    RepairAction action = payment.confirmExternalCapture(cmd);
    payments.save(payment);
    actions.save(action);
    outbox.save(PaymentCaptureReconciled.from(payment, action));

    return RepairActionResult.from(action);
}
~~~

Logic thực cần xử lý unique constraint/race khi hai request trùng key đến đồng thời; việc find trước rồi insert đơn thuần chưa đủ. Approval và evidence phải kiểm chứng chặt, các giao dịch/bút toán được cập nhật theo mô hình ledger chính thức.

### 21.4. Scheduler theo lô và giới hạn tải

~~~java
public void scheduledPass() {
    for (PaymentId id : payments.findStalePendingPage(
            Instant.now().minus(Duration.ofMinutes(10)), 200)) {
        reconciliationQueue.enqueueIfNotActive(id);
    }
}
~~~

Chỉ là phác thảo. Khi chạy nhiều replica, cần đảm bảo claim/lease, idempotent enqueue, pagination và checkpoint để không quét cùng tập vô hạn. Có thể dùng DB job table hoặc queue broker theo quy mô và năng lực vận hành.

### 21.5. Hành động thủ công có event riêng

Có thể phát các sự kiện như:

- ReconciliationCaseOpened
- ReconciliationEvidenceUpdated
- RepairActionApproved
- RepairActionExecuted
- RepairActionVerificationFailed
- ReconciliationCaseResolved

Đây là **audit/operational events** phục vụ theo dõi và tích hợp, không có nghĩa mỗi event phải được công bố ra toàn hệ thống. Phân biệt event “đã phê duyệt sửa” và “sửa có hiệu lực” để consumer không hiểu nhầm.

## 22. SQL minh họa cho tìm kiếm bất thường

### 22.1. Tìm payment pending quá tuổi

~~~sql
SELECT payment_id, merchant_reference, status, updated_at
FROM payments
WHERE status IN ('CAPTURE_PENDING', 'CAPTURE_UNKNOWN')
  AND updated_at < :cutoff
ORDER BY updated_at
LIMIT :batchSize;
~~~

Trong DB lớn cần index theo status/updated_at, cursor/keyset pagination và kiểm soát số lần scan. Không dùng quét không giới hạn trên một bảng nóng.

### 22.2. Tìm reservation hết hạn nhưng vẫn active

~~~sql
SELECT reservation_id, order_id, expires_at, version
FROM inventory_reservations
WHERE status = 'ACTIVE'
  AND expires_at < :now
ORDER BY expires_at
LIMIT :batchSize;
~~~

Một reservation “ACTIVE sau expiresAt” có thể là ứng viên đối soát, nhưng trước khi release phải xác minh policy và trạng thái order/fulfillment theo hợp đồng.

### 22.3. Tìm outbox bị kẹt

~~~sql
SELECT event_id, aggregate_id, event_type, created_at
FROM outbox
WHERE published_at IS NULL
  AND created_at < :cutoff
ORDER BY created_at
LIMIT :batchSize;
~~~

Không tự kết luận event chưa được broker nhận chỉ vì published_at NULL; relay có thể đã publish rồi crash trước khi đánh dấu. Khôi phục có khả năng publish duplicate nên consumer phải idempotent.

### 22.4. Không sửa trực tiếp bằng một UPDATE tùy tiện

~~~sql
-- Không nên dùng câu kiểu này như thao tác nghiệp vụ:
UPDATE payments SET status = 'CAPTURED'
WHERE payment_id = :paymentId;
~~~

Lệnh trên bỏ qua evidence, ledger, version, idempotency, outbox, audit và business rules. Nếu một runbook buộc phải dùng data repair ở tầng DB vì sự cố nghiêm trọng, cần quy trình riêng có backup, review, phê duyệt, phạm vi rõ, log thao tác và bước hậu kiểm — không làm nó thành cơ chế sửa sai mặc định.

## 23. Kiểm thử phục hồi: thử lỗi đúng ranh giới

Một bộ kiểm thử đủ tốt cần tiêm lỗi ở những điểm dễ để lại **trạng thái mơ hồ**, không chỉ mô phỏng 500 trước khi ghi dữ liệu.

### 23.1. Ma trận lỗi

| Điểm tiêm lỗi | Nguy cơ | Điều cần xác minh |
| --- | --- | --- |
| Crash sau DB commit, trước publish event | Missing downstream signal | Outbox recover và consumer idempotent |
| Crash sau publish, trước đánh dấu outbox | Duplicate event | Không tạo side effect trùng |
| Provider xử lý thành công nhưng response timeout | Unknown outcome | Tra cứu trước retry, không charge lần hai |
| Retry compensation khi bước cũ đang chạy | Race | State/lease/version bảo vệ |
| Callback cũ đến sau khi state final | Regression | Monotonic transition/version check |
| Operator nhấn nút hai lần | Duplicate manual action | Idempotency và single approval |
| Auto-repair chạy đồng thời với manual action | Conflicting fixes | Precondition/lock/cancel policy |
| Provider trả hai IDs cho một intent | Duplicate external operation | Phát hiện, điều tra và resolution an toàn |
| Projection trễ một phút | False-positive | Grace window/watermark |
| Event vào DLQ | Silent partial completion | Alert, owner, re-drive an toàn |
| Ledger thiếu dòng adjustment | Accounting mismatch | Case chưa được đóng |
| Đối tác mất API tra cứu | Evidence unavailable | Escalation với SLA |
| Approval hết hạn trước khi action thực thi | Unauthorized action | Từ chối và refresh approval |
| Operator không đủ scope của tenant | Unauthorized read/write | Không lộ dữ liệu, ghi audit |
| Case đã RESOLVED nhưng event muộn xuất hiện | Reopened mismatch | Mở lại/khởi tạo case theo policy |
| Retention event log hết | Không thể replay đầy đủ | Snapshot/backfill hoặc manual recovery |

### 23.2. Bất biến kiểm thử

- Không có hai capture thực cho cùng intent ngoài quy tắc nghiệp vụ.
- Không có case được RESOLVED chỉ vì command đã được enqueue.
- Lỗi timeout provider không tự biến thành REJECTED.
- Nếu bằng chứng UNKNOWN, auto-repair không gửi một command tiền mới không an toàn.
- Manual action luôn có operator, reason code, evidence và version.
- Cùng idempotency key được retry không tạo hai adjustment.
- Case mới phải có owner hoặc cơ chế auto assignment trong SLA.
- Không dùng read model chưa xác minh để chứng minh provider đã xử lý tiền.
- Reconciliation retry không thay đổi kết quả sau khi case đã có terminal resolution hợp lệ.
- Khi auto và manual race, chỉ action qua precondition hiện hành được phép có hiệu lực.

### 23.3. Contract tests với đối tác

Provider có thể thay đổi cách báo pending, cách trả NotFound, lịch settlement hoặc ID. Kiểm thử contract phải phân biệt:

- Transaction không tồn tại thật.
- Transaction đang xử lý/chưa thể tra cứu.
- Lỗi hệ thống tạm thời.
- Kết quả cuối thành công.
- Kết quả cuối bị từ chối.
- Callback duplicate hoặc đến trễ.

Đặc biệt, provider trả 404 trong thời gian eventual indexing chưa chắc chứng minh “capture chưa thực hiện”. Đây phải là kiến thức từ contract, không suy đoán.

### 23.4. Game days và diễn tập

Trong môi trường an toàn, diễn tập:

1. Cố ý làm một reconciliation job không hoàn tất.
2. Để webhook tới muộn sau một phút.
3. Kill worker giữa write DB và ack.
4. Đóng giả provider lookup trong một khoảng.
5. Cho hai operator cùng mở case.
6. Thử auto-repair trước khi manual case claim.
7. Thực thi một approval bị thay đổi dữ liệu.
8. Re-drive DLQ vào consumer staging.
9. Kiểm tra dashboard, alert, on-call và audit.
10. Đối chiếu tổng số tiền/trạng thái cuối không bị trùng.

Không thử tạo giao dịch tiền thật hoặc sửa dữ liệu khách hàng production khi chưa có phê duyệt và cô lập phù hợp.

## 24. Vận hành ở quy mô lớn: ưu tiên, công suất và backlog

### 24.1. Một backlog reconciliation cũng là hàng đợi nghiệp vụ

Khi một payment provider outage kéo dài, có thể xuất hiện hàng trăm nghìn giao dịch pending. Không thể query provider cho tất cả mỗi giây. Cần:

- Batch và rate limit theo provider.
- Retry với exponential backoff và jitter.
- Ưu tiên theo mức độ rủi ro/giá trị và deadline.
- Fairness theo tenant/customer.
- Admission control và worker concurrency cap.
- Lịch query phù hợp chính sách provider.
- Bulk reconciliation từ settlement file nếu đó là kênh tin cậy hơn.
- Dự trù capacity sau sự cố để backlog giảm.

### 24.2. Ước lượng đơn giản

Giả sử mỗi lần đối soát cần trung bình 2 giây wall time và có 20 worker hiệu quả, năng lực lý thuyết khoảng 10 kiểm tra/giây (600/phút) khi không bị rate limit/lock. Nếu 30.000 case tồn, tối thiểu khoảng 50 phút để đi qua một lượt theo giả định lý tưởng, chưa tính case cần nhiều lần query và tải mới.

Đây là phép tính minh họa, không phải cam kết. Thông lượng thực thường bị giới hạn bởi API đối tác, database, số lần retry, phân bố thời gian xử lý và giới hạn tài chính/bảo mật.

### 24.3. Chống starvation

Case giá trị nhỏ không nên bị bỏ quên vô hạn chỉ vì case lớn luôn ưu tiên. Có thể dùng priority với aging, quota theo class, deadline queue và escalation rules. Mỗi lớp cần SLO riêng.

### 24.4. Dọn dẹp case và chứng cứ

Đóng case không có nghĩa xóa ngay. Cần retention/audit theo chính sách. Khi đã quá thời hạn, có thể lưu snapshot tối thiểu hoặc xóa dữ liệu nhạy cảm theo quy định. Không để kho evidence thành điểm rò dữ liệu lâu dài.

## 25. Một kịch bản chi tiết: đơn đã thu tiền nhưng giao hàng thất bại

### 25.1. Diễn biến

1. Ordering tạo order-742 PENDING.
2. Inventory giữ hàng thành công.
3. Payments capture 500.000 VND thành công.
4. Fulfillment gửi CreateShipment, provider tạo vận đơn ship-9.
5. Response CreateShipment timeout.
6. Saga cho rằng CreateShipment thất bại và thử hủy; provider trả “không tìm thấy” do indexing delay.
7. Sau nhiều lần, compensation chưa rõ đã hủy hay chưa.
8. Order vẫn ở trạng thái COMPENSATING, khách thấy tiền bị thu nhưng chưa có lịch giao.

### 25.2. Điều không được làm

- Không tự động tạo shipment mới với request ID mới khi chưa biết ship-9 tồn tại hay không.
- Không đánh dấu đơn “hủy xong” khi payment refund vẫn UNKNOWN.
- Không giải phóng reservation nếu đã có bước fulfillment thực sự tiêu thụ hàng.
- Không gửi email “đơn đã giao” dựa trên response timeout hoặc một projection sai.
- Không yêu cầu khách thanh toán lại chỉ vì UI chưa nhận được PaymentCaptured.

### 25.3. Luồng đối soát

~~~text
Stuck saga detector
    |
    v
Case opened: SHIPMENT_OUTCOME_UNKNOWN
    |
    +--> Query Payments: capture confirmed 500.000 VND
    +--> Query Inventory: reservation active
    +--> Query carrier by merchant shipment key: ship-9 exists
    +--> Query carrier status: LABEL_CREATED, not dispatched
    |
    v
Policy: resume fulfillment with existing ship-9
    |
    v
Fulfillment.AttachExistingShipment (idempotent)
    |
    v
Ordering updates business state through valid events
    |
    v
Reconcile invariant, close case after verification
~~~

Nếu carrier thực sự không cho tra cứu hoặc trạng thái quá phức tạp, chuyển manual review để liên hệ đối tác. Nếu shipment đã giao hoặc không thể hủy, cần chọn con đường nghiệp vụ khác; không bắt hệ thống phải “quay về trước khi đặt hàng”.

### 25.4. Manual decision tree

Nếu provider xác nhận vận đơn tồn tại:

- Có thể gắn lại vận đơn cũ và tiếp tục?
- Trạng thái thực tế của kiện hàng ra sao?
- Có chứng từ phí/nhãn đã phát sinh?
- Có thể hủy mà không tạo nghĩa vụ bổ sung?
- Nếu khách đã yêu cầu hủy, ai phê duyệt phương án hoàn tiền/giao trả?
- Có cần thông báo tình trạng trung thực cho khách?

Nếu provider không xác nhận được:

- Escalation tới carrier support.
- Đặt case ở AWAITING_PROVIDER_EVIDENCE với deadline.
- Giới hạn các thao tác có thể gây duplicate.
- Thống nhất phương án dịch vụ khách hàng nếu kéo dài.

## 26. Kịch bản khác: cấp quyền chưa thực hiện sau khi thanh toán

Một nền tảng học trực tuyến thu tiền thành công nhưng user chưa có quyền vào khóa học. Đây không nhất thiết là lỗi tiền, có thể là event mất hoặc entitlement consumer lỗi.

Phương pháp:

1. Xác minh payment capture tại nguồn Payments/provider.
2. Kiểm tra Entitlement DB theo userId/courseId/business purchase intent.
3. Xem outbox PaymentCaptured và inbox của Entitlement.
4. Nếu event thiếu, phát recovery event/command có ID ổn định qua domain owner.
5. Nếu entitlement đã cấp nhưng projection chưa cập nhật, rebuild projection.
6. Nếu course đã bị gỡ hoặc user không đủ điều kiện, cần business decision hoàn tiền hoặc chuyển khóa.
7. Chỉ thông báo “đã cấp quyền” sau khi entitlement owner xác nhận.
8. Audit thời gian khách bị mất quyền và chính sách bồi hoàn nếu có.

Có thể tự sửa nhanh nếu entitlement creation idempotent và điều kiện không đổi. Ngược lại, nếu khóa học đã bị hủy hoặc quyền truy cập có hạn định pháp lý, cần xử lý thủ công có chính sách.

## 27. Khi nào không cần một hệ thống reconciliation riêng?

Trong ứng dụng nhỏ, có thể có:

- Một database.
- Ít hoặc không có hệ ngoài.
- Công việc idempotent, rollback cục bộ đủ.
- Số case ngoại lệ rất ít.

Khi đó, một scheduled query + bảng exception + dashboard đơn giản có thể đủ. Không nhất thiết mua workflow engine hoặc xây platform chung.

Ngược lại, khi số lượng tiền/giao hàng, số đối tác, kỳ vọng kiểm toán và nhiều service tăng, nên có một **năng lực đối soát có owner**, có case store, policy, alert, công cụ thao tác và audit. Quyết định triển khai riêng hay nằm trong service không thay đổi yêu cầu tính đúng đắn.

## 28. Thiết kế ranh giới tổ chức và trách nhiệm

### 28.1. Ai sở hữu việc gì?

| Năng lực | Owner nên xác định | Trách nhiệm |
| --- | --- | --- |
| Payment outcome | Payments/domain team | Provider contract, ledger, idempotency |
| Refund decision | Payments + business policy owner | Điều kiện refund, approval, nghĩa vụ |
| Inventory reservation | Inventory team | Reservation state và release semantics |
| Shipping state | Fulfillment team | Carrier API và vận đơn |
| Case operations | Operations/support được phân quyền | Điều tra, phê duyệt và thao tác theo runbook |
| Reconciliation platform | Platform hoặc domain owner | Scheduler, case store, audit, dashboard |
| Incident response | On-call/Incident commander | Phối hợp, mức độ, thông tin khách hàng |
| Accounting/compliance | Team có thẩm quyền | Đối soát sổ, điều chỉnh và lưu chứng cứ |

Không để một team “đối soát” dùng quyền admin toàn hệ thống để tự quyết định mọi nghiệp vụ. Domain owners phải cung cấp các command sửa sai được kiểm soát; operational team thực thi trong phạm vi được ủy quyền.

### 28.2. Escalation hữu ích

- Case không có evidence đủ → domain owner/provider support.
- Action tiền vượt hạn mức → approval của Payments/Finance.
- Nghi vấn gian lận → Risk/Fraud team.
- Dữ liệu cá nhân hoặc quyền truy cập sai → Security/Privacy.
- Nhiều case cùng root cause → Incident response.
- Vi phạm deadline khách hàng → Customer Support và policy owner.

Một escalation tốt xác định **người, quyền, SLA và đầu ra mong đợi**, thay vì chỉ gửi một email “nhờ kiểm tra”.

## 29. Bài tập thực hành A — thanh toán có kết quả mơ hồ

**Bối cảnh:** ứng dụng du lịch đặt phòng. Booking tạo yêu cầu thanh toán 1.500.000 VND. Payment provider timeout. Sau đó webhook thông báo CAPTURED đến trễ 30 phút; trong lúc ấy saga cố cancel booking và tự phát lệnh refund, nhưng refund cũng timeout.

**Yêu cầu:**

1. Vẽ các state Booking, Payment, Refund và ReconciliationCase.
2. Chỉ ra tại sao timeout không cho phép kết luận payment FAILED.
3. Đề xuất những ID/idempotency key cần lưu.
4. Thiết kế bộ đối soát trước khi quyết định retry capture/refund.
5. Xác định khi nào được phép hoàn tiền tự động và khi nào cần operator.
6. Với webhook CAPTURED đến sau khi booking CANCELLED, action nào còn hợp lệ?
7. Nếu refund đã thực hiện nhưng callback mất, làm sao tránh hoàn tiền hai lần?
8. Thiết kế response trung thực cho user trong khi kết quả UNKNOWN.
9. Định nghĩa điều kiện RESOLVED của reconciliation case.
10. Đề xuất 8 failure-injection tests tại các ranh giới commit, publish, ack, callback và manual action.

### Hướng giải tham khảo

Lưu payment intent và provider reference ổn định; query provider để xác minh capture, không tạo capture thứ hai khi còn UNKNOWN. Lệnh refund dùng idempotency key riêng cho cùng ý định hoàn tiền. Cả payment/refund có thể có nhiều attempts nhưng một kết quả nghiệp vụ. Case chỉ đóng khi booking/payment/refund thỏa chính sách cuối. Nếu booking đã hủy nhưng capture thành công, quy trình có thể cần refund xác nhận, tùy điều kiện dịch vụ/đối tác. Webhook trễ cần version/state preconditions để không hồi sinh booking.

## 30. Bài tập thực hành B — tồn kho bị giữ sau khi hủy đơn

**Bối cảnh:** hệ thống có 30.000 reservation mỗi ngày. Scheduler tự giải phóng reservation hết hạn. Một lần deploy làm job không chạy trong 2 giờ; khi chạy lại, nhiều reservation đã đổi trạng thái vì fulfillment đã thực thi.

**Yêu cầu:**

1. Tìm các reservation ứng viên bằng truy vấn có index.
2. Thiết kế grace window để tránh false-positive.
3. Phân biệt ACTIVE, RELEASED, EXPIRED, CONSUMED và UNKNOWN.
4. Đề xuất command ReleaseReservation với expectedVersion.
5. Làm sao chạy nhiều reconciliation workers mà không release trùng?
6. Có nên force release mọi reservation quá giờ không?
7. Nếu Inventory và Fulfillment mâu thuẫn, bằng chứng nào cần thu thập?
8. Mở case thủ công khi điều kiện nào xảy ra?
9. Tạo metrics backlog, oldest age, auto-repair success, manual escalation.
10. Thiết kế rollout xử lý backlog mà không làm quá tải Inventory DB.

### Hướng giải tham khảo

Dùng quét theo status/expiry với batch/keyset pagination, worker concurrency cap và idempotent release. Kiểm tra reservation state/version và mối liên hệ với fulfillment. Không force release record đã CONSUMED hoặc có lệnh giao hàng đang thực thi. Khi không thể xác định, đưa vào case với owner và deadline; chỉ đóng sau verify.

## 31. Bài tập thực hành C — sai lệch sổ thanh toán

**Bối cảnh:** cuối ngày hệ thống nội bộ ghi 9.800 giao dịch capture, provider settlement file liệt kê 9.795 dòng. Một số giao dịch là partial capture và một số settlement trừ phí.

**Yêu cầu:**

1. Giải thích vì sao không thể chỉ so sánh số dòng và tổng amount.
2. Xác định những ID, currency, fee, transaction type và accounting date cần chuẩn hóa.
3. Thiết kế các loại mismatch và quy tắc phân loại.
4. Trình bày cách lưu evidence và không rò thông tin nhạy cảm.
5. Một capture có provider reference nhưng không có ledger entry thì xử lý sao?
6. Có nên sửa database nội bộ trực tiếp để khớp file không?
7. Nêu vai trò của manual approval khi điều chỉnh sổ.
8. Thiết kế báo cáo unresolved amount và độ tuổi case.
9. Đề xuất cách chạy lại đối soát không nhân duplicate adjustments.
10. Mô tả tiêu chí hoàn tất đợt đối soát cuối ngày.

### Hướng giải tham khảo

So sánh đúng loại giao dịch/giá trị trong cùng đơn vị tiền, xử lý partial transactions và phí theo contract. Ghi mismatch và triage. Với thay đổi tiền, dùng ledger adjustment/reversal được ủy quyền, đối chiếu lại và audit. Chạy lại phải idempotent theo batch ID, transaction ID và adjustment intent; không tự sửa status để biểu đồ “đẹp”.

## 32. ADR mẫu: cơ chế đối soát và can thiệp thủ công cho Saga thanh toán

~~~markdown
# ADR: Đối soát và xử lý ngoại lệ sau khi Saga tự phục hồi thất bại

## Bối cảnh
Checkout thực thi Order, Inventory, Payments, Shipping.
Compensation không phải luôn thành công và external timeout
có thể để lại kết quả UNKNOWN. Hiện một số case PENDING
không có owner, đối soát trễ và nhân viên phải can thiệp bằng SQL.

## Quyết định
- Các domain service giữ source of truth và sửa qua command API.
- Mỗi workflow có correlation/business operation IDs ổn định.
- Bổ sung scheduled reconciliation cho state quá hạn.
- Trước khi retry external side effect, tra cứu outcome theo reference.
- Dùng outbox/inbox/idempotency và version precondition.
- Mở ReconciliationCase cho mismatch hoặc unknown chưa phục hồi.
- Auto-repair chỉ theo policy xác định, có post-action verification.
- Manual repair qua Ops Console có RBAC, evidence, reason và audit.
- Money adjustments theo ledger/approval, không SQL update trực tiếp.
- Theo dõi stuck age, unknown outcomes và unresolved cases.

## Phương án cân nhắc
A. Chỉ tăng retry/retry vô hạn.
B. Thủ công bằng SQL và ticket tự do.
C. Reconciliation jobs + case management + repair commands.
D. Đổi toàn bộ workflow sang distributed transaction toàn cục.

## Lý do
C bảo đảm đường phục hồi có chủ, quan sát và audit; không giả định
external providers có transaction chung hoặc compensation luôn thành công.

## Hệ quả
- Tăng case store, scheduler, dashboard và runbook.
- Cần phân quyền/approval cho manual actions.
- Phải thiết kế key/version, producer/consumer idempotency.
- Có chi phí đối soát provider và các dữ liệu cần lưu giữ.

## Chỉ số và xác nhận
- SLO biết outcome hoặc có owner cho transaction quá hạn.
- Time to detect/time to resolve cho từng case type.
- Tỷ lệ auto-fix và manual-escalation.
- Test unknown outcome, callback muộn, duplicate, operator race.
- Đối soát ledger/provider/Order sau mọi action tiền.

## Điều kiện xem lại
- Lượng case vượt capacity xử lý thủ công.
- Provider cung cấp API lookup hoặc idempotency mới.
- Có loại sai lệch mới hoặc yêu cầu tuân thủ thay đổi.
~~~

## 33. Checklist trước khi triển khai production

**Định nghĩa nghiệp vụ và nguồn bằng chứng**

- [ ] Mỗi loại giao dịch có source of truth và owner rõ.
- [ ] Phân biệt outcome UNKNOWN với FAILED.
- [ ] Có invariant kiểm tra được cho tiền/hàng/quyền lợi.
- [ ] Xác định settling window, deadline và mức độ ưu tiên.
- [ ] Nhận diện các trường hợp partial capture/refund/shipment hợp lệ.

**Ghi nhận và phát hiện**

- [ ] Có business operation ID, provider reference, event ID, saga ID.
- [ ] Có outbox/inbox hoặc cơ chế chống mất/trùng phù hợp.
- [ ] Scheduled reconciliation tìm stuck/expired/mismatch.
- [ ] Event-based detection và batch settlement khi cần.
- [ ] Có retry/backoff/quota/checkpoint cho reconciliation jobs.
- [ ] Case store theo dõi evidence, owner, SLA và lifecycle.

**Sửa sai an toàn**

- [ ] Auto-repair chỉ với policy được phê duyệt và đủ evidence.
- [ ] Command sửa qua domain owner, không SQL chéo database.
- [ ] Có idempotency key và version/precondition tại thời điểm thực thi.
- [ ] Có hành vi rõ khi action response timeout hoặc provider UNKNOWN.
- [ ] Post-action verification trước khi RESOLVED.
- [ ] Điều chỉnh tiền có ledger entry, reason và approval theo mức rủi ro.
- [ ] Callback/event đến trễ không ghi đè trạng thái cuối sai cách.

**Can thiệp thủ công**

- [ ] Ops Console có timeline, evidence, root cause và action được phép.
- [ ] Có phân quyền, tenant isolation và audit đầy đủ.
- [ ] Tác vụ nhạy cảm có maker-checker hoặc quy trình phê duyệt phù hợp.
- [ ] Có cảnh báo khi case quá SLA hoặc chưa có owner.
- [ ] Có escalation rõ tới domain/provider/risk/finance.
- [ ] Manual action chịu được double-click, retry và race với automation.
- [ ] Có quy trình break-glass khi cấp thiết, ghi lại và rà soát.

**Vận hành và kiểm chứng**

- [ ] Theo dõi số lượng, tuổi, giá trị và severity của unresolved cases.
- [ ] Có SLO cho detection/resolution và outcome UNKNOWN.
- [ ] Thử crash giữa DB commit–publish, ack, external timeout, callback trễ.
- [ ] Thử retry trùng, compensation thất bại, manual/auto race.
- [ ] Có runbook khôi phục và phương án an toàn khi provider outage.
- [ ] Định kỳ đối soát kết quả repair với nguồn có thẩm quyền.
- [ ] Có postmortem và biện pháp phòng ngừa lỗi lặp lại.

## 34. Tổng kết

Trong giao dịch phân tán, **retry, idempotency, saga và compensation là lớp phục hồi tự động đầu tiên**, không phải bảo đảm rằng mọi quy trình đều sẽ quay về trạng thái hoàn hảo. Khi kết quả bên ngoài mơ hồ, các nguồn mâu thuẫn hoặc bù trừ thất bại, hệ thống cần một luồng rõ ràng để **đối soát sự thật, quyết định cách sửa và bàn giao có kiểm soát cho con người**.

Năng lực này phải được thiết kế ngay từ đầu:

- **Phát hiện:** không để PENDING, UNKNOWN, COMPENSATING hoặc sai lệch tồn tại vô hạn không ai biết.
- **Hiểu bằng chứng:** biết source of truth, định danh, trạng thái cuối, độ trễ và giới hạn của từng nguồn.
- **Sửa an toàn:** sử dụng command theo miền, idempotency, precondition và xác minh lại, không chỉnh dữ liệu tùy tiện.
- **Con người trong vòng lặp:** có case, quyền, phê duyệt, audit, SLA, escalation và giao diện hỗ trợ quyết định.
- **Theo dõi kết quả nghiệp vụ:** không chỉ biết message đã ack hay API đã trả 200, mà biết tiền/hàng/quyền lợi thực sự đã ở trạng thái chấp nhận được hay chưa.

Một kiến trúc đủ trưởng thành không đòi hỏi **mọi lỗi đều tự sửa được**. Nó bảo đảm rằng **khi tự động phục hồi thất bại, hệ thống vẫn có bằng chứng, người chịu trách nhiệm và con đường sửa sai an toàn, có thể kiểm chứng**.
