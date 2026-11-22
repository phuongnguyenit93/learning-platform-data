# Kiểm tra đồng thời đặc tả sinh ra với phản hồi HTTP thực tế

springdoc-openapi tạo đặc tả OpenAPI từ controller, mapping và các annotation của ứng dụng Spring Boot. Đặc tả mô tả client cần gửi request như thế nào và có thể nhận response nào. Tuy nhiên, một tài liệu được sinh thành công chưa chứng minh ứng dụng đang trả đúng dữ liệu như tài liệu đã công bố. Controller có thể khai báo response **201** nhưng lúc chạy lại trả **200**; OpenAPI có thể ghi **application/json** trong khi endpoint thực tế trả **application/problem+json**; hoặc schema có thể thiếu field mà response đang gửi.

Vì vậy, cần kiểm tra hai phía trong cùng một quy trình:

- **Đặc tả được sinh ra** tại endpoint OpenAPI, thường là **/v3/api-docs**.
- **Phản hồi HTTP thực tế** khi gửi request đến endpoint nghiệp vụ.

Mục tiêu là xác nhận đường dẫn, method, request body, mã trạng thái, header, media type và cấu trúc dữ liệu thực tế phù hợp với hợp đồng OpenAPI. Đây là một phần quan trọng của kiểm thử hợp đồng API trong module **SPRINGDOC_OPENAPI**, bên cạnh việc mô tả request, response, schema, bảo mật và nhóm tài liệu.

## 1. Vì sao phải đối chiếu đặc tả với HTTP thực tế?

Springdoc phân tích cấu hình Spring MVC hoặc WebFlux và các annotation để xây dựng tài liệu. Nó không gọi mọi endpoint với mọi dữ liệu để quan sát tất cả kết quả có thể xảy ra. Đặc tả có thể được sinh đúng theo metadata trong mã nguồn nhưng vẫn lệch so với hành vi runtime do:

- Logic nghiệp vụ trả về mã trạng thái hoặc kiểu response khác dự kiến.
- Jackson đổi tên field, bỏ field null, thay đổi enum hoặc định dạng ngày giờ.
- Validation tạo response lỗi chưa được mô tả đầy đủ.
- Cấu hình message converter hoặc content negotiation làm thay đổi **Content-Type**.
- Spring Security, filter, interceptor hoặc gateway trả lỗi trước khi request đến controller.
- Cấu hình context path, reverse proxy hoặc nhóm tài liệu làm URL công khai khác URL trong tài liệu.
- Một nhánh xử lý mới được thêm vào nhưng annotation **@ApiResponse** chưa được cập nhật.

Ví dụ, controller được mô tả là trả **201 Created**, nhưng một nhánh nghiệp vụ trả **409 Conflict** khi đơn hàng đã tồn tại. Nếu OpenAPI không có response **409**, client tạo từ đặc tả có thể không xử lý được trường hợp thực tế.

Một trường hợp khác là API trả lỗi bằng **ProblemDetail** với **application/problem+json**, trong khi tài liệu chỉ liệt kê **application/json**. Cả hai đều là JSON, nhưng media type và cấu trúc hợp đồng khác nhau.

## 2. Những thành phần cần so sánh

Đối chiếu không chỉ là kiểm tra response có phải JSON hay không. Cần xem các thành phần của operation và response:

| Thành phần | Trong OpenAPI | Trong HTTP thực tế |
| --- | --- | --- |
| Đường dẫn và method | **paths**, **get**, **post**, **put**, **delete**... | URL và method đã gửi |
| Path/query/header parameter | **parameters**, **in**, **required**, **schema** | Giá trị URL, query string và request header |
| Request body | **requestBody.content**, **required**, schema | Body thực gửi, **Content-Type** |
| Mã trạng thái | Các key trong **responses**, ví dụ **200**, **201**, **400**, **409** | Status code nhận được |
| Media type | **responses.content** | Response header **Content-Type** |
| Schema | **$ref**, **properties**, **required**, **format**, **enum** | JSON hoặc dữ liệu thực tế trong body |
| Header response | **responses.headers** | **Location**, **ETag**, **Content-Disposition**, **Cache-Control**... |
| Bảo mật | **security**, **securitySchemes** | Kết quả khi gửi token hợp lệ, thiếu token hoặc token không đủ quyền |
| Nội dung lỗi | Response cho **4xx** và **5xx** | Body lỗi do validation, security, exception handler hoặc gateway trả về |

