Câu 01. Spring REST Docs khác tài liệu REST viết tay chủ yếu ở điểm nào?
A. Sinh snippets từ schema database mà ứng dụng kết nối
B. Sinh snippets từ tên của các bean trong Spring context
C. Sinh snippets từ mô tả Javadoc của controller method
D. Sinh snippets từ HTTP request/response đã chạy test
Đáp án đúng: D

Câu 02. Với JUnit 5, extension nào cung cấp hỗ trợ Spring REST Docs cho test?
A. `RestDocumentationExtension` cung cấp context REST Docs
B. `OutputCaptureExtension` thu thập logging trong test
C. `SpringExtension` khởi tạo ApplicationContext cho test
D. `MockitoExtension` khởi tạo Mockito mocks của test
Đáp án đúng: A

Câu 03. Trong test JUnit 5, tham số nào có thể inject để cấu hình REST Docs cho MockMvc?
A. `RestDocumentationResultHandler` xử lý kết quả MockMvc
B. `RestDocumentationContextProvider` cho cấu hình test
C. `JUnitRestDocumentation` khai báo JUnit 4 rule cho test
D. `RestDocumentationExtension` là extension của JUnit 5
Đáp án đúng: B

Câu 04. Với MockMvc, API cấu hình nào thuộc đúng tích hợp Spring REST Docs?
A. `MockMvcRestDocumentation.documentationConfiguration(context)`
B. `RestAssuredRestDocumentation.documentationConfiguration(context)`
C. `MockMvcRestDocumentation.document("orders-get")`
D. `WebTestClientRestDocumentation.documentationConfiguration(context)`
Đáp án đúng: A

Câu 05. Sau khi MockMvc thực thi HTTP request, thao tác nào sinh snippet cho lần gọi đó?
A. `andReturn()` lấy kết quả MockMvc sau khi request chạy
B. `andDo(print())` in request/response ra output của test
C. `andDo(document("orders-get"))` ghi snippets từ test
D. `andExpect(status().isOk())` xác minh HTTP status
Đáp án đúng: C

Câu 06. Với WebTestClient, cách nào gắn REST Docs configuration vào client test?
A. `expectStatus().isOk()` cấu hình docs khi kiểm response
B. `mutateWith(documentationConfiguration(context))` bật docs
C. `expectBody().returnResult()` cấu hình docs từ HTTP body
D. `exchange()` cấu hình docs trước khi chạy HTTP request
Đáp án đúng: B

Câu 07. Trên WebTestClient đã cấu hình REST Docs, API nào ghi snippets sau khi kiểm body?
A. `expectBody().consumeWith(document("orders-get"))` ghi docs
B. `expectStatus().isOk()` tạo snippet từ HTTP status
C. `exchange()` tạo snippet bằng cách chạy request
D. `expectBody().returnResult()` tạo snippet từ response
Đáp án đúng: A

Câu 08. Với REST Assured, cách gắn cấu hình Spring REST Docs vào request specification là gì?
A. `given().filter(documentationConfiguration(context))` bật docs
B. `given().then().statusCode(200)` bật docs configurer
C. `given().filter(document("orders-get"))` bật configurer
D. `given().when().get("/orders")` bật docs configuration
Đáp án đúng: A

Câu 09. REST Assured đã thiết lập REST Docs; thao tác nào ghi snippets cho request được test?
A. `given().filter(log().all())` ghi snippets qua logging filter
B. `given().filter(document("orders-get"))` sinh snippets
C. `given().when().get("/orders")` ghi snippet khi gửi GET
D. `given().then().statusCode(200)` ghi snippets từ matcher
Đáp án đúng: B

Câu 10. Trong `document("orders-get", ...)`, identifier `orders-get` thường xác định gì?
A. Tên bean của `RestDocumentationContextProvider` trong test
B. Tên module Java được scan để sinh REST controller
C. Tên HTTP header được thêm vào request khi test chạy
D. Thư mục con chứa các snippets của test trong output root
Đáp án đúng: D

