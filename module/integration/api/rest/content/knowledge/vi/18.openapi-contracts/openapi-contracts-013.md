# Lint, phát hiện thay đổi phá vỡ tương thích và kiểm tra trong CI

## 1. Tại sao cần quality gate cho hợp đồng OpenAPI?

Một REST API được nhiều client sử dụng có thể hỏng dù server biên dịch và chạy thành công: endpoint đổi mã 201 sang 200, một trường JSON biến mất, tham số phân trang được đổi tên hoặc scope xác thực bị siết mà client cũ chưa biết. Các thay đổi ấy **không nhất thiết làm test đơn vị Java thất bại**. Đối với đối tác và SDK đã phát hành, hợp đồng HTTP quan trọng không kém mã nguồn.

**OpenAPI Specification (OAS)** mô tả method, URI, tham số, media type, schema, header, status và security scheme. Đưa các kiểm tra OAS vào **Continuous Integration (CI)** giúp phát hiện sớm lỗi mô tả và thay đổi tương thích trước khi merge/deploy. Nhưng OpenAPI **không tự chứng minh** API tuân thủ đầy đủ ràng buộc REST, phân quyền chính xác hay giao dịch thực sự lũy đẳng.

Sau bài học, người học có thể:

1. Phân biệt **validate**, **lint**, **diff tương thích** và **kiểm thử contract/runtime**.
2. Phân loại thay đổi request/response theo hướng tương thích ngược đối với client hiện hữu.
3. Thiết kế một pipeline CI có baseline đáng tin cậy, quality gates, báo cáo và quy trình ngoại lệ.
4. Liên hệ OpenAPI với controller/DTO Java Spring, HTTP status, authentication/authorization và consumer-driven tests.
5. Viết test ngăn lỗi schema, xung đột mã trạng thái, regression idempotency, phân trang và bảo mật.

**Bài toán xuyên suốt:** OmniOrder có POST /api/orders tạo đơn, GET /api/orders/{id} đọc đơn và GET /api/orders phân trang. Một bản pull request chỉnh OpenAPI và Spring controller. Nhóm cần biết: *Tài liệu có hợp lệ không? Thiết kế có đúng quy ước không? Có phá client đang chạy không? Runtime có làm đúng những gì spec hứa?*

## 2. Bốn lớp kiểm tra, bốn loại phát hiện

| Lớp | Câu hỏi | Công cụ/kỹ thuật | Điều không thể kết luận |
|---|---|---|---|
| **Validate OAS** | YAML/JSON và cấu trúc OpenAPI có đúng? | Parser, schema validation, kiểm tra $ref | HTTP runtime đúng hay không |
| **Lint OAS** | Có theo quy ước thiết kế và bảo mật của tổ chức? | Rule engine, style guide, custom rules | Không có breaking change |
| **Diff compatibility** | Bản ứng viên có phá người dùng của bản đã phát hành? | Semantic OpenAPI diff, review consumer | Không có thay đổi nghiệp vụ ẩn |
| **Contract/runtime test** | Server thực trả đúng schema/status/header/quyền không? | MockMvc, integration, provider/consumer tests | Mọi ràng buộc REST đều đạt |

**Không thay thế lớp này bằng lớp khác.** Một file YAML parse được vẫn có thể thiếu mô tả 401. Một file đạt lint vẫn có thể xóa endpoint đã phát hành. Một diff không báo breaking vẫn có thể che đi việc GET âm thầm thay đổi dữ liệu. Một bộ contract test đạt vẫn có thể bỏ sót quyền truy cập chéo tenant nếu không có negative tests.

### 2.1. Luồng CI đề xuất

**Pull request → validate → lint → diff baseline → test runtime/security → review → publish artifact có version.** Các job độc lập có thể chạy song song, nhưng không publish nếu gate bắt buộc chưa đạt; breaking change có chủ đích cần migration và phê duyệt.

## 3. Validate tài liệu: hợp lệ trước khi nói tới “đúng”

OpenAPI thường được viết bằng YAML; nhưng **YAML hợp lệ chưa đồng nghĩa OpenAPI hợp lệ**. Ví dụ một đoạn mô tả:

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /api/orders/{orderId}:
    get:
      operationId: getOrder
      responses:
        '200':
          description: Order representation
~~~

