# Xác định workflow tạo tác động tài chính hoặc danh tiếng

Không phải mọi endpoint đều có mức rủi ro như nhau. Một API đọc danh sách sản phẩm thường có tác động khác với API hoàn tiền, chuyển tiền, thay đổi giá, phát hành thông báo hàng loạt hoặc công khai nội dung dưới tên một tổ chức. Để thiết kế bảo mật API theo đúng mức độ rủi ro, nhóm cần nhận diện những workflow có thể gây tổn thất tài chính, làm suy giảm uy tín, ảnh hưởng quyền lợi khách hàng hoặc tạo ra hậu quả khó đảo ngược.

Workflow là chuỗi bước nghiệp vụ dẫn từ một sự kiện khởi đầu đến kết quả cuối cùng. Chuỗi này có thể đi qua nhiều endpoint, service, message queue, tác vụ nền và hệ thống bên thứ ba. Vì vậy, việc chỉ nhìn từng controller hoặc HTTP route riêng lẻ thường không cho thấy đầy đủ tác động. Một request tưởng như chỉ cập nhật trạng thái có thể kích hoạt thanh toán, gửi email, cấp quyền, phát hành nội dung hoặc đồng bộ dữ liệu sang hệ thống khác.

Mục tiêu của bước nhận diện là biết workflow nào cần kiểm soát chặt hơn, ai có thể khởi tạo và phê duyệt, dữ liệu nào quyết định kết quả, side effect nào xảy ra, và cách phát hiện hoặc khôi phục khi có hành vi sai trái.

## 1. Hiểu thế nào là tác động tài chính và tác động danh tiếng

Tác động tài chính là hậu quả làm thay đổi tiền, nghĩa vụ thanh toán, giá trị tài sản, doanh thu, chi phí hoặc quyền lợi kinh tế. Tác động danh tiếng là hậu quả làm suy giảm niềm tin của khách hàng, đối tác, cơ quan quản lý hoặc công chúng đối với cá nhân hay tổ chức.

Hai loại tác động có thể xuất hiện cùng lúc. Một lần hoàn tiền trái phép vừa gây mất tiền vừa làm khách hàng nghi ngờ khả năng bảo vệ tài khoản. Một thông báo sai về sự cố dữ liệu có thể gây tổn hại uy tín, phát sinh chi phí hỗ trợ và tạo nghĩa vụ pháp lý.

| Nhóm tác động | Ví dụ | Hậu quả có thể xảy ra |
|---|---|---|
| Tiền và tài sản | Thanh toán, hoàn tiền, chuyển tiền, rút tiền, điều chỉnh số dư | Mất tiền, sai lệch sổ cái, tranh chấp hoặc gian lận |
| Giá và thương mại | Sửa giá, tạo coupon, áp dụng chiết khấu, thay đổi hạn mức tín dụng | Thất thu, bán dưới giá, lạm dụng ưu đãi |
| Nghĩa vụ và quyền lợi | Phát hành hóa đơn, ghi nhận công nợ, cấp quyền lợi hoặc gói dịch vụ | Sai nghĩa vụ, cấp quyền lợi trái phép, vi phạm hợp đồng |
| Nội dung công khai | Đăng bài, công bố thông báo, sửa trang sản phẩm hoặc chính sách | Thông tin sai lệch, mất niềm tin, ảnh hưởng thương hiệu |
| Giao tiếp với khách hàng | Gửi email/SMS/push hàng loạt, thông báo sự cố, xác nhận giao dịch | Gây hoang mang, spam, tiết lộ thông tin hoặc làm giảm uy tín |
| Danh tính và tài khoản | Khôi phục tài khoản, thay email/điện thoại, đổi chủ sở hữu, khóa tài khoản | Chiếm đoạt tài khoản, mất quyền truy cập hoặc mất niềm tin |
| Dữ liệu và riêng tư | Export dữ liệu, chia sẻ hồ sơ, cấp link tải hoặc thay đổi quyền truy cập | Rò rỉ dữ liệu, khiếu nại, chế tài và tổn hại danh tiếng |
| Kiểm duyệt và đánh giá | Gỡ nội dung, ẩn đánh giá, khóa người dùng hoặc thay đổi kết quả xếp hạng | Quyết định thiếu công bằng, phản ứng công khai, tranh chấp |

Khi đánh giá, không chỉ xem số tiền hoặc số người bị ảnh hưởng trực tiếp. Một lỗi ở workflow cấp quyền có thể mở đường cho tổn thất tài chính về sau; một thao tác sửa dữ liệu nội bộ có thể làm sai báo cáo, hóa đơn hoặc thông tin công khai.

## 2. Nhận diện workflow từ toàn bộ bề mặt hệ thống

Không nên bắt đầu bằng danh sách endpoint đơn thuần. Hãy kết hợp tài liệu API với luồng giao diện, service, event và tác vụ vận hành để tìm các workflow thực tế.

Các nguồn cần rà soát:

- API contract/OpenAPI: method, path, request/response, action và endpoint quản trị.
- Giao diện web/mobile: thao tác người dùng, bước xác nhận, chức năng bulk và quyền hiển thị.
- Service/domain: nơi thay đổi trạng thái, số dư, giá, owner, permission hoặc dữ liệu công khai.
- Event và message: event phát sinh sau thanh toán, duyệt, xuất bản, khóa tài khoản hoặc thay đổi hợp đồng.
- Background job: export, import, settlement, retry, reconciliation, gửi thông báo và đồng bộ.
- Webhook/callback: thông báo từ cổng thanh toán, đối tác vận chuyển, nhà cung cấp định danh hoặc nền tảng khác.
- Công cụ nội bộ: admin portal, support console, batch script và thao tác vận hành có thể tác động dữ liệu thật.

Một endpoint không nhất thiết là điểm cuối của workflow. Ví dụ POST /orders có thể tạo đơn, giữ tồn kho, tạo payment intent, phát event và gửi email. Một webhook payment có thể cập nhật trạng thái, ghi ledger, kích hoạt giao hàng và thông báo cho khách hàng. Phải theo dõi cả chuỗi side effect sau request ban đầu.

### 2.1. Lập danh mục workflow

Mỗi workflow nên có một bản ghi ngắn với các thông tin:

| Trường | Câu hỏi cần trả lời |
|---|---|
| Tên workflow | Người dùng hoặc nghiệp vụ gọi luồng này là gì? |
| Trigger | Ai hoặc hệ thống nào khởi tạo? Qua endpoint, event, lịch chạy hay callback? |
| Actor | Customer, nhân viên, quản lý, service account hay đối tác? |
| Object/data | Đơn hàng, payment, account, nội dung, hồ sơ hay dữ liệu nào bị tác động? |
| Action | Tạo, sửa, duyệt, chuyển, xóa, công khai, hoàn tiền hay cấp quyền? |
| Side effect | Có thay đổi ledger, gọi nhà cung cấp, gửi thông báo hoặc enqueue job không? |
| Approval | Có cần người thứ hai, hạn mức hoặc phê duyệt theo cấp không? |
| Failure/compensation | Nếu một bước lỗi hoặc bị gửi lặp thì khôi phục thế nào? |
| Evidence | Log, audit event, trace và dữ liệu đối soát nào chứng minh kết quả? |
| Owner | Nhóm nghiệp vụ và nhóm kỹ thuật nào chịu trách nhiệm? |

Danh mục này cần được cập nhật khi thêm endpoint, event, trạng thái hoặc tích hợp mới. Nếu một workflow chưa có owner hoặc chưa xác định được side effect, đó là dấu hiệu cần làm rõ trước khi phát hành.

### 2.2. Theo dõi cả đường đồng bộ và bất đồng bộ

Một workflow có thể tiếp tục sau khi API trả response. Ví dụ API trả 202 Accepted khi tạo yêu cầu hoàn tiền; worker xử lý sau đó mới gọi cổng thanh toán. Nếu chỉ kiểm tra controller, nhóm có thể bỏ qua quyền của worker, retry, trạng thái trung gian và cách xử lý callback.

Với từng workflow, hãy tìm:

- Những request nào tạo hoặc thay đổi trạng thái.
- Event nào được phát ra và consumer nào nhận event đó.
- Những tác vụ retry hoặc scheduler có thể chạy lại.
- Hệ thống bên ngoài nào có thể xác nhận hoặc từ chối kết quả.
- Điểm nào ghi nhận kết quả cuối cùng và điểm nào có thể phát sinh side effect lần nữa.

## 3. Xác định các workflow thường có tác động cao

Các ví dụ sau là điểm bắt đầu để rà soát. Mức rủi ro thực tế phụ thuộc vào dữ liệu, quy mô, quyền truy cập, khả năng đảo ngược và quy trình của từng sản phẩm.

| Workflow | Tác động chính | Điểm cần chú ý |
|---|---|---|
| Tạo đơn và thanh toán | Tài chính, tồn kho, quyền lợi khách hàng | Giá, số lượng, người trả tiền, payment intent và trạng thái |
| Hoàn tiền hoặc chargeback | Tài chính, uy tín và tranh chấp | Số tiền, lý do, payment gốc, hạn mức và idempotency |
| Chuyển tiền hoặc thay đổi số dư | Tài chính trực tiếp | Tài khoản nguồn/đích, tính nguyên tử và đối soát |
| Tạo coupon hoặc điều chỉnh giá | Doanh thu và tính công bằng | Thời hạn, đối tượng áp dụng, số lần dùng và stacking |
| Phát hành hóa đơn hoặc ghi nhận công nợ | Tài chính, kế toán và nghĩa vụ | Số tiền, thuế, định danh khách hàng và tính duy nhất |
| Cấp hoặc thu hồi gói dịch vụ | Quyền lợi và doanh thu | Entitlement, thời hạn, gia hạn và đồng bộ hệ thống |
| Xuất bản nội dung/chính sách | Danh tiếng và nghĩa vụ thông tin | Người duyệt, phiên bản, thời điểm công bố và phạm vi hiển thị |
| Gửi thông báo hàng loạt | Danh tiếng, riêng tư và chi phí | Audience, nội dung, consent, tốc độ và khả năng dừng |
| Khôi phục tài khoản/đổi thông tin xác thực | Danh tính, tài sản và niềm tin | Xác minh chủ thể, session cũ, MFA và kênh khôi phục |
| Khóa tài khoản hoặc gỡ nội dung | Quyền truy cập và danh tiếng | Căn cứ, người quyết định, khiếu nại và khả năng khôi phục |
| Export hoặc chia sẻ dữ liệu | Riêng tư, pháp lý và uy tín | Phạm vi dữ liệu, người nhận, link tải và thời hạn |
| Duyệt nhà cung cấp hoặc thay đổi tài khoản nhận tiền | Tài chính và gian lận | Xác minh đối tác, thay đổi thông tin ngân hàng và dual control |

