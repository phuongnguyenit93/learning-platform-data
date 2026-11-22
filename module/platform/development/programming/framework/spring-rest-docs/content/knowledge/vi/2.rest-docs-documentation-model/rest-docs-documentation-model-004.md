# Snippet là mảnh tài liệu có thể nhúng vào tài liệu lớn

Trong **Spring REST Docs**, một bài kiểm thử HTTP có thể tạo ra nhiều **snippet**: đoạn ví dụ request, ví dụ response, bảng tham số đường dẫn, bảng query parameter, bảng request/response header, bảng trường JSON hoặc lệnh cURL. Mỗi snippet là một **mảnh nội dung tài liệu được sinh từ operation đã kiểm thử**, có thể đưa vào một trang mô tả endpoint hoặc một bộ tài liệu API lớn hơn.

Bài này thuộc chương **Mô hình tài liệu** của module `SPRING_REST_DOCS`. Mục đích của module là tạo tài liệu REST API có thể kiểm chứng từ test với **MockMvc**, **WebTestClient** hoặc **REST Assured**, mô tả request, response, payload, tham số và header, sau đó biên soạn **Asciidoctor/Markdown** trong quy trình build và CI. Trọng tâm của bài là cách một snippet được sinh, được nhận diện, được nhúng vào trang tài liệu, được tái sử dụng đúng cách và được kiểm soát khi API thay đổi.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao snippet là **đơn vị nội dung nhỏ** chứ không phải toàn bộ tài liệu endpoint.
2. Phân biệt snippet mặc định về dữ liệu HTTP với snippet bảng mô tả được yêu cầu bởi descriptor.
3. Viết một test Spring REST Docs tạo những snippet cần thiết cho một operation.
4. Chèn snippet vào trang AsciiDoc bằng `include`, đồng thời bổ sung ngữ cảnh nghiệp vụ do con người viết.
5. Thiết kế đường dẫn, tên operation và quy trình build để tránh thiếu, nhầm hoặc dùng snippet cũ.
6. Nhận ra những khác biệt khi xuất bản tài liệu Markdown thay vì Asciidoctor.

## 2. Snippet là gì, và không phải là gì?

Giả sử API có endpoint `GET /api/products/{productId}`. Người tích hợp API cần biết:

- Cách gọi endpoint, gồm method, path, header và query parameter nếu có.
- Request có body hay không.
- Khi gọi thành công, status, response header và JSON sẽ như thế nào.
- `productId`, `name`, `price` và các field khác mang ý nghĩa gì.
- Những tình huống nào trả `400`, `404` hoặc `403` theo hợp đồng của API.

Một file `http-response.adoc` có thể chứa ví dụ response được ghi lại từ test. Một file `response-fields.adoc` lại chứa bảng diễn giải các field. **Từng file chỉ trả lời một phần câu hỏi**. Trang tài liệu hoàn chỉnh kết hợp chúng với tiêu đề, mô tả endpoint, điều kiện gọi, thông tin lỗi và liên kết tới các phần khác.

Có thể hình dung quan hệ như sau:

```text
HTTP test cho một operation
              │
              ▼
         Spring REST Docs
              │
              ├── http-request.adoc       (mẫu lời gọi)
              ├── http-response.adoc      (mẫu kết quả)
              ├── path-parameters.adoc    (bảng path parameter)
              ├── query-parameters.adoc   (bảng query parameter)
              ├── request-headers.adoc    (bảng request header)
              └── response-fields.adoc    (bảng trường response)
                          │
                          ▼
          Trang tài liệu "Tra cứu sản phẩm"
          ┌───────────────────────────────┐
          │ Mục đích và quyền truy cập    │
          │ Mẫu request                  │
          │ Bảng tham số                 │
          │ Mẫu response                 │
          │ Bảng JSON fields             │
          │ Các mã lỗi và ví dụ tương ứng│
          └───────────────────────────────┘
                          │
                          ▼
           Bộ tài liệu API của dịch vụ
```

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Operation** | Một lần trao đổi request/response được Spring REST Docs ghi nhận | Test gọi `GET /api/products/7` và nhận `200` |
| **Snippet** | Mảnh tài liệu sinh từ operation và cấu hình mô tả | `products-get/http-response.adoc` |
| **Trang endpoint** | Trình bày cách sử dụng một hành vi API | Mục “Lấy chi tiết sản phẩm” |
| **Bộ tài liệu API** | Tập hợp nhiều trang, phần mở đầu, quy tắc chung và tham chiếu | Tài liệu quản lý sản phẩm, đơn hàng và xác thực |

