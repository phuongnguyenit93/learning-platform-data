# Khác biệt giữa ALPS, JSON Schema và tài liệu hợp đồng OpenAPI trong Spring Data REST

## Mục tiêu

Sau bài này, bạn có thể phân biệt ba loại metadata thường gặp khi mô tả một REST API: ALPS, JSON Schema và OpenAPI. Bạn sẽ biết mỗi loại trả lời câu hỏi gì, Spring Data REST cung cấp ALPS và JSON Schema ở đâu, OpenAPI được bổ sung bằng công cụ nào, và cách kết hợp chúng để hỗ trợ client khám phá API, kiểm tra dữ liệu và tích hợp endpoint.

## 1. Vì sao cần nhiều loại metadata?

Một API không chỉ gồm URL và JSON response. Client còn cần biết:

- Resource có những thuộc tính nào và mỗi thuộc tính mang ý nghĩa gì?
- API hỗ trợ những thao tác nào trên resource?
- Body request và response có cấu trúc, kiểu dữ liệu và ràng buộc gì?
- Tham số nằm ở path, query hay header?
- Endpoint có thể trả những status code và media type nào?
- Cần xác thực bằng cơ chế nào và có những link hypermedia nào để tiếp tục điều hướng?

Không một định dạng metadata nào giải quyết tốt mọi câu hỏi trên. ALPS, JSON Schema và OpenAPI có phạm vi khác nhau:

- **ALPS** mô tả ngữ nghĩa ở cấp ứng dụng và các affordance/chuyển tiếp hypermedia.
- **JSON Schema** mô tả cấu trúc dữ liệu JSON và các ràng buộc có thể kiểm tra trên instance JSON.
- **OpenAPI** mô tả hợp đồng HTTP API: đường dẫn, method, tham số, request body, response, media type và bảo mật.

Trong Spring Data REST, ALPS và JSON Schema là metadata được hỗ trợ sẵn. OpenAPI thường được bổ sung bằng thư viện tích hợp như `springdoc-openapi`. Vì vậy, ba định dạng có thể cùng tồn tại và phục vụ các nhóm client khác nhau.

## 2. ALPS: mô tả ngữ nghĩa và thao tác hypermedia

ALPS là viết tắt của Application-Level Profile Semantics. Đây là định dạng mô tả các khái niệm và ngữ nghĩa của một ứng dụng theo cách không phụ thuộc chặt vào một media type cụ thể. Một ALPS profile có thể giúp client hiểu ý nghĩa các thuộc tính và các chuyển tiếp mà resource hỗ trợ.

Spring Data REST tạo một ALPS document cho mỗi repository được export. Metadata thường bao gồm:

- Các thuộc tính của representation, chẳng hạn `firstName`, `lastName`, `email`.
- Các thao tác REST được hỗ trợ, chẳng hạn đọc collection, đọc item, tạo, cập nhật hoặc xóa.
- Kiểu hypermedia control và resource type liên quan.
- Các projection được công bố, nếu repository có projection.
- Mô tả bổ sung cho resource hoặc thuộc tính khi ứng dụng cung cấp metadata tương ứng.

### Khám phá ALPS trong Spring Data REST

API root có link `profile`. Theo link đó, client đến `/profile` để xem danh sách profile của các repository. Ví dụ rút gọn:

```json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/profile"
    },
    "people": {
      "href": "http://localhost:8080/profile/people"
    },
    "addresses": {
      "href": "http://localhost:8080/profile/addresses"
    }
  }
}
```

Để lấy ALPS của repository `people`, client theo link `/profile/people`:

```http
GET /profile/people
Accept: application/alps+json
```

Spring Data REST cũng có thể phục vụ ALPS theo mặc định khi client theo profile link mà không chỉ rõ media type. Nên dùng đúng link do API trả về thay vì tự ghép path, đặc biệt khi ứng dụng có base path hoặc cấu hình resource path tùy chỉnh.

Một ALPS document có thể chứa các descriptor như:

```json
{
  "version": "1.0",
  "descriptors": [
    {
      "id": "person-representation",
      "descriptors": [
        { "name": "firstName", "type": "SEMANTIC" },
        { "name": "lastName", "type": "SEMANTIC" },
        { "name": "address", "type": "SAFE" }
      ]
    },
    {
      "id": "create-people",
      "name": "people",
      "type": "UNSAFE",
      "rt": "#person-representation"
    },
    {
      "id": "get-people",
      "name": "people",
      "type": "SAFE",
      "rt": "#person-representation"
    }
  ]
}
```

Đây là ví dụ rút gọn để minh họa cấu trúc descriptor. Metadata thực tế phụ thuộc domain model, repository methods và phiên bản Spring Data REST.

### Các loại descriptor trong ALPS

| Type | Ý nghĩa | Ví dụ điển hình |
| --- | --- | --- |
| `SEMANTIC` | Thuộc tính mang ý nghĩa dữ liệu | `firstName`, `email` |
| `SAFE` | Chuyển tiếp không thay đổi trạng thái hệ thống | GET hoặc HEAD |
| `IDEMPOTENT` | Chuyển tiếp có thể thay đổi trạng thái nhưng lặp lại cùng request có cùng hiệu ứng cuối | PUT hoặc DELETE |
| `UNSAFE` | Chuyển tiếp có thể thay đổi trạng thái và không bảo đảm idempotent | POST |

ALPS giúp client hiểu các thao tác và ý nghĩa dữ liệu ở mức ngữ nghĩa. Ví dụ, một descriptor `UNSAFE` có thể cho biết thao tác tạo resource trên collection; `rt` liên kết thao tác với representation type tương ứng.

### ALPS và projection

Nếu repository có projection được đăng ký, ALPS có thể mô tả tham số `projection` và các tên projection được hỗ trợ. Client có thể khám phá những góc nhìn representation thay thế mà không cần hard-code danh sách projection từ tài liệu ngoài.

### Bổ sung mô tả cho ALPS

Có thể thêm mô tả cho resource và property bằng các message key theo quy ước `rest.description.*` trong `rest-messages.properties`. Ví dụ:

```properties
rest.description.person=A collection of people
rest.description.person.firstName=Person's first name
rest.description.person.lastName=Person's last name
rest.description.person.address=Person's address
```

Các giá trị này được đưa vào phần `doc` của descriptor. Spring MVC hỗ trợ locale, nên có thể cung cấp các resource bundle theo ngôn ngữ để mô tả profile phù hợp với người dùng.

ALPS không phải tài liệu mô tả đầy đủ từng byte của HTTP request/response. Nó tập trung vào semantics và hypermedia controls; các kiểu dữ liệu chi tiết, constraint cấu trúc, response code và security scheme cần được mô tả bằng định dạng khác khi cần.

## 3. JSON Schema: mô tả cấu trúc và ràng buộc JSON

JSON Schema là một vocabulary để mô tả hình dạng của JSON document. Nó có thể định nghĩa:

- Kiểu dữ liệu: object, array, string, number, integer, boolean, null.
- Các property và kiểu dữ liệu tương ứng.
- Property bắt buộc qua `required`.
- Giới hạn như `minLength`, `maxLength`, `minimum`, `maximum`, `pattern`.
- Cấu trúc lồng nhau, phần tử của array và các lựa chọn schema.
- Một số annotation như title, description, format và readOnly.

JSON Schema hữu ích cho client generator, form generator, validator và test tự động vì client có thể kiểm tra JSON instance có phù hợp với schema hay không.

### Lấy JSON Schema từ Spring Data REST

Spring Data REST dùng cùng profile URI nhưng chọn representation bằng content negotiation. Ví dụ:

```http
GET /profile/people
Accept: application/schema+json
```

Hoặc dùng curl:

```bash
curl -i http://localhost:8080/profile/people \
  -H "Accept: application/schema+json"
```

Profile link của repository vẫn có thể trả ALPS theo mặc định; header `Accept: application/schema+json` yêu cầu JSON Schema. Hãy theo link `profile` do API root hoặc collection resource cung cấp.

Ví dụ JSON Schema rút gọn:

```json
{
  "$schema": "https://json-schema.org/draft-04/schema#",
  "title": "Person",
  "type": "object",
  "properties": {
    "firstName": {
      "type": "string",
      "readOnly": false
    },
    "lastName": {
      "type": "string",
      "readOnly": false
    },
    "address": {
      "type": "string",
      "format": "uri"
    },
    "created": {
      "type": "string",
      "format": "date-time"
    }
  }
}
```

Schema thực tế Spring Data REST phát ra được xác định bởi phiên bản và mapping của ứng dụng. Tài liệu hiện hành có thể hiển thị draft version cụ thể; client nên đọc trường `$schema` thay vì giả định mọi server dùng cùng một draft.

### JSON Schema giúp gì cho client?

Giả sử client cần gửi một object Person. Schema có thể cho biết `firstName` là string, `created` là date-time, và `address` là URI. Client có thể dùng các thông tin đó để:

- Tạo form với control phù hợp.
- Kiểm tra dữ liệu trước khi gửi.
- Sinh type hoặc model cho ngôn ngữ lập trình.
- Tạo test xác nhận JSON request/response có đúng shape.
- Hiển thị metadata cơ bản về property.

### Giới hạn của JSON Schema trong Spring Data REST

JSON Schema mô tả cấu trúc dữ liệu; nó không thay thế toàn bộ hợp đồng HTTP:

- Không mô tả đầy đủ danh sách path và HTTP method như OpenAPI.
- Không tự mô tả mọi status code, response header, security scheme hoặc luồng OAuth.
- Một schema domain không nhất thiết là schema riêng cho từng thao tác POST, PUT, PATCH và GET.
- Các quy tắc nghiệp vụ phụ thuộc nhiều field, database hoặc người dùng không thể được suy ra đầy đủ chỉ từ kiểu property.
- Có schema không đồng nghĩa server tự động validate request theo mọi constraint trong schema.

Hãy phân biệt schema metadata với validation thực thi. Server vẫn cần Bean Validation, domain rules, authorization và database constraints. Client validation chỉ cải thiện trải nghiệm; server phải tự xác minh dữ liệu đầu vào.

## 4. OpenAPI: tài liệu hợp đồng HTTP API

OpenAPI Specification (OAS) mô tả một HTTP API theo cấu trúc máy có thể đọc. Một OpenAPI document thường bao gồm:

- `openapi`: phiên bản đặc tả.
- `info`: tên, mô tả, phiên bản API và thông tin liên hệ/license.
- `servers`: base URL của các môi trường.
- `paths`: endpoint và các HTTP operations.
- `parameters`: path, query, header hoặc cookie parameters.
- `requestBody`: media type và schema của body đầu vào.
- `responses`: status code, header và response body.
- `components`: schema, response, parameter và security scheme tái sử dụng.
- `security`: yêu cầu xác thực và phân quyền ở mức API hoặc operation.

Ví dụ OpenAPI rút gọn cho collection `/people`:

```yaml
openapi: 3.1.0
info:
  title: People API
  version: 1.0.0
servers:
  - url: https://api.example.com
paths:
  /people:
    get:
      summary: List people
      responses:
        "200":
          description: People collection
          content:
            application/hal+json:
              schema:
                type: object
    post:
      summary: Create a person
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/PersonInput"
      responses:
        "201":
          description: Person created
          headers:
            Location:
              description: URI of the created resource
              schema:
                type: string
                format: uri
  /people/{id}:
    get:
      summary: Get one person
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Person resource
        "404":
          description: Person not found
components:
  schemas:
    PersonInput:
      type: object
      required:
        - firstName
      properties:
        firstName:
          type: string
        lastName:
          type: string
```

Đây là ví dụ minh họa, không phải OpenAPI document được Spring Data REST tự động phát ra nguyên dạng. Một API thực tế cần mô tả chính xác HAL representation, response codes, request media types, security và các association link được hỗ trợ.

OpenAPI đặc biệt hữu ích cho:

- Swagger UI hoặc Scalar để người phát triển thử API.
- Sinh client SDK và server stub.
- Contract testing giữa producer và consumer.
- Tạo tài liệu tích hợp có path, method, request, response và security rõ ràng.
- So sánh thay đổi contract giữa các phiên bản API.

