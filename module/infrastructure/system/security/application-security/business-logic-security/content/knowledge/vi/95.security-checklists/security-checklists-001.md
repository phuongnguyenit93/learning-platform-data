# New feature security checklist

## 1. Mục đích và cách sử dụng

Một tính năng mới có thể xác thực người dùng đúng, kiểm tra định dạng đầu vào đầy đủ và vẫn cho phép gian lận. Ví dụ: người mua tự gửi giá thấp hơn, người tạo yêu cầu tự phê duyệt, nhân viên hoàn tiền nhiều hơn số đã thu hoặc hai yêu cầu đồng thời cùng tiêu một số dư. Đây là lỗi bảo mật logic nghiệp vụ: hệ thống cho phép một kết quả trái với quy tắc mà doanh nghiệp phải bảo vệ.

Checklist này dùng khi thiết kế, triển khai và kiểm tra một tính năng mới trong phạm vi **Business Logic Security**. Mục tiêu là chuyển yêu cầu nghiệp vụ thành những điều kiện mà phía máy chủ thực sự cưỡng chế, kể cả khi người gọi bỏ qua giao diện, thay đổi thứ tự thao tác, gọi lại API hoặc gửi nhiều yêu cầu đồng thời.

Checklist không thay thế việc phân tích nghiệp vụ. Mỗi mục đánh dấu hoàn thành cần gắn với quy tắc cụ thể, vị trí thực thi và bằng chứng kiểm thử. Một dấu tích không có bằng chứng chưa đủ để kết luận tính năng an toàn.

### 1.1. Thông tin cần ghi cho từng tính năng

| Nội dung | Câu hỏi cần trả lời |
|---|---|
| Tính năng và hành động | Người dùng đang đặt hàng, duyệt chi, đổi gói, chuyển tiền hay hoàn tiền? |
| Tài sản cần bảo vệ | Tiền, tồn kho, hạn mức, quyền sử dụng, dữ liệu của khách hàng hay trạng thái phê duyệt? |
| Chủ thể | Ai được thao tác, thuộc tổ chức nào, với vai trò và quan hệ nào đối với tài nguyên? |
| Ranh giới tin cậy | Dữ liệu nào đến từ trình duyệt, ứng dụng di động, dịch vụ khác hoặc callback của đối tác? |
| Quy tắc bất biến | Điều gì phải luôn đúng trước và sau khi hành động hoàn tất? |
| Luồng trạng thái | Những chuyển trạng thái nào hợp lệ, do ai thực hiện, với điều kiện gì? |
| Phạm vi nguyên tử | Những thay đổi nào phải cùng thành công hoặc cùng thất bại? |
| Tác động bên ngoài | Có gọi cổng thanh toán, gửi hàng, cấp quyền hoặc phát sự kiện không? |
| Chủ sở hữu và bằng chứng | Ai xác nhận quy tắc, ai triển khai, kiểm thử nào chứng minh quy tắc được giữ? |

### 1.2. Quy ước đánh dấu

- `[ ]`: chưa hoàn tất hoặc chưa có bằng chứng.
- `[x]`: đã áp dụng và có thể chỉ ra bằng chứng.
- `N/A — lý do`: không áp dụng, kèm giải thích và người xác nhận.

Không đánh dấu `N/A` chỉ vì giao diện chưa cung cấp thao tác tương ứng. Kẻ lạm dụng có thể gọi trực tiếp endpoint, dùng phiên bản API cũ hoặc thao tác thông qua một luồng khác.

## 2. Ví dụ xuyên suốt: yêu cầu hoàn tiền có phê duyệt

Giả sử hệ thống cho phép nhân viên lập yêu cầu hoàn tiền cho một đơn hàng đã thanh toán. Người duyệt phải khác người tạo. Khi đã duyệt, hệ thống tạo lệnh hoàn tiền và gửi sang cổng thanh toán.

Một số quy tắc cần bảo vệ:

1. Người thao tác có quyền đối với đúng đơn hàng và đúng tổ chức.
2. Chỉ đơn hàng đủ điều kiện mới được lập yêu cầu hoàn tiền.
3. Số tiền hoàn phải dương và có cùng tiền tệ với giao dịch gốc.
4. Tổng tiền đã hoàn cộng các khoản đang giữ chỗ cho hoàn tiền không vượt quá số tiền đã thu.
5. Người tạo yêu cầu không được tự duyệt, kể cả khi có đồng thời hai vai trò.
6. Số tiền, giao dịch gốc và người hưởng không được âm thầm đổi sau khi phê duyệt.
7. Một hành động hoàn tiền chỉ tạo một tác động tài chính trong phạm vi cam kết xử lý trùng.
8. Timeout từ đối tác không được tự động hiểu là hoàn tiền thất bại.

Với một giao dịch có số tiền đã thu là `capturedAmount`, có thể biểu diễn điều kiện về hạn mức:

```text
refundedAmount >= 0
reservedRefundAmount >= 0

refundedAmount + reservedRefundAmount <= capturedAmount

Khi giữ chỗ cho yêu cầu mới có số tiền amount:
amount > 0
refundedAmount + reservedRefundAmount + amount <= capturedAmount
```

