# Document một phần response payload trong Spring REST Docs

## 1. Mục tiêu bài học

**Spring REST Docs** tạo tài liệu REST API có thể kiểm chứng từ những bài kiểm thử HTTP chạy bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**. Snippet được sinh từ request và response của ca kiểm thử đã chạy, sau đó được đưa vào tài liệu Asciidoctor/Markdown và quy trình build, CI.

Trong nhóm kiến thức **Subsection**, bài này tập trung vào một câu hỏi cụ thể:

> Khi response JSON có nhiều nhánh lồng nhau, làm thế nào để trích riêng một nhánh và document chính xác các field bên trong nhánh đó?

Ví dụ, endpoint lấy đơn hàng có thể trả về thông tin đơn, tổng tiền, các sản phẩm và thanh toán. Tài liệu tổng quan cần trình bày cấu trúc response; riêng phần `payment` cần một đoạn JSON và bảng mô tả field dễ đọc. Ta có thể sinh cả hai dạng tài liệu ngay từ **một lần thực thi kiểm thử**.

Sau bài học, bạn sẽ:

- Hiểu vai trò của `subsectionWithPath(...)` khi document response ở mức tổng quan.
- Dùng `beneathPath(...)` với `responseBody(...)` để sinh snippet của riêng một phần response.
- Dùng `beneathPath(...)` với `responseFields(...)` để document từng field của nhánh đã chọn, với path tương đối.
- Nhận biết các thay đổi schema mà kiểm thử strict có thể phát hiện.
- Biên soạn các snippet vào Asciidoctor và bảo đảm bước sinh tài liệu phụ thuộc vào bước chạy test.

## 2. Dữ liệu mẫu: response của API lấy đơn hàng

Giả sử `GET /orders/ord-1042` trả HTTP `200 OK` với header `Content-Type: application/json` và body:

```json
{
  "id": "ord-1042",
  "status": "PAID",
  "total": {
    "amount": 1250000,
    "currency": "VND"
  },
  "payment": {
    "method": "CARD",
    "state": "CAPTURED",
    "card": {
      "brand": "VISA",
      "last4": "4242"
    },
    "transactionId": "txn-demo-001"
  },
  "items": [
    {
      "sku": "BOOK-001",
      "quantity": 2
    }
  ]
}
```

Ở ví dụ này:

- `id` và `status` là thông tin cấp gốc.
- `total`, `payment` và `items` là các nhánh con.
- Nhánh `payment` chứa thông tin về phương thức, trạng thái, chi tiết thẻ đã rút gọn và mã giao dịch.

Nhánh `payment` là **subsection** mà chúng ta muốn trình bày riêng. REST Docs cung cấp hai cách phối hợp để làm điều đó:

| Mục tiêu | Cách gọi | Ý nghĩa |
| --- | --- | --- |
| Nêu `payment` là một khối trong bảng tổng quan | `subsectionWithPath("payment")` bên trong `responseFields(...)` | Document một nhánh ở cấp tổng quan, bao gồm các hậu duệ cho việc kiểm tra field của snippet này. |
| Sinh riêng phần JSON của `payment` | `responseBody(beneathPath("payment"))` | Trích đoạn body theo path đã chọn. |
| Tạo bảng chi tiết các field thuộc `payment` | `responseFields(beneathPath("payment"), ...)` | Mô tả và kiểm tra field bên trong subsection; các path descriptor tính từ gốc của nhánh được trích. |

**Phân biệt quan trọng:** `subsectionWithPath` là **descriptor** mô tả cả nhánh, còn `beneathPath` là **extractor** chọn nhánh để tạo snippet body hoặc bảng field. `subsectionWithPath` không tự động sinh JSON riêng của nhánh và cũng không xác minh đầy đủ các field con.

## 3. Kiểm thử MockMvc tạo ba snippet tài liệu