Về cấu trúc, đoạn này có thể là tài liệu OAS hợp lệ tùy các thành phần còn lại, nhưng **không khai báo path parameter orderId** và không có schema dữ liệu. Một validator/linter tốt sẽ nhận diện thiếu hoặc lệch khai báo parameter theo quy tắc OAS và style guide. Nếu tài liệu thực có $ref tới component không tồn tại, phải chặn từ lớp validate.

Các kiểm tra tối thiểu:

- **YAML/JSON parsing:** thụt đầu dòng, dấu ngoặc, kiểu scalar, key trùng. Một số parser YAML có thể âm thầm nhận key trùng và giữ giá trị sau, nên cần chính sách từ chối duplicate keys.
- **Phiên bản OAS:** biết tài liệu đang là 3.0.x hay 3.1.x; cú pháp JSON Schema/nullable không giống nhau hoàn toàn.
- **Bắt buộc:** openapi, info, paths hoặc phần phù hợp với loại tài liệu, operation responses, path parameter required.
- **Tham chiếu:** $ref đúng đích, không vòng tham chiếu gây lỗi tool, không trỏ tới component bị xóa.
- **Kiểu và cú pháp:** HTTP status response keys, media types, parameter location, schema keyword/format.
- **Tính duy nhất:** operationId duy nhất khi tổ chức dùng để sinh SDK; path template không gây xung đột mapping.

**Thực hành:** chạy validator trên file đã bundle/resolve nếu công cụ downstream yêu cầu một tài liệu đơn; nhưng hãy giữ kiểm tra các file nguồn. Khi giải quyết external $ref, không cho PR tùy ý fetch URL không đáng tin hoặc tiết lộ token trong môi trường CI.

### 3.1. Chọn tool theo phiên bản

Các hệ sinh thái thường có **Spectral** hoặc công cụ tương đương để lint, **OpenAPI parser/validator** để kiểm tra tài liệu và **oasdiff/openapi-diff** để so sánh phiên bản. Tên cụ thể, CLI options và khả năng hỗ trợ OAS 3.1 thay đổi theo phiên bản; **khóa dependency/tool version trong CI**, xác nhận bằng tài liệu công cụ và test một fixture cụ thể trước khi dùng như gate.

**Linter chạy thành công không chứng minh hợp đồng đầy đủ**: quy tắc mặc định có thể thiếu yêu cầu riêng về phân trang, auth hoặc idempotency.

## 4. Lint: biến style guide thành quy tắc kiểm tra được

Lint giúp team áp dụng một ngôn ngữ thiết kế API nhất quán. Các nhóm quy tắc thường thấy:

| Nhóm | Ví dụ quy tắc | Mức xử lý gợi ý |
|---|---|---|
| **Định danh & tài liệu** | operationId duy nhất; summary/description cho operation | Error hoặc warning tùy mức ảnh hưởng |
| **URI & method** | URI resource rõ nghĩa; path param mô tả; không dùng GET để gây side effect | Review nghiệp vụ; lint chỉ bắt mẫu rõ ràng |
| **Request/response** | Mọi response chính có schema và media type phù hợp; 204/304 không khai body | Error |
| **Trạng thái lỗi** | Mô tả 400/401/403/404/409/412/422 khi endpoint có thể phát sinh | Rule có điều kiện theo loại endpoint |
| **Security** | Khai báo security scheme và quyền theo operation; không vô tình công khai endpoint private | Error + runtime security test |
| **Pagination** | Collection GET có limit/cursor hoặc chính sách rõ | Error/warning theo chuẩn tổ chức |
| **Versioning** | Không dùng schema tên mơ hồ, có changelog/deprecation policy | Warning/review |
| **Schema quality** | Định nghĩa required, type/format, enum, ví dụ, field deprecated | Error cho lỗi dữ liệu; warning cho tài liệu |

Không nên bắt tất cả operation khai **mọi** status 4xx, vì một endpoint không hỗ trợ một số hành vi. Rule cần theo **ngữ cảnh**: endpoint private nên có mô tả auth; endpoint tạo mới có thể cần 201 + Location; endpoint GET/HEAD có điều kiện có thể công bố 304 nhưng không bắt buộc.

### 4.1. Lỗi và cảnh báo không có cùng trọng số

Một cách tổ chức:

- **Error:** đặc tả sai; xóa schema bắt buộc; thiếu security ở endpoint private; response 204 có body; operationId trùng.
- **Warning:** thiếu ví dụ thực tế, mô tả chưa rõ, tên chưa đúng style nhưng chưa phá hợp đồng.
- **Information:** gợi ý cải thiện nhất quán/khả năng sinh SDK.