`reservedRefundAmount` là tổng tiền của các yêu cầu đã chiếm hạn mức nhưng chưa kết thúc. Phải định nghĩa rõ trạng thái nào được tính vào tổng này. Nếu chỉ tính các khoản đã hoàn thành, hai yêu cầu đang xử lý có thể cùng vượt qua kiểm tra và cùng hoàn tiền.

Các quy tắc trên là ví dụ. Từng sản phẩm cần xác định cách xử lý thanh toán một phần, nhiều lần thu tiền, phí, tranh chấp và tỷ giá nếu các trường hợp đó có trong phạm vi tính năng.

## 3. Checklist về phạm vi và mô hình lạm dụng

- [ ] Đã xác định mọi đường vào của tính năng: UI, REST API, tác vụ nền, import, webhook, công cụ quản trị và phiên bản API còn được hỗ trợ.
- [ ] Đã liệt kê tài sản có thể bị chiếm đoạt hoặc làm sai lệch.
- [ ] Đã mô tả chủ thể có động cơ lạm dụng: khách hàng, nhân viên, tài khoản bị chiếm hoặc dịch vụ tích hợp.
- [ ] Đã phân biệt thao tác hợp lệ một lần với chuỗi thao tác gây hại khi kết hợp.
- [ ] Đã xét việc gọi trực tiếp bước cuối, bỏ qua bước chuẩn bị hoặc đảo thứ tự gọi.
- [ ] Đã xét việc dùng dữ liệu cũ, giữ nhiều phiên, đổi vai trò hoặc đổi tổ chức giữa các bước.
- [ ] Đã xác định mức tổn thất có thể xảy ra trước khi hệ thống phát hiện.
- [ ] Đã ghi rõ những giả định bắt buộc phải được thực thi bằng kỹ thuật.

Một cách viết tình huống lạm dụng hữu ích:

> Với tư cách là nhân viên có quyền tạo yêu cầu, tôi muốn sửa mã yêu cầu trong lời gọi phê duyệt để duyệt yêu cầu thuộc tổ chức khác; nếu thành công, tôi có thể thực hiện hoàn tiền ngoài phạm vi được giao.

Mô tả này chỉ ra được chủ thể, khả năng sẵn có, thao tác tấn công và hậu quả. Câu “cần kiểm tra bảo mật API” chưa đủ cụ thể để thiết kế cơ chế bảo vệ.

## 4. Checklist về business invariants

**Business invariant** là điều kiện nghiệp vụ phải luôn đúng trong phạm vi đã xác định. Quy tắc nên có dạng có thể kiểm tra, thay vì chỉ là lời nhắc như “không được hoàn tiền sai”.

- [ ] Mỗi bất biến đã nêu rõ đối tượng, điều kiện và đại lượng liên quan.
- [ ] Quy tắc đã bao gồm cả giá trị biên: bằng không, âm, đúng hạn mức, vượt hạn mức và hết hạn.
- [ ] Đã xác định cách biểu diễn tiền, đơn vị và quy tắc làm tròn; không dùng số thực dấu phẩy động để biểu diễn trực tiếp giá trị tiền cần chính xác.
- [ ] Đã chỉ rõ dữ liệu nào có thẩm quyền để tính giá, chiết khấu, thuế, quyền lợi hoặc hạn mức.
- [ ] Bất biến được kiểm tra ở phía máy chủ cho mọi đường thay đổi dữ liệu.
- [ ] Quy tắc quan trọng được củng cố bằng ràng buộc dữ liệu phù hợp nếu cơ sở dữ liệu có thể biểu diễn được.
- [ ] Đã xét quy tắc liên quan nhiều bản ghi, nhiều yêu cầu đồng thời hoặc nhiều dịch vụ.
- [ ] Khi quy tắc không thể xác minh do phụ thuộc lỗi, hệ thống không mặc nhiên cho phép hành động tạo giá trị.
- [ ] Các ngoại lệ nghiệp vụ có điều kiện, quyền hạn và dấu vết riêng.

### 4.1. Biến yêu cầu mơ hồ thành điều kiện kiểm tra

| Yêu cầu mơ hồ | Quy tắc có thể thực thi | Nơi cần bảo vệ |
|---|---|---|
| Không hoàn quá số đã trả | Tổng đã hoàn + đang giữ chỗ + khoản mới không vượt tiền đã thu | Cập nhật hạn mức trong transaction |
| Chỉ quản lý được duyệt | Chủ thể có quyền duyệt trên tài nguyên và đáp ứng quy tắc khác người tạo | Chính sách quyền trong hành động duyệt |
| Không sửa yêu cầu đã duyệt | Thay đổi trường ảnh hưởng quyết định phải bị từ chối hoặc tạo phiên bản cần duyệt lại | API sửa và luồng phê duyệt |
| Không hoàn tiền hai lần | Mỗi thao tác tài chính có định danh ổn định và được chống trùng xuyên suốt luồng | API, bản ghi thực thi và tích hợp đối tác |
| Chỉ dùng mã giảm giá hợp lệ | Đúng chủ thể, thời hạn, phạm vi sản phẩm và hạn mức sử dụng | Tính giá và ghi nhận sử dụng |

Một `CHECK` trên một hàng có thể bảo vệ điều kiện như `amount > 0`. Điều kiện tổng của nhiều hàng thường cần thêm cách phối hợp cập nhật, chẳng hạn khóa bản ghi tổng hợp hoặc cập nhật có điều kiện. Không suy ra rằng một constraint đơn giản đã bảo vệ được mọi bất biến liên bản ghi.

