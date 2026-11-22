# Tài liệu API

API (Application Programming Interface) là hợp đồng mà một thành phần công bố để thành phần khác có thể sử dụng chức năng hoặc dữ liệu của nó. **Tài liệu API (API documentation)** giải thích hợp đồng đó: API làm được gì, gọi như thế nào, cần quyền gì, nhận dữ liệu gì, trả về kết quả nào và xử lý lỗi ra sao. Trong một hệ sinh thái DSL (Domain-Specific Language), tài liệu API còn mô tả cú pháp, kiểu dữ liệu, ràng buộc và semantics mà compiler, runtime hoặc dịch vụ được sinh ra cung cấp.

Tài liệu API tốt giúp người dùng tích hợp đúng ngay từ đầu, giảm trao đổi hỏi đáp, phát hiện thay đổi không tương thích và sử dụng API an toàn. Tài liệu cần phục vụ nhiều đối tượng: developer gọi API, người thiết kế hệ thống, người vận hành, người quản trị và cả công cụ tự động như SDK generator hoặc contract validator.

Khi API được mô tả bằng DSL, có thể dùng cùng một định nghĩa làm nguồn tạo contract, schema, tài liệu, client stub, server stub và test. Cách tiếp cận này giảm nguy cơ tài liệu lệch khỏi implementation, nhưng chỉ hiệu quả khi metadata đủ rõ, ví dụ có thể chạy/kiểm tra và pipeline cập nhật tài liệu cùng release của API.

## 1. Tài liệu API là gì?

Tài liệu API là tập thông tin mô tả cách một consumer tương tác với provider. Tài liệu có thể gồm trang hướng dẫn, reference theo từng operation, schema dữ liệu, ví dụ request/response, mô tả lỗi, chính sách xác thực, giới hạn sử dụng và hướng dẫn nâng cấp.

Ví dụ một API quản lý đơn hàng:

~~~http
GET    /orders/{orderId}
POST   /orders
PATCH  /orders/{orderId}
DELETE /orders/{orderId}
~~~

Chỉ liệt kê method và path chưa đủ. Người dùng cần biết orderId có kiểu gì, request body có trường nào, trường nào bắt buộc, response có cấu trúc gì, lỗi nào có thể xảy ra và quyền nào được yêu cầu.

### 1.1. Tài liệu giải thích contract

API contract xác định hành vi có thể quan sát được từ phía consumer. Tài liệu phải giải thích contract theo cách người dùng có thể dự đoán kết quả mà không cần đọc implementation.

### 1.2. Tài liệu không chỉ là danh sách endpoint

Một API có thể có nhiều khái niệm dùng chung: authentication, pagination, error envelope, rate limit, version header, idempotency và quy tắc dữ liệu. Những phần này cần được giải thích một lần ở cấp API hoặc service rồi liên kết từ từng operation.

### 1.3. Tài liệu và implementation

Implementation có thể thay đổi nội bộ miễn là contract công khai được giữ. Nếu hành vi quan sát được thay đổi, tài liệu và version contract cần được cập nhật. Không nên dùng tài liệu để hợp thức hóa hành vi thực tế không đúng contract.

## 2. Ai sử dụng tài liệu API?

Các nhóm người đọc có câu hỏi khác nhau:

| Đối tượng | Điều họ cần biết |
|---|---|
| API consumer/developer | Cách gọi, dữ liệu đầu vào/đầu ra và ví dụ |
| Solution architect | Khả năng, giới hạn, dependency và cách tích hợp |
| Frontend/mobile developer | Request/response, error handling, pagination và authentication |
| Backend developer | Contract, schema, semantics và compatibility |
| Operator/SRE | Timeout, retry, rate limit, observability và availability |
| Security engineer | Authentication, authorization, scopes và dữ liệu nhạy cảm |
| Product owner | Hành vi nghiệp vụ và các giới hạn được hỗ trợ |
| Tooling/compiler author | Metadata, schema và quy tắc sinh code |

### 2.1. Bắt đầu từ nhiệm vụ của người đọc

Người đọc thường không muốn biết implementation được tổ chức thành class nào. Họ muốn hoàn thành một tác vụ: tạo đơn hàng, lấy danh sách, cập nhật trạng thái hoặc nhận sự kiện. Tài liệu nên tổ chức theo nhiệm vụ và resource, đồng thời vẫn cung cấp reference chi tiết theo operation.

### 2.2. Phân biệt tutorial, guide và reference

- **Tutorial:** hướng dẫn từng bước để hoàn thành một tác vụ đầu tiên.
- **How-to guide:** giải quyết một nhu cầu cụ thể, ví dụ lọc danh sách hoặc xử lý webhook.
- **Reference:** mô tả đầy đủ operation, parameter, request, response, error và schema.
- **Conceptual guide:** giải thích mô hình, thuật ngữ và quyết định thiết kế.

Các dạng nội dung bổ sung cho nhau. Reference chính xác nhưng không thay thế tutorial cho người mới; tutorial dễ theo dõi nhưng không thể chứa mọi trường hợp.

## 3. Contract-first và documentation-first

Với contract-first, nhóm thiết kế API contract trước rồi triển khai provider và consumer dựa trên contract đó. Documentation-first mở rộng cách tiếp cận này bằng việc viết luồng sử dụng, ví dụ và mô tả trước khi implementation hoàn tất.

Quy trình khái quát:

~~~text
Use cases and domain model
          |
          v
API contract / DSL definition
          |
          +----------+
          |          |
          v          v
     Implementation  Documentation
          |          |
          +----+-----+
               |
               v
        Contract validation
               |
               v
        Release API and docs
