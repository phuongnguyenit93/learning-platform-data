# URI template và path parameter lồng nhau

## Mục tiêu bài học

Trong REST API, tài nguyên thường được tổ chức theo quan hệ cha–con. Ví dụ, một cửa hàng có nhiều sản phẩm, một đơn hàng có nhiều dòng hàng, hoặc một tài khoản có nhiều giao dịch. Đường dẫn thể hiện quan hệ đó bằng nhiều đoạn và nhiều biến:

```text
/api/stores/{storeId}/products/{productId}
/api/orders/{orderId}/lines/{lineId}
/api/accounts/{accountId}/transactions/{transactionId}
```

Đây là **nested resource URI** (URI tài nguyên lồng nhau). Khi viết bài kiểm thử với **Spring REST Docs**, mỗi biến trên đường dẫn đều cần được nhận diện và mô tả chính xác bằng **pathParameters(...)** và **parameterWithName(...)**. Tài liệu phải giúp người dùng API hiểu từng ID định danh tài nguyên nào, mối quan hệ giữa chúng ra sao và khi nào nên dùng endpoint lồng nhau.

Bài học thuộc module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng từ test HTTP bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**, sinh snippet cho request, response, payload, tham số và header, rồi biên soạn Asciidoctor/Markdown và đưa vào build/CI.

Sau bài này, bạn có thể:

- Đọc và thiết kế URI template có nhiều path parameter.
- Phân biệt **ID cha** và **ID con**, hiểu ý nghĩa của từng đoạn trong đường dẫn.
- Khai báo đủ descriptor cho path parameter lồng nhau.
- Kiểm thử việc tài nguyên con thực sự thuộc tài nguyên cha.
- Phân biệt lỗi không tìm thấy cha, không tìm thấy con và con không thuộc cha.
- Đánh giá khi nào nên lồng URI, khi nào nên dùng URI phẳng hoặc kết hợp cả hai.
- Sinh và nhúng snippet **path-parameters.adoc** vào tài liệu API.

## 1. Nhận diện URI template lồng nhau

Giả sử hệ thống quản lý cửa hàng và sản phẩm. Một cửa hàng có nhiều sản phẩm; một sản phẩm trong cửa hàng có mã riêng. API lấy thông tin một sản phẩm có thể sử dụng:

```http
GET /api/stores/store-09/products/product-31
Accept: application/json
```

URI template tương ứng:

```text
/api/stores/{storeId}/products/{productId}
```

Tách từng đoạn:

| Vị trí | Literal hoặc biến | Ý nghĩa |
| --- | --- | --- |
| 1 | `api` | Tiền tố API |
| 2 | `stores` | Tập hợp cửa hàng |
| 3 | `{storeId}` | Định danh cửa hàng cha |
| 4 | `products` | Tập hợp sản phẩm thuộc cửa hàng |
| 5 | `{productId}` | Định danh sản phẩm con |

Hai biến **storeId** và **productId** là hai path parameter khác nhau. Giá trị **store-09** gắn với biến cha; giá trị **product-31** gắn với biến con. Tên trong descriptor phải trùng chính xác tên biến của URI template:

```java
pathParameters(
    parameterWithName("storeId")
        .description("Mã cửa hàng chứa sản phẩm"),
    parameterWithName("productId")
        .description("Mã sản phẩm thuộc cửa hàng")
)
```

Không khai báo `parameterWithName("id")` cho cả hai biến hoặc dùng giá trị `store-09` và `product-31` làm tên descriptor. Spring REST Docs cần **tên biến trong template**, không phải giá trị thực tế của request.

### 1.1. Đường dẫn lồng nhau thể hiện điều gì?

Đường dẫn trên truyền đạt rằng người gọi đang truy cập sản phẩm trong phạm vi một cửa hàng. Nó mô tả vị trí tài nguyên theo quan hệ cha–con, nhưng bản thân URI **không bảo đảm** sản phẩm thực sự thuộc cửa hàng đó. Ứng dụng vẫn phải kiểm tra quan hệ trong dữ liệu.

Ví dụ:

| Request | Ý nghĩa mong đợi |
| --- | --- |
| `GET /api/stores/store-09/products/product-31` | Lấy sản phẩm 31 trong cửa hàng 09 |
| `GET /api/stores/store-12/products/product-31` | Lấy sản phẩm 31 nếu nó thuộc cửa hàng 12 |
| `GET /api/stores/store-09/products/product-999` | Sản phẩm 999 có tồn tại trong cửa hàng 09 không? |
| `GET /api/stores/store-999/products/product-31` | Cửa hàng 999 có tồn tại không? |

Nếu sản phẩm tồn tại nhưng thuộc **store-12**, request dùng **store-09** không nên trả dữ liệu sản phẩm chỉ vì **productId** hợp lệ. Service phải kiểm tra cả hai khóa hoặc truy vấn theo quan hệ **storeId + productId**.

## 2. Thiết kế endpoint cho tài nguyên lồng nhau

Một cấu trúc API thường gặp:

```text
/api/orders/{orderId}/lines
/api/orders/{orderId}/lines/{lineId}
/api/accounts/{accountId}/transactions
/api/accounts/{accountId}/transactions/{transactionId}
```

| Endpoint | Thao tác |
| --- | --- |
| `GET /api/orders/{orderId}/lines` | Liệt kê các dòng thuộc đơn hàng |
| `GET /api/orders/{orderId}/lines/{lineId}` | Lấy một dòng hàng trong đơn |
| `POST /api/orders/{orderId}/lines` | Tạo dòng hàng trong đơn |
| `DELETE /api/orders/{orderId}/lines/{lineId}` | Xóa dòng hàng khỏi đơn |

Mỗi biến mô tả một phần phạm vi tài nguyên. Với endpoint chi tiết, **orderId** xác định đơn hàng cha, **lineId** xác định dòng hàng con trong đơn đó.

### 2.1. ID con có thể duy nhất toàn hệ thống nhưng vẫn cần ID cha

Ngay cả khi **lineId** là UUID duy nhất toàn cục, URI lồng nhau vẫn có thể hữu ích vì nó cho biết ngữ cảnh nghiệp vụ và giúp máy chủ xác minh quan hệ:

```text
/api/orders/{orderId}/lines/{lineId}
```

Nếu API chỉ cần định danh dòng hàng và không phụ thuộc ngữ cảnh đơn hàng, một endpoint phẳng như **/api/order-lines/{lineId}** cũng có thể phù hợp. Lựa chọn phụ thuộc vào hợp đồng, quyền truy cập, cách tổ chức tài nguyên và nhu cầu của client.

Không nên lồng quá sâu một cách máy móc. Một URI như **/companies/{companyId}/departments/{departmentId}/teams/{teamId}/members/{memberId}/devices/{deviceId}** có thể khó sử dụng và làm client phụ thuộc quá nhiều vào cấu trúc nội bộ. Hãy chỉ giữ những cấp cha thực sự cần để xác định phạm vi hoặc ngữ cảnh tài nguyên.

### 2.2. URI cha–con không tự thực thi kiểm soát truy cập

Người dùng có thể thay **orderId** hoặc **lineId** trong URL. Việc có ID trong path không chứng minh rằng người gọi được phép đọc tài nguyên đó. Backend cần kiểm tra:

- Người gọi có quyền xem đơn hàng cha không?
- Dòng hàng con có thực sự thuộc đơn hàng đã nêu không?
- Người gọi có quyền thao tác trên dòng hàng trong đơn đó không?

Đây là kiểm soát nghiệp vụ và bảo mật tại service/authorization layer. **pathParameters(...)** chỉ tài liệu hóa các biến; nó không xác minh quyền sở hữu và không ngăn truy cập trái phép.

## 3. Triển khai controller và service cho route lồng nhau

Ví dụ dưới đây dùng **Spring Boot 3.x**, Java 17+, **Spring MVC** và **JUnit 5**. Controller lấy dòng hàng trong một đơn hàng:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
class OrderLineController {

    private final OrderLineService service;

    OrderLineController(OrderLineService service) {
        this.service = service;
    }

    @GetMapping("/api/orders/{orderId}/lines/{lineId}")
    OrderLineResponse getLine(
            @PathVariable("orderId") Long orderId,
            @PathVariable("lineId") Long lineId) {
        return service.getLine(orderId, lineId);
    }
}

