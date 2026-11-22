# Chọn kiểm thử hợp đồng hay tích hợp transport theo rủi ro

Trong Spring Boot, **GraphQL và SOAP đều có thể chạy trên HTTP**, nhưng hợp đồng của chúng không giống nhau. GraphQL đưa phần lớn ý nghĩa của request vào **schema, operation, field, argument và cấu trúc `data`/`errors`**. SOAP thường đặt trọng tâm vào **WSDL/XSD, XML namespace, SOAP Envelope/Header/Body, Fault, SOAPAction và những chính sách WS-\***; phần HTTP chỉ là một trong các transport có thể dùng.

Một bài test chạy trên bộ xử lý trong bộ nhớ có thể bảo vệ hợp đồng schema hoặc payload rất tốt, nhưng **không xác nhận TLS, proxy, servlet mapping, Content-Type, SOAPAction hay cổng mạng đang hoạt động**. Một bài test gọi HTTP server thật có thể xác nhận transport, nhưng nếu nó chỉ kiểm `HTTP 200`, không so nội dung GraphQL `errors` hoặc cấu trúc XML thì vẫn bỏ lọt lỗi hợp đồng nghiêm trọng.

Vì thế, câu hỏi không phải “chọn contract test **hay** transport integration test cho cả dự án”, mà là:

> **Rủi ro nào cần được phát hiện, phép kiểm nào thực sự chạy qua ranh giới gây ra rủi ro ấy, và một bài test bổ sung có đáng chi phí/độ bất ổn của nó không?**

Bài học dành cho module **Spring Boot – testing**, phần **GraphQL và SOAP**, dùng **Java 17+, Spring Boot 3.5.x, Spring GraphQL, Spring Web Services, JUnit Jupiter 5, Mockito, GraphQlTester, MockWebServiceClient và TestRestTemplate**. Ví dụ có hai endpoint cùng dùng một service tính báo giá nội bộ để so sánh **hợp đồng**, **vận chuyển HTTP** và **logic nghiệp vụ thật**. Không gọi database, cổng thanh toán hoặc đối tác production.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **contract test**, **transport integration test**, **service/unit test** và **end-to-end test** bằng thứ chúng thật sự chứng minh.
- Nhận diện rủi ro khác nhau giữa GraphQL schema/operation/errors và SOAP WSDL/XSD/namespace/Fault.
- Chọn `@GraphQlTest` + `GraphQlTester`, `@SpringBootTest(RANDOM_PORT)`, `MockWebServiceClient`, `MockWebServiceServer` và HTTP client theo mục tiêu.
- Biết **GraphQL trả HTTP 200 vẫn có thể có `errors`**, và **SOAP Fault** không thể đánh giá chỉ từ body/status mà không hiểu phiên bản SOAP.
- Thiết kế ma trận test theo **tác động × khả năng xảy ra × khả năng khó phát hiện**, không chạy mọi kịch bản qua network chỉ vì “tích hợp thật hơn”.
- Kiểm backward compatibility của GraphQL schema và SOAP WSDL/XSD trước khi giao tiếp với client production.
- Phân biệt request/response contract với authentication, authorization, proxy, TLS, content negotiation và timeout.
- Viết ví dụ Java 17+ gồm schema, controller/resolver, SOAP endpoint, XSD, test hợp đồng trong bộ nhớ và test HTTP qua random port.
- Thiết kế negative tests để phát hiện missing field, incorrect namespace, authorization leak, SOAPAction mismatch, partial GraphQL error, malformed SOAP và timeout.
- Báo cáo phạm vi kiểm thử trung thực: **test nào chạy logic thật, test nào mock collaborator và test nào đi qua TCP**.

## 2. Bốn ranh giới không được đánh đồng

### 2.1. Unit/service test

SUT là chính sách hoặc application service thật. Ví dụ `PricingService.quote(...)` tính đơn giá, giảm giá và kiểm input. Không cần GraphQL/HTTP/SOAP. Test chạy nhanh, phát hiện bug tính toán, nhưng **không biết schema, XML hay transport có đúng không**.

### 2.2. Contract test

Test bảo vệ **giao diện mà bên tiêu thụ nhìn thấy**. GraphQL: type/field/argument/non-null, data shape, error shape, authorization theo field. SOAP: WSDL operation/message, XSD qualified name và type, payload, Fault, WS-Addressing/SOAPAction nếu được cam kết. Có thể chạy trong bộ nhớ qua framework dispatcher, hoặc kiểm tệp/schema đã công bố. **Không bắt buộc mở socket**.

### 2.3. Transport integration test

Test đi qua một transport hoặc adapter thật: HTTP routing, content type, header, serialization, body bytes, SOAP envelope, servlet, TLS hoặc gateway tùy cấp độ. `@SpringBootTest(RANDOM_PORT)` kiểm server HTTP nội bộ. Nó **không tự kiểm reverse proxy, mTLS, load balancer hoặc đối tác bên ngoài** nếu những thứ đó không nằm trên đường gọi.

### 2.4. End-to-end/system test

Test băng qua nhiều dịch vụ và tài nguyên đã định nghĩa. Chi phí/độ bất ổn lớn hơn; hữu ích khi hợp đồng giữa hệ thống hoặc hành vi phân tán có rủi ro cao. Không gọi một test `RANDOM_PORT` dùng in-memory catalog là “E2E production”.

Sơ đồ:

```text
Domain/unit
   PricingService + real rules
           |
           v
Contract in process
   GraphQL schema/resolver  |  SOAP payload/XSD/endpoint
           |
           v
Transport integration
   POST /graphql via HTTP   |  SOAP Envelope via HTTP /services
           |
           v
Deployment/partner E2E
   gateway, TLS, identity, broker, DB, external partner

Mỗi tầng bổ sung bảo đảm; tầng rộng không thay thế tự động các assertion tầng hẹp.
```

## 3. GraphQL: “hợp đồng” nằm ở những chỗ nào?

Một GraphQL API được mô tả bằng **Schema Definition Language (SDL)**:

```graphql
type Query {
  quote(sku: String!, quantity: Int!, member: Boolean!): Quote!
}

type Quote {
  sku: String!
  quantity: Int!
  subtotalVnd: Int!
  discountVnd: Int!
  totalVnd: Int!
}
```

Những thay đổi hợp đồng có thể làm client hỏng:

- Xóa hoặc đổi tên `Quote.totalVnd`.
- Đổi field `quantity: Int!` thành kiểu không tương thích.
- Thêm một **required argument** mới mà client cũ không gửi.
- Đổi `Quote!` thành một kiểu khác, hoặc đổi nullable/non-null theo hướng làm thay đổi cách client xử lý.
- Đổi enum value/scalar encoding, pagination cursor hoặc sort semantics.
- Thay quy tắc truy cập khiến client cũ nhìn thấy hoặc không nhìn thấy dữ liệu khác trước.
- Resolver trả `null` tại vị trí schema đánh dấu non-null, dẫn tới **null propagation** và một hoặc nhiều lỗi.

**Không phải mọi thay đổi schema đều breaking.** Thêm field mới thường là thay đổi có thể tương thích với client cũ; nhưng thay đổi security, performance hoặc field-level authorization vẫn có thể là regression. So sánh schema/operation với tập query của consumer quan trọng hơn việc chỉ so số dòng SDL.

### 3.1. Contract là schema cộng hành vi thực thi

Schema compile thành công **không tự chứng minh** `Quote.totalVnd` đúng. Một bài test GraphQL mạnh có cả:

1. Schema field/argument tồn tại và coerces đúng.
2. Resolver mapping query/mutation đúng.
3. Response `data` có type, field, giá trị được chọn.
4. Error path, classification/extension và quyền truy cập đúng theo public contract.
5. Test service thật riêng để bảo vệ tính toán, repository, transaction.
6. Test transport nếu request thật cần đúng method, path, header, cookies, auth, CORS hoặc gateway.

## 4. GraphQL-over-HTTP: đừng đoán HTTP status từ một GraphQL error

Request thường có dạng:

```http
POST /graphql HTTP/1.1
Content-Type: application/json
Accept: application/graphql-response+json, application/json;q=0.9

{"query":"query { quote(sku:\"BOOK\",quantity:2,member:true) { totalVnd } }"}
```

Response thành công:

```json
{
  "data": {
    "quote": {
      "totalVnd": 216000
    }
  }
}
```

**Điểm mấu chốt:** Lỗi có thể phát sinh ở những pha khác nhau:

- **Request/parse/validation error:** JSON malformed, GraphQL syntax sai, field không tồn tại, biến không ép kiểu được; thao tác có thể không được thực thi.
- **Execution/field error:** Resolver ném exception hoặc không thể đọc dữ liệu của một field; GraphQL có thể trả **một phần `data`** cùng mảng `errors`.
- **Transport/security error:** HTTP method không cho phép, Content-Type sai, chưa xác thực, gateway timeout, server không khởi động.