## 5. Spring Data REST có cung cấp OpenAPI sẵn không?

Spring Data REST có metadata ALPS và JSON Schema trong lõi. OpenAPI là một đặc tả riêng và thường được tích hợp qua công cụ bên ngoài, ví dụ `springdoc-openapi`.

Với Spring Boot, springdoc có module hỗ trợ Spring Data REST, bao gồm các kiểu như `@RepositoryRestResource` và các tích hợp liên quan. Thư viện có thể phân tích ứng dụng và tạo OpenAPI JSON/YAML; nếu dùng starter có UI, có thể cung cấp Swagger UI.

Các endpoint thường gặp của springdoc:

- `/v3/api-docs`: OpenAPI document dạng JSON.
- `/v3/api-docs.yaml`: OpenAPI document dạng YAML.
- `/swagger-ui.html`: giao diện Swagger UI (đường dẫn có thể được cấu hình).

Ví dụ dependency Maven cho ứng dụng Spring Boot 3 dùng Spring MVC và muốn có Swagger UI:

```xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version><!-- Chọn phiên bản tương thích với Spring Boot --></version>
</dependency>
```

Dùng springdoc 2.x cho Spring Boot 3; nhánh springdoc 3.x dành cho Spring Boot 4. Kiểm tra bảng tương thích của đúng phiên bản dự án trước khi thêm dependency. Nếu chỉ cần OpenAPI document và không cần UI, chọn starter API tương ứng.

Sau khi chạy ứng dụng, có thể lấy document:

```bash
curl -i http://localhost:8080/v3/api-docs
```

Và mở Swagger UI tại đường dẫn được cấu hình, thường là:

```text
http://localhost:8080/swagger-ui.html
```

### Kiểm tra phần Spring Data REST được sinh tự động

Không nên mặc định rằng mọi chi tiết động của repository endpoint đã được mô tả hoàn hảo trong OpenAPI chỉ vì document được tạo thành công. Hãy kiểm tra:

- Repository collection và item path có xuất hiện không.
- Query method resources và query parameters có đúng không.
- Các operation POST/PUT/PATCH/DELETE có đúng exposure thực tế không.
- Request/response media type có bao gồm HAL hoặc media type ứng dụng đang dùng không.
- Response schema có phản ánh `_links`, `_embedded`, pagination và projection không.
- Association resource, URI-list payload và conditional headers có được mô tả không.
- Security scheme và response lỗi có đúng với Spring Security configuration không.

Với custom controller, dùng annotation OpenAPI như `@Operation`, `@ApiResponse`, `@Parameter`, `@RequestBody` và `@Schema` để bổ sung mô tả. Với các phần được sinh tự động nhưng thiếu hoặc không chính xác, bổ sung customizer hoặc cấu hình springdoc phù hợp. OpenAPI phải được kiểm tra như một artifact của API, không chỉ tin vào kết quả auto-scan.

## 6. So sánh trực tiếp ALPS, JSON Schema và OpenAPI

| Tiêu chí | ALPS | JSON Schema | OpenAPI |
| --- | --- | --- | --- |
| Câu hỏi chính | Resource có ý nghĩa gì và có thể chuyển tiếp ra sao? | JSON có cấu trúc và constraint gì? | Gọi endpoint HTTP như thế nào? |
| Trọng tâm | Semantics, descriptors, hypermedia controls | Object, property, type, required, constraints | Paths, methods, parameters, body, responses, security |
| Đơn vị mô tả | Profile, semantic descriptor, transition | JSON instance/schema | API server, path, operation, component |
| Dùng để | Khám phá ngữ nghĩa và affordance | Validate/generate model hoặc form | Tài liệu, SDK, contract test, API tooling |
| Spring Data REST core | Có | Có | Không; tích hợp bằng công cụ như springdoc |
| Content type/endpoint thường gặp | `application/alps+json`, `/profile/{repository}` | `application/schema+json`, cùng profile URI | JSON/YAML tại endpoint do công cụ OpenAPI cung cấp |
| Giới hạn chính | Không phải mô tả chi tiết mọi HTTP request/response | Không mô tả toàn bộ giao thức và operation | Không tự thay thế runtime hypermedia discovery; cần giữ document đồng bộ với API |

