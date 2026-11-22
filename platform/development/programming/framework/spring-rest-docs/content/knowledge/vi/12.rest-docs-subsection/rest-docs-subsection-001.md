# Document một phần request payload trong Spring REST Docs

## 1. Mục tiêu và bối cảnh

**Spring REST Docs** tạo tài liệu REST API từ những bài kiểm thử HTTP thực sự chạy qua **MockMvc**, **WebTestClient** hoặc **REST Assured**. Khi kiểm thử thành công, công cụ sinh các *snippet* mô tả request, response, payload, header và tham số. Những snippet này có thể được đưa vào tài liệu Asciidoctor hoặc Markdown và chạy trong quy trình build/CI.

Bài học thuộc nhóm **Subsection**, tập trung vào việc **document một phần request payload**: một request JSON có thể chứa nhiều nhánh lồng nhau, nhưng người đọc đôi khi chỉ cần xem riêng nhánh địa chỉ giao hàng, thông tin thanh toán hoặc một nhóm thuộc tính cụ thể.

Sau bài này, bạn có thể:

- Phân biệt mô tả tổng quan một nhánh với tách riêng nhánh đó để document chi tiết.
- Dùng `subsectionWithPath(...)`, `beneathPath(...)`, `requestFields(...)` và `requestBody(...)` đúng mục đích.
- Tạo một kiểm thử MockMvc sinh nhiều snippet từ cùng một request và đưa chúng vào tài liệu Asciidoctor.
- Hiểu cơ chế kiểm tra field bắt buộc, field chưa được document, field tùy chọn và lỗi khi chọn sai đường dẫn.

## 2. Ba cách nhìn một phần payload

Giả sử endpoint `POST /orders` nhận JSON:

```json
{
  "customerId": "cus-17",
  "shippingAddress": {
    "recipient": "Nguyen Lan",
    "street": "12 Nguyen Hue",
    "city": "Ho Chi Minh City",
    "postalCode": "700000"
  },
  "items": [
    {
      "sku": "BOOK-01",
      "quantity": 2
    }
  ]
}
```

Ở đây, `shippingAddress` là một **subsection** (nhánh con) của payload. Có ba nhu cầu khác nhau:

| Nhu cầu | API phù hợp | Kết quả |
| --- | --- | --- |
| Chỉ giới thiệu `shippingAddress` là một khối dữ liệu | `requestFields(subsectionWithPath("shippingAddress").description(...))` | Bảng field có một hàng cho `shippingAddress`; các field con được xem là đã document trong *snippet đó*. |
| Hiển thị riêng JSON của địa chỉ giao hàng | `requestBody(beneathPath("shippingAddress"))` | Snippet body chỉ chứa phần JSON được trích xuất. |
| Giải thích từng field nằm trong địa chỉ giao hàng | `requestFields(beneathPath("shippingAddress"), fieldWithPath(...), ...)` | Bảng riêng cho các field của `shippingAddress`; đường dẫn trong bảng tính **tương đối** với nhánh đã chọn. |

**Phân biệt quan trọng:**

- `subsectionWithPath("shippingAddress")` là một *field descriptor*. Nó thông báo rằng nhánh `shippingAddress` và toàn bộ hậu duệ được tính là đã document trong bảng field hiện tại; bản thân nó **không tạo snippet JSON riêng**.
- `beneathPath("shippingAddress")` là một *subsection extractor*. Nó trích xuất nhánh để `requestBody(...)` xuất body hoặc `requestFields(...)` kiểm tra và mô tả các field **bên trong** nhánh.
- Hai công cụ có thể dùng cùng lúc: bảng tổng quan document request ở cấp gốc, bảng chi tiết document địa chỉ giao hàng và đoạn body riêng giúp người đọc nhìn thấy cấu trúc dữ liệu.

## 3. Ví dụ đầy đủ với MockMvc

Ví dụ dưới dùng **JUnit 5**, **Java 17+**, **MockMvc** và extension của Spring REST Docs. Controller mẫu được khai báo ngay trong bài kiểm thử để ví dụ độc lập với logic nghiệp vụ và cơ sở dữ liệu. Trong dự án thật, thay controller mẫu bằng controller/bean của ứng dụng.

