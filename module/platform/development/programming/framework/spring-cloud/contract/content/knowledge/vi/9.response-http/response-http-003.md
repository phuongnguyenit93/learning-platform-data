# JSON response body và cấu trúc dữ liệu

## 1. Tại sao cấu trúc JSON response là một phần quan trọng của hợp đồng?

Trong hệ thống microservice, một API có thể tiếp tục trả HTTP `200 OK` nhưng vẫn làm hỏng consumer nếu cấu trúc JSON thay đổi. Chẳng hạn `Order Service` từng trả:

~~~json
{
  "orderId": "ORD-123",
  "totalAmount": 250000,
  "paid": true
}
~~~

Sau một lần refactor, producer đổi thành:

~~~json
{
  "id": "ORD-123",
  "totalAmount": "250000",
  "paid": "true"
}
~~~

Dù status không đổi, consumer đang đọc `orderId` hoặc giải mã `totalAmount` thành số sẽ gặp lỗi. Đây là một **thay đổi không tương thích ở ranh giới HTTP**.

**Spring Cloud Contract** cho phép producer và consumer thống nhất những kỳ vọng có thể kiểm chứng: HTTP status, headers và **response body**. Contract có thể viết bằng **Groovy DSL** hoặc **YAML DSL**. Plugin sinh test chạy ở phía producer để phát hiện hành vi không còn đáp ứng contract; khi producer đã vượt qua kiểm chứng, các stub được phát hành để consumer sử dụng qua Stub Runner. Trong CI, chuỗi công cụ này giúp bắt thay đổi API sớm hơn khi các nhóm triển khai độc lập.

Bài học thuộc chương **Response HTTP** và tập trung vào đề tài **JSON response body và cấu trúc dữ liệu**: viết contract cho object, array, các kiểu giá trị, trường lồng nhau, giá trị động và phản hồi lỗi.

Sau bài này, bạn có thể:

1. Phân biệt HTTP status, `Content-Type` và nội dung JSON response body.
2. Biểu diễn JSON object, array và cấu trúc lồng nhau bằng Groovy/YAML DSL.
3. Kiểm tra đúng String, number, boolean, `null` và trường không tồn tại.
4. Sử dụng JSONPath và matcher để cân bằng giữa tính ổn định và khả năng phát hiện breaking change.
5. Tổ chức các phản hồi thành công/lỗi có ý nghĩa đối với consumer.
6. Hiểu các kiểm chứng nào được sinh cho producer và cách đưa chúng vào quy trình CI.

> **Nguyên tắc:** Hợp đồng nên bảo vệ những phần của response mà consumer thật sự phụ thuộc. Không sao chép toàn bộ cấu trúc nội bộ của producer thành một snapshot cứng nhắc nếu consumer không cần các trường đó.

## 2. Ba lớp cần đọc trong một HTTP response

Ví dụ response đầy đủ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "orderId": "ORD-123",
  "status": "CONFIRMED",
  "totalAmount": 250000
}
~~~

| Lớp | Ví dụ | Điều consumer có thể phụ thuộc |
| --- | --- | --- |
| HTTP status | `200` | Phân biệt thành công, không tìm thấy, dữ liệu không hợp lệ |
| Response headers | `Content-Type: application/json` | Chọn cách giải mã body và các metadata liên quan |
| Response body | `orderId`, `status`, `totalAmount` | Truy xuất trường, kiểm tra kiểu và xử lý nghiệp vụ |

Ở cấp HTTP, status và body là hai điều khác nhau:

- `200` với JSON lỗi giả ở body có thể làm client xử lý sai nếu hợp đồng cam kết dữ liệu thành công.
- `404` với JSON có field `code` có thể cần một contract riêng nếu consumer đọc mã lỗi để hiển thị hoặc quyết định retry.
- `204 No Content` thông thường **không có body**. Đừng tạo một body JSON có ý nghĩa cho phản hồi `204`.
- `Content-Type` cần phù hợp với body thực tế; JSON body không nhất thiết đồng nghĩa server đã khai báo media type đúng.

### 2.1. Response body có thể có nhiều hình dạng

JSON không bắt buộc phải là object ở cấp gốc:

~~~json
{"id":"ORD-123","status":"CONFIRMED"}
~~~

~~~json
[
  {"id":"ORD-123","status":"CONFIRMED"},
  {"id":"ORD-456","status":"PENDING"}
]
~~~

~~~json
{
  "data": [
    {"id":"ORD-123","status":"CONFIRMED"}
  ],
  "page": {
    "number": 0,
    "size": 20
  }
}
~~~

Ví dụ lần lượt là **root object**, **root array** và **object chứa array cùng metadata phân trang**. Một consumer đã thiết kế cho `List<Order>` sẽ không tự hiểu một response bị thay thành `{"data":[...]}`.

## 3. Viết response JSON bằng Groovy DSL

Một hợp đồng HTTP đủ đơn giản để bắt đầu:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_confirmed_order')

    request {
        method 'GET'
        url '/api/orders/ORD-123'
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: 'ORD-123',
            status: 'CONFIRMED',
            totalAmount: 250000,
            paid: true
        )
    }
}
~~~

Ở đây:

- `response { ... }` là phần mô tả kết quả producer cần trả.
- `status OK()` diễn tả HTTP `200`.
- `contentType(applicationJson())` mô tả header `Content-Type` phù hợp JSON.
- `body(...)` chứa các trường JSON mà consumer cần.
- `'ORD-123'`, `250000` và `true` lần lượt là String, number và boolean.

JSON tương ứng:

~~~json
{
  "orderId": "ORD-123",
  "status": "CONFIRMED",
  "totalAmount": 250000,
  "paid": true
}
~~~

**Không cần viết một đoạn JSON string để mô tả object đơn giản.** Với Groovy DSL, cú pháp `body(key: value, ...)` rất thuận tiện, đặc biệt khi phải lồng map, list và matcher.

### 3.1. Đối tượng ở cấp gốc dùng map

Cách viết tường minh bằng Groovy map cũng phù hợp:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body([
        orderId: 'ORD-123',
        status: 'CONFIRMED',
        totalAmount: 250000
    ])
}
~~~