Đây là ví dụ tự chứa dùng **JUnit 5**, **MockMvc**, **Spring MVC** và **Spring REST Docs**. Controller mô phỏng trả response JSON cố định để tập trung vào cơ chế sinh tài liệu. Trong ứng dụng thực tế, hãy dùng controller thật cùng dữ liệu kiểm thử ổn định.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseBody;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class OrderResponseDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders
                .standaloneSetup(new SampleOrderController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentPaymentSubsection() throws Exception {
        mockMvc.perform(get("/orders/{orderId}", "ord-1042")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.payment.state").value("CAPTURED"))
                .andDo(document("orders-get",

                        // (1) Tổng quan response cấp gốc.
                        responseFields(
                                fieldWithPath("id")
                                        .description("Mã đơn hàng"),
                                fieldWithPath("status")
                                        .description("Trạng thái đơn hàng"),
                                subsectionWithPath("total")
                                        .description("Tổng tiền và đơn vị tiền tệ"),
                                subsectionWithPath("payment")
                                        .description("Thông tin thanh toán"),
                                subsectionWithPath("items")
                                        .description("Các sản phẩm thuộc đơn hàng")
                        ),

                        // (2) Phần JSON dành riêng cho payment.
                        responseBody(beneathPath("payment")
                                .withSubsectionId("payment")),

                        // (3) Bảng field chi tiết trong payment.
                        responseFields(
                                beneathPath("payment")
                                        .withSubsectionId("payment"),
                                fieldWithPath("method")
                                        .description("Phương thức thanh toán"),
                                fieldWithPath("state")
                                        .description("Trạng thái xử lý thanh toán"),
                                fieldWithPath("card.brand")
                                        .description("Thương hiệu thẻ"),
                                fieldWithPath("card.last4")
                                        .description("Bốn chữ số cuối của thẻ"),
                                fieldWithPath("transactionId")
                                        .optional()
                                        .description("Mã giao dịch nếu đã có")
                        )
                ));
    }

    @RestController
    public static class SampleOrderController {

        @GetMapping(value = "/orders/{orderId}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<String> getOrder(
                @PathVariable String orderId) {

            if (!"ord-1042".equals(orderId)) {
                return ResponseEntity.notFound().build();
            }

            String response = """
                    {
                      "id": "ord-1042",
                      "status": "PAID",
                      "total": {
                        "amount": 1250000,
                        "currency": "VND"
                      },
                      "payment": {
                        "method": "CARD",
                        "state": "CAPTURED",
                        "card": {
                          "brand": "VISA",
                          "last4": "4242"
                        },
                        "transactionId": "txn-demo-001"
                      },
                      "items": [
                        {
                          "sku": "BOOK-001",
                          "quantity": 2
                        }
                      ]
                    }
                    """;

            return ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(response);
        }
    }
}
```

Phần thử nghiệm cần classpath có JUnit Jupiter, Spring MVC Test và `spring-restdocs-mockmvc`. Đoạn ví dụ dùng Java 17+ vì có text block. Khi áp dụng vào controller thật, việc kiểm tra HTTP status, header và dữ liệu nghiệp vụ trước `document(...)` vẫn cần thiết để snippet phản ánh response đúng.

### 3.1. Bảng response tổng quan

Đoạn:

```java
responseFields(
    fieldWithPath("id").description("Mã đơn hàng"),
    fieldWithPath("status").description("Trạng thái đơn hàng"),
    subsectionWithPath("total").description("Tổng tiền và đơn vị tiền tệ"),
    subsectionWithPath("payment").description("Thông tin thanh toán"),
    subsectionWithPath("items").description("Các sản phẩm thuộc đơn hàng")
)
```

sinh bảng mô tả năm thành phần cấp gốc. `subsectionWithPath("payment")` cho REST Docs biết nhánh này đã được mô tả ở mức tổng quan, nên các field như `payment.card.last4` không phải xuất hiện thành từng hàng trong bảng tổng quan. Tương tự, `total.amount` và `items[].sku` nằm dưới hai subsection đã được mô tả tổng quan.

Nhờ đó bảng mở đầu ngắn gọn, nhưng có một giới hạn: chỉ có bảng này thì khi API thêm `payment.providerCode`, kiểm thử có thể **không phát hiện** field con mới, vì descriptor của subsection bao phủ cả nhánh. Để giữ tính kiểm chứng ở mức chi tiết, phần tiếp theo bổ sung một bảng riêng cho `payment`.

### 3.2. Snippet body riêng cho subsection

Đoạn:

```java
responseBody(beneathPath("payment").withSubsectionId("payment"))
```

chọn nhánh `payment` trong response và yêu cầu REST Docs sinh snippet body riêng. Đoạn trích liên quan đến các dữ liệu:

```json
{
  "method": "CARD",
  "state": "CAPTURED",
  "card": {
    "brand": "VISA",
    "last4": "4242"
  },
  "transactionId": "txn-demo-001"
}
```

Đây là **nội dung khái niệm của nhánh được chọn**; định dạng văn bản cuối cùng phụ thuộc vào cách REST Docs trích xuất và template snippet đang sử dụng. Điều quan trọng là đoạn trích không còn chứa `id`, `status`, `total` và `items` của response cấp gốc.

`withSubsectionId("payment")` đặt ID dễ nhận biết để tên snippet ổn định và thuận tiện cho lệnh `include` của Asciidoctor.

### 3.3. Bảng field chi tiết và đường dẫn tương đối

Khi dùng:

```java
responseFields(
    beneathPath("payment").withSubsectionId("payment"),
    fieldWithPath("method").description("Phương thức thanh toán"),
    fieldWithPath("state").description("Trạng thái xử lý thanh toán"),
    fieldWithPath("card.brand").description("Thương hiệu thẻ"),
    fieldWithPath("card.last4").description("Bốn chữ số cuối của thẻ"),
    fieldWithPath("transactionId").optional()
        .description("Mã giao dịch nếu đã có")
)
```

REST Docs kiểm tra **phần response nằm bên dưới `payment`**. Do đó, các path descriptor phải tính từ gốc của subsection:

| Truy cập từ response gốc | Path trong `responseFields(beneathPath("payment"), ...)` |
| --- | --- |
| `payment.method` | `method` |
| `payment.state` | `state` |
| `payment.card.brand` | `card.brand` |
| `payment.card.last4` | `card.last4` |
| `payment.transactionId` | `transactionId` |

Nếu nhầm `fieldWithPath("payment.state")` trong bảng chi tiết, REST Docs sẽ tìm một field `payment` **nằm bên trong** phần `payment` đã trích, dẫn tới lỗi tài liệu.

`optional()` trên `transactionId` cho phép response hợp lệ chưa có mã giao dịch. Trong ví dụ hiện tại, response có field đó; để kiểm tra chính xác tính tùy chọn, nên có thêm test với trạng thái thanh toán chưa tạo mã giao dịch.

## 4. Tên snippet và cách nhúng vào Asciidoctor

Với identifier `orders-get`, test trên sinh các snippet liên quan trong thư mục output được cấu hình, thường là `build/generated-snippets/orders-get/` với Gradle:

| Snippet | Nội dung |
| --- | --- |
| `http-response.adoc` | Toàn bộ HTTP response, gồm status, header và body. |
| `response-body.adoc` | Toàn bộ body của response. |
| `response-fields.adoc` | Bảng mô tả tổng quan năm thành phần cấp gốc. |
| `response-body-payment.adoc` | Body của phần response được chọn bằng `beneathPath("payment")`. |
| `response-fields-payment.adoc` | Bảng field bên trong `payment`. |

Tên hai snippet cuối đến từ `withSubsectionId("payment")`. Nếu bỏ `withSubsectionId`, REST Docs đặt subsection ID theo path dưới dạng `beneath-<path>`; tên file phụ thuộc vào ID mặc định đó. Vì vậy, chỉ nên tự đặt ID khi có nhu cầu đặt tên ổn định, rõ nghĩa cho tài liệu.

Ví dụ tài liệu `src/docs/asciidoc/orders.adoc`:

```asciidoc
= API đơn hàng
:toc: left

== GET /orders/{orderId}

Truy vấn trạng thái đơn hàng và thông tin thanh toán.

=== HTTP response mẫu

include::{snippets}/orders-get/http-response.adoc[]

=== Các trường của response

include::{snippets}/orders-get/response-fields.adoc[]

=== Chi tiết JSON phần thanh toán

include::{snippets}/orders-get/response-body-payment.adoc[]

=== Các trường thuộc phần thanh toán

include::{snippets}/orders-get/response-fields-payment.adoc[]
```

Giá trị `snippets` phải được cấu hình trỏ đến thư mục sinh snippet. Ví dụ biên soạn trên sử dụng định dạng Asciidoctor mặc định. Muốn dùng snippet Markdown thì phải cấu hình template/output tương ứng và thay đổi cách kết hợp các tệp trong tài liệu.

## 5. Tích hợp vào build và CI

Một nguyên tắc quan trọng của Spring REST Docs là **tài liệu gắn với bài kiểm thử HTTP**. Nếu test thất bại vì API trả payload sai hoặc thiếu field bắt buộc, quá trình build tài liệu không nên công bố snippet cũ như thể nó vẫn hợp lệ.

Ví dụ Gradle (Groovy DSL), giả định dự án đã áp dụng plugin Asciidoctor và task `test` đã có dependency REST Docs:

```groovy
dependencies {
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}

def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
    attributes 'snippets': snippetsDir
}
```

Trong CI có thể chạy:

```bash
./gradlew clean test asciidoctor
```

Hệ thống CI phải có JDK thích hợp, dependencies của test và plugin tạo tài liệu. Lệnh trên chạy kiểm thử trước khi dựng Asciidoctor, giúp chặn việc phát hành tài liệu khi ca kiểm thử liên quan thất bại. Với dự án Maven, đường dẫn snippet thông dụng là `target/generated-snippets` và build lifecycle cần được cấu hình để kiểm thử chạy trước bước sinh tài liệu.

Để CI đáng tin cậy hơn, hãy giữ dữ liệu test ổn định và không ghi response chứa thông tin nhạy cảm thực vào snippet. Ví dụ này chỉ sử dụng dữ liệu giả, kèm `card.last4` thay cho số thẻ đầy đủ.

## 6. Strict response documentation phát hiện gì?

`responseFields(...)` mặc định kiểm tra chặt (*strict*). Các field trong phạm vi snippet phải có descriptor phù hợp, trừ khi bạn chủ ý dùng cơ chế nới lỏng.

| Trường hợp | Điều có thể xảy ra |
| --- | --- |
| Thêm `payment.gatewayReference` vào JSON nhưng chưa thêm descriptor trong bảng `beneathPath("payment")` | Test thất bại do field chưa được document. |
| Xóa `payment.state` nhưng descriptor `state` vẫn bắt buộc | Test thất bại do field được document không tồn tại. |
| Xóa `payment.transactionId` khi descriptor có `optional()` | Bảng field vẫn hợp lệ. |
| Thêm `total.tax` nhưng chỉ có `subsectionWithPath("total")` ở bảng gốc | Bảng tổng quan vẫn có thể hợp lệ vì nhánh `total` được bao phủ. |
| Response từ endpoint đổi sang body rỗng trong test dùng `beneathPath("payment")` | Không thể trích nhánh như kỳ vọng; cần xác minh kịch bản và path. |

Các descriptor liên quan:

- **`fieldWithPath("x")`:** mô tả một field theo đường dẫn JSON.
- **`subsectionWithPath("x")`:** mô tả cả nhánh `x` và tính các hậu duệ trong nhánh là đã document cho snippet hiện tại.
- **`optional()`:** đánh dấu field có thể vắng mặt trong response.
- **`ignored()`:** cho phép một field đã biết không xuất hiện trong bảng nhưng vẫn được xử lý trong kiểm tra document; nên sử dụng có chủ đích.
- **`relaxedResponseFields(...)`:** giảm ràng buộc đối với các field chưa document, hữu ích trong tài liệu chọn lọc nhưng dễ bỏ sót thay đổi schema nếu lạm dụng.
- **`beneathPath("x")`:** chọn subtree để `responseBody(...)` hoặc `responseFields(...)` làm việc trong phạm vi đó.

Chẳng hạn, nếu `payment` có thêm field tùy biến không cần đưa vào bảng, có thể dùng `ignored()` cho đúng path thay vì nới lỏng toàn bộ snippet. Nếu API có contract cố định, bảng chi tiết strict giúp phát hiện sớm thay đổi ngoài dự kiến.

## 7. Xử lý path cho object và array

### Object lồng nhau

Path của field JSON có dấu chấm để biểu thị các cấp object. Khi document từ root, dùng `payment.card.brand`; khi đã trích `payment` bằng `beneathPath`, dùng `card.brand`. Với những key JSON chứa dấu chấm theo nghĩa ký tự (ví dụ `"card.brand"` là tên nguyên vẹn của key), cần cú pháp path dành cho key đặc biệt thay vì suy diễn dấu chấm như phân tách object.

### Mảng trong response

Với response:

```json
{
  "items": [
    { "sku": "BOOK-001", "quantity": 2 },
    { "sku": "PEN-002", "quantity": 1 }
  ]
}
```

Nếu muốn document trực tiếp các field của từng phần tử mảng từ **root**, có thể dùng:

```java
responseFields(
    fieldWithPath("items[].sku")
        .description("Mã sản phẩm"),
    fieldWithPath("items[].quantity")
        .description("Số lượng")
)
```

Ký hiệu `[]` biểu thị các phần tử của mảng. Với response lớn có nhiều nhóm, bạn có thể dùng bảng tổng quan kết hợp tài liệu chi tiết của từng nhóm; trước khi dùng `beneathPath(...)` cho một cấu trúc mảng, hãy xác nhận path chỉ đúng phần cần trích và descriptor được khai báo tương đối với phần trích đó.

### Response có nhiều biến thể

Một API có thể trả các cấu trúc khác nhau theo trạng thái đơn hàng:

- `PAID` có `payment.transactionId`.
- `PENDING` chưa có `payment.transactionId`.
- `CANCELLED` có thể không chứa `payment`.

Nếu contract thật sự cho phép các biến thể này, hãy viết **các test HTTP tương ứng**. Với biến thể không chứa `payment`, không gọi extractor `beneathPath("payment")` vì nhánh cần trích không tồn tại. Chỉ dùng `optional()` khi chính field đó tùy chọn theo contract; `optional()` không thể tạo ra một subsection vắng mặt để extractor xử lý.

## 8. Tương đương khi dùng WebTestClient và REST Assured

Phần trích payload và các descriptor thuộc `PayloadDocumentation`, nên chiến lược document subsection vẫn giống nhau. Thay đổi chủ yếu ở nơi gắn bộ xử lý `document(...)` vào HTTP exchange.

**WebTestClient:** giả sử `webTestClient` đã được cấu hình với Spring REST Docs và `document` được static import từ `WebTestClientRestDocumentation`:

```java
webTestClient.get()
    .uri("/orders/ord-1042")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.payment.state").isEqualTo("CAPTURED")
    .consumeWith(document("orders-webtestclient",
        responseFields(
            beneathPath("payment").withSubsectionId("payment"),
            fieldWithPath("method").description("Phương thức"),
            fieldWithPath("state").description("Trạng thái"),
            fieldWithPath("card.brand").description("Thương hiệu thẻ"),
            fieldWithPath("card.last4").description("Bốn số cuối"),
            fieldWithPath("transactionId").optional()
                .description("Mã giao dịch")
        )
    ));
