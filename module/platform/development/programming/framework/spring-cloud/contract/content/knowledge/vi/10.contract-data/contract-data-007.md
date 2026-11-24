# Dữ liệu biên: rỗng, thiếu, null và giá trị giới hạn

## 1. Vì sao phải kiểm thử dữ liệu biên trong hợp đồng?

Một API có thể hoạt động tốt với request mẫu nhưng vẫn phá vỡ consumer khi gặp trường bị thiếu, giá trị `null`, chuỗi rỗng hoặc một số nằm ngay ngoài giới hạn cho phép. Đó là **hành vi giao tiếp công khai**: consumer phải biết nên gửi gì và có thể kỳ vọng status, response body, mã lỗi nào.

Trong **Spring Cloud Contract (SCC)**, producer và consumer thống nhất hành vi HTTP hoặc message bằng **Groovy DSL/YAML DSL**. SCC sinh test kiểm chứng implementation của producer và stub cho consumer sử dụng với **Stub Runner**. Đưa các kiểm tra đó vào CI giúp phát hiện thay đổi API không tương thích trước khi phát hành.

Dữ liệu biên đòi hỏi chúng ta trả lời những câu hỏi rất cụ thể:

- Trường **không xuất hiện** có giống trường xuất hiện với `null` không?
- Chuỗi `""`, chuỗi toàn khoảng trắng, mảng `[]` và object `{}` có hợp lệ không?
- `0` và `false` có phải giá trị hợp lệ hay sẽ bị hiểu nhầm thành “không có”?
- Giá trị bằng min/max được chấp nhận hay bị từ chối?
- Khi input sai, consumer nhận `400`, `422`, lỗi dạng nào và mã lỗi gì?

Bài học này hướng dẫn thiết kế **ma trận tình huống**, thể hiện bằng contract, kiểm chứng hai phía và xử lý các giới hạn của matcher/stub. Ví dụ xuyên suốt là API tính báo giá sản phẩm.

### Kết quả học tập

Bạn sẽ có thể:

1. Phân loại trường **thiếu**, `null`, empty, blank và các giá trị sát biên.
2. Xây dựng hợp đồng HTTP cho cả **thành công** lẫn **lỗi** ở dữ liệu biên.
3. Viết Groovy/YAML DSL cho JSON request/response, bao gồm field không xuất hiện và field explicit null.
4. Hiểu giới hạn của JSONPath matcher, Bean Validation và serializer.
5. Chạy generated producer tests, kiểm tra stub mappings và kiểm thử consumer với stub ứng viên.
6. Áp dụng cùng tư duy cho mảng, thông điệp và các API PATCH.

## 2. Sáu trạng thái cần phân biệt

Giả sử request có thuộc tính `couponCode`. Các dạng dưới đây **không đồng nghĩa**:

~~~json
{"sku":"SKU-123","quantity":1}
~~~

~~~json
{"sku":"SKU-123","quantity":1,"couponCode":null}
~~~

~~~json
{"sku":"SKU-123","quantity":1,"couponCode":""}
~~~

~~~json
{"sku":"SKU-123","quantity":1,"couponCode":"   "}
~~~

~~~json
{"sku":"SKU-123","quantity":1,"couponCode":"SAVE10"}
~~~

~~~json
{"sku":"SKU-123","quantity":1,"couponCode":123}
~~~

| Trạng thái | Đặc điểm | Một quy tắc API có thể chọn |
|---|---|---|
| **Thiếu (absent)** | JSON không có key `couponCode` | Chấp nhận và dùng mặc định |
| **Null tường minh** | Key có mặt với JSON `null` | Từ chối vì client đã gửi giá trị null |
| **Chuỗi rỗng (empty)** | `""`, độ dài bằng 0 | Từ chối |
| **Chuỗi trắng (blank)** | `"   "`, có ký tự nhưng không có nội dung có nghĩa | Từ chối |
| **Chuỗi có giá trị** | `"SAVE10"` | Có thể chấp nhận sau khi validate |
| **Sai kiểu** | `123` là JSON number | Từ chối vì contract yêu cầu string |

Một số cặp khác dễ nhầm:

| Giá trị | Khác với | Vì sao |
|---|---|---|
| `0` | `null` và absent | Số không vẫn là một số |
| `false` | absent | Boolean false có ý nghĩa nghiệp vụ |
| `[]` | `null` | Mảng tồn tại nhưng không có phần tử |
| `{}` | `null` | Object tồn tại nhưng không có thuộc tính |
| `"0"` | `0` | String khác JSON number |
| `"null"` | `null` | Chuỗi bốn ký tự khác JSON null |
| `" "` | `""` | Chuỗi có khoảng trắng khác chuỗi rỗng |

**Không có quy tắc chung** buộc mọi API xử lý absent và null giống nhau hoặc khác nhau. Điều cần thiết là chính sách đã được thống nhất trong contract và có test bảo vệ.

## 3. Bối cảnh: API tính báo giá

**Pricing Service** là producer của endpoint:

