# Authorization, correlation id và header nghiệp vụ

Header HTTP có thể mang thông tin xác thực, hỗ trợ truy vết request hoặc truyền ngữ cảnh nghiệp vụ ảnh hưởng đến cách server xử lý. Ba nhóm thường gặp có mục đích và rủi ro khác nhau: **Authorization** trình bày credential; **correlation ID** liên kết log và các bước xử lý; **header nghiệp vụ** như tenant hoặc locale mang ngữ cảnh do API định nghĩa. Tài liệu cần mô tả đúng cách gửi, điều kiện bắt buộc, semantics và response tương ứng.

Trong **Spring REST Docs**, header được mô tả bằng `requestHeaders(...)` hoặc `responseHeaders(...)` kết hợp `headerWithName(...)`. Test có thể kiểm tra sự hiện diện, giá trị hoặc tác động của header; descriptor sinh các bảng snippet để chèn vào Asciidoctor/Markdown. Bài học thuộc chương **Headers** của module `SPRING_REST_DOCS`. Module tạo tài liệu REST API có thể kiểm chứng từ test HTTP với MockMvc, WebTestClient hoặc REST Assured, sinh snippet request, response, payload, tham số và header, rồi tích hợp vào build, CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt mục đích của Authorization, correlation ID và header nghiệp vụ.
2. Mô tả header request bằng `requestHeaders(...)` và header response bằng `responseHeaders(...)`.
3. Dùng assertion để xác minh header được yêu cầu và hành vi server phụ thuộc header.
4. Tài liệu hóa Bearer token mà không đưa credential thật vào snippet.
5. Mô tả cách tạo, truyền tiếp và trả correlation ID qua các thành phần.
6. Xác định tenant, locale hoặc custom header khác là bắt buộc, tùy chọn hay không được chấp nhận.
7. Sinh snippet header và kiểm tra tài liệu trong CI.

## 2. Nhìn header theo vai trò

Header có thể chỉ xuất hiện ở request, chỉ ở response hoặc ở cả hai chiều. Trước khi viết descriptor, xác định đúng chiều và trách nhiệm.

| Nhóm | Vị trí thường gặp | Mục đích | Câu hỏi hợp đồng |
| --- | --- | --- | --- |
| Authorization | Request | Trình bày thông tin xác thực | Scheme nào, khi nào bắt buộc, token lấy ở đâu, lỗi ra sao? |
| Correlation ID | Request và/hoặc response | Liên kết log, trace và các bước xử lý | Client có thể gửi không, server tạo nếu thiếu không, response dùng tên header nào? |
| Tenant header | Request | Chọn tenant/phạm vi dữ liệu nếu API thiết kế như vậy | Ai được phép chọn tenant, server đối chiếu với identity ra sao? |
| Locale/language | Request; response có thể có Content-Language | Chọn ngôn ngữ representation | Ngôn ngữ mặc định và fallback là gì? |
| Custom business context | Request hoặc response | Truyền ngữ cảnh nghiệp vụ riêng | Giá trị hợp lệ, tác động và quyền sử dụng là gì? |

Không tạo custom header chỉ vì một giá trị có thể đặt trong header. Hãy xác định nó thuộc semantics HTTP, payload, query parameter hay cơ chế xác thực. Chỉ công bố custom header khi nó có ý nghĩa ổn định và client cần biết cách dùng.

## 3. Authorization: mô tả xác thực, không tiết lộ credential

### 3.1. Bearer token trong request

Với API dùng HTTP Bearer authentication, client thường gửi:

```http
GET /api/orders/501 HTTP/1.1
Host: api.example.test
Accept: application/json
Authorization: Bearer <access-token>
```

Header Authorization mang scheme Bearer cùng access token. Tài liệu cần nói client lấy token từ cơ chế cấp quyền nào, token được gửi trong header nào, endpoint nào yêu cầu xác thực và cách xử lý khi token hết hạn hoặc không hợp lệ.

