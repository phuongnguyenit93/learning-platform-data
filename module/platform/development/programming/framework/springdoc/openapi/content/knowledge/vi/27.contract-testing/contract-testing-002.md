# Đọc đặc tả bằng parser tương thích phiên bản

Một file OpenAPI có thể là JSON hoặc YAML, nhưng chỉ đọc được cú pháp chưa có nghĩa công cụ hiểu đúng hợp đồng. Parser cần nhận diện đúng phiên bản được khai báo trong trường `openapi`, hiểu các cấu trúc của phiên bản đó và xử lý `$ref`, schema cùng các thành phần liên quan theo đúng quy tắc.

Với Springdoc, đặc tả thường được lấy từ `/v3/api-docs` hoặc `/v3/api-docs.yaml`. Có thể dùng parser trong Java test hoặc pipeline để đọc document thành object model, thu thập cảnh báo/lỗi và kiểm tra các thành phần cần thiết trước khi chạy contract checks tiếp theo.

## 1. Xác định phiên bản trước khi chọn parser

Trường `openapi` ở cấp cao nhất của document cho biết phiên bản OpenAPI:

```yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths: {}
```

Không nhầm trường này với `info.version`. `openapi` xác định phiên bản của ngôn ngữ đặc tả; `info.version` là phiên bản API do nhóm phát triển đặt tên.

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Orders API",
    "version": "2026.11"
  }
}
```

Trong ví dụ, document dùng OpenAPI 3.1.0 còn API được công bố có phiên bản `2026.11`. Parser phải hỗ trợ OpenAPI 3.1; không chọn parser chỉ dựa trên chuỗi `info.version`.

## 2. Chọn parser theo phiên bản OpenAPI

Các parser có thể hỗ trợ các phiên bản đặc tả khác nhau. Một thư viện có thể đọc được OpenAPI 3.0 nhưng chưa hiểu đầy đủ JSON Schema 2020-12 trong OpenAPI 3.1, hoặc chưa hỗ trợ các cấu trúc mới của OpenAPI 3.2.

Tại thời điểm biên soạn, tài liệu chính thức của Swagger Parser nêu các mốc chính sau:

| Parser | Phạm vi được tài liệu công bố | Lưu ý |
|---|---|---|
| Swagger Parser 1.x | Swagger/OpenAPI 2.0 theo nhánh 1.x | Dòng API cũ; repository chính hướng người dùng 1.x sang nhánh `v1` |
| Swagger Parser 2.1.x | OpenAPI 3.0 và 3.1 | Hỗ trợ OpenAPI 3.1 bắt đầu từ 2.1.0; cùng dòng artifact 2.x xử lý cả hai phiên bản |
| Swagger Parser 2.1.48 | Bản 2.1.x được README/Maven Central liệt kê khi kiểm tra | Có thể dùng làm ví dụ dependency; vẫn kiểm tra bản vá mới hơn trước khi khóa phiên bản |
| openapi-processor/openapi-parser | OpenAPI 3.0, 3.1 và 3.2 | Dự án công bố parser và JSON Schema validator cho ba phiên bản; yêu cầu JDK 17+ |

Swagger Parser 2.1.x có hỗ trợ OpenAPI 3.1 từ 2.1.0, bao gồm parsing, validation và xử lý reference. Tuy nhiên, tài liệu của dòng này hiện công bố hỗ trợ đến 3.1; không suy luận rằng parser 2.1.48 tự động hỗ trợ mọi cấu trúc OpenAPI 3.2. Nếu document khai báo 3.2, hãy chọn một parser có công bố rõ hỗ trợ 3.2 và kiểm tra các tính năng thực tế mà document dùng.

`openapi-processor/openapi-parser` là một lựa chọn Java được dự án công bố hỗ trợ OpenAPI 3.2, 3.1 và 3.0. Tài liệu dự án nêu parser dùng JSON Schema Draft 4 để validate schema OpenAPI 3.0 và JSON Schema Draft 2020-12 cho OpenAPI 3.1/3.2. Đây là lựa chọn cần đánh giá riêng về API Java, dependency, JDK và tích hợp CI trước khi đưa vào dự án.

Các mốc hỗ trợ ở trên là thông tin của dự án parser, không phải cam kết rằng mọi phiên bản Swagger UI, Springdoc, client generator hoặc validator khác cũng hỗ trợ cùng một tập tính năng. Luôn kiểm tra release notes của đúng phiên bản được khóa trong build.

## 3. Swagger Parser 2.x và OpenAPI 3.1

Swagger Parser 2.x dùng các artifact cùng dòng để xử lý OpenAPI 3.0 và 3.1. Hỗ trợ OpenAPI 3.1 được thêm từ phiên bản 2.1.0. OpenAPI 3.1 căn chỉnh Schema Object với JSON Schema Draft 2020-12, vì vậy parser cần hiểu các khác biệt như:

- Schema type có thể là một danh sách gồm `string` và `null`.
- Các keyword JSON Schema 2020-12 như `$dynamicRef`, `$dynamicAnchor`, `unevaluatedProperties` hoặc `prefixItems` có thể xuất hiện.
- `jsonSchemaDialect` có thể xác định dialect schema của document.
- OpenAPI 3.1 có thể sử dụng một số cấu trúc không có trong 3.0, ví dụ `webhooks`.

Parser chỉ hỗ trợ OpenAPI 3.0 có thể từ chối document 3.1 hoặc đọc được một phần nhưng không giữ đúng semantics của schema. Không được sửa trường `openapi: 3.1.0` thành `3.0.3` chỉ để vượt qua lỗi parser; việc đó không chuyển đổi các keyword 3.1 thành cấu trúc hợp lệ của 3.0.

Một chi tiết API dễ nhầm: Swagger Parser README hướng dẫn dùng `OpenAPIParser` để đọc document và nhận diện phiên bản. `OpenAPIV3Parser` là convenience API chuyên xử lý OpenAPI 3.0 theo README; không nên chọn API đó cho luồng cần tự nhận diện hoặc đọc OpenAPI 3.1. Hãy theo API và ví dụ của đúng release parser.

## 4. Thêm Swagger Parser vào dự án Java

Nếu chỉ cần đọc đặc tả trong test hoặc bước CI, có thể đặt dependency ở test scope để không đưa parser vào runtime của service.

Maven:

```xml
<dependency>
    <groupId>io.swagger.parser.v3</groupId>
    <artifactId>swagger-parser</artifactId>
    <version>2.1.48</version>
    <scope>test</scope>
