# Giá trị mặc định và điều kiện áp dụng của query parameters trong Spring REST Docs

## 1. Vấn đề: tham số có thể vắng mặt nhưng API vẫn có quy tắc xử lý

Xét endpoint tìm đơn hàng:

```http
GET /api/orders?page=2&status=PAID HTTP/1.1
Host: api.example.test
```

Client chỉ gửi `page` và `status`. Server có thể tự áp dụng `size=20` vì client không gửi `size`. Tương tự, một API có thể cho phép bỏ qua `fromDate` và `toDate` khi không lọc ngày, nhưng **yêu cầu gửi cả hai** nếu người dùng bật lọc theo khoảng ngày.

Đây là hai vấn đề riêng biệt:

- **Giá trị mặc định (default value):** Khi client không cung cấp một tham số, server lựa chọn giá trị nào?
- **Điều kiện áp dụng (conditional applicability):** Khi nào một tham số được phép, bắt buộc, bị bỏ qua hoặc phải đi kèm tham số khác?

Trong module **SPRING_REST_DOCS**, Spring REST Docs sinh tài liệu REST API có thể kiểm chứng từ kiểm thử HTTP với **MockMvc**, **WebTestClient** hoặc **REST Assured**. Ở chương **Query parameters**, ta mô tả hai vấn đề trên bằng `parameterWithName(...).description(...)`, sử dụng `optional()` khi tên tham số có thể vắng mặt, và viết thêm kiểm thử hành vi để xác nhận các quy tắc mặc định và điều kiện.

Sau bài học, bạn có thể:

1. Phân biệt giá trị mặc định của Spring MVC với cách REST Docs kiểm tra query string.
2. Mô tả đúng default, phạm vi áp dụng, giá trị hợp lệ và quan hệ giữa các tham số.
3. Viết endpoint cùng kiểm thử HTTP cho trường hợp vắng mặt, giá trị rỗng, giá trị tường minh và tham số phụ thuộc nhau.
4. Sinh `query-parameters.adoc`, đưa vào tài liệu Asciidoctor/Markdown và sử dụng trong build/CI.

## 2. Giá trị mặc định thuộc hợp đồng xử lý của server

Trong Spring MVC, `@RequestParam` có thuộc tính `defaultValue`:

```java
@GetMapping("/api/orders")
public String list(
        @RequestParam(name = "page", defaultValue = "0") int page,
        @RequestParam(name = "size", defaultValue = "20") int size,
        @RequestParam(name = "status", defaultValue = "ALL") String status) {
    return "page=" + page + ";size=" + size + ";status=" + status;
}
```

Ở ví dụ này, các giá trị `0`, `20`, `ALL` là quyết định của server. Việc sử dụng `defaultValue` cũng khiến tham số tương ứng không bắt buộc ở tầng binding của Spring MVC.

### 2.1. Vắng mặt, giá trị rỗng và giá trị tường minh

| Request gửi đến | Giá trị `page` trong controller | Giải thích |
| --- | --- | --- |
| `/api/orders` | `0` | Không gửi `page`, dùng mặc định |
| `/api/orders?page=` | `0` | Có tên `page` nhưng giá trị rỗng; `@RequestParam(defaultValue = "0")` sử dụng mặc định |
| `/api/orders?page=3` | `3` | Giá trị tường minh ghi đè mặc định |
| `/api/orders?page=abc` | Lỗi chuyển kiểu, thông thường phản hồi HTTP 400 | Giá trị không rỗng nhưng không phải số nguyên |
| `/api/orders?page=-1` | `-1` sau khi binding | Chuyển kiểu thành công; chỉ bị từ chối nếu ứng dụng có validation cho `page >= 0` |

Không nên đồng nhất **giá trị rỗng** với **giá trị chỉ chứa khoảng trắng**: `page=%20` có thể đi qua bước chuyển đổi theo cấu hình khác nhau. Nếu hợp đồng cần quy định xử lý whitespace, hãy kiểm thử chính xác request đó.

Điểm dễ nhầm: Giá trị mặc định do server quyết định **không xuất hiện ngược vào query string của HTTP request**. Ví dụ, request `GET /api/orders?page=2` vẫn không chứa `size` dù controller đã nhận `size=20`. REST Docs tài liệu hóa request thực, không tự thêm `size=20` vào request snippet.

