# Content type `application/x-www-form-urlencoded` trong Spring REST Docs

## 1. Vì sao cần hiểu media type của request?

Trong REST API, cùng một thao tác “gửi thông tin biểu mẫu” có thể được biểu diễn bằng nhiều dạng HTTP body. Header `Content-Type` nói cho máy chủ biết **body được mã hóa theo định dạng nào**; từ đó framework chọn cách đọc và ánh xạ dữ liệu. Khi xây dựng tài liệu bằng **Spring REST Docs** (`SPRING_REST_DOCS`), hiểu đúng media type giúp:

- Tạo request kiểm thử tương đương request client thật.
- Dùng đúng công cụ để tài liệu hóa form parameters, thay vì nhầm với query string hoặc các trường JSON.
- Phát hiện thay đổi không tương thích giữa cách client gửi dữ liệu và cách API nhận dữ liệu.
- Sinh các snippet request, response, parameter, header từ kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured, rồi đưa vào Asciidoctor/Markdown và CI.

`application/x-www-form-urlencoded` là media type phổ biến của **dữ liệu biểu mẫu**. Nó thường xuất hiện khi trình duyệt gửi HTML form bằng phương thức POST, nhưng cũng có thể được client HTTP gửi trực tiếp.

Ví dụ client tạo đơn hàng:

```http
POST /orders HTTP/1.1
Host: api.example.test
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

sku=BK-42&quantity=2&note=Giao+h%C3%A0ng+tr%C6%B0%E1%BB%9Bc+17h
```

Body gồm ba cặp tên/giá trị. Sau khi giải mã UTF-8 và quy tắc form encoding, server nhận:

| Tên | Giá trị sau giải mã | Ý nghĩa |
| --- | --- | --- |
| `sku` | `BK-42` | Mã hàng |
| `quantity` | `2` | Số lượng, được gửi dưới dạng chuỗi |
| `note` | `Giao hàng trước 17h` | Ghi chú có khoảng trắng và ký tự tiếng Việt |

**Điểm quan trọng:** body này là chuỗi các cặp khóa/giá trị được mã hóa, **không phải JSON** và cũng **không nằm trong URL**.

## 2. Quy tắc mã hóa của `application/x-www-form-urlencoded`

### 2.1. Cú pháp cơ bản

Body thường có dạng:

```text
name1=value1&name2=value2&name3=value3
```

Mỗi phần được phân tách bởi ký tự `&`, còn dấu `=` phân tách tên với giá trị. Các ký tự có ý nghĩa đặc biệt trong dữ liệu được mã hóa theo quy tắc form encoding:

| Ký tự trong giá trị gốc | Biểu diễn trên wire | Giải thích |
| --- | --- | --- |
| Khoảng trắng ` ` | `+` | Đặc trưng của form encoding |
| Dấu cộng `+` | `%2B` | Phân biệt với ký hiệu khoảng trắng |
| Dấu `&` | `%26` | Không bị hiểu là phần tách tham số |
| Dấu `=` | `%3D` | Không bị hiểu là phần tách tên/giá trị |
| Dấu `@` | `%40` | Thường gặp trong địa chỉ email |
| Ký tự `à` khi dùng UTF-8 | `%C3%A0` | Mỗi byte UTF-8 được mã hóa bằng `%HH` |

Ví dụ giá trị gốc `quà tặng: A+B & C` được mã hóa thành:

```text
qu%C3%A0+t%E1%BA%B7ng%3A+A%2BB+%26+C
```

Server giải mã lần lượt từ body theo quy tắc form. Nếu client gửi ký tự `+` thô trong giá trị, trình giải mã thường diễn giải nó thành **khoảng trắng**; muốn truyền dấu cộng thực sự, client phải mã hóa thành `%2B`.

### 2.2. Charset và dữ liệu Unicode

Khi biểu mẫu có tiếng Việt hoặc các ký tự Unicode, nên thống nhất UTF-8 ở cả client và server. Header có thể khai báo:

```http
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
```

