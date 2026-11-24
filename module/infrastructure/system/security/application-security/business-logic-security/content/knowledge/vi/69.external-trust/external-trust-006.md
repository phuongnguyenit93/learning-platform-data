# External disagreement handling — Xử lý bất đồng từ hệ thống bên ngoài

Một webhook báo giao dịch đã thành công, API truy vấn vẫn trả trạng thái đang xử lý, còn đơn hàng nội bộ đã nhận yêu cầu hủy. Nếu ứng dụng chọn thông điệp đến sau cùng rồi cho giao hàng, kẻ tấn công có thể tận dụng độ trễ, replay hoặc sai ánh xạ để vượt quy tắc nghiệp vụ.

**External disagreement handling** là việc nhận diện, phân loại và xử lý những thông tin không thống nhất giữa hệ thống nội bộ với nguồn ngoài, hoặc giữa nhiều nguồn ngoài. Mục tiêu là đưa ra quyết định có căn cứ trong khi vẫn giữ các business invariant, kể cả khi chưa thể xác định kết quả cuối cùng.

Bài thuộc chương **External Trust** của module **SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY**. Phạm vi tập trung vào logic ứng dụng: quyền quyết định của từng nguồn, state machine, phân quyền theo đối tượng, transaction, idempotency và kiểm thử tình huống lạm dụng.

Sau bài học, người học có thể:

- Phân biệt thông tin trễ, dữ liệu sai phạm vi và mâu thuẫn nghiệp vụ thực sự.
- Xác định nguồn có thẩm quyền cho từng sự kiện hoặc thuộc tính.
- Thiết kế trạng thái tạm giữ và quy trình đối soát có giới hạn.
- Áp dụng kết quả đối soát an toàn khi có hủy đơn, retry hoặc worker chạy đồng thời.
- Tránh sửa dữ liệu, giao hàng hoặc thực hiện bù trừ dựa trên bằng chứng chưa đủ.

## 1. Bất đồng không chỉ là “hai status khác nhau”

Giả sử một đơn hàng cần xác nhận thanh toán và giữ hàng trước khi được phép giao. Nền tảng nhận thông tin từ trình duyệt khách hàng, nhà cung cấp thanh toán, kho và hệ thống đánh giá rủi ro.

Các tình huống sau cần cách xử lý khác nhau:

| Quan sát | Có thể là vấn đề gì? |
|---|---|
| Client báo thành công, server chưa có xác nhận | Khẳng định từ nguồn không đủ thẩm quyền |
| Webhook báo thành công, bản sao API còn pending | Độ trễ đồng bộ hoặc khác thời điểm quan sát |
| Hai payload có cùng event ID nhưng số tiền khác | Xung đột toàn vẹn hoặc lỗi tích hợp |
| Provider báo thành công nhưng merchant account không khớp | Sai phạm vi hoặc ánh xạ đối tượng |
| Provider báo đã thu tiền, hệ thống rủi ro yêu cầu review | Hai sự thật thuộc hai miền khác nhau, chưa chắc mâu thuẫn |
| Giao dịch đã thu tiền nhưng sau đó có hoàn tiền | Hai sự kiện ở các bước khác nhau của vòng đời |
| Request timeout nhưng provider đã thực hiện | Kết quả chưa xác định tại bên gọi |
| Hai nhà cung cấp có ID giống nhau | Namespace khác nhau, không phải cùng đối tượng |

Điều đầu tiên cần hỏi là:

> Hai thông tin có nói về cùng thực thể, cùng thao tác, cùng phạm vi, cùng thời điểm và cùng ý nghĩa nghiệp vụ không?

So sánh chuỗi `SUCCESS` với `FAILED` trước khi trả lời câu hỏi đó thường dẫn đến quyết định sai.

## 2. Tách sự thật bên ngoài khỏi quyền quyết định nội bộ

### 2.1. Nguồn có thẩm quyền theo từng miền

Không có nguồn nào mặc nhiên có quyền quyết định mọi trường của đơn hàng.

| Sự thật hoặc quyết định | Nguồn chịu trách nhiệm trong ví dụ |
|---|---|
| Điều khoản giá trị đơn hàng đã được chấp thuận | Nền tảng, gắn với phiên bản đơn hàng |
| Một giao dịch cụ thể đã được nhà cung cấp thực hiện hay chưa | Nhà cung cấp của giao dịch đó, theo hợp đồng API |
| Hàng đang được giữ cho đơn nào | Hệ thống quản lý giữ hàng |
| Đơn có bị yêu cầu hủy hoặc đang bị tạm giữ không | State machine đơn hàng nội bộ |
| Có vượt điều kiện phê duyệt rủi ro không | Chính sách và quy trình phê duyệt của nền tảng |
| Có được phát lệnh giao hàng hay không | Quyết định nghiệp vụ kết hợp các điều kiện trên |

Nhà cung cấp báo đã thu tiền không được tự ghi đè `risk_review_status` hoặc hủy bỏ yêu cầu hủy đơn. Ngược lại, hệ thống nội bộ không được xóa sự thật giao dịch đã xảy ra chỉ vì đơn đang muốn hủy.

Đây là sự phân biệt giữa **ghi nhận một sự kiện** và **cho phép một hành động tiếp theo**.

### 2.2. Biểu diễn nhiều chiều thay vì một status tổng

Một mô hình dễ gây lỗi:

~~~text
order.status = SUCCESS
~~~

Một mô hình rõ hơn:

~~~text
order.lifecycle_state
payment_attempt.capture_state
payment_attempt.refund_state
inventory_reservation.state
risk_review.state
order.active_holds
external_reconciliation.state
~~~