~~~

### 3.1. Lợi ích

- Consumer có thể review API trước khi provider hoàn tất.
- Các nhóm phát hiện sớm tên field, kiểu dữ liệu hoặc semantics khó dùng.
- Server stub, client SDK và test có thể được sinh từ cùng contract.
- Tài liệu và implementation có một nguồn định nghĩa chung.
- Breaking changes có thể được phát hiện trong review và CI.

### 3.2. Những gì contract không thể tự quyết định

Contract có thể mô tả kiểu và response nhưng vẫn cần quyết định nghiệp vụ như trạng thái nào được phép chuyển, idempotency có hiệu lực bao lâu, dữ liệu có nhất quán ngay hay cuối cùng, hoặc khi nào một thao tác được xem là hoàn tất. Những semantics này phải được viết rõ.

### 3.3. Contract không phải implementation detail

Không nên công bố tên bảng, class nội bộ hoặc cấu trúc storage nếu consumer không cần phụ thuộc vào chúng. Contract nên giữ mức trừu tượng phù hợp với khả năng được hỗ trợ lâu dài.

## 4. Cấu trúc của bộ tài liệu API

Một bộ tài liệu API có thể được tổ chức thành các phần:

1. Overview: API giải quyết vấn đề gì và dành cho ai.
2. Getting started: đăng ký, credentials và request đầu tiên.
3. Authentication and authorization: cách xác thực và quyền.
4. Core concepts: resource, identifier, trạng thái và thuật ngữ.
5. API reference: operation, parameter, request và response.
6. Data models: schema, field, enum và constraint.
7. Errors: mã lỗi, cấu trúc và cách khắc phục.
8. Guides: pagination, filtering, webhooks, upload hoặc workflow.
9. Limits: rate limits, payload limits, timeout và quotas.
10. Versioning: compatibility, deprecation và migration.
11. Changelog: thay đổi theo release.
12. Support: status page, contact và quy trình báo lỗi.

### 4.1. Overview

Overview nên trả lời API phục vụ mục đích gì, có những nhóm chức năng nào, base URL hoặc giao thức nào được dùng, môi trường sandbox có sẵn không và người đọc nên bắt đầu từ đâu.

### 4.2. Getting started

Getting started nên đưa người đọc từ trạng thái chưa có cấu hình đến request thành công đầu tiên. Hướng dẫn cần có prerequisite, cách lấy credentials, cài SDK hoặc gửi HTTP request và cách nhận biết kết quả đúng.

### 4.3. API reference

Reference nên có cấu trúc nhất quán cho mọi operation để người đọc dễ so sánh và máy có thể sinh giao diện.

### 4.4. Guides và conceptual docs

Guide giải thích các quy trình xuyên nhiều endpoint. Conceptual docs giải thích những ý tưởng như idempotency, asynchronous operation, resource lifecycle hoặc consistency model.

## 5. Mô tả một API operation

Mỗi operation nên có một bộ thông tin tối thiểu:

| Thuộc tính | Nội dung |
|---|---|
| Operation ID | Định danh duy nhất, ổn định |
| Tên và summary | Hành động ngắn gọn |
| Description | Hành vi và semantics chi tiết |
| Method/route | HTTP method và path, hoặc RPC method |
| Parameters | Path, query, header, cookie hoặc input arguments |
| Request body | Schema, media type và requiredness |
| Responses | Status/result, headers và body schema |
| Authentication | Cơ chế và quyền cần thiết |
| Errors | Các lỗi có thể xảy ra |
| Examples | Request, response và tình huống lỗi |
| Limits | Timeout, payload size, rate limit hoặc pagination cap |
| Lifecycle | Stable, beta, deprecated hoặc sunset |

### 5.1. Operation ID

Operation ID cần duy nhất trong phạm vi API và ổn định qua các lần build nếu contract không thay đổi. SDK generator có thể dùng nó để tạo method name; test và telemetry có thể dùng nó làm định danh.

### 5.2. Summary và description

Summary nên ngắn, mô tả hành động. Description giải thích tác dụng, điều kiện, side effects, quyền, tính nhất quán và các trường hợp đặc biệt.

Ví dụ:

**Summary:** Tạo đơn hàng mới.

**Description:** Tạo một đơn hàng ở trạng thái PENDING. Request cần có ít nhất một dòng hàng. Operation hỗ trợ idempotency key để client retry an toàn trong khoảng thời gian được công bố.

### 5.3. Method và route

Với REST, method và route mô tả thao tác trên resource. Tài liệu cần nói rõ resource được định danh bằng path parameter nào và method có tạo, đọc, thay thế hay cập nhật một phần resource.

### 5.4. Side effects

Operation có thể tạo dữ liệu, gửi thông báo, trừ tiền hoặc kích hoạt workflow. Side effects phải được mô tả để consumer không giả định một request chỉ thay đổi response.

### 5.5. Đồng bộ và bất đồng bộ

Một operation có thể hoàn tất ngay hoặc trả về job/resource để xử lý nền. Nếu bất đồng bộ, cần mô tả cách kiểm tra trạng thái, event/webhook hoàn tất và hành vi khi job thất bại.

## 6. Mô tả parameters

Parameters có thể nằm trong path, query, header, cookie hoặc RPC input. Mỗi parameter nên có tên, vị trí, kiểu, requiredness, default, constraints và ý nghĩa.

Ví dụ:

| Parameter | Vị trí | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|---|
| orderId | Path | OrderId | Có | Định danh đơn hàng |
| expand | Query | String[] | Không | Các quan hệ cần mở rộng |
| If-Match | Header | ETag | Không | Điều kiện cập nhật theo version |
| Idempotency-Key | Header | String | Theo policy | Khóa nhận diện thao tác retry |

### 6.1. Path parameters

Path parameter thường định danh resource hoặc phần tử con. Cần mô tả format, phạm vi duy nhất, case sensitivity và cách xử lý ID không tồn tại.

### 6.2. Query parameters

Query parameters thường điều khiển filter, sort, pagination, projection hoặc expansion. Cần chỉ rõ cú pháp, kiểu, default, giới hạn và cách kết hợp nhiều giá trị.

### 6.3. Header parameters

Header có thể điều khiển content negotiation, conditional requests, tracing, idempotency hoặc version. Tài liệu cần phân biệt header do client cung cấp và header do server trả về.

### 6.4. Required, optional và default

Không nên chỉ ghi “optional”. Cần giải thích khi bỏ qua parameter thì server dùng default nào, không lọc, hay chọn hành vi khác. Nếu default thay đổi giữa các version, đó có thể là breaking change về semantics.

### 6.5. Encoding và format

Với date, timestamp, decimal, binary hoặc enum, tài liệu cần nêu format chính xác. Ví dụ timestamp dùng ISO 8601 UTC hay cho phép offset; decimal dùng JSON number hay string để giữ precision.

## 7. Request body và data schema

Request schema mô tả cấu trúc dữ liệu mà consumer gửi. Cần phân biệt object, array, scalar, enum, union và reference đến schema dùng chung.

Ví dụ request tạo đơn hàng:

~~~json
{
  "customerId": "cus-204",
  "items": [
    {
      "productId": "prd-18",
      "quantity": 2
    }
  ],
  "currency": "VND"
}
~~~

### 7.1. Field descriptions

Mỗi field nên có mô tả ngắn, kiểu, requiredness, constraints, format và ví dụ. Tên field tự nó không đủ để người dùng biết ý nghĩa nghiệp vụ.

### 7.2. Required và optional fields

Required nghĩa là consumer phải gửi field theo contract. Optional nghĩa là có thể bỏ qua. Cần phân biệt optional với nullable: field có thể không xuất hiện, có thể xuất hiện với null, hoặc cả hai tùy schema.

### 7.3. Nullability

Ví dụ middleName có thể không bắt buộc nhưng nếu được gửi thì phải là string; hoặc có thể gửi null để xóa giá trị. Hai semantics khác nhau và cần mô tả rõ.

### 7.4. Constraints

Constraints có thể gồm min/max, length, pattern, format, uniqueness, enum values và quan hệ giữa các field. Nên cung cấp cả quy tắc máy đọc được lẫn mô tả cho con người.

### 7.5. Reusable schemas

Các kiểu như Money, Address, Error và Page<T> có thể dùng lại giữa nhiều operation. Tài liệu nên có trang schema riêng và liên kết từ từng request/response để tránh mô tả trùng lặp.

### 7.6. Composition

Schema có thể kế thừa hoặc kết hợp bằng các cấu trúc như all-of, one-of hoặc discriminated union. Tài liệu phải giải thích cách xác định biến thể cụ thể, đặc biệt khi payload chứa nhiều loại resource.

## 8. Response và status

Response documentation cần mô tả các kết quả thành công và thất bại có thể quan sát được.

Ví dụ response tạo đơn hàng:

~~~json
{
  "id": "ord-901",
  "status": "PENDING",
  "currency": "VND",
  "total": {
    "amount": "250000",
    "currency": "VND"
  },
  "createdAt": "2026-11-15T03:15:00Z"
}
~~~

### 8.1. Success responses

Với mỗi response, cần mô tả status code hoặc result type, schema, headers, điều kiện trả về và các field có thể vắng mặt.

### 8.2. Partial responses

Một API có thể trả dữ liệu rút gọn, field được mở rộng tùy chọn hoặc kết quả từng phần. Tài liệu cần giải thích field nào có thể thiếu và cách nhận biết response chưa đầy đủ.

### 8.3. Empty responses

Các thao tác như delete hoặc update có thể trả response không có body. Cần nêu rõ status code, headers và việc client có nên đọc body hay không.

### 8.4. Asynchronous responses

Nếu operation trả 202 Accepted, tài liệu cần mô tả job ID, URL kiểm tra trạng thái, trạng thái terminal, retry polling và event/webhook nếu có.

### 8.5. Consistency

Sau khi tạo hoặc cập nhật resource, API có thể trả trạng thái đã commit nhưng các read replica hoặc search index chưa cập nhật. Nếu có eventual consistency, cần mô tả thời gian hoặc điều kiện quan sát được dữ liệu mới.

## 9. Error documentation

Consumer cần biết lỗi có thể xảy ra và cách xử lý. Tài liệu nên phân biệt lỗi request, xác thực, quyền, conflict, giới hạn, lỗi nghiệp vụ và lỗi hệ thống.

Ví dụ error response:

~~~json
{
  "error": {
    "code": "ORDER_NOT_FOUND",
    "message": "The requested order does not exist.",
    "requestId": "req-71a2",
    "details": {
      "orderId": "ord-901"
    }
  }
}
~~~

### 9.1. Error code ổn định

Client nên dựa vào machine-readable code thay vì phân tích message tự do. Message có thể được cải thiện hoặc dịch mà không làm thay đổi contract.

### 9.2. HTTP status và domain error

