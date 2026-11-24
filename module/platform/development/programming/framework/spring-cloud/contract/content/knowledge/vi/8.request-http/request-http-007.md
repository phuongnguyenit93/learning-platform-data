# JSON request body và cấu trúc lồng nhau

## Mục tiêu bài học

Khi **consumer** gọi API HTTP của **producer**, JSON request body thường có nhiều lớp: thông tin khách hàng, địa chỉ, danh sách sản phẩm và các tùy chọn của từng sản phẩm. Nếu kiểm thử hợp đồng chỉ kiểm tra method và URL mà bỏ qua body, producer có thể thay đổi cấu trúc đầu vào, làm consumer lỗi dù endpoint vẫn tồn tại.

Với **Spring Cloud Contract**, ta dùng **Groovy DSL** hoặc **YAML DSL** để mô tả request và response. Từ hợp đồng này, công cụ sinh kiểm thử phía producer, tạo stub để consumer thử nghiệm qua **Stub Runner** và giúp CI phát hiện thay đổi API không tương thích.

Sau bài này, bạn có thể:

- Phân tích cấu trúc object, array và các giá trị lồng nhau của JSON request.
- Viết body bằng map/list trong Groovy DSL hoặc mapping/sequence trong YAML DSL.
- Dùng JSONPath và request body matchers cho các trường động, giữ giá trị mẫu ổn định cho producer tests.
- Phân biệt string, number, boolean, null, chuỗi rỗng và thuộc tính vắng mặt.
- Thiết kế các kịch bản hợp lệ và không hợp lệ, đặc biệt với các trường trong mảng.
- Giải thích giới hạn bằng chứng mà generated producer tests và stub tests cung cấp.

## 1. Hợp đồng JSON lồng nhau mô tả điều gì?

Giả sử ứng dụng Checkout gọi Order Service để tạo một đơn hàng.

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json
~~~

Request body mẫu:

~~~json
{
  "customer": {
    "id": "CUS-101",
    "address": {
      "city": "Ha Noi",
      "postalCode": "100000"
    }
  },
  "items": [
    {
      "sku": "BOOK-001",
      "quantity": 2,
      "options": {
        "giftWrap": true
      }
    },
    {
      "sku": "PEN-002",
      "quantity": 1,
      "options": {
        "giftWrap": false
      }
    }
  ],
  "delivery": {
    "method": "STANDARD"
  }
}
~~~

Response minh họa:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"orderId":"ORD-9001","status":"CREATED"}
~~~

Các nhánh cấu trúc JSON:

~~~text
request body (object)
├── customer (object)
│   ├── id (string)
│   └── address (object)
│       ├── city (string)
│       └── postalCode (string)
├── items (array)
│   ├── [0] (object)
│   │   ├── sku (string)
│   │   ├── quantity (number)
│   │   └── options (object)
│   │       └── giftWrap (boolean)
│   └── [1] (object)
│       ├── sku (string)
│       ├── quantity (number)
│       └── options (object)
│           └── giftWrap (boolean)
└── delivery (object)
    └── method (string)
~~~

**Đường dẫn đến trường** có thể được biểu diễn bằng JSONPath:

| JSONPath | Kiểu | Ý nghĩa với consumer/producer |
| --- | --- | --- |
| **$.customer.id** | string | Mã khách hàng |
| **$.customer.address.city** | string | Thành phố nhận hàng |
| **$.customer.address.postalCode** | string | Mã bưu chính; giữ chuỗi để không mất số 0 đầu |
| **$.items** | array | Danh sách sản phẩm |
| **$.items[0].sku** | string | SKU phần tử đầu tiên trong ví dụ |
| **$.items[0].quantity** | number | Số lượng sản phẩm đầu tiên |
| **$.items[1].options.giftWrap** | boolean | Tùy chọn gói quà ở phần tử thứ hai |
| **$.delivery.method** | string | Phương thức giao hàng |

