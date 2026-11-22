# parameterWithName cho biến trong URI

## Mục tiêu

Trong **Spring REST Docs**, tài liệu REST API được sinh từ các bài kiểm thử HTTP đã chạy với **MockMvc**, **WebTestClient** hoặc **REST Assured**. Khi cần tài liệu hóa biến trên đường dẫn, chúng ta dùng **parameterWithName(...)** bên trong **pathParameters(...)**. Kết quả là bảng tham số có thể được kiểm tra về độ khớp với URI template của request, sau đó đưa vào tài liệu Asciidoctor và quy trình build/CI.

Sau bài học này, bạn có thể:

- Xác định chính xác tên biến trong URI template, phân biệt tên biến với giá trị thực tế.
- Viết một **parameterWithName("...")** cho từng biến, kèm mô tả có ích cho người dùng API.
- Dùng các descriptor trong bài kiểm thử MockMvc để sinh **path-parameters.adoc**.
- Phát hiện các lỗi khai báo sai tên, khai báo thừa hoặc thiếu biến.
- Hiểu khi nào cần **ignored()**, vì sao phải thận trọng với **optional()** và **relaxedPathParameters(...)**.
- Tái sử dụng cách mô tả biến đường dẫn với WebTestClient/REST Assured, nhúng snippet vào tài liệu và CI.

## 1. Biến trong URI là gì?

Giả sử API trả thông tin một sản phẩm tại một cửa hàng:

~~~http
GET /api/stores/store-09/products/product-31
Accept: application/json
~~~

Trong mã nguồn, đường dẫn thường được định nghĩa bằng **URI template**:

~~~text
/api/stores/{storeId}/products/{productId}
~~~

| Thành phần | Vai trò |
| --- | --- |
| **/api/stores/**, **/products/** | Các phần đường dẫn cố định, không phải biến |
| **{storeId}** | Tên biến chỉ cửa hàng |
| **{productId}** | Tên biến chỉ sản phẩm |
| **store-09** | Giá trị gắn vào **storeId** trong request ví dụ |
| **product-31** | Giá trị gắn vào **productId** trong request ví dụ |

Ký hiệu **{storeId}** được dùng trong template để nhận diện một vị trí biến; dấu ngoặc nhọn không xuất hiện trong URL cuối cùng gửi tới máy chủ.

Điểm cần phân biệt:

- **@PathVariable("storeId")** trong Spring MVC lấy giá trị từ request để xử lý nghiệp vụ.
- **parameterWithName("storeId")** trong Spring REST Docs khai báo cách **tài liệu hóa** đúng tên biến này.
- **pathParameters(...)** tập hợp các khai báo đó thành một *snippet* tham số đường dẫn.

Vì vậy, tên được đưa vào **parameterWithName(...)** là **storeId**, không phải **{storeId}**, **store-09**, hay tên tham số Java tình cờ khác với tên trong URL.

## 2. Cú pháp parameterWithName(...) và vị trí sử dụng

Khai báo cơ bản:

~~~java
pathParameters(
    parameterWithName("storeId")
        .description("Mã cửa hàng chứa sản phẩm"),
    parameterWithName("productId")
        .description("Mã sản phẩm cần tra cứu trong cửa hàng")
)
~~~

Cần static import hai phương thức:

~~~java
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
~~~

**parameterWithName(name)** tạo một descriptor cho tham số mang **name**. Phương thức **description(...)** gắn mô tả nghiệp vụ, còn **pathParameters(...)** xác định rằng các descriptor này thuộc **đường dẫn URI**. Khai báo trên sẽ tạo nội dung cho snippet **path-parameters.adoc** khi được truyền vào **document(...)** trong bài kiểm thử có tích hợp REST Docs.

Đặc điểm quan trọng:

1. **Tên có phân biệt chữ hoa/chữ thường**: **storeId** và **storeID** là hai tên khác nhau.
2. **Mỗi biến có một descriptor tương ứng**: nếu URI template chứa **{storeId}** và **{productId}**, hãy mô tả cả hai.
3. **Mô tả phải nói lên ý nghĩa**: “Mã cửa hàng chứa sản phẩm” hữu ích hơn “storeId”.
4. **Descriptor không tự kiểm tra kiểu hay định dạng**: việc viết “UUID” trong mô tả không khiến REST Docs tự từ chối giá trị sai định dạng.
5. **Nơi sử dụng quyết định loại tham số**: cùng API **parameterWithName(...)** có thể được dùng cho snippet của nhóm tham số khác; chính **pathParameters(...)** xác định đây là *path parameters*.

Đừng nhầm với query parameter. Trong URL **/api/stores/store-09/products?limit=20**, **limit** nằm sau dấu **?**, nên không phải biến đường dẫn và không được mô tả trong **pathParameters(...)**.

