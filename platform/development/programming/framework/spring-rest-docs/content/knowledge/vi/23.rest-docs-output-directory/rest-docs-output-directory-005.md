# Định danh test class và test method trong đường dẫn snippet

## 1. Vì sao cần đưa tên class và method vào đường dẫn?

Một test class có thể kiểm thử nhiều operation:

```java
class OrderDocumentationTests {
    @Test void getOrderById() { /* ... */ }
    @Test void createOrder() { /* ... */ }
    @Test void cancelOrder() { /* ... */ }
}
```

Mỗi test có thể sinh các snippet trùng tên như `http-request.adoc`, `http-response.adoc`, `curl-request.adoc` và `request-fields.adoc`. Nếu mọi test ghi vào cùng một thư mục, file cùng tên có thể ghi đè nhau hoặc làm tài liệu tham chiếu nhầm operation.

Spring REST Docs giải quyết việc này bằng **document identifier** — chuỗi định danh truyền cho `document(...)`. Identifier trở thành thư mục con dưới output directory. Ta có thể đặt identifier cố định hoặc dùng placeholder để đưa tên test class, test method và số thứ tự operation vào đường dẫn.

Module **SPRING_REST_DOCS** tạo REST API documentation có thể kiểm chứng bằng HTTP tests với MockMvc, WebTestClient hoặc REST Assured. Test sinh snippet cho request, response, payload, parameter và header; sau đó biên soạn thành Asciidoctor/Markdown và đưa vào build/CI. Bài thuộc chương **Thư mục output**, tập trung định danh test class và test method trong đường dẫn snippet.

Sau bài học, bạn có thể:

1. Phân biệt output directory gốc với document identifier.
2. Dùng `{class-name}` và `{method-name}` để phân vùng snippet tự động.
3. Chọn placeholder theo quy ước đặt tên phù hợp.
4. Dùng `{step}` khi một test method document nhiều HTTP operation.
5. Tổ chức include trong Asciidoctor mà không trộn snippet giữa các test.

## 2. Hai cấp đường dẫn cần phân biệt

Giả sử Gradle dùng output directory:

```text
build/generated-snippets
```

Khi test gọi:

```java
document("order-detail")
```

Spring REST Docs tạo snippet dưới:

```text
build/generated-snippets/
  order-detail/
    curl-request.adoc
    http-request.adoc
    http-response.adoc
    httpie-request.adoc
    request-body.adoc
    response-body.adoc
```

Trong đó:

- **Output directory** là thư mục gốc nhận toàn bộ snippet, ví dụ `build/generated-snippets`.
- **Document identifier** là thư mục con của một operation, ví dụ `order-detail`.
- **Snippet file** là file cụ thể được sinh trong thư mục identifier, ví dụ `http-request.adoc`.

Đường dẫn đầy đủ:

```text
<output-directory>/<document-identifier>/<snippet-file>
```

Thay output directory sẽ chuyển toàn bộ cây snippet. Thay identifier sẽ phân vùng snippet của operation bên trong cùng output directory. Hai cấu hình này không thay thế nhau.

## 3. Identifier cố định và nguy cơ trùng lặp

Ví dụ identifier cố định:

```java
mockMvc.perform(get("/api/orders/42"))
        .andDo(document("order-detail"));
```

Cách này phù hợp khi chỉ một test sở hữu identifier đó. Nếu nhiều test cùng dùng `order-detail`, chúng ghi vào cùng một thư mục và cùng các file tên `http-request.adoc`, `http-response.adoc`. Nội dung có thể ghi đè nhau; chạy song song còn có nguy cơ cạnh tranh khi ghi file.

Chỉ dùng identifier cố định khi các test thực sự muốn chia sẻ cùng một bộ snippet hoặc có một test duy nhất sinh bộ snippet đó. Khi mỗi test mô tả operation khác nhau, hãy phân vùng theo class và method.

## 4. Các placeholder trong document identifier

Spring REST Docs hỗ trợ các tham số sau:

| Placeholder | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `{methodName}` | Tên test method nguyên bản | `getOrderById` |
| `{method-name}` | Tên method dạng kebab-case | `get-order-by-id` |
| `{method_name}` | Tên method dạng snake_case | `get_order_by_id` |
| `{ClassName}` | Tên class đơn giản nguyên bản | `OrderDocumentationTests` |
| `{class-name}` | Tên class dạng kebab-case | `order-documentation-tests` |
| `{class_name}` | Tên class dạng snake_case | `order_documentation_tests` |
| `{step}` | Số lần gọi service trong test hiện tại | `1`, `2`, `3` |

Có thể ghép placeholder bằng dấu slash:

```java
document("{class-name}/{method-name}")
```

Ví dụ test method `getOrderById` trong class `OrderDocumentationTests` sinh snippet vào:

```text
build/generated-snippets/
  order-documentation-tests/
    get-order-by-id/
      http-request.adoc
      http-response.adoc
      curl-request.adoc
```

Placeholder phân biệt chữ hoa/chữ thường. `{ClassName}` và `{class-name}` có ý nghĩa khác nhau; hãy chọn đúng dạng trong bảng.

## 5. Cấu hình identifier một lần trong test class

Với MockMvc, có thể cấu hình document identifier mặc định trong `@BeforeEach`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTests {

    @Autowired
    private WebApplicationContext context;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
                .apply(documentationConfiguration(restDocumentation))
                .alwaysDo(document("{class-name}/{method-name}"))
                .build();
    }

    @Test
    void getOrderById() throws Exception {
        this.mockMvc.perform(get("/api/orders/42"))
                .andExpect(status().isOk());
    }
}
```

`alwaysDo(document(...))` tự document các request được thực hiện qua MockMvc với identifier mặc định theo test context. Cách này tiện khi mọi request trong class đều cần snippet. Nếu một test cần cấu hình riêng, dùng `andDo(document(...))` và cân nhắc bỏ `alwaysDo` để tránh sinh hai bộ snippet không chủ đích.

## 6. Định danh nhiều operation trong một test method bằng {step}

Một test method đôi khi thực hiện nhiều HTTP exchange, ví dụ tạo order, đọc order vừa tạo rồi hủy order. Nếu cả ba request cùng dùng `{class-name}/{method-name}`, chúng sẽ cùng nhắm vào một thư mục và có thể ghi đè snippet cùng tên.

Placeholder `{step}` cung cấp số thứ tự của lần gọi service trong test hiện tại:

```java
@Test
void createReadAndCancelOrder() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType("application/json")
                    .content("""
                            {"productId":"P-42","quantity":1}
                            """))
            .andExpect(status().isCreated())
            .andDo(document("{class-name}/{method-name}/{step}"));

    mockMvc.perform(get("/api/orders/ORD-100"))
            .andExpect(status().isOk())
            .andDo(document("{class-name}/{method-name}/{step}"));

    mockMvc.perform(delete("/api/orders/ORD-100"))
            .andExpect(status().isNoContent())
            .andDo(document("{class-name}/{method-name}/{step}"));
}
```

Cây thư mục minh họa:

```text
build/generated-snippets/
  order-documentation-tests/
    create-read-and-cancel-order/
      1/
      2/
      3/
```

`{step}` là số lần gọi service trong test hiện tại, không phải số thứ tự toàn cục của test suite. Khi dùng nhiều operation trong một method, hãy giải thích ý nghĩa của từng step trong tài liệu để người đọc hiểu bước 1, 2, 3 tương ứng với hành động nào.

## 7. Kết hợp identifier với output directory tùy chỉnh

Với JUnit 5, `RestDocumentationExtension` nhận output directory qua constructor:

```java
@RegisterExtension
final RestDocumentationExtension restDocumentation =
        new RestDocumentationExtension("build/api-snippets");
```

Khi identifier là `{class-name}/{method-name}`, cấu trúc có dạng:

```text
build/api-snippets/
  order-documentation-tests/
    get-order-by-id/
      http-request.adoc
      http-response.adoc