Trong GraphQL-over-HTTP draft, `application/graphql-response+json` có hướng dẫn status code rõ hơn. Các server/legacy clients dùng `application/json` có thể trả HTTP 200 ngay cả khi response chứa `errors`, đặc biệt khi có partial data. **Không hard-code kết luận “GraphQL luôn trả 200 cho lỗi” hoặc “GraphQL error phải là HTTP 400”.** Hãy xác định **media type, phiên bản framework và hợp đồng triển khai**.

`GraphQlTester` mặc định coi GraphQL `errors` là lỗi khi xác minh dữ liệu, trừ những lỗi được test xử lý có chủ đích. `TestRestTemplate` hoặc HTTP client trả raw status/body để kiểm contract transport.

**Một GraphQL test chỉ `status().isOk()` có thể xanh dù bên trong có:**

```json
{
  "data": {
    "quote": null
  },
  "errors": [
    {
      "message": "Internal error",
      "path": ["quote"]
    }
  ]
}
```

Vì vậy cần assert **không có lỗi ngoài dự kiến**, và với kịch bản lỗi cần assert `errors` đúng classification/path/public information, không vô tình lộ stack trace hoặc SQL.

## 5. GraphQL queries, mutations và subscriptions cần test khác nhau

| Loại operation | Rủi ro chính | Contract nên kiểm | Transport cần kiểm khi... |
|---|---|---|---|
| Query | Sai field, argument, quyền đọc, N+1, cache | Schema, field, data, errors, authorization | Auth header, GET/POST support, gateway, CORS, cache |
| Mutation | Side effect, idempotency, transaction, optimistic locking | Input/output, error code, trạng thái sau mutation | POST semantics, CSRF/auth, retry/timeout và network ambiguity |
| Subscription | Stream event, order, cancellation, resource leak | Event type/data, lifecycle, errors | WebSocket handshake, subprotocol, reconnect, backpressure, proxy idle timeout |

Nếu dự án chỉ có query/mutation và dùng HTTP POST, `@GraphQlTest` + một vài real HTTP tests có thể đủ. Nếu có subscription chạy qua WebSocket, HTTP test `POST /graphql` **không bảo vệ** handshake, authentication refresh hoặc disconnect semantics; cần `WebSocketGraphQlTester`/stream integration test.

### 5.1. DataLoader và lỗi N+1

Một resolver được mock có thể trả dữ liệu đúng nhưng bỏ qua batch loading. Nếu latency/rate-limit DB là rủi ro, phải có test performance hoặc instrumentation với dữ liệu đủ lớn, kiểm số query/batch và cancellation, không chỉ assert JSON.

### 5.2. Authorization nằm sâu hơn URL

Một endpoint duy nhất `/graphql` thường cung cấp nhiều field với policy khác nhau. Cho phép truy cập URL **không đủ chứng minh** user chỉ xem được các object/field thuộc quyền. Cần test **object-level và field-level authorization**, kể cả truy cập qua aliases, fragments, nested resolvers hoặc alternate query paths.

## 6. SOAP: WSDL, XSD và thông điệp thực

SOAP thường đi cùng **WSDL 1.1/2.0**, **XSD** và một hoặc nhiều binding/policy. Chúng cung cấp các hợp đồng mà client được generate code từ đó rất nhạy:

- WSDL `portType`/operation, binding, service address, style/use, action.
- QName của root element, XML namespace URI và local name.
- Kiểu XSD: `xsd:string`, `xsd:int`, `xsd:decimal`, optional/required, occurrence, sequence và enumeration.
- SOAP 1.1 vs SOAP 1.2 envelope namespace và media type.
- Header theo chuẩn: SOAPAction, WS-Addressing Action, correlation ID, WS-Security signature.
- SOAP Fault semantics (`Client`/`Server` SOAP 1.1; `Sender`/`Receiver` SOAP 1.2), fault detail thuộc contract.
- MTOM/attachments, XML canonicalization/signature nếu có, character encoding/line endings ở wire format.

Nếu đổi:

```xml
<q:QuoteResponse xmlns:q="urn:demo:pricing:v1">
  <q:totalVnd>216000</q:totalVnd>
</q:QuoteResponse>
```

thành:

```xml
<q:QuoteResponse xmlns:q="urn:demo:pricing:v2">
  <q:totalVnd>216000</q:totalVnd>
</q:QuoteResponse>
```

thì client dựa vào **QName namespace URI** có thể không parse hoặc không dispatch được, dù tên local `QuoteResponse` và số tiền giống nhau. SOAP contract test nên bắt lỗi này, không chỉ tìm substring `216000`.

### 6.1. XML prefix khác XML namespace URI

Hai cách viết:

```xml
<a:QuoteResponse xmlns:a="urn:demo:pricing:v1" />
```

và:

```xml
<b:QuoteResponse xmlns:b="urn:demo:pricing:v1" />
```

có **cùng QName** đối với root element. So raw XML string sẽ báo khác vì `a`/`b`, dù nghĩa XML giống nhau. Dùng XML-aware comparison, XPath có namespace, hoặc XSD validation. Ngược lại, đổi URI thành `urn:demo:pricing:v2` là thay đổi thực chất.

### 6.2. XSD validation chưa phải toàn bộ WSDL contract

Kiểm `ResponseMatchers.validPayload(xsdResource)` chứng minh **payload output** thỏa XSD chỉ định. Nó không tự kiểm SOAPAction, endpoint URL, WSDL `binding`, mTLS, WS-Security, fault behavior, version SOAP hoặc policy của đối tác. Tệp WSDL công bố cần test riêng khi client generate từ WSDL, và bất kỳ sự thay đổi schema nào cũng cần review compatibility.

## 7. SOAP Envelope, Fault và HTTP status

SOAP 1.1 envelope ví dụ:

```xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:q="urn:demo:pricing:v1">
  <soapenv:Header/>
  <soapenv:Body>
    <q:QuoteRequest>
      <q:sku>BOOK</q:sku>
      <q:quantity>2</q:quantity>
      <q:member>true</q:member>
    </q:QuoteRequest>
  </soapenv:Body>
</soapenv:Envelope>
```

SOAP test trong bộ nhớ thường gửi **payload** (`QuoteRequest`) cho dispatcher, không tự gửi nguyên HTTP header/socket. HTTP transport test phải gửi **envelope** với đúng SOAP version và `Content-Type`.

Các điểm cần kiểm:

- SOAP 1.1 thường dùng `text/xml` và có `SOAPAction` khi binding/partner yêu cầu.
- SOAP 1.2 thường dùng `application/soap+xml`; action có thể nằm trong media-type parameter. Không trộn namespace SOAP 1.1 với Content-Type SOAP 1.2.
- Fault là **một cấu trúc SOAP**; tùy SOAP version/binding, nó có quan hệ với HTTP 500 hoặc status khác. Không kiểm mọi lỗi SOAP chỉ bằng `HTTP 500` mà bỏ `Fault`, faultcode và detail.
- Một HTTP 200 chứa payload SOAP có thể vẫn sai QName, sai kiểu XSD hoặc thiếu header bắt buộc.
- Một `MockWebServiceClient` test không phải test gateway/TLS/network timeouts, dù nó dùng khái niệm request/response.

## 8. WS-Security, chữ ký và MTOM cần cấp test riêng

Các lỗi **không thể được chứng minh** bằng việc so payload sau parse:

1. Chữ ký XML không hợp lệ sau canonicalization hoặc thay đổi namespace.
2. Timestamp WS-Security hết hạn hoặc sai skew.
3. Token/certificate không được tin cậy, mTLS handshake lỗi.
4. Header `mustUnderstand` bị bỏ qua.
5. MTOM attachment bị drop, sai MIME boundary hoặc Content-ID.
6. SOAPAction hoặc WS-Addressing Action không khớp WSDL/policy.
7. Proxy sửa Content-Type/chunking/size limit.
8. XML parser không khóa XXE/entity expansion hoặc không giới hạn payload kích thước lớn.

Khi những khả năng này có **tác động cao**, cần **adapter/transport integration test** đi qua interceptor, HTTP stack, TLS hoặc test partner sandbox tùy boundary. MockWebServiceClient chỉ có thể bảo vệ những interceptor được nạp trong test context; nếu WS-Security interceptor không có mặt, test payload xanh không chứng minh signature được validate.

**An toàn:** Không dùng keystore/credential production trong fixture, không gửi SOAP tới URL đối tác thật trừ khi có sandbox và quyền cho phép. Dùng test certificate/secret độc lập và làm sạch log chứa dữ liệu nhạy cảm.

## 9. Quy tắc lựa chọn theo rủi ro: không phải theo “độ lớn của annotation”

Một phép ước lượng có ích:

**Priority = Impact × Likelihood × Escape/Detectability**, mỗi yếu tố có thể chấm 1–5 trong team. Đây là cách **xếp thứ tự tương đối**, không phải một công thức tiêu chuẩn đo xác suất tuyệt đối.

