# Regex hoặc JSONPath đúng trong ý tưởng nhưng sai khi được sinh

Trong **Spring Cloud Contract**, ta có thể mô tả một hợp đồng HTTP rất hợp lý: mã đơn hàng bắt đầu bằng `ORD-`, trường `amountMinor` phải là số, email có định dạng hợp lệ, và một phần tử trong mảng `items` phải mang `sku` cụ thể. Thế nhưng sau khi plugin **sinh producer verification tests** hoặc **WireMock stub mappings**, kết quả có thể bất ngờ: test compile lỗi vì dấu gạch chéo ngược, generated assertion tìm không thấy JSONPath, matcher regex đang so chuỗi với số, hoặc Stub Runner trả 404 dù request mà consumer gửi trông có vẻ đúng.

Đây là lớp lỗi đặc biệt khó chẩn đoán vì một biểu thức có thể **đúng về ý tưởng** nhưng **sai ở một trong nhiều lớp diễn giải**. Groovy/YAML là nơi biểu thức được viết; Spring Cloud Contract phân tích DSL và sinh mã kiểm thử/mapping; Java hoặc Groovy compiler phân tích chuỗi; JSONPath đánh giá đường dẫn trên JSON; regex engine thực hiện so khớp; WireMock xử lý request của consumer. **Chỉ một bước escape hoặc ép kiểu không đúng** có thể khiến ý tưởng ban đầu bị biến dạng.

Bài thuộc chương **Chẩn đoán sự cố** của mô-đun **SPRING_CLOUD_CONTRACT**. Phạm vi mô-đun gồm hợp đồng HTTP/messaging với Groovy/YAML DSL, sinh tests phía producer, phát hành `stubs`, sử dụng Stub Runner và CI/CD để phát hiện thay đổi API không tương thích. Mục tiêu bài này là tìm **đúng lớp phát sinh lỗi**, đọc được đầu ra generated, tạo ví dụ tái hiện tối thiểu và sửa ở **contract nguồn** thay vì chỉnh tạm generated code.

Các ví dụ dưới đây chủ yếu sử dụng **Spring Cloud Contract 4.x với Groovy/YAML DSL, JUnit 5 và HTTP JSON**. Chữ ký DSL và cách generator, JSONPath, AssertJ/Hamcrest hoặc WireMock xử lý matcher có thể khác tùy phiên bản. Khi nêu generated code hay mapping, bài dùng **hình thái minh họa**, không khẳng định đó là Java/JSON chính xác được mọi phiên bản sinh ra.

## 1. Hiểu toàn bộ đường đi trước khi sửa regex

~~~mermaid
flowchart TD
    A["Groovy/YAML contract nguồn"] --> B["DSL parser và contract model"]
    B --> C["Sinh producer verification test"]
    B --> D["Chuyển thành WireMock stub mapping"]
    C --> E["Biên dịch test Java/Groovy"]
    E --> F["JSONPath + regex/assertion trên response producer thật"]
    D --> G["Stub Runner nạp mappings"]
    G --> H["WireMock match request từ consumer"]
    H --> I["Trả response mẫu cho client thật"]
    F --> J["Producer CI PASS/FAIL"]
    I --> K["Consumer CI PASS/FAIL"]
~~~

Một lỗi có thể xuất hiện tại:

| Tầng | Dấu hiệu điển hình | Cần xem |
| --- | --- | --- |
| **DSL parse** | Plugin báo không hiểu matcher, YAML không hợp lệ. | Groovy/YAML nguồn, cách quote, schema DSL của version đang dùng. |
| **Generation** | Generated test không có assertion mong đợi hoặc path bị biến đổi. | Source được sinh, mapping JSON được chuyển đổi. |
| **Compilation** | `illegal escape character`, string literal sai hoặc import không có. | Dòng Java/Groovy do plugin sinh, compiler/SDK versions. |
| **JSONPath evaluation** | Không tìm thấy key, trả list thay vì scalar, sai kiểu. | JSON response thực và chính JSONPath mà generated test sử dụng. |
| **Regex evaluation** | Pattern match sai hoặc không match dù dữ liệu có vẻ hợp lệ. | Pattern sau escape, kiểu giá trị, full-match/substring semantics. |
| **Stub request matching** | WireMock không khớp request, trả 404 no-match. | Stub mapping và request journal, không chỉ generated producer test. |
| **Consumer decoding** | Stub trả đúng nhưng DTO deserialize lỗi. | Wire bytes/JSON type, `Content-Type`, client DTO và producer stub version. |

**Không bắt đầu bằng cách nới regex cho “dễ xanh”.** Trước tiên xác định **test nào fail và ở tầng nào**: producer verification, stub matching, consumer deserialization hay chính việc sinh/biên dịch test.

## 2. Hai phía của matcher không đối xứng

Spring Cloud Contract có thể dùng `bodyMatchers` ở **request** và ở **response**:

| Nơi trong DSL | Mục đích chính ở HTTP contract | Rủi ro nếu hiểu sai |
| --- | --- | --- |
| `request.bodyMatchers` | Mô tả cách **request** cần được nhận diện, đặc biệt khi sinh stubs. | WireMock quá chặt gây 404 no-match; quá lỏng làm stub chấp nhận request sai. |
| `response.bodyMatchers` | Mô tả cách **generated producer tests** kiểm **response producer**. | Khóa giá trị động gây false failure hoặc chỉ kiểm kiểu làm lọt lỗi nghiệp vụ. |
| `request.headers/queryParameters` | Xác định header/query cần thiết của request. | Consumer quên header nhưng stub vẫn trả 200 nếu mapping quá lỏng. |
| `response.headers` | Xác minh metadata mà producer cam kết trả. | So giá trị không quan trọng byte-by-byte hoặc bỏ header quan trọng. |
| Consumer test assertions | Kiểm **client thật** hiểu và xử lý dữ liệu từ stub. | Chỉ assert 200 mà không kiểm DTO, error handling hoặc side effect. |

Một matcher response `jsonPath('$.orderId', byRegex(...))` không có nghĩa Stub Runner sẽ phát sinh một `orderId` mới tùy ý mỗi request. **Stub thường phát response mẫu trong contract**; regex ở phía response chủ yếu giúp generated verification test kiểm **producer thật**.

Ngược lại, request matcher ảnh hưởng điều kiện mà WireMock dùng để quyết định **có trả stub response hay không**. Một request 404 no-match không nhất thiết là phản hồi 404 nghiệp vụ của producer.

## 3. Ví dụ xuyên suốt: Order API

Giả sử **Order Service** là producer, **Billing Service** là consumer:

~~~http
GET /api/orders/42
Accept: application/json
~~~

Response hợp lệ:

~~~json
{
  "id": 42,
  "orderId": "ORD-0042",
  "status": "PAID",
  "amountMinor": 125000,
  "currency": "VND",
  "createdAt": "2026-11-24T04:00:00Z",
  "metadata": {
    "trace.id": "trace-abc123"
  },
  "items": [
    {"sku": "SKU-42", "quantity": 2},
    {"sku": "SKU-99", "quantity": 1}
  ]
}
~~~

Hợp đồng có các ý nghĩa khác nhau:

- `id` phải tương ứng request `/42`, nên một assertion **exact 42** là có lý.
- `orderId` phải theo định dạng `ORD-` và các chữ số, nhưng có thể thay đổi giữa fixtures khác nhau.
- `status=PAID`, `currency=VND`, `amountMinor=125000` là **giá trị nghiệp vụ** của fixture này.
- `createdAt` là timestamp động, không nên luôn bằng một thời điểm.
- Key `trace.id` **chứa dấu chấm trong tên**, không có nghĩa là một object `trace` chứa key `id`.
- `items` là mảng; việc chọn **một phần tử**, **tất cả phần tử** hoặc **một list kết quả** tạo những kiểu matcher khác nhau.

Ta sẽ dùng cùng JSON này để bóc tách lỗi thay vì đổi ví dụ sau mỗi bước.

## 4. Một contract Groovy đầu tiên có thể sinh tests

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'

    request {
        method 'GET'
        url '/api/orders/42'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            orderId: 'ORD-0042',
            status: 'PAID',
            amountMinor: 125000,
            currency: 'VND',
            createdAt: '2026-11-24T04:00:00Z',
            metadata: ['trace.id': 'trace-abc123'],
            items: [
                [sku: 'SKU-42', quantity: 2],
                [sku: 'SKU-99', quantity: 1]
            ]
        )
        bodyMatchers {
            jsonPath('$.orderId',
                byRegex('^ORD-[0-9]{4}$'))
            jsonPath('$.createdAt',
                byRegex(
                    '^[0-9]{4}-[0-9]{2}-[0-9]{2}' +
                    'T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'
                ))
            jsonPath('$["metadata"]["trace.id"]',
                byRegex('^trace-[A-Za-z0-9-]+$'))
        }
    }
}
~~~

Điều chủ ý trong ví dụ:

1. `orderId` là **string** và có regex giới hạn độ dài.
2. `createdAt` có regex kiểm hình dạng **UTC timestamp** nhưng chưa đảm bảo ngày tháng thực sự tồn tại.
3. Key có dấu chấm được truy cập bằng **bracket notation**.
4. `id`, `status`, `amountMinor` và `currency` vẫn dùng expected values theo fixture.
5. `items` chưa có matcher riêng, vì trước hết cần xác định yêu cầu về thứ tự và số lượng phần tử.

Trong một project thực, plugin cần dependency, base test, JUnit/test mode và contract source path đúng. Không coi một đoạn Groovy DSL hợp lệ là bằng chứng generated test chắc chắn đã được tạo và chạy.

## 5. Bốn lớp escape dễ làm regex đổi nghĩa

Một chuỗi regex thường đi qua các lớp:

~~~text
Ý định regex:       \d{4}
Groovy source:       '\\d{4}'  (single-quoted string)
Giá trị sau Groovy:  \d{4}
Java generated code: "\\d{4}" (nếu generator dùng Java String literal)
Regex engine:        \d{4}
~~~

Ở mỗi lớp, dấu `\` có thể là **escape của string literal** hoặc là **một phần của cú pháp regex**. Lỗi thường gặp:

| Biểu thức nguồn | Vấn đề có thể phát sinh |
| --- | --- |
| `'\d{4}'` trong Groovy string | Một dấu gạch chéo ngược không escape đúng ở lớp string; cú pháp/ý nghĩa tùy parser. |
| `'\\d{4}'` trong Groovy single-quoted | Trả regex chứa `\d{4}` nếu cách escape được áp dụng đúng. |
| `"\\d{4}"` trong Java string literal | Trả regex chứa `\d{4}` cho `Pattern`. |
| `'\d{4}'` trong YAML single-quoted scalar | Dấu `\` được giữ nguyên; YAML single quotes không có escape kiểu Java. |
| `"\d{4}"` trong YAML double-quoted scalar | Có thể **sai YAML** vì `\d` không phải escape sequence hợp lệ của YAML. |
| `"[0-9]{4}"` | Tránh backslash và đủ rõ khi chỉ cần chữ số ASCII. |

**Không đếm dấu gạch chéo ngược bằng mắt rồi đoán**. Cần so **source DSL → generated source → giá trị regex thực**. Nếu chỉ cần chữ số ASCII, cách viết `[0-9]` thường dễ review hơn `\d` và tránh tranh luận về Unicode digit class.

### 5.1. Groovy single quotes, double quotes và slashy strings

Trong Groovy:

~~~groovy
def singleQuoted = '\\d{4}'
def doubleQuoted = "\\d{4}"
def slashy = /\d{4}/
~~~

Ba cách trên có thể đều đưa pattern `\d{4}` tới regex engine, nhưng **cơ chế escape/interpolation khác nhau**. Slashy string tiện cho regex có nhiều backslash, nhưng nếu pattern chứa dấu `/` hoặc `$` thì lại cần hiểu cú pháp slashy/GString của Groovy.

Khi contract dùng Groovy DSL, **ưu tiên single-quoted strings** cho regex không cần interpolation, hoặc dùng dạng ký tự `[0-9]` để giảm lớp escape. Không ghép các fragment nếu việc đó khiến người review khó nhìn pattern cuối cùng.

### 5.2. YAML single quotes thường đơn giản hơn cho regex

~~~yaml
matchers:
  body:
    - path: $.orderId
      type: by_regex
      value: '^ORD-[0-9]{4}$'
    - path: $.createdAt
      type: by_regex
      value: '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'
~~~

YAML single-quoted scalar giữ `\` là ký tự thường; nếu cần biểu thức có apostrophe `'`, cú pháp YAML single quotes escape apostrophe bằng **hai apostrophes liền nhau**. Trong YAML **double-quoted** strings, backslash có ý nghĩa escape riêng.

**Không sao chép cùng một literal `\\d` từ Java vào YAML mà cho rằng kết quả giống nhau**. Số lượng gạch chéo ngược cần thiết phụ thuộc lớp string đang viết.

## 6. Regex đúng về cú pháp nhưng sai miền dữ liệu

Giả sử mã Order yêu cầu `ORD-` theo sau bởi **đúng bốn chữ số ASCII**.

| Regex | `ORD-0042` | `ORD-42` | `XORD-0042-OLD` | Nhận xét |
| --- | --- | --- | --- | --- |
| `ORD-[0-9]+` | Có thể match | Có thể match | Có thể match **substring** nếu engine tìm kiếm | Không hạn chế độ dài/biên. |
| `^ORD-[0-9]{4}$` | Match | Không | Không | Kiểm toàn bộ chuỗi theo biên. |
| `^ORD-[0-9]{1,4}$` | Match | Match | Không | Chấp nhận 1–4 chữ số. |
| `^.*ORD-.*$` | Match | Match | Match | Quá lỏng. |

**Thao tác match có thể khác nhau**:

- `Pattern.matcher(value).matches()` thường yêu cầu **toàn bộ chuỗi** khớp.
- `Pattern.matcher(value).find()` tìm **một đoạn con** phù hợp.
- Một số DSL/JSONPath/WireMock matcher có hành vi hoặc flags riêng tùy version.

Do đó, nếu hợp đồng muốn **toàn bộ string** đúng định dạng, hãy dùng anchors `^...$` khi phù hợp và kiểm **generated assertion/mapping**. Không suy rằng mọi thư viện đều dùng `matches()` hoặc mọi phiên bản đều dùng `find()`.