## 5. Checklist về dữ liệu đầu vào và giá trị do máy chủ quyết định

- [ ] API chỉ nhận các trường mà người gọi thực sự được phép chọn.
- [ ] Không ánh xạ toàn bộ request trực tiếp vào entity có các trường quyền hạn, giá, trạng thái hoặc kết quả phê duyệt.
- [ ] Tổng tiền, giá cuối cùng, chiết khấu và hạn mức được tính hoặc xác minh từ nguồn có thẩm quyền.
- [ ] Tenant, người tạo và vai trò được lấy từ ngữ cảnh xác thực và chính sách phía máy chủ; dữ liệu client gửi chỉ là tham chiếu cần kiểm tra.
- [ ] Mọi ID tham chiếu đều được kiểm tra quan hệ: đơn hàng có thuộc khách hàng, dòng hàng có thuộc đơn hàng, giao dịch có thuộc tổ chức đó không.
- [ ] Kiểm tra định dạng được kết hợp với kiểm tra ý nghĩa nghiệp vụ.
- [ ] Đã xử lý trường không biết, trường lặp hoặc biểu diễn mơ hồ theo một chính sách nhất quán.
- [ ] Các phép chuyển đổi đơn vị, tiền tệ, ngày giờ và làm tròn có quy tắc rõ ràng.
- [ ] Bản báo giá, token thao tác hoặc dữ liệu có chữ ký được kiểm tra đúng phạm vi, thời hạn và điều kiện sử dụng lại.

Ví dụ, request tạo yêu cầu hoàn tiền có thể chứa:

```json
{
  "orderId": "ord-410",
  "amount": "250000",
  "currency": "VND",
  "reasonCode": "RETURN_ACCEPTED"
}
```

Máy chủ vẫn phải xác minh đơn hàng, giao dịch gốc, tiền tệ và số dư được phép hoàn. Các trường như `approvedBy`, `status`, `tenantId` hoặc `refundableBalance` không được trở thành quyết định có thẩm quyền chỉ vì xuất hiện trong JSON.

Với tính năng mua hàng, nếu client gửi `unitPrice` để hiển thị hoặc xác nhận báo giá, máy chủ cần có chính sách giá rõ ràng. Có thể tính lại tại thời điểm đặt hàng hoặc dùng báo giá được ràng buộc với sản phẩm, chủ thể, tiền tệ và thời hạn. Chữ ký hợp lệ chỉ chứng minh dữ liệu chưa bị sửa theo cơ chế ký; nó không tự chứng minh báo giá còn được phép sử dụng.

## 6. Checklist về state machine và phê duyệt

Một state machine giúp mô tả trạng thái hợp lệ, nhưng chỉ có ích khi mỗi hành động thực sự cưỡng chế điều kiện chuyển trạng thái. Không để client chọn trạng thái đích tùy ý.

- [ ] Đã liệt kê các trạng thái và ý nghĩa nghiệp vụ của từng trạng thái.
- [ ] Mỗi hành động có tập trạng thái nguồn và trạng thái đích được phép.
- [ ] Mỗi chuyển trạng thái có điều kiện về chủ thể, dữ liệu, hạn mức và thời gian.
- [ ] Không thể bỏ qua bước phê duyệt bằng cách gọi thẳng API thực thi.
- [ ] Người phê duyệt xem và phê duyệt đúng phiên bản dữ liệu sẽ được thực thi.
- [ ] Sửa dữ liệu quan trọng sau phê duyệt làm mất hiệu lực phê duyệt hoặc bị từ chối.
- [ ] Đã định nghĩa hành vi của yêu cầu lặp, yêu cầu đến muộn và thao tác trên trạng thái kết thúc.
- [ ] Callback chỉ được phép tạo các chuyển trạng thái đã định nghĩa.
- [ ] Đã có cách xử lý kết quả bên ngoài chưa xác định và đối soát lại.
- [ ] Các luồng quản trị, hỗ trợ và khôi phục cũng tuân thủ quy tắc chuyển trạng thái.

### 6.1. Bảng chuyển trạng thái mẫu

| Hành động | Trạng thái nguồn | Điều kiện chính | Trạng thái đích |
|---|---|---|---|
| Gửi yêu cầu | `DRAFT` | Đủ dữ liệu, đúng quyền, đơn hàng đủ điều kiện | `PENDING_APPROVAL` |
| Duyệt | `PENDING_APPROVAL` | Khác người tạo, đúng quyền, đúng phiên bản, giữ được hạn mức | `APPROVED` |
| Từ chối | `PENDING_APPROVAL` | Đúng quyền, có lý do theo chính sách | `REJECTED` |
| Lập lệnh thực thi | `APPROVED` | Khoản giữ chỗ còn hợp lệ, chưa có lệnh tương ứng | `PROCESSING` |
| Xác nhận thành công | `PROCESSING` hoặc `UNKNOWN` | Kết quả đối tác đã được xác minh và khớp giao dịch | `SUCCEEDED` |
| Xác nhận không thực hiện | `PROCESSING` hoặc `UNKNOWN` | Có bằng chứng kết thúc không tạo hoàn tiền | `FAILED` |
| Ghi nhận chưa rõ kết quả | `PROCESSING` | Timeout hoặc kết quả chưa đủ kết luận | `UNKNOWN` |

