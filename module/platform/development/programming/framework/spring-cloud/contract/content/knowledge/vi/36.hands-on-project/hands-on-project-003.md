# Viết hợp đồng JSON có trường động và matcher

Một API tạo đơn hàng thường nhận dữ liệu thay đổi theo từng request như customer ID, client request ID và số lượng sản phẩm; đồng thời trả về các giá trị do producer sinh ra như order ID và thời điểm tạo. Nếu hợp đồng khóa cứng mọi giá trị vào một JSON mẫu, stub chỉ phù hợp với đúng một request. Nếu matcher quá rộng, test lại có thể chấp nhận payload sai kiểu hoặc thiếu trường.

**Spring Cloud Contract** cho phép mô tả cả **giá trị mẫu** và **quy tắc khớp** cho từng phía giao tiếp. Với Groovy DSL, bạn có thể khai báo giá trị riêng cho consumer và producer ngay trong body bằng `$()` hoặc `value(...)`, hoặc tách quy tắc ra `bodyMatchers`. Với YAML DSL, khai báo dữ liệu mẫu trong body và quy tắc trong phần `matchers`. Từ cùng một hợp đồng, Contract Verifier sinh producer tests và plugin tạo stubs để consumer dùng qua Stub Runner.

Bài này thuộc chương **Thực hành tổng hợp**, trong lộ trình **SPRING_CLOUD_CONTRACT**: học kiểm thử hợp đồng giữa producer và consumer bằng Groovy/YAML DSL, sinh test phía cung cấp, phát hành stub, dùng Stub Runner và tích hợp CI để phát hiện thay đổi API không tương thích. Chủ đề trực tiếp là **Viết hợp đồng JSON có trường động và matcher**.

Sau bài thực hành, bạn sẽ phân biệt giá trị consumer/producer, viết JSON có UUID, mã đơn, timestamp và correlation ID động, dùng regex/type/date/array matchers, viết ý tưởng tương đương bằng Groovy và YAML, đọc generated test/stub mapping, và kết nối producer verification với consumer Stub Runner tests.

## 1. Bối cảnh: Checkout tạo đơn hàng

**Order Service** cung cấp API tạo đơn. **Checkout Service** gửi:

```http
POST /api/orders
Content-Type: application/json
Accept: application/json

{
  "customerId": "CUS-000042",
  "clientRequestId": "A1B2C3D4E5F60708",
  "items": [
    {
      "sku": "SKU-42",
      "quantity": 2,
      "unitPrice": 62500
    }
  ]
}
```

Order Service xác thực dữ liệu, sinh mã đơn, ghi thời gian và trả:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/orders/ORD-100042

{
  "orderId": "ORD-100042",
  "clientRequestId": "A1B2C3D4E5F60708",
  "status": "CREATED",
  "createdAt": "2026-11-24T09:00:00Z",
  "totalAmount": 125000,
  "items": [
    {
      "sku": "SKU-42",
      "quantity": 2,
      "unitPrice": 62500
    }
  ]
}
```

| Trường | Nguồn | Điều cần kiểm tra |
|---|---|---|
| customerId | Checkout gửi | Mã khách hàng đúng format |
| clientRequestId | Checkout tạo | ID đúng format và được echo đúng |
| items | Checkout gửi | Mảng, SKU, quantity, unitPrice đúng kiểu |
| orderId | Order Service sinh | Tiền tố ORD và độ dài |
| createdAt | Order Service sinh | Timestamp ISO-8601 |
| status | Nghiệp vụ producer | Giá trị CREATED |
| totalAmount | Order Service tính | Kiểu number và giá trị nghiệp vụ |
| Location | Order Service trả | Resource path của đơn mới |

Contract cần cho phép consumer gửi nhiều ID hợp lệ, trong khi generated producer test vẫn có một request cụ thể, tái lập được.

## 2. Hiểu hai phía consumer và producer

Spring Cloud Contract tạo hai đầu ra từ contract:

- **Consumer side:** stub mà consumer gọi. Stub cần request matcher đủ linh hoạt và response mẫu có thể dự đoán.
- **Producer side:** generated test gọi implementation producer thật. Test cần request cụ thể và kiểm tra response thực bằng matcher.

| Phần hợp đồng | consumer(...) | producer(...) |
|---|---|---|
| Request body/header/path | Giá trị hoặc matcher dùng khi stub nhận request | Giá trị cụ thể generated test gửi tới producer |
| Response body/header | Giá trị cụ thể stub trả về cho consumer | Giá trị hoặc matcher để generated test kiểm tra response thật |

### 2.1. Request: consumer gửi biến thiên, producer test gửi mẫu cố định

```groovy
customerId: $(
    consumer(regex('CUS-[0-9]{6}')),
    producer('CUS-000042')
)
```

Kết quả:

- Stub chấp nhận các mã như CUS-000042 hoặc CUS-654321.
- Generated producer test gửi request cụ thể với CUS-000042.

Producer test không gửi regex như một chuỗi; regex là quy tắc để stub match request consumer.

### 2.2. Response: stub trả mẫu cố định, producer test kiểm tra giá trị động

```groovy
orderId: $(
    consumer('ORD-100042'),
    producer(regex('ORD-[0-9]{6}'))
)
```

Kết quả:

- Stub trả orderId cố định ORD-100042 để consumer test ổn định.
- Generated producer test chấp nhận response thật có orderId khớp ORD-[0-9]{6}.

Nhờ vậy producer được tự sinh ID mà test không phải ép UUID generator về một giá trị duy nhất.

### 2.3. Quy tắc ghi nhớ

- **Request:** consumer matcher, producer sample.
- **Response:** consumer sample, producer matcher.

Nếu đảo hai phía, bạn có thể tạo request test không thể gửi hoặc stub response không có giá trị cụ thể để trả. Luôn kiểm tra generated test và mapping sau khi viết dynamic contract.

## 3. Groovy DSL: contract tạo đơn với trường động

Tạo file:

```text
src/test/resources/contracts/checkout/create_order_201.groovy
```

Nội dung:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'checkout_create_order_201'
    description 'Checkout tạo đơn với request ID động và response ID do producer sinh'

    request {
        method POST()
        url '/api/orders'

        headers {
            contentType(applicationJson())
            accept(applicationJson())
        }

        body(
            customerId: $(
                consumer(regex('CUS-[0-9]{6}')),
                producer('CUS-000042')
            ),
            clientRequestId: $(
                consumer(regex('[A-F0-9]{16}')),
                producer('A1B2C3D4E5F60708')
            ),
            items: [
                [
                    sku: 'SKU-42',
                    quantity: 2,
                    unitPrice: 62500
                ]
            ]
        )

        bodyMatchers {
            jsonPath('$.items', byType {
                minOccurrence(1)
                maxOccurrence(5)
            })
        }
    }

    response {
        status CREATED()

        headers {
            contentType(applicationJson())
            header(
                'Location',
                $(
                    consumer('/api/orders/ORD-100042'),
                    producer(regex('/api/orders/ORD-[0-9]{6}'))
                )
            )
        }

        body(
            orderId: $(
                consumer('ORD-100042'),
                producer(regex('ORD-[0-9]{6}'))
            ),
            clientRequestId: fromRequest().body('$.clientRequestId'),
            status: 'CREATED',
            createdAt: $(
                consumer('2026-11-24T09:00:00Z'),
                producer(anyIso8601WithOffset())
            ),
            totalAmount: 125000,
            items: [
                [
                    sku: 'SKU-42',
                    quantity: 2,
                    unitPrice: 62500
                ]
            ]
        )

        bodyMatchers {
            jsonPath('$.totalAmount', byType())
            jsonPath('$.items', byType {
                minOccurrence(1)
                maxOccurrence(5)
            })
        }
    }
}
```

