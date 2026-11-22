# Đánh giá giải pháp bằng độ chính xác, khả năng đọc và tính tái tạo

## 1. Mục tiêu bài học

Trong module **SPRING_REST_DOCS**, ta tạo tài liệu REST API có thể kiểm chứng bằng các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Test gửi request, xác nhận response và Spring REST Docs sinh snippet cho request, response, payload, tham số và header. Các snippet được biên soạn bằng Asciidoctor/Markdown rồi đưa vào build và CI.

Một bộ tài liệu API hoàn chỉnh không chỉ cần build thành công. Nó cần mô tả đúng hành vi thực tế, giúp người đọc nhanh chóng thực hiện request và có thể được tạo lại từ một môi trường sạch. Ba tiêu chí của bài capstone:

- **Độ chính xác:** ví dụ, status, header, payload và mô tả field khớp với hành vi được test.
- **Khả năng đọc:** người tích hợp hiểu cách gọi endpoint, dữ liệu cần gửi, response nhận được và cách xử lý lỗi.
- **Tính tái tạo:** người khác có thể checkout source, chạy test và tạo lại cùng bộ snippet/tài liệu mà không cần sửa thủ công.

Sau bài học, bạn có thể đánh giá một giải pháp Spring REST Docs bằng rubric có bằng chứng, phát hiện trade-off và lập kế hoạch cải thiện trước khi phát hành tài liệu.

## 2. Bối cảnh capstone

Giả sử nhóm phát triển API quản lý đơn hàng với các endpoint:

| Method | Endpoint | Thành công | Lỗi tiêu biểu |
| --- | --- | --- | --- |
| POST | /api/orders | 201 Created | 400 validation, 401 unauthorized |
| GET | /api/orders/{id} | 200 OK | 404 not found |
| GET | /api/orders | 200 OK với danh sách và paging | 400 query không hợp lệ |
| POST | /api/orders/{id}/cancel | 204 No Content | 403 forbidden, 409 conflict |

Nhóm dùng MockMvc để document Spring MVC controller, Spring REST Docs để sinh snippets, Asciidoctor để biên soạn tài liệu và Gradle/CI để tự động hóa.

Capstone không chấm số lượng trang hoặc số lượng snippet. Mục tiêu là chứng minh rằng người đọc có thể hiểu và sử dụng API dựa trên tài liệu, còn nhóm có thể tái tạo tài liệu từ test.

## 3. Ba trục đánh giá

| Trục | Trọng số | Câu hỏi đánh giá |
| --- | ---: | --- |
| Accuracy | 40% | Tài liệu có đúng contract và được test xác nhận không? |
| Readability | 30% | Developer có thể hiểu và thực hiện request từ tài liệu không? |
| Reproducibility | 30% | Có thể tạo lại tài liệu từ checkout sạch bằng quy trình tự động không? |

Tỷ trọng là gợi ý cho bài tập. Nhóm có thể điều chỉnh, nhưng không nên để một tiêu chí bù hoàn toàn cho một tiêu chí yếu nghiêm trọng. Tài liệu đẹp nhưng sai contract vẫn không thể phát hành; tài liệu chính xác nhưng không thể build lại cũng khó duy trì.

## 4. Đánh giá độ chính xác

Độ chính xác trả lời câu hỏi: “Những gì tài liệu nói có được test xác nhận và có đúng với contract mà client nhìn thấy không?”

### 4.1. Request phải đúng

Kiểm tra:

- HTTP method và path có đúng mapping không?
- Path variables, query parameters và encoding có chính xác không?
- Request headers như Content-Type, Accept, Authorization có được mô tả đúng không?
- Request body có đúng field, kiểu dữ liệu, required/optional và nested structure không?
- Ví dụ có dùng giá trị hợp lệ, nhất quán với validation và business rules không?

Một ví dụ request có thể trông hợp lý nhưng sai nếu field quantity được document là optional trong khi DTO yêu cầu giá trị dương. Hãy đối chiếu snippet với test assertion và schema thực tế.

