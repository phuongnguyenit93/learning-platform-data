# Kiểm thử sửa tham số yêu cầu (Parameter tampering test)

Một giao diện có thể khóa ô giá, ẩn nút phê duyệt và chỉ hiển thị đơn hàng thuộc tài khoản hiện tại. Người gửi vẫn có thể tự tạo request, thay ID trong đường dẫn hoặc thêm trường mà giao diện không bao giờ gửi. Nếu server chấp nhận các giá trị đó làm sự thật nghiệp vụ, một request hợp lệ về cú pháp có thể trở thành cách mua sai giá, tự nâng quyền hoặc bỏ qua một bước bắt buộc.

Trong chương **Security Testing** của module Business Logic Security, parameter tampering test kiểm tra cách server xử lý tham số do phía gọi kiểm soát. Đích kiểm thử là ranh giới tin cậy: **giá trị nào chỉ là ý định của caller, giá trị nào phải được server suy ra, và điều kiện nghiệp vụ nào phải được kiểm tra lại trước khi có hiệu lực?**

## 1. Mục tiêu và phạm vi

Sau bài học, bạn có thể:

- Phân biệt tham số do người dùng được phép chọn với dữ liệu có thẩm quyền từ server.
- Lập ma trận biến đổi tham số theo giá, số lượng, danh tính, đối tượng và trạng thái.
- Thiết kế request đối chứng để phân biệt kiểm thử đi đúng nhánh với lỗi cú pháp hoặc hết phiên.
- Kiểm tra từ chối đúng lý do hoặc xử lý an toàn theo hợp đồng, thay vì chỉ đếm phản hồi HTTP.
- Xác minh dữ liệu đã commit, outbox và hiệu lực bên ngoài sau request bị sửa.
- Kết hợp kiểm thử với object-level authorization, state machine, transaction và idempotency.
- Chuyển một lỗi sửa tham số thành kiểm thử hồi quy có thể tái hiện.

Các ví dụ dùng một API đặt hàng giả lập và fixture kiểm thử cô lập. Không cần lỗi injection: giá trị `total = 1` có thể là JSON hoàn toàn hợp lệ nhưng không phải tổng tiền mà caller được quyền quyết định.

### 1.1. Không coi mọi thay đổi tham số là tấn công

Đổi địa chỉ nhận hàng sang một địa chỉ khác thuộc quyền sử dụng, hoặc tăng số lượng trong phạm vi cho phép, có thể là thao tác hợp lệ. Bài kiểm thử phải chỉ ra quy tắc nào bị đe dọa.

Ví dụ:

- Quantity là đầu vào hợp lệ nhưng phải dương, trong giới hạn và được tính giá lại theo chính sách.
- `shippingAddressId` được chọn bởi caller nhưng phải thuộc phạm vi mà caller được phép sử dụng.
- `unitPrice`, `approvedBy` hoặc `paymentStatus` thường là dữ liệu server quản lý trong luồng đặt hàng của ví dụ.
- `expectedVersion` là một điều kiện cạnh tranh, không phải chứng cứ có quyền sửa đối tượng.

Nếu không định nghĩa quyền sở hữu dữ liệu, test dễ biến thành “thêm bất kỳ trường nào cũng phải lỗi” trong khi hợp đồng thực tế có thể cho phép bỏ qua trường không hỗ trợ một cách an toàn.

## 2. Mô hình đe dọa và ranh giới tin cậy

Giả định người gửi có thể kiểm soát:

- Path, query string, header nghiệp vụ và request body.
- Trường bổ sung không có trong giao diện.
- Giá trị enum, số lượng, ID và cách lồng cấu trúc JSON.
- Thứ tự gửi, gửi lại, gửi dữ liệu cũ và gửi nhiều request cạnh tranh.

Người gửi có thể có tài khoản hợp lệ, biết ID của đối tượng khác hoặc biết giá từ lần đọc trước. Biết ID không đồng nghĩa có quyền sử dụng đối tượng.

Các nguồn thường bị hiểu nhầm là đáng tin:

| Nguồn giá trị | Điều thực sự chứng minh | Điều không tự chứng minh |
|---|---|---|
| Trường bị disable trên giao diện | Giao diện hiện tại không cho nhập | Caller không thể sửa request |
| Hidden input | Giá trị có trong form | Giá trị được server bảo vệ |
| Mobile app do tổ chức phát hành | Có một client chính thức | Mọi request đều đi qua client đó |
| Body chứa userId hoặc tenantId | Caller đề nghị dùng định danh đó | Caller được phép hành động trong scope đó |
| Request đã đăng nhập | Danh tính được xác thực theo cơ chế đăng nhập | Có quyền trên mọi object và mọi thao tác |
| Quote có chữ ký | Payload có thể được bảo vệ toàn vẹn nếu xác minh đúng | Quote còn hạn, đúng chủ thể và chưa bị dùng sai ngữ cảnh |

Một chữ ký hợp lệ chỉ có ý nghĩa trong phạm vi được ký và chính sách xác minh. Nếu quantity, currency, tenant hoặc mục đích sử dụng không nằm trong ràng buộc cần thiết, chữ ký trên một phần dữ liệu không bảo vệ được toàn bộ quyết định.

## 3. Ví dụ xuyên suốt: xác nhận đơn hàng

Fixture có:

- Người dùng A thuộc tenant T1.
- Đơn ORD-A thuộc A và T1, đang APPROVED, version 7.
- Báo giá Q-A-3 có hiệu lực cho đúng đơn, đúng tenant và đúng nội dung đã được duyệt.
- Hai sản phẩm cùng đơn giá 100.000 đồng, giảm giá hợp lệ 20.000 đồng, phí vận chuyển 15.000 đồng.
- Tổng server đã chấp nhận: 200.000 - 20.000 + 15.000 = 195.000 đồng.
- Địa chỉ ADDR-A và phương thức thanh toán PM-A thuộc phạm vi sử dụng hợp lệ của A.