```

Output directory tùy chỉnh là root; identifier vẫn tạo thư mục con bên dưới root đó.

Với JUnit 4, `JUnitRestDocumentation` rule nhận output directory trong constructor:

```java
@Rule
public JUnitRestDocumentation restDocumentation =
        new JUnitRestDocumentation("target/api-snippets");
```

Nếu dùng Spring Boot `@AutoConfigureRestDocs`, có thể cấu hình `outputDir` cho root snippet. Identifier vẫn được truyền vào `document(...)` như bình thường. Tránh để JUnit extension, rule hoặc auto-configuration cùng ghi ra nhiều root khác nhau trong khi Asciidoctor chỉ đọc một nơi.

## 8. Dùng với WebTestClient và REST Assured

Placeholder identifier cũng dùng được với WebTestClient:

```java
webTestClient.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("{class-name}/{method-name}"));
```

Với REST Assured, identifier được truyền vào document filter:

```java
given(this.spec)
        .filter(document("{class-name}/{method-name}"))
        .when()
        .get("/api/orders/42")
        .then()
        .statusCode(200);
```

Nếu một test method gửi nhiều request, sử dụng `{step}` trong identifier của từng operation. Identifier chỉ quyết định vị trí snippet; nó không thay thế cấu hình WebTestClient, RequestSpecification hoặc đích gửi HTTP.

## 9. Quy ước đặt tên và cấu trúc thư mục

Một cấu trúc dễ đọc:

```text
generated-snippets/
  order-documentation-tests/
    get-order-by-id/
    create-order/
    cancel-order/
  customer-documentation-tests/
    get-customer-by-id/
    update-customer-address/
```

Khuyến nghị:

- Dùng `{class-name}` để nhóm theo class test hoặc miền API.
- Dùng `{method-name}` để thể hiện operation bằng kebab-case.
- Chọn một ngôn ngữ và quy ước đặt tên method nhất quán.
- Dùng `{step}` khi một test method có nhiều exchange cần snippet riêng.
- Không đưa ID random hoặc timestamp vào identifier nếu không thật sự cần.
- Giữ identifier ổn định để các trang Asciidoctor include không phải cập nhật theo mỗi lần test.

Tên test method trở thành một phần gián tiếp của cấu trúc tài liệu. Đổi tên method có thể đổi tên thư mục snippet; cần rà soát include trong tài liệu cùng thay đổi đó.

## 10. Include snippet trong Asciidoctor

Với identifier `{class-name}/{method-name}`, Asciidoctor include đúng đường dẫn tương ứng:

```asciidoc
= Order API

== Lấy đơn hàng theo ID

include::{snippets}/order-documentation-tests/get-order-by-id/http-request.adoc[]
include::{snippets}/order-documentation-tests/get-order-by-id/http-response.adoc[]

== Tạo đơn hàng

include::{snippets}/order-documentation-tests/create-order/http-request.adoc[]
include::{snippets}/order-documentation-tests/create-order/http-response.adoc[]
```

Biến `{snippets}` phải trỏ tới output directory gốc, ví dụ `build/generated-snippets`. Không đưa identifier vào biến `{snippets}` lần nữa nếu include đã chứa class/method, vì có thể tạo đường dẫn lặp.

Với `{step}`, include thư mục bước tương ứng:

```asciidoc
== Quy trình tạo, đọc và hủy đơn hàng

=== Bước 1 — Tạo đơn hàng
include::{snippets}/order-documentation-tests/create-read-and-cancel-order/1/http-request.adoc[]

=== Bước 2 — Đọc đơn hàng
include::{snippets}/order-documentation-tests/create-read-and-cancel-order/2/http-request.adoc[]

