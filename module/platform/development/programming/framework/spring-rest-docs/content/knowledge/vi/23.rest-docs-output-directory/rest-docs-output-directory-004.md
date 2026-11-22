# Parameterized output directories

## 1. Mục tiêu của output directory có tham số

Trong Spring REST Docs, mỗi lần gọi `document(...)` có thể sinh nhiều snippet như HTTP request, HTTP response, headers, parameters và payload. Nếu nhiều test dùng cùng một document identifier, chúng có thể ghi vào cùng thư mục và tạo xung đột hoặc làm kết quả khó truy nguyên.

**Parameterized output directory** cho phép đưa thông tin của test hiện tại vào document identifier để Spring REST Docs tự tạo đường dẫn riêng. Thay vì tự nối chuỗi class/test trong từng lời gọi, ta dùng placeholder như `{class-name}`, `{method-name}` và `{step}`.

Ví dụ:

~~~java
mockMvc.perform(get("/orders/42"))
    .andDo(document("{class-name}/{method-name}"));
~~~

Với test class `OrderDocumentationTest` và test method `getOrderDetails`, output sẽ nằm dưới:

~~~text
order-documentation-test/
└── get-order-details/
    ├── http-request.adoc
    ├── http-response.adoc
    └── ...
~~~

Parameterized path đặc biệt hữu ích khi cấu hình documentation một lần trong setup và tái sử dụng cho nhiều test method. Mỗi test có thư mục riêng mà không cần viết lại identifier cố định ở từng chỗ.

Trong module **SPRING_REST_DOCS**, test HTTP bằng MockMvc, WebTestClient hoặc REST Assured sinh snippet để biên soạn thành Asciidoctor/Markdown và đưa vào build/CI. Đặt tên đường dẫn có quy tắc giúp snippet được phân tách theo class, method và lần gọi HTTP; nhờ đó tài liệu không vô tình dùng chung output của các test khác nhau.

## 2. Các placeholder được hỗ trợ

Spring REST Docs hỗ trợ các placeholder sau trong document identifier:

| Placeholder | Ý nghĩa | Ví dụ kết quả |
| --- | --- | --- |
| `{methodName}` | Tên test method nguyên dạng | `getOrderDetails` |
| `{method-name}` | Tên method theo kebab-case | `get-order-details` |
| `{method_name}` | Tên method theo snake_case | `get_order_details` |
| `{ClassName}` | Tên đơn giản của test class, giữ nguyên | `OrderDocumentationTest` |
| `{class-name}` | Tên class theo kebab-case | `order-documentation-test` |
| `{class_name}` | Tên class theo snake_case | `order_documentation_test` |
| `{step}` | Số thứ tự lần gọi service trong test hiện tại | `1`, `2`, `3` |

### 2.1. Chọn kiểu chữ nhất quán

Kebab-case phù hợp với tên thư mục và đường dẫn include:

~~~java
document("{class-name}/{method-name}");
~~~

Snake-case cũng hợp lệ nếu nhóm đang dùng quy ước đó:

~~~java
document("{class_name}/{method_name}");
~~~

Tên nguyên dạng hữu ích khi muốn bám sát tên Java, nhưng có thể chứa chữ hoa và ít đồng nhất hơn khi đọc cây thư mục. Chọn một kiểu cho toàn bộ module để người biên soạn tài liệu dễ dự đoán đường dẫn.

### 2.2. Placeholder không phải biến Maven/Gradle

Các placeholder trên được Spring REST Docs phân giải trong document identifier khi test thực thi. Chúng không phải thuộc tính của Asciidoctor, biến môi trường hay property trong POM/build.gradle. Ví dụ:

~~~java
document("{class-name}/{method-name}");
~~~

được phân giải bởi REST Docs thành đường dẫn snippet; còn:

~~~adoc
include::{snippets}/order-documentation-test/get-order-details/http-request.adoc[]
~~~

là include được Asciidoctor xử lý khi render tài liệu. Hai giai đoạn có liên quan nhưng dùng cú pháp và thời điểm xử lý khác nhau.

## 3. Kết hợp class và method để tách output

Giả sử có test class:

~~~java
class OrderDocumentationTest {

    @Test
    void getOrderDetails() {
        // Gửi request GET /orders/42
    }