Ví dụ `capture_state = CONFIRMED` và `refund_state = CONFIRMED` có thể cùng đúng. Không nên ép chúng vào một danh sách tuyến tính rồi cho rằng trạng thái “lớn hơn” luôn thắng.

Tương tự, đơn hàng bị hủy không tự chứng minh giao dịch đã được hoàn; phải có luồng xử lý tác động bên ngoài tương ứng.

## 3. Ví dụ xuyên suốt: có được phát lệnh giao hàng không?

Đơn `ORDER-42` thuộc tenant T1 có:

~~~text
approved_order_amount      = 250000
currency                   = VND
payment_attempt            = ATTEMPT-7
provider_account           = ACCOUNT-A
provider_transaction       = TX-91
payment_binding_generation = 3
inventory_reservation      = RESERVATION-8
order_version              = 12
~~~

Các tên trạng thái trong bài là mô hình chuẩn hóa để minh họa, không phải enum bắt buộc của một nhà cung cấp cụ thể.

Quy tắc phát lệnh giao hàng:

~~~text
can_dispatch =
  order_allows_dispatch
  AND verified_payment_satisfies_approved_terms
  AND inventory_reservation_is_valid
  AND risk_approval_is_valid
  AND no_relevant_unresolved_hold
  AND current_binding_and_decision_generation
~~~

Các invariant quan trọng:

| Mã | Invariant |
|---|---|
| INV-01 | Chỉ dùng bằng chứng đã xác minh và ánh xạ đúng tenant, account, transaction và payment attempt |
| INV-02 | Client hoặc nguồn không có thẩm quyền không được nâng trạng thái thành “đủ điều kiện giao” |
| INV-03 | Thông tin đến muộn không được ghi đè một quyết định mới hơn mà không kiểm tra phiên bản và ngữ nghĩa |
| INV-04 | Mâu thuẫn liên quan đến điều kiện bắt buộc phải chặn tác động khó đảo ngược trong khi chưa đủ căn cứ |
| INV-05 | Timeout không tự được diễn giải thành thao tác chưa xảy ra |
| INV-06 | Retry hoặc nhiều worker không được tạo tác động nghiệp vụ trùng |
| INV-07 | Kết quả đối soát phải được áp dụng trên context và thế hệ binding còn phù hợp |
| INV-08 | Giải quyết một case không được tự xóa hold của rủi ro, hủy đơn hoặc case khác |
| INV-09 | Can thiệp thủ công không được thay thế bằng chứng bằng một cờ “force success” thiếu kiểm soát |

Hệ thống có thể tiếp tục hiển thị trạng thái đơn hoặc cho xem lịch sử trong khi giữ lại quyền phát lệnh giao. Không cần đóng băng mọi tính năng chỉ vì một thuộc tính chưa rõ.

## 4. Xác minh và chuẩn hóa trước khi so sánh

### 4.1. Xác thực nguồn chưa chứng minh đúng đối tượng

Với webhook hoặc response API, cần kiểm tra phù hợp với kênh:

- Nguồn và credential được xác minh theo cơ chế tích hợp.
- Provider account, môi trường test/live và tenant được ánh xạ từ cấu hình tin cậy.
- Transaction ID thuộc đúng namespace và liên kết với attempt đã tạo tại server.
- Số tiền, loại tiền, loại thao tác và các tham chiếu nghiệp vụ khớp context cần kiểm tra.
- Payload đúng schema và phiên bản API được hỗ trợ.
- Quyền của tích hợp và của worker đối soát còn phù hợp với nhiệm vụ.

Một webhook có chữ ký hợp lệ nhưng thuộc account khác không được dùng để giải quyết đơn hàng này. Không tự đổi binding chỉ vì payload chứa một `orderId` có vẻ hợp lệ.

Với truy vấn chủ động, endpoint và account phải do server chọn từ cấu hình. Không gọi URL tùy ý do webhook hoặc client cung cấp để “xác minh”, vì việc đó có thể biến quy trình đối soát thành đường truy cập hệ thống khác ngoài ý muốn.

### 4.2. Chuẩn hóa đúng nghĩa nghiệp vụ

Một adapter cần tạo quan sát có cấu trúc thay vì trả thẳng chuỗi status:

~~~text
source
source_account
environment
external_resource_id
local_attempt_binding
binding_generation
observation_kind
normalized_fact
amount_in_contract_units
currency
source_revision, nếu có
source_occurred_at, nếu có
received_at
verification_result
evidence_reference
~~~

Các trạng thái “được ủy quyền”, “đã thu”, “đã quyết toán” hoặc “đã hoàn” không nên được gộp thành một giá trị thành công nếu quy tắc giao hàng cần phân biệt chúng.

Số tiền phải được diễn giải theo đơn vị trong hợp đồng API và loại tiền tương ứng. Không dùng số thực nhị phân hoặc mặc định mọi tiền tệ đều có cùng số chữ số thập phân. Một field bị thiếu không được tự đổi thành số 0 rồi so sánh như dữ liệu hợp lệ.

Nếu có nhiều lần thu hoặc hoàn một phần, chính sách phải kiểm tra từng tác động và tổng hợp hợp lệ. Một cờ `paid=true` đơn lẻ có thể không đủ.

### 4.3. Lưu bằng chứng và projection riêng

Có thể giữ:

- Quan sát gốc trong kho bằng chứng có giới hạn và quyền truy cập phù hợp.
- Quan sát đã chuẩn hóa, có nguồn và tham chiếu.
- Projection hiện tại dùng cho quyết định.
- Case đối soát và lịch sử quyết định.

Không xóa quan sát trước chỉ vì một API trả giá trị khác. Nếu thông tin không hợp lệ, đánh dấu hoặc cách ly; không đưa vào projection có quyền cho phép tác động.