### 2.2. Khi không dùng `defaultValue`

```java
@RequestParam(name = "status", required = false) String status
```

Với kiểu tham chiếu `String`, khi thiếu `status`, controller thường nhận `null`. Nếu ứng dụng quyết định mặc định trong service, nội dung `description(...)` vẫn cần mô tả giá trị người dùng cuối thực sự nhận được; không nên đoán mặc định từ annotation. Với tham số kiểu nguyên thủy, enum hoặc kiểu dữ liệu đặc biệt, cần kiểm tra cách binding khi thiếu giá trị.

## 3. Mô tả mặc định bằng `parameterWithName` và `optional()`

Giả sử hợp đồng API của nhóm quy định:

| Tham số | Có thể bỏ qua? | Mặc định/điều kiện |
| --- | --- | --- |
| `page` | Có | Chỉ số trang từ 0; mặc định `0` |
| `size` | Có | Từ 1 đến 100; mặc định `20` |
| `status` | Có | `ALL`, `PAID` hoặc `CANCELLED`; mặc định `ALL` |
| `fromDate` | Có điều kiện | Ngày bắt đầu theo `yyyy-MM-dd`; **phải đi cùng** `toDate` |
| `toDate` | Có điều kiện | Ngày kết thúc theo `yyyy-MM-dd`; **phải đi cùng** `fromDate` và không được trước `fromDate` |

Mô tả trong Spring REST Docs:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;

queryParameters(
    parameterWithName("page")
        .description("Chỉ số trang từ 0; mặc định 0 nếu bỏ qua hoặc gửi rỗng")
        .optional(),
    parameterWithName("size")
        .description("Số kết quả/trang (1-100); mặc định 20")
        .optional(),
    parameterWithName("status")
        .description("ALL, PAID hoặc CANCELLED; mặc định ALL")
        .optional(),
    parameterWithName("fromDate")
        .description("Ngày bắt đầu yyyy-MM-dd; nếu truyền thì phải có toDate")
        .optional(),
    parameterWithName("toDate")
        .description("Ngày kết thúc yyyy-MM-dd; phải có fromDate và không sớm hơn fromDate")
        .optional()
)
```

`queryParameters(...)` là factory của `org.springframework.restdocs.request.RequestDocumentation`. Mỗi `parameterWithName("...")` tạo một descriptor cho **tên** tham số. `description(...)` tạo nội dung giải thích trên tài liệu; `optional()` cho REST Docs biết tên đó **được phép không xuất hiện trong request của kiểm thử**.

### Những điều `optional()` không thực hiện

- Không thiết lập giá trị mặc định cho controller.
- Không xác minh rằng `size` nằm trong khoảng 1–100.
- Không kiểm tra `status` thuộc một tập giá trị.
- Không biết rằng `fromDate` chỉ hợp lệ khi `toDate` cũng xuất hiện.
- Không tự suy luận giá trị mặc định từ `@RequestParam`, `@PageableDefault` hoặc cấu hình service.

**Vì vậy, mô tả đúng mới là bước đầu.** Để điều kiện trong tài liệu có ý nghĩa kiểm chứng, cần validation và các HTTP test cho nhánh được phép lẫn nhánh bị từ chối.

## 4. Điều kiện áp dụng: từ "có thể vắng mặt" đến "bắt buộc khi..."

Một tham số có thể **tùy chọn trong request thông thường** nhưng **bắt buộc theo điều kiện**. Với hai tham số lọc khoảng ngày:

| `fromDate` | `toDate` | Kết quả theo hợp đồng minh họa |
| --- | --- | --- |
| Không gửi | Không gửi | Hợp lệ, không lọc theo ngày |
| Có | Có | Hợp lệ nếu cả hai đúng định dạng và `fromDate <= toDate` |
| Có | Không gửi | Không hợp lệ: thiếu ngày kết thúc |
| Không gửi | Có | Không hợp lệ: thiếu ngày bắt đầu |
| Có nhưng rỗng | Có | Không hợp lệ: ngày bắt đầu không phải ngày ISO hợp lệ |

REST Docs không có một modifier `conditionallyRequired()` tự động kiểm tra các quan hệ này trong `queryParameters(...)`. Việc ghi cả hai `.optional()` là đúng vì mỗi tham số có thể vắng mặt khi **cả cặp cùng vắng mặt**. Điều kiện "nếu có A thì phải có B" được mô tả bằng `description(...)` và được thực thi tại controller/service/validation.

Ví dụ về một số quan hệ khác:

| Mối quan hệ | Ví dụ | Điều phải viết trong tài liệu |
| --- | --- | --- |
| **Chỉ áp dụng khi chọn chế độ** | `cursor` chỉ dùng nếu `mode=cursor` | Giá trị `mode` nào kích hoạt `cursor`, có bắt buộc `cursor` ở chế độ đó không |
| **Loại trừ nhau** | `cursor` không được dùng cùng `page` | Server từ chối hay bỏ qua khi client gửi cả hai |
| **Yêu cầu theo cặp** | `fromDate` và `toDate` | Có thể bỏ cả hai; nếu dùng thì phải gửi đủ |
| **Mặc định phụ thuộc tham số khác** | `sort` mặc định theo `status` | Liệt kê các trường hợp mặc định, quy tắc ưu tiên và kết quả nếu không gửi `sort` |
| **Có giới hạn theo điều kiện** | `size` tối đa 100 khi `mode=search` | Phạm vi hợp lệ trong từng chế độ và mã lỗi nếu vượt giới hạn |

Các quy tắc này là **thiết kế API của từng ứng dụng**, không phải khả năng Spring REST Docs tự động áp đặt.

## 5. Xây dựng controller minh họa có default và validation điều kiện

Controller sau thực thi chính xác hợp đồng ở mục 3 và 4. Nó trả về chuỗi để dễ đối chiếu dữ liệu trong test, thay vì truy vấn database hoặc tạo JSON:

```java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
class OrderController {

