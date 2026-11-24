# Command replay scenario

## 1. Mục tiêu và phạm vi

Trong chương **Replay Protection** của module bảo mật logic nghiệp vụ, command replay là tình huống một lệnh thay đổi trạng thái được gửi hoặc xử lý lại, khiến hệ thống có nguy cơ thực hiện thêm một tác dụng nghiệp vụ ngoài ý định ban đầu.

“Command” trong bài là lệnh như hoàn tiền, duyệt hồ sơ, chuyển điểm hoặc xác nhận đơn hàng; không phải lệnh hệ điều hành.

Sau bài học, bạn có thể:

- Mô tả đường đi của một lệnh bị phát lại, từ client đến cơ sở dữ liệu và dịch vụ bên ngoài.
- Phân biệt retry hợp lệ, phát lại có chủ đích và một ý định nghiệp vụ mới.
- Xác định danh tính lệnh, phạm vi chống trùng và bất biến cần giữ.
- Giải thích vì sao xác thực, chữ ký, timestamp hay idempotency key riêng lẻ chưa đủ.
- Chọn kết quả xử lý phù hợp khi lệnh đang chạy, đã hoàn tất hoặc chưa rõ kết quả.
- Viết các tình huống kiểm thử để phát hiện thực thi trùng và vượt quyền khi phát lại.

Ví dụ xuyên suốt là hoàn toàn bộ tiền của một giao dịch đã thanh toán. Những quy tắc “chỉ một lần” trong ví dụ thuộc hợp đồng cụ thể này; không áp dụng máy móc cho nghiệp vụ cho phép nhiều lần hoàn một phần.

## 2. Kịch bản: một lệnh hoàn tiền được nhận hai lần

### 2.1. Bối cảnh nghiệp vụ

Hệ thống có các dữ kiện do server quản lý:

| Thành phần | Giá trị minh họa |
|---|---|
| Tenant | T-A |
| Giao dịch thanh toán | CAP-981 |
| Số tiền đã thu | 1.000.000 VND |
| Hồ sơ hoàn tiền | RI-42 |
| Trạng thái hồ sơ | APPROVED |
| Phiên bản được duyệt | 7 |
| Số tiền được duyệt | 1.000.000 VND |
| Nơi nhận tiền hoàn | Phương thức thanh toán gốc |

Nhân viên có quyền gửi lệnh hoàn tiền dựa trên hồ sơ RI-42. Một command hợp lệ cần gắn với đúng tenant, giao dịch, hồ sơ phê duyệt và phiên bản đã được duyệt.

Yêu cầu minh họa:

~~~http
POST /api/refund-intents/RI-42/commands HTTP/1.1
Host: payments.example
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: 8a914a15-ff5f-4ad0-86ef-0ab454bf5bef

{
  "type": "EXECUTE_FULL_REFUND",
  "expectedVersion": 7,
  "amount": 1000000,
  "currency": "VND"
}
~~~

Tenant và principal phải được suy ra từ ngữ cảnh xác thực đáng tin cậy và kiểm tra quyền; không lấy một tenant_id tùy ý trong body làm căn cứ thẩm quyền.

amount và currency là dữ liệu client đề nghị hoặc xác nhận. Server phải đối chiếu chúng với hồ sơ được duyệt và giao dịch gốc, không dùng chúng để tự tạo một quyền hoàn tiền mới.

### 2.2. Diễn biến khi phản hồi bị mất

1. Client gửi command C1.
2. Server kiểm tra người gọi và hồ sơ phê duyệt.
3. Dịch vụ thanh toán thực hiện hoàn tiền.
4. Kết nối bị ngắt trước khi client nhận được phản hồi.
5. Client không biết thao tác đã thành công hay chưa nên gửi lại C1.
6. Server có lỗi coi lần nhận thứ hai là một lệnh mới và gọi hoàn tiền lần nữa.

Lỗi có thể xảy ra dù lần gửi lại không có ý đồ xấu. Một người gọi có chủ đích cũng có thể lưu yêu cầu hợp lệ của chính mình rồi gửi lại nhiều lần, hoặc thay idempotency key để thử vượt qua lớp chống trùng.

Không cần giả định kẻ tấn công đã phá TLS. Người dùng có quyền gửi một yêu cầu vốn đã có thể biết nội dung yêu cầu đó.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Ứng dụng
    participant P as Dịch vụ thanh toán
    C->>A: Gửi command C1
    A->>P: Yêu cầu hoàn tiền
    P-->>A: Đã hoàn tiền
    A--xC: Phản hồi bị mất
    C->>A: Gửi lại command C1
    Note over A: Nếu không nhận diện command cũ
    A->>P: Yêu cầu hoàn tiền mới
    Note over A,P: Nguy cơ tác dụng nghiệp vụ bị thực hiện thêm
~~~

Một số dịch vụ thanh toán có thể tự chặn vượt số tiền đã thu. Điều đó không đủ để kết luận ứng dụng an toàn: sổ cái nội bộ, điểm thưởng, email hay trạng thái hồ sơ vẫn có thể bị cập nhật trùng. Trong nghiệp vụ khác, hệ thống bên ngoài cũng có thể cho phép nhiều thao tác tương tự.

### 2.3. Điều gì phải được bảo vệ?

Với hợp đồng của ví dụ:

~~~text
Mỗi hồ sơ hoàn tiền được duyệt -> nhiều nhất một operation hoàn tiền logic.

Mỗi giao dịch thanh toán -> nhiều nhất một lần hoàn toàn bộ thành công.