## 3. Ví dụ đầy đủ: controller và bài kiểm thử MockMvc

Ví dụ bên dưới giả định dự án **Spring Boot 3.x**, **Java 17+**, **JUnit 5**, và có các dependency kiểm thử:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Spring Boot BOM/dependency management có thể quản lý phiên bản cho các thư viện này. Với dự án Maven, thêm các dependency tương ứng và dùng thư mục snippet ở **target/generated-snippets**.

### 3.1. Controller mẫu

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductLocationController {

    @GetMapping("/api/stores/{storeId}/products/{productId}")
    ProductLocation getProduct(
            @PathVariable("storeId") String storeId,
            @PathVariable("productId") String productId) {
        return new ProductLocation(storeId, productId, "AVAILABLE");
    }
}

record ProductLocation(String storeId, String productId, String status) {}
~~~

Request **GET /api/stores/store-09/products/product-31** trả về JSON ví dụ:

~~~json
{
  "storeId": "store-09",
  "productId": "product-31",
  "status": "AVAILABLE"
}
~~~

Controller minh họa chỉ trả dữ liệu cố định; trong ứng dụng thực tế, logic tìm kiếm sản phẩm thường nằm ở service. Phần cần quan sát ở bài này là tên biến trong **@GetMapping** và cách chúng khớp với descriptor.

### 3.2. Kiểm thử HTTP và ghi tài liệu

Đặt test ở cùng package với controller để ví dụ truy cập được lớp package-private:

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