Lưu payload gốc không đồng nghĩa ghi token, khóa bí mật hoặc dữ liệu nhạy cảm vào log phổ thông.

## 5. Phân loại bất đồng trước khi chọn cách giải quyết

### 5.1. Không đủ bằng chứng

Ví dụ: chỉ có redirect từ trình duyệt báo `success=true`.

Cách xử lý: ghi nhận ý định hoặc tín hiệu, giữ trạng thái chờ, lấy xác nhận server-to-server theo thiết kế. Không coi đây là hai nguồn ngang quyền để biểu quyết.

### 5.2. Chênh lệch do độ trễ

Ví dụ: webhook phản ánh thay đổi mới hơn projection nội bộ, hoặc API đang đọc một bản sao trễ.

Cách xử lý: kiểm tra hợp đồng độ nhất quán, revision và khả năng đọc trạng thái hiện tại. Đặt thời hạn đối soát, giữ hành động nhạy cảm nếu điều kiện chưa rõ, không retry vô hạn.

Bản truy vấn “vừa gọi xong” chỉ mới về thời điểm quan sát; nó không tự bảo đảm dữ liệu nguồn mới hơn mọi webhook.

### 5.3. Sự kiện đến sai thứ tự hoặc phát lại

Một sự kiện pending cũ đến sau sự kiện xác nhận không tự đưa đối tượng quay về pending.

