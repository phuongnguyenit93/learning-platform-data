# Plan transition: chuyển gói thuê bao an toàn theo quy tắc nghiệp vụ

## 1. Chuyển gói là một quy trình nghiệp vụ

Trong chương **Subscription Rules**, plan transition là quá trình đưa một thuê bao từ cấu hình gói hiện tại sang cấu hình gói đích. Quá trình này có thể thay đổi giá, chu kỳ tính phí, số lượng thành viên, hạn mức sử dụng, quyền truy cập tính năng và thời điểm có hiệu lực.

Một API chỉ thực hiện `subscription.plan = request.plan` thường bỏ qua các điều kiện quyết định tính hợp lệ của thay đổi: ai được đổi, gói nào được mua, thanh toán đã được xác nhận chưa, tài nguyên hiện có có phù hợp với gói đích không và một yêu cầu gửi lại có tạo thêm quyền lợi không.

Ví dụ xuyên suốt:

| Thuộc tính | Starter | Pro |
| --- | --- | --- |
| Số thành viên tối đa | 10 | 50 |
| Tính năng xuất báo cáo nâng cao | Không | Có |
| Giá một kỳ minh họa | 100.000 đơn vị tiền tệ nhỏ nhất | 300.000 đơn vị tiền tệ nhỏ nhất |
| Chu kỳ | Cùng một loại chu kỳ trong ví dụ | Cùng một loại chu kỳ trong ví dụ |

Chính sách tham chiếu trong bài:

- Thuê bao đang `ACTIVE` mới được đổi gói qua luồng này.
- Nâng cấp có khoản phải trả chỉ có hiệu lực sau khi xác nhận khoản thanh toán phù hợp.
- Hạ cấp được lên lịch cuối kỳ và phải qua kiểm tra khả năng áp dụng tại thời điểm đó.
- Mỗi thuê bao chỉ có một transition chưa kết thúc.
- Thay đổi quyền có hiệu lực và trạng thái transition được commit cùng một transaction cục bộ.
- Đổi gói không tự đặt lại lượng sử dụng, quyền dùng thử hoặc ưu đãi đã nhận.

Đây là một chính sách ví dụ để học bảo mật logic nghiệp vụ. Sản phẩm khác có thể chọn thời điểm áp dụng hoặc cách xử lý chênh lệch giá khác, nhưng phải mô hình hóa chúng thành quy tắc rõ ràng.

## 2. Phân biệt các khái niệm dễ bị gộp sai

### 2.1. Gói, giá, thuê bao và quyền sử dụng

**Plan version** là phiên bản bất biến của một cấu hình gói. Nó xác định tính năng và giới hạn. Nếu sửa chính sách bán cho khách mới, tạo phiên bản mới thay vì âm thầm đổi nội dung mà các giao dịch trước đó đã tham chiếu.

**Price version** xác định giá, đơn vị tiền tệ, chu kỳ, số lượng tính phí và các điều kiện thương mại tương ứng. Hai khách có cùng tên gói chưa chắc có cùng price version.

**Subscription** là quan hệ thuê bao của một chủ thể trong một tenant, bao gồm gói đang có hiệu lực, trạng thái thanh toán, kỳ hiện tại và phiên bản trạng thái nghiệp vụ.

**Transition** là một yêu cầu thay đổi có định danh, trạng thái và lịch sử riêng. Nó có thể đang chờ thanh toán hoặc chờ thời điểm áp dụng, trong khi subscription vẫn dùng gói cũ.

**Entitlements** là tập quyền thực tế hệ thống cho phép tại thời điểm xử lý: tính năng, hạn mức, số thành viên và các quyền tài nguyên liên quan.

Không dùng tên hiển thị như “Pro” làm định danh giá hoặc bằng chứng quyền truy cập. Không suy quyền từ gói mà người dùng vừa chọn trên giao diện.

### 2.2. Được tiếp nhận chưa có nghĩa là đã áp dụng

Một response `202 Accepted` có thể chỉ xác nhận transition đã được ghi nhận. Nó không chứng minh thanh toán thành công hoặc quyền đã thay đổi.

~~~text
Người dùng chọn Pro
    → Server kiểm tra và tạo transition
    → Chờ thanh toán
    → Xác nhận thanh toán có thẩm quyền
    → Áp dụng quyền Pro
~~~

Với hạ cấp cuối kỳ:

~~~text
Người dùng chọn Starter
    → Server kiểm tra và tạo lịch
    → Thuê bao vẫn dùng Pro trong phần kỳ còn lại
    → Đến thời điểm hiệu lực, kiểm tra lại điều kiện
    → Áp dụng Starter và phối hợp cập nhật kỳ tính phí
~~~

Phải cho client thấy rõ `currentPlan`, `pendingPlan`, `transitionStatus` và `effectiveAt`. Một trường `plan` duy nhất dùng cho cả “đã chọn”, “đã thanh toán” và “đang có hiệu lực” rất dễ tạo lỗi quyền.

## 3. Business invariants của chuyển gói

### 3.1. Một trạng thái có hiệu lực tại một thời điểm

Đối với mỗi subscription:

~~~text
Tại một thời điểm quyết định:
  Có đúng một phiên bản gói đang có hiệu lực.
  Có tối đa một transition chưa kết thúc.
  Quyền truy cập được suy từ trạng thái có hiệu lực và chính sách hiện hành.
~~~

Nếu quyền được lưu ở bảng hoặc cache khác, phải có cơ chế liên kết phiên bản để tránh đọc gói mới với quyền cũ hoặc ngược lại.

Hai nâng cấp đồng thời không được cùng tính toán từ một trạng thái cũ rồi mỗi lần ghi đè kết quả của lần kia. Một yêu cầu hạ cấp đang chờ cũng không được tự động bị thay thế bởi một request khác nếu sản phẩm chưa có quy tắc hủy hoặc thay lịch.

### 3.2. Chuyển từ nguồn đúng sang đích đúng

Một transition cần gắn với:

- Tenant và subscription cụ thể.
- Phiên bản trạng thái nguồn, gói nguồn và kỳ nguồn.
- Gói đích cùng phiên bản giá đã được chấp nhận.
- Chế độ áp dụng: ngay hoặc tại ranh giới kỳ.
- Người yêu cầu, quyền hoặc phê duyệt cần thiết.
- Báo giá có hiệu lực và định danh nghiệp vụ.
- Khoản thanh toán hoặc điều chỉnh tài chính liên quan, nếu có.

Điều kiện áp dụng có thể diễn đạt:

~~~text
transition.tenant = subscription.tenant
transition.subscription = subscription.id
transition.source_revision = subscription.effective_revision
transition.source_plan_version = subscription.current_plan_version

target_plan được phép cho tenant và chủ thể
subscription đang ở trạng thái được phép
thời điểm áp dụng và điều kiện thanh toán đều hợp lệ
~~~

