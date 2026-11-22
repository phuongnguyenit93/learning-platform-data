# Masking links để loại bỏ host hoặc token

HTTP snippet có thể chứa URL đầy đủ để người đọc hiểu hoặc thử lại request. Nhưng link được ghi nhận trong môi trường test có thể mang hostname nội bộ, random port, callback URL riêng hoặc token nằm trong query string. Response có thể trả header Location trỏ về máy test, hoặc body chứa liên kết xác thực tạm thời. Công bố nguyên những link này có thể làm lộ cấu trúc môi trường, tạo tài liệu khó tái sử dụng hoặc vô tình phát hành credential.

Trong Spring REST Docs, ta có thể **mask hoặc chuẩn hóa link trong bản message dùng để tạo snippet**. Với URI của request, `modifyUris()` có thể chuẩn hóa scheme, host và port. Với URL nằm trong header/body hoặc token nhúng trong query, có thể dùng `modifyHeaders()` hoặc `replacePattern(...)` để thay giá trị bằng mẫu an toàn. Những thay đổi này chỉ ảnh hưởng bản ghi tài liệu; request/response thực tế và assertion của test vẫn giữ nguyên.

Bài học thuộc chương **Preprocessors** của module `SPRING_REST_DOCS`. Module thực hành tạo tài liệu REST API có thể kiểm chứng từ test HTTP với MockMvc, WebTestClient hoặc REST Assured, sinh snippet request, response, payload, tham số và header, rồi biên soạn Asciidoctor/Markdown và tích hợp build, CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện host nội bộ, port ngẫu nhiên, callback URL và token nhúng trong link.
2. Phân biệt chuẩn hóa URI request với masking URL trong header/body.
3. Dùng `modifyUris()` để thay scheme/host/port trong request snippet.
4. Dùng `modifyHeaders()` và `replacePattern(...)` để làm sạch link hoặc token trong message.
5. Viết quy tắc thay thế có phạm vi hẹp, giữ path/query semantics cần công bố.
6. Kiểm tra assertion trên message thật và đọc lại mọi snippet dẫn xuất.
7. Tích hợp bước review link và secret vào build/CI.

## 2. Vì sao phải mask host hoặc token trong link?

Một URL có thể chứa nhiều thành phần:

```text
https://internal-api.example.local:53128/api/auth/callback
    ?tenant=tenant-test
    &access_token=eyJhbGciOi...
    &state=5f3c...
```

| Thành phần | Rủi ro hoặc ảnh hưởng | Cách xử lý trong tài liệu |
| --- | --- | --- |
| Scheme | Thể hiện cách client kết nối | Giữ đúng contract; chỉ thay khi cần URL canonical |
| Host | Tiết lộ hostname riêng hoặc không dùng được ngoài môi trường | Thay bằng domain tài liệu đã thống nhất |
| Port | Có thể là random port của test | Bỏ hoặc chuẩn hóa nếu không thuộc contract |
| Path | Thường mô tả endpoint và route | Giữ nguyên nếu là phần API contract |
| Query parameter thông thường | Có thể chứa tenant/filter/trạng thái nghiệp vụ | Giữ cấu trúc; dùng dữ liệu giả nếu riêng tư |
| Token/secret | Có thể cấp quyền hoặc cho phép tiếp tục flow xác thực | Xóa hoặc thay placeholder |
| Fragment | Có thể chứa state hoặc dữ liệu phía client | Kiểm tra trước khi công bố |

Không phải URL dài nào cũng nhạy cảm. Host có thể cần giữ nếu là domain public chính thức; query có thể là phần contract cần mô tả. Cần xác định phần nào người đọc phải hiểu và phần nào chỉ là dữ liệu môi trường/credential của test.

## 3. Xác định vị trí có link

| Vị trí | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Request URI | GET đến localhost và random port | Request URI preprocessor |
| Host header | localhost:53128 | Chuẩn hóa URI/host theo API |
| Response Location | http://app-node:8080/api/items/42 | Thay response header hoặc chuẩn hóa link |
| Response Link | URL trang next/prev | Giữ rel và path, thay host |
| JSON body | verificationUrl chứa token | Response body processor |
| HTML/text body | Link xác nhận hoặc callback | Thay đúng URL, giữ nội dung còn lại |

`modifyUris()` chủ yếu điều chỉnh URI request được ghi nhận. Không giả định nó sẽ tìm và thay mọi URL trong response body, Location hoặc Link. Với các vị trí đó, dùng processor phù hợp cho response/header/body và kiểm tra snippet đầu ra.

## 4. Chuẩn hóa request URI bằng modifyUris()

