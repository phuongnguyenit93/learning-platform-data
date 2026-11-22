# Kiểm tra tương thích với parser, UI, bộ sinh mã và công cụ kiểm thử

Một tài liệu OpenAPI có thể hợp lệ theo đặc tả nhưng vẫn không dùng được trong toàn bộ chuỗi công cụ của dự án. Parser có thể đọc được nhưng validator không hiểu một số keyword; Swagger UI có thể render phần lớn operation nhưng bỏ qua tính năng mới; code generator có thể tạo client sai hoặc bỏ qua operation; contract test có thể kiểm tra runtime mà không phát hiện tài liệu sai.

Vì vậy, kiểm tra tương thích cần bao phủ cả **phiên bản OpenAPI**, **springdoc-openapi**, **parser/validator**, **Swagger UI**, **code generator** và **công cụ kiểm thử**. Không nên kết luận toàn bộ hệ sinh thái tương thích chỉ vì một trang Swagger UI mở thành công.

Bài này trình bày cách chọn phiên bản OpenAPI, hiểu khác biệt giữa 3.0, 3.1 và 3.2, lập ma trận tương thích, kiểm tra các công cụ downstream, tổ chức CI và nâng cấp đặc tả theo từng bước.

## 1. Phân biệt các lớp phiên bản

Trong một dự án Spring Boot, có nhiều phiên bản độc lập:

| Lớp | Ví dụ | Ý nghĩa |
|---|---|---|
| Spring Boot | 3.x hoặc 4.x | Nền tảng ứng dụng |
| springdoc-openapi | 2.x hoặc 3.x | Thư viện đọc metadata Spring và sinh OpenAPI |
| OpenAPI Specification | 3.0, 3.1 hoặc 3.2 | Phiên bản định dạng tài liệu được sinh |
| Swagger Core / swagger-models | 2.x hoặc 3.x | Mô hình và annotation OpenAPI mà springdoc sử dụng |
| Swagger UI | 5.x | Giao diện đọc và hiển thị tài liệu |
| Parser / validator | Ví dụ swagger-parser | Đọc, phân tích và kiểm tra tài liệu |
| Code generator | Ví dụ OpenAPI Generator | Sinh client hoặc server stub |
| Contract test tool | Công cụ kiểm tra request/response theo spec | Đối chiếu tài liệu với hành vi runtime |

Các phiên bản này không đồng nghĩa với nhau. springdoc 3.x không có nghĩa tài liệu đầu ra tự động là OpenAPI 3.2. OpenAPI 3.1 cũng không có nghĩa Swagger UI, parser và generator trong dự án đều đã hỗ trợ mọi tính năng của 3.1.

Khi báo lỗi tương thích, hãy ghi đủ phiên bản của từng lớp. Chỉ ghi “đang dùng OpenAPI 3” là chưa đủ để tái hiện vấn đề.

## 2. Các phiên bản OpenAPI cần nhận biết

OpenAPI dùng chuỗi phiên bản theo dạng major.minor.patch. Các nhánh phổ biến hiện nay gồm:

| Nhánh | Phiên bản patch tiêu biểu | Điểm cần quan tâm |
|---|---|---|
| OpenAPI 3.0 | 3.0.4 | Nhiều công cụ cũ hỗ trợ rộng; Schema Object dùng tập con JSON Schema riêng |
| OpenAPI 3.1 | 3.1.2 | Đồng bộ Schema Object với JSON Schema 2020-12 và thay đổi cách mô tả null |
| OpenAPI 3.2 | 3.2.1 | Bổ sung khả năng mới như tag lồng nhau, operation method mở rộng, streaming và document identity |

Tại thời điểm biên soạn, OpenAPI 3.2.1 là bản mới nhất; 3.2.0 được công bố ngày 19-09-2025 và 3.2.1 là bản patch ngày 10-09-2026. Bản patch chủ yếu sửa lỗi và làm rõ đặc tả, không tạo một feature set mới so với cùng nhánh minor.

Theo quy ước phiên bản của OpenAPI, phần major.minor xác định feature set. Công cụ hỗ trợ một nhánh minor nên hướng tới tương thích với các bản patch thuộc nhánh đó. Tuy vậy, dự án vẫn cần chạy parser, UI, generator và test với đúng bản tài liệu được phát hành.

