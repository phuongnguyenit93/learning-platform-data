# Mục đích của idempotency key

## 1. Vì sao một yêu cầu có thể tạo ra hai tác động nghiệp vụ?

Trong bảo mật logic nghiệp vụ, hệ thống phải bảo vệ những quy tắc như: một đơn hàng chỉ được thanh toán toàn bộ thành công một lần, một yêu cầu hoàn tiền chỉ được ghi nhận một lần, hoặc một quyết định phê duyệt chỉ được áp dụng đúng một lần. Một request hợp lệ về đăng nhập và dữ liệu vẫn có thể làm sai các quy tắc này nếu được thực thi lặp lại.

Ví dụ, người dùng thanh toán đơn hàng `O42` bằng ví nội bộ:

1. Client gửi yêu cầu thanh toán.
2. Server trừ tiền, ghi nhận thanh toán và commit transaction.
3. Kết nối bị ngắt trước khi client nhận được phản hồi.
4. Client không biết thao tác đã thành công nên gửi lại.

Nếu server xem lần gửi lại là một lần thanh toán mới, ví có thể bị trừ tiền lần thứ hai. Tình huống tương tự xuất hiện khi người dùng nhấn nút nhiều lần, ứng dụng tự retry, message được giao lại hoặc kẻ tấn công chủ động gửi nhiều request đồng thời.

**Idempotency key giúp server nhận diện các lần gửi thuộc cùng một ý định thao tác, để việc gửi lại không tạo thêm tác động nghiệp vụ ngoài dự kiến.** Đây là một cơ chế bảo vệ quan trọng trong module Business Logic Security, bên cạnh business invariants, state machine, quyền theo đối tượng và transaction.

Sau bài này, người học cần giải thích được key đại diện cho điều gì, phạm vi bảo đảm của nó, cách xử lý key trùng và lý do vẫn phải kiểm tra các quy tắc nghiệp vụ độc lập với key.

## 2. Idempotency bảo đảm điều gì?

Một thao tác có tính idempotent khi thực hiện lại cùng một thao tác không tạo thêm thay đổi trạng thái ngoài kết quả của lần thực hiện đầu tiên. Đối với API có idempotency key, tính chất này thường được giới hạn bởi một hợp đồng rõ ràng:

> Trong cùng phạm vi định danh và thời gian còn hiệu lực, các request dùng cùng key và cùng ý định nghiệp vụ được liên kết với cùng một lần xử lý; server không tạo thêm lần thực thi tác động đã được bảo vệ.

Cụm “cùng phạm vi” rất quan trọng. Một chuỗi key đơn lẻ chưa đủ để xác định request nào được xem là trùng. Thông thường còn cần tenant, người thực hiện và loại thao tác.

Không nên hiểu idempotency là mọi lần gọi đều trả về các byte giống hệt nhau. Một hợp đồng có thể trả lại kết quả đã lưu; hợp đồng khác có thể trả về mã tài nguyên hoặc trạng thái đang xử lý. Dù chọn cách nào, client phải nhận diện được cùng một thao tác và không bị tạo thêm tác động vì retry.

Idempotency cũng không có nghĩa request chắc chắn sẽ thành công. Nếu mọi lần gọi đều thất bại trước khi commit, có thể không có tác động nào được tạo ra. Cơ chế này kiểm soát việc lặp lại, còn khả năng hoàn thành công việc phụ thuộc thêm vào retry, phục hồi và trạng thái hệ thống.

### Phân biệt những khái niệm thường bị nhầm

| Khái niệm | Mục đích chính | Giới hạn cần nhớ |
|---|---|---|
| Idempotency key | Liên kết các lần gửi với cùng một ý định thao tác | Không tự chứng minh quyền hoặc tính hợp lệ của thao tác |
| Request ID / trace ID | Theo dõi một lần gọi hoặc một luồng xử lý | Thường thay đổi qua từng lần retry, không đủ để chống tác động trùng |
| Transaction | Ghi nhận một nhóm thay đổi cùng thành công hoặc cùng rollback | Hai transaction hợp lệ riêng biệt vẫn có thể cùng thực thi một thao tác |
| Business invariant | Bảo vệ quy tắc luôn phải đúng, ví dụ một đơn chỉ có một thanh toán toàn bộ thành công | Phải được bảo vệ cả khi request dùng key khác nhau |
| State machine | Kiểm soát chuyển trạng thái hợp lệ | Không tự cung cấp cơ chế trả lại kết quả cho request bị mất phản hồi |
| Chống replay trong xác thực | Phát hiện hoặc từ chối việc gửi lại thông điệp theo hợp đồng xác thực | Không thay thế cơ chế retry an toàn ở tầng nghiệp vụ |