`body(orderId: ..., status: ...)` và `body([orderId: ..., status: ...])` đều thể hiện JSON object về mặt dữ liệu. Chọn một phong cách để các contract trong dự án dễ đọc và sửa.

### 3.2. Chỉ viết body thì đã đủ chưa?

Chưa hẳn. Nếu contract thiếu `Content-Type`, producer test có thể không bảo vệ được media type mà consumer đang dựa vào. Nếu thiếu status, hợp đồng không mô tả đầy đủ HTTP response.

Một response contract điển hình nên có:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body(
        // Các trường mà consumer sử dụng
        orderId: 'ORD-123'
    )
}
~~~

Các trường hợp đặc biệt như file download, text hoặc binary body cần cách mô tả khác. Đừng đặt `application/json` cho phản hồi không phải JSON chỉ để test dễ chạy.

## 4. Kiểu dữ liệu JSON: String, Number, Boolean và Null

Ví dụ:

~~~groovy
body(
    orderId: 'ORD-123',
    quantity: 3,
    price: 49.95,
    delivered: false,
    promotionCode: null
)
~~~

Body JSON biểu diễn:

~~~json
{
  "orderId": "ORD-123",
  "quantity": 3,
  "price": 49.95,
  "delivered": false,
  "promotionCode": null
}
~~~

| Trường | Kiểu JSON | Một thay đổi có thể phá vỡ consumer |
| --- | --- | --- |
| `orderId` | String | Trả number hoặc xóa/đổi tên trường |
| `quantity` | Number | Đổi từ `3` thành `"3"` |
| `price` | Number | Đổi sang chuỗi định dạng tiền mà không có thỏa thuận |
| `delivered` | Boolean | Đổi `false` thành `"false"` |
| `promotionCode` | Null | Đổi thành chuỗi `"null"` hoặc xóa field khi client cần phân biệt |

### 4.1. Giá trị số và định dạng tiền

Nếu producer trả:

~~~json
{"totalAmount": 250000}
~~~

thì `totalAmount` là số. Response sau khác kiểu:

~~~json
{"totalAmount": "250000"}
~~~

Với dữ liệu tiền tệ, contract nên xác định **đơn vị và ý nghĩa của số**, ví dụ `250000` là số tiền theo VND. Một số có thể mang kiểu `Integer`, `Long` hoặc `BigDecimal` trong ứng dụng Java; JSON chỉ có kiểu `number` ở cấp dữ liệu. Consumer có thể cần thêm cam kết về miền giá trị, độ chính xác và cách làm tròn.

Generated test phải kiểm tra những kỳ vọng tương ứng với DSL và matcher đã chọn; không nên suy ra rằng chỉ kiểm tra giá trị mẫu sẽ tự chứng minh mọi giới hạn nghiệp vụ về số tiền. Những quy tắc như `totalAmount >= 0` vẫn nên có unit/domain tests.

### 4.2. Boolean khác String

~~~groovy
body(
    paid: true,
    cancelled: false
)
~~~

khác với:

~~~groovy
body(
    paid: 'true',
    cancelled: 'false'
)
~~~

Hai response thứ hai có giá trị String. Nếu consumer dùng parser mạnh kiểu như `boolean paid`, đây có thể là breaking change.

### 4.3. Null, field vắng mặt và chuỗi rỗng

Ba JSON sau có ý nghĩa khác nhau:

~~~json
{"couponCode": null}
~~~

~~~json
{}
~~~

~~~json
{"couponCode": ""}
~~~

- `null`: trường xuất hiện với giá trị null.
- Trường vắng: object không chứa khóa `couponCode`.
- Chuỗi rỗng `""`: trường xuất hiện với một giá trị String dài 0 ký tự.

Trong contract, `couponCode: null` mô tả **trường có giá trị null**, không phải một field tùy chọn bất kỳ. Nếu consumer có yêu cầu khác nhau cho ba trường hợp trên, hãy định nghĩa các kịch bản phù hợp và kiểm tra chính sách dữ liệu thực tế.

## 5. JSON object lồng nhau với Groovy map

Nhiều API trả object lồng nhau để thể hiện thực thể liên quan:

~~~json
{
  "orderId": "ORD-123",
  "customer": {
    "id": "CUS-7",
    "name": "Lan"
  },
  "delivery": {
    "address": {
      "city": "Da Nang",
      "postalCode": "550000"
    },
    "priority": false
  }
}
~~~

Trong Groovy DSL:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body(
        orderId: 'ORD-123',
        customer: [
            id: 'CUS-7',
            name: 'Lan'
        ],
        delivery: [
            address: [
                city: 'Da Nang',
                postalCode: '550000'
            ],
            priority: false
        ]
    )
}
~~~

Cách đọc:

1. `body(...)` là một **object gốc**.
2. `customer: [ ... ]` là **object con**.
3. `delivery: [address: [...], priority: false]` là **object lồng object**.
4. Khóa của map trở thành tên field trong JSON, còn giá trị giữ kiểu phù hợp.

### 5.1. Khóa JSON không phải định danh Groovy hợp lệ

Nếu API thật có field chứa dấu gạch ngang hoặc dấu chấm, hãy trích dẫn khóa:

~~~groovy
body([
    'order-id': 'ORD-123',
    'trace.id': 'TRACE-9',
    customer: [
        'display-name': 'Lan'
    ]
])
~~~

JSON tương ứng:

~~~json
{
  "order-id": "ORD-123",
  "trace.id": "TRACE-9",
  "customer": {
    "display-name": "Lan"
  }
}
~~~

Sau này khi viết JSONPath matcher, ký tự đặc biệt trong field thường cần dạng bracket notation, chẳng hạn `$['trace.id']`, thay vì đường dẫn có dấu chấm theo nghĩa phân tách thuộc tính.

### 5.2. Map rỗng

~~~groovy
body(
    metadata: [:]
)
~~~

tương đương:

~~~json
{"metadata": {}}
~~~

Lưu ý `[:]` là **map rỗng** trong Groovy. `[]` lại là **list rỗng**, tạo JSON array `[]`. Việc tráo hai kiểu này là lỗi cấu trúc rất dễ lọt nếu chỉ đọc log dạng text.