- **Impact:** lỗi gây mất tiền, lộ dữ liệu, ngắt hợp tác, vi phạm compliance đến mức nào?
- **Likelihood:** cấu hình này hay thay, độ phức tạp của adapter/protocol, lịch sử sự cố?
- **Escape/Detectability:** nếu chỉ chạy unit/slice thì bug có dễ lọt đến staging/production không?

Ví dụ minh họa, không phải số liệu thực tế:

| Rủi ro | Impact | Likelihood | Escape | Điểm | Test nên có |
|---|---:|---:|---:|---:|---|
| GraphQL field-level auth lộ giá nội bộ | 5 | 3 | 5 | 75 | Authorization integration, negative queries |
| SOAP namespace v1 đổi nhầm v2 | 4 | 4 | 4 | 64 | XSD/WSDL contract, namespace fixture |
| TLS mTLS handshake với partner sai | 5 | 2 | 5 | 50 | Transport/sandbox với test cert |
| Thứ tự key trong GraphQL JSON khác | 1 | 4 | 1 | 4 | **Không** cần raw text snapshot |
| SOAP XML prefix khác nhưng URI giống | 1 | 4 | 1 | 4 | XML-aware assertion, không raw compare |
| Pricing service tính giảm giá sai | 5 | 3 | 3 | 45 | Unit/service thật + vài integrated path |
| Broker timeout khi publish mutation | 4 | 3 | 4 | 48 | Failure injection tại port + transport test |
| HTTP Content-Type GraphQL không đúng | 3 | 3 | 4 | 36 | Một vài real HTTP assertions |

**Cách dùng:** Team xếp rủi ro quan trọng nhất, chọn *test rẻ nhất có thể phát hiện rủi ro cụ thể*, rồi bổ sung vài test transport ở nơi in-memory test không có khả năng phát hiện. Không biến mọi operation/field thành một full random-port test.

## 10. Ma trận “rủi ro → đúng loại test”

| Rủi ro | GraphQL | SOAP | Vì sao không chỉ test tầng khác? |
|---|---|---|---|
| Schema/binding bị breaking | SDL/schema diff + consumer operations | WSDL/XSD diff + generated client tests | HTTP 200 một kịch bản chưa bảo vệ compatibility |
| Sai mapping argument/type | `@GraphQlTest` + `GraphQlTester` | `MockWebServiceClient` + schema/XPath | Domain unit không có parser/resolver/dispatcher |
| Sai nghiệp vụ | Service unit test + real service integration | Service unit test + real endpoint integration | Mock service ở slice che thuật toán |
| Sai header/media type | HTTP integration | HTTP SOAP envelope integration | In-memory dispatcher không đi qua HTTP |
| Sai field-level authorization | GraphQL auth integration | SOAP interceptor/policy integration | Query success không đủ cho data leak |
| SOAPAction/WS-Addressing | Ít liên quan trừ gateway custom | Transport test với header/action | Chỉ XSD payload không kiểm header |
| Partial data + errors | GraphQlTester error assertions | SOAP Fault/detail assertions | Không được chỉ kiểm status |
| TLS/mTLS/proxy | Staging or transport integration | Staging/partner sandbox | `RANDOM_PORT` localhost HTTP không test TLS production |
| N+1/load | Resolver + query count/perf test | DB/client throughput test | Schema đúng vẫn có thể chạy quá chậm |
| Retry/idempotency | Mutation/service failure injection | WebServiceTemplate failure injection | Happy-path không quan sát partial failure |
| MTOM/attachments | File upload/multipart nếu có | SOAP MIME/attachment integration | XML payload-only test bỏ attachment |

**Chiến lược tối thiểu:** Mỗi contract quan trọng nên có **contract assertions rẻ và dễ đọc**; mỗi transport boundary quan trọng nên có **ít nhất một bài integration test thực sự đi qua boundary ấy**; mỗi business rule quan trọng có **service/unit test chạy logic thật**.

## 11. Một thay đổi ảnh hưởng GraphQL và SOAP khác nhau thế nào?

Giả sử cùng nghiệp vụ báo giá có thể truy cập qua:

```text
            +------------------+
 GraphQL -->|                  |
            |  PricingService  |--> in-memory catalog
 SOAP ------|                  |
            +------------------+
```

Nếu sửa discount từ 10% sang 5%:

- Service unit test dùng logic thật phải đỏ.
- Full HTTP GraphQL/SOAP test dùng service thật cũng phải đỏ.
- `@GraphQlTest` với `@MockitoBean PricingService` có thể **vẫn xanh** do response được stub.
- SOAP `MockWebServiceClient` nếu dùng endpoint/service thật thì có thể đỏ; nếu endpoint service cũng mock thì không.

Nếu đổi GraphQL field `totalVnd` thành `amount`:

- GraphQL contract test/schema compatibility phải đỏ.
- SOAP payload contract **có thể không ảnh hưởng**.
- Service unit test không phát hiện vì không biết GraphQL SDL.

Nếu đổi SOAP namespace `urn:demo:pricing:v1` thành `v2`:

- SOAP QName/XSD tests phải đỏ.
- GraphQL tests thường không ảnh hưởng.
- HTTP 200 assertion đơn độc có thể không phát hiện nếu không đọc XML.

Nếu cấu hình sai SOAP servlet URL hoặc GraphQL HTTP media type:

- In-process contract tests có thể xanh.
- Real HTTP test phải phát hiện.

**Đây là lý do một ma trận kiểm thử đa giao thức cần các test trực giao**, không lặp cùng happy path ở mọi tầng một cách máy móc.

## 12. Chọn `GraphQlTester` đúng biến thể

Spring for GraphQL hỗ trợ cùng workflow kiểm thử nhưng **khác transport binding**:

- `ExecutionGraphQlServiceTester`: chạy server-side execution, **không cần HTTP**.
- `WebGraphQlTester`: chạy qua `WebGraphQlHandler` server-side.
- `HttpGraphQlTester`: dùng `WebTestClient` gửi qua HTTP; có thể bind vào mock application context hoặc live HTTP server tùy cách cấu hình.
- `WebSocketGraphQlTester`: phù hợp cho subscription qua WebSocket.
- `RSocketGraphQlTester`: khi ứng dụng thật dùng RSocket.

Trong Spring Boot 3.5:

- `@GraphQlTest` dựng graphQL slice **không có HTTP transport**, thường inject `GraphQlTester`. `@MockitoBean` cung cấp collaborator ngoài slice.
- `@SpringBootTest(RANDOM_PORT)` có thể tự cấu hình `HttpGraphQlTester` khi có những test dependencies cần thiết.
- `@SpringBootTest(MOCK)` có thể dùng `@AutoConfigureHttpGraphQlTester` để kiểm HTTP handler qua mock web environment; vẫn **không phải socket thật**.

**Không suy ra “dùng HttpGraphQlTester = dùng HTTP server thật”.** Phải xem `WebTestClient` bên dưới được bind thế nào. Trong ví dụ ở dưới, GraphQL contract test dùng `GraphQlTester`; transport test dùng `TestRestTemplate` qua `RANDOM_PORT` để mức kiểm rõ ràng.

## 13. Spring-WS: `MockWebServiceClient` vs `MockWebServiceServer`

Hai công cụ nghe gần giống nhau nhưng phục vụ **hai hướng tích hợp ngược nhau**:

| Công cụ | SUT là gì? | Test double nằm ở đâu? | Điều chứng minh |
|---|---|---|---|
| `MockWebServiceClient` | SOAP **server endpoint** và dispatcher | Không mở transport HTTP thật | SOAP request payload → endpoint mapping → response XML/Fault trong context |
| `MockWebServiceServer` | SOAP **client adapter** dùng `WebServiceTemplate` | Mô phỏng remote SOAP server | Client marshal/request đúng, xử lý response/fault giả, không gọi partner thật |
| HTTP client + `RANDOM_PORT` | SOAP server và servlet/HTTP | Partner/client thật tùy test | SOAP envelope, HTTP path, Content-Type, status và XML thực |
| Partner sandbox | Server/client và remote protocol có kiểm soát | Sandbox chứ không production | TLS/auth/action/policy/interoperability đúng phạm vi sandbox |

`MockWebServiceClient.createClient(applicationContext)` có thể hoạt động với endpoint/context đã nạp và gửi `RequestCreators.withPayload(...)`. Assert bằng `ResponseMatchers.payload`, `validPayload`, `xpath`, `noFault` hoặc fault matchers phù hợp.

`MockWebServiceServer.createServer(webServiceTemplate)` có thể dùng `RequestMatchers.payload`/`soapHeader` rồi `ResponseCreators.withPayload`/`withServerOrReceiverFault`; sau lời gọi SUT phải `verify()`. Những test này **không thay** kết nối thực qua HTTP nếu rủi ro nằm ở proxy/timeout/TLS.

