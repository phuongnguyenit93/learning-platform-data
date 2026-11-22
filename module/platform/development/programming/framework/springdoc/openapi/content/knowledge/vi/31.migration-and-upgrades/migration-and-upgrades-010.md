# So sánh ngữ nghĩa của đặc tả trước và sau khi chuyển đổi

Khi nâng cấp Spring Boot, springdoc-openapi hoặc chuyển OpenAPI document sang một phiên bản đặc tả mới, tài liệu được sinh ra có thể thay đổi rất nhiều dòng dù API runtime vẫn giữ nguyên. Ngược lại, một thay đổi chỉ vài ký tự trong schema có thể làm client không còn gửi được request hợp lệ hoặc không đọc được response.

Vì vậy, so sánh hai file YAML/JSON bằng text diff chưa đủ để kết luận migration an toàn. Cần so sánh **ngữ nghĩa của hợp đồng**: operation nào tồn tại, client gửi được những dữ liệu nào, server cam kết trả những status và representation nào, cách xác thực được yêu cầu ra sao và các công cụ sinh SDK hiểu document như thế nào.

Trong module springdoc-openapi, quy trình này thường bắt đầu bằng cách lấy OpenAPI document từ cùng một ứng dụng trước và sau migration, sau đó validate từng document, chạy semantic diff, kiểm tra payload mẫu và review các thay đổi có ảnh hưởng đến consumer.

## 1. Phân biệt text diff, semantic diff và compatibility diff

Ba loại so sánh trả lời ba câu hỏi khác nhau:

| Loại so sánh | Câu hỏi | Ví dụ |
|---|---|---|
| Text diff | Những dòng hoặc ký tự nào thay đổi? | YAML đổi thứ tự property, đổi indent hoặc thay nullable bằng type có null |
| Semantic diff | Hai document mô tả hành vi và tập dữ liệu được chấp nhận giống nhau đến đâu? | Schema trước và sau có chấp nhận cùng giá trị request không? |
| Compatibility diff | Consumer đang dùng contract cũ có tiếp tục hoạt động với contract mới không? | Thêm một query parameter bắt buộc có làm client cũ thất bại không? |

Text diff hữu ích để review nguồn, nhưng không hiểu cấu trúc OpenAPI. Semantic diff phân tích document theo model OpenAPI và so sánh operation, parameter, schema, response, security cùng các thành phần liên quan. Compatibility diff xem thay đổi theo hướng consumer/provider để nhận diện nguy cơ breaking.

**Tương đương ngữ nghĩa không đồng nghĩa với tương thích ngược.** Ví dụ, đổi schema từ nullable của OpenAPI 3.0 sang union type có null trong OpenAPI 3.1 có thể giữ nguyên tập giá trị hợp lệ. Ngược lại, thêm một property bắt buộc vào request có thể là thay đổi hợp lệ theo đặc tả mới nhưng làm client cũ không còn gửi request thành công.

## 2. Xác định đúng hai document cần so sánh

Trước khi chạy công cụ, phải bảo đảm hai file đại diện cho cùng một API contract ở hai thời điểm:

- Cùng service và cùng API domain.
- Cùng group, ví dụ orders-v1.
- Cùng profile Spring Boot và các property ảnh hưởng đến controller mapping.
- Cùng context path hoặc quy tắc public path.
- Cùng nguồn dữ liệu và cấu hình customizer nếu chúng ảnh hưởng document.
- Cùng phạm vi authentication khi truy xuất endpoint tài liệu.
- Một file là baseline trước migration, file còn lại là candidate sau migration.

Không so sánh document orders-v1 với orders-v2 rồi kết luận migration đã làm thay đổi contract. Đó là hai phiên bản API khác nhau. Tương tự, không so sánh tài liệu mặc định trước migration với group mới sau migration nếu phạm vi operation không giống nhau.

Nên lưu artifact theo cấu trúc có thể nhận biết nguồn và thời điểm:

