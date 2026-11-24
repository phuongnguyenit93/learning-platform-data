# Webhook response handling

## 1. HTTP response là một phần của hợp đồng giao nhận

Webhook là cách một hệ thống chủ động gửi HTTP request để thông báo sự kiện hoặc chuyển một yêu cầu tới hệ thống khác. **Webhook response handling** gồm hai phía:

- Bên nhận quyết định lúc nào trả response và response đó xác nhận điều gì.
- Bên gửi quyết định ghi nhận, retry, dừng hay đối chiếu dựa trên response và tình trạng kết nối.

Nếu hai phía hiểu khác nhau về “thành công”, một response có thể làm mất sự kiện hoặc gây tác động trùng. Ví dụ, bên nhận trả 200 trước khi lưu message bền vững rồi tiến trình chết; bên gửi ngừng retry nhưng đơn hàng không bao giờ được xử lý. Ở chiều ngược lại, bên nhận đã commit hoàn tiền nhưng response bị mất; bên gửi retry và có thể làm hoàn tiền lần nữa nếu bên nhận thiếu idempotency.

Trong bảo mật logic nghiệp vụ, response handling phải giữ các bất biến như không đánh dấu đơn đã trả tiền khi thiếu căn cứ, không bỏ bước phê duyệt, không lặp tác động tài chính và không mở quyền từ nội dung response không đáng tin.

Bài này dùng các mã HTTP và tên sự kiện làm ví dụ thiết kế. Cách retry, mã thành công và response body thực tế phải được xác định theo hợp đồng của bên tích hợp; không có một quy tắc áp dụng nguyên trạng cho mọi nhà cung cấp webhook.

## 2. Phân biệt ba loại kết quả

| Lớp kết quả | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Vận chuyển HTTP | Bên gửi có nhận được response hợp lệ không? | Có status line hay gặp timeout? |
| Tiếp nhận webhook | Bên nhận đã chấp nhận và lưu sự kiện theo hợp đồng chưa? | Inbox và công việc xử lý đã commit |
| Nghiệp vụ | Tác động yêu cầu đã xảy ra chưa? | Đơn đã chuyển trạng thái, tiền đã được ghi nhận |

Một 2xx có thể chỉ xác nhận tiếp nhận bền vững nếu endpoint xử lý bất đồng bộ. Nó không tự chứng minh mọi tác động nghiệp vụ đã hoàn tất.

Một timeout chỉ cho biết bên gửi chưa có kết quả đúng hạn. Nó không chứng minh bên nhận chưa xử lý. Một 5xx cũng không chắc là “chưa tạo tác động”: lỗi có thể xuất hiện sau commit khi dựng response.

### 2.1. Định nghĩa rõ ý nghĩa ACK

Trong bài này, ACK là response mà bên gửi coi là đã xác nhận giao nhận theo hợp đồng. Đây là cách gọi ở mức ứng dụng, không phải bảo đảm rằng HTTP và database cùng tham gia một transaction.

Có hai mô hình phổ biến:

1. **Xử lý đồng bộ:** trả ACK sau khi tác động nghiệp vụ và bằng chứng bắt buộc đã commit.
2. **Tiếp nhận bất đồng bộ:** trả ACK sau khi sự kiện và công việc xử lý đã được lưu bền vững; hệ thống nhận chịu trách nhiệm retry nội bộ.

Không trộn hai mô hình trong vận hành. Nếu bên nhận chọn ACK sớm sau lưu bền vững, lỗi ở worker về sau không thể được giải quyết bằng giả định rằng bên gửi sẽ tự giao lại.

### 2.2. HTTP thành công không cấp thêm quyền

Bên gửi không được dùng một response tùy ý để mở rộng quyền của endpoint. Ví dụ, nếu webhook chỉ thông báo “đơn đã tạo”, response body `{"refund": true}` không phải căn cứ tự động hoàn tiền.

Nếu sản phẩm thật sự cần một giao thức hai chiều hoặc quyết định đồng bộ từ đối tác, cần hợp đồng, xác thực, schema, quyền và state machine riêng cho điều đó. Không ngầm biến body trả về thành command quản trị.

## 3. Các bất biến cần giữ

| Bất biến | Hệ quả đối với thiết kế |
| --- | --- |
| Không ACK việc chưa được đảm nhận bền vững | Chỉ trả thành công sau mốc commit tương ứng |
| Không dùng HTTP status thay bằng chứng nghiệp vụ | Trạng thái thanh toán/hoàn tiền có căn cứ riêng |
| Cùng sự kiện không tạo tác động trùng | Event ID ổn định, inbox và ràng buộc theo operation |
| Timeout không bị coi là chưa thực hiện | Retry cùng định danh hoặc đối chiếu theo hợp đồng |
| Response không mở rộng quyền của người gửi/nhận | Chỉ dùng trường và hành vi đã được cho phép |
| Tenant và tài nguyên luôn được đối chiếu | Không tin ID đối tượng chỉ vì chữ ký request hợp lệ |
| Replay không bỏ phê duyệt hoặc trạng thái | Áp dụng lại các kiểm tra cần thiết trước tác động mới |
| Công việc đã ACK không mất khi tiến trình chết | Có hàng đợi/outbox bền vững và quy trình phục hồi |
| Phân loại kết quả có thể kiểm chứng | Tách tiếp nhận, tác động, retry và trạng thái chưa rõ |

Các bất biến này cần đúng cả khi hai delivery cùng đến, response bị mất, endpoint trả nội dung bất thường hoặc người vận hành replay thủ công.

## 4. Bên nhận: xác định mốc được phép trả thành công