Request đối chứng:

```http
POST /v1/orders/ORD-A/confirm HTTP/1.1
Host: shop.test
Authorization: Bearer <token-cua-A>
Content-Type: application/json
Idempotency-Key: confirm-A-001

{
  "quoteId": "Q-A-3",
  "expectedVersion": 7,
  "shippingAddressId": "ADDR-A",
  "paymentMethodId": "PM-A"
}
```

Hợp đồng của ví dụ:

1. Server xác thực caller và kiểm tra quyền trên đơn.
2. Kiểm tra báo giá, phiên bản, địa chỉ, phương thức thanh toán và bước phê duyệt.
3. Trong transaction thích hợp, chuyển đơn sang PAYMENT_PENDING, tạo payment attempt và outbox event `PaymentRequested`.
4. Trả 202 cho thao tác đã được chấp nhận.
5. Worker dùng adapter thanh toán kiểm thử; kết quả thanh toán cuối được cập nhật theo giao thức riêng.

202 không có nghĩa khoản thanh toán đã thành công. Test kiểm tra thao tác được chấp nhận cần đọc PAYMENT_PENDING và dữ liệu thanh toán tương ứng; test kiểm tra thanh toán hoàn tất cần chờ kết quả cuối theo điều kiện có giới hạn.

### 3.1. Request bị sửa giá

```http
POST /v1/orders/ORD-A/confirm HTTP/1.1
Host: shop.test
Authorization: Bearer <token-cua-A>
Content-Type: application/json
Idempotency-Key: confirm-A-price-test

{
  "quoteId": "Q-A-3",
  "expectedVersion": 7,
  "shippingAddressId": "ADDR-A",
  "paymentMethodId": "PM-A",
  "unitPrice": 1,
  "discount": 199999,
  "total": 1,
  "currency": "USD"
}
```

Luồng confirm của ví dụ không cho caller quyết định các trường giá này. Có hai hợp đồng an toàn thường gặp:

- **Từ chối trường ngoài danh sách cho phép:** trả lỗi cấu trúc/nghiệp vụ đã quy định và không tạo hiệu lực đặt hàng.
- **Bỏ qua trường không có thẩm quyền:** chỉ dùng báo giá và dữ liệu server, kết quả vẫn là 195.000 đồng theo báo giá hợp lệ.

Phải chọn hợp đồng trước khi viết assertion. Một test chấp nhận cả hai cách tùy hứng có thể che việc cấu hình API thay đổi ngoài dự kiến. Các ví dụ code trong bài chọn hợp đồng từ chối trường lạ với mã 400 và business code `UNKNOWN_FIELD`.

Bỏ qua trường chỉ an toàn khi nó bị loại trước mọi quyết định, ghi dữ liệu hoặc tác dụng phụ. Không được thu tiền theo total của client rồi mới sửa lại total trong response.

## 4. Xác định invariant và quyền sở hữu từng trường

### 4.1. Các invariant chính

```text
Mọi thay đổi đơn hàng phải được caller hiện tại cho phép trên đúng đối tượng.

Khoản tiền được yêu cầu thanh toán phải khớp báo giá có hiệu lực
hoặc chính sách tính lại giá đã được định nghĩa phía server.

Chỉ trạng thái và phiên bản hợp lệ mới được chuyển sang PAYMENT_PENDING.

Không có request bị từ chối nào tạo payment attempt, outbox nghiệp vụ
hoặc lệnh thanh toán ngoài hợp đồng.

Một operation gửi lại không tạo thêm hiệu lực thanh toán.
```

Projection nghiệp vụ dùng để kiểm tra request bị từ chối có thể gồm trạng thái đơn, version, số tiền, currency, payment attempt, outbox và yêu cầu đã gửi tới adapter thanh toán. Audit về lần thử bị từ chối có thể tăng, nên không yêu cầu toàn bộ database giống từng byte trước request.

### 4.2. Bảng quyền sở hữu tham số

| Nhóm | Ví dụ | Caller được làm gì? | Server cần kiểm tra gì? |
|---|---|---|---|
| Định danh tài nguyên | orderId trong path | Chọn đối tượng muốn thao tác | Quyền theo object, tenant, trạng thái |
| Lựa chọn có giới hạn | shippingAddressId | Chọn địa chỉ được phép | Quan hệ sở hữu/chia sẻ, khả dụng, tác động tới báo giá |
| Điều kiện cạnh tranh | expectedVersion | Nêu phiên bản caller đã thấy | So khớp ở ranh giới ghi phù hợp |
| Dữ liệu nhập hợp lệ | quantity ở endpoint sửa dòng hàng | Đề nghị số lượng | Kiểu, miền, quota, tồn kho, giá và phê duyệt liên quan |
| Dữ liệu suy ra | subtotal, tax, total | Không quyết định trực tiếp trong luồng này | Tính hoặc đọc từ nguồn có thẩm quyền |
| Dữ liệu quyền | role, ownerId, tenantId | Không tự nâng quyền qua payload | Lấy từ danh tính và quan hệ quyền hợp lệ |
| Dữ liệu quy trình | status, approvedBy, approvedAt | Gửi ý định qua thao tác được cho phép | State machine, phân tách nhiệm vụ, phiên bản |
| Định danh gửi lại | Idempotency-Key | Chọn key trong scope hợp đồng | Scope, fingerprint, replay và quyền đọc kết quả |

Không áp bảng này máy móc cho API quản trị. Một endpoint quản trị giá có thể cho phép sửa unitPrice, nhưng phải có quyền, quy tắc và lịch sử tương ứng. Test phải chỉ rõ endpoint và vai trò đang kiểm tra.

## 5. Lập ma trận biến đổi tham số

Mỗi dòng của ma trận cần có request gốc, biến đổi, caller, trạng thái ban đầu và kỳ vọng. “Thử sửa nhiều field” chưa phải một trường hợp kiểm thử có thể đánh giá.

