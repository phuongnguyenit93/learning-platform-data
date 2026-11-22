# Xác nhận status, header và body trước khi `document`

## 1. Mục tiêu: tài liệu phải dựa trên kết quả HTTP đã kiểm chứng

**Spring REST Docs** tạo tài liệu REST API từ bài kiểm thử HTTP bằng **MockMvc**, WebTestClient hoặc REST Assured. Công cụ có thể tạo snippet về request, response, payload, tham số và header, sau đó biên soạn chúng thành tài liệu Asciidoctor/Markdown trong build và CI. Với **MockMvc**, thao tác căn bản là `mockMvc.perform(...)`; bài học này tập trung vào việc **kiểm chứng response trước khi gọi `document(...)`**.

Chỉ nhìn thấy snippet `http-response.adoc` được sinh ra **chưa đủ** để kết luận API đúng hợp đồng. Một bài test tài liệu tốt phải xác nhận được ít nhất ba chiều:

1. **HTTP status:** thành công `200`/`201`/`204` hay lỗi `400`/`404`/... có đúng tình huống đang kiểm thử không?
2. **Header:** response có `Content-Type`, `Location`, `ETag`, header truy vết hoặc cache phù hợp không? Giá trị của chúng có đúng không?
3. **Body:** payload có đúng định dạng, trường dữ liệu, kiểu và giá trị nghiệp vụ cần kiểm chứng không? Với `204 No Content`, body có thật sự rỗng không?

Thực hành chuẩn:

```java
mockMvc.perform(get("/api/orders/{id}", "ord-101")
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value("ord-101"))
        .andDo(document("orders-get"));
```

`andExpect(...)` giúp test **thất bại khi hành vi HTTP sai**. `andDo(document(...))` chuyển thao tác HTTP đã được kiểm tra thành snippet cho tài liệu.

Sau bài này, bạn sẽ viết được test cho response thành công, tạo tài nguyên, lỗi không tìm thấy và response không có body; chọn matcher phù hợp, đọc nguyên nhân lỗi và đưa snippet đã kiểm chứng vào tài liệu.

## 2. Vì sao thứ tự `andExpect` trước `andDo(document(...))` quan trọng?

Một chuỗi `ResultActions` thường có thứ tự:

```text
MockMvcRequestBuilders.get/post/delete(...)
                |
                v
         mockMvc.perform(...)
                |
                v
     DispatcherServlet xử lý
                |
                v
        Response thực tế
                |
          +-----+--------------------+
          |                          |
          v                          v
  andExpect(status())      andExpect(header()/content()/jsonPath())
          |                          |
          +------------+-------------+
                       |
           Chỉ khi các kiểm tra đạt
                       |
                       v
             andDo(document(...))
                       |
                       v
       build/generated-snippets/<identifier>/
```

Trong chuỗi gọi bình thường, nếu một `andExpect(...)` ném lỗi, bước `andDo(...)` đặt **sau** nó không được thực hiện. Điều này tránh ghi lại một response sai hợp đồng như một ví dụ API hợp lệ.

| Thành phần | Chức năng | Có thể thay thế kiểm chứng HTTP không? |
| --- | --- | --- |
| `status().isOk()`, `status().isCreated()`, ... | Xác nhận mã trạng thái | Đây là kiểm chứng status. |
| `header().string(...)`, `header().exists(...)` | Xác nhận sự hiện diện hoặc giá trị header | Đây là kiểm chứng header. |
| `content().contentTypeCompatibleWith(...)`, `jsonPath(...)` | Xác nhận kiểu nội dung và dữ liệu body | Đây là kiểm chứng body. |
| `responseHeaders(headerWithName(...))` | Mô tả header trong snippet | Không kiểm tra giá trị header cụ thể so với yêu cầu nghiệp vụ. |
| `responseFields(fieldWithPath(...))` | Mô tả cấu trúc payload được tài liệu hóa; có thể phát hiện field thiếu/thừa | Không tự đảm bảo status hoặc giá trị nghiệp vụ của từng trường. |
| `document("identifier", ...)` | Ghi các snippet của HTTP operation | Không tự biết expected status/giá trị mà test cần xác nhận. |

**Thứ tự gợi ý:** `perform → andExpect(status) → andExpect(header) → andExpect(body) → andDo(document)`. Không có bắt buộc kỹ thuật phải kiểm tra status trước header, nhưng đây là trình tự dễ đọc, dễ chẩn đoán.