Không nên tự nâng trường openapi trong JSON từ 3.1.0 lên 3.2.1 nếu tài liệu vẫn được tạo theo mô hình 3.1. Thay số phiên bản không tự bổ sung các object, keyword hoặc quy tắc của phiên bản mới.

## 3. Khác biệt quan trọng giữa OpenAPI 3.0 và 3.1

Một khác biệt lớn nằm ở Schema Object.

OpenAPI 3.0 dùng một tập con JSON Schema riêng. Ví dụ, thuộc tính nullable có thể được dùng để mô tả giá trị null:

~~~yaml
type: string
nullable: true
~~~

OpenAPI 3.1 dựa trên JSON Schema 2020-12. Kiểu dữ liệu có thể bao gồm null theo cú pháp JSON Schema:

~~~yaml
type:
  - string
  - "null"
~~~

Điều này ảnh hưởng trực tiếp tới parser, validator, UI và code generator. Một công cụ cũ có thể hiểu nullable của 3.0 nhưng xử lý sai type array chứa null của 3.1.

Các điểm cần kiểm tra khi chuyển 3.0 sang 3.1:

- Cách biểu diễn nullable và union type.
- JSON Schema keywords và dialect.
- $schema và jsonSchemaDialect nếu được sử dụng.
- exclusiveMinimum, exclusiveMaximum và các constraint.
- oneOf, anyOf, allOf và discriminator.
- $ref, anchor và cách giải quyết reference.
- Schema được inline hay đặt trong components.
- Client generator ánh xạ optional, nullable và enum ra ngôn ngữ đích thế nào.

Không nên chỉ thay giá trị trường openapi. Hãy kiểm tra lại schema sinh ra và code client được tạo.

## 4. Những điểm mới đáng chú ý của OpenAPI 3.2

OpenAPI 3.2 bổ sung một số khả năng mà công cụ cũ có thể chưa nhận biết:

- Tag có thêm summary, parent và kind để tổ chức tài liệu theo cấu trúc lồng nhau.
- HTTP QUERY được hỗ trợ như một operation method chuẩn.
- additionalOperations cho phép mô tả các HTTP method khác ngoài những khóa operation quen thuộc.
- $self cung cấp document identity/base URI phục vụ giải quyết relative reference.
- Bổ sung khả năng mô tả streaming và các kiểu media type liên quan.
- Cải tiến cách mô tả ví dụ, discriminator và một số nội dung khác.

Ví dụ tag lồng nhau:

~~~yaml
tags:
  - name: orders
    summary: Quản lý đơn hàng
    kind: nav
  - name: order-admin
    parent: orders
    summary: Thao tác quản trị đơn hàng
~~~

Ví dụ operation QUERY:

~~~yaml
paths:
  /orders/search:
    query:
      summary: Truy vấn đơn hàng theo điều kiện
      responses:
        "200":
          description: Kết quả truy vấn
~~~

Một parser chỉ biết các method của OpenAPI 3.1 có thể từ chối hoặc bỏ qua operation QUERY. Code generator cũng có thể không tạo method tương ứng.

Vì vậy, trước khi sử dụng tính năng mới của 3.2, hãy xác minh từng công cụ downstream. Tài liệu có thể render được không chứng minh rằng code generator đã hiểu operation mới.

## 5. Kiểm tra khả năng của springdoc-openapi

springdoc có hai trách nhiệm cần phân biệt:

1. Tương thích với phiên bản Spring Boot và Spring Framework.
2. Chọn phiên bản OpenAPI mà tài liệu đầu ra sử dụng.

Ma trận tương thích Spring Boot và springdoc hiện hành được công bố theo các dòng chính:

| Spring Boot | Dòng springdoc tương ứng |
|---|---|
| Spring Boot 4.x | springdoc 3.x |
| Spring Boot 3.x | springdoc 2.x |
| Spring Boot 2.x và 1.x | springdoc 1.8.0; nhánh này đã hết hỗ trợ mã nguồn mở |

Tài liệu hiện hành còn phân biệt Spring Boot 4.0.x với 4.1.x ở các minor release của springdoc. Hãy dùng bảng compatibility trên trang chính thức tại thời điểm nâng cấp, không ghép tùy ý một phiên bản Boot với một phiên bản springdoc.

