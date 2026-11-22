# Chọn đầu ra OpenAPI 3.0 hoặc 3.1 theo nhánh được hỗ trợ

Springdoc-openapi có thể sinh đặc tả theo OpenAPI 3.0 hoặc OpenAPI 3.1. Việc chọn phiên bản ảnh hưởng trực tiếp tới cách Schema Object biểu diễn kiểu dữ liệu, giá trị null, ràng buộc số và ví dụ. Vì vậy, lựa chọn này cần dựa trên khả năng của các công cụ tiêu thụ hợp đồng như Swagger UI, API gateway, validator, code generator và nền tảng quản lý API.

Khi làm việc với Spring Boot, cần tách bốn khái niệm:

| Phiên bản | Ví dụ | Ý nghĩa |
|---|---|---|
| Spring Boot | 3.5.x hoặc 4.1.x | Nền tảng runtime của ứng dụng. |
| springdoc-openapi | 2.10.x hoặc 3.2.x | Thư viện đọc controller và sinh tài liệu. |
| OpenAPI Specification | 3.0.x hoặc 3.1.x | Phiên bản ngôn ngữ đặc tả được ghi trong trường `openapi`. |
| API version | `info.version: 2.4.0` | Phiên bản hợp đồng/API do sản phẩm quản lý. |

Đổi `springdoc.api-docs.version` chỉ thay đổi phiên bản đặc tả được sinh. Nó không tự nâng Spring Boot, không đổi version endpoint và không thay thế quy trình versioning API.

## 1. OpenAPI 3.0 và 3.1 giải quyết cùng một mục tiêu

Cả hai phiên bản đều mô tả:

- `paths` và HTTP operations.
- Request parameters, request body và response.
- Schema, enum, validation constraints và examples.
- Authentication, security schemes và security requirements.
- Tags, servers, callbacks, links và reusable components.

Khác biệt đáng chú ý nhất nằm ở Schema Object. OpenAPI 3.0 dùng một tập con JSON Schema được điều chỉnh cho OpenAPI. OpenAPI 3.1 đồng bộ Schema Object với JSON Schema Draft 2020-12, cho phép dùng các kiểu và từ khóa JSON Schema hiện đại hơn.

Điều này làm OpenAPI 3.1 biểu đạt schema linh hoạt hơn, nhưng cũng yêu cầu validator, code generator, API gateway hoặc catalog hiểu đúng JSON Schema dialect mới.

### 1.1. Không nhầm phiên bản đặc tả với phiên bản API

Một tài liệu có thể trông như sau:

~~~yaml
openapi: 3.1.0
info:
  title: Catalog API
  version: 2.4.0
~~~

- `openapi: 3.1.0` cho biết tài liệu tuân theo nhánh OpenAPI 3.1.
- `info.version: 2.4.0` là phiên bản API mà đội sản phẩm công bố.

Nếu API chuyển từ 2.4.0 sang 2.5.0 nhưng vẫn dùng OpenAPI 3.1, chỉ `info.version` thay đổi. Nếu đội tích hợp chuyển parser từ OpenAPI 3.0 sang 3.1 mà contract API không đổi, trường `openapi` thay đổi còn `info.version` có thể giữ nguyên.

### 1.2. Phiên bản patch của đặc tả

OpenAPI Initiative phát hành các bản patch như 3.0.4 hoặc 3.1.2. Chúng vẫn thuộc nhánh 3.0 hoặc 3.1. Property của springdoc chọn chế độ 3.0/3.1; không dùng property này để yêu cầu một patch cụ thể như `3.1.2`.

Sau khi cấu hình, hãy đọc trường `openapi` thực tế trong JSON/YAML để biết chính xác patch version mà thư viện đang sinh.

## 2. Khác biệt về Schema Object

Các thay đổi schema có ảnh hưởng trực tiếp tới code generator và validator. Bảng dưới đây tóm tắt những khác biệt thường gặp khi chuyển từ 3.0 sang 3.1:

| Chủ đề | OpenAPI 3.0 | OpenAPI 3.1 |
|---|---|---|
| Nền tảng schema | Tập con JSON Schema được điều chỉnh cho OAS. | Tương thích đầy đủ hơn với JSON Schema Draft 2020-12, cộng các từ khóa OpenAPI. |
| Giá trị null | Dùng `nullable: true` cùng một `type`. | Dùng `"null"` trong danh sách `type` hoặc cấu trúc JSON Schema tương ứng. |
| Nhiều kiểu dữ liệu | `type` nhận một kiểu đơn. | `type` có thể là mảng kiểu, ví dụ `[string, "null"]`. |
| `exclusiveMinimum` | Boolean kết hợp với `minimum`. | Giá trị số trực tiếp. |
| Ví dụ ở Schema Object | `example` đơn. | `examples` theo JSON Schema; `example` trong Schema Object đã lỗi thời. |
| JSON Schema keywords | Chỉ hỗ trợ tập từ khóa được OAS 3.0 định nghĩa. | Hỗ trợ các keyword/dialect của JSON Schema 2020-12 và mở rộng OAS. |

Không phải mọi field `example` đều phải đổi thành `examples`. Media Type Object và Parameter Object vẫn có cách mô tả ví dụ riêng theo OpenAPI. Khi migration, xác định đúng vị trí của keyword thay vì thay chuỗi toàn cục.

## 3. Biểu diễn giá trị null

Đây là khác biệt dễ gặp nhất trong schema được sinh từ Java/Kotlin DTO.

### 3.1. OpenAPI 3.0 dùng `nullable`

Ví dụ một thuộc tính chuỗi có thể nhận `null`:

~~~yaml
type: object
properties:
  nickname:
    type: string
    nullable: true
~~~

Trong OpenAPI 3.0, `nullable` là từ khóa riêng của OAS. Nó phải đi cùng `type` được khai báo rõ. Không viết `type: null` hoặc `type: [string, null]` theo cú pháp JSON Schema thông thường.

### 3.2. OpenAPI 3.1 dùng union type

Schema tương đương trong OpenAPI 3.1:

~~~yaml
type: object
properties:
  nickname:
    type:
      - string
      - "null"
~~~

`null` là một kiểu dữ liệu JSON Schema. Cách biểu diễn này phù hợp với JSON Schema Draft 2020-12 và có thể được các validator JSON Schema hiện đại xử lý trực tiếp.

### 3.3. Optional và nullable là hai khái niệm khác nhau

Một property không nằm trong danh sách `required` có thể bị bỏ qua. Một property nullable có thể xuất hiện với giá trị `null`.

~~~yaml
type: object
required:
  - id
properties:
  id:
    type: string
  nickname:
    type:
      - string
      - "null"
~~~

Ở ví dụ trên:

- `id` bắt buộc có mặt.
- `nickname` có thể bị bỏ qua.
- Nếu `nickname` có mặt, giá trị có thể là chuỗi hoặc `null`.

Không dùng `nullable` hoặc union type để thay thế `required`. Hãy kiểm tra cả hai khía cạnh khi đối chiếu DTO với JSON thực tế.

## 4. Ràng buộc số thay đổi trong OpenAPI 3.1

OpenAPI 3.0 dùng Boolean cho `exclusiveMinimum` và `exclusiveMaximum`, kết hợp với `minimum`/`maximum`.

~~~yaml
# OpenAPI 3.0
type: number
minimum: 10
exclusiveMinimum: true
maximum: 100
exclusiveMaximum: false
~~~

Trong OpenAPI 3.0, ví dụ này có nghĩa giá trị phải lớn hơn 10 và nhỏ hơn hoặc bằng 100.

OpenAPI 3.1 dùng giá trị số trực tiếp:

~~~yaml
# OpenAPI 3.1
type: number
exclusiveMinimum: 10
maximum: 100
~~~