```java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestBody;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders
                .standaloneSetup(new ExampleOrderController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentShippingAddressSubsection() throws Exception {
        String requestJson = """
                {
                  "customerId": "cus-17",
                  "shippingAddress": {
                    "recipient": "Nguyen Lan",
                    "street": "12 Nguyen Hue",
                    "city": "Ho Chi Minh City",
                    "postalCode": "700000"
                  },
                  "items": [
                    { "sku": "BOOK-01", "quantity": 2 }
                  ]
                }
                """;

        this.mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(requestJson))
                .andExpect(status().isCreated())
                .andDo(document("orders-create",

                        // (1) Mô tả request ở cấp gốc.
                        requestFields(
                                fieldWithPath("customerId")
                                        .description("Mã khách hàng tạo đơn"),
                                subsectionWithPath("shippingAddress")
                                        .description("Địa chỉ giao hàng"),
                                subsectionWithPath("items")
                                        .description("Danh sách sản phẩm đặt mua")
                        ),

                        // (2) Trích riêng phần JSON của shippingAddress.
                        requestBody(beneathPath("shippingAddress")
                                .withSubsectionId("shipping")),

                        // (3) Mô tả chi tiết các field của subsection.
                        requestFields(
                                beneathPath("shippingAddress")
                                        .withSubsectionId("shipping"),
                                fieldWithPath("recipient")
                                        .description("Tên người nhận"),
                                fieldWithPath("street")
                                        .description("Địa chỉ đường, số nhà"),
                                fieldWithPath("city")
                                        .description("Thành phố giao hàng"),
                                fieldWithPath("postalCode")
                                        .optional()
                                        .description("Mã bưu chính, có thể bỏ qua")
                        )
                ));
    }

    @RestController
    static class ExampleOrderController {

        @PostMapping("/orders")
        public ResponseEntity<Map<String, String>> create(
                @RequestBody Map<String, Object> request) {
            return ResponseEntity.status(HttpStatus.CREATED)
                    .body(Map.of("id", "ord-001"));
        }
    }
}
```

Điều kiện để đoạn mã chạy: test classpath có JUnit Jupiter, Spring MVC Test và Spring REST Docs MockMvc; dự án đã cấu hình thư mục output snippet (thông dụng là `build/generated-snippets`). Đây là ví dụ cho request JSON: `contentType(MediaType.APPLICATION_JSON)` cho phép REST Docs nhận diện đúng kiểu payload.

### Giải thích các điểm quyết định

**(1) Bảng cấp gốc có kiểm tra cấu trúc.** `requestFields(...)` ở chế độ mặc định là *strict*: khi request xuất hiện một field chưa được mô tả, kiểm thử có thể thất bại. `customerId` được mô tả trực tiếp, còn `shippingAddress` và `items` dùng `subsectionWithPath(...)` nên các field con tương ứng được tính là đã bao phủ. Bảng tổng quan chỉ có ba hàng chính, thích hợp để giới thiệu hình dạng request.

**(2) Cắt phần body cần nhấn mạnh.** `requestBody(beneathPath("shippingAddress").withSubsectionId("shipping"))` tạo một snippet chứa JSON của riêng nhánh địa chỉ. Trong trường hợp này, nó có nội dung tương đương:

```json
{
  "shippingAddress": {
    "recipient": "Nguyen Lan",
    "street": "12 Nguyen Hue",
    "city": "Ho Chi Minh City",
    "postalCode": "700000"
  }
}
```

Snippet vẫn giữ tên phần tử `shippingAddress` để người đọc thấy nhánh này nằm ở đâu. Nó không chứa `customerId` hay `items`.

**(3) Bảng chi tiết kiểm tra độc lập nhánh được chọn.** Vì extractor đã chọn `shippingAddress`, các path tương ứng là `recipient`, `street`, `city` và `postalCode`, **không phải** `shippingAddress.recipient` hay `shippingAddress.city`. `postalCode` được đánh dấu `optional()`: nếu field này vắng mặt, test vẫn hợp lệ; ba field còn lại phải có trong payload của ca kiểm thử.