=== Bước 3 — Hủy đơn hàng
include::{snippets}/order-documentation-tests/create-read-and-cancel-order/3/http-request.adoc[]
```

## 11. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Snippet của test này xuất hiện trong tài liệu test khác | Nhiều test dùng chung identifier cố định | Dùng `{class-name}/{method-name}` |
| Chỉ có snippet của lần gọi HTTP cuối | Nhiều request trong cùng method ghi cùng thư mục | Thêm `{step}` |
| Asciidoctor báo không tìm thấy snippet | Include path không khớp placeholder đã phân giải | Kiểm tra cây thư mục output sau test |
| Đường dẫn include có class name lặp hai lần | `{snippets}` đã chứa identifier nhưng include cũng thêm lại | Để `{snippets}` là output root |
| Đổi tên test khiến build tài liệu lỗi | `{method-name}` sinh thư mục mới nhưng include chưa đổi | Cập nhật include hoặc giữ identifier explicit |
| Chạy song song gây output không ổn định | Hai test ghi cùng identifier | Tạo identifier riêng cho class/method/step |
| Folder tên method khó đọc | Dùng `{methodName}` giữ nguyên camelCase | Dùng `{method-name}` cho kebab-case |
| Identifier đổi theo từng lần chạy | Chèn random ID/time vào tên | Dùng tên test ổn định; để dữ liệu động trong snippet |

## 12. Build và CI

Quy trình cơ bản:

1. Chọn output root ổn định, ví dụ `build/generated-snippets`.
2. Cấu hình `RestDocumentationExtension`, JUnit 4 rule hoặc Spring Boot `@AutoConfigureRestDocs`.
3. Chọn quy ước identifier, thường là `{class-name}/{method-name}`.
4. Với test có nhiều exchange, thêm `{step}`.
5. Chạy test để sinh snippet.
6. Chạy Asciidoctor và kiểm tra mọi include trỏ tới cây thư mục đã sinh.

Ví dụ Gradle khi task đã được cấu hình:

```groovy
val snippetsDir by extra { file("build/generated-snippets") }

tasks.test {
    outputs.dir(snippetsDir)
    useJUnitPlatform()
}

tasks.named("asciidoctor") {
    inputs.dir(snippetsDir)
    dependsOn(tasks.test)
}
```

Nếu đổi tên test method, build có thể sinh thư mục mới trong khi Asciidoctor vẫn include thư mục cũ. CI nên build từ output sạch và yêu cầu mọi include được resolve thành công. Tránh để snippet stale từ lần chạy trước làm build xanh giả.

## 13. Bài tập thực hành

Tạo class `InventoryDocumentationTests` gồm:

- `getStockBySku`
- `reserveStock`
- `releaseReservation`

Thực hiện:

1. Cấu hình output root là `build/generated-snippets`.
2. Dùng identifier `{class-name}/{method-name}` cho mỗi test.
3. Trong `reserveStock`, thực hiện hai exchange: tạo reservation rồi đọc reservation; dùng `{step}` để phân vùng.
4. Chạy test và quan sát cây thư mục output.
5. Viết Asciidoctor include request/response snippet của từng method và từng step.
6. Đổi tên một test method rồi chạy lại build để quan sát ảnh hưởng đến đường dẫn include.
7. Chạy `test` và `asciidoctor` trong CI.

**Tiêu chí hoàn thành:** Mỗi test có thư mục snippet riêng; nhiều exchange trong một method không ghi đè nhau; identifier ổn định và dễ đọc; output root và include path được phân biệt; build sạch vẫn tạo và include đủ snippet.

## 14. Ghi nhớ

Output directory là thư mục gốc, còn document identifier xác định thư mục con của từng operation. Spring REST Docs cho phép dùng `{class-name}`, `{method-name}`, các biến thể camelCase/snake_case và `{step}` trong identifier để phân vùng snippet tự động. Dùng `{class-name}/{method-name}` cho phần lớn test; thêm `{step}` khi một method document nhiều request. Đặt `{snippets}` trỏ tới output root, giữ tên test và identifier ổn định, rồi kiểm tra include trong Asciidoctor ở build/CI để snippet không ghi đè hoặc bị tham chiếu sai.

### Tài liệu tham khảo

- [Spring REST Docs — Generating Documentation Snippets](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/)
- [Spring REST Docs — RestDocumentationExtension API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/RestDocumentationExtension.html)
- [Spring Boot — Auto-configured Spring REST Docs Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Guides — Creating API Documentation with REST Docs](https://spring.io/guides/gs/testing-restdocs/)