### 4.2. Response phải đúng

Kiểm tra:

- Status code có đúng cho từng trường hợp thành công và thất bại không?
- Response headers có phản ánh media type, pagination, location hoặc correlation ID mà API cam kết không?
- Body có đúng cấu trúc, field path, nullability và format không?
- Error code có ổn định và gắn đúng HTTP status không?
- Empty response, redirect, async hoặc streaming response có được mô tả đúng không?

Đặc biệt, không lấy một response 200 làm ví dụ cho mọi nhánh lỗi. Mỗi nhóm lỗi quan trọng nên có test và operation snippet riêng.

### 4.3. Descriptors phải khớp payload

Spring REST Docs giúp phát hiện khác biệt giữa payload và field descriptors:

~~~java
responseFields(
    fieldWithPath("id")
        .description("Mã định danh đơn hàng."),
    fieldWithPath("status")
        .description("Trạng thái hiện tại của đơn hàng."),
    fieldWithPath("items[]")
        .description("Danh sách sản phẩm trong đơn hàng.")
)
~~~

Đánh giá descriptor:

- Field path đúng với JSON thật, bao gồm nested path và collection.
- Type/format được giải thích đủ để client sử dụng.
- Optional chỉ được đánh dấu khi hợp đồng cho phép vắng mặt.
- Field ignored hoặc relaxed descriptor phải có lý do rõ ràng.
- Không dùng relaxedResponseFields để che việc tài liệu chưa mô tả một field quan trọng.

### 4.4. Test là bằng chứng, không phải lời khẳng định

Test cần assertion vào các điểm quyết định contract:

~~~java
mockMvc.perform(get("/api/orders/{id}", 42))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.id").value(42))
    .andExpect(jsonPath("$.status").value("CREATED"))
    .andDo(document("orders/get"));
~~~

Nếu test chỉ kiểm tra status 200 rồi document toàn bộ response, test chưa chứng minh những giá trị nghiệp vụ quan trọng. Bổ sung assertion có chủ đích, đặc biệt cho error code, pagination metadata, header và field bắt buộc.

## 5. Đánh giá khả năng đọc

Khả năng đọc trả lời câu hỏi: “Một developer chưa biết hệ thống có thể gọi API thành công và hiểu cách xử lý response không?”

### 5.1. Cấu trúc tài liệu theo nhiệm vụ của người đọc

Một operation nên trình bày theo thứ tự:

1. Mục đích và điều kiện sử dụng.
2. HTTP method, endpoint và quyền truy cập.
3. Path/query parameters và request headers.
4. Request body với ví dụ thực tế.
5. Response status, headers và body.
6. Lỗi thường gặp, error code và hướng khắc phục.
7. Liên kết tới schema hoặc operation liên quan.

Người đọc nên tìm được thông tin cần thiết mà không phải lần ngược qua test source code.

### 5.2. Description phải trả lời “vì sao” và “dùng thế nào”

Description yếu:

~~~java
fieldWithPath("status").description("Status");
~~~

Description tốt hơn:

~~~java
fieldWithPath("status")
    .description("Trạng thái đơn hàng. CREATED là mới tạo, PAID là đã thanh toán và SHIPPED là đã bàn giao vận chuyển.");
~~~

Mô tả tốt nêu ý nghĩa, giá trị có thể nhận và hệ quả đối với client. Không lặp lại tên field bằng một từ đồng nghĩa.

### 5.3. Ví dụ phải nhất quán

Nếu request dùng customerId = 1001, response nên tham chiếu đúng khách hàng đó. Nếu response có status = PAID, phần giải thích phải nói rõ điều kiện để đơn hàng đạt trạng thái này. Tránh copy/paste khiến ID, ngày tháng hoặc status mâu thuẫn giữa các snippet.

### 5.4. Giữ tài liệu dễ quét

