# Giá trị literal, map, list và chuỗi nhiều dòng

## 1. Vì sao phải nắm rõ kiểu dữ liệu trong Groovy DSL?

Spring Cloud Contract giúp producer và consumer thống nhất hành vi HTTP hoặc thông điệp thông qua các tệp hợp đồng có thể kiểm chứng. Trong một contract Groovy, nội dung của `request`, `response` và `outputMessage` thường chứa dữ liệu mô phỏng một request/response thực tế: mã định danh, số tiền, cờ trạng thái, đối tượng JSON, danh sách hàng hóa hoặc đoạn văn nhiều dòng.

Các dữ liệu này được biểu diễn bằng **cú pháp Groovy** trước khi Spring Cloud Contract chuyển thành generated producer tests và stub cho consumer. Viết sai kiểu hoặc cấu trúc ở DSL có thể dẫn tới hai loại sự cố:

- **Contract không biên dịch/không sinh được test:** Ví dụ thiếu dấu ngoặc, khai báo chuỗi sai hoặc dùng cấu trúc Groovy không hợp lệ.
- **Contract hợp lệ nhưng kiểm chứng sai ý định:** Ví dụ producer trả số `2` nhưng contract dùng chuỗi `'2'`, hoặc consumer cần một mảng JSON nhưng contract lại mô tả object.

Bài học thuộc chương **Groovy DSL** của module `SPRING_CLOUD_CONTRACT`. Trọng tâm là các literal, `Map`, `List` và chuỗi nhiều dòng dùng trong mô tả HTTP hoặc messaging, làm nền tảng cho những bước tiếp theo: sinh test phía cung cấp, xuất bản stub, chạy Stub Runner và tích hợp CI để phát hiện thay đổi API không tương thích.

Sau bài này, bạn có thể:

1. Chọn literal có kiểu phù hợp cho chuỗi, số, boolean và `null`.
2. Dùng map Groovy để mô tả đối tượng JSON lồng nhau, kể cả khóa có ký tự đặc biệt.
3. Dùng list và list chứa map để mô tả JSON array có thứ tự.
4. Viết chuỗi nhiều dòng bằng dấu nháy ba và hiểu khi nào Groovy nội suy biểu thức.
5. Phân biệt dữ liệu literal với matcher linh hoạt trong contract test.
6. Viết được một contract HTTP hoàn chỉnh có nhiều kiểu dữ liệu và kiểm tra những lỗi thường gặp trước khi đưa vào CI.

> Phạm vi: Các ví dụ giả định một producer dùng Spring MVC và contract nguồn là Groovy DSL. Chúng minh họa cách **khai báo hợp đồng**, không phải mã xử lý nghiệp vụ hay cấu hình build đầy đủ.

## 2. Vị trí của giá trị Groovy trong một contract

Một tệp contract điển hình:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Lấy thông tin đơn hàng đã được xác nhận'

    request {
        method 'GET'
        url '/api/orders/ORD-100'
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: 'ORD-100',
            status: 'CONFIRMED',
            totalAmount: 120000,
            paid: true
        )
    }
}
~~~

Trong ví dụ này, `Contract.make { ... }` là DSL dành cho Spring Cloud Contract; còn `'ORD-100'`, `120000` và `true` là **literal của Groovy**. Cú pháp `body(orderId: 'ORD-100', ...)` tạo dữ liệu có cấu trúc tương đương map, để framework có thể chuyển thành nội dung JSON và điều kiện kiểm chứng.

Cần phân biệt hai lớp:

| Lớp | Ví dụ | Chức năng |
| --- | --- | --- |
| Cấu trúc contract | `request { ... }`, `response { ... }`, `outputMessage { ... }` | Xác định tương tác nào được kiểm chứng |
| Giá trị bên trong contract | `'CONFIRMED'`, `120000`, `true`, `[sku: 'A']`, `['A', 'B']` | Mô tả dữ liệu được gửi hoặc nhận |

**Giá trị đúng kiểu** rất quan trọng. JSON `{"quantity":2}` khác JSON `{"quantity":"2"}`; với consumer có schema hoặc kiểu dữ liệu chặt chẽ, khác biệt đó có thể làm ứng dụng lỗi dù cùng hiển thị số “2”.

## 3. Literal là gì?

**Literal** là giá trị viết trực tiếp trong mã Groovy, không cần tính toán từ biến hoặc gọi hàm. Những literal dùng thường xuyên trong Spring Cloud Contract:

| Mục đích | Groovy DSL | Kiểu/ý nghĩa trong JSON |
| --- | --- | --- |
| Chuỗi | `'ORD-100'` hoặc `"ORD-100"` | `"ORD-100"` |
| Số nguyên | `2`, `120000` | `2`, `120000` |
| Số thập phân | `19.95` | `19.95` |
| Boolean | `true`, `false` | `true`, `false` |
| Giá trị rỗng | `null` | `null`, khác với thiếu trường |
| Map | `[id: 'C-1', vip: true]` | JSON object |
| List | `['NEW', 'PAID']` | JSON array |
| List chứa map | `[[sku: 'BK-1', qty: 2]]` | JSON array chứa object |