Đừng giữ nguyên cú pháp Boolean của 3.0 khi chuyển schema sang 3.1. Hãy kiểm tra các ràng buộc được tạo từ Bean Validation như `@DecimalMin`, `@DecimalMax`, `@Min` và `@Max`, sau đó xác nhận JSON Schema cuối cùng biểu diễn đúng điều kiện nghiệp vụ.

## 5. Ví dụ trong Schema Object

Trong OpenAPI 3.0, Schema Object thường dùng `example`:

~~~yaml
type: string
format: email
example: developer@example.com
~~~

OpenAPI 3.1 đồng bộ với JSON Schema `examples`:

~~~yaml
type: string
format: email
examples:
  - developer@example.com
  - support@example.com
~~~

Tuy nhiên, `example` vẫn xuất hiện ở những vị trí khác của OpenAPI, chẳng hạn Media Type Object. Ví dụ:

~~~yaml
content:
  application/json:
    example:
      id: "d4a8f9"
      nickname: null
~~~

Khi chuyển đổi, phân biệt Schema Object với Example Object/Media Type Object. Dùng `examples` cho Schema Object theo JSON Schema, còn ví dụ payload của media type tuân theo cấu trúc tương ứng trong OpenAPI.

## 6. JSON Schema 2020-12 mở rộng khả năng mô tả

OpenAPI 3.1 cho phép tận dụng nhiều keyword của JSON Schema, ví dụ:

- `if`, `then`, `else` để mô tả điều kiện schema.
- `prefixItems` cho tuple/array có vị trí phần tử với schema riêng.
- `contentEncoding` và `contentMediaType` để mô tả nội dung được mã hóa.
- `$schema` hoặc `jsonSchemaDialect` để xác định dialect trong trường hợp cần chỉ rõ.
- Các keyword JSON Schema khác được dialect cho phép.

Ví dụ schema có điều kiện:

~~~yaml
type: object
required:
  - paymentMethod
properties:
  paymentMethod:
    type: string
    enum: [card, bank_transfer]
  cardToken:
    type: string
  bankAccount:
    type: string
if:
  required:
    - paymentMethod
  properties:
    paymentMethod:
      const: card
then:
  required:
    - cardToken
else:
  required:
    - bankAccount
~~~

Schema này diễn tả rằng khi `paymentMethod` là `card`, object phải có `cardToken`; trong trường hợp còn lại, object phải có `bankAccount`. Hãy xác nhận validator và code generator phía client có hỗ trợ các keyword này trước khi dùng trong contract được phát hành.

### 6.1. Upload file và content metadata

OpenAPI 3.0 thường mô tả binary upload bằng:

~~~yaml
type: string
format: binary
~~~

OpenAPI 3.1 có thể tận dụng `contentMediaType` và `contentEncoding` theo JSON Schema. Ví dụ nội dung base64:

~~~yaml
type: string
contentEncoding: base64
contentMediaType: image/png
~~~

Đối với multipart request, vẫn cần mô tả đúng media type, từng part và cấu trúc payload. Không thay toàn bộ schema file upload chỉ vì chuyển sang 3.1; chọn cách biểu diễn phù hợp với wire format thực tế và khả năng parser của client.

## 7. Cấu hình phiên bản đầu ra trong springdoc

Springdoc cung cấp property `springdoc.api-docs.version` để chọn OpenAPI 3.0 hoặc 3.1. Tài liệu property hiện hành ghi mặc định là `openapi_3_1`.

### 7.1. Chọn OpenAPI 3.1

Trong `application.yml`:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

Đây là lựa chọn phù hợp khi toàn bộ công cụ downstream đã hỗ trợ OpenAPI 3.1 và ứng dụng cần các khả năng schema theo JSON Schema 2020-12.

### 7.2. Chọn OpenAPI 3.0