Chẳng hạn `Hà Nội` khi mã hóa form với UTF-8 có dạng `H%C3%A0+N%E1%BB%99i`. Việc dùng `charset=UTF-8` giúp nêu rõ cách diễn giải các byte, nhưng vẫn cần cấu hình xử lý mã hóa ký tự nhất quán ở tầng HTTP/server. Không nên mặc định mọi client, proxy và môi trường kiểm thử đều có cùng lựa chọn charset.

Trong Java, `URLEncoder` cung cấp **form encoding** cho một tên hoặc giá trị:

```java
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

String original = "quà tặng: A+B & C";
String encoded = URLEncoder.encode(original, StandardCharsets.UTF_8);
// qu%C3%A0+t%E1%BA%B7ng%3A+A%2BB+%26+C

String decoded = URLDecoder.decode(encoded, StandardCharsets.UTF_8);
// quà tặng: A+B & C
```

**Chỉ mã hóa từng tên/giá trị** trước khi nối thành `name=value&...`. Không áp dụng `URLEncoder` lên toàn bộ URL hay chuỗi body đã ghép sẵn, vì thao tác đó có thể mã hóa luôn các dấu `=` và `&` dùng làm cấu trúc.

### 2.3. Tham số trùng tên, tham số rỗng và tham số thiếu

Form có thể chứa nhiều giá trị cho cùng một tên:

```text
tag=spring&tag=rest-docs&tag=testing
```

Server có thể đọc thành danh sách giá trị, ví dụ `List<String> tag` hoặc `MultiValueMap` tùy cách binding. Ngược lại, `note=` biểu diễn tham số `note` **có mặt nhưng giá trị rỗng**; nếu không có cặp `note=...` nào thì tham số `note` **vắng mặt**. Hai tình huống có thể dẫn đến hành vi khác nhau khi controller khai báo giá trị mặc định hoặc áp dụng kiểm tra dữ liệu.

Không tự suy đoán rằng form encoding hỗ trợ kiểu số, boolean hoặc danh sách lồng nhau theo một schema chung. Các giá trị trên wire là chuỗi; quy tắc chuyển kiểu thuộc về framework và ứng dụng.

## 3. Phân biệt với query, JSON và multipart

| Dạng dữ liệu | Ví dụ | Nơi đặt dữ liệu | Cách tài liệu hóa với Spring REST Docs |
| --- | --- | --- | --- |
| URL-encoded form | `sku=BK-42&quantity=2` | Body, `Content-Type: application/x-www-form-urlencoded` | `formParameters(...)` |
| Query parameter | `/orders?channel=mobile` | Query string của URL | `queryParameters(...)` |
| JSON | `{"sku":"BK-42","quantity":2}` | Body, `Content-Type: application/json` | `requestFields(...)` |
| Multipart | Form có tệp ảnh và trường text | Các part trong body, `multipart/form-data` | `requestParts(...)` và tài liệu part phù hợp |

Hai ví dụ sau có tên tham số giống nhau nhưng khác vị trí và ngữ nghĩa:

```http
GET /orders?sku=BK-42&quantity=2 HTTP/1.1
```

```http
POST /orders HTTP/1.1
Content-Type: application/x-www-form-urlencoded

sku=BK-42&quantity=2
```

Trong Spring MVC, `@RequestParam` có thể truy cập tham số request từ các nguồn phù hợp với Servlet, nên chỉ nhìn chữ ký controller chưa đủ để suy ra client gửi query hay form body. Khi viết Spring REST Docs, cần tạo **đúng request HTTP** và khai báo snippet đúng loại.

Header `Accept` có mục đích khác: nó mô tả kiểu response client muốn nhận. Ví dụ request gửi form URL-encoded nhưng chấp nhận response JSON là hoàn toàn hợp lệ:

```http
Content-Type: application/x-www-form-urlencoded
Accept: application/json
```

Không dùng `Accept: application/x-www-form-urlencoded` để thay cho `Content-Type` của request body.

## 4. Ví dụ endpoint Spring MVC nhận URL-encoded form

Giả sử ứng dụng có endpoint tạo đơn hàng, yêu cầu `sku`, số lượng `quantity` mặc định là `1`, và `note` không bắt buộc.