~~~http
POST /api/quotes HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "sku": "SKU-123",
  "quantity": 1,
  "couponCode": "SAVE10"
}
~~~

**Checkout Service** là consumer dùng endpoint này.

Chúng ta **giả định** quy tắc kinh doanh cho bài thực hành:

| Thuộc tính | Quy tắc |
|---|---|
| `sku` | Bắt buộc, phải là string không rỗng |
| `quantity` | Bắt buộc, phải là số nguyên JSON từ **1 đến 100**, bao gồm hai đầu |
| `couponCode` thiếu | Hợp lệ; không áp dụng giảm giá |
| `couponCode: null` | Lỗi `400`, mã `COUPON_NULL` |
| `couponCode: ""` hoặc blank | Lỗi `400`, mã `COUPON_BLANK` |
| `couponCode` hợp lệ | Mã string được hệ thống chấp nhận |
| `quantity` thiếu | Lỗi `400`, mã `QUANTITY_REQUIRED` |
| `quantity: null` | Lỗi `400`, mã `QUANTITY_NULL` |
| `quantity` ngoài khoảng | Lỗi `400`, mã `QUANTITY_OUT_OF_RANGE` |
| `quantity` sai kiểu | Lỗi `400`, mã `QUANTITY_INVALID_TYPE` |

Các mã lỗi trong bảng là **thiết kế minh họa**, không phải hành vi mặc định của Spring MVC hay Spring Cloud Contract. Dự án thật có thể chọn `422` hay gom các lỗi vào một mã công khai; khi đó hợp đồng phải phản ánh đúng quyết định đó.

Response thành công nếu không có coupon:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-123",
  "quantity": 1,
  "discountApplied": false,
  "totalVnd": 150000
}
~~~

Response lỗi khi explicit null:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "code": "COUPON_NULL",
  "message": "couponCode must not be null"
}
~~~

Với consumer, **HTTP status và mã lỗi ổn định** thường quan trọng hơn câu chữ thông báo vốn có thể thay đổi hoặc được bản địa hóa.

## 4. Ma trận biên cho số lượng 1..100

Một tập tình huống điển hình:

| Giá trị `quantity` | Nhóm kiểm thử | Kỳ vọng |
|---|---|---|
| Không có key | Thiếu bắt buộc | `400 QUANTITY_REQUIRED` |
| `null` | Null tường minh | `400 QUANTITY_NULL` |
| `"1"` | Sai kiểu: string | `400 QUANTITY_INVALID_TYPE` |
| `1.5` | Số thập phân thay vì số nguyên | `400 QUANTITY_INVALID_TYPE` |
| `-1` | Giá trị âm | `400 QUANTITY_OUT_OF_RANGE` |
| `0` | **min − 1** | `400 QUANTITY_OUT_OF_RANGE` |
| `1` | **min** | `200` |
| `2` | **min + 1** | `200` |
| `99` | **max − 1** | `200` |
| `100` | **max** | `200` |
| `101` | **max + 1** | `400 QUANTITY_OUT_OF_RANGE` |
| `2147483648` | Vượt giới hạn số nguyên Java 32 bit | `400 QUANTITY_INVALID_TYPE` theo quy ước ví dụ |

Mẫu **min−1, min, min+1, max−1, max, max+1** giúp phát hiện lỗi so sánh `<` với `<=`, hoặc `>` với `>=`. Không cần kiểm hết mọi số từ 1 đến 100; hãy ưu tiên **lớp tương đương** và các ranh giới làm thay đổi quyết định.

Ngoài quantity, cần xem xét: mã giảm giá quá dài, SKU chỉ có khoảng trắng, mảng chứa 0 hoặc quá nhiều phần tử, giá tiền âm, kiểu boolean sai, ký tự Unicode, giá trị lớn vượt phạm vi kiểu dữ liệu.

## 5. YAML DSL: field thiếu được viết thế nào?

YAML contract dùng `request.body` để biểu diễn payload. Trong YAML, **không khai báo key** nghĩa là field thiếu trong body mẫu; ghi `key: null` hoặc `key: ~` là giá trị null, còn `key: ''` là chuỗi rỗng.

Ví dụ tệp `src/test/resources/contracts/quotes/quote-without-coupon.yml`:

~~~yaml
description: Không gửi couponCode thì tính báo giá không giảm
name: quote_without_coupon

request:
  method: POST
  url: /api/quotes
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 1

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 1
    discountApplied: false
    totalVnd: 150000
~~~

Lưu ý: `request.body` **không có** `couponCode`. Đây là case “không gửi mã giảm giá”, khác với việc gửi `couponCode: null`.

Những field có thể bị YAML tự suy kiểu, ví dụ chuỗi toàn chữ số hoặc giá trị giống boolean, nên được đặt trong dấu nháy khi API yêu cầu **string**. Riêng `quantity: 1` là JSON number theo chủ đích.

## 6. YAML DSL: explicit null, empty và blank

### 6.1. Explicit null