## 6. JSON array: list ở cấp con và cấp gốc

Một đơn hàng có thể chứa nhiều dòng sản phẩm:

~~~json
{
  "orderId": "ORD-123",
  "items": [
    {"sku": "BK-1", "quantity": 2, "unitPrice": 50000},
    {"sku": "PEN-7", "quantity": 1, "unitPrice": 10000}
  ]
}
~~~

Trong Groovy:

~~~groovy
body(
    orderId: 'ORD-123',
    items: [
        [sku: 'BK-1', quantity: 2, unitPrice: 50000],
        [sku: 'PEN-7', quantity: 1, unitPrice: 10000]
    ]
)
~~~

- Ngoặc vuông ngoài của `items` tạo **list**.
- Mỗi phần tử `[sku: ..., quantity: ...]` là **map**.
- JSON array có thứ tự. Nếu thứ tự là một phần của cam kết, việc thay đổi vị trí phần tử có thể ảnh hưởng consumer.

### 6.1. Root array

Không phải response nào cũng có object bao ngoài. Ví dụ producer trả trực tiếp danh sách:

~~~json
[
  {"sku": "BK-1", "available": true},
  {"sku": "PEN-7", "available": false}
]
~~~

Groovy DSL có thể biểu diễn list ở cấp body gốc:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body([
        [sku: 'BK-1', available: true],
        [sku: 'PEN-7', available: false]
    ])
}
~~~

Không viết `body(items: [...])` nếu API thực sự trả root array; cách đó sẽ thay đổi schema thành:

~~~json
{
  "items": [
    {"sku": "BK-1", "available": true},
    {"sku": "PEN-7", "available": false}
  ]
}
~~~

Consumer có thể giải mã root array bằng `List<Product>` nhưng không thể tự hiểu object wrapper mới.

### 6.2. List rỗng, null và trường không tồn tại

Đối với trường `items`, ba tình huống dưới đây không đồng nhất:

~~~json
{"items": []}
~~~

~~~json
{"items": null}
~~~

~~~json
{}
~~~

Nếu consumer hiển thị trạng thái “không có dòng sản phẩm” khi `items: []`, nhưng coi `items: null` là lỗi dữ liệu, contract cần làm rõ hành vi chính xác. Không tự đổi `[]` thành `null` chỉ vì cả hai “không chứa phần tử”.

### 6.3. Array có bao nhiêu phần tử?

Một body cố định có thể mô tả ví dụ với hai phần tử. Nhưng dịch vụ tìm kiếm có thể trả 0–20 phần tử tùy dữ liệu. Hãy quyết định consumer phụ thuộc vào:

- **Đúng một tập phần tử cố định**, ví dụ mã các mục cấu hình đã thống nhất.
- **Một danh sách biến độ dài**, trong đó consumer chủ yếu cần kiểu phần tử, trường bắt buộc và giới hạn phân trang.
- **Thứ tự sắp xếp**, nếu API công bố sort order và consumer dựa vào đó.
- **Phân trang**, nếu consumer dựa vào `totalElements`, `page` hoặc `hasNext`.

Trường hợp độ dài biến đổi cần matcher hoặc kịch bản phù hợp, không nên chụp một response bất kỳ thành snapshot cố định cho mọi lần gọi.

## 7. Cùng response body bằng YAML DSL

Spring Cloud Contract hỗ trợ biểu diễn contract HTTP bằng YAML. Ví dụ response có object và array lồng nhau:

~~~yaml
name: get_order_detail
description: Consumer xem chi tiết đơn hàng
request:
  method: GET
  url: /api/orders/ORD-123
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    orderId: ORD-123
    status: CONFIRMED
    paid: true
    totalAmount: 110000
    customer:
      id: CUS-7
      name: Lan
    items:
      - sku: BK-1
        quantity: 2
        unitPrice: 50000
      - sku: PEN-7
        quantity: 1
        unitPrice: 10000
~~~

Trong YAML:

- Một **mapping** dưới `body` tương ứng JSON object.
- Các phần tử mở đầu bằng `-` dưới `items` tương ứng JSON array.
- `true` và `110000` là boolean và number; `ORD-123` là string.
- Độ thụt dòng quyết định cấu trúc lồng nhau, vì vậy phải nhất quán.

Body JSON mà consumer nhận theo contract:

~~~json
{
  "orderId": "ORD-123",
  "status": "CONFIRMED",
  "paid": true,
  "totalAmount": 110000,
  "customer": {
    "id": "CUS-7",
    "name": "Lan"
  },
  "items": [
    {"sku": "BK-1", "quantity": 2, "unitPrice": 50000},
    {"sku": "PEN-7", "quantity": 1, "unitPrice": 10000}
  ]
}
~~~

### 7.1. Bảng đối chiếu Groovy và YAML

| Kiểu dữ liệu | Groovy DSL | YAML DSL | JSON |
| --- | --- | --- | --- |
| String | `status: 'PAID'` | `status: PAID` | `"status":"PAID"` |
| Number | `amount: 1000` | `amount: 1000` | `"amount":1000` |
| Boolean | `paid: true` | `paid: true` | `"paid":true` |
| Null | `coupon: null` | `coupon: null` | `"coupon":null` |
| Object | `customer: [id: 'C-1']` | `customer:` rồi `id: C-1` thụt dòng | `"customer":{"id":"C-1"}` |
| Array | `tags: ['vip', 'web']` | `tags:` rồi `- vip`, `- web` | `"tags":["vip","web"]` |
| Empty object | `metadata: [:]` | `metadata: {}` | `"metadata":{}` |
| Empty array | `items: []` | `items: []` | `"items":[]` |

**Cẩn thận với YAML scalar:** Một số chuỗi trông giống số, boolean hoặc null có thể được parser hiểu thành kiểu khác tùy cách viết và phiên bản parser. Để chắc chắn một ID có số 0 ở đầu hoặc một chuỗi giống từ khóa YAML vẫn là String, hãy đặt trong dấu nháy:

~~~yaml
body:
  zipCode: "00123"
  externalCode: "true"
  remarks: "null"
~~~