## 14. Ví dụ runnable: một service, hai giao thức

Để dễ thấy ranh giới, ta dựng một ứng dụng **Spring MVC + Spring GraphQL + Spring Web Services** cùng chạy trong Spring Boot 3.5.x. Dữ liệu giá cố định, không có DB hay đối tác ngoài.

Quy tắc demo:

- `BOOK`: 120.000 VND/đơn vị, `PEN`: 20.000 VND/đơn vị.
- `quantity` phải từ 1 trở lên.
- `member=true` giảm 10% tạm tính bằng chia nguyên.
- Quote gồm `sku`, `quantity`, `subtotalVnd`, `discountVnd`, `totalVnd`.
- Số tiền là `int` chỉ để hợp với GraphQL scalar `Int` và XSD `xs:int`. GraphQL `Int` là **signed 32-bit**; hệ thống tiền tệ thật không nên coi `Int` đủ cho số tiền lớn. Dùng scalar Money/BigDecimal/custom scalar hoặc cách biểu diễn an toàn với contract rõ.

Ứng dụng cung cấp:

- `POST /graphql` qua Spring GraphQL.
- SOAP 1.1 trên servlet mapping mặc định của Boot **`/services`**.
- GraphQL SDL và một XSD contract fixture.
- Test slice/contract không socket và test HTTP random port.

### 14.1. Cây file

```text
src/main/java/com/example/dualcontract/
    DualContractApplication.java
    Quote.java
    PricingService.java
    QuoteGraphQlController.java
    QuoteSoapEndpoint.java

src/main/resources/graphql/
    schema.graphqls

src/test/java/com/example/dualcontract/
    GraphQlSchemaContractTest.java
    GraphQlHttpTransportTest.java
    SoapPayloadContractTest.java
    SoapHttpTransportTest.java

src/test/resources/contracts/
    quote.xsd
```

**Phạm vi ví dụ runnable:** Các file này đủ để kiểm **query GraphQL**, SOAP quote payload, response XSD và HTTP transport trong một project với dependencies ở mục 15. Ví dụ không công bố WSDL, không triển khai WS-Security, không thử SOAP 1.2, MTOM hay client SOAP ngoài: những phần ấy được giải thích bằng test recipes riêng và không được tuyên bố đã kiểm.

## 15. Dependencies và lệnh chạy Gradle

Trong Gradle project đã cấu hình **Spring Boot 3.5.x plugin/BOM, repositories và Java 17+**, khai báo:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-webservices'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.graphql:spring-graphql-test'
    testImplementation 'org.springframework.ws:spring-ws-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **đoạn dependency bổ sung**, không phải một `build.gradle` hoàn chỉnh. Project cần có cấu hình plugin version và repository thật. Với Boot 3.5, `@GraphQlTest` dùng `spring-graphql-test`, `TestRestTemplate` đến từ bộ test Boot, `MockWebServiceClient` đến từ `spring-ws-test`. Nếu có nhiều starter web stack, cần kiểm application type; ví dụ chỉ dùng servlet Spring MVC, không cần thêm starter-webflux cho code test này.

Chạy qua Gradle wrapper:

```bash
./gradlew test --tests com.example.dualcontract.GraphQlSchemaContractTest --tests com.example.dualcontract.GraphQlHttpTransportTest --tests com.example.dualcontract.SoapPayloadContractTest --tests com.example.dualcontract.SoapHttpTransportTest
```

Trên PowerShell:

```powershell
.\gradlew.bat test --tests com.example.dualcontract.GraphQlSchemaContractTest --tests com.example.dualcontract.GraphQlHttpTransportTest --tests com.example.dualcontract.SoapPayloadContractTest --tests com.example.dualcontract.SoapHttpTransportTest
```

Bốn test class này được trình bày ở các mục tiếp theo. **Đoạn có nhãn “snippet” không phải file Java độc lập**; chỉ tạo các file trong cây thư mục đã liệt kê. Với multi-module Gradle, chọn đúng task `:module:test` của dự án.

## 16. Code Java: application và quote domain

**`src/main/java/com/example/dualcontract/DualContractApplication.java`**

```java
package com.example.dualcontract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DualContractApplication {
    public static void main(String[] args) {
        SpringApplication.run(DualContractApplication.class, args);
    }
}
```

**`src/main/java/com/example/dualcontract/Quote.java`**

```java
package com.example.dualcontract;

public record Quote(
        String sku,
        int quantity,
        int subtotalVnd,
        int discountVnd,
        int totalVnd) {
}
```

**`src/main/java/com/example/dualcontract/PricingService.java`**

```java
package com.example.dualcontract;

import org.springframework.stereotype.Service;

@Service
public class PricingService {

    public Quote quote(String sku, int quantity, boolean member) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                    "sku is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }

        int unitPrice = switch (sku) {
            case "BOOK" -> 120_000;
            case "PEN" -> 20_000;
            default -> throw new IllegalArgumentException(
                    "unknown sku");
        };

        int subtotal = Math.multiplyExact(unitPrice, quantity);
        int discount = member ? subtotal / 10 : 0;
        int total = Math.subtractExact(subtotal, discount);

        return new Quote(sku, quantity, subtotal,
                discount, total);
    }
}
```

`Math.multiplyExact` phát hiện overflow của `int`. Production nên có giới hạn input và error mapping công khai; ví dụ này chỉ phục vụ minh họa logic thật được gọi qua hai giao thức. **Không mock PricingService trong HTTP transport tests**, để một lỗi business làm cả GraphQL/SOAP integration test đỏ.

## 17. GraphQL schema và controller/resolver

**`src/main/resources/graphql/schema.graphqls`**

```graphql
type Query {
    quote(
        sku: String!
        quantity: Int!
        member: Boolean!
    ): Quote!
}

type Quote {
    sku: String!
    quantity: Int!
    subtotalVnd: Int!
    discountVnd: Int!
    totalVnd: Int!
}
```

**`src/main/java/com/example/dualcontract/QuoteGraphQlController.java`**

```java
package com.example.dualcontract;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class QuoteGraphQlController {
    private final PricingService pricing;

    public QuoteGraphQlController(PricingService pricing) {
        this.pricing = pricing;
    }

    @QueryMapping
    public Quote quote(
            @Argument String sku,
            @Argument int quantity,
            @Argument boolean member) {
        return pricing.quote(sku, quantity, member);
    }
}
```

`@QueryMapping` liên kết field `Query.quote` trong schema với method thật; `@Argument` bind query arguments. Với kết quả là Java record, các field được GraphQL Java/Spring GraphQL lấy từ dữ liệu trả về theo cơ chế property data fetcher thông dụng.

**Điểm kiểm:** schema contract test phải phát hiện khi argument hoặc field bị đổi. Nhưng nếu service trong slice bị mock, nó không kiểm tính đúng của phép giảm giá; test HTTP phía sau sẽ chạy `PricingService` thật.

## 18. SOAP endpoint: payload theo QName và service thật

**`src/main/java/com/example/dualcontract/QuoteSoapEndpoint.java`**

```java
package com.example.dualcontract;

import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.Source;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMResult;
import javax.xml.transform.dom.DOMSource;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

@Endpoint
public class QuoteSoapEndpoint {

    public static final String NS = "urn:demo:pricing:v1";
    private final PricingService pricing;

    public QuoteSoapEndpoint(PricingService pricing) {
        this.pricing = pricing;
    }

    @PayloadRoot(namespace = NS, localPart = "QuoteRequest")
    @ResponsePayload
    public Source quote(@RequestPayload Source request)
            throws Exception {

        Document in = DocumentBuilderFactory.newInstance()
                .newDocumentBuilder().newDocument();
        TransformerFactory.newInstance()
                .newTransformer()
                .transform(request, new DOMResult(in));

        Element root = in.getDocumentElement();
        String sku = child(root, "sku");
        int quantity = Integer.parseInt(child(root, "quantity"));
        boolean member = Boolean.parseBoolean(
                child(root, "member"));

        Quote value = pricing.quote(sku, quantity, member);

        Document out = DocumentBuilderFactory.newInstance()
                .newDocumentBuilder().newDocument();
        Element response = out.createElementNS(
                NS, "q:QuoteResponse");
        out.appendChild(response);

        append(out, response, "sku", value.sku());
        append(out, response, "quantity",
                Integer.toString(value.quantity()));
        append(out, response, "subtotalVnd",
                Integer.toString(value.subtotalVnd()));
        append(out, response, "discountVnd",
                Integer.toString(value.discountVnd()));
        append(out, response, "totalVnd",
                Integer.toString(value.totalVnd()));

        return new DOMSource(response);
    }

    private static String child(Element root, String localName) {
        NodeList matches =
                root.getElementsByTagNameNS(NS, localName);
        if (matches.getLength() != 1) {
            throw new IllegalArgumentException(
                    "expected one element: " + localName);
        }
        return matches.item(0).getTextContent().trim();
    }

    private static void append(
            Document doc, Element parent,
            String localName, String value) {
        Element child = doc.createElementNS(
                NS, "q:" + localName);
        child.setTextContent(value);
        parent.appendChild(child);
    }
}
```

