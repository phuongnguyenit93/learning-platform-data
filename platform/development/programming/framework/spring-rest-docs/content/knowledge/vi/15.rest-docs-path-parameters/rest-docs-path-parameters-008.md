# Xác nhận tên parameter khớp route thực tế

## Mục tiêu bài học

Một bài kiểm thử Spring REST Docs có thể sinh được bảng path parameters nhưng tài liệu vẫn sai nếu **tên biến trong descriptor, URI template dùng để tạo request và route thực tế của controller không thống nhất**. Ví dụ controller khai báo `/api/orders/{orderId}`, nhưng test lại dùng template `/api/orders/{id}` và descriptor `parameterWithName("orderId")`. Một bài test tốt cần phát hiện được sự lệch này trước khi tài liệu được đưa vào build hoặc CI.

Bài học thuộc module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng từ test HTTP với **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet request, response, payload, tham số và header; biên soạn tài liệu Asciidoctor/Markdown và đưa vào quy trình build, CI.

Sau bài này, bạn có thể:

- Phân biệt tên biến trong **controller mapping**, **URI template của request test** và **descriptor REST Docs**.
- Hiểu giới hạn kiểm chứng của `pathParameters(...)`: nó đối chiếu descriptor với thông tin URI template của request được tài liệu hóa.
- Viết test gọi controller thật để phát hiện route hoặc tên biến đã thay đổi.
- Phát hiện các lỗi sai tên, thiếu descriptor, descriptor thừa, sai tiền tố path và mapping không tương thích.
- Xây dựng helper hoặc quy ước dùng chung để giảm tình trạng đổi tên một nơi nhưng quên nơi khác.
- Sinh snippet ổn định, ghép vào Asciidoctor và bảo đảm CI chạy kiểm thử trước khi dựng tài liệu.

## 1. Ba nơi cần đồng bộ tên biến

Giả sử API lấy thông tin đơn hàng:

~~~java
@GetMapping("/api/orders/{orderId}")
OrderResponse getOrder(@PathVariable("orderId") Long orderId) {
    // ...
}
~~~

Để tạo tài liệu đúng, ba nơi sau phải nhất quán:

| Nơi khai báo | Ví dụ đúng | Trách nhiệm |
| --- | --- | --- |
| Mapping của controller | `/api/orders/{orderId}` | Định nghĩa route được Spring ánh xạ |
| URI template trong HTTP test | `get("/api/orders/{orderId}", 42L)` | Tạo request có biến mang tên `orderId` |
| Descriptor REST Docs | `parameterWithName("orderId")` | Mô tả biến được hiển thị trong snippet |

Ở controller, `@PathVariable("orderId")` gắn biến Java với tên trong đường dẫn. Ở bài kiểm thử, **RestDocumentationRequestBuilders.get(...)** giữ URI template để Spring REST Docs biết tên biến. Descriptor **parameterWithName("orderId")** mô tả chính tên đó.

Luồng kiểm tra:

~~~mermaid
flowchart TD
    A["Controller mapping: /api/orders/{orderId}"] --> B["MockMvc request template: /api/orders/{orderId}"]
    B --> C["Spring chọn handler và bind orderId"]
    C --> D["document(..., pathParameters(...))"]
    D --> E["REST Docs đối chiếu descriptor với request template"]
    E --> F["path-parameters.adoc"]
    C --> G["HTTP status và response assertions"]
    G --> H["Test xác nhận route thực sự chạy đúng"]
~~~

Điểm cần nhớ: **REST Docs nhìn thấy URI template của request được truyền cho test client; nó không tự đọc source code controller để so sánh mọi chuỗi mapping**. Chính việc test thực sự gửi request qua Spring MVC/WebFlux và xác nhận response giúp kiểm tra route đang được triển khai. Vì vậy cần kết hợp descriptor validation và các assertion HTTP.

## 2. Ví dụ đúng với MockMvc

Ví dụ sử dụng **Spring Boot 3.x**, **Java 17+**, **JUnit 5** và **spring-restdocs-mockmvc**. Controller:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/api/orders/{orderId}")
    OrderResponse getOrder(@PathVariable("orderId") Long orderId) {
        return new OrderResponse(orderId, "OPEN");
    }
}

