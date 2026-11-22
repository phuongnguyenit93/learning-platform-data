# Quan hệ sở hữu, tham chiếu và liên kết giữa tài nguyên

## 1. Mục tiêu và bối cảnh

Một REST API thường bắt đầu bằng các tài nguyên như đơn hàng, khách hàng, sản phẩm và dòng hàng. Phần khó xuất hiện khi phải trả lời: dòng hàng có thể sống độc lập với đơn hàng không, sản phẩm có bị xóa khi xóa dòng hàng không, khách hàng được nhúng vào đơn hàng hay chỉ được tham chiếu, và client nên đi theo đường dẫn nào để lấy dữ liệu liên quan?

Trong phạm vi **INTEGRATION_API_REST**, bài học này giúp bạn:

- Phân biệt quan hệ sở hữu theo vòng đời, quan hệ tham chiếu và liên kết để điều hướng.
- Chọn URI, biểu diễn JSON và thao tác HTTP phù hợp với ý nghĩa của từng quan hệ.
- Nêu rõ ràng buộc khi tạo, đổi, bỏ liên kết hoặc xóa tài nguyên.
- Áp dụng các quyết định đó vào hợp đồng API và lớp xử lý Java/Spring.
- Xác định những tình huống cần kiểm thử để tránh liên kết sai, xóa nhầm hoặc lộ dữ liệu.

Bài học giả định bạn đã biết tài nguyên, URI và các phương thức HTTP cơ bản. Các URI, kiểu JSON và quy tắc nghiệp vụ dưới đây là một thiết kế minh họa; chúng không phải định dạng bắt buộc cho mọi REST API.

## 2. Ba khái niệm cần tách biệt

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Sở hữu theo vòng đời | Tài nguyên nào kiểm soát việc tồn tại và thay đổi của tài nguyên khác? | Đơn hàng chứa các dòng hàng chỉ có ý nghĩa trong đơn đó |
| Tham chiếu | Tài nguyên nào cần nhận diện hoặc sử dụng một tài nguyên độc lập khác? | Dòng hàng tham chiếu sản phẩm trong danh mục |
| Liên kết | Client tìm hoặc thao tác với tài nguyên liên quan bằng cách nào? | Phản hồi dòng hàng chứa đường dẫn đến sản phẩm |

Ba khái niệm này có thể cùng xuất hiện trong một quan hệ. Một dòng hàng thuộc đơn hàng về vòng đời và vẫn có thể cung cấp liên kết đến đơn hàng. Một đơn hàng tham chiếu khách hàng và cũng có thể chứa liên kết để client đọc khách hàng đó.

**Liên kết không tự xác định quyền sở hữu.** Việc phản hồi chứa URL của một sản phẩm không có nghĩa đơn hàng được phép sửa hoặc xóa sản phẩm ấy.

Từ “sở hữu” trong bài nói về vòng đời và ràng buộc miền nghiệp vụ. Người tạo bản ghi, người được giao xử lý, chủ tài khoản và người có quyền quản trị là những khái niệm khác. Một người dùng tạo đơn hàng không có nghĩa tài nguyên người dùng sở hữu vòng đời của toàn bộ đơn hàng đó.

### 2.1. Số lượng không quyết định vòng đời

Quan hệ một-nhiều hay nhiều-nhiều chỉ mô tả số lượng đầu mối:

- Một đơn hàng có nhiều dòng hàng.
- Một khách hàng có nhiều đơn hàng.
- Một người dùng tham gia nhiều dự án, và một dự án có nhiều người dùng.

Hai quan hệ đầu đều là một-nhiều, nhưng ý nghĩa khác nhau. Dòng hàng phụ thuộc đơn hàng; đơn hàng có lịch sử riêng và không nhất thiết bị xóa khi khách hàng bị xóa.

Vì vậy, chỉ thấy khóa ngoại hoặc quan hệ `@OneToMany` trong Java chưa đủ để kết luận cách thiết kế API.

## 3. Xác định quan hệ từ quy tắc nghiệp vụ

Xét một hệ thống bán hàng với các quy tắc minh họa sau:

1. Đơn hàng nháp cho phép thêm, sửa và xóa dòng hàng.
2. Mỗi dòng hàng thuộc đúng một đơn hàng và không được chuyển sang đơn khác.
3. Dòng hàng không có ý nghĩa độc lập khi đơn hàng nháp bị xóa.
4. Sản phẩm là tài nguyên dùng chung, tồn tại độc lập với các đơn hàng.
5. Khách hàng tồn tại độc lập; một đơn nháp có thể chưa gắn khách hàng, nhưng phải có khách hàng trước khi xác nhận.
6. Khi xác nhận đơn, hệ thống chốt thông tin cần thiết như tên hàng, đơn giá và địa chỉ giao hàng theo hợp đồng nghiệp vụ.
7. Đơn đã xác nhận không được xóa qua API minh họa; việc hủy đơn là chuyển trạng thái riêng.

Bảng thiết kế tương ứng:

| Quan hệ | Số lượng | Ý nghĩa vòng đời | Hành vi khi thay đổi |
| --- | --- | --- | --- |
| Đơn hàng → dòng hàng | Một-nhiều | Đơn hàng sở hữu dòng hàng | Xóa đơn nháp làm các dòng hàng của đơn đó không còn khả dụng |
| Dòng hàng → sản phẩm | Nhiều-một | Tham chiếu tài nguyên độc lập | Xóa dòng hàng không xóa sản phẩm |
| Đơn hàng → khách hàng | Nhiều-một, tùy chọn khi nháp | Tham chiếu tài nguyên độc lập | Bỏ liên kết không xóa khách hàng |
| Đơn hàng → địa chỉ giao hàng đã chốt | Một-một | Giá trị được lưu trong đơn | Sửa địa chỉ hồ sơ khách hàng không tự sửa lịch sử đơn |

Trước khi chọn URI, hãy trả lời các câu hỏi sau cho từng quan hệ:

- Tài nguyên con có thể được tạo hoặc đọc độc lập không?
- Tài nguyên đó có thể có nhiều cha hoặc đổi cha không?
- Khi cha bị xóa, con phải bị xóa, được giữ lại, hay chặn thao tác xóa?
- Ai được phép thay đổi quan hệ và trong trạng thái nghiệp vụ nào?
- Cần giữ trạng thái hiện tại của tài nguyên liên quan hay trạng thái tại thời điểm giao dịch?

Những câu trả lời này tạo ra hợp đồng API. Không nên để lựa chọn mặc định của ORM quyết định thay nghiệp vụ.

### 3.1. Giá trị nhúng khác với tài nguyên được tham chiếu

Địa chỉ giao hàng có thể được biểu diễn như một giá trị bên trong đơn:

~~~json
{
  "shippingAddress": {
    "recipient": "Nguyễn An",
    "street": "12 Đường A",
    "city": "Đà Nẵng"
  }
}
~~~

Nếu địa chỉ này không có định danh, URI hoặc vòng đời riêng trong API, bạn không cần biến nó thành một tài nguyên độc lập chỉ vì cơ sở dữ liệu lưu ở bảng khác.

Ngược lại, `/customers/cus-42` có định danh và vòng đời riêng. Đơn hàng tham chiếu khách hàng đó nhưng vẫn có thể giữ một bản chụp địa chỉ giao hàng. Bản chụp và tham chiếu giải quyết hai nhu cầu khác nhau.

## 4. Thiết kế URI theo ý nghĩa của quan hệ

### 4.1. URI lồng nhau cho tài nguyên phụ thuộc

Với dòng hàng chỉ tồn tại trong một đơn hàng, có thể dùng:

~~~http
GET    /orders/ord-1042/items
POST   /orders/ord-1042/items
GET    /orders/ord-1042/items/oi-7
PATCH  /orders/ord-1042/items/oi-7
DELETE /orders/ord-1042/items/oi-7
~~~

Trong thiết kế này, URI chuẩn của dòng hàng là:

~~~text
/orders/ord-1042/items/oi-7
~~~

Đường dẫn thể hiện phạm vi nghiệp vụ và cung cấp đủ đầu mối để kiểm tra dòng hàng thuộc đúng đơn hàng.

Điều đó không có nghĩa đường dẫn tự thực thi được ràng buộc. Server phải kiểm tra cặp `orderId` và `itemId`, đồng thời kiểm tra quyền truy cập đơn hàng.

### 4.2. URI độc lập cho tài nguyên được chia sẻ

Sản phẩm và khách hàng có URI riêng:

~~~http
GET /products/prod-8
GET /customers/cus-42
GET /orders/ord-1042
~~~

Nếu muốn liệt kê đơn hàng theo khách hàng, có thể chọn một trong các dạng truy vấn:

~~~http
GET /orders?customerId=cus-42
~~~

hoặc:

~~~http
GET /customers/cus-42/orders
~~~

Dạng thứ hai có thể biểu diễn một tập hợp có quan hệ với khách hàng. Nó **không tự cam kết** rằng xóa khách hàng sẽ xóa các đơn hàng đó. Chính sách vòng đời vẫn cần được mô tả riêng.

Trong ví dụ của bài, API chọn `/orders?customerId=cus-42` để lọc và dùng `/orders/{orderId}` làm URI chuẩn của mỗi đơn hàng.

### 4.3. Chọn một URI chuẩn và tránh chuỗi cha không cần thiết

Không cần đẩy toàn bộ chuỗi tổ chức vào URI:

~~~text
/companies/co-1/branches/br-2/customers/cus-42/orders/ord-1042/items/oi-7/product
~~~

Mỗi cấp bổ sung làm tăng số quan hệ phải kiểm tra và có thể khiến định danh bị phụ thuộc vào các quan hệ có thể thay đổi.

Nếu một tài nguyên có thể chuyển cha, URI độc lập như `/tasks/{taskId}` thường phù hợp hơn việc dùng cha hiện tại làm một phần định danh chuẩn. Quan hệ với cha khi đó có thể nằm trong dữ liệu hoặc một endpoint quản lý quan hệ.

Nếu API cung cấp nhiều đường dẫn đến cùng một tài nguyên, cần thống nhất:

- URI nào xuất hiện trong `self` và `Location`.
- Các đường dẫn có áp dụng cùng quyền và cùng quy tắc cập nhật hay không.
- Cách tránh việc client coi hai URI là hai tài nguyên khác nhau.
- Chính sách cache, chuyển hướng hoặc ngừng hỗ trợ đường dẫn cũ nếu có.

Một thiết kế đơn giản nên bắt đầu với một URI chuẩn cho mỗi tài nguyên.

## 5. Biểu diễn quan hệ trong JSON

