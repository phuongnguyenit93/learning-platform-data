# URI chứa localhost hoặc port không mong muốn

## 1. Vì sao URI trong snippet có `localhost` hoặc port lạ?

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ HTTP tests dùng MockMvc, WebTestClient hoặc REST Assured. Khi test chạy, request thường đi qua địa chỉ cục bộ, embedded server hoặc test client có base URI riêng. Vì vậy snippet `http-request.adoc`, `curl-request.adoc` hoặc `http-response.adoc` đôi khi hiển thị URI như:

```http
GET http://localhost:53821/api/books/42 HTTP/1.1
Host: localhost:53821
```

Trong tài liệu công bố, nhóm có thể muốn hiển thị:

```http
GET https://api.example.com/api/books/42 HTTP/1.1
Host: api.example.com
```

Port ngẫu nhiên thường đến từ embedded server chạy với random port; `localhost` là địa chỉ test nội bộ, không phải host public của API. URI trong snippet phản ánh request mà test đã gửi hoặc thông tin request mà test client cung cấp. Nó không tự biết domain production.

Đây thường là vấn đề **chuẩn hóa ví dụ tài liệu**, không nhất thiết là lỗi endpoint. Hãy phân biệt URI thực tế được dùng để gửi request với URI đại diện muốn công bố. Không thay đổi cấu hình server hoặc DNS production chỉ để làm snippet đẹp hơn.

## 2. Xác định URI được lấy từ đâu

Các test client có thể tạo request URI theo cách khác nhau:

| Test client | Nguồn host/port thường gặp | Điều cần kiểm tra |
| --- | --- | --- |
| MockMvc | Mock servlet request và cấu hình test; đôi khi URI mặc định có `localhost`. | URI truyền vào `get/post`, servlet context path và request builder. |
| WebTestClient | Base URL hoặc URI được cấu hình cho client; bind-to-server có thể dùng random port. | `baseUrl`, `bindToServer`, `bindToApplicationContext` và URI trong từng request. |
| REST Assured | `baseURI`, `port`, `basePath` hoặc cấu hình `RequestSpecification`. | Specification dùng chung, port ngẫu nhiên và URI truyền vào `.get(...)`. |

Trước khi preprocess, đọc `http-request.adoc` để xem chính xác phần nào không mong muốn: scheme, host, port, path, query hay header `Host`. Chỉ chuẩn hóa phần cần thiết; không xóa path hoặc query parameters vốn là một phần của hợp đồng API.

## 3. Chuẩn hóa URI bằng request preprocessor

Spring REST Docs cung cấp `modifyUris()` để thay đổi thành phần URI trong request được document. Có thể dùng `preprocessRequest(...)` trong `document(...)`:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

filter(document("books-get",
        preprocessRequest(
                modifyUris()
                        .scheme("https")
                        .host("api.example.com")
                        .removePort())));
```

Ví dụ này chuẩn hóa scheme thành `https`, host thành `api.example.com` và bỏ port khỏi URI được ghi vào snippet. Path, query string và các phần khác của URI được giữ nguyên. Nếu API công bố trên một port không mặc định, có thể đặt port mong muốn bằng cấu hình `port(...)` thay vì xóa.

Preprocessor chỉ tác động request representation dùng để tạo tài liệu. Nó không thay đổi địa chỉ mà test đã gọi, không đổi server đang lắng nghe và không cấu hình proxy/DNS.

## 4. Dùng chung preprocessor cho MockMvc, WebTestClient và REST Assured

Preprocessor được gắn tại operation document, vì vậy cách áp dụng tương tự dù test client khác nhau.

### MockMvc

```java
mockMvc.perform(get("/api/books/{id}", 42))
        .andExpect(status().isOk())
        .andDo(document("books-get",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .removePort())));
```

### WebTestClient

```java
webTestClient.get()
        .uri("/api/books/{id}", 42)
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("books-get",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .removePort())));
```

### REST Assured

```java
given(this.specification)
        .filter(document("books-get",
                preprocessRequest(
                        modifyUris()
                                .scheme("https")
                                .host("api.example.com")
                                .removePort())))
.when()
        .get("/api/books/{id}", 42)
.then()
        .statusCode(200);
