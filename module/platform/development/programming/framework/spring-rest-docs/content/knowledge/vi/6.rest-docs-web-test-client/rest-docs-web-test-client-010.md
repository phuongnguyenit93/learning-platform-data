# Đọc lỗi khi filter tài liệu chưa được gắn trong WebTestClient

## 1. Vai trò của documentation filter

**Spring REST Docs** tạo tài liệu REST API từ các bài kiểm thử HTTP bằng **WebTestClient**, MockMvc hoặc REST Assured. Test thực thi exchange qua WebTestClient, kiểm tra status/body rồi dùng `document(...)` để sinh snippet cho request, response, payload, header hoặc tham số.

Để REST Docs nhận biết và xử lý exchange của WebTestClient, builder cần được gắn cấu hình bằng **documentation filter**:

```java
.filter(documentationConfiguration(restDocumentation))
```

Trong đó:

- `documentationConfiguration(restDocumentation)` tạo cấu hình/filter dành cho WebTestClient của Spring REST Docs.
- `filter(...)` đăng ký cấu hình đó vào chuỗi `ExchangeFilterFunction` của WebTestClient.
- `document("operation-id")` được dùng sau exchange, thường trong `consumeWith(...)`, để sinh snippet của operation.

Nếu thiếu bước đăng ký filter, lời gọi `document(...)` không có đầy đủ ngữ cảnh tích hợp mà cấu hình WebTestClient của REST Docs cung cấp. Khi đó việc document có thể thất bại hoặc không sinh ra bộ snippet như mong đợi, tùy cách test được cấu hình và phiên bản thư viện. Cần kiểm tra chính builder tạo ra client đang được test sử dụng.

Bài này hướng dẫn chẩn đoán lỗi **filter tài liệu chưa được gắn**: nhận diện vị trí thiếu cấu hình, sửa đúng builder, phân biệt với những nguyên nhân khác và xác minh snippet sau khi chạy test.

## 2. Cấu hình đúng: gắn filter trước khi build WebTestClient

Với JUnit 5 và Spring REST Docs, một cách cấu hình phổ biến là dùng `RestDocumentationExtension` để cung cấp `RestDocumentationContextProvider`, sau đó đăng ký filter trên builder.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class UsersDocumentationTest {

    private WebTestClient webTestClient;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.webTestClient = WebTestClient.bindToController(new UsersController())
                .configureClient()
                .filter(documentationConfiguration(restDocumentation))
                .build();
    }
}
```

Điểm cần kiểm tra là thứ tự cấu hình:

1. Tạo builder từ controller, application context hoặc server.
2. Gọi `configureClient()` nếu cần cấu hình client.
3. Đăng ký `documentationConfiguration(restDocumentation)` bằng `filter(...)`.
4. Gọi `build()` để tạo client đã có filter.

Không thể thêm filter vào một builder sau khi client đã được build và kỳ vọng client cũ tự nhận cấu hình mới. Nếu có nhiều phương thức tạo WebTestClient, hãy xác định chính xác biến nào được inject hoặc gọi trong test.

### 2.1. Cấu hình khi bind vào ApplicationContext

Trong test Spring có application context, cấu hình tương tự:

```java
@Autowired
private ApplicationContext context;

private WebTestClient webTestClient;

@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    this.webTestClient = WebTestClient.bindToApplicationContext(this.context)
            .configureClient()
            .filter(documentationConfiguration(restDocumentation))
            .build();
}
```

Điểm khác biệt là nguồn tạo client. Việc đăng ký documentation filter vẫn nằm trên builder trước `build()`.

Nếu dùng WebTestClient kết nối tới server đang chạy, cũng cần cấu hình filter trên builder tương ứng. Đừng nhầm filter của REST Docs với filter bảo mật, filter xác thực, filter ghi log hoặc filter CORS của ứng dụng. Chúng có thể cùng tồn tại trong chuỗi, nhưng có nhiệm vụ khác nhau.

## 3. Ví dụ test hoàn chỉnh sinh snippet

Ví dụ dưới đây dùng một controller đơn giản trả JSON cố định. Trong dự án thật, thay controller minh họa bằng endpoint ứng dụng và fixture phù hợp.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class UserWebTestClientDocumentationTest {

    private WebTestClient webTestClient;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.webTestClient = WebTestClient.bindToController(new SampleController())
                .configureClient()
                .filter(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void getUser() {
        this.webTestClient.get()
                .uri("/users/42")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("42")
                .jsonPath("$.displayName").isEqualTo("Ha Nguyen")
                .consumeWith(document("users-get"));
    }

    @RestController
    static class SampleController {

        @GetMapping(value = "/users/42",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        String getUser() {
            return """
                    {
                      "id": "42",
                      "displayName": "Ha Nguyen"
                    }
                    """;
        }
    }
}
```

