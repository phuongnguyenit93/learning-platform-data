# Promotion cancellation — Hủy chương trình khuyến mãi an toàn

Trong chương **Promotions**, hủy chương trình khuyến mãi không chỉ là đổi một cờ active thành false. Một chiến dịch có thể đã tạo báo giá, giữ ngân sách, cấp quyền mua có giảm giá, phát quà hoặc cộng điểm. Nếu hủy không đồng bộ với các hiệu ứng đó, hệ thống có thể tiếp tục cấp ưu đãi đã bị dừng, hoàn lượt dùng hai lần hoặc thu tiền khác với giá khách đã xác nhận.

Trong bảo mật logic nghiệp vụ, cần xem cancellation là một lệnh chuyển trạng thái có quyền hạn, điều kiện trước, quy tắc xử lý các cam kết đang tồn tại và dấu vết kiểm toán. Mục tiêu là bảo vệ bất biến xuyên qua chiến dịch, lượt hưởng ưu đãi, đơn hàng, thanh toán và phần thưởng.

Bài học dùng một chính sách cửa hàng giả định. Việc có tôn trọng lượt giữ trước thời điểm hủy hay có khôi phục quyền dùng mã sau hoàn tiền là quyết định nghiệp vụ cần được công bố rõ; không có một lựa chọn mặc định phù hợp cho mọi hệ thống.

Sau bài học, bạn cần có khả năng:

- Xác định đúng đối tượng đang bị hủy và phạm vi hiệu ứng cần xử lý.
- Thiết kế state machine cho chiến dịch và lượt giữ ưu đãi.
- Chặn tranh chấp giữa hủy, cấp ưu đãi, thanh toán và hoàn lượt.
- Bảo vệ quyền theo đối tượng, tính nguyên tử và idempotency.
- Viết tình huống kiểm thử các đường lạm dụng do hủy sai trình tự.

## 1. Một từ “hủy” có thể chỉ nhiều nghiệp vụ khác nhau

| Thao tác | Đối tượng bị tác động | Không được mặc nhiên suy ra |
| --- | --- | --- |
| Hủy chiến dịch | Promotion hoặc campaign | Mọi đơn đã giảm giá đều bị hủy |
| Bỏ mã khỏi giỏ | Ý định dùng ưu đãi và báo giá chưa chốt | Lượt dùng đã tiêu thụ tự động được hoàn |
| Giải phóng lượt giữ | Reservation về ngân sách hoặc quyền sử dụng | Thanh toán bên ngoài chắc chắn chưa thành công |
| Hủy đơn chưa thanh toán | Order và quy trình thanh toán đang mở | Có thể bỏ qua đối soát với cổng thanh toán |
| Hoàn tiền đơn đã trả | Refund và phân bổ tiền của đơn | Phải tính lại giá bằng chính sách khuyến mãi hiện tại |
| Đảo ngược lợi ích | Điểm, cashback, voucher phát sinh hoặc quà | Có thể xóa lịch sử đã cấp mà không ghi bút toán đối ứng |

Ví dụ, chiến dịch đã hủy vẫn có thể có đơn PAID hợp lệ được mua trước khi hủy. Ngược lại, một đơn bị hủy trong khi chiến dịch vẫn ACTIVE có thể phải giải phóng ngân sách để khách khác sử dụng.

Nên đặt tên lệnh rõ nghĩa, chẳng hạn:

~~~text
cancelPromotion
removePromotionFromCart
releasePromotionReservation
cancelOrder
requestRefund
reversePromotionReward
~~~

Các lệnh này có thể liên quan nhưng không nên được gộp thành một endpoint “cancel” tự suy đoán mọi hiệu ứng từ vài cờ do client gửi.

## 2. Những câu hỏi phải chốt trước khi triển khai

Một yêu cầu “dừng mã này ngay” chưa đủ để thiết kế hành vi an toàn. Cần thống nhất:

1. Dừng việc phát hành mã, việc tạo lượt giữ mới hay cả việc sử dụng lượt giữ cũ?
2. Báo giá chưa giữ chỗ có được tiếp tục dùng không?
3. Lượt giữ hợp lệ trước thời điểm hủy có được thanh toán trong thời hạn cũ không?
4. Đơn đã chốt nhưng thanh toán chưa có kết quả được xử lý thế nào?
5. Đơn đã trả tiền có giữ nguyên giá và quyền lợi đã cam kết không?
6. Khi hủy hoặc hoàn đơn, ngân sách và quyền dùng lại được hoàn theo quy tắc nào?
7. Điểm, quà hoặc cashback đã cấp được thu hồi ra sao?
8. Ai được hủy, ai được yêu cầu thu hồi khẩn cấp và có cần phê duyệt không?
9. API trả “đã chặn cấp mới” hay “mọi tác vụ bù trừ đã hoàn tất”?
10. Một chiến dịch đã hủy có được mở lại cùng ID không?

Đặc biệt, hủy chiến dịch không được trở thành một đường để tự tăng giá đơn đã chốt hoặc tự thu thêm tiền của khách. Nếu buộc phải thay đổi một cam kết, cần một quy trình riêng về xác nhận, hủy thanh toán hoặc hoàn tiền phù hợp với trạng thái hiện tại.

## 3. Chính sách ví dụ để theo dõi xuyên suốt

Cửa hàng có chiến dịch **WELCOME100**:

| Thuộc tính | Quy tắc giả định |
| --- | --- |
| Điều kiện | Tiền hàng đủ điều kiện từ 1.000.000 đồng |
| Lợi ích | Giảm cố định 100.000 đồng |
| Ngân sách | 2.000.000 đồng cho các khoản giảm được giữ hoặc tiêu thụ |
| Quyền theo khách | Mỗi khách có tối đa một lượt giữ hoặc một lượt đã tiêu thụ |
| Báo giá | Chỉ là tính thử, chưa giữ quyền hoặc ngân sách |
| Lượt giữ | Tồn tại trên máy chủ, gắn đúng khách, giỏ, phiên bản và chính sách |
| Thời hạn lượt giữ | Có 5 phút để bắt đầu một lần thanh toán được hệ thống chấp nhận |
| Hủy thông thường | Chặn lượt giữ mới; tôn trọng lượt giữ cũ còn hiệu lực |
| Hủy đơn trước trả tiền | Chỉ giải phóng sau khi xác định không còn thanh toán có thể hoàn tất |
| Hoàn tiền sau trả tiền | Không tự phục hồi quyền dùng một lần hoặc ngân sách chiến dịch trong ví dụ |
| Điểm thưởng minh họa | 100 điểm ở trạng thái PENDING sau thanh toán, chỉ khả dụng sau khi đơn hoàn tất theo chính sách |
| Trạng thái CANCELLED | Kết thúc vĩnh viễn đối với ID chiến dịch này |

Các quy tắc về ngân sách và quyền dùng sau hoàn tiền ở đây nhằm làm ví dụ nhất quán. Nếu doanh nghiệp muốn khôi phục chúng, phải đặc tả và thực thi một lệnh phục hồi riêng, có kiểm tra trạng thái chiến dịch và chống trùng.

### 3.1. Thời điểm hủy

Giả sử tại **10:00:00, UTC+07:00**, lệnh hủy được commit thành công:

- Khách A đã có lượt giữ hợp lệ lúc 09:59:00, hạn bắt đầu thanh toán là 10:04:00.
- Khách B chỉ có báo giá lúc 09:59:30, chưa giữ quyền.
- Khách C đã thanh toán từ 09:58:00.
- Khách D gửi yêu cầu giữ quyền sau khi hủy đã commit.

Với chính sách thông thường:

| Đối tượng | Sau khi hủy |
| --- | --- |
| A | Có thể bắt đầu thanh toán với lượt giữ cũ trong thời hạn được cam kết |
| B | Không được biến báo giá cũ thành lượt giữ mới cho chiến dịch này |
| C | Giữ nguyên giá đơn đã trả và xử lý lợi ích theo vòng đời đơn |
| D | Không được cấp lượt giữ mới |

