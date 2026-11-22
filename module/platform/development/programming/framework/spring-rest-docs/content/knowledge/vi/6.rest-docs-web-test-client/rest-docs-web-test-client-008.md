# Tiền xử lý URI, header và body trong WebTestClient

## 1. Mục tiêu bài học

Trong module **SPRING_REST_DOCS**, ta tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP dùng MockMvc, WebTestClient hoặc REST Assured. Test gửi request, xác nhận response và sinh snippet cho request, response, payload, tham số và header; sau đó Asciidoctor/Markdown ghép snippet vào build và CI.

Trong chương **WebTestClient**, cần phân biệt hai việc: chuẩn bị request thực tế để ứng dụng nhận đúng URI, header, body; và chuẩn hóa bản request/response được Spring REST Docs ghi vào snippet. Bản tài liệu nên có URL ổn định, payload dễ đọc và không để lộ token, cookie hoặc dữ liệu nội bộ.

Sau bài học, bạn có thể xây dựng URI từ template/path/query; thiết lập header cho từng request hoặc mặc định trên client; gửi JSON, chuỗi và reactive publisher; phân biệt request thật với bản đã tiền xử lý để ghi snippet; chuẩn hóa URI, loại header nội bộ và định dạng/che body bằng REST Docs preprocessors.

## 2. Hai lớp xử lý cần phân biệt

| Lớp | Công cụ | Mục đích |
| --- | --- | --- |
| **Chuẩn bị request gửi đến ứng dụng** | uri(...), headers(...), header(...), contentType(...), bodyValue(...), body(...) | Xác định HTTP request thực tế mà endpoint nhận. |
| **Tiền xử lý dữ liệu tài liệu hóa** | preprocessRequest(...), preprocessResponse(...), modifyUris(), modifyHeaders(), prettyPrint(), replacePattern(...) | Chuẩn hóa hoặc loại dữ liệu khỏi bản request/response được ghi vào snippet. |

~~~mermaid
flowchart TD
    A["WebTestClient request builder"] --> B["HTTP request thực tế"]
    B --> C["WebFlux endpoint"]
    C --> D["HTTP response thực tế"]
    D --> E["Assertions"]
    E --> F["consumeWith(document(...))"]
    F --> G["REST Docs preprocessors"]
    G --> H["Request/response snippets"]
    H --> I["Asciidoctor / CI"]
~~~

Ví dụ, header Authorization được đặt bằng request builder để endpoint có thể xác thực. Một request preprocessor có thể loại Authorization khỏi **snippet** để tài liệu không chứa credential. Preprocessor không làm request gửi đến ứng dụng mất header đó; assertion vẫn kiểm tra response mà ứng dụng thực sự trả về.

Nguyên tắc quan trọng: **không nhầm việc thay đổi request thật với việc thay đổi bản sao dùng để tạo tài liệu**. Nếu sửa header hoặc URI ở phía WebTestClient, endpoint sẽ nhận giá trị đã sửa. Nếu dùng REST Docs preprocessor, mục tiêu là điều chỉnh dữ liệu tài liệu hóa.

## 3. Xây dựng URI cho request

### 3.1. URI template và path variable

Dùng URI template giúp code test dễ đọc và khớp với path parameter mà REST Docs cần mô tả:

~~~java
client.get()
    .uri("/api/orders/{orderId}", 42)
    .exchange()
    .expectStatus().isOk();
~~~

Giá trị 42 được gán vào biến {orderId}. Khi dùng pathParameters(...) trong document(...), tên descriptor cần khớp tên biến trong URI template và hợp đồng endpoint.

### 3.2. Query parameter

Có thể gắn query parameter trực tiếp trong URI:

~~~java
client.get()
    .uri("/api/orders?status={status}&page={page}", "PAID", 0)
    .exchange()
    .expectStatus().isOk();
~~~

Hoặc dùng UriBuilder khi URI có nhiều điều kiện:

~~~java
client.get()
    .uri(builder -> builder
        .path("/api/orders")
        .queryParam("status", "PAID")
        .queryParam("page", 0)
        .queryParam("size", 20)
        .build())
    .exchange()
    .expectStatus().isOk();
~~~

UriBuilder giúp tránh nối chuỗi query thủ công, nhất là khi giá trị cần được encode. Khi tài liệu hóa query parameter, dùng descriptor phù hợp với phiên bản Spring REST Docs của dự án và bảo đảm request thật sự có tham số đó.