Có ba lựa chọn phổ biến: chỉ trả tham chiếu, nhúng dữ liệu, hoặc cung cấp liên kết. Có thể kết hợp chúng theo nhu cầu đọc.

### 5.1. Tham chiếu bằng định danh

~~~json
{
  "id": "ord-1042",
  "status": "DRAFT",
  "customerId": "cus-42"
}
~~~

Ưu điểm là gọn và dễ gửi khi tạo hoặc cập nhật. Đổi lại, client cần biết endpoint tương ứng nếu muốn đọc chi tiết khách hàng.

Định danh không phải bằng chứng quyền truy cập. Khi nhận `customerId`, server phải xác minh khách hàng đó tồn tại và được phép liên kết với đơn hàng trong phạm vi người gọi.

### 5.2. Nhúng một phần dữ liệu liên quan

~~~json
{
  "id": "ord-1042",
  "status": "DRAFT",
  "customer": {
    "id": "cus-42",
    "displayName": "Nguyễn An"
  }
}
~~~

Cách này giảm số request cho màn hình cần tên khách hàng. Hợp đồng cần nói rõ:

- Đây là dữ liệu hiện tại hay bản chụp tại một thời điểm.
- Đây là bản tóm tắt hay toàn bộ tài nguyên khách hàng.
- Client có được cập nhật qua đối tượng nhúng hay chỉ được đọc.
- Khi dữ liệu khách hàng thay đổi, phản hồi đơn hàng và cache của nó được cập nhật như thế nào.

Không nên để client gửi lại toàn bộ phản hồi rồi vô tình cập nhật khách hàng qua đơn hàng. Tách DTO đầu vào và đầu ra giúp giới hạn rõ các trường có thể ghi.

### 5.3. Liên kết đến tài nguyên liên quan

Ví dụ một biểu diễn đơn hàng:

~~~json
{
  "id": "ord-1042",
  "status": "DRAFT",
  "customerId": "cus-42",
  "links": {
    "self": {
      "href": "/orders/ord-1042"
    },
    "customer": {
      "href": "/customers/cus-42"
    },
    "items": {
      "href": "/orders/ord-1042/items"
    }
  }
}
~~~

Các URI bắt đầu bằng `/` là tham chiếu tương đối theo gốc của API. Khi triển khai dưới một base path hoặc qua gateway, server và client cần dùng quy tắc phân giải URI nhất quán.

Trường `links` cùng cấu trúc `href` ở đây là **quy ước JSON do API lựa chọn**. HTTP không tự định nghĩa ý nghĩa của cấu trúc này. API cần mô tả rõ hoặc chọn một định dạng hypermedia có quy ước tương ứng.

Một liên kết đọc đến khách hàng không mô tả đầy đủ quyền sửa khách hàng. Muốn client khám phá thao tác có thể thực hiện theo trạng thái hiện tại, hợp đồng còn phải mô tả phương thức, dữ liệu đầu vào và điều kiện của thao tác đó.

### 5.4. Chọn biểu diễn theo nhu cầu

| Cách biểu diễn | Phù hợp khi | Điều cần kiểm soát |
| --- | --- | --- |
| Chỉ định danh | Ghi dữ liệu hoặc phản hồi cần gọn | Client cần quy tắc tìm tài nguyên liên quan |
| Tóm tắt nhúng | Màn hình cần vài trường để hiển thị | Tính hiện thời, kích thước và quyền đọc các trường |
| Liên kết | Client cần điều hướng qua quan hệ | Ý nghĩa quan hệ và cách phân giải URI |
| Nhúng đầy đủ | Dữ liệu nhỏ, giới hạn rõ, nhu cầu đọc cụ thể | Đệ quy, dữ liệu nhạy cảm, chi phí và cache |

Nhúng tài nguyên không làm thay đổi vòng đời của nó. Sản phẩm vẫn độc lập với dòng hàng dù phản hồi dòng hàng chứa tên sản phẩm.

## 6. Tham chiếu hiện tại và bản chụp lịch sử

Dòng hàng có thể lưu cả định danh sản phẩm và thông tin đã chốt:

~~~json
{
  "id": "oi-7",
  "productId": "prod-8",
  "productSnapshot": {
    "name": "Bàn phím cơ",
    "sku": "KB-008"
  },
  "quantity": 2,
  "unitPrice": {
    "amount": "1250000",
    "currency": "VND"
  },
  "links": {
    "self": {
      "href": "/orders/ord-1042/items/oi-7"
    },
    "product": {
      "href": "/products/prod-8"
    }
  }
}
~~~

Trong hợp đồng minh họa:

- `productId` nhận diện sản phẩm liên quan.
- `productSnapshot` là thông tin sản phẩm tại lúc xác nhận đơn.
- `unitPrice` là đơn giá đã chốt, không tự thay đổi theo giá danh mục.
- Liên kết `product` dùng để truy cập tài nguyên hiện tại nếu người gọi có quyền và sản phẩm còn khả dụng.

API cần định nghĩa dữ liệu trước lúc xác nhận đơn: có thể là giá tạm tính, giá đã báo hoặc chưa có snapshot. Đừng dùng cùng một trường với ý nghĩa thay đổi ngầm giữa các trạng thái.

Nếu sản phẩm ngừng bán hoặc không còn khả dụng qua API, bản chụp vẫn giúp giải thích đơn hàng cũ. Khi đó cần chọn chính sách rõ cho tham chiếu, chẳng hạn giữ sản phẩm ở trạng thái ngừng hoạt động hoặc cho phép liên kết không còn truy cập được nhưng vẫn giữ thông tin lịch sử.

