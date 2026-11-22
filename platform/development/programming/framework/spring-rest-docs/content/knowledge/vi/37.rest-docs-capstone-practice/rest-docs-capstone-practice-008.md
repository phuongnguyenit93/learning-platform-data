# Che token và host bằng preprocessors

## 1. Mục tiêu bài thực hành

Trong một HTTP operation, tài liệu REST API có thể ghi lại nhiều dữ liệu cần làm sạch: Authorization header, API key, cookie session, access/refresh token trong JSON, query values, hostname nội bộ và port động của môi trường test. Một preprocessor đơn lẻ không xử lý mọi vùng dữ liệu. Cần chọn đúng công cụ theo vị trí dữ liệu:

- **modifyHeaders()**: set hoặc remove request/response headers.
- **replacePattern()**: thay pattern trong request/response content, thường là body text.
- **modifyUris()**: chuẩn hóa scheme, host và port của URI.
- **maskLinks()**: che href của hypermedia links được nhận diện trong content.

Bài thuộc chương **Thực hành tổng hợp** của module **SPRING_REST_DOCS**. Module tạo tài liệu REST API có thể kiểm chứng từ HTTP tests bằng MockMvc, WebTestClient hoặc REST Assured; sinh snippets cho request, response, payload, tham số và header; biên soạn Asciidoctor/Markdown rồi tích hợp build/CI.

Bài thực hành sẽ kết hợp các thao tác trên trong một workflow có kiểm chứng. Kết quả mong muốn là snippets vẫn thể hiện được contract API, nhưng không công bố credential hoặc địa chỉ môi trường nội bộ.

Sau bài này, bạn có thể:

- Phân loại dữ liệu nhạy cảm theo header, body và URI.
- Thay Authorization/API key/cookie bằng placeholder.
- Mask token/password trong JSON body.
- Chuẩn hóa host và port của request/response URI.
- Che hypermedia href mà vẫn giữ link relations.
- Nhận biết trường hợp query parameter cần synthetic value hoặc custom request preprocessor.
- Scan toàn bộ snippets và tài liệu đã render trước khi publish.

## 2. Chuẩn bị scenario và dữ liệu tổng hợp

Giả sử service có endpoint lấy đơn hàng và trả hypermedia links:

**Request**

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.internal.cluster.local:8087
Authorization: Bearer DOCS_ONLY_ACCESS_TOKEN
X-Api-Key: DOCS_ONLY_API_KEY
Cookie: JSESSIONID=DOCS_ONLY_SESSION
Accept: application/json
~~~

**Response**

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Set-Cookie: SESSION=DOCS_ONLY_RESPONSE_SESSION; Path=/; HttpOnly; Secure

{
  "id": 42,
  "status": "PAID",
  "accessToken": "DOCS_ONLY_RESPONSE_TOKEN",
  "_links": {
    "self": {
      "href": "http://orders.internal.cluster.local:8087/api/orders/42"
    },
    "payment": {
      "href": "http://payments.internal.cluster.local:8092/checkout?ticket=DOCS_ONLY_TICKET"
    }
  }
}
~~~

Các giá trị DOCS_ONLY_* là sentinel tổng hợp, không phải credential thật. Dùng sentinel để xác minh redaction: nếu bất kỳ giá trị nào còn trong generated output, bài kiểm tra phải thất bại.

### 2.1. Lập bảng xử lý trước khi viết code

| Dữ liệu | Vị trí | Cách xử lý |
| --- | --- | --- |
| Bearer token | Request Authorization | Set placeholder hoặc remove header. |
| API key | Request X-Api-Key | Set placeholder hoặc remove header. |
| Session cookie | Request Cookie | Remove header. |
| Response session | Response Set-Cookie | Remove hoặc set placeholder. |
| accessToken | JSON response body | replacePattern hoặc JSON-aware modifier. |
| Internal host/port | URI | modifyUris để chuẩn hóa scheme/host/port. |
| Hypermedia href | JSON HAL links | maskLinks nếu muốn che toàn bộ href. |
| Query ticket | Request URI hoặc href | Synthetic value; custom URI preprocessor nếu request URI cần thay. |

Bảng này giúp chọn đúng API. Đừng áp dụng một regex chung cho cả HTTP dump rồi giả định tất cả loại dữ liệu đã được che.

## 3. Chuẩn hóa host và port bằng modifyUris()

