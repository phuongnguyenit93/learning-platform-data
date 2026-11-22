# REST Assured URI customization với Spring REST Docs

## 1. Vì sao cần tùy chỉnh URI trong REST Assured?

REST Assured gửi HTTP request thật đến service đang chạy. Trong test, service có thể khởi động trên loopback, port ngẫu nhiên hoặc hostname nội bộ:

```text
http://localhost:53142/api/products/42
```

Người sử dụng API bên ngoài có thể gọi endpoint công khai:

```text
https://api.example.com/v1/products/42
```

Hai URI có thể đại diện cho cùng operation nhưng phục vụ hai mục đích khác nhau. URI thứ nhất là địa chỉ test cần dùng để gửi request đến service. URI thứ hai là địa chỉ nên xuất hiện trong tài liệu công khai. Nếu snippet ghi lại nguyên địa chỉ test, lệnh curl sinh ra có thể chứa port ngẫu nhiên hoặc hostname chỉ tồn tại trong mạng nội bộ.

Khi dùng REST Assured, cần phân biệt hai lớp cấu hình:

- **REST Assured request configuration:** quyết định request thực sự được gửi đến đâu, thông qua base URI, port, base path và request specification.
- **Spring REST Docs URI preprocessing:** thay đổi cách URI được trình bày trong snippet sau khi operation đã được thực hiện.

Tùy chỉnh URI tài liệu không chuyển request sang server khác. Nó chỉ thay đổi biểu diễn của request/response được ghi vào tài liệu. Đây là trọng tâm của bài **REST Assured URI customization** trong chương **URI configuration** của module **SPRING_REST_DOCS**. Module này tạo tài liệu REST API có thể kiểm chứng từ test HTTP với MockMvc, WebTestClient hoặc REST Assured, sinh snippet cho request/response rồi biên soạn bằng Asciidoctor/Markdown và build/CI.

Sau bài học, bạn có thể:

1. Cấu hình đích gửi request của REST Assured bằng RequestSpecification.
2. Dùng URI preprocessor của Spring REST Docs để chuẩn hóa scheme, host và port trong snippet.
3. Áp dụng riêng request preprocessor và response preprocessor.
4. Phân biệt authority với base path, route và query string.
5. Kiểm tra http-request, curl-request và response snippets trước khi công bố.

## 2. REST Assured gửi request thật

REST Assured là HTTP client dùng trong test. Khi gọi:

```java
given()
    .baseUri("http://localhost")
    .port(8080)
    .basePath("/api")
    .when()
    .get("/products/42");
```

request thực sự được gửi đến:

```text
http://localhost:8080/api/products/42
```

REST Assured không tạo request mô phỏng như MockMvc. Vì vậy, Spring REST Docs không thể áp dụng cách cấu hình URI defaults của MockMvc lên request đã gửi. URI trong operation được lấy từ HTTP exchange thực tế; muốn thay đổi URI được document, cần preprocessing sau exchange và trước khi ghi snippet.

### 2.1. Các thành phần URI

| Thành phần | Ví dụ | Cấu hình REST Assured liên quan |
| --- | --- | --- |
| Scheme | http | baseUri hoặc URL tuyệt đối |
| Host | localhost | baseUri hoặc URL tuyệt đối |
| Port | 53142 | port |
| Base path | /api | basePath |
| Resource path | /products/42 | Path truyền vào get, post, patch |
| Query | ?view=summary | queryParam hoặc query string |

URI public ví dụ https://api.example.com:443/v1/products/42 có scheme https, host api.example.com, port 443, base path /v1 và resource path /products/42. Không nhầm base path với host hoặc port.

## 3. Cấu hình đích request bằng RequestSpecification

Spring REST Docs không chọn server để REST Assured gọi tới. Phần đó thuộc trách nhiệm của REST Assured.

Ví dụ dùng một RequestSpecification riêng cho test:

```java
import io.restassured.builder.RequestSpecBuilder;
import io.restassured.specification.RequestSpecification;

RequestSpecification requestSpec = new RequestSpecBuilder()
        .setBaseUri("http://localhost")
        .setPort(8080)
        .setBasePath("/api")
        .build();
```

Dùng specification:

```java
given(requestSpec)
        .accept("application/json")
        .when()
        .get("/products/42")
        .then()
        .statusCode(200);
```