</dependency>
```

Gradle Kotlin DSL:

```kotlin
dependencies {
    testImplementation("io.swagger.parser.v3:swagger-parser:2.1.48")
}
```

Phiên bản `2.1.48` là ví dụ đã được kiểm tra trong tài liệu Swagger Parser khi biên soạn. Khi nâng cấp, hãy khóa một phiên bản phát hành cụ thể và kiểm tra dependency tree. Springdoc cũng sử dụng các thư viện thuộc hệ Swagger; nếu ứng dụng có nhiều phiên bản `swagger-core`, `swagger-models` hoặc Jackson trên classpath, xung đột có thể gây lỗi runtime hoặc làm model parse khác kỳ vọng.

Kiểm tra dependency tree với Maven:

```bash
mvn dependency:tree -Dincludes=io.swagger.parser.v3,io.swagger.core.v3
```

Không tự ý ép tất cả dependency Swagger Core sang phiên bản mới chỉ để khớp parser. Hãy kiểm tra compatibility matrix của Springdoc và Swagger Parser, sau đó dùng dependency management nhất quán. Nếu parser chỉ phục vụ contract test, test scope hoặc một module CI riêng giúp giảm ảnh hưởng đến ứng dụng chạy thật.

## 5. Đọc OpenAPI JSON/YAML từ file hoặc URL

`OpenAPIParser` có thể đọc document từ vị trí file hoặc URL và trả về `SwaggerParseResult`. Kết quả chứa object model cùng các thông báo validation.

```java
import io.swagger.parser.OpenAPIParser;
import io.swagger.v3.parser.core.models.ParseOptions;
import io.swagger.v3.parser.core.models.SwaggerParseResult;
import io.swagger.v3.oas.models.OpenAPI;

public final class OpenApiReader {

    private OpenApiReader() {
    }