Nếu API gateway, validator, code generator hoặc developer portal chỉ hỗ trợ 3.0, cấu hình:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_0
~~~

Giá trị `OPENAPI_3_0` và `OPENAPI_3_1` chọn chế độ serialization/schema của tài liệu. Không tự sửa trường `openapi` sau khi sinh để giả lập phiên bản khác; các Schema Object có thể vẫn mang cú pháp của phiên bản ban đầu.

### 7.3. Dùng profile cho môi trường hoặc nhóm triển khai

Nếu một nhóm triển khai cần OpenAPI 3.0 để tương thích với hệ thống cũ, có thể cấu hình theo profile:

~~~yaml
# application.yml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

~~~yaml
# application-legacy-contract.yml
springdoc:
  api-docs:
    version: OPENAPI_3_0
~~~

Chỉ một profile đang hoạt động sẽ quyết định chế độ đầu ra của instance đó. Cách này phù hợp khi chạy hai deployment hoặc pipeline riêng. Không nên kỳ vọng cùng một instance tự phát sinh hai dialect khác nhau chỉ bằng cách thay query parameter.

## 8. Chọn phiên bản springdoc tương thích với Spring Boot

Phiên bản thư viện springdoc phải tương thích với major/minor line của Spring Boot trước khi chọn OpenAPI 3.0 hay 3.1.

Theo compatibility matrix của dự án springdoc tại thời điểm biên soạn:

| Spring Boot | Nhánh springdoc tương ứng | Ghi chú |
|---|---|---|
| 4.1.x | springdoc 3.1.x – 3.2.x | Dùng nhánh springdoc 3.x. |
| 4.0.x | springdoc 3.0.x | Dùng nhánh springdoc 3.x. |
| 3.5.x | springdoc 2.8.x – 2.10.x | Dùng nhánh springdoc 2.x. |
| 3.4.x | springdoc 2.7.x – 2.8.x | Dùng nhánh springdoc 2.x. |
| 3.3.x | springdoc 2.6.x | Dùng nhánh springdoc 2.x. |
| 3.2.x | springdoc 2.3.x – 2.5.x | Dùng nhánh springdoc 2.x. |
| 3.1.x | springdoc 2.2.x | Dùng nhánh springdoc 2.x. |
| 3.0.x | springdoc 2.0.x – 2.1.x | Dùng nhánh springdoc 2.x. |
| Spring Boot 2.x/1.x | springdoc 1.x | Nhánh legacy; kiểm tra trạng thái hỗ trợ và tài liệu v1. |

Matrix có thể thay đổi theo các bản phát hành. Khi nâng cấp, kiểm tra compatibility matrix hiện hành thay vì chỉ chọn phiên bản springdoc mới nhất. Springdoc 2.x được xây dựng cho Spring Boot 3; springdoc 3.x dành cho Spring Boot 4.

### 8.1. Springdoc version không quyết định API version

Ví dụ ứng dụng dùng Spring Boot 3.5, springdoc 2.10 và OpenAPI 3.1:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

Nếu một client cũ cần OpenAPI 3.0, có thể đổi property sang `OPENAPI_3_0` mà không đổi API `info.version`. Tuy nhiên, nếu cần dùng một tính năng chỉ có trong OAS 3.1, phải đánh giá lại schema và công cụ downstream trước khi hạ xuống 3.0.

## 9. Chọn 3.0 hay 3.1 theo khả năng tương thích

Không nên chọn 3.1 chỉ vì đó là mặc định hiện tại của springdoc. Hãy lập danh sách hệ thống tiêu thụ tài liệu:

| Thành phần | Điều cần xác minh |
|---|---|
| Swagger UI | Phiên bản đang dùng có render đúng OpenAPI 3.1 và Schema Object mới không? |
| API gateway | Có import, validate và chuyển đổi OpenAPI 3.1 không? |
| OpenAPI parser | Parser có nhận đúng `openapi: 3.1.x` và JSON Schema 2020-12 không? |
| Code generator | Generator có xử lý `type: [string, "null"]`, conditional schema và `examples` đúng không? |
| Contract testing | Công cụ có validate schema 3.1 và các dialect liên quan không? |
| API catalog/portal | Catalog có hiển thị schema, nullable field và example theo 3.1 không? |
| Client SDK đã phát hành | Chuyển schema có làm thay đổi model nullability hoặc generated code không? |

### 9.1. Khi nên chọn OpenAPI 3.0

Chọn 3.0 khi:

- API gateway hoặc API catalog chỉ chấp nhận OAS 3.0.
- Client generator chưa hỗ trợ JSON Schema 2020-12.
- Hệ thống contract testing đang khóa theo validator 3.0.
- Các đối tác tích hợp đã thống nhất schema 3.0 và chưa thể nâng cấp.
- Schema của API không cần keyword mới của JSON Schema.

OpenAPI 3.0 vẫn đáp ứng phần lớn nhu cầu mô tả REST API thông thường. Không cần chuyển phiên bản chỉ để thay đổi một nhãn trong tài liệu.

### 9.2. Khi nên chọn OpenAPI 3.1

Chọn 3.1 khi:

- Tất cả consumer chính đã hỗ trợ OAS 3.1.
- Cần mô tả null bằng JSON Schema type union.
- Cần conditional schema hoặc các keyword JSON Schema 2020-12.
- Cần chia sẻ schema với hệ sinh thái JSON Schema mà không phải chuyển đổi nhiều.
- Muốn chuẩn hóa contract theo dialect mới hơn và có thể kiểm thử toàn bộ pipeline.

OpenAPI 3.1 có thể cải thiện tính chính xác của schema, nhưng chỉ khi các công cụ tiêu thụ diễn giải schema đúng như hợp đồng mong muốn.

## 10. Quy trình chuyển từ OpenAPI 3.0 sang 3.1

Thay đổi property chỉ là bước đầu. Một migration nên đi qua các bước:

1. **Kiểm kê consumer**: liệt kê Swagger UI, gateway, parser, generator, contract tests, API catalog và client SDK.
2. **Kiểm tra compatibility**: xác nhận phiên bản công cụ hỗ trợ OpenAPI 3.1 và JSON Schema Draft 2020-12.
3. **Sinh tài liệu 3.1**: đặt `springdoc.api-docs.version=OPENAPI_3_1` trong môi trường kiểm thử.
4. **So sánh schema**: kiểm tra `nullable`, union type, `exclusiveMinimum`, `exclusiveMaximum`, `example` và `examples`.
5. **Rà soát JSON Schema keywords**: xác nhận keyword mới không làm validator hoặc generator hiểu sai.
6. **Validate đặc tả**: dùng validator hỗ trợ OAS 3.1, không dùng cấu hình chỉ hiểu OAS 3.0.
7. **Generate thử SDK**: so sánh model, nullability, enum và kiểu dữ liệu giữa hai đầu ra.
8. **Chạy contract tests**: kiểm tra payload hợp lệ/không hợp lệ theo schema mới.
9. **Kiểm tra Swagger UI và API gateway**: import, render, authorize và thử request.
10. **Phát hành có kiểm soát**: lưu artifact mới, ghi rõ spec version và API version, chuẩn bị rollback.

### 10.1. So sánh hai tài liệu được sinh

Lưu hai artifact từ cùng một revision ứng dụng:

- `openapi-3.0.json`
- `openapi-3.1.json`

Sau đó so sánh:

- Trường `openapi`.
- `components.schemas` và các `$ref`.
- Nullable fields.
- Ràng buộc số và chuỗi.
- Examples ở Schema Object và Media Type Object.
- Request/response content.
- Security schemes.
- Server URL và path.

Không chỉ so sánh text vì thứ tự key hoặc cách pretty-print có thể khác. Nên parse hai tài liệu rồi so sánh cấu trúc và chạy validator phù hợp cho từng phiên bản.

