# Kết hợp nhiều preprocessor theo thứ tự

Một request hoặc response được ghi nhận trong Spring REST Docs có thể cần nhiều bước chuẩn hóa trước khi sinh snippet. Request có thể cần thay Authorization bằng placeholder, bỏ Cookie và chuẩn hóa host; response có thể cần định dạng JSON, loại header nội bộ và thay request ID động. Các thao tác này được kết hợp trong cùng operation, nhưng **thứ tự processor rất quan trọng**: mỗi bước làm việc trên kết quả của bước trước, vì vậy một bước có thể thay đổi hoặc loại bỏ dữ liệu mà bước tiếp theo cần xử lý.

Spring REST Docs cho phép truyền nhiều operation preprocessors qua `preprocessRequest(...)` và `preprocessResponse(...)`. Danh sách processor trong cùng một nhánh được áp dụng theo thứ tự cấu hình. Muốn chuỗi xử lý dễ bảo trì, hãy xác định output cuối, sắp xếp phép biến đổi theo phụ thuộc dữ liệu, chạy test và đọc snippet thực tế để xác minh.

Bài học thuộc chương **Preprocessors** của module `SPRING_REST_DOCS`. Module tạo tài liệu REST API có thể kiểm chứng từ test HTTP với MockMvc, WebTestClient hoặc REST Assured, sinh snippet request, response, payload, tham số và header, rồi biên soạn Asciidoctor/Markdown và tích hợp build, CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao cần kết hợp nhiều preprocessor trong một operation.
2. Sắp xếp chuỗi request và response preprocessors theo thứ tự có chủ đích.
3. Nhận biết phụ thuộc giữa loại header, thay header, thay pattern, chuẩn hóa URI và định dạng body.
4. Phân biệt thứ tự processor trong một nhánh với xử lý request và response độc lập.
5. Thiết kế helper tái sử dụng chuỗi xử lý nhưng vẫn cho phép tùy biến.
6. Xác minh output thực tế, tránh che lỗi assertion hoặc làm hỏng semantics API.
7. Kiểm tra snippet và build để phát hiện thay đổi thứ tự ngoài ý muốn.

## 2. Vì sao thứ tự processor quan trọng?

Hãy xem chuỗi thao tác:

1. Thay Authorization bằng placeholder.
2. Loại Cookie khỏi request.
3. Chuẩn hóa URI.
4. Ghi request snippet.

Nếu xóa Cookie trước rồi mới cố thay giá trị Cookie, bước thay thế không còn dữ liệu để xử lý. Tương tự, nếu pattern thay đổi body trước khi pretty print, định dạng sẽ áp dụng lên nội dung đã thay đổi. Thứ tự quyết định kết quả snippet.

### 2.1. Mô hình xử lý tuần tự

```text
Message được ghi nhận
        │
        ▼
Preprocessor A
        │
        ▼
Message sau A
        │
        ▼
Preprocessor B
        │
        ▼
Message sau B
        │
        ▼
Preprocessor C
        │
        ▼
Message cuối
        │
        ▼
Snippet generation
```

Mỗi processor làm việc trên kết quả hiện thời của chuỗi. Processor sau không nhìn thấy dữ liệu đã bị processor trước loại bỏ, trừ khi processor trước đã thay nó bằng giá trị khác.

### 2.2. Chọn thứ tự theo quan hệ phụ thuộc

Trước khi viết chuỗi, hãy hỏi: bước nào cần header hoặc đoạn text vẫn tồn tại; bước nào xóa dữ liệu và nên chạy sau bước thay thế; bước format body nên chạy trước hay sau khi thay; có processor nào khiến nội dung không còn khớp pattern của bước tiếp theo?

Nguyên tắc dễ dùng là thực hiện phép biến đổi cần dữ liệu gốc trước, phép loại bỏ sau cùng, rồi kiểm tra định dạng cuối. Đây là nguyên tắc thiết kế, không phải quy tắc tuyệt đối: thứ tự cụ thể phải dựa trên dữ liệu và processor thực tế.

## 3. Kết hợp processor trong request

Request có thể cần chuẩn hóa URI, thay credential và loại header không thuộc tài liệu công khai:

```java
.andDo(document("orders-get",
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
        removeHeaders("Cookie", "X-Internal-Trace"),
        prettyPrint()
    )
));
```

Chuỗi này thực hiện: chuẩn hóa scheme/host/port request URI; thay Authorization và correlation ID trong bản request dùng cho snippet; loại Cookie và header trace; định dạng request body nếu có body phù hợp.