Không phải response nào cũng có body. Ví dụ **204 No Content** thường không có **Content-Type** hoặc schema body. Với response này, cần kiểm tra status và việc body thực sự rỗng thay vì yêu cầu một schema JSON.

## 3. Quy trình kiểm tra từ tài liệu đến request thực tế

### Bước 1: Lấy đặc tả OpenAPI đang được ứng dụng phục vụ

Khởi động ứng dụng với đúng profile và cấu hình cần kiểm tra. Với cấu hình mặc định của springdoc, lấy JSON bằng:

~~~powershell
curl.exe -sS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Nếu ứng dụng dùng context path, reverse proxy hoặc đã đổi **springdoc.api-docs.path**, hãy dùng URL mà client thực sự truy cập. Khi có nhiều nhóm tài liệu, lấy đúng endpoint của nhóm cần kiểm tra.

Kiểm tra nhanh version OpenAPI và các path:

~~~powershell
jq -r '.openapi, (.paths | keys[])' openapi.json
~~~

Ví dụ xem request body và các response được mô tả cho thao tác tạo đơn hàng:

~~~powershell
jq '.paths["/api/orders"].post | {
  requestBody: .requestBody,
  responses: .responses
}' openapi.json
~~~

Các lệnh trên chỉ đọc tài liệu được sinh ra. Chúng không chứng minh endpoint nghiệp vụ đã trả đúng dữ liệu.

### Bước 2: Gửi request có dữ liệu xác định

Gửi request đến chính endpoint nghiệp vụ và lưu cả status, header lẫn body. Dùng **-i** để xem header cùng response:

~~~powershell
curl.exe -i -X POST http://localhost:8080/api/orders -H "Content-Type: application/json" -H "Accept: application/json" -d '{"customerCode":"CUS-100","quantity":2}'
~~~

Ghi nhận ít nhất:

- URL và HTTP method đã gọi.
- Request header và request body.
- HTTP status code.
- Response header, đặc biệt **Content-Type** và các header được công bố trong hợp đồng.
- Response body nguyên bản.

Nên dùng bộ dữ liệu xác định để có thể lặp lại kiểm thử. Không dùng một ví dụ thành công duy nhất để kết luận mọi nhánh lỗi cũng đúng hợp đồng.

### Bước 3: Đối chiếu operation và response

Với request tạo đơn hàng ở trên, kiểm tra operation **POST /api/orders** trong OpenAPI:

~~~json
{
  "requestBody": {
    "required": true,
    "content": {
      "application/json": {
        "schema": {
          "$ref": "#/components/schemas/CreateOrderRequest"
        }
      }
    }
  },
  "responses": {
    "201": {
      "description": "Đơn hàng đã được tạo",
      "content": {
        "application/json": {
          "schema": {
            "$ref": "#/components/schemas/OrderView"
          }
        }
      }
    }
  }
}
~~~

Nếu HTTP thực tế trả **201** và **Content-Type: application/json**, response đó phải được mô tả trong **responses["201"].content["application/json"]**. Sau đó kiểm tra schema **OrderView** trong **components.schemas** có chứa các field thực tế như **id**, **customerCode**, **quantity** và **status**.

Nếu status hoặc media type thực tế không có trong đặc tả, đó là dấu hiệu hợp đồng đang thiếu hoặc mô tả sai. Cần xác định hành vi runtime là chủ đích hay lỗi triển khai trước khi sửa annotation hoặc logic controller.

### Bước 4: Lặp lại với các nhánh kết quả khác

Kiểm tra tối thiểu các tình huống có ý nghĩa với endpoint:

| Tình huống | Hành vi HTTP cần xác minh | Đặc tả cần có |
| --- | --- | --- |
| Request hợp lệ | **200 OK** hoặc **201 Created** theo thiết kế | Response thành công và schema |
| Thiếu field bắt buộc hoặc sai định dạng | Thường là **400 Bad Request** | Response validation error |
| Không xác thực | **401 Unauthorized** | Response lỗi xác thực |
| Không đủ quyền | **403 Forbidden** | Response lỗi phân quyền |
| Tài nguyên không tồn tại | **404 Not Found** | Response lỗi không tìm thấy |
| Xung đột nghiệp vụ | **409 Conflict** nếu được thiết kế | Response lỗi xung đột |
| Không có nội dung | **204 No Content** | Response không có body |
| Lỗi ngoài dự kiến | **500 Internal Server Error** hoặc mã đã chuẩn hóa | Response lỗi phù hợp với chính sách API |

Các mã trạng thái trên là ví dụ phổ biến, không phải quy tắc bắt buộc cho mọi API. Hãy đối chiếu với quyết định thiết kế của ứng dụng và bảo đảm mỗi nhánh có thể xảy ra đều được mô tả rõ.

## 4. Kiểm tra tự động bằng MockMvc

**MockMvc** cho phép gọi request qua Spring MVC trong kiểm thử tích hợp mà không cần mở cổng HTTP thật. Có thể dùng nó để lấy **/v3/api-docs**, gọi endpoint nghiệp vụ, sau đó so sánh status và media type thực tế với operation trong đặc tả.

Ví dụ sau giả định ứng dụng có **POST /api/orders**, nhận **CreateOrderRequest** dạng JSON và trả **OrderView** với **201 Created**. Các lớp DTO và controller là mã của ứng dụng; ví dụ tập trung vào phần kiểm thử đối chiếu.

~~~java
import java.util.Iterator;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiRuntimeContractTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void createOrderResponseMatchesOpenApi() throws Exception {
        // Lấy đặc tả từ chính ứng dụng đang được kiểm thử.
        MvcResult specResult = mockMvc.perform(
                get("/v3/api-docs").accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andReturn();

        JsonNode openApi = objectMapper.readTree(
            specResult.getResponse().getContentAsString()
        );

        JsonNode operation = openApi
            .path("paths")
            .path("/api/orders")
            .path("post");

        // Kiểm tra request body mà đặc tả công bố.
        JsonNode requestContent = operation
            .path("requestBody")
            .path("content")
            .path("application/json");

        assertThat(requestContent.isMissingNode()).isFalse();
        assertThat(operation.path("requestBody").path("required").asBoolean())
            .isTrue();

        // Gọi endpoint nghiệp vụ bằng dữ liệu hợp lệ.
        String requestJson = """
            {
              "customerCode": "CUS-100",
              "quantity": 2
            }
            """;

        MvcResult actualResult = mockMvc.perform(
                post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content(requestJson)
            )
            .andReturn();

        int actualStatus = actualResult.getResponse().getStatus();
        String statusKey = Integer.toString(actualStatus);

        // Status thực tế phải được mô tả trong responses.
        JsonNode responses = operation.path("responses");
        JsonNode responseDefinition = responses.path(statusKey);
        if (responseDefinition.isMissingNode()) {
            responseDefinition = responses.path("default");
        }

        assertThat(responseDefinition.isMissingNode()).isFalse();

        // Media type thực tế phải xuất hiện trong content của status đó.
        String actualContentType = actualResult.getResponse().getContentType();
        assertThat(actualContentType).isNotBlank();

        MediaType parsedType = MediaType.parseMediaType(actualContentType);
        String mediaTypeKey = parsedType.getType() + "/" + parsedType.getSubtype();

        JsonNode mediaDefinition = responseDefinition
            .path("content")
            .path(mediaTypeKey);

        assertThat(mediaDefinition.isMissingNode()).isFalse();

        // Đối chiếu các field thực tế với schema response được tham chiếu.
        JsonNode schemaDefinition = mediaDefinition.path("schema");
        String schemaRef = schemaDefinition.path("$ref").asText(null);
        JsonNode responseSchema = schemaRef == null
            ? schemaDefinition
            : openApi.at(schemaRef.substring(1));

        assertThat(responseSchema.isMissingNode()).isFalse();

        JsonNode actualBody = objectMapper.readTree(
            actualResult.getResponse().getContentAsString()
        );
        JsonNode declaredProperties = responseSchema.path("properties");

        Iterator<String> fieldNames = actualBody.fieldNames();
        while (fieldNames.hasNext()) {
            String fieldName = fieldNames.next();
            assertThat(declaredProperties.has(fieldName))
                .as("Field '%s' phải được mô tả trong OpenAPI", fieldName)
                .isTrue();
        }
    }
}
~~~

