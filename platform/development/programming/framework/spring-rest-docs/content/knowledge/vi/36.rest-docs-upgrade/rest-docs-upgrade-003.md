# Chuyển giữa MockMvc, WebTestClient và REST Assured

## Mục tiêu bài học

Spring REST Docs có thể tạo tài liệu từ nhiều test harness HTTP. Dự án có thể bắt đầu với **MockMvc**, sau đó chuyển sang **WebTestClient** khi ứng dụng dùng WebFlux hoặc cần kiểm thử reactive stack; hoặc dùng **REST Assured** khi muốn kiểm thử API qua HTTP với cú pháp fluent. Việc chuyển đổi không chỉ là thay import hay đổi dependency: cách dựng request, chờ response, cấu hình documentation và biểu diễn operation đều khác nhau.

Bài học thuộc chương **Nâng cấp** của module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng bằng các bài kiểm thử HTTP với **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, payload, tham số và header; biên soạn tài liệu Asciidoctor/Markdown rồi tích hợp vào build và CI.

Sau bài học, bạn có thể:

- Hiểu vai trò và giới hạn của ba test harness.
- Chọn integration phù hợp với kiến trúc ứng dụng và mục tiêu test.
- Xác định dependency, setup và documentation configurer cần thay đổi.
- Chuyển request, assertion và REST Docs descriptors theo từng API.
- Giữ nguyên document identifier, contract và cấu trúc snippet cần công bố.
- So sánh output giữa harness cũ và mới để phát hiện khác biệt.
- Nâng cấp từng bước và giữ pipeline tài liệu chạy ổn định trong CI.

## 1. Hiểu đúng ba test harness

Ba lựa chọn đều có thể thực hiện HTTP operation và tích hợp Spring REST Docs, nhưng chúng kiểm thử ở các lớp khác nhau.

| Tiêu chí | MockMvc | WebTestClient | REST Assured |
| --- | --- | --- | --- |
| Nền tảng thường dùng | Spring MVC | Spring WebFlux; cũng có thể bind tới mock server | HTTP client test fluent, dùng với server đang chạy hoặc cấu hình phù hợp |
| Cách thực thi | Gọi Spring MVC request pipeline trong test, không cần mở HTTP server thật | Có thể bind tới application context/controller hoặc gọi server qua HTTP | Gửi request qua HTTP tới base URI/server |
| Kiểu API | Fluent request builder và result matchers | Fluent reactive client, exchange() | Given/When/Then |
| Response | MvcResult và MockMvc matchers | EntityExchangeResult/exchange result và expectations | Response và response assertions |
| REST Docs integration | spring-restdocs-mockmvc | spring-restdocs-webtestclient | spring-restdocs-restassured |
| Phù hợp | Controller/API test trong Spring MVC | Reactive endpoint hoặc test qua WebTestClient | Integration/API test qua HTTP và cú pháp assertion fluent |

Không có một harness tốt nhất cho mọi dự án. Chọn theo mục tiêu:

- Ứng dụng Spring MVC, muốn test controller nhanh trong process: MockMvc thường phù hợp.
- Ứng dụng WebFlux/reactive, cần kiểm tra luồng reactive hoặc dùng WebTestClient sẵn có: WebTestClient phù hợp.
- Cần gọi API qua HTTP, kiểm thử cùng server đã khởi động hoặc muốn Given/When/Then: REST Assured phù hợp.

Nếu mục tiêu là xác nhận hành vi thực tế của reverse proxy, TLS, cookie browser hoặc network gateway, cần test qua server/hạ tầng thật. MockMvc không mô phỏng toàn bộ các lớp đó; WebTestClient bind trực tiếp vào application context cũng không tương đương gọi qua network.

## 2. Xác định phạm vi chuyển đổi trước khi sửa test

Trước khi đổi harness, ghi lại baseline của một operation đại diện:

| Thành phần | Cần ghi nhận |
| --- | --- |
| HTTP operation | Method, URI, query/path parameters |
| Request | Headers, cookies, content type, body |
| Response | Status, headers, body |
| Assertions | Status, JSON fields, headers, cookies và lỗi |
| REST Docs | Document identifier, descriptors, preprocessors |
| Snippet output | Tên file, template format, output directory |
| Build | Task test, task Asciidoctor/Markdown assembly |