    public static OpenAPI read(String location) {
        ParseOptions options = new ParseOptions();
        options.setResolve(true);

        SwaggerParseResult result = new OpenAPIParser()
            .readLocation(location, null, options);

        if (result == null || result.getOpenAPI() == null) {
            String diagnostics = result == null || result.getMessages() == null
                ? "Parser không trả về OpenAPI model hoặc diagnostics."
                : String.join("\n", result.getMessages());
            throw new IllegalStateException("Không đọc được OpenAPI document:\n" + diagnostics);
        }

        if (result.getMessages() != null && !result.getMessages().isEmpty()) {
            result.getMessages().forEach(message ->
                System.err.println("OpenAPI parser: " + message)
            );
        }

        return result.getOpenAPI();
    }
}
```

Gọi với file YAML:

```java
OpenAPI openAPI = OpenApiReader.read("src/test/resources/openapi.yaml");
```

Hoặc với endpoint Springdoc đang chạy:

```java
OpenAPI openAPI = OpenApiReader.read("http://localhost:8080/v3/api-docs");
```

Parser nhận JSON hoặc YAML và dùng trường phiên bản trong document để chọn logic phù hợp. Khi đọc từ URL, tiến trình test/CI phải truy cập được host và port đó; nếu endpoint yêu cầu xác thực, cần cung cấp credentials theo API của parser thay vì làm endpoint public chỉ để test.

## 6. Kiểm tra `SwaggerParseResult` thay vì chỉ lấy model

Không nên chỉ gọi `getOpenAPI()` rồi coi parse thành công là document hợp lệ. Hãy kiểm tra cả hai phần:

- `getOpenAPI()` phải trả về model để các bước sau có thể đọc.
- `getMessages()` chứa cảnh báo hoặc lỗi mà parser phát hiện trong lúc parse/validate.

Ví dụ kiểm tra thủ công:

```java
SwaggerParseResult result = new OpenAPIParser()
    .readLocation("src/test/resources/openapi.yaml", null, null);

if (result == null) {
    throw new IllegalStateException("Không nhận được kết quả từ parser");
}

if (result.getMessages() != null) {
    result.getMessages().forEach(System.err::println);
}

if (result.getOpenAPI() == null) {
    throw new IllegalStateException("Không tạo được OpenAPI model");
}