### 4.1. ACK sau xử lý đồng bộ

Luồng minh họa:

~~~text
Nhận request có giới hạn kích thước.
Xác minh nguồn và nội dung theo hợp đồng.
Kiểm tra schema, tenant, đối tượng và điều kiện nghiệp vụ.
Mở transaction cho tác động:
  chống trùng;
  cập nhật dữ liệu;
  ghi kết quả và audit/outbox.
COMMIT.
Trả response thành công.
~~~

Mô hình này thích hợp khi xử lý đủ ngắn trong giới hạn thời gian tích hợp. Không giữ request mở quá lâu cho nhiều bước mạng không kiểm soát được.

Nếu transaction rollback, không trả thành công với ý nghĩa “nghiệp vụ đã hoàn tất”. Nếu kết quả commit chưa rõ do mất kết nối database, cần xác định qua cùng operation ID khi xử lý lại, không tự tạo operation mới.

### 4.2. ACK sau tiếp nhận bất đồng bộ

~~~mermaid
sequenceDiagram
    participant S as Bên gửi
    participant E as Webhook endpoint
    participant DB as Database
    participant W as Worker

    S->>E: Sự kiện với định danh ổn định
    E->>E: Giới hạn, xác minh nguồn, kiểm tra schema
    E->>DB: BEGIN, ghi inbox và công việc bền vững
    E->>DB: COMMIT
    DB-->>E: Đã commit
    E-->>S: ACK theo hợp đồng
    W->>DB: Đọc công việc đã commit
    W->>DB: Kiểm tra nghiệp vụ, tạo tác động, ghi kết quả/audit
~~~

Phần lưu bền vững phải đủ để khôi phục xử lý, gồm nội dung cần thiết hoặc tham chiếu có khả năng truy xuất phù hợp và ngữ cảnh đã xác minh. Một ID trỏ tới dữ liệu chỉ nằm trong bộ nhớ không đáp ứng điều đó.

Có thể ghi inbox và processing outbox trong cùng transaction rồi relay sang queue. Không commit inbox rồi publish riêng mà thiếu cơ chế phục hồi nếu tiến trình chết giữa hai bước.

### 4.3. Những cách ACK quá sớm

~~~text
Đưa request vào danh sách trong RAM -> trả 200.
Bắt đầu một thread nền -> trả 200.
Ghi log "received" -> trả 200.
Gửi queue nhưng không biết đã được lưu bền vững -> trả 200.
~~~

Các cách trên không đủ nếu hợp đồng ACK đòi hỏi tiếp nhận bền vững. Khi tiến trình chết, bên gửi có thể đã dừng retry trong khi không còn công việc để xử lý.

Một response 200 kèm body `{"error": "database unavailable"}` cũng dễ gây mất dữ liệu nếu bên gửi chỉ dùng status để xác định thành công. Status và body phải cùng diễn đạt một hợp đồng nhất quán.

## 5. Bên nhận: chọn status theo tình trạng thật và hợp đồng

| Tình huống | Hướng phản hồi minh họa | Điều phải giữ |
| --- | --- | --- |
| Sự kiện hợp lệ, đã tiếp nhận bền vững | 200, 202 hoặc 204 nếu bên gửi chấp nhận | Không ngầm nói nghiệp vụ đã hoàn tất nếu mới enqueue |
| Tác động đồng bộ đã commit | Mã thành công theo hợp đồng | Không còn bước bắt buộc chưa được đảm nhận |
| Bản sao của sự kiện đã tiếp nhận bền vững | ACK phù hợp với hợp đồng | Không xử lý lại tác động hoặc tạo công việc trùng |
| Nguồn/chữ ký không hợp lệ | Phản hồi lỗi xác thực theo hợp đồng, thường 401/403 | Không tạo nghiệp vụ và không tiết lộ secret |
| Body không hợp lệ hoặc thiếu trường bắt buộc | Lỗi đầu vào, có thể là 400/422 | Không ghi nhận như đã xử lý thành công |
| Cùng event ID nhưng nội dung xung đột | Lỗi xung đột, có thể là 409 | Không dùng kết quả cũ để hợp thức hóa nội dung mới |
| Chưa thể lưu bền vững do lỗi tạm thời | Lỗi tạm thời như 503 theo hợp đồng | Không ACK việc chưa đảm nhận |
| Hết khả năng nhận thêm công việc | Từ chối theo chính sách tải, có thể 429/503 | Giới hạn retry và thời gian chờ phải phối hợp |
| Event hợp lệ nhưng không thuộc loại cần xử lý | Có thể ACK và ghi rõ bỏ qua nếu hợp đồng cho phép | Không đánh đồng với schema lỗi hoặc sự kiện bắt buộc bị mất |
| Đã nhận bền vững nhưng nghiệp vụ bị từ chối về sau | ACK chỉ xác nhận tiếp nhận; lưu kết quả nghiệp vụ riêng | Worker và quy trình vận hành chịu trách nhiệm theo dõi |

Các mã trong bảng không quyết định lịch retry của phía gửi. Có bên retry mọi response không thành công, có bên phân loại khác; endpoint cần tuân thủ hợp đồng thực tế và theo dõi các lỗi lặp lại.

### 5.1. Bản sao đang xử lý có hai trường hợp khác nhau

**Đã có receipt bền vững và worker đang chạy:** có thể ACK bản sao nếu hợp đồng là tiếp nhận bất đồng bộ. Trách nhiệm xử lý đã thuộc hệ thống nhận.

**Một request khác đang giữ transaction nhưng chưa commit receipt:** chưa có căn cứ để xác nhận bền vững. Có thể chờ ngắn rồi đọc kết quả đã commit, hoặc trả lỗi tạm thời theo thiết kế. Không chỉ thấy một flag trong RAM rồi trả thành công.