Không giả định mọi liên kết trả về đều có thể truy cập mãi mãi. Tài nguyên, trạng thái và quyền của người dùng đều có thể thay đổi sau thời điểm nhận phản hồi.

## 7. Tạo và cập nhật quan hệ

### 7.1. Tạo tài nguyên con thuộc sở hữu

~~~http
POST /orders/ord-1042/items
Content-Type: application/json

{
  "productId": "prod-8",
  "quantity": 2
}
~~~

Server cần kiểm tra:

1. Người gọi được phép sửa đơn `ord-1042`.
2. Đơn đang ở trạng thái cho phép thêm dòng hàng.
3. Sản phẩm tồn tại, khả dụng và được phép sử dụng trong phạm vi đơn hàng.
4. Số lượng hợp lệ và các ràng buộc nghiệp vụ khác được thỏa mãn.
5. Dòng hàng được gắn với chính đơn trong URI; client không được thay cha qua body.

Phản hồi khi tạo thành công:

~~~http
HTTP/1.1 201 Created
Location: /orders/ord-1042/items/oi-7
Content-Type: application/json

{
  "id": "oi-7",
  "productId": "prod-8",
  "quantity": 2,
  "links": {
    "self": {
      "href": "/orders/ord-1042/items/oi-7"
    }
  }
}
~~~

`POST` tạo dòng hàng không mặc nhiên idempotent. Nếu client gửi lại khi mất phản hồi, có thể phát sinh hai dòng hàng. Với luồng cần chống tạo trùng, thiết kế cơ chế khử trùng request hoặc hợp đồng idempotency riêng; ràng buộc quan hệ không tự giải quyết việc gửi lại.

### 7.2. Đặt một quan hệ tham chiếu đơn

Có thể mô hình hóa khách hàng của đơn hàng thành một tài nguyên quan hệ:

~~~http
PUT /orders/ord-1042/customer
Content-Type: application/json

{
  "customerId": "cus-42"
}
~~~

Ở đây, endpoint đại diện cho **quan hệ khách hàng của đơn hàng**, không phải tài nguyên khách hàng. Request thay thế toàn bộ trạng thái của quan hệ đơn này.

Theo hợp đồng minh họa:

- Khi quan hệ chưa có và được tạo thành công, trả `201 Created` cùng `Location: /orders/ord-1042/customer`.
- Khi thay thế một quan hệ đã có, trả `204 No Content`; cũng có thể thiết kế `200 OK` nếu cần trả biểu diễn.
- Gửi lại cùng một `PUT` có cùng hiệu ứng mong muốn đối với quan hệ, dù mã phản hồi lần đầu và lần sau có thể khác.
- Chỉ đơn nháp được đổi khách hàng.
- Endpoint không sửa tên, email hoặc địa chỉ hồ sơ của khách hàng.

Nếu đổi khách hàng kéo theo tính lại giá, địa chỉ mặc định hoặc điều kiện thanh toán, phải mô tả các tác động này. Tính idempotent không có nghĩa là bỏ qua tác động nghiệp vụ; nó yêu cầu tránh lặp các tác động ngoài ý muốn khi cùng yêu cầu được gửi lại.

Một lựa chọn khác là cập nhật `customerId` qua `PATCH /orders/{orderId}`. Nếu hỗ trợ cả hai cách, chúng phải đi qua cùng quy tắc nghiệp vụ và cơ chế kiểm soát đồng thời.

### 7.3. Bỏ liên kết khác với xóa tài nguyên đích

~~~http
DELETE /orders/ord-1042/customer
~~~

Trong ví dụ này, thao tác chỉ bỏ quan hệ khách hàng của đơn nháp. Nó không xóa `/customers/cus-42`.

API có thể quy định trả `204 No Content` khi đơn tồn tại và quan hệ vốn đã trống. Nếu chọn phản hồi khác cho quan hệ không tồn tại, cần mô tả nhất quán. Tính idempotent của `DELETE` nói về hiệu ứng mong muốn, không bắt buộc mọi lần gọi phải có cùng mã phản hồi.

Với đơn đã xác nhận, việc bỏ khách hàng vi phạm quy tắc trạng thái, nên API minh họa trả `409 Conflict`.

### 7.4. Phân biệt trường bị bỏ qua và giá trị null

Đối với cập nhật một phần, phải xác định rõ định dạng patch. Ví dụ dùng JSON Merge Patch:

~~~http
PATCH /orders/ord-1042
Content-Type: application/merge-patch+json

{
  "customerId": null
}
~~~

Với JSON Merge Patch, `null` yêu cầu loại bỏ thành viên tương ứng khỏi biểu diễn đích. API có thể ánh xạ việc đó thành bỏ quan hệ khách hàng nếu quy tắc nghiệp vụ cho phép. Không gửi trường `customerId` thì giữ nguyên quan hệ.

Nếu dùng `application/json` với một DTO cập nhật tự thiết kế, không được mặc nhiên suy ra cùng ngữ nghĩa. Phải tài liệu hóa cách phân biệt “không được gửi”, “gửi null” và “gửi định danh mới”.

JSON Merge Patch cũng thay thế cả mảng khi mảng được gửi lên; nó không tự hiểu rằng từng phần tử của `items` là một tài nguyên cần được đối chiếu theo ID. Với tập dòng hàng, endpoint cho từng dòng thường làm rõ ý định hơn.