Trong ví dụ này, giữ chỗ hạn mức diễn ra khi duyệt. Khi thành công, khoản giữ chỗ được chuyển sang tổng đã hoàn trong cùng một cập nhật nguyên tử. Khi có bằng chứng thất bại dứt điểm, hệ thống mới giải phóng khoản giữ chỗ. Khi kết quả còn `UNKNOWN`, không giải phóng hạn mức chỉ vì đã hết thời gian chờ HTTP.

Nếu một hệ thống chọn giữ chỗ ở bước khác, cần ghi rõ thời điểm chiếm và trả hạn mức, hành vi hết hạn cùng tác động của các yêu cầu đang chạy. Không trộn hai chính sách trong cùng luồng.

### 6.2. Ràng buộc quyết định phê duyệt

Một quyết định phê duyệt có thể gắn với:

```text
requestId
requestVersion
amount
currency
sourcePaymentId
beneficiaryReference
requesterId
approverId
approvedAt
```

Danh sách trường phải phản ánh đúng dữ liệu ảnh hưởng quyết định. Nếu số tiền hoặc người hưởng thay đổi mà quyết định vẫn dùng được, hệ thống đang cho phép thay nội dung sau khi đã được chấp thuận.

## 7. Checklist về quyền theo đối tượng và tenant

Kiểm tra vai trò trả lời câu hỏi “người này có loại quyền nào”. Quyền theo đối tượng còn phải trả lời “quyền đó có áp dụng cho tài nguyên cụ thể và hành động cụ thể này không”.

- [ ] Mỗi thao tác đọc, tạo, sửa, duyệt, hủy và thực thi đều có kiểm tra quyền phù hợp.
- [ ] Kiểm tra quyền sử dụng danh tính đã xác thực và quan hệ với tài nguyên.
- [ ] Tenant được ràng buộc trong truy vấn và được kiểm tra trên tài nguyên liên quan.
- [ ] Đã xét việc thay ID trên URL, query, body, header và danh sách ID.
- [ ] Batch API kiểm tra quyền cho từng đối tượng và có chính sách thất bại rõ ràng.
- [ ] Quyền xem không tự động trở thành quyền sửa hoặc quyền duyệt.
- [ ] Quy tắc tách người tạo và người duyệt được kiểm tra bằng danh tính, không chỉ bằng tên vai trò.
- [ ] Quyền được đánh giá lại tại hành động nhạy cảm nếu có thể bị thu hồi giữa các bước.
- [ ] Công việc nền nhận đủ ngữ cảnh nghiệp vụ và xác minh điều kiện cần thiết trước khi thực thi.
- [ ] Tài khoản quản trị hoặc dịch vụ có phạm vi rõ ràng; thao tác vượt phạm vi thông thường có dấu vết.

Ví dụ kiểm tra cần kết hợp nhiều điều kiện:

```text
canApprove(actor, refund) =
    actor thuộc tenant của refund
    AND actor có quyền refund.approve trên phạm vi tài nguyên
    AND actor.id khác refund.requesterId
    AND refund đang ở PENDING_APPROVAL
    AND phiên bản được duyệt khớp phiên bản hiện tại
```

ID khó đoán giúp giảm khả năng dò tìm, nhưng không thay thế các điều kiện này. Một người có thể lấy ID hợp lệ từ lịch sử, log, liên kết chia sẻ hoặc dữ liệu được phép xem.

Với thao tác thay chủ sở hữu hoặc chuyển tài nguyên sang tổ chức khác, cần kiểm tra cả quyền chuyển đi lẫn quyền nhận vào. Chỉ kiểm tra tài nguyên trước hoặc sau chuyển có thể để lại khoảng trống.

## 8. Checklist về transaction, đồng thời và TOCTOU

**TOCTOU** là khoảng cách giữa lúc kiểm tra điều kiện và lúc sử dụng kết quả kiểm tra. Ví dụ: hai yêu cầu cùng đọc số dư hoàn tiền còn 300.000 VND, rồi mỗi yêu cầu giữ 200.000 VND.

- [ ] Các thao tác đọc điều kiện và ghi thay đổi quan trọng đã được xem xét như một đơn vị.
- [ ] Đã xác định ràng buộc có thể bị phá khi hai request chạy đồng thời.
- [ ] Việc kiểm tra và thay đổi được thực hiện nguyên tử bằng cơ chế phù hợp.
- [ ] Nếu dùng khóa, mọi luồng cạnh tranh cùng tuân thủ phạm vi và thứ tự khóa đã chọn.
- [ ] Nếu dùng optimistic locking, xung đột được phát hiện và xử lý trước khi tạo tác động ngoài.
- [ ] Nếu retry transaction, toàn bộ điều kiện liên quan được đọc và đánh giá lại.
- [ ] Có ràng buộc duy nhất cho các định danh nghiệp vụ phải duy nhất.
- [ ] Không giả định cache hoặc bản sao đọc luôn phản ánh trạng thái mới nhất cho quyết định cấp tiền hay cấp quyền.
- [ ] Hành động thất bại không để lại bản ghi, hạn mức hoặc trạng thái dở dang trái quy tắc.
- [ ] Đã kiểm thử cạnh tranh bằng nhiều kết nối hoặc tiến trình theo điều kiện gần với môi trường sử dụng.