Câu 11. Để sinh snippet mô tả nguyên một HTTP request, tên file mặc định nào phù hợp?
A. `response-body.adoc` chứa biểu diễn raw HTTP request
B. `http-response.adoc` chứa biểu diễn HTTP request thử nghiệm
C. `curl-request.adoc` chứa biểu diễn raw HTTP request
D. `http-request.adoc` chứa biểu diễn HTTP request thử nghiệm
Đáp án đúng: D

Câu 12. Để sinh lệnh cURL mô phỏng HTTP request đã test, snippet mặc định nào đúng?
A. `http-request.adoc` mô tả request dưới dạng cURL
B. `http-response.adoc` mô tả request dưới dạng cURL
C. `curl-request.adoc` mô tả request dưới dạng cURL
D. `request-body.adoc` mô tả request dưới dạng cURL
Đáp án đúng: C

Câu 13. Muốn mô tả trường `id` trong JSON response, tổ hợp API nào hợp lý?
A. `responseFields(fieldWithPath("id").description("Mã"))`
B. `pathParameters(parameterWithName("id").description("Mã"))`
C. `responseHeaders(headerWithName("id").description("Mã"))`
D. `requestFields(fieldWithPath("id").description("Mã"))`
Đáp án đúng: A

Câu 14. Muốn mô tả trường `name` trong JSON request body, tổ hợp API nào hợp lý?
A. `requestHeaders(headerWithName("name").description("Tên"))`
B. `requestFields(fieldWithPath("name").description("Tên"))`
C. `responseFields(fieldWithPath("name").description("Tên"))`
D. `queryParameters(parameterWithName("name").description("Tên"))`
Đáp án đúng: B

Câu 15. Với JSON `{ "customer": { "name": "Mai" } }`, path nào chỉ đúng trường `name`?
A. `fieldWithPath("customer")` truy cập đúng trường name
B. `fieldWithPath("name.customer")` truy cập đúng trường name
C. `fieldWithPath("customer.name")` chọn trường lồng
D. `fieldWithPath("customer[0].name")` cho object lồng
Đáp án đúng: C

Câu 16. Một response field có thể vắng mặt trong một số tình huống nhưng vẫn cần hiện trong docs; modifier nào phù hợp?
A. `.attributes(...)` cho phép field thiếu và loại khỏi bảng
B. `.optional()` cho phép field thiếu mà vẫn được mô tả
C. `.type(...)` cho phép field thiếu mà không cần metadata
D. `.ignored()` cho phép field thiếu và loại khỏi bảng
Đáp án đúng: B

Câu 17. Muốn bỏ trường kỹ thuật `internalId` khỏi bảng tài liệu payload nhưng không xem nó là undocumented, dùng gì?
A. `fieldWithPath("internalId").description("-")` bỏ khỏi bảng
B. `fieldWithPath("internalId").optional()` bỏ khỏi bảng
C. `fieldWithPath("internalId").type(STRING)` bỏ khỏi bảng
D. `fieldWithPath("internalId").ignored()` bỏ khỏi bảng
Đáp án đúng: D

Câu 18. Khi response có trường mới chưa khai báo, cách mô tả nào bỏ qua các trường chưa được liệt kê?
A. `responseFields(...)` chấp nhận field chưa mô tả
B. `relaxedRequestFields(...)` kiểm response field
C. `relaxedResponseFields(...)` bỏ qua field chưa mô tả
D. `responseHeaders(...)` kiểm response field chưa mô tả
Đáp án đúng: C

Câu 19. Ở chế độ strict `responseFields`, một field bắt buộc đã mô tả nhưng response thiếu thì sao?
A. REST Docs bổ sung field vào response body để kiểm lại
B. Test chỉ báo warning nhưng matcher vẫn coi hợp đồng hợp lệ
C. Snippet bỏ field khỏi bảng và vẫn qua test thành công
D. Test thất bại khi field được mô tả mà response thiếu
Đáp án đúng: D

Câu 20. Muốn mô tả object `customer` như một subsection thay vì liệt kê mọi field con, dùng gì?
A. `fieldWithPath("customer.email")` mô tả cả nhánh object
B. `subsectionWithPath("customer")` mô tả cả nhánh object
C. `fieldWithPath("customer.name")` mô tả cả nhánh object
D. `fieldWithPath("customer.id")` mô tả cả nhánh object
Đáp án đúng: B