Cấu hình cần điều chỉnh theo contract thực tế. Nếu Cookie thuộc API contract và client cần hiểu cách gửi, không loại nó chỉ để snippet ngắn hơn. Nếu correlation ID có thể thiếu, test và descriptor cần mô tả điều kiện đó.

### 3.1. Thay header trước khi loại header

Nếu muốn giữ tên Cookie nhưng thay giá trị bằng placeholder, hãy thay và không remove cùng header:

```java
preprocessRequest(
    modifyHeaders()
        .set("Cookie", "SESSION=<session-cookie>")
        .build(),
    removeHeaders("X-Internal-Trace")
)
```

Nếu remove Cookie trước, bước thay ở sau không còn header để xử lý. Ngược lại, nếu mục tiêu là loại Cookie hoàn toàn, chỉ cần remove và không thực hiện bước thay giá trị cho header đó.

### 3.2. URI processor và content replacement

`modifyUris()` xử lý các thành phần URI request như scheme, host và port. `replacePattern(...)` thay nội dung khớp pattern trong message. Nếu chỉ muốn đổi host của request URI, ưu tiên URI processor thay vì regex trên toàn message.

Có thể kết hợp hai bước khi request còn chuỗi động trong body:

```java
preprocessRequest(
    modifyUris()
        .scheme("https")
        .host("api.example.test")
        .removePort()
        .build(),
    replacePattern(
        Pattern.compile("trace-[A-Za-z0-9-]+"),
        "trace-docs"
    ),
    prettyPrint()
)
```

Pattern chỉ là ví dụ. Xác nhận chuỗi cần thay nằm đúng trong request content và không trùng ID nghiệp vụ khác. Với JSON phức tạp, fixture ổn định hoặc processor hiểu cấu trúc JSON có thể thích hợp hơn regex.

## 4. Kết hợp processor trong response

Response có thể cần định dạng body, thay giá trị động và loại metadata không công khai:

```java
.andDo(document("orders-get",
    preprocessResponse(
        modifyHeaders()
            .set("X-Request-Id", "docs-request-id")
            .build(),
        removeHeaders("Set-Cookie", "X-Internal-Node"),
        replacePattern(
            Pattern.compile("run-[0-9]+"),
            "docs-run"
        ),
        prettyPrint()
    )
));
```

Chuỗi ví dụ thay request ID, loại cookie và header nội bộ, chuẩn hóa chuỗi run động rồi định dạng body cuối. Nếu pattern cần tìm request ID trong body chứ không phải header, phải cấu hình đúng vùng content. Không coi `replacePattern(...)` và `modifyHeaders()` là hai API thay thế nhau.

### 4.1. Thay rồi loại hay loại rồi thay?

| Mục tiêu | Chuỗi xử lý |
| --- | --- |
| Thay header bằng placeholder và giữ tên | Modify header; không remove cùng header |
| Xóa hẳn header khỏi snippet | Remove header; không cần modify giá trị |
| Thay giá trị rồi loại header khỏi snippet | Chỉ cần khi có bước trung gian phụ thuộc giá trị; thường nên xem lại thiết kế |
| Giữ header public, loại header nội bộ | Modify header public; remove header nội bộ |

Tránh cấu hình vừa thay một header thành placeholder rồi xóa chính header đó ngay sau đó nếu không có lý do cụ thể. Output cuối không còn placeholder, khiến bước thay trở nên thừa.

## 5. Thứ tự giữa replace pattern và pretty print

Đối với body, thứ tự thay pattern và định dạng có thể tạo khác biệt.

### 5.1. Thay trước, định dạng sau

Khi pattern cần khớp chuỗi trên body compact, có thể thay trước rồi pretty print:

```java
preprocessResponse(
    replacePattern(
        Pattern.compile("trace-[A-Za-z0-9-]+"),
        "trace-docs"
    ),
    prettyPrint()
)
```

Pattern có thể khớp trực tiếp body một dòng; sau đó pretty print giúp body dễ đọc.

### 5.2. Định dạng trước, thay sau

Nếu pattern được viết để khớp cấu trúc sau format, có thể định dạng trước. Tuy vậy, regex trên JSON thường dễ vỡ khi khoảng trắng, xuống dòng hoặc thứ tự field thay đổi. Ưu tiên pattern ít phụ thuộc whitespace hoặc custom processor hiểu cấu trúc JSON.

Không có một thứ tự luôn đúng. Chọn theo input thật processor nhận và kiểm tra snippet cuối.

### 5.3. Nội dung không phải JSON

Với XML, text hoặc body mà whitespace mang ý nghĩa, pretty print có thể không phù hợp. Nếu body chứa chữ ký, payload đã ký hoặc chuỗi mà từng byte/whitespace có ý nghĩa, không format chỉ để snippet đẹp hơn.

