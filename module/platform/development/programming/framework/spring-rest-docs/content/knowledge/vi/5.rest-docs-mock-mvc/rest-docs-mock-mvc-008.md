# Document nhiều operation trong một test

## Mục tiêu

Với **MockMvc** và **Spring REST Docs**, một bài kiểm thử có thể gửi nhiều HTTP request bằng nhiều lệnh `mockMvc.perform(...)`. Mỗi request có thể đại diện cho một **operation** riêng trong API, chẳng hạn lấy danh sách, lấy chi tiết và tạo tài nguyên. Để tài liệu hóa đầy đủ, cần gọi **document(...)** sau từng request và cấp cho từng operation một **snippet identifier** riêng.

Bài học thuộc module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng từ HTTP test bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, payload, tham số và header; biên soạn Asciidoctor/Markdown và đưa vào quy trình build, CI.

Sau bài học, bạn có thể:

- Thực hiện nhiều request MockMvc trong cùng một phương thức test.
- Gắn **document(...)** vào từng kết quả `ResultActions` để sinh snippet riêng.
- Đặt tên operation có ý nghĩa và tránh trùng snippet identifier.
- Tài liệu hóa các method hoặc endpoint khác nhau mà không trộn request/response của chúng.
- Tách phần setup, assertion và descriptor để test vẫn dễ đọc.
- Nhúng nhiều nhóm snippet vào Asciidoctor và bảo đảm CI sinh đủ tài liệu.

## 1. Một operation tương ứng với một lần thực hiện HTTP

Giả sử API quản lý đơn hàng hỗ trợ:

| Operation | HTTP request | Mục đích |
| --- | --- | --- |
| Liệt kê đơn hàng | `GET /api/orders` | Lấy danh sách |
| Xem đơn hàng | `GET /api/orders/{orderId}` | Lấy một đơn hàng |
| Tạo đơn hàng | `POST /api/orders` | Tạo tài nguyên mới |

Trong MockMvc, mỗi request được thực thi qua một lệnh **`mockMvc.perform(...)`**. Spring REST Docs gắn việc sinh snippet vào kết quả của request bằng **`andDo(document(...))`**:

~~~java
mockMvc.perform(get("/api/orders"))
    .andExpect(status().isOk())
    .andDo(document("orders-list"));

mockMvc.perform(get("/api/orders/{orderId}", 42L))
    .andExpect(status().isOk())
    .andDo(document("order-get"));
~~~

Hai lần gọi **`document(...)`** dùng identifier khác nhau, nên snippet của danh sách nằm trong thư mục **`orders-list`**, còn snippet chi tiết nằm trong **`order-get`**.

Điểm quan trọng: **một test method có thể chứa nhiều operation, nhưng mỗi operation cần được document tại chính request tương ứng**. Chỉ gọi `document(...)` một lần ở request cuối thì REST Docs chỉ tạo snippet cho request cuối đó; nó không tự thu thập các request trước trong cùng method.

## 2. Identifier riêng cho từng operation

Tham số đầu tiên của **`document("...")`** là tên định danh snippet. Ví dụ:

~~~java
document("orders-list")
document("order-get")
document("order-create")
~~~

Kết quả thường được tạo dưới:

~~~text
build/generated-snippets/
├── orders-list/
├── order-get/
└── order-create/
~~~

Trong mỗi thư mục có thể chứa `http-request.adoc`, `http-response.adoc`, `curl-request.adoc` và những snippet khác được bật hoặc khai báo.

| Cách đặt identifier | Đánh giá |
| --- | --- |
| `orders-list`, `order-get`, `order-create` | Rõ ràng, thể hiện operation |
| `test1`, `test2`, `result` | Khó hiểu khi đọc tài liệu và build output |
| Dùng cùng `order` cho GET và POST | Dễ ghi vào cùng vị trí snippet, gây nhầm lẫn hoặc ghi đè |
| `orders-list-v1`, `orders-list-v2` | Có ích khi thực sự tài liệu hóa hai contract khác nhau |

Nếu hai request gọi **cùng identifier**, chúng ghi vào cùng vùng output. Tùy cấu hình snippet writer và cách chạy test, nội dung có thể bị ghi thay thế hoặc gây xung đột. Không dùng identifier trùng để gom nhiều operation: hãy tạo tên riêng cho từng operation.

## 3. Ví dụ hoàn chỉnh: nhiều operation trong một test method

Ví dụ dưới đây dùng **Java 17+**, **Spring Boot 3.x**, **JUnit 5** và **spring-restdocs-mockmvc**. Các dependency test trong Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Spring Boot dependency management/BOM có thể quản lý phiên bản tương thích. Controller mẫu có ba operation:

