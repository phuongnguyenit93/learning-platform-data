# Media type, profile và quy ước diễn giải biểu diễn

## 1. Tại sao một biểu diễn JSON chưa đủ để client hiểu REST API?

Giả sử client nhận được phản hồi sau:

~~~json
{
  "id": "ord-913",
  "status": "PENDING_PAYMENT",
  "customerId": "cus-41",
  "paymentUrl": "/api/orders/ord-913/payment"
}
~~~

Đây là JSON hợp lệ. Nhưng nhìn vào cú pháp JSON, client **không thể tự biết**:

- **paymentUrl** là URI có thể gửi GET để xem thông tin, hay đích POST để thực hiện thanh toán?
- Khi đơn chuyển thành **PAID**, URL thanh toán có còn hợp lệ không?
- **customerId** có cần tự nối vào URI **/api/customers/** hay phải đi qua một liên kết được server cung cấp?
- Client có được dùng một mẫu chung để hiểu các trường đặc thù không, hay phải ghi nhớ quy ước riêng của từng endpoint?

**Hypermedia** giải quyết phần quan trọng của bài toán bằng cách đưa **liên kết, quan hệ liên kết và có thể cả thao tác được phép** vào biểu diễn. Tuy nhiên, chỉ có một trường tên **links** chưa tự bảo đảm hai hệ thống sẽ hiểu giống nhau. Client cần biết **quy tắc diễn giải biểu diễn (representation processing model)**.

Trong module **INTEGRATION_API_REST**, chủ đề này kết nối thiết kế **resource và URI**, phương thức/mã trạng thái HTTP, hợp đồng dữ liệu, cache, idempotency, xác thực/phân quyền, OpenAPI và kiểm thử với Java/Spring hoặc công nghệ tương đương.

Ba thành phần đóng vai trò riêng:

1. **Media type** cho biết **định dạng và mô hình xử lý cơ bản** của representation.
2. **Profile** bổ sung **quy ước hoặc ràng buộc chuyên biệt** trên một biểu diễn đã có media type, mà không thay đổi ý nghĩa nền tảng của media type đó.
3. **Link relation và action semantics** giúp client hiểu một liên kết/thao tác **có quan hệ gì** với resource hiện tại và làm thế nào để tiếp tục luồng nghiệp vụ.

**Mục tiêu bài học:** thiết kế và tiêu thụ biểu diễn hypermedia theo một hợp đồng rõ ràng, tránh gán ý nghĩa tùy tiện cho tên trường JSON hoặc suy đoán các URI.

## 2. Phân biệt resource, representation, media type, profile và affordance

Một **resource** là đối tượng được định danh bằng URI. Một resource có thể có nhiều **representation**: JSON thông thường, HAL JSON, XML hoặc HTML. Trong HTTP, client không nhất thiết nhận “bản thân resource”; client nhận một representation phù hợp với yêu cầu và chính sách của server.

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| **Resource** | Đối tượng logic có URI | **/api/orders/ord-913** |
| **Representation** | Dữ liệu được gửi mô tả trạng thái/khả năng của resource | Body JSON của đơn hàng |
| **Media type** | Quy tắc đọc và xử lý representation | **application/json**, **application/hal+json** |
| **Profile** | Quy ước bổ sung cho tập biểu diễn | **https://api.example.test/profiles/order-v1** |
| **Link** | URI tham chiếu đến resource liên quan | Liên kết tới customer hoặc collection |
| **Link relation** | Ý nghĩa mối quan hệ giữa nguồn và đích | **self**, **collection**, **next** hoặc URI relation riêng |
| **Affordance / action** | Khả năng tương tác cụ thể, có thể kèm method và input | “Hủy đơn” dùng **POST** với form/field phù hợp |
| **State transition** | Thay đổi trạng thái nghiệp vụ sau thao tác | **PENDING_PAYMENT → PAID** |

**Phân biệt quan trọng:** Link chỉ mang địa chỉ và quan hệ; **link không tự xác định phương thức POST/PATCH**, trừ khi định dạng hypermedia hoặc profile bổ sung một quy ước được công bố. Một URI có tên **/cancel** cũng không chứng minh được request phù hợp là DELETE, POST hay PATCH.

### Hypermedia như động cơ của trạng thái ứng dụng

Nguyên tắc **HATEOAS (Hypermedia as the Engine of Application State)** hướng client:

1. Bắt đầu từ một **entry point** đã biết.
2. Đọc representation và các liên kết/action hợp lệ.
3. Chọn bước tiếp theo theo **relation/action semantics**, thay vì tự đoán đường dẫn từ ID.
4. Sau mỗi phản hồi, **đọc trạng thái và affordance mới**, không mặc định trạng thái nghiệp vụ bất biến.

Điều này giúp server thay đổi một số cấu trúc URI hoặc luồng điều hướng mà client ít phụ thuộc hơn, **nếu client thực sự đi theo links và hiểu các relation ổn định**. Hypermedia không tự xóa nhu cầu versioning, schema và kiểm thử tương thích.

## 3. Media type là hợp đồng diễn giải cơ bản

HTTP dùng **Content-Type** trong response để chỉ ra media type của body và **Accept** trong request để diễn đạt những media type client chấp nhận.

~~~http
GET /api/orders/ord-913 HTTP/1.1
Host: api.example.test
Accept: application/hal+json, application/json;q=0.6

~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{"id":"ord-913","_links":{"self":{"href":"/api/orders/ord-913"}}}
~~~

Trong ví dụ, client ưu tiên **application/hal+json** và cũng chấp nhận **application/json** với chất lượng tương đối thấp hơn. Server chọn **application/hal+json** vì nó là một representation mà server hỗ trợ và client chấp nhận.

### Một số media type thường gặp

| Media type | Dạng dữ liệu | Client có thể kỳ vọng gì? |
|---|---|---|
| **application/json** | JSON tổng quát | Chỉ biết cú pháp JSON; tên **_links** không tự có ngữ nghĩa chuẩn hóa chung |
| **application/hal+json** | HAL (Hypertext Application Language) dùng JSON | Mô hình **_links**, **_embedded** và các quan hệ liên kết theo HAL |
| **application/vnd.siren+json** | Siren | Entity, links, actions và thông tin đầu vào theo mô hình Siren |
| **application/vnd.api+json** | JSON:API | Mô hình resource objects, relationships, links và quy tắc đặc tả JSON:API |
| **application/problem+json** | Problem Details | Biểu diễn vấn đề HTTP qua type/title/status/detail/instance và extension |
| **text/html** | HTML | Browser có quy tắc đọc liên kết, biểu mẫu và điều hướng HTML |

**JSON hợp lệ không có nghĩa JSON nào cũng tương thích với nhau về ngữ nghĩa.** HAL, Siren và JSON:API đều có cú pháp JSON, nhưng áp dụng **mô hình xử lý khác nhau**; không thể gửi body Siren rồi gắn **Content-Type: application/hal+json** và mong client hiểu đúng.

