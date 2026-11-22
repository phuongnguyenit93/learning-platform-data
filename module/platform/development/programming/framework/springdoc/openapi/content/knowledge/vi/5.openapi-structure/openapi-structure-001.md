# Trường openapi và phiên bản định dạng của đặc tả

Mỗi OpenAPI Description bắt đầu bằng một OpenAPI Object ở cấp gốc. Trường **openapi** trong object này cho biết document tuân theo phiên bản nào của **OpenAPI Specification (OAS)**. Công cụ đọc document dựa vào giá trị đó để hiểu cú pháp, cấu trúc object và các quy tắc schema được phép sử dụng.

Ví dụ:

~~~yaml
openapi: "3.1.0"
info:
  title: Catalog API
  version: "2026.11"
paths:
  /products:
    get:
      operationId: listProducts
      summary: Lấy danh sách sản phẩm
      responses:
        "200":
          description: Danh sách sản phẩm
~~~

Trong ví dụ, openapi là phiên bản định dạng OpenAPI; info.version là phiên bản của OpenAPI document theo metadata của Info Object. Hai giá trị này không có quan hệ bắt buộc phải giống nhau.

Đây là điểm cần phân biệt ngay từ đầu khi làm việc với springdoc: version của thư viện springdoc, version của OpenAPI Specification và version của API/document là những thông tin khác nhau.

## 1. openapi là trường gì?

openapi là trường bắt buộc trong OpenAPI Object ở cấp gốc. Kiểu dữ liệu của nó là chuỗi (string), và giá trị phải là số phiên bản OpenAPI Specification mà document sử dụng.

Ví dụ:

~~~yaml
openapi: "3.0.4"
~~~

~~~yaml
openapi: "3.1.0"
~~~

~~~yaml
openapi: "3.2.1"
~~~

Các giá trị trên biểu thị những feature set khác nhau của OAS. Khi parser đọc trường này, nó có thể chọn đúng bộ quy tắc để diễn giải paths, components, schemas, security, webhooks và các object khác.

Một số đặc điểm quan trọng:

- Trường phải nằm ở cấp gốc, ngang hàng với info, servers, paths và components.
- Tên trường phân biệt chữ hoa/chữ thường; viết OpenAPI hoặc openApi không thay thế được openapi.
- Giá trị là chuỗi version, không phải tên thư viện hay URL tài liệu.
- Giá trị phải phản ánh đúng cú pháp và tính năng mà document thực sự sử dụng.
- Không tự đặt một version tùy ý như latest, v3 hoặc 3.1.

OpenAPI Specification định nghĩa trường này là bắt buộc và khuyến nghị tooling dùng nó để diễn giải document. Nếu thiếu openapi, parser không thể xác định chắc chắn document đang khai báo theo OAS nào.

## 2. Phân biệt bốn loại phiên bản

Trong một dự án Spring Boot có thể xuất hiện nhiều chuỗi version gần giống nhau. Chúng có ý nghĩa khác nhau:

| Thông tin | Ví dụ | Ý nghĩa |
|---|---|---|
| Phiên bản thư viện springdoc | 2.10.0 | Version dependency Java dùng để sinh OpenAPI |
| Phiên bản OpenAPI Specification | 3.1.0 | Feature set và quy tắc định dạng của document |
| info.version | 2026.11 | Version của OpenAPI document được mô tả trong Info Object |
| Phiên bản release của API | v1, v2 hoặc 2026-11 | Quy ước versioning API mà tổ chức công bố cho consumer |

Không được suy ra rằng:

- springdoc 3.x bắt buộc sinh openapi 3.0.0 hoặc 3.2.0.
- API /v2/products bắt buộc có openapi 2.0.
- info.version 3.1.0 có nghĩa document dùng OAS 3.1.0.
- Nâng version springdoc đồng nghĩa nâng version OpenAPI Specification.

Ví dụ, ứng dụng có thể dùng springdoc 2.10.0, sinh document theo OAS 3.1.0, mô tả OpenAPI document version 2026.11, trong khi API public vẫn được quản lý theo release v1.