Tệp hợp đồng riêng:

~~~yaml
description: Từ chối couponCode null tường minh
name: reject_null_coupon

request:
  method: POST
  url: /api/quotes
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 1
    couponCode: null

response:
  status: 400
  headers:
    Content-Type: application/json
  body:
    code: COUPON_NULL
    message: couponCode must not be null
~~~

### 6.2. Chuỗi rỗng

~~~yaml
description: Từ chối couponCode là chuỗi rỗng
name: reject_empty_coupon

request:
  method: POST
  url: /api/quotes
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 1
    couponCode: ''

response:
  status: 400
  headers:
    Content-Type: application/json
  body:
    code: COUPON_BLANK
~~~

### 6.3. Chuỗi chỉ chứa khoảng trắng

~~~yaml
description: Từ chối couponCode chỉ gồm khoảng trắng
name: reject_blank_coupon

request:
  method: POST
  url: /api/quotes
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 1
    couponCode: '   '

response:
  status: 400
  headers:
    Content-Type: application/json
  body:
    code: COUPON_BLANK
~~~

Dấu nháy trong `couponCode: ''` và `couponCode: '   '` là quan trọng. Nếu viết `couponCode:` không kèm giá trị, YAML parser thường hiểu là **null**.

Ba contract trên đều mô tả **cùng URL và method**, nhưng khác body request và kết quả. Khi sinh stub, phải xác minh các mapping nhận diện đúng từng case, nhất là giữa **absent** và **null**. Không nên cho rằng mọi kiểu so khớp JSON của WireMock tự động phân biệt chúng một cách chặt chẽ.

## 7. YAML DSL: giá trị bằng và vượt giới hạn

Trường hợp **bằng max**, còn hợp lệ:

~~~yaml
description: quantity bằng 100 vẫn được chấp nhận
name: quote_at_max_quantity

request:
  method: POST
  url: /api/quotes
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 100

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 100
    discountApplied: false
    totalVnd: 15000000
~~~

Trường hợp **max + 1**, bị từ chối:

~~~yaml
description: quantity 101 vượt giới hạn
name: reject_quantity_101

request:
  method: POST
  url: /api/quotes
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: 101

response:
  status: 400
  headers:
    Content-Type: application/json
  body:
    code: QUANTITY_OUT_OF_RANGE
~~~

Tương tự, nên có case `quantity: 0` (lỗi) và `quantity: 1` (thành công). Các số tiền trong ví dụ dùng giả định mỗi đơn vị giá 150.000 đồng; nếu sản phẩm có tính giá động, cần thiết kế assertion theo hành vi được cam kết thay vì cố định số tiền không ổn định.

**Một contract với `quantity: 50` chưa kiểm chứng được điều kiện có bao gồm 1 và 100 hay không.**

## 8. Groovy DSL: so sánh thiếu, null và empty

Groovy DSL dùng map để biểu diễn JSON body. Ví dụ explicit null:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Từ chối couponCode null'

    request {
        method POST()
        url '/api/quotes'
        headers {
            contentType(applicationJson())
        }
        body([
            sku: 'SKU-123',
            quantity: 1,
            couponCode: null
        ])
    }

    response {
        status BAD_REQUEST()
        headers {
            contentType(applicationJson())
        }
        body(code: 'COUPON_NULL')
    }
}
~~~

Tương ứng, nếu field **thiếu**, không đưa key vào map:

~~~groovy
body([
    sku: 'SKU-123',
    quantity: 1
    // Không có key couponCode
])
~~~

Các giá trị có mặt nhưng rỗng:

~~~groovy
body([
    sku: 'SKU-123',
    quantity: 1,
    couponCode: '',   // Empty string
    tags: [],         // Empty array
    metadata: [:]     // Empty object
])
~~~

Đây là các đoạn minh họa **thay thế cho nhau**, không phải khuyến nghị gom mọi tình huống trái ngược vào một contract. Khi chuyển đổi giữa Groovy và YAML, phải chạy lại generated tests và kiểm tra stub mapping, vì cú pháp giống ý tưởng chưa đảm bảo mọi matcher có semantics giống nhau ở từng phiên bản.

## 9. Field thiếu khác body HTTP bị thiếu

Hai tình huống thường bị đánh đồng:

~~~http
POST /api/quotes HTTP/1.1
Content-Type: application/json

{"sku":"SKU-123","quantity":1}
~~~

Request trên **có body JSON**, chỉ không có field `couponCode`.

Ngược lại:

~~~http
POST /api/quotes HTTP/1.1
Content-Length: 0
~~~

Request thứ hai **không có body**. Trường hợp khác nữa là một body chứa JSON literal `null`:

~~~http
POST /api/quotes HTTP/1.1
Content-Type: application/json

null
~~~

Chúng có thể được Spring MVC xử lý ở các tầng khác nhau: parse HTTP body, convert JSON, bind DTO rồi mới validate field. Nếu API yêu cầu JSON object, cần xác định response công khai cho body vắng mặt, JSON null và object thiếu trường; không nên mặc nhiên nghĩ một contract bao phủ cả ba.