Một API không bắt buộc dùng tất cả định dạng trên. Chọn **một mô hình nhất quán, có tài liệu và thư viện phù hợp** thường giúp hệ thống dễ tích hợp hơn một tập các định dạng lẫn lộn.

### Suffix +json nói lên điều gì?

Hậu tố **+json** cho biết dữ liệu dùng cú pháp JSON và cho phép một số công cụ xử lý nội dung ở mức JSON chung. Tuy vậy, một client khai báo **Accept: application/json** **không tự động** đồng ý nhận mọi media type có hậu tố +json theo quy tắc so khớp Accept chuẩn. Nếu cần HAL, hãy khai báo rõ **application/hal+json** hoặc một media range phù hợp và được server hỗ trợ.

## 4. Ví dụ HAL: diễn giải liên kết từ biểu diễn

Giả sử server trả một đơn hàng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Link: <https://api.example.test/profiles/order-v1>; rel="profile"
Vary: Accept

{
  "id": "ord-913",
  "status": "PAID",
  "total": {
    "amount": 150000,
    "currency": "VND"
  },
  "_links": {
    "self": {
      "href": "/api/orders/ord-913"
    },
    "collection": {
      "href": "/api/orders"
    },
    "https://api.example.test/rels/customer": {
      "href": "/api/customers/cus-41"
    },
    "https://api.example.test/rels/invoice": {
      "href": "/api/orders/ord-913/invoice"
    }
  }
}
~~~

Đây là **ví dụ minh họa**; URI, số tiền và trạng thái chỉ phục vụ học tập.

### Client hiểu gì nhờ HAL?

- **_links.self**: liên kết đến chính resource đang được biểu diễn.
- **_links.collection**: liên kết đến collection chứa item, theo ngữ nghĩa relation đã được lựa chọn.
- Relation URI **/rels/customer**: mối liên hệ tới resource khách hàng; client hiểu chi tiết bằng tài liệu relation tương ứng.
- Relation URI **/rels/invoice**: mối quan hệ tới hóa đơn; server có thể thay đổi đích thực tế mà không bắt client tự ghép **/invoice**.
- **Link rel="profile"**: một profile gợi ý quy ước chuyên biệt của biểu diễn đơn hàng, không thay đổi media type HAL.

Client HAL phải hiểu **_links** theo HAL, không đọc **customerId** rồi mặc định tự nối path. Khi client được viết để hiểu relation URI ổn định, đích có thể chuyển sang **/api/billing/invoices/inv-72** mà client vẫn dùng đúng link.

### _embedded là tối ưu hóa biểu diễn, không xóa quan hệ

Một response HAL có thể nhúng một resource liên quan:

~~~json
{
  "id": "ord-913",
  "_links": {
    "self": {"href": "/api/orders/ord-913"},
    "https://api.example.test/rels/customer": {
      "href": "/api/customers/cus-41"
    }
  },
  "_embedded": {
    "https://api.example.test/rels/customer": {
      "id": "cus-41",
      "name": "Khách hàng ví dụ",
      "_links": {
        "self": {"href": "/api/customers/cus-41"}
      }
    }
  }
}
~~~

**_embedded** cho phép gửi kèm representation của một resource liên quan để giảm số request. Tuy nhiên:

- Resource nhúng vẫn có **quyền truy cập** và quy tắc cache riêng cần đánh giá.
- Client không được cho rằng mọi relation luôn có **_embedded**; server có thể chỉ gửi link.
- Nhúng quá sâu làm response lớn, tăng coupling và nguy cơ rò dữ liệu.
- Nếu resource liên quan thay đổi, bản nhúng có thể cũ so với một GET độc lập; hợp đồng cần nêu kỳ vọng nhất quán.

### Một giới hạn quan trọng của HAL

HAL biểu diễn **liên kết** rất rõ, nhưng **không cung cấp cùng một mô hình action/form hoàn chỉnh như Siren**. Một relation tên “cancel” trong HAL không tự cho biết client phải dùng **POST**, **PATCH** hay body gì. Nếu cần hướng dẫn hành động có method và input, chọn một định dạng có action semantics hoặc công bố một profile/quy ước khác đủ rõ và được client hỗ trợ.

## 5. Ví dụ Siren: khi biểu diễn cần mô tả hành động

Với quy trình thanh toán, client có thể cần biết **thao tác hiện khả dụng**, HTTP method, endpoint và trường đầu vào. Siren là một mô hình hypermedia dùng media type **application/vnd.siren+json**.

~~~http
HTTP/1.1 200 OK
Content-Type: application/vnd.siren+json

{
  "class": ["order"],
  "properties": {
    "id": "ord-913",
    "status": "PENDING_PAYMENT",
    "totalAmount": 150000
  },
  "links": [
    {
      "rel": ["self"],
      "href": "/api/orders/ord-913"
    }
  ],
  "actions": [
    {
      "name": "pay",
      "title": "Thanh toán đơn hàng",
      "method": "POST",
      "href": "/api/orders/ord-913/payments",
      "type": "application/json",
      "fields": [
        {"name": "paymentMethodId", "type": "text"}
      ]
    }
  ]
}
~~~

Trong ví dụ:

1. **properties** mô tả trạng thái đơn.
2. **links** mô tả liên kết điều hướng.
3. **actions** mô tả một tương tác: tên, method, URI, request media type và các trường.
4. **class** cung cấp phân loại theo mô hình Siren; ý nghĩa miền cụ thể vẫn cần hợp đồng.

**Lưu ý:** Trường **type** của action nói request body dự kiến có media type gì; ví dụ với **application/json**, server còn phải có quy ước riêng cách ánh xạ các **fields** thành JSON và validation cụ thể. Một Siren action không chứng minh sẵn rằng mọi giá trị đầu vào đều hợp lệ.

Khi đơn chuyển sang **PAID**, server có thể bỏ action **pay** và chỉ công bố liên kết xem hóa đơn. Client phải **tải trạng thái mới sau thao tác**, không giữ mãi action cũ như một quyền đã được cấp vĩnh viễn.

### Link, form và action không thay thế authorization

Dù biểu diễn có action **pay**, server vẫn phải:

- Xác thực người gọi, kiểm tra quyền trên đúng đơn hàng.
- Kiểm tra trạng thái đơn ở **thời điểm POST thực tế**.
- Xác minh payload, phương thức thanh toán, số tiền và các ràng buộc nghiệp vụ.
- Áp dụng idempotency key cho các thao tác có rủi ro nhân đôi thanh toán.
- Trả status/Problem Details phù hợp nếu action không còn hợp lệ.

**“Không có action trong body”** là tín hiệu UI không nên hiển thị nút, **không phải** bằng chứng thay thế kiểm soát truy cập; và **“có action trong body”** không phải giấy phép bỏ qua authorization.