### 3.1. Tác động trực tiếp và tác động dây chuyền

Tác động trực tiếp xảy ra ngay trong bước đang thực hiện, chẳng hạn một lệnh refund làm giảm số tiền thu được. Tác động dây chuyền xảy ra khi trạng thái hoặc dữ liệu thay đổi kích hoạt các hệ thống khác.

Ví dụ thay đổi địa chỉ giao hàng có thể dẫn đến:

1. Cập nhật địa chỉ trong đơn.
2. Gửi yêu cầu thay đổi cho đối tác vận chuyển.
3. Tính lại phí giao hàng hoặc thuế.
4. Gửi thông báo xác nhận cho khách hàng.
5. Cập nhật lịch giao và báo cáo vận hành.

Nếu kẻ tấn công thay đổi địa chỉ của đơn thuộc người khác, hậu quả không dừng ở một field trong database. Hàng hóa có thể bị chuyển hướng, phát sinh chi phí và gây tranh chấp. Khi lập bản đồ workflow, hãy ghi cả tác động dây chuyền và hệ thống phụ thuộc.

## 4. Vẽ workflow từ trigger đến kết quả cuối

Một sơ đồ workflow cần thể hiện actor, ranh giới tin cậy, các quyết định bảo mật, thay đổi trạng thái và side effect. Ví dụ luồng thanh toán:

~~~mermaid
flowchart TD
    A[Customer submits order] --> B[Authenticate and resolve tenant]
    B --> C[Check function and object permissions]
    C --> D[Recalculate price and validate inventory]
    D --> E[Create pending order and payment intent]
    E --> F[Payment provider processes payment]
    F --> G[Verify signed callback and correlate transaction]
    G --> H[Update payment and ledger atomically]
    H --> I[Publish order-paid event]
    I --> J[Reserve or release fulfillment]
    J --> K[Notify customer and record audit]
~~~

Ở mỗi bước, cần xác định dữ liệu đến từ đâu và ai có thể thay đổi nó. Giá do client gửi không phải nguồn đáng tin cậy để tính tiền. Callback từ nhà cung cấp phải được xác minh chữ ký hoặc cơ chế xác thực tương ứng. Event không nên được xử lý như một lệnh hợp lệ chỉ vì nó xuất hiện trong queue.

### 4.1. Đánh dấu trust boundary

Các ranh giới thường gặp:

- Client hoặc trình duyệt sang API gateway.
- API gateway sang service nội bộ.
- Service sang database hoặc cache.
- Service sang message broker và worker.
- Hệ thống nội bộ sang payment provider, email provider hoặc đối tác.
- Admin/support console sang API nghiệp vụ.

Với mỗi ranh giới, ghi rõ cách xác thực, dữ liệu được tin cậy ở mức nào, quyền nào được chuyển tiếp và cách xác minh message/callback. Không để một header hoặc field do client kiểm soát được xem như bằng chứng về actor, tenant, giá tiền hay kết quả giao dịch.

### 4.2. Ghi lại state transition

Workflow có tác động cao thường có nhiều trạng thái. Ví dụ payment có thể là CREATED, REQUIRES_ACTION, AUTHORIZED, CAPTURED, REFUND_PENDING, REFUNDED hoặc FAILED. Không nên cho client tự gửi trạng thái mới tùy ý.

Với mỗi transition, hãy ghi:

- Trạng thái nguồn được phép.
- Action khởi tạo transition.
- Principal hoặc service identity được phép.
- Điều kiện dữ liệu và hạn mức.
- Trạng thái đích.
- Side effect được phát ra.
- Cách xử lý lỗi, retry và trạng thái không xác định.

State machine giúp phát hiện những bước không hợp lệ, chẳng hạn refund trước capture, approve một yêu cầu đã bị hủy hoặc publish một bản nháp chưa được duyệt.

## 5. Đánh giá mức độ tác động và ưu tiên

Không phải workflow có tiền hoặc nội dung công khai đều cần cùng một mức kiểm soát. Cần đánh giá nhiều chiều thay vì chỉ dựa vào tên endpoint hoặc một điểm severity.

| Chiều đánh giá | Câu hỏi gợi ý |
|---|---|
| Giá trị tài chính | Một lần thực hiện có thể gây mất bao nhiêu tiền hoặc tạo nghĩa vụ gì? |
| Quy mô | Một actor có thể tác động một object hay hàng nghìn object? |
| Tầm ảnh hưởng | Chỉ một user, một tenant, nhiều tenant hay toàn bộ công chúng bị ảnh hưởng? |
| Danh tiếng | Thông tin có công khai, gắn với thương hiệu hoặc khó đính chính không? |
| Khả năng đảo ngược | Có thể hoàn tác hoàn toàn hay chỉ bồi thường/đính chính một phần? |
| Khả năng lạm dụng | Có thể tự động hóa, replay, thao túng input hoặc kết hợp nhiều endpoint không? |
| Độ tin cậy của nguồn | Trigger đến từ user, nhân viên, đối tác, webhook hay service account? |
| Khả năng phát hiện | Có audit, đối soát và cảnh báo đủ sớm không? |
| Nghĩa vụ pháp lý | Có dữ liệu cá nhân, kế toán, hợp đồng hoặc nghĩa vụ thông báo không? |

