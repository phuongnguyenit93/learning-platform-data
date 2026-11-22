# Đánh giá OpenAPI 3.2 theo hỗ trợ thực tế của toàn bộ bộ công cụ

OpenAPI 3.2 mở rộng cách mô tả API với streaming media types, HTTP QUERY, query string như một tham số hoàn chỉnh, tag phân cấp và OAuth 2.0 Device Authorization Flow. Tuy nhiên, một đặc tả hợp lệ theo chuẩn chưa chắc được mọi parser, validator, giao diện tài liệu hoặc code generator xử lý đúng.

Khi dùng springdoc-openapi, cần đánh giá riêng khả năng sinh tài liệu của Springdoc, mô hình dữ liệu của swagger-core, parser/validator, Swagger UI và công cụ sinh SDK. Không thể kết luận toàn bộ toolchain hỗ trợ OpenAPI 3.2 chỉ vì Swagger UI hiển thị được file hoặc dependency có số phiên bản 3.2.0.

Bài học này đánh giá tình hình hỗ trợ theo các bản phát hành và issue công khai được kiểm tra ngày 20-11-2026. Trạng thái của công cụ thay đổi theo release; trước mỗi lần nâng cấp, hãy kiểm tra lại phiên bản đang được khóa trong dự án và chạy bộ kiểm thử tương thích của chính API.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt phiên bản OpenAPI với phiên bản springdoc-openapi, swagger-core và Swagger UI.
- Giải thích những thay đổi đáng chú ý trong OpenAPI 3.2.
- Đánh giá riêng khả năng sinh, đọc, giữ nguyên, kiểm tra, hiển thị và sinh mã từ tài liệu 3.2.
- Nhận biết giới hạn hiện tại của Springdoc, swagger-core, swagger-parser và OpenAPI Generator.
- Chọn công cụ có hỗ trợ 3.2 thực tế cho từng công đoạn.
- Thiết kế pipeline CI để phát hiện trường mới bị mất hoặc bị diễn giải sai.
- Quyết định khi nào nên giữ OpenAPI 3.1 và khi nào có thể phát hành OpenAPI 3.2.
- Xây dựng kế hoạch chuyển đổi mà không làm hỏng client hoặc hợp đồng API hiện có.

## 1. Phân biệt các phiên bản trước khi đánh giá

OpenAPI Specification (OAS) là định dạng mô tả hợp đồng HTTP API. springdoc-openapi, swagger-core, Swagger UI, parser và generator là các sản phẩm sử dụng hoặc tạo ra định dạng đó. Số phiên bản của các sản phẩm này có chu kỳ phát hành riêng.

Ví dụ:

| Chuỗi phiên bản | Thuộc về | Ý nghĩa |
|---|---|---|
| openapi: 3.2.1 | OpenAPI Specification | Bộ quy tắc và cấu trúc của tài liệu API |
| springdoc-openapi: 3.2.0 | Springdoc | Phiên bản thư viện tích hợp Spring Boot và tạo tài liệu |
| swagger-core: 2.2.56 | Swagger Core | Thư viện Java chứa mô hình, annotation và chức năng đọc/ghi OpenAPI |
| swagger-ui: 5.34.0 | Swagger UI | Giao diện trình bày và thử API từ tài liệu |
| openapi-generator: 7.27.0 | OpenAPI Generator | Công cụ sinh SDK, server stub và tài liệu |

Không được suy ra springdoc-openapi 3.2.0 hỗ trợ OAS 3.2 chỉ vì hai chuỗi có cùng 3.2. Springdoc 3.2.0 là một release của thư viện, được xây dựng cho Spring Boot 4.1.x; đó là thông tin tương thích giữa hai sản phẩm Spring, không phải tuyên bố hỗ trợ mọi tính năng OAS 3.2.

### 1.1. OAS 3.2.0 và OAS 3.2.1

OpenAPI 3.2.0 được công bố ngày 19-09-2025. Bản vá 3.2.1 được công bố ngày 10-09-2026. Tính đến ngày 20-11-2026, 3.2.1 là bản OAS 3.2 mới nhất.

OAS dùng quy tắc phiên bản major.minor.patch:

- major.minor xác định tập tính năng của chuẩn.
- patch sửa lỗi hoặc làm rõ văn bản, không tạo một tập tính năng mới.
- Công cụ hỗ trợ OAS 3.2 nên xử lý các bản vá 3.2.x theo cùng bộ tính năng.

Vì vậy, một công cụ công bố hỗ trợ OAS 3.2.0 có thể dùng cho tài liệu 3.2.1 nếu nó tuân thủ quy tắc tương thích patch của OAS. Tuy nhiên, vẫn cần kiểm thử các trường được sửa hoặc làm rõ trong bản vá.