HTTP status thể hiện nhóm kết quả giao thức; error code mô tả nguyên nhân nghiệp vụ cụ thể. Ví dụ nhiều lỗi domain có thể dùng cùng status 409 Conflict nhưng có code khác nhau.

### 9.3. Retryability

Tài liệu nên cho biết lỗi nào có thể retry, lỗi nào cần sửa request và lỗi nào cần chờ hoặc liên hệ support. Không nên khuyên retry mọi lỗi 5xx hoặc mọi timeout mà không có idempotency.

### 9.4. Validation errors

Validation error nên chỉ rõ field hoặc path không hợp lệ, constraint mong đợi và giá trị nào bị từ chối nếu việc hiển thị giá trị đó an toàn.

### 9.5. Request ID

Request ID giúp support và operator tìm log phía server. Tài liệu cần nói client lấy ID từ response header hay body và cung cấp nó khi báo lỗi.

## 10. Authentication và authorization

Tài liệu API phải mô tả cách xác thực request và quyền cần thiết cho từng operation.

Các cơ chế thường gặp:

- API key.
- Bearer token/OAuth 2.0.
- OpenID Connect.
- Mutual TLS.
- Service account hoặc workload identity.

### 10.1. Authentication

Authentication xác định client hoặc người dùng là ai. Tài liệu cần chỉ rõ cách lấy credential, nơi truyền credential, thời hạn, cách refresh và cách thu hồi.

### 10.2. Authorization

Authorization xác định principal được phép làm gì. Có thể dùng scopes, roles, resource ownership hoặc policy. Một operation nên liệt kê scopes hoặc quyền cần thiết.

### 10.3. Ví dụ request có bearer token

~~~http
GET /v1/orders/ord-901 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

Placeholder phải được đánh dấu rõ và không dùng token thật trong tài liệu hoặc test fixture.

### 10.4. Credential safety

Không đưa secret thật vào ví dụ, screenshot, log hoặc URL query. Hướng dẫn cần khuyên dùng secret manager hoặc biến môi trường ở client/server theo mô hình phù hợp.

### 10.5. Sandbox credentials

Nếu có sandbox, cần phân biệt credential sandbox với production, base URL, dữ liệu giả lập và giới hạn của môi trường thử nghiệm.

## 11. Rate limits, timeout và retry

API có thể giới hạn số request, kích thước payload, thời gian xử lý và concurrency.

### 11.1. Rate limits

Tài liệu cần mô tả giới hạn theo principal, API key, tenant hoặc endpoint; cửa sổ thời gian; phản hồi khi vượt ngưỡng; và header cung cấp quota còn lại nếu có.

### 11.2. Retry policy

Client nên retry với exponential backoff và jitter khi lỗi được xác định là tạm thời. Với thao tác tạo hoặc thanh toán, cần idempotency key để tránh tạo hiệu ứng trùng.

### 11.3. Timeout

Phân biệt client timeout, server processing timeout và thời hạn của một asynchronous job. Nếu client timeout, server có thể vẫn hoàn tất thao tác; tài liệu cần chỉ cách kiểm tra trạng thái trước khi gửi lại.

### 11.4. Idempotency

Idempotency key cho phép nhận diện các lần retry của cùng một thao tác. Tài liệu cần mô tả phạm vi key, thời gian lưu, hành vi khi cùng key nhưng payload khác và response trả về khi request được lặp.

### 11.5. Pagination limits

Với API trả danh sách, cần nêu page size mặc định/tối đa, offset hay cursor, cách tiếp tục trang và ý nghĩa total count. Có thể liên kết đến guide pagination dùng chung.

## 12. Webhooks và event APIs

Không phải API nào cũng được consumer gọi trực tiếp. Webhook hoặc event API cho phép provider gửi thông báo khi một sự kiện xảy ra.

Tài liệu webhook cần mô tả:

- Event types và payload schema.
- Cách đăng ký endpoint nhận event.
- Cách xác thực chữ ký hoặc nguồn gửi.
- Retry và thời gian chờ acknowledgement.
- Thứ tự, duplicate delivery và idempotency.
- Cách replay hoặc lấy lại event bị bỏ lỡ.
- Versioning và deprecation của event schema.

### 12.1. Webhook signature

Provider có thể ký payload bằng secret để consumer xác minh nguồn và tính toàn vẹn. Tài liệu cần chỉ rõ thuật toán, header, canonicalization và cách chống replay.

### 12.2. Duplicate delivery

Webhook thường có thể được gửi lại nếu provider không nhận acknowledgement. Consumer nên deduplicate theo event ID và xử lý idempotent.

### 12.3. Acknowledgement

Tài liệu cần nói status code nào được xem là đã nhận thành công, thời gian phản hồi tối đa và liệu provider có retry khi endpoint trả 4xx hoặc 5xx không.

### 12.4. Event schema

Event API cần tài liệu riêng cho event type, version, envelope, correlation và causation metadata. Không nên mô tả webhook như một REST callback đơn giản nếu semantics có ordering hoặc delivery guarantee phức tạp.

## 13. API theo phong cách REST, RPC và GraphQL

Tài liệu phải phản ánh mô hình giao tiếp thực tế.

### 13.1. REST

REST-style API thường tổ chức quanh resource và HTTP method. Tài liệu cần mô tả resource identity, representation, status code, headers, pagination, filtering và conditional requests.

### 13.2. RPC

RPC mô tả operation hoặc method. Tài liệu cần nhấn mạnh input/output type, error model, timeout, streaming và semantics của lời gọi.

### 13.3. GraphQL

GraphQL documentation thường xoay quanh schema types, fields, queries, mutations, subscriptions, arguments và directives. Tài liệu cần giải thích nullability, resolver behavior, pagination convention và authorization ở cấp field nếu có.

