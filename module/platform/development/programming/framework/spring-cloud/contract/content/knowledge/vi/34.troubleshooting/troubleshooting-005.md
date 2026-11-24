# Sai content type, serialization hoặc dữ liệu body

## Mục tiêu bài học

Trong **Spring Cloud Contract**, producer và consumer thống nhất hành vi HTTP hoặc thông điệp bằng **Groovy/YAML DSL**. Contract Verifier dùng hợp đồng để sinh kiểm thử phía producer; các mappings được đóng gói vào stub artifact để consumer dùng **Stub Runner**. Một nhóm lỗi rất phổ biến trong quy trình này là **Content-Type không đúng, dữ liệu được serialize/deserialize khác kỳ vọng hoặc body thực tế không khớp hợp đồng**.

Các lỗi này thường trông giống nhau ở bề mặt: generated producer test FAIL, consumer test nhận HTTP 400/404/415/406, Jackson ném exception, WireMock không tìm thấy mapping, hoặc assertion báo khác biệt giữa hai JSON. Tuy nhiên, **nguyên nhân và cách sửa của mỗi trường hợp rất khác nhau**. Nếu vội sửa DSL hoặc nới matcher mà chưa xác định lớp lỗi, ta có thể làm CI xanh nhưng đánh mất bảo vệ tương thích API.

Bài **“Sai content type, serialization hoặc dữ liệu body”** thuộc chương **Chẩn đoán sự cố** giúp bạn:

1. Phân biệt **`Content-Type`** và **`Accept`**, request/response headers, lỗi content negotiation và lỗi body parsing.
2. Chẩn đoán lỗi HTTP 400, 404, 406, 415, 422, 500 theo **bằng chứng**, không đoán chỉ từ status.
3. Hiểu tác động của YAML/Groovy DSL, HTTP message converters, Jackson, JSON number/null/array/string và charset.
4. Phân biệt lỗi trong **generated producer tests**, **stub mappings/WireMock** và **consumer deserialization**.
5. Xây quy trình so sánh **request thực**, **contract**, **mapping**, **response thực**, logs và test reports.
6. Rà soát message contracts và định dạng payload trong broker/binder.
7. Sửa nguyên nhân gốc, giữ matcher đủ chặt và bổ sung test ngăn hồi quy.

## 1. Tình huống mở đầu: cùng một API, ba lỗi khác nhau

Giả sử Order Service có endpoint:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"customerId":"CUS-1001","amount":125000}
~~~

Kỳ vọng response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"id":"ORD-1001","status":"CREATED"}
~~~

Một số tình huống:

- Consumer gửi `Content-Type: text/plain` nhưng body vẫn trông như JSON: producer có thể trả **415 Unsupported Media Type**.
- Consumer gửi `Content-Type: application/json` nhưng body là `"{\"customerId\":\"CUS-1001\"}"` — một **JSON string chứa JSON text** thay vì JSON object: producer có thể trả **400 Bad Request** vì DTO mong đợi object.
- Consumer gửi request đúng nhưng Stub Runner trả **404**: có thể do WireMock **không tìm thấy mapping** vì URL, header hoặc body không match; điều này không giống 404 nghiệp vụ `ORDER_NOT_FOUND`.
- Producer trả `Content-Type: application/json` nhưng body thực lại là chuỗi không phải JSON: generated test hoặc consumer có thể lỗi **JSON parsing** dù status 201 đúng.

Vì vậy, bước đầu tiên là **xác định giao thức đã nhận được thực sự là gì**, thay vì chỉ nhìn một dòng `AssertionError`.

## 2. Bốn lớp cần tách khi chẩn đoán

~~~mermaid
flowchart TD
    A["Contract Groovy/YAML"] --> B["Generated producer test"]
    B --> C["Producer HTTP/message implementation"]
    A --> D["Converted stub mapping"]
    D --> E["WireMock / Stub Runner"]
    F["Consumer request/client"] --> E
    E --> G["Stub response"]
    G --> H["Consumer deserializer + assertions"]
    C --> I["Producer response + generated assertions"]
    I --> J{"Phát hiện sai ở đâu?"}
    H --> J
~~~

| Lớp | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| **Contract source** | DSL yêu cầu method, headers, body, types và response nào? | Groovy/YAML tại đúng revision |
| **Producer verification** | Generated test gửi request gì và producer trả gì? | Generated source, producer logs, test reports |
| **Stub runtime** | Mapping được sinh có match request của consumer không? | Stub JAR, WireMock mappings và request journal |
| **Consumer runtime** | Client gửi/nhận bytes, headers, deserialize và xử lý ra sao? | HTTP client logs, exception, assertions |

Không được kết luận “Contract Verifier sai” chỉ vì **consumer test lỗi**. Có thể producer tests PASS, mappings đúng, nhưng consumer gửi `text/plain` hoặc chọn sai stub artifact.

Ngược lại, một stub trả response mẫu chính xác không chứng minh **producer implementation** thực sự serialize theo contract. Cần kiểm tra producer generated tests.

## 3. `Content-Type` khác `Accept` như thế nào?

Đây là nguyên tắc cơ bản nhất:

- **`Content-Type`** mô tả **media type của phần body đang gửi**.
- **`Accept`** mô tả **những media types mà bên gửi request muốn nhận trong response**.

Ví dụ:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"customerId":"CUS-1001","amount":125000}
~~~

`Content-Type: application/json` nói body request là JSON. `Accept: application/json` nói consumer muốn nhận JSON response.

Response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"id":"ORD-1001","status":"CREATED"}
~~~

Response `Content-Type` do producer chọn và công bố. Không nên nhầm nó với request `Accept`.

### Bảng tình huống

| Request Content-Type | Request Accept | Điều cần kiểm tra |
| --- | --- | --- |
| `application/json` | `application/json` | JSON request và JSON response như hợp đồng |
| `text/plain` | `application/json` | Producer có nhận plain-text request không? Có thể 415 |
| `application/json` | `application/xml` | Producer có thể tạo XML không? Có thể 406 nếu không |
| Không gửi (request không có body) | `application/json` | Có thực sự cần request body không? |
| `application/json;charset=UTF-8` | `application/json` | Media type parameters và charset có được xử lý đúng? |
| `application/vnd.example.order+json` | `application/json` | Producer/message converter có hỗ trợ vendor media type không? |

**HTTP header names không phân biệt chữ hoa/thường**; tuy nhiên giá trị media type phải được phân tích theo cú pháp media type, không so sánh chuỗi tùy tiện. Một matcher exact string trong test có thể quá chặt khi chỉ khác cách thêm tham số `charset`.

### Lỗi thường gặp khi sửa