Câu 21. Để mô tả query parameter `page` của GET `/orders?page=2`, dùng snippet nào?
A. `pathParameters(parameterWithName("page").description(...))`
B. `formParameters(parameterWithName("page").description(...))`
C. `queryParameters(parameterWithName("page").description(...))`
D. `requestHeaders(headerWithName("page").description(...))`
Đáp án đúng: C

Câu 22. Với MockMvc GET `/orders/{id}` có URI template, API nào sinh bảng path parameter `id`?
A. `formParameters(parameterWithName("id").description(...))`
B. `pathParameters(parameterWithName("id").description(...))`
C. `responseHeaders(headerWithName("id").description(...))`
D. `queryParameters(parameterWithName("id").description(...))`
Đáp án đúng: B

Câu 23. Muốn mô tả request header `Authorization` của request đã kiểm thử, dùng gì?
A. `requestFields(fieldWithPath("Authorization").description(...))`
B. `requestHeaders(headerWithName("Authorization").description(...))`
C. `responseHeaders(headerWithName("Authorization").description(...))`
D. `pathParameters(parameterWithName("Authorization").description(...))`
Đáp án đúng: B

Câu 24. Muốn ghi tài liệu cho response header `Location` của HTTP 201, snippet nào phù hợp?
A. `responseHeaders(headerWithName("Location").description(...))`
B. `requestHeaders(headerWithName("Location").description(...))`
C. `formParameters(parameterWithName("Location").description(...))`
D. `responseFields(fieldWithPath("Location").description(...))`
Đáp án đúng: A

Câu 25. Khi document request `application/x-www-form-urlencoded`, API nào mô tả form field `email`?
A. `pathParameters(parameterWithName("email").description(...))`
B. `requestHeaders(headerWithName("email").description(...))`
C. `queryParameters(parameterWithName("email").description(...))`
D. `formParameters(parameterWithName("email").description(...))`
Đáp án đúng: D

Câu 26. Khi test upload file multipart tên `attachment`, API nào mô tả part đó?
A. `requestHeaders(headerWithName("attachment").description(...))`
B. `requestFields(fieldWithPath("attachment").description(...))`
C. `pathParameters(parameterWithName("attachment").description(...))`
D. `requestParts(partWithName("attachment").description(...))`
Đáp án đúng: D

Câu 27. Khi một multipart part `metadata` chứa JSON, API nào mô tả field `title` trong part?
A. `requestFields("metadata", fieldWithPath("title").description(...))`
B. `requestParts("metadata", fieldWithPath("title").description(...))`
C. `requestPartFields("metadata", fieldWithPath("title").description(...))`
D. `responseFields("metadata", fieldWithPath("title").description(...))`
Đáp án đúng: C

Câu 28. Khi API trả hypermedia `self` link, mô tả link relation đó bằng API nào?
A. `links(linkWithRel("self").description(...))` mô tả link
B. `responseHeaders(headerWithName("self").description(...))`
C. `pathParameters(parameterWithName("self").description(...))`
D. `requestFields(fieldWithPath("self").description(...))`
Đáp án đúng: A

Câu 29. Muốn tạo snippet chỉ chứa body của HTTP response được kiểm thử, dùng gì?
A. `curlRequest()` tạo snippet thân response
B. `requestBody()` tạo snippet thân response
C. `responseBody()` tạo snippet của HTTP response body
D. `httpRequest()` tạo snippet thân response
Đáp án đúng: C

Câu 30. Để định dạng JSON trong response snippet cho dễ đọc, chọn preprocessor nào?
A. `preprocessRequest(prettyPrint())` định dạng response
B. `preprocessResponse(prettyPrint())` định dạng response
C. `preprocessResponse(removeHeaders(...))` định dạng JSON
D. `preprocessRequest(removeHeaders(...))` định dạng JSON
Đáp án đúng: B

