# Link header theo chuẩn Web Linking

## 1. Tại sao REST API cần liên kết ngoài nội dung JSON?

Khi client gọi một REST API, phản hồi thường chứa biểu diễn của tài nguyên: ID đơn hàng, trạng thái, số tiền hoặc danh sách bản ghi. Tuy nhiên, client còn cần biết **nên điều hướng đến tài nguyên nào tiếp theo**, **đường dẫn của trang kế tiếp**, **địa chỉ tài liệu mô tả**, hoặc **biểu diễn khác của cùng một nội dung**.

Ví dụ, một ứng dụng quản trị tải các đơn hàng đã thanh toán:

~~~http
GET /orders?status=PAID&limit=2 HTTP/1.1
Host: api.example.com
Accept: application/json
Authorization: Bearer <access-token>
~~~

Server có thể trả dữ liệu và một liên kết đến trang tiếp theo:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Link: </orders?status=PAID&limit=2&cursor=c2>; rel="next"
Cache-Control: private, no-store

{
  "items": [
    {"id": "ord-105", "status": "PAID"},
    {"id": "ord-104", "status": "PAID"}
  ]
}
~~~

Trường **Link** cung cấp một chỉ dẫn có ngữ nghĩa: URL trong dấu ngoặc nhọn góc là **đích liên kết**; tham số **rel="next"** cho biết quan hệ *trang tiếp theo* đối với ngữ cảnh phản hồi. Client hiểu quan hệ có thể dùng URL đó thay vì tự tính toán offset hoặc tự dựng lại toàn bộ query string.

Trong module **INTEGRATION_API_REST**, việc thiết kế resource, URI, phương thức, mã trạng thái, hợp đồng dữ liệu, phân trang, cache, OpenAPI, xác thực, phân quyền và kiểm thử đều liên quan đến câu hỏi: *client biết phải làm gì sau phản hồi hiện tại bằng cách nào?* Bài **Link header theo chuẩn Web Linking**, thuộc chương **Hypermedia**, tập trung vào một cách chuyển thông tin liên kết theo ngữ nghĩa HTTP.

Sau bài học, bạn có thể:

- Giải thích **Web Linking** và cấu trúc của **Link** header theo **RFC 8288**.
- Phân biệt **link target**, **link context**, **relation type** và các **target attributes**.
- Dùng các quan hệ như **next**, **prev**, **first**, **last**, **self**, **canonical**, **alternate**, **describedby** đúng mục đích.
- Thiết kế phân trang cursor qua Link header mà không lộ thuật toán phân trang cho client.
- Xử lý nhiều Link, URI tương đối, caching, xác thực và nguy cơ link không đáng tin cậy.
- Triển khai/kiểm thử Link header trong Java/Spring và mô tả trong OpenAPI.

## 2. Web Linking theo RFC 8288

**RFC 8288 – Web Linking** là đặc tả định nghĩa mô hình liên kết giữa các tài nguyên trên Web và cách tuần tự hóa liên kết trong **HTTP Link header field**. RFC 8288 thay thế đặc tả Web Linking trước đó là **RFC 5988**.

Một liên kết không chỉ là một chuỗi URL. Nó mô tả một **mối quan hệ có kiểu** giữa:

1. **Link context:** tài nguyên đang được mô tả hoặc tài nguyên mà liên kết xuất phát.
2. **Link relation type:** ý nghĩa của quan hệ giữa context và target.
3. **Link target:** tài nguyên đích mà liên kết tham chiếu tới.
4. **Target attributes:** thông tin bổ sung về liên kết hoặc đích, chẳng hạn ngôn ngữ hay media type dự kiến.

~~~mermaid
flowchart LR
    A["Context: GET /orders?cursor=c1"] -->|"rel=next"| B["Target: /orders?cursor=c2"]
    A -->|"rel=describedby"| C["Target: tài liệu schema"]
    A -->|"rel=help"| D["Target: hướng dẫn sử dụng"]
~~~

**Link** header là một cách biểu diễn mô hình đó ở **metadata của HTTP response**, thay vì buộc tất cả liên kết phải nằm bên trong JSON. Cùng một nguyên tắc Web Linking còn có thể xuất hiện ở những định dạng hypermedia khác; không nên nhầm *mô hình Web Linking* với một schema JSON cụ thể.

### 2.1. Cú pháp tối thiểu

~~~http
Link: </orders?cursor=eyJpZCI6MTA0fQ>; rel="next"
~~~

Các thành phần:

| Thành phần | Giá trị minh họa | Ý nghĩa |
| --- | --- | --- |
| Tên header | **Link** | HTTP header field chứa một hoặc nhiều liên kết. |
| Đích trong dấu **< >** | **/orders?cursor=...** | URI reference của tài nguyên đích. |
| Dấu chấm phẩy **;** | Phân tách đích và tham số | Bắt đầu phần mô tả thuộc tính của liên kết. |
| **rel** | **"next"** | Loại quan hệ: tài nguyên đích biểu diễn phần tiếp theo. |
| Dấu ngoặc kép | **"next"** | Cách biểu diễn relation value; các giá trị có khoảng trắng cần được quote đúng. |

Ví dụ trên chỉ hợp lệ để client hiểu là **trang kế** khi server đã gắn nó với đúng context và hợp đồng tập hợp. Bản thân một chuỗi **cursor** không mang nghĩa “trang kế” nếu không có relation.

### 2.2. URI tương đối được giải quyết thế nào?

Trong phản hồi của:

~~~http
GET https://api.example.com/orders?status=PAID&limit=20
~~~

header:

~~~http
Link: </orders?status=PAID&limit=20&cursor=c2>; rel="next"
~~~

chứa một **URI reference tương đối**. Client phân giải đích theo URI thích hợp của link context, với quy tắc giải quyết URI reference; trong trường hợp thông thường context là URI của tài nguyên được yêu cầu. Kết quả ở ví dụ là:

~~~text
https://api.example.com/orders?status=PAID&limit=20&cursor=c2
~~~

URI không có dấu gạch chéo đầu cũng có thể tương đối với đường dẫn hiện hành; điều này dễ gây sai khi chuyển endpoint từ **/orders** sang **/v2/orders**. Dùng đường dẫn tương đối một cách có chủ đích và luôn kiểm thử việc phân giải đích. Đừng ghép URL bằng thao tác nối chuỗi không hiểu quy tắc URI.

### 2.3. Context là gì khi response chứa Link?

Trong trường hợp phổ biến, context là tài nguyên mà phản hồi nói tới. Với:

~~~http
GET /orders?status=PAID&limit=20
~~~

thì Link có thể mô tả mối quan hệ của *trang collection hiện tại* với trang tiếp theo.

RFC 8288 cũng định nghĩa tham số **anchor** để nêu một context khác:

~~~http
Link: </guides/orders>; rel="help"; anchor="/orders"
~~~

Ở ví dụ này, liên kết trợ giúp được đặt trong ngữ cảnh **/orders**. Việc sử dụng **anchor** có ý nghĩa cụ thể và một số client có thể không hỗ trợ hoặc không áp dụng các link có context thay thế. Với REST API thông thường, nên ưu tiên relation rõ ràng gắn với tài nguyên đang được truy cập, chỉ dùng anchor khi thật sự cần và đã kiểm tra khả năng xử lý của client.

## 3. Ngữ pháp Link header và cách đọc chính xác

