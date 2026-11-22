# Quy ước đặt tên path, danh từ và tính nhất quán

Một API có thể trả đúng dữ liệu nhưng vẫn khó sử dụng nếu cùng một ý nghĩa lại xuất hiện dưới nhiều tên: `/getOrders`, `/order-list`, `/customers/42/order` và `/OrderDetails/9001`. Người dùng API phải nhớ ngoại lệ cho từng endpoint; nhóm phát triển cũng khó mở rộng hợp đồng mà không tạo thêm cách đặt tên mới.

Trong chương **Thiết kế URI** của module **INTEGRATION_API_REST**, bài này tập trung vào cách đặt tên path để người đọc nhận ra resource, tập hợp resource và quan hệ giữa chúng. Các ví dụ dùng API quản lý đơn hàng, có thể triển khai bằng Java/Spring hoặc công nghệ tương đương. Mục tiêu là tạo một hợp đồng dễ hiểu và ổn định, làm nền cho tài liệu OpenAPI, phân quyền và kiểm thử API.

Sau bài học, bạn có thể:

- Phân biệt phần path với các phần khác của URI, đồng thời xác định vai trò của từng segment.
- Chọn danh từ, số nhiều, dấu phân cách và tên tham số theo một quy ước thống nhất.
- Biểu diễn collection, resource đơn, singleton và quan hệ lồng nhau.
- Phân biệt thay đổi tên endpoint với thay đổi mô hình resource.
- Đánh giá một thiết kế URI bằng tiêu chí cụ thể và đưa nó vào hợp đồng Java/Spring.

## 1. Path là một phần của hợp đồng API

Xét một URI ví dụ:

```text
https://api.example.com/api/v1/orders/ord_9001/items?status=available
```

Trong ví dụ này:

- `https` là scheme.
- `api.example.com` là host trong authority.
- `/api/v1/orders/ord_9001/items` là path.
- `status=available` là query.

Path gồm các segment được ngăn cách bằng `/`: `api`, `v1`, `orders`, `ord_9001`, `items`. Các segment không bắt buộc phải ánh xạ thành thư mục trên máy chủ hoặc bảng trong cơ sở dữ liệu.

Bài học sử dụng base path `/api/v1` như một lựa chọn đã thống nhất cho API ví dụ. Các bảng ngắn bên dưới thường lược bỏ base path để dễ đọc. Đặt phiên bản trong path là một chiến lược quản lý phiên bản; đây không phải yêu cầu bắt buộc của REST.

Trong thiết kế thường gặp:

```text
/orders                       tập hợp đơn hàng
/orders/ord_9001              một đơn hàng
/orders/ord_9001/items        tập hợp dòng hàng của đơn hàng đó
```

Query thường thể hiện bộ lọc, cách sắp xếp hoặc phân trang:

```http
GET /api/v1/orders?status=paid&page=0&size=20
```

Không nên suy ra rằng query không tham gia định danh. URI đầy đủ bao gồm cả query; hai URI có query khác nhau có thể định danh hai tập kết quả khác nhau. Quy ước thực dụng ở đây là dùng path để diễn đạt cấu trúc resource và dùng query cho các biến thể truy vấn collection.

### 1.1. Resource không đồng nghĩa với bản ghi dữ liệu

Resource là khái niệm mà API cho phép client tham chiếu và tương tác. Một resource có thể là:

- Đơn hàng được tổng hợp từ nhiều bảng.
- Collection các sản phẩm có thể mua.
- Giỏ hàng hiện tại của người dùng.
- Một yêu cầu xuất báo cáo đang được xử lý.
- Một bản tóm tắt được tính toán từ dữ liệu khác.

Vì vậy, việc có các bảng `order_header`, `order_detail` và `order_status_history` không buộc API phải công bố các tên tương ứng. API có thể cung cấp `/orders`, `/orders/{orderId}/items` và `/orders/{orderId}/status-events` nếu đó là các khái niệm phù hợp với người sử dụng.

Tên resource nên thuộc ngôn ngữ nghiệp vụ. Tránh để tên lớp Java, framework hay thủ tục lưu trữ trở thành hợp đồng công khai như `/OrderController`, `/orderService` hoặc `/spGetOrder`.

### 1.2. HTTP method và path đảm nhiệm các vai trò khác nhau

Path giúp xác định resource đích; HTTP method thể hiện cách tương tác với resource đó. Vì vậy, nhiều thao tác có thể dùng chung một path:

| Mục đích | Method và path | Ý nghĩa của tên path |
| --- | --- | --- |
| Liệt kê đơn hàng | `GET /orders` | Collection đơn hàng |
| Tạo đơn hàng | `POST /orders` | Gửi dữ liệu vào collection theo hợp đồng tạo mới |
| Đọc một đơn hàng | `GET /orders/{orderId}` | Một đơn hàng xác định |
| Cập nhật một phần | `PATCH /orders/{orderId}` | Tác động lên đơn hàng đã xác định |
| Đọc các dòng hàng | `GET /orders/{orderId}/items` | Collection thuộc đơn hàng |

API phải định nghĩa riêng phương thức nào được hỗ trợ và điều kiện nghiệp vụ của từng phương thức. Không phải mọi resource đều cần đủ `GET`, `POST`, `PUT`, `PATCH`, `DELETE`. Đặc biệt, xóa một đơn hàng và hủy một đơn hàng là hai nghiệp vụ khác nhau.

## 2. Ưu tiên danh từ thể hiện resource

Một quy ước dễ áp dụng là đặt tên các segment cố định theo danh từ:

```text
/orders
/customers
/products
/shipping-addresses
```

So sánh hai cách diễn đạt:

| Thiết kế dễ gây khó nhớ | Thiết kế theo resource | Điều được cải thiện |
| --- | --- | --- |
| `GET /getOrders` | `GET /orders` | Method đã thể hiện thao tác đọc |
| `POST /createOrder` | `POST /orders` | Tạo mới qua collection |
| `GET /getOrderById?id=ord_9001` | `GET /orders/ord_9001` | ID nằm cạnh tên loại resource |
| `PATCH /updateOrder/ord_9001` | `PATCH /orders/ord_9001` | Một địa chỉ cho đơn hàng qua nhiều method |
| `GET /listOrderItems/ord_9001` | `GET /orders/ord_9001/items` | Quan hệ giữa đơn hàng và dòng hàng rõ ràng |

Đây là quy ước thiết kế hữu ích, không phải quy định cú pháp URI hay phép kiểm tra đầy đủ để chứng minh một API là REST. Một path chứa toàn danh từ vẫn có thể mô hình hóa sai nghiệp vụ, dùng sai HTTP method hoặc thiếu kiểm soát truy cập.

### 2.1. Chọn danh từ đúng với miền nghiệp vụ

Đừng chỉ bỏ động từ khỏi tên cũ. Trước tiên, hãy xác định client đang làm việc với đối tượng nào.

Ví dụ, chức năng “xuất báo cáo” có thể tạo một công việc chạy bất đồng bộ. Resource phù hợp là một yêu cầu xuất báo cáo có vòng đời:

```http
POST /api/v1/report-exports
Content-Type: application/json

{
  "reportType": "monthly-sales",
  "month": "2026-10"
}
```

Sau khi được chấp nhận, client có thể nhận địa chỉ để theo dõi công việc:

```http
GET /api/v1/report-exports/exp_127
```

Tên `report-exports` có ích vì công việc thực sự có ID, trạng thái và kết quả. Nếu hệ thống chỉ ghép động từ thành một danh từ giả mà không có resource hoặc hợp đồng tương ứng, thiết kế chưa chắc đã dễ hiểu hơn.

### 2.2. Có phải cấm mọi động từ trong path?

Không. Một số API có thao tác miền nghiệp vụ khó diễn đạt tự nhiên như CRUD. Điều quan trọng là mô hình và quy ước phải nhất quán, có chủ đích.

Với “hủy đơn hàng”, có thể cân nhắc:

| Cách mô hình hóa | Ví dụ | Khi phù hợp |
| --- | --- | --- |
| Tạo một yêu cầu hủy | `POST /orders/{orderId}/cancellations` | Yêu cầu có lý do, thời điểm, người yêu cầu và trạng thái riêng |
| Thay đổi trạng thái của đơn hàng | `PATCH /orders/{orderId}` với body đã định nghĩa | Trạng thái là thuộc tính được phép cập nhật và có kiểm soát chuyển trạng thái |
| Một thao tác rõ nghĩa trong miền | `POST /orders/{orderId}/cancel` | Hợp đồng chủ động chọn kiểu action cho thao tác này |

Không chọn tên `cancellations` chỉ để tránh từ `cancel`. Hãy chọn dựa vào mô hình nghiệp vụ. Nếu dùng action, cần quy ước thống nhất về tên, HTTP method, trạng thái kết quả, xử lý gửi lặp và quyền thực hiện. Không dùng `GET` để kích hoạt việc hủy đơn hàng.

Trong phần còn lại của bài học, API ví dụ ưu tiên resource; khi một yêu cầu hủy có vòng đời riêng, nó được mô hình hóa bằng collection `cancellations`.

## 3. Số nhiều cho collection, ngoại lệ rõ ràng cho singleton

### 3.1. Dùng số nhiều nhất quán cho collection

Quy ước của API ví dụ là dùng danh từ số nhiều cho collection và giữ nguyên tên đó khi truy cập một phần tử:

```text
/orders
/orders/{orderId}

/customers
/customers/{customerId}

/products
/products/{productId}
```

Không đổi từ số nhiều sang số ít giữa hai route:

```text
/orders                  collection
/order/{orderId}         cách đặt tên không nhất quán với collection trên
```

Cả số ít lẫn số nhiều đều có thể được một hệ thống chọn làm quy ước. Lợi ích chính đến từ việc thống nhất toàn bộ hợp đồng, không phải từ việc một dạng số nhiều có tính hợp lệ HTTP cao hơn dạng số ít.

Với danh từ bất quy tắc, nên chốt trong bảng thuật ngữ của API. Ví dụ dùng `/people` và `/people/{personId}`, tránh để một nhóm chọn `/persons`, nhóm khác chọn `/people` cho cùng một loại resource mà không có lý do nghiệp vụ.

### 3.2. Singleton không cần bị ép thành collection

Singleton là một resource đơn trong một ngữ cảnh xác định. Ví dụ:

```text
/me
/me/preferences
/customers/{customerId}/profile
/orders/{orderId}/billing-address
```

`billing-address` có thể ở số ít nếu mỗi đơn hàng chỉ có đúng một địa chỉ xuất hóa đơn trong mô hình API. Ngược lại, `/customers/{customerId}/addresses` phù hợp khi một khách hàng có nhiều địa chỉ.

Path tự nó không quyết định cardinality. Hợp đồng cần nói rõ `preferences` là một tài liệu cấu hình đơn hay một collection các mục. Một tên có hình thức số nhiều vẫn có thể đại diện cho một singleton; không nên suy luận cấu trúc response chỉ từ hậu tố của từ.