Số tiền, tiền tệ và nơi nhận -> đúng phạm vi được phê duyệt.

Gửi lại cùng command -> không tạo thêm tác dụng nghiệp vụ.

Nhận lại cùng xác nhận thanh toán -> không ghi sổ cái thêm lần nữa.
~~~

“Operation logic” là danh tính ổn định của một ý định được hệ thống chấp nhận. Một operation có thể cần nhiều lần thử gửi mạng và nhiều lần đối soát; số attempt không phải số lần nghiệp vụ được phép áp dụng.

## 3. Replay, retry và lệnh mới khác nhau như thế nào?

### 3.1. Retry mô tả lý do, replay mô tả việc lặp lại

Retry thường là nỗ lực phục hồi sau timeout, mất mạng hoặc lỗi tạm thời. Replay mô tả việc một thông điệp hoặc command được đưa vào xử lý lại, có thể hợp lệ hoặc có chủ đích lạm dụng.

Server thường không thể suy ra ý đồ của người gọi từ hai yêu cầu giống nhau. Hợp đồng nên quy định kết quả dựa trên danh tính lệnh và trạng thái đã lưu, thay vì cố đoán người gọi vô tình hay cố ý.

### 3.2. Cùng nội dung chưa chắc là cùng ý định

Hai lệnh chuyển 100 điểm cho cùng một người có thể là:

- Một lần chuyển bị gửi lại vì timeout.
- Hai lần chuyển độc lập mà người dùng thực sự muốn thực hiện.

Nếu chỉ so sánh body, hệ thống có thể gộp nhầm hai lệnh hợp lệ. Nếu chỉ coi mỗi lần HTTP đến là một lệnh mới, hệ thống có thể nhân đôi một lần chuyển.

Cần có cách biểu đạt danh tính ý định, chẳng hạn idempotency key trong một phạm vi đã định nghĩa hoặc một command ID gắn với hồ sơ nghiệp vụ.

### 3.3. Các biến thể cần phân biệt

| Lần gửi tiếp theo | Ý nghĩa cần xem xét | Cách xử lý trong hợp đồng minh họa |
|---|---|---|
| Cùng key, cùng nội dung, cùng phạm vi | Cùng command được gửi lại | Trả lại receipt cũ hoặc trạng thái đang xử lý |
| Cùng key, đổi số tiền | Tái sử dụng danh tính lệnh cho nội dung khác | Báo xung đột, không thực thi nội dung mới |
| Key mới, vẫn dùng RI-42 đã được nhận xử lý | Yêu cầu mới trỏ tới ý định đã tiêu thụ | Không tạo operation hoàn tiền thứ hai |
| Key mới, hồ sơ mới cho cùng CAP-981 đã hoàn toàn bộ | Vượt qua lớp chống trùng bằng danh tính mới | Bất biến hoàn toàn bộ phải chặn |
| Cùng chuỗi key nhưng tenant khác | Hai phạm vi độc lập | Không dùng chung receipt hay làm lộ kết quả |
| Cùng command, access token đã hết hạn | Lần gọi chưa được xác thực hợp lệ | Không bỏ qua xác thực vì command đã tồn tại |
| Message được broker giao lại | Cùng ý định được consumer nhận thêm lần nữa | Không áp dụng thêm tác dụng nghiệp vụ |

Một key mới có thể làm một yêu cầu trở thành “mới” ở lớp API, nhưng không làm hồ sơ đã tiêu thụ trở thành hồ sơ chưa sử dụng.

## 4. Bốn loại danh tính không nên trộn lẫn

### 4.1. Request ID hoặc attempt ID

Nhận diện một lần truyền hay một lần tiếp nhận. Dùng để theo dõi log, độ trễ và lỗi.

Hai lần retry có thể có hai request ID khác nhau dù cùng một command.

### 4.2. Idempotency key

Cho biết người gọi muốn những lần gửi nào được xem là cùng một command trong phạm vi hợp đồng API.

Một phạm vi minh họa là:

~~~text
scope = (tenant_id, caller_scope, command_type)
lookup = (scope, idempotency_key)
~~~

caller_scope có thể là principal hoặc danh tính ứng dụng tích hợp ổn định. Không nên dùng nguyên access token làm scope vì token có thể thay đổi khi refresh.

Đây là lựa chọn thiết kế, không phải quy tắc duy nhất. Nếu nhiều nhân viên có thể tiếp tục cùng một hồ sơ, bản thân hồ sơ vẫn cần một danh tính nghiệp vụ chung để ngăn hai người tạo hai operation.

### 4.3. Business intent ID hoặc command ID

Nhận diện ý định nghiệp vụ được duyệt, chẳng hạn RI-42 và lệnh EXECUTE_FULL_REFUND của hồ sơ đó.

ID do server cấp không tự tạo bảo mật. Server vẫn phải kiểm tra tenant, quyền theo đối tượng, trạng thái và quan hệ giữa ID với dữ liệu đã được phê duyệt.

### 4.4. Operation ID và message ID

Operation ID nhận diện công việc đã được hệ thống chấp nhận, ví dụ RF-501.

Message ID nhận diện một thông điệp gửi đến worker. Một operation có thể sinh nhiều loại message và có nhiều attempt giao nhận.

Không dùng message ID làm căn cứ duy nhất cho bất biến nghiệp vụ: cùng một operation có thể bị đóng gói thành một message mới với ID khác.

Bảng liên hệ:

~~~text
Business intent RI-42
  -> command EXECUTE_FULL_REFUND
  -> operation RF-501
     -> HTTP attempt REQ-1
     -> HTTP retry REQ-2
     -> outbox event EVT-1
     -> delivery attempt DEL-1
     -> delivery retry DEL-2
~~~

Số request, số message và số tác dụng nghiệp vụ thành công là ba đại lượng khác nhau.

## 5. Idempotency có ý nghĩa gì trong kịch bản này?

Idempotency yêu cầu việc lặp lại cùng thao tác không làm thay đổi tác dụng dự định so với thực hiện một lần. Đây cũng là trọng tâm của định nghĩa phương thức idempotent trong [RFC 9110, mục 9.2.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2).

Có thể biểu diễn trực giác:

~~~text
apply(C, apply(C, S)) tương đương apply(C, S)
đối với tác dụng nghiệp vụ được hợp đồng của C quy định.
~~~

Log của hai lần tiếp nhận có thể khác nhau. Idempotency không đòi mọi quan sát của hệ thống đều giống hệt nhau, mà cần xác định rõ tác dụng nào được phép xuất hiện một lần.

Trong ví dụ hoàn tiền:

- Có thể có hai access log vì có hai lần gửi.
- Có thể có hai bản ghi audit cho hai attempt.
- Chỉ có một operation hoàn tiền logic cho hồ sơ đã duyệt.
- Không có thêm khoản hoàn tiền hoặc bút toán chỉ vì request được phát lại.

Không thể thêm header Idempotency-Key rồi mặc định server đã thực thi đúng hợp đồng đó. Phía server phải thực sự ràng buộc key với nội dung và xử lý tranh chấp nguyên tử.

Không được dựa vào tên HTTP method để đoán độ an toàn của một endpoint viết sai. Ví dụ, đổi đường dẫn hoàn tiền thành PUT không tự loại bỏ việc gọi dịch vụ thanh toán hai lần.

## 6. Vì sao các biện pháp quen thuộc chưa đủ?

| Biện pháp | Giá trị thực tế | Phần còn thiếu với command replay |
|---|---|---|
| HTTPS/TLS | Bảo vệ kênh truyền giữa các đầu cuối TLS | Người gửi hợp lệ vẫn có thể gửi lại lệnh |
| Access token | Xác thực người gọi và hỗ trợ quyết định quyền | Cùng người gọi có thể lặp lại thao tác |
| Chữ ký hoặc HMAC | Kiểm tra tính xác thực và toàn vẹn của phần được ký | Một thông điệp cũ hợp lệ vẫn có thể bị phát lại |
| Timestamp | Giới hạn độ cũ được chấp nhận | Trong cửa sổ hợp lệ vẫn có thể gửi nhiều lần |
| Nonce dùng một lần | Nhận diện một thông điệp đã dùng | Retry ký lại với nonce mới vẫn có thể cùng một ý định |
| Idempotency key | Nhận diện command lặp trong một phạm vi | Key mới không được phép vượt bất biến nghiệp vụ |
| Rate limit | Hạn chế tần suất | Hai request vẫn đủ để tạo lỗi nếu chỉ được phép một |
| Khóa trong bộ nhớ ứng dụng | Điều phối trong phạm vi tiến trình | Không tự phối hợp được nhiều instance hay sau restart |
| Vô hiệu hóa nút trên UI | Giảm gửi nhầm từ giao diện | Không ràng buộc lời gọi trực tiếp hoặc retry từ hạ tầng |

Các lớp có thể phối hợp với nhau. Ví dụ nonce bảo vệ thông điệp có chữ ký, idempotency key bảo vệ việc retry một command, còn trạng thái hồ sơ và constraint bảo vệ quyền tạo operation.

Không gộp tất cả vào một biến “request đã hợp lệ”. Tính hợp lệ của người gọi, tính mới của thông điệp và quyền áp dụng một ý định là các quyết định riêng.

## 7. Mô tả một hợp đồng xử lý rõ ràng

Thiết kế minh họa sau dùng API bất đồng bộ.

### 7.1. Lần tiếp nhận đầu tiên

Khi command được chấp nhận, server tạo operation RF-501 và trả:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /api/refund-operations/RF-501

{
  "operationId": "RF-501",
  "intentId": "RI-42",
  "acceptance": "ACCEPTED"
}
~~~

202 có nghĩa là đã nhận xử lý theo hợp đồng; không được diễn giải thành tiền đã được hoàn thành công.

Thông tin tiến độ hiện tại được truy vấn qua tài nguyên operation với kiểm tra quyền tương ứng.

### 7.2. Cùng key và cùng command

Sau khi xác thực và kiểm tra quyền đọc kết quả, server trả lại receipt chấp nhận đã lưu, vẫn tham chiếu RF-501. Không tạo RF-502 và không tạo thêm một ý định gọi nhà cung cấp.

Trong hợp đồng này, receipt là kết quả tại lúc chấp nhận. Nếu RF-501 sau đó đã hoàn tất, việc phát lại receipt 202 không phải tuyên bố trạng thái hiện tại vẫn đang chờ. Client dùng endpoint trạng thái để biết kết quả mới nhất.

Một API khác có thể trả trạng thái hiện tại. Cần chọn một hợp đồng và kiểm thử đúng hợp đồng đó.

### 7.3. Cùng key nhưng nội dung khác

Server trả lỗi xung đột có mã ứng dụng như IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_COMMAND. Không thay nội dung đã gắn với key.