~~~text
artifacts/
└── openapi/
    ├── baseline/
    │   └── orders-v1.json
    └── candidate/
        └── orders-v1.json
~~~

Baseline nên lấy từ release đã phát hành hoặc commit đã được chấp thuận. Candidate nên được sinh từ đúng commit đang review. Tránh dùng hai file được tải từ hai môi trường có cấu hình khác nhau vì khác biệt môi trường có thể bị hiểu nhầm là thay đổi do migration.

## 3. Lấy OpenAPI document từ springdoc trước và sau migration

springdoc sinh OpenAPI document từ Spring-managed controller, annotation, model và cấu hình. Với document mặc định, endpoint thường là:

~~~text
/v3/api-docs
~~~

Với group, endpoint thường có dạng:

~~~text
/v3/api-docs/{groupName}
~~~

Ví dụ lấy cùng group orders-v1 từ hai bản chạy độc lập:

~~~bash
curl -fsS http://localhost:8081/v3/api-docs/orders-v1 -o artifacts/openapi/baseline/orders-v1.json
curl -fsS http://localhost:8082/v3/api-docs/orders-v1 -o artifacts/openapi/candidate/orders-v1.json
~~~

Trên Windows PowerShell, dùng curl.exe để tránh alias curl của PowerShell:

~~~powershell
curl.exe -fsS http://localhost:8081/v3/api-docs/orders-v1 -o artifacts/openapi/baseline/orders-v1.json
curl.exe -fsS http://localhost:8082/v3/api-docs/orders-v1 -o artifacts/openapi/candidate/orders-v1.json
~~~

Nếu endpoint tài liệu được bảo vệ, cần cung cấp authentication theo chính sách môi trường. Không đưa access token hoặc secret vào file OpenAPI hay log của pipeline.

Khi ứng dụng có nhiều group, lặp lại thao tác cho từng group và lưu mỗi cặp baseline/candidate riêng. Không gộp các document trước khi kiểm tra phạm vi từng group.

## 4. Validate từng document trước khi so sánh

Semantic diff chỉ có ý nghĩa khi cả hai input được parse và hợp lệ. Hãy validate từng file độc lập:

~~~bash
oasdiff validate artifacts/openapi/baseline/orders-v1.json
oasdiff validate artifacts/openapi/candidate/orders-v1.json
~~~

Validator giúp phát hiện lỗi cú pháp, cấu trúc OpenAPI hoặc quy tắc schema trước khi đọc kết quả diff. Nếu candidate không hợp lệ, cần sửa bước sinh document hoặc migration trước khi phân loại thay đổi.

Không dùng kết quả diff như một validator thay thế. Hai document có thể giống nhau ở phần lớn operation nhưng cùng chứa một schema sai; ngược lại, hai document đều hợp lệ nhưng contract của chúng không tương thích.

Nếu dùng external $ref, cần bảo đảm reference được resolve từ cùng một baseline có thể tái lập. Công cụ diff có thể phải tải tài nguyên bên ngoài; chỉ cho phép điều đó với nguồn đáng tin cậy. Với document không tin cậy, chạy trong môi trường hạn chế network hoặc tắt khả năng resolve external reference theo tùy chọn của công cụ để tránh truy cập tài nguyên ngoài ý muốn.

## 5. So sánh schema tương đương sau khi chuyển OpenAPI 3.0 sang 3.1

Một migration đặc tả có thể đổi cách viết schema mà không đổi tập giá trị hợp lệ. Ví dụ nullability:

OpenAPI 3.0:

~~~yaml
displayName:
  type: string
  nullable: true
~~~

OpenAPI 3.1:

~~~yaml
displayName:
  type:
    - string
    - 'null'
~~~

Nếu property có thể vắng mặt trong cả hai phiên bản, không bị thêm vào required, và runtime xử lý null như trước, hai schema có thể biểu diễn cùng ý nghĩa cho property đó.

