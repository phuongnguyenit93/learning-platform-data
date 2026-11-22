# Tập hợp rỗng và tài nguyên tập hợp không tồn tại

## 1. Bài toán: không có phần tử hay không có tài nguyên?

Một ứng dụng bán hàng gọi **GET /orders?status=SHIPPED**. API không tìm thấy đơn hàng nào phù hợp. Một ứng dụng khác gọi **GET /workspaces/w-404/tasks**, nhưng workspace **w-404** không tồn tại. Cả hai truy vấn đều không thể trả về bản ghi công việc, song **ý nghĩa nghiệp vụ khác hẳn**:

- Trong trường hợp đầu, tập hợp **orders vẫn tồn tại**, người gọi có quyền xem và kết quả lọc chỉ có **0 phần tử**.
- Trong trường hợp sau, tài nguyên cha **workspace** không tồn tại; theo hợp đồng của ví dụ, không có tập hợp con **tasks** hợp lệ dưới workspace đó.

Đối với REST API, quyết định quan trọng là phân biệt **“truy vấn thành công với kết quả rỗng”** và **“không có tài nguyên đích để truy vấn”**. Nếu trả **404 Not Found** cho mọi tập hợp rỗng, client có thể nhầm dữ liệu rỗng bình thường thành lỗi tài nguyên. Nếu luôn trả **200 OK** cho mọi URL bất kể tài nguyên cha có tồn tại hay không, API lại che lấp lỗi định danh hoặc đường dẫn, khiến việc kiểm thử, giám sát và xử lý nghiệp vụ trở nên khó khăn.

Trong module **INTEGRATION_API_REST**, quyết định này gắn với thiết kế **resource và URI, phương thức và mã trạng thái HTTP**, hợp đồng dữ liệu rõ ràng, phân trang, cache, xác thực/phân quyền, Problem Details, OpenAPI và triển khai Java/Spring.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **tài nguyên tập hợp**, **kết quả truy vấn tập hợp**, **tài nguyên phần tử** và **tài nguyên cha**.
2. Chọn **200**, **204**, **404** theo ngữ nghĩa của URI và hợp đồng API, tránh suy diễn từ số bản ghi.
3. Thiết kế phản hồi tập hợp rỗng nhất quán với **filter, sort, pagination, cursor và quyền truy cập**.
4. Hiểu trường hợp có thể dùng **403**, **404 để không tiết lộ sự tồn tại**, **410** và những mã khác không liên quan trực tiếp đến tập hợp rỗng.
5. Cân nhắc **cache, ETag/304, dữ liệu thay đổi đồng thời** và hiển thị trạng thái rỗng ở client.
6. Viết endpoint và hợp đồng OpenAPI rõ ràng, xử lý lỗi bằng Problem Details, kiểm thử các tình huống Java/Spring.

## 2. Xác định đối tượng đang được truy cập

### 2.1. Bốn khái niệm thường bị đánh đồng

| Khái niệm | URI ví dụ | Đặc điểm |
|---|---|---|
| **Tài nguyên tập hợp (collection resource)** | **/orders** | Đại diện danh sách/khả năng truy vấn các đơn hàng trong phạm vi quyền của caller |
| **Kết quả truy vấn (collection query result)** | **/orders?status=SHIPPED** | Biểu diễn tập hợp sau khi áp dụng bộ lọc; số phần tử có thể bằng 0 |
| **Tài nguyên phần tử (member resource)** | **/orders/o-123** | Đại diện cho một đơn hàng cụ thể, có thể tồn tại hoặc không |
| **Tập hợp con có tài nguyên cha (nested collection)** | **/workspaces/w-1/tasks** | Danh sách task gắn với một workspace xác định; tính hợp lệ phụ thuộc hợp đồng của tài nguyên cha |

Một **collection resource** không biến mất chỉ vì hiện tại nó không có phần tử. Hình dung một thư mục có thật nhưng chưa chứa tệp: thư mục rỗng vẫn khác với một đường dẫn trỏ đến thư mục không tồn tại.

### 2.2. Hai câu hỏi phải tách rời

Trước khi chọn HTTP status, hãy hỏi:

1. **Target resource theo URI có tồn tại và caller được phép truy cập hay không?**
2. **Nếu có, biểu diễn/truy vấn của tài nguyên đó chứa bao nhiêu phần tử?**

Ví dụ:

| Request | Tình trạng tài nguyên đích | Kết quả | Ứng viên phản hồi |
|---|---|---|---|
| GET /orders | Tập hợp orders hợp lệ | 0 đơn hàng | **200 OK** với tập hợp rỗng |
| GET /orders?status=PAID | Tập hợp orders hợp lệ; bộ lọc hợp lệ | Không đơn nào khớp | **200 OK** với tập hợp rỗng |
| GET /orders/o-999 | Không tồn tại đơn hàng o-999 hoặc API không muốn công bố sự tồn tại | Không có representation của phần tử | **404 Not Found** |
| GET /workspaces/w-1/tasks | Workspace w-1 tồn tại và caller được xem | Workspace chưa có task | **200 OK** với tập hợp rỗng |
| GET /workspaces/w-999/tasks | Workspace w-999 không tồn tại và theo hợp đồng không có subcollection ở URI này | Không có tài nguyên đích hợp lệ | **404 Not Found** |
| GET /workspaces/w-2/tasks | Workspace có thể tồn tại, nhưng caller không có quyền | Không được truy cập | **403**, hoặc **404** nếu chọn không tiết lộ sự tồn tại |

Những ví dụ trên là **quy ước thiết kế REST** cho các resource được mô tả, không có quy tắc HTTP bắt buộc rằng mọi URI có dạng **/{parent}/{id}/{children}** phải hoạt động y hệt. API phải xác định ngữ nghĩa của URI ngay từ hợp đồng.

### 2.3. Tập hợp có luôn được lưu dưới dạng bảng hay đối tượng riêng?

Không. **/orders** có thể là một tài nguyên truy vấn ảo được tạo từ cơ sở dữ liệu, search index hoặc dữ liệu tổng hợp; nó không nhất thiết có hàng “orders collection” trong database. Điều kiện tồn tại của **resource** đến từ **mô hình API** chứ không phải việc có bao nhiêu record trong bảng.

Ngược lại, nếu tổ chức cho phép tạo **named collections**, ví dụ **/saved-lists/list-42/items**, thì chính **saved list list-42** có vòng đời tạo/xóa riêng. Khi danh sách tồn tại mà không có item, truy vấn thành công trả tập hợp rỗng. Khi **list-42 đã bị xóa** và không còn URI hợp lệ cho subcollection của nó, trả 404 có thể phù hợp.

## 3. Đọc đúng ngữ nghĩa HTTP của 200, 204 và 404

### 3.1. 200 OK

**200 OK** cho biết request thành công. Với **GET**, response thông thường chứa biểu diễn tài nguyên được yêu cầu. Với collection query hợp lệ trả 0 phần tử, **200** cùng biểu diễn tập hợp rỗng là lựa chọn rất hữu ích:

~~~http
GET /orders?status=PAID HTTP/1.1
Host: api.example.test
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json

[]
~~~

Nếu API quy định **/orders** luôn trả JSON array, thì **[]** là một representation đúng kiểu dữ liệu. Client có thể giải mã thành collection rỗng, dùng cùng nhánh xử lý như khi có 1 hoặc 100 phần tử.

Nếu API quy định response là object có **items và metadata phân trang**, trả envelope rỗng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "items": [],
  "page": {
    "number": 0,
    "size": 20,
    "totalItems": 0,
    "totalPages": 0,
    "hasNext": false
  }
}
~~~

**Quan trọng:** Nếu contract dùng array, hãy giữ array; nếu dùng envelope, hãy giữ envelope. Không trả object khi có dữ liệu nhưng đổi sang array hoặc body trống khi rỗng. Sự nhất quán kiểu dữ liệu giúp giảm lỗi client và làm OpenAPI chính xác.