**Một operation có thể sinh nhiều snippet; một trang tài liệu có thể chèn snippet từ nhiều operation**. Chẳng hạn trang `GET /api/products/{productId}` có thể chứa snippet của cả `200 OK` và `404 Not Found`.

## 3. Hai nhóm snippet thường gặp

Spring REST Docs cung cấp các snippet dựa trên dữ liệu request/response và các snippet được sinh khi test yêu cầu mô tả một thành phần cụ thể.

### 3.1. Snippet thể hiện dữ liệu HTTP quan sát được

Những snippet mặc định thông dụng (trừ khi cấu hình lại bộ snippet mặc định) là:

| Tên file | Nội dung | Khi nào nên chèn |
| --- | --- | --- |
| `http-request.adoc` | HTTP request line, header và body | Khi người đọc cần một mẫu HTTP đầy đủ |
| `http-response.adoc` | HTTP response status, header và body | Khi cần hiển thị mẫu kết quả đầy đủ |
| `curl-request.adoc` | Ví dụ gọi API bằng cURL | Khi người đọc muốn thử API nhanh |
| `httpie-request.adoc` | Ví dụ gọi API bằng HTTPie | Khi bộ tài liệu ưu tiên HTTPie |
| `request-body.adoc` | Chỉ phần request body | Khi phần body dài hoặc cần giải thích riêng |
| `response-body.adoc` | Chỉ phần response body | Khi muốn minh họa JSON/XML mà không lặp status/header |

Các snippet này lấy dữ liệu từ **request và response thực sự được test thực hiện**, có thể qua các bước tiền xử lý được cấu hình để định dạng, chuẩn hóa hoặc che dữ liệu.

Ví dụ `http-request.adoc` có thể hiển thị:

```http
GET /api/products/7?locale=vi HTTP/1.1
Accept: application/json
```

Trong khi `response-body.adoc` chỉ hiển thị body:

```json
{
  "id": 7,
  "name": "Sổ tay",
  "price": 45000
}
```

Chúng không chứa toàn bộ giải thích nghiệp vụ của API. Giá tiền được biểu diễn theo đơn vị nào, có áp dụng thuế hay không, quyền nào được phép xem sản phẩm: các thông tin ấy vẫn phải do tác giả nêu rõ theo hợp đồng của hệ thống.

### 3.2. Snippet bảng mô tả theo descriptor

Nhóm này được tạo khi test khai báo các descriptor tương ứng:

| API mô tả trong test | Tên snippet thông dụng | Điều tài liệu hóa |
| --- | --- | --- |
| `pathParameters(...)` | `path-parameters.adoc` | Các biến trong path template |
| `queryParameters(...)` | `query-parameters.adoc` | Query parameter của request |
| `requestHeaders(...)` | `request-headers.adoc` | Các request header |
| `responseHeaders(...)` | `response-headers.adoc` | Các response header |
| `requestFields(...)` | `request-fields.adoc` | Field trong request payload |
| `responseFields(...)` | `response-fields.adoc` | Field trong response payload |
| `links(...)` | `links.adoc` | Các liên kết hypermedia nếu API sử dụng |

Ví dụ:

```java
pathParameters(
    parameterWithName("productId")
        .description("Mã sản phẩm cần tra cứu")
),
responseFields(
    fieldWithPath("id")
        .type(JsonFieldType.NUMBER)
        .description("Mã sản phẩm"),
    fieldWithPath("name")
        .type(JsonFieldType.STRING)
        .description("Tên hiển thị"),
    fieldWithPath("price")
        .type(JsonFieldType.NUMBER)
        .description("Giá theo đơn vị tiền tệ của API")
)
```

Kết quả dự kiến là bảng path parameter và bảng response field, lần lượt trong `path-parameters.adoc` và `response-fields.adoc`.

**Không phải mọi operation đều có mọi snippet**. Một `GET` không gửi JSON body thì không cần `request-fields.adoc`. Một `DELETE` trả `204 No Content` thường không có bảng response fields. Nếu test không khai báo `responseHeaders(...)` thì không nên giả định file `response-headers.adoc` đã được sinh.