Trong ví dụ:

- `documentationConfiguration(restDocumentation)` được gắn vào builder bằng `filter(...)`.
- `document("users-get")` được dùng sau khi exchange và các assertion đã hoàn thành.
- REST Docs ghi snippet vào thư mục operation `users-get` bên dưới output directory được cấu hình.

Với cấu hình mặc định, một số snippet HTTP phổ biến có thể được sinh là `curl-request.adoc`, `http-request.adoc`, `http-response.adoc`, `httpie-request.adoc`, `request-body.adoc` và `response-body.adoc`. Các snippet thực tế phụ thuộc handler và cấu hình snippet được sử dụng.

## 4. Dấu hiệu cho thấy filter có thể chưa được đăng ký

Không nên chẩn đoán chỉ dựa trên một thông báo lỗi. Hãy xem lỗi phát sinh ở bước nào và kiểm tra cấu hình client trước.

| Dấu hiệu quan sát | Khả năng liên quan tới filter | Việc cần kiểm tra |
| --- | --- | --- |
| Test gọi `consumeWith(document(...))` nhưng REST Docs không thể lấy ngữ cảnh operation | Documentation filter chưa gắn vào client hoặc cấu hình context chưa được truyền đúng | Builder có `filter(documentationConfiguration(restDocumentation))` hay không |
| Client được tạo trong một helper khác và test không thấy cấu hình REST Docs | Helper trả về client chưa được cấu hình filter | Lần theo method tạo client và xác nhận filter được đăng ký trước `build()` |
| Một số test sinh snippet, một số test khác không | Các test đang dùng các instance WebTestClient khác nhau | So sánh builder của client được inject, client tự tạo và client trong test helper |
| Test đã pass nhưng thư mục operation không xuất hiện như dự kiến | `document(...)` chưa được gọi, filter/context không được dùng hoặc output directory khác | Kiểm tra bước `consumeWith`, log test, cấu hình REST Docs và đường dẫn output |
| Snippet mặc định có nhưng bảng field không có | Filter có thể đã hoạt động; handler field chưa được thêm hoặc nhánh xử lý chưa chạy | Kiểm tra `document(..., responseFields(...))` hoặc `requestFields(...)` |
| Snippet có nhưng thiếu header/parameter mong muốn | Handler document header/parameter chưa được khai báo hoặc request không gửi giá trị | Kiểm tra descriptor và request thực tế |

Các dấu hiệu chỉ giúp khoanh vùng, không khẳng định duy nhất một nguyên nhân. Đặc biệt, nếu test ném lỗi ở `document(...)`, cần xác định client có filter REST Docs và test có dùng đúng instance đó hay không.

## 5. Quy trình chẩn đoán theo từng bước

### Bước 1: tìm tất cả nơi tạo WebTestClient

Tìm các chỗ gọi:

```java
WebTestClient.bindToController(...)
WebTestClient.bindToApplicationContext(...)
WebTestClient.bindToServer()
WebTestClient.builder()
```

Sau đó xác định builder nào tạo ra instance được test gọi. Một dự án có thể có client dùng cho test API thông thường và client khác dùng cho REST Docs.

### Bước 2: kiểm tra documentation filter

Trong chuỗi builder của client dùng để document, cần thấy:

```java
.filter(documentationConfiguration(restDocumentation))
```

Đồng thời kiểm tra import đúng lớp:

```java
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;
```

Tránh import nhầm cấu hình dành cho MockMvc hoặc một filter khác có tên gần giống. Với WebTestClient, dùng API trong `org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation`.

