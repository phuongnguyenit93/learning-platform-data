# Document path parameters bằng pathParameters

## Mục tiêu bài học

Trong **Spring REST Docs**, tài liệu API được tạo từ các bài kiểm thử HTTP đã thực thi. Thay vì tự viết một bảng tham số rồi hy vọng nó luôn đúng, ta khai báo các phần cần tài liệu hóa ngay trong bài kiểm thử. Khi đường dẫn API thay đổi mà khai báo tài liệu không còn phù hợp, bài kiểm thử có thể thất bại và cảnh báo sự sai lệch trước khi tài liệu được phát hành.

Sau bài này, bạn có thể:

- Phân biệt **path parameter** với query parameter, request body và HTTP header.
- Dùng **pathParameters(...)** cùng **parameterWithName(...)** để mô tả các biến trong URI template.
- Sinh snippet **path-parameters.adoc** từ bài kiểm thử **MockMvc**, đồng thời hiểu cách áp dụng với **WebTestClient** và **REST Assured**.
- Đưa snippet vào tài liệu **Asciidoctor** và kết nối việc sinh tài liệu với build/CI.
- Chẩn đoán các lỗi thường gặp khi URI template và tài liệu tham số không khớp.

## 1. Path parameter là gì?

Xét endpoint:

~~~http
GET /api/orders/42/lines/7
Accept: application/json
~~~

Phần định nghĩa đường dẫn của endpoint là:

~~~text
/api/orders/{orderId}/lines/{lineId}
~~~

Hai thành phần **{orderId}** và **{lineId}** là *path parameters* (biến đường dẫn): chúng xác định tài nguyên ngay trong đường dẫn URI. Ở request mẫu, giá trị tương ứng là **42** và **7**.

| Thành phần | Ví dụ | Cách tài liệu hóa với Spring REST Docs |
| --- | --- | --- |
| Path parameter | **/orders/{orderId}** | **pathParameters(...)** |
| Query parameter | **/orders?status=OPEN** | **queryParameters(...)** ở phiên bản hỗ trợ API này |
| Request header | **Authorization: Bearer ...** | **requestHeaders(...)** |
| JSON request body | **{"quantity": 2}** | **requestFields(...)** |
| JSON response body | **{"id": 42}** | **responseFields(...)** |

Điểm phân biệt quan trọng: **@PathVariable** là cách Spring MVC liên kết giá trị trên URL vào tham số của controller; **pathParameters(...)** là cách Spring REST Docs **mô tả và kiểm chứng tài liệu** cho các biến đó. Một API chạy được chưa có nghĩa là phần tài liệu của nó đã đầy đủ.

## 2. Cách hoạt động của pathParameters(...)

Cú pháp cốt lõi trong bài kiểm thử:

~~~java
pathParameters(
    parameterWithName("orderId").description("Mã đơn hàng"),
    parameterWithName("lineId").description("Mã dòng hàng trong đơn")
)
~~~

- **pathParameters(...)** tạo snippet mô tả nhóm tham số của đường dẫn.
- **parameterWithName("orderId")** tạo mô tả cho đúng biến **{orderId}** trong URI template.
- **description(...)** cung cấp ý nghĩa nghiệp vụ hiển thị trong bảng tài liệu.
- **document("order-line-get", ...)** gắn các snippet vào một request/response đã được kiểm thử và lưu dưới thư mục theo mã định danh **order-line-get**.

Quy trình sinh tài liệu:

~~~mermaid
flowchart LR
    A["HTTP test với URI template"] --> B["Kiểm tra status và dữ liệu"]
    B --> C["document(..., pathParameters(...))"]
    C --> D["generated-snippets/order-line-get/path-parameters.adoc"]
    D --> E["Asciidoctor: tài liệu API"]
    E --> F["Build / CI xuất bản"]
~~~