Thuộc tính springdoc.api-docs.version hiện cho phép chọn OpenAPI 3.0 hoặc 3.1. Giá trị mặc định được tài liệu cấu hình hiện hành công bố là openapi_3_1. Chưa có lựa chọn OPENAPI_3_2 trong danh sách property đó.

application.yml:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

Hoặc chọn 3.0:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_0
~~~

Không tự thêm giá trị OPENAPI_3_2 nếu phiên bản springdoc không hỗ trợ. Cấu hình không được hỗ trợ có thể bị bỏ qua, bị bind như chuỗi không hợp lệ hoặc không tạo ra document theo feature set mong muốn.

## 6. Lưu ý hiện trạng hỗ trợ OpenAPI 3.2 trong springdoc

Tại thời điểm biên soạn, tài liệu properties của springdoc công bố lựa chọn OpenAPI 3.0 và 3.1. Yêu cầu bổ sung hỗ trợ OpenAPI 3.2 vẫn được theo dõi trong issue upstream.

Điều này có nghĩa:

- Không nên giả định springdoc hiện tại có thể sinh đầy đủ OpenAPI 3.2 chỉ vì thư viện đã có major version mới.
- Không sửa trường openapi trong JSON sau khi sinh để giả lập 3.2.
- Không thêm các cấu trúc 3.2 vào OpenAPI model nếu swagger-core/swagger-models của dự án chưa biểu diễn được chúng.
- Nếu cần sử dụng tính năng 3.2 ngay, có thể cần một pipeline tạo spec độc lập hoặc một công cụ authoring hỗ trợ 3.2.
- Nếu ứng dụng dùng springdoc để sinh tài liệu, hãy chọn 3.0 hoặc 3.1 theo property được hỗ trợ và kiểm tra các công cụ tiêu thụ tương ứng.

Đây là trạng thái tại ngày 20-11-2026. Khi nâng cấp dự án, hãy kiểm tra changelog và properties của đúng phiên bản springdoc đang pin vì tình trạng hỗ trợ có thể thay đổi.

## 7. Lập compatibility matrix cho toàn bộ toolchain

Một ma trận tốt ghi lại phiên bản thực tế và kết quả thử nghiệm:

| Thành phần | Phiên bản pin | OAS được kiểm tra | Kết quả |
|---|---|---|---|
| springdoc-openapi | Phiên bản trong build | 3.0 / 3.1 | Sinh document và đúng schema |
| Swagger UI | Phiên bản được đóng gói | 3.1 hoặc 3.2 | Render operation, security và schema |
| Swagger Parser | Phiên bản trong test | 3.1 hoặc 3.2 | Parse và resolve reference |
| OpenAPI Generator | Phiên bản CLI/plugin | 3.1 hoặc 3.2 | Validate, sinh client và compile |
| Contract validator | Phiên bản pin | 3.1 hoặc 3.2 | Validate document và response |
| WebTestClient/MockMvc | Phiên bản theo Spring Boot | Runtime API | Request/response khớp hợp đồng |

Không ghi “latest” làm phiên bản trong ma trận. Dùng số phiên bản cụ thể để kết quả CI có thể tái lập.

Một hàng chỉ được đánh dấu PASS khi đã chạy thử các cấu trúc mà API thực sự sử dụng. Nếu tool chỉ đọc được một document đơn giản nhưng chưa xử lý nullable, oneOf hoặc QUERY, hãy ghi giới hạn đó.

Ảnh chụp trạng thái công cụ tại ngày 20-11-2026 cho thấy các mức hỗ trợ có thể khác nhau:

| Công cụ | Phiên bản/thông tin được công bố | Cách diễn giải |
|---|---|---|
| springdoc-openapi | Properties hiện chỉ chọn OPENAPI_3_0 hoặc OPENAPI_3_1; issue hỗ trợ OAS 3.2 vẫn mở | Không dùng springdoc làm nguồn sinh OAS 3.2 cho tới khi release công bố hỗ trợ |
| Swagger UI | Bảng compatibility của Swagger UI 5.32.0 liệt kê OAS 3.2.0 | UI độc lập có thể render 3.2.0; phải kiểm tra đúng WebJar đang được springdoc đóng gói |
| Swagger Parser | Dòng 2.1.x hỗ trợ OAS 3.1 từ 2.1.0; release 2.1.48 không đồng nghĩa có hỗ trợ 3.2 | Kiểm tra issue 3.2 và release notes trước khi dùng làm validator cho OAS 3.2 |
| OpenAPI Generator | README hiện liệt kê OAS 3.1 ở mức beta; bản stable 7.27.0 chưa liệt kê 3.2 | Không giả định generator xử lý đầy đủ operation hoặc keyword mới của 3.2 |

