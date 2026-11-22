# Giá trị số, UUID và chuỗi trong path

## Mục tiêu bài học

Một biến trong đường dẫn HTTP luôn được truyền đi dưới dạng ký tự của URI, nhưng ứng dụng có thể sử dụng giá trị đó như **số nguyên**, **UUID** hoặc **chuỗi định danh**. Với **Spring REST Docs**, ta cần mô tả rõ ý nghĩa và định dạng mong đợi của các biến này, đồng thời kiểm thử cách Spring xử lý giá trị hợp lệ và không hợp lệ.

Bài học thuộc nhóm **Path parameters** của module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng từ bài kiểm thử HTTP bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, tham số và biên soạn thành tài liệu **Asciidoctor/Markdown** trong quy trình build, CI.

Sau khi hoàn thành, bạn có thể:

- Phân biệt **tên biến** trong URI template với **giá trị** và **kiểu dữ liệu Java** của biến.
- Hiểu các bước khớp route, trích xuất path variable, chuyển đổi kiểu và kiểm tra nghiệp vụ.
- Xử lý ID số nguyên, UUID, slug/chuỗi với quy tắc phù hợp.
- Viết kiểm thử MockMvc sinh **path-parameters.adoc** cho cả ba kiểu dữ liệu.
- Kiểm thử giá trị sai định dạng; phân biệt lỗi định tuyến với lỗi chuyển đổi hoặc không tìm thấy tài nguyên.
- Tài liệu hóa định dạng một cách rõ ràng mà không nhầm phần mô tả của REST Docs với cơ chế validation.
- Đưa snippet vào Asciidoctor và quy trình build/CI.

## 1. Dù là số hay UUID, giá trị vẫn nằm trong URI

Xét ba endpoint:

~~~text
GET /api/orders/42
GET /api/users/550e8400-e29b-41d4-a716-446655440000
GET /api/articles/spring-rest-docs-guide
~~~

Trong controller, chúng có thể được mô tả bởi ba URI template:

~~~text
/api/orders/{orderId}
/api/users/{userId}
/api/articles/{slug}
~~~

| Biến trong URI template | Giá trị của request mẫu | Kiểu Java thường chọn | Ý nghĩa |
| --- | --- | --- | --- |
| **{orderId}** | **42** | **Long** hoặc **Integer** | Khóa số của đơn hàng |
| **{userId}** | **550e8400-e29b-41d4-a716-446655440000** | **UUID** | Định danh người dùng |
| **{slug}** | **spring-rest-docs-guide** | **String** | Chuỗi nhận diện bài viết |

**{orderId}**, **{userId}** và **{slug}** là *tên biến*; các chuỗi **42**, **550e...** và **spring-rest-docs-guide** là *giá trị*. Spring MVC sử dụng **@PathVariable** để lấy giá trị từ đường dẫn rồi chuyển thành kiểu mà phương thức controller khai báo.

Không có kiểu “Long” hay “UUID” ở cấp cú pháp URI. Trên đường truyền, URI chứa ký tự; việc hiểu chuỗi đó là số, UUID hay slug thuộc về ứng dụng.

### 1.1. Ba bước xử lý cần phân biệt

~~~mermaid
flowchart LR
    A["GET /api/orders/42"] --> B["Khớp /api/orders/{orderId}"]
    B --> C["Lấy chuỗi 42"]
    C --> D["Chuyển thành Long"]
    D --> E["Kiểm tra nghiệp vụ / tra cứu"]
    E --> F["HTTP response"]
    F --> G["Spring REST Docs sinh snippet từ test"]
~~~

| Giai đoạn | Câu hỏi chính | Ví dụ lỗi |
| --- | --- | --- |
| **Định tuyến** | Request có khớp mẫu **/api/orders/{orderId}** không? | Thiếu đoạn **/{orderId}**, có thể trả 404 nếu không có route khác |
| **Chuyển đổi dữ liệu** | Chuỗi của biến có chuyển được sang **Long/UUID** không? | **abc** không thể chuyển thành **Long**, thông thường trả 400 |
| **Nghiệp vụ và validation** | Giá trị hợp lệ về kiểu có được phép và có tồn tại không? | ID **9999** đúng kiểu nhưng không có đơn hàng, ứng dụng có thể trả 404 |