**Giới hạn anchors:** `$` có sắc thái riêng với ký tự xuống dòng và flags của Java regex. Với dữ liệu yêu cầu nghiêm ngặt, cân nhắc cách generator kiểm full string và kiểm các edge cases chứa newline; không dùng anchors như một lời bảo đảm tuyệt đối mà không test.

## 7. Regex trên JSON number không giống regex trên String

Ví dụ JSON:

~~~json
{
  "amountMinor": 125000,
  "orderId": "ORD-0042"
}
~~~

JSON parser phân biệt:

- `$.amountMinor` → **JSON number** (có thể được JSONPath engine biểu diễn bằng Integer/Long/BigDecimal tùy parser).
- `$.orderId` → **JSON string**.

Nếu dùng:

~~~groovy
bodyMatchers {
    jsonPath('$.amountMinor', byRegex('[0-9]+'))
}
~~~

thì ta đang áp một **regular expression trên một giá trị JSON number**. Tùy generated assertion, thư viện có thể **chuyển number sang String**, yêu cầu matcher kiểu String, hoặc thất bại vì type mismatch. Một số trường hợp sẽ pass nhưng **mất kiểm kiểu JSON number**, vì chuỗi `"125000"` cũng có thể match `[0-9]+`.

Lựa chọn tốt hơn theo yêu cầu:

| Mong muốn | Hướng kiểm |
| --- | --- |
| `amountMinor` đúng bằng `125000` cho fixture | Giữ expected JSON number và equality assertion. |
| `amountMinor` có thể thay đổi nhưng **bắt buộc là number** | Dùng `byType()` phù hợp với JSONPath/type support, thêm range/business assertions. |
| `amountMinor` là số nguyên không âm | Kiểm JSON numeric type và miền giá trị bằng assertion hoặc custom command phù hợp. |
| `orderId` là chuỗi có định dạng | Dùng `byRegex(...)` trên string. |

**Quy tắc:** regular expression là công cụ kiểm **chuỗi ký tự**. Nếu consumer phụ thuộc vào **JSON type**, không dùng regex như sự thay thế duy nhất cho type assertion.

## 8. JSONPath không phải một chuỗi field name

Với JSON ví dụ:

~~~json
{
  "metadata": {
    "trace.id": "trace-abc123"
  },
  "items": [
    {"sku": "SKU-42"},
    {"sku": "SKU-99"}
  ]
}
~~~

Đường dẫn đúng:

| JSONPath | Kết quả mong đợi |
| --- | --- |
| `$.metadata` | Một JSON object. |
| `$.metadata['trace.id']` | String `trace-abc123`. |
| `$['metadata']['trace.id']` | String `trace-abc123`. |
| `$.metadata.trace.id` | Tìm `metadata.trace.id` qua **hai key lồng nhau**, không phải key literal `trace.id`. |
| `$.items[0].sku` | Scalar `SKU-42`. |
| `$.items[*].sku` | **Danh sách** `["SKU-42","SKU-99"]`. |
| `$.items.length()` | Hỗ trợ tùy JSONPath engine/biểu thức cụ thể, cần kiểm. |

**Dot notation** là đường đi qua các key lồng nhau; **bracket notation** có thể chọn key có dấu chấm, khoảng trắng, dấu gạch nối hoặc ký tự đặc biệt mà dot notation không biểu diễn an toàn.

Đây là lỗi rất hay gặp khi JSONPath trông “đúng” ở code review nhưng trả về **không có giá trị** sau generation.

### 8.1. Root object và root array

Đường dẫn:

~~~text
$.items[0].sku
~~~

chỉ đúng nếu JSON root là một **object** chứa property `items`. Nếu API trả trực tiếp một mảng:

~~~json
[
  {"sku": "SKU-42"},
  {"sku": "SKU-99"}
]
~~~

thì đường dẫn bắt đầu bằng:

~~~text
$[0].sku
~~~

**Đừng áp JSONPath của response dự kiến lên một wrapper object khác**. Nhiều lần test fail thực ra producer trả `{"data": {...}}` hoặc `{"result": [...] }`, nên path bắt đầu sai từ root.

## 9. JSONPath trả một scalar hay một list?

Sự khác nhau này thường bị che bởi DSL:

~~~groovy
bodyMatchers {
    jsonPath('$.items[0].sku', byRegex('^SKU-[0-9]+$'))
    jsonPath('$.items[*].sku', byRegex('^SKU-[0-9]+$'))
}
~~~

Biểu thức thứ nhất thường chọn **một string**. Biểu thức thứ hai chọn **một list**. Nếu generator đưa cả list vào matcher regex thiết kế cho String, có thể gặp:

~~~text
Expected: a string matching ^SKU-[0-9]+$
Actual:   [SKU-42, SKU-99]
~~~

Đây là **thông báo minh họa**, không phải error message cố định của Spring Cloud Contract.

Các cách xử lý dựa trên hợp đồng:

1. Nếu chỉ muốn kiểm **phần tử đầu**, dùng `$.items[0].sku` nhưng nhận thức rằng cách này **không kiểm các phần tử sau**.
2. Nếu muốn kiểm **mọi phần tử**, dùng matcher/JSONPath hỗ trợ **each element**, hoặc viết thêm assertion lặp trong test phù hợp.
3. Nếu muốn kiểm **có một SKU cụ thể**, dùng filter JSONPath có cú pháp được engine hỗ trợ hoặc kiểm list chứa phần tử trong consumer test.
4. Nếu muốn kiểm **số lượng/không trùng lặp**, thêm assertion về size/multiplicity.

Không “sửa” lỗi type mismatch bằng cách đổi pattern thành `.*SKU.*` để nó match `list.toString()`. Kết quả đó phụ thuộc cách Java in list và có thể pass dù từng phần tử sai.

## 10. Filter JSONPath: dấu quote và kiểu dữ liệu

Giả sử:

~~~json
{
  "items": [
    {"sku": "SKU-42", "quantity": 2},
    {"sku": "SKU-99", "quantity": 1}
  ]
}
~~~

Ý định: chọn dòng có `sku=SKU-42`. Một JSONPath filter thông dụng:

~~~text
$.items[?(@.sku == 'SKU-42')]
~~~

Đặt filter trong **Groovy DSL** cần chú ý dấu quote:

~~~groovy
// Single-quoted Groovy chứa single quotes trong filter:
jsonPath('$.items[?(@.sku == \'SKU-42\')]', byType())

// Cách dễ đọc hơn với double-quoted Groovy
// khi không có interpolation:
jsonPath("$.items[?(@.sku == 'SKU-42')]", byType())
~~~

Khi chuỗi đi qua Groovy parser, hãy kiểm JSONPath nhận được có còn dấu `'SKU-42'` hay không. Các engine JSONPath có khác biệt ở **cú pháp filter, kết quả list/scalar và coercion số**; tránh dùng một filter quá phức tạp nếu plugin/generator version không hỗ trợ chính xác.

**Không viết:** `@.quantity == '2'` nếu JSON thực là số `2` và bạn cần kiểm numeric equality. Một số thư viện có thể ép kiểu, một số không; hãy dùng JSON type đúng:

~~~text
$.items[?(@.quantity == 2)]
~~~

Đối với business invariant như `quantity > 0` cho **mọi item**, một filter chọn các phần tử phù hợp **không tự chứng minh toàn bộ các phần tử đều hợp lệ**. Cần kiểm **không tồn tại item vi phạm** hoặc lặp qua collection trong test phù hợp.

## 11. Missing, null và empty không được đánh đồng

So sánh:

~~~json
{}
~~~

~~~json
{"note": null}
~~~

~~~json
{"note": ""}
~~~

~~~json
{"note": "ship before Friday"}
~~~

Một JSONPath `$.note` có thể:

- **Không tồn tại** và ném `PathNotFoundException` hoặc trả giá trị mặc định tùy cấu hình.
- **Tồn tại với JSON null**, thường được biểu diễn bằng Java `null` hoặc NullNode.
- **Tồn tại với string rỗng**.
- **Tồn tại với string có nội dung**.

Một matcher kiểu `byRegex('.*')` có thể che mất ý nghĩa này vì regex chuỗi không thể quyết định **trường có tồn tại không** nếu framework đã ép missing/null thành chuỗi hoặc áp default không phù hợp.

Trước tiên viết **quy tắc hợp đồng**:

| Policy | Điều phải kiểm |
| --- | --- |
| `note` required, non-null string | Path tồn tại, không null, đúng type. |
| `note` optional, nếu có thì string | Missing được chấp nhận; null không được chấp nhận trừ khi policy cho phép. |
| `note` nullable | Phân biệt null với missing nếu semantics yêu cầu. |
| PATCH: missing không đổi, null để xóa | **Hai nhánh hành vi khác nhau** phải có contracts/ tests. |

Nếu DSL matcher tích hợp không phân biệt đầy đủ, bổ sung unit/integration test hoặc custom assertion có chủ đích. **Không nới matcher đơn giản vì “null làm test đỏ” mà chưa xác định hợp đồng nullability.**

## 12. JSONPath trên số thập phân, boolean và enum

Payload:

~~~json
{
  "paid": true,
  "amount": 1250.50,
  "currency": "VND",
  "status": "PAID"
}
~~~

Những kết quả có thể khác nhau:

| Path | JSON type | Điều cần bảo vệ |
| --- | --- | --- |
| `$.paid` | Boolean | `true` khác string `"true"`. |
| `$.amount` | Number | Số thập phân, chính sách precision/scale theo nghiệp vụ. |
| `$.currency` | String | Format ISO code hoặc equality theo fixture. |
| `$.status` | String | Tập enum được hỗ trợ; không phải “string bất kỳ”. |

Với tiền, ưu tiên truyền **minor units dạng số nguyên** nếu domain cho phép; nếu dùng decimal, hãy nêu rõ cách làm tròn/độ chính xác và không chỉ dùng regex decimal string.

**Java numeric class không phải JSON numeric type.** Một JSON number có thể được parser trả thành `Integer`, `Long`, `Double` hoặc `BigDecimal` tùy giá trị/cấu hình. Nếu generated test so `Integer(42)` với `Long(42)` mà fail, hãy kiểm **coercion và matcher của generated code**; không tự đổi contract thành string để “hợp kiểu”.

## 13. Đừng nhầm kiểu JSON với cách trình bày regex

Một mẫu dễ sai:

~~~groovy
response {
    body(
        orderId: 'ORD-0042',
        amountMinor: '125000'
    )
    bodyMatchers {
        jsonPath('$.amountMinor', byRegex('[0-9]+'))
    }
}
~~~

Ở đây contract đã định nghĩa `amountMinor` là **JSON string** vì mẫu là `'125000'`, trong khi consumer có thể cần **number**. Việc regex pass không chứng minh đúng kiểu.

Sửa **mô hình dữ liệu trước**:

~~~groovy
response {
    body(
        orderId: 'ORD-0042',
        amountMinor: 125000
    )
    bodyMatchers {
        jsonPath('$.orderId', byRegex('^ORD-[0-9]{4}$'))
        jsonPath('$.amountMinor', byEquality())
    }
}
~~~

Nếu `amountMinor` thực sự động, có thể dùng matcher kiểm kiểu và thêm assertion miền giá trị riêng. **Regex không được ưu tiên chỉ vì dễ gõ**; chọn công cụ theo **type và semantics**, không theo cách output test trông đơn giản.

## 14. Kiểm generated test source, không chỉ DSL

Khi test fail, bước có giá trị nhất là **mở file được plugin sinh**. Trong nhiều cấu hình Maven, generated source nằm dưới:

~~~text
target/generated-test-sources/
~~~

Với Gradle, generated source thường nằm dưới:

~~~text
build/generated-test-sources/
~~~

**Đường dẫn con và tên task phụ thuộc phiên bản plugin/cấu hình project**. Hãy xem Maven/Gradle log để tìm thư mục **được cấu hình thực sự**; đừng mặc định mọi bản dùng cùng thư mục chính xác.

Trong generated test, tìm:

1. Test method tương ứng `name` hoặc file contract.
2. Request `method`, `url`, headers và body mà test gửi.
3. JSONPath literal **sau khi được generator escape**.
4. Regex literal **sau khi compiler Java/Groovy diễn giải**.
5. Matcher implementation dùng `equals`, `matches`, `find` hay helper khác.
6. Việc parse JSON dẫn tới scalar hay collection.
7. Loại assertion dùng cho missing/null/JSON number.
8. Base test class và test mode thực tế.

Ví dụ **hình thái** một generated assertion:

~~~java
// PSEUDOCODE: generator và assertion library có thể khác.
Object actual = JsonPath.read(
    responseBody, "$.orderId"
);
assertThat(actual.toString())
    .matches("^ORD-[0-9]{4}$");
~~~

Không có bảo đảm generator viết đúng dạng trên. Điểm cần xem là **ý nghĩa của mã đã sinh**, không chỉ filename hoặc thông báo “Generating contracts”.

## 15. Kiểm WireMock mapping được chuyển đổi

Với request contract có body matcher, plugin thường sinh mapping dùng WireMock `bodyPatterns`/JSONPath hoặc các matcher tương đương:

~~~json
{
  "request": {
    "method": "POST",
    "urlPath": "/api/orders",
    "bodyPatterns": [
      {
        "matchesJsonPath": "$.clientRequestId"
      }
    ]
  },
  "response": {
    "status": 201,
    "headers": {"Content-Type": "application/json"},
    "body": "{\"id\":42,\"status\":\"CREATED\"}"
  }
}
~~~

**Đây là mapping rút gọn minh họa**, không nhất thiết là chính xác output của `byRegex(...)`: Spring Cloud Contract có thể sinh một JSONPath expression kết hợp điều kiện hoặc matcher khác để kiểm cả giá trị.

Với WireMock, có những biểu thức kiểm **path tồn tại**, có những biểu thức kiểm **giá trị trả về**; `matchesJsonPath` không nên được hiểu mặc định là “đã kiểm regex cho từng leaf string”.

**Điều cần xác minh:** request giả định không hợp lệ (`clientRequestId` sai, thiếu required field, sai body type) có **không match** hay không; request hợp lệ có match không. Chỉ nhìn một đoạn mapping tên `matchesJsonPath` rồi đoán ý nghĩa là chưa đủ.