`/me` là bí danh phụ thuộc danh tính đang xác thực. Hai người gọi cùng path có thể nhận hai resource khác nhau. Nếu sử dụng, API cần xác định hành vi xác thực và cache tương ứng; `/me` không tự thay thế mọi địa chỉ ổn định như `/users/{userId}`.

### 3.3. Tránh trộn ngôn ngữ và thuật ngữ

Một API có thể dùng tên tiếng Việt hoặc tiếng Anh. Trong API mẫu, nhóm chọn tiếng Anh để đồng nhất với hợp đồng tích hợp:

```text
/orders
/customers
/shipping-addresses
```

Không trộn thành:

```text
/orders
/khach-hang
/customerDiaChi
```

Đây là quyết định của hợp đồng, không phải giới hạn rằng URI chỉ được chứa tiếng Anh. Với IRI hoặc dữ liệu tên gọi Unicode, cần quy định cách biểu diễn và mã hóa nhất quán. Bài này dùng tên segment cố định bằng ASCII để việc trao đổi qua công cụ và hệ thống tích hợp đơn giản hơn.

## 4. Chữ thường, dấu phân cách và tên rõ nghĩa

### 4.1. Dùng chữ thường cho các segment do API định nghĩa

Quy ước đề xuất:

```text
/order-items
/shipping-addresses
/payment-methods
```

Tránh công bố nhiều kiểu tên cho cùng một khái niệm:

```text
/OrderItems
/orderItems
/order_items
/order-items
```

Path có thể phân biệt chữ hoa và chữ thường. Không dựa vào cách một framework, proxy hoặc hệ điều hành đang xử lý để xem `/Orders` và `/orders` mặc nhiên là cùng một địa chỉ. Hợp đồng nên công bố một cách viết chính thức.

Quy ước chữ thường áp dụng cho các segment cố định mà nhóm API thiết kế. Không tự chuyển chữ thường một ID hoặc một giá trị path do client cung cấp, vì hệ thống định danh có thể phân biệt hoa thường:

```text
/products/SKU-AbC9
```

Nếu `SKU-AbC9` và `sku-abc9` là hai mã khác nhau, việc chuẩn hóa tùy tiện sẽ làm sai resource đích.

### 4.2. Dùng dấu gạch nối cho tên nhiều từ

Chọn `kebab-case` cho các tên cố định:

```text
/payment-methods
/shipping-addresses
/report-exports
```

Dấu gạch dưới và camelCase vẫn có thể là URI hợp lệ. Vấn đề là không nên đổi quy ước giữa các endpoint khi không có nhu cầu rõ ràng.

Phân biệt tên trong path với tên tham số của tài liệu hoặc code:

```text
/orders/{orderId}/items/{itemId}
```

Trong OpenAPI và Spring, `orderId` và `itemId` là tên biến của hợp đồng hoặc code; chúng không xuất hiện nguyên văn trong URL gửi qua mạng. URL thực tế có thể là:

```text
/orders/ord_9001/items/item_4
```

Vì vậy, việc dùng `kebab-case` cho segment và `camelCase` cho biến path không phải mâu thuẫn. Cần thống nhất hai quy ước này và giữ tên biến khớp giữa tài liệu và mã nguồn.

### 4.3. Ưu tiên rõ nghĩa hơn viết tắt khó hiểu

| Nên cân nhắc dùng | Tên dễ gây hiểu nhầm | Lý do |
| --- | --- | --- |
| `/customers` | `/cust` | Không buộc client học viết tắt nội bộ |
| `/shipping-addresses` | `/ship-addr` | Đọc được đầy đủ ý nghĩa nghiệp vụ |
| `/payment-methods` | `/pm` | Tránh xung đột nghĩa giữa các bộ phận |
| `/orders/{orderId}` | `/data/{id}` | Nhìn path biết loại resource |

Không phải mọi chữ viết tắt đều xấu. Các từ đã là thuật ngữ chung của miền có thể phù hợp. Điều cần tránh là tên chỉ người viết hệ thống hiểu.

## 5. Thiết kế quan hệ lồng nhau có chủ đích

### 5.1. Lồng nhau khi ngữ cảnh cha giúp định danh hoặc diễn đạt quan hệ

Ví dụ:

```text
/orders/{orderId}/items
/orders/{orderId}/items/{itemId}
```

Cách này cho biết collection dòng hàng được đặt trong ngữ cảnh một đơn hàng. Nó đặc biệt phù hợp khi mã dòng hàng chỉ có ý nghĩa trong đơn hàng đó.

Giả sử dòng số `1` tồn tại trong nhiều đơn hàng:

```text
/orders/ord_9001/items/1
/orders/ord_9002/items/1
```

Hai URI chỉ hai dòng hàng khác nhau. Lúc này, chỉ `/items/1` không đủ thông tin để định danh nếu hệ thống không có một định danh toàn cục khác.

### 5.2. Không lồng mọi mối quan hệ trong mô hình dữ liệu

Một khách hàng có nhiều đơn hàng, nhưng điều đó không buộc mọi địa chỉ của đơn hàng phải có tiền tố khách hàng:

```text
/customers/{customerId}/orders/{orderId}
```

Nếu `orderId` đã định danh duy nhất toàn hệ thống và client thường truy cập đơn hàng trực tiếp, địa chỉ chính thức có thể là:

```text
/orders/{orderId}
```