Nếu unique constraint báo tranh chấp, phải xử lý transaction đúng, đọc trạng thái đã commit và đối chiếu nội dung. Không bắt mọi lỗi unique rồi trả 200.

### 5.2. Không biến lỗi vĩnh viễn thành thành công âm thầm

Trả 200 để “ngừng bị retry” có thể che mất sự kiện cần xử lý. Nếu chủ động tiếp nhận một sự kiện lỗi để cách ly, phải lưu bền vững nó hoặc bằng chứng cần thiết và ghi kết quả cách ly rõ ràng.

Với request chưa xác thực, không coi nó là sự kiện nghiệp vụ đã tiếp nhận. Có thể ghi một sự kiện bảo mật riêng, nhưng phải tránh lưu không giới hạn dữ liệu do bên ngoài gửi.

Sự kiện xác thực hợp lệ nhưng không liên quan có thể được bỏ qua theo hợp đồng đã định. Điều này khác với nuốt lỗi parser hoặc bỏ một loại sự kiện mới mà nghiệp vụ vẫn cần.

### 5.3. Response body nên nhỏ và ít tiết lộ

Một response minh họa cho tiếp nhận bất đồng bộ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "eventId": "event-781",
  "receiptStatus": "accepted"
}
~~~

`accepted` ở đây có nghĩa đã tiếp nhận bền vững, không phải tiền đã chuyển hoặc đơn đã giao. Nếu tích hợp không cần body, không thêm dữ liệu nhạy cảm chỉ để tiện debug.

Response lỗi không nên trả stack trace, secret ký, cấu hình nội bộ, dữ liệu tài khoản hoặc chi tiết tài nguyên ngoài quyền. Nếu cần mã hỗ trợ điều tra, trả một reference không tiết lộ nội dung và lưu lý do chi tiết ở vùng audit có kiểm soát.

## 6. Mã giả Java cho endpoint tiếp nhận bất đồng bộ

Ví dụ sau dùng inbox và processing outbox cùng database. Hàm xác minh dùng đúng nội dung request theo hợp đồng webhook; chi tiết mật mã phụ thuộc tích hợp.

~~~java
HttpResponse receiveWebhook(
        RawHttpRequest request,
        TrustedEndpointConfiguration endpoint) {

    RawBody body = request.readBodyWithinLimit(endpoint.maxBodyBytes());

    VerifiedWebhook verified = verifier.verify(
            endpoint,
            request.allowedVerificationHeaders(),
            body);

    SupportedEvent event = schemas.parseVerified(verified);

    // Tenant được ràng buộc với endpoint/nguồn đã xác minh,
    // rồi đối chiếu với tài nguyên, không chỉ lấy từ payload.
    TrustedReceiptContext context = receiptPolicy.bind(
            endpoint, verified, event);

    ReceiptResult result = database.transaction(tx -> {
        ReceiptClaim claim = inbox.claimOrLoad(
                tx,
                context.sourceNamespace(),
                event.eventId(),
                fingerprintOfCanonicalEvent(event));

        if (claim.alreadyAccepted()) {
            claim.requireSameFingerprint(
                    fingerprintOfCanonicalEvent(event));
            return ReceiptResult.previouslyAccepted(claim.receiptId());
        }

        receiptPolicy.requireAdmissible(tx, context, event);

        StoredReceipt receipt = inbox.accept(
                tx, claim, context, event.requiredProcessingData());

        processingOutbox.append(
                tx, ProcessWebhook.from(receipt));

        auditOutbox.append(
                tx, WebhookAccepted.from(receipt, context));

        return ReceiptResult.accepted(receipt.id());
    });

    // transaction() chỉ trả thành công sau commit.
    return responseContract.accepted(result);
}
~~~

Các điều kiện của mã giả:

1. Nội dung được parse là nội dung đã được xác minh. Không xác minh một bản byte rồi xử lý bản khác đã bị biến đổi.
2. Namespace và event ID phải có phạm vi đúng theo hợp đồng nguồn; ID trần có thể trùng giữa tài khoản hoặc môi trường.
3. Fingerprint ràng buộc với nội dung cần so khớp, theo quy tắc ổn định. Không đưa chữ ký hoặc timestamp vận chuyển thay đổi hợp lệ qua mỗi delivery vào fingerprint nếu chúng không thuộc định danh nội dung sự kiện.
4. Inbox có unique constraint và cách xử lý cạnh tranh rõ. Lỗi lưu trữ không bị bắt chung rồi đổi thành thành công.
5. Receipt lưu đủ ngữ cảnh để worker tiếp tục sau restart. Dữ liệu nhạy cảm chỉ được giữ ở mức cần thiết, với quyền truy cập và thời hạn phù hợp.
6. `requireAdmissible` kiểm tra điều kiện tiếp nhận, không thay mọi điều kiện tạo tác động. Worker vẫn phải đối chiếu trạng thái nghiệp vụ, quyền và bất biến cần thiết.
7. Processing outbox và audit/outbox cùng commit với receipt. Các relay có thể chuyển lại, nên consumer vẫn cần chống trùng.
8. Nhánh bản sao chỉ ACK khi receipt cũ thực sự đã được tiếp nhận bền vững và nội dung khớp.

HTTP exception mapping nằm ngoài mã giả: lỗi xác thực, xung đột và lỗi tạm thời cần response theo hợp đồng riêng. Một khối `catch (Exception) { return ok(); }` sẽ phá vỡ các điều kiện này.