Trong test, server có thể chạy trên localhost hoặc port ngẫu nhiên; request/response URI được ghi lại có thể chứa địa chỉ nội bộ. Spring REST Docs có modifyUris() để thay scheme, host và port.

Ví dụ chuẩn hóa request URI về host tài liệu:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

preprocessRequest(
    modifyUris()
        .scheme("https")
        .host("api.example.test")
        .removePort()
)
~~~

Nếu muốn đặt port cố định, có thể dùng cấu hình port tương ứng của ModifyUrisOperationPreprocessor thay vì removePort.

### 3.1. Giới hạn của modifyUris()

modifyUris() xử lý thành phần URI như scheme, host và port. Không coi nó là công cụ:

- Xóa query parameters.
- Thay token trong JSON body.
- Thay Authorization/Cookie headers.
- Thay path segment.
- Tìm mọi URL nằm trong free-text response.

Ví dụ URI có query:

~~~text
http://orders.internal.cluster.local:8087/oauth/callback?code=DOCS_ONLY_CODE
~~~

Sau khi chuẩn hóa host/port, query code vẫn có thể còn nguyên. Dùng synthetic value trong test hoặc custom request preprocessor nếu cần thay query trong request URI.

### 3.2. Chuẩn hóa host không nhất thiết phải mask host

Nếu hostname public/sandbox là một phần hướng dẫn gọi API, thay host nội bộ bằng host tài liệu có thể hữu ích hơn che toàn bộ URI. Nếu endpoint chỉ dành cho internal docs, có thể dùng hostname internal đã được phê duyệt cho audience đó. Quyết định dựa trên classification và audience.

## 4. Che request headers bằng modifyHeaders()

Đặt placeholder cho Authorization và API key, đồng thời loại session cookie:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

preprocessRequest(
    modifyHeaders()
        .set("Authorization", "Bearer <access-token>")
        .set("X-Api-Key", "<api-key>")
        .remove("Cookie")
)
~~~

Header names vẫn xuất hiện cho người đọc biết API yêu cầu gì. Các values được thay bằng placeholder không có hiệu lực.

Nếu tài liệu không cần thể hiện tên header nhạy cảm, remove chúng:

~~~java
preprocessRequest(
    modifyHeaders()
        .remove("Authorization")
        .remove("X-Api-Key")
        .remove("Cookie")
)
~~~

Chọn set hay remove dựa trên mục đích tài liệu. Không remove Content-Type, Accept hoặc header contract khác nếu người đọc cần chúng để gọi API.

## 5. Xử lý response headers

Response có thể phát hành session cookie hoặc token trong custom header. Dùng response preprocessor riêng:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

preprocessResponse(
    modifyHeaders()
        .remove("Set-Cookie")
        .remove("X-Internal-Trace")
)
~~~

Nếu cần giải thích cookie attributes, thay value nhưng giữ attributes:

~~~java
preprocessResponse(
    modifyHeaders()
        .set("Set-Cookie", "SESSION=<session-id>; Path=/; HttpOnly; Secure")
)
~~~

Không dùng request preprocessor để mong nó tự che response headers. Hai chiều request và response phải được cấu hình riêng.

## 6. Che token trong body bằng replacePattern()

Body response ví dụ:

~~~json
{
  "id": 42,
  "status": "PAID",
  "accessToken": "DOCS_ONLY_RESPONSE_TOKEN",
  "refreshToken": "DOCS_ONLY_REFRESH_TOKEN"
}
~~~

Có thể dùng regex nhắm vào các field string cụ thể:

~~~java
import java.util.regex.Pattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

private static final Pattern TOKEN_FIELDS = Pattern.compile(
    "(\"(accessToken|refreshToken)\"\\s*:\\s*\")[^\"]*(\")"
);

preprocessResponse(
    replacePattern(TOKEN_FIELDS, "$1[REDACTED]$3")
)
~~~

Kết quả mong muốn:

~~~json
{
  "id": 42,
  "status": "PAID",
  "accessToken": "[REDACTED]",
  "refreshToken": "[REDACTED]"
}
~~~

Pattern phải khớp payload thực tế. Regex minh họa này dành cho JSON string đơn giản; nếu body có escaped quotes, nested structures phức tạp hoặc nhiều media types, dùng JSON-aware ContentModifier để parse, thay đúng property rồi serialize lại.

### 6.1. Không nhầm body replacement với header replacement

replacePattern() xử lý request/response content. Nó không thao tác trực tiếp trên header collection. Với Authorization, Cookie hoặc Set-Cookie, dùng modifyHeaders().set/remove().