Các giá trị này là String, khác với số `123`, boolean `true` hoặc JSON null.

### 7.2. Đừng để YAML response và HTTP response bị trộn cấu trúc

Sai cách thụt dòng:

~~~yaml
response:
  status: 200
body:
  orderId: ORD-123
~~~

Ở đây `body` không nằm trong `response`. Cấu trúc đúng là:

~~~yaml
response:
  status: 200
  body:
    orderId: ORD-123
~~~

Khi dùng YAML DSL, phần lớn lỗi cấu trúc đến từ vị trí của trường và độ thụt dòng chứ không phải từ tên HTTP endpoint.

## 8. Khi nào nên viết JSON raw string?

Groovy DSL cũng cho phép viết JSON bằng chuỗi nhiều dòng:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body('''{
      "orderId": "ORD-123",
      "status": "CONFIRMED",
      "customer": {
        "id": "CUS-7",
        "vip": false
      },
      "items": [
        {"sku": "BK-1", "quantity": 2}
      ]
    }''')
}
~~~

Ưu điểm của cách này là đoạn JSON giống với tài liệu API hoặc ví dụ payload người dùng nhìn thấy. Tuy nhiên:

- Phải đảm bảo JSON hợp lệ; dấu phẩy thừa hoặc quote không đúng làm nội dung không thể parse.
- Dấu ba nháy đơn của Groovy giúp giữ nguyên những ký tự không cần nội suy.
- Trường động hoặc matcher cho JSONPath có thể dễ quản lý hơn nếu body được khai báo theo map/list.
- Với raw text không phải JSON, cách so khớp và kiểu nội dung lại khác; không dùng `Content-Type: application/json` cho text thường.

**Không nên tranh luận rằng một cách “luôn đúng” hơn cách kia.** Chọn một phong cách dễ hiểu, kiểm chứng và bảo trì đối với schema thực tế.

## 9. Giá trị cố định hay giá trị động: chọn mức ràng buộc

Một API có thể trả các trường ổn định và động trong cùng response:

~~~json
{
  "orderId": "ORD-98765",
  "status": "CONFIRMED",
  "createdAt": "2026-11-24T09:30:00Z",
  "currency": "VND"
}
~~~

Nếu consumer phụ thuộc vào `status` và `currency` chính xác, nên ràng buộc các giá trị này. Nhưng `orderId` và `createdAt` có thể thay đổi giữa các lần chạy. Cố định toàn bộ response sẽ khiến generated tests thất bại do dữ liệu hợp lệ biến động.

Spring Cloud Contract hỗ trợ **response body matchers** để diễn tả những thuộc tính cần kiểm tra:

- Giá trị **bằng đúng** một giá trị cam kết.
- Giá trị **khớp regex** (ví dụ mã đơn đúng định dạng).
- Giá trị **đúng kiểu** của JSON.
- Giá trị **đúng định dạng ngày/giờ**.
- Một số yêu cầu về số lượng phần tử trong collection.

Nguyên tắc chọn matcher:

| Giá trị response | Thường nên kiểm tra | Tránh |
| --- | --- | --- |
| `status: CONFIRMED` | Bằng đúng một trạng thái nghiệp vụ | Regex chấp nhận mọi chuỗi |
| `currency: VND` | Bằng đúng nếu consumer dựa vào VND | Bất kỳ mã tiền nào mà không có chuyển đổi |
| `orderId` do server sinh | Đúng định dạng ID đã công bố | Cố định một ID ngẫu nhiên |
| `createdAt` | Kiểu/định dạng timestamp | Cố định thời điểm chạy |
| `totalAmount` | Kiểu số và quy tắc miền giá trị quan trọng | Chấp nhận chuỗi số nếu API định nghĩa Number |
| `items` phân trang | Kiểu phần tử, field cần thiết, giới hạn số lượng | Snapshot toàn bộ danh sách dữ liệu môi trường |

## 10. Response bodyMatchers với JSONPath trong Groovy

**JSONPath** chọn một vị trí trong JSON để kiểm tra. Một số ví dụ:

| JSONPath | Chọn gì? |
| --- | --- |
| `$.orderId` | Field `orderId` ở object gốc |
| `$.customer.id` | Field `id` trong object `customer` |
| `$.items[0].sku` | `sku` của phần tử đầu tiên trong `items` |
| `$.items[*].quantity` | Tập các trường `quantity` trong array |
| `$['trace.id']` | Field gốc có tên chứa dấu chấm |
| `$[0].sku` | `sku` của phần tử đầu của root array |

Ví dụ contract Groovy cho một ID động và một trường số:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_order_with_dynamic_id')

    request {
        method 'GET'
        url '/api/orders/ORD-123'
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }

        body(
            orderId: 'ORD-123',
            status: 'CONFIRMED',
            totalAmount: 250000,
            customer: [
                id: 'CUS-7',
                vip: true
            ]
        )

        bodyMatchers {
            jsonPath('$.orderId', byRegex('ORD-[0-9]+'))
            jsonPath('$.totalAmount', byType())
            jsonPath('$.customer.vip', byType())
        }
    }
}
~~~

Ý nghĩa:

1. `body(...)` cung cấp một response mẫu. Mẫu này cũng hữu ích khi sinh stub cho consumer.
2. `bodyMatchers` chỉ định quy tắc kiểm chứng ở các JSONPath cụ thể cho **response của producer**.
3. `byRegex('ORD-[0-9]+')` yêu cầu ID phù hợp định dạng; nó không buộc ID phải đúng `ORD-123`.
4. `byType()` kiểm tra kiểu theo giá trị mẫu: `totalAmount` là số, `vip` là boolean.
5. Trường `status` không có matcher riêng, vì vậy vẫn có thể được kiểm chứng theo giá trị mẫu `CONFIRMED`.

> Một matcher chỉ kiểm tra các thuộc tính nó được thiết kế để kiểm tra. `byType()` cho trường số **không tự chứng minh** số dương, cách làm tròn hay đúng công thức tính. Với thuộc tính nghiệp vụ quan trọng, hãy bổ sung ràng buộc thích hợp hoặc domain tests.

### 10.1. Các matcher thường dùng