## 7. Bên gửi: diễn giải response bằng một hợp đồng rõ ràng

### 7.1. Ma trận xử lý minh họa

| Quan sát của bên gửi | Cách xử lý cần được định nghĩa | Không được suy ra |
| --- | --- | --- |
| Status thành công được hợp đồng chấp nhận | Ghi nhận ACK; kiểm tra body nếu hợp đồng yêu cầu | Mọi nghiệp vụ bên nhận đã hoàn tất |
| Status thành công nhưng body bắt buộc không hợp lệ | Lỗi giao thức, retry/đối chiếu theo hợp đồng | Tự mặc định thành công hoặc chưa thực hiện |
| 400/422 do dữ liệu không được chấp nhận | Thường cần sửa nguyên nhân hoặc xử lý thủ công theo hợp đồng | Mọi bên nhận đều ngừng retry cùng một cách |
| 401/403 | Kiểm tra cấu hình/quyền/chữ ký, giới hạn retry | Được tự bỏ xác thực hoặc đổi sang credential mạnh hơn |
| 404/410 | Xem chính sách endpoint không tồn tại/ngừng hoạt động | Có thể xóa mọi lịch sử hoặc tự chuyển sang URL khác |
| 409 | Diễn giải theo mã và nghĩa đã thống nhất | Mọi 409 đều là duplicate thành công |
| 429 | Lên lịch theo giới hạn tải và hợp đồng | Có thể retry ngay không giới hạn |
| 5xx | Có thể retry nếu an toàn và được chính sách cho phép | Bên nhận chắc chắn chưa tạo tác động |
| 3xx | Xử lý theo chính sách redirect được kiểm soát | URL mới tự được tin ngang endpoint cũ |
| Timeout/reset/mất response | Ghi kết quả chưa rõ; retry cùng định danh hoặc đối chiếu | Không có tác động ở phía nhận |

Bảng này là khung thiết kế. Một tích hợp có thể quy định khác, nhưng phải nhất quán và có kiểm thử.

Nếu bên nhận dùng 200 để xác nhận tiếp nhận, không yêu cầu nó trả thêm kết quả nghiệp vụ ngoài hợp đồng. Nếu hợp đồng chỉ dùng status, một body tùy ý không được phép đổi nghĩa của status theo một quy tắc do endpoint tự sáng tạo.

### 7.2. Không dùng một cờ success cho mọi trạng thái

Phía gửi có thể lưu riêng:

~~~text
delivery_state: ACKNOWLEDGED
remote_receipt_state: ACCEPTED nếu hợp đồng cung cấp
remote_business_state: UNKNOWN nếu chưa có căn cứ riêng
last_http_status: 200
~~~

Một giao nhận đã được ACK vẫn có thể dẫn tới kết quả nghiệp vụ bị từ chối hợp lệ. Khi cần biết kết quả cuối, dùng API tra cứu, sự kiện kết quả hoặc cơ chế đối chiếu được xác thực.

Ngược lại, `delivery_state: RETRY_WAIT` không chứng minh nghiệp vụ bên nhận chưa hoàn tất. Nó chỉ mô tả điều phối giao nhận theo dữ liệu hiện có.

### 7.3. Response body là dữ liệu không đáng tin

Ngay cả endpoint đã được cấu hình cũng có thể trả nội dung lỗi, bị chiếm quyền hoặc do proxy thay đổi. Bên gửi cần:

- Giới hạn số byte đọc, thời gian đọc và kích thước sau giải nén nếu có.
- Chỉ parse content type/schema được hỗ trợ khi thật sự cần.
- Kiểm tra tham chiếu event/receipt mà hợp đồng yêu cầu, thay vì tin một chuỗi `success` bất kỳ.
- Không thực thi script, class, template hoặc command từ body.
- Không dùng body để đổi tenant, số tiền, người nhận hoặc quyền nghiệp vụ.
- Không ghi nguyên body vào log hoặc hiển thị như HTML an toàn.

Nếu cần lưu một phần response để chẩn đoán, dùng trích đoạn có giới hạn, giảm dữ liệu và escape đúng khi hiển thị. Một digest có thể hỗ trợ so sánh response, nhưng không thay nội dung cần thiết cho việc giải thích hoặc xác thực nguồn.

### 7.4. Redirect cần được kiểm soát

Không tự theo mọi redirect của webhook có credential hoặc dữ liệu nhạy cảm. URL mới có thể trỏ ra ngoài đích đã đăng ký hoặc tới tài nguyên mạng nội bộ.

Nếu sản phẩm cho redirect, cần xác minh đích theo chính sách endpoint, kiểm soát số lần chuyển, phương thức HTTP và việc chuyển tiếp credential. Không gửi secret hoặc header xác thực sang một đích chưa được cho phép.

Đổi URL webhook nên là một thao tác cấu hình có quyền và audit. Response 3xx không tự thay thế quy trình đó.

## 8. Retry sau response lỗi hoặc không có response

### 8.1. Giữ định danh sự kiện ổn định

Một chuỗi giao nhận minh họa:

~~~text
event_id: event-781
delivery_attempt_id: attempt-1 -> timeout
delivery_attempt_id: attempt-2 -> 503
delivery_attempt_id: attempt-3 -> ACK
~~~

Cả ba attempt vẫn là cùng một sự kiện. Nếu tạo event ID mới ở mỗi retry, bên nhận có thể không nhận ra bản sao.

Chữ ký, timestamp hoặc định danh của từng delivery có thể cần thay theo hợp đồng bảo mật, nhưng không làm thay đổi ý nghĩa và định danh nghiệp vụ của sự kiện. Bên nhận phải phân biệt dữ liệu ổn định để chống trùng với thông tin vận chuyển thay đổi hợp lệ.