@WebMvcTest(ProductLocationController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductLocationDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentProductWithinStore() throws Exception {
        mockMvc.perform(
                get("/api/stores/{storeId}/products/{productId}",
                    "store-09", "product-31")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.storeId").value("store-09"))
            .andExpect(jsonPath("$.productId").value("product-31"))
            .andDo(document("product-location-get",
                pathParameters(
                    parameterWithName("storeId")
                        .description("Mã cửa hàng chứa sản phẩm"),
                    parameterWithName("productId")
                        .description("Mã sản phẩm cần tra cứu")
                )
            ));
    }
}
~~~

Ở đây có ba chi tiết quyết định:

- **RestDocumentationRequestBuilders.get(...)** giữ thông tin URI template để Spring REST Docs nhận biết tên **storeId** và **productId**. Với MockMvc, đây là cách trực tiếp và rõ ràng để tài liệu hóa biến đường dẫn.
- **get("/.../{storeId}/.../{productId}", "store-09", "product-31")** dùng lần lượt hai giá trị thực tế cho hai vị trí biến. Các giá trị này giúp request chạy, nhưng *tên* để viết tài liệu vẫn là **storeId** và **productId**.
- **andDo(document(..., pathParameters(...)))** sinh snippet sau khi request được thực hiện; bài kiểm thử còn xác nhận cả status và dữ liệu trả về.

Nếu viết request với đường dẫn cố định **get("/api/stores/store-09/products/product-31")** thì thông tin template có thể không còn cho Spring REST Docs nhận diện hai tên biến như mong muốn. Hãy dùng request builder dành cho tài liệu hóa URI template.

### 3.3. Snippet đầu ra

Khi chạy bài kiểm thử thành công, Spring REST Docs tạo các tệp dưới thư mục:

~~~text
build/
└── generated-snippets/
    └── product-location-get/
        ├── http-request.adoc
        ├── http-response.adoc
        ├── curl-request.adoc
        └── path-parameters.adoc
~~~

Đây là cấu trúc minh họa rút gọn; REST Docs có thể sinh thêm các snippet mặc định tùy cấu hình. Trong **path-parameters.adoc**, thông tin quan trọng là bảng có hai dòng tương ứng:

| Parameter | Description |
| --- | --- |
| **storeId** | Mã cửa hàng chứa sản phẩm |
| **productId** | Mã sản phẩm cần tra cứu |

Các tên và mô tả này lấy từ bài kiểm thử, không nên chỉnh sửa thủ công trong thư mục **generated-snippets**, vì chúng sẽ được sinh lại ở lần chạy test tiếp theo.

## 4. Quy tắc khớp tên giữa URI template và descriptor

Spring REST Docs cần xác định được những biến có mặt trên URI template và những descriptor mà bạn khai báo. Trong chế độ tài liệu hóa nghiêm ngặt, việc khai báo thiếu biến hoặc mô tả một biến không có trong request có thể làm bước sinh snippet thất bại.

| URI template và khai báo | Đánh giá |
| --- | --- |
| **{storeId}** ↔ **parameterWithName("storeId")** | Khớp |
| **{storeId}** ↔ **parameterWithName("storeID")** | Sai chữ hoa/chữ thường |
| **{storeId}** ↔ **parameterWithName("{storeId}")** | Sai vì chứa cả dấu ngoặc nhọn |
| **{storeId}** ↔ **parameterWithName("store-09")** | Sai vì dùng giá trị thay cho tên |
| **{storeId}**, **{productId}**, chỉ khai báo **storeId** | Thiếu mô tả **productId** |
| Chỉ có **{storeId}**, khai báo thêm **productId** | Khai báo tên không tồn tại trong template |

Ví dụ sai:

~~~java
get("/api/stores/{storeId}/products/{productId}",
        "store-09", "product-31")
// ...
pathParameters(
    parameterWithName("storeId").description("Mã cửa hàng"),
    parameterWithName("id").description("Mã sản phẩm")
)
~~~

Tên **id** không trùng với **productId**. Cách sửa đúng là thay descriptor thứ hai bằng **parameterWithName("productId")**; không cần đổi giá trị **product-31** trong request.

Một điểm dễ nhầm: **tên biến trong URL** phải khớp tên descriptor, còn **tên tham số Java** không nhất thiết phải giống nếu controller đã chỉ rõ tên liên kết:

~~~java
@GetMapping("/api/stores/{storeId}")
String getStore(@PathVariable("storeId") String id) {
    return id;
}
~~~

Ở trường hợp này, descriptor vẫn là **parameterWithName("storeId")** chứ không phải **parameterWithName("id")**, bởi URI template sử dụng **{storeId}**.

## 5. Viết description như một hợp đồng API

Giá trị lớn nhất của **parameterWithName(...)** nằm ở mô tả dễ hiểu và ổn định. Hãy ghi cụ thể dữ liệu nhận diện điều gì, nó thuộc phạm vi nào và định dạng có ràng buộc gì.

| Mô tả khó hiểu | Mô tả hữu ích |
| --- | --- |
| “ID” | “Mã đơn hàng cần truy vấn” |
| “userId” | “UUID định danh người dùng cần lấy thông tin” |
| “Code” | “Mã kho hàng, phân biệt chữ hoa/chữ thường” |
| “Số của item” | “Số thứ tự của dòng hàng trong đơn, bắt đầu từ 1” |

Ví dụ endpoint dùng UUID:

~~~text
GET /api/users/{userId}
~~~

~~~java
pathParameters(
    parameterWithName("userId")
        .description("UUID định danh người dùng; ví dụ: "
            + "550e8400-e29b-41d4-a716-446655440000")
)
~~~

Đây chỉ là **mô tả**. Để kiểm tra UUID hợp lệ, bạn cần thêm ràng buộc ở ứng dụng và test đường dẫn hợp lệ/không hợp lệ. REST Docs không tự xác minh giá trị thuộc định dạng UUID chỉ dựa trên chuỗi trong **description(...)**.

Với các mã mà giá trị trong URL có ký tự đặc biệt, client cần mã hóa URI đúng quy tắc. Ví dụ **/tasks/{taskId}** với giá trị chứa khoảng trắng phải được mã hóa thích hợp; phần mô tả parameter không thay thế việc kiểm tra URL encoding. Đặc biệt, ký tự **/** bên trong ID có thể bị hiểu là ranh giới giữa hai path segment; cần thiết kế đường dẫn và cơ chế mã hóa nhất quán, không giả định ID nào cũng có thể đưa trực tiếp vào một segment.

Không đưa token bí mật, mật khẩu hay dữ liệu nhạy cảm vào ví dụ path parameters: URL thường được ghi trong access log, lịch sử trình duyệt và hệ thống quan sát.

## 6. ignored(), optional() và relaxedPathParameters(...)

### 6.1. Bỏ một biến khỏi bảng bằng ignored()

Đôi khi một biến kỹ thuật đã có ở URI nhưng tài liệu dành cho người dùng không cần hiển thị. **ignored()** đánh dấu descriptor là đã được nhận biết nhưng bỏ qua khi tạo bảng:

~~~java
pathParameters(
    parameterWithName("tenantId").ignored(),
    parameterWithName("orderId")
        .description("Mã đơn hàng trong tenant hiện tại")
)
~~~

Điều này phù hợp nếu endpoint thực sự có template **/api/tenants/{tenantId}/orders/{orderId}**, còn khái niệm **tenantId** đã được diễn giải tại phần dùng chung của tài liệu. Không dùng **ignored()** để che giấu một tham số mà người gọi phải biết cách truyền.

### 6.2. Ý nghĩa của optional()

**optional()** đánh dấu descriptor không bắt buộc xuất hiện trong *request được tài liệu hóa*. Tuy nhiên, một biến trên một route cụ thể như **/orders/{orderId}** thường là bắt buộc để route đó khớp. Gắn **optional()** vào descriptor **không** thay đổi quy tắc định tuyến của Spring MVC và không làm cho **@PathVariable** tự trở thành tùy chọn.

Nếu một tài nguyên hỗ trợ cả **/orders** và **/orders/{orderId}**, nên mô tả và kiểm thử **hai endpoint** riêng. Việc gắn **optional()** nhằm che lỗi thiếu biến sẽ làm sai ý nghĩa hợp đồng API.

### 6.3. Tài liệu hóa không nghiêm ngặt

**relaxedPathParameters(...)** là lựa chọn cho phép một số biến có trong request nhưng chưa được liệt kê trong tài liệu. Dù tiện khi áp dụng dần REST Docs cho dự án cũ, nó có thể khiến biến đường dẫn mới bị bỏ sót mà bài kiểm thử vẫn chạy. Với API công khai hoặc khi cần tài liệu có khả năng kiểm chứng chặt chẽ, ưu tiên **pathParameters(...)** và mô tả đầy đủ.

## 7. Áp dụng nguyên tắc tương tự với các HTTP test client

Các ví dụ bên dưới là phần trích trong test đã **cấu hình tích hợp Spring REST Docs** cho HTTP client tương ứng; các import và bước khởi tạo client cần bổ sung theo loại test.

### WebTestClient

~~~java
webTestClient.get()
    .uri("/api/stores/{storeId}/products/{productId}",
        "store-09", "product-31")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("product-location-webtestclient",
        pathParameters(
            parameterWithName("storeId").description("Mã cửa hàng"),
            parameterWithName("productId").description("Mã sản phẩm")
        )
    ));