Đây là ví dụ Groovy DSL để học dynamic values và matchers. Các helper cần được xác nhận theo phiên bản Spring Cloud Contract đang dùng.

### 3.1. Phân tích request

customerId có hai giá trị:

- Consumer stub matcher chấp nhận CUS- cộng sáu chữ số.
- Generated producer test gửi CUS-000042.

clientRequestId cũng tương tự:

- Consumer có thể gửi ID hex 16 ký tự khác nhau.
- Producer test gửi A1B2C3D4E5F60708.
- Stub không bị khóa vào một correlation ID.

items có một phần tử mẫu. bodyMatchers đặt ràng buộc mảng từ 1 đến 5 phần tử. Mẫu body vẫn cần có field items; matcher không tự tạo field hoặc payload.

### 3.2. Phân tích response

orderId:

- Stub trả mã ORD-100042.
- Generated producer test kiểm tra response thật khớp ORD-[0-9]{6}.

createdAt:

- Stub trả timestamp cố định để consumer test tái lập được.
- Producer test chấp nhận timestamp ISO-8601 có offset.
- anyIso8601WithOffset() là predefined regex helper của Spring Cloud Contract.

totalAmount được kiểm tra kiểu bằng byType(). Mẫu body dùng số 125000, vì vậy response producer phải trả JSON number, không phải chuỗi "125000".

Location cũng dùng dynamic response: stub trả URL cụ thể, producer test kiểm tra URL thực theo pattern.

### 3.3. Echo giá trị từ request sang response

Dòng sau yêu cầu response chứa lại clientRequestId nhận trong request:

```groovy
clientRequestId: fromRequest().body('$.clientRequestId')
```

Groovy fromRequest() có thể tham chiếu URL, path, query, headers và body theo JSONPath. Với YAML, có thể dùng Handlebars helper như {{{ jsonpath this '$.clientRequestId' }}} trong response body. Response templating cần được hỗ trợ bởi WireMock version và transformer tương ứng.

## 4. YAML DSL: body mẫu và JSONPath matchers

YAML không dùng trực tiếp cú pháp Groovy $(). Với YAML, khai báo **giá trị mẫu trong body** rồi đặt quy tắc trong phần matchers.

Tạo file minh họa thay thế cho Groovy ở phần trước:

```text
src/test/resources/contracts/checkout/create_order_201.yml
```

```yaml
name: checkout_create_order_201_yaml
description: Checkout tạo đơn với JSON matcher

request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
    Accept: application/json
  body:
    customerId: CUS-000042
    clientRequestId: A1B2C3D4E5F60708
    items:
      - sku: SKU-42
        quantity: 2
        unitPrice: 62500
  matchers:
    body:
      - path: $.customerId
        type: by_regex
        value: 'CUS-[0-9]{6}'
        regexType: as_string
      - path: $.clientRequestId
        type: by_regex
        value: '[A-F0-9]{16}'
        regexType: as_string
      - path: $.items
        type: by_type
        minOccurrence: 1
        maxOccurrence: 5

response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    orderId: ORD-100042
    clientRequestId: A1B2C3D4E5F60708
    status: CREATED
    createdAt: '2026-11-24T09:00:00Z'
    totalAmount: 125000
    items:
      - sku: SKU-42
        quantity: 2
        unitPrice: 62500
  matchers:
    body:
      - path: $.orderId
        type: by_regex
        value: 'ORD-[0-9]{6}'
        regexType: as_string
      - path: $.createdAt
        type: by_timestamp
      - path: $.totalAmount
        type: by_type
      - path: $.items
        type: by_type
        minOccurrence: 1
        maxOccurrence: 5
```

Đây là **cách viết YAML thay thế** cho cùng ý tưởng, không nên đặt cả Groovy và YAML trên vào cùng source directory nếu chúng đại diện cùng một scenario. Làm vậy có thể tạo contract, generated test hoặc stub mapping trùng lặp.

### 4.1. request.matchers dùng cho stub request