Fingerprint trong ví dụ endpoint nên được tính từ biểu diễn chuẩn của các trường sự kiện bất biến cần so khớp: type, tài nguyên, nội dung nghiệp vụ và các phạm vi liên quan. Nó không thay thế việc xác minh nguồn.

### 8.2. Backoff, jitter và Retry-After

Một chính sách minh họa:

~~~text
cap(n) = min(max_delay, base_delay * 2^(n - 1))
jitter_delay = random_uniform(0, cap(n))
~~~

Trong đó `n = 1` là lần retry đầu tiên. Cần giới hạn phép tính, số attempt và tổng thời gian giao nhận.

Nếu hợp đồng yêu cầu tôn trọng `Retry-After`, chỉ dùng giá trị hợp lệ theo định dạng được hỗ trợ và nguồn response đã chấp nhận. Không parse tùy tiện một chuỗi bất kỳ.

Thời điểm retry không được sớm hơn mốc chờ bắt buộc mà chính sách chấp nhận. Nếu thời gian chờ vượt deadline hoặc giới hạn vận hành, chuyển sang trạng thái dừng/chờ xử lý phù hợp thay vì âm thầm retry sớm hơn yêu cầu.

Backoff và jitter giảm tải; chúng không chống được tác động tài chính trùng.

### 8.3. Timeout phải có giới hạn theo từng giai đoạn

Đặt giới hạn kết nối, chờ response, đọc body và tổng thời gian attempt phù hợp. Một endpoint trả header nhanh nhưng giữ body không kết thúc không được chiếm worker vô hạn.

Phân biệt tín hiệu timeout với kết quả nghiệp vụ. Khi bên gửi hết thời gian chờ, handler phía nhận vẫn có thể tiếp tục và commit.

Cũng cần kiểm soát retry tự động ở HTTP client, proxy và worker. Nhiều tầng cùng retry có thể nhân số lần gọi mà tầng điều phối không quan sát đầy đủ.

### 8.4. Khi nào không nên retry tự động?

- Nội dung không hợp lệ cần sửa theo quy trình, thay vì gửi lại vô hạn.
- Credential hoặc quyền sai cần xử lý cấu hình, không được bỏ kiểm tra để “gửi cho được”.
- Đã hết budget hoặc thời hạn giao nhận.
- Tác động phía nhận đang chưa rõ và không có bảo đảm chống trùng/đối chiếu đủ dùng.
- Endpoint hoặc đích mới chưa được xác minh.
- Kết quả cho thấy cần can thiệp nghiệp vụ riêng.

Dừng retry không đồng nghĩa tác động bên nhận chưa xảy ra. Giữ trạng thái chưa rõ và tham chiếu cần thiết để đối chiếu.

Với tác động nhạy cảm mà bên nhận không hỗ trợ idempotency hoặc tra cứu đáng tin, không thể bảo đảm an toàn chỉ bằng vòng lặp POST phía gửi.

## 9. Lưu trạng thái giao nhận một cách bền vững

### 9.1. State machine phía gửi

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> IN_FLIGHT: Claim một attempt
    RETRY_WAIT --> IN_FLIGHT: Đến thời điểm thử lại
    IN_FLIGHT --> ACKNOWLEDGED: ACK hợp lệ theo hợp đồng
    IN_FLIGHT --> RETRY_WAIT: Có thể retry an toàn
    IN_FLIGHT --> STOPPED: Lỗi hoặc deadline theo chính sách
    IN_FLIGHT --> NEEDS_REVIEW: Kết quả chưa rõ, không đủ căn cứ retry
    RETRY_WAIT --> STOPPED: Hết budget hoặc bị dừng
    NEEDS_REVIEW --> RETRY_WAIT: Đã đối chiếu và được phép thử lại
    NEEDS_REVIEW --> ACKNOWLEDGED: Có bằng chứng tiếp nhận đủ dùng
~~~

`ACKNOWLEDGED` trong sơ đồ là xác nhận giao nhận theo hợp đồng. `STOPPED` là dừng gửi tự động, không phải kết luận chưa từng có tác động ở bên nhận.

Nếu một event được gửi tới nhiều subscription, cần theo dõi kết quả từng đích. Một endpoint trả thành công không xác nhận thay cho các endpoint còn lại.

### 9.2. Ghi ý định trước lời gọi mạng

Bên gửi nên có một bản ghi bền vững về event và delivery cần thực hiện, thường xuất phát từ outbox cùng transaction với sự kiện nghiệp vụ.

Trước khi gửi, lưu attempt và claim phù hợp. Sau lời gọi, lưu kết quả quan sát, phân loại và lịch tiếp theo. Không giữ transaction database mở để chờ toàn bộ HTTP rồi giả định nó bao phủ tác động ở phía nhận.

Nếu nhận được 2xx nhưng tiến trình chết trước khi lưu trạng thái ACK, worker sau có thể gửi lại. Đó là lý do cả phía nhận lẫn phía gửi phải giữ định danh ổn định và xử lý bản sao.

### 9.3. Response đến muộn không được làm lùi trạng thái

Ví dụ:

~~~text
Attempt 1 chạy chậm.
Attempt 2 được claim sau khi thời hạn sở hữu của attempt 1 hết.
Attempt 2 nhận ACK và lưu ACKNOWLEDGED.
Attempt 1 nhận lỗi muộn rồi cố đặt RETRY_WAIT.
~~~

Một cập nhật không kiểm tra attempt/version có thể làm hệ thống gửi lại dù đã ACK.

