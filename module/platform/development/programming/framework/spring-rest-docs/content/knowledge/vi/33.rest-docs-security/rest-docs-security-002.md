# Masking links có tham số nhạy cảm

## 1. Mục tiêu và bối cảnh

REST API có thể trả về hypermedia links hoặc callback URLs chứa query parameters. Một số giá trị là dữ liệu công khai như page, size, sort; một số khác có thể là authorization code, signed URL, reset token, invitation token, session reference hoặc dữ liệu cá nhân. Nếu Spring REST Docs ghi nguyên response vào snippet, các giá trị nhạy cảm có thể xuất hiện trong tài liệu được commit hoặc publish.

Spring REST Docs cung cấp preprocessor **maskLinks** để che href của hypermedia links trong request/response content. Cần phân biệt việc đó với che mọi query parameter trong request URI. **replacePattern** thay nội dung request/response; **modifyUris** thay scheme, host và port. Khi cần ẩn query parameter của request URI, hãy dùng dữ liệu test giả hoặc custom request preprocessor.

Bài học thuộc chương **Bảo mật** của module **SPRING_REST_DOCS**. Module tạo tài liệu REST API có thể kiểm chứng từ HTTP tests bằng MockMvc, WebTestClient hoặc REST Assured; sinh snippet cho request, response, payload, tham số và header; biên soạn Asciidoctor/Markdown và tích hợp build/CI.

Sau bài học, bạn có thể nhận diện query parameters nhạy cảm; dùng maskLinks cho hypermedia href; phân biệt maskLinks, replacePattern và modifyUris; chọn synthetic values; viết custom OperationRequestPreprocessor khi cần; kiểm tra mọi snippets và đưa leak checks vào CI.

## 2. Các vị trí cần xem xét

Ví dụ response hypermedia:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/42"
    },
    "payment": {
      "href": "https://pay.example.test/checkout?order=42&state=opaque-state"
    }
  }
}
~~~

Các nhóm thường gặp:

| Vị trí | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Hypermedia href | _links.payment.href | maskLinks hoặc custom content transform. |
| Request query | access_token=... | Synthetic value hoặc custom request preprocessor. |
| Callback URL | code=...&state=... | Authorization code giả, mask nếu cần. |
| Signed URL | X-Amz-Signature=... | Không publish URL còn hiệu lực. |
| Reset/invitation link | token=... | Không publish token có thể sử dụng. |
| Pagination | page=0&size=20 | Thường giữ để mô tả contract. |
| Filter/sort | status=PAID&sort=createdAt | Giữ nếu không chứa PII/secret. |

Không phải mọi query parameter đều nhạy cảm. Che quá mức làm ví dụ mất giá trị; che thiếu có thể công bố credential có thể sử dụng.

## 3. maskLinks: che href của hypermedia links

Spring REST Docs cung cấp Preprocessors.maskLinks() và overload nhận chuỗi thay thế. Preprocessor tìm hypermedia links trong request/response content và thay href bằng giá trị mask.

Response trước khi mask:

~~~json
{
  "_links": {
    "self": {
      "href": "https://internal.example.test/orders/42"
    },
    "cancel": {
      "href": "https://internal.example.test/orders/42/cancel?ticket=private-value"
    }
  }
}
~~~

Áp dụng cho response:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.maskLinks;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

.andDo(document("orders-get",
    preprocessResponse(maskLinks())
));
~~~

Dùng placeholder tùy chỉnh:

~~~java
.andDo(document("orders-get",
    preprocessResponse(maskLinks("[LINK]"))
));
~~~

Các link relations vẫn có thể được mô tả bằng link descriptors:

~~~java
.andDo(document("orders-get",
    links(
        linkWithRel("self").description("Đơn hàng hiện tại"),
        linkWithRel("cancel").description("Link hủy đơn hàng nếu được phép")
    ),
    preprocessResponse(maskLinks())
));
~~~

Cấu hình links snippet và response preprocessing phải dùng đúng static imports của dự án. Mục tiêu là giữ ý nghĩa rel nhưng không công bố href có token hoặc host nội bộ.

## 4. maskLinks không che mọi URL

maskLinks xử lý href của hypermedia links được nhận diện trong request/response content. Nó không phải bộ lọc tổng quát cho mọi query string trong request URI, mọi URL trong text hoặc log, hay custom JSON fields không được nhận diện là hypermedia links.