## 6. Profile theo RFC 6906: quy ước bổ sung không đổi nền tảng media type

Một media type mô tả **mô hình biểu diễn chung**. Trong nhiều hệ thống, ta cần công bố thêm quy ước nghiệp vụ như:

- Cách hiểu các trường **status**, **total**, **amount**.
- Các loại link relation chuyên biệt như **invoice**, **refund**, **shipment**.
- Quy tắc những trường nào phải hiện diện cho một trạng thái.
- Ràng buộc hoặc kỳ vọng xử lý thêm đối với một tập biểu diễn.

**RFC 6906** định nghĩa link relation **profile** để liên kết một resource/representation với **một bộ ngữ nghĩa bổ sung**, ví dụ quy tắc, ràng buộc hoặc quy ước. Profile **không được thay thế hoặc làm trái ngữ nghĩa cơ bản của media type**.

### Cách quảng bá profile bằng Link header

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Link: <https://api.example.test/profiles/order-v1>; rel="profile"

{"id":"ord-913","status":"PAID","_links":{"self":{"href":"/api/orders/ord-913"}}}
~~~

Ở đây:

- **application/hal+json**: client xử lý body theo mô hình HAL.
- **rel="profile"**: biểu diễn liên kết tới profile **order-v1** có quy ước bổ sung.
- URI profile là **định danh cho một tập quy ước**; nếu URL trỏ tới tài liệu, client hoặc lập trình viên có thể đọc để hiểu chi tiết.
- Server không biến body thành một media type mới chỉ bằng cách thêm Link profile.

Một profile có thể được công bố qua **HTTP Link header**, hoặc qua **định dạng hypermedia có cơ chế link profile**. Cách biểu đạt phải tương thích định dạng đang dùng.

### Profile có phải schema không?

**Không nhất thiết.** Một profile có thể được viết bằng tài liệu con người đọc, JSON Schema, ALPS hoặc định dạng khác. Nó có thể chỉ cung cấp **ngữ nghĩa và quy tắc tương tác**, không chỉ cấu trúc dữ liệu. Một JSON Schema kiểm tra kiểu trường, nhưng không nhất thiết mô tả đầy đủ ý nghĩa “khi nào được hủy đơn” hay “liên kết refund có vai trò gì”.

| Thành phần | Trả lời câu hỏi | Có thay thế phần còn lại không? |
|---|---|---|
| **Media type** | Đọc representation này theo mô hình nào? | Không thay thế quy tắc miền |
| **Profile** | Có thêm ràng buộc/quy ước ngữ nghĩa nào? | Không đổi ngữ nghĩa nền của media type |
| **JSON Schema** | Cấu trúc/kiểu/constraint dữ liệu nào hợp lệ? | Không tự mô tả navigation hay workflow đầy đủ |
| **OpenAPI** | Endpoint, method, parameter, response, security và schema được mô tả ra sao? | Không tự biến một body tĩnh thành hypermedia |
| **Link relation** | Quan hệ giữa source và target là gì? | Không mặc định mô tả request method/action |
| **HTTP status/headers** | Kết quả request và điều kiện giao thức là gì? | Không được thay bằng dữ liệu trong profile |

### Profile không phải versioning miễn phí

Một URI profile **order-v2** có thể giúp mô tả hợp đồng mới, nhưng không làm một thay đổi phá vỡ tương thích trở nên an toàn cho client cũ. Nếu thay tên trường bắt buộc, đổi relation URI hoặc đổi ngữ nghĩa action, cần có **chiến lược versioning/negotiation/migration** thật sự.

### Tham số profile trong Content-Type/Accept

Một số media type **quy định riêng** việc sử dụng tham số **profile** (hoặc tham số khác như **ext**). Tuy nhiên, **RFC 6906 không bắt buộc mọi media type phải hỗ trợ tham số profile**, và không có quyền tự thêm **;profile=...** vào tất cả Content-Type để mong mọi client/server hiểu.

Nếu định dạng đang dùng hỗ trợ cú pháp tham số profile, phải tuân theo **đặc tả của định dạng đó** về media type parameters, quoting, normalization và thương lượng. Một cách phổ quát và dễ hiểu hơn khi profile là metadata bổ sung là dùng **Link rel="profile"**.

## 7. Quy ước diễn giải biểu diễn (representation processing model)

Một client có thể hiểu JSON ở **nhiều tầng**, và phải phân biệt chúng:

~~~mermaid
flowchart TD
    R["Nhận HTTP response"] --> S["1. Đọc status + headers"]
    S --> T["2. Chọn parser theo Content-Type"]
    T --> M["3. Áp dụng media type semantics<br/>HAL / Siren / JSON:API / Problem Details"]
    M --> P["4. Nhận profile và relation semantics<br/>nếu client hỗ trợ"]
    P --> A["5. Xác định liên kết/action phù hợp"]
    A --> C["6. Gửi request tiếp theo theo method & contract"]
    C --> R
~~~

### Tầng 1 — HTTP semantics

Client trước tiên phải xử lý **HTTP status**: 200 nghĩa là thành công; 401/403 liên quan xác thực/quyền; 404 không tìm thấy; 409 xung đột; 429 vượt hạn mức; 5xx báo lỗi phía server. Một response **204 No Content** không có body để phân tích hypermedia. Một response **304 Not Modified** là kết quả kiểm tra điều kiện cache, không phải representation mới để đọc links.

### Tầng 2 — Media type

Client đọc **Content-Type** và dùng parser/handler phù hợp. Với **application/hal+json**, nó hiểu **_links** và **_embedded**. Với **application/vnd.siren+json**, nó hiểu **links** và **actions**. Với **application/problem+json**, nó chuyển sang xử lý lỗi theo problem type và status.

### Tầng 3 — Profile

Client có thể sử dụng profile để bổ sung quy ước miền, nhưng profile **không được khiến parser HAL diễn giải sai _links hoặc _embedded**. Client không hỗ trợ profile có thể vẫn đọc các thành phần nền của HAL, nhưng có thể không biết ý nghĩa các trường hoặc hành động chuyên biệt.

### Tầng 4 — Relation/action

Client tìm relation mà mình hiểu, ví dụ **self**, **next**, hoặc **https://api.example.test/rels/invoice**. Nó không nên:

- Dựa vào vị trí phần tử trong mảng links thay vì relation.
- Ghép URI bằng cách thêm **/invoice** nếu đã có relation **invoice**.
- Dùng **POST** chỉ vì URI có đuôi **/pay**.
- Gọi một action không còn được quảng bá mà không kiểm tra điều kiện hiện hành.

Client cần xử lý **thiếu relation/action** như một trạng thái có thể xảy ra, không phải lập tức coi server lỗi; tùy contract, thiếu link có thể là vì trạng thái hiện tại, quyền, cấu hình hoặc khả năng tính toán khác nhau.