Stripe là ví dụ thực tế: tài liệu webhook nêu rằng thứ tự giao event không được bảo đảm và một event có thể được gửi nhiều lần. Đây là đặc tính của kênh cần được xử lý, không phải bằng chứng mọi lần khác trạng thái đều là gian lận. [Stripe — Event delivery behaviors](https://docs.stripe.com/webhooks#event-delivery-behaviors).

Nếu có revision đáng tin cậy, chỉ so sánh các revision trong cùng miền và cùng binding. Không so một sequence của payment với một sequence của kho.

Nếu nguồn không cung cấp thứ tự có thể kiểm chứng, cần quy tắc state machine hoặc truy vấn bổ sung theo hợp đồng. Không lấy timestamp do bên gửi tự khai làm tiêu chí duy nhất.

### 5.4. Mâu thuẫn ngữ nghĩa hoặc dữ liệu

Ví dụ: giao dịch đúng ID nhưng số tiền không đủ cho điều khoản đơn hàng; currency khác; hoặc hai thông điệp cùng revision có giá trị khác nhau.

Cách xử lý: mở case, giữ lại điều kiện liên quan, điều tra nguồn và ánh xạ. Không làm tròn, đổi currency hoặc sửa giá trị đơn hàng để hai bên “khớp nhau” nếu không có nghiệp vụ được cho phép.

### 5.5. Sai phạm vi hoặc dấu hiệu giả mạo

Ví dụ: ID của account A bị dùng cho đơn của account B; payload test xuất hiện trong luồng live; chữ ký hoặc nguồn không hợp lệ.

Cách xử lý: không áp dụng dữ liệu; cách ly và ghi nhận tín hiệu an ninh. Cần kiểm tra tích hợp có bị lộ credential hoặc sai định tuyến không. Không tiếp tục truy vấn hàng loạt ID bên ngoài theo dữ liệu chưa được phép.

### 5.6. Kết quả thao tác chưa xác định

Ví dụ: request thu tiền hoặc hủy giữ hàng bị timeout.

Cách xử lý: giữ `UNKNOWN` ở mức kết quả thao tác, truy vấn theo operation reference hoặc retry bằng đúng cơ chế idempotency đã cam kết. Không tạo một thao tác mới chỉ để thử xem nguồn có trả lời khác không.

Một timeout có thể xảy ra sau khi hệ thống đích đã thực hiện. Amazon Builders' Library phân tích chính tình huống retry có nguy cơ tạo tác dụng phụ trùng và vai trò của định danh yêu cầu để diễn đạt cùng ý định. [Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/).

## 6. Chọn chính sách theo authority, không theo số phiếu

### 6.1. Không dùng “nguồn đến sau luôn thắng”

Thời gian nhận phụ thuộc mạng, hàng đợi và retry. Kẻ tấn công có thể phát lại thông điệp cũ để khiến nó trở thành thông điệp đến sau.

“Lấy mới nhất” chỉ có nghĩa khi đã xác định được thế nào là mới hơn trong hợp đồng của đúng tài nguyên đó.

### 6.2. Không lấy số đông làm bằng chứng

Hai dashboard có thể đọc từ cùng một cache. Một email, một webhook và một màn hình do đối tác cung cấp không nhất thiết là ba nguồn độc lập.

Với quyết định quyền hoặc tác động nghiệp vụ, phải biết nguồn nào có thẩm quyền trên sự thật cần xác nhận. Điểm tin cậy thống kê không tự thay thế một điều kiện bắt buộc như đúng merchant account hoặc đúng currency.

### 6.3. API truy vấn không mặc nhiên thắng webhook

Có thể ưu tiên truy vấn trạng thái hiện tại nếu hợp đồng provider bảo đảm ý nghĩa và độ nhất quán phù hợp. Nếu API là bản sao trễ hoặc dữ liệu không thể so sánh thứ tự, cần giữ bất đồng và tiếp tục xử lý theo chính sách.

Một response HTTP 200 chỉ thể hiện lời gọi được xử lý theo giao thức. Phải đọc đúng trạng thái, đối tượng và điều kiện nghiệp vụ bên trong.

### 6.4. Không để nguồn dự phòng có quyền cao hơn thiết kế

Nếu nhà cung cấp chính ngừng phản hồi, không chuyển sang tin `paid=true` từ trình duyệt để duy trì tỷ lệ hoàn tất đơn.

Có thể cung cấp chế độ suy giảm: hiển thị “đang xác minh”, nhận yêu cầu vào hàng đợi, giữ chỗ trong thời gian có hạn hoặc cho phép người có quyền xem xét. Chế độ này cần được thiết kế theo từng tác động, không phải bỏ các invariant khi hệ thống chậm.

## 7. Ma trận quyết định cho ví dụ đơn hàng

| Tình huống đã xác minh | Hướng xử lý trong ví dụ |
|---|---|
| Client báo thành công, chưa có bằng chứng từ nguồn có thẩm quyền | Chờ xác nhận, chưa phát lệnh giao |
| Quan sát mới hợp lệ khớp điều khoản và binding, không còn hold liên quan | Cập nhật projection và đánh giá lại điều kiện giao |
| Webhook cũ có thể xác định bằng revision hoặc quy tắc nguồn | Lưu bằng chứng, không hạ trạng thái từ quan sát cũ |
| API và webhook khác nhau, chưa xác định thứ tự | Tạm giữ điều kiện liên quan, đối soát có giới hạn |
| Đã thu tiền nhưng số tiền hoặc currency không khớp | Mở case, không sửa điều khoản để khớp |
| Nhà cung cấp xác nhận thu tiền, đơn đã có yêu cầu hủy | Ghi nhận sự thật, tiếp tục luồng hủy và xử lý liên quan; không tự giao |
| Transaction thuộc account hoặc môi trường khác | Không áp dụng, cách ly và điều tra binding |
| Cùng event ID nhưng fingerprint khác | Từ chối xung đột, giữ dấu vết, không áp dụng lần hai |
| Kết quả thao tác bên ngoài chưa xác định | Đối soát operation cũ, không tạo thao tác thay thế tùy tiện |
| Không giải quyết được trước deadline | Chuyển tuyến xử lý được định nghĩa; không tự coi là thành công |
| Case đã giải quyết nhưng có bằng chứng mới hợp lệ | Mở vòng đánh giá mới, không âm thầm sửa quyết định lịch sử |

Đánh giá lại điều kiện giao không đồng nghĩa luôn giao. Các điều kiện về kho, rủi ro, hủy đơn và quyền vẫn phải đồng thời thỏa mãn.

## 8. State machine cho case đối soát

State machine đối soát nên tách khỏi state machine đơn hàng:

~~~mermaid
stateDiagram-v2
    [*] --> OPEN
    OPEN --> CHECKING: Worker nhận việc
    CHECKING --> WAITING_EXTERNAL: Thiếu bằng chứng hoặc nguồn tạm lỗi
    WAITING_EXTERNAL --> CHECKING: Đến lịch và còn ngân sách
    CHECKING --> RESOLVED: Có căn cứ và áp dụng quyết định hợp lệ
    CHECKING --> MANUAL_REVIEW: Không đủ khả năng tự quyết
    WAITING_EXTERNAL --> MANUAL_REVIEW: Hết thời hạn hoặc ngân sách
    MANUAL_REVIEW --> CHECKING: Có bằng chứng mới
    MANUAL_REVIEW --> RESOLVED: Quyết định hợp lệ
    MANUAL_REVIEW --> ESCALATED: Cần tuyến xử lý khác
    ESCALATED --> MANUAL_REVIEW: Tuyến xử lý tiếp nhận
    RESOLVED --> [*]
~~~

`RESOLVED` có nghĩa case đã có kết luận theo policy và bằng chứng được lưu. Kết luận có thể là “không đủ điều kiện giao” hoặc “ánh xạ trước đó sai”, không chỉ là “thanh toán thành công”.

Nếu có bằng chứng mới sau khi giải quyết, tạo case mới hoặc thế hệ case mới liên kết với lịch sử trước đó. Cần quy tắc cụ thể để tránh một webhook trùng liên tục mở lại cùng vấn đề.

Case nên chứa:

~~~text
case_id
tenant_id
order_id
payment_attempt_id
binding_generation
disagreement_type
state
case_version
lease_fence
lease_until
first_detected_at
next_check_at
deadline_at
attempt_count
policy_version
evidence_references
resolution_code
resolution_actor
~~~

Tách `lease_fence` với `binding_generation`:

- Lease fence ngăn worker cũ áp dụng kết quả sau khi đã mất quyền nhận việc.
- Binding generation ngăn kết quả của một liên kết tài nguyên cũ ghi vào liên kết hiện tại.
- Version đơn hàng ngăn kế hoạch đã tính trên trạng thái cũ áp dụng sau một thay đổi cạnh tranh.

Một worker lease hết hạn vẫn có thể đang chạy. Chỉ đặt thời gian hết hạn mà không kiểm tra fence tại nơi ghi chưa ngăn được worker đó.

## 9. Quy trình đối soát chủ động

Một vòng đối soát nên đi theo thứ tự:

1. Đọc case và binding do server quản lý; xác nhận worker có quyền xử lý phạm vi này.
2. Nhận lease có fence trong transaction ngắn.
3. Chọn adapter, account và endpoint từ cấu hình tin cậy.
4. Truy vấn hoặc thu thập bằng chứng ngoài transaction đang khóa đơn hàng.
5. Xác minh và chuẩn hóa kết quả; ghi nhận thông tin không đủ hoặc không hợp lệ đúng loại.
6. Trong transaction ngắn, kiểm tra lại lease, binding, phiên bản và các điều kiện nghiệp vụ hiện tại.
7. Lưu quan sát và áp dụng kế hoạch được policy cho phép; ghi audit và outbox cùng thay đổi.
8. Nếu cần xử lý tiếp, đặt lịch có giới hạn hoặc chuyển tuyến phù hợp.

Không giữ khóa database trong khi chờ API bên ngoài. Lời gọi chậm có thể giữ tài nguyên lâu, tạo điểm nghẽn và khiến việc hủy hoặc thu hồi quyền bị chặn.

### 9.1. Retry có deadline và ngân sách

Cần xác định:

- Timeout cho từng lời gọi và giới hạn tổng thời gian xử lý.
- Backoff có jitter khi phù hợp với hợp đồng nguồn.
- Số lần hoặc ngân sách truy vấn cho mỗi case.
- Hạn mức theo tenant và nguồn.
- Deadline của case và tuyến xử lý khi hết hạn.
- Cách tiếp tục sau crash, bảo trì hoặc hết lease.

Hết retry không có nghĩa thao tác bên ngoài đã thất bại hoặc chưa xảy ra. Nó có nghĩa hệ thống chưa đủ khả năng tự kết luận trong ngân sách đã đặt.

Circuit breaker giúp hạn chế lời gọi đến nguồn đang lỗi; nó không biến dữ liệu cũ hoặc một nguồn kém thẩm quyền thành bằng chứng hợp lệ.

### 9.2. Quản lý quan sát cũ và nguồn không có revision

Khi nguồn có revision, kiểm tra miền revision và contract trước khi dùng để bỏ qua quan sát cũ.

Khi nguồn không có revision có thể so sánh, có thể phải dựa vào sự kiện nghiệp vụ được định danh, truy vấn có bảo đảm thích hợp hoặc giữ case để xem xét. Không tự tạo thứ tự “chắc chắn” bằng `received_at`.

Nếu dùng dữ liệu đã cache, ghi rõ tuổi cache và chính sách cho phép. Với mỗi loại hành động, cần biết bằng chứng được phép cũ đến mức nào và điều gì có thể làm nó mất hiệu lực ngay trước khi thực hiện.

## 10. Minh họa Java: đọc ngoài transaction, áp dụng có kiểm tra lại

Mã dưới đây minh họa cấu trúc, không phải chương trình độc lập. Các class, repository và adapter cần được triển khai theo hợp đồng nguồn thực tế.

### 10.1. Điều phối một vòng đối soát

~~~java
public ReconcileResult reconcile(
        InternalWorkerPrincipal worker,
        UUID tenantId,
        UUID caseId
) {
    // Transaction ngắn: xác nhận phạm vi, cấp lease và fence mới.
    ReconcileTicket ticket = claimService.claim(
            worker, tenantId, caseId
    );

    // Cấu hình này không lấy URL hoặc account tùy ý từ payload.
    ProviderRoute route = routes.resolveTrustedRoute(
            ticket.integrationId(),
            ticket.providerAccountId()
    );

    // Lời gọi mạng nằm ngoài transaction khóa nghiệp vụ.
    ProviderReadResult readResult = providerClient.fetchStatus(
            route, ticket.externalTransactionId()
    );

    VerifiedObservation observation =
            evidenceVerifier.verifyAndNormalize(
                    ticket, route, readResult
            );

    // Bean riêng để cơ chế transaction của ứng dụng có hiệu lực.
    return applyService.apply(worker, ticket, observation);
}
~~~

`VerifiedObservation` là kiểu dữ liệu nội bộ do thành phần xác minh tạo, không phải DTO mà client được tự dựng. Bản ghi này chỉ có nghĩa các bước kiểm tra được khai báo đã đạt; mức độ mới và khả năng giải quyết case vẫn do policy đánh giá.

Timeout hoặc response không thể xác minh không được ép thành `VerifiedObservation` có trạng thái thành công. Luồng xử lý những kết quả đó phải lên lịch lại, giữ `UNKNOWN` hoặc chuyển tuyến theo chính sách.

### 10.2. Áp dụng trên context hiện tại

~~~java
@Transactional
public ReconcileResult apply(
        InternalWorkerPrincipal worker,
        ReconcileTicket ticket,
        VerifiedObservation observation
) {
    // Các đường xử lý liên quan dùng cùng thứ tự khóa đã thống nhất.
    ReconcileAggregate aggregate =
            repository.lockAggregate(
                    ticket.tenantId(),
                    ticket.orderId(),
                    ticket.caseId()
            );

    policy.requireReconcileAuthority(worker, aggregate);

    // Lưu bằng chứng, không đồng nghĩa chấp nhận mọi kết luận từ nó.
    observations.append(observation);

    if (!aggregate.caseState().hasCurrentLease(
            ticket.leaseFence(), clock.instant())) {
        audit.recordLateWorkerIgnored(ticket, observation);
        return ReconcileResult.STALE_WORKER;
    }

    boolean contextChanged =
            aggregate.bindingGeneration()
                    != ticket.bindingGeneration()
            || aggregate.orderVersion()
                    != ticket.expectedOrderVersion();

    if (contextChanged) {
        aggregate.requestReevaluation("CONTEXT_CHANGED");
        repository.saveCaseState(aggregate.caseState());
        audit.recordReevaluationRequired(ticket, observation);
        return ReconcileResult.CONTEXT_CHANGED;
    }

    ResolutionPlan plan = resolutionPolicy.evaluate(
            aggregate.currentFacts(),
            observation,
            aggregate.activeHolds()
    );

    // Chỉ thay đổi các fact và hold mà plan được phép quản lý.
    plan.applyTo(aggregate);

    repository.saveWithExpectedVersions(aggregate);
    audit.appendResolution(ticket, observation, plan);
    outbox.appendResolution(ticket.caseId(), plan);

    return plan.result();
}
~~~

Các điều kiện của ví dụ:

- `lockAggregate` khóa đúng tài nguyên trong tenant, cùng các hàng có thể thay đổi quyền quyết định của case; mọi đường ghi cạnh tranh tuân thủ giao thức khóa tương ứng.
- `observations.append` có cơ chế khử trùng hoặc tham chiếu bằng chứng ổn định. Gọi lại cùng quan sát không tự tạo tác động lần hai.
- `hasCurrentLease` kiểm tra cả fence và hạn lease theo thiết kế thời gian của hệ thống.
- `saveWithExpectedVersions` không được bỏ qua kết quả cập nhật bằng 0; xung đột phải làm rollback hoặc được xử lý rõ.
- Audit và outbox của quyết định được lưu cùng transaction áp dụng.
- `requestReevaluation` tạo trạng thái chờ kiểm tra lại bằng polling hoặc cơ chế lịch bền. Không chỉ gọi một callback trong bộ nhớ rồi coi đã có lịch.

`ResolutionPlan` không được tùy ý đặt đơn thành `READY_TO_SHIP` hoặc xóa toàn bộ hold. Nó chỉ cập nhật sự thật và hold thuộc case, rồi yêu cầu đánh giá lại điều kiện tiếp theo.

Nếu đơn đã chuyển sang payment attempt khác, vẫn giữ và đối soát sự kiện của attempt cũ theo liên kết lịch sử thích hợp. Không chuyển kết quả cũ sang attempt hiện tại, cũng không bỏ qua một tác động đã xảy ra chỉ vì UI không còn hiển thị attempt đó.

## 11. Chặn tranh chấp với hủy đơn và phát lệnh giao

### 11.1. Kết quả API đúng vẫn có thể bị áp dụng sai thời điểm

Tình huống:

~~~text
t1: Worker đọc đơn version 12, chưa có yêu cầu hủy.
t2: Worker gọi provider.
t3: Request hủy cập nhật đơn lên version 13.
t4: Worker nhận bằng chứng giao dịch đã được thực hiện.
t5: Worker dùng context version 12 để cho giao hàng.
~~~

Sai lầm không nhất thiết nằm ở provider. Nó nằm ở việc dùng kế hoạch cũ để vượt quyết định mới.

Worker phải ghi nhận bằng chứng giao dịch, kiểm tra lại đơn hiện tại và xử lý theo luồng hủy phù hợp. Không được tự khôi phục điều kiện giao chỉ vì đã xác nhận thanh toán.

### 11.2. Hold cần có nguồn gốc riêng

Ví dụ:

~~~text
hold-1: EXTERNAL_DISAGREEMENT, owner_case = CASE-8
hold-2: RISK_REVIEW, owner_case = RISK-3
hold-3: CANCELLATION_PENDING, owner_operation = CANCEL-5
~~~

Giải quyết CASE-8 chỉ được giải phóng hold-1 nếu policy cho phép. Không dùng `order.onHold = false` để xóa cả ba.

Khi một hold chặn hành động, nơi ra quyết định phải đọc trạng thái hold hiện tại trong ranh giới nhất quán phù hợp. Cache cũ không được tự cấp quyền phát lệnh.

### 11.3. Phát lệnh giao cũng cần idempotency

Có thể dùng unique constraint cho ý định phát lệnh:

~~~sql
CREATE TABLE fulfillment_intent (
    intent_id             UUID PRIMARY KEY,
    tenant_id             UUID NOT NULL,
    order_id              UUID NOT NULL,
    action                VARCHAR(40) NOT NULL,
    action_generation     BIGINT NOT NULL,
    decision_epoch        BIGINT NOT NULL,
    state                 VARCHAR(24) NOT NULL,
    UNIQUE (
        tenant_id, order_id, action, action_generation
    )
);
~~~

`action_generation` phải được server quản lý theo định nghĩa một lần thực hiện hợp lệ. Không cho client tăng generation để né unique constraint.

Constraint này ngăn hai transaction tạo cùng ý định cục bộ. Nó không tự bảo đảm kho ngoài chỉ thực hiện một lần. Khi giao tiếp ra ngoài, cần định danh lệnh ổn định và cơ chế idempotency tương ứng.

Giữa lúc đưa vào outbox và lúc kho thực hiện, điều kiện có thể thay đổi. Cần xác định rõ điểm hủy còn được chấp nhận và cách consumer kiểm tra `decision_epoch` hoặc quyền thực thi trước điểm khó đảo ngược. Một khóa database tại service đơn hàng không tự khóa được hành động ở service kho.

## 12. Retry thao tác và tác động bù trừ

### 12.1. Giữ nguyên ý định khi retry

Nếu request bên ngoài timeout, lưu và tái sử dụng định danh operation hoặc idempotency key của đúng ý định đó. Không tạo key mới mỗi lần thử.

Idempotency có hợp đồng riêng theo nhà cung cấp và phiên bản API. Ví dụ, Stripe mô tả khác biệt giữa API v1 và v2; ở API v1, kết quả đã lưu có thể bao gồm cả lỗi 500 và việc dùng lại key với tham số khác bị kiểm tra. Không nên mặc định mọi API hoạt động giống nhau. [Stripe — Idempotent requests](https://docs.stripe.com/api/idempotent_requests).

Trước khi retry cần biết:

- Thao tác nào hỗ trợ idempotency.
- Phạm vi duy nhất của key.
- Key được giữ bao lâu.
- Tham số nào phải giữ nguyên.
- Cách truy vấn operation hoặc kết quả đã có.
- Điều gì xảy ra khi retry đến muộn sau khi tài nguyên thay đổi.

Khi hết thời gian lưu key, không mặc định retry vẫn an toàn. Có thể cần bằng chứng bền hoặc đối soát theo định danh nghiệp vụ.

### 12.2. Không coi bù trừ là rollback database

Nếu đã thu tiền nhưng đơn không thể hoàn tất, luồng xử lý có thể cần hoàn tiền hoặc nghiệp vụ khác theo chính sách sản phẩm. Đó là một operation mới, có quyền, điều kiện, định danh và trạng thái riêng.

Không thực hiện bù trừ chỉ vì không thấy response của thao tác gốc. Nếu chưa biết thao tác gốc xảy ra chưa, bù trừ không có điều kiện có thể tạo thêm sai lệch.

Luồng bù trừ cần:

- Liên kết tác động gốc đã được xác định.
- Kiểm tra tổng lượng hoặc giá trị còn được phép bù.
- Chống trùng và quản lý cạnh tranh.
- Trạng thái chờ khi kết quả bù trừ chưa rõ.
- Audit và tuyến xử lý khi bù trừ không thành công.

Một cuộc gọi bù trừ thành công cũng không xóa lịch sử tác động ban đầu.

## 13. Quyết định thủ công vẫn phải giữ invariant

Khi tự động đối soát không đủ căn cứ, người vận hành cần một giao diện có bằng chứng và hành động giới hạn, thay vì nút “mark paid” chung.

Thông tin cần hiển thị:

- Đơn, tenant, account, payment attempt và generation.
- Các quan sát cùng nguồn, thời điểm và kết quả xác minh.
- Các khác biệt về amount, currency, trạng thái hoặc binding.
- Những tác động đã biết, đang chờ và chưa xác định.
- Policy áp dụng và các hành động hiện được cho phép.

Một quyết định thủ công có thể là:

- Xác nhận thông tin sai ánh xạ và chuyển điều tra.
- Chấp nhận bằng chứng phù hợp từ nguồn có thẩm quyền.
- Tiếp tục giữ hoặc kết luận không cho thực hiện bước tiếp theo.
- Khởi tạo một nghiệp vụ bù trừ có điều kiện riêng.

Nếu chính sách yêu cầu phê duyệt bổ sung hoặc tách nhiệm vụ, phải ràng buộc phê duyệt với đúng bằng chứng và phiên bản case. Case thay đổi sau khi duyệt phải được kiểm tra lại trước khi áp dụng.

Không cho phép người xử lý sửa trực tiếp số tiền đã được chấp thuận để khớp response. Việc sửa điều khoản là nghiệp vụ riêng và có thể cần sự chấp thuận khác.

Quyền xử lý case trong T1 không mở rộng sang T2. Tài khoản nội bộ vẫn cần phân quyền theo đối tượng và lưu dấu vết.

## 14. Audit và vận hành quy trình bất đồng

Mỗi quyết định nên có:

~~~text
case_id và case_generation
tenant_id, order_id, payment_attempt_id
provider và provider_account_reference
binding_generation
evidence_references
classification và reason_code
policy_version
previous_case_state và new_case_state
order_version_before và order_version_after nếu có
worker_identity hoặc manual_actor
lease_fence
decision và những hold được thêm hoặc gỡ
operation_id và effect_reference nếu phát sinh tác động
~~~

Đừng ghi token, secret ký webhook hoặc toàn bộ dữ liệu nhạy cảm chỉ để tiện đối soát. Tham chiếu bằng chứng phải có kiểm soát truy cập.

Các chỉ số nên theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Số case đang mở và tuổi case cũ nhất | Tồn đọng và nguy cơ không giải quyết đúng hạn |
| Số case theo loại bất đồng và nguồn | Lỗi schema, account hoặc contract đang tập trung ở đâu |
| Tỷ lệ chuyển manual review | Mức độ quy trình tự động chưa đủ |
| Số kết quả bị bỏ do fence hoặc binding cũ | Cạnh tranh, lease hoặc lịch xử lý có vấn đề |
| Retry, timeout và ngân sách truy vấn còn lại | Nguy cơ tạo tải hoặc kéo dài tình trạng chưa rõ |
| Số operation có kết quả UNKNOWN | Nhu cầu đối soát tác động thật |
| Số intent hoặc tác động bị chặn trùng | Hoạt động của cơ chế chống lặp |
| Số quyết định thủ công và thay đổi policy | Phát hiện đường vòng hoặc cấu hình quá rộng |

Cảnh báo và deadline phải có người hoặc tuyến xử lý chịu trách nhiệm. Hàng đợi dead-letter mà không có cơ chế xem xét chỉ chuyển nơi tồn đọng, không giải quyết bất đồng.

Không log lại “resolved” mỗi lần nhận webhook trùng. Cần phân biệt một event vận chuyển được nhận lại với một kết luận mới của case.

## 15. Những cách sửa nhanh dễ tạo lỗ hổng

| Cách làm | Vấn đề | Hướng thiết kế |
|---|---|---|
| Lấy response đến sau cùng | Replay và độ trễ làm đảo quyết định | Kiểm tra authority, scope, revision và state machine |
| Lấy đa số nguồn | Nguồn có thể không độc lập hoặc không có thẩm quyền | Gán trách nhiệm theo sự thật cần xác nhận |
| Gặp lỗi thì tin client | Tạo đường bỏ qua xác nhận server | Giữ trạng thái chờ hoặc chế độ suy giảm đã định nghĩa |
| Timeout thì đánh dấu chưa thực hiện | Có thể thực hiện lại một tác động đã xảy ra | UNKNOWN, truy vấn operation và idempotency |
| Provider success thì đặt đơn success | Bỏ qua hủy đơn, kho, rủi ro và amount | Ghi sự thật riêng, đánh giá lại toàn bộ điều kiện |
| Xóa mọi hold khi một case xong | Vượt các chặn nghiệp vụ độc lập | Hold có nguồn gốc và quyền giải phóng riêng |
| Gọi provider trong transaction dài | Giữ khóa, chặn hủy, tạo nghẽn | Đọc ngoài transaction, kiểm tra lại khi ghi |
| Worker lấy lease là đủ | Worker mất lease vẫn có thể ghi | Fence được kiểm tra tại nơi áp dụng |
| Retry bằng key mới | Tạo operation mới | Giữ định danh cho cùng ý định |
| Force success để đóng case | Che mất bất đồng và vượt invariant | Quyết định giới hạn, bằng chứng và phê duyệt phù hợp |
| Sửa lịch sử để hai bên khớp | Mất dấu nguồn và nguyên nhân | Lưu quan sát, projection và quyết định riêng |

## 16. Ma trận kiểm thử tình huống tấn công logic

Đây là đặc tả các ca cần xây dựng khi triển khai, không phải kết quả kiểm thử của một hệ thống cụ thể.

| Tình huống | Kết quả bắt buộc |
|---|---|
| Client tự khai success | Không tự xác nhận điều kiện thanh toán |
| Webhook hợp lệ nhưng account khác | Không gắn vào đơn; có dấu vết sai phạm vi |
| Webhook test vào luồng live | Không áp dụng tác động live |
| Giao dịch đúng ID nhưng amount hoặc currency sai | Mở case và giữ điều kiện liên quan; không sửa giá trị đơn |
| Pending cũ đến sau xác nhận mới có thứ tự kiểm chứng | Không hạ projection từ quan sát cũ |
| Hai event cùng ID nhưng payload khác | Không áp dụng lần hai; ghi xung đột |
| API vừa truy vấn trả dữ liệu trễ | Không coi thời gian nhận là bằng chứng mới hơn tuyệt đối |
| Không có revision có thể so sánh | Không tự tạo thứ tự tin cậy bằng timestamp client |
| Nguồn ngoài xác nhận nhưng đơn đã yêu cầu hủy | Ghi sự thật; không tự cho giao hàng |
| Giải quyết case thanh toán khi còn hold rủi ro | Chỉ gỡ hold của case đó; điều kiện giao vẫn bị chặn |
| Worker hết lease rồi trả kết quả | Fence cũ không được áp dụng thay đổi quyết định |
| Hai worker cùng xử lý một case | Không phát sinh hai intent hoặc tác động trùng |
| Binding chuyển sang payment attempt khác giữa lúc gọi API | Kết quả cũ không ghi vào attempt mới; sự kiện cũ vẫn được lưu và xử lý đúng phạm vi |
| Transaction ghi quyết định bị lỗi | Không có projection, audit thành công hoặc outbox nửa chừng |
| Commit xong nhưng response bị mất | Retry không tạo tác động mới |
| Provider timeout sau khi đã thực hiện | Không đánh dấu chắc chắn thất bại hoặc tạo thao tác thay thế tùy tiện |
| Retry đến sau khi key hết thời gian giữ | Tuân thủ chính sách đối soát và bảo vệ nghiệp vụ bổ sung |
| Hết ngân sách retry | Chuyển tuyến rõ; không tự resolved success |
| Response chứa status mới chưa hỗ trợ | Không mặc định thành công; giữ loại unknown hoặc cách ly theo policy |
| Payload chứa URL xác minh tùy ý | Không gọi URL ngoài cấu hình tin cậy |
| Người xử lý thủ công truy cập case tenant khác | Bị từ chối |
| Bằng chứng đổi sau khi được duyệt thủ công | Không áp dụng phê duyệt cũ cho nội dung mới |
| Bù trừ được retry hoặc hai worker cùng khởi tạo | Không vượt số lượng hoặc giá trị được phép bù |
| Một nguồn gửi nhiều sự kiện mâu thuẫn liên tục | Có hạn mức và kiểm soát tải; không làm mất các chặn bắt buộc |

Các ca cạnh tranh cần dùng ít nhất hai transaction thực và điều khiển thứ tự bằng barrier hoặc latch. Đặc biệt cần kiểm tra lúc hủy đơn commit giữa lần đọc snapshot và lần áp dụng kết quả.

Dùng stub hoặc sandbox provider để mô phỏng response trễ, duplicate, timeout sau tác động và schema không hỗ trợ. Kiểm tra cả dữ liệu cuối, intent, outbox, hold và audit; HTTP status đúng chưa đủ.

## 17. Những quyết định cần chốt trước khi triển khai

1. Mỗi sự thật có nguồn nào chịu trách nhiệm và điều kiện nào làm bằng chứng hợp lệ?
2. Các thông tin đang so sánh có cùng object, account, attempt và generation không?
3. Hợp đồng nguồn bảo đảm gì về thứ tự, độ nhất quán và idempotency?
4. Những tác động nào phải chờ khi chưa đủ bằng chứng, và tính năng nào vẫn được tiếp tục?
5. Case có deadline, ngân sách truy vấn và tuyến xử lý nào?
6. Kết quả đọc ngoài transaction được kiểm tra lại bằng version, binding và fence ra sao?
7. Một quyết định có thể thêm hoặc gỡ những hold nào?
8. Ai được xử lý thủ công, bằng chứng nào phải giữ và phê duyệt gắn với phiên bản nào?
9. Sau timeout hoặc crash, hệ thống đối soát tác động đã xảy ra bằng định danh nào?

Với ví dụ đơn hàng, xác nhận từ provider chỉ giải quyết sự thật của đúng giao dịch đã được liên kết. Quyền phát lệnh giao vẫn là quyết định của nền tảng trên trạng thái hiện tại, đầy đủ điều kiện và không có bất đồng liên quan chưa được xử lý.