```java
package example.docs;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Void> create(
            @RequestParam String sku,
            @RequestParam(defaultValue = "1") int quantity,
            @RequestParam(required = false) String note) {

        if (sku.isBlank() || quantity < 1) {
            return ResponseEntity.badRequest().build();
        }

        // Ví dụ tối giản: hệ thống thật cần tạo và lưu đơn hàng.
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

`@PostMapping(consumes = ...)` giúp công bố và giới hạn media type mà handler chấp nhận. Nếu client gửi JSON thay vì form URL-encoded, Spring MVC thường trả `415 Unsupported Media Type` khi không có handler khác chấp nhận loại đó. Nếu gửi form thiếu `sku`, framework có thể trả `400 Bad Request` do thiếu `@RequestParam` bắt buộc.

Lưu ý: `@RequestParam String sku` mặc định yêu cầu **sự hiện diện** của tham số; nó không tự đảm bảo chuỗi có nội dung. Ví dụ kiểm tra `sku.isBlank()` trong controller chỉ nhằm minh họa khác biệt này. Tài liệu phải mô tả chính xác những quy tắc nghiệp vụ đã được triển khai, không suy ra từ annotation một cách máy móc.

## 5. Viết kiểm thử MockMvc để sinh tài liệu

### 5.1. Dependency và cấu hình kiểm thử

Với Spring Boot sử dụng Gradle Groovy DSL, các dependency kiểm thử thường gồm:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

Ví dụ giả định project đã cấu hình phiên bản Spring Boot và dependency management tương thích với Spring REST Docs. Trường hợp không dùng Spring Boot cần tự gắn `RestDocumentationExtension`/`RestDocumentationContextProvider` vào MockMvc.

### 5.2. Test tạo request form và `form-parameters.adoc`

```java
package example.docs;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderFormDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void createOrderFromUrlEncodedForm() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .characterEncoding(StandardCharsets.UTF_8.name())
                .param("sku", "BK-42")
                .param("quantity", "2")
                .param("note", "quà tặng: A+B & C"))
            .andExpect(status().isCreated())
            .andDo(document("orders/create-form",
                formParameters(
                    parameterWithName("sku")
                        .description("Mã hàng; bắt buộc, không được để trống"),
                    parameterWithName("quantity")
                        .optional()
                        .description("Số lượng nguyên dương; mặc định 1"),
                    parameterWithName("note")
                        .optional()
                        .description("Ghi chú của khách hàng, có thể chứa Unicode")
                )
            ));
    }

    @Test
    void rejectJsonWhenOnlyFormIsSupported() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"BK-42\",\"quantity\":2}"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void rejectInvalidQuantity() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("sku", "BK-42")
                .param("quantity", "0"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void acceptOmittedOptionalFields() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("sku", "BK-42"))
            .andExpect(status().isCreated());
    }
}
```

Phân tích các bước quan trọng:

1. `contentType(MediaType.APPLICATION_FORM_URLENCODED)` khai báo **loại body** mà endpoint sẽ nhận; đây là phần không thể bỏ qua khi kiểm chứng media type.
2. `characterEncoding("UTF-8")` giúp kiểm thử có lựa chọn mã hóa ký tự rõ ràng, nhất là khi fixture chứa tiếng Việt. Với client thật, hãy kiểm tra header và byte body gửi đi.
3. `param(...)` cung cấp các tham số request cho MockMvc. Trong yêu cầu POST form URL-encoded, Spring MockMvc có cơ chế xây dựng biểu mẫu phục vụ kiểm thử. Cần kiểm tra snippet `http-request.adoc` được sinh để bảo đảm payload trên wire khớp điều client thật gửi.
4. `andExpect(status().isCreated())` khẳng định endpoint xử lý request thành công. Spring REST Docs chỉ tạo tài liệu hữu ích khi hành vi được kiểm thử.
5. `formParameters(...)` khai báo tên và ý nghĩa của các **tham số body**; `.optional()` cho phép chúng vắng mặt trong test. Nó không tự kiểm tra `sku` phải khác rỗng hay `quantity` phải là số dương; các kiểm thử hành vi đảm nhiệm phần đó.

Nếu ứng dụng có Spring Security bảo vệ CSRF, request POST trong test cần có CSRF token hợp lệ hoặc cấu hình kiểm thử phù hợp; đó là yêu cầu bảo mật riêng, không phải đặc tính của form encoding.

### 5.3. Snippet và tài liệu được tạo

Sau khi bài kiểm thử `createOrderFromUrlEncodedForm` thành công, ví dụ thư mục đầu ra:

```text
build/generated-snippets/
└── orders/
    └── create-form/
        ├── form-parameters.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        ├── curl-request.adoc
        └── ...