Các biến khai báo trong **parameterWithName(...)** phải có tên trùng với URI template. Ví dụ, dùng tên **id** để mô tả **{orderId}** là sai, dù request thực tế vẫn trả HTTP 200.

## 3. Ví dụ hoàn chỉnh với Spring MVC và MockMvc

Ví dụ dưới đây sử dụng **Java 17+**, **JUnit 5**, **Spring Boot 3.x** và **spring-restdocs-mockmvc**. Với Maven, thay thư mục build tương ứng bằng **target/generated-snippets**.

### 3.1. Thư viện kiểm thử

Trong dự án Spring Boot dùng Gradle, cần thư viện kiểm thử của Spring Boot và Spring REST Docs cho MockMvc:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Nếu dùng Spring Boot dependency management/BOM, không cần tự ghi phiên bản của từng dependency REST Docs khi BOM đã quản lý nó. Với WebTestClient hay REST Assured, thay thư viện tích hợp phù hợp.

### 3.2. Controller mẫu

Tệp **OrderLineController.java**:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderLineController {

    @GetMapping("/api/orders/{orderId}/lines/{lineId}")
    OrderLineResponse getLine(
            @PathVariable("orderId") Long orderId,
            @PathVariable("lineId") Long lineId) {
        return new OrderLineResponse(orderId, lineId, 2);
    }
}

record OrderLineResponse(Long orderId, Long lineId, int quantity) {}
~~~

Endpoint trả JSON theo cấu trúc:

~~~json
{
  "orderId": 42,
  "lineId": 7,
  "quantity": 2
}
~~~

Ở hệ thống thực, controller thường gọi service để lấy dữ liệu. Controller cố định trong ví dụ chỉ nhằm tập trung vào cơ chế tài liệu hóa biến đường dẫn.

### 3.3. Bài kiểm thử sinh snippet

Tệp **OrderLineDocumentationTest.java**, đặt cùng package với controller:

~~~java
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