### 13.4. Event-driven APIs

Event-driven contract mô tả channel/topic, producer, consumer, event schema, delivery và ordering. Consumer cần biết event có thể đến trễ, trùng hoặc ngoài thứ tự.

### 13.5. Không ép mọi API vào một khuôn

REST, RPC, GraphQL và event API có semantics khác nhau. Có thể dùng cùng nguyên tắc về schema, examples, security và versioning, nhưng cấu trúc reference nên phù hợp với giao thức.

## 14. Tài liệu hóa dữ liệu và domain model

Trong DSL API và dữ liệu, schema thường là phần trung tâm của tài liệu. Kiểu dữ liệu nên được mô tả ở mức người dùng hiểu được, không chỉ là kiểu nền tảng.

Ví dụ:

~~~text
type Money {
    amount: Decimal
    currency: CurrencyCode
}

type OrderStatus =
    PENDING | PAID | SHIPPED | CANCELLED
~~~

Tài liệu nên giải thích:

- amount có precision/scale và quy ước làm tròn nào.
- currency dùng mã ISO hay tập giá trị riêng.
- OrderStatus có thể chuyển qua lại theo quy tắc nào.
- Trường nào được client ghi và trường nào chỉ server quản lý.
- Trường nào có thể null hoặc không xuất hiện.

### 14.1. Identifier

ID nên có format, phạm vi duy nhất và semantics rõ. Không nên giả định ID có thể được tăng tuần tự hoặc chứa thông tin nghiệp vụ nếu contract không cam kết.

### 14.2. Enum

Enum cần mô tả ý nghĩa từng giá trị và hành vi khi server bổ sung giá trị mới. Client nên xử lý unknown enum theo cách an toàn nếu API cho phép mở rộng.

### 14.3. Date/time

Phân biệt date-only, local date-time và instant. Nêu timezone, format, precision và cách xử lý daylight saving nếu có.

### 14.4. Decimal và money

Với tiền tệ, mô tả currency, precision, rounding và cách biểu diễn JSON. Nếu dùng string cho decimal, cần giải thích lý do và format.

### 14.5. Binary và file

Upload/download cần mô tả content type, kích thước tối đa, streaming, checksum, multipart và thời hạn của URL tạm nếu có.

## 15. Ví dụ request/response có thể chạy

Ví dụ là một trong những phần có giá trị nhất của tài liệu API. Ví dụ tốt cho thấy cả cú pháp lẫn hành vi.

### 15.1. Request với curl

~~~bash
curl --request POST \
  --url https://api.example.test/v1/orders \
  --header "Authorization: Bearer $API_TOKEN" \
  --header "Content-Type: application/json" \
  --header "Idempotency-Key: order-create-2026-001" \
  --data '{
    "customerId": "cus-204",
    "items": [
      {"productId": "prd-18", "quantity": 2}
    ],
    "currency": "VND"
  }'
~~~

Ví dụ cần dùng domain giả lập và placeholder cho credential. Nếu copy/paste được, người đọc nên biết cần thay base URL, token và ID nào.

### 15.2. Response thành công

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /v1/orders/ord-901

{
  "id": "ord-901",
  "status": "PENDING",
  "createdAt": "2026-11-15T03:15:00Z"
}
~~~

### 15.3. Response lỗi

~~~http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "error": {
    "code": "INVALID_QUANTITY",
    "message": "Quantity must be greater than zero.",
    "requestId": "req-71a2"
  }
}
~~~

### 15.4. Ví dụ tối thiểu và ví dụ đầy đủ

Ví dụ tối thiểu giúp người mới bắt đầu nhanh. Ví dụ đầy đủ nên thể hiện optional fields, pagination, error handling hoặc các trường hợp phức tạp. Cả hai cần được gắn nhãn rõ.

### 15.5. Example values và fake data

Ví dụ nên dùng dữ liệu giả lập, nhất quán giữa các trang và không chứa dữ liệu cá nhân thật. Nếu có format đặc biệt, ví dụ cần tuân schema để có thể dùng trong contract tests.

## 16. Tạo tài liệu từ DSL

Khi API contract được khai báo bằng DSL, compiler hoặc documentation generator có thể sinh reference tự động.

Ví dụ cú pháp minh họa:

~~~text
@apiGroup("Orders")
@summary("Create an order")
@description("Creates a new order in PENDING state.")
@security(scope = "orders.write")
@idempotency(required = true, ttl = 24h)
operation createOrder {
    method POST
    path "/v1/orders"
    request CreateOrderRequest
    response 201 Order
    errors [400, 401, 403, 409, 422]
}
~~~

Annotation cung cấp metadata cho documentation generator. Grammar và metamodel có thể kiểm tra tên schema, response type, operation ID và các tham chiếu.

### 16.1. Documentation comments

Có thể gắn mô tả vào operation, type hoặc field bằng comment có cấu trúc hoặc annotation. Cần xác định comment nào được giữ trong metamodel và cách nối với generated docs.

### 16.2. Metadata có kiểu

Các thuộc tính như deprecated, since, security, rateLimit và example nên có kiểu rõ thay vì chỉ là chuỗi tự do. Compiler có thể validate và generator có thể render thống nhất.

### 16.3. Source of truth

Nên xác định rõ contract DSL hay implementation là nguồn sự thật. Nếu contract-first, implementation phải được kiểm tra phù hợp contract. Nếu reverse-generate từ code, cần cơ chế xử lý metadata không thể suy ra từ source.