## 8. Link relation: quan hệ chuẩn và quan hệ miền riêng

HTTP Web Linking (RFC 8288) cung cấp khái niệm **link relation**: liên kết không chỉ có một URI đích mà còn có **loại quan hệ** giữa ngữ cảnh nguồn và đích.

~~~http
HTTP/1.1 200 OK
Link: </api/orders/ord-913>; rel="self"
Link: </api/orders>; rel="collection"
Link: <https://api.example.test/profiles/order-v1>; rel="profile"
~~~

### Chuẩn hóa relation để client hiểu

- **Relation được đăng ký** như **self**, **next**, **prev**, **profile** có ý nghĩa được mô tả ngoài API cụ thể.
- **Relation do ứng dụng định nghĩa** nên dùng **URI riêng ổn định** hoặc cú pháp được format hỗ trợ để tránh đụng tên.
- URI relation **định danh ý nghĩa**, không nhất thiết là endpoint được gọi mỗi lần; tài liệu relation thường có ích.
- Thay đổi **đích href** khác với thay đổi **ngữ nghĩa relation**. Có thể chuyển href mà vẫn giữ relation khi ý nghĩa không đổi.

Ví dụ:

~~~json
{
  "_links": {
    "self": {"href": "/api/orders/ord-913"},
    "https://api.example.test/rels/invoice": {
      "href": "/api/billing/invoices/inv-72"
    }
  }
}
~~~

Client hiểu relation **invoice** mà không cần biết trước URI hóa đơn thuộc service/bounded context nào.

### URI tương đối và URI tuyệt đối

Link có thể sử dụng **relative URI**, được phân giải dựa trên URI của representation hoặc ngữ cảnh phù hợp, hoặc **absolute URI**. Dù dùng cách nào, client cần:

1. Phân giải theo chuẩn URI, không nối chuỗi tùy ý.
2. Kiểm tra scheme và host trước khi **tự động gửi credentials** sang đích.
3. Tôn trọng chính sách chuyển hướng, phân quyền, CORS và rate limit của endpoint mới.
4. Không giả định mọi liên kết là **cùng origin** hoặc **cùng vùng tin cậy**.

Server không nên tạo absolute href từ **Host/X-Forwarded-Host** do client không tin cậy để tránh host poisoning. Dùng base URL đáng tin cậy hoặc cấu hình trusted proxy chính xác.

### URI template và dữ liệu đầu vào

Một representation có thể quảng bá **URI template** khi media type hoặc profile hỗ trợ. Ví dụ một relation tìm kiếm có template:

~~~json
{
  "_links": {
    "search": {
      "href": "/api/orders{?status,limit}",
      "templated": true
    }
  }
}
~~~

Mẫu này phù hợp với cơ chế URI template như RFC 6570, nhưng **client phải biết mô hình template được format sử dụng**, escape query values đúng cách và vẫn kiểm tra tài liệu parameter. Chỉ thấy dấu ngoặc nhọn không đủ để tự suy rằng bất kỳ chuỗi nào cũng là URI template hợp lệ.

## 9. Biểu diễn điều hướng theo trạng thái nghiệp vụ

Hypermedia đặc biệt hữu ích ở các workflow có hành động thay đổi theo trạng thái. Ví dụ đơn hàng:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING_PAYMENT: submit
    PENDING_PAYMENT --> PAID: pay
    PENDING_PAYMENT --> CANCELLED: cancel
    PAID --> SHIPPED: ship
    PAID --> CANCELLED: cancel theo chính sách
    SHIPPED --> DELIVERED: confirm delivery
    DELIVERED --> [*]
    CANCELLED --> [*]
~~~

Các chuyển trạng thái trên là **ví dụ nghiệp vụ**, không phải quy tắc chung của REST hoặc mua bán. Chính sách thực tế có thể cho hoàn tiền hoặc hủy theo điều kiện khác.

Với một API dùng Siren:

- Ở **DRAFT**, có thể có action **submit**.
- Ở **PENDING_PAYMENT**, có thể có action **pay** và **cancel**.
- Ở **PAID**, có thể không còn **pay**; có link **invoice** và hành động phù hợp với vai trò.
- Ở **SHIPPED**, có thể có link **shipment tracking**, nhưng action hủy không còn.

Điểm mạnh không phải server sẽ không bao giờ trả lỗi. Giữa lúc client đọc trạng thái và lúc POST hành động, quyền và trạng thái có thể đổi. Server vẫn phải validate và trả **409 Conflict**, **412 Precondition Failed**, **403 Forbidden** hoặc lỗi khác đúng tình huống.

### Tránh race condition bằng ETag/If-Match

Nếu một action chỉnh sửa tài nguyên theo phiên bản, API có thể dùng **ETag** trong response và yêu cầu **If-Match** ở request thay đổi:

~~~http
GET /api/orders/ord-913 HTTP/1.1
Host: api.example.test
Accept: application/vnd.siren+json

HTTP/1.1 200 OK
Content-Type: application/vnd.siren+json
ETag: "order-913-v8"

{"properties":{"id":"ord-913","status":"PENDING_PAYMENT"}}
~~~

~~~http
POST /api/orders/ord-913/payments HTTP/1.1
Host: api.example.test
If-Match: "order-913-v8"
Idempotency-Key: pay-ord-913-attempt-1
Content-Type: application/json

{"paymentMethodId":"pm-7"}
~~~

Đây là một **hợp đồng ứng dụng minh họa**. Việc dùng **If-Match** với resource/action endpoint nào phải được định nghĩa rõ; HTTP precondition áp dụng cho target resource của request và không tự so sánh ETag của một resource khác. Nếu muốn kiểm tra ETag của **/api/orders/ord-913** khi POST đến **/payments**, server cần **hợp đồng riêng** để ràng buộc phiên bản đơn, ví dụ truyền **expectedOrderVersion** trong payload hoặc sử dụng endpoint cập nhật đúng target.

Đối với thanh toán, **idempotency** và đối soát vẫn cần có dù sử dụng ETag, vì trạng thái mạng có thể không rõ sau side effect.

## 10. Media type negotiation và profile discovery qua HTTP

### Accept và Content-Type không phải một

**Accept** là yêu cầu client chấp nhận những representation nào; **Content-Type** nói body thực tế thuộc loại nào.

~~~http
GET /api/orders/ord-913 HTTP/1.1
Host: api.example.test
Accept: application/hal+json;q=1.0, application/json;q=0.5

~~~

Server có thể chọn:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Vary: Accept
Link: <https://api.example.test/profiles/order-v1>; rel="profile"

{"id":"ord-913","_links":{"self":{"href":"/api/orders/ord-913"}}}
~~~

Nếu server có **hai representation** cho cùng resource, **Vary: Accept** giúp cache biết nội dung có thể thay đổi theo Accept. Nếu bản địa hóa theo **Accept-Language**, cân nhắc **Vary: Accept, Accept-Language** và đặt **Content-Language** phù hợp.