Một ví dụ khác là giới hạn số:

OpenAPI 3.0:

~~~yaml
age:
  type: integer
  minimum: 18
  exclusiveMinimum: true
~~~

OpenAPI 3.1:

~~~yaml
age:
  type: integer
  exclusiveMinimum: 18
~~~

Cả hai cách đều yêu cầu giá trị lớn hơn 18. Nếu migration vô tình đổi thành minimum: 18, giá trị 18 sẽ được chấp nhận và tập dữ liệu hợp lệ đã thay đổi.

Khi review, hãy ghi rõ mỗi thay đổi là:

1. Thay đổi biểu diễn do khác phiên bản đặc tả.
2. Thay đổi metadata hoặc tài liệu.
3. Thay đổi tập giá trị được schema chấp nhận.
4. Thay đổi hành vi HTTP hoặc cách consumer gọi API.

Không đánh dấu mọi thay đổi schema là breaking, nhưng cũng không kết luận an toàn chỉ vì tên property và kiểu dữ liệu nhìn qua vẫn giống nhau.

## 6. Các chiều ngữ nghĩa cần so sánh

Một OpenAPI document có nhiều thành phần ảnh hưởng đến consumer. Nên review theo từng chiều thay vì chỉ nhìn số lượng dòng diff.

| Thành phần | Cần kiểm tra | Ví dụ thay đổi có thể ảnh hưởng |
|---|---|---|
| Paths và methods | URL, HTTP method, path template | Xóa GET /orders/{id} |
| Parameters | name, in, required, style, explode, schema | Thêm query parameter bắt buộc |
| Request body | required, media type, schema | Đổi JSON sang multipart |
| Schema | type, format, enum, required, bounds, nullability, composition | Thu hẹp enum hoặc bỏ giá trị null |
| Responses | Status code, media type, header, body schema | Xóa response 404 |
| Security | Scheme, requirement, OAuth scope | Bắt buộc thêm scope mới |
| Servers | Base URL, biến server, protocol | Đổi host hoặc prefix public |
| Operation metadata | operationId, deprecated, tags | Đổi operationId làm SDK đổi tên method |
| References | $ref, $id, external schema | Reference trỏ sang schema khác |
| Extensions | x-* vendor extensions | Gateway hoặc code generator không còn nhận policy |
| Webhooks/callbacks | Event, callback URL và payload | Xóa event mà consumer đang lắng nghe |

Một số thay đổi chỉ ảnh hưởng tài liệu hiển thị, nhưng vẫn có thể tác động công cụ sinh SDK hoặc portal. Vì thế cần phân biệt tác động đến wire contract với tác động đến developer experience và toolchain.

## 7. Phân loại thay đổi theo hướng request và response

Không thể đánh giá schema chỉ bằng câu hỏi type có đổi không. Phải xét ai gửi dữ liệu và ai nhận dữ liệu.

| Thay đổi | Hướng tác động thường gặp | Đánh giá ban đầu |
|---|---|---|
| Thêm request property optional | Client có thể tiếp tục bỏ qua property | Thường tương thích ngược |
| Thêm request property vào required | Client cũ không gửi property sẽ bị từ chối | Breaking |
| Xóa request property được hỗ trợ | Client cũ vẫn gửi field mà server không còn xử lý đúng | Có thể breaking |
| Thu hẹp enum request | Client gửi giá trị cũ không còn hợp lệ | Breaking |
| Mở rộng enum request | Server chấp nhận thêm giá trị | Thường tương thích ngược |
| Xóa response property | Consumer đang đọc property có thể thất bại | Breaking |
| Đổi response property sang type không tương thích | Consumer deserialize hoặc validate thất bại | Breaking |
| Thêm response property | Consumer linh hoạt thường bỏ qua được | Thường tương thích, nhưng cần xét additionalProperties và client strict |
| Xóa response status hoặc media type | Consumer không còn nhận được nhánh đã dựa vào | Breaking |
| Thêm response status mới | Consumer có thể cần xử lý nhánh mới | Thường không phá contract hiện có, nhưng client có thể xử lý lỗi nếu không có fallback |