Cập nhật điều phối phải kiểm tra claim, version và chuyển trạng thái được phép. Kết quả đến muộn vẫn có thể được ghi audit, nhưng không được tùy ý ghi đè trạng thái mới.

Nếu cấu hình endpoint thay đổi, cần ràng buộc kết quả với đúng delivery và phiên bản đích. Response của URL cũ không tự xác nhận giao nhận cho URL mới.

### 9.4. Mã giả phân loại và lưu kết quả

~~~java
DeliveryAttempt attempt = deliveryStore.claimDueAttempt(now);

// Đích và credential đã được kiểm tra theo cấu hình được phép.
// HTTP client không tự redirect hoặc retry ngoài chính sách điều phối.
HttpObservation observed = httpClient.sendWithinLimits(
        attempt.endpointConfiguration(),
        attempt.stableEvent(),
        attempt.deliveryMetadata());

HandlingDecision decision = responseContract.classify(
        observed,
        attempt.stableEvent().reference(),
        attempt.retryBudget());

database.transaction(tx -> {
    DeliveryTask task = deliveryStore.lockForUpdate(
            tx, attempt.deliveryTaskId());

    if (!task.acceptsResultFrom(
            attempt.claimVersion(),
            attempt.endpointConfigurationVersion())) {
        audit.appendLateAttemptObservation(tx, attempt, observed);
        return;
    }

    task.applyAllowedTransition(decision);
    deliveryStore.save(tx, task);
    audit.appendDeliveryObservation(tx, attempt, observed, decision);
});
~~~

`classify` chỉ diễn giải response theo hợp đồng có sẵn. Nó không thực thi command tùy ý lấy từ body.

Mã giả không biến request HTTP thành một transaction nguyên tử với trạng thái lưu cục bộ. Việc phục hồi vẫn phải chấp nhận khả năng gửi lại sau khi response hoặc kết quả lưu bị mất.

## 10. Response không thay các kiểm tra nghiệp vụ

### 10.1. Request được xác thực vẫn phải được đối chiếu

Một webhook thanh toán có chữ ký hợp lệ cần được ràng buộc với đúng tài khoản nguồn, tenant, đơn hàng, payment intent, số tiền, đồng tiền và trạng thái.

Chữ ký chứng minh một nguồn theo cơ chế xác minh, không tự chứng minh mọi mối quan hệ nghiệp vụ. Một capture không được áp dụng cho hai đơn chỉ vì nó xuất hiện dưới hai event ID khác nhau.

Với xử lý đồng bộ, kiểm tra và thay đổi cần ở trong cơ chế transaction/cạnh tranh phù hợp. Với xử lý bất đồng bộ, receipt hợp lệ không miễn các kiểm tra trước tác động ở worker.

### 10.2. Event ID và operation ID bảo vệ các mức khác nhau

- Event ID giúp nhận ra cùng sự kiện được chuyển lại.
- Operation ID hoặc định danh giao dịch thực tế giúp ngăn cùng tác động xuất hiện dưới nhiều sự kiện.
- Delivery attempt ID chỉ phục vụ từng lần gửi, không phải khóa tác động.
- Fingerprint phát hiện nội dung khác dưới cùng một định danh theo hợp đồng.

Nếu dùng event ID mới để hoàn một refund request đã hoàn, idempotency theo delivery không đủ. Cần bất biến như một yêu cầu hoàn chỉ tạo một hiệu ứng ghi có hợp lệ và tổng hoàn không vượt phần được phép.

### 10.3. Response lỗi không được mở đường bỏ phê duyệt

Một retry không được tự đổi trạng thái `PENDING_APPROVAL` thành `APPROVED`, đổi người nhận hoặc nâng quyền worker để vượt qua lỗi.

Nếu người vận hành cần sửa dữ liệu, đó là thay đổi nghiệp vụ có quyền và audit riêng. Replay giữ cùng ý nghĩa của operation, không phải một cách hợp thức hóa payload mới.

Nếu operation tiếp tục sau khi người khởi tạo mất quyền, phải có chính sách rõ về cam kết đã chấp nhận và quyền hiện tại. Timeout hoặc retry không tự chọn được chính sách đó.

### 10.4. Sự kiện đến sai thứ tự

Một webhook đến muộn có thể được tiếp nhận nhưng không còn được phép chuyển đối tượng về trạng thái cũ. Ví dụ, xác nhận capture đến sau khi đơn bị hủy cần đối chiếu hoặc xử lý theo quy trình của đơn đã hủy.

Không dùng thứ tự nhận HTTP hoặc timestamp đơn lẻ để ghi đè state machine. ACK một sự kiện đã được lưu để đối chiếu khác với tự áp dụng nó thành công vào đối tượng.

Nếu hệ thống bỏ qua một sự kiện vì đã được phản ánh hợp lệ hoặc không còn tác động theo hợp đồng, cần ghi kết quả rõ để người vận hành phân biệt với mất dữ liệu.

## 11. Audit và vận hành

### 11.1. Ghi đủ để giải thích response

Thông tin hữu ích gồm:

~~~text
event_id, issuer/source namespace
business_operation_id nếu có
subscription_id / endpoint configuration version
delivery_attempt_id, claim_version
verified tenant và tài nguyên khi đã xác định
request_started_at, response_observed_at, elapsed_time
http_status nếu nhận được
transport_error_category
response_classification
receipt_id / effect_id khi có căn cứ
retry_count, next_attempt_at, stop_reason
correlation_id / trace_id nếu có
~~~

Tách nguồn tự khai khỏi nguồn đã xác minh. Không ghi tenant tự khai thành tenant có trách nhiệm trước khi đối chiếu.