### Vai trò của info.version

info.version là một chuỗi metadata trong Info Object. Theo OAS 3.2.1, nó mô tả phiên bản của OpenAPI document và khác với:

- Phiên bản OpenAPI Specification ghi ở openapi.
- Phiên bản API được mô tả.
- Phiên bản của toàn bộ OpenAPI Description nếu description được chia thành nhiều document.

Trong nhiều dự án, info.version được dùng theo quy ước nội bộ như version của API hoặc release tài liệu. Điều đó cần được thống nhất với consumer và pipeline. Nếu dự án cần biểu diễn API release riêng, hãy dùng metadata hoặc extension có quy ước rõ ràng, thay vì ghi nhầm vào trường openapi.

Ví dụ:

~~~yaml
openapi: "3.1.0"
info:
  title: Catalog API
  version: "2026.11.20"
x-api-release: "v1"
~~~

Ở đây, x-api-release là specification extension do tổ chức tự quy ước; tooling không được giả định extension này có semantics chuẩn nếu chưa được cấu hình.

## 3. Version của OpenAPI Specification theo major, minor và patch

OAS sử dụng cách đánh version theo dạng:

~~~text
major.minor.patch
~~~

Ví dụ 3.2.1 có:

- Major: 3.
- Minor: 2.
- Patch: 1.

Theo quy tắc versioning của OAS:

- Phần major.minor xác định feature set.
- Patch release sửa lỗi, làm rõ nội dung hoặc cập nhật diễn giải; không chủ đích thêm feature set mới.
- Tooling hỗ trợ OAS 3.2 nên tương thích với các patch release thuộc 3.2.x.
- Tooling không nên xem 3.2.0 và 3.2.1 là hai feature set khác nhau chỉ vì patch number thay đổi.

Điều này không có nghĩa mọi parser cũ đều tự hiểu version mới. Một tool tuyên bố hỗ trợ 3.1 có thể từ chối hoặc xử lý không đầy đủ document 3.2, dù khác biệt patch trong cùng minor thường không làm thay đổi feature set.

### Các phiên bản đã phát hành

Tại ngày 20-11-2026, trang đặc tả chính thức liệt kê:

| Nhánh | Một số phiên bản |
|---|---|
| OpenAPI 3.2 | 3.2.1, 3.2.0 |
| OpenAPI 3.1 | 3.1.2, 3.1.1, 3.1.0 |
| OpenAPI 3.0 | 3.0.4, 3.0.3, 3.0.2, 3.0.1, 3.0.0 |
| Swagger/OpenAPI 2.0 | 2.0 |

OAS 3.2.1 được phát hành ngày 10-09-2026. Đây là patch release của nhánh 3.2, trong khi 3.2.0 là minor feature release trước đó.

## 4. Phân biệt Swagger 2.0 với OpenAPI 3.x

Trước OpenAPI 3.0, định dạng thường được gọi là Swagger Specification 2.0. Document Swagger 2.0 sử dụng trường gốc:

~~~yaml
swagger: "2.0"
info:
  title: Catalog API
  version: "v1"
paths: {}
~~~

OpenAPI 3.x dùng trường openapi:

~~~yaml
openapi: "3.0.4"
info:
  title: Catalog API
  version: "v1"
paths: {}
~~~

Không đưa cả hai trường vào cùng một document để hỗ trợ cả hai. Chúng thuộc hai phiên bản định dạng khác nhau. Khi chuyển từ Swagger 2.0 sang OpenAPI 3.x, cần chuyển cấu trúc tương ứng như:

- definitions sang components.schemas.
- securityDefinitions sang components.securitySchemes.
- host, basePath, schemes sang servers.
- Cấu trúc body parameter sang requestBody.
- Các cấu trúc response và media type sang cách biểu diễn mới.

Chỉ đổi swagger: "2.0" thành openapi: "3.0.0" không phải migration hợp lệ vì các object còn lại có thể vẫn theo cấu trúc Swagger 2.0.

