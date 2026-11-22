# Hypermedia điều khiển chuyển trạng thái ứng dụng

Một response có thể trả về nhiều hơn dữ liệu. Nó còn có thể cho client biết đang đứng ở đâu, có thể đi tới tài nguyên nào và có thể gửi yêu cầu nghiệp vụ nào tiếp theo. Khi client chọn bước tiếp theo dựa trên những điều khiển có trong biểu diễn đã nhận, hypermedia đang tham gia điều khiển luồng ứng dụng.

Trong chương **Ràng buộc REST** của module **INTEGRATION_API_REST**, bài học này giải thích cơ chế thường được gọi là **HATEOAS — Hypermedia as the Engine of Application State**. Các ví dụ nối hypermedia với tài nguyên, URI, phương thức HTTP, mã trạng thái, hợp đồng dữ liệu và yêu cầu vận hành của một API Java/Spring hoặc công nghệ tương đương.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt trạng thái ứng dụng ở phía client với trạng thái tài nguyên do server quản lý.
- Giải thích vai trò của link, relation, media type và điều khiển gửi dữ liệu.
- Thiết kế biểu diễn có lựa chọn phù hợp với trạng thái nghiệp vụ và người gọi.
- Viết luồng client theo relation và điều khiển nhận được thay vì tự ghép mọi URI.
- Nhận diện giới hạn của hypermedia về phân quyền, cạnh tranh cập nhật, retry và tương thích hợp đồng.

## 2. Từ dữ liệu thuần tới dữ liệu có điều khiển

### 2.1. Client tự biết toàn bộ đường đi

Một response đơn giản có thể chỉ chứa:

~~~json
{
  "id": "ord-1042",
  "status": "CONFIRMED",
  "version": 7,
  "total": 350000,
  "currency": "VND"
}
~~~

Để hủy đơn, client có thể phải tự mã hóa các quy tắc:

~~~text
Nếu status là CONFIRMED:
    hiển thị nút Hủy
    ghép /orders/{id}/cancellations
    gửi POST với cấu trúc body đã ghi trong mã
~~~

Cách làm này tạo nhiều điểm phụ thuộc: cấu trúc đường dẫn, tập trạng thái cho phép, quyền người dùng và cấu trúc yêu cầu hủy. Nếu server đổi vị trí endpoint hoặc điều kiện hủy, nhiều client có thể phải sửa cùng lúc.

Không phải mọi phụ thuộc đều có thể hoặc cần loại bỏ. Client vẫn phải hiểu nghiệp vụ và hợp đồng dữ liệu. Hypermedia đưa các lựa chọn và địa chỉ cụ thể của lần tương tác hiện tại vào biểu diễn, qua đó giảm việc client phải tự suy ra chúng.

### 2.2. Server trả cả lựa chọn tiếp theo

Một biểu diễn giàu điều khiển hơn có thể bao gồm:

~~~json
{
  "id": "ord-1042",
  "status": "CONFIRMED",
  "version": 7,
  "links": [
    {
      "rel": "self",
      "href": "/orders/ord-1042",
      "type": "application/vnd.example.order+json"
    }
  ],
  "actions": [
    {
      "rel": "https://api.example.test/rels/cancel-order",
      "href": "/orders/ord-1042/cancellations",
      "method": "POST",
      "contentType": "application/vnd.example.cancellation-request+json",
      "fields": [
        {
          "name": "reason",
          "type": "string",
          "required": true,
          "allowedValues": ["CUSTOMER_REQUEST", "OTHER"]
        },
        {
          "name": "expectedOrderVersion",
          "type": "integer",
          "required": true,
          "value": 7
        }
      ]
    }
  ]
}
~~~

Client hiểu relation `cancel-order` có thể tìm điều khiển tương ứng, dùng `href`, `method` và mô tả đầu vào để tạo request. Địa chỉ cụ thể đến từ server; ý nghĩa nghiệp vụ của relation và định dạng điều khiển đến từ hợp đồng mà client hỗ trợ.

**Cấu trúc `links`, `actions`, `fields` và các media type `application/vnd.example.*+json` trong bài là thiết kế minh họa, không phải một chuẩn JSON có sẵn.** Server và client phải thống nhất quy tắc xử lý trước khi dùng. Chỉ thêm những tên field này vào JSON không tự làm client bất kỳ hiểu được API.

## 3. Hai loại trạng thái cần phân biệt

### 3.1. Trạng thái tài nguyên

Trạng thái tài nguyên là thông tin nghiệp vụ mà server quản lý. Ví dụ, đơn hàng `ord-1042` đang `CONFIRMED`, có địa chỉ giao hàng, danh sách mặt hàng và phiên bản `7`.