Trong bài, `effective_revision` tăng khi có thay đổi ảnh hưởng quyết định nghiệp vụ như gói hiệu lực, trạng thái thuê bao, kỳ hoặc số lượng tính phí. Việc chỉ ghi một transition đang chờ chưa làm đổi gói nên không tự tăng revision này; hàng subscription vẫn được khóa để bảo vệ thao tác.

Mọi đường ghi thay đổi dữ kiện liên quan phải tăng revision hoặc tham gia một cơ chế kiểm tra tương đương. Một bộ đếm được bỏ qua bởi tác vụ gia hạn hoặc endpoint quản trị không còn bảo vệ được báo giá và transition.

### 3.3. Quyền cao hơn phải có căn cứ hợp lệ

Nếu chính sách yêu cầu thanh toán trước:

~~~text
Quyền mới có hiệu lực
  ⇒ Có transition hợp lệ
  ∧ Có xác nhận thanh toán khớp transition
  ∧ Transition được áp dụng đúng một lần
~~~

Thông báo “thanh toán thành công” từ trình duyệt không phải xác nhận có thẩm quyền. Tham số trên URL chuyển hướng, một nút “Tôi đã thanh toán” hoặc một trường `paymentStatus` từ client đều không đủ.

Ngược lại, một giao dịch tiền đã được nhà cung cấp xác nhận nhưng chưa áp dụng quyền không được bỏ quên. Hệ thống phải có trạng thái và quy trình phục hồi hoặc bù trừ phù hợp.

### 3.4. Không nhân bản quyền lợi theo số lần đổi gói

Đổi gói không tự tạo một người dùng mới hoặc một kỳ ưu đãi mới. Những bất biến bổ sung có thể là:

~~~text
Một quyền dùng thử chỉ được cấp theo danh tính đủ điều kiện của chương trình.
Một transition chỉ tạo tối đa một hiệu ứng cấp quyền.
Lượng đã sử dụng trong kỳ không giảm chỉ vì đổi tên gói.
Một khoản thanh toán không bảo chứng cho nhiều transition độc lập.
~~~

Nếu gói Pro có hạn mức 1.000 lượt và khách đã dùng 400 lượt trong kỳ, chuyển giữa các gói không được mặc nhiên đưa `used` về 0. Phải định nghĩa cách tính quyền còn lại theo cùng kỳ hoặc theo giao dịch cấp bổ sung có nguồn rõ ràng.

## 4. Ranh giới tin cậy và phân quyền theo đối tượng

### 4.1. Client gửi ý định, server quyết định điều kiện

Payload yêu cầu báo giá có thể chỉ chứa:

~~~json
{
  "targetPlanVersionId": "plan-pro-v3",
  "applyMode": "IMMEDIATE"
}
~~~

Payload chấp nhận một báo giá có thể là:

~~~http
POST /subscriptions/{subscriptionId}/transitions
Idempotency-Key: <client-generated-key>
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "quoteId": "quote-123",
  "expectedRevision": 7
}
~~~

Server phải đọc các dữ kiện có thẩm quyền thay vì nhận chúng như sự thật từ request:

~~~json
{
  "tenantId": "tenant-khac",
  "currentPlan": "Starter",
  "newPrice": 1,
  "alreadyPaid": true,
  "skipApproval": true,
  "newSeatLimit": 9999,
  "newPeriodEnd": "2099-01-01T00:00:00Z"
}
~~~

Không bind payload tùy ý vào entity subscription. DTO chỉ nên cho phép các trường biểu đạt ý định; giá, quyền, trạng thái và mốc kỳ phải được xác định tại server.

`expectedRevision` do client gửi là một điều kiện lạc quan cần so sánh với dữ liệu hiện tại, không phải quyền thay thế revision trong cơ sở dữ liệu.

### 4.2. Phân quyền phải gắn với subscription cụ thể

Role `BILLING_ADMIN` có thể là điều kiện cần, nhưng còn phải kiểm tra:

- Actor đang thao tác trong tenant đã được xác thực.
- Subscription thuộc tenant đó.
- Actor được quản lý thanh toán cho subscription hoặc tài khoản liên quan.
- Gói đích được bán cho nhóm khách và khu vực kinh doanh tương ứng.
- Nếu phải phê duyệt, actor và quyết định phê duyệt thỏa mãn chính sách.

Ví dụ truy vấn lấy đối tượng:

~~~sql
SELECT *
FROM subscription
WHERE tenant_id = :verified_tenant_id
  AND subscription_id = :subscription_id;
~~~

Không truy vấn chỉ bằng ID rồi cho rằng UUID khó đoán sẽ chống thao tác sai quyền. Các API tạo quote, chấp nhận quote, xem transition, hủy lịch và đọc kết quả idempotency đều cần kiểm tra quyền trên đối tượng.

Nếu quyền có thể bị thu hồi trong lúc lệnh chờ, phải định nghĩa thời điểm quyết định và điểm đồng bộ. Kiểm tra role ở controller rồi chờ nhiều giây không chứng minh rằng actor vẫn có quyền khi thay đổi được chấp nhận.

### 4.3. Gói đích cũng là một đối tượng được bảo vệ

Không phải mọi plan ID hợp lệ đều là gói người dùng được mua. Có thể tồn tại gói thử nghiệm, gói nhân viên, gói cũ chỉ dành cho khách giữ hợp đồng hoặc gói yêu cầu ký kết riêng.

Server phải kiểm tra khả năng chuyển **từ nguồn sang đích**. Một danh sách gói hiển thị trên UI không thay thế kiểm tra ở endpoint ghi.

Quyền mua gói, quyền thay giá và quyền cấp ưu đãi là các quyền khác nhau. Cho phép quản lý thuê bao không có nghĩa cho phép tự sửa giá gói.

## 5. Báo giá phải gắn với trạng thái và thời gian

### 5.1. Nội dung một quote có thể kiểm chứng

Một quote dùng để chấp nhận chuyển gói nên lưu tối thiểu:

| Nhóm dữ liệu | Ví dụ |
| --- | --- |
| Chủ thể | Tenant, subscription, đối tượng thanh toán |
| Nguồn | Effective revision, gói nguồn, kỳ nguồn, số lượng đang tính phí |
| Đích | Plan version, price version, số lượng đích |
| Thời điểm | Thời điểm tính, thời điểm hiệu lực, thời hạn chấp nhận |
| Tài chính | Đơn vị tiền tệ, khoản ghi nợ, khoản ghi có, số tiền cần thanh toán |
| Chính sách | Phiên bản chính sách tính chênh lệch, ưu đãi và điều kiện phê duyệt |
| Kiểm soát lặp | Quote ID, trạng thái chấp nhận, transition đã liên kết |

Nếu báo giá được ký để client mang theo, chữ ký chỉ bảo vệ tính toàn vẹn của nội dung. Server vẫn phải kiểm tra tenant, quyền, trạng thái nguồn, thời hạn và việc quote đã được sử dụng.