    private static final Set<String> STATUSES =
            Set.of("ALL", "PAID", "CANCELLED");

    @GetMapping("/api/orders")
    public String search(
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "size", defaultValue = "20") int size,
            @RequestParam(name = "status", defaultValue = "ALL") String status,
            @RequestParam(name = "fromDate", required = false) String fromDate,
            @RequestParam(name = "toDate", required = false) String toDate) {

        if (page < 0 || size < 1 || size > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "page/size out of range");
        }
        if (!STATUSES.contains(status)) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "status is unsupported");
        }

        // Cặp ngày cùng vắng mặt hoặc cùng xuất hiện mới hợp lệ.
        if ((fromDate == null) != (toDate == null)) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "fromDate and toDate must appear together");
        }

        String range = "none";
        if (fromDate != null) {
            try {
                LocalDate from = LocalDate.parse(fromDate);
                LocalDate to = LocalDate.parse(toDate);

                if (from.isAfter(to)) {
                    throw new ResponseStatusException(
                            HttpStatus.BAD_REQUEST, "fromDate is after toDate");
                }
                range = from + ".." + to;
            } catch (DateTimeParseException exception) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "invalid ISO date", exception);
            }
        }

        return "page=" + page
                + ";size=" + size
                + ";status=" + status
                + ";range=" + range;
    }
}
```

Lưu ý:

- `defaultValue` xử lý trường hợp tham số `page`, `size` hoặc `status` vắng mặt hay rỗng.
- Kiểm tra khoảng số, danh mục trạng thái và ngày nằm **trong controller**, nên các điều kiện đã mô tả có ý nghĩa thực tế.
- `LocalDate.parse(...)` theo ISO date chuẩn `yyyy-MM-dd`; các giá trị ngày không hợp lệ bị trả HTTP 400.
- Điều kiện cặp `fromDate`/`toDate` áp dụng khi một trong hai tên được cung cấp. Giá trị rỗng như `fromDate=` không được xem là một ngày hợp lệ.
- Đây là endpoint minh họa để học việc document; dự án thực nên đặt quy tắc nghiệp vụ trong tầng service/validation phù hợp.

## 6. Kiểm thử MockMvc và sinh snippet REST Docs

Để tài liệu có thể kiểm chứng, cần kết hợp assertion hành vi với `document(...)`. Ví dụ dùng JUnit 5, MockMvc và Spring REST Docs:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class OrderQueryDefaultsDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsOptionalParametersAndTheirDefaults() throws Exception {
        // Client chỉ gửi page; size/status dùng mặc định,
        // fromDate/toDate cùng vắng mặt nên không lọc ngày.
        mockMvc.perform(get("/api/orders").queryParam("page", "2"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "page=2;size=20;status=ALL;range=none"))
                .andDo(document("orders-search-defaults",
                        queryParameters(
                                parameterWithName("page")
                                        .description("Trang từ 0; mặc định 0")
                                        .optional(),
                                parameterWithName("size")
                                        .description("Số kết quả/trang (1-100); mặc định 20")
                                        .optional(),
                                parameterWithName("status")
                                        .description("ALL, PAID, CANCELLED; mặc định ALL")
                                        .optional(),
                                parameterWithName("fromDate")
                                        .description("Ngày bắt đầu yyyy-MM-dd; phải đi cùng toDate")
                                        .optional(),
                                parameterWithName("toDate")
                                        .description("Ngày kết thúc yyyy-MM-dd; phải đi cùng fromDate")
                                        .optional()
                        )));
    }

    @Test
    void appliesDefaultsWhenValuesAreMissing() throws Exception {
        mockMvc.perform(get("/api/orders"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "page=0;size=20;status=ALL;range=none"));
    }

    @Test
    void appliesDefaultsWhenValuesAreEmpty() throws Exception {
        mockMvc.perform(get("/api/orders")
                        .queryParam("page", "")
                        .queryParam("size", "")
                        .queryParam("status", ""))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "page=0;size=20;status=ALL;range=none"));
    }

    @Test
    void acceptsBothDateParameters() throws Exception {
        mockMvc.perform(get("/api/orders")
                        .queryParam("fromDate", "2026-11-01")
                        .queryParam("toDate", "2026-11-30"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "page=0;size=20;status=ALL;range=2026-11-01..2026-11-30"));
    }

    @Test
    void rejectsPartialDateRange() throws Exception {
        mockMvc.perform(get("/api/orders")
                        .queryParam("fromDate", "2026-11-01"))
                .andExpect(status().isBadRequest());

        mockMvc.perform(get("/api/orders")
                        .queryParam("toDate", "2026-11-30"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidValues() throws Exception {
        mockMvc.perform(get("/api/orders").queryParam("size", "101"))
                .andExpect(status().isBadRequest());

        mockMvc.perform(get("/api/orders").queryParam("page", "oops"))
                .andExpect(status().isBadRequest());

        mockMvc.perform(get("/api/orders").queryParam("status", "UNKNOWN"))
                .andExpect(status().isBadRequest());

        mockMvc.perform(get("/api/orders")
                        .queryParam("fromDate", "2026-11-30")
                        .queryParam("toDate", "2026-11-01"))
                .andExpect(status().isBadRequest());
    }
}
```