```

`form-parameters.adoc` sẽ chứa mô tả các trường `sku`, `quantity` và `note`; `http-request.adoc` trình bày request được kiểm thử, bao gồm phương thức, URL, header và body. Đây là hai snippet bổ trợ cho nhau: **một snippet giải thích hợp đồng dữ liệu, snippet kia cho thấy request HTTP cụ thể**.

Bảng sau minh họa *nội dung thông tin* của snippet form; bố cục thực tế do template Asciidoctor quyết định:

| Parameter | Description |
| --- | --- |
| `sku` | Mã hàng; bắt buộc, không được để trống |
| `quantity` | Số lượng nguyên dương; mặc định 1 |
| `note` | Ghi chú của khách hàng, có thể chứa Unicode |

Hãy kiểm tra ký tự đặc biệt trong `http-request.adoc`: trên wire, dấu `+` nằm trong giá trị phải được mã hóa phù hợp và phân biệt với ký hiệu khoảng trắng. Đừng sửa snippet bằng tay để làm ví dụ “đẹp” hơn; hãy sửa cách tạo request hoặc logic endpoint rồi chạy lại test.

## 6. Gửi request tương đương bằng HTTP client

Với `curl` trong shell hỗ trợ cú pháp Bash, có thể gửi form như sau:

```bash
curl -i -X POST 'http://localhost:8080/orders' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  --data-urlencode 'sku=BK-42' \
  --data-urlencode 'quantity=2' \
  --data-urlencode 'note=quà tặng: A+B & C'
```

`--data-urlencode` mã hóa giá trị form và ghép các tham số. Cách này giúp hạn chế lỗi tự ghép body bằng dấu `&` khi dữ liệu chứa khoảng trắng, dấu cộng hoặc ký tự Unicode. URL giả định ứng dụng đang chạy ở `localhost:8080`; không phải bước bắt buộc để chạy MockMvc test.

Một ví dụ HTML form tương ứng:

```html
<form action="/orders" method="post" accept-charset="UTF-8">
  <label>SKU <input name="sku" required></label>
  <label>Số lượng <input name="quantity" type="number" min="1" value="1"></label>
  <label>Ghi chú <input name="note"></label>
  <button type="submit">Tạo đơn</button>
</form>
```

Khi không chỉ định `enctype`, HTML form gửi bằng POST thường dùng `application/x-www-form-urlencoded` theo mặc định. `enctype="multipart/form-data"` được dùng cho trường hợp cần tải tệp lên; tài liệu REST Docs của phần multipart phải sử dụng nhóm snippet khác.

## 7. Áp dụng với WebTestClient và REST Assured

Spring REST Docs tích hợp được với nhiều công cụ kiểm thử HTTP. Trong mỗi công cụ, request phải mang body form và media type chính xác.

### 7.1. WebTestClient

Ví dụ giả định `webTestClient` đã gắn cấu hình Spring REST Docs và endpoint WebFlux được viết để đọc form data:

```java
import org.springframework.web.reactive.function.BodyInserters;

import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

webTestClient.post()
    .uri("/orders")
    .body(BodyInserters.fromFormData("sku", "BK-42")
        .with("quantity", "2")
        .with("note", "quà tặng: A+B & C"))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("orders/webtestclient-form",
        formParameters(
            parameterWithName("sku").description("Mã hàng"),
            parameterWithName("quantity").optional()
                .description("Số lượng, mặc định 1"),
            parameterWithName("note").optional()
                .description("Ghi chú")
        )
    ));