~~~java
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/api/orders")
    List<OrderResponse> listOrders() {
        return List.of(new OrderResponse(42L, "OPEN"));
    }

    @GetMapping("/api/orders/{orderId}")
    OrderResponse getOrder(@PathVariable("orderId") Long orderId) {
        return new OrderResponse(orderId, "OPEN");
    }

    @PostMapping("/api/orders")
    @ResponseStatus(HttpStatus.CREATED)
    OrderResponse createOrder(@RequestBody CreateOrderRequest request) {
        return new OrderResponse(43L, request.description());
    }
}

record OrderResponse(Long id, String status) {}
record CreateOrderRequest(String description) {}
~~~

Để minh họa cách sinh tài liệu, controller trả dữ liệu cố định. Ứng dụng thực tế sẽ dùng service/repository để đọc và ghi dữ liệu.

### 3.1. Test chứa ba request và ba lần document

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderOperationsDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentListGetAndCreateOperations() throws Exception {
        // Operation 1: GET collection
        mockMvc.perform(get("/api/orders")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].id").value(42))
            .andDo(document("orders-list"));

        // Operation 2: GET one resource
        mockMvc.perform(get("/api/orders/{orderId}", 42L)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.status").value("OPEN"))
            .andDo(document("order-get"));

        // Operation 3: POST create resource
        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "description": "OPEN"
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value(43))
            .andDo(document("order-create"));
    }
}
~~~

Trong method trên:

- **Request thứ nhất** gửi GET đến collection và sinh snippet **orders-list**.
- **Request thứ hai** gửi GET đến một resource, truyền path variable **orderId** và sinh snippet **order-get**.
- **Request thứ ba** gửi POST với JSON body, nhận HTTP 201 và sinh snippet **order-create**.

Mỗi lệnh `perform(...)` có assertion riêng và có một lệnh `andDo(document(...))` tương ứng. Kết quả là ba bộ request/response được ghi độc lập. Nếu bỏ `document("orders-list")`, thao tác GET danh sách vẫn được test nhưng không sinh bộ snippet tài liệu cho operation đó.

### 3.2. Mô tả path parameter và request fields

Với GET chi tiết, có thể thêm descriptor path parameter:

~~~java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;

// Thay andDo(document("order-get")) bằng:
.andDo(document("order-get",
    pathParameters(
        parameterWithName("orderId")
            .description("Mã đơn hàng cần tra cứu")
    )
));
~~~

Với POST, mô tả JSON body bằng **requestFields(...)**:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;

.andDo(document("order-create",
    requestFields(
        fieldWithPath("description")
            .description("Nội dung mô tả đơn hàng")
    )
));
~~~

Đặt các descriptor này vào đúng lệnh **`document(...)`** của operation tương ứng. Không đưa `orderId` vào POST collection vì request đó không có path variable; cũng không đưa trường body `description` vào `pathParameters(...)`.

### 3.3. Response fields theo từng operation

Nếu muốn mô tả JSON response, có thể thêm **responseFields(...)** riêng:

~~~java
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

.andDo(document("order-get",
    pathParameters(
        parameterWithName("orderId")
            .description("Mã đơn hàng cần tra cứu")
    ),
    responseFields(
        fieldWithPath("id").description("Mã đơn hàng"),
        fieldWithPath("status").description("Trạng thái đơn hàng")
    )
));
~~~

Response của GET danh sách là một mảng, nên descriptor cần mô tả cấu trúc phần tử, ví dụ **`[]._id`** không phải đường dẫn field chuẩn nếu tên field thực tế là **id**. Với payload JSON mảng các object, dùng **`[].id`** và **`[].status`** theo cú pháp field path của Spring REST Docs:

~~~java
responseFields(
    fieldWithPath("[].id").description("Mã đơn hàng"),
    fieldWithPath("[].status").description("Trạng thái đơn hàng")
)
~~~

Mỗi operation có response contract riêng. Không sao chép nguyên danh sách response field của GET detail sang GET list hoặc POST nếu cấu trúc trả về khác nhau.

## 4. Phân biệt nhiều operation trong một test với nhiều test method

Bạn có thể gom nhiều request vào một test method, như ví dụ ở trên. Tuy nhiên, **không bắt buộc** mọi operation phải nằm chung một method. Tách thành nhiều test method thường phù hợp hơn khi mỗi operation có setup, dữ liệu hoặc điều kiện kiểm thử khác nhau.

| Tiêu chí | Nhiều operation trong một method | Một operation mỗi method |
| --- | --- | --- |
| Setup | Có thể dùng chung dữ liệu và fixture | Có thể lặp setup hoặc dùng helper |
| Khả năng đọc | Thấy một luồng request liên tiếp | Mỗi test tập trung vào một hành vi |
| Khi test fail | Có thể dừng ở operation đầu gây lỗi | Chỉ method liên quan thất bại |
| Tài liệu REST Docs | Vẫn cần identifier riêng từng lần document | Identifier riêng từng test |
| Phù hợp | Luồng liên quan chặt chẽ, setup chung | Operation độc lập hoặc có nhiều kịch bản |

