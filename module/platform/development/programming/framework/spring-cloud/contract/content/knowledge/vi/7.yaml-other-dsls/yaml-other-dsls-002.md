# Cấu trúc request, response và phần matcher trong YAML

## 1. Mục tiêu của bài học

**Spring Cloud Contract (SCC)** cho phép mô tả hành vi giao tiếp giữa dịch vụ cung cấp (**producer**) và dịch vụ sử dụng (**consumer**) bằng các hợp đồng có thể kiểm chứng. Với HTTP, một contract nêu rõ request nào được chấp nhận, response nào phải được trả về và những giá trị nào cần so khớp. Với giao tiếp bất đồng bộ, SCC cũng có thể mô tả thông điệp được phát hoặc nhận.

SCC hỗ trợ nhiều DSL như **Groovy, YAML, Java và Kotlin**. Trong bài này, ta tập trung vào **YAML DSL**: cách tổ chức hai khối `request`, `response` và các khối `matchers` nằm bên trong chúng. YAML thích hợp khi nhóm muốn một định dạng dữ liệu khai báo, dễ diff và dễ review mà không cần viết closure Groovy.

Đặt contract đúng cú pháp chỉ là bước đầu. Khi plugin SCC xử lý YAML, nó có thể **sinh kiểm thử cho producer** và **sinh stub để consumer dùng qua Stub Runner**. Nếu dùng matcher sai phía, test có thể quá nghiêm ngặt, quá dễ dãi hoặc phản ánh sai yêu cầu của consumer. Bài học vì vậy giải thích cả cú pháp **và ý nghĩa kiểm chứng**.

Sau khi học, bạn có thể:

1. Đọc và viết một YAML contract HTTP hoàn chỉnh với `request`, `response` và `matchers`.
2. Phân biệt matcher áp dụng cho request ở **stub** với matcher kiểm tra response ở **generated producer test**.
3. Sử dụng JSONPath, regex, kiểm tra kiểu, thời gian, giá trị rỗng, header và query parameter.
4. Tránh các lỗi thường gặp về thụt lề YAML, kiểu dữ liệu, regex và đường dẫn JSONPath.
5. Kiểm chứng contract bằng generated test, stub artifact, Stub Runner và các bước CI.

## 2. Hình dung luồng chạy trước khi xem cú pháp

Giả sử **Checkout Service** cần hỏi **Inventory Service** xem một sản phẩm còn hàng hay không. Contract định nghĩa request hợp lệ và response mà consumer cần đọc.

~~~mermaid
flowchart TD
    A["Tệp YAML contract"] --> B["Spring Cloud Contract"]
    B --> C["Generated test phía producer"]
    B --> D["Stub / WireMock mapping"]
    C --> E["Chạy với ứng dụng Inventory thật"]
    D --> F["Stub Runner trong test Checkout"]
    E --> G{"Producer thỏa contract?"}
    F --> H{"Consumer xử lý stub đúng?"}
    G -- "Không" --> I["Chặn thay đổi / sửa contract hoặc code"]
    H -- "Không" --> I
    G -- "Có" --> J["Tổng hợp kết quả CI"]
    H -- "Có" --> J
~~~

Có hai phía cần nhớ:

- **Trong request:** matcher mô tả những điều kiện mà **request do consumer gửi đến stub** phải thỏa để stub chọn phản hồi phù hợp. Khi sinh producer test, SCC cũng tạo một request cụ thể để gọi producer thật.
- **Trong response:** matcher mô tả những điều kiện mà **response do producer thật trả về** phải thỏa trong generated test. Stub phía consumer thường trả mẫu response tương ứng với `body`, có thể qua cơ chế template khi được cấu hình.

Một cặp test producer và consumer xanh chỉ có ý nghĩa với các tình huống được contract thực sự mô tả và stub **đúng phiên bản ứng viên**. Contract không tự thay thế test bảo mật, cơ sở dữ liệu, timeout hay toàn bộ kiểm thử end-to-end.

## 3. Khung YAML contract HTTP

Tệp YAML có thể đặt dưới thư mục contract được plugin cấu hình, ví dụ với Maven:

~~~text
inventory-service/
└── src/
    └── test/
        └── resources/
            └── contracts/
                └── inventory/
                    └── stock-available.yml
~~~

Ví dụ tối thiểu:

~~~yaml
description: Trả tồn kho cho một SKU
name: stock_available

request:
  method: GET
  url: /api/inventory/SKU-123
  headers:
    Accept: application/json

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    available: true
    quantity: 12
~~~

Các trường chính:

| Vị trí | Trường | Vai trò |
|---|---|---|
| Cấp gốc | `description` | Diễn giải tình huống nghiệp vụ cho người đọc |
| Cấp gốc | `name` | Đặt tên cho contract, thuận tiện nhận diện test/mapping |
| `request` | `method` | HTTP method, ví dụ `GET`, `POST`, `PUT`, `DELETE` |
| `request` | `url` hoặc `urlPath` | Địa chỉ đích hoặc phần path, tùy cách mô tả request |
| `request` | `headers` | Header consumer gửi, chẳng hạn `Accept` |
| `request` | `body` | Payload request, nếu phương thức có body |
| `request` | `matchers` | Quy tắc so khớp request để stub nhận đúng tình huống |
| `response` | `status` | HTTP status dưới dạng số, ví dụ `200` hoặc `201` |
| `response` | `headers` | Header producer trả lại, ví dụ `Content-Type` |
| `response` | `body` | Payload mà producer cần trả và stub minh họa |
| `response` | `matchers` | Quy tắc xác nhận response của producer trong generated test |