Nếu chỉ nhìn file http-request cuối cùng, headers và body có thể nằm cạnh nhau trong cùng snippet text. Điều đó không có nghĩa hai vùng được xử lý bởi cùng API.

## 7. Che hypermedia href bằng maskLinks()

Response HAL có thể chứa href với hostname nội bộ hoặc query ticket. Nếu mục tiêu là che toàn bộ hypermedia href, dùng maskLinks():

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.maskLinks;

preprocessResponse(
    maskLinks("[LINK]")
)
~~~

maskLinks() nhắm vào href của hypermedia links được nhận diện trong content. Link relations như self, payment, cancel vẫn có thể được mô tả bằng links descriptors.

### 7.1. Khi nào nên maskLinks, khi nào nên modifyUris?

| Nhu cầu | Chọn |
| --- | --- |
| Che toàn bộ href trong hypermedia links | maskLinks() |
| Thay host nội bộ bằng host public/sandbox | modifyUris() nếu URI thuộc phạm vi preprocessor |
| Loại Authorization/Cookie | modifyHeaders() |
| Thay token field trong JSON | replacePattern() hoặc ContentModifier |
| Che query value trong request URI | Synthetic test value hoặc custom request preprocessor |
| Che URL nằm trong JSON string thường | Fixture giả, replacePattern hoặc JSON-aware modifier |

Nếu cần giữ URL để người đọc có thể hiểu cấu trúc, normalize host/port có thể phù hợp. Nếu href chứa signed URL có thể sử dụng, mask toàn bộ href hoặc dùng fixture không có chữ ký thật.

## 8. Kết hợp preprocessors trong một operation

Một operation có thể áp dụng request và response preprocessors cùng lúc:

~~~java
.andDo(document("orders-get",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .set("X-Api-Key", "<api-key>")
            .remove("Cookie"),
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
    ),
    preprocessResponse(
        modifyHeaders()
            .remove("Set-Cookie")
            .remove("X-Internal-Trace"),
        replacePattern(TOKEN_FIELDS, "$1[REDACTED]$3"),
        maskLinks("[LINK]"),
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
    )
));
~~~

Đây là cấu hình minh họa. Import, overload và thứ tự kết hợp phải khớp Spring REST Docs version của dự án. Nếu maskLinks() được dùng, href có thể đã được thay bằng placeholder; modifyUris() sau đó không còn host cụ thể để chuẩn hóa. Chọn một cách xử lý link phù hợp thay vì áp dụng cả hai một cách dư thừa.

### 8.1. Tách helper dùng chung

Có thể gom policy headers:

~~~java
private static OperationRequestPreprocessor sanitizeRequest() {
    return preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .set("X-Api-Key", "<api-key>")
            .remove("Cookie"),
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
    );
}

private static OperationResponsePreprocessor sanitizeResponse() {
    return preprocessResponse(
        modifyHeaders().remove("Set-Cookie"),
        replacePattern(TOKEN_FIELDS, "$1[REDACTED]$3")
    );
}
~~~

Sau đó gắn helper vào operation:

~~~java
.andDo(document("orders-get",
    sanitizeRequest(),
    sanitizeResponse()
));
~~~

Đặt policy ở helper giảm nguy cơ một operation quên redaction. Với endpoints có response HAL hoặc link nhạy cảm, bổ sung maskLinks hoặc custom logic riêng.

## 9. Xử lý query parameters và URL text

modifyUris() không phải query masking tool; maskLinks() không che request URI tổng quát. Với query chứa token, ưu tiên test fixture an toàn:

~~~java
mockMvc.perform(get("/oauth/callback")
        .queryParam("code", "DOCS_ONLY_CODE")
        .queryParam("state", "DOCS_ONLY_STATE"))
    .andExpect(status().isOk())
    .andDo(document("oauth-callback"));
~~~

Nếu request URI bắt buộc được tạo từ giá trị động, viết custom OperationRequestPreprocessor để parse URI, thay value của đúng keys nhạy cảm rồi tạo request mới bằng API/factory của version REST Docs. Bảo toàn encoding, duplicate keys, method, headers và body.

Nếu URL nằm trong field JSON như redirectUrl, dùng fixture giả, replacePattern trên response content hoặc JSON-aware modifier. Không giả định maskLinks nhận diện mọi string URL.

## 10. Ví dụ tích hợp với MockMvc