@WebMvcTest(OrderLineController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderLineDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentGetOrderLine() throws Exception {
        mockMvc.perform(get(
                    "/api/orders/{orderId}/lines/{lineId}",
                    42L, 7L)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.orderId").value(42))
            .andExpect(jsonPath("$.lineId").value(7))
            .andDo(document("order-line-get",
                pathParameters(
                    parameterWithName("orderId")
                        .description("Mã đơn hàng cần tra cứu"),
                    parameterWithName("lineId")
                        .description("Mã dòng hàng thuộc đơn hàng")
                )
            ));
    }
}
~~~

**Tại sao dùng RestDocumentationRequestBuilders.get(...)?** Khi kiểm thử bằng MockMvc, builder này giúp Spring REST Docs giữ được *URI template* cùng tên các biến, chẳng hạn **{orderId}**, để tạo snippet path parameters. Tránh thay bằng lời gọi sử dụng chuỗi URL đã triển khai sẵn như **/api/orders/42/lines/7**: chuỗi đó không còn thể hiện tên biến cần mô tả.

Bài kiểm thử đồng thời xác nhận mã trạng thái HTTP và vài giá trị quan trọng trong response. Vì vậy snippet gắn với một tình huống request/response thực sự đạt yêu cầu, thay vì một ví dụ viết thủ công.

### 3.4. Kết quả sinh ra

Sau khi chạy bài kiểm thử, thư mục đầu ra sẽ có cấu trúc tương tự:

~~~text
build/
└── generated-snippets/
    └── order-line-get/
        ├── curl-request.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        ├── httpie-request.adoc
        ├── request-body.adoc
        ├── response-body.adoc
        └── path-parameters.adoc
~~~

Số lượng snippet thực tế còn tùy phiên bản và cấu hình. Phần cần chú ý ở bài này là **path-parameters.adoc**: nó chứa bảng có tên tham số và mô tả lấy từ hai lời gọi **parameterWithName(...)**. Không nên sửa trực tiếp snippet sinh ra, vì lần chạy test sau sẽ tạo lại nội dung.

## 4. Cơ chế kiểm chứng và mức độ nghiêm ngặt

Khi sử dụng **pathParameters(...)** thông thường, Spring REST Docs kiểm tra khai báo tham số so với URI template. Việc này giúp phát hiện tài liệu thiếu hoặc không nhất quán.

| Tình huống | Kết quả mong đợi |
| --- | --- |
| URI template chứa **{orderId}**, có **parameterWithName("orderId")** | Được tài liệu hóa |
| URI template chứa thêm **{lineId}** nhưng không mô tả **lineId** | Snippet nghiêm ngặt báo tham số chưa được tài liệu hóa |
| Mô tả **customerId** trong khi template không có **{customerId}** | Snippet báo mô tả không khớp với request |
| Mô tả đúng tên nhưng sai ý nghĩa nghiệp vụ | Framework không thể tự suy ra; cần review nội dung |
| Có biến đường dẫn không muốn hiển thị | Có thể khai báo descriptor với **ignored()** để bỏ qua một cách tường minh |

**ignored()** và **optional()** có ý nghĩa khác nhau:

~~~java
pathParameters(
    parameterWithName("orderId").description("Mã đơn hàng"),
    parameterWithName("internalKey").ignored()
)
~~~

Descriptor **ignored()** cho biết tham số vẫn được nhận diện nhưng không được liệt kê trong bảng. **optional()** đánh dấu mô tả là không bắt buộc xuất hiện trong mẫu request được kiểm thử; nó **không** biến một **@PathVariable** bắt buộc trong cấu hình định tuyến thành tùy chọn. Với path parameter thông thường, nên mô tả đầy đủ và giữ tính nghiêm ngặt của snippet.

Một số API của Spring REST Docs cung cấp biến thể **relaxedPathParameters(...)** để bỏ qua lỗi do tham số có trong request nhưng chưa được mô tả. Chỉ nên dùng có chủ đích, vì khi mở rộng URI template, tài liệu có thể âm thầm bỏ sót biến mới.

## 5. Nhiều path parameters và các tình huống đặc biệt

Một URI template có thể chứa nhiều biến và mỗi biến cần mô tả theo đúng vai trò:

~~~text
GET /api/shops/{shopId}/products/{productId}/reviews/{reviewId}
~~~

~~~java
pathParameters(
    parameterWithName("shopId").description("Mã cửa hàng"),
    parameterWithName("productId").description("Mã sản phẩm tại cửa hàng"),
    parameterWithName("reviewId").description("Mã đánh giá cần xem")
)
~~~

Không gộp chúng thành một mô tả chung vì người đọc API cần biết rõ quan hệ giữa từng ID. Nếu một biến mang kiểu UUID, ULID hoặc mã nghiệp vụ, nên nói rõ định dạng và cung cấp ví dụ trong tài liệu; **pathParameters(...)** tạo tài liệu, không tự kiểm tra quy tắc kiểu dữ liệu đó. Hãy thêm bài kiểm thử hợp lệ/không hợp lệ tương ứng nếu định dạng là một phần của hợp đồng API.

Với đường dẫn có query string, hãy tách trách nhiệm tài liệu:

~~~http
GET /api/orders/42/lines/7?locale=vi
~~~

- **orderId** và **lineId**: được mô tả bởi **pathParameters(...)**.
- **locale**: là query parameter; mô tả bằng nhóm snippet tham số truy vấn tương ứng với phiên bản REST Docs đang dùng.

Nếu endpoint chỉ khác HTTP method, chẳng hạn **GET** và **DELETE** cùng dùng **/api/orders/{orderId}/lines/{lineId}**, mỗi phép thử/document nên có mã định danh snippet riêng, ví dụ **order-line-get** và **order-line-delete**. Bạn có thể dùng lại hàm tạo các descriptor khi ý nghĩa biến không đổi, nhưng vẫn phải kiểm thử từng hành vi của endpoint.

## 6. Dùng pathParameters với WebTestClient và REST Assured

**pathParameters(...)** là khai báo tài liệu chung cho URI template; cách gắn nó vào chuỗi kiểm thử thay đổi theo HTTP test client.

### WebTestClient

Khi đã cấu hình Spring REST Docs cho **WebTestClient** bằng **documentationConfiguration(...)**, cách dùng điển hình là:

~~~java
webTestClient.get()
    .uri("/api/orders/{orderId}/lines/{lineId}", 42L, 7L)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("order-line-webtestclient",
        pathParameters(
            parameterWithName("orderId").description("Mã đơn hàng"),
            parameterWithName("lineId").description("Mã dòng hàng")
        )
    ));