Có thể nhớ theo ba câu hỏi:

- ALPS trả lời: **“Các thành phần và thao tác này có ý nghĩa gì?”**
- JSON Schema trả lời: **“Dữ liệu JSON có hình dạng và ràng buộc nào?”**
- OpenAPI trả lời: **“Tôi gọi endpoint nào, bằng method và dữ liệu gì, rồi có thể nhận response nào?”**

## 7. Một ví dụ dùng cả ba loại metadata

Giả sử Spring Data REST export repository `people` với entity Person:

```java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;

    // Constructor, getters và setters
}
```

Repository:

```java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
```

Client có thể khám phá API theo trình tự:

**Bước 1 — lấy API root**

```http
GET /
Accept: application/hal+json
```

Đọc link `people` để tìm collection và link `profile` để tìm metadata.

**Bước 2 — đọc ALPS profile**

```http
GET /profile/people
Accept: application/alps+json
```

Client thấy các semantic descriptor như `firstName`, `lastName` và các transition như GET collection, POST collection, GET item.

**Bước 3 — đọc JSON Schema**

```http
GET /profile/people
Accept: application/schema+json
```

Client biết `firstName` và `lastName` là string, các property khác có kiểu tương ứng, và có thể dùng schema để hỗ trợ form hoặc kiểm tra JSON.

**Bước 4 — đọc OpenAPI**

```http
GET /v3/api-docs
Accept: application/json
```

Client hoặc công cụ phát triển đọc paths, HTTP methods, parameters, request body, responses và security schemes đã được springdoc tạo/bổ sung.

Ba document không cạnh tranh nhau. ALPS hỗ trợ hypermedia semantics; JSON Schema mô tả dữ liệu; OpenAPI là hợp đồng HTTP phục vụ tích hợp và tooling.

## 8. Kết hợp metadata mà không tạo ba nguồn chân lý mâu thuẫn

Nếu ứng dụng công bố cả ALPS, JSON Schema và OpenAPI, cần giữ chúng nhất quán với runtime API.

Một số nguyên tắc thực tế:

1. Xem domain model, repository exposure, security configuration và custom controller là nguồn thực thi.
2. Dùng ALPS để mô tả semantics và các affordance mà Spring Data REST công bố.
3. Dùng JSON Schema để mô tả cấu trúc JSON; kiểm tra draft và giới hạn schema thực tế mà server phát ra.
4. Dùng OpenAPI để mô tả giao thức HTTP đầy đủ, bao gồm media type HAL, status code, headers, auth và error response.
5. Không tự viết một schema request riêng rồi để nó khác với validation thực tế của server.
6. Nếu dùng springdoc auto-generation, kiểm tra document sau mỗi thay đổi repository path, query method, projection hoặc security.
7. Có thể dùng contract tests để so sánh OpenAPI với endpoint thực tế và kiểm tra các JSON payload quan trọng.
8. Đưa các profile link và OpenAPI URL vào tài liệu developer portal để client dễ tìm thấy.

Đặc biệt, OpenAPI có thể tham chiếu JSON Schema trong phần `components/schemas` hoặc khai báo schema inline cho request/response. Tuy nhiên, schema dùng trong OpenAPI cần tương thích với phiên bản OpenAPI đang chọn; không sao chép nguyên một JSON Schema draft cũ vào document mà không kiểm tra quy tắc dialect và hỗ trợ của tooling.

## 9. Chọn định dạng nào theo nhu cầu?

**Chọn ALPS khi:**

- API dùng hypermedia và muốn client khám phá semantics của resource.
- Cần mô tả thuộc tính, transition và projection do Spring Data REST công bố.
- Muốn client ít phụ thuộc vào URL/method được hard-code và đi theo link từ server.

**Chọn JSON Schema khi:**