Những cam kết này phản ánh **giao diện tích hợp**. Chúng không bắt buộc producer phải dùng một Java DTO hay bảng database cụ thể. Producer có thể thay cách deserialize, lưu trữ, validate nội bộ miễn hành vi công khai đã thỏa thuận vẫn được giữ.

## 2. Viết JSON request body bằng Groovy DSL

Groovy DSL biểu diễn JSON object bằng **map** và JSON array bằng **list**. Một hợp đồng tạo đơn hàng có body lồng nhiều cấp:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Tạo đơn hàng gồm địa chỉ và nhiều sản phẩm"

    request {
        method POST()
        url "/api/orders"
        headers {
            contentType(applicationJson())
            header("Accept", "application/json")
        }
        body(
            customer: [
                id: "CUS-101",
                address: [
                    city: "Ha Noi",
                    postalCode: "100000"
                ]
            ],
            items: [
                [
                    sku: "BOOK-001",
                    quantity: 2,
                    options: [giftWrap: true]
                ],
                [
                    sku: "PEN-002",
                    quantity: 1,
                    options: [giftWrap: false]
                ]
            ],
            delivery: [
                method: "STANDARD"
            ]
        )
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(orderId: "ORD-9001", status: "CREATED")
    }
}
~~~

Giải thích:

1. **body(...)** chứa các cặp key–value tạo object ngoài cùng.
2. **customer: [...]** và **address: [...]** là map lồng nhau.
3. **items: [[...], [...]]** là list gồm hai map, tương ứng một JSON array.
4. **quantity: 2** giữ kiểu số; **giftWrap: true** giữ kiểu boolean.
5. **postalCode: "100000"** là chuỗi. Với những mã có thể bắt đầu bằng 0, việc chuyển sang số làm thay đổi dữ liệu.

Trong Groovy, dấu ngoặc vuông có thể tạo **map** hoặc **list** tùy biểu thức bên trong. Vì thế không thể chỉ nhìn số lượng ngoặc mà suy ra JSON đúng: nên đối chiếu cấu trúc JSON được sinh và request mà generated test thực sự gửi.

Kịch bản này dùng giá trị xác định để producer test có input ổn định. **ORD-9001** là response mẫu của test; không có nghĩa producer ngoài production luôn trả đúng ID này.

## 3. Viết cùng hành vi bằng YAML DSL

Trong YAML, **mapping** dùng key và dấu hai chấm, còn **sequence** dùng dấu gạch đầu dòng. Cùng hợp đồng:

~~~yaml
description: "Tạo đơn hàng gồm địa chỉ và nhiều sản phẩm"
name: create_order_with_nested_body
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
    Accept: application/json
  body:
    customer:
      id: "CUS-101"
      address:
        city: "Ha Noi"
        postalCode: "100000"
    items:
      - sku: "BOOK-001"
        quantity: 2
        options:
          giftWrap: true
      - sku: "PEN-002"
        quantity: 1
        options:
          giftWrap: false
    delivery:
      method: STANDARD
response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    orderId: "ORD-9001"
    status: CREATED
~~~

YAML dễ đọc khi object có nhiều cấp nhưng rất nhạy với **thụt lề**. Nếu dấu gạch đầu dòng của một sản phẩm hoặc trường **options** nằm sai cấp, mô hình JSON nhận được có thể khác ý định.

Để tránh lỗi, cần chú ý:

- Dùng dấu cách để thụt lề, không dùng tab.
- Dùng ký hiệu **-** cho từng phần tử mảng.
- Đặt string dễ bị hiểu như số hoặc boolean trong dấu nháy, nhất là mã định danh và mã bưu chính.
- Kiểm tra trường đang thuộc cấp **customer**, **address**, **items** hay **delivery**.
- Tránh biến toàn bộ JSON thành một chuỗi dài khi có thể khai báo dưới dạng YAML có cấu trúc.

## 4. Body cố định và matcher khác nhau ra sao?