Việc vô hiệu hóa nút thanh toán trên giao diện chỉ giúp giảm thao tác nhầm. API vẫn phải chịu được request gửi trực tiếp và các request đến đồng thời.

## 3. Một key đại diện cho một ý định thao tác

Client tạo key **trước lần gửi đầu tiên**, giữ lại key đó khi chưa biết chắc kết quả và tái sử dụng nó cho các lần retry của cùng thao tác.

Ví dụ minh họa:

```http
POST /v1/orders/O42/payments
Authorization: Bearer <access-token>
Idempotency-Key: 1b1f3c4a-8a62-4a84-9c26-8ec5c75b40d2
Content-Type: application/json

{
  "paymentMethodId": "wallet-main",
  "expectedOrderVersion": 12
}
```

Server lấy số tiền, tiền tệ và điều kiện được thanh toán từ dữ liệu tin cậy của đơn hàng. Idempotency key không làm cho một trường giá do client tự gửi trở thành đáng tin cậy.

Nếu response bị mất, client gửi lại cùng key và cùng nội dung có ý nghĩa nghiệp vụ. Server có thể trả lại cùng mã thanh toán:

```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "paymentId": "pay_901",
  "orderId": "O42",
  "status": "SUCCEEDED",
  "amountMinor": 250000,
  "currency": "VND"
}
```

Các mã tài nguyên và giá trị ở đây chỉ dùng để minh họa. API phải công bố cụ thể phản hồi khi replay, khi đang xử lý và khi phát hiện nội dung không khớp.

### Khi nào giữ key, khi nào tạo key mới?

| Tình huống | Cách xử lý key |
|---|---|
| Timeout, mất kết nối, chưa biết request đã commit chưa | Giữ key của thao tác đang chờ kết quả |
| Nhấn gửi lại cùng ý định sau khi ứng dụng hiển thị trạng thái chưa xác định | Giữ key đã lưu cho thao tác đó |
| Tạo một ý định nghiệp vụ mới được hệ thống cho phép | Tạo key mới |
| Thay đổi phương thức thanh toán hoặc phiên bản đơn hàng trong lúc kết quả cũ chưa rõ | Tra cứu và giải quyết thao tác cũ trước; không tự xem đây là retry cùng nội dung |
| Thấy lỗi mạng rồi tạo key mới cho mỗi lần retry | Sai: server có thể nhận các request như những thao tác độc lập |

Không nên suy ý định chỉ từ hash của toàn bộ request. Hai lần chuyển tiền hợp lệ, độc lập có thể có cùng người nhận và cùng số tiền. Ngược lại, hai request thuộc cùng ý định có thể khác trace ID hoặc một số metadata truyền tải.

Key nên đủ khó trùng do ngẫu nhiên, được lưu bền phù hợp với vòng đời thao tác và có giới hạn độ dài, định dạng rõ ràng. Nếu client chỉ giữ key trong bộ nhớ rồi mất nó khi ứng dụng khởi động lại, khả năng retry an toàn cũng có thể bị mất. Tùy sản phẩm, client cần lưu cả key và mã thao tác để tiếp tục tra cứu sau khi khởi động lại.

## 4. Ràng buộc key với đúng phạm vi và đúng nội dung

### 4.1. Phạm vi định danh

Một bản ghi có thể được nhận diện bằng bộ giá trị:

```text
scope = (tenant_id, subject_id, operation_name)
identity = (scope, idempotency_key)
```

Trong ví dụ này, `subject_id` là định danh người hoặc service thực hiện thao tác sau xác thực. `operation_name` là loại thao tác đã chuẩn hóa, chẳng hạn `order.pay.v1`, không phải một chuỗi tùy ý do client quyết định.

Các thành phần của scope phải đến từ ngữ cảnh xác thực và định tuyến tin cậy. Nếu tenant chỉ được lấy từ body mà không kiểm tra, kẻ tấn công có thể thử chiếm key hoặc đọc lại kết quả của tenant khác.

Đây là một thiết kế scope thường gặp, không phải công thức duy nhất. Một luồng được phép tiếp tục bởi nhiều service hoặc nhiều người có thể cần scope theo danh tính nghiệp vụ ổn định. Thiết kế đó vẫn phải kiểm tra quyền của từng người gọi. Ngược lại, scope theo người dùng sẽ không tự gộp được hai thao tác do hai người khác nhau gửi cho cùng đơn hàng; business invariant phải xử lý trường hợp ấy.