### 5.2. Tính chênh lệch tại server

Với ví dụ đơn giản, cùng đơn vị và chu kỳ, không xét các thành phần tài chính khác:

~~~text
Giá Starter: 100.000
Giá Pro:     300.000
Tỷ lệ thời gian còn lại: 12/30

Chênh lệch minh họa:
  (300.000 - 100.000) × 12/30 = 80.000
~~~

Không triển khai tính chênh lệch bằng cách tin số tiền client gửi. Trong sản phẩm thật cần định nghĩa cách đo phần kỳ còn lại, giá đang được áp dụng cho khách, số lượng, ưu đãi, khoản ghi có và cách làm tròn.

Lưu số tiền bằng số nguyên theo đơn vị tiền tệ nhỏ nhất phù hợp, hoặc kiểu thập phân chính xác theo miền nghiệp vụ. Không dùng `double` cho phép tính tiền cần chính xác. Kiểm tra tràn số trước khi nhân, chia và cộng các thành phần.

Nếu giá thay đổi sau khi quote được tạo, chính sách phải chọn rõ: giữ giá đã báo trong thời hạn, hoặc yêu cầu báo giá mới. Không thu một giá nhưng cấp quyền hoặc ghi sổ theo giá khác mà không có quyết định minh bạch.

### 5.3. Quote cũ phải thất bại có kiểm soát

Sau khi tạo quote, các sự kiện sau có thể làm nó không còn áp dụng được:

- Subscription đã đổi gói qua một lệnh khác.
- Kỳ hiện tại đã kết thúc hoặc chuyển sang kỳ mới.
- Số lượng tính phí đã thay đổi.
- Ưu đãi hết hiệu lực hoặc đã được dùng.
- Trạng thái chuyển sang quá hạn thanh toán.
- Gói đích không còn được bán theo chính sách đã chọn.

Lúc chấp nhận quote, khóa subscription và quote, rồi so sánh các điều kiện nguồn. Nếu không khớp, trả lỗi yêu cầu báo giá lại; không tự chuyển quote sang trạng thái nguồn mới để làm cho nó “hợp lệ”.

Đối với thời hạn, dùng đồng hồ server hoặc cơ sở dữ liệu và kiểm tra tại thời điểm quyết định sau khi chờ khóa. Không sử dụng thời gian do client khai báo. Cần quy định rõ mốc cuối là bao gồm hay loại trừ, ví dụ chấp nhận khi `now < expires_at`.

## 6. State machine cho transition

Trạng thái subscription và trạng thái transition là hai trục khác nhau. Một subscription `ACTIVE` có thể có transition `WAITING_PAYMENT`; điều đó không cho phép cấp quyền đích ngay.

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> WAITING_PAYMENT: Cần thanh toán trước
    REQUESTED --> SCHEDULED: Hạ cấp cuối kỳ
    REQUESTED --> APPLIED: Được phép áp dụng ngay và không cần thu thêm
    WAITING_PAYMENT --> READY: Xác nhận thanh toán phù hợp
    WAITING_PAYMENT --> FAILED: Xác nhận thất bại cuối cùng
    READY --> APPLIED: Kiểm tra lại và commit quyền
    READY --> REVIEW_REQUIRED: Nguồn hoặc điều kiện đã thay đổi
    SCHEDULED --> APPLIED: Đến hạn và đủ điều kiện
    SCHEDULED --> CANCELLED: Hủy hợp lệ trước khi áp dụng
    SCHEDULED --> REVIEW_REQUIRED: Không thể áp dụng an toàn
    APPLIED --> [*]
    FAILED --> [*]
    CANCELLED --> [*]
~~~

`REVIEW_REQUIRED` chặn việc cấp quyền tự động cho đến khi một quy trình đối soát hoặc xử lý có thẩm quyền giải quyết. Nó không có nghĩa được bỏ qua tiền đã thu hoặc giữ khách vô thời hạn mà không có hướng xử lý.

### 6.1. Mỗi cạnh có điều kiện riêng

Ví dụ:

- `REQUESTED → WAITING_PAYMENT`: quote được chấp nhận hợp lệ và cần một khoản thanh toán.
- `WAITING_PAYMENT → READY`: khoản thanh toán có thẩm quyền khớp chủ thể, transition, số tiền, đơn vị và mục đích.
- `READY → APPLIED`: revision nguồn còn đúng, quyền đích được phép và transition chưa áp dụng.
- `SCHEDULED → APPLIED`: đã đến hạn, hạ cấp khả thi và cập nhật chu kỳ được phối hợp đúng.
- `SCHEDULED → CANCELLED`: actor có quyền, thao tác hủy được cho phép và chưa bị worker áp dụng trước đó.

Không cung cấp một API chung cho phép client tùy ý gán `status`.

### 6.2. Timeout và hủy phải có ngữ nghĩa rõ

Timeout mạng khi gọi nhà cung cấp không chứng minh thanh toán thất bại. Để transition chờ đối soát và truy vấn lại bằng định danh thao tác ổn định. Chỉ chuyển `FAILED` khi có căn cứ thất bại cuối cùng theo hợp đồng tích hợp.

Trong chính sách ví dụ, người dùng được hủy lịch hạ cấp chưa áp dụng. Hủy một transition đang có khả năng thu tiền là quy trình khác: cần xác định khoản thu đã xảy ra chưa, có thể hủy ở provider không và có phải hoàn tiền không.

Nếu một khoản thu đến muộn cho transition đã kết thúc, phải đưa vào đối soát và xử lý bù phù hợp. Không chỉ bỏ qua sự kiện vì trạng thái hiện tại là `FAILED` hoặc `CANCELLED`.

### 6.3. Gia hạn và chuyển gói tại cùng ranh giới kỳ

Gia hạn và áp dụng hạ cấp không được là hai tác vụ độc lập cùng ghi kỳ hoặc gói mà không phối hợp.

Một cách triển khai là một lệnh tại ranh giới kỳ: khóa subscription, xem lịch chuyển hợp lệ, xác định gói cho kỳ tiếp theo rồi cập nhật kỳ, gói, quyền và nghĩa vụ thanh toán theo cùng quyết định nghiệp vụ.

Nếu lệnh gia hạn cập nhật revision trước, worker hạ cấp không được bỏ qua xung đột revision để tiếp tục. Nó phải đi qua quy trình đánh giá lại đã được thiết kế. Không tự sửa `source_revision` của transition để tránh lỗi.

## 7. Hạ cấp và bảo vệ tài nguyên hiện có

### 7.1. Giới hạn mới không làm tài nguyên cũ tự biến mất

Một tenant Pro có 40 thành viên yêu cầu xuống Starter với giới hạn 10. Hệ thống phải chọn chính sách cụ thể, chẳng hạn:

- Yêu cầu giảm số thành viên trước thời điểm áp dụng.
- Cho phép trạng thái vượt giới hạn có kiểm soát, chặn tạo mới nhưng vẫn cho đọc và xử lý tài nguyên cũ.
- Yêu cầu quyết định chọn tài nguyên giữ lại qua một luồng riêng có quyền phù hợp.

