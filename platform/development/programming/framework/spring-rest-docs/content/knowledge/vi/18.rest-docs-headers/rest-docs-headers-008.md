# Header không nên đưa nguyên giá trị nhạy cảm vào tài liệu

Spring REST Docs ghi nhận request và response để tạo các snippet như `http-request.adoc`, `http-response.adoc`, `curl-request.adoc` và `httpie-request.adoc`. Những file này hữu ích cho người tích hợp API, nhưng cũng có thể đưa dữ liệu nhạy cảm vào tài liệu nếu test gửi hoặc nhận giá trị thật. Header Authorization có thể chứa bearer token; Set-Cookie có thể mang session identifier; header nội bộ có thể tiết lộ tenant, định danh cá nhân hoặc thông tin vận hành.

Vì vậy, **không đưa nguyên giá trị nhạy cảm vào tài liệu hoặc artifact công khai**. Hãy dùng fixture giả, placeholder có chủ đích, preprocessor phù hợp và bước review output. Việc che dữ liệu phải được làm có kiểm soát để bảo vệ thông tin mà vẫn giữ được ý nghĩa cần thiết của ví dụ HTTP.

Bài học thuộc chương **Headers** của module `SPRING_REST_DOCS`. Module tạo tài liệu REST API có thể kiểm chứng từ test HTTP bằng MockMvc, WebTestClient hoặc REST Assured, sinh snippet cho request, response, payload, tham số và header, rồi biên soạn Asciidoctor/Markdown và tích hợp build, CI. Bài này tập trung nhận diện header nhạy cảm, chiến lược không ghi dữ liệu thật, làm sạch output và kiểm tra rò rỉ qua snippet.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện header chứa credential, session, dữ liệu cá nhân và thông tin nội bộ.
2. Giải thích vì sao raw HTTP snippet có thể làm lộ giá trị dù bảng descriptor không liệt kê header.
3. Phân biệt dữ liệu cần loại bỏ, dữ liệu có thể thay placeholder và metadata có thể giữ lại.
4. Thiết kế test fixture an toàn thay cho secret thật.
5. Dùng preprocessor Spring REST Docs để loại bỏ hoặc thay giá trị header trong snippet.
6. Kiểm tra request, response, cURL, HTTPie và artifact đã render.
7. Đưa kiểm soát dữ liệu nhạy cảm vào review và CI.

## 2. Vì sao header nhạy cảm dễ lọt vào tài liệu?

Một test gửi request, nhận response rồi gọi `document(...)`. Raw snippet có thể chứa request line, header và body đã ghi nhận. Ví dụ:

```http
GET /api/profile HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOi...
Cookie: SESSION=8f4...
X-Internal-User: user-1042
Accept: application/json
```

Ngay cả khi `requestHeaders(...)` chỉ mô tả `Accept`, raw `http-request.adoc` vẫn có thể hiển thị các header khác. **Bảng descriptor và raw HTTP snippet có mục đích khác nhau**: descriptor chọn header cần giải thích; raw snippet có thể thể hiện toàn bộ message.

Rủi ro cũng xuất hiện trong `http-response.adoc` (Set-Cookie, token refresh), `curl-request.adoc` và `httpie-request.adoc` (lệnh có credential), body snippets (dữ liệu cá nhân), bảng descriptor và bản HTML/PDF/site. Không giả định header không có trong bảng mô tả sẽ tự động biến mất khỏi raw snippet.

## 3. Nhận diện nhóm header cần bảo vệ

| Header hoặc nhóm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| `Authorization` | Bearer token, Basic credential hoặc scheme khác | Không dùng giá trị thật; thay placeholder |
| `Proxy-Authorization` | Credential gửi tới proxy | Không công bố |
| `Cookie` | Session ID, trạng thái đăng nhập | Loại bỏ hoặc thay placeholder |
| `Set-Cookie` | Session token, refresh token, cookie flags | Không đưa cookie thật vào ví dụ |
| API key như `X-API-Key` | Khóa truy cập dịch vụ | Dùng placeholder giả |
| CSRF header/token | Token gắn với session | Chỉ dùng giá trị giả |
| Header chứa email/user ID/tenant | Dữ liệu cá nhân hoặc định danh | Ẩn danh hóa hoặc dùng dữ liệu giả |
| Header trace/debug nội bộ | Hostname, topology hoặc metadata vận hành | Chỉ giữ phần cần thiết đã được đánh giá |
| Request/correlation ID | Có thể liên kết tới log nội bộ | Dùng ID mẫu, không dùng ID thật |
| `Content-Type`, `Accept` | Thường không phải secret | Có thể giữ nếu không lộ ngữ cảnh riêng |