Đây là **endpoint demo để học test boundary**, không phải XML processing implementation khuyến nghị cho production. XML parser/transformer/WS-Security cần được cấu hình chống XXE, entity expansion, external DTD và payload quá lớn, hoặc thay bằng JAXB/typed binding đã kiểm schema. `Boolean.parseBoolean(...)` nhận nhiều chuỗi không phải `"true"` thành `false`; ở production phải **validate XSD và coerce kiểu nghiêm ngặt** trước khi tính tiền.

**Ranh giới quan trọng:**

- `@PayloadRoot` dispatch theo **namespace URI và local name** của phần tử payload gốc.
- `@RequestPayload Source`/`@ResponsePayload Source` làm việc với payload XML; HTTP envelope/body được Spring-WS xử lý.
- `PricingService` chạy thật trong SOAP endpoint.
- Chưa có WSDL bean được công bố trong ví dụ: test XSD riêng chỉ bảo vệ shape payload; để kiểm interoperability dựa trên WSDL, cần cấu hình WSDL/XSD chính thức và thực hiện thêm WSDL publication test.

## 19. XSD fixture cho SOAP response/request

**`src/test/resources/contracts/quote.xsd`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    targetNamespace="urn:demo:pricing:v1"
    xmlns:q="urn:demo:pricing:v1"
    elementFormDefault="qualified">

  <xs:element name="QuoteRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="sku" type="xs:string"/>
        <xs:element name="quantity" type="xs:int"/>
        <xs:element name="member" type="xs:boolean"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="QuoteResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="sku" type="xs:string"/>
        <xs:element name="quantity" type="xs:int"/>
        <xs:element name="subtotalVnd" type="xs:int"/>
        <xs:element name="discountVnd" type="xs:int"/>
        <xs:element name="totalVnd" type="xs:int"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

Tệp này **là contract fixture do test quản lý**, không tự công bố thành WSDL endpoint. Khi API SOAP thật là contract-first, thường nên để XSD/WSDL thuộc main resources/version-controlled artifacts và test đọc **chính tệp đã công bố**, không copy một bản dễ lệch nằm riêng trong test.

`xs:int` và GraphQL `Int` được chọn để cùng dùng demo numbers. Trong thực tế, một số tiền lớn hoặc có decimal scale nên biểu diễn bằng `xs:decimal`, long/custom scalar hoặc kiểu money tương ứng; cần review overflow và rounding.

## 20. Test GraphQL hợp đồng không qua HTTP

**`src/test/java/com/example/dualcontract/GraphQlSchemaContractTest.java`**

```java
package com.example.dualcontract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@GraphQlTest(QuoteGraphQlController.class)
class GraphQlSchemaContractTest {

    @Autowired
    GraphQlTester tester;

    @MockitoBean
    PricingService pricing;

    @Test
    void mapsArgumentsAndSelectedFields() {
        when(pricing.quote("BOOK", 2, true))
                .thenReturn(new Quote(
                        "BOOK", 2, 240_000, 24_000, 216_000));

        tester.document("""
                query Quote($sku: String!,
                            $quantity: Int!,
                            $member: Boolean!) {
                  quote(sku: $sku,
                        quantity: $quantity,
                        member: $member) {
                    sku
                    quantity
                    subtotalVnd
                    discountVnd
                    totalVnd
                  }
                }
                """)
                .variable("sku", "BOOK")
                .variable("quantity", 2)
                .variable("member", true)
                .execute()
                .path("quote.totalVnd")
                .entity(Integer.class)
                .isEqualTo(216_000);

        verify(pricing).quote("BOOK", 2, true);
    }

    @Test
    void rejectsFieldNotDeclaredBySchema() {
        tester.document("""
                { quote(sku:"BOOK",quantity:2,member:true) {
                    secretKey
                  } }
                """)
                .execute()
                .errors()
                .satisfy(errors -> assertFalse(errors.isEmpty()));
    }
}
```

**Giá trị của test:**

- GraphQL schema được parse/validated; argument mapping vào controller thật.
- `GraphQlTester` đọc path **tương đối với `data`**, không cần `$.data.quote.totalVnd`.
- Kết quả trả về được ánh xạ theo schema field selection.
- Truy vấn field chưa khai báo tạo `errors`, giúp phát hiện contract không đúng.
- `PricingService` là **Mockito mock**, nên test **không chứng minh phép giảm 10%**. Điều này là có chủ đích để test web/schema slice nhanh và cô lập.

**Không có HTTP socket, Content-Type, authentication gateway hoặc serialization network thật** trong test này. Đừng gọi nó là transport integration.

## 21. Test GraphQL qua real HTTP server

**`src/test/java/com/example/dualcontract/GraphQlHttpTransportTest.java`**

```java
package com.example.dualcontract;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = DualContractApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GraphQlHttpTransportTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    ObjectMapper mapper;

    @Test
    void postsActualHttpAndRunsPricingService() throws Exception {
        String operation = """
                query Quote($sku: String!,
                            $quantity: Int!,
                            $member: Boolean!) {
                  quote(sku: $sku,
                        quantity: $quantity,
                        member: $member) {
                    sku
                    quantity
                    subtotalVnd
                    discountVnd
                    totalVnd
                  }
                }
                """;

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));

        HttpEntity<Map<String, Object>> request = new HttpEntity<>(
                Map.of(
                        "query", operation,
                        "variables", Map.of(
                                "sku", "BOOK",
                                "quantity", 2,
                                "member", true)),
                headers);

        ResponseEntity<String> response = http.exchange(
                "/graphql", HttpMethod.POST, request, String.class);

        assertEquals(200, response.getStatusCode().value());
        MediaType type = response.getHeaders().getContentType();
        assertNotNull(type);
        assertTrue(MediaType.APPLICATION_JSON.isCompatibleWith(type));

        JsonNode root = mapper.readTree(response.getBody());
        assertFalse(root.has("errors"));
        assertEquals("BOOK",
                root.required("data").required("quote")
                        .required("sku").asText());
        assertEquals(216_000,
                root.required("data").required("quote")
                        .required("totalVnd").intValue());
    }
}
```

**Tại sao chọn `Accept: application/json` trong demo?** Để test đơn giản một media type được Spring GraphQL/Boot 3.5 triển khai; với API mới được thiết kế theo GraphQL-over-HTTP draft, nên có thêm negotiation test dành cho `application/graphql-response+json` và status behavior theo chính sách/version của server. Đừng khẳng định hai media type luôn có cùng status policy ở mọi server.

**Điều test này chứng minh:**

- Embedded server thật mở cổng ngẫu nhiên, nhận POST `/graphql` qua HTTP.
- HTTP JSON request/response được encode/decode, Content-Type đúng.
- GraphQL endpoint và schema được nạp.
- PricingService **chạy thật**, nên tổng tiền được tính từ code.
- Nếu đổi công thức giảm 10% thành 5%, JSON result sẽ thay và test phải đỏ.

**Điều chưa chứng minh:** token/mTLS/gateway/CDN, DB, GraphQL subscription WebSocket, rate limiting, persisted queries hay security field-level vì demo chưa cấu hình chúng.

## 22. SOAP payload contract: chạy endpoint nhưng không mở socket

**`src/test/java/com/example/dualcontract/SoapPayloadContractTest.java`**

```java
package com.example.dualcontract;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.ws.test.server.RequestCreators;
import org.springframework.ws.test.server.ResponseMatchers;
import org.springframework.xml.transform.StringSource;

@SpringBootTest(
        classes = DualContractApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class SoapPayloadContractTest {

    @Autowired
    ApplicationContext context;

    MockWebServiceClient client;

    @BeforeEach
    void setUp() {
        client = MockWebServiceClient.createClient(context);
    }

    @Test
    void matchesQualifiedResponseAndXsd() {
        StringSource request = new StringSource("""
                <q:QuoteRequest xmlns:q="urn:demo:pricing:v1">
                  <q:sku>BOOK</q:sku>
                  <q:quantity>2</q:quantity>
                  <q:member>true</q:member>
                </q:QuoteRequest>
                """);

        StringSource expected = new StringSource("""
                <q:QuoteResponse xmlns:q="urn:demo:pricing:v1">
                  <q:sku>BOOK</q:sku>
                  <q:quantity>2</q:quantity>
                  <q:subtotalVnd>240000</q:subtotalVnd>
                  <q:discountVnd>24000</q:discountVnd>
                  <q:totalVnd>216000</q:totalVnd>
                </q:QuoteResponse>
                """);

        client.sendRequest(RequestCreators.withPayload(request))
                .andExpect(ResponseMatchers.noFault())
                .andExpect(ResponseMatchers.payload(expected))
                .andExpect(ResponseMatchers.validPayload(
                        new ClassPathResource("contracts/quote.xsd")));
    }
}
```