Chọn ít nhất một GET có path/query parameter và một POST có request body nếu dự án có cả hai dạng. Các operation đại diện giúp phát hiện khác biệt về encoding, body, header và descriptor.

Giữ nguyên contract và document identifier trong lần chuyển đầu tiên. Nếu đồng thời đổi identifier, template và nội dung API, việc so sánh snippet sẽ khó xác định nguyên nhân.

## 3. Dependency và cấu hình REST Docs

Mỗi harness có integration artifact tương ứng. Ví dụ Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc:<version>'
    // Hoặc:
    // testImplementation 'org.springframework.restdocs:spring-restdocs-webtestclient:<version>'
    // testImplementation 'org.springframework.restdocs:spring-restdocs-restassured:<version>'
}
~~~

Chỉ thêm integration thực sự được sử dụng. Giữ các artifact Spring REST Docs cùng version theo hướng dẫn của release và dependency management của dự án. Không copy cả ba dependency chỉ để thử chuyển đổi nếu test suite không cần chúng.

Với Maven, thay artifact trong dependency tương ứng và giữ scope test. Sau khi thay đổi, kiểm tra dependency tree để phát hiện core/integration modules bị resolve lệch version.

Các thành phần dùng chung thường vẫn giữ:

- spring-restdocs-core thông qua dependency integration.
- Document identifiers trong document(...).
- Payload descriptors như requestFields(...), responseFields(...).
- Custom snippets, attributes và template format nếu tương thích.
- Tài liệu AsciiDoc/Markdown và quy trình publish.

Phần cần thay thường là test harness, cách gắn documentation filter/configurer và cách lấy/assert response.

## 4. Từ MockMvc sang WebTestClient

### 4.1. Cấu hình WebTestClient

REST Docs cung cấp WebTestClientRestDocumentation.documentationConfiguration(...) để gắn documentation vào WebTestClient. Ví dụ cấu hình khái quát:

~~~java
import org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient webTestClient = WebTestClient
    .bindToApplicationContext(applicationContext)
    .configureClient()
    .filter(
        WebTestClientRestDocumentation.documentationConfiguration(
            restDocumentation
        )
    )
    .build();
~~~

Đoạn này minh họa cách bind vào application context và gắn documentation filter. Nếu test dùng WebFlux controller slice, router function hoặc server đang chạy, chọn cách bind phù hợp với fixture đó. Không thay bind mode máy móc khi test cũ đang xác minh network behavior.

### 4.2. Chuyển request và assertion

MockMvc:

~~~java
mockMvc.perform(get("/api/orders/{id}", 42)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(42))
    .andDo(document("orders-get"));
~~~

WebTestClient:

~~~java
webTestClient.get()
    .uri("/api/orders/{id}", 42)
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.id").isEqualTo(42)
    .consumeWith(
        WebTestClientRestDocumentation.document("orders-get")
    );
~~~

Document identifier vẫn là orders-get, giúp giữ liên kết tới trang tài liệu hiện tại. Assertion phải được chuyển đầy đủ; đừng chỉ giữ status rồi bỏ JSON path, header hoặc cookie checks từ test MockMvc cũ.

### 4.3. Chuyển descriptor

Các descriptor REST Docs thường có thể được dùng lại:

~~~java
.consumeWith(
    WebTestClientRestDocumentation.document(
        "orders-get",
        pathParameters(
            parameterWithName("id")
                .description("Mã đơn hàng")
        ),
        responseFields(
            fieldWithPath("id").description("Mã đơn hàng"),
            fieldWithPath("status").description("Trạng thái đơn hàng")
        )
    )
)
~~~

Descriptor mô tả operation data; nó không phụ thuộc vào cách request được dựng bởi MockMvc hay WebTestClient. Tuy nhiên, cách gắn snippet/documentation vào chain phụ thuộc integration và vị trí consume result.

## 5. Từ MockMvc sang REST Assured

### 5.1. Cấu hình documentation filter

REST Assured tích hợp Spring REST Docs qua RestAssuredRestDocumentation. Test thường dùng một RequestSpecification dùng chung để gắn filter:

~~~java
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.documentationConfiguration;

RequestSpecification documentationSpec =
    new RequestSpecBuilder()
        .addFilter(documentationConfiguration(restDocumentation))
        .build();
~~~

Trong thực tế cần các import REST Assured và RestDocumentationContextProvider tương ứng. Cấu hình output directory và snippet defaults ở documentation configuration hoặc build setup theo version đang dùng.

### 5.2. Chuyển request và assertion

MockMvc:

~~~java
mockMvc.perform(get("/api/orders/{id}", 42)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(42));
~~~

REST Assured:

~~~java
given(documentationSpec)
    .accept(ContentType.JSON)
    .filter(document("orders-get"))
    .when()
    .get("/api/orders/{id}", 42)
    .then()
    .statusCode(200)
    .body("id", equalTo(42));
~~~

REST Assured thường dùng filter document(...) để ghi operation. Hãy bảo đảm filter được gắn vào đúng request và chạy trong chain. Nếu assertion thất bại, test phải fail như trước; không để quá trình sinh snippet che mất lỗi API.

### 5.3. Dùng descriptors

Có thể truyền descriptor vào REST Assured documentation filter:

~~~java
.filter(document("orders-get",
    pathParameters(
        parameterWithName("id")
            .description("Mã đơn hàng")
    ),
    responseFields(
        fieldWithPath("id").description("Mã đơn hàng"),
        fieldWithPath("status").description("Trạng thái đơn hàng")
    )
))
~~~

Các descriptor payload, headers, parameters và links được dùng theo API REST Docs tương ứng. Xác nhận static imports và overload của version hiện tại; không giả định mọi helper hoặc preprocessing method có cùng chữ ký trên các integration.

## 6. Chuyển đổi request body

Request body là nơi dễ phát sinh khác biệt do API dựng request khác nhau.