Ví dụ khai báo đầu tài liệu:

~~~yaml
openapi: 3.2.1
info:
  title: Product API
  version: 1.0.0
paths: {}
~~~

Trường info.version là phiên bản API do nhóm phát triển quản lý. Nó độc lập với trường gốc openapi.

## 2. Những tính năng đáng chú ý trong OpenAPI 3.2

Không phải mọi API đều cần dùng tính năng mới. Hãy xác định tính năng nào tạo giá trị cho hợp đồng hiện tại và kiểm tra công cụ hỗ trợ đúng tính năng đó.

### 2.1. Streaming media types và itemSchema

OpenAPI 3.2 mô tả cấu trúc của từng phần tử trong nội dung truyền tuần tự bằng itemSchema. Điều này hữu ích với Server-Sent Events (SSE), JSON Lines, JSON Text Sequences và một số kiểu multipart streaming.

Ví dụ:

~~~yaml
paths:
  /events:
    get:
      summary: Theo dõi sự kiện
      responses:
        '200':
          description: Luồng sự kiện liên tục
          content:
            text/event-stream:
              itemSchema:
                type: object
                required:
                  - event
                  - timestamp
                properties:
                  event:
                    type: string
                  timestamp:
                    type: string
                    format: date-time
                  data:
                    type: object
                    additionalProperties: true
~~~

itemSchema mô tả mỗi phần tử trong luồng. Nó không phải schema của một response JSON duy nhất. Công cụ chỉ hiểu schema truyền thống có thể đọc được tài liệu nhưng không biết cấu trúc từng sự kiện.

### 2.2. HTTP QUERY và additionalOperations

OAS 3.2 bổ sung operation query cho HTTP QUERY. Phương thức này cho phép mô tả truy vấn có request body, phù hợp với bộ lọc tìm kiếm phức tạp mà không phải nhồi toàn bộ tiêu chí vào URL.

~~~yaml
paths:
  /products/search:
    query:
      operationId: searchProducts
      summary: Tìm sản phẩm theo tiêu chí
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                text:
                  type: string
                categories:
                  type: array
                  items:
                    type: string
                priceRange:
                  type: object
                  properties:
                    minimum:
                      type: number
                    maximum:
                      type: number
      responses:
        '200':
          description: Kết quả tìm kiếm
~~~

additionalOperations mô tả các HTTP method khác ngoài các field cố định như get, post, put, delete, patch, head, options và trace. Ví dụ API có method COPY có thể đặt operation trong map additionalOperations.

~~~yaml
paths:
  /products/{id}:
    additionalOperations:
      COPY:
        operationId: copyProduct
        summary: Sao chép sản phẩm
        responses:
          '201':
            description: Sản phẩm đã được sao chép
~~~

Việc mô tả một method trong OpenAPI không làm cho Spring MVC, WebFlux, reverse proxy, WAF hoặc API gateway tự động hỗ trợ method đó. Cần kiểm tra cả khả năng định tuyến và hành vi runtime.

### 2.3. Querystring parameter

OAS 3.2 bổ sung vị trí parameter in: querystring. Parameter này biểu diễn toàn bộ query string như một giá trị, thay vì khai báo từng cặp key/value bằng nhiều parameter in: query.

~~~yaml
parameters:
  - name: filter
    in: querystring
    required: true
    content:
      application/x-www-form-urlencoded:
        schema:
          type: object
          properties:
            status:
              type: string
            includeArchived:
              type: boolean
            page:
              type: integer
~~~

querystring chỉ được xuất hiện tối đa một lần trong operation hoặc path item và không được kết hợp với parameter in: query trong cùng phạm vi. Nó dùng content để mô tả cách serialize toàn bộ query string; không dùng schema/style như parameter query thông thường.

Đây là tính năng dễ bị công cụ cũ bỏ qua hoặc biến đổi sai vì mô hình parameter trước đó chỉ có query, path, header và cookie.

### 2.4. Tag phân cấp

Tag trong OAS 3.2 có thêm summary, parent và kind. Có thể dùng chúng để tổ chức tài liệu theo cây, nhóm audience hoặc loại điều hướng.

~~~yaml
tags:
  - name: products
    summary: Sản phẩm
    kind: nav
  - name: product-search
    summary: Tìm kiếm sản phẩm
    parent: products
    kind: nav
  - name: partner
    summary: API đối tác
    kind: audience
~~~

parent tham chiếu tên tag cha đã khai báo. Không tạo vòng lặp cha/con. kind là chuỗi phân loại; các giá trị như nav, badge và audience thường được dùng trong công cụ tài liệu.

