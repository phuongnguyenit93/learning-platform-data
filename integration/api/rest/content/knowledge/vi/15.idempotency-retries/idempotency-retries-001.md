# Tính lũy đẳng đo tác động dự kiến, không đòi phản hồi giống hệt

## 1. Bài toán: một thao tác, nhiều lần gửi HTTP

Một khách hàng nhấn nút **“Thanh toán”** trong ứng dụng. Client gửi một request tới REST API; server xử lý thành công nhưng kết nối bị ngắt trước khi client nhận response. Vì không biết kết quả, client gửi lại cùng request. Nếu hệ thống thực hiện nghiệp vụ thêm lần nữa, khách hàng có thể bị trừ tiền hai lần.

Tình huống này thường được gọi là **ambiguous outcome**: phía client không phân biệt được “server chưa hề nhận”, “server đang xử lý”, “server đã hoàn tất nhưng response thất lạc”. Timeout ở client **không chứng minh** rằng thao tác phía server chưa diễn ra.

Để xây API có thể phục hồi khi retry, ta phải hiểu đúng **idempotency (tính lũy đẳng)**. Trong HTTP, một phương thức được coi là lũy đẳng nếu **tác động được yêu cầu (intended effect) của nhiều request giống hệt nhau lên server giống tác động của một request duy nhất**. Định nghĩa không yêu cầu các lần gọi phải trả **cùng HTTP status, cùng JSON, cùng ETag, cùng thời gian xử lý hoặc cùng response bytes**.

Bài này thuộc chương **Lũy đẳng và thử lại** của module **INTEGRATION_API_REST**. Nội dung kết nối ngữ nghĩa phương thức HTTP với thiết kế resource, URI, mã trạng thái, idempotency key, điều kiện cập nhật, lỗi API, hợp đồng OpenAPI và cách triển khai/kiểm thử bằng Java/Spring hoặc công nghệ tương đương.

Sau bài học, bạn có thể:

1. Giải thích vì sao **idempotent effect** khác với **identical response**.
2. Phân biệt **safe**, **idempotent**, **cacheable** và **exactly-once**.
3. Đánh giá các trường hợp **GET, PUT, DELETE, POST, PATCH** bằng trạng thái nghiệp vụ, không chỉ dựa trên status code.
4. Thiết kế retry an toàn khi timeout, mất response, client gửi trùng hoặc broker giao message lặp.
5. Xây hợp đồng **Idempotency-Key** với scope, fingerprint, trạng thái thực thi và TTL.
6. Dùng **transaction, unique constraint, outbox, If-Match** và đối soát để ngăn tác động lặp không mong muốn.
7. Viết contract tests và fault-injection tests chứng minh **kết quả nghiệp vụ** chỉ xảy ra theo số lần dự định.

> **Ý chính:** Một request lũy đẳng có thể trả **201 rồi 200**, **204 rồi 404**, hoặc **200 rồi 412** mà vẫn đúng về tác động, nếu nhiều lần gửi cùng một yêu cầu không tạo thêm thay đổi nghiệp vụ được client yêu cầu.

## 2. Định nghĩa ở cấp HTTP: “intended effect” là gì?

Theo **RFC 9110 — HTTP Semantics**, một request method là **idempotent** khi tác động dự kiến lên server của nhiều request **giống hệt nhau** sử dụng phương thức đó bằng tác động dự kiến của **một** request như thế.

Điều đó đặt trọng tâm vào **tác động được yêu cầu**, không phải mọi dấu vết quan sát được:

| Thứ cần so sánh | Có phải tiêu chí cốt lõi của HTTP idempotency? | Ví dụ |
|---|---|---|
| Trạng thái resource sau thao tác được yêu cầu | **Có** | PUT cùng biểu diễn hai lần vẫn cho trạng thái mong muốn |
| Hiệu ứng nghiệp vụ được client yêu cầu | **Có** | Một lần “đặt giá 99.000” không biến thành hai lần cộng tiền |
| HTTP status mỗi lần | **Không bắt buộc giống** | PUT tạo mới trả 201, PUT lặp trả 200/204 |
| Body phản hồi | **Không bắt buộc giống** | Server có requestId hoặc thông tin thời điểm khác |
| ETag/Last-Modified | **Không bắt buộc byte-identical** | Response được sinh trong điều kiện khác, miễn hợp đồng có nghĩa |
| Access log, metric, trace | **Không cần bất biến** | Mỗi lần gọi ghi một access log |
| Network latency, header Date | **Không bắt buộc giống** | Lần gọi sau có thời gian trễ khác |
| Thông báo/email hoặc thu tiền là kết quả trực tiếp được yêu cầu | **Phải xem là hiệu ứng cần bảo vệ** | Retry không được biến một lệnh thu tiền thành hai lần thu |

HTTP cho phép server **ghi log riêng từng request, lưu revision history hoặc ghi nhận tác dụng phụ nội bộ** ngay cả khi phương thức có ngữ nghĩa lũy đẳng. Tuy nhiên, không nên lấy điều này làm lý do để lặp lại một **tác động nghiệp vụ quan sát được** như thu phí, cộng điểm, gửi xác nhận hoặc đặt vé khi người dùng chỉ yêu cầu thao tác đó một lần.

### Mô hình hóa đơn giản

Giả sử một thao tác `f` tác động lên trạng thái nghiệp vụ `S`. Về trực giác, tính lũy đẳng được mô tả:

\[
f(f(S))=f(S).
\]

Đây là **mô hình tư duy**, không phải yêu cầu server phải trả cùng object hay toàn bộ trạng thái hạ tầng bằng nhau. Nếu `f` nghĩa là “đặt cờ active thành true”, áp dụng nhiều lần vẫn active=true. Nếu `f` nghĩa là “tăng số dư thêm 100”, áp dụng hai lần khác một lần.

Khi đánh giá ứng dụng phân tán, hãy xác định **ranh giới trạng thái quan trọng**: database, payment provider, inventory reservation, ledger, email notification, outbox và các hệ thống có side effect. Một API không được tự nhận an toàn chỉ vì response được cache và trả lại cùng JSON trong khi downstream đã làm nghiệp vụ hai lần.

## 3. Phân biệt safe, idempotent, cacheable và retryable

Bốn khái niệm thường bị nhầm:

| Khái niệm | Câu hỏi | Ví dụ / cảnh báo |
|---|---|---|
| **Safe** | Client chỉ yêu cầu đọc, không yêu cầu đổi trạng thái nghiệp vụ? | GET, HEAD, OPTIONS, TRACE theo HTTP semantics |
| **Idempotent** | Gửi cùng request nhiều lần có giữ nguyên **tác động dự kiến** như một lần? | PUT, DELETE; các safe methods cũng idempotent |
| **Cacheable** | Response có được lưu và tái sử dụng theo HTTP caching rules? | GET thường cacheable nếu policy cho phép; idempotent không tự đồng nghĩa cacheable |
| **Retryable** | Client có thể gửi lại trong tình huống cụ thể mà không gây hại, xét cả trạng thái không rõ và hợp đồng ứng dụng? | PUT có thể retry sau mất kết nối; POST cần cơ chế đặc thù |

**Safe là mạnh hơn idempotent về ý định:** đọc một tài nguyên không yêu cầu thay đổi nó. Tuy nhiên một GET có thể khiến server ghi metric hoặc log; điều này không làm GET mất tính safe theo ý nghĩa HTTP.

Một API thực hiện `GET /api/orders/913/charge` để **thu tiền** là một phản mẫu: request GET đã yêu cầu thay đổi nghiệp vụ. Không thể chữa vấn đề bằng cách chỉ nói “client đừng refresh trang”. Cần dùng phương thức/hợp đồng phù hợp, xác thực, kiểm soát retry và idempotency.

### Bảng ngữ nghĩa phương thức

| Phương thức | Safe theo HTTP? | Idempotent theo HTTP? | Nhận xét |
|---|---|---|---|
| **GET** | Có | Có | Chỉ yêu cầu lấy representation; server không được gán side effect nghiệp vụ cho GET |
| **HEAD** | Có | Có | Như GET về ngữ nghĩa nhưng không có response content |
| **OPTIONS** | Có | Có | Hỏi khả năng giao tiếp với resource/server |
| **TRACE** | Có | Có | Phương thức chẩn đoán; nhiều server vô hiệu hóa vì an ninh |
| **PUT** | Không | Có | Tạo/thay thế trạng thái resource ở target URI; gửi lại cùng request không nhân đôi tác động dự kiến |
| **DELETE** | Không | Có | Yêu cầu loại bỏ association của target resource; lần tiếp theo không “xóa thêm một resource khác” |
| **POST** | Không | **Không mặc định** | Ngữ nghĩa do resource quyết định; có thể thiết kế lũy đẳng bằng hợp đồng ứng dụng |
| **PATCH** | Không | **Không mặc định** | Có thể lũy đẳng hoặc không tùy patch document và xử lý |