### 3.3. Base URL và URI mặc định

Khi test thường xuyên gọi cùng một API prefix, có thể cấu hình base URL lúc xây dựng client:

~~~java
WebTestClient client = WebTestClient.bindToServer()
    .baseUrl("http://localhost:8080")
    .build();
~~~

Ví dụ này dùng HTTP server đang chạy. Với client bind vào controller, router hoặc ApplicationContext trong test, thường dùng URI tương đối như /api/orders. Nếu cần kiểm tra host/port thực, hãy chọn chế độ bind phù hợp.

Base URL là một phần của địa chỉ request thực tế. REST Docs có thể chuẩn hóa host, scheme hoặc port trong bản ghi để snippet không phụ thuộc máy chạy CI; việc đó không đổi địa chỉ mà WebTestClient đã gọi.

## 4. Thiết lập request header

### 4.1. Header trên từng request

Dùng header(name, values...) khi một operation cần header cụ thể:

~~~java
client.get()
    .uri("/api/orders/{id}", 42)
    .header("X-Request-Id", "test-req-001")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk();
~~~

### 4.2. Thiết lập nhiều header

headers(...) cho phép sửa HttpHeaders trong một callback:

~~~java
client.post()
    .uri("/api/orders")
    .headers(headers -> {
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));
        headers.set("X-Request-Id", "test-req-002");
    })
    .bodyValue(Map.of("productId", "BOOK-01", "quantity", 2))
    .exchange()
    .expectStatus().isCreated();
~~~

Các import bổ trợ:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.http.MediaType;
~~~

### 4.3. Header mặc định của client

Khi nhiều test dùng chung header, đặt default header lúc xây dựng WebTestClient:

~~~java
WebTestClient client = WebTestClient.bindToController(new OrderController())
    .configureClient()
    .defaultHeader("X-Client-Name", "documentation-test")
    .build();
~~~

Header mặc định áp dụng cho các request của client, trừ khi được ghi đè theo cách API hỗ trợ. Không đặt token cá nhân, mật khẩu hoặc bí mật dùng chung vào default header hay tài liệu. Dùng credential giả dành riêng cho test và loại chúng khỏi snippet.

## 5. Gửi request body

### 5.1. JSON bằng bodyValue(...)

Khi body là object đơn giản, bodyValue(...) là cách trực tiếp:

~~~java
client.post()
    .uri("/api/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of(
        "productId", "BOOK-01",
        "quantity", 2
    ))
    .exchange()
    .expectStatus().isCreated();
~~~

WebFlux codec serialize object thành JSON theo Content-Type và cấu hình codec. Khi tài liệu hóa request, requestFields(...) mô tả cấu trúc body; request-body.adoc thể hiện payload được ghi nhận tùy snippet và cấu hình.

### 5.2. Chuỗi hoặc nội dung văn bản

Với endpoint nhận plain text:

~~~java
client.put()
    .uri("/api/notes/{id}", 7)
    .contentType(MediaType.TEXT_PLAIN)
    .bodyValue("Nội dung ghi chú")
    .exchange()
    .expectStatus().isNoContent();
~~~

Content-Type phải phản ánh kiểu body và tương thích với consumes của endpoint. Không gửi JSON nhưng khai báo text/plain, hoặc ngược lại.

### 5.3. Reactive publisher làm body

Khi dữ liệu đầu vào là publisher, sử dụng body(...) với BodyInserters:

~~~java
Flux<OrderLine> lines = Flux.just(
    new OrderLine("BOOK-01", 2),
    new OrderLine("BOOK-02", 1)
);

client.post()
    .uri("/api/orders/import")
    .contentType(MediaType.APPLICATION_JSON)
    .body(BodyInserters.fromPublisher(lines, OrderLine.class))
    .exchange()
    .expectStatus().isAccepted();
~~~

Ví dụ giả định endpoint import chấp nhận dữ liệu JSON dạng stream và các lớp OrderLine/service đã được định nghĩa. Cần import BodyInserters và Flux. Xác định endpoint mong đợi một JSON array hữu hạn, NDJSON hay streaming body; media type và cách encode ảnh hưởng đến request server nhận. Snippet cần đại diện cho request mẫu có thể tái lập, tránh nguồn dữ liệu ngẫu nhiên giữa các lần chạy.