### Bước 3: kiểm tra context của REST Docs

Khi dùng JUnit 5, extension cần được kích hoạt:

```java
@ExtendWith(RestDocumentationExtension.class)
class ApiDocumentationTest {
    // ...
}
```

Và phương thức setup nhận context:

```java
@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    // cấu hình WebTestClient tại đây
}
```

Nếu không dùng extension, dự án phải cung cấp `RestDocumentationContextProvider` theo cơ chế tích hợp khác. Không nên gọi `documentationConfiguration(null)` hoặc dùng context của một test khác.

### Bước 4: kiểm tra đúng instance được dùng

Ví dụ lỗi cấu hình phổ biến:

```java
@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    WebTestClient.Builder builder =
            WebTestClient.bindToController(new SampleController())
                    .configureClient();

    // Client được build trước khi gắn REST Docs filter.
    this.webTestClient = builder.build();
}

// Filter được thêm vào builder khác, không tác động client phía trên.
```

Cách sửa là đăng ký filter trước khi build client:

```java
@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    this.webTestClient = WebTestClient.bindToController(new SampleController())
            .configureClient()
            .filter(documentationConfiguration(restDocumentation))
            .build();
}
```

Lỗi tương tự có thể xảy ra khi một test tự tạo client mới thay vì dùng field `webTestClient` đã được setup.

### Bước 5: xác nhận `document(...)` được gọi

Với WebTestClient, document consumer thường được đặt ở cuối chuỗi exchange:

```java
webTestClient.get()
        .uri("/users/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("users-get"));
```

Nếu test chỉ gọi `exchange()` rồi kết thúc, hoặc assertion/flow dừng trước `consumeWith`, việc document không được thực hiện. Filter đã gắn không tự sinh snippet cho mọi request; phải có lời gọi `document(...)`.

### Bước 6: xác minh output directory và operation identifier

Sau khi test hoàn tất, xác định output directory mà REST Docs đang dùng và kiểm tra đúng tên operation. Ví dụ:

```text
build/generated-snippets/
└── users-get/
    ├── curl-request.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    ├── httpie-request.adoc
    ├── request-body.adoc
    └── response-body.adoc
```

Nếu output directory khác, snippet có thể vẫn được ghi nhưng bạn đang kiểm tra nhầm chỗ. Nếu operation identifier khác, thư mục cũng có tên khác.

## 6. Phân biệt filter thiếu với các lỗi cấu hình khác

Không phải mọi tình huống thiếu snippet đều do filter. Dùng bảng dưới để phân biệt:

| Nguyên nhân | Vị trí lỗi | Cách kiểm tra |
| --- | --- | --- |
| Thiếu documentation filter | Builder WebTestClient | Có `filter(documentationConfiguration(restDocumentation))` trước `build()` không? |
| Thiếu REST Docs extension/context | JUnit setup | Extension/provider đã được cấu hình và truyền đúng chưa? |
| Không gọi document consumer | Test method | Có `consumeWith(document("..."))` sau exchange không? |
| Sai operation identifier | `document(...)` và `include` | Tên thư mục output có trùng identifier không? |
| Sai output directory | Cấu hình REST Docs/build | Test và Asciidoctor có dùng cùng thư mục snippet không? |
| Chưa có handler field | Đối số `document(...)` | Có `requestFields`/`responseFields` cần thiết chưa? |
| Assertion thất bại trước document | Chuỗi test | Test dừng tại status/body assertion nào? |
| Test không chạy trong build | Gradle/Maven/CI | Task test có include đúng class/method không? |

Một cách chẩn đoán nhanh là xem **test có thực sự hoàn tất tới `consumeWith(document(...))` không**. Nếu assertion trước đó thất bại, snippet có thể chưa được sinh dù filter được cấu hình hoàn toàn đúng.

## 7. Cấu hình Spring Boot tự động và cấu hình thủ công

Trong một số dự án Spring Boot, có thể dùng hỗ trợ auto-configuration của Spring Boot Test với `@AutoConfigureRestDocs` và inject WebTestClient đã được cấu hình. Cách dùng annotation có thể khác với ví dụ tự tạo client thủ công.