Trong YAML trên:

- Body mẫu có customerId CUS-000042.
- Matcher $.customerId yêu cầu request consumer khớp CUS-[0-9]{6}.
- Body mẫu có clientRequestId cụ thể.
- Matcher cho phép consumer dùng ID hex 16 ký tự khác.
- items phải có số phần tử nằm trong giới hạn.

Generated producer test vẫn dùng body mẫu từ contract để gọi producer. request.matchers giúp stub nhận request khác nhau nhưng vẫn đúng định dạng.

### 4.2. response.matchers dùng cho producer verification

Response body trong YAML là giá trị mẫu để stub trả cho consumer. response.matchers mô tả cách generated producer test xác minh response thực:

- orderId phải đúng pattern.
- createdAt phải đúng dạng ISO timestamp.
- totalAmount phải giữ kiểu number.
- items phải là collection trong giới hạn đã định.

**Mọi JSONPath trong matchers phải tham chiếu tới phần tử đã tồn tại trong body.** Nếu viết matcher $.orderId nhưng body không có orderId, contract thiếu dữ liệu mẫu cần thiết.

### 4.3. YAML matchers không phải JSON Schema validator tổng quát

YAML matchers của Spring Cloud Contract dựa trên JSONPath và các loại matcher được hỗ trợ. Chúng không thay thế toàn bộ JSON Schema/OpenAPI validation hay business validation.

Nếu cần xác minh tổng tiền bằng tổng quantity nhân unitPrice, hoặc invariant phức tạp giữa nhiều field, hãy bổ sung producer integration/service tests. Contract nên bảo vệ những thuộc tính consumer thực sự phụ thuộc.

## 5. bodyMatchers và dynamic values khác nhau thế nào?

Groovy DSL hỗ trợ hai cách mô tả phần động:

1. Đặt trực tiếp giá trị hai phía trong body bằng value(...) hoặc $().
2. Khai báo body mẫu rồi đặt JSONPath matchers trong bodyMatchers.

| Cách viết | Phù hợp khi | Ví dụ |
|---|---|---|
| `$(consumer(...), producer(...))` | Hai phía cần giá trị khác nhau | Stub trả ID cố định, producer test chấp nhận regex |
| bodyMatchers | Muốn tách dữ liệu mẫu và quy tắc | Timestamp, type, array size |
| byType() | Kiểm tra kiểu JSON | String, number, boolean, collection |
| byRegex(...) | Kiểm tra pattern | UUID, mã đơn, email |
| byDate/byTimestamp/byTime | Kiểm tra định dạng thời gian | Date, ISO datetime, time |
| byEquality() | So sánh đúng giá trị mẫu | Status hoặc enum |
| byNull() | Kiểm tra field null | Field được phép null |

### 5.1. bodyMatchers trong request và response

| Vị trí | Mục đích | Phía sử dụng |
|---|---|---|
| request.bodyMatchers | Điều kiện stub chấp nhận request JSON | Consumer-side stub |
| response.bodyMatchers | Xác minh response thực của producer | Generated producer test |
| outputMessage.bodyMatchers | Xác minh body message producer phát | Generated producer messaging test |

Groovy ví dụ:

```groovy
bodyMatchers {
    jsonPath('$.orderId', byRegex('ORD-[0-9]{6}').asString())
    jsonPath('$.createdAt', byTimestamp())
    jsonPath('$.totalAmount', byType())
}
```

Đặt matcher đúng phần. Matcher trong request không tự động kiểm tra response.

## 6. Chọn matcher theo dữ liệu JSON

### 6.1. Regex cho chuỗi

```groovy
bodyMatchers {
    jsonPath('$.orderId', byRegex('ORD-[0-9]{6}').asString())
    jsonPath('$.customer.email', byRegex('[^@]+@[^@]+\\.[^@]+').asString())
}
```

YAML:

```yaml
matchers:
  body:
    - path: $.orderId
      type: by_regex
      value: 'ORD-[0-9]{6}'
      regexType: as_string
```

Regex khớp **toàn bộ giá trị**, không chỉ tìm một đoạn con. Vì vậy ORD-[0-9]{6} khớp ORD-100042 nhưng không khớp prefix-ORD-100042-suffix. Spring Cloud Contract sử dụng semantics tương đương Pattern.matches().

Nếu regex được dùng để tự sinh giá trị đối ứng, cần chú ý giới hạn của thư viện tạo chuỗi từ regex; tránh dựa vào ^/$ trong trường hợp tự động sinh giá trị. Khi có thể, cung cấp một giá trị cụ thể cho phía cần sample.

### 6.2. Regex và kiểu JSON

YAML regexType hỗ trợ các kiểu như:

| regexType | Kiểu |
|---|---|
| as_string | String |
| as_integer | Integer |
| as_long | Long |
| as_double | Double |
| as_float | Float |
| as_short | Short |
| as_boolean | Boolean |

Groovy:

```groovy
bodyMatchers {
    jsonPath('$.quantity', byRegex('[1-9][0-9]*').asInteger())
    jsonPath('$.unitPrice', byRegex('[0-9]+').asInteger())
    jsonPath('$.active', byRegex('true|false').asBooleanType())
}
```

JSON number và JSON string là hai kiểu khác nhau:

```json
{"quantity": 2}
```

```json
{"quantity": "2"}
```

Nếu consumer deserialize thành integer, contract không nên coi hai payload này tương đương.

### 6.3. Matcher thời gian

Groovy:

```groovy
bodyMatchers {
    jsonPath('$.createdDate', byDate())
    jsonPath('$.createdAt', byTimestamp())
    jsonPath('$.deliveryTime', byTime())
}
```

YAML:

```yaml
matchers:
  body:
    - path: $.createdDate
      type: by_date
    - path: $.createdAt
      type: by_timestamp
    - path: $.deliveryTime
      type: by_time
```