Khi request snippet ghi nhận localhost hoặc random port, `modifyUris()` giúp tạo URI ví dụ ổn định:

```java
.andDo(document("items-get",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
            .build()
    )
));
```

Trong snippet, scheme/host/port được điều chỉnh theo cấu hình. Path và query được giữ lại nếu không có processor khác chỉnh chúng.

Dùng host cố định khi test chạy local với random port, CI có hostname container khác, hoặc tài liệu public cần domain canonical. Chỉ dùng domain ví dụ đã được quy ước; nếu tài liệu phải copy chạy thật, dùng base URL công khai đã được xác nhận. Không tự suy diễn domain production.

### 4.1. Giữ path và API version

Chuẩn hóa host không được làm sai path, query hoặc API version. Ví dụ:

```http
GET https://api.example.test/v1/orders/42?expand=items HTTP/1.1
Accept: application/json
```

Path /v1/orders/42 và query expand=items vẫn là một phần contract. Không rút gọn chúng chỉ vì muốn URL trông gọn hơn.

## 5. Mask host trong response header

Các response header có thể chứa URL là Location, Link, Content-Location hoặc custom callback header. Ví dụ response thật:

```http
HTTP/1.1 201 Created
Location: http://orders-service.internal:8080/api/orders/42
Content-Type: application/json
```

Nếu tài liệu cần giữ Location nhưng thay host, có thể thay giá trị header trong response preprocessor:

```java
.andDo(document("orders-create",
    preprocessResponse(
        modifyHeaders()
            .set(
                "Location",
                "https://api.example.test/api/orders/42"
            )
            .build()
    ),
    responseHeaders(
        headerWithName("Location")
            .description("URI của đơn hàng vừa được tạo")
    )
));
```

Ví dụ dùng giá trị hoàn chỉnh đã biết. Nếu path có ID động, hãy dùng fixture xác định hoặc quy tắc thay hẹp; tránh hard-code ID mẫu khiến snippet không khớp với response test.

### 5.1. Header Link có nhiều URI

Header Link có thể chứa nhiều URL và tham số rel như next, prev, first hoặc last. Khi mask host, phải giữ dấu ngoặc góc, quan hệ và tham số. Thay toàn bộ header thành một URL có thể làm mất semantics phân trang.

Nếu cấu trúc phức tạp hoặc có nhiều URL động, dùng fixture xác định hoặc custom response preprocessor chuyên xử lý cú pháp Link thay vì regex bao quát. Kiểm tra output để xác nhận tất cả link hợp lệ.

## 6. Mask token trong query string

Token thường xuất hiện trong link xác thực, reset password, invitation hoặc callback:

```text
https://api.example.test/verify-email?token=eyJhbGciOiJIUzI1NiJ9.secret.signature
```

Không công bố token thật, kể cả khi token đã hết hạn. Dùng placeholder:

```text
https://api.example.test/verify-email?token=<verification-token>
```

Nếu token nằm trong response header, có thể thay giá trị bằng `modifyHeaders()`. Nếu token nằm trong body hoặc URI text, có thể dùng `replacePattern(...)` với pattern cụ thể.

Ví dụ khái niệm thay giá trị query parameter token trong response:

```java
.andDo(document("verification-link",
    preprocessResponse(
        replacePattern(
            Pattern.compile("([?&]token=)[^&\\s]+"),
            "$1<verification-token>"
        )
    )
));
```

Pattern thay giá trị của query key token tới trước dấu ampersand hoặc whitespace. Cần kiểm tra escaping, encoding và response thực tế; nếu token URL-encoded hoặc chứa ký tự phân cách đặc biệt, điều chỉnh pattern. Khi kiểm soát được fixture, ưu tiên tạo token giả an toàn ngay từ đầu.

### 6.1. Các query key khác cần rà soát

Không chỉ token. Link có thể chứa access_token, refresh_token, code, authorization_code, api_key, signature, state, nonce, ticket, session hoặc key. Xác định key nào có thể cấp quyền/định danh phiên rồi mask theo quy tắc đã thống nhất. Không thay mọi parameter chỉ vì tên chung chung nếu chúng thuộc contract và không nhạy cảm.

Các key như email, userId, tenantId hoặc invitee cũng cần đánh giá vì có thể tiết lộ dữ liệu cá nhân dù không phải credential. Dùng dữ liệu giả hoặc placeholder khi giá trị cụ thể không cần thiết cho ví dụ.

## 7. Dùng replacePattern có kiểm soát

`replacePattern(...)` hữu ích khi cùng pattern xuất hiện trong body hoặc raw message. Quy tắc tốt cần:

1. Giới hạn chính xác vị trí cần thay, chẳng hạn query key token.
2. Chỉ thay value, giữ tên parameter và các parameter lân cận.
3. Không làm hỏng URL encoding, dấu &, ?, fragment hoặc JSON.
4. Có test với token ngắn, dài và URL chứa nhiều query parameter.
5. Đọc snippet sau xử lý, không chỉ dựa vào việc test pass.

Ví dụ ý tưởng thay authority của một URL trong response text:

```java
.andDo(document("callback-info",
    preprocessResponse(
        replacePattern(
            Pattern.compile("https?://[^/\\s]+"),
            "https://api.example.test"
        )
    )
));
```

Pattern này chỉ minh họa URL authority đơn giản. URL có user-info, IPv6, port, nhiều dòng hoặc nhiều URL trong body cần xử lý thận trọng. Nếu thay host trong JSON, phải bảo đảm string replacement không làm hỏng escaping/cấu trúc JSON.

### 7.1. Khi regex không phù hợp

Regex đơn giản không phải URI parser. Khi message có nhiều URL, encoding phức tạp hoặc cú pháp Link nhiều phần, cân nhắc:

- Dùng fixture với URL giả đúng định dạng.
- Dùng `modifyHeaders()` khi chỉ thay một header.
- Viết custom preprocessor dùng API URI phù hợp.
- Tách operation nếu các trường hợp có semantics khác nhau.

Mục tiêu là thay đúng phần nhạy cảm mà không phá cú pháp hoặc ý nghĩa của link.

## 8. Ví dụ end-to-end với MockMvc

Giả sử endpoint tạo đơn hàng trả 201, Location có host nội bộ và body chứa link thanh toán với token test. Test dùng fixture giả; tài liệu cần domain ví dụ và placeholder:

```java
@Test
void createOrder_documentsSafeLinks() throws Exception {
    mockMvc.perform(
            post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"customerId":12,"productId":7,"quantity":2}
                    """)
        )
        .andExpect(status().isCreated())
        .andExpect(header().exists("Location"))
        .andExpect(jsonPath("$.paymentUrl").exists())
        .andDo(document("orders-create-success",
            preprocessResponse(
                modifyHeaders()
                    .set(
                        "Location",
                        "https://api.example.test/api/orders/42"
                    )
                    .build(),
                replacePattern(
                    Pattern.compile("([?&]token=)[^&\\s]+"),
                    "$1<payment-token>"
                )
            ),
            responseHeaders(
                headerWithName("Location")
                    .description("URI của đơn hàng vừa được tạo")
            ),
            responseFields(
                fieldWithPath("paymentUrl")
                    .description("Link thanh toán do API cung cấp")
            )
        ));
}
```

Đây là ví dụ minh họa; test cần fixture cho ID/link xác định và response thật tương ứng. Assertion phải kiểm tra response thực, chẳng hạn Location có đúng resource path và payment URL tuân theo contract. Preprocessor chỉ thay host/token trong snippet. Nếu ID thay đổi, dùng fixture xác định hoặc custom processor thay vì hard-code /42.

### 8.1. Kiểm tra file snippet

Sau test, xác minh:

- Location dùng domain tài liệu, không còn hostname nội bộ.
- Path và API version vẫn đúng.
- Query parameter token chỉ có placeholder.
- Các query parameter công khai khác vẫn hiện đúng.
- Body vẫn là JSON hợp lệ sau khi thay URL/token.
- response-headers.adoc mô tả semantics của Location.
- Không còn token trong snippet khác hoặc bản render.

## 9. Chọn preprocessor đúng phía

| Mục tiêu | Hướng xử lý | Lưu ý |
| --- | --- | --- |
| Host/port của request URI | `preprocessRequest(modifyUris()...)` | Chuẩn hóa URI request trong snippet |
| Authorization request header | Request header modifier | Giữ scheme, thay credential |
| Token trong request URI | Request processor phù hợp hoặc fixture giả | Không thay query parameter không liên quan |
| Location trong response | `preprocessResponse(modifyHeaders()...)` | Giữ path/semantics resource |
| Link trong response | Response processor hoặc custom processor | Bảo toàn rel và từng URI |
| URL trong JSON response | Response replacePattern hoặc custom processor | Bảo toàn JSON/escaping |
| URL trong text/HTML response | Response processor phù hợp | Tránh thay nội dung không phải link |

Không dùng request preprocessor để xử lý response header; cũng không cho rằng modifyUris tự động tìm URL trong mọi field của body.

## 10. Assertion, descriptor và preprocessor

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Assertion | Kiểm tra URL/token trong response thật theo contract | Kiểm tra Location trỏ đúng resource |
| Preprocessor | Mask host/token trong bản ghi snippet | Thay host và query token bằng placeholder |
| Descriptor | Giải thích header/field cho người tích hợp | Mô tả Location hoặc paymentUrl |