Khi sử dụng một cơ chế auto-configuration:

- kiểm tra annotation ở đúng test class hoặc test slice;
- dùng instance WebTestClient được Spring inject;
- đọc cấu hình output directory đang được áp dụng;
- tránh tự tạo thêm client mới mà không đăng ký documentation filter.

Khi tự cấu hình bằng `documentationConfiguration(restDocumentation)`, hãy gắn filter rõ ràng trên builder như ví dụ ở mục 2. **Chọn một đường cấu hình nhất quán** và xác minh instance client cuối cùng. Không thêm cấu hình thủ công một cách máy móc nếu auto-configuration đã quản lý instance mà test đang sử dụng.

## 8. Filter và các filter khác trong WebTestClient

WebTestClient hỗ trợ chuỗi `ExchangeFilterFunction`. Documentation filter của REST Docs có thể cùng tồn tại với filter xác thực, header mặc định hoặc filter ghi log.

Ví dụ:

```java
this.webTestClient = WebTestClient.bindToController(new SampleController())
        .configureClient()
        .defaultHeader("X-Test-Client", "docs")
        .filter(documentationConfiguration(restDocumentation))
        .build();
```

Hãy đảm bảo filter REST Docs thực sự được đăng ký vào builder của client cuối cùng. Nếu có helper riêng để cấu hình filter, tránh tạo một builder mới sau khi đã gắn REST Docs mà không mang theo cấu hình đó.

Việc thứ tự filter có thể ảnh hưởng cách các filter quan sát request/response; nếu có filter tùy chỉnh thay đổi body hoặc header, kiểm tra xem snippet cần phản ánh dữ liệu trước hay sau biến đổi. Với nhu cầu chỉnh nội dung tài liệu, REST Docs còn hỗ trợ operation preprocessors; không nên dùng logging filter như một thay thế cho preprocessing tài liệu.

## 9. Đưa snippet vào Asciidoctor và CI

Khi filter và document consumer hoạt động, REST Docs sinh các snippet vào output directory. Asciidoctor cần chạy sau test và đọc đúng thư mục đó.

Ví dụ Gradle Groovy DSL, giả định dự án đã áp dụng plugin Asciidoctor và cấu hình REST Docs:

```groovy
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

Tài liệu `src/docs/asciidoc/users.adoc`:

```asciidoc
= User API

== GET /users/{id}

include::{snippets}/users-get/http-response.adoc[]