HTTP còn định nghĩa phương thức và cơ chế mở rộng khác; bảng tập trung vào các phương thức thường gặp khi thiết kế REST API. **Phương thức có ngữ nghĩa idempotent** không chứng minh **implementation đã tuân thủ**: server PUT mà luôn sinh thêm đơn mới là sai hợp đồng dự kiến, không thể dựa vào nhãn PUT để bỏ kiểm thử.

### Safe không có nghĩa retry vô điều kiện

GET đọc dữ liệu nhạy cảm vẫn cần authentication và quota; client có thể bị 429/503; một GET rất đắt có thể làm quá tải backend khi hàng nghìn client retry đồng thời. **An toàn về side effect** không đồng nghĩa **an toàn về công suất**. Client vẫn cần timeout, backoff, jitter, retry budget và chính sách hạn mức.

## 4. Một request “giống hệt” gồm những gì?

Trong định nghĩa HTTP, **identical requests** là nhiều lần gửi cùng yêu cầu ở cấp phương thức và nội dung liên quan. Khi áp dụng vào nghiệp vụ, cần xét:

- **Phương thức và target resource**: `PUT /api/products/42` khác `PUT /api/products/43`.
- **Payload/ý nghĩa lệnh**: đặt giá 99.000 khác đặt giá 129.000.
- **Điều kiện thực thi**: `If-Match`, phiên bản dự kiến, idempotency key và các preconditions có thể đổi kết quả.
- **Danh tính/phạm vi**: tenant A không được trùng khóa và chia sẻ kết quả với tenant B.
- **Thời gian, trạng thái bên ngoài**: một request giống hệt có thể gặp trạng thái resource đã đổi hoặc quyền người gọi bị thu hồi.

**Hai lần người dùng nhấn nút giống nhau không tự chứng minh hai HTTP requests là một “ý định nghiệp vụ” duy nhất**. Nếu khách đặt **hai đơn hàng cùng giỏ** một cách cố ý, hệ thống cần cho phép hai lệnh riêng biệt. Ngược lại, khi client retry do mất response cho **một** lệnh đặt hàng, hệ thống cần cơ chế nhận diện chính xác “cùng intent”.

Đó là lý do **Idempotency-Key** thường cần thiết cho POST: nó giúp phân biệt **retry của cùng lệnh** với **lệnh mới có payload trùng nhau**.

## 5. PUT: trạng thái sau cùng có thể giống nhau, response có thể khác

PUT theo HTTP semantics yêu cầu tạo hoặc thay thế trạng thái của **target resource** bằng representation trong request, tuân thủ ràng buộc của server. Một tình huống quen thuộc:

~~~http
PUT /api/preferences/users/u-7 HTTP/1.1
Host: api.example.test
Content-Type: application/json

{"theme":"dark","emailNotifications":true}
~~~

**Lần gửi thứ nhất** khi resource chưa tồn tại:

~~~http
HTTP/1.1 201 Created
Location: /api/preferences/users/u-7
Content-Type: application/json

{"userId":"u-7","theme":"dark","emailNotifications":true}
~~~

**Lần gửi thứ hai** cùng request sau khi resource đã tồn tại:

~~~http
HTTP/1.1 204 No Content

~~~

Sau cả hai request, **preference được yêu cầu** vẫn là `theme=dark`, `emailNotifications=true`. Lần thứ nhất trả **201 Created**, lần thứ hai trả **204 No Content** vẫn hoàn toàn có thể đúng với tính lũy đẳng; **không có quy tắc bắt buộc 201 phải được phát lại**.

### PUT không nhất thiết chỉ là “update”

PUT có thể **tạo resource tại một URI do client đã biết/chọn**, hoặc thay thế một resource tồn tại, theo khả năng của server. Khi thành công với resource mới, status **201 Created** phù hợp. Khi thay thế resource hiện có, có thể trả **200 OK** hoặc **204 No Content**.

Nếu ứng dụng luôn tự sinh một ID mới cho mỗi lần nhận PUT cùng target URI, đó là lỗi thiết kế làm sai ý nghĩa lũy đẳng. Với collection tạo ID tự động, **POST /api/orders** thường là lựa chọn phổ biến hơn, nhưng cần hợp đồng retry riêng.

### Một số thay đổi phụ cần đánh giá

Server có thể ghi log, lịch sử xử lý và metric cho mỗi lần PUT. Nhưng nếu mỗi lần PUT cùng nội dung lại:

- Cộng thêm 100 điểm thưởng;
- Gửi hàng thêm một lần;
- Gửi hai hóa đơn có hiệu lực thanh toán;
- Tạo thêm một resource nghiệp vụ độc lập;

thì **tác động dự kiến đã không còn lũy đẳng**. Đừng đánh đồng “trạng thái record cuối cùng giống nhau” với “toàn bộ side effects quan trọng vẫn an toàn”.

Nếu server cập nhật `updatedAt` hoặc version mỗi lần nhận PUT giống hệt, cần xác định liệu đây là **metadata vận hành chấp nhận được** hay làm phát sinh những thay đổi nghiệp vụ không được yêu cầu (trigger gửi notification, đồng bộ hàng loạt hoặc tính tiền). Thiết kế tốt có thể kiểm tra content/version để tránh ghi không cần thiết và tránh event thừa.

## 6. DELETE: “đã xóa” khác “lần nào cũng trả 204”

DELETE yêu cầu server loại bỏ association của **target URI** khỏi chức năng hiện tại của origin server. Ví dụ:

~~~http
DELETE /api/carts/cart-91/items/item-3 HTTP/1.1
Host: api.example.test

~~~

**Lần thứ nhất** xóa item khỏi giỏ:

~~~http
HTTP/1.1 204 No Content

~~~

**Lần thứ hai** item đã không còn:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{"type":"about:blank","title":"Not Found","status":404}
~~~

Tác động dự kiến sau hai lần vẫn là: **item-3 không còn gắn với giỏ cart-91**. Do đó DELETE có thể lũy đẳng dù status khác nhau. API cũng có thể chọn trả **204** cho cả hai lần nếu phù hợp với contract và yêu cầu bảo mật/không tiết lộ, nhưng đó là **quyết định thiết kế**, không phải điều kiện duy nhất của idempotency.

### Tình huống cần cẩn thận

- **Soft delete:** gắn `deleted=true` thường có thể lũy đẳng; nhưng nếu mỗi lần DELETE lại tạo một giao dịch hoàn tiền thì không an toàn.
- **DELETE kích hoạt workflow:** việc hủy đơn có thể là một transition nghiệp vụ, cần bảo vệ khỏi tạo hai lệnh hoàn tiền/hủy vận chuyển.
- **Resource đã không tồn tại:** 404 ở lần retry **không cho client biết chắc** lần đầu đã thành công hay resource vốn đã không tồn tại. Muốn biết kết quả đúng của một lệnh quan trọng, cần audit/operation status/idempotency key.
- **Async deletion:** DELETE có thể trả **202 Accepted** nếu việc xóa còn đang xử lý; hợp đồng phải mô tả trạng thái, không coi 202 là bằng chứng đã xóa xong.

Không sử dụng `DELETE /api/orders/oldest` để xóa “đơn cũ nhất hiện thời” mà sau mỗi lần retry lại chọn **một đơn khác**. Target URI kiểu này có ngữ nghĩa thay đổi theo thời gian và có thể khiến DELETE thực tế không lũy đẳng theo tác động nghiệp vụ.

## 7. PATCH: cùng một payload không tự động lũy đẳng

Theo **RFC 5789**, PATCH **không safe và không idempotent theo mặc định**, nhưng một cách dùng PATCH cụ thể **có thể được thiết kế lũy đẳng**.

### PATCH theo phép gán (thường lũy đẳng)

~~~http
PATCH /api/products/42 HTTP/1.1
Host: api.example.test
Content-Type: application/merge-patch+json

{"price":99000}
~~~

Nếu contract quy định `price` là giá cuối cùng, cập nhật lặp lại cùng patch thường giữ `price=99000`, miễn có ràng buộc nghiệp vụ và side effects phù hợp.