**Điều test này bảo vệ:**

- SOAP payload root `{urn:demo:pricing:v1}QuoteRequest` được dispatcher map vào `@PayloadRoot`.
- `QuoteSoapEndpoint` gọi service thật và tạo XML có QName, value, sequence tương ứng expected.
- Response payload không chứa SOAP Fault.
- XML response thỏa XSD fixture, phát hiện thiếu/sai kiểu/sai namespace đối với trường được schema khai báo.

**Điều chưa bảo vệ:** HTTP endpoint mapping `/services`, SOAPAction trên wire, actual envelope version, TLS, proxy, WSDL publish, MTOM và partner policy. Nếu cần WSDL compatibility, phải test **tệp WSDL thực sự xuất bản**, không suy ra từ payload fixture.

## 23. SOAP transport integration: envelope + HTTP + payload

**`src/test/java/com/example/dualcontract/SoapHttpTransportTest.java`**

```java
package com.example.dualcontract;

import java.io.StringReader;
import java.util.List;
import javax.xml.parsers.DocumentBuilderFactory;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = DualContractApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SoapHttpTransportTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void soap11EnvelopeTravelsThroughRealHttp() throws Exception {
        String envelope = """
                <soap:Envelope
                    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
                    xmlns:q="urn:demo:pricing:v1">
                  <soap:Header/>
                  <soap:Body>
                    <q:QuoteRequest>
                      <q:sku>BOOK</q:sku>
                      <q:quantity>2</q:quantity>
                      <q:member>true</q:member>
                    </q:QuoteRequest>
                  </soap:Body>
                </soap:Envelope>
                """;

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.parseMediaType(
                "text/xml;charset=UTF-8"));
        headers.setAccept(List.of(MediaType.TEXT_XML));
        headers.set("SOAPAction", "\"urn:demo:pricing:v1/quote\"");

        ResponseEntity<String> response = http.exchange(
                "/services",
                HttpMethod.POST,
                new HttpEntity<>(envelope, headers),
                String.class);

        assertEquals(200, response.getStatusCode().value());
        MediaType contentType = response.getHeaders().getContentType();
        assertNotNull(contentType);
        assertTrue(MediaType.TEXT_XML.isCompatibleWith(contentType));
        assertNotNull(response.getBody());

        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl",
                true);
        factory.setFeature(
                "http://xml.org/sax/features/external-general-entities",
                false);
        factory.setFeature(
                "http://xml.org/sax/features/external-parameter-entities",
                false);
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);

        Document document = factory.newDocumentBuilder().parse(
                new InputSource(new StringReader(response.getBody())));

        Element root = document.getDocumentElement();
        assertEquals("Envelope", root.getLocalName());
        assertEquals(
                "http://schemas.xmlsoap.org/soap/envelope/",
                root.getNamespaceURI());

        NodeList totals = document.getElementsByTagNameNS(
                "urn:demo:pricing:v1", "totalVnd");
        assertEquals(1, totals.getLength());
        assertEquals("216000", totals.item(0).getTextContent());
    }
}
```

**Ý nghĩa test:** request thật đi qua HTTP servlet mapping `/services` (mặc định Boot 3.5), SOAP 1.1 envelope và Content-Type, đến Spring-WS endpoint rồi trở về dưới dạng SOAP XML. Các field được parse **theo namespace URI**, không dựa vào prefix `q` hay text comparison thuần.

**Giới hạn chính xác:** Header `SOAPAction` được **gửi qua transport** nhưng endpoint demo dùng `@PayloadRoot`, không có rule buộc phải match SOAPAction. Test trên **chưa chứng minh server từ chối SOAPAction sai**. Nếu đối tác/WSDL yêu cầu action matching, thêm `@SoapAction`, mapping/interceptor/policy phù hợp và negative test. Tương tự, parser của test chỉ đọc response từ server nội bộ; production XML security cần có cấu hình cứng rắn và giới hạn tài nguyên ngay trên request ingestion.

**Cẩn trọng:** `TestRestTemplate` trả body như String trong ví dụ để tập trung vào SOAP Envelope; nếu charset/byte signing là hợp đồng, hãy đọc `byte[]`, kiểm encoding và canonicalization theo đúng chuẩn, không dựa vào hiển thị văn bản.

## 24. Những test quan trọng chưa có trong demo

Bộ code ở trên cố ý nhỏ. Trong sản phẩm thật, thêm test khi **rủi ro đủ lớn**:

### 24.1. GraphQL schema compatibility/consumer contract

Dùng công cụ schema diff có phân tích breaking changes và tập operations từ client thật. Tập query phải bao gồm alias, fragment, variable, enum/scalar thay đổi. Một thay đổi schema backward-compatible về cú pháp vẫn có thể sai authorization hoặc performance; kiểm cả behavior.

### 24.2. GraphQL partial errors

Một resolver trả data cho `publicField` nhưng ném exception ở `restrictedField`. Test cần xác nhận `data` chỉ chứa thông tin phù hợp, `errors[].path`/`extensions.code` đúng public contract; không lộ internal exception. Không giả định HTTP 500 khi execution tạo partial response.

### 24.3. GraphQL mutation idempotency

Với mutation tạo order hoặc charge tiền, mô phỏng retry cùng idempotency key, timeout sau commit và hai request song song. Assert **chỉ một side effect** và response contract rõ. HTTP 200 và `data` đúng trong một request không chứng minh chống double charge.

### 24.4. GraphQL authorization negative cases

Query cùng một object với hai user/tenant, yêu cầu field-level access; thử aliases/fragments/nested paths để phát hiện bypass. Thêm test full context/security filter khi rủi ro nằm ở auth token hoặc filter chain, không chỉ mock principal.

### 24.5. SOAP WSDL XSD backward compatibility

Xuất WSDL thật hoặc giữ contract-first WSDL versioned. Dùng code generation/validation cho generated client của partner; so `operation`, `message`, `binding`, `service`, namespaces, cardinalities, schema imports và SOAPAction. Payload XSD unit test không thay kiểm WSDL publication.

### 24.6. SOAP Fault và error leakage

Tạo input sai schema, namespace sai, business exception và downstream timeout. Assert **SOAP Fault** theo version cùng fault code/detail công khai; không trả stack trace hoặc raw credential. Khác nhau giữa SOAP 1.1 và 1.2 cần test theo đúng binding.

### 24.7. SOAP WS-Security mTLS

Dùng test certificates/keystores và server sandbox để kiểm signature, timestamp replay/expiry, credential rotation, truststore và mTLS. Mock payload không bảo vệ transport identity. Không kiểm chữ ký bằng việc đơn thuần so XML sau khi deserialize: XML Signature có semantics riêng về canonicalization và references.

### 24.8. SOAPAction / WS-Addressing

Nếu WSDL/policy yêu cầu `SOAPAction` và `wsa:Action`, gửi action sai và assert bị từ chối. HTTP client cần truyền header thật; test `@PayloadRoot` đơn lẻ chỉ kiểm QName root, **không kiểm action**.

### 24.9. Attachments và streaming

SOAP MTOM, multipart attachments hoặc GraphQL subscriptions cần test MIME parts, Content-ID, sequence, cancellation, timeout và memory profile. `MockWebServiceClient.withPayload` không tái tạo toàn bộ MIME transport; `GraphQlTester.document(...).execute()` không kiểm WebSocket handshake.

### 24.10. Data validation trước SOAP service

Dù response XSD hợp lệ, input không tự được validate nếu chưa cấu hình validating interceptor. Dự án thật cần inbound XSD validation và test gửi `quantity` sai kiểu, thiếu field, nhiều occurrence, namespace sai và XML entity attack, bảo đảm không chạm business service khi request vi phạm contract.

## 25. Hướng kiểm SOAP client adapter bằng `MockWebServiceServer`

Nếu ứng dụng của bạn **là client gọi SOAP partner**, `MockWebServiceClient` không phải lựa chọn phù hợp để kiểm outbound adapter. Dùng `WebServiceTemplate` thật cùng `MockWebServiceServer` để mô phỏng remote SOAP server.

Ví dụ **snippet** (không phải file Java runnable độc lập; cần một client class và cấu hình `WebServiceTemplate` tương ứng):

```java
MockWebServiceServer server =
        MockWebServiceServer.createServer(webServiceTemplate);

server.expect(RequestMatchers.payload(
        new StringSource("""
                <q:QuoteRequest xmlns:q="urn:demo:pricing:v1">
                  <q:sku>BOOK</q:sku>
                  <q:quantity>2</q:quantity>
                  <q:member>true</q:member>
                </q:QuoteRequest>
                """)))
        .andRespond(ResponseCreators.withPayload(
                new StringSource("""
                        <q:QuoteResponse
                            xmlns:q="urn:demo:pricing:v1">
                          <q:sku>BOOK</q:sku>
                          <q:quantity>2</q:quantity>
                          <q:subtotalVnd>240000</q:subtotalVnd>
                          <q:discountVnd>24000</q:discountVnd>
                          <q:totalVnd>216000</q:totalVnd>
                        </q:QuoteResponse>
                        """)));

Quote result = soapPartnerClient.getQuote("BOOK", 2, true);
assertEquals(216_000, result.totalVnd());
server.verify();
```