Hãy quan sát từng nhóm trong một response:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body(
        id: 'ORD-100',       // String
        quantity: 2,        // số
        accepted: true,     // boolean
        discountCode: null, // JSON null
        tags: ['web', 'new'] // danh sách chuỗi
    )
}
~~~

Kết quả JSON về mặt dữ liệu:

~~~json
{
  "id": "ORD-100",
  "quantity": 2,
  "accepted": true,
  "discountCode": null,
  "tags": ["web", "new"]
}
~~~

Không tự động đổi `null` thành chuỗi `'null'`, hoặc `false` thành `'false'`. Việc đặt dấu nháy khiến một giá trị chuyển thành **String** và thay đổi hợp đồng.

### 3.1. Literal số nguyên và số thập phân

Groovy hỗ trợ literal số nguyên và số thập phân:

~~~groovy
body(
    quantity: 3,
    price: 49.90,
    taxRate: 0.08,
    totalInVnd: 159000
)
~~~

Giá trị `49.90` ở đây là literal số, không phải chuỗi. Tuy nhiên, representation cụ thể trong generated test, JSON serializer và consumer có thể khác về scale hoặc kiểu số nội bộ. Đối với tiền, hai quy ước thường gặp là:

- **Số nguyên theo đơn vị nhỏ nhất** được API định nghĩa, chẳng hạn `totalInVnd: 159000`.
- **Số thập phân với đơn vị và quy tắc làm tròn rõ ràng**, chẳng hạn `price: 49.90`.

Cần thống nhất hợp đồng về đơn vị, độ chính xác và cách consumer giải mã. Tránh dùng chuỗi `'49.90'` chỉ vì bạn muốn giữ hai chữ số sau dấu thập phân, trừ khi API thật sự định nghĩa trường này là String.

### 3.2. Boolean và null

~~~groovy
body(
    available: true,
    discontinued: false,
    promotionCode: null
)
~~~

Tương đương:

~~~json
{
  "available": true,
  "discontinued": false,
  "promotionCode": null
}
~~~

**`promotionCode: null` không có nghĩa là không có khóa `promotionCode`.** Consumer có thể phân biệt ba trạng thái: có giá trị, giá trị `null` hoặc field vắng mặt. Nếu API cho phép thiếu field, hãy mô tả đúng cam kết; không thêm `null` chỉ để tiện viết DSL.

## 4. Chuỗi đơn và chuỗi kép: điểm giống, khác

Groovy cho phép cả dấu nháy đơn và kép:

~~~groovy
def a = 'CONFIRMED'
def b = "CONFIRMED"
~~~

Khi chỉ có chữ cố định, cả hai đều biểu diễn cùng nội dung. Điểm khác xuất hiện khi chuỗi có **nội suy**:

~~~groovy
def orderId = 'ORD-100'

def literalText = 'Order: $orderId'
def interpolatedText = "Order: $orderId"
~~~

- `literalText` chứa nguyên các ký tự `$orderId`.
- `interpolatedText` trở thành `Order: ORD-100` vì dấu nháy kép hỗ trợ GString interpolation.

Trong contract, nếu một trường phải nhận **chuỗi cố định**, dùng dấu nháy đơn giúp tránh vô tình nội suy biến. Nếu thật sự cần tạo dữ liệu từ biến, có thể dùng Groovy expression, nhưng hãy cân nhắc tính ổn định của contract khi producer và consumer chạy test ở các môi trường khác nhau.

### 4.1. Dấu nháy trong chính nội dung chuỗi

~~~groovy
body(
    message: 'Khách hàng chọn "Giao nhanh"',
    note: "Đơn hàng của khách 'Lan'"
)
~~~

Một cách khác là escape dấu nháy cùng loại bằng dấu gạch chéo ngược:

~~~groovy
body(
    note: 'Khách hàng nói: \'Giao trước 18:00\''
)
~~~

Trường hợp chuỗi có nhiều dấu nháy kép, dùng nháy đơn bên ngoài thường dễ đọc hơn. Không nhất thiết phải escape tất cả dấu `"` trong chuỗi Groovy dùng nháy đơn.

### 4.2. Dấu gạch chéo ngược không phải ký tự vô hại

Groovy vẫn xử lý escape sequence trong những dạng String nhất định, kể cả chuỗi nháy đơn. Ví dụ `'\n'` có thể biểu diễn ký tự xuống dòng, còn `'\\n'` biểu diễn dấu gạch chéo ngược và chữ `n`.