Nếu server trả Location sai path, test cần thất bại dù preprocessor thay host thành domain đúng. Không viết preprocessor sửa cả path sai thành path mong đợi; điều đó che giấu lỗi API.

Nếu tài liệu dùng placeholder payment-token, phần mô tả cần giải thích client nhận token qua flow đã công bố và cách sử dụng link. Không để người đọc hiểu placeholder là giá trị thực có thể dùng.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Request snippet còn localhost/random port | Chưa chuẩn hóa request URI | Dùng modifyUris trong request preprocessor |
| Response Location còn hostname nội bộ | Chỉ dùng modifyUris cho request | Xử lý response header riêng |
| Token còn lộ trong URL | Regex không bao phủ key thực tế hoặc encoding | Rà soát key, fixture và pattern |
| Thay token làm mất query parameter kế tiếp | Regex tham lam/không giới hạn | Giới hạn tới ampersand/whitespace |
| Path bị thay cùng host | Pattern quá rộng | Dùng processor URI-aware hoặc chỉ thay authority |
| Link header bị hỏng | Regex không giữ cú pháp nhiều link/rel | Dùng fixture hoặc custom parser |
| JSON không hợp lệ | String replacement phá escaping | Kiểm tra JSON; ưu tiên dữ liệu giả |
| Descriptor và raw snippet khác nhau | Hard-code ID/value không khớp fixture | Dùng fixture ổn định và assertion đầy đủ |
| HTML/PDF còn token | Chỉ kiểm tra một snippet hoặc artifact cũ | Scan mọi snippet và render lại sạch |
| Host public bị thay dù cần giữ | Mask quá mức | Chỉ thay host môi trường riêng |

## 12. Best practices

1. Ưu tiên fixture URL/token giả; masking là lớp bảo vệ bổ sung.
2. Phân biệt request URI với URL trong response header/body.
3. Dùng modifyUris để chuẩn hóa scheme/host/port request khi phù hợp.
4. Dùng modifyHeaders cho response header cụ thể như Location.
5. Dùng replacePattern với regex hẹp cho token trong query/body.
6. Không thay query parameter nghiệp vụ cần người đọc hiểu.
7. Bảo toàn encoding, dấu phân cách query, fragment và cú pháp Link.
8. Assertion kiểm tra link thật; preprocessor chỉ chuẩn hóa bản ghi snippet.
9. Rà soát HTTP, cURL/HTTPie, header/body snippets và HTML/PDF.
10. Chạy clean build và scan URL/secret patterns trước publish.

## 13. Bài thực hành

Tài liệu hóa endpoint POST /api/orders. Response có Location chứa hostname nội bộ và JSON chứa paymentUrl với query token giả. Test chạy trên random port.

**Nhiệm vụ:**

1. Tạo MockMvc documentation test với fixture đơn hàng và token giả.
2. Assertion status, path của Location, resource ID trong body và payment URL theo contract.
3. Dùng request URI preprocessing nếu request snippet có localhost/random port.
4. Dùng response preprocessor thay Location host bằng domain tài liệu.
5. Dùng replacePattern hoặc custom processor thay query token trong paymentUrl bằng placeholder.
6. Giữ path và query parameter công khai khác.
7. Include response header/body snippets vào AsciiDoc.
8. Kiểm tra HTTP, cURL/HTTPie, response headers và body snippets.
9. Scan generated docs để xác nhận hostname nội bộ và token fixture không còn.
10. Chạy clean build và rà soát HTML/PDF cuối trước publish.

**Tiêu chí hoàn thành:** host môi trường riêng không xuất hiện khi không cần; token không bị công bố; link giữ path, parameter và semantics; assertion kiểm tra response thật; snippet và tài liệu cuối nhất quán.

## 14. Ghi nhớ

- URL có thể xuất hiện trong request URI, Location, Link, Content-Location hoặc body; chọn processor đúng vị trí.
- `modifyUris()` hữu ích để chuẩn hóa scheme/host/port của request URI được ghi nhận.
- `modifyHeaders()` phù hợp khi thay response header cụ thể như Location.
- `replacePattern(...)` có thể mask token hoặc host trong raw message, nhưng regex phải hẹp và được kiểm tra.
- Không giả định request URI processor tự xử lý URL trong response headers hoặc payload.
- Assertion kiểm tra link thật; preprocessor chỉ biến đổi bản ghi snippet.
- Rà soát snippet dẫn xuất và artifact đã render, không chỉ một file HTTP.