Đây là phân loại ban đầu, không phải định luật cho mọi consumer. Ví dụ, thêm response property có thể phá một consumer dùng schema validation với additionalProperties: false. Ngược lại, một server có thể tiếp tục chấp nhận request property cũ dù document mới không còn mô tả nó; khi đó runtime và document đang lệch nhau.

## 8. Security và server cũng là ngữ nghĩa contract

Một migration có thể giữ nguyên path và schema nhưng vẫn thay đổi khả năng truy cập:

- Thêm security requirement ở cấp operation khiến request cũ không có token bị từ chối.
- Đổi OAuth scope có thể làm access token hiện tại không còn đủ quyền.
- Đổi tên hoặc loại security scheme có thể làm Swagger UI và SDK không cấu hình authentication như trước.
- Đổi servers.url có thể khiến client gọi sai host hoặc prefix.
- Đổi header parameter, style hoặc explode có thể làm client serialize query/path khác trước.

Không nên gộp các thay đổi này vào nhóm metadata. Security requirement và server URL có thể quyết định request có được gửi đến đúng service và có được chấp nhận hay không.

Việc gỡ security requirement có thể không phá client cũ nhưng lại làm giảm mức bảo vệ. Báo cáo compatibility không thay thế security review; thay đổi theo hướng nới quyền vẫn cần được phê duyệt.

## 9. OperationId và cấu trúc component có thể ảnh hưởng SDK

operationId thường được dùng làm tên method trong SDK generator. Đổi getOrderById thành findOrder có thể không thay đổi HTTP request/response, nhưng SDK được sinh lại có thể đổi public method name và làm mã nguồn consumer không biên dịch.

Tương tự, đổi tên component hoặc di chuyển schema từ inline sang $ref có thể chỉ là tái cấu trúc document. Nếu schema tham chiếu vẫn tương đương, wire contract có thể giữ nguyên. Tuy nhiên, một số generator dùng tên component để đặt class trong SDK; do đó thay đổi component name có thể ảnh hưởng public API của SDK.

Khi phát hành SDK từ OpenAPI, cần chạy thêm một bước:

1. Sinh SDK từ baseline.
2. Sinh SDK từ candidate bằng cùng generator và cùng cấu hình.
3. So sánh public API của hai SDK hoặc biên dịch consumer mẫu.
4. Review thay đổi tên class, method, enum, parameter và package.

Không kết luận SDK tương thích chỉ dựa vào báo cáo HTTP contract.

## 10. Dùng oasdiff để tạo ba góc nhìn báo cáo

oasdiff cung cấp các lệnh có mục đích khác nhau:

| Lệnh | Nội dung | Khi dùng |
|---|---|---|
| oasdiff diff | Diff đầy đủ của định nghĩa, gồm cả thay đổi tài liệu | Điều tra mọi khác biệt giữa hai artifact |
| oasdiff changelog | Thay đổi có thể ảnh hưởng consumer, gồm breaking và non-breaking | Tạo báo cáo cho reviewer |
| oasdiff breaking | Chỉ thay đổi được phân loại có nguy cơ phá client hiện có | Chặn migration không tương thích trong CI |
| oasdiff validate | Validate một document | Kiểm tra từng input trước diff |

Chạy:

~~~bash
oasdiff diff artifacts/openapi/baseline/orders-v1.json artifacts/openapi/candidate/orders-v1.json --format markdown
~~~

Xem thay đổi ảnh hưởng consumer:

~~~bash
oasdiff changelog artifacts/openapi/baseline/orders-v1.json artifacts/openapi/candidate/orders-v1.json --format markdown
~~~

Chỉ kiểm tra breaking change:

~~~bash
oasdiff breaking artifacts/openapi/baseline/orders-v1.json artifacts/openapi/candidate/orders-v1.json
~~~