record OrderResponse(Long id, String status) {}
~~~

Bài kiểm thử:

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

@WebMvcTest(OrderController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentGetOrder() throws Exception {
        mockMvc.perform(get("/api/orders/{orderId}", 42L)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.status").value("OPEN"))
            .andDo(document("order-get",
                pathParameters(
                    parameterWithName("orderId")
                        .description("Mã định danh đơn hàng")
                )
            ));
    }
}
~~~

Test sử dụng **RestDocumentationRequestBuilders.get(...)** thay cho builder MockMvc thông thường để lưu lại URI template. Request chạy qua handler Spring thật, assert status và response, sau đó mới tạo snippet. Do đó test có khả năng phát hiện nếu route không còn khớp hoặc handler trả kết quả khác hợp đồng.

## 3. Khi tên biến bị lệch

### 3.1. Template test dùng tên khác controller

Giả sử controller vẫn là:

~~~java
@GetMapping("/api/orders/{orderId}")
OrderResponse getOrder(@PathVariable("orderId") Long orderId) {
    // ...
}
~~~

Nhưng test viết:

~~~java
mockMvc.perform(get("/api/orders/{id}", 42L))
~~~

Tên `id` trong request template không giống tên biến của mapping. Khi chạy, Spring MVC vẫn có thể khớp route theo vị trí và bind giá trị vào mapping của controller, tùy cách xử lý placeholder của framework; tuy nhiên URI template mà REST Docs nhận được mang tên **id**. Nếu descriptor lại là:

~~~java
pathParameters(
    parameterWithName("orderId").description("Mã đơn hàng")
)
~~~

REST Docs sẽ phát hiện descriptor không khớp với tên biến trong template request; snippet có thể thất bại với lỗi parameter không tồn tại hoặc biến request chưa được mô tả, tùy phiên bản và trường hợp cụ thể.

**Cách sửa:** dùng cùng tên `orderId` trong URI template test và descriptor. Không dựa vào việc request tình cờ vẫn được route vào controller để kết luận tài liệu đã chính xác.

### 3.2. Descriptor sai tên hoặc thừa descriptor

Mapping và test template đều dùng `{orderId}`, nhưng descriptor ghi:

~~~java
pathParameters(
    parameterWithName("id").description("Mã đơn hàng")
)
~~~

Tên `id` không có trong template. Với `pathParameters(...)` ở chế độ mặc định nghiêm ngặt, REST Docs báo lỗi vì descriptor không tương ứng với path parameter của request.

Tương tự, nếu template có `{orderId}` và `{lineId}` nhưng test chỉ mô tả `orderId`, tham số `lineId` bị thiếu tài liệu hóa. Khai báo đầy đủ:

~~~java
pathParameters(
    parameterWithName("orderId").description("Mã đơn hàng"),
    parameterWithName("lineId").description("Mã dòng hàng trong đơn")
)
~~~

### 3.3. Tên biến Java không nhất thiết là tên URI

Tên tham số Java có thể khác với tên biến URI nếu annotation chỉ rõ ánh xạ:

~~~java
@GetMapping("/api/orders/{orderId}")
OrderResponse getOrder(@PathVariable("orderId") Long id) {
    return new OrderResponse(id, "OPEN");
}
~~~

Trong trường hợp này descriptor vẫn là:

~~~java
parameterWithName("orderId").description("Mã đơn hàng")
~~~

Không dùng `parameterWithName("id")` chỉ vì biến Java tên `id`. Tài liệu path parameters mô tả **tên trong URI template**, không mô tả tên biến cục bộ của Java.

## 4. Mapping đổi nhưng test cũ vẫn còn

Một lỗi phổ biến khi refactor là đổi mapping:

~~~java
@GetMapping("/api/purchases/{purchaseId}")
PurchaseResponse getPurchase(
        @PathVariable("purchaseId") Long purchaseId) {
    // ...
}
~~~

nhưng test chưa đổi:

~~~java
get("/api/orders/{orderId}", 42L)
~~~

Nếu chỉ kiểm tra descriptor dựa trên template cũ, test tài liệu có thể vẫn tạo được snippet theo **orderId** nhưng request không còn gọi đúng route hiện tại; thường sẽ nhận 404. Test cần assert status thành công và các trường response có ý nghĩa để bắt lỗi này.

Khi thay đổi route, cập nhật đồng bộ:

1. Mapping của controller.
2. Annotation `@PathVariable` nếu tên biến đổi.
3. URI template trong test.
4. Các descriptor `parameterWithName(...)`.
5. Tên snippet hoặc phần include trong tài liệu nếu mã định danh snippet thay đổi.
6. Test liên quan đến routing, quyền truy cập và quan hệ tài nguyên.

Tên snippet như **order-get** là định danh do nhóm phát triển lựa chọn; nó không tự được REST Docs suy ra từ URL. Nếu đổi snippet ID thành **purchase-get**, hãy cập nhật đường dẫn **include** trong Asciidoctor.

## 5. Xác nhận đúng route và đúng quan hệ path parameter

Với endpoint lồng nhau:

~~~text
/api/orders/{orderId}/lines/{lineId}
~~~

Controller có thể bind:

~~~java
@GetMapping("/api/orders/{orderId}/lines/{lineId}")
OrderLineResponse getLine(
        @PathVariable("orderId") Long orderId,
        @PathVariable("lineId") Long lineId) {
    return service.getLine(orderId, lineId);
}
~~~

Test cần mô tả đủ cả hai biến:

~~~java
mockMvc.perform(get(
        "/api/orders/{orderId}/lines/{lineId}",
        42L, 7L))
    .andExpect(status().isOk())
    .andDo(document("order-line-get",
        pathParameters(
            parameterWithName("orderId")
                .description("Mã đơn hàng chứa dòng hàng"),
            parameterWithName("lineId")
                .description("Mã dòng hàng cần lấy trong đơn")
        )
    ));
~~~

Nhưng route match và snippet chính xác chưa chứng minh **lineId 7 thuộc orderId 42**. Service/repository phải truy vấn theo cả hai khóa hoặc kiểm tra quan hệ trước khi trả dữ liệu. Hãy thêm test cho những tình huống:

| Dữ liệu | Hành vi cần xác nhận |
| --- | --- |
| Đơn 42 có dòng 7 | Trả thành công |
| Đơn 42 không có dòng 7 | Không trả dữ liệu của dòng khác |
| Dòng 7 thuộc đơn 99, request dùng đơn 42 | Trả lỗi theo hợp đồng (thường 404) |
| Đơn 42 không tồn tại | Trả lỗi không tìm thấy theo hợp đồng |
| Thiếu segment `lineId` | Không khớp route chi tiết nếu không có route khác |

Việc kiểm chứng quan hệ tài nguyên là trách nhiệm của test nghiệp vụ, không phải chức năng của `pathParameters(...)`.

## 6. Dùng helper chung để giảm sai lệch

Với API có nhiều test cho cùng route, có thể gom phần URI template và descriptor vào một hằng số hoặc helper trong test:

~~~java
private static final String ORDER_URI =
    "/api/orders/{orderId}";

private static PathParametersSnippet orderPathParameters() {
    return pathParameters(
        parameterWithName("orderId")
            .description("Mã định danh đơn hàng")
    );
}
~~~

Khi dùng:

~~~java
mockMvc.perform(get(ORDER_URI, 42L))
    .andExpect(status().isOk())
    .andDo(document("order-get", orderPathParameters()));
~~~

Ví dụ cần static import:

~~~java
import org.springframework.restdocs.request.PathParametersSnippet;

import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
~~~

Một helper dùng chung giảm lặp lại chuỗi và description, nhưng **không tự bảo đảm controller mapping luôn trùng** với hằng số trong test. Hãy đảm bảo test gọi ứng dụng đã khởi tạo, assert HTTP status và response, đồng thời tổ chức test theo endpoint để người review có thể nhận ra khi mapping đổi.

Không nên xây dựng một cơ chế reflection phức tạp chỉ để đọc annotation controller và tự sinh descriptor nếu dự án chưa có nhu cầu rõ ràng. Cách đó làm tăng độ phức tạp và có thể che mất việc test chưa thực sự gọi route đúng.

## 7. Giữ test request, descriptor và tài liệu cùng một hợp đồng

Với mỗi endpoint, dùng một quy ước thống nhất:

| Thành phần | Nguồn chuẩn cần kiểm tra |
| --- | --- |
| HTTP method và route | Annotation mapping hoặc functional route của ứng dụng |
| Tên biến đường dẫn | Placeholder trong URI template |
| Giá trị test | Giá trị phù hợp với kiểu và quy tắc nghiệp vụ |
| Descriptor | Tên placeholder và mô tả dành cho người gọi API |
| Assertion | Status, response, validation và các điều kiện nghiệp vụ |
| Snippet ID | Tên duy nhất, ổn định để tài liệu include |
| Trang Asciidoctor | Đường dẫn snippet và mô tả endpoint tương ứng |

Một bài test tài liệu nên có ít nhất:

- Một request hợp lệ gọi được route thực tế.
- Assertion status và một số trường quan trọng của response.
- Descriptor đầy đủ cho các biến path.
- Test riêng cho dữ liệu sai kiểu, thiếu biến hoặc sai quan hệ nghiệp vụ nếu đó là hành vi cần công bố.

Với endpoint có query parameter hoặc header, tài liệu hóa đúng nhóm tương ứng:

~~~java
document("order-get",
    pathParameters(
        parameterWithName("orderId").description("Mã đơn hàng")
    ),
    queryParameters(
        parameterWithName("includeLines")
            .description("Có trả danh sách dòng hàng hay không")
            .optional()
    ),
    requestHeaders(
        headerWithName("Accept")
            .description("Kiểu dữ liệu response được client chấp nhận")
    )
)
~~~

Đoạn mở rộng trên cần static import các API **queryParameters(...)**, **requestHeaders(...)** và **headerWithName(...)** tương ứng. Nó cho thấy một request có thể có nhiều nhóm thông tin được tài liệu hóa; không đưa query parameter hay header vào `pathParameters(...)`.

## 8. Kiểm thử với WebTestClient và REST Assured

Nguyên tắc đồng bộ tên biến vẫn giống với MockMvc: URI template của request phải khớp route đang được test, descriptor phải dùng tên placeholder.

### 8.1. WebTestClient

Trong test đã cấu hình tích hợp Spring REST Docs:

~~~java
webTestClient.get()
    .uri("/api/orders/{orderId}", 42L)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("order-webtestclient",
        pathParameters(
            parameterWithName("orderId")
                .description("Mã định danh đơn hàng")
        )
    ));