### 5.1. Phân loại mức ưu tiên

Có thể dùng ba mức để bắt đầu:

| Mức | Dấu hiệu | Kiểm soát tối thiểu nên xem xét |
|---|---|---|
| Cao | Có thể chuyển tiền, thay đổi số dư/quyền lợi, thay đổi tài khoản nhận tiền, công khai thông tin quan trọng hoặc ảnh hưởng nhiều tenant | Function và object authorization, kiểm tra trạng thái, xác nhận/dual control khi phù hợp, idempotency, audit và cảnh báo |
| Trung bình | Có thể thay đổi thông tin thương mại, nội dung hướng tới khách hàng, trạng thái đơn hoặc dữ liệu quan trọng trong phạm vi giới hạn | Permission rõ ràng, validation, object scope, giới hạn tốc độ, audit theo mức độ |
| Thấp | Tác động nhỏ, dễ đảo ngược, không làm lộ dữ liệu nhạy cảm và khó tạo hiệu ứng dây chuyền | Xác thực, authorization cơ bản, validation và log vận hành phù hợp |

Đây là cách phân loại ban đầu, không phải quy tắc cứng. Một endpoint đọc có thể có rủi ro cao nếu trả dữ liệu nhạy cảm hoặc cho phép export hàng loạt. Một endpoint cập nhật nội bộ có thể có tác động lớn nếu dữ liệu đó quyết định giá, quyền lợi hoặc thông tin công khai.

### 5.2. Xem xét khả năng lặp và phạm vi hàng loạt

Một thao tác đơn lẻ có thể có tác động nhỏ nhưng trở nên nghiêm trọng khi lặp tự động hoặc thực hiện hàng loạt. Hãy hỏi:

- Có thể gọi action bao nhiêu lần trong một khoảng thời gian?
- Có thể gửi danh sách object hoặc batch lớn không?
- Một user có thể tạo nhiều API key hoặc service account để chia tải không?
- Retry hoặc callback lặp có tạo side effect nhiều lần không?
- Có thể thao túng số tiền, số lượng, tỷ lệ chiết khấu hoặc audience không?

Phạm vi hàng loạt, tốc độ và tính lặp cần được ghi vào đánh giá rủi ro. Đây là lý do workflow có tác động tài chính thường cần idempotency, quota, rate limit và concurrency limit.

## 6. Nhận diện điểm kiểm soát trong workflow tài chính

Với workflow tạo hoặc thay đổi tiền, cần xác định điểm nào quyết định giá trị, điểm nào xác nhận giao dịch và điểm nào ghi nhận kết quả.

### 6.1. Tính giá trị ở phía server

Không tin các giá trị tài chính do client gửi như:

- Unit price, discount, tax, shipping fee hoặc total amount.
- Currency hoặc exchange rate.
- Account owner, beneficiary hoặc merchant.
- Refund amount, fee hoặc balance.
- Trạng thái payment, invoice hoặc settlement.

Server cần tính hoặc lấy các giá trị này từ nguồn tin cậy và kiểm tra lại tại thời điểm thực hiện. Nếu nghiệp vụ cho phép client đề xuất số tiền, server vẫn phải kiểm tra hạn mức, quyền và quy tắc làm tròn.

### 6.2. Tách yêu cầu khỏi xác nhận giao dịch

Tạo payment intent không có nghĩa tiền đã được thu. Gửi yêu cầu refund không có nghĩa nhà cung cấp đã hoàn tiền. Cần phân biệt trạng thái yêu cầu, trạng thái xử lý bên ngoài và trạng thái được ghi nhận trong hệ thống.

Một luồng an toàn thường:

1. Xác thực caller và quyền trên order/payment.
2. Kiểm tra amount, currency, trạng thái và hạn mức.
3. Tạo operation có ID duy nhất và idempotency key.
4. Gọi provider bằng credential của server.
5. Xác minh callback hoặc truy vấn trạng thái provider.
6. Cập nhật trạng thái và ledger theo quy tắc nhất quán.
7. Phát event sau khi thay đổi nội bộ đã được commit.
8. Đối soát khi kết quả provider và hệ thống nội bộ không khớp.

Không dựa vào response redirect từ trình duyệt hoặc tham số query do client quay lại để kết luận thanh toán thành công.

### 6.3. Idempotency và chống replay

Một request có thể được gửi lại do timeout, mạng chập chờn, client retry hoặc webhook được gửi nhiều lần. Với thao tác có side effect tài chính, cần idempotency key hoặc mã operation duy nhất gắn với actor, tenant và loại nghiệp vụ.

Hệ thống cần:

- Lưu kết quả của operation đã xử lý.
- Kiểm tra cùng key không được dùng lại với payload khác.
- Bảo đảm thao tác ghi trạng thái và ghi nhận idempotency nhất quán.
- Đặt thời hạn lưu key phù hợp với chu kỳ retry và đối soát.
- Xử lý callback trùng mà không tạo giao dịch hoặc ledger entry thứ hai.