Để CI trả lỗi khi có breaking change mức chắc chắn cao:

~~~bash
oasdiff breaking --fail-on ERR artifacts/openapi/baseline/orders-v1.json artifacts/openapi/candidate/orders-v1.json
~~~

Theo tài liệu CLI, lệnh breaking trả exit code 0 khi không có breaking change và 1 khi tìm thấy breaking change. ERR biểu thị thay đổi chắc chắn phá tương thích; WARN là thay đổi có khả năng ảnh hưởng nhưng công cụ không thể khẳng định chỉ từ đặc tả; INFO là thay đổi không phá tương thích. Có thể dùng --fail-on WARN nếu chính sách yêu cầu chặn cả trường hợp cần điều tra.

Không nên chỉ lưu báo cáo breaking. diff giúp nhận ra thay đổi cú pháp dự kiến do migration, còn changelog giúp reviewer hiểu thay đổi nào có thể tác động consumer.

## 11. Vì sao semantic diff vẫn cần review thủ công?

Công cụ diff phân tích cấu trúc và áp dụng quy tắc đã được định nghĩa. Nó không biết toàn bộ cách consumer sử dụng API, cấu hình runtime hoặc hành vi tùy biến bên ngoài document.

Một số ví dụ cần review thủ công:

- operationId thay đổi nhưng wire request/response không đổi; SDK có thể đổi method name.
- Server URL thay đổi theo môi trường; cần xác minh public URL và reverse proxy.
- Security requirement được nới lỏng; có thể không phải breaking nhưng là thay đổi bảo mật.
- Vendor extension x-* bị xóa; gateway hoặc generator nội bộ có thể phụ thuộc vào extension đó.
- Schema có oneOf, anyOf, allOf hoặc $ref lồng nhau; cần xác minh ngữ nghĩa sau khi resolver xử lý toàn bộ graph.
- Format như date-time, uuid hoặc email có thể được validator và code generator diễn giải khác nhau.
- Schema có readOnly, writeOnly, default, discriminator hoặc additionalProperties; thay đổi nhỏ có thể ảnh hưởng serializer/deserializer.

oasdiff có các mặc định để tránh một số khác biệt không cần thiết, ví dụ nhận diện một số schema inline và $ref tương đương trong nhánh anyOf/oneOf, hoặc so sánh tên header không phân biệt chữ hoa/chữ thường. Các tùy chọn như flatten allOf hoặc flatten parameters có thể thay đổi cách matching và không nên bật tùy tiện. Khi kết quả phụ thuộc vào option, hãy ghi rõ cấu hình diff trong repository để các lần chạy có thể tái lập.

## 12. Kiểm tra tập payload được schema chấp nhận

Semantic diff của document nên được bổ sung bằng một bộ payload mẫu. Mục tiêu là kiểm tra schema trước và sau chấp nhận hoặc từ chối cùng các trường hợp quan trọng.

Ví dụ schema Customer có property nullable:

~~~json
{
  "id": "c-100",
  "displayName": null
}
~~~

Tạo các fixture:

| Payload | Ý nghĩa | Kỳ vọng trước/sau nếu migration giữ semantics |
|---|---|---|
| displayName là chuỗi | Giá trị thông thường | Cả hai chấp nhận |
| displayName là null | Kiểm tra nullability | Cả hai chấp nhận |
| Không có displayName | Kiểm tra optional/required | Cả hai phải giữ cùng kết quả |
| displayName là số | Kiểm tra type | Cả hai từ chối |
| id bị thiếu | Kiểm tra required | Cả hai giữ cùng kết quả |

Với giới hạn số, cần kiểm tra cả giá trị ở biên:

| Payload age | Schema yêu cầu lớn hơn 18 |
|---:|---|
| 17 | Từ chối |
| 18 | Từ chối |
| 19 | Chấp nhận |