Request mẫu có **customer.id = CUS-101**, nhưng Checkout có thể gửi nhiều mã khách hàng hợp lệ khác. Nếu stub chỉ nhận một chuỗi cố định, các request hợp lệ khác có thể không match. Spring Cloud Contract cho phép khai báo **request body matchers** để một phần body được đối chiếu theo điều kiện.

| Thuộc tính | Điều consumer/producer cần thống nhất | Cách biểu diễn |
| --- | --- | --- |
| Method và URL | POST /api/orders | Giá trị cụ thể |
| Content-Type | JSON | Header cụ thể |
| customer.id | Theo định dạng mã khách hàng | Regex nếu phù hợp |
| items[0].quantity | Có kiểu số; nghiệp vụ thường đòi số nguyên dương | Matcher kiểu và test validation bổ sung |
| delivery.method | STANDARD là một phương thức được hỗ trợ | Giá trị cụ thể hoặc tập giá trị có chủ đích |
| giftWrap | Boolean | Dữ liệu mẫu hoặc matcher kiểu |

Một điểm quan trọng: **request matcher chủ yếu ảnh hưởng đến cách stub đối chiếu request của consumer**, trong khi generated test phía producer thường **gửi các giá trị ví dụ đã khai báo**. Kiểm thử producer PASS với CUS-101 không tự động chứng minh mọi ID phù hợp regex đều thành công.

### Groovy bodyMatchers với JSONPath

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Tạo đơn hàng với mã khách hàng đúng định dạng"

    request {
        method POST()
        url "/api/orders"
        headers {
            contentType(applicationJson())
        }
        body(
            customer: [id: "CUS-101"],
            items: [[sku: "BOOK-001", quantity: 2]],
            delivery: [method: "STANDARD"]
        )
        bodyMatchers {
            jsonPath('$.customer.id', byRegex('CUS-[0-9]{3}'))
            jsonPath('$.items[0].quantity', byType())
        }
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(orderId: "ORD-9001", status: "CREATED")
    }
}
~~~

- **$.customer.id** chọn trường id bên trong customer. Regex mô tả CUS- theo sau là ba chữ số.
- **$.items[0].quantity** chọn quantity của phần tử đầu tiên. **byType()** biểu đạt ràng buộc kiểu theo cơ chế matcher.
- Các trường còn lại vẫn là một phần body mẫu; phải kiểm tra stub mapping thực tế để hiểu cách công cụ phối hợp matcher với các điều kiện body khác.

**byType() không có nghĩa quantity phải dương.** Giá trị -1 vẫn là một số. Ràng buộc nghiệp vụ như lớn hơn 0 hoặc giới hạn số lượng cần được mô tả và xác minh bằng cơ chế thích hợp, thường bao gồm các kịch bản producer trả lỗi cho input không hợp lệ.

### YAML request matchers

Ví dụ YAML dùng cùng ý tưởng, tập trung vào hai trường:

~~~yaml
description: "Tạo đơn hàng với request matchers"
name: create_order_with_matchers
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
  body:
    customer:
      id: "CUS-101"
    items:
      - sku: "BOOK-001"
        quantity: 2
    delivery:
      method: STANDARD
  matchers:
    body:
      - path: $.customer.id
        type: by_regex
        value: "CUS-[0-9]{3}"
      - path: $.items[0].quantity
        type: by_type
response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    orderId: "ORD-9001"
    status: CREATED
~~~

Đây là dạng matcher thường gặp trong YAML DSL. **Cú pháp và các tùy chọn matcher cần được đối chiếu với phiên bản Spring Cloud Contract đang dùng** và xác nhận bằng stub/test thực tế được sinh. Không nên suy ra mọi helper trong Groovy đều có tên tương tự trong YAML ở tất cả phiên bản.

## 5. JSONPath khi object và array nhiều cấp

JSONPath là cú pháp chọn một phần của tài liệu JSON. Các ví dụ thường dùng:

| Biểu thức JSONPath | Ý nghĩa |
| --- | --- |
| **$.customer** | Toàn object customer |
| **$.customer.address.city** | Thành phố trong object address |
| **$.items[0].sku** | SKU phần tử đầu tiên |
| **$.items[1].quantity** | Quantity phần tử thứ hai |
| **$.items[*].sku** | Chọn SKU của nhiều phần tử (wildcard) |
| **$['customer']['address']['postalCode']** | Cách chọn field bằng bracket notation |

Wildcard **[*]** có thể dùng để chỉ nhiều phần tử, nhưng **không tự đảm bảo số phần tử**, không tự kiểm tra trùng SKU hay thứ tự. Tùy cơ chế match được chọn, một matcher trên một phần tử có thể không kiểm tra phần tử khác. Nếu API yêu cầu ít nhất một sản phẩm, tối đa mười sản phẩm hoặc các SKU không được trùng nhau, cần quy tắc và test riêng cho những điều kiện đó.

Nếu tên property thực sự chứa dấu chấm hoặc ký tự đặc biệt, bracket notation giúp phân biệt tên property với dấu chấm ngăn cấp object. Luôn kiểm tra JSONPath với body ví dụ trước khi dùng trong hợp đồng lớn.

## 6. Phân biệt number, string, boolean, null và field vắng mặt

Xem JSON:

~~~json
{
  "quantity": 2,
  "quantityText": "2",
  "giftWrap": true,
  "giftWrapText": "true",
  "deliveryNote": null,
  "emptyNote": ""
}
~~~

| Giá trị | Loại | Hậu quả có thể gặp |
| --- | --- | --- |
| Số **2** | JSON number | Hợp lệ cho quantity nếu API yêu cầu số |
| Chuỗi **"2"** | JSON string | Deserializer hoặc validation có thể xử lý khác |
| **true** | JSON boolean | Khác chuỗi chữ **"true"** |
| **null** | JSON null | Field tồn tại nhưng không mang giá trị |
| **""** | Chuỗi rỗng | Field tồn tại và có độ dài 0 |
| Field không tồn tại | Absent | Producer có thể dùng mặc định hoặc trả lỗi thiếu input |

Ví dụ ba trạng thái của trường ghi chú tùy chọn:

~~~json
{"delivery":{"method":"STANDARD"}}
~~~

~~~json
{"delivery":{"method":"STANDARD","instructions":null}}
~~~

~~~json
{"delivery":{"method":"STANDARD","instructions":""}}
~~~

Đây là **ba request khác nhau**. Không được tự giả định Spring, Jackson hay một schema cụ thể luôn coi chúng tương đương. Đội producer và consumer cần thống nhất chính sách: field có thể thiếu không, null có được chấp nhận không, chuỗi rỗng có bị từ chối không.

Trong YAML nên viết rõ kiểu:

~~~yaml
postalCode: "00100"
quantity: 2
giftWrap: false
instructions: null
~~~

Trong Groovy dùng số, boolean và **null** theo đúng kiểu. Nếu consumer yêu cầu số nguyên, đừng tạo mẫu bằng một string biểu diễn số chỉ vì producer tình cờ tự chuyển kiểu trong môi trường hiện tại.

**Một matcher theo kiểu chưa chứng minh null và absent đều hợp lệ.** Khi hai trường hợp có ý nghĩa khác nhau, hãy thêm hợp đồng hoặc test xác minh riêng thay vì coi một kịch bản là đại diện cho tất cả.

## 7. Mảng JSON: kích thước, thứ tự và từng phần tử

Mảng **items** tạo ra nhiều câu hỏi nghiệp vụ hơn một object:

1. Cho phép mảng rỗng hay bắt buộc ít nhất một sản phẩm?
2. Mỗi phần tử có cần **sku** và **quantity** không?
3. Có cho phép một SKU xuất hiện hai lần không?
4. **options** có bắt buộc ở mọi phần tử không?
5. Thứ tự sản phẩm có ý nghĩa không?
6. Số phần tử tối đa bao nhiêu?