### 2.5. OAuth2 Device Authorization Flow và metadata

OAS 3.2 bổ sung deviceAuthorization cho OAuth2 flow, cùng deviceAuthorizationUrl, oauth2MetadataUrl và thuộc tính deprecated cho security scheme.

Ví dụ:

~~~yaml
components:
  securitySchemes:
    deviceOAuth:
      type: oauth2
      oauth2MetadataUrl: https://auth.example.com/.well-known/oauth-authorization-server
      flows:
        deviceAuthorization:
          deviceAuthorizationUrl: https://auth.example.com/device
          tokenUrl: https://auth.example.com/token
          scopes:
            events:read: Đọc sự kiện
~~~

Đây là cách mô tả luồng đăng nhập trên thiết bị có giao diện nhập liệu hạn chế. Authorization server vẫn phải triển khai flow thực tế; khai báo trong OpenAPI chỉ mô tả cơ chế cho client.

## 3. Hỗ trợ OAS 3.2 phải được đánh giá theo từng lớp

Một công cụ có thể nhận diện chuỗi openapi: 3.2.1 nhưng không hiểu field mới. Một công cụ khác có thể render được tài liệu nhưng không sinh được SDK. Vì vậy, không nên dùng một nhãn chung hỗ trợ 3.2 cho toàn bộ hệ thống.

| Mức | Khả năng | Câu hỏi kiểm tra |
|---|---|---|
| 1. Nhận diện | Đọc được version 3.2.x | Có từ chối tài liệu chỉ vì version mới không? |
| 2. Parse | Đọc cấu trúc JSON/YAML thành model | Có đọc được query, itemSchema, parent và querystring không? |
| 3. Round-trip | Đọc rồi ghi lại tài liệu | Field mới có bị mất hoặc đổi cấu trúc không? |
| 4. Validate | Kiểm tra đúng quy tắc OAS 3.2 và JSON Schema | Có phát hiện tổ hợp field sai theo chuẩn không? |
| 5. Render | Hiển thị đúng trong portal hoặc Swagger UI | Tag phân cấp và streaming có được trình bày đúng không? |
| 6. Generate | Sinh SDK, server stub hoặc tài liệu | Method và schema mới có xuất hiện đúng trong mã không? |
| 7. Runtime | Server và client thực hiện được hợp đồng | Framework, gateway và SDK có gửi/nhận đúng request thực tế không? |

Một kết quả tốt ở mức 5 không chứng minh mức 2, 3, 4, 6 hoặc 7. Hãy ghi trạng thái theo từng mức trong ma trận tương thích của dự án.

## 4. Tình hình hỗ trợ được kiểm tra ngày 20-11-2026

Ma trận dưới đây phản ánh tài liệu, release và issue công khai tại thời điểm kiểm tra. Chưa xác nhận nghĩa là nguồn chính thức chưa chứng minh đầy đủ tính năng OAS 3.2; không nên diễn giải thành tương thích hoàn toàn.

| Thành phần | Trạng thái được công bố | Đánh giá thực tế |
|---|---|---|
| OpenAPI Specification | OAS 3.2.1 là bản hiện hành | Chuẩn đã ổn định; dùng tài liệu 3.2.1 làm nguồn tham chiếu |
| Swagger UI | Bảng tương thích của 5.32.0 liệt kê OAS 3.2.0; Springdoc 3.2.0 nhúng Swagger UI 5.34.0 | Có thể dùng để render tài liệu 3.2, nhưng không chứng minh Springdoc sinh được 3.2 |
| Springdoc | Issue hỗ trợ OAS 3.2 #3324 vẫn ở trạng thái mở | Chưa xác nhận khả năng sinh OAS 3.2 đầy đủ từ controller |
| swagger-core | README nêu hỗ trợ 3.1; PR bổ sung SpecVersion.V32 và các model 3.2 vẫn đang mở | Không dựa vào nhãn chung 3.x để kết luận hỗ trợ field mới |
| swagger-parser | Issue hỗ trợ OAS 3.2 #2248 vẫn mở | Parser Java phổ biến này chưa phải lựa chọn đã xác nhận cho tài liệu 3.2 |
| OpenAPI Generator | README của 7.27.0 liệt kê 3.1 ở mức beta, không liệt kê 3.2 | Chưa dùng làm code generator mặc định cho hợp đồng 3.2 có tính năng mới |
| Redocly CLI | 2.82.0 phát hành ngày 19-11-2026; changelog có các sửa lỗi và tính năng riêng cho OAS 3.2 | Có thể dùng để lint, bundle và xử lý nhiều tính năng 3.2 |
| openapi-processor/openapi-parser | Công bố parse và validate OAS 3.2, 3.1, 3.0; hỗ trợ JSON Schema 2020-12 | Một lựa chọn Java để đánh giá parse/validate độc lập |
| JetBrains IDE | Tài liệu IntelliJ IDEA 2026.3 vẫn ghi hỗ trợ đến OAS 3.1 | Editor có thể báo sai hoặc không cung cấp coding assistance cho 3.2 |