### PATCH theo phép tăng (không lũy đẳng)

~~~http
POST /api/loyalty/accounts/77/points-adjustments HTTP/1.1
Host: api.example.test
Content-Type: application/json

{"delta":100,"reason":"PURCHASE"}
~~~

Nếu handler **cộng thêm 100 điểm** mỗi lần thì một lần tạo +100, hai lần +200. Đây là **lệnh không lũy đẳng về nghiệp vụ**, dù client dùng POST hay một endpoint PATCH được thiết kế theo phép tăng. Muốn retry an toàn phải nhận diện cùng **adjustment ID/idempotency key**, hoặc thay bằng một lệnh gán trạng thái phù hợp (nếu bài toán cho phép).

Với **JSON Patch** (RFC 6902), thao tác `replace` một giá trị có thể lũy đẳng nếu điều kiện nền thích hợp, trong khi `add` vào mảng tại một vị trí cụ thể có thể làm thay đổi kết quả khi lặp. Một patch gồm nhiều thao tác có thể phụ thuộc vào thứ tự và điều kiện `test`.

### Không kết luận chỉ dựa vào cú pháp JSON

Nhìn thấy `{"status":"CANCELLED"}` không đủ để kết luận request lũy đẳng nếu mỗi lần set status lại **phát lệnh hoàn tiền**. Ngược lại, một POST lệnh có payload phức tạp vẫn có thể an toàn trước retry nếu server có cơ chế idempotency trên chính **tác động nghiệp vụ**.

## 8. POST: retry có thể an toàn, nhưng phải nhờ hợp đồng ứng dụng

POST thường dùng khi server quyết định cách xử lý dữ liệu gửi vào target resource, ví dụ **POST /api/orders** để tạo một đơn hàng có ID do server sinh. Không có bảo đảm idempotent mặc định cho POST.

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json

{"cartId":"cart-91","shippingAddressId":"addr-9"}
~~~

Nếu hai request như trên đều được coi là **hai yêu cầu tạo đơn độc lập**, kết quả có thể là **ord-913** và **ord-914**. Đây không phải tự động sai HTTP: POST không được định nghĩa idempotent. Sai xuất hiện khi client **retry cùng một intent do timeout**, còn server lại hiểu là hai intent.

Hai giải pháp thường gặp:

1. **Client chọn target URI** và dùng **PUT** với một định danh ổn định, nếu hợp với mô hình resource và quyền cấp URI.
2. Giữ **POST**, nhưng có hợp đồng **Idempotency-Key** và backend bảo đảm cùng một khóa/cùng ý định chỉ có một tác động nghiệp vụ được chấp nhận.

**Idempotency-Key không phải thuộc tính mặc định của mọi POST hoặc một phần bắt buộc của RFC 9110.** Server, SDK và tài liệu OpenAPI phải thống nhất **header, scope, thời gian giữ, request fingerprint và hành vi khi retry**.

## 9. Mất response: vì sao client không thể tự suy ra kết quả?

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as REST API
    participant D as Database
    C->>S: POST /payments + Idempotency-Key K
    S->>D: Ghi giao dịch thanh toán
    D-->>S: COMMIT thành công
    S--xC: Response thất lạc do mạng/timeout
    Note over C: Kết quả không rõ, không được giả định thất bại
    C->>S: Retry cùng intent + cùng K
    S->>D: Tra khóa K/trạng thái đã lưu
    D-->>S: Thanh toán đã hoàn tất với paymentId P
    S-->>C: Kết quả theo hợp đồng, không thu lần 2
~~~

Từ góc nhìn client, các trường hợp sau có thể cùng biểu hiện thành timeout:

| Điều thực sự xảy ra | Client nhìn thấy | Rủi ro nếu retry mù |
|---|---|---|
| Request chưa rời khỏi client | Timeout/lỗi truyền | Có thể retry, nhưng client chưa chứng minh được server không nhận trong mọi tình huống |
| Server nhận nhưng chưa xử lý | Timeout | Retry song song gây tranh chấp cùng một lệnh |
| DB commit xong nhưng response mất | Timeout | POST tạo payment/order trùng nếu không dedupe |
| Server gọi provider thành công, nhưng chưa ghi DB | Timeout/5xx | Có thể thu tiền hai lần khi provider không idempotent |
| Server trả 429/503 trước side effect | HTTP error rõ nếu nhận được | Cần chính sách retry/backoff, không tạo retry storm |

**TCP reconnect, HTTP retry hay load balancer failover không tự đưa ra exactly-once semantics.** Cần cách bảo đảm từ **nghiệp vụ và lưu trữ bền vững**.

### Phân biệt hai câu hỏi khi retry

1. “Tôi có thể **gửi lại cùng request** mà không nhân đôi tác động dự kiến không?”
2. “Tôi có thể **biết kết quả của intent đầu tiên** hay chưa?”

Một DELETE lũy đẳng có thể đáp ứng câu (1) nhưng trả 404 không đủ trả lời câu (2). Với thanh toán và giao dịch tiền, client thường cần **operation ID, status endpoint hoặc idempotency record** để đối soát.

## 10. Hợp đồng Idempotency-Key: ranh giới “cùng intent”

Ví dụ client gửi:

~~~http
POST /api/payments HTTP/1.1
Host: api.example.test
Idempotency-Key: 8be2b060-94a4-49a2-a1ee-2a23114af04b
Content-Type: application/json
Accept: application/json

{"orderId":"ord-913","amount":150000,"currency":"VND"}
~~~

Server cần quy định rõ:

- **Một khóa đại diện cho một intent**; retry của cùng intent dùng **lại khóa cũ**.
- **Intent mới** dùng **khóa mới**, dù payload giống hệt (nếu nghiệp vụ cho phép).
- Scope của khóa phải gắn với **principal/tenant**, loại thao tác và ranh giới API hợp lý.
- Cùng khóa dùng với **payload khác** bị từ chối, không âm thầm áp payload mới.
- Thời gian giữ khóa (**TTL/retention**) và hành vi sau hết hạn được công bố.
- Request có cùng khóa đang xử lý song song phải được xử lý an toàn, không cùng tạo side effect.
- Kết quả retry khi operation đã hoàn tất được định nghĩa rõ: **phát lại response gốc** hoặc trả **trạng thái operation hiện tại**; đây là **chính sách API**, không phải yêu cầu chung của HTTP idempotency.

### Khóa nào là “giống nhau”?

Ví dụ định danh nội bộ:

~~~text
scope = tenantId + ":" + principalId + ":" + operationKind
logicalKey = (scope, idempotencyKey)
fingerprint = SHA256(canonicalSemanticRequest)
~~~

Một fingerprint có thể tính từ **method, route/operation kind, media type, các trường nghiệp vụ có ý nghĩa và payload đã được chuẩn hóa có kiểm soát**. Nếu raw JSON bytes được dùng, hai document JSON giống nghĩa nhưng khác thứ tự trường có thể có hash khác; khi ấy phải công bố chính sách fingerprint theo **bytes**. Nếu canonical hóa, phải quy định rõ kiểu số, null, Unicode, field defaults và dữ liệu không được tham gia.

**Không dùng mỗi payload hash thay cho intent key.** Hai đơn hàng cố ý giống nhau có thể cần hai ID khác nhau. Ngược lại, một khóa cố định tái sử dụng cho mọi đơn của cùng user sẽ khiến những intent khác nhau bị từ chối.

### Bảng hành vi gợi ý

| Request | Trạng thái record của khóa | Hành vi hợp đồng đề xuất |
|---|---|---|
| Khóa mới, payload hợp lệ | Chưa tồn tại | Nhận quyền xử lý; tạo record bền vững và thực hiện một lần |
| Cùng khóa, cùng fingerprint | **COMPLETED** | Trả kết quả đã ghi hoặc kết quả hiện tại theo policy; không làm lại side effect |
| Cùng khóa, cùng fingerprint | **PROCESSING** | Trả 409/202 hoặc chờ theo thời hạn; không chạy song song |
| Cùng khóa, fingerprint khác | Bất kỳ record còn hiệu lực | Từ chối 409 hoặc 422 theo contract; không áp yêu cầu mới |
| Thiếu khóa trong endpoint yêu cầu | Không phù hợp contract | Trả 400 theo API, giải thích cách gửi |
| Khóa hết hạn và record đã được dọn | Không còn thông tin dedupe | Chính sách phải nêu **không còn bảo đảm dedupe**; cần operation lookup hoặc business key khác |