Spring REST Docs **không quyết định** ba giai đoạn trên. Nó sinh tài liệu từ những request/response được bài kiểm thử thực hiện, giúp kiểm chứng tên biến trong URI template và phần mô tả của người viết.

## 2. Path parameter là số nguyên

### 2.1. Khai báo kiểu Long/Integer

~~~java
@GetMapping("/api/orders/{orderId}")
OrderResponse getOrder(@PathVariable("orderId") Long orderId) {
    return orderService.getOrder(orderId);
}
~~~

Khi gửi **GET /api/orders/42**, Spring khớp mẫu, lấy giá trị ký tự **42** rồi chuyển sang **Long**. Với một giá trị không phải số nguyên như **abc**, quá trình chuyển đổi sang **Long** thường gây **400 Bad Request** theo cấu hình xử lý lỗi mặc định của Spring MVC.

Những trường hợp cần lưu ý:

| Giá trị trên path | Binding vào **Long** | Điểm cần kiểm tra |
| --- | --- | --- |
| **42** | Chuyển thành số 42 | Giá trị có tồn tại, có quyền truy cập không? |
| **00042** | Thường chuyển thành 42 | Nếu số **0** đầu có ý nghĩa, không nên dùng kiểu số |
| **-42** | Có thể chuyển thành -42 | Kiểu **Long** không tự đảm bảo ID dương |
| **abc** | Không chuyển được | Thường gây lỗi 400 |
| Số quá lớn vượt giới hạn **Long** | Không chuyển được | Cần bài kiểm thử cho giá trị ngoài phạm vi |
| **42.5** | Không phù hợp với số nguyên | Thường gây lỗi 400 |

Chuyển đổi kiểu chỉ đảm bảo cú pháp và phạm vi mà kiểu Java hỗ trợ; nó **không tự đảm bảo** ID phải dương, phải tồn tại trong cơ sở dữ liệu hay thuộc tài nguyên người gọi được phép truy cập. Những điều kiện đó thuộc về validation, service và kiểm thử nghiệp vụ.

### 2.2. Khi nào nên dùng String cho ID trông giống số?

Ví dụ mã khách hàng **00001234**. Nếu các số **0** đầu là một phần bắt buộc của mã, chuyển sang **Long** sẽ làm mất ý nghĩa biểu diễn. Dùng **String** và kiểm tra định dạng sẽ phù hợp hơn:

~~~java
@GetMapping("/api/customers/{customerCode}")
CustomerResponse getCustomer(
        @PathVariable("customerCode") String customerCode) {
    // customerCode giữ nguyên "00001234" để tra cứu
    return customerService.getByCode(customerCode);
}
~~~

Quyết định nên dựa vào bản chất **ID nghiệp vụ**, không chỉ dựa vào việc chuỗi hiện đang có toàn chữ số.

## 3. Path parameter là UUID

UUID thường được biểu diễn bằng một chuỗi gồm các nhóm ký tự hexa và dấu gạch nối, ví dụ:

~~~text
550e8400-e29b-41d4-a716-446655440000
~~~

Controller có thể nhận thẳng kiểu **java.util.UUID**:

~~~java
import java.util.UUID;

@GetMapping("/api/users/{userId}")
UserResponse getUser(@PathVariable("userId") UUID userId) {
    return userService.getUser(userId);
}
~~~

Spring thường chuyển giá trị path sang UUID thông qua hệ thống chuyển đổi kiểu. Với chuỗi không thể phân tích thành UUID, binding thất bại và theo cấu hình mặc định thường trả **400**.

Hãy tách hai khái niệm:

- **UUID đúng cú pháp:** bộ chuyển đổi nhận được một đối tượng UUID.
- **UUID hợp lệ theo hợp đồng API:** ứng dụng có thể còn giới hạn phiên bản UUID, yêu cầu dạng hiển thị chuẩn hoặc yêu cầu ID thực sự tồn tại.

Một chuỗi có thể được bộ phân tích cú pháp UUID chấp nhận mà vẫn không đáp ứng quy tắc riêng của API. Vì vậy, nếu hợp đồng yêu cầu **UUID version cụ thể** hoặc **dạng chữ thường theo chuẩn**, hãy áp dụng kiểm tra riêng và viết test cho quy tắc đó; đừng chỉ dựa vào kiểu tham số Java.

Trong tài liệu, nên ghi rõ ví dụ:

~~~java
parameterWithName("userId")
    .description("UUID định danh người dùng; ví dụ "
        + "550e8400-e29b-41d4-a716-446655440000")
~~~

Đoạn **description(...)** chỉ hiển thị mô tả. Nó **không tự kiểm tra** tính đúng của UUID được gửi lên.

## 4. Path parameter là chuỗi, slug hoặc mã nghiệp vụ

Một số tài nguyên sử dụng ID dạng chuỗi thay cho số hoặc UUID:

~~~text
GET /api/articles/spring-rest-docs-guide
GET /api/products/SKU-2026-001
GET /api/locales/vi
~~~

Với **@PathVariable String**, Spring có thể nhận chuỗi trong một đoạn đường dẫn:

~~~java
@GetMapping("/api/articles/{slug}")
ArticleResponse getArticle(@PathVariable("slug") String slug) {
    return articleService.getBySlug(slug);
}
~~~

**String** không tự đảm bảo slug chỉ gồm chữ thường, chữ số và dấu gạch ngang. Nếu API yêu cầu định dạng **[a-z0-9-]+**, bạn có thể:

1. Khớp route có giới hạn bằng URI pattern phù hợp.
2. Để route khớp rồi áp dụng validation trong controller/service, trả mã lỗi theo hợp đồng API.

Ví dụ một route Spring MVC có điều kiện mẫu:

~~~java
@GetMapping("/api/articles/{slug:[a-z0-9-]+}")
ArticleResponse getArticle(@PathVariable("slug") String slug) {
    return articleService.getBySlug(slug);
}
~~~

Trong trường hợp này, **/api/articles/spring-rest-docs** có thể khớp, còn **/api/articles/Invalid_Slug** không khớp mẫu vì chứa chữ hoa và dấu gạch dưới. Nếu không có mapping khác, kết quả thường là **404** ở giai đoạn định tuyến. Nếu bạn chọn kiểm tra ở tầng validation thay vì mẫu route, ứng dụng có thể trả **400**; hãy ghi rõ và kiểm thử hành vi mong đợi.

### 4.1. Mã hóa ký tự đặc biệt trên URL

Path là một phần của URI và có quy tắc mã hóa riêng. Những trường hợp thường cần chú ý:

| Giá trị nghiệp vụ | Vấn đề | Cách xử lý |
| --- | --- | --- |
| **spring-rest-docs** | Chữ, số, dấu gạch ngang an toàn cho slug | Có thể đặt trực tiếp vào một segment |
| **café** hoặc văn bản có dấu | Phải có cách biểu diễn URI hợp lệ | Dùng URI builder/client có xử lý encoding phù hợp |
| **A B** | Khoảng trắng không nên đưa thô vào URI | Encode giá trị trước khi gửi |
| **A/B** | Dấu **/** có ý nghĩa phân tách đoạn path | Tránh dùng trong ID một segment; encoded slash có thể bị proxy/server xử lý khác nhau |
| **A?B** hoặc **A#B** | **?** mở query; **#** bắt đầu fragment ở phía client | Encode đúng hoặc thiết kế mã định danh an toàn |

Với tên bài viết, nên chọn slug ngắn, ổn định và ít ký tự đặc biệt. Nếu ID buộc phải chứa dấu phân tách, cân nhắc thiết kế endpoint hoặc cách truyền khác, thay vì mặc định **{slug}** sẽ nhận mọi chuỗi bất kỳ một cách đồng nhất ở mọi HTTP server.

Không truyền mật khẩu, access token hoặc thông tin nhạy cảm qua path: URL có thể được ghi lại ở access log, lịch sử trình duyệt hoặc hệ thống giám sát.

## 5. Dùng pathParameters(...) để tài liệu hóa cả ba kiểu

Spring REST Docs không yêu cầu hàm riêng cho mỗi kiểu. Cả số, UUID lẫn chuỗi đều dùng:

~~~java
pathParameters(
    parameterWithName("orderId")
        .description("Mã đơn hàng dạng số nguyên dương")
)
~~~

Với URI template **/api/orders/{orderId}**, hàm **parameterWithName("orderId")** phải khớp **tên biến** trong dấu ngoặc nhọn. Nó không nhận giá trị **42**, cũng không nhận nguyên chuỗi **{orderId}** làm tên.