Nếu A đã bắt đầu thanh toán hợp lệ lúc 10:03:00, không giải phóng lượt giữ đơn giản vào 10:04:00 trong khi kết quả thanh toán còn chưa rõ. Khi một payment attempt đã được gắn với lượt giữ, quy trình phải theo dõi kết quả có thẩm quyền thay vì áp dụng TTL của lượt giữ chưa sử dụng.

### 3.2. Không dùng thời gian do client gửi để quyết định

Mốc thời gian giúp giải thích cho con người, nhưng bằng chứng “đã giữ trước hủy” phải đến từ thứ tự chuyển trạng thái được máy chủ bảo vệ, chẳng hạn phiên bản hoặc admission epoch.

Không chấp nhận các trường sau làm căn cứ cấp quyền:

~~~json
{
  "promotionId": "WELCOME100",
  "requestedAt": "2026-11-22T09:59:59+07:00",
  "alreadyReserved": true,
  "honorOldPrice": true
}
~~~

Người gọi có thể sửa toàn bộ chúng. Chỉ bản ghi reservation thật, đúng đối tượng và đúng trạng thái trên máy chủ mới chứng minh được cam kết đang tồn tại.

## 4. Tách trạng thái chiến dịch khỏi trạng thái công việc hủy

### 4.1. State machine của chiến dịch

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> SCHEDULED: Lên lịch
    DRAFT --> CANCELLED: Hủy bản nháp
    SCHEDULED --> ACTIVE: Đến lịch và còn hợp lệ
    SCHEDULED --> CANCELLED: Hủy trước khi chạy
    ACTIVE --> PAUSED: Tạm dừng
    PAUSED --> ACTIVE: Tiếp tục theo quyền
    ACTIVE --> ENDED: Kết thúc theo lịch
    PAUSED --> ENDED: Hết thời gian hiệu lực
    ACTIVE --> CANCELLED: Hủy chiến dịch
    PAUSED --> CANCELLED: Hủy chiến dịch
~~~

PAUSED cho phép tiếp tục theo chính sách. CANCELLED trong mô hình này là trạng thái cuối: không có cạnh CANCELLED → ACTIVE. Nếu muốn chạy chương trình khác, tạo campaign ID mới và kiểm tra lại quyền hưởng ưu đãi.

ENDED biểu thị kết thúc theo lịch; CANCELLED biểu thị quyết định hủy trước hoặc trong thời gian hoạt động. Việc một API xử lý lệnh hủy trên chiến dịch ENDED bằng từ chối hoặc kết quả không thay đổi cần được ghi rõ. Không tự ghi lại lịch sử thành “đã hủy” để làm mất nguyên nhân kết thúc ban đầu.

Một job lên lịch chỉ được kích hoạt SCHEDULED đúng phiên bản. Job cũ không được đổi một chiến dịch đã CANCELLED sang ACTIVE.

### 4.2. Trạng thái chiến dịch và tiến độ bù trừ là hai việc

Có thể đã chặn cấp mới thành công nhưng vẫn còn tác vụ:

- Xóa cache hiển thị.
- Gửi thông báo.
- Đối soát các payment attempt chưa có kết quả.
- Thu hồi lợi ích thuộc một quy trình khẩn cấp riêng.
- Tổng hợp các đơn bị ảnh hưởng.

Không nên giữ chiến dịch ở ACTIVE chỉ vì gửi thông báo chưa xong. Ngược lại, không báo “đã hoàn tất mọi thu hồi” ngay sau khi mới ghi một sự kiện.

Một phản hồi có thể tách rõ:

~~~json
{
  "promotionId": "WELCOME100",
  "campaignState": "CANCELLED",
  "newReservationsBlocked": true,
  "cancellationOperationId": "pcancel-42",
  "followUpState": "PENDING"
}
~~~

API chỉ trả newReservationsBlocked = true sau khi hàng rào cấp quyền có thẩm quyền đã được cập nhật bền vững. Việc xóa cache hoặc publish một sự kiện đơn lẻ không đủ chứng minh điều đó.

## 5. Chính sách hủy thông thường và thu hồi khẩn cấp

| Cách xử lý | Ý nghĩa | Điều kiện cần thiết |
| --- | --- | --- |
| STOP_NEW_RESERVATIONS | Chặn cam kết mới, giữ cam kết cũ đúng hạn | Điểm cấp lượt giữ phải kiểm tra hàng rào hủy |
| REVOKE_UNUSED_RESERVATIONS | Thu hồi lượt giữ chưa bắt đầu thanh toán | Quyền riêng, điều kiện thu hồi và thông báo rõ; không được tự tăng giá |
| Thu hồi liên quan giao dịch đang xử lý | Dừng hoặc bù trừ một giao dịch đã đi sang hệ thống khác | Quy trình bất đồng bộ, đối soát và quyết định theo trạng thái thanh toán |
| Xem xét giao dịch đã trả | Kiểm tra một cam kết đã hoàn tất | Quy trình riêng; không coi hủy chiến dịch là bằng chứng được phép thu thêm tiền |

Ví dụ trong bài áp dụng STOP_NEW_RESERVATIONS. Hai cách sau không phải tham số tùy ý mà người có quyền hủy thông thường được tự gửi qua force = true.

Nếu có hủy khẩn cấp do cấu hình giảm sai hoặc nghi ngờ gian lận, cần ghi rõ:

- Ai được yêu cầu, ai được phê duyệt và phạm vi nào bị tác động.
- Chỉ những reservation nào chưa có payment attempt mới được giải phóng trực tiếp.
- Trường hợp nào phải chặn bắt đầu thanh toán, hủy authorization hoặc hoàn tiền.
- Dữ liệu và bằng chứng nào được dùng để xác định trạng thái.
- Trường hợp nào cần xử lý thủ công khi lợi ích không thể thu hồi tự động.

Thu hồi hàng loạt cần operation ID và tiến độ theo từng đối tượng. Không dùng một boolean “done” để che các tác vụ bù trừ thất bại.

## 6. Những bất biến bảo mật quan trọng

### 6.1. Phạm vi và quyền hạn

- Lệnh hủy chỉ tác động chiến dịch thuộc đúng tenant và phạm vi mà người gọi quản lý.
- Có quyền xem hoặc chỉnh nội dung quảng bá chưa chắc có quyền hủy chiến dịch.
- Quyền hủy thông thường không đồng nghĩa quyền hoàn tiền, khôi phục mã hoặc ghi giảm điểm.
- Phê duyệt, nếu cần, phải gắn với đúng chiến dịch, phiên bản, chế độ và phạm vi hủy.
- Thay đổi phạm vi hoặc chế độ sau phê duyệt làm yêu cầu phải được xét lại.

### 6.2. Cấp quyền và giá

- Sau khi hàng rào hủy đã commit, không có lượt giữ mới được cấp cho chiến dịch theo chính sách ví dụ.
- Một báo giá không giữ chỗ không thể giả làm một cam kết cũ.
- Một lượt giữ chỉ gắn với đúng khách, giỏ, phiên bản và các điều kiện đã được máy chủ chấp nhận.
- Không tái định giá đơn đã chốt chỉ vì trạng thái campaign đổi.
- Không chuyển reservation đã RELEASED hoặc REVOKED thành CONSUMED bằng một callback cũ mà bỏ qua đối soát.

### 6.3. Ngân sách và hiệu ứng