Secret và dữ liệu cá nhân không giống nhau. Credential có thể dùng để truy cập hệ thống; dữ liệu cá nhân có thể không đăng nhập được nhưng vẫn không nên công bố. Metadata vận hành đôi khi không phải secret nhưng có thể tiết lộ cấu trúc hệ thống. Do đó, kiểm tra không chỉ tìm chuỗi có dạng token.

### 3.1. Phân loại cách xử lý

- **Giữ nguyên:** chỉ khi giá trị thuộc hợp đồng công khai và an toàn, ví dụ `Content-Type: application/json`.
- **Thay bằng placeholder:** cần thể hiện vị trí/format nhưng không cần giá trị thật, ví dụ `Authorization: Bearer <access-token>`.
- **Ẩn một phần:** chỉ khi phần còn lại không thể dùng để nhận diện/truy cập và vẫn có ích.
- **Loại bỏ:** header nội bộ không cần cho client hoặc có nguy cơ tiết lộ.
- **Không tạo dữ liệu nhạy cảm ngay từ đầu:** ưu tiên fixture giả để secret thật không đi vào message được ghi nhận.

## 4. Ưu tiên fixture giả từ đầu

Biện pháp an toàn nhất là không đưa secret thật vào documentation test. Nếu test cần xác thực để qua security filter, dùng token giả chỉ hợp lệ trong môi trường test.

```http
GET /api/orders/501 HTTP/1.1
Authorization: Bearer docs-test-token
Accept: application/json
```

Hoặc trong phần hướng dẫn cho người đọc:

```http
GET /api/orders/501 HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json
```

`docs-test-token` phải là giá trị giả, không có quyền truy cập môi trường thật. Placeholder chỉ diễn tả vị trí client cần cung cấp credential của chính họ.

Không đọc secret production từ biến môi trường để đưa vào request tài liệu hóa:

```java
String token = System.getenv("PRODUCTION_ACCESS_TOKEN");
mockMvc.perform(
    get("/api/profile").header("Authorization", "Bearer " + token)
);
```

Cách này có nguy cơ ghi credential vào snippet, báo cáo test hoặc log. Hãy dùng test principal, mock authentication hoặc token được ký bằng khóa riêng của test environment.

Nếu test chỉ xác nhận request thiếu token trả `401`, không cần gửi Authorization. Nếu cần minh họa request có token, dùng token giả hoặc placeholder. Có thể có hai operation riêng: `orders-get-unauthenticated` và `orders-get-authenticated`.

## 5. Preprocessors của Spring REST Docs

Spring REST Docs hỗ trợ operation preprocessors để thay đổi request/response được ghi thành snippet. Các API thường dùng trong `org.springframework.restdocs.operation.preprocess.Preprocessors` gồm:

- `preprocessRequest(...)` và `preprocessResponse(...)`: áp dụng processor cho message.
- `removeHeaders(...)`: loại header không muốn xuất hiện trong snippet.
- `modifyHeaders()`: thay đổi header trong bản ghi.
- `replacePattern(...)`: thay phần nội dung khớp regular expression.
- `prettyPrint()`: định dạng payload cho dễ đọc.

Hãy chọn cách xử lý theo mục tiêu: loại header không cần cho client; thay giá trị nếu tên header thuộc hợp đồng nhưng giá trị thật nhạy cảm.

### 5.1. Loại bỏ header không cần công khai

Ví dụ loại bỏ Cookie và header nội bộ khỏi request snippet:

```java
.andDo(document("profile-get",
    preprocessRequest(
        removeHeaders("Cookie", "X-Internal-User")
    )
));
```

Nếu response có Set-Cookie không cần hiển thị:

```java
.andDo(document("login-success",
    preprocessResponse(
        removeHeaders("Set-Cookie")
    )
));
```

Đây là thao tác trên **bản message được ghi thành snippet**. Nó không xóa header khỏi request/response thật và không sửa rò rỉ trong implementation. Assertion vẫn phải kiểm tra message thực tế.

### 5.2. Thay Authorization bằng placeholder

Nếu header thuộc contract và cần hiện trong ví dụ:

```java
.andDo(document("orders-get-authenticated",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .build()
    )
));
```

Cú pháp builder cần khớp phiên bản Spring REST Docs trong dự án. Assertion security vẫn chạy trên request gửi token giả ban đầu; preprocessor chỉ thay message dùng để ghi snippet. Không để giá trị placeholder vô tình bị xử lý như AsciiDoc markup; kiểm tra output cuối.

### 5.3. Chuẩn hóa correlation ID động

Nếu ID thay đổi mỗi lần chạy nhưng tài liệu chỉ cần cho thấy header:

```java
.andDo(document("orders-get",
    preprocessResponse(
        modifyHeaders()
            .set("X-Correlation-Id", "docs-correlation-id")
            .build()
    )
));
```

Test vẫn cần assertion rằng response có ID hoặc đáp ứng format hợp đồng. Snippet dùng một giá trị mẫu ổn định. Nếu format là một phần hợp đồng, hãy dùng giá trị giả có format đúng, chẳng hạn UUID mẫu.

### 5.4. Dùng replacePattern có giới hạn

`replacePattern(...)` hữu ích khi chuỗi nhạy cảm xuất hiện trong giá trị header hoặc message. Ví dụ URI callback chứa query parameter tạm thời. Regex phải giới hạn đúng phạm vi; biểu thức quá rộng có thể thay nhầm dữ liệu hợp lệ hoặc khiến snippet không còn đại diện cho request. Sau khi chạy test, đọc file snippet để xác nhận thay thế đúng.

## 6. Che giá trị khác với xóa header

| Phương án | Kết quả snippet | Khi phù hợp |
| --- | --- | --- |
| Remove header | Header biến mất khỏi raw message | Header nội bộ không cần hướng dẫn client |
| Replace value | Giữ tên header, thay bằng placeholder | Header thuộc contract nhưng giá trị thật không công bố |
| Mask một phần | Giữ format tổng quát, che phần nhạy cảm | Khi format quan trọng và phần còn lại an toàn |
| Dùng fixture giả | Message chỉ chứa dữ liệu thử nghiệm | Lựa chọn ưu tiên |
| Không tạo descriptor | Không có bảng mô tả riêng | Không phải biện pháp bảo mật |

**Không khai báo `requestHeaders(...)` hoặc `responseHeaders(...)` không có nghĩa header bị ẩn.** Descriptor quyết định bảng mô tả; fixture/preprocessor quyết định raw snippet ghi giá trị nào. Xóa header khỏi bảng nhưng giữ nó trong `http-request.adoc` vẫn có thể làm lộ credential.

## 7. Ví dụ end-to-end với MockMvc

Giả sử `GET /api/profile` yêu cầu Bearer token giả và trả correlation ID. Test dùng security setup của ứng dụng, nhưng snippet không chứa token test:

```java
@Test
void getProfile_documentsSafeHeaders() throws Exception {
    mockMvc.perform(
            get("/api/profile")
                .header("Authorization", "Bearer docs-test-token")
                .header("X-Correlation-Id", "test-flow-001")
                .accept(MediaType.APPLICATION_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(header().exists("X-Correlation-Id"))
        .andDo(document("profile-get-success",
            preprocessRequest(
                modifyHeaders()
                    .set("Authorization", "Bearer <access-token>")
                    .set("X-Correlation-Id", "docs-correlation-id")
                    .build()
            ),
            preprocessResponse(
                removeHeaders("Set-Cookie", "X-Internal-Trace")
            ),
            requestHeaders(
                headerWithName("Authorization")
                    .description("Bearer access token của client"),
                headerWithName("X-Correlation-Id")
                    .description("Mã tương quan client có thể cung cấp")
            ),
            responseHeaders(
                headerWithName("X-Correlation-Id")
                    .description("Mã dùng để truy vết lần xử lý")
            )
        ));
}
```