Một điểm dễ nhầm: việc bảng cấp gốc dùng `subsectionWithPath("shippingAddress")` **không làm mất** kiểm tra chi tiết của bảng thứ ba. Mỗi `requestFields(...)` là một snippet riêng, với phạm vi và descriptor riêng. Vì vậy có thể vừa có bản mô tả tổng quan, vừa có bản kiểm tra đầy đủ field của nhánh.

## 4. Snippet được sinh và cách biên soạn tài liệu

Với identifier `orders-create` và subsection ID `shipping`, khi kiểm thử chạy thành công, REST Docs sẽ sinh (ngoài các snippet mặc định) những tệp chính sau trong thư mục `build/generated-snippets/orders-create/`:

| Tệp | Nội dung |
| --- | --- |
| `http-request.adoc` | HTTP request thực tế đã kiểm thử. |
| `request-body.adoc` | Toàn bộ request body (snippet mặc định). |
| `request-fields.adoc` | Bảng field ở cấp gốc: `customerId`, `shippingAddress`, `items`. |
| `request-body-shipping.adoc` | Body trích riêng cho nhánh `shippingAddress`. |
| `request-fields-shipping.adoc` | Bảng field chi tiết `recipient`, `street`, `city`, `postalCode`. |

Nếu không gọi `withSubsectionId("shipping")`, mặc định ID của subsection có dạng `beneath-<path>`. Ví dụ path `shippingAddress` tạo các tên như `request-body-beneath-shippingAddress.adoc` và `request-fields-beneath-shippingAddress.adoc`. Dùng ID dễ đọc giúp ổn định tên snippet khi tên path thay đổi có chủ đích.

Trong file tài liệu Asciidoctor, với biến `snippets` đã trỏ tới thư mục output, có thể viết:

```asciidoc
= Tạo đơn hàng
:toc: left

== POST /orders

Tạo đơn hàng từ mã khách hàng, địa chỉ giao hàng và danh sách sản phẩm.

=== Ví dụ HTTP request
include::{snippets}/orders-create/http-request.adoc[]

=== Cấu trúc request tổng quan
include::{snippets}/orders-create/request-fields.adoc[]

=== JSON địa chỉ giao hàng
include::{snippets}/orders-create/request-body-shipping.adoc[]

=== Các field của địa chỉ giao hàng
include::{snippets}/orders-create/request-fields-shipping.adoc[]
```