## 8. Quan hệ nhiều-nhiều có thuộc tính riêng

Xét người dùng và dự án. Một người có thể tham gia nhiều dự án; mỗi lần tham gia có vai trò, thời điểm bắt đầu và trạng thái riêng.

Khi quan hệ có dữ liệu và vòng đời đáng kể, có thể đưa nó thành tài nguyên:

~~~http
POST   /projects/prj-1/memberships
GET    /projects/prj-1/memberships
GET    /projects/prj-1/memberships/mem-9
PATCH  /projects/prj-1/memberships/mem-9
DELETE /projects/prj-1/memberships/mem-9
~~~

~~~json
{
  "id": "mem-9",
  "userId": "usr-3",
  "role": "EDITOR",
  "status": "ACTIVE",
  "joinedAt": "2026-01-10T08:30:00Z",
  "links": {
    "self": {
      "href": "/projects/prj-1/memberships/mem-9"
    },
    "user": {
      "href": "/users/usr-3"
    }
  }
}
~~~

Ở mô hình này:

- Dự án sở hữu tài nguyên thành viên theo vòng đời đã chọn.
- Thành viên tham chiếu một người dùng độc lập.
- Xóa thành viên không xóa người dùng.
- Nếu chỉ cho phép một thành viên đang hoạt động cho mỗi cặp dự án/người dùng, server phải thực thi ràng buộc đó.
- Nếu cần lưu lịch sử tham gia lại, phải xác định tái kích hoạt thành viên cũ hay tạo một lần tham gia mới.

Không cần thêm ID quan hệ trong mọi trường hợp. Với quan hệ chỉ cần có/không và một cặp định danh đã xác định duy nhất quan hệ, có thể dùng:

~~~http
PUT    /projects/prj-1/members/usr-3
DELETE /projects/prj-1/members/usr-3
~~~

Hai thiết kế phục vụ hai hợp đồng khác nhau. Hãy chọn theo định danh, dữ liệu và lịch sử của quan hệ, thay vì chỉ phản chiếu bảng nối trong cơ sở dữ liệu.

## 9. Xóa tài nguyên và tính toàn vẹn của quan hệ

Cần phân biệt ít nhất ba thao tác:

| Thao tác | Tác động được thiết kế trong ví dụ |
| --- | --- |
| Xóa dòng hàng của đơn nháp | Dòng hàng không còn khả dụng; sản phẩm vẫn tồn tại |
| Bỏ khách hàng khỏi đơn nháp | Quan hệ bị bỏ; khách hàng và đơn hàng vẫn tồn tại |
| Xóa khách hàng đang được đơn tham chiếu | Phụ thuộc chính sách đã công bố; không suy ra từ hai thao tác trên |

Một số chính sách phổ biến cho tài nguyên đích đang được tham chiếu:

| Chính sách | Khi phù hợp | Hệ quả phải nêu rõ |
| --- | --- | --- |
| Chặn xóa | Tham chiếu cần luôn hợp lệ | Client phải xử lý các quan hệ trước; có thể trả `409 Conflict` |
| Vô hiệu hóa | Cần ngừng sử dụng mới nhưng vẫn đọc lịch sử | Tách rõ “không hoạt động” với “không tồn tại” |
| Bỏ tham chiếu | Quan hệ thực sự tùy chọn | Dữ liệu còn lại phải tự giải thích được |
| Giữ bản chụp | Giao dịch cần thông tin tại thời điểm xảy ra | Bản chụp không phải dữ liệu hiện tại của tài nguyên đích |
| Xóa lan truyền | Con phụ thuộc thật sự và chính sách cho phép | Không được lan sang tài nguyên dùng chung ngoài phạm vi sở hữu |

Các chính sách có thể kết hợp. Ví dụ vô hiệu hóa sản phẩm và giữ snapshot trong đơn hàng.

Đối với đơn nháp và dòng hàng, “xóa lan truyền” ở hợp đồng API có nghĩa sau thao tác xóa thành công, các dòng hàng của đơn đó không còn khả dụng theo quy tắc đã công bố. Nó không bắt buộc cơ sở dữ liệu phải xóa vật lý mọi hàng ngay lập tức.

Đừng suy ra cascade từ URI lồng nhau, và đừng suy ra quyền xóa API từ `CascadeType.REMOVE` hoặc `orphanRemoval`. Các cấu hình lưu trữ phải phục vụ chính sách nghiệp vụ đã chọn.

## 10. Phân quyền, trạng thái và cập nhật đồng thời

### 10.1. Kiểm tra cả tài nguyên nguồn lẫn tài nguyên đích

Với request:

~~~http
PUT /orders/ord-1042/customer

{
  "customerId": "cus-99"
}
~~~

Chỉ kiểm tra quyền sửa đơn là chưa đủ. Server còn phải xác minh `cus-99` được phép liên kết trong phạm vi đơn và người gọi.

Trong hệ thống nhiều tổ chức, một định danh hợp lệ của tổ chức khác vẫn có thể là một tham chiếu không được phép. Không lấy tenant hoặc tổ chức có thẩm quyền trực tiếp từ một trường do client tùy ý gửi.

Endpoint lồng nhau cũng cần chống trường hợp:

~~~http
DELETE /orders/ord-1042/items/oi-from-another-order
~~~

Server phải tìm dòng hàng theo cả cha và con trong phạm vi được phép, không chỉ gọi `findById(itemId)` rồi xóa.