Nếu contract cần chứa ký tự `\` theo nghĩa đen (ví dụ đường dẫn Windows hoặc regex), bạn phải kiểm tra đủ **hai lớp escaping**: cú pháp String của Groovy và định dạng JSON/regex mà dữ liệu hướng tới.

## 5. Map Groovy: biểu diễn một JSON object

**Map** lưu dữ liệu theo cặp khóa–giá trị. Trong Groovy, map literal dùng dấu ngoặc vuông với cú pháp `key: value`:

~~~groovy
def customer = [
    id: 'CUS-7',
    name: 'Lan',
    vip: true
]
~~~

Nếu đưa map này vào body:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body(
        customer: [
            id: 'CUS-7',
            name: 'Lan',
            vip: true
        ]
    )
}
~~~

Ý nghĩa JSON:

~~~json
{
  "customer": {
    "id": "CUS-7",
    "name": "Lan",
    "vip": true
  }
}
~~~

### 5.1. Map lồng nhau

Map có thể chứa map khác ở mọi cấp hợp lý:

~~~groovy
body(
    orderId: 'ORD-100',
    delivery: [
        receiver: [
            name: 'Lan',
            phone: '0900000000'
        ],
        address: [
            city: 'Da Nang',
            postalCode: '550000'
        ]
    ]
)
~~~

Ở đây `delivery`, `receiver` và `address` đều là JSON object. Cấu trúc lồng nhau nên phản ánh schema mà consumer thực tế sử dụng; không thêm trường nội bộ chỉ vì producer có chúng trong entity database.

### 5.2. Truyền map tường minh hay dùng cú pháp đặt tên?

Hai hình thức sau thường biểu đạt cùng dữ liệu body:

~~~groovy
// Cú pháp named arguments, dễ đọc với body đơn giản
body(
    id: 'ORD-100',
    paid: true
)
~~~

~~~groovy
// Tạo map tường minh rồi truyền vào body
body([
    id: 'ORD-100',
    paid: true
])
~~~

Cú pháp thứ nhất thuận tiện cho JSON object. Cú pháp thứ hai hữu ích khi biểu diễn map phức tạp hoặc khi cần làm rõ bạn đang truyền **một map** cho phương thức DSL.

### 5.3. Khóa có dấu gạch ngang, dấu cách hoặc ký tự đặc biệt

Với khóa JSON không phù hợp với định danh Groovy thông thường, hãy đặt khóa trong dấu nháy:

~~~groovy
body([
    'order-id': 'ORD-100',
    'customer name': 'Lan',
    'is-active': true
])
~~~

JSON tương ứng:

~~~json
{
  "order-id": "ORD-100",
  "customer name": "Lan",
  "is-active": true
}
~~~

Dùng `'order-id'` như một khóa map có nháy thay vì viết `order-id` rồi để Groovy hiểu sai là biểu thức trừ.

### 5.4. Không gộp nhầm nhiều trường thành một chuỗi

Sai về ngữ nghĩa nếu consumer cần object:

~~~groovy
body(
    customer: 'id=CUS-7,name=Lan'
)
~~~

Đúng khi consumer cần object:

~~~groovy
body(
    customer: [
        id: 'CUS-7',
        name: 'Lan'
    ]
)
~~~

Đây không chỉ là vấn đề thẩm mỹ mã nguồn. Hợp đồng đầu là JSON string, hợp đồng sau là JSON object với hai field có thể được consumer đọc riêng.

## 6. List Groovy: biểu diễn JSON array

**List** trong Groovy là một tập phần tử có thứ tự, viết bằng dấu ngoặc vuông và dấu phẩy:

~~~groovy
def tags = ['new', 'online', 'promotion']
def quantities = [1, 2, 5]
~~~

Khi dùng trong contract:

~~~groovy
body(
    orderId: 'ORD-100',
    tags: ['new', 'online'],
    quantities: [1, 2, 5]
)
~~~

JSON tương đương:

~~~json
{
  "orderId": "ORD-100",
  "tags": ["new", "online"],
  "quantities": [1, 2, 5]
}
~~~

Khác với map, **thứ tự phần tử trong list có thể mang ý nghĩa**: trình tự các bước, danh sách ưu tiên, kết quả đã sắp xếp hoặc các dòng hàng khi consumer hiển thị theo thứ tự.

### 6.1. List chứa nhiều map

Một tình huống phổ biến là đơn hàng có nhiều dòng sản phẩm:

~~~groovy
body(
    orderId: 'ORD-100',
    items: [
        [
            sku: 'BK-1',
            quantity: 2,
            unitPrice: 55000
        ],
        [
            sku: 'PEN-9',
            quantity: 1,
            unitPrice: 10000
        ]
    ]
)
~~~

JSON tương đương:

~~~json
{
  "orderId": "ORD-100",
  "items": [
    { "sku": "BK-1", "quantity": 2, "unitPrice": 55000 },
    { "sku": "PEN-9", "quantity": 1, "unitPrice": 10000 }
  ]
}
~~~

Đọc từ ngoài vào trong:

1. `body(...)` biểu diễn **object đơn hàng**.
2. `items: [ ... ]` biểu diễn **array các dòng sản phẩm**.
3. Mỗi phần tử `[sku: ..., quantity: ..., unitPrice: ...]` là **một object**.

### 6.2. List lồng list

~~~groovy
body(
    matrix: [
        [1, 2],
        [3, 4]
    ]
)
~~~

Tương đương `{"matrix":[[1,2],[3,4]]}`. Trường hợp này hữu ích khi consumer thực sự nhận ma trận hoặc cấu trúc hai chiều, nhưng đừng lồng list chỉ để mô phỏng nhiều object khác nhau.

### 6.3. Empty list và empty map là hai giá trị khác nhau

~~~groovy
body(
    items: [],    // JSON array rỗng
    metadata: [:]  // JSON object rỗng
)
~~~

Tương đương:

~~~json
{
  "items": [],
  "metadata": {}
}
~~~

Đặc biệt lưu ý `[]` trong Groovy là **list rỗng**, còn `[:]` là **map rỗng**. Trong JSON, `[]` và `{}` khác kiểu; nhiều consumer deserialize trực tiếp vào `List<T>` hoặc object nên không chấp nhận dùng thay thế cho nhau.

### 6.4. Khi body có JSON array ở cấp gốc

Không phải mọi HTTP API đều trả object chứa các field. Nếu endpoint trả trực tiếp một mảng:

~~~json
[
  { "sku": "BK-1", "quantity": 2 },
  { "sku": "PEN-9", "quantity": 1 }
]
~~~

Có thể biểu diễn giá trị body bằng một list chứa map:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body([
        [sku: 'BK-1', quantity: 2],
        [sku: 'PEN-9', quantity: 1]
    ])
}
~~~

Ngoặc vuông **ngoài cùng** là JSON array. Không viết `body(items: [...])` nếu consumer thực tế nhận array ở cấp gốc, vì điều đó sẽ thay đổi schema thành object có field `items`.

## 7. Chuỗi nhiều dòng trong Groovy

Chuỗi nhiều dòng thường xuất hiện trong nội dung mô tả, email template, payload chứa văn bản, HTTP body dạng text hoặc JSON được viết nguyên văn. Groovy hỗ trợ dấu nháy ba:

- `''' ... '''`: chuỗi nhiều dòng **không nội suy** Groovy expression.
- `""" ... """`: chuỗi nhiều dòng **có thể nội suy** biến/biểu thức như dấu nháy kép.

Ví dụ:

~~~groovy
def note = '''Giao vào giờ hành chính.
Gọi trước khi đến.
Không để hàng ở lễ tân.'''
~~~

Giá trị của `note` chứa các ký tự xuống dòng giữa ba câu. Nếu consumer nhận một text có newline, contract có thể cần ràng buộc nội dung này; nếu consumer chỉ cần mô tả bất kỳ, cân nhắc matcher phù hợp để không khóa cứng văn bản ngoài yêu cầu.

### 7.1. Chuỗi nhiều dòng trong JSON field

~~~groovy
body(
    orderId: 'ORD-100',
    deliveryNote: '''Giao vào giờ hành chính.
Gọi trước khi đến.'''
)
~~~

Về mặt dữ liệu, trường `deliveryNote` là **một String có ký tự xuống dòng**. Khi serialize sang JSON, newline thường được escape thành `\n` trong biểu diễn ký tự của JSON, nhưng nội dung sau khi consumer giải mã vẫn có xuống dòng.

Không nhầm:

~~~groovy
// Có xuống dòng thật trong giá trị String
deliveryNote: '''Dòng một
Dòng hai'''
~~~

với:

~~~groovy
// Giá trị gồm chuỗi ký tự dấu gạch chéo ngược và chữ n
deliveryNote: 'Dòng một\\nDòng hai'
~~~

Hai giá trị trên không tương đương: giá trị thứ hai dùng `\\n` trong mã Groovy để giữ dấu gạch chéo ngược ở dữ liệu sau khi giải mã Groovy.

### 7.2. Viết nguyên một JSON body bằng chuỗi nhiều dòng

Khi payload có nhiều cấp lồng nhau, một cách khác là mô tả **nguyên JSON như một String**:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method 'POST'
        url '/api/orders'
        headers {
            contentType(applicationJson())
        }
        body('''{
          "customer": {
            "id": "CUS-7",
            "vip": true
          },
          "items": [
            {"sku": "BK-1", "quantity": 2},
            {"sku": "PEN-9", "quantity": 1}
          ],
          "note": "Giao trong giờ hành chính"
        }''')
    }

    response {
        status CREATED()
    }
}
~~~

Với `Content-Type: application/json`, body string chứa JSON hợp lệ là một cách được Spring Cloud Contract hỗ trợ để mô tả request. Khác với map, bạn có thể nhìn thấy trực tiếp cú pháp JSON mà client gửi.

**Hai cách viết khác nhau, cùng ý nghĩa dữ liệu:**

~~~groovy
// A. Map Groovy
body(
    customer: [id: 'CUS-7', vip: true],
    items: [
        [sku: 'BK-1', quantity: 2],
        [sku: 'PEN-9', quantity: 1]
    ],
    note: 'Giao trong giờ hành chính'
)
~~~

~~~groovy
// B. JSON dạng chuỗi
body('''{
  "customer": {"id": "CUS-7", "vip": true},
  "items": [
    {"sku": "BK-1", "quantity": 2},
    {"sku": "PEN-9", "quantity": 1}
  ],
  "note": "Giao trong giờ hành chính"
}''')
~~~

Nên chọn **map Groovy** khi muốn giữ cú pháp DSL nhất quán và tận dụng các giá trị/matcher lồng trong từng field. Nên chọn **JSON string** khi cần so sánh dễ dàng với một JSON mẫu có sẵn hoặc payload nhiều cấp mà nhóm thấy dễ review hơn dưới dạng JSON. Cả hai đều cần được kiểm chứng bằng generated tests.

### 7.3. Thận trọng với khoảng trắng đầu/cuối và xuống dòng

Với JSON object, dấu cách và xuống dòng ngoài chuỗi thường không làm thay đổi ý nghĩa dữ liệu. Với **text/plain**, email template hoặc trường String, khoảng trắng và ký tự xuống dòng có thể là một phần hợp đồng.

Ví dụ:

~~~groovy
def exactText = '''Line one
Line two'''
~~~

khác với:

~~~groovy
def textWithLeadingNewline = '''
Line one
Line two'''
~~~

Ở ví dụ thứ hai, giá trị bắt đầu bằng newline ngay sau dấu `'''`. Nếu muốn điều khiển khoảng trắng, hãy viết nội dung sát dấu nháy mở, hoặc dùng kỹ thuật `stripIndent()`, `trim()` khi phù hợp và đã kiểm tra kết quả thực tế. Không thêm `trim()` tùy tiện nếu dòng trống và khoảng trắng có ý nghĩa với consumer.

## 8. Nội suy trong chuỗi nhiều dòng: khi nào nên và không nên?

Ví dụ:

~~~groovy
def customerName = 'Lan'

def noInterpolation = '''Xin chào $customerName,
Đơn hàng đang được xử lý.'''

def withInterpolation = """Xin chào $customerName,
Đơn hàng đang được xử lý."""
~~~

Ở `noInterpolation`, văn bản chứa nguyên `$customerName`. Ở `withInterpolation`, Groovy thay `$customerName` bằng `Lan`.

Điều này đặc biệt cần lưu ý khi **body vốn chứa ký hiệu `$`**. Ví dụ một payload tài liệu hoặc mẫu chứa ký hiệu dạng `${field}` có thể bị Groovy xem là một biểu thức nếu được viết bằng triple-double-quoted string. Muốn gửi ký hiệu nguyên văn, dùng `'''...'''` hoặc escape đúng cách.

### 8.1. Không dùng nội suy để che giấu dữ liệu không ổn định

Ví dụ sau có thể chạy được trong Groovy nhưng tạo contract khó tái lập:

~~~groovy
def requestId = java.util.UUID.randomUUID().toString()

Contract.make {
    request {
        method 'POST'
        url '/api/events'
        body(requestId: requestId)
    }
    response {
        status ACCEPTED()
    }
}
~~~

Giá trị contract thay đổi khi load DSL. Điều này dễ khiến generated test, stub được đóng gói và consumer test ở các môi trường khác nhau có dữ liệu không thống nhất. Với dữ liệu động thật sự, nên dùng **giá trị mẫu ổn định cho stub** và cơ chế **matcher** phù hợp cho producer verification, thay vì tự sinh giá trị ngẫu nhiên ngay lúc parse DSL.

## 9. Ví dụ hoàn chỉnh: contract tạo đơn hàng có literal, map, list và multiline text

Giả sử consumer gọi `POST /api/orders` với khách hàng, các dòng sản phẩm và ghi chú giao hàng. Producer trả về mã đơn và tổng tiền.

### 9.1. Yêu cầu nghiệp vụ

| Trường | Kiểu JSON | Ý nghĩa đối với consumer |
| --- | --- | --- |
| `customer.id` | String | Định danh khách hàng |
| `customer.vip` | Boolean | Nhánh nghiệp vụ dành cho khách VIP |
| `items` | Array | Các dòng sản phẩm cần xử lý |
| `items[].quantity` | Number | Số lượng đặt hàng |
| `deliveryNote` | String | Ghi chú, có thể gồm newline |
| `orderId` | String | Mã đơn hàng để consumer tra cứu |
| `totalAmount` | Number | Tổng tiền theo đơn vị đã thống nhất |
| `accepted` | Boolean | Cho biết yêu cầu tạo đơn đã được chấp nhận |

### 9.2. Contract Groovy

Tệp `src/test/resources/contracts/orders/create_order.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('create_order_with_two_items')
    description('Nhận đơn gồm hai sản phẩm và ghi chú nhiều dòng')

    request {
        method 'POST'
        url '/api/orders'

        headers {
            contentType(applicationJson())
            accept(applicationJson())
        }

        body(
            customer: [
                id: 'CUS-7',
                vip: true
            ],
            items: [
                [
                    sku: 'BK-1',
                    quantity: 2,
                    unitPrice: 55000
                ],
                [
                    sku: 'PEN-9',
                    quantity: 1,
                    unitPrice: 10000
                ]
            ],
            deliveryNote: '''Giao vào giờ hành chính.