- Dùng heading có ý nghĩa theo endpoint hoặc nghiệp vụ.
- Dùng bảng cho parameters, headers, error codes và enum values.
- Giữ code block ngắn, có thể chạy hoặc có đủ ngữ cảnh để hiểu.
- Đặt giải thích trước hoặc ngay sau snippet liên quan.
- Không đưa toàn bộ implementation detail vào hướng dẫn client.
- Dùng thuật ngữ nhất quán cho cùng một khái niệm.

## 6. Đánh giá tính tái tạo

Tính tái tạo trả lời câu hỏi: “Một developer khác có thể tạo lại chính bộ tài liệu này từ repository không?”

### 6.1. Build phải có thứ tự rõ ràng

~~~mermaid
flowchart TD
    A["Checkout source"] --> B["Resolve dependencies"]
    B --> C["Run HTTP documentation tests"]
    C --> D["Generate REST Docs snippets"]
    D --> E["Run Asciidoctor"]
    E --> F["Validate output"]
    F --> G["Publish CI artifact"]
~~~

Test phải chạy trước Asciidoctor vì snippet là input của bước biên soạn. Không dùng snippet cũ còn sót từ lần build trước để làm build hiện tại có vẻ thành công.

### 6.2. Môi trường phải ổn định

Kiểm tra:

- Java và Gradle wrapper version được pin.
- Dependency Spring Boot/Spring REST Docs được quản lý nhất quán.
- Test không phụ thuộc API bên ngoài hoặc credential cá nhân.
- Clock, random ID và dữ liệu test được kiểm soát.
- Locale, timezone và encoding không làm thay đổi snippet ngoài dự kiến.
- Generated snippets được tạo vào build directory sạch.

Nếu trace ID hoặc timestamp thay đổi mỗi lần chạy, snippet diff sẽ nhiễu. Dùng test fixture ổn định hoặc preprocessor có chủ đích, nhưng vẫn giữ assertion để xác nhận hành vi thật.

### 6.3. Không chỉnh sửa snippet sinh tự động

Snippet là output từ test. Không sửa tay file trong build/generated-snippets để làm tài liệu đẹp hơn. Hãy sửa:

- Test fixture nếu dữ liệu ví dụ không phù hợp.
- Assertion nếu test chưa kiểm chứng contract.
- Field/header descriptors nếu mô tả thiếu.
- Operation preprocessor nếu cần chuẩn hóa URI hoặc che dữ liệu.
- Asciidoctor source nếu cần thêm phần diễn giải, bảng tổng hợp hoặc cấu trúc.

Sau thay đổi, chạy lại test để snippet được sinh từ source of truth.

## 7. Rubric đánh giá chi tiết

Chấm mỗi tiêu chí theo thang 0–4:

| Điểm | Ý nghĩa |
| ---: | --- |
| 0 | Không có hoặc sai nghiêm trọng. |
| 1 | Có nhưng thiếu nhiều phần, khó tin cậy. |
| 2 | Đạt một phần, còn thiếu ví dụ/assertion quan trọng. |
| 3 | Đạt yêu cầu, có bằng chứng và dễ sử dụng. |
| 4 | Rất tốt, nhất quán, có thể bảo trì và kiểm chứng tự động. |

### 7.1. Accuracy — 40%

| Tiêu chí | Bằng chứng để chấm |
| --- | --- |
| Request contract | Request snippet, path/query/header descriptors và test assertions. |
| Response contract | Status, response header/body snippets và assertions. |
| Payload descriptors | Field paths, types, optionality, nested objects và arrays. |
| Error contract | Status, error codes, validation details và ví dụ từng nhóm lỗi. |
| Example consistency | Request/response examples nhất quán và có thể thực hiện. |

### 7.2. Readability — 30%

| Tiêu chí | Bằng chứng để chấm |
| --- | --- |
| Information architecture | Mục lục và thứ tự operation phù hợp nhiệm vụ người đọc. |
| Description quality | Mô tả ý nghĩa, constraints và cách sử dụng, không chỉ lặp tên field. |
| Example clarity | Code block có ngữ cảnh, dữ liệu dễ hiểu và nhất quán. |
| Navigation | Người đọc tìm được endpoint, error code và schema liên quan. |