### 4.2. Fingerprint của ý định nghiệp vụ

Server lưu thêm fingerprint để phân biệt:

- Cùng key, cùng ý định: retry hợp lệ.
- Cùng key, khác ý định: xung đột, không được thực thi như một thao tác mới.

Ví dụ đầu vào để tạo fingerprint:

```text
fingerprint = HASH(canonicalize({
    operation: "order.pay.v1",
    orderId: "O42",
    paymentMethodId: "wallet-main",
    expectedOrderVersion: 12
}))
```

`HASH` ở đây đại diện cho một hàm băm mật mã phù hợp. Fingerprint dùng để so sánh nội dung, không phải chữ ký chứng minh client có quyền thao tác.

Việc chuẩn hóa cần dựa trên schema của API:

- Chuẩn hóa các trường mặc định theo đúng hợp đồng.
- Với dữ liệu tiền do API chấp nhận, biểu diễn giá trị bằng đơn vị nhỏ nhất hoặc kiểu số thập phân có quy tắc rõ ràng; không dùng sai số số thực để định nghĩa ý định.
- Không xem thứ tự thuộc tính JSON hay khoảng trắng là thay đổi nghiệp vụ.
- Giữ nguyên thứ tự của mảng nếu thứ tự đó có ý nghĩa.
- Bao gồm mã đối tượng, phiên bản kỳ vọng hoặc mã báo giá nếu chúng quyết định thao tác được thực hiện.
- Loại bỏ metadata không ảnh hưởng ý định, ví dụ trace ID.

Không nên băm nguyên văn toàn bộ HTTP request vì access token, header truyền tải và cách serialize JSON có thể thay đổi giữa các lần retry.

Ngược lại, không được bỏ sót trường quan trọng. Nếu fingerprint chỉ có `orderId` mà thiếu phương thức thanh toán, request dùng lại key nhưng thay phương thức có thể bị hiểu nhầm là cùng thao tác.

### 4.3. Không tái định nghĩa thao tác cũ bằng dữ liệu hiện tại

Giả sử thao tác đầu tiên đã thanh toán giá trị được server xác nhận. Sau đó giá niêm yết hoặc cấu hình giảm giá thay đổi. Retry của thao tác cũ phải được liên kết với kết quả và dữ liệu đã chốt cho thao tác đó; không được tính lại thành một lần thanh toán mới theo giá hiện tại.

Điều này không có nghĩa bỏ qua xác thực hay quyền hiện tại. Cần tách hai việc: kiểm tra người gọi còn được phép xem hoặc tiếp tục thao tác, và quyết định liệu request đang lặp lại một kết quả đã có hay đang yêu cầu thực thi mới.

Với ví dụ trên, `expectedOrderVersion` là dữ liệu của ý định ban đầu. Không thay nó bằng phiên bản mới đọc được rồi kết luận một retry hợp lệ đã đổi nội dung.

## 5. Hành vi cần có khi nhận lại một key

Một hợp đồng API nên mô tả ít nhất các trường hợp sau:

| Trạng thái server quan sát được | Hành vi mong muốn |
|---|---|
| Chưa có key trong scope | Đăng ký quyền xử lý nguyên tử, sau đó kiểm tra và thực hiện nghiệp vụ |
| Đã có key, fingerprint khác | Từ chối xung đột; không ghi đè bản ghi và không thực thi nội dung mới |
| Đã có key, cùng fingerprint, đã hoàn tất | Kiểm tra quyền hiện tại rồi trả kết quả đã lưu hoặc tham chiếu cùng thao tác |
| Đã có key, cùng fingerprint, đang xử lý | Chờ có giới hạn hoặc trả trạng thái đang xử lý theo hợp đồng; không tạo worker độc lập thứ hai |
| Có kết quả nghiệp vụ bị từ chối và kết quả đó được lưu | Trả lại kết quả từ chối theo chính sách đã công bố |
| Chưa rõ tác động bên ngoài đã xảy ra chưa | Giữ liên kết với thao tác cũ, tra cứu hoặc đối soát; không mặc định cho chạy mới |

Ví dụ, API có thể dùng `409 Conflict` với mã lỗi `IDEMPOTENCY_KEY_REUSED` khi key trùng nhưng fingerprint khác. Với xử lý bất đồng bộ, API có thể trả `202 Accepted` cùng mã thao tác và URL tra cứu. Những lựa chọn này là hợp đồng minh họa; không phải mọi API đều phải dùng cùng một mã HTTP.

