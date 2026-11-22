# Tạo mới với ID do server hoặc client cấp

## 1. Bài toán: ai quyết định định danh tài nguyên?

Trong REST API, một tài nguyên (*resource*) cần có định danh ổn định để client truy cập, cập nhật hoặc xóa. Khi **tạo mới tài nguyên**, có hai cách thiết kế thường gặp:

1. **Server cấp ID:** client gửi dữ liệu cần tạo tới URI của *collection*; server chọn ID, lưu tài nguyên và trả URI tài nguyên vừa tạo.
2. **Client cấp ID:** client chọn ID trước, gửi biểu diễn tài nguyên tới URI chứa ID đó; server quyết định có được tạo tại URI này hay không theo hợp đồng API.

Ví dụ, ứng dụng bán hàng có collection **/orders** và tài nguyên đơn hàng **/orders/{id}**. Ở mô hình đầu tiên, client chưa biết ID khi gửi yêu cầu; ở mô hình thứ hai, client có thể tạo một UUID khi đang ngoại tuyến rồi dùng nó để đồng bộ đơn lên server.

Chủ đề này thuộc chương **Thao tác tài nguyên** của module **INTEGRATION_API_REST**. Thiết kế đúng cần phối hợp resource, URI, phương thức và mã trạng thái HTTP, hợp đồng dữ liệu, idempotency, quyền truy cập và kiểm thử API bằng Java/Spring hoặc công nghệ tương đương. Người học cũng cần hiểu trường hợp nào yêu cầu đã thành công nhưng client chưa nhận được phản hồi và cách tránh tạo trùng trong quá trình thử lại.

Sau bài học, bạn có thể:

- Chọn **POST tới collection** khi server quyết định ID và **PUT tới URI tài nguyên** khi client được phép chỉ định ID.
- Thiết kế phản hồi **201 Created**, **Location**, biểu diễn tài nguyên và các mã lỗi phù hợp.
- Giải thích idempotency của PUT, cách áp dụng **Idempotency-Key** cho POST và trường hợp retry có kết quả chưa rõ.
- Ngăn ghi đè hoặc tạo trùng nhờ **If-None-Match: \***, ràng buộc duy nhất và kiểm tra quyền.
- Mô tả, triển khai và kiểm thử hai hợp đồng tạo tài nguyên với OpenAPI, Spring MVC và cơ sở dữ liệu.

## 2. Phân biệt ID tài nguyên với đường dẫn và khóa dữ liệu

**ID** là giá trị xác định một tài nguyên trong một phạm vi, ví dụ UUID **7b6e2af2-5e91-42a1-9327-0da5637bb172**. **URI** là địa chỉ để thao tác lên resource, ví dụ **/orders/7b6e2af2-5e91-42a1-9327-0da5637bb172**. **Khóa nội bộ** có thể là một giá trị khác trong CSDL; API không nhất thiết phải công khai khóa chính của database.

| Khái niệm | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| ID công khai của resource | UUID của một đơn hàng | Định danh ổn định cho client; phải có phạm vi và quy tắc duy nhất rõ ràng. |
| URI chuẩn (*canonical URI*) | /orders/7b6e2af2-... | Địa chỉ client dùng để đọc/cập nhật/xóa theo hợp đồng. |
| Khóa chính nội bộ | bigint 102938 trong bảng orders | Phục vụ lưu trữ và quan hệ dữ liệu; có thể được ẩn khỏi API. |
| Mã nghiệp vụ | ORD-2026-000418 | Dùng hiển thị, tra cứu hoặc quy trình kinh doanh; có thể có quy tắc riêng về trùng lặp. |
| Idempotency key | create-order-req-81 | Định danh **một lần yêu cầu logic** để nhận diện retry; không tự động là ID tài nguyên. |

Đừng đồng nhất **ID đơn hàng** với **Idempotency-Key**: một khóa giúp client gửi lại cùng thao tác an toàn; một ID giúp truy cập resource sau khi đã tạo. Chúng có thể cùng do client sinh nhưng phục vụ hai trách nhiệm khác nhau.

**Phạm vi duy nhất** cần ghi rõ: ID là duy nhất toàn hệ thống hay chỉ trong một tenant? Nếu URI chỉ là **/orders/{id}**, server cần phân biệt tài nguyên qua ID toàn cục hoặc một quy tắc định tuyến nhất quán. Nếu ID chỉ duy nhất trong tenant, có thể dùng **/tenants/{tenantId}/orders/{id}**, nhưng tenant trong URL không được thay thế kiểm tra quyền từ danh tính đã xác thực.

## 3. Hai mô hình tạo mới và cách lựa chọn

| Tiêu chí | Server cấp ID | Client cấp ID |
| --- | --- | --- |
| Phương thức điển hình | **POST /orders** | **PUT /orders/{clientId}** |
| Ai chọn URI cuối? | Server | Client lựa chọn ID trong phạm vi server cho phép. |
| Body | Dữ liệu cần tạo; thường **không có ID** do client tự quyết. | Biểu diễn hoàn chỉnh hoặc dữ liệu tạo resource theo hợp đồng; ID ở path. |
| Phản hồi khi tạo ngay | **201 Created**, Location URI của resource. | **201 Created**, Location có thể chỉ chính URI đích. |
| Retry khi mất phản hồi | POST không tự idempotent; dùng Idempotency-Key hoặc cơ chế chống trùng khác. | PUT có ngữ nghĩa idempotent; tạo mới có điều kiện cần xử lý **412** khi retry. |
| Xung đột | Trùng khóa nghiệp vụ, payload hoặc idempotency key khác nội dung. | ID đã có; điều kiện tạo mới thất bại hoặc không được ghi đè. |
| Phù hợp | Tạo đơn, người dùng, sản phẩm khi backend chịu trách nhiệm định danh. | Đồng bộ ngoại tuyến, nhập tài nguyên có ID toàn cục, lưu một resource theo URI định sẵn. |
| Rủi ro chính | Duplicate sau timeout/retry; client cần lưu ID server trả. | Chiếm ID, va chạm ID, ghi đè nhầm resource và lộ quyền truy cập nếu xác thực yếu. |

**Quy tắc chọn nhanh:** nếu server sở hữu không gian định danh, hãy ưu tiên **POST collection**. Nếu client có lý do chính đáng để quyết định danh tính resource trước khi gửi và server cho phép tạo tại URI đó, hãy cân nhắc **PUT resource URI** với hợp đồng rõ ràng. Đây là quy ước thiết kế phổ biến, không phải quy tắc nói rằng mọi POST đều sinh ID hay mọi PUT đều phải tạo mới.

### 3.1. Sơ đồ quyết định