## 3. Thiết lập MockMvc và Spring REST Docs

Ví dụ dùng **Java 17+, Spring Boot 3.x, Spring MVC, JUnit Jupiter (JUnit 5)** và Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Nếu dùng Spring Boot BOM, hãy để hệ thống dependency management chọn phiên bản Spring REST Docs tương thích. Với dự án không dùng BOM, cần chọn rõ phiên bản phù hợp với Spring Framework và JUnit Jupiter đang sử dụng.

Trong bài này, `standaloneSetup` tạo controller độc lập với dữ liệu cố định để làm rõ assertions:

```java
@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }
}
```

`RestDocumentationExtension` cung cấp `RestDocumentationContextProvider` cho `@BeforeEach`, còn `documentationConfiguration(...)` cấu hình Spring REST Docs trên MockMvc builder **trước `build()`**. Ví dụ đầy đủ có imports ở phần kế tiếp.

Với dự án cần kiểm thử converter, security, `@ControllerAdvice` và wiring thực tế, có thể đổi sang `webAppContextSetup(webApplicationContext)` hoặc sử dụng cấu hình MockMvc của Spring Boot. Dù chọn cách nào, quy tắc **kiểm chứng status/header/body trước khi ghi tài liệu** vẫn giữ nguyên.

## 4. Ví dụ hoàn chỉnh: GET, POST, lỗi 404 và DELETE 204

Ta tài liệu hóa API đơn hàng gồm bốn trường hợp:

| HTTP request | Status cần xác nhận | Header cần xác nhận | Body cần xác nhận |
| --- | --- | --- | --- |
| `GET /api/orders/ord-101` | `200 OK` | `Content-Type: application/json`, `ETag: "v3"` | `id`, `status`, `amount` |
| `POST /api/orders` | `201 Created` | `Location: /api/orders/ord-102` và JSON content type | `id`, `item`, `quantity`, `status` |
| `GET /api/orders/missing` | `404 Not Found` | JSON content type | `code` và `message` |
| `DELETE /api/orders/ord-102` | `204 No Content` | Không có JSON content type | Body rỗng |

Lớp test dưới đây có một controller minh họa ngay trong file, phù hợp để đọc và chạy độc lập trong dự án Spring MVC có các dependency ở phần 3:

