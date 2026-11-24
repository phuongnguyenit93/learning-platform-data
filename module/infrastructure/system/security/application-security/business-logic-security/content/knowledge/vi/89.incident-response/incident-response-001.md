# Business rule incident detection — Phát hiện sự cố vi phạm quy tắc nghiệp vụ

## 1. Mục tiêu và phạm vi

Một đơn hàng có thể chuyển sang trạng thái đã thanh toán dù chưa có bằng chứng thu tiền. Một yêu cầu hoàn tiền có thể vượt hạn mức sau khi hai worker cùng xử lý. Một người dùng có thể gửi dữ liệu đúng định dạng nhưng tác động tới đối tượng ngoài quyền. Các thao tác này có thể nhận phản hồi HTTP thành công, không tạo exception và không làm hệ thống chậm đi.

**Phát hiện sự cố vi phạm quy tắc nghiệp vụ** là quá trình quan sát bằng chứng để nhận ra rằng hành vi hoặc trạng thái đã đi ra ngoài hợp đồng nghiệp vụ và bảo mật. Đơn vị cần bảo vệ là số tiền, quyền, trạng thái, hạn mức hoặc nghĩa vụ của một thao tác; không chỉ là sự sống của tiến trình hay mã phản hồi API.

Bài học thuộc chương Incident Response của module SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY. Nội dung nối business invariants, state machine, quyền theo đối tượng, transaction và idempotency với việc tạo tín hiệu phát hiện, xác minh và chuyển giao sự cố. Các ví dụ bao gồm bỏ qua phê duyệt, sửa giá, thao tác sai quyền và yêu cầu trùng.

Sau bài học, bạn có thể:

- Chuyển quy tắc nghiệp vụ thành điều kiện phát hiện có phạm vi và bằng chứng rõ ràng.
- Phân biệt nỗ lực bị chặn, hành vi bất thường và hiệu lực trái phép đã xảy ra.
- Chọn nguồn dữ liệu đủ tin cậy, xử lý giao trùng và độ trễ của luồng sự kiện.
- Thiết kế cảnh báo có thể điều tra mà không làm lộ dữ liệu không cần thiết.
- Kiểm thử detector bằng kịch bản phá bất biến và ca đối chứng hợp lệ.

## 2. Phát hiện khác với ngăn chặn như thế nào?

Kiểm soát phòng ngừa quyết định thao tác có được phép tạo hiệu lực hay không. Ví dụ, service kiểm tra quyền trên đơn, xác nhận phiên bản phê duyệt và giữ hạn mức hoàn tiền trong transaction trước khi ghi thay đổi.

Detector kiểm tra những gì đã được yêu cầu, được quyết định hoặc thực sự xảy ra. Nó giúp nhận ra đường đi bị bỏ sót, cấu hình sai, race condition, lạm dụng đặc quyền hoặc hậu quả chưa được kiểm soát phòng ngừa bao phủ.

| Lớp quan sát | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Yêu cầu | Người gọi đã cố làm gì? | Gửi giá thấp hơn báo giá đã xác nhận |
| Quyết định | Hệ thống đã cho phép hay từ chối dựa trên gì? | Cho phép hoàn tiền theo policy version V7 |
| Hiệu lực đã commit | Điều gì đã thay đổi bền vững? | Tạo hai khoản hoàn cho cùng thao tác logic |
| Đối soát | Dữ liệu giữa các ranh giới có khớp không? | Nhà cung cấp xác nhận hoàn nhưng sổ nội bộ chưa ghi nhận |

Yêu cầu bị từ chối là bằng chứng về một nỗ lực, chưa phải bằng chứng thiệt hại đã xảy ra. Không thấy request đáng ngờ cũng không chứng minh an toàn: hiệu lực sai có thể đến từ worker, tích hợp, công cụ quản trị hoặc thao tác sửa dữ liệu.

Không dùng cảnh báo sau sự kiện để thay cho kiểm tra quyền và transaction ở đường xử lý chính. Detector có độ trễ vài phút không thể tự thu hồi hàng đã giao hoặc dữ liệu đã bị xem.

## 3. Chuyển bất biến thành điều kiện phát hiện

Bất biến cần chỉ rõ đối tượng, phạm vi, điều kiện áp dụng và thời điểm đánh giá. Câu “không cho hoàn quá tiền” chưa đủ vì chưa nói tới tiền tệ, khoản giữ chỗ, thao tác chưa rõ kết quả hoặc thanh toán nhiều đợt.

Ví dụ, với một khoản thanh toán và một loại tiền tệ:

```text
R = tổng hoàn tiền đã thành công
H = tổng hạn mức đang giữ cho thao tác hoàn còn hiệu lực
C = số tiền đã thu được phép hoàn theo chính sách

R + H <= C
```

Mỗi thao tác chỉ đóng góp một lần theo trạng thái hiện tại. Khi chuyển từ giữ chỗ sang thành công, cùng số tiền không được nằm đồng thời trong R và H. Một thao tác bên ngoài chưa rõ kết quả cần giữ mức phơi nhiễm phù hợp theo chính sách; timeout không tự chứng minh tiền chưa được hoàn.