### 10.2. Thay quan hệ phải tôn trọng trạng thái nghiệp vụ

Giữa lúc client đọc đơn nháp và gửi cập nhật, một request khác có thể đã xác nhận đơn.

Do đó, kiểm tra trạng thái cần diễn ra trong thao tác ghi có kiểm soát đồng thời. Có thể dùng khóa, phiên bản lạc quan hoặc cập nhật có điều kiện, tùy kiến trúc. Chỉ kiểm tra ở giao diện hoặc controller trước khi ghi không đảm bảo được bất biến.

Nếu API dùng điều kiện HTTP như `If-Match`, cần trả và kiểm tra validator theo đúng tài nguyên được nhắm tới. ETag của `/orders/ord-1042` không tự trở thành ETag của `/orders/ord-1042/customer`.

Khi điều kiện `If-Match` không thỏa mãn, dùng `412 Precondition Failed`. Xung đột với trạng thái nghiệp vụ như “đơn đã xác nhận” có thể dùng `409 Conflict`. Hai trường hợp cần được phân biệt trong hợp đồng lỗi.

### 10.3. Giữ bất biến trong một lần thay đổi

Trong cùng một cơ sở dữ liệu, việc kiểm tra và ghi quan hệ thường cần một giao dịch, kết hợp cơ chế chống tranh chấp phù hợp. Giao dịch đơn thuần không thay thế khóa, phiên bản hoặc ràng buộc duy nhất khi có các request đồng thời.

Ví dụ với thành viên dự án, kiểm tra “chưa có thành viên” rồi insert ở hai request song song vẫn có thể tạo trùng. Một ràng buộc duy nhất phù hợp với quy tắc miền giúp chặn lỗi ở nơi lưu trữ.

Nếu tài nguyên đích do dịch vụ khác quản lý, không thể mặc nhiên có giao dịch ACID bao trùm hai dịch vụ. Phải xác định cách xác minh tham chiếu, xử lý trạng thái thay đổi và khôi phục khi một bước thất bại.

## 11. Ví dụ ánh xạ vào Java/Spring

Đoạn mã sau minh họa ranh giới HTTP để gắn hoặc bỏ khách hàng của đơn hàng. Đây là phần khung của lớp API; lớp `OrderRelationshipService` và ánh xạ lỗi phải được triển khai theo nghiệp vụ và cơ chế lưu trữ cụ thể.

~~~java
import java.net.URI;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

@RestController
@RequestMapping("/orders/{orderId}/customer")
public class OrderCustomerController {

    private final OrderRelationshipService relationships;

    public OrderCustomerController(OrderRelationshipService relationships) {
        this.relationships = relationships;
    }

    @PutMapping
    public ResponseEntity<Void> replace(
            @PathVariable("orderId") String orderId,
            @Valid @RequestBody ReplaceCustomerRequest request,
            Authentication authentication) {

        LinkChange result = relationships.setCustomer(
                authentication, orderId, request.customerId());

        if (result.created()) {
            URI location = UriComponentsBuilder
                    .fromPath("/orders/{orderId}/customer")
                    .buildAndExpand(orderId)
                    .encode()
                    .toUri();

            return ResponseEntity.created(location).build();
        }

        return ResponseEntity.noContent().build();
    }

    @DeleteMapping
    public ResponseEntity<Void> remove(
            @PathVariable("orderId") String orderId,
            Authentication authentication) {

        relationships.removeCustomer(authentication, orderId);
        return ResponseEntity.noContent().build();
    }

    public record ReplaceCustomerRequest(
            @NotBlank String customerId) {
    }

    public record LinkChange(boolean created) {
    }

    public interface OrderRelationshipService {
        LinkChange setCustomer(
                Authentication caller, String orderId, String customerId);

        void removeCustomer(
                Authentication caller, String orderId);
    }
}
~~~

Ví dụ giả định dự án đã cấu hình Spring Web, Spring Security và Jakarta Bean Validation phù hợp; request đã đi qua bước xác thực. `Authentication` cung cấp đầu mối nhận diện người gọi, còn quy tắc quyền cụ thể phải được kiểm tra trong luồng nghiệp vụ.

`@NotBlank` chỉ kiểm tra hình dạng dữ liệu. Nó không xác minh khách hàng có tồn tại, cùng tổ chức hoặc được phép gắn vào đơn.

Trách nhiệm của `setCustomer` gồm:

1. Xác định phạm vi truy cập từ danh tính đã xác thực.
2. Tìm đơn trong phạm vi đó và kiểm tra quyền sửa.
3. Kiểm tra đơn còn ở trạng thái nháp.
4. Tìm khách hàng được phép liên kết, kiểm tra khả dụng.
5. Thay quan hệ và các dữ liệu phụ thuộc theo chính sách đã công bố.
6. Bảo vệ toàn bộ thay đổi khỏi tranh chấp và trả đúng việc quan hệ vừa được tạo hay đã tồn tại.

`removeCustomer` thực hiện quy trình tương tự, nhưng chỉ bỏ liên kết. Nó không gọi thao tác xóa khách hàng.

Ví dụ cố ý không bind body vào JPA entity. Nếu nhận một đồ thị entity và bật cascade tùy tiện, một request “đổi khách hàng của đơn” có thể kéo theo cập nhật ngoài ý muốn trên tài nguyên khách hàng.