Phải phân biệt lỗi cú pháp với kết quả đã được chốt. Request JSON không hợp lệ thường có thể bị từ chối trước khi đăng ký key. Một lỗi nghiệp vụ xác định, như không đủ điều kiện phê duyệt, có thể được lưu để retry nhận cùng kết quả. Nếu trạng thái đã thay đổi và người dùng muốn thử một ý định mới, phải làm theo chính sách nghiệp vụ về thao tác mới.

Không thể quyết định vòng đời key chỉ bằng mã HTTP. Một lỗi `5xx` có thể xảy ra trước commit, sau commit hoặc sau khi hệ thống bên ngoài đã nhận lệnh. Quyết định được retry thực thi hay chỉ replay/tra cứu phải dựa vào trạng thái bền vững của thao tác và tác động của nó.

## 6. Cần bảo vệ tác động và bản ghi idempotency cùng nhau

### 6.1. Vì sao kiểm tra rồi ghi riêng rẽ bị lỗi?

Mẫu sau không an toàn:

```text
if key chưa tồn tại:
    trừ tiền()
    lưu key và kết quả()
```

Hai request có thể cùng đọc thấy key chưa tồn tại rồi cùng trừ tiền. Ngay cả khi chỉ có một request, tiến trình có thể chết sau khi trừ tiền nhưng trước khi lưu key.

Nếu lưu “đã xong” trước khi trừ tiền, lỗi theo chiều ngược lại xuất hiện: server có thể trả thành công cho một thao tác chưa hề tạo ra tác động.

Với dữ liệu nằm trong cùng cơ sở dữ liệu có transaction phù hợp, cần kết hợp:

1. Ràng buộc duy nhất cho định danh idempotency.
2. Cơ chế khóa hoặc cập nhật có điều kiện bảo vệ dữ liệu nghiệp vụ.
3. Transaction chứa cả tác động nghiệp vụ và kết quả idempotency.

### 6.2. Dữ liệu cần lưu

Một mô hình tối thiểu có thể gồm:

| Trường | Vai trò |
|---|---|
| `tenant_id`, `subject_id`, `operation_name`, `key` | Xác định scope và key |
| `request_fingerprint` | Phát hiện cùng key nhưng khác ý định |
| `processing_state` | Thể hiện kết quả xử lý request theo mô hình đã chọn |
| `business_operation_id` | Liên kết với thanh toán, hoàn tiền hoặc quyết định nghiệp vụ |
| `response_status`, `response_payload` hoặc tham chiếu kết quả | Cho phép trả lại kết quả một cách nhất quán |
| `created_at`, `expires_at` | Quản lý thời gian lưu và vòng đời |

Trong thiết kế có scope như trên, phải có ràng buộc duy nhất tương đương:

```sql
UNIQUE (tenant_id, subject_id, operation_name, idempotency_key)
```

Các cột định danh này phải có quy tắc không rỗng phù hợp, tránh phụ thuộc vào cách từng cơ sở dữ liệu xử lý giá trị `NULL` trong unique constraint. Một thao tác đọc trước rồi mới insert không thay thế được ràng buộc duy nhất tại nơi ghi dữ liệu.

Chỉ lưu những phần phản hồi cần thiết. Nếu lưu toàn bộ response nhạy cảm, bản ghi idempotency cũng trở thành dữ liệu cần kiểm soát truy cập và vòng đời.

### 6.3. Luồng đồng bộ với ví nội bộ

Giả sử số dư ví, sổ cái, đơn hàng, thanh toán và bản ghi idempotency đều nằm trong cùng một cơ sở dữ liệu. Đây là mã giả thể hiện thứ tự xử lý, không phải đoạn Java hay SQL có thể chạy trực tiếp:

```text
principal = authenticate(request)
input = parseAndNormalizeUsingSchema(request)
key = validateKeyFormatAndLength(request.idempotencyKey)
scope = trustedScope(principal, "order.pay.v1")
digest = fingerprint(input, route.orderId, "order.pay.v1")

BEGIN TRANSACTION

claim = reserveWithUniqueConstraint(scope, key, digest)

if claim refers to an existing committed record:
    requireCurrentPermission(principal, route.orderId)

    if claim.fingerprint != digest:
        END WITHOUT BUSINESS EFFECT
        return KEY_CONFLICT

    result = claim.savedResult
    END WITHOUT BUSINESS EFFECT
    return result

order = loadOrderForUpdate(route.orderId)
requireCurrentPermission(principal, order)
require(order.version == input.expectedOrderVersion)
require(order.state == READY_FOR_PAYMENT)

amount = trustedPayableAmount(order)
paymentId = newPaymentId()

debitWalletAtomically(principal.wallet, amount)
insertLedgerEntry(paymentId, order.id, amount)
insertSuccessfulFullPaymentWithBusinessUniqueness(order.id, paymentId)
transitionOrder(order, READY_FOR_PAYMENT, PAID)

result = paymentResponse(paymentId, order.id, amount)
saveCompletedIdempotencyResult(scope, key, digest, result)

COMMIT
return result
```