Các mã trạng thái cho **in-progress/mismatch** không bị một quy tắc HTTP cốt lõi buộc cố định. Hãy chọn và ghi rõ trong OpenAPI/SDK. Ví dụ một API dùng **409 Conflict** cho khóa đang xử lý, **422** cho cùng khóa khác payload; API khác có thể chọn cách khác miễn hợp lý, nhất quán.

### Khóa có thời hạn không đồng nghĩa nghiệp vụ có thời hạn

Nếu idempotency record chỉ giữ **24 giờ**, sau 24 giờ một retry với cùng khóa có thể bị coi là intent mới nếu không có business uniqueness khác. Đây là ranh giới rủi ro nghiêm trọng với **thanh toán, chuyển tiền, hoàn tiền, mua vé**. Cần xác định thời gian giữ đủ dài theo **thời gian retry tối đa, vòng đời nghiệp vụ và yêu cầu đối soát**, hoặc kết hợp **business reference duy nhất** để chống trùng lâu dài.

Một thanh toán có thể phải có **UNIQUE(orderId, paymentIntentId)** hoặc unique business operation ID ngay trong ledger, thay vì trông chờ TTL ngắn của Redis.

## 11. Dedupe đồng thời: kiểm tra rồi ghi riêng rẽ là chưa đủ

Nếu hai request có cùng khóa tới hai pod khác nhau cùng lúc:

~~~text
Pod A: SELECT key K -> không thấy
Pod B: SELECT key K -> không thấy
Pod A: gọi payment provider -> tạo thanh toán P1
Pod B: gọi payment provider -> tạo thanh toán P2
Pod A: INSERT idempotency record
Pod B: INSERT conflict
~~~

**Unique constraint ở cuối không cứu được side effect đã diễn ra trước khi ghi nhận quyền xử lý.** Cần **claim cùng intent bằng thao tác atomic trước side effect**, rồi bảo đảm rằng các bước thực thi không có hai owner hợp lệ.

### Một state machine đơn giản

~~~mermaid
stateDiagram-v2
    [*] --> ABSENT
    ABSENT --> PROCESSING: Atomic claim key + fingerprint
    PROCESSING --> COMPLETED: Hoàn tất + lưu result
    PROCESSING --> FAILED_FINAL: Lỗi nghiệp vụ cuối cùng
    PROCESSING --> RECOVERING: Lease hết hạn hoặc worker mất kết nối
    RECOVERING --> PROCESSING: Reconcile / resume an toàn
    COMPLETED --> [*]
    FAILED_FINAL --> [*]
~~~

**ABSENT/PROCESSING/COMPLETED/FAILED_FINAL/RECOVERING** là trạng thái thiết kế minh họa, không phải enum của HTTP. Trong sản xuất phải xác định **record nào là terminal**, lỗi nào có thể thử lại, lease/fencing token và cách tra cứu khi provider đã xử lý nhưng backend chưa kịp ghi kết quả.

### Schema dữ liệu tham khảo

~~~sql
-- SQL minh họa, cú pháp và kiểu dữ liệu điều chỉnh theo DB thực tế.
CREATE TABLE idempotency_records (
    tenant_id        VARCHAR(100) NOT NULL,
    operation_kind   VARCHAR(100) NOT NULL,
    idempotency_key  VARCHAR(200) NOT NULL,
    request_hash     VARCHAR(128) NOT NULL,
    state            VARCHAR(32) NOT NULL,
    operation_id     VARCHAR(100),
    response_status  INTEGER,
    response_body    TEXT,
    expires_at       TIMESTAMP,
    created_at       TIMESTAMP NOT NULL,
    updated_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, operation_kind, idempotency_key)
);
~~~

Trong ứng dụng nhiều tenant, record phải được phân quyền và lưu ở kho **có atomic uniqueness**. Không lưu thông tin thẻ thanh toán hoặc token nhạy cảm trong `response_body` nếu không có lý do và biện pháp bảo vệ phù hợp.

### Phác thảo claim và xử lý

~~~text
handleCreatePayment(tenant, key, request):
    validateAuthenticatedScopeAndBusinessInput()
    hash = fingerprint(request)

    record = atomicInsertIfAbsent(
        tenant, operationKind, key, hash, PROCESSING)

    if record.alreadyExisted:
        if record.requestHash != hash:
            return CONTRACT_ERROR_KEY_REUSED_WITH_DIFFERENT_REQUEST
        if record.state == COMPLETED:
            return storedResultOrOperationStatus(record)
        if record.state == FAILED_FINAL:
            return storedFailureOrOperationStatus(record)
        return IN_PROGRESS_RESPONSE_WITH_RETRY_POLICY

    // Chỉ owner hợp lệ được tiếp tục.
    operation = persistBusinessIntentWithUniqueReference()
    result = executeOrResumeWithDownstreamIdempotency(operation)
    persistTerminalStatusAndResult(result)
    return responseAccordingToContract(result)
~~~

**Điểm không được bỏ qua:** `PROCESSING` không thể tồn tại vĩnh viễn nếu process crash. Recovery phải kiểm tra **business intent và kết quả downstream** trước khi thực hiện lại. Lease hết hạn **không có nghĩa provider chưa thực hiện giao dịch**; takeover cần fencing/reconciliation và các khóa idempotency tương ứng ở provider.

## 12. Transaction, outbox và ranh giới exactly-once

Chỉ bảo vệ HTTP entrypoint là chưa đủ nếu workflow lan qua nhiều hệ thống:

~~~mermaid
flowchart LR
    C["Client + Idempotency-Key K"] --> API["Payment API"]
    API --> DB[("DB transaction:<br/>idempotency + payment intent + outbox")]
    DB --> R["Outbox relay"]
    R --> Q["Queue (at-least-once)"]
    Q --> W["Worker + dedupe"]
    W --> P["Payment provider<br/>idempotent business reference"]
    W --> L[("Ledger / reconciliation")]
~~~

Ví dụ giao dịch nội bộ có thể ghi **payment intent** và **outbox event** trong cùng DB transaction:

~~~sql
BEGIN;

-- Chỉ owner của khóa đã claim mới có quyền tạo intent nghiệp vụ.
INSERT INTO payment_intents(intent_id, tenant_id, order_id, state)
VALUES (:intent_id, :tenant_id, :order_id, 'PENDING');

INSERT INTO outbox(event_id, aggregate_id, event_type, payload)
VALUES (:event_id, :intent_id, 'PaymentRequested', :payload);

COMMIT;
~~~

Đây là **giả mã SQL**, giả định khóa idempotency đã được claim, các ràng buộc uniqueness nghiệp vụ và logic transaction được triển khai. Nếu claim key và tạo intent nằm ở hai giao dịch riêng, cần xử lý khoảng trống crash; trong nhiều thiết kế, tốt nhất là claim/intent/outbox cùng một transaction, hoặc có recovery state rõ ràng.

### Những điều outbox bảo đảm và không bảo đảm

- Giúp tránh **DB commit rồi mất event vĩnh viễn** do process chết trước publish, nếu relay và retention được vận hành đúng.
- Relay có thể publish **trùng** khi broker nhận event nhưng relay chưa kịp đánh dấu đã gửi.
- Worker có thể nhận lại message sau visibility timeout hoặc lỗi ACK.
- Consumer cần nhận diện `eventId`/business ID và **không tạo lại side effect**; một `UNIQUE(consumer, eventId)` chỉ đủ khi được phối hợp nguyên tử với tác động tương ứng.
- Với **payment provider**, phải chuyển cùng một idempotency/business reference tới provider hoặc làm **reconciliation trước retry**, vì transaction DB nội bộ không bao trùm HTTP call tới provider.

**“Exactly once” ở cấp hạ tầng không tự suy ra “exactly one business effect” xuyên hệ thống.** Điều mong muốn là **một tác động nghiệp vụ đã xác định trên từng ranh giới**, được bảo vệ bằng định danh ổn định, transaction phù hợp và xử lý kết quả không rõ.

### Tình huống provider thành công nhưng API mất kết nối

1. Worker gọi PSP với `paymentIntentId = p-913`; PSP đã thu tiền.
2. Kết nối đứt trước response, DB vẫn ghi `PROCESSING`.
3. Worker khác nhận lại job.
4. Nếu PSP hỗ trợ idempotency key **với phạm vi và TTL phù hợp**, worker gửi lại cùng reference và tra kết quả.
5. Nếu PSP không hỗ trợ, worker phải **tra cứu/đối soát** trước khi có bất kỳ thao tác thu tiền mới nào.