| Mã | Bất biến | Dấu hiệu cần kiểm tra | Bằng chứng tối thiểu |
| --- | --- | --- | --- |
| BR-01 | Chỉ thực hiện đơn sau khi đáp ứng điều kiện thanh toán | Có quyền thực hiện đơn nhưng thiếu khoản thu hợp lệ | Đơn, kỳ thu, bằng chứng thu và chính sách áp dụng |
| BR-02 | Thao tác được bảo vệ phải có phê duyệt hợp lệ | Chuyển trạng thái thiếu phê duyệt đúng phiên bản | Lịch sử chuyển trạng thái, revision nội dung và phê duyệt |
| BR-03 | Giá chấp nhận phải có căn cứ phía server | Giá chốt lệch báo giá hoặc giảm giá được phép | Báo giá, phiên bản giá, cấu phần tiền và quyết định giảm giá |
| BR-04 | Chủ thể chỉ tác động tới đối tượng trong quyền | Hiệu lực trên tài nguyên ngoài phạm vi được cấp | Danh tính đã xác thực và căn cứ ủy quyền tại thời điểm thao tác |
| BR-05 | Một danh tính thao tác chỉ tạo số hiệu lực được phép | Nhiều hiệu lực cho cùng thao tác logic | Operation ID, nội dung đã ràng buộc và hiệu lực đã commit |
| BR-06 | Tổng nghĩa vụ hoàn không vượt khả năng hoàn | R + H vượt C | Trạng thái từng thao tác, số tiền, tiền tệ và dữ liệu thu |

Các mã là quy ước của ví dụ, không phải tên một tiêu chuẩn. Quy tắc thực tế cần phiên bản và người chịu trách nhiệm giải thích chính sách.

Không mặc định mọi đơn chỉ có một khoản thu, mọi khoản hoàn đều cần hai người duyệt hoặc mọi thao tác khác tenant đều trái phép. Thanh toán nhiều đợt, ủy quyền hợp lệ và tài khoản vận hành dùng chung phải được biểu diễn trong hợp đồng thay vì ngoại lệ ngầm.

Một đặc tả phát hiện nên trả lời đủ:

1. Đang kiểm tra bất biến nào và ở phạm vi nào?
2. Sự kiện hay lịch quét nào kích hoạt đánh giá?
3. Nguồn nào xác nhận các sự thật được sử dụng?
4. Khi nào dữ liệu đủ đầy để kết luận?
5. Kết quả nào là vi phạm, hợp lệ hoặc chưa đủ bằng chứng?
6. Ai tiếp nhận, xác minh và quyết định hành động bảo vệ?

## 4. Nguồn bằng chứng và ranh giới tin cậy

### 4.1. Không lấy điều người gọi khai làm sự thật

Các trường tenantId, actorRole, approvedBy, price hoặc paymentStatus trong body chỉ là đầu vào nếu chưa được ràng buộc với nguồn đáng tin cậy.

Nguồn phát hiện nên nối được:

- Chủ thể đã xác thực với phiên làm việc hoặc tài khoản dịch vụ.
- Tài nguyên thực sự bị tác động với tổ chức sở hữu và phiên bản dữ liệu.
- Quyết định quyền với policy, ủy quyền hoặc ngoại lệ được cấp cụ thể.
- Giá với báo giá và quy tắc giảm giá phía server.
- Thanh toán với định danh giao dịch từ nguồn đã xác minh.
- Thay đổi trạng thái với transaction hoặc phiên bản đã commit.

Webhook mang tên PaymentSucceeded chưa chứng minh đã thu tiền. Cần biết nguồn gửi, ranh giới xác minh và tham chiếu thanh toán có gắn với đúng đối tượng hay không.

### 4.2. Thu thập từ hiệu lực đã commit

Log “bắt đầu hoàn tiền” không chứng minh hoàn thành công. Log “đã duyệt” ghi trước transaction có thể vẫn tồn tại dù transaction rollback.

Khi dữ liệu nghiệp vụ và outbox cùng database, có thể ghi sự kiện thay đổi cùng transaction rồi phát hành sau commit. Detector vẫn phải chịu được phát hành trùng, chậm và phát lại; một dòng outbox không bảo đảm toàn bộ luồng chỉ nhận một lần.

Nếu cần đối chiếu với hệ thống ngoài, phải có nguồn xác nhận ở ranh giới đó. Commit database nội bộ không chứng minh nhà cung cấp đã tạo hiệu lực, cũng không hoàn tác hiệu lực ngoài khi transaction nội bộ rollback.

### 4.3. Giữ cả chuyển trạng thái

Trạng thái hiện tại có thể che một lần chuyển sai rồi được sửa lại. Ví dụ, đơn chuyển từ PENDING_APPROVAL sang FULFILLING, tạo lệnh giao hàng, sau đó được đưa trở về trạng thái cũ.

Lịch sử chuyển trạng thái hoặc sự kiện bền vững giúp nhận ra đường đi này. Snapshot vẫn hữu ích cho bất biến tổng hợp, nhưng cần kết hợp với bằng chứng chuyển đổi và các hiệu lực liên quan.

Quyền ghi và sửa bằng chứng cũng cần được giới hạn. Nếu một tài khoản có thể sửa dữ liệu và xóa toàn bộ dấu vết tương ứng, việc không tìm thấy cảnh báo có giá trị chứng minh rất thấp.

## 5. Hợp đồng sự kiện phục vụ phát hiện

Sự kiện minh họa cho một thay đổi đã commit:

```json
{
  "eventId": "evt-refund-42",
  "eventType": "RefundOperationStateCommitted",
  "schemaVersion": 1,
  "source": "refund-service",
  "occurredAt": "2026-01-15T09:00:00Z",
  "tenantId": "tenant-A",
  "aggregateType": "Payment",
  "aggregateId": "pay-17",
  "aggregateVersion": 108,
  "operationId": "refund-op-42",
  "actorId": "service-refund-worker",
  "authorizationDecisionId": "decision-93",
  "policyVersion": "refund-policy-v7",
  "beforeState": "RESERVED",
  "afterState": "SUCCEEDED",
  "amountMinor": 400000,
  "currency": "VND",
  "correlationId": "flow-61"
}
```

Đây là mô hình minh họa, không phải giao thức bắt buộc. Trường source chỉ đáng tin khi được ràng buộc với danh tính bên phát qua cơ chế tích hợp; nó không tự xác thực bằng cách mang tên một service.

Các điểm cần thống nhất:

- Event ID nhận diện sự kiện trong phạm vi nguồn đã xác thực; giữ ổn định khi giao lại cùng sự kiện.
- Operation ID nhận diện thao tác nghiệp vụ, khác một lần gọi HTTP hoặc lần giao broker.
- Aggregate version chỉ biểu diễn thứ tự trong phạm vi đối tượng theo hợp đồng, không phải đồng hồ toàn hệ thống.
- OccurredAt biểu diễn thời điểm nghiệp vụ theo nguồn; detector ghi riêng thời điểm nhận để đo độ trễ.
- Policy version và decision ID cho phép truy lại căn cứ quyền, không thay cho xác minh căn cứ đó phù hợp.
- AmountMinor dùng số nguyên theo đơn vị tiền nhỏ nhất được quy định cho từng tiền tệ. VND trong ví dụ dùng số đồng; không mặc định mọi tiền tệ có hai chữ số thập phân.

Nếu thiếu lịch sử quyền hoặc dữ liệu phê duyệt, báo thiếu bằng chứng tương ứng. Không suy ra “được phép” từ việc request thành công, hoặc “trái phép” chỉ vì người thao tác hiện không còn quyền.

Không đưa token, mật khẩu, khóa ký hoặc toàn bộ payload khách hàng vào sự kiện cảnh báo. Dùng tham chiếu tới bằng chứng có kiểm soát truy cập khi cần điều tra sâu.

## 6. Ba cách phát hiện bổ trợ nhau

### 6.1. Kiểm tra tại điểm thay đổi

Service ghi nhận vi phạm hoặc nỗ lực bị chặn khi đánh giá lệnh. Cách này có ngữ cảnh tốt về chủ thể, đối tượng và quyết định quyền, nhưng có thể bỏ sót đường xử lý không đi qua cùng điểm kiểm tra.

Sự kiện phải phân biệt REJECTED, ALLOWED và COMMITTED. Không gộp request bị từ chối với hiệu lực đã xảy ra thành cùng một loại sự cố.

### 6.2. Phân tích luồng sự kiện

Detector theo dõi sự kiện đã commit để kiểm tra chuyển trạng thái, số hiệu lực và mẫu hành vi theo thời gian. Nó có thể nối phê duyệt với thao tác sau đó hoặc nhận ra một operation ID tạo nhiều hiệu lực.

Cần giữ trạng thái đủ cho cửa sổ kiểm tra, chịu giao trùng và nhận ra mất kết nối, sự kiện đến muộn hoặc thiếu phiên bản.

### 6.3. Đối soát định kỳ

Truy vấn dữ liệu đã commit hoặc đối chiếu nguồn ngoài có thể tìm sai lệch mà luồng sự kiện bỏ lỡ. Cách này phù hợp với tổng tiền, trạng thái tồn đọng và xác nhận hiệu lực ngoài.

Đối soát cần phạm vi, mốc chốt và cách phục hồi sau lần chạy dở. Một lần quét kéo dài, so sánh các đối tượng tại thời điểm khác nhau, có thể tạo sai lệch quan sát nếu không được thiết kế theo yêu cầu nhất quán.

Luồng sự kiện giúp giảm độ trễ, đối soát kiểm tra tính đầy đủ, còn dấu vết tại điểm thay đổi giúp giải thích quyết định ban đầu. Độ bao phủ nên xét cả API, worker, tích hợp và đường quản trị có thể tạo cùng loại hiệu lực.

## 7. Ví dụ: hoàn tiền vượt số đã thu

### 7.1. Tình huống và bất biến

Khoản thanh toán P-17 đã thu 1000000 VND, toàn bộ số tiền được phép hoàn theo chính sách ví dụ. Trước đợt xử lý, đã có khoản hoàn thành công R-1 là 700000 VND.

Hai worker đọc dữ liệu cũ và mỗi worker cho phép hoàn 200000 VND. Nếu không giữ hạn mức nguyên tử, cả hai khoản có thể cùng được chấp nhận. Khi cả hai thành công:

```text
C = 1000000 VND
R = 700000 + 200000 + 200000 = 1100000 VND
H = 0 VND
R + H - C = 100000 VND
```

Đây là vi phạm bất biến theo fixture, không cần ngưỡng “hơn 10 giao dịch trong một phút”. Để khẳng định tiền bên ngoài đã hoàn thừa, cần xác nhận từ nguồn có thẩm quyền ở ranh giới thanh toán, không chỉ tên một sự kiện nội bộ.

### 7.2. Giả mã đánh giá

