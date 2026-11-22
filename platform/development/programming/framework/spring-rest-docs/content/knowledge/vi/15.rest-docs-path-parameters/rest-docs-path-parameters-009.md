# Document lỗi khi resource id không tồn tại

## Mục tiêu bài học

Một request có thể khớp route và truyền đúng kiểu **resource ID**, nhưng tài nguyên được yêu cầu không tồn tại. Ví dụ **GET /api/orders/9999** có thể khớp route **/api/orders/{orderId}**, chuyển được **9999** thành **Long**, nhưng service không tìm thấy đơn hàng. API thường trả **404 Not Found** trong trường hợp đó.

Với **Spring REST Docs**, bài kiểm thử có thể tài liệu hóa cả request thành công và response lỗi. Khi ghi lại lỗi không tìm thấy tài nguyên, cần mô tả đúng path parameter, mã HTTP và cấu trúc response lỗi để người gọi biết tài nguyên nào được tra cứu, lỗi có ý nghĩa gì và có thể xử lý ra sao.

Bài học thuộc module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**; sinh snippet cho request, response, payload, tham số và header; biên soạn tài liệu Asciidoctor/Markdown và đưa vào build/CI.

Sau bài này, bạn có thể:

- Phân biệt **resource ID không tồn tại** với route không khớp, ID sai định dạng và lỗi phân quyền.
- Thiết kế response **404** ổn định, không làm lộ thông tin nội bộ.
- Viết test cho cả trường hợp ID có tài nguyên và ID không có tài nguyên.
- Dùng **pathParameters(...)** kết hợp snippet response để tài liệu hóa request gây lỗi.
- Tạo snippet response body, response fields và HTTP response từ bài test.
- Kiểm tra hợp đồng lỗi qua MockMvc, WebTestClient hoặc REST Assured.
- Ghép snippet lỗi vào tài liệu Asciidoctor và quy trình CI.

## 1. 404 do không có resource khác với 404 do không có route

Xét endpoint:

~~~text
GET /api/orders/{orderId}
~~~

Hai request sau có thể cùng nhận HTTP **404**, nhưng nguyên nhân khác nhau:

| Request | Giai đoạn | Ý nghĩa |
| --- | --- | --- |
| **GET /api/orders/9999** | Route khớp, ID được bind; service truy vấn nhưng không tìm thấy đơn hàng | **Resource not found** |
| **GET /api/missing/9999** | Không có handler phù hợp với đường dẫn | **Route not found** |

Một số lỗi khác cũng có mã HTTP khác:

| Request | Nguyên nhân | Mã thường gặp |
| --- | --- | --- |
| **GET /api/orders/abc** khi controller nhận **Long** | Giá trị không chuyển đổi được sang kiểu ID | **400 Bad Request** |
| **POST /api/orders/42** khi chỉ có mapping GET | Method không được hỗ trợ trên resource path đó | **405 Method Not Allowed** |
| **GET /api/orders/42** nhưng người gọi không có quyền | Không được phép truy cập tài nguyên | **403 Forbidden** hoặc đôi khi **404** theo chính sách che giấu sự tồn tại |
| **GET /api/orders/9999** khi ID hợp lệ nhưng không có bản ghi | Không tìm thấy resource | **404 Not Found** |

Mã trả về thực tế phụ thuộc route khác, exception handler và chính sách bảo mật của ứng dụng. Vì vậy, bài kiểm thử không nên chỉ assert rằng request “bị lỗi”; hãy xác định rõ **nguyên nhân** và **hợp đồng HTTP** mà API công bố.

~~~mermaid
flowchart TD
    A["GET /api/orders/9999"] --> B{"Route /api/orders/{orderId} khớp?"}
    B -->|Không| C["Không có handler: thường 404"]
    B -->|Có| D["Bind orderId"]
    D --> E{"ID có đúng kiểu?"}
    E -->|Không| F["Binding lỗi: thường 400"]
    E -->|Có| G["Service tìm đơn hàng"]
    G --> H{"Tìm thấy resource?"}
    H -->|Không| I["Resource not found: 404"]
    H -->|Có| J["Trả response thành công"]
~~~

Sự phân biệt này quan trọng khi viết tài liệu: **404 do ID không tồn tại** phải đi qua đúng route và đúng kiểu dữ liệu, sau đó mới phát sinh từ tầng tìm kiếm tài nguyên.

## 2. Thiết kế response lỗi có cấu trúc ổn định

Không nên trả stack trace, tên bảng, SQL, đường dẫn file hay chi tiết nội bộ trong response lỗi. API nên trả một cấu trúc ổn định, đủ thông tin cho client nhận diện lỗi.