    @Test
    void createOrder() {
        // Gửi request POST /orders
    }
}
~~~

Nếu mỗi thao tác ghi bằng:

~~~java
document("{class-name}/{method-name}");
~~~

hai bộ snippet được ghi vào các thư mục riêng:

~~~text
build/generated-snippets/
└── order-documentation-test/
    ├── get-order-details/
    │   ├── http-request.adoc
    │   └── http-response.adoc
    └── create-order/
        ├── http-request.adoc
        └── http-response.adoc
~~~

Cấu trúc này có ba lợi ích:

- Nhìn đường dẫn biết test class và hành vi API nào tạo snippet.
- Các test method không ghi đè snippet cùng tên của nhau.
- Khi đổi hoặc xóa một test, có thể xác định chính xác nhóm snippet cần cập nhật.

Nếu nhiều test class cùng kiểm tra một endpoint nhưng khác fixture, giữ cả class lẫn method trong identifier. Chỉ dùng `{method-name}` khi bảo đảm tên method duy nhất trong toàn bộ nhóm test ghi vào cùng output root.

## 4. Tái sử dụng cấu hình với MockMvc

### 4.1. Cấu hình một lần trong setup

Một ứng dụng phổ biến là cấu hình MockMvc trong `@BeforeEach` và dùng `alwaysDo(...)` để ghi snippet sau mỗi request:

~~~java
@ExtendWith(RestDocumentationExtension.class)
@WebMvcTest(OrderController.class)
class OrderDocumentationTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
            .apply(documentationConfiguration(documentation))
            .alwaysDo(document("{class-name}/{method-name}/{step}"))
            .build();
    }

    @Test
    void getOrderDetails() throws Exception {
        this.mockMvc.perform(get("/orders/42"))
            .andExpect(status().isOk());
    }

    @Test
    void createOrder() throws Exception {
        this.mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"product\":\"book\"}"))
            .andExpect(status().isCreated());
    }
}
~~~

Giả sử test đầu tiên chỉ gửi một request, đường dẫn có dạng:

~~~text
order-documentation-test/get-order-details/1/
~~~

Test thứ hai có output riêng:

~~~text
order-documentation-test/create-order/1/
~~~

`alwaysDo(...)` gắn result handler vào mọi request được thực hiện qua MockMvc instance. Vì vậy không cần gọi `andDo(document(...))` trong từng test method.

### 4.2. Khi một test gửi nhiều request

Placeholder `{step}` phân biệt lần gọi service trong test hiện tại. Ví dụ:

~~~java
@Test
void createThenReadOrder() throws Exception {
    mockMvc.perform(post("/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"product\":\"book\"}"))
        .andExpect(status().isCreated());

    mockMvc.perform(get("/orders/42"))
        .andExpect(status().isOk());
}
~~~

Với identifier `{class-name}/{method-name}/{step}`, các snippet được tách theo thứ tự:

~~~text
order-documentation-test/
└── create-then-read-order/
    ├── 1/
    │   ├── http-request.adoc
    │   └── http-response.adoc
    └── 2/
        ├── http-request.adoc
        └── http-response.adoc
~~~

Điều này đặc biệt hữu ích khi tài liệu hóa một workflow gồm nhiều request như tạo tài nguyên, truy vấn tài nguyên vừa tạo và cập nhật trạng thái.

### 4.3. Chỉ ghi snippet cho request phù hợp

Vì `alwaysDo(...)` chạy cho mọi request đi qua MockMvc instance, hãy cân nhắc có nên ghi tất cả request trong test hay chỉ một số request. Nếu test có request phụ trợ như đăng nhập, khởi tạo fixture hoặc gọi endpoint không thuộc tài liệu công khai, có thể dùng cấu hình document riêng tại từng request thay vì áp dụng handler toàn cục.

Khi mỗi test chỉ có một request cần ghi, dùng `{class-name}/{method-name}` là đủ. Thêm `{step}` khi có nhiều lần gọi cần có snippet riêng.

## 5. Tái sử dụng cấu hình với REST Assured

REST Assured dùng filter để quan sát request/response và sinh snippet. Có thể đặt document identifier có tham số trong request specification dùng chung:

~~~java
@BeforeEach
void setUp(RestDocumentationContextProvider documentation) {
    this.specification = new RequestSpecBuilder()
        .addFilter(documentationConfiguration(documentation))
        .addFilter(document("{class-name}/{method-name}/{step}"))
        .build();
}
~~~

Trong mỗi test:

~~~java
given(this.specification)
    .when()
    .get("/orders/42")
    .then()
    .statusCode(200);
~~~

Filter document được cài một lần trong specification. Placeholder được phân giải theo test class, test method và số thứ tự lần gọi service hiện tại. Nếu test gửi nhiều request bằng cùng specification, `{step}` tạo thư mục riêng cho từng lần.

Để REST Assured ghi snippet đúng output root, filter `documentationConfiguration(documentation)` phải dùng context provider của REST Docs. Đừng bỏ filter cấu hình context rồi chỉ thêm document filter; document filter cần context để biết output directory và test metadata.

## 6. WebTestClient và khác biệt về cách áp dụng

WebTestClient dùng filter của Spring REST Docs để ghi tài liệu. Ví dụ một request:

~~~java
webTestClient
    .mutateWith(documentationConfiguration(documentation))
    .get()
    .uri("/orders/42")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("{class-name}/{method-name}"));
~~~

Với WebTestClient, document operation thường được gắn vào bước kiểm tra response bằng `consumeWith(document(...))`. Vì thế có thể dùng placeholder trong identifier của lần gọi đó. Nếu test phát nhiều request, chọn identifier có `{step}` hoặc tên scenario rõ ràng để các bộ snippet không trùng nhau.

API builder và filter cụ thể có thể khác theo Spring Framework/Spring REST Docs version. Hãy kiểm tra cách tích hợp WebTestClient trong phiên bản dependency của dự án trước khi dùng một cấu hình tự động chung. Nguyên tắc vẫn giữ nguyên: mỗi lần document cần một identifier được phân giải và context cung cấp output root.

## 7. Quy tắc chọn identifier thực tế

| Tình huống | Identifier gợi ý | Lý do |
| --- | --- | --- |
| Mỗi test method sinh một request | `{class-name}/{method-name}` | Tách theo class và method |
| Một test có nhiều request cần ghi | `{class-name}/{method-name}/{step}` | Tách từng lần gọi |
| Tên class đã nằm trong package/module path | `{method-name}/{step}` | Rút gọn nhưng vẫn tách test method |
| Test class có method name trùng với class khác | `{class-name}/{method-name}` | Tránh collision giữa class |
| Cần đường dẫn dễ đọc bằng mắt | Kebab-case | Đồng nhất với URL/path |
| Muốn bám sát tên Java | `{ClassName}/{methodName}` | Giữ nguyên chữ hoa/thường |

Tránh identifier chỉ có `{step}` khi nhiều test class hoặc method dùng chung output root. Bộ đếm step được khởi tạo trong phạm vi test hiện tại; giá trị `1` có thể lặp lại giữa các test khác nhau. Luôn thêm method hoặc class để tạo namespace khi cần tách output.

Không nên đưa dữ liệu test động như order ID, UUID, timestamp hoặc email vào đường dẫn. Những giá trị này tạo cây thư mục khó đoán, gây khó include và có thể để lộ dữ liệu không cần thiết. Placeholder class/method/step ổn định hơn vì dựa trên cấu trúc test.

## 8. Tổ chức include trong Asciidoctor

Giả sử document identifier là `{class-name}/{method-name}/{step}`. Sau khi chạy test, snippet nằm dưới:

~~~text
build/generated-snippets/
└── order-documentation-test/
    └── create-then-read-order/
        ├── 1/
        │   ├── http-request.adoc
        │   └── http-response.adoc
        └── 2/
            ├── http-request.adoc
            └── http-response.adoc
~~~

Trang Asciidoctor có thể include:

~~~adoc
== Tạo đơn hàng

=== Request tạo đơn
include::{snippets}/order-documentation-test/create-then-read-order/1/http-request.adoc[]

=== Response tạo đơn
include::{snippets}/order-documentation-test/create-then-read-order/1/http-response.adoc[]

=== Request đọc đơn vừa tạo
include::{snippets}/order-documentation-test/create-then-read-order/2/http-request.adoc[]

=== Response đọc đơn
include::{snippets}/order-documentation-test/create-then-read-order/2/http-response.adoc[]
~~~