Không ghi secret, chữ ký đầy đủ nếu không cần, token xác thực hoặc nguyên request/response vào log. Một response nhỏ vẫn có thể chứa dữ liệu nhạy cảm hoặc nội dung chèn vào trang quản trị.

### 11.2. Các tín hiệu cần theo dõi

- Tỷ lệ timeout và 5xx theo endpoint.
- Tăng đột biến 401/403 sau xoay vòng credential.
- Nhiều lần ACK nhưng receipt hoặc công việc nội bộ thiếu.
- Inbox đã tiếp nhận nhưng worker không tiến triển.
- Cùng event ID xuất hiện với nội dung khác.
- Retry budget cạn, delivery chưa rõ kết quả hoặc DLQ tăng.
- Response body vượt giới hạn, redirect bất thường hoặc đích bị chặn.
- Một operation có nhiều effect trái bất biến.

Không đánh giá chất lượng nghiệp vụ chỉ từ tỷ lệ 2xx. Với tiếp nhận bất đồng bộ, cần theo dõi cả độ trễ xử lý, kết quả cuối và khả năng phục hồi sau ACK.

### 11.3. Replay và đối chiếu

Replay phải có quyền theo tenant, loại sự kiện và endpoint. Giữ event/operation ID, ghi người yêu cầu và lý do; không sửa payload rồi coi như cùng retry hợp lệ.

Nếu kết quả phía nhận chưa rõ, tìm receipt/effect qua cơ chế tra cứu đã thống nhất. Không xóa bản ghi chống trùng để buộc chạy lại một tác động tài chính.

Khi đổi cấu hình hoặc sửa lỗi, phân biệt “gửi lại cùng sự kiện” với “tạo một command mới”. Các tác động đã xảy ra cần giữ lịch sử và quy trình đính chính riêng.

## 12. Ví dụ xuyên suốt: webhook thanh toán bị mất response

Giả sử webhook `event-781` xác nhận capture cho đơn `order-81`. Bên nhận chọn mô hình tiếp nhận bất đồng bộ và hợp đồng quy định 200 là đã tiếp nhận bền vững.

| Thời điểm | Điều xảy ra | Kết luận đúng |
| --- | --- | --- |
| T1 | Bên gửi tạo delivery cho event-781 | Có công việc cần giao, chưa có ACK |
| T2 | Bên nhận xác minh, ghi inbox và processing outbox | Sau commit, đã đảm nhận xử lý |
| T3 | Bên nhận gửi 200 nhưng kết nối bị mất | Bên gửi chưa biết kết quả; receipt vẫn tồn tại |
| T4 | Worker đối chiếu capture và commit trạng thái đơn | Nghiệp vụ đã tạo tác động theo bằng chứng riêng |
| T5 | Bên gửi retry cùng event ID | Đây là lần giao lại, không phải thanh toán mới |
| T6 | Bên nhận thấy receipt cũ, nội dung khớp, trả ACK | Không tạo công việc/tác động mới |
| T7 | Bên gửi nhận ACK và lưu kết quả | Giao nhận được xác nhận |

Nếu tiến trình bên nhận chết sau T2, worker phục hồi từ dữ liệu bền vững. Nếu worker chết sau T4 nhưng trước khi cập nhật một trạng thái vận chuyển riêng, ràng buộc operation/effect vẫn ngăn áp dụng capture lần nữa.

### 12.1. Nếu lỗi xảy ra trước commit receipt

Bên nhận không được trả thành công như thể đã đảm nhận công việc. Có thể trả lỗi tạm thời theo hợp đồng để bên gửi retry.

Nếu kết nối tới database đứt khi đang xác nhận commit, lần retry cùng event ID giúp xác định receipt đã tồn tại hay chưa. Không dùng ID mới để tránh việc phải xác định trạng thái cũ.

### 12.2. Nếu dữ liệu nghiệp vụ không hợp lệ

Giả sử event hợp lệ về nguồn và schema nhưng số tiền không khớp đơn. Trong mô hình bất đồng bộ, 200 có thể đã xác nhận tiếp nhận, còn worker ghi kết quả bị từ chối hoặc cần đối chiếu.

Đơn không được chuyển sang đã trả chỉ để làm kết quả “khớp với HTTP 200”. Kết quả nghiệp vụ được phản ánh qua trạng thái nội bộ và kênh tra cứu/thông báo đã thiết kế.

Nếu bên tích hợp cần response đồng bộ quyết định nghiệp vụ, phải chọn hợp đồng tương ứng ngay từ đầu; không dùng cùng một mã thành công với hai ý nghĩa mâu thuẫn.

### 12.3. Nếu endpoint trả nội dung nguy hiểm

Bên nhận có thể là một endpoint khách hàng cấu hình. Nó trả 200 với một trang HTML chứa nội dung chèn script hoặc một body rất lớn.

Bên gửi chỉ dùng status/body theo hợp đồng có giới hạn. Không render body như HTML trong trang quản trị, không thực thi nội dung và không tải toàn bộ body không giới hạn.

Nếu endpoint trả redirect tới một địa chỉ nội bộ, chính sách đích chặn việc tự theo. Response không được biến webhook sender thành công cụ truy cập mạng tùy ý.

## 13. Kiểm thử response handling

Cần kiểm tra cả response quan sát được và trạng thái bền vững. Một test chỉ assert `status == 200` không chứng minh tiếp nhận hoặc nghiệp vụ đúng.