~~~

Ở đây **document(...)** thuộc **WebTestClientRestDocumentation**. Client phải có cấu hình REST Docs, ví dụ qua **documentationConfiguration(...)**. Nguyên tắc đặt tên biến không đổi.

### REST Assured

~~~java
given(spec)
    .filter(document("product-location-rest-assured",
        pathParameters(
            parameterWithName("storeId").description("Mã cửa hàng"),
            parameterWithName("productId").description("Mã sản phẩm")
        )
    ))
    .pathParam("storeId", "store-09")
    .pathParam("productId", "product-31")
    .when()
    .get("/api/stores/{storeId}/products/{productId}")
    .then()
    .statusCode(200);
~~~

Ở đây **document(...)** thuộc **RestAssuredRestDocumentation**, còn **spec** là **RequestSpecification** đã thiết lập REST Docs. Hai lời gọi **pathParam(...)** gán giá trị request; hai lời gọi **parameterWithName(...)** mô tả tên biến trên template.

## 8. Tái sử dụng descriptor để tránh mô tả không nhất quán

Nếu nhiều endpoint đều dùng **{storeId}** với cùng nghĩa, có thể dùng chung hàm tạo descriptor:

~~~java
import org.springframework.restdocs.request.ParameterDescriptor;

import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

static ParameterDescriptor storeIdParameter() {
    return parameterWithName("storeId")
        .description("Mã cửa hàng chứa tài nguyên");
}
~~~

Trong mỗi test:

~~~java
pathParameters(
    storeIdParameter(),
    parameterWithName("productId").description("Mã sản phẩm")
)
~~~

Cách này giữ mô tả nhất quán ở những route dùng chung hợp đồng. Nếu ý nghĩa **{storeId}** khác nhau giữa các API, ưu tiên mô tả cụ thể theo ngữ cảnh. Một hàm tạo descriptor mới ở mỗi lần gọi cũng giúp hạn chế thay đổi trạng thái descriptor khi test sử dụng các tùy chọn như **ignored()**.

## 9. Đưa bảng path parameters vào Asciidoctor và CI

Với file **src/docs/asciidoc/index.adoc**, có thể nhúng snippet:

~~~asciidoc
= Product Location API
:toc: left

== Tra cứu sản phẩm theo cửa hàng

GET /api/stores/{storeId}/products/{productId}

=== Path parameters

include::{snippets}/product-location-get/path-parameters.adoc[]

=== Request

include::{snippets}/product-location-get/http-request.adoc[]

=== Response

include::{snippets}/product-location-get/http-response.adoc[]
~~~