### Ngữ nghĩa của q-value

| Accept | Cách hiểu |
|---|---|
| **application/hal+json** | Client chấp nhận HAL |
| **application/hal+json, application/json;q=0.5** | Ưu tiên HAL so với JSON tổng quát |
| **application/hal+json;q=0** | Không chấp nhận HAL theo biểu thức đó |
| `application/*` | Chấp nhận các media subtype thuộc nhóm application |
| `*/*` | Có thể chấp nhận mọi media type |
| **application/json** | Không tự đồng nghĩa chấp nhận HAL/Siren |
| Không có Accept | Client không giới hạn response media type bằng header này |

**Mã 406 Not Acceptable:** Nếu server không có representation phù hợp với Accept và không lựa chọn gửi representation mặc định, có thể trả **406**. Cần công bố policy và kiểm thử; đừng luôn đẩy HAL cho client chỉ hỗ trợ JSON tổng quát.

**Mã 415 Unsupported Media Type:** Liên quan **Content-Type của request body** không được endpoint xử lý, không phải lựa chọn định dạng response. Ví dụ action Siren yêu cầu **application/json** nhưng client gửi **text/plain**, server có thể trả 415.

### Thương lượng profile có thể là chính sách riêng

Một số hệ thống cho client đề nghị profile cụ thể, nhưng **không có cơ chế chung trong RFC 6906 buộc mọi API phải hiểu một header tùy ý như Accept-Profile**. Cần phân biệt:

- **Link rel="profile"** trong response để khám phá profile đang được áp dụng.
- **Media type parameter profile** chỉ khi media type cụ thể cho phép và định nghĩa ngữ nghĩa.
- **Custom header/query hoặc API version** nếu API tự thiết kế cơ chế chọn profile; phải công bố và không xung đột HTTP caching.

Nếu server chọn representation khác nhau theo một custom request header, phải xem xét **Vary** và cấu hình cache; nếu profile chỉ được quảng bá như metadata đi kèm, không cần tự tạo cơ chế negotiation phức tạp.

## 11. Media type, profile và phiên bản API

Một hệ thống thường thay đổi theo thời gian. Vấn đề không chỉ là “version bao nhiêu” mà là **thay đổi có làm client hiểu sai không?**

| Thay đổi | Thường có an toàn tương thích không? | Cần kiểm tra |
|---|---|---|
| Thêm một link relation tùy chọn | Thường có, nếu client bỏ qua quan hệ chưa biết | Client có parser linh hoạt, không lỗi khi có trường mới |
| Thay href nhưng giữ đúng relation semantics | Có thể an toàn với hypermedia client | Client có thực sự follow link thay vì ghép URI? |
| Bỏ một action vì trạng thái resource thay đổi | Là hành vi runtime bình thường nếu đã mô tả | Client có xử lý thiếu action không? |
| Đổi tên/trường bắt buộc | Có thể breaking | Schema, SDK, khả năng fallback |
| Đổi ý nghĩa cùng một relation URI | Thường breaking về ngữ nghĩa | Relation docs, profile, contract test |
| Đổi media type từ HAL sang Siren | Breaking với client chỉ hiểu HAL | Accept negotiation, giai đoạn hỗ trợ song song |
| Thêm profile ràng buộc chặt hơn | Có thể breaking với client dùng profile đó | Cam kết của profile và phân loại clients |
| Thêm enum status mới | Tùy client | Client có chiến lược xử lý trạng thái lạ không? |

### Ghi lại quyết định thiết kế

Một hợp đồng hypermedia tốt cần nêu:

1. **Media type mặc định** và những media type được Accept negotiation.
2. **Profile URI** với phiên bản/quy ước được hỗ trợ.
3. **Relation registry**: tên relation, URI, ý nghĩa và target resource.
4. **Action semantics**: method, request media type, payload fields, side effect, idempotency.
5. **Trạng thái và điều kiện khả dụng** của links/actions.
6. **Mã trạng thái và Problem Details** khi client gọi một affordance không còn hợp lệ.
7. **Security, cache và versioning** của biểu diễn.

Đặt **v=2** vào URL, media type, profile hoặc header không giải quyết vấn đề nếu chưa xác định **điều gì thay đổi và client lựa chọn phiên bản ra sao**.

## 12. Triển khai minh họa bằng Spring MVC

Ví dụ dưới đây dùng **Spring Framework 6 / Spring Boot 3** và tạo một response HAL tối giản mà không yêu cầu thêm thư viện hypermedia. Trong dự án lớn, có thể cân nhắc **Spring HATEOAS** để hỗ trợ tạo links, nhưng phải đọc chính xác contract và version thư viện đang dùng.

### Endpoint trả HAL và profile link

~~~java
import java.util.Map;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderHypermediaController {

    private static final String BASE = "https://api.example.test";
    private static final String ORDER_PROFILE =
            "https://api.example.test/profiles/order-v1";

    @GetMapping(
            path = "/api/orders/{id}",
            produces = "application/hal+json")
    ResponseEntity<Map<String, Object>> getOrder(@PathVariable long id) {
        // Dữ liệu giả lập: thực tế cần query + authorization theo principal.
        Map<String, Object> body = Map.of(
                "id", id,
                "status", "PAID",
                "_links", Map.of(
                        "self", Map.of(
                                "href", "/api/orders/" + id),
                        "collection", Map.of(
                                "href", "/api/orders")));

        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType("application/hal+json"))
                .header(HttpHeaders.LINK,
                        "<" + ORDER_PROFILE + ">; rel=\"profile\"")
                .header(HttpHeaders.VARY, "Accept")
                .body(body);
    }
}
~~~

**Giới hạn ví dụ:** Controller sử dụng một response hard-coded và chưa tìm đơn, kiểm tra quyền hoặc điều kiện trạng thái. Nó **không phải ứng dụng production hoàn chỉnh**, nhưng minh họa đúng:

- **produces = application/hal+json**: nội dung của endpoint có media type HAL, không phải application/json tùy ý.
- **Content-Type** đi cùng response body.
- **Link rel="profile"** quảng bá quy ước Order v1.
- **Vary: Accept** khi hệ thống có chọn representation theo Accept.
- **_links** được đưa vào body theo định dạng HAL.

Nếu endpoint chỉ phục vụ HAL và client gửi **Accept: application/xml**, Spring MVC có thể trả **406 Not Acceptable** theo cấu hình negotiation. Lỗi ấy có thể đi qua exception handler riêng; phải kiểm thử phản hồi cuối qua cả security và proxy. Nếu cùng URI có handler JSON thông thường khác, cần xác định lựa chọn theo **Accept** không mơ hồ.

### Không tự dùng Host chưa tin cậy