**Đặc biệt:** `matchers` là một khối **bên trong** `request` hoặc `response`, không phải một tập quy tắc tùy ý đặt ở cấp gốc. Cùng tên `matchers` nhưng ý nghĩa khác nhau theo phía của giao tiếp.

Một contract có thể không cần `body` nếu response chỉ là `204 No Content`, hoặc không có request body với `GET`. Chỉ mô tả những đặc điểm thực sự thuộc hợp đồng.

## 4. Hiểu request: method, URL và query parameter

### 4.1. `url` và `urlPath`

Một request thường xác định `method` và một trong hai biểu diễn URL:

~~~yaml
request:
  method: GET
  url: /api/inventory/SKU-123
~~~

Khi query parameters là thành phần đáng chú ý, có thể biểu diễn riêng:

~~~yaml
request:
  method: GET
  urlPath: /api/inventory/SKU-123
  queryParameters:
    includeWarehouses: "true"
    locale: vi
~~~

Việc tách `urlPath` khỏi `queryParameters` khiến người đọc thấy rõ consumer đang yêu cầu dữ liệu gì. HTTP query parameter là dữ liệu ở URL, nên `"true"` trong ví dụ được xem là **chuỗi** chứ không phải boolean JSON.

Không đặt dấu hỏi `?` kèm query vào `urlPath` nếu bạn đã mô tả chúng trong `queryParameters`. Hãy chọn một biểu diễn rõ ràng và nhất quán để tránh vô tình định nghĩa hai lần cùng điều kiện.

### 4.2. Request headers

~~~yaml
request:
  method: GET
  url: /api/inventory/SKU-123
  headers:
    Accept: application/json
    X-Channel: checkout
~~~

Header trong request xác định thông tin consumer gửi. Một số hệ thống còn cần `Authorization`, version header hoặc correlation ID. Không đưa token thật vào contract; dùng dữ liệu giả lập hoặc matcher thích hợp.

### 4.3. Request body

Với POST tạo phiếu giữ hàng:

~~~yaml
request:
  method: POST
  url: /api/reservations
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 2
    customerRef: CUST-DEMO
~~~

YAML map ở `body` được hiểu là cấu trúc dữ liệu tương ứng khi gửi JSON. Dữ liệu mẫu này vừa giúp SCC sinh request cụ thể cho producer test, vừa cung cấp những giá trị có thể được dùng làm điều kiện cho stub.

Không nên ghi `quantity: "2"` nếu API nhận số JSON `2`: hai kiểu dữ liệu khác nhau có thể khiến test chạy sai ý nghĩa.

## 5. Hiểu response: status, header và body

Response là hành vi producer hứa thực hiện khi nhận request phù hợp:

~~~yaml
response:
  status: 200
  headers:
    Content-Type: application/json
    Cache-Control: no-store
  body:
    sku: SKU-123
    available: true
    quantity: 12
    warehouses:
      - code: HCM-01
        quantity: 7
      - code: HN-02
        quantity: 5
~~~

Trong đó:

- `status: 200` là HTTP status **số nguyên**.
- `Content-Type: application/json` thể hiện loại nội dung trả về; nó ảnh hưởng cả cách client giải mã dữ liệu.
- `available: true` là boolean, không phải chuỗi `"true"`.
- `warehouses` là một mảng các đối tượng. YAML dùng `-` để mở một phần tử mảng.
- Tên trường như `available`, `quantity` và ngữ nghĩa của chúng là một phần hành vi mà consumer có thể phụ thuộc.

Ví dụ response không có body:

~~~yaml
response:
  status: 204
~~~

Không cần tạo body giả cho trường hợp `204`, vì như vậy có thể khiến contract và giao thức HTTP mâu thuẫn.

## 6. Vì sao matcher quan trọng?

Nếu không có matcher, một giá trị cố định trong contract có thể trở thành kỳ vọng quá chặt. Giả sử producer tạo mã phiếu `RSV-1001` trong một lần chạy và `RSV-1002` ở lần sau. Consumer chỉ cần một mã hợp lệ dạng `RSV-<số>`; buộc response phải luôn là `RSV-1001` sẽ khiến producer test thất bại dù ứng dụng đúng nghiệp vụ.

Ngược lại, nếu stub chấp nhận **bất kỳ** request mà không kiểm tra `sku`, `quantity` hoặc header, consumer test có thể xanh dù client gửi dữ liệu sai.

Matcher giải quyết hai nhu cầu:

| Nơi đặt | Mục đích chính | Câu hỏi |
|---|---|---|
| `request.matchers` | Mô tả điều kiện mà request phải thỏa để **stub** nhận ra request của consumer | Consumer có gọi API đúng định dạng, header, query, body không? |
| `response.matchers` | Mô tả cách **generated test** kiểm tra response producer thật | Producer có trả dữ liệu đúng kiểu/định dạng/giá trị đã cam kết không? |

SCC dùng giá trị mẫu trong `body` làm cơ sở cho phía còn lại của luồng kiểm chứng. Ví dụ, một matcher trên response không có nghĩa stub tự sinh ngẫu nhiên một response khác mỗi lần: stub vẫn có thể trả **giá trị mẫu** trong contract. Cần phân biệt rõ **dữ liệu trả trong stub** với **quy tắc xác nhận producer**.

## 7. Cú pháp chung của matcher trên body

Trong YAML DSL, các matcher body thường là **danh sách** ở:

~~~yaml
request:
  body:
    sku: SKU-123
  matchers:
    body:
      - path: $.sku
        type: by_regex
        value: '^SKU-[A-Z0-9-]+$'
~~~

Mỗi phần tử mô tả một quy tắc:

| Thuộc tính | Ý nghĩa |
|---|---|
| `path` | JSONPath trỏ đến giá trị trong payload, ví dụ `$.sku` |
| `type` | Phương pháp so khớp như `by_regex`, `by_equality`, `by_type` |
| `value` | Giá trị hoặc regex dùng với matcher tương ứng |
| `predefined` | Regex dựng sẵn của SCC, ví dụ `uuid` hoặc `non_empty` |
| `regexType` | Khai báo kiểu kết quả cho regex, ví dụ `as_integer`, `as_boolean` |
| `minOccurrence` / `maxOccurrence` | Giới hạn số phần tử trong một số trường hợp matcher kiểu dữ liệu/tập hợp |

**Quy tắc quan trọng:** JSONPath phải tham chiếu phần tử **có thật trong `body` mẫu**. Ví dụ `path: $.id` là sai nếu fixture chỉ có `reservationId`. Một số JSONPath hợp lệ về cú pháp nhưng trỏ đến giá trị không tồn tại vẫn sẽ làm việc sinh test hoặc kiểm chứng hoạt động sai kỳ vọng.

Nên bắt đầu với matcher đơn giản, chạy generated test/stub, rồi chỉ mở rộng matcher khi thực sự có dữ liệu động cần chấp nhận.

## 8. Các matcher phổ biến trên response

Giả sử producer trả dữ liệu tạo phiếu:

~~~yaml
response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    reservationId: RSV-1001
    status: CREATED
    acceptedQuantity: 2
    expiresAt: "2026-11-24T11:30:00"
    note: null
  matchers:
    body:
      - path: $.reservationId
        type: by_regex
        value: '^RSV-[0-9]+$'
      - path: $.status
        type: by_equality
      - path: $.acceptedQuantity
        type: by_type
      - path: $.expiresAt
        type: by_timestamp
      - path: $.note
        type: by_null
~~~

Các quy tắc ở đây có ý nghĩa khác nhau:

- **`by_regex`** ở `reservationId`: chấp nhận chuỗi hợp mẫu, ví dụ `RSV-2002`, thay vì bắt buộc `RSV-1001`.
- **`by_equality`** ở `status`: kỳ vọng đúng giá trị `CREATED` đã đặt trong `body`.
- **`by_type`** ở `acceptedQuantity`: xác nhận kiểu dữ liệu phù hợp mẫu `2`; **không** có nghĩa giá trị phải bằng 2.
- **`by_timestamp`** ở `expiresAt`: xác nhận định dạng thời điểm theo quy tắc SCC; **không** thay thế kiểm tra nghiệp vụ “phải ở tương lai ít nhất 15 phút”.
- **`by_null`** ở `note`: xác nhận giá trị là `null`, khác với trường hoàn toàn không tồn tại.

Nếu consumer cần xác nhận `acceptedQuantity` bằng chính số lượng được yêu cầu, chỉ dùng `by_type` là chưa đủ; cần matcher hoặc phép kiểm chứng nghiệp vụ phù hợp để thể hiện quan hệ đó.

### Những loại matcher cần ghi nhớ

| `type` | Dùng khi | Hành vi kiểm tra |
|---|---|---|
| `by_equality` | Giá trị phải cố định | So sánh với mẫu ở body |
| `by_regex` | Chuỗi hoặc số theo định dạng | So với biểu thức chính quy |
| `by_type` | Giá trị có thể thay đổi nhưng kiểu phải đúng | So kiểu với giá trị mẫu |
| `by_date` | Ngày | Xác nhận định dạng ngày |
| `by_time` | Giờ | Xác nhận định dạng giờ |
| `by_timestamp` | Ngày giờ | Xác nhận định dạng timestamp |
| `by_null` | Giá trị phải rỗng thực sự | Xác nhận JSON `null` |
| `by_command` | Quy tắc tùy biến khi test producer | Gọi hàm xác nhận trong test base |

`by_command` chỉ có ý nghĩa khi hàm Java/Groovy tương ứng được chuẩn bị đúng trong test base hoặc import phù hợp. Không nên dùng matcher tùy biến chỉ để thay thế một phép so sánh có sẵn.

## 9. Regex và regexType: kiểm soát tính linh hoạt

Một regex thường nên được viết bằng **chuỗi YAML đặt trong dấu nháy đơn** để giảm nhu cầu escape dấu gạch chéo ngược:

~~~yaml
response:
  body:
    reservationId: RSV-1001
    referenceNumber: 120045
  matchers:
    body:
      - path: $.reservationId
        type: by_regex
        value: '^RSV-[0-9]{4}$'
      - path: $.referenceNumber
        type: by_regex
        value: '^[0-9]{6}$'
        regexType: as_integer
~~~

Với chuỗi `reservationId`, regex định nghĩa định dạng mã. Với trường `referenceNumber` là **số JSON**, `regexType: as_integer` diễn tả kiểu mong muốn cho regex thay vì chỉ xử lý như chuỗi.

Một số giá trị `regexType` có trong DSL gồm:

- `as_string`
- `as_integer`
- `as_long`
- `as_double`
- `as_float`
- `as_short`
- `as_boolean`

Cần so khớp cả **mẫu** và **kiểu**. Ví dụ `referenceNumber: "120045"` trong body là chuỗi JSON, khác `referenceNumber: 120045` là số. Đừng dùng regex để che việc model dữ liệu đang sai kiểu.

### Regex dựng sẵn

Thay vì viết regex từ đầu, YAML matcher có thể dùng `predefined`:

~~~yaml
response:
  body:
    requestId: "550e8400-e29b-41d4-a716-446655440000"
    email: "customer@example.test"
  matchers:
    body:
      - path: $.requestId
        type: by_regex
        predefined: uuid
      - path: $.email
        type: by_regex
        predefined: email
