# Đọc tài nguyên không tồn tại, đã xóa hoặc không được phép thấy

## 1. Bài toán: cùng một URI nhưng không phải lúc nào cũng được trả dữ liệu

Trong REST API, một client thường đọc tài nguyên bằng GET, hoặc dùng HEAD để chỉ lấy metadata của phản hồi. Tuy nhiên, yêu cầu đọc có thể gặp ít nhất ba tình huống:

1. **Tài nguyên không tồn tại:** chưa từng được tạo, ID sai, hoặc không còn representation tại URI được yêu cầu.
2. **Tài nguyên đã xóa:** từng tồn tại nhưng đã bị xóa mềm, xóa khỏi hệ thống vận hành hoặc ngừng cung cấp ở URI đó.
3. **Tài nguyên không được phép thấy:** tài nguyên có thể tồn tại nhưng người gọi không có quyền biết hoặc truy xuất nó.

Ba tình huống này có thể cùng dẫn đến **404 Not Found**, nhưng không phải mọi trường hợp đều nên trả 404. Với một số hợp đồng API, 410 Gone hoặc 403 Forbidden mới mô tả đúng hơn. Khi thiếu thông tin xác thực, 401 Unauthorized thường là phản hồi phù hợp. Việc chọn mã còn phụ thuộc **mức độ công khai của tài nguyên, chính sách phân quyền và ý nghĩa nghiệp vụ**.

**Ví dụ xuyên suốt:** dịch vụ đơn hàng có URI:

~~~http
GET /api/orders/7a3e3b4a-125c-4f6d-a30d-3d4ffad54a63 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

Ở đây, một mã định danh trong URL **không đồng nghĩa người gọi được phép đọc**. API phải kiểm tra danh tính, phạm vi quyền và quan hệ sở hữu/tenant trước khi quyết định trả dữ liệu hoặc tiết lộ trạng thái đã xóa.

**Mục tiêu bài học:** lựa chọn đúng mã HTTP khi đọc tài nguyên, bảo vệ tài nguyên bị che giấu, xử lý vòng đời xóa, thiết kế response nhất quán và kiểm thử trong Java/Spring hoặc công nghệ tương đương.

> **Nguyên tắc:** 404 mô tả việc server không tìm thấy representation hiện tại **hoặc không muốn tiết lộ rằng nó tồn tại**; 410 dành cho trường hợp server biết quyền truy cập tới tài nguyên đích không còn và tình trạng đó có khả năng lâu dài; 401/403 mô tả vấn đề xác thực hoặc quyền theo chính sách công bố.

## 2. Mã trạng thái cần phân biệt

| Mã | Tên | Ý nghĩa liên quan đến thao tác đọc | Khi nào chọn |
|---|---|---|---|
| **200 OK** | Thành công | Client có quyền đọc representation hiện tại | Tài nguyên hiện có và được phép thấy |
| **401 Unauthorized** | Chưa có thông tin xác thực hợp lệ | Yêu cầu cần xác thực hoặc token không hợp lệ/hết hạn | Endpoint yêu cầu authentication và client chưa đáp ứng |
| **403 Forbidden** | Từ chối thực hiện | Server hiểu yêu cầu nhưng từ chối dù đã biết danh tính/quyền | Có thể công khai việc bị từ chối mà không tạo rủi ro lộ sự tồn tại |
| **404 Not Found** | Không tìm thấy | Không có representation tại URI, **hoặc server không muốn tiết lộ sự tồn tại** | Không tồn tại, bị ẩn theo quyền/tenant, đã xóa nhưng không công khai lịch sử |
| **410 Gone** | Không còn | Tài nguyên đích không còn khả dụng, tình trạng được biết là có khả năng lâu dài | Chủ thể có quyền được biết tài nguyên đã ngừng tồn tại ở URI |
| **304 Not Modified** | Không thay đổi | Chỉ dùng với request điều kiện khi representation hiện có, truy cập được và validator phù hợp | GET/HEAD có If-None-Match hoặc If-Modified-Since được đánh giá hợp lệ |

**Điều quan trọng:** 404 **không khẳng định** “ID này chưa từng tồn tại”. Ngược lại, 410 có thể gián tiếp cho biết trước đây có tài nguyên ở URI đó; vì vậy không nên dùng 410 khi mục tiêu là che giấu sự tồn tại khỏi người không có quyền.

### 2.1. 404 Not Found theo ngữ nghĩa HTTP

HTTP định nghĩa 404 cho trường hợp origin server **không tìm thấy representation hiện tại của tài nguyên đích, hoặc không sẵn sàng tiết lộ rằng representation đó tồn tại**. Mã này không cho biết sự thiếu vắng là tạm thời hay vĩnh viễn.

Ví dụ:

~~~http
GET /api/orders/does-not-exist HTTP/1.1
Host: api.example.test

HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Không tìm thấy tài nguyên"
}
~~~

Response trên được dùng như mẫu cho tài nguyên riêng tư. Cache-Control: no-store là **lựa chọn chính sách bảo vệ dữ liệu của API này**, không phải header bắt buộc của mọi 404.

### 2.2. 410 Gone: biết tài nguyên không còn và có khả năng lâu dài

410 diễn đạt rằng quyền truy cập tới tài nguyên đích không còn ở origin server và tình trạng đó **có khả năng mang tính lâu dài**. Server không cần dùng 410 nếu không biết tình trạng vắng mặt kéo dài bao lâu.

~~~http
GET /public/reports/legacy-2024 HTTP/1.1
Host: api.example.test

HTTP/1.1 410 Gone
Content-Type: application/problem+json
Cache-Control: public, max-age=60

{
  "type": "about:blank",
  "title": "Gone",
  "status": 410,
  "detail": "Báo cáo này không còn được cung cấp"
}
~~~

Mẫu này phù hợp với tài nguyên **công khai** khi doanh nghiệp chủ động công bố rằng báo cáo đã ngừng cung cấp. Trường hợp tài nguyên riêng tư, cần kiểm tra quyền trước khi quyết định có tiết lộ “Gone” hay không.

410 **không tự chứng minh rằng dữ liệu đã bị xóa vật lý khỏi mọi backup hoặc archive**. Trạng thái HTTP cho biết tài nguyên không còn được phục vụ tại URI, còn lưu giữ/xóa dữ liệu vật lý chịu chính sách vòng đời và nghĩa vụ pháp lý riêng.

### 2.3. 401 và 403: xác thực khác với phân quyền