### 7.3. Reproducibility — 30%

| Tiêu chí | Bằng chứng để chấm |
| --- | --- |
| Clean build | Có thể chạy từ checkout sạch, không dựa snippet cũ. |
| Deterministic output | Fixture/clock/locale/ID được kiểm soát; diff không nhiễu. |
| CI integration | Test chạy trước Asciidoctor; build fail khi test hoặc snippet contract fail. |
| Maintenance | Không sửa tay generated snippets; source và version được quản lý. |

## 8. Ví dụ scorecard cho một bộ tài liệu

Giả sử nhóm review một bộ tài liệu có kết quả:

| Trục | Điểm trung bình (0–4) | Trọng số | Điểm quy đổi |
| --- | ---: | ---: | ---: |
| Accuracy | 3.5 | 40% | 35.0/40 |
| Readability | 2.5 | 30% | 18.75/30 |
| Reproducibility | 4.0 | 30% | 30.0/30 |
| **Tổng** | | | **83.75/100** |

Cách tính mỗi trục:

\[
\text{Điểm trục} =
\frac{\text{Điểm trung bình}}{4}
\times \text{Trọng số}
\]

Kết quả 83.75 không có nghĩa tài liệu tự động được phát hành. Review vẫn phải kiểm tra các lỗi chặn như secret bị lộ, status sai hoặc endpoint quan trọng không có ví dụ. Một lỗi nghiêm trọng có thể khiến bộ tài liệu không đạt dù tổng điểm cao.

## 9. Quality gates trước khi phát hành

Nên tách tiêu chí chấm điểm khỏi các điều kiện bắt buộc:

| Gate | Điều kiện đạt |
| --- | --- |
| Contract | Test assertions và REST Docs descriptors phản ánh đúng endpoint được công bố. |
| Coverage | Có ví dụ cho luồng thành công và các lỗi quan trọng theo phạm vi API. |
| Security | Không có token, secret, dữ liệu cá nhân hoặc debug detail ngoài ý muốn. |
| Build | Clean test và Asciidoctor build thành công. |
| Output | Snippets và tài liệu cuối cùng được sinh đầy đủ, không dùng output cũ. |
| Review | Có người review nội dung và các thay đổi contract. |

Không phát hành chỉ dựa vào tổng điểm rubric nếu một gate bắt buộc chưa đạt.

## 10. Quy trình review một operation

Với từng endpoint, reviewer có thể thực hiện:

1. Đọc mô tả endpoint và xác định người dùng API cần làm gì.
2. Đọc test để xem request nào được gửi và assertion nào bảo vệ contract.
3. Đọc http-request.adoc và xác nhận method, URI, headers, body.
4. Đọc http-response.adoc và xác nhận status, headers, body.
5. Đọc request/response fields snippets để kiểm tra schema.
6. So sánh mô tả trong Asciidoctor với snippets và error behavior.
7. Kiểm tra dữ liệu nhạy cảm và thông tin nội bộ.
8. Chạy lại build từ trạng thái sạch để xác nhận tính tái tạo.

Nếu reviewer không thể giải thích cách gọi endpoint chỉ từ tài liệu, khả năng đọc chưa đạt. Nếu phải sửa snippet bằng tay để build pass, tính tái tạo chưa đạt.

## 11. Ví dụ test và document có chất lượng