Trong ứng dụng test dùng random port, lấy port từ server test hoặc cấu hình test đang chạy rồi đưa vào RequestSpecification. Không ghi cứng port ngẫu nhiên vào tài liệu.

### 3.1. Dùng RequestSpecBuilder thay vì thay đổi global state

REST Assured có các thuộc tính static như RestAssured.baseURI, RestAssured.port và RestAssured.basePath. Cách này ngắn gọn:

```java
RestAssured.baseURI = "http://localhost";
RestAssured.port = 8080;
RestAssured.basePath = "/api";
```

Nhưng các giá trị static ảnh hưởng những test chạy sau và có thể gây xung đột khi test chạy song song hoặc mỗi class cần server/port khác nhau. RequestSpecification đóng gói cấu hình trong một đối tượng được truyền rõ ràng:

```java
RequestSpecification localService = new RequestSpecBuilder()
        .setBaseUri("http://127.0.0.1")
        .setPort(serverPort)
        .setBasePath("/api")
        .build();
```

serverPort ở đây phải là port thực tế mà test server đang lắng nghe. Lấy giá trị từ cơ chế khởi chạy server của dự án.

## 4. Cấu hình Spring REST Docs cho REST Assured

Tích hợp REST Assured của Spring REST Docs được đăng ký dưới dạng REST Assured Filter. Với JUnit 5, RestDocumentationExtension cấp RestDocumentationContextProvider để cấu hình output snippets:

```java
import io.restassured.builder.RequestSpecBuilder;
import io.restassured.specification.RequestSpecification;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;

import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class ProductRestAssuredDocumentationTest {

    private RequestSpecification spec;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.spec = new RequestSpecBuilder()
                .setBaseUri("http://localhost")
                .setPort(8080)
                .setBasePath("/api")
                .addFilter(documentationConfiguration(restDocumentation))
                .build();
    }
}
```

Trong cấu hình này:

1. setBaseUri, setPort và setBasePath xác định nơi test gửi request.
2. documentationConfiguration(restDocumentation) thêm filter ghi nhận operation và sinh snippets.
3. Các test dùng given(this.spec) để tái sử dụng cấu hình.

Dependency test cần dùng module tích hợp tương ứng, thường là spring-restdocs-restassured, bên cạnh REST Assured và JUnit 5. Phiên bản của Spring REST Docs và REST Assured cần tương thích với nền tảng Spring/Java của dự án.

## 5. Dùng modifyUris() để thay URI trong snippet

Spring REST Docs cung cấp modifyUris() trong package org.springframework.restdocs.operation.preprocess.Preprocessors. Preprocessor này thay một hoặc nhiều thành phần scheme, host và port của URI được document.

Ví dụ, test gọi server local nhưng tài liệu công khai dùng HTTPS:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

given(this.spec)
        .filter(document("product-detail",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .port(443)
                )))
        .when()
        .get("/products/42")
        .then()
        .statusCode(200);
```

Giả sử request thật được gửi đến:

```text
http://localhost:8080/api/products/42
```

Snippet request được tạo sau preprocessing có URI:

```text
https://api.example.com:443/api/products/42
```

Port mặc định 443 thường được biểu diễn mà không cần :443, tùy URI serialization; URL cuối cùng có thể hiện là:

```text
https://api.example.com/api/products/42
```

Request vẫn được gửi đến localhost ở port 8080. modifyUris() chỉ thay URI dùng trong tài liệu, không đổi network destination của exchange đã hoàn tất.

### 5.1. Cấu hình port

Nếu tài liệu cần public port không mặc định:

```java
modifyUris()
        .scheme("https")
        .host("partner-api.example.com")
        .port(8443)
```

Nếu public URL không có port tường minh:

```java
modifyUris()
        .scheme("https")
        .host("api.example.com")
        .removePort()
```

Chỉ chọn port theo endpoint khách hàng thực sự sử dụng. Không mang port random hoặc port backend vào tài liệu public.

## 6. Áp dụng preprocessor sau khi operation hoàn tất

Đây là điểm khác biệt quan trọng của REST Assured. REST Assured thực hiện HTTP exchange thật; URI customization phải diễn ra sau operation trên service nhưng trước khi Spring REST Docs tạo snippet. Cấu hình có thể gắn ngay vào filter document:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;

given(this.spec)
        .filter(document("product-list",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .removePort()
                )))
        .when()
        .get("/products")
        .then()
        .statusCode(200);
```

