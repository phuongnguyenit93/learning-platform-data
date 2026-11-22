# Phân biệt khả năng của đặc tả với khả năng của Springdoc và giao diện

Khi nói một API “hỗ trợ OpenAPI 3.1”, cần xác định đang nói tới lớp nào. **OpenAPI Specification (OAS)** định nghĩa cấu trúc và ngữ nghĩa của tài liệu mô tả API. **springdoc-openapi** đọc ứng dụng Spring Boot rồi tạo tài liệu theo khả năng mà thư viện hỗ trợ. **Swagger UI** đọc tài liệu đó để hiển thị và cho người dùng thử gọi API. Ba thành phần có liên quan nhưng không có cùng phạm vi trách nhiệm.

Một tính năng được định nghĩa trong OAS không tự động có nghĩa springdoc có thể suy ra nó từ controller, hoặc Swagger UI có thể hiển thị và thực thi nó đầy đủ. Ngược lại, một tùy chọn giao diện như bật nút Try it out không làm thay đổi hợp đồng OpenAPI. Muốn đánh giá đúng khả năng của hệ thống, phải kiểm tra riêng đặc tả, bộ sinh tài liệu, giao diện và công cụ tiêu thụ.

## 1. Ba lớp trong chuỗi tài liệu API

~~~mermaid
flowchart TD
    A["Spring Boot application"] --> B["springdoc-openapi"]
    B --> C["OpenAPI Description JSON/YAML"]
    C --> D["Swagger UI"]
    C --> E["Validator / Linter"]
    C --> F["Client generator"]
    C --> G["Contract tests / API gateway"]
    D --> H["Browser renders documentation"]
    D --> I["Try it out sends HTTP request"]
    I --> A
~~~

| Thành phần | Vai trò chính | Không tự làm việc gì? |
|---|---|---|
| **OpenAPI Specification** | Định nghĩa chuẩn mô tả HTTP API, các object, field và quy tắc diễn giải | Không tạo controller, không chạy server, không xác thực request |
| **springdoc-openapi** | Phân tích ứng dụng Spring, annotation và cấu hình để sinh OpenAPI Description | Không thay thế đặc tả, không tự biết toàn bộ quy tắc nghiệp vụ ẩn trong code |
| **Swagger UI** | Đọc OpenAPI Description, hiển thị operation/schema và cung cấp giao diện tương tác | Không sinh hợp đồng từ controller, không thay đổi route hoặc quyền truy cập của server |

OpenAPI Description có thể được dùng độc lập bởi nhiều công cụ như validator, code generator, API gateway, contract test hoặc cổng tài liệu. Swagger UI chỉ là một trong các cách tiêu thụ tài liệu đó.

## 2. OpenAPI Specification định nghĩa điều gì?

OAS là chuẩn mô tả giao diện HTTP API, độc lập với ngôn ngữ lập trình. Một OpenAPI document có thể được biểu diễn bằng JSON hoặc YAML. Các object thường gặp gồm:

- **openapi**: phiên bản của OpenAPI Specification mà tài liệu sử dụng.
- **info**: tên, mô tả, liên hệ và phiên bản của tài liệu API.
- **servers**: các địa chỉ server mà client có thể gọi.
- **paths**: path, HTTP method và operation.
- **components**: schema, response, parameter, request body và security scheme có thể tái sử dụng.
- **security**: yêu cầu bảo mật ở cấp tài liệu hoặc operation.
- **tags**: nhóm operation về mặt tài liệu.

Ví dụ một tài liệu nhỏ:

~~~yaml
openapi: 3.1.0
info:
  title: Catalog API
  version: 2.4.0
  description: API quản lý danh mục sản phẩm.
servers:
  - url: https://api.example.com
paths:
  /products:
    get:
      operationId: listProducts
      summary: Liệt kê sản phẩm
      responses:
        "200":
          description: Danh sách sản phẩm
components:
  schemas:
    Product:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
~~~

Tài liệu trên mô tả một operation GET và schema Product. Nó không tạo endpoint /products trong ứng dụng. Nếu server chưa triển khai route đó, OpenAPI document vẫn có thể mô tả nó nhưng request thực tế sẽ thất bại.

### Đặc tả quy định hợp đồng, không thực thi hợp đồng