Ban đầu nên bật bộ quy tắc nhỏ nhưng **đáng tin**; nhiều false positives sẽ khiến team bỏ qua cảnh báo. Với repo legacy, có thể tạo baseline các lỗi đã tồn tại và chặn **lỗi mới**, sau đó cải thiện dần. Tuy nhiên, baseline không nên biến lỗi bảo mật nghiêm trọng thành nợ không thời hạn.

### 4.2. Ví dụ ruleset minh họa

Ví dụ tệp rule config theo cú pháp của một linter kiểu Spectral (được đưa **trong bài** làm tham khảo, không ghi thành tệp riêng):

~~~yaml
extends:
  - spectral:oas
rules:
  operation-operationId: error
  operation-description: warn
  require-get-summary:
    description: GET operations should explain their purpose
    severity: warn
    given: $.paths[*].get
    then:
      field: summary
      function: truthy
~~~

**Giới hạn:** tên built-in rules và JSONPath selector có thể khác theo bản Spectral/ruleset được cài; đoạn trên mô tả **ý tưởng cấu hình**. Kiểm tra bằng phiên bản đã pin và chạy với fixture trước khi đặt làm gate. Không copy một selector chưa được kiểm chứng rồi coi nó đã kiểm tra được tất cả operation, đặc biệt khi có path-item $ref.

### 4.3. Quy tắc semantic không thể viết bằng regex đơn giản

Ví dụ GET /api/orders/{id}/cancel có thể mang side effect; linter có thể cảnh báo dựa trên tên path nhưng không thể chứng minh server thực sự hủy đơn. Ngược lại, POST /api/reports/generate có thể là operation nghiệp vụ hợp pháp. **REST là phong cách kiến trúc**, lint OpenAPI là kiểm tra mô tả; cần review use case và test runtime.

Với lỗi ẩn sâu như “GET trả private data nhưng Cache-Control public”, một số header chỉ được quyết định ở gateway. Linter không thể đọc chính sách toàn hệ thống nếu chúng không nằm trong tài liệu.

## 5. Breaking change là thay đổi phá lời hứa với client cũ

Trong kiểm tra tương thích ngược, cần xác định góc nhìn: **client đã triển khai theo hợp đồng đã phát hành** tiếp tục gửi request cũ và xử lý response cũ. Nếu bản mới khiến những client đó không thể tương tác như trước, thay đổi có khả năng *breaking*.

Nguyên tắc thực hành thường dùng:

- **Đầu vào server (request):** nới rộng điều được chấp nhận thường tương thích hơn; siết điều kiện có thể phá client.
- **Đầu ra server (response):** không bỏ những điều client được phép trông đợi; khi bổ sung giá trị/hình dạng mới, phải xét client cũ có xử lý được hay không.
- **Hành vi ngoài schema:** mã trạng thái, quyền, header, pagination, lũy đẳng, độ trễ và sự tồn tại của liên kết cũng là một phần hợp đồng.

### 5.1. Ma trận thay đổi request

| Thay đổi ở request | Đánh giá sơ bộ | Lý do |
|---|---|---|
| Xóa path hoặc HTTP method | **Breaking** | Client cũ không gọi được |
| Đổi tên path/query/header parameter | **Breaking** | Request cũ không còn khớp |
| Thêm trường/parameter **required** | **Breaking** | Client cũ chưa gửi |
| Đổi trường request từ integer thành string | **Breaking** | Payload cũ có thể bị từ chối |
| Tăng minimum, giảm maximum, hạn chế enum được chấp nhận | **Breaking** | Thu hẹp tập dữ liệu hợp lệ |
| Chuyển field required thành optional | Thường tương thích | Request cũ vẫn hợp lệ |
| Thêm field request tùy chọn | Thường tương thích | Request cũ không cần đổi |
| Thêm media type request mới trong khi giữ loại cũ | Thường tương thích | Không từ chối request cũ |
| Bắt buộc header Idempotency-Key trước đây optional | **Breaking** | Client cũ thiếu header |
| Siết authentication/scope | **Có thể breaking** | Token/permission hiện hữu không đủ |

### 5.2. Ma trận thay đổi response