document(...) là filter của tích hợp REST Assured. Request preprocessor được truyền vào filter này để chuẩn hóa request operation trước khi ghi snippet.

### 6.1. Sửa cả URI trong response khi cần

Response có thể chứa URI tuyệt đối, chẳng hạn header Location hoặc link hypermedia. Chỉ dùng preprocessRequest(...) sẽ không sửa URI trong response. Nếu contract tài liệu cần public URI trong cả request lẫn response, áp dụng cả hai:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

given(this.spec)
        .filter(document("product-create",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .removePort()
                ),
                preprocessResponse(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .removePort()
                )))
        .when()
        .body("{\"name\":\"Keyboard\"}")
        .post("/products")
        .then()
        .statusCode(201);
```

UriModifyingOperationPreprocessor có thể sửa URI trong request URI, request headers/content, request part headers/content và response headers/content. Vì vậy, nếu response có URI absolute trong Location hoặc link body, cần kiểm tra snippet sau preprocessing để bảo đảm địa chỉ được chuẩn hóa đúng.

Chỉ áp dụng response preprocessing khi response contract cần thay URI. Không thay mọi chuỗi trong response một cách máy móc; chỉ URI mới thuộc phạm vi cần chuẩn hóa.

## 7. Phân biệt baseURI/basePath với modifyUris()

Đây là hai nhóm cấu hình dễ bị nhầm:

| Cấu hình | Khi nào có hiệu lực? | Có thay đích gửi HTTP không? | Có ảnh hưởng URI snippet không? |
| --- | --- | --- | --- |
| setBaseUri(...) | Khi REST Assured xây request | Có | URI thực tế được ghi nhận mang base URI đó |
| setPort(...) | Khi REST Assured xây request | Có | URI thực tế được ghi nhận mang port đó |
| setBasePath(...) | Khi REST Assured xây request | Có | Path trong request được ghi nhận có base path |
| modifyUris().scheme(...) | Khi Spring REST Docs preprocess operation | Không | Có, thay scheme trong snippet |
| modifyUris().host(...) | Khi Spring REST Docs preprocess operation | Không | Có, thay host trong snippet |
| modifyUris().port(...) | Khi Spring REST Docs preprocess operation | Không | Có, thay port trong snippet |
| modifyUris().removePort() | Khi Spring REST Docs preprocess operation | Không | Có, bỏ port trong snippet |

Ví dụ đúng với test local và tài liệu public:

```java
RequestSpecification spec = new RequestSpecBuilder()
        .setBaseUri("http://localhost")
        .setPort(8080)
        .setBasePath("/internal-api")
        .build();

given(spec)
        .filter(document("customer-detail",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .removePort()
                )))
        .when()
        .get("/customers/42")
        .then()
        .statusCode(200);
```

Kết quả:

- Test gửi request tới http://localhost:8080/internal-api/customers/42.
- Preprocessor tạo URI trong snippet là https://api.example.com/internal-api/customers/42.

Ví dụ chỉ đúng nếu public API thật sự expose path /internal-api/customers/42. Nếu gateway public dùng /v1/customers/42, thay host/scheme/port không đủ để biến path nội bộ thành path public. Hãy cấu hình test route phù hợp với external contract hoặc tổ chức tài liệu/path riêng đã được xác nhận.

## 8. Path, query string và URL encoding

modifyUris() tập trung vào scheme, host và port. Nó không phải công cụ đổi tên resource path, version prefix hoặc query parameter.

Ví dụ:

```java
given(this.spec)
        .queryParam("q", "spring rest docs")
        .queryParam("page", 2)
        .filter(document("product-search",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .removePort()
                )))
        .when()
        .get("/products/search")
        .then()
        .statusCode(200);