String version = result.getOpenAPI().getOpenapi();
System.out.println("OpenAPI version: " + version);
```

`getMessages()` có thể chứa warning lẫn error dưới dạng thông báo. Một model không null không chứng minh mọi quy tắc đều đạt. Ngược lại, không phải mọi warning đều có cùng mức độ nghiêm trọng. CI nên định nghĩa policy rõ: ghi nhận mọi message, fail khi parse không tạo được model, và fail hoặc yêu cầu review khi xuất hiện diagnostics theo mức độ mà dự án quy định.

Nếu cần phân loại severity máy đọc được, không nên tự đoán bằng cách tìm từ như `warning` hoặc `error` trong chuỗi thông báo. Hãy dùng validator có cấu trúc kết quả rõ hơn hoặc quy tắc wrapper được kiểm thử với đúng phiên bản parser.

## 7. Đọc đặc tả sinh ra bởi Springdoc trong integration test

Một cách thực tế là khởi động Spring Boot trên cổng ngẫu nhiên, gọi endpoint API Docs và đưa URL cho parser. Ví dụ với Spring Boot 3 và JUnit 5:

```java
import io.swagger.parser.OpenAPIParser;
import io.swagger.v3.parser.core.models.SwaggerParseResult;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OpenApiDocumentParsingTest {

    @Value("${local.server.port}")
    int port;

    @Test
    void generatedOpenApiDocumentCanBeRead() {
        String location = "http://localhost:" + port + "/v3/api-docs";

        SwaggerParseResult result = new OpenAPIParser()
            .readLocation(location, null, null);

        assertNotNull(result, "Parser phải trả kết quả");
        assertNotNull(
            result.getOpenAPI(),
            () -> result.getMessages() == null
                ? "Không tạo được OpenAPI model"
                : String.join("\n", result.getMessages())
        );

        assertEquals("3.1.0", result.getOpenAPI().getOpenapi());
        assertTrue(
            result.getMessages() == null || result.getMessages().isEmpty(),
            () -> String.join("\n", result.getMessages())
        );
    }
}
```

Assertion `3.1.0` chỉ phù hợp khi ứng dụng được cấu hình sinh OpenAPI 3.1. Nếu ứng dụng xuất 3.0.x, thay expected version bằng giá trị mà dự án chọn. Assertion không có diagnostics là policy strict cho ví dụ; nếu parser có warning đã được đánh giá và chấp nhận, hãy tách warning khỏi lỗi bằng quy trình kiểm tra của dự án thay vì bỏ qua toàn bộ message.

Nếu endpoint tài liệu được bảo vệ, truyền thông tin xác thực qua `AuthorizationValue` và không ghi token vào log. Nếu test đang dùng MockMvc/WebTestClient và đã có body JSON trong bộ nhớ, có thể dùng API đọc nội dung của đúng phiên bản parser hoặc ghi artifact tạm trong test; không cần triển khai một endpoint public mới chỉ để parser đọc được document.

## 8. Phân biệt parse, validate và resolve `$ref`

Các bước này liên quan nhưng không đồng nghĩa:

| Công việc | Mục đích | Kết quả cần quan sát |
|---|---|---|
| Parse | Đọc JSON/YAML và tạo object model | Có `OpenAPI` model hoặc diagnostics giải thích lỗi |
| Validate | Kiểm tra cấu trúc và quy tắc OpenAPI/JSON Schema mà parser hỗ trợ | Diagnostics; không chỉ dựa vào model được tạo |
| Resolve | Tìm external/relative reference và thay chúng bằng local reference đến component | Các `$ref` được chuyển đến component trong model đã resolve |
| Resolve fully | Thay cả local reference bằng nội dung được tham chiếu | Model inline nhiều hơn, có thể lặp nội dung |
| Flatten | Chuyển một số schema inline thành component và thay bằng `$ref` | Components schema được bổ sung và operation trỏ đến chúng |

Parse thành công không chứng minh `$ref` ngoài có thể tải được. Nếu hợp đồng sử dụng external reference, bật resolve trong test để kiểm tra các tài nguyên đó có thể truy cập và được đọc.

## 9. Cấu hình resolve và resolveFully

Swagger Parser có `ParseOptions` để điều khiển xử lý reference. Ví dụ bật resolve:

```java
import io.swagger.parser.OpenAPIParser;
import io.swagger.v3.parser.core.models.ParseOptions;
import io.swagger.v3.parser.core.models.SwaggerParseResult;

ParseOptions options = new ParseOptions();
options.setResolve(true);

SwaggerParseResult result = new OpenAPIParser()
    .readLocation("src/test/resources/openapi.yaml", null, options);
```

Khi resolve external hoặc relative reference, parser có thể tải tài nguyên được tham chiếu, thêm component đã resolve vào `components` và thay URL external bằng local `$ref`. Điều này hữu ích để phát hiện file bị thiếu, URI sai hoặc tài nguyên không truy cập được.

`resolveFully` có tác động mạnh hơn:

```java
ParseOptions options = new ParseOptions();
options.setResolve(true);
options.setResolveFully(true);

SwaggerParseResult result = new OpenAPIParser()
    .readLocation("src/test/resources/openapi.yaml", null, options);
```

Parser thay các local reference bằng nội dung của phần tử được tham chiếu. Kết quả có thể lớn hơn nhiều do schema hoặc response bị lặp lại. Chỉ bật khi công cụ downstream cần document đã dereference; không bật chỉ để “parse kỹ hơn”.

Với OpenAPI 3.1, Swagger Parser sử dụng logic dereference riêng so với 3.0. Cách resolve external và internal reference có thể cho kết quả object model khác nhau giữa hai phiên bản. Hãy kiểm tra đúng document đầu vào và test kết quả resolve trên phiên bản parser được khóa, đặc biệt khi pipeline so sánh hoặc serialize lại document.

## 10. Flatten và composed schema

`flatten` hữu ích khi công cụ downstream cần các schema inline được chuyển vào `components.schemas`:

```java
ParseOptions options = new ParseOptions();
options.setFlatten(true);

SwaggerParseResult result = new OpenAPIParser()
    .readLocation("src/test/resources/openapi.yaml", null, options);