Không nên sửa một response contract từ `application/json` sang `text/plain` chỉ vì producer đang trả sai header. Cần xác định **giao diện đã thỏa thuận** là gì và sửa producer/serializer nếu hợp đồng đúng.

## 4. Đọc HTTP status có định hướng, không đoán nguyên nhân

| Status hoặc triệu chứng | Ý nghĩa thường gặp | Cần điều tra tiếp |
| --- | --- | --- |
| **400 Bad Request** | Body không parse được, validation thất bại hoặc request không hợp lệ | Raw bytes, JSON syntax, DTO binding, validation/error body |
| **404 Not Found** | Route không có, resource không có hoặc WireMock không match | Producer route vs stub mapping vs business 404 |
| **406 Not Acceptable** | Không thể tạo response hợp với `Accept`/negotiation | Response converters, `produces`, client Accept |
| **415 Unsupported Media Type** | Server không hỗ trợ request `Content-Type` | `consumes`, request converter, actual media type |
| **422 Unprocessable Content** | Ứng dụng có thể chọn status cho lỗi semantics | Quy ước API riêng, validation và error schema |
| **500 Internal Server Error** | Exception ở producer hoặc lỗi xử lý | Stack trace, serializer, mapper, exception handler |
| **200/201 nhưng test FAIL** | Body/header sai hoặc matcher quá chặt | Actual response, JSONPath, types, property names |
| **Stub Runner trả 404** | Mapping không match hoặc scenario/resource được định nghĩa trả 404 | Request journal và mapping, phân biệt unmatched |
| **Consumer parse exception** | Body không tương thích DTO/schema của consumer | Raw response + Content-Type + DTO/ObjectMapper settings |

Các status là dấu hiệu, **không phải quy luật một–một**. Ví dụ producer có thể map một lỗi deserialize thành 422 thay vì 400. Phải xem error handling của chính ứng dụng và contract.

## 5. Một contract YAML HTTP nhất quán về headers và body

Ví dụ **hợp đồng HTTP** cho thao tác tạo đơn:

~~~yaml
description: "Tạo đơn hàng từ JSON request"
name: create_order
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
    Accept: application/json
  body:
    customerId: CUS-1001
    amount: 125000
response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: CREATED
~~~

Trong ví dụ:

- `request.headers.Content-Type` yêu cầu request có body JSON.
- `request.headers.Accept` mô tả media type response được client yêu cầu.
- `request.body` là **JSON object** gồm `customerId` dạng string và `amount` dạng number.
- `response.headers.Content-Type` công bố response JSON.
- `response.body` là object gồm hai field.

Đây là **mẫu cú pháp cho một tập tính năng SCC phổ biến**; cách thiết lập matcher/optional headers hoặc serialization cho một số phiên bản cần kiểm tra plugin release đang dùng.

### Đừng đặt mọi dữ liệu vào string

Sai hướng nếu muốn JSON object:

~~~yaml
request:
  body: '{"customerId":"CUS-1001","amount":125000}'
~~~

Tùy vị trí và cách parser nhận DSL, đây có thể được hiểu là **một chuỗi chứa JSON text**, không giống YAML mapping ở ví dụ chuẩn. Với một số cấu hình, plugin có khả năng xử lý raw JSON string; điểm quan trọng là phải **xác nhận output được sinh**, không suy luận từ việc nhìn giống JSON.

Để tránh ambiguity khi người mới học, sử dụng **YAML mapping/sequence** cho JSON object/array, sau đó kiểm tra generated test và stub mapping.

## 6. Serialization khác deserialization như thế nào?

**Serialization** là chuyển object/domain data thành bytes/string để truyền. **Deserialization** là đọc JSON/XML/text từ request/response thành object phù hợp.

~~~mermaid
flowchart LR
    A["Consumer DTO"] --> B["Serialize request JSON"]
    B --> C["HTTP bytes + Content-Type"]
    C --> D["Producer deserialize DTO"]
    D --> E["Producer business logic"]
    E --> F["Serialize response JSON"]
    F --> G["HTTP response bytes + Content-Type"]
    G --> H["Consumer deserialize DTO"]
    H --> I["Consumer business assertions"]
~~~

Lỗi có thể xuất hiện tại **bất kỳ mũi tên nào**. Ví dụ:

- Consumer `StringHttpMessageConverter` tạo plain text thay vì Jackson serialize DTO.
- Producer `@RequestBody` không thể deserialize string thành một Java bean.
- Producer DTO getter trả tên property khác contract.
- Jackson đang dùng snake_case, còn contract đòi camelCase.
- Consumer enum không chấp nhận giá trị mới.

**Cùng status 200 không đủ**: nếu body không parse được thì consumer vẫn thất bại. Trong contract tests, việc so khớp data types và headers phải phản ánh consumer thật sự sử dụng.

## 7. Lỗi “JSON object bị encode thành JSON string”

Hai payload nhìn na ná nhưng khác hoàn toàn:

**JSON object:**

~~~json
{
  "customerId": "CUS-1001",
  "amount": 125000
}
~~~

**JSON string có nội dung là JSON text:**

~~~json
"{\"customerId\":\"CUS-1001\",\"amount\":125000}"
~~~

Trong payload thứ hai, root là **string**, không phải object. Nếu producer nhận:

~~~java
@PostMapping(
    path = "/api/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public ResponseEntity<OrderCreated> create(
        @RequestBody CreateOrderRequest request) {
    // ...
}
~~~

thì deserialization có thể thất bại, vì `CreateOrderRequest` mong đợi JSON object.

### Nguyên nhân phổ biến ở client

Một client tự gọi `objectMapper.writeValueAsString(data)`, sau đó lại đưa chuỗi kết quả vào một API vốn **serialize lần nữa**, tạo double encoding.

**Cách sửa:** chọn một ranh giới serialization rõ ràng:

- Hoặc HTTP client nhận **DTO object** và tự serialize JSON.
- Hoặc HTTP client nhận **raw JSON bytes/string** theo API được định nghĩa và không encode lần nữa.

Không dùng cả hai một cách vô thức.

### Cần kiểm tra bytes thật

Đừng chỉ xem log `CreateOrderRequest(customerId=...)`. Log object Java chưa chứng minh client đã gửi JSON object. Hãy xem **wire-level request body** và `Content-Type` theo logging an toàn/đã ẩn secrets.

## 8. JSON number, string, boolean và null không tương đương

YAML mapping có thể phân biệt:

~~~yaml
body:
  amount: 125000
  active: true
  status: PAID
  discount: null
~~~

Một response JSON tương ứng:

~~~json
{
  "amount": 125000,
  "active": true,
  "status": "PAID",
  "discount": null
}
~~~