Đây là ví dụ ghép descriptor và preprocessor; cần đối chiếu imports/API builder với phiên bản Spring REST Docs dự án. Test phải có security filter chain nếu muốn chứng minh xác thực. `docs-test-token` là fixture giả, không có quyền ở môi trường thật.

### 7.1. Assertion phải kiểm tra message thật

Preprocessor chỉ tác động tới bản ghi snippet. Test cần assertion trên request/response thực tế:

```java
.andExpect(status().isOk())
.andExpect(header().exists("X-Correlation-Id"))
.andExpect(jsonPath("$.id").value("profile-demo"))
```

Nếu hợp đồng yêu cầu server trả lại đúng ID client gửi, kiểm tra equality. Nếu server tạo ID mới, kiểm tra header và format phù hợp. Không coi giá trị placeholder sau preprocessing là bằng chứng server trả chính giá trị đó.

### 7.2. Kiểm tra tất cả snippet được sinh

```text
target/generated-snippets/profile-get-success/
├── http-request.adoc
├── http-response.adoc
├── curl-request.adoc
├── httpie-request.adoc
├── request-headers.adoc
└── response-headers.adoc
```

Danh sách file phụ thuộc descriptor. Khi review, xác nhận Authorization chỉ còn placeholder hoặc đã bị loại; Cookie/Set-Cookie không chứa session thật; correlation ID là giá trị giả ổn định; không có header nội bộ ngoài ý muốn; cURL và HTTPie cũng đã được xử lý.

## 8. Đừng quên các snippet dẫn xuất

| File | Điều cần rà soát |
| --- | --- |
| `http-request.adoc` | Authorization, Cookie, API key, header định danh |
| `curl-request.adoc` | Token/cookie có thể copy-paste |
| `httpie-request.adoc` | Credential nhúng trong command |
| `http-response.adoc` | Set-Cookie, refresh token, trace header |
| `request-headers.adoc` / `response-headers.adoc` | Descriptor vô tình chứa giá trị nhạy cảm |
| Body snippets | Dữ liệu cá nhân hoặc credential nằm trong JSON/XML |

Nếu có snippet tùy chỉnh hoặc pipeline chuyển Markdown, thêm chúng vào danh sách kiểm tra. Bản HTML/PDF cuối cũng có thể giữ giá trị đã xuất hiện trong snippet.

## 9. Viết mô tả header an toàn

Không đưa token vào description:

```java
headerWithName("Authorization")
    .description("Bearer access token do cơ chế xác thực cấp cho client")
```

Không đưa tenant thật hoặc tên khách hàng vào mô tả:

```java
headerWithName("X-Tenant-Id")
    .description("Mã tenant mà client được phép thao tác")
```

Descriptor cũng được lưu vào snippet và có thể xuất bản, vì vậy cần áp dụng nguyên tắc bảo vệ dữ liệu như với raw message.

## 10. Kiểm tra bảo mật trong CI

Pipeline có thể thực hiện:

```text
Clean build output
       │
       ▼
Run documentation tests with fake credentials
       │
       ▼
Generate request/response snippets
       │
       ▼
Scan snippets for known secrets / forbidden patterns
       │
       ▼
Render Asciidoctor / Markdown
       │
       ▼
Review HTML/PDF and generated artifacts
       │
       ▼
Publish
```

Các kiểm tra hữu ích:

1. Quét giá trị secret đã biết hoặc pattern credential được tổ chức sử dụng.
2. Rà soát Authorization, Cookie, Set-Cookie, API key và trace/debug header.
3. Kiểm tra snippet raw, bảng descriptor, cURL và HTTPie.
4. Kiểm tra output đã render vì conversion có thể copy nội dung sang HTML/PDF.
5. Chỉ publish sau khi scan và review đạt.

Pattern scan không thể nhận diện mọi secret hoặc dữ liệu cá nhân. Đây là lớp phòng thủ bổ sung, không thay thế fixture an toàn và review output.

### 10.1. Nếu credential thật đã bị commit hoặc publish