```

Flatten có thể tạo thêm schema component và `$ref` mới. Đây là biến đổi object model, không phải yêu cầu bắt buộc để đọc đặc tả.

Với `allOf`, `oneOf` và `anyOf`, `resolveFully` có tùy chọn `resolveCombinators`. Khi bật, parser có thể hợp nhất một số composed schema thành schema không còn giữ cấu trúc composition trong kết quả resolved. Khi tắt, các thành phần `allOf`/`oneOf`/`anyOf` được giữ lại trong model.

```java
ParseOptions options = new ParseOptions();
options.setResolve(true);
options.setResolveFully(true);
options.setResolveCombinators(false);
```

Nếu contract test cần xác nhận chính xác cấu trúc `allOf` hoặc `oneOf` mà API công bố, không dùng cấu hình resolve làm mất cấu trúc đó. Parse document gốc hoặc giữ `resolveCombinators=false`, tùy mục tiêu kiểm thử.

## 11. Đọc document cần xác thực hoặc external reference

Nếu OpenAPI document được phục vụ sau xác thực, Swagger Parser hỗ trợ gửi thông tin authorization khi đọc URL.

```java
import io.swagger.parser.OpenAPIParser;
import io.swagger.v3.parser.core.models.AuthorizationValue;
import io.swagger.v3.parser.core.models.SwaggerParseResult;
import java.util.List;

AuthorizationValue auth = new AuthorizationValue(
    "Authorization",
    "Bearer " + System.getenv("OPENAPI_READ_TOKEN"),
    "header"
);