| Thay đổi ở response | Đánh giá sơ bộ | Lý do |
|---|---|---|
| Xóa field đã được schema hứa trả | **Breaking**, đặc biệt nếu required | Client cũ cần field |
| Đổi kiểu dữ liệu từ string sang number | **Breaking** | Deserialize/logic cũ có thể lỗi |
| Cho phép null ở field trước đây luôn có giá trị | **Có thể breaking** | Client cũ không kiểm tra null |
| Thêm field response tùy chọn | Thường tương thích | Client khoan dung sẽ bỏ qua field lạ |
| Thêm enum value trả về | **Có thể breaking** | Client dùng exhaustive switch/SDK enum đóng |
| Bỏ một enum value trả về | Thường không phá parser, nhưng cần review | Client có thể đang phụ thuộc nghiệp vụ vào giá trị ấy |
| Thay 201 + Location bằng 200 không Location | **Breaking** | Client dựa trên mã/hypermedia |
| Bỏ Content-Type hoặc đổi media type | **Breaking** | Client không biết parse body |
| Đổi JSON body sang rỗng (204) | **Breaking** | Client cần dữ liệu |
| Thêm status hợp lệ 202 cho cùng thao tác | **Có thể breaking** | Client phải xử lý trạng thái pending |
| Thêm field bí mật vào response | **Không nên chỉ xét compatibility** | Có thể thành lỗi bảo mật |

**“Thường tương thích” không có nghĩa chắc chắn an toàn.** Generated SDK có thể từ chối unknown fields, custom enum deserializer có thể lỗi với giá trị mới; nhiều consumer không tuân thủ nguyên tắc tolerant reader. Do đó các công cụ diff nên trả về *tín hiệu cần review* thay vì là trọng tài duy nhất.

### 5.3. Ví dụ tối thiểu: thêm request field required

Hợp đồng phát hành:

~~~yaml
CreateOrderRequest:
  type: object
  required: [customerId, items]
  properties:
    customerId:
      type: string
    items:
      type: array
      items:
        $ref: '#/components/schemas/OrderItem'
~~~

Trong PR, một người thêm:

~~~yaml
CreateOrderRequest:
  type: object
  required: [customerId, items, promotionCode]
  properties:
    customerId:
      type: string
    items:
      type: array
      items:
        $ref: '#/components/schemas/OrderItem'
    promotionCode:
      type: string
~~~

Một client cũ vẫn gửi:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Authorization: Bearer <test-token>

{"customerId":"cus-17","items":[{"sku":"BOOK-01","quantity":1}]}
~~~

Nếu server mới từ chối thiếu promotionCode, API đã **phá tương thích**. Cách mở rộng thường an toàn hơn: làm promotionCode **optional**, có default nghiệp vụ được định nghĩa, hoặc triển khai version mới và kế hoạch chuyển đổi.

### 5.4. Ví dụ: đổi response enum

Hợp đồng cũ chỉ trả status **PENDING_PAYMENT**, **CONFIRMED**, **CANCELLED**. Bản mới thêm **PAYMENT_REVIEW**. Một client dùng switch không có nhánh mặc định có thể gặp lỗi dù OAS chỉ “thêm enum value”.

Nên:

1. Xác định consumer SDK/ứng dụng có khả năng xử lý **unknown value**.
2. Cân nhắc cung cấp trạng thái tương thích hoặc versioning.
3. Cập nhật changelog và consumer contract tests.
4. Bảo đảm UI không suy luận “unknown = đã thanh toán thành công”.

Thay đổi ngữ nghĩa của một giá trị cũ, ví dụ CONFIRMED trước kia nghĩa đã thanh toán nhưng nay chỉ nghĩa đã nhận đơn, thậm chí **không xuất hiện như diff schema**. Review nghiệp vụ là bắt buộc.

## 6. Diff không chỉ là so dòng YAML

Text diff rất hữu ích để review nhưng có thể tạo nhiễu khi:

- Đổi thứ tự các property hoặc format YAML.
- Di chuyển schema sang components và dùng $ref.
- Đổi tên component nội bộ mà response schema thực tế không đổi.
- Chia một file lớn thành nhiều file nhưng bundle giữ cùng contract.

**Semantic OpenAPI diff** cố gắng so sánh hành vi công bố: path/method, tham số, media type, schema, status, security và constraints. Nó thường phân loại thành **breaking**, **non-breaking** hoặc **potentially breaking** tùy tool/ruleset.