Câu 31. Để tránh ghi giá trị Authorization vào tài liệu từ request thử nghiệm, cách nào phù hợp?
A. `requestHeaders(headerWithName("Authorization"))` ẩn header
B. `responseHeaders(headerWithName("Authorization"))` ẩn header
C. `preprocessRequest(removeHeaders("Authorization"))` ẩn header
D. `preprocessResponse(removeHeaders("Authorization"))` ẩn header request
Đáp án đúng: C

Câu 32. Muốn làm đẹp JSON của request trong snippet mà không sửa HTTP request thật, dùng gì?
A. `responseBody()` tự pretty-print JSON request
B. `preprocessResponse(prettyPrint())` chỉ định dạng request
C. `requestFields(fieldWithPath("body"))` tự pretty-print
D. `preprocessRequest(prettyPrint())` chỉ định dạng snippet
Đáp án đúng: D

Câu 33. Trong test Spring Boot, annotation nào thường tự cấu hình Spring REST Docs tích hợp với test?
A. `@AutoConfigureMockMvc` tạo các snippet từ API khi test
B. `@SpringBootTest` sinh các snippet từ API khi test
C. `@AutoConfigureRestDocs` hỗ trợ REST Docs trong Boot test
D. `@RestController` cấu hình tài liệu khi test
Đáp án đúng: C

Câu 34. Trong Asciidoctor, cú pháp nào chèn file `http-response.adoc` đã sinh cho `orders-get`?
A. `include::{snippets}/orders-get/http-response.adoc[]`
B. `include::{snippets}/orders-get/curl-request.adoc[]`
C. `include::{snippets}/orders-get/http-request.adoc[]`
D. `include::{snippets}/orders-get/request-fields.adoc[]`
Đáp án đúng: A

Câu 35. Trong dự án Gradle, thư mục thường cấu hình lưu các snippets của test là đâu?
A. `build/classes/generated-snippets` lưu snippet khi test
B. `src/main/java/generated-snippets` lưu snippet khi test
C. `build/generated-snippets` chứa output snippets của test
D. `src/test/java/generated-snippets` lưu snippet khi test
Đáp án đúng: C

Câu 36. Tại sao task Asciidoctor thường phụ thuộc task test trong pipeline build tài liệu?
A. Asciidoctor phải chạy trước test để viết HTTP assertions
B. Chạy test sinh snippets trước bước render Asciidoctor
C. Task test tự quét Asciidoctor để phát hiện controller
D. Task test cần HTML output để gửi HTTP requests tới MockMvc
Đáp án đúng: B

Câu 37. Khi REST controller đổi trường response, lợi ích của test strict `responseFields` là gì?
A. Test báo lỗi khi body có field không khớp với docs
B. Snippet giữ bản cũ và test không cần chạy khi API thay đổi
C. RestDocs tự migrate database schema cho response mới
D. Tài liệu tự đổi payload thật của controller cho phù hợp
Đáp án đúng: A

Câu 38. Vì sao snippets lấy từ HTTP test thường đáng tin hơn ví dụ JSON chép tay?
A. Chúng chứa SQL schema nên không phụ thuộc API execution
B. Chúng lấy dữ liệu từ OpenAPI generator nên không cần test
C. Chúng tự chạy production traffic khi render Asciidoctor
D. Ví dụ bám request/response thực sự được test
Đáp án đúng: D

Câu 39. Với endpoint trả lỗi HTTP 404, nên chứng minh tài liệu error response bằng cách nào?
A. Document chỉ happy-path 200 rồi suy ra body của HTTP 404
B. Gán `@ResponseStatus(404)` vào tài liệu Asciidoctor
C. Ghi ví dụ lỗi thủ công mà không chạy test HTTP 404
D. Test HTTP 404 và mô tả các trường của error response
Đáp án đúng: D

Câu 40. Trong CI, trình tự nào duy trì tài liệu REST nhất quán với code mới?
A. Chạy HTTP tests sinh snippets rồi build và kiểm tài liệu
B. Sinh lại OpenAPI schemas rồi tắt kiểm thử Spring REST Docs
C. Chỉ xuất HTML thủ công từ source code không chạy tests
D. Render tài liệu cũ rồi bỏ qua test API khi đổi controller
Đáp án đúng: A