Một body có JSON đúng cú pháp nhưng không hợp lệ về nghiệp vụ:

~~~json
{
  "customer": {"id": "CUS-101"},
  "items": [{"sku": "BOOK-001", "quantity": -1}],
  "delivery": {"method": "STANDARD"}
}
~~~

Hợp đồng thành công với quantity 2 không chứng minh producer từ chối quantity -1. Tương tự, chỉ match **$.items[0].quantity** không kiểm tra tất cả phần tử trong một mảng có nhiều sản phẩm.

Khi thiết kế matcher cho array:

- Nếu cần một **mẫu cố định**, khai báo từng phần tử để dễ biết producer nhận đúng body nào.
- Nếu cần cho phép **danh sách có kích thước biến động**, phải cân nhắc cả quy tắc về phần tử và số lượng phần tử; chỉ một JSONPath trên phần tử đầu không đủ.
- Nếu thứ tự không có ý nghĩa nghiệp vụ, tránh biến thứ tự thành ràng buộc công khai không cần thiết.
- Nếu mọi phần tử phải thỏa một quy tắc, cần kiểm chứng quy tắc trên toàn mảng bằng khả năng matcher phù hợp hoặc kiểm thử validation khác.

## 8. Viết một kịch bản lỗi cho field lồng nhau

Hãy mô tả trường hợp Order Service **từ chối số lượng âm** với HTTP 400:

~~~yaml
description: "Từ chối đơn hàng có quantity âm"
name: reject_order_with_negative_quantity
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
  body:
    customer:
      id: "CUS-101"
    items:
      - sku: "BOOK-001"
        quantity: -1
    delivery:
      method: STANDARD
response:
  status: 400
  headers:
    Content-Type: application/json
  body:
    code: INVALID_ORDER
    errors:
      - field: "items[0].quantity"
        reason: MUST_BE_POSITIVE
~~~

**INVALID_ORDER**, **MUST_BE_POSITIVE** và mảng **errors** là schema lỗi **do ví dụ giả định**. Chúng chỉ nên trở thành hợp đồng thực tế khi producer và consumer đã thống nhất. Spring Cloud Contract không quy định sẵn response lỗi có cấu trúc này.

Nếu consumer hiển thị lỗi theo đường dẫn **items[0].quantity**, việc đổi field lỗi thành một chuỗi khác cũng có thể phá vỡ consumer. Một hợp đồng về nhánh lỗi phải đặc tả **đúng những gì consumer dùng**, không chỉ mã HTTP.

Nên có thêm kịch bản lỗi khi consumer thực sự phân nhánh theo các tình huống: customer thiếu, items rỗng, SKU không hợp lệ, quantity sai kiểu hoặc vượt giới hạn. Tránh đưa nhiều lỗi vào cùng một body nếu producer chỉ trả lỗi đầu tiên, vì thứ tự validation nội bộ có thể làm test không ổn định.

## 9. Một hợp đồng phục vụ producer test và consumer stub ra sao?

~~~mermaid
flowchart TD
    A["Groovy/YAML contract với JSON request body"] --> B["Spring Cloud Contract"]
    B --> C["Sinh producer test"]
    B --> D["Sinh stub/mapping"]
    C --> E["Gửi request mẫu đến producer"]
    E --> F["Đối chiếu status/header/body phản hồi"]
    D --> G["Consumer dùng Stub Runner"]
    G --> H["Stub đối chiếu request consumer"]
    H --> I["Trả phản hồi để consumer xử lý"]
~~~

**Phía producer:** generated test tạo request từ ví dụ trong contract và gửi tới producer trong môi trường kiểm thử, rồi đối chiếu response. Nếu producer đổi cấu trúc nhận request mà không còn xử lý JSON cũ, test có thể thất bại, giúp CI phát hiện khả năng không tương thích.