| Mục tiêu lạm dụng | Biến đổi | Kỳ vọng theo hợp đồng |
|---|---|---|
| Mua sai giá | Thêm total = 1 hoặc unitPrice = 1 | Từ chối hoặc loại bỏ đúng chính sách; không thanh toán giá client |
| Tăng giảm giá | Thêm discount lớn hoặc thay mã ưu đãi | Kiểm tra quyền dùng mã, điều kiện và giới hạn cộng dồn |
| Dùng sai currency | Chuyển currency nhưng giữ số tiền | Không đổi đơn vị tiền ngoài báo giá/chính sách |
| Truy cập đơn người khác | Thay orderId bằng ORD-B | Từ chối truy cập; không đổi ORD-A hay ORD-B |
| Chuyển tenant | Thêm tenantId = T2 | Không mở rộng scope caller |
| Bỏ qua phê duyệt | Thêm status = APPROVED trên đơn SUBMITTED | Không tạo phê duyệt hoặc payment attempt |
| Giả danh người duyệt | Thêm approvedBy hoặc role = ADMIN | Không thay quyết định quyền hoặc lịch sử duyệt |
| Lạm dụng quantity | Gửi 0, âm, quá lớn hoặc sai kiểu | Từ chối đúng miền; không tạo tổng âm hoặc overflow |
| Gắn object không được phép | Đổi addressId hoặc paymentMethodId | Kiểm tra quyền trên từng object tham chiếu |
| Gửi dữ liệu cũ | Giữ quote cũ, thay version | Tôn trọng chính sách báo giá và optimistic concurrency |
| Nhân đôi hiệu lực | Thay key hoặc phát lại payload | Idempotency và invariant chung vẫn đúng |
| Gây mâu thuẫn nguồn | Path ORD-A nhưng body orderId ORD-B | Từ chối hoặc xử lý theo hợp đồng nguồn duy nhất |

Ưu tiên biến đổi một trường để cô lập nguyên nhân, sau đó thử các tổ hợp liên quan: quantity với giá, địa chỉ với phí giao hàng, trạng thái với version, hoặc idempotency key với payload khác.

## 6. Thiết kế request đối chứng và fixture

### 6.1. Chứng minh baseline hợp lệ

Trước khi kết luận một request sửa tham số đã bị chặn, cần biết request gốc có thể đi qua nhánh nghiệp vụ cần kiểm tra.

Một chuỗi kiểm thử tốt:

1. Tạo fixture mới và gửi baseline bằng caller đúng quyền.
2. Xác nhận phản hồi, trạng thái đã commit và dữ liệu server khớp hợp đồng.
3. Tạo fixture tương đương khác cho ca sửa tham số.
4. Chỉ thay điều kiện mà test đang xét.
5. Đối chiếu kết quả và hiệu lực của ca sửa.

Không confirm cùng một đơn thành công rồi dùng chính đơn đó để thử các payload tiếp theo mà không reset. Khi đó mọi request có thể bị chặn vì đơn đã PAYMENT_PENDING, che mất lỗi giá hoặc quyền.

### 6.2. Tách lỗi bảo mật khỏi lỗi request không tới nhánh cần xét

Ví dụ một test sửa total nhận 401 vì token hết hạn. Điều đó không chứng minh server bảo vệ total. Tương tự, lỗi parse JSON không chứng minh object-level authorization đúng.

Cần giữ các điều kiện khác hợp lệ: token, content type, phiên bản, báo giá, các ID liên quan và key mới khi không kiểm tra replay. Với test sai quyền, request phải đủ hợp lệ để kiểm tra đúng trường hợp quyền, đồng thời tránh yêu cầu API tiết lộ chi tiết đối tượng mà caller không được biết.

### 6.3. Truyền nguyên tham số thực sự muốn thử

Một SDK hoặc typed DTO phía test có thể tự bỏ trường lạ trước khi gửi. Nếu test thêm `total` vào object nhưng serializer không đưa nó ra wire, test chưa thử parameter tampering trên server.

Dùng raw request hoặc serializer cho phép gửi đầy đủ cấu trúc đã tạo; xác minh payload thực được gửi khi cần. Với key JSON trùng, thứ tự tham số hoặc biểu diễn raw đặc biệt, phải dùng raw bytes vì map thông thường không giữ được hai key giống nhau.

Fixture cần danh tính riêng cho A, B cùng tenant và C khác tenant. Mọi object đích phải có nguồn gốc rõ trong fixture; không dựa vào dữ liệu tình cờ tồn tại hoặc ID từ môi trường khác.

## 7. Kiểm tra cấu trúc, kiểu và cách phân tích tham số

### 7.1. Trường thiếu, null và giá trị mặc định

Kiểm tra riêng:

- Bỏ trường bắt buộc.
- Gửi null thay vì giá trị.
- Gửi chuỗi rỗng, chuỗi chỉ có khoảng trắng hoặc collection rỗng.
- Gửi enum ngoài tập cho phép.
- Gửi một object thay cho chuỗi hoặc chuỗi thay cho số.

Điểm nguy hiểm không chỉ là parser có báo lỗi hay không. Một giá trị mặc định như `approved = true`, `quantity = 1` hoặc `tenantId = currentTenant` có thể đưa request vào nhánh khác với ý định đã xác nhận. Kỳ vọng phải theo hợp đồng: trường nào bắt buộc, trường nào có default và default có còn thỏa quy tắc nghiệp vụ không.

### 7.2. Trường trùng và nhiều nguồn giá trị

Ví dụ JSON có key trùng:

```json
{
  "quoteId": "Q-A-3",
  "expectedVersion": 7,
  "shippingAddressId": "ADDR-A",
  "paymentMethodId": "PM-A",
  "total": 195000,
  "total": 1
}
```

Các thành phần có thể xử lý key trùng khác nhau: từ chối, chọn đầu hoặc chọn cuối. Không giả định tất cả framework có cùng hành vi. Lỗi nghiệp vụ xuất hiện khi lớp kiểm tra dùng một giá trị còn lớp thực thi dùng giá trị khác.