- **401 Unauthorized:** mặc dù tên lịch sử là “Unauthorized”, mã này liên quan đến **authentication**. Server yêu cầu thông tin xác thực và phải gửi ít nhất một challenge phù hợp trong header **WWW-Authenticate**.
- **403 Forbidden:** server hiểu yêu cầu và từ chối thực hiện. Nếu đã nhận credential, server xem chúng không đủ quyền; việc gửi lại **cùng credential** thường không giải quyết được. Một 403 cũng có thể phát sinh vì chính sách khác, không chỉ phạm vi token.

Ví dụ 401 khi thiếu token:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Cần thông tin xác thực hợp lệ"
}
~~~

Ví dụ 403 khi đã xác thực nhưng không có scope để đọc đơn:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "Không đủ quyền thực hiện yêu cầu"
}
~~~

HTTP cũng cho phép origin server **thay 403 bằng 404** nếu muốn che giấu tài nguyên bị cấm. Chính sách này cần nhất quán trên các lớp gateway, application và data access.

## 3. Ma trận quyết định cho GET tài nguyên đơn lẻ

Giả sử endpoint GET /api/orders/{id} yêu cầu token Bearer. Service có quyền đọc đơn theo scope, đồng thời mỗi đơn thuộc một tenant.

| Trạng thái xác thực/quyền | Trạng thái bản ghi | Chính sách tiết lộ | Mã gợi ý |
|---|---|---|---|
| Không có token hợp lệ | Không cần tra bản ghi | Endpoint yêu cầu authentication | **401** kèm WWW-Authenticate |
| Có token nhưng thiếu quyền đọc loại tài nguyên | Không cần tra bản ghi | Quy tắc quyền của endpoint được phép công bố | **403** |
| Có quyền đọc loại tài nguyên, ID không có trong phạm vi được phép | Không tìm thấy | Không có representation hợp lệ | **404** |
| Có quyền đọc nhưng ID thuộc tenant khác | Có bản ghi ở tenant khác | Không tiết lộ tồn tại liên tenant | **404**, thông điệp giống ID chưa tồn tại |
| Có quyền đọc, bản ghi đang hoạt động thuộc tenant của mình | Có bản ghi | Được phép đọc | **200** |
| Có quyền đọc, đơn đã soft-delete và không công khai trạng thái xóa | Có tombstone hoặc cờ xóa | Che giấu khỏi API đọc thông thường | **404** |
| Có quyền đọc lịch sử, API công bố rằng tài nguyên đã ngừng phục vụ lâu dài | Có tombstone được phép công bố | Được phép tiết lộ | **410** nếu hợp đồng chọn ngữ nghĩa Gone |
| Có quyền đọc, yêu cầu điều kiện khớp ETag của representation hiện tại | Bản ghi hoạt động | Có quyền thấy | **304**, chỉ sau các kiểm tra thích hợp |

**Không có quy tắc “mọi tài nguyên đã xóa luôn trả 410”.** Một đơn hàng bị xóa mềm có thể cần trả 404 với tất cả người dùng thông thường để tránh tiết lộ lịch sử. Ngược lại, một trang tài liệu công khai bị ngừng cung cấp có thể trả 410 và thông báo thay thế.

### 3.1. Thuật toán quyết định gợi ý

~~~mermaid
flowchart TD
    A[GET hoặc HEAD /resources/id] --> B{Authentication hợp lệ?}
    B -- Không --> C[401 + WWW-Authenticate]
    B -- Có --> D{Quyền gọi endpoint?}
    D -- Không --> E[403 hoặc 404 theo chính sách che giấu]
    D -- Có --> F[Tra cứu trong phạm vi tenant / ACL]
    F --> G{Có tài nguyên hiện hành được phép đọc?}
    G -- Có --> H{Conditional GET hợp lệ và validator khớp?}
    H -- Có --> I[304 Not Modified]
    H -- Không --> J[200 OK]
    G -- Không --> K{Được phép biết trạng thái đã xóa lâu dài?}
    K -- Có và có tombstone hợp lệ --> L[410 Gone]
    K -- Không hoặc không biết --> M[404 Not Found]
~~~

Sơ đồ mô tả logic nghiệp vụ. Trong triển khai, validation của URI, kiểm tra quyền và truy vấn có thể được tổ chức khác nhau, nhưng **không được làm lộ thông tin của tài nguyên không có quyền** trong error body, timing, log trả về client hoặc response khác biệt dễ khai thác.

## 4. Trường hợp không tồn tại: 404 và những nhầm lẫn

### 4.1. Tài nguyên đơn lẻ khác với tập hợp rỗng

~~~http
GET /api/orders/9d141db3-fbc1-4313-8cf9-52c7d3572a30
~~~

Nếu ID này không có tài nguyên đọc được theo hợp đồng, trả **404**.

Nhưng với:

~~~http
GET /api/orders?status=PENDING
~~~

Nếu query hợp lệ, có quyền truy cập collection và đơn giản là **không có phần tử phù hợp**, phản hồi thông thường là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "items": [],
  "page": 0,
  "size": 20,
  "totalItems": 0
}
~~~

Tương tự, một khách hàng hợp lệ có 0 đơn hàng vẫn nhận danh sách rỗng. **Không dùng 404 chỉ vì kết quả của truy vấn collection là rỗng.**

Với tài nguyên con như GET /api/customers/{id}/orders, cần phân biệt: parent customer không tồn tại/không được phép thấy → 404 theo chính sách; customer hợp lệ nhưng chưa có đơn → 200 với collection rỗng.

### 4.2. 404 khác 400 và 405

| Request | Lỗi thực tế | Phản hồi điển hình |
|---|---|---|
| GET /api/orders/not-a-uuid | ID không đúng cú pháp định dạng đã công bố | **400 Bad Request** khi validation coi URI parameter không hợp lệ |
| GET /api/orders/{uuid-hop-le} | ID hợp lệ nhưng không tìm thấy | **404 Not Found** |
| POST /api/orders/{id} trên route chỉ hỗ trợ GET/HEAD | Không hỗ trợ method đó tại target | **405 Method Not Allowed** kèm Allow theo yêu cầu giao thức |
| GET /api/orders/{id} nhưng DB timeout | Lỗi hạ tầng | Thường **5xx** phù hợp; không che thành 404 |

Các framework có thể ánh xạ sai cú pháp hoặc route khác nhau nếu không cấu hình; hãy định nghĩa rõ trong hợp đồng và nhất quán trong test. **Không tùy tiện trả 404 cho lỗi DB**, vì client sẽ hiểu sai rằng tài nguyên không tồn tại và có thể cache phản hồi lỗi.

### 4.3. URI đã đổi không đồng nghĩa tài nguyên đã xóa