### 3.2. 204 No Content

**204 No Content** có nghĩa request đã thành công và server **không có nội dung bổ sung để gửi trong response**. Theo HTTP, response 204 **không được có message content**; không thể trả JSON **[]** kèm 204.

Ví dụ hình thức hợp lệ:

~~~http
GET /orders?status=PAID HTTP/1.1

HTTP/1.1 204 No Content
X-Request-ID: req-a8b3
~~~

GET 204 không bị cấm tuyệt đối. Tuy nhiên, với endpoint trả danh sách, 204 thường **kém hữu dụng hơn 200** vì:

- Không mang được **items: []**, **totalItems: 0**, cursor hoặc liên kết điều hướng trong body.
- Client phải xử lý một nhánh riêng **không có JSON body** thay vì giải mã cùng schema.
- Dễ khiến SDK cố parse body trống thành array hoặc object, rồi phát sinh lỗi.
- Một trang rỗng do bộ lọc hoặc do dữ liệu thay đổi có thể cần metadata để hiển thị UI.

**204 không phải mã mặc định cho “danh sách có 0 phần tử”.** Nếu API cố ý quy định GET không trả representation trong một tình huống nhất định, nó có thể dùng 204, nhưng phải tài liệu hóa rõ và kiểm thử client. Trong thực hành thiết kế collection API, **200 với dạng tập hợp rỗng thống nhất** thường là lựa chọn mặc định tốt hơn.

### 3.3. 404 Not Found

**404 Not Found** cho biết server **không tìm thấy representation hiện tại của tài nguyên đích hoặc không muốn tiết lộ rằng representation đó tồn tại**. 404 **không có nghĩa** “một câu truy vấn tìm thấy 0 hàng”.

Ví dụ tìm phần tử không tồn tại:

~~~http
GET /orders/o-999 HTTP/1.1

HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/resource-not-found",
  "title": "Resource not found",
  "status": 404,
  "detail": "Không tìm thấy tài nguyên được yêu cầu.",
  "code": "RESOURCE_NOT_FOUND"
}
~~~

Một **collection** có thể không tồn tại theo mô hình API, chẳng hạn:

- **/teams/t-999/members** khi team **t-999** không tồn tại và URI tập hợp con không hợp lệ nếu không có team.
- **/saved-lists/l-999/items** khi saved list đã bị xóa.
- URI không được ứng dụng cung cấp như **/archived-unknown-collections**.

Với những trường hợp này, trả 404 là phù hợp nếu API không thể cung cấp representation của **target resource**. Ngược lại, khi team tồn tại nhưng **members = []**, 404 sẽ diễn đạt sai trạng thái tài nguyên.

### 3.4. So sánh ngắn gọn

| Câu hỏi | 200 với []/envelope rỗng | 204 | 404 |
|---|---|---|---|
| Request thành công? | Có | Có | Không tìm thấy/không công bố tài nguyên đích |
| Có representation collection trong body? | **Có** | **Không** | Có thể có body lỗi, không phải collection representation |
| Có thể gửi metadata phân trang dạng JSON? | Có | Không | Không có kết quả phân trang thành công |
| Dùng khi filter hợp lệ không khớp hàng nào? | **Nên dùng** | Có thể nếu hợp đồng cố ý | **Không nên dùng** |
| Dùng khi parent theo hợp đồng không tồn tại? | Thường không | Thường không | **Thường phù hợp** |
| SDK có thể luôn giải mã cùng schema collection? | Có | Không | Xử lý nhánh lỗi |

## 4. Cây quyết định khi xử lý GET collection

~~~mermaid
flowchart TD
    R[GET collection URI] --> V{Request có cú pháp và tham số hợp lệ?}
    V -->|Không| E400[400 hoặc mã lỗi client phù hợp]
    V -->|Có| A{Caller được xác thực / có quyền?}
    A -->|Không| EAUTH[401 / 403 / 404 che giấu tồn tại]
    A -->|Có| T{Tài nguyên đích tồn tại theo hợp đồng?}
    T -->|Không| E404[404 Not Found]
    T -->|Có| Q[Thực hiện truy vấn trong phạm vi quyền]
    Q --> C{Số phần tử được trả?}
    C -->|0| EMPTY[200 OK + [] hoặc envelope items: []]
    C -->|Lớn hơn 0| DATA[200 OK + collection representation]
~~~

Sơ đồ nêu **điều kiện logic**, không quy định thứ tự kiểm tra bảo mật của mọi API. Để tránh rò thông tin, hệ thống có thể áp dụng chính sách 404 thay cho 403 khi tài nguyên không thuộc quyền truy cập của người gọi, và không tiết lộ sự tồn tại của tài nguyên trong bước xác thực.

Các trường hợp có **If-None-Match/If-Modified-Since** hoặc phương thức **HEAD** cần xét cơ chế HTTP riêng; không thể đưa trực tiếp vào nhánh “số phần tử” của sơ đồ trên.

## 5. Tập hợp rỗng sau khi lọc và sắp xếp

### 5.1. Một bộ lọc hợp lệ có thể không khớp gì

Ví dụ:

~~~http
GET /products?category=stationery&minPrice=100000000 HTTP/1.1
Accept: application/json
~~~

Giả sử **category** và **minPrice** đều đúng hợp đồng, người dùng được phép truy vấn, collection **/products** tồn tại, nhưng không sản phẩm nào đạt mức giá. Phản hồi hợp lý:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "items": [],
  "totalItems": 0
}
~~~

**“Bộ lọc không khớp dữ liệu” khác với “bộ lọc không hợp lệ”.**

| Request | Ý nghĩa | Hướng xử lý |
|---|---|---|
| GET /products?category=stationery | Bộ lọc hợp lệ, 0 hàng | **200** với collection rỗng |
| GET /products?minPrice=-100 | Nếu API cấm giá âm | **400** hoặc mã lỗi validation theo hợp đồng |
| GET /products?sort=unknownField | Trường sắp xếp không nằm trong allowlist | **400** hoặc mã lỗi client tương ứng |
| GET /products?status=SHIPPED | Nếu status có giá trị hợp lệ nhưng không khớp dữ liệu | **200** với collection rỗng |
| GET /products?status=NOT_AN_ENUM | Nếu status bắt buộc thuộc enum mà giá trị không được định nghĩa | **400** |
| GET /products?cursor=broken | Cursor sai định dạng hoặc không được công nhận | Mã lỗi theo contract cursor; **không tự gán 404** |

Mã **422 Unprocessable Content** có thể phù hợp cho một số lỗi ngữ nghĩa trong request content theo hợp đồng, nhưng với **query parameter sai kiểu/giá trị**, **400 Bad Request** là lựa chọn đơn giản và dễ hiểu. Đừng dùng 422 hoặc 404 một cách tùy tiện chỉ vì DB trả 0 hàng.

### 5.2. Các query parameter tùy chọn cần được định nghĩa rõ

Phân biệt những trường hợp sau:

- **Không có filter**: lấy danh sách trong phạm vi quyền, có phân trang.
- **Có filter hợp lệ nhưng không có kết quả**: tập hợp rỗng.
- **Có filter giá trị rỗng**: API có thể quy định coi như không filter, tìm chuỗi rỗng, hoặc từ chối; phải chọn rõ.
- **Có filter null/không hỗ trợ**: không suy luận tự động; tài liệu hóa semantics.
- **Nhiều filter kết hợp**: phép **AND/OR** và cách encode danh sách phải nhất quán.

Ví dụ **GET /orders?customerId=** không nên có ngữ nghĩa thay đổi âm thầm giữa các phiên bản. Nếu request muốn tra cứu đơn hàng của khách hàng có ID rỗng nhưng ID đó không hợp lệ, server cần trả lỗi hợp đồng thay vì vô tình trả tất cả đơn hàng.

## 6. Tập hợp con và tài nguyên cha không tồn tại