### 3.1. Một phản hồi có thể chứa nhiều liên kết

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Link: </orders?limit=20&cursor=c2>; rel="next"
Link: </orders?limit=20>; rel="first"
Link: <https://docs.example.com/orders>; rel="describedby"; type="text/html"
~~~

Nhiều HTTP header field cùng tên có thể được biểu diễn hoặc kết hợp thành danh sách các link-value, ví dụ:

~~~http
Link: </orders?cursor=c2>; rel="next", </orders>; rel="first"
~~~

Với định dạng trên, **dấu phẩy phân tách các link-value**, còn **dấu chấm phẩy phân tách các tham số trong một link-value**. Nhưng dữ liệu hợp lệ có thể chứa dấu phẩy trong thành phần được quote hoặc trong URI reference được bao bởi dấu **< >**, nên parser **không được** dùng phép **split(",")** một cách mù quáng.

### 3.2. Một đích có thể có nhiều relation type

~~~http
Link: </orders>; rel="first canonical"
~~~

Ví dụ này thể hiện **hai relation type** cho cùng một target: **first** và **canonical**. Danh sách relation type được ngăn bằng khoảng trắng trong giá trị của **rel**. Client phải phân tích từng type sau khi parse cú pháp header, không coi chuỗi nguyên **"first canonical"** là một tên relation duy nhất.

Một API thường dễ đọc hơn khi gửi từng quan hệ thành một link-value riêng, đặc biệt nếu các quan hệ có thuộc tính hoặc mục tiêu khác nhau. Tuy nhiên, client vẫn phải hỗ trợ dạng relation list hợp lệ theo chuẩn.

### 3.3. Target attributes

~~~http
Link: <https://docs.example.com/orders.vi.html>; rel="help"; hreflang="vi"; type="text/html"; title="Hướng dẫn đơn hàng"
~~~

| Thuộc tính | Vai trò | Lưu ý |
| --- | --- | --- |
| **rel** | Xác định mối quan hệ giữa context và target. | Thành phần quan trọng nhất để hiểu ý nghĩa liên kết. |
| **hreflang** | Gợi ý ngôn ngữ của target. | Là thông tin mô tả; không chứng minh nội dung chắc chắn được phục vụ đúng ngôn ngữ. |
| **type** | Gợi ý media type của target. | Không thay thế Content-Type thực tế khi client truy xuất target. |
| **title** | Nhãn dễ đọc của liên kết. | Không dùng làm mã logic vì có thể được dịch hoặc đổi. |
| **title*** | Dạng nhãn hỗ trợ bộ ký tự/ngôn ngữ mở rộng theo quy tắc tương ứng. | Cần parser đúng cú pháp giá trị mở rộng, không parse bằng thao tác cắt chuỗi tự chế. |
| **anchor** | Gợi ý context khác cho liên kết. | Không dùng để vượt quyền hoặc thay đổi ý nghĩa dữ liệu mà client không hiểu. |

Ví dụ chỉ dùng **hreflang/type/title** làm metadata; việc một URL có vẻ dẫn tới HTML không miễn trừ client khỏi kiểm tra loại nội dung, chính sách CORS hoặc bảo mật khi thực sự gọi URL đó.

### 3.4. Đừng nhầm Link header với HTML link element

HTML có thể chứa:

~~~html
<link rel="canonical" href="https://example.com/products/42">
~~~

HTTP response có thể chứa:

~~~http
Link: <https://example.com/products/42>; rel="canonical"
~~~

Hai cú pháp khác nhau nhưng đều biểu thị quan hệ liên kết. Link trong HTTP header không phụ thuộc vào việc body là HTML hay JSON. Đối với API trả JSON, Link header thường giúp công bố metadata điều hướng mà không cần định nghĩa một trường JSON mới.

## 4. Relation types: ý nghĩa do quan hệ quyết định

**Relation type** cho biết đích liên hệ thế nào với context. Không nên suy đoán chỉ từ tên đường dẫn hoặc tên tham số query. Các quan hệ thường gặp:

| Quan hệ | Ý nghĩa thực hành | Ví dụ |
| --- | --- | --- |
| **self** | Một liên kết đến tài nguyên được xác định là context của quan hệ theo định nghĩa relation. | Trang/tài nguyên đang được mô tả. |
| **next** | Tài nguyên tiếp theo trong một chuỗi có thứ tự. | Trang tiếp theo của collection. |
| **prev** | Tài nguyên trước đó trong chuỗi có thứ tự. | Trang trước của collection. |
| **first** | Tài nguyên đầu tiên trong chuỗi có thứ tự. | Trang đầu của danh sách. |
| **last** | Tài nguyên cuối cùng trong chuỗi có thứ tự. | Trang cuối, nếu server xác định được. |
| **canonical** | URI được lựa chọn làm định danh chuẩn của một tài nguyên theo ngữ nghĩa quan hệ. | Địa chỉ chuẩn thay cho URL có tham số theo dõi. |
| **alternate** | Biểu diễn hoặc phiên bản thay thế có liên hệ. | Phiên bản ở định dạng/ngôn ngữ khác. |
| **describedby** | Tài nguyên mô tả thêm về context. | Tài liệu schema/metadata. |
| **help** | Tài nguyên trợ giúp liên quan đến context. | Hướng dẫn dùng API hoặc giao diện. |

Không phải mọi relation đều phù hợp cho mọi API. Một relation type cần có **định nghĩa ngữ nghĩa rõ ràng**, không chỉ là một từ tiếng Anh ngẫu nhiên.

### 4.1. Registered relation và extension relation

Theo mô hình Web Linking, một loại quan hệ có thể là:

- **Registered relation type:** tên ngắn được đăng ký theo quy trình tương ứng, ví dụ **next**, **prev**, **alternate**.
- **Extension relation type:** URI tuyệt đối định danh loại quan hệ riêng, ví dụ:

~~~http
Link: </jobs/job-71>; rel="https://api.example.com/rels/job-status"
~~~

Ở ví dụ, **https://api.example.com/rels/job-status** là URI định danh ngữ nghĩa “tài nguyên theo dõi trạng thái job” do API tự định nghĩa; cần tài liệu cho client. Nó **không bắt buộc** phải là endpoint thực hiện job, cũng không mang nghĩa một phương thức HTTP cụ thể.

Khi cần relation riêng, không nên đặt **rel="pay-now"** rồi mặc nhiên coi đây là relation chuẩn đã đăng ký. Dùng URI extension ổn định, có tài liệu ý nghĩa và kế hoạch tương thích; kiểm tra danh mục relation chuẩn trước khi tự tạo.

### 4.2. Relation không mô tả đầy đủ một thao tác HTTP

~~~http
Link: </orders/ord-123>; rel="self"
~~~

Thông tin này **không nói rằng client được POST, PATCH hay DELETE** tới URL, cũng không khẳng định client có quyền truy cập. Client vẫn phải tuân theo hợp đồng phương thức, xác thực và phân quyền của tài nguyên đích.

Nếu muốn biểu diễn các **hành động** như hủy đơn, thanh toán hoặc cập nhật theo trạng thái, API có thể cần định dạng hypermedia hỗ trợ action/method/schema hoặc một hợp đồng riêng. HTTP Link chỉ mô tả quan hệ có kiểu; nó không phải một *form* hay *command* hoàn chỉnh.

### 4.3. Tại sao self và canonical không giống nhau?

Một trang collection có thể được gọi qua URI cụ thể:

~~~http
GET /orders?status=PAID&limit=20&cursor=c2
~~~

Quan hệ **self** thường trỏ về chính biểu diễn/trang cụ thể. **Canonical** dùng khi muốn chỉ ra một URI được xem là chuẩn theo chính sách tài nguyên. Ví dụ, một URL có tham số marketing có thể liên kết đến URI sản phẩm chuẩn, nhưng URI của một trang cursor thường là định danh của trang đó trong tập kết quả, không mặc nhiên có thể coi trang đầu là canonical cho mọi trang sau.

Tránh gắn canonical vào mọi trang với cùng đích chỉ để client “quay về đầu”; nếu mục tiêu chỉ là trang đầu, **first** diễn đạt đúng hơn.

## 5. Bài toán điển hình: phân trang REST bằng Link header

### 5.1. Trang đầu và trang tiếp theo

Giả sử API đơn hàng được sắp xếp ổn định theo **created_at DESC, id DESC**. Với năm đơn đã thanh toán, thứ tự là:

~~~text
ord-105, ord-104, ord-103, ord-102, ord-101
~~~

Trang đầu, kích thước 2:

~~~http
GET /orders?status=PAID&limit=2 HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
Content-Type: application/json
Link: </orders?status=PAID&limit=2&cursor=after104>; rel="next"
Link: </orders?status=PAID&limit=2>; rel="first"
Cache-Control: private, no-store

{"items":[{"id":"ord-105"},{"id":"ord-104"}]}
~~~

Trang thứ hai:

~~~http
GET /orders?status=PAID&limit=2&cursor=after104 HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
Content-Type: application/json
Link: </orders?status=PAID&limit=2&cursor=after102>; rel="next"
Link: </orders?status=PAID&limit=2>; rel="first"
Link: </orders?status=PAID&limit=2>; rel="prev"

{"items":[{"id":"ord-103"},{"id":"ord-102"}]}
~~~

Trang cuối:

~~~http
GET /orders?status=PAID&limit=2&cursor=after102 HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
Content-Type: application/json
Link: </orders?status=PAID&limit=2>; rel="first"
Link: </orders?status=PAID&limit=2&cursor=after104>; rel="prev"

{"items":[{"id":"ord-101"}]}
~~~

**Các cursor after104/after102 là tên minh họa**, không phải cơ chế token đủ an toàn. Production nên dùng token opaque có xác thực tính toàn vẹn hoặc state trên server. Giá trị **prev** trong ví dụ là đích đã biết cho quá trình duyệt này; nếu cần quay về nhiều trang bất kỳ, server phải hỗ trợ phân trang ngược hoặc có một cách lưu lịch sử trang.

Trang cuối **không có Link rel="next"** vì không còn phần tiếp theo tại thời điểm server tính kết quả. Việc không có next chỉ nói về tập kết quả của lần truy vấn và hợp đồng phân trang; nó không chứng minh collection sẽ không có đơn mới trong tương lai.

### 5.2. Cách server tạo next link khi dùng keyset

Để trả 2 dòng, truy vấn 3 dòng (**limit + 1**):

~~~sql
SELECT id, created_at, status
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
  AND (
        :after_created_at IS NULL
        OR created_at < :after_created_at
        OR (created_at = :after_created_at AND id < :after_id)
      )
ORDER BY created_at DESC, id DESC
LIMIT :limit_plus_one;
~~~

Đây là truy vấn minh họa cho PostgreSQL với giả định các giá trị khóa sắp xếp không NULL và **after_created_at/after_id cùng được cung cấp hoặc cùng vắng mặt**. Để hệ quản trị dùng index hiệu quả, triển khai thực có thể dùng **hai câu SQL** riêng cho trang đầu và trang tiếp, tránh biểu thức OR bao quát điều kiện thiếu cursor. Phải đặt bộ lọc tenant từ danh tính xác thực, không tin tenant do client tùy ý gửi.

Quy trình:

1. Nếu số dòng tìm được lớn hơn **limit**, còn trang tiếp theo.
2. Chỉ trả **limit** dòng đầu cho client.
3. Lấy khóa sắp xếp của **dòng cuối thực sự trả** để tạo cursor tiếp.
4. Phát Link **next** chứa đầy đủ filter/sort/limit và cursor theo hợp đồng.
5. Nếu không còn dòng dư thì **không phát next**.

Nếu lấy cursor từ **dòng dư thứ limit + 1**, client có thể bỏ qua dòng này ở trang sau. Nếu chỉ sắp xếp theo **created_at** không duy nhất, các bản ghi trùng timestamp có thể bị bỏ sót. Cần tie-breaker duy nhất như ID, trong đó ID không NULL và quy tắc so sánh ổn định.

### 5.3. Giữ toàn bộ ngữ cảnh truy vấn trong link

Sai:

~~~http
GET /orders?status=PAID&sort=-createdAt&limit=20

Link: </orders?cursor=c2>; rel="next"
~~~

Nếu server không mã hóa hoặc khôi phục filter/sort/limit từ cursor, client đi theo link có thể vô tình nhận **tập kết quả khác**.

Một thiết kế rõ ràng hơn:

~~~http
Link: </orders?status=PAID&sort=-createdAt&limit=20&cursor=c2>; rel="next"
~~~

Hoặc server có thể mã hóa toàn bộ ngữ cảnh vào token và công bố rằng chỉ cần tham số cursor. Dù chọn cách nào, **server phải ràng buộc cursor với truy vấn trước đó**, kiểm tra limit, sort, filter và quyền truy cập. Link header không làm một token cursor trở nên đáng tin cậy nếu token có thể sửa nội dung mà server không kiểm chứng.

### 5.4. Khi nào nên phát first, prev, last?

| Relation | Khi nên phát | Cần lưu ý |
| --- | --- | --- |
| **first** | Có cách xác định trang đầu. | Phải giữ filter và sort. |
| **next** | Có kết quả sau trang hiện tại theo hợp đồng. | Chỉ phát khi thực sự có trang sau. |
| **prev** | Hệ thống thực sự dựng được trang trước. | Keyset ngược cần so sánh/ORDER BY đúng và xử lý các bản ghi thay đổi. |
| **last** | Server biết chính xác trang cuối và có thể tạo URI có nghĩa cho nó. | Với cursor/keyset trên tập lớn, tìm trang cuối có thể đắt; không bắt buộc phát last. |

Đừng phát một URL **last** chỉ vì muốn có đủ bốn liên kết. Việc nhảy tới trang cuối cần thuật toán, dữ liệu và mức nhất quán phù hợp; nhiều API infinite-scroll chỉ hỗ trợ **next** và **first**.

### 5.5. Link header không bảo đảm snapshot

Một cursor keyset có thể tránh lặp bản ghi do insert mới ở đầu danh sách, nhưng nếu trường sort thay đổi, bản ghi bị xóa hoặc filter membership thay đổi giữa hai lần GET, tập kết quả vẫn có thể biến động. Link **next** là **chỉ dẫn truy vấn tiếp theo**, không phải bằng chứng các trang thuộc cùng snapshot bất biến.

Nếu nghiệp vụ cần đọc chính xác một tập ID tại một thời điểm, cần snapshot, job export hoặc mô hình khác có mốc nhất quán được định nghĩa rõ. Link header vẫn có thể dùng để điều hướng giữa các phần kết quả đó, nhưng **tính nhất quán thuộc về kiến trúc dữ liệu**, không phải tự đến từ relation **next**.