Đoạn này **giải thích hướng kiểm**, không định nghĩa `soapPartnerClient` hoặc marshaller; dự án phải có outbound adapter thật. `MockWebServiceServer` thay transport đến partner, nên test không mở network nhưng vẫn có thể kiểm cách client marshalling, parsing và xử lý SOAP Fault có chủ đích.

Khi rủi ro nằm ở connection pool, HTTP authentication, proxy, TLS hoặc timeout network, cần một bài HTTP integration với mock SOAP server/container hoặc sandbox. Không thay mọi outbound unit test bằng sandbox thật — dễ flaky và tốn thời gian.

## 26. Chi phí kiểm thử: tối ưu coverage chứ không đếm số integration tests

Một lỗi phổ biến là chạy 300 GraphQL queries và 300 SOAP payloads qua HTTP random port, mỗi test bootstraps full context. Điều này có thể khiến CI chậm, dữ liệu dùng chung, race condition và test failure khó debug.

Phân chia hợp lý:

1. **Nhiều unit tests rẻ** cho policy, validation, Money, mapping quan trọng.
2. **Nhiều contract slice tests** cho GraphQL fields, SOAP QName/XSD/Fault và boundary logic.
3. **Ít nhưng chọn lọc HTTP transport tests** cho media type, URL, headers, serialization, servlet config và một vài negative errors.
4. **Adapter/partner contract tests** cho WSDL, schema compatibility, generated clients và các format cụ thể.
5. **Rất ít E2E tests** cho vài luồng giá trị cao xuyên qua những hệ thống bạn thực sự vận hành/được phép thử.

Đây không phải tỷ lệ cố định. Payment platform có thể cần nhiều transaction failure/soap fault integration; dashboard read-only GraphQL có thể cần nhiều authorization/performance tests hơn SOAP client sandbox tests.

**Mục tiêu không phải “mỗi method có test HTTP”**. Mục tiêu là lỗi rủi ro cao **không thể lọt chỉ vì tất cả bài test đã mock mất boundary gây lỗi đó**.

## 27. Chọn test theo những thay đổi cụ thể

| Thay đổi | Test nên chạy trước | Test bổ sung khi rủi ro cao |
|---|---|---|
| Thêm GraphQL field nullable | Schema diff + slice test field | Consumer query test |
| Đổi GraphQL argument thành non-null | Breaking-change analysis | HTTP consumer compatibility |
| Sửa PricingService giảm giá | Unit service thật | Một GraphQL và một SOAP integration path |
| Đổi GraphQL endpoint URL | HTTP transport test | Gateway/ingress test |
| Đổi Content-Type/Accept policy | HTTP tests về negotiation | Legacy client compatibility |
| Đổi SOAP namespace | XSD/QName payload test | Generated client/WSDL compatibility |
| Đổi thứ tự element trong XSD sequence | XSD validation | Partner generated client test |
| Đổi SOAPAction | HTTP header + action mapping | Partner sandbox |
| Bật WS-Security signature | Interceptor test | Real HTTP/mTLS + cert test |
| Thêm MTOM | Attachment test | HTTP multipart/partner interoperability |
| Sửa GraphQL field-level security | Authorization negative tests | Real token/gateway integration |
| Chuyển repository sang R2DBC/JPA mới | Repository integration | Business HTTP path với DB test |

**Định nghĩa rõ lằn ranh:** `@GraphQlTest` không mở HTTP; `MockWebServiceClient` không mở HTTP; `@SpringBootTest(MOCK)` cũng không mở server socket. Chỉ tuyên bố “transport integration” khi request thực sự đi qua đường transport cần kiểm.

## 28. Negative tests: phần dễ bị thiếu nhất

Một suite chỉ kiểm happy path có thể xanh trước khi lỗi production xảy ra. Nhóm negative tests nên được ưu tiên theo rủi ro:

**GraphQL**

- Field/argument không có trong schema.
- `null` ở vị trí non-null.
- Invalid enum/scalar value hoặc variable coercion.
- User A đọc dữ liệu user B.
- Resolver error tạo partial data nhưng không lộ secrets.
- Query quá sâu/quá phức tạp; depth/complexity limit hoạt động.
- Mutation retry/idempotency.
- WebSocket subscription bị ngắt/cancel/reauth.

**SOAP**

- Payload root namespace sai.
- Thiếu mandatory XSD element, sai order, sai dữ liệu decimal/date.
- SOAP 1.1 gửi Content-Type của SOAP 1.2 hoặc ngược lại.
- SOAPAction sai.
- SOAP Fault mapping cho input/partner/internal failure.
- WS-Security signature/timestamp sai hoặc expired.
- Attachment thiếu hoặc Content-ID không khớp.
- XXE, entity expansion, oversized XML payload.
- Partner timeout và request retry có thể gây double effect.

Không phải mọi test trên đều chạy trong ví dụ. Chọn những nhánh mà **hợp đồng thật** và **risk register** của ứng dụng yêu cầu.

## 29. Debug khi contract test xanh nhưng HTTP integration đỏ

Cách điều tra theo lớp:

**Bước 1 — Client có gửi request tới endpoint đúng không?** Kiểm port, URL, HTTP method, path mapping và Content-Type; tránh hard-code 8080 trong `RANDOM_PORT`.

**Bước 2 — JSON/XML parse có thành công không?** Với GraphQL, kiểm JSON request và GraphQL document riêng; với SOAP, kiểm envelope, namespace URI, XML encoding và XML parser errors.

**Bước 3 — Framework handler đã được chọn chưa?** GraphQL xem schema mapping/resolver; SOAP xem `@PayloadRoot` và SOAPAction/WS-Addressing mappings.

**Bước 4 — Dịch vụ thật hay mock?** Nếu slice test có `@MockitoBean` mà HTTP test dùng service thật, chúng có thể khác behavior hợp lý; cần unit test service để phân biệt bug business.

**Bước 5 — Lỗi nằm ở body hay transport?** GraphQL HTTP 200 + `errors` là khác hoàn toàn với HTTP 404 do URL sai; SOAP Fault là khác HTTP proxy HTML 502.

**Bước 6 — Security/interceptors/filter chain?** Nếu production có auth, test context có đúng filter/interceptor không? Bài payload mock không mặc nhiên dùng JWT decoder hoặc mTLS.

**Bước 7 — Serialization/type?** GraphQL `Int` 32-bit, date/scalar custom, SOAP XSD order/namespace/decimal; kiểm schema và actual response tree.

**Bước 8 — External resources?** Network timeout, DB transaction, Kafka, partner sandbox, test data cleanup; không sửa expected cho khớp actual khi chưa xác nhận contract.

### 29.1. Bảng triệu chứng nhanh

| Triệu chứng | Root cause có thể | Điều cần kiểm |
|---|---|---|
| GraphQL response có `errors` nhưng status 200 | Execution/field error; media type legacy | `data`, `errors`, public error policy |
| GraphQL HTTP 404 | Route `/graphql` chưa map | Starter, endpoint property, HTTP path |
| GraphQL field test pass, totalVnd production sai | PricingService bị mock trong slice | Service real unit/full-context test |
| GraphQL schema xanh nhưng web UI fail | Field authorization/fragment/variables khác client | Consumer operations, auth |
| SOAP response có đúng 216000 nhưng client fail | Namespace/QName/XSD/action sai | XML-aware comparison, WSDL binding |
| SOAP payload mock pass, HTTP 415 | SOAP version/Content-Type sai | `text/xml` vs `application/soap+xml` |
| SOAP mock pass, transport 404 | Servlet mapping/path khác | `spring.webservices.path`, URL |
| SOAP HTTP 500 | SOAP Fault hoặc lỗi server/proxy | Parse envelope/Fault rồi xem server log |
| SOAP partner fail TLS | Truststore/certificate/hostname | mTLS integration với test cert |
| Schema test pass, WSDL client generate fail | Binding/operation/service address khác | Published WSDL và generated client |
| Test chỉ fail trên CI | Port/locale/timezone/shared DB/parallel | Isolation/timeout và deterministic fixtures |
| Thêm snapshot sửa hết test | Expected cập nhật từ actual không review | Review contract baseline và versioning |

## 30. Rủi ro của schema-driven snapshot quá chặt hoặc quá lỏng

**Quá chặt:**