```text
onCommittedRefundEvent(event):
    verifyTrustedSourceAndSchema(event)
    paymentKey = resolveVerifiedPaymentScope(event)

    snapshot = readConsistentCommittedPaymentSnapshot(paymentKey)
    require snapshot is sufficiently complete for this rule

    capacity = calculateCapacityFromTrustedFacts(snapshot)
    succeeded = sumDistinctSuccessfulRefundOperations(snapshot)
    reserved = sumDistinctActiveRefundReservations(snapshot)

    if succeeded + reserved > capacity:
        upsertViolationCandidate(
            ruleId = BR_06,
            ruleVersion = detectorRuleVersion,
            scope = paymentKey,
            evaluatedVersion = snapshot.version,
            evidence = snapshot.references,
            excess = succeeded + reserved - capacity
        )
    else:
        recordEvaluationWithoutViolation(snapshot.version)
```

Các hàm là giả mã, không phải API có sẵn. Chúng phải dùng cùng tiền tệ, loại bản sao vận chuyển và xác định trạng thái từng thao tác theo mô hình hệ thống. Nếu còn thao tác ngoài chưa rõ kết quả, không âm thầm tính chúng bằng không.

Không dùng nguyên hàm quyết định hạn mức của production làm oracle duy nhất. Nếu chính hàm đó sai, detector có thể lặp lại lỗi. Hợp đồng phát hiện cần được mô tả độc lập, dùng dữ liệu gốc và fixture có kết quả biết trước.

### 7.3. Truy vấn kiểm tra hiệu lực trùng

Truy vấn sau giả sử bảng refund_business_effect chứa một dòng chuẩn cho mỗi hiệu lực hoàn thành công, không phải các dòng debit và credit của sổ kép:

```sql
SELECT tenant_id,
       provider_account_id,
       external_refund_id,
       COUNT(*) AS effect_count
FROM refund_business_effect
WHERE effect_state = 'SUCCEEDED'
  AND external_refund_id IS NOT NULL
GROUP BY tenant_id, provider_account_id, external_refund_id
HAVING COUNT(*) > 1;
```

Phạm vi định danh của nhà cung cấp phải phản ánh đúng trong khóa. Kết quả cho thấy nội bộ có nhiều dòng cho cùng hiệu lực ngoài theo hợp đồng ví dụ; nó không tự chứng minh nhà cung cấp đã hoàn tiền hai lần.

Truy vấn cũng không phát hiện hai khoản hoàn khác ID nhưng tổng vượt hạn mức. Cần quy tắc tổng hợp BR-06 và đối soát ngoài để trả lời các câu hỏi đó. Thiếu external refund ID ở thao tác lẽ ra phải có định danh cần tín hiệu chất lượng dữ liệu riêng, không được coi là không vi phạm.

## 8. Phê duyệt, state machine và giá

### 8.1. Phê duyệt phải gắn với nội dung được duyệt

Yêu cầu hoàn 100000 VND được duyệt ở revision 12 không mặc nhiên cho phép hoàn 900000 VND ở revision 13. Detector cần nối hiệu lực với phiên bản nội dung và căn cứ phê duyệt tương ứng.

Điều kiện phát hiện có thể là:

```text
protected transition committed
AND no valid approval exists for:
    target object + relevant revision + operation type + allowed scope
```

“Không thấy phê duyệt” phải được đánh giá trên nguồn đủ đầy và theo mốc chốt phù hợp. Nếu luồng phê duyệt đang trễ, tạo ứng viên cần xác minh hoặc tra cứu nguồn gốc; độ trễ đó chưa chứng minh người dùng đã bỏ qua phê duyệt.

Nếu chính sách yêu cầu tách người tạo và người duyệt, so sánh danh tính theo quy tắc tổ chức, không chỉ tên hiển thị. Phê duyệt khẩn cấp hợp lệ cần căn cứ ngoại lệ, phạm vi, thời hạn và bằng chứng được cấp.

### 8.2. Theo dõi cạnh chuyển trạng thái

Ví dụ hệ thống quy định:

```text
DRAFT -> PENDING_APPROVAL -> APPROVED -> EXECUTING -> COMPLETED
```

Cạnh PENDING_APPROVAL -> EXECUTING là ứng viên vi phạm nếu thiếu ngoại lệ hợp lệ. Nhận sự kiện EXECUTING trước APPROVED qua hai kênh chưa chứng minh cạnh đó đã xảy ra. Phải dùng lịch sử đã commit, phiên bản đối tượng hoặc nguồn trạng thái có thẩm quyền.

Ngoài tên cạnh, kiểm tra điều kiện bảo vệ cạnh. APPROVED -> EXECUTING có thể đúng về tên trạng thái nhưng sai nếu phê duyệt đã bị thu hồi trước khi thực hiện hoặc nội dung đã đổi ngoài phạm vi được duyệt.

### 8.3. Kiểm tra căn cứ giá

So sánh giá chốt với giá niêm yết hiện tại dễ gây cảnh báo sai vì có báo giá cũ còn hiệu lực, mã giảm giá, thuế, phí vận chuyển hoặc quy tắc làm tròn.

Detector nên truy lại báo giá được chấp nhận, phiên bản quy tắc, cấu phần số tiền và ngoại lệ được cấp tại thời điểm chốt. Tiền giảm có mã hợp lệ khác với trường discount do client tự nhập rồi được chấp nhận ngoài chính sách.

Không dùng số thực nhị phân hoặc ngưỡng sai lệch tùy ý để che lỗi tính tiền. Đơn vị tiền, cách làm tròn và sai số cho phép cần được xác định theo nghiệp vụ.

## 9. Quyền theo đối tượng và tín hiệu lạm dụng