```java
import java.net.URI;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentGetOrderWhenFound() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", "ord-101")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().string(HttpHeaders.ETAG, "\"v3\""))
                .andExpect(jsonPath("$.id").value("ord-101"))
                .andExpect(jsonPath("$.status").value("READY"))
                .andExpect(jsonPath("$.amount").value(12500))
                .andDo(document("orders-get",
                        pathParameters(
                                parameterWithName("id")
                                        .description("Mã đơn hàng")),
                        responseHeaders(
                                headerWithName(HttpHeaders.ETAG)
                                        .description("Phiên bản tài nguyên")),
                        responseFields(
                                fieldWithPath("id").description("Mã đơn hàng"),
                                fieldWithPath("status")
                                        .description("Trạng thái đơn hàng"),
                                fieldWithPath("amount")
                                        .description("Giá trị đơn hàng"))));
    }

    @Test
    void documentCreateOrder() throws Exception {
        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .characterEncoding("UTF-8")
                        .content("""
                                {"item":"book","quantity":2}
                                """))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        HttpHeaders.LOCATION, "/api/orders/ord-102"))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value("ord-102"))
                .andExpect(jsonPath("$.item").value("book"))
                .andExpect(jsonPath("$.quantity").value(2))
                .andExpect(jsonPath("$.status").value("CREATED"))
                .andDo(document("orders-create",
                        requestFields(
                                fieldWithPath("item")
                                        .description("Mặt hàng được đặt"),
                                fieldWithPath("quantity")
                                        .description("Số lượng đặt mua")),
                        responseHeaders(
                                headerWithName(HttpHeaders.LOCATION)
                                        .description("Đường dẫn của đơn hàng mới")),
                        responseFields(
                                fieldWithPath("id").description("Mã đơn hàng mới"),
                                fieldWithPath("item").description("Mặt hàng"),
                                fieldWithPath("quantity").description("Số lượng"),
                                fieldWithPath("status")
                                        .description("Trạng thái đơn hàng"))));
    }

    @Test
    void documentGetOrderNotFound() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", "missing")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"))
                .andExpect(jsonPath("$.message")
                        .value("Không tìm thấy đơn hàng"))
                .andDo(document("orders-get-not-found",
                        pathParameters(
                                parameterWithName("id")
                                        .description("Mã đơn hàng được tìm kiếm")),
                        responseFields(
                                fieldWithPath("code").description("Mã lỗi"),
                                fieldWithPath("message")
                                        .description("Nội dung thông báo lỗi"))));
    }

    @Test
    void documentDeleteOrderNoContent() throws Exception {
        mockMvc.perform(delete("/api/orders/{id}", "ord-102"))
                .andExpect(status().isNoContent())
                .andExpect(content().string(""))
                .andExpect(header().doesNotExist(HttpHeaders.CONTENT_TYPE))
                .andDo(document("orders-delete",
                        pathParameters(
                                parameterWithName("id")
                                        .description("Mã đơn hàng cần xóa"))));
    }

    @RestController
    public static class OrderController {

        @GetMapping(
                value = "/api/orders/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<Map<String, Object>> find(
                @PathVariable("id") String id) {
            if ("missing".equals(id)) {
                return ResponseEntity.status(HttpStatus.NOT_FOUND)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(Map.of(
                                "code", "ORDER_NOT_FOUND",
                                "message", "Không tìm thấy đơn hàng"));
            }
            return ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.ETAG, "\"v3\"")
                    .body(Map.of(
                            "id", id,
                            "status", "READY",
                            "amount", 12500));
        }

        @PostMapping(
                value = "/api/orders",
                consumes = MediaType.APPLICATION_JSON_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<Map<String, Object>> create(
                @RequestBody Map<String, Object> request) {
            return ResponseEntity.status(HttpStatus.CREATED)
                    .location(URI.create("/api/orders/ord-102"))
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of(
                            "id", "ord-102",
                            "item", request.get("item"),
                            "quantity", request.get("quantity"),
                            "status", "CREATED"));
        }

        @DeleteMapping("/api/orders/{id}")
        public ResponseEntity<Void> deleteById(
                @PathVariable("id") String id) {
            return ResponseEntity.noContent().build();
        }
    }
}
```

### Đọc kết quả kiểm chứng

- **GET thành công:** `status().isOk()` xác nhận `200`; `contentTypeCompatibleWith(APPLICATION_JSON)` xác nhận body là JSON; `header().string(ETAG, ...)` so khớp phiên bản; ba `jsonPath(...)` bảo vệ các giá trị nghiệp vụ quan trọng. Chỉ sau đó test mới ghi `orders-get`.
- **POST tạo mới:** `status().isCreated()` xác nhận `201`; header `Location` phải dẫn đến tài nguyên mới; body phải có mã, mặt hàng, số lượng và trạng thái như dự kiến. `requestFields(...)` mô tả body đầu vào; `responseFields(...)` mô tả kết quả.
- **GET không tồn tại:** `404` là **kết quả mong đợi** của kịch bản lỗi, không phải dấu hiệu tài liệu thất bại. Test xác nhận cả mã lỗi và thông điệp rồi sinh `orders-get-not-found` riêng.
- **DELETE:** `204` có response body rỗng, vì vậy test kiểm tra chuỗi rỗng và không mong đợi `Content-Type` của JSON. Không dùng `responseFields(...)` cho response không có payload.

Trong ứng dụng thật, controller và service thường nằm trong `src/main/java`. Ví dụ lồng controller vào class test để trình bày trọn vẹn và tạo dữ liệu ổn định; test này không xác minh database hoặc wiring thực tế.

## 5. Kiểm chứng status: chính xác hơn kiểm tra nhóm mã

Các matcher thông dụng:

| Kỳ vọng | Matcher | Tình huống |
| --- | --- | --- |
| `200 OK` | `status().isOk()` | Đọc tài nguyên thành công, trả payload. |
| `201 Created` | `status().isCreated()` | POST tạo tài nguyên mới. |
| `202 Accepted` | `status().isAccepted()` | Nhận xử lý bất đồng bộ. |
| `204 No Content` | `status().isNoContent()` | DELETE thành công, không có response body. |
| `400 Bad Request` | `status().isBadRequest()` | Dữ liệu request không hợp lệ. |
| `401 Unauthorized` | `status().isUnauthorized()` | Cần xác thực. |
| `403 Forbidden` | `status().isForbidden()` | Người dùng không đủ quyền. |
| `404 Not Found` | `status().isNotFound()` | Không tìm thấy tài nguyên. |
| `409 Conflict` | `status().isConflict()` | Xung đột trạng thái tài nguyên. |
| Status tùy chọn | `status().is(422)` | API dùng mã ngoài các matcher chuyên biệt. |

`status().is2xxSuccessful()` hoặc `status().is4xxClientError()` chỉ xác minh **nhóm** mã. Chúng hữu ích khi hợp đồng cho phép nhiều status, nhưng tài liệu endpoint thường cần một tình huống rõ ràng. Chẳng hạn, dùng `is2xxSuccessful()` có thể không phát hiện việc `POST` trả `200` thay vì `201`.

Một lỗi logic thường gặp là viết:

```java
// Kiểm tra quá rộng: 200 OK cũng qua được dù mong đợi 201 Created.
mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"item\":\"book\",\"quantity\":2}"))
        .andExpect(status().is2xxSuccessful());
```

Khi hợp đồng là `201 Created`, hãy dùng `status().isCreated()` và xác minh thêm `Location`, response body.

Nếu cùng endpoint trả các status khác nhau theo dữ liệu, viết **các test riêng** với identifier riêng (ví dụ `orders-get` và `orders-get-not-found`) để snippet của thành công và lỗi không bị ghi đè lẫn nhau.

## 6. Kiểm chứng header: có mặt, không có mặt và đúng giá trị

Header có thể quyết định cách client xử lý response. Các assertion nên phản ánh hợp đồng thay vì chỉ mô tả tên header.

```java
.andExpect(header().exists(HttpHeaders.LOCATION))
.andExpect(header().string(
        HttpHeaders.LOCATION, "/api/orders/ord-102"))
.andExpect(header().string(HttpHeaders.ETAG, "\"v3\""))
.andExpect(header().doesNotExist("X-Debug-Token"))
```

Đây là những lời gọi **minh họa** để nối vào các `ResultActions` phù hợp, không phải một chuỗi áp dụng cùng lúc cho mọi endpoint.

Các điểm cần chú ý:

- **`Location`:** với `201`, kiểm tra URI tài nguyên mới; `header().exists(...)` chỉ xác nhận có header, `header().string(...)` mới xác nhận giá trị mong đợi.
- **`Content-Type`:** đây cũng là header HTTP, nhưng thường kiểm tra dễ đọc hơn bằng `content().contentType(...)` hoặc `content().contentTypeCompatibleWith(...)`.
- **`ETag`:** giá trị ETag hợp lệ thường có dấu ngoặc kép, ví dụ `"v3"`. So khớp đúng phần chuỗi mà endpoint công bố.
- **Header động:** correlation ID hoặc request ID được tạo ngẫu nhiên không nên được kiểm tra bằng hằng số cố định trong môi trường tạo ID động. Có thể kiểm tra `exists(...)` hoặc dùng matcher theo định dạng, rồi kiểm tra tương quan với request nếu hợp đồng yêu cầu.
- **Header nhạy cảm:** không sử dụng token, cookie hoặc bí mật thực trong ví dụ test được đưa vào snippet công khai.

### Phân biệt kiểm tra `Content-Type` và `Accept`

`Accept` là header **request** biểu thị định dạng client muốn nhận. `Content-Type` của **response** mô tả định dạng server thực trả:

```java
mockMvc.perform(get("/api/orders/{id}", "ord-101")
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON));
```

Đặt `accept(APPLICATION_JSON)` **không đủ** để chứng minh server đã trả JSON. Nếu `Content-Type` yêu cầu chính xác `application/json`, dùng `content().contentType(MediaType.APPLICATION_JSON)`. Nếu có thể kèm tham số charset hoặc media type tương thích, `contentTypeCompatibleWith(...)` thường linh hoạt hơn.

Với `204 No Content`, không áp dụng matcher kiểm tra JSON content type như với `200`. Kiểm tra sự vắng mặt của body và chỉ kiểm tra header nào thực sự thuộc hợp đồng.

## 7. Kiểm chứng body: nội dung, cấu trúc và trường hợp rỗng