Ví dụ request line:

~~~http
GET /oauth/callback?code=authorization-code-secret&state=opaque-state HTTP/1.1
~~~

Đây là request URI của operation, không phải href trong response HAL. Chỉ gắn maskLinks vào response không che query string này.

Tương tự, JSON field redirectUrl dạng string thuần có thể không được xử lý như hypermedia link. Nếu field chứa signed URL, phải dùng fixture giả hoặc xử lý content phù hợp.

## 5. Phân biệt các preprocessors

| Preprocessor | Phạm vi chính | Không nên giả định |
| --- | --- | --- |
| maskLinks() | Href của hypermedia links trong content | Không che mọi query string của request URI. |
| replacePattern(pattern, replacement) | Thay pattern trong request/response content | Không mặc định sửa URI object. |
| modifyUris() | Thay scheme, host và port | Không xóa query parameter hoặc path segment. |
| modifyHeaders() | Thêm, set hoặc remove headers | Không che URL trong request line/body. |
| Custom OperationPreprocessor | Logic tùy biến trên request/response operation | Phải test output và giữ đúng contract. |

modifyUris hữu ích khi test chạy trên localhost/random port nhưng docs cần host chuẩn. API này tập trung scheme, host và port; không dùng nó để mask query parameters.

replacePattern hữu ích cho body text, ví dụ redirectUrl trong JSON, nhưng API mô tả nó là cơ chế thay content. Khi cần sửa request URI được lưu riêng trong operation, hãy dùng synthetic query values hoặc custom request preprocessor.

## 6. Ưu tiên synthetic query values

Cách đơn giản và an toàn nhất là documentation test dùng giá trị giả không có hiệu lực:

~~~java
mockMvc.perform(get("/oauth/callback")
        .queryParam("code", "DOCS_AUTH_CODE")
        .queryParam("state", "DOCS_STATE"))
    .andExpect(status().isOk())
    .andDo(document("oauth-callback"));
~~~

Chỉ dùng cách này nếu endpoint chấp nhận test fixture và không gọi hệ thống xác thực thật. DOCS_AUTH_CODE phải được tạo riêng cho test, không phải code lấy từ OAuth provider.

Với signed URL, không dùng chữ ký thật để tạo snippet. Mock service trả URL giả hoặc fixture hết hiệu lực. Tài liệu vẫn thể hiện tên query parameters và hình dạng URL mà không có credential có thể tái sử dụng.

Nếu query parameter là một phần contract, giữ tên và mô tả ý nghĩa, chỉ thay value:

~~~text
?page=0&size=20&status=PAID&access_token=[REDACTED]
~~~

Giữ pagination/filter để tài liệu hữu ích. Với state, xác minh semantics: nó có thể là secret/correlation value hoặc trạng thái nghiệp vụ công khai.

## 7. Custom request preprocessor cho query URI

Nếu URI được tạo với giá trị động không thể thay ở test fixture, có thể viết OperationRequestPreprocessor để tạo request documentation đã sanitize.

Các bước:

1. Nhận OperationRequest trước khi REST Docs render snippets.
2. Đọc URI và parse query parameters.
3. Giữ nguyên các key công khai theo allowlist.
4. Thay value của key nhạy cảm như code, token, state, signature.
5. Tạo OperationRequest mới với URI đã xử lý, giữ method, headers, body và request parts.
6. Trả request mới cho bước documentation.

Pseudo-code minh họa, không phải implementation copy/paste:

~~~java
OperationRequestPreprocessor redactQueryParameters =
    request -> {
        URI original = request.getUri();
        URI sanitized = redactSensitiveQueryValues(original);

        // Tạo OperationRequest mới bằng API/factory của version đang dùng.
        // Giữ method, headers, content, multipart parts và cookies.
        return createSanitizedRequest(request, sanitized);
    };
~~~

redactSensitiveQueryValues và createSanitizedRequest là helper do ứng dụng tự triển khai. Không có built-in preprocessor chung được mô tả ở trên bảo đảm xóa tùy ý query parameter khỏi request URI.