Ví dụ schema có required, minimum, format hoặc response 404 giúp client hiểu dữ liệu hợp lệ và các kết quả có thể xảy ra. Nhưng việc server có thực sự từ chối dữ liệu sai, trả đúng status code hoặc kiểm tra quyền hay không phụ thuộc implementation và kiểm thử runtime.

Tương tự:

- **security** mô tả cơ chế bảo vệ; không bật Spring Security.
- **servers** mô tả địa chỉ; không cấu hình DNS, TLS hay reverse proxy.
- **deprecated: true** thông báo operation đã lỗi thời; không tự ngừng route.
- **readOnly** và **writeOnly** mô tả cách dùng schema; không tự ngăn code ghi hoặc đọc property.

## 3. Springdoc làm gì với ứng dụng Spring Boot?

springdoc-openapi là thư viện tích hợp Spring Boot. Nó phân tích các thông tin mà ứng dụng công bố được, chẳng hạn:

- Mapping từ @RestController, @RequestMapping, @GetMapping, @PostMapping.
- Kiểu tham số, @PathVariable, @RequestParam, @RequestHeader và request body.
- Kiểu trả về và response metadata.
- Annotation Swagger/OpenAPI như @Operation, @Parameter, @Schema, @ApiResponse.
- Ràng buộc Bean Validation và một số quy ước serialization.
- Cấu hình OpenAPI, GroupedOpenApi, customizer và các integration được hỗ trợ.

Từ những thông tin đó, springdoc tạo OpenAPI Description, thường được phục vụ ở /v3/api-docs và /v3/api-docs.yaml. Nó có thể tạo nhiều tài liệu theo group, bổ sung metadata bằng annotation hoặc customizer và phục vụ Swagger UI nếu dùng starter có giao diện.

### Springdoc chỉ có thể sinh điều mà nó nhận biết được

Một số hành vi nằm trong service, filter, converter, router tự viết hoặc logic điều kiện có thể không suy ra đầy đủ từ controller. Ví dụ:

- Handler trả ResponseEntity<?> nhưng payload thực tế thay đổi theo nhánh nghiệp vụ.
- Functional route hoặc endpoint tùy biến cần metadata tường minh.
- Exception handler dùng status code riêng.
- Serializer đổi tên field hoặc bỏ field tùy theo user role.
- Quyền truy cập phụ thuộc tenant, scope hoặc trạng thái dữ liệu.

Khi springdoc không thể suy ra chính xác, hãy bổ sung annotation hoặc dùng extension point phù hợp như OperationCustomizer, OpenApiCustomizer hay khai báo OpenAPI model. Sau đó đối chiếu tài liệu với response và hành vi runtime. Không mặc định tài liệu sinh tự động luôn phản ánh toàn bộ nghiệp vụ.

### Springdoc không phải OpenAPI Specification

springdoc có thể hỗ trợ một phần các object và tính năng của OAS, nhưng phạm vi hỗ trợ cụ thể phụ thuộc phiên bản thư viện, swagger-core và cách ứng dụng khai báo metadata. Một tính năng có trong chuẩn nhưng chưa được springdoc tự động tạo ra vẫn có thể cần khai báo thủ công hoặc customizer, nếu phiên bản thư viện có mô hình tương ứng.

Ngược lại, một property riêng của springdoc như springdoc.paths-to-match hoặc springdoc.api-docs.version là cấu hình của bộ sinh tài liệu. Những property này không phải field trong OpenAPI document.

## 4. Swagger UI làm gì với OpenAPI Description?

Swagger UI là ứng dụng web đọc OpenAPI Description và tạo giao diện cho người dùng. Nó thường:

- Hiển thị title, version, servers và thông tin mô tả.
- Nhóm operation theo tag.
- Hiển thị path, method, parameter, request body, response và schema.
- Cung cấp nút Authorize dựa trên security scheme được mô tả.
- Cho phép thử gửi HTTP request bằng tính năng Try it out nếu được bật.
- Hỗ trợ tùy chỉnh layout, sorter, filter, theme và plugin.

Swagger UI không tạo OpenAPI document từ Spring controller. Nó nhận document đã có và hiển thị theo khả năng của phiên bản giao diện.

Swagger UI mặc định không thay thế một OpenAPI validator. Có thể cấu hình validator riêng, nhưng việc giao diện tải và render được document không phải bằng chứng rằng document tuân thủ mọi quy tắc của OAS.