~~~

Ở đây **document(...)** được import từ **WebTestClientRestDocumentation**. Client cần được thiết lập với cấu hình REST Docs trước khi gọi test. Assert HTTP status thành công giúp xác nhận request đã khớp một handler phù hợp.

### 8.2. REST Assured

Với **RequestSpecification spec** đã được cấu hình REST Docs:

~~~java
given(spec)
    .filter(document("order-rest-assured",
        pathParameters(
            parameterWithName("orderId")
                .description("Mã định danh đơn hàng")
        )
    ))
    .pathParam("orderId", 42L)
    .when()
    .get("/api/orders/{orderId}")
    .then()
    .statusCode(200);
~~~

Ở đây **document(...)** được import từ **RestAssuredRestDocumentation**. **pathParam("orderId", 42L)** gán giá trị request; **parameterWithName("orderId")** mô tả tên placeholder. `spec` cần được thiết lập filter và cấu hình REST Docs tương ứng.

## 9. Tích hợp snippet với Asciidoctor và CI

Sau khi test chạy, snippet có thể được đặt dưới:

~~~text
build/generated-snippets/order-get/
├── path-parameters.adoc
├── http-request.adoc
└── http-response.adoc
~~~

Trong **src/docs/asciidoc/index.adoc**:

~~~asciidoc
= Orders API
:toc: left

