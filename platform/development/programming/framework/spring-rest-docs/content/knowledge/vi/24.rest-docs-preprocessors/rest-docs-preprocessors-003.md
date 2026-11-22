# Preprocess request trước khi sinh snippet

Trong Spring REST Docs, request được ghi nhận từ bài kiểm thử HTTP có thể chứa những chi tiết không phù hợp để đưa nguyên trạng vào tài liệu: token xác thực của test, cookie phiên, hostname/port phụ thuộc máy chạy, request ID ngẫu nhiên hoặc payload có dữ liệu fixture không cần công khai. **Request preprocessing** cho phép chuẩn hóa bản request mà REST Docs dùng để tạo snippet trước khi các file tài liệu được ghi ra.

Mục tiêu là tạo ví dụ HTTP dễ đọc, ổn định và an toàn, đồng thời giữ nguyên khả năng kiểm chứng của test. Test vẫn gửi request ban đầu đến ứng dụng và assertion vẫn kiểm tra hành vi của ứng dụng. Preprocessor chỉ tác động lên bản request phục vụ tài liệu; nó không thay đổi request đã được gửi tới server.

Bài học thuộc chương **Preprocessors** của module `SPRING_REST_DOCS`. Module thực hành tạo tài liệu REST API có thể kiểm chứng từ test HTTP với MockMvc, WebTestClient hoặc REST Assured, sinh snippet cho request, response, payload, tham số và header, rồi biên soạn Asciidoctor/Markdown và tích hợp build, CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích request preprocessing giải quyết vấn đề gì trong Spring REST Docs.
2. Xác định vị trí request preprocessor trong chuỗi gửi request → assertion → document → snippet.
3. Dùng `preprocessRequest(...)` để gắn một hoặc nhiều `OperationRequestPreprocessor`.
4. Làm đẹp request body, thay/loại header và chuẩn hóa URI trước khi ghi snippet.
5. Phân biệt thay đổi bản request dùng cho snippet với thay đổi request thật.
6. Kiểm tra raw HTTP, cURL, HTTPie và bảng descriptor sau preprocessing.
7. Tổ chức fixture và CI để snippet ổn định, không lộ dữ liệu nhạy cảm.

## 2. Request preprocessing nằm ở đâu?

Một HTTP documentation test thường thực hiện các bước:

```text
Chuẩn bị fixture và test client
             │
             ▼
Tạo HTTP request ban đầu
             │
             ▼
Gửi request tới ứng dụng
             │
             ▼
Nhận response và chạy assertions
             │
             ▼
Gọi document(identifier, ...)
             │
             ▼
Request preprocessor xử lý bản request được ghi nhận
             │
             ▼
REST Docs tạo snippet từ request đã xử lý
             │
             ▼
Asciidoctor / Markdown ghép snippet vào tài liệu
```

Trong MockMvc, hook tài liệu hóa thường được gắn bằng `andDo(document(...))`. Request preprocessor được truyền qua `preprocessRequest(...)`. Với WebTestClient hoặc REST Assured, cách gắn recorder/filter khác nhau, nhưng cần cấu hình để request được ghi nhận và processor được áp dụng trước khi snippet được sinh.

### 2.1. Bản request thật và bản request dùng cho tài liệu

Giả sử test gửi:

```http
GET /api/orders/42 HTTP/1.1
Host: localhost:53128
Authorization: Bearer docs-test-token
Cookie: SESSION=session-for-test
X-Request-Id: 6b49c1f4-volatile
Accept: application/json
```

Tài liệu công khai có thể chỉ cần:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
```

Server nhận request đầu tiên; snippet có thể được tạo từ bản thứ hai sau preprocessing. Không dùng bản đã xử lý làm bằng chứng rằng ứng dụng thật nhận placeholder hoặc hostname mẫu.

### 2.2. Vì sao xử lý trước khi tạo snippet?

Request snippet thường được copy để thử API, nên giá trị không phù hợp có thể gây hậu quả:

- Credential hoặc session ID bị công bố.
- Người đọc copy hostname chỉ tồn tại trên máy developer.
- Request ID thay đổi khiến tài liệu khác nhau sau mỗi build.
- Payload chứa tên, email hoặc mã khách hàng của fixture thật.
- URI có query parameter nội bộ hoặc dữ liệu không cần thiết.
- cURL/HTTPie snippet tái sử dụng nguyên giá trị nhạy cảm.

Preprocessing cho phép xử lý các trường hợp này tại một điểm rõ ràng trước khi file snippet được ghi.

## 3. preprocessRequest(...) và OperationRequestPreprocessor

Spring REST Docs cung cấp API trong package `org.springframework.restdocs.operation.preprocess`. `preprocessRequest(...)` nhận một hoặc nhiều request preprocessor và tạo processor tổng hợp để đưa vào cấu hình tài liệu hóa.

Ví dụ:

```java
.andDo(document("orders-get",
    preprocessRequest(prettyPrint())
));
```

`OperationRequestPreprocessor` là abstraction xử lý một `OperationRequest` và trả về request đã được xử lý. Các hàm built-in như `prettyPrint()`, `removeHeaders(...)`, `modifyHeaders()` và `replacePattern(...)` tạo những processor có thể kết hợp.

Static import thường dùng:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
```