Ví dụ response:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "code": "ORDER_NOT_FOUND",
  "message": "Không tìm thấy đơn hàng",
  "resource": "order",
  "resourceId": "9999"
}
~~~

| Field | Ý nghĩa |
| --- | --- |
| **code** | Mã lỗi ổn định để client phân nhánh xử lý |
| **message** | Thông điệp dành cho người dùng hoặc client |
| **resource** | Loại tài nguyên không tìm thấy |
| **resourceId** | Giá trị ID đã yêu cầu, nếu chính sách API cho phép công bố |

Đối với một số API đa tenant hoặc có tài nguyên nhạy cảm, không nên xác nhận ID đó có tồn tại ở tenant khác. Khi đó có thể dùng cùng response **404** cho cả trường hợp “không tồn tại” và “không thuộc phạm vi được phép nhìn thấy”, tránh rò rỉ thông tin.

Một lựa chọn khác là dùng chuẩn **Problem Details** của HTTP (RFC 9457), với các field như **type**, **title**, **status**, **detail** và **instance**. Nếu ứng dụng chọn định dạng này, hãy tài liệu hóa đúng media type và cấu trúc mà API thực sự trả về. Không trộn lẫn hai định dạng lỗi trong cùng một endpoint nếu chưa có hợp đồng rõ ràng.

## 3. Triển khai controller và exception handler

Ví dụ dùng **Spring Boot 3.x**, **Java 17+**, Spring MVC và một kiểu lỗi domain riêng.

### 3.1. Exception và response model

~~~java
class OrderNotFoundException extends RuntimeException {
    private final Long orderId;

    OrderNotFoundException(Long orderId) {
        super("Order not found");
        this.orderId = orderId;
    }

    Long getOrderId() {
        return orderId;
    }
}

record ApiError(
    String code,
    String message,
    String resource,
    String resourceId
) {}
~~~

Service phát sinh exception khi không có tài nguyên:

~~~java
import org.springframework.stereotype.Service;

@Service
class OrderService {

    OrderResponse getOrder(Long orderId) {
        // Minh họa: chỉ có đơn hàng 42 trong dữ liệu mẫu.
        if (!orderId.equals(42L)) {
            throw new OrderNotFoundException(orderId);
        }
        return new OrderResponse(orderId, "OPEN");
    }
}

record OrderResponse(Long id, String status) {}
~~~

Controller chỉ xử lý mapping và gọi service:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/orders/{orderId}")
    OrderResponse getOrder(@PathVariable("orderId") Long orderId) {
        return orderService.getOrder(orderId);
    }
}
~~~

Exception handler chuyển lỗi domain thành response HTTP có cấu trúc:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleOrderNotFound(
            OrderNotFoundException exception) {
        ApiError body = new ApiError(
            "ORDER_NOT_FOUND",
            "Không tìm thấy đơn hàng",
            "order",
            exception.getOrderId().toString()
        );
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }
}
~~~

Trong dự án thực tế, service sẽ truy vấn repository thay vì dùng ID cố định. Exception handler cần tuân thủ chuẩn response chung của API. Nếu ứng dụng đã có **@ControllerAdvice** dùng chung, hãy bổ sung mapping lỗi vào nơi đó thay vì tạo nhiều handler cạnh tranh.

## 4. Viết test cho trường hợp thành công và không tìm thấy

Test lỗi 404 cần chứng minh request đã **đi đúng route**. Với MockMvc, sử dụng **RestDocumentationRequestBuilders.get(...)** cùng URI template và truyền một giá trị ID có kiểu hợp lệ.

### 4.1. Cấu hình dependency

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Ví dụ giả định Spring Boot dependency management/BOM quản lý phiên bản tương thích. Nếu dùng Maven, cấu hình dependency tương ứng và thư mục snippets trong **target/generated-snippets**.