record OrderLineResponse(Long orderId, Long lineId, int quantity) {}
```

Service phải sử dụng cả hai ID khi xác định dòng hàng:

```java
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
class OrderLineService {

    OrderLineResponse getLine(Long orderId, Long lineId) {
        // Minh họa dữ liệu: line 7 chỉ thuộc order 42.
        if (!orderId.equals(42L)) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Order not found");
        }

        if (!lineId.equals(7L)) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Order line not found");
        }

        return new OrderLineResponse(orderId, lineId, 2);
    }
}
```

Trong hệ thống thực tế, thay logic minh họa bằng truy vấn repository có điều kiện theo **cả orderId và lineId**, ví dụ truy vấn một dòng hàng có **id = lineId AND order_id = orderId**. Truy vấn như vậy bảo đảm dòng hàng được lấy trong đúng phạm vi đơn hàng.

### 3.1. Phân biệt các tình huống lỗi

| Tình huống | Ý nghĩa | Hành vi thường chọn |
| --- | --- | --- |
| Không có **orderId** trên đường dẫn | Không khớp URI template chi tiết | Thường 404 nếu không có route khác |
| **orderId** sai kiểu Long | Binding path variable thất bại | Thường 400 |
| Đơn hàng cha không tồn tại | Không tìm thấy tài nguyên cha | 404 |
| Dòng hàng con không tồn tại trong đơn | Không tìm thấy tài nguyên con trong phạm vi cha | 404 |
| Dòng hàng có tồn tại nhưng thuộc đơn khác | Quan hệ cha–con không hợp lệ với request | Thường trả 404 để không tiết lộ tài nguyên ngoài phạm vi; tùy hợp đồng có thể chọn chính sách khác |
| Người gọi không được phép truy cập | Lỗi phân quyền | 403 hoặc 404 tùy chính sách bảo mật |

Mã HTTP cụ thể phụ thuộc hợp đồng API và cơ chế xử lý lỗi của ứng dụng. Điều quan trọng là **test và tài liệu phải nhất quán với hành vi đã chọn**.

## 4. Tài liệu hóa nhiều path parameter bằng Spring REST Docs

Spring REST Docs sử dụng **pathParameters(...)** để mô tả toàn bộ biến trong URI template. Với route:

```text
/api/orders/{orderId}/lines/{lineId}
```

descriptor tương ứng:

```java
pathParameters(
    parameterWithName("orderId")
        .description("Mã đơn hàng chứa dòng hàng"),
    parameterWithName("lineId")
        .description("Mã dòng hàng cần lấy trong đơn")
)
```

Mô tả nên làm rõ vai trò của ID cha và ID con. Hai mô tả kiểu **“ID đơn hàng”** và **“ID dòng hàng”** tốt hơn việc lặp lại tên biến, nhưng có thể cụ thể hơn: “Mã đơn hàng chứa dòng hàng” và “Mã dòng hàng cần lấy trong đơn”.

Các descriptor phải đáp ứng:

1. Tên khớp chính xác với **{orderId}** và **{lineId}**.
2. Không đưa giá trị thực tế như **42** hoặc **7** vào tên descriptor.
3. Mỗi biến có mô tả riêng, tránh gộp nhiều ID vào một descriptor chung.
4. Nêu rõ quan hệ cha–con nếu đây là điều kiện quan trọng để gọi endpoint.

## 5. Ví dụ kiểm thử MockMvc sinh snippet

Thêm dependency test trong Gradle nếu dự án chưa có:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

Với Spring Boot dependency management/BOM, phiên bản tương thích có thể do BOM quản lý. Ví dụ test đặt cùng package với controller:

```java
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
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderLineController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderLineDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderLineService service;

    @Test
    void documentGetOrderLineInOrder() throws Exception {
        given(service.getLine(42L, 7L))
            .willReturn(new OrderLineResponse(42L, 7L, 2));

        mockMvc.perform(get(
                "/api/orders/{orderId}/lines/{lineId}",
                42L, 7L)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.orderId").value(42))
            .andExpect(jsonPath("$.lineId").value(7))
            .andExpect(jsonPath("$.quantity").value(2))
            .andDo(document("order-line-get",
                pathParameters(
                    parameterWithName("orderId")
                        .description("Mã đơn hàng chứa dòng hàng"),
                    parameterWithName("lineId")
                        .description("Mã dòng hàng cần lấy trong đơn")
                )
            ));
    }
}
```

Ở ví dụ trên:

- **RestDocumentationRequestBuilders.get(...)** giữ URI template có tên biến. Đây là builder cần dùng với MockMvc để Spring REST Docs nhận diện **orderId** và **lineId**.
- Hai giá trị **42L** và **7L** là dữ liệu request; thứ tự giá trị khớp thứ tự biến trên template.
- **given(...).willReturn(...)** cô lập controller test bằng service giả lập; test này kiểm tra routing, binding, response và snippet. Quy tắc kiểm tra dòng hàng có thuộc đơn hay không được kiểm thử riêng ở service.
- **document("order-line-get", ...)** sinh snippet cho request đã thực thi.

### 5.1. Snippet được tạo

Thư mục ví dụ:

```text
build/generated-snippets/
└── order-line-get/
    ├── path-parameters.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    └── curl-request.adoc