### Dùng `jsonPath` để kiểm tra dữ liệu JSON quan trọng

```java
.andExpect(jsonPath("$.id").value("ord-101"))
.andExpect(jsonPath("$.status").value("READY"))
.andExpect(jsonPath("$.amount").value(12500))
```

Ưu điểm của `jsonPath` là không phụ thuộc thứ tự các field JSON. Khi API trả danh sách, có thể kiểm tra một phần tử hoặc số phần tử bằng JSONPath và matcher phù hợp:

```java
// Đoạn nối tiếp sau mockMvc.perform(...), với body có items.
.andExpect(jsonPath("$.items[0].id").value("ord-101"))
.andExpect(jsonPath("$.items[0].status").value("READY"))
```

Đối với field tùy chọn, hãy phân biệt:

- Field **bắt buộc** theo hợp đồng: xác nhận `exists()` hoặc một giá trị cụ thể.
- Field **không được phép có** trong response: dùng matcher kiểm tra không tồn tại.
- Field **được phép null hoặc vắng mặt**: thiết kế assertions theo hợp đồng, tránh kiểm tra một giá trị cố định khi không có cam kết đó.

Khi cần kiểm tra toàn bộ JSON, có thể dùng matcher JSON phù hợp với thư viện test được cài đặt, nhưng tránh so sánh chuỗi thô nếu thứ tự key hoặc khoảng trắng không quan trọng.

### Kiểm tra plain text hoặc response rỗng

Với endpoint trả văn bản:

```java
mockMvc.perform(get("/api/health"))
        .andExpect(status().isOk())
        .andExpect(content().string("UP"));
```

Với `204 No Content`:

```java
mockMvc.perform(delete("/api/orders/{id}", "ord-102"))
        .andExpect(status().isNoContent())
        .andExpect(content().string(""))
        .andDo(document("orders-delete"));
```

Đoạn `DELETE` trên là ví dụ rút gọn **chỉ khi endpoint có hành vi tương ứng**. Nếu cần snippet `path-parameters.adoc`, thêm `pathParameters(...)` như trong ví dụ hoàn chỉnh.

### Vì sao `responseFields(...)` không thay cho `jsonPath(...)`?

`responseFields(...)` của Spring REST Docs kiểm tra và mô tả **cấu trúc** payload. Nó giúp phát hiện các field không được mô tả hoặc descriptor trỏ đến field không tồn tại; nhưng không diễn đạt đầy đủ expected business value.

Ví dụ, API trả:

```json
{
  "id": "ord-101",
  "status": "CANCELLED",
  "amount": 12500
}
```

Nếu tài liệu chỉ dùng:

```java
responseFields(
        fieldWithPath("id").description("Mã đơn hàng"),
        fieldWithPath("status").description("Trạng thái"),
        fieldWithPath("amount").description("Giá trị"))
```

thì các descriptor này vẫn mô tả ba field hiện diện. Nhưng nếu bài kiểm thử đang kiểm chứng đơn hàng `READY`, chính `jsonPath("$.status").value("READY")` mới phát hiện được giá trị sai. Vì vậy **assertion nghiệp vụ và kiểm tra cấu trúc của snippet bổ trợ nhau**.

## 8. Tách kiểm thử thành công và lỗi trước khi sinh tài liệu

Một số lỗi không làm response mất định dạng JSON; chẳng hạn một API có thể trả `404` với payload:

```json
{
  "code": "ORDER_NOT_FOUND",
  "message": "Không tìm thấy đơn hàng"
}
```

Nếu chỉ kiểm tra `Content-Type` và `responseFields(...)`, test có thể ghi response lỗi vào tài liệu của kịch bản thành công mà không nhận ra sai status. Do đó:

```java
mockMvc.perform(get("/api/orders/{id}", "missing"))
        .andExpect(status().isNotFound())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"))
        .andDo(document("orders-get-not-found",
                pathParameters(
                        parameterWithName("id").description("Mã đơn hàng")),
                responseFields(
                        fieldWithPath("code").description("Mã lỗi"),
                        fieldWithPath("message").description("Thông báo"))));
```

Với lỗi xác thực/phân quyền (`401`/`403`), cần cấu hình security filter trong phạm vi test rồi kiểm tra đúng status và body/header mong đợi. Nếu MockMvc standalone chưa áp dụng bảo mật của ứng dụng, không thể dùng kết quả `200` từ controller làm bằng chứng rằng endpoint không yêu cầu xác thực.