Ở ví dụ, **BASE** chưa được dùng; nếu chuyển từ relative URI sang absolute URI, nên dùng **base URL từ cấu hình tin cậy** hoặc forwarded headers chỉ sau proxy được tin cậy. Không tự ghép **Host** từ request để tạo link tới miền không kiểm soát.

### Thêm action cần định dạng phù hợp

Nếu cần mô tả hành động **pay/cancel** kèm method/input, hãy cân nhắc biểu diễn Siren hoặc một đặc tả action rõ ràng. Không thêm một trường **_actions** tùy tiện vào HAL rồi mặc định mọi HAL client sẽ hiểu; nếu chọn extension riêng, phải mô tả profile và khả năng tương thích với client cơ bản.

## 13. Mô tả hợp đồng trong OpenAPI 3.1

OpenAPI giúp mô tả **endpoint, media type, schema, header và response codes**. Nó bổ trợ hypermedia; OpenAPI không tự biến một JSON body thành một hypermedia representation khi server không thực sự gửi các links/actions theo đúng media type.

~~~yaml
openapi: 3.1.0
info:
  title: Orders Hypermedia API
  version: 1.0.0
paths:
  /api/orders/{id}:
    get:
      summary: Đọc đơn hàng dưới dạng HAL
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: integer
            format: int64
      responses:
        '200':
          description: Biểu diễn HAL của một đơn hàng
          headers:
            Link:
              description: >
                Có thể chứa rel="profile" tới quy ước Order v1.
              schema:
                type: string
              example: >
                <https://api.example.test/profiles/order-v1>; rel="profile"
            Vary:
              description: Response có thể thay đổi theo Accept
              schema:
                type: string
              example: Accept
          content:
            application/hal+json:
              schema:
                $ref: '#/components/schemas/OrderHal'
        '401':
          description: Chưa xác thực
        '403':
          description: Không có quyền
        '404':
          description: Không tìm thấy đơn
        '406':
          description: Không có representation phù hợp Accept
components:
  schemas:
    HalLink:
      type: object
      required: [href]
      properties:
        href:
          type: string
    OrderHal:
      type: object
      required: [id, status, _links]
      properties:
        id:
          type: integer
          format: int64
        status:
          type: string
        _links:
          type: object
          required: [self]
          properties:
            self:
              $ref: '#/components/schemas/HalLink'
            collection:
              $ref: '#/components/schemas/HalLink'
~~~

**Lưu ý:** JSON Schema trong ví dụ là **tập con hợp đồng HAL** của API: nó mô tả relation **self/collection**, chưa mô tả toàn bộ khả năng mở rộng relation tùy chọn hoặc kiểu link array. Khi cần hỗ trợ các relation URI động, cần schema phù hợp với dạng HAL và giới hạn mà API chọn; không áp dụng schema rút gọn rồi cho rằng nó mô tả tất cả HAL.

### OpenAPI Links Object không đồng nhất với HAL _links

OpenAPI có cơ chế **Links Object** để mô tả quan hệ giữa response và operation được gọi tiếp; đây là **thông tin trong tài liệu OpenAPI**, không phải một trường **_links** tự động xuất hiện trong HTTP response.

Muốn hỗ trợ HATEOAS ở runtime, server phải **phát links/actions thật trong representation**, và client phải đọc chúng theo media type/profile đã công bố.

## 14. Bảo mật, caching và vận hành biểu diễn hypermedia

### An toàn khi client đi theo links

Hypermedia khuyến khích client đi theo link do server cấp, nhưng không có nghĩa **mọi URL trả về đều tin cậy tuyệt đối**:

- SDK chỉ tự gửi **Authorization/cookie/secret** tới origin được phép.
- Không lấy một relation URL từ server ngoài danh sách tin cậy rồi tải dữ liệu nội bộ qua backend (nguy cơ SSRF).
- Kiểm tra scheme **https** nếu chính sách yêu cầu; xử lý redirect an toàn.
- Không coi link/action có mặt là **quyền truy cập** hay bảo đảm trạng thái không đổi.
- Không đưa access token hoặc dữ liệu nhạy cảm vào query string của href.
- Khi liên kết dẫn tới third-party, áp dụng chính sách sandbox/allowlist hoặc yêu cầu xác nhận tùy loại client.

### Cache theo representation variant

Một URI có thể trả HAL hoặc JSON thường theo **Accept**. Cache cần phân biệt các biến thể:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Vary: Accept, Accept-Language
ETag: "order-913-hal-vi-v8"
Cache-Control: private, max-age=30
~~~

Đây là ví dụ minh họa, **không khuyến nghị cache đơn hàng nhạy cảm 30 giây trong mọi hệ thống**. Với dữ liệu chứa thông tin cá nhân hoặc thanh toán, có thể chọn **Cache-Control: no-store** và chỉ bật cache khi đã đánh giá quyền riêng tư, nội dung thay đổi và mô hình truy cập.

**ETag** xác thực một representation/variant cụ thể theo cách server chọn. Không dùng cùng ETag một cách cẩu thả cho body HAL và JSON thường khi nội dung/bytes khác nhau, đặc biệt với **strong validators**. Đối với link phụ thuộc trạng thái, việc cache có thể làm UI hiển thị một action đã hết hiệu lực; request thật vẫn phải kiểm tra điều kiện và trả lỗi phù hợp.

### CORS và Link header

Nếu frontend từ origin khác cần đọc **Link rel="profile"** trong response, có thể phải expose header:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Expose-Headers: Link, ETag
Vary: Origin, Accept
~~~

Policy CORS chỉ kiểm soát khả năng đọc cross-origin của JavaScript trong trình duyệt; **không thay authorization**. Nếu response phụ thuộc ngôn ngữ, Vary phải phản ánh chính xác các request headers thực sự được dùng để chọn representation.

### Quan sát hành vi

Theo dõi tối thiểu:

- **Response media type** theo endpoint và trạng thái HTTP.
- **Accept negotiation failures** (406) và **request body media type errors** (415).
- Số lượng client dùng **profile version** cũ nếu có cơ chế phân biệt.
- Tỷ lệ lỗi của **relation/action** quan trọng, 409/412 khi trạng thái thay đổi.
- Phản hồi 401/403/429/5xx theo gateway/controller và request ID.
- Số lượng liên kết có host/scheme bất thường, redirect không mong đợi.
- Cache hit/miss, ETag/304 theo representation variant và rò rỉ dữ liệu nếu có.

## 15. Kiểm thử media type, profile và khả năng đi theo liên kết

### 15.1. Dùng curl xác minh HTTP contract

~~~bash
curl -i \
  -H 'Accept: application/hal+json' \
  'https://api.example.test/api/orders/913'

curl -i \
  -H 'Accept: application/json' \
  'https://api.example.test/api/orders/913'

curl -i \
  -H 'Accept: application/xml' \
  'https://api.example.test/api/orders/913'
~~~