## 6. HTTP Link so với Location, Allow và redirect

Các header HTTP mô tả những thông tin **khác nhau**:

| Header / cơ chế | Chức năng | Ví dụ |
| --- | --- | --- |
| **Location** trong **201 Created** | Xác định tài nguyên được tạo theo ngữ nghĩa của response. | Location: /orders/ord-123 |
| **Location** trong **3xx** phù hợp | Chỉ đích chuyển hướng. | 303 See Other với Location: /jobs/job-71 |
| **Link** | Công bố quan hệ có kiểu giữa context và target. | Link: </orders?page=2>; rel="next" |
| **Allow** | Liệt kê phương thức được phép tại resource, đặc biệt với **405**. | Allow: GET, HEAD |
| **Content-Location** | Liên hệ representation được gửi với một URI theo semantics HTTP. | Dùng đúng khi phù hợp biểu diễn, không thay Location. |

### 6.1. POST tạo tài nguyên

~~~http
POST /orders HTTP/1.1
Content-Type: application/json

{"customerId":"cust-17"}

HTTP/1.1 201 Created
Location: /orders/ord-123
Content-Type: application/json

{"id":"ord-123","status":"PENDING"}
~~~

**Location** là header mang ngữ nghĩa tạo tài nguyên. Phản hồi 201 cũng có thể cung cấp **Link** mang quan hệ phù hợp với context, chẳng hạn tài liệu mô tả tài nguyên; cần xác định chính xác context theo ngữ nghĩa của phản hồi, không tự động cho rằng mọi Link có **rel="self"** trỏ đến tài nguyên mới. Không thay Location bằng Link rồi cho rằng mọi client đều hiểu cách lấy tài nguyên mới, bởi nhiều client xử lý **201 + Location** như một phần của hợp đồng HTTP quen thuộc.

Nếu API không cần Link tự trỏ đến resource, có thể bỏ nó và chỉ giữ Location. Header Link không phải điều kiện để một REST API trả **201** hợp lệ.

### 6.2. 202 Accepted: liên kết tới job theo dõi

Một yêu cầu tạo báo cáo có thể được chấp nhận để xử lý nền:

~~~http
POST /exports HTTP/1.1
Content-Type: application/json

{"format":"csv"}

HTTP/1.1 202 Accepted
Content-Type: application/json
Link: </jobs/job-71>; rel="https://api.example.com/rels/job-status"

{"jobId":"job-71","state":"QUEUED"}
~~~

Vì **202** không có nghĩa job chắc chắn sẽ thành công, client cần theo dõi tài nguyên trạng thái job. Ở đây relation là một **extension relation** có định nghĩa riêng trong API; Link chỉ công bố mối quan hệ, không thay hợp đồng của **GET /jobs/job-71**.

Không tự suy luận rằng **rel="next"** phù hợp cho job trạng thái: “next” thường diễn đạt phần tử tiếp trong chuỗi, không phải một bước nghiệp vụ đang chờ hoàn thành.

### 6.3. Link không phải lệnh redirect

~~~http
HTTP/1.1 200 OK
Link: <https://docs.example.com/orders>; rel="help"
~~~

Client **không bị yêu cầu tự động chuyển tới trang tài liệu**. Đó là một liên kết ngữ nghĩa có thể được sử dụng nếu client hỗ trợ. Muốn chỉ định chuyển hướng một HTTP request, server dùng status 3xx và **Location** theo ngữ nghĩa tương ứng. Không dùng **200 + Link rel="next"** rồi mong browser tự chuyển sang trang sau.

## 7. Link ở header và link trong body: nên chọn cái nào?

Hai cách có thể cùng tồn tại:

### 7.1. Link trong HTTP header

~~~http
HTTP/1.1 200 OK
Link: </orders?cursor=c2>; rel="next"
Content-Type: application/json

{"items":[{"id":"ord-105"},{"id":"ord-104"}]}
~~~

**Ưu điểm:**

- Phân tách metadata điều hướng khỏi cấu trúc domain JSON.
- Có thể công bố liên kết ở phản hồi không phụ thuộc biểu diễn nội dung cụ thể.
- Client hoặc middleware có khả năng đọc HTTP header có thể quan sát relation.
- Có thể dùng chuẩn Web Linking thay vì mỗi API tự đặt một trường **nextPageUrl**.

**Giới hạn:**

- Không phải SDK hoặc UI nào cũng có sẵn parser Link chuẩn.
- Một số gateway hoặc cấu hình CORS có thể không chuyển/cho JavaScript đọc header như mong đợi.
- Khó mô tả các hành động phức tạp gồm phương thức, request schema hoặc điều kiện thực thi chỉ bằng Link.
- Một số đội phát triển quen JSON envelope hơn, nên cần chuẩn hóa và tài liệu rõ ràng.

### 7.2. Link trong body

~~~json
{
  "items": [
    {"id":"ord-105"},
    {"id":"ord-104"}
  ],
  "_links": {
    "next": {"href": "/orders?cursor=c2"},
    "first": {"href": "/orders"}
  }
}
~~~

Đây là **cấu trúc JSON minh họa theo phong cách hypermedia**, không phải một cách tuần tự hóa trực tiếp của RFC 8288. Nếu chọn HAL hoặc một định dạng hypermedia khác, hãy tuân theo media type, schema và semantics của định dạng đó; không cho rằng mọi object có trường **_links** đều tự động hợp chuẩn HAL.

### 7.3. Bảng lựa chọn

| Tiêu chí | Link header | JSON body links |
| --- | --- | --- |
| Metadata điều hướng đơn giản | Phù hợp. | Cũng phù hợp. |
| Cần gắn relation với cả response | Rất tự nhiên. | Phải định nghĩa vị trí trong envelope. |
| Client chỉ làm việc với JSON model | Cần parser/header access. | Dễ truy cập từ object đã parse. |
| Nhiều media type cho cùng resource | Có thể tái sử dụng ở lớp HTTP. | Mỗi media type có cấu trúc riêng. |
| Form/action có method và field yêu cầu | Không đủ thông tin nếu chỉ có Link. | Cần định dạng hypermedia hỗ trợ hành động hoặc hợp đồng bổ sung. |
| CORS trên trình duyệt | Có thể cần expose header. | Dữ liệu body vốn có theo chính sách CORS áp dụng. |

Không nhất thiết chọn duy nhất một cách. Nếu cùng công bố next trong Link header và body, phải bảo đảm **hai giá trị nhất quán**, cùng filter, sort và cursor; tránh tạo hai nguồn sự thật mâu thuẫn.

## 8. Thiết kế server: tạo Link an toàn, ổn định

### 8.1. Đừng nối URL bằng chuỗi thô

Đoạn giả mã sau dễ gây lỗi:

~~~text
link = "<" + "/orders?status=" + userStatus
       + "&cursor=" + rawCursor + ">; rel=\"next\""
~~~

Nếu **userStatus** hoặc **rawCursor** không được kiểm tra và encode phù hợp, dấu **&**, dấu cách, ký tự **>**, xuống dòng hoặc các thành phần đặc biệt có thể làm hỏng URI hay cú pháp header. Dữ liệu ngoài kiểm soát không được phép chèn thêm header hoặc khiến client đến host khác.

Nguyên tắc tạo Link:

1. Tạo URI bằng **URI builder** hiểu cách encode path segment/query parameter.
2. Chỉ cho phép **sort/filter** trong whitelist, giới hạn kích thước trang.
3. Dùng **cursor opaque** đã được ký xác thực hoặc tham chiếu tới server-side state; không cho client tự đặt ID/tenant từ token không đáng tin.
4. Tạo link target từ **base path/public origin tin cậy**; khi dùng absolute URL sau reverse proxy phải có cấu hình forwarded headers đáng tin.
5. Giữ nguyên bối cảnh truy vấn theo hợp đồng và không mang token truy cập nhạy cảm vào query string.
6. Kiểm thử cú pháp header, việc phân giải URI tương đối và khả năng đọc qua gateway/CORS.

### 8.2. Ví dụ Java/Spring MVC

Ví dụ sử dụng Spring MVC và URI builder. Service/query model ở đây là lớp giả định, để tập trung vào phần xây response HTTP.

~~~java
import java.util.List;
import java.util.HashMap;
import java.util.Map;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

record OrderView(String id, String status) {}
record OrderSlice(List<OrderView> items, String nextCursor) {}

interface OrderQueryService {
    OrderSlice listForCurrentUser(String status, int limit, String cursor);
}

@RestController
@RequestMapping("/orders")
class OrdersController {
    private final OrderQueryService service;

    OrdersController(OrderQueryService service) {
        this.service = service;
    }

    @GetMapping
    ResponseEntity<List<OrderView>> list(
            @RequestParam(defaultValue = "PAID") String status,
            @RequestParam(defaultValue = "20") int limit,
            @RequestParam(required = false) String cursor) {

        // Hợp đồng minh họa: limit trong [1, 100].
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Invalid page size");
        }

        OrderSlice page = service.listForCurrentUser(status, limit, cursor);
        HttpHeaders headers = new HttpHeaders();
        headers.setCacheControl("private, no-store");

        String firstUri = ordersUri(status, limit, null);
        headers.add("Link", "<" + firstUri + ">; rel=\"first\"");

        if (page.nextCursor() != null) {
            String nextUri = ordersUri(status, limit, page.nextCursor());
            headers.add("Link", "<" + nextUri + ">; rel=\"next\"");
        }

        return ResponseEntity.ok()
                .headers(headers)
                .contentType(MediaType.APPLICATION_JSON)
                .body(page.items());
    }

    private static String ordersUri(
            String status, int limit, String cursor) {
        UriComponentsBuilder builder =
                UriComponentsBuilder.fromPath("/orders")
                        .queryParam("status", "{status}")
                        .queryParam("limit", limit);
        Map<String, Object> variables = new HashMap<>();
        variables.put("status", status);
        if (cursor != null) {
            builder.queryParam("cursor", "{cursor}");
            variables.put("cursor", cursor);
        }
        // Encode cả ký tự dành riêng nằm trong giá trị query variable.
        return builder.encode().buildAndExpand(variables).toUriString();
    }
}
~~~

**Các giả định phải hoàn thiện trong hệ thống thật:**

- **OrderQueryService** phải kiểm tra status/filter, quyền dữ liệu của principal, cursor signature, expiry và giới hạn sort/limit; controller **không tự bảo đảm** những điều đó.
- Nếu listForCurrentUser nhận cursor không hợp lệ, cần ánh xạ sang **400 Bad Request** với Problem Details phù hợp; ví dụ code trên chưa bao gồm exception handler.
- **ordersUri** tạo URI tương đối bắt đầu bằng **/orders**, giúp tránh tin vào header Host do người gọi kiểm soát. Nếu API chạy dưới prefix/public base path, cần cấu hình và kiểm tra đường dẫn đó.
- Dùng nhiều **Link** field là hợp lệ; một số gateway có thể gộp chúng khi chuyển tiếp. Client phải parse cả hai cách.
- **first** chỉ có ý nghĩa nếu endpoint thật sự hỗ trợ truy cập trang đầu của cùng bộ lọc. Ví dụ đang dùng status cố định qua từng request.
- Không tạo Link chứa bearer token hoặc thông tin cá nhân của user.

Controller trả **200 OK** với danh sách rỗng khi không có dữ liệu; **không có next link** ở trang cuối. Trong contract có thể trả JSON envelope chứa hasNext nếu muốn, nhưng không bắt buộc khi client đã dùng Link header.

### 8.3. Kiểm tra link sau khi đi qua gateway

Trên production, gateway có thể gắn route prefix, chuyển từ HTTP nội bộ sang HTTPS công khai, hoặc dùng nhiều host. Nếu app dựng absolute URI dựa trên **Host** hoặc **X-Forwarded-Host** chưa được tin cậy, attacker có thể tác động đích Link hoặc Location.

Hãy dùng cấu hình public base URL và cơ chế trust proxy đúng; kiểm tra host/scheme ở phản hồi thực tế sau gateway. Kiểm thử với request Host không hợp lệ để chắc chắn server không phát Link dẫn sang domain do attacker chọn.

## 9. Client: diễn giải Link đúng và không theo liên kết mù quáng

### 9.1. Cách client nên xử lý

~~~mermaid
flowchart TD
    A[Nhận response HTTP] --> B{Có Link header?}
    B -->|Không| C[Dừng hoặc dùng hợp đồng body]
    B -->|Có| D[Parse chuẩn Link header]
    D --> E[Lọc các relation type hỗ trợ]
    E --> F{Có rel=next hợp lệ?}
    F -->|Không| C
    F -->|Có| G[Phân giải URI target]
    G --> H[Kiểm tra scheme, origin, phạm vi và quyền]
    H --> I{Đích được phép?}
    I -->|Không| J[Từ chối / báo lỗi]
    I -->|Có| K[GET next với xác thực an toàn]
~~~

Các bước quan trọng:

- **Không parse bằng split dấu phẩy/dấu chấm phẩy**. Dùng parser hiểu dấu ngoặc góc, quoted-string, escape và cú pháp tham số.
- **Chỉ chọn relation đã hiểu**. Có thể có nhiều link cùng hoặc khác relation; cần chính sách khi có nhiều đích cùng rel.
- **Phân giải URI reference** theo ngữ cảnh phù hợp; không tự giả định mọi href là absolute.
- **Không tự chuyển Authorization sang host lạ**. Với link chéo origin, cân nhắc whitelist/trust boundary hoặc hỏi hệ thống cho phép.
- **Kiểm tra giới hạn**: số trang tối đa, vòng lặp link, TTL cursor, 429/5xx, timeout, hủy request.
- **Không dùng URL xuất hiện trong Link làm lệnh đặc quyền**. Quan hệ chỉ mô tả tài nguyên; quyền và phương thức được kiểm tra riêng.

### 9.2. Ví dụ client giả mã

~~~text
response = GET("/orders?status=PAID&limit=20")
consume(response.body.items)

visited = set()
while response.status == 200:
    nextTarget = parseLinkRelations(response.headers).first("next")
    if nextTarget is absent:
        break

    nextUrl = resolveRelativeUrl(response.url, nextTarget)
    require isAllowedApiTarget(nextUrl)
    require nextUrl not in visited
    visited.add(nextUrl)

    response = GET(nextUrl, boundedRetryPolicy)
    if response.status != 200:
        handleHttpError(response)
        break
    consume(response.body.items)
~~~

Đây là giả mã, không phải thư viện Link parser có thể copy trực tiếp. Ở ứng dụng thực, cần giới hạn tổng số trang/tài nguyên và tránh vừa retry vừa hiển thị lại bản ghi trùng nếu các response bị phát lặp.