### 15.1. Stub JAR có thể không phải bản đang được sinh

Nếu người học chỉ sửa Groovy DSL rồi chạy consumer test với:

~~~text
com.acme:order-service:1.4.1:stubs
~~~

trong khi stub mới chưa được đóng gói/publish, Stub Runner vẫn có thể đọc mapping **phiên bản cũ**. Phải kiểm:

- Tọa độ Maven `groupId:artifactId:version:stubs`.
- `StubsMode.LOCAL` hay `REMOTE`, repositoryRoot và Maven local cache.
- Checksum/nội dung JAR được nạp.
- Contract source Git SHA tương ứng artifact.
- WireMock request journal ở instance thực sự được consumer gọi.

**Đổi matcher ở producer nhưng không đổi artifact mà consumer test dùng** là một nguyên nhân rất phổ biến của “sửa rồi mà vẫn 404”.

## 16. Request `bodyMatchers`: giá trị động và 404 no-match

Giả sử Billing gửi:

~~~http
POST /api/orders
Content-Type: application/json

{
  "customerId": "C-42",
  "quantity": 2,
  "clientRequestId": "req-xyz-2026"
}
~~~

Trong contract, ta có thể viết:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldCreateOrder'
    request {
        method 'POST'
        url '/api/orders'
        headers {
            contentType(applicationJson())
        }
        body(
            customerId: 'C-42',
            quantity: 2,
            clientRequestId: 'req-example'
        )
        bodyMatchers {
            jsonPath('$.clientRequestId',
                byRegex('^req-[A-Za-z0-9-]+$'))
        }
    }
    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(id: 42, status: 'CREATED')
    }
}
~~~

Matcher request cho phép `clientRequestId` biến thiên theo format. Nhưng nó **không có nghĩa**:

- Bất kỳ `customerId` nào cũng được chấp nhận trong **stub tình huống này**.
- `quantity=-99` là request hợp lệ nếu validation yêu cầu dương.
- Consumer có thể bỏ `Content-Type` hoặc đổi URL mà không ảnh hưởng.

Nếu WireMock trả 404, hãy kiểm trước **method/path/headers/body** có khớp mapping thật không, thay vì nới ngay regex. Một 404 no-match không phải 404 nghiệp vụ; nên có contract 404 riêng nếu client cần kiểm xử lý order không tồn tại.

## 17. So sánh bằng bảng: lỗi ở phía producer hay phía consumer?

| Hiện tượng | Producer generated test | Consumer Stub Runner test | Lớp cần điều tra |
| --- | --- | --- | --- |
| Compiler báo `illegal escape` | **Fail trước khi chạy** | Có thể chưa liên quan | Generated Java/Groovy source và escaping DSL. |
| JSONPath `$.items[*].sku` cho list nhưng regex cần string | **Fail assertion** | Stub có thể vẫn trả sample | Response matcher/type của generated test. |
| `orderId` response không đúng format | **Fail** nếu matcher có hiệu lực | Stub có thể vẫn trả mẫu đúng | Implementation producer hoặc matcher bị sai. |
| Consumer POST có ID động, WireMock no-match | Producer test có thể PASS | **404** | Request body matcher/mapping. |
| Consumer DTO không đọc được `amountMinor` | Producer có thể PASS với matcher quá lỏng | **Fail deserialize** | JSON type, contract và DTO. |
| Cùng contract source nhưng consumer dùng stub JAR cũ | Producer test PASS sau sửa | Consumer test vẫn sai | Stub version/artifact/cache. |
| Test nhận JSON `null` khi expected missing | Tùy matcher | Tùy DTO | Nullability và JSONPath config. |
| Producer security test 401 bị 200 | **Fail** nếu negative contract đúng | Không nhất thiết phát hiện | Auth test context và contract status. |

**Không coi “producer test xanh” là lời bảo đảm consumer test sẽ xanh** nếu request mapping, stub version hoặc DTO client không phù hợp. Hai bộ kiểm có mục đích riêng nhưng phải sử dụng **cùng hợp đồng có hiệu lực**.

## 18. Một quy trình tái hiện tối thiểu có kiểm soát

Khi thấy regex hoặc JSONPath lỗi sau generation, hãy tạo **một contract và một response nhỏ**:

~~~json
{
  "orderId": "ORD-0042",
  "amountMinor": 125000,
  "items": [
    {"sku": "SKU-42"},
    {"sku": "SKU-99"}
  ]
}
~~~

Đặt một matcher duy nhất:

~~~groovy
bodyMatchers {
    jsonPath('$.orderId', byRegex('^ORD-[0-9]{4}$'))
}
~~~

Sau đó tăng dần độ phức tạp:

1. Thử `$.orderId` trên JSON fixture bằng JSONPath library thực tế.
2. Thử regex riêng với `Pattern` hoặc matcher library đúng version.
3. Sinh producer test, đọc source và xác nhận JSONPath/pattern nguyên vẹn.
4. Chạy đúng một test method.
5. Thêm matcher `$.items[0].sku`; xác nhận scalar.
6. Thêm `$.items[*].sku`; quan sát list và chọn assertion đúng collection semantics.
7. Thêm key có dấu chấm bằng bracket notation.
8. Thêm null/missing branch, rồi mới kết hợp vào contract lớn.

**Tạo repro nhỏ giúp phân biệt lỗi parser/escaping với lỗi app business**. Nếu bài kiểm tối thiểu fail ngay ở matcher, không cần debug database, JWT hay toàn bộ hệ thống Kafka.

## 19. Thử pattern độc lập với Java regex engine

Với Java, có thể viết một test nhỏ:

~~~java
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class RegexContractTest {
    @Test
    void orderIdHasFourDigits() {
        Pattern pattern = Pattern.compile("^ORD-[0-9]{4}$");

        assertThat(pattern.matcher("ORD-0042").matches())
            .isTrue();
        assertThat(pattern.matcher("ORD-42").matches())
            .isFalse();
        assertThat(pattern.matcher("XORD-0042-OLD").matches())
            .isFalse();
    }
}
~~~

Nếu pattern này pass nhưng generated assertion fail, khả năng cao khác biệt nằm ở **literal được sinh**, **JSONPath trả kiểu khác String**, hoặc **matcher semantics**. Nếu pattern riêng đã sai, cần sửa chính regex trước khi nghĩ tới Spring Cloud Contract.

### 19.1. Test escape `\d` riêng

~~~java
Pattern digits = Pattern.compile("^ORD-\\d{4}$");

assertThat(digits.matcher("ORD-0042").matches()).isTrue();
~~~

Trong Java string literal, `\\d` tạo regex escape `\d`. Viết `"\d"` trực tiếp vào Java source là sai cú pháp escape. Khi regex đi từ Groovy/YAML qua generator, source cuối cùng phải giữ đúng các lớp escape.

**Không chỉnh generated Java để tăng thêm backslash rồi commit nó vào source**: bước generate tiếp theo sẽ ghi đè sửa chữa đó. Hãy sửa literal ở **Groovy/YAML DSL** và kiểm code được sinh lại.

## 20. Tách kiểm JSONPath khỏi regex trong test nhỏ