- by_date: giá trị dạng ngày.
- by_timestamp: ngày và thời gian.
- by_time: giờ.

Matcher định dạng không tự kiểm tra timezone nghiệp vụ hoặc quan hệ thời gian giữa hai field. Nếu createdAt phải nhỏ hơn expiresAt, hãy thêm assertion nghiệp vụ riêng.

### 6.4. Matcher kiểu dữ liệu và kích thước mảng

Groovy:

```groovy
bodyMatchers {
    jsonPath('$.status', byType())
    jsonPath('$.totalAmount', byType())
    jsonPath('$.items', byType {
        minOccurrence(1)
        maxOccurrence(5)
    })
}
```

YAML:

```yaml
matchers:
  body:
    - path: $.status
      type: by_type
    - path: $.totalAmount
      type: by_type
    - path: $.items
      type: by_type
      minOccurrence: 1
      maxOccurrence: 5
```

byType() so sánh kiểu thực tế với kiểu trong body mẫu. Với collection, minOccurrence/maxOccurrence đặt giới hạn số phần tử theo semantics matcher. Nếu cần đúng hai phần tử, có thể đặt min/max cùng bằng 2 hoặc dùng equality khi mảng phải có nội dung cố định.

### 6.5. Equality và null

Groovy:

```groovy
bodyMatchers {
    jsonPath('$.status', byEquality())
    jsonPath('$.optionalNote', byNull())
}
```

YAML:

```yaml
matchers:
  body:
    - path: $.status
      type: by_equality
    - path: $.optionalNote
      type: by_null
      value: null
```

Field không xuất hiện và field có giá trị null là hai trạng thái khác nhau. Đừng coi chúng tương đương nếu consumer phân biệt.

## 7. Mảng và JSON lồng nhau

Ví dụ response:

```json
{
  "orderId": "ORD-100042",
  "customer": {
    "id": "CUS-000042",
    "tier": "GOLD"
  },
  "items": [
    {
      "sku": "SKU-42",
      "quantity": 2,
      "unitPrice": 62500
    },
    {
      "sku": "SKU-99",
      "quantity": 1,
      "unitPrice": 20000
    }
  ]
}
```

Một số JSONPath:

| JSONPath | Ý nghĩa |
|---|---|
| $.orderId | Mã đơn |
| $.customer.id | Mã khách hàng lồng nhau |
| $.customer.tier | Hạng khách hàng |
| $.items | Toàn bộ mảng |
| $.items[0].sku | SKU phần tử đầu |
| $.items[*].sku | SKU của các phần tử |
| $.items[*].quantity | Quantity của các phần tử |

Groovy matcher:

```groovy
bodyMatchers {
    jsonPath('$.customer.id', byRegex('CUS-[0-9]{6}').asString())
    jsonPath('$.customer.tier', byEquality())
    jsonPath('$.items', byType {
        minOccurrence(1)
        maxOccurrence(10)
    })
    jsonPath('$.items[0].quantity', byRegex('[1-9][0-9]*').asInteger())
}
```

Matcher $.items[0].quantity bảo vệ phần tử đầu tiên. Nếu muốn ràng buộc mọi phần tử, hãy xác minh JSONPath wildcard semantics và generated assertions với plugin version; không giả định matcher ở [0] áp dụng cho toàn mảng.

## 8. Predefined regex helpers

Spring Cloud Contract cung cấp helper để tránh tự viết mọi pattern:

| Helper | Ý nghĩa |
|---|---|
| anyUuid() | UUID |
| anyInteger() | Số nguyên |
| anyPositiveInt() | Số nguyên dương |
| anyNumber() | Giá trị số |
| anyDouble() | Số thực |
| anyBoolean()/aBoolean() | Boolean |
| anyEmail() | Email |
| anyUrl()/anyHttpsUrl() | URL |
| anyIpAddress() | Địa chỉ IP |
| anyHostname() | Hostname |
| anyDate() | Ngày |
| anyDateTime() | Ngày và giờ |
| anyTime() | Giờ |
| anyIso8601WithOffset() | ISO-8601 có offset |
| anyNonBlankString() | Chuỗi không blank |
| anyNonEmptyString() | Chuỗi không rỗng |
| anyOf('A', 'B') | Một trong các giá trị đã cho |

Ví dụ:

```groovy
body(
    id: $(anyUuid()),
    quantity: $(anyPositiveInt()),
    email: $(anyEmail()),
    active: $(anyBoolean()),
    createdAt: $(anyIso8601WithOffset())
)
```

Chọn helper phản ánh ngữ nghĩa API. Nếu quantity phải lớn hơn 0, anyInteger() quá rộng vì có thể bao gồm số âm hoặc 0; anyPositiveInt() phù hợp hơn.

## 9. Field tùy chọn và null

Groovy DSL hỗ trợ optional(...) ở những vị trí được framework quy định.

Ví dụ request có email tùy chọn:

```groovy
body(
    customerId: 'CUS-000042',
    email: $(
        consumer(optional(regex(email()))),
        producer('buyer@example.test')
    )
)
```

Stub phía consumer có thể chấp nhận request không gửi email hoặc gửi email hợp lệ; generated producer test dùng giá trị email cụ thể.

Không dùng optional() tùy tiện ở mọi vị trí. Tài liệu Spring Cloud Contract giới hạn optional parameters theo phía contract được hỗ trợ, chẳng hạn stub side của request và test side của response. Kiểm tra version trước khi mở rộng.

Ba payload sau khác nhau:

```json
{"email": "buyer@example.test"}
```

```json
{"email": null}
```

```json
{}
```

Chúng lần lượt là field có giá trị, field có giá trị null và field không xuất hiện. byNull() không đồng nghĩa với optional field.

## 10. Header và query parameter cũng có thể động

Groovy request header:

```groovy
headers {
    header(
        'X-Correlation-Id',
        $(
            consumer(regex('[A-F0-9]{16}')),
            producer('A1B2C3D4E5F60708')
        )
    )
    contentType(applicationJson())
}
```