**Khuyến nghị:** gom các request khi chúng tạo thành một kịch bản có ý nghĩa và setup chung thực sự hữu ích. Nếu GET list, GET detail và POST create có thể kiểm thử độc lập, ba test method riêng thường dễ bảo trì hơn. Dù chọn cách nào, vẫn document từng request riêng.

## 5. Tổ chức helper để giảm lặp

Nếu nhiều operation dùng chung cấu hình hoặc descriptor, tạo helper nhỏ trong test:

~~~java
private static PathParametersSnippet orderIdParameter() {
    return pathParameters(
        parameterWithName("orderId")
            .description("Mã đơn hàng cần tra cứu")
    );
}
~~~

Các import cần thiết:

~~~java
import org.springframework.restdocs.request.PathParametersSnippet;

import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
~~~

Khi đó:

~~~java
mockMvc.perform(get("/api/orders/{orderId}", 42L))
    .andExpect(status().isOk())
    .andDo(document("order-get", orderIdParameter()));
~~~

Helper chỉ nên gom phần mô tả hoặc setup lặp lại, không nên che khuất request, assertion và identifier. Người đọc test vẫn cần nhận ra:

- Request dùng HTTP method và URI nào.
- Operation được lưu bằng identifier nào.
- Assertion nào chứng minh response đúng.
- Descriptor nào được đưa vào snippet.

## 6. Những lỗi thường gặp khi document nhiều operation

### 6.1. Chỉ document operation cuối

Ví dụ:

~~~java
mockMvc.perform(get("/api/orders"))
    .andExpect(status().isOk());

mockMvc.perform(get("/api/orders/{orderId}", 42L))
    .andExpect(status().isOk())
    .andDo(document("order-get"));
~~~

Test có hai request nhưng chỉ GET detail được tài liệu hóa. Hãy gắn **`andDo(document(...))`** vào lần `perform` thứ nhất nếu cần tài liệu cho GET collection.

### 6.2. Dùng chung snippet identifier

~~~java
mockMvc.perform(get("/api/orders"))
    .andDo(document("order"));

mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"description\":\"OPEN\"}"))
    .andDo(document("order"));
~~~

GET và POST ghi cùng tên **order** dù request/response khác nhau. Hãy dùng **orders-list** và **order-create**, rồi include đúng thư mục trong tài liệu.

### 6.3. Thiếu descriptor tương ứng với operation

Nếu GET detail có path parameter mà test chỉ gọi `document("order-get")`, snippet path parameters sẽ không được sinh. Thêm **pathParameters(...)** khi operation có biến đường dẫn. Ngược lại, không khai báo descriptor không hiện diện trong request template.

### 6.4. Setup dữ liệu phụ thuộc thứ tự

Nếu POST tạo đơn hàng rồi GET đọc đơn vừa tạo, test có thể phụ thuộc vào thứ tự thực thi và trạng thái dùng chung. Đảm bảo test có dữ liệu xác định, hoặc dùng kết quả ID từ response POST để tạo GET tiếp theo trong cùng kịch bản. Tránh để một test method dựa vào dữ liệu tồn tại do một test method khác tạo ra; thứ tự test không nên trở thành điều kiện ngầm của suite.

### 6.5. Snippet cũ còn sót

Khi đổi tên identifier từ **order** sang **order-get**, cần cập nhật cả **`include::...`** trong Asciidoctor và đảm bảo build dùng output snippets của lần test hiện tại. Snippet cũ còn lại trên đĩa có thể khiến tài liệu vẫn dựng được dù test mới không sinh đúng nội dung bạn nghĩ.

## 7. WebTestClient và REST Assured

Bài học tập trung vào MockMvc, nhưng nguyên tắc **mỗi operation có một lần document riêng và identifier riêng** áp dụng tương tự với các test client khác.

### WebTestClient

~~~java
webTestClient.get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders-list-webtestclient"));

webTestClient.get()
    .uri("/api/orders/{orderId}", 42L)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("order-get-webtestclient",
        pathParameters(
            parameterWithName("orderId")
                .description("Mã đơn hàng")
        )
    ));
~~~

Đây là các đoạn trích trong test đã cấu hình REST Docs cho **WebTestClient**; `document(...)` được import từ **WebTestClientRestDocumentation**.

### REST Assured

~~~java
given(spec)
    .filter(document("orders-list-rest-assured"))
    .when()
    .get("/api/orders")
    .then()
    .statusCode(200);