409 là một lựa chọn cho API minh họa, không phải mã bắt buộc cho mọi hệ thống.

### 7.4. Command đang được transaction khác tiếp nhận

Có thể chờ trong một khoảng có giới hạn rồi trả receipt đã commit, hoặc trả trạng thái đang xử lý để client thử lại theo chính sách.

Không được dùng khoảng chờ hết hạn làm lý do cho phép một transaction thứ hai tự thực hiện cùng command.

Cũng không được kết luận “đã thành công” chỉ vì thấy một dấu giữ chỗ chưa có kết quả nghiệp vụ.

### 7.5. Key mới nhưng hồ sơ đã được tiêu thụ

Trong ví dụ, server từ chối tạo operation mới cho RI-42 và có thể trả mã INTENT_ALREADY_SUBMITTED.

Chỉ cung cấp liên kết tới operation cũ nếu người gọi có quyền đọc. Đổi key không làm thay đổi phê duyệt hoặc trạng thái của hồ sơ.

## 8. Ràng buộc key với đúng nội dung và quyền

### 8.1. Fingerprint của command

Một receipt cần lưu fingerprint của ý nghĩa command, không chỉ lưu key.

Dữ liệu có thể cần đưa vào fingerprint:

~~~text
fingerprint_schema_version
tenant_id
caller_scope
command_type
target_intent_id
capture_id
approved_snapshot_id hoặc approved_version
expected_version
amount theo đơn vị tiền tệ đã định nghĩa
currency
refund_destination_reference
~~~

Danh sách chính xác phụ thuộc API. Điểm quan trọng là những thuộc tính làm thay đổi đối tượng, số tiền, nơi nhận hoặc phạm vi phê duyệt phải được ràng buộc.

Một fingerprint dạng băm không phải bằng chứng người gọi có quyền. Nó chỉ hỗ trợ so sánh danh tính nội dung theo một hợp đồng đã xác định.

### 8.2. Chuẩn hóa có chủ đích

Không nối các trường bằng một dấu phân cách tùy ý rồi cho rằng kết quả luôn không mơ hồ. Nên dùng định dạng chuẩn hóa có schema và quy tắc rõ ràng:

- Cùng cách biểu diễn ID và enum.
- Quy định chính xác trường vắng mặt khác null hay không.
- Quy định đơn vị và kiểu biểu diễn số tiền; tránh số thực nhị phân cho số tiền.
- Xác định các trường mặc định trước khi tính fingerprint.
- Giữ phiên bản thuật toán chuẩn hóa khi nâng cấp API.

Hash nguyên byte JSON phân biệt cả thay đổi khoảng trắng hoặc thứ tự thuộc tính. Điều đó có thể dùng được nếu API định nghĩa command theo byte, nhưng không tự tương đương với so sánh ý nghĩa nghiệp vụ.

Token, trace ID, thời điểm gửi lại và nonce truyền tải thường thay đổi giữa các attempt. Không đưa chúng vào fingerprint ý định nếu hợp đồng yêu cầu retry vẫn nhận diện cùng command.

### 8.3. Xác thực và quyền phải được xét cả khi phát lại

Một lỗi nguy hiểm là:

~~~java
// Cách làm sai: trả cache trước khi xác thực và kiểm tra phạm vi.
Receipt receipt = receipts.findByKey(request.idempotencyKey());
if (receipt != null) {
    return receipt.response();
}
authenticateAndAuthorize(request);
~~~

Người biết hoặc đoán được key có thể nhận kết quả của người khác nếu key lookup thiếu phạm vi.

Luồng đúng cần xác thực người gọi, xác định tenant và caller scope đáng tin cậy, rồi chỉ trả kết quả mà người gọi được quyền đọc.

Phân biệt hai quyền:

- **Thực thi lệnh mới:** cần quyền và điều kiện nghiệp vụ tại thời điểm thao tác có hiệu lực.
- **Đọc lại kết quả cũ:** cần quyền đọc operation hoặc receipt theo chính sách hiện tại.

Thu hồi quyền gửi lệnh mới không tự động quyết định người dùng còn được đọc lịch sử của chính họ hay không; đó là chính sách cần viết rõ. Dù chọn chính sách nào, replay không được bỏ qua nó.

Với command đã hoàn tất, không kiểm tra lại expectedVersion cũ như thể đang bắt đầu một command mới rồi vô tình từ chối mọi retry. Trước hết xác định đó có đúng command cũ hay không, sau đó áp dụng quyền đọc kết quả. Với command mới, phải kiểm tra phiên bản và trạng thái hiện tại.

## 9. Giữ quyết định chống trùng và thay đổi nghiệp vụ trong cùng transaction

### 9.1. Mẫu check-then-act có lỗi

~~~java
if (!receipts.exists(scope, key)) {
    PaymentResult result = paymentProvider.refund(newRefundRequest());
    receipts.save(scope, key, result);
    return result;
}

return receipts.load(scope, key);
~~~

Hai request có thể cùng thấy “chưa tồn tại” rồi cùng gọi hoàn tiền. Ngoài ra, ứng dụng có thể chết sau khi dịch vụ thanh toán thành công nhưng trước khi lưu receipt.

Thêm synchronized cho đoạn mã không giải quyết được đầy đủ khi có nhiều instance, và vẫn không tạo được transaction nguyên tử giữa database và nhà cung cấp.

### 9.2. Các ràng buộc ở mức dữ liệu

Một thiết kế có thể dùng các ràng buộc sau:

| Dữ liệu | Ràng buộc minh họa | Điều được bảo vệ |
|---|---|---|
| Command receipt | Unique theo tenant, caller scope, command type, key | Một key không đồng thời nhận hai nội dung trong cùng phạm vi |
| Refund operation | Unique theo tenant và refund intent | Một hồ sơ không tạo nhiều operation |
| Full-refund reservation | Unique theo tenant và capture | Hai hồ sơ khác nhau không cùng tiêu thụ quyền hoàn toàn bộ |
| Ledger application | Unique theo tenant, operation và loại bút toán cụ thể | Xác nhận trùng không ghi cùng tác dụng thêm lần nữa |
| Outbox khởi tạo | Unique theo tenant, operation và loại REFUND_REQUESTED | Không tạo trùng ý định khởi động cho cùng operation |

Ràng buộc hoàn toàn bộ phải nằm ở nguồn dữ liệu có thẩm quyền và bao phủ cả operation đang xử lý. Chỉ đếm các refund thành công rồi cho phép hai refund mới cùng chạy vẫn tạo cửa sổ vượt bất biến.

Nếu operation chưa rõ kết quả, không tự giải phóng reservation. Chỉ xem xét giải phóng khi có bằng chứng đủ mạnh rằng tác dụng bên ngoài chưa xảy ra và chính sách cho phép.

### 9.3. Transaction tiếp nhận command

Luồng sau là mã giả về ranh giới xử lý, không phải triển khai hoàn chỉnh:

~~~text
Xác thực người gọi.
Kiểm tra cấu trúc yêu cầu và suy ra scope đáng tin cậy.
Chuẩn hóa command.

BEGIN TRANSACTION

  Chiếm key bằng thao tác nguyên tử có unique constraint.

  Nếu key đã tồn tại:
      So sánh fingerprint.
      Nếu khác: báo xung đột.
      Nếu giống: kiểm tra quyền đọc receipt/operation.
      Trả receipt hoặc trạng thái được hợp đồng cho phép.

  Nếu vừa chiếm key:
      Đọc và khóa hồ sơ đúng tenant.
      Kiểm tra quyền thực thi trên hồ sơ.
      Kiểm tra phê duyệt, phiên bản và trạng thái.
      Kiểm tra số tiền, tiền tệ và nơi nhận theo dữ liệu server.
      Giữ reservation hoàn toàn bộ của giao dịch.
      Tạo một operation.
      Chuyển hồ sơ sang QUEUED bằng điều kiện trạng thái/phiên bản.
      Ghi một outbox event REFUND_REQUESTED.
      Hoàn thiện receipt gắn với operation.

COMMIT

Trả receipt đã commit.
~~~

Bản ghi giữ chỗ chưa hoàn thiện không được commit rồi bị coi như kết quả thành công. Nếu quyết định nghiệp vụ bị từ chối trong mô hình này, transaction rollback cả việc giữ key. Một API muốn lưu cả từ chối cuối cùng phải định nghĩa riêng loại kết quả nào được ghi nhớ.

Với unique conflict, cách tiếp tục phụ thuộc database và transaction manager. Không bắt mọi lỗi unique rồi trả “thành công”. Phải xác định conflict thuộc key, intent hay reservation nào; nếu transaction đã hỏng thì rollback và đọc lại trong transaction phù hợp.

### 9.4. Chuyển trạng thái có điều kiện

Ví dụ phần chuyển hồ sơ:

~~~sql
UPDATE refund_intent
SET state = 'QUEUED',
    operation_id = :operation_id,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND id = :intent_id
  AND state = 'APPROVED'
  AND version = :expected_version;
~~~

Chỉ số dòng cập nhật bằng 1 mới cho phép hoàn tất nhánh chấp nhận. Kết quả bằng 0 cần được phân loại theo hợp đồng: phiên bản cũ, trạng thái không phù hợp hoặc hồ sơ đã được nhận xử lý.

Câu UPDATE này chỉ là một phần của transaction. Nó không tự kiểm tra quyền ở nguồn khác, không thay thế reservation theo capture và không chứng minh rằng nhà cung cấp đã hoàn tiền.

Nếu quyền hoặc nội dung được duyệt có thể đổi đồng thời, thiết kế phải bảo vệ mối quan hệ giữa chúng và bước chuyển trạng thái. Một lần kiểm tra quyền từ trước không tự bảo đảm quyền còn hợp lệ tại điểm quyết định.

## 10. Ranh giới với dịch vụ bên ngoài và kết quả chưa biết

### 10.1. Vì sao transaction cục bộ chưa đủ?

Database rollback không thu hồi được một khoản hoàn tiền mà nhà cung cấp đã thực hiện. Outbox giúp lưu ý định gửi cùng transaction nghiệp vụ, nhưng worker vẫn có thể gửi lại sau lỗi.

Do đó cần kết hợp:

- Operation ID ổn định qua mọi lần thử.
- Key chống trùng phía nhà cung cấp, nếu giao thức hỗ trợ.
- Tra cứu kết quả bằng operation/reference ổn định.
- Ghi nhận kết quả và áp dụng sổ cái một lần ở phía ứng dụng.
- Đối soát khi không biết tác dụng bên ngoài đã xảy ra hay chưa.

Provider key nên được suy ra từ danh tính operation ổn định và phạm vi tài khoản phù hợp. Không tạo key mới cho mỗi attempt của cùng operation.

### 10.2. State machine cần biểu đạt sự không chắc chắn