Trong test document, chỉ `page=2` thực sự xuất hiện trong URL. Các descriptor khác được đánh dấu `.optional()` nên REST Docs không yêu cầu tên của chúng xuất hiện trong request đó. Tuy nhiên **bảng tài liệu vẫn có dòng mô tả** cho từng descriptor; mặc định và điều kiện đều do `description(...)` ghi rõ.

Các test khác kiểm chứng hành vi mà REST Docs **không tự kiểm tra**: default được áp dụng khi vắng/rỗng, cặp ngày chỉ hợp lệ khi đầy đủ, giá trị sai bị từ chối.

### 6.1. Tại sao cần `queryParam(...)`?

Với MockMvc và REST Docs phiên bản có `queryParameters(...)`, hãy dùng `.queryParam("page", "2")` hoặc URL `get("/api/orders?page=2")` để mô tả query string. `.param("page", "2")` chỉ thiết lập Servlet request parameter tổng quát, vốn có thể bắt nguồn từ query string hoặc form body; controller có thể nhận được giá trị trong khi REST Docs không thấy đúng query parameter.

### 6.2. Nếu quên `optional()` thì sao?

Ví dụ sau không phù hợp khi request thử nghiệm thiếu `size`:

```java
// Request GET /api/orders?page=2 không có size.
queryParameters(
    parameterWithName("page").description("Chỉ số trang"),
    parameterWithName("size").description("Mặc định 20")
)
```

`description("Mặc định 20")` là chữ mô tả, **không làm descriptor trở thành optional**. Khi `size` vắng mặt, Spring REST Docs mặc định sẽ báo lỗi vì descriptor đó được coi là bắt buộc. Cách sửa phù hợp là thêm `.optional()` nếu hợp đồng API thực sự cho phép bỏ qua `size`.