Đây là trạng thái được ghi nhận từ tài liệu và repository upstream tại thời điểm biên soạn, không phải cam kết rằng mọi cấu hình hoặc mọi generator target đều có cùng kết quả. Trước mỗi lần nâng cấp, hãy kiểm tra lại release notes và chạy fixture đại diện của dự án.

## 8. Swagger UI có thể hỗ trợ khác với springdoc

Swagger UI là lớp hiển thị tài liệu. Nó không phải parser, generator và validator duy nhất trong pipeline.

Tài liệu tương thích của Swagger UI 5.32.0 liệt kê hỗ trợ OpenAPI 2.0, 3.0.x, 3.1.x và 3.2.0. Điều này cho thấy một bản Swagger UI độc lập có thể render được một số document 3.2, nhưng không chứng minh springdoc đã sinh được 3.2 hoặc parser/code generator trong dự án hiểu đầy đủ cùng tài liệu.

Khi dùng Swagger UI được đóng gói cùng springdoc:

1. Kiểm tra phiên bản swagger-ui WebJar thực tế trong dependency tree.
2. Xác định phiên bản đó có hỗ trợ OAS mà API công bố không.
3. Mở UI với document có các feature đang dùng.
4. Kiểm tra operation, parameters, schemas, security và examples.
5. Kiểm tra browser console và network khi render lỗi.
6. Không chỉ thử một endpoint GET đơn giản.

Có thể kiểm tra dependency Maven:

~~~bash
mvn dependency:tree -Dincludes=org.webjars:swagger-ui
~~~

Phiên bản Swagger UI mới nhất độc lập có thể khác phiên bản được springdoc kéo vào. Nếu cần nâng Swagger UI, hãy kiểm tra tương thích với springdoc và các dependency liên quan thay vì ghi đè WebJar một cách tùy tiện.

## 9. Parser và validator cần hiểu đúng OAS version

Parser chuyển JSON/YAML thành mô hình đối tượng OpenAPI. Validator kiểm tra tài liệu theo quy tắc đặc tả. Một số công cụ kết hợp cả hai nhiệm vụ.

Swagger Parser hỗ trợ OpenAPI 3.1 từ dòng 2.1.0. Tuy nhiên, hỗ trợ 3.1 không đồng nghĩa tự động hỗ trợ mọi feature của 3.2. Yêu cầu hỗ trợ OpenAPI 3.2 đã được mở trong repository swagger-parser; cần kiểm tra trạng thái issue và release tương ứng trước khi chọn công cụ.

Một parser có thể:

- Từ chối document vì version không được nhận diện.
- Parse được phần cấu trúc cũ nhưng bỏ qua field mới.
- Trả warning thay vì error.
- Resolve một số $ref nhưng không xử lý đầy đủ JSON Schema dialect.
- Đọc JSON nhưng xử lý YAML khác với dự kiến.

Hãy đọc cả lỗi và warning. Không coi việc parser trả về một object là bằng chứng toàn bộ document hợp lệ.

Nếu parser được dùng trong ứng dụng Java, hãy pin phiên bản dependency và tạo test với document mẫu đại diện cho feature set của dự án. Không chỉ test file OpenAPI đơn giản nhất.

## 10. Code generator cần được kiểm tra riêng

Code generator có thể đọc được document nhưng vẫn sinh code không đúng với ý nghĩa API.

Các lỗi có thể gặp:

- nullable bị ánh xạ thành non-nullable.
- Optional và required bị hiểu sai.
- Enum hoặc oneOf tạo model không chính xác.
- Discriminator không ánh xạ đúng subtype.
- Request body hoặc multipart bị mất encoding.
- Security scheme không tạo cấu hình client như mong đợi.
- Operation method mới không được sinh.
- Header, cookie hoặc parameter serialization sai.
- Streaming response bị tạo thành một object thông thường.

OpenAPI Generator README hiện công bố hỗ trợ 3.1 ở mức beta và chưa liệt kê 3.2 trong bảng compatibility. Nếu dùng generator này, không nên kết luận 3.2 được hỗ trợ đầy đủ chỉ vì lệnh validate hoặc generate chạy xong.