Gọi trước khi đến.'''
        )
    }

    response {
        status CREATED()
        headers {
            contentType(applicationJson())
        }

        body(
            orderId: 'ORD-100',
            totalAmount: 120000,
            accepted: true,
            tags: ['new', 'online']
        )
    }
}
~~~

Ở đây:

- `'POST'` và `'/api/orders'` là literal String mô tả HTTP method và URL.
- `customer: [id: ..., vip: ...]` là map lồng trong request.
- `items: [[...], [...]]` là list gồm hai map.
- `deliveryNote` là String có newline.
- `totalAmount` là số; `accepted` là boolean; `tags` là list String.
- `status CREATED()` mô tả HTTP status `201`, độc lập với giá trị body.

Tính toán minh họa: hai sản phẩm `BK-1` giá `55.000` mỗi chiếc cộng một sản phẩm `PEN-9` giá `10.000` cho tổng `120.000`, không xét thuế hoặc phí vận chuyển. Thực tế, giá tiền và quy tắc tính cần được producer xử lý đúng trong logic nghiệp vụ; contract chỉ phản ánh **cam kết giao tiếp** ở kịch bản này.

### 9.3. JSON mà consumer gửi

~~~json
{
  "customer": {
    "id": "CUS-7",
    "vip": true
  },
  "items": [
    {"sku": "BK-1", "quantity": 2, "unitPrice": 55000},
    {"sku": "PEN-9", "quantity": 1, "unitPrice": 10000}
  ],
  "deliveryNote": "Giao vào giờ hành chính.\nGọi trước khi đến."
}
~~~

Phản hồi producer được cam kết:

~~~json
{
  "orderId": "ORD-100",
  "totalAmount": 120000,
  "accepted": true,
  "tags": ["new", "online"]
}
~~~

Dấu `\n` trong JSON là **cách biểu diễn một newline trong String**. Nó không đòi consumer phải nhận hai ký tự gạch chéo ngược và chữ `n`; sau khi parse JSON, giá trị chứa xuống dòng thật.

## 10. Cùng kiểu dữ liệu trong messaging DSL

Spring Cloud Contract không chỉ dùng Groovy DSL cho HTTP. Với producer phát message, `outputMessage { body(...) }` cũng có thể chứa literal, map, list và chuỗi nhiều dòng.

Ví dụ `Payment Service` phát sự kiện `PaymentAuthorized`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Phát sự kiện thanh toán được xác nhận'
    label 'paymentAuthorized'

    input {
        triggeredBy('publishAuthorizedPayment()')
    }

    outputMessage {
        sentTo('payments.authorized')

        headers {
            header('contentType', 'application/json')
        }

        body(
            eventType: 'PaymentAuthorized',
            paymentId: 'PAY-9',
            approved: true,
            amount: 120000,
            items: [
                [sku: 'BK-1', quantity: 2],
                [sku: 'PEN-9', quantity: 1]
            ],
            note: '''Đã xác nhận thanh toán.