### 6.1. Khác biệt giữa workspace chưa có task và workspace không tồn tại

API minh họa:

~~~text
GET /workspaces/{workspaceId}/tasks
~~~

Quy ước nghiệp vụ: một workspace có thể có **0 hoặc nhiều task**. Phải truy vấn/kiểm tra quyền workspace trước khi lấy task trong phạm vi đó.

**Tình huống A: workspace có thật, 0 task**

~~~http
GET /workspaces/w-123/tasks HTTP/1.1
Authorization: Bearer <token>

HTTP/1.1 200 OK
Content-Type: application/json

{
  "items": [],
  "page": {"number": 0, "size": 20, "totalItems": 0, "hasNext": false}
}
~~~

**Tình huống B: workspace w-999 không tồn tại**

~~~http
GET /workspaces/w-999/tasks HTTP/1.1
Authorization: Bearer <token>

HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/workspace-not-found",
  "title": "Workspace not found",
  "status": 404,
  "code": "WORKSPACE_NOT_FOUND"
}
~~~

Không thể chỉ chạy **SELECT * FROM tasks WHERE workspace_id = ?** rồi suy ra tất cả kết quả rỗng đều 200. Query trả 0 hàng cho **cả workspace trống và workspace chưa tồn tại**; cần có bước xác định resource và quyền đúng đắn.

### 6.2. Khi collection có định danh riêng

Một sản phẩm có thể cho phép **tạo và xóa bộ sưu tập của người dùng**:

| URI | Tình trạng | Phản hồi |
|---|---|---|
| GET /collections/c-1 | c-1 tồn tại, metadata hợp lệ | **200** với representation của collection |
| GET /collections/c-1/items | c-1 tồn tại, 0 phần tử | **200** với items: [] |
| GET /collections/c-2/items | c-2 chưa từng được tạo | **404** theo contract |
| GET /collections/c-3/items | c-3 đã xóa và server biết trạng thái permanent | **404**, hoặc **410** khi muốn thông báo rõ đã biến mất |

**410 Gone** diễn tả tình huống server biết tài nguyên không còn tồn tại và tình trạng này có khả năng thường trực. Không bắt buộc mọi tài nguyên đã xóa phải trả 410; **404** vẫn phổ biến và có thể phù hợp. Bảo mật cũng có thể đòi hỏi không công khai việc tài nguyên từng tồn tại.

### 6.3. Khi đường dẫn con là một tập hợp “ảo”

Đôi khi API thiết kế **/users/{userId}/orders** như một **search view** thay vì tài nguyên tồn tại độc lập. Vẫn phải nêu rõ **userId có phải parent entity bắt buộc tồn tại không** và ai được truy vấn. Không thể suy quy tắc chỉ dựa trên hình dạng URL.

Ví dụ một API có thể định nghĩa **/orders?customerId=c-999** là tìm mọi order tham chiếu ID đó. Nếu ID không tồn tại nhưng filter hợp lệ, nó **có thể** trả 200 với 0 kết quả. API khác có thể yêu cầu customer phải tồn tại khi dùng **/customers/c-999/orders** và trả 404. Sự khác nhau nằm ở **hợp đồng và đối tượng đích**; cần tránh tình trạng cùng một API trả 404 hay 200 ngẫu nhiên giữa các endpoint mà không giải thích.

## 7. Quyền truy cập và nguy cơ tiết lộ sự tồn tại

Một collection truy vấn trong phạm vi user/tenant không được lộ dữ liệu của người khác. Giả sử:

~~~text
GET /tenants/t-1/invoices
GET /tenants/t-2/invoices
~~~

Caller thuộc **t-1** nhưng không có quyền trên **t-2**. Đừng chỉ trả một **200 với []** cho t-2 để che lỗi quyền trong mọi trường hợp. Cách làm này có thể khiến client hiểu rằng “tenant tồn tại và không có hóa đơn”, gây khó chẩn đoán hoặc che giấu truy cập trái phép.

Hành vi có thể được thiết kế:

- **401 Unauthorized** nếu request không có thông tin xác thực hợp lệ (tên theo chuẩn HTTP; về ý nghĩa là cần xác thực).
- **403 Forbidden** nếu caller đã được xác thực nhưng không có quyền, và API cho phép công bố điều này.
- **404 Not Found** nếu chính sách không muốn tiết lộ tài nguyên đích có tồn tại hay không.

Phải nhất quán chính sách che giấu tồn tại. **Không dùng số lượng hàng trả về** để quyết định quyền: một truy vấn SQL có điều kiện tenant cho 0 hàng chưa đủ chứng minh caller được truy cập tenant đó.

### 7.1. Bộ lọc bảo mật và bộ lọc nghiệp vụ là hai lớp khác nhau

Trong repository, có thể áp dụng:

~~~sql
SELECT o.id, o.status, o.created_at
FROM orders o
WHERE o.tenant_id = :authorized_tenant_id
  AND (:status_filter IS NULL OR o.status = :status_filter)
ORDER BY o.created_at DESC, o.id DESC
LIMIT :limit OFFSET :offset;
~~~

**authorized_tenant_id** phải đến từ principal đã xác thực và được cấp quyền, **không lấy nguyên từ query/header do client tự khai**. Khi không có order khớp filter, trả 200 với **items: []**. Khi không có quyền trên tenant, cần từ chối trước hoặc trong cơ chế kiểm soát truy cập; không được biến lỗi phân quyền thành kết quả rỗng một cách không kiểm soát.

Ngoài kiểm tra ở ứng dụng, có thể sử dụng **row-level security**, quyền database hoặc phân vùng lưu trữ để bảo vệ nhiều lớp. Những cơ chế đó không thay thế kiểm thử authorization ở API.

### 7.2. Tránh rò thông tin qua số lượng và metadata

Ngay cả khi trả **items: []**, những trường như **totalItems**, **nextCursor**, **facets**, **aggregation** hoặc thời gian phản hồi có thể để lộ sự tồn tại của dữ liệu thuộc tenant khác. Phải tính chúng **trong cùng phạm vi quyền** với các items trả ra.

Không tự đặt **totalItems = tổng số bản ghi toàn hệ thống** nếu collection được filter theo người dùng. Trường totalItems phải có định nghĩa rõ (tổng trong phạm vi filter và quyền, hoặc chỉ số khác được ghi chú).

## 8. Phân trang: trang rỗng vẫn có thể là một phản hồi thành công

### 8.1. Offset pagination

Giả sử API có 23 task, mỗi trang 10 phần tử, quy ước **page đánh số từ 0**:

| Request | Khoảng kết quả | Số items | Status đề xuất |
|---|---|---:|---|
| GET /tasks?page=0&size=10 | Phần tử 1–10 | 10 | **200** |
| GET /tasks?page=1&size=10 | Phần tử 11–20 | 10 | **200** |
| GET /tasks?page=2&size=10 | Phần tử 21–23 | 3 | **200** |
| GET /tasks?page=3&size=10 | Không còn phần tử | 0 | **200** với metadata không có trang sau |
| GET /tasks?page=-1&size=10 | page không hợp lệ | Không áp dụng | **400** theo hợp đồng |
| GET /tasks?page=0&size=0 | size không hợp lệ nếu size phải từ 1 | Không áp dụng | **400** theo hợp đồng |

Một lựa chọn hợp lý là **page vượt số trang hiện có nhưng cú pháp và giá trị vẫn hợp lệ** sẽ trả **200 với items: []**, thay vì 404. Vì **/tasks** vẫn là collection hợp lệ; chỉ có cửa sổ phân trang trống. API khác có thể **từ chối chỉ số trang vượt biên bằng lỗi client** nếu contract quy định rõ, nhưng không nên gọi đây là “resource collection không tồn tại” theo nghĩa HTTP một cách tùy tiện.

Ví dụ:

~~~http
GET /tasks?page=3&size=10 HTTP/1.1

HTTP/1.1 200 OK
Content-Type: application/json