## 4. Ví dụ trọn vẹn: tạo snippet từ MockMvc

Ta xây dựng một controller chỉ phục vụ ví dụ. Endpoint `GET /api/products/{productId}?locale=vi` trả về sản phẩm mẫu có mã `7`; sản phẩm khác trả `404`. Cách tổ chức thực tế có thể dùng service, repository và security, nhưng ở đây chỉ tập trung vào quá trình sinh snippet.

### 4.1. Controller trả dữ liệu có thể dự đoán

```java
@RestController
class ProductController {

    record ProductView(
        long id,
        String name,
        BigDecimal price,
        String locale
    ) {}

    @GetMapping(
        value = "/api/products/{productId}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<ProductView> findOne(
            @PathVariable long productId,
            @RequestParam(defaultValue = "vi") String locale) {

        if (productId != 7L) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok(
            new ProductView(
                7L,
                "Sổ tay",
                new BigDecimal("45000"),
                locale
            )
        );
    }
}
```

Ví dụ dùng Java `record` (Java 17+) và Spring MVC. Cần import tương ứng cho `BigDecimal`, `RestController`, `GetMapping`, `PathVariable`, `RequestParam`, `ResponseEntity` và `MediaType`. Trong dự án thật, nên dùng fixture riêng để phản ánh đúng dữ liệu nghiệp vụ và thiết lập test cho từng tình huống.

### 4.2. Test chứa cả assertion và cấu hình sinh snippet

```java
@ExtendWith(RestDocumentationExtension.class)
class ProductDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider provider) {
        mockMvc = MockMvcBuilders
            .standaloneSetup(new ProductController())
            .apply(documentationConfiguration(provider))
            .build();
    }

    @Test
    void getProduct_generatesSnippets() throws Exception {
        mockMvc.perform(
                get("/api/products/{productId}", 7L)
                    .queryParam("locale", "vi")
                    .accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.name").value("Sổ tay"))
            .andExpect(jsonPath("$.price").value(45000))
            .andDo(document("products-get-success",
                pathParameters(
                    parameterWithName("productId")
                        .description("Mã định danh sản phẩm")
                ),
                queryParameters(
                    parameterWithName("locale")
                        .description("Mã ngôn ngữ hiển thị")
                        .optional()
                ),
                requestHeaders(
                    headerWithName("Accept")
                        .description("Định dạng response client mong muốn")
                ),
                responseFields(
                    fieldWithPath("id")
                        .type(JsonFieldType.NUMBER)
                        .description("Mã sản phẩm"),
                    fieldWithPath("name")
                        .type(JsonFieldType.STRING)
                        .description("Tên sản phẩm"),
                    fieldWithPath("price")
                        .type(JsonFieldType.NUMBER)
                        .description("Giá sản phẩm"),
                    fieldWithPath("locale")
                        .type(JsonFieldType.STRING)
                        .description("Ngôn ngữ của response")
                )
            ));
    }
}
```

Để tài liệu hóa `{productId}`, ví dụ cần import `get` từ `org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get`. Request builder này lưu URI template để `pathParameters(...)` xác định tên biến. Các hàm `document` và `documentationConfiguration` đến từ `MockMvcRestDocumentation`, còn `fieldWithPath`, `parameterWithName` và `headerWithName` đến từ các nhóm API payload/request/header của Spring REST Docs.

Một nhóm static import tiêu biểu:

```java
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
```

Các import còn lại gồm `MockMvc`, `MockMvcBuilders`, `JsonFieldType`, `RestDocumentationContextProvider`, `RestDocumentationExtension` và annotation JUnit tương ứng. Dự án cần dependency Spring REST Docs và cấu hình thư mục snippet đúng với build tool đang dùng. Ví dụ dựa trên phong cách API Spring REST Docs 3.x.

### 4.3. Test sinh những file nào?

Khi chạy `getProduct_generatesSnippets`, Spring REST Docs thường ghi vào:

```text
build/generated-snippets/products-get-success/     (Gradle)
target/generated-snippets/products-get-success/    (Maven)
```

Nếu dùng tên thư mục Gradle trong ví dụ, kết quả có thể gồm:

```text
generated-snippets/
└── products-get-success/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── curl-request.adoc
    ├── httpie-request.adoc
    ├── request-body.adoc
    ├── response-body.adoc
    ├── path-parameters.adoc
    ├── query-parameters.adoc
    ├── request-headers.adoc
    └── response-fields.adoc
```

Sáu file ví dụ/body thường là nhóm snippet mặc định; bốn bảng cuối được yêu cầu bởi các descriptor trong `document(...)`. Với `GET` không có body, nội dung `request-body.adoc` có thể rỗng. Đường dẫn và tập file cụ thể phụ thuộc cấu hình output và bộ snippet mặc định của dự án.

**Tên `products-get-success` phải thống nhất giữa test và tài liệu.** Nếu đổi tên trong `document(...)` mà không sửa lệnh include, quá trình render có thể báo thiếu file hoặc lấy file cũ nếu output trước đó chưa được dọn.

## 5. Nhúng snippet vào trang Asciidoctor

Giả sử một file tài liệu nguồn `src/docs/asciidoc/products.adoc` (tên đường dẫn tùy dự án) cần trình bày operation thành công. Có thể viết:

```asciidoc
[[products-get]]
=== Tra cứu sản phẩm

Gọi endpoint này để đọc thông tin của một sản phẩm.
productId là mã định danh của sản phẩm.
Nếu không tồn tại, API trả về HTTP 404.

==== Request mẫu

include::{snippets}/products-get-success/http-request.adoc[]

==== Biến trong đường dẫn

include::{snippets}/products-get-success/path-parameters.adoc[]

==== Tham số truy vấn

include::{snippets}/products-get-success/query-parameters.adoc[]

==== Header của request

include::{snippets}/products-get-success/request-headers.adoc[]

==== Response thành công

include::{snippets}/products-get-success/http-response.adoc[]

==== Các trường JSON của response

include::{snippets}/products-get-success/response-fields.adoc[]
```

Với Asciidoctor, `include::...[]` là directive đưa nội dung file con vào file nguồn **tại vị trí render**. Trong `include::{snippets}/products-get-success/http-request.adoc[]`:

- `{snippets}` là attribute trỏ tới thư mục chứa snippet, được build cấu hình.
- `products-get-success` là identifier của operation từ `document(...)`.
- `http-request.adoc` là mảnh nội dung muốn hiển thị.

Nếu file không tồn tại hoặc attribute bị cấu hình sai, quá trình biên soạn có thể báo lỗi/hiển thị cảnh báo tùy cấu hình. CI nên coi include không hợp lệ là một sự cố cần xử lý, không công bố một trang chứa directive chưa được giải quyết.

### 5.1. Vì sao không sao chép snippet vào Markdown/AsciiDoc bằng tay?

Giả sử JSON response đổi field `price` thành `unitPrice`. Nếu bạn đã copy đoạn JSON vào trang tài liệu, copy đó không tự đổi theo code. Nếu trang dùng include tới `http-response.adoc` được tạo lại sau test, ví dụ có thể cập nhật theo response hiện tại; nếu `responseFields(...)` vẫn mô tả `price`, test tài liệu hóa nghiêm ngặt sẽ phát hiện thiếu đồng bộ.

Vì vậy, include duy trì **một nguồn tạo ví dụ**, thay cho nhiều bản sao tĩnh. Tuy nhiên, tác giả vẫn phải sửa đoạn giải thích nghiệp vụ về ý nghĩa field và quy tắc dùng API khi hợp đồng thay đổi; snippet không tự viết được phần này.

### 5.2. Chèn theo mục đích đọc, không chèn tất cả mảnh có sẵn

Một trang có thể chọn chèn `http-request.adoc` hoặc `curl-request.adoc`, tùy đối tượng sử dụng. Không nhất thiết hiển thị cả HTTP raw, cURL, HTTPie và request body giống nhau trong cùng một đoạn nếu chúng chỉ lặp thông tin.

Một cách tổ chức rõ ràng:

| Phần tài liệu | Snippet đề xuất | Lời giải thích nên bổ sung |
| --- | --- | --- |
| Giới thiệu endpoint | Không bắt buộc | Mục đích, quyền truy cập, tiền điều kiện |
| Ví dụ cách gọi | `http-request.adoc` hoặc `curl-request.adoc` | Khi nào truyền tham số, giá trị mặc định |
| Mô tả đầu vào | `path-parameters.adoc`, `query-parameters.adoc`, `request-fields.adoc` khi có | Ý nghĩa, ràng buộc và ví dụ hợp lệ |
| Ví dụ kết quả | `http-response.adoc` | Điều kiện trả status và xử lý lỗi |
| Mô tả đầu ra | `response-fields.adoc`, `response-headers.adoc` khi có | Giá trị enum, đơn vị, định dạng ngày giờ |
| Tình huống lỗi | Snippet của operation lỗi tương ứng | Điều kiện `400`, `404`, `409` và cách khắc phục |

Đây là lựa chọn trình bày, không phải yêu cầu cố định của thư viện. Điều quan trọng là người đọc tìm được thông tin cần thiết mà không phải ghép ý nghĩa từ nhiều ví dụ rời rạc.

## 6. Dùng snippet của nhiều operation trong cùng một trang

Một endpoint có thể trả nhiều status. Hãy tạo test riêng cho tình huống quan trọng, chẳng hạn:

```java
@Test
void getProduct_notFound() throws Exception {
    mockMvc.perform(
            get("/api/products/{productId}", 999L)
                .accept(MediaType.APPLICATION_JSON)
        )
        .andExpect(status().isNotFound())
        .andDo(document("products-get-not-found",
            pathParameters(
                parameterWithName("productId")
                    .description("Mã định danh sản phẩm")
            )
        ));
}
```

Với controller ví dụ, response `404` không có body nên đoạn này không khai báo `responseFields(...)`. Trang AsciiDoc có thể thêm:

```asciidoc
==== Khi không tìm thấy sản phẩm (HTTP 404)

Mã sản phẩm không tồn tại trong dữ liệu của hệ thống.

include::{snippets}/products-get-not-found/http-request.adoc[]

include::{snippets}/products-get-not-found/http-response.adoc[]
```

Nếu hệ thống thật có body lỗi JSON như `{"code":"PRODUCT_NOT_FOUND","message":"..."}`, test phải thực sự tạo và kiểm tra body đó rồi mô tả các field lỗi tương ứng. Không được chèn snippet response thành công vào mục lỗi hoặc tự tưởng tượng response lỗi mà test chưa chứng minh.

### 6.1. Cẩn thận với việc “tái sử dụng” snippet

Có hai kiểu tái sử dụng khác nhau:

1. **Tái sử dụng chính snippet đã sinh**: nhiều trang có thể cùng include `products-get-success/response-fields.adoc` khi đang nhắc tới **cùng một operation và cùng một schema**.
2. **Tái sử dụng bộ descriptor hoặc cách trình bày**: nhiều endpoint có chung lỗi chuẩn hoặc header chung có thể dùng helper test, mẫu tài liệu hoặc tài liệu quy tắc chung.

Đừng lấy bảng response field của `GET /api/products/7` đặt vào phần `POST /api/orders` chỉ vì cả hai có field `id`: ý nghĩa và schema là khác nhau. Snippet có liên hệ với **operation nguồn**. Khi muốn làm bảng mô tả chung, cần xác định hợp đồng thực sự chung và kiểm tra nó ở những endpoint thích hợp.

## 7. Các đặc tính quan trọng của snippet

### 7.1. Snippet có đường dẫn ổn định, nội dung có thể thay đổi

`products-get-success/response-fields.adoc` là một vị trí có thể tham chiếu ổn định, nhưng nội dung file sẽ được ghi lại khi test chạy. Đây là lợi thế: tài liệu bám theo hành vi test hiện tại.

Từ đó có hai yêu cầu:

- Đặt tên operation có ý nghĩa, dễ theo dõi và không xung đột giữa các test.
- Không dùng cùng identifier cho nhiều test sinh nội dung khác nhau; trong chạy song song, các test có thể ghi đè output lẫn nhau.

Nếu cần hiển thị `200` và `404`, đặt tên `products-get-success` và `products-get-not-found` sẽ rõ hơn dùng chung `products-get`.

### 7.2. Snippet phản ánh dữ liệu sau tiền xử lý