## 11. Kiểm tra đầu ra bằng MockMvc

Một integration test có thể xác nhận springdoc đang phát đúng nhánh OpenAPI đã cấu hình.

Ví dụ kiểm tra OpenAPI 3.1:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "springdoc.api-docs.version=OPENAPI_3_1"
})
@AutoConfigureMockMvc
class OpenApiVersionContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publishesOpenApi31Document() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.openapi", startsWith("3.1.")));
    }
}
~~~

Để kiểm tra 3.0, thay property bằng `OPENAPI_3_0` và matcher thành `startsWith("3.0.")`. Dùng prefix thay vì hard-code patch version vì patch có thể phụ thuộc phiên bản springdoc/swagger-core.

### 11.1. Kiểm tra YAML output

Springdoc thường cung cấp cả JSON và YAML:

- JSON: `/v3/api-docs`
- YAML: `/v3/api-docs.yaml`

Có thể lấy hai đầu ra trong CI:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
curl -fsS http://localhost:8080/v3/api-docs.yaml -o openapi.yaml
~~~

Parse cả hai và xác nhận trường `openapi` cùng schema tương ứng. Không nên chỉ test JSON nếu artifact phát hành cho đối tác là YAML hoặc ngược lại.

### 11.2. Kiểm tra `info.version` độc lập

Trong cùng test suite, có thể kiểm tra API release version:

~~~java
mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.info.version").value("2.4.0"));
~~~

Test này xác minh API version. Nó không thay thế test `$.openapi` vì hai trường có ý nghĩa khác nhau.

## 12. Những lỗi thường gặp

- **Đổi `info.version` để chọn OpenAPI 3.1**: `info.version` chỉ là phiên bản API; dùng `springdoc.api-docs.version`.
- **Đổi `openapi` bằng tay sau khi sinh**: schema vẫn có thể mang cú pháp của dialect cũ.
- **Giữ `nullable: true` như thể là JSON Schema chuẩn 2020-12**: chuyển sang type union có `"null"` khi schema dùng cú pháp 3.1.
- **Giữ `exclusiveMinimum: true` trong 3.1**: 3.1 dùng giá trị số trực tiếp.
- **Thay mọi `example` bằng `examples`**: chỉ Schema Object có khác biệt này; Media Type Object và các vị trí khác cần được xử lý theo cấu trúc riêng.
- **Chỉ kiểm tra Swagger UI render được**: UI render thành công không chứng minh gateway, validator và code generator hiểu schema đúng.
- **Nâng springdoc mà không kiểm tra Spring Boot**: major version springdoc phải theo compatibility matrix của Spring Boot.
- **Cho rằng springdoc 3.x đồng nghĩa OpenAPI 3.1**: version thư viện và version đặc tả là hai lựa chọn riêng.
- **Dùng parser OAS 3.0 để validate tài liệu 3.1**: parser có thể từ chối hoặc bỏ qua keyword mới.
- **Không test YAML**: JSON đúng không bảo đảm artifact YAML được phát hành đúng.
- **Bỏ qua SDK đã phát hành**: thay đổi nullability hoặc schema có thể ảnh hưởng model được sinh và logic client.
- **Giả định springdoc hỗ trợ mọi phiên bản OpenAPI mới nhất**: kiểm tra property và khả năng serialization của đúng nhánh thư viện trước khi chọn dialect.

## 13. Lưu ý về OpenAPI 3.2

OpenAPI Initiative đã công bố nhánh OpenAPI 3.2. Tuy nhiên, property `springdoc.api-docs.version` trong tài liệu springdoc hiện hành mô tả hai lựa chọn `OPENAPI_3_0` và `OPENAPI_3_1`.