### 9.3. Các lỗi parsing thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Split trực tiếp theo **,** | Phá trường chứa dấu phẩy trong vùng được quote hoặc URI reference. | Dùng parser hiểu cú pháp Link. |
| Split **rel="next prev"** thành một relation duy nhất | Không nhận ra next và prev. | Parse relation list theo khoảng trắng. |
| Chỉ đọc Link đầu tiên | Bỏ qua next nếu header đầu là first hoặc describedby. | Xử lý mọi link-value hợp lệ. |
| Coi relative URI là absolute | Gọi nhầm host/path. | Phân giải với context phù hợp. |
| Coi title là loại quan hệ | Hỏng khi server đổi ngôn ngữ. | Dùng rel, không dùng title làm logic. |
| Follow mọi link từ API | Có thể gửi request sang domain độc hại. | Kiểm soát scheme, origin, quyền và mục đích. |
| Không giới hạn vòng lặp | Server lỗi phát next trỏ lại trang cũ, client lặp mãi. | Theo dõi URL/cursor đã thăm và giới hạn số trang. |

## 10. Bảo mật, CORS và caching

### 10.1. Link không cấp quyền

Phản hồi:

~~~http
Link: </admin/reports>; rel="related"
~~~

không chứng minh người đang đăng nhập có quyền **GET /admin/reports**. Khi client theo liên kết, API vẫn phải kiểm tra xác thực, phân quyền theo resource/tenant, giới hạn tần suất và chính sách dữ liệu. Server cũng nên chỉ đưa các liên kết phù hợp với quyền khi đó là hợp đồng hypermedia hướng theo capability, nhưng **ẩn link không thay cho kiểm tra quyền ở endpoint đích**.

Nếu một token cursor thuộc tenant A xuất hiện trong Link, tenant B không được dùng token đó để đọc dữ liệu A. Cần kiểm tra lại danh tính và quyền hiện hành mỗi lần GET, kể cả khi cursor được ký.

### 10.2. Link và nguy cơ SSRF

Client máy chủ đôi khi được lập trình để tự động theo các liên kết trong phản hồi API. Một Link trỏ đến mạng nội bộ, địa chỉ metadata cloud hoặc domain giả mạo có thể trở thành đường tấn công **server-side request forgery (SSRF)** nếu client coi mọi target là an toàn.

Ví dụ target không đáng tin:

~~~http
Link: <http://127.0.0.1:8080/internal>; rel="next"
~~~

Client **không nên** tự động theo link này chỉ vì rel là next. Cần xác minh scheme, origin, địa chỉ IP/DNS sau phân giải, chống redirect qua host không được phép và bảo vệ thông tin xác thực. Đối với phân trang API công khai, một chính sách thường hợp lý là **chỉ chấp nhận next trên origin hoặc danh sách origin đã công bố**.

### 10.3. JavaScript trình duyệt và CORS

Một frontend ở domain khác gọi API bằng **fetch** có thể nhận response thành công nhưng **không đọc được header Link** nếu server không expose nó qua CORS:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Expose-Headers: Link
Link: </orders?cursor=c2>; rel="next"
~~~

**Access-Control-Expose-Headers** cho phép JavaScript truy cập tên header không thuộc nhóm mặc định được lộ theo CORS. Cấu hình CORS còn phải đáp ứng các yêu cầu khác như credentials và allow-origin; chỉ thêm header trên không đủ cho mọi trường hợp.

Nếu API có dữ liệu người dùng, không cấu hình CORS quá rộng. Với requests có credentials, cần tuân theo chính sách origin cụ thể, không mặc định cho mọi origin truy cập response.

### 10.4. Caching

Link header là **một phần metadata của phản hồi HTTP**, vì vậy cần thiết kế nó cùng với cache behavior:

- Trang collection công khai, ít đổi có thể cache theo chính sách với **Cache-Control** và validator thích hợp.
- Trang chứa dữ liệu riêng của user/tenant nên dùng chính sách **private** hoặc **no-store** theo mức nhạy cảm; tránh CDN lưu và chia sẻ Link có cursor riêng sang user khác.
- Nếu response được revalidate bằng ETag/Last-Modified, metadata điều hướng phải vẫn nhất quán với representation và trạng thái dữ liệu được dùng.
- Không mặc định **rel="next"** có nghĩa URI đích luôn giữ nội dung cố định khi GET trong tương lai.

Phân trang cursor trên collection thay đổi liên tục thường cần thận trọng với cache. Nếu ứng dụng chủ động tạo snapshot bất biến, việc cache có thể thuận lợi hơn nhưng phải công bố điều kiện hết hạn và phân quyền của snapshot.

### 10.5. Quan sát và dữ liệu nhạy cảm

API nên theo dõi số lượng phản hồi có next, tỷ lệ cursor lỗi/hết hạn, độ trễ trang sâu, 429 và các trường hợp client không đi hết chuỗi. Nhưng Link có thể chứa cursor và filter; access log/gateway log không nên lưu nguyên URL/token nhạy cảm nếu không cần thiết. Sử dụng route template, request ID và telemetry có redaction phù hợp.

## 11. Mô tả Link header bằng OpenAPI 3.1

OpenAPI có thể mô tả **Link** như một response header:

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /orders:
    get:
      summary: Liệt kê đơn hàng với Link-based pagination
      parameters:
        - in: query
          name: status
          schema:
            type: string
            enum: [PAID, PENDING, CANCELLED]
            default: PAID
        - in: query
          name: limit
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
        - in: query
          name: cursor
          description: Opaque cursor của trang trước
          schema:
            type: string
      responses:
        '200':
          description: Trang dữ liệu. Link next chỉ có khi còn trang.
          headers:
            Link:
              description: >
                Theo RFC 8288. Có thể có nhiều link-value
                (next, first, prev...) trong một hoặc nhiều Link field.
                Client phải parse quan hệ và URI reference theo chuẩn.
              schema:
                type: string
              example: '</orders?status=PAID&limit=20&cursor=c2>; rel="next"'
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderList'
        '400':
          description: Filter, limit hoặc cursor không hợp lệ
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'
        '401':
          description: Chưa xác thực hợp lệ
        '403':
          description: Không có quyền xem collection
        '429':
          description: Quá nhiều yêu cầu
components:
  schemas:
    OrderList:
      type: object
      required: [items]
      properties:
        items:
          type: array
          items:
            type: object
            properties:
              id: {type: string}
              status: {type: string}
    Problem:
      type: object
      properties:
        type: {type: string, format: uri-reference}
        title: {type: string}
        status: {type: integer}
        detail: {type: string}
~~~

**Hai cách dùng từ Link dễ nhầm:** OpenAPI còn có **Link Object** để mô tả khả năng liên hệ giữa các operation trong hợp đồng. Đó **không đồng nghĩa** việc server thực sự phát **HTTP Link header** ở runtime. Khi muốn tài liệu hóa header RFC 8288, dùng phần **responses.headers.Link** như ví dụ.

Mẫu trên thể hiện **Link** dưới dạng chuỗi vì parser HTTP sẽ nhận các trường/header có thể được kết hợp; trong thực tế, giá trị có thể là danh sách nhiều link-value và không phải client generator nào cũng sinh parser Web Linking tự động. Đừng xem OpenAPI khai báo header là đủ để chứng minh SDK xử lý đúng relation.

## 12. Kiểm thử Link header ở mức HTTP và ứng dụng