## 6. Chuẩn hóa URI trong snippet bằng REST Docs

Test bind vào server thật có thể ghi host và port khác nhau giữa local, CI và các máy chạy test. Dùng modifyUris() để chuẩn hóa địa chỉ **trong snippet**:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

client.get()
    .uri("/api/orders/{id}", 42)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders/get",
        preprocessRequest(
            modifyUris()
                .scheme("https")
                .host("api.example.com")
                .removePort()
        )
    ));
~~~

Đây là phần cuối của test đã cấu hình REST Docs filter. Request thật vẫn gửi tới server test; bản http-request.adoc được chuẩn hóa thành URL ví dụ https://api.example.com/api/orders/42.

| Phương thức | Ảnh hưởng tới snippet |
| --- | --- |
| scheme("https") | Thay scheme được ghi. |
| host("api.example.com") | Dùng hostname tài liệu cố định. |
| port(443) | Ghi port đã chọn. |
| removePort() | Bỏ port khỏi URI được ghi. |

Chọn tổ hợp theo địa chỉ công khai của API. Không dùng host giả làm người đọc hiểu nhầm endpoint production; hãy ghi rõ base URL mẫu khi cần.

## 7. Loại bỏ hoặc sửa header trong snippet

Request thực tế có thể chứa Authorization, Cookie, X-Internal-Token hoặc X-Request-Id. Không phải tất cả header đều cần xuất bản. Spring REST Docs cung cấp preprocessor để chỉnh sửa các header **trong bản ghi tài liệu**.

### 7.1. Xóa header nhạy cảm

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

.consumeWith(document("orders/get",
    preprocessRequest(
        modifyHeaders()
            .remove("Authorization")
            .remove("Cookie")
            .remove("X-Internal-Token")
    )
));
~~~

Đoạn này minh họa phần cuối của test GET; request thực tế vẫn có thể gửi header cần thiết để xác thực. Chỉ những header bị xóa khỏi bản ghi snippet. Kiểm tra API modifyHeaders() trong phiên bản Spring REST Docs của dự án nếu chữ ký khác.

### 7.2. Mô tả header công khai

Nếu hợp đồng API yêu cầu mô tả X-Request-Id, dùng descriptor:

~~~java
requestHeaders(
    headerWithName("X-Request-Id")
        .description("Mã theo dõi request")
)
~~~

Descriptor nói header có ý nghĩa gì trong API; preprocessor quyết định header nào xuất hiện trong bản request đã chuẩn hóa. Không loại header khỏi snippet nếu tài liệu cần người dùng hiểu cách gọi endpoint hoặc descriptor yêu cầu thể hiện header đó.

### 7.3. Thay giá trị header nhạy cảm

Nếu muốn giữ tên header nhưng thay giá trị bằng ví dụ an toàn, dùng API chỉnh sửa header phù hợp với phiên bản thư viện hoặc tạo credential giả ngay từ đầu trong test. Cách an toàn và dễ bảo trì là không dùng bí mật thật trong test; preprocessor không nên là lớp phòng vệ duy nhất chống rò rỉ credential.

## 8. Định dạng và che dữ liệu trong body snippet

### 8.1. Định dạng JSON

Dùng prettyPrint() để tạo snippet JSON dễ đọc:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

.consumeWith(document("orders/create",
    preprocessRequest(prettyPrint()),
    preprocessResponse(prettyPrint()),
    requestFields(
        fieldWithPath("productId").description("Mã sản phẩm"),
        fieldWithPath("quantity").description("Số lượng")
    )
));
~~~

Đây là đoạn nối vào test POST có body JSON gồm productId và quantity. prettyPrint() cải thiện định dạng snippet; nó không sửa body thực tế đã gửi hoặc nhận.

### 8.2. Thay chuỗi nhạy cảm trong body

Khi response ví dụ có dữ liệu cần ẩn, replacePattern(...) có thể thay nội dung khớp biểu thức chính quy trong bản ghi:

~~~java
import java.util.regex.Pattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;

.consumeWith(document("profile/get",
    preprocessResponse(
        replacePattern(
            Pattern.compile("\"email\"\\s*:\\s*\"[^\"]+\""),
            "\"email\":\"user@example.test\""
        ),
        prettyPrint()
    )
));
~~~