Tuy nhiên, kết quả phụ thuộc phiên bản công cụ, cách resolve $ref, ngữ nghĩa JSON Schema và cách tool hiểu các schema composition như oneOf/anyOf/allOf. Không có công cụ nào chứng minh toàn bộ compatibility của hệ thống phân tán.

### 6.1. Chọn baseline thật sự đã phát hành

So sánh:

~~~text
base = hợp đồng hiện đang phục vụ client production/đối tác
candidate = hợp đồng được build từ pull request
~~~

Không tự chọn “file YAML trong nhánh main hôm nay” nếu nhánh main có những thay đổi chưa phát hành hoặc API có nhiều phiên bản đang cùng hoạt động. Một baseline đáng tin nên là **artifact bất biến theo release/version**, có checksum/tag và provenance rõ. Trong CI, nguồn baseline phải được xác thực, không do PR tự tùy tiện đổi để qua gate.

Nếu v1/v2 chạy song song, so candidate v1 với **v1 đã phát hành**, không phải v2.

### 6.2. Phân tích kết quả theo hướng request/response

Một báo cáo diff có thể nói:

~~~text
BREAKING:
  POST /api/orders:
    requestBody.application/json:
      new required property: promotionCode

POTENTIALLY BREAKING:
  GET /api/orders/{id}:
    response.status enum value added: PAYMENT_REVIEW

NON-BREAKING:
  GET /api/orders/{id}:
    optional response property added: displayLabel
~~~

Đây là **định dạng báo cáo minh họa**, không phải output được bảo đảm của một CLI cụ thể. Khi xuất bản báo cáo PR nên kèm **đường dẫn operation, vị trí schema, loại thay đổi, mức nghiêm trọng, baseline version và đường dẫn migration**.

### 6.3. Những thay đổi mà diff khó thấy

| Thay đổi thực | Vì sao OAS diff có thể bỏ sót? | Bằng chứng nên có |
|---|---|---|
| GET bất ngờ ghi trạng thái hoặc gọi payment | OAS mô tả interface, không thấy side effect | Integration test, review domain |
| POST retry cùng Idempotency-Key vẫn tạo hai orders | Header vẫn được mô tả như cũ | DB concurrency/failure-injection test |
| GET list chỉ trả 10 item thay vì limit=50 | Schema response có thể không đổi | Pagination integration tests |
| Query mặc định sort theo field khác | Không phải mọi semantic đều nằm trong schema | Consumer tests, changelog |
| Tenant A đọc được resource tenant B | OAS security declaration không thực thi ACL | Authorization tests |
| CORS/cache policy tại gateway thay đổi | Thường không nằm trong OAS source | Environment/infrastructure tests |
| 504 tăng mạnh do query chậm | Contract schema vẫn nguyên | Performance/SLO regression |

Do đó **diff gate + runtime contract tests + human review** là tổ hợp cần thiết. Không nên “đổi spec cho khớp bug production” mà không thảo luận tác động và trách nhiệm tương thích.

## 7. Dựng pipeline CI từ đầu đến cuối

### 7.1. Những artifact cần có

Giả sử dự án có một tài liệu hợp đồng dành cho Orders API:

~~~text
contracts/orders-v1.yaml          # candidate từ PR
contracts/baselines/orders-v1.yaml # bản đã phát hành, read-only trong CI
contracts/ruleset.yaml            # quy tắc lint đã phê duyệt
~~~

Đây chỉ là **sơ đồ tệp minh họa trong bài học**, không yêu cầu tạo hoặc thay đổi tệp nào ngoài bài Markdown đang được viết. Trong thực tế, baseline có thể lấy từ API registry hoặc release artifact có xác minh checksum, thay vì để một bản sao cùng nhánh PR có thể sửa.

Các bước chất lượng:

1. **Build candidate:** nếu code-first, sinh OpenAPI từ build/đường chạy kiểm soát; nếu design-first, bundle tài liệu nguồn để kiểm tra.
2. **Validate:** kiểm tra cấu trúc và reference; dừng với lỗi parse/schema.
3. **Lint:** áp rule set đã pin, tính severity và xuất vị trí lỗi.
4. **Diff:** so với baseline đúng version mà client đang được hỗ trợ; chặn breaking ngoài chính sách.
5. **Build/test Java/Spring:** biên dịch, unit test, MockMvc, integration test DB/auth và negative cases.
6. **Review ngữ nghĩa:** người sở hữu API/consumer review logic mà máy không kiểm tra được.
7. **Publish:** gắn contract artifact với cùng commit/build/release, có changelog.