### 4.1. Springdoc và sự nhầm lẫn về phiên bản 3.2.0

Springdoc-openapi 3.2.0 được phát hành ngày 24-10-2026 cho dòng Spring Boot 4.1.x. Release này dùng Swagger UI 5.34.0 và bổ sung các thay đổi của riêng Springdoc.

Trong khi đó, issue Add support for OpenAPI spec 3.2 của chính dự án Springdoc vẫn mở tại thời điểm kiểm tra. Vì vậy:

- Springdoc 3.2.0 không đồng nghĩa đầu ra có openapi: 3.2.0.
- Việc Swagger UI đi kèm render được một file OAS 3.2 không chứng minh Springdoc có thể tạo model 3.2.
- Cần kiểm tra trường openapi trong /v3/api-docs và các field mới trong JSON thực tế.

Với ứng dụng Spring Boot 3, Springdoc 2.x là dòng dành cho Spring Boot 3; không nâng lên Springdoc 3.x chỉ vì muốn dùng OAS 3.2. Việc nâng major Springdoc còn liên quan đến major Spring Boot và dependency tương ứng.

### 4.2. Swagger Core và swagger-parser

Swagger Core 2.2.56 được phát hành ngày 17-11-2026. README có bảng tương thích ghi 3.x, nhưng phần hướng dẫn cụ thể vẫn nói từ 2.2.0 hỗ trợ OpenAPI 3.1. Pull request swagger-core #5326 bổ sung SpecVersion.V32, additionalOperations, itemSchema, querystring và các trường khác của OAS 3.2 vẫn đang mở trong lần kiểm tra này.

swagger-parser có issue hỗ trợ OAS 3.2 từ tháng 11-2025 và vẫn mở trong lần kiểm tra này. Các thảo luận của dự án chỉ ra parser cần thay đổi cùng với mô hình swagger-core. Một tài liệu có openapi: 3.2.0 có thể bị parser cũ từ chối hoặc không đọc được operation query.

Điều này giải thích vì sao một công cụ render dựa trên JavaScript có thể hỗ trợ OAS 3.2 trong khi thư viện Java dùng để parse hoặc sinh mã vẫn chưa hỗ trợ.

### 4.3. Swagger UI và công cụ hiển thị

Swagger UI 5.32.0 công bố tương thích với OAS 3.2.0. Release Springdoc 3.2.0 nhúng Swagger UI 5.34.0, nên lớp hiển thị có thể mới hơn mốc tương thích được liệt kê.

Tuy nhiên, Swagger UI chỉ tiêu thụ tài liệu. Nếu /v3/api-docs do Springdoc tạo ra vẫn là OAS 3.1, giao diện không tự nâng tài liệu thành 3.2. Khi thử file 3.2 bên ngoài, hãy kiểm tra riêng streaming, tag phân cấp, QUERY và querystring; một trang không báo lỗi chưa đủ để chứng minh mọi tính năng được render đúng.

### 4.4. Redocly CLI và parser Java thay thế

Redocly CLI 2.x có tiến trình hỗ trợ 3.2 được ghi trong changelog:

- Từ 2.65.0, generate-spec có tùy chọn --openapi-version và mặc định tạo OAS 3.2.
- 2.64.1 sửa xử lý OAuth2 deviceAuthorization.
- 2.74.0 sửa lint cho components.mediaTypes, prefixEncoding và itemEncoding trong tài liệu 3.2.
- 2.78.0 bổ sung hỗ trợ querystring cho lệnh Respect.
- 2.82.0 là release hiện hành ngày 19-11-2026.

Với Java, openapi-processor/openapi-parser công bố parser và JSON Schema validator cho OAS 3.2/3.1/3.0, yêu cầu JDK 17 trở lên và dùng JSON Schema draft 2020-12 cho OAS 3.2. Đây là một lựa chọn để kiểm tra tài liệu độc lập với swagger-parser; vẫn cần thử trên các cấu trúc thực tế của API.

## 5. Không chỉ đổi trường openapi để nâng phiên bản

Thay:

~~~yaml
openapi: 3.1.0
~~~

thành:

~~~yaml
openapi: 3.2.1
~~~