Quyền gọi endpoint không đồng nghĩa quyền trên mọi đối tượng truyền vào endpoint đó. Detector cần biết chủ thể đang thao tác cho ai, tài nguyên thuộc phạm vi nào và căn cứ ủy quyền cụ thể.

Hiệu lực đã commit mà không tìm được quyết định quyền hợp lệ cho đúng chủ thể, hành động, đối tượng và ngữ cảnh là tín hiệu cần xác minh. Thiếu bản ghi quyết định cũng có thể là lỗi thu thập; cần tách thiếu bằng chứng khỏi bằng chứng quyết định cho phép sai.

Không dùng riêng điều kiện actor.tenantId khác object.tenantId để kết luận vượt quyền. Nhân viên hỗ trợ, dịch vụ liên tổ chức hoặc ủy quyền có thể hợp lệ. Cũng không mặc định tài khoản đặc quyền được phép làm mọi việc: phạm vi và thời hạn đặc quyền vẫn cần kiểm chứng.

Các mẫu có ích cho việc ưu tiên điều tra:

- Nhiều lần truy cập đối tượng ngoài phạm vi, sau đó có một lần tạo hiệu lực thành công.
- Một chủ thể đổi tham chiếu đơn, tổ chức hoặc người thụ hưởng qua nhiều yêu cầu gần nhau.
- Một tài khoản tạo và duyệt nhiều yêu cầu mà chính sách đòi hỏi tách nhiệm vụ.
- Tài khoản dịch vụ bắt đầu thực hiện loại thao tác ngoài hợp đồng tích hợp.

Đây là tín hiệu, không tự chứng minh ý đồ tấn công. Cần xét thay đổi sản phẩm, thao tác vận hành được cấp quyền và tích hợp mới; vẫn ưu tiên bảo vệ đối tượng khi đã có bằng chứng vi phạm.

Quyền phải được xét theo thời điểm hành động. Thu hồi quyền hôm nay không làm thao tác được phép hôm qua trở thành trái phép; cấp quyền sau sự cố cũng không hợp thức hóa hành động trước đó.

## 10. Giao trùng, thứ tự và độ trễ

### 10.1. Detector cũng cần idempotency

Sự kiện có thể được giao lại sau khi detector đã lưu ứng viên nhưng mất ACK. Nếu mỗi lần nhận tạo cảnh báo mới, hệ thống gây bão cảnh báo và làm sai số liệu sự cố.

Khóa tiếp nhận có thể gồm phạm vi detector, nguồn đã xác thực và event ID. Việc ghi bằng chứng đã xử lý và cập nhật trạng thái đánh giá cần ranh giới nhất quán theo thiết kế; không ACK công việc chưa lưu bền vững.

Khóa gom cảnh báo khác khóa tiếp nhận. Nhiều sự kiện có thể cùng chứng minh một vi phạm trên P-17; cần nối chúng vào trường hợp điều tra và cập nhật tác động.

Khóa gom minh họa:

```text
(ruleId, detectorRuleVersion, verifiedTenantScope,
 aggregateId, violationEpisodeId)
```

Violation episode phân biệt đợt đang mở với đợt mới sau phục hồi. Không khử trùng vĩnh viễn theo payment ID rồi bỏ mất tái diễn. Khi đổi phiên bản detector, cần liên kết hoặc di chuyển các trường hợp đang mở để tránh nhân đôi cảnh báo chỉ do triển khai.

### 10.2. Sự kiện đến muộn không đồng nghĩa trạng thái sai

Thời điểm xảy ra khác thời điểm detector nhận sự kiện. Sự kiện thu tiền tới chậm có thể làm detector tạm thấy lệnh thực hiện đơn mà chưa thấy bằng chứng thanh toán.

Có thể dùng cửa sổ chờ có căn cứ, phiên bản đối tượng hoặc truy vấn xác minh trực tiếp. Cửa sổ phải dựa trên đặc điểm luồng, yêu cầu phát hiện và giới hạn vận hành; không tự chọn số giây rồi dùng cho mọi hệ thống.

Cửa sổ xử lý độ trễ điều chỉnh cách diễn giải bằng chứng, không kéo dài quyền làm một thao tác trái phép. Quy tắc phải phát hiện tại điểm commit không được âm thầm chuyển thành chờ cuối ngày.

Nếu phiên bản bị khuyết hoặc luồng vượt giới hạn đến muộn, đánh dấu phạm vi chưa đủ dữ liệu, bổ sung đối soát và đánh giá lại. Không tuyên bố an toàn vì detector chưa có đủ sự kiện.

### 10.3. Snapshot phải nhất quán với câu hỏi

Đọc tổng thu ở T1 rồi tổng hoàn ở T2 có thể tạo tổ hợp chưa từng tồn tại như trạng thái đã commit. Với bất biến trong cùng database, dùng snapshot hoặc transaction đọc phù hợp database và mô hình cập nhật.

Với nhiều hệ thống không chia sẻ transaction, xác định mốc chốt, trạng thái chưa rõ và quy trình đối soát. Không gọi các lần đọc độc lập là snapshot nhất quán chỉ vì cùng correlation ID.

## 11. Từ tín hiệu thành cảnh báo có thể xử lý

Một vòng đời minh họa:

```text
OBSERVED -> NEEDS_VERIFICATION -> CONFIRMED_VIOLATION
                              -> EXPECTED_BEHAVIOR
                              -> INSUFFICIENT_EVIDENCE
```