```

Preprocessor thay authority nhưng giữ path và query của request:

```text
https://api.example.com/api/products/search?q=spring%20rest%20docs&page=2
```

Chi tiết encoding phụ thuộc cách REST Assured xây query string và cấu hình URL encoding. Khi tài liệu hóa, dùng queryParam(...) để thể hiện ý nghĩa parameter và kiểm tra http-request.adoc/curl-request.adoc sau khi chạy test. Không tự nối query string bằng chuỗi nếu parameter có ký tự cần encode.

### 8.1. Khi public path khác internal path

Ví dụ:

| Môi trường | Path |
| --- | --- |
| Backend nội bộ | /internal/products/42 |
| Gateway public | /v1/products/42 |

Nếu test gọi backend trực tiếp, snippet được preprocess chỉ host/scheme/port vẫn còn /internal/products/42. Đừng dùng modifyUris() rồi mặc định rằng tài liệu đã có route public. Có thể test qua gateway test, hoặc viết hướng dẫn public route bằng tài liệu được xác minh và giữ snippet test cho phần request/response thực tế phù hợp. Tránh rewrite path bằng replace pattern rộng vì có thể thay nhầm payload, link hoặc giá trị dữ liệu.

## 9. Dùng preprocessor chung cho cả test suite

Nếu mọi operation đều cần cùng public authority, có thể tạo helper trả về request/response preprocessors:

```java
import org.springframework.restdocs.operation.preprocess.OperationRequestPreprocessor;
import org.springframework.restdocs.operation.preprocess.OperationResponsePreprocessor;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

final class PublicApiDocumentationUris {

    private PublicApiDocumentationUris() {}

    static OperationRequestPreprocessor publicRequestUri() {
        return preprocessRequest(
                modifyUris()
                        .scheme("https")
                        .host("api.example.com")
                        .removePort()
        );
    }

    static OperationResponsePreprocessor publicResponseUris() {
        return preprocessResponse(
                modifyUris()
                        .scheme("https")
                        .host("api.example.com")
                        .removePort()
        );
    }
}
```

Dùng trong test:

```java
given(this.spec)
        .filter(document("product-detail",
                PublicApiDocumentationUris.publicRequestUri(),
                PublicApiDocumentationUris.publicResponseUris()
        ))
        .when()
        .get("/products/42")
        .then()
        .statusCode(200);
```

Ưu điểm là host public được khai báo tập trung. Nếu có nhiều API host, tạo cấu hình riêng theo service hoặc nạp giá trị từ test property/environment. Tránh dùng biến static toàn cục có thể bị test khác sửa khi chạy song song.

## 10. Dùng preprocessor riêng cho một operation

Không phải operation nào cũng cần cùng authority. Ví dụ một gateway dành cho upload file có domain riêng:

```java
given(this.spec)
        .filter(document("file-upload",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("upload-api.example.com")
                                .removePort()
                )))
        .when()
        .multiPart("file", new File("report.pdf"))
        .post("/files")
        .then()
        .statusCode(201);
```

Các operation khác vẫn có thể dùng api.example.com. Đặt preprocessor ở đúng filter của operation cần ngoại lệ sẽ làm rõ ý định hơn là sửa global REST Assured base URI.

## 11. Ảnh hưởng lên response links và Location

URI có thể xuất hiện không chỉ ở request line. Một response tạo tài nguyên có thể trả:

```http
HTTP/1.1 201 Created
Location: http://localhost:8080/api/products/42
Content-Type: application/json