### Giao diện có thể giới hạn thao tác mà không thay đổi đặc tả

Ví dụ, Swagger UI có cấu hình supportedSubmitMethods. Nếu danh sách này rỗng, nút Try it out có thể bị vô hiệu hóa cho mọi operation. Các operation vẫn còn trong OpenAPI document và vẫn có thể được hiển thị.

Tương tự, tryItOutEnabled điều khiển trạng thái mặc định của phần thử request. Nó không xóa operation, không thay đổi method được API hỗ trợ và không thay đổi hợp đồng.

Nếu Try it out không hoạt động, hãy kiểm tra cấu hình giao diện, CORS, servers, xác thực và kết nối tới API. Đừng kết luận rằng OpenAPI Specification không hỗ trợ operation chỉ vì giao diện không gửi được request.

## 5. Bốn phiên bản không được nhầm lẫn

Trong một dự án, có thể đồng thời tồn tại nhiều số phiên bản:

| Vị trí | Ví dụ | Ý nghĩa |
|---|---|---|
| Field openapi | 3.1.0 | Phiên bản OpenAPI Specification của document |
| Field info.version | 2.4.0 | Phiên bản của OpenAPI document; dự án thường dùng để thể hiện phiên bản API |
| Dependency springdoc | 2.x hoặc 3.x | Phiên bản thư viện tích hợp Spring Boot |
| Swagger UI assets | 5.x | Phiên bản ứng dụng giao diện được đóng gói hoặc phục vụ |

Ngoài ra, dự án còn có phiên bản Spring Boot, Spring Framework, swagger-core, validator và client generator. Mỗi thành phần có vòng đời và ma trận tương thích riêng.

### openapi không phải info.version

Trong ví dụ:

~~~yaml
openapi: 3.1.0
info:
  title: Catalog API
  version: 2.4.0
~~~

3.1.0 nói rằng document dùng cú pháp và ngữ nghĩa của OpenAPI 3.1. 2.4.0 là phiên bản của document được mô tả trong Info Object. Nhiều dự án đặt info.version trùng với phiên bản phát hành API để client dễ nhận biết, nhưng hai field vẫn có ý nghĩa khác nhau.

Đổi info.version không tự chuyển document từ OpenAPI 3.0 sang 3.1. Đổi field openapi bằng cách sửa chuỗi cũng không tự chuyển đổi schema hoặc làm công cụ sinh tài liệu hỗ trợ tính năng mới.

### Phiên bản springdoc không phải phiên bản OpenAPI

Nâng springdoc có thể nâng swagger-core, Swagger UI và thay đổi cách tài liệu được sinh. Tuy nhiên, dependency version không phải field openapi trong document. Phải đọc document đầu ra để biết OAS version thực tế.

Tương tự, nâng Swagger UI không tự nâng OAS document mà server đang phát. Giao diện có thể hiểu được nhiều phiên bản đặc tả hơn, nhưng nó không sửa nội dung document.

## 6. Khác biệt giữa các phiên bản OpenAPI ảnh hưởng tới schema

Các phiên bản OAS có thể định nghĩa cách biểu diễn schema khác nhau. Một ví dụ dễ gặp là giá trị nullable.

Trong OpenAPI 3.0, schema thường dùng nullable: true:

~~~yaml
type: string
nullable: true
~~~

Trong OpenAPI 3.1, Schema Object dựa trên JSON Schema hiện đại hơn; giá trị null có thể được biểu diễn trong type:

~~~yaml
type:
  - string
  - "null"
~~~

Đây là khác biệt ở ngôn ngữ đặc tả. Công cụ sinh tài liệu, validator, UI và client generator phải hiểu đúng phiên bản để diễn giải schema. Nếu đổi field openapi nhưng giữ nguyên cách biểu diễn cũ, document có thể sai hoặc bị công cụ diễn giải khác nhau.

OpenAPI 3.1 cũng thay đổi cách Schema Object liên kết với JSON Schema, mở rộng khả năng dùng các từ vựng và cấu trúc schema. Không nên giả định mọi validator hoặc generator hỗ trợ đầy đủ mọi tính năng JSON Schema chỉ vì chúng nhận được một document mang nhãn 3.1.