~~~

Các mẫu dựng sẵn thường gặp: `uuid`, `email`, `number`, `any_boolean`, `iso_date`, `iso_date_time`, `iso_time`, `non_empty`, `non_blank`. Danh sách và cách chuyển kiểu cần đối chiếu tài liệu **đúng phiên bản SCC** mà dự án đang dùng.

Regex dựng sẵn xác minh **hình thức**, không tự xác minh logic nghiệp vụ như email có tồn tại, UUID có trong database hoặc thời điểm có nằm trong giới hạn xử lý.

## 10. Matcher cho request body: producer nhận đúng mẫu

Với API tạo giữ hàng, request có thể chứa mã tham chiếu thay đổi theo từng consumer:

~~~yaml
description: Tạo phiếu giữ hàng
name: create_reservation

request:
  method: POST
  url: /api/reservations
  headers:
    Content-Type: application/json
  body:
    clientRequestId: REQ-1001
    sku: SKU-123
    quantity: 2
  matchers:
    body:
      - path: $.clientRequestId
        type: by_regex
        value: '^REQ-[0-9]{4}$'
      - path: $.sku
        type: by_regex
        value: '^SKU-[A-Z0-9-]+$'
      - path: $.quantity
        type: by_regex
        value: '^[1-9][0-9]*$'
        regexType: as_integer

response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    reservationId: RSV-1001
    status: CREATED
~~~

Khi Stub Runner dùng stub đã sinh, request gửi đến phải thỏa các điều kiện cần thiết để match tình huống tạo phiếu. Ví dụ `quantity` phải là số nguyên dương theo định dạng đã chọn. Generated producer test có thể dùng **dữ liệu mẫu** `REQ-1001`, `SKU-123`, `2` để gọi code producer thật.

Nếu nghiệp vụ có giới hạn `quantity` từ 1 đến 100, regex `^[1-9][0-9]*$` vẫn cho phép 101 và nhiều số lớn khác; cần thêm quy tắc phù hợp hoặc contract trường hợp lỗi riêng. Một matcher đúng cú pháp chưa chắc đủ chặt về nghiệp vụ.

## 11. Matcher cho URL, header và query parameter

Body không phải phần duy nhất cần so khớp. Một số API phụ thuộc chặt vào path, header hoặc query. YAML DSL có các matcher tương ứng dưới `request.matchers`.

### 11.1. Match URL

~~~yaml
request:
  method: GET
  urlPath: /api/inventory/SKU-123
  matchers:
    url:
      regex: '/api/inventory/SKU-[A-Z0-9-]+'
~~~

Đường dẫn mẫu vẫn hiện diện trong `urlPath`; matcher cho phép stub nhận những đường dẫn phù hợp regex khi cơ chế mapping được sinh từ contract. Cần xác nhận hành vi cụ thể của plugin với cấu hình URL và các query parameters của dự án.

### 11.2. Match header

~~~yaml
request:
  method: GET
  url: /api/inventory/SKU-123
  headers:
    Accept: application/json
    X-Channel: checkout
  matchers:
    headers:
      - key: Accept
        regex: 'application/json.*'
      - key: X-Channel
        regex: 'checkout|mobile'
~~~

Matcher `headers` dùng `key` và cách so khớp phù hợp, ví dụ `regex`; nó không sử dụng biểu diễn `path` như matcher body. Khi dùng regex, hãy hiểu phạm vi so khớp và tránh mở quá rộng các header dùng để phân luồng truy cập.

### 11.3. Match query parameter

~~~yaml
request:
  method: GET
  urlPath: /api/inventory/SKU-123
  queryParameters:
    locale: vi
    includeWarehouses: "true"
  matchers:
    queryParameters:
      - key: locale
        type: matching
        value: 'vi|en'
      - key: includeWarehouses
        type: equal_to
        value: "true"
~~~

Đối với **query parameters**, các giá trị `type` có dạng riêng như `equal_to`, `containing`, `matching`, `not_matching`, `absent`. **Không** dùng `by_regex` của matcher body để mô tả query parameter.

| Vị trí | Cú pháp mẫu |
|---|---|
| Body JSON | `- path: $.sku` và `type: by_regex` |
| Header | `- key: Accept` và `regex: application/json.*` |
| Query parameter | `- key: locale`, `type: matching`, `value: 'vi|en'` |
| URL | `matchers.url.regex: '/api/...' ` |

Đây là các nhánh **khác nhau** của schema YAML. Không thể chuyển nguyên một matcher body sang headers/query chỉ bằng cách đổi tên trường.

## 12. Matcher response headers

Phía response cũng có thể chứa matcher header để producer test xác nhận định dạng một header thay đổi:

~~~yaml
response:
  status: 201
  headers:
    Content-Type: application/json
    X-Request-Id: req-1001
  body:
    status: CREATED
  matchers:
    headers:
      - key: Content-Type
        regex: 'application/json.*'
      - key: X-Request-Id
        regex: 'req-[0-9]+'
~~~

Các matcher này áp dụng cho **header của response**, khác với `request.matchers.headers` kiểm tra header consumer gửi. Nếu header là bắt buộc, contract nên thể hiện điều đó rõ ràng; nếu client không sử dụng một header, không cần bắt toàn bộ header phụ do framework tự tạo.

Một số matcher header hỗ trợ `command` cho logic kiểm thử tùy chỉnh. Chỉ sử dụng khi nhóm có test base cung cấp hàm xử lý tương ứng và có lý do kỹ thuật rõ ràng.

## 13. JSONPath: chỉ đúng trường cần kiểm chứng