Sai khác rõ ràng:

~~~json
{
  "amount": "125000",
  "active": "true",
  "status": "PAID",
  "discount": "null"
}
~~~

Ở JSON thứ hai, `amount`, `active` và `discount` đều là strings. Jackson có thể **coerce** một số giá trị theo cấu hình, nhưng không nên dựa vào coercion để che một breaking change về schema.

| Trường | JSON mong đợi | Dữ liệu sai thường gặp |
| --- | --- | --- |
| `amount` | number | string `"125000"` |
| `active` | boolean | string `"true"` |
| `discount` | JSON null | string `"null"` |
| `items` | array | object hoặc string chứa JSON |
| `customer` | object | array hoặc escaped JSON string |

### YAML có những bẫy khi đọc kiểu dữ liệu

Một số giá trị trong YAML có cú pháp đặc biệt theo parser/schema. Để kiểm soát rõ:

- Dùng quotes cho **IDs** có thể trông như number, ví dụ `"00123"`.
- Dùng quotes cho giá trị có dấu `:` hoặc ký tự đặc biệt dễ bị hiểu là cú pháp.
- Dùng số không quote khi muốn JSON number.
- Dùng `true`/`false` không quote khi muốn boolean.
- Dùng `null` không quote khi muốn null.
- Đối chiếu parser version/YAML schema khi có giá trị mang hình thức đặc biệt (ngày, số có tiền tố, boolean-like).

**Quy tắc:** bản mô tả trong DSL phải tạo ra **kiểu dữ liệu consumer thật sự cần**, không chỉ trông đẹp trên file.

## 9. Null, missing field và empty value khác nhau

Một consumer có thể phân biệt:

~~~json
{"middleName":null}
~~~

và:

~~~json
{}
~~~

và:

~~~json
{"middleName":""}
~~~

Ba response thể hiện ba tình trạng:

1. Field tồn tại với giá trị **null**.
2. Field **không tồn tại**.
3. Field tồn tại với chuỗi **rỗng**.

Với JSON arrays, cũng cần phân biệt:

~~~json
{"items":[]}
~~~

với:

~~~json
{"items":null}
~~~

và:

~~~json
{}
~~~

Trong Java, cấu hình Jackson như `@JsonInclude(Include.NON_NULL)` hoặc `NON_EMPTY` có thể làm field biến mất khỏi output. Nếu contract hoặc consumer yêu cầu field tồn tại, phải review annotation, serialization policy và generated assertions.

**Không tự thay null bằng missing** chỉ để test PASS; đó có thể là thay đổi semantics mà consumer dùng để phân biệt “chưa biết” và “không áp dụng”.

## 10. JSON object order, array order và whitespace

Với JSON objects, thứ tự các properties thường **không mang ý nghĩa dữ liệu JSON**, trong khi thứ tự elements của **array** có ý nghĩa. Ví dụ:

~~~json
{"id":"ORD-1001","status":"PAID"}
~~~

và:

~~~json
{"status":"PAID","id":"ORD-1001"}
~~~

mang cùng cấu trúc object về hai trường, mặc dù raw strings khác nhau.

Nhưng hai arrays:

~~~json
{"items":["A","B"]}
~~~

và:

~~~json
{"items":["B","A"]}
~~~

không đương nhiên tương đương nếu API cam kết thứ tự.

### Chọn cách so sánh đúng

- Khi kiểm tra **semantic JSON**, ưu tiên parse JSON/JSONPath/structural assertions.
- Khi API cam kết thứ tự array, giữ assertion về thứ tự.
- Nếu API không cam kết thứ tự array, cần matcher/assertion phù hợp để không tạo flaky tests.
- Chỉ so **raw bytes** nếu chính hợp đồng yêu cầu body ở dạng bytes/text chính xác (ví dụ signature canonical JSON hoặc payload binary).
- Whitespace, indentation và property order không nên trở thành breaking change giả khi không thuộc giao diện.

Một test `assertEquals(expectedJsonString, actualJsonString)` có thể FAIL chỉ vì format. Đừng “sửa” bằng cách xóa tất cả matcher; hãy so sánh theo ngữ nghĩa phù hợp.

## 11. Content-Type có tham số charset và vendor media type

Một số HTTP responses có:

~~~http
Content-Type: application/json;charset=UTF-8
~~~

thay vì:

~~~http
Content-Type: application/json
~~~

Cả hai có media type `application/json`, nhưng giá trị header nguyên chuỗi không giống nhau. Một test dùng exact string có thể FAIL dù client vẫn parse JSON được.

**Cách điều tra:**

1. Xác định contract có thực sự cam kết **exact header string** hay chỉ media type.
2. Đọc raw response headers.
3. Kiểm tra producer response converter và `produces`.
4. Dùng matcher/test API phân tích media type phù hợp nếu consumer chỉ cần JSON.
5. Nếu cần charset cụ thể, viết tiêu chí rõ và test nó.

Với vendor type:

~~~http
Content-Type: application/vnd.example.order+json
~~~

đừng tự coi mọi framework đều hỗ trợ cách parse như `application/json`. Nhiều converter có hỗ trợ hậu tố `+json` nhưng hành vi phụ thuộc client/server library và cấu hình. Hãy kiểm chứng consumer thực tế.

### Chú ý mã hóa ký tự

Body có tiếng Việt:

~~~json
{"message":"Đơn hàng đã được tạo"}
~~~

Nếu bytes UTF-8 bị đọc bằng encoding khác, output có thể thành ký tự lỗi. Kiểm tra:

- Bytes của request/response.
- Thông tin charset/media type.
- HTTP client/server encoding.
- Source files và resource encoding trong build.
- Có BOM hoặc việc encode/decode hai lần không.

Không sửa hợp đồng thành chuỗi bị lỗi dấu chỉ để CI xanh.

## 12. Spring MVC và HTTP message converters

Trong Spring MVC, controller có thể khai báo:

~~~java
@PostMapping(
    path = "/api/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ResponseEntity<OrderCreated> create(
        @RequestBody CreateOrderRequest body) {

    OrderCreated created = service.create(body);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

Ở mức khái niệm:

- `consumes` tác động đến request media types endpoint chấp nhận.
- `produces` tác động đến response media type endpoint có thể tạo.
- `@RequestBody` cần một `HttpMessageConverter` phù hợp để deserialize body vào DTO.
- Jackson JSON converter thường được Spring Boot auto-configure khi dependencies thích hợp.
- Exception handler có thể chuyển lỗi parse/validation thành error response theo quy ước.

### Một lỗi thực tế

Contract gửi:

~~~http
Content-Type: application/json
~~~

nhưng test client hoặc application context thiếu converter phù hợp. Generated test có thể FAIL khác với chạy ứng dụng thật do dependencies/config khác nhau.

**Điều tra:** effective Spring test context, MVC/WebFlux stack, converter registration, DTO getters/setters/constructors, Jackson modules và test mode.

Không giả định “cài thêm Jackson dependency” luôn là cách sửa; cũng có trường hợp producer response đã dùng sai media type hoặc hợp đồng mô tả sai định dạng.

## 13. Serialization DTO: field name, enums, dates và BigDecimal

Một DTO Java có thể dùng:

~~~java
public record OrderResponse(
    String id,
    String paymentStatus,
    BigDecimal amount
) {}
~~~

Trong JSON mặc định, field thường thành `paymentStatus`. Nhưng cấu hình Jackson hoặc annotation có thể đổi:

~~~java
public record OrderResponse(
    String id,
    @JsonProperty("payment_status") String paymentStatus,
    BigDecimal amount
) {}
~~~

Khi đó response có thể chứa `payment_status` thay vì `paymentStatus`. Nếu contract yêu cầu camelCase, generated producer test có thể FAIL.

### Những nguồn khác biệt cần review

| Nguồn khác biệt | Ví dụ | Tác động |
| --- | --- | --- |
| `@JsonProperty` | `payment_status` | Tên field thay đổi |
| Global naming strategy | snake_case vs camelCase | Nhiều fields đồng loạt đổi |
| `@JsonIgnore` | Field bị loại | Consumer không thấy dữ liệu |
| `@JsonInclude` | Null/empty bị bỏ | Missing khác null |
| Enum representation | `"PAID"` vs `"paid"` | Consumer enum parsing fail |
| Date formatting | ISO string vs numeric timestamp | Type/format compatibility |
| Timezone | UTC vs local timezone | Sai semantics thời gian |
| Decimal representation | number vs string, scale | Parser/tính toán khác |
| Default values | Chèn missing field mặc định | Che sự thay đổi contract |
| Custom serializer | Output không theo DTO fields thông thường | Có thể phá schema ngoài dự kiến |

Đối với dữ liệu tiền tệ, ưu tiên kiểm tra **kiểu dữ liệu, đơn vị, precision/rounding và giá trị** theo thỏa thuận. Không dùng việc hiển thị `125000.00` khác `125000` như bằng chứng breaking nếu API chỉ cam kết giá trị số; ngược lại, nếu scale là một phần của format được công bố, cần kiểm tra đúng.

## 14. Contract Groovy DSL: body là object hay chuỗi?

Ví dụ HTTP contract Groovy:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Tạo đơn với JSON body"

    request {
        method POST()
        url "/api/orders"
        headers {
            contentType(applicationJson())
            accept(applicationJson())
        }
        body(
            customerId: "CUS-1001",
            amount: 125000
        )
    }

    response {
        status CREATED()
        headers {
            contentType(applicationJson())
        }
        body(
            id: "ORD-1001",
            status: "CREATED"
        )
    }
}
~~~

Trong Groovy DSL, body dạng map giúp nêu cấu trúc JSON. Tuy nhiên:

- Không nhầm `body(...)` với Java method serialize DTO.
- Không thêm dấu quote quanh số nếu contract cần JSON number.
- Không dùng string interpolation không chủ đích khiến Groovy thay giá trị ngay khi plugin parse DSL.
- Không dùng mã Groovy tùy ý để tự tạo dữ liệu production hoặc gọi external service trong quá trình build.
- Khi dùng `bodyFromFile(...)`, cần kiểm tra file encoding, location và content type của response/request theo phiên bản plugin.

**Groovy DSL và YAML DSL không bảo đảm serialize giống nhau nếu bạn vô tình mô tả hai loại dữ liệu khác nhau**. Hãy so sánh kết quả mapping/test đã sinh, không chỉ so ngoại hình file nguồn.

## 15. Request matcher và response matcher phải được hiểu riêng

Spring Cloud Contract tạo hai nhánh bằng chứng:

- **Producer generated test:** gửi request cho producer rồi kiểm tra response theo contract.
- **Consumer stub mapping:** WireMock tìm request khớp rule rồi trả stub response.

Một request matcher có thể yêu cầu:

- HTTP method đúng.
- URL path/query đúng.
- Header `Content-Type` hoặc `Accept` đúng.
- Body JSON có field/giá trị phù hợp.
- Cookies hoặc các điều kiện khác được khai báo.

Nếu consumer gửi **cùng JSON semantic** nhưng một matcher dùng **raw body equality**, khác whitespace hoặc thứ tự key có thể khiến WireMock không match. Với JSON, ưu tiên cơ chế JSON structural matching nếu phù hợp.

### Dấu hiệu request không match không phải response sai

Nếu WireMock không tìm được mapping, nó có thể trả một 404 unmatched. Khi đó chưa cần sửa response body contract. Phải điều tra **request matching** trước.

Nếu request match đúng và WireMock trả response khác kỳ vọng, kiểm tra **artifact/version của mapping**, response files, headers và scenario state.

## 16. 404 từ WireMock khác 404 nghiệp vụ

Giả sử producer có business contract:

~~~yaml
description: "Không tìm thấy đơn hàng"
name: get_missing_order
request:
  method: GET
  url: /api/orders/ORD-NOT-FOUND
response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: ORDER_NOT_FOUND
    message: "Đơn hàng không tồn tại"
~~~

Một **business 404** phải trả error code/body đã thỏa thuận. Nhưng nếu consumer gọi sai `/api/order/ORD-NOT-FOUND` (thiếu `s`), WireMock có thể trả 404 **unmatched** không cùng schema.

Điều tra:

1. Đọc request URL/method thực từ consumer.
2. Xem stub mapping nào được nạp.
3. Nếu WireMock admin API/request journal được bật và được phép truy cập trong test, kiểm tra **unmatched requests**.
4. So sánh headers và body matchers.
5. Kiểm tra Stub Runner đang chạy đúng artifact version.

**Không kết luận contract 404 PASS** chỉ vì consumer đã nhận một response có status 404. Phải xác minh **body và mapping đã khớp**.

## 17. Debug request bằng cURL một cách tái lập

Một request mẫu:

~~~bash
curl --verbose \
  --request POST \
  "http://localhost:8090/api/orders" \
  --header "Content-Type: application/json" \
  --header "Accept: application/json" \
  --data-binary '{"customerId":"CUS-1001","amount":125000}'
~~~

Quan sát:

- Đã kết nối đúng host/port chưa?
- Request method/path có đúng không?
- Đã gửi `Content-Type` và `Accept` nào?
- Body root là object hay string?
- Response status và `Content-Type` là gì?
- Body trả về có parse được JSON không?