SwaggerParseResult result = new OpenAPIParser().readLocation(
    "https://api.example.com/v3/api-docs",
    List.of(auth),
    null
);
```

Token nên được lấy từ secret store của CI hoặc biến môi trường được bảo vệ. Không commit token, không in giá trị header ra log và không đưa credential vào URL query string nếu không có yêu cầu giao thức cụ thể.

External `$ref` có thể khiến parser thực hiện request mạng đến host khác. Chỉ resolve document từ nguồn tin cậy; kiểm soát domain được phép truy cập và không để parser tự do tải URL do người dùng không tin cậy cung cấp. Điều này giúp giảm nguy cơ SSRF hoặc rò rỉ thông tin qua request ngoài ý muốn.

Không tắt xác minh TLS để làm parser chấp nhận certificate lỗi. Với CA nội bộ, cài CA vào truststore hoặc cấu hình SSL trust đúng cho tiến trình CI. Cờ `TRUST_ALL` của Swagger Parser bỏ qua certificate không hợp lệ và không nên dùng trong pipeline thông thường.

## 12. Swagger 2.0 và OpenAPI 3.x

Swagger 2.0 dùng trường `swagger: "2.0"`, không dùng `openapi`. `OpenAPIParser` có thể đọc Swagger 2.0 và chuyển document sang mô hình OpenAPI 3.0 tương đương trước khi trả kết quả.

Điều đó hữu ích khi muốn xử lý nhiều đầu vào trong cùng pipeline, nhưng cần nhớ kết quả model không còn là biểu diễn nguyên trạng của Swagger 2.0. Nếu công việc yêu cầu giữ đúng mô hình 2.0 hoặc dùng API cũ của Swagger Parser 1.x, hãy dùng đúng nhánh/thư viện dành cho Swagger 2.0 thay vì giả định parser 2.x giữ nguyên document nguồn.

Khi pipeline chấp nhận cả 2.0 và 3.x, nên ghi lại phiên bản nguồn, phiên bản đích sau chuyển đổi và các thay đổi do converter tạo ra. Đừng so sánh trực tiếp hai document khác phiên bản như thể chúng có cùng cấu trúc.

## 13. Parse không thay thế contract test runtime

Parser kiểm tra document và object model theo những quy tắc mà phiên bản parser hỗ trợ. Nó không tự chứng minh controller thực sự trả đúng response đã mô tả.

Các tầng kiểm tra nên được tách rõ:

| Tầng | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Đọc document | JSON/YAML có đọc được không? | Parser tạo được OpenAPI model |
| Đặc tả hợp lệ | Document có tuân thủ phiên bản OpenAPI/JSON Schema đã khai báo không? | Parser diagnostics hoặc validator tương ứng |
| Reference | `$ref` có resolve được không? | Bật resolve và kiểm tra external resource |
| Quy tắc dự án | OperationId có duy nhất? API có mô tả security? | Linter hoặc custom rules |
| Runtime contract | API có trả status/header/body đúng document không? | Gửi request test và validate response |
| Compatibility | Thay đổi document có phá client hiện hữu không? | So sánh spec với baseline và breaking-change checker |

Một document parse thành công vẫn có thể mô tả sai status code, header, response body hoặc security của ứng dụng. Để kiểm tra hành vi runtime, dùng request test với validator request/response phù hợp hoặc contract testing giữa provider và consumer.

## 14. Đưa parser vào CI pipeline

Một pipeline thực tế có thể thực hiện theo thứ tự:

1. Khởi động ứng dụng với cấu hình test hoặc tạo OpenAPI artifact ở build time.
2. Lấy `/v3/api-docs` hoặc file JSON/YAML đã xuất.
3. Đọc trường `openapi` và xác nhận phiên bản được phép trong repository.
4. Dùng parser có hỗ trợ phiên bản đó để parse và thu thập diagnostics.
5. Resolve `$ref` nếu hợp đồng sử dụng external/relative references.
6. Chạy validator hoặc linter theo quy tắc của dự án.
7. So sánh với baseline để phát hiện breaking changes.
8. Chạy contract test request/response với ứng dụng.

Ví dụ shell tải document từ Springdoc:

```bash
curl -fsS http://localhost:8080/v3/api-docs -o target/openapi.json
```

Parser test có thể đọc `target/openapi.json` bằng `readLocation`. Nếu dùng URL trực tiếp, bảo đảm service đã sẵn sàng trước khi gọi parser và không để bước test chạy trước khi ứng dụng bind cổng.

Khóa parser version trong Maven/Gradle và cập nhật có chủ đích. Khi nâng parser, chạy lại bộ fixture đại diện cho các cấu trúc document quan trọng: `$ref` nội bộ/ngoài, `allOf`, `oneOf`, nullable schema, security schemes, callbacks/webhooks và các keyword JSON Schema mà API đang dùng.

## 15. Ma trận fixture để kiểm tra parser tương thích

Một test chỉ parse Petstore đơn giản có thể không phát hiện parser thiếu hỗ trợ tính năng mà dự án thực sự dùng. Nên duy trì một bộ fixture nhỏ theo phiên bản và tính năng:

| Fixture | Nội dung cần có | Điều cần xác minh |
|---|---|---|
| OAS 3.0 | `nullable`, `components`, request/response refs | Parser 3.0 đọc và giữ model mong đợi |
| OAS 3.1 | JSON Schema type union có `null`, `webhooks` hoặc schema 2020-12 | Parser hiểu version 3.1 và không làm mất keyword quan trọng |
| OAS 3.2 | Một tính năng mới thực sự được dự án sử dụng | Chỉ chạy với parser có công bố hỗ trợ 3.2 |
| External references | Relative file và URL ngoài | Resolve được trong môi trường CI có quyền truy cập |
| Recursive schema | `$ref` trỏ lại component gốc | Không bị coi nhầm là reference không tồn tại |
| Composition | `allOf`, `oneOf`, `anyOf` và discriminator | Model giữ cấu trúc nếu test cần kiểm tra composition |
| Protected document | Endpoint yêu cầu token | Parser gửi authorization đúng và không lộ secret |

Sau khi parse, serialize model ra JSON/YAML rồi so sánh ngữ nghĩa hoặc kiểm tra các trường quan trọng. Không nhất thiết so sánh byte-for-byte vì parser/serializer có thể đổi thứ tự key, chuẩn hóa quoting hoặc format mà không đổi semantics.

## 16. Lỗi thường gặp khi đọc đặc tả

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Parser báo unsupported version | Parser cũ hơn phiên bản `openapi` của document | Nâng parser hoặc chọn parser có hỗ trợ phiên bản đó |
| OAS 3.1 bị parse lỗi với parser 3.0 | Dùng parser/API chỉ hỗ trợ OpenAPI 3.0 | Dùng Swagger Parser 2.1.0+ và API `OpenAPIParser` phù hợp |
| OAS 3.2 không được nhận diện | Parser đang dùng chưa công bố hỗ trợ 3.2 | Chọn parser 3.2-aware, ví dụ openapi-processor parser, và kiểm tra tính năng cần dùng |
| `getOpenAPI()` trả null | Lỗi cú pháp, version hoặc lỗi đọc nguồn | In `getMessages()`, kiểm tra URL/file và định dạng JSON/YAML |
| Có model nhưng parser vẫn báo message | Document có warning hoặc validation issue | Đánh giá diagnostics theo policy CI; không bỏ qua toàn bộ message |
| `$ref` ngoài không resolve | File/URL thiếu, DNS, TLS, auth hoặc base URI sai | Kiểm tra resource và credentials; bật resolve trong test |
| Local `$ref` biến mất khỏi output | Đã bật `resolveFully` | Dùng `resolve` thường hoặc tắt resolveFully nếu cần giữ refs |
| Schema `allOf` bị hợp nhất | `resolveFully` cùng `resolveCombinators` đang bật | Giữ composition bằng `resolveCombinators=false` hoặc parse document gốc |
| Swagger 2.0 output thành OpenAPI 3.0 | Parser 2.x tự chuyển đổi đầu vào 2.0 | Ghi nhận conversion; dùng nhánh parser 1.x nếu cần model 2.0 |
| Parser test xung đột class | Nhiều phiên bản Swagger Core/Models trên classpath | Kiểm tra dependency tree và đồng bộ dependency management |
| URL document trả 401/403 | CI không gửi credentials | Cấu hình AuthorizationValue hoặc tải artifact đã xác thực |
| Parser tải URL ngoài không mong muốn | External `$ref` trỏ đến host không tin cậy | Giới hạn nguồn tài liệu và host được phép resolve |

## 17. Checklist chọn và vận hành parser

- [ ] Đã đọc trường `openapi` ở root, không nhầm với `info.version`.
- [ ] Parser được chọn có công bố hỗ trợ đúng phiên bản OpenAPI.
- [ ] Nếu dùng OpenAPI 3.1, parser hỗ trợ JSON Schema 2020-12 và reference behavior tương ứng.
- [ ] Nếu dùng OpenAPI 3.2, parser được tài liệu xác nhận hỗ trợ 3.2.
- [ ] Đã khóa phiên bản parser trong Maven/Gradle và kiểm tra dependency tree.
- [ ] Dùng `OpenAPIParser` phù hợp để auto-detect version; không dùng convenience API chỉ hỗ trợ 3.0 cho document 3.1.
- [ ] Đã kiểm tra cả `SwaggerParseResult.getOpenAPI()` và `getMessages()`.
- [ ] CI có policy rõ ràng cho warning và error.
- [ ] Bật resolve khi cần kiểm tra external/relative `$ref`.
- [ ] Chỉ bật `resolveFully` hoặc `flatten` khi bước downstream cần biến đổi model.
- [ ] Đã kiểm thử `allOf`/`oneOf` và recursive schema mà API sử dụng.
- [ ] External reference được giới hạn trong nguồn tin cậy và TLS được xác minh.
- [ ] Contract test runtime xác minh request/response thực tế ngoài việc parse document.
- [ ] Có fixture đại diện cho các phiên bản và tính năng OpenAPI mà dự án sử dụng.

Đọc đặc tả đúng cách bắt đầu từ việc nhận diện phiên bản `openapi` và chọn parser có hỗ trợ phiên bản đó. Swagger Parser 2.1.x hỗ trợ OpenAPI 3.0/3.1, trong khi document 3.2 cần parser công bố hỗ trợ 3.2. Sau khi đọc, kiểm tra cả model và diagnostics; chỉ resolve reference khi mục tiêu test yêu cầu, vì `resolveFully` có thể thay đổi cấu trúc và làm document lớn hơn. Cuối cùng, tách kiểm tra cú pháp/đặc tả khỏi contract test runtime để biết API thực tế có tuân thủ document hay không.

## Tài liệu tham khảo

- [Swagger Parser – README và API sử dụng](https://github.com/swagger-api/swagger-parser)
- [Swagger Parser – OpenAPI 3.1 support](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---OpenAPI-3.1)
- [Swagger Parser – Issue theo dõi hỗ trợ OpenAPI 3.2](https://github.com/swagger-api/swagger-parser/issues/2248)
- [openapi-processor/openapi-parser – OpenAPI 3.2, 3.1 và 3.0 parser](https://github.com/openapi-processor/openapi-parser)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [Springdoc OpenAPI – Official documentation](https://springdoc.org/)