YAML header matcher:

```yaml
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
    X-Correlation-Id: A1B2C3D4E5F60708
  matchers:
    headers:
      - key: X-Correlation-Id
        regex: '[A-F0-9]{16}'
```

Với response header Location, có thể dùng dynamic value ở Groovy như phần 3. Với YAML, dùng matcher header theo cấu trúc DSL hỗ trợ. Đừng đặt matcher body vào matchers.headers hoặc nhầm tên header với JSONPath.

## 11. Tham chiếu request trong response

Groovy DSL có fromRequest():

```groovy
response {
    status CREATED()
    headers {
        contentType(applicationJson())
    }
    body(
        orderId: 'ORD-100042',
        clientRequestId: fromRequest().body('$.clientRequestId'),
        customerId: fromRequest().body('$.customerId')
    )
}
```

YAML có thể dùng Handlebars helpers:

```yaml
response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    orderId: ORD-100042
    clientRequestId: "{{{ jsonpath this '$.clientRequestId' }}}"
    customerId: "{{{ jsonpath this '$.customerId' }}}"
```

Các template response dựa trên WireMock response transformer và Handlebars. Xác nhận WireMock version và transformer được bật theo Spring Cloud Contract release train. Nếu không cần response echo động, giá trị mẫu cố định sẽ đơn giản hơn.

## 12. Producer implementation và fixture

Controller minh họa:

```java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderApplicationService orderService;

    public OrderController(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<OrderResponse> create(
            @RequestBody CreateOrderRequest request) {
        OrderResponse response = orderService.create(request);

        return ResponseEntity
            .created(URI.create("/api/orders/" + response.orderId()))
            .body(response);
    }
}
```

Service thực hiện nghiệp vụ:

```java
@Service
public class OrderApplicationService {

    private final OrderRepository repository;
    private final Clock clock;
    private final OrderIdGenerator idGenerator;

    public OrderApplicationService(
            OrderRepository repository,
            Clock clock,
            OrderIdGenerator idGenerator) {
        this.repository = repository;
        this.clock = clock;
        this.idGenerator = idGenerator;
    }

    public OrderResponse create(CreateOrderRequest request) {
        validate(request);

        String orderId = idGenerator.nextOrderId();
        Instant createdAt = clock.instant();

        Order order = Order.create(
            orderId,
            request.customerId(),
            request.items(),
            createdAt
        );

        repository.save(order);

        return OrderResponse.from(order, request.clientRequestId());
    }
}
```

Các lớp CreateOrderRequest, OrderResponse, Order, OrderRepository, OrderIdGenerator và validate là phần minh họa cần project tự triển khai. Đây không phải ứng dụng hoàn chỉnh đã build.

### 12.1. Fixture producer ổn định

Generated producer test gửi request cụ thể từ producer(...). Base test có thể chuẩn bị database:

```java
@SpringBootTest
@AutoConfigureMockMvc
public abstract class OrderContractTestBase {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    OrderContractFixture fixture;

    @BeforeEach
    void prepare() {
        fixture.reset();
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
```

Với contract tạo đơn, fixture cần reset dữ liệu giữa các test, không dùng database production, seed customer CUS-000042 nếu endpoint yêu cầu, cấu hình Clock/ID generator phù hợp nếu test cần giá trị xác định, và không mock OrderApplicationService nếu mục tiêu là kiểm tra nghiệp vụ tạo đơn. Chỉ fake external boundaries nằm ngoài phạm vi contract.

### 12.2. Maven plugin tạo producer tests

POM fragment:

```xml
<properties>
    <spring-cloud-contract.version>CONTRACT_VERSION_PHU_HOP</spring-cloud-contract.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-contract-verifier</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
            <version>${spring-cloud-contract.version}</version>
            <extensions>true</extensions>
            <configuration>
                <baseClassForTests>
                    com.example.order.contract.OrderContractTestBase
                </baseClassForTests>
                <testMode>MOCKMVC</testMode>
                <testFramework>JUNIT5</testFramework>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Đây là fragment, cần parent/BOM và Spring Boot/Cloud/Contract versions tương thích. Generated test sources thường xuất hiện dưới target/generated-test-sources/contracts/ theo cấu hình Maven plugin. Test runner cần thực sự thực thi các classes đó.

Chạy:

```bash
./mvnw -B -ntp clean verify
```

generateTests chỉ sinh source; verify đi qua lifecycle để compile và chạy tests nếu plugin/test runner được cấu hình đúng. Generated files tồn tại không phải bằng chứng producer đã pass.

## 13. Đọc generated producer test và stub mapping

Sau khi build, generated test có ý nghĩa tương tự pseudocode:

```java
// Pseudocode minh họa, không phải generated source nguyên văn.
given()
    .contentType("application/json")
    .body("""
        {
          "customerId": "CUS-000042",
          "clientRequestId": "A1B2C3D4E5F60708",
          "items": [
            {"sku":"SKU-42","quantity":2,"unitPrice":62500}
          ]
        }
        """)
.when()
    .post("/api/orders")
.then()
    .statusCode(201)
    .body("orderId", matchesPattern("ORD-[0-9]{6}"))
    .body("status", equalTo("CREATED"))
    .body("totalAmount", instanceOf(Number.class));