- Ngân sách giữ và ngân sách đã tiêu thụ không âm.
- Tổng ngân sách đang giữ và đã tiêu thụ không vượt hạn mức.
- Một reservation chỉ được giải phóng hoặc tiêu thụ một lần theo một chuyển trạng thái hợp lệ.
- Hủy lặp không tạo thêm khoản hoàn, thêm lượt dùng hoặc thêm bút toán thu hồi.
- Không vừa giữ quyền dùng lại vừa giữ lợi ích của giao dịch đã bị hủy trái chính sách.

### 6.4. Dấu vết và khả năng phục hồi

- Hủy không xóa dữ liệu chứng minh một ưu đãi đã được áp dụng.
- Mỗi hiệu ứng bù trừ truy được về lệnh hủy hoặc sự kiện nghiệp vụ gốc.
- Tác vụ thất bại có thể retry mà không làm lặp hiệu ứng.
- Không tuyên bố toàn bộ quy trình đã hoàn tất nếu còn một kết quả thanh toán hoặc hoàn tiền chưa xác định.

## 7. Dữ liệu tối thiểu để thực thi và điều tra

Không nên chỉ có một bảng promotion với cột active. Cần phân biệt ít nhất các loại bản ghi sau:

| Loại bản ghi | Dữ liệu quan trọng |
| --- | --- |
| Promotion | tenantId, promotionId, trạng thái, version, admissionEpoch, chính sách hủy, thời điểm và người hủy |
| Reservation | reservationId, promotionId, khách, giỏ và phiên bản, phiên bản chính sách, epoch lúc cấp, khoản giảm, loại tiền, hạn sử dụng, trạng thái |
| Order snapshot | Giá gốc, giảm giá thực tế, phân bổ theo dòng, tổng phải trả, reservation và payment attempt liên quan |
| Cancellation operation | operationId, chế độ, lý do, phạm vi, người yêu cầu, phê duyệt, trạng thái công việc |
| Budget hoặc usage ledger | Các khoản giữ, tiêu thụ, giải phóng và khóa chống lặp |
| Reward ledger | Lợi ích được cấp, phần đã khả dụng, đã dùng và bút toán thu hồi |
| Outbox và inbox | Sự kiện phải phát, sự kiện đã nhận và trạng thái xử lý bền vững |

Trong mô hình này, admissionEpoch tăng khi hàng rào cấp mới thay đổi. Nó giúp nhận diện việc dùng dữ liệu cấp quyền cũ. Tuy nhiên, lưu epoch trong token không tự bảo vệ được hệ thống: nơi ra quyết định phải đối chiếu nó với trạng thái có thẩm quyền.

Không xóa promotion sau hủy nếu order hoặc ledger vẫn tham chiếu nó. Có thể ẩn khỏi danh mục hiển thị, nhưng vẫn giữ dữ liệu chính sách và quyết định lịch sử cần để đối soát.

## 8. Chống cuộc đua giữa hủy và cấp lượt giữ

### 8.1. Mẫu dễ lỗi

~~~text
Request cấp ưu đãi:
  đọc cache: campaign = ACTIVE
  kiểm tra đủ điều kiện
  tạo reservation

Request hủy:
  ghi campaign = CANCELLED
  phát sự kiện xóa cache
~~~

Nếu request đầu đã đọc ACTIVE trước khi hủy, nó có thể tạo reservation sau khi hủy đã báo thành công. Xóa cache nhanh hơn chỉ thu hẹp cửa sổ lỗi, không bảo vệ được bất biến.

Đọc trạng thái trước transaction rồi dùng lại trạng thái đó trong transaction cũng có cùng vấn đề.

### 8.2. Một điểm có thẩm quyền cho quyết định cấp mới

Với các dữ liệu nằm trong cùng một cơ sở dữ liệu, có thể dùng cùng một bản ghi khóa hoặc một cơ chế cập nhật có điều kiện mà cả đường reserve và cancel đều tuân thủ.

~~~text
RESERVE:
BEGIN
  khóa promotion theo tenant và promotionId
  xác nhận đang cho phép cấp mới
  kiểm tra điều kiện và phiên bản cần thiết
  giữ ngân sách và slot của khách bằng cập nhật có điều kiện
  tạo reservation với admissionEpoch hiện tại
COMMIT

CANCEL:
BEGIN
  khóa cùng promotion theo tenant và promotionId
  kiểm tra quyền và yêu cầu hủy
  chuyển trạng thái sang CANCELLED
  tăng version và admissionEpoch
  ghi cancellation operation, audit và outbox
COMMIT
~~~

Hai đường này có thứ tự rõ ràng:

| Thứ tự được cơ sở dữ liệu bảo vệ | Kết quả |
| --- | --- |
| Reserve giữ khóa và commit trước | Reservation là cam kết cũ; cancel áp chính sách đối với cam kết đó |
| Cancel giữ khóa và commit trước | Reserve sau đó đọc CANCELLED và từ chối cấp mới |
| Reserve gặp lỗi hoặc rollback | Không có cam kết được tạo, dù client đã nhận một bước tính thử thành công |

Thời điểm client bấm nút hoặc thời gian bắt đầu HTTP request không quyết định ai thắng. Thứ tự quyết định là thứ tự chuyển trạng thái được hệ thống có thẩm quyền bảo vệ.

Cần xác định thứ tự khóa chung cho mọi đường thao tác liên quan đến promotion, reservation, order và ledger. Không để đường cấp ưu đãi khóa promotion trước order trong khi đường hủy khóa ngược lại mà không có thiết kế xử lý deadlock.

### 8.3. Nếu nhiều dịch vụ cùng tham gia

Một consumer nhận sự kiện hủy sau vài giây không thể bảo đảm “chặn cấp mới ngay khi API hủy trả thành công”, nếu nó vẫn tự cấp quyền từ bản sao cũ.

Có thể lựa chọn:

- Đưa quyết định tạo reservation về một dịch vụ có thẩm quyền duy nhất.
- Yêu cầu một quyền cấp có fencing token và kiểm tra hàng rào tại nơi commit.
- Thiết kế một giao thức khác có thứ tự cam kết được chứng minh rõ ràng.

Nếu chọn nhất quán cuối cùng và chấp nhận một khoảng trễ, phải mô tả đúng cam kết đó, thay vì tuyên bố ngăn cấp mới tức thời.

Khi không kiểm tra được nguồn có thẩm quyền, từ chối hoặc hoãn việc cấp mới theo hợp đồng API. Không suy ra campaign vẫn ACTIVE chỉ vì cache chưa bị xóa.

## 9. Luồng hủy có quyền, phiên bản và idempotency

### 9.1. Request chỉ mang ý định

Một lệnh hủy thông thường có thể là:

~~~http
POST /promotions/promo-100/cancellations
Idempotency-Key: cancel-request-42
Content-Type: application/json

{
  "expectedVersion": 18,
  "reasonCode": "BUSINESS_STOP",
  "reason": "Dừng chiến dịch theo quyết định đã phê duyệt"
}
~~~

Máy chủ lấy tenant và người thao tác từ ngữ cảnh đã xác thực, không tin userId, tenantId hoặc role tự khai báo trong body.

Không để endpoint thông thường nhận các trường có quyền lực vượt phạm vi như:

~~~text
forceRefundAll = true
restoreAllUsage = true
ignoreApproval = true
cancelledAt = thời gian client tự chọn
targetCustomerId = tài khoản tùy ý
~~~

Nếu cần chế độ khẩn cấp, dùng hợp đồng và quyền riêng, kiểm tra bản ghi phê duyệt thật. Giấu nút trên giao diện không ngăn gọi API trực tiếp.

### 9.2. Giả mã Java cho đường ghi cuối cùng

Đoạn sau là mã khung mô tả hợp đồng; các repository, transaction và kiểm tra quyền là thành phần giả định, không phải một ứng dụng chạy độc lập.