Ví dụ test tạo đơn hàng:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
            {
              "customerId": 1001,
              "items": [
                {
                  "productId": "BOOK-01",
                  "quantity": 2
                }
              ]
            }
            """))
    .andExpect(status().isCreated())
    .andExpect(header().exists("Location"))
    .andExpect(jsonPath("$.id").isNumber())
    .andExpect(jsonPath("$.status").value("CREATED"))
    .andDo(document("orders/create",
        requestFields(
            fieldWithPath("customerId")
                .description("Mã khách hàng đã được xác thực và có quyền tạo đơn."),
            fieldWithPath("items")
                .description("Danh sách sản phẩm cần đặt."),
            fieldWithPath("items[].productId")
                .description("Mã sản phẩm trong catalog."),
            fieldWithPath("items[].quantity")
                .description("Số lượng phải lớn hơn hoặc bằng 1.")
        ),
        responseHeaders(
            headerWithName("Location")
                .description("URI của đơn hàng vừa được tạo.")
        ),
        responseFields(
            fieldWithPath("id")
                .description("Mã định danh đơn hàng mới."),
            fieldWithPath("status")
                .description("Trạng thái ban đầu của đơn hàng.")
        )
    ));
~~~

Đánh giá ví dụ:

- **Accuracy:** test xác nhận 201, Location, id và status; descriptors mô tả request/response fields.
- **Readability:** descriptions giải thích ý nghĩa và constraint; operation ID dễ hiểu.
- **Reproducibility:** test dùng dữ liệu fixture rõ ràng; snippet được sinh qua document(...).

Đoạn code là minh họa cho một test đã có MockMvc và REST Docs configured; dự án cần import static và setup phù hợp.

## 12. Đánh giá error documentation

Một bộ tài liệu tốt không chỉ document 2xx. Ví dụ lỗi validation:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "customerId": 1001,
              "items": []
            }
            """))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
    .andExpect(jsonPath("$.errors").isArray())
    .andDo(document("orders/create-validation-error",
        responseFields(
            fieldWithPath("code")
                .description("Mã lỗi tổng quát."),
            fieldWithPath("message")
                .description("Thông điệp giải thích lỗi."),
            fieldWithPath("errors")
                .description("Danh sách lỗi validation."),
            fieldWithPath("errors[].path")
                .description("Đường dẫn tới field không hợp lệ."),
            fieldWithPath("errors[].code")
                .description("Mã lỗi cụ thể của field."),
            fieldWithPath("errors[].message")
                .description("Giải thích điều kiện validation.")
        )
    ));
~~~

Reviewer cần kiểm tra error payload thực tế có đúng cấu trúc trên không, đặc biệt nếu object-level error có path nullable hoặc response có thêm field. Không sao chép descriptor từ ví dụ mà không đối chiếu response.

## 13. Kiểm tra tính ổn định của output

Chạy build hai lần từ trạng thái sạch và so sánh:

~~~bash
./gradlew clean test asciidoctor
~~~

~~~bash
./gradlew clean test asciidoctor
~~~

Kết quả mong muốn:

- Cùng test source và fixture tạo cùng nội dung snippet.
- Không phụ thuộc thứ tự test.
- Không phụ thuộc thời gian hiện tại, timezone hoặc locale ngoài ý muốn.
- Không cần file snippet từ lần chạy trước.
- Không cần thao tác chỉnh sửa thủ công sau khi build.

Nếu output có timestamp hoặc ID động, xác định đó có phải một phần contract cần document hay chỉ là noise. Có thể dùng test fixture hoặc operation preprocessor để chuẩn hóa snippet; không thay đổi hành vi được assertion kiểm tra.

## 14. Tích hợp Gradle và CI

Ví dụ cấu hình task:

~~~groovy
def snippetsDir = layout.buildDirectory.dir("generated-snippets")

tasks.named("test") {
    outputs.dir(snippetsDir)
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(snippetsDir)
    attributes "snippets": snippetsDir.get().asFile
}
~~~

Pipeline có thể gồm:

~~~yaml
steps:
  - name: Run documentation tests and build API docs
    run: ./gradlew clean test asciidoctor
  - name: Archive generated API documentation
    uses: actions/upload-artifact@v4
    with:
      name: spring-rest-docs
      path: build/docs/asciidoc
~~~

Đây là ví dụ workflow tổng quát; tên task, output path và artifact action phải khớp cấu hình repository. Không copy nguyên path nếu plugin của dự án xuất tài liệu ở vị trí khác.

## 15. Lỗi thường gặp khi đánh giá