Ví dụ cấu hình Gradle (Groovy DSL) sau giả định dự án đã áp dụng plugin Asciidoctor và có task `test`/`asciidoctor`. Nó thể hiện mối liên hệ build: tài liệu được dựng sau khi kiểm thử sinh snippet.

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
}
```

Trong build thực tế, cần cấu hình REST Docs ghi snippet vào cùng thư mục và truyền thuộc tính `snippets` cho Asciidoctor. Khi chọn template Markdown thay Asciidoctor, đuôi và cú pháp nhúng snippet sẽ khác; ví dụ trong bài sử dụng cấu hình Asciidoctor mặc định.

## 5. Nên chọn cách nào trong từng tình huống?

### Chỉ cần mô tả ý nghĩa cả một khối

Ví dụ tài liệu API nhận metadata linh hoạt, nhưng ở cấp tổng quan chỉ cần ghi "metadata tùy chỉnh của khách hàng":

```java
requestFields(
    fieldWithPath("name").description("Tên hiển thị"),
    subsectionWithPath("metadata")
        .description("Nhóm thuộc tính tùy chỉnh")
)
```

`subsectionWithPath` giúp bảng ngắn gọn. Đổi lại, test này không xác minh từng field con của `metadata`; nếu cấu trúc bên trong quan trọng, cần thêm một snippet/test chi tiết.

### Cần mô tả từng thuộc tính của phần payload

Dùng `beneathPath` với `requestFields`:

```java
requestFields(
    beneathPath("shippingAddress")
        .withSubsectionId("shipping-details"),
    fieldWithPath("recipient").description("Tên người nhận"),
    fieldWithPath("street").description("Địa chỉ đường, số nhà"),
    fieldWithPath("city").description("Thành phố"),
    fieldWithPath("postalCode").optional().description("Mã bưu chính")
)
```

Đây là lựa chọn tốt khi người triển khai client phải biết chính xác schema của riêng một khối, đặc biệt khi request lớn.

### Chỉ cần trích một ví dụ JSON dễ đọc

Dùng `requestBody(beneathPath(...))`. Snippet body giúp người đọc hình dung payload con, nhưng **không thay thế** việc mô tả và kiểm tra từng field bằng `requestFields(...)` nếu cần bảo vệ schema.

## 6. Quy tắc path và tác động đến tính kiểm chứng

### Path tuyệt đối so với path tương đối

Với JSON ở đầu bài:

| Ngữ cảnh | Path hợp lệ | Ý nghĩa |
| --- | --- | --- |
| `requestFields(...)` cấp gốc | `shippingAddress.city` | Trỏ từ root đến thành phố. |
| `requestFields(...)` cấp gốc | `shippingAddress` | Trỏ đến toàn bộ nhánh địa chỉ. |
| `requestFields(beneathPath("shippingAddress"), ...)` | `city` | Trỏ đến thành phố bên trong nhánh đã trích. |
| `requestFields(beneathPath("shippingAddress"), ...)` | `postalCode` | Trỏ đến mã bưu chính bên trong nhánh đã trích. |

Với mảng JSON, cú pháp đường dẫn dùng `[]`: ví dụ `items[].sku` và `items[].quantity` khi document ở cấp gốc. Với key chứa dấu chấm, có thể dùng bracket notation như `['shipping.address']` để dấu chấm được hiểu là một phần của key. Path cần phù hợp với cấu trúc JSON thật; REST Docs không tự suy luận tên field từ DTO của Java.

### Strict, optional, ignored và relaxed

- **`requestFields(...)` (strict):** lỗi nếu có field trong phạm vi kiểm tra chưa được document hoặc field được document là bắt buộc nhưng không xuất hiện. Với `beneathPath`, phạm vi áp dụng là subsection đã chọn.
- **`optional()`:** chấp nhận field vắng mặt; nên dùng cho dữ liệu hợp đồng cho phép client bỏ qua, không phải cách che một path gõ sai.
- **`ignored()`:** field/nhánh có thể được tính là đã bao phủ mà không xuất hiện trong bảng. Chỉ nên dùng khi thực sự chủ ý loại khỏi tài liệu; một ví dụ là field kỹ thuật nội bộ đã biết.
- **`relaxedRequestFields(...)`:** không gây lỗi vì field chưa được document. Vẫn kiểm tra sự hiện diện của các descriptor bắt buộc đã khai báo. Hữu ích cho tài liệu theo từng kịch bản, nhưng kém hiệu quả hơn strict khi muốn phát hiện schema thay đổi ngoài ý muốn.
- **`subsectionWithPath(...)`:** bao phủ cả nhánh con trong chính snippet đó; thích hợp cho trình bày cấp cao. Nếu muốn kiểm tra các field con, khai báo thêm snippet chi tiết bằng `beneathPath(...)`.

Ví dụ một thay đổi đáng chú ý: nhà phát triển thêm `shippingAddress.country` vào request. Bảng tổng quan dùng `subsectionWithPath("shippingAddress")` sẽ vẫn cho qua, nhưng bảng chi tiết **strict** dùng `beneathPath("shippingAddress")` có thể thất bại do `country` chưa được document. Nhờ vậy, thay đổi schema buộc người viết cập nhật tài liệu hoặc xác định rõ lý do không mô tả field mới.

### Trường hợp subsection vắng mặt

`beneathPath("shippingAddress")` cần tìm được nhánh tương ứng trong request dùng để sinh snippet. Nếu API cho phép hoàn toàn bỏ `shippingAddress`, hãy dùng **ca kiểm thử có địa chỉ** để sinh tài liệu chi tiết và một ca kiểm thử riêng xác nhận hành vi request **không có địa chỉ**. Đừng chỉ thêm `optional()` cho descriptor cấp gốc rồi cho rằng extractor luôn hoạt động khi nhánh không tồn tại.

## 7. Áp dụng với WebTestClient hoặc REST Assured

Cơ chế document phần payload nằm ở `PayloadDocumentation`, nên mô tả field và extractor có thể tái sử dụng giữa các công cụ kiểm thử. Điều thay đổi là nơi gắn `document(...)` vào request/response.

**Với WebTestClient**, giả sử `webTestClient` đã được cấu hình Spring REST Docs:

```java
webTestClient.post()
    .uri("/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(requestJson)
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("orders-webtestclient",
        requestFields(
            beneathPath("shippingAddress").withSubsectionId("shipping"),
            fieldWithPath("recipient").description("Tên người nhận"),
            fieldWithPath("street").description("Địa chỉ đường, số nhà"),
            fieldWithPath("city").description("Thành phố"),
            fieldWithPath("postalCode").optional().description("Mã bưu chính")
        )
    ));