không tự động làm tài liệu tương thích OAS 3.2. Nó chỉ đổi nhãn version. Nếu nội dung có itemSchema, query, additionalOperations hoặc in: querystring, các công cụ cũ có thể từ chối, bỏ qua hoặc làm mất chúng.

Ngay cả khi tài liệu chưa dùng field mới, một parser chỉ nhận diện đến 3.1 có thể từ chối version 3.2.1. Ngược lại, ép công cụ bỏ qua kiểm tra version có thể khiến nó âm thầm bỏ qua một operation mới.

### Những lỗi nguy hiểm khi ép công cụ cũ đọc 3.2

- Parser trả về null hoặc lỗi khi không nhận diện version.
- Field query bị bỏ qua và SDK không có method tương ứng.
- itemSchema bị mất khi serialize lại tài liệu.
- querystring bị chuyển thành parameter query thông thường, làm thay đổi cách serialize request.
- additionalOperations bị bỏ khỏi tài liệu hoặc không được sinh thành operation.
- Tag phân cấp bị làm phẳng, khiến portal hiển thị sai cấu trúc.
- Validator không phát hiện quy tắc sai vì nó không hiểu cấu trúc mới.

Không dùng tùy chọn bỏ qua validate như --skip-validate-spec để coi một tài liệu chưa được hỗ trợ là hợp lệ. Nếu công cụ không hiểu một method hoặc field, việc bỏ qua validate có thể làm mất dữ liệu mà không có lỗi rõ ràng.

## 6. Đánh giá tài liệu bằng một bộ fixture có tính năng 3.2

Tạo một fixture nhỏ chứa ít nhất các cấu trúc mà dự án dự định sử dụng. Không nên kiểm tra tương thích chỉ bằng một tài liệu đơn giản không có field mới.

Ví dụ fixture rút gọn:

~~~yaml
openapi: 3.2.1
info:
  title: OAS 3.2 Compatibility Fixture
  version: 1.0.0
tags:
  - name: events
    summary: Luồng sự kiện
    kind: nav
  - name: event-details
    summary: Chi tiết sự kiện
    parent: events
    kind: nav
paths:
  /events:
    get:
      tags:
        - events
      responses:
        '200':
          description: Luồng sự kiện
          content:
            text/event-stream:
              itemSchema:
                type: object
                properties:
                  event:
                    type: string
                  timestamp:
                    type: string
                    format: date-time
    query:
      operationId: searchEvents
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                eventType:
                  type: string
      responses:
        '200':
          description: Kết quả tìm kiếm
components:
  securitySchemes:
    deviceOAuth:
      type: oauth2
      flows:
        deviceAuthorization:
          deviceAuthorizationUrl: https://auth.example.com/device
          tokenUrl: https://auth.example.com/token
          scopes:
            events:read: Đọc sự kiện
~~~

Fixture trên có các tính năng mới: tag phân cấp, streaming itemSchema, HTTP QUERY và device authorization. Có thể bổ sung một parameter in: querystring và additionalOperations vào fixture riêng để cô lập lỗi của từng parser.

### 6.1. Kiểm tra parse và round-trip

Với mỗi công cụ parser:

1. Đọc fixture OAS 3.2.1.
2. Kiểm tra model có đủ query, itemSchema, parent, kind và deviceAuthorization.
3. Serialize model trở lại JSON hoặc YAML.
4. Parse lại kết quả vừa serialize.
5. So sánh cấu trúc quan trọng trước và sau round-trip.

Không chỉ so sánh text vì formatter có thể đổi thứ tự key hoặc cách xuống dòng. So sánh cây dữ liệu đã parse và xác nhận mọi field quan trọng còn nguyên.

### 6.2. Kiểm tra validate

Validator cần hiểu đúng version 3.2 và các quy tắc mới. Với querystring, kiểm tra trường hợp hợp lệ và không hợp lệ:

- Một operation có một querystring parameter.
- Không đồng thời khai báo querystring và query trong cùng phạm vi.
- Không có nhiều hơn một querystring parameter.
- querystring dùng content thay vì schema/style.

Với itemSchema, kiểm tra schema của từng phần tử trong stream. Với tag, kiểm tra parent tồn tại và không tạo chu trình. Với OAuth2 device flow, kiểm tra deviceAuthorizationUrl và tokenUrl.

### 6.3. Kiểm tra render

Mở fixture trong phiên bản Swagger UI hoặc portal được chọn. Kiểm tra:

- Tag con được đặt dưới tag cha.
- text/event-stream hiển thị schema của từng item.
- QUERY được hiển thị như một method riêng.
- Request body của QUERY xuất hiện đúng.
- Device authorization được nhận diện trong security scheme.