Trong CI, test tài liệu không nên giấu lỗi bằng cách bỏ matcher khó hoặc chuyển mọi field thành `optional()`/`ignored()`. Những phương thức đó chỉ phù hợp khi hợp đồng API thật sự cho phép field tùy chọn hoặc cần bỏ qua field nhất định.

## 9. Khi assertion thất bại, nên chẩn đoán thế nào?

### In kết quả để hiểu response thực tế

```java
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;

mockMvc.perform(get("/api/orders/{id}", "ord-101")
                .accept(MediaType.APPLICATION_JSON))
        .andDo(print())
        .andExpect(status().isOk());
```

`print()` hữu ích để xem request, handler, status, header, body khi test thất bại. Chỉ dùng dữ liệu test phù hợp vì log có thể chứa header, cookie hoặc payload nhạy cảm.

### Một số nguyên nhân và hướng xử lý

| Kiểm tra thất bại | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Mong `200` nhưng nhận `404` | URL/method sai hoặc controller chưa đăng ký | Kiểm tra `@GetMapping`, URI template và setup MockMvc. |
| Mong `201` nhưng nhận `200` | Endpoint trả status không đúng hợp đồng | Sửa controller hoặc thống nhất lại hợp đồng, sau đó cập nhật test và tài liệu. |
| Mong `201` nhưng nhận `415` | `Content-Type` của request không phù hợp | Đặt `contentType(APPLICATION_JSON)`, kiểm tra `consumes` và converter. |
| Mong JSON nhưng `Content-Type` sai | Server trả HTML lỗi, plain text hoặc converter khác | Đọc response, status và cấu hình converter/advice. |
| Header `Location` sai hoặc thiếu | Controller không đặt URI tài nguyên mới | Kiểm tra `ResponseEntity.created(...)` và đường dẫn dự kiến. |
| Header `ETag` không khớp | Định dạng chuỗi ETag, dấu ngoặc kép hoặc phiên bản khác | Kiểm tra header thực và logic sinh ETag. |
| `jsonPath` không tìm thấy field | Body không phải JSON mong đợi, field sai tên hoặc response là lỗi | Kiểm tra status, body thực, JSONPath và hợp đồng API. |
| `jsonPath` đúng nhưng `responseFields` thất bại | Còn field chưa mô tả hoặc descriptor không phù hợp | Mô tả đủ các field thực, dùng `optional()`/`ignored()` khi hợp đồng cho phép. |
| `204` nhưng body không rỗng | Endpoint đang trả payload | Sửa controller hoặc cập nhật hợp đồng nếu status khác được thiết kế. |
| Không có `generated-snippets` | Chưa gọi `document(...)`, test dừng ở matcher, hoặc thiếu cấu hình REST Docs | Kiểm tra kết quả test, extension và builder trước khi tìm đường dẫn output. |

Nếu muốn kiểm tra một response không quá phức tạp, có thể lấy `MvcResult` sau các matcher và đọc `getResponse().getContentAsString()`, nhưng thường `status`, `header`, `content` và `jsonPath` là đủ rõ ràng.

## 10. Biên soạn snippet đã kiểm chứng thành tài liệu

Chạy test bằng Gradle:

```bash
./gradlew test
```

Trên Windows có thể dùng `gradlew.bat test`. Với cấu hình mặc định tương ứng, snippet Gradle thường ở `build/generated-snippets/`; với Maven thường ở `target/generated-snippets/`. Sau ví dụ phần 4, cấu trúc rút gọn có thể là:

```text
build/generated-snippets/
├── orders-get/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   ├── path-parameters.adoc
│   ├── response-headers.adoc
│   └── response-fields.adoc
├── orders-create/
│   ├── request-fields.adoc
│   ├── response-headers.adoc
│   └── response-fields.adoc
├── orders-get-not-found/
│   ├── http-response.adoc
│   └── response-fields.adoc
└── orders-delete/
    └── http-response.adoc
```

Đây là danh sách **tiêu biểu được rút gọn**, không phải danh sách file đầy đủ. Spring REST Docs còn có thể tạo `curl-request.adoc`, `httpie-request.adoc`, `request-body.adoc` và `response-body.adoc` tùy phiên bản, cấu hình và bộ snippet mặc định.