Quy tắc có bằng chứng đầy đủ có thể xác nhận trực tiếp; tín hiệu hành vi thường cần xác minh thêm. Vi phạm nghiệp vụ đã xác nhận vẫn chưa tự xác định nguyên nhân là tấn công hay lỗi phần mềm.

| Nhóm | Nội dung cảnh báo |
| --- | --- |
| Nhận diện | Rule ID, phiên bản quy tắc, mã trường hợp điều tra |
| Phạm vi | Tenant, loại đối tượng, object ID và operation ID |
| Kết luận hiện tại | Nỗ lực bị chặn, ứng viên cần xác minh hay vi phạm có bằng chứng |
| Bất biến | Điều kiện mong đợi và giá trị thực tế |
| Thời gian | Thời điểm hiệu lực, phát hiện, mốc chốt và độ trễ |
| Bằng chứng | Tham chiếu bản ghi đã commit, quyết định quyền, phê duyệt hoặc nguồn ngoài |
| Tác động | Số tiền, tiền tệ, số đối tượng và nghĩa vụ bị ảnh hưởng |
| Điều phối | Nhóm tiếp nhận, độ ưu tiên, bước xác minh và thời điểm cập nhật |

Mô tả có ích: “BR-06, P-17, snapshot version 108: hoàn thành công 1100000 VND vượt khả năng hoàn 1000000 VND; ba thao tác liên quan; cần xác minh trạng thái nhà cung cấp.” Câu “refund bất thường” không cho người trực biết cần bảo vệ điều gì.

Không đưa dữ liệu cá nhân hoặc bí mật vào tiêu đề, nhãn metric hay kênh thông báo rộng. Quyền xem cảnh báo và mở bằng chứng cần phù hợp phạm vi đối tượng.

Ứng viên chưa đủ bằng chứng cần thời hạn và bước theo dõi. Nếu dữ liệu bổ sung cho thấy hành vi hợp lệ, ghi lý do chuyển trạng thái; không xóa lịch sử khiến việc đánh giá chất lượng detector mất căn cứ.

## 12. Mức ưu tiên, ngưỡng và ngoại lệ

Ưu tiên phản ánh tác động, độ tin cậy bằng chứng và khả năng tiếp tục tạo hiệu lực sai. Một lần đọc trái phép thành công có thể cần xử lý khẩn dù không mất tiền. Khoản hoàn vượt hạn mức chưa rõ kết quả ngoài cần theo dõi phơi nhiễm và bước xác minh rõ.

Phân biệt hai loại quy tắc:

- **Bất biến cứng:** trong phạm vi và thời điểm áp dụng, một lần vi phạm đã có ý nghĩa. Không chờ nhiều lần mới ghi nhận một lần vượt quyền đã xác nhận.
- **Tín hiệu hành vi:** tần suất, tốc độ, chuỗi thất bại hoặc phân bố giá trị khác thường. Cần baseline, ngưỡng phù hợp nhóm đối tượng và ca giải thích hợp lệ.

Rate limit cảnh báo có thể giảm thông báo lặp nhưng phải giữ dữ liệu, bộ đếm và khả năng nâng mức khi tác động tăng. Không im lặng sau cảnh báo đầu tiên rồi che toàn bộ thiệt hại tiếp theo.

Ngoại lệ cần căn cứ, người cấp, phạm vi, thời hạn và dấu vết. Tắt quy tắc cho toàn tenant vì một thao tác đặc biệt dễ tạo điểm mù. Hết hạn ngoại lệ, detector phải trở lại chính sách bình thường và cho phép kiểm tra thao tác trong khoảng đó.

Metric có thể gom theo rule và mức ưu tiên. Customer ID hoặc order ID có rất nhiều giá trị nên đặt trong hệ thống bằng chứng hoặc log có kiểm soát thay vì nhãn metric không giới hạn.

## 13. Tính sẵn sàng và độ bao phủ của detector

Không có cảnh báo có thể nghĩa là chưa quan sát thấy vi phạm, hoặc detector không còn quan sát được. Cần theo dõi riêng:

- Luồng vào còn tiến triển; heartbeat hoặc tín hiệu kiểm tra đã biết có tới nơi không.
- Độ trễ từ hiệu lực tới phát hiện và dữ liệu chưa được đánh giá.
- Sự kiện lỗi schema, nguồn không xác thực, khuyết phiên bản hoặc cần cách ly.
- Lần đối soát gần nhất hoàn tất ở đâu, phạm vi nào còn chưa quét.
- Số ứng viên chờ bằng chứng và tuổi trạng thái chưa rõ.
- Khả năng truy cập nguồn quyền, phê duyệt, sổ tiền và dữ liệu nhà cung cấp.

Khi detector mất dữ liệu, ghi nhận sự cố quan sát riêng. Không biến lỗi truy cập kho bằng chứng thành “không có phê duyệt”, cũng không biến nó thành “mọi thao tác đều hợp lệ”.

Cần chính sách cho công việc rủi ro cao trong lúc quan sát suy giảm. Việc giữ lại, tạm dừng hoặc tiếp tục có giới hạn phải do thiết kế và quy trình vận hành quy định; detector không tự có quyền bỏ kiểm soát hoặc khóa toàn hệ thống.

Sau phục hồi, nạp lại từ checkpoint hoặc đối soát khoảng thiếu, có chống trùng và giới hạn tải. Chỉ đánh dấu khôi phục đầy đủ khi xác định tồn đọng đã được xử lý, không chỉ khi process chạy lại.

## 14. Xác minh ban đầu và chuyển giao sự cố