### 16.4. Không để annotation thay thế giải thích

Metadata máy đọc được có thể sinh bảng và schema, nhưng các semantics dài như eventual consistency, side effects hoặc retry behavior vẫn cần prose và ví dụ.

## 17. OpenAPI, AsyncAPI và các định dạng trao đổi

Các định dạng mô tả máy đọc được giúp chia sẻ API contract với công cụ khác.

### 17.1. OpenAPI

OpenAPI thường được dùng để mô tả HTTP APIs: paths, operations, parameters, request bodies, responses, schemas, security schemes và metadata. Từ một contract DSL, generator có thể tạo OpenAPI document để dùng với documentation UI, client generator và contract tooling.

### 17.2. AsyncAPI

AsyncAPI mô tả API bất đồng bộ như message channels, operations, servers, message schemas và security. Nó phù hợp với event/message-driven contract hơn việc cố biểu diễn mọi thứ thành HTTP endpoint.

### 17.3. Schema formats

JSON Schema hoặc các định dạng schema tương đương có thể biểu diễn object, properties, constraints và composition. Cần xác định subset và semantics khi chuyển từ DSL sang schema format.

### 17.4. Mapping không phải lúc nào cũng một-một

DSL có thể có kiểu miền hoặc semantics không biểu diễn trực tiếp trong OpenAPI/AsyncAPI. Generator có thể cần extension metadata, description bổ sung hoặc báo giới hạn. Không nên âm thầm bỏ mất constraint quan trọng.

### 17.5. Kiểm tra generated contract

Generated OpenAPI/AsyncAPI cần được parse và validate bằng tool phù hợp. Có thể so sánh contract mới với contract đã phát hành để phát hiện breaking changes.

## 18. Tài liệu hóa API trong IDE và developer portal

Tài liệu có thể được trình bày qua website, IDE, command line hoặc portal nội bộ.

### 18.1. Reference site

Reference site nên hỗ trợ tìm kiếm theo operation, schema, tag và error code. Navigation cần cho phép đi từ endpoint đến schema, từ schema đến operation sử dụng và ngược lại.

### 18.2. IDE integration

IDE có thể hiển thị documentation khi hover symbol hoặc gợi ý completion. Nếu DSL là nguồn contract, language server có thể cung cấp description, type, examples và deprecation metadata ngay trong editor.

### 18.3. Developer portal

Portal có thể tập hợp API catalog, owner, environment, access request, status, changelog và documentation. Cần phân quyền nội dung nội bộ và nội dung công khai.

### 18.4. Try it out

Interactive console cho phép người đọc gửi request mẫu. Nó cần sandbox, dữ liệu giả, credential giới hạn và cảnh báo rõ nếu thao tác có side effect. Không nên mặc định trỏ console vào production.

### 18.5. Search và deep links

Mỗi operation và schema nên có URL ổn định để chia sẻ trong issue, code review và support ticket. Search cần hiểu tên miền và alias phổ biến.

## 19. Docs as Code

Docs as Code là cách quản lý tài liệu bằng quy trình tương tự source code: lưu trong version control, review qua pull request, chạy validation trong CI và phát hành theo version.

### 19.1. Lợi ích

- Thay đổi tài liệu có lịch sử và reviewer.
- Tài liệu có thể được version cùng API.
- Link, example và generated reference có thể được kiểm tra tự động.
- Có thể review contract và prose trong cùng pull request.
- Dễ tạo release notes từ thay đổi đã merge.

### 19.2. Tổ chức repository

Có thể lưu docs trong cùng repository với DSL/API contract hoặc repository riêng. Cùng repository giúp đồng bộ release; repository riêng có thể phù hợp khi nhiều API chia sẻ một portal.

### 19.3. Review documentation changes

Reviewer cần xem nội dung thay đổi có phản ánh đúng behavior không, ví dụ có chạy được không, breaking changes đã nêu chưa và security guidance có đúng không.

### 19.4. Generated và handwritten content

Generated reference nên được đánh dấu để không sửa tay rồi bị ghi đè. Prose hướng dẫn có thể được viết thủ công, nhưng cần liên kết đến operation/schema chính xác.

## 20. Versioning và compatibility của tài liệu

Tài liệu cần phản ánh version API mà consumer đang sử dụng.

### 20.1. Versioned docs

Có thể cung cấp tài liệu cho các version đang được hỗ trợ, ví dụ /docs/v1 và /docs/v2. Trang mặc định nên chỉ rõ version mới nhất và trạng thái support của version cũ.

### 20.2. Breaking changes

Các thay đổi có thể phá consumer:

- Xóa operation hoặc field.
- Đổi tên hoặc đổi kiểu field.
- Làm optional thành required.
- Thay semantics hoặc side effects.
- Thay error code hoặc status behavior.
- Thu hẹp giá trị enum được chấp nhận.
- Thay default hoặc pagination behavior.

Không phải mọi thay đổi thêm mới đều an toàn: client có thể không xử lý enum mới hoặc field mới nếu parser/SDK quá nghiêm ngặt.

### 20.3. Deprecation

Khi một operation hoặc field sắp bị loại bỏ, tài liệu cần nêu trạng thái deprecated, phiên bản bắt đầu deprecate, phương án thay thế và thời điểm sunset nếu đã xác định.

### 20.4. Migration guide

Migration guide nên đưa ví dụ trước/sau, thay đổi code, cách chuyển dữ liệu và các bước triển khai theo thứ tự. Với API nhiều service, cần nói rõ giai đoạn tương thích đồng thời giữa consumer cũ và provider mới.

### 20.5. Changelog