## 10. Java DTO có thể làm mất thông tin absent/null

Xét DTO:

~~~java
public record QuoteRequest(
        String sku,
        Integer quantity,
        String couponCode) {
}
~~~

Với cấu hình Jackson thông dụng, **cả hai** body sau có thể cho `couponCode() == null`:

~~~json
{"sku":"SKU-123","quantity":1}
~~~

~~~json
{"sku":"SKU-123","quantity":1,"couponCode":null}
~~~

Nếu contract quy định hai kết quả khác nhau, chỉ kiểm tra DTO là không đủ. Cần theo dõi **field presence** trước hoặc trong quá trình deserialization.

Một cách minh họa bằng `JsonNode`:

~~~java
import com.fasterxml.jackson.databind.JsonNode;

public String classifyCoupon(JsonNode body) {
    if (!body.has("couponCode")) {
        return "ABSENT";
    }

    JsonNode coupon = body.get("couponCode");

    if (coupon.isNull()) {
        return "NULL";
    }
    if (!coupon.isTextual()) {
        return "WRONG_TYPE";
    }
    if (coupon.asText().isEmpty()) {
        return "EMPTY";
    }
    if (coupon.asText().isBlank()) {
        return "BLANK";
    }

    return "PRESENT";
}
~~~

Trong Jackson, `has("couponCode")` giúp kiểm tra sự tồn tại của field, kể cả khi value là JSON null; `hasNonNull(...)` yêu cầu vừa tồn tại vừa khác null. Tùy kiểu dữ liệu và cách bind, có thể dùng custom deserializer hoặc wrapper trạng thái, nhưng không nên làm phức tạp DTO nếu contract không cần phân biệt absent/null.

## 11. Bean Validation và những giới hạn của nó

Jakarta Bean Validation được Spring Boot sử dụng rộng rãi:

| Constraint | Kiểm tra chủ yếu |
|---|---|
| `@NotNull` | Giá trị không phải null |
| `@NotEmpty` | String, collection, map hoặc array không null và không rỗng |
| `@NotBlank` | Chuỗi có nội dung khác blank theo tiêu chí validator |
| `@Size(min, max)` | Giới hạn độ dài hoặc số phần tử |
| `@Min(1)` / `@Max(100)` | Giới hạn số |
| `@DecimalMin` / `@DecimalMax` | Biên số thập phân, có thể inclusive/exclusive |
| `@Digits` | Giới hạn số chữ số của giá trị số |

Ví dụ DTO:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record SimpleQuoteRequest(
        @NotBlank String sku,
        @NotNull @Min(1) @Max(100) Integer quantity,
        String couponCode) {
}
~~~

Cần chú ý:

- `@NotNull` **không phân biệt absent và explicit null** nếu cả hai đã được ánh xạ thành Java null.
- `@NotEmpty` có thể chấp nhận `"   "` vì chuỗi không có độ dài 0; với nội dung text thường dùng `@NotBlank`.
- `@Size` và nhiều constraint khác thường không tự từ chối null, nên trường bắt buộc cần constraint phù hợp.
- Phải kích hoạt validation của Spring MVC bằng `@Valid`/`@Validated` ở vị trí thích hợp và có dependency validation.
- `@Min` và `@Max` không tự xử lý đầy đủ các lỗi parse JSON, overflow hoặc sai kiểu trước khi tới Bean Validation.

Dùng `Integer` cho quantity giúp phân biệt **số 0** với **null**; primitive `int` có thể làm lẫn giá trị mặc định và trạng thái thiếu tùy cấu hình binder. Nhưng `Integer` vẫn không giải quyết được khác biệt **absent/explicit null**.

## 12. Matcher không tự thay thế dữ liệu biên

SCC có `response.matchers` và `request.matchers`. Ví dụ matcher response kiểm tra kiểu:

~~~yaml
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    quantity: 100
    totalVnd: 15000000
  matchers:
    body:
      - path: $.quantity
        type: by_type
      - path: $.totalVnd
        type: by_type
~~~

**`by_type` chỉ kiểm tra kiểu**, không đảm bảo quantity thuộc đoạn 1..100. Một response có `quantity: 101` vẫn có thể hợp lệ về kiểu.

Khi cần xác nhận **chính xác** một giá trị ở ranh giới, có thể viết:

~~~yaml
response:
  status: 200
  body:
    status: READY
    quantity: 100
    quoteId: Q-1001
  matchers:
    body:
      - path: $.status
        type: by_equality
      - path: $.quantity
        type: by_equality
      - path: $.quoteId
        type: by_regex
        value: '^Q-[0-9]+$'
~~~

Ở đây `quoteId` là dữ liệu động theo regex; status và quantity phải bằng mẫu. Tuy nhiên, **response matcher chỉ chứng minh giá trị trả trong tình huống đã mô tả**. Để kiểm tra producer từ chối `quantity: 101`, cần một contract riêng hoặc test bổ sung cho request đó.