Bài này chọn cách đầu tiên: có thể ghi nhận lịch hạ cấp, nhưng chỉ áp dụng khi số thành viên và các tài nguyên liên quan đã phù hợp. Không tự xóa ngẫu nhiên 30 thành viên.

Nếu đến hạn vẫn vượt giới hạn, chuyển sang trạng thái xử lý theo chính sách và giữ dữ liệu. Đồng thời phải phối hợp việc tính phí: không cứ phát hành hóa đơn Starter trong khi giữ quyền Pro vô thời hạn, cũng không tự thu thêm một khoản ngoài quyết định đã được chấp nhận. Quy trình thương mại khi hạ cấp không thực hiện được cần được xác định rõ.

### 7.2. Kiểm tra tại lúc áp dụng và lúc tạo tài nguyên

Kiểm tra số thành viên khi lập lịch chưa đủ. Tenant có thể thêm thành viên trước thời điểm hạ cấp.

Để không có race:

1. Lệnh áp dụng hạ cấp và lệnh thêm thành viên dùng chung điểm đồng bộ trên subscription hoặc bản ghi hạn mức.
2. Lệnh hạ cấp đọc lại lượng sử dụng dưới khóa.
3. Sau khi Starter có hiệu lực, lệnh thêm thành viên kiểm tra giới hạn Starter hiện hành.
4. Một lệnh thêm thành viên đã chờ khóa phải đánh giá lại gói sau khi lấy được khóa.

Truy vấn `COUNT(*)` trong một transaction không tự ngăn transaction khác thêm thành viên. Có thể dùng bộ đếm được cập nhật nguyên tử hoặc một giao thức khóa thống nhất cho tất cả đường tạo và xóa thành viên.

### 7.3. Chặn vòng lặp nâng cấp, dùng quyền rồi hạ cấp

Một hành vi lạm dụng là nâng cấp để chạy tác vụ đắt, rồi hạ cấp hoặc hủy trước khi thanh toán được xác nhận. Biện pháp cốt lõi là chỉ cấp quyền theo điều kiện thanh toán và thời điểm hiệu lực đã định.

Các biện pháp khác tùy chính sách:

- Không hoàn lại phần tài nguyên đã tiêu thụ bằng việc thay gói.
- Không cấp lại trial, coupon hoặc credit chào mừng mỗi lần quay lại gói.
- Gắn ưu đãi với danh tính quyền lợi bền vững.
- Ghi nhận tiêu thụ theo kỳ hoặc nguồn cấp, không theo nhãn gói hiện tại.
- Nếu áp dụng thời gian chờ hoặc giới hạn số lần đổi, kiểm tra tại server và không dùng chúng thay cho tính đúng của transaction.

Một thao tác hợp lệ riêng lẻ vẫn có thể trở thành lạm dụng khi kết hợp thành chuỗi. Vì vậy cần kiểm tra cả hành trình nâng cấp → sử dụng → hạ cấp → nâng cấp lại.

## 8. Transaction cục bộ và kiểm soát đồng thời

### 8.1. Một điểm tuần tự hóa trên subscription

Một chiến lược tham chiếu là mọi lệnh ảnh hưởng việc chuyển gói đều khóa hàng subscription trước khi đọc và sửa trạng thái nghiệp vụ:

~~~sql
SELECT *
FROM subscription
WHERE tenant_id = :tenant_id
  AND subscription_id = :subscription_id
FOR UPDATE;
~~~

Các luồng chấp nhận quote, áp dụng transition, hủy lịch, thay số lượng tính phí và gia hạn phải có thứ tự khóa tương thích. Nếu có thêm các hàng liên quan, có thể thống nhất thứ tự subscription → quote/transition → hạn mức → bản ghi tài chính cục bộ.

Đây không phải yêu cầu rằng mọi hệ thống phải dùng khóa bi quan. Optimistic locking hoặc isolation phù hợp cũng có thể đúng nếu bảo vệ đủ dữ kiện và xử lý xung đột toàn lệnh. Mục đích là xác định rõ request nào thắng và request nào phải đọc lại trạng thái.

Đừng giữ khóa cơ sở dữ liệu trong lúc chờ API thanh toán. Lời gọi mạng có độ trễ và kết quả không chắc chắn; nó không thể được rollback bằng transaction SQL.

### 8.2. Constraint bảo vệ các điểm quan trọng

Với bảng transition đã có các cột tương ứng, có thể dùng ràng buộc:

~~~sql
CREATE UNIQUE INDEX one_open_transition_per_subscription
ON subscription_transition (tenant_id, subscription_id)
WHERE status IN (
    'REQUESTED',
    'WAITING_PAYMENT',
    'READY',
    'SCHEDULED',
    'REVIEW_REQUIRED'
);

CREATE UNIQUE INDEX one_transition_per_quote
ON subscription_transition (tenant_id, quote_id);
~~~

Index đầu bảo đảm không có hai transition đang mở cho cùng subscription. Index sau ngăn một quote được chấp nhận thành nhiều transition độc lập.

Trong lược đồ đầy đủ, khóa ngoại ghép phải liên kết subscription, quote và transition theo tenant. Cần thêm các kiểm tra miền trạng thái, số tiền, đơn vị, mốc thời gian và tham chiếu provider phù hợp.

Constraint không tự quyết định actor có quyền hay giá có hợp lệ. Nó là lớp bảo vệ bổ sung cho các bất biến có thể biểu diễn ở cơ sở dữ liệu.

### 8.3. Chấp nhận yêu cầu không có side effect mạng trong transaction

Phác thảo Java sau là mã giả, không phải triển khai hoàn chỉnh:

~~~java
TransitionResult accept(
        Actor actor,
        SubscriptionId subscriptionId,
        AcceptQuoteCommand cmd,
        String idempotencyKey) {

    TenantId tenant = actor.verifiedTenant();
    input.validate(cmd, idempotencyKey);
    access.requireCanAttemptPlanChange(actor, tenant, subscriptionId);

    RequestHash hash = hasher.canonicalHash(
        "ACCEPT_PLAN_QUOTE_V1", tenant, subscriptionId, cmd
    );

    return transactions.required(() -> {
        IdempotencyDecision idem = idempotency.claimOrReplay(
            tenant, actor.id(), "ACCEPT_PLAN_QUOTE_V1",
            idempotencyKey, hash
        );

        if (idem.isReplay()) {
            access.requireCanReadTransition(actor, idem.transitionId());
            return idem.result();
        }

        Subscription sub = subscriptions.lock(tenant, subscriptionId);
        access.requireCurrentBillingAuthority(actor, sub);

        Quote quote = quotes.lock(tenant, cmd.quoteId());
        Instant decisionTime = databaseClock.currentInstant();

        policy.requireQuoteMatches(sub, quote, cmd.expectedRevision());
        policy.requireQuoteAcceptable(actor, quote, decisionTime);
        transitions.requireNoOpenTransition(sub);

        PlanTransition transition = transitions.insert(sub, quote, actor);
        quotes.markAccepted(quote, transition.id());

        if (quote.requiresPayment()) {
            transitions.moveToWaitingPayment(transition);
            outbox.requestPayment(transition);
        } else if (quote.isEndOfPeriod()) {
            transitions.schedule(transition, quote.effectiveAt());
            outbox.requestScheduledApplication(transition);
        } else {
            applyPolicy.requireImmediateNoPaymentAllowed(sub, quote);
            planApplier.applyInsideTransaction(sub, transition);
        }

        audit.appendTransitionAccepted(actor, transition);
        TransitionResult result = results.from(transition);
        idempotency.complete(idem.requestId(), result);
        return result;
    });
}
~~~