## 6. Request và response là hai chuỗi độc lập

Có thể khai báo cả hai nhánh trong cùng operation:

```java
.andDo(document("verification-create",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
            .build(),
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .build(),
        removeHeaders("Cookie")
    ),
    preprocessResponse(
        modifyHeaders()
            .set("X-Request-Id", "docs-request-id")
            .build(),
        removeHeaders("Set-Cookie", "X-Internal-Trace"),
        replacePattern(
            Pattern.compile("([?&]token=)[^&\\s]+"),
            "$1<verification-token>"
        ),
        prettyPrint()
    )
));
```

Các processor trong request chain chỉ xử lý bản request; processor trong response chain chỉ xử lý bản response. Khai báo cả hai nhánh không có nghĩa processor cuối của request chạy tiếp trên response. Giữ quy tắc theo đúng chiều message để người review hiểu phần nào đang được chuẩn hóa.

## 7. Assertion vẫn kiểm tra message thật

Preprocessor được gắn trong bước tài liệu hóa, không thay thế assertion:

```java
mockMvc.perform(get("/api/orders/{id}", 42L)
        .header("Authorization", "Bearer docs-test-token"))
    .andExpect(status().isOk())
    .andExpect(header().exists("X-Request-Id"))
    .andExpect(jsonPath("$.id").value(42))
    .andDo(document("orders-get",
        preprocessResponse(
            modifyHeaders()
                .set("X-Request-Id", "docs-request-id")
                .build()
        )
    ));
```

Test xác nhận response thật có request ID và order ID đúng. Snippet sau xử lý hiển thị request ID mẫu. Nếu response thật thiếu header, assertion phải thất bại; preprocessor không được tạo header giả để làm test pass.

Không thay status lỗi thành thành công, thêm field đang thiếu, sửa ID resource sai hoặc che response rò rỉ dữ liệu bằng chuỗi processor. Những thao tác đó làm mất giá trị kiểm chứng của REST Docs.

## 8. Thiết kế helper tái sử dụng

Khi nhiều test dùng cùng chính sách, có thể đóng gói request/response processor thành helper riêng. Ví dụ:

```java
static OperationRequestPreprocessor publicRequestPreprocessor() {
    return preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
            .build(),
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .build(),
        removeHeaders("Cookie")
    );
}
```

```java
static OperationResponsePreprocessor publicResponsePreprocessor() {
    return preprocessResponse(
        modifyHeaders()
            .set("X-Request-Id", "docs-request-id")
            .build(),
        removeHeaders("Set-Cookie", "X-Internal-Trace"),
        prettyPrint()
    );
}
```

Kiểu trả về và imports cần đối chiếu với phiên bản Spring REST Docs trong dự án. Giữ helper riêng cho request và response để tránh áp dụng nhầm chính sách. Nếu operation có contract khác, cho phép dùng helper tùy biến hoặc processor riêng.

### 8.1. Không tạo helper quá tổng quát

Helper công khai không nên tự động xóa mọi header không nhận diện hoặc thay tất cả URL trong body. Quy tắc quá rộng dễ làm hỏng ví dụ của operation đặc biệt. Helper tốt có phạm vi rõ, tên phản ánh mục đích và từng bước có thể đọc được.

## 9. Kiểm tra thứ tự bằng output

Đọc cấu hình chưa đủ để xác minh chuỗi processor. Sau khi test chạy, kiểm tra các snippet:

```text
target/generated-snippets/orders-get/
├── http-request.adoc
├── http-response.adoc
├── curl-request.adoc
├── httpie-request.adoc
├── request-headers.adoc
├── response-headers.adoc
└── response-fields.adoc
```

Checklist:

- Placeholder xuất hiện đúng header và không còn credential test.
- Header bị remove thực sự vắng mặt trong raw snippet.
- Host/port được chuẩn hóa nhưng path/query vẫn đúng.
- Pattern thay đúng giá trị mục tiêu, không sửa ID nghiệp vụ.
- Body sau pretty print vẫn hợp lệ và giữ semantics.
- Bảng descriptor khớp raw request/response đã xử lý.
- cURL/HTTPie và HTML/PDF không chứa dữ liệu cũ.
- Hai lần clean build với fixture xác định cho output nhất quán.

Nếu output sai, điều chỉnh thứ tự hoặc phạm vi processor rồi chạy lại test. Không chỉnh snippet sinh ra bằng tay vì lần build tiếp theo sẽ tạo lại chúng.

## 10. Những lỗi thiết kế thường gặp