JSONPath là cách chỉ vị trí trong một payload JSON:

~~~json
{
  "sku": "SKU-123",
  "available": true,
  "warehouses": [
    {"code": "HCM-01", "quantity": 7},
    {"code": "HN-02", "quantity": 5}
  ],
  "metadata": {
    "source.system": "warehouse-core"
  }
}
~~~

Ví dụ những JSONPath liên quan:

| JSONPath | Ý nghĩa |
|---|---|
| `$.sku` | Trường `sku` ở cấp gốc |
| `$.available` | Trường boolean `available` |
| `$.warehouses[0].code` | Mã kho của phần tử đầu tiên |
| `$.warehouses[1].quantity` | Số lượng ở phần tử thứ hai |
| `$['metadata']['source.system']` | Trường có dấu chấm nằm trong **tên key** |

Với key có dấu chấm, dấu cách hoặc ký tự đặc biệt, nên dùng ký pháp ngoặc vuông và dấu nháy bên trong JSONPath, đồng thời đặt **toàn bộ path** trong dấu nháy YAML phù hợp:

~~~yaml
response:
  body:
    metadata:
      source.system: warehouse-core
  matchers:
    body:
      - path: "$['metadata']['source.system']"
        type: by_equality
~~~

Đừng giả định `$.metadata.source.system` trỏ đến cùng key: cú pháp dấu chấm thường biểu thị **nhiều cấp đối tượng**, trong khi `source.system` ở đây là **một tên key**.

Nếu dùng index cụ thể như `[0]`, matcher có thể phụ thuộc thứ tự mảng. Khi thứ tự không phải cam kết API, hãy thiết kế matcher và test consumer để tránh khóa cứng thứ tự không cần thiết.

## 14. Kiểm tra kiểu và số phần tử mảng

Các trường số, boolean hoặc mảng có thể thay đổi giá trị giữa các lần chạy. `by_type` giúp producer test xác minh kiểu của giá trị so với mẫu trong `body`:

~~~yaml
response:
  status: 200
  body:
    sku: SKU-123
    available: true
    quantity: 12
    warehouses:
      - code: HCM-01
      - code: HN-02
  matchers:
    body:
      - path: $.available
        type: by_type
      - path: $.quantity
        type: by_type
      - path: $.warehouses
        type: by_type
        minOccurrence: 1
        maxOccurrence: 5
~~~

Ý định là xác nhận `available` vẫn là boolean, `quantity` vẫn là số và danh sách kho nằm trong phạm vi được chấp nhận. Tuy nhiên, kiểm tra kích thước mảng phụ thuộc **phiên bản, cấu hình và khả năng hỗ trợ của verifier**. Trong tài liệu SCC, cơ chế assert JSON array size từng được ghi là thử nghiệm và có tùy chọn bật riêng. Vì vậy, sau khi dùng `minOccurrence` hoặc `maxOccurrence`, cần quan sát **generated test thực tế** để bảo đảm có assertion về kích thước, thay vì kết luận từ YAML.

Nếu consumer cần `quantity >= 0` hoặc tổng số lượng các kho bằng `quantity`, matcher `by_type` chưa kiểm tra những quan hệ đó. Bạn cần bổ sung test nghiệp vụ hay kiểm tra tùy biến thích hợp.

## 15. Dùng by_command khi quy tắc vượt khả năng matcher sẵn có

Một số ràng buộc cần logic bổ sung, chẳng hạn mã trả về phải tồn tại trong một danh mục, hoặc hai trường phải nhất quán với nhau. Phía **response** của YAML contract hỗ trợ matcher `by_command` để generated test gọi hàm kiểm chứng được cung cấp trong test base.

~~~yaml
response:
  status: 200
  body:
    quantity: 12
  matchers:
    body:
      - path: $.quantity
        type: by_command
        value: 'assertNonNegative($it)'
~~~

Ví dụ Java về ý tưởng hàm kiểm chứng:

~~~java
// Hàm phải được SCC generated test có thể gọi theo cấu hình test base.
public void assertNonNegative(Number value) {
    org.assertj.core.api.Assertions
            .assertThat(value.doubleValue())
            .isGreaterThanOrEqualTo(0);
}
~~~

`$it` là vị trí mà SCC truyền giá trị đã lấy qua JSONPath vào hàm. Cần bảo đảm hàm được generated test gọi được (ví dụ tồn tại ở lớp test base, kiểu tham số tương thích), rồi kiểm tra source test đã sinh để xác nhận. Đây là **matcher ở phía kiểm thử producer**, không phải một đoạn code được thực thi trong consumer từ stub.

Không dùng `by_command` cho những điều kiện có thể diễn đạt đơn giản bằng `by_equality`, `by_regex` hoặc `by_type`: logic tùy biến làm contract khó đọc và phụ thuộc test infrastructure hơn.

## 16. Một contract hoàn chỉnh có request và response matcher

Sau khi hiểu từng thành phần, ta kết hợp chúng thành một tình huống thực tế: **consumer yêu cầu tạo phiếu giữ hàng**, producer trả mã mới và số lượng đã được chấp nhận.

Tệp `src/test/resources/contracts/reservation/create-reservation.yml`:

~~~yaml
description: Checkout tạo phiếu giữ hàng hợp lệ
name: create_reservation

request:
  method: POST
  url: /api/reservations
  headers:
    Content-Type: application/json
    X-Channel: checkout
  body:
    clientRequestId: REQ-1001
    sku: SKU-123
    quantity: 2
  matchers:
    headers:
      - key: Content-Type
        regex: 'application/json.*'
    body:
      - path: $.clientRequestId
        type: by_regex
        value: '^REQ-[0-9]{4}$'
      - path: $.sku
        type: by_regex
        value: '^SKU-[A-Z0-9-]+$'
      - path: $.quantity
        type: by_regex
        value: '^[1-9][0-9]*$'
        regexType: as_integer