## 5. Khác biệt định dạng quan trọng giữa OAS 3.0, 3.1 và 3.2

Trường openapi không chỉ là nhãn hiển thị. Nó tuyên bố document dùng bộ quy tắc tương ứng. Khi đổi version, phải xem các schema, field và cấu trúc đang dùng có phù hợp hay không.

### OAS 3.0

OAS 3.0 có Schema Object dựa trên một subset riêng của JSON Schema. Một số keyword và cách biểu diễn khác với JSON Schema hiện đại.

Ví dụ nullable:

~~~yaml
type: string
nullable: true
~~~

### OAS 3.1

OAS 3.1 căn chỉnh Schema Object với JSON Schema Draft 2020-12 và hỗ trợ JSON Schema vocabulary. Cách biểu diễn nullability chuyển sang semantics của JSON Schema:

~~~yaml
type:
  - string
  - "null"
~~~

Trong OAS 3.1, nullable không còn là cách chuẩn của OAS 3.0. Nếu chỉ đổi trường openapi từ 3.0 sang 3.1 mà giữ các schema cũ, cần kiểm tra cách tooling diễn giải chúng.

### OAS 3.2

OAS 3.2 tiếp tục mở rộng và làm rõ đặc tả. Tooling cần hỗ trợ đúng nhánh 3.2 để hiểu các trường và semantics mới. Không nên dùng version 3.2 chỉ vì đó là bản mới nhất nếu validator, gateway, SDK generator hoặc API portal của hệ thống chưa hỗ trợ.

Nguyên tắc: version ghi ở openapi phải khớp feature set thực tế. Không chọn version cao hơn chỉ để có số mới, và không chọn version thấp hơn nếu document sử dụng feature chỉ có ở nhánh mới.

## 6. File JSON/YAML không quyết định phiên bản OpenAPI

OpenAPI document là một JSON object; nó có thể được biểu diễn dưới dạng JSON hoặc YAML. Định dạng file và phiên bản đặc tả là hai trục độc lập.

Hai file sau có thể mô tả cùng một document:

~~~yaml
openapi: "3.1.0"
info:
  title: Catalog API
  version: "v1"
paths: {}
~~~

~~~json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Catalog API",
    "version": "v1"
  },
  "paths": {}
}
~~~

Đổi đuôi .yaml thành .json không chuyển phiên bản OpenAPI. Ngược lại, chuyển từ YAML sang JSON cũng không làm thay đổi semantics nếu quá trình serialize giữ nguyên dữ liệu.

Tên field trong OpenAPI phân biệt chữ hoa/chữ thường. YAML 1.2 được khuyến nghị để giữ khả năng chuyển đổi qua lại JSON/YAML; không nên dựa vào các giá trị YAML không thể biểu diễn tương đương trong JSON.

## 7. Cấu trúc tối thiểu của một document

Một document API thông thường có các thành phần:

~~~yaml
openapi: "3.1.0"
info:
  title: Catalog API
  summary: API quản lý danh mục sản phẩm
  description: Cung cấp thao tác tra cứu và quản lý sản phẩm.
  version: "2026.11"
servers:
  - url: https://api.example.com
paths:
  /products:
    get:
      operationId: listProducts
      summary: Lấy danh sách sản phẩm
      responses:
        "200":
          description: Trả về danh sách sản phẩm
components:
  schemas: {}
~~~

Vai trò:

| Field | Vai trò |
|---|---|
| openapi | Phiên bản OpenAPI Specification |
| info | Metadata của document/API |
| servers | Base URL mà consumer có thể gọi |
| paths | Các HTTP path và operation |
| components | Schema, response, parameter, security scheme và object tái sử dụng |

Ở các OAS mới, OpenAPI Object có thể có cấu trúc bổ sung như webhooks và các field khác. Ví dụ trên chỉ là document nhỏ để minh họa vị trí của openapi, không phải danh sách đầy đủ mọi field của OAS 3.2.1.

## 8. springdoc chọn phiên bản OpenAPI được sinh như thế nào?