**Dùng dữ liệu tổng hợp**; không thêm authorization token thật vào terminal history hoặc log. Với dữ liệu chứa ký tự phức tạp, có thể đặt body vào file test và dùng `--data-binary @request.json` để tránh shell quoting làm sai bytes.

### Một bài test đối chứng có kiểm soát

Gửi hai request chỉ khác một yếu tố:

**A — request đúng:**

~~~http
Content-Type: application/json

{"customerId":"CUS-1001","amount":125000}
~~~

**B — request sai media type:**

~~~http
Content-Type: text/plain

{"customerId":"CUS-1001","amount":125000}
~~~

Nếu A match stub/producer còn B không, content type là một biến quan trọng. Nhưng nếu cả hai không match, cần kiểm tra URL, body matcher và artifact chứ không đổ lỗi ngay cho header.

**Thay đổi từng biến** giúp phân biệt lỗi hơn là sửa đồng thời path, header, body và DTO rồi không biết điều gì đã làm test PASS.

## 18. Kiểm tra raw body và parsed JSON

Nhiều lỗi chỉ hiện rõ khi xem cả **representation gốc** lẫn **parsed structure**.

Ví dụ body gốc:

~~~text
"{\"id\":\"ORD-1001\",\"status\":\"PAID\"}"
~~~

Một người đọc lướt thấy `id` và `status` tưởng đó là JSON object. Nhưng JSON parser cho biết root type là string.

Một số kiểm tra hữu ích:

~~~bash
# Với một file response mẫu không chứa secret:
python -m json.tool response.json
~~~

Lệnh trên **chỉ minh họa cách kiểm tra JSON syntax**, không phải yêu cầu người học chạy Python trong quy trình hiện tại. Nó có thể chấp nhận JSON string hợp lệ; vì vậy cần kiểm tra root type, không chỉ parse success.

Nếu dùng một công cụ JSON viewer, hãy xác định:

- Root là object, array, string, number, boolean hay null.
- Tên field có đúng case không.
- Trường null/omitted có khác contract không.
- Arrays có đúng thứ tự hay không.
- Numeric values có bị convert thành strings không.

**Không đưa response thực có PII lên dịch vụ JSON formatter công khai** chỉ để debug. Ưu tiên tool chạy local/trong môi trường được phép.

## 19. Generated producer test FAIL: đọc lỗi theo đúng điểm thất bại

Một generated test có thể fail ở nhiều thời điểm:

~~~mermaid
flowchart TD
    A["Generated producer test"] --> B{"HTTP/message test client setup OK?"}
    B -->|Không| X["Base class / test mode / context"]
    B -->|Có| C{"Request được producer nhận?"}
    C -->|Không| Y["Method/path/Content-Type/Accept"]
    C -->|Có| D{"Body deserialize thành công?"}
    D -->|Không| Z["JSON syntax/types/DTO/converter"]
    D -->|Có| E{"Business logic hoàn thành?"}
    E -->|Không| W["Fixture/validation/dependency"]
    E -->|Có| F{"Response được serialize đúng?"}
    F -->|Không| V["Jackson/headers/DTO/date/enum"]
    F -->|Có| G{"Assertions khớp contract?"}
    G -->|Không| U["Contract semantics/matcher"]
    G -->|Có| H["Producer contract test PASS"]
~~~

### Bước điều tra thực tế

1. Đọc **failure đầu tiên** trong test report, không chỉ summary cuối.
2. Xác định request đã tới producer hay chưa.
3. Ghi lại actual status, response headers và body **sau khi redact dữ liệu nhạy cảm**.
4. Xác định error là parse request, response serialization hay matcher.
5. Kiểm tra test base class, Spring MVC/WebFlux test mode và dependencies.
6. So sánh contract với behavior công khai muốn giữ.
7. Sửa producer hoặc contract theo thay đổi đã được thỏa thuận, rồi chạy lại tests.

**Không sửa contract theo output hiện tại một cách máy móc.** Nếu output producer phá consumer, contract FAIL là tín hiệu cần bảo vệ.

## 20. MockMvc, WebTestClient và HTTP thật có thể cho kết quả khác

Spring Cloud Contract cho phép nhiều chế độ test HTTP tùy producer stack và plugin configuration. Các lớp test có thể gồm:

- **MockMvc/RestAssuredMockMvc** với Spring MVC.
- **WebTestClient/RestAssuredWebTestClient** với WebFlux.
- **Live HTTP server/RestAssured** khi dùng môi trường có cổng thật.

Các cơ chế có thể khác nhau ở:

- Message converter/codecs được cấu hình.
- Filter/security chain được kích hoạt.
- Handler routing và exception handling.
- Content negotiation.
- Encoding.
- Serialization của streaming responses.

Ví dụ **WebFlux** có thể dùng codec khác hoặc streaming `Flux`. Một test giả lập một object JSON tĩnh không chứng minh server thực xử lý đúng SSE/NDJSON/chunked streaming trong mọi tình huống.

### Đừng trộn test mode

Nếu generated test dùng RestAssuredMockMvc nhưng base test lại chỉ cấu hình WebTestClient, test có thể fail trước cả bước parse body. Đây là **lỗi wiring test**, không phải lỗi response body của producer.

Đọc generated source, plugin test mode và base class để xác nhận client được setup đúng.

## 21. Khi dùng bodyFromFile hoặc response file

Một số hợp đồng chứa JSON dài có thể tách body ra file:

~~~text
src/test/resources/contracts/
  orders/
    get_paid_order.groovy
    get_paid_order_response.json
~~~

Nội dung file JSON:

~~~json
{
  "id": "ORD-1001",
  "status": "PAID",
  "items": [
    {"sku": "SKU-1", "quantity": 2}
  ]
}
~~~

Nếu sử dụng DSL helper như `bodyFromFile(...)` theo version hỗ trợ, cần kiểm tra:

1. File path có được resolver tìm thấy theo **thư mục contract** hoặc cấu hình tương ứng không?
2. File được đóng gói cùng stub artifact chưa?
3. Content-Type có là `application/json` không?
4. Encoding có đúng UTF-8 không?
5. File chứa JSON object hay escaped JSON string?
6. Có line endings/BOM làm parser/client thay đổi behavior không?
7. Có chứa dữ liệu production nhạy cảm không?

Với binary body, không nên ngụy trang bytes thành JSON string mà không mô tả encoding. Cần dùng cơ chế file/binary stub đúng theo loại payload và version công cụ.

## 22. Stub Runner chọn sai artifact cũng có thể giống lỗi body