| Cấu hình | Vấn đề | Cách sửa |
| --- | --- | --- |
| Remove header rồi mới modify cùng header | Header đã bị xóa, không còn giá trị để thay | Modify trước nếu muốn giữ placeholder; hoặc chỉ remove |
| Modify header rồi remove ngay | Bước modify không có tác dụng trong output cuối | Bỏ bước thừa hoặc xác định lại mục tiêu |
| Regex thay token chạy sau khi header/body bị loại | Không còn content để regex tìm | Đặt replace trước bước remove hoặc dùng fixture |
| Pretty print trước regex phụ thuộc chuỗi một dòng | Whitespace mới làm pattern không khớp | Thay trước hoặc viết pattern ít phụ thuộc whitespace |
| Regex chạy trên toàn body | Có thể thay nhầm ID/field nghiệp vụ | Giới hạn pattern hoặc dùng parser-aware processor |
| Dùng modifyUris để thay URL trong JSON | URI request processor không xử lý mọi URL trong payload | Dùng body processor phù hợp |
| Dùng cùng chain cho mọi operation | Có thể loại header thuộc contract endpoint khác | Tách helper và cấu hình theo operation |
| Tin snippet là bằng chứng assertion | Giá trị đã chuẩn hóa có thể khác message thật | Assertion trên response ban đầu |
| Chỉ review http-request | Credential có thể còn trong cURL/HTTPie | Rà soát toàn bộ output dẫn xuất |

## 11. Best practices

1. Xác định output cuối trước khi chọn thứ tự.
2. Xử lý dữ liệu cần giữ hoặc thay trước khi xóa nó.
3. Chỉ dùng remove khi mục tiêu là loại header khỏi snippet.
4. Dùng URI processor cho request URI; dùng header/body processor cho vị trí khác.
5. Chọn thứ tự replace pattern và pretty print theo content mà pattern cần khớp.
6. Giới hạn regex và dùng fixture/parser khi cấu trúc phức tạp.
7. Giữ assertion trên request/response thật, độc lập với snippet đã xử lý.
8. Tách request chain và response chain; tạo helper có phạm vi rõ.
9. Kiểm tra mọi snippet dẫn xuất và bản render cuối.
10. Chạy clean build trong CI để xác nhận chuỗi processor tạo output ổn định.

## 12. Bài thực hành

Tài liệu hóa endpoint `POST /api/orders`. Request test dùng Bearer token giả, Cookie giả và correlation ID động. Response có JSON đơn hàng, request ID động, Set-Cookie và Location. Tài liệu cần host mẫu, placeholder token, ID ổn định, JSON dễ đọc và không có Cookie/Set-Cookie.

**Nhiệm vụ:**

1. Viết MockMvc documentation test và assertion status, order ID, Location và request ID trên message thật.
2. Request chain: chuẩn hóa URI; thay Authorization và correlation ID; loại Cookie.
3. Response chain: thay request ID; loại Set-Cookie và header nội bộ; định dạng JSON sau khi các giá trị cần thay đã được xử lý.
4. Kiểm tra thứ tự bằng cách đọc raw request và response snippet.
5. Xác nhận path/query contract vẫn giữ nguyên.
6. Kiểm tra request/response header descriptors khớp raw snippet.
7. Rà soát cURL, HTTPie và body/field snippets.
8. Tạo helper riêng nếu một chain được tái sử dụng.
9. Chạy clean test hai lần và so sánh output để phát hiện dữ liệu động còn sót.
10. Render Asciidoctor và kiểm tra artifact cuối.

**Tiêu chí hoàn thành:** mỗi chain xử lý đúng chiều; thứ tự có lý do và output được xác minh; assertion bảo vệ message thật; snippet không lộ credential; contract và dữ liệu ví dụ nhất quán; build tạo lại output ổn định.

## 13. Ghi nhớ

- Nhiều preprocessor trong cùng nhánh được kết hợp theo thứ tự cấu hình; mỗi bước xử lý kết quả của bước trước.
- `preprocessRequest(...)` và `preprocessResponse(...)` tạo hai chain độc lập cho request và response.
- Không thể thay header sau khi đã remove nó; không nên modify rồi remove cùng header nếu không có mục đích trung gian.
- Thứ tự replace pattern và pretty print phụ thuộc dạng content mà pattern cần khớp.
- Dùng `modifyUris()` cho thành phần URI request; dùng processor phù hợp cho response header và body.
- Assertion kiểm tra message thật; preprocessor chỉ chuẩn hóa bản ghi snippet.
- Đọc lại raw HTTP, cURL, HTTPie, descriptor và tài liệu đã render để xác minh output cuối.