```

Đây là danh sách rút gọn; các snippet mặc định khác có thể được sinh tùy cấu hình. Bảng **path-parameters.adoc** có nội dung tương đương:

| Parameter | Description |
| --- | --- |
| **orderId** | Mã đơn hàng chứa dòng hàng |
| **lineId** | Mã dòng hàng cần lấy trong đơn |

Không chỉnh sửa trực tiếp file sinh ra trong **generated-snippets**. Hãy sửa descriptor trong bài kiểm thử và chạy lại test để tạo nội dung mới.

## 6. Kiểm thử tính toàn vẹn của quan hệ cha–con

Test sinh snippet thành công chưa đủ để bảo đảm API không trả dòng hàng từ đơn khác. Cần có service test hoặc integration test kiểm tra quan hệ dữ liệu.

Ví dụ với Mockito trong unit test service:

```java
@Test
void doesNotReturnLineBelongingToAnotherOrder() {
    // Giả sử dữ liệu: line 7 thuộc order 42.
    assertThatThrownBy(() -> service.getLine(99L, 7L))
        .isInstanceOf(ResponseStatusException.class)
        .extracting(error ->
            ((ResponseStatusException) error).getStatusCode())
        .isEqualTo(HttpStatus.NOT_FOUND);
}
```

Đoạn minh họa trên cần được đặt trong test class có khởi tạo service hoặc mock repository phù hợp. Với repository thực, tốt hơn là kiểm tra truy vấn được giới hạn theo cả hai khóa thay vì tải con theo **lineId** rồi quên xác minh **orderId**.

Một số kịch bản nên có:

| Kịch bản | Mục tiêu test |
| --- | --- |
| Cha tồn tại, con thuộc cha | Trả thông tin con thành công |
| Cha không tồn tại | Trả kết quả không tìm thấy theo hợp đồng |
| Cha tồn tại, con không tồn tại | Không trả dữ liệu con |
| Cha tồn tại, con tồn tại nhưng thuộc cha khác | Không để lộ dữ liệu ngoài phạm vi |
| Người dùng không có quyền trên cha | Từ chối theo chính sách phân quyền |

Nếu hệ thống dùng **@ControllerAdvice** hoặc error response chuẩn, test nên assert cả mã HTTP và cấu trúc lỗi mà API công bố.

## 7. Nhiều cấp path parameter và quan hệ lồng nhau sâu hơn

Ví dụ API quản lý dòng hàng:

```text
/api/companies/{companyId}/orders/{orderId}/lines/{lineId}
```

Khi đó descriptor phải bao gồm cả ba biến:

```java
pathParameters(
    parameterWithName("companyId")
        .description("Mã công ty sở hữu đơn hàng"),
    parameterWithName("orderId")
        .description("Mã đơn hàng thuộc công ty"),
    parameterWithName("lineId")
        .description("Mã dòng hàng thuộc đơn hàng")
)
```

Test cần xác minh **orderId thuộc companyId** và **lineId thuộc orderId**. Nếu chỉ kiểm tra từng ID tồn tại riêng lẻ, API vẫn có nguy cơ trả nhầm tài nguyên trong một quan hệ cha–con không hợp lệ.

Khi có nhiều cấp:

- Duy trì thứ tự descriptor theo thứ tự xuất hiện trong URI template để người đọc dễ đối chiếu.
- Mô tả đầy đủ vai trò của từng cấp.
- Không bỏ qua biến cha nếu client cần nó để xác định đúng phạm vi tài nguyên.
- Cân nhắc độ sâu URL và mức độ phụ thuộc vào mô hình dữ liệu nội bộ.

Nếu một parent ID chỉ dùng để kiểm tra phạm vi nhưng không cần hiển thị trong bảng, REST Docs có descriptor **ignored()**. Tuy nhiên, chỉ nên ẩn khi tài liệu ở nơi khác giải thích rõ cách truyền biến đó:

```java
pathParameters(
    parameterWithName("tenantId").ignored(),
    parameterWithName("orderId")
        .description("Mã đơn hàng trong tenant"),
    parameterWithName("lineId")
        .description("Mã dòng hàng trong đơn")
)
```

**ignored()** không làm biến cha trở thành tùy chọn khi định tuyến và không bỏ qua kiểm tra quyền truy cập trong ứng dụng.

## 8. WebTestClient và REST Assured

Cùng một nhóm descriptor có thể sử dụng với các HTTP test client khác.

### 8.1. WebTestClient

Với WebTestClient đã được cấu hình tích hợp Spring REST Docs:

```java
webTestClient.get()
    .uri("/api/orders/{orderId}/lines/{lineId}", 42L, 7L)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("order-line-webtestclient",
        pathParameters(
            parameterWithName("orderId")
                .description("Mã đơn hàng chứa dòng hàng"),
            parameterWithName("lineId")
                .description("Mã dòng hàng trong đơn")
        )
    ));