Người trực hoặc quy trình tự động cần trả lời:

1. Quy tắc và phiên bản có đúng với sản phẩm, tenant và thời điểm thao tác không?
2. Bằng chứng là request, quyết định hay hiệu lực đã commit? Có hiệu lực ngoài cần xác nhận không?
3. Chủ thể, đối tượng, số tiền, tiền tệ và operation ID đã được ràng buộc đúng nguồn chưa?
4. Có giao trùng, replica trễ, khuyết sự kiện hoặc quét dở làm sai quan sát không?
5. Có ngoại lệ hoặc ủy quyền hợp lệ cho chính thao tác đó không?
6. Còn thao tác qua cùng đường lỗi có thể tạo hiệu lực không, và phạm vi nào bị ảnh hưởng?

Lưu bằng chứng cần thiết, kiểm soát truy cập và ghi rõ nguồn, thời điểm thu thập, phạm vi. Không tùy tiện sửa bản ghi gốc để làm con số khớp nhau.

Detector có thể đề xuất bảo vệ theo phạm vi, như giữ yêu cầu hoàn mới của đường lỗi hoặc ngăn bước thực hiện đơn tiếp theo. Thực thi phải theo quyền và playbook được phê duyệt. Không tự hoàn tác mọi giao dịch trong cảnh báo khi trạng thái ngoài còn chưa rõ.

Bàn giao cần bất biến bị phá, mức chắc chắn, mốc thời gian, đối tượng, bằng chứng, hành động đã làm và câu hỏi chưa giải quyết. Không kết luận “đã bị tấn công” chỉ từ một chỉ số tăng đột biến.

Phát hiện xong chưa đồng nghĩa xử lý xong. Khôi phục dữ liệu, giải quyết nghĩa vụ, điều tra nguyên nhân và đóng sự cố cần tiêu chí riêng trong quy trình ứng phó.

## 15. Kiểm thử detector bằng kịch bản có chủ đích

Bộ kiểm thử cần tạo được bằng chứng vi phạm, chứng minh đường truyền phát hiện hoạt động và giữ ca hợp lệ để tránh tối ưu theo hướng cảnh báo tất cả.

| Mã | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| DET-01 | Hiệu lực thiếu phê duyệt đúng revision | Phát hiện thiếu căn cứ; xác nhận khi nguồn đủ đầy |
| DET-02 | Duyệt rồi sửa nội dung trước thực hiện | Nhận ra phê duyệt cũ không bao phủ nội dung mới |
| DET-03 | Chấp nhận giá client sửa ngoài báo giá hợp lệ | Phát hiện sai căn cứ giá từ dữ liệu server |
| DET-04 | Hai worker tạo nghĩa vụ hoàn vượt khả năng hoàn | Có trường hợp BR-06 với số tiền và thao tác liên quan |
| DET-05 | Giao lại sự kiện detector đã xử lý | Không nhân đôi hiệu lực đánh giá hoặc thông báo ngoài chính sách |
| DET-06 | Hai hiệu lực cho cùng operation ID | Giữ bằng chứng cả hai, nhận ra vi phạm idempotency |
| DET-07 | Thanh toán hợp lệ tới trễ trong giới hạn | Không xác nhận sai chỉ vì thứ tự nhận |
| DET-08 | Mất đoạn sự kiện hoặc không truy cập nguồn quyền | Báo thiếu độ bao phủ, không kết luận vô căn cứ |
| DET-09 | Thu hồi quyền sau thao tác hợp lệ | Đánh giá quyền theo thời điểm hành động |
| DET-10 | Chuyển trạng thái sai rồi sửa trạng thái hiện tại | Vẫn tìm được chuyển đổi sai và hiệu lực liên quan |
| DET-11 | Detector chết sau lưu ứng viên, trước ACK | Phục hồi không mất ứng viên hoặc gây bão cảnh báo |
| DET-12 | Ngoại lệ hết hạn hoặc tác động tăng | Tiếp tục phát hiện, cập nhật hoặc nâng mức theo chính sách |

Ca đối chứng gồm giảm giá hợp lệ, thanh toán nhiều đợt đúng mô hình, ủy quyền liên tổ chức còn hiệu lực, request bị chặn hoàn toàn và thao tác rollback chưa tạo hiệu lực. Đáp án dựa trên fixture cụ thể, không lấy chính logic production có thể sai làm oracle.

Đặc tả minh họa cho DET-04:

```text
fixture:
    capturedCapacity = 1000000 VND
    committedSuccessfulRefunds = [700000, 200000, 200000] VND
    activeReservations = []
    providerEvidence = confirms three distinct successful operations

run:
    publish committed events, including one duplicate delivery
    wait until fixture scope is evaluated and alert delivery completes

assert:
    one active violation episode for BR_06 and payment P17
    succeededAmount = 1100000 VND
    excessAmount = 100000 VND
    evidence references all three operations
    evidence distinguishes provider confirmation from internal state
    duplicate delivery creates no extra notification beyond policy
```

Đây là dữ liệu cố tình vi phạm trong môi trường kiểm thử được kiểm soát. Nếu kiểm soát phòng ngừa đúng và không cho tạo trạng thái sai qua API thường, có thể nạp fixture hoặc sự kiện thử qua bộ tích hợp chuyên dụng. Không nới quyền hoặc tắt kiểm soát ở môi trường vận hành để thử detector.