Changelog nên phân loại Added, Changed, Deprecated, Removed, Fixed và Security. Mỗi mục cần liên kết đến operation hoặc schema liên quan.

## 21. Kiểm thử tài liệu API

Tài liệu cần được kiểm tra như một phần của sản phẩm.

Các kiểm tra thường dùng:

1. Contract DSL parse và validate.
2. Generated OpenAPI/AsyncAPI/schema hợp lệ.
3. Operation ID và schema references không trùng hoặc dangling.
4. Request/response examples khớp schema.
5. Code samples có thể chạy trong sandbox hoặc test harness.
6. Link nội bộ và external references hoạt động.
7. Error codes trong docs khớp implementation contract.
8. Authentication scopes được mô tả đầy đủ.
9. Breaking changes được phát hiện so với release trước.
10. Tài liệu versioned trỏ đúng API version.
11. Secret hoặc dữ liệu nhạy cảm không xuất hiện trong examples.
12. Generated docs có thể build lặp lại.

### 21.1. Example validation

Ví dụ JSON có thể được parse và validate với schema. Code sample có thể chạy trong CI bằng test credential giả. Điều này giúp tránh ví dụ cũ hoặc sai cú pháp.

### 21.2. Contract tests

Contract tests xác nhận provider thực hiện response phù hợp với contract và consumer kỳ vọng. Khi API được sinh từ DSL, cùng schema có thể được dùng để tạo test fixture.

### 21.3. Link checking

Link nội bộ cần được kiểm tra khi đổi tên operation hoặc version. Deep links ổn định giúp tránh tài liệu tham chiếu bị hỏng.

### 21.4. Accessibility

Trang docs nên có heading hierarchy, bảng dễ đọc, code block có ngôn ngữ, link có nhãn mô tả và giao diện dùng được bằng bàn phím/screen reader. Nội dung không nên chỉ truyền đạt thông tin bằng màu sắc.

## 22. Chất lượng ví dụ và hướng dẫn

Ví dụ tốt cần:

- Thể hiện một tác vụ thực tế.
- Dùng dữ liệu giả nhưng hợp lệ.
- Có đủ headers và parameters cần thiết.
- Cho thấy response thành công và lỗi quan trọng.
- Nêu rõ giá trị cần thay thế.
- Không chứa credential thật.
- Nhất quán với schema và version.

### 22.1. Từ đơn giản đến đầy đủ

Nên bắt đầu với ví dụ tối thiểu để người mới hiểu cấu trúc, sau đó mở rộng với filter, pagination, retry hoặc error handling.

### 22.2. Giải thích vì sao

Không chỉ đưa code. Hãy giải thích tại sao cần idempotency key, vì sao một field bắt buộc hoặc khi nào nên dùng cursor thay vì offset.

### 22.3. Nêu rõ placeholder

Placeholder như <access-token>, YOUR_API_KEY hoặc $API_BASE_URL cần được đánh dấu. Tránh ví dụ trông như giá trị thật nhưng không thể sử dụng.

### 22.4. Ví dụ lỗi

Ví dụ lỗi giúp người dùng thiết kế error handling. Nên có lỗi validation, authentication, authorization, not found, conflict, rate limit và transient failure khi phù hợp.

## 23. Governance và ownership

Tài liệu API cần có người chịu trách nhiệm. Nếu không, operation cũ có thể không được cập nhật khi implementation đổi.

### 23.1. API owner

Mỗi API hoặc domain nên có owner chịu trách nhiệm contract, tài liệu, versioning và deprecation. Owner cần được ghi trong catalog hoặc metadata.

### 23.2. Review policy

Thay đổi public contract cần review từ owner và các consumer liên quan. Thay đổi bảo mật có thể cần security review; thay đổi breaking cần migration plan.

### 23.3. Publication policy

Không phải mọi API đều công khai. Portal có thể phân loại public, partner, internal và experimental; mỗi loại có yêu cầu review và access khác nhau.

### 23.4. Support lifecycle

Tài liệu cần thể hiện API đang experimental, beta, stable, deprecated hay sunset. Mỗi trạng thái nên có ý nghĩa và tiêu chí chuyển trạng thái rõ ràng.

## 24. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ liệt kê endpoint | Người dùng không biết schema và semantics | Mô tả request, response, errors và examples |
| Tài liệu viết sau implementation | Contract và docs dễ lệch nhau | Dùng contract-first hoặc docs-as-code |
| Mô tả field bằng tên בלבד | Không hiểu ý nghĩa nghiệp vụ | Viết type, constraints, nullability và examples |
| Không phân biệt optional/null | Consumer gửi hoặc đọc dữ liệu sai | Nêu rõ absent, null và default |
| Không có error catalog | Client không biết xử lý lỗi | Dùng error code ổn định và retry guidance |
| Ví dụ không chạy được | Người dùng mất thời gian sửa ví dụ | Validate examples trong CI |
| Đưa secret thật vào sample | Credential có thể bị lộ | Dùng placeholder và sandbox credentials |
| Không nói về rate limit/timeout | Client retry sai hoặc gây quá tải | Công bố limits và retry semantics |
| Không version hóa docs | Người dùng version cũ đọc nhầm contract mới | Duy trì docs theo API version |
| Generated docs bỏ mất semantics | Tài liệu máy sinh nhưng thiếu thông tin quan trọng | Bổ sung prose và metadata có kiểu |
| Không có owner | Docs lỗi thời, không ai cập nhật | Gán ownership và review policy |
| Không kiểm tra breaking changes | Consumer bị hỏng sau release | Contract diff và compatibility gates |