~~~mermaid
flowchart TD
    A[Cần tạo resource] --> B{Ai được quyền chọn ID?}
    B -->|Server| C[POST tới collection]
    B -->|Client được phép| D{Có cho ghi đè tại URI?}
    C --> E[Server cấp ID, lưu nguyên tử]
    E --> F[201 + Location]
    D -->|Chỉ tạo mới| G[PUT URI + If-None-Match: *]
    D -->|Tạo hoặc thay thế| H[PUT URI theo hợp đồng upsert]
    G --> I[201 nếu chưa tồn tại; 412 nếu đã tồn tại]
    H --> J[201 nếu tạo; 200 hoặc 204 nếu thay thế]
~~~

Sơ đồ tập trung thao tác tạo **đồng bộ**. Nếu server chỉ nhận việc để xử lý nền, **202 Accepted** có thể phù hợp khi tài nguyên/kết quả cuối chưa được tạo; cần thêm resource theo dõi job và hợp đồng xử lý thất bại.

## 4. Mô hình A: POST /orders để server cấp ID

### 4.1. Request và response

Client gửi dữ liệu mới tới collection:

~~~http
POST /orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "customerId": "cust-17",
  "items": [
    {"sku": "SKU-42", "quantity": 2}
  ]
}
~~~

Server tạo resource, tự cấp ID và trả:

~~~http
HTTP/1.1 201 Created
Location: /orders/7b6e2af2-5e91-42a1-9327-0da5637bb172
Content-Type: application/json
ETag: "order-v1"

{
  "id": "7b6e2af2-5e91-42a1-9327-0da5637bb172",
  "customerId": "cust-17",
  "status": "PENDING",
  "items": [
    {"sku": "SKU-42", "quantity": 2}
  ]
}
~~~

Ý nghĩa của từng thành phần:

- **POST /orders:** yêu cầu collection xử lý việc tạo resource mới. Client không chỉ định URI đích.
- **201 Created:** tài nguyên mới đã được tạo khi server phát phản hồi cuối.
- **Location:** định danh tài nguyên được tạo; trong ví dụ là URI tương đối được phân giải theo URI yêu cầu. Có thể dùng URI tuyệt đối theo quy tắc triển khai.
- **Body:** biểu diễn tài nguyên sau khi tạo, gồm ID và các trường server quyết định. Với 201, body có thể được cung cấp hoặc không; nên nhất quán trong hợp đồng.
- **ETag:** validator tùy chọn đại diện phiên bản resource, hữu ích cho cập nhật có điều kiện sau này.

Việc có trường **id** trong response không có nghĩa server phải chấp nhận trường id do client gửi. Nếu API quy định server cấp ID, có thể **từ chối** trường ID trong request hoặc bỏ qua theo tài liệu; từ chối rõ ràng thường giúp phát hiện lỗi tích hợp sớm.

### 4.2. Server nên cấp ID như thế nào?

Một số chiến lược:

| Chiến lược | Ưu điểm | Giới hạn cần cân nhắc |
| --- | --- | --- |
| Số tăng từ DB sequence | Tạo đơn giản, compact và dễ index. | Có thể lộ thứ tự hoặc quy mô hoạt động; khó hợp nhất nhiều nguồn cấp ID. |
| UUID v4 | Dễ tạo phân tán, xác suất trùng cực thấp khi sinh đúng. | Độ dài lớn; thứ tự ngẫu nhiên có thể ảnh hưởng một số kiểu index. |
| UUID v7 hoặc ID có thành phần thời gian | Có xu hướng sắp xếp theo thời gian, hữu ích cho một số workload. | Cần thư viện/triển khai đúng; có thể lộ thông tin thời gian phát sinh. |
| ID do dịch vụ cấp tập trung | Kiểm soát quy tắc định danh và phân phối. | Có thêm phụ thuộc, độ trễ hoặc điểm lỗi cần thiết kế. |
| Mã nghiệp vụ | Dễ đọc, có ích cho quy trình vận hành. | Có thể cần chống trùng và quy tắc đổi tên; không nhất thiết thích hợp làm khóa API. |

**Không dùng ID khó đoán thay cho phân quyền.** Dù dùng UUID ngẫu nhiên, server vẫn phải xác thực và kiểm tra quyền với từng resource. Nếu dùng số tăng, cần tránh trả dữ liệu của tenant khác chỉ vì client thay một chữ số trong URL.

### 4.3. Trình tự xử lý an toàn

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Orders API
    participant DB as CSDL
    C->>A: POST /orders + payload
    A->>A: Xác thực, phân quyền, validate
    A->>A: Tạo ID server
    A->>DB: INSERT đơn + ràng buộc trong transaction
    DB-->>A: Commit thành công
    A-->>C: 201 Created + Location + body
    C->>A: GET /orders/{id}
    A-->>C: 200 OK + resource
~~~

Tại bước lưu, cần có ràng buộc toàn vẹn ở CSDL (khóa chính/unique và các quan hệ cần thiết). Kiểm tra “ID chưa tồn tại” trong code **không đủ** chống hai request đồng thời. Nguồn dữ liệu phải có cơ chế atomicity; lỗi va chạm ID được xử lý có kiểm soát (ví dụ sinh lại ID trong phạm vi an toàn khi dùng ID do server cấp). Nếu có tính tiền, giữ kho hoặc phát sự kiện, phải thiết kế giao dịch và cơ chế idempotency cho các tác dụng phụ đó.

## 5. Mô hình B: PUT /orders/{id} để client cấp ID

### 5.1. Client chuẩn bị ID trước khi gửi

Một ứng dụng ngoại tuyến có thể tạo UUID cho đơn hàng cục bộ và giữ ID này trong hàng đợi đồng bộ. Khi kết nối trở lại, nó gửi request tới URI chứa ID đã chọn:

~~~http
PUT /orders/eeaa0f86-ce4b-40d3-b8ad-3da9b270e6e1 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Content-Type: application/json
If-None-Match: *

{
  "customerId": "cust-17",
  "items": [
    {"sku": "SKU-42", "quantity": 2}
  ]
}
~~~

Nếu URI chưa có resource hiện hành và client được phép tạo tại đó:

~~~http
HTTP/1.1 201 Created
Location: /orders/eeaa0f86-ce4b-40d3-b8ad-3da9b270e6e1
Content-Type: application/json

{
  "id": "eeaa0f86-ce4b-40d3-b8ad-3da9b270e6e1",
  "status": "PENDING"
}
~~~

**PUT** yêu cầu tạo hoặc thay thế trạng thái của **resource tại URI đích**, theo biểu diễn và quy tắc của API. Trong ví dụ, API dùng **If-None-Match: \*** để xác định rõ đây là **create-only**: chỉ được tạo nếu chưa có representation hiện hành ở URI đó. Điều kiện này ngăn việc vô tình ghi đè resource đã tồn tại.

Nếu server hỗ trợ PUT nhưng không cho client chọn URI/ID theo chính sách, hãy trả lỗi phù hợp theo hợp đồng; không tự động chấp nhận mọi ID. Ngược lại, khi API cho phép tạo theo ID, server vẫn có quyền kiểm tra định dạng, phạm vi, quyền, trạng thái và ràng buộc dữ liệu.