Nếu tài nguyên thật sự chỉ được chuyển sang URI mới và client có quyền tới đó, có thể chọn **301/308** (chuyển lâu dài) hoặc **302/307** (tạm thời) theo ngữ nghĩa chuyển hướng. Không dùng 410 khi tài nguyên vẫn được cung cấp ở một URI mới và mục tiêu API là hướng client tới URI đó.

Redirect có đánh đổi về client, cache, bảo toàn method và thông tin xác thực; cần cân nhắc migration contract riêng. Với tài nguyên không có quyền thấy, **không phát Location làm lộ URI mới** chỉ để giữ redirect nhất quán.

## 5. Tài nguyên đã xóa: vòng đời, soft delete và tombstone

### 5.1. Xóa vật lý, xóa mềm và ngừng cung cấp URI

| Trạng thái nội bộ | Ví dụ lưu trữ | Ý nghĩa ở API đọc thông thường |
|---|---|---|
| Chưa tồn tại | Chưa có bản ghi | 404 |
| Đang hoạt động | row có deleted_at = null | 200 nếu được phép đọc |
| Xóa mềm (soft delete) | row vẫn lưu, deleted_at có giá trị | 404 theo mặc định che giấu; 410 nếu được phép công bố Gone |
| Bản ghi chỉ còn trong archive | Dữ liệu vận hành đã dừng | 404/410 ở URI cũ theo hợp đồng; archive có API riêng nếu được phép |
| Xóa vật lý, còn tombstone metadata | Bảng tombstone hoặc event lịch sử | Có thể trả 410 khi chính sách và quyền cho phép |
| Xóa vật lý, không còn bằng chứng | Không biết từng tồn tại hay không | 404 |

**Tombstone** là bản ghi trạng thái tối thiểu giúp hệ thống biết tài nguyên từng tồn tại, đã bị xóa hoặc không còn phục vụ. Tombstone có thể cần cho đồng bộ, chống tạo lại ID, xử lý event trễ hoặc trả 410; nhưng bản thân tombstone cũng có dữ liệu cần bảo vệ và vòng đời lưu giữ.

### 5.2. Minh họa vòng đời xóa

Một client có quyền gửi:

~~~http
DELETE /api/orders/42 HTTP/1.1
Authorization: Bearer <access-token>
~~~

Hệ thống hoàn thành xóa theo hợp đồng và trả:

~~~http
HTTP/1.1 204 No Content
~~~

Sau đó:

~~~http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 404 Not Found
Cache-Control: no-store
~~~

Đây là hành vi hợp lệ khi API **không công bố lịch sử xóa** trên URI đọc. Nếu chính sách cho phép biết tài nguyên đã bị ngừng lâu dài, GET có thể trả 410:

~~~http
HTTP/1.1 410 Gone
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Gone",
  "status": 410,
  "detail": "Tài nguyên đã ngừng được cung cấp"
}
~~~

**Không diễn giải 204 của DELETE là yêu cầu GET sau đó cũng phải trả 204.** 204 chỉ cho biết request trước thành công và không có response body; nó không biểu diễn việc tìm không thấy một tài nguyên.

Nếu xóa **bất đồng bộ** và server chỉ nhận yêu cầu xử lý, DELETE có thể trả 202 Accepted theo hợp đồng. Trạng thái GET trong lúc đang xử lý phải được công bố rõ: tài nguyên có thể còn đọc được, ở trạng thái DELETING, hoặc bị ẩn sớm theo chính sách. Không hứa rằng mọi GET ngay sau 202 đều phải trả 404.

### 5.3. “Đã xóa” ở tầng API không đồng nghĩa xóa khỏi mọi bản sao

Một row có deleted_at không null vẫn nằm trong DB. Dữ liệu cũng có thể nằm trong backup, snapshot, audit log, event store hoặc archive theo chính sách lưu giữ. GET trả 404/410 là **trạng thái truy cập representation**, không chứng minh dữ liệu đã bị xóa khỏi hệ thống lưu trữ hoặc đáp ứng một yêu cầu xóa dữ liệu cá nhân.

Cần tách:

- **Resource lifecycle:** khi nào URI phục vụ, bị ẩn hoặc bị ngừng.
- **Data retention/disposition:** dữ liệu nào được giữ, đến bao giờ, theo căn cứ gì, khi nào xóa an toàn.
- **Authorization:** ai được biết tài nguyên đã từng tồn tại hoặc có trạng thái đã xóa.

### 5.4. Khi nào nên chọn 410?

Chọn 410 khi đồng thời có căn cứ:

1. API biết việc truy cập tới tài nguyên **không còn và nhiều khả năng sẽ không phục hồi** ở URI đó.
2. Việc công khai rằng tài nguyên đã tồn tại/đã ngừng **không vi phạm chính sách riêng tư hoặc phân quyền**.
3. Client có lợi khi phân biệt Gone với Not Found, ví dụ xóa bookmark cũ hoặc đồng bộ trạng thái.
4. Server có cách xác định tình trạng Gone đáng tin cậy, chẳng hạn tombstone hợp lệ.

Nếu thiếu căn cứ về tính lâu dài hoặc không muốn tiết lộ, **404 là lựa chọn đúng và an toàn hơn**. Không dùng 410 đơn thuần vì một cờ soft-delete hiện có trong DB; bản ghi có thể được phục hồi hoặc chính sách không cho tiết lộ.

## 6. Không được phép thấy: 401, 403 và kỹ thuật che giấu bằng 404

### 6.1. Hai tầng quyền cần tách riêng

**Tầng 1 — Quyền vào API:** client có được gọi endpoint đọc đơn không? Ví dụ token phải có scope orders.read. Không có token → 401; token hợp lệ nhưng thiếu scope → 403 theo chính sách cho biết quyền của endpoint.

**Tầng 2 — Quyền trên từng tài nguyên:** người gọi có được thấy **đơn cụ thể này** không? Ví dụ đơn thuộc tenant khác. Một API nhiều tenant thường muốn người gọi không thể phân biệt “ID tồn tại ở tenant khác” với “ID hoàn toàn không tồn tại”, nên trả 404 trong cả hai trường hợp.

~~~mermaid
flowchart LR
    C[Client thuộc tenant A] --> API[GET /api/orders/id]
    API --> AUTH[Kiểm tra token và scope]
    AUTH --> LOOKUP[SELECT theo id + tenant A + còn active]
    LOOKUP --> YES{Có record được phép đọc?}
    YES -- Có --> OK[200 + representation]
    YES -- Không --> NF[404 chung]
    DB[(Đơn của tenant B)] -. Không truy xuất qua phạm vi A .-> LOOKUP