Asciidoctor không tự hiểu placeholder JUnit như `{class-name}`. Placeholder này đã được REST Docs phân giải lúc test chạy; trong tài liệu nguồn phải include đường dẫn kết quả thực tế, hoặc dùng attribute/partial riêng của quy trình build nếu nhóm muốn trừu tượng hóa đường dẫn.

Nếu đổi tên test class hoặc method, các thư mục sinh ra sẽ đổi theo. Cập nhật include tương ứng; trong pull request có thể kiểm tra diff giữa snippet mới và các đường dẫn include.

## 9. Tránh ghi đè và quản lý output cũ

Parameterized identifier giúp tách các test, nhưng không tự dọn snippet cũ. Khi đổi tên test method hoặc xóa test, thư mục output được tạo ở build trước có thể vẫn tồn tại cho đến khi build directory được làm sạch.

Thực hành tốt:

1. Dùng class và method trong identifier nếu test thuộc nhiều class.
2. Dùng step chỉ khi test có nhiều request cần document.
3. Giữ tên method ổn định nếu Asciidoctor include trực tiếp vào thư mục đó.
4. Chạy clean build khi đổi convention hoặc refactor tên test.
5. Không sửa tay snippet do test sinh.

Với Gradle:

~~~bash
./gradlew clean test asciidoctor
~~~

Với Maven:

~~~bash
mvn clean verify
~~~

Trong CI, test cần chạy trước bước render tài liệu. Khi snippet không xuất hiện, kiểm tra test đã đi qua document handler/filter hay chưa, sau đó kiểm tra output root và identifier đã được phân giải.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Tất cả test ghi cùng một thư mục | Dùng identifier cố định | Dùng `{class-name}/{method-name}` |
| Hai class có cùng method name ghi đè nhau | Chỉ dùng `{method-name}` | Thêm `{class-name}` |
| Nhiều request trong test ghi cùng snippet | Thiếu `{step}` khi dùng một handler chung | Thêm `{step}` vào identifier |
| Thư mục step bắt đầu lại ở test khác | Step count có phạm vi test hiện tại | Kết hợp step với class và method |
| Asciidoctor include không tìm thấy sau khi đổi tên test | Đường dẫn snippet đã đổi theo placeholder | Cập nhật include theo output mới |
| Snippet cũ còn trong build | Đã xóa/đổi test nhưng chưa clean | Chạy clean build |
| REST Assured filter không biết output root | Thiếu documentation configuration filter/context | Thêm filter documentationConfiguration dùng cùng provider |
| MockMvc ghi snippet ngoài ý muốn cho request phụ | alwaysDo áp dụng mọi request | Chỉ gắn document tại request cần tài liệu hoặc tách test |

## 11. Bài tập thực hành

Tạo lớp `ProductDocumentationTest` có ba test:

- `getProductDetails`: gọi GET một lần.
- `createProduct`: gọi POST một lần.
- `createThenReadProduct`: gọi POST rồi GET trong cùng test.

Thực hiện:

1. Cấu hình MockMvc với `alwaysDo(document("{class-name}/{method-name}/{step}"))`.
2. Chạy test và quan sát cấu trúc thư mục cho từng class/method/step.
3. Xác nhận hai test một request đều sinh thư mục step `1` nhưng nằm trong method directory khác nhau.
4. Xác nhận test workflow sinh hai thư mục `1` và `2`.
5. Include các snippet request/response của workflow trong Asciidoctor.
6. Đổi tên test method, chạy `clean test asciidoctor` và cập nhật include theo đường dẫn mới.
7. Thử identifier chỉ có `{step}` trong một test class khác để quan sát nguy cơ collision, rồi sửa lại theo quy tắc class/method/step.

**Tiêu chí hoàn thành:** document identifier tạo output path ổn định và dễ đoán; các test method/class không ghi đè nhau; các request trong cùng test được tách bằng step; Asciidoctor include đúng các snippet mới nhất.

## Tài liệu tham khảo

- [Spring REST Docs — Using Parameterized Output Directories](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — RestDocumentationContext API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/RestDocumentationContext.html)
- [Spring REST Docs — MockMvc API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/mockmvc/MockMvcRestDocumentation.html)