MockMvc:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"customerId":42,"description":"Keyboard"}
            """))
    .andExpect(status().isCreated());
~~~

WebTestClient:

~~~java
webTestClient.post()
    .uri("/api/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of(
        "customerId", 42,
        "description", "Keyboard"
    ))
    .exchange()
    .expectStatus().isCreated();
~~~

REST Assured:

~~~java
given(documentationSpec)
    .contentType(ContentType.JSON)
    .body(Map.of(
        "customerId", 42,
        "description", "Keyboard"
    ))
    .filter(document("orders-create",
        requestFields(
            fieldWithPath("customerId").description("Mã khách hàng"),
            fieldWithPath("description").description("Mô tả đơn hàng")
        )
    ))
    .when()
    .post("/api/orders")
    .then()
    .statusCode(201);
~~~

Khi chuyển từ chuỗi JSON sang object/Map, serialization có thể tạo thứ tự field, number representation hoặc escaping khác. JSON object thường không yêu cầu thứ tự field, nhưng snippet diff có thể thay đổi. Nếu tài liệu cần payload ổn định, dùng fixture rõ ràng và so sánh JSON theo cấu trúc thay vì phụ thuộc thứ tự key.

## 7. Chuyển preprocessors và dữ liệu nhạy cảm

Preprocessor REST Docs chuẩn hóa bản request/response ghi vào snippet. Khi đổi integration, giữ cùng chính sách:

- Pretty-print JSON nếu cần.
- Loại bỏ hoặc thay giá trị Authorization.
- Che cookie/session/token.
- Chuẩn hóa timestamp hoặc UUID động nếu chúng không thuộc contract.
- Giữ lại Content-Type, Location và các header có ý nghĩa.

MockMvc có thể cấu hình preprocessors mặc định trên MockMvcRestDocumentationConfigurer. WebTestClient và REST Assured có cấu hình documentation riêng; chuyển chính sách tương đương sang configurer/filter tương ứng theo API của version đang dùng.

Không giả định cấu hình MockMvc có thể truyền nguyên trạng cho WebTestClient hoặc REST Assured. Nếu API nhận request/response preprocessor khác kiểu, viết adapter/helper trả về đúng kiểu mà integration yêu cầu.

Sau chuyển đổi, kiểm tra cả hai điều:

1. Ứng dụng vẫn nhận request thật với header/cookie cần thiết và test behavior vẫn đúng.
2. Snippet không chứa giá trị nhạy cảm.

Preprocessor chỉ thay đổi dữ liệu REST Docs ghi lại, không phải cơ chế bảo vệ endpoint hoặc thay thế security filter.

## 8. Giữ ổn định document identifiers và snippet contract

Nếu tài liệu đang include:

~~~asciidoc
include::{snippets}/orders-get/http-request.adoc[]
include::{snippets}/orders-get/http-response.adoc[]
include::{snippets}/orders-get/path-parameters.adoc[]
include::{snippets}/orders-get/response-fields.adoc[]
~~~

giữ identifier orders-get khi chuyển harness nếu operation vẫn là cùng API. Điều này giúp giảm số lượng thay đổi trong tài liệu.

Tuy nhiên, không mặc định mọi snippet sẽ byte-for-byte giống nhau. Các yếu tố có thể làm output khác:

- URI encoding hoặc cách serialize query parameter.
- Header mặc định do client thêm vào.
- Thứ tự header.
- Pretty-print hoặc JSON serializer.
- Cách biểu diễn multipart, form data hoặc cookie.
- Template format và phiên bản REST Docs.

So sánh snippet theo ý nghĩa HTTP/contract trước, sau đó mới quyết định có cần giữ nguyên formatting. Chỉ cập nhật tài liệu khi khác biệt là có chủ đích.

## 9. Bảng chuyển đổi nhanh

| Tác vụ | MockMvc | WebTestClient | REST Assured |
| --- | --- | --- | --- |
| GET request | mockMvc.perform(get(...)) | webTestClient.get().uri(...) | given().when().get(...) |
| POST body | .content(...) | .bodyValue(...) hoặc body publisher | .body(...) |
| Thực thi | perform(...) | .exchange() | .when() |
| Status assertion | .andExpect(status().isOk()) | .expectStatus().isOk() | .statusCode(200) |
| JSON assertion | jsonPath(...) matcher | .expectBody().jsonPath(...) | .body(path, matcher) |
| Ghi REST Docs | .andDo(document(...)) | .consumeWith(documentation(...)) | .filter(document(...)) |
| Documentation setup | documentationConfiguration(...) | WebTestClientRestDocumentation.documentationConfiguration(...) | documentationConfiguration(...) filter |

Bảng này là bản đồ khái niệm, không phải thay thế từng dòng tự động. Chữ ký cụ thể và cách setup phụ thuộc version Spring REST Docs, Spring Framework và REST Assured.

## 10. Kiểm thử parity sau khi chuyển

Để xác nhận harness mới tạo tài liệu tương đương, chọn một operation và chạy cả test cũ lẫn test mới trong thời gian chuyển tiếp.

Kiểm tra:

| Nhóm | So sánh |
| --- | --- |
| Request line | Method, path, query string |
| Request headers | Content-Type, Accept, custom headers |
| Request body | JSON structure, encoding, null/optional fields |
| Response | Status và body structure |
| Headers | Location, Content-Type, cache/security headers |
| Parameters | Tên, giá trị và encoding |
| Descriptors | Field paths, descriptions, optional/subsection |
| Preprocessors | Masking, pretty-print, normalization |
| Snippet output | Identifier, file names, template format |

Với JSON, so sánh theo cấu trúc thay vì text nếu thứ tự property không phải contract. Với header, cân nhắc header nào thứ tự không quan trọng. Với query string và cookie, kiểm tra encoding vì khác biệt ở đây có thể ảnh hưởng client.

Sau khi parity đạt, mới loại bỏ test harness cũ nếu không còn được dùng ở nơi khác. Không xóa test cũ chỉ vì một test mới đã compile.

## 11. Tổ chức chuyển đổi theo từng giai đoạn

Một kế hoạch giảm rủi ro:

1. Chọn một operation đơn giản và lưu snippet baseline.
2. Thêm integration dependency cần thiết, giữ version đồng bộ.
3. Tạo test mới bằng harness đích và giữ nguyên document identifier.
4. Chuyển request, assertions và REST Docs descriptors.
5. Chuyển preprocessors, custom snippets và output configuration.
6. Sinh snippet vào thư mục sạch và so sánh với baseline.
7. Render tài liệu, kiểm tra include và link.
8. Mở rộng sang operation có body, multipart, cookie và error response.
9. Chạy toàn bộ test suite và CI.
10. Gỡ integration cũ khi không còn test nào sử dụng.

Nếu đang chuyển từ Spring MVC sang WebFlux, đây là thay đổi kiến trúc ứng dụng chứ không chỉ thay test harness. Cần kiểm tra controller/router, serialization, exception handling và behavior reactive riêng.

## 12. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Test WebTestClient không sinh snippet | Chưa gắn documentation filter hoặc chưa gọi consumeWith | Kiểm tra configurer và vị trí consume result |
| REST Assured gọi API được nhưng không có snippet | Filter document chưa gắn vào request specification | Gắn filter vào request đang thực thi |
| Body snippet khác sau chuyển đổi | Serializer hoặc cách tạo body khác | Dùng fixture thống nhất và so sánh JSON theo cấu trúc |
| Query parameter bị encode khác | Client xử lý URI template/parameter khác nhau | Assert URI cuối và kiểm tra wire representation |
| Header xuất hiện thêm | Client tự thêm default header | Phân loại header thuộc contract và header do harness thêm |
| Assertion cũ bị mất | Chỉ chuyển phần document call | Lập danh sách assertion và chuyển đầy đủ |
| Preprocessor không hoạt động | Cấu hình của harness cũ không được chuyển | Tạo cấu hình tương đương cho integration mới |
| Snippet include bị lỗi | Document identifier hoặc tên file thay đổi | Giữ ID và kiểm tra output thực tế |
| WebTestClient test treo/khác behavior | Sai cách bind hoặc xử lý reactive chain | Chọn bind mode đúng và hoàn tất exchange/assertion |
| REST Assured không dùng được mock application context | REST Assured đang gọi HTTP qua client | Khởi động server/test environment hoặc chọn harness bind phù hợp |
| CI không sinh tài liệu | Task chỉ chạy test cũ hoặc dependency thiếu | Cập nhật task/test filters và kiểm tra dependency graph |

## 13. Bài thực hành

Chọn endpoint:

~~~text
POST /api/orders
GET /api/orders/{id}
~~~

Yêu cầu:

1. Tạo một bộ test MockMvc hiện có và ghi lại document identifiers, assertions, descriptors và preprocessors.
2. Chuyển hai operation sang WebTestClient hoặc REST Assured.
3. Giữ nguyên status, body, header, parameter và cookie assertions.
4. Giữ document identifiers để các trang tài liệu hiện tại tiếp tục hoạt động.
5. Sinh snippet từ cả harness cũ và mới vào hai thư mục riêng.
6. So sánh HTTP exchange, field tables và output sau preprocessing.
7. Render Asciidoctor/Markdown bằng pipeline hiện tại.
8. Chạy toàn bộ CI; chỉ gỡ integration cũ sau khi xác nhận không còn test phụ thuộc.

**Tiêu chí hoàn thành:** test harness mới xác nhận cùng contract; REST Docs sinh đủ snippet; khác biệt output được giải thích; tài liệu render thành công; CI chạy ổn định và không làm mất assertion cũ.

## Ghi nhớ

Chuyển giữa MockMvc, WebTestClient và REST Assured là thay đổi ở test harness, cách dựng request/response và điểm gắn documentation filter/configurer. Các REST Docs descriptors và document identifiers thường có thể giữ lại, nhưng request serialization, headers, URI encoding và snippet formatting cần được kiểm tra lại. Chuyển từng operation, giữ nguyên assertions và preprocessing, sinh snippet vào thư mục riêng rồi so sánh parity trước khi gỡ harness cũ. Nếu đồng thời đổi MVC sang reactive stack, xem đó là thay đổi kiến trúc có phạm vi rộng hơn và kiểm thử riêng behavior của ứng dụng.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring WebTestClient Reference](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html), [REST Assured Usage Guide](https://github.com/rest-assured/rest-assured/wiki/Usage) và [Spring REST Docs Releases](https://github.com/spring-projects/spring-restdocs/releases).
