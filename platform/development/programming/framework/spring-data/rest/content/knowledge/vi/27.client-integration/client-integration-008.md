# Phân biệt retry yêu cầu đọc với gửi lại thao tác tạo hoặc cập nhật

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vì sao GET thường có thể retry an toàn hơn thao tác ghi.
- Phân biệt tính safe và idempotent của HTTP method.
- Nhận diện tình huống timeout khiến client không biết thao tác ghi đã được server thực hiện hay chưa.
- Thiết kế retry có giới hạn, backoff và xử lý Retry-After.
- Ngăn tạo dữ liệu trùng bằng idempotency key hoặc cơ chế định danh nghiệp vụ.
- Dùng ETag và If-Match để tránh ghi đè cập nhật của người khác.

## 1. Retry không đồng nghĩa với gửi lại mọi request

Retry là việc client gửi lại một request sau khi lần gọi trước gặp lỗi tạm thời hoặc không nhận được kết quả rõ ràng. Việc này hữu ích khi mạng chập chờn, server quá tải hoặc một dịch vụ phụ thuộc tạm thời không khả dụng.

Tuy nhiên, trước khi retry phải trả lời hai câu hỏi:

1. Request trước có thể đã được server thực hiện hay chưa?
2. Nếu gửi lại cùng request, trạng thái dữ liệu có bị thay đổi thêm lần nữa hay không?

Với yêu cầu đọc, gửi lại thường không tạo thêm dữ liệu hoặc thực hiện thêm nghiệp vụ. Với yêu cầu tạo hoặc cập nhật, server có thể đã commit transaction dù response bị mất trên đường về client. Gửi lại một cách mù quáng có thể tạo bản ghi trùng, phát sinh side effect lặp lại hoặc ghi đè một thay đổi mới hơn.

Trong Spring Data REST, cần phân biệt rõ collection resource dùng để tạo entity, item resource dùng để đọc/cập nhật entity và association resource dùng để truy cập quan hệ. Client nên khám phá URL từ HAL link khi có thể, đồng thời áp dụng retry theo semantics của HTTP method và hợp đồng API.

## 2. Safe và idempotent trong HTTP

Hai khái niệm thường bị nhầm lẫn:

- **Safe**: request được định nghĩa là chỉ đọc, không yêu cầu server thay đổi trạng thái tài nguyên.
- **Idempotent**: thực hiện cùng một request một hoặc nhiều lần có cùng hiệu ứng dự kiến lên trạng thái server như thực hiện một lần.

| Method | Safe | Idempotent theo HTTP | Ý nghĩa khi retry |
|---|---|---|---|
| GET | Có | Có | Thường có thể retry khi lỗi tạm thời |
| HEAD | Có | Có | Tương tự GET nhưng không trả body |
| OPTIONS | Có | Có | Có thể retry khi cần đọc capability |
| PUT | Không | Có | Có thể lặp lại cùng ý định thay thế tài nguyên, nhưng phải xét concurrency và side effect của ứng dụng |
| DELETE | Không | Có | Hiệu ứng xóa đã đạt được sau lần đầu; response của lần sau có thể khác |
| POST | Không | Không mặc định | Có nguy cơ tạo tài nguyên hoặc thực hiện nghiệp vụ lặp |
| PATCH | Không | Không mặc định | Tùy nội dung patch và cách server triển khai |

Tính idempotent nói về hiệu ứng dự kiến lên trạng thái tài nguyên, không bảo đảm mọi response giống hệt nhau. Ví dụ, GET đầu tiên có thể trả dữ liệu cũ và GET tiếp theo trả dữ liệu mới do một người dùng khác vừa cập nhật.

Một PUT lặp lại có thể trả status khác nhau hoặc tạo thêm log, audit record, notification nếu ứng dụng triển khai side effect cho mỗi request. Vì vậy, semantics HTTP là cơ sở để thiết kế retry, còn hợp đồng nghiệp vụ và implementation vẫn cần được kiểm tra.

## 3. Retry yêu cầu đọc bằng GET

GET là safe và idempotent. Nếu client không nhận được response do lỗi mạng hoặc server tạm thời quá tải, gửi lại GET thường không làm thay đổi dữ liệu.

Ví dụ đọc một item resource:

~~~http
GET /orders/42
Accept: application/hal+json
~~~