Spring REST Docs có thể áp dụng preprocessors khi sinh snippet để làm đẹp JSON, chuẩn hóa URI, loại header không cần hiển thị hoặc thay dữ liệu nhạy cảm bằng giá trị giả. Ví dụ:

```java
.andDo(document("products-get-success",
    preprocessRequest(prettyPrint()),
    preprocessResponse(prettyPrint()),
    responseFields(
        fieldWithPath("id").description("Mã sản phẩm"),
        fieldWithPath("name").description("Tên sản phẩm"),
        fieldWithPath("price").description("Giá sản phẩm"),
        fieldWithPath("locale").description("Ngôn ngữ")
    )
));
```

Đây là **đoạn minh họa cho cách cấu hình khác của `document(...)`**, không phải bản thay thế nguyên vẹn cho ví dụ test ở trên vì đã lược bớt descriptor đầu vào. Các hàm `preprocessRequest`, `preprocessResponse` và `prettyPrint` thuộc `org.springframework.restdocs.operation.preprocess.Preprocessors`.

Khi render tài liệu công khai, phải dùng dữ liệu fixture an toàn. Tránh đưa token thật, cookie, thông tin cá nhân, hostname nội bộ hoặc credential vào snippet. Đồng thời, preprocessor chỉ thay đổi cách trình bày; test cần giữ assertion kiểm tra hành vi thực để tránh che lấp sai khác của API.

### 7.3. Snippet là file AsciiDoc theo cấu hình thông dụng

Phần lớn ví dụ Spring REST Docs dùng template **Asciidoctor**, nên output có đuôi `.adoc`. Nếu dự án dùng Markdown, không nên đổi tên `response-fields.adoc` thành `response-fields.md` rồi chèn trực tiếp: cú pháp bảng, block source và directive có thể không tương thích.

Các hướng triển khai thường là:

- Dùng Asciidoctor làm nguồn tài liệu và chuyển đổi sang HTML/PDF hoặc một định dạng trung gian.
- Cấu hình template snippet phù hợp với định dạng đầu ra mong muốn và có bước chèn vào Markdown theo công cụ đang sử dụng.
- Dùng một pipeline sinh Markdown từ dữ liệu/snippet đã kiểm chứng, có bước kiểm tra đầu ra.

**Markdown không có cú pháp include chuẩn thống nhất.** Cú pháp `include::{snippets}/...[]` là của Asciidoctor; muốn dùng trong Markdown phải có trình biên dịch hoặc plugin hỗ trợ rõ ràng.

### 7.4. Snippet không mô tả được mọi quy tắc nghiệp vụ

Một bảng `response-fields` có thể cho biết `price` là kiểu number và có mô tả “Giá sản phẩm”. Nhưng một request mẫu không chứng minh được mọi quy tắc làm tròn, đơn vị tiền tệ, giá sau thuế, quyền xem giá hay hiệu lực của giá theo thời gian. Muốn tuyên bố các quy tắc đó, cần tài liệu nghiệp vụ chính xác và test tương ứng nếu chúng là hợp đồng công khai.

## 8. Tổ chức tài liệu lớn bằng phần và liên kết

Khi số endpoint tăng, nên sắp xếp tài liệu theo resource hoặc nhóm nghiệp vụ. Ví dụ:

```text
src/docs/asciidoc/
├── index.adoc              (điểm vào)
├── introduction.adoc       (base URL, xác thực, quy ước)
├── products.adoc           (tài nguyên sản phẩm)
├── orders.adoc             (tài nguyên đơn hàng)
└── errors.adoc             (định dạng lỗi chung)

build/generated-snippets/
├── products-get-success/
├── products-get-not-found/
├── products-create-success/
├── orders-get-success/
└── orders-create-invalid/
```

File `index.adoc` có thể ghép các phần thành tài liệu lớn:

```asciidoc
= API Reference
:toc: left
:toclevels: 3

include::introduction.adoc[]

include::products.adoc[]

include::orders.adoc[]

include::errors.adoc[]
```

Ở đây có **hai mức include** khác nhau:

- `include::products.adoc[]` đưa một **trang hoặc phần nội dung** vào tài liệu tổng.
- `include::{snippets}/products-get-success/http-response.adoc[]` đưa **snippet được sinh từ test** vào bên trong trang đó.