~~~

Trong đoạn trên, **document(...)** được static import từ **WebTestClientRestDocumentation**; **pathParameters(...)** và **parameterWithName(...)** vẫn thuộc **RequestDocumentation**. Test client cần được gắn bộ lọc REST Docs trong bước thiết lập để sinh snippet.

### REST Assured

Với **RequestSpecification spec** đã được cấu hình bộ lọc Spring REST Docs:

~~~java
given(spec)
    .filter(document("order-line-rest-assured",
        pathParameters(
            parameterWithName("orderId").description("Mã đơn hàng"),
            parameterWithName("lineId").description("Mã dòng hàng")
        )
    ))
    .pathParam("orderId", 42L)
    .pathParam("lineId", 7L)
    .when()
    .get("/api/orders/{orderId}/lines/{lineId}")
    .then()
    .statusCode(200);
~~~

Ở đây **document(...)** là API từ **RestAssuredRestDocumentation**. Đầu tiên cấu hình **RequestSpecification** với REST Docs; sau đó request sử dụng đường dẫn chứa tên biến để hệ thống nhận diện và lập bảng tham số.

Ba cách tích hợp đều hướng đến cùng một kết quả: kiểm thử HTTP chạy thành công và sinh snippet từ những request đã được quan sát.

## 7. Đưa snippet vào tài liệu Asciidoctor và build

Ví dụ tệp **src/docs/asciidoc/index.adoc**:

~~~asciidoc
= Order API
:toc: left
:snippets: {docdir}/../../../build/generated-snippets

== Xem dòng hàng trong đơn

GET /api/orders/{orderId}/lines/{lineId}

=== Path parameters

include::{snippets}/order-line-get/path-parameters.adoc[]

=== HTTP request

include::{snippets}/order-line-get/http-request.adoc[]

=== HTTP response

include::{snippets}/order-line-get/http-response.adoc[]
~~~

Trong ví dụ trên, **{docdir}** là thư mục chứa tài liệu AsciiDoc; đường dẫn tương đối phù hợp với cấu trúc dự án Gradle được nêu. Nếu build tool truyền sẵn thuộc tính **snippets**, hãy sử dụng thuộc tính từ build để tránh phụ thuộc đường dẫn cố định.

Với Gradle và plugin **org.asciidoctor.jvm.convert** đã được cài đặt, có thể thiết lập sự phụ thuộc như sau:

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

Nhờ **dependsOn**, tác vụ sinh tài liệu sẽ thực hiện kiểm thử trước khi xử lý các lệnh **include**. Trong CI nên chạy đầy đủ bài kiểm thử và tác vụ Asciidoctor; nếu kiểm thử REST Docs thất bại hoặc snippet bị thiếu, pipeline cần dừng thay vì xuất bản tài liệu cũ. Khi dùng Maven, thiết lập tương đương trong vòng đời kiểm thử và Asciidoctor Maven Plugin.