Giả sử producer mới `2.5.0` trả:

~~~json
{
  "id": "ORD-1001",
  "paymentStatus": "PAID"
}
~~~

nhưng consumer vẫn dùng:

~~~text
com.example.orders:order-service:2.4.0:stubs
~~~

Stub cũ có thể trả:

~~~json
{
  "id": "ORD-1001",
  "status": "PAID"
}
~~~

Consumer test có thể FAIL vì body khác kỳ vọng hoặc thậm chí PASS vì nó chỉ biết schema cũ. **Đó không phải bằng chứng về producer 2.5.0**.

Điều tra:

- Stub Runner ID: `groupId:artifactId:version:classifier[:port]`.
- Maven local/remote repository và cache.
- Stub JAR thực sự được tải.
- Mappings và response files bên trong JAR.
- Checksum artifact/producer verification build khi cần.

**Không vội đổi serializer của consumer** nếu sự khác biệt body đến từ một artifact cũ được dùng sai.

## 23. JSONPath matchers: tránh cả quá lỏng lẫn quá chặt

Matcher theo JSONPath hữu ích khi response có giá trị động:

- `$.id` cần đúng format.
- `$.status` cần enum `PAID`.
- `$.items[0].sku` cần một SKU cụ thể.
- `$.amount` cần kiểu number.

Nhưng cũng có rủi ro:

| Matcher | Rủi ro |
| --- | --- |
| `byType` cho mọi field | Có thể không phát hiện enum semantics đổi |
| Regex `.*` | Chấp nhận cả chuỗi rỗng/sai format |
| Chỉ kiểm tra body chứa `"PAID"` | Có thể match debug text thay vì status |
| JSONPath sai nhưng không được kiểm tra | Assertion không bảo vệ trường muốn kiểm |
| Exact equality với timestamp động | Flaky nếu thời gian không được cố định |
| So raw JSON string | Fail do whitespace/property order không thuộc contract |
| Bỏ matcher khi test FAIL | Làm contract yếu, che regression |

**Nguyên tắc:** giữ chặt những giá trị/semantics mà consumer thật sự phụ thuộc; dùng matcher linh hoạt cho giá trị động không cần cố định, với constraint rõ ràng.

### Kiểm tra negative case

Tạo một tình huống kiểm soát trong test:

~~~json
{
  "id": "INVALID",
  "status": "PENDING"
}
~~~

Nếu generated producer test vẫn PASS dù contract yêu cầu ID format và `status = PAID`, matcher có thể sai hoặc test không thật sự chạy. Hãy kiểm tra generated source, test reports và matcher configuration.

## 24. Phân biệt request body matcher và response body matcher

Trong CDC, cần phân biệt hai việc:

1. **Request matching của stub:** Consumer request có match contract để WireMock trả response?
2. **Response assertion của producer test:** Producer implementation có trả response theo contract?

Ví dụ consumer gửi:

~~~json
{"customerId":"CUS-1001","amount":"125000"}
~~~

trong khi contract request yêu cầu:

~~~json
{"customerId":"CUS-1001","amount":125000}
~~~

Nếu request body matching kiểm tra đúng JSON type, Stub Runner có thể không match và trả unmatched 404. Lỗi nằm ở **consumer request serialization**.

Nếu producer generated test gửi request hợp lệ nhưng producer trả `amount` dưới dạng string ở response, lỗi nằm ở **producer response serialization**.

**Đừng sửa response matcher để chữa một request không match**. Tách request side và response side trước.

## 25. Message contracts: Content-Type cũng ảnh hưởng payload

Spring Cloud Contract hỗ trợ message-based contracts, ví dụ:

~~~yaml
description: "Order đã thanh toán phát ORDER_PAID"
label: order_paid
input:
  triggeredBy: markTestOrderAsPaid()
outputMessage:
  sentTo: orders.events
  headers:
    contentType: application/json
  body:
    eventType: ORDER_PAID
    orderId: ORD-1001
    amount: 125000
~~~

Trong ví dụ:

- `triggeredBy` là phương thức kích hoạt producer trong test environment.
- `outputMessage.sentTo` mô tả logical destination.
- Message `headers.contentType` là **header message**, không tự đồng nghĩa với HTTP `Content-Type`.
- Message `body` có thể được serializer/binder chuyển thành bytes, String hoặc Map tùy adapter.

### Một số sai khác thường gặp

| Sai khác | Triệu chứng |
| --- | --- |
| Header nói JSON nhưng payload là Java `toString()` | Consumer không parse được |
| Kafka serializer tạo bytes khác JSON contract | Assertion/deserializer fail |
| Event body `amount` string thay vì number | Consumer schema validation fail |
| `contentType` header vắng mặt | Converter của consumer chọn cách xử lý khác |
| Producer emit String chứa JSON đã escape | Consumer nhận JSON string thay vì object |
| Sai destination/event type | Không nhận được message, tưởng body sai |

**Không giả định memory test binder và broker production dùng cùng serializer.** Khi contract cần chứng minh dữ liệu trên wire, bổ sung integration test với serializer/broker phù hợp.

### Không đồng nhất message body và HTTP JSON body

Một message có body dạng Map trong test framework có thể được serialize thành bytes khi publish qua Kafka/RabbitMQ. Cần xác định **các lớp conversion** của binder, framework và serializer thực tế.

Nếu consumer nhận raw bytes, không thể chỉ dựa vào việc body Map trong generated producer test đúng để kết luận wire format hoàn toàn tương thích.

## 26. Trường hợp content type bị đổi bởi proxy/gateway

Khi consumer gọi producer qua gateway:

~~~mermaid
flowchart LR
    C["Consumer"] --> G["Gateway / reverse proxy"]
    G --> P["Producer"]
    P --> G
    G --> C
~~~

Gateway có thể:

- Thay `Content-Type` hoặc `Accept`.
- Thêm/đổi charset.
- Nén response bằng gzip.
- Chuyển đổi lỗi thành HTML/text.
- Rewrite path làm request đi sai endpoint.
- Trả trang lỗi proxy 502/503 với `text/html` thay vì JSON API body.

Vì vậy, khi consumer log `Unexpected character '<'` lúc parse JSON, có thể response thực là **HTML error page từ proxy**, không phải body do producer serializer tạo.

**Cách điều tra:** xem status, response headers, body prefix an toàn, correlation/request ID và đường network của client. Không mặc định JSON parse exception = lỗi Jackson ở producer.

## 27. Quy trình chẩn đoán từng bước

Một workflow nên được lặp lại cho mọi tình huống:

~~~mermaid
flowchart TD
    A["Test FAIL / consumer lỗi"] --> B["Xác định tầng: producer hay consumer/stub?"]
    B --> C["Ghi method, path, request headers, body type"]
    C --> D["Đọc actual status + response headers/body"]
    D --> E{"Request tới đúng listener/mapping?"}
    E -->|Không| F["Sửa routing/Stub Runner artifact/request matcher"]
    E -->|Có| G{"Content-Type/Accept phù hợp?"}
    G -->|Không| H["Sửa client/server media type/negotiation"]
    G -->|Có| I{"Body parse đúng type?"}
    I -->|Không| J["Sửa serializer/DTO/codec/encoding"]
    I -->|Có| K{"Body khớp contract semantics?"}
    K -->|Không| L["Review producer behavior/contract/matcher"]
    K -->|Có| M["Kiểm tra fixture, test mode và assertions"]
    F --> N["Chạy lại producer + consumer tests"]
    H --> N
    J --> N
    L --> N
    M --> N
~~~

### Bảy thao tác ưu tiên

1. **Đóng băng bằng chứng:** xác định producer commit, contract revision, stub GAV/version và test run.
2. **Phân loại lỗi:** 415/406, JSON parser, mapping unmatched, response matcher hay business validation.
3. **So raw request/response:** method, URL, headers, body root type và bytes/encoding.
4. **Xem generated test/mapping:** DSL có thực sự sinh ra điều mong đợi?
5. **Xem converter/DTO:** Spring MVC/WebFlux, Jackson, serializers, annotations và profiles.
6. **Sửa đúng lớp:** client request, producer response, contract thỏa thuận, stub mapping hoặc hạ tầng.
7. **Chạy hồi quy:** producer generated tests, artifact mới và consumer tests với đúng stub mới.

### Vì sao không nên sửa đồng thời tất cả?

Nếu bạn cùng lúc đổi `Content-Type`, response DTO, JSONPath matcher và version Stub Runner, test PASS cuối cùng không chỉ ra nguyên nhân. Tốt hơn là đổi **một biến quan trọng mỗi lần**, lưu input/output tối thiểu và dùng test âm tính để kiểm chứng giả thuyết.

## 28. Checklist evidence tối thiểu trong bug report

Một bug report có thể dùng mẫu:

~~~text
Producer service/version/commit:
Contract path + revision:
Producer generated test ID + report:
Consumer service/version/commit:
Stub artifact GAV + classifier + checksum:
Stub Runner mode/repository/HTTP port:
Request method and full path:
Request Content-Type:
Request Accept:
Request body JSON root type:
Actual HTTP status:
Actual response Content-Type:
Actual response body (synthetic/redacted):
Expected contract status/body:
Exception/root cause:
Observed unmatched request or mapping ID:
Minimal reproduction:
Fix layer and rerun evidence:
~~~

Không bắt buộc mọi trường có giá trị với message contracts hoặc integration test không dùng Stub Runner; khi không áp dụng, hãy ghi rõ `N/A`.

**Không đưa token, Cookie, password, private key, payload có thông tin cá nhân hoặc link bí mật vào bug report.** Có thể sử dụng dữ liệu tổng hợp và log đã redact để tái hiện lỗi.

## 29. Mẫu bảng triệu chứng và hành động

| Triệu chứng trong test | Giả thuyết ưu tiên | Bằng chứng nên lấy | Hướng sửa |
| --- | --- | --- | --- |
| Producer trả 415 | Request Content-Type không thuộc `consumes` | Actual request header, controller mapping | Sửa client/contract hoặc media type hỗ trợ |
| Producer trả 406 | `Accept` không phù hợp `produces` | Actual Accept, converter list | Sửa content negotiation theo API |
| Producer trả 400 khi gửi JSON | Body syntax/type/DTO binding sai | Raw request body, Jackson cause | Sửa JSON/DTO/serializer |
| Producer trả 500 serialize response | Getter/custom serializer/date module lỗi | Stack trace, DTO config | Sửa producer serialization |
| WireMock unmatched 404 | URL/header/body matcher không khớp | Request journal, mapping | Sửa request hoặc contract/mapping đúng thỏa thuận |
| Consumer thấy HTML thay JSON | Proxy/gateway error body | Status, Content-Type, upstream logs | Sửa gateway/backend routing hoặc error handling |
| JSONPath `$.status` không tồn tại | Field bị đổi/omit/null | Actual response JSON + Jackson config | Review breaking change |
| `amount` string thay vì number | Double encoding/type coercion | JSON root/field types | Sửa serializer, giữ schema |
| Test FAIL do thứ tự object keys | Raw string equality | Parse JSON semantic diff | So structural JSON |
| Test FAIL do array order | API có thể cam kết thứ tự | Contract + business requirements | Chọn assertion tương ứng |
| Message consumer không parse | Body converter/serializer/header mismatch | Raw message bytes, headers, binder config | Sửa message format và versioning |
| Local PASS, CI FAIL | Khác profiles/artifacts/encoding/versions | Build metadata, stub checksum | Khóa env và artifact, tái lập |

## 30. Bài tập thực hành

### Bài tập A — Phân biệt Content-Type và Accept

Consumer gửi `Content-Type: text/plain`, `Accept: application/json` và JSON object body tới endpoint chỉ chấp nhận JSON.

**Yêu cầu:** lỗi nào có khả năng xảy ra? Cần kiểm tra và sửa yếu tố nào trước?

**Gợi ý:** kiểm tra 415, actual `consumes` và request Content-Type; không vội sửa response contract.

### Bài tập B — JSON bị double encoding

Contract request mong đợi JSON object, nhưng consumer gửi:

~~~json
"{\"customerId\":\"CUS-1001\",\"amount\":125000}"
~~~

**Yêu cầu:** root type là gì? Vì sao DTO producer có thể không parse được? Làm thế nào sửa client?

**Gợi ý:** đây là JSON string; chỉ serialize một lần ở đúng tầng HTTP client.

### Bài tập C — Body number bị đổi thành string

Producer trả `{"amount":"125000"}` nhưng contract yêu cầu number.

**Yêu cầu:** đây có thể là breaking change không? Vì sao không nên sửa matcher thành `any string`?

**Gợi ý:** consumer schema có thể cần numeric type; sửa serialization/DTO theo thỏa thuận hoặc làm migration được review.

### Bài tập D — 404 nghiệp vụ hay unmatched?

Consumer gọi `GET /api/order/ORD-NOT-FOUND` (không có chữ `s`), nhận 404; contract quy định `GET /api/orders/ORD-NOT-FOUND` trả JSON code `ORDER_NOT_FOUND`.

**Yêu cầu:** kết quả 404 có chứng minh business contract PASS không?