Tên và chữ ký builder cần khớp version Spring REST Docs mà project đang quản lý.

## 4. Định dạng request body trước khi ghi snippet

### 4.1. prettyPrint()

`prettyPrint()` định dạng body để dễ đọc, đặc biệt với JSON/XML. Request compact:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"customerId":12,"productId":7,"quantity":2}
```

Có thể trở thành snippet dễ đọc hơn:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json

{
  "customerId": 12,
  "productId": 7,
  "quantity": 2
}
```

Gắn processor:

```java
.andDo(document("orders-create",
    preprocessRequest(prettyPrint())
));
```

`prettyPrint()` chỉ định dạng body; nó không xác nhận JSON hợp lệ theo hợp đồng và không ẩn dữ liệu nhạy cảm. Assertion và descriptor vẫn cần được viết riêng.

### 4.2. XML và text body

Với XML hoặc text, cần kiểm tra processor và content type có xử lý định dạng như mong đợi hay không. Không giả định mọi body đều được format giống JSON. Với text thuần, khoảng trắng hoặc xuống dòng đôi khi có ý nghĩa nên giữ nguyên có thể đúng hơn.

Ví dụ XML:

```xml
<order>
    <customerId>12</customerId>
    <quantity>2</quantity>
</order>
```

Nếu processor hỗ trợ pretty print cho định dạng này trong version đang dùng, snippet có thể được chuẩn hóa indentation. Đọc file sinh ra để xác nhận nội dung và encoding chính xác.

### 4.3. Không dùng prettyPrint để sửa payload sai

Nếu request test gửi sai cấu trúc, pretty print không làm request trở nên đúng. Preprocessor chỉ trình bày message đã nhận. Test cần assertion status và kết quả liên quan; request field descriptor mô tả contract độc lập với định dạng.

## 5. Làm sạch và chuẩn hóa request header

### 5.1. Loại bỏ header không cần công bố

`removeHeaders(...)` loại header khỏi bản request ghi thành snippet:

```java
.andDo(document("orders-get",
    preprocessRequest(
        removeHeaders("Cookie", "X-Internal-Trace")
    )
));
```

Cách này phù hợp với cookie phiên, header debug hoặc metadata môi trường không cần trong hướng dẫn client. Nó chỉ làm header biến mất khỏi snippet; server vẫn đã nhận request ban đầu có các header đó.

Không loại header thuộc hợp đồng nếu người tích hợp cần biết phải gửi gì. Ví dụ Authorization thường cần giữ tên trong ví dụ nhưng thay giá trị bằng placeholder.

### 5.2. Thay giá trị header bằng placeholder

`modifyHeaders()` cho phép thay giá trị trong bản request được ghi:

```java
.andDo(document("orders-get-authenticated",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .build()
    )
));
```

Request gửi tới ứng dụng vẫn dùng token test; chỉ snippet thể hiện placeholder. Đây là lựa chọn thích hợp khi muốn người đọc hiểu header cần có nhưng không được nhìn thấy credential test. Cú pháp builder cần khớp version thư viện.

Ví dụ với correlation ID:

```java
.andDo(document("orders-get",
    preprocessRequest(
        modifyHeaders()
            .set("X-Correlation-Id", "docs-correlation-id")
            .build()
    )
));
```

Giá trị mẫu ổn định giúp snippet không thay đổi mỗi lần test tạo ID ngẫu nhiên. Nếu format ID thuộc hợp đồng, dùng giá trị giả có format phù hợp, chẳng hạn UUID mẫu.

### 5.3. Header bắt buộc và tùy chọn

Preprocessor không định nghĩa header là bắt buộc hay tùy chọn. Điều đó thuộc hợp đồng và descriptor. Nếu client phải gửi Authorization, tài liệu cần mô tả header bắt buộc và cách lấy token. Nếu correlation ID chỉ do client tùy chọn gửi, mô tả rõ server xử lý khi thiếu. Nếu header nội bộ được loại khỏi snippet, không có nghĩa nó tùy chọn với server.