```

Generated source thực tế do Contract Verifier quyết định theo DSL, test framework và version. Xác nhận request gửi producer sample, response matcher dùng regex/type, status và headers được assert, JSON fields consumer phụ thuộc được bảo vệ, generated test kế thừa đúng base class và runner thực thi class, không skip.

### 13.1. Stub response

Consumer-side stub cần trả JSON mẫu có thể dự đoán:

```json
{
  "orderId": "ORD-100042",
  "clientRequestId": "A1B2C3D4E5F60708",
  "status": "CREATED",
  "createdAt": "2026-11-24T09:00:00Z",
  "totalAmount": 125000
}
```

Request mapping cần chấp nhận dynamic customerId/clientRequestId theo matcher. Không tự sửa generated mappings trong target/; sửa contract DSL rồi generate lại.

### 13.2. Thử hai request với cùng một stub

Request A:

```json
{
  "customerId": "CUS-000042",
  "clientRequestId": "A1B2C3D4E5F60708",
  "items": [{"sku":"SKU-42","quantity":2,"unitPrice":62500}]
}
```

Request B:

```json
{
  "customerId": "CUS-654321",
  "clientRequestId": "ABCDEF0123456789",
  "items": [{"sku":"SKU-42","quantity":2,"unitPrice":62500}]
}
```

Cả hai phải khớp stub nếu đáp ứng request matcher. Stub trả response mẫu ổn định, giúp Checkout test logic sau khi tạo đơn mà không cần biết Order Service sinh ID/time thật nào.

## 14. Consumer test bằng Stub Runner

Consumer resolve stubs artifact đúng version. Ví dụ:

```java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:order-service:1.4.0:stubs:8085",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutOrderClientTest {
    // Inject OrderClient thật và kiểm tra request/response.
}
```

Đây là cấu hình minh họa; cần imports, Stub Runner test dependency, base URL và artifact đã được cài/publish. 8085 là cổng HTTP stub server trong notation ví dụ.

Consumer test nên kiểm tra client gửi POST /api/orders, Content-Type và Accept đúng, JSON request có ID đúng format, client xử lý 201 Created, đọc orderId/status/createdAt/totalAmount đúng kiểu, và xử lý Location nếu sử dụng.

Stub Runner không chạy Order Service implementation thật. Producer verification và consumer Stub Runner tests bổ sung cho nhau.

## 15. Contract lỗi để bảo vệ validation

Ví dụ YAML cho quantity không hợp lệ:

```yaml
name: checkout_create_order_invalid_quantity_400
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
  body:
    customerId: CUS-000042
    clientRequestId: A1B2C3D4E5F60708
    items:
      - sku: SKU-42
        quantity: 0
        unitPrice: 62500
response:
  status: 400
  headers:
    Content-Type: application/json
  body:
    code: INVALID_QUANTITY
  matchers:
    body:
      - path: $.code
        type: by_equality