Idempotency không thay thế authorization. Người gọi vẫn phải có quyền thực hiện operation; key chỉ giúp kiểm soát việc thực hiện lặp.

### 6.4. Ledger, transaction và đối soát

Với hệ thống có sổ cái, việc ghi nhận debit/credit cần tuân theo nguyên tắc nghiệp vụ và tính nhất quán. Không chỉ cập nhật một field balance nếu nghiệp vụ yêu cầu lịch sử giao dịch và đối soát.

Hãy xác định:

- Bút toán nào được tạo cho từng transition.
- Mỗi operation có mã tham chiếu duy nhất nào.
- Cách xử lý giao dịch một phần hoặc kết quả không xác định.
- Cách đối soát với provider, ngân hàng hoặc hệ thống kế toán.
- Quy trình điều chỉnh và phê duyệt khi dữ liệu lệch.

Không cố giả định một transaction database có thể bao trùm cả dịch vụ bên ngoài. Với side effect phân tán, cần thiết kế state machine, outbox/inbox, retry có kiểm soát và bước reconciliation.

### 6.5. Dual control và separation of duties

Một số thao tác có tác động lớn nên yêu cầu hai người hoặc hai vai trò độc lập. Ví dụ người tạo yêu cầu chuyển tiền không được tự phê duyệt; người cập nhật tài khoản nhận tiền không được tự xác nhận thay đổi đó.

Dual control cần bảo đảm:

- Người tạo và người duyệt là principal độc lập theo policy.
- Người duyệt xem đúng dữ liệu đã được cố định trong yêu cầu.
- Thay đổi payload sau phê duyệt làm mất hiệu lực approval hoặc yêu cầu duyệt lại.
- Approval có thời hạn và được gắn với phiên bản dữ liệu.
- Mọi quyết định và thay đổi được audit.

Không nên dùng một cờ isApproved do client gửi để thay thế quy trình phê duyệt phía server.

## 7. Nhận diện workflow gây tác động danh tiếng

Tác động danh tiếng thường khó định lượng và khó đảo ngược hơn thay đổi dữ liệu nội bộ. Một thông tin sai có thể được sao chép hoặc chia sẻ trước khi tổ chức kịp đính chính.

### 7.1. Nội dung công khai và thông tin chính thức

Các workflow cần rà soát:

- Publish bài viết, thông báo, chính sách, bảng giá hoặc nội dung sản phẩm.
- Sửa nội dung đã công khai hoặc thay đổi lịch phát hành.
- Gửi thông báo khẩn cấp hoặc thông báo sự cố.
- Thay đổi nội dung trên trang hỗ trợ, trạng thái dịch vụ hoặc trang trạng thái.
- Phát hành tài liệu, báo cáo hoặc thông tin gắn với tổ chức.

Kiểm soát nên xem xét:

- Permission riêng cho draft, review, approve và publish.
- Preview và kiểm tra phiên bản trước khi công khai.
- Approval độc lập cho nội dung có tác động cao.
- Lưu bản trước/sau và thời điểm phát hành.
- Cơ chế unpublish hoặc đính chính nhanh.
- Giới hạn audience, kênh và thời gian gửi.

### 7.2. Email, SMS và thông báo hàng loạt

Endpoint gửi thông báo có thể gây thiệt hại danh tiếng, chi phí và rủi ro riêng tư nếu gửi sai người hoặc sai nội dung. Cần kiểm tra:

- Audience được xác định từ nguồn dữ liệu nào.
- Người gửi có quyền liên hệ nhóm người nhận đó không.
- Consent, unsubscribe và preference có được áp dụng không.
- Nội dung có chứa dữ liệu của tenant hoặc người dùng khác không.
- Có preview, test recipient, approval và giới hạn số lượng không.
- Có thể pause hoặc cancel chiến dịch khi phát hiện sai sót không.

Không để client gửi danh sách email tùy ý rồi dùng quyền của một tenant để gửi thay mặt toàn hệ thống. Cần giới hạn tenant, sender identity, template và phạm vi người nhận.

### 7.3. Danh tính, khôi phục tài khoản và thay đổi quyền truy cập

Account recovery, đổi email, đổi số điện thoại, reset MFA, thay đổi thiết bị tin cậy và chuyển quyền sở hữu có thể tạo ra rủi ro chiếm đoạt tài khoản. Hậu quả không chỉ là mất quyền truy cập mà còn có thể dẫn đến thanh toán trái phép, rò rỉ dữ liệu và mất niềm tin.

Workflow cần xác minh chủ thể bằng yếu tố phù hợp với mức rủi ro, thông báo qua kênh độc lập, thu hồi session/token cũ khi cần và có cơ chế hỗ trợ khi người dùng bị khóa nhầm. Không để một endpoint chỉ yêu cầu đăng nhập bằng session hiện tại có thể tự thay đổi mọi yếu tố khôi phục mà không có kiểm tra bổ sung.

### 7.4. Kiểm duyệt, khóa tài khoản và xử lý khiếu nại

Gỡ nội dung, ẩn đánh giá, khóa tài khoản hoặc đình chỉ tổ chức có thể ảnh hưởng trực tiếp đến quyền lợi và uy tín. Hãy xác định:

- Ai có quyền đưa ra quyết định?
- Tiêu chí hoặc căn cứ nào được áp dụng?
- Có cần review thứ hai hoặc escalation không?
- Người bị ảnh hưởng có nhận thông báo và kênh khiếu nại không?
- Có thể khôi phục trạng thái khi quyết định sai không?
- Có audit lý do và người thực hiện không?

Các thao tác moderation cần tách quyền xem xét, phê duyệt và thực thi khi mức tác động yêu cầu. Tránh để một endpoint chung cho phép bất kỳ nhân viên nào xóa nội dung hoặc khóa tài khoản mà không có lý do và audit.

## 8. Xác định các điểm dễ bị lạm dụng trong workflow

Sau khi vẽ luồng, hãy tìm các điểm mà dữ liệu không tin cậy có thể thay đổi kết quả hoặc vượt qua một quyết định.

| Điểm rủi ro | Câu hỏi kiểm tra | Ví dụ kiểm soát |
|---|---|---|
| Input quyết định giá trị | Client có thể tự đặt amount, discount, owner hoặc recipient không? | Tính phía server, allowlist field và validation |
| Authorization | Mỗi bước có kiểm tra function và object scope không? | Policy theo principal, action, object và tenant |
| Approval | Người tạo có tự duyệt được không? Approval có gắn với đúng payload không? | Dual control và version-bound approval |
| State transition | Có thể bỏ qua bước hoặc gọi action sai thứ tự không? | State machine và transition guard |
| Replay/retry | Gửi lại request hoặc callback có tạo side effect lặp không? | Idempotency và deduplication |
| Race condition | Hai request đồng thời có vượt hạn mức hoặc duyệt hai lần không? | Transaction, lock hoặc optimistic version |
| Batch/bulk | Một request có thể tác động hàng nghìn object không? | Per-item authorization, quota và giới hạn batch |
| External callback | Hệ thống có tin callback chưa xác minh không? | Signature verification, correlation và replay protection |
| Async processing | Worker có giữ đúng tenant, actor và permission context không? | Trusted job metadata và service identity |
| Notification | Có gửi sai audience hoặc lộ dữ liệu qua template không? | Recipient scope, preview, approval và send limit |
| Recovery | Có thể khôi phục hoặc đính chính khi sai không? | Compensation, rollback hoặc manual recovery |

Một workflow có thể có nhiều điểm yếu kết hợp. Ví dụ attacker sửa amount, gửi request lặp và khai thác race condition để tạo nhiều refund. Vì vậy, không nên chỉ kiểm tra từng endpoint một cách độc lập; hãy mô phỏng toàn bộ chuỗi thao tác.

## 9. Gắn kiểm soát bảo mật với mức tác động

Sau khi phân loại workflow, chọn kiểm soát tương ứng. Không phải mọi luồng đều cần dual control, nhưng mọi luồng có tác động cao cần có authorization, validation, kiểm soát trạng thái và bằng chứng vận hành phù hợp.

| Kiểm soát | Khi nào cần đặc biệt chú ý |
|---|---|
| Function authorization | Action quản trị, tài chính, publish, export hoặc thay đổi quyền |
| Object/tenant authorization | Mọi workflow thao tác trên dữ liệu thuộc user, tổ chức hoặc merchant |
| Field allowlist | Update giá, số dư, owner, role, trạng thái hoặc thông tin nhận tiền |
| State machine | Thanh toán, refund, phê duyệt, xuất bản, khóa/mở tài khoản |
| Idempotency | Payment, refund, transfer, webhook, job và action có thể retry |
| Dual control | Chuyển tiền lớn, thay đổi tài khoản nhận tiền, publish thông tin quan trọng |
| Rate limit/quota | Gửi thông báo, export, batch, thử thanh toán hoặc action có thể tự động hóa |
| Audit | Mọi thay đổi tài chính, quyền truy cập và quyết định có tác động cao |
| Reconciliation | Giao dịch với provider hoặc hệ thống kế toán bên ngoài |
| Alert/kill switch | Dấu hiệu gian lận, gửi nhầm hàng loạt hoặc sai lệch trạng thái |

### 9.1. Xác minh dữ liệu ở từng bước

Validation ở đầu workflow không đảm bảo dữ liệu vẫn hợp lệ khi thực thi. Giá, quyền, hạn mức, trạng thái hoặc quan hệ object có thể thay đổi trong lúc chờ phê duyệt hoặc xử lý bất đồng bộ.

Với action nhạy cảm, cần kiểm tra lại những điều kiện quan trọng ngay trước side effect. Nếu payload đã được duyệt thay đổi, yêu cầu có thể phải quay lại bước review. Nếu quyền bị thu hồi trong thời gian chờ, worker cần tuân theo chính sách hiệu lực đã định nghĩa.

### 9.2. Phân quyền service-to-service

Workflow thường chuyển từ request của user sang service account hoặc worker. Cần giữ được thông tin ai khởi tạo và service nào thực hiện:

- User hoặc actor ban đầu được ghi trong audit metadata.
- Service identity chỉ có permission cần cho nhiệm vụ.
- Tenant context được truyền qua kênh tin cậy.
- Consumer xác minh event đến từ producer hợp lệ.
- Không dùng credential quản trị toàn hệ thống cho mọi worker.