Không dùng removeHeaders để né việc ghi tài liệu cho header public mà client bắt buộc phải gửi.

## 6. Chuẩn hóa URI, Host và port

Request ghi nhận trong môi trường test có thể dùng Host/port tạm thời, chẳng hạn server random port. Spring REST Docs có processor hỗ trợ điều chỉnh URI như `modifyUris()`.

Ví dụ:

```java
.andDo(document("orders-get",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
            .build()
    )
));
```

Ví dụ biến URI được ghi trong snippet theo host và scheme tài liệu. Dùng domain minh họa đã được nhóm thống nhất; không thay endpoint thành URL không tồn tại nếu người đọc cần copy request để chạy trực tiếp.

### 6.1. Khi nên chuẩn hóa URI?

- Test chạy local với random port.
- CI có hostname container khác máy developer.
- Tài liệu public cần domain chính thức thay cho localhost.
- Request dùng absolute URI nhưng endpoint public có base URL thống nhất.

Nếu snippet dùng relative URI và chỉ Host header khác nhau, kiểm tra output để chọn biến đổi phù hợp. Không chỉnh path, query hoặc scheme nếu chúng là phần hợp đồng cần thể hiện.

### 6.2. Giữ đúng semantics request

Chuẩn hóa hostname không được làm sai method, path, query parameter hoặc header cần thiết. Ví dụ API phân biệt base path /v1 với /v2; preprocessor không nên xóa version segment chỉ để URL ngắn hơn.

## 7. Chuẩn hóa giá trị động trong request

Request có thể chứa dữ liệu động không quan trọng với ví dụ: timestamp, nonce, correlation ID hoặc mã fixture ngẫu nhiên. `replacePattern(...)` có thể thay phần nội dung khớp regular expression bằng giá trị mẫu.

Ví dụ khái niệm: thay một correlation ID động bằng chuỗi ổn định. Với header cụ thể, `modifyHeaders()` thường rõ ràng hơn; dùng regex khi giá trị cần xử lý xuất hiện ở nhiều vị trí trong message.

Nguyên tắc dùng regex:

1. Giới hạn pattern vào đúng header hoặc field.
2. Không thay tất cả chuỗi chữ/số trong request.
3. Chọn giá trị thay thế có format phù hợp.
4. Chạy test và đọc snippet để bảo đảm không sửa nhầm path, ID nghiệp vụ hoặc payload khác.

Chữ ký `replacePattern(...)` và nơi áp dụng pattern cần khớp API version. Không sao chép một regex chưa được kiểm tra rồi mặc định nó xử lý đúng mọi request.

## 8. Kết hợp nhiều request processor

Một request có thể cần nhiều phép xử lý:

```java
.andDo(document("orders-create",
    preprocessRequest(
        prettyPrint(),
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
            .build(),
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .set("X-Correlation-Id", "docs-correlation-id")
            .build(),
        removeHeaders("Cookie", "X-Internal-Trace")
    )
));
```

Trong ví dụ, body được định dạng; URI được chuẩn hóa; Authorization và correlation ID được thay bằng giá trị mẫu; Cookie và header trace nội bộ bị loại khỏi request snippet.

Đừng áp dụng tất cả phép xử lý cho mọi API. Một endpoint có thể cần cookie như một phần contract; endpoint khác dùng custom host để định tuyến. Chọn processor theo mục tiêu tài liệu của operation.

### 8.1. Thứ tự xử lý và output

Thứ tự processor có thể ảnh hưởng kết quả. Nếu xóa header trước, processor sau không thể thay giá trị header đó. Nếu thay text rồi pretty print, kết quả định dạng áp dụng lên body sau thay đổi.

Hãy đọc output cuối cùng thay vì suy luận chỉ từ cấu hình. Giữ processor theo thứ tự có ý nghĩa và tránh chuỗi biến đổi thừa khó bảo trì.

## 9. Ví dụ end-to-end với MockMvc

Giả sử API có `GET /api/orders/{orderId}`. Test gửi token giả và correlation ID ngẫu nhiên, trong khi tài liệu cần host minh họa và không chứa cookie.