Không đưa token thật, token staging/production hoặc token developer vào snippet công khai. Dùng placeholder như `Bearer <access-token>` hoặc giá trị giả chỉ dùng trong test. Nếu test tạo token động, phải làm sạch giá trị trong output trước publish.

### 3.2. Mô tả request header bằng Spring REST Docs

Với MockMvc, test có thể gửi token giả trong fixture và khai báo descriptor:

```java
mockMvc.perform(
        get("/api/orders/{orderId}", 501L)
            .header("Authorization", "Bearer docs-test-token")
            .accept(MediaType.APPLICATION_JSON)
    )
    .andExpect(status().isOk())
    .andDo(document("orders-get-authenticated",
        requestHeaders(
            headerWithName("Authorization")
                .description(
                    "Bearer access token cấp cho client đã xác thực"
                ),
            headerWithName("Accept")
                .description("Media type response client chấp nhận")
        )
    ));
```

Ví dụ này minh họa nơi gắn descriptor. Để chứng minh xác thực, test phải chạy với security filter chain và cơ chế xác thực phù hợp. Nếu controller standalone không có security filter, việc gửi header chỉ chứng minh header được gửi, **không chứng minh server đã xác thực token**.

Các static import chính:

```java
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
```

Nếu ứng dụng dùng Spring Security, hãy thiết lập test context có filter chain và fixture authentication phù hợp. Có thể dùng test token giả hoặc principal test; không cần credential thật để chứng minh contract.

### 3.3. Kiểm tra các kết quả xác thực

| Tình huống | HTTP status thường gặp | Điều cần kiểm tra |
| --- | --- | --- |
| Thiếu Authorization | 401 Unauthorized | Endpoint yêu cầu xác thực; response lỗi theo schema API |
| Token sai/hết hạn | 401 Unauthorized | Server từ chối và trả lỗi phù hợp |
| Token hợp lệ nhưng thiếu quyền | 403 Forbidden | Danh tính đã xác thực nhưng không được phép |
| Token hợp lệ và đủ quyền | Status thành công theo operation | Payload chỉ chứa dữ liệu được phép truy cập |

Status và body lỗi phụ thuộc hợp đồng. Có hệ thống dùng 404 để không tiết lộ tài nguyên tồn tại khi người gọi không có quyền; tài liệu phải phản ánh chính sách thực tế.

Ví dụ test thiếu token:

```java
@Test
void getOrder_withoutToken() throws Exception {
    mockMvc.perform(
            get("/api/orders/{orderId}", 501L)
                .accept(MediaType.APPLICATION_JSON)
        )
        .andExpect(status().isUnauthorized())
        .andDo(document("orders-get-unauthenticated",
            responseFields(
                fieldWithPath("code").description("Mã lỗi"),
                fieldWithPath("message").description("Thông báo lỗi")
            )
        ));
}
```

Đoạn test giả định API trả JSON lỗi có hai field. Nếu response thực tế không có body hoặc dùng schema khác, điều chỉnh descriptor theo response thực. Không khai báo Authorization như header có mặt trong request này.

### 3.4. Giữ Authorization an toàn trong snippet

`http-request.adoc`, cURL và HTTPie snippet có thể ghi lại header mà test gửi. Vì vậy:

- Dùng token giả ngắn hạn chỉ có giá trị trong test.
- Không đọc secret thật từ biến môi trường developer/CI để đưa vào request tài liệu hóa.
- Nếu token được tạo động, thay/che giá trị trong snippet bằng preprocessor phù hợp.
- Rà soát cả HTTP, cURL và HTTPie snippet trước publish.
- Không commit token vào source test, log, fixture hoặc artifact.

Nếu mục tiêu là kiểm tra quyền, có thể dùng test security context với principal giả. Nếu cần chứng minh việc parse Bearer token, dùng token giả hợp lệ do test tạo và làm sạch snippet trước khi công bố.

## 4. Correlation ID: liên kết một request qua nhiều thành phần

### 4.1. Vai trò và hợp đồng