Nếu chính sách yêu cầu quyền thu hồi có hiệu lực ngay khi transaction thu hồi commit, `requireCurrentBillingAuthority` phải dùng một cơ chế đồng bộ tương ứng với luồng thu hồi. Chỉ gọi một cache role cũ không đáp ứng yêu cầu đó.

Mọi lỗi sau khi ghi một phần phải làm rollback toàn transaction. Không bắt exception rồi trả lỗi bình thường mà vô tình commit transition, quote hoặc outbox dở dang.

### 8.4. Áp dụng phải là một phép chuyển có điều kiện

Worker hoặc handler xác nhận thanh toán không được chỉ ghi gói mới. Nó cần:

1. Khóa subscription và transition theo thứ tự chung.
2. Nếu transition đã `APPLIED`, trả kết quả đã có, không tạo thêm hiệu ứng.
3. Kiểm tra trạng thái cho phép, điều kiện thời gian và xác nhận thanh toán nếu cần.
4. Kiểm tra nguồn, revision, tài nguyên và chính sách hiện tại.
5. Cập nhật gói, giá, quyền và revision cùng trạng thái transition trong một transaction.
6. Ghi audit và outbox để cập nhật các hệ thống phụ trợ sau commit.

Ví dụ phần cập nhật có điều kiện:

~~~sql
UPDATE subscription
SET current_plan_version_id = :target_plan_version_id,
    current_price_version_id = :target_price_version_id,
    effective_revision = effective_revision + 1
WHERE tenant_id = :tenant_id
  AND subscription_id = :subscription_id
  AND effective_revision = :source_revision
  AND current_plan_version_id = :source_plan_version_id
  AND billing_status = 'ACTIVE'
RETURNING effective_revision;
~~~

Phải có đúng một hàng được cập nhật. Giá trị đích và revision nguồn lấy từ transition đã được xác thực dưới khóa, không lấy trực tiếp từ webhook hoặc request.

Đây chỉ là phần SQL minh họa. Các thay đổi quyền được vật chất hóa, dữ liệu kỳ khi cần, trạng thái transition và bằng chứng ghi sổ vẫn phải thuộc cùng transaction. Nếu một bước thất bại, tất cả rollback.

Không coi việc câu `UPDATE` trả 0 hàng là thành công. Nếu đã thu tiền nhưng nguồn thay đổi, chuyển quy trình sang đối soát theo thiết kế; không tự áp dụng gói đích trên một nguồn khác.

### 8.5. Quyền đọc phải thống nhất sau commit

Nếu hệ thống có bảng entitlement, dùng cùng transaction để cập nhật nó và ghi `effective_revision` tương ứng. Nếu quyền được suy trực tiếp từ plan version bất biến, quyết định truy cập cần đọc một trạng thái subscription nhất quán.

Cache và token dài hạn có thể giữ quyền Pro sau khi Starter đã có hiệu lực. Với thao tác cần thu hồi quyền ngay theo chính sách, hãy kiểm tra phiên bản hiện hành ở nguồn tin cậy hoặc dùng cơ chế vô hiệu hóa có bảo đảm phù hợp. Không coi việc đã phát một sự kiện là bằng chứng mọi cache đã được cập nhật.

Client có thể hiển thị tiến độ từ dữ liệu cache, nhưng API thực thi tài nguyên phải quyết định theo quyền có hiệu lực.

## 9. Idempotency và danh tính nghiệp vụ

### 9.1. Retry cùng ý định

Tình huống:

~~~text
Server tạo transition T và commit.
Kết nối đứt trước khi response tới client.
Client gửi lại cùng yêu cầu.
~~~

Nếu server tạo transition mới, có thể tạo thêm phiên thanh toán hoặc thêm nghĩa vụ thu tiền. Một idempotency key bền vững cần gắn với:

~~~text
tenant + actor + operation_version + idempotency_key
~~~

Fingerprint của yêu cầu bao gồm subscription, quote, expected revision và các trường ảnh hưởng hiệu ứng. Cần canonicalize dữ liệu trước khi hash; không dùng JSON thô có thứ tự thuộc tính không ổn định.

Cùng key và cùng fingerprint: trả lại kết quả đã lưu. Cùng key nhưng khác fingerprint: báo xung đột, không thực hiện nội dung mới.

Bản ghi idempotency cho việc tiếp nhận phải commit cùng transition và outbox. Một cache riêng không đủ chứng minh transition đã được tạo hoặc chưa.

### 9.2. Response được phát lại có thể là trạng thái ban đầu

Nếu lần đầu trả `202` với transition đang `WAITING_PAYMENT`, lần retry có thể phát lại đúng response đã lưu dù transition hiện đã `APPLIED`. Response nên chứa transition ID và đường dẫn tra trạng thái hiện tại.

Không chạy lại toàn bộ thanh toán chỉ vì response idempotency mô tả trạng thái đang chờ. Idempotency bảo vệ hiệu ứng của lệnh tiếp nhận; API đọc phản ánh tiến độ hiện tại.

Khi trả kết quả cũ, vẫn kiểm tra actor, tenant và quyền đọc đối tượng. Khóa không phải token trao quyền truy cập vĩnh viễn.

### 9.3. Khác key vẫn không được nhận lại cùng quyền lợi

Idempotency không ngăn người dùng gửi cùng quote với hai key mới. Vì vậy còn cần:

- Một quote chỉ liên kết một transition.
- Một subscription chỉ có một transition mở.
- Transition áp dụng có điều kiện theo trạng thái và revision.
- Một thao tác thanh toán có khóa ổn định theo transition, không theo mỗi lần worker chạy.
- Ưu đãi hoặc quyền dùng thử có định danh quyền lợi riêng.

Nếu bản ghi idempotency được dọn sau một khoảng thời gian, các bằng chứng nghiệp vụ còn hiệu lực vẫn phải ngăn một quote hoặc khoản thanh toán cũ được sử dụng lại.

### 9.4. Hủy lịch và áp dụng cũng cần chống lặp