### 8.1. Cập nhật hạn mức có điều kiện

Một cách tiếp cận là lưu số tiền đã hoàn và số tiền giữ chỗ trên bản ghi thanh toán, rồi cập nhật có điều kiện. Ví dụ SQL minh họa với tham số bind:

```sql
UPDATE payment
SET reserved_refund_amount = reserved_refund_amount + :amount,
    version = version + 1
WHERE id = :payment_id
  AND tenant_id = :tenant_id
  AND currency = :currency
  AND status = 'CAPTURED'
  AND :amount > 0
  AND refunded_amount + reserved_refund_amount + :amount
      <= captured_amount;
```

Chỉ khi cập nhật đúng một hàng mới tiếp tục ghi khoản giữ chỗ tương ứng. Cập nhật hạn mức, ghi khoản giữ chỗ, chuyển trạng thái yêu cầu và ghi sự kiện cần thiết phải thuộc cùng transaction; nếu một bước thất bại, rollback toàn bộ.

Đây là minh họa cơ chế giữ hạn mức, không phải toàn bộ hàm duyệt. Hàm duyệt còn phải kiểm tra quyền, trạng thái nguồn và phiên bản của yêu cầu. Có thể khóa bản ghi yêu cầu trước khi xử lý, hoặc dùng chuyển trạng thái có điều kiện để bảo đảm hai lệnh duyệt không cùng chiếm hạn mức cho một yêu cầu.

Một phép kiểm tra trong Java rồi gọi `save()` không tự tạo ra bảo đảm tương đương. Hiệu lực của khóa, mức cô lập và cách ORM flush dữ liệu phải được xác định theo triển khai thực tế.

### 8.2. Tác động qua nhiều dịch vụ

Không giữ transaction cơ sở dữ liệu mở trong lúc chờ cổng thanh toán để cố tạo cảm giác nguyên tử. Một phương án thường dùng:

1. Trong transaction cục bộ, tạo lệnh hoàn tiền, giữ hạn mức và ghi outbox.
2. Worker đọc outbox và gửi lệnh với định danh chống trùng ổn định.
3. Ghi nhận kết quả đã xác minh, rồi cập nhật khoản giữ chỗ và trạng thái.
4. Đối soát các kết quả chưa rõ; xử lý bù theo quy tắc nghiệp vụ khi cần.

Outbox giúp gắn việc thay đổi dữ liệu cục bộ với ý định phát sự kiện. Nó không tự ngăn phát trùng hoặc tự bảo đảm tác động bên ngoài chỉ xảy ra một lần. Consumer và tích hợp đối tác vẫn cần xử lý trùng.

## 9. Checklist về idempotency, retry và replay

**Idempotency** là khả năng xử lý lại cùng một thao tác mà không tạo thêm tác động nghiệp vụ ngoài cam kết. Nó không đồng nghĩa với việc mọi request có nội dung giống nhau đều là cùng một thao tác.

- [ ] Đã chỉ rõ hành động nào cần idempotency: đặt hàng, trừ tiền, hoàn tiền, giữ tồn kho hoặc cấp quyền.
- [ ] Khóa idempotency có phạm vi theo tenant, chủ thể hoặc client đã xác thực và loại thao tác thích hợp.
- [ ] Một khóa được ràng buộc với nội dung có ý nghĩa nghiệp vụ của request.
- [ ] Cùng khóa nhưng khác nội dung bị từ chối theo hợp đồng API.
- [ ] Hai request đồng thời cùng khóa không cùng tạo tác động.
- [ ] Bản ghi idempotency được phối hợp nguyên tử với thay đổi nghiệp vụ cục bộ.
- [ ] Đã xác định phản hồi khi thao tác đang chạy, đã thành công, thất bại hoặc chưa rõ kết quả.
- [ ] Retry sau timeout có cách tìm lại kết quả hoặc tiếp tục đúng thao tác cũ.
- [ ] Thời hạn giữ khóa phù hợp với thời gian retry, đối soát và rủi ro gọi lại.
- [ ] Khóa gửi sang hệ thống ngoài ổn định qua các lần gửi lại của cùng một lệnh.
- [ ] Có định danh nghiệp vụ và ràng buộc duy nhất để bảo vệ trước việc đổi khóa nhằm lặp cùng hành động bị cấm.
- [ ] Truy xuất kết quả cũ vẫn kiểm tra danh tính và quyền hiện tại; khóa không trở thành vé đọc dữ liệu.

### 9.1. Hợp đồng xử lý mẫu

| Tình huống | Hành vi cần định nghĩa |
|---|---|
| Khóa mới, request hợp lệ | Ghi nhận thao tác và xử lý trong phạm vi nguyên tử đã chọn |
| Cùng khóa, cùng nội dung, đang chạy | Trả trạng thái đang xử lý hoặc phản hồi xung đột có hướng dẫn retry |
| Cùng khóa, cùng nội dung, đã xong | Trả lại kết quả theo hợp đồng, sau khi kiểm tra quyền |
| Cùng khóa, khác nội dung | Từ chối; không diễn giải thành thao tác mới |
| Timeout khi gọi đối tác | Giữ định danh thao tác cũ, tra cứu hoặc gửi lại theo cam kết của đối tác |
| Khóa đã hết thời hạn lưu | Áp dụng chính sách công bố rõ; không tuyên bố chống trùng vô thời hạn |

