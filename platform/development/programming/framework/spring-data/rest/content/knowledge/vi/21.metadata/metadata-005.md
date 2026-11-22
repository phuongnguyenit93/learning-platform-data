# JSON Schema của tài nguyên và thương lượng media type

## Mục tiêu

Spring Data REST cung cấp metadata để client khám phá cấu trúc và ngữ nghĩa của repository resource. Hai dạng metadata quan trọng là:

- **ALPS (Application-Level Profile Semantics):** mô tả các thuộc tính và những chuyển tiếp REST mà resource hỗ trợ.
- **JSON Schema:** mô tả cấu trúc dữ liệu JSON của domain resource, gồm tên property, kiểu dữ liệu và một số metadata như `readOnly` hoặc `format`.

Client truy cập metadata qua profile link. Cùng một profile URI có thể trả về ALPS hoặc JSON Schema tùy HTTP `Accept` header.

Bên cạnh đó, Spring Data REST dùng content negotiation để chọn representation cho request và response. Client cần phân biệt:

- `Accept`: những media type client muốn nhận trong response.
- `Content-Type`: media type của request body mà client gửi.
- `Content-Type` trong response: representation server thực sự trả về.

Hiểu đúng ba phần này giúp client lấy JSON Schema, đọc HAL, gửi JSON khi POST/PUT/PATCH và gửi URI association theo đúng media type.

## 1. Metadata và profile link trong Spring Data REST

Spring Data REST tự export repository thành REST resource. Root resource trả về các link tới collection và một link `profile` để khám phá metadata.

Ví dụ root response:

    GET /

    {
      "_links": {
        "customers": {
          "href": "http://localhost:8080/customers"
        },
        "orders": {
          "href": "http://localhost:8080/orders"
        },
        "profile": {
          "href": "http://localhost:8080/profile"
        }
      }
    }

Các relation `customers`, `orders` và URL cụ thể phụ thuộc repository, cấu hình path và relation của ứng dụng. Client nên theo link server cung cấp thay vì tự ghép URL.

Tiếp tục GET profile index:

    GET /profile

Response có thể liệt kê profile URI của từng repository:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/profile"
        },
        "customers": {
          "href": "http://localhost:8080/profile/customers"
        },
        "orders": {
          "href": "http://localhost:8080/profile/orders"
        }
      }
    }

Mỗi profile URI mô tả repository tương ứng. Ví dụ `/profile/customers` cung cấp metadata cho resource Customer.

Collection response cũng có thể chứa link `profile` trong `_links`. Vì vậy, client có thể bắt đầu từ root hoặc từ collection mà nó đang sử dụng.

## 2. ALPS mô tả ngữ nghĩa và thao tác REST

ALPS là định dạng metadata mô tả ngữ nghĩa ở cấp ứng dụng. Spring Data REST cung cấp ALPS document cho mỗi exported repository.

ALPS có thể mô tả:

- Các thuộc tính của representation, ví dụ `id`, `firstName`, `lastName`.
- Các thao tác trên collection và item.
- Resource type được trả về bởi thao tác.
- Những descriptor liên quan đến projection.
- Mô tả do ứng dụng bổ sung cho resource hoặc property.

Yêu cầu ALPS:

    curl -i       -H "Accept: application/alps+json"       http://localhost:8080/profile/customers

Response có media type:

    Content-Type: application/alps+json

Ví dụ ALPS rút gọn:

    {
      "version": "1.0",
      "descriptors": [
        {
          "id": "customer-representation",
          "descriptors": [
            { "name": "firstName", "type": "SEMANTIC" },
            { "name": "lastName", "type": "SEMANTIC" },
            { "name": "address", "type": "SAFE" }
          ]
        },
        {
          "id": "get-customers",
          "name": "customers",
          "type": "SAFE",
          "rt": "#customer-representation"
        }
      ]
    }

Các type thường gặp trong ALPS:

| Type | Ý nghĩa |
|---|---|
| SEMANTIC | Thuộc tính hoặc dữ liệu có ý nghĩa trong representation |
| SAFE | Chuyển tiếp an toàn, không thay đổi trạng thái, thường là GET/HEAD |
| IDEMPOTENT | Chuyển tiếp có thể thay đổi trạng thái nhưng có tính idempotent, ví dụ PUT/DELETE |
| UNSAFE | Chuyển tiếp có thể làm thay đổi trạng thái và không idempotent, ví dụ POST |