~~~

Điều quan trọng là **truy vấn được giới hạn theo tenant/ACL**, thay vì đọc toàn bộ database rồi lộ thông tin qua lỗi trả về.

### 6.2. Rủi ro enumeration

Một API có thể làm lộ sự tồn tại của đơn hàng nếu trả:

~~~text
ID thật của tenant khác   -> 403 "Bạn không sở hữu đơn này"
ID không có trong DB      -> 404 "Không có đơn"
ID đã xóa                 -> 410 "Đơn đã bị xóa"
~~~

Kẻ tấn công thử nhiều ID có thể dựng danh sách đơn từng tồn tại, dù không đọc được nội dung. Nếu đó là thông tin nhạy cảm, chính sách tốt hơn là:

~~~text
ID thật của tenant khác   -> 404 "Không tìm thấy tài nguyên"
ID không có trong DB      -> 404 "Không tìm thấy tài nguyên"
ID đã xóa mà không có quyền biết -> 404 "Không tìm thấy tài nguyên"
~~~

**Chỉ thay status/body chưa đủ.** Các khác biệt về thời gian phản hồi, kích thước body, header, cache, route hoặc rate-limit đôi khi vẫn tiết lộ thông tin. Cần áp dụng cùng một policy cho đường đọc, log, observability và các endpoint phụ, đồng thời giới hạn tốc độ thăm dò bất thường.

### 6.3. Khi nào 403 vẫn phù hợp?

403 vẫn đúng khi **việc thông báo có tài nguyên hoặc hành động bị cấm là chấp nhận được**. Ví dụ:

- API quản trị trả 403 vì nhân viên có quyền xem tài nguyên nhưng không được xuất nội dung nhạy cảm.
- Endpoint đọc đơn chỉ dành cho scope orders.read; token hiện tại thiếu scope.
- Người dùng đã được thông báo rõ về tài nguyên trong quy trình nghiệp vụ nhưng thiếu quyền truy cập nội dung theo trạng thái hiện tại.

Không nên cố trả 404 cho mọi lỗi quyền mà không cân nhắc trải nghiệm client: 401/403 cho phép client biết khi nào cần đăng nhập lại hoặc xin quyền cao hơn. **Chính sách che giấu phải dựa trên mô hình đe dọa**, không phải một quy tắc status duy nhất cho toàn ứng dụng.

### 6.4. Không suy luận tenant từ dữ liệu tùy ý của request

Nếu tenant_id được truyền trực tiếp qua query parameter:

~~~http
GET /api/orders/42?tenantId=tenant-b
~~~

thì server **không được coi tenantId do client khai báo là bằng chứng quyền sở hữu**. Tenant phải được xác định hoặc kiểm chứng qua authentication context, token claims tin cậy và các quy tắc phân quyền của server. Nếu hệ thống hỗ trợ quản trị xuyên tenant, quyền quản trị đó cần được xác minh rõ và ghi audit.

## 7. Cache: 404 và 410 có thể được lưu lại

Một điểm dễ bỏ sót: theo quy tắc HTTP, **404 và 410 có thể được cache theo heuristic** nếu không có chỉ dẫn ngăn cản và điều kiện cache khác cho phép. Vì vậy, phản hồi “không tồn tại” không mặc nhiên biến mất ngay khi tài nguyên mới được tạo hoặc phục hồi.

Ví dụ:

1. Client gọi GET /api/reports/42 trước khi báo cáo được tạo và nhận 404.
2. Proxy hoặc cache lưu phản hồi 404 theo chính sách áp dụng.
3. Báo cáo 42 được tạo sau đó.
4. Client vẫn có thể thấy 404 trong thời gian cache còn hiệu lực.

### 7.1. Chọn cache policy theo loại tài nguyên

| Loại tài nguyên | Chính sách tham khảo | Vì sao |
|---|---|---|
| Đơn hàng cá nhân, hồ sơ nhạy cảm | Cache-Control: no-store cho 404/410/403 và dữ liệu nhạy cảm nếu chính sách yêu cầu | Tránh lưu và chia sẻ nhầm phản hồi phân quyền |
| Dữ liệu công khai, không tồn tại tạm thời | Cache-Control: public, max-age=30 nếu phù hợp | Giảm truy vấn lặp, nhưng tạo cửa sổ negative cache |
| Trang công khai đã ngừng lâu dài | 410 với freshness phù hợp nếu muốn công bố và cho cache | Tiết kiệm tài nguyên, chấp nhận độ trễ cập nhật |
| Tài nguyên dự kiến có thể phục hồi ngay | no-store hoặc TTL ngắn | Không giữ nhầm 404 cũ sau khi restore |

Những giá trị max-age chỉ minh họa. **Cacheability còn phụ thuộc method, trạng thái authentication, chỉ dẫn cache và chính sách tầng trung gian**. Không dùng public cho phản hồi riêng tư phụ thuộc vào người gọi hoặc tenant.

### 7.2. 304 Not Modified không thay thế 404/410

Giả sử client từng nhận:

~~~http
HTTP/1.1 200 OK
ETag: "order-v3"
Content-Type: application/json

{"id":"42","status":"PENDING"}
~~~

Request tiếp:

~~~http
GET /api/orders/42 HTTP/1.1
If-None-Match: "order-v3"
~~~

Nếu tài nguyên **vẫn tồn tại, client có quyền đọc và validator phù hợp**, server có thể trả 304 Not Modified. Nhưng nếu đơn đã bị xóa hoặc client bị thu hồi quyền, server phải đánh giá trạng thái/quyền hiện tại trước khi quyết định điều kiện cache; **không được trả 304 chỉ vì ETag client đưa đến khớp một phiên bản cũ**.

Cache và ETag là cơ chế tối ưu đọc, **không cấp lại quyền truy cập** vào tài nguyên đã bị ẩn.

## 8. GET và HEAD phải phản ánh cùng trạng thái

HEAD yêu cầu metadata tương ứng với GET nhưng **không có response body**. Nếu GET /api/orders/{id} sẽ trả 404 vì không tồn tại hoặc không được phép tiết lộ, HEAD tương ứng cũng nên trả 404 với chính sách quyền đó. Nếu GET sẽ trả 410, HEAD thường trả 410. Không cho phép HEAD làm lộ sự tồn tại mà GET đã che giấu.

~~~http
HEAD /api/orders/42 HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 404 Not Found
Cache-Control: no-store
~~~