Tên miền và ID là ví dụ. Nếu endpoint chỉ có HAL, request đầu nên nhận **application/hal+json** nếu đã được xác thực/có quyền. Request thứ hai hoặc ba phải theo chính sách Accept negotiation thực tế — có thể nhận **406** nếu không có representation phù hợp và server không dùng mặc định — chứ không nên âm thầm gắn sai Content-Type.

### 15.2. MockMvc kiểm tra HAL và profile

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderHypermediaContractTest {

    @Autowired MockMvc mvc;

    @Test
    void orderUsesHalAndAdvertisesProfile() throws Exception {
        mvc.perform(get("/api/orders/913")
                  .accept("application/hal+json"))
           .andExpect(status().isOk())
           .andExpect(content().contentTypeCompatibleWith(
                   "application/hal+json"))
           .andExpect(jsonPath("$._links.self.href")
                   .value("/api/orders/913"))
           .andExpect(header().string("Link",
                   "<https://api.example.test/profiles/order-v1>; rel=\"profile\""));
    }
}
~~~

Test giả định có controller tương ứng và request đã vượt qua authentication/authorization. Nếu Spring Security đang bật, phải dùng cấu hình test/mock principal phù hợp. Đây là **khung contract test minh họa**, không phải test đã chạy trong khi viết tài liệu.

### 15.3. Ma trận kiểm thử quan trọng

| Tình huống | Điều phải xác minh |
|---|---|
| Client Accept HAL | Content-Type đúng HAL; _links hợp schema |
| Client Accept JSON thường | Server phục vụ đúng variant hoặc 406 theo policy |
| Client q=0 cho HAL | Không chọn HAL trái điều kiện Accept |
| Header profile | URI hợp lệ, ổn định; không làm sai media type semantics |
| Trả profile phiên bản mới | Client cũ xử lý được hoặc có migration policy |
| HAL links có relation URI | Client có thể tìm relation mà không phụ thuộc href path |
| HAL _embedded có/không | Client vẫn xử lý link và dữ liệu quyền hạn đúng |
| Siren action chỉ hiện ở trạng thái phù hợp | Client không giữ action cũ vô hạn |
| Action trả xung đột | 409/412/403 theo state/permission thực tế |
| Client đi theo href chuyển host | Không làm rò token/cookie, tuân thủ origin allowlist |
| Link header khác body link | Contract test phát hiện và sửa nguồn tạo link |
| 406/415 và lỗi JSON | Không nhầm response Accept với request Content-Type |
| ETag theo variant | Không tái sử dụng bản HAL cho request cần JSON thường |
| CORS đọc Link header | Frontend được phép đọc header khi được policy cho phép |
| Proxy/gateway đổi host | Không phát URL tới domain chưa tin cậy |
| Client gặp relation lạ | Bỏ qua/hiển thị theo fallback, không crash |

### 15.4. Kiểm thử theo hành vi, không chỉ snapshot JSON

Một snapshot test so sánh nguyên body JSON có thể phát hiện thay đổi shape, nhưng không chứng minh hypermedia:

1. Lấy một representation từ entry point.
2. Chọn relation được hỗ trợ dựa trên ngữ nghĩa, **không ghép URL bằng ID**.
3. Follow href hoặc thực thi action theo format.
4. Kiểm tra HTTP status, biến thể media type, state mới và quyền.
5. Thử một state/action không còn hợp lệ để chứng minh server từ chối đúng.
6. Thử thiếu relation, relation lạ, client cũ và profile mới để chứng minh fallback.

**Bài test quan trọng:** Đổi URI đích của relation **invoice** trên server nhưng giữ relation và contract; một client hypermedia đúng vẫn có thể tìm hóa đơn qua link mới, trong khi client hard-code **/api/orders/{id}/invoice** sẽ lỗi.

## 16. Bài tập tình huống: API đặt chỗ sự kiện

Một dịch vụ bán vé cung cấp resource:

- **/api/reservations/{id}**: trạng thái giữ chỗ.
- **/api/reservations/{id}/payments**: tạo một yêu cầu thanh toán theo hợp đồng.
- **/api/tickets/{id}**: xem vé đã phát hành.
- **/api/events/{id}**: xem sự kiện.

Trạng thái có thể là **HELD**, **PAID**, **EXPIRED**. Khi **HELD**, người dùng được thanh toán trước thời hạn; khi **PAID**, có liên kết tới vé; khi **EXPIRED**, không còn action thanh toán. Frontend muốn dùng HAL để duyệt các tài nguyên, nhưng form thanh toán cần method/body rõ ràng.

### Câu hỏi

1. Nêu **media type** phù hợp để client đọc các liên kết và **một cách biểu diễn action** có method/body rõ.
2. Viết response **HAL** cho reservation HELD gồm self, event và một relation URI tới thông tin thanh toán.
3. Viết response **Siren** hoặc mô tả action tương đương có **method=POST**, href, type và trường **paymentMethodId**.
4. Đề xuất URI profile **reservation-v1**, mô tả ít nhất **bốn quy ước** profile cần công bố.
5. Phân biệt **Content-Type: application/hal+json** với **Link rel="profile"** và với **OpenAPI**.
6. Trình bày hành vi client nếu nó gọi action thanh toán sau khi reservation vừa chuyển sang **EXPIRED**.
7. Nếu client gửi **Accept: application/json** nhưng server chỉ có HAL, server nên xử lý thế nào theo chính sách negotiation đã chọn?
8. Thiết kế **sáu test** cho media type, profile, links, action, quyền và tính tương thích.

### Gợi ý đáp án

**Câu 1:** HAL thích hợp để đọc các relation qua **_links**. Nếu cần diễn đạt action với method và input, Siren là một lựa chọn; cũng có thể xây hợp đồng riêng rõ ràng khi client hỗ trợ, nhưng không được giả định HAL tự có action semantics.

**Câu 2:** Ví dụ:

~~~json
{
  "id": "res-19",
  "status": "HELD",
  "_links": {
    "self": {"href": "/api/reservations/res-19"},
    "https://api.example.test/rels/event": {
      "href": "/api/events/evt-4"
    },
    "https://api.example.test/rels/payment-info": {
      "href": "/api/reservations/res-19/payment-info"
    }
  }
}
~~~

**Câu 3:** Ví dụ Siren:

~~~json
{
  "class": ["reservation"],
  "properties": {"id": "res-19", "status": "HELD"},
  "links": [
    {"rel": ["self"], "href": "/api/reservations/res-19"}
  ],
  "actions": [
    {
      "name": "pay",
      "title": "Thanh toán giữ chỗ",
      "method": "POST",
      "href": "/api/reservations/res-19/payments",
      "type": "application/json",
      "fields": [
        {"name": "paymentMethodId", "type": "text"}
      ]
    }
  ]
}
~~~