~~~mermaid
stateDiagram-v2
    [*] --> QUEUED: Command được commit
    QUEUED --> IN_FLIGHT: Worker bắt đầu gửi
    IN_FLIGHT --> SUCCEEDED: Xác nhận thành công
    IN_FLIGHT --> FAILED_FINAL: Xác nhận không thực hiện và lỗi cuối cùng
    IN_FLIGHT --> UNKNOWN: Timeout hoặc mất kết nối
    UNKNOWN --> SUCCEEDED: Đối soát thấy đã thực hiện
    UNKNOWN --> FAILED_FINAL: Xác nhận không thực hiện và không tiếp tục
~~~

Timeout là thông tin về quan sát của ứng dụng, không tự là bằng chứng nhà cung cấp chưa hoàn tiền.

Ở trạng thái UNKNOWN:

1. Không tạo một operation mới chỉ để thử lại cho nhanh.
2. Tra cứu hoặc đối soát bằng cùng định danh.
3. Nếu giao thức cho phép retry, dùng lại cùng danh tính và key theo hợp đồng của nhà cung cấp.
4. Giữ bất biến nghiệp vụ trong lúc chưa có kết luận.
5. Chỉ cập nhật kết quả cuối khi có căn cứ tương ứng.

Không thể hứa “exactly once” xuyên suốt nhiều hệ thống chỉ bằng một unique constraint trong database cục bộ. Cần nói rõ phạm vi bảo đảm: tiếp nhận command một lần về mặt logic, gửi message có thể lặp, và áp dụng tác dụng nghiệp vụ được chống trùng tại từng ranh giới.

### 10.3. Chính sách của nhà cung cấp phải được đọc riêng