Ví dụ dùng AssertJ, Jackson, JUnit 5 và các lớp kiểm thử Spring. Nếu dự án dùng kiểu response khác hoặc schema inline, điều chỉnh phần lấy schema theo tài liệu thực tế. Bài kiểm thử minh họa ba lớp đối chiếu quan trọng: request media type được công bố, status thực tế có trong **responses**, và response media type cùng field thực tế khớp schema được tham chiếu.

Kiểm tra field trong ví dụ là kiểm tra một chiều: mọi field xuất hiện trong response mẫu phải được schema cho phép. Với hợp đồng chặt hơn, hãy kiểm tra thêm field bắt buộc, kiểu dữ liệu, **format**, **enum**, giá trị null, cấu trúc object lồng nhau và các ràng buộc của schema.

Nếu endpoint có thể trả **204 No Content**, không đọc body bằng **ObjectMapper** trong nhánh đó. Thay vào đó, xác nhận status **204**, body rỗng và response trong OpenAPI không khai báo nội dung.

## 5. Khi cần kiểm tra qua HTTP server thật

**MockMvc** kiểm tra luồng xử lý Spring MVC nhưng không đi qua socket HTTP, reverse proxy, ingress hoặc API gateway. Khi các lớp này có thể thay đổi URL, header hay response, hãy bổ sung kiểm thử chạy ứng dụng trên cổng ngẫu nhiên bằng **@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)** và gọi bằng **TestRestTemplate**, **WebTestClient** hoặc HTTP client của dự án.

Ví dụ ý tưởng với **TestRestTemplate**:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LiveHttpContractTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void endpointUsesDocumentedStatusAndMediaType() {
        ResponseEntity<String> response = http.postForEntity(
            "/api/orders",
            new CreateOrderRequest("CUS-100", 2),
            String.class
        );

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        MediaType actualType = response.getHeaders().getContentType();
        assertThat(actualType).isNotNull();
        assertThat(actualType.isCompatibleWith(MediaType.APPLICATION_JSON)).isTrue();
    }
}
~~~

Đây là ví dụ kiểm tra response qua HTTP server nhúng. Để đối chiếu đầy đủ với OpenAPI, có thể lấy thêm **/v3/api-docs** bằng cùng HTTP client rồi áp dụng các assertion về status, media type và schema như phần **MockMvc**.

Với môi trường staging hoặc production, có thể chạy kiểm tra từ bên ngoài bằng **curl.exe** hoặc HTTP client trong pipeline. Khi đó cần dùng URL công khai và thông tin xác thực phù hợp, đồng thời tránh ghi token hoặc dữ liệu nhạy cảm vào log kiểm thử.

## 6. Đối chiếu schema với JSON được serialize

Kiểu Java không phải lúc nào cũng trùng với JSON thực tế. Springdoc thường suy luận schema từ DTO và annotation, còn Jackson quyết định JSON được ghi ra response. Những cấu hình sau có thể làm hai phía khác nhau:

- **@JsonProperty** đổi tên field trong JSON.
- **@JsonIgnore** loại field khỏi JSON.
- **@JsonInclude** có thể bỏ field null hoặc field có giá trị mặc định.
- Enum có thể được serialize thành tên, mã hoặc giá trị tùy cấu hình.
- **@JsonFormat** và cấu hình ObjectMapper ảnh hưởng định dạng ngày giờ.
- Naming strategy có thể đổi **customerCode** thành **customer_code**.
- Custom serializer có thể ghi kiểu dữ liệu khác với kiểu Java ban đầu.

Khi kiểm tra schema, dùng tên field trong JSON đã serialize để so sánh với **properties** của schema, không chỉ nhìn tên thuộc tính trong class Java. Với ngày giờ, xác minh cả **type**, **format**, timezone và ví dụ thực tế. Với enum, so sánh tập giá trị runtime có thể trả với danh sách **enum** được mô tả.

Ví dụ nếu response JSON thực tế là:

~~~json
{
  "order_id": "ORD-1001",
  "customer_code": "CUS-100",
  "status": "CREATED"
}
~~~

thì schema OpenAPI cần mô tả các tên **order_id**, **customer_code**, **status** tương ứng. Schema vẫn ghi **id** hoặc **customerCode** sẽ khiến client sinh từ OpenAPI hiểu sai cấu trúc dữ liệu.

## 7. Kiểm tra header và content negotiation

Response hợp đồng có thể bao gồm header ngoài **Content-Type**. Ví dụ:

- **Location** cho biết URL của tài nguyên vừa được tạo.
- **ETag** hỗ trợ cache và kiểm soát cập nhật có điều kiện.
- **Content-Disposition** mô tả cách tải tệp và tên tệp.
- **Cache-Control** quy định hành vi lưu cache.
- **WWW-Authenticate** cung cấp thông tin về cơ chế xác thực khi trả **401**.

Nếu client cần sử dụng một header, mô tả header đó trong response OpenAPI và kiểm tra giá trị runtime. Không nên chỉ kiểm tra header có tồn tại; hãy kiểm tra nội dung có đúng định dạng và ngữ nghĩa mà client cần.

Với content negotiation, gửi các giá trị **Accept** khác nhau để xác minh endpoint hỗ trợ đúng media type đã công bố. Ví dụ, nếu API hỗ trợ JSON và XML, thử cả hai và xác nhận response **Content-Type** tương ứng. Nếu gửi một **Accept** không được hỗ trợ, kiểm tra hành vi **406 Not Acceptable** và quyết định xem response này có cần xuất hiện trong hợp đồng hay không.

Đối với request, thử gửi **Content-Type** không được hỗ trợ để kiểm tra **415 Unsupported Media Type** nếu endpoint có giới hạn **consumes**. Đặc tả phải thể hiện các media type mà endpoint chấp nhận, không liệt kê những định dạng controller thực tế không xử lý được.

## 8. Kiểm tra validation, bảo mật và lỗi

Một hợp đồng chỉ mô tả response thành công là chưa đủ nếu API có nhiều nhánh lỗi có thể dự đoán. Kiểm tra riêng:

**Validation.** Gửi thiếu field bắt buộc, chuỗi vượt giới hạn, giá trị số ngoài khoảng hoặc enum không hợp lệ. Xác minh status, media type và schema lỗi. Nếu dùng **ProblemDetail**, kiểm tra các thuộc tính như **type**, **title**, **status**, **detail**, **instance** và các extension riêng của ứng dụng.

**Authentication.** Gọi endpoint bảo vệ mà không có token. Xác minh status **401**, header **WWW-Authenticate** nếu được dùng và response body theo hợp đồng.

**Authorization.** Gửi token hợp lệ nhưng thiếu quyền. Xác minh status **403** và nội dung lỗi. Không gộp **401** và **403** nếu client cần phân biệt hai tình huống.

**Exception nghiệp vụ.** Kích hoạt các trường hợp như tài nguyên không tồn tại, xung đột dữ liệu hoặc trạng thái không cho phép. Xác nhận **@ControllerAdvice** hoặc exception handler trả đúng status và body đã mô tả.