**Câu 4:** Profile **https://api.example.test/profiles/reservation-v1** có thể mô tả trạng thái hợp lệ, đơn vị thời gian giữ chỗ, ý nghĩa relation **event/payment-info/ticket**, khi nào action thanh toán xuất hiện và quy tắc hợp đồng dữ liệu. Nó không được đổi ngữ nghĩa nền của HAL/Siren. Nếu profile chỉ hỗ trợ HAL hoặc Siren, tài liệu phải nói rõ áp dụng cho định dạng nào.

**Câu 5:** Media type nói **cách parse representation**; profile nói **quy ước bổ sung**; OpenAPI mô tả **hợp đồng các endpoint và schema**, không tự bảo đảm links/action xuất hiện trong response runtime.

**Câu 6:** API phải kiểm tra trạng thái mới và quyền; có thể trả **409 Conflict** hoặc mã lỗi theo hợp đồng, không cho thanh toán chỉ vì client thấy action ở response cũ. Với side effect thanh toán, phải có idempotency, đối soát và chính sách giữ chỗ nhất quán.

**Câu 7:** **application/json** không mặc nhiên bao gồm HAL. Có thể cung cấp representation JSON thường nếu server hỗ trợ; nếu không và server không dùng fallback trái Accept, **406 Not Acceptable** là hành vi có thể chọn. Tài liệu và contract test cần nhất quán.

**Câu 8:** Kiểm tra Accept HAL/Siren, Link profile, relation URI, action HELD/EXPIRED, 403 khi thiếu quyền, response 409 khi race, CORS/Link header, và việc client không làm rò credentials khi follow link.

## 17. Những phản mẫu thường gặp

| Phản mẫu | Hậu quả | Cách cải thiện |
|---|---|---|
| Chỉ dùng **application/json** nhưng coi mọi trường **_links** là HAL chuẩn | Client không biết chuẩn xử lý | Quảng bá đúng media type nếu thực sự dùng HAL |
| Gửi body HAL với **Content-Type: application/vnd.siren+json** | Parser hiểu sai representation | Media type phải khớp body thực |
| Đồng nhất **profile** với **schema** | Bỏ qua relation/action semantics | Tài liệu hóa quy ước, ràng buộc và hành vi |
| Coi **Link rel=profile** là yêu cầu client đổi parser | Sai vai trò profile | Giữ parser theo Content-Type, áp dụng profile bổ sung |
| Tự thêm tham số **profile** vào mọi media type | Client/server hiểu khác nhau | Chỉ dùng tham số khi media type định nghĩa; có thể dùng Link rel=profile |
| Chỉ dựa trên href có đuôi **/cancel** để gửi POST | URI không tự nói method | Dùng action semantics hoặc contract rõ ràng |
| Cố định href từ ID thay vì đi theo rel | Server khó thay URI | Client tìm relation ổn định rồi follow href |
| Quảng bá action nhưng bỏ authorization lúc gọi | Bypass quyền, race condition | Kiểm tra trạng thái/quyền mỗi request |
| Dùng cùng ETag cho mọi variant bất kể bytes | Cache/conditional request có thể sai | Xây validators theo representation đúng nghĩa |
| Trả HAL cho **Accept: application/json** mà không có policy | Content negotiation không nhất quán | Hỗ trợ variant đúng hoặc 406 khi phù hợp |
| Link từ Host không đáng tin | Host injection và lộ token khi client follow | Chỉ dùng base URL/proxy tin cậy |
| Client chuyển Authorization sang mọi href | Nguy cơ rò credential/SSRF | Kiểm soát origin/scheme/redirect |
| Không xử lý relation/action vắng mặt | Client crash khi state thay đổi | Fallback theo capability hiện có |
| Chỉ test JSON shape, không test traversal | Không phát hiện link sai và action lỗi | Contract test hành vi đi theo link |

## 18. Checklist thiết kế một hypermedia contract

- [ ] Resource và biểu diễn được định danh rõ; server không gán hành động cho tên path một cách mơ hồ.
- [ ] **Content-Type** phản ánh đúng media type của body; **Accept** được xử lý nhất quán.
- [ ] Nếu dùng HAL/Siren/JSON:API, body tuân theo mô hình của định dạng đã chọn.
- [ ] Profile được quảng bá qua cơ chế phù hợp (như **Link rel="profile"**) và không thay đổi semantics nền của media type.
- [ ] Profile URI ổn định, có tài liệu giải thích trường, relation, ràng buộc và thay đổi tương thích.
- [ ] Các **link relations** chuẩn hoặc URI relation riêng có ngữ nghĩa rõ ràng; href có thể thay đổi mà client vẫn định vị được.
- [ ] Nếu có action, mô tả **method, request media type, dữ liệu đầu vào và điều kiện khả dụng** đúng định dạng/hợp đồng.
- [ ] Tình huống **thiếu relation/action** theo trạng thái hoặc quyền đã được client xử lý.
- [ ] Request thay đổi dữ liệu vẫn được xác thực/phân quyền, kiểm tra trạng thái, điều kiện cập nhật và idempotency khi cần.
- [ ] Không dùng profile để thay HTTP status, Allow, ETag, If-Match, Retry-After hoặc Problem Details.
- [ ] **406/415**, Vary, caching, ETag, CORS và localization được kiểm tra theo các representation variants.
- [ ] Hypermedia links không chứa token/secret; client không chuyển credentials sang origin ngoài allowlist.
- [ ] OpenAPI, schema, runtime media type/links/actions và tài liệu profile đồng nhất.
- [ ] Có test từ **entry point → relation/action → request tiếp theo → state mới**, không chỉ snapshot JSON.
- [ ] Có chiến lược versioning, migration và quan sát client cũ khi thay media type/profile/relation.

**Điểm cần nhớ:** **Media type** nói client phải **đọc và xử lý representation theo mô hình nào**; **profile** mô tả **những quy ước bổ sung** mà không thay semantics nền; **link relation/action** biến dữ liệu thành các bước điều hướng hoặc tương tác có ý nghĩa. Dùng ba lớp này nhất quán giúp REST API bớt phụ thuộc vào URI hard-code, vẫn giữ đúng ngữ nghĩa HTTP, quyền truy cập và khả năng tiến hóa hợp đồng.

### Tài liệu nền để tra cứu

- **RFC 9110 — HTTP Semantics:** Content-Type, Accept, status code, conditional requests và content negotiation.
- **RFC 8288 — Web Linking:** Link header và cách mô tả link relations.
- **RFC 6906 — The 'profile' Link Relation Type:** profile là ngữ nghĩa bổ sung cho representation.
- **RFC 6570 — URI Template:** cú pháp và diễn giải URI templates khi định dạng hỗ trợ.
- **HAL — Hypertext Application Language:** mô hình _links và _embedded của application/hal+json.
- **Siren specification:** entity, links, actions và application/vnd.siren+json.
- **OpenAPI Specification 3.1:** content theo media type, response headers, schema và Links Object.