Dấu vân tay request nên được tính từ biểu diễn chuẩn hóa của dữ liệu nghiệp vụ sau khi phân tích hợp lệ. Băm nguyên văn JSON có thể coi hai cách sắp xếp trường tương đương là hai nội dung khác nhau. Ngược lại, bỏ sót số tiền hoặc người hưởng khỏi dấu vân tay có thể coi hai thao tác khác nhau là cùng một thao tác.

Khóa do client cung cấp không phải bằng chứng về quyền. Một request gửi lại vẫn phải đi qua xác thực và kiểm tra quyền cần thiết.

### 9.2. Idempotency khác chống lạm dụng hạn mức

Nếu một người đổi khóa ở mỗi lần gửi, cơ chế idempotency theo khóa có thể coi đó là các thao tác mới. Vì vậy:

- “Mỗi đơn hàng chỉ có một lần nhận ưu đãi này” cần ràng buộc theo đơn hàng và chương trình ưu đãi.
- “Tổng hoàn tiền không vượt số đã thu” cần bảo vệ hạn mức nguyên tử.
- “Mỗi yêu cầu đã duyệt chỉ có một lệnh hoàn tiền” cần định danh lệnh duy nhất theo yêu cầu hoặc phiên bản được phép thực thi.

Không dùng idempotency key để thay thế tất cả các quy tắc này.

## 10. Checklist về webhook, tác vụ nền và tích hợp

- [ ] Callback được xác thực theo cơ chế của đối tác; trạng thái thành công không chỉ dựa vào dữ liệu client chuyển tiếp.
- [ ] Mã giao dịch, đơn hàng, số tiền, tiền tệ và đối tác được đối chiếu với lệnh nội bộ.
- [ ] Sự kiện trùng được xử lý bằng định danh phù hợp với phạm vi của bên gửi.
- [ ] Việc ghi nhận sự kiện đã xử lý gắn nguyên tử với cập nhật nghiệp vụ cục bộ.
- [ ] Sự kiện đến sai thứ tự không làm lùi trạng thái một cách không hợp lệ.
- [ ] Worker retry cùng một công việc không tạo thêm tác động tài chính hoặc cấp quyền.
- [ ] Timeout, lỗi tạm thời, từ chối dứt điểm và kết quả chưa xác định được phân biệt.
- [ ] Đã có quy trình đối soát khi trạng thái nội bộ khác với đối tác.
- [ ] Xử lý thủ công có kiểm tra quyền, lý do, bằng chứng và audit trail.
- [ ] Thông báo gửi người dùng không được dùng thay bằng chứng giao dịch đã hoàn tất.

Ví dụ, callback `SUCCEEDED` đến hai lần không được cộng tiền hoàn hai lần. Một callback cũ thông báo đang xử lý đến sau thành công không được chuyển trạng thái từ `SUCCEEDED` về `PROCESSING`.

Nếu đối tác có thể điều chỉnh hoặc đảo giao dịch sau đó, phải mô hình hóa sự kiện điều chỉnh riêng theo hợp đồng nghiệp vụ. Không chỉ bỏ qua mọi sự kiện mới vì tài nguyên đang ở trạng thái được gọi là “kết thúc”.

## 11. Checklist về chống lạm dụng chức năng hợp lệ

Một chuỗi hành động có thể hợp lệ ở cấp từng request nhưng gây hại ở cấp tổng thể. Ví dụ: tạo nhiều tài khoản để nhận thưởng, giữ rồi hủy tồn kho liên tục, chia nhỏ giao dịch để tránh ngưỡng duyệt hoặc thử mã ưu đãi hàng loạt.

- [ ] Đã xác định tài nguyên khan hiếm và chi phí của mỗi thao tác.
- [ ] Hạn mức được chọn theo đúng ngữ nghĩa: tài khoản, khách hàng, tổ chức, chiến dịch, thiết bị hoặc phương thức thanh toán khi có căn cứ sử dụng.
- [ ] Các thao tác có thể chia nhỏ được đánh giá theo tổng trong khoảng thời gian phù hợp.
- [ ] Hạn mức có yêu cầu chính xác được kiểm tra và cập nhật nguyên tử.
- [ ] Chính sách giữ chỗ, hết hạn, hủy và khôi phục tài nguyên không tạo cách chiếm dụng kéo dài.
- [ ] Luồng hoàn tiền, hủy, đổi hàng hoặc đổi gói không tạo vòng lặp sinh lợi ngoài chính sách.
- [ ] Rate limit hỗ trợ kiểm soát tốc độ nhưng không thay thế hạn mức nghiệp vụ.
- [ ] Các ngoại lệ và quyền vượt hạn mức có kiểm soát, có thời hạn nếu cần và có dấu vết.

Ví dụ, quy tắc “giao dịch từ 10 triệu đồng cần hai người duyệt” có thể bị tránh bằng nhiều giao dịch nhỏ nếu ý định thực là kiểm soát tổng chi cho cùng một người hưởng. Cần xác nhận đúng yêu cầu với chủ sở hữu nghiệp vụ và xác định phạm vi cộng dồn; không tự đặt thêm hạn chế mà chưa rõ mục đích.