## 7. Chọn phiên bản OpenAPI trong springdoc

Với springdoc, phiên bản tài liệu được cấu hình bằng property:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

Trong các tài liệu cấu hình springdoc 2.x, springdoc.api-docs.version được mô tả là lựa chọn giữa OpenAPI 3.0 và 3.1; giá trị mặc định được ghi là openapi_3_1. Ví dụ cấu hình cho 3.0:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_0
~~~

Hãy kiểm tra tài liệu của đúng nhánh springdoc đang dùng. Không suy ra một phiên bản OAS mới được hỗ trợ chỉ vì phiên bản đặc tả đó đã được OpenAPI Initiative phát hành.

Property này chỉ chọn phiên bản document mà springdoc tạo ra trong phạm vi phiên bản thư viện hỗ trợ. Nó không:

- Thay đổi phiên bản API trong info.version.
- Nâng Spring Boot hoặc springdoc dependency.
- Nâng Swagger UI assets.
- Bảo đảm validator và code generator phía người dùng hỗ trợ cùng phiên bản.
- Chuyển đổi mọi custom schema hoặc extension sang ngữ nghĩa mới một cách tự động.

Sau khi đổi property, hãy đọc /v3/api-docs để xác nhận field openapi và kiểm tra các schema nhạy cảm với phiên bản.

## 8. Ma trận tương thích phải xét cả chuỗi

Một hệ thống có thể dùng đặc tả mới nhưng một thành phần tiêu thụ cũ. Ví dụ:

| Lớp | Cần xác minh |
|---|---|
| Spring Boot | Phiên bản này được nhánh springdoc đang dùng hỗ trợ không? |
| springdoc-openapi | Có thể tạo đúng OAS version và các object cần dùng không? |
| swagger-core/model | Mô hình Java và serializer có giữ được field/schema cần thiết không? |
| Swagger UI | Parser và renderer có hỗ trợ OAS version cùng các feature được dùng không? |
| Validator/linter | Có validate theo đúng OAS version và dialect không? |
| Client generator | Có sinh client đúng schema, parameter và security không? |
| API gateway/contract test | Có hiểu cùng document và thực thi đúng policy không? |

Ví dụ ma trận tương thích của springdoc hiện phân biệt nhánh 2.x cho Spring Boot 3.x và nhánh 3.x cho Spring Boot 4.x. Với dự án cũ trên Spring Boot 2.x/1.x, cần theo nhánh hỗ trợ tương ứng thay vì chỉ nâng springdoc lên bản mới nhất.

### Ví dụ về khoảng cách phiên bản tại thời điểm viết

Tại ngày 20-11-2026:

- OpenAPI Specification đã công bố phiên bản 3.2.1.
- Trang cấu hình springdoc hiện mô tả springdoc.api-docs.version để chọn OpenAPI 3.0 hoặc 3.1.
- Bảng tương thích của Swagger UI 5.32.0 liệt kê hỗ trợ tới OpenAPI 3.2.0.

Các mốc này cho thấy việc đặc tả đã phát hành một phiên bản mới không đồng nghĩa mọi bộ sinh và giao diện đã hỗ trợ cùng phiên bản đó. Khi chọn OAS 3.2.x, hãy kiểm tra chính xác phiên bản springdoc, swagger-core và Swagger UI đang được dùng; không chỉ dựa vào phiên bản mới nhất của chuẩn.

Các ma trận tương thích thay đổi theo release. Hãy xem tài liệu và dependency thực tế của dự án tại thời điểm nâng cấp.

## 9. Phân biệt tính năng của OAS với khả năng sinh tự động

Một số tính năng có thể được mô tả trong OpenAPI nhưng không tự suy ra từ Spring controller:

| Tính năng trong OAS | Springdoc có thể làm gì? | Khi nào cần bổ sung? |
|---|---|---|
| servers | Có thể tạo hoặc nhận cấu hình server tùy cách ứng dụng triển khai | Khi có nhiều môi trường, proxy prefix hoặc server URL tĩnh |
| securitySchemes | Có thể đọc annotation hoặc OpenAPI bean | Khi cơ chế bảo mật đặc thù không được suy ra từ Spring Security |
| callbacks | Có thể cần khai báo metadata tường minh | Khi operation kích hoạt callback tới endpoint bên ngoài |
| webhooks | Cần mô tả rõ các webhook do service phát ra | Khi API có sự kiện gửi chủ động tới consumer |
| links | Cần metadata thể hiện quan hệ giữa response và operation tiếp theo | Khi muốn mô tả workflow giữa các operation |
| oneOf, anyOf, allOf | Có thể sinh từ schema/annotation và model converter được hỗ trợ | Khi polymorphism hoặc union type không được suy ra đúng |
| Vendor extensions x-* | Có thể thêm bằng annotation hoặc customizer | Khi gateway hoặc tooling cần metadata riêng |