Chờ hoàn tất giao hàng.'''
        )
    }
}
~~~

Producer verification cho message cần có cách thực thi `publishAuthorizedPayment()` và quan sát message mà producer phát ra, theo cơ chế message verifier/binder được cấu hình. Dữ liệu của `body` tuân theo cách biểu diễn map/list/String tương tự HTTP, nhưng **đích gửi, header và cơ chế kích hoạt khác với một HTTP response**.

Hợp đồng trên không chứng minh message delivery một lần duy nhất, thứ tự broker, retry hay idempotency; những đặc tính đó cần kiểm thử tích hợp phù hợp.

## 11. Literal cố định và matcher trong contract testing

Một literal có nghĩa là bạn mô tả một giá trị cụ thể. Điều đó rất có ích với giá trị thể hiện **ý nghĩa nghiệp vụ ổn định**, chẳng hạn:

~~~groovy
body(
    status: 'CONFIRMED',
    accepted: true,
    currency: 'VND'
)
~~~

Nhưng nhiều giá trị là **động**, ví dụ `orderId` do server sinh ra hoặc `occurredAt` tại thời điểm phát sự kiện. Nếu luôn kiểm tra chúng bằng một literal cố định, test có thể thất bại dù producer vẫn tương thích.

Spring Cloud Contract cho phép phối hợp một **giá trị mẫu** với **matcher**. Ví dụ trong response:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }

    body(
        orderId: 'ORD-123',
        status: 'CONFIRMED'
    )

    bodyMatchers {
        jsonPath('$.orderId', byRegex('ORD-[0-9]+'))
    }
}
~~~

Trong trường hợp này:

- `'ORD-123'` là giá trị mẫu của contract; có thể dùng trong stub dành cho consumer.
- `byRegex('ORD-[0-9]+')` giúp generated producer test chấp nhận các mã đơn đúng định dạng.
- `status: 'CONFIRMED'` vẫn là literal vì consumer cần đúng trạng thái nghiệp vụ.

**Matcher không sửa ý nghĩa dữ liệu.** Nếu consumer cần status chính xác `CONFIRMED` để ra quyết định, việc chuyển thành matcher “bất kỳ chuỗi nào” sẽ khiến contract không còn bắt được breaking change. Nếu consumer yêu cầu số, đừng dùng matcher chuỗi để hợp thức hóa việc producer trả String sai kiểu.

## 12. Những lỗi thường gặp với literal, map, list và multiline string

| Lỗi | Ví dụ/biểu hiện | Hậu quả | Cách sửa |
| --- | --- | --- | --- |
| Biến số thành String | `quantity: '2'` | JSON nhận String thay vì number | Dùng `quantity: 2` nếu schema yêu cầu number |
| Biến boolean thành String | `active: 'false'` | Consumer đọc boolean có thể lỗi | Dùng `active: false` |
| Nhầm null với String | `note: 'null'` | Không còn là JSON null | Dùng `note: null` hoặc bỏ field nếu contract cho phép vắng |
| Nhầm empty map với empty list | `metadata: []` | JSON array thay vì object | Dùng `metadata: [:]` |
| Thiếu một cấp list | `items: [sku: 'A']` | Object thay vì array object | Dùng `items: [[sku: 'A']]` |
| Dùng khóa có dấu gạch ngang mà không nháy | `order-id: 'X'` | Cú pháp dễ bị hiểu sai | Viết `'order-id': 'X'` trong map |
| Thêm newline ngoài ý muốn | Dấu nháy ba bắt đầu ở dòng trước nội dung | String có newline đầu | Đặt chữ sát dấu mở hoặc xử lý newline có chủ đích |
| Nội suy nhầm | Dùng `"""$value"""` cho payload muốn giữ nguyên ký tự `$` | Groovy thay nội dung | Chọn `'''...'''` khi cần giữ placeholder nguyên dạng |
| Gõ raw JSON không hợp lệ | Dấu phẩy thừa, khóa thiếu nháy trong chuỗi JSON | Không parse được JSON | Đối chiếu JSON với định dạng chuẩn hoặc dùng map Groovy |
| Kỳ vọng trật tự key trong object | So sánh toàn bộ JSON theo vị trí key | Test quá chặt so với ý nghĩa JSON | Kiểm chứng field và giá trị quan trọng |
| Không phân biệt list có thứ tự | Đảo `['first', 'second']` | Consumer có thể xử lý sai thứ tự | Ràng buộc thứ tự khi API cam kết thứ tự |
| Sinh ID ngẫu nhiên khi load DSL | `UUID.randomUUID()` trong contract | Stub và test có dữ liệu khó tái lập | Dùng giá trị mẫu ổn định + matcher có chủ đích |
| Gom cấu trúc JSON thành một String | `customer: 'id=C-1'` | Mất schema object | Dùng `customer: [id: 'C-1']` |
| Tạo object sai cấp gốc | `body(items: [...])` khi API trả array | Response schema bị đổi | Dùng `body([...])` cho root array |

### Lỗi tinh vi: map literal có khóa trùng

~~~groovy
body([
    status: 'PENDING',
    status: 'CONFIRMED'
])
~~~

Groovy map không thể đại diện hai field cùng tên theo cách bạn mong muốn; một giá trị có thể ghi đè giá trị còn lại khi map được xây dựng. Hãy chọn đúng một định nghĩa cho một key, hoặc tách thành **hai contract** nếu đó là hai tình huống khác nhau.

### Lỗi tinh vi: viết JSON nguyên văn nhưng quên Content-Type

~~~groovy
request {
    method 'POST'
    url '/api/orders'
    body('''{"quantity": 2}''')
}
~~~

Đoạn trên mô tả body, nhưng consumer thực tế có thể gửi `Content-Type: application/json`. Khi header là một phần của giao tiếp đã thống nhất, nên mô tả rõ:

~~~groovy
headers {
    contentType(applicationJson())
}
~~~

Làm vậy giúp contract kiểm chứng rằng producer và consumer thống nhất không chỉ payload mà cả media type.

## 13. Từ DSL tới producer test, stub và CI

Dữ liệu trong contract ảnh hưởng trực tiếp tới vòng đời Spring Cloud Contract:

~~~mermaid
flowchart LR
    A["Groovy DSL: literal/map/list/multiline"] --> B["Sinh producer tests"]
    A --> C["Sinh stub mappings"]
    B --> D{"Producer đáp ứng dữ liệu và kiểu?"}
    D -- "Không" --> E["Sửa producer hoặc thương lượng contract"]
    D -- "Có" --> F["Build hợp lệ"]
    C --> G["Consumer kiểm thử với Stub Runner"]
    F --> H["Phát hành stub đã xác minh"]
    H --> G
~~~

Ví dụ, consumer mong `quantity` là JSON number. Nếu producer chuyển sang `"quantity": "2"`, generated producer test từ hợp đồng cũ có thể phát hiện sai kiểu/giá trị theo điều kiện matcher đã chọn, rồi CI chặn việc phát hành.

Khi đổi một field từ `tags: []` sang `tags: [:]`, bạn đã đổi **JSON array thành JSON object**, một thay đổi có khả năng phá vỡ consumer. Hãy đánh giá compatibility trước khi cập nhật contract chỉ để làm test xanh.

Một quy trình kiểm chứng thực hành:

1. Đặt tệp Groovy DSL trong thư mục nguồn contract được build tool cấu hình, thường là `src/test/resources/contracts`.
2. Thiết lập base test class và dữ liệu cần thiết ở producer.
3. Chạy build có sinh **và thực thi** generated tests, ví dụ `./mvnw -B clean verify` với dự án Maven đã cấu hình Spring Cloud Contract.
4. Kiểm tra test thất bại khi cố ý thay kiểu dữ liệu hoặc xóa một trường mà consumer dùng.
5. Chỉ đóng gói/phát hành stub sau khi producer đã đạt những kiểm chứng cần thiết; cho consumer kiểm thử với Stub Runner.
6. Giữ contract, generated test và stub đúng phiên bản mà pipeline phát hành.

Chỉ tạo file Groovy DSL chưa đủ để bảo đảm test được chạy. Maven/Gradle plugin, dependency Spring Cloud Contract, base class và test runner phải được cấu hình phù hợp phiên bản của dự án.

## 14. Thực hành: viết hợp đồng cho API giỏ hàng

`Cart Service` cung cấp `POST /api/carts/checkout` và nhận dữ liệu:

~~~json
{
  "customerId": "CUS-42",
  "items": [
    {"sku": "MOUSE-1", "quantity": 1, "unitPrice": 350000},
    {"sku": "PAD-2", "quantity": 2, "unitPrice": 50000}
  ],
  "coupon": null,
  "urgent": false,
  "note": "Giao sau 17:00.\nGọi trước 15 phút."
}
~~~

Kết quả mong đợi:

~~~json
{
  "checkoutId": "CHK-9",
  "totalAmount": 450000,
  "accepted": true,
  "warnings": []
}
~~~

### Yêu cầu

1. Viết một `Contract.make` bằng Groovy DSL, khai báo method, URL, `Content-Type` và hai body.
2. Dùng literal đúng kiểu cho `customerId`, `urgent`, `coupon`, `quantity` và `totalAmount`.
3. Dùng list chứa map để biểu diễn hai dòng `items`.
4. Dùng chuỗi ba dấu nháy cho `note` để chứa newline thật.
5. Dùng list rỗng cho `warnings`; giải thích vì sao không dùng map rỗng.
6. Thử đổi producer trả `"totalAmount": "450000"`; nêu lý do contract cũ phải phát hiện thay đổi này nếu consumer dựa vào số.

### Một lời giải tham khảo

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('checkout_cart_success')

    request {
        method 'POST'
        url '/api/carts/checkout'
        headers {
            contentType(applicationJson())
        }
        body(
            customerId: 'CUS-42',
            items: [
                [sku: 'MOUSE-1', quantity: 1, unitPrice: 350000],
                [sku: 'PAD-2', quantity: 2, unitPrice: 50000]
            ],
            coupon: null,
            urgent: false,
            note: '''Giao sau 17:00.