Danh sách đơn hàng của khách hàng vẫn có thể được cung cấp qua một collection theo quan hệ:

```text
/customers/{customerId}/orders
```

Hoặc qua bộ lọc của collection tổng:

```text
/orders?customerId={customerId}
```

Cả hai cách đều có thể hợp lý. Hãy chọn theo nhu cầu truy cập, phạm vi quyền và khả năng diễn đạt của hợp đồng; tránh thêm cả hai chỉ vì chưa quyết định được.

### 5.3. Đừng để path dài chỉ để phản chiếu sơ đồ quan hệ

Ví dụ khó sử dụng:

```text
/organizations/{organizationId}/departments/{departmentId}/customers/{customerId}/orders/{orderId}/items/{itemId}
```

Nếu chỉ cần `orderId` và `itemId` để định danh, có thể dùng:

```text
/orders/{orderId}/items/{itemId}
```

Nếu phạm vi tổ chức là một phần cần thiết của định danh và hợp đồng tenant, có thể giữ:

```text
/organizations/{organizationId}/orders/{orderId}
```

Không có quy tắc phổ quát rằng path chỉ được lồng đúng một hoặc hai cấp. Mỗi cấp nên có lý do cụ thể: bổ sung thông tin định danh, phạm vi truy cập hoặc quan hệ có ý nghĩa với client. Nếu bỏ một cấp mà hợp đồng không mất thông tin cần thiết, nên xem xét rút gọn.

### 5.4. Path lồng nhau không tự thực thi phân quyền

Với yêu cầu:

```http
GET /api/v1/customers/cus_42/orders/ord_9001
```

Máy chủ cần kiểm tra các điều kiện liên quan:

1. Người gọi có quyền truy cập ngữ cảnh khách hàng `cus_42` hay không.
2. Đơn hàng `ord_9001` có thực sự thuộc khách hàng đó hay không.
3. Người gọi có quyền đọc đơn hàng cụ thể hay không.

Không được lấy đơn hàng chỉ bằng `orderId` rồi bỏ qua `customerId` trên path. Tương tự, thay ID tuần tự bằng UUID không thay thế kiểm soát truy cập. Quy ước URI giúp diễn đạt phạm vi; logic ứng dụng mới thực thi phạm vi đó.

## 6. Phân biệt resource đích với tiêu chí truy vấn

Dùng path cho một resource đã được định danh:

```http
GET /api/v1/orders/ord_9001
```

Dùng query khi truy vấn collection theo các điều kiện có thể kết hợp:

```http
GET /api/v1/orders?status=paid&customerId=cus_42
```

Nếu đưa mọi điều kiện vào path:

```text
/orders/status/paid/customer/cus_42/created-after/2026-10-01
```

thì việc thêm điều kiện hoặc đổi thứ tự trở nên khó quản lý. Query thường phù hợp hơn:

```text
/orders?status=paid&customerId=cus_42&createdAfter=2026-10-01
```

Quy ước này cũng giúp giữ path ổn định khi mở rộng phân trang và sắp xếp:

```text
/orders?status=paid&sort=createdAt,desc&page=0&size=20
```

Tên query, kiểu dữ liệu, thứ tự sắp xếp, múi giờ và cách đánh số trang phải được định nghĩa trong hợp đồng riêng. Ví dụ `page=0` ở trên chỉ là lựa chọn của API mẫu, không phải quy tắc chung của HTTP.

Một collection con như `/customers/{customerId}/orders` và một collection lọc như `/orders?customerId=...` không bắt buộc phải có mọi hành vi giống hệt nhau. Nếu cung cấp cả hai, cần nói rõ phạm vi dữ liệu, quyền và cấu trúc response để client không suy đoán.

## 7. Quy ước cho ID, slug và các segment đặc biệt

### 7.1. Coi ID là giá trị không cần bóc tách ở phía client

Ví dụ:

```text
/orders/ord_9001
/products/prd_284
/customers/550e8400-e29b-41d4-a716-446655440000
```

Client nên lưu và gửi lại ID theo hợp đồng, không suy ra quy tắc nghiệp vụ từ từng ký tự nếu API không công bố quy tắc đó. Tránh bắt client phân tích tiền tố để biết trạng thái, khu vực hoặc loại tài khoản.

Có thể dùng số nguyên, UUID hoặc một định danh khác. Điều cần xác định rõ là:

- ID duy nhất toàn hệ thống hay chỉ trong một resource cha.
- ID có phân biệt chữ hoa, chữ thường không.
- ID có ổn định trong suốt vòng đời resource không.
- Định dạng nào được chấp nhận và giá trị nào bị từ chối.

Không đưa token, mật khẩu hoặc bí mật vào path. URI có thể xuất hiện trong log, lịch sử truy cập và các công cụ giám sát. Dù dùng loại ID nào, máy chủ vẫn cần kiểm tra quyền truy cập.

### 7.2. Slug dễ đọc cần chính sách ổn định

Slug có thể tạo URI dễ nhận biết:

```text
/articles/thiet-ke-uri-rest
```

Nhưng tiêu đề bài viết có thể đổi. Nếu slug là một phần định danh, hợp đồng cần quyết định:

- Slug có thay đổi khi tiêu đề thay đổi không.
- Slug có duy nhất trong phạm vi nào.
- Địa chỉ cũ sẽ được giữ, chuyển hướng hay báo không còn tồn tại.
- Client nên lưu ID ổn định hay lưu liên kết do API trả về.