Các trường hợp cần xét theo những định dạng endpoint thực sự hỗ trợ:

- Query có cùng tên tham số nhiều lần.
- Path và body chứa hai orderId khác nhau.
- Query và body cùng cung cấp quantity.
- Một trường dạng phẳng và một trường lồng nhau cùng biểu diễn giá.
- Header nghiệp vụ bị lặp hoặc chứa giá trị mâu thuẫn.

Hợp đồng nên từ chối sự mơ hồ hoặc quy định nguồn duy nhất. Bài kiểm thử phải xác minh cả lớp nhận request và đường thực thi dùng cùng giá trị đã được kiểm tra. Test parser nội bộ không thay thế kiểm tra qua gateway nếu gateway có bước chuẩn hóa liên quan.

### 7.3. Không để đổi định dạng mở đường khác

Nếu API hỗ trợ JSON và form, kiểm tra quy tắc quyền và nghiệp vụ trên cả hai đường. Nếu API chỉ hỗ trợ JSON, một content type khác phải được xử lý theo chính sách rõ ràng, không rơi vào bộ binding ít kiểm soát hơn.

Trường lồng nhau cũng cần được kiểm tra. Một API từ chối `total` ở cấp trên nhưng tự bind `order.payment.total` vào entity có thể vẫn cho phép thay tổng tiền.

Đây là một dạng mass assignment: server nhận quá nhiều thuộc tính của model lưu trữ so với tập ý định được endpoint cho phép. Việc test cần làm là chứng minh các thuộc tính nhạy cảm không thể được thay đổi qua bất kỳ cấu trúc đầu vào nào mà endpoint nhận.

## 8. Kiểm tra giá, quantity và điều kiện báo giá

### 8.1. Quantity và số học

Ở endpoint cho phép sửa quantity, thử:

```text
quantity = 0
quantity = -1
quantity = 1
quantity = maxAllowed
quantity = maxAllowed + 1
quantity = giá trị rất lớn
quantity = số thập phân khi nghiệp vụ chỉ nhận số nguyên
quantity = chuỗi số nếu hợp đồng yêu cầu kiểu number
```

Giá trị ngoài miền phải bị từ chối mà không thay đổi tồn kho, quota, tổng tiền hay state machine. Giá trị hợp lệ phải được xử lý đúng, để tránh một endpoint từ chối mọi thứ vẫn được coi là bảo mật.

Kiểm tra cả phép nhân và tổng: quantity riêng lẻ có thể nằm trong kiểu dữ liệu nhưng `unitPrice * quantity` hoặc tổng nhiều dòng vượt miền. Oracle nên dùng biểu diễn chính xác đủ lớn, rồi so với giới hạn nghiệp vụ. Không để chính phép tính expected trong test bị overflow.

Không mặc định tăng quantity luôn tăng total theo cùng một tỷ lệ; giá theo bậc, ưu đãi hoặc phí vận chuyển có thể tạo quy tắc khác. Assertion phải dựa trên công thức giá đã xác định cho fixture.

### 8.2. Giá và giảm giá

Thử sửa các trường liên quan ở cả cấp đơn và cấp dòng hàng:

- unitPrice, subtotal, discountAmount, taxAmount, shippingFee, total.
- Mã ưu đãi, danh sách ưu đãi hoặc số lần áp dụng.
- Điểm thưởng hoặc số dư dùng để thanh toán.
- SKU hoặc biến thể sản phẩm nhưng giữ báo giá của sản phẩm cũ.

Đối với mã ưu đãi, một chuỗi code hợp lệ vẫn có thể không dành cho tenant, khách hàng, sản phẩm hoặc thời điểm hiện tại. Cần kiểm tra điều kiện dùng mã, quota, số lượt và quy tắc kết hợp, không chỉ việc mã tồn tại.

Kỳ vọng không nhất thiết là từ chối mọi mã caller nhập. Mã được chọn hợp lệ phải tạo đúng giảm giá do server tính; mã không hợp lệ không được làm giảm khoản thu hoặc tiêu thụ quyền lợi của người khác.

### 8.3. Báo giá cũ và dữ liệu thay đổi

Một kịch bản kiểm thử:

1. A nhận báo giá Q1 cho một tập item, quantity và địa chỉ.
2. Một yếu tố liên quan thay đổi: giá, nội dung giỏ hoặc địa chỉ.
3. A gửi confirm dùng Q1, đồng thời thêm giá cũ hoặc sửa expectedVersion.
4. Kiểm tra chính sách: giữ giá Q1 trong thời gian cam kết, hoặc từ chối để yêu cầu báo giá lại.

Giữ giá cũ có thể đúng nếu đó là cam kết hợp lệ. Lỗi là áp một báo giá cho dữ liệu mà nó không ràng buộc, hoặc cho caller tự chọn phiên bản có lợi ngoài chính sách.

Nếu quote là payload có chữ ký, thử sửa từng trường được bảo vệ, hết hạn, đổi tenant, đổi order, đổi quantity và dùng lại ở thao tác không phù hợp. Một quote chưa bị sửa byte nào vẫn có thể bị dùng sai ngữ cảnh.

## 9. Kiểm tra quyền theo đối tượng và state machine

### 9.1. Thay ID trong path

Tạo ORD-A thuộc A và ORD-B thuộc B. Dùng token của A gọi confirm ORD-B với dữ liệu đủ hợp lệ cho ORD-B nhưng không cấp quyền tương ứng cho A.

Kỳ vọng:

- API từ chối theo chính sách, ví dụ 403 hoặc 404 nhằm hạn chế tiết lộ sự tồn tại.
- Không thay trạng thái, version hay payment attempt của ORD-B.
- Không vô tình cập nhật ORD-A do một trường trong body.
- Response không trả chi tiết giá, địa chỉ hoặc phương thức thanh toán của B.