## 7. Đọc snippet và đưa vào tài liệu Asciidoctor/Markdown

Sau khi chạy test có `document("orders-search-defaults", ...)`, với cấu hình Gradle xuất snippets vào `build/generated-snippets`, có thể thấy:

```text
build/
  generated-snippets/
    orders-search-defaults/
      query-parameters.adoc
      http-request.adoc
      http-response.adoc
      curl-request.adoc
      ...
```

Tên thư mục phụ thuộc identifier `orders-search-defaults`; trong Maven, thư mục mặc định thường là `target/generated-snippets`. `query-parameters.adoc` trình bày tên và phần mô tả tham số; REST Docs không tự ghi con số default từ controller nếu descriptor không nói đến chúng.

Trang tài liệu `src/docs/asciidoc/orders.adoc` có thể chèn snippet:

```asciidoc
= Orders API

== Tìm kiếm đơn hàng

GET /api/orders

=== Query parameters

include::{snippets}/orders-search-defaults/query-parameters.adoc[]

=== Quy tắc lọc ngày

Nếu không truyền fromDate và toDate, API không lọc theo ngày.
Nếu dùng lọc ngày, phải truyền đủ hai tham số theo yyyy-MM-dd
và fromDate không được sau toDate.
```

Khi build bằng Asciidoctor, cấu hình `{snippets}` phải trỏ đến nơi test ghi snippets và task render tài liệu cần phụ thuộc task `test`.

Spring REST Docs cũng hỗ trợ định dạng snippet Markdown thông qua cấu hình `TemplateFormats.markdown()`. Nếu dùng Markdown, chọn công cụ ghép các snippet vào trang đầu ra phù hợp vì Markdown thông thường không có cú pháp `include` tiêu chuẩn như Asciidoctor.

## 8. Cùng ý tưởng với WebTestClient và REST Assured

Các descriptor `parameterWithName(...).description(...).optional()` không đổi theo công cụ kiểm thử. Thay đổi chủ yếu là cách gửi request và chỗ gắn `document(...)`.

### WebTestClient

Ví dụ client đã được cấu hình Spring REST Docs:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
        .uri(uriBuilder -> uriBuilder.path("/api/orders")
                .queryParam("page", 2)
                .build())
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("orders-search-defaults",
                queryParameters(
                        parameterWithName("page")
                                .description("Trang từ 0; mặc định 0")
                                .optional(),
                        parameterWithName("size")
                                .description("Số kết quả/trang; mặc định 20")
                                .optional()
                )));
```

Ví dụ ở đây mô tả hai tên `page` và `size` của một hợp đồng rút gọn; với endpoint thực chứa thêm các tham số, nên mô tả đủ theo phạm vi request và tài liệu chính thức.

### REST Assured

Với tích hợp `spring-restdocs-restassured`, gửi request có query string bằng `queryParam(...)`; đặt `queryParameters(...)` trong cấu hình filter tài liệu hóa:

```java
given()
    .filter(documentationFilter)
    .queryParam("page", 2)
    .when()
    .get("/api/orders")
    .then()
    .statusCode(200);