`reserveWithUniqueConstraint` phải được hiện thực bằng cơ chế nguyên tử của cơ sở dữ liệu. Không thay nó bằng một biến trong bộ nhớ của một instance. Khi một transaction khác đang giữ cùng định danh chưa commit, cơ sở dữ liệu có thể buộc request sau chờ kết quả cạnh tranh. Ứng dụng cần giới hạn thời gian chờ và xử lý timeout hoặc deadlock theo hợp đồng retry, không suy ra rằng được phép thực thi thêm lần nữa.

Trong mô hình một transaction này, bản ghi đăng ký ban đầu và trạng thái hoàn tất commit cùng nhau. Request khác thường chỉ đọc được bản ghi đã hoàn tất sau commit; không cần giả định một trạng thái “đang xử lý” đã được commit riêng. Nếu transaction rollback trước commit, cả tác động và bản ghi đăng ký đều bị hủy.

Các hàm kiểm tra hoặc ghi nghiệp vụ trong mã giả có thể thất bại. Nhánh lỗi phải rollback những thay đổi chưa commit; nếu muốn lưu một kết quả từ chối ổn định, cần thiết kế nhánh lưu đó rõ ràng. Không nuốt lỗi ghi sổ cái hoặc lỗi unique constraint rồi vẫn commit một phần thao tác.

`debitWalletAtomically` cũng phải bảo vệ điều kiện đủ số dư khi có các thanh toán khác nhau cùng dùng ví. Idempotency key của một thao tác không giải quyết cạnh tranh giữa nhiều thao tác hợp lệ. Khi khóa nhiều bản ghi, cần có thứ tự khóa nhất quán và chính sách xử lý deadlock.

Một tác động phụ như gửi email không tự trở thành nguyên tử chỉ vì hàm gọi được đặt trong khối transaction. Cơ sở dữ liệu chỉ rollback được những gì nằm trong phạm vi transaction của nó.

### 6.4. Hai lớp duy nhất bảo vệ hai quy tắc khác nhau

Trong ví dụ chỉ cho phép một lần thanh toán toàn bộ thành công cho mỗi đơn hàng:

- Unique theo scope và key ngăn cùng ý định bị thực thi lại.
- Ràng buộc nghiệp vụ trên bản ghi thanh toán thành công, kết hợp chuyển trạng thái có khóa hoặc cập nhật có điều kiện, ngăn thanh toán toàn bộ một đơn hai lần bằng các key khác nhau.

Nếu sản phẩm cho phép chia lần thanh toán, nhiều lần thu tiền hoặc điều chỉnh, không được sao chép máy móc ràng buộc “mỗi đơn một payment”. Khi đó invariant phải gắn với đúng khoản phải thu hoặc mã thao tác nghiệp vụ, đồng thời bảo vệ tổng số tiền được phép thu.

## 7. Các điểm lỗi và cách hiểu kết quả

| Điểm xảy ra lỗi trong mô hình một transaction | Dữ liệu bền vững có thể quan sát | Hướng xử lý |
|---|---|---|
| Trước khi transaction bắt đầu | Chưa có tác động | Có thể gửi lại cùng key |
| Trong transaction, đã xác nhận rollback | Không có tác động hoặc bản ghi idempotency từ transaction đó | Có thể gửi lại cùng key và kiểm tra nghiệp vụ lại |
| Commit thành công, response bị mất | Tác động và kết quả idempotency cùng tồn tại | Retry cùng key trả lại kết quả đã có |
| Client hoặc ứng dụng mất kết nối đúng lúc commit | Chưa biết commit thành công hay thất bại | Retry cùng key hoặc tra cứu để phân giải; không tạo key mới để đoán |
| Tác động đã được gửi ra hệ thống khác | Phụ thuộc trạng thái của cả hai hệ thống | Dùng mã thao tác ổn định, tra cứu và đối soát |