```

Ở đoạn này, `document` được static import từ `WebTestClientRestDocumentation`. Test cần cấu hình `WebTestClient` cùng REST Docs trước khi chạy.

**Với REST Assured**, giả sử biến `spec` là `RequestSpecification` đã được cấu hình bộ lọc Spring REST Docs:

```java
RestAssured.given(spec)
    .contentType("application/json")
    .body(requestJson)
    .filter(document("orders-restassured",
        requestBody(beneathPath("shippingAddress")
            .withSubsectionId("shipping"))
    ))
    .when()
    .post("/orders")
    .then()
    .statusCode(201);
```

Ở đây, `document` được static import từ `RestAssuredRestDocumentation`. Điểm chung của cả ba phương án là cùng sinh snippet từ **HTTP exchange đã kiểm thử**, thay vì chỉ dựng ví dụ tĩnh.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Test báo field chưa được document | `requestFields` strict thấy field mới hoặc thiếu descriptor | Bổ sung descriptor, hoặc dùng `subsectionWithPath`/`ignored` khi thực sự có chủ đích. |
| Test báo field bắt buộc không tồn tại | Path khai báo sai, field bị thiếu trong payload hoặc nằm sai cấp | So JSON thực tế với path; với `beneathPath`, dùng path **tương đối**. |
| Không tìm thấy subsection | `beneathPath` trỏ nhầm nhánh hoặc ca kiểm thử không gửi nhánh đó | Kiểm tra tên/casing của key và dữ liệu request của test. |
| Thiếu `request-fields-shipping.adoc` | Chưa gọi `requestFields(beneathPath(...))` hoặc test không chạy tới `document` | Kiểm tra cấu hình REST Docs và tên subsection ID. |
| Tài liệu Asciidoctor không thể `include` snippet | Sai thuộc tính `snippets`, sai thư mục output hoặc bước dựng tài liệu chạy trước test | Kiểm tra đường dẫn và phụ thuộc `asciidoctor -> test`. |
| Thêm field con nhưng test vẫn xanh | Chỉ có `subsectionWithPath` cấp gốc, không có bảng chi tiết strict | Bổ sung `requestFields(beneathPath(...), ...)` để kiểm tra schema con. |

## 9. Bài thực hành

Hãy mở rộng ví dụ `POST /orders` theo trình tự:

1. Thêm `country` vào `shippingAddress` trong JSON và chạy lại test. Quan sát snippet chi tiết strict báo field chưa được document; sau đó thêm `fieldWithPath("country").description("Mã quốc gia")`.
2. Loại `postalCode` khỏi request. Kiểm tra test vẫn qua vì descriptor có `optional()`; sau đó tạm bỏ `optional()` để nhận biết lỗi field bắt buộc bị thiếu.
3. Đổi subsection ID từ `shipping` thành `delivery` ở cả `requestBody` và `requestFields`. Cập nhật các lệnh `include` tương ứng trong Asciidoctor.
4. Viết thêm test cho trường hợp request không chứa `shippingAddress` theo contract của ứng dụng; không dùng extractor của nhánh này trong test đó.

**Tiêu chí hoàn thành:** bạn giải thích được vì sao bảng cấp gốc vẫn ổn khi thêm field con, vì sao bảng chi tiết strict có thể thất bại, và biết dùng snippet body riêng cùng bảng field riêng mà không nhân bản JSON vào tài liệu thủ công.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): mô tả `subsectionWithPath`, `beneathPath`, `requestBody`, `requestFields`, path JSON và quy tắc kiểm tra field.
- [Spring REST Docs — Reference](https://docs.spring.io/spring-restdocs/reference/): hướng dẫn cấu hình, sinh snippet và tích hợp tài liệu vào build.