Lệnh hủy hạ cấp nên cập nhật có điều kiện từ `SCHEDULED` sang `CANCELLED`. Lặp lại lệnh hủy không được hoàn tiền hoặc cấp ưu đãi nhiều lần.

Nếu worker áp dụng và người dùng hủy cùng lúc, khóa subscription và transition giúp chỉ một nhánh thắng:

~~~text
Hủy thắng:
  Transition CANCELLED; worker không được áp dụng.

Áp dụng thắng:
  Transition APPLIED; hủy không được biến lịch sử thành chưa từng áp dụng.
  Muốn quay lại gói cũ phải tạo một quyết định chuyển mới theo chính sách.
~~~

## 10. Phối hợp với hệ thống thanh toán

### 10.1. Không có một transaction SQL bao trùm nhà cung cấp

Luồng tham chiếu dùng các bước bền vững:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant D as Cơ sở dữ liệu
    participant W as Worker
    participant P as Nhà cung cấp

    C->>A: Chấp nhận quote và gửi key
    A->>D: Ghi transition, idempotency, outbox
    D-->>A: Commit
    A-->>C: 202 và transition ID
    W->>D: Nhận tác vụ outbox
    W->>P: Tạo hoặc tra khoản thanh toán bằng khóa ổn định
    P-->>W: Kết quả hoặc trạng thái chưa rõ
    P->>A: Webhook
    A->>D: Ghi inbox và đối chiếu transition
    W->>D: Áp dụng sau xác nhận hợp lệ
~~~

Đây là phối hợp qua nhiều transaction và một hệ thống ngoài. Mục tiêu là các bước có thể retry, tìm lại kết quả và phục hồi, không phải hứa rằng mọi tác động xảy ra tức thời cùng nhau.

### 10.2. Khóa thanh toán ổn định theo thao tác

Worker có thể nhận cùng outbox nhiều lần. Khóa gửi provider nên xuất phát từ danh tính thao tác, ví dụ:

~~~text
plan-transition:{transition-id}:payment:v1
~~~

Cùng một bước retry dùng lại khóa đó. Không tạo khóa mới theo timestamp mỗi lần thử vì provider có thể hiểu là một khoản thu mới.

Phải hiểu phạm vi và thời hạn idempotency của hệ thống ngoài khi tích hợp. Khi kết quả chưa rõ hoặc thời hạn khóa đã qua, tra đối tượng liên quan và đối soát trước khi tạo khoản thu mới.

Định danh provider, liên kết transition và trạng thái xử lý phải được lưu bền vững. Nếu provider đã tạo đối tượng nhưng worker chết trước khi lưu ID, lần chạy sau cần tìm lại theo định danh đã được thiết kế; không mặc định rằng “không có ID cục bộ” nghĩa là “chưa có khoản thu”.

### 10.3. Webhook hợp lệ chưa chắc đủ điều kiện đổi gói

Trình tự xử lý cần bao gồm:

1. Xác minh nguồn webhook theo cơ chế của provider, đúng tài khoản tích hợp và dữ liệu gốc được yêu cầu.
2. Ghi hoặc nhận diện event bằng một inbox có ràng buộc duy nhất trong phạm vi provider account.
3. Đối chiếu đối tượng thanh toán với liên kết đã lưu phía server.
4. Xác định trạng thái thanh toán có thẩm quyền; nếu cần, truy vấn lại đối tượng provider.
5. So subscription, chủ thể thanh toán, transition, số tiền, đơn vị và mục đích.
6. Chỉ thực hiện chuyển trạng thái được phép.
7. Ghi kết quả xử lý bền vững rồi phản hồi theo hợp đồng retry của tích hợp.

Chữ ký đúng chỉ chứng minh sự kiện đến từ nguồn được xác thực theo cơ chế đó. Một sự kiện thật về hóa đơn kỳ trước không phải căn cứ nâng cấp cho transition kỳ này.

Metadata hoặc một transition ID trong sự kiện cũng không đủ nếu không đối chiếu với liên kết đã được server thiết lập. Không cho phép một khoản thanh toán của tenant khác bảo chứng cho transition hiện tại.

### 10.4. Sự kiện có thể trùng hoặc đến sai thứ tự

Các tình huống phải dự kiến:

| Tình huống | Cách bảo vệ |
| --- | --- |
| Cùng event ID được gửi lại | Unique inbox và xử lý có thể retry |
| Hai event ID khác nhau cùng nói về một khoản thanh toán | Chuyển trạng thái có điều kiện và liên kết thanh toán duy nhất |
| Event thất bại cũ đến sau xác nhận thành công | Đối chiếu trạng thái có thẩm quyền, không ghi đè mù |
| Webhook đến trước khi worker lưu provider object ID | Giữ sự kiện để đối soát hoặc liên kết qua tham chiếu server được kiểm chứng |
| Event đúng chữ ký nhưng sai số tiền hoặc đơn vị | Không cấp quyền; đưa vào điều tra hoặc đối soát |
| Thanh toán thành công nhưng áp dụng quyền bị lỗi | Giữ bằng chứng đã thu và retry bước áp dụng an toàn |
| Hoàn tiền hoặc tranh chấp thực sự xảy ra sau đó | Đi qua quy trình tài chính và thu hồi quyền riêng |

Không coi mọi event thất bại đến muộn là vô nghĩa: nó có thể mô tả một sự kiện tài chính mới. Cần phân biệt một thông báo cũ với một hành động đảo ngược mới có thẩm quyền.

Nếu inbox được ghi nhận ở transaction đầu rồi xử lý sau, phải có trạng thái như received/processing/handled và cơ chế phục hồi. Không đánh dấu “đã xử lý” chỉ vì đã nhận webhook rồi bỏ mất bước áp dụng khi process chết.

### 10.5. Tiền đã thu nhưng transition không thể áp dụng

Ví dụ thanh toán thành công trong lúc subscription bị đình chỉ vì một lý do khác. Không tự ghi đè trạng thái đình chỉ để cấp Pro.

Có thể:

- Retry áp dụng nếu lỗi chỉ là tạm thời và mọi điều kiện còn đúng.
- Đưa vào `REVIEW_REQUIRED` khi trạng thái nguồn hoặc chính sách đã thay đổi.
- Thực hiện hoàn tiền hoặc điều chỉnh bằng một workflow có định danh và chống lặp riêng.
- Thông báo tiến độ cho người dùng qua trạng thái transition.

Mọi bù trừ đều cần bằng chứng và tính idempotent. Không “rollback” một khoản thanh toán ngoài hệ thống bằng cách chỉ xóa transition cục bộ.

## 11. Hợp đồng API và quan sát vận hành

### 11.1. Response thể hiện trạng thái thực

~~~json
{
  "transitionId": "transition-456",
  "subscriptionId": "subscription-789",
  "status": "WAITING_PAYMENT",
  "currentPlanVersionId": "plan-starter-v2",
  "targetPlanVersionId": "plan-pro-v3",
  "applyMode": "IMMEDIATE",
  "effectiveAt": null,
  "statusUrl": "/subscriptions/subscription-789/transitions/transition-456"
}
~~~