Đặc biệt, một exception ở phía ứng dụng không luôn chứng minh transaction đã rollback. Mất kết nối lúc xác nhận commit là tình huống không rõ kết quả. Chính khả năng giữ cùng định danh xuyên qua retry giúp giải quyết khoảng không chắc chắn này.

Nếu lưu key ở cache còn số dư ở cơ sở dữ liệu khác, hai nơi không tự có tính nguyên tử chung. Cache hết hạn, bị mất dữ liệu hoặc không sẵn sàng đều có thể mở đường cho thực thi lại. Cache có thể hỗ trợ hiệu năng, nhưng cơ chế bảo vệ cuối cùng phải phù hợp với nơi lưu tác động nghiệp vụ và yêu cầu bền vững của nó.

## 8. Khi tác động nằm ở cổng thanh toán hoặc hệ thống khác

Một transaction cơ sở dữ liệu nội bộ thông thường không bao trùm lời gọi HTTP đến cổng thanh toán. Tình huống nguy hiểm:

1. Cổng thanh toán đã thu tiền.
2. Service mất kết nối hoặc chết trước khi ghi kết quả nội bộ.
3. Worker chạy lại và gửi một lệnh thu tiền mới.

Idempotency ở API đầu vào chỉ giải quyết một phần của luồng. Với tác động ra ngoài, cần thiết kế tiếp định danh và phục hồi:

1. Trong transaction nội bộ, tạo mã thao tác ổn định, bản ghi xử lý và sự kiện outbox.
2. Sau commit, worker lấy outbox để gửi lệnh.
3. Mọi lần gửi lại cho cùng thao tác dùng cùng định danh hoặc key được nhà cung cấp hỗ trợ, trong đúng tài khoản và phạm vi của nhà cung cấp.
4. Lưu kết quả hoặc trạng thái chưa xác định theo mã thao tác.
5. Khi kết quả chưa rõ, tra cứu nhà cung cấp bằng định danh ổn định hoặc đối soát theo quy trình, trước khi quyết định bước tiếp theo.
6. Nếu nhận webhook hoặc message kết quả nhiều lần, xử lý trùng theo định danh sự kiện hoặc thao tác và chuyển trạng thái có điều kiện.

Outbox giúp việc ghi nhận công việc cần gửi đi đi cùng transaction nội bộ. Nó không làm cho hệ thống nhận tự động hết tác động trùng: cùng một outbox message vẫn có thể được gửi lại.

Nếu API đầu vào trả `202 Accepted`, kết quả idempotency có thể là “đã tiếp nhận thao tác `pay_901`”. Trạng thái xử lý request đó khác với trạng thái “đã thu tiền thành công”. Client dùng mã thao tác để tra cứu tiến trình tiếp theo; replay không được tạo thêm thao tác mới.

Không nên dùng thời gian lease hết hạn làm bằng chứng rằng lần gọi bên ngoài trước đó chưa có tác động. Một worker cũ có thể vẫn tiếp tục chạy sau khi worker mới được cấp quyền. Khi cho phép thu hồi quyền xử lý, cần cơ chế phối hợp hoặc fencing thích hợp; tác động bên ngoài vẫn cần key ổn định và phục hồi trạng thái.

Nếu nhà cung cấp không có idempotency hoặc tra cứu đủ tin cậy, vẫn còn khoảng lỗi không thể che đi bằng một bảng key nội bộ. Cần giữ trạng thái chưa xác định và có phương án đối soát phù hợp. Không tuyên bố xử lý “exactly once” trên toàn luồng chỉ vì API có header idempotency.

## 9. Idempotency key không thay thế bảo mật nghiệp vụ

### 9.1. Không thay thế quyền theo đối tượng

Một người dùng biết key và mã thanh toán của người khác vẫn không được xem kết quả của người đó. Key là dữ liệu định danh thao tác, không phải bearer token cấp quyền.

Mỗi lần gọi, kể cả replay, phải xác thực và kiểm tra quyền truy cập hiện tại đối với đối tượng liên quan. Nếu quyền đã bị thu hồi, không được trả response nhạy cảm đã cache chỉ vì fingerprint khớp.

Phản hồi lỗi cũng cần tránh làm lộ tài nguyên. Không nên trả thông tin chi tiết về key hoặc thanh toán của một tenant khác chỉ vì request tình cờ dùng cùng chuỗi key.

### 9.2. Không thay thế state machine và phê duyệt