response:
  status: 201
  headers:
    Content-Type: application/json
    X-Request-Id: req-1001
  body:
    reservationId: RSV-1001
    status: CREATED
    acceptedQuantity: 2
    expiresAt: "2026-11-24T11:30:00"
  matchers:
    headers:
      - key: X-Request-Id
        regex: 'req-[0-9]+'
    body:
      - path: $.reservationId
        type: by_regex
        value: '^RSV-[0-9]+$'
      - path: $.status
        type: by_equality
      - path: $.acceptedQuantity
        type: by_type
      - path: $.expiresAt
        type: by_timestamp
~~~

### Bằng chứng mong đợi khi chạy

**Generated producer test** gửi request với dữ liệu phù hợp, rồi xác minh producer trả `201`, trạng thái `CREATED` và các trường/header đáp ứng matcher. Nếu `reservationId` thực tế là `RSV-2002`, regex vẫn có thể cho test đạt. Nếu producer trả `status: REJECTED`, matcher `by_equality` phải phát hiện sai lệch.

**Stub phía consumer** dùng các điều kiện request để quyết định có trả phản hồi mẫu hay không. Nếu client gửi `sku` không hợp lệ hoặc header cần thiết không khớp, stub có thể không match và consumer test sẽ thất bại hoặc nhận response không mong đợi.

**Cần lưu ý:** `acceptedQuantity` trong response mới chỉ được kiểm tra kiểu. Contract chưa nói `acceptedQuantity` phải đúng bằng `quantity` trong request; muốn cam kết điều đó thì phải mô tả/thử thêm quan hệ tương ứng.

## 17. Tách body lớn sang file mà vẫn dùng matcher

Khi body dài, YAML DSL hỗ trợ tham chiếu fixture:

~~~yaml
response:
  status: 200
  headers:
    Content-Type: application/json
  bodyFromFile: payloads/stock-available.json
  matchers:
    body:
      - path: $.quantity
        type: by_type
~~~

Tệp `payloads/stock-available.json` chứa body JSON thực tế và phải được đặt tại vị trí được cơ chế resolve tài nguyên của SCC tìm thấy. Matcher vẫn được viết **trong contract YAML** và JSONPath phải trỏ đến trường tồn tại trong fixture.

Với dữ liệu byte, một số phiên bản DSL hỗ trợ `bodyFromFileAsBytes`. Chỉ chọn cách này cho payload nhị phân khi phiên bản/plugin và pipeline thật sự xử lý đúng byte.

Không coi file fixture là nội dung phụ có thể thay đổi tùy tiện: đổi field, kiểu dữ liệu hoặc cấu trúc trong fixture sẽ thay đổi generated test và stub, có thể trở thành **breaking change** với consumer.

## 18. Phân biệt YAML DSL với Groovy DSL

Groovy và YAML đều diễn tả contract, nhưng cú pháp matcher khác nhau.

**Groovy DSL:**

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method POST()
        url '/api/reservations'
        body(sku: 'SKU-123')
        bodyMatchers {
            jsonPath('$.sku', byRegex('^SKU-[A-Z0-9-]+$'))
        }
    }
    response {
        status CREATED()
        body(reservationId: 'RSV-1001')
        bodyMatchers {
            jsonPath('$.reservationId', byRegex('^RSV-[0-9]+$'))
        }
    }
}
~~~

**YAML DSL tương đương về ý tưởng:**

~~~yaml
request:
  method: POST
  url: /api/reservations
  body:
    sku: SKU-123
  matchers:
    body:
      - path: $.sku
        type: by_regex
        value: '^SKU-[A-Z0-9-]+$'
response:
  status: 201
  body:
    reservationId: RSV-1001
  matchers:
    body:
      - path: $.reservationId
        type: by_regex
        value: '^RSV-[0-9]+$'
~~~

Chú ý:

- Groovy dùng `bodyMatchers { jsonPath(..., byRegex(...)) }`.
- YAML dùng `matchers: body: - path: ...; type: by_regex`.
- Groovy có thể biểu diễn giá trị động bằng các biểu thức `consumer(...)`/`producer(...)`; YAML tập trung vào **body mẫu và phần matchers riêng**.
- Khi chuyển DSL, phải kiểm tra lại generated tests/stubs để xác nhận không đổi nghĩa. Không thể thay tên extension rồi giữ nguyên cú pháp.

Ngoài Groovy và YAML, SCC còn có Java/Kotlin DSL. Những lựa chọn này phù hợp với sở thích và hạ tầng build của dự án, nhưng việc đổi DSL không làm mất yêu cầu kiểm chứng cả producer và consumer.