Không được suy từ timeout rằng cần gọi một lệnh charge mới với ID khác. Khi provider không có cơ chế đối soát đủ tốt, API phải công bố **trạng thái cần xử lý thủ công** thay vì mạo hiểm nhân đôi giao dịch.

## 13. Idempotency và optimistic concurrency là hai bài toán khác nhau

**Idempotency** bảo vệ khi **cùng một yêu cầu được gửi nhiều lần**. **Optimistic concurrency** bảo vệ khi **hai yêu cầu khác nhau tranh sửa cùng resource** dựa trên phiên bản cũ.

### If-Match có thể khiến response retry khác lần đầu

Client đọc:

~~~http
HTTP/1.1 200 OK
ETag: "product-42-v5"
Content-Type: application/json

{"id":42,"price":120000}
~~~

Client gửi:

~~~http
PUT /api/products/42 HTTP/1.1
Host: api.example.test
If-Match: "product-42-v5"
Content-Type: application/json

{"id":42,"price":99000}
~~~

Server cập nhật thành v6:

~~~http
HTTP/1.1 204 No Content
ETag: "product-42-v6"

~~~

Nếu client **retry request nguyên văn với If-Match v5**, điều kiện có thể không còn đúng:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/version-conflict",
  "title": "Precondition Failed",
  "status": 412,
  "detail": "ETag của resource không còn khớp điều kiện."
}
~~~

**Lần đầu 204, lần sau 412 không phủ định tính lũy đẳng của PUT.** Lần sau không sửa thêm tài nguyên và trạng thái mong muốn có thể đã đạt. Tuy nhiên từ status 412 **không thể chắc chắn chính retry của client này đã tạo v6**: một writer khác có thể đã thay đổi dữ liệu. Client cần GET lại, so sánh trạng thái và xử lý xung đột theo nghiệp vụ.

### If-Match không thay thế Idempotency-Key của payment POST

Một lệnh thanh toán có thể có:

- **If-Match/expectedVersion** để xác nhận trạng thái đơn chưa đổi;
- **Idempotency-Key** để cùng intent tạo payment không bị chạy hai lần;
- **Unique business reference/ledger constraint** để bảo vệ tác động tài chính lâu dài;
- **Provider idempotency/reconciliation** để bảo vệ qua ranh giới hệ thống.

Các cơ chế **bổ sung** cho nhau, không thể thay thế cho nhau một cách mặc định.

## 14. HTTP status khi retry: đọc ý nghĩa thay vì so bytes

| Lần đầu | Lần sau | Có thể vẫn lũy đẳng? | Điều cần xem |
|---|---|---|---|
| PUT mới: **201** | PUT lặp: **200/204** | **Có** | Cùng target và trạng thái resource mong muốn |
| DELETE: **204** | DELETE lặp: **404** | **Có** | Resource vẫn bị loại bỏ, không xóa thêm thứ khác |
| PUT với If-Match: **204** | Retry cùng điều kiện: **412** | **Có** | Điều kiện v5 không còn đúng, không thực hiện ghi thêm |
| GET: **200** | GET sau thay đổi ngoài: **404** | **Có** | GET không yêu cầu side effect, resource có thể đã bị người khác xóa |
| OPTIONS: **200** | OPTIONS: **204** | **Có** | Không thay đổi trạng thái nghiệp vụ được yêu cầu |
| POST + key: **201** | Retry: **201** đã lưu | **Có theo hợp đồng ứng dụng** | Chỉ tạo một resource; replay response là lựa chọn API |
| POST + key: **202** | Retry: **200** kèm trạng thái hoàn tất | **Có theo hợp đồng ứng dụng** | Chỉ một operation; giai đoạn xử lý đã tiến triển |
| POST không key: **201** | POST lại: **201** với ID mới | **Thường không** | Tạo hai resource nghiệp vụ nếu đó là hai execution |
| PATCH increment: **200** | PATCH increment: **200** | **Không** nếu tăng hai lần | Status giống nhau nhưng intended effect đã nhân đôi |

**Cần tránh suy luận ngược:** Không phải cứ response khác nhau là lũy đẳng; và cũng không phải cứ **response giống hệt** là an toàn. Một server trả cùng JSON `{"success":true}` cho hai lần charge nhưng thực sự thu hai khoản tiền vẫn không đáp ứng kỳ vọng idempotency nghiệp vụ.

### Không dùng status 2xx làm bằng chứng dedupe duy nhất

Client phải kiểm tra **business ID, operation state, amount, ledger reference và phạm vi quyền**. Với lệnh được chấp nhận bất đồng bộ qua **202**, thông tin thực hiện sau có thể thay đổi; việc retry với cùng key không được tạo thêm job độc lập.

## 15. Retry policy phía client: phương thức chỉ là điểm khởi đầu

### Khi nào client có thể tự retry?

RFC 9110 lưu ý client **không nên tự động retry** request dùng phương thức không lũy đẳng trừ khi client có cách biết ngữ nghĩa thực tế là lũy đẳng, hoặc có bằng chứng request ban đầu chưa được áp dụng. Proxy **không được tự động retry** những request không lũy đẳng một cách tùy tiện.

Một chiến lược thực dụng:

1. Phân loại request: **safe/idempotent**, hay **non-idempotent có key và bảo đảm dedupe**.
2. Với **timeout hoặc kết nối đứt**, xác định outcome là **unknown**, không tự gắn FAILED.
3. Với **429/503**, tôn trọng `Retry-After` khi hợp lệ; chỉ retry nếu còn ngân sách và request retry-safe.
4. Với các lỗi tạm như một số **502/503/504**, dùng **exponential backoff có jitter**; không retry tất cả 4xx.
5. Đặt **max attempts, overall deadline, concurrency limit** và **retry budget**; giới hạn tổng tải do retry.
6. Với POST side effect, giữ nguyên **Idempotency-Key** và các trường định danh intent; không tạo key mới mỗi lần thử.
7. Nếu hết thời hạn, trả **trạng thái không rõ** và chuyển sang GET operation status/đối soát khi cần; tránh trả “chắc chắn thất bại”.

~~~text
sendWithRetry(request, deadline, maxAttempts):
    assert request is safe-to-retry under documented contract
    stableIntentKey = request.idempotencyKey

    for attempt in 1..maxAttempts:
        responseOrError = send(request with stableIntentKey)

        if responseOrError is terminal success or non-retryable failure:
            return responseOrError

        if responseOrError is ambiguous:
            if operationStatusEndpointExists():
                state = queryIntentByKeyOrOperationId()
                if state is terminal:
                    return state

        if attempt == maxAttempts or deadline exceeded:
            return UNKNOWN_OR_RETRY_EXHAUSTED_WITH_RECOVERY_INSTRUCTIONS

        wait = computeRetryAfterOrBoundedBackoffWithJitter()
        if wait would exceed deadline:
            return UNKNOWN_OR_RETRY_EXHAUSTED_WITH_RECOVERY_INSTRUCTIONS
        sleep(wait)
~~~

Giả mã không thay cho HTTP client library thật. Không gọi `sendWithRetry` cho bất kỳ POST nào chỉ vì có header tên **Idempotency-Key**; server phải thực sự **hỗ trợ và bảo đảm** hợp đồng đó.

### Backoff mẫu

Với độ trễ cơ sở `D0=1s`, mức trần `Dmax=16s`, các bước trước jitter là `1, 2, 4, 8, 16` giây:

\[
D(n)=\min(D_{\max}, D_0 \times 2^{n-1}).
\]

**Jitter** tránh nhiều client retry đồng thời. Nếu Retry-After đề xuất **thời điểm sớm nhất** được gửi lại, không áp jitter làm client gửi **sớm hơn** mốc đó. Backoff kiểm soát tải, còn idempotency kiểm soát tác động lặp; **cần cả hai**.

### Điều kiện dừng

Không retry vô hạn khi:

- Payload sai schema hoặc validation không thể tự sửa;
- API từ chối do quyền **401/403** và cần bước xác thực/được cấp quyền;
- Đơn hàng đã ở trạng thái kết thúc và yêu cầu là xung đột nghiệp vụ;
- Key đã hết hạn, không còn dedupe và không có cách xác định outcome;
- Retry sẽ vượt deadline/SLO hoặc tạo tải không thể chấp nhận.

## 16. Java/Spring: minh họa thiết kế tác động lũy đẳng

### 16.1. PUT với target URI xác định