```java
@Test
void getOrder_documentsNormalizedRequest() throws Exception {
    mockMvc.perform(
            RestDocumentationRequestBuilders
                .get("/api/orders/{orderId}", 42L)
                .header("Authorization", "Bearer docs-test-token")
                .header("Cookie", "SESSION=test-session")
                .header("X-Correlation-Id", "run-982761")
                .accept(MediaType.APPLICATION_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(header().exists("X-Request-Id"))
        .andExpect(jsonPath("$.id").value(42))
        .andDo(document("orders-get-success",
            preprocessRequest(
                modifyUris()
                    .scheme("https")
                    .host("api.example.test")
                    .removePort()
                    .build(),
                modifyHeaders()
                    .set("Authorization", "Bearer <access-token>")
                    .set("X-Correlation-Id", "docs-correlation-id")
                    .build(),
                removeHeaders("Cookie")
            ),
            pathParameters(
                parameterWithName("orderId")
                    .description("Mã định danh đơn hàng")
            )
        ));
}
```

Ví dụ minh họa nơi gắn request processor; dự án cần fixture/controller thực tế và setup REST Docs phù hợp. Assertions chạy trên request/response thật. Sau preprocessing, request snippet có thể hiển thị host ví dụ, token placeholder và correlation ID cố định, không còn cookie test.

### 9.1. Kiểm tra các snippet đầu ra

Sau khi test chạy, kiểm tra các file liên quan tới identifier:

```text
target/generated-snippets/orders-get-success/
├── http-request.adoc
├── curl-request.adoc
├── httpie-request.adoc
└── path-parameters.adoc
```

Tên file phụ thuộc descriptor/template. Xác minh:

- Authorization không còn token fixture.
- Cookie đã bị loại nếu không thuộc ví dụ.
- Host/port là giá trị tài liệu dự kiến.
- Correlation ID không biến động giữa các lần build.
- Path parameter vẫn giữ đúng template/giá trị.
- cURL và HTTPie cũng thể hiện request đã chuẩn hóa theo hành vi processor của version đang dùng.

Đừng chỉ kiểm tra http-request; người dùng thường copy lệnh cURL/HTTPie trực tiếp.

## 10. RequestPreprocessor và descriptor

Request preprocessor chuẩn hóa message; descriptor mô tả contract. Ví dụ:

```java
.andDo(document("orders-get",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .build()
    ),
    requestHeaders(
        headerWithName("Authorization")
            .description("Bearer access token của client")
    ),
    pathParameters(
        parameterWithName("orderId")
            .description("Mã định danh đơn hàng")
    )
));
```

Preprocessor giữ cấu trúc header và thay credential. requestHeaders giải thích ý nghĩa Authorization. pathParameters mô tả orderId. Assertion riêng xác nhận request thành công theo hợp đồng.

Chỉ dùng descriptor mà không preprocessing có thể khiến raw request lộ credential; chỉ preprocessing mà không descriptor có thể khiến người đọc thấy placeholder nhưng không hiểu cách dùng header. Nếu processor xóa một header, hãy cân nhắc có nên mô tả header đó trong bảng descriptor hay không. Raw snippet và bảng mô tả phải nhất quán.

## 11. Những giới hạn cần hiểu

### 11.1. Không sửa request ứng dụng đã nhận

Request preprocessor không thay thế filter, interceptor hay logic server. Nếu cần thay đổi request thực tế, phải xử lý ở test setup/client hoặc trong ứng dụng; không dựa vào preprocessor.

### 11.2. Không thay thế assertion

Nếu server từ chối request nhưng test không kiểm tra status/body, preprocessor vẫn có thể tạo snippet đẹp. Assertion phải bảo vệ những điều quan trọng trên response thật.

### 11.3. Không che lỗi contract

Không sửa method, path, header bắt buộc hoặc payload sai thành ví dụ đúng mà không sửa test/API. Nếu request thực tế sai, cần sửa fixture hoặc test; tài liệu phải phản ánh request hợp lệ mà client cần gửi.

### 11.4. Không loại thông tin client cần