Ví dụ này giả định build đã truyền thuộc tính **snippets** đến Asciidoctor, trỏ đến thư mục **build/generated-snippets**. Với Gradle và plugin Asciidoctor JVM đã được thiết lập, các tác vụ thường được nối bằng quan hệ:

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

Trong CI, chạy kiểm thử sinh snippet trước bước dựng tài liệu và xuất bản chỉ khi toàn bộ bước cần thiết thành công. Như vậy, nếu đổi **{productId}** thành **{sku}** ở endpoint mà quên sửa descriptor, bài kiểm thử tài liệu sẽ giúp phát hiện sự không khớp trước khi trang mới được tạo.

Spring REST Docs sinh snippet AsciiDoc theo cấu hình mặc định. Nếu dự án xuất bản Markdown, cần cơ chế chuyển đổi hoặc mẫu sinh snippet tương thích; cú pháp **include::{snippets}/...[]** là cú pháp Asciidoctor, không phải cú pháp Markdown tiêu chuẩn.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Không nhận diện được path parameter | Request dùng URL cố định hoặc không lưu URI template | Dùng **RestDocumentationRequestBuilders** cho MockMvc với URL có **{...}** |
| Descriptor bị báo thừa | **parameterWithName(...)** không khớp biến nào | Đối chiếu tên trong template, bỏ dấu ngoặc nhọn trong descriptor |
| Biến bị báo chưa tài liệu hóa | Thiếu một **parameterWithName(...)** | Thêm descriptor và mô tả nghiệp vụ tương ứng |
| Bảng sinh ra đúng tên nhưng khó hiểu | Mô tả chỉ lặp lại tên kỹ thuật | Bổ sung vai trò, phạm vi, định dạng và ví dụ khi cần |
| Không có **path-parameters.adoc** | Chưa thực thi **document(...)** hoặc REST Docs chưa cấu hình | Kiểm tra extension/filter/annotation của test và đường dẫn đầu ra |
| Asciidoctor không tìm thấy snippet | Test chưa chạy hoặc thuộc tính **snippets** không đúng | Cho tác vụ Asciidoctor phụ thuộc test, kiểm tra đường dẫn generated-snippets |
| Một biến có tên khác với tên tham số Java | **@PathVariable** đã ánh xạ tên khác | Lấy tên từ URI template, không suy từ tên biến Java |

## 11. Bài tập thực hành

Cho URI template:

~~~text
/api/teams/{teamId}/members/{memberId}/permissions/{permissionCode}
~~~

Request kiểm thử:

~~~http
GET /api/teams/team-2/members/user-8/permissions/READ
~~~

Yêu cầu:

1. Tạo bài kiểm thử HTTP với đúng ba biến của URI template, kiểm tra status và dữ liệu trả về.
2. Dùng **pathParameters(...)** với ba descriptor **parameterWithName(...)**. Mô tả **teamId** là mã nhóm, **memberId** là mã thành viên trong nhóm, **permissionCode** là mã quyền được tra cứu.
3. Sinh snippet **team-member-permission-get/path-parameters.adoc** và nhúng vào tài liệu Asciidoctor.
4. Thử đổi **parameterWithName("memberId")** thành **parameterWithName("userId")**; dự đoán nguyên nhân bài kiểm thử tài liệu báo lỗi.
5. Thêm test xác nhận API xử lý đúng khi **permissionCode** không tồn tại; giải thích vì sao chỉ mô tả tên tham số không tự kiểm thử hành vi này.

Lời giải phần descriptor:

~~~java
pathParameters(
    parameterWithName("teamId")
        .description("Mã nhóm chứa thành viên"),
    parameterWithName("memberId")
        .description("Mã thành viên cần kiểm tra quyền trong nhóm"),
    parameterWithName("permissionCode")
        .description("Mã quyền cần tra cứu, ví dụ READ hoặc WRITE")
)
~~~

Đánh giá bài thực hành theo bốn tiêu chí: đúng **tên** ba biến, đúng **ý nghĩa** từng biến, test sinh được **path-parameters.adoc**, và thay đổi sai tên descriptor làm tài liệu bị phát hiện không khớp.

## Tóm tắt

**parameterWithName("tênBiến")** là khai báo cho một tên tham số xuất hiện trong URI template. Đặt nó trong **pathParameters(...)** để tài liệu hóa biến đường dẫn; dùng **description(...)** để truyền đạt vai trò và ràng buộc nghiệp vụ. Khi gắn vào bài kiểm thử HTTP đã cấu hình Spring REST Docs, khai báo này giúp tạo snippet có thể kiểm chứng và đưa vào Asciidoctor/Markdown cùng pipeline build, CI.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/) và [RequestDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/RequestDocumentation.html).