springdoc là thư viện tích hợp Spring Boot để sinh OpenAPI document. Phiên bản springdoc dependency không tự động trở thành giá trị của trường openapi.

Theo tài liệu cấu hình hiện hành, property:

~~~yaml
springdoc:
  api-docs:
    version: openapi_3_1
~~~

springdoc.api-docs.version cho phép chọn giữa OpenAPI 3.0 và OpenAPI 3.1. Giá trị mặc định hiện được tài liệu công bố là openapi_3_1.

Nếu cần dùng OAS 3.0:

~~~yaml
springdoc:
  api-docs:
    version: openapi_3_0
~~~

Trong application.properties:

~~~properties
springdoc.api-docs.version=OPENAPI_3_1
~~~

Hoặc:

~~~properties
springdoc.api-docs.version=OPENAPI_3_0
~~~

Hãy xác minh property và giá trị được hỗ trợ trong đúng nhánh springdoc đang sử dụng. Tài liệu hiện hành liệt kê lựa chọn 3.0 và 3.1; chưa công bố lựa chọn OPENAPI_3_2. Vì vậy, không thể giả định thêm springdoc.api-docs.version=openapi_3_2 sẽ khiến springdoc sinh OAS 3.2.1.

Nếu dự án bắt buộc phát hành OAS 3.2, cần kiểm tra release springdoc mới hơn có hỗ trợ hay không. Nếu chưa có, có thể cần một bước chuyển đổi document có kiểm soát hoặc một công cụ sinh đặc tả khác; không sửa riêng trường openapi của document 3.1 thành 3.2.1 khi nội dung chưa tuân thủ OAS 3.2.

## 9. Kiểm tra giá trị openapi từ endpoint springdoc

Sau khi ứng dụng khởi động, endpoint mặc định thường là:

~~~text
GET /v3/api-docs
GET /v3/api-docs.yaml
~~~

Tải JSON và đọc trường:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs \
  -o build/openapi.json

jq -r '.openapi, .info.version, .info.title' build/openapi.json
~~~

Ví dụ kết quả:

~~~text
3.1.0
2026.11
Catalog API
~~~

Ba dòng là ba metadata khác nhau. Dòng đầu là version OAS; dòng thứ hai là version của document theo Info Object; dòng thứ ba là tên API.

Kiểm tra bằng PowerShell:

~~~powershell
$document = Get-Content -Raw -Encoding UTF8 "build/openapi.json" |
    ConvertFrom-Json

$document.openapi
$document.info.version
$document.info.title
~~~

Nếu endpoint trả YAML, dùng YAML parser phù hợp để đọc field; không dùng regex đơn giản nếu document có comment, anchor hoặc cấu trúc phức tạp.

## 10. Kiểm tra format version và cấu trúc bằng validator

Validator phải hỗ trợ phiên bản OAS mà document khai báo. Ví dụ, không dùng một validator chỉ hỗ trợ OpenAPI 3.0 để kết luận document 3.2.1 không hợp lệ.

Một quy trình kiểm tra:

1. Parse JSON/YAML để xác nhận cú pháp.
2. Đọc openapi và xác định OAS version.
3. Chọn validator hỗ trợ đúng major/minor.
4. Validate cấu trúc và object theo đặc tả.
5. Chạy linter theo quy ước nội bộ.
6. Kiểm tra lại bằng Swagger UI, gateway hoặc code generator thực sự được consumer sử dụng.

Ví dụ dùng Redocly CLI với một phiên bản công cụ đã được pin trong dự án:

~~~bash
redocly lint build/openapi.json
~~~

Ví dụ dùng Swagger CLI:

~~~bash
swagger-cli validate build/openapi.json
~~~

Hãy kiểm tra tài liệu của phiên bản CLI đang cài về mức hỗ trợ OAS 3.1/3.2. Không phải công cụ nào cũng theo kịp bản OAS mới ngay khi specification phát hành.

Schema JSON trên spec.openapis.org là hỗ trợ validation hữu ích, nhưng chính nội dung normative của specification mới là nguồn có thẩm quyền nếu schema và văn bản đặc tả có điểm không khớp.