Trong Spring MVC, có thể viết controller:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record PreferenceRequest(String theme, boolean emailNotifications) {}

@RestController
@RequestMapping("/api/preferences")
class PreferenceController {
    private final PreferenceService service;

    PreferenceController(PreferenceService service) {
        this.service = service;
    }

    @PutMapping("/{userId}")
    ResponseEntity<Void> replace(
            @PathVariable String userId,
            @RequestBody PreferenceRequest request) {

        // Service phải xác thực chủ sở hữu/quyền trước khi ghi.
        boolean created = service.replaceToDesiredState(userId, request);
        if (created) {
            return ResponseEntity.status(HttpStatus.CREATED).build();
        }
        return ResponseEntity.noContent().build();
    }
}
~~~

Đây là snippet minh họa: **PreferenceService** do ứng dụng tự định nghĩa, cần xử lý transaction, phân quyền, validation và unique key `userId`. Trạng thái của preference sau hai lần PUT cùng dữ liệu là như nhau, trong khi **201** và **204** khác nhau là bình thường.

**Điểm tinh tế:** Nếu `replaceToDesiredState` tự động cộng một counter hoặc gửi email mỗi lần PUT thành công, hãy đánh giá lại tác động dự kiến; tên phương thức **PUT** không biến implementation sai thành lũy đẳng.

### 16.2. POST với Idempotency-Key và transaction

Một API tạo payment có thể yêu cầu header:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record PaymentRequest(String orderId, long amount, String currency) {}
record PaymentResponse(String paymentId, String state) {}

@RestController
@RequestMapping("/api/payments")
class PaymentController {
    private final PaymentApplicationService service;

    PaymentController(PaymentApplicationService service) {
        this.service = service;
    }

    @PostMapping
    ResponseEntity<PaymentResponse> create(
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody PaymentRequest request) {

        // identity/tenant phải đến từ security context tin cậy.
        PaymentOutcome outcome = service.handleCreate(
                key, request);
        return ResponseEntity.status(outcome.status())
                .body(outcome.body());
    }
}
~~~

**PaymentApplicationService** và **PaymentOutcome** là các abstraction ứng dụng, không phải class/framework API có sẵn. Controller chỉ chuyển giao; bảo đảm dedupe nằm ở **service + database + provider**. Ở production cần xác thực, scope tenant, định dạng key, payload validation, chống request replay, timeout và lỗi trạng thái.

### 16.3. Transactional claim trong service

Một service sử dụng database có thể xây theo quy trình:

~~~text
@Transactional
claimIntent(tenant, operation, key, fingerprint):
    INSERT idempotency_record if absent
    if conflict:
        SELECT existing
        compare fingerprint
        return COMPLETED / IN_PROGRESS / MISMATCH
    INSERT payment_intent with unique business reference
    INSERT outbox event with stable event id
    COMMIT
    return NEW_OPERATION

dispatchPaymentAfterCommit(operationId):
    load status and attempt ownership safely
    call provider using stable downstream idempotency key
    reconcile unknown outcomes
    persist result + publish completion via outbox
~~~

**Không giữ database transaction mở khi chờ một PSP qua mạng** trong kiến trúc đơn giản này; việc đó có thể khóa hàng, hết connection pool và không biến hai hệ thống thành một atomic transaction. Ghi intent bền vững, xử lý sau commit và có recovery/outbox thường dễ vận hành hơn.

### 16.4. Dedupe không chỉ bằng @Transactional

Annotation `@Transactional` bảo đảm phạm vi transaction theo cấu hình, nhưng **không tự khóa hai request cạnh tranh cùng idempotency key**. Cần ràng buộc uniqueness, atomic claim, transaction isolation phù hợp và chiến lược khi conflict/in-progress. Trên nhiều node, một `synchronized` Java chỉ bảo vệ **một JVM**, không phải toàn cluster.

### 16.5. Dữ liệu cần lưu và quản lý vòng đời

- Business ID và trạng thái operation;
- Scope, key, fingerprint;
- Response/result nếu hợp đồng chọn replay;
- Mốc thời gian, TTL/retention, lỗi terminal hoặc hướng recovery;
- Version/lease/fencing để xử lý takeover;
- Correlation/request ID để tracing, nhưng không dùng chúng thay key intent;
- Bằng chứng provider/ledger reference để đối soát.

Nếu lưu response body, cần tránh PII/secret, giới hạn kích thước và xác định policy khi representation chứa thông tin đã thay đổi. API chọn **replay response cũ** cần nói rõ đây là snapshot kết quả của intent, không phải trạng thái resource mới nhất.

## 17. Mô tả contract trong OpenAPI 3.1

~~~yaml
openapi: 3.1.0
info:
  title: Payments API
  version: 1.0.0
paths:
  /api/payments:
    post:
      summary: Tạo payment intent với bảo vệ retry
      description: >
        Mỗi Idempotency-Key biểu thị một intent trong phạm vi tenant
        và thao tác tạo thanh toán. Retry cùng key và cùng payload
        không tạo thêm payment. Retention và trạng thái in-progress
        phải được công bố trong tài liệu tích hợp.
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          description: >
            Khóa duy nhất cho một payment intent; giữ nguyên khi retry.
            Không tái sử dụng cho request có payload khác.
          schema:
            type: string
            minLength: 1
            maxLength: 200
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [orderId, amount, currency]
              properties:
                orderId:
                  type: string
                amount:
                  type: integer
                  minimum: 1
                currency:
                  type: string
                  example: VND
      responses:
        '201':
          description: Payment intent đã được tạo lần đầu
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/PaymentResult'
        '200':
          description: Kết quả intent hiện có theo chính sách retry
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/PaymentResult'
        '202':
          description: Operation đã được nhận và còn xử lý
        '400':
          description: Request sai hoặc thiếu key bắt buộc
        '409':
          description: Cùng key đang xử lý, hoặc key conflict theo contract
          content:
            application/problem+json:
              schema:
                type: object
        '422':
          description: Khóa được dùng lại với payload không tương thích
          content:
            application/problem+json:
              schema:
                type: object
        '429':
          description: Vượt hạn mức; có thể kèm Retry-After
        '503':
          description: Tạm không thể tiếp nhận an toàn
components:
  schemas:
    PaymentResult:
      type: object
      required: [paymentId, state]
      properties:
        paymentId:
          type: string
        state:
          type: string
          enum: [PENDING, SUCCEEDED, FAILED]
~~~

**Đây là ví dụ hợp đồng minh họa.** Các mã **200/201/202/409/422**, retention, in-progress và cách replay phải được triển khai đúng như tài liệu thực tế; không có một chuẩn HTTP chung yêu cầu mọi dịch vụ idempotency key dùng y hệt sơ đồ này.

**Gợi ý:** Bổ sung endpoint **GET /api/payments/{paymentId}** hoặc **GET /api/operations/{id}** để client phân biệt **PENDING/SUCCEEDED/FAILED** sau timeout, đồng thời không cần tạo một intent mới.

## 18. Kiểm thử đúng bản chất: khẳng định side effect, không chỉ response

### Ma trận contract test

| Tình huống | Điều phải chứng minh |
|---|---|
| PUT tạo resource chưa có | Lần đầu có thể 201, lần sau 200/204; resource đúng một ID |
| DELETE lặp | Sau mọi lần target vẫn bị loại bỏ; không xóa thêm resource khác |
| PATCH phép gán | Gửi cùng patch không tăng thêm tác động nghiệp vụ |
| PATCH phép tăng | Nếu không có dedupe, test cho thấy tăng hai lần; không gắn nhãn idempotent sai |
| POST không key | API công bố rủi ro/từ chối nếu key bắt buộc |
| POST cùng key, cùng payload | Một business record/ledger effect; response theo hợp đồng |
| POST cùng key, payload khác | Từ chối, không ghi dữ liệu thứ hai |
| Hai POST đồng thời cùng key trên hai instance | Chỉ một owner, một business intent |
| Crash sau claim trước side effect | Recovery an toàn, không kẹt PROCESSING vô hạn |
| Crash sau provider success trước DB result | Reconcile hoặc provider dedupe, không charge thêm |
| Outbox publish trùng | Worker xử lý lặp không nhân đôi effect |
| Event đến không đúng thứ tự | Không hạ business state hay áp kết quả cũ |
| PUT với If-Match v5 đã thành v6 | Lần tiếp theo có thể 412; không cập nhật thêm |
| Timeout/mất response | SDK giữ key, truy trạng thái, không tạo key mới |
| Retry-After và 429 | Client đợi, có jitter/budget, không tạo retry storm |
| TTL của idempotency record hết | Không tuyên bố an toàn nếu business uniqueness không còn |
| Tenant A dùng key của tenant B | Không chia sẻ kết quả/trạng thái hoặc lộ dữ liệu |
| 5xx do gateway, duplicate từ proxy | Hợp đồng retry được bảo vệ ở tầng nghiệp vụ |