Một key mới không cho phép chuyển đơn hàng từ trạng thái chưa duyệt sang đã thanh toán. Điều kiện chuyển trạng thái phải được kiểm tra và cập nhật nguyên tử cho lần thực thi mới.

Ngược lại, khi replay một thanh toán đã hoàn tất, không nên ép thao tác phải còn ở trạng thái `READY_FOR_PAYMENT`: chính lần thực thi đầu tiên đã chuyển nó sang `PAID`. Luồng replay kiểm tra quyền và trả kết quả cũ; luồng thực thi mới kiểm tra toàn bộ điều kiện chuyển trạng thái.

### 9.3. Không sửa được lỗi tin dữ liệu giá từ client

Nếu server chấp nhận giá bị sửa từ 250.000 đồng xuống 1 đồng, idempotency chỉ giúp thao tác sai đó không bị lặp thêm dưới cùng key. Giá, quyền giảm giá, hạn mức hoàn tiền và người được phê duyệt vẫn phải đến từ dữ liệu và quy tắc tin cậy.

### 9.4. Không ngăn kẻ tấn công đổi key

Kẻ tấn công có thể gửi 100 key khác nhau cho cùng đơn hàng. Hệ thống phải dùng invariant, ràng buộc duy nhất nghiệp vụ, khóa hoặc cập nhật có điều kiện để bảo vệ đơn hàng; dùng rate limit và quota để kiểm soát lạm dụng tài nguyên.

Một key có độ ngẫu nhiên cao chủ yếu giúp tránh trùng ngoài ý muốn và hạn chế đoán key. Nó không thay thế bất kỳ kiểm tra quyền nào.

## 10. Thời gian lưu key là một phần của hợp đồng

Key chỉ còn giúp nhận diện retry nếu server còn giữ đủ dữ liệu để liên kết nó với thao tác cũ. Chính sách lưu cần xét:

- Khoảng thời gian client có thể retry hoặc tiếp tục sau khi offline.
- Thời gian một công việc có thể nằm trong hàng đợi hoặc được giao lại.
- Thời gian nhà cung cấp giữ idempotency key của họ.
- Khả năng tra cứu và đối soát thao tác sau sự cố.
- Chi phí lưu trữ và mức nhạy cảm của dữ liệu được lưu.

Không có một TTL đúng cho mọi loại thao tác. Hệ thống phải công bố khoảng thời gian hỗ trợ và cách xử lý request đến quá muộn.

**Xóa key không làm tác động nghiệp vụ cũ biến mất.** Khi retry rất muộn đến sau thời hạn lưu, server có thể không còn nhận ra key cũ. Invariant bền vững, mã thao tác nghiệp vụ, hoặc dữ liệu đánh dấu đã xử lý được giữ lâu hơn phải tiếp tục ngăn tác động trái quy tắc.

Với thao tác cho phép lặp hợp lệ, như chuyển tiền nhiều lần cùng số tiền, invariant kiểu “cùng nội dung chỉ được làm một lần” là sai. Khi đó cần chính sách rõ ràng về mã ý định nghiệp vụ được giữ lâu, thời hạn chấp nhận ý định hoặc cách client tra cứu trước khi retry ngoài cửa sổ hỗ trợ. Không dựa vào timestamp do client tự khai để chứng minh request còn mới.

Không tự xóa bản ghi “đang xử lý” chỉ vì quá TTL rồi cho phép chạy lại. Trước hết phải xác định tác động có thể đã xảy ra hay chưa và cơ chế nào cho phép phục hồi an toàn.

## 11. Các tình huống kiểm thử logic cần thiết

Kiểm thử nên khẳng định số tác động nghiệp vụ và trạng thái cuối cùng, không chỉ so sánh mã HTTP.