## 25. Ví dụ tổng hợp: khai báo API và tài liệu bằng DSL

Ví dụ minh họa một API resource:

~~~text
@api(version = "v1")
@tag("Orders")
service OrderApi {

    @summary("Get an order")
    @description("Returns an order visible to the authenticated caller.")
    @security(scope = "orders.read")
    operation getOrder {
        method GET
        path "/orders/{orderId}"
        pathParam orderId: OrderId required
        response 200 Order
        errors [401, 403, 404]
    }

    @summary("Create an order")
    @description("Creates a new order in PENDING state.")
    @security(scope = "orders.write")
    @idempotency(required = true, ttl = 24h)
    operation createOrder {
        method POST
        path "/orders"
        request CreateOrderRequest
        response 201 Order
        errors [400, 401, 403, 409, 422]
    }
}

type CreateOrderRequest {
    customerId: CustomerId required
    items: OrderItem[] minItems(1) required
    currency: CurrencyCode required
}

type Order {
    id: OrderId
    status: OrderStatus
    total: Money
    createdAt: Instant
}
~~~

Documentation generator có thể tạo trang service, trang từng operation, schema reference, security summary và example skeleton từ metadata. Người viết bổ sung prose về semantics, retry và consistency.

### 25.1. Trang operation được sinh

Trang createOrder có thể hiển thị method/path, scope orders.write, idempotency requirement, request schema, response 201, error codes và ví dụ curl/JSON.

### 25.2. Trang schema được sinh

Trang CreateOrderRequest giải thích customerId, items, currency, requiredness và minItems(1). Trang Order giải thích ID, status, total và createdAt.

### 25.3. Kiểm tra contract

CI có thể parse DSL, sinh OpenAPI, validate schema và examples, sau đó so sánh với contract version trước. Nếu operation bị xóa hoặc field requiredness thay đổi, pipeline yêu cầu review breaking change.

## 26. Checklist nội dung cho một operation

Trước khi công bố một operation, tài liệu nên trả lời được:

- Operation giải quyết tác vụ nào?
- Method/path hoặc RPC name là gì?
- Parameter nào bắt buộc, kiểu và format ra sao?
- Request body có schema và example hợp lệ không?
- Response thành công gồm status, headers và body nào?
- Có asynchronous behavior hoặc side effects không?
- Những error code nào có thể xảy ra?
- Lỗi nào retry được và có cần idempotency key không?
- Authentication và scope nào được yêu cầu?
- Rate limit, timeout và payload limit là gì?
- Pagination/filter/sort semantics có được mô tả không?
- Version, lifecycle và deprecation status là gì?
- Có link đến schema, guide và changelog không?

Checklist này giúp giữ cấu trúc reference nhất quán; nó không thay thế review semantics và trải nghiệm người đọc.

## 27. Nguyên tắc thiết kế tài liệu API

Khi xây dựng tài liệu cho DSL/API, có thể áp dụng các nguyên tắc sau:

1. **Viết theo nhiệm vụ của người dùng.** Kết hợp tutorial, guide, concept và reference.
2. **Xem contract là nguồn định nghĩa.** Tài liệu phải khớp hành vi được hỗ trợ.
3. **Mô tả đầy đủ request và response.** Bao gồm kiểu, format, requiredness, nullability và constraints.
4. **Giải thích semantics nghiệp vụ.** Nêu side effects, consistency, state transitions và asynchronous behavior.
5. **Dùng error code ổn định.** Phân biệt lỗi cần sửa, lỗi retry và lỗi quyền.
6. **Công bố security rõ ràng.** Authentication, scopes, credential handling và dữ liệu nhạy cảm.
7. **Cung cấp ví dụ có thể kiểm tra.** Request, response, error và code sample phải khớp contract.
8. **Tự động sinh phần có cấu trúc.** Dùng DSL metadata/schema để tạo reference và machine-readable specs.
9. **Bổ sung prose cho semantics.** Không trông chờ generator suy ra mọi quy tắc nghiệp vụ.
10. **Version hóa tài liệu.** Gắn docs với API release và migration guide.
11. **Kiểm thử docs trong CI.** Validate schema, examples, links và compatibility.
12. **Gán owner và review.** Mỗi API cần người chịu trách nhiệm duy trì.
13. **Bảo vệ môi trường thử nghiệm.** Dùng sandbox và credential giả; không chạy ví dụ nguy hiểm trên production.
14. **Giữ navigation và accessibility tốt.** Search, deep links, heading và code samples phải dễ sử dụng.

## 28. Kết luận

Tài liệu API giải thích hợp đồng giữa provider và consumer: operation làm gì, nhận dữ liệu nào, trả kết quả nào, yêu cầu quyền gì và xử lý lỗi ra sao. Một bộ tài liệu hữu ích kết hợp overview, getting started, conceptual guides, operation reference, data schemas, examples, security, limits, versioning và changelog.

Trong hệ sinh thái DSL, contract có thể là nguồn tạo tài liệu, schema, SDK và test. Cách làm này giúp giảm sai lệch nhưng không loại bỏ nhu cầu giải thích semantics nghiệp vụ bằng prose và ví dụ. Tài liệu cần được version hóa, review, kiểm thử và phát hành cùng API; generated content phải được kiểm tra và bổ sung khi metadata không biểu đạt hết hành vi.

Khi tài liệu được xem là một phần của API contract và có owner rõ ràng, consumer có thể tích hợp an toàn hơn, nhóm phát triển phát hiện breaking changes sớm hơn và API có vòng đời dễ quản lý hơn.