Với resource nghiệp vụ như đơn hàng, một ID ổn định thường dễ quản lý hơn việc lấy tên hiển thị làm địa chỉ. Với nội dung công khai, slug có thể hữu ích nếu hệ thống quản lý tốt liên kết cũ.

### 7.3. Mã hóa từng giá trị segment đúng cách

Không nối trực tiếp chuỗi do người dùng nhập vào path:

```text
/products/ + externalCode
```

Nếu `externalCode` chứa `/`, `?`, `#` hoặc ký tự cần mã hóa, cấu trúc URI có thể thay đổi. Hãy dùng URI builder phù hợp và quy định rõ tập ký tự của ID.

Việc mã hóa dấu `/` trong một segment cũng có thể được proxy hoặc router xử lý khác nhau. Một hợp đồng ID đơn giản, không chứa dấu phân cách path, thường dễ triển khai hơn. Không tự thay thế ký tự hoặc giải mã nhiều lần để cố làm cho một ID không hợp lệ trở nên hợp lệ.

Trong hợp đồng ví dụ, các ID dạng `ord_9001` và `item_4` tránh những ký tự phân cách này. Dấu gạch dưới trong **giá trị ID** không mâu thuẫn với quy ước gạch nối cho **tên segment cố định**.

### 7.4. Dành trước tên đặc biệt khi cần

Cân nhắc hai route:

```text
/orders/{orderId}
/orders/search
```

Nếu chuỗi `search` cũng được phép là một `orderId`, hợp đồng có thể trở nên mơ hồ. Router có thể có quy tắc ưu tiên riêng, nhưng client vẫn cần một thiết kế dễ hiểu.

Với tìm kiếm thông thường, ưu tiên truy vấn collection:

```text
/orders?query=invoice-2026
```

Nếu cần một endpoint tìm kiếm chuyên biệt, hãy quy định tên dành riêng, giới hạn ID và kiểm thử cách router phân giải. Không mặc nhiên coi một regex hoặc quy tắc ưu tiên của framework là giải pháp đầy đủ cho thiết kế hợp đồng.

## 8. Một địa chỉ chính thức và chính sách chuẩn hóa

### 8.1. Thống nhất dấu `/` ở cuối

Chọn một dạng chính thức, ví dụ không có dấu `/` cuối:

```text
/orders
/orders/ord_9001
```

Đừng dựa vào giả định rằng những cặp sau luôn tương đương:

```text
/orders
/orders/
```

Tùy máy chủ và cấu hình định tuyến, chúng có thể được xử lý khác nhau. Nếu hỗ trợ dạng thay thế, cần có chính sách rõ ràng: chấp nhận, chuyển hướng hoặc từ chối. Kiểm thử hành vi qua cả gateway và ứng dụng, nhất là với các yêu cầu có body.

Không thêm chuyển hướng một cách máy móc cho mọi method. Nếu hợp đồng chọn chuyển hướng, mã trạng thái và hành vi giữ nguyên method/body cần phù hợp với client đang hỗ trợ.

### 8.2. Không gắn phần mở rộng định dạng theo thói quen

Với API JSON thông thường:

```http
GET /api/v1/orders/ord_9001
Accept: application/json
```

thường dễ mở rộng hơn việc bắt mọi resource mang hậu tố `.json`:

```text
/orders/ord_9001.json
```

Header `Accept` mô tả dạng biểu diễn mà client muốn nhận; API cần công bố những dạng được hỗ trợ. Tuy vậy, phần mở rộng không bị URI hay REST cấm. Nếu resource thực sự là một tệp tải xuống, tên có phần mở rộng có thể có ý nghĩa với sản phẩm và hợp đồng.

Điểm cần giữ là phân biệt định danh resource với một lựa chọn biểu diễn, rồi áp dụng cùng một chính sách trên toàn API.

### 8.3. Hạn chế nhiều địa chỉ tương đương không có chủ đích

Ví dụ, nếu cùng một đơn hàng xuất hiện ở cả:

```text
/orders/ord_9001
/customers/cus_42/orders/ord_9001
```

hãy xác định đâu là địa chỉ chính thức, còn địa chỉ kia có vai trò gì. Các bí danh không tự chia sẻ cache hoặc tự có cùng quy tắc phân quyền. Chúng cũng có thể làm phân tán log, số liệu theo dõi và tài liệu.

Nếu API trả liên kết `self` hoặc header `Location` sau tạo mới, nên dùng địa chỉ chính thức đã công bố. Có thể dùng URI tuyệt đối hoặc tham chiếu URI tương đối theo hợp đồng; điều quan trọng là client phân giải được và kết quả nhất quán.

### 8.4. Đổi tên path là thay đổi hợp đồng

Đổi `/order-items` thành `/line-items` có thể làm hỏng client dù hai tên cùng chỉ một dữ liệu và response không đổi.

Khi API đã có người sử dụng:

1. Đánh giá client, tài liệu, SDK, gateway và liên kết đang phụ thuộc path cũ.
2. Xác định cách hỗ trợ chuyển tiếp phù hợp với chính sách phiên bản.
3. Công bố path mới và thời gian ngừng hỗ trợ nếu có.
4. Đo việc sử dụng trước khi loại bỏ path cũ.

Không đổi hàng loạt tên chỉ để đạt vẻ đồng nhất nếu không có kế hoạch tương thích. Với API mới, thống nhất từ đầu rẻ hơn nhiều so với sửa sau khi đã tích hợp.

## 9. Bộ quy ước hoàn chỉnh cho API ví dụ

Một quy ước ngắn, có ví dụ cụ thể sẽ dễ áp dụng hơn danh sách khẩu hiệu.