~~~groovy
bodyMatchers {
    jsonPath('$.orderId', byRegex('ORD-[0-9]+'))
    jsonPath('$.status', byEquality())
    jsonPath('$.createdAt', byTimestamp())
    jsonPath('$.customer.id', byType())
}
~~~

Các matcher này minh họa những khả năng khác nhau. Để dùng chúng trong một contract thực tế, **body phải chứa các field tương ứng**: `orderId`, `status`, `createdAt`, `customer.id`. Nếu matcher trỏ tới field không có trong body hoặc schema không hợp lý, công cụ có thể báo lỗi khi tạo test hoặc test thất bại.

### 10.2. Cẩn thận khi áp matcher lên collection

Ví dụ:

~~~groovy
body(
    items: [
        [sku: 'BK-1', quantity: 2],
        [sku: 'PEN-7', quantity: 1]
    ]
)

bodyMatchers {
    jsonPath('$.items[0].sku', byType())
    jsonPath('$.items[1].sku', byType())
}
~~~

Điều này kiểm tra kiểu của hai `sku` được chỉ định, nhưng không tự chứng minh mọi phần tử hay toàn bộ các giá trị khác trong array đều tuân thủ quy tắc mong muốn. Với list biến độ dài, cần thiết kế matcher, giới hạn số phần tử và/hoặc test bổ sung đúng phạm vi consumer sử dụng.

Đừng dùng `$.items[0]` rồi cho rằng mọi `items[*]` đã được kiểm chứng. Đặc biệt, khi một vị trí đã có matcher, cách generated assertion được tạo cho vị trí đó có thể khác với việc so sánh literal không có matcher.

## 11. Response matchers trong YAML DSL

YAML dùng phần `response.matchers.body` để mô tả các quy tắc tương đương với `bodyMatchers` của Groovy:

~~~yaml
name: get_order_with_dynamic_id
request:
  method: GET
  url: /api/orders/ORD-123
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    orderId: ORD-123
    status: CONFIRMED
    totalAmount: 250000
    customer:
      id: CUS-7
      vip: true
  matchers:
    body:
      - path: $.orderId
        type: by_regex
        value: 'ORD-[0-9]+'
      - path: $.totalAmount
        type: by_type
      - path: $.customer.vip
        type: by_type
~~~

Bảng đối chiếu nhanh:

| Groovy DSL | YAML DSL | Công dụng |
| --- | --- | --- |
| `jsonPath('$.orderId', byRegex('ORD-[0-9]+'))` | `path: $.orderId`, `type: by_regex`, `value: 'ORD-[0-9]+'` | Kiểm tra chuỗi theo pattern |
| `jsonPath('$.totalAmount', byType())` | `path: $.totalAmount`, `type: by_type` | Kiểm tra kiểu dựa trên body |
| `jsonPath('$.status', byEquality())` | `path: $.status`, `type: by_equality` | Kiểm tra bằng giá trị mẫu |
| `jsonPath('$.couponCode', byNull())` | `path: $.couponCode`, `type: by_null` | Kiểm tra giá trị null |

Không đặt `matchers` ngang cấp với toàn bộ contract nếu bạn muốn kiểm tra **response**. Nó phải nằm bên trong `response` theo schema của Spring Cloud Contract.

### 11.1. Null matcher và optional field

Khi một field phải xuất hiện với giá trị `null`, hợp đồng có thể mô tả:

~~~groovy
response {
    status OK()
    body(
        couponCode: null
    )
    bodyMatchers {
        jsonPath('$.couponCode', byNull())
    }
}
~~~

Nếu giao diện cho phép field `couponCode` **không xuất hiện**, hãy xác định chính sách schema và thiết kế kịch bản tương ứng. Kiểm tra null không tự đồng nghĩa với kiểm tra field tùy chọn.

## 12. Ví dụ thực tế: response chi tiết đơn hàng có cấu trúc lồng nhau

Bây giờ ghép các kiến thức thành một hợp đồng có ý nghĩa nghiệp vụ. `Order Service` cung cấp:

~~~http
GET /api/orders/ORD-123 HTTP/1.1
Accept: application/json
~~~

Phản hồi mẫu:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "orderId": "ORD-123",
  "status": "CONFIRMED",
  "currency": "VND",
  "totalAmount": 110000,
  "customer": {
    "id": "CUS-7",
    "name": "Lan"
  },
  "items": [
    {"sku": "BK-1", "quantity": 2, "unitPrice": 50000},
    {"sku": "PEN-7", "quantity": 1, "unitPrice": 10000}
  ],
  "discountCode": null
}
~~~

### 12.1. Đề xuất contract Groovy

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_order_detail')

    request {
        method 'GET'
        url '/api/orders/ORD-123'
        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }

        body(
            orderId: 'ORD-123',
            status: 'CONFIRMED',
            currency: 'VND',
            totalAmount: 110000,
            customer: [
                id: 'CUS-7',
                name: 'Lan'
            ],
            items: [
                [sku: 'BK-1', quantity: 2, unitPrice: 50000],
                [sku: 'PEN-7', quantity: 1, unitPrice: 10000]
            ],
            discountCode: null
        )

        bodyMatchers {
            jsonPath('$.orderId', byRegex('ORD-[0-9]+'))
            jsonPath('$.totalAmount', byType())
            jsonPath('$.discountCode', byNull())
        }
    }
}
~~~

Contract giữ các giá trị có ý nghĩa nghiệp vụ như `status: CONFIRMED` và `currency: VND`. ID có thể thay đổi nhưng vẫn cần đúng định dạng. `totalAmount` phải là một giá trị số; tuy nhiên việc tính tổng `2 × 50000 + 1 × 10000 = 110000` vẫn cần được kiểm thử bằng unit/domain test hoặc assertion phù hợp nếu consumer yêu cầu độ chính xác nghiệp vụ tuyệt đối.

### 12.2. Các tình huống mà contract này chưa bao phủ

Hợp đồng trên mô tả một **happy path** cụ thể. Nó chưa khẳng định:

- API trả gì khi `ORD-123` không tồn tại.
- API có hỗ trợ mảng `items` rỗng hay không.
- Consumer làm gì nếu `customer` không tồn tại hoặc `name` là null.
- API xử lý phân trang, cập nhật trạng thái hoặc xác thực như thế nào.
- Producer có thể trả thêm những trường JSON nào mà consumer được phép bỏ qua.

Hãy bổ sung contract theo nhu cầu thực của consumer, tránh tạo hàng trăm trường hợp chỉ để “phủ” mọi sự kết hợp giá trị.

## 13. JSON response lỗi cũng là một hợp đồng

Không chỉ response thành công mới có body. Giả sử consumer hiển thị thông báo riêng khi đơn hàng không tồn tại.

Contract Groovy:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_order_not_found')

    request {
        method 'GET'
        url '/api/orders/ORD-404'
    }

    response {
        status NOT_FOUND()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'ORDER_NOT_FOUND',
            message: 'Order not found'
        )
    }
}
~~~

Phản hồi kỳ vọng:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "code": "ORDER_NOT_FOUND",
  "message": "Order not found"
}
~~~

Điểm cần quyết định với consumer là **trường nào ổn định**:

- `code: ORDER_NOT_FOUND` có thể là mã nghiệp vụ mà consumer dùng để chọn nhánh xử lý.
- `message` có thể chỉ là văn bản hiển thị, có khả năng thay đổi theo bản dịch; không nên ràng buộc cố định nếu các bên không cam kết wording.
- `status 404` có thể là phần quan trọng để consumer phân biệt với `400`, `409` hoặc `500`.

Đừng ràng buộc response lỗi chỉ bởi thông điệp tiếng Anh khi consumer thực sự chỉ cần mã lỗi. Nếu contract có body thì producer phải thực sự trả body đó; một controller ném exception nhưng default error handler trả cấu trúc khác sẽ khiến generated test thất bại.

### 13.1. Các error envelope thường gặp

Một số hệ thống dùng cấu trúc kiểu:

~~~json
{
  "error": {
    "code": "ORDER_NOT_FOUND",
    "details": {
      "orderId": "ORD-404"
    }
  }
}
~~~

Hệ thống khác dùng:

~~~json
{
  "type": "https://example.org/problems/order-not-found",
  "title": "Order not found",
  "status": 404
}
~~~

Đây là **hai schema khác nhau**. Một consumer đã giải mã `error.code` sẽ không tự hiểu `type`. Nếu chọn chuẩn hóa error response, cần thỏa thuận schema trước khi phát hành và có contract test cho các nhánh mà consumer sử dụng.

## 14. Tập dữ liệu, phân trang và tiến hóa response

Một ví dụ API tìm kiếm:

~~~json
{
  "items": [
    {"id": "P-1", "price": 100000},
    {"id": "P-2", "price": 200000}
  ],
  "page": {
    "number": 0,
    "size": 20,
    "totalElements": 42,
    "hasNext": true
  }
}
~~~

Đừng chỉ kiểm tra `items[0].id` rồi bỏ qua metadata phân trang nếu consumer dựa vào `hasNext` để hiện nút “Trang tiếp”. Mặt khác, đừng cố định `totalElements: 42` nếu nó là giá trị thường xuyên biến động và consumer chỉ cần biết trường thuộc kiểu số không âm.

### 14.1. Phân biệt thay đổi tương thích và phá vỡ

| Thay đổi producer | Tác động dự kiến | Hành động đối với contract |
| --- | --- | --- |
| Thêm trường `traceId` mà consumer bỏ qua | Thường tương thích nếu parser bỏ qua field lạ | Không nhất thiết bắt mọi consumer cập nhật |
| Xóa `totalAmount` khi consumer đang đọc | Breaking change | Producer test cần phát hiện |
| Đổi `totalAmount` từ number sang String | Có thể phá vỡ giải mã và tính toán | Kiểm tra kiểu và cập nhật giao diện theo thỏa thuận |
| Đổi `items: []` thành `items: null` | Có thể làm client lặp mảng bị lỗi | Giữ contract về cấu trúc list |
| Đưa `items` vào `data.items` | Thay đổi JSONPath/schema | Đánh giá version/migration với consumer |
| Thêm một giá trị enum mới cho `status` | Tùy khả năng xử lý trạng thái lạ của consumer | Thử nghiệm các nhánh thực tế |
| Đổi thứ tự `items` | Chỉ phá vỡ nếu consumer phụ thuộc thứ tự | Nêu rõ thứ tự khi là cam kết API |
| Thêm trường `discountCode` tùy chọn | Tùy khả năng đọc field thiếu/null của consumer | Xác định optional/null policy |

Một contract tốt tránh **over-specification** (khóa chặt những gì consumer không cần), nhưng vẫn phải đủ cụ thể để phát hiện thay đổi sai kiểu, sai cấu trúc, sai mã lỗi hoặc sai ngữ nghĩa.

### 14.2. Đừng dùng regex để che lỗi cấu trúc

Nếu body mẫu khai báo:

~~~groovy
body(
    totalAmount: 110000
)
~~~

thì trường này có kiểu số. Đặt matcher kiểu “mọi chuỗi” để producer trả `"110000"` mà vẫn được chấp nhận có thể che một breaking change đối với consumer. Matcher phải phản ánh **schema được cam kết**, không nhằm làm test xanh bằng mọi giá.

## 15. Từ response DSL đến generated producer tests và Stub Runner

Khi producer đã có một contract mô tả response, luồng xử lý thường là:

~~~mermaid
flowchart LR
    A["Groovy/YAML contract"] --> B["Sinh producer tests"]
    A --> C["Sinh stub mapping"]
    B --> D["Chạy với producer"]
    D --> E{"Status, headers, body có khớp?"}
    E -- "Không" --> F["Build thất bại"]
    E -- "Có" --> G["Build đạt"]
    C --> H["Đóng gói stub"]
    G --> H
    H --> I["Consumer dùng Stub Runner"]
~~~

**Ở phía producer**, generated test gọi endpoint đã khai báo, sau đó so sánh HTTP status, headers và những phần JSON body mà DSL yêu cầu. Ví dụ nếu controller trả `"paid":"true"` thay vì boolean `true`, kiểm chứng về kiểu phù hợp cần báo lỗi.