Correlation ID là mã tương quan dùng để liên kết log hoặc sự kiện phát sinh từ cùng request/luồng xử lý. Client có thể gửi mã; server có thể giữ nguyên, xác thực format hoặc tạo mã mới nếu thiếu rồi trả mã trong response. Tên header không được chuẩn hóa cho mọi ứng dụng; dự án có thể chọn `X-Correlation-Id` hoặc `X-Request-Id`.

Request:

```http
GET /api/orders/501 HTTP/1.1
Accept: application/json
X-Correlation-Id: docs-flow-001
```

Response:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Correlation-Id: docs-flow-001

{"id":501,"status":"CONFIRMED"}
```

Tài liệu phải nói rõ server giữ nguyên ID hay thay bằng ID do server tạo, ID có được truyền tới downstream service không, format có giới hạn nào và client nên cung cấp mã này khi báo lỗi. Không cam kết giữ nguyên nếu gateway/server có thể tạo ID khác.

### 4.2. Ghi cả request và response header

Nếu hợp đồng nói server trả lại cùng correlation ID mà client gửi, test có thể mô tả hai chiều:

```java
mockMvc.perform(
        get("/api/orders/{orderId}", 501L)
            .header("X-Correlation-Id", "docs-flow-001")
            .accept(MediaType.APPLICATION_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(header().string(
        "X-Correlation-Id", "docs-flow-001"
    ))
    .andDo(document("orders-get-with-correlation",
        requestHeaders(
            headerWithName("X-Correlation-Id")
                .description("Mã tương quan do client cung cấp")
        ),
        responseHeaders(
            headerWithName("X-Correlation-Id")
                .description("Mã tương quan được trả để tra cứu log")
        )
    ));
```

Đây là contract cụ thể: server trả lại cùng giá trị. Nếu server chỉ nhận ID để ghi log nhưng trả ID riêng, assertion và mô tả cần phản ánh chính sách đó.

### 4.3. Server tạo ID khi client không gửi

Một chính sách khác là server tạo ID nếu request không có header:

```java
mockMvc.perform(
        get("/api/orders/{orderId}", 501L)
            .accept(MediaType.APPLICATION_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(header().exists("X-Correlation-Id"))
    .andDo(document("orders-get-generated-correlation",
        responseHeaders(
            headerWithName("X-Correlation-Id")
                .description("Mã do server tạo khi request không cung cấp ID")
        )
    ));
```

Nếu response luôn có header theo hợp đồng, descriptor bắt buộc và assertion exists là phù hợp. Nếu response có thể không có ID, descriptor có thể dùng `optional()` và phần viết tay cần giải thích điều kiện. Không dùng optional chỉ vì fixture chưa tạo header trong khi API cam kết luôn trả nó.

### 4.4. Correlation ID khác access token

| Đặc điểm | Authorization | Correlation ID |
| --- | --- | --- |
| Mục đích | Xác thực hoặc trình bày credential | Truy vết và liên kết xử lý |
| Dùng cấp quyền? | Có, tùy scheme/token và policy | Không |
| Có phải bí mật? | Credential phải được bảo vệ | Thường không phải credential, nhưng tránh nhét dữ liệu nhạy cảm |
| Truyền downstream | Theo cơ chế identity được thiết kế | Thường truyền để giữ trace context |
| Khi thiếu | Có thể bị từ chối với 401 | Server có thể tạo hoặc chấp nhận thiếu theo hợp đồng |

Không dùng correlation ID làm bằng chứng xác thực. Biết mã request không cho phép xem dữ liệu hay sửa tài nguyên.

## 5. Header nghiệp vụ: tenant, locale và ngữ cảnh API

Header nghiệp vụ là custom header mà API định nghĩa để truyền ngữ cảnh. Chúng cần được dùng có chọn lọc, semantics và tác động phải rõ.

### 5.1. Tenant header

API đa tenant có thể yêu cầu client gửi:

```http
GET /api/invoices HTTP/1.1
Authorization: Bearer <access-token>
X-Tenant-Id: tenant-demo
Accept: application/json
```

Tài liệu cần nói rõ tenant ID được cấp ở đâu, header bắt buộc cho endpoint nào, server kiểm tra tenant thuộc phạm vi principal đã xác thực ra sao, và điều gì xảy ra khi tenant thiếu/không tồn tại/ngoài quyền.

**X-Tenant-Id không phải bằng chứng phân quyền.** Server phải kiểm tra tenant được chọn có nằm trong phạm vi identity được xác thực. Nếu tin trực tiếp giá trị client gửi, người dùng có thể thử thay tenant để truy cập dữ liệu ngoài quyền.

Descriptor ví dụ:

```java
requestHeaders(
    headerWithName("Authorization")
        .description("Bearer token của client đã xác thực"),
    headerWithName("X-Tenant-Id")
        .description("Tenant ID trong phạm vi client được cấp quyền")
)
```

Test cần kiểm tra tenant hợp lệ và tenant ngoài quyền. Một test chỉ xác nhận server nhận header không chứng minh cách ly dữ liệu tenant.

### 5.2. Locale hoặc ngôn ngữ

Một số API dùng `Accept-Language` để chọn ngôn ngữ response. Header này có semantics HTTP; nếu API dùng custom header khác, cần giải thích quy tắc ưu tiên.

Request:

```http
GET /api/products/7 HTTP/1.1
Accept: application/json
Accept-Language: vi
```

Response có thể trả `Content-Language: vi` để chỉ ngôn ngữ representation. Tài liệu nên nêu locale hỗ trợ, mặc định khi thiếu, fallback khi không hỗ trợ và liệu locale đổi dữ liệu hay chỉ chuỗi hiển thị. Nếu representation thay đổi theo Accept-Language, cân nhắc `Vary: Accept-Language` theo cách API triển khai.

### 5.3. Custom header nghiệp vụ khác

| Header ví dụ | Mục đích có thể có | Điều cần tài liệu hóa |
| --- | --- | --- |
| `X-Client-Version` | Phiên bản client | Format, dùng cho tương thích hay telemetry |
| `X-Channel` | Kênh bán hàng/nguồn request | Giá trị cho phép, tác động nghiệp vụ và quyền |
| `X-Region` | Khu vực áp dụng quy tắc | Mã vùng, fallback và kiểm tra quyền |
| `Idempotency-Key` | Định danh yêu cầu có thể retry | Scope, thời hạn lưu và hành vi khi key được dùng lại với payload khác |
| `If-Match` | Điều kiện cập nhật dựa trên validator | Cách lấy ETag và response khi validator không khớp |

Đây là ví dụ custom/context header, không phải yêu cầu của Spring REST Docs hay header bắt buộc với mọi API. Chỉ dùng khi hệ thống định nghĩa chúng. Nếu dữ liệu là thuộc tính cốt lõi của resource, request body hoặc query parameter có thể phù hợp hơn header.

## 6. Kết hợp requestHeaders và responseHeaders trong một operation

Một test có thể mô tả nhiều nhóm header:

```java
.andDo(document("invoices-get",
    requestHeaders(
        headerWithName("Authorization")
            .description("Bearer token để xác thực client"),
        headerWithName("X-Tenant-Id")
            .description("Tenant ID trong phạm vi client được phép"),
        headerWithName("X-Correlation-Id")
            .description("Mã tương quan do client cung cấp")
    ),
    responseHeaders(
        headerWithName("X-Correlation-Id")
            .description("Mã tương quan được trả trong response"),
        headerWithName("Content-Type")
            .description("Media type của representation")
    )
));
```

Test có thể tạo `request-headers.adoc` và `response-headers.adoc` cùng identifier. Raw `http-request.adoc` và `http-response.adoc` vẫn minh họa header trong trao đổi HTTP; bảng descriptor giải thích các header được chọn.

### 6.1. Header bắt buộc và tùy chọn

Header bắt buộc nên có descriptor không optional và assertion nếu sự hiện diện là cam kết quan trọng. Header tùy chọn có thể dùng:

```java
requestHeaders(
    headerWithName("X-Correlation-Id")
        .description("Mã tương quan do client có thể cung cấp")
        .optional()
)
```

`optional()` trong descriptor cho biết header có thể không xuất hiện ở message được tài liệu hóa. Nó không có nghĩa server bỏ qua mọi giá trị, không kiểm tra format hoặc không cần authorization. Hợp đồng vẫn phải giải thích hành vi khi thiếu.

### 6.2. Tách operation theo điều kiện

Không đưa descriptor bắt buộc vào mọi tình huống nếu header chỉ có ở một số response. Có thể tạo operation riêng:

- `orders-get-authenticated`: request có Authorization.
- `orders-get-unauthenticated`: không gửi Authorization, response lỗi xác thực.
- `orders-get-with-correlation`: client gửi correlation ID.
- `orders-get-generated-correlation`: client không gửi ID, server tạo và trả ID.

Operation riêng giúp snippet mô tả chính xác request/response, tránh bảng header gây hiểu nhầm.

## 7. Sinh snippet và biên soạn tài liệu

Khi test gọi `requestHeaders(...)` hoặc `responseHeaders(...)`, Spring REST Docs sinh bảng header cho identifier tương ứng. Trong cấu hình thường gặp, tên file là `request-headers.adoc` và `response-headers.adoc`.

Ví dụ output:

```text
target/generated-snippets/
└── invoices-get/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-headers.adoc
    └── response-headers.adoc
```

Tên file cụ thể phụ thuộc descriptor được yêu cầu. Không include snippet nếu test không tạo nó.

AsciiDoc có thể nhúng bảng cùng ví dụ HTTP:

```asciidoc
=== Xác thực và ngữ cảnh request

API yêu cầu Bearer access token. Client gửi token trong Authorization.
Tenant ID chỉ chọn phạm vi xử lý; server vẫn kiểm tra tenant có thuộc
quyền của danh tính đã xác thực.

==== Request headers

include::{snippets}/invoices-get/request-headers.adoc[]

==== Request mẫu

include::{snippets}/invoices-get/http-request.adoc[]

==== Response headers

include::{snippets}/invoices-get/response-headers.adoc[]

==== Response mẫu

include::{snippets}/invoices-get/http-response.adoc[]
```

Attribute `snippets` phải trỏ tới output directory Spring REST Docs, ví dụ `target/generated-snippets` với Maven hoặc `build/generated-snippets` với Gradle theo cấu hình dự án. Với Markdown, cần bước chuyển đổi/chèn snippet tương thích; cú pháp include Asciidoctor không phải tính năng mặc định của mọi Markdown renderer.

Phần viết tay vẫn phải giải thích semantics Authorization, correlation ID và tenant. Snippet không thay thế chính sách bảo mật hoặc quy tắc nghiệp vụ.

## 8. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Token xuất hiện trong `http-request.adoc` | Test dùng credential thật hoặc không làm sạch snippet | Dùng token giả, preprocessor và rà soát HTTP/cURL/HTTPie |
| Có Authorization descriptor nhưng test không chứng minh auth | Header gửi tới controller không có security filter | Dùng test setup có security filter/authorization |
| Case thiếu token nhưng request snippet có Authorization | Dùng sai fixture/test case | Tạo operation không gửi header |
| Correlation ID đổi mỗi build | Giá trị ngẫu nhiên ghi nguyên trạng | Dùng ID cố định hoặc chuẩn hóa snippet |
| Server trả correlation ID khác nhưng tài liệu nói giữ nguyên | Mô tả/asserion giả định sai semantics | Xác minh chính sách tạo/propagate ID |
| Tenant header được xem như quyền truy cập | Server tin giá trị client mà không đối chiếu principal | Kiểm tra tenant authorization và test truy cập chéo |
| Locale header không làm response đổi như mô tả | Test không kiểm tra nội dung/ngôn ngữ | Thêm assertion và ghi rõ fallback |
| Bảng header thiếu header trong response | Chưa khai báo descriptor | Thêm requestHeaders/responseHeaders nếu header thuộc hợp đồng |
| Snippet header không xuất hiện | Test không chạy hoặc descriptor không được gọi | Kiểm tra test report, document và identifier |
| Header nội bộ bị công bố | Ghi mọi header server gửi | Chỉ chọn header public, làm sạch raw snippet |
| CI dùng snippet cũ | Output không được clean hoặc test bị skip | Clean build và bảo đảm test trước render |

## 9. Best practices

1. Xác định chiều header: Authorization và tenant thường ở request; correlation ID có thể ở cả hai chiều.
2. Mô tả semantics cụ thể: scheme, nguồn cấp token, cách truyền ID, tenant scope và locale fallback.
3. Tách xác thực khỏi truy vết: correlation ID không phải credential và không cấp quyền.
4. Không dùng secret thật; tài liệu chỉ chứa placeholder hoặc dữ liệu test giả.
5. Kết hợp descriptor với assertion để kiểm tra giá trị và tác động bảo mật quan trọng.
6. Test tenant isolation; server phải đối chiếu tenant với identity và permission.
7. Chuẩn hóa correlation ID động để snippet ổn định.
8. Tách operation theo tình huống có/không có token, correlation ID hoặc tenant hợp lệ.
9. Chỉ công bố custom header có hợp đồng rõ.
10. Kiểm tra cả raw snippet và bảng descriptor trước publish.

## 10. Bài thực hành

Tài liệu hóa `GET /api/invoices/{invoiceId}` của API đa tenant. Hợp đồng giả định:

- Client cần Bearer token hợp lệ.
- Client gửi `X-Tenant-Id` thuộc phạm vi được cấp quyền.
- Client có thể gửi `X-Correlation-Id`; nếu thiếu, server tạo ID.
- Response trả `X-Correlation-Id` để client tra cứu request.
- Tenant không hợp lệ hoặc ngoài quyền bị từ chối theo schema lỗi đã định nghĩa.

**Nhiệm vụ:**

1. Viết test thành công với token giả, tenant hợp lệ và correlation ID cố định.
2. Dùng `requestHeaders(...)` mô tả Authorization, X-Tenant-Id và X-Correlation-Id.
3. Dùng `responseHeaders(...)` mô tả correlation ID trả về.
4. Assert status, dữ liệu response và correlation ID theo chính sách đã chọn.
5. Viết test thiếu token và xác nhận response lỗi; không đưa Authorization vào request descriptor của operation này.
6. Viết test tenant ngoài phạm vi và xác nhận server không trả dữ liệu tenant khác.
7. Viết test không có correlation ID và xác nhận server tạo ID nếu đó là cam kết.
8. Rà soát snippet raw để không chứa token thật hoặc dữ liệu tenant nhạy cảm.
9. Include hai bảng header trong AsciiDoc, giải thích tenant header không thay thế authorization.
10. Chạy build sạch và xác nhận test sinh snippet trước render.

**Tiêu chí hoàn thành:** test bảo vệ những quy tắc đã nêu; descriptor phản ánh đúng header request/response; token an toàn; correlation ID rõ semantics; tenant được kiểm tra với danh tính đã xác thực; tài liệu render từ snippet hiện tại.

## 11. Ghi nhớ

- Authorization trình bày thông tin xác thực; tài liệu phải mô tả scheme và cách lấy token, tuyệt đối không công bố credential thật.
- Correlation ID liên kết log và luồng xử lý; nó không phải token và không cấp quyền.
- Header nghiệp vụ như tenant, locale hoặc idempotency key chỉ nên dùng khi semantics và điều kiện áp dụng được định nghĩa rõ.
- `requestHeaders(...)` mô tả header client gửi; `responseHeaders(...)` mô tả header server trả; `headerWithName(...)` tạo descriptor cho từng header.
- Assertion xác nhận giá trị/tác động; descriptor tạo bảng mô tả và kiểm tra tính khớp với message được test.
- Tách operation theo tình huống có/không có token, correlation ID hoặc tenant hợp lệ; chuẩn hóa giá trị động và làm sạch snippet.
- Kết nối test, snippet, Asciidoctor/Markdown và CI để tài liệu header được tái tạo từ tình huống HTTP đã kiểm thử.