~~~java
mockMvc.perform(get("/api/orders/42")
        .header("Authorization", "Bearer DOCS_ONLY_ACCESS_TOKEN")
        .header("X-Api-Key", "DOCS_ONLY_API_KEY")
        .cookie(new Cookie("JSESSIONID", "DOCS_ONLY_SESSION")))
    .andExpect(status().isOk())
    .andDo(document("orders-get",
        preprocessRequest(
            modifyHeaders()
                .set("Authorization", "Bearer <access-token>")
                .set("X-Api-Key", "<api-key>")
                .remove("Cookie"),
            modifyUris()
                .scheme("https")
                .host("api.example.test")
                .removePort()
        ),
        preprocessResponse(
            modifyHeaders().remove("Set-Cookie"),
            replacePattern(TOKEN_FIELDS, "$1[REDACTED]$3"),
            maskLinks("[LINK]")
        )
    ));
~~~

Test sử dụng sentinel DOCS_ONLY_* để leak check có thể phát hiện nếu preprocessor bị bỏ quên. Nếu request/response URI còn host nội bộ, bổ sung modifyUris() vào đúng chiều operation.

## 11. Áp dụng cho WebTestClient và REST Assured

### 11.1. WebTestClient

~~~java
webTestClient.get()
    .uri("/api/orders/42")
    .header("Authorization", "Bearer DOCS_ONLY_ACCESS_TOKEN")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders-get-webflux",
        preprocessRequest(
            modifyHeaders().set("Authorization", "Bearer <access-token>"),
            modifyUris().scheme("https").host("api.example.test").removePort()
        ),
        preprocessResponse(
            modifyHeaders().remove("Set-Cookie"),
            replacePattern(TOKEN_FIELDS, "$1[REDACTED]$3"),
            maskLinks("[LINK]")
        )
    ));
~~~

Dùng WebTestClient REST Docs filter/configuration đúng version. Kiểm tra snippets được tạo bởi chính filter đang chạy trong test.

### 11.2. REST Assured

~~~java
given(specification)
    .header("Authorization", "Bearer DOCS_ONLY_ACCESS_TOKEN")
    .filter(document("orders-get-restassured",
        preprocessRequest(
            modifyHeaders().set("Authorization", "Bearer <access-token>"),
            modifyUris().scheme("https").host("api.example.test").removePort()
        ),
        preprocessResponse(
            modifyHeaders().remove("Set-Cookie"),
            replacePattern(TOKEN_FIELDS, "$1[REDACTED]$3"),
            maskLinks("[LINK]")
        )
    ))
.when()
    .get("/api/orders/42")
.then()
    .statusCode(200);
~~~

Cấu hình REST Assured documentation filter theo context của dự án. Không lấy token từ môi trường production hoặc browser session làm fixture.

## 12. Kiểm chứng generated snippets bằng sentinel

Sau khi chạy tests, scan toàn bộ output directory và assembled docs. Sentinel nên là chuỗi duy nhất, dễ tìm:

~~~text
DOCS_ONLY_ACCESS_TOKEN
DOCS_ONLY_API_KEY
DOCS_ONLY_SESSION
DOCS_ONLY_RESPONSE_TOKEN
DOCS_ONLY_TICKET
orders.internal.cluster.local
payments.internal.cluster.local
~~~

Ví dụ assertion:

~~~java
assertThat(allGeneratedDocumentation)
    .doesNotContain("DOCS_ONLY_ACCESS_TOKEN")
    .doesNotContain("DOCS_ONLY_API_KEY")
    .doesNotContain("DOCS_ONLY_SESSION")
    .doesNotContain("DOCS_ONLY_RESPONSE_TOKEN")
    .doesNotContain("DOCS_ONLY_TICKET")
    .doesNotContain("orders.internal.cluster.local")
    .doesNotContain("payments.internal.cluster.local");
~~~

Nếu host đã được chuẩn hóa, kiểm tra host public mong muốn còn lại. Nếu hypermedia href đã mask, kiểm tra placeholder [LINK] và link relation descriptors vẫn có mặt.

Scan các loại output:

- http-request và http-response.
- curl-request và httpie-request.
- request-body và response-body.
- Request/response headers và parameters.
- Custom snippets.
- Assembled Markdown/Asciidoctor.
- Rendered HTML và CI artifacts được upload.

Không chỉ kiểm tra một file request snippet.

## 13. CI gate cho redaction và host normalization