Chạy cùng fixture qua validator phù hợp với dialect của từng document. OpenAPI 3.0 dùng schema model riêng; OpenAPI 3.1 dựa trên JSON Schema Draft 2020-12. Phải cấu hình validator đúng dialect, không dùng một cấu hình mặc định không rõ phiên bản cho cả hai.

Ngoài schema validator, nên gửi fixture qua endpoint test của ứng dụng để xác minh runtime có thực hiện đúng contract. Một document có thể mô tả đúng nhưng controller, deserializer hoặc validation annotation vẫn xử lý khác.

## 13. Ví dụ migration giữ nguyên semantics

Giả sử trước migration, springdoc sinh OpenAPI 3.0.3:

~~~yaml
openapi: 3.0.3
info:
  title: Customer API
  version: 1.4.0
paths:
  /customers:
    post:
      operationId: createCustomer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateCustomer'
      responses:
        '201':
          description: Customer created
components:
  schemas:
    CreateCustomer:
      type: object
      required:
        - name
      properties:
        name:
          type: string
        nickname:
          type: string
          nullable: true
        age:
          type: integer
          minimum: 18
          exclusiveMinimum: true
~~~

Sau migration, document OpenAPI 3.1.1:

~~~yaml
openapi: 3.1.1
info:
  title: Customer API
  version: 1.4.0
paths:
  /customers:
    post:
      operationId: createCustomer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateCustomer'
      responses:
        '201':
          description: Customer created
components:
  schemas:
    CreateCustomer:
      type: object
      required:
        - name
      properties:
        name:
          type: string
        nickname:
          type:
            - string
            - 'null'
        age:
          type: integer
          exclusiveMinimum: 18
~~~

Trong ví dụ, path, method, operationId, request body, status và required property giữ nguyên. Hai chuyển đổi schema có thể bảo toàn tập dữ liệu hợp lệ:

- nickname vẫn chấp nhận chuỗi hoặc null; property vẫn optional vì không nằm trong required.
- age vẫn phải lớn hơn 18.

Nếu diff hiển thị các thay đổi schema tương ứng, reviewer cần xác nhận đây là thay đổi biểu diễn theo OAS version và fixture kiểm tra biên cho kết quả như nhau. Không cần coi thay đổi cú pháp này là breaking nếu ngữ nghĩa thực sự được giữ nguyên.

## 14. Ví dụ migration vô tình làm thay đổi contract

Giả sử candidate đổi nickname thành:

~~~yaml
nickname:
  type: string
~~~

Candidate không còn cho phép null. Consumer cũ gửi nickname: null có thể bị validation từ chối.

Hoặc candidate đổi age thành:

~~~yaml
age:
  type: integer
  minimum: 18
~~~

Giá trị 18 trước đây không hợp lệ nhưng nay được chấp nhận. Đây là thay đổi tập dữ liệu hợp lệ. Nó có thể không làm client cũ hỏng, nhưng semantics không còn tương đương và có thể ảnh hưởng nghiệp vụ.

Một ví dụ khác là thêm property bắt buộc:

~~~yaml
required:
  - name
  - countryCode
~~~

Client cũ chỉ gửi name sẽ không còn đáp ứng schema. Đây là breaking change theo hướng request. Nếu countryCode là yêu cầu mới của nghiệp vụ, cần có kế hoạch versioning hoặc giai đoạn chuyển tiếp thay vì chỉ sửa document.

## 15. Đưa so sánh vào CI sau khi nâng springdoc

Một pipeline có thể chạy theo trình tự:

1. Checkout baseline từ release hoặc commit đã được duyệt.
2. Build ứng dụng baseline và candidate bằng cấu hình tương ứng.
3. Khởi chạy từng bản trong môi trường test cô lập.
4. Tải cùng OpenAPI group từ hai bản.
5. Validate cả hai document.
6. Chạy oasdiff diff và lưu báo cáo đầy đủ.
7. Chạy oasdiff changelog để reviewer xem thay đổi ảnh hưởng consumer.
8. Chạy oasdiff breaking --fail-on ERR để chặn breaking change chưa được chấp thuận.
9. Chạy fixture schema và integration tests cho các payload/status quan trọng.
10. Review security, server URL, operationId, vendor extensions và SDK nếu có.
11. Lưu candidate document cùng báo cáo diff làm artifact của release.