== Lấy đơn hàng

GET /api/orders/{orderId}

=== Path parameters

include::{snippets}/order-get/path-parameters.adoc[]

=== HTTP request

include::{snippets}/order-get/http-request.adoc[]

=== HTTP response

include::{snippets}/order-get/http-response.adoc[]
~~~

Ví dụ cấu hình Gradle Groovy DSL, giả định plugin **org.asciidoctor.jvm.convert** đã được thêm:

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

Trong CI, luồng cần có:

1. Biên dịch và chạy các test REST Docs.
2. Dừng build nếu route không khớp, assertion thất bại hoặc snippet không sinh được.
3. Chạy Asciidoctor sau khi snippets đã có.
4. Chỉ xuất bản tài liệu khi các bước cần thiết thành công.

Nếu tài liệu đầu ra là Markdown, dùng bộ chuyển đổi hoặc cách nhúng snippet phù hợp; chỉ thị `include::...[]` thuộc Asciidoctor, không phải cú pháp Markdown tiêu chuẩn.

## 10. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| REST Docs báo descriptor không tồn tại | Tên trong `parameterWithName(...)` khác URI template | Dùng đúng tên placeholder, kể cả chữ hoa/thường |
| Request chạy nhưng snippet không sinh | Chưa gọi `document(...)`, sai cấu hình hoặc thiếu template URI | Dùng request builder REST Docs và kiểm tra cấu hình |
| Test trả 404 sau khi đổi mapping | URI test chưa cập nhật | Đồng bộ template test với route mới |
| Test trả 400 khi path chứa chữ thay vì số | Binding sang kiểu Long thất bại | Dùng giá trị đúng kiểu và test riêng trường hợp sai |
| Tài liệu hiển thị tên biến cũ | Descriptor hoặc test template chưa được cập nhật | Cập nhật cả mapping, request template và descriptor |
| Thiếu một dòng trong bảng path parameters | Quên mô tả một biến của route nhiều cấp | Thêm descriptor cho từng placeholder |
| Snippet tạo được nhưng trả sai tài nguyên con | Service chỉ kiểm tra ID con | Kiểm tra quan hệ cha–con theo cả hai ID |
| Asciidoctor báo thiếu snippet | Snippet ID trong include không trùng document ID | Đồng bộ tên ở `document(...)` và `include::...` |