| Tình huống | Điều cần kiểm chứng |
| --- | --- |
| Request hợp lệ, receipt và công việc đã commit | Chỉ sau mốc đó mới trả ACK tiếp nhận |
| Database lỗi trước commit receipt | Không ACK như đã tiếp nhận |
| Tiến trình chết sau ACK trong mô hình bất đồng bộ | Công việc vẫn phục hồi được |
| Ghi inbox thành công nhưng không ghi được processing outbox | Transaction không để receipt bị bỏ rơi |
| Hai delivery đồng thời cùng event/nội dung | Một receipt hợp lệ, không nhân bản công việc |
| Request đầu còn giữ transaction chưa commit | Request sau không xác nhận dựa trên trạng thái tạm |
| Cùng event ID nhưng nội dung khác | Xung đột bị chặn, không tạo tác động mới |
| Cùng event với chữ ký/timestamp delivery mới hợp lệ | Không bị nhầm thành một sự kiện nghiệp vụ mới |
| Transaction nghiệp vụ rollback | Không có tác động thành công hoặc audit thành công đã commit |
| Commit xong nhưng response bị mất | Retry cùng ID nhận kết quả/receipt cũ, không lặp tác động |
| Sender nhận 2xx rồi chết trước lưu ACK | Có thể gửi lại an toàn theo cùng event ID |
| 200 trong mô hình tiếp nhận bất đồng bộ | Không tự đặt remote business state thành hoàn tất |
| Body bắt buộc sai schema hoặc sai tham chiếu event | Xử lý lỗi giao thức theo hợp đồng, không suy đoán kết quả |
| 200 kèm body chứa command ngoài hợp đồng | Không thực thi hoặc mở quyền từ body |
| 401/403 lặp lại | Giới hạn retry và báo cấu hình; không bỏ xác thực |
| 409 từ endpoint | Chỉ coi là ACK nếu hợp đồng thực sự định nghĩa và kiểm chứng được nghĩa đó |
| 429/503 có thời gian chờ hợp lệ | Retry không sớm hơn mốc cần tôn trọng và vẫn giữ budget |
| Retry-After sai định dạng hoặc vượt deadline | Không ngủ vô hạn hoặc retry tùy tiện; xử lý theo chính sách |
| 5xx sau khi receiver đã commit | Sender không mặc định phía nhận chưa làm |
| Timeout trong khi receiver vẫn tiếp tục | Chống trùng vẫn giữ đúng tác động cuối |
| Attempt cũ trả lỗi sau attempt mới đã ACK | Không làm lùi trạng thái điều phối |
| Response của phiên bản endpoint cũ đến muộn | Không xác nhận thay cho đích mới |
| Một event có nhiều endpoint | Kết quả được theo dõi riêng từng delivery |
| 3xx sang đích không được phép | Không tự theo hoặc chuyển credential trái quyền |
| Body quá lớn, chậm hoặc giải nén phình lớn | Tài nguyên được giới hạn, worker không bị giữ vô hạn |
| Body chứa HTML/ký tự xuống dòng | Không chèn nội dung vào trang quản trị hoặc giả mạo log |
| Replay thủ công | Giữ định danh, kiểm tra quyền và có audit |
| Khác event ID nhưng cùng capture/refund operation | Bất biến nghiệp vụ vẫn ngăn tác động trùng |
| Hết retry budget nhưng kết quả chưa rõ | Trạng thái và quy trình đối chiếu còn được giữ |
| Luồng hợp lệ đầy đủ | Giao nhận và nghiệp vụ tiến triển đúng theo mô hình đã chọn |

Với lỗi giữa các bước, chủ động chèn điểm dừng trước commit, sau commit, trước gửi response và sau khi sender nhận response nhưng chưa lưu kết quả. Đọc trạng thái đã commit từ một kết nối độc lập.

Với timeout, mô phỏng cả “request chưa tới receiver” và “receiver đã commit nhưng response mất”. Nếu test luôn tạo timeout trước tác động, nó sẽ bỏ sót rủi ro quan trọng nhất.

Với concurrency, dùng điểm đồng bộ để hai request tranh chấp cùng event. Với retry, dùng đồng hồ điều khiển được để kiểm tra deadline và next-attempt thay vì chờ thời gian thực dài.

Với bảo mật response, kiểm tra dữ liệu thực sự được ghi log và hiển thị trên giao diện. Giới hạn ở HTTP client chưa đủ nếu tầng chẩn đoán vẫn thu thập nguyên body bằng đường khác.

## 14. Tiêu chí hoàn thành thiết kế

Một thiết kế response handling cần trả lời được:

- Mã thành công xác nhận tiếp nhận hay hoàn tất nghiệp vụ?
- Mốc bền vững nào phải đạt trước khi receiver trả ACK?
- Công việc sau ACK được phục hồi và retry nội bộ ra sao?
- Bản sao, nội dung xung đột và delivery đang chưa commit được xử lý thế nào?
- Sender phân loại từng nhóm response theo hợp đồng nào?
- Timeout, mất response và mất xác nhận commit có đường xác định kết quả không?
- Event ID và định danh tác động có giữ ổn định qua retry/replay không?
- Response body, redirect, credential và giới hạn tài nguyên được kiểm soát ra sao?
- Kết quả attempt cũ có thể ghi đè trạng thái mới không?
- Quyền theo đối tượng, phê duyệt và bất biến nghiệp vụ còn được giữ ở nơi tạo tác động không?

HTTP response cần diễn đạt đúng điều hệ thống đã đảm nhận hoặc đã hoàn tất. Khi ý nghĩa đó được gắn với dữ liệu bền vững, idempotency và quy tắc nghiệp vụ, webhook mới có thể phục hồi sau lỗi mà không làm mất sự kiện hoặc nhân bản tác động.