Trong mô hình minh họa, vòng đời có thể là:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> CONFIRMED: xác nhận
    DRAFT --> CANCELLED: hủy
    CONFIRMED --> SHIPPED: bàn giao vận chuyển
    CONFIRMED --> CANCELLED: hủy khi đủ điều kiện
    SHIPPED --> DELIVERED: giao thành công
~~~

Đây là mô hình nghiệp vụ để học, không phải vòng đời bắt buộc của mọi hệ thống. Quyền, thanh toán, tồn kho hoặc thời hạn có thể làm điều kiện chuyển trạng thái phức tạp hơn.

### 3.2. Trạng thái ứng dụng

Trạng thái ứng dụng mô tả tiến trình tương tác của client: đang xem danh sách, đã chọn đơn nào, đang nhập lý do hủy hay đang xem kết quả. Đi từ danh sách tới chi tiết là một chuyển trạng thái ứng dụng dù đơn hàng chưa thay đổi.

| Tương tác | Trạng thái ứng dụng thay đổi thế nào? | Trạng thái đơn hàng có bắt buộc đổi không? |
|---|---|---|
| Theo link tới danh sách | Client đang xem tập đơn hàng | Không |
| Theo link tới chi tiết | Client đang xem một đơn cụ thể | Không |
| Chọn điều khiển hủy | Client chuẩn bị yêu cầu hủy | Chưa |
| Server thực hiện hủy | Client nhận kết quả yêu cầu | Có, theo hợp đồng ví dụ |
| Đọc lại đơn hàng | Client có biểu diễn và lựa chọn mới | Lần đọc không yêu cầu đổi trạng thái đơn |