Ví dụ, Stripe API v1 mô tả việc lưu kết quả theo idempotency key sau khi endpoint bắt đầu thực thi, kiểm tra tham số khi dùng lại key và có chính sách loại bỏ key. Không nên suy rộng hợp đồng đó sang mọi API hoặc mọi phiên bản. Xem [tài liệu idempotent requests của Stripe](https://docs.stripe.com/api/idempotent_requests).

Khi tích hợp một nhà cung cấp cụ thể, cần xác định thời gian lưu key, loại lỗi được ghi nhớ, cách xử lý yêu cầu đồng thời và cách tra cứu một kết quả chưa rõ. Bất biến hoàn tiền của ứng dụng không được phụ thuộc hoàn toàn vào thời gian nhà cung cấp còn nhớ key.

## 11. Khi command được ký: replay thông điệp và replay ý định

Với API giữa các hệ thống, command có thể được ký hoặc gắn MAC. Chữ ký hợp lệ không tự chứng minh thông điệp chưa từng được dùng.

[RFC 9421, mục 7.2.2](https://www.rfc-editor.org/rfc/rfc9421.html#section-7.2.2) thảo luận nguy cơ phát lại chữ ký, việc bao phủ đủ thành phần thông điệp và dùng nonce cùng thông tin thời gian để hạn chế replay.

Một chính sách cần xác định:

- Signer nào được phép thực hiện loại lệnh này.
- Method, target, body hoặc digest đã được xác minh, và các tham số bảo mật nào phải được chữ ký bao phủ.
- Giới hạn thời gian được chấp nhận và độ lệch đồng hồ.
- Phạm vi duy nhất của nonce, chẳng hạn theo danh tính khóa ký và audience.
- Cách ghi nhận nonce đã dùng bằng thao tác nguyên tử.
- Cách xử lý khi kho kiểm tra replay không khả dụng.

Dữ liệu ở ngoài phạm vi được ký không được tự nhiên trở thành đáng tin cậy chỉ vì một phần khác của request có chữ ký.

Ví dụ, timestamp chỉ giới hạn cửa sổ:

~~~text
Thông điệp hợp lệ trong một khoảng thời gian.
Trong khoảng đó, một bản sao vẫn có thể được gửi nhiều lần.
~~~

Nonce cần được nhớ đủ lâu để không bị quên khi chữ ký tương ứng vẫn còn được chấp nhận, có tính đến chính sách thời gian và độ lệch đồng hồ.

Mặt khác, client hợp lệ có thể ký lại một retry bằng timestamp và nonce mới. Khi ấy thông điệp truyền tải mới nhưng command nghiệp vụ vẫn là C1. Hệ thống vẫn cần operation ID, idempotency và bất biến nghiệp vụ.

Không dùng nonce làm thay thế hoàn toàn cho danh tính command nếu mỗi retry hợp lệ bắt buộc có nonce khác nhau.

## 12. Thời gian lưu và lỗi “quên mất đã làm”

### 12.1. TTL của receipt không phải thời hạn bất biến

Giả sử kho idempotency xóa receipt sau một khoảng lưu giữ. Một người gửi lại yêu cầu cũ sau đó có thể làm lớp lookup coi key như chưa từng xuất hiện.

Điều đó không được làm RI-42 trở về APPROVED hoặc làm CAP-981 có thêm quyền hoàn toàn bộ.

Các lớp có vòng đời khác nhau:

| Dữ liệu | Mục đích | Vấn đề cần quyết định |
|---|---|---|
| Response cache | Trả nhanh kết quả đã lưu | Có thể tái tạo kết quả từ operation khi cache hết hạn không? |
| Command receipt | Gắn key với một command | API cho phép dùng lại key sau thời hạn nào, và xử lý thế nào? |
| Nonce đã dùng | Chống phát lại thông điệp có chữ ký | Khi nào thông điệp tương ứng chắc chắn không còn được nhận? |
| Hồ sơ đã tiêu thụ và operation | Duy trì lịch sử ý định nghiệp vụ | Làm sao vẫn nhận ra thao tác đã thực hiện sau archive? |
| Sổ cái hoặc dấu chống áp dụng trùng | Giữ tính đúng của tác dụng tài chính/nội bộ | Có còn đủ bằng chứng khi event cũ được giao lại không? |

Không có một TTL chung phù hợp cho mọi command. Chọn theo khả năng retry, thời gian giao lại message, vòng đời nghiệp vụ và cách dữ liệu được lưu trữ lâu dài.

### 12.2. Restart và nhiều instance

Nếu thông tin “đã xử lý” chỉ nằm trong một map hoặc cache cục bộ, restart có thể làm hệ thống quên command. Hai instance cũng có thể đồng thời chấp nhận cùng một key.

Nguồn dữ liệu quyết định cần có tính bền vững và cơ chế phân xử tranh chấp phù hợp. Cache có thể tăng tốc nhưng không được làm mất ràng buộc khi bị xóa.

### 12.3. Khóa có lease và worker chạy chậm

Một lease hết hạn không chứng minh worker trước đã ngừng hoặc nhà cung cấp chưa xử lý. Worker cũ có thể tiếp tục sau khi worker mới được nhận việc.

Cần cơ chế ngăn ghi bằng quyền sở hữu cũ, nhận diện operation ổn định và chống trùng tác dụng bên ngoài theo khả năng giao thức. Việc gia hạn khóa không thay thế các bất biến này.

## 13. Consumer và callback cũng có replay scenario

Một command đã được tiếp nhận đúng vẫn có thể bị thực thi trùng ở bước sau:

~~~text
Outbox lưu REFUND_REQUESTED cho RF-501.
Worker nhận message, gọi nhà cung cấp rồi chết trước khi ACK.
Broker giao lại message.
Worker mới tiếp tục xử lý RF-501.
~~~

Ngoài ra, nhà cung cấp có thể gửi nhiều callback cho cùng một refund, hoặc có nhiều event ID mô tả các thay đổi liên quan tới cùng operation.

Vì vậy cần hai loại chống trùng:

- **Chống xử lý lại thông điệp:** nhận diện event trong phạm vi nguồn phát phù hợp.
- **Chống áp dụng lại nghiệp vụ:** ràng buộc operation và loại tác dụng cụ thể, bất kể có bao nhiêu event.

Ví dụ, callback “refund succeeded” đến hai lần không được tạo hai bút toán hoàn tiền. Nếu hai event ID khác nhau cùng xác nhận một refund, chỉ dedupe theo event ID chưa bảo vệ đủ.

Việc đánh dấu message đã xử lý và ghi tác dụng cục bộ phải có ranh giới nguyên tử phù hợp. Đánh dấu trước rồi chết có thể mất tác dụng; ghi tác dụng rồi chết trước khi đánh dấu có thể tạo trùng nếu không có ràng buộc bổ sung.

Callback cũng cần xác thực nguồn và đối chiếu tài khoản, operation, số tiền và tiền tệ; một event có chữ ký hợp lệ vẫn phải được ánh xạ vào đúng đối tượng của ứng dụng.

## 14. Chuyển kịch bản thành kiểm thử

Không chỉ assert số HTTP response thành công. Một phản hồi lỗi vẫn có thể đi kèm tác dụng đã xảy ra.

Ma trận tối thiểu cho ví dụ:

| Ca | Thao tác | Kết quả cần quan sát |
|---|---|---|
| Tiếp nhận hợp lệ | Gửi một command đúng phê duyệt | Một operation, một ý định khởi động, dữ liệu đúng snapshot |
| Retry tuần tự | Gửi lại cùng scope, key và nội dung | Cùng operation, không thêm tác dụng |
| Retry sau mất phản hồi | Command đã commit nhưng phản hồi bị ngắt | Tìm lại được operation cũ |
| Hai request đồng thời | Cùng key, cùng command, hai transaction | Chỉ một nhánh tạo operation |
| Key bị dùng cho nội dung khác | Cùng key, đổi amount hoặc target | Xung đột, không thực thi nội dung mới |
| Key mới cho cùng intent | RI-42 đã được tiếp nhận | Không tạo operation thứ hai |
| Intent mới cho capture đã tiêu thụ | Đổi cả key và intent | Reservation/bất biến vẫn chặn hoàn toàn bộ thêm |
| Khác tenant | Dùng cùng chuỗi key | Không nhận receipt hoặc dữ liệu tenant khác |
| Quyền đã đổi | Người gọi mất quyền thực thi hoặc đọc | Đúng chính sách hiện tại, không bỏ qua vì cache |
| Sau restart | Xử lý lại command cũ | Nguồn dữ liệu bền vững vẫn nhận diện đã xử lý |
| Sau khi cache hết hạn | Replay command lịch sử | Bất biến nghiệp vụ vẫn giữ |
| Provider timeout | Chưa xác định đã hoàn tiền hay chưa | UNKNOWN hoặc trạng thái tương ứng; không tạo lệnh mới tùy ý |
| Giao lại message/callback | Cùng operation được nhận nhiều lần | Không ghi sổ cái hoặc cấp lợi ích thêm lần nữa |
| Thông điệp ký bị phát lại | Cùng nonce còn trong cửa sổ nhận | Xử lý đúng chính sách chống replay của thông điệp |
| Retry được ký mới | Nonce mới nhưng cùng command | Vẫn gắn với operation cũ |

Các assertion quan trọng có thể viết dưới dạng:

~~~text
operation_count(tenant, intent) <= 1

successful_full_refund_count(tenant, capture) <= 1

ledger_application_count(operation, refund_effect) <= 1

recorded_amount = approved_amount
recorded_currency = approved_currency
recorded_destination = original_payment_destination

Mọi receipt được trả cho người gọi đều nằm trong phạm vi họ được quyền đọc.
~~~

Để bắt race ở nhánh tiếp nhận, đặt điểm đồng bộ ở vị trí phù hợp với thuật toán claim key hoặc chuyển trạng thái. Không chỉ gửi hai request “gần cùng lúc” rồi giả định cửa sổ tranh chấp đã được tạo.

Để kiểm tra mất phản hồi sau commit, phải ngắt tại đúng mốc sau commit. Một test ngắt trước khi command được nhận chỉ kiểm tra một tình huống khác.

Khi giả lập nhà cung cấp, phân biệt số lần gọi mạng với số tác dụng được áp dụng: retry cùng provider key có thể tạo nhiều lần gọi nhưng chỉ một tác dụng. Cả hai số liệu đều hữu ích, nhưng có ý nghĩa khác nhau.

## 15. Dấu hiệu thiết kế dễ bị lạm dụng

Khi đọc một luồng xử lý command, hãy tìm những dấu hiệu sau:

- Controller gọi dịch vụ bên ngoài trước khi có danh tính operation bền vững.
- Kiểm tra key bằng SELECT rồi INSERT mà không có cơ chế phân xử nguyên tử.
- Key chỉ được nhớ trong bộ nhớ của một instance.
- Cùng key nhưng payload mới vẫn được nhận mà không so fingerprint.
- Receipt lookup không gắn tenant hoặc caller scope.
- Cache hit được trả trước khi xác thực hay kiểm tra quyền đọc.
- Key mới làm hồ sơ đã xử lý được chạy lại.
- APPROVED được kiểm tra nhưng không gắn với phiên bản và nội dung được duyệt.
- Timeout bị đổi trực tiếp thành “chưa làm gì”.
- Worker retry với một provider key mới cho cùng operation.
- Xóa dấu chống trùng theo TTL làm mất luôn bằng chứng đã tiêu thụ ý định.
- Callback trùng tạo thêm bút toán dù trạng thái cuối vẫn là SUCCEEDED.

Một trạng thái cuối nhìn có vẻ đúng không chứng minh quá trình an toàn. Hai lần ghi có thể cùng để lại trạng thái REFUNDED, nhưng đã tạo hai khoản chi hoặc hai lợi ích.

## 16. Thực hành

### Bài tập 1: Phân loại lần gửi thứ hai

Với command hoàn tiền RI-42, hãy quyết định cách xử lý cho bốn trường hợp:

1. Cùng key, cùng body, token được refresh nhưng vẫn cùng principal.
2. Cùng key, số tiền từ 1.000.000 đổi thành 2.000.000.
3. Key mới, vẫn dùng RI-42 đã được tiếp nhận.
4. Cùng chuỗi key, đến từ tenant khác.

Với mỗi trường hợp, ghi rõ scope được dùng, có được tạo operation không, và dữ liệu nào được phép trả về.

### Bài tập 2: Phân tích điểm chết

Ứng dụng chết tại một trong các mốc:

~~~text
A. Trước khi transaction tiếp nhận commit.
B. Sau commit nhưng trước khi trả receipt.
C. Sau khi nhà cung cấp hoàn tiền nhưng trước khi worker lưu kết quả.
D. Sau khi ghi sổ cái nhưng trước khi ACK callback.
~~~

Với từng mốc, nêu nguồn dữ liệu cho phép phục hồi, danh tính nào phải được giữ qua retry, và điều gì ngăn tác dụng bị áp dụng thêm.

### Bài tập 3: Đổi sang hoàn tiền một phần

Giả sử hệ thống cho phép nhiều lần hoàn một phần. Thay bất biến “mỗi capture chỉ một refund” bằng quy tắc tổng số tiền đã hoàn và đã giữ chỗ không vượt số tiền được phép hoàn.

Giải thích vì sao vẫn cần chống trùng theo command, đồng thời không thể giữ nguyên một unique constraint theo capture nếu nó cấm mọi lần hoàn tiếp theo hợp lệ.

### Bài tập 4: Viết hợp đồng cho kết quả chưa biết

Thiết kế phản hồi khi operation ở UNKNOWN:

- Client được biết điều gì?
- Có được gửi command mới không?
- Ai thực hiện đối soát và dùng định danh nào?
- Khi nào được chuyển sang SUCCEEDED hoặc FAILED_FINAL?

Không dùng câu “timeout thì cứ thử lại bằng key mới” làm chính sách phục hồi.

## 17. Điểm cần nhớ

Command replay xuất hiện khi cùng một ý định quay lại hệ thống qua retry, gửi lại có chủ đích, giao lại message hoặc callback. Một lệnh hợp lệ ở lần đầu không mặc nhiên có quyền tạo thêm tác dụng ở lần sau.

Với kịch bản hoàn tiền, cần nối được danh tính command với operation bền vững, phê duyệt đúng nội dung, quyền theo đối tượng, transaction tiếp nhận và bất biến của giao dịch. Khi kết quả bên ngoài chưa rõ, phải giữ danh tính đó để đối soát và phục hồi, thay vì tạo một lệnh mới rồi hy vọng không bị trùng.