### 5.2. Nếu ID đã tồn tại thì sao?

Với **If-None-Match: \***, điều kiện tạo mới không thỏa khi resource hiện hành đã tồn tại:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/create-precondition-failed",
  "title": "Resource already exists",
  "status": 412,
  "detail": "Không thể tạo mới tại URI này vì đã có tài nguyên."
}
~~~

Lưu ý quan trọng: **412 không chứng minh yêu cầu trước đó đã thất bại**. Nếu lần PUT đầu đã tạo thành công nhưng kết nối bị mất trước khi client nhận 201, lần PUT thử lại với cùng If-None-Match sẽ nhận 412. Client cần truy vấn resource theo ID, kiểm tra quyền và nội dung/định danh yêu cầu để xác định lần tạo trước có phải của mình hay không. Không được thấy 412 rồi tự động sinh ID khác để tạo thêm đơn hàng.

### 5.3. PUT tạo hoặc thay thế (*upsert*) là hợp đồng khác

Nếu API thực sự cho phép client thay thế resource tại URI đó, PUT không có điều kiện create-only có thể có hành vi:

| Trạng thái trước request | Hành vi PUT thành công | Phản hồi thường dùng |
| --- | --- | --- |
| Resource chưa có | Tạo representation mới tại URI được chỉ định. | **201 Created** |
| Resource đã có, được phép thay thế | Thay thế trạng thái resource theo biểu diễn request. | **200 OK** nếu có representation trong body hoặc **204 No Content** nếu không có body |
| Resource đã có nhưng client không có quyền | Từ chối thao tác. | **403 Forbidden** hoặc **404 Not Found** nếu che giấu tồn tại theo chính sách |
| Resource đã có, nhưng điều kiện **If-Match** không thỏa | Không áp dụng cập nhật. | **412 Precondition Failed** |

**PUT không có nghĩa luôn “tạo hoặc cập nhật tất cả các trường” một cách tùy tiện.** Server có thể có trường chỉ đọc, bất biến nghiệp vụ hoặc quy tắc từ chối thay thế. Hợp đồng phải nêu rõ một biểu diễn PUT hoàn chỉnh trông thế nào và khi thiếu trường có xóa/reset chúng hay không. Nếu chỉ thay đổi một phần, **PATCH** có thể phù hợp hơn.

### 5.4. Khi nào dùng POST với ID do client gửi trong body?

Một API cũng có thể định nghĩa:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json

{"id":"eeaa0f86-ce4b-40d3-b8ad-3da9b270e6e1","customerId":"cust-17"}
~~~

HTTP không cấm POST chứa ID do client đề xuất. Tuy nhiên, server phải nói rõ đó là **ID bắt buộc, ID gợi ý hay khóa tra cứu nghiệp vụ**; có cho phép ghi vào URI tương ứng không; xử lý ID trùng ra sao; và tránh tác dụng phụ lặp lại thế nào. **POST không mặc nhiên idempotent chỉ vì body có ID.** Khi muốn biểu đạt trực tiếp “tạo resource tại URI tôi đã chọn”, PUT kèm điều kiện là lựa chọn rõ nghĩa hơn trong nhiều thiết kế.

## 6. So sánh idempotency, retry và kết quả chưa rõ

### 6.1. Idempotent trong HTTP nghĩa là gì?

Một phương thức là *idempotent* khi nhiều request giống hệt nhau có **hiệu ứng dự kiến lên server** giống một request đơn lẻ. **PUT** thuộc nhóm phương thức idempotent theo ngữ nghĩa HTTP; **POST** không được bảo đảm như vậy. Nhưng **idempotent không đồng nghĩa với mọi lần gọi đều trả cùng status**.

Ví dụ với PUT không có điều kiện:

1. Lần đầu **PUT /profiles/u-7** tạo tài nguyên → **201**.
2. Lần thứ hai cùng payload thay thế tài nguyên bằng cùng trạng thái → **200** hoặc **204**.
3. Trạng thái cuối vẫn tương đương một lần PUT, dù mã phản hồi có thể khác.

Ví dụ với PUT create-only:

1. Lần đầu với **If-None-Match: \*** → **201**, tài nguyên được tạo.
2. Lần retry → **412**, vì điều kiện “chưa tồn tại” đã hết đúng.
3. Không có resource thứ hai được tạo, nhưng client phải xác minh liệu tài nguyên đang có có thuộc yêu cầu trước hay không.

Phương thức idempotent vẫn có thể tạo nhiều bản ghi log, metric, audit hoặc hoạt động không đổi trạng thái resource; điều quan trọng là **hiệu ứng nghiệp vụ được yêu cầu** không bị nhân lên một cách không mong muốn.

### 6.2. POST với Idempotency-Key

Khi server chọn ID, client không biết URI của resource nếu mất phản hồi. Một chiến lược là gửi **Idempotency-Key** cho thao tác tạo:

~~~http
POST /orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Idempotency-Key: create-order-8ce6c1
Content-Type: application/json

{"customerId":"cust-17","items":[{"sku":"SKU-42","quantity":2}]}
~~~

Server định nghĩa các quy tắc:

1. Khóa được gắn với **phạm vi cụ thể** như tenant/client và loại thao tác, tránh trùng giữa những người dùng hoặc endpoint khác nhau.
2. Yêu cầu đầu với khóa mới được kiểm tra và thực thi; lưu trạng thái tiến trình và kết quả trong cơ chế bền vững đủ để xử lý retry.
3. Yêu cầu sau với **cùng khóa, cùng nội dung** nhận lại kết quả đã ghi hoặc trạng thái đang xử lý theo hợp đồng, **không tạo đơn thứ hai**.
4. Yêu cầu cùng khóa nhưng **khác nội dung** bị từ chối theo một mã lỗi nhất quán (thường có thể chọn **409 Conflict**) để tránh gán nhầm hai thao tác.
5. Yêu cầu đồng thời dùng cùng khóa cần được khóa/đồng bộ một cách nguyên tử, không được cả hai cùng đi qua kiểm tra rồi cùng tạo resource.
6. Thời hạn giữ khóa, cách chuẩn hóa/fingerprint payload, trường bị bỏ qua và hành vi sau khi khóa hết hạn phải được ghi trong tài liệu API.

Header **Idempotency-Key** là một quy ước được nhiều API áp dụng; bản thân việc thêm header **không tự làm POST an toàn** nếu server không thực thi cơ chế chống trùng. Server có thể lưu phản hồi 201 ban đầu và trả lại 201/Location trong retry, hoặc dùng hợp đồng khác có trạng thái phù hợp; cần thống nhất và kiểm thử.