| Thành phần | Quy ước của API mẫu | Ví dụ |
| --- | --- | --- |
| Base path | Dùng `/api/v1` theo chính sách phiên bản đã chọn | `/api/v1/orders` |
| Ngôn ngữ tên cố định | Tiếng Anh theo bảng thuật ngữ nghiệp vụ | `orders`, `customers` |
| Collection | Danh từ số nhiều | `/orders` |
| Resource trong collection | Giữ tên collection, thêm ID | `/orders/{orderId}` |
| Singleton | Tên diễn tả đúng một resource trong ngữ cảnh | `/orders/{orderId}/billing-address` |
| Chữ và dấu phân cách | Chữ thường, gạch nối cho tên nhiều từ | `/payment-methods` |
| Biến path trong hợp đồng | Tên có ngữ nghĩa, camelCase | `{customerId}`, `{orderId}` |
| Giá trị ID | Tuân thủ định dạng ID, không tự đổi chữ hoa/thường | `ord_9001` |
| Quan hệ lồng nhau | Thêm ngữ cảnh cha khi cần cho định danh hoặc hợp đồng | `/orders/{orderId}/items/{itemId}` |
| Lọc và phân trang | Query của collection | `/orders?status=paid&page=0&size=20` |
| Dấu `/` cuối | Không có trong URI chính thức | `/orders`, không công bố thêm `/orders/` |
| Dạng biểu diễn | Công bố qua hợp đồng media type | `Accept: application/json` |
| Bí danh | Có lý do và xác định địa chỉ chính thức | `Location` trỏ đến `/orders/{orderId}` |

### 9.1. Áp dụng lên một nhóm endpoint

Giả sử ứng dụng cần: liệt kê đơn hàng, tạo đơn, xem chi tiết, đọc dòng hàng, đọc địa chỉ xuất hóa đơn và tạo yêu cầu hủy.

```http
GET   /api/v1/orders
POST  /api/v1/orders
GET   /api/v1/orders/{orderId}
GET   /api/v1/orders/{orderId}/items
GET   /api/v1/orders/{orderId}/items/{itemId}
GET   /api/v1/orders/{orderId}/billing-address
POST  /api/v1/orders/{orderId}/cancellations
```

Ở đây, `{itemId}` được hiểu trong phạm vi một đơn hàng. `billing-address` là một singleton. `cancellations` là collection các yêu cầu hủy có vòng đời riêng, không phải một tên thay thế tùy tiện cho việc xóa đơn hàng.

Từ các path này, client có thể đoán được cấu trúc chung. Tuy nhiên, vẫn phải đọc hợp đồng để biết body, response, trạng thái HTTP, điều kiện hủy và quyền truy cập.

## 10. Ví dụ Java/Spring: giữ path thống nhất trong controller

Ví dụ dưới đây minh họa một thao tác tạo mới qua collection và một thao tác đọc resource đơn. Đây là khung cho ứng dụng Spring MVC hỗ trợ Java records; ứng dụng cần cung cấp một bean triển khai `OrderService`, xử lý xác thực và các kiểm tra dữ liệu theo hợp đồng thực tế.

```java
package example.orders;

import java.net.URI;
import java.util.Optional;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{orderId}")
    public OrderView getOrder(@PathVariable("orderId") String orderId) {
        return orderService.findVisibleToCurrentUser(orderId)
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Order not found"));
    }

    @PostMapping
    public ResponseEntity<OrderView> createOrder(
            @RequestBody CreateOrderRequest request) {
        OrderView created = orderService.createForCurrentUser(request);

        URI location = ServletUriComponentsBuilder
            .fromCurrentRequestUri()
            .path("/{orderId}")
            .buildAndExpand(created.id())
            .encode()
            .toUri();

        return ResponseEntity.created(location).body(created);
    }

    public record CreateOrderRequest(String customerId) {}

    public record OrderView(String id, String status) {}

    public interface OrderService {
        Optional<OrderView> findVisibleToCurrentUser(String orderId);
        OrderView createForCurrentUser(CreateOrderRequest request);
    }
}
```

Những lựa chọn liên quan trực tiếp đến thiết kế URI:

- Controller ánh xạ collection bằng `/api/v1/orders`, không dùng `/createOrder` hoặc `/getOrder` làm route.
- `GET /api/v1/orders/{orderId}` và `POST /api/v1/orders` chia sẻ cùng một tên resource.
- Tên `orderId` trong annotation khớp với placeholder của path.
- `Location` sau khi tạo mới trỏ đến địa chỉ chính thức của đơn hàng vừa tạo.
- URI builder nhận ID như một giá trị, tránh lắp ghép URL bằng phép cộng chuỗi.

Dữ liệu `customerId` trong request không chứng minh người gọi được phép tạo đơn cho khách hàng đó. Phần triển khai service phải kiểm tra quyền trước khi xử lý. Tương tự, `findVisibleToCurrentUser` biểu đạt yêu cầu lọc theo quyền; tên phương thức tự nó không thực thi bảo mật.

Khi ứng dụng chạy sau reverse proxy, việc tạo URI tuyệt đối từ request cần cấu hình tin cậy và xử lý forwarded headers đúng với hạ tầng. Nếu không, `Location` có thể mang host hoặc scheme không đúng địa chỉ công khai. Đây là điều kiện triển khai cần xác minh, bên cạnh quy ước đặt tên path.

### 10.1. Giữ tên path trong OpenAPI khớp với code

Đoạn YAML sau là một phần trích của tài liệu OpenAPI, không phải toàn bộ đặc tả:

```yaml
paths:
  /api/v1/orders/{orderId}:
    get:
      operationId: getOrder
      summary: Lấy một đơn hàng mà người gọi được phép đọc
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
          description: Định danh ổn định của đơn hàng
      responses:
        '200':
          description: Đã trả về đơn hàng
        '404':
          description: Không tìm thấy đơn hàng trong phạm vi truy cập
```

`operationId: getOrder` có động từ là bình thường: đây là tên thao tác trong tài liệu hoặc SDK, không phải tên resource trong path. Không cần ép tên hàm Java và tên path có cùng hình thức.

Placeholder `{orderId}` phải khớp với parameter `name: orderId`. Một tài liệu dùng `{id}` trong path nhưng lại khai báo `name: orderId` tạo ra hợp đồng không nhất quán dù controller hoạt động.

## 11. Chuyển một thiết kế thiếu nhất quán thành hợp đồng rõ ràng

Giả sử nhóm đang đề xuất các endpoint mới sau:

```text
GET  /getAllOrders
GET  /Order/{id}
POST /orders/create
GET  /customer/{customerId}/orderList
GET  /orders/{id}/order_items
POST /orders/{id}/delete
```

Trước khi đổi tên, hãy hỏi thao tác cuối thật sự có nghĩa là xóa dữ liệu hay tạo yêu cầu hủy. Sau khi xác nhận mô hình, bảng chuyển đổi cho **API đang thiết kế, chưa phát hành** có thể là:

| Đề xuất ban đầu | Hợp đồng thống nhất | Giải thích |
| --- | --- | --- |
| `GET /getAllOrders` | `GET /orders` | Collection, không cam kết trả mọi bản ghi trong một lần |
| `GET /Order/{id}` | `GET /orders/{orderId}` | Chữ thường, số nhiều, tên biến rõ nghĩa |
| `POST /orders/create` | `POST /orders` | Dùng method và hợp đồng tạo mới |
| `GET /customer/{customerId}/orderList` | `GET /customers/{customerId}/orders` | Cả resource cha lẫn collection con thống nhất số nhiều |
| `GET /orders/{id}/order_items` | `GET /orders/{orderId}/items` | Bỏ phần `order` lặp nghĩa, dùng tên quan hệ gọn |
| `POST /orders/{id}/delete` | `POST /orders/{orderId}/cancellations` nếu nghiệp vụ là yêu cầu hủy | Sửa mô hình theo ý nghĩa thực, không chỉ thay động từ |

Nếu nghiệp vụ cuối thật sự là xóa resource và hệ thống cho phép xóa, một lựa chọn là `DELETE /orders/{orderId}` với điều kiện và phản hồi được định nghĩa rõ. Không được đổi hủy thành xóa chỉ để tạo một bảng CRUD cân đối.

Nếu các endpoint ban đầu đã được phát hành, bảng trên là định hướng thiết kế mới; nó không cho phép xóa route cũ ngay lập tức. Cần áp dụng chính sách tương thích đã nêu ở phần trước.

## 12. Lỗi thường gặp và cách nhận ra

### 12.1. Dùng một path tổng quát cho mọi thao tác

```http
POST /api
Content-Type: application/json

{
  "action": "getOrder",
  "id": "ord_9001"
}
```

Kiểu hợp đồng này có thể thuộc một lựa chọn RPC có chủ đích, nhưng không thể hiện rõ resource qua URI như API đang học. Client và công cụ quan sát phải đọc body mới biết thao tác gì đang diễn ra. Với nhu cầu đọc một đơn hàng trong thiết kế hiện tại, `GET /orders/{orderId}` diễn đạt trực tiếp hơn.

### 12.2. Biến trạng thái thành nhiều path cố định

```text
/paid-orders
/unpaid-orders
/cancelled-orders
```

Nếu đây chỉ là ba bộ lọc trên cùng collection đơn hàng, nên cân nhắc:

```text
/orders?status=paid
/orders?status=unpaid
/orders?status=cancelled
```

Ngược lại, nếu “hàng chờ xử lý” là một resource có quyền truy cập và vòng đời riêng, một collection như `/fulfillment-tasks` có thể có lý do tồn tại. Đừng quyết định chỉ bằng việc hai response hiện cùng chứa đơn hàng.

### 12.3. Đưa chi tiết triển khai vào địa chỉ công khai

```text
/v2/order-table
/orders-jpa
/spring-order-service/get
```

Các tên này gắn client với công nghệ hoặc cấu trúc bên trong. Đổi ORM hay tách service không nên buộc client đổi URI nếu ý nghĩa resource không đổi.

### 12.4. Nghĩ rằng lồng sâu sẽ an toàn hơn

Một path dài chứa đủ `organizationId`, `customerId`, `orderId` không có tác dụng bảo vệ nếu backend bỏ qua quan hệ và quyền. Hãy giữ những ngữ cảnh cần thiết, rồi kiểm tra chúng tại lớp xử lý có trách nhiệm.

### 12.5. Chuẩn hóa quá mức giá trị path

Chuyển mọi ký tự thành chữ thường, xóa dấu câu hoặc giải mã nhiều lần có thể biến một ID thành ID khác. Chỉ chuẩn hóa những thành phần mà hợp đồng cho phép và giữ phân biệt giữa tên route cố định với dữ liệu định danh.

## 13. Tự đánh giá thiết kế trước khi triển khai

Khi rà soát một nhóm endpoint, hãy trả lời các câu hỏi sau:

1. **Resource là gì?** Người ngoài nhóm có hiểu được tên mà không biết bảng dữ liệu hoặc tên lớp không?
2. **Collection và resource đơn có cùng quy ước không?** Ví dụ `/orders` đi với `/orders/{orderId}`.
3. **Singleton có thực sự là một đối tượng trong ngữ cảnh đó không?** Nếu có nhiều địa chỉ, vì sao lại đặt `/address`?
4. **Các tên nhiều từ có cùng cách viết không?** Kiểm tra chữ thường, gạch nối và bảng thuật ngữ.
5. **Mỗi cấp lồng nhau có lý do không?** Ngữ cảnh cha có cần cho định danh hoặc hợp đồng không?
6. **Điều kiện lọc có đang làm path phình ra không?** Có thể dùng query rõ ràng hơn không?
7. **ID có hợp đồng ổn định không?** Có quy định phạm vi, phân biệt hoa thường và ký tự hợp lệ không?
8. **Địa chỉ chính thức là gì?** `Location`, liên kết trả về và tài liệu có sử dụng cùng cách viết không?
9. **Path có khớp với code và OpenAPI không?** Đặc biệt là placeholder và tên path parameter.
10. **Quan hệ trong path có được kiểm tra khi xử lý không?** Thử trường hợp ID con thuộc một cha khác.
11. **Tên mới có làm hỏng client hiện tại không?** Nếu có, kế hoạch chuyển tiếp là gì?

Đây là bộ tiêu chí để tự xem xét thiết kế URI, không thay thế kiểm thử toàn bộ chức năng, bảo mật hoặc đánh giá học thuật của tài liệu.

## 14. Bài tập thực hành

### Bài tập 1: Chuẩn hóa tên và giải thích lựa chọn

Hãy thiết kế lại nhóm endpoint chưa phát hành sau:

```text
GET  /GetProducts
GET  /product/{id}
POST /createProduct
GET  /products/{id}/ProductReviews
GET  /products/category/books/status/active
```

Yêu cầu:

- Dùng một quy ước cho collection và resource đơn.
- Tách tên segment cố định khỏi tên biến path.
- Giữ ngữ cảnh sản phẩm cho collection đánh giá.
- Chuyển các tiêu chí lọc có thể kết hợp sang query.

Một phương án tham khảo:

```text
GET  /products
GET  /products/{productId}
POST /products
GET  /products/{productId}/reviews
GET  /products?category=books&status=active
```

Điểm cần giải thích là lý do giữ `/products/{productId}/reviews`: collection đánh giá đang được truy cập trong ngữ cảnh một sản phẩm. Nếu cần địa chỉ cho một đánh giá cụ thể, hãy xác định trước `reviewId` duy nhất toàn hệ thống hay chỉ trong một sản phẩm.

### Bài tập 2: Chọn mức lồng nhau

Hệ thống có `orderId` duy nhất toàn cục. Mỗi dòng hàng dùng số thứ tự chỉ duy nhất trong đơn hàng. Hãy chọn URI cho:

1. Một đơn hàng.
2. Danh sách dòng hàng của đơn đó.
3. Dòng số `3` của đơn đó.

Phương án tham khảo:

```text
/orders/ord_9001
/orders/ord_9001/items
/orders/ord_9001/items/3
```

Không thể rút trường hợp cuối thành `/items/3` nếu hệ thống không có định danh toàn cục khác cho dòng hàng.

### Bài tập 3: Phân biệt collection và singleton

Một khách hàng lưu nhiều địa chỉ giao hàng; mỗi đơn hàng lưu đúng một bản chụp địa chỉ xuất hóa đơn tại thời điểm mua. Hãy đặt path cho hai loại dữ liệu.

Phương án tham khảo:

```text
/customers/{customerId}/shipping-addresses
/orders/{orderId}/billing-address
```

Giải thích vì sao một bên là collection và một bên là singleton. Bản chụp địa chỉ của đơn hàng cũng không nhất thiết là cùng resource với địa chỉ hiện tại trong hồ sơ khách hàng.

### Bài tập 4: Quyết định mô hình cho thao tác hủy

Nghiệp vụ yêu cầu lưu người gửi yêu cầu, lý do, thời điểm và kết quả phê duyệt việc hủy đơn. Hãy đề xuất path và mô tả resource đích.

Phương án tham khảo:

```text
POST /orders/{orderId}/cancellations
GET  /orders/{orderId}/cancellations/{cancellationId}
```

Resource đích là yêu cầu hủy có vòng đời riêng. Path chỉ là một phần của thiết kế: hợp đồng vẫn cần định nghĩa ai được tạo yêu cầu, trạng thái phản hồi và cách xử lý khi client gửi lặp.

## 15. Ghi nhớ để áp dụng

Một path tốt giúp người đọc xác định **đang nói đến loại resource nào, một phần tử hay một collection, và trong phạm vi nào**. Hãy bắt đầu từ mô hình nghiệp vụ, ưu tiên danh từ, rồi thống nhất số nhiều, cách viết tên, cấu trúc quan hệ và địa chỉ chính thức.

Với API ví dụ, trục thiết kế là:

```text
/orders
/orders/{orderId}
/orders/{orderId}/items
/orders/{orderId}/items/{itemId}
```

Tính nhất quán giúp client học một quy tắc rồi áp dụng sang nhiều endpoint. Giá trị của quy ước nằm ở một hợp đồng dễ hiểu và ổn định, đi cùng HTTP method, quyền truy cập và dữ liệu được định nghĩa rõ ràng.