**Gợi ý:** không; kiểm tra URL và mapping, rồi xác nhận error body phù hợp.

### Bài tập E — Charset và tiếng Việt

Response `{"message":"Đơn hàng đã được tạo"}` bị hiển thị lỗi dấu trong consumer log.

**Yêu cầu:** lập danh sách nơi cần kiểm tra encoding.

**Gợi ý:** bytes, media type charset, client decoder, resource encoding và double encoding; không đổi expected body thành chuỗi lỗi dấu.

### Bài tập F — JSON null hay missing?

Contract yêu cầu field `discount: null`, nhưng producer dùng `NON_NULL` và bỏ field.

**Yêu cầu:** đây có thể là thay đổi behavior không? Cần review gì?

**Gợi ý:** absent khác null; kiểm tra consumer logic và hợp đồng.

### Bài tập G — Strict deserialization

Producer thêm trường `paymentStatus` vào response mà consumer cũ từ chối unknown properties.

**Yêu cầu:** vì sao thay đổi additive vẫn có thể phá consumer? Cần chạy test nào?

**Gợi ý:** thử consumer cũ với stub mới và parser config cũ.

### Bài tập H — Sai stub version

Producer 2.5.0 đã đổi schema, consumer test vẫn dùng stub 2.4.0 nên PASS.

**Yêu cầu:** có thể kết luận producer mới tương thích không? Cần bằng chứng gì?

**Gợi ý:** không; chạy consumer với stub 2.5.0 được sinh từ contract revision đã producer-verified.

### Bài tập I — Message header khác HTTP header

Contract message khai báo `contentType: application/json`, nhưng consumer nhận bytes do serializer khác tạo.

**Yêu cầu:** cần kiểm tra những tầng nào?

**Gợi ý:** binder/message converter, serializer thực, raw bytes và consumer deserializer; message header không tự tạo JSON bytes.

### Bài tập J — JSON object order

Response `{"id":"ORD-1001","status":"PAID"}` và `{"status":"PAID","id":"ORD-1001"}` bị so sánh raw string và FAIL.

**Yêu cầu:** chọn cách assertion phù hợp hơn và nêu khi nào cần byte-level equality.

**Gợi ý:** structural JSON equality/JSONPath, trừ khi giao thức cam kết canonical bytes.

### Bài tập K — Producer test mode sai

Generated test dùng RestAssuredMockMvc, nhưng base class lại chỉ cấu hình WebTestClient.

**Yêu cầu:** lỗi có nhất thiết nằm ở Content-Type không? Cần kiểm tra gì?

**Gợi ý:** kiểm tra test mode, generated source và base class wiring trước.

### Bài tập L — Proxy trả HTML

Consumer log có JSON parse error với ký tự đầu `<`; response status là 502 và Content-Type `text/html`.

**Yêu cầu:** ưu tiên điều tra producer serializer hay proxy/route?

**Gợi ý:** 502 HTML có thể do gateway; kiểm tra upstream error trước khi sửa JSON mapper.

## 31. Checklist trước khi đánh dấu đã khắc phục

### Xác định đúng triệu chứng

- [ ] Đã phân biệt request `Content-Type` với request `Accept`.
- [ ] Đã đọc actual response status, Content-Type và body.
- [ ] Đã xác định lỗi producer, stub mapping hay consumer deserialization.
- [ ] Đã phân biệt unmatched 404 của WireMock với 404 nghiệp vụ.
- [ ] Log dùng dữ liệu synthetic/redacted và không lộ secrets.

### Body và serialization

- [ ] Request body là JSON object/array/string đúng kiểu contract.
- [ ] Không double encode JSON.
- [ ] JSON numbers, booleans, null và strings đúng semantics.
- [ ] Missing field, explicit null và empty value được review.
- [ ] JSON object order/whitespace không bị coi là breaking giả.
- [ ] Array order được kiểm tra theo yêu cầu API.
- [ ] Charset và encoding được kiểm chứng khi có dữ liệu Unicode.
- [ ] Jackson DTO/annotations/naming/enum/date/decimal modules phù hợp.
- [ ] Content negotiation và `consumes`/`produces` khớp với giao diện đã thỏa thuận.
- [ ] Body-from-file được đóng gói và đọc đúng encoding/path.

### Spring Cloud Contract và Stub Runner

- [ ] Contract Groovy/YAML được plugin phát hiện ở đúng revision.
- [ ] Generated producer test có request và assertions như dự kiến.
- [ ] Test mode MockMvc/WebTestClient/live HTTP phù hợp base class.
- [ ] Generated tests thực sự chạy PASS, không bị skip ngoài ý muốn.
- [ ] Stub JAR có mappings và response files đúng.
- [ ] Stub Runner dùng GAV/classifier/version và repository đúng.
- [ ] Request thực của consumer match stub theo method/path/headers/body.
- [ ] Consumer tests có assertions riêng về nghiệp vụ và body, không chỉ HTTP status.
- [ ] Lỗi message serialization/binder/headers được kiểm tra nếu là message contract.
- [ ] Contract matcher không bị nới lỏng chỉ để CI xanh.

### Bằng chứng sửa lỗi

- [ ] Có minimal reproduction trước khi sửa.
- [ ] Đã xác định lớp nguyên nhân chính và thay đổi có chủ đích.
- [ ] Có regression test cho lỗi content type/serialization/body tương ứng.
- [ ] Producer verification và consumer tests đã chạy với artifact mới khi cần.
- [ ] Contract revision, producer commit, stub checksum và test reports được ghi.
- [ ] Không tuyên bố tương thích ngoài những versions/scenarios đã kiểm tra.

## Kết luận

Khi gặp lỗi **Content-Type, serialization hoặc body**, điều khó nhất không phải đọc JSON, mà là **xác định lớp nào tạo ra sai khác**: client gửi request sai, producer không deserialize được, producer serialize response khác contract, generated test dùng matcher không phù hợp, WireMock không match request, hoặc consumer parse response sai kiểu.

Một quy trình chẩn đoán hiệu quả bắt đầu bằng **method/path/headers/body thực**, phân biệt `Content-Type` và `Accept`, kiểm tra **raw bytes cùng JSON structure**, đọc generated producer test và mapping, rồi xác minh **stub artifact version** mà consumer thực sự dùng. Sửa đúng lớp và chạy lại producer–consumer tests giúp giữ giá trị phát hiện API không tương thích của Spring Cloud Contract.

**Ghi nhớ:** *HTTP status đúng chưa chắc body đúng; JSON hợp lệ chưa chắc đúng schema; WireMock 404 chưa chắc là 404 nghiệp vụ; và một consumer test PASS với stub cũ không chứng minh producer mới tương thích.*
