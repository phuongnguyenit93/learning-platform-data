# Phân biệt path parameter với query parameter

## Mục tiêu bài học

Trong một REST API, **path parameter** và **query parameter** đều được truyền qua URL, nhưng chúng nằm ở những vị trí khác nhau và phục vụ những mục đích khác nhau. Khi viết tài liệu với **Spring REST Docs**, phân biệt đúng hai nhóm này là điều kiện để sinh snippet chính xác từ bài kiểm thử HTTP.

Bài học thuộc module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng thông qua **MockMvc**, **WebTestClient** hoặc **REST Assured**, sau đó biên soạn snippet request, response, tham số vào **Asciidoctor/Markdown** và nối với quy trình build, CI.

Sau bài này, bạn có thể:

- Nhận biết path parameter và query parameter trong cùng một URL.
- Giải thích cách hai loại tham số ảnh hưởng đến **định tuyến** và **xử lý nghiệp vụ**.
- Phân biệt **@PathVariable** với **@RequestParam** trong Spring MVC.
- Tài liệu hóa cùng một request bằng **pathParameters(...)** và **queryParameters(...)** của Spring REST Docs.
- Mô tả đúng tham số truy vấn **bắt buộc**, **tùy chọn**, có **giá trị mặc định** hoặc **nhiều giá trị**.
- Kiểm thử những tình huống thiếu tham số; nhận diện lỗi thường gặp khi sinh snippet hoặc dựng tài liệu.

## 1. Phân tích một URL cụ thể

Xét request tìm sản phẩm:

~~~http
GET /api/stores/store-09/products?category=BOOK&page=1
Accept: application/json
~~~

Ứng dụng có thể định nghĩa URI template:

~~~text
/api/stores/{storeId}/products
~~~

Tách thành hai phần:

~~~text
GET /api/stores/store-09/products ? category=BOOK & page=1
    |-------------------------|   |--------------------|
         phần đường dẫn              phần truy vấn
    {storeId} = store-09         category = BOOK
                                 page = 1
~~~

**Path parameter** là giá trị được đặt vào một biến của mẫu đường dẫn, ví dụ **{storeId}**. **Query parameter** là cặp tên/giá trị trong chuỗi truy vấn sau ký tự **?**, chẳng hạn **category=BOOK** hoặc **page=1**.

| Đặc điểm | Path parameter | Query parameter |
| --- | --- | --- |
| Ví dụ | **/api/stores/{storeId}** | **?category=BOOK&page=1** |
| Vị trí | Trong các đoạn (segment) của đường dẫn | Phần query sau dấu **?** |
| Ký hiệu | Tên biến **{...}** trong URI template | **name=value**, các cặp thường cách nhau bởi **&** |
| Mục đích phổ biến | Xác định tài nguyên hoặc phạm vi tài nguyên | Lọc, sắp xếp, phân trang, chọn biểu diễn hoặc tùy chọn xử lý |
| Spring MVC | **@PathVariable** | **@RequestParam** |
| Spring REST Docs | **pathParameters(...)** | **queryParameters(...)** |
| Snippet thường sinh | **path-parameters.adoc** | **query-parameters.adoc** |
| Tính bắt buộc | Một biến thường phải có để khớp route chứa chính đoạn đó | Có thể bắt buộc, tùy chọn hoặc có giá trị mặc định tùy hợp đồng API |

Hai nhóm tham số có thể cùng xuất hiện trên một request, và việc có tên giống nhau không khiến chúng tương đương. Trong ví dụ trên, **storeId** xác định cửa hàng cần tìm kiếm, còn **category** và **page** điều khiển danh sách sản phẩm trả về.

## 2. Vì sao không thể thay thế hai loại tham số cho nhau?

### 2.1. Path parameter tham gia khớp đường dẫn

Với route:

~~~java
@GetMapping("/api/stores/{storeId}/products")
~~~