Đặc biệt, không dùng tùy chọn bỏ qua validation để ép generator chạy với document có feature chưa hỗ trợ. Một operation không được nhận diện có thể bị bỏ qua trong code đầu ra mà không tạo client method như mong đợi.

Sau khi sinh client, hãy compile project được sinh và chạy test request/response. Sinh code thành công chỉ là một bước trong kiểm tra tương thích.

## 11. Kiểm tra bằng OpenAPI Generator CLI

Có thể dùng CLI để validate tài liệu và sinh client thử nghiệm:

~~~bash
openapi-generator-cli version
openapi-generator-cli validate -i target/openapi.json
~~~

Sinh client thử:

~~~bash
openapi-generator-cli generate \
  -i target/openapi.json \
  -g java \
  -o target/generated-client
~~~

Pin phiên bản CLI hoặc Maven/Gradle plugin. Nếu developer dùng CLI phiên bản mới còn CI dùng plugin phiên bản cũ, kết quả có thể khác nhau.

Không dùng --skip-validate-spec để biến một document không tương thích thành PASS. Nếu cần thử một feature mới, tạo fixture nhỏ, chạy parser và generator đúng phiên bản, sau đó kiểm tra code đầu ra.

Một pipeline nên lưu lại:

- Phiên bản generator.
- Input OpenAPI artifact.
- Log validate.
- Code được sinh.
- Kết quả compile.
- Kết quả test client.

## 12. Kiểm tra JSON Schema và nullable

Khi chuyển từ OAS 3.0 sang 3.1, hãy tạo fixture cho các schema quan trọng.

Ví dụ thuộc tính nullable trong 3.0:

~~~yaml
type: string
nullable: true
~~~

Cách biểu diễn tương ứng trong 3.1:

~~~yaml
type:
  - string
  - "null"
~~~

Kiểm tra ít nhất:

- JSON payload có field bị bỏ qua.
- JSON payload có field mang giá trị null.
- Field required nhưng nullable.
- Field optional nhưng non-null nếu xuất hiện.
- Array chứa item nullable.
- Nested object có thuộc tính nullable.
- oneOf/anyOf với null và discriminator.
- Constraint min/max, pattern và format.

Optional và nullable là hai khái niệm khác nhau. Optional nói rằng property có thể không xuất hiện; nullable nói rằng property có thể xuất hiện với giá trị null. Generator phải ánh xạ hai trường hợp này đúng với ngôn ngữ đích.

Đừng chỉ kiểm tra schema JSON. Hãy sinh client và xác minh kiểu dữ liệu, serializer và deserializer thực tế.

## 13. Kiểm tra UI với fixture feature đại diện

Không nên dùng duy nhất tài liệu API production lớn để điều tra UI. Tạo fixture OpenAPI nhỏ cho từng feature quan trọng:

- Schema nullable.
- oneOf và discriminator.
- External reference.
- Security requirement.
- Multipart request.
- Response có nhiều media type.
- Tag lồng nhau nếu dùng OAS 3.2.
- Operation QUERY nếu dùng OAS 3.2.
- Streaming media type nếu dùng OAS 3.2.

Mỗi fixture nên có một kỳ vọng rõ ràng: UI phải hiển thị operation, schema hoặc security theo cách nào.

Nếu Swagger UI render một document 3.2 nhưng parser downstream không hỗ trợ, ghi rõ kết quả từng tool. Không gộp thành “OAS 3.2 supported” vì hệ thống vẫn có thể thất bại ở bước code generation hoặc contract test.

## 14. Phân biệt document validation với runtime contract testing

Hai nhóm kiểm thử này giải quyết hai câu hỏi khác nhau:

| Kiểm tra | Xác minh điều gì |
|---|---|
| OpenAPI schema validation | Document có tuân thủ cấu trúc và quy tắc OAS không? |
| Parser test | Công cụ có đọc và resolve document đúng không? |
| Swagger UI test | Giao diện có render feature được mô tả không? |
| Code generation test | Client/server stub được sinh đúng và compile không? |
| Runtime API test | Ứng dụng thực tế trả status, header và body gì? |
| Contract test | Request/response runtime có phù hợp với OpenAPI không? |

WebTestClient và MockMvc kiểm tra hành vi Spring Boot. Chúng không tự chứng minh Swagger Parser hay OpenAPI Generator hiểu mọi feature.