Tương tự, một số cách so khớp JSON body trong stub có thể chỉ so cấu trúc một phần hoặc cho phép trường bổ sung. **Không suy ra** rằng request body mẫu không có `couponCode` sẽ luôn từ chối request chứa `couponCode: null`. Phải xem **mapping sinh ra** và chạy các case cạnh tranh trực tiếp trên Stub Runner.

## 13. Dữ liệu số: integer, thập phân và tràn số

Các JSON dưới đây có thể cùng biểu thị một giá trị toán học nhưng **khác kiểu/biểu diễn**:

~~~json
{"quantity":1}
~~~

~~~json
{"quantity":1.0}
~~~

~~~json
{"quantity":"1"}
~~~

Nếu hợp đồng yêu cầu **số nguyên JSON**, một consumer gửi chuỗi `"1"` có thể bị từ chối dù framework có khả năng coercion. Cần chốt việc **cho phép hay cấm chuyển kiểu ngầm**.

Số rất lớn:

~~~json
{"quantity":2147483648}
~~~

có thể vượt phạm vi `int` 32-bit có dấu của Java. Nếu parser/mapper trả exception trước khi vào controller, response có thể khác lỗi validation `@Max(100)`. Contract nên xác định consumer nhận **mã lỗi công khai** nào, thay vì phụ thuộc class exception nội bộ.

Với tiền tệ, cần kiểm tra các biên như `0`, giá âm, giới hạn thanh toán, số quá dài, giá trị có nhiều chữ số thập phân. Trong Java, nên dùng `BigDecimal` cho tính toán tiền cần chính xác; hợp đồng cần nói rõ **đơn vị, số chữ số thập phân và cách làm tròn**.

## 14. Chuỗi và Unicode: “32 ký tự” không phải lúc nào cũng rõ

Giả sử mã giảm giá dài từ **1 đến 32 ký tự** và không chứa toàn whitespace.

Ma trận nên bao gồm:

| Input | Mục đích |
|---|---|
| `""` | Độ dài 0 |
| `" "` | Whitespace |
| `"A"` | Độ dài tối thiểu |
| Chuỗi 32 ký tự hợp lệ | Bằng max |
| Chuỗi 33 ký tự | Max + 1 |
| `" SAVE10 "` | Quy tắc trim / có cho phép khoảng trắng đầu cuối |
| Chuỗi tiếng Việt hoặc emoji | Kiểm tra quy ước độ dài Unicode |
| Chuỗi có newline hoặc tab | Kiểm tra ký tự điều khiển |

Chú ý: `String.length()` trong Java đếm **UTF-16 code units**; đó không nhất thiết là số Unicode code points hoặc số ký tự người dùng nhìn thấy. Một ký tự có dấu có thể biểu diễn bằng một code point dựng sẵn hoặc chuỗi ký tự kết hợp. Nếu API cam kết số **byte UTF-8**, **code points** hoặc **grapheme clusters**, cách đo cần được ghi cụ thể và thử đúng biên.

Không nên tự trim/normalize input một cách âm thầm nếu consumer đang phụ thuộc vào cách xử lý hiện tại. Khi chuẩn hóa thay đổi nghĩa của trường, hãy ghi nó trong contract hoặc tài liệu API.

## 15. Mảng, object và giá trị false

Ba body sau là ba trạng thái khác nhau:

~~~json
{"items":[]}
~~~

~~~json
{"items":null}
~~~

~~~json
{}
~~~

Với API cần ít nhất một item, có thể quy định:

| Trạng thái | Kỳ vọng minh họa |
|---|---|
| `items` thiếu | `400 ITEMS_REQUIRED` |
| `items: null` | `400 ITEMS_NULL` |
| `items: []` | `400 ITEMS_EMPTY` |
| Một item | Thành công |
| Đúng giới hạn số item | Thành công |
| Vượt giới hạn một item | Lỗi phạm vi |

Tương tự, `metadata: {}` là object rỗng, khác `metadata: null`. Với response, `items: []` là cam kết khác với việc bỏ field `items`; consumer có thể lặp trên danh sách rỗng an toàn nhưng lỗi khi nhận null.

Đối với boolean:

~~~json
{"discountApplied":false}
~~~

`false` là một giá trị có nghĩa; consumer không được nhầm nó với field thiếu. Khi serialize/deserialize DTO, cần kiểm tra cách dùng kiểu primitive `boolean`, wrapper `Boolean`, default value và chính sách bỏ trường null.

## 16. Ý nghĩa đặc biệt của absent/null trong PATCH

Đối với `application/merge-patch+json` theo **RFC 7396**, trên tài nguyên dạng object, hai patch sau thường mang ý nghĩa khác nhau:

~~~json
{}
~~~

Không có key nào được yêu cầu thay đổi.

~~~json
{"nickname":null}
~~~

Yêu cầu **xóa thuộc tính `nickname`** khỏi object đích theo semantics của JSON Merge Patch.