Nếu UI render thiếu một phần, so sánh JSON nguồn trước khi kết luận lỗi nằm ở parser hay UI.

### 6.4. Kiểm tra code generation

Nếu dùng code generator, hãy xác minh:

- Generator không từ chối openapi: 3.2.1.
- QUERY được sinh thành method/client call tương ứng.
- Request body của QUERY được giữ nguyên.
- Streaming được biểu diễn thành kiểu trả về phù hợp với runtime.
- Các operation trong additionalOperations không bị bỏ qua.
- Parameter querystring được serialize thành toàn bộ query string theo media type đã mô tả.

Build thành công không có nghĩa SDK đúng. Hãy kiểm tra source code sinh ra và chạy test request trên server mock hoặc contract test.

## 7. Vai trò của Springdoc khi dự án cần OAS 3.2

Springdoc rất phù hợp để tự động tạo OpenAPI từ controller, DTO và annotation Spring. Tuy nhiên, khi phiên bản model mà Springdoc phụ thuộc chưa có đầy đủ các field OAS 3.2, customizer không thể tự biến mọi cấu trúc Java thành một mô hình 3.2 hoàn chỉnh.

Hãy xác định rõ nguồn sự thật của hợp đồng:

### Cách A: Giữ Springdoc làm nguồn sinh và dùng OAS 3.1

Chọn cách này khi:

- API dùng các cấu trúc HTTP thông thường đã được Springdoc hỗ trợ.
- Không cần QUERY, streaming itemSchema, querystring hoặc field mới khác.
- Client và pipeline hiện tại dựa trên swagger-parser/OpenAPI Generator.

Tiếp tục phát hành OAS 3.1.2 (hoặc phiên bản 3.1.x đã được bộ công cụ xác nhận). Không cần nâng version chỉ để có số mới hơn.

### Cách B: Duy trì một hợp đồng OAS 3.2 độc lập

Chọn cách này khi API thực sự cần các tính năng 3.2 và Springdoc chưa thể sinh chúng. Có thể quản lý file OpenAPI 3.2.1 như một artifact có nguồn gốc và review riêng, sau đó kiểm tra bằng parser/validator có hỗ trợ 3.2.

Khi dùng cách này:

- Xác định rõ file OAS 3.2.1 là hợp đồng phát hành.
- Dùng Springdoc để đối chiếu endpoint và schema được suy ra từ ứng dụng.
- Duy trì kiểm tra chênh lệch giữa controller/runtime và hợp đồng.
- Không ghi đè file OAS 3.2 bằng tài liệu 3.1 sinh tự động.
- Ghi lại các phần được mô tả thủ công và người chịu trách nhiệm cập nhật.

### Cách C: Tạo tài liệu nền rồi áp dụng bước chuyển đổi có kiểm soát

Một pipeline có thể lấy OpenAPI do Springdoc sinh làm tài liệu nền rồi áp dụng transform/overlay để bổ sung metadata 3.2. Cách này chỉ phù hợp khi:

- Transform sử dụng parser/model có hiểu OAS 3.2.
- Không sửa text JSON/YAML bằng replace chuỗi toàn cục.
- Mỗi field được thêm có test xác minh.
- Round-trip không làm mất các field 3.2.
- Hợp đồng cuối cùng được validate bằng công cụ hỗ trợ 3.2.

Đây là một pipeline riêng cần sở hữu và kiểm thử. Nó không có nghĩa Springdoc đã hỗ trợ OAS 3.2.

## 8. Ma trận lựa chọn theo nhu cầu

| Nhu cầu | Hướng lựa chọn |
|---|---|
| Sinh tài liệu tự động từ Spring Boot và dùng REST thông thường | Springdoc với OAS 3.1 |
| Hiển thị file OAS 3.2.1 | Swagger UI phiên bản hỗ trợ 3.2 hoặc portal đã xác nhận |
| Lint/bundle tài liệu OAS 3.2 | Redocly CLI phiên bản có hỗ trợ 3.2 |
| Parse/validate OAS 3.2 trong Java | Đánh giá openapi-processor/openapi-parser |
| Sinh SDK từ OAS 3.2 có QUERY hoặc streaming | Chưa mặc định dùng OpenAPI Generator 7.27.0; cần chờ hỗ trợ hoặc chọn generator khác đã kiểm thử |
| Dùng QUERY trong controller Spring | Kiểm tra hỗ trợ của Spring Framework, Spring MVC/WebFlux, gateway và Springdoc riêng |
| Tổ chức tag phân cấp | Chỉ phát hành sau khi parser và renderer giữ đúng parent, summary, kind |
| API có SSE/JSONL streaming | Kiểm tra itemSchema, generator và runtime streaming độc lập |