{
  "items": [],
  "page": {
    "number": 3,
    "size": 10,
    "totalItems": 23,
    "totalPages": 3,
    "hasNext": false
  }
}
~~~

**Cẩn thận với totalPages:** trong ví dụ, các trang có dữ liệu là 0, 1 và 2; **totalPages = 3 là số trang**, không phải chỉ số trang cuối. Nếu **totalItems = 0**, nhiều API quy ước **totalPages = 0**. Contract cần nêu rõ cách tính để client không suy ra một trang ảo.

### 8.2. Cursor pagination

Với tập hợp biến động lớn, cursor pagination thường ổn định hơn offset trong nhiều bài toán:

~~~http
GET /tasks?limit=20&cursor=eyJrZXkiOi...
~~~

Khi cursor hợp lệ nhưng sau đó không còn phần tử, có thể trả:

~~~json
{
  "items": [],
  "nextCursor": null,
  "hasNext": false
}
~~~

Điều này khác với:

- **Cursor sai định dạng**: request không hợp lệ, thường **400**.
- **Cursor đã hết hạn hoặc không còn tương thích với truy vấn**: chọn mã lỗi có cấu trúc theo contract, có thể hướng dẫn bắt đầu lại.
- **Resource cha đã biến mất**: có thể **404/410** tùy ngữ nghĩa và chính sách.
- **Client không có quyền truy vấn**: **401/403/404 che giấu**.

Không dùng **416 Range Not Satisfiable** cho phân trang thông thường. 416 liên quan đến cơ chế **HTTP Range** đối với một representation, không phải một mã chung cho page/cursor vượt giới hạn. Tương tự, **206 Partial Content** dành cho nội dung được trả theo ngữ nghĩa range của HTTP; một trang JSON có 20 item trong tổng 1.000 item **không tự động phải dùng 206**.

### 8.3. Sắp xếp ổn định để tránh lặp hoặc bỏ sót

Nếu API dùng:

~~~text
ORDER BY created_at DESC
~~~

và có nhiều item cùng timestamp, thứ tự có thể không xác định. Nên có khóa phụ ổn định:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Với cursor, cần encode cả khóa sắp xếp cần thiết và bảo vệ cursor khỏi bị sửa sai theo chính sách. Với offset, dữ liệu bị thêm/xóa giữa các request có thể làm item xuất hiện hai lần hoặc bị bỏ qua: **một trang rỗng tại thời điểm này không chứng minh collection vĩnh viễn rỗng**. Nếu yêu cầu dữ liệu nhất quán giữa các trang, cần cân nhắc snapshot, version token hoặc mô hình xuất báo cáo riêng.

### 8.4. Total count có chi phí và thời điểm

Ở tập dữ liệu rất lớn, **COUNT(*)** có thể tốn kém. Một API có thể:

- Trả **totalItems chính xác** nếu đáp ứng SLO và chi phí.
- Trả **ước lượng** nhưng phải đặt tên/trường và semantics rõ ràng.
- Không trả total; dùng **hasNext/nextCursor** để điều hướng.

Không nên mặc định mọi phản hồi **items: []** có nghĩa toàn bộ collection có 0 bản ghi. **items: []** có thể chỉ là **một trang ở cuối**, hoặc kết quả của filter, hoặc tập dữ liệu mà caller được phép xem.

## 9. Cache: tập hợp rỗng vẫn là dữ liệu có thể thay đổi

### 9.1. Cache một kết quả truy vấn rỗng

Một phản hồi **200 với []** là representation hợp lệ có thể được cache theo chính sách HTTP phù hợp. Nhưng một kết quả rỗng có thể trở nên có dữ liệu ngay khi có item mới.

Ví dụ:

1. Lúc 10:00, **GET /orders?status=PAID** trả **items: []**.
2. Lúc 10:01, một đơn hàng được thanh toán và xuất hiện trong tập hợp này.
3. Nếu cache giữ response rỗng quá lâu mà không tái xác nhận, client có thể vẫn nhìn thấy **0 đơn hàng**.

Hãy xác định **Cache-Control**, TTL, cơ chế invalidation hoặc conditional request dựa trên yêu cầu về độ mới dữ liệu. Không tự xem “kết quả rỗng” là bất biến.

### 9.2. ETag và 304 Not Modified

Nếu server phát ETag cho representation collection đã chọn:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "orders-paid-v3"
Cache-Control: private, max-age=0, must-revalidate

{"items": [], "totalItems": 0}
~~~

Client gửi lần sau:

~~~http
GET /orders?status=PAID HTTP/1.1
If-None-Match: "orders-paid-v3"
~~~

Nếu representation tương ứng **chưa thay đổi** và điều kiện HTTP được đáp ứng, server có thể trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "orders-paid-v3"
Cache-Control: private, max-age=0, must-revalidate
~~~

**304 không có response body.** Nó không nói tập hợp rỗng; nó nói client có thể tái sử dụng representation đã lưu theo quy tắc cache. Nếu item mới xuất hiện làm representation thay đổi, server cần trả **200** với dữ liệu và validator mới (hoặc xử lý theo chính sách cache đã công bố).

ETag cho collection phải đại diện cho **đúng biểu diễn được chọn**, bao gồm những yếu tố ảnh hưởng tới kết quả như **filter, sort, page, tenant/quyền và thay đổi dữ liệu có liên quan**. Chỉ lấy version của một item ngẫu nhiên rồi gắn cho mọi query có thể làm validator sai.

### 9.3. Collection chứa dữ liệu riêng và bộ nhớ đệm dùng chung

Tập hợp đơn hàng, hóa đơn hoặc hồ sơ cá nhân thường phụ thuộc **danh tính và quyền**. Không để cache chia sẻ response của tenant A cho tenant B chỉ vì cùng URL:

- Dùng **Cache-Control: private** hoặc **no-store** theo chính sách bảo vệ dữ liệu.
- Nếu dùng cache có quyền ở gateway/CDN, khóa cache và phân vùng phải xét tenant/principal, quyền, các tham số query và cơ chế invalidation.
- Sử dụng **Vary** đúng với header thương lượng representation khi cần; **Vary một mình** không thể thay thế thiết kế quyền truy cập dữ liệu.
- Khi thay đổi membership/quyền, cần xử lý cache cũ để không trả dữ liệu trái phép.

Với API public, kết quả rỗng được cache có thể tiết kiệm tài nguyên; với dữ liệu nhạy cảm, ưu tiên đúng quyền và tính mới hơn tối ưu cache.

### 9.4. HEAD và trạng thái collection

**HEAD /orders** có ngữ nghĩa tương tự GET về thông tin phản hồi nhưng **không gửi body**. Không thể dùng việc HEAD không có body để kết luận collection rỗng hoặc phải trả 204. Một response HEAD 200 có thể có ETag, Content-Type hoặc các header liên quan; client cần GET để nhận collection representation.

## 10. Hợp đồng lỗi khi collection thực sự không tồn tại

Nếu resource đích không tồn tại, nên trả lỗi có cấu trúc rõ ràng, ví dụ **RFC 9457 Problem Details**:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
X-Correlation-ID: cf5e7602-3e6e-4735-ac9e-43ee1df5db1d
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/resource-not-found",
  "title": "Resource not found",
  "status": 404,
  "detail": "Không tìm thấy workspace hoặc danh sách công việc được yêu cầu.",
  "code": "WORKSPACE_NOT_FOUND",
  "correlationId": "cf5e7602-3e6e-4735-ac9e-43ee1df5db1d"
}
~~~

**code** và **correlationId** là thành viên mở rộng do API định nghĩa, không phải trường bắt buộc của RFC 9457. Không tiết lộ ID nhạy cảm, thông tin tenant khác, SQL query hoặc stack trace trong detail. Khi API cố ý dùng 404 để không công bố tài nguyên tồn tại, thông điệp nên mang tính chung, tránh vô tình xác nhận rằng user/tenant có thật.