**Lỗi hạ tầng.** Khi gateway hoặc reverse proxy có thể trả lỗi riêng, kiểm tra response ở ranh giới mà client thực sự gọi. Các response do gateway tạo có thể không đi qua controller hoặc springdoc, nên cần được quản lý trong hợp đồng phân phối tương ứng.

## 9. Tích hợp kiểm tra vào CI

Nên tự động lấy đặc tả từ ứng dụng được khởi động bằng cấu hình kiểm thử, thực hiện các request đại diện và xác minh kết quả. Một pipeline cơ bản có thể đi theo trình tự:

~~~text
Khởi động ứng dụng với profile kiểm thử
              |
              v
Tải /v3/api-docs và xác nhận tài liệu hợp lệ
              |
              v
Kiểm tra paths, methods, requestBody và responses
              |
              v
Gửi request thành công và request lỗi đại diện
              |
              v
So sánh status, headers, media type và body với OpenAPI
              |
              v
So sánh đặc tả với bản đã phát hành (nếu có)
              |
              v
        Báo cáo kết quả CI
~~~

Trong CI, có thể chia kiểm tra thành các nhóm:

1. **Kiểm tra cấu trúc đặc tả:** **/v3/api-docs** trả thành công, JSON hợp lệ, có version, paths và schemas cần thiết.
2. **Kiểm tra mapping:** method, path, parameter, request body và media type trùng với endpoint được triển khai.
3. **Kiểm tra response:** mọi status và media type quan trọng đều được mô tả; schema bao phủ dữ liệu thực tế.
4. **Kiểm tra nhánh lỗi:** validation, authentication, authorization và lỗi nghiệp vụ có status cùng body ổn định.
5. **Kiểm tra thay đổi hợp đồng:** so sánh OpenAPI hiện tại với bản đã phát hành để phát hiện thay đổi có thể phá vỡ client.

Các công cụ so sánh OpenAPI có thể phát hiện thay đổi trong hai bản đặc tả, nhưng tự chúng không chứng minh runtime trả đúng hợp đồng. Ngược lại, kiểm thử một số HTTP response không chứng minh mọi operation và schema trong tài liệu đều chính xác. Kết hợp kiểm tra đặc tả, kiểm thử HTTP và so sánh phiên bản sẽ tạo phạm vi kiểm soát tốt hơn.

## 10. Checklist khi hoàn thành một lần đối chiếu

- [ ] Đã lấy OpenAPI từ đúng ứng dụng, profile, context path và document group.
- [ ] URL và HTTP method trong tài liệu khớp endpoint thực tế.
- [ ] Parameter, request body, **Content-Type** và **Accept** khớp cách endpoint xử lý.
- [ ] Mỗi status thực tế quan trọng đều có response tương ứng trong OpenAPI.
- [ ] Response **Content-Type** được khai báo trong **responses.content**.
- [ ] JSON thực tế khớp tên field, kiểu dữ liệu, enum và format trong schema.
- [ ] Header mà client cần sử dụng được mô tả và có giá trị đúng.
- [ ] Response lỗi validation, authentication, authorization và nghiệp vụ đã được kiểm tra.
- [ ] Response không có body như **204** được kiểm tra đúng cách.
- [ ] Kiểm thử chạy trong CI và thất bại khi phát hiện sai lệch hợp đồng.

## 11. Kết luận

Đặc tả OpenAPI là hợp đồng được công bố cho client, còn phản hồi HTTP là hành vi mà client thực sự nhận được. springdoc giúp sinh hợp đồng từ ứng dụng Spring Boot; kiểm thử tích hợp và kiểm thử HTTP xác nhận hợp đồng đó phản ánh đúng hành vi runtime. Hãy đối chiếu cả request lẫn response, bao gồm status, header, media type, schema và các nhánh lỗi. Khi những kiểm tra này chạy tự động trong CI, thay đổi controller hoặc cấu hình serialization sẽ sớm bộc lộ sai lệch trước khi tài liệu và API được phân phối cho người dùng.