### 12.1. Ma trận kiểm thử

| ID | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| L01 | Trang đầu có nhiều bản ghi hơn limit | **200**; Link có **rel="next"** trỏ trang kế đúng filter/limit. |
| L02 | Trang cuối hoặc collection rỗng | **200**; **không có rel=next**; body đúng. |
| L03 | Nhiều bản ghi cùng khóa thời gian | Cursor đi tiếp không mất/lặp vì có khóa phá hòa duy nhất. |
| L04 | Hai Link field cùng tên | Client nhận và phân tích được tất cả quan hệ. |
| L05 | Một Link header có nhiều link-value, phân tách bởi dấu phẩy | Parser nhận đủ next, first, describedby. |
| L06 | Giá trị title có dấu phẩy hoặc quoted string | Không tách sai link-value. |
| L07 | rel có nhiều relation type | Client nhận diện từng relation theo giá trị rel. |
| L08 | URI đích tương đối | Client phân giải đúng origin và path. |
| L09 | Cursor bị sửa/hết hạn hoặc đổi filter | Server từ chối theo hợp đồng, không lộ dữ liệu tenant khác. |
| L10 | Client có token của tenant khác | Mọi trang đều kiểm quyền; không trả dữ liệu ngoài phạm vi. |
| L11 | Header trỏ tới host/IP không tin cậy | Client không tự động theo hoặc gửi Authorization. |
| L12 | Gọi API qua gateway/reverse proxy | Scheme, host và prefix của link đúng origin công khai. |
| L13 | Web frontend khác origin | Có thể đọc **Link** khi CORS đã expose đúng; không mở quyền quá mức. |
| L14 | Cache response theo user/tenant | Không chia sẻ next cursor và dữ liệu giữa người dùng. |
| L15 | POST tạo resource | **201 + Location** đúng; Link nếu có không mâu thuẫn. |
| L16 | 202 Accepted có link job | Relation extension được tài liệu hóa; client không coi job đã hoàn thành. |
| L17 | Link next vòng về trang hiện tại | Client nhận ra vòng lặp hoặc chạm ngưỡng an toàn. |

### 12.2. Ví dụ curl

~~~bash
# -i cho thấy status line, response headers và body.
curl -i \
  -H 'Authorization: Bearer <access-token>' \
  'https://api.example.com/orders?status=PAID&limit=2'

# -I gửi HEAD: có thể quan sát metadata phù hợp nếu endpoint hỗ trợ.
curl -I \
  -H 'Authorization: Bearer <access-token>' \
  'https://api.example.com/orders?status=PAID&limit=2'
~~~

Với **HEAD**, server nên trả metadata nhất quán với GET tương ứng theo semantics HTTP, nhưng không có response body; việc hiện diện cụ thể của Link phụ thuộc thiết kế endpoint. **Không coi HEAD là bằng chứng** nội dung danh sách được trả đúng nếu chưa thử GET thật.

### 12.3. Ví dụ Spring MockMvc

Giả sử repository/service trong phần 8 trả hai đơn và một next cursor:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