Không đặt `OPENAPI_3_2` hoặc tự sửa trường `openapi` thành `3.2.x` nếu phiên bản springdoc và Swagger Core đang dùng chưa hỗ trợ serialization cùng schema theo OAS 3.2. Khi cần 3.2, hãy kiểm tra release notes và tài liệu của thư viện, parser, UI và generator trước khi xây dựng pipeline.

## 14. Quy trình chọn phiên bản cho dự án

1. **Xác định Spring Boot line** đang chạy.
2. **Chọn springdoc branch tương thích** với Boot line.
3. **Kiểm tra property** `springdoc.api-docs.version` trên branch đó.
4. **Lập danh sách consumer** của OpenAPI JSON/YAML.
5. **Chọn 3.0** nếu cần tương thích hệ thống cũ; chọn 3.1 khi toàn bộ consumer hỗ trợ schema mới.
6. **Cấu hình profile** để kiểm thử hoặc phát hành artifact theo dialect đã chọn.
7. **Validate JSON và YAML** bằng tool hiểu đúng OAS version.
8. **So sánh schema và SDK** trước khi thay đổi contract.
9. **Ghi rõ API version và spec version** trong artifact/release note.
10. **Theo dõi compatibility** khi nâng Spring Boot, springdoc, Swagger UI hoặc code generator.

## 15. Checklist review

- [ ] Đã phân biệt Spring Boot version, springdoc version, OpenAPI version và `info.version`.
- [ ] Springdoc branch tương thích với Spring Boot đang dùng.
- [ ] Giá trị `springdoc.api-docs.version` là `OPENAPI_3_0` hoặc `OPENAPI_3_1` theo chủ đích.
- [ ] Đã kiểm tra trường `openapi` trong JSON/YAML đầu ra.
- [ ] Schema nullable và required được biểu diễn đúng.
- [ ] `exclusiveMinimum` và `exclusiveMaximum` đúng dialect.
- [ ] `example`/`examples` nằm đúng vị trí của OpenAPI Object.
- [ ] Validator và parser hỗ trợ phiên bản được chọn.
- [ ] Swagger UI và API gateway render/import đúng.
- [ ] Code generator tạo model đúng nullability và kiểu dữ liệu.
- [ ] Contract tests bao phủ payload hợp lệ và không hợp lệ.
- [ ] JSON và YAML đều được kiểm tra nếu cả hai định dạng được phát hành.
- [ ] Artifact ghi rõ API version và OpenAPI specification version.
- [ ] Không tự đổi `openapi` field để giả lập dialect chưa được thư viện hỗ trợ.

## 16. Tài liệu tham khảo

- [springdoc-openapi – Core properties](https://springdoc.org/core-properties.html)
- [springdoc-openapi v2 – Core properties](https://springdoc.org/v2/core-properties.html)
- [springdoc-openapi – Compatibility matrix](https://springdoc.org/#what-is-the-compatibility-matrix-of-springdoc-openapi-with-spring-boot)
- [springdoc-openapi GitHub README](https://github.com/springdoc/springdoc-openapi)
- [OpenAPI Initiative – Specification versions](https://spec.openapis.org/oas/)
- [OpenAPI 3.1 – Upgrading from OpenAPI 3.0](https://learn.openapis.org/upgrading/v3.0-to-v3.1.html)
- [Swagger – OpenAPI 3.0 Data Types](https://swagger.io/docs/specification/v3_0/data-models/data-types/)
- [Swagger – OpenAPI 3.1 Specification](https://swagger.io/specification/v3.1/)

Chọn OpenAPI 3.0 hay 3.1 là quyết định về ngôn ngữ hợp đồng và khả năng tương thích của toàn bộ hệ sinh thái. Hãy chọn đúng nhánh springdoc theo Spring Boot, đặt `springdoc.api-docs.version`, kiểm tra schema theo dialect tương ứng và xác minh JSON/YAML bằng chính các công cụ sẽ tiêu thụ tài liệu. Giữ `info.version` độc lập để quản lý vòng đời API mà không làm lẫn nó với phiên bản đặc tả.