**Ở phía consumer**, stub mô phỏng những phản hồi mẫu. Stub Runner giúp consumer thử xem client có gửi request đúng và xử lý response theo cấu trúc đã thống nhất hay không, mà không cần khởi chạy producer thật.

**Sự khác biệt quan trọng:** Matcher ở response thường dùng để xác minh giá trị producer thực trả; stub cho consumer vẫn cần response mẫu hoặc cơ chế templating thích hợp. Một regex ở `$.orderId` không tự biến stub thành một producer có khả năng sinh ID nghiệp vụ đúng cho mọi request.

### 15.1. Base class và fixture vẫn cần thiết

Giả sử contract yêu cầu `GET /api/orders/ORD-123` trả `200`. Nếu test context không có đơn hàng này, producer có thể trả `404` làm test thất bại. Đó có thể là **lỗi setup/fixture**, không phải breaking change của API.

Base test class phía producer thường chuẩn bị dữ liệu hoặc mock dependency phù hợp. Nếu contract mô tả status `CONFIRMED`, test phải đưa producer vào trạng thái có thể trả đúng status đó.

### 15.2. CI phải chạy tests, không chỉ tạo artifact

Với dự án Maven đã cấu hình Spring Cloud Contract Verifier:

~~~bash
./mvnw -B clean verify
~~~

Với dự án Gradle đã cấu hình plugin và tasks tương ứng:

~~~bash
./gradlew clean build
~~~

Bản thân các lệnh trên không tạo ra kiểm chứng có ý nghĩa nếu plugin, base class và đường dẫn contract chưa được cấu hình. Trong CI cần kiểm tra:

1. Contract hiện có được đọc đúng từ source tree.
2. Generated producer tests thật sự được sinh và thực thi, không bị bỏ qua.
3. Test thất bại khi cố ý đổi một field quan trọng từ number sang String hoặc thay đổi JSONPath.
4. Stub artifact được phát hành từ producer đã vượt qua kiểm chứng tương ứng.
5. Consumer dùng đúng phiên bản stub thông qua Stub Runner.

Contract test chỉ bao phủ những gì bạn đã khai báo và chạy. Nó không thay thế kiểm thử công thức tính tiền, performance, security hay hành vi end-to-end nhiều dịch vụ.

## 16. Lỗi thường gặp khi mô tả JSON response

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Không khai báo `Content-Type` mà consumer cần | Kiểm chứng bỏ sót media type | Thêm header JSON vào `response.headers` |
| Dùng `'250000'` thay vì `250000` | JSON String thay vì number | Khai báo literal đúng kiểu |
| Dùng `'false'` thay vì `false` | JSON String thay vì boolean | Đặt boolean không có nháy |
| Nhầm `[]` và `[:]` | JSON array/object đổi kiểu | Chọn list/map theo schema |
| Viết `body(items: ...)` trong khi API trả root array | Thêm một lớp object không có trong API | Dùng body là list gốc |
| Ràng buộc ID ngẫu nhiên bằng literal duy nhất | Test thất bại khi ID thay đổi hợp lệ | Dùng giá trị mẫu và matcher có chủ đích |
| Dùng matcher quá rộng cho `status` | Bỏ lọt breaking change nghiệp vụ | Giữ enum/status quan trọng được kiểm tra rõ |
| Chỉ kiểm tra item đầu tiên | Các phần tử sau có thể sai | Bổ sung kiểm chứng phần tử/collection phù hợp |
| Lẫn `null` với field vắng mặt | Consumer không xử lý đúng optional | Xác định rõ chính sách schema |
| Đặt YAML `body` sai cấp thụt dòng | Contract không hợp lệ hoặc body không được đọc | Đặt `response.body` đúng cấu trúc |
| Trỏ JSONPath sai cấp | Matcher không kiểm tra đúng field | Đối chiếu JSON thực với từng path |
| Hai contract lỗi/thành công có cùng điều kiện request | Stub mapping cạnh tranh | Phân biệt request/fixture hoặc thiết kế scenario |
| Copy toàn bộ entity database sang response contract | Thay đổi nội bộ gây báo lỗi giả | Ràng buộc trường consumer thật sự đọc |
| Sửa contract để test xanh mà chưa đánh giá consumer | Che mất breaking change | Thương lượng API, giữ tương thích hoặc version mới |

### 16.1. Quy trình chẩn đoán một generated test thất bại

Khi generated producer test báo mismatch:

1. Kiểm tra **request** trong contract có thực sự đi vào đúng endpoint.
2. Đọc **HTTP status** thực nhận.
3. Kiểm tra **Content-Type** và headers mà producer trả.
4. Xem **JSON body thực tế**, đối chiếu kiểu, field và cấp lồng nhau.
5. Đối chiếu **JSONPath matchers** để xác định field nào được so khớp chặt, field nào chỉ kiểm tra kiểu.
6. Kiểm tra base test class, dữ liệu đầu vào và serialization; sau đó sửa **producer hoặc contract** theo cam kết thực tế.

Không chỉnh sửa generated test trong thư mục đầu ra của build để che lỗi, vì file đó sẽ được sinh lại.

## 17. Bài thực hành: viết hợp đồng JSON response cho Catalog Service

`Catalog Service` cung cấp:

~~~http
GET /api/products/P-100 HTTP/1.1
Accept: application/json
~~~

JSON mẫu:

~~~json
{
  "productId": "P-100",
  "name": "Wireless Mouse",
  "price": 350000,
  "available": true,
  "category": {
    "id": "ACCESSORIES",
    "displayName": "Phụ kiện"
  },
  "tags": ["wireless", "mouse"],
  "variants": [
    {"sku": "MOUSE-BLACK", "stock": 10},
    {"sku": "MOUSE-WHITE", "stock": 4}
  ],
  "discountCode": null
}
~~~

### Nhiệm vụ A — Viết contract với body đúng cấu trúc

Viết một contract Groovy `get_product_detail` có:

- `request.method` là `GET`, URL `/api/products/P-100`.
- `response.status` là `200` và header `Content-Type: application/json`.
- `productId`, `name`, `tags` có kiểu String/String array phù hợp.
- `category` là object con và `variants` là array gồm hai object.
- `price`, `stock` là number; `available` là boolean.
- `discountCode` là JSON null.