## 9. Pipeline CI cho OpenAPI 3.2

Pipeline nên kiểm tra cùng một artifact qua các công đoạn, không để mỗi công cụ đọc một file khác nhau.

Một quy trình tham khảo:

~~~text
Source controllers / OpenAPI source
             |
             v
       Generate document
             |
             v
      Parse as OAS 3.2.1
             |
             v
       Validate structure
             |
             v
      Lint and bundle refs
             |
             v
       Render documentation
             |
             v
       Generate SDK / stubs
             |
             v
     Contract and runtime tests
             |
             v
        Publish artifact
~~~

Ở mỗi bước, lưu lại version công cụ và checksum của file đầu vào. Nếu một bước tạo ra file mới, bước tiếp theo phải dùng chính file đó và có test xác nhận không mất field.

### 9.1. Khóa phiên bản công cụ

Không dùng latest hoặc version range mở trong pipeline quan trọng. Pin:

- Springdoc và Spring Boot.
- swagger-core, swagger-annotations và Swagger UI được resolve thực tế.
- Redocly CLI hoặc parser/validator.
- OpenAPI Generator nếu đang dùng.
- Runtime/browser dùng để kiểm tra render.

Khi nâng cấp, chạy lại fixture có các field 3.2. Không dựa vào việc release mới có version lớn hơn để kết luận hỗ trợ chuẩn mới.

### 9.2. Ví dụ kiểm tra với Redocly CLI

Với Redocly CLI 2.x đã xác nhận hỗ trợ 3.2:

~~~bash
npx @redocly/cli lint openapi/openapi.yaml
npx @redocly/cli bundle openapi/openapi.yaml --output build/openapi-bundled.yaml
~~~

Pin CLI trong devDependencies và khóa file lock của npm để kết quả không đổi giữa các lần build. Nếu dùng rule set riêng, kiểm tra các rule không vô tình loại field mới hoặc cấm tính năng hợp lệ của 3.2.

### 9.3. Chặn việc mất field

Tạo assertion cho các node quan trọng:

| Đường dẫn JSON | Giá trị cần kiểm tra |
|---|---|
| openapi | 3.2.1 |
| paths./events.get.responses.200.content.text/event-stream.itemSchema | Schema item còn nguyên |
| paths./products/search.query | Operation QUERY còn nguyên |
| tags[1].parent | Tag cha còn nguyên |
| components.securitySchemes.deviceOAuth.flows.deviceAuthorization | Device flow còn nguyên |

Với querystring và additionalOperations, thêm fixture riêng để assertion không bị bỏ sót do ví dụ đơn giản.

## 10. Đánh giá rủi ro khi dùng công cụ chưa hỗ trợ

| Cách làm | Rủi ro |
|---|---|
| Chỉ đổi openapi từ 3.1 lên 3.2 | Tài liệu tuyên bố một chuẩn nhưng không tuân thủ field/rule mới |
| Dùng UI render được rồi kết luận toolchain đạt | Parser, validator và generator có thể vẫn thất bại |
| Dùng --skip-validate-spec | Operation hoặc field mới có thể bị bỏ âm thầm |
| Parse rồi serialize bằng model 3.1 | Field không có trong model có thể bị mất |
| Chỉnh file bằng regex | Có thể làm hỏng $ref, YAML hoặc cấu trúc lồng nhau |
| Dùng Springdoc 3.2.0 với suy luận cùng version | Nhầm phiên bản thư viện với phiên bản chuẩn |
| Nâng đồng thời mọi dependency | Khó xác định thành phần nào làm thay đổi hợp đồng |
| Không kiểm tra runtime của QUERY/SSE | Tài liệu đúng nhưng server/gateway không thực hiện được |

## 11. Kế hoạch chuyển đổi từ OpenAPI 3.1

Khi quyết định chuyển sang 3.2, có thể triển khai theo các bước:

1. Lập danh sách client, SDK, portal, mock server, validator và code generator đang tiêu thụ OpenAPI.
2. Ghi phiên bản hiện tại của từng công cụ và xác minh tài liệu tương thích chính thức.
3. Chọn một fixture 3.2.1 chứa các tính năng dự kiến dùng.
4. Kiểm tra parse, round-trip, validate, render và generate độc lập.
5. Đánh giá tác động của QUERY, streaming, querystring và tag hierarchy tới runtime.
6. Chọn nguồn sự thật: Springdoc 3.1, tài liệu 3.2 độc lập hoặc pipeline transform.
7. Giữ artifact 3.1 hiện tại để đối chiếu và rollback.
8. Sinh SDK thử nghiệm và kiểm tra khác biệt về method, schema và serialization.
9. Chạy contract test với server thật hoặc môi trường tích hợp.
10. Công bố tài liệu mới cho một nhóm client thử nghiệm.
11. Theo dõi lỗi parser, render, codegen và request thực tế.
12. Chỉ chuyển toàn bộ consumer sau khi từng công cụ đạt tiêu chí chấp nhận.