### 11.1. Hợp đồng lỗi cho quan hệ

| Tình huống | Lựa chọn trong API minh họa |
| --- | --- |
| Body thiếu `customerId` hoặc chứa chuỗi trống | `400 Bad Request` |
| Người gọi chưa xác thực | `401 Unauthorized` |
| Không được phép thực hiện thao tác | `403 Forbidden`, hoặc `404` nếu chính sách che giấu sự tồn tại yêu cầu |
| Không tìm thấy đơn hoặc khách hàng trong phạm vi được phép | `404 Not Found` |
| Đơn đã xác nhận nên không thể đổi quan hệ | `409 Conflict` |
| Không thỏa mãn điều kiện `If-Match` nếu endpoint hỗ trợ | `412 Precondition Failed` |

Đây là các lựa chọn hợp đồng, không phải một ánh xạ duy nhất cho mọi API. Cần mô tả phân biệt lỗi cú pháp, tham chiếu không hợp lệ và xung đột nghiệp vụ, đồng thời giữ nhất quán giữa các endpoint.

Phản hồi lỗi nên có mã lỗi ổn định để client xử lý, chẳng hạn `ORDER_CUSTOMER_CHANGE_NOT_ALLOWED`, thay vì buộc client phân tích thông báo tiếng Việt. Không đưa chi tiết về tài nguyên ngoài quyền truy cập vào thông báo lỗi.

## 12. Ghi rõ quan hệ trong OpenAPI và tài liệu

Một trường `customerId: string` chưa đủ mô tả quan hệ. Hợp đồng tối thiểu cần nêu:

- Tham chiếu đến loại tài nguyên nào và định dạng định danh.
- Khi nào quan hệ bắt buộc, tùy chọn hoặc bất biến.
- Ý nghĩa của việc bỏ trường hoặc gửi `null` theo từng loại request.
- Endpoint dùng để đọc, thay hoặc bỏ quan hệ.
- Hành vi khi tài nguyên đích không tồn tại, không khả dụng hoặc không được phép truy cập.
- Hành vi xóa và ảnh hưởng đến dữ liệu lịch sử.
- Dữ liệu nhúng là hiện tại, bản tóm tắt hay bản chụp.
- URI chuẩn và các quan hệ liên kết mà client có thể sử dụng.

Ví dụ một phần khai báo schema OpenAPI; đoạn này cần được đặt trong một tài liệu OpenAPI hoàn chỉnh:

~~~yaml
components:
  schemas:
    ReplaceOrderCustomerRequest:
      type: object
      additionalProperties: false
      required:
        - customerId
      properties:
        customerId:
          type: string
          minLength: 1
          description: >-
            Định danh khách hàng được phép liên kết với đơn hàng.
            Chỉ thay đổi khi đơn còn ở trạng thái DRAFT.
            Request này không cập nhật dữ liệu hồ sơ khách hàng.
          example: cus-42

    OrderRelationshipLinks:
      type: object
      readOnly: true
      properties:
        customer:
          type: object
          description: >-
            Liên kết đọc tài nguyên khách hàng hiện được tham chiếu.
            Không có trường này khi đơn chưa gắn khách hàng.
          required:
            - href
          properties:
            href:
              type: string
              format: uri-reference
              example: /customers/cus-42
~~~

Nếu schema khai báo `additionalProperties: false`, bộ xử lý đầu vào cũng cần có chính sách từ chối trường lạ tương ứng. Khai báo trong tài liệu không tự cấu hình hành vi deserialize của Spring/Jackson.

Trong OpenAPI, `$ref` trỏ đến một thành phần mô tả như schema dùng lại. Nó không tự kiểm tra rằng giá trị `cus-42` tồn tại ở runtime và không thay thế khóa ngoại hay kiểm tra nghiệp vụ.

Tương tự, OpenAPI Link Object mô tả quan hệ giữa các operation trong tài liệu. Nó không tự thêm trường `links` vào phản hồi JSON của server.

## 13. Các bẫy khi triển khai biểu diễn quan hệ

### 13.1. Serialize trực tiếp đồ thị hai chiều

Nếu `Order` chứa danh sách `OrderItem` và mỗi `OrderItem` lại chứa `Order`, serialize trực tiếp có thể gây vòng lặp, phản hồi quá lớn hoặc truy vấn ngoài dự kiến.

Thiết kế DTO theo nhu cầu của tài nguyên đang trả về:

- Đơn hàng trả thông tin đơn và liên kết đến dòng hàng.
- Dòng hàng trả định danh sản phẩm, dữ liệu cần hiển thị và liên kết liên quan.
- Tránh nhúng ngược toàn bộ đơn hàng trong mỗi dòng hàng.

Quy tắc này cũng giúp tránh lộ trường nội bộ hoặc dữ liệu nhạy cảm của khách hàng.

### 13.2. Nhúng một tập hợp không giới hạn

Một đơn có ít dòng hàng có thể trả kèm toàn bộ dòng. Một dự án có hàng chục nghìn thành viên cần endpoint tập hợp riêng với phân trang.

Nếu nhúng một phần tập hợp, phải nói rõ đó chỉ là phần đã lấy và cung cấp cách lấy tiếp. Không trả mười phần tử trong `members` rồi để client hiểu đó là toàn bộ thành viên.

### 13.3. Quên chi phí truy vấn và cache