Ví dụ lệnh PowerShell trong CI:

~~~powershell
oasdiff validate .\artifacts\openapi\baseline\orders-v1.json
if ($LASTEXITCODE -ne 0) { throw "Baseline OpenAPI document is invalid" }

oasdiff validate .\artifacts\openapi\candidate\orders-v1.json
if ($LASTEXITCODE -ne 0) { throw "Candidate OpenAPI document is invalid" }

oasdiff diff .\artifacts\openapi\baseline\orders-v1.json .\artifacts\openapi\candidate\orders-v1.json --format markdown
if ($LASTEXITCODE -ne 0) { throw "OpenAPI diff failed" }

oasdiff breaking --fail-on ERR .\artifacts\openapi\baseline\orders-v1.json .\artifacts\openapi\candidate\orders-v1.json
if ($LASTEXITCODE -ne 0) { throw "Breaking OpenAPI changes detected" }
~~~

Đường dẫn và bước tải artifact cần được điều chỉnh theo pipeline thực tế. Nếu diff phát hiện breaking change đã được phê duyệt có chủ đích, hãy lưu quyết định cùng báo cáo và áp dụng chính sách versioning tương ứng; không xóa baseline hoặc bỏ qua báo cáo để làm pipeline xanh.

## 16. Chọn công cụ so sánh phù hợp với phiên bản đặc tả

Một số công cụ có phạm vi hỗ trợ khác nhau:

| Công cụ | Phù hợp khi | Lưu ý |
|---|---|---|
| oasdiff | So sánh OpenAPI 3.0, 3.1 và 3.2; phân loại breaking/non-breaking | Có lệnh diff, changelog, breaking, validate và nhiều định dạng báo cáo |
| openapi-diff của OpenAPITools | Dự án đang so sánh document OpenAPI 3.0 | README của dự án công bố hỗ trợ OAS 3.0; kiểm tra hỗ trợ phiên bản trước khi dùng cho tài liệu 3.1/3.2 |
| Text diff của Git | Review thay đổi source YAML/JSON | Không phân tích semantics hoặc compatibility |

Với migration từ OAS 3.0 sang 3.1, chọn công cụ có parser hỗ trợ cả hai phiên bản. Theo tài liệu công bố, oasdiff hỗ trợ các phiên bản 3.0, 3.1 và 3.2; openapi-diff của OpenAPITools hiện mô tả hỗ trợ OpenAPI 3.0. Không chọn công cụ chỉ dựa vào tên gọi hoặc số lượng star; hãy kiểm tra phiên bản đặc tả mà tool thực sự parse được.

Pin version của công cụ diff trong CI. Cùng một cặp document nhưng phiên bản rule engine khác nhau có thể phân loại thay đổi khác nhau sau khi tool cập nhật rule hoặc sửa lỗi.