## 11. Tác động tới Swagger UI và code generator

Giá trị openapi giúp Swagger UI, API portal, gateway và code generator chọn parser tương ứng. Nếu document khai báo version mới hơn khả năng hỗ trợ của consumer, có thể xảy ra:

- Swagger UI báo không thể render definition.
- Một số schema hoặc keyword bị bỏ qua.
- Validator từ chối document dù YAML/JSON parse được.
- Code generator sinh model thiếu hoặc sai kiểu.
- Gateway import được file nhưng bỏ qua một phần policy.
- Contract test diễn giải request/response khác với server.

Ngược lại, nếu document dùng feature mới nhưng khai báo OAS cũ, consumer có thể đọc sai hoặc không nhận ra feature đó.

Trước khi đổi openapi, kiểm tra toàn bộ consumer quan trọng:

| Consumer | Điều cần kiểm tra |
|---|---|
| Swagger UI | Phiên bản UI có render OAS version và Schema Object cần dùng không? |
| OpenAPI validator | Có hỗ trợ đúng major/minor không? |
| SDK generator | Có sinh đúng nullable, union, enum và reference không? |
| API gateway | Có import được security, server và operation không? |
| Contract test | Parser và matcher có hiểu schema mới không? |
| API portal | Có hiển thị đúng description, example và reference không? |

Không đổi version trong document trước khi đã thử trên bộ consumer mà tổ chức hỗ trợ.

## 12. Chọn OAS 3.0 hay 3.1 trong springdoc

Nếu springdoc hiện tại chỉ cung cấp hai lựa chọn 3.0 và 3.1, việc chọn cần dựa trên nhu cầu schema và khả năng tương thích consumer.

| Tiêu chí | OAS 3.0 | OAS 3.1 |
|---|---|---|
| JSON Schema | Subset riêng của OAS 3.0 | Căn chỉnh JSON Schema Draft 2020-12 |
| Nullability | Có nullable: true | Dùng JSON Schema type/union với null |
| Tooling cũ | Thường có độ phủ lâu đời | Cần xác minh parser/generator |
| Biểu diễn schema phức tạp | Một số trường hợp bị giới hạn | Linh hoạt hơn nhờ JSON Schema |
| springdoc property | openapi_3_0 | openapi_3_1 |

Chọn 3.1 khi cần JSON Schema semantics và consumer đã hỗ trợ. Chọn 3.0 khi hệ sinh thái gateway, generator hoặc portal của tổ chức còn yêu cầu 3.0. Không dùng 3.0 chỉ vì một tool cũ chưa được cập nhật mà không ghi nhận giới hạn đó.

## 13. Quy trình nâng phiên bản OAS có kiểm soát

Khi muốn chuyển document từ 3.0 sang 3.1 hoặc sang 3.2:

1. Xác định feature mới nào cần sử dụng.
2. Kiểm tra springdoc có hỗ trợ sinh version đích hay không.
3. Kiểm tra Swagger UI, validator, gateway, SDK generator và portal.
4. Đọc migration notes giữa hai minor/major OAS.
5. Chuyển các schema và keyword cũ sang semantics mới.
6. Sinh document từ ứng dụng.
7. Kiểm tra field openapi có đúng version mong muốn.
8. Validate bằng công cụ hỗ trợ version đích.
9. So sánh semantic diff và chạy contract tests.
10. Phát hành document và thông báo consumer nếu thay đổi ảnh hưởng SDK/tooling.

Không thực hiện migration bằng cách search/replace chuỗi 3.0.0 thành 3.1.0 hoặc 3.2.1 trong file. Trường version chỉ tuyên bố semantics; nó không tự chuyển đổi schema hay object.

## 14. Những lỗi thường gặp