Ngược lại, OpenAPI validator không chứng minh controller trả đúng response body. Cần cả test tài liệu và test runtime.

## 15. Kiểm tra OpenAPI JSON được springdoc sinh ra

Tải tài liệu:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o target/openapi.json
~~~

Kiểm tra phiên bản:

~~~bash
jq -r '.openapi' target/openapi.json
~~~

Kiểm tra metadata và path:

~~~bash
jq '{info: .info, paths: (.paths | keys)}' target/openapi.json
~~~

Kiểm tra component:

~~~bash
jq '.components.schemas | keys' target/openapi.json
~~~

Kiểm tra security scheme:

~~~bash
jq '.components.securitySchemes' target/openapi.json
~~~

Không chỉ kiểm tra trường openapi. Cần xác minh các keyword và schema thực sự tương thích với version được khai báo.

Nếu springdoc đang cấu hình OAS 3.1, test nên xác nhận output là 3.1 và không chứa cấu trúc chỉ hợp lệ ở 3.2. Nếu pipeline cần OAS 3.2, hãy dùng một nguồn sinh spec có hỗ trợ 3.2 được xác minh độc lập.

## 16. Ví dụ test version và operation bằng WebTestClient

Có thể kiểm tra phiên bản document do springdoc trả về:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class OpenApiCompatibilityTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void publishesExpectedOpenApiVersion() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.openapi").isEqualTo("3.1.0");
    }

    @Test
    void publishesExpectedOperation() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.paths['/api/orders'].get").exists()
            .jsonPath(
                "$.paths['/api/orders'].get.responses['200']"
            ).exists();
    }
}
~~~

Ví dụ giả định ứng dụng đã chọn OAS 3.1 và endpoint /api/orders tồn tại. Nếu dự án dùng một patch hoặc version string khác theo generator, hãy đặt kỳ vọng theo contract mà dự án đã chọn.

Test nên kiểm tra feature quan trọng chứ không chỉ version string. Một document khai báo 3.1 vẫn có thể có schema sai hoặc component không tương thích với generator.

## 17. Kiểm tra parser trong Java

Nếu dự án sử dụng Swagger Parser, có thể viết test parse document đã xuất:

~~~java
@Test
void parsesGeneratedOpenApiDocument() {
    SwaggerParseResult result =
        new OpenAPIV3Parser().readLocation(
            "target/openapi.json",
            null,
            new ParseOptions()
        );

    assertThat(result.getOpenAPI()).isNotNull();
    assertThat(result.getMessages()).isEmpty();
}
~~~

Tên API và constructor có thể thay đổi theo phiên bản parser. Hãy dùng đúng phiên bản dependency đã pin và đọc warning/message từ parser.

Test trên chỉ có ý nghĩa trong phạm vi OAS mà phiên bản parser hỗ trợ. Nếu parser chưa hỗ trợ 3.2, không dùng test này làm bằng chứng tương thích 3.2. Dùng một parser/validator có hỗ trợ đã được xác nhận hoặc tạm giữ document ở phiên bản mà toolchain hiểu.

Nếu parser trả OpenAPI object nhưng kèm warning, hãy xem warning có liên quan tới feature đang dùng hay không. Không xóa warning hàng loạt để pipeline xanh.

## 18. Kiểm tra code generator bằng client thực

Sau khi generate client:

1. Compile source code được sinh.
2. Kiểm tra model nullable, enum và polymorphism.
3. Kiểm tra operation method và URL.
4. Kiểm tra serialization của query/path/header parameter.
5. Kiểm tra auth interceptor và security scheme.
6. Gửi request tới test server.
7. Deserialize response thật.
8. Kiểm tra lỗi và response status.

Một client có thể compile nhưng vẫn serialize query parameter sai hoặc bỏ header. Vì vậy, compile không phải bước kiểm thử cuối cùng.

Đối với feature mới của OAS 3.2, hãy tạo fixture tối giản để kiểm tra generator có giữ operation, tag, server hoặc media type hay không. Nếu generator bỏ qua feature, cần ghi nhận giới hạn và không phát hành client với hợp đồng thiếu operation.

## 19. Tổ chức compatibility test trong CI

Một pipeline có thể chia thành các bước:

~~~text
Spring Boot test
      |
      v
Generate OpenAPI JSON/YAML
      |
      v