Không gửi JSON body với HEAD. Một ứng dụng tự cài đặt HEAD khác với GET cần kiểm thử hai đường để tránh lộ thông tin qua header, mã trạng thái hoặc response time.

### 8.1. Điều kiện và cạnh tranh trạng thái

Giữa thời điểm xác thực, kiểm tra quyền và đọc DB, trạng thái có thể thay đổi: quyền bị thu hồi, đơn bị xóa, hoặc ownership được chuyển. Với dữ liệu nhạy cảm, cần xác định mức nhất quán cần có và cách kiểm tra lại quyền trong cùng phạm vi giao dịch/đọc có ý nghĩa.

Không thể bảo đảm tuyệt đối rằng mọi thay đổi đồng thời đều bị loại bỏ nếu đọc từ cache/replica trễ; phải nêu rõ các cam kết về độ mới dữ liệu và thời điểm hiệu lực của việc thu hồi quyền. Khi hệ thống phân tán hoặc có read replica, cache phân quyền cần được vô hiệu hóa đúng lúc để tránh trả 200 cho tài nguyên vừa bị cấm.

## 9. Thiết kế response lỗi theo Problem Details

RFC 9457 định nghĩa định dạng **Problem Details for HTTP APIs**, thường dùng media type application/problem+json. Nó cho client một cấu trúc lỗi có thể xử lý:

~~~json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Không tìm thấy tài nguyên",
  "instance": "/api/orders/42"
}
~~~

Các trường:

| Trường | Mục đích | Lưu ý bảo mật |
|---|---|---|
| type | Định danh loại vấn đề; about:blank sử dụng ý nghĩa chung của status | Không tạo URL loại lỗi chứa thông tin riêng |
| title | Tên ngắn của lỗi | Nhất quán với status/loại lỗi |
| status | Mã HTTP tương ứng | Phải khớp status của phản hồi |
| detail | Mô tả dành cho lần lỗi này | Không tiết lộ tồn tại/owner/tenant nếu trả 404 che giấu |
| instance | Tham chiếu lần xảy ra lỗi | Hạn chế đưa thông tin nhạy cảm vào URL |

**Không nên trả:**

~~~json
{
  "status": 404,
  "detail": "Đơn 42 tồn tại nhưng thuộc tenant-b và đã bị xóa"
}
~~~

Body này phá vỡ mục tiêu che giấu dù status là 404. Dùng một thông điệp chung cho trường hợp không tồn tại và không được phép thấy, còn thông tin chi tiết phục vụ điều tra ghi trong log nội bộ có giới hạn quyền và chính sách lưu giữ.

### 9.1. Mã lỗi nội bộ có nên khác nhau?

Có thể lưu mã nội bộ như RESOURCE_MISSING, RESOURCE_HIDDEN, RESOURCE_GONE trong telemetry có kiểm soát để hỗ trợ vận hành. Tuy nhiên, nếu API đang che giấu tồn tại, **không xuất các mã đó trực tiếp cho người gọi không đủ quyền**.

Client thường cần xử lý hợp lý:

- **401:** kiểm tra token, đăng nhập lại hoặc lấy token hợp lệ.
- **403:** báo thiếu quyền, không tự retry vô hạn cùng token.
- **404:** hiển thị không tìm thấy/không khả dụng, không mặc định tạo một tài nguyên mới với ID đó.
- **410:** nếu hợp đồng cho biết Gone, ngừng truy cập URI cũ hoặc xóa liên kết cũ theo quy trình.

Không nên tự động retry 404/410 liên tục; nếu nghiệp vụ có trạng thái eventual consistency và kỳ vọng tài nguyên xuất hiện sau đó, phải có **hợp đồng polling riêng**, thời hạn và backoff.

## 10. Triển khai ví dụ với Java/Spring

### 10.1. Mục tiêu thiết kế

Ta triển khai GET /api/orders/{id} với các quy tắc:

- Spring Security OAuth2 Resource Server xác thực Bearer JWT.
- Người gọi cần scope orders.read mới được vào endpoint.
- Tenant ID lấy từ **JWT đã được xác thực**, không lấy từ query parameter tự khai báo.
- Truy vấn lấy chỉ các đơn **đang hoạt động và thuộc tenant**.
- Không có record trong tập được phép đọc → 404 chung, kể cả record thật thuộc tenant khác hoặc đã soft-delete.
- 410 là **tính năng tùy chọn** cho một loại tài nguyên mà hợp đồng cho phép công bố tombstone.

### 10.2. Truy vấn dữ liệu cần kiểm soát scope

Ví dụ SQL mô tả truy vấn đọc authoritative:

~~~sql
SELECT id, status, total_amount, created_at
FROM orders
WHERE id = :id
  AND tenant_id = :authorized_tenant_id
  AND deleted_at IS NULL;
~~~

Biến authorized_tenant_id phải được lấy từ **ngữ cảnh đã xác thực và xác minh quyền**, không chấp nhận tùy ý từ client. Query trả 0 dòng cho cả ID không có, khác tenant và soft-deleted. Thiết kế này làm giảm khả năng lộ tài nguyên qua quyết định status.

Với phân quyền phức tạp (shared resources, ACL theo nhóm, người được ủy quyền), predicate truy vấn cần bao gồm đầy đủ điều kiện hoặc một cơ chế authorization đáng tin cậy tương đương. Tenant isolation **không tự thay thế** mọi kiểm tra quyền trên tài nguyên.

### 10.3. Spring REST controller

Ví dụ dưới dùng Spring Web và Spring Security, giả định OrderReadService đã triển khai truy vấn chỉ trả dữ liệu được phép đọc. Mã tập trung vào status và bảo vệ phản hồi:

~~~java
import java.util.Optional;
import java.util.UUID;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderReadController {
    private final OrderReadService orderReadService;

    public OrderReadController(OrderReadService orderReadService) {
        this.orderReadService = orderReadService;
    }

    @GetMapping("/{id}")
    public ResponseEntity<?> getOrder(
            @PathVariable UUID id,
            @AuthenticationPrincipal Jwt jwt) {

        // Spring Security phải xác thực JWT trước khi gọi controller.
        String tenantId = jwt.getClaimAsString("tenant_id");
        if (tenantId == null || tenantId.isBlank()) {
            throw new AccessDeniedException("Missing tenant context");
        }

        Optional<OrderView> order =
                orderReadService.findActiveVisibleOrder(id, tenantId);

        if (order.isPresent()) {
            return ResponseEntity.ok()
                    .cacheControl(CacheControl.noStore())
                    .body(order.get());
        }

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Không tìm thấy tài nguyên"
        );
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .cacheControl(CacheControl.noStore())
                .body(problem);
    }
}
~~~