### 6.3. Mất phản hồi không đồng nghĩa mất giao dịch

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant A as Orders API
    participant DB as Database
    C->>G: POST /orders + Idempotency-Key K
    G->>A: Chuyển request
    A->>DB: Tạo order và commit
    DB-->>A: Commit thành công
    A-->>G: 201 + Location
    Note over C,G: Kết nối bị ngắt trước khi client nhận response
    C->>G: Retry POST với K và cùng payload
    G->>A: Chuyển retry
    A->>A: Tra cứu kết quả đã xử lý cho K
    A-->>G: Trả kết quả được ghi nhận, không tạo lại
    G-->>C: Phản hồi theo hợp đồng idempotency
~~~

Nếu không có cơ chế này, POST lại có thể tạo đơn trùng. Với thanh toán hoặc giữ tồn kho, hậu quả còn nghiêm trọng hơn; cần idempotency ở **từng tác dụng phụ nghiệp vụ** chứ không chỉ ở controller HTTP. Không thể dùng một status **502/503/504** từ gateway để kết luận transaction đã rollback; upstream có thể đã commit.

### 6.4. Nên retry khi nào?

| Tình huống | Hành động phù hợp |
| --- | --- |
| POST timeout, có Idempotency-Key | Retry cùng khóa/payload theo chính sách, có giới hạn và backoff; hoặc tra cứu trạng thái theo khóa. |
| POST timeout, không có cơ chế chống trùng | Tìm resource qua khóa nghiệp vụ/endpoint tra cứu trước; tránh thử lại mù. |
| PUT create-only timeout | GET resource theo ID, xác minh quyền và nội dung/phiên bản; retry có thể trả 412. |
| 409 trùng khóa nghiệp vụ | Đọc lỗi, xác định resource hiện có và xử lý theo quy tắc; không đổi ID vô điều kiện. |
| 412 do If-None-Match không thỏa | Không ghi đè; đối chiếu resource hiện hành trước khi quyết định. |
| 429 hoặc 503 có Retry-After | Chờ theo gợi ý, áp dụng backoff/jitter và ngân sách retry; không mặc định thao tác trước chưa xảy ra. |

Đừng viết client chỉ dựa vào nhóm 2xx/5xx để quyết định retry. **Phương thức, tính idempotent, khóa yêu cầu và trạng thái thực tế của resource** đều quan trọng.

## 7. Điều kiện HTTP và chống mất cập nhật

Hai header điều kiện thường có vai trò khác nhau:

| Header | Mục đích thường gặp | Mã khi điều kiện không thỏa |
| --- | --- | --- |
| **If-None-Match: \*** | Chỉ áp dụng thay đổi khi URI chưa có representation hiện hành; thường dùng **PUT create-only**. | **412 Precondition Failed** với PUT. |
| **If-Match: "order-v3"** | Chỉ thay đổi tài nguyên nếu validator còn khớp; dùng khi cập nhật sau khi đọc. | **412 Precondition Failed** nếu ETag đã thay đổi. |

Ví dụ cập nhật sau khi đã tạo:

~~~http
GET /orders/eeaa0f86-ce4b-40d3-b8ad-3da9b270e6e1 HTTP/1.1
Host: api.example.com

HTTP/1.1 200 OK
ETag: "order-v3"
Content-Type: application/json

{"id":"eeaa0f86-ce4b-40d3-b8ad-3da9b270e6e1","status":"PENDING"}
~~~

Client thay đổi ghi chú dựa trên ETag vừa đọc:

~~~http
PATCH /orders/eeaa0f86-ce4b-40d3-b8ad-3da9b270e6e1 HTTP/1.1
If-Match: "order-v3"
Content-Type: application/merge-patch+json

{"note":"Gọi trước khi giao"}
~~~

Nếu resource chuyển sang version khác trước khi PATCH, phản hồi **412** giúp tránh *lost update*. API có thể chọn bắt buộc conditional request và trả **428 Precondition Required** khi thiếu header theo chính sách.

**Chống tạo trùng** và **chống ghi đè** là hai bài toán có liên hệ nhưng khác nhau: ID duy nhất ngăn tạo hai bản ghi cùng ID, còn If-Match/If-None-Match giúp diễn đạt điều kiện thao tác dựa trên trạng thái resource. Với POST cấp ID, cần thêm idempotency key nếu muốn tránh hai ID cho cùng một yêu cầu bị gửi lặp.

## 8. Tranh chấp ID, quyền truy cập và ràng buộc cơ sở dữ liệu

### 8.1. Race condition khi hai client cùng chọn một ID

Một cách cài đặt dễ lỗi:

~~~text
Client A: SELECT ... WHERE id = X => không có
Client B: SELECT ... WHERE id = X => không có
Client A: INSERT id = X => thành công
Client B: INSERT id = X => cố chèn trùng
~~~

Nếu CSDL không có unique constraint phù hợp, có thể sinh dữ liệu trùng hoặc trạng thái sai. Nếu có ràng buộc khóa chính, chỉ một insert được commit; server cần chuyển lỗi cạnh tranh thành phản hồi nhất quán. Với request **PUT create-only kèm If-None-Match: \***, kết quả thông thường là một **201** và yêu cầu còn lại **412** vì điều kiện tồn tại không thỏa. Việc kiểm tra trước khi ghi chỉ là tối ưu hoặc bước báo lỗi sớm; **bảo đảm cuối phải nằm ở thao tác ghi nguyên tử/constraint**.

### 8.2. 409 khác gì 412?

| Vấn đề | Mã nên cân nhắc | Giải thích |
| --- | --- | --- |
| PUT với **If-None-Match: \***, resource đã tồn tại | **412** | HTTP precondition thất bại; đây là trường hợp chuẩn của conditional request. |
| POST trùng mã nghiệp vụ không được phép trùng | **409** | Yêu cầu xung đột với trạng thái hiện tại của hệ thống. |
| POST dùng lại idempotency key với payload khác | **409** theo hợp đồng | Cùng khóa đại diện hai yêu cầu khác nội dung; server từ chối xung đột. |
| Client cấp ID sai định dạng | **400** | Đường dẫn/định dạng request không hợp lệ. |
| JSON hợp lệ nhưng dữ liệu vi phạm quy tắc nội dung | **422** hoặc **400** theo hợp đồng | Validation ở mức ngữ nghĩa, không phải ID collision. |
| PUT create-only thiếu header điều kiện mà API yêu cầu | **428** | Server yêu cầu precondition để tránh ghi đè. |
| Client không được tạo tài nguyên trong phạm vi tenant | **403** hoặc **404** nếu che tồn tại | Lỗi quyền, không nên tiết lộ resource của tenant khác. |

Thông báo lỗi có thể theo **Problem Details (RFC 9457)**:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-already-exists",
  "title": "Create precondition failed",
  "status": 412,
  "detail": "Đã có tài nguyên tại ID được chỉ định.",
  "code": "ORDER_CREATE_PRECONDITION_FAILED"
}
~~~