```

`BodyInserters.fromFormData(...)` xây dựng body URL-encoded và thiết lập media type thích hợp khi không có `Content-Type` khác bị ghi đè. Trong WebFlux, handler thường đọc form qua `ServerWebExchange.getFormData()` hoặc cơ chế binding phù hợp; đừng giả định ví dụ `@RequestParam` của Spring MVC hoạt động tương tự ở mọi handler WebFlux.

### 7.2. REST Assured

Ví dụ giả định có server đang chạy và `specification` đã cấu hình `RestAssuredRestDocumentation.documentationConfiguration(...)`:

```java
import io.restassured.http.ContentType;

import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

given(specification)
    .filter(document("orders/rest-assured-form",
        formParameters(
            parameterWithName("sku").description("Mã hàng"),
            parameterWithName("quantity").optional()
                .description("Số lượng, mặc định 1"),
            parameterWithName("note").optional()
                .description("Ghi chú")
        )))
    .contentType(ContentType.URLENC)
    .formParam("sku", "BK-42")
    .formParam("quantity", "2")
    .formParam("note", "quà tặng: A+B & C")
    .when()
    .post("/orders")
    .then()
    .statusCode(201);
```

`ContentType.URLENC` và `formParam(...)` giúp REST Assured sinh request form. Kiểm tra cấu hình charset của client nếu có Unicode. Không dùng `.body("{...}")` với `ContentType.JSON` rồi mong REST Docs tạo `form-parameters.adoc` tương ứng.

## 8. Đưa snippet vào Asciidoctor, Markdown và CI

### 8.1. Trang AsciiDoc

Ví dụ tệp `src/docs/asciidoc/index.adoc`:

```adoc
= Orders API

== Tạo đơn hàng bằng URL-encoded form

Request sử dụng `Content-Type: application/x-www-form-urlencoded`.

=== Ví dụ HTTP request
include::{snippets}/orders/create-form/http-request.adoc[]

=== Form parameters
include::{snippets}/orders/create-form/form-parameters.adoc[]

=== Ví dụ HTTP response
include::{snippets}/orders/create-form/http-response.adoc[]
```

Biến `{snippets}` phải trỏ tới thư mục gốc chứa snippet (ví dụ `build/generated-snippets`), không phải thư mục con `orders/create-form`. Cú pháp `include::{snippets}/...[]` thuộc Asciidoctor; trình render Markdown thông thường không hiểu chỉ thị này.

Khi dự án cần xuất tài liệu Markdown, có thể dẫn tới HTML do Asciidoctor sinh hoặc có bước chuyển đổi thích hợp trong pipeline. Không giả định tệp `.adoc` nhúng trực tiếp vào Markdown sẽ tự hiển thị thành bảng.

### 8.2. Tích hợp build và CI

Trong dự án dùng Gradle và plugin Asciidoctor đã cài, có thể cấu hình quan hệ giữa tác vụ test và render tài liệu (Groovy DSL):

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
    attributes 'snippets': snippetsDir.absolutePath
}
```

Sau đó CI chạy, chẳng hạn:

```bash
./gradlew test asciidoctor
```

Quy trình có ý nghĩa sau:

1. Test tạo request URL-encoded, kiểm chứng HTTP status và mô tả tham số form.
2. Spring REST Docs ghi `form-parameters.adoc`, `http-request.adoc` và các snippet mặc định trong thư mục khai báo.
3. Asciidoctor đọc snippet vừa sinh để tạo tài liệu HTML hoặc định dạng đã cấu hình.
4. Nếu một tham số bắt buộc thay đổi, kiểm thử hoặc bước kiểm tra snippet sẽ phát hiện sự không phù hợp; CI chặn việc xuất bản tài liệu đã lỗi thời.

Để có bảo đảm thực tế, pipeline cũng cần kiểm tra tệp HTML cuối cùng đã được tạo và được công bố đúng nơi. Không nên dùng lại thư mục `generated-snippets` tồn tại từ build cũ như bằng chứng tài liệu còn chính xác.