Không nên hiểu bảng này là mọi phiên bản springdoc đều hỗ trợ tất cả tính năng theo cùng cách. Đây là các object/khái niệm ở lớp đặc tả; cách tạo, serialize và render phụ thuộc phiên bản từng công cụ.

## 10. Phân biệt tính năng của OAS với khả năng hiển thị của Swagger UI

Swagger UI là một renderer và công cụ thử request. Nó không phải tiêu chuẩn quy định cách mọi tài liệu phải được trình bày.

| Nội dung OpenAPI | Điều Swagger UI có thể làm | Giới hạn cần nhớ |
|---|---|---|
| Tags và operations | Hiển thị danh sách và nhóm operation | Sorter chỉ đổi thứ tự giao diện |
| Schema và examples | Hiển thị model, example và field | Cách trình bày phụ thuộc phiên bản UI |
| Security schemes | Hiển thị Authorize và hỗ trợ gắn credential vào request | Không xác thực token thay server |
| Servers | Chọn hoặc dùng server URL để gửi request | URL phải truy cập được và phù hợp môi trường |
| Request/response | Hiển thị cấu trúc và response | Không bảo đảm server thực hiện đúng schema |
| Try it out | Gửi HTTP request tới server thật | Phụ thuộc CORS, auth, network và cấu hình UI |
| Vendor extensions | Có thể hiển thị nếu bật cấu hình tương ứng | Không phải extension nào cũng có cách hiển thị riêng |

Một operation vẫn có thể hợp lệ trong OpenAPI dù Swagger UI không cung cấp nút tương tác phù hợp. Một document cũng có thể được tiêu thụ tốt bởi code generator dù giao diện không trình bày đẹp.

Ngược lại, UI hiển thị một schema không chứng minh schema hợp lệ theo chuẩn. Hãy dùng validator/linter phù hợp để kiểm tra tài liệu.

## 11. Ví dụ một tính năng tồn tại trong chuẩn nhưng UI không thực thi thay server

Giả sử document có operation:

~~~yaml
paths:
  /orders:
    post:
      operationId: createOrder
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - productId
              properties:
                productId:
                  type: string
      responses:
        "201":
          description: Order created
~~~

Swagger UI có thể hiển thị form hoặc vùng nhập request body. Khi người dùng bấm Execute, UI gửi request tới server URL. Nếu server không có route POST /orders, request sẽ trả 404 dù tài liệu vẫn hiển thị operation.

Nếu UI tắt Try it out, document vẫn chứa POST /orders; client generator vẫn có thể tạo method cho operation đó. Việc tắt nút chỉ ảnh hưởng khả năng gửi request từ giao diện.

## 12. Cách xác minh phiên bản của từng lớp

Không suy luận toàn bộ chuỗi từ một con số trong pom.xml. Kiểm tra riêng từng nơi.

### Kiểm tra OpenAPI document

~~~bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '{openapi, infoVersion: .info.version}'
~~~

Kết quả ví dụ:

~~~json
{
  "openapi": "3.1.0",
  "infoVersion": "2.4.0"
}
~~~

Kiểm tra YAML nếu ứng dụng expose:

~~~bash
curl -s http://localhost:8080/v3/api-docs.yaml
~~~

### Kiểm tra springdoc và dependency bắc cầu

Với Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3,org.webjars
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Tìm các dependency:

- springdoc-openapi-starter: phiên bản springdoc.
- swagger-core hoặc swagger model: thư viện mô hình/serializer OpenAPI.
- swagger-ui hoặc WebJar chứa assets: phiên bản giao diện thực tế.
- Spring Boot và Spring Framework: nền tảng tương thích.