### Kiểm thử lỗi theo timeline

~~~mermaid
sequenceDiagram
    participant T as Test Client
    participant A as API instance A
    participant B as API instance B
    participant D as DB
    T->>A: POST cùng key K
    T->>B: POST cùng key K (đồng thời)
    A->>D: Atomic claim K
    B->>D: Atomic claim K
    D-->>A: Claim success
    D-->>B: Conflict / existing state
    A->>D: Tạo business intent + outbox
    B-->>T: In-progress hoặc trạng thái theo contract
    A-->>T: Kết quả operation
    Note over T,D: Assert chỉ có một intent và một effect liên quan
~~~

Không dừng test ở việc cả hai HTTP responses đều có status “hợp lệ”. Phải kiểm tra **database row count, unique business reference, ledger entries, số lần provider charge, outbox event ID và trạng thái cuối**. Nếu không thể quan sát provider thật trong test, dùng một mock/stub **có bộ đếm side effect** và cơ chế mô phỏng mất response sau success.

### Ví dụ kiểm thử PUT bằng MockMvc

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Khung test minh họa; cần fixture, principal và service thật trong ứng dụng.
var payload = """
        {"theme":"dark","emailNotifications":true}
        """;

mvc.perform(put("/api/preferences/u-7")
        .contentType("application/json")
        .content(payload))
    .andExpect(status().isCreated());

mvc.perform(put("/api/preferences/u-7")
        .contentType("application/json")
        .content(payload))
    .andExpect(status().isNoContent());

// Assert trạng thái preference chỉ là dark/true, không có bản ghi trùng.
// Nếu có side effects khác, assert số lần hợp lệ theo intent.
~~~

Đoạn test là **phần thân minh họa**, không phải class JUnit hoàn chỉnh. Trong môi trường Spring Security, phải cung cấp user/token hợp lệ; nếu hệ thống chọn trả 200 cho PUT lặp, sửa assertion theo contract.

### Chỉ số vận hành cần đo

| Metric | Ý nghĩa |
|---|---|
| **Idempotency key hit/miss/reused-with-different-payload** | Client retry có đúng và bị cấu hình sai không? |
| **Concurrent claim conflict rate** | Có bão retry hoặc race trên một intent không? |
| **PROCESSING age và recovery count** | Có operation bị kẹt sau crash không? |
| **Downstream duplicate suppression** | PSP/consumer đã bảo vệ được bao nhiêu duplicate? |
| **Ledger uniqueness violations** | Tác động nghiệp vụ có bị nhân đôi không? |
| **Retry attempts per intent và backoff** | Hệ thống có retry storm không? |
| **Outbox backlog/DLQ** | Có side effect đang chờ/không thể hoàn tất? |
| **Unknown outcome count và reconciliation lag** | Bao nhiêu giao dịch cần tra cứu để kết luận? |

Đừng lưu idempotency key thô/ID người dùng nhạy cảm thành metric labels có cardinality cực cao. Khi cần debug, dùng structured logs có quyền truy cập phù hợp và correlation ID.

## 19. Case study: thanh toán vé trong đợt mở bán

### Bối cảnh giả định

Một nền tảng bán vé có thể gặp 2.000 request/giây trong một đợt mở bán. Người dùng nhấn mua, thanh toán qua đối tác. Mobile app có thể retry khi mạng yếu; API gateway cũng có chính sách retry cho upstream lỗi. Một đơn có thể đi qua:

~~~text
Mobile → API Gateway → Booking API → DB + Outbox → Worker → Payment Provider
                                            ↓
                                         Ticketing
~~~

**Yêu cầu nghiệp vụ:** một `purchaseIntentId` hợp lệ không được phát hành hai vé hay thu hai khoản tiền do retry kỹ thuật; người mua được phép tạo **một intent mua mới** khi họ thật sự muốn mua thêm vé và inventory còn.

### Thiết kế đề xuất

1. Khi user xác nhận mua, client tạo **Idempotency-Key K** cho **purchase intent**.
2. Booking API xác thực tài khoản, kiểm tra scope, ghi **intent K** cùng dữ liệu đặt chỗ và event cần thiết trong transaction.
3. Backend có unique business reference cho `purchaseIntentId`; kiểm tra chính sách tồn kho/giữ chỗ bằng transaction hoặc cơ chế concurrency phù hợp.
4. Relay publish job với stable `eventId`; worker nhận lặp vẫn chỉ điều phối **một intent**.
5. Worker dùng stable **provider idempotency reference**; nếu provider timeout, tra cứu trạng thái trước khi thu lại.
6. Việc phát hành vé có **unique constraint** liên kết với purchase intent hoặc số lượng vé đã đặt. Không dựa vào consumer ACK để ngăn phát hành trùng.
7. Client có GET trạng thái intent; nếu thấy PENDING thì **không tạo key mới chỉ để tránh chờ**.
8. Có cảnh báo operation kẹt, PSP discrepancy, duplicate suppression, outbox lag và DLQ.

### Các mức bảo đảm phải viết rõ

- **HTTP idempotency:** cùng request retry không tạo thêm purchase intent trong phạm vi retention.
- **Business uniqueness:** một purchase intent có số vé và tổng tiền đúng.
- **External side effects:** payment và ticket issuance được dedupe/đối soát theo reference.
- **Consistency:** phản hồi 202 chỉ là đã nhận, không phải đã thanh toán; phản hồi thành công sau cùng có nguồn dữ liệu chứng minh.
- **Retention:** nếu key cũ hết TTL, business ID vẫn phải bảo vệ tác động dài hạn hoặc client phải được hướng dẫn tra cứu.

### Tình huống incident

Payment provider đã thu tiền nhưng Booking API nhận timeout. Nếu ứng dụng lập tức gọi payment mới với một reference mới, khách có thể bị thu đôi. Hướng xử lý đúng là **đánh dấu trạng thái không rõ**, tra cứu PSP bằng reference ổn định, cập nhật DB sau đối soát và chỉ phát hành vé khi trạng thái thanh toán được xác minh. Nếu PSP không cung cấp API tra cứu đủ tin cậy, phải có quy trình reconciliation/thủ công phù hợp, không tự báo thất bại hay thành công giả.

## 20. Bài tập áp dụng và đáp án gợi ý

Một API quản lý bài viết có:

- **PUT /api/articles/a-91** với body cố định `{"title":"REST","published":true}`.
- **DELETE /api/articles/a-91**.
- **PATCH /api/articles/a-91** để **`viewCount += 1`**.
- **POST /api/articles/a-91/comments** tạo comment mới, ID do server sinh.
- **POST /api/invoices** phát hành hóa đơn, yêu cầu **Idempotency-Key**.

### Yêu cầu

1. PUT gửi hai lần: lần đầu 201, lần sau 204. Có trái idempotency không? Vì sao?
2. DELETE lần đầu 204, lần thứ hai 404. Có trái idempotency không? Vì sao?
3. PATCH `viewCount += 1` hai lần nhưng cả hai trả 200 giống body mẫu. Có lũy đẳng không?
4. Hai POST comment có body giống hệt từ hai lần người dùng cố ý đăng cùng nội dung. Có nên dedupe chỉ theo payload hash không?
5. Client gửi `POST /api/invoices` với key `K1` và payload A, timeout; retry key `K1` nhưng payload B. Server nên làm gì?
6. Hai API instance cùng nhận key `K2`, cùng payload, cùng lúc. Vì sao `SELECT ...` trước rồi `INSERT` sau không đủ? Đề xuất biện pháp.
7. Server đã commit invoice nhưng response mất. Làm cách nào để client biết kết quả mà không tạo invoice mới?
8. Một PUT với `If-Match: "v8"` thành công rồi retry nguyên văn nhận 412. Kết luận lũy đẳng hay không, và client cần xác minh gì?
9. Đề xuất ít nhất **sáu failure/contract tests** và **năm metrics**.

### Đáp án tham khảo