Trường **code** là mở rộng riêng của API; **status** trong body không thay thế mã HTTP của phản hồi. Không cung cấp thông tin chi tiết về chủ sở hữu/resource của tenant khác nếu không có quyền.

### 8.3. Kiểm tra quyền dù ID do client tạo

Client kiểm soát ID không đồng nghĩa được kiểm soát **tenant, owner, trạng thái hoặc trường server-managed**. Các bước tối thiểu ở server:

1. Xác thực token và xác định danh tính/tenant có thẩm quyền.
2. Kiểm tra quyền tạo mới trong phạm vi đó, cùng giới hạn quota hoặc chính sách chống lạm dụng.
3. Kiểm tra ID đúng định dạng, có nằm trong namespace được phép và có trùng resource/bí danh cần bảo vệ không.
4. Không tin **tenantId/ownerId** từ JSON nếu trường này phải bắt nguồn từ danh tính xác thực.
5. Ràng buộc unique theo phạm vi phù hợp: **(tenant_id, external_id)** hoặc global ID, tùy URI đã công bố.
6. Ghi audit và trace đủ để điều tra nhưng không log token, body nhạy cảm hoặc toàn bộ khóa định danh bí mật.

Đặc biệt, UUID ngẫu nhiên **không bảo đảm authorization**. Cần chống *broken object-level authorization* khi GET/PUT/PATCH/DELETE theo ID, kể cả khi ID rất khó đoán.

### 8.4. Xóa rồi tạo lại cùng ID

Sau DELETE, API cần xác định có cho phép tái sử dụng ID hay không. Nếu có tombstone/soft-delete hoặc ràng buộc nghiệp vụ không cho tái sử dụng (ví dụ ID của thanh toán), request tạo lại phải tuân theo chính sách đó. **If-None-Match: \*** chỉ kiểm tra điều kiện về representation hiện hành theo ngữ nghĩa HTTP; nó không thay thế quy tắc nghiệp vụ cấm tái sử dụng ID đã từng tồn tại. Có thể dùng 409 hoặc lỗi phù hợp theo hợp đồng khi ID bị giữ vĩnh viễn.

## 9. Thiết kế response và hợp đồng dữ liệu

### 9.1. Khi tạo mới đồng bộ

| Nội dung cần công bố | POST server cấp ID | PUT client cấp ID |
| --- | --- | --- |
| Request URI | /orders | /orders/{id} |
| Quy tắc payload | Không có ID do client quyết định; server tạo ID. | ID ở path, body có thể gồm trường bất biến và dữ liệu khởi tạo. |
| Mã thành công | 201 Created | 201 Created khi tạo resource mới. |
| Location | Trỏ đến URI mới do server quyết định. | Có thể chỉ đến URI đích; hữu ích để thống nhất contract. |
| Response body | ID, dữ liệu đã chuẩn hóa, trạng thái ban đầu. | Representation chuẩn hóa và trạng thái nếu trả body. |
| Validator | ETag tùy chọn nếu server cung cấp representation. | ETag tùy chọn, có thể phục vụ cập nhật có điều kiện. |
| Tính duy nhất | Khóa PK và khóa nghiệp vụ khi cần. | Khóa PK/unique cùng logic tránh va chạm. |
| Retry | Idempotency key hoặc cơ chế chống trùng nghiệp vụ. | Idempotency PUT; nếu create-only có thể nhận 412 ở retry. |

Nếu response trả một URI tuyệt đối, cần cấu hình proxy headers và public base URL đúng; không để header Host do client điều khiển dẫn tới **Location** sang domain giả mạo.

### 9.2. Khi xử lý bất đồng bộ

Không phải request tạo nào cũng hoàn thành ngay. Ví dụ, import một lô sản phẩm:

~~~http
POST /imports HTTP/1.1
Idempotency-Key: import-req-004
Content-Type: application/json

{"sourceFileId":"file-88"}

HTTP/1.1 202 Accepted
Location: /jobs/job-44
Content-Type: application/json

{"jobId":"job-44","state":"QUEUED"}
~~~

Mã **202** biểu đạt request đã được chấp nhận nhưng quá trình cuối chưa hoàn tất; công việc vẫn có thể thất bại. Client theo dõi resource job theo hợp đồng. Nếu hệ thống thực sự **đã tạo resource đại diện cho tác vụ** với URI ổn định ngay lúc phản hồi, cần quyết định rõ resource nào đã được tạo và trạng thái nào được theo dõi; không coi mọi thao tác có background processing đều mặc định trả 202.

## 10. Thiết kế Java/Spring: hai endpoint tạo tài nguyên

Ví dụ dưới đây minh họa controller của Spring MVC/Spring Boot. Để dễ tập trung vào hợp đồng HTTP, phần service và DTO được định nghĩa như interface/record tối giản; triển khai thực tế cần repository, transaction, validation, security và exception handling.

### 10.1. DTO và hợp đồng service

~~~java
import java.util.List;
import java.util.UUID;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

record OrderItemRequest(@NotBlank String sku, @Min(1) int quantity) {}

record CreateOrderRequest(
        @NotBlank String customerId,
        @NotEmpty List<@Valid OrderItemRequest> items) {}

record OrderView(UUID id, String customerId, String status) {}

interface OrderCommandService {
    // Tự cấp ID và lưu đơn thành công trước khi trả.
    OrderView createWithServerId(CreateOrderRequest request);

    // Phải là thao tác insert có điều kiện/unique nguyên tử.
    // Ném CreatePreconditionFailed khi ID đã có.
    OrderView createAtClientId(UUID id, CreateOrderRequest request);
}

class CreatePreconditionFailed extends RuntimeException {
    CreatePreconditionFailed() {
        super("Tài nguyên đã tồn tại tại ID được chỉ định");
    }
}
~~~

Ở ví dụ này, field ID của OrderView là UUID, còn request không có ID. **Client cấp ID qua path khi PUT**, nên tránh gửi hai ID có thể mâu thuẫn giữa path và body. Quy tắc kiểm tra customerId/tenant cần được hoàn thiện ở lớp service/security.

### 10.2. Controller cho POST và PUT create-only

~~~java
@RestController
@RequestMapping("/orders")
class OrderCreationController {
    private final OrderCommandService service;

    OrderCreationController(OrderCommandService service) {
        this.service = service;
    }

    @PostMapping
    ResponseEntity<OrderView> createServerAssigned(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderView created = service.createWithServerId(request);
        return ResponseEntity
                .created(java.net.URI.create("/orders/" + created.id()))
                .body(created);
    }