var response = mockMvc.perform(get("/orders")
        .param("status", "PAID")
        .param("limit", "2"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$[0].id").value("ord-105"))
    .andReturn()
    .getResponse();

// Không giả định response chỉ có đúng một Link field.
assertThat(response.getHeaders("Link"))
    .anyMatch(value -> value.contains("rel=\"next\""));
~~~

Ví dụ trên giả định header **Link** được môi trường kiểm thử biểu diễn thành giá trị có chứa next. Khi response phát **nhiều Link field**, có thể dùng cách truy xuất **getHeaders("Link")** và parser Link chuyên dụng để xác minh từng relation, thay vì giả định giá trị duy nhất. Nếu endpoint bật Spring Security, test cần danh tính có quyền và dữ liệu seed đại diện.

### 12.4. Kiểm thử cú pháp, không chỉ so chuỗi

Một bài test tốt nên:

1. Lấy tất cả giá trị **Link** trong phản hồi.
2. Parse đúng chuẩn Web Linking, lấy relation type **next**.
3. Phân giải target thành URI tuyệt đối với context.
4. Kiểm tra path, filter, limit và chính sách origin của target.
5. Dùng target đó để gọi GET trang tiếp theo.
6. Xác nhận không lặp/mất ID trong dữ liệu tĩnh, xử lý đúng trang cuối.
7. Lặp lại qua gateway và frontend CORS khi ứng dụng thực sử dụng các tầng này.

Test chỉ so chuỗi **rel="next"** có thể vẫn PASS dù URL đích sai filter hoặc cursor, vì vậy cần test end-to-end theo chính link server phát.

## 13. Những phản mẫu thường gặp

| Phản mẫu | Vì sao nguy hiểm hoặc khó dùng? | Thiết kế tốt hơn |
| --- | --- | --- |
| Gọi mọi URL đích là **next** | Mất ngữ nghĩa relation; client không biết link nào để làm gì. | Dùng registered relation đúng hoặc extension URI có tài liệu. |
| Dùng **Link** thay cho **Location** khi POST tạo resource | Client HTTP không nhận được semantics 201/Location rõ ràng. | Duy trì Location; Link chỉ là metadata bổ sung. |
| Dùng **Link** để chỉ phương thức POST/PATCH mà không có hợp đồng | Link đơn thuần không cung cấp HTTP method, body schema và quyền. | Dùng hợp đồng thao tác hoặc định dạng hypermedia action. |
| Chỉ phát next trỏ **?cursor=...** và đánh mất filter | Client thấy tập kết quả khác. | Giữ filter/sort/limit hoặc ràng buộc tất cả trong cursor. |
| Phát next ở trang cuối | Client có thể gọi thêm vô hạn hoặc nhận dữ liệu lặp. | Phát next khi còn dữ liệu theo hợp đồng. |
| Tự parse Link bằng split dấu phẩy | Sai với cú pháp quote/URI phức tạp. | Dùng parser tuân RFC 8288. |
| Dùng Base64 không ký làm cursor | Client có thể đổi ID/tenant/filter. | Ký/MAC hoặc token opaque có state, kiểm tra quyền từng request. |
| Tự tạo absolute Link từ Host chưa được tin cậy | Host poisoning, liên kết tới domain ngoài ý muốn. | Public base URL/forwarded header trust policy. |
| Tự theo mọi Link và gửi Authorization | Có thể lộ token cho host lạ/SSRF. | Allowlist origin/scheme và tách xác thực theo đối tượng. |
| JSON body nói next=A, Link header nói next=B | Hai hợp đồng mâu thuẫn, client khác nhau hành xử khác nhau. | Chọn một nguồn điều hướng hoặc sinh cả hai từ cùng một kết quả. |
| Bật caching chung cho response cá nhân | Cursor/data của tenant này có thể lộ sang tenant khác. | Cache-Control theo mức nhạy cảm và chính sách auth. |
| Dùng **last** giả định trên collection biến động lớn | Tính trang cuối có thể đắt hoặc không có nghĩa ổn định. | Chỉ phát các relation server thật sự xác định được. |

## 14. Bài tập tình huống: API đơn hàng phục vụ dashboard và ứng dụng di động

### 14.1. Bối cảnh

Một nền tảng thương mại có REST API **GET /orders** phục vụ dashboard và ứng dụng di động. Dữ liệu tăng khoảng **100.000 đơn/ngày** và luôn có cập nhật. API lọc theo **status**, sort **createdAt DESC, id DESC**, phân trang bằng cursor. Dashboard chạy tại **https://dashboard.example.com**, API đặt tại **https://api.example.com** sau reverse proxy. Mỗi tenant chỉ được xem đơn của mình.

Nhóm backend muốn dùng **Link** header để công bố trang kế. Nhóm frontend phát hiện **fetch** không đọc được Link. Một ứng dụng tích hợp còn tự động theo mọi URL từ Link và có thể gửi token bearer sang host khác.

### 14.2. Nhiệm vụ

1. Thiết kế response cho trang đầu và trang cuối, dùng **rel="next"** và **rel="first"** hợp lý.
2. Nêu thông tin cần giữ trong cursor hoặc URL để trang sau không đổi filter/sort.
3. Chọn cấu hình CORS tối thiểu để frontend được phép đọc Link.
4. Chỉ ra rủi ro nếu backend xây absolute Link dựa trên **Host** do client tùy ý gửi.
5. Đề xuất quy tắc client theo link an toàn; có được gửi bearer token tới host khác không?
6. Nêu bài kiểm thử chứng minh không lặp/mất đơn khi nhiều đơn trùng timestamp.
7. Giải thích Link header khác **Location** khi tạo đơn bằng POST.

### 14.3. Lời giải tham khảo

**Trang đầu**, giả sử còn dữ liệu:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store
Access-Control-Allow-Origin: https://dashboard.example.com
Access-Control-Expose-Headers: Link
Link: </orders?status=PAID&limit=20&cursor=signed-c2>; rel="next"
Link: </orders?status=PAID&limit=20>; rel="first"

{"items":[{"id":"ord-105"},{"id":"ord-104"}]}
~~~

**Trang cuối:** không phát relation **next**, vẫn có thể phát **first**. Server phải trả **200** và collection rỗng nếu trang được yêu cầu hợp lệ nhưng không có bản ghi; 404 không phải mã mặc định của một collection rỗng.

**Cursor:** cần giữ khóa seek **(createdAt, id)**, sort, filter, limit, tenant hoặc phạm vi quyền, phiên bản và thời hạn; dùng chữ ký xác thực hoặc state opaque. Backend vẫn kiểm tra quyền hiện tại và áp dụng filter tenant ở mỗi request.

**CORS:** expose **Link** và chỉ định origin được cho phép theo chính sách credentials; không dùng CORS như biện pháp thay thế kiểm tra quyền API.

**Host header:** nếu lấy Host chưa đáng tin để dựng absolute URL, một request có Host giả có thể khiến response dẫn tới domain giả mạo. Nên tạo relative URI hoặc dùng cấu hình public origin đã tin cậy.

**Client:** chỉ theo relation cần thiết, phân giải target, kiểm tra scheme và allowlist origin; **không tự động chuyển bearer token sang host khác**. Giới hạn vòng lặp, số trang và retry.

**Kiểm thử:** tạo các đơn có createdAt trùng nhau, dùng limit=2 qua ba trang, so tập ID và thứ tự; dùng chính URL từ Link để gọi trang tiếp, không tự tạo cursor. Thử đổi filter, tenant, sửa token và chạy qua proxy.

**Location:** POST tạo đơn đồng bộ nên trả **201 + Location: /orders/{id}**. Link có thể thêm relation self hoặc khác, nhưng không thay thế semantics của Location.

### 14.4. Câu hỏi mở rộng

- Nếu có nhiều bản dịch tài liệu API, quan hệ và thuộc tính nào giúp client biết link dẫn tới ngôn ngữ nào?
- Nếu response chứa hai relation next vì lỗi cấu hình, client nên chọn tùy ý một cái hay coi hợp đồng mơ hồ và báo lỗi?
- Nếu muốn client thực hiện một lệnh hủy đơn chỉ khi đơn ở trạng thái PENDING, Link header đơn thuần có đủ mô tả method và điều kiện chưa?
- Nếu ứng dụng thêm Link vào 304 Not Modified, client có thể mặc định coi body 304 là JSON chứa items không?

**Gợi ý:** **hreflang** có thể gợi ý ngôn ngữ; relation trùng/mơ hồ cần quy tắc rõ hoặc báo lỗi, không tùy tiện chọn; Link không tự diễn tả form hành động; **304 không có body**, client dùng cache theo semantics HTTP và metadata phù hợp.

## 15. Checklist triển khai Link header đúng Web Linking

- [ ] Hiểu **Link** header là metadata quan hệ, không phải một URL đơn lẻ hoặc lệnh HTTP.
- [ ] Mỗi link có **target URI reference**, **rel** đúng ngữ nghĩa và context được xác định.
- [ ] Dùng relation chuẩn khi phù hợp; extension relation dùng **URI** ổn định và có tài liệu.
- [ ] Nếu nhiều Link, serial hóa/parse đúng danh sách; không dùng split dấu phẩy đơn giản.
- [ ] Parser xử lý URI trong **< >**, quoted-string và relation list có khoảng trắng.
- [ ] Khi dùng target tương đối, phân giải đúng context và public base path của API.
- [ ] Cẩn trọng với **anchor**; không thay đổi context khi client không hỗ trợ.
- [ ] Phân trang **next/prev/first/last** được phát khi thực sự có đích có nghĩa.
- [ ] Link next chứa đủ ngữ cảnh filter/sort/limit/cursor hoặc phục hồi được ngữ cảnh từ token.
- [ ] Keyset sort có tie-breaker duy nhất; next cursor lấy từ dòng cuối **thực sự trả**.
- [ ] Cursor được kiểm tra chữ ký/state, expiry, scope và phân quyền mỗi request.
- [ ] Không nhầm **Link rel="next"** với snapshot nhất quán hoặc nghĩa vụ trả next mãi mãi.
- [ ] **Location** vẫn được dùng theo semantics HTTP 201/3xx; Link là thông tin khác.
- [ ] CORS expose **Link** nếu JavaScript khác origin cần đọc header; auth/CORS tuân đúng chính sách.
- [ ] Không phát URI dựa trên Host/forwarded headers chưa được tin cậy hoặc token nhạy cảm trong Link.
- [ ] Client không follow tự động link đến origin lạ, không gửi bearer token mù quáng, có giới hạn vòng lặp.
- [ ] Cache-Control phù hợp response theo user/tenant; không chia sẻ cursor cá nhân.
- [ ] Spring/controller xuất Link với URI builder đúng encode; gateway không làm sai scheme/host/prefix.
- [ ] OpenAPI mô tả **responses.headers.Link**, điều kiện xuất hiện và các relation được hỗ trợ.
- [ ] Kiểm thử cú pháp, next URI thực, trang cuối, quyền, CORS, proxy, liên kết ngoại và Link trùng.

**Điểm cốt lõi:** **RFC 8288** chuẩn hóa cách nói “tài nguyên này liên hệ với tài nguyên kia như thế nào” bằng **Link header**, URI đích và relation type. Với REST API, Link đặc biệt hữu ích để công bố **next/prev/first** cho phân trang và các liên kết mô tả/trợ giúp. Nhưng Link không tự quyết định phương thức HTTP, không cấp quyền, không bảo đảm snapshot và không thay thế status hay Location. Một thiết kế đáng tin phải kết hợp **quan hệ đúng ngữ nghĩa, URI/cursor an toàn, phân quyền, cache, OpenAPI và kiểm thử end-to-end**.