Đừng áp đặt quy tắc này cho mọi HTTP PATCH. Với `application/json-patch+json` theo **RFC 6902**, request là danh sách thao tác `add`, `remove`, `replace`..., còn PATCH sử dụng `application/json` có thể được thiết kế với ngữ nghĩa riêng.

Nếu API dùng Merge Patch, **absence và null là một phần của giao thức cập nhật**: cần contract cho “không đổi”, “xóa” và “đặt giá trị”, không chỉ test request thành công thông thường.

## 17. Kiểm thử producer khi framework làm mất thông tin

Generated tests từ SCC cần được **chạy với producer thật**, bao gồm controller, validator và exception handler. Các tình huống đặc biệt như absent/null có thể cần integration test bổ sung để kiểm tra framework binding và response công khai.

Ví dụ `MockMvc` (giả định controller triển khai mã lỗi ở phần 3):

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class QuoteBoundaryTest {
    @Autowired MockMvc mvc;

    @Test
    void absentCouponIsAccepted() throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"sku":"SKU-123","quantity":1}
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.discountApplied").value(false));
    }

    @Test
    void explicitNullIsRejected() throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"sku":"SKU-123","quantity":1,"couponCode":null}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("COUPON_NULL"));
    }

    @Test
    void zeroQuantityIsRejected() throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"sku":"SKU-123","quantity":0}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("QUANTITY_OUT_OF_RANGE"));
    }
}
~~~

Đây là **test minh họa** cho producer có controller đã triển khai semantics đã chọn. Với dự án Java cũ chưa hỗ trợ text blocks, hãy dùng chuỗi Java thông thường.

Generated producer test đỏ là tín hiệu cần kiểm tra: contract có đúng cam kết không, controller có chạy đúng không, hoặc cách generated test nạp payload có đúng không. **Test xanh nhưng không được sinh ra hoặc không được chạy** không phải bằng chứng contract đạt.

## 18. Stub Runner: tránh nhầm tình huống thiếu, null và empty

Luồng kiểm chứng:

~~~mermaid
flowchart TD
    A["Groovy/YAML contract cho dữ liệu biên"] --> B["SCC sinh producer tests"]
    A --> C["SCC tạo stub mappings"]
    B --> D["Producer thực tế"]
    C --> E["Stub Runner trong test consumer"]
    D --> F{"Producer đáp ứng các case?"}
    E --> G{"Consumer gửi và xử lý đúng?"}
    F -- "Không" --> H["Chặn thay đổi và sửa"]
    G -- "Không" --> H
    F -- "Có" --> I["Tổng hợp cổng CI"]
    G -- "Có" --> I
~~~

Đối với mỗi case, consumer test nên dùng **HTTP client và JSON serializer thực**:

- Không gửi `couponCode` → nhận `200`.
- Gửi explicit `"couponCode":null` → nhận `400 COUPON_NULL`.
- Gửi `"couponCode":""` → nhận `400 COUPON_BLANK`.
- Gửi `quantity: 100` → nhận `200`.
- Gửi `quantity: 101` → nhận `400 QUANTITY_OUT_OF_RANGE`.

**Hai giới hạn quan trọng:**

1. Serializer có thể được cấu hình **không ghi field null** (ví dụ chính sách kiểu `NON_NULL`). Khi muốn test explicit null, phải xem **body gửi đi thực sự** có key đó hay không.
2. Các WireMock mappings cùng method/path có thể vô tình **chồng lấn** nếu matcher được sinh ra cho phép extra fields hoặc so khớp một phần. Hãy xem mapping trong JAR stub và chạy test âm tính cho từng tình huống.

Nếu stub mapping không thể biểu đạt điều kiện “field hoàn toàn không tồn tại” với cách sinh hiện có, cần bổ sung cơ chế request matching phù hợp hoặc integration test đối với producer; không thể coi những contract na ná nhau là đã kiểm chứng độc lập.

## 19. Response lỗi cũng là hợp đồng

Một consumer có thể dựa vào:

| Thành phần | Ví dụ | Điểm cần thống nhất |
|---|---|---|
| HTTP status | `400` | Dùng 400 hay 422 cho validation? |
| Mã lỗi | `QUANTITY_OUT_OF_RANGE` | Có ổn định qua version? |
| Field lỗi | `quantity` | Client hiển thị đúng trường nào? |
| Message | `quantity must be 1..100` | Có được đổi câu chữ/ngôn ngữ? |
| Danh sách lỗi | `errors: []` | Luôn tồn tại hay có thể bị bỏ? |

Một số hệ thống dùng **Problem Details** với media type `application/problem+json` theo **RFC 9457**. Khi đó contract có thể cam kết `type`, `title`, `status`, `detail` và trường mở rộng. Chuyển từ error body riêng sang Problem Details có thể là **breaking change** nếu consumer đang đọc schema cũ.