Gọi trước 15 phút.'''
        )
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            checkoutId: 'CHK-9',
            totalAmount: 450000,
            accepted: true,
            warnings: []
        )
    }
}
~~~

Ở lời giải này, `warnings: []` thể hiện **không có phần tử cảnh báo**. Nếu thay bằng `warnings: [:]`, consumer sẽ nhận object rỗng thay vì array rỗng. Tương tự, `totalAmount: 450000` là số; việc producer chuyển sang chuỗi có thể làm hỏng xử lý tính tiền của consumer.

### Câu hỏi mở rộng

- Nếu producer tạo `checkoutId` ngẫu nhiên, nên giữ literal hay thêm matcher? Hãy nêu giá trị mẫu và định dạng cần cam kết.
- Nếu `coupon` là field tùy chọn và có thể bị loại bỏ hoàn toàn, cách kiểm chứng nên thay đổi như thế nào?
- Nếu `items` là một danh sách được sắp xếp theo thứ tự người dùng chọn, việc đảo hai phần tử có phải thay đổi tương thích không?
- Nếu email xác nhận thanh toán được gửi qua message broker, có nên dùng lại cấu trúc `items` trong `outputMessage`? Những trường nào consumer của message thực sự cần?

**Gợi ý:** Matcher có ích cho ID động; trường tùy chọn cần chính sách có/vắng/null rõ ràng; list có thể yêu cầu giữ thứ tự; hợp đồng messaging nên dựa trên subscriber thực sự và không sao chép toàn bộ HTTP payload theo quán tính.

## 15. Checklist trước khi hoàn thành một contract Groovy

- [ ] Mọi String literal có dấu nháy phù hợp; không nội suy ngoài ý muốn.
- [ ] Số và boolean dùng literal đúng kiểu, không bọc trong chuỗi nếu API không định nghĩa như vậy.
- [ ] `null` chỉ xuất hiện khi schema thật sự cho phép hoặc yêu cầu giá trị null.
- [ ] Object JSON được biểu diễn bằng map; array JSON được biểu diễn bằng list.
- [ ] Map rỗng dùng `[:]` và list rỗng dùng `[]`, không hoán đổi.
- [ ] List chứa object có đúng hai lớp ngoặc vuông như `[[sku: 'A']]`.
- [ ] Khóa có dấu gạch ngang, khoảng trắng hoặc ký tự đặc biệt được trích dẫn đúng.
- [ ] Dữ liệu nhiều dòng được kiểm tra newline và khoảng trắng đầu/cuối.
- [ ] Chuỗi raw JSON là JSON hợp lệ, có header media type theo giao tiếp đã cam kết.
- [ ] Matcher chỉ dùng khi cần; không làm yếu đi trường hợp cần giá trị nghiệp vụ chính xác.
- [ ] Contract có fixture/thiết lập producer phù hợp để generated test chạy được.
- [ ] Đã xác nhận generated tests được thực thi trong CI; stub phát hành cùng phiên bản producer đã kiểm chứng.

**Ghi nhớ:** Trong Spring Cloud Contract Groovy DSL, **literal** quyết định kiểu và giá trị; **map** mô tả JSON object; **list** mô tả JSON array; và **chuỗi nhiều dòng** giữ những phần văn bản có newline hoặc JSON viết trực tiếp. Hiểu đúng bốn yếu tố này giúp hợp đồng kiểm chứng đúng hành vi mà consumer phụ thuộc, thay vì chỉ tạo ra một tệp DSL trông hợp lệ.