```

`documentationFilter` ở đây đại diện cho filter đã được tạo với cấu hình REST Docs và `document(..., queryParameters(...))`; riêng đoạn gọi request chưa đủ để tạo snippet.

## 9. Quy trình build và CI

Một quy trình thực tế cho bài kiểm thử tài liệu:

1. Khai báo dependency Spring REST Docs tương ứng với công cụ đang dùng: `spring-restdocs-mockmvc`, `spring-restdocs-webtestclient` hoặc `spring-restdocs-restassured`; chọn phiên bản tương thích Spring Framework/Spring Boot.
2. Cấu hình output của task kiểm thử làm thư mục snippet, chẳng hạn `build/generated-snippets`.
3. Cho task Asciidoctor hoặc bước biên soạn Markdown phụ thuộc task test, cung cấp đường dẫn snippets cho bộ biên soạn.
4. Trong CI, chạy test và tác vụ xuất tài liệu; pipeline thất bại nếu test không đạt hoặc snippet bị thiếu/sai đường dẫn.

Để tránh tài liệu nói sai về default hoặc quan hệ điều kiện, cần duy trì **test hành vi** cùng test tạo snippet. Khi thay giá trị mặc định từ `20` sang `50`, chỉ sửa annotation/logic là chưa đủ: hãy cập nhật `description(...)` và assertion về trường hợp vắng mặt.

## 10. Sai sót thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Tài liệu ghi "mặc định 20" nhưng server trả 50 | `description(...)` được cập nhật thủ công, không tự đọc giá trị từ controller | Kiểm tra annotation/service và assertion khi không gửi `size` |
| Test REST Docs báo thiếu `size` dù controller dùng `defaultValue` | Descriptor `size` không có `.optional()` | Đánh dấu optional trong tài liệu nếu client được phép bỏ tham số |
| `fromDate` có mặt một mình nhưng tài liệu vẫn sinh thành công | REST Docs kiểm tra tên, không biết quan hệ với `toDate` | Thêm validation và test HTTP 400 |
| `page=abc` bị lỗi dù có mặc định 0 | `defaultValue` không thay thế giá trị tường minh không hợp lệ | Test conversion và thông báo lỗi phù hợp |
| `size=-1` đi qua tầng binding | Số nguyên hợp lệ về kiểu nhưng không hợp lệ về nghiệp vụ | Kiểm tra miền giá trị bằng validation |
| Query string không có `size` mặc dù response thể hiện size 20 | Default được áp dụng khi binding ở server | Mô tả default trong snippet, không kỳ vọng REST Docs tự thêm query vào request |
| Tài liệu build thành công nhưng thiếu bảng | Sai đường dẫn `{snippets}`, identifier hoặc thiếu `queryParameters(...)` | Kiểm tra output snippet và quan hệ phụ thuộc task |
| Dùng `relaxedQueryParameters(...)` che mất parameter mới | Chế độ relaxed cho phép tên chưa được mô tả | Ưu tiên `queryParameters(...)` nghiêm ngặt khi xuất tài liệu chính thức |

## 11. Bài tập thực hành

Thiết kế API giả định:

```http
GET /api/reports?format=CSV&month=2026-11&includeDetails=true HTTP/1.1
```

Hợp đồng:

- `format`: không bắt buộc, mặc định `JSON`, chỉ nhận `JSON` hoặc `CSV`.
- `month`: chỉ được truyền khi `format=CSV`; trong chế độ CSV, `month` là bắt buộc và có dạng `yyyy-MM`.
- `includeDetails`: không bắt buộc, mặc định `false`; chỉ có tác dụng ở chế độ CSV.

Hãy thực hiện:

1. Tạo endpoint áp dụng các mặc định và điều kiện trên. Quyết định rõ server sẽ **từ chối hay bỏ qua** `includeDetails` khi `format=JSON`, rồi thể hiện nhất quán trong code và tài liệu.
2. Viết `queryParameters(...)` mô tả từng tham số và `.optional()` hợp lý. Với `month`, nêu điều kiện bắt buộc theo `format` trong `description(...)`.
3. Viết test cho request không có query string, `?format=CSV&month=2026-11`, `?format=CSV` và `?format=JSON&month=2026-11`.
4. Thêm test cho `month` sai định dạng hoặc `includeDetails` sai kiểu boolean, kiểm tra mã lỗi HTTP.
5. Chèn snippet vào Asciidoctor hoặc quy trình Markdown của dự án; chạy kiểm thử cùng bước sinh tài liệu trong CI.

**Tiêu chí hoàn thành:** Có mô tả mặc định chính xác cho từng tham số; có test chứng minh default và điều kiện; snippet được sinh từ request thực và trang tài liệu sử dụng đúng snippet.

## 12. Ghi nhớ

Trong Spring REST Docs, `parameterWithName(...)` mô tả tên query parameter, `description(...)` là nơi công bố **mặc định và điều kiện sử dụng**, còn `optional()` chỉ làm tham số có thể vắng mặt trong request đang được document. Default thật thuộc cơ chế binding/logic ứng dụng; điều kiện phụ thuộc giữa các tham số phải được thực thi và kiểm tra bằng test riêng. Khi kết hợp cả hai, tài liệu Asciidoctor/Markdown được sinh từ test sẽ phản ánh một hợp đồng HTTP rõ ràng và có thể đưa vào build/CI.

### Tài liệu tham khảo

- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — Documenting your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/index.html)
- [Spring Framework — Method Arguments: `@RequestParam`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring Framework Javadoc — `RequestParam.defaultValue`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/RequestParam.html)