    @PutMapping("/{id}")
    ResponseEntity<OrderView> createClientAssigned(
            @PathVariable UUID id,
            @RequestHeader(value = HttpHeaders.IF_NONE_MATCH, required = false)
            String ifNoneMatch,
            @Valid @RequestBody CreateOrderRequest request) {

        // Hợp đồng endpoint này: chỉ tạo, không cho thay thế.
        if (!"*".equals(ifNoneMatch)) {
            throw new ResponseStatusException(
                    HttpStatus.PRECONDITION_REQUIRED,
                    "Yêu cầu If-None-Match: *");
        }

        OrderView created = service.createAtClientId(id, request);
        return ResponseEntity
                .created(java.net.URI.create("/orders/" + created.id()))
                .body(created);
    }
}
~~~

**Điểm cần nhớ:** kiểm tra If-None-Match ở controller chỉ diễn đạt hợp đồng; không ngăn được hai request cùng lúc chèn một ID. **OrderCommandService phải lưu có tính nguyên tử và sử dụng unique constraint**, đồng thời chuyển đúng lỗi ID đã tồn tại thành **CreatePreconditionFailed**. Khi tài nguyên thuộc tenant khác, không được trả nội dung resource ra ngoài để giải thích lỗi.

### 10.3. Ánh xạ xung đột điều kiện sang 412

~~~java
import java.net.URI;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class OrderCreationErrors {
    @ExceptionHandler(CreatePreconditionFailed.class)
    ResponseEntity<ProblemDetail> alreadyExists(
            CreatePreconditionFailed exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.PRECONDITION_FAILED,
                "Không thể tạo tại URI đã tồn tại.");
        problem.setTitle("Create precondition failed");
        problem.setType(URI.create(
                "https://api.example.com/problems/order-already-exists"));
        problem.setProperty("code", "ORDER_CREATE_PRECONDITION_FAILED");

        return ResponseEntity
                .status(HttpStatus.PRECONDITION_FAILED)
                .body(problem);
    }
}
~~~

Các lớp trên minh họa đường HTTP; không bao gồm cài đặt service, database, xác thực, kiểm soát tenant hay idempotency cho POST. Đặc biệt, **POST controller hiện chưa chống request lặp**; nếu ứng dụng có thể tạo đơn chịu phí hoặc phát sinh tác dụng phụ, cần thiết kế thêm Idempotency-Key ở middleware/service trước khi sử dụng thật.

### 10.4. Triển khai service và database cần bảo đảm điều gì?

Một triển khai bền vững có thể dùng các bảng rút gọn:

~~~sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    customer_id VARCHAR(100) NOT NULL,
    status VARCHAR(32) NOT NULL
);

-- Tùy hợp đồng, có thể có khóa nghiệp vụ riêng để ngăn tạo trùng.
-- CREATE UNIQUE INDEX uq_tenant_external_ref
--     ON orders (tenant_id, external_ref);
~~~

Đây là DDL minh họa cho hệ CSDL có kiểu UUID (ví dụ PostgreSQL); cần điều chỉnh theo database và mô hình thực tế. Khi tạo:

1. Lấy **tenant/actor từ danh tính đã xác thực**, không lấy làm nguồn tin cậy từ JSON.
2. Validate request và quyền tạo trước khi bắt đầu tác dụng phụ.
3. POST: sinh ID server và insert trong transaction; PUT: insert với ID client cung cấp và điều kiện tạo-only.
4. Xử lý **vi phạm unique** theo ngữ cảnh: trùng ID của PUT create-only → **412**; trùng khóa nghiệp vụ không đi qua HTTP precondition có thể → **409**. Không gom mọi unique violation thành 412.
5. Commit dữ liệu trước khi trả 201; các tác dụng phụ khác được quản lý bằng transaction/outbox hoặc cơ chế phục hồi phù hợp.
6. Nếu hỗ trợ Idempotency-Key cho POST, bản ghi khóa/yêu cầu phải phối hợp nhất quán với commit order, ngăn hai request đồng thời tạo hai đơn.

**Không xử lý rủi ro đồng thời bằng một truy vấn SELECT rồi mới INSERT nếu database không có ràng buộc duy nhất**. Một kiểm thử tích hợp thực sự chạy nhiều lời gọi đồng thời sẽ phát hiện lỗi này tốt hơn kiểm thử controller giả lập repository.

## 11. Mô tả hai hợp đồng bằng OpenAPI

Trích đoạn OpenAPI 3.1 dưới đây thể hiện rõ URI, phương thức, ID, điều kiện và mã phản hồi. Đây là mẫu có thể mở rộng cho ứng dụng thật:

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /orders:
    post:
      summary: Tạo đơn với ID do server cấp
      description: >
        Server chọn ID; client có thể gửi Idempotency-Key
        theo hợp đồng chống tạo trùng của API.
      parameters:
        - name: Idempotency-Key
          in: header
          required: false
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201':
          description: Tạo đơn thành công
          headers:
            Location:
              description: URI của resource vừa tạo
              schema:
                type: string
                format: uri-reference
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '400':
          description: Request không hợp lệ
        '401':
          description: Chưa xác thực hợp lệ
        '403':
          description: Không được phép tạo đơn
        '409':
          description: Xung đột nghiệp vụ hoặc idempotency key
        '422':
          description: Nội dung không xử lý được
        '429':
          description: Vượt giới hạn request
  /orders/{id}:
    put:
      summary: Tạo đơn tại URI có ID do client chọn
      description: Chỉ tạo mới; cần If-None-Match là dấu sao.
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
            format: uuid
        - name: If-None-Match
          in: header
          required: true
          schema:
            type: string
            enum: ['*']
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201':
          description: Đã tạo tại URI chỉ định
          headers:
            Location:
              schema:
                type: string
                format: uri-reference
        '400':
          description: URI hoặc payload không hợp lệ
        '401':
          description: Chưa xác thực hợp lệ
        '403':
          description: Không có quyền dùng ID hoặc phạm vi này
        '412':
          description: Điều kiện If-None-Match không còn đúng
        '428':
          description: Thiếu precondition bắt buộc
components:
  schemas:
    CreateOrderRequest:
      type: object
      required: [customerId, items]
      properties:
        customerId:
          type: string
        items:
          type: array
          minItems: 1
          items:
            type: object
            required: [sku, quantity]
            properties:
              sku: {type: string}
              quantity: {type: integer, minimum: 1}
    Order:
      type: object
      required: [id, customerId, status]
      properties:
        id: {type: string, format: uuid}
        customerId: {type: string}
        status: {type: string}
~~~

Trong production cần bổ sung **securitySchemes**, response lỗi có **application/problem+json**, schema đầy đủ, header **ETag**, mapping lỗi 5xx và các giới hạn hệ thống thực tế. Đặc biệt, **Idempotency-Key** là tính năng có hợp đồng riêng: OpenAPI mới mô tả header, chưa tự cung cấp cơ chế server chống tạo trùng.

## 12. Kiểm thử API: thành công, retry, đồng thời và phân quyền

### 12.1. Ma trận kiểm thử