Hoặc đọc association:

~~~http
GET /orders/42/customer
Accept: application/hal+json
~~~

Client có thể retry khi gặp các tình huống tạm thời như:

- Mất kết nối trước khi nhận response.
- Connect timeout hoặc read timeout.
- HTTP 408 Request Timeout.
- HTTP 429 Too Many Requests, tuân theo Retry-After nếu có.
- HTTP 502, 503 hoặc 504 trong hạ tầng gateway/proxy.

Không nên retry vô hạn. Dùng số lần thử tối đa, tổng deadline và khoảng chờ tăng dần. Nếu response có Retry-After, client nên tôn trọng thời gian server yêu cầu.

Ví dụ lệnh đọc:

~~~bash
curl -i -H "Accept: application/hal+json" \
  "http://localhost:8080/orders/42"
~~~

Có thể chạy lại request này khi lỗi tạm thời. Nếu lần đầu đã thành công nhưng response bị mất, lần GET sau chỉ đọc lại trạng thái hiện tại.

Lưu ý: GET có thể trả dữ liệu khác nhau giữa hai lần gọi nếu dữ liệu thay đổi. Idempotent không có nghĩa là response bất biến; nó có nghĩa request không tạo thêm hiệu ứng ghi lên trạng thái tài nguyên.

## 4. POST tạo tài nguyên: timeout có thể tạo bản ghi trùng

Spring Data REST thường công bố collection resource để tạo entity bằng POST:

~~~http
POST /orders
Content-Type: application/json
Accept: application/hal+json

{
  "status": "CREATED",
  "reference": "WEB-2026-0042"
}
~~~

Nếu tạo thành công, server thường trả HTTP 201 Created và header Location trỏ đến item resource vừa tạo.

Một tình huống nguy hiểm:

1. Client gửi POST.
2. Server nhận request, tạo đơn hàng và commit transaction.
3. Server gửi response 201.
4. Kết nối bị ngắt trước khi client nhận được response.
5. Client chỉ thấy timeout và không biết đơn hàng đã được tạo.
6. Client gửi lại POST; server có thể tạo đơn hàng thứ hai.

Timeout ở client không chứng minh server chưa xử lý request. Đây là lý do POST không được retry tự động một cách mù quáng.

Sau một POST có kết quả không rõ ràng:

- Giữ lại request payload và mã tham chiếu nghiệp vụ.
- Kiểm tra trạng thái bằng một GET/search resource có thể tìm theo mã tham chiếu nếu API hỗ trợ.
- Nếu tìm thấy tài nguyên đã tạo, dùng Location/self link của nó và không tạo lại.
- Nếu chưa thể xác định kết quả, giữ trạng thái thao tác là **UNKNOWN/PENDING_RECONCILIATION** và tiếp tục đối soát theo hợp đồng API.
- Chỉ gửi lại POST khi có bằng chứng request trước không được thực hiện hoặc endpoint hỗ trợ cơ chế chống trùng.

Không nên coi một lần GET chưa thấy dữ liệu là bằng chứng tuyệt đối rằng POST thất bại nếu hệ thống có eventual consistency, dữ liệu được lập chỉ mục bất đồng bộ hoặc truy vấn đang đọc replica chậm.

## 5. Idempotency key để chống tạo trùng

Với nghiệp vụ cần retry POST, một giải pháp phổ biến là idempotency key. Client tạo một khóa duy nhất cho một ý định nghiệp vụ và gửi cùng khóa trong mọi lần thử của ý định đó.

Ví dụ:

~~~http
POST /api/orders
Content-Type: application/json
Idempotency-Key: 7e7f4f2a-5df7-4dc1-8e8f-9d4eaf9a1f31

{
  "reference": "WEB-2026-0042",
  "status": "CREATED"
}
~~~

Server cần chủ động triển khai hợp đồng này. Chỉ gửi header **Idempotency-Key** không tự làm cho Spring Data REST hoặc HTTP tự động chống tạo trùng.

Một triển khai server-side thường cần:

1. Nhận key trong request và xác định phạm vi sử dụng, chẳng hạn theo tenant hoặc người dùng.
2. Lưu key cùng hash của request, trạng thái xử lý và kết quả đã tạo.
3. Đảm bảo key có unique constraint trong database để hai request đồng thời không cùng tạo hai kết quả.
4. Xử lý việc ghi key và tạo tài nguyên trong transaction hoặc một cơ chế đồng bộ tương đương.
5. Nếu key đã hoàn tất với cùng payload, trả lại kết quả đã lưu, chẳng hạn status và Location của tài nguyên ban đầu.
6. Nếu key đã được dùng với payload khác, từ chối theo hợp đồng rõ ràng, thường là conflict.
7. Có chính sách thời hạn lưu key đủ dài cho cửa sổ retry và đối soát.

Cùng một ý định tạo đơn phải dùng lại cùng key qua các lần retry. Một thao tác tạo mới độc lập phải có key mới. Nếu mỗi lần retry client tạo UUID mới, cơ chế chống trùng sẽ không có tác dụng.

Một unique business key như mã đơn hàng từ hệ thống nguồn cũng có thể ngăn tạo trùng ở tầng dữ liệu. Đây là lớp bảo vệ hữu ích ngay cả khi API đã có idempotency key.

## 6. PUT cập nhật tài nguyên

PUT được định nghĩa là idempotent: gửi lại cùng nội dung đến cùng URI có cùng hiệu ứng dự kiến lên trạng thái tài nguyên.

Ví dụ thay thế representation của item:

~~~http
PUT /orders/42
Content-Type: application/json
Accept: application/hal+json

{
  "status": "PAID",
  "reference": "WEB-2026-0042"
}
~~~

Nếu request đầu đã thành công nhưng response bị mất, gửi lại cùng PUT thường đưa tài nguyên về cùng trạng thái mong muốn. Dù vậy, cần lưu ý:

- Payload phải giữ nguyên ý định cập nhật; không tạo payload mới từ dữ liệu cũ một cách tùy tiện.
- PUT thường thay thế representation theo semantics của endpoint; trường bị bỏ khỏi payload có thể có ý nghĩa khác với PATCH.
- Một ứng dụng có thể phát notification, ghi audit hoặc kích hoạt side effect mỗi lần xử lý request. Cần thiết kế các side effect này idempotent nếu client có thể retry.
- Một người dùng khác có thể cập nhật tài nguyên giữa hai lần gửi. Khi đó gửi lại payload cũ có thể ghi đè dữ liệu mới.

Chỉ dùng PUT khi endpoint và contract cho phép thay thế tài nguyên theo cách đó. Với Spring Data REST, kiểm tra đúng item URI và media type mà API hỗ trợ.

## 7. PATCH cập nhật một phần: phải xem nội dung patch

PATCH không được bảo đảm idempotent theo HTTP. Một patch có thể idempotent hoặc không, tùy thao tác mà nó biểu diễn.

Ví dụ cập nhật một trường về giá trị cố định:

~~~http
PATCH /orders/42
Content-Type: application/merge-patch+json

{
  "status": "PAID"
}
~~~

Nếu gửi lại cùng patch, trạng thái status vẫn là PAID. Đây là một thao tác có hiệu ứng idempotent nếu không có side effect phụ.

Ngược lại, một thao tác kiểu “tăng số lượng thêm 1” hoặc “append phần tử vào danh sách” có thể tạo hiệu ứng nhiều lần nếu gửi lại. Một JSON Patch dùng thao tác add vào cuối array là ví dụ cần đặc biệt cẩn thận.

Với PATCH, hãy tự hỏi:

- Patch đang gán một giá trị xác định hay thực hiện một phép biến đổi?
- Gửi lại patch có tạo thêm phần tử, tăng số, trừ số hoặc kích hoạt hành động lần nữa không?
- Server có thể trả trạng thái hiện tại để client đối soát không?
- Có cần ETag/If-Match để bảo vệ phiên bản tài nguyên không?

Nếu không thể chứng minh patch idempotent, không tự động retry sau timeout không rõ kết quả. Hãy đọc lại tài nguyên và đối soát trước khi quyết định.

## 8. ETag và If-Match để tránh ghi đè cập nhật mới

Spring Data REST có thể sử dụng optimistic locking khi entity có thuộc tính phiên bản được đánh dấu **@Version**. Response item có thể chứa ETag để client biết phiên bản representation.

Ví dụ entity:

~~~java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @Version
    private Long version;

    private OrderStatus status;
}
~~~