## 9. Lỗi thường gặp

| Biểu hiện | Khả năng gây lỗi | Cách xác minh và khắc phục |
| --- | --- | --- |
| POST trả `415 Unsupported Media Type` | Client gửi JSON hoặc thiếu `Content-Type` trong khi endpoint chỉ nhận URL-encoded form | Kiểm tra request và `consumes` của handler; đặt `Content-Type: application/x-www-form-urlencoded` |
| Giá trị `A+B` trở thành `A B` | Dấu `+` thô bị hiểu là khoảng trắng | Mã hóa dấu cộng thành `%2B` hoặc để HTTP client mã hóa tham số |
| Tiếng Việt bị lỗi dấu | Byte/charset không nhất quán | Dùng UTF-8 xuyên suốt, xem body/charset thực tế trong request snippet |
| Giá trị `A&B` bị chia thành hai tham số | Tự nối chuỗi mà không encode giá trị | Mã hóa `&` thành `%26`; dùng form encoder của thư viện |
| Test nhận 400 khi thiếu dữ liệu | Không gửi trường `@RequestParam` bắt buộc, hoặc lỗi chuyển kiểu dữ liệu | Kiểm tra tên tham số, nội dung request và quy tắc binding |
| `formParameters(...)` báo thiếu/trường lạ | Descriptor không khớp tập tên form của request | Cập nhật descriptor hoặc fixture; chỉ dùng `.optional()` cho trường thực sự tùy chọn |
| Test pass nhưng snippet có body khác request thật | Dùng tham số MockMvc sai cách hoặc khác phương thức/charset client | Đối chiếu `http-request.adoc` với HTTP request thật và test tích hợp |
| Gửi tệp qua `application/x-www-form-urlencoded` | Nhầm với multipart upload | Sử dụng `multipart/form-data`, mô tả request part thích hợp |
| Không render được bảng tham số | Chưa tạo snippet hoặc sai đường dẫn `{snippets}` | Chạy test trước Asciidoctor, kiểm tra identifier và tên tệp |

**Bảo vệ dữ liệu:** snippet của HTTP request có thể chứa toàn bộ body, bao gồm những giá trị đầu vào của bài kiểm thử. Chỉ dùng dữ liệu giả và tuyệt đối tránh đưa mật khẩu, token, số thẻ, email thật hoặc dữ liệu cá nhân vào request mẫu để xuất bản.

## 10. Bài thực hành

Thiết kế endpoint `POST /registrations` chỉ nhận form URL-encoded với ba trường:

- `email`: bắt buộc, không được rỗng.
- `newsletter`: tùy chọn, nhận `true` hoặc `false`, mặc định `false`.
- `displayName`: tùy chọn, có thể chứa tiếng Việt và dấu `+`.

Hoàn thành lần lượt:

1. Gửi request bằng `curl --data-urlencode` với tên `Mỹ Anh + Team`; viết ra chuỗi body mã hóa dự kiến và xác minh request sau khi gửi.
2. Viết MockMvc test khai báo `Content-Type`, sinh `form-parameters.adoc` bằng `formParameters(...)` và kiểm tra HTTP status thành công.
3. Viết test thiếu `email`; viết test gửi JSON để kiểm chứng phản hồi khi media type không tương thích.
4. Thử trường `displayName` vắng mặt và rỗng để đánh giá khác biệt thực tế của controller.
5. Nhúng cả `http-request.adoc` và `form-parameters.adoc` vào Asciidoctor, tạo tài liệu bằng CI.

**Tiêu chí hoàn thành:** body được mã hóa đúng, server đọc đúng các tham số, các trường bắt buộc/tùy chọn được kiểm thử, snippet được sinh từ test chạy thành công và trang tài liệu cuối cùng sử dụng chính snippet đó.

## Tài liệu tham khảo

- [Spring REST Docs — Documenting Your API: Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Documenting Your API: Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [MDN — `<form>`: HTML form element](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/form)
- [WHATWG HTML Standard — URL-encoded form data](https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#url-encoded-form-data)