ALPS giúp client hiểu resource cung cấp thao tác nào và các descriptor liên quan. Nó không phải JSON Schema và không thay thế tài liệu API về authorization, quy tắc nghiệp vụ hoặc lỗi runtime.

### 2.1. Thêm mô tả tùy chỉnh vào ALPS

Có thể bổ sung mô tả bằng file `rest-messages.properties` trên classpath.

Ví dụ:

    rest.description.customer=A collection of customers
    rest.description.customer.id=Customer identifier
    rest.description.customer.firstName=Customer first name
    rest.description.customer.lastName=Customer family name

Các key `rest.description.*` gắn mô tả cho resource hoặc property tương ứng. Spring Data REST đưa thông tin này vào ALPS dưới descriptor `doc`.

Có thể dùng nhiều file properties theo locale theo cơ chế message resolution của Spring. Điều này hữu ích khi API cần mô tả metadata cho nhiều ngôn ngữ.

Tên key phải tuân theo quy ước của Spring Data REST và tên domain/property thực tế. Nếu mô tả không xuất hiện, kiểm tra vị trí file, key và profile URI đang được truy cập.

## 3. JSON Schema mô tả cấu trúc resource

JSON Schema là metadata có cấu trúc, có thể đọc bằng máy và dùng làm tài liệu cho client. Spring Data REST xuất JSON Schema của repository thông qua profile URI.

Để lấy schema của Customer:

    curl -i       -H "Accept: application/schema+json"       http://localhost:8080/profile/customers

Response có media type:

    Content-Type: application/schema+json

Ví dụ JSON Schema rút gọn:

    {
      "title": "com.example.Customer",
      "properties": {
        "firstName": {
          "readOnly": false,
          "type": "string"
        },
        "lastName": {
          "readOnly": false,
          "type": "string"
        },
        "createdAt": {
          "readOnly": false,
          "type": "string",
          "format": "date-time"
        },
        "address": {
          "readOnly": false,
          "type": "string",
          "format": "uri"
        }
      },
      "descriptors": {},
      "type": "object",
      "$schema": "https://json-schema.org/draft-04/schema#"
    }

Đây là ví dụ minh họa. Property, type, format, title và dialect thực tế phụ thuộc domain model, mapping và phiên bản Spring Data REST.

Các phần thường thấy:

- `title`: tên type được export.
- `properties`: danh sách property và metadata tương ứng.
- `type`: kiểu cấu trúc của schema, thường là `object`.
- `format`: gợi ý định dạng cho kiểu string, ví dụ `date-time` hoặc `uri`.
- `readOnly`: cho biết property có được xem là chỉ đọc trong schema hay không.
- `$schema`: định danh dialect JSON Schema mà document sử dụng.

### 3.1. Kiểu dữ liệu và association

JSON Schema có thể mô tả scalar property như string, integer hoặc boolean. Association tới resource khác có thể được biểu diễn dưới dạng URI string, thường kèm `format: uri`.

Ví dụ:

    {
      "address": {
        "type": "string",
        "format": "uri"
      }
    }

Điều này phù hợp với hypermedia: client có thể liên kết association bằng URI resource được server cung cấp.

Không suy luận rằng mọi association luôn có cùng schema. Kiểu biểu diễn phụ thuộc association, repository, projection, serializer và cấu hình của ứng dụng.

### 3.2. Schema không phải database DDL

JSON Schema mô tả representation JSON mà API công bố. Nó không phải bản sao đầy đủ của schema database.

Ví dụ JSON Schema có thể mô tả property là string nhưng không thể hiện đầy đủ:

- Foreign key và cách database xử lý ON DELETE.
- Index hoặc execution plan.
- Unique constraint phức tạp theo collation.
- Quy tắc tenant hoặc quyền của principal hiện tại.
- Business rule cần gọi service hoặc kiểm tra trạng thái khác.
- Transaction boundary và concurrency behavior.

Vì vậy, không dùng JSON Schema như bằng chứng duy nhất rằng database có constraint hoặc request sẽ được chấp nhận.

### 3.3. Schema không thay thế server-side validation

Client có thể dùng JSON Schema để:

- Sinh form nhập liệu.
- Kiểm tra kiểu dữ liệu và cấu trúc trước khi gửi.
- Tạo mock payload.
- Sinh một phần client model hoặc tài liệu.
- Viết contract test cho representation.

Server vẫn phải validate request và enforce authorization/database constraint. Client có thể bị sửa hoặc gửi request trực tiếp mà không chạy validator ở giao diện.

## 4. Cùng profile URI, chọn ALPS hoặc JSON Schema bằng Accept