Khi triển khai thật, kiểm tra API OperationRequest và OperationRequestFactory của đúng version Spring REST Docs. Bảo toàn percent-encoding, duplicate query keys, parameter không có value, thứ tự nếu cần và URI fragment. Tránh nối chuỗi query bằng replace đơn giản vì có thể làm hỏng encoding.

### 7.1. Chỉ mask key nhạy cảm

Ví dụ đầu vào:

~~~text
?page=0&size=20&status=PAID&access_token=secret
~~~

Kết quả mong muốn:

~~~text
?page=0&size=20&status=PAID&access_token=[REDACTED]
~~~

Giữ pagination/filter. Với state, xác minh semantics trước khi mask.

## 8. URL trong response body

Response có thể chứa URL ở field thường:

~~~json
{
  "redirectUrl": "https://pay.example.test/checkout?session=private-session&order=42",
  "expiresIn": 300
}
~~~

Nếu URL là string JSON chứ không phải hypermedia href, maskLinks có thể không nhận diện. Có thể dùng fixture giả, replacePattern trên response content hoặc custom content modifier hiểu cấu trúc JSON.

~~~java
Pattern sensitiveSession =
    Pattern.compile("session=[^&\"\\s]+");

.andDo(document("payment-session",
    preprocessResponse(
        replacePattern(sensitiveSession, "session=[REDACTED]")
    )
));
~~~

Pattern minh họa có thể thay session query value trong JSON string hoặc text response. Cần test escaping và URL encoding. Với JSON phức tạp, parse JSON rồi thay đúng property thường rõ ràng hơn regex tổng quát.

## 9. Chuẩn hóa host/path trong môi trường test

modifyUris có thể chuẩn hóa scheme, host và port:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

.andDo(document("orders-get",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
    )
));
~~~

Preprocessor này không xóa query parameters và không thay path segment. Nếu path chứa reset token hoặc customer identifier nhạy cảm, hãy dùng fixture giả hoặc custom request preprocessor.

## 10. Áp dụng cho các HTTP test clients

### 10.1. MockMvc

~~~java
mockMvc.perform(get("/oauth/callback")
        .queryParam("code", "DOCS_AUTH_CODE")
        .queryParam("state", "DOCS_STATE"))
    .andExpect(status().isOk())
    .andDo(document("oauth-callback",
        preprocessResponse(maskLinks("[LINK]"))
    ));
~~~

Response hypermedia href được mask; request query values an toàn vì dùng fixture giả. Nếu test dùng query value thật, cần xử lý URI riêng.

### 10.2. WebTestClient

~~~java
webTestClient.get()
    .uri(uriBuilder -> uriBuilder
        .path("/oauth/callback")
        .queryParam("code", "DOCS_AUTH_CODE")
        .queryParam("state", "DOCS_STATE")
        .build())
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("oauth-callback-webflux",
        preprocessResponse(maskLinks())
    ));
~~~

Dùng test values không có hiệu lực. Nếu response chứa signed hypermedia href, mask chúng trước khi ghi snippet hoặc dùng response fixture không có signature thật.

### 10.3. REST Assured

~~~java
given(specification)
    .queryParam("code", "DOCS_AUTH_CODE")
    .queryParam("state", "DOCS_STATE")
    .filter(document("oauth-callback-restassured",
        preprocessResponse(maskLinks())
    ))
.when()
    .get("/oauth/callback")
.then()
    .statusCode(200);
~~~

Specification cần cấu hình server/base URI, port và REST Docs context. Không lấy callback URL hoặc authorization code từ OAuth flow đang hoạt động để làm sample.

## 11. Kiểm thử kết quả masking

Dùng sentinel riêng để xác minh không có giá trị nhạy cảm trong generated snippets:

~~~java
private static final String SECRET_QUERY_VALUE =
    "DOCS_ONLY_QUERY_SECRET_4c91";
~~~

Sau khi test sinh snippets, scan toàn bộ output directory và trang assemble:

~~~java
assertThat(allGeneratedDocumentation)
    .doesNotContain(SECRET_QUERY_VALUE)
    .doesNotContain("session=private-session");
~~~

Kiểm tra cả http-request, curl-request, httpie-request, query parameter snippets, custom request snippets, assembled Markdown/Asciidoctor và rendered HTML.