Tổ chức nhiều tầng giúp tác giả làm chủ lời giải thích tổng thể, còn các mẫu request/response và bảng field được quản lý từ test. Tránh cho một trang có hàng trăm include không phân nhóm; hãy đặt section và tiêu đề phù hợp để người đọc hiểu từng mảnh tài liệu đang mô tả tình huống nào.

## 9. Build và CI đảm bảo snippet có nguồn rõ ràng

Vì snippet là output của test, bước biên soạn tài liệu **phải chạy sau bước tạo snippet**. Với một dự án Gradle có plugin Asciidoctor đã được cấu hình phù hợp, phần kết nối có thể theo hướng sau (Groovy DSL, mang tính minh họa):

```groovy
def snippetsDir = file("build/generated-snippets")

tasks.named("test") {
    outputs.dir snippetsDir
}

tasks.named("asciidoctor") {
    dependsOn tasks.named("test")
    inputs.dir snippetsDir
    attributes "snippets": snippetsDir
}
```

Đoạn cấu hình giả định project đã có task `test` và `asciidoctor`, dependency Spring REST Docs và plugin phù hợp. Cú pháp của phần cấu hình task có thể cần điều chỉnh theo phiên bản Gradle/Asciidoctor plugin. Với Maven, ý tưởng tương tự: test tạo snippet trong `target/generated-snippets`, plugin biên soạn tài liệu được nối đúng pha và nhận đường dẫn snippet làm attribute.

Luồng build mong muốn:

```text
Source code + test + descriptor + trang .adoc
                  │
                  ▼
              Chạy HTTP test
                  │
             ┌────┴────┐
             │         │
           FAIL       PASS
             │         │
        Dừng build   Sinh snippets
                       │
                       ▼
             Render tài liệu với include
                       │
                ┌──────┴──────┐
                │             │
           Thiếu file        PASS
                │             │
           Dừng build     HTML/PDF/site
```

Trong CI, chạy từ output sạch hoặc bảo đảm output cũ được loại bỏ hợp lý trước khi kiểm chứng. Nếu test tài liệu hóa bị skip, snippet cũ có thể khiến trang vẫn biên soạn được, tạo cảm giác sai rằng tài liệu đã được xác nhận bởi mã hiện tại.

### 9.1. Thay đổi API được phản ánh ra sao?

Giả sử response của sản phẩm đổi từ:

```json
{"id":7,"name":"Sổ tay","price":45000,"locale":"vi"}
```

sang:

```json
{"id":7,"name":"Sổ tay","unitPrice":45000,"locale":"vi"}
```

Trong test đang dùng `responseFields(...)` với `price` và cơ chế kiểm tra nghiêm ngặt, tài liệu hóa sẽ phát hiện schema không còn khớp. Người phát triển cần xác minh đây là thay đổi hợp đồng có chủ đích, sửa descriptor và assertion thích hợp, sau đó sinh lại snippet. Trang AsciiDoc dùng include sẽ nhận bảng trường và mẫu response mới sau khi test pass.

Ngược lại, nếu trang chỉ chứa JSON chép tay, việc đổi API không tự tạo ra kết nối kiểm tra này. Đó là lợi ích thiết thực của việc nhúng snippet sinh từ test.

### 9.2. Kiểm tra chất lượng output

Khi một trang Asciidoctor hoặc Markdown render xong, nên xác minh:

1. Không còn directive include chưa được giải quyết.
2. Tất cả ví dụ hiện đúng operation và đúng HTTP status.
3. Bảng field có đủ các trường thuộc hợp đồng và giải thích rõ ý nghĩa.
4. Link nội bộ, mục lục và tiêu đề không gây nhầm lẫn.
5. Không có dữ liệu bí mật hoặc dữ liệu môi trường nội bộ trong snippet công khai.

Những bước này bổ sung cho test. Test bảo vệ tính đúng đắn của hành vi được kiểm tra; kiểm tra output bảo vệ việc **lắp ráp và trình bày** các mảnh tài liệu.