## 12. Checklist về audit, giám sát và khôi phục

- [ ] Ghi nhận chủ thể, tenant, hành động, tài nguyên, kết quả và thời điểm.
- [ ] Có thể liên kết request, quyết định phê duyệt, lệnh thực thi, sự kiện và giao dịch đối tác.
- [ ] Thay đổi quan trọng có trạng thái hoặc phiên bản trước và sau, trong giới hạn dữ liệu cần thiết.
- [ ] Lý do từ chối nghiệp vụ được phân loại để phát hiện mẫu lạm dụng.
- [ ] Không ghi bí mật xác thực, token đầy đủ hoặc dữ liệu nhạy cảm không cần thiết.
- [ ] Log và bản ghi nghiệp vụ có quyền truy cập, thời hạn lưu và biện pháp bảo vệ phù hợp.
- [ ] Đã định nghĩa cảnh báo cho các dấu hiệu đáng chú ý: tự duyệt, vượt hạn mức, xung đột khóa hoặc nhiều thao tác thất bại bất thường.
- [ ] Có thể tạm dừng phần tạo tác động nhạy cảm khi phát hiện vấn đề mà vẫn bảo toàn dữ liệu phục vụ điều tra và đối soát.
- [ ] Khôi phục, replay hoặc chạy lại job có kiểm tra trùng và không phá bất biến.
- [ ] Đã phân biệt bản ghi nghiệp vụ cần độ bền với log vận hành có thể được lấy mẫu.

Một dòng log “refund successful” không chứng minh được ai đã duyệt đúng số tiền nào, trên phiên bản nào và tác động bên ngoài nào đã xảy ra. Những câu hỏi này cần được trả lời bằng dữ liệu có thể liên kết và đối chiếu.

## 13. Ma trận kiểm thử tình huống tấn công logic

Các tình huống dưới đây là đầu vào cho kiểm thử tính năng. Phản hồi HTTP chỉ là một phần bằng chứng; cần xác nhận trạng thái dữ liệu, số dư, lệnh ngoài và sự kiện liên quan.

| Nhóm | Thao tác thử | Kết quả cần quan sát |
|---|---|---|
| Sửa giá trị | Đổi số tiền thành 0, âm hoặc vượt số được hoàn | Từ chối; không thay đổi hạn mức hay tạo lệnh |
| Trộn dữ liệu | Dùng giao dịch gốc của đơn hàng khác | Từ chối quan hệ không hợp lệ |
| Sai tenant | Thay ID bằng tài nguyên thuộc tenant khác | Không đọc được dữ liệu hoặc tạo tác động trái quyền |
| Sai đối tượng | Dùng tài nguyên của người khác trong cùng tenant khi không có quyền | Chính sách đối tượng được thực thi |
| Tự phê duyệt | Người tạo có thêm vai trò duyệt rồi duyệt yêu cầu của mình | Quy tắc tách người được giữ |
| Bỏ bước | Gọi thực thi trực tiếp từ `DRAFT` hoặc `PENDING_APPROVAL` | Không có lệnh hoàn tiền |
| Sửa sau duyệt | Đổi số tiền hoặc người hưởng sau phê duyệt | Bị từ chối hoặc phải duyệt phiên bản mới |
| Dữ liệu cũ | Duyệt phiên bản cũ sau khi yêu cầu đã được sửa | Phát hiện xung đột, không duyệt nhầm nội dung |
| Duyệt đồng thời | Hai người cùng duyệt một yêu cầu | Chỉ một chuyển trạng thái và một khoản giữ chỗ |
| Tranh hạn mức | Hai yêu cầu khác nhau cùng vượt phần hạn mức còn lại | Tổng giữ chỗ và đã hoàn vẫn trong giới hạn |
| Request trùng | Gửi cùng khóa và nội dung đồng thời | Một tác động; các phản hồi tuân thủ hợp đồng |
| Đổi payload | Giữ khóa nhưng tăng số tiền | Từ chối xung đột nội dung |
| Đổi khóa | Gửi nhiều khóa để thực thi lại cùng yêu cầu | Ràng buộc nghiệp vụ vẫn chặn lệnh không hợp lệ |
| Mất phản hồi | Cắt kết nối sau commit rồi gửi lại | Tìm được thao tác cũ, không thực thi thêm |
| Lỗi giữa chừng | Lỗi sau cập nhật hạn mức nhưng trước ghi yêu cầu | Transaction rollback, không còn khoản giữ chỗ mồ côi |
| Timeout đối tác | Đối tác đã nhận nhưng client không nhận phản hồi | Giữ trạng thái chưa rõ, đối soát bằng định danh cũ |
| Callback trùng | Gửi lại cùng sự kiện nhiều lần | Không cộng tổng hoàn hoặc phát quyền lợi thêm lần nữa |
| Callback sai thứ tự | Gửi sự kiện cũ sau thành công | Không lùi trạng thái trái quy tắc |
| Thu hồi quyền | Thu hồi quyền trước bước duyệt hoặc thực thi tương ứng | Áp dụng chính sách quyền tại thời điểm đã quy định |
| Job chạy lại | Chạy lại worker hoặc phát lại sự kiện | Giữ đúng số lệnh và tác động nghiệp vụ |
| Hạn mức cộng dồn | Chia giao dịch thành nhiều phần nhỏ | Kiểm soát tổng theo chính sách đã xác nhận |