```

Các đoạn code rút gọn để minh họa vị trí gắn preprocessor. Dùng filter/configuration và static imports phù hợp với module Spring REST Docs, test client và version dự án.

## 5. Chọn port: xóa hay thay bằng port công bố?

Nếu API public dùng HTTPS trên port mặc định 443, URI thường không cần hiển thị port. Khi đó `.removePort()` phù hợp. Nếu API được công bố trên port khác, có thể đặt port tường minh:

```java
preprocessRequest(
        modifyUris()
                .scheme("https")
                .host("api.example.com")
                .port(8443))
```

Chỉ đưa port vào tài liệu khi client thực sự cần dùng nó. Không đưa random port như `53821` từ embedded server vào tài liệu API vì giá trị này có thể thay đổi mỗi lần chạy test.

| URI test | URI tài liệu mong muốn | Cách xử lý |
| --- | --- | --- |
| `http://localhost:53821/api/books/42` | `https://api.example.com/api/books/42` | Đổi scheme/host và remove port. |
| `http://127.0.0.1:8080/api/books` | `https://api.example.com:8443/api/books` | Đổi scheme/host và đặt port 8443. |
| `http://localhost/api/books` | `https://api.example.com/api/books` | Đổi scheme/host; port có thể không cần chỉnh. |

## 6. Không nhầm URI với header `Host`

URI và HTTP header `Host` là hai phần khác nhau của request representation. `modifyUris()` chuẩn hóa URI được hiển thị trong request snippet. Tùy cách test client tạo request và snippet template, header `Host` có thể vẫn thể hiện giá trị ban đầu hoặc được xử lý riêng.

Hãy đọc cả hai dòng trong `http-request.adoc`:

```http
GET https://api.example.com/api/books/42 HTTP/1.1
Host: localhost:53821
```

Nếu URI đã đúng nhưng `Host` còn là địa chỉ test, quyết định xem header này có được document hay không. Nếu nó không thuộc thông tin client cần cấu hình, có thể bỏ header khỏi snippet bằng request preprocessor thích hợp hoặc tùy chỉnh template theo mục tiêu tài liệu. Không nên tự thay header bằng giá trị production nếu điều đó làm sai ví dụ request mà client thực sự cần gửi.

Khi API phụ thuộc virtual host/routing theo Host header, giá trị Host có thể là một phần hợp đồng cần công bố. Khi đó phải document đúng host yêu cầu và kiểm chứng bằng test tương ứng.

## 7. Giữ nguyên path, query và context path

Chuẩn hóa host không có nghĩa là xóa phần còn lại của URI. Ví dụ:

```text
Test URI:
http://localhost:53821/store/api/books/42?view=full

Document URI:
https://api.example.com/store/api/books/42?view=full
```

Context path `/store`, API path `/api/books/42` và query `view=full` vẫn được giữ. Nếu tài liệu mong muốn bỏ context path hoặc thay API version, đó là một quyết định khác và cần được xử lý có chủ đích. Không xóa query parameters vì chúng có thể là đầu vào quan trọng của operation.

Nếu URI trong snippet thiếu path segment, kiểm tra request builder/basePath/context path trước khi dùng `modifyUris()`. Preprocessor đổi URI theo cấu hình; nó không sửa lỗi endpoint mapping hoặc request được test gọi nhầm.

## 8. Dùng preprocessor chung để tránh lặp cấu hình

Nếu nhiều operation dùng cùng public base URI, có thể tạo helper:

```java
private static OperationRequestPreprocessor publicApiUri() {
    return preprocessRequest(
            modifyUris()
                    .scheme("https")
                    .host("api.example.com")
                    .removePort());
}
```

Sau đó:

```java
filter(document("books-get",
        publicApiUri(),
        responseFields(
                fieldWithPath("id").description("Mã sách"))));
```

```java
filter(document("orders-create",
        publicApiUri(),
        requestFields(
                fieldWithPath("customerId").description("Mã khách hàng"))));
```

Đặt helper ở test support dùng chung để mọi operation có cùng cách chuẩn hóa. Nếu tài liệu có nhiều API host hoặc version, truyền cấu hình theo service thay vì hard-code một host dùng cho tất cả.

## 9. Chọn host theo môi trường build