Request **GET /api/stores/store-09/products** có đoạn **store-09** ở đúng vị trí của **{storeId}**. Request **GET /api/stores/products** không khớp mẫu này vì thiếu đoạn dành cho ID cửa hàng. Việc thêm **?storeId=store-09** vào URL không tự thay thế đoạn đường dẫn bị thiếu.

Một controller khác có thể khai báo route **/api/stores/products**, nhưng đó là hợp đồng định tuyến khác. **@PathVariable(required = false)** không tự làm cho một đoạn URI đang có trong mẫu trở nên có thể bỏ qua.

### 2.2. Query parameter không tạo thêm đoạn đường dẫn

Với cùng route trên, cả hai URL sau đều có thể khớp một handler:

~~~http
GET /api/stores/store-09/products?category=BOOK
GET /api/stores/store-09/products?category=BOOK&page=1
~~~

**page** có thể là tùy chọn và mặc định bằng **0**. Ngược lại, **category** có thể bắt buộc nếu API yêu cầu phải nêu loại sản phẩm. Thiếu một query parameter bắt buộc không nhất thiết làm route không khớp: handler có thể đã được chọn nhưng bước **binding/validation** báo lỗi vì thiếu dữ liệu.

Điều này cũng có nghĩa **query parameter không phải lúc nào cũng tùy chọn**. Quy tắc bắt buộc phụ thuộc hợp đồng API và khai báo của ứng dụng.

### 2.3. Chọn path hay query khi thiết kế API?

Giả sử hệ thống có những tác vụ sau:

| Tác vụ | Gợi ý thiết kế URL | Lý do |
| --- | --- | --- |
| Xem đơn hàng có ID 42 | **GET /api/orders/42** | ID xác định tài nguyên đơn hàng |
| Xem dòng hàng 7 của đơn 42 | **GET /api/orders/42/lines/7** | Hai ID chỉ vị trí tài nguyên trong cấu trúc |
| Liệt kê đơn đang mở | **GET /api/orders?status=OPEN** | **status** là điều kiện lọc tập hợp |
| Đến trang 3, mỗi trang 20 dòng | **GET /api/orders?page=3&size=20** | Điều khiển cách lấy một phần danh sách |
| Lấy chi tiết đơn bằng ngôn ngữ tiếng Việt | **GET /api/orders/42?locale=vi** | Chọn cách biểu diễn một tài nguyên |

Đây là **quy ước thiết kế thường dùng**, không phải quy tắc tuyệt đối của HTTP. Một query parameter cũng có thể ảnh hưởng sâu đến kết quả nghiệp vụ; quan trọng là duy trì hợp đồng URL nhất quán, rõ ràng và được kiểm thử.

## 3. Liên kết tham số trong Spring MVC

Ví dụ sau kết hợp một path parameter bắt buộc với một query parameter bắt buộc và một query parameter tùy chọn có giá trị mặc định:

~~~java
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class StoreProductsController {

    @GetMapping("/api/stores/{storeId}/products")
    List<ProductResponse> listProducts(
            @PathVariable("storeId") String storeId,
            @RequestParam("category") String category,
            @RequestParam(value = "page", defaultValue = "0") int page) {
        return List.of(
            new ProductResponse("product-31", storeId, category, page)
        );
    }
}

record ProductResponse(
        String id, String storeId, String category, int page) {}
~~~

Trong ví dụ:

- **storeId** có trong mẫu **/api/stores/{storeId}/products** nên được liên kết bởi **@PathVariable("storeId")**.
- **category** được liên kết bởi **@RequestParam("category")**; mặc định **required = true**, vì vậy request thiếu **category** thường trả HTTP **400 Bad Request**.
- **page** cũng được liên kết bởi **@RequestParam**, nhưng **defaultValue = "0"** cho phép bỏ tham số khỏi URL và nhận giá trị **0**.

Các kết quả dưới đây giả định controller trên là mapping phù hợp duy nhất và ứng dụng không tùy chỉnh xử lý ngoại lệ:

| Request | Hành vi mong đợi |
| --- | --- |
| **/api/stores/store-09/products?category=BOOK&page=1** | HTTP 200; **storeId=store-09**, **category=BOOK**, **page=1** |
| **/api/stores/store-09/products?category=BOOK** | HTTP 200; **page** dùng mặc định **0** |
| **/api/stores/store-09/products?page=1** | HTTP 400 do thiếu query parameter **category** bắt buộc |
| **/api/stores/products?category=BOOK** | Không khớp route có **{storeId}**; thường trả HTTP 404 |
| **/api/stores/store-09/products?category=BOOK&page=abc** | Route khớp, nhưng chuyển **abc** thành **int** thường gây HTTP 400 |

Phân biệt ba lớp xử lý:

~~~mermaid
flowchart TD
    A["GET /api/stores/store-09/products?category=BOOK&page=1"] --> B{"Path khớp /api/stores/{storeId}/products?"}
    B -->|Không| C["Không vào handler này"]
    B -->|Có| D["Bind storeId từ path"]
    D --> E["Bind category và page từ query"]
    E --> F{"Thiếu giá trị bắt buộc / sai kiểu?"}
    F -->|Có| G["Trả lỗi, ví dụ HTTP 400"]
    F -->|Không| H["Gọi handler, tạo response"]
~~~

**@RequestParam** của Spring MVC còn có thể lấy dữ liệu từ request parameters trong một số kiểu request khác, như form data. Do đó, tên annotation không tự nói rằng tham số luôn nằm trên query string. Khi tài liệu hóa **HTTP query string**, Spring REST Docs sử dụng **queryParameters(...)**; với form request, hãy sử dụng cơ chế tài liệu hóa form parameters phù hợp với phiên bản REST Docs.

## 4. Spring REST Docs: hai nhóm snippet cho một request

Để mô tả URL **/api/stores/store-09/products?category=BOOK&page=1**, dùng **pathParameters(...)** cho **storeId** và **queryParameters(...)** cho **category**, **page**:

~~~java
pathParameters(
    parameterWithName("storeId")
        .description("Mã cửa hàng chứa sản phẩm")
),
queryParameters(
    parameterWithName("category")
        .description("Loại sản phẩm cần tìm; ví dụ BOOK"),
    parameterWithName("page")
        .description("Chỉ số trang, bắt đầu từ 0; mặc định 0")
        .optional()
)
~~~

Cả hai snippet đều dùng **parameterWithName(...)**, nhưng chính hàm bao ngoài xác định loại dữ liệu được tài liệu hóa:

~~~java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
~~~

**pathParameters(...)** đối chiếu descriptor với các tên biến thuộc URI template. **queryParameters(...)** đối chiếu descriptor với tham số nằm trong query string. Mỗi nhóm tạo một tệp snippet tương ứng khi truyền vào **document(...)**.

**Lưu ý phiên bản:** ví dụ trong bài sử dụng API **queryParameters(...)** của Spring REST Docs phiên bản hiện đại (3.x). Trong một số tài liệu hoặc dự án REST Docs đời cũ, bạn có thể gặp **requestParameters(...)**. Khi nâng cấp, hãy kiểm tra API tương ứng vì tham số truy vấn và tham số form được phân biệt trong phiên bản mới.

### 4.1. Vì sao page dùng optional() còn category thì không?

API yêu cầu **category** để chọn loại sản phẩm; vì vậy descriptor của nó không đánh dấu tùy chọn. **page** có giá trị mặc định ở controller nên mô tả bằng **optional()** là phù hợp: test với URL không có **page** vẫn có thể sinh tài liệu của endpoint.

Chú ý rằng **optional()** trong Spring REST Docs chỉ điều chỉnh **tính bắt buộc đối với việc kiểm tra tài liệu**. Nó không thay đổi **@RequestParam(required = ...)**, không cấp giá trị mặc định và không làm thay đổi hành vi của controller. Khi cập nhật hợp đồng API, cần đồng bộ cả code xử lý, bài kiểm thử và descriptor.