Lỗi parse JSON có thể xuất hiện **trước controller**. Nếu API yêu cầu mọi lỗi validation có schema nhất quán, cần kiểm tra cả exception handler để không vô tình trả response mặc định khác hợp đồng.

## 20. Áp dụng cho message contract

SCC cũng hỗ trợ hợp đồng message, ví dụ sự kiện:

~~~json
{
  "eventType": "QuoteCalculated",
  "quoteId": "Q-1001",
  "discountApplied": false,
  "couponCode": null,
  "totalVnd": 150000
}
~~~

Consumer đang xử lý phiên bản cũ có thể hiểu:

- `couponCode` **thiếu**: phiên bản producer chưa cung cấp thông tin mã giảm giá.
- `couponCode: null`: producer có field nhưng không áp dụng mã.
- `couponCode: ""`: dữ liệu không hợp lệ hoặc cách biểu diễn cũ.
- `discountApplied: false`: quyết định không áp dụng giảm giá, khác field vắng mặt.
- `totalVnd: 0`: có thể là báo giá miễn phí hợp lệ hoặc lỗi nghiệp vụ tùy domain.

Với thông điệp, còn phải kiểm tra schema/serializer, header, destination/topic, cách kích hoạt generated message tests và consumer handler thực. Fixture JSON hợp lệ chưa chứng minh broker và handler production hoạt động đúng.

## 21. Đưa ma trận dữ liệu biên vào CI

| Cổng | Bằng chứng cần có | Khi nào chặn |
|---|---|---|
| Contract parsing | Groovy/YAML hợp lệ và fixture được nạp | Contract không parse được hoặc không sinh test |
| Producer verification | Generated tests + validation tests với code ứng viên | Status/body/error sai với bất kỳ case quan trọng nào |
| Candidate stub | Artifact từ **đúng commit** với đủ mapping | Stub không có hoặc mapping sai/chồng lấn |
| Consumer verification | Client thực chạy với stub ứng viên | Gửi nhầm absent/null hoặc xử lý response sai |
| Release gate | Kết quả các consumer cần hỗ trợ | Có breaking change chưa có kế hoạch chuyển đổi |

Ví dụ lệnh chạy trong **dự án đã cấu hình SCC**:

~~~bash
# Producer: sinh và chạy contract tests theo Maven lifecycle.
./mvnw clean verify

# Consumer: chạy test sử dụng Stub Runner với đúng stub ứng viên.
./mvnw test
~~~

Với Gradle, dùng task tương ứng của plugin và cấu hình dự án; trên Windows dùng wrapper `mvnw.cmd` hoặc `gradlew.bat`. Luôn kiểm tra generated source, test report và stub artifact, không chỉ dựa vào exit code của lệnh build.

**Chốt version và commit của stub**. Nếu consumer test vẫn lấy stub của bản producer cũ, mọi case biên vừa bổ sung có thể chưa hề được kiểm tra.

## 22. Lỗi phổ biến khi kiểm thử dữ liệu biên

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| YAML `couponCode:` biến thành null | Không có giá trị sau dấu hai chấm | Dùng `couponCode: ''` cho empty string |
| Client muốn gửi null nhưng field biến mất | Serializer bỏ qua null | Xem raw JSON, cấu hình serializer/test |
| Stub trả nhầm response thành công cho null | Mapping từ case absent match quá rộng | Xem WireMock mappings, thêm test âm tính |
| `quantity: "1"` vẫn được nhận | Framework coercion string → integer | Quyết định có cho phép chuyển kiểu; bổ sung test |
| `@NotEmpty` không chặn `"   "` | Empty khác blank | Dùng `@NotBlank` theo yêu cầu |
| Quantity thiếu vượt qua `@Min(1)` | Giá trị null chưa bị chặn hoặc validation không chạy | Dùng `@NotNull`, kiểm tra thiết lập validation |
| `101` vẫn đạt matcher | `by_type` chỉ xác minh kiểu | Thêm contract biên hoặc kiểm tra phạm vi |
| Số quá lớn trả 500 | Parser/mapper exception chưa được xử lý | Bổ sung error handling và contract |
| Response `items: null` làm consumer lỗi | Consumer kỳ vọng mảng, không xử lý null | Chốt và kiểm thử schema response |
| Producer test xanh nhưng consumer cũ lỗi | Contract mới không còn bao phủ behavior cũ | Chạy consumer test với stub ứng viên, phối hợp migration |

## 23. Bài thực hành từng bước

**Phần A — Thiết kế dữ liệu biên:** với `POST /api/quotes`, lập bảng đầy đủ cho `couponCode` thiếu/null/empty/blank/hợp lệ và `quantity` thiếu/null/0/1/100/101/"1"/1.5. Nêu request, status, mã lỗi và lý do.

**Phần B — Viết hợp đồng:** viết contract Groovy hoặc YAML cho ít nhất sáu trường hợp: thiếu coupon hợp lệ; null bị từ chối; chuỗi rỗng bị từ chối; quantity 0 bị từ chối; 1 hợp lệ; 100 hợp lệ; 101 bị từ chối. Các case biên nên rõ ràng, không cần matcher phức tạp nếu giá trị mẫu đã thể hiện được hành vi.