Ví dụ dùng Jayway JsonPath (thường có trong chuỗi công cụ liên quan):

~~~java
import com.jayway.jsonpath.JsonPath;
import java.util.List;

String json = """
    {"items":[
      {"sku":"SKU-42"},
      {"sku":"SKU-99"}
    ]}
    """;

String first = JsonPath.read(json, "$.items[0].sku");
List<String> all = JsonPath.read(json, "$.items[*].sku");

assertThat(first).isEqualTo("SKU-42");
assertThat(all).containsExactly("SKU-42", "SKU-99");
~~~

Ví dụ dùng Java text block (**JDK 15+**) và AssertJ, giả định imports/dependency đầy đủ. Nó cho thấy **cùng JSON** nhưng JSONPath khác nhau trả **hai loại kết quả**.

Để kiểm key có dấu chấm:

~~~java
String metadata = """
    {"metadata":{"trace.id":"trace-abc123"}}
    """;

String trace = JsonPath.read(
    metadata, "$['metadata']['trace.id']");
assertThat(trace).isEqualTo("trace-abc123");
~~~

Nếu JSONPath library riêng trả đúng nhưng generated assertion không đúng, kiểm **JSONPath parser configuration, path literal, type conversion và version library** của build. Nhiều error message không cho thấy dấu quote bị mất, nên việc in path trong log chẩn đoán (không chứa dữ liệu nhạy cảm) rất có giá trị.

## 21. Quan sát generated test với Maven và Gradle

Với Maven Plugin đã được gắn vào lifecycle:

~~~shell
./mvnw clean test
~~~

Nếu cần tách giai đoạn để điều tra (mục đích minh họa):

~~~shell
./mvnw generate-test-sources
./mvnw test
~~~

**Lưu ý:** chạy goal/phase riêng lẻ không thay thế build producer verification hoàn chỉnh. Kiểm plugin có thật sự sinh tests trước `test-compile` và Surefire có chạy test, không chỉ có dòng `BUILD SUCCESS`.

Với Gradle Plugin:

~~~shell
./gradlew tasks --all
./gradlew generateContractTests
./gradlew test
~~~

Tên task/version có thể khác ở những cấu hình đặc thù. `generateContractTests` là tên thường gặp; hãy kiểm task graph và generated directory của **project thực tế**.

Một trình tự điều tra cụ thể:

1. Bỏ output cũ bằng `clean` để loại trừ generated source/stub mapping stale.
2. Bật log hợp lý để biết **contract files được phát hiện** và số generated tests.
3. Mở file generated test chứa matcher đáng nghi.
4. So pattern JSONPath/regex ở source DSL và generated code.
5. Chạy một test hẹp, giữ lại stack trace/actual JSON **được redaction**.
6. Với request matcher, mở JSON mapping từ plugin convert hoặc JAR `stubs`.
7. Chạy consumer test và xem request journal của đúng WireMock instance.

**Không cần bật debug vô hạn** khi CI chứa secrets, bearer token hoặc dữ liệu khách hàng thật. Ưu tiên contract fixture giả lập, log đường dẫn test/regex và metadata build.

## 22. Lỗi riêng của JSONPath filter và array order

Một filter chọn các phần tử:

~~~text
$.items[?(@.quantity > 1)]
~~~

không tương đương assertion:

> Tất cả phần tử đều phải có quantity lớn hơn 1.

Filter chỉ chọn **những phần tử thỏa điều kiện**. Nếu có phần tử không hợp lệ, kết quả filter vẫn có thể không rỗng, khiến test “có ít nhất một item hợp lệ” pass nhưng toàn array sai.

Ví dụ:

~~~json
{
  "items": [
    {"sku": "SKU-42", "quantity": 2},
    {"sku": "SKU-99", "quantity": -5}
  ]
}
~~~

Filter `quantity > 1` vẫn trả một phần tử. Để kiểm **mọi quantity dương**, phải assert không có phần tử vi phạm hoặc lặp qua mảng với test invariant:

~~~java
List<Integer> quantities =
    JsonPath.read(json, "$.items[*].quantity");

assertThat(quantities).allMatch(q -> q > 0);
~~~

**Một JSONPath biểu diễn được ý tưởng chọn dữ liệu không tự động biểu diễn điều kiện tổng quát trên toàn bộ mảng.** Khi yêu cầu nghiệp vụ phức tạp, nên tách contract shape với domain-level assertions, không ép mọi invariant thành một biểu thức khó đọc.

### 22.1. Array có thứ tự và không có thứ tự

Nếu `history` cam kết timeline tăng dần, dùng assert có thứ tự. Nếu `tags` là một tập, dùng so sánh bỏ thứ tự nhưng giữ multiplicity:

~~~java
assertThat(historyStates)
    .containsExactly("CREATED", "PAID", "SHIPPED");

assertThat(tags)
    .containsExactlyInAnyOrder("fragile", "insured");
~~~

Một matcher JSONPath `$..status` lấy nhiều status trong toàn cây có thể trả **list** không phản ánh đúng thứ tự/ngữ cảnh mà consumer cần. Hãy dùng đường dẫn cụ thể thay vì recursive descent `..` nếu dễ làm kết quả quá rộng.

## 23. Headers, charset và format: tránh đổ lỗi nhầm JSONPath

Không phải test fail ở response body đều do JSONPath. Ví dụ producer trả:

~~~http
Content-Type: application/json;charset=UTF-8
~~~

nhưng matcher header so nguyên chuỗi:

~~~text
application/json
~~~

Nếu consumer chỉ cần JSON media type, giá trị `charset` có thể được cho phép theo giao thức/cấu hình. Hãy kiểm **header matcher** đúng semantics, không đổi JSONPath của body để “chữa” một assertion header.

Các nguyên nhân khác cần loại trừ:

- Response là HTML error page do security filter, không phải JSON.
- App trả `204 No Content` nhưng contract dự kiến body JSON.
- Serialization của `Instant` đổi format hoặc timezone.
- Jackson naming strategy đổi `orderId` thành `order_id`.
- API thêm wrapper `data` làm JSONPath từ `$.orderId` thành `$.data.orderId`.
- Content encoding/compression khiến test helper chưa giải mã body đúng.

**Xem HTTP status, Content-Type và body thực tế trước khi sửa matcher**. Nếu producer trả 500 và một trang lỗi, chỉnh regex `orderId` sẽ không giải quyết nguyên nhân thật.

## 24. Messaging: JSONPath áp lên payload ở abstraction nào?

Hợp đồng messaging có thể định nghĩa:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'orderCreatedV1'
    input {
        triggeredBy('publishOrderCreated()')
    }
    outputMessage {
        sentTo('orders.created')
        headers {
            header('eventType', 'OrderCreated')
            header('contentType', 'application/json')
        }
        body(
            eventId: 'evt-00042',
            orderId: 'ORD-0042',
            amountMinor: 125000
        )
        bodyMatchers {
            jsonPath('$.eventId',
                byRegex('^evt-[A-Za-z0-9-]+$'))
        }
    }
}
~~~

Nếu generated message test fail ở `$.eventId`, cần xác định **payload mà MessageVerifierReceiver thực trả**:

- Một Java/Groovy Map?
- JSON String?
- `byte[]` chứa JSON UTF-8?
- Một envelope object có field `payload`?
- Một binary Avro/Protobuf record?

JSONPath chỉ hoạt động đúng khi được áp lên **cấu trúc JSON mà matcher mong đợi**. Nếu adapter trả toàn bộ envelope làm payload:

~~~json
{
  "payload": {
    "eventId": "evt-00042"
  }
}
~~~

thì `$.eventId` không tồn tại, dù `$.payload.eventId` có tồn tại. Tuy nhiên **không nên tự sửa contract thành `$.payload.eventId`** nếu envelope chỉ là wrapper nội bộ của adapter, không phải wire contract. Hãy sửa **adapter/serialization boundary** để generated test nhận payload đúng abstraction.

Với messaging, còn phải kiểm **destination, header types, serializer/schema registry, broker/test binder** và timeout. Một JSONPath regex pass trên test Map không chứng minh consumer thật đọc được bytes Kafka/queue; cần integration test với codec/transport khi có rủi ro.

## 25. Một ma trận lỗi và sửa có trách nhiệm

| Triệu chứng | Nguyên nhân nhiều khả năng | Cách sửa đúng |
| --- | --- | --- |
| Groovy parse error ở regex chứa `\d` | Chưa escape đúng lớp string. | Dùng `[0-9]` hoặc escape đúng Groovy literal; xem generated code. |
| YAML báo unknown escape `\d` | Dùng double-quoted scalar sai escape. | Đổi YAML single quotes hoặc escape đúng YAML. |
| Generated Java `illegal escape character` | Generator/literal để lại một `\` sai ở Java string. | Sửa DSL nguồn, xác minh source được sinh; kiểm version nếu là bug generator. |
| Regex chỉ match substring ngoài ý muốn | Thiếu anchors hoặc dùng matcher `find()`. | Xác định semantics, dùng pattern toàn chuỗi và mutation cases. |
| Regex match `"125000"` trong khi cần number | Chỉ kiểm ký tự số, bỏ qua JSON type. | Giữ numeric body sample và type/equality assertion. |
| JSONPath `$.metadata.trace.id` không tìm thấy | Key thật là `trace.id`. | Dùng bracket notation. |
| `$.items[*].sku` nhận list nhưng matcher mong String | Đường dẫn indefinite/collection. | Dùng path scalar hoặc matcher/loop kiểm collection. |
| Filter `?(@.quantity > 0)` pass dù có item âm | Filter chứng minh tồn tại item đúng, không phải tất cả đúng. | Assert tất cả phần tử hoặc không tồn tại phần tử vi phạm. |
| Missing và null bị coi như nhau | JSONPath default/path config. | Đặt policy presence/nullability và kiểm riêng. |
| JSON number 42 không bằng expected 42 | Parser/generator dùng numeric Java class khác hoặc equality quá đặc thù. | Kiểm JSON numeric semantics, type/coercion theo version. |
| Regex date pass với ngày 99 | Regex chỉ kiểm shape, không parse calendar. | Kết hợp `Instant.parse`/validator khi cần. |
| Producer test xanh, Stub Runner POST 404 | Response matcher đúng nhưng request body matcher chưa phù hợp. | Mở WireMock mapping, kiểm journal và ID động. |
| DSL đã sửa mà Stub Runner vẫn dùng mapping cũ | JAR stub/version/local cache cũ. | Rebuild/publish và ghim artifact checksum/version. |
| Test lỗi JSONPath nhưng response thực là HTML | Status/security/Content-Type sai. | Sửa lỗi producer hoặc fixture, không sửa JSONPath. |
| Generated matcher hoàn toàn không xuất hiện | DSL đặt sai scope, plugin version không hỗ trợ hoặc generator skip. | Đối chiếu source DSL, plugin logs và generated code. |
| Test xanh sau khi dùng `byType()` mọi field | Matcher quá lỏng. | Khôi phục equality/invariant cho business fields, mutation tests. |
| Messaging JSONPath không tìm key | Adapter trả envelope/byte[] không đúng abstraction. | Chuẩn hóa payload đúng, thêm codec/broker test. |
| Consumer nhận WireMock 404 thay vì ORDER_NOT_FOUND | No-match 404 bị nhầm 404 nghiệp vụ. | Kiểm matched mapping, request và error body contract. |

**Quy tắc chẩn đoán:** nếu một lỗi chỉ xuất hiện **sau bước generation**, phải xem **đầu ra của bước generation**. Nếu chỉ xuất hiện **khi Stub Runner chạy**, phải xem **artifact và WireMock mapping** mà Stub Runner thực tế nạp.

## 26. Đặt cổng chất lượng trong CI/CD

~~~mermaid
flowchart TD
    A["PR sửa Groovy/YAML contract"] --> B["Parse/generate producer tests"]
    B --> C{"Generated code compile?"}
    C -->|Không| D["Fail: kiểm escape và plugin version"]
    C -->|Có| E["Review JSONPath/pattern trong generated test"]
    E --> F["Run producer verification trên implementation thật"]
    F --> G{"Đúng semantics?"}
    G -->|Không| H["Fail: sửa contract hoặc implementation có chủ đích"]
    G -->|Có| I["Convert stubs và kiểm mapping"]
    I --> J["Consumer Stub Runner tests với client thật"]
    J --> K{"Request match và DTO đúng?"}
    K -->|Không| L["Kiểm WireMock journal, artifact và client"]
    K -->|Có| M["Publish/promote immutable stubs + báo cáo CI"]
~~~

Một pipeline chất lượng nên có:

1. **Sinh generated tests từ contracts thực**; fail nếu không phát hiện hợp đồng bắt buộc.
2. **Biên dịch tests**, không bỏ qua lỗi escape/JSONPath bằng skip flag.
3. **Chạy producer verification**; báo cáo test count và scenario names.
4. **Thực hiện mutation nhỏ** cho các contract quan trọng (một case hợp lệ PASS, một case phá tương thích FAIL), ít nhất khi thay đổi matcher phức tạp.
5. **Inspect stub mapping** đối với request matchers hoặc các endpoint mới.
6. **Chạy consumer Stub Runner** với artifact/version cố định và client thật.
7. **Lưu Git SHA, plugin versions, stub coordinates/checksum, test reports** để tái hiện lỗi.
8. **Không publish** khi generated tests bị skip, 0 test không chủ đích hoặc regression chưa giải quyết.

**Không dùng “đã sửa regex, build xanh” làm bằng chứng đủ**. Một regex nới quá rộng có thể làm test xanh bằng cách ngừng phát hiện lỗi. Cần kiểm ngược lại rằng một thay đổi sai vẫn FAIL.

## 27. Bài thực hành: từ lỗi JSONPath đến sửa đúng hợp đồng

Thực hành trên Order Service producer và Billing Service consumer, dùng Spring Cloud Contract phù hợp với phiên bản Spring Boot trong dự án.

1. **Tạo contract Groovy** cho `GET /api/orders/42` trả JSON ở mục 3, chứa `orderId`, `amountMinor`, `metadata["trace.id"]` và `items`.
2. **Viết regex đơn giản** `^ORD-[0-9]{4}$` cho `$.orderId`. Chạy test regex Java độc lập và xác nhận case đúng/sai.
3. **Thử regex `\d`** trong Groovy/YAML với các cách quote khác nhau; so source DSL, generated Java literal và giá trị regex thật. Ghi lại lỗi parse/compile nếu có.
4. **Tạo JSONPath sai có chủ đích** `$.metadata.trace.id` rồi sửa thành `$['metadata']['trace.id']` sau khi quan sát JSONPath response.
5. **Dùng `$.items[*].sku` với matcher mong string**, ghi nhận kết quả list/type mismatch; chuyển thành matcher collection hoặc assert từng item phù hợp yêu cầu.
6. **Tạo một filter `quantity > 0`**, chứng minh nó chỉ chọn một số item và không bảo đảm **mọi quantity đều dương**; thêm test invariant đúng.
7. **Giữ `amountMinor` là JSON number**, thử matcher regex và `byType()`; xác định lựa chọn giữ đúng type/value semantics của consumer.
8. **Thử thiếu `note`, `note:null` và `note:""`**, ghi rõ policy API và assertion cần thiết.
9. **Sinh lại producer tests**, kiểm file generated (không sửa thủ công), chạy `mvn clean test` hoặc Gradle task tương đương và xem đúng failure.
10. **Cố tình phá producer**: đổi `orderId` format, JSON number thành string, status 200 thành 500; generated test phải FAIL.
11. **Thử thay đổi hợp lệ**: đổi trace ID hợp lệ hoặc timestamp hợp lệ; test không được FAIL khi đó chỉ là metadata động đã cho phép.
12. **Viết contract POST có request clientRequestId động**; kiểm WireMock mapping sau convert, thực thi consumer test qua Stub Runner.
13. **Làm client gọi sai path**, quan sát WireMock 404 no-match và phân biệt với 404 nghiệp vụ từ contract lỗi.
14. **Đóng gói artifact `stubs` phiên bản mới**, kiểm JAR/mapping, làm consumer test dùng đúng version và không lấy bản stale từ local cache.
15. **Thêm message contract** có `eventId` và header `eventType`; nếu dùng custom messaging adapter, kiểm payload không bị bọc envelope sai khiến JSONPath khác root.
16. **Lập báo cáo ngắn**: source matcher, generated assertion, response/request thực, nguyên nhân và cách sửa; đưa vào CI gate.

**Tiêu chí đạt:** người học **phân biệt được lỗi DSL escape, generated code, JSONPath path/result type, regex engine, stub request matcher và consumer decode**, sửa ở nguồn chính xác, chứng minh một trường hợp hợp lệ **PASS** và một thay đổi phá hợp đồng **FAIL**, không bỏ qua producer verification để làm build xanh.

## 28. Câu hỏi tự kiểm tra

1. Một regex có thể đi qua những lớp escape nào từ Groovy DSL tới Java regex engine?
2. Vì sao `[0-9]{4}` thường dễ dùng hơn `\d{4}` khi debug Groovy/YAML DSL?
3. Khác biệt của YAML single quotes và double quotes đối với backslash là gì?
4. `Pattern.matcher(...).matches()` khác `find()` như thế nào?
5. Vì sao regex `ORD-[0-9]+` có thể quá lỏng khi cần đúng bốn chữ số?
6. Có thể dùng chỉ `byRegex('[0-9]+')` để chứng minh `amountMinor` là JSON number không?
7. `$.metadata.trace.id` khác `$['metadata']['trace.id']` khi key là `trace.id`?
8. `$.items[0].sku` trả dữ liệu loại gì, còn `$.items[*].sku` trả gì?
9. Một JSONPath filter chọn các item có `quantity > 0` có chứng minh mọi item đều dương không?
10. Missing, JSON null và empty string có luôn tương đương không?
11. Khi JSON parser trả `Long` nhưng expected matcher dùng `Integer`, nên kiểm điều gì?
12. Vì sao generated producer test code cần được đọc khi matcher DSL trông đúng?
13. Vì sao không nên chỉnh sửa trực tiếp mã test được generator sinh ra?
14. `request.bodyMatchers` và `response.bodyMatchers` khác nhau ở ảnh hưởng tới stubs/tests?
15. Vì sao WireMock trả 404 chưa chắc producer định nghĩa lỗi 404 nghiệp vụ?
16. Khi sửa contract nguồn nhưng Stub Runner vẫn chạy sai, vì sao cần kiểm JAR version/checksum?
17. Nếu response thực là HTML error page, sửa JSONPath có giúp giải quyết không?
18. Với array có thứ tự, vì sao không dùng matcher bỏ qua thứ tự?
19. Regex timestamp kiểm đúng hình dạng đã chứng minh timestamp thực sự hợp lệ chưa?
20. Với message contract, JSONPath cần áp vào payload hay envelope nội bộ của adapter?
21. Một matcher bị nới để test PASS cần kiểm những mutation nào để chứng minh không lọt regression?
22. CI cần lưu những dấu vết gì để tái hiện một lỗi sau generation?

## 29. Checklist debug tại bàn làm việc

| Kiểm tra | Câu hỏi cần trả lời |
| --- | --- |
| **Contract source** | Đúng file Groovy/YAML và đúng bodyMatchers scope chưa? |
| **Parser** | DSL/YAML parse được chưa, quotes/backslashes đã đúng lớp chưa? |
| **Generator** | Generated test source/mapping mới nhất hay output cũ? |
| **Literal** | Pattern JSONPath/regex sau sinh có giữ ý nghĩa gốc không? |
| **JSON type** | JSONPath trả String, Number, Boolean, Null, Map hay List? |
| **JSONPath result** | Path có tồn tại, có đúng root và bracket notation không? |
| **Regex semantics** | Full match hay substring, anchors/flags/charset có đúng không? |
| **Business rules** | Exact, type, regex và invariant được chọn đúng mức chưa? |
| **Generated tests** | Test có biên dịch, được runner phát hiện và thực sự chạy không? |
| **Stub mapping** | Request method/path/header/body matcher đúng và đủ chặt không? |
| **Stub artifact** | Đúng Maven coordinates, classifier, version, checksum không? |
| **Consumer client** | Gửi request thật đúng và parse response đúng không? |
| **Messaging adapter** | Có đổi envelope, serializer hoặc header types không? |
| **CI evidence** | Có test report, source SHA, plugin version và case FAIL tái hiện được không? |

**Ghi nhớ:** **Regex hoặc JSONPath “đúng trên giấy” chỉ thực sự đúng khi đi qua DSL parser, generated source, matcher runtime và stub mapping mà không đổi nghĩa**. Với Spring Cloud Contract, hãy tách rõ **request matcher của WireMock** và **response matcher của producer verification**, kiểm regex escaping theo lớp Groovy/YAML/Java, kiểm JSONPath trên JSON thật và phân biệt scalar–list, missing–null, number–string. Khi có lỗi, đọc **generated test code và mapping của artifact `stubs` đang dùng**, sửa **contract nguồn** thay vì generated output, chạy cả producer và consumer tests. Một thay đổi hợp lệ nên **PASS**, còn một thay đổi phá tương thích phải **FAIL**: đó mới là bằng chứng cho một hợp đồng đáng tin trong CI/CD.