Dependency tree giúp biết phiên bản được resolve cuối cùng, không chỉ phiên bản được khai báo trực tiếp. BOM hoặc dependency management có thể thay đổi phiên bản transitive.

### Kiểm tra Swagger UI đang tải

Mở Developer Tools, tab Network, lọc swagger-ui hoặc xem tài nguyên JavaScript/CSS được tải. Đối chiếu asset với dependency tree hoặc metadata của WebJar. Không đoán phiên bản UI chỉ từ phiên bản springdoc.

## 13. Kiểm tra tài liệu bằng validator và consumer thực tế

Một quy trình kiểm tra tốt có nhiều lớp:

1. **Kiểm tra field phiên bản:** đọc openapi trong JSON đầu ra.
2. **Validate document:** dùng validator tương ứng với OAS version và schema dialect.
3. **Kiểm tra rendering:** mở document bằng đúng Swagger UI đang được đóng gói.
4. **Kiểm tra code generation:** chạy generator mà consumer thật sẽ sử dụng.
5. **Kiểm tra contract:** so sánh request/response runtime với tài liệu.
6. **Kiểm tra tương tác:** thử Authorize và Try it out trong môi trường có CORS và quyền phù hợp.

Không dùng kết quả của một bước thay cho các bước khác:

- Document validate thành công không chứng minh server đúng hợp đồng.
- Swagger UI render được không chứng minh mọi tool khác hiểu document.
- Client generator chạy được không chứng minh request runtime thành công.
- Request runtime thành công không chứng minh OpenAPI document đầy đủ hoặc chính xác.

### Ví dụ kiểm tra một schema có khác biệt phiên bản

Nếu dự án chuyển từ OAS 3.0 sang 3.1:

- Tìm các schema có nullable.
- Kiểm tra union type, $ref và composition.
- Xác minh JSON Schema dialect được công cụ tiêu thụ hỗ trợ.
- Chạy validator cho OAS 3.1.
- Sinh client bằng đúng generator dự kiến dùng ở downstream.
- So sánh request/response trước và sau thay đổi.

Không đổi openapi thành 3.1.0 rồi kết thúc migration. Phải chuyển cách biểu diễn schema và xác minh các công cụ liên quan.

## 14. Lỗi thường gặp khi nhầm ba lớp

| Hiện tượng | Ngộ nhận | Cách điều tra |
|---|---|---|
| OAS có field nhưng springdoc không sinh ra | Nghĩ rằng chuẩn tự làm ứng dụng phát sinh metadata | Bổ sung annotation, bean hoặc customizer; kiểm tra phiên bản springdoc |
| Swagger UI không hiển thị một feature | Kết luận OAS không hỗ trợ feature | Kiểm tra phiên bản UI và khả năng renderer |
| UI không có Try it out | Nghĩ operation không tồn tại | Kiểm tra supportedSubmitMethods, tryItOutEnabled và document |
| UI hiển thị operation nhưng server trả 404 | Nghĩ UI tạo route | Kiểm tra Spring mapping và server URL |
| info.version thay đổi nhưng OAS vẫn 3.0 | Nghĩ đã nâng phiên bản đặc tả | Kiểm tra field openapi và springdoc.api-docs.version |
| Nâng springdoc nhưng UI vẫn cũ | Nghĩ starter luôn dùng UI mới nhất | Kiểm tra dependency transitive và dependency management |
| Swagger UI parse được nhưng codegen lỗi | Nghĩ UI render thành công là đủ | Kiểm tra hỗ trợ feature của generator |
| Document validate được nhưng API trả sai payload | Nghĩ schema tự enforce runtime | Kiểm tra serializer, validation và contract tests |
| Ghi openapi: 3.2.1 thủ công | Nghĩ đổi nhãn sẽ bật hỗ trợ 3.2.1 | Kiểm tra model, serializer, validator và UI có thực sự hỗ trợ |

## 15. Quy trình chọn và nâng cấp phiên bản

Khi dự án muốn sử dụng một feature mới của OpenAPI, thực hiện theo thứ tự:

1. **Xác định feature cần dùng:** tìm field hoặc object trong OAS và phiên bản đầu tiên định nghĩa nó.
2. **Chọn OAS version:** ưu tiên phiên bản mà toàn bộ consumer quan trọng có thể hỗ trợ.
3. **Kiểm tra springdoc:** xác nhận đúng nhánh thư viện tương thích với Spring Boot và có thể sinh hoặc cho phép bổ sung feature cần thiết.
4. **Kiểm tra model/serializer:** bảo đảm swagger-core và serializer không làm mất field.
5. **Kiểm tra Swagger UI:** xác nhận parser và renderer hỗ trợ document version.
6. **Kiểm tra validator và generator:** dùng đúng phiên bản sẽ chạy trong CI và phía consumer.
7. **Tạo fixture hoặc document mẫu:** xác minh feature mới trước khi áp dụng cho toàn API.
8. **Kiểm thử runtime:** bảo đảm server vẫn thực hiện đúng hợp đồng.
9. **Công bố thay đổi:** ghi rõ OAS version, API/document version và yêu cầu toolchain nếu consumer cần nâng cấp.

Nếu một consumer quan trọng chưa hỗ trợ OAS version mới, có thể tiếp tục phát hành OAS version cũ trong thời gian chuyển đổi hoặc cung cấp tài liệu riêng cho từng nhóm consumer. Không hạ chuẩn một cách âm thầm nếu việc đó làm mất ngữ nghĩa schema hoặc security.

## 16. Checklist xác định đúng lớp chịu trách nhiệm

- [ ] Đã phân biệt field openapi với info.version.
- [ ] Đã xác định phiên bản Spring Boot và springdoc đang dùng.
- [ ] Đã kiểm tra dependency bắc cầu của swagger-core và Swagger UI.
- [ ] Đã xác định feature cần dùng thuộc phiên bản OAS nào.
- [ ] Đã xác minh springdoc có thể sinh hoặc bổ sung feature đó.
- [ ] Đã xác minh Swagger UI có thể parse và hiển thị document.
- [ ] Đã xác minh validator/linter hỗ trợ cùng OAS version.
- [ ] Đã chạy client generator nếu dự án phát hành SDK.
- [ ] Đã kiểm tra runtime contract riêng với document validation.
- [ ] Không dùng tùy chọn giao diện để kết luận về nội dung đặc tả.
- [ ] Không sửa field openapi bằng tay để giả lập nâng cấp hỗ trợ.
- [ ] Đã ghi rõ yêu cầu tương thích cho các consumer.

## 17. Tài liệu tham khảo chính thức

- [OpenAPI Specification – phiên bản hiện hành](https://spec.openapis.org/oas/latest.html): định nghĩa object, field và ngữ nghĩa của OpenAPI Description.
- [OpenAPI Specification 3.0](https://spec.openapis.org/oas/v3.0.4.html): tài liệu đặc tả nhánh 3.0.
- [OpenAPI Specification 3.1](https://spec.openapis.org/oas/v3.1.2.html): tài liệu đặc tả nhánh 3.1 và Schema Object dựa trên JSON Schema.
- [springdoc-openapi – Configuration Properties](https://springdoc.org/properties.html): property hiện hành cho sinh tài liệu và Swagger UI.
- [springdoc-openapi v2 – Core Properties](https://springdoc.org/v2/core-properties.html): cấu hình nhánh springdoc dành cho Spring Boot 3.x.
- [springdoc-openapi – Compatibility](https://github.com/springdoc/springdoc-openapi#compatibility): quan hệ giữa nhánh springdoc và Spring Boot.
- [Swagger UI – Compatibility](https://github.com/swagger-api/swagger-ui#compatibility): ma trận hỗ trợ giữa phiên bản Swagger UI và OpenAPI Specification.

## Kết luận

OpenAPI Specification định nghĩa hợp đồng và ngữ nghĩa của tài liệu; springdoc-openapi tạo tài liệu từ metadata mà ứng dụng Spring cung cấp; Swagger UI đọc tài liệu để hiển thị và gửi request thử nghiệm. Phiên bản openapi, info.version, dependency springdoc và Swagger UI là các trục riêng. Một feature có trong chuẩn chưa chắc được springdoc tự sinh hoặc UI hỗ trợ đầy đủ; một nút giao diện bị tắt cũng không làm operation biến mất khỏi hợp đồng. Hãy kiểm tra document đầu ra, dependency tree, ma trận tương thích của UI, validator, generator và hành vi runtime trước khi kết luận toàn bộ hệ thống hỗ trợ một phiên bản OpenAPI.