### 10.1. Mã lỗi gần kề cần tách bạch

| Tình huống | Mã thường phù hợp | Ghi chú |
|---|---|---|
| Không có thông tin xác thực hợp lệ | **401 Unauthorized** | Có thách thức xác thực phù hợp nếu cần |
| Không có quyền trên tài nguyên | **403 Forbidden** hoặc **404** để che giấu | Quyết định theo chính sách bảo mật |
| Resource đích không tồn tại | **404 Not Found** | Khác với collection tồn tại nhưng 0 item |
| Resource đã bị xóa vĩnh viễn và API muốn thông báo | **410 Gone** | Không bắt buộc thay mọi 404 bằng 410 |
| Query parameter sai kiểu, page âm | **400 Bad Request** | Cung cấp mã validation có thể hành động |
| Có xung đột khi tạo/sửa collection | **409 Conflict** | Lỗi trạng thái, không phải đọc tập hợp rỗng |
| GET có validator khớp, điều kiện cache phù hợp | **304 Not Modified** | Không có body do tái xác nhận, không phải 0 item |
| Trả một byte range theo HTTP | **206 Partial Content** | Không là mã mặc định cho API pagination |
| Tạo một collection resource mới qua POST | **201 Created** khi tạo thành công | Không liên quan số member hiện có |
| Chấp nhận job tìm kiếm/export chạy nền | **202 Accepted** khi phù hợp | Kết quả truy vấn có thể xuất hiện sau đó |

### 10.2. Không tạo 404 chỉ từ repository trả Optional.empty cho danh sách

Trong Java, **Optional.empty()** của một truy vấn “tìm một đối tượng” có thể biểu thị tài nguyên không tồn tại. Còn **List.empty()** hoặc **Page.empty()** của truy vấn tập hợp thường là **kết quả thành công rỗng**. Đừng dùng chung một quy tắc “không tìm thấy dữ liệu thì ném NotFoundException” cho cả hai loại truy vấn.

Ngược lại, cũng không nên gọi **Collections.emptyList()** để xử lý mọi exception như lỗi database, lỗi timeout hoặc lỗi xác thực: đó là cách **che giấu sự cố thành kết quả rỗng**. Truy vấn không thực thi được là lỗi thật, cần mã 5xx hay status phù hợp khác, logging và monitoring tương ứng.

## 11. Triển khai Java/Spring: parent tồn tại, collection rỗng trả 200

### 11.1. Hợp đồng REST của ví dụ

Thiết kế:

~~~text
GET /workspaces/{workspaceId}/tasks?status=OPEN&page=0&size=20
~~~

Giả định:

- Workspace phải tồn tại và người dùng phải được phép xem.
- **status** là một trong các giá trị enum hợp lệ, không có nghĩa là task phải tồn tại.
- **page** bắt đầu từ 0; **size** nằm trong đoạn 1–100.
- Sort cố định theo **createdAt DESC, id DESC** để kết quả có thứ tự ổn định tương đối.
- Khi query hợp lệ trả 0 item, luôn **200** với schema **TaskCollectionResponse**.
- Nếu workspace không tồn tại, trả **404**; nếu caller thiếu quyền, trả **403 hoặc 404** theo chính sách đã lựa chọn.

### 11.2. Controller và DTO minh họa

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

record TaskView(UUID id, String title, String status) {}

record PageInfo(
    int number, int size, long totalItems, int totalPages,
    boolean hasNext
) {}

record TaskCollectionResponse(List<TaskView> items, PageInfo page) {}

enum TaskStatus { OPEN, IN_PROGRESS, DONE }

@RestController
@RequestMapping("/workspaces/{workspaceId}/tasks")
class TaskCollectionController {
    private final TaskService taskService;

    TaskCollectionController(TaskService taskService) {
        this.taskService = taskService;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<TaskCollectionResponse> list(
            @PathVariable UUID workspaceId,
            @RequestParam(required = false) TaskStatus status,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            Authentication principal) {

        if (page < 0 || size < 1 || size > 100) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid pagination parameters");
        }

        Pageable pageable = PageRequest.of(
            page,
            size,
            Sort.by(Sort.Order.desc("createdAt"),
                    Sort.Order.desc("id"))
        );

        // Service phải kiểm tra tồn tại + quyền workspace.
        // Nếu workspace hợp lệ và không có task, trả Page rỗng.
        Page<TaskView> result = taskService.findVisibleTasks(
            principal, workspaceId, status, pageable);

        return ResponseEntity.ok(new TaskCollectionResponse(
            result.getContent(),
            new PageInfo(
                result.getNumber(),
                result.getSize(),
                result.getTotalElements(),
                result.getTotalPages(),
                result.hasNext()
            )
        ));
    }
}
~~~

Ví dụ giả định có **TaskService** thực hiện xác thực, phân quyền và truy vấn repository; imports, cấu hình Spring Security, cơ chế exception mapping và entity/repository thực tế cần được tích hợp vào project. **TaskStatus** là enum và Spring MVC thường trả **400** khi không thể chuyển query parameter hợp lệ; cần kiểm thử error response theo cấu hình thực.

**Điểm quan trọng của code:** Controller **không kiểm tra result.isEmpty() để đổi thành 404 hoặc 204**. Nó luôn trả 200 với **items** và metadata khi service đã xác minh resource hợp lệ và truy vấn hoàn thành.

### 11.3. Service cần phân biệt tồn tại, quyền và kết quả tìm kiếm

Luồng logic:

~~~text
findVisibleTasks(principal, workspaceId, status, pageable):
    workspace = workspaceRepository.findById(workspaceId)
    if workspace does not exist:
        throw WorkspaceNotFoundException

    authorization.checkCanReadWorkspace(principal, workspace)
    // Hoặc trả 404 thay 403 nếu contract có chính sách che giấu tồn tại.

    page = taskRepository.findByWorkspaceAndStatusWithinAccessScope(
        workspace, status, pageable
    )

    return page.map(toTaskView)
~~~

Đây là giả mã. Trong production, thứ tự kiểm tra tồn tại và quyền cần phối hợp để **không làm rò tài nguyên giữa các tenant**. Có thể dùng truy vấn workspace trong phạm vi được phép và trả 404 chung khi không tìm thấy resource nhìn thấy được; điều quan trọng là không coi truy vấn task rỗng đã chứng minh workspace có quyền truy cập.

### 11.4. Xử lý resource không tồn tại bằng Problem Details