Check declared OAS version
      |
      v
Parser and schema validation
      |
      v
Swagger UI smoke test
      |
      v
Generate client SDK
      |
      v
Compile generated client
      |
      v
Runtime contract tests
      |
      v
Review OpenAPI diff
      |
      v
Publish approved artifact
~~~

Mỗi bước cần dùng phiên bản công cụ được pin. Khi một bước thất bại, log phải chỉ ra tool và version đã chạy.

Ví dụ các lệnh CI:

~~~bash
mvn test

curl -fsS http://localhost:8080/v3/api-docs \
  -o target/openapi.json

jq -e '.openapi == "3.1.0"' target/openapi.json

openapi-generator-cli validate -i target/openapi.json

openapi-generator-cli generate \
  -i target/openapi.json \
  -g java \
  -o target/generated-client

mvn -f target/generated-client/pom.xml test
~~~

Các lệnh cần được điều chỉnh theo cách pipeline khởi động ứng dụng, lưu artifact và quản lý generator. Nếu generator không hỗ trợ version document, pipeline phải fail rõ ràng thay vì bỏ qua validation.

## 20. Lưu compatibility matrix cạnh build configuration

Nên lưu ma trận tương thích trong tài liệu kỹ thuật hoặc build metadata của dự án:

~~~yaml
openapiCompatibility:
  documentVersion: "3.1.0"
  springBoot: "4.1.x"
  springdoc: "3.2.x"
  swaggerUi: "pinned-version"
  parser: "pinned-version"
  generator: "pinned-version"
  contractTest: "pinned-version"
  verifiedFeatures:
    - nullable
    - oneOf
    - discriminator
    - security
    - multipart
~~~

Đây là ví dụ cấu trúc tài liệu nội bộ, không phải property mặc định của springdoc. Thay placeholder bằng phiên bản thực tế của dự án và chỉ liệt kê feature đã được test.

Cần lưu ý compatibility matrix có thể khác nhau giữa các generator. Ví dụ Java client và TypeScript client có thể xử lý nullable hoặc union type khác nhau. Nếu có nhiều client language, tạo test cho từng generator target.

## 21. Nâng cấp OpenAPI 3.0 lên 3.1

Có thể thực hiện theo từng bước:

1. Chốt phiên bản springdoc và Spring Boot tương thích.
2. Kiểm tra parser, UI, generator và contract test tool hiện tại.
3. Bật springdoc.api-docs.version thành OPENAPI_3_1.
4. Xuất document mới.
5. So sánh schema nullable, enum, oneOf, discriminator và $ref.
6. Chạy validator và parser.
7. Render bằng đúng Swagger UI được đóng gói.
8. Sinh client cho mọi ngôn ngữ được hỗ trợ.
9. Compile và chạy contract tests.
10. Review diff và xử lý breaking change trước khi phát hành.

Nếu một generator chưa hiểu một schema 3.1, có thể giữ document ở 3.0 trong giai đoạn chuyển tiếp hoặc nâng generator. Không nên âm thầm chuyển nullable thành required hoặc loại bỏ keyword để làm cho công cụ cũ chạy.

## 22. Đánh giá trước khi nâng lên OpenAPI 3.2

Nâng lên 3.2 cần đánh giá nhiều hơn việc đổi version string:

- springdoc có thể sinh document 3.2 chưa?
- Swagger Core model có biểu diễn đầy đủ cấu trúc cần dùng không?
- Parser và validator có hiểu 3.2 không?
- Swagger UI bundle trong ứng dụng có hỗ trợ không?
- Generator có giữ operation QUERY và additionalOperations không?
- Client runtime có thực hiện được method mới không?
- Contract testing tool có parse được document không?
- Gateway, API portal và tài liệu nội bộ có chấp nhận version mới không?

Nếu một mắt xích chưa hỗ trợ, có thể tiếp tục công bố 3.1 cho pipeline hiện tại và thử nghiệm 3.2 bằng fixture riêng. Không cần sử dụng feature 3.2 chỉ vì đặc tả mới đã phát hành.

Một cách chuyển đổi an toàn là tạo nhánh thử nghiệm, giữ artifact 3.1 làm chuẩn hiện tại và so sánh từng feature mới trong 3.2. Chỉ chuyển khi toàn bộ consumer quan trọng đã được xác minh.