HATEOAS thuộc ràng buộc giao diện thống nhất của REST. Roy Fielding nhấn mạnh rằng client bắt đầu từ một URI đầu vào cùng các media type đã hiểu, rồi chọn bước tiếp theo từ những lựa chọn server cung cấp. Hypermedia không yêu cầu biểu diễn phải là HTML. [Giải thích của Roy Fielding về API được điều khiển bằng hypertext](https://roy.gbiv.com/untangled/2008/rest-apis-must-be-hypertext-driven).

### 3.3. Hypermedia không mâu thuẫn với stateless

Server không cần lưu trong bộ nhớ rằng “client này vừa mở màn hình hủy” để hiểu request tiếp theo. Request hủy vẫn phải chứa thông tin xác thực và đầu vào cần thiết. Server đọc trạng thái nghiệp vụ hiện tại rồi đánh giá yêu cầu.

Client giữ ngữ cảnh tương tác của mình, còn server lưu đơn hàng và quy tắc nghiệp vụ. Link và action là một phần biểu diễn, không đòi hỏi phiên hội thoại nằm trên một instance cụ thể.

## 4. Những thành phần làm hypermedia có ý nghĩa

### 4.1. Link: từ ngữ cảnh hiện tại tới đích

Một link có ngữ cảnh, quan hệ và đích. Ví dụ trong biểu diễn đơn hàng:

~~~json
{
  "rel": "self",
  "href": "/orders/ord-1042",
  "type": "application/vnd.example.order+json"
}
~~~

`href` xác định đích; `rel` mô tả quan hệ với ngữ cảnh; `type` trong định dạng minh họa là gợi ý media type của đích. Response thực tế vẫn cần có `Content-Type` phù hợp.

RFC 8288 mô tả mô hình Web Linking và cách truyền link bằng header `Link`. Relation mở rộng có thể dùng URI định danh. URI relation biểu đạt ý nghĩa quan hệ, không đồng nhất với địa chỉ đích và không yêu cầu client tự động tải tài liệu tại URI đó. [RFC 8288, mục 2 và 2.1.2](https://www.rfc-editor.org/rfc/rfc8288.html#section-2).

Ví dụ liên kết phân trang được truyền trong header:

~~~http
Link: </orders?cursor=eyJpZCI6MTA0Mn0>; rel="next"
~~~

Không phải cứ gặp link là client phải gọi. Nó chọn relation phù hợp với mục đích, định dạng được hỗ trợ và chính sách tin cậy của mình.

### 4.2. Relation: ý nghĩa ổn định hơn vị trí

Hai link có thể cùng trỏ tới URI hợp lệ nhưng mang ý nghĩa khác nhau. Client cần biết mình muốn xem trang kế tiếp, tài nguyên hiện tại hay một tài nguyên nghiệp vụ liên quan.

| Thành phần | Ví dụ | Client sử dụng để làm gì? |
|---|---|---|
| Relation chung | `self`, `next`, `prev` | Hiểu quan hệ theo định nghĩa tương ứng |
| Relation nghiệp vụ minh họa | `https://api.example.test/rels/cancel-order` | Nhận diện lựa chọn gửi yêu cầu hủy |
| Địa chỉ đích | `/orders/ord-1042/cancellations` | Gửi request tới vị trí server cung cấp |
| Nhãn hiển thị nếu có | `Hủy đơn` | Trình bày cho người dùng, không làm khóa xử lý ổn định |

Đổi nhãn tiếng Việt không được làm client mất khả năng nhận diện thao tác. Ngược lại, giữ relation nhưng đổi ý nghĩa từ “yêu cầu hủy” sang “hoàn tiền” là thay đổi hợp đồng nguy hiểm.

### 4.3. Điều khiển thao tác: cần nhiều hơn URL

Địa chỉ `/orders/ord-1042/cancellations` chưa cho biết phương thức nào được dùng, phải gửi gì và theo định dạng nào. Để hướng dẫn gửi dữ liệu, biểu diễn phải mô tả các thông tin đó hoặc dẫn tới hợp đồng mà client hiểu.

Quy ước của định dạng minh họa:

| Field | Quy tắc trong bài |
|---|---|
| `links` | Danh sách lựa chọn điều hướng đọc bằng `GET` |
| `links[].rel` | Ý nghĩa quan hệ; client tìm theo giá trị này |
| `links[].href` | URI-reference của đích, được phân giải theo URI cơ sở của biểu diễn |
| `actions` | Các điều khiển gửi yêu cầu nghiệp vụ đang được quảng bá |
| `actions[].method` | Phương thức HTTP của điều khiển |
| `actions[].contentType` | Media type của request body |
| `fields[].name` và `type` | Tên và kiểu đầu vào trong body JSON |
| `fields[].required` | Field phải có theo hợp đồng |
| `fields[].allowedValues` | Những giá trị được phép trong điều khiển hiện tại |
| `fields[].value` | Giá trị server cung cấp để điền vào request của ví dụ |

Không suy rộng quy tắc “link là GET” của bảng sang mọi định dạng hypermedia. Phương thức và cách gửi dữ liệu phụ thuộc media type cùng ngữ nghĩa quan hệ đang áp dụng.

`expectedOrderVersion` là điều kiện nghiệp vụ minh họa, không phải cơ chế HTTP chuẩn. Server phải kiểm tra nó; client sửa giá trị không thể thay đổi phiên bản thật của đơn hàng.

### 4.4. Media type và hợp đồng xử lý

`application/json` cho biết cú pháp JSON, nhưng không định nghĩa field `actions` là form hay `href` phải được theo bằng phương thức nào. Các quy tắc này cần được mô tả bằng media type, profile hoặc hợp đồng biểu diễn được thỏa thuận.

Có thể dùng định dạng hypermedia đã được đặc tả, hoặc thiết kế định dạng riêng khi có lý do và khả năng hỗ trợ. Dù theo cách nào, hãy làm rõ:

- Client tìm và hiểu relation thế nào.
- Cách phân giải URI-reference và xử lý URI template nếu có.
- Cách lấy đầu vào, xác định phương thức và mã hóa request.
- Hành vi với field, relation hoặc điều khiển chưa biết.
- Cách biểu diễn lỗi, dữ liệu rỗng và kết quả bất đồng bộ.

Đuôi `+json` hoặc tên media type tự đặt không tự cung cấp những quy tắc đó. Tài liệu và triển khai hai phía mới tạo thành hợp đồng có thể sử dụng.

## 5. Luồng hoàn chỉnh: khám phá, xem đơn và hủy đơn

### 5.1. Bắt đầu từ URI đầu vào

Giả sử client được cấu hình URI đầu vào `https://api.example.test/api` và hỗ trợ định dạng của ví dụ:

~~~http
GET /api HTTP/1.1
Host: api.example.test
Accept: application/vnd.example.api+json
Authorization: Bearer <access-token>
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/vnd.example.api+json
Cache-Control: private, no-store

{
  "links": [
    {
      "rel": "https://api.example.test/rels/orders",
      "href": "/orders?limit=20",
      "type": "application/vnd.example.orders+json"
    }
  ]
}
~~~

Client tìm relation `orders`, phân giải `href` thành URI tuyệt đối và gửi request. Nó không cần tự biết collection nằm ở `/orders` hay `/sales/orders`.

URI đầu vào, ý nghĩa relation và media type là kiến thức ban đầu vẫn tồn tại. “Không ghép URI” không có nghĩa là “không cần biết bất kỳ điều gì trước khi gọi API”.

### 5.2. Theo link từ collection tới chi tiết

~~~http
GET /orders?limit=20 HTTP/1.1
Accept: application/vnd.example.orders+json
Authorization: Bearer <access-token>
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/vnd.example.orders+json
Cache-Control: private, no-store

{
  "items": [
    {
      "id": "ord-1042",
      "status": "CONFIRMED",
      "links": [
        {
          "rel": "self",
          "href": "/orders/ord-1042",
          "type": "application/vnd.example.order+json"
        }
      ]
    }
  ],
  "links": [
    {
      "rel": "self",
      "href": "/orders?limit=20",
      "type": "application/vnd.example.orders+json"
    },
    {
      "rel": "next",
      "href": "/orders?cursor=eyJpZCI6MTA0Mn0&limit=20",
      "type": "application/vnd.example.orders+json"
    }
  ]
}
~~~

Client theo `next` mà không phân tích cấu trúc cursor hay tự tính trang kế tiếp. Khi đã chọn item, nó theo `self` trong ngữ cảnh item để đọc chi tiết. Phải phân biệt rõ ngữ cảnh collection với ngữ cảnh item khi tìm relation.

Nếu không còn trang sau, API có thể không quảng bá `next` theo hợp đồng. Theo link phân trang không tự bảo đảm quá trình đọc là một snapshot nhất quán; dữ liệu có thể thay đổi giữa hai lần gọi nếu API không cung cấp bảo đảm đó.

### 5.3. Đọc chi tiết và chọn điều khiển

Client nhận biểu diễn đơn có `actions` như phần 2.2. Với người được phép hủy và đơn đủ điều kiện, action `cancel-order` xuất hiện. Nếu người dùng chọn hủy, client tạo body từ đầu vào và phiên bản được cung cấp:

~~~http
POST /orders/ord-1042/cancellations HTTP/1.1
Content-Type: application/vnd.example.cancellation-request+json
Accept: application/vnd.example.cancellation+json
Authorization: Bearer <access-token>

{
  "reason": "CUSTOMER_REQUEST",
  "expectedOrderVersion": 7
}
~~~

Phương thức, đích và kiểu nội dung request được lấy từ action. Media type response mong muốn thuộc hợp đồng mà client hỗ trợ cho relation này. Không có quy tắc chung rằng `contentType` của request cũng là media type của response.

### 5.4. Server thực hiện và trả tài nguyên kết quả

Trong ví dụ, yêu cầu hủy được thực hiện đồng bộ. Nếu thành công, server tạo tài nguyên ghi nhận việc hủy:

~~~http
HTTP/1.1 201 Created
Location: /orders/ord-1042/cancellations/can-31
Content-Type: application/vnd.example.cancellation+json
Cache-Control: private, no-store

{
  "id": "can-31",
  "status": "APPLIED",
  "reason": "CUSTOMER_REQUEST",
  "links": [
    {
      "rel": "self",
      "href": "/orders/ord-1042/cancellations/can-31",
      "type": "application/vnd.example.cancellation+json"
    },
    {
      "rel": "https://api.example.test/rels/order",
      "href": "/orders/ord-1042",
      "type": "application/vnd.example.order+json"
    }
  ]
}
~~~

`APPLIED` là trạng thái do hợp đồng ví dụ định nghĩa. Không suy ra mọi API tạo yêu cầu hủy đều hủy ngay: một hệ thống khác có thể chỉ tiếp nhận và xử lý sau, với mã trạng thái cùng tài nguyên theo dõi phù hợp.

Client theo relation `order` để đọc biểu diễn mới. Nếu chính sách không cho hủy lại, biểu diễn mới không quảng bá action `cancel-order`:

~~~json
{
  "id": "ord-1042",
  "status": "CANCELLED",
  "version": 8,
  "links": [
    {
      "rel": "self",
      "href": "/orders/ord-1042",
      "type": "application/vnd.example.order+json"
    }
  ],
  "actions": []
}
~~~

Danh sách action rỗng không có nghĩa là hết mọi tương tác; client vẫn đọc hoặc điều hướng qua link đã hiểu.

### 5.5. Nhìn toàn bộ đường đi

~~~mermaid
flowchart LR
    A[URI đầu vào] -->|relation orders, GET| B[Collection]
    B -->|self của item, GET| C[Chi tiết đơn]
    C -->|action cancel-order, POST| D[Kết quả hủy]
    D -->|relation order, GET| E[Biểu diễn đơn mới]
~~~

Sơ đồ giúp người học hiểu một hành trình. Client thực tế phải đọc lựa chọn ở từng response. Nếu action không được quảng bá hoặc có kết quả lỗi, nó xử lý nhánh tương ứng thay vì cố thực hiện chuỗi đã vẽ.

## 6. Điều khiển được quảng bá không phải giấy phép thực thi

### 6.1. Lựa chọn phụ thuộc trạng thái và người gọi

| Trạng thái tài nguyên | Người gọi | Có thể quảng bá hủy? |
|---|---|---|
| `CONFIRMED`, còn thời hạn hủy | Chủ đơn có quyền hủy | Có |
| `CONFIRMED` | Người chỉ có quyền đọc | Không |
| `SHIPPED` | Chủ đơn | Không, nếu phải dùng quy trình trả hàng riêng |
| `CANCELLED` | Chủ đơn | Không, nếu hợp đồng không có thao tác hủy lại |

Server nên dựng điều khiển từ chính sách nghiệp vụ và quyền, thay vì chỉ so sánh chuỗi `status`. Một đơn còn `CONFIRMED` vẫn có thể hết thời hạn hủy hoặc đang trong công đoạn không thể đảo ngược.

### 6.2. Kiểm tra lại khi nhận request

Giả sử client đọc đơn lúc 10:00:00 và thấy action hủy. Đến 10:00:02, kho bàn giao đơn cho đơn vị vận chuyển. Đến 10:00:03, request hủy mới tới.

Server phải đánh giá lại quyền, phiên bản và điều kiện hủy tại thời điểm thực hiện. Việc kiểm tra với cập nhật cần được phối hợp bằng giao dịch hoặc kiểm soát đồng thời phù hợp, tránh khoảng trống giữa “đã kiểm tra” và “đã ghi”.

Action đã nhận phản ánh lựa chọn server quảng bá trong ngữ cảnh trước đó. Nó không khóa tài nguyên, không giữ chỗ và không bảo đảm request tương lai thành công.

### 6.3. Thiếu link không phải cơ chế phân quyền

Người gọi có thể tự nhập URI, dùng response cũ hoặc sửa request. Endpoint vẫn cần xác thực và kiểm tra quyền theo tài nguyên.

Server cũng có thể không quảng bá lựa chọn vì trạng thái, quyền, chức năng chưa hỗ trợ hoặc chính sách biểu diễn. Client không nên suy ra một nguyên nhân duy nhất nếu hợp đồng không nói rõ.

Nếu sản phẩm cần giải thích vì sao không thể hủy, API có thể bổ sung mã lý do hoặc thông tin hỗ trợ. Cân nhắc thông tin được phép tiết lộ để tránh rò rỉ qua danh sách điều khiển.

## 7. Cạnh tranh cập nhật, lỗi và retry

### 7.1. Điều kiện phiên bản của ví dụ

`expectedOrderVersion: 7` yêu cầu server chỉ thực hiện hủy nếu phiên bản đơn vẫn phù hợp. Nếu phiên bản thực đã đổi, API minh họa có thể trả lỗi xung đột và link đọc lại:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/vnd.example.error+json
Cache-Control: private, no-store

{
  "code": "ORDER_VERSION_CONFLICT",
  "message": "Đơn hàng đã thay đổi. Hãy đọc lại trước khi chọn thao tác.",
  "links": [
    {
      "rel": "https://api.example.test/rels/order",
      "href": "/orders/ord-1042",
      "type": "application/vnd.example.order+json"
    }
  ]
}
~~~

Đây là hợp đồng lỗi minh họa. Sau khi đọc lại, client đánh giá điều khiển mới, không tự thay phiên bản rồi gửi lại thao tác có tác dụng phụ mà bỏ qua ý định hiện tại của người dùng.

### 7.2. Phân biệt điều kiện nghiệp vụ với If-Match

HTTP có `ETag` và `If-Match` để điều kiện hóa request; `If-Match` dùng so sánh mạnh. Điều kiện HTTP không thỏa có thể dẫn tới `412 Precondition Failed`; `409 Conflict` biểu đạt xung đột với trạng thái hiện tại của tài nguyên. [RFC 9110 về If-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1), [mã 409 và 412](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.10).

Cần xác định đúng tài nguyên đích. Nếu đọc ETag của `/orders/ord-1042` rồi gửi request tới `/orders/ord-1042/cancellations`, không được mặc định `If-Match` tại URI con kiểm tra ETag của đơn cha. Hợp đồng phải giải quyết điều kiện trên đúng tài nguyên; ví dụ trong bài dùng field phiên bản nghiệp vụ một cách tường minh.

### 7.3. Có action không làm POST tự idempotent

Nếu request hủy timeout, client chưa biết server đã thực hiện chưa. Theo lại action và gửi `POST` lần nữa không tự bảo đảm chỉ tạo một kết quả hủy.

API cần chọn cách xử lý: khóa idempotency theo hợp đồng, ràng buộc chống tạo trùng, hoặc cách truy vấn và đối soát kết quả. Nếu dùng khóa idempotency, phải quy định phạm vi chủ thể, liên hệ với payload, thời hạn lưu và xử lý request trùng đến đồng thời.

Hypermedia có thể cung cấp lựa chọn truy vấn kết quả; bảo đảm chống tác dụng phụ lặp vẫn phải do server và hệ thống phía sau triển khai.

## 8. Cách client sử dụng hypermedia

### 8.1. Thuật toán tương tác

~~~text
1. Gọi URI đầu vào với media type được hỗ trợ.
2. Kiểm tra mã trạng thái và Content-Type.
3. Đọc biểu diễn theo hợp đồng đã biết.
4. Tìm relation phù hợp với mục tiêu của người dùng.
5. Phân giải href theo URI cơ sở của biểu diễn.
6. Kiểm tra đích thuộc phạm vi tin cậy của client.
7. Với action đã hiểu, lấy đầu vào và tạo request đúng mô tả.
8. Gửi request; xử lý thành công, lỗi và kết quả chưa hoàn tất.
9. Dùng biểu diễn mới để quyết định bước tiếp theo.
~~~

Nếu API có chuyển hướng hoặc cơ chế đặt URI cơ sở riêng, client cần xử lý đúng. Không mặc định nối chuỗi địa chỉ với domain ban đầu trong mọi tình huống.

### 8.2. Tìm theo relation thay vì vị trí trong mảng

Giả mã Java:

~~~java
String cancelRel = "https://api.example.test/rels/cancel-order";

Optional<Action> cancellation = orderView.actions().stream()
    .filter(action -> cancelRel.equals(action.rel()))
    .findFirst();

if (cancellation.isEmpty()) {
    showCancellationUnavailable();
    return;
}

Action action = cancellation.get();
URI target = representationUri.resolve(action.href());

requireTrustedTarget(target);
requireSupportedAction(action);

// Body được tạo từ fields, dữ liệu người dùng và hợp đồng relation.
// Chỉ gửi khi người dùng hoặc mục đích ứng dụng cho phép.
showCancellationForm(action, target);
~~~

`Action`, các hàm kiểm tra và hàm giao diện là thành phần do ứng dụng định nghĩa. Client thực tế cần decoder, bộ xử lý HTTP, chính sách lỗi và mô hình dữ liệu tương ứng; đây không phải chương trình hoàn chỉnh.

Không dùng `actions().get(0)` để suy ra thao tác hủy, không nhận diện bằng nhãn hiển thị và không kiểm tra hậu tố URI để đoán ý nghĩa nghiệp vụ.

### 8.3. Relation chưa biết và action chưa hỗ trợ

Server mới có thể bổ sung relation mà client cũ chưa hiểu. Với hợp đồng cho phép mở rộng, client bỏ qua lựa chọn chưa biết theo quy tắc đã thỏa thuận, thay vì báo lỗi toàn bộ biểu diễn.

Bỏ qua field tùy chọn khác với bỏ qua field bắt buộc để xử lý an toàn. Nếu gặp media type, phương thức hoặc điều khiển chưa hỗ trợ, client không được đoán rồi gửi request có tác dụng phụ.

Hypermedia không biến client thành tác nhân hiểu mọi nghiệp vụ mới. Client biết “hủy đơn” chưa chắc hiểu “chia đơn”. Form động có thể hỗ trợ một phần mở rộng giao diện, nhưng vẫn cần ngữ nghĩa, validation và quyết định sản phẩm.

## 9. Tổ chức phía server với Java/Spring

Có thể xem việc tạo hypermedia là bước dựng biểu diễn trên dữ liệu miền và chính sách người gọi. Bộ định tuyến cung cấp URI công khai; chính sách nghiệp vụ quyết định lựa chọn nào được quảng bá.

~~~text
HTTP adapter
    -> Lấy dữ liệu và ngữ cảnh người gọi
    -> Dựng biểu diễn
         -> Gắn link điều hướng
         -> Tham khảo chính sách để gắn action
    -> Trả Content-Type, header và body

Khi nhận yêu cầu hủy
    -> Xác thực và kiểm tra đầu vào
    -> Kiểm tra quyền, phiên bản và trạng thái
    -> Thực hiện với kiểm soát đồng thời phù hợp
    -> Dựng biểu diễn kết quả
~~~

Giả mã bộ chuyển đổi:

~~~java
OrderView toView(Order order, Viewer viewer) {
    List<Link> links = new ArrayList<>();
    links.add(link("self", publicUris.order(order.id())));

    List<Action> actions = new ArrayList<>();
    if (orderPolicy.mayCancel(viewer, order)) {
        actions.add(cancellationAction(
            publicUris.cancellations(order.id()),
            order.version()
        ));
    }

    return new OrderView(
        order.id(),
        order.status(),
        order.version(),
        links,
        actions
    );
}
~~~

Đoạn mã nhấn mạnh trách nhiệm, không phụ thuộc API của một phiên bản thư viện. Các kiểu và hàm như `OrderView`, `publicUris`, `cancellationAction` do ứng dụng định nghĩa. Hàm dựng action phải điền đủ relation, phương thức, media type và field theo hợp đồng.

Hai điểm cần giữ:

- Dùng cùng nguồn chính sách có thẩm quyền cho quảng bá và thực thi; endpoint vẫn phải đánh giá lại với trạng thái hiện tại.
- Tạo URI từ cấu hình và thông tin định tuyến công khai đáng tin cậy. Tránh trả hostname nội bộ hoặc tin mọi header chuyển tiếp do bên gọi tự cung cấp.

Không nên để việc gắn link gây một truy vấn cơ sở dữ liệu cho từng action trên từng item khi collection lớn. Có thể chọn biểu diễn tóm tắt và cung cấp điều khiển chi tiết khi đọc tài nguyên riêng, miễn hợp đồng nói rõ.

## 10. Cache, phân trang và an toàn khi theo link

### 10.1. Cache phải tính cả điều khiển

Nếu biểu diễn chứa action theo quyền người gọi, cache sai có thể trả lựa chọn hoặc dữ liệu của người này cho người khác. Các ví dụ dùng `Cache-Control: private, no-store` để tập trung vào luồng tương tác, không đề xuất một chính sách duy nhất cho mọi API.

Khi cần cache, thiết kế phạm vi chia sẻ, khóa cache, thời gian sống và tái xác thực theo dữ liệu cùng chính sách quyền. Dù không dùng cache HTTP, response vẫn có thể cũ ngay sau khi nhận; server luôn cần kiểm tra lại khi thực thi.

### 10.2. Theo next giúp giảm hiểu biết về cách phân trang

Client theo `next` có thể tiếp tục hoạt động khi server đổi cấu trúc cursor hoặc cách tạo địa chỉ, nếu relation và hợp đồng tương thích. Client không nên tự sửa cursor hoặc mặc định `next` luôn tồn tại.

Server vẫn phải giới hạn kích thước trang, duy trì quyền truy cập và quy định tính ổn định của thứ tự. Hypermedia hỗ trợ khám phá trang, không thay thế toàn bộ thiết kế phân trang.

### 10.3. Không chuyển thông tin xác thực tới mọi đích

Một link có thể trỏ ngoài origin hiện tại. Client cần chính sách về origin, scheme, chuyển hướng và thông tin xác thực được gửi. Không tự động đính kèm access token nội bộ cho mọi URI trong response.

Với client chạy phía server, theo URI không được kiểm soát còn có thể dẫn tới truy cập đích nội bộ ngoài dự kiến. Phạm vi tin cậy nên gắn với nhiệm vụ tích hợp, thay vì chấp nhận mọi địa chỉ chỉ vì nó nằm trong field `href`.

## 11. Hypermedia và OpenAPI bổ sung cho nhau

OpenAPI có thể mô tả request, response, schema, mã trạng thái và cấu trúc biểu diễn. Hypermedia trả địa chỉ và lựa chọn của một lần tương tác cụ thể trong ngữ cảnh hiện tại.

| Câu hỏi | Nguồn trả lời thích hợp |
|---|---|
| Field phiên bản có ý nghĩa gì? | Hợp đồng dữ liệu và tài liệu nghiệp vụ |
| Client hiểu cancel-order thế nào? | Định nghĩa relation và hợp đồng xử lý |
| Với đơn và người gọi hiện tại, có quảng bá hủy không? | Biểu diễn runtime |
| Gửi tới URI nào trong lần này? | `href` trong điều khiển nhận được |
| Request vừa gửi đã thành công chưa? | Mã trạng thái, header và biểu diễn kết quả |

Tài liệu liệt kê endpoint không tự tạo điều khiển runtime. Response có link cũng không thay thế tài liệu ngữ nghĩa, schema hoặc yêu cầu bảo mật. Cần mô tả cả hai phần phù hợp với cách client thực sự sử dụng.

## 12. Giá trị và giới hạn khi phát triển API

### 12.1. Giá trị có thể đạt được

- Server kiểm soát vị trí đích; client ít phải ghép đường dẫn theo cấu trúc nội bộ.
- Lựa chọn được thể hiện theo ngữ cảnh, giảm sao chép một phần quy tắc hiển thị giữa client.
- Luồng khám phá và phân trang thích ứng tốt hơn với thay đổi địa chỉ.
- API bộc lộ bước tiếp theo gần dữ liệu mà người dùng đang xem.

Lợi ích xuất hiện khi client thực sự dùng điều khiển và hợp đồng ổn định. Nếu client bỏ qua link rồi tiếp tục ghép URI, thêm hypermedia chủ yếu làm payload lớn hơn.

### 12.2. Những điều vẫn cần thiết kế

- Hiểu biết nghiệp vụ, relation và media type của client.
- Tương thích khi schema hoặc ngữ nghĩa thay đổi.
- Phân quyền, giao dịch, idempotency và xử lý lỗi.
- Số lượt trao đổi, dữ liệu nhúng và kích thước payload.
- Chi phí dựng biểu diễn và khả năng quan sát.

Đổi `/orders/ord-1042/cancellations` sang URI khác có thể ít ảnh hưởng tới client theo relation. Đổi `reason` từ mã chuỗi thành đối tượng bắt buộc phức tạp, hoặc đổi ý nghĩa `cancel-order`, vẫn có thể phá vỡ hợp đồng.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác hơn |
|---|---|
| Có field url là đã có HATEOAS | Cần ngữ nghĩa, quy tắc xử lý và việc client dùng điều khiển để đi tiếp |
| Mọi link đều thay đổi dữ liệu | Nhiều link phục vụ điều hướng đọc; gửi dữ liệu cần hợp đồng tương ứng |
| URI relation chính là endpoint | Relation định danh ý nghĩa; href định danh đích của lần tương tác |
| Client không cần tài liệu | Client vẫn phải hiểu biểu diễn, relation, dữ liệu và nghiệp vụ |
| Có action là chắc chắn thành công | Trạng thái và quyền có thể đổi; server phải kiểm tra lại |
| Ẩn link là đủ bảo vệ endpoint | Request trực tiếp vẫn phải được kiểm tra quyền |
| Mọi action nên chạy tự động | Chỉ thực hiện lựa chọn đã hiểu và được mục đích/người dùng cho phép |
| Hypermedia loại bỏ versioning | Tương thích schema và ngữ nghĩa vẫn cần quản lý |
| HATEOAS đòi server lưu phiên từng bước | Ngữ cảnh tương tác có thể ở client; request vẫn đủ thông tin xử lý |
| Đặt field _links là đủ | Tên field không tự định nghĩa định dạng và không làm client theo link |

## 14. Thực hành thiết kế và kiểm chứng hành vi

Có thể thực hành với một tài nguyên đơn hàng nhỏ và bộ giả lập quyền:

1. Định nghĩa hợp đồng biểu diễn, relation và quy tắc links/actions.
2. Tạo URI đầu vào dẫn tới collection và link từ item tới chi tiết.
3. Dựng action hủy theo người gọi, trạng thái, thời hạn và phiên bản.
4. Viết client tìm theo relation, phân giải URI và trình bày form.
5. Đổi cấu trúc URI phía server trong kịch bản thử; kiểm tra client vẫn theo địa chỉ được trả.
6. Mô phỏng trạng thái đổi sau lần đọc; kiểm tra server từ chối phù hợp và client đọc lại.
7. Thử người chỉ có quyền đọc; kiểm tra vừa không quảng bá action, vừa kiểm soát request trực tiếp.
8. Thêm relation mới; kiểm tra client cũ xử lý theo quy tắc mở rộng đã thống nhất.

Các tình huống kiểm chứng nên bám vào hành vi hợp đồng:

| Tình huống | Kết quả cần quan sát |
|---|---|
| Người có quyền, đơn đủ điều kiện | Action có đúng relation, method, href và đầu vào |
| Người không có quyền hủy | Không quảng bá hủy; request trực tiếp vẫn bị kiểm soát |
| Đơn đã chuyển sang không thể hủy | Điều khiển cũ không gây chuyển trạng thái trái phép |
| Có action lạ | Client không tự thực thi, không đoán payload |
| Đổi URI, giữ hợp đồng | Client dùng đích mới từ biểu diễn |
| Request timeout | Áp dụng đối soát/retry có bảo vệ tác dụng phụ |
| Dữ liệu đổi khi phân trang | Hành vi đúng bảo đảm đã công bố |

## 15. Câu hỏi tự đánh giá

**1. Theo link từ danh sách sang chi tiết có chuyển trạng thái ứng dụng dù đơn hàng chưa đổi không?**

Có. Client thay ngữ cảnh tương tác, còn lần đọc không yêu cầu đổi trạng thái nghiệp vụ của đơn.

**2. Biết trước relation cancel-order có trái với hypermedia không?**

Không. Client cần hiểu ngữ nghĩa và định dạng; điều cần giảm là việc mã hóa URI cụ thể và suy diễn mọi lựa chọn runtime từ quy tắc sao chép.

**3. Server gửi action hủy rồi trả lỗi xung đột khi client gọi có phải luôn là lỗi thiết kế không?**

Không. Trạng thái có thể thay đổi giữa hai request. API cần hợp đồng lỗi, đường khôi phục và kiểm tra điều kiện trên trạng thái có thẩm quyền.

**4. Có thể gửi ETag của đơn làm If-Match tới collection yêu cầu hủy rồi mặc định nó bảo vệ đơn cha không?**

Không. Phải xác định đúng tài nguyên được đánh giá; nếu điều kiện liên quan tài nguyên khác, cần hợp đồng và kiểm soát đồng thời tường minh.

**5. Client chỉ đọc dữ liệu, bỏ qua link thì có thể kết luận luồng được hypermedia điều khiển không?**

Không. Cần xem client chọn bước tiếp theo từ điều khiển nhận được hay từ địa chỉ và luồng đã mã hóa sẵn.

Mỗi biểu diễn vừa mang thông tin, vừa có thể cung cấp lựa chọn có ngữ nghĩa cho bước tiếp theo. Server quảng bá lựa chọn trong ngữ cảnh hiện tại; client hiểu và lựa chọn; server tiếp tục chịu trách nhiệm kiểm tra và thực hiện nghiệp vụ khi request tới.