given(spec)
    .filter(document("order-get-rest-assured",
        pathParameters(
            parameterWithName("orderId").description("Mã đơn hàng")
        )
    ))
    .pathParam("orderId", 42L)
    .when()
    .get("/api/orders/{orderId}")
    .then()
    .statusCode(200);
~~~

Trong REST Assured, mỗi request có filter **document(...)** riêng; **spec** cần được thiết lập tích hợp Spring REST Docs. `document(...)` ở đây được import từ **RestAssuredRestDocumentation**.

## 8. Ghép nhiều operation vào Asciidoctor

Sau khi test chạy, thư mục snippets có thể có cấu trúc:

~~~text
build/generated-snippets/
├── orders-list/
│   ├── http-request.adoc
│   └── http-response.adoc
├── order-get/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   └── path-parameters.adoc
└── order-create/
    ├── http-request.adoc
    ├── http-response.adoc
    └── request-fields.adoc
~~~

Trong **src/docs/asciidoc/orders.adoc**:

~~~asciidoc
= Orders API
:toc: left

== Liệt kê đơn hàng

GET /api/orders

=== Request

include::{snippets}/orders-list/http-request.adoc[]

=== Response

include::{snippets}/orders-list/http-response.adoc[]

== Xem một đơn hàng

GET /api/orders/{orderId}

=== Path parameters

include::{snippets}/order-get/path-parameters.adoc[]

=== Request

include::{snippets}/order-get/http-request.adoc[]

=== Response

include::{snippets}/order-get/http-response.adoc[]

== Tạo đơn hàng

POST /api/orders

=== Request fields

include::{snippets}/order-create/request-fields.adoc[]

=== Request và response

include::{snippets}/order-create/http-request.adoc[]
include::{snippets}/order-create/http-response.adoc[]
~~~

Mỗi phần tài liệu sử dụng snippet identifier tương ứng với operation. Không dùng một đường dẫn snippet chung cho toàn bộ API khi mỗi request cần một bộ request/response độc lập.

### 8.1. Nối test với Asciidoctor trong Gradle

Ví dụ Gradle Groovy DSL khi plugin **org.asciidoctor.jvm.convert** đã được cấu hình:

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

Trong CI, hãy chạy các test sinh snippets trước khi dựng tài liệu. Nếu một operation không còn chạy hoặc assertion thất bại, build phải dừng trước khi xuất bản tài liệu. Có thể kiểm tra đầu ra bằng cách xác nhận các thư mục **orders-list**, **order-get**, **order-create** và những snippet được include đều xuất hiện sau bước test.

Nếu tài liệu cuối là Markdown, cần cơ chế chuyển đổi hoặc nhúng tương thích; cú pháp **include::...[]** là cú pháp của Asciidoctor, không phải Markdown chuẩn.

## 9. Bài thực hành

Một ứng dụng quản lý sách có ba operation:

~~~text
GET /api/books
GET /api/books/{bookId}
POST /api/books
~~~

Yêu cầu:

1. Viết một test method gọi cả ba request bằng **MockMvc**.
2. Thêm assertion cho status và ít nhất một field response trong từng operation.
3. Gọi **document(...)** ba lần, với identifier lần lượt là **books-list**, **book-get** và **book-create**.
4. Dùng **pathParameters(...)** cho operation GET chi tiết; dùng **requestFields(...)** cho POST create.
5. Kiểm tra từng thư mục snippets được sinh riêng và không chứa nhầm request/response của operation khác.
6. Nhúng các snippet vào file Asciidoctor có ba section.
7. Đổi thử một identifier trong test nhưng không sửa include; quan sát tác vụ Asciidoctor báo thiếu snippet.

Mẫu tạo descriptor cho GET chi tiết:

~~~java
pathParameters(
    parameterWithName("bookId")
        .description("Mã sách cần tra cứu")
)
~~~

**Tiêu chí hoàn thành:** một test method có ba lần thực hiện HTTP; mỗi operation có assertion và một document identifier riêng; snippet được sinh đúng nhóm; tài liệu Asciidoctor include đúng request/response tương ứng.

## Ghi nhớ

MockMvc cho phép một test method thực hiện nhiều HTTP operation. Để Spring REST Docs sinh tài liệu đầy đủ, hãy gọi **`andDo(document(...))`** sau từng request, đặt **identifier riêng** cho từng operation và khai báo descriptor phù hợp với request đó. Mỗi bộ snippet nên phản ánh đúng method, URI, header, payload và response của một operation. Sau đó, include từng bộ vào đúng section Asciidoctor và nối tác vụ test với build/CI để tài liệu được tạo từ những request đã kiểm thử.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs MockMvc API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/mockmvc/MockMvcRestDocumentation.html) và [MockMvc API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/servlet/MockMvc.html).