## 10. Lỗi thường gặp khi làm việc với snippet

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `include` báo không thấy `response-fields.adoc` | Test chưa khai báo `responseFields(...)` hoặc không chạy | Bổ sung descriptor phù hợp và chạy đúng task test |
| Thư mục `products-get-success` không tồn tại | Tên trong `document(...)` khác với tên trong trang hoặc test bị skip | Đối chiếu identifier và log chạy test |
| Trang vẫn hiển thị response cũ | Snippet tồn dư hoặc task render không phụ thuộc test | Chạy build từ trạng thái sạch và nối task đúng thứ tự |
| Bảng tham số path không sinh được | Builder không lưu URI template hoặc descriptor sai tên | Dùng `RestDocumentationRequestBuilders` với `{productId}` |
| Trùng nội dung khi nhúng | Chèn đồng thời nhiều mảnh cùng lặp phần HTTP/body | Chọn snippet theo mục đích của từng section |
| `response-fields.adoc` không khớp JSON | Test thay schema nhưng descriptor chưa sửa | Xác nhận hợp đồng rồi cập nhật test, descriptor và nội dung diễn giải |
| Hai test ghi cùng một thư mục snippet | Dùng trùng identifier cho các response khác nhau | Đặt định danh riêng theo tình huống |
| Markdown hiển thị nguyên cú pháp Asciidoctor | Pipeline Markdown không hỗ trợ include/adoc | Chuyển đổi hoặc cấu hình công cụ/template phù hợp |
| Ví dụ xuất hiện token hay hostname nhạy cảm | Operation test chứa dữ liệu không nên công bố | Dùng fixture giả, preprocessor hoặc bước loại dữ liệu an toàn |
| Tài liệu chỉ gồm bảng và code block | Chưa có phần mô tả nghiệp vụ | Bổ sung điều kiện sử dụng, ý nghĩa, lỗi và quy tắc chung |

## 11. Bài thực hành: từ các mảnh nhỏ đến trang API đầy đủ

Hãy tài liệu hóa endpoint `GET /api/products/{productId}` với hai tình huống: sản phẩm tồn tại (`200`) và không tìm thấy (`404`).

**Yêu cầu thực hiện:**

1. Viết hai test MockMvc, dùng identifier `products-get-success` và `products-get-not-found`.
2. Ở test `200`, mô tả `productId`, `locale`, header `Accept` và các response field; xác nhận status và giá trị nghiệp vụ.
3. Ở test `404`, xác nhận status và chỉ mô tả những thành phần thật sự xuất hiện trong response.
4. Chạy test và kiểm tra các file `http-request.adoc`, `http-response.adoc`, `path-parameters.adoc` và `response-fields.adoc` trong thư mục operation phù hợp.
5. Tạo một trang AsciiDoc có phần giới thiệu, request thành công, bảng tham số, response thành công và phần lỗi `404`. Chỉ include file thực sự được sinh.
6. Biên soạn trang, sau đó thử đổi tên `products-get-success` trong test mà chưa sửa trang. Quan sát lỗi thiếu include; khôi phục tên và chạy lại.
7. Thử thêm field JSON mới vào response nhưng chưa mô tả; nếu đang dùng response field documentation nghiêm ngặt, test cần phát hiện thay đổi. Cập nhật descriptor đúng hợp đồng rồi sinh lại tài liệu.

**Tiêu chí đạt:** mỗi snippet trên trang có một nguồn test cụ thể; phần giải thích giúp người đọc hiểu khi nào dùng endpoint; tài liệu được tái tạo trên build sạch và phát hiện thiếu file hoặc lệch schema trong phạm vi được kiểm tra.

## 12. Ghi nhớ

- **Snippet** là mảnh nội dung tài liệu được tạo từ **operation HTTP trong test** và có thể chèn vào trang Asciidoctor hoặc quy trình biên soạn Markdown phù hợp.
- **Một operation có nhiều snippet**; mỗi mảnh thể hiện một phần của request/response hoặc bảng mô tả field, tham số và header.
- **Trang tài liệu lớn** ghép các snippet với phần diễn giải nghiệp vụ, tổ chức theo endpoint và tình huống thành công/lỗi.
- **Identifier ổn định, descriptor đầy đủ, build đúng thứ tự và CI từ output sạch** giúp tránh nhầm snippet và giữ tài liệu nhất quán với phần API đã được test.
- **Snippet là nguồn ví dụ có thể kiểm chứng, không thay thế** thông tin về quyền truy cập, quy tắc nghiệp vụ và phạm vi test mà người viết tài liệu phải làm rõ.