Đoạn ví dụ áp dụng cho JSON response có field email, thay giá trị bằng địa chỉ mẫu. Trong code thực tế, cần kiểm tra regex và thứ tự preprocessor để kết quả JSON vẫn hợp lệ. Tốt hơn hết là tạo fixture với dữ liệu giả ngay từ đầu; không dùng thông tin cá nhân thật trong response mẫu.

### 8.3. Tiền xử lý theo operation hoặc mặc định cho client

| Phạm vi | Cách cấu hình | Khi nào dùng |
| --- | --- | --- |
| Một operation | document(..., preprocessRequest(...), preprocessResponse(...)) | Endpoint cần quy tắc đặc biệt. |
| Mọi operation của client | operationPreprocessors().withRequestDefaults(...).withResponseDefaults(...) | Quy tắc chung như pretty print hoặc chuẩn hóa URI. |

Ví dụ cấu hình mặc định:

~~~java
client = WebTestClient.bindToController(new OrderController())
    .configureClient()
    .filter(documentationConfiguration(restDocumentation)
        .operationPreprocessors()
            .withRequestDefaults(prettyPrint())
            .withResponseDefaults(prettyPrint()))
    .build();
~~~

Đây là cấu hình thay cho phần khởi tạo client trong @BeforeEach. Khi cần xử lý riêng một operation, có thể bổ sung preprocessor trong chính document(...).

## 9. Ví dụ tích hợp: chuẩn hóa request và tạo snippet

Ví dụ sau giả định endpoint POST /api/orders nhận JSON, yêu cầu request ID và trả tài nguyên mới. Client đã được cấu hình REST Docs filter.

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.http.MediaType;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

client.post()
    .uri("/api/orders")
    .headers(headers -> {
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));
        headers.set("X-Request-Id", "doc-test-001");
        headers.setBearerAuth("test-token");
    })
    .bodyValue(Map.of(
        "productId", "BOOK-01",
        "quantity", 2
    ))
    .exchange()
    .expectStatus().isCreated()
    .expectHeader().valueEquals("Location", "/api/orders/42")
    .expectBody()
    .jsonPath("$.id").isEqualTo(42)
    .consumeWith(document("orders/create",
        preprocessRequest(
            modifyUris()
                .scheme("https")
                .host("api.example.com")
                .removePort(),
            modifyHeaders()
                .remove("Authorization")
        ),
        preprocessResponse(prettyPrint()),
        requestHeaders(
            headerWithName("X-Request-Id")
                .description("Mã truy vết request")
        ),
        requestFields(
            fieldWithPath("productId").description("Mã sản phẩm"),
            fieldWithPath("quantity").description("Số lượng")
        ),
        responseHeaders(
            headerWithName("Location")
                .description("URI của đơn hàng được tạo")
        ),
        responseFields(
            fieldWithPath("id").description("Mã đơn hàng")
        )
    ));
~~~

Đoạn code kết hợp các phần đã học:

1. headers(...) gửi Content-Type, Accept, X-Request-Id và Authorization tới endpoint.
2. bodyValue(...) gửi JSON request.
3. exchange() thực hiện HTTP request; các expect...() xác nhận response.
4. preprocessRequest(...) chuẩn hóa URI và xóa Authorization khỏi snippet.
5. preprocessResponse(prettyPrint()) định dạng JSON response trong snippet.
6. Descriptor mô tả request header, request field, response header và response field.

Trong môi trường test mẫu, test-token là credential giả; không sao chép token thật vào ví dụ hoặc kho tài liệu. Việc bỏ Authorization khỏi snippet không bỏ qua bước xác thực của endpoint.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân và cách xử lý |
| --- | --- |
| Request đi sai endpoint | Kiểm tra URI template, base URL, path variable và query parameter; tránh nối chuỗi thủ công khi cần encoding. |
| Server trả 400 vì query parameter | Kiểm tra tên, kiểu dữ liệu, encoding và giá trị qua UriBuilder. |
| Server trả 415 | Content-Type không khớp body hoặc consumes của endpoint. |
| Server trả 406 | Accept không tương thích với produces/codec của endpoint. |
| Header mặc định làm test khác nhau | Kiểm tra defaultHeader(...) và header ghi đè; tránh mang header không cần thiết sang mọi operation. |
| Snippet có host/port ngẫu nhiên | Dùng REST Docs modifyUris() để chuẩn hóa bản ghi, đồng thời giữ base URL thực cho test. |
| Snippet chứa Authorization hoặc Cookie | Dùng credential giả, loại header khỏi snippet và kiểm tra tệp đã sinh trước khi chia sẻ. |
| Body snippet khó đọc | Áp dụng prettyPrint() trong document(...) hoặc preprocessor mặc định. |
| Body sau replace không còn JSON hợp lệ | Rà regex, nội dung thay thế và thứ tự preprocessor; ưu tiên fixture không chứa dữ liệu nhạy cảm. |
| Descriptor không khớp request/response | Cập nhật requestFields, responseFields, requestHeaders, responseHeaders và parameter theo HTTP thực tế. |