## 19. Những lỗi YAML và matcher thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Contract không parse được | Sai thụt lề, dùng tab hoặc dấu `:` không đúng | Dùng spaces, kiểm tra cấu trúc bằng YAML parser và chạy SCC generation |
| Test trả `status` lạ hoặc body sai kiểu | YAML tự suy kiểu `true`, số, chuỗi hoặc null | Chủ động quote giá trị cần là chuỗi, giữ boolean/số đúng kiểu |
| Matcher không có tác dụng | Đặt `matchers` sai cấp hoặc JSONPath không tồn tại | Đặt matcher trong đúng `request`/`response`, trỏ đến trường mẫu có thật |
| Stub nhận request không hợp lệ | Matcher ở request quá rộng hoặc thiếu header/query cần thiết | Bổ sung điều kiện thực sự thuộc API contract, kiểm thử trường hợp sai |
| Producer test đỏ với ID thay đổi | Dùng equality cho trường sinh động | Dùng `by_regex`/`by_type` theo ràng buộc thực tế |
| Producer test xanh dù dữ liệu nghiệp vụ sai | Dùng `by_type` thay cho ràng buộc giá trị/quan hệ cần thiết | Thêm equality, regex chặt hơn hoặc assertion nghiệp vụ |
| Regex hoạt động khác mong đợi | YAML escape hoặc regex không anchor | Quote regex bằng nháy đơn, thêm `^`/`$` khi cần, thử dữ liệu biên |
| JSONPath truy vấn sai key | Key có dấu chấm hoặc sai cấp cấu trúc | Dùng ký pháp ngoặc `$['key.with.dot']` phù hợp |
| Matcher mảng không kiểm tra được số lượng | Giới hạn/tùy chọn kích thước mảng của verifier | Đọc generated test và cấu hình hỗ trợ `minOccurrence`/`maxOccurrence` |
| `by_command` gây lỗi biên dịch test | Thiếu hàm trong test base hoặc kiểu tham số không phù hợp | Cung cấp hàm đúng chữ ký, kiểm tra generated source |
| Consumer test xanh khi producer thay API | Consumer vẫn chạy stub phiên bản trước | Ghim stub artifact của commit ứng viên, xác minh version trong log |
| Contract YAML hợp lệ nhưng không sinh test | Plugin sai cấu hình/không tìm thấy contract | Kiểm tra contracts directory, plugin version, build lifecycle/task |

Sai lầm phổ biến nhất là đánh đồng **YAML parse hợp lệ** với **contract chính xác**. YAML parser chỉ kiểm tra định dạng tài liệu; SCC mới hiểu `matchers` và sinh test; producer/consumer tests mới kiểm tra tính đúng đắn của giao tiếp.

## 20. Kiểm tra contract từ máy phát triển đến CI

### 20.1. Kiểm tra tối thiểu trong producer

Với một dự án Maven đã cấu hình Spring Cloud Contract Maven plugin và test base:

~~~bash
# Tạo generated tests, chạy test và kiểm tra vòng đời build.
./mvnw clean verify
~~~

Với Gradle đã cấu hình Contract plugin:

~~~bash
# Chạy các task test cần thiết, kiểm tra generated tests có được thực thi.
./gradlew clean test
~~~

Tên task, nơi sinh test và cách đóng gói stub có thể khác nhau theo phiên bản plugin; hãy xem log thực tế thay vì giả định tất cả cấu hình đều dùng một đường dẫn. Trên Windows dùng wrapper `mvnw.cmd` hoặc `gradlew.bat`.

Khi đọc kết quả, cần xác nhận:

1. YAML contract được tìm thấy trong thư mục cấu hình.
2. Request mẫu từ contract được generated test gửi tới code producer thật.
3. Assertions dựa trên `response.matchers` thực sự được sinh và chạy.
4. Response stub được tạo từ đúng contract và dữ liệu mẫu.
5. Không có matcher nào bị bỏ qua vì sai cú pháp hoặc thiếu hỗ trợ.

### 20.2. Kiểm tra phía consumer

Consumer dùng **Stub Runner** để tải và chạy stub của producer. Bài test nên sử dụng **HTTP client thật** của consumer, gửi request khớp `request.matchers` rồi assert phản hồi được xử lý đúng, ví dụ mã phiếu trả về được đọc thành công.

Test cần trỏ vào stub artifact ứng viên với group, artifact, version và classifier rõ ràng. Nếu API đổi `reservationId` thành `id`, producer test có thể xanh sau khi contract được sửa; **consumer test với stub mới** phải phát hiện client cũ không đọc được field như mong đợi.

### 20.3. Cổng kiểm tra CI

~~~mermaid
flowchart LR
    A["Thay đổi YAML contract hoặc code"] --> B["Validate và generate producer tests"]
    B --> C{"Producer tests đạt?"}
    C -- "Không" --> X["Chặn PR/release"]
    C -- "Có" --> D["Đóng gói stub ứng viên"]
    D --> E["Consumer tests dùng Stub Runner"]
    E --> F{"Consumer tests đạt?"}
    F -- "Không" --> X
    F -- "Có" --> G["Tiếp tục các kiểm tra trước release"]
~~~

Một pipeline đáng tin cậy cần ghi lại commit, phiên bản Spring Cloud Contract, các generated tests đã chạy, tọa độ stub và kết quả consumer. Không nên kết luận tương thích chỉ từ producer build xanh hoặc consumer test đang sử dụng stub cũ.

## 21. Bài thực hành theo ba vòng

**Bối cảnh:** Inventory Service là producer; Checkout Service là consumer. Checkout cần gọi API tồn kho và tạo phiếu giữ hàng bằng JSON.

### Vòng A — Viết contract cơ bản

1. Tạo một contract YAML cho `GET /api/inventory/SKU-123`.
2. Khai báo `request.method`, `request.url`, header `Accept`; trong `response`, khai báo `status: 200`, `Content-Type`, `sku`, `available` và `quantity`.
3. Sinh generated producer test và xác nhận test gọi được endpoint.
4. Xem stub mapping hoặc stub artifact để hiểu mẫu response mà consumer sẽ thấy.

**Điểm cần trình bày:** field nào là chuỗi, boolean, số; vì sao không dùng `response.matchers` cho tất cả trường nếu không cần dữ liệu động.

### Vòng B — Thêm matcher hợp lý