Nếu worker thực hiện action thay mặt user, cần xác định policy được đánh giá tại thời điểm enqueue, thời điểm thực thi hay cả hai. Đối với action tài chính hoặc quyền lợi quan trọng, thường cần kiểm tra lại các điều kiện có thể thay đổi trước khi thực hiện side effect.

## 10. Thiết kế xử lý lỗi và khôi phục

Workflow có tác động cao cần định nghĩa rõ trạng thái khi một bước thành công nhưng bước kế tiếp thất bại. Không thể giả định toàn bộ chuỗi nhiều service cùng commit hoặc rollback như một database transaction.

Các chiến lược thường dùng:

- **Database transaction:** giữ các thay đổi nội bộ liên quan trong cùng transaction.
- **Transactional outbox:** ghi event cần phát trong cùng transaction với thay đổi dữ liệu, sau đó publisher gửi event.
- **Inbox/deduplication:** ghi nhận event đã xử lý để chống callback hoặc message trùng.
- **Saga/compensation:** xác định hành động bù khi một bước phân tán thất bại.
- **Reconciliation:** so sánh trạng thái nội bộ với provider hoặc hệ thống kế toán để phát hiện lệch.
- **Manual review:** chuyển sang trạng thái chờ người xử lý khi kết quả không xác định hoặc vượt ngưỡng rủi ro.

Ví dụ payment provider đã capture tiền nhưng service nội bộ timeout trước khi ghi nhận. Không nên tự động tạo payment mới hoặc báo khách hàng thanh toán thất bại ngay. Hệ thống cần tra cứu operation theo mã tham chiếu, đối soát trạng thái và hoàn tất hoặc bù trừ theo quy trình.

Với workflow công khai nội dung hoặc gửi thông báo, khả năng rollback có giới hạn. Có thể unpublish, gửi đính chính hoặc thông báo thu hồi, nhưng không thể bảo đảm mọi người đã xem nội dung cũ sẽ quên nó. Vì vậy, bước review trước khi công bố và khả năng dừng sớm đặc biệt quan trọng.

## 11. Kiểm thử workflow có tác động cao

Kiểm thử cần đi theo chuỗi nghiệp vụ và các biến thể lỗi, không chỉ kiểm tra status code của endpoint đầu tiên.

### 11.1. Kiểm thử luồng hợp lệ và luồng bị từ chối

Với mỗi workflow, cần có:

- Actor đúng quyền, object đúng phạm vi và trạng thái hợp lệ.
- Actor thiếu function permission.
- Actor có function permission nhưng không có quyền trên object.
- Tenant khác hoặc object lồng nhau ngoài phạm vi.
- Field nhạy cảm bị gửi thêm hoặc giá trị tài chính bị thay đổi.
- State transition sai thứ tự.
- Approval bởi chính người tạo khi policy cấm.
- Callback không có chữ ký hợp lệ hoặc sai correlation.

### 11.2. Kiểm thử retry, concurrency và failure

Thử:

- Gửi cùng request nhiều lần với cùng idempotency key.
- Dùng cùng key nhưng payload khác.
- Gửi callback hoặc message trùng.
- Gửi hai request đồng thời khi hạn mức gần cạn.
- Timeout sau khi provider đã thực hiện side effect.
- Worker crash sau khi ghi dữ liệu nhưng trước khi acknowledge message.
- Dependency không khả dụng hoặc trả kết quả không xác định.
- Hủy hoặc thay đổi quyền trong khi job đang chờ.

Kết quả phải bảo đảm không có thanh toán/refund lặp, không vượt hạn mức, không bỏ qua approval và không để dữ liệu nội bộ lệch mà không có cơ chế phát hiện.

### 11.3. Kiểm thử tác động danh tiếng

Với workflow publish hoặc gửi thông báo, cần thử:

- User không có quyền publish nhưng có quyền soạn draft.
- Nội dung thay đổi sau khi được duyệt.
- Audience chứa người nhận ngoài tenant.
- Template render dữ liệu nhạy cảm hoặc sai người nhận.
- Gửi hàng loạt bị pause giữa chừng.
- Nội dung đã công khai cần unpublish hoặc đính chính.
- Một nhân viên tự duyệt nội dung do chính mình tạo khi policy yêu cầu người duyệt độc lập.

### 11.4. Test end-to-end và bằng chứng

Test end-to-end nên kiểm tra cả trạng thái cuối, ledger/audit event, notification, job và dữ liệu ở hệ thống phụ thuộc. Chỉ thấy API trả 200 hoặc 202 không chứng minh workflow hoàn tất đúng.

Lưu lại request ID, operation ID, trace ID, trạng thái trước/sau và audit event trong môi trường test. Dữ liệu kiểm thử không nên dùng credential hoặc thông tin cá nhân thật.

## 12. Giám sát và cảnh báo theo workflow

Log theo endpoint hữu ích nhưng chưa đủ để hiểu một nghiệp vụ kéo dài qua nhiều service. Nên gắn operation ID hoặc workflow ID xuyên suốt request, event, job và callback.

Các tín hiệu nên theo dõi:

- Số lượng payment, refund, transfer hoặc adjustment theo tenant và thời gian.
- Tỷ lệ action bị từ chối, vượt hạn mức hoặc chuyển sang manual review.
- Số lần callback trùng, signature invalid hoặc correlation mismatch.
- Tỷ lệ payment/refund không khớp khi đối soát.
- Số lần thay đổi tài khoản nhận tiền, role hoặc thông tin khôi phục.
- Số lượng nội dung được publish, unpublish hoặc chỉnh sửa sau publish.
- Số người nhận, tốc độ gửi và tỷ lệ lỗi của notification campaign.
- Job chạy quá lâu, retry nhiều lần hoặc stuck ở trạng thái trung gian.

Audit cần ghi actor, action, object, tenant, thời điểm, kết quả và lý do theo chính sách dữ liệu. Không ghi token, secret, thông tin thẻ đầy đủ hoặc toàn bộ payload nhạy cảm. Metric label nên dùng endpoint template, action và nhóm rủi ro thay vì ID tùy ý có cardinality cao.

Với workflow quan trọng, cần cảnh báo theo bất thường so với baseline và ngưỡng nghiệp vụ. Ví dụ số refund tăng đột biến, nhiều lần thay đổi tài khoản nhận tiền, số lượng thông báo vượt mức dự kiến hoặc một service account bắt đầu gọi chức năng ngoài phạm vi bình thường.

## 13. Ví dụ: lập bản đồ workflow thay đổi tài khoản nhận tiền

Giả sử một tổ chức cho phép merchant thay đổi tài khoản ngân hàng nhận settlement. Đây là workflow có tác động tài chính trực tiếp và có thể bị khai thác để chuyển tiền sang tài khoản của kẻ tấn công.

| Bước | Hành động | Kiểm soát cần có |
|---|---|---|
| 1 | Merchant yêu cầu thay đổi tài khoản | Xác thực mạnh, function permission và tenant/object scope |
| 2 | Nhập thông tin tài khoản mới | Validation, chuẩn hóa và kiểm tra định dạng |
| 3 | Xác minh quyền kiểm soát tài khoản | Quy trình xác minh độc lập với dữ liệu do client gửi |
| 4 | Gửi yêu cầu phê duyệt | Tách người tạo và người duyệt khi chính sách yêu cầu |
| 5 | Người có thẩm quyền duyệt | Approval gắn với payload/version cụ thể |
| 6 | Cập nhật thông tin settlement | Transaction, audit và kiểm soát concurrency |
| 7 | Đồng bộ với provider | Service identity tối thiểu, idempotency và correlation ID |
| 8 | Thông báo và theo dõi | Gửi cảnh báo qua kênh đã đăng ký, giám sát thay đổi bất thường |

Các test quan trọng:

- User không thuộc merchant không thể khởi tạo thay đổi.
- Nhân viên không có permission không thể duyệt.
- Người tạo không thể tự duyệt nếu policy cấm.
- Thay đổi payload sau khi duyệt làm approval mất hiệu lực.
- Retry không cập nhật provider nhiều lần.
- Callback giả hoặc callback của merchant khác bị từ chối.
- Nếu provider cập nhật thành công nhưng hệ thống nội bộ lỗi, reconciliation có thể khôi phục trạng thái.

Ví dụ này cho thấy một workflow quan trọng thường cần nhiều lớp bảo vệ. Chỉ kiểm tra đăng nhập hoặc chỉ xác minh định dạng số tài khoản không đủ để bảo đảm tiền được chuyển đúng người nhận.

## 14. Checklist nhận diện workflow trước khi phát hành

- [ ] Đã lập danh sách workflow từ endpoint, event, job, webhook và công cụ nội bộ.
- [ ] Mỗi workflow có owner nghiệp vụ và owner kỹ thuật.
- [ ] Đã xác định trigger, actor, tenant, object, dữ liệu và side effect.
- [ ] Đã phân loại tác động tài chính, danh tiếng, quyền lợi, riêng tư và nghĩa vụ pháp lý.
- [ ] Đã đánh giá quy mô, khả năng lặp, phạm vi ảnh hưởng và khả năng đảo ngược.
- [ ] Đã vẽ luồng từ request đến event, worker, provider và kết quả cuối.
- [ ] Trust boundary và nguồn dữ liệu tin cậy được đánh dấu rõ.
- [ ] State transition và điều kiện cho phép từng action được định nghĩa.
- [ ] Giá trị tài chính và quyền lợi được tính/kiểm tra phía server.
- [ ] Function, object, tenant và field authorization được áp dụng ở đúng bước.
- [ ] Workflow có side effect hỗ trợ idempotency, retry an toàn và deduplication.
- [ ] Thao tác rủi ro cao có approval, dual control hoặc hạn mức phù hợp.
- [ ] Có phương án compensation, reconciliation hoặc manual review khi thất bại.
- [ ] Audit, operation ID, metric và cảnh báo theo workflow đã được xác định.
- [ ] Có test end-to-end cho luồng hợp lệ, thiếu quyền, replay, concurrency và lỗi dependency.
- [ ] Workflow công khai hoặc gửi thông báo có preview, approval, giới hạn audience và khả năng dừng/đính chính.

Nhận diện workflow có tác động tài chính hoặc danh tiếng là bước nền tảng để phân bổ kiểm soát bảo mật đúng chỗ. Khi nhóm nhìn được toàn bộ chuỗi từ trigger đến side effect và hậu quả cuối cùng, họ có thể ưu tiên authorization, approval, idempotency, audit, đối soát và khả năng khôi phục theo rủi ro nghiệp vụ thực tế.