Test phải chuẩn hóa tập mã cho phép theo hợp đồng của dự án. Không chấp nhận mọi 4xx. Một response 422 vì thiếu trường có thể chưa đi tới phép kiểm tra quyền cần xét.

### 9.2. Thay ID tham chiếu trong body

Giữ orderId của A nhưng thay:

- shippingAddressId bằng địa chỉ của B.
- paymentMethodId bằng phương thức của B.
- quoteId bằng báo giá của order khác hoặc tenant khác.

Mỗi tham chiếu cần được kiểm tra theo quan hệ nghiệp vụ. Có quyền trên order không tự tạo quyền dùng mọi địa chỉ, phương thức thanh toán hay quote. Nếu hệ thống cho chia sẻ một loại đối tượng, fixture phải phân biệt đối tượng được chia sẻ hợp lệ với đối tượng không được phép.

### 9.3. Thêm trường quyền và trạng thái

Trên đơn SUBMITTED chưa được duyệt, gửi:

```json
{
  "quoteId": "Q-SUBMITTED",
  "expectedVersion": 4,
  "shippingAddressId": "ADDR-A",
  "paymentMethodId": "PM-A",
  "status": "APPROVED",
  "approvedBy": "USER-A",
  "role": "ADMIN",
  "skipApproval": true
}
```

Request không được tạo phê duyệt hoặc thanh toán. Tuy nhiên ca này có thể dừng ngay ở bước từ chối trường lạ, chưa chứng minh điều kiện trạng thái được bảo vệ.

Vì vậy cần một ca bổ sung: bỏ toàn bộ trường lạ, giữ nguyên đơn SUBMITTED và gọi thao tác confirm vốn yêu cầu APPROVED. Ca bổ sung phải bị từ chối do chuyển trạng thái không hợp lệ, không tạo tác dụng phụ.

Để thử quy tắc người tạo không tự duyệt, dùng endpoint duyệt thật với caller là người tạo. Thêm `approvedBy` vào endpoint confirm chỉ kiểm tra chống gán thuộc tính, không thay thế test phân tách nhiệm vụ.

### 9.4. Sửa expectedVersion

Thử version cũ, version tương lai, version của đối tượng khác và bỏ version nếu bắt buộc. Một giá trị đúng dạng số không có nghĩa được phép cập nhật.

Sau conflict, nếu ứng dụng tự retry, nó phải đọc lại trạng thái, xét quyền và các điều kiện nghiệp vụ cần thiết. Không được chỉ lấy version mới rồi áp lại quyết định phê duyệt hay mức giá đã hết hiệu lực.

## 10. Ví dụ Java: kiểm thử các trường server quản lý

Ví dụ dùng Java 17 và JUnit 5, gồm test đối chứng và test tham số hóa. Các interface là hợp đồng fixture để nối với API, database và adapter thanh toán thật của môi trường kiểm thử; đây không phải ứng dụng chạy hoàn chỉnh.

Fixture có những quy ước quan trọng:

- Mỗi lần tạo là một đơn APPROVED mới, giá server bằng 195.000 đồng.
- Worker thanh toán được điều khiển; nó chỉ chạy khi fixture được yêu cầu drain.
- `postAsOwner` gửi toàn bộ map ra JSON, kể cả trường lạ; không qua DTO tự bỏ trường.
- `committedProjection` đọc nguồn có thẩm quyền bằng transaction mới.
- `settleWorkForOrder` chờ công việc thuộc đơn kết thúc trong deadline và báo lỗi nếu chưa xác định được kết quả.

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.*;

record HttpResult(int status, String businessCode) {}

record BusinessProjection(
        String orderState,
        long version,
        long total,
        String currency,
        long paymentAttempts,
        long paymentRequestedEvents,
        long externalPaymentRequests,
        long externalPaymentEffects) {}

interface ConfirmFixture extends AutoCloseable {
    Map<String, Object> validBody();
    HttpResult postAsOwner(Map<String, Object> body, String idempotencyKey)
            throws Exception;
    BusinessProjection committedProjection() throws Exception;
    void settleWorkForOrder(Duration timeout) throws Exception;
    @Override void close() throws Exception;
}

abstract class ParameterTamperingTest {
    protected abstract ConfirmFixture newFixture() throws Exception;

    static Stream<Arguments> serverManagedFields() {
        return Stream.of(
                Arguments.of("unitPrice", 1L),
                Arguments.of("total", 1L),
                Arguments.of("currency", "USD"),
                Arguments.of("status", "PAID"),
                Arguments.of("approvedBy", "USER-A"),
                Arguments.of("role", "ADMIN"),
                Arguments.of("tenantId", "TENANT-B"),
                Arguments.of("paid", true)
        );
    }

    @Test
    void validRequestUsesTheApprovedServerQuote() throws Exception {
        try (ConfirmFixture fixture = newFixture()) {
            HttpResult result = fixture.postAsOwner(
                    fixture.validBody(), UUID.randomUUID().toString());

            assertEquals(202, result.status());
            assertEquals("PAYMENT_PENDING", result.businessCode());

            BusinessProjection state = fixture.committedProjection();
            assertAll(
                    () -> assertEquals("PAYMENT_PENDING", state.orderState()),
                    () -> assertEquals(195_000L, state.total()),
                    () -> assertEquals("VND", state.currency()),
                    () -> assertEquals(1L, state.paymentAttempts()),
                    () -> assertEquals(1L, state.paymentRequestedEvents())
            );
        }
    }