~~~java
CancellationResult cancelPromotion(
        Actor actor,
        CancelPromotionCommand command
) {
    return transaction.required(() -> {
        Promotion promotion = promotions.lockByTenantAndId(
                actor.tenantId(), command.promotionId());

        authorization.requireCanCancel(actor, promotion);

        IdempotencyReceipt receipt = idempotency.beginOrLoad(
                actor.tenantId(),
                actor.id(),
                "CANCEL_PROMOTION",
                command.requestKey(),
                command.semanticPayloadHash());

        if (receipt.isCompleted()) {
            return receipt.savedResult();
        }

        if (promotion.isCancelled()) {
            CancellationResult existing =
                    cancellationResults.forPromotion(promotion.id());

            idempotency.complete(receipt, existing);
            return existing;
        }

        promotion.requireVersion(command.expectedVersion());
        approvalPolicy.verifyIfRequired(actor, promotion, command);

        // Chính sách lấy từ máy chủ, không lấy từ cờ force của client.
        CancellationPolicy policy = promotion.cancellationPolicy();
        Instant now = clock.instant();

        CancellationOperation operation =
                promotion.cancel(policy, actor.id(), now, command.reason());

        promotions.save(promotion);
        cancellationOperations.save(operation);
        audit.append(operation.auditRecord());
        outbox.append(operation.cancellationEvent());

        CancellationResult result = operation.acceptedResult();
        idempotency.complete(receipt, result);
        return result;
    });
}
~~~

Các hợp đồng quan trọng của mã khung:

- lockByTenantAndId khóa đúng chiến dịch trong phạm vi tenant; không tải toàn cục rồi quên kiểm tra phạm vi.
- requireCanCancel kiểm tra quyền trên đối tượng, kể cả trước khi trả kết quả hủy cũ.
- semanticPayloadHash được máy chủ tính từ nội dung có ý nghĩa; không tin một hash do client tự cung cấp.
- beginOrLoad phát hiện key trùng nhưng payload khác và không cho hai nhánh cùng hoàn tất hiệu ứng.
- Nhánh đã CANCELLED trả kết quả cũ chỉ phù hợp cho cùng nghiệp vụ hủy thông thường; không biến nó thành yêu cầu thu hồi khẩn cấp mới.
- Nếu chiến dịch chưa hủy nhưng expectedVersion đã cũ, từ chối xung đột để người gọi đọc lại tình trạng.
- cancel kiểm tra cạnh chuyển trạng thái hợp lệ và tăng version, admissionEpoch đúng một lần.
- Trạng thái, operation, audit, outbox và kết quả idempotency được lưu nguyên tử.
- Bất kỳ bước nào thất bại trước commit đều không để lại trạng thái “đã hủy một nửa”.

Không gọi cổng thanh toán hoặc dịch vụ gửi thư trong transaction đang giữ khóa campaign. Ghi ý định vào outbox rồi xử lý sau commit.

### 9.3. Hai lớp chống lặp

| Lớp | Bảo vệ |
| --- | --- |
| Idempotency theo key, người gọi, tenant và loại lệnh | Mạng retry không làm lặp cùng yêu cầu |
| Điều kiện trạng thái nghiệp vụ và ràng buộc duy nhất | Gửi key mới vẫn không hủy hoặc giải phóng cùng đối tượng hai lần |

Với chiến dịch đã hủy thông thường, một lệnh cùng nghĩa dùng key khác có thể trả cùng kết quả nghiệp vụ mà không tăng epoch và không phát thêm sự kiện hủy.

Khóa idempotency của một lần bù trừ phải đủ cụ thể, chẳng hạn:

~~~text
(cancellationOperationId, reservationId, RELEASE_RESERVATION)
(refundRequestId, orderId, REFUND_PAYMENT)
(reversalRequestId, rewardGrantId, REVERSE_REWARD)
~~~

Không dùng riêng promotionId làm khóa cho mọi khoản hoàn: nhiều khách có thể cần các khoản hoàn độc lập. Cũng không dùng riêng số tiền làm khóa vì hai yêu cầu hoàn hợp lệ khác nhau có thể có cùng giá trị.

## 10. State machine của lượt hưởng ưu đãi

~~~mermaid
stateDiagram-v2
    [*] --> HELD: Giữ quyền và ngân sách
    HELD --> PAYMENT_PENDING: Bắt đầu thanh toán hợp lệ
    HELD --> RELEASED: Hết hạn hoặc bỏ giữ khi chưa có thanh toán
    HELD --> REVOKED: Thu hồi chưa sử dụng theo quyền riêng
    PAYMENT_PENDING --> CONSUMED: Xác nhận trả tiền hợp lệ
    PAYMENT_PENDING --> RELEASED: Xác nhận thất bại cuối cùng
    PAYMENT_PENDING --> CANCEL_PENDING: Có yêu cầu hủy đơn
    CANCEL_PENDING --> RELEASED: Đã xác nhận không thể thu tiền
    CANCEL_PENDING --> CONSUMED: Phát hiện tiền đã được thu
~~~

Trong mô hình này:

- HELD là quyền đã giữ nhưng chưa gắn payment attempt.
- PAYMENT_PENDING là đã bắt đầu một lần thanh toán được phép.
- CONSUMED giữ lịch sử lợi ích đã đi vào giao dịch trả tiền.
- RELEASED hoặc REVOKED không phải giấy phép để dùng lại chính reservation đó.
- CANCEL_PENDING là yêu cầu hủy đang chờ kết quả, chưa phải bằng chứng tiền chưa bị thu.

Nếu CANCEL_PENDING chuyển thành CONSUMED vì thanh toán đã thành công, quy trình hủy đơn phải tiếp tục bằng yêu cầu hoàn tiền phù hợp. Không xóa kết quả trả tiền hoặc tự đổi về RELEASED cho khớp ý định ban đầu.

Hủy chiến dịch thông thường không tự đưa mọi reservation sang CANCEL_PENDING. Trạng thái này dành cho việc hủy giao dịch đang xử lý hoặc một quy trình thu hồi riêng.

### 10.1. Kiểm tra lượt giữ cũ sau hủy

Với chính sách tôn trọng lượt giữ cũ, bước bắt đầu thanh toán kiểm tra:

1. Reservation thật thuộc đúng khách, giỏ và tenant.
2. Reservation được cấp hợp lệ trước hàng rào hủy theo dữ liệu máy chủ.
3. Trạng thái là HELD và chưa hết hạn bắt đầu thanh toán.
4. Giỏ và số tiền vẫn khớp snapshot đã cam kết.
5. Chính sách hủy ghi nhận cho phép tôn trọng loại cam kết này.
6. Chuyển HELD → PAYMENT_PENDING chỉ thành công một lần.

Không chỉ kiểm tra campaign đang ACTIVE, vì cách đó sẽ từ chối cả cam kết cũ được chính sách cho phép. Cũng không bỏ qua trạng thái campaign hoàn toàn, vì cách đó có thể chấp nhận một lượt giữ sai phạm vi hoặc bị thu hồi.

Sửa số lượng, sản phẩm hoặc địa chỉ làm thay đổi điều kiện của cam kết phải đi qua quy tắc cập nhật riêng. Không cho phép một reservation giảm 100.000 đồng của giỏ đạt ngưỡng được chuyển sang giỏ khác không đạt ngưỡng.

## 11. Giải phóng ngân sách và quyền dùng mà không tạo lợi ích kép

Đặt:

~~~text
L = hạn mức ngân sách
R = ngân sách đang giữ
C = ngân sách đã tiêu thụ
A = ngân sách khả dụng theo hạn mức = L - R - C
~~~

Các bất biến:

~~~text
R >= 0
C >= 0
R + C <= L
~~~

Khi reservation được tiêu thụ, chuyển khoản tương ứng từ R sang C. Khi một lượt giữ chưa tiêu thụ được giải phóng hợp lệ, giảm R đúng một lần. Mọi thao tác phải gắn với chuyển trạng thái thành công của chính reservation đó.