### 4.2. Test sinh snippet cho response thành công

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(controllers = OrderController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void documentExistingOrder() throws Exception {
        given(orderService.getOrder(42L))
            .willReturn(new OrderResponse(42L, "OPEN"));

        mockMvc.perform(get("/api/orders/{orderId}", 42L)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andDo(document("order-get",
                pathParameters(
                    parameterWithName("orderId")
                        .description("Mã đơn hàng cần tra cứu")
                )
            ));
    }
}
~~~

Đây là phần test thành công để đối chiếu với tài liệu lỗi. Trong các ví dụ tiếp theo, thêm method test vào cùng class trên.

### 4.3. Test 404 do resource ID không tồn tại và sinh snippet lỗi

~~~java
@Test
void documentOrderNotFound() throws Exception {
    given(orderService.getOrder(9999L))
        .willThrow(new OrderNotFoundException(9999L));

    mockMvc.perform(get("/api/orders/{orderId}", 9999L)
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"))
        .andExpect(jsonPath("$.resourceId").value("9999"))
        .andDo(document("order-get-not-found",
            pathParameters(
                parameterWithName("orderId")
                    .description("Mã đơn hàng cần tra cứu")
            ),
            responseFields(
                fieldWithPath("code")
                    .description("Mã lỗi ổn định cho client"),
                fieldWithPath("message")
                    .description("Thông điệp lỗi"),
                fieldWithPath("resource")
                    .description("Loại tài nguyên không tìm thấy"),
                fieldWithPath("resourceId")
                    .description("Mã tài nguyên đã yêu cầu")
            )
        ));
}
~~~

Các static import cho `fieldWithPath(...)` và `responseFields(...)` đã được khai báo trong phần import của **OrderDocumentationTest**. Trong snippet lỗi:

- **pathParameters(...)** vẫn mô tả **orderId** vì request đi qua route chi tiết.
- **responseFields(...)** mô tả payload lỗi mà client nhận được.
- **andExpect(status().isNotFound())** xác nhận mã HTTP.
- **andExpect(jsonPath(...))** xác nhận response đúng mã lỗi và ID.

Snippet **http-response.adoc** mặc định thể hiện status, header và body response. **responseFields(...)** bổ sung bảng mô tả cấu trúc JSON để người đọc hiểu từng field của payload lỗi.

### 4.4. Không gọi đây là lỗi route

Trong test trên, URL **/api/orders/9999** có template đúng và ID **9999** chuyển được thành **Long**. Mock service phát sinh **OrderNotFoundException** và handler tạo HTTP 404. Đây là **resource not found**.

Nếu muốn kiểm tra route không tồn tại, hãy dùng request khác, ví dụ **GET /api/missing/9999**, và assert 404 riêng. Không gắn descriptor **orderId** cho request đó nếu không có biến tương ứng trong URI template của nó.

## 5. Những snippet có thể dùng để tài liệu hóa lỗi

Spring REST Docs tạo một số snippet hữu ích cho lỗi:

| Snippet | Nội dung |
| --- | --- |
| **path-parameters.adoc** | Tên và mô tả biến đường dẫn của request |
| **http-request.adoc** | Method, URI và header của request |
| **http-response.adoc** | Status, header và body của response |
| **response-body.adoc** | Body response thô hoặc đã định dạng |
| **response-fields.adoc** | Bảng mô tả cấu trúc payload lỗi |

Thư mục sinh dự kiến:

~~~text
build/generated-snippets/
└── order-get-not-found/
    ├── path-parameters.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    ├── response-body.adoc
    └── response-fields.adoc
~~~

Danh sách thực tế phụ thuộc vào default snippets và các snippet bạn đã yêu cầu trong **document(...)**. Spring REST Docs thường sinh các snippet mặc định như **http-request.adoc** và **http-response.adoc** khi tích hợp đúng; các snippet payload cần được khai báo tương ứng.

### 5.1. Dùng responseFields nghiêm ngặt

Với:

~~~java
responseFields(
    fieldWithPath("code").description("Mã lỗi"),
    fieldWithPath("message").description("Thông điệp")
)
~~~

Spring REST Docs kiểm tra các field được mô tả với payload response theo chế độ nghiêm ngặt. Nếu response có thêm **resource** và **resourceId** mà không mô tả, snippet có thể báo lỗi field chưa được tài liệu hóa.

Nếu response có field phụ chưa muốn mô tả trong bài hiện tại, cân nhắc descriptor **ignored()** hoặc **relaxedResponseFields(...)** chỉ khi thực sự có lý do. Với hợp đồng API công khai, ưu tiên mô tả toàn bộ field để thay đổi cấu trúc lỗi được phát hiện sớm.

## 6. Tài liệu hóa lỗi trong Asciidoctor

Trong **src/docs/asciidoc/index.adoc**, có thể tạo một mục riêng cho lỗi 404:

~~~asciidoc
== Lấy đơn hàng theo ID

=== Path parameters

include::{snippets}/order-get/path-parameters.adoc[]

=== Successful response

include::{snippets}/order-get/http-response.adoc[]

=== Khi đơn hàng không tồn tại

Request:

include::{snippets}/order-get-not-found/http-request.adoc[]

Path parameters:

include::{snippets}/order-get-not-found/path-parameters.adoc[]

Response:

include::{snippets}/order-get-not-found/http-response.adoc[]

Error response fields:

include::{snippets}/order-get-not-found/response-fields.adoc[]
~~~

Như vậy người đọc thấy được cùng một endpoint có response thành công và response lỗi. Hai trường hợp dùng snippet ID riêng, tránh ghi đè file sinh ra.

### 6.1. Tích hợp Gradle

Ví dụ dưới giả định plugin **org.asciidoctor.jvm.convert** đã được cấu hình:

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

Tác vụ Asciidoctor cần chạy sau bài kiểm thử sinh snippet. Trong CI, test assertion thất bại, snippet thiếu hoặc cấu trúc response thay đổi ngoài mô tả phải làm pipeline dừng trước khi xuất bản tài liệu.

Với tài liệu cuối dạng Markdown, dùng hệ thống chuyển đổi hoặc cơ chế include phù hợp. **include::...[]** là cú pháp của Asciidoctor, không phải cú pháp Markdown tiêu chuẩn.

## 7. Kiểm thử với WebTestClient và REST Assured

Nguyên tắc không thay đổi: gửi request có URI template, xác nhận mã HTTP và response body, rồi gắn snippet path parameters cùng response fields.

### 7.1. WebTestClient

Trong test đã cấu hình REST Docs cho **WebTestClient**:

~~~java
webTestClient.get()
    .uri("/api/orders/{orderId}", 9999L)
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isNotFound()
    .expectBody()
    .consumeWith(document("order-not-found-webtestclient",
        pathParameters(
            parameterWithName("orderId")
                .description("Mã đơn hàng cần tra cứu")
        ),
        responseFields(
            fieldWithPath("code").description("Mã lỗi ổn định"),
            fieldWithPath("message").description("Thông điệp lỗi"),
            fieldWithPath("resource").description("Loại tài nguyên"),
            fieldWithPath("resourceId").description("Mã tài nguyên đã yêu cầu")
        )
    ));
~~~

Ở đây **document(...)** được import từ **WebTestClientRestDocumentation**. Client cần cấu hình REST Docs trước; **pathParameters(...)** và **responseFields(...)** vẫn dùng API mô tả chung.

### 7.2. REST Assured

Với **RequestSpecification spec** đã cấu hình REST Docs:

~~~java
given(spec)
    .filter(document("order-not-found-rest-assured",
        pathParameters(
            parameterWithName("orderId")
                .description("Mã đơn hàng cần tra cứu")
        ),
        responseFields(
            fieldWithPath("code").description("Mã lỗi ổn định"),
            fieldWithPath("message").description("Thông điệp lỗi"),
            fieldWithPath("resource").description("Loại tài nguyên"),
            fieldWithPath("resourceId").description("Mã tài nguyên đã yêu cầu")
        )
    ))
    .pathParam("orderId", 9999L)
    .when()
    .get("/api/orders/{orderId}")
    .then()
    .statusCode(404);
~~~

Ở đây **document(...)** thuộc **RestAssuredRestDocumentation**. **pathParam(...)** gán giá trị ID; snippet ghi lại biến **orderId** và payload lỗi. Có thể bổ sung assertion nội dung JSON nếu test cần xác nhận mã lỗi cụ thể.

## 8. Các lưu ý khi tài liệu hóa 404

### 8.1. Giữ response lỗi ổn định

Client thường cần mã lỗi máy đọc được hơn là một câu tiếng người có thể thay đổi theo ngôn ngữ. Vì vậy, hãy ưu tiên **code** ổn định, dùng message cho mục đích hiển thị và tránh để test phụ thuộc quá nhiều vào câu chữ nếu API không cam kết message cố định.

### 8.2. Không tiết lộ dữ liệu nhạy cảm

Không trả stack trace, câu SQL, tên bảng, thông tin máy chủ, hay dữ liệu của tài nguyên không thuộc quyền người gọi. Trường **resourceId** chỉ nên xuất hiện nếu chính sách bảo mật cho phép phản hồi ID do chính client vừa gửi. Trong đa tenant, hãy cẩn thận với việc tiết lộ tài nguyên tồn tại trong tenant khác.

### 8.3. Phân biệt lỗi chuyển đổi và lỗi không tồn tại

ID **abc** gửi vào **@PathVariable Long** thường gây lỗi 400 trước khi service truy vấn. ID **9999** hợp lệ về kiểu nhưng không tìm thấy dữ liệu sẽ tạo 404 từ service. Hai trường hợp nên có test riêng vì chúng đại diện cho hai lỗi khác nhau.

### 8.4. Không làm test tài liệu phụ thuộc dữ liệu không ổn định

Test sinh snippet nên dùng fixture cố định, mock hoặc dữ liệu test có thể tái lập. Nếu dùng DB chia sẻ hoặc ID ngẫu nhiên không kiểm soát, kết quả 404 có thể lúc thành công lúc thất bại, làm tài liệu và CI không ổn định.

## 9. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Request ID hợp lệ trả 404 ngoài dự kiến | Dữ liệu test không có hoặc service mock sai | Tạo fixture rõ ràng và kiểm tra lời gọi mock |
| Test mong 404 nhưng nhận 400 | ID sai định dạng hoặc lỗi binding xảy ra trước service | Dùng ID hợp lệ về kiểu khi test resource-not-found |
| Test 404 nhưng không sinh snippet path | Chưa dùng URI template hoặc thiếu **document(...)** | Dùng request builder REST Docs và descriptor |
| Snippet response-fields báo field thiếu/thừa | Descriptor không khớp payload lỗi | Cập nhật mô tả hoặc dùng ignored/relaxed có chủ đích |
| Response lỗi chứa stack trace | Handler trả exception nội bộ | Chuyển exception thành response công khai an toàn |
| Route không tồn tại cũng dùng chung snippet ID với resource missing | Test không tách nguyên nhân | Dùng snippet ID riêng và ghi rõ tình huống |
| Tài liệu hiển thị response cũ | Snippet không được sinh lại hoặc output cũ còn sót | Bảo đảm test là dependency của Asciidoctor và build sạch khi cần |
| ID tồn tại ở tài khoản khác vẫn bị trả về | Truy vấn chỉ theo ID con | Giới hạn truy vấn theo owner/tenant và test quan hệ |

## 10. Bài thực hành

Cho API:

~~~text
GET /api/customers/{customerId}
~~~

Hợp đồng:

- **customerId** là UUID.
- Nếu khách hàng tồn tại, trả HTTP 200 và JSON khách hàng.
- Nếu UUID hợp lệ nhưng không có khách hàng, trả HTTP 404 với payload có **code**, **message**, **resource** và **resourceId**.
- Nếu UUID sai định dạng, trả HTTP 400.

Hãy thực hiện:

1. Viết controller/service và exception handler cho **CustomerNotFoundException**.
2. Viết test MockMvc thành công, dùng URI template **/api/customers/{customerId}**, sinh snippet với **pathParameters(...)**.
3. Viết test UUID hợp lệ nhưng không tồn tại, assert 404 và các field payload lỗi; dùng snippet ID **customer-not-found**.
4. Viết test UUID sai định dạng, assert 400; giải thích vì sao không phải resource-not-found.
5. Nhúng **path-parameters.adoc**, **http-response.adoc** và **response-fields.adoc** vào Asciidoctor.
6. Chạy test rồi dựng tài liệu; thử bỏ một response field descriptor và quan sát REST Docs phát hiện thay đổi payload như thế nào.

Mẫu descriptor cho lỗi:

~~~java
pathParameters(
    parameterWithName("customerId")
        .description("UUID định danh khách hàng")
),
responseFields(
    fieldWithPath("code").description("Mã lỗi ổn định"),
    fieldWithPath("message").description("Thông điệp lỗi"),
    fieldWithPath("resource").description("Loại tài nguyên"),
    fieldWithPath("resourceId").description("UUID đã yêu cầu")
)
~~~

**Tiêu chí hoàn thành:** test phân biệt được 200, 404 do resource không tồn tại và 400 do ID sai định dạng; snippet mô tả đúng path parameter và response lỗi; tài liệu dựng thành công từ snippet do test tạo.

## Ghi nhớ

Khi **resource ID hợp lệ về kiểu nhưng không có tài nguyên**, API thường trả **404 Not Found** sau khi route đã khớp và service thực hiện tra cứu. Hãy phân biệt tình huống này với route không tồn tại, lỗi binding 400 và lỗi phân quyền. Trong Spring REST Docs, dùng **pathParameters(...)** để mô tả ID đã yêu cầu, kết hợp **responseFields(...)** và **http-response.adoc** để ghi lại payload lỗi. Kiểm thử cả trường hợp thành công lẫn không tìm thấy bằng dữ liệu ổn định, sau đó nhúng snippet vào Asciidoctor và CI để hợp đồng lỗi luôn được kiểm chứng.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs RequestDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/RequestDocumentation.html), [Spring Framework @ExceptionHandler](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptions.html) và [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457).