```

Contract này cần file riêng và producer implementation phải trả đúng status/error body. Nếu API policy dùng 422, hãy dùng status đó thay vì ép mọi validation error thành 400.

Nếu Checkout phụ thuộc code, hãy assert field đó; chỉ kiểm tra status 400 có thể bỏ lọt error schema không tương thích.

## 16. Lỗi thường gặp khi viết dynamic JSON contracts

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Đảo consumer và producer | Request test/stub response dùng sai giá trị | Áp dụng ma trận ở phần 2 |
| Regex ở cả hai phía không cần thiết | Khó tái lập hoặc thiếu sample | Cung cấp giá trị cụ thể cho phía cần sample |
| JSON number viết thành string | Type matcher/deserializer sai | Giữ đúng JSON type |
| Matcher path không tồn tại | Contract thiếu phần tử được tham chiếu | Thêm body field hoặc sửa JSONPath |
| Regex quá rộng như .* | Chấp nhận payload sai | Giới hạn prefix, độ dài, character set |
| Regex quá hẹp | Request hợp lệ không khớp stub | Đối chiếu format API thực |
| Nhầm by_type với business validation | Chỉ kiểm tra kiểu | Thêm equality hoặc business tests |
| by_timestamp bị hiểu là timezone validation | Bỏ sót rule timezone | Thêm assertion nghiệp vụ |
| Array thiếu min/max | Không kiểm soát số phần tử | Đặt occurrence bounds |
| YAML dùng cú pháp $() | YAML không xử lý Groovy expression | Dùng matchers |
| Groovy/YAML trùng scenario | Generated tests/stubs trùng | Chọn một source cho mỗi scenario |
| Matcher request đặt trong response | Kiểm tra sai phía | Đặt đúng request/response |
| Dùng fromRequest() trong YAML | YAML không có Groovy method | Dùng Handlebars |
| Không inspect generated mapping | Stub match quá rộng hoặc sai body | Kiểm tra mapping thật |
| Chỉ chạy Stub Runner test | Không xác minh producer | Chạy Contract Verifier |
| Chỉ chạy producer test | Chưa biết consumer xử lý stub ra sao | Chạy Stub Runner test |

### 16.1. Regex khớp toàn bộ giá trị

Spring Cloud Contract dùng semantics Pattern.matches() cho regex matching. ORD-[0-9]{6} kiểm tra toàn bộ chuỗi; nó không tìm một đoạn con trong chuỗi lớn hơn.

- ORD-100042: khớp.
- prefix-ORD-100042: không khớp.
- ORD-100042-suffix: không khớp.

Regex kiểm tra format, không xác minh ID tồn tại hay caller có quyền truy cập.

## 17. Mutation test để biết matcher có tác dụng

Cố ý thay đổi implementation trong branch thử nghiệm:

| Mutation | Test phải phát hiện |
|---|---|
| orderId thành BAD-42 | Regex ORD-[0-9]{6} thất bại |
| createdAt thành yesterday | Timestamp matcher thất bại |
| totalAmount từ number thành string | Type matcher phát hiện |
| items thành mảng rỗng | minOccurrence: 1 thất bại |
| status thành PENDING | Equality matcher cho CREATED thất bại |
| Bỏ Location | Header assertion thất bại |

Quy trình:

1. Chạy baseline và xác nhận producer tests PASS.
2. Thay đổi một field trong implementation.
3. Chạy lại đúng generated test.
4. Kiểm tra failure xảy ra ở matcher mong đợi.
5. Khôi phục implementation.
6. Chạy lại và xác nhận PASS.

Nếu mutation không làm test fail, xem generated assertions, base class, test mode và runner report. Contract parse thành công chưa chứng minh matcher có hiệu lực.

## 18. Bài thực hành theo từng bước

### Giai đoạn A — tạo API và JSON mẫu

1. Tạo Order Service với POST /api/orders.
2. Tạo DTO request có customerId, clientRequestId và items.
3. Tạo DTO response có orderId, status, createdAt, totalAmount và items.
4. Xác định JSON type cho từng field.
5. Thống nhất format ID/timestamp với Checkout.

### Giai đoạn B — viết Groovy contract

1. Tạo create_order_201.groovy.
2. Dùng consumer(regex(...)) cho request fields biến thiên.
3. Dùng producer('...') để generated test gửi request cố định.
4. Dùng consumer('...') cho response mẫu của stub.
5. Dùng producer(regex(...)) cho ID do producer sinh.
6. Dùng fromRequest() để echo clientRequestId nếu API yêu cầu.
7. Dùng bodyMatchers cho array size và type.

### Giai đoạn C — viết YAML thay thế

1. Tạo bản YAML độc lập để học matchers.
2. Giữ body mẫu có đủ JSON fields.
3. Thêm request body matcher cho customerId/clientRequestId.
4. Thêm response matcher cho orderId/createdAt/totalAmount/items.
5. Chọn regexType đúng cho string/number/boolean.
6. Không đưa Groovy và YAML trùng scenario vào cùng bộ contracts khi build thật.

### Giai đoạn D — sinh và chạy producer tests

1. Cấu hình Spring Cloud Contract Maven/Gradle plugin đúng version.
2. Cấu hình base test class phù hợp MVC/WebFlux.
3. Seed dữ liệu test cần thiết.
4. Chạy generated producer tests.
5. Đọc generated source để xem request sample và assertions.
6. Đọc test reports để xác nhận đúng tests đã chạy, không skip.

### Giai đoạn E — kiểm tra stub

1. Package stubs artifact.
2. Kiểm tra request matcher có regex cho dynamic fields.
3. Kiểm tra response body có sample ổn định.
4. Kiểm tra content type và Location.
5. Thử hai request với customer ID/client request ID khác nhau.
6. Xác nhận chỉ request hợp lệ match.

### Giai đoạn F — consumer Stub Runner

1. Checkout dùng Stub Runner với đúng GAV/classifier/version.
2. Client gửi request có dynamic fields.
3. Xác nhận stub match request.
4. Consumer đọc response sample.
5. Kiểm tra mapping lỗi validation 400.
6. Không coi consumer test là bằng chứng producer implementation đã pass.

### Giai đoạn G — mutation và CI

1. Thay orderId sang sai format.
2. Xác nhận producer matcher fail.
3. Thay totalAmount từ number thành string.
4. Xác nhận type matcher fail.
5. Thay createdAt thành chuỗi không phải timestamp.
6. Xác nhận timestamp matcher fail.
7. Khôi phục implementation.
8. Đưa producer verification và report checks vào CI.
9. Chỉ publish stubs từ build đã vượt verification.

**Tiêu chí hoàn thành:** contract bảo vệ request và response dynamic; consumer có stub sample ổn định; producer generated tests chấp nhận dữ liệu động đúng format; mutation sai bị phát hiện ở đúng matcher.

## 19. CI: kiểm tra contract có thực sự bảo vệ field

Pipeline tối thiểu cần:

- Contract discovery và DSL parsing thành công.
- Generated producer tests được sinh.
- Generated tests compile và thực thi.
- JUnit/Surefire/Failsafe reports có đúng test cases.
- Không có generated tests quan trọng bị skip.
- Producer response thỏa dynamic matchers.
- Stubs JAR có mappings và response sample phù hợp.
- Artifact version/classifier gắn với cùng producer commit đã verify.
- Consumer Stub Runner test resolve đúng stubs version.

### 19.1. Checklist JSON matchers

- [ ] Mỗi dynamic request field có producer-side sample cụ thể.
- [ ] Consumer stub matcher nhận các giá trị hợp lệ khác nhau.
- [ ] Response stub dùng giá trị cụ thể có thể dự đoán.
- [ ] Generated producer test kiểm tra format ID/timestamp.
- [ ] Number, string và boolean giữ đúng JSON type.
- [ ] JSONPath trỏ tới field có trong body.
- [ ] Array có min/max occurrence khi API yêu cầu.
- [ ] Field null, absent và optional được phân biệt.
- [ ] Regex có giới hạn phù hợp, không dùng .* thay validation.
- [ ] Header/body matchers nằm đúng request/response.
- [ ] Groovy fromRequest() hoặc YAML Handlebars dùng đúng cú pháp.
- [ ] Generated source và stub mapping đã được inspect.
- [ ] Có mutation test cho ID, timestamp và JSON type.
- [ ] Consumer Stub Runner test dùng đúng artifact/version.
- [ ] Producer verification và consumer test có báo cáo độc lập.

## 20. Bảng chẩn đoán matcher

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Stub chỉ nhận CUS-000042 | Request matcher chưa generate hoặc đặt sai | Inspect mapping và request.matchers |
| Generated test gửi regex text | Regex đặt sai phía | Request producer side phải là sample |
| Stub response trả regex text | Response consumer side thiếu sample | Dùng consumer('...') |
| Producer test fail với ID ngẫu nhiên | Assertion đang equality | Kiểm tra response producer(regex(...)) |
| createdAt không match | Format/timezone khác pattern | Dùng byTimestamp hoặc regex phù hợp |
| totalAmount không match | Number bị serialize thành String | Kiểm tra DTO/Jackson và regexType |
| YAML matcher không hiệu lực | Path sai hoặc không tồn tại | Kiểm tra body và JSONPath |
| Array nhận số lượng sai | Thiếu min/max hoặc path sai | Inspect generated matcher |
| Response echo ID sai | Request reference template không xử lý | Kiểm tra fromRequest/Handlebars |
| Stub Runner trả 404 | Request không khớp mapping | Method/path/header/body matcher |
| Producer test không chạy | Plugin/test runner/lifecycle | Generated source và reports |
| Groovy regex parse lỗi | Quote/escape hoặc DSL version | Đọc stack trace, kiểm tra version |
| YAML parse được nhưng generation fail | Key/type không thuộc DSL | Đối chiếu YAML schema |
| Matcher quá rộng | Regex không ràng buộc format | Giới hạn prefix/length/type |
| Matcher bị lặp | Trùng dynamic body value và bodyMatcher | Chọn một cách rõ ràng cho field |

## 21. Tài liệu tham khảo và giới hạn phiên bản

Đối chiếu tài liệu chính thức của Spring Cloud Contract:

- [Dynamic properties — Spring Cloud Contract 4.2](https://docs.spring.io/spring-cloud-contract/reference/4.2/project-features-contract/dsl-dynamic-properties.html)
- [Dynamic properties — current reference](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html)
- [Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html)
- [YAML schema](https://docs.spring.io/spring-cloud-contract/reference/yml-schema.html)
- [Getting started: first application](https://docs.spring.io/spring-cloud-contract/reference/getting-started/first-application.html)
- [Maven project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html)
- [Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-core.html)

Các điểm cần nhớ:

- Cú pháp `$(consumer(...), producer(...))` thuộc Groovy/coded DSL; YAML dùng matchers.
- bodyMatchers dựa trên JSONPath, không phải JSON Schema engine tổng quát.
- Tên matcher YAML như by_regex, by_type, by_timestamp và regexType phải khớp schema version.
- Generated code, test framework, Maven/Gradle tasks và WireMock response templating có thể khác theo release train.
- Regex dùng để tự sinh giá trị đối ứng có giới hạn của regex-to-string generation.
- Code snippets là ví dụ thực hành, chưa phải một project đã build.

## 22. Câu hỏi tự kiểm tra

1. **Vì sao cần dynamic fields?** Để stub dùng lại được khi ID, timestamp hoặc request values thay đổi.
2. **consumer(...) đại diện phía nào?** Giá trị/behavior phía consumer stub.
3. **producer(...) đại diện phía nào?** Giá trị/behavior trong generated producer verification.
4. **Request dùng consumer(regex(...)) để làm gì?** Stub chấp nhận nhiều request hợp lệ.
5. **Request dùng producer('CUS-000042') để làm gì?** Generated producer test gửi request cụ thể.
6. **Response dùng consumer('ORD-100042') để làm gì?** Stub trả response sample cố định.
7. **Response dùng producer(regex(...)) để làm gì?** Producer test kiểm tra response thực theo pattern.
8. **Groovy DSL khai báo dynamic body bằng gì?** value(...) hoặc $().
9. **YAML DSL khai báo matcher ở đâu?** Phần matchers.
10. **by_regex làm gì?** Kiểm tra JSON value khớp regex.
11. **Vì sao cần regexType: as_integer?** Giữ semantics kiểu số nguyên thay vì chuỗi.
12. **by_type kiểm tra gì?** Kiểu dữ liệu thực tế so với body mẫu.
13. **minOccurrence/maxOccurrence dùng cho đâu?** Giới hạn số phần tử collection.
14. **by_timestamp dùng khi nào?** Field là timestamp.
15. **by_null khác optional thế nào?** Null là field có giá trị null; optional có thể cho phép field vắng mặt ở vị trí DSL hỗ trợ.
16. **Vì sao matcher path phải trỏ field có trong body?** Matcher không tự tạo payload element.
17. **fromRequest() dùng để làm gì?** Tham chiếu request fields trong response Groovy DSL.
18. **YAML tham chiếu request body bằng cách nào?** Handlebars helper như {{{ jsonpath this '$.field' }}}.
19. **Regex matcher có tìm chuỗi con không?** Không nên giả định; semantics là match toàn bộ giá trị.
20. **Vì sao không dùng .* cho mọi field?** Nó làm matcher quá rộng và bỏ lọt breaking changes.
21. **Producer test và Stub Runner test khác gì?** Một kiểm tra producer thật, một kiểm tra consumer với stubs.
22. **Stub có cần response sample cố định không?** Thông thường có để consumer test tái lập.
23. **Vì sao phải phân biệt JSON number và JSON string?** Đây là hai kiểu dữ liệu khác nhau.
24. **Mutation test chứng minh điều gì?** Matcher phát hiện một thay đổi sai cụ thể trong implementation.
25. **Khi nào dùng Groovy dynamic values và khi nào YAML matchers?** Groovy thuận tiện khi hai phía cần giá trị khác nhau trực tiếp trong body; YAML phù hợp khi tách body mẫu và JSONPath constraints.

## Kết luận

Một hợp đồng JSON tốt mô tả **mẫu dữ liệu consumer có thể dùng**, **request matcher đủ linh hoạt** và **producer assertions đủ chặt**. Groovy DSL cho phép đặt hai giá trị riêng biệt bằng `$(consumer(...), producer(...))`; YAML DSL đặt body mẫu cùng matchers dựa trên JSONPath. Chọn đúng phía cho từng giá trị giúp stub không bị khóa vào ID/timestamp của một request duy nhất mà producer vẫn được kiểm tra bằng generated tests.

Trong bài thực hành này, customerId và clientRequestId được match theo format; orderId và createdAt được producer sinh; totalAmount giữ kiểu number; items có giới hạn số phần tử; clientRequestId có thể được echo từ request. Kết hợp **Contract Verifier**, **Stub Runner**, generated test inspection, mutation checks và **CI gates**, nhóm có thể phát hiện sớm thay đổi JSON không tương thích mà vẫn giữ stub linh hoạt và dễ tái sử dụng.