Các job validate/lint/diff có thể chạy song song với build/test để giảm thời gian CI. Khi một job thất bại, merge gate vẫn phải coi **toàn bộ quality gate** là chưa đạt.

### 7.2. Lệnh CLI tham khảo

Một pipeline dùng tool được cài và **pin version** có thể có ý tưởng tương tự:

~~~bash
# 1. Lint / kiểm tra quy tắc OAS
npx @stoplight/spectral-cli lint contracts/orders-v1.yaml \
  --ruleset contracts/ruleset.yaml

# 2. Phát hiện thay đổi breaking so với bản đã phát hành
oasdiff breaking \
  contracts/baselines/orders-v1.yaml \
  contracts/orders-v1.yaml

# 3. Chạy kiểm thử thực thi của API Spring
./gradlew test
~~~

**Đây là chuỗi lệnh minh họa**, không phải bộ lệnh đã chạy trên repository của người học. Lệnh giả định dự án đã cài và khóa phiên bản Spectral, oasdiff, JDK/Gradle, có ruleset tương thích; cấu hình phụ thuộc phiên bản tool đang dùng. Trên môi trường không phải Unix, cách gọi wrapper/đường dẫn có thể khác. Trong pipeline thật, bổ sung validator OAS riêng nếu linter không bảo đảm tất cả kiểm tra cú pháp và reference.

Không để **npx tự tải một phiên bản mới không kiểm soát** tại mỗi lần chạy; tránh tình huống hôm qua CI xanh nhưng hôm nay cùng commit CI đỏ chỉ vì thay đổi dependency. Phải đảm bảo công cụ có nguồn đáng tin, được pin, và cách lấy baseline không phụ thuộc dữ liệu PR chưa được duyệt.

### 7.3. Pseudocode cho quality gate

~~~text
candidate = buildOrLoadCandidateContract()
baseline  = fetchVerifiedPublishedContract(api="orders", major=1)

validate(candidate)          # parse, refs, OAS structure
lint(candidate, ruleset)     # conventions, policy

diff = compareSemantics(baseline, candidate)
if diff.containsBreakingChange():
    requireApprovedMigrationOrFail(diff)

runSpringContractTests(candidate)
runSecurityAndFailureTests()
publishOnlyAfterMergeAndReleaseApproval()
~~~

Trình tự có thể khác; điều cần giữ là **nguồn baseline đáng tin** và **không cho một nhánh PR tự ghi đè baseline để khiến diff rỗng**. Báo cáo nên hiển thị cả diff được đánh giá là không phá tương thích, để consumer thấy các giá trị enum/response mới.

### 7.4. Gate cho repository lâu năm

Với API legacy có nhiều warning, có thể chặn **lỗi cấu trúc và lỗi lint mới**, dùng warning baseline được kiểm soát rồi giảm dần nợ; vẫn chặn breaking change và xử lý ngay lỗi auth/PII nghiêm trọng. Mỗi ngoại lệ cần owner và hạn xử lý, không trở thành miễn trừ vô thời hạn.

## 8. Java/Spring: giữ tài liệu và controller không lệch nhau

Giả sử hợp đồng đã công bố **POST /api/orders** nhận customerId, items và trả 201 + Location; GET có authentication và chỉ trả order thuộc quyền người dùng.

Một implementation rút gọn:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.net.URI;
import java.util.List;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

record ItemInput(@NotBlank String sku, @Min(1) int quantity) {}
record CreateOrderInput(
        @NotBlank String customerId,
        @NotEmpty List<@Valid ItemInput> items) {}
record OrderView(String id, String status, long totalAmount) {}

interface OrdersUseCase {
    // Thực hiện authz, tenant constraints và idempotency trong service.
    OrderView create(
            Authentication caller, String key, CreateOrderInput input);
    OrderView readVisible(Authentication caller, String orderId);
}

@RestController
@RequestMapping("/api/orders")
class OrdersController {
    private final OrdersUseCase orders;

    OrdersController(OrdersUseCase orders) {
        this.orders = orders;
    }