Client đọc tài nguyên và nhận:

~~~http
GET /orders/42
Accept: application/hal+json
~~~

~~~http
HTTP/1.1 200 OK
ETag: "5"
~~~

Khi cập nhật, client gửi điều kiện phiên bản:

~~~http
PUT /orders/42
If-Match: "5"
Content-Type: application/json

{
  "status": "PAID"
}
~~~

Nếu một client khác đã cập nhật tài nguyên và ETag hiện tại không còn là "5", server có thể trả HTTP 412 Precondition Failed. Điều này ngăn client ghi đè một phiên bản mới hơn bằng dữ liệu cũ.

Khi nhận 412:

1. Không retry cùng request với ETag cũ.
2. GET lại item resource.
3. So sánh trạng thái mới với ý định nghiệp vụ.
4. Tính lại thay đổi cần thiết.
5. Gửi một request mới với ETag mới nếu nghiệp vụ vẫn hợp lệ.

ETag và If-Match cần được endpoint hỗ trợ và cấu hình đúng. Không nên tự đoán giá trị ETag hoặc bỏ điều kiện phiên bản chỉ để request retry thành công.

## 9. Phân loại lỗi trước khi retry

Không phải mọi lỗi HTTP đều là lỗi tạm thời.

| Tình huống | Hướng xử lý |
|---|---|
| DNS/connect failure, reset hoặc timeout | Với GET có thể retry có giới hạn; với write cần xác định request có thể đã được xử lý hay chưa |
| 408 Request Timeout | Có thể thử lại theo policy; với write phải xét kết quả không rõ ràng |
| 429 Too Many Requests | Chờ theo Retry-After nếu có, sau đó retry theo giới hạn |
| 502, 503, 504 | Thường là lỗi tạm thời; áp dụng backoff và deadline |
| 500 Internal Server Error | Có thể là lỗi tạm thời hoặc lỗi nghiệp vụ/server; với write cần đối soát trước khi gửi lại |
| 400 Bad Request / 422 Unprocessable Content | Sửa payload hoặc validation; không retry cùng request |
| 401 Unauthorized | Làm mới thông tin xác thực theo cơ chế bảo mật rồi đánh giá lại request |
| 403 Forbidden | Kiểm tra quyền; retry cùng request thường không giải quyết được |
| 404 Not Found | Kiểm tra URI/resource; không tự retry vô hạn |
| 409 Conflict | Đọc trạng thái và xử lý xung đột nghiệp vụ |
| 412 Precondition Failed | GET phiên bản mới, tính lại thay đổi và dùng ETag mới |

Với write, cả 500 hay timeout đều có thể xảy ra sau khi transaction đã commit. Vì vậy, status code hoặc exception phía client không phải lúc nào cũng đủ để kết luận thao tác chưa xảy ra.

## 10. Backoff, jitter và giới hạn retry

Nếu nhiều client retry ngay lập tức khi server quá tải, lượng request tăng đột biến có thể làm sự cố nặng hơn. Dùng exponential backoff để tăng khoảng chờ theo số lần thử và thêm jitter để các client không đồng bộ gửi lại cùng thời điểm.

Ví dụ lịch chờ minh họa:

| Lần thử tiếp theo | Khoảng chờ cơ sở |
|---|---:|
| Lần 2 | 200 ms |
| Lần 3 | 400 ms |
| Lần 4 | 800 ms |
| Lần 5 | 1.600 ms |

Thời gian thực tế có thể thêm random jitter và phải tuân theo Retry-After khi server cung cấp hướng dẫn đó.

Một retry policy nên có:

- Số lần thử tối đa.
- Tổng thời gian deadline cho toàn bộ request.
- Backoff có giới hạn và jitter.
- Danh sách lỗi được phép retry.
- Quy tắc riêng cho GET, POST, PUT và PATCH.
- Ghi log attempt, request correlation ID và kết quả đối soát.
- Cơ chế circuit breaker hoặc giới hạn concurrency khi dịch vụ liên tục lỗi.

Không retry khi lỗi validation, dữ liệu không hợp lệ, quyền truy cập bị từ chối hoặc xung đột cần xử lý nghiệp vụ.

## 11. Luồng quyết định cho client

Có thể áp dụng quy trình sau:

1. Xác định method và ý nghĩa nghiệp vụ của request.
2. Nếu là GET/HEAD, retry có giới hạn khi lỗi thuộc nhóm tạm thời.
3. Nếu là PUT/DELETE, xác nhận thao tác có idempotent theo contract và kiểm soát concurrency; sau timeout vẫn cần cân nhắc side effect.
4. Nếu là POST, kiểm tra API có idempotency key hoặc unique business key hay không.
5. Nếu là PATCH, đánh giá patch có lặp lại an toàn hay không.
6. Nếu write timeout hoặc mất response, đánh dấu kết quả chưa rõ và đối soát bằng GET/search hoặc trạng thái nghiệp vụ.
7. Chỉ gửi lại write khi đã xác định cách chống trùng hoặc đã chứng minh lần trước chưa được thực hiện.
8. Khi dùng optimistic locking, GET lại ETag và tính lại cập nhật nếu nhận 412.

Pseudocode:

~~~text
send(request)

if response received:
    handle response and status

else if request is a read:
    retry with bounded backoff when failure is transient

else if request is a write:
    mark outcome as UNKNOWN
    reconcile current resource/business state

    if operation is already applied:
        use the existing result; do not repeat the mutation

    else if the API provides idempotency protection:
        retry with the same idempotency key

    else:
        do not blindly resend
        escalate or follow the API's reconciliation contract
~~~

## 12. Thực hành bằng curl

Đọc item resource:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/orders/42
~~~

Tạo tài nguyên qua collection resource:

~~~bash
curl -i -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"reference":"WEB-2026-0042","status":"CREATED"}' \
  http://localhost:8080/orders
~~~

Chỉ thêm header idempotency key nếu API custom của ứng dụng đã triển khai và tài liệu hóa cơ chế đó:

~~~bash
curl -i -X POST \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: 7e7f4f2a-5df7-4dc1-8e8f-9d4eaf9a1f31" \
  -d '{"reference":"WEB-2026-0042","status":"CREATED"}' \
  http://localhost:8080/api/orders
~~~

Cập nhật một phần tài nguyên:

~~~bash
curl -i -X PATCH \
  -H "Content-Type: application/merge-patch+json" \
  -d '{"status":"PAID"}' \
  http://localhost:8080/orders/42
~~~

Khi thực hành, hãy mô phỏng tình huống server xử lý request nhưng client mất response. Kiểm tra số bản ghi trong database và trạng thái resource trước khi quyết định gửi lại. Không tạo retry loop POST chỉ để thử nghiệm trên dữ liệu thật.

## 13. Bài tập tự luyện

1. Vì sao một GET bị timeout thường có thể gửi lại, trong khi một POST tạo đơn hàng bị timeout cần đối soát trước?
2. Phân biệt safe và idempotent. Vì sao PUT idempotent nhưng không safe?
3. Nếu server đã commit POST nhưng response 201 bị mất, client có thể gặp hậu quả gì khi gửi lại?
4. Thiết kế idempotency key cho API tạo đơn hàng: key được tạo ở đâu, lưu thế nào và xử lý hai request đồng thời ra sao?
5. So sánh PATCH gán status cố định với PATCH tăng quantity thêm một đơn vị. Thao tác nào có thể lặp lại an toàn?
6. Một PUT trả timeout rồi GET cho thấy tài nguyên đã ở trạng thái mong muốn. Client nên xử lý thế nào?
7. Khi nhận 412 Precondition Failed, vì sao không nên gửi lại payload với ETag cũ?
8. Thiết kế retry policy có exponential backoff, jitter, Retry-After, giới hạn số lần thử và deadline.

**Ghi nhớ:** Retry GET thường an toàn vì request chỉ đọc. Với POST, PATCH và cả PUT, client phải xét semantics của thao tác, khả năng server đã commit, side effect và xung đột phiên bản. Khi kết quả write không rõ ràng, hãy đối soát trạng thái; dùng idempotency key cho thao tác cần chống tạo trùng và ETag/If-Match để bảo vệ cập nhật đồng thời.

## Tài liệu tham khảo

- [RFC 9110 — HTTP Semantics: Safe and Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 5789 — PATCH Method for HTTP](https://www.rfc-editor.org/rfc/rfc5789.html)
- [Spring Data REST Reference](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Data REST — Conditional Operations and ETags](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html)