### Nhiệm vụ B — Bổ sung matcher

Giả sử `productId` luôn có dạng `P-` theo sau là chữ số, nhưng mã thực tế có thể thay đổi. Bổ sung `bodyMatchers` kiểm tra định dạng ID mà không cố định số `100`.

Tiếp theo, dùng `byType()` với `$.price` và `$.available` để phát hiện producer đổi number/boolean thành String. Giữ nguyên giá trị `category.id: ACCESSORIES` nếu consumer phụ thuộc vào mã phân loại này.

### Nhiệm vụ C — Chuyển sang YAML

Tạo một biểu diễn YAML tương đương; sử dụng `response.body` với mapping, sequence và `response.matchers.body` cho hai kiểu matcher. Khi kiểm tra build, chỉ kích hoạt một định nghĩa cho mỗi tương tác để tránh test/stub trùng lặp ngoài ý muốn.

### Nhiệm vụ D — Cố ý tạo breaking change

Thử lần lượt các thay đổi sau trong producer:

1. Đổi `price: 350000` thành `price: "350000"`.
2. Đổi `category` từ object thành String.
3. Đổi `variants` từ array thành object.
4. Xóa `productId`.
5. Thêm field `manufacturer: "ABC"` mà consumer không dùng.

Ghi nhận thay đổi nào khiến producer verification thất bại theo những assertions đã thiết kế. Nếu một thay đổi nguy hiểm không bị bắt, hãy xem lại contract hoặc matcher trước khi coi bộ kiểm chứng là đầy đủ.

### Gợi ý lời giải Groovy

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_product_detail')

    request {
        method GET()
        url('/api/products/P-100')
        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }

        body(
            productId: 'P-100',
            name: 'Wireless Mouse',
            price: 350000,
            available: true,
            category: [
                id: 'ACCESSORIES',
                displayName: 'Phụ kiện'
            ],
            tags: ['wireless', 'mouse'],
            variants: [
                [sku: 'MOUSE-BLACK', stock: 10],
                [sku: 'MOUSE-WHITE', stock: 4]
            ],
            discountCode: null
        )

        bodyMatchers {
            jsonPath('$.productId', byRegex('P-[0-9]+'))
            jsonPath('$.price', byType())
            jsonPath('$.available', byType())
            jsonPath('$.discountCode', byNull())
        }
    }
}
~~~

Một số matcher trong ví dụ cho phép giá trị biến đổi. Tuy nhiên, nếu consumer đòi hỏi **giá chính xác trong một kịch bản nghiệp vụ**, dùng `byType()` thôi là quá yếu; cần thêm kiểm chứng giá trị và quy tắc tính phù hợp.

### Gợi ý lời giải YAML

~~~yaml
name: get_product_detail
request:
  method: GET
  url: /api/products/P-100
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    productId: P-100
    name: Wireless Mouse
    price: 350000
    available: true
    category:
      id: ACCESSORIES
      displayName: Phụ kiện
    tags:
      - wireless
      - mouse
    variants:
      - sku: MOUSE-BLACK
        stock: 10
      - sku: MOUSE-WHITE
        stock: 4
    discountCode: null
  matchers:
    body:
      - path: $.productId
        type: by_regex
        value: 'P-[0-9]+'
      - path: $.price
        type: by_type
      - path: $.available
        type: by_type
      - path: $.discountCode
        type: by_null
~~~

**Thảo luận:** Nếu consumer luôn bỏ qua `manufacturer`, việc producer thêm field đó thường không làm đổi ý nghĩa những trường cũ. Tuy vậy, mức độ tương thích thực tế vẫn phụ thuộc vào cách consumer giải mã JSON và mức ràng buộc của contract/test.

## 18. Checklist trước khi hoàn thành contract về JSON response

- [ ] Đã xác định response status và `Content-Type` mà consumer thực sự phụ thuộc.
- [ ] Body khai báo đúng hình dạng gốc: object hay array.
- [ ] Các map/list lồng nhau đúng cấp, không tự thêm hoặc bỏ wrapper.
- [ ] Kiểu String, Number, Boolean và Null được biểu diễn đúng.
- [ ] Phân biệt rõ `null`, field vắng mặt, chuỗi rỗng, array rỗng và object rỗng.
- [ ] Các trường bắt buộc cho consumer được bảo vệ; tránh snapshot trường nội bộ không cần thiết.
- [ ] Các giá trị động dùng matcher phù hợp, các mã/trạng thái nghiệp vụ quan trọng vẫn được kiểm tra chặt.
- [ ] JSONPath trỏ đúng field, kể cả khóa có ký tự đặc biệt.
- [ ] Array được kiểm tra với thứ tự/độ dài/kiểu phần tử đúng mức consumer cần.
- [ ] Nhánh lỗi mà consumer xử lý đã có contract riêng.
- [ ] Base test class có fixture để generated producer test thực thi được.
- [ ] CI thực sự sinh và chạy generated tests, chặn phát hành khi có breaking change.
- [ ] Stub được phát hành theo phiên bản producer đã được kiểm chứng và consumer dùng qua Stub Runner.

## 19. Tài liệu tham khảo

- [Spring Cloud Contract – HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): cách khai báo status, headers và response body.
- [Spring Cloud Contract – Dynamic Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): `bodyMatchers`, JSONPath, matcher kiểu dữ liệu/regex và cách sử dụng YAML matchers.
- [Spring Cloud Contract – Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): cú pháp Groovy/YAML, vai trò của response và nguồn sinh test/stub.

**Ghi nhớ:** Trong Spring Cloud Contract, **JSON response body là cam kết về dữ liệu**, không chỉ là một đoạn văn bản. Hãy mô tả đúng object, array, field lồng nhau và kiểu giá trị; sử dụng matcher cho phần dữ liệu thật sự biến đổi; giữ ràng buộc chặt cho những giá trị consumer cần để xử lý nghiệp vụ. Khi producer tests chạy trong CI và stub được phát hành từ các contract đã xác minh, thay đổi JSON không tương thích sẽ được phát hiện sớm hơn.