| Tình huống | Kết quả cần kiểm chứng |
|---|---|
| Gửi tuần tự nhiều request cùng scope, key và fingerprint | Một tác động; các response liên kết cùng mã thao tác |
| Gửi đồng thời nhiều request cùng key qua nhiều instance | Một lần ghi tác động thành công; các request còn lại replay, chờ hoặc nhận trạng thái theo hợp đồng |
| Cùng key nhưng thay đối tượng, phương thức hoặc giá trị có ý nghĩa | Từ chối xung đột; không thay kết quả cũ và không thực thi nội dung mới |
| Gửi lại sau commit nhưng làm mất response đầu tiên | Không tạo thêm sổ cái hoặc thanh toán |
| Dừng tiến trình trước commit trong mô hình transaction nội bộ | Không còn tác động dở dang từ transaction đã rollback |
| Mất kết nối khi commit chưa rõ kết quả | Retry cùng key phân giải về một kết quả hợp lệ |
| Nhiều key khác nhau cùng thanh toán toàn bộ một đơn | Invariant vẫn ngăn thanh toán thành công nhiều lần |
| Hai thao tác hợp lệ khác nhau cùng trừ một ví | Không chi vượt số dư theo quy tắc của ví |
| Key giống nhau ở hai tenant khác nhau | Scope tách biệt; không lộ dữ liệu chéo tenant |
| Người không có quyền gửi key đã biết | Không xem hoặc tạo được tác động trái quyền |
| Quyền bị thu hồi sau lần thực thi đầu | Replay không làm lộ response đã lưu trái quyền hiện tại |
| Replay sau khi đơn đã chuyển sang `PAID` | Người còn quyền nhận kết quả cũ, không tạo thanh toán mới |
| Retry sau khi dữ liệu giá hiện tại thay đổi | Kết quả cũ vẫn gắn với dữ liệu đã chốt của thao tác cũ |
| Key hết hạn rồi request cũ xuất hiện lại | Chính sách request muộn và invariant tiếp tục được thực thi |
| Worker gửi lệnh bên ngoài bị dừng sau khi nhà cung cấp nhận lệnh | Phục hồi bằng cùng định danh, tra cứu hoặc đối soát; không gửi lệnh mới tùy tiện |
| Webhook kết quả đến nhiều lần hoặc sai thứ tự | Không ghi lặp tác động; chỉ chuyển trạng thái khi điều kiện hợp lệ |

Với ví dụ ví nội bộ, các khẳng định quan trọng gồm: chỉ có một khoản trừ tương ứng thao tác; tổng biến động số dư đúng bằng số tiền phải trả; chỉ có một thanh toán toàn bộ thành công cho đơn; và kết quả idempotency trỏ đến thanh toán đã commit.

## 12. Vận hành và quan sát mà không tạo thêm lỗ hổng

Key là dữ liệu đầu vào không đáng tin cậy. Cần giới hạn chiều dài, kích thước payload, số bản ghi đang xử lý và tốc độ tạo key mới theo người dùng hoặc tenant. Nếu không, kẻ tấn công có thể tạo rất nhiều key để làm đầy kho lưu hoặc chiếm tài nguyên chờ khóa.

Log nên liên kết được request, scope và mã thao tác nghiệp vụ. Khi key hoặc payload có thể chứa dữ liệu nhạy cảm, dùng cách che hoặc băm phù hợp và hạn chế quyền xem log. Không ghi token xác thực hoặc dữ liệu phương thức thanh toán nhạy cảm chỉ để phục vụ replay.

Các chỉ số hữu ích gồm tỷ lệ replay, số xung đột fingerprint, thời gian chờ cùng key, thao tác ở trạng thái chưa xác định và số lần invariant từ chối các key khác nhau cho cùng đối tượng. Không đưa key hoặc mã người dùng có số lượng rất lớn trực tiếp vào nhãn metric.

Nếu kho idempotency không sẵn sàng, không tự chuyển sang thực thi không có cơ chế chống trùng cho thao tác nhạy cảm. Cần trả trạng thái lỗi hoặc chờ theo thiết kế, rồi cho phép client tiếp tục bằng cùng key khi hệ thống phục hồi.

## 13. Câu hỏi tự kiểm tra

1. Vì sao timeout không chứng minh thanh toán thất bại?
2. Vì sao một transaction cho mỗi request chưa đủ ngăn hai request cùng trừ tiền?
3. Vì sao cùng key nhưng khác fingerprint phải bị từ chối thay vì ghi đè?
4. Khi người dùng thay key cho cùng đơn hàng, cơ chế nào còn phải bảo vệ đơn hàng?
5. Vì sao request replay vẫn cần kiểm tra quyền theo đối tượng?
6. Vì sao outbox không tự bảo đảm cổng thanh toán chỉ thu tiền một lần?
7. Điều gì xảy ra nếu retry đến sau khi server đã xóa bản ghi key?

Một cách trả lời nhất quán là phân biệt ba trách nhiệm: key nhận diện ý định đang được gửi lại; transaction và phối hợp xử lý bảo vệ việc ghi nhận tác động; còn invariant, state machine và quyền theo đối tượng quyết định tác động nào được phép xảy ra. Thiết kế an toàn cần các trách nhiệm đó cùng hoạt động, kể cả khi request đến đồng thời hoặc kết quả lần gọi trước chưa rõ.