### 4.2. Vì sao không nên dùng relaxed...() theo thói quen?

REST Docs có các biến thể kiểm tra không nghiêm ngặt, chẳng hạn **relaxedPathParameters(...)** và **relaxedQueryParameters(...)**. Chúng có thể cho phép bỏ sót những tham số chưa mô tả mà test sinh snippet vẫn chạy, tùy trường hợp.

Nếu mục tiêu là **tài liệu REST API có thể kiểm chứng**, ưu tiên các hàm nghiêm ngặt **pathParameters(...)** và **queryParameters(...)** với danh sách descriptor đầy đủ. Khi ai đó bổ sung query parameter mới, bài kiểm thử tài liệu sẽ nhắc đội phát triển cập nhật hợp đồng thay vì bỏ qua một thay đổi quan trọng.

## 5. Ví dụ đầy đủ với MockMvc

Ví dụ dưới dùng **Java 17+**, **Spring Boot 3.x**, **JUnit 5**, **spring-restdocs-mockmvc** và controller ở mục 3. Cấu hình dependency Gradle tối thiểu khi dự án đã dùng Spring Boot BOM/dependency management:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Tạo **StoreProductsDocumentationTest.java** trong cùng package với controller:

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
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(StoreProductsController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class StoreProductsDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentPathAndQueryParameters() throws Exception {
        mockMvc.perform(
                get("/api/stores/{storeId}/products", "store-09")
                    .queryParam("category", "BOOK")
                    .queryParam("page", "1")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].storeId").value("store-09"))
            .andExpect(jsonPath("$[0].category").value("BOOK"))
            .andExpect(jsonPath("$[0].page").value(1))
            .andDo(document("store-products-get",
                pathParameters(
                    parameterWithName("storeId")
                        .description("Mã cửa hàng chứa sản phẩm")
                ),
                queryParameters(
                    parameterWithName("category")
                        .description("Loại sản phẩm cần tìm; ví dụ BOOK"),
                    parameterWithName("page")
                        .description("Chỉ số trang, bắt đầu từ 0; mặc định 0")
                        .optional()
                )
            ));
    }

    @Test
    void pageIsOptionalAndDefaultsToZero() throws Exception {
        mockMvc.perform(
                get("/api/stores/{storeId}/products", "store-09")
                    .queryParam("category", "BOOK"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].page").value(0));
    }

    @Test
    void categoryIsRequired() throws Exception {
        mockMvc.perform(
                get("/api/stores/{storeId}/products", "store-09")
                    .queryParam("page", "1"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Trong bài kiểm thử này, có hai chi tiết dễ bị nhầm:

1. **get("/api/stores/{storeId}/products", "store-09")** là request builder của **Spring REST Docs**, cho phép giữ URI template để nhận diện tên **storeId**. Gọi **get("/api/stores/store-09/products")** với URL đã mở rộng không cung cấp cùng thông tin template.
2. **.queryParam("category", "BOOK")** và **.queryParam("page", "1")** đưa giá trị lên query string của request. Đây là lựa chọn rõ ràng khi cần snippet **queryParameters(...)**. Đừng nhầm với **.param(...)**, vì thao tác đặt request parameter không nhất thiết biểu diễn cùng một query string.

Bài kiểm thử thứ nhất xác nhận HTTP 200, các giá trị JSON và sinh hai snippet; hai bài kiểm thử còn lại xác nhận ý nghĩa nghiệp vụ của **page** tùy chọn và **category** bắt buộc. Riêng Spring REST Docs không tự kiểm tra tính đúng đắn nghiệp vụ của nội dung **description(...)** hoặc giá trị mặc định **0**; các assert vẫn cần được viết.

### 5.1. Những tệp được sinh

Sau khi chạy test, thư mục ví dụ sẽ có:

~~~text
build/
└── generated-snippets/
    └── store-products-get/
        ├── curl-request.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        ├── path-parameters.adoc
        └── query-parameters.adoc
~~~

Đây là danh sách rút gọn; cấu hình và phiên bản có thể sinh thêm snippet mặc định. Hai bảng tài liệu được sinh có nội dung tương đương như sau:

**Path parameters**

| Parameter | Description |
| --- | --- |
| **storeId** | Mã cửa hàng chứa sản phẩm |

**Query parameters**

| Parameter | Description |
| --- | --- |
| **category** | Loại sản phẩm cần tìm; ví dụ BOOK |
| **page** | Chỉ số trang, bắt đầu từ 0; mặc định 0 |

Không chỉnh sửa trực tiếp các tệp trong **generated-snippets**: chúng là sản phẩm được sinh lại từ bài kiểm thử. Mô tả cần được sửa ở **parameterWithName(...).description(...)** trong test.

## 6. Một số tình huống query parameter cần chú ý

### 6.1. Tham số có thể xuất hiện nhiều lần

Ví dụ:

~~~http
GET /api/articles?tag=java&tag=spring
~~~

Nếu ứng dụng nhận nhiều tag bằng **@RequestParam List<String> tag**, đây vẫn là một **tên query parameter là tag**, xuất hiện nhiều lần trong query string. Mô tả tài liệu một descriptor cho tên đó:

~~~java
queryParameters(
    parameterWithName("tag")
        .description("Nhãn lọc bài viết; được phép truyền nhiều lần")
        .optional()
)
~~~

Không tạo hai descriptor trùng tên chỉ vì request có hai giá trị **java** và **spring**. Cần có test xác nhận cách controller xử lý các giá trị lặp, vì **queryParameters(...)** không tự xác thực quy tắc gom, sắp xếp hay loại trùng của chúng.

### 6.2. Tham số có mặt nhưng rỗng khác tham số vắng mặt

So sánh:

~~~text
/api/search
/api/search?q=
/api/search?q=java
~~~

Ba request có thể có ý nghĩa khác nhau nếu API phân biệt *không truyền*, *truyền chuỗi rỗng*, và *truyền nội dung*. **optional()** trong REST Docs không quyết định chính sách xử lý những giá trị này; controller cần chỉ rõ quy tắc và có bài kiểm thử tương ứng.

### 6.3. URL encoding và dữ liệu nhạy cảm

Giá trị query chứa khoảng trắng, **&**, **=** hoặc các ký tự đặc biệt cần được mã hóa theo quy tắc URI. Ví dụ, nếu muốn truyền tìm kiếm **A&B** làm một giá trị, client phải mã hóa dấu **&** thuộc về giá trị để nó không bị hiểu là dấu phân cách tham số.

Tương tự, path segment có dấu **/** hoặc ký tự dành riêng cần được thiết kế và mã hóa cẩn thận. Cả path lẫn query đều là một phần của URL, có thể xuất hiện trong log và lịch sử truy cập; không đặt mật khẩu, access token hoặc bí mật vào hai vị trí này.

## 7. Cùng một ý tưởng với WebTestClient và REST Assured

Những test client khác vẫn dùng **pathParameters(...)** và **queryParameters(...)**; khác biệt nằm ở cách tạo request và gắn bộ sinh tài liệu.

### 7.1. WebTestClient

Với **WebTestClient** đã được cấu hình REST Docs, ví dụ qua **documentationConfiguration(...)**:

~~~java
webTestClient.get()
    .uri("/api/stores/{storeId}/products?category=BOOK&page=1", "store-09")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("store-products-webtestclient",
        pathParameters(
            parameterWithName("storeId")
                .description("Mã cửa hàng")
        ),
        queryParameters(
            parameterWithName("category")
                .description("Loại sản phẩm cần tìm"),
            parameterWithName("page")
                .description("Chỉ số trang, mặc định 0")
                .optional()
        )
    ));
~~~

Ở đây **document(...)** thuộc **WebTestClientRestDocumentation**. Giá trị **store-09** được truyền vào URI template; **category** và **page** ở query string. Trong dự án thực tế, nên sử dụng API tạo URI của client để encode query values phức tạp đúng cách.

### 7.2. REST Assured

Với **RequestSpecification spec** đã cấu hình Spring REST Docs:

~~~java
given(spec)
    .filter(document("store-products-rest-assured",
        pathParameters(
            parameterWithName("storeId")
                .description("Mã cửa hàng")
        ),
        queryParameters(
            parameterWithName("category")
                .description("Loại sản phẩm cần tìm"),
            parameterWithName("page")
                .description("Chỉ số trang, mặc định 0")
                .optional()
        )
    ))
    .pathParam("storeId", "store-09")
    .queryParam("category", "BOOK")
    .queryParam("page", 1)
    .when()
    .get("/api/stores/{storeId}/products")
    .then()
    .statusCode(200);
~~~

Ở ví dụ REST Assured, **document(...)** thuộc **RestAssuredRestDocumentation**. **pathParam(...)** cung cấp giá trị của biến đường dẫn, còn **queryParam(...)** tạo query parameter; hai nhóm descriptor tài liệu hóa tương ứng.

## 8. Biên soạn tài liệu và đưa vào build/CI

Ví dụ tệp **src/docs/asciidoc/index.adoc** sử dụng snippet được sinh:

~~~asciidoc
= Store Products API
:toc: left

== Danh sách sản phẩm theo cửa hàng

GET /api/stores/{storeId}/products?category=BOOK&page=1

=== Path parameters

include::{snippets}/store-products-get/path-parameters.adoc[]

=== Query parameters

include::{snippets}/store-products-get/query-parameters.adoc[]

=== HTTP request

include::{snippets}/store-products-get/http-request.adoc[]

=== HTTP response

include::{snippets}/store-products-get/http-response.adoc[]
~~~

Ví dụ trên giả định build truyền thuộc tính **snippets** trỏ đến **build/generated-snippets**. Nếu sử dụng **Gradle** với plugin **org.asciidoctor.jvm.convert** đã được cài đặt:

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

Với cấu hình trên, tác vụ Asciidoctor phụ thuộc vào việc chạy test và nhận đường dẫn tới snippets. Trong **CI**, chạy kiểm thử trước khi dựng và xuất bản tài liệu. Nếu đổi tên biến **{storeId}** hoặc bổ sung query parameter nhưng không cập nhật mô tả, kiểm tra snippet nghiêm ngặt có thể giúp phát hiện hợp đồng tài liệu bị lệch.

Nếu sản phẩm cuối dùng **Markdown**, cần bước chuyển đổi hoặc cách nhúng snippet phù hợp với công cụ dựng Markdown đang dùng. Cú pháp **include::...[]** là chỉ thị của **Asciidoctor**, không phải cú pháp Markdown tiêu chuẩn.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| **storeId** không được REST Docs nhận diện | Dùng URL cố định thay vì URI template trong test MockMvc | Dùng **RestDocumentationRequestBuilders.get("/.../{storeId}", value)** |
| **queryParameters(...)** không thấy tham số | Test chỉ đặt request parameter, không tạo query string tương ứng | Với MockMvc, ưu tiên **.queryParam(name, value)** |
| Path parameter bị báo thiếu | Quên **parameterWithName("storeId")** | Khai báo đúng tên biến trong path template |
| Query parameter bị báo thiếu | Request thêm **category** hoặc **page** nhưng không mô tả | Bổ sung descriptor trong **queryParameters(...)** |
| Gọi **/api/stores/products?storeId=store-09** không tìm được route | Đã chuyển ID từ path thành query nhưng mapping vẫn chứa **/{storeId}** | Gửi đúng URL theo contract hoặc thiết kế mapping khác |
| Thiếu **category** trả HTTP 400 | Controller yêu cầu query parameter này | Truyền category hoặc sửa hợp đồng để nó tùy chọn |
| Thiếu **page** vẫn thành công | Controller có **defaultValue = "0"** | Tài liệu hóa page tùy chọn và ghi giá trị mặc định |
| Không tìm thấy **query-parameters.adoc** khi dựng trang | Test không sinh snippet hoặc đường dẫn **snippets** chưa đúng | Kiểm tra **document(...)**, kết quả test và thiết lập Asciidoctor |
| Mô tả **page** là bắt đầu từ 1 trong khi code mặc định 0 | Tài liệu sai ý nghĩa nghiệp vụ | Sửa **description(...)** và thêm assert xác nhận giá trị mặc định |

## 10. Bài thực hành

Thiết kế endpoint lấy danh sách giao dịch của một tài khoản:

~~~http
GET /api/accounts/12/transactions?type=DEBIT&page=2&size=10
~~~

Hợp đồng đề xuất:

- **accountId** nằm trong URI template **/api/accounts/{accountId}/transactions** và chỉ tài khoản sở hữu giao dịch.
- **type** là query parameter bắt buộc, xác định loại giao dịch.
- **page** là query parameter tùy chọn, mặc định **0**.
- **size** là query parameter tùy chọn, mặc định **20**.

Yêu cầu thực hành:

1. Viết controller với **@PathVariable("accountId")**, **@RequestParam("type")**, **@RequestParam(defaultValue = "0")** cho **page** và **@RequestParam(defaultValue = "20")** cho **size**.
2. Viết test MockMvc cho URL đầy đủ, assert HTTP 200 và một vài giá trị từ response.
3. Gắn **document(...)** với **pathParameters(...)** và **queryParameters(...)**, sinh hai snippet **path-parameters.adoc** và **query-parameters.adoc** dưới thư mục **account-transactions-get**.
4. Kiểm thử thiếu **page/size** để xác nhận mặc định; kiểm thử thiếu **type** để xác nhận lỗi do query parameter bắt buộc.
5. Thử truyền **?accountId=12** nhưng bỏ đoạn **/12** trong path; giải thích tại sao request không tự khớp route chi tiết.
6. Nhúng cả hai snippet vào tài liệu Asciidoctor và kiểm tra thứ tự thực thi test trước khi dựng HTML.

Lời giải phần descriptor:

~~~java
pathParameters(
    parameterWithName("accountId")
        .description("Mã tài khoản sở hữu giao dịch")
),
queryParameters(
    parameterWithName("type")
        .description("Loại giao dịch bắt buộc, ví dụ DEBIT hoặc CREDIT"),
    parameterWithName("page")
        .description("Chỉ số trang bắt đầu từ 0, mặc định 0")
        .optional(),
    parameterWithName("size")
        .description("Số giao dịch tối đa trên một trang, mặc định 20")
        .optional()
)
~~~

**Tiêu chí hoàn thành:** phân loại chính xác bốn tham số; controller xử lý đúng trường hợp bắt buộc/tùy chọn; bài kiểm thử xác nhận status và dữ liệu; hai bảng snippet chứa đúng tên tham số, vai trò và giá trị mặc định.

## Ghi nhớ

**Path parameter** là biến nằm trong mẫu đường dẫn, thường dùng để nhận diện tài nguyên và cần xuất hiện ở vị trí tương ứng để khớp route. **Query parameter** nằm sau dấu **?**, thường điều khiển việc lọc, phân trang hoặc biểu diễn kết quả; nó có thể bắt buộc hoặc tùy chọn theo hợp đồng API. Trong Spring REST Docs, mô tả chúng bằng **pathParameters(...)** và **queryParameters(...)** trong bài kiểm thử HTTP để tạo các snippet tách biệt, rồi đưa snippet vào tài liệu Asciidoctor/Markdown cùng quy trình build và CI.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs RequestDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/RequestDocumentation.html), [Spring MVC @RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html) và [Spring MVC @PathVariable](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/pathvariable.html).