Profile URI là điểm truy cập metadata. Media type được chọn theo `Accept` header.

Ví dụ lấy ALPS:

    curl -i       -H "Accept: application/alps+json"       http://localhost:8080/profile/customers

Ví dụ lấy JSON Schema:

    curl -i       -H "Accept: application/schema+json"       http://localhost:8080/profile/customers

Hai request dùng cùng URI nhưng yêu cầu hai representation khác nhau. Hãy kiểm tra response header `Content-Type` để biết server đã trả loại metadata nào.

Có thể hình dung:

| Request Accept | Response Content-Type mong đợi | Nội dung |
|---|---|---|
| application/alps+json | application/alps+json | Descriptor và thao tác REST |
| application/schema+json | application/schema+json | Cấu trúc property JSON |
| application/hal+json | application/hal+json | Resource hypermedia HAL |
| application/json | Phụ thuộc cấu hình | JSON representation, mặc định thường dùng HAL trong Spring Data REST hiện đại |

Nếu không gửi `Accept`, server dùng default media type đã cấu hình. Vì vậy, client cần gửi header tường minh khi cần một loại metadata cụ thể.

## 5. Content negotiation với Accept

`Accept` là request header mô tả media type mà client có thể nhận. Server chọn một representation được endpoint và message converter hỗ trợ, rồi ghi media type thực tế vào response `Content-Type`.

Ví dụ đọc collection dưới dạng HAL:

    curl -i       -H "Accept: application/hal+json"       http://localhost:8080/customers

Response minh họa:

    HTTP/1.1 200 OK
    Content-Type: application/hal+json

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/customers"
        },
        "profile": {
          "href": "http://localhost:8080/profile/customers"
        }
      },
      "_embedded": {
        "customers": [
          {
            "firstName": "An",
            "lastName": "Nguyen"
          }
        ]
      }
    }

HAL cung cấp hypermedia controls trong `_links` và dữ liệu collection trong `_embedded`. Client có thể theo link để khám phá item, association hoặc profile.

### 5.1. application/json và HAL mặc định

Trong Spring Data REST hiện đại, khi client yêu cầu `application/json`, HAL thường được dùng làm representation mặc định. Điều này giúp API tiếp tục cung cấp link hypermedia ngay cả khi client gửi Accept tổng quát là JSON.

Có thể điều khiển hành vi này bằng `RepositoryRestConfiguration.useHalAsDefaultJsonMediaType(...)`.

Ví dụ giữ HAL làm representation cho request `application/json`:

    @Component
    public class RestConfiguration implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {
            config.useHalAsDefaultJsonMediaType(true);
        }
    }

Nếu cấu hình là `false`, Spring Data REST dùng legacy Spring Data representation khi client yêu cầu `application/json`, theo behavior của phiên bản tương ứng.

Không giả định `application/json` luôn có nghĩa JSON thuần không có hypermedia. Hãy kiểm tra `Content-Type`, response body và cấu hình thực tế.

### 5.2. Accept với nhiều lựa chọn và quality value

Client có thể gửi nhiều media type và chỉ định quality value:

    Accept: application/hal+json;q=1.0, application/json;q=0.8

Giá trị `q` thể hiện mức ưu tiên tương đối của client. Server chọn một representation phù hợp trong số media type mà endpoint hỗ trợ.

Dù gửi nhiều lựa chọn, client vẫn phải kiểm tra response `Content-Type`. Không suy luận response chỉ từ header request đã gửi.

## 6. Content-Type cho request body

`Content-Type` mô tả định dạng body client đang gửi. Spring sử dụng header này để chọn converter có thể deserialize body thành object hoặc association input.

Ví dụ tạo Customer bằng JSON:

    curl -i -X POST       -H "Content-Type: application/json"       -H "Accept: application/hal+json"       -d '{"firstName":"An","lastName":"Nguyen"}'       http://localhost:8080/customers

Hoặc gửi HAL JSON:

    curl -i -X POST       -H "Content-Type: application/hal+json"       -H "Accept: application/hal+json"       -d '{"firstName":"An","lastName":"Nguyen"}'       http://localhost:8080/customers

PUT và PATCH cũng cần Content-Type phù hợp với body và operation.

Các media type được hỗ trợ bởi repository resource theo tài liệu Spring Data REST hiện hành:

| Operation | Media type request/response thường được hỗ trợ |
|---|---|
| GET collection | application/hal+json, application/json |
| POST collection | application/hal+json, application/json |
| GET item | application/hal+json, application/json |
| PUT item | application/hal+json, application/json |
| PATCH item | application/hal+json, application/json, application/patch+json, application/merge-patch+json |
| GET association | application/hal+json, application/json |
| PUT association | text/uri-list |
| POST association collection | text/uri-list |