Spring REST Docs tạo snippet AsciiDoc một cách trực tiếp. Nếu trang tài liệu cuối được viết bằng Markdown, bạn có thể liên kết/nhúng thông qua công cụ xuất bản phù hợp, hoặc cấu hình mẫu snippet riêng theo công cụ đó; **không** nên giả định mọi trình dựng Markdown đều hiểu cú pháp **include::...[]** của Asciidoctor.

## 8. Lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân hay gặp | Cách khắc phục |
| --- | --- | --- |
| Không tìm được thông tin URI template hoặc không sinh được path parameter snippet | Sử dụng URL đã mở rộng hay request builder không giữ URI template | Với MockMvc, dùng **RestDocumentationRequestBuilders.get("/.../{id}", id)** |
| Bị báo tham số chưa được tài liệu hóa | URI template có biến mới nhưng thiếu descriptor | Thêm **parameterWithName(...)** đúng tên và mô tả nghiệp vụ |
| Bị báo tham số được mô tả không xuất hiện | Tên descriptor sai hoặc template thay đổi | So sánh từng tên trong **{...}** và **parameterWithName("...")** |
| Bài kiểm thử xanh nhưng không có file snippet | Chưa gắn REST Docs extension/filter hoặc chưa gọi **document(...)** | Kiểm tra cấu hình test client và lệnh sinh tài liệu |
| Asciidoctor báo thiếu **path-parameters.adoc** | Chưa chạy bài test hoặc đường dẫn **snippets** sai | Bảo đảm thứ tự **test → asciidoctor** và kiểm tra vị trí file |
| Tài liệu mô tả sai ý nghĩa của ID | Kiểm thử kiểm tra kỹ thuật, không hiểu nghiệp vụ | Review mô tả, dùng ví dụ và thêm các test theo hợp đồng API |

Để xác minh sau khi thay đổi endpoint, hãy chạy lại chính test sinh snippet, đọc **path-parameters.adoc** và kiểm tra bản HTML cuối cùng. Chỉ nhìn thấy test HTTP 200 là chưa đủ nếu phần **document(...)** không được thực thi.

## 9. Bài thực hành

Bạn có endpoint:

~~~http
GET /api/teams/12/members/34?includeInactive=false
~~~

Đường dẫn mẫu:

~~~text
/api/teams/{teamId}/members/{memberId}
~~~

Hãy viết bài kiểm thử sinh tài liệu gồm:

1. Kiểm tra request trả mã HTTP thành công và một trường trong JSON response.
2. Dùng **pathParameters(...)** mô tả **teamId** và **memberId**, với mô tả rõ ràng cho từng biến.
3. Tài liệu hóa riêng **includeInactive** là query parameter nếu endpoint hỗ trợ.
4. Sinh snippet có tên **team-member-get/path-parameters.adoc**, nhúng vào một tệp **index.adoc** và chạy lại build.
5. Thử xóa descriptor **memberId** hoặc đổi tên thành **id** để quan sát lỗi kiểm chứng, rồi khôi phục mã đúng.

Một lời giải phần path parameters:

~~~java
pathParameters(
    parameterWithName("teamId").description("Mã nhóm chứa thành viên"),
    parameterWithName("memberId").description("Mã thành viên trong nhóm")
)
~~~

**Tiêu chí hoàn thành:** bài kiểm thử HTTP thành công; snippet nêu đúng cả hai biến; trang tài liệu render được bảng path parameters; và trường hợp tài liệu thiếu biến được bài kiểm thử phát hiện.

## Ghi nhớ

**pathParameters(...)** biến các biến của URI template thành bảng tài liệu có khả năng được kiểm chứng qua bài kiểm thử. Dùng đúng builder và URI template, mô tả tất cả biến với **parameterWithName(...)**, giữ snippet nghiêm ngặt, rồi đưa kết quả vào Asciidoctor và CI để tài liệu REST API luôn bám sát hành vi đã được kiểm thử.

**Tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/) và [Spring REST Docs API](https://docs.spring.io/spring-restdocs/docs/current/api/).