### 13.1. Cách kiểm thử đồng thời có ý nghĩa

Không chỉ chạy một vòng lặp gửi request nối tiếp. Hãy tạo điều kiện hai hoặc nhiều tác vụ cùng vượt qua điểm có nguy cơ tranh chấp:

1. Chuẩn bị một giao dịch đã thu 300.000 VND, chưa có khoản hoàn hay giữ chỗ.
2. Tạo hai yêu cầu hoàn khác nhau, mỗi yêu cầu 200.000 VND.
3. Dùng các kết nối độc lập, phối hợp để hai lần duyệt tranh cùng hạn mức.
4. Chờ cả hai thao tác kết thúc.
5. Xác nhận tối đa một yêu cầu giữ được 200.000 VND.
6. Xác nhận tổng đã hoàn cộng đang giữ chỗ không vượt 300.000 VND và không có lệnh thừa.

Một bài kiểm thử cạnh tranh chạy thành công một lần chưa chứng minh mọi lịch thực thi đều an toàn. Bằng chứng cần kết hợp với cơ chế nguyên tử đã chọn và cách mọi đường ghi sử dụng cơ chế đó.

### 13.2. Các thuộc tính nên kiểm tra

```text
Với mọi chuỗi hành động được chấp nhận:
- Số tiền và khoản giữ chỗ không âm.
- Tổng đã hoàn + đang giữ chỗ không vượt số đã thu.
- Mỗi lần duyệt tham chiếu đúng phiên bản và người duyệt hợp lệ.
- Mỗi chuyển trạng thái thuộc tập chuyển trạng thái cho phép.
- Mỗi tác động tài chính có định danh nghiệp vụ truy vết được.
- Retry và callback trùng không làm tăng số tác động ngoài cam kết.
```

Có thể dùng kiểm thử theo bảng, sinh chuỗi hành động hoặc kiểm thử dựa trên thuộc tính để khám phá nhiều tổ hợp. Cần ưu tiên các chuỗi có hậu quả tài chính, thay đổi quyền hoặc vượt ranh giới tenant.

## 14. Mẫu ghi bằng chứng cho một quy tắc

Dùng một dòng cho mỗi quy tắc quan trọng để tránh checklist chỉ tồn tại trên tài liệu:

| Trường | Ví dụ |
|---|---|
| Mã quy tắc | `REFUND-INV-01` |
| Nội dung | Tổng đã hoàn và đang giữ chỗ không vượt số đã thu |
| Dữ liệu có thẩm quyền | Giao dịch thanh toán và các khoản giữ chỗ trong hệ thống |
| Điểm cưỡng chế | Hành động duyệt; cập nhật hạn mức có điều kiện trong transaction |
| Các đường phải tuân thủ | API nhân viên, API quản trị, batch và tác vụ khôi phục |
| Bằng chứng | Kiểm thử hai yêu cầu 200.000 VND tranh hạn mức 300.000 VND; xác nhận dữ liệu sau chạy |
| Quan sát vận hành | Số lần từ chối do thiếu hạn mức; khoản giữ chỗ tồn đọng cần đối soát |
| Chủ sở hữu | Người phụ trách nghiệp vụ hoàn tiền và nhóm triển khai |
| Tình trạng | Hoàn tất hoặc còn vấn đề cụ thể cần xử lý |

Không cần chép toàn bộ code vào bảng. Cần đủ thông tin để người khác tìm đúng cơ chế bảo vệ và tái hiện kiểm thử.

## 15. Điều kiện hoàn tất checklist cho tính năng mới

- [ ] Các quy tắc có ảnh hưởng đến tiền, quyền, dữ liệu và tài nguyên khan hiếm đã được chủ sở hữu nghiệp vụ xác nhận.
- [ ] Có sơ đồ hoặc bảng trạng thái và quy tắc quyền cho từng hành động nhạy cảm.
- [ ] Mỗi đường ghi đều đi qua cơ chế cưỡng chế thích hợp.
- [ ] Các yêu cầu về đồng thời và xử lý trùng có thiết kế cụ thể, bao gồm phạm vi và thời hạn cam kết.
- [ ] Đã ghi cách xử lý lỗi từng phần, timeout, kết quả chưa rõ và đối soát.
- [ ] Ma trận kiểm thử bao gồm bỏ bước, sửa dữ liệu, sai đối tượng, replay và cạnh tranh.
- [ ] Bằng chứng kiểm thử xác nhận cả phản hồi lẫn tác động dữ liệu và tác động bên ngoài.
- [ ] Các mục không áp dụng có lý do; các mục chưa xong có chủ sở hữu và quyết định xử lý rõ ràng.
- [ ] Có khả năng quan sát, dừng tác động nhạy cảm và khôi phục theo quy tắc nghiệp vụ.
- [ ] Quyết định đưa tính năng vào sử dụng dựa trên rủi ro và bằng chứng còn lại, không chỉ dựa vào số ô đã tích.

Checklist có giá trị khi biến một yêu cầu như “chỉ được hoàn đúng tiền sau khi duyệt” thành những điều kiện mà hệ thống bảo vệ được qua mọi đường vào, mọi lần gửi lại và những thời điểm nhiều thao tác cùng diễn ra.