| Lỗi | Vì sao sai | Cách sửa |
|---|---|---|
| Dùng openapi: "2.0" | OAS 2.0 dùng field swagger: "2.0" | Chuyển cấu trúc sang OpenAPI 3.x |
| Đặt openapi: "v1" | Đây không phải OAS version hợp lệ | Dùng version OAS như 3.1.0 |
| Đặt openapi: "3.1" | Thiếu patch component của version string chuẩn | Dùng full version như 3.1.0 |
| Đặt openapi: "3.2.1" nhưng dùng cú pháp 3.0/3.1 không đúng ngữ nghĩa | Field version không tự chuyển đổi document | Validate và chuyển đổi object/schema theo OAS 3.2 |
| Dùng info.version thay openapi | Hai field có ý nghĩa khác nhau | Giữ openapi ở root và info.version trong Info Object |
| Cho rằng springdoc 3.x phải sinh OAS 3.2 | Version thư viện và OAS version độc lập | Kiểm tra springdoc.api-docs.version |
| Đổi đuôi YAML thành JSON | Không chuyển đổi cú pháp file | Serialize lại bằng JSON parser |
| Dùng validator chỉ hỗ trợ OAS 3.0 cho document 3.1/3.2 | Validator không hiểu version đích | Dùng tool version có hỗ trợ tương ứng |
| Nâng OAS mà không kiểm tra Swagger UI | UI có thể chưa hỗ trợ schema/keyword mới | Test trên đúng phiên bản UI consumer |
| Thay version field để làm hết cảnh báo | Có thể che giấu lỗi thực tế hoặc khai báo sai semantics | Sửa document theo đúng specification |

## 15. Checklist review trường openapi

- [ ] Có trường openapi ở root object.
- [ ] Tên field viết đúng chữ thường openapi.
- [ ] Giá trị là chuỗi version đầy đủ.
- [ ] Version phản ánh đúng feature set mà document sử dụng.
- [ ] Không trộn swagger: "2.0" với OpenAPI 3.x.
- [ ] Không nhầm version springdoc với OAS version.
- [ ] Không nhầm info.version với OAS version.
- [ ] Đã kiểm tra các consumer có hỗ trợ OAS version khai báo.
- [ ] Validator được pin và hỗ trợ đúng version.
- [ ] Schema dùng đúng semantics của OAS 3.0/3.1/3.2.
- [ ] Đã chạy semantic diff và contract tests khi nâng version.
- [ ] springdoc property được xác minh trong đúng release đang dùng.

## 16. Tài liệu tham khảo chính thức

- [OpenAPI Specification – Version Index](https://spec.openapis.org/oas/): danh sách phiên bản 3.0, 3.1, 3.2 và schema iteration.
- [OpenAPI Specification 3.2.1](https://spec.openapis.org/oas/v3.2.1.html): ý nghĩa trường openapi, info.version, quy tắc major/minor/patch và cấu trúc OpenAPI Object.
- [OpenAPI Specification 3.1.0](https://spec.openapis.org/oas/v3.1.0.html): Schema Object và JSON Schema alignment trong OAS 3.1.
- [OpenAPI Specification 3.0.4](https://spec.openapis.org/oas/v3.0.4.html): cấu trúc và semantics của OAS 3.0.
- [springdoc-openapi Core Properties](https://springdoc.org/core-properties.html): springdoc.api-docs.version, giá trị mặc định và lựa chọn OAS 3.0/3.1.
- [springdoc-openapi v2 Properties](https://springdoc.org/v2/core-properties.html): cấu hình version cho nhánh Boot 3.

## Kết luận

Trường openapi khai báo phiên bản OpenAPI Specification mà document tuân theo. Nó khác với version của thư viện springdoc và khác với info.version. OAS dùng major/minor để xác định feature set, còn patch chủ yếu sửa lỗi và làm rõ đặc tả. Tại ngày 20-11-2026, OAS 3.2.1 là bản mới nhất, nhưng springdoc hiện tài liệu hóa lựa chọn sinh OAS 3.0 hoặc 3.1. Khi chọn hoặc nâng version, hãy kiểm tra khả năng hỗ trợ của springdoc và toàn bộ consumer, chuyển đổi schema theo đúng semantics, validate document và chạy contract tests; không chỉ thay chuỗi version ở root.