## 11. Bài thực hành

Cho controller hiện có route:

~~~text
GET /api/projects/{projectId}/tasks/{taskId}
~~~

Hãy thực hiện:

1. Viết controller dùng **@PathVariable("projectId")** và **@PathVariable("taskId")**.
2. Tạo bài kiểm thử MockMvc với **RestDocumentationRequestBuilders.get("/api/projects/{projectId}/tasks/{taskId}", 12L, 34L)**.
3. Assert HTTP status và các trường **projectId**, **taskId** trong JSON response.
4. Gọi **document("project-task-get", pathParameters(...))** với hai descriptor có tên chính xác là **projectId** và **taskId**.
5. Thử đổi template test thành **/api/projects/{id}/tasks/{taskId}** nhưng giữ descriptor **projectId**; giải thích lỗi REST Docs có thể báo.
6. Thử đổi mapping controller thành **/api/workspaces/{projectId}/tasks/{taskId}** nhưng không cập nhật test; xác nhận assertion thành công thất bại do route cũ không còn tồn tại.
7. Kiểm tra service không trả task thuộc project khác.
8. Nhúng snippet vào Asciidoctor và chạy thứ tự test → asciidoctor.

Mẫu descriptor:

~~~java
pathParameters(
    parameterWithName("projectId")
        .description("Mã dự án sở hữu công việc"),
    parameterWithName("taskId")
        .description("Mã công việc trong dự án")
)
~~~

**Tiêu chí hoàn thành:** template test khớp route được triển khai; descriptor khớp tên placeholder; request thực tế trả response đúng; trường hợp sai tên và sai mapping được phát hiện; tài liệu được dựng từ snippet do test tạo ra.

## Ghi nhớ

Để xác nhận tên parameter khớp route thực tế, hãy đồng bộ **placeholder trong mapping**, **URI template của HTTP test** và **tên trong parameterWithName(...)**. Spring REST Docs đối chiếu descriptor với URI template của request; test gọi controller thực tế và assert status/response mới xác nhận route đang hoạt động đúng. Với route lồng nhau, kiểm tra thêm quan hệ giữa ID cha và ID con. Tích hợp các bài test này vào build/CI để thay đổi route mà quên cập nhật tài liệu được phát hiện trước khi xuất bản.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs RequestDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/RequestDocumentation.html), [Spring MVC @PathVariable](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/pathvariable.html) và [Spring MVC URI patterns](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html).