**Phía consumer:** stub match request theo các điều kiện được sinh ra từ DSL, bao gồm method, URL, header và body. Nếu matcher quá chặt, request hợp lệ sẽ không nhận stub response; nếu quá lỏng, một request mà producer thật từ chối vẫn có thể được stub trả thành công.

**Bằng chứng phải gắn cùng phiên bản:** producer test PASS với một revision contract nhưng consumer test chạy với stub cũ thì chưa đủ để khẳng định producer mới tương thích với consumer đó. Stub cần được sinh/phát hành từ hợp đồng đã xác minh, có phiên bản rõ ràng và được consumer test qua Stub Runner.

## 10. Ví dụ thay đổi schema làm hỏng consumer

Checkout cũ gửi:

~~~json
{
  "customer": {
    "id": "CUS-101",
    "address": {"city": "Ha Noi"}
  },
  "items": [{"sku": "BOOK-001", "quantity": 2}]
}
~~~

Producer mới chỉ chấp nhận:

~~~json
{
  "customerId": "CUS-101",
  "shippingAddress": {"city": "Ha Noi"},
  "lines": [{"productCode": "BOOK-001", "count": 2}]
}
~~~

Dù hai request có nội dung nghiệp vụ tương tự, chúng **khác cấu trúc công khai**:

| JSONPath cũ | JSONPath mới | Nguy cơ |
| --- | --- | --- |
| **$.customer.id** | **$.customerId** | Producer không còn đọc customer.id |
| **$.customer.address.city** | **$.shippingAddress.city** | Địa chỉ nằm ở nhánh khác |
| **$.items[0].sku** | **$.lines[0].productCode** | Đổi tên mảng và trường con |
| **$.items[0].quantity** | **$.lines[0].count** | Thay đổi tên trường số lượng |

Producer có thể trả HTTP 400 hoặc xử lý dữ liệu mặc định không như mong đợi. Giữ nguyên endpoint POST /api/orders **không đủ** để bảo đảm tương thích.

Các hướng xử lý có thể là: tiếp tục nhận schema cũ trong giai đoạn chuyển tiếp; cập nhật consumer trước bằng cơ chế hỗ trợ hai dạng; hoặc tạo phiên bản API mới với kế hoạch rollout/rollback rõ ràng. Trước khi phát hành, chạy lại producer test theo hợp đồng của consumer còn đang hoạt động và kiểm tra consumer với stub tương ứng bản producer mới.

## 11. Lỗi thường gặp khi mô tả body JSON

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Viết **items** là object thay vì array | Producer/stub đọc body sai cấu trúc | Dùng list Groovy hoặc sequence YAML |
| Thụt lề sai YAML | Field bị đưa sang object cha khác | Đối chiếu request được sinh |
| Gửi **"quantity": "2"** thay vì số | Khác kiểu JSON | Khai báo số đúng |
| Chỉ match phần tử đầu tiên của mảng | Bỏ sót lỗi ở phần tử khác | Thiết kế độ phủ cho toàn mảng |
| Regex quá rộng | Stub chấp nhận dữ liệu không mong muốn | Ràng buộc theo định dạng thực |
| Không phân biệt null và absent | Producer hiểu sai optional field | Tạo kịch bản riêng khi cần |
| Chỉ test request thành công | Validation bị hỏng khó phát hiện | Thêm nhánh lỗi quan trọng |
| Dùng random trong expected body | Test và stub không tái lập được | Dùng fixture ổn định hoặc matcher |
| So khớp cả JSON như chuỗi thứ tự cố định | Test dễ fail do serializer đổi thứ tự key | Dùng cấu trúc JSON/matcher phù hợp |
| Consumer CI vẫn dùng stub cũ | PASS không phản ánh schema mới | Chốt stub version và chạy lại |

Khi consumer không nhận response từ stub, hãy kiểm tra method, URL, Content-Type, JSONPath, matcher body và mapping sinh ra trước khi kết luận producer thật bị lỗi.