- Cần mô tả cấu trúc JSON để validate hoặc sinh form/model.
- Cần ràng buộc kiểu, required fields, format, length hoặc numeric range.
- Cần test payload theo schema hoặc trao đổi schema giữa các hệ thống.

**Chọn OpenAPI khi:**

- Cần tài liệu endpoint cho đội frontend/mobile/đối tác.
- Cần mô tả HTTP method, path/query/header parameter, body, response và auth.
- Cần Swagger UI, SDK generation hoặc contract testing.
- Có custom REST controllers và muốn công bố hợp đồng tích hợp đầy đủ.

Trong một ứng dụng Spring Data REST lớn, thường có lợi khi công bố cả metadata hypermedia và OpenAPI. Client hypermedia có thể dùng ALPS/profile links; công cụ tích hợp có thể dùng OpenAPI; validator hoặc form generator có thể dùng JSON Schema.

## 10. Các lỗi thường gặp

**Không tìm thấy profile link**

Kiểm tra API root và repository có được export không. Dùng link `profile` từ root hoặc link `profile` của collection resource; không tự giả định path khi ứng dụng có base path.

**Profile trả ALPS trong khi mong đợi JSON Schema**

Gửi `Accept: application/schema+json` đến profile URI. `/profile` chỉ liệt kê các profile; URI cụ thể của repository là `/profile/{repository}`.

**JSON Schema có property nhưng không có business rule mong muốn**

Schema được sinh từ metadata domain và có giới hạn. Bổ sung validation ở server, constraint phù hợp, custom schema hoặc OpenAPI mô tả rõ request semantics. Đừng coi schema là validation engine của server.

**OpenAPI document thiếu repository endpoint**

Kiểm tra phiên bản springdoc và module hỗ trợ Spring Data REST; xác nhận repository export; xem filter/hidden configuration; và kiểm tra customizer. Có thể cần cấu hình hoặc bổ sung mô tả thủ công cho operation chưa được suy ra đầy đủ.

**Swagger UI hiển thị JSON nhưng không hiển thị HAL links đúng**

Kiểm tra response media type và schema OpenAPI. HAL representation có `_links`, `_embedded` và URI template; một schema object chung có thể không đủ để mô tả hypermedia controls chi tiết.

**Metadata cũ sau khi đổi API**

Tạo lại OpenAPI document, kiểm tra build-time generation/cache nếu có, và chạy contract tests. ALPS/JSON Schema thường được tạo từ runtime mapping nên cần kiểm tra đúng phiên bản ứng dụng đang chạy.

## Tóm tắt

- ALPS mô tả semantics, thuộc tính và các hypermedia transitions; Spring Data REST cung cấp profile cho mỗi repository được export.
- JSON Schema mô tả shape và constraint của JSON; Spring Data REST phục vụ nó tại profile URI khi client gửi `Accept: application/schema+json`.
- OpenAPI mô tả HTTP contract gồm paths, methods, parameters, request/response, media types và security.
- ALPS và JSON Schema được hỗ trợ trong Spring Data REST core; OpenAPI thường được bổ sung bằng springdoc hoặc công cụ tương đương.
- springdoc có hỗ trợ Spring Data REST, nhưng vẫn cần kiểm tra document được sinh có phản ánh đầy đủ HAL, projections, association, security và error responses không.
- Ba định dạng bổ trợ nhau: semantics, data shape và HTTP contract.

## Tài liệu tham khảo

- [Spring Data REST — Metadata: ALPS and JSON Schema](https://docs.spring.io/spring-data/rest/reference/metadata.html)
- [Spring Data REST — Project overview and features](https://spring.io/projects/spring-data-rest/)
- [ALPS specification](https://alps.io/spec/drafts/draft-00.html)
- [JSON Schema — Specification and documentation](https://json-schema.org/)
- [OpenAPI — Specification explained](https://learn.openapis.org/specification/)
- [OpenAPI — Paths and operations](https://learn.openapis.org/specification/paths.html)
- [OpenAPI — Parameters and payload](https://learn.openapis.org/specification/parameters.html)
- [springdoc-openapi — Spring Data REST support](https://springdoc.org/v2/#spring-data-rest-support)