Ví dụ với hạn mức 2.000.000 đồng:

| Bước | R | C | A |
| --- | ---: | ---: | ---: |
| Trước xử lý | 300.000 | 700.000 | 1.000.000 |
| Giải phóng một lượt giữ 100.000 | 200.000 | 700.000 | 1.100.000 |
| Tiêu thụ một lượt giữ cũ khác 100.000 | 100.000 | 800.000 | 1.100.000 |

Sau khi campaign bị hủy, A tăng lên không có nghĩa campaign được cấp ưu đãi mới. Ngân sách khả dụng và trạng thái cho phép cấp mới là hai điều kiện độc lập.

### 11.1. Chuyển trạng thái và cập nhật tiền trong cùng transaction

~~~text
BEGIN
  khóa reservation và các tài nguyên liên quan theo thứ tự thống nhất

  nếu reservation đã RELEASED:
      trả kết quả đã giải phóng, không giảm R lần nữa

  yêu cầu trạng thái hiện tại cho phép giải phóng
  xác nhận không có payment attempt chưa rõ kết quả

  đổi reservation sang RELEASED
  giảm R bằng đúng số tiền đang giữ của reservation
  cập nhật slot của khách theo chính sách
  ghi ledger và outbox với khóa hiệu ứng duy nhất
COMMIT
~~~

Không thực hiện “giảm R” rồi mới ghi trạng thái ở transaction khác. Nếu request chết giữa hai bước, lần retry có thể giảm R thêm lần nữa.

Một ràng buộc duy nhất trên event ID không đủ bảo vệ nếu hai sự kiện khác nhau cùng yêu cầu giải phóng một reservation. Cần cả bất biến trên đối tượng và khóa hiệu ứng nghiệp vụ.

### 11.2. Hoàn quyền dùng sau hủy đơn

Với chính sách ví dụ:

- Đơn chưa trả tiền và đã xác nhận không thể thu tiền: giải phóng slot.
- Nếu campaign còn ACTIVE, khách có thể xin một lượt giữ mới theo điều kiện hiện tại.
- Nếu campaign đã CANCELLED, slot trống vẫn không cho phép cấp lại.
- Đơn đã trả tiền rồi hoàn: không tự mở slot đã tiêu thụ.

Không dùng một cờ used = false chung để xử lý mọi trường hợp. Cần biết mã đang được giữ, đã tiêu thụ, đã giải phóng hay đã được phục hồi theo một quyết định riêng.

Hủy rồi tạo lại campaign bằng ID mới cũng phải có chính sách định danh quyền hưởng phù hợp. Nếu doanh nghiệp muốn “mỗi khách chỉ hưởng chương trình chào mừng một lần” xuyên nhiều campaign, khóa hạn mức phải gắn với quyền chào mừng, không chỉ ID chiến dịch.

## 12. Tác vụ bù trừ, thanh toán và sự kiện đến muộn

### 12.1. Không nhầm yêu cầu hủy với hủy thành công

Có thể xảy ra trình tự:

~~~text
1. Hệ thống gửi yêu cầu thanh toán.
2. Khách yêu cầu hủy đơn.
3. Hệ thống gửi yêu cầu hủy thanh toán.
4. Request đến cổng bị timeout.
5. Cổng đã thu tiền thành công trước khi nhận yêu cầu hủy.
~~~

Nếu bước 4 làm hệ thống giải phóng ngân sách và phục hồi mã ngay, khách có thể vừa giữ đơn đã trả vừa sử dụng lại ưu đãi.

Giữ giao dịch ở trạng thái cần đối soát. Khi xác nhận đã thu tiền, ghi nhận đúng kết quả rồi tiếp tục quy trình hoàn tiền nếu yêu cầu hủy còn hợp lệ.