Ví dụ Asciidoctor:

```adoc
= Orders API

== Lấy đơn hàng

include::{snippets}/orders-get/http-request.adoc[]
include::{snippets}/orders-get/path-parameters.adoc[]
include::{snippets}/orders-get/http-response.adoc[]
include::{snippets}/orders-get/response-headers.adoc[]
include::{snippets}/orders-get/response-fields.adoc[]

== Tạo đơn hàng

include::{snippets}/orders-create/request-fields.adoc[]
include::{snippets}/orders-create/http-response.adoc[]
include::{snippets}/orders-create/response-headers.adoc[]

== Không tìm thấy đơn hàng

include::{snippets}/orders-get-not-found/http-response.adoc[]
include::{snippets}/orders-get-not-found/response-fields.adoc[]

== Xóa đơn hàng

include::{snippets}/orders-delete/http-response.adoc[]
```

Thuộc tính `{snippets}` phải trỏ đúng thư mục output. Nếu sản phẩm dùng Markdown, hãy dùng template/chuyển đổi hoặc cơ chế nhúng phù hợp, vì các snippet mặc định thường là AsciiDoc. Trình tự build/CI nên là **test HTTP → sinh snippet → biên soạn Asciidoctor/Markdown → xuất bản**, để tài liệu mới chỉ được biên soạn khi các kiểm chứng HTTP đã đạt.

## 11. Bài tập thực hành

1. **Kiểm tra status sai:** thay `201` trong controller POST thành `200`, giữ `status().isCreated()`; giải thích vì sao test thất bại trước `document(...)`.
2. **Kiểm tra header:** xóa `Location` của POST, giữ matcher `header().string(...)`; sửa controller để khôi phục hợp đồng.
3. **Kiểm tra body:** thay `status: READY` thành `CANCELLED` trong GET, giữ `jsonPath("$.status").value("READY")`; quan sát điểm lỗi.
4. **Tài liệu hóa lỗi:** tạo test `400 Bad Request` cho request thiếu field bắt buộc; xác minh status, cấu trúc JSON lỗi và tạo identifier riêng.
5. **No Content:** cố ý trả JSON khi DELETE và kiểm tra vì sao `content().string("")` không đạt; sửa response về `204` với body rỗng.
6. **Tích hợp tài liệu:** chạy lại test, ghép `orders-get`, `orders-create`, `orders-get-not-found` và `orders-delete` vào tài liệu Asciidoctor/Markdown; nối bước tạo snippet vào CI.

**Tiêu chí đạt:** mỗi test thể hiện rõ status, header, body mà tình huống yêu cầu; matcher sai khiến test thất bại; snippet chỉ được ghi khi các assertion đứng trước nó đều đạt; tài liệu được biên soạn từ những snippet mới sinh.

## 12. Checklist trước khi gọi `document(...)`

- [ ] Xác định đúng status cần có cho từng kịch bản: thành công, tạo mới, lỗi hay không có body.
- [ ] Kiểm tra header quan trọng bằng matcher phù hợp, bao gồm **giá trị** khi có yêu cầu cụ thể.
- [ ] Kiểm tra `Content-Type` của response nếu endpoint trả body có định dạng xác định.
- [ ] Kiểm tra field/giá trị nghiệp vụ bằng `jsonPath(...)` hoặc matcher nội dung tương đương.
- [ ] Với `204`, kiểm tra body rỗng; tránh mô tả `responseFields(...)` khi không có payload.
- [ ] Đặt `andExpect(...)` trước `andDo(document(...))` để không ghi response sai hợp đồng.
- [ ] Mô tả trường, parameter, header có thật; tách identifier cho từng endpoint và từng kịch bản lỗi.
- [ ] Bảo đảm tác vụ build/CI chỉ biên soạn tài liệu từ các snippet sinh ra sau khi test đạt.

**Ghi nhớ:** `andExpect(status/header/body)` bảo vệ **hành vi HTTP mà ứng dụng cam kết**; `document(...)` ghi lại **dữ liệu đã được kiểm tra** để tạo tài liệu. Khi hai phần được đặt đúng thứ tự, tài liệu REST API có thể kiểm chứng cùng với bài test và không âm thầm công bố một response sai hợp đồng.