| Nhận xét sai | Vì sao chưa đủ | Cách đánh giá đúng |
| --- | --- | --- |
| “Build thành công nên docs chính xác” | Build chỉ chứng minh các bước đã chạy, không chứng minh test assertion bao phủ contract | Kiểm tra assertions và snippets theo endpoint. |
| “Có đủ snippets nên dễ đọc” | Snippet có thể thiếu ngữ cảnh, mô tả và thứ tự | Thử thực hiện một nhiệm vụ chỉ dựa trên tài liệu. |
| “CI xanh nên có thể tái tạo” | CI có thể dùng cache hoặc output cũ | Chạy clean build, kiểm tra generated output và dependency pinning. |
| “Dùng relaxed descriptors giúp test ổn định” | Có thể che field mới hoặc field quan trọng chưa được document | Dùng strict descriptors cho contract quan trọng; giải thích rõ ngoại lệ. |
| “Che token trong snippet là đủ an toàn” | Secret vẫn có thể xuất hiện trong test log, report hoặc artifact khác | Kiểm tra toàn bộ output và không dùng secret thật trong fixture. |
| “Hai client phải sinh byte giống hệt nhau” | Host/port/runtime header có thể khác theo binding mode | So sánh contract có ý nghĩa và chuẩn hóa khác biệt có chủ đích. |

## 16. Bài tập capstone

Hoàn thiện bộ tài liệu cho API quản lý đơn hàng với yêu cầu:

1. Document POST /api/orders với request fields, response fields, 201 và Location.
2. Document GET /api/orders/{id} với path parameter và 404 error.
3. Document GET /api/orders với query parameters, paging metadata và response list.
4. Document lỗi validation field-level và object-level.
5. Document lỗi 401/403/409 theo contract thực tế.
6. Che credential, cookie và dữ liệu cá nhân khỏi snippets.
7. Tổ chức Asciidoctor thành phần Overview, Authentication, Orders, Errors và Troubleshooting.
8. Nối Gradle test và Asciidoctor vào CI.
9. Chạy hai clean builds và so sánh output.
10. Dùng rubric ở mục 7 để chấm, ghi evidence và tạo danh sách việc cần cải thiện.

## 17. Mẫu báo cáo đánh giá

Khi review, ghi kết quả theo mẫu:

~~~text
Project:
Commit:
Build command:

Accuracy: __ / 4
Evidence:
- Request contract:
- Response contract:
- Field descriptors:
- Error contract:

Readability: __ / 4
Evidence:
- Navigation:
- Descriptions:
- Examples:

Reproducibility: __ / 4
Evidence:
- Clean build:
- Deterministic output:
- CI integration:

Blocking issues:
1.

Improvements:
1.

Decision: PASS / NEEDS WORK
~~~

Evidence phải trỏ tới test, snippet, tài liệu hoặc CI result cụ thể. Tránh nhận xét chung như “docs ổn” hoặc “code sạch” mà không chỉ ra căn cứ.

## 18. Ghi nhớ

- Độ chính xác được chứng minh bằng test assertions và snippets khớp contract.
- Khả năng đọc được đánh giá qua việc developer có thể hiểu và gọi API từ tài liệu.
- Tính tái tạo yêu cầu clean build, fixture ổn định, dependency được quản lý và CI chạy đúng thứ tự.
- Snippet là output từ test; không chỉnh sửa thủ công generated snippets.
- Strict descriptors giúp phát hiện payload thay đổi ngoài dự kiến.
- Security, contract correctness và clean build là quality gates, không chỉ là điểm cộng trong rubric.
- Scorecard cần có bằng chứng và danh sách cải thiện cụ thể.

## 19. Tài liệu tham khảo

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/reference/getting-started.html): cấu hình test và tạo tài liệu từ snippets.
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html): các loại snippets cho request, response, headers và payload.
- [Spring REST Docs — Gradle Plugin](https://docs.spring.io/spring-restdocs/reference/gradle.html): tích hợp Asciidoctor và Gradle.