API thanh toán thường giới hạn việc hủy theo trạng thái tài nguyên. Chẳng hạn, tài liệu Stripe chỉ cho hủy PaymentIntent trong các trạng thái cụ thể; không thể giả định mọi giao dịch đều hủy được chỉ vì ứng dụng vừa nhận lệnh hủy. [Stripe — Cancel a PaymentIntent](https://docs.stripe.com/api/payment_intents/cancel).

### 12.2. Luồng bù trừ có thể retry

Một quy trình thu hồi giao dịch đang xử lý có thể gồm:

~~~text
REQUESTED
→ chặn thao tác bắt đầu thanh toán mới trên đối tượng bị thu hồi
→ EXTERNAL_PENDING
→ truy vấn hoặc nhận kết quả có thẩm quyền

Nếu xác nhận chưa thu và không thể thu:
  giải phóng reservation, ngân sách và tài nguyên tương ứng

Nếu xác nhận đã thu:
  ghi nhận trả tiền
  tạo yêu cầu hoàn theo chính sách
  thu hồi lợi ích liên quan bằng bút toán riêng

Nếu kết quả mâu thuẫn hoặc chưa rõ:
  RECONCILE_REQUIRED hoặc MANUAL_REVIEW
~~~

Mỗi bước có khóa hiệu ứng ổn định và kết quả đã lưu. Nếu gọi ra ngoài thành công nhưng ghi nhận nội bộ thất bại, lần retry phải truy vấn hoặc dùng khóa chống trùng của nhà cung cấp để đối soát, không phát một giao dịch mới tùy ý.

Phạm vi COMPLETED của operation cần được định nghĩa. Với STOP_NEW_RESERVATIONS, hoàn tất có thể là đã chặn cấp mới và xử lý xong các tác vụ phụ đã xác định; không cần đợi mọi khách có reservation cũ hoàn tất mua hàng. Với thu hồi hàng loạt, phải theo dõi kết quả của tập đối tượng bị thu hồi.

### 12.3. Nhận webhook không đồng nghĩa áp hiệu ứng ngay

Một webhook handler cần:

1. Xác minh nguồn theo giao thức nhà cung cấp.
2. Ánh xạ đúng tài khoản nhà cung cấp, tenant, payment attempt và order.
3. Lưu sự kiện hoặc đưa vào hàng đợi bền vững trước khi xác nhận đã tiếp nhận.
4. Loại lặp ở cấp event và bảo vệ chuyển trạng thái ở cấp đối tượng.
5. Không hồi sinh một trạng thái cũ chỉ vì sự kiện đến sau.
6. Đối soát tài nguyên hiện tại khi sự kiện không đủ chứng minh kết quả.

Tài liệu Stripe nêu webhook có thể lặp và không bảo đảm thứ tự giao sự kiện. Vì vậy, thứ tự HTTP đến ứng dụng không thể thay thế quy tắc chuyển trạng thái nghiệp vụ. [Stripe — Webhooks](https://docs.stripe.com/webhooks).

Không mặc định sắp xếp theo timestamp trong payload là giải pháp đầy đủ. Chỉ dùng sequence hoặc version như bằng chứng thứ tự nếu nhà cung cấp thực sự bảo đảm nghĩa của nó.

## 13. Đơn đã trả tiền, điểm thưởng và quà tặng

Hủy chiến dịch thông thường chỉ chặn cam kết mới. Nó không tự thu hồi điểm hoặc quà của mọi đơn lịch sử. Việc đảo ngược lợi ích cần dựa vào một nghiệp vụ riêng, chẳng hạn đơn bị hủy, hàng được hoàn hoặc một quyết định thu hồi được phê duyệt.

OWASP mô tả tình huống khách bắt đầu giao dịch để nhận điểm rồi hủy hoặc giảm giá trị mua, nhưng hệ thống không điều chỉnh điểm tương ứng. Đây là một ví dụ trực tiếp về lợi ích được giữ lại khi quy trình không hoàn thành như yêu cầu. [OWASP WSTG — Testing for the Circumvention of Work Flows](https://wstg.owasp.org/v4.2/4-Web_Application_Security_Testing/10-Business_Logic_Testing/06-Testing_for_the_Circumvention_of_Work_Flows/).

### 13.1. Hoàn đúng tiền thực trả

Giả sử đơn dùng WELCOME100 có:

| Dòng | Tiền hàng gốc | Phần giảm được phân bổ | Tiền hàng thực trả |
| --- | ---: | ---: | ---: |
| A | 600.000 | 60.000 | 540.000 |
| B | 400.000 | 40.000 | 360.000 |
| **Tổng** | **1.000.000** | **100.000** | **900.000** |

Để tập trung vào khuyến mãi, ví dụ này không có phí giao hàng hoặc khoản thu khác.

Nếu hủy và hoàn toàn bộ đơn đã trả, số tiền hàng có thể hoàn là **900.000 đồng**, không phải 1.000.000 đồng. Khoản giảm 100.000 đồng không phải tiền mà khách đã nộp.

Nếu chỉ hoàn dòng A, cơ sở hoàn tiền của dòng đó là 540.000 đồng. Không tính lại bằng cấu hình campaign đang có tại thời điểm hoàn, vì campaign có thể đã bị hủy.

Với chính sách giả định không định giá lại các dòng được giữ, dòng B tiếp tục mang giá thực trả 360.000 đồng. Nếu doanh nghiệp yêu cầu thu hồi giảm giá khi phần giữ lại không đạt ngưỡng, phải đặc tả trước cách tính và cách thực hiện. Không tự trừ một khoản bất ngờ hoặc gọi thu thêm tiền chỉ vì hệ thống phát hiện đơn còn lại không đủ 1.000.000 đồng.

Lưu phân bổ giảm giá ở thời điểm chốt giúp bảo vệ:

~~~text
Tổng các khoản giảm phân bổ = Khoản giảm thực tế
Tổng tiền hoàn thành công + tiền đang giữ cho yêu cầu hoàn
    <= Phần tiền thực trả được phép hoàn
~~~

Đối với nhiều yêu cầu hoàn đồng thời, phải giữ hạn mức hoàn nguyên tử. Chỉ kiểm tra tổng đã hoàn trước khi gửi request ra ngoài không ngăn được hai khoản hoàn cùng vượt giới hạn.

### 13.2. Điểm chưa khả dụng

Với 100 điểm PENDING sau thanh toán, khi đơn bị hủy hợp lệ trước thời điểm điểm khả dụng:

- Ghi nhận việc vô hiệu lợi ích theo chính sách.
- Không cho phép chuyển PENDING → AVAILABLE sau đó.
- Gắn việc vô hiệu với order và reward grant gốc.
- Retry không tạo thêm bút toán thu hồi.

Job làm điểm khả dụng phải kiểm tra trạng thái hiện tại của grant và điều kiện hoàn tất đơn. Một sự kiện “đơn đã thanh toán” đến muộn không được tự cấp lại điểm đã bị vô hiệu do hoàn đơn.

Có thể thay đổi trạng thái grant và ghi bút toán đối ứng phù hợp mô hình ledger, nhưng phải giữ lịch sử cấp và thu hồi. Không xóa grant khiến hệ thống không còn chứng minh được điểm đã từng phát.

### 13.3. Điểm đã được sử dụng

Giả sử 100 điểm đã khả dụng, khách dùng 40 điểm, còn 60 điểm. Nếu chính sách cần thu hồi đủ 100 điểm, trừ tối đa 60 rồi coi đã thu hồi đủ sẽ bỏ sót 40 điểm.

Cần mô hình hóa phần chưa thu hồi, ví dụ:

~~~text
Lợi ích cần thu hồi:     100 điểm
Điểm còn có thể thu hồi:  60 điểm
Nghĩa vụ còn thiếu:       40 điểm
~~~

Phần 40 điểm có thể được theo dõi trong một ledger nghĩa vụ, hạn chế đổi thưởng tiếp hoặc chuyển xử lý thủ công theo chính sách. Không tự quy đổi thành một khoản thu tiền nếu hệ thống chưa có nghiệp vụ và sự chấp thuận cần thiết.

Các số dư, nghĩa vụ và bút toán cần ràng buộc với khách và grant cụ thể. Không cho phép gửi customerId khác để trừ điểm của người khác hoặc chuyển nghĩa vụ sang tài khoản khác.

### 13.4. Quà tặng và cashback

Nếu khuyến mãi có quà vật lý:

- Chưa xuất kho: chặn hoặc hủy yêu cầu xuất theo trạng thái được kho xác nhận.
- Đang đóng gói: cần xác nhận đã dừng trước khi hoàn tồn.
- Đã giao: xử lý hoàn quà hoặc ngoại lệ theo chính sách; không tự ghi tăng tồn như thể quà chưa được giao.
- Request hủy lặp không được hoàn tồn nhiều lần.

Nếu cashback đã được chuyển qua một hệ thống khác, việc đổi trạng thái nội bộ không lấy tiền về được. Cần một lệnh bù trừ riêng có kết quả xác nhận và khả năng đối soát.

Không để cả hai cơ chế “đã thu hồi qua API” và “đã thu hồi qua webhook” cùng ghi hai khoản thu hồi cho một lợi ích.

## 14. Những đường lạm dụng điển hình

### 14.1. Hủy rồi dùng lại mã trong khi giao dịch cũ vẫn có thể trả tiền

**Lỗi:** mở slot ngay khi nhận yêu cầu hủy, trước khi biết kết quả payment attempt.

**Hậu quả:** khách tạo lượt giữ mới, trong khi giao dịch cũ vẫn thành công và giữ ưu đãi.

**Kiểm soát:** CANCEL_PENDING không giải phóng slot; chờ kết quả có thẩm quyền và bảo vệ chuyển trạng thái bằng cập nhật có điều kiện.

### 14.2. Dùng báo giá cũ để đi vòng hàng rào hủy

**Lỗi:** checkout tin total hoặc quoteId mà không kiểm tra loại cam kết.

**Hậu quả:** báo giá chỉ tính thử được chấp nhận như một reservation cũ.

**Kiểm soát:** phân biệt quote và reservation; đối chiếu bản ghi thật, phiên bản, phạm vi và chính sách tôn trọng cam kết.

### 14.3. Giả thời gian hoặc trạng thái từ client

**Lỗi:** tin requestedAt, alreadyReserved hoặc state = HELD trong request.

**Hậu quả:** khách tự làm cho yêu cầu mới trông như đã được chấp nhận trước khi hủy.

**Kiểm soát:** quyết định bằng dữ liệu máy chủ và thứ tự chuyển trạng thái được bảo vệ, không bằng thời điểm tự khai.

### 14.4. Hủy chiến dịch của tenant khác

**Lỗi:** tải promotion bằng ID toàn cục rồi chỉ kiểm tra người gọi có vai trò marketing.

**Hậu quả:** một tài khoản quản trị phạm vi nhỏ có thể phá hoạt động của tổ chức khác.

**Kiểm soát:** kiểm tra quyền trên đúng đối tượng và tenant; cùng kiểm tra đó áp dụng cho API trực tiếp, giao diện quản trị và tác vụ nội bộ.

### 14.5. Dùng quyền hỗ trợ để thu hồi hàng loạt

**Lỗi:** cùng endpoint cho phép nhân viên hỗ trợ gửi force = true để chuyển từ dừng cấp mới sang hoàn tiền hoặc xóa quyền lợi.

**Hậu quả:** tác động vượt quyền mà không cần sửa code hoặc khai thác lỗi kỹ thuật khác.

**Kiểm soát:** tách quyền, chế độ và phê duyệt; đường ghi cuối cùng kiểm tra lại phạm vi thực tế.

### 14.6. Nhận điểm, hủy, rồi lặp lại

**Lỗi:** cấp điểm khả dụng trước khi đơn đủ điều kiện và không có ledger đảo ngược.

**Hậu quả:** người dùng tích lũy điểm bằng các đơn không hoàn thành.

**Kiểm soát:** tách điểm PENDING và AVAILABLE, khóa chuyển trạng thái, ghi thu hồi và kiểm soát quyền dùng mã theo vòng đời.

### 14.7. Hủy hai lần để nhân ngân sách hoặc tiền hoàn

**Lỗi:** mỗi lần gọi đều giảm tổng ngân sách đang giữ hoặc phát một yêu cầu refund mới.

**Hậu quả:** ngân sách âm, quyền sử dụng tăng sai hoặc hoàn tiền vượt số thực trả.

**Kiểm soát:** chuyển trạng thái và ghi ledger nguyên tử; chống trùng theo cả request lẫn hiệu ứng nghiệp vụ.

### 14.8. Job hoặc sự kiện cũ làm sống lại campaign

**Lỗi:** job đến lịch ghi ACTIVE mà không kiểm tra trạng thái; consumer ghi đè snapshot mới bằng sự kiện cũ.

**Hậu quả:** chiến dịch đã hủy được mở lại ngoài chủ đích.

**Kiểm soát:** cạnh chuyển trạng thái có điều kiện, version tăng đơn điệu cho sự kiện nội bộ do hệ thống kiểm soát và đối soát khi phát hiện khoảng trống hoặc trạng thái mâu thuẫn.

### 14.9. Giữ hết ngân sách rồi bỏ giao dịch

**Lỗi:** reservation không có thời hạn hoặc không được giải phóng an toàn khi chưa bắt đầu thanh toán.

**Hậu quả:** người dùng chiếm ngân sách để khách khác không sử dụng được.

**Kiểm soát:** TTL cho HELD, hạn mức giữ theo đối tượng, giới hạn tốc độ phù hợp và worker giải phóng có chống trùng. Những biện pháp này không được giải phóng PAYMENT_PENDING chỉ vì hết TTL cũ.

## 15. Đặc tả kiểm thử tình huống tấn công logic

Bảng dưới mô tả các kiểm tra cần có cho chính sách ví dụ. Đây là nội dung học tập, không phải kết quả một bộ test đã chạy.

| Tình huống | Cách tạo điều kiện | Kết quả cần chứng minh |
| --- | --- | --- |
| Hủy thông thường | Hủy campaign ACTIVE phiên bản 18 | Chuyển CANCELLED, tăng version và epoch một lần, có audit và outbox |
| Retry cùng key | Gửi lại cùng key và nội dung sau thành công | Trả operation cũ, không tạo thêm sự kiện hoặc hiệu ứng |
| Key trùng, payload khác | Đổi lý do hoặc phạm vi nhưng giữ key | Báo xung đột, không dùng kết quả cũ cho lệnh mới |
| Key khác, cùng nghiệp vụ | Hủy lại campaign đã CANCELLED | Không tăng epoch lần nữa, không giải phóng gì thêm |
| Phiên bản cũ | Campaign chưa hủy nhưng đã được sửa sau lần người gọi đọc | Từ chối xung đột theo expectedVersion |
| Sai tenant | Dùng ID campaign của tổ chức khác | Từ chối, không lộ chi tiết cấu hình riêng |
| Thiếu quyền thu hồi | Người chỉ có quyền hủy gửi tham số ép hoàn tiền | Từ chối quyền vượt phạm vi |
| Reserve cạnh tranh cancel | Điều khiển hai transaction tranh cùng hàng rào | Reserve được cấp trước hoặc bị chặn sau hủy; không có nhánh đọc cũ rồi cấp mới |
| Báo giá cũ | Có quote trước hủy nhưng chưa reserve | Không tạo reservation sau hủy theo chính sách ví dụ |
| Lượt giữ cũ còn hạn | Có HELD hợp lệ trước hủy, giỏ không đổi | Cho phép bắt đầu thanh toán trong cam kết cũ |
| Giả thời gian | Gửi requestedAt trước mốc hủy cho yêu cầu mới | Không được coi là reservation cũ |
| Lượt giữ hết hạn | Không có payment attempt trước hết hạn | Không thể dùng lại; giải phóng đúng một lần |
| Thanh toán đang chờ | PAYMENT_PENDING vượt thời hạn HELD ban đầu | Không giải phóng chỉ theo TTL cũ |
| Sửa giỏ | Thay đổi sản phẩm hoặc giá trị sau khi giữ ưu đãi | Không dùng cam kết cũ cho giao dịch không còn khớp |
| Callback thành công sau yêu cầu hủy | Cổng xác nhận đã thu tiền trong khi CANCEL_PENDING | Ghi đúng kết quả và xử lý hoàn theo quy trình; không vừa mở slot vừa giữ lợi ích |
| Callback trùng | Lặp cùng sự kiện thành công | Chỉ tiêu thụ reservation một lần |
| Hai event khác ID, cùng hiệu ứng | Cả hai yêu cầu giải phóng cùng reservation | R chỉ giảm một lần |
| Giải phóng ngân sách | R = 300.000, giải phóng reservation 100.000 | R = 200.000; retry vẫn là 200.000 |
| Ngân sách trống sau hủy | Giải phóng tạo thêm khả dụng | Không cấp lượt giữ mới khi campaign CANCELLED |
| Job lên lịch cũ | Hủy SCHEDULED rồi chạy job kích hoạt cũ | Không chuyển CANCELLED về ACTIVE |
| Đơn đã trả | Hủy campaign sau khi đơn đã trả 900.000 | Không đổi giá lịch sử và không tự thu hồi toàn bộ lợi ích |
| Hoàn toàn bộ đơn | Hoàn đơn ví dụ đã trả 900.000 | Tổng tiền hàng hoàn không vượt 900.000 |
| Hoàn dòng A | Hoàn riêng dòng có tiền thực trả 540.000 | Dùng phân bổ đã chốt; không hoàn 600.000 theo giá gốc |
| Điểm PENDING | Hủy đơn trước khi điểm khả dụng rồi chạy job cũ | Điểm bị vô hiệu không được cấp lại |
| Điểm đã dùng | Cần thu hồi 100 điểm nhưng chỉ còn 60 | Ghi đủ phần thiếu 40 theo chính sách, không coi thu hồi hoàn tất sai |
| Crash sau commit | Commit cancel xong nhưng chưa phát sự kiện | Outbox được xử lý lại, hàng rào cấp mới vẫn có hiệu lực |
| Timeout hệ thống ngoài | Không biết yêu cầu hủy thanh toán đã thành công chưa | Giữ trạng thái cần đối soát; không đoán để mở lại quyền |

### 15.1. Kiểm thử theo mô hình trạng thái

Có thể sinh các chuỗi thao tác gồm:

~~~text
quote
reserve
cancelCampaign
startPayment
requestOrderCancellation
paymentSucceeded
paymentFailed
releaseReservation
requestRefund
refundSucceeded
reverseReward
retryPreviousCommand
deliverOldEvent
~~~

Sau mỗi bước, kiểm tra các bất biến thay vì chỉ so HTTP status:

- Không có reservation mới sau hàng rào hủy.
- Không có hai lượt hoạt động hoặc đã tiêu thụ trái giới hạn theo khách.
- Ngân sách không âm và không vượt trần.
- Các khoản hoàn không vượt số tiền đủ điều kiện hoàn.
- Mỗi lợi ích được cấp hoặc thu hồi đúng số lần được phép.
- Trạng thái cuối không bị một sự kiện cũ làm lùi.
- Quyết định giá và lợi ích truy được về snapshot và ledger.

Đặc biệt cần chạy các thứ tự đối nghịch: reserve trước cancel và cancel trước reserve; payment success trước yêu cầu hủy và sau yêu cầu hủy; giải phóng từ job hết hạn cạnh tranh với bắt đầu thanh toán.

Không dùng sleep ngẫu nhiên làm bằng chứng duy nhất cho test đồng thời. Nên điều khiển điểm đồng bộ hoặc cạnh tranh có chủ đích để chứng minh hai nhánh thực sự gặp nhau tại vùng cần bảo vệ.

### 15.2. Phân biệt kết quả HTTP và bất biến tài chính

Hai request có thể đều nhận phản hồi thành công nhưng không nhất thiết tạo hai hiệu ứng: một phản hồi có thể là kết quả đã lưu của lần trước.

Ngược lại, một request nhận lỗi timeout không có nghĩa hiệu ứng chưa xảy ra. Test cần đối chiếu bản ghi campaign, reservation, ngân sách, order, refund và reward ledger sau khi retry hoặc đối soát.

## 16. Quan sát, kiểm toán và khôi phục sau lỗi

### 16.1. Audit của lệnh hủy

Nên ghi:

| Dữ liệu | Mục đích |
| --- | --- |
| tenantId, promotionId | Xác định đúng phạm vi |
| actorId và quyền thực tế | Chứng minh người thao tác được phép |
| operationId và request fingerprint | Liên kết retry và công việc theo sau |
| previousState, newState, version, admissionEpoch | Chứng minh chuyển trạng thái |
| cancelledAt theo máy chủ | Giải thích thời điểm nghiệp vụ |
| mode, reasonCode, approvalId | Giải thích chính sách và thẩm quyền |
| Tập đối tượng hoặc tiêu chí thu hồi | Giới hạn phạm vi của quy trình khẩn cấp |
| Hiệu ứng hoàn tất, thất bại và cần đối soát | Tránh coi chấp nhận lệnh là hoàn tất mọi công việc |

Không ghi token xác thực, khóa webhook hoặc mã bí mật nguyên văn vào audit. Nếu ghi lý do tự do, cần giới hạn độ dài, xử lý ký tự phù hợp và tránh đưa thông tin nhạy cảm không cần thiết.

Hủy không được xóa audit của chính mình. Việc sửa lý do sau này, nếu được phép, cũng phải có lịch sử thay đổi.

### 16.2. Chỉ số phát hiện bất thường

Các tín hiệu đáng theo dõi gồm:

- Reservation được tạo trái hàng rào hủy.
- Chuyển trạng thái bất hợp lệ hoặc callback của reservation đã giải phóng.
- Cùng khách lặp lại chu kỳ giữ ưu đãi, hủy và tạo đơn.
- Ngân sách âm, sai lệch giữa tổng ledger và bộ đếm tổng hợp.
- Nhiều idempotency key khác nhau cho cùng một hiệu ứng nghiệp vụ.
- Tác vụ thu hồi hoặc hoàn tiền ở RECONCILE_REQUIRED quá lâu.
- Job kích hoạt hoặc cache cố dùng version cũ sau hủy.
- Chênh lệch giữa tiền đã thu, đã hoàn và giá thực trả của order snapshot.

Retry nhiều có thể đến từ mạng kém hoặc một consumer gặp sự cố. Cần đánh giá cùng trạng thái và dấu vết để phân biệt lỗi vận hành với hành vi lạm dụng.

### 16.3. Đối soát định kỳ và sửa sai có kiểm soát

Đối soát có thể so sánh:

~~~text
Tổng tiền reservation HELD hoặc đang xử lý thanh toán
    ↔ ngân sách đang giữ

Tổng khoản giảm đã tiêu thụ theo chính sách
    ↔ ngân sách đã tiêu thụ

Các yêu cầu hủy hoặc hoàn đang chờ
    ↔ trạng thái hiện tại tại nhà cung cấp

Reward grant và bút toán thu hồi
    ↔ trạng thái nghiệp vụ của đơn
~~~

Cần quy định rõ trạng thái nào được tính vào từng tổng. Trong ví dụ, hoàn tiền không tự tái sử dụng ngân sách đã tiêu thụ, nên một đơn REFUNDED vẫn có lịch sử khoản giảm đã tiêu thụ.

Nếu tìm thấy sai lệch, tạo điều chỉnh có lý do và quyền hạn, không sửa trực tiếp một con số tổng để che nguồn gốc. Công cụ hỗ trợ và script sửa dữ liệu phải giữ cùng bất biến chống trùng và quyền theo đối tượng.

## 17. Bài tập vận dụng

### Bài tập 1: Viết hợp đồng hủy rõ ràng

Yêu cầu ban đầu: “Hủy campaign ngay; khách nào đang checkout thì xử lý hợp lý”.

Hãy viết lại thành một chính sách trả lời:

1. Quote có phải cam kết được giữ không?
2. Reservation nào được tôn trọng?
3. Đâu là điểm quyết định thứ tự giữa reserve và cancel?
4. Payment attempt chưa có kết quả giữ tài nguyên đến khi nào và đối soát ra sao?
5. API trả kết quả gì khi mới chặn cấp mới nhưng các công việc phụ chưa xong?
6. Ai được đổi từ dừng thông thường sang thu hồi khẩn cấp?

### Bài tập 2: Phân tích một đường tạo lợi ích kép

Một hệ thống có quy trình:

~~~text
POST /orders/{id}/cancel
  đặt order = CANCELLED
  đặt coupon.used = false
  tăng ngân sách khả dụng
  gửi yêu cầu hủy tới cổng thanh toán
~~~

Hãy chỉ ra vì sao việc gửi request ra ngoài ở cuối không chứng minh các thay đổi trước đó an toàn. Thiết kế lại để xử lý cả ba trường hợp: cổng xác nhận đã hủy, cổng xác nhận đã thu tiền và cổng không trả kết quả rõ ràng.

Sau đó thêm hai request cancel đồng thời và một callback thành công đến muộn. Xác định bản ghi nào cần khóa hoặc cập nhật có điều kiện.

### Bài tập 3: Lập bảng hiệu ứng bù trừ

Một đơn có khoản giảm 100.000 đồng, 100 điểm PENDING và một quà chưa xuất kho. Campaign bị hủy nhưng đơn vẫn hợp lệ.

Trước hết, giải thích vì sao hủy campaign thông thường không tự thu hồi ba lợi ích này. Tiếp theo, giả sử khách hủy đơn và được chấp nhận: lập bảng cho từng lợi ích gồm điều kiện thu hồi, nguồn xác nhận, khóa chống lặp và cách xử lý thất bại.

### Bài tập 4: Xây dựng cuộc đua có kiểm soát

Thiết kế hai test:

- Reserve đang giữ khóa trước khi cancel bắt đầu.
- Cancel commit trước khi reserve kiểm tra hàng rào.

Với mỗi test, mô tả trạng thái cuối của campaign, reservation, ngân sách và slot của khách. Không chỉ ghi “một request thành công, một request thất bại”; hãy chứng minh không có quyền hưởng ưu đãi vượt chính sách.

## 18. Những điểm cần ghi nhớ

Promotion cancellation cần một hợp đồng rõ ràng về đối tượng bị hủy, thời điểm chặn cấp mới và cách xử lý cam kết đã tồn tại. Hủy chiến dịch, giải phóng reservation, hủy đơn và hoàn tiền là các nghiệp vụ có liên hệ nhưng có điều kiện chuyển trạng thái riêng.

Máy chủ phải kiểm tra quyền trên đúng đối tượng, bảo vệ cuộc đua reserve/cancel tại điểm có thẩm quyền và lưu trạng thái cùng ledger một cách nguyên tử. Cache, thời gian client gửi hoặc một cờ “đã hủy” không thay thế được các kiểm soát đó.

Khi đã có hiệu ứng bên ngoài, cần quy trình bù trừ và đối soát có thể retry. Giá lịch sử, hạn mức, điểm và quà phải được xử lý theo chính sách đã cam kết, với dấu vết đủ để giải thích từng quyết định.