Không xóa tài liệu 3.1 hoặc thay endpoint artifact đang được client dùng trước khi có kế hoạch tương thích và versioning rõ ràng.

## 12. Bài thực hành tổng hợp

Đánh giá một dự án Spring Boot có Springdoc, Swagger UI, validator và OpenAPI Generator:

1. Ghi lại version thực tế của Spring Boot, Springdoc, swagger-core, Swagger UI và OpenAPI Generator.
2. Gọi /v3/api-docs và xác định OAS version mà Springdoc đang sinh.
3. Tạo fixture OAS 3.2.1 chứa itemSchema, query, tag hierarchy và deviceAuthorization.
4. Thêm một parameter in: querystring và một additionalOperations vào fixture thứ hai.
5. Mở fixture trong Swagger UI và kiểm tra các tính năng mới.
6. Chạy Redocly CLI lint/bundle và ghi lại cảnh báo.
7. Dùng một Java parser có hỗ trợ 3.2 để parse, validate và round-trip.
8. Thử OpenAPI Generator hiện tại; ghi rõ lỗi, warning hoặc field bị bỏ.
9. So sánh kết quả với tài liệu tương thích chính thức của từng công cụ.
10. Xác định tính năng nào Springdoc có thể sinh tự động và tính năng nào phải quản lý trong hợp đồng 3.2 riêng.
11. Viết test để xác nhận field không mất sau mỗi bước transform.
12. Đưa kết quả vào ma trận tương thích và đề xuất quyết định phát hành.

### Tiêu chí hoàn thành

- [ ] Phân biệt được OAS 3.2.1 với springdoc-openapi 3.2.0.
- [ ] Nêu được ít nhất ba tính năng mới của OAS 3.2.
- [ ] Có ma trận hỗ trợ riêng cho Springdoc, model, parser, validator, UI và generator.
- [ ] Không kết luận hỗ trợ đầy đủ chỉ dựa vào Swagger UI.
- [ ] Fixture 3.2.1 parse và validate bằng công cụ đã xác nhận hỗ trợ.
- [ ] Round-trip không làm mất itemSchema, query, querystring, tag hierarchy và security flow.
- [ ] Code generator được kiểm tra với các operation và schema mới.
- [ ] Runtime của QUERY/streaming được kiểm tra ngoài tài liệu.
- [ ] CI pin version công cụ và kiểm tra field quan trọng.
- [ ] Có kế hoạch chuyển đổi/rollback và người sở hữu hợp đồng.

## Tiếp tục học

Sau bài này, hãy kết hợp quản lý OpenAPI version với contract testing, code generation, API governance và phân phối tài liệu. Khi một công cụ công bố hỗ trợ OAS 3.2, hãy kiểm tra đúng release và đúng tính năng cần dùng; khả năng tương thích của một mắt xích không đại diện cho toàn bộ chuỗi.

## Tài liệu tham khảo

- [OpenAPI Specification 3.2.1](https://spec.openapis.org/oas/v3.2)
- [OpenAPI 3.2.0 – Revision history and versioning](https://spec.openapis.org/oas/v3.2.0.html)
- [Swagger: hỗ trợ OpenAPI 3.2.0 trong hệ sinh thái Swagger](https://swagger.io/blog/swagger-launches-support-for-openapi-3-2-0/)
- [Swagger UI compatibility table](https://github.com/swagger-api/swagger-ui)
- [Springdoc issue: Add support for OpenAPI spec 3.2](https://github.com/springdoc/springdoc-openapi/issues/3324)
- [Swagger Core – compatibility and releases](https://github.com/swagger-api/swagger-core)
- [Swagger Core PR: OpenAPI 3.2 model support](https://github.com/swagger-api/swagger-core/pull/5326)
- [Swagger Parser issue: Support for OpenAPI Spec 3.2](https://github.com/swagger-api/swagger-parser/issues/2248)
- [OpenAPI Generator – compatibility](https://github.com/OpenAPITools/openapi-generator)
- [Redocly CLI changelog](https://redocly.com/docs/cli/changelog)
- [openapi-processor/openapi-parser](https://github.com/openapi-processor/openapi-parser)
- [IntelliJ IDEA – OpenAPI support](https://www.jetbrains.com/help/idea/openapi.html)