    @ParameterizedTest(name = "reject server-managed field: {0}")
    @MethodSource("serverManagedFields")
    void addedFieldCannotChangeBusinessState(
            String field, Object value) throws Exception {

        try (ConfirmFixture fixture = newFixture()) {
            BusinessProjection before = fixture.committedProjection();
            Map<String, Object> tampered =
                    new LinkedHashMap<>(fixture.validBody());
            tampered.put(field, value);

            HttpResult result = fixture.postAsOwner(
                    tampered, UUID.randomUUID().toString());

            assertEquals(400, result.status());
            assertEquals("UNKNOWN_FIELD", result.businessCode());

            fixture.settleWorkForOrder(Duration.ofSeconds(10));
            BusinessProjection after = fixture.committedProjection();
            assertEquals(before, after,
                    "Rejected input must not create a business effect");
        }
    }
}
```

Projection loại audit của request bị từ chối nhưng giữ cả số lệnh gửi tới adapter và hiệu lực thanh toán. Như vậy một lỗi gọi thanh toán rồi trả 400 vẫn làm test thất bại, kể cả khi trạng thái đơn chưa đổi.

Trong ứng dụng cập nhật outbox hoặc projection bất đồng bộ, fixture cần đọc dữ liệu đúng nguồn và chờ đúng công việc. Một hàm drain không thực sự theo dõi producer/consumer liên quan không đủ bảo đảm không còn hiệu lực đến muộn.

Nếu API chọn bỏ qua trường lạ, viết một test khác cho đúng hợp đồng: xác nhận giá trị server, trạng thái và số hiệu lực bằng baseline, đồng thời payload sửa không được lưu hay chuyển sang hệ thống ngoài. Không sửa test trên thành “400 hoặc 202 đều được”.

## 11. Kết hợp sửa tham số với idempotency và cạnh tranh

### 11.1. Cùng key nhưng đổi ý định

Gửi confirm hợp lệ với key K. Sau đó giữ K nhưng đổi quoteId, địa chỉ, phương thức thanh toán hoặc đối tượng đích trong phạm vi endpoint.

Kỳ vọng phụ thuộc fingerprint đã định nghĩa, nhưng không được áp dụng một ý định mới dưới kết quả cũ mà không kiểm tra:

- Nếu đó là thay đổi mang ý nghĩa nghiệp vụ, API phải xử lý xung đột key theo hợp đồng.
- Không tạo payment attempt hay hiệu lực thứ hai.
- Không trả kết quả chứa dữ liệu của một đối tượng mà caller không có quyền đọc.

Scope idempotency phải phù hợp với tenant, loại thao tác và chủ thể theo thiết kế. Hai tenant dùng cùng chuỗi key không được lấy nhầm kết quả của nhau.

Trường lạ bị từ chối ở bước parse có thể không đi tới nhánh kiểm tra fingerprint. Muốn kiểm tra fingerprint, dùng hai payload khác nhau nhưng đều hợp lệ về cấu trúc và cùng đi vào cơ chế idempotency.

### 11.2. Khác key nhưng cùng đe dọa một invariant

Hai request confirm cùng một đơn dùng hai key khác nhau vẫn không được tạo hai khoản thu ngoài quy tắc. Key chống gửi lại một ý định không thay thế việc bảo vệ state machine của đơn.

Tương tự, hai mã ưu đãi khác nhau có thể đều hợp lệ riêng lẻ nhưng không được cộng dồn. Đổi key không được làm biến mất quy tắc tổng.

### 11.3. Dữ liệu thay đổi giữa kiểm tra và ghi

Một test có thể giữ request A tại điểm sau khi đọc version và giá. Request B sửa nội dung đơn hoặc làm mất hiệu lực phê duyệt, rồi commit. Sau đó cho A tiếp tục.

Kỳ vọng:

- A bị conflict hoặc xét lại đầy đủ theo chính sách.
- Không thanh toán cho dữ liệu chưa được duyệt.
- Không ghi đè thay đổi mới bằng payload cũ.
- Quyền theo đối tượng được đánh giá lại nếu chính sách yêu cầu tại lần thử ghi mới.

Điểm đồng bộ cần phù hợp cơ chế khóa, không tạo barrier buộc worker đi qua khóa do worker khác đang giữ. Start gate chỉ giúp request xuất phát gần nhau; nó không chứng minh lịch “cả hai đọc cùng dữ liệu cũ” đã xảy ra.

Mỗi worker phải có kết quả hoặc ngoại lệ được thu nhận, cùng deadline. Timeout không đồng nghĩa request không có hiệu lực; cần truy vết trạng thái và cô lập tác vụ còn chạy trước khi cleanup.

### 11.4. Mất phản hồi rồi gửi lại

Gây mất phản hồi sau khi transaction confirm đã commit. Client gửi lại cùng key và ý định.

Test phải tìm về operation cũ và không tạo thêm hiệu lực. Nếu sau đó client sửa total hoặc dùng key khác, server vẫn phải giữ quy tắc giá và trạng thái như một request độc lập. Kết quả của lần đầu không trở thành quyền được bỏ qua validation ở lần sau.

## 12. Quy trình chạy một ca kiểm thử đầy đủ

### Bước 1: Ghi giả thuyết nghiệp vụ

Ví dụ: “Caller có thể làm server dùng total trong body thay vì số tiền của báo giá đã duyệt”.

Ghi rõ endpoint, caller, field, giá trị gốc, biến đổi, trạng thái đầu và invariant. Giả thuyết càng rõ thì bằng chứng càng dễ đánh giá.

### Bước 2: Tạo fixture và snapshot trước

Ghi nhận đơn, phiên bản, báo giá, chủ thể và các object tham chiếu. Đọc projection nghiệp vụ trước request, gồm các bản ghi/tác dụng phụ có liên quan.

Với dữ liệu bất đồng bộ, xác nhận fixture đã ở trạng thái khởi đầu ổn định. Không dùng hàng đợi còn công việc từ test trước.

### Bước 3: Chạy đối chứng

Trên fixture tương đương, baseline hợp lệ phải tạo đúng kết quả. Nếu baseline fail, sửa fixture hoặc điều kiện test trước khi kết luận về tham số.

### Bước 4: Thực hiện biến đổi có kiểm soát

Đổi một yếu tố để kiểm tra ban đầu. Với test quyền, thay danh tính hoặc object đích theo kế hoạch. Với test replay, giữ hoặc đổi key có chủ đích.

Đảm bảo payload thực sự chứa biến đổi. Không để HTTP client tự sửa content type, lọc trường hoặc hợp nhất key trùng theo cách làm mất điều đang kiểm thử.

### Bước 5: Thu kết quả trực tiếp

Lưu status, business code và các trường response có ý nghĩa. Kiểm tra lỗi không làm lộ thông tin nhạy cảm ngoài phạm vi caller được biết.

Không dùng phản hồi làm nguồn duy nhất để quyết định có hiệu lực hay không. Request báo lỗi vẫn có thể đã tạo tác dụng phụ do transaction hoặc xử lý ngoại lệ sai.

### Bước 6: Đọc trạng thái và chờ phần bất đồng bộ

Đọc nguồn có thẩm quyền sau commit; theo dõi operation/correlation ID và chờ điều kiện cuối trong deadline. Kiểm tra:

- Order có còn đúng owner, tenant, version và trạng thái không?
- Tổng tiền, currency và các khoản thành phần có đúng nguồn server không?
- Có payment attempt, outbox hoặc thay đổi quota/tồn kho ngoài dự kiến không?
- Adapter bên ngoài đã nhận lệnh nào, với số tiền, currency và định danh nào?
- Có hiệu lực lặp khi retry hoặc giao lại thông điệp không?

Nếu kiểm tra một request được chấp nhận theo hợp đồng bỏ qua trường lạ, phải kiểm tra cả payload ra hệ thống ngoài. Tổng tiền trong database đúng chưa chứng minh số tiền thực sự gửi đi cũng đúng.

### Bước 7: Kết luận theo invariant

Kết luận “không khai thác được với ca này” khi biến đổi đã được gửi, kỳ vọng hợp đồng đúng và dữ liệu/tác dụng phụ đều thỏa invariant. Không suy rộng một ca đậu thành mọi biến thể đều an toàn.

Nếu có lỗi, lưu phản ví dụ nhỏ nhất và chuyển thành kiểm thử hồi quy. Khi chưa biết request có commit hay không, báo kết quả chưa xác định thay vì tự coi là không có hiệu lực.

## 13. Thu thập bằng chứng và phân loại kết quả

### 13.1. Một bản ghi kiểm thử hữu ích

```text
Case: PT-PRICE-001
Endpoint: POST /v1/orders/{id}/confirm
Caller: owner hợp lệ của order trong fixture
Initial state: APPROVED, version 7
Baseline amount: 195000 VND
Mutation: thêm total = 1
Contract: từ chối field không được hỗ trợ