```

Ở đây **document(...)** thuộc **WebTestClientRestDocumentation**. Client cần được thiết lập qua cơ chế REST Docs, ví dụ **documentationConfiguration(...)**. Hai biến trong **uri(...)** giữ đúng tên template và nhận giá trị theo thứ tự.

### 8.2. REST Assured

Với **RequestSpecification spec** đã cấu hình REST Docs:

```java
given(spec)
    .filter(document("order-line-rest-assured",
        pathParameters(
            parameterWithName("orderId")
                .description("Mã đơn hàng chứa dòng hàng"),
            parameterWithName("lineId")
                .description("Mã dòng hàng trong đơn")
        )
    ))
    .pathParam("orderId", 42L)
    .pathParam("lineId", 7L)
    .when()
    .get("/api/orders/{orderId}/lines/{lineId}")
    .then()
    .statusCode(200);
```

Ở đây **document(...)** thuộc **RestAssuredRestDocumentation**. Hai lệnh **pathParam(...)** cung cấp các giá trị; descriptor mô tả hai tên biến. Phần cấu hình REST Docs và request filter phải được khởi tạo trước khi chạy test.

## 9. Đưa snippet vào Asciidoctor và build/CI

Tệp **src/docs/asciidoc/index.adoc** có thể nhúng:

```asciidoc
= Order API
:toc: left

== Lấy dòng hàng trong đơn

GET /api/orders/{orderId}/lines/{lineId}

=== Path parameters

include::{snippets}/order-line-get/path-parameters.adoc[]

=== HTTP request

include::{snippets}/order-line-get/http-request.adoc[]

=== HTTP response

include::{snippets}/order-line-get/http-response.adoc[]
```

Ví dụ Gradle Groovy DSL khi dự án đã cài plugin **org.asciidoctor.jvm.convert**:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir
}
```

Quan hệ phụ thuộc đảm bảo bài kiểm thử sinh snippet trước khi Asciidoctor xử lý các lệnh **include**. Trong CI, chỉ xuất bản tài liệu nếu các bài kiểm thử REST Docs và tác vụ dựng tài liệu đều thành công. Nếu đổi tên **{lineId}** nhưng quên sửa descriptor hoặc URI test, lỗi có thể được phát hiện ngay ở bước test.

Spring REST Docs mặc định tạo snippet AsciiDoc. Nếu tài liệu cuối được xuất bản dưới dạng Markdown, cần cơ chế chuyển đổi hoặc mẫu snippet tương thích; cú pháp **include::...[]** thuộc Asciidoctor, không phải Markdown tiêu chuẩn.