Danh sách chính xác phụ thuộc loại resource và phiên bản. Đặc biệt, association resource nhận URI thông qua `text/uri-list`, không nhất thiết nhận một JSON object.

### 6.1. PUT và POST association bằng text/uri-list

Ví dụ gắn một Address vào association `address` của Customer:

    curl -i -X PUT       -H "Content-Type: text/uri-list"       -d "http://localhost:8080/addresses/10"       http://localhost:8080/customers/1001/address

Với collection association, POST thêm một phần tử:

    curl -i -X POST       -H "Content-Type: text/uri-list"       -d "http://localhost:8080/orders/5001"       http://localhost:8080/customers/1001/orders

Các URL chỉ là ví dụ. Dùng association link do HAL response cung cấp thay vì tự đoán path.

## 7. PATCH và media type của patch document

PATCH mô tả một thay đổi một phần đối với resource. Spring Data REST hỗ trợ một số media type patch, gồm:

- `application/merge-patch+json`: JSON Merge Patch, mô tả trạng thái một phần cần hợp nhất.
- `application/patch+json`: media type patch được Spring Data REST hỗ trợ; semantics cụ thể phụ thuộc converter và implementation được cấu hình.
- `application/json` hoặc `application/hal+json`: tùy endpoint và phiên bản.

Ví dụ Merge Patch:

    curl -i -X PATCH       -H "Content-Type: application/merge-patch+json"       -H "Accept: application/hal+json"       -d '{"status":"INACTIVE"}'       http://localhost:8080/customers/1001

Không đổi Content-Type thành `application/merge-patch+json` nếu body thực tế không tuân theo JSON Merge Patch. Hãy dùng đúng patch format mà client và server thống nhất.

## 8. Cấu hình default media type

Spring Data REST cho phép cấu hình media type mặc định khi request không chỉ rõ loại representation.

Ví dụ:

    @Component
    public class RestConfiguration implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {
            config.setDefaultMediaType(MediaType.APPLICATION_HAL_JSON);
        }
    }

Có thể chọn default media type phù hợp với API và client. Tên constant hoặc API cấu hình có thể thay đổi theo phiên bản Spring Framework/Spring Data REST; kiểm tra dependency thực tế khi biên dịch.

Hai cấu hình có vai trò riêng:

- `setDefaultMediaType(...)`: media type mặc định khi request không chỉ định.
- `useHalAsDefaultJsonMediaType(...)`: cách xử lý request chấp nhận `application/json` trong trường hợp HAL được dùng làm representation chính.

Không cấu hình default media type mà không kiểm tra các client hiện tại. Thay đổi mặc định có thể làm thay đổi response body mà client đang parse.

## 9. Lỗi content negotiation thường gặp

### 9.1. 406 Not Acceptable

Server không tìm được representation phù hợp với `Accept` header của client.

Ví dụ client chỉ chấp nhận media type không được endpoint hỗ trợ:

    Accept: application/xml

Nếu repository resource không có converter XML tương ứng, server có thể trả:

    HTTP/1.1 406 Not Acceptable

Cách xử lý:

- Gửi media type được endpoint hỗ trợ.
- Kiểm tra custom converter và cấu hình message converter.
- Kiểm tra response thực tế của endpoint thay vì giả định tất cả endpoint hỗ trợ cùng loại.

### 9.2. 415 Unsupported Media Type

Server không hỗ trợ `Content-Type` của request body.

Ví dụ client gửi XML tới endpoint chỉ nhận JSON:

    Content-Type: application/xml

Server có thể trả:

    HTTP/1.1 415 Unsupported Media Type

Cách xử lý:

- Dùng Content-Type được endpoint hỗ trợ.
- Kiểm tra body thực sự tuân theo media type đó.
- Với association PUT/POST, kiểm tra có cần `text/uri-list` hay không.

### 9.3. 400 Bad Request

Request có media type được hỗ trợ nhưng JSON hoặc URI body không hợp lệ, thiếu dữ liệu bắt buộc hoặc không thể deserialize theo domain model.

Kiểm tra cú pháp JSON, property name, kiểu dữ liệu, association URI và validation error.

### 9.4. Nhận JSON nhưng không có _links

Nếu client nhận JSON representation không có HAL links, kiểm tra:

- `Accept` header có phải `application/json` không.
- `useHalAsDefaultJsonMediaType` đang được cấu hình thế nào.
- Endpoint có phải repository resource hay custom controller không.
- Response `Content-Type` thực tế là gì.

Không phải mọi controller trong cùng ứng dụng đều tự động tuân theo cấu hình representation của Spring Data REST.

## 10. Dùng metadata trong client và contract testing

Client có thể khám phá API theo quy trình:

1. GET root resource và đọc các collection link.
2. Theo link `profile` tới metadata index.
3. Theo profile link của repository.
4. Gửi `Accept: application/schema+json` để lấy JSON Schema.
5. Gửi `Accept: application/alps+json` để lấy ALPS.
6. Dùng JSON Schema để hiểu cấu trúc property và ALPS để hiểu descriptor/transition.
7. Gửi request với `Accept` và `Content-Type` phù hợp.
8. Kiểm tra response `Content-Type` và các hypermedia links.

Có thể dùng schema trong contract test để phát hiện thay đổi property hoặc type. Tuy nhiên, schema snapshot cần được quản lý theo version của API và Spring Data REST. Một thay đổi domain model có thể làm thay đổi metadata được export.

### 10.1. Ví dụ kiểm tra metadata bằng curl

Lấy root và profile links:

    curl -i       -H "Accept: application/hal+json"       http://localhost:8080/

    curl -i       -H "Accept: application/hal+json"       http://localhost:8080/profile

Lấy JSON Schema:

    curl -i       -H "Accept: application/schema+json"       http://localhost:8080/profile/customers

Lấy ALPS:

    curl -i       -H "Accept: application/alps+json"       http://localhost:8080/profile/customers

Đọc collection dưới dạng HAL:

    curl -i       -H "Accept: application/hal+json"       http://localhost:8080/customers

Khi chạy ứng dụng thật, thay host, port và resource path bằng link mà server trả về.

## 11. Các giới hạn cần hiểu

- JSON Schema mô tả cấu trúc representation, không phải toàn bộ business rule.
- ALPS mô tả ngữ nghĩa và transition, không thay thế authorization.
- Một profile URI có thể trả nhiều loại metadata theo Accept; hãy kiểm tra Content-Type.
- Media type được hỗ trợ có thể khác nhau giữa collection, item, association và query resource.
- `application/json` có thể được ánh xạ thành HAL theo cấu hình mặc định.
- Association write thường dùng `text/uri-list`.
- Custom controller có thể có content negotiation độc lập với repository exporter.
- Custom serializer, projection hoặc excerpt có thể làm representation khác domain type trực tiếp.
- JSON Schema được export không chứng minh database đã có foreign key, unique index hoặc constraint tương ứng.
- Client vẫn phải xử lý status code, validation error và authorization failure.

## 12. Checklist

1. GET root resource và theo link profile do server cung cấp.
2. GET `/profile` để khám phá profile URI của từng repository.
3. Dùng `Accept: application/schema+json` để lấy JSON Schema.
4. Dùng `Accept: application/alps+json` để lấy ALPS.
5. Kiểm tra `$schema` để biết dialect JSON Schema được export.
6. Dùng JSON Schema cho cấu trúc property và client-side contract checks.
7. Không coi JSON Schema là database schema hoặc authorization policy.
8. Dùng `Accept` để chọn response representation.
9. Dùng `Content-Type` đúng với request body.
10. Kiểm tra response `Content-Type` thay vì suy đoán từ request.
11. Kiểm tra HAL mặc định khi client gửi `application/json`.
12. Dùng `text/uri-list` cho association PUT/POST khi endpoint yêu cầu.
13. Dùng patch media type phù hợp với cấu trúc patch document.
14. Điều tra 406, 415 và 400 theo đúng header và body.
15. Kiểm thử metadata và content negotiation trên đúng phiên bản Spring Data REST đang chạy.

## Tài liệu tham khảo

- [Spring Data REST — Metadata, ALPS and JSON Schema](https://docs.spring.io/spring-data/rest/reference/metadata.html)
- [Spring Data REST — Repository resources and supported media types](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — RepositoryRestConfiguration API](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html)
- [Spring Boot — Spring HATEOAS and HAL media type defaults](https://docs.spring.io/spring-boot/reference/web/spring-hateoas.html)
- [JSON Schema — Media type application/schema+json](https://github.com/json-schema-org/json-schema-spec/blob/main/ietf/json-schema-media-types.md)
- [HTTP Semantics — Accept and Content-Type](https://www.rfc-editor.org/rfc/rfc9110.html)