- So JSON key order/whitespace như hợp đồng GraphQL.
- So raw SOAP XML prefix `q` thay vì namespace URI.
- Assert exact internal exception message từ framework hoặc số lượng internal metadata có thể thay.

**Quá lỏng:**

- Chỉ kiểm HTTP 200, bỏ GraphQL `errors`.
- Chỉ assert SOAP response có chứa chuỗi `216000`, bỏ QName/schema/fault.
- Dùng `JsonCompareMode.LENIENT` cho dữ liệu nhạy cảm nhưng không cấm extra fields.
- Chấp nhận mọi SOAP Fault rồi nói “đã xử lý lỗi”.
- Mock business service và đồng thời tuyên bố đã kiểm business rule.

**Trọng tâm đúng:** Strict ở **public contract và security invariants**, flexible ở **representations tương đương** khi hợp đồng không quy định byte-for-byte.

## 31. Versioning và hợp đồng đối tác

### GraphQL

Schema evolution thường ưu tiên thêm field mới, đánh dấu deprecation trước khi xóa và dựa trên telemetry/consumer operation registry. Thêm nullable field thường ít rủi ro hơn thêm required argument, nhưng vẫn phải kiểm performance/auth. Tránh đổi tên hoặc thay đổi scalar mà không có migration path.

### SOAP

SOAP WSDL/XSD thường gắn chặt generated clients. Thay namespace version, `minOccurs`, sequence hay binding có thể đòi regenerate client, và một phần runtime vẫn không tương thích dù build compile. Cần phát hành WSDL/XSD versioned, test generated clients, test old/new cùng lúc nếu cam kết compatibility.

### Cả hai

Không dùng “schema đã load” như bằng chứng mọi consumer chạy được. Test hợp đồng phải bám **operations/messages thực sự được consumer dùng**. Khi nhiều client độc lập, có thể dùng schema diff + consumer-driven contract tests, rồi vài transport/interoperability tests trên sandbox.

## 32. Bài tập thực hành theo rủi ro

### Bài A — GraphQL 200 với lỗi

API trả HTTP 200 nhưng body:

```json
{
  "data": {"quote": null},
  "errors": [{"message":"Not authorized","path":["quote"]}]
}
```

Nếu test chỉ `assertEquals(200,status)` thì có phát hiện user không được quyền truy cập? Hãy viết assertion `errors` và policy ẩn data đúng cho principal tương ứng. Giải thích vì sao status không đủ.

### Bài B — SOAP QName

Response thay prefix từ `q` sang `x` nhưng namespace URI vẫn `urn:demo:pricing:v1`. Một test so raw string fail. Đây có phải breaking change không? Vì sao `ResponseMatchers.payload`/XPath namespace-aware thường phù hợp hơn?

### Bài C — WSDL thay đổi

Partner generate client từ WSDL v1. Team chỉ thay XSD response fixture nhưng không test published WSDL. Có thể bỏ lọt lỗi gì? Hãy liệt kê operation name, binding, SOAPAction, service address và schema import cần kiểm.

### Bài D — Chọn cấp test

1. Tính giảm giá 10% sai.
2. HTTP header GraphQL `Content-Type` sai.
3. SOAP `@PayloadRoot` không match namespace.
4. Partner mTLS handshake fail.

Hãy chọn cấp test rẻ nhất phát hiện từng lỗi. **Đáp án định hướng:** service unit; real HTTP; MockWebServiceClient/XSD; transport/sandbox TLS với test certificate.

### Bài E — SOAP client adapter

Application dùng `WebServiceTemplate` gọi partner. Nên dùng `MockWebServiceClient` hay `MockWebServiceServer` để mô phỏng remote SOAP? Vì sao vẫn cần một sandbox transport test riêng?

### Bài F — GraphQL nullable vs non-null

Schema `Quote!` nhưng resolver trả null. Hãy mô tả null propagation, `errors` và cách xác minh không expose confidential exception details. Lưu ý status code phụ thuộc response media type/implementation, không cố định một giá trị khi chưa định contract.

### Bài G — SOAP Action

Test `@PayloadRoot` pass khi gửi SOAPAction sai. Vì sao? Hãy thêm action mapping/validation và negative test qua HTTP nếu WSDL yêu cầu action cụ thể.

### Bài H — Chi phí suite

Một nhóm muốn chuyển 500 GraphQL contract assertions thành `@SpringBootTest(RANDOM_PORT)` để “giống production”. Hãy nêu chi phí startup/state/concurrency và đề xuất giữ nhiều `@GraphQlTest`, vài transport smoke tests cùng contract schema/consumer queries. Cấp độ test nào phải giữ khi muốn bắt query DB lỗi?

### Bài I — Risk score

Đánh giá ba rủi ro với Impact/Likelihood/Escape 1–5: schema rename, auth leak, TLS certificate mismatch. Lập bảng ưu tiên và giải thích vì sao điểm số chỉ là công cụ hội thoại, không thay threat modeling hoặc yêu cầu compliance.

## 33. Checklist review trước khi chốt chiến lược test

- [ ] Mỗi test nêu rõ bug/rủi ro mà nó phải bắt.
- [ ] Tôi biết SUT và collaborator nào là real, mock, fake.
- [ ] Tôi phân biệt **contract** và **transport**; có thể cần cả hai.
- [ ] Với GraphQL, schema/arguments/field selection và error shape được bảo vệ.
- [ ] GraphQL `data` và `errors` được kiểm cùng nhau; không đồng nhất HTTP 200 với thành công nghiệp vụ.
- [ ] Đối với GraphQL HTTP, method/path/Content-Type/Accept theo media type/version của server đã được kiểm.
- [ ] Field/object-level authorization, query complexity và mutation idempotency có test nếu rủi ro cao.
- [ ] Với SOAP, XML root QName, namespace URI, XSD cardinality/sequence và response payload được kiểm.
- [ ] Published WSDL được test riêng nếu client generate từ WSDL.
- [ ] SOAP 1.1/1.2 envelope/media type, SOAPAction/WS-Addressing được kiểm đúng binding.
- [ ] SOAP Fault code/detail được kiểm, không chấp nhận generic HTML 500 như một SOAP contract hợp lệ.
- [ ] SOAP client adapter dùng `MockWebServiceServer`; SOAP endpoint server dùng `MockWebServiceClient` theo mục tiêu.
- [ ] Test payload mock không bị báo nhầm là test HTTP/TLS/mTLS production.
- [ ] WS-Security, cert, signature, timestamp, MTOM, attachment và gateway có test theo rủi ro.
- [ ] Domain/business tests chạy logic thật; không có test chỉ so dữ liệu do mock tự trả.
- [ ] HTTP real-server tests sử dụng random port, environment cô lập và không đụng production.
- [ ] Error messages không lộ stack trace, credential, SQL hoặc dữ liệu khách hàng.
- [ ] Test data deterministic, có cleanup và không phụ thuộc thứ tự chạy.
- [ ] Breaking-change workflow có schema diff + consumer contract tests khi có nhiều client.
- [ ] Tôi không tăng integration test count khi không tạo thêm khả năng phát hiện lỗi.
- [ ] Danh sách lỗi chưa được kiểm và ranh giới out-of-scope được công bố rõ.

**Ghi nhớ:** Chọn test **dựa vào rủi ro và khả năng quan sát**, không dựa vào tên công cụ. GraphQL schema/resolver có thể được bảo vệ rất tốt bởi `@GraphQlTest`; SOAP payload/QName/XSD có thể được bảo vệ bởi `MockWebServiceClient`. Nhưng khi rủi ro nằm ở HTTP media type, SOAPAction, servlet mapping, TLS hoặc interoperability, phải đưa request qua **transport thật tương ứng**. Và dù test transport xanh, logic nghiệp vụ chỉ được chứng minh nếu **code nghiệp vụ thật chạy và assertion kiểm đúng kết quả**.

### Tài liệu tham khảo

- Spring Boot 3.5 — Testing Spring GraphQL `@GraphQlTest` và HTTP testers: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring for GraphQL — GraphQlTester và các transport variants: https://docs.spring.io/spring-graphql/reference/testing.html
- Spring Boot 3.5 — Spring Web Services: https://docs.spring.io/spring-boot/3.5/reference/io/webservices.html
- Spring Web Services — MockWebServiceClient/MockWebServiceServer và XML assertions: https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/
- Spring Web Services — MockWebServiceClient API: https://docs.spring.io/spring-ws/docs/current/api/org/springframework/ws/test/server/MockWebServiceClient.html
- GraphQL — Serving over HTTP, data/errors/media types: https://graphql.org/learn/serving-over-http/
- GraphQL-over-HTTP draft specification (review version/status before treating as a deployed MUST): https://github.com/graphql/graphql-over-http/blob/main/spec/GraphQLOverHTTP.md
- W3C SOAP 1.2 Part 1: https://www.w3.org/TR/soap12-part1/
- W3C XML Schema 1.1: https://www.w3.org/TR/xmlschema11-1/
- RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110