## 12. Bài tập thực hành

### Bài tập A — Chuyển JSON sang Groovy

Cho request:

~~~json
{
  "buyer": {"id": "CUS-101"},
  "lines": [
    {"sku": "A-001", "quantity": 1},
    {"sku": "B-002", "quantity": 3}
  ],
  "metadata": {"source": "WEB", "gift": false}
}
~~~

**Yêu cầu:** viết phần body của hợp đồng POST /api/orders bằng map/list, giữ nguyên kiểu số và boolean. Gợi ý:

~~~groovy
body(
    buyer: [id: "CUS-101"],
    lines: [
        [sku: "A-001", quantity: 1],
        [sku: "B-002", quantity: 3]
    ],
    metadata: [source: "WEB", gift: false]
)
~~~

### Bài tập B — Chọn matcher

Consumer có thể gửi buyer.id bất kỳ theo định dạng CUS- và ba chữ số, còn quantity phải có kiểu số.

**Yêu cầu:** viết JSONPath và matcher tương ứng. Giải thích vì sao matcher kiểu số chưa chứng minh giá trị dương.

**Gợi ý:** JSONPath **$.buyer.id** với regex **CUS-[0-9]{3}**; **$.lines[0].quantity** với **byType()**. Giá trị -1 vẫn có kiểu số.

### Bài tập C — Optional field

Producer định nghĩa delivery.instructions là ghi chú tùy chọn. Consumer có thể bỏ field, gửi null hoặc gửi chuỗi rỗng.

**Yêu cầu:** thống nhất cách xử lý từng trường hợp và viết hai hoặc ba hợp đồng để chứng minh chính sách đó. Không giả định rằng cả ba biểu diễn tự động tương đương.

### Bài tập D — API thay đổi tên field

Producer đổi **lines[].quantity** thành **lines[].count**. Consumer cũ vẫn gửi quantity và kiểm thử stub của tuần trước tiếp tục PASS.

**Yêu cầu:** nêu lý do kết quả cũ chưa đủ bằng chứng, xác định hợp đồng nào cần chạy lại và cách dùng Stub Runner để kiểm tra consumer với phiên bản producer mới.

## 13. Checklist khi thiết kế request JSON lồng nhau

- [ ] Method, URL, Content-Type và cấu trúc body được khai báo rõ.
- [ ] Object, array và cấp lồng nhau đúng với JSON consumer gửi.
- [ ] Kiểu number/string/boolean/null khớp giao diện công khai.
- [ ] Trường bắt buộc, tùy chọn, null, absent và chuỗi rỗng có quy tắc rõ.
- [ ] Với array, quy tắc số phần tử, thứ tự và từng phần tử được xem xét khi cần.
- [ ] Dữ liệu mẫu cố định và trường cần matcher được phân biệt có chủ đích.
- [ ] JSONPath chọn đúng cấp; matcher đủ chặt với yêu cầu consumer.
- [ ] Có kịch bản lỗi quan trọng cho field lồng nhau sai hoặc thiếu.
- [ ] Generated producer test thực sự chạy và kiểm chứng response.
- [ ] Stub được sinh từ đúng contract revision, không bị bỏ sót mapping.
- [ ] Consumer test bằng Stub Runner dùng đúng phiên bản stub mới.
- [ ] Mọi thay đổi tên field, kiểu hoặc cấu trúc request được đánh giá tương thích trước phát hành.

**Ghi nhớ:** JSON request body là **một phần hợp đồng tích hợp**, gồm tên trường, kiểu dữ liệu và quan hệ object/array lồng nhau. Groovy DSL dùng map/list, YAML DSL dùng mapping/sequence, còn JSONPath và request body matchers giúp mô tả những quy tắc linh hoạt có chủ đích. Chỉ khi producer test và consumer stub test cùng xác minh đúng hành vi, CI mới có cơ sở phát hiện thay đổi request schema không tương thích.