Nếu Authorization, Content-Type hoặc Idempotency-Key là phần cần thiết của request, hãy giữ tên header và thay giá trị nhạy cảm nếu cần. Không xóa toàn bộ header chỉ để tránh xử lý secret.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Token vẫn xuất hiện trong request snippet | Chỉ bỏ descriptor, chưa preprocessing raw request | Dùng fixture giả và thay Authorization trong request preprocessor |
| Cookie vẫn có trong tài liệu | Chưa remove header hoặc processor chưa gắn vào operation | Dùng removeHeaders("Cookie"), kiểm tra snippet |
| URI chứa localhost/random port | Chưa chuẩn hóa URI được ghi lại | Dùng modifyUris() theo base URL tài liệu |
| Path parameter sai/mất template | Request builder không giữ URI template hoặc preprocessing chỉnh path | Dùng REST Docs request builder phù hợp, không sửa path ngoài ý muốn |
| cURL còn credential | Chỉ kiểm tra http-request.adoc | Rà soát mọi snippet dẫn xuất |
| Correlation ID thay đổi mỗi build | Giá trị động được ghi nguyên trạng | Dùng fixture xác định hoặc thay header |
| Body không được format | Content type/body không được processor hỗ trợ hoặc processor chưa gắn đúng | Kiểm tra request và file sinh ra |
| Header cần thiết biến mất | Remove quá rộng | Chỉ loại header nội bộ, giữ header thuộc contract |
| Assertion bị nhầm là kiểm tra snippet | Dùng giá trị sau preprocessing để suy ra message gốc | Assertion trên message thật; review snippet riêng |
| Snippet chứa dữ liệu fixture thật | Test dùng dữ liệu không an toàn | Dùng dữ liệu giả và kiểm tra toàn bộ output |
| Asciidoctor không tìm thấy snippet | Test chưa chạy, sai identifier hoặc output directory | Chạy test trước render và đối chiếu đường dẫn |

## 13. Best practices

1. Ưu tiên fixture an toàn: không đưa token/session thật vào request test.
2. Preprocess đúng phía: request header/body/URI dùng preprocessRequest.
3. Giữ contract dễ hiểu: thay value nhạy cảm bằng placeholder thay vì xóa header client cần gửi.
4. Chuẩn hóa môi trường: thay localhost, random port và host nội bộ bằng base URL đã công bố.
5. Dùng ID ổn định để giảm diff không có ý nghĩa.
6. Giới hạn regex, chỉ thay đúng vùng dữ liệu có mục tiêu.
7. Kết hợp descriptor để giải thích header, parameter và field.
8. Kiểm tra mọi snippet dẫn xuất: HTTP, cURL và HTTPie có thể chứa cùng dữ liệu.
9. Giữ assertion trên kết quả thật; không để preprocessing che hành vi sai.
10. Chạy clean build trong CI, tạo lại snippet trước khi Asciidoctor render.

## 14. Bài thực hành

Tài liệu hóa `GET /api/orders/{orderId}`. Test gửi Bearer token giả, Cookie phiên test, correlation ID động và chạy server trên random port. Tài liệu cần request có domain mẫu, Authorization placeholder, correlation ID ổn định và không có Cookie.

**Nhiệm vụ:**

1. Cấu hình MockMvc với Spring REST Docs và viết test.
2. Gửi token giả và cookie giả; không dùng credential thật.
3. Assertion status và ít nhất một giá trị response quan trọng.
4. Gọi preprocessRequest để thay Authorization bằng placeholder.
5. Loại Cookie khỏi snippet nếu nó không thuộc contract công khai.
6. Dùng modifyUris để chuẩn hóa scheme/host/port theo domain tài liệu.
7. Thay correlation ID ngẫu nhiên bằng ID mẫu ổn định.
8. Khai báo descriptor path parameter và request headers cần thiết.
9. Chạy test, kiểm tra HTTP, cURL và HTTPie snippet.
10. Render Asciidoctor, xác nhận include đúng và không có credential fixture trong artifact.

**Tiêu chí hoàn thành:** request thật vẫn được gửi và kiểm tra đúng; request snippet có URI nhất quán, header cần thiết được giữ dưới dạng an toàn, header nội bộ được xử lý có chủ đích, snippet dẫn xuất không lộ giá trị nhạy cảm và build tái tạo được từ output sạch.

## 15. Ghi nhớ

- Request preprocessing biến đổi bản request dùng để sinh snippet; không thay đổi request mà ứng dụng đã nhận.
- preprocessRequest nhận các OperationRequestPreprocessor và gắn chúng vào operation được tài liệu hóa.
- prettyPrint định dạng body; removeHeaders loại header khỏi snippet; modifyHeaders thay giá trị header; modifyUris chuẩn hóa URI; replacePattern thay nội dung khớp pattern.
- Assertion kiểm tra hành vi thật; preprocessor chỉ chuẩn hóa bản ghi tài liệu.
- Descriptor giải thích header/parameter/field; preprocessor kiểm soát raw message được ghi ra.
- Kiểm tra raw HTTP, cURL, HTTPie và snippet liên quan sau mỗi thay đổi.
- Ưu tiên fixture giả, placeholder và output ổn định; chạy test trước render trong CI.