include::{snippets}/users-get/response-body.adoc[]
```

Chạy:

```bash
./gradlew clean test asciidoctor
```

Trong CI, việc chạy test trước Asciidoctor giúp tài liệu dùng snippet từ lần kiểm thử hiện tại. Nếu đường dẫn include sai hoặc snippet chưa được sinh, bước dựng tài liệu cần báo lỗi để nhóm kiểm tra lại cấu hình.

Với Maven, thư mục snippet thường là `target/generated-snippets`; cấu hình plugin tài liệu phải phụ thuộc vào test sinh snippet. Không giả định rằng chỉ có filter là đủ: operation identifier, output path và include cũng phải khớp nhau.

## 10. Checklist khắc phục nhanh

Khi nghi ngờ WebTestClient thiếu documentation filter, kiểm tra lần lượt:

- [ ] Đúng dependency Spring REST Docs WebTestClient có trong test classpath.
- [ ] Test dùng JUnit extension hoặc context provider hợp lệ.
- [ ] Builder của đúng WebTestClient có `filter(documentationConfiguration(restDocumentation))`.
- [ ] Filter được đăng ký trước `build()`.
- [ ] Test dùng đúng instance client đã cấu hình.
- [ ] `document("operation-id")` được gọi sau exchange trong `consumeWith(...)`.
- [ ] Assertion trước document không thất bại.
- [ ] Output directory và operation identifier đúng.
- [ ] Test được chạy trong Gradle/Maven/CI.
- [ ] Asciidoctor đọc cùng thư mục snippet vừa sinh.

Checklist giúp tách riêng lỗi tích hợp WebTestClient khỏi lỗi nội dung document hoặc lỗi build tài liệu.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Lỗi xảy ra khi gọi `document(...)` | Client thiếu filter hoặc context REST Docs không được gắn | Kiểm tra `documentationConfiguration(restDocumentation)` và extension/provider |
| Đã có filter nhưng snippet không xuất hiện | Test không dùng instance đó hoặc không chạy tới `consumeWith` | Lần theo client thực tế và chuỗi assertion |
| Chỉ một số test sinh snippet | Các test tạo client qua builder khác nhau | Chuẩn hóa method tạo WebTestClient cho test documentation |
| Snippet có nhưng Asciidoctor báo thiếu | Sai output directory hoặc operation identifier | Kiểm tra cấu hình snippet và đường dẫn include |
| Có HTTP snippet nhưng thiếu bảng field | Không truyền handler field vào `document(...)` | Bổ sung `requestFields` hoặc `responseFields` |
| Test dừng trước khi document | Assertion về status/body thất bại | Sửa dữ liệu hoặc expectation; không coi đây là lỗi filter |
| Filter REST Docs không được import | Import nhầm API của MockMvc | Dùng `WebTestClientRestDocumentation.documentationConfiguration` |
| Auto-config và client tự tạo cùng tồn tại | Test gọi client tự tạo chưa được cấu hình | Dùng đúng client inject hoặc thêm filter vào builder thủ công |

## 12. Bài thực hành

Tạo test `UserWebTestClientDocumentationTest`:

1. Tạo WebTestClient bằng `bindToController` hoặc `bindToApplicationContext`.
2. Cố tình bỏ `filter(documentationConfiguration(restDocumentation))`, chạy test và ghi nhận lỗi hoặc việc document không hoàn thành theo cấu hình hiện tại.
3. Thêm filter vào đúng builder trước `build()`, chạy lại.
4. Xác nhận test thực sự tới `consumeWith(document("users-get"))` và thư mục snippet operation xuất hiện.
5. Tạo một test khác dùng một WebTestClient mới; kiểm tra nếu client mới không có filter thì việc document gặp vấn đề dù client cũ đã cấu hình.
6. Cố tình đổi operation identifier trong Asciidoctor để kiểm tra build phát hiện đường dẫn include không tồn tại.
7. Chạy `./gradlew clean test asciidoctor` trong dự án đã cấu hình, rồi mở HTML để xác nhận snippet được nhúng.

**Tiêu chí hoàn thành:** bạn tìm đúng builder tạo client được test dùng, nhận biết documentation filter phải được đăng ký trước `build()`, phân biệt được lỗi filter với lỗi `document`/output/include, và xác nhận snippet sinh ra từ exchange đã kiểm thử.

## 13. Câu hỏi tự kiểm tra

**1. Documentation filter của WebTestClient được đăng ký ở đâu?**

Trên builder của WebTestClient bằng `.filter(documentationConfiguration(restDocumentation))`, trước khi gọi `build()`.

**2. `document("users-get")` có tự gắn filter không?**

Không. Đây là document consumer được dùng sau exchange. Client cần được cấu hình filter REST Docs để cung cấp cơ chế tích hợp cần thiết.

**3. Có filter nhưng không gọi `consumeWith(document(...))` thì sao?**

REST Docs không tự sinh snippet cho mọi request. Phải gọi document consumer ở exchange muốn ghi tài liệu.

**4. Filter đã gắn nhưng bảng field không xuất hiện, cần xem gì?**

Kiểm tra handler `responseFields(...)`/`requestFields(...)` đã được truyền vào `document(...)` chưa, và test có chạy tới đoạn document không.

**5. Nếu dùng Spring Boot auto-configuration có cần thêm filter thủ công không?**

Không nên thêm một cách máy móc. Hãy dùng đúng instance WebTestClient được auto-configuration chuẩn bị và xác minh cấu hình REST Docs đã áp dụng. Nếu tự tạo client mới, client đó cần cấu hình filter riêng.

## Tài liệu tham khảo

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html): ví dụ WebTestClient exchange và document consumer.
- [Spring REST Docs — Documented URIs](https://docs.spring.io/spring-restdocs/reference/configuration/uris.html): cấu hình WebTestClient và đăng ký documentation filter trên builder.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): cấu hình snippet, preprocessors và tích hợp tài liệu.