## 17. Những lỗi thường gặp khi đọc báo cáo

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Diff có nhiều thay đổi dù API không đổi | Chỉ so sánh text hoặc cấu trúc YAML | Dùng parser và semantic diff; phân loại thay đổi do biểu diễn |
| Diff không phát hiện runtime behavior change | OpenAPI document không mô tả hết logic thực thi | Bổ sung integration test và payload fixture |
| Báo breaking sau khi đổi OAS version | Schema migration làm đổi nullability, bounds hoặc required | So sánh ngữ nghĩa từng schema và kiểm tra payload ở biên |
| Không resolve được $ref | File reference thiếu, base URI sai hoặc external resource không truy cập được | Đóng gói reference, cố định base URI và kiểm tra quyền truy cập |
| Báo cáo quá nhiều thay đổi do đổi tên component | Refactor schema hoặc generator thay đổi tên model | Xác minh schema sau resolve có tương đương và kiểm tra SDK |
| Không có breaking change nhưng client vẫn lỗi | operationId, server URL, auth hoặc extension thay đổi | Review toolchain, security và môi trường gọi API |
| Kết quả CI khác máy local | Khác phiên bản oasdiff, config hoặc external ref | Pin tool version, lưu config và cố định input artifact |
| WARN bị bỏ qua | Chỉ fail trên ERR | Review WARN hoặc nâng mức fail theo chính sách nhóm |
| Candidate hợp lệ nhưng contract sai | Validate cú pháp không kiểm tra tương thích | Chạy diff, fixture và runtime contract test |
| Diff giữa hai group khác nhau | Baseline/candidate không cùng group hoặc filter | Xác minh tên group, URL và phạm vi operation trước khi so sánh |

## 18. Checklist xác nhận migration giữ đúng semantics

- [ ] Baseline và candidate thuộc cùng service, API version và group.
- [ ] Hai document được sinh từ cấu hình có thể tái lập.
- [ ] Cả hai document đều parse và validate thành công.
- [ ] paths và HTTP methods giữ đúng phạm vi dự kiến.
- [ ] Parameters giữ đúng in, required, style, explode và schema.
- [ ] Request body giữ đúng media type và tập giá trị hợp lệ.
- [ ] Response giữ đúng status code, media type, header và schema.
- [ ] Nullability, enum, bounds, required và composition được so sánh theo ngữ nghĩa.
- [ ] $ref, allOf, oneOf, anyOf và external schema được resolve đúng.
- [ ] Security scheme, OAuth scope và security requirement đã được review.
- [ ] Server URL và context path trỏ đúng endpoint public.
- [ ] operationId, component name và extension được kiểm tra nếu có SDK/gateway phụ thuộc.
- [ ] Đã chạy semantic diff và breaking-change report.
- [ ] Đã chạy payload fixture bằng validator đúng dialect.
- [ ] Đã kiểm tra runtime bằng integration/contract test.
- [ ] Breaking change có quyết định versioning và phê duyệt.
- [ ] Báo cáo diff và candidate artifact được lưu cùng release.

## 19. Tài liệu tham khảo chính thức

- [oasdiff — CLI Quick Start](https://www.oasdiff.com/docs/getting-started) — cài đặt, validate, diff, changelog, breaking, exit code và định dạng báo cáo.
- [oasdiff — Breaking Changes and Changelog](https://github.com/oasdiff/oasdiff/blob/main/docs/BREAKING-CHANGES.md) — phân loại ERR/WARN/INFO và cấu hình fail trong CI.
- [oasdiff — Diff](https://github.com/oasdiff/oasdiff/blob/main/docs/DIFF.md) — hành vi so sánh mặc định, matching inline schema với $ref và các tùy chọn ảnh hưởng cách diff.
- [oasdiff — Supported OpenAPI versions](https://www.oasdiff.com/diff) — phạm vi hỗ trợ OpenAPI 3.0, 3.1 và 3.2.
- [OpenAPITools — openapi-diff](https://github.com/OpenAPITools/openapi-diff) — công cụ so sánh OpenAPI; README hiện công bố hỗ trợ OpenAPI 3.0.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html) — cấu trúc và ngữ nghĩa của OpenAPI document.

So sánh ngữ nghĩa trước và sau migration là bước xác nhận hợp đồng API có giữ đúng ý nghĩa hay không. Hãy dùng cùng một group và baseline đáng tin cậy, validate từng document, chạy semantic diff, kiểm tra payload mẫu và review những thay đổi về security, server URL cùng SDK. Báo cáo công cụ giúp khoanh vùng thay đổi; quyết định phát hành vẫn cần dựa trên contract và hành vi consumer thực tế.