## 10. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Thiếu một path parameter trong snippet | Quên descriptor cho một biến lồng nhau | Khai báo từng **parameterWithName(...)** |
| Descriptor không được tìm thấy | Tên sai hoặc có phân biệt hoa/thường | Đối chiếu chính xác tên trong URI template |
| Dòng hàng của đơn khác được trả về | Service chỉ tra cứu theo **lineId** | Kiểm tra đồng thời **orderId** và **lineId** |
| Không tìm thấy handler | Request thiếu segment ID cha hoặc con | Kiểm tra URI template và request |
| HTTP 400 khi truyền ID | Giá trị không chuyển đổi được sang kiểu Java | Kiểm tra kiểu path variable và giá trị |
| Snippet có ID nhưng mô tả mơ hồ | Description chỉ lặp lại tên kỹ thuật | Mô tả vai trò cha–con và phạm vi định danh |
| Tài liệu không có bảng path parameters | Chưa gọi **document(...)**, sai URI builder hoặc thiếu cấu hình | Kiểm tra test client và snippet output |
| Asciidoctor không tìm thấy snippet | Test chưa chạy hoặc sai thuộc tính **snippets** | Đảm bảo thứ tự test → asciidoctor và đường dẫn |
| URI lồng quá sâu, client khó dùng | Lạm dụng quan hệ dữ liệu để xếp path | Cân nhắc endpoint phẳng hoặc giảm cấp lồng |

## 11. Bài thực hành

Thiết kế API quản lý bình luận trong bài viết:

```text
GET /api/articles/{articleId}/comments/{commentId}
POST /api/articles/{articleId}/comments
```

Yêu cầu:

1. Tạo controller chi tiết nhận **articleId** và **commentId** bằng **@PathVariable**.
2. Tạo bài test MockMvc cho request chi tiết, kiểm tra status và hai trường ID trong JSON.
3. Dùng **pathParameters(...)** mô tả riêng ID bài viết và ID bình luận; sinh snippet với tên **article-comment-get**.
4. Viết service test bảo đảm bình luận thuộc bài viết được nêu; trường hợp comment tồn tại nhưng thuộc bài viết khác không được trả về như tài nguyên hợp lệ.
5. Tạo test cho route tạo bình luận; chỉ có **articleId** là path parameter. Dữ liệu bình luận nằm trong request body nên không được mô tả thành path parameter.
6. Nhúng snippet **path-parameters.adoc**, **request-fields.adoc** và các snippet cần thiết vào tài liệu Asciidoctor.
7. Chạy test → Asciidoctor trong build/CI; xác nhận tài liệu được tạo lại từ test.

Mẫu descriptor cho endpoint chi tiết:

```java
pathParameters(
    parameterWithName("articleId")
        .description("Mã bài viết chứa bình luận"),
    parameterWithName("commentId")
        .description("Mã bình luận cần lấy trong bài viết")
)
```

**Tiêu chí hoàn thành:** URI template và request có đủ biến; descriptor khớp từng tên; service xác minh quan hệ cha–con; snippet thể hiện đúng ý nghĩa hai ID; test và tài liệu chạy thành công trong pipeline.

## Ghi nhớ

URI template lồng nhau như **/api/orders/{orderId}/lines/{lineId}** biểu diễn tài nguyên con trong phạm vi tài nguyên cha. Mỗi biến là một path parameter độc lập và cần descriptor riêng bằng **parameterWithName(...)** bên trong **pathParameters(...)**. Tài liệu hóa đúng tên biến mới là một phần của hợp đồng: test nghiệp vụ còn phải xác minh con thuộc cha, quyền truy cập và các trường hợp không tìm thấy. Khi sinh snippet từ MockMvc, WebTestClient hoặc REST Assured rồi nhúng vào Asciidoctor và CI, tài liệu có thể phản ánh ổn định cách API nhận diện tài nguyên lồng nhau.

**Tài liệu tham khảo:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs RequestDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/RequestDocumentation.html), [Spring MVC @PathVariable](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/pathvariable.html) và [Spring MVC URI patterns](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html).