## 23. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Swagger UI mở nhưng generator thất bại | UI và generator có mức hỗ trợ OAS khác nhau |
| Parser đọc được document nhưng có warning | Một số keyword hoặc reference chưa được xử lý đầy đủ |
| springdoc vẫn sinh 3.1 dù muốn 3.2 | Property hiện chỉ hỗ trợ lựa chọn 3.0 và 3.1 |
| Chỉ sửa trường openapi thành 3.2.1 | Header version không biến cấu trúc 3.1 thành 3.2 |
| Generator bỏ operation mới | Generator/parser chưa hiểu method hoặc feature mới |
| Nullable thành non-nullable trong client | Khác biệt JSON Schema 3.0/3.1 hoặc generator mapping |
| Client compile nhưng request sai | Serialization, auth hoặc parameter mapping sai |
| CI pass nhưng UI production lỗi | CI dùng Swagger UI version khác bản đóng gói |
| Local parse được nhưng CI thất bại | Dependency version hoặc plugin version không đồng nhất |
| --skip-validate-spec làm pipeline xanh | Feature không hỗ trợ có thể bị bỏ qua hoặc sinh sai |
| OAS 3.2 document không render hết | UI bundle hoặc parser chưa hỗ trợ feature mới |
| Patch version bị coi như feature mới | Nhầm patch với minor feature set |

## 24. Checklist tương thích trước khi phát hành

- [ ] Đã ghi rõ phiên bản Spring Boot và springdoc.
- [ ] Đã chọn OpenAPI version bằng cấu hình được hỗ trợ.
- [ ] Không tự sửa trường openapi để giả lập version mới.
- [ ] Đã kiểm tra khác biệt Schema Object giữa 3.0 và 3.1.
- [ ] Đã xác minh Swagger UI version được đóng gói.
- [ ] Đã xác minh parser và validator đọc đúng document.
- [ ] Đã chạy code generator với phiên bản được pin.
- [ ] Đã compile client được sinh.
- [ ] Đã test nullable, oneOf, discriminator và security.
- [ ] Đã test các feature mới như QUERY nếu dùng OAS 3.2.
- [ ] Đã kiểm tra response runtime bằng WebTestClient hoặc MockMvc.
- [ ] Đã chạy contract test với document cuối cùng.
- [ ] Không bỏ qua validation để ép tool chạy.
- [ ] Đã review OpenAPI diff và breaking change.
- [ ] Đã lưu compatibility matrix cùng build.
- [ ] CI và môi trường phát hành dùng cùng phiên bản công cụ.

## 25. Nguồn tra cứu

- [OpenAPI Specification – phiên bản mới nhất](https://spec.openapis.org/oas/latest.html)
- [OpenAPI 3.2.1 – đặc tả chính thức](https://spec.openapis.org/oas/v3.2.1.html)
- [OpenAPI – hướng dẫn nâng cấp từ 3.1 lên 3.2](https://learn.openapis.org/upgrading/v3.1-to-v3.2.html)
- [springdoc-openapi – Configuration Properties](https://springdoc.org/properties.html)
- [springdoc-openapi – Compatibility FAQ](https://springdoc.org/faq.html)
- [Swagger UI – Compatibility](https://github.com/swagger-api/swagger-ui)
- [Swagger Parser – OpenAPI 3.1 support](https://github.com/swagger-api/swagger-parser)
- [OpenAPI Generator – Compatibility](https://github.com/OpenAPITools/openapi-generator)
- [OpenAPI Generator – Issue hỗ trợ OAS 3.2](https://github.com/OpenAPITools/openapi-generator/issues/22728)
- [Swagger Parser – Issue hỗ trợ OAS 3.2](https://github.com/swagger-api/swagger-parser/issues/2248)
- [springdoc-openapi – Issue hỗ trợ OAS 3.2](https://github.com/springdoc/springdoc-openapi/issues/3324)

Tương thích OpenAPI là thuộc tính của toàn bộ toolchain. Một tài liệu render được trong Swagger UI vẫn có thể thất bại ở parser, code generator hoặc contract test. Hãy pin phiên bản, lập ma trận feature, kiểm tra schema và generated client, rồi chạy runtime contract tests. Với OpenAPI 3.2, chỉ sử dụng feature mới sau khi xác minh springdoc, parser, UI, generator và các consumer thực tế đều hỗ trợ.