Không phải dự án nào cũng có một hostname công bố duy nhất. Có thể cấu hình host bằng Gradle/Maven property hoặc system property của test, nhưng cần bảo đảm output tài liệu tái lập được.

Ví dụ Java helper đọc property có default an toàn cho tài liệu:

```java
private static String docsApiHost() {
    return System.getProperty("docs.api.host", "api.example.com");
}

private static OperationRequestPreprocessor publicApiUri() {
    return preprocessRequest(
            modifyUris()
                    .scheme("https")
                    .host(docsApiHost())
                    .removePort());
}
```

Có thể truyền property khi chạy test:

```bash
./gradlew test -Ddocs.api.host=api.example.com
```

Nếu dùng host từ environment/CI, đừng để hostname nội bộ hoặc hostname của staging vô tình đi vào tài liệu công khai. Hãy đặt default rõ ràng và kiểm tra snippet trong build artifact trước khi publish. Không đưa secret hoặc token vào property được ghi vào snippet.

## 10. Chuẩn hóa response links và absolute URLs

Một response hypermedia có thể chứa absolute links trong JSON, ví dụ:

```json
{
  "_links": {
    "self": { "href": "http://localhost:53821/api/books/42" }
  }
}
```

`modifyUris()` trong `preprocessRequest(...)` xử lý URI của request snippet; không nên giả định nó tự thay mọi absolute URL nằm trong response body. Nếu response JSON chứa localhost trong `href`, cần kiểm tra nguồn tạo link:

- Server tạo link từ request host/scheme như thế nào?
- Test có gửi forwarded headers (`X-Forwarded-Host`, `X-Forwarded-Proto`) và ứng dụng có tin cậy chúng không?
- Có thể cấu hình public base URI trong application/test configuration không?
- Có nên dùng response preprocessor để thay host chỉ trong tài liệu không?

Ví dụ response preprocessor có thể thay nội dung body, nhưng phải cẩn trọng để chỉ thay giá trị host cần chuẩn hóa và không làm biến đổi payload semantics. Tốt nhất là cấu hình link generation đúng theo cách ứng dụng dự kiến triển khai và kiểm chứng response href trong test.

Không dùng `modifyUris()` của request để kết luận response hypermedia links đã được chuẩn hóa. Hãy mở `http-response.adoc` và kiểm tra JSON/XML thực tế.

## 11. Không làm sai lệch ví dụ HTTP

Preprocessor là công cụ trình bày tài liệu, không phải cách che giấu lỗi cấu hình. Trước khi thay host/port, xác nhận:

- Path và query trong request vẫn đúng.
- Scheme/host công bố là endpoint thật mà người dùng API sẽ gọi.
- Port bị xóa chỉ khi không cần công bố.
- Header `Host` không còn mâu thuẫn với URI nếu header được hiển thị.
- Absolute links trong response được kiểm tra riêng.
- Các ví dụ cURL và HTTP request không đưa token/cookie nội bộ ra ngoài.

Nếu tài liệu nhằm hướng dẫn chạy integration test tại local, có thể giữ `localhost` và giải thích port được cấp động. Nếu tài liệu là API reference công khai, chuẩn hóa về public base URI thường dễ sử dụng hơn. Chọn theo đối tượng đọc và mục đích tài liệu.

## 12. Chẩn đoán khi URI vẫn không đúng sau preprocess

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Snippet vẫn có `localhost` | Preprocessor chưa được truyền vào đúng `document(...)` hoặc operation dùng cấu hình khác. | Kiểm tra filter/document call của operation đó. |
| Host đã đúng nhưng port vẫn còn | Chưa gọi `removePort()` hoặc đặt `port(...)` theo cấu hình khác. | Chọn một chiến lược port rõ ràng và kiểm tra URI output. |
| Scheme vẫn là `http` | Preprocessor chưa áp dụng hoặc có operation-specific override. | Xác nhận `.scheme("https")` nằm trong request preprocessor đang chạy. |
| URI đúng nhưng `Host` header sai | Header được ghi riêng, không đồng nhất với URI đã sửa. | Kiểm tra request headers snippet và xử lý header có chủ đích. |
| Request URI đúng nhưng response `_links` còn localhost | Response body chứa absolute URLs do server tạo. | Kiểm tra link generation/forwarded headers hoặc response preprocessor riêng. |
| Path/query bị mất | Request builder hoặc custom preprocessing đã thay đổi nhiều hơn host. | So sánh raw request và snippet; giữ nguyên phần path/query. |
| Local đúng, CI sai | Host property/environment khác nhau hoặc operation không dùng helper chung. | In cấu hình không nhạy cảm và chuẩn hóa property trong CI. |
| Port random xuất hiện lại ở một operation | Operation đó không dùng shared preprocessor. | Dùng helper chung và rà toàn bộ document calls. |