    @PostMapping(consumes = "application/json",
                 produces = "application/json")
    ResponseEntity<OrderView> create(
            @RequestHeader("Idempotency-Key") String key,
            @Valid @RequestBody CreateOrderInput input,
            Authentication caller) {
        OrderView created = orders.create(caller, key, input);
        return ResponseEntity
                .created(URI.create("/api/orders/" + created.id()))
                .cacheControl(CacheControl.noStore())
                .body(created);
    }

    @GetMapping(path = "/{id}", produces = "application/json")
    ResponseEntity<OrderView> get(
            @PathVariable String id, Authentication caller) {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(orders.readVisible(caller, id));
    }
}
~~~

Đây là **fragment minh họa**, không tự chạy nếu chưa có OrdersUseCase, persistence, Spring Security configuration, xử lý exception hoặc bộ test. @Valid giúp kiểm tra DTO; nó **không tự bảo đảm** quyền tenant hoặc idempotency. Spring có thể trả 400 cho một số validation error theo mặc định; nếu OAS hứa 422 thì cần handler mapping đúng và test.

### 8.1. Cách detect drift

- **Design-first:** so controller thực với spec đã phê duyệt: mỗi path/method, response status, Content-Type, error schema, header, field type.
- **Code-first:** sinh OpenAPI từ controller/annotation, so kết quả với artifact chuẩn và review diff. Generator có thể không suy được trạng thái lỗi hoặc semantics được xử lý bởi global advice/gateway.
- **Contract testing:** gọi HTTP endpoint thật hoặc MockMvc và kiểm tra response. Đừng coi metadata annotation là hành vi runtime.

Ví dụ một nhà phát triển đổi:

~~~java
// Sai hợp đồng nếu 201 + Location đã được phát hành:
return ResponseEntity.ok(created);
~~~

Code vẫn biên dịch, unit test business vẫn có thể xanh, nhưng client phụ thuộc 201 hoặc Location sẽ lỗi. **Contract test phải bắt được**.

### 8.2. MockMvc test cho status, header và body

Fragment test JUnit với MockMvc đã cấu hình principal, OrdersUseCase giả lập và dữ liệu thử:

~~~java
mockMvc.perform(post("/api/orders")
        .with(jwt())
        .header("Idempotency-Key", "intent-001")
        .contentType("application/json")
        .content("""
            {"customerId":"cus-17",
             "items":[{"sku":"BOOK-01","quantity":2}]}
            """))
    .andExpect(status().isCreated())
    .andExpect(header().string(
        "Location", startsWith("/api/orders/")))
    .andExpect(jsonPath("$.id").exists())
    .andExpect(jsonPath("$.status").isString())
    .andExpect(jsonPath("$.totalAmount").isNumber());
~~~

Các matcher và jwt() cần static imports/thiết lập từ Spring Test, Spring Security Test và Hamcrest. **Kiểm tra JSON bằng vài jsonPath chưa đủ** nếu contract có nhiều nhánh hoặc optional/required phức tạp: cần schema-based test hoặc kiểm thử dạng payload lớn/nhỏ khác nhau.

Nếu client phụ thuộc vào kết quả retry của POST khi mất phản hồi, integration test phải dùng **database transaction/unique key thật** để chứng minh không tạo hai đơn. Không thể xác minh lũy đẳng chỉ bằng việc thấy OpenAPI có tham số Idempotency-Key.

### 8.3. Lỗi HTTP và Problem Details

Nếu contract mô tả response lỗi application/problem+json, server cần thực trả cấu trúc phù hợp, ví dụ:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/idempotency-conflict",
  "title": "Idempotency key conflict",
  "status": 409,
  "detail": "Khóa này đã được dùng cho một yêu cầu khác",
  "code": "IDEMPOTENCY_KEY_REUSED"
}
~~~

Trường **code** là extension do API định nghĩa, không phải trường bắt buộc của Problem Details (RFC 9457). Test cần kiểm tra status/mime type, error code ổn định, thông báo không lộ stack trace, giá trị thanh toán hoặc PII. Không sửa tất cả 4xx/5xx thành HTTP 200 với success=false chỉ vì frontend muốn dễ parse.

## 9. Security và quality gate cho thay đổi không hiện trong schema

Giả sử PR vẫn giữ nguyên GET /api/orders/{id} và schema Order, nhưng bỏ bộ lọc tenant ở repository. **Lint và OpenAPI diff có thể đều xanh**, trong khi tenant A đọc được đơn của B. Vì vậy CI phải kiểm thử hành vi:

- **401:** token thiếu, không hợp lệ hoặc hết hạn bị từ chối.
- **403/404:** không thể đọc/sửa resource không thuộc quyền; tránh enumeration theo policy.
- **Field security:** response không xuất PII, secret hoặc internal notes ngoài quyền.
- **Cache:** response riêng tư không bị shared cache phân phối sai người.
- **Idempotency/rate limit:** retry không tạo giao dịch trùng, lỗi 429/503 được xử lý theo hợp đồng.

Nếu PR tăng scope từ orders.read lên orders.admin thì phải review tác động client và tính đúng của resource authorization. Trong OpenAPI, mô tả securitySchemes **không tạo filter bảo mật thật**; test Spring/gateway phải có.

## 10. Xử lý breaking change có chủ đích

Khi diff báo breaking, không mặc định chặn mọi đổi mới mãi mãi. Hãy yêu cầu một **migration decision** ghi rõ: endpoint/schema bị ảnh hưởng, consumer nào còn dùng, lý do đổi, kế hoạch tương thích (giữ version cũ/song song/adapter), ngày deprecate và sunset khi phù hợp, owner và người phê duyệt.

Ngoại lệ quality gate cần **có phạm vi và thời hạn**, ví dụ chỉ cho phép xóa một response field ở API v2 nội bộ sau khi toàn bộ consumer đã nâng cấp; không tắt global rule trong mọi API. Baseline và report phải được lưu cùng build để audit.

Trong CI của pull request từ nguồn chưa tin cậy, **không cấp production secret cho job lint/test**, không để tài liệu $ref tùy ý khiến pipeline truy cập endpoint nội bộ; pin tool/action dependencies và kiểm soát quyền ghi artifact.

## 11. Bài tập thực hành

**Bài 1 — Phân loại thay đổi.** Bản mới thêm request property promotionCode vào danh sách required, đổi response totalAmount từ integer sang string và thêm optional displayLabel. **Đáp án:** Hai thay đổi đầu **breaking**, thay đổi cuối **thường tương thích** nếu client chịu được field lạ.

**Bài 2 — Lint có đủ không?** File OAS hợp lệ, operationId duy nhất, nhưng API GET /orders/{id} trả dữ liệu khác tenant. **Đáp án:** Không. Cần test quyền ở runtime/query; khai báo bearerAuth hoặc linter không bảo đảm authorization.

**Bài 3 — Chọn baseline.** Nhánh main đã có API v2 chưa phát hành; production vẫn chạy v1. PR chỉnh v1 phải so với bản nào? **Đáp án:** Bản **v1 đã phát hành** và còn được hỗ trợ, không chỉ main/v2.

**Bài 4 — Thay đổi enum.** Thêm PAYMENT_REVIEW vào response status, tool diff báo non-breaking. Có thể merge ngay không? **Đáp án:** Cần xem client exhaustive switch/SDK enum, thêm fallback và contract tests, đánh giá hành vi nghiệp vụ.

**Bài 5 — Drift trong Spring.** OAS hứa POST tạo đơn trả 201 + Location; controller được sửa thành 200 không Location. **Đáp án:** Build Java có thể vẫn xanh nhưng contract test phải thất bại; sửa implementation hoặc thảo luận migration trước khi đổi contract.

## 12. Checklist và kết luận

- [ ] Candidate OAS được parse/validate đúng phiên bản, $ref và parameter?
- [ ] Ruleset lint đã pin, mức error/warning rõ, có owner xử lý?
- [ ] Diff so với **artifact đã phát hành** của đúng API version?
- [ ] Đã kiểm tra cả request và response, status/header/media type, security và enum?
- [ ] Có review semantic changes ngoài OAS như pagination, lũy đẳng và side effects?
- [ ] MockMvc/integration/consumer tests kiểm tra HTTP thực và quyền tenant?
- [ ] Breaking change có migration/versioning, thông báo và ngoại lệ được duyệt?
- [ ] CI không để PR sửa baseline, tải $ref không tin cậy hoặc dùng production secret?
- [ ] Contract được publish gắn với đúng build/release sau khi gates đạt?

**Kết luận:** **Validate** kiểm tra cấu trúc, **lint** giữ quy ước, **semantic diff** phát hiện rủi ro tương thích và **contract/security tests** xác minh runtime. Kết hợp CI, baseline phát hành và review để API tiến hóa an toàn; không công cụ nào thay thế kiểm thử HTTP thực tế.