Với hypermedia response, xác minh href đã mask và relation descriptors vẫn còn. Với query URI, xác minh public keys còn nguyên và secret value đã được thay.

## 12. CI: chặn query/link secret trước publish

~~~mermaid
flowchart TD
    A["HTTP tests với synthetic URL values"] --> B["Apply maskLinks / custom preprocessor"]
    B --> C["Generate all snippets"]
    C --> D["Assemble API documentation"]
    D --> E["Scan sentinels and signed URL patterns"]
    E --> F{"Sensitive value found?"}
    F -->|Yes| X["Fail CI"]
    F -->|No| G["Render docs and validate links"]
    G --> H{"Render checks pass?"}
    H -->|No| X
    H -->|Yes| I["Publish"]
~~~

CI nên:
1. Dùng synthetic query values và URL fixtures.
2. Gắn maskLinks cho hypermedia links cần che.
3. Dùng custom request preprocessor nếu query trong request URI cần thay.
4. Scan generated snippets và assembled docs bằng sentinel.
5. Kiểm tra curl/HTTPie, body snippets và rendered HTML.
6. Fail build nếu signed URL/token thật xuất hiện.
7. Không in nguyên secret vào log.
8. Chỉ publish sau khi scan và render pass.

Nếu URL có chữ ký thật đã được commit/publish, cần revoke credential hoặc tạo lại signed URL theo policy. Xóa file khỏi workspace không thu hồi chữ ký hay xóa CI artifacts/Git history.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Hypermedia href vẫn lộ | maskLinks không gắn vào response operation | Kiểm tra response preprocessor và output. |
| Query token trong request line còn | maskLinks không xử lý request URI tổng quát | Synthetic value hoặc custom request preprocessor. |
| replacePattern không đổi URI | Nó thay content, không phải URI object nói chung | Xử lý request URI riêng. |
| modifyUris không che query | Nó thay scheme/host/port | Mask query theo key bằng cách phù hợp. |
| redirectUrl trong JSON vẫn lộ | Field string không phải hypermedia link | Fixture giả, body replacement hoặc JSON modifier. |
| Public parameters biến mất | Mask toàn bộ query string | Chỉ thay value của key nhạy cảm. |
| URL hỏng sau regex | Percent-encoding/duplicate keys không được giữ | Parse URI/query đúng chuẩn. |
| Request snippet sạch nhưng curl lộ | Chỉ kiểm tra một file | Scan toàn bộ operation output. |
| Local sạch, CI có secret | Fixture/credential CI khác | Synthetic data và cùng preprocessing. |
| Link relation mất ý nghĩa | Che toàn bộ link object | Chỉ mask href, giữ rel và description. |

## 14. Bài thực hành

Tạo API giả định:

- GET /api/orders trả _links.self, _links.next và _links.payment.
- GET /oauth/callback nhận code và state.
- Response payment có redirectUrl chứa session query parameter.

Thực hiện:

1. Viết HTTP tests với URL/query values tổng hợp.
2. Áp dụng maskLinks cho hypermedia response.
3. Xác minh link descriptors vẫn mô tả rel dù href đã mask.
4. Kiểm tra request query dùng synthetic values.
5. Nếu phải thay request URI động, triển khai custom OperationRequestPreprocessor theo API version dự án.
6. Che session trong redirectUrl bằng fixture, body replacement hoặc JSON-aware modifier.
7. Kiểm tra HTTP, curl, HTTPie, query parameter snippets và response body.
8. Scan assembled docs và rendered HTML bằng sentinel.
9. Chạy CI clean build và fail nếu phát hiện secret.
10. Ghi rõ parameter nào public, parameter nào được thay placeholder.

**Tiêu chí hoàn thành:** phân biệt hypermedia href với request query URI; dùng maskLinks đúng phạm vi; không nhầm replacePattern/modifyUris là bộ lọc query tổng quát; giữ public parameters; che signed URL/token; và có CI leak check trước publish.

## Tài liệu tham khảo

- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [Spring REST Docs — Preprocessors API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/Preprocessors.html)
- [Spring REST Docs — OperationRequestPreprocessor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/OperationRequestPreprocessor.html)
- [OWASP — Information Exposure Through Query Strings in URL](https://owasp.org/www-community/vulnerabilities/Information_exposure_through_query_strings_in_url)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