## 11. Tích hợp snippet vào Asciidoctor và CI

Với operation có identifier orders/create, snippet tiêu biểu được lưu dưới thư mục:

~~~text
build/generated-snippets/
└── orders/
    └── create/
        ├── http-request.adoc
        ├── http-response.adoc
        ├── request-headers.adoc
        ├── request-fields.adoc
        ├── response-headers.adoc
        └── response-fields.adoc
~~~

Đây là các tệp tiêu biểu; snippet mặc định khác có thể xuất hiện tùy cấu hình và loại request/response.

Asciidoctor tham chiếu các tệp:

~~~asciidoc
= Orders API
:snippets: build/generated-snippets

== Tạo đơn hàng

include::{snippets}/orders/create/http-request.adoc[]
include::{snippets}/orders/create/request-headers.adoc[]
include::{snippets}/orders/create/request-fields.adoc[]
include::{snippets}/orders/create/http-response.adoc[]
include::{snippets}/orders/create/response-headers.adoc[]
include::{snippets}/orders/create/response-fields.adoc[]
~~~

Với Gradle (giả sử plugin Asciidoctor đã được cấu hình và có task asciidoctor):

~~~groovy
def snippetsDir = layout.buildDirectory.dir("generated-snippets")

tasks.named("test") {
    outputs.dir(snippetsDir)
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(snippetsDir)
    attributes "snippets": snippetsDir.get().asFile
}
~~~

CI có thể chạy ./gradlew clean test asciidoctor khi các plugin/task đã được khai báo. Test xác nhận request/response, preprocessor chuẩn hóa nội dung snippet và Asciidoctor dựng trang từ kết quả mới. Với Markdown thuần, cần bước build riêng để nhúng hoặc liên kết snippet; cú pháp include:: là của Asciidoctor.

## 12. Bài thực hành

1. Gửi GET với path variable và query parameter qua uri(...)/UriBuilder; kiểm tra URL thực tế bằng assertion và mô tả parameter trong REST Docs.
2. Thêm X-Request-Id và Authorization giả vào một request POST; xác nhận server nhận request đúng và snippet không chứa Authorization.
3. Dùng modifyUris() để đổi host/port trong http-request.adoc; so sánh URL được gọi trong test với URL ghi trong snippet.
4. Gửi JSON qua bodyValue(...), bật prettyPrint() và đối chiếu request-body.adoc.
5. Thử replacePattern(...) với fixture email giả, sau đó kiểm tra JSON trong snippet vẫn hợp lệ.
6. Cấu hình preprocessor mặc định cho client, dựng Asciidoctor và xác nhận snippet không chứa token hoặc hostname ngẫu nhiên.

## 13. Ghi nhớ

- Dùng uri(...)/UriBuilder để tạo URI rõ ràng; dùng header(...), headers(...), defaultHeader(...) để chuẩn bị header gửi thật.
- Chọn bodyValue(...) cho object/giá trị đơn giản và body(...) cho publisher hoặc body inserter phù hợp.
- Request builder quyết định dữ liệu ứng dụng nhận; REST Docs preprocessors điều chỉnh bản request/response được ghi trong snippet.
- modifyUris() chuẩn hóa URL; modifyHeaders() loại header không cần công bố; prettyPrint() định dạng body; replacePattern() thay nội dung khớp trong bản ghi.
- Dùng dữ liệu giả trong test, kiểm tra snippet trước khi chia sẻ và không dựa duy nhất vào preprocessor để bảo vệ bí mật.
- Cho CI chạy test trước Asciidoctor để tài liệu được tạo từ những request/response đã xác nhận.