## 13. Quy trình xử lý từ đầu đến cuối

1. Chạy test và mở `http-request.adoc` của operation bị lỗi.
2. Xác định phần sai là scheme, host, port, path, query hay `Host` header.
3. Tìm nguồn cấu hình URI trong MockMvc/WebTestClient/REST Assured.
4. Chọn public base URI mà tài liệu cần công bố.
5. Gắn `preprocessRequest(modifyUris()...)` vào operation hoặc helper dùng chung.
6. Chạy lại test để sinh snippet mới; không sửa file generated bằng tay.
7. Đọc lại cả `http-request.adoc`, `curl-request.adoc` và các header snippets liên quan.
8. Kiểm tra `http-response.adoc` riêng nếu hypermedia href cũng chứa localhost.
9. Render Asciidoctor và xác nhận HTML/PDF hiển thị URI đúng.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Public docs lộ `localhost` | Snippet ghi nguyên test URI. | Dùng request preprocessor để chuẩn hóa scheme/host. |
| Port random xuất hiện | Embedded server dùng random port. | Dùng `.removePort()` hoặc đặt port công bố. |
| Chỉ một số operation được chuẩn hóa | Preprocessor chỉ được gắn vào một số document calls. | Tạo helper dùng chung và áp dụng nhất quán. |
| Host header không khớp URI | URI và header được xử lý riêng. | Kiểm tra header snippet, document hoặc preprocess theo hợp đồng. |
| JSON `_links.href` vẫn localhost | Request preprocessor không sửa response body. | Sửa link generation hoặc response preprocessing có kiểm soát. |
| Dùng domain staging trong tài liệu public | Property CI/environment không đúng. | Dùng property tài liệu riêng, default/allowlist host công bố. |
| Chỉnh snippet thủ công nhưng mất sau test | Generated output được ghi lại. | Sửa preprocessor hoặc template trong source test. |

## 15. Checklist thực hành

- [ ] Đã xác định URI sai trong request snippet hay absolute href trong response body.
- [ ] Đã kiểm tra nguồn host/port của test client.
- [ ] Đã chọn public scheme, host và port đúng với tài liệu cần phát hành.
- [ ] Đã dùng `preprocessRequest(modifyUris()...)` cho request URI khi phù hợp.
- [ ] Đã giữ nguyên path, query và context path.
- [ ] Đã quyết định rõ xóa port hay đặt port công bố.
- [ ] Đã kiểm tra header `Host` riêng nếu nó xuất hiện trong snippet.
- [ ] Đã kiểm tra response hypermedia links riêng; không giả định request preprocessor sửa body.
- [ ] Các operation dùng chung helper hoặc cấu hình thống nhất.
- [ ] Đã chạy lại test, đọc snippet mới và render HTML/PDF trước khi publish.
- [ ] Không để hostname nội bộ, token hoặc cookie nhạy cảm lọt vào tài liệu.

URI chứa `localhost` hoặc port ngẫu nhiên thường xuất phát từ môi trường test. Spring REST Docs cho phép chuẩn hóa request URI bằng `preprocessRequest(modifyUris()...)` để tài liệu hiển thị public scheme, host và port phù hợp mà không thay đổi request thực thi. Hãy kiểm tra riêng URI, header `Host` và absolute links trong response; mỗi phần có thể cần cách xử lý khác nhau. Sau khi preprocess, luôn chạy lại test và đọc snippet mới trước khi render tài liệu.

## Tài liệu tham khảo

- [Spring REST Docs – Preprocessors](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [Spring REST Docs – Preprocessors API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/operation/preprocess/Preprocessors.html)
- [Spring REST Docs – OperationRequestPreprocessor API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/operation/preprocess/OperationRequestPreprocessor.html)