**Câu 1:** Không trái. Cả hai lần PUT cùng target và representation vẫn để article có `title=REST`, `published=true`. **201 → 204** phản ánh trạng thái resource trước mỗi lần gọi khác nhau; HTTP idempotency không yêu cầu response giống nhau.

**Câu 2:** Không trái. Sau một hoặc nhiều DELETE, target đã không còn. **204 → 404** có thể đúng dù client cần kênh khác để biết kết quả lịch sử của intent đầu tiên.

**Câu 3:** Không. Hai lần tăng `viewCount` làm cộng hai, nên **tác động dự kiến** khác một lần, dù cả hai HTTP response đều trả 200 và có thể có cùng body text.

**Câu 4:** Không. Hai comment cố ý giống nhau vẫn là hai intent khác nhau. Hash payload không thay được **key định danh intent**; nếu client retry một intent do timeout, cần khóa ổn định của intent đó.

**Câu 5:** Từ chối theo hợp đồng **key reused with different request**, ví dụ 422 hoặc 409, không áp payload B và không chạy nghiệp vụ thêm. Client nên dùng key mới khi thật sự tạo intent khác.

**Câu 6:** Hai node có thể đều đọc “chưa tồn tại”. Cần **unique constraint hoặc atomic insert-if-absent**, phối hợp claim và transaction theo cùng scope/key; chỉ owner được phép thực hiện side effect, node kia đọc trạng thái/chờ.

**Câu 7:** Retry cùng key để lấy stored result/operation status hoặc **GET /api/invoices/{id}** / **GET /api/operations/{id}**. Nếu kết quả downstream không rõ, dùng đối soát, không tạo hóa đơn mới từ key khác.

**Câu 8:** Vẫn có thể lũy đẳng: lần đầu PUT thay v8 thành v9, lần sau If-Match v8 không còn đúng nên 412; không ghi thêm. Nhưng 412 có thể do writer khác, vì vậy client phải đọc trạng thái/version hiện tại để xác định intent đã đạt hay chưa.

**Câu 9:** Test PUT 201/204, DELETE 204/404, PATCH increment, hai POST cùng key, key khác payload, concurrency nhiều pod, crash sau provider success, timeout/lost response, outbox duplicate, TTL expiry và tenant scope. Metric: dedupe hits, key mismatch, in-progress age, duplicate business effects, retry attempts/intent, PSP reconciliation lag, 409/412 và DLQ depth.

### Rubric tự đánh giá

| Năng lực | Điểm tối đa | Điều kiện đạt |
|---|---:|---|
| Định nghĩa intended effect và response variability | 25 | Không nhầm idempotency với status/body giống hệt |
| HTTP methods và conditional updates | 20 | Phân tích đúng PUT/DELETE/PATCH/POST/If-Match |
| Idempotency-Key và concurrent dedupe | 25 | Scope, fingerprint, atomic claim, TTL/recovery |
| Retry và phân tán | 20 | Biết outcome unknown, outbox, provider/reconciliation |
| Kiểm thử và quan sát | 10 | Đo business effect, lỗi cạnh tranh, thời gian khôi phục |

## 21. Phản mẫu và checklist trước khi triển khai

| Phản mẫu | Vì sao sai | Cách sửa |
|---|---|---|
| “Lũy đẳng = response phải giống hệt” | Không đúng ngữ nghĩa HTTP | So **intended effect**, không so byte-identical body |
| “DELETE trả 404 lần hai nên không lũy đẳng” | Nhầm trạng thái phản hồi với trạng thái resource | Kiểm tra association còn hay mất |
| “PUT là idempotent nên implementation nào cũng an toàn” | Method label không bảo vệ side effects sai | Kiểm tra nghiệp vụ, event, unique constraints |
| Dùng GET để thực hiện thanh toán hoặc xóa | Vi phạm safe semantics | Dùng method/hợp đồng phù hợp |
| Tạo key mới trên mỗi retry POST | Mất khả năng nhận diện cùng intent | Giữ nguyên key tới khi biết outcome hoặc hết chính sách |
| Dedupe chỉ bằng payload hash | Hai intent khác nhau có thể cùng payload | Dùng business intent ID/key tách biệt |
| Kiểm tra key bằng SELECT rồi mới INSERT sau side effect | Race khiến hai node cùng thực thi | Atomic claim/uniqueness trước side effect |
| Dùng synchronized trong một pod làm khóa phân tán | Nhiều instance vẫn tranh chấp | Shared transactional coordination |
| Dùng Redis TTL 1 phút như bảo đảm thu tiền không trùng vĩnh viễn | Khóa hết hạn có thể tạo giao dịch mới | Durable business uniqueness và reconciliation |
| Gọi provider lần nữa sau timeout với reference mới | Có thể nhân đôi tiền | Idempotency downstream và đối soát |
| Coi ACK của broker là exactly-one business effect | Message có thể giao lại, consumer có thể crash | Idempotent consumer và unique business reference |
| Trả 200/201 giả thành công khi còn PROCESSING | Client hiểu sai kết quả | 202/operation state hoặc kết quả thật theo contract |
| Retry mọi 4xx và mọi POST vô hạn | Gây tải và side effect lặp | Phân loại lỗi, retry budget, backoff và deadline |
| Trả lại cùng response nhưng thực hiện side effect hai lần | Giống body không chứng minh an toàn | Test ledger/provider/business result |
| Log raw idempotency key/token nhạy cảm công khai | Rủi ro bảo mật và cardinality | Scope, mask, audit logs có quyền |

### Checklist thực hành

- [ ] Đã định nghĩa rõ **tác động nghiệp vụ được yêu cầu** và ranh giới đo lũy đẳng.
- [ ] Không nhầm **safe**, **idempotent**, **cacheable** và **retryable**.
- [ ] HTTP method khớp ngữ nghĩa: GET không thực hiện lệnh ghi, PUT/DELETE không nhân đôi tác động mong muốn.
- [ ] Đã test **response có thể khác nhau**: PUT 201/204, DELETE 204/404, If-Match 204/412.
- [ ] POST/PATCH có side effect không lũy đẳng được bảo vệ bằng idempotency key hoặc business reference phù hợp.
- [ ] Key có **scope tenant/principal/operation** và fingerprint được định nghĩa; khác payload bị từ chối.
- [ ] Tác vụ trùng đồng thời dùng **atomic claim + unique constraint**, không dựa vào check-then-insert.
- [ ] Có chiến lược **PROCESSING/COMPLETED/FAILED/RECOVERY**, TTL và hành vi sau khi key hết hạn.
- [ ] Side effect tới PSP, email, ledger hoặc broker được bảo vệ/đối soát **ở chính ranh giới đó**.
- [ ] Transaction và outbox được thiết kế để không mất ý định nghiệp vụ, consumer chịu được at-least-once.
- [ ] Client retry **cùng key**, có retry budget/backoff/jitter và biết dừng khi outcome unknown.
- [ ] HTTP status/Problem Details phản ánh trạng thái thật; **202** không bị hiển thị như hoàn tất.
- [ ] Có OpenAPI mô tả header key, retention, in-progress, mismatch, result/status lookup và codes.
- [ ] Contract/failure tests kiểm tra **business invariants và side effects**, không chỉ HTTP response.
- [ ] Có metric/alert về duplicate, stuck operations, provider reconciliation, retry storm và cross-tenant leakage.

**Điểm cần nhớ:** Tính lũy đẳng trong HTTP **đo tác động dự kiến** của nhiều request giống nhau, không yêu cầu mọi lần trả về cùng status hoặc body. Muốn retry an toàn ngoài thực tế, nhất là với POST thanh toán và workflow phân tán, cần **định danh intent ổn định, ràng buộc uniqueness, recovery và đối soát end-to-end**; không thể thay chúng chỉ bằng một header hoặc một câu khẳng định “API idempotent”.

### Tài liệu nền để tra cứu

- **RFC 9110 — HTTP Semantics:** định nghĩa safe/idempotent methods, PUT, DELETE, conditional requests và retry tự động.
- **RFC 5789 — PATCH Method for HTTP:** PATCH không idempotent mặc định, có thể thiết kế idempotent trong trường hợp cụ thể.
- **RFC 6902 — JavaScript Object Notation (JSON) Patch:** ngữ nghĩa của add/remove/replace/test.
- **RFC 9457 — Problem Details for HTTP APIs:** biểu diễn lỗi có cấu trúc.
- **OpenAPI Specification 3.1:** headers, responses và schemas cho hợp đồng retry.
- **Spring Framework / Spring Boot:** controller method mapping, transaction boundaries, optimistic locking và exception handling.