Hãy xử lý như một sự cố lộ credential: dừng publish, xác định phạm vi file/artifact đã lộ, thu hồi hoặc rotate credential nếu còn hiệu lực, xóa/thay giá trị trong source/snippet/artifact theo quy trình tổ chức, kiểm tra lịch sử commit và CI logs, rồi bổ sung kiểm soát để không tái diễn. Chỉ xóa token khỏi file mới nhất không thu hồi một credential đã phát hành.

## 11. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Bảng header không nhắc token nhưng raw request có token | Chỉ bỏ descriptor, không làm sạch raw snippet | Fixture giả và request preprocessor |
| Token test xuất hiện trong cURL | Chỉ kiểm tra http-request | Rà soát mọi snippet dẫn xuất |
| Set-Cookie còn trong response snippet | Chưa xử lý response header | Response preprocessor hoặc fixture an toàn |
| Placeholder làm test auth thất bại | Nhầm preprocessor với request gửi server | Giữ assertion trên message thực; thay chỉ ở snippet |
| Header biến mất nhưng client cần biết | Dùng remove thay vì replace | Giữ tên header, thay giá trị bằng placeholder |
| Correlation ID thay đổi mỗi build | Giá trị động ghi nguyên trạng | ID cố định hoặc preprocessor |
| Header nội bộ vẫn xuất hiện | Chỉ loại khỏi descriptor | Làm sạch raw snippet và xem xét implementation |
| Regex thay nhầm giá trị | Pattern quá rộng | Giới hạn regex và test output |
| CI scan pass nhưng secret vẫn lọt | Pattern không bao phủ mọi dạng dữ liệu | Kết hợp fixture, review và kiểm tra artifact |
| HTML/PDF vẫn chứa token | Artifact cũ hoặc chưa render lại | Clean, tạo lại và scan artifact mới |

## 12. Bài thực hành

Tài liệu hóa `GET /api/accounts/me`. API yêu cầu Bearer token, nhận correlation ID tùy chọn và response middleware có thể có `Set-Cookie`.

**Nhiệm vụ:**

1. Tạo test security dùng token giả chỉ có quyền trong test.
2. Gửi `Authorization: Bearer docs-test-token` và `X-Correlation-Id: docs-flow-001`.
3. Assert hành vi xác thực và response theo contract.
4. Dùng `requestHeaders(...)` mô tả Authorization và correlation ID bằng lời, không ghi token vào description.
5. Dùng request preprocessor thay Authorization bằng `Bearer <access-token>` và chuẩn hóa correlation ID.
6. Dùng response preprocessor loại Set-Cookie nếu cookie không thuộc ví dụ public.
7. Sinh request, response, cURL, HTTPie và header snippets.
8. Tìm giá trị fixture gốc trong toàn bộ output; xác nhận token không xuất hiện.
9. Render HTML/PDF và rà soát artifact.
10. Thêm bước scan/validation tương ứng vào CI.

**Tiêu chí hoàn thành:** test vẫn kiểm tra request/response thực bằng fixture giả; snippet chỉ có placeholder an toàn hoặc không có header không cần thiết; không có credential thật trong raw snippets, bảng hoặc tài liệu đã render; pipeline có thể tái tạo và kiểm tra output.

## 13. Ghi nhớ

- Raw HTTP snippets có thể ghi header dù header đó không xuất hiện trong `requestHeaders(...)` hoặc `responseHeaders(...)`.
- Không dùng token, cookie, API key hoặc credential thật trong documentation tests; ưu tiên fixture giả ngay từ đầu.
- `removeHeaders(...)` loại header khỏi snippet; `modifyHeaders()` có thể thay giá trị bằng placeholder; `prettyPrint()` chỉ định dạng message.
- Preprocessor thay đổi bản message dùng để ghi snippet, không thay thế assertion trên request/response thực tế.
- Rà soát http-request, http-response, cURL, HTTPie, bảng header và HTML/PDF sau render.
- CI scan là lớp hỗ trợ; fixture an toàn, review và kiểm soát artifact vẫn cần thiết.
- Nếu credential thật đã lộ, xử lý như sự cố bảo mật và rotate/thu hồi credential khi thích hợp.