Expected:
    400, UNKNOWN_FIELD
    order projection không đổi
    không có payment attempt hoặc PaymentRequested mới
    không có yêu cầu/hiệu lực thanh toán ngoài

Evidence:
    request thực gửi đã ẩn token
    response status và business code
    snapshot trước/sau từ nguồn có thẩm quyền
    operation/correlation ID và trạng thái worker liên quan
```

Nếu API chọn bỏ qua trường lạ, expected phải được viết lại thành kết quả hợp lệ theo giá server, không dùng mẫu từ chối trên.

Log cần đủ để tái hiện nhưng phải loại token, bí mật và dữ liệu cá nhân không cần thiết. Tên logic như USER-A, ORD-A giúp diễn giải; ID thật của fixture có thể được lưu ở môi trường test với quyền truy cập phù hợp.

### 13.2. Phân loại điều quan sát được

| Quan sát | Ý nghĩa | Hành động tiếp theo |
|---|---|---|
| Từ chối đúng hợp đồng, không hiệu lực | Ca kiểm thử đạt | Giữ làm hồi quy |
| Bỏ qua field đúng hợp đồng, dùng dữ liệu server | Ca kiểm thử đạt | Kiểm tra cả downstream theo phạm vi test |
| Response lỗi nhưng có hiệu lực trái phép | Lỗi nghiệp vụ hoặc tính nguyên tử | Giữ trace, thu nhỏ ca lỗi |
| Request đổi object nhưng nhận dữ liệu không có quyền | Lỗi phân quyền hoặc rò dữ liệu | Kiểm tra scope và quyền từng tham chiếu |
| 401 vì token không hợp lệ | Chưa chứng minh điều muốn kiểm tra | Sửa điều kiện xác thực |
| 500 hoặc timeout | Lỗi hoặc kết quả chưa rõ | Truy vết commit, worker và adapter |
| Không thấy field sửa trên wire | Test chưa gửi đúng biến đổi | Sửa client/serializer kiểm thử |
| Snapshot đến từ cache/replica chưa cập nhật | Nguồn đo chưa đủ tin cậy | Đọc đúng nguồn hoặc chờ hội tụ có điều kiện |

Mã 500 không phải kết quả từ chối hợp lệ mặc định. Nó có thể là lỗi xử lý đầu vào, cũng có thể che hiệu lực đã xảy ra; cần phân tích thay vì đếm như một hàng “blocked”.

## 14. Chuyển lỗi thành kiểm thử hồi quy và sửa đúng lớp

### 14.1. Thu nhỏ lỗi

Giả sử request có nhiều trường thêm vào và server thu 1 đồng. Thử giữ baseline rồi chỉ thêm total = 1 trên fixture mới.

Nếu vẫn sai, có một phản ví dụ nhỏ. Nếu không, thêm lại các trường theo nhóm có ý nghĩa để tìm tương tác, ví dụ total cùng currency hoặc status cùng skipApproval. Không xóa một điều kiện cần rồi gọi lỗi khác là cùng nguyên nhân.

Với quyền theo object, giữ cặp danh tính–đối tượng rõ ràng. Đừng thay ID tồn tại bằng ID bất kỳ, vì response “không tìm thấy” không còn kiểm tra việc caller không có quyền trên object có thật.

### 14.2. Những cơ chế sửa cần được xác minh

| Nguyên nhân | Hướng bảo vệ | Bằng chứng hồi quy cần giữ |
|---|---|---|
| Bind request vào entity quá rộng | DTO/command chỉ chứa ý định được phép | Trường nhạy cảm bị từ chối hoặc bị loại trước xử lý |
| Tin giá từ caller | Tính/đọc giá từ nguồn có thẩm quyền | Giá lưu và payload thanh toán đúng báo giá |
| Chỉ kiểm tra đăng nhập | Quyền theo object và tenant | Caller khác không đọc/đổi được object |
| Cho client gán trạng thái | Command nghiệp vụ và state machine phía server | Đơn sai trạng thái không tạo hiệu lực |
| Xét quyền rồi ghi tách rời | Điều kiện phiên bản, khóa hoặc cơ chế transaction phù hợp | Dữ liệu thay đổi xen giữa không vượt quy tắc |
| Chống trùng chỉ theo key toàn cục | Scope và fingerprint đúng | Hai tenant không trộn kết quả, key khác vẫn giữ invariant |
| Các parser dùng giá trị khác nhau | Từ chối mơ hồ hoặc nguồn tham số thống nhất | Cùng dữ liệu được kiểm tra và được sử dụng |

Một annotation validation có thể bảo vệ miền số nhưng không tự chứng minh caller được dùng một object. Một transaction có thể giữ các lần ghi nguyên tử nhưng không tự khiến giá client thành dữ liệu đúng. Kiểm thử phải bám từng quy tắc được bảo vệ.

### 14.3. Giữ assertion theo hành vi

Test hồi quy nên yêu cầu “không thể tạo thanh toán sai giá”, không buộc phải gọi một hàm có tên cụ thể. Khi implementation thay đổi, test vẫn cần phát hiện lỗi nghiệp vụ.

Đối với những chỗ hợp đồng bắt buộc cụ thể như UNKNOWN_FIELD hoặc conflict, giữ assertion chính xác để tránh thay đổi ngoài ý muốn. Khi sản phẩm quyết định đổi hợp đồng, cập nhật cả mô tả API, test đối chứng và test biến đổi.

## 15. Bài thực hành

Xây hoặc dùng một API xác nhận đơn trong môi trường kiểm thử. Tạo ba caller:

- A sở hữu ORD-A trong T1.
- B sở hữu ORD-B trong T1.
- C sở hữu ORD-C trong T2.

Tạo báo giá, địa chỉ và phương thức thanh toán tương ứng. Cố định các khoản tiền ở fixture để expected không phụ thuộc dữ liệu thị trường hoặc dịch vụ thật.

Hoàn thành các ca:

1. Baseline confirm hợp lệ của A.
2. Thêm total thấp hơn và currency khác vào request A.
3. Gửi quantity bằng 0, âm và vượt giới hạn qua endpoint thật sự hỗ trợ quantity.
4. Dùng token A confirm ORD-B và ORD-C.
5. Giữ ORD-A nhưng tham chiếu địa chỉ hoặc phương thức thanh toán không được phép.
6. Thêm trạng thái/phân quyền giả vào đơn chưa duyệt.
7. Gọi confirm đơn chưa duyệt bằng payload sạch, không có trường lạ.
8. Dùng báo giá không còn phù hợp theo chính sách đã chọn.
9. Gửi cùng key với một payload hợp lệ khác về ý nghĩa.
10. Gửi hai key khác nhau cho cùng thao tác không được phép có hiệu lực hai lần.

Với mỗi ca, ghi request đối chứng, biến đổi, kỳ vọng response, projection trước/sau và tác dụng phụ. Chọn một lỗi trong bản triển khai cố ý sai, thu nhỏ request và viết test hồi quy.

Phần mở rộng: thêm raw request có tham số trùng hoặc nguồn path/body mâu thuẫn. Chỉ đánh giá các định dạng mà hệ thống thực sự hỗ trợ và ghi rõ hành vi mong đợi tại ranh giới nhận request.

## 16. Checklist hoàn thành

- [ ] Endpoint, caller, tenant, object và trạng thái đầu được xác định.
- [ ] Baseline hợp lệ đi qua được nhánh nghiệp vụ cần kiểm tra.
- [ ] Quyền sở hữu từng field và nguồn dữ liệu có thẩm quyền đã được ghi rõ.
- [ ] Test đã gửi đúng payload sửa, không bị SDK tự loại bỏ.
- [ ] Có ca sửa giá, quyền, object tham chiếu và trạng thái theo phạm vi endpoint.
- [ ] Quantity, kiểu số, giá trị biên và nguy cơ overflow được kiểm tra.
- [ ] Trường thiếu, null, cấu trúc lồng và tham số mâu thuẫn được xét khi liên quan.
- [ ] Hợp đồng từ chối hoặc bỏ qua field được chọn trước, không chấp nhận tùy ý cả hai.
- [ ] Assertion kiểm tra đúng nhóm lỗi, không coi mọi 4xx/5xx là đạt.
- [ ] Dữ liệu đã commit và tác dụng phụ được kiểm tra, không chỉ response.
- [ ] Quyền được kiểm tra trên từng object tham chiếu, không chỉ order chính.
- [ ] Có test state machine bằng payload sạch để tránh lỗi parser che mất lỗi quy trình.
- [ ] Idempotency có scope, fingerprint và test khác key trên cùng invariant.
- [ ] Kịch bản bất đồng bộ/cạnh tranh có deadline và xử lý kết quả chưa xác định.
- [ ] Phản ví dụ được thu nhỏ, lưu trace an toàn và trở thành test hồi quy.

Parameter tampering test có giá trị khi chứng minh được server duy trì quyền quyết định đối với giá, quyền truy cập và chuyển trạng thái. Request có thể bị thay đổi ở bất kỳ lớp đầu vào nào, nhưng dữ liệu được ghi và hiệu lực cuối cùng phải xuất phát từ ý định được cho phép, trong đúng phạm vi đối tượng và theo đầy đủ quy tắc nghiệp vụ.