```

**REST Assured:** giả sử `spec` là `RequestSpecification` có bộ lọc cấu hình REST Docs và `document` được static import từ `RestAssuredRestDocumentation`:

```java
RestAssured.given(spec)
    .accept("application/json")
    .filter(document("orders-restassured",
        responseBody(
            beneathPath("payment").withSubsectionId("payment")
        )
    ))
    .when()
    .get("/orders/ord-1042")
    .then()
    .statusCode(200);
```

Cả ba công cụ đều sử dụng HTTP exchange thật trong bài kiểm thử để lấy dữ liệu sinh snippet; các đoạn trên chỉ minh họa cách gắn response snippet, chưa thay thế phần thiết lập toàn bộ môi trường test.

## 9. Lỗi thường gặp khi document một phần response

| Hiện tượng | Nguyên nhân có thể | Hướng giải quyết |
| --- | --- | --- |
| `responseFields` báo thiếu field hoặc path sai | Dùng `payment.state` trong bảng đã trích `payment` | Đổi path thành `state` vì path tương đối với subsection. |
| `responseFields` báo field chưa được document | JSON trả thêm field trong subsection strict | Bổ sung descriptor hoặc chủ động đánh dấu `ignored()` khi phù hợp. |
| Test pass dù response có field con mới | Bảng tổng quan chỉ có `subsectionWithPath(...)` | Thêm bảng `responseFields(beneathPath(...), ...)` để kiểm chứng nhánh. |
| Không sinh `response-body-payment.adoc` | Chưa gọi `responseBody(beneathPath(...))` hoặc ID bị đổi | Kiểm tra identifier, subsection ID và kết quả chạy test. |
| Không trích được `payment` | Response của ca kiểm thử thiếu nhánh hoặc path sai chữ hoa/chữ thường | Kiểm tra body nhận được và contract của biến thể response. |
| Asciidoctor báo thiếu snippet | Đường dẫn `snippets` sai, test chưa chạy hoặc tên file không khớp | Kiểm tra cấu hình build, thư mục output và tên file thực tế. |
| Snippet chứa dữ liệu không nên công khai | Test dùng thông tin người dùng hoặc giao dịch thực | Dùng fixture giả, loại bỏ/redact dữ liệu nhạy cảm trước khi tạo tài liệu. |

## 10. Bài thực hành

Bắt đầu từ kiểm thử `OrderResponseDocumentationTest` ở mục 3:

1. **Kiểm chứng strict:** thêm `payment.gatewayReference` vào JSON controller nhưng không thay các descriptor. Chạy test và quan sát lỗi field chưa document; sau đó khai báo `fieldWithPath("gatewayReference").description("Mã tham chiếu cổng thanh toán")` vào bảng chi tiết.
2. **Kiểm chứng optional:** bỏ `transactionId` khỏi response; giữ `optional()` và xác nhận tài liệu vẫn sinh. Bỏ `optional()` rồi chạy lại để thấy khác biệt.
3. **Document nhánh khác:** thêm `responseBody(beneathPath("total").withSubsectionId("total"))` và một bảng `responseFields(beneathPath("total").withSubsectionId("total"), ...)` cho `amount`, `currency`. Cập nhật Asciidoctor để nhúng hai snippet mới.
4. **Kiểm tra biến thể:** viết test cho đơn hàng chưa thanh toán, trong đó `payment.transactionId` chưa có. Chỉ ghi snippet khi các assertion về trạng thái HTTP và dữ liệu nghiệp vụ đều pass.
5. **Tích hợp build:** chạy `./gradlew clean test asciidoctor` và mở trang HTML xuất ra. Đối chiếu các snippet với body response mà test sử dụng.

**Tiêu chí hoàn thành:** bạn có thể giải thích vì sao `subsectionWithPath` không bảo đảm kiểm tra mọi field con, chọn `beneathPath` để trích phần JSON, dùng path tương đối trong bảng field chi tiết, và kiểm tra được thay đổi schema response qua kết quả test.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): cách mô tả field và subsection trong request/response payload.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): cấu hình kiểm thử, template snippet, Asciidoctor và tích hợp build.