1. Viết contract `POST /api/reservations` với `clientRequestId`, `sku`, `quantity`.
2. Dùng `request.matchers.body` để chấp nhận mã request theo regex và số lượng hợp lệ.
3. Dùng `response.matchers.body` để xác nhận `reservationId` hợp định dạng, `status` bằng `CREATED` và `acceptedQuantity` có kiểu số.
4. Thử producer trả `reservationId: "INVALID"`: generated test phải phát hiện lỗi.
5. Thử consumer gửi sai `sku`: stub không nên match tình huống thành công.

**Điểm cần trình bày:** tại sao matcher request và response tác động vào **hai bước kiểm chứng khác nhau**.

### Vòng C — Kiểm tra thay đổi không tương thích

1. Đổi producer và contract để response chỉ trả `id` thay cho `reservationId`.
2. Quan sát producer tests có thể xanh khi khớp contract mới.
3. Tạo **stub ứng viên mới** và chạy consumer test của Checkout cũ.
4. Ghi lại lỗi khi client còn đọc `reservationId`.
5. Đề xuất cách nâng cấp an toàn: giữ đồng thời field cũ và field mới trong giai đoạn chuyển đổi, rồi mới loại bỏ field cũ.

**Bằng chứng nộp bài:** tệp YAML, generated test, log kết quả producer, stub version ứng viên, kết quả consumer test và giải thích điều kiện matcher nào đã được kiểm tra.

## 22. Checklist trước khi merge contract YAML

- [ ] `request` chứa đúng method, URL/path, query, header và body mà consumer gửi.
- [ ] `response` nêu rõ status, header, body và ngữ nghĩa producer phải bảo đảm.
- [ ] Các field YAML có kiểu đúng, chuỗi dễ bị suy kiểu đã được quote.
- [ ] `matchers` nằm **đúng phía** và đúng cấp của cấu trúc YAML.
- [ ] Từng `path` JSONPath trỏ đến một phần tử tồn tại trong body mẫu.
- [ ] Regex chỉ cho phép định dạng thật sự mong muốn; `regexType` phù hợp khi cần.
- [ ] Những giá trị cần cố định vẫn dùng equality, không bị nới lỏng thành by_type.
- [ ] Những giá trị động không bị khóa cứng một mẫu không cần thiết.
- [ ] Matcher request có đủ điều kiện để Stub Runner không nhận nhầm request khác.
- [ ] Generated producer tests thật sự sinh, chạy và assert matcher như mong đợi.
- [ ] Stub ứng viên được tạo từ đúng commit/contract và consumer dùng đúng version.
- [ ] Các thay đổi field, status, header có nguy cơ breaking đã được consumer kiểm chứng.

## 23. Câu hỏi tự kiểm tra

**1. Tại sao `matchers` không đặt chung ở cấp root của YAML?**

Vì matcher có hai mục đích phụ thuộc phía giao tiếp. `request.matchers` mô tả điều kiện request stub cần nhận; `response.matchers` mô tả cách xác minh response của producer. Đặt đúng vị trí giúp SCC sinh stub và generated test đúng ý nghĩa.

**2. Khác biệt giữa `by_equality` và `by_type` là gì?**

`by_equality` yêu cầu giá trị bằng mẫu; `by_type` cho phép giá trị thay đổi nhưng phải phù hợp kiểu mẫu. Nếu nghiệp vụ cần đúng `status: CREATED`, chỉ kiểm tra kiểu string là không đủ.

**3. Tại sao `by_regex` cho `quantity` có thể cần `regexType`?**

Vì `quantity` là số JSON; regex mặc định có thể được diễn giải theo kiểu chuỗi. `regexType: as_integer` giúp SCC hiểu giá trị cần so khớp dưới dạng số nguyên trong trường hợp được hỗ trợ.

**4. Tại sao cần quote regex bằng nháy đơn trong YAML?**

Vì các ký tự regex như dấu gạch chéo ngược dễ bị parser xử lý khác khi đặt trong chuỗi nháy kép. Dùng nháy đơn thường giữ regex dễ đọc và giảm lỗi escape, nhưng vẫn cần kiểm thử biểu thức với dữ liệu thực tế.

**5. Producer test xanh có chứng minh consumer cũ tương thích không?**

Không. Nếu producer và contract cùng đổi theo phiên bản mới, generated test vẫn có thể đạt trong khi consumer cũ không giải mã được response. Phải chạy consumer test với **stub ứng viên** để nhận biết thay đổi breaking.

## 24. Tài liệu tham khảo

- [Spring Cloud Contract – Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): các biến thể DSL và cấu trúc YAML contract.
- [Spring Cloud Contract – Dynamic properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): semantics matcher, `type`, `predefined`, `regexType` và khác biệt giữa request/response.
- [Spring Cloud Contract – YML Schema](https://docs.spring.io/spring-cloud-contract/reference/yml-schema.html): các field và kiểu matcher được hỗ trợ trong YAML.

**Lưu ý phiên bản:** Các ví dụ được xây dựng dựa trên cú pháp YAML DSL trong tài liệu Spring Cloud Contract hiện hành. Tên trường, lựa chọn matcher và tính năng nâng cao có thể khác theo phiên bản mà dự án đã chốt; luôn đối chiếu tài liệu cùng phiên bản plugin và xác nhận qua generated test/stub thực tế.

---

**Điểm cần nhớ:** YAML contract tách rõ **`request`** (điều kiện consumer gửi) và **`response`** (cam kết producer trả). Matcher trong request giúp stub nhận đúng dữ liệu; matcher trong response giúp generated producer test kiểm tra đúng ràng buộc. Sử dụng matcher vừa đủ chặt, JSONPath đúng trường và stub ứng viên đúng phiên bản để phát hiện thay đổi API không tương thích trước khi phát hành.