~~~java
import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class CollectionErrorHandler {

    @ExceptionHandler(WorkspaceNotFoundException.class)
    ResponseEntity<ProblemDetail> workspaceMissing(
            WorkspaceNotFoundException ignored) {

        ProblemDetail body =
            ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        body.setType(URI.create(
            "https://api.example.test/problems/resource-not-found"));
        body.setTitle("Resource not found");
        body.setDetail("Không tìm thấy tài nguyên được yêu cầu.");
        body.setProperty("code", "RESOURCE_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(body);
    }
}
~~~

Ví dụ dùng Spring Framework 6+ với **ProblemDetail**. Trong hệ thống thật, handler này có thể bổ sung correlation ID từ request context, nhưng không được trả chi tiết nội bộ không phù hợp với quyền của caller.

**Tránh bắt mọi Exception rồi trả 404 hoặc items: []**: lỗi DB, timeout downstream, lỗi truy vấn và exception lập trình không trở thành “collection rỗng” chỉ vì controller chưa thể lấy dữ liệu.

## 12. OpenAPI: mô tả kiểu dữ liệu nhất quán khi rỗng và có phần tử

Một API có thể đúng status nhưng gây lỗi SDK nếu schema trả về thay đổi tùy số phần tử. Vì vậy, tài liệu **OpenAPI** cần có một schema collection duy nhất cho response **200**, dùng cả khi **items.length = 0**.

Ví dụ OpenAPI 3.0.3 rút gọn:

~~~yaml
openapi: 3.0.3
info:
  title: Workspace Tasks API
  version: 1.0.0
paths:
  /workspaces/{workspaceId}/tasks:
    get:
      summary: Lấy danh sách task của một workspace
      description: >
        Nếu workspace tồn tại và người gọi có quyền,
        kết quả truy vấn không khớp task nào vẫn trả 200
        với items là mảng rỗng. Workspace không tồn tại
        hoặc không được phép công bố có thể trả 404.
      parameters:
        - in: path
          name: workspaceId
          required: true
          schema:
            type: string
            format: uuid
        - in: query
          name: status
          required: false
          schema:
            type: string
            enum: [OPEN, IN_PROGRESS, DONE]
        - in: query
          name: page
          required: false
          schema:
            type: integer
            minimum: 0
            default: 0
        - in: query
          name: size
          required: false
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
      responses:
        "200":
          description: >
            Truy vấn thành công; items có thể là [].
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/TaskCollection"
              examples:
                empty:
                  summary: Workspace có thật nhưng chưa có task
                  value:
                    items: []
                    page:
                      number: 0
                      size: 20
                      totalItems: 0
                      totalPages: 0
                      hasNext: false
        "400":
          description: Tham số query không hợp lệ
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/ApiProblem"
        "401":
          description: Chưa xác thực
        "403":
          description: Không có quyền truy cập
        "404":
          description: Workspace hoặc tài nguyên đích không tồn tại
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/ApiProblem"
components:
  schemas:
    Task:
      type: object
      properties:
        id:
          type: string
          format: uuid
        title:
          type: string
        status:
          type: string
          enum: [OPEN, IN_PROGRESS, DONE]
      required: [id, title, status]
    PageInfo:
      type: object
      properties:
        number:
          type: integer
          minimum: 0
        size:
          type: integer
          minimum: 1
        totalItems:
          type: integer
          format: int64
          minimum: 0
        totalPages:
          type: integer
          minimum: 0
        hasNext:
          type: boolean
      required: [number, size, totalItems, totalPages, hasNext]
    TaskCollection:
      type: object
      properties:
        items:
          type: array
          items:
            $ref: "#/components/schemas/Task"
        page:
          $ref: "#/components/schemas/PageInfo"
      required: [items, page]
    ApiProblem:
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
        code:
          type: string
      required: [type, title, status]
~~~

Mẫu trên tập trung vào ngữ nghĩa **200/400/404** và collection schema. Khi triển khai thực tế, cần bổ sung **security schemes**, chính sách 403 so với 404, ví dụ non-empty, response headers, cache controls, correlation ID và các lỗi 5xx/429 nếu contract quy định.

### 12.1. Có nên khai báo response 204 cho GET collection?

Nếu API **luôn** trả 200 với collection representation khi GET thành công, không cần thêm 204 chỉ vì “sau này có thể rỗng”. Việc liệt kê 204 có thể khiến SDK sinh kiểu dữ liệu tùy chọn hoặc nhánh null không cần thiết.

Nếu API quyết định có cả **200 và 204**, phải mô tả rõ:

- **Điều kiện** nào trả 204 và vì sao **không có representation**.
- Client **không được parse JSON body** của 204.
- Cách client nhận metadata, thông tin phân trang và trạng thái empty khi body không có.
- Các test bảo đảm không trả nhầm **Content-Length** cho một body không tồn tại.

Trong một API mới, ưu tiên hợp đồng đơn giản, nhất quán và dễ sinh client SDK; phần lớn các collection query được hưởng lợi từ **200 với []**.

## 13. Kiểm thử: xác minh resource tồn tại trước khi đếm kết quả

### 13.1. Ma trận test cho collection API

| Trường hợp | Tiền điều kiện | Kết quả cần xác minh |
|---|---|---|
| Collection cơ bản rỗng | /orders hợp lệ; không có đơn | **200**, items: [], metadata thống nhất |
| Collection có phần tử | Có 3 đơn người dùng được phép xem | **200**, đúng 3 items và schema giống trường hợp rỗng |
| Filter hợp lệ không khớp | Có đơn nhưng không đơn nào status=SHIPPED | **200**, items: [], totalItems trong phạm vi filter bằng 0 |
| Filter sai enum | status=INVALID | **400**, body lỗi có code; không biến thành 404 |
| Page vượt cuối | Truy vấn hợp lệ; page lớn hơn cuối theo contract | **200**, items: [], hasNext=false, không tự dùng 416 |
| Page âm | page=-1 | **400** và không thực hiện truy vấn không hợp lệ |
| Size quá lớn | size=9999 khi max=100 | **400** hoặc chính sách giới hạn rõ, không gây quá tải |
| Workspace có thật, task rỗng | Workspace w-1 tồn tại và caller có quyền | **200**, items: [] |
| Workspace không tồn tại | w-999 không có resource | **404** nếu contract yêu cầu parent |
| Caller không được phép | Caller không có quyền trên w-2 | **403** hoặc **404** che giấu theo policy |
| Không xác thực | Không có token/credential hợp lệ | **401** theo cấu hình auth |
| DB hoặc search timeout | Dependency bị lỗi | **5xx phù hợp**, không trả items: [] |
| Xóa item cuối cùng | Collection vẫn còn, số task về 0 | **200**, items: [] khi GET lại |
| Cập nhật dữ liệu sau cache | Trước đó GET rỗng, sau đó tạo item | Cache/revalidation không trả dữ liệu cũ ngoài chính sách |
| Dữ liệu của tenant khác | DB có record tenant B, caller tenant A | Không lộ item, totalCount/facets/cursor của B |
| GET với If-None-Match | Representation không đổi | **304** khi điều kiện phù hợp, không body |
| HEAD collection | URI hợp lệ, có/không có phần tử | HEAD đúng metadata/status, không response body |

### 13.2. MockMvc: workspace rỗng nhưng hợp lệ

Ví dụ dưới đây giả định có **TaskCollectionController** và fixture **w-1** tồn tại, caller được xác thực:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.hamcrest.Matchers.hasSize;

// Workspace hợp lệ, không có task:
mockMvc.perform(get("/workspaces/{id}/tasks", workspaceId)
        .param("status", "OPEN")
        .param("page", "0")
        .param("size", "20"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.items", hasSize(0)))
    .andExpect(jsonPath("$.page.totalItems").value(0))
    .andExpect(jsonPath("$.page.hasNext").value(false));
~~~

Ví dụ không tạo workspace hay cấu hình security; đó là trách nhiệm của test fixture. Phép kiểm tra này chứng minh **không dùng 404/204 cho danh sách rỗng**. Cần thêm kiểm thử trên response khi có dữ liệu để đảm bảo cùng schema, không thay trường **items** thành **null**.

### 13.3. MockMvc: parent không tồn tại

~~~java
// Workspace không có trong kho dữ liệu hoặc bị ẩn theo policy:
mockMvc.perform(get("/workspaces/{id}/tasks", missingWorkspaceId))
    .andExpect(status().isNotFound())
    .andExpect(jsonPath("$.status").value(404))
    .andExpect(jsonPath("$.code").value("RESOURCE_NOT_FOUND"));
~~~

Với endpoint có bảo mật, các request test phải có principal/roles đúng; nếu chưa xác thực thì **401** có thể xảy ra trước 404. Trong production, nên có kiểm thử **không rò tồn tại của workspace giữa các tenant** khi API chọn chính sách 404 che giấu.

### 13.4. Kiểm thử repository riêng với kiểm thử API

Ở tầng repository, xác minh:

1. Query có filter đúng và chỉ lấy record trong phạm vi quyền.
2. Count cho metadata được tính trên **cùng filter và authorization**.
3. Sort có tie-breaker rõ ràng.
4. Khi một query trả 0 hàng, repository trả Page/List rỗng hợp lệ, không phát sinh exception.

Ở tầng service/API, xác minh **quyền và tồn tại của parent** trước/đúng ngữ cảnh truy vấn, status HTTP, JSON schema và mapping lỗi. Nếu chỉ kiểm thử repository trả empty, chưa chứng minh endpoint phân biệt được **workspace không tồn tại** với **workspace có thật nhưng chưa có task**.

## 14. Case study: REST API quản lý công việc theo tenant

### 14.1. Bối cảnh

Giả sử nền tảng **TaskHub** phục vụ hai doanh nghiệp **North** và **South**. Mỗi tenant có workspace, mỗi workspace có nhiều task. Nền tảng hỗ trợ:

~~~text
GET /workspaces/{workspaceId}
GET /workspaces/{workspaceId}/tasks?status=OPEN&page=0&size=20
GET /tasks/{taskId}
~~~

Quy ước API:

- Workspace ID là UUID do server phát hành.
- Caller phải được xác thực và có quyền trên workspace.
- Task có thể có trạng thái **OPEN, IN_PROGRESS, DONE**.
- Collection endpoint luôn trả object với **items và page** khi thành công.
- Workspace không tồn tại hoặc bị che giấu theo tenant policy trả 404.
- Page vượt cuối nhưng vẫn hợp lệ trả 200 với mảng rỗng.

### 14.2. Bốn truy vấn, bốn ý nghĩa

| Truy vấn | Dữ liệu thực | Phản hồi theo contract |
|---|---|---|
| North GET tasks của w-N-1 | Workspace North tồn tại nhưng chưa có task | **200**, items: [], totalItems: 0 |
| North GET tasks của w-N-2?status=DONE | Workspace có task nhưng không task nào DONE | **200**, items: [], totalItems: 0 |
| North GET tasks của w-unknown | Workspace không tồn tại | **404** với Problem Details |
| North GET tasks của w-S-1 | Workspace thuộc South, North không có quyền | **404** che giấu hoặc **403**, theo policy |

Nếu cả bốn trường hợp được ánh xạ thành **404**, dashboard theo dõi 404 sẽ bị tràn bởi thao tác lọc bình thường. Nếu cả bốn đều trả **200 với []**, hệ thống sẽ che giấu đường dẫn sai và lỗi phân quyền.

### 14.3. Lỗi phát sinh từ thiết kế ban đầu

Đội phát triển triển khai:

~~~java
List<Task> tasks = taskRepository.findAllByWorkspaceId(workspaceId);
if (tasks.isEmpty()) {
    throw new ResourceNotFoundException();
}
~~~

Đoạn code này **không phân biệt**:

- Workspace chưa có task.
- Workspace không tồn tại.
- Workspace có task nhưng caller không có quyền xem item nào.
- Filter có giá trị hợp lệ nhưng không khớp.

Hệ quả là frontend hiện thông báo “Workspace không tồn tại” cho người vừa tạo workspace mới, các bài test không ổn định và thống kê 404 sai lệch.

### 14.4. Điều chỉnh thiết kế

Đội TaskHub sửa theo ba trách nhiệm:

1. **Workspace lookup/authorization:** xác định workspace được phép truy cập theo tenant, trả lỗi đúng hợp đồng nếu không có.
2. **Collection query:** áp filter, sort, pagination trong phạm vi quyền, trả Page/List có thể rỗng.
3. **HTTP response mapping:** khi bước 1 thành công và bước 2 hoàn thành, trả **200** với cùng schema. Chỉ ánh xạ exception có ý nghĩa tài nguyên/điều kiện/bảo mật sang 4xx; lỗi dependency không bị biến thành kết quả rỗng.

Đội còn bổ sung test **workspace tồn tại nhưng task rỗng** và **workspace không tồn tại** để ngăn lỗi tái xuất hiện. Sau khi triển khai, nhóm kiểm tra tỷ lệ 200 rỗng, 404 thật, các trường hợp không đủ quyền và độ trễ/count query để xác nhận hành vi hợp đồng.

## 15. Bài thực hành: thiết kế API collection đúng ngữ nghĩa

### 15.1. Đề bài

Một nền tảng học tập cung cấp:

~~~text
GET /courses
GET /courses/{courseId}
GET /courses/{courseId}/lessons?published=true&page=0&size=10
GET /users/{userId}/enrollments
~~~

Yêu cầu giả định:

- **/courses** là resource collection luôn truy vấn được bởi người dùng công khai.
- Một khóa học mới được tạo có thể **chưa có lesson nào**.
- Lesson nháp không hiển thị với người dùng bình thường.
- **/courses/{courseId}/lessons** yêu cầu course tồn tại.
- Enrollment chỉ được xem bởi chính user đó hoặc admin; chính sách có thể che giấu sự tồn tại của user.
- Page và size có giới hạn công bố; page hợp lệ vượt cuối trả mảng rỗng.

Hãy trả lời:

1. GET /courses khi chưa có course nên trả mã và body gì?
2. GET /courses/c-1/lessons khi c-1 tồn tại nhưng chưa có lesson thì sao?
3. GET /courses/c-1/lessons?published=true khi tất cả lesson đều ở trạng thái nháp thì sao?
4. GET /courses/c-999/lessons khi course c-999 không tồn tại thì sao?
5. GET /users/u-2/enrollments khi caller là u-1 không có quyền thì sao?
6. GET /courses/c-1/lessons?page=1000 khi course c-1 có hai trang thì sao?
7. GET /courses/c-1/lessons?page=-1 thì sao?
8. Hãy viết schema JSON thống nhất cho collection có 0 và 2 phần tử.
9. Nếu collection rỗng được cache, cần chú ý gì khi lesson đầu tiên được xuất bản?
10. Viết hai test phân biệt **resource cha không tồn tại** với **resource cha tồn tại nhưng collection rỗng**.

### 15.2. Gợi ý đáp án

| Câu | Lời giải hợp lý |
|---|---|
| 1 | **200** với **[]** hoặc envelope **items: []** theo contract |
| 2 | **200** với collection rỗng vì course hợp lệ |
| 3 | **200** với collection rỗng vì filter hợp lệ nhưng không khớp lesson hiển thị |
| 4 | **404** vì parent course không tồn tại theo contract |
| 5 | **403** hoặc **404** che giấu theo policy; không dùng 200 rỗng chỉ để bỏ qua authorization |
| 6 | **200** với items: [] và hasNext=false theo quy ước đã đưa |
| 7 | **400** do page âm không hợp lệ |
| 8 | Cùng kiểu items array và metadata trong cả hai trường hợp; không dùng null hay thay schema |
| 9 | Cache cần hết hạn/tái xác nhận/invalidation; ETag cho đúng biểu diễn khi dữ liệu thay đổi |
| 10 | Test một course hợp lệ chưa có lesson trả 200 [], một course không tồn tại trả 404 Problem Details |

### 15.3. Thử thách nâng cao

Giả sử lesson được thêm đồng thời trong lúc client phân trang. Hãy đề xuất một chiến lược **sort ổn định và cursor pagination** để giảm lặp/bỏ sót, và giải thích tại sao **items: [] ở một trang cuối** không chứng minh dữ liệu toàn collection bằng 0. Nếu API phải cho phép tải ra toàn bộ lesson theo một snapshot nhất quán, đề xuất một quy trình **export job** tách khỏi GET phân trang thông thường.

## 16. Góc nhìn client: “rỗng”, “lỗi” và “đang tải” là ba trạng thái khác nhau

Một UI danh sách thường cần tối thiểu những trạng thái:

- **Loading:** request chưa hoàn tất.
- **Success với dữ liệu:** response thành công và có items.
- **Success rỗng:** response thành công, items.length = 0; có thể hiển thị “Chưa có dữ liệu” hoặc “Không tìm thấy kết quả với bộ lọc hiện tại”.
- **Error:** response 4xx/5xx, network timeout hoặc không thể giải mã response theo hợp đồng.

Ví dụ client TypeScript với response envelope:

~~~typescript
type Task = {
  id: string;
  title: string;
  status: "OPEN" | "IN_PROGRESS" | "DONE";
};

type TaskCollection = {
  items: Task[];
  page: {
    number: number;
    size: number;
    totalItems: number;
    totalPages: number;
    hasNext: boolean;
  };
};

async function loadTasks(
  workspaceId: string,
  page = 0,
): Promise<TaskCollection> {
  const response = await fetch(
    "/workspaces/" + encodeURIComponent(workspaceId) +
    "/tasks?page=" + page + "&size=20",
    { headers: { Accept: "application/json" } }
  );

  if (!response.ok) {
    // Đọc Problem Details theo Content-Type nếu có;
    // phân biệt 404, 403, 400 và lỗi server/network.
    throw new Error("Không tải được danh sách task");
  }

  // Hợp đồng quy định mọi GET thành công đều trả 200 + JSON.
  return (await response.json()) as TaskCollection;
}

const result = await loadTasks("w-123");
if (result.items.length === 0) {
  // Trạng thái rỗng hợp lệ, không phải exception.
}
~~~

Đoạn code là minh họa, chưa có xác thực, timeout, xử lý Problem Details chi tiết và kiểm tra schema ở runtime. Với API chọn trả **204**, client phải có nhánh xử lý body trống trước khi gọi **response.json()**; điều này cho thấy tại sao 200 với schema nhất quán có lợi cho SDK.

### 16.1. Thông điệp giao diện cần phân biệt bối cảnh

- **Không có item nào:** “Workspace này chưa có công việc. Hãy tạo công việc đầu tiên.”
- **Có filter nhưng không khớp:** “Không tìm thấy công việc phù hợp. Thử thay đổi bộ lọc.”
- **Trang vượt cuối:** “Không còn kết quả ở trang này.” Có thể quay về trang trước hoặc điều chỉnh cursor.
- **404 workspace:** “Workspace không còn khả dụng hoặc không tồn tại.”
- **403 hoặc 404 che giấu:** dùng thông điệp không làm lộ thông tin bị hạn chế theo chính sách.
- **Lỗi hệ thống:** “Không tải được dữ liệu. Thử lại theo hướng dẫn.” Không hiển thị như collection rỗng.

**Không dùng mảng rỗng làm trạng thái chung cho mọi lỗi tải dữ liệu.** Nếu client bắt lỗi mạng rồi trả **[]** như thể request thành công, người dùng có thể tưởng dữ liệu đã bị xóa, còn đội kỹ thuật mất tín hiệu về lỗi thật.

## 17. Các phản mẫu và cách sửa

| Phản mẫu | Hệ quả | Cách sửa |
|---|---|---|
| Không tìm được hàng nào thì luôn ném NotFoundException | Bộ lọc bình thường thành 404 | Phân biệt lookup tài nguyên với query tập hợp |
| Dùng 204 mặc định cho GET danh sách rỗng | Client không nhận được [] và metadata | Ưu tiên 200 với representation nhất quán |
| Trả 200 với [] cho workspace không tồn tại | Che giấu lỗi URI và ngữ nghĩa parent | Kiểm tra tài nguyên cha theo contract |
| Trả 200 với [] khi không có quyền | Nhầm quyền với không có dữ liệu, khó audit | Trả 403/404 che giấu theo security policy |
| Không kiểm tra query parameter | Filter sai âm thầm thành kết quả rỗng | Validation và thông báo lỗi có cấu trúc |
| Trả 404 khi page vượt cuối | Xem page như resource riêng dù contract không quy định | Thống nhất quy tắc pagination và dùng 200 [] khi phù hợp |
| Dùng 206 cho mọi trang JSON | Nhầm HTTP Range với pagination | Dùng 200 cho trang bình thường |
| Trả **null** cho items khi không có phần tử | Client phải xử lý nhiều kiểu | Luôn trả array, có thể là [] |
| Trả items [] nhưng totalItems lấy từ dữ liệu toàn tenant | Rò dữ liệu và metadata không nhất quán | Tính metadata trong cùng filter và phạm vi quyền |
| Cache mãi phản hồi rỗng | Item mới không xuất hiện | TTL/revalidation/ETag hoặc invalidation phù hợp |
| Nuốt exception database và trả [] | Sự cố 5xx biến thành “không có dữ liệu” | Giữ phân loại lỗi, observability và retry phù hợp |
| Không có sort ổn định giữa các trang | Item trùng hoặc bị bỏ sót | Thêm tie-breaker và cân nhắc cursor/snapshot |

### 17.1. Một quy tắc đơn giản nhưng không được áp dụng máy móc

“**GET collection rỗng → 200 []**” là quy tắc thực hành tốt **sau khi đã xác minh collection target tồn tại và request hợp lệ**. Nó không bỏ qua xác thực, phân quyền, vòng đời parent resource, điều kiện HTTP hay lỗi hệ thống.

## 18. Checklist thiết kế và kiểm thử

- [ ] Collection URI và member URI được phân biệt rõ trong tài liệu.
- [ ] Biết collection có thể rỗng mà vẫn tồn tại; không suy từ số hàng DB rằng URI không tồn tại.
- [ ] Xác định rõ ngữ nghĩa parent và named collection; trường hợp parent vắng mặt có status theo hợp đồng.
- [ ] GET collection hợp lệ không có kết quả trả **200 với []/items: []** và metadata thống nhất.
- [ ] Nếu hỗ trợ 204 cho GET, có lý do và hợp đồng riêng; không đưa JSON body vào 204.
- [ ] 404 chỉ dùng khi target resource không tồn tại hoặc API không công bố sự tồn tại.
- [ ] 401, 403 và 404 che giấu được quyết định theo chính sách bảo mật; không rò dữ liệu tenant.
- [ ] Filter, sort, page, size, cursor được validate; filter hợp lệ không khớp không trở thành 404.
- [ ] Trang rỗng và toàn bộ collection rỗng được phân biệt bằng metadata/cursor khi cần.
- [ ] Pagination có sort ổn định, định nghĩa số trang và giới hạn kích thước rõ ràng.
- [ ] totalItems, facets và nextCursor chỉ phản ánh dữ liệu trong phạm vi quyền.
- [ ] Cache/ETag/304 được áp dụng theo URI, filter, page, quyền và chính sách độ mới.
- [ ] OpenAPI khai báo một schema collection 200 nhất quán cho dữ liệu rỗng/có phần tử.
- [ ] 404/400 trả Problem Details an toàn, mã lỗi rõ và có correlation ID nếu contract hỗ trợ.
- [ ] Client hiển thị riêng trạng thái empty, error và loading; không nuốt lỗi network thành [].
- [ ] Test parent tồn tại/không tồn tại, filter rỗng, page vượt cuối, query invalid, authorization, cache và dependency failure.

## 19. Ghi nhớ và tài liệu tham khảo

**Tập hợp rỗng** nói về **nội dung của một kết quả truy vấn hợp lệ**; **tài nguyên tập hợp không tồn tại** nói về **URI đích và vòng đời của resource**. Với GET collection có thật, caller có quyền, filter/page hợp lệ và số phần tử bằng 0, **200 OK với [] hoặc envelope items: []** là phản hồi nhất quán, dễ sử dụng. **204 No Content** chỉ nói không có nội dung response và làm mất khả năng trả biểu diễn collection; **404 Not Found** dành cho tài nguyên đích không có representation hiện tại hoặc không được công bố. Phân biệt hai câu hỏi **“target resource có hợp lệ không?”** và **“result có bao nhiêu item?”** giúp API REST rõ hợp đồng, an toàn hơn và dễ kiểm thử.

Tài liệu tham khảo:

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ngữ nghĩa GET, HEAD và các mã **200, 204, 304, 403, 404, 410, 416**.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): lưu trữ, tái xác nhận và kiểm soát cache của HTTP representation.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): cấu trúc response lỗi **application/problem+json**.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): khai báo response, schema collection, tham số query và error response.
- [Spring Data — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): nguyên tắc truy vấn repository, phân trang và sắp xếp.