| Kiểu | Template | Mô tả nên có |
| --- | --- | --- |
| **Long** | **/api/orders/{orderId}** | Dữ liệu là số nguyên, giới hạn/điều kiện nếu có, ý nghĩa ID |
| **UUID** | **/api/users/{userId}** | UUID định danh loại tài nguyên nào, ví dụ giá trị chuẩn |
| **String/slug** | **/api/articles/{slug}** | Quy tắc ký tự, phân biệt hoa/thường, ví dụ |

Thông tin về **kiểu dữ liệu** trong các mô tả trên là **quy ước API do người viết tài liệu cung cấp**. Bản thân **pathParameters(...)** không nhìn vào kiểu **Long/UUID/String** của controller để xác minh nội dung mô tả. Nó chủ yếu giúp đối chiếu các **tên** biến của URI template với descriptor.

## 6. Ví dụ hoàn chỉnh với Spring Boot và MockMvc

Ví dụ sử dụng **Java 17+**, **Spring Boot 3.x**, **JUnit 5** và **Spring REST Docs MockMvc**. Dự án có plugin Spring Boot và BOM quản lý phiên bản có thể khai báo Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

### 6.1. Controller nhận Long, UUID và String

Tạo **PathValuesController.java**:

~~~java
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PathValuesController {

    @GetMapping("/api/orders/{orderId}")
    PathValueView getOrder(@PathVariable("orderId") Long orderId) {
        return new PathValueView("order", orderId.toString());
    }

    @GetMapping("/api/users/{userId}")
    PathValueView getUser(@PathVariable("userId") UUID userId) {
        return new PathValueView("user", userId.toString());
    }

    @GetMapping("/api/articles/{slug}")
    PathValueView getArticle(@PathVariable("slug") String slug) {
        return new PathValueView("article", slug);
    }
}

record PathValueView(String kind, String value) {}
~~~

Controller này chỉ trả lại dữ liệu đã được bind để minh họa cơ chế. Một ứng dụng thực sẽ kiểm tra quyền truy cập, validation và tra cứu tài nguyên bằng service/repository.

### 6.2. Bài kiểm thử sinh snippet

Tạo **PathValuesDocumentationTest.java** cùng package với controller:

~~~java
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PathValuesController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class PathValuesDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    private static final UUID USER_ID = UUID.fromString(
        "550e8400-e29b-41d4-a716-446655440000");

    @Test
    void documentNumericId() throws Exception {
        mockMvc.perform(get("/api/orders/{orderId}", 42L)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.kind").value("order"))
            .andExpect(jsonPath("$.value").value("42"))
            .andDo(document("order-id-get",
                pathParameters(
                    parameterWithName("orderId")
                        .description("Mã đơn hàng dạng số nguyên Long")
                )
            ));
    }

    @Test
    void documentUuid() throws Exception {
        mockMvc.perform(get("/api/users/{userId}", USER_ID)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.kind").value("user"))
            .andExpect(jsonPath("$.value")
                .value("550e8400-e29b-41d4-a716-446655440000"))
            .andDo(document("user-uuid-get",
                pathParameters(
                    parameterWithName("userId")
                        .description("UUID định danh người dùng")
                )
            ));
    }

    @Test
    void documentStringSlug() throws Exception {
        mockMvc.perform(get("/api/articles/{slug}",
                    "spring-rest-docs-guide")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.kind").value("article"))
            .andExpect(jsonPath("$.value")
                .value("spring-rest-docs-guide"))
            .andDo(document("article-slug-get",
                pathParameters(
                    parameterWithName("slug")
                        .description("Slug bài viết, ví dụ spring-rest-docs-guide")
                )
            ));
    }

    @Test
    void rejectInvalidNumber() throws Exception {
        mockMvc.perform(get("/api/orders/{orderId}", "not-a-number"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectInvalidUuid() throws Exception {
        mockMvc.perform(get("/api/users/{userId}", "invalid-uuid"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Tại sao **RestDocumentationRequestBuilders.get(...)** quan trọng? Với **MockMvc**, builder của REST Docs giúp giữ thông tin URI template như **/api/users/{userId}**. Nếu thay bằng URL đã triển khai sẵn như **/api/users/550e...**, tên biến **userId** không còn được truyền tường minh, làm cơ chế sinh bảng path parameters dễ thất bại.

Hai test với giá trị sai chỉ xác nhận **cách Spring MVC chuyển đổi kiểu** trong controller mẫu; chúng không sinh bảng tham số và không nhằm kết luận mọi API đều phải trả đúng cùng mã lỗi khi đã cấu hình xử lý ngoại lệ tùy chỉnh.

### 6.3. Các snippet được sinh

Sau khi chạy bài kiểm thử thành công, ta kỳ vọng có các thư mục:

~~~text
build/generated-snippets/
├── order-id-get/
│   └── path-parameters.adoc
├── user-uuid-get/
│   └── path-parameters.adoc
└── article-slug-get/
    └── path-parameters.adoc
~~~

Sơ đồ trên chỉ liệt kê snippet path parameters; Spring REST Docs còn có thể sinh **http-request.adoc**, **http-response.adoc**, **curl-request.adoc** và các snippet khác theo cấu hình. Ví dụ bảng nội dung tương ứng:

| Snippet | Parameter | Description |
| --- | --- | --- |
| **order-id-get/path-parameters.adoc** | **orderId** | Mã đơn hàng dạng số nguyên Long |
| **user-uuid-get/path-parameters.adoc** | **userId** | UUID định danh người dùng |
| **article-slug-get/path-parameters.adoc** | **slug** | Slug bài viết, ví dụ spring-rest-docs-guide |

Không sửa trực tiếp file dưới **generated-snippets**, vì lần chạy test sau sẽ tạo lại chúng từ các descriptor.

## 7. Tách kiểm tra tên biến khỏi kiểm tra dữ liệu

**pathParameters(...)** kiểm tra tính khớp giữa khai báo tài liệu và biến của URI template. Điều này khác với việc test dữ liệu đã được parse/validate.

| Tình huống | Phần kiểm tra có trách nhiệm |
| --- | --- |
| Template dùng **{userId}** nhưng descriptor ghi **userID** | Spring REST Docs có thể báo lỗi tài liệu |
| Template có **{orderId}** nhưng quên mô tả **orderId** | Snippet nghiêm ngặt báo tham số chưa được tài liệu hóa |
| Giá trị **abc** gửi tới **@PathVariable Long** | Spring MVC chuyển đổi kiểu và test HTTP |
| Giá trị **invalid-uuid** gửi tới **@PathVariable UUID** | Spring MVC chuyển đổi kiểu và test HTTP |
| Giá trị **-42** được chuyển thành **Long** nhưng ID phải dương | Validation hoặc logic nghiệp vụ của ứng dụng |
| UUID đúng cú pháp nhưng người dùng không tồn tại | Service/repository và bài kiểm thử nghiệp vụ |
| Slug chứa ký tự ngoài quy ước | Route regex/validation và bài kiểm thử tương ứng |

Vì vậy một bộ test có chất lượng nên có **test hợp lệ tạo snippet**, **test sai kiểu dữ liệu**, và **test sai điều kiện nghiệp vụ** nếu những điều kiện đó thuộc hợp đồng API.

### 7.1. Có nên dùng optional() với ID trong path?

Với route **/api/orders/{orderId}**, đoạn dành cho **{orderId}** phải có để khớp mẫu. **parameterWithName("orderId").optional()** chỉ thay đổi đặc tính của descriptor Spring REST Docs; nó **không** làm **GET /api/orders** khớp route chi tiết.

Nếu API cần cả endpoint danh sách **GET /api/orders** và endpoint chi tiết **GET /api/orders/{orderId}**, hãy khai báo hai mẫu route, kiểm thử và tài liệu hóa từng trường hợp. Không sử dụng **optional()** để cố biến path segment thành một tùy chọn định tuyến.

### 7.2. Khi nào dùng ignored()?

Nếu một biến kỹ thuật có trong đường dẫn nhưng đã được giải thích ở chỗ dùng chung, có thể chọn bỏ nó khỏi bảng:

~~~java
pathParameters(
    parameterWithName("tenantId").ignored(),
    parameterWithName("userId")
        .description("UUID người dùng thuộc tenant")
)
~~~

Giả sử URI template là **/api/tenants/{tenantId}/users/{userId}**, đoạn **tenantId** vẫn cần được cung cấp khi gọi route. **ignored()** chỉ làm cho descriptor không hiển thị trong snippet; hãy cân nhắc vì người đọc API vẫn có thể cần biết cách truyền biến này.

## 8. WebTestClient và REST Assured áp dụng tương tự

Tính đúng của số, UUID và slug được kiểm tra bởi ứng dụng; hai test client khác cũng có thể sinh snippet với cùng **pathParameters(...)**.

### 8.1. WebTestClient

Trong bài kiểm thử đã cấu hình bộ sinh tài liệu REST Docs cho **WebTestClient**:

~~~java
webTestClient.get()
    .uri("/api/users/{userId}",
        "550e8400-e29b-41d4-a716-446655440000")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("user-uuid-webtestclient",
        pathParameters(
            parameterWithName("userId")
                .description("UUID định danh người dùng")
        )
    ));
~~~

Trong đoạn trên, **document(...)** thuộc **WebTestClientRestDocumentation**, và client cần gắn cấu hình REST Docs (ví dụ **documentationConfiguration(...)**) trước khi gọi.

### 8.2. REST Assured

Với **RequestSpecification spec** đã cấu hình tích hợp Spring REST Docs:

~~~java
given(spec)
    .filter(document("article-slug-rest-assured",
        pathParameters(
            parameterWithName("slug")
                .description("Slug định danh bài viết")
        )
    ))
    .pathParam("slug", "spring-rest-docs-guide")
    .when()
    .get("/api/articles/{slug}")
    .then()
    .statusCode(200);
~~~

Ở đây **document(...)** được import từ **RestAssuredRestDocumentation**. **pathParam(...)** gán giá trị vào request; **parameterWithName(...)** định nghĩa tên biến cần mô tả. Với giá trị có ký tự đặc biệt, hãy dùng khả năng mã hóa URI của HTTP client và kiểm tra hành vi server/proxy.

## 9. Nhúng snippet vào Asciidoctor và tích hợp CI

Với file **src/docs/asciidoc/index.adoc**, nếu thuộc tính **snippets** đã được build truyền vào:

~~~asciidoc
= API Path Identifiers
:toc: left

== Đơn hàng theo mã số

GET /api/orders/{orderId}

include::{snippets}/order-id-get/path-parameters.adoc[]
include::{snippets}/order-id-get/http-response.adoc[]

== Người dùng theo UUID

GET /api/users/{userId}

include::{snippets}/user-uuid-get/path-parameters.adoc[]
include::{snippets}/user-uuid-get/http-response.adoc[]

== Bài viết theo slug

GET /api/articles/{slug}

include::{snippets}/article-slug-get/path-parameters.adoc[]
include::{snippets}/article-slug-get/http-response.adoc[]
~~~

Ví dụ cấu hình **Gradle Groovy DSL** khi plugin **org.asciidoctor.jvm.convert** đã được cài đặt:

~~~groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir
}
~~~

Quan hệ **dependsOn test** giúp tác vụ dựng tài liệu thực thi test sinh snippets trước. Trong **CI**, chỉ xuất bản tài liệu khi các bài kiểm thử liên quan và tác vụ dựng tài liệu đều thành công. Nhờ đó, nếu đổi tên URI template từ **{userId}** thành **{accountId}** mà chưa cập nhật descriptor, quá trình sinh snippet nghiêm ngặt có thể phát hiện thay đổi không đồng bộ.

Spring REST Docs thường sinh snippet AsciiDoc khi dùng cấu hình mặc định. Nếu dự án xuất bản bằng **Markdown**, hãy dùng cơ chế chuyển đổi hoặc mẫu snippet phù hợp; câu lệnh **include::...[]** là cú pháp của Asciidoctor, không tự hoạt động trong Markdown thuần.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| **/api/orders/abc** trả 400 | Spring không chuyển được chuỗi sang **Long** | Gửi số nguyên phù hợp hoặc thiết kế lại kiểu mã |
| **/api/users/invalid-uuid** trả 400 | Giá trị không được phân tích thành UUID | Dùng UUID hợp lệ và thêm test cho trường hợp sai |
| **/api/orders/-1** vẫn vào controller | **Long** cho phép số âm | Thêm validation/ràng buộc nghiệp vụ nếu ID phải dương |
| Mã **00042** bị biến thành **42** | ID được bind sang kiểu số | Dùng **String** nếu số 0 đầu mang ý nghĩa nghiệp vụ |
| **/api/articles/A/B** không khớp route **/{slug}** | Dấu **/** phân tách path segments | Chọn slug an toàn hoặc thiết kế route khác |
| Slug sai quy ước nhưng vẫn chạy | **String** không tự kiểm tra định dạng | Bổ sung route regex hoặc validation |
| Bị báo descriptor không tồn tại | Tên trong **parameterWithName(...)** khác tên trong URI template | Dùng đúng tên, ví dụ **userId**, không dùng giá trị UUID |
| Không sinh **path-parameters.adoc** | Test chưa gọi **document(...)**, thiếu cấu hình hoặc không giữ URI template | Dùng builder REST Docs và kiểm tra thiết lập test |
| Asciidoctor thiếu snippet | Test chưa chạy hoặc thuộc tính **snippets** chưa đúng | Kiểm tra thứ tự build và đường dẫn đầu ra |
| Tài liệu ghi UUID nhưng endpoint thực nhận String tùy ý | Mô tả không được đối chiếu với kiểu Java/validation | Review hợp đồng và viết test nhận/từ chối giá trị |

## 11. Bài thực hành

Hãy xây dựng ba endpoint:

~~~text
GET /api/invoices/{invoiceId}
GET /api/customers/{customerId}
GET /api/products/{productCode}
~~~

Quy ước nghiệp vụ:

- **invoiceId** là số nguyên dương trong phạm vi **Long**.
- **customerId** là UUID, ví dụ **550e8400-e29b-41d4-a716-446655440000**.
- **productCode** là mã chuỗi có thể chứa các số 0 đầu, ví dụ **00007A**.

Thực hiện lần lượt:

1. Viết controller nhận **Long**, **UUID** và **String** bằng ba **@PathVariable** tương ứng.
2. Viết bài kiểm thử HTTP hợp lệ cho từng endpoint bằng **RestDocumentationRequestBuilders.get(...)**; kiểm tra HTTP status và một trường JSON response.
3. Với mỗi request, gọi **document(...)** và **pathParameters(parameterWithName(...).description(...))** để sinh snippet riêng.
4. Thêm test gửi **invoiceId=abc**, **customerId=not-a-uuid** và giải thích vì sao lỗi kiểu dữ liệu khác với lỗi tài nguyên không tồn tại.
5. Kiểm tra **productCode=00007A** được giữ nguyên giá trị. Giải thích vì sao không nên ép mã này sang **Long**.
6. Nhúng ba file **path-parameters.adoc** vào Asciidoctor; chạy test rồi dựng tài liệu, bảo đảm CI sẽ phát hiện khi test thất bại.

Mẫu khai báo tài liệu:

~~~java
// Với GET /api/invoices/{invoiceId}
pathParameters(
    parameterWithName("invoiceId")
        .description("Mã hóa đơn là số nguyên dương")
)

// Với GET /api/customers/{customerId}
pathParameters(
    parameterWithName("customerId")
        .description("UUID định danh khách hàng")
)

// Với GET /api/products/{productCode}
pathParameters(
    parameterWithName("productCode")
        .description("Mã sản phẩm dạng chuỗi, giữ nguyên số 0 đầu")
)
~~~

**Tiêu chí hoàn thành:** ba request hợp lệ sinh được snippet; test kiểm tra đúng cách bind và lỗi giá trị; mô tả nêu rõ định dạng/ý nghĩa; tài liệu Asciidoctor hiển thị ba bảng tương ứng.

## Ghi nhớ

Giá trị path được truyền trên URI dưới dạng ký tự; **Spring MVC** chuyển chúng thành **Long**, **UUID** hoặc **String** theo chữ ký controller và quy tắc của ứng dụng. **Số nguyên** cần kiểm tra giới hạn/điều kiện nghiệp vụ, **UUID** cần kiểm tra quy ước định dạng nếu có, còn **chuỗi** cần chú ý slug và URL encoding. **Spring REST Docs** sử dụng cùng cơ chế **pathParameters(...)** và **parameterWithName(...)** để mô tả cả ba, nhưng không tự kiểm tra tính đúng của định dạng trong phần mô tả. Kết hợp kiểm thử dữ liệu hợp lệ/sai, sinh snippet từ request thực và đưa vào build, CI để tài liệu REST API có thể kiểm chứng.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs RequestDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/RequestDocumentation.html), [Spring MVC @PathVariable](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/pathvariable.html), và [Spring MVC URI patterns](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html).