{
  "id": "42",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/products/42"
    }
  }
}
```

Nếu tài liệu công khai cần URI của gateway:

```text
Location: https://api.example.com/api/products/42
```

Áp dụng response preprocessor cùng request preprocessor như phần trước. Sau đó đọc lại http-response.adoc, response-body.adoc và các snippet hypermedia liên quan. Đảm bảo việc sửa URI phù hợp với link mà client thật sẽ nhận từ public API. Nếu ứng dụng đã trả public URI đúng ở production, hãy cân nhắc test qua gateway hoặc điều chỉnh cấu hình ứng dụng/proxy thay vì phụ thuộc vào việc sửa snippet để che response runtime sai.

## 12. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Request thực tế đi đến host public thay vì server test | Đã thay baseURI thay vì chỉ preprocessing snippet | Giữ base URI test; sửa URI trong filter document |
| Snippet vẫn chứa localhost | Filter document chưa nhận preprocessRequest(modifyUris()...) | Kiểm tra overload và import đúng preprocessor |
| Port random vẫn xuất hiện | Chỉ thay scheme/host, chưa đặt hoặc xóa port | Dùng port(...) hoặc removePort() |
| Request line đúng nhưng Location vẫn chứa host local | Chỉ preprocess request | Thêm preprocessResponse(modifyUris()...) nếu response URI cần chuẩn hóa |
| Host đúng nhưng path vẫn là internal route | modifyUris() không đổi base path/resource path | Test qua public gateway hoặc xác định external path riêng |
| Query string bị encode hai lần | Tự encode trước khi truyền vào queryParam | Truyền giá trị thô cho REST Assured và kiểm tra URL sinh ra |
| Test song song gây rò base URI/port | Dùng REST Assured static global configuration | Dùng RequestSpecification riêng cho từng test/client |
| Response link bị thay đổi ngoài ý muốn | Preprocessor xử lý cả URI trong response content | Chỉ áp dụng response preprocessing khi cần và kiểm tra snippet |
| API trả redirect nhưng snippet mô tả URL chưa đúng | Chưa xem xét header Location và redirect response | Kiểm tra response header, body và cả request/response preprocessors |

## 13. Build, Asciidoctor và CI

Quy trình:

1. Cấu hình REST Assured với base URI, port và base path của service test.
2. Đăng ký documentationConfiguration(restDocumentation) như filter để sinh snippets.
3. Gắn request/response URI preprocessor vào document(...) cho từng operation hoặc dùng helper chung.
4. Chạy test để sinh http-request.adoc, curl-request.adoc, http-response.adoc và payload snippets.
5. Render Asciidoctor và kiểm tra host/port/path trong output.
6. Trong CI, rà soát hostname nội bộ, loopback và port test trong tài liệu public; cho phép chúng ở phần hướng dẫn chạy local nếu được ghi rõ.

Ví dụ Gradle khi task đã được cấu hình:

```bash
./gradlew test asciidoctor
```

Thư mục snippets thường là build/generated-snippets với Gradle hoặc target/generated-snippets với Maven, tùy cấu hình extension. Asciidoctor phải phụ thuộc vào test task để đọc snippets vừa sinh.

Ví dụ rà soát thủ công:

```bash
grep -RniE 'localhost|127\\.0\\.0\\.1|0\\.0\\.0\\.0|:8080|:5[0-9]{4}' build/generated-snippets
```

Kết quả match cần được xem theo ngữ cảnh. Một test snippet nội bộ hoặc hướng dẫn local có thể hợp lệ; trang API công khai không nên yêu cầu người đọc truy cập loopback hoặc port ephemeral của test.

## 14. Bài tập thực hành

Một ứng dụng catalog chạy trong test tại:

```text
http://localhost:53142/internal-api
```

Public API được công bố tại:

```text
https://catalog.example.com/v2
```

Endpoint public là:

```text
GET /v2/products/{productId}
```

Hãy thực hiện:

1. Tạo RequestSpecification trỏ tới host và port test thực tế.
2. Thêm documentationConfiguration(restDocumentation) vào REST Assured filter chain.
3. Dùng preprocessRequest(modifyUris()...) để thay scheme/host/port trong snippet.
4. Xác minh path test có thực sự tương ứng với public path. Nếu internal path khác external path, quyết định test qua gateway hay tổ chức tài liệu/path theo contract đã xác nhận.
5. Tạo operation trả Location và hypermedia link; áp dụng response preprocessor nếu cần chuẩn hóa URI response.
6. Chạy test, kiểm tra curl-request và render Asciidoctor trong CI.

**Tiêu chí hoàn thành:** REST Assured vẫn gọi đúng server test; snippet thể hiện đúng public scheme, host và port; path/query không bị thay đổi ngoài ý muốn; URI trong Location và link response nhất quán với tài liệu public.

## 15. Ghi nhớ

REST Assured gửi HTTP request thật, vì vậy cấu hình base URI, port và base path quyết định server nhận request. Spring REST Docs URI preprocessing chạy sau operation và trước khi sinh snippet, cho phép thay scheme, host hoặc port mà không đổi đích gửi HTTP. Dùng preprocessRequest(modifyUris()...) cho request; thêm preprocessResponse(modifyUris()...) nếu response cũng chứa URI cần chuẩn hóa. modifyUris() không tự sửa resource path hoặc contract của gateway. Giữ RequestSpecification riêng, kiểm tra URL trong request/response snippets và đưa rà soát host/port test vào CI để tài liệu phản ánh đúng địa chỉ mà người tích hợp cần sử dụng.

### Tài liệu tham khảo

- [Spring REST Docs — REST Assured URI Customization](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/#configuration-uris-rest-assured)
- [Spring REST Docs — Modifying URIs](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/#customizing-requests-and-responses-modifying-uris)
- [Spring REST Docs — REST Assured integration](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/#getting-started-setting-up-your-tests)
- [REST Assured — Usage and Request Specification](https://github.com/rest-assured/rest-assured/wiki/Usage)