Trong response này, `IMMEDIATE` nghĩa là áp dụng ngay khi đủ điều kiện, không có nghĩa đã được phép dùng Pro ngay lúc đọc response. `effectiveAt` thực tế chỉ được chốt theo chính sách sau khi điều kiện đã đạt.

Một số lỗi minh họa:

| Lỗi | Ý nghĩa | Hành vi client |
| --- | --- | --- |
| `QUOTE_EXPIRED` | Quá thời hạn chấp nhận | Lấy quote mới |
| `SOURCE_REVISION_CHANGED` | Nguồn không còn khớp | Đọc trạng thái rồi báo giá lại |
| `TRANSITION_ALREADY_OPEN` | Có quy trình đang diễn ra | Theo dõi hoặc hủy theo quyền |
| `TARGET_PLAN_NOT_ALLOWED` | Không được chuyển sang đích này | Chọn gói được phép |
| `IDEMPOTENCY_KEY_REUSED` | Cùng key nhưng khác nội dung | Không retry nội dung mới bằng key cũ |
| `DOWNGRADE_USAGE_CONFLICT` | Tài nguyên chưa phù hợp gói đích | Xử lý tài nguyên theo chính sách |
| `PAYMENT_STATE_UNCERTAIN` | Chưa xác định được kết quả bên ngoài | Theo dõi, không tạo khoản thu khác tùy tiện |

Mã HTTP cụ thể là hợp đồng của sản phẩm. Có thể dùng `409` cho xung đột trạng thái và `403` hoặc `404` cho đối tượng ngoài quyền theo chính sách che giấu tồn tại; không để thông báo lỗi tiết lộ dữ liệu tenant khác.

### 11.2. Audit cần tái dựng được quyết định

Một bản ghi chuyển gói nên liên kết được:

- Actor hoặc service identity, tenant và subscription.
- Transition, quote và idempotency request.
- Gói nguồn, gói đích, revision và phiên bản chính sách.
- Thời điểm yêu cầu, thời điểm đủ điều kiện và thời điểm áp dụng.
- Tham chiếu khoản thanh toán cùng kết quả đối soát.
- Lý do từ chối, hủy hoặc đưa sang xử lý bổ sung.
- Các sự kiện cập nhật quyền và phiên bản quyền đã commit.

Không ghi token xác thực hoặc thông tin thanh toán bí mật không cần thiết vào log.

### 11.3. Đối soát và cảnh báo theo bất biến

Theo dõi các trường hợp như:

- Có thanh toán đã xác nhận nhưng transition chưa áp dụng quá thời gian xử lý dự kiến.
- Transition `APPLIED` nhưng subscription không mang gói hoặc revision đã ghi nhận.
- Có hai transition mở cho cùng subscription.
- Quote đã được dùng nhưng không có transition tương ứng.
- Khoản thu được liên kết với nhiều transition ngoài mô hình cho phép.
- Webhook hoặc outbox liên tục retry.
- Lịch hạ cấp quá hạn mà chưa có kết quả rõ ràng.
- Số lần đổi gói, hủy, hoàn tiền hoặc nhận ưu đãi bất thường.

Đọc dữ liệu đối soát trong snapshot nhất quán khi so nhiều bảng. Phát hiện sai lệch không được dẫn đến việc sửa trực tiếp số tiền hoặc quyền để làm các bảng trông khớp; cần quy trình điều chỉnh có thẩm quyền và dấu vết.

## 12. Kiểm thử theo tình huống tấn công logic

### 12.1. Quyền, báo giá và dữ liệu đầu vào

| Ca kiểm thử | Hành vi tấn công | Kết quả cần chứng minh |
| --- | --- | --- |
| Subscription ngoài tenant | Đổi ID trên URL | Không đọc hoặc sửa đối tượng ngoài phạm vi |
| Quote của subscription khác | Giữ URL nhưng thay quote ID | Từ chối trước hiệu ứng |
| Gói nội bộ | Gửi trực tiếp ID không xuất hiện trên UI | Không mua được gói ngoài chính sách |
| Sửa giá hoặc hạn mức | Thêm trường giá, seat limit, paid flag | Không ảnh hưởng quyết định của server |
| Quote hết hạn | Chấp nhận tại và sau mốc hết hạn | Tuân thủ chính xác quy tắc thời gian |
| Quote cũ sau gia hạn | Dùng revision hoặc kỳ trước | Yêu cầu đánh giá lại, không áp dụng mù |
| Thay số lượng tính phí | Sửa seats sau khi lấy quote | Không thu giá cũ cho cấu hình mới |
| Mất quyền trong lúc chờ | Thu hồi quyền trước điểm quyết định | Kết quả theo cơ chế đồng bộ đã công bố |
| Sửa ưu đãi | Dùng mã hoặc quyền lợi đã tiêu thụ | Không nhận lại quyền lợi |
| Tràn hoặc làm tròn bất lợi | Dùng lượng lớn, phần kỳ rất nhỏ, đổi chu kỳ nhiều lần | Số tiền theo chính sách, không wrap-around |

### 12.2. Đồng thời và retry

**Ca A — Hai quote khác nhau cùng được chấp nhận**

~~~text
Ban đầu:
  Subscription ACTIVE, effective_revision = 7
  Không có transition mở
  Hai quote đều tính từ revision 7

Chạy hai lệnh chấp nhận đồng thời với hai key khác nhau.

Kỳ vọng:
  Tối đa một transition mở được tạo.
  Lệnh còn lại nhận xung đột hoặc bị yêu cầu đọc lại.
  Không có hai yêu cầu thu tiền độc lập.
~~~

Nếu lệnh đầu là thay đổi không cần thanh toán và áp dụng ngay, lệnh thứ hai phải thất bại do revision nguồn đã thay đổi, dù không còn transition mở.

**Ca B — Cùng key, cùng nội dung**

Gửi nhiều request cùng key và fingerprint. Sau khi xử lý retry tạm thời theo hợp đồng, chỉ có một transition, một liên kết quote và một ý định thanh toán.

**Ca C — Cùng key, khác nội dung**

Tranh chấp cùng key nhưng khác quote hoặc subscription. Chỉ một nội dung có thể gắn với hiệu ứng thành công; nội dung còn lại bị xung đột.

**Ca D — Khác key, cùng quote**

Dùng hai actor đều có quyền hoặc hai key khác nhau để chấp nhận cùng quote. Unique theo quote và kiểm tra trạng thái phải ngăn tạo transition thứ hai.

**Ca E — Hủy cạnh tranh với áp dụng**

Cho worker đến hạn và lệnh hủy lấy khóa cạnh tranh. Kết quả cuối là `CANCELLED` hoặc `APPLIED` đúng theo nhánh thắng, không đồng thời có audit “đã hủy” và hiệu ứng đổi gói chưa được giải thích.