OrderReadService và OrderView là kiểu ứng dụng cần được định nghĩa riêng. Dịch vụ **không được** cài đặt theo kiểu findById(id) rồi trả 403 nếu record thuộc tenant khác, bởi điều đó có thể tiết lộ sự tồn tại. Điều kiện truy vấn cũng phải bảo vệ việc lọc trạng thái xóa và quyền chia sẻ tài nguyên.

Trong cấu hình thực tế, cần xác thực chính xác JWT signature, issuer, audience, expiration và cách ánh xạ scope/tenant claim. Không tự tin mọi trường JWT do client cung cấp trước khi đi qua cơ chế xác thực đáng tin cậy.

### 10.4. Chặn thiếu token/scope ở lớp Spring Security

Ví dụ cấu hình security cho API (Spring Security 6):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET,
                                "/api/orders/**"
                        ).hasAuthority("SCOPE_orders.read")
                        .anyRequest().denyAll()
                )
                .oauth2ResourceServer(oauth -> oauth
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Lớp security xử lý authentication và scope trước controller: **401** kèm Bearer challenge khi không có credential hợp lệ, **403** khi xác thực được nhưng không đủ scope (tùy cấu hình error handler). Controller xử lý việc không tìm thấy tài nguyên **trong phạm vi được phép** bằng 404.

Trong production cần cấu hình resource server đầy đủ, entry point, access denied handler, chính sách session/CSRF phù hợp loại client, mapping authority và cách trả body Problem Details thống nhất. Nếu muốn che giấu cả lỗi thiếu scope bằng 404, phải thiết kế handler nhất quán và vẫn xem xét nghĩa vụ challenge cho trường hợp thiếu authentication.

### 10.5. Tùy chọn 410 khi được phép tiết lộ tombstone

Nếu API quản lý **tài liệu công khai đã ngừng cung cấp**, hoặc có endpoint lịch sử chỉ cho người có quyền đọc lịch sử, controller có thể bổ sung bước kiểm tra tombstone **sau khi đã xác nhận quyền**:

~~~java
if (historyPolicy.canRevealDeletion(authenticationContext)
        && tombstoneService.hasGoneMarkerForVisibleResource(
                id, authorizedTenantId)) {

    ProblemDetail gone = ProblemDetail.forStatusAndDetail(
            HttpStatus.GONE,
            "Tài nguyên đã ngừng được cung cấp"
    );
    return ResponseEntity.status(HttpStatus.GONE)
            .cacheControl(CacheControl.noStore())
            .body(gone);
}
~~~

Đoạn này là **fragment minh họa** sau bước kiểm tra quyền, không phải controller độc lập. Cần bảo đảm phương thức hasGoneMarkerForVisibleResource **không tra cứu rộng rồi tiết lộ bản ghi tenant khác** và marker có ngữ nghĩa Gone đáng tin cậy. Khi không có tombstone được phép công bố, trả 404.

Không nhất thiết dùng 410 cho mọi bản ghi soft-delete; nhiều ứng dụng cố tình không để người dùng thông thường nhận biết sự tồn tại của bản ghi xóa.

## 11. Kiểm thử API theo ma trận truy cập và vòng đời

### 11.1. Ma trận kiểm thử tối thiểu

| STT | Token và quyền | Trạng thái tài nguyên | Kết quả mong đợi |
|---|---|---|---|
| 1 | Không token | Bất kỳ | 401 + WWW-Authenticate |
| 2 | Token hết hạn hoặc không hợp lệ | Bất kỳ | 401, không tiết lộ dữ liệu |
| 3 | Token hợp lệ, thiếu orders.read | Bất kỳ | 403 hoặc 404 nếu hợp đồng có chính sách che giấu |
| 4 | Token tenant A có orders.read | Đơn của tenant A đang hoạt động | 200, chỉ dữ liệu được phép |
| 5 | Token tenant A có orders.read | ID chưa từng tồn tại | 404 chung |
| 6 | Token tenant A có orders.read | ID của tenant B | 404 giống trường hợp 5 |
| 7 | Token tenant A có orders.read | Đơn A đã soft-delete, không công bố | 404 |
| 8 | Vai trò được phép xem lịch sử | Tombstone hợp lệ được công bố | 410 theo hợp đồng |
| 9 | Token tenant A có orders.read | Collection hợp lệ, không có đơn | 200 với danh sách rỗng |
| 10 | Token tenant A có orders.read | HEAD của đơn không tồn tại/không được phép thấy | 404, không body |
| 11 | Token tenant A có orders.read | If-None-Match với đơn vẫn tồn tại/được phép đọc | 304 nếu validator khớp |
| 12 | Token bị thu hồi quyền | ETag cũ từng khớp | Không trả 304 chỉ vì validator cũ |
| 13 | Token tenant A có orders.read | DB bị timeout | Mã lỗi hệ thống phù hợp, không giả 404 |

Test **so sánh trường hợp 5, 6 và 7** phải kiểm tra không chỉ status mà cả Problem Details công khai, Cache-Control và khác biệt dễ lộ thông tin. Thời gian phản hồi có nhiễu tự nhiên nên không lấy một lần đo làm bảo đảm không có timing side channel; security review cần đánh giá theo mô hình đe dọa.

### 11.2. Ví dụ test với MockMvc và Spring Security Test

Fragment dưới đây minh họa cách yêu cầu tenant A truy cập một ID ngoài phạm vi được phép. Giả định bộ test đã khởi tạo MockMvc, dữ liệu và OrderReadService để ID đó không có record hợp lệ trong tenant A.

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

// Phần bên trong lớp test đã cấu hình MVC, security và dữ liệu:
@Test
void orderFromAnotherTenantIsHidden() throws Exception {
    mockMvc.perform(get(
            "/api/orders/5a009747-e2f2-4417-8700-650b0686e1f1")
            .with(jwt()
                    .jwt(jwt -> jwt.claim("tenant_id", "tenant-a"))
                    .authorities(new SimpleGrantedAuthority(
                            "SCOPE_orders.read"))))
        .andExpect(status().isNotFound())
        .andExpect(header().string(
                "Cache-Control", "no-store"))
        .andExpect(jsonPath("$.status").value(404))
        .andExpect(jsonPath("$.title").value("Not Found"));
}
~~~

**Lưu ý:** đây là test fragment đặt trong class đã inject MockMvc (ví dụ một trường mockMvc); cần cấu hình bảo mật phù hợp và bảo đảm mock/dữ liệu phản ánh tenant khác. Test riêng cho token thiếu/hết hạn phải chạy qua authentication thực hoặc mô phỏng đúng cách; jwt() trong Spring Security Test có thể cung cấp principal giả lập, không tự chứng minh việc xác minh chữ ký JWT thực tế.

### 11.3. Kiểm tra GET và HEAD bằng curl

Để xem status và header:

~~~bash
curl -i \
  -H 'Authorization: Bearer <test-token>' \
  -H 'Accept: application/problem+json' \
  https://api.example.test/api/orders/42
~~~

Kiểm tra HEAD:

~~~bash
curl -I \
  -H 'Authorization: Bearer <test-token>' \
  https://api.example.test/api/orders/42
~~~

Chỉ dùng token và endpoint thử nghiệm được phép; tránh lưu hoặc chia sẻ stdout/verbose log chứa secret. Nếu cần kiểm chứng cache, quan sát Cache-Control và hành vi qua proxy được cấu hình tương đương production. Không suy đoán chính sách cache chỉ từ lần gọi curl trực tiếp.

## 12. OpenAPI: diễn đạt rõ hợp đồng lỗi

Ví dụ OpenAPI rút gọn cho endpoint đọc đơn:

~~~yaml
paths:
  /api/orders/{id}:
    get:
      summary: Read an order visible to the caller
      description: >
        Returns 404 when the order does not exist, has been hidden
        after deletion, or is outside the caller's permitted scope.
        A 410 response is reserved for approved history endpoints.
      security:
        - bearerAuth: []
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Visible active order
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderView'
        '401':
          description: Missing or invalid authentication
          headers:
            WWW-Authenticate:
              schema:
                type: string
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'
        '403':
          description: Authenticated but insufficient endpoint permission
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'
        '404':
          description: Missing, deleted, or deliberately hidden resource
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    OrderView:
      type: object
      properties:
        id:
          type: string
          format: uuid
        status:
          type: string
      required:
        - id
        - status
    Problem:
      type: object
      properties:
        type:
          type: string
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
~~~

Ví dụ không khai báo 410 trong hợp đồng GET đơn thông thường vì chính sách của endpoint **không công khai trạng thái đã xóa**. Nếu có endpoint riêng như GET /api/order-history/{id} và được phép trả Gone, cần khai báo 410 tại endpoint đó và kiểm thử quyền tương ứng.

OpenAPI chỉ là phần hợp đồng tĩnh. Phân quyền tenant, khả năng bảo vệ ẩn danh và cache behavior vẫn cần được chứng minh bằng code, test và cấu hình runtime.

## 13. Một số tình huống dễ trả sai status

### 13.1. Quyền bị thu hồi sau khi client đã cache đơn

Client từng lấy được đơn và ETag. Hôm sau quyền được thu hồi. GET với If-None-Match cũ **không được trả 304 chỉ vì ETag trùng**, bởi 304 có thể cho phép client tiếp tục dùng representation đã cache. Authorization phải được đánh giá theo chính sách hiện hành.

### 13.2. Đơn hàng soft-delete nhưng có thể khôi phục

Đơn được gắn deleted_at, nhưng quản trị viên có thể restore trong 30 ngày. Nếu API cho người dùng thông thường xem đơn chỉ khi active, **404** là phản hồi tự nhiên. Với quyền quản trị vào một endpoint trash riêng, có thể trả **200 với representation của bản ghi đã xóa**, nếu họ được phép đọc metadata đó. Không mặc định 410 cho một trạng thái có thể phục hồi.

### 13.3. Tài nguyên hết hạn theo thời gian

Một link tải file có thời hạn sử dụng hoặc tài liệu đã hết hạn công bố có thể dùng **404** để che giấu, hoặc **410** nếu chủ thể có quyền được biết nó đã ngừng cung cấp và tình trạng có khả năng lâu dài. Với signed URL, việc kiểm tra chữ ký/hạn dùng và phản hồi không được vô tình tiết lộ file gốc.

### 13.4. Record thuộc tenant khác nhưng ID có thể đoán được

Nếu hệ thống trả 403 cho ID có thật ở tenant B và 404 cho ID sai, người gọi tenant A có thể dò ID. Dùng truy vấn theo tenant của người gọi, trả cùng 404 và áp dụng rate limiting/audit cho hoạt động dò quét.

### 13.5. Hệ thống phụ thuộc bị lỗi

Nếu database hoặc dịch vụ quyền gặp lỗi, không coi kết quả truy vấn bất định là “không tồn tại”. Lỗi **5xx/503** phù hợp theo loại sự cố và hợp đồng, với thông điệp an toàn. Nếu có circuit breaker hoặc cache fallback, phải xác định rõ khi nào có thể phục vụ dữ liệu cũ và yêu cầu nhất quán/bảo mật.

### 13.6. Bản ghi đã xóa nhưng worker còn xử lý sự kiện

Khi một đơn bị xóa/hủy ở tầng nghiệp vụ, consumer có thể còn nhận event trễ. Trạng thái HTTP khi GET được quyết định bởi **mô hình tài nguyên hiện hành**; xử lý event phải kiểm tra version, idempotency, tombstone và invariant để không vô tình tái tạo tài nguyên bị xóa. Trả 410 không tự ngăn sự kiện ghi lại vào DB.

## 14. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Trả 403 cho tài nguyên thuộc tenant khác trong API cần che giấu | Lộ ID tồn tại qua enumeration | Dùng query theo tenant/ACL và 404 chung |
| Trả 410 cho mọi soft-delete | Tiết lộ lịch sử hoặc sai ý nghĩa có thể restore | Phân biệt vòng đời và quyền công bố tombstone |
| Trả 404 khi thiếu token của endpoint yêu cầu xác thực | Client không biết cần authentication | 401 + WWW-Authenticate phù hợp |
| Dùng 401 cho người đã xác thực nhưng thiếu scope | Gây retry đăng nhập không hiệu quả | 403 hoặc 404 có chủ đích nếu cần che giấu |
| Trả 404 khi danh sách filter rỗng | Sai ngữ nghĩa của collection | 200 với items rỗng và metadata phân trang |
| Trả 404 khi DB timeout | Che mất sự cố; dễ bị negative cache | Dùng lỗi 5xx phù hợp và alert |
| Trả 304 trước kiểm tra quyền | Có thể cho client dùng cache của tài nguyên đã bị cấm | Đánh giá quyền/trạng thái rồi mới conditional request |
| Chỉ kiểm tra owner sau khi đọc dữ liệu tùy ý | Nguy cơ lộ qua lỗi, log hoặc timing | Áp dụng scope trong query, defense in depth |
| Lấy tenantId trực tiếp từ query/header không tin cậy | Truy cập chéo tenant | Lấy/đối chiếu tenant từ authentication context |
| Body 404 tiết lộ “thuộc khách B, đã xóa” | Status che giấu mất tác dụng | Problem Details chung cho người không có quyền |
| Cache 404/410 riêng tư không có chính sách | Phản hồi lỗi bị lưu ngoài ý muốn hoặc kéo dài | Cache-Control phù hợp, xét negative cache |
| HEAD có status khác GET khi cùng quyền | Rò rỉ thông tin tồn tại | Kiểm thử GET/HEAD theo cùng chính sách |

## 15. Bài tập thực hành

### Bài 1 — Chọn mã trạng thái

Chọn phản hồi và giải thích:

1. Người dùng chưa đăng nhập gọi GET /api/orders/{id} của API private.
2. Người dùng đăng nhập nhưng không có scope đọc đơn.
3. Người dùng tenant A có scope đọc đơn, gọi ID không có trong tenant A.
4. ID thật thuộc tenant B, API yêu cầu không tiết lộ tồn tại liên tenant.
5. Tài liệu công khai đã ngừng cung cấp vĩnh viễn; API biết tình trạng này và muốn client xóa liên kết.
6. Người dùng có quyền gọi GET /api/orders, nhưng không có đơn nào.

**Gợi ý:** (1) 401 kèm challenge; (2) 403 theo chính sách endpoint, có thể 404 nếu che giấu được thiết kế; (3) 404; (4) 404 cùng body với (3); (5) 410; (6) 200 với collection rỗng.

### Bài 2 — Soft delete và cache

Đơn của tenant A đã được soft-delete nhưng có thể restore trong 14 ngày. Client từng cache representation có ETag và gửi If-None-Match sau khi bị thu hồi quyền.

**Câu hỏi:** GET thông thường nên trả gì? Có được trả 304 không? Quản trị viên có thể truy xuất dữ liệu đã xóa bằng cách nào?

**Gợi ý:** GET thông thường nên trả 404 theo chính sách ẩn bản ghi xóa; không trả 304 vì quyền và trạng thái hiện tại thay đổi. Quản trị viên cần endpoint hoặc phạm vi quyền riêng để xem dữ liệu đã xóa (có thể 200 với representation phù hợp) và audit truy xuất.

### Bài 3 — Tìm lỗi bảo mật trong controller

~~~java
Order order = repository.findById(id).orElse(null);
if (order == null) {
    return notFound();
}
if (!order.getTenantId().equals(request.getParameter("tenantId"))) {
    return forbidden("Order belongs to " + order.getTenantId());
}
return ok(order);
~~~

**Câu hỏi:** Ít nhất ba lỗi của đoạn mã là gì?

**Gợi ý:** tin tenantId do request khai báo; truy vấn không giới hạn theo tenant đã xác thực; trả 403 kèm tenant thực làm lộ tài nguyên; trả trực tiếp entity có thể lộ trường nội bộ; chưa kiểm tra scope, soft deletion hoặc quyền chia sẻ chi tiết. Thiết kế lại bằng authentication context và query theo phạm vi được phép.

### Bài 4 — Trạng thái HTTP và vòng đời xóa

Một tài liệu công khai được gỡ khỏi website nhưng vẫn lưu trong archive phục vụ kiểm toán. Người dùng thường không được truy cập archive.

**Câu hỏi:** Có thể dùng 410 ở URL công khai không? Điều này có nghĩa dữ liệu đã bị xóa vật lý không?

**Gợi ý:** Có thể dùng 410 nếu việc ngừng cung cấp URL là lâu dài và chính sách cho phép công khai; không đồng nghĩa dữ liệu đã xóa khỏi archive/backup. Phân quyền archive phải độc lập với trạng thái URL công khai.

## 16. Checklist trước khi phát hành API đọc tài nguyên

- [ ] Đã phân biệt GET tài nguyên đơn lẻ và GET collection không có phần tử?
- [ ] Có quy tắc rõ cho 401, 403, 404 và 410 theo authentication, authorization và trạng thái tài nguyên?
- [ ] Với endpoint private, 401 có challenge WWW-Authenticate phù hợp?
- [ ] Tenant/ACL được xác định từ nguồn tin cậy và áp dụng trong truy vấn hoặc cơ chế tương đương?
- [ ] ID không tồn tại, khác tenant và đã xóa bị ẩn có response công khai nhất quán?
- [ ] Chỉ công bố 410 khi tài nguyên Gone được biết là có khả năng lâu dài và người gọi có quyền biết?
- [ ] Soft-delete, restore, archive, retention và xóa vật lý có mô hình vòng đời rõ ràng?
- [ ] Cấu trúc Problem Details không lộ owner, tenant, ID khác, trạng thái xóa hay stack trace?
- [ ] Cache-Control đúng cho 404/410/403 và dữ liệu riêng tư; đã đánh giá negative caching?
- [ ] Conditional GET chỉ trả 304 khi representation hiện còn và người gọi vẫn được phép đọc?
- [ ] HEAD không có body và không làm lộ trạng thái khác GET?
- [ ] Không chuyển lỗi hạ tầng hoặc timeout DB thành 404 giả?
- [ ] Có test cho token thiếu/hết hạn, thiếu scope, khác tenant, soft-delete, Gone, collection rỗng và lỗi DB?
- [ ] Đã cập nhật OpenAPI, tài liệu vòng đời tài nguyên, rate limiting, telemetry và audit?

## 17. Kết luận

Khi đọc một tài nguyên REST, **404** có thể biểu diễn không tồn tại, không có representation hiện tại, đã xóa nhưng bị ẩn, hoặc sự tồn tại bị che giấu theo quyền. **410** dùng khi server biết tài nguyên không còn khả dụng tại URI và tình trạng đó có khả năng lâu dài, đồng thời được phép công bố. **401** yêu cầu thông tin xác thực hợp lệ; **403** diễn đạt việc từ chối thực hiện khi người gọi không có quyền theo chính sách.

Thiết kế tốt không chỉ chọn status theo trạng thái của một row trong database. Nó kết hợp **quyền truy cập, vòng đời tài nguyên, tính nhất quán, cache và hợp đồng dữ liệu**. Với REST API nhiều người dùng hoặc nhiều tenant, hãy đặt ranh giới phân quyền vào truy vấn/miền nghiệp vụ, kiểm thử các trường hợp che giấu và chỉ trả thông tin mà người gọi có quyền biết.