Điểm chờ cần thời hạn và điều kiện kết thúc rõ. Hàng đợi trống chưa đủ nếu còn tác vụ đã lấy thông điệp, đối soát đang chạy hoặc thông báo chưa giao xong. Hết hạn mà chưa đủ bằng chứng phải báo chưa kết luận hoặc lỗi theo hợp đồng test.

Khi phát lại dữ liệu lịch sử để thử quy tắc mới, cô lập việc gửi cảnh báo và mọi hành động có hiệu lực. So sánh kết quả dự kiến trước khi bật chuyển giao vận hành, đồng thời giữ khả năng phát hiện vi phạm thật mới phát sinh.

## 16. Đo hiệu quả và cải tiến quy tắc

Chỉ số hữu ích gồm thời gian từ hiệu lực tới phát hiện, độ trễ xác minh, số vi phạm đã xác nhận, số ứng viên là hành vi hợp lệ, tuổi trường hợp chưa đủ bằng chứng và phạm vi dữ liệu chưa đánh giá.

Chỉ so sánh thời gian khi mốc và đồng hồ có ý nghĩa phù hợp. Tách độ trễ nguồn phát, vận chuyển, đánh giá và chuyển giao để biết đoạn cần cải thiện.

Không suy ra tỷ lệ bỏ sót từ số cảnh báo đã thấy. Muốn đánh giá khả năng phát hiện cần sự cố đã biết, kịch bản kiểm thử, đối soát độc lập và đánh giá độ bao phủ. Cảnh báo giảm có thể là cải thiện hoặc mất dữ liệu.

Mỗi quy tắc nên có người sở hữu, lý do tồn tại, nguồn bằng chứng, phiên bản, ca hợp lệ đi kèm và cách xử lý khi nguồn không sẵn sàng. Khi sản phẩm đổi state machine, giá hoặc quyền, xem lại hợp đồng phát hiện trong cùng đợt thay đổi.

Bài học từ sự cố cần trở thành fixture hồi quy và cải thiện bằng chứng. Nếu điều tra thường không biết thao tác dựa vào phê duyệt nào, chỉ tăng độ nhạy của ngưỡng không giải quyết được thiếu hụt.

## 17. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| Chỉ theo dõi HTTP 5xx hoặc exception | Bỏ sót thao tác thành công nhưng sai nghiệp vụ | Theo dõi hiệu lực và bất biến |
| Coi request bị chặn là thiệt hại đã xảy ra | Tăng nhiễu, sai tác động | Tách nỗ lực, quyết định và hiệu lực |
| Chỉ đọc trạng thái hiện tại | Bỏ qua chuyển đổi sai đã sửa lại | Giữ lịch sử và hiệu lực liên quan |
| Xét thao tác cũ bằng quyền hoặc giá hiện tại | Sai kết luận do chính sách đổi | Truy lại căn cứ theo thời điểm |
| Cộng tiền khác loại hoặc đếm lặp thao tác | Tổng số không có ý nghĩa | Nhóm đúng phạm vi, trạng thái rõ |
| Tin nguồn hoặc tenant tự khai | Giả mạo hoặc né quy tắc | Ràng buộc với dữ liệu đáng tin |
| Đếm lần giao như số hiệu lực | Cảnh báo trùng khi giao lại | Tách event ID, operation ID và hiệu lực |
| Xóa ứng viên khi hết cửa sổ nhưng còn thiếu dữ liệu | Biến mất quan sát thành an toàn giả | Giữ trạng thái thiếu bằng chứng, đối soát bổ sung |
| Tắt cảnh báo lâu dài để giảm nhiễu | Bỏ sót vi phạm tái diễn | Ngoại lệ có phạm vi và thời hạn |
| Tự sửa dữ liệu từ tín hiệu yếu | Thêm hiệu lực sai hoặc mất chứng cứ | Xác minh, thực thi theo quyền và playbook |

## 18. Danh sách kiểm tra trước vận hành

- Quy tắc nêu rõ bất biến, đối tượng, phạm vi, thời điểm và nguồn chính sách.
- Bằng chứng phân biệt request, quyết định, commit và xác nhận hiệu lực ngoài.
- Chủ thể, tenant, tài nguyên, giá và phê duyệt không chỉ dựa vào điều người gọi khai.
- Có lịch sử chuyển trạng thái và căn cứ quyền tại thời điểm hành động.
- Detector chịu giao trùng, đảo thứ tự nhận, thiếu dữ liệu và restart.
- Gom cảnh báo giữ được bằng chứng mới, tác động tăng và đợt tái diễn.
- Cửa sổ chờ, mốc chốt, trạng thái chưa rõ và điều kiện kết thúc cụ thể.
- Cảnh báo chỉ rõ mong đợi, quan sát và bước xác minh tiếp.
- Có quan sát sức khỏe detector, độ trễ, độ bao phủ và tồn đọng đối soát.
- Đã thử vi phạm có chủ đích, hành vi hợp lệ, lỗi thu thập và phục hồi sau crash.
- Ngoại lệ có người cấp, phạm vi, thời hạn và khả năng truy lại.
- Hành động bảo vệ, khôi phục tuân theo quyền vận hành và tiêu chí riêng.

Phát hiện sự cố quy tắc nghiệp vụ có giá trị khi nối được điều kiện bị phá với đối tượng, hiệu lực và bằng chứng có thể kiểm tra. Mục tiêu là nhận ra tổn hại hoặc nguy cơ đúng lúc, đủ rõ để ứng phó, đồng thời biết khi nào dữ liệu chưa cho phép kết luận.