**Ca F — Thêm thành viên cạnh tranh với hạ cấp**

~~~text
Ban đầu:
  Pro có 9 thành viên.
  Starter giới hạn 10.
  Có lịch hạ cấp đến hạn.

Đồng thời:
  Một luồng thêm nhiều thành viên theo chính sách tạo tài nguyên.
  Một luồng áp dụng Starter.

Kỳ vọng:
  Không thể commit Starter với tài nguyên vượt giới hạn
  nếu chính sách không cho phép trạng thái vượt giới hạn.
  Lệnh chờ khóa đánh giá lại quyền hoặc số lượng sau khi được tiếp tục.
~~~

Dùng latch hoặc barrier để tạo điểm tranh chấp có kiểm soát. Kiểm thử trên cơ sở dữ liệu có semantics khóa như môi trường thực; mock repository không đủ để chứng minh chống race.

### 12.3. Sự kiện và lỗi giữa các bước

Các điểm chèn lỗi hữu ích:

| Điểm lỗi | Kết quả cần có |
| --- | --- |
| Sau ghi transition, trước ghi outbox | Rollback toàn bộ transaction tiếp nhận |
| Sau commit, trước trả response | Retry trả lại transition gốc |
| Provider đã tạo khoản thu, worker chưa lưu ID | Tìm lại bằng định danh ổn định, không thu lần hai |
| Webhook đến trước response tạo payment | Không mất sự kiện hoặc cấp quyền sai liên kết |
| Cùng webhook lặp nhiều lần | Một hiệu ứng chuyển trạng thái |
| Hai event khác nhau cho cùng payment | Một lần áp dụng quyền |
| Xác nhận thành công đến trước thông báo thất bại cũ | Không hạ trạng thái mù; xác định trạng thái có thẩm quyền |
| Sau đổi plan, trước cập nhật entitlement | Transaction áp dụng rollback, không commit trạng thái pha trộn |
| Đã thu tiền nhưng nguồn thay đổi | Có đối soát hoặc bù trừ, không tự áp dụng trên nguồn khác |
| Cache chưa nhận sự kiện hạ cấp | API nhạy cảm không cấp quyền đã bị thu hồi trái chính sách |

Ngoài response, phải kiểm tra số transition, ý định thanh toán, lần thu thực tế trong môi trường kiểm thử tích hợp, bản ghi audit, quyền hiện hành và trạng thái quote.

### 12.4. Chuỗi hành động để phát hiện lạm dụng

Ví dụ một chuỗi kiểm thử:

~~~text
Lấy quote
→ Nâng cấp
→ Retry sau timeout
→ Dùng tài nguyên
→ Lập lịch hạ cấp
→ Hủy lịch
→ Lập lịch lại
→ Gia hạn
→ Gửi lại webhook kỳ cũ
→ Nâng cấp lại
~~~

Sau từng bước đã commit, kiểm tra:

- Chỉ có một gói có hiệu lực và tối đa một transition mở.
- Không có quyền mới trước điều kiện thanh toán.
- Không có khoản thu hoặc ưu đãi bị nhân bản.
- Lượng sử dụng không tự giảm vì đổi gói.
- Quyền và revision nhất quán.
- Lệnh thất bại không để lại dữ liệu dở dang.
- Sự kiện cũ không ghi đè một trạng thái mới mà không qua đánh giá hợp lệ.

Có thể áp dụng kiểm thử dựa trên mô hình hoặc thuộc tính cho các chuỗi trạng thái này. Điều cần chứng minh là bất biến qua cả hành trình, không chỉ từng endpoint riêng lẻ trả mã HTTP đúng.

## 13. Các lỗi thiết kế cần nhận ra khi review

| Thiết kế có vấn đề | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Gán plan trực tiếp từ request | Bỏ qua quyền, giá, thời điểm và thanh toán | Lệnh transition với điều kiện cụ thể |
| Dùng success URL để cấp quyền | Client có thể giả hoặc phát lại | Xác nhận từ nguồn thanh toán có thẩm quyền |
| Ghi target plan vào current plan khi còn chờ | Dùng quyền cao hơn trước điều kiện | Tách current và pending |
| Chỉ chống trùng theo event ID | Event khác ID vẫn tạo thêm hiệu ứng | State machine và định danh thao tác |
| Tạo payment key mới mỗi lần retry | Có thể thu nhiều lần | Khóa provider ổn định theo bước nghiệp vụ |
| Chỉ kiểm tra quota lúc lên lịch | Tài nguyên có thể tăng trước lúc hạ cấp | Kiểm tra và đồng bộ tại lúc áp dụng |
| Reset usage khi đổi gói | Tạo vòng lặp lấy lại hạn mức | Bảo toàn tiêu thụ theo kỳ và nguồn |
| Giữ khóa SQL khi gọi provider | Khóa kéo dài nhưng không có tính nguyên tử phân tán | Outbox và bước xử lý có thể khôi phục |
| Bỏ qua source revision sau khi đã thu tiền | Áp dụng quyết định cũ trên nguồn mới | Đối soát, đánh giá lại hoặc bù trừ |
| Để token chứa quyền cũ quyết định mãi | Hạ cấp không có hiệu lực ở API tài nguyên | Kiểm tra phiên bản hoặc thu hồi theo chính sách |
| Sửa lịch sử để chữa lỗi tài chính | Mất bằng chứng về nghĩa vụ và quyền | Điều chỉnh có tham chiếu và thẩm quyền |

## 14. Tiêu chí hoàn thành thiết kế

Một luồng chuyển gói cần trả lời được:

- Ai được đổi subscription này và ai được duyệt điều kiện đặc biệt?
- Gói và giá nào được phép chuyển từ trạng thái nguồn hiện tại?
- Quote gắn với revision, kỳ, số lượng và thời hạn nào?
- Quyền đích có hiệu lực ngay, sau thanh toán hay ở ranh giới kỳ?
- Điểm nào tuần tự hóa hai request hoặc worker cùng tác động?
- Cùng key, cùng quote và cùng payment được chống lặp ở những lớp nào?
- Nếu thanh toán thành công nhưng cập nhật quyền thất bại, hệ thống phục hồi ra sao?
- Gia hạn, hạ cấp và thay đổi tài nguyên phối hợp thế nào?
- Đổi gói có giữ đúng tiêu thụ, ưu đãi và quyền dùng thử đã nhận không?
- Audit và đối soát có tái dựng được quyết định cùng hiệu ứng đã commit không?

Chuyển gói an toàn đòi hỏi một quyết định có thẩm quyền về **nguồn, đích, chi phí, thời điểm và quyền sử dụng**, được áp dụng theo state machine có kiểm soát. Transaction giữ trạng thái cục bộ nhất quán; idempotency và định danh nghiệp vụ ngăn tác động trùng; quy trình đối soát giữ thanh toán và quyền không bị tách rời khi có lỗi.