**Phần C — Kiểm chứng producer:** chạy generated tests, kiểm tra assertion và bổ sung kiểm thử controller/binding khi thiếu/null có thể bị đồng nhất bởi DTO. Xem các lỗi parse và validation được ánh xạ thành HTTP response đúng contract hay chưa.

**Phần D — Kiểm chứng stub/consumer:** đóng gói stub ứng viên, xem mapping cùng URL, gửi request cho từng case và đảm bảo response đúng. Chạy consumer test bằng client thực, kiểm tra serializer có ghi explicit null hay không.

**Phần E — Thử breaking change:** producer muốn xem `couponCode:null` là hợp lệ như trường thiếu. Khi cập nhật code và contract, kiểm tra consumer đang dựa vào `COUPON_NULL` có bị ảnh hưởng không; đề xuất thứ tự triển khai và migration trước khi thay đổi hành vi.

**Bằng chứng nộp bài:** ma trận, các contract, test report producer, phiên bản/commit của stub, kết quả consumer test và phân tích một trường hợp lỗi.

## 24. Checklist trước khi hợp nhất

- [ ] Có phân biệt **trường thiếu, null, empty, blank** theo ngữ nghĩa API.
- [ ] `0`, `false`, `[]` và `{}` không bị coi tương đương absent.
- [ ] Đã kiểm tra min−1, min, min+1, max−1, max, max+1 với các giới hạn quan trọng.
- [ ] Đã chốt kiểu number/string/boolean và xử lý coercion.
- [ ] Đã xem xét overflow, precision tiền tệ và độ dài Unicode khi liên quan.
- [ ] Mọi case lỗi quan trọng có status và schema response nhất quán.
- [ ] Groovy/YAML DSL thể hiện đúng field vắng mặt, null hoặc chuỗi rỗng.
- [ ] Generated producer tests thực sự được sinh và chạy.
- [ ] Matcher không chỉ kiểm tra kiểu nếu cần ràng buộc giá trị.
- [ ] Stub mappings được xem xét để tránh trùng/nhận nhầm case.
- [ ] Consumer test dùng client/serializer thật và đúng stub ứng viên.
- [ ] CI lưu được thông tin contract, commit, artifact, kết quả các cổng.

## 25. Câu hỏi tự kiểm tra

**1. Trường thiếu có luôn giống explicit null không?**

Không. API có thể cho phép bỏ một trường tùy chọn nhưng từ chối explicit null. DTO Java đơn giản có thể làm mất khác biệt đó; cần cơ chế theo dõi field presence nếu hợp đồng yêu cầu.

**2. Tại sao `@NotEmpty` chưa đủ cho chuỗi toàn khoảng trắng?**

Vì chuỗi có ba dấu cách không rỗng về độ dài. Nếu nghiệp vụ cần nội dung không trắng, nên dùng kiểm tra blank phù hợp.

**3. Tại sao `by_type` không đủ để kiểm tra quantity 1..100?**

Vì `by_type` kiểm tra kiểu dữ liệu; 101 vẫn là số. Phải có ràng buộc phạm vi hoặc contract riêng cho giá trị biên.

**4. Nếu body mẫu không có key `couponCode`, stub có chắc không match request chứa key đó không?**

Chưa chắc; phụ thuộc matching và tùy chọn WireMock được SCC sinh. Hãy xem mapping thật và chạy case âm tính.

**5. Vì sao ý nghĩa `null` trong JSON Merge Patch cần được học riêng?**

Vì với `application/merge-patch+json`, null thường biểu thị xóa thuộc tính trong object, còn thiếu field có nghĩa không thay đổi field đó.

**6. Producer test xanh có đủ chứng minh consumer cũ vẫn tương thích không?**

Không. Producer và contract có thể cùng thay đổi. Phải chạy consumer test với **stub của chính producer ứng viên** để phát hiện client cũ không xử lý được dữ liệu biên hoặc schema mới.

## 26. Tài liệu tham khảo

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): hợp đồng HTTP/message, Groovy/YAML DSL, generated test và Stub Runner.
- [Spring Cloud Contract – Dynamic Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): matcher, JSONPath và dữ liệu động.
- [Spring Framework – Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): tích hợp validation.
- [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/): định nghĩa constraint và giới hạn.
- [RFC 7396 – JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396): ngữ nghĩa field thiếu/null trong Merge Patch.
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): định dạng phản hồi lỗi tiêu chuẩn.

---

**Điểm cần nhớ:** **Thiếu ≠ null ≠ rỗng**, và **đúng kiểu ≠ đúng giới hạn**. Dữ liệu biên cần được mô tả bằng những request/response có kỳ vọng rõ ràng, chạy qua generated producer tests và kiểm tra stub mappings thật. Consumer phải kiểm thử với **stub ứng viên** để CI phát hiện thay đổi API không tương thích trước khi phát hành.