~~~mermaid
flowchart TD
    A["HTTP tests with synthetic secrets"] --> B["Apply header preprocessors"]
    B --> C["Apply body and URI preprocessors"]
    C --> D["Generate all snippets"]
    D --> E["Assemble and render docs"]
    E --> F["Scan secret sentinels and internal hosts"]
    F --> G{"Leak found?"}
    G -->|Yes| X["Fail build"]
    G -->|No| H["Validate snippets and links"]
    H --> I{"All checks pass?"}
    I -->|No| X
    I -->|Yes| J["Review artifact"]
    J --> K["Publish approved docs"]
~~~

CI cần:

1. Chạy clean HTTP tests với synthetic values.
2. Sinh snippets bằng preprocessors đúng operation.
3. Assemble và render tài liệu.
4. Scan sentinel tokens, API keys, session IDs và internal hostnames.
5. Kiểm tra public host/placeholder mong muốn.
6. Fail build nếu bất kỳ sentinel nào còn trong output.
7. Không in nguyên secret vào log khi báo lỗi.
8. Chỉ upload/publish artifact sau khi scan và review pass.

Secret scanner bổ sung cho sentinel check. Không allowlist các giá trị thật chỉ để pipeline thành công.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Authorization còn trong snippet | Chỉ dùng replacePattern trên body | Dùng modifyHeaders set/remove. |
| Token JSON vẫn còn | Chỉ che headers | Dùng replacePattern hoặc ContentModifier. |
| Host nội bộ vẫn còn trong request | Chỉ normalize response | Preprocess đúng chiều request/response. |
| Query token vẫn còn sau modifyUris | modifyUris chỉ đổi scheme/host/port | Synthetic query value hoặc custom URI preprocessor. |
| Hypermedia href còn chữ ký | Chưa dùng maskLinks hoặc response fixture giả | Mask href hoặc thay bằng fixture an toàn. |
| JSON bị hỏng | Regex không xử lý escaping/nesting | Dùng JSON-aware ContentModifier. |
| Header contract biến mất | Remove header cần được tài liệu hóa | Set placeholder thay vì remove. |
| Public hostname cũng bị mask | Áp dụng maskLinks quá rộng | Chọn modifyUris nếu cần giữ cấu trúc link. |
| Chỉ HTTP snippet sạch, curl còn token | Chỉ scan một file | Scan toàn bộ operation output. |
| Local pass, CI fail | CI fixture/host khác local | Dùng synthetic fixtures và cùng build config. |
| Build dùng snippet cũ | Task dependency/output khai báo sai | Clean output, chạy tests trước render. |

## 15. Bài tập capstone

Hoàn thành tài liệu cho hai operations:

- GET /api/orders/42: yêu cầu Bearer token, API key tùy chọn, cookie session có thể xuất hiện; response chứa HAL links.
- POST /api/orders: request body có customerEmail và clientReference; response có accessToken tạm thời cho một flow nghiệp vụ.

Thực hiện:

1. Tạo HTTP tests bằng MockMvc, WebTestClient hoặc REST Assured.
2. Dùng sentinel riêng cho Authorization, API key, Cookie, token body và internal host.
3. Dùng modifyHeaders() để thay/remove request và response headers.
4. Dùng replacePattern() hoặc ContentModifier để che token/PII trong body.
5. Dùng modifyUris() để chuẩn hóa scheme, host và port của URI.
6. Dùng maskLinks() cho hypermedia href cần che; giữ link relations.
7. Dùng synthetic values cho query parameters; nếu cần, viết custom request URI preprocessor.
8. Sinh tất cả snippets và assemble Markdown/Asciidoctor.
9. Scan generated snippets, final docs và rendered HTML.
10. Cố ý bỏ từng preprocessor để xác nhận sentinel check phát hiện rò rỉ.
11. Chạy clean CI build và chỉ publish khi mọi gate pass.

**Tiêu chí hoàn thành:** tài liệu giữ được method/path, headers và body contract cần thiết; token/cookie/API key được thay hoặc loại đúng vùng; host nội bộ được chuẩn hóa; hypermedia href được mask đúng phạm vi; query secrets không lọt; mọi generated output được scan và CI chặn publish khi có rò rỉ.

## Tài liệu tham khảo

- [Spring REST Docs — Preprocessing](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/preprocessors.html)
- [Spring REST Docs — Preprocessors API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/Preprocessors.html)
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP — Information Exposure Through Query Strings in URL](https://owasp.org/www-community/vulnerabilities/Information_exposure_through_query_strings_in_url)