Nhúng khách hàng hoặc sản phẩm có thể tạo truy vấn N+1 nếu mỗi phần tử lại tải một tài nguyên liên quan. DTO gọn vẫn cần chiến lược truy vấn phù hợp, chẳng hạn lấy theo lô hoặc projection.

Nếu phản hồi đơn hàng chứa tên hiện tại của khách hàng, thay đổi tên có thể làm biểu diễn đơn hàng thay đổi. Validator và cache phải xét các dữ liệu tham gia biểu diễn, hoặc API phải công bố một chính sách làm mới phù hợp.

Nếu phản hồi chỉ chứa `customerId` và liên kết ổn định, thay đổi tên khách hàng không nhất thiết làm biểu diễn đó thay đổi. Dù chọn cách nào, vẫn phải tách cache theo phạm vi xác thực và quyền xem dữ liệu phù hợp.

### 13.4. Đồng bộ hai chiều bằng hai lần cập nhật từ client

Không nên yêu cầu client vừa cập nhật `order.customerId`, vừa cập nhật danh sách `customer.orderIds` để duy trì cùng một quan hệ. Nếu một request thất bại, hai biểu diễn sẽ mâu thuẫn.

Hãy chọn một thao tác có thẩm quyền thay đổi quan hệ. Các tập hợp nhìn từ phía ngược lại được server suy ra hoặc đồng bộ theo cơ chế đã thiết kế.

## 14. Tình huống tự kiểm tra khi thiết kế

Các tình huống sau là đầu vào để xây dựng kiểm thử API; bài học không giả định mã khung phía trên đã thực thi chúng.

| Tình huống | Kết quả cần xác minh |
| --- | --- |
| Thêm dòng hàng hợp lệ vào đơn nháp | Tạo đúng một tài nguyên con cho mỗi request được chấp nhận; trả URI chuẩn |
| Dùng item của đơn khác trong URI hiện tại | Không đọc, sửa hoặc xóa được item đó |
| Bỏ khách hàng của đơn nháp | Đơn và khách hàng vẫn tồn tại; quan hệ trống |
| Gửi lại cùng một PUT gắn khách hàng | Quan hệ cuối cùng giống nhau, không tạo thêm khách hàng hoặc tác động nghiệp vụ bị lặp |
| Đổi khách hàng của đơn đã xác nhận | Thất bại theo hợp đồng; dữ liệu không bị thay một phần |
| Gắn khách hàng ngoài phạm vi tổ chức | Bị từ chối mà không lộ dữ liệu không được phép |
| Xóa dòng hàng | Sản phẩm dùng chung vẫn tồn tại |
| Xóa đơn nháp | Không còn truy cập các dòng hàng của đơn theo chính sách xóa |
| Cập nhật giá hoặc tên sản phẩm sau khi đơn đã chốt | Bản chụp và đơn giá của đơn cũ giữ đúng giá trị đã chốt |
| Hai request tạo cùng quan hệ thành viên | Không vi phạm ràng buộc duy nhất đã chọn |
| Có cập nhật đồng thời với xác nhận đơn | Không làm lọt thay đổi bị cấm sau khi xác nhận |
| Phản hồi có liên kết đến tài nguyên hạn chế quyền | Gọi liên kết vẫn phải qua kiểm tra quyền độc lập |
| Tập hợp có nhiều phần tử | Phân trang không bị nhầm thành toàn bộ tập hợp |
| Thay đổi dữ liệu đang được nhúng | Cache và validator tuân theo chính sách biểu diễn đã công bố |

Không chỉ kiểm tra mã HTTP. Cần kiểm tra cả trạng thái sau thao tác: tài nguyên nào còn tồn tại, quan hệ nào đã thay đổi và dữ liệu độc lập nào phải được giữ nguyên.

## 15. Bài tập thiết kế

Thiết kế một API dự án với người dùng, công việc, bình luận và thành viên. Giả sử:

- Người dùng tồn tại độc lập với dự án.
- Công việc có thể chuyển từ dự án này sang dự án khác.
- Bình luận chỉ tồn tại trong một công việc theo chính sách đã chọn.
- Thành viên dự án có vai trò và trạng thái riêng.

Hãy viết:

1. Bảng quan hệ, bao gồm số lượng, vòng đời và quy tắc xóa.
2. URI chuẩn của từng tài nguyên, đặc biệt là công việc có thể chuyển dự án.
3. Một phản hồi công việc có người được giao, liên kết bình luận và liên kết dự án.
4. Hợp đồng thay người được giao và bỏ người được giao.
5. Điều kiện để chuyển công việc sang dự án khác.
6. Cách xử lý nếu người được giao không còn là thành viên của dự án đích.
7. Các tình huống kiểm thử để ngăn việc sửa tài nguyên con qua sai cha.

Một hướng giải thích hợp là dùng `/tasks/{taskId}` làm URI chuẩn cho công việc, dùng quan hệ hoặc trường cập nhật để chuyển dự án, và kiểm tra lại điều kiện của người được giao trong cùng luồng thay đổi. Bình luận có thể dùng `/tasks/{taskId}/comments/{commentId}` nếu vòng đời thực sự phụ thuộc công việc.

Điểm cần giải thích là vì sao mỗi URI và thao tác phản ánh đúng vòng đời, quyền truy cập và bất biến nghiệp vụ. Chất lượng mô hình quan hệ thể hiện ở việc client hiểu được tác động của thao tác, còn server giữ được các ràng buộc đó khi dữ liệu và trạng thái thay đổi.