| ID | Trường hợp | Kỳ vọng |
| --- | --- | --- |
| T01 | POST /orders hợp lệ | **201**, Location trỏ tới ID server cấp, GET URI mới trả đúng resource. |
| T02 | POST gửi trường ID mà hợp đồng không cho phép | Lỗi validation hoặc xử lý đúng quy tắc đã công bố; client không được áp đặt ID. |
| T03 | PUT /orders/{newId} + If-None-Match: * | **201**, resource có ID đúng path, không bị tạo lại bằng ID khác. |
| T04 | PUT create-only tới ID đã tồn tại | **412**, resource cũ không bị ghi đè. |
| T05 | PUT create-only thiếu If-None-Match khi API yêu cầu | **428**, không có resource mới. |
| T06 | PUT cùng ID/payload hai lần liên tiếp | Lần đầu 201, lần sau 412; chỉ **một** resource được tạo. |
| T07 | Hai PUT đồng thời tới cùng ID | Chỉ một request tạo thành công; không có hai bản ghi; response còn lại phản ánh precondition thất bại. |
| T08 | POST với cùng Idempotency-Key và payload hai lần | Chỉ **một** đơn/tác dụng phụ được tạo; response theo hợp đồng retry. |
| T09 | POST cùng key nhưng payload khác | Lỗi xung đột đã định, không tạo đơn mới. |
| T10 | POST timeout sau khi transaction đã commit | Retry/tra cứu không làm tạo thêm resource hoặc tính phí trùng. |
| T11 | PUT/GET ID của tenant khác | Từ chối theo chính sách, không lộ dữ liệu chủ sở hữu. |
| T12 | ID không đúng kiểu hoặc payload sai | **400** hoặc **422** theo quy tắc; không lưu dữ liệu. |
| T13 | Trùng mã nghiệp vụ với ID khác | Không tạo trùng nghiệp vụ; ví dụ **409** nếu quy tắc cấm. |
| T14 | DELETE rồi PUT lại cùng ID | Đúng chính sách tái sử dụng/tombstone được công bố. |

**T04–T07** quan trọng vì một kiểm thử đơn luồng có thể bỏ sót lỗi tranh chấp trong service/database. Với T08–T10, cần mô phỏng request mất phản hồi và hai request đồng thời để bảo đảm Idempotency-Key được lưu và sử dụng nhất quán với transaction, thay vì chỉ kiểm tra có header.

### 12.2. Ví dụ curl

~~~bash
# Server cấp ID bằng POST.
curl -i -X POST 'https://api.example.com/orders' \
  -H 'Authorization: Bearer <access-token>' \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: order-request-81' \
  --data '{"customerId":"cust-17","items":[{"sku":"SKU-42","quantity":2}]}'

# Client chọn ID và chỉ cho phép tạo nếu resource chưa tồn tại.
curl -i -X PUT \
  'https://api.example.com/orders/eeaa0f86-ce4b-40d3-b8ad-3da9b270e6e1' \
  -H 'Authorization: Bearer <access-token>' \
  -H 'Content-Type: application/json' \
  -H 'If-None-Match: *' \
  --data '{"customerId":"cust-17","items":[{"sku":"SKU-42","quantity":2}]}'
~~~

Ví dụ là request minh họa; địa chỉ **api.example.com** không phải server thử nghiệm thật. Khi thử bằng môi trường riêng, hãy lấy Location trong phản hồi 201 để GET resource đã tạo; gọi PUT lần nữa với cùng ID để kiểm tra 412 và xác minh resource không đổi.

### 12.3. Ví dụ MockMvc

Giả sử controller/service đã được cấu hình trong một test Spring MVC, và **validJson** là JSON hợp lệ theo DTO:

~~~java
mockMvc.perform(
        post("/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content(validJson))
    .andExpect(status().isCreated())
    .andExpect(header().exists("Location"));

mockMvc.perform(
        put("/orders/{id}", UUID.randomUUID())
            .contentType(MediaType.APPLICATION_JSON)
            .content(validJson))
    .andExpect(status().isPreconditionRequired());
~~~

Đoạn test đầu cần mock hoặc tích hợp service để tạo ID; nếu endpoint được bảo vệ bởi Spring Security, request test phải có thông tin xác thực hợp lệ. Đoạn thứ hai kiểm tra quy tắc cần **If-None-Match: \***, nhưng **không chứng minh** database xử lý cạnh tranh đúng. Cần thêm integration test với DB thật cho hai PUT cùng ID, POST retry cùng key và phân quyền tenant.

### 12.4. Quan sát và điều tra

Khi có lỗi tạo resource, log/trace nên cho biết **method, route dạng template, status, tenant/actor đã được phép ghi nhận, request ID, idempotency key đã băm hoặc định danh theo chính sách, nguyên nhân xung đột và kết quả transaction**. Không ghi token, toàn bộ payload nhạy cảm hoặc lạm dụng log để giữ dữ liệu cá nhân. Phân tách metric **POST tạo mới**, **PUT create-only**, **409**, **412**, **428**, retry, duplicate được nhận diện và thời gian xử lý DB sẽ giúp đánh giá chất lượng hợp đồng API.

## 13. Những phản mẫu thường gặp

| Phản mẫu | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| POST luôn trả 200 dù tạo resource mới | Client không nhận rõ ngữ nghĩa đã tạo, thiếu URI. | Trả **201 Created** khi resource mới thực sự được tạo, kèm Location. |
| Client tự gửi ID vào POST nhưng server âm thầm thay ID khác | Client hiểu sai quyền sở hữu ID, dễ lỗi đồng bộ. | Quy định ID server/client cấp; validate hoặc từ chối trường ID trái hợp đồng. |
| PUT tạo mới không kiểm tra tồn tại và vô tình thay thế | Ghi đè resource hoặc dữ liệu tenant khác. | Áp **If-None-Match: \*** và cơ chế insert nguyên tử nếu API chỉ cho tạo. |
| Chỉ SELECT trước INSERT để kiểm tra ID | Hai request đồng thời có thể qua kiểm tra rồi cùng ghi. | Unique constraint hoặc thao tác có điều kiện tại nguồn dữ liệu. |
| Retry POST sau timeout với ID mới | Tạo hai đơn hoặc tính tiền trùng. | Idempotency-Key, tra cứu trạng thái và chống trùng tác dụng phụ. |
| Cho rằng PUT luôn trả 201 | Không phân biệt tạo mới và thay thế. | 201 khi tạo; 200/204 khi thay thế thành công theo hợp đồng. |
| Thấy 412 ở retry rồi tạo ID khác ngay | Có thể tạo trùng resource sau lần đầu đã commit. | GET xác minh resource theo ID và nguồn gốc request trước. |
| Trả 409 cho mọi trường hợp ID đã có, kể cả If-None-Match thất bại | Làm mất ngữ nghĩa HTTP precondition. | Dùng **412** cho conditional request không thỏa; **409** cho xung đột nghiệp vụ khác. |
| Tin UUID khó đoán là đủ bảo mật | Lộ dữ liệu khi ai đó biết được ID hoặc URL. | Xác thực và phân quyền theo resource/tenant cho mọi thao tác. |
| Không xác định quy tắc tái sử dụng ID sau DELETE | ID cũ có thể được tạo lại trái ràng buộc nghiệp vụ. | Thiết kế tombstone/retention và mô tả lỗi khi ID bị giữ. |

## 14. Bài tập thiết kế: đơn hàng từ thiết bị có thể ngoại tuyến

Một ứng dụng bán hàng có cả web trực tuyến lẫn máy tính bảng tại kho đôi khi mất Internet. Web có thể đợi server cấp ID. Máy tính bảng cần tạo đơn trong lúc ngoại tuyến, hiển thị đơn và sau đó đồng bộ; nếu kết nối gián đoạn, nó có thể gửi cùng một đơn nhiều lần. Hệ thống có nhiều tenant và không được ghi đè dữ liệu tenant khác. Khi tạo đơn, server còn phải kiểm tra tồn kho và ghi sự kiện phục vụ xử lý tiếp.

### Yêu cầu

1. Chọn cách cấp ID cho web và máy tính bảng, giải thích vì sao có thể dùng hai endpoint hoặc một hợp đồng chung.
2. Thiết kế request, success response, lỗi khi ID trùng và cách client xử lý khi mất phản hồi.
3. Chỉ rõ biện pháp tránh hai lần ghi đơn hoặc trừ tồn kho.
4. Xác định ràng buộc DB, phạm vi ID và kiểm soát quyền.
5. Chọn ít nhất sáu bài kiểm thử, gồm retry và đồng thời.

### Một phương án tham khảo

**Web:** gọi **POST /orders**; server cấp UUID, trả **201 + Location**. Web sinh **Idempotency-Key** cho mỗi lần bấm tạo đơn logic và giữ khóa này khi retry. Server ràng buộc khóa với tenant/request fingerprint; commit kết quả để retry không sinh đơn thứ hai.

**Máy tính bảng:** sinh UUID v4 hợp lệ khi tạo đơn cục bộ và lưu vào hàng đợi; đồng bộ bằng **PUT /orders/{id}** kèm **If-None-Match: \***. Nếu mất phản hồi, thiết bị giữ nguyên ID, kiểm tra **GET /orders/{id}** khi có quyền và xác minh đơn có đúng với thao tác trước; không tự tạo ID mới khi nhận 412.

**Server:** dùng tenant từ access token, unique constraint phù hợp, validation, transaction và khóa nghiệp vụ chống trùng. Nếu tác dụng phụ như ghi nhận tồn kho hoặc phát sự kiện không thể gói cùng giao dịch, dùng transactional outbox hay một cơ chế nhất quán/retry an toàn; consumer phải xử lý trùng được. Nếu cả POST và PUT cùng tạo loại tài nguyên này, chúng phải dùng chung quy tắc quyền, trạng thái và bất biến nghiệp vụ.

**Kiểm thử:** POST thành công trả 201/Location; PUT thành công trả 201 đúng ID; PUT cùng ID lần nữa trả 412; hai PUT đồng thời chỉ một lần commit; hai POST cùng idempotency key chỉ một đơn; POST cùng key khác body bị từ chối; tenant khác không thể truy cập; mô phỏng timeout sau commit và replay sự kiện không trừ tồn kho lần hai.

### Câu hỏi suy luận

- Nếu client dùng **PUT không điều kiện** để đồng bộ một đơn đã bị server cập nhật trạng thái, dữ liệu nào có nguy cơ mất?
- Nếu hai thiết bị trong cùng tenant tạo **hai UUID khác nhau** cho cùng một đơn thực tế, unique constraint theo ID có đủ chống trùng nghiệp vụ không?
- Nếu lần PUT đầu đã commit nhưng client nhận timeout, lần thứ hai nhận 412, liệu có chứng minh lần PUT đầu thất bại?
- Nếu hệ thống trả 202 để đợi kiểm tra tồn kho, ID do client tạo có tự động chứng minh đơn đã được duyệt không?

**Gợi ý:** (1) PUT thay thế có thể ghi đè trạng thái mới nếu không kiểm soát phiên bản/điều kiện; (2) không, cần khóa nghiệp vụ/idempotency hoặc quy trình phát hiện trùng; (3) không, phải đối chiếu resource đã tồn tại; (4) không, 202 chỉ là chấp nhận xử lý, kết quả nghiệp vụ phải được theo dõi sau đó.

## 15. Checklist trước khi công bố endpoint tạo tài nguyên

- [ ] Quy định rõ **ai cấp ID**, phạm vi duy nhất, kiểu dữ liệu và cách dựng canonical URI.
- [ ] Phân biệt POST collection và PUT resource URI theo trách nhiệm chọn ID.
- [ ] Tạo đồng bộ thành công trả **201 Created** và URI tài nguyên rõ ràng qua Location hoặc hợp đồng tương đương.
- [ ] Nếu dùng PUT create-only, yêu cầu **If-None-Match: \*** và trả **412** khi điều kiện thất bại; không ghi đè.
- [ ] Nếu PUT cho phép thay thế, mô tả đầy đủ ngữ nghĩa payload, quyền, ETag/If-Match và mã 200/204 khi cập nhật.
- [ ] POST có chiến lược retry/idempotency phù hợp với nghiệp vụ; không tạo trùng sau timeout.
- [ ] Idempotency-Key có phạm vi, fingerprint, xử lý đồng thời, thời hạn lưu và quy tắc payload khác khóa.
- [ ] Database có unique constraint/transaction phù hợp; lỗi tranh chấp được ánh xạ đúng 409 hoặc 412.
- [ ] Xác thực, phân quyền theo tenant/resource và chống ID enumeration được kiểm tra ở mọi endpoint.
- [ ] Trường server-managed như owner, createdAt, status khởi tạo không bị client áp đặt trái quy tắc.
- [ ] Hợp đồng OpenAPI nêu request, response, Location, header điều kiện và lỗi.
- [ ] Có kiểm thử end-to-end cho tạo mới, retry sau mất phản hồi, đồng thời, ID trùng, tenant khác và tác dụng phụ.
- [ ] Có log/trace an toàn, metric duplicate/retry và cách tra cứu kết quả yêu cầu chưa rõ.

**Điểm cần nhớ:** khi **server cấp ID**, **POST /collection** và phản hồi **201 + Location** là thiết kế rõ ràng; khi **client được phép cấp ID**, **PUT /collection/{id}** diễn đạt thao tác tại URI đã biết. Hãy quyết định riêng **chỉ tạo hay được thay thế**, dùng điều kiện HTTP và ràng buộc dữ liệu để bảo vệ tài nguyên, đồng thời triển khai idempotency để lỗi mạng không trở thành lỗi nghiệp vụ.
